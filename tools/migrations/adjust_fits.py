"""Stage library panel fit adjustments and provide shared migration helpers.

Without --apply, prepare and reopen verified .blend/.png copies outside
the library, preserving originals. With --apply, validate hashes before
publishing. Existing index entries, resource names and catalog UUIDs stay stable."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sys
import bpy

RAIZ = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, RAIZ)
import archy_builder as addon


def digital(caminho):
    with open(caminho, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def caminho_da_peca(pasta, nome):
    if os.path.basename(nome) != nome or nome in ('', '.', '..'):
        raise ValueError("Filename points outside the library: " + nome)
    return os.path.join(pasta, nome)


def validar_destino(biblioteca, destino):
    """CLI and direct calls use the same external staging folder.
    realpath resolves junctions; normcase preserves this rule on Windows."""
    biblioteca, destino = [os.path.normcase(os.path.realpath(os.path.abspath(p)))
                           for p in (biblioteca, destino)]
    try:
        dentro = os.path.commonpath((biblioteca, destino)) == biblioteca
    except ValueError:
        dentro = False
    if dentro:
        raise ValueError("Backup and staging must be OUTSIDE the library")


def limpar():
    # Successive libraries must not acquire .001 names from residual IDs.
    for nome in ('objects', 'collections', 'meshes', 'armatures', 'actions',
                 'curves', 'cameras', 'lights', 'materials', 'node_groups', 'images'):
        dados = getattr(bpy.data, nome)
        for d in list(dados):
            dados.remove(d, do_unlink=True)


def carregar(caminho):
    limpar()
    with bpy.data.libraries.load(caminho, link=False) as (de, para):
        para.collections = list(de.collections)
        para.objects = list(de.objects)
    for c in para.collections:
        if c.asset_data:
            bpy.context.scene.collection.children.link(c)
    bpy.context.view_layer.update()
    return list(para.collections), list(para.objects)


def valor_json(v):
    if isinstance(v, bpy.types.ID):
        return {'id': v.name, 'tipo': v.bl_rna.identifier}
    if hasattr(v, 'to_dict'):
        v = v.to_dict()
    if isinstance(v, dict):
        return {k: valor_json(x) for k, x in v.items()}
    if hasattr(v, 'to_list'):
        v = v.to_list()
    if isinstance(v, (list, tuple)):
        return [valor_json(x) for x in v]
    return v


def estado(colecoes, objetos):
    return dict(
        assets={c.name: c.asset_data.catalog_id for c in colecoes if c.asset_data},
        objetos={o.name: dict(
            matriz=[v for linha in o.matrix_world for v in linha],
            props={k: valor_json(v) for k, v in o.items() if not k.startswith('adj_')},
            medidas=[o.chapa_largura_mm, o.chapa_comprimento_mm, o.chapa_espessura_mm]
                    if addon.chapas.MARCA_CHAPA in o else None,
            materiais=[[s.link, s.material.name if s.material else None] for s in o.material_slots],
            malha=hashlib.sha256(repr(([tuple(v.co) for v in o.data.vertices],
                                      [tuple(p.vertices) for p in o.data.polygons])).encode()).hexdigest()
                  if o.type == 'MESH' else None)
            for o in objetos})


def conferir(a, b, caminho='estado'):
    if isinstance(a, dict):
        if a.keys() != b.keys():
            raise AssertionError("Different identities: " + caminho)
        for k in a:
            conferir(a[k], b[k], caminho + '/' + k)
    elif isinstance(a, list):
        if len(a) != len(b):
            raise AssertionError("Different lengths: " + caminho)
        for i, (x, y) in enumerate(zip(a, b)):
            conferir(x, y, caminho + '/%d' % i)
    elif isinstance(a, float):
        if abs(a - b) > 1e-5:
            raise AssertionError("Dimension/position changed: " + caminho)
    elif a != b:
        raise AssertionError("Different data: " + caminho)


def preparar(biblioteca, destino):
    validar_destino(biblioteca, destino)
    originais = os.path.join(destino, 'originais')
    novos = os.path.join(destino, 'novos')
    os.makedirs(originais, exist_ok=False)
    os.makedirs(novos, exist_ok=False)
    # If register/timers run, they also stay outside the real library.
    addon.opcoes._pasta_addon = lambda: novos
    addon.biblioteca.pasta_biblioteca = lambda: novos
    addon.register()
    with open(os.path.join(biblioteca, 'indice.json'), encoding='utf-8') as f:
        indice = json.load(f)
    manifesto = dict(biblioteca=biblioteca, versao=addon.bl_info['version'],
                     verificados=0, modulos=[], arquivos=[], publicado=False)
    for it in indice:
        if it.get('tipo') != 'modulo' or len(addon.biblioteca.caminho_de(it)) < 4:
            continue
        nomes = [it['arquivo'], os.path.splitext(it['arquivo'])[0] + '.png']
        hashes_originais = {nome: digital(caminho_da_peca(biblioteca, nome))
                            if os.path.isfile(caminho_da_peca(biblioteca, nome)) else None for nome in nomes}
        fonte = caminho_da_peca(biblioteca, it['arquivo'])
        colecoes, objetos = carregar(fonte)
        grupos = [o for o in objetos if addon.chapas.MARCA_CONJUNTO in o]
        manifesto['verificados'] += 1
        antes = estado(colecoes, objetos)
        ajustes = [a for g in grupos for a in addon.promob.ajustar_encaixes(g)]
        if not ajustes:
            continue
        esperado = estado(colecoes, objetos)
        alteradas = {a['chapa'] for a in ajustes}
        # Only base/top positions may change; mesh/thickness and systems remain intact.
        antes_sem_posicoes = valor_json(antes)
        for nome in alteradas:
            antes_sem_posicoes['objetos'][nome]['matriz'] = esperado['objetos'][nome]['matriz']
        conferir(antes_sem_posicoes, esperado)
        for g in grupos:
            if addon.promob.encaixes_a_ajustar(g):
                raise AssertionError("Joint still open: " + it['arquivo'])
        for nome in nomes:
            original = caminho_da_peca(biblioteca, nome)
            if os.path.isfile(original):
                shutil.copy2(original, os.path.join(originais, nome))
                if digital(os.path.join(originais, nome)) != hashes_originais[nome]:
                    raise RuntimeError("File edited during preparation: " + nome)
        blend = os.path.join(novos, nomes[0])
        bpy.data.libraries.write(blend, set(colecoes) | set(objetos),
                                 fake_user=True, compress=True)
        # The photo follows the library standard, but the asset remains CLOSED.
        for g in grupos:
            for porta in addon.portas._portas_do_conjunto(g):
                for folha in addon.portas._folhas_portas(porta):
                    addon.ferragens._definir_abertura(bpy.context, folha, addon.biblioteca.ABERTURA_FOTO)
        png = os.path.join(novos, nomes[1])
        ok, msg = addon.biblioteca.fotografar_com_camera(png, objetos)
        if not ok:
            raise RuntimeError("Photo for %s: %s" % (it['arquivo'], msg))
        limpar()
        ok, msg = addon.biblioteca.aplicar_preview_png(blend, png)
        if not ok:
            raise RuntimeError("Preview for %s: %s" % (it['arquivo'], msg))
        cols, objs = carregar(blend)
        conferir(esperado, estado(cols, objs))
        for g in [o for o in objs if addon.chapas.MARCA_CONJUNTO in o]:
            if addon.promob.encaixes_a_ajustar(g):
                raise AssertionError("Reopened file has a gap: " + it['arquivo'])
        for c in cols:
            if c.asset_data and (not c.preview or c.preview.image_size[0] == 0):
                raise AssertionError("Preview lost: " + it['arquivo'])
        manifesto['modulos'].append(dict(arquivo=it['arquivo'], ajustes=ajustes))
        for nome in nomes:
            original = caminho_da_peca(biblioteca, nome)
            if (digital(original) if os.path.isfile(original) else None) != hashes_originais[nome]:
                raise RuntimeError("File edited during preparation: " + nome)
            manifesto['arquivos'].append(dict(nome=nome,
                original=hashes_originais[nome],
                novo=digital(os.path.join(novos, nome))))
        print("[fits] %d: %s (%d panels)" % (
            len(manifesto['modulos']), it['arquivo'], len(ajustes)), flush=True)
    limpar()
    addon.unregister()
    with open(os.path.join(destino, 'manifesto.json'), 'w', encoding='utf-8') as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=1)
    return manifesto


def publicar(destino):
    caminho = os.path.join(destino, 'manifesto.json')
    with open(caminho, encoding='utf-8') as f:
        manifesto = json.load(f)
    biblioteca = manifesto['biblioteca']
    validar_destino(biblioteca, destino)
    # Check ALL hashes before replacing the first file; do not overwrite recent edits.
    for arq in manifesto['arquivos']:
        atual = caminho_da_peca(biblioteca, arq['nome'])
        if (digital(atual) if os.path.isfile(atual) else None) != arq['original']:
            raise RuntimeError("Library changed since preparation: " + arq['nome'])
        if arq['original'] is not None and digital(os.path.join(destino, 'originais', arq['nome'])) != arq['original']:
            raise RuntimeError("Backup changed: " + arq['nome'])
        if digital(os.path.join(destino, 'novos', arq['nome'])) != arq['novo']:
            raise RuntimeError("Staged file changed: " + arq['nome'])
    aplicados = []
    temporario = None
    try:
        for arq in manifesto['arquivos']:
            alvo = caminho_da_peca(biblioteca, arq['nome'])
            temporario = alvo + '.encaixe-novo'
            shutil.copyfile(os.path.join(destino, 'novos', arq['nome']), temporario)
            os.replace(temporario, alvo)
            aplicados.append(arq)
    except Exception:
        # The failed file's temporary copy must not remain in the real library.
        if temporario and os.path.exists(temporario):
            os.remove(temporario)
        for arq in aplicados:
            alvo = caminho_da_peca(biblioteca, arq['nome'])
            if arq['original'] is not None:
                shutil.copy2(os.path.join(destino, 'originais', arq['nome']), alvo)
            else:
                os.remove(alvo)
        raise
    manifesto['publicado'] = True
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=1)
    print("[fits] PUBLISHED %d cabinets; backup in %s" % (len(manifesto['modulos']), destino))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', required=True, dest='destino', metavar='DESTINATION')
    parser.add_argument('--library', default=os.path.join(RAIZ, 'archy_builder', "assets/library"), dest='biblioteca', metavar='LIBRARY')
    parser.add_argument('--apply', action='store_true', dest='aplicar')
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = parser.parse_args(argv)
    destino = os.path.abspath(args.destino)
    biblioteca = os.path.abspath(args.biblioteca)
    validar_destino(biblioteca, destino)
    if args.aplicar:
        publicar(destino)
    else:
        preparar(biblioteca, destino)


if __name__ == '__main__':
    main()
