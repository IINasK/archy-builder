"""Reconstrui so' portas dos presets Promob pelos DXFs de referencia.

Blender 5.x --background --factory-startup --python este_arquivo --
    --destino PASTA_BACKUP [--fontes PASTA_PROMOB] [--aplicar]
Prepara/reabre/verifica antes de publicar; nao muda indice nem catalogos.
"""
import argparse
import json
import os
import re
import shutil
import statistics
import sys
import bpy
from mathutils import Matrix, Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ajustar_encaixes_promob import (addon, carregar, limpar, estado, conferir,
                                    digital, caminho_da_peca, publicar, valor_json)
from ajustar_encaixes_promob import validar_destino


def capturar(caminho):
    planos = []
    original = addon.promob.planejar
    def planejar(pecas, ferragens):
        plano = original(pecas, ferragens)
        portas = []
        for p in plano['portas']:
            q = {k: v for k, v in p.items() if k not in ('folhas', 'referencia', 'centros')}
            q['referencia'] = [list(r) for r in p['referencia']]
            q['centros'] = [[list(c) for c in cs] for cs in p['centros']]
            q['folhas'] = [{k: v for k, v in f.items() if k not in ('obj', 'original', 'pontos')}
                           for f in p['folhas']]
            portas.append(q)
        planos.append(dict(portas=portas,
            pecas={p['origem']: {k: v for k, v in p.items() if k not in ('obj', 'pontos')}
                   for p in pecas if 'origem' in p},
            remover=[p['origem'] for p in plano['remover']]))
        # O importador faz a mesma separacao por contato, sem criar rigs
        # ou modificar fundos. Aqui queremos apenas referencias numericas.
        return dict(portas=[], gavetas=[], correr=[], remover=[], fundo=None, travessas=[])
    aplicar = addon.promob.aplicar
    marcar = addon.promob.marcar_dependentes
    ajustar = addon.promob.ajustar_encaixes
    try:
        addon.promob.planejar = planejar
        addon.promob.aplicar = lambda *args: dict(portas=0, gavetas=0, correr=0)
        addon.promob.marcar_dependentes = lambda *args: None
        addon.promob.ajustar_encaixes = lambda *args: []
        limpar()
        addon.importacao.importar_dxf_promob(bpy.context, caminho)
    finally:
        addon.promob.planejar = original
        addon.promob.aplicar = aplicar
        addon.promob.marcar_dependentes = marcar
        addon.promob.ajustar_encaixes = ajustar
        limpar()
    return planos, addon.importacao.ler_dxf_promob(caminho)


def nome_fonte(obj):
    return re.sub(r'\.\d{3}$', '', obj.name)


def deslocamento(conj, plano):
    candidatos = []
    for obj in addon.modulos._chapas_do_conjunto(conj):
        p = plano['pecas'].get(nome_fonte(obj))
        if (not p or addon.chapas.eh_dependente(obj)
                or abs(p.get('normal', (0, 0, 1))[2]) > .1):
            continue
        lo, hi = addon.importacao._caixa_mundo_mm(obj)
        candidatos.append(Vector(tuple((p['lo'][k] + p['hi'][k] - lo[k] - hi[k]) / 2
                                       for k in range(3))))
    if not candidatos:
        raise ValueError('Sem lateral original para identificar o deslocamento de ' + conj.name)
    offset = Vector(tuple(statistics.median(v[k] for v in candidatos) for k in range(3)))
    if not any((v - offset).length < .1 for v in candidatos):
        raise ValueError('A geometria do DXF nao corresponde ao preset ' + conj.name)
    return offset


def corrigir(conj, plano, geometria):
    antigas = [g for g in addon.portas._portas_do_conjunto(conj)
               if g['porta_parametros']['abertura'] != 'CORRER']
    if not antigas and not plano['portas']:
        return None
    offset = deslocamento(conj, plano)
    frentes = {f['origem'] for p in plano['portas'] for f in p['folhas']}
    chapas = {nome_fonte(o): o for o in addon.modulos._chapas_do_conjunto(conj)}
    remover = set(plano['remover'])
    restaurar, puxadores, materiais, materiais_restaurados = set(), [], [], {}
    for nome in frentes & chapas.keys():
        obj = chapas[nome]
        materiais.append((obj.matrix_world.translation.copy(),
                          [(s.link, s.material) for s in obj.material_slots]))
    for grupo in antigas:
        for folha in addon.portas._folhas_portas(grupo):
            fechada = addon.ferragens._matriz_fechada(folha)
            centro = fechada.translation * 1000 + offset
            ns = fechada.to_3x3().col[2].normalized()
            # Associar a folha antiga a' chapa fonte; uma falsa porta
            # volta a ser chapa. Caixas de gaveta continuam nativas.
            candidatas = []
            for nome, p in plano['pecas'].items():
                if abs(Vector(p.get('normal', (0, 0, 1))).dot(ns)) > .995:
                    c = Vector(tuple((p['lo'][k] + p['hi'][k]) / 2 for k in range(3)))
                    candidatas.append(((c - centro).length, nome))
            if candidatas:
                distancia, fonte = min(candidatas)
                if distancia < 35 and fonte not in chapas and fonte not in remover:
                    restaurar.add(fonte)
                    materiais_restaurados[fonte] = [(s.link, s.material) for s in folha.material_slots]
            materiais.append((fechada.translation.copy(), [(s.link, s.material) for s in folha.material_slots]))
        for o in grupo.children_recursive:
            if addon.chapas.MARCA_PUXADOR in o:
                mundo = o.matrix_world.copy()
                o.parent = None
                o.matrix_world = mundo
                puxadores.append(o)
        # Copiar nomes antes: remover uma raiz do rig libera descendentes.
        nomes = [o.name for o in grupo.children_recursive] + [grupo.name]
        for nome in reversed(nomes):
            obj = bpy.data.objects.get(nome)
            if obj is not None and obj not in puxadores:
                addon.ferragens._remover_ferragem(obj)
    for nome in frentes:
        if nome in chapas:
            addon.importacao._remover_objeto(chapas[nome])
    for nome in restaurar:
        camada = nome.removeprefix('Peca ')
        vs, fs = geometria[camada]
        obj = addon.importacao._objeto_da_peca(bpy.context, nome,
            [tuple(Vector(v) - offset) for v in vs], fs, conj.users_collection[0])
        addon.importacao.converter_em_chapa(obj)
        for link, material in materiais_restaurados.get(nome, []):
            obj.data.materials.append(material)
            obj.material_slots[-1].link = link
            obj.material_slots[-1].material = material
        mundo = obj.matrix_world.copy()
        obj.parent = conj
        obj.matrix_parent_inverse = conj.matrix_world.inverted()
        obj.matrix_world = mundo
    bpy.context.view_layer.update()
    addon.modulos.sincronizar_medidas_conjunto(conj)
    portas = []
    for p in plano['portas']:
        q = dict(p)
        ref = Matrix(p['referencia'])
        delta = ref.transposed() @ offset
        q['referencia'] = ref
        q['plano'] -= delta.y
        q['vao'] = [v - d for v, d in zip(p['vao'], (delta.x, delta.x, delta.z, delta.z))]
        q['folhas'] = [dict(f, lo=[v - delta[k] for k, v in enumerate(f['lo'])],
                           hi=[v - delta[k] for k, v in enumerate(f['hi'])]) for f in p['folhas']]
        q['centros'] = [[Vector(c) - delta for c in cs] for cs in p['centros']]
        portas.append(q)
    addon.promob.aplicar(bpy.context, conj, dict(portas=portas, gavetas=[], correr=[]))
    novas = [f for g in addon.portas._portas_do_conjunto(conj) for f in addon.portas._folhas_portas(g)]
    for f in novas:
        if materiais:
            _, mats = min(materiais, key=lambda par: (par[0] - f.matrix_world.translation).length)
            f.data.materials.clear()
            for link, mat in mats:
                f.data.materials.append(mat)
                f.material_slots[-1].link = link
                f.material_slots[-1].material = mat
    for pux in puxadores:
        alvo = min(novas + addon.modulos._chapas_do_conjunto(conj),
                   key=lambda f: (f.matrix_world.translation - pux.matrix_world.translation).length)
        addon.portas._ligar_puxador(pux, alvo)
    addon.chapas.detectar_adjacencia(addon.modulos._chapas_do_conjunto(conj))
    addon.modulos.sincronizar_medidas_conjunto(conj)
    addon.ferragens.ocultar_pecas_do_rig()
    return dict(portas_antes=len(antigas), portas_depois=len(portas),
                folhas=sum(len(p['folhas']) for p in portas), restauradas=sorted(restaurar),
                frentes_convertidas=sorted(frentes & chapas.keys()))


def preparar(biblioteca, fontes, destino):
    validar_destino(biblioteca, destino)
    originais, novos = [os.path.join(destino, p) for p in ('originais', 'novos')]
    os.makedirs(originais, exist_ok=False)
    os.makedirs(novos, exist_ok=False)
    addon.opcoes._pasta_addon = lambda: novos
    addon.biblioteca.pasta_biblioteca = lambda: novos
    addon.register()
    indice = json.load(open(os.path.join(biblioteca, 'indice.json'), encoding='utf-8'))
    fontes_por_categoria = {}
    for pasta, _, arquivos in os.walk(fontes):
        for nome in arquivos:
            if nome.lower().endswith('.dxf'):
                caminho = os.path.join(pasta, nome)
                ambiente = os.path.relpath(pasta, fontes).split(os.sep)[0]
                aba, categoria, _ = addon.importacao.categoria_promob(caminho)
                fontes_por_categoria[(ambiente, aba, categoria)] = caminho
    manifesto = dict(biblioteca=biblioteca, versao=addon.bl_info['version'],
                     modulos=[], arquivos=[], fontes={}, verificados=0, sem_fonte=[], publicado=False)
    for categoria, caminho in sorted(fontes_por_categoria.items()):
        itens = [it for it in indice if tuple(addon.biblioteca.caminho_de(it)[1:]) == categoria
                 and it.get('tipo') == 'modulo']
        if not itens:
            continue
        hash_fonte = digital(caminho)
        manifesto['fontes'][caminho] = hash_fonte
        planos, geometria = capturar(caminho)
        for it in itens:
            numero = re.search(r' (\d+) \d+x\d+x\d+$', it['nome'])
            if not numero or int(numero[1]) > len(planos):
                raise ValueError('Sem correspondencia de modulo: ' + it['nome'])
            plano = planos[int(numero[1]) - 1]
            manifesto['verificados'] += 1
            nomes = [it['arquivo'], os.path.splitext(it['arquivo'])[0] + '.png']
            hashes = {n: digital(caminho_da_peca(biblioteca, n)) for n in nomes}
            cols, objs = carregar(caminho_da_peca(biblioteca, nomes[0]))
            assets = {c.name: c.asset_data.catalog_id for c in cols if c.asset_data}
            conj, = [o for o in objs if addon.chapas.MARCA_CONJUNTO in o]
            antes = estado(cols, objs)
            ajuste = corrigir(conj, plano, geometria)
            if ajuste is None:
                continue
            # Toda peca que permaneceu estrutural conserva geometria, UID
            # e os encaixes corrigidos na v230. So' portas sao reconstruidas.
            depois = estado(list(bpy.data.collections), list(bpy.data.objects))
            for obj in addon.modulos._chapas_do_conjunto(conj):
                if obj.name in antes['objetos']:
                    a, b = dict(antes['objetos'][obj.name]), dict(depois['objetos'][obj.name])
                    for d in (a, b):
                        d['props'] = {k: v for k, v in d['props'].items() if k != 'chapa_vizinhos'}
                    conferir(a, b, obj.name)
            if assets != depois['assets']:
                raise AssertionError('Catalogos mudaram: ' + it['arquivo'])
            for nome in nomes:
                shutil.copy2(caminho_da_peca(biblioteca, nome), os.path.join(originais, nome))
            blend = os.path.join(novos, nomes[0])
            bpy.data.libraries.write(blend, set(bpy.data.collections) | set(bpy.data.objects), fake_user=True)
            esperado = estado(list(bpy.data.collections), list(bpy.data.objects))
            addon.biblioteca.preparar_abertura_foto(bpy.context, conj)
            png = os.path.join(novos, nomes[1])
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
                    raise RuntimeError('Preset editado durante o preparo: ' + nome)
                manifesto['arquivos'].append(dict(nome=nome, original=hashes[nome],
                                                     novo=digital(os.path.join(novos, nome))))
            manifesto['modulos'].append(dict(arquivo=it['arquivo'], fonte=caminho, ajuste=ajuste))
            print('[portas] %d: %s %s' % (len(manifesto['modulos']), it['arquivo'], ajuste), flush=True)
        if digital(caminho) != hash_fonte:
            raise RuntimeError('DXF editado durante o preparo: ' + caminho)
    manifesto['sem_fonte'] = [it['arquivo'] for it in indice if it.get('tipo') == 'modulo'
        and len(addon.biblioteca.caminho_de(it)) >= 4
        and tuple(addon.biblioteca.caminho_de(it)[1:]) not in fontes_por_categoria]
    limpar()
    addon.unregister()
    json.dump(manifesto, open(os.path.join(destino, 'manifesto.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destino', required=True)
    parser.add_argument('--fontes', default=os.path.expanduser('~/Documents/Promob'))
    parser.add_argument('--biblioteca', default=os.path.join(os.path.dirname(__file__), 'cabinet_creator', 'biblioteca'))
    parser.add_argument('--aplicar', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    validar_destino(args.biblioteca, args.destino)
    if args.aplicar:
        manifesto = json.load(open(os.path.join(args.destino, 'manifesto.json'), encoding='utf-8'))
        for fonte, esperado in manifesto.get('fontes', {}).items():
            if digital(fonte) != esperado:
                raise RuntimeError('DXF mudou desde o preparo: ' + fonte)
        publicar(args.destino)
    else:
        preparar(args.biblioteca, args.fontes, args.destino)


if __name__ == '__main__':
    main()
