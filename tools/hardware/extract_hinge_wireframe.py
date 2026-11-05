"""Extract hinge wireframe geometry into the existing hardware JSON.

Run with the hinge asset open in a disposable background Blender process.
Preserves mesh provenance keys, object-space segments and closed hinge poses.
Also executed by extract_hinge.py and replace_hinge_screws.py."""
from pathlib import Path
import json
import math
import os

import bmesh
import bpy

AQUI = str(Path(__file__).resolve().parents[2])
JSON = os.path.join(AQUI, 'archy_builder', "assets/hardware", 'dobradica_reta.json')
ANGULO_VINCO = 30.0          # Angle in degrees between faces required to display an edge.
FORA = ('furo', 'controle')  # Cutter and controller: not the component.
ATRIBUTO_SEM_ARAME = 'cabinet_sem_arame'    # `arame.ATRIBUTO_SEM_ARAME`


def arame():
    raiz = next(o for o in bpy.data.objects if o.get('cabinet_peca') == 'raiz')
    controle = next(o for o in bpy.data.objects
                    if o.get('cabinet_peca') == 'controle')
    controle.rotation_euler.z = -math.radians(0.5)       # Door closed.
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
                # Standard screw: head only; the thread is inside the wood.
                fora = bm.edges.layers.int.get(ATRIBUTO_SEM_ARAME)
                for e in bm.edges:
                    if fora is not None and e[fora]:
                        continue
                    if (len(e.link_faces) != 2 or e.calc_face_angle(0.0)
                            > math.radians(ANGULO_VINCO)):
                        for v in e.verts:
                            pontos += [round(c * 1000.0, 3) for c in v.co]
                bm.free()
                malhas[chave] = pontos
            pose = raiz.matrix_world.inverted() @ o.matrix_world
            parte = o
            while parte is not None and parte.get('cabinet_peca') not in ('base', 'suporte'):
                parte = parte.parent
            pecas.append({'calco': parte.get('cabinet_peca') if parte else '',
                          'malha': chave, 'pose': [
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
    # Compact: indentation put each wireframe number on its own line, adding megabytes.
    json.dump(dados_json, f, separators=(',', ':'))
print("[wireframe] %d components, %d meshes, %d segments" % (
    len(dados_arame['pecas']), len(dados_arame['malhas']),
    sum(len(v) // 6 for v in dados_arame['malhas'].values())))
