"""Extrai a dobradica reta (modelo + rig do usuario) para o add-on.

    blender --background --factory-startup "<arquivo do usuario>.blend" \\
        --python extrair_dobradica.py

Use o Blender MAIS ANTIGO suportado (4.2): arquivo salvo no 5.x nao abre
no 4.2. Gera, em cabinet_creator/ferragens/:
  dobradica_reta.blend -- UMA dobradica (a da porta esquerda de baixo),
      raiz na origem, sem a porta: malha e rig exatamente os do usuario.
      O cortador do Boolean do copo vira filho da CABECA (que anda junto
      com a porta) e o controlador, filho da raiz. O cortador e' a UNICA
      peca refeita: o do modelo era um octogono de 29 mm, 1,2 mm fora do
      centro, menor que o copo redondo -- sobravam lascas da porta dentro
      do copo (print do usuario). Vira um cilindro medido no proprio copo.
  dobradica_reta.json -- o que o add-on precisa sem abrir o .blend: onde
      fica a costa da porta e a tabela do movimento da cabeca (o que a
      porta faz) para cada angulo do controlador.
Referencial da raiz: -X = para dentro do movel, +Y = frente, Z = eixo.
"""
import json
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

AQUI = os.path.dirname(os.path.abspath(__file__))
DESTINO = os.path.join(AQUI, 'cabinet_creator', 'ferragens')

RAIZ, PORTA, CONTROLE = 'Hinge Empty', 'Door Left', 'door controller'
LATERAL = 'Left table'                          # a chapa onde a base prende
CORTADOR, CABECA = 'Boolean Hinge Botton', 'Left Hinge Head'
PAPEIS = {RAIZ: 'raiz', 'Left Hinge base': 'base',
          'Left Hinge suport': 'suporte', CABECA: 'cabeca',
          CORTADOR: 'furo', CONTROLE: 'controle', 'Armature': 'armacao',
          'Armature.001': 'armacao_ik'}
# a porta do usuario e o que vai nela: ficam de fora
FORA = {PORTA, 'Aluminum handle Left', 'Boolean Hinge Botton.001'}
LIXO = ('hops', 'kitops', 'scatter5', 'HG')    # props de outros add-ons
CONTROLE_MIN, CONTROLE_MAX = 0.5, 90.0          # graus (Limit Rotation)
FOLGA_COPO_MM = 0.2          # de cada lado do copo, no furo
# Versao do asset: copia de versao antiga (nomes em ingles, furo velho) e'
# trocada pela nova quando a porta se refaz. Suba ao mudar o asset.
VERSAO = 2
NOMES_PT = {RAIZ: 'Dobradica', 'Left Hinge base': 'Dobradica Base',
            'Left Hinge suport': 'Dobradica Suporte', CABECA: 'Dobradica Copo',
            CORTADOR: 'Dobradica Furo do Copo', CONTROLE: 'Dobradica Controle',
            'Armature': 'Dobradica Armacao',
            'Armature.001': 'Dobradica Armacao IK',
            'Left Hinge.Arm.001': 'Dobradica Braco 1',
            'Left Hinge.Arm': 'Dobradica Braco 2',
            'Left Hinge spring': 'Dobradica Mola'}
NOMES_MODIFICADORES = {'MIRROR': 'Espelhar', 'SUBSURF': 'Subdivisao',
                       'NODES': 'Suavizar por Angulo'}
NOMES_RESTRICOES = {'LIMIT_ROTATION': 'Limitar Giro', 'IK': 'IK'}
NOMES_OSSOS = {'Bone': 'Osso 1', 'Bone.001': 'Osso 2', 'Bone.002': 'Osso 3'}
NOMES_MATERIAIS = {'Steel Rough #1.009': 'Aco Fosco'}
ABA_COPO_MM = 1.0            # o que entra menos que isto e' aba, nao copo

objs = bpy.data.objects
raiz, porta = objs[RAIZ], objs[PORTA]
bpy.context.view_layer.update()

# medidas tiradas ANTES de mexer (porta fechada)
inv = raiz.matrix_world.inverted()
cantos = [inv @ (porta.matrix_world @ Vector(c)) for c in porta.bound_box]
costas_mm = min(v.y for v in cantos) * 1000.0      # +Y = frente
espessura_mm = (max(v.y for v in cantos) - min(v.y for v in cantos)) * 1000.0
borda_mm = max(v.x for v in cantos) * 1000.0       # a folha passa da face
# a folga que o usuario deixou entre as costas da porta e a frente do
# modulo: o rig foi feito com ela (sem ela o canto da porta aberta entra)
frente_mm = max((inv @ (objs[LATERAL].matrix_world @ Vector(c))).y
                for c in objs[LATERAL].bound_box) * 1000.0
folga_mm = costas_mm - frente_mm


def refazer_cortador():
    """O furo pelo COPO de verdade: a parte da cabeca (com modificadores)
    que entra mais que ABA_COPO_MM na porta fechada. Cilindro redondo no
    centro dela, um pouco mais largo e mais fundo, saindo 1 mm das costas
    (sem face coplanar para o Boolean)."""
    cabeca, cortador = objs[CABECA], objs[CORTADOR]
    grafo = bpy.context.evaluated_depsgraph_get()
    avaliada = cabeca.evaluated_get(grafo)
    malha = avaliada.to_mesh()
    da_porta = porta.matrix_world.inverted()
    pontos = [da_porta @ (cabeca.matrix_world @ v.co) for v in malha.vertices]
    avaliada.to_mesh_clear()
    costas = min(Vector(c).y for c in porta.bound_box)     # -Y local
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
    # cilindro em Z -> eixo Y da porta (o furo entra pelas costas)
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
objs[CONTROLE].animation_data_clear()           # a acao travava o giro
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
# so' o material das pecas: o da porta, o do puxador e o HDRI do mundo
# vinham empacotados (MBs de textura)
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
        idb['cabinet_origem'] = idb.name     # o add-on deduplica por isto
        for chave in LIXO:
            if chave in idb:
                del idb[chave]

# Movimento: a cabeca (e a porta presa nela) para cada angulo do
# controlador, no referencial da raiz. Planar: giro em Z + translacao XY.
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
    assert abs(giro.x) < 1e-3 and abs(giro.y) < 1e-3, giro   # so' em Z
    t = rel.translation * 1000.0
    return [round(graus, 6), round(math.degrees(giro.z), 6),
            round(t.x, 6), round(t.y, 6)]


# 0,5 grau do controlador, subdividido onde a folha gira mais de 0,1
# grau entre duas amostras: no fim do curso o IK estica e a folha salta
# ~2 graus em 0,05 grau do controlador (o rig do usuario e' assim)
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
# so' ate' a abertura MAXIMA: depois dela o IK volta um pouco (a folha
# "assenta"), e a tabela tem de ser monotona para achar o controlador
fim = max(range(len(tabela)), key=lambda i: abs(tabela[i][1]))
tabela = tabela[:fim + 1]
assert all(abs(b[1]) >= abs(a[1]) for a, b in zip(tabela, tabela[1:]))
cabeca_em(CONTROLE_MIN)


def nome_pt(nome):
    """Nome em portugues (pedido do usuario) pelo nome no arquivo dele;
    pinos e parafusos repetidos ganham o .001 do Blender."""
    if nome in NOMES_PT:
        return NOMES_PT[nome]
    if nome.startswith('Screw'):
        return 'Dobradica Parafuso'
    if nome == 'Left Hinge' or nome.startswith('Left Hinge.0'):
        return 'Dobradica Pino'
    return 'Dobradica Peca'


# Tudo em portugues. Nomes nao sao chave de nada (o add-on acha cada peca
# por `cabinet_peca`; driver e IK apontam para o objeto, e renomear osso
# pelo Blender acerta o alvo do IK).
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
print('[extrair] costas %.2f mm, porta %.2f mm, borda %.2f mm, folga %.2f'
      ' mm, furo do copo %.2f x %.2f mm, %d objetos, giro maximo %.2f graus'
      % (costas_mm, espessura_mm, borda_mm, folga_mm, diametro_copo,
         fundo_copo, len(guardar), tabela[-1][1]))
# o arame da previa (contorno de cada peca) vai para o mesmo .json
with open(os.path.join(AQUI, 'extrair_arame_dobradica.py'),
          encoding='utf-8') as f:
    exec(compile(f.read(), 'extrair_arame_dobradica.py', 'exec'))
