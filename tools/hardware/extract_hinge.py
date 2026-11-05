"""Extract the user hinge model and rig into compatible hardware assets.

Run with the source scene in background Blender 4.2, the oldest supported
asset format. Writes dobradica_reta.blend/.json, including measured motion,
then executes extract_hinge_wireframe.py. Generate the standard screw and
run replace_hinge_screws.py after extracting a new hinge. Stored names stay stable."""
from pathlib import Path
import json
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

AQUI = str(Path(__file__).resolve().parents[2])
DESTINO = os.path.join(AQUI, 'archy_builder', "assets/hardware")

RAIZ, PORTA, CONTROLE = 'Hinge Empty', 'Door Left', 'door controller'
LATERAL = 'Left table'                          # Panel to which the mounting plate attaches.
CORTADOR, CABECA = 'Boolean Hinge Botton', 'Left Hinge Head'
PAPEIS = {RAIZ: 'raiz', 'Left Hinge base': 'base',
          'Left Hinge suport': 'suporte', CABECA: 'cabeca',
          CORTADOR: 'furo', CONTROLE: 'controle', 'Armature': 'armacao',
          'Armature.001': 'armacao_ik'}
# The user's door and its attached components are excluded.
FORA = {PORTA, 'Aluminum handle Left', 'Boolean Hinge Botton.001'}
LIXO = ('hops', 'kitops', 'scatter5', 'HG')    # Properties from other add-ons.
CONTROLE_MIN, CONTROLE_MAX = 0.5, 90.0          # Degrees (Limit Rotation).
FOLGA_COPO_MM = 0.2          # On each side of the cup, at the hole.
# Asset version: replace copies of older versions (English names, old hole)
# when rebuilding the door. Increment when the asset changes.
VERSAO = 2
NOMES_PT = {RAIZ: "Hinge", 'Left Hinge base': 'Dobradica Base',
            'Left Hinge suport': 'Dobradica Suporte', CABECA: 'Dobradica Copo',
            CORTADOR: 'Dobradica Furo do Copo', CONTROLE: 'Dobradica Controle',
            'Armature': 'Dobradica Armacao',
            'Armature.001': 'Dobradica Armacao IK',
            'Left Hinge.Arm.001': 'Dobradica Braco 1',
            'Left Hinge.Arm': 'Dobradica Braco 2',
            'Left Hinge spring': 'Dobradica Mola'}
NOMES_MODIFICADORES = {'MIRROR': "Mirror", 'SUBSURF': "Subdivision",
                       'NODES': "Smooth by Angle"}
NOMES_RESTRICOES = {'LIMIT_ROTATION': "Limit Rotation", 'IK': 'IK'}
NOMES_OSSOS = {'Bone': 'Osso 1', 'Bone.001': 'Osso 2', 'Bone.002': 'Osso 3'}
NOMES_MATERIAIS = {'Steel Rough #1.009': "Matte Steel"}
ABA_COPO_MM = 1.0            # Anything penetrating less than this is flange, not cup.

objs = bpy.data.objects
raiz, porta = objs[RAIZ], objs[PORTA]
bpy.context.view_layer.update()

# Measurements taken BEFORE changes, with the door closed.
inv = raiz.matrix_world.inverted()
cantos = [inv @ (porta.matrix_world @ Vector(c)) for c in porta.bound_box]
costas_mm = min(v.y for v in cantos) * 1000.0      # +Y = front.
espessura_mm = (max(v.y for v in cantos) - min(v.y for v in cantos)) * 1000.0
borda_mm = max(v.x for v in cantos) * 1000.0       # Leaf extends beyond the face.
# Gap the user left between the door back and cabinet front: the rig
# was built with it; without it, the open door's corner penetrates.
frente_mm = max((inv @ (objs[LATERAL].matrix_world @ Vector(c))).y
                for c in objs[LATERAL].bound_box) * 1000.0
folga_mm = costas_mm - frente_mm


def refazer_cortador():
    """Hole based on the ACTUAL CUP: the modified head portion penetrating
    more than ABA_COPO_MM into the closed door. Round cylinder centered
    there, slightly wider and deeper, extending 1 mm beyond the back
    to avoid a coplanar Boolean face."""
    cabeca, cortador = objs[CABECA], objs[CORTADOR]
    grafo = bpy.context.evaluated_depsgraph_get()
    avaliada = cabeca.evaluated_get(grafo)
    malha = avaliada.to_mesh()
    da_porta = porta.matrix_world.inverted()
    pontos = [da_porta @ (cabeca.matrix_world @ v.co) for v in malha.vertices]
    avaliada.to_mesh_clear()
    costas = min(Vector(c).y for c in porta.bound_box)     # Local -Y.
    copo = [p for p in pontos if p.y > costas + ABA_COPO_MM / 1000.0]
    xs, zs = [p.x for p in copo], [p.z for p in copo]
    cx, cz = (max(xs) + min(xs)) / 2.0, (max(zs) + min(zs)) / 2.0
    raio = (max(math.hypot(p.x - cx, p.z - cz) for p in copo)
            + FOLGA_COPO_MM / 1000.0)
    fundo = max(p.y for p in copo) - costas + 0.5 / 1000.0
    y0, y1 = costas - 1.0 / 1000.0, costas + fundo
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=64,
                          radius1=raio, radius2=raio, depth=y1 - y0)
    # Z cylinder -> door Y axis (the hole enters through the back).
    bmesh.ops.rotate(bm, cent=(0, 0, 0), verts=bm.verts,
                     matrix=Matrix.Rotation(-math.pi / 2, 3, 'X'))
    novo = bpy.data.meshes.new('Copo Furo')
    bm.to_mesh(novo)
    bm.free()
    antigo = cortador.data
    cortador.data = novo
    if antigo.users == 0:
        bpy.data.meshes.remove(antigo)
    rotacao = porta.matrix_world.to_quaternion().to_matrix().to_4x4()
    cortador.matrix_world = (Matrix.Translation(
        porta.matrix_world @ Vector((cx, (y0 + y1) / 2.0, cz))) @ rotacao)
    return raio * 2000.0, fundo * 1000.0


diametro_copo, fundo_copo = refazer_cortador()

guardar = [o for o in [raiz, *raiz.children_recursive] if o.name not in FORA]
guardar += [o for o in (objs[CORTADOR], objs[CONTROLE]) if o not in guardar]
for o in (objs[CORTADOR], objs[CONTROLE]):
    mundo = o.matrix_world.copy()
    o.parent = objs[CABECA] if o.name == CORTADOR else raiz
    o.matrix_world = mundo
mundo_raiz = raiz.matrix_world.copy()
raiz.parent = None
raiz.matrix_world = Matrix.Identity(4)
objs[CONTROLE].animation_data_clear()           # The action locked rotation.
manter = {o.name for o in guardar}
for o in list(objs):
    if o.name not in manter:
        objs.remove(o, do_unlink=True)

colecao = bpy.data.collections.new('Cabinet Dobradica Reta')
bpy.context.scene.collection.children.link(colecao)
for o in guardar:
    for c in list(o.users_collection):
        c.objects.unlink(o)
    colecao.objects.link(o)
    o['cabinet_peca'] = PAPEIS.get(o.name, 'peca')
    for chave in LIXO:
        if chave in o:
            del o[chave]
for c in list(bpy.data.collections):
    if c != colecao:
        bpy.data.collections.remove(c)
# Only component materials: door, handle, and world HDRI materials
# were being packed too, adding megabytes of textures.
usados = {s.material for o in guardar for s in o.material_slots if s.material}
for cena in bpy.data.scenes:
    cena.world = None
for mundo_ in list(bpy.data.worlds):
    bpy.data.worlds.remove(mundo_)
for material in list(bpy.data.materials):
    if material not in usados:
        bpy.data.materials.remove(material)
bpy.data.orphans_purge(do_recursive=True)
for imagem in list(bpy.data.images):
    if imagem.users == 0 or imagem.name == 'Render Result':
        bpy.data.images.remove(imagem)
for colecao_dados in (bpy.data.meshes, bpy.data.curves, bpy.data.armatures,
                      bpy.data.materials, bpy.data.node_groups,
                      bpy.data.images):
    for idb in colecao_dados:
        idb['cabinet_origem'] = idb.name     # The add-on uses this for deduplication.
        for chave in LIXO:
            if chave in idb:
                del idb[chave]

# Motion: head (and its attached door) for each controller angle,
# in the root frame. Planar: Z rotation + XY translation.
vl = bpy.context.view_layer
controle, cabeca = objs[CONTROLE], objs[CABECA]


def cabeca_em(graus):
    controle.rotation_euler.z = -math.radians(graus)
    vl.update()
    return cabeca.matrix_world.copy()


fechada = cabeca_em(CONTROLE_MIN)


def linha(graus):
    rel = cabeca_em(graus) @ fechada.inverted()
    giro = rel.to_euler('XYZ')
    assert abs(giro.x) < 1e-3 and abs(giro.y) < 1e-3, giro   # Z only.
    t = rel.translation * 1000.0
    return [round(graus, 6), round(math.degrees(giro.z), 6),
            round(t.x, 6), round(t.y, 6)]


# Controller steps of 0.5 degrees, subdivided where leaf rotation exceeds
# 0.1 degrees between samples: near the travel end, IK stretches and the
# leaf jumps about 2 degrees per 0.05 controller degrees in the user's rig.
tabela = []
passos = 179
anterior = linha(CONTROLE_MIN)
tabela.append(anterior)
for i in range(1, passos + 1):
    atual = linha(CONTROLE_MIN + (CONTROLE_MAX - CONTROLE_MIN) * i / passos)
    pilha = [(anterior, atual)]
    novas = []
    while pilha:
        a, b = pilha.pop()
        if abs(b[1] - a[1]) > 0.1 and b[0] - a[0] > 1e-4:
            meio = linha((a[0] + b[0]) / 2.0)
            pilha += [(meio, b), (a, meio)]
        else:
            novas.append(b)
    tabela += novas
    anterior = atual
# Only up to MAXIMUM opening: afterward IK settles back slightly,
# and the table must be monotonic to recover the controller value.
fim = max(range(len(tabela)), key=lambda i: abs(tabela[i][1]))
tabela = tabela[:fim + 1]
assert all(abs(b[1]) >= abs(a[1]) for a, b in zip(tabela, tabela[1:]))
cabeca_em(CONTROLE_MIN)


def nome_pt(nome):
    """Portuguese name, as requested by the user, from the source filename;
    repeated pins and screws receive Blender's .001 suffix."""
    if nome in NOMES_PT:
        return NOMES_PT[nome]
    if nome.startswith('Screw'):
        return 'Dobradica Parafuso'
    if nome == 'Left Hinge' or nome.startswith('Left Hinge.0'):
        return 'Dobradica Pino'
    return 'Dobradica Peca'


# All names are Portuguese. Names are not keys: the add-on finds each component
# by `cabinet_peca`; drivers and IK reference objects, and renaming a bone
# through Blender updates the IK target.
for o in sorted(guardar, key=lambda o: o.name):
    novo = nome_pt(o.name)
    o.name = novo
    if o.data is not None and o.type in ('MESH', 'CURVE', 'ARMATURE'):
        o.data.name = novo
    for m in o.modifiers:
        m.name = NOMES_MODIFICADORES.get(m.type, m.name)
    for c in o.constraints:
        c.name = NOMES_RESTRICOES.get(c.type, c.name)
    if o.type == 'ARMATURE':
        for osso in sorted(o.data.bones, key=lambda b: b.name):
            osso.name = NOMES_OSSOS.get(osso.name, osso.name)
        for osso in o.pose.bones:
            for c in osso.constraints:
                c.name = NOMES_RESTRICOES.get(c.type, c.name)
for material in bpy.data.materials:
    material.name = NOMES_MATERIAIS.get(material.name, material.name)
colecao.name = 'Dobradica Reta'
raiz['cabinet_versao'] = VERSAO
for colecao_dados in (bpy.data.meshes, bpy.data.curves, bpy.data.armatures,
                      bpy.data.materials, bpy.data.node_groups):
    for idb in colecao_dados:
        idb['cabinet_origem'] = idb.name
bpy.context.view_layer.update()

os.makedirs(DESTINO, exist_ok=True)
with open(os.path.join(DESTINO, 'dobradica_reta.json'), 'w',
          encoding='utf-8') as f:
    json.dump({'origem': os.path.basename(bpy.data.filepath),
               'versao_blender': bpy.app.version_string,
               'versao': VERSAO,
               'costas_mm': round(costas_mm, 4),
               'espessura_porta_mm': round(espessura_mm, 4),
               'borda_porta_mm': round(borda_mm, 4),
               'folga_modulo_mm': round(folga_mm, 4),
               'controle_graus': [CONTROLE_MIN, CONTROLE_MAX],
               'tabela': tabela}, f, indent=1)
bpy.ops.wm.save_as_mainfile(
    filepath=os.path.join(DESTINO, 'dobradica_reta.blend'),
    compress=True, copy=True)
print("[extract] back %.2f mm, door %.2f mm, edge %.2f mm, gap %.2f mm, cup hole %.2f x %.2f mm, %d objects, maximum rotation %.2f degrees"
      % (costas_mm, espessura_mm, borda_mm, folga_mm, diametro_copo,
         fundo_copo, len(guardar), tabela[-1][1]))
# Preview wireframe (each component's outline) goes into the same .json.
with open(str(Path(__file__).with_name('extract_hinge_wireframe.py')),
          encoding='utf-8') as f:
    exec(compile(f.read(), 'tools/hardware/extract_hinge_wireframe.py', 'exec'))
