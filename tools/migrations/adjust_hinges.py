"""Stage angular hinge fit adjustments with backup and atomic publication."""
from pathlib import Path
import argparse, json, os, shutil, sys
import bpy

RAIZ = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, RAIZ)
import archy_builder as addon
from tools.migrations.adjust_fits import (carregar, limpar, digital, estado,
                                     conferir, publicar, caminho_da_peca)
from tools.migrations.adjust_fits import validar_destino


def preparar(biblioteca, destino):
    validar_destino(biblioteca, destino)
    novos, originais = [os.path.join(destino, p) for p in ('novos', 'originais')]
    os.makedirs(novos, exist_ok=False)
    os.makedirs(originais, exist_ok=False)
    addon.opcoes._pasta_addon = lambda: novos
    addon.biblioteca.pasta_biblioteca = lambda: novos
    addon.register()
    indice = json.load(open(os.path.join(biblioteca, 'indice.json'), encoding='utf-8'))
    m = dict(biblioteca=biblioteca, versao=addon.bl_info['version'], arquivos=[],
             modulos=[], verificados=0, publicado=False)
    for it in indice:
        if it.get('tipo') != 'modulo':
            continue
        nomes = [it['arquivo'], os.path.splitext(it['arquivo'])[0] + '.png']
        hashes = {n: digital(caminho_da_peca(biblioteca, n)) for n in nomes}
        cols, objs = carregar(caminho_da_peca(biblioteca, nomes[0]))
        antes = estado(cols, objs)
        m['verificados'] += 1
        grupos = [o for o in objs if addon.chapas.MARCA_PORTAS in o]
        alterados = []
        for g in grupos:
            p, L, A, folhas = addon.ferragens._porta_calculada(g)
            conj = addon.portas._modulo_da_chapa(addon.portas._folhas_portas(g)[0])
            apoios = addon.ferragens._apoios_obliquos(conj, g.matrix_world, p, L, A, folhas)
            if apoios:
                addon.ferragens._refazer_ferragens(g)
                alterados.append(g.name)
        if not alterados:
            continue
        bpy.context.view_layer.update()
        depois = estado(list(bpy.data.collections), list(bpy.data.objects))
        for obj in objs:
            if not addon.ferragens._vivo(obj) or addon.ferragens.CHAVE_FERRAGEM in obj:
                continue
            a, b = antes['objetos'][obj.name], depois['objetos'][obj.name]
            for d in (a, b):
                d['props'].pop('porta_ferragens_encaixe', None)
            conferir(a, b, obj.name)
        conferir(antes['assets'], depois['assets'], "Catalogs")
        for nome in nomes:
            shutil.copy2(caminho_da_peca(biblioteca, nome), os.path.join(originais, nome))
        blend, png = [os.path.join(novos, nome) for nome in nomes]
        bpy.data.libraries.write(blend, set(bpy.data.collections) | set(bpy.data.objects), fake_user=True)
        esperado = estado(list(bpy.data.collections), list(bpy.data.objects))
        conj, = [o for o in objs if addon.chapas.MARCA_CONJUNTO in o]
        addon.biblioteca.preparar_abertura_foto(bpy.context, conj)
        ok, msg = addon.biblioteca.fotografar_com_camera(png, list(bpy.data.objects))
        if not ok:
            raise RuntimeError(msg)
        limpar()
        ok, msg = addon.biblioteca.aplicar_preview_png(blend, png)
        if not ok:
            raise RuntimeError(msg)
        cols, objs = carregar(blend)
        conferir(esperado, estado(cols, objs))
        for nome in nomes:
            if digital(caminho_da_peca(biblioteca, nome)) != hashes[nome]:
                raise RuntimeError("Library edited during preparation: " + nome)
            m['arquivos'].append(dict(nome=nome, original=hashes[nome], novo=digital(os.path.join(novos, nome))))
        m['modulos'].append(dict(arquivo=it['arquivo'], portas=alterados))
        print("[hinges] %s: %s" % (it['arquivo'], alterados), flush=True)
    limpar()
    addon.unregister()
    with open(os.path.join(destino, 'manifesto.json'), 'w', encoding='utf-8') as f:
        json.dump(m, f, indent=1, ensure_ascii=False)
    print('AUDITADOS', m['verificados'], 'CORRIGIDOS', len(m['modulos']), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--destination', required=True, dest='destino', metavar='DESTINATION')
    p.add_argument('--library', default=os.path.join(RAIZ, 'archy_builder', "assets/library"), dest='biblioteca', metavar='LIBRARY')
    p.add_argument('--apply', action='store_true', dest='aplicar')
    a = p.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    destino, biblioteca = os.path.abspath(a.destino), os.path.abspath(a.biblioteca)
    validar_destino(biblioteca, destino)
    if a.aplicar:
        publicar(destino)
    else:
        preparar(biblioteca, destino)


if __name__ == '__main__':
    main()
