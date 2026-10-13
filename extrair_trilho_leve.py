"""Extrai o TRILHO LEVE (porta de correr leve) do modelo do usuario para o
add-on: colecao "Trilho exemplo" -- a chapa com os dois canais fresados
("Base.002") e o perfil em U de embutir ("Trilho inferior.001", um U por
canal, com aba sobre a chapa).

    blender --background --factory-startup "<arquivo do usuario>.blend" \\
        --python extrair_trilho_leve.py

Acrescenta a chave "LEVE" em cabinet_creator/ferragens/trilho_moldura.json
(o pesado, de `extrair_trilho_moldura.py`, fica como esta'). Em mm:
u = profundidade a partir das COSTAS do par de perfis (para a frente),
v = altura a partir da FACE da chapa (negativo = dentro do canal). O U
tem as pontas abertas: a secao sai das arestas da ponta (um contorno por
U), da malha AVALIADA (o comprimento vem de Geometry Nodes). No modelo o
comprimento corre em Y do mundo e a frente da chapa e' -X.
"""
import json
import os

import bmesh
import bpy

AQUI = os.path.dirname(os.path.abspath(__file__))
DESTINO = os.path.join(AQUI, 'cabinet_creator', 'ferragens',
                       'trilho_moldura.json')
CHAPA, PERFIL = 'Base.002', 'Trilho inferior.001'
TOL = 1e-4          # m


def _contornos_da_ponta(obj):
    """Contornos (laços de arestas) da ponta de menor Y, em mundo (m)."""
    grafo = bpy.context.evaluated_depsgraph_get()
    avaliado = obj.evaluated_get(grafo)
    malha = avaliado.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(malha)
    bm.transform(obj.matrix_world)
    try:
        y0 = min(v.co.y for v in bm.verts)
        ponta = {v for v in bm.verts if abs(v.co.y - y0) < TOL}
        vizinhos = {v: [e.other_vert(v) for e in v.link_edges
                        if e.other_vert(v) in ponta] for v in ponta}
        # a caminhada depende de onde comeca (ha' vertices com mais de dois
        # vizinhos na malha avaliada): tenta de TODOS e fica com as mais longas
        laços = []
        for inicio in ponta:
            for primeiro in vizinhos[inicio]:
                laço, vistos = [inicio, primeiro], {inicio, primeiro}
                anterior, atual = inicio, primeiro
                while True:
                    seguinte = next((n for n in vizinhos[atual]
                                     if n is not anterior and n not in vistos), None)
                    if seguinte is None:
                        break
                    laço.append(seguinte)
                    vistos.add(seguinte)
                    anterior, atual = atual, seguinte
                laços.append([v.co.copy() for v in laço])
        return laços
    finally:
        bm.free()
        avaliado.to_mesh_clear()


def _canais_da_chapa(obj, face_z):
    """[(x_min, x_max, fundo_z)] dos canais fresados na face de cima."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    try:
        y0 = min(v.co.y for v in bm.verts)
        faces = [f for f in bm.faces if all(abs(v.co.y - y0) < TOL for v in f.verts)]
        # o canal e' o vao, entre as faces que chegam na face de cima, que
        # tem fundo abaixo dela: as faces "baixas" (topo < face) sob o canal
        baixas = []
        for f in faces:
            zs = [v.co.z for v in f.verts]
            xs = [v.co.x for v in f.verts]
            if max(zs) < face_z - TOL:
                baixas.append((min(xs), max(xs), max(zs)))
        altas = sorted((min(v.co.x for v in f.verts), max(v.co.x for v in f.verts))
                       for f in faces
                       if abs(max(v.co.z for v in f.verts) - face_z) < TOL)
        canais = []
        for (a0, a1), (b0, b1) in zip(altas, altas[1:]):
            if b0 - a1 > TOL:          # vao entre duas faces de cima = canal
                fundo = max(z for x0, x1, z in baixas if x0 <= a1 + TOL and x1 >= b0 - TOL)
                canais.append((a1, b0, fundo))
        return canais
    finally:
        bm.free()


def main():
    chapa = bpy.data.objects[CHAPA]
    face = max((chapa.matrix_world @ v.co).z for v in chapa.data.vertices)
    laços = _contornos_da_ponta(bpy.data.objects[PERFIL])
    costas = max(p.x for l in laços for p in l)       # a frente e' -X
    u = lambda x: round((costas - x) * 1000.0, 3)
    v = lambda z: round((z - face) * 1000.0, 3)
    canais = sorted(_canais_da_chapa(chapa, face), key=lambda c: -c[0])
    centros = [round((u(c[0]) + u(c[1])) / 2.0, 3) for c in canais]
    # os U sao iguais; o modelo tem um deles com vertices soltos (o laço
    # quebra em pedacos): vale o laço inteiro mais longo, posto no meio de
    # CADA canal
    modelo = max(laços, key=len)
    perfil = [(u(p.x), v(p.z)) for p in modelo]
    meio = (min(a for a, _b in perfil) + max(a for a, _b in perfil)) / 2.0
    poligonos = [[(round(a - meio + c, 3), b) for a, b in perfil] for c in centros]
    dados = {
        'origem': os.path.basename(bpy.data.filepath),
        'versao_blender': bpy.app.version_string,
        'malha': PERFIL, 'chapa': CHAPA,
        'profundidade_mm': max(a for p in poligonos for a, _b in p),
        'aba_mm': max(b for p in poligonos for _a, b in p),
        'poligonos': poligonos,
        # centro de cada canal (costas -> frente), largura e fundo
        'canais_mm': centros,
        'canal_largura_mm': round(max(abs(u(c[0]) - u(c[1])) for c in canais), 3),
        'canal_fundo_mm': round(max(-v(c[2]) for c in canais), 3)}
    with open(DESTINO, encoding='utf-8') as arq:
        saida = json.load(arq)
    saida['trilhos']['LEVE'] = dados
    with open(DESTINO, 'w', encoding='utf-8') as arq:
        json.dump(saida, arq, indent=1)
    print('LEVE', len(poligonos), 'perfis', dados['profundidade_mm'], dados['aba_mm'],
          dados['canais_mm'], dados['canal_largura_mm'], dados['canal_fundo_mm'])
    print('Gravado', DESTINO)


main()
