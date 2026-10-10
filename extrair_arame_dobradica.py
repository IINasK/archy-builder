"""Grava no JSON do asset o ARAME da dobradica reta (previa do add-on).

    blender --background --factory-startup \\
        cabinet_creator/ferragens/dobradica_reta.blend \\
        --python extrair_arame_dobradica.py

(`extrair_dobradica.py` ja' roda isto no fim.) A previa das dobradicas e'
o wireframe da PECA de verdade (pedido do usuario), nao uma caixa. A malha
avaliada tem ~190 mil arestas por dobradica (subdivisao): ilegivel e
pesada. Daqui sai so' o CONTORNO -- bordas e vincos acima de
`ANGULO_VINCO` -- da malha espelhada SEM a subdivisao, em mm:
  'malhas': {nome da malha (cabinet_origem): [x1,y1,z1,x2,y2,z2, ...]}
            no espaco do OBJETO (a selecao usa o matrix_world da copia);
  'pecas':  [{'malha', 'pose'}] com a pose (4x4, mm) de cada peca na
            RAIZ com a porta fechada (o wizard, sem objeto ainda).
"""
import json
import math
import os

import bmesh
import bpy

AQUI = os.path.dirname(os.path.abspath(__file__))
JSON = os.path.join(AQUI, 'cabinet_creator', 'ferragens', 'dobradica_reta.json')
ANGULO_VINCO = 30.0          # graus entre as faces para a aresta aparecer
FORA = ('furo', 'controle')  # cortador e controlador: nao sao a peca


def arame():
    raiz = next(o for o in bpy.data.objects if o.get('cabinet_peca') == 'raiz')
    controle = next(o for o in bpy.data.objects
                    if o.get('cabinet_peca') == 'controle')
    controle.rotation_euler.z = -math.radians(0.5)       # porta fechada
    malhas, pecas = {}, []
    for o in sorted(bpy.data.objects, key=lambda o: o.name):
        if o.type != 'MESH' or o.get('cabinet_peca') in FORA:
            continue
        chave = o.data.get('cabinet_origem', o.data.name)
        desligados = [m for m in o.modifiers
                      if m.type in {'SUBSURF', 'NODES'} and m.show_viewport]
        for m in desligados:
            m.show_viewport = False
        bpy.context.view_layer.update()
        try:
            avaliado = o.evaluated_get(bpy.context.evaluated_depsgraph_get())
            if chave not in malhas:
                bm = bmesh.new()
                bm.from_mesh(avaliado.to_mesh())
                avaliado.to_mesh_clear()
                pontos = []
                for e in bm.edges:
                    if (len(e.link_faces) != 2 or e.calc_face_angle(0.0)
                            > math.radians(ANGULO_VINCO)):
                        for v in e.verts:
                            pontos += [round(c * 1000.0, 3) for c in v.co]
                bm.free()
                malhas[chave] = pontos
            pose = raiz.matrix_world.inverted() @ o.matrix_world
            pecas.append({'malha': chave, 'pose': [
                round(pose[i][j] * (1000.0 if j == 3 and i < 3 else 1.0), 4)
                for i in range(4) for j in range(4)]})
        finally:
            for m in desligados:
                m.show_viewport = True
    bpy.context.view_layer.update()
    return {'angulo': ANGULO_VINCO, 'malhas': malhas, 'pecas': pecas}


dados_arame = arame()
with open(JSON, encoding='utf-8') as f:
    dados_json = json.load(f)
dados_json['arame'] = dados_arame
with open(JSON, 'w', encoding='utf-8') as f:
    # compacto: com indent cada numero do arame ia numa linha (MBs)
    json.dump(dados_json, f, separators=(',', ':'))
print('[arame] %d pecas, %d malhas, %d segmentos' % (
    len(dados_arame['pecas']), len(dados_arame['malhas']),
    sum(len(v) // 6 for v in dados_arame['malhas'].values())))
