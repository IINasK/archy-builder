"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_importacao_blender.py"""
import math
import os
import sys
import unittest

import bpy
import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon


def caixa(nome, dims, centro, rot_z=0.0):
    """Malha de caixa como viria de um arquivo de fora: sem marcador."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= dims[0]
        v.co.y *= dims[1]
        v.co.z *= dims[2]
    malha = bpy.data.meshes.new(nome)
    bm.to_mesh(malha)
    bm.free()
    obj = bpy.data.objects.new(nome, malha)
    bpy.context.collection.objects.link(obj)
    obj.location = centro
    obj.rotation_euler.z = rot_z
    bpy.context.view_layer.update()
    return obj


def selecionar(*objs):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def limites(objs):
    pontos = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    return ([min(p[i] for p in pontos) for i in range(3)],
            [max(p[i] for p in pontos) for i in range(3)])



def relativo(bloco):
    """O bloco com y relativo ao 1o widget: na aba Portas ele desce para
    caber o "Criar Portas" no topo (Epico 2.3); o CONTEUDO e as posicoes
    entre os campos continuam identicos."""
    if not bloco:
        return bloco
    y0 = bloco[0][1]
    return [(b[0], b[1] - y0) + tuple(b[2:]) for b in bloco]


def _faces_da_caixa(lo, hi):
    """12 triangulos de uma caixa (como o Promob exporta), em mm."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    quads = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2),
             (2, 6, 7, 3), (3, 7, 4, 0)]
    return [[v[a], v[b], v[c]] for q in quads for a, b, c in ((q[0], q[1], q[2]),
                                                             (q[0], q[2], q[3]))]


def dxf_promob(caminho, caixas, polyfaces=(), cores=None):
    """DXF no formato do Promob: uma CAMADA por peca; 3DFACE para as
    caixas e POLYLINE polyface (70 = 64) para as recortadas. `cores` =
    {camada: cor} vai na tabela de camadas (7 chapa, 253 ferragem, 254
    aluminio), como o Promob grava."""
    out = []
    if cores:
        out += ['0', 'SECTION', '2', 'TABLES', '0', 'TABLE', '2', 'LAYER', '70', str(len(cores))]
        for camada, cor in cores.items():
            out += ['0', 'LAYER', '2', camada, '70', '0', '62', str(cor), '6', 'CONTINUOUS']
        out += ['0', 'ENDTAB', '0', 'ENDSEC']
    out += ['0', 'SECTION', '2', 'ENTITIES']
    for camada, faces in caixas:
        for face in faces:
            pts = list(face) + [face[-1]] * (4 - len(face))
            out += ['0', '3DFACE', '8', camada]
            for n, p in enumerate(pts):
                out += ['1%d' % n, str(p[0]), '2%d' % n, str(p[1]), '3%d' % n, str(p[2])]
    for camada, vertices, faces in polyfaces:
        out += ['0', 'POLYLINE', '8', camada, '66', '1', '70', '64']
        for p in vertices:
            out += ['0', 'VERTEX', '8', camada, '10', str(p[0]), '20', str(p[1]),
                    '30', str(p[2]), '70', '192']
        for face in faces:
            out += ['0', 'VERTEX', '8', camada, '10', '0', '20', '0', '30', '0', '70', '128']
            for k, indice in enumerate(face):
                out += ['7%d' % (k + 1), str(indice + 1)]
        out += ['0', 'SEQEND', '8', camada]
    out += ['0', 'ENDSEC', '0', 'EOF']
    with open(caminho, 'w', encoding='latin1') as f:
        f.write('\n'.join(out) + '\n')


def base_em_l(lado=600.0, recorte=300.0, e=15.0, z=0.0):
    """Prisma em L (a base de um canto do Promob): 12 vertices."""
    contorno = [(0, 0), (lado, 0), (lado, recorte), (recorte, recorte),
                (recorte, lado), (0, lado)]
    vs = [(x, y, z) for x, y in contorno] + [(x, y, z + e) for x, y in contorno]
    n = len(contorno)
    faces = [(0, 3, 2, 1), (0, 5, 4, 3), (6, 7, 8, 9), (6, 9, 10, 11)]
    faces += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    return vs, faces


class TestImportacao(unittest.TestCase):
    def test_modulos_do_promob_so_com_as_chapas(self):
        # pedido do usuario: os modulos prontos do Promob, exportados em
        # DXF (uma camada por peca); dobradica, plaquinha de 2 mm e piso
        # ficam de fora, a base em L continua em L
        import tempfile
        caminho = os.path.join(tempfile.mkdtemp(), 'Cantos.dxf')
        vs_l, fs_l = base_em_l()
        dxf_promob(caminho, [
            ('LAYER0', _faces_da_caixa((-100, -100, -5), (3000, 900, 0))),      # piso
            ('LAYER1', _faces_da_caixa((0, 0, 15), (15, 600, 700))),           # lateral
            ('LAYER2', _faces_da_caixa((15, 585, 15), (600, 600, 700))),       # lateral
            ('LAYER3', _faces_da_caixa((15, 200, 300), (38, 243, 352))),       # dobradica
            ('LAYER4', _faces_da_caixa((15, 300, 500), (17, 331, 542))),       # placa 2 mm
            ('LAYER10', _faces_da_caixa((2000, 0, 0), (2015, 400, 700))),      # outro modulo
            ('LAYER11', _faces_da_caixa((2015, 0, 0), (2500, 400, 15))),
        ], [('LAYER5', vs_l, fs_l)])
        modulos, info = addon.importacao.importar_dxf_promob(
            bpy.context, caminho, addon.importacao.prefixo_da_categoria('Cantos'))
        self.assertEqual(info, {'pecas': 8, 'chapas': 5, 'curvas': 0, 'descartadas': 2,
                                'piso': 1, 'portas': 0, 'gavetas': 0, 'correr': 0})
        self.assertEqual(len(modulos), 2)
        canto, outro = modulos
        self.assertTrue(canto.name.startswith('Canto 01 '), canto.name)
        self.assertEqual(len(addon.modulos._chapas_do_conjunto(canto)), 3)
        self.assertEqual(len(addon.modulos._chapas_do_conjunto(outro)), 2)
        # a base em L e' chapa de 15 mm com a malha PRESERVADA, no mesmo lugar
        base = next(c for c in addon.modulos._chapas_do_conjunto(canto)
                    if not addon.chapas._malha_e_caixa(c.data))
        self.assertAlmostEqual(base.chapa_espessura_mm, 15.0, places=3)
        self.assertEqual(len(base.data.vertices), 12)
        pts = [base.matrix_world @ v.co * 1000.0 for v in base.data.vertices]
        self.assertPerto([min(p[k] for p in pts) for k in range(3)], (0, 0, 0), 3)
        self.assertPerto([max(p[k] for p in pts) for k in range(3)], (600, 600, 15), 3)
        # as retangulares viram a caixa parametrica
        lateral = next(c for c in addon.modulos._chapas_do_conjunto(canto)
                       if addon.chapas._malha_e_caixa(c.data))
        self.assertEqual(sorted(round(v) for v in (lateral.chapa_largura_mm,
                                                   lateral.chapa_comprimento_mm,
                                                   lateral.chapa_espessura_mm)),
                         [15, 585, 685] if lateral.chapa_comprimento_mm < 600 else [15, 600, 685])
        # o operador (cabinet_importar_promob) faz o mesmo na cena
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        self.assertEqual(bpy.ops.object.cabinet_importar_promob(
            'EXEC_DEFAULT', filepath=caminho), {'FINISHED'})
        self.assertEqual(len([o for o in bpy.data.objects
                              if addon.chapas.MARCA_CONJUNTO in o]), 2)
        self.assertEqual(addon.importacao.prefixo_da_categoria('Inferiores'), 'Inferior')

    def test_promob_traz_a_porta_curva_e_a_prateleira_redonda(self):
        # pedido do usuario: o raio das cantoneiras/diagonais e' editavel,
        # entao a porta CURVA vem junto (acessorio que deforma) e a
        # prateleira de quina redonda e' chapa (contorno preservado). O
        # micro-ondas (caixa com moldura) nao e' peca curva.
        import tempfile
        caminho = os.path.join(tempfile.mkdtemp(), 'Diagonais.dxf')
        arco = lambda r: [(150 + r * math.cos(math.radians(180 + 7.5 * i)),
                           150 + r * math.sin(math.radians(180 + 7.5 * i)))
                          for i in range(13)]
        contorno = arco(150) + [(300, 0), (300, 550), (0, 550)]
        n = len(contorno)
        prateleira = ([(x, y, 0) for x, y in contorno] + [(x, y, 15) for x, y in contorno],
                      [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
                      + [(0, i + 1, i) for i in range(1, n - 1)]
                      + [(n, n + i, n + i + 1) for i in range(1, n - 1)])
        fora, dentro = arco(150), arco(135)
        faixa = fora + dentro[::-1]
        m = len(faixa)
        porta = ([(x, y, 15) for x, y in faixa] + [(x, y, 685) for x, y in faixa],
                 [(i, (i + 1) % m, m + (i + 1) % m, m + i) for i in range(m)]
                 + [(i, i + 1, m - 2 - i, m - 1 - i) for i in range(12)]
                 + [(m + i, m + m - 1 - i, m + m - 2 - i, m + i + 1) for i in range(12)])
        # micro-ondas: caixa de 450 x 300 x 15 com um vao (moldura)
        moldura = [(2000, 0), (2450, 0), (2450, 300), (2000, 300)]
        dxf_promob(caminho, [
            ('LAYER0', _faces_da_caixa((-500, -500, -5), (3000, 2000, 0))),     # piso
            ('LAYER1', _faces_da_caixa((300, 0, 0), (315, 565, 700))),
            ('LAYER2', _faces_da_caixa((0, 550, 0), (300, 565, 700))),
            ('LAYER9', _faces_da_caixa((2000, 0, 0), (2015, 400, 700))),
            ('LAYER10', _faces_da_caixa((2015, 0, 0), (2450, 400, 15))),
            ('LAYER11', _faces_da_caixa((2015, 0, 100), (2450, 20, 400))),     # micro-ondas
        ], [('LAYER3', *prateleira), ('LAYER4', *porta)])
        modulos, info = addon.importacao.importar_dxf_promob(bpy.context, caminho, 'Diagonal')
        self.assertEqual((info['chapas'], info['curvas']), (6, 1))
        diagonal = modulos[0]
        curvas = [o for o in diagonal.children if addon.formas.MARCA_CURVA in o]
        self.assertEqual(len(curvas), 1)
        self.assertIn(addon.chapas.MARCA_ACESSORIO, curvas[0])
        redonda = next(c for c in addon.modulos._chapas_do_conjunto(diagonal)
                       if not addon.chapas._malha_e_caixa(c.data))
        self.assertAlmostEqual(redonda.chapa_espessura_mm, 15.0, places=2)
        self.assertEqual(addon.formas.forma_do_modulo(diagonal)['cantos'][0]['tipo'], 'CURVA')

    def test_categorias_do_promob_pela_pasta_e_pelo_arquivo(self):
        # pedido do usuario: a PASTA e' a aba do Promob, o ARQUIVO a
        # categoria; as primeiras exportacoes (Cantos/, Bifond/) sao Inferiores
        cat = addon.importacao.categoria_promob
        raiz = os.path.join('Promob', 'Cozinha')
        self.assertEqual(cat(os.path.join(raiz, 'Bifond', 'Balcões.dxf')),
                         ('Inferiores', 'Balcoes', 'Balcao'))
        self.assertEqual(cat(os.path.join(raiz, 'Bifond', 'Bifond.dxf')),
                         ('Inferiores', 'Cantos Bifold', 'Bifold'))
        self.assertEqual(cat(os.path.join(raiz, 'Bifond', 'PEletros.dxf')),
                         ('Inferiores', 'Para Eletros', 'Eletro'))
        self.assertEqual(cat(os.path.join(raiz, 'Cantos', 'Cantos.dxf')),
                         ('Inferiores', 'Cantos', 'Canto'))
        # fora de Inferiores o nome leva a aba: nao grava por cima
        self.assertEqual(cat(os.path.join(raiz, 'Sup Baixos', 'Cantos.dxf')),
                         ('Sup Baixos', 'Cantos', 'Canto Sup Baixo'))
        self.assertEqual(cat(os.path.join(raiz, 'Altos', 'Torres.dxf')),
                         ('Altos', 'Torres', 'Torre Alto'))
        self.assertEqual(cat(os.path.join(raiz, 'Ilhas', 'Inferiores.dxf')),
                         ('Ilhas', 'Inferiores', 'Inferior Ilha'))
        self.assertEqual(addon.importacao.prefixo_da_categoria('Diagonais'), 'Diagonal')

    def test_piso_fino_sai_mesmo_com_modulos_fora_dele(self):
        # Especiais do Promob: os modulos passam da borda do piso (72% em
        # cima); fino assim (5 mm) e grande, e' piso -- senao ele juntava
        # todos os modulos num so'
        import tempfile
        caminho = os.path.join(tempfile.mkdtemp(), 'Especiais.dxf')
        caixas = [('LAYER0', _faces_da_caixa((0, 0, -5), (2000, 1000, 0)))]
        for n, x in enumerate((100, 1800, 2600)):
            caixas += [('LAYER%d' % (10 * n + 1), _faces_da_caixa((x, 100, 0), (x + 15, 600, 700))),
                       ('LAYER%d' % (10 * n + 2), _faces_da_caixa((x + 15, 100, 0), (x + 400, 600, 15)))]
        dxf_promob(caminho, caixas)
        modulos, info = addon.importacao.importar_dxf_promob(bpy.context, caminho, 'Especial')
        self.assertEqual(info['piso'], 1)
        self.assertEqual(len(modulos), 3)

    def test_peca_girada_e_recortada_fica_no_lugar_ao_virar_chapa(self):
        # Regressao: `converter_em_chapa` trocava a matriz sem levar os
        # vertices -- a peca recortada ia para outro lugar, e a caixa a 45
        # graus (porta de canto do Promob) nao era reconhecida como caixa
        malha = bpy.data.meshes.new('Diagonal')
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Rotation(math.radians(45), 4, 'Z')
                              @ Matrix.Diagonal((0.4, 0.015, 0.7, 1.0)))
        bm.to_mesh(malha)
        bm.free()
        obj = bpy.data.objects.new('Diagonal', malha)
        bpy.context.collection.objects.link(obj)
        obj.location = (1.0, 2.0, 0.35)
        bpy.context.view_layer.update()
        antes = sorted(tuple(round(c, 5) for c in obj.matrix_world @ v.co)
                       for v in obj.data.vertices)
        addon.importacao.converter_em_chapa(obj)
        bpy.context.view_layer.update()
        self.assertTrue(addon.chapas._malha_e_caixa(obj.data))
        self.assertAlmostEqual(obj.chapa_espessura_mm, 15.0, places=3)
        depois = sorted(tuple(round(c, 5) for c in obj.matrix_world @ v.co)
                        for v in obj.data.vertices)
        for a, b in zip(antes, depois):
            self.assertPerto(a, b, 4)

    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.context.scene.cabinet_aba = 'MODULOS'

    def assertPerto(self, a, b, casas=5):
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=casas)

    # ------------------------------------------------------ classificador
    def test_classifica_chapa_e_acessorio(self):
        placa = caixa('Placa', (0.6, 0.4, 0.018), (0, 0, 0))
        cubo = caixa('Cubo', (0.3, 0.3, 0.3), (1, 0, 0))
        pe = caixa('Pe', (0.05, 0.05, 0.1), (2, 0, 0))
        bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=0.3,
                                            location=(3, 0, 0))
        cilindro = bpy.context.object
        self.assertTrue(addon.importacao._analisar_peca(placa)['chapa'])
        for obj in (cubo, pe, cilindro):
            self.assertFalse(addon.importacao._analisar_peca(obj)['chapa'], obj.name)

    def test_lateral_em_pe_girada_vira_chapa_sem_sair_do_lugar(self):
        # REGRESSAO: a conversao lia obj.dimensions em eixos de mundo e
        # tomava Z como espessura -- esta lateral virava chapa de 30 mm.
        lateral = caixa('Lateral', (0.018, 0.4, 0.7), (1, 2, 3),
                        rot_z=math.radians(30))
        antes = limites([lateral])
        selecionar(lateral)
        self.assertEqual(bpy.ops.object.cabinet_marcar(), {'FINISHED'})
        self.assertIn(addon.chapas.MARCA_CHAPA, lateral)
        self.assertEqual(lateral.chapa_espessura_mm, 18.0)
        self.assertEqual(sorted((round(lateral.chapa_largura_mm),
                                 round(lateral.chapa_comprimento_mm))),
                         [400, 700])
        self.assertPerto(lateral.scale, (1, 1, 1))
        depois = limites([lateral])
        self.assertPerto(antes[0], depois[0])
        self.assertPerto(antes[1], depois[1])
        # local Z = espessura (invariante 1)
        z = lateral.matrix_world.to_3x3().col[2].normalized()
        self.assertAlmostEqual(abs(z.dot(Vector((math.cos(math.radians(30)),
                                                 math.sin(math.radians(30)),
                                                 0)))), 1.0, places=5)

    def test_escala_do_objeto_vira_medida(self):
        placa = caixa('Placa', (0.3, 0.4, 0.018), (0, 0, 0))
        placa.scale = (2.0, 1.0, 1.0)
        bpy.context.view_layer.update()
        selecionar(placa)
        bpy.ops.object.cabinet_marcar()
        self.assertPerto(placa.scale, (1, 1, 1))
        self.assertAlmostEqual(max(placa.chapa_largura_mm,
                                   placa.chapa_comprimento_mm), 600.0, places=2)

    def test_chapa_alinhada_continua_como_antes(self):
        placa = caixa('Placa', (0.6, 0.4, 0.018), (0, 0, 0))
        selecionar(placa)
        bpy.ops.object.cabinet_marcar()
        self.assertAlmostEqual(placa.chapa_largura_mm, 600.0, places=3)
        self.assertAlmostEqual(placa.chapa_comprimento_mm, 400.0, places=3)
        self.assertPerto(placa.rotation_euler, (0, 0, 0))

    # ------------------------------------------------------------- modulo
    def armario(self):
        """Laterais, base, tampo e um pe' cilindrico do lado direito."""
        pecas = [caixa('Lat_E', (0.018, 0.4, 0.7), (-0.291, 0, 0.35)),
                 caixa('Lat_D', (0.018, 0.4, 0.7), (0.291, 0, 0.35)),
                 caixa('Base', (0.564, 0.4, 0.018), (0, 0, 0.009)),
                 caixa('Tampo', (0.564, 0.4, 0.018), (0, 0, 0.691))]
        bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=0.08,
                                            location=(0.25, 0, 0.04))
        pe = bpy.context.object
        return pecas, pe

    def test_converter_em_modulo_separa_chapas_e_acessorios(self):
        pecas, pe = self.armario()
        selecionar(*pecas, pe)
        self.assertEqual(bpy.ops.object.cabinet_converter_modulo(), {'FINISHED'})
        conj = bpy.context.object
        self.assertIn(addon.chapas.MARCA_CONJUNTO, conj)
        self.assertEqual(set(addon.modulos._chapas_do_conjunto(conj)), set(pecas))
        self.assertIn(addon.chapas.MARCA_ACESSORIO, pe)
        self.assertNotIn(addon.chapas.MARCA_CHAPA, pe)
        self.assertEqual(pe.parent, conj)
        for peca in pecas:
            self.assertEqual(peca.chapa_espessura_mm, 18.0)

    def test_acessorio_segue_a_face_mais_proxima(self):
        pecas, pe = self.armario()
        selecionar(*pecas, pe)
        bpy.ops.object.cabinet_converter_modulo()
        conj = bpy.context.object
        antes = addon.portas._centro_mundo(pe)
        conj.conj_largura_mm += 100     # cresce a partir da esquerda
        bpy.context.view_layer.update()
        depois = addon.portas._centro_mundo(pe)
        # o pe' esta' perto da DIREITA: anda junto com ela
        self.assertAlmostEqual(depois.x - antes.x, 0.1, places=4)
        self.assertAlmostEqual(depois.z, antes.z, places=4)
        conj.conj_altura_mm += 200      # base parada: o pe' tambem
        bpy.context.view_layer.update()
        self.assertAlmostEqual(addon.portas._centro_mundo(pe).z, antes.z, places=4)

    def test_sem_nenhuma_chapa_tudo_vira_chapa(self):
        a = caixa('A', (0.3, 0.3, 0.3), (0, 0, 0))
        b = caixa('B', (0.3, 0.3, 0.3), (0.3, 0, 0))
        selecionar(a, b)
        bpy.ops.object.cabinet_converter_modulo()
        self.assertIn(addon.chapas.MARCA_CHAPA, a)
        self.assertIn(addon.chapas.MARCA_CHAPA, b)

    # --------------------------------------------- porta a partir de objetos
    def porta_importada(self, x=0.0, largura=0.4, altura=0.7, z=0.35,
                        y=-0.2, puxador=True):
        placa = caixa('Placa', (largura, 0.018, altura), (x, y - 0.009, z))
        objs = [placa]
        if puxador:
            objs.append(caixa('Puxador', (0.02, 0.03, 0.15),
                              (x + largura / 2 - 0.03, y - 0.033, z)))
        selecionar(*objs)
        self.assertEqual(bpy.ops.object.cabinet_folha_de_objetos(), {'FINISHED'})
        return addon.portas._grupo_portas(bpy.context.object), placa, objs[1:]

    def test_folha_de_objetos_fica_no_lugar_com_o_puxador(self):
        placa = caixa('Placa', (0.4, 0.018, 0.7), (0, -0.209, 0.35))
        pux = caixa('Puxador', (0.02, 0.03, 0.15), (0.17, -0.233, 0.35))
        antes = limites([placa]), limites([pux])
        selecionar(placa, pux)
        bpy.ops.object.cabinet_folha_de_objetos()
        grupo = addon.portas._grupo_portas(placa)
        self.assertIsNotNone(grupo)
        self.assertIn(addon.chapas.MARCA_FOLHA, placa)
        self.assertEqual(addon.portas._folhas_portas(grupo), [placa])
        self.assertEqual(pux.parent, placa)
        self.assertIn(addon.chapas.MARCA_PUXADOR, pux)
        for obj, (lo, hi) in ((placa, antes[0]), (pux, antes[1])):
            lo2, hi2 = limites([obj])
            self.assertPerto(lo, lo2, 4)
            self.assertPerto(hi, hi2, 4)
        # a frente vai para o lado do puxador (-Y)
        normal = grupo.matrix_world.to_3x3().col[2].normalized()
        self.assertAlmostEqual(normal.y, -1.0, places=5)

    def test_puxador_travado_mantem_medida_e_distancia_da_borda(self):
        grupo, placa, (pux,) = self.porta_importada()
        largura = limites([pux])[1][0] - limites([pux])[0][0]
        borda = limites([placa])[1][0] - limites([pux])[1][0]
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'folga_mm', 3.0), '')
        self.assertAlmostEqual(limites([pux])[1][0] - limites([pux])[0][0],
                               largura, places=5)
        self.assertAlmostEqual(limites([placa])[1][0] - limites([pux])[1][0],
                               borda, places=5)

    def test_puxador_destravado_estica_com_a_folha(self):
        grupo, placa, (pux,) = self.porta_importada()
        pux[addon.chapas.CHAVE_TRAVAS_PUXADOR] = [0, 1, 1]
        largura = limites([pux])[1][0] - limites([pux])[0][0]
        folha_antes = placa.chapa_largura_mm
        addon.portas._editar_parametro_porta(bpy.context, grupo, 'folga_mm', 20.0)
        razao = placa.chapa_largura_mm / folha_antes
        self.assertLess(razao, 1.0)
        self.assertAlmostEqual(limites([pux])[1][0] - limites([pux])[0][0],
                               largura * razao, places=5)

    def test_vao_inverso_ida_e_volta(self):
        base = dict(abertura='GIRO', folhas=1, dobradica='RETA',
                    espessura_mm=18.0, lateral_mm=18.0, folga_mm=2.0,
                    entre_folhas_mm=3.0, afastamento_mm=4.0,
                    recuo_embutida_mm=5.0, recuo_correr_mm=30.0,
                    entre_planos_mm=2.0)
        for dobradica in ('RETA', 'CURVA', 'SUPER_CURVA'):
            for folhas in (1, 2):
                with self.subTest(dobradica=dobradica, folhas=folhas):
                    p = dict(base, dobradica=dobradica, folhas=folhas)
                    calculadas = addon.portas._calcular_folhas_portas(600, 800, p)
                    pontos = [Vector(c) + Vector((sx * l, sy * a, sz * e)) / 2
                              for l, a, e, c in calculadas
                              for sx in (-1, 1) for sy in (-1, 1)
                              for sz in (-1, 1)]
                    lo = Vector(tuple(min(q[i] for q in pontos) for i in range(3)))
                    hi = Vector(tuple(max(q[i] for q in pontos) for i in range(3)))
                    largura, altura, origem = addon.importacao._vao_inverso((lo, hi), p)
                    self.assertAlmostEqual(largura, 600, places=6)
                    self.assertAlmostEqual(altura, 800, places=6)
                    self.assertPerto(origem, (0, 0, 0), 6)

    def test_porta_dupla_funde_duas_folhas(self):
        g1, p1, _ = self.porta_importada(x=-0.2015, largura=0.4)
        g2, p2, _ = self.porta_importada(x=0.2015, largura=0.4)
        externo = limites([p1, p2])
        nome_g2 = g2.name
        selecionar(g1, g2)
        self.assertEqual(bpy.ops.object.cabinet_porta_dupla(), {'FINISHED'})
        self.assertNotIn(nome_g2, bpy.data.objects)
        self.assertEqual(len(addon.portas._folhas_portas(g1)), 2)
        self.assertAlmostEqual(g1['porta_parametros']['entre_folhas_mm'], 3.0,
                               places=3)
        lo, hi = limites(addon.portas._folhas_portas(g1))
        self.assertPerto(lo, externo[0], 4)
        self.assertPerto(hi, externo[1], 4)

    def test_porta_dupla_recusa_alturas_diferentes(self):
        g1, _p1, _ = self.porta_importada(x=-0.2015)
        g2, _p2, _ = self.porta_importada(x=0.2015, altura=0.6)
        selecionar(g1, g2)
        self.assertEqual(bpy.ops.object.cabinet_porta_dupla(), {'CANCELLED'})
        self.assertIn(g2.name, bpy.data.objects)
        self.assertEqual(len(addon.portas._folhas_portas(g1)), 1)

    def test_definir_frente_vira_a_porta_sem_mover(self):
        grupo, placa, (pux,) = self.porta_importada()
        antes = limites([placa]), limites([pux])
        normal = grupo.matrix_world.to_3x3().col[2].normalized()
        self.assertFalse(addon.importacao._definir_frente_porta(bpy.context, grupo, normal))
        self.assertTrue(addon.importacao._definir_frente_porta(bpy.context, grupo, -normal))
        nova = grupo.matrix_world.to_3x3().col[2].normalized()
        self.assertAlmostEqual(nova.dot(normal), -1.0, places=5)
        for obj, (lo, hi) in ((placa, antes[0]), (pux, antes[1])):
            lo2, hi2 = limites([obj])
            self.assertPerto(lo, lo2, 4)
            self.assertPerto(hi, hi2, 4)
        with self.assertRaises(ValueError):
            addon.importacao._definir_frente_porta(bpy.context, grupo, Vector((0, 0, 1)))

    # ---------------------------------------------- vincular porta + modulo
    def nicho(self):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar()
        conj = next(o for o in bpy.data.objects if addon.chapas.MARCA_CONJUNTO in o)
        bpy.context.view_layer.update()
        return conj

    def porta_no_modulo(self, conj, embutida=False):
        lo, hi = addon.portas._limites_locais_modulo(conj)
        E = addon.portas._caixa_do_modulo(conj)[3]
        if embutida:
            L, A = hi.x - lo.x - 2 * E, hi.z - lo.z - 2 * E
            y = lo.y + 9          # atras da face, dentro do vao
        else:
            L, A = hi.x - lo.x, hi.z - lo.z
            y = lo.y - 9          # na frente, cobrindo as laterais
        centro = conj.matrix_world @ (Vector(((lo.x + hi.x) / 2, y,
                                              (lo.z + hi.z) / 2)) / 1000)
        placa = caixa('Frente', (L / 1000, 0.018, A / 1000), centro)
        pux = caixa('Puxador', (0.02, 0.03, 0.15),
                    centro + Vector((L / 2000 - 0.04, -0.03, 0)))
        selecionar(placa, pux)
        bpy.ops.object.cabinet_folha_de_objetos()
        grupo = addon.portas._grupo_portas(placa)
        selecionar(grupo, conj)
        self.assertTrue(addon.importacao.OBJECT_OT_vincular_porta.poll(bpy.context))
        self.assertEqual(bpy.ops.object.cabinet_vincular_porta(), {'FINISHED'})
        return grupo, placa, pux

    def test_vincular_deduz_reta_e_acompanha_o_modulo(self):
        conj = self.nicho()
        grupo, placa, pux = self.porta_no_modulo(conj)
        p = grupo['porta_parametros']
        self.assertEqual(p['dobradica'], 'RETA')
        self.assertAlmostEqual(p['folga_mm'], 0.0, places=3)
        self.assertAlmostEqual(p['afastamento_mm'], 0.0, places=3)
        self.assertEqual(grupo[addon.portas.CHAVE_MODULO_PORTA], conj.name)
        self.assertEqual(grupo.parent, conj)
        L = addon.portas._caixa_do_modulo(conj)[0]
        conj.conj_largura_mm = L + 200
        bpy.context.view_layer.update()
        lo, hi = limites([placa])
        self.assertAlmostEqual(hi[0] - lo[0], (L + 200) / 1000, places=4)
        # o puxador travado continua perto da borda direita
        self.assertAlmostEqual(hi[0] - limites([pux])[1][0], 0.03, places=4)

    def test_vincular_deduz_embutida(self):
        conj = self.nicho()
        grupo, _placa, _pux = self.porta_no_modulo(conj, embutida=True)
        self.assertEqual(grupo['porta_parametros']['dobradica'], 'SUPER_CURVA')

    def test_reposicionar_move_a_mesma_porta_para_o_vao_novo(self):
        conj = self.nicho()
        grupo, placa, _pux = self.porta_no_modulo(conj)
        lo, hi = addon.portas._limites_locais_modulo(conj)
        E = addon.portas._caixa_do_modulo(conj)[3]
        meio = (lo.z + hi.z) / 2
        a = conj.matrix_world @ (Vector((lo.x, lo.y, meio)) / 1000)
        b = conj.matrix_world @ (Vector((hi.x, lo.y, hi.z)) / 1000)
        chapa = addon.modulos._chapas_do_conjunto(conj)[0]
        ref = conj.matrix_world.to_quaternion().to_matrix()
        quantos = len([o for o in bpy.data.objects if addon.chapas.MARCA_PORTAS in o])
        self.assertEqual(bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            referencia=tuple(v for linha in ref for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name,
            objeto_a_nome=chapa.name, objeto_b_nome=chapa.name,
            centro=addon.portas._centro_do_movel(chapa, chapa),
            grupo_alvo=grupo.name), {'FINISHED'})
        self.assertEqual(len([o for o in bpy.data.objects
                              if addon.chapas.MARCA_PORTAS in o]), quantos)
        self.assertAlmostEqual(grupo['porta_vao_altura_mm'],
                               hi.z - E - meio, places=2)
        self.assertEqual(grupo[addon.portas.CHAVE_MODULO_PORTA], conj.name)
        self.assertEqual(addon.portas._folhas_portas(grupo), [placa])

    # ------------------------------------------------------------ gaveta
    def test_cabecalho_tem_as_cinco_abas(self):
        # As correntes entre as abas foram descontinuadas (pedido do
        # usuario): nenhum widget de operador no cabecalho. A aba Gavetas
        # e a Prateleiras (pedidos do usuario) vem antes de Puxadores.
        for largura in (190, 320, 564):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1200)
            cabecalho = widgets[:addon.gaveta.WIDGETS_CABECALHO]
            self.assertEqual([w[5][0] for w in cabecalho], ['aba'] * 5)
            self.assertFalse(any(w[5] and w[5][0] == 'operador'
                                 and w[1] > 1200 - 48 for w in widgets))
            self.assertEqual([w[5][1] for w in cabecalho if w[5][0] == 'aba'],
                             ['MODULOS', 'PORTAS', 'GAVETAS', 'PRATELEIRAS', 'PUXADORES'])
            fim = cabecalho[-1]
            self.assertAlmostEqual(fim[0] + fim[2], 12 + min(540, largura - 24))
        # sem selecao, as correntes nao tem o que ligar
        selecionar(caixa('X', (0.1, 0.1, 0.1), (0, 0, 0)))
        self.assertFalse(addon.gaveta_eventos._poll_operador('object.cabinet_vincular_porta'))
        self.assertFalse(addon.gaveta_eventos._poll_operador('object.cabinet_vincular_puxador'))

    def test_bloco_do_puxador_tem_cadeados_e_e_igual_nas_tres_abas(self):
        _grupo, _placa, (pux,) = self.porta_importada()
        selecionar(pux)
        modo, campos, dono = addon.gaveta._medidas_gaveta(bpy.context)
        self.assertEqual((modo, dono), ('PUXADOR', 'puxador'))
        alvo = {'medida', 'cadeado'}

        def bloco(aba):
            bpy.context.scene.cabinet_aba = aba
            widgets = addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)
            return [v[:4] + (v[5][0],) for v in widgets
                    if v[5] and v[5][0] in alvo]

        # o puxador e' da aba Puxadores (pedido do usuario: cada menu
        # mostra o que vale para a selecao); nas outras, nada dele
        puxadores = bloco('PUXADORES')
        self.assertEqual(sum(1 for b in puxadores if b[4] == 'cadeado'), 3)
        self.assertEqual(bloco('PORTAS'), [])
        self.assertEqual(bloco('MODULOS'), [])
        # editar uma medida escala so' aquele eixo do puxador
        altura_antes = limites([pux])[1][2] - limites([pux])[0][2]
        self.assertEqual(bpy.ops.object.cabinet_editar_medida_gaveta(
            'EXEC_DEFAULT', dono='puxador', objeto=pux.name,
            propriedade='pux_0', valor=0.05), {'FINISHED'})
        self.assertAlmostEqual(limites([pux])[1][0] - limites([pux])[0][0],
                               0.05, places=5)
        self.assertAlmostEqual(limites([pux])[1][2] - limites([pux])[0][2],
                               altura_antes, places=5)

    def test_aba_puxadores_sem_sobreposicao(self):
        bpy.context.scene.cabinet_aba = 'PUXADORES'
        for largura in (190, 320, 564):
            caixas = [(v[0], v[1], v[2], v[3]) for v in
                      addon.gaveta._widgets_gaveta(bpy.context, largura, 1400)]
            for i, (ax, ay, aw, ah) in enumerate(caixas):
                for bx, by, bw, bh in caixas[i + 1:]:
                    sobrepoe = (ax < bx + bw - 0.01 and bx < ax + aw - 0.01
                                and ay < by + bh - 0.01 and by < ay + ah - 0.01)
                    self.assertFalse(sobrepoe, 'largura %d' % largura)

    # ------------------------------------------- Promob -> sistemas nossos
    # Pedido do usuario: "integracao, nao importacao bruta". A frente com
    # dobradica vira PORTA nativa, a com caixa atras GAVETAS nativas, o
    # quadro de aluminio porta de CORRER (folha Quadro); trilho, dobradica
    # e quadro do Promob nunca viram chapa. Caixas em mm, frente em -Y.
    def importar(self, nome, caixas, cores):
        import tempfile
        caminho = os.path.join(tempfile.mkdtemp(), nome)
        dxf_promob(caminho, [(c, _faces_da_caixa(lo, hi)) for c, lo, hi in caixas],
                   cores=cores)
        return addon.importacao.importar_dxf_promob(bpy.context, caminho, 'Teste')

    CORPO_400 = [   # 400 x 700, corpo de 15 de y 15 a 565 (a porta na frente)
        ('LAYER1', (0, 15, 0), (15, 565, 700)),
        ('LAYER2', (385, 15, 0), (400, 565, 700)),
        ('LAYER3', (15, 15, 0), (385, 565, 15)),
        ('LAYER4', (15, 15, 685), (385, 565, 700)),
    ]

    def test_promob_frente_com_dobradica_vira_porta_nativa(self):
        caixas = self.CORPO_400 + [
            ('LAYER5', (10, 541, 10), (390, 547, 690)),       # fundo de 6
            ('LAYER6', (5, 0, 5), (395, 15, 695)),            # a frente
            ('LAYER7', (367, 14, 100), (390, 57, 152)),       # dobradicas
            ('LAYER8', (367, 14, 550), (390, 57, 602)),
            ('LAYER9', (354, 15, 105), (385, 17, 147)),       # placa 2 mm
        ]
        cores = {c: 7 for c, _lo, _hi in caixas}
        cores.update(LAYER7=253, LAYER8=253, LAYER9=253)
        modulos, info = self.importar('Balcoes.dxf', caixas, cores)
        self.assertEqual((len(modulos), info['portas']), (1, 1), info)
        conj = modulos[0]
        # a frente saiu do corpo: P = 550, e o E e' o da caixa (nao o fundo de 6)
        self.assertAlmostEqual(conj.conj_profundidade_mm, 550.0, places=1)
        self.assertAlmostEqual(conj.conj_espessura_mm, 15.0, places=3)
        grupo, = addon.portas._portas_do_conjunto(conj)
        p = dict(grupo['porta_parametros'])
        # dobradicas a' direita; cobre 10 de 15 (o Promob deixa 5) = RETA nossa
        self.assertEqual((p['abertura'], p['folhas'], p['dobradica_lado'], p['dobradica']),
                         ('GIRO', 1, 'DIREITA', 'RETA'))
        # o fundo fino e' o FUNDO dependente (refeito pela caixa, em canal)
        fundo = addon.modulos.fundo_do_modulo(conj)
        self.assertIsNotNone(fundo)
        self.assertAlmostEqual(fundo.chapa_espessura_mm, 6.0, places=1)
        self.assertAlmostEqual(fundo.chapa_largura_mm, 400 - 30 + 14, places=1)
        # nenhuma ferragem do Promob virou peca
        self.assertFalse([o for o in bpy.data.objects if o.name in ('Peca LAYER7', 'Peca LAYER9')])

    def test_promob_pilha_com_caixa_vira_gavetas_nativas(self):
        caixas = list(self.CORPO_400)
        frentes = ((5, 230), (235, 460), (465, 695))
        for i, (z0, z1) in enumerate(frentes):
            caixas.append(('LAYER1%d' % i, (5, 0, z0), (395, 15, z1)))
            # a caixa do Promob nasce DENTRO da frente (y 12): encosta nela
            caixas += [('LAYER2%d' % i, (28, 12, z0 + 20), (43, 500, z0 + 150)),
                       ('LAYER3%d' % i, (357, 12, z0 + 20), (372, 500, z0 + 150)),
                       ('LAYER4%d' % i, (43, 15, z0 + 20), (357, 30, z0 + 150)),
                       ('LAYER5%d' % i, (28, 12, z0 + 14), (372, 500, z0 + 20))]
        modulos, info = self.importar('Gaveteiros.dxf', caixas, {c: 7 for c, _l, _h in caixas})
        conj, = modulos
        self.assertEqual(info['gavetas'], 1, info)
        # a caixa do Promob saiu: o modulo e' so' o corpo
        self.assertEqual(len(addon.modulos._chapas_do_conjunto(conj)), 4)
        grupo, = addon.gavetas.grupos_do_modulo(conj)
        p = addon.gavetas.parametros(grupo)
        self.assertEqual((p['quantidade'], p['cobertura'], p['trilho']),
                         (3, 'SOBREPOSTA', 'TELESCOPICO'))
        # as alturas DESIGUAIS do Promob ficam (proporcao), e as frentes
        # nascem onde estavam
        alturas = [addon.gavetas.frente_da_gaveta(g).chapa_comprimento_mm
                   for g in addon.gavetas.gavetas_do_grupo(grupo)]
        self.assertAlmostEqual(alturas[2] / alturas[0], 230.0 / 225.0, places=2)
        frente = addon.gavetas.frente_da_gaveta(addon.gavetas.gavetas_do_grupo(grupo)[0])
        self.assertAlmostEqual(frente.chapa_largura_mm, 390.0, delta=1.0)

    def test_promob_quadro_de_aluminio_vira_correr_com_trilho_nosso(self):
        caixas = [
            ('LAYER1', (0, 0, 0), (15, 550, 1356)), ('LAYER2', (1185, 0, 0), (1200, 550, 1356)),
            ('LAYER3', (15, 0, 3), (1185, 550, 18)), ('LAYER4', (15, 0, 1338), (1185, 550, 1353)),
            ('LAYER5', (15, 0, 18), (1185, 60, 24)),           # trilho de baixo (6 mm)
            ('LAYER6', (15, 0, 1298), (1185, 80, 1338)),       # trilho de cima
            ('LAYER7', (16, 7, 26), (616, 30, 1320)),          # quadros de 23
            ('LAYER8', (599, 37, 26), (1184, 60, 1320)),
            ('LAYER9', (21, 13, 32), (609, 18, 1314)),         # vidro de 5
        ]
        cores = {c: 7 for c, _l, _h in caixas}
        cores.update(LAYER5=253, LAYER6=253, LAYER7=254, LAYER8=254, LAYER9=254)
        modulos, info = self.importar('Despenseiros.dxf', caixas, cores)
        conj, = modulos
        self.assertEqual(info['correr'], 1, info)
        # o trilho de 6 mm passava como chapa: agora e' ferragem e sai
        self.assertEqual(sorted(round(c.chapa_espessura_mm) for c in
                                addon.modulos._chapas_do_conjunto(conj)), [15, 15, 15, 15])
        grupo, = addon.portas._portas_do_conjunto(conj)
        p = dict(grupo['porta_parametros'])
        self.assertEqual((p['abertura'], p['folhas'], p['folha']), ('CORRER', 2, 'QUADRO'))
        for folha in addon.portas._folhas_portas(grupo):
            self.assertAlmostEqual(folha.chapa_espessura_mm, 23.0, places=3)
            self.assertIn('chapa_quadro_mm', folha)

    def test_promob_travessas_do_topo_viram_dependentes(self):
        caixas = self.CORPO_400[:3] + [
            ('LAYER4', (15, 15, 685), (385, 85, 700)),          # travessa da frente
            ('LAYER5', (15, 495, 685), (385, 565, 700)),        # e a de tras
        ]
        modulos, _info = self.importar('Balcoes.dxf', caixas, {c: 7 for c, _l, _h in caixas})
        conj, = modulos
        lados = sorted(t[addon.modulos.CHAVE_LADO_TRAVESSA]
                       for t in addon.modulos.travessas_do_modulo(conj))
        self.assertEqual(lados, ['FRENTE', 'TRAS'])
        # a travessa refeita pela caixa: entre as laterais, E do modulo
        for t in addon.modulos.travessas_do_modulo(conj):
            self.assertAlmostEqual(t.chapa_largura_mm, 370.0, places=1)
            self.assertAlmostEqual(t.chapa_espessura_mm, 15.0, places=1)
        # o modulo continua 400 x 700 (sem crescer pela travessa)
        self.assertAlmostEqual(conj.conj_largura_mm, 400.0, places=1)
        self.assertAlmostEqual(conj.conj_altura_mm, 700.0, places=1)

    def test_promob_vao_sem_chapa_entre_gavetas_e_porta(self):
        # gavetas embaixo de uma basculante, sem travessa entre elas: o
        # vao das gavetas para na frente delas (menos a cobertura dos
        # lados), nao sobe ate' o tampo (`promob.vao_atras`)
        P = addon.promob
        corpo = [P.peca(None, (0, 15, 0), (15, 565, 1356), 0),
                 P.peca(None, (785, 15, 0), (800, 565, 1356), 0),
                 P.peca(None, (15, 15, 3), (785, 565, 18), 2),
                 P.peca(None, (15, 15, 1338), (785, 565, 1353), 2)]
        pilha = {'lo': [5, 0, 13], 'hi': [795, 15, 1007]}
        x0, x1, z0, z1 = P.vao_atras(corpo, pilha, 15.0, 565.0)
        self.assertEqual((x0, x1, z0), (15, 785, 18))
        self.assertAlmostEqual(z1, 1007 - 10.0, places=3)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestImportacao)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de importacao')
