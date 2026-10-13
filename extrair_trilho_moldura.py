"""Extrai os PERFIS dos trilhos da porta de correr com moldura (modelo do
usuario: colecao "Moldura porta guardaroupa") para o add-on.

    blender --background --factory-startup "<arquivo do usuario>.blend" \
        --python extrair_trilho_moldura.py

Gera cabinet_creator/ferragens/trilho_moldura.json com a SECAO de cada
trilho, em mm: u = profundidade a partir das COSTAS do trilho (para a
frente), v = altura a partir da BASE. O modelo e' montado de varias
pecas de aluminio sobrepostas (ilhas), entao a secao nao e' um contorno
so': sao os POLIGONOS da ponta (uma face por pedaco), cada um extrudado
na largura do vao pelo add-on. O trilho e' um prisma: esticar no
comprimento nao deforma nada (o Bevel do modelo fica de fora: ele so'
arredonda as quinas). No modelo o comprimento corre em Y do mundo e a
frente e' +X.
"""
import json
import os

import bmesh
import bpy

AQUI = os.path.dirname(os.path.abspath(__file__))
DESTINO = os.path.join(AQUI, 'cabinet_creator', 'ferragens',
                       'trilho_moldura.json')
TRILHOS = {'CIMA': 'Trilho superior', 'BAIXO': 'Trilho inferior'}
TOL = 1e-4          # m


def _poligonos_da_ponta(obj):
    """Faces da ponta de menor Y, em mundo (m), cada uma em ordem."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    try:
        y0 = min(v.co.y for v in bm.verts)
        return [[v.co.copy() for v in f.verts] for f in bm.faces
                if all(abs(v.co.y - y0) < TOL for v in f.verts)]
    finally:
        bm.free()


def main():
    saida = {'origem': os.path.basename(bpy.data.filepath) or 'autosave',
             'versao_blender': bpy.app.version_string, 'trilhos': {}}
    for chave, nome in TRILHOS.items():
        faces = _poligonos_da_ponta(bpy.data.objects[nome])
        pontos = [p for f in faces for p in f]
        x0 = min(p.x for p in pontos)
        z0 = min(p.z for p in pontos)
        poligonos = [[(round((p.x - x0) * 1000.0, 3), round((p.z - z0) * 1000.0, 3))
                      for p in f] for f in faces]
        dados = {'malha': nome,
                 'profundidade_mm': max(u for f in poligonos for u, _v in f),
                 'altura_mm': max(v for f in poligonos for _u, v in f),
                 'poligonos': poligonos}
        saida['trilhos'][chave] = dados
        print('TRILHO', chave, len(poligonos), 'poligonos',
              dados['profundidade_mm'], dados['altura_mm'])
    with open(DESTINO, 'w', encoding='utf-8') as arq:
        json.dump(saida, arq, indent=1)
    print('Gravado', DESTINO)


main()
