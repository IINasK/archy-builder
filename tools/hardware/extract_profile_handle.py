"""Extract the profile handle mesh, materials, textures and dimensions.

Run with the user source scene in background Blender 4.2. Writes the existing
puxador_perfil.blend/.json resource names in archy_builder/ferragens.
Coordinates follow the handle edge: X along the edge, Y into the leaf, Z outward."""
from pathlib import Path
import json
import os

import bmesh
import bpy
from mathutils import Vector

AQUI = str(Path(__file__).resolve().parents[2])
DESTINO = os.path.join(AQUI, 'archy_builder', 'ferragens')
PORTA, PUXADOR = 'Door Left', 'Aluminum handle Left'
NOME = 'Puxador Perfil'
NOME_MATERIAL = 'Aluminio Escovado'
NOMES_IMAGENS = {'BaseColor': 'Cor', 'Metalness': 'Metal',
                 'Roughness': 'Aspereza', 'Normal': 'Relevo'}
LIXO = ('hops', 'kitops', 'scatter5', 'HG')

objs = bpy.data.objects
porta, puxador = objs[PORTA], objs[PUXADOR]
bpy.context.view_layer.update()
grafo = bpy.context.evaluated_depsgraph_get()
malha = bpy.data.meshes.new_from_object(puxador.evaluated_get(grafo))

# referencial da porta (local): x = largura, y = espessura (+y = frente),
# z = altura; o perfil fica na borda de BAIXO
da_porta = porta.matrix_world.inverted() @ puxador.matrix_world
cantos = [Vector(c) for c in porta.bound_box]
frente = max(v.y for v in cantos)
costas = min(v.y for v in cantos)
base_porta = min(v.z for v in cantos)
pontos = [da_porta @ v.co for v in malha.vertices]
x0, x1 = min(p.x for p in pontos), max(p.x for p in pontos)
borda = min(p.z for p in pontos)             # borda NOMINAL da folha
meio = (x0 + x1) / 2.0

bm = bmesh.new()
bm.from_mesh(malha)
for v, p in zip(bm.verts, pontos):
    # (-x, z, y): rotacao propria (o X invertido nao espelha a malha)
    v.co = Vector((-(p.x - meio), p.z - borda, p.y - frente))
bm.to_mesh(malha)
bm.free()
malha.name = NOME

for o in list(objs):
    objs.remove(o, do_unlink=True)
for c in list(bpy.data.collections):
    bpy.data.collections.remove(c)
objeto = bpy.data.objects.new(NOME, malha)
bpy.context.scene.collection.objects.link(objeto)
for cena in bpy.data.scenes:
    cena.world = None
for mundo in list(bpy.data.worlds):
    bpy.data.worlds.remove(mundo)
usados = set(m for m in malha.materials if m)
for material in list(bpy.data.materials):
    if material not in usados:
        bpy.data.materials.remove(material)
bpy.data.orphans_purge(do_recursive=True)
for imagem in list(bpy.data.images):
    if imagem.users == 0 or imagem.name == 'Render Result':
        bpy.data.images.remove(imagem)

for material in usados:
    material.name = NOME_MATERIAL
for imagem in bpy.data.images:
    for chave, nome in NOMES_IMAGENS.items():
        if chave in imagem.name:
            imagem.name = '%s %s' % (NOME_MATERIAL, nome)
    if imagem.packed_file is None:
        imagem.pack()
for colecao_dados in (bpy.data.meshes, bpy.data.materials, bpy.data.images,
                      bpy.data.node_groups):
    for idb in colecao_dados:
        idb['cabinet_origem'] = idb.name     # o add-on deduplica por isto
        for chave in LIXO:
            if chave in idb:
                del idb[chave]

dados = {'origem': os.path.basename(bpy.data.filepath),
         'versao_blender': bpy.app.version_string,
         'malha': NOME,
         'altura_mm': round((base_porta - borda) * 1000.0, 4),
         'espessura_porta_mm': round((frente - costas) * 1000.0, 4),
         'comprimento_mm': round((x1 - x0) * 1000.0, 4)}
os.makedirs(DESTINO, exist_ok=True)
with open(os.path.join(DESTINO, 'puxador_perfil.json'), 'w',
          encoding='utf-8') as f:
    json.dump(dados, f, indent=1)
bpy.ops.wm.save_as_mainfile(
    filepath=os.path.join(DESTINO, 'puxador_perfil.blend'),
    compress=True, copy=True)
print('[extrair] puxador perfil: corta %.2f mm, porta %.2f mm, comprimento'
      ' %.2f mm, %d vertices, material %s, imagens %s' % (
          dados['altura_mm'], dados['espessura_porta_mm'],
          dados['comprimento_mm'], len(malha.vertices),
          [m.name for m in malha.materials],
          [i.name for i in bpy.data.images]))
