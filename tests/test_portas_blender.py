"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_portas_blender.py"""
import math
import os
import sys
import tempfile
import unittest

import bpy
import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon


def parametros(**alteracoes):
    p = dict(abertura='GIRO', folhas=1, dobradica='RETA',
             espessura_mm=18.0, lateral_mm=18.0, folga_mm=0.0,
             entre_folhas_mm=2.0, afastamento_mm=0.0,
             recuo_embutida_mm=0.0, recuo_correr_mm=30.0,
             sobreposicao_mm=20.0, entre_planos_mm=2.0)
    p.update(alteracoes)
    return p


class TestPortas(unittest.TestCase):
    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        # Este script usa somente a cena descartavel de --factory-startup.
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def pontos(self, pontos=((0, -0.15, 0), (0.6, -0.15, 0.8)), separados=False,
               pai=None):
        objetos = []
        for coords in ([[p] for p in pontos] if separados else [pontos]):
            malha = bpy.data.meshes.new('VerticesTeste')
            malha.from_pydata(coords, [], [])
            obj = bpy.data.objects.new('VaoTeste', malha)
            bpy.context.collection.objects.link(obj)
            obj.parent = pai
            obj.select_set(True)
            objetos.append(obj)
        bpy.context.view_layer.objects.active = objetos[0]
        bpy.context.view_layer.update()
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        return objetos

    def criar(self, **kwargs):
        self.pontos()
        resultado = bpy.ops.object.cabinet_portas('EXEC_DEFAULT', **kwargs)
        self.assertEqual(resultado, {'FINISHED'})
        return bpy.context.object

    def test_coberturas_e_profundidades(self):
        for dobradica, cobertura, z in [('RETA', 18, 9), ('CURVA', 9, 9),
                                      ('SUPER_CURVA', 0, -9)]:
            for abertura in ('GIRO', 'BASCULANTE'):
                with self.subTest(dobradica=dobradica, abertura=abertura):
                    folha = addon._calcular_folhas_portas(
                        600, 800, parametros(dobradica=dobradica, abertura=abertura))[0]
                    self.assertEqual(folha[:3], (600 + 2 * cobertura,
                                                800 + 2 * cobertura, 18))
                    self.assertEqual(folha[3], (300, 400, z))

    def test_giro_duplo_fecha_perimetro(self):
        folhas = addon._calcular_folhas_portas(600, 800, parametros(folhas=2))
        l = folhas[0][0]
        self.assertEqual(l, 317)
        self.assertEqual(folhas[0][3][0] - l / 2, -18)
        self.assertEqual(folhas[-1][3][0] + l / 2, 618)
        self.assertEqual(folhas[1][3][0] - folhas[0][3][0] - l, 2)

    def test_limites_no_calculo(self):
        for abertura, limite in addon.LIMITES_FOLHAS.items():
            for n in range(0, 6):
                with self.subTest(abertura=abertura, folhas=n):
                    if 1 <= n <= limite:
                        self.assertEqual(len(addon._calcular_folhas_portas(
                            600, 800, parametros(abertura=abertura, folhas=n))), n)
                    else:
                        with self.assertRaises(ValueError):
                            addon._calcular_folhas_portas(
                                600, 800, parametros(abertura=abertura, folhas=n))

    def test_correr_planos_sem_colisao_e_recuo(self):
        for n in range(1, 5):
            folhas = addon._calcular_folhas_portas(
                600, 800, parametros(abertura='CORRER', folhas=n))
            self.assertAlmostEqual(folhas[0][3][0] - folhas[0][0] / 2, 0)
            self.assertAlmostEqual(folhas[-1][3][0] + folhas[-1][0] / 2, 600)
            for i, (l, a, e, centro) in enumerate(folhas):
                self.assertEqual(centro[2] + e / 2, -30 - (i % 2) * 20)
                if i:
                    anterior = folhas[i - 1]
                    self.assertAlmostEqual(anterior[3][0] + l / 2 -
                                           (centro[0] - l / 2), 20)
                if i >= 2:
                    self.assertGreaterEqual(centro[0] - l / 2,
                                            folhas[i - 2][3][0] + l / 2)

    def test_medidas_invalidas(self):
        for alteracao in [dict(folga_mm=500), dict(entre_folhas_mm=1000, folhas=2),
                          dict(dobradica='ESCOLHER'), dict(espessura_mm=17),
                          dict(folga_mm=float('nan')),
                          dict(abertura='CORRER', recuo_correr_mm=0),
                          dict(abertura='CORRER', folhas=4, sobreposicao_mm=200)]:
            with self.subTest(alteracao=alteracao), self.assertRaises(ValueError):
                addon._calcular_folhas_portas(600, 800, parametros(**alteracao))

    def test_folgas_e_afastamentos(self):
        l, a, e, centro = addon._calcular_folhas_portas(
            600, 800, parametros(folga_mm=2, afastamento_mm=3))[0]
        self.assertEqual((l, a, centro[2] - e / 2), (632, 832, 3))
        folha = addon._calcular_folhas_portas(
            600, 800, parametros(dobradica='SUPER_CURVA', recuo_embutida_mm=5))[0]
        self.assertEqual(folha[3][2] + folha[2] / 2, -5)

    def test_ordem_dos_vertices_e_faces(self):
        for frente in ('NEG_Y', 'POS_Y', 'NEG_X', 'POS_X'):
            a, b = ((1, 2, 3), (1.6, 2, 3.8)) if frente.endswith('Y') else (
                (1, 2, 3), (1, 2.6, 3.8))
            l, h, matriz = addon._mapear_vao_portas(a, b, Matrix.Identity(3), frente)
            l2, h2, matriz2 = addon._mapear_vao_portas(b, a, Matrix.Identity(3), frente)
            self.assertAlmostEqual(l, 600, places=3)
            self.assertAlmostEqual(h, 800, places=3)
            self.assertEqual((l, h, matriz), (l2, h2, matriz2))
            self.assertAlmostEqual(matriz.determinant(), 1)

    def test_vao_degenerado_ou_fora_do_plano(self):
        for ponto in [(0, 0, 0), (0, 0, 0.8), (0.6, 0, 0), (0.6, 0.1, 0.8)]:
            with self.assertRaises(ValueError):
                addon._mapear_vao_portas((0, 0, 0), ponto, Matrix.Identity(3), 'NEG_Y')

    def test_captura_bmesh_de_duas_chapas(self):
        self.pontos(separados=True)
        a, b, ref, pai = addon._capturar_vertices_portas(bpy.context)
        l, h, _ = addon._mapear_vao_portas(a, b, ref, 'NEG_Y')
        self.assertAlmostEqual(l, 600, places=3)
        self.assertAlmostEqual(h, 800, places=3)
        self.assertIsNone(pai)

    def test_contagem_invalida_preserva_cena_e_modo(self):
        for n in (1, 3):
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            objetos = self.pontos(pontos=[(i, 0, i) for i in range(n)])
            antes = set(bpy.data.objects.keys())
            self.assertEqual(bpy.ops.object.cabinet_portas(dobradica='RETA'), {'CANCELLED'})
            self.assertEqual(set(bpy.data.objects.keys()), antes)
            self.assertEqual(bpy.context.mode, 'EDIT_MESH')
            self.assertEqual(sum(v.select for v in bmesh.from_edit_mesh(objetos[0].data).verts), n)

    def test_dobradica_obrigatoria(self):
        self.pontos()
        antes = len(bpy.data.objects)
        self.assertEqual(bpy.ops.object.cabinet_portas(dobradica='ESCOLHER'), {'CANCELLED'})
        self.assertEqual(len(bpy.data.objects), antes)
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')

    def test_malhas_fechadas_sem_ferragens(self):
        grupo = self.criar(abertura='CORRER', folhas=4)
        folhas = addon._folhas_portas(grupo)
        self.assertEqual(len(grupo.children), 4)
        self.assertEqual(len(bpy.data.objects), 6)  # vao, grupo e 4 solidos
        for folha in folhas:
            self.assertEqual(len(folha.data.vertices), 8)
            self.assertEqual(len(folha.data.polygons), 6)
            self.assertFalse(folha.modifiers)
            bm = bmesh.new()
            bm.from_mesh(folha.data)
            self.assertTrue(all(e.is_manifold for e in bm.edges))
            self.assertGreater(bm.calc_volume(signed=True), 0)
            bm.free()
        addon.normalizar_chapas()
        addon.absorver_conjuntos()
        self.assertEqual(len(grupo.children), 4)
        self.assertEqual(len(addon.familia_de(folhas[0])), 5)

    def test_posicao_em_mundo_e_origem(self):
        grupo = self.criar(dobradica='RETA')
        folha = addon._folhas_portas(grupo)[0]
        vertices = [folha.matrix_world @ v.co for v in folha.data.vertices]
        self.assertAlmostEqual(min(v.x for v in vertices), -0.018, places=6)
        self.assertAlmostEqual(max(v.x for v in vertices), 0.618, places=6)
        self.assertAlmostEqual(min(v.z for v in vertices), -0.018, places=6)
        self.assertAlmostEqual(max(v.z for v in vertices), 0.818, places=6)
        self.assertAlmostEqual(min(v.y for v in vertices), -0.168, places=6)
        self.assertAlmostEqual(max(v.y for v in vertices), -0.15, places=6)
        self.assertLess((grupo.matrix_world.translation - Vector((0, -0.15, 0))).length, 1e-6)

    def test_pai_rotacionado_escalado_e_transladado(self):
        pai = bpy.data.objects.new('Modulo', None)
        bpy.context.collection.objects.link(pai)
        pai.location = (1, 2, 3)
        pai.rotation_euler = (0.2, -0.1, math.radians(37))
        pai.scale = (2, 1, 1.5)
        bpy.context.view_layer.update()
        self.pontos(separados=True, pai=pai)
        a, b, ref, capturado = addon._capturar_vertices_portas(bpy.context)
        self.assertEqual(capturado, pai)
        l, h, _ = addon._mapear_vao_portas(a, b, ref, 'NEG_Y')
        self.assertAlmostEqual(l, 1200, places=2)
        self.assertAlmostEqual(h, 1200, places=2)
        self.assertEqual(bpy.ops.object.cabinet_portas(dobradica='SUPER_CURVA'), {'FINISHED'})
        grupo = bpy.context.object
        folha = addon._folhas_portas(grupo)[0]
        self.assertEqual(grupo.parent, pai)
        self.assertAlmostEqual((folha.matrix_world.to_3x3().col[2]).length, 1, places=5)
        self.assertAlmostEqual(folha.chapa_espessura_mm, 18)
        antes = folha.matrix_world.translation.copy()
        pai.location.x += 1
        bpy.context.view_layer.update()
        self.assertAlmostEqual(folha.matrix_world.translation.x - antes.x, 1, places=5)

    def test_objeto_rotacionado_sem_pai(self):
        objetos = self.pontos()
        bpy.ops.object.mode_set(mode='OBJECT')
        objetos[0].rotation_euler.z = math.radians(45)
        objetos[0].location = (2, 3, 4)
        bpy.context.view_layer.update()
        bpy.ops.object.mode_set(mode='EDIT')
        self.assertEqual(bpy.ops.object.cabinet_portas(
            orientacao='ATIVO', dobradica='SUPER_CURVA'), {'FINISHED'})
        grupo = bpy.context.object
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], 600, places=2)
        self.assertAlmostEqual(grupo['porta_vao_altura_mm'], 800, places=2)

    def test_parametros_sobrevivem_arquivo_blend(self):
        grupo = self.criar(abertura='CORRER', folhas=3, recuo_correr_mm=45)
        params = dict(grupo['porta_parametros'])
        folhas = addon._folhas_portas(grupo)
        with tempfile.TemporaryDirectory(prefix='cabinet_portas_teste_') as pasta:
            arquivo = os.path.join(pasta, 'portas.blend')
            bpy.data.libraries.write(arquivo, {grupo, *folhas})
            with bpy.data.libraries.load(arquivo, link=False) as (origem, destino):
                destino.objects = origem.objects
            copias = destino.objects
        novo = next(o for o in copias if addon.MARCA_PORTAS in o)
        self.assertEqual(dict(novo['porta_parametros']), params)
        self.assertEqual(len(addon._folhas_portas(novo)), 3)
        self.assertAlmostEqual(novo['porta_vao_largura_mm'], 600, places=3)

    def test_malha_compartilhada_nao_altera_outra_porta(self):
        grupo = self.criar(dobradica='RETA')
        primeira = addon._folhas_portas(grupo)[0]
        copia = primeira.copy()
        bpy.context.collection.objects.link(copia)
        copia.parent = None
        malha_original = copia.data
        vertices = [v.co.copy() for v in malha_original.vertices]
        self.assertEqual(bpy.ops.object.cabinet_portas(
            editar=True, grupo_nome=grupo.name, dobradica='SUPER_CURVA'), {'FINISHED'})
        self.assertNotEqual(primeira.data, malha_original)
        self.assertEqual([v.co for v in copia.data.vertices], vertices)

    def test_edicao_reutiliza_materiais_e_remove_somente_folhas(self):
        grupo = self.criar(abertura='CORRER', folhas=4)
        primeira = addon._folhas_portas(grupo)[0]
        material = bpy.data.materials.new('MadeiraTeste')
        primeira.data.materials.append(material)
        extra = bpy.data.objects.new('FilhoDoUsuario', None)
        bpy.context.collection.objects.link(extra)
        extra.parent = grupo
        matriz = grupo.matrix_world.copy()
        resultado = bpy.ops.object.cabinet_portas(editar=True, grupo_nome=grupo.name,
                                                abertura='BASCULANTE', folhas=1,
                                                dobradica='CURVA')
        self.assertEqual(resultado, {'FINISHED'})
        self.assertEqual(addon._folhas_portas(grupo), [primeira])
        self.assertEqual(primeira.data.materials[0], material)
        self.assertEqual(extra.parent, grupo)
        self.assertEqual(grupo.matrix_world, matriz)
        self.assertEqual(grupo['porta_parametros']['dobradica'], 'CURVA')

    def test_edicao_invalida_nao_altera_grupo(self):
        grupo = self.criar(dobradica='RETA')
        original = dict(grupo['porta_parametros'])
        primeira = addon._folhas_portas(grupo)[0]
        coords = [v.co.copy() for v in primeira.data.vertices]
        self.assertEqual(bpy.ops.object.cabinet_portas(
            editar=True, grupo_nome=grupo.name, dobradica='RETA', folga_mm=1000), {'CANCELLED'})
        self.assertEqual(dict(grupo['porta_parametros']), original)
        self.assertEqual([v.co for v in primeira.data.vertices], coords)

    def test_vao_apanhado_em_modo_objeto_dispensa_edit_mode(self):
        # Caminho do apanhador (`cabinet_apanhar_vao`): os pontos
        # chegam prontos e o Modo Edicao nao entra na historia.
        objetos = self.pontos(separados=True)
        bpy.ops.object.mode_set(mode='OBJECT')
        self.assertEqual(bpy.context.mode, 'OBJECT')

        a = objetos[0].matrix_world @ objetos[0].data.vertices[0].co
        b = objetos[1].matrix_world @ objetos[1].data.vertices[0].co
        referencia, pai = addon._referencia_do_par(objetos[0], objetos[1])
        resultado = bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            referencia=tuple(v for linha in referencia for v in linha),
            pai_nome=pai.name if pai is not None else '',
            dobradica='RETA')
        self.assertEqual(resultado, {'FINISHED'})
        grupo = addon._grupo_portas(bpy.context.object)
        self.assertIsNotNone(grupo)
        folha = addon._folhas_portas(grupo)[0]
        # 600 x 800 de vao, dobradica reta: cobre a lateral dos dois
        # lados. Nos eixos LOCAIS da folha, X=largura, Y=altura e
        # Z=espessura -- a altura nao e' o Z.
        self.assertAlmostEqual(folha.dimensions.x, 0.636, places=4)
        self.assertAlmostEqual(folha.dimensions.y, 0.836, places=4)
        self.assertAlmostEqual(folha.dimensions.z, 0.018, places=4)

    def test_referencia_do_par_usa_o_ancestral_comum(self):
        # A mesma regra serve ao Modo Edicao e ao apanhador; se as duas
        # divergirem, o vao sai girado num dos caminhos.
        bpy.ops.object.empty_add()
        empty = bpy.context.object
        empty.rotation_euler = (0.0, 0.0, math.radians(30))
        objetos = self.pontos(separados=True, pai=empty)
        bpy.ops.object.mode_set(mode='OBJECT')
        referencia, pai = addon._referencia_do_par(objetos[0], objetos[1])
        self.assertEqual(pai, empty)
        esperado = pai.matrix_world.to_quaternion().to_matrix()
        for linha_a, linha_b in zip(referencia, esperado):
            for va, vb in zip(linha_a, linha_b):
                self.assertAlmostEqual(va, vb, places=6)

    def test_apanhador_so_roda_em_modo_objeto(self):
        self.pontos()
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        self.assertFalse(addon.OBJECT_OT_apanhar_vao_portas.poll(bpy.context))
        bpy.ops.object.mode_set(mode='OBJECT')
        self.assertTrue(addon.OBJECT_OT_apanhar_vao_portas.poll(bpy.context))

    def test_ima_enxerga_os_vertices_em_mundo(self):
        objetos = self.pontos(separados=True)
        bpy.ops.object.mode_set(mode='OBJECT')
        alvos = dict(addon._alvos_do_ima(bpy.context))
        for obj in objetos:
            self.assertIn(obj, alvos)
            esperado = obj.matrix_world @ obj.data.vertices[0].co
            self.assertAlmostEqual((alvos[obj][0] - esperado).length, 0.0,
                                   places=6)

    def test_operador_limita_basculante_e_giro(self):
        grupo = self.criar(abertura='BASCULANTE', folhas=4, dobradica='RETA')
        self.assertEqual(len(addon._folhas_portas(grupo)), 1)
        self.assertEqual(bpy.ops.object.cabinet_portas(
            editar=True, grupo_nome=grupo.name, abertura='GIRO', folhas=4,
            dobradica='RETA'), {'FINISHED'})
        self.assertEqual(len(addon._folhas_portas(grupo)), 2)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestPortas)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
addon.register()
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de portas')
