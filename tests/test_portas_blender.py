"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_portas_blender.py"""
import math
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

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



def relativo(bloco):
    """O bloco com y relativo ao 1o widget: na aba Portas ele desce para
    caber o "Criar Portas" no topo (Epico 2.3); o CONTEUDO e as posicoes
    entre os campos continuam identicos."""
    if not bloco:
        return bloco
    y0 = bloco[0][1]
    return [(b[0], b[1] - y0) + tuple(b[2:]) for b in bloco]


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
                          dict(dobradica='ESCOLHER'), dict(espessura_mm=0),
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

    def nicho(self):
        """Modulo de verdade, com laterais, base e tampo."""
        bpy.ops.object.cabinet_criar_nicho()
        # O nicho cria as chapas soltas; o Empty do conjunto, com as
        # medidas parametricas, vem do agrupar.
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar()
        conj = next(o for o in bpy.data.objects
                    if addon.MARCA_CONJUNTO in o)
        bpy.context.view_layer.update()
        return conj

    def porta_no_nicho(self, conj):
        """Cria a porta pelo vao interno do modulo (cenario 2)."""
        L = conj.conj_largura_mm
        A = conj.conj_altura_mm
        P = conj.conj_profundidade_mm
        E = conj.conj_espessura_mm
        local_a = Vector((-L / 2 + E, -P / 2, E)) / 1000.0
        local_b = Vector((L / 2 - E, -P / 2, A - E)) / 1000.0
        a = conj.matrix_world @ local_a
        b = conj.matrix_world @ local_b
        chapa = next(o for o in addon._chapas_do_conjunto(conj))
        self.assertEqual(addon._modulo_da_chapa(chapa), conj)
        resultado = bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            referencia=tuple(
                v for linha in conj.matrix_world.to_quaternion().to_matrix()
                for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name,
            frente='NEG_Y', dobradica='RETA', folhas=2)
        self.assertEqual(resultado, {'FINISHED'})
        # Com o vinculo, quem fica ativo e' o MODULO (etapa 3), entao o
        # grupo vem pela lista de portas dele.
        self.assertEqual(bpy.context.object, conj)
        grupos = addon._portas_do_conjunto(conj)
        self.assertEqual(len(grupos), 1)
        return grupos[0]

    def test_modulo_da_chapa_sobe_ate_o_conjunto(self):
        conj = self.nicho()
        for chapa in addon._chapas_do_conjunto(conj):
            self.assertEqual(addon._modulo_da_chapa(chapa), conj)
        bpy.ops.mesh.primitive_cube_add()
        self.assertIsNone(addon._modulo_da_chapa(bpy.context.object))

    def test_porta_vinculada_grava_folgas_em_espessuras(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        self.assertEqual(grupo[addon.CHAVE_MODULO_PORTA], conj.name)
        # o vao encosta nas quatro chapas: uma espessura por lado
        for folga in grupo[addon.CHAVE_FOLGAS_PORTA]:
            self.assertAlmostEqual(folga, 1.0, places=4)

    def corrente(self):
        """Estado da corrente porta/modulo (o operador saiu da gaveta,
        segue no F3)."""
        return 'LINKED' if addon._corrente_porta_ligada(bpy.context) else 'UNLINKED'

    def test_corrente_decide_porta_no_modulo_ou_no_mundo(self):
        s = bpy.context.scene
        self.addCleanup(s.property_unset, 'porta_associar')
        # sem porta ativa: a corrente e' a escolha para a proxima porta
        bpy.ops.object.select_all(action='DESELECT')
        self.assertEqual(self.corrente(), 'LINKED')
        self.assertEqual(bpy.ops.object.cabinet_corrente_porta(), {'FINISHED'})
        self.assertFalse(s.porta_associar)
        self.assertEqual(self.corrente(), 'UNLINKED')
        apanhador = SimpleNamespace(_grupo_alvo='')
        classe = addon.OBJECT_OT_apanhar_vao_portas
        self.assertFalse(classe._associar(apanhador, bpy.context))
        s.porta_associar = True
        self.assertTrue(classe._associar(apanhador, bpy.context))
        # porta ATIVA: a corrente mostra e troca o estado dela
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        bpy.context.view_layer.objects.active = grupo
        self.assertEqual(self.corrente(), 'LINKED')
        mundo = grupo.matrix_world.copy()
        self.assertEqual(bpy.ops.object.cabinet_corrente_porta(), {'FINISHED'})
        self.assertNotIn(addon.CHAVE_MODULO_PORTA, grupo)
        self.assertIsNone(grupo.parent)
        self.assertTrue(all(abs(a - b) < 1e-6 for la, lb in
                            zip(mundo, grupo.matrix_world) for a, b in zip(la, lb)))
        self.assertEqual(self.corrente(), 'UNLINKED')
        self.assertTrue(s.porta_associar)          # a da cena nao mexeu
        # solta, nao acompanha o modulo
        largura = addon._folhas_portas(grupo)[0].chapa_largura_mm
        conj.conj_largura_mm += 200.0
        bpy.context.view_layer.update()
        self.assertEqual(addon._folhas_portas(grupo)[0].chapa_largura_mm, largura)
        # religar volta para o mesmo modulo, mesmo sem ele selecionado
        bpy.context.view_layer.objects.active = grupo
        self.assertEqual(bpy.ops.object.cabinet_corrente_porta(), {'FINISHED'})
        self.assertEqual(grupo[addon.CHAVE_MODULO_PORTA], conj.name)
        self.assertEqual(grupo.parent, conj)
        self.assertEqual(self.corrente(), 'LINKED')

    def test_porta_acompanha_a_largura_do_modulo(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        antes = grupo['porta_vao_largura_mm']
        conj.conj_largura_mm = conj.conj_largura_mm + 400.0
        bpy.context.view_layer.update()
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], antes + 400.0,
                               places=3)
        folha = addon._folhas_portas(grupo)[0]
        self.assertGreater(folha.chapa_largura_mm, 0.0)

    def test_porta_acompanha_a_altura_do_modulo(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        antes = grupo['porta_vao_altura_mm']
        conj.conj_altura_mm = conj.conj_altura_mm + 300.0
        bpy.context.view_layer.update()
        self.assertAlmostEqual(grupo['porta_vao_altura_mm'], antes + 300.0,
                               places=3)

    def test_porta_acompanha_a_espessura_das_chapas(self):
        # Folga guardada em espessuras: chapa mais grossa aperta o vao.
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        antes = grupo['porta_vao_largura_mm']
        e_antes = conj.conj_espessura_mm
        conj.conj_espessura_mm = 30.0
        bpy.context.view_layer.update()
        esperado = antes - 2.0 * (30.0 - e_antes)
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], esperado,
                               places=3)

    def test_porta_sem_modulo_nao_ganha_vinculo(self):
        # Cenario 1: objeto generico, nenhum vinculo a manter.
        objetos = self.pontos(separados=True)
        bpy.ops.object.mode_set(mode='OBJECT')
        a = objetos[0].matrix_world @ objetos[0].data.vertices[0].co
        b = objetos[1].matrix_world @ objetos[1].data.vertices[0].co
        bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            dobradica='RETA')
        grupo = addon._grupo_portas(bpy.context.object)
        self.assertNotIn(addon.CHAVE_MODULO_PORTA, grupo)

    def test_operador_limita_basculante_e_giro(self):
        grupo = self.criar(abertura='BASCULANTE', folhas=4, dobradica='RETA')
        self.assertEqual(len(addon._folhas_portas(grupo)), 1)
        self.assertEqual(bpy.ops.object.cabinet_portas(
            editar=True, grupo_nome=grupo.name, abertura='GIRO', folhas=4,
            dobradica='RETA'), {'FINISHED'})
        self.assertEqual(len(addon._folhas_portas(grupo)), 2)

    def criar_por_pontos(self, conj, a, b, objetos=(None, None), **opcoes):
        anteriores = set(addon._portas_do_conjunto(conj))
        ref = conj.matrix_world.to_quaternion().to_matrix()
        p = dict(frente='NEG_Y', dobradica='RETA', folhas=2)
        p.update(opcoes)
        resultado = bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True,
            ponto_a=conj.matrix_world @ Vector(a),
            ponto_b=conj.matrix_world @ Vector(b),
            referencia=tuple(v for linha in ref for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name,
            objeto_a_nome=objetos[0].name if objetos[0] else '',
            objeto_b_nome=objetos[1].name if objetos[1] else '', **p)
        self.assertEqual(resultado, {'FINISHED'})
        return next(g for g in addon._portas_do_conjunto(conj) if g not in anteriores)

    def limites_folhas(self, conj, grupo):
        inversa = conj.matrix_world.inverted()
        pontos = [inversa @ (f.matrix_world @ v.co)
                  for f in addon._folhas_portas(grupo) for v in f.data.vertices]
        return ([min(v[i] for v in pontos) for i in range(3)],
                [max(v[i] for v in pontos) for i in range(3)])

    def lateral_esquerda(self, conj):
        return min((c for c in addon._chapas_do_conjunto(conj)
                    if abs(addon._eixos(c)[2].x) > 0.9),
                   key=lambda c: (conj.matrix_world.inverted()
                                  @ c.matrix_world.translation).x)

    def test_ima_oferece_o_meio_da_espessura(self):
        # Porta que cobre METADE de uma chapa (pedido do usuario): ja' na
        # diagonal, o ima pega o meio das arestas de espessura.
        conj = self.nicho()
        L, A, P, E = addon._caixa_do_modulo(conj)
        lateral = self.lateral_esquerda(conj)
        meio = conj.matrix_world @ (Vector((-L / 2 + E / 2, -P / 2, A)) / 1000.0)
        alvos = dict(addon._alvos_do_ima(bpy.context))
        self.assertLess(min((p - meio).length for p in alvos[lateral]), 1e-6)
        # o vertice continua primeiro (o meio vem depois)
        self.assertEqual(len(alvos[lateral]), 8 + 4)

    def test_porta_cobre_meia_chapa_marcada_no_meio(self):
        conj = self.nicho()
        L, A, P, E = addon._caixa_do_modulo(conj)
        lateral = self.lateral_esquerda(conj)
        a = conj.matrix_world @ (Vector((-L / 2 + E / 2, -P / 2, A)) / 1000.0)
        b = conj.matrix_world @ (Vector((L / 2, -P / 2, 0)) / 1000.0)
        self.assertEqual(bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            referencia=tuple(v for linha in
                             conj.matrix_world.to_quaternion().to_matrix()
                             for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name,
            objeto_a_nome=lateral.name, frente='NEG_Y', dobradica='RETA',
            folhas=1, folga_mm=0), {'FINISHED'})
        grupo = addon._portas_do_conjunto(conj)[0]
        p = grupo['porta_parametros']
        self.assertEqual(p['cobertura_esq_e'], 0.5)
        self.assertEqual([k for k in addon.COBERTURAS_LADOS if k in p],
                         ['cobertura_esq_e'])
        lo, hi = self.limites_folhas(conj, grupo)
        # esquerda: no MEIO da lateral; o resto cobre a chapa inteira (Reta)
        self.assertAlmostEqual(lo[0] * 1000, -L / 2 + E / 2, places=3)
        self.assertAlmostEqual(hi[0] * 1000, L / 2, places=3)
        self.assertAlmostEqual(lo[2] * 1000, 0.0, places=3)
        self.assertAlmostEqual(hi[2] * 1000, A, places=3)
        # redimensionar o modulo mantem a borda no meio da lateral
        conj.conj_largura_mm = L + 100
        bpy.context.view_layer.update()
        lo, hi = self.limites_folhas(conj, grupo)
        self.assertAlmostEqual(lo[0] * 1000, -(L + 100) / 2 + E / 2, places=3)
        self.assertAlmostEqual(hi[0] * 1000, (L + 100) / 2, places=3)
        # meia cobertura e' fixa: a Curva ja' cobre meia, nada muda nela
        p = dict(grupo['porta_parametros'], dobradica='CURVA')
        self.assertEqual(addon._inicios_porta(p), [-E / 2] * 4)
        # a meia e' do VAO: fica mesmo se a dobradica mudar
        p = dict(p, dobradica='SUPER_CURVA')
        self.assertEqual(addon._inicios_porta(p), [-E / 2, 0.0, 0.0, 0.0])

    def porta_por_quatro_cliques(self, conj, p1, p2, p3, p4, **extras):
        mundo = [conj.matrix_world @ (Vector(p) / 1000.0)
                 for p in (p1, p2, p3, p4)]
        chapa = self.lateral_esquerda(conj)
        self.assertEqual(bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=mundo[1],
            ponto_b=mundo[2], quatro_pontos=True, porta_a=mundo[0],
            porta_b=mundo[3],
            referencia=tuple(v for linha in
                             conj.matrix_world.to_quaternion().to_matrix()
                             for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name,
            objeto_a_nome=chapa.name, frente='NEG_Y', folga_mm=0,
            **extras), {'FINISHED'})
        return addon._portas_do_conjunto(conj)[0]

    def test_quatro_cliques_definem_a_porta_lado_a_lado(self):
        conj = self.nicho()
        L, A, P, E = addon._caixa_do_modulo(conj)
        y = -P / 2
        # esq/cima/baixo: chapa inteira; dir: metade da lateral
        grupo = self.porta_por_quatro_cliques(
            conj, (-L / 2, y, A), (-L / 2 + E, y, A - E), (L / 2 - E, y, E),
            (L / 2 - E / 2, y, 0), dobradica='RETA', folhas=1)
        p = grupo['porta_parametros']
        self.assertEqual([p[k] for k in addon.COBERTURAS_LADOS],
                         [1.0, 0.5, 1.0, 1.0])
        lo, hi = self.limites_folhas(conj, grupo)
        self.assertAlmostEqual(lo[0] * 1000, -L / 2, places=3)
        self.assertAlmostEqual(hi[0] * 1000, L / 2 - E / 2, places=3)
        self.assertAlmostEqual(lo[2] * 1000, 0.0, places=3)
        self.assertAlmostEqual(hi[2] * 1000, A, places=3)
        # acompanha o modulo
        conj.conj_largura_mm = L + 100
        bpy.context.view_layer.update()
        lo, hi = self.limites_folhas(conj, grupo)
        self.assertAlmostEqual(hi[0] * 1000, (L + 100) / 2 - E / 2, places=3)

    def test_quatro_cliques_com_porta_e_vao_no_mesmo_ponto(self):
        conj = self.nicho()
        L, A, P, E = addon._caixa_do_modulo(conj)
        y = -P / 2
        # 1 e 2 no MESMO ponto (quina de fora): vale a margem do par 3-4
        grupo = self.porta_por_quatro_cliques(
            conj, (-L / 2, y, A), (-L / 2, y, A), (L / 2 - E, y, E),
            (L / 2, y, 0), dobradica='RETA', folhas=1)
        p = grupo['porta_parametros']
        self.assertEqual([p[k] for k in addon.COBERTURAS_LADOS], [1.0] * 4)
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], L - 2 * E,
                               places=3)
        # os 4 no canto do vao: porta embutida, sem cobrir nada
        bpy.data.objects.remove(grupo, do_unlink=True)
        grupo = self.porta_por_quatro_cliques(
            conj, (-L / 2 + E, y, A - E), (-L / 2 + E, y, A - E),
            (L / 2 - E, y, E), (L / 2 - E, y, E),
            dobradica='SUPER_CURVA', folhas=1)
        p = grupo['porta_parametros']
        self.assertEqual([p[k] for k in addon.COBERTURAS_LADOS], [0.0] * 4)

    def test_cantos_da_porta_sao_os_4_cliques_e_refazem_a_porta(self):
        # Pedido do usuario: porta selecionada mostra os 4 pontos do
        # wizard; com Alt, mover um deles refaz a porta.
        conj = self.nicho()
        L, A, P, E = addon._caixa_do_modulo(conj)
        y = -P / 2
        cliques = [(-L / 2, y, A), (-L / 2 + E, y, A - E), (L / 2 - E, y, E),
                   (L / 2 - E / 2, y, 0)]
        grupo = self.porta_por_quatro_cliques(conj, *cliques,
                                              dobradica='RETA', folhas=1)
        mundo = [conj.matrix_world @ (Vector(p) / 1000.0) for p in cliques]
        for a, b in zip(addon._cantos_da_porta(grupo), mundo):
            self.assertLess((a - b).length, 1e-6)
        # canto 4 na quina de fora: a direita passa a cobrir a chapa toda
        novos = list(mundo)
        novos[3] = conj.matrix_world @ (Vector((L / 2, y, 0)) / 1000.0)
        self.assertEqual(addon._mover_cantos_porta(bpy.context, grupo, novos),
                         {'FINISHED'})
        p = grupo['porta_parametros']
        self.assertEqual([p[k] for k in addon.COBERTURAS_LADOS], [1.0] * 4)
        self.assertEqual(grupo[addon.CHAVE_MODULO_PORTA], conj.name)
        # a porta continua selecionada para seguir ajustando
        self.assertIn(grupo, addon._portas_com_cantos(bpy.context))
        # canto 1 no meio da lateral das dobradicas: a dobradica vira Curva
        novos[0] = conj.matrix_world @ (Vector((-L / 2 + E / 2, y, A)) / 1000.0)
        addon._mover_cantos_porta(bpy.context, grupo, novos)
        self.assertEqual(grupo['porta_parametros']['cobertura_esq_e'], 0.5)
        self.assertEqual(grupo['porta_parametros']['dobradica'], 'CURVA')
        # fora do padrao: pergunta (viewport) e "Nao" volta os cantos
        antigos = addon._cantos_da_porta(grupo)
        torto = list(antigos)
        torto[0] = conj.matrix_world @ (Vector((-L / 2 - 40, y, A)) / 1000.0)
        addon._aplicar_cantos_porta(bpy.context, grupo, torto, [None] * 4,
                                    antigos)
        pergunta = addon._pergunta_atual[0]
        self.assertEqual(pergunta['texto'], 'As medidas estao corretas?')
        self.assertFalse(pergunta['na_gaveta'])
        self.assertTrue(addon._lados_fora_do_padrao(
            addon._coberturas_da_porta(grupo)))
        bpy.ops.object.cabinet_responder_pergunta(opcao=1)
        self.assertEqual(grupo['porta_parametros']['cobertura_esq_e'], 0.5)
        # "Sim" nao mexe em nada
        antes = addon._cantos_da_porta(grupo)
        self.assertEqual(bpy.ops.object.cabinet_cantos_porta(
            grupo=grupo.name, manter=True), {'FINISHED'})
        for a, b in zip(antes, addon._cantos_da_porta(grupo)):
            self.assertLess((a - b).length, 1e-9)
        self.assertFalse(addon._lados_fora_do_padrao(
            addon._coberturas_da_porta(grupo)))

    def test_cantos_externos_equivalem_aos_internos_nas_quatro_faces(self):
        conj = self.nicho()
        conj.location = (2, -3, 1)
        conj.rotation_euler = (0.1, -0.2, 0.4)
        bpy.context.view_layer.update()
        L, A, P, E = addon._caixa_do_modulo(conj)
        for frente in ('NEG_Y', 'POS_Y', 'NEG_X', 'POS_X'):
            for dobradica in ('RETA', 'CURVA', 'SUPER_CURVA'):
                with self.subTest(frente=frente, dobradica=dobradica):
                    plano = (-1 if frente.startswith('NEG') else 1)
                    if frente.endswith('Y'):
                        a, b = (-L/2, plano*P/2, 0), (L/2, plano*P/2, A)
                    else:
                        a, b = (plano*L/2, -P/2, 0), (plano*L/2, P/2, A)
                    g = self.criar_por_pontos(conj, Vector(a)/1000, Vector(b)/1000,
                                             frente=frente, dobradica=dobradica)
                    self.assertAlmostEqual(g['porta_vao_largura_mm'],
                                           (L if frente.endswith('Y') else P) - 2*E, places=2)
                    self.assertAlmostEqual(g['porta_vao_altura_mm'], A-2*E, places=2)
                    for f in g[addon.CHAVE_FOLGAS_PORTA]:
                        self.assertAlmostEqual(f, 1, places=3)

    def test_canto_misto_nao_desconta_duas_vezes_a_espessura(self):
        conj = self.nicho()
        L, A, P, E = (v/1000 for v in addon._caixa_do_modulo(conj))
        g = self.criar_por_pontos(conj, (L/2-E, -P/2, A-E), (-L/2, -P/2, 0))
        lo, hi = self.limites_folhas(conj, g)
        for atual, esperado in ((lo[0], -L/2), (hi[0], L/2), (lo[2], 0), (hi[2], A)):
            self.assertAlmostEqual(atual, esperado, places=5)

    def duas_fileiras(self, inverter=False):
        conj = self.nicho()
        conj.conj_altura_mm = 1800
        L, A, P, E = (v/1000 for v in addon._caixa_do_modulo(conj))
        cima = self.criar_por_pontos(conj, (-L/2, -P/2, 0.7), (L/2, -P/2, A))
        folha = addon._folhas_portas(cima)[-1]
        inferior = self.limites_folhas(conj, cima)[0][2]
        a, b = (-L/2, -P/2, 0), (L/2, -P/2-0.018, inferior)
        chapa = addon._chapas_do_conjunto(conj)[0]
        objetos = (chapa, folha)
        if inverter:
            a, b, objetos = b, a, tuple(reversed(objetos))
        baixo = self.criar_por_pontos(conj, a, b, objetos)
        return conj, cima, baixo

    def test_apoio_em_porta_respeita_folga_e_plano_nas_duas_ordens(self):
        for inverter in (False, True):
            self.setUp()
            conj, cima, baixo = self.duas_fileiras(inverter)
            lo_c, hi_c = self.limites_folhas(conj, cima)
            lo_b, hi_b = self.limites_folhas(conj, baixo)
            self.assertAlmostEqual(lo_c[2] - hi_b[2], 0.002, places=5)
            self.assertAlmostEqual(lo_c[1], lo_b[1], places=5)
            self.assertAlmostEqual(hi_c[1], hi_b[1], places=5)
            self.assertAlmostEqual(lo_c[0], lo_b[0], places=5)
            self.assertAlmostEqual(hi_c[0], hi_b[0], places=5)
            self.assertIn('porta_ancora_3', baixo)

    def test_apoio_e_origem_acompanham_redimensionamento(self):
        conj, cima, baixo = self.duas_fileiras()
        # Forca a ordem alfabetica contraria a ordem das dependencias.
        cima.name, baixo.name = 'Z_superiores', 'A_inferiores'
        for prop, valor in (('conj_altura_mm', 2200), ('conj_largura_mm', 1000),
                            ('conj_profundidade_mm', 550), ('conj_espessura_mm', 30)):
            setattr(conj, prop, valor)
            bpy.context.view_layer.update()
            lo_c, hi_c = self.limites_folhas(conj, cima)
            lo_b, hi_b = self.limites_folhas(conj, baixo)
            self.assertAlmostEqual(lo_c[2] - hi_b[2], 0.002, places=5)
            self.assertAlmostEqual(lo_c[1], lo_b[1], places=5)
            self.assertAlmostEqual(lo_c[0], lo_b[0], places=5)
            self.assertAlmostEqual(hi_c[0], hi_b[0], places=5)

    def test_preview_preserva_arestas_e_duas_fileiras_reais(self):
        conj, cima, baixo = self.duas_fileiras()
        for modo in ('GRUPO', 'PORTA'):
            dims, vertices, arestas = addon._geometria_wireframe(conj, modo)
            alvos = addon._folhas_portas(cima) + addon._folhas_portas(baixo)
            if modo == 'GRUPO':
                alvos = addon._chapas_do_conjunto(conj) + alvos
            self.assertEqual(len(vertices), sum(len(o.data.vertices) for o in alvos))
            self.assertEqual(len(arestas), sum(len(o.data.edges) for o in alvos))
            alturas = sorted({round(v[2], 2) for v in vertices})
            self.assertGreaterEqual(len(alturas), 4)
            for i, j in arestas:
                self.assertGreater((Vector(vertices[i])-Vector(vertices[j])).length, 0)
        self.assertIsNone(addon._geometria_wireframe(conj, 'INDIVIDUAL'))

    def test_medidas_da_cena_sincronizam_modulo_e_portas(self):
        conj, cima, baixo = self.duas_fileiras()
        chapa = addon._chapas_do_conjunto(conj)[0]
        bpy.context.view_layer.objects.active = chapa
        chapa.chapa_modo = 'GRUPO'
        addon.sincronizar_grupo(bpy.context)
        bpy.context.scene.grupo_altura_mm = 2200
        self.assertAlmostEqual(conj.conj_altura_mm, 2200, places=3)
        lo_c, hi_c = self.limites_folhas(conj, cima)
        lo_b, hi_b = self.limites_folhas(conj, baixo)
        self.assertAlmostEqual(hi_c[2], 2.2, places=5)
        self.assertAlmostEqual(lo_c[2] - hi_b[2], 0.002, places=5)

    def test_cantos_externos_usam_a_malha_com_campo_antigo(self):
        conj = self.nicho()
        addon.redimensionar_grupo(addon._chapas_do_conjunto(conj), (600, 1200, 300))
        addon.reposicionar_origem(conj)
        self.assertAlmostEqual(conj.conj_altura_mm, 400)
        g = self.criar_por_pontos(conj, (-0.3, -0.15, 0), (0.3, -0.15, 1.2))
        self.assertAlmostEqual(g['porta_vao_altura_mm'], 1164, places=3)
        for folga in g[addon.CHAVE_FOLGAS_PORTA]:
            self.assertAlmostEqual(folga, 1, places=4)

    def test_apoio_lateral_e_reedicao_mantem_folga(self):
        conj = self.nicho()
        primeira = self.criar_por_pontos(conj, (-0.3, -0.15, 0), (0, -0.15, 0.4),
                                         folhas=1)
        folha = addon._folhas_portas(primeira)[0]
        borda = self.limites_folhas(conj, primeira)[1][0]
        segunda = self.criar_por_pontos(
            conj, (borda, -0.168, 0), (0.3, -0.15, 0.4),
            (folha, addon._chapas_do_conjunto(conj)[0]), folhas=1)
        self.assertAlmostEqual(self.limites_folhas(conj, segunda)[0][0] - borda,
                               0.002, places=5)
        for _ in range(2):
            bpy.ops.object.cabinet_portas(editar=True, grupo_nome=segunda.name,
                                          entre_folhas_mm=4)
            self.assertAlmostEqual(self.limites_folhas(conj, segunda)[0][0] - borda,
                                   0.004, places=5)

    def test_frente_automatica_nos_tres_eixos(self):
        # O eixo que nao varia na diagonal e' a normal; o lado sai do
        # centro do movel. Diagonal sem mudar Z = porta deitada.
        ref, centro = Matrix.Identity(3), (0, 0, 0.5)
        casos = [(((-0.3, -0.2, 0.1), (0.3, -0.2, 0.9)), 'NEG_Y'),
                 (((-0.3, 0.2, 0.1), (0.3, 0.2, 0.9)), 'POS_Y'),
                 (((0.3, -0.2, 0.1), (0.3, 0.2, 0.9)), 'POS_X'),
                 (((-0.3, -0.2, 1.0), (0.3, 0.2, 1.0)), 'POS_Z'),
                 (((-0.3, -0.2, 0.0), (0.3, 0.2, 0.0)), 'NEG_Z')]
        for (a, b), esperado in casos:
            with self.subTest(esperado=esperado):
                self.assertEqual(addon._frente_automatica(ref, a, b, centro),
                                 esperado)
        # Deitada, a largura corre pelo lado MAIOR da diagonal
        self.assertEqual(addon._largura_do_vao(ref, (0, 0, 1), (0.6, 0.4, 1)), 'X')
        self.assertEqual(addon._largura_do_vao(ref, (0, 0, 1), (0.4, 0.6, 1)), 'Y')

    def test_mapear_porta_deitada(self):
        for a, b in (((0, 0, 1), (0.6, 0.4, 1)), ((0, 0, 1), (0.4, 0.6, 1))):
            for frente, sinal in (('POS_Z', 1), ('NEG_Z', -1)):
                with self.subTest(b=b, frente=frente):
                    l, h, matriz = addon._mapear_vao_portas(
                        a, b, Matrix.Identity(3), frente)
                    self.assertAlmostEqual(l, 600, places=3)
                    self.assertAlmostEqual(h, 400, places=3)
                    self.assertAlmostEqual(matriz.determinant(), 1)
                    self.assertAlmostEqual(matriz.col[2].z, sinal)

    def porta_deitada(self, conj, z):
        L, A, P, E = (v / 1000 for v in addon._caixa_do_modulo(conj))
        chapa = addon._chapas_do_conjunto(conj)[0]
        return self.criar_por_pontos(
            conj, (-L / 2, -P / 2, z), (L / 2, P / 2, z), (chapa, chapa),
            frente='AUTO', folhas=1,
            centro=addon._centro_do_movel(chapa, chapa))

    def test_tampa_de_bau_nasce_em_cima_e_acompanha_o_modulo(self):
        conj = self.nicho()
        L, A, P, E = addon._caixa_do_modulo(conj)
        grupo = self.porta_deitada(conj, A / 1000)
        self.assertEqual(grupo['porta_frente'], 'POS_Z')
        largura, altura = max(L, P), min(L, P)
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], largura - 2 * E, places=2)
        self.assertAlmostEqual(grupo['porta_vao_altura_mm'], altura - 2 * E, places=2)
        lo, hi = self.limites_folhas(conj, grupo)
        # reta: cobre o tampo inteiro e fica por cima dele
        self.assertAlmostEqual(lo[2], A / 1000, places=5)
        self.assertAlmostEqual(hi[2], (A + E) / 1000, places=5)
        self.assertAlmostEqual(hi[0] - lo[0], L / 1000, places=5)
        self.assertAlmostEqual(hi[1] - lo[1], P / 1000, places=5)
        conj.conj_largura_mm = L + 200
        conj.conj_altura_mm = A + 100
        bpy.context.view_layer.update()
        lo, hi = self.limites_folhas(conj, grupo)
        self.assertAlmostEqual(hi[0] - lo[0], (L + 200) / 1000, places=5)
        self.assertAlmostEqual(lo[2], (A + 100) / 1000, places=5)

    def test_porta_na_base_aponta_para_baixo(self):
        conj = self.nicho()
        grupo = self.porta_deitada(conj, 0.0)
        self.assertEqual(grupo['porta_frente'], 'NEG_Z')
        lo, hi = self.limites_folhas(conj, grupo)
        self.assertAlmostEqual(hi[2], 0.0, places=5)
        self.assertLess(lo[2], 0.0)

    def test_lateral_e_porta_seguem_a_espessura_do_modulo(self):
        conj = self.nicho()
        conj.conj_espessura_mm = 15.0
        bpy.context.view_layer.update()
        grupo = self.porta_no_nicho(conj)
        self.assertEqual(grupo['porta_parametros']['lateral_mm'], 15.0)
        self.assertEqual(grupo['porta_parametros']['espessura_mm'], 15.0)
        # REGRESSAO: a lateral ficava com a espessura de quando a porta
        # nasceu; ao trocar a do modulo, a porta reta sobrava para fora.
        conj.conj_espessura_mm = 30.0
        bpy.context.view_layer.update()
        L, A, P, E = addon._caixa_do_modulo(conj)
        lo, hi = self.limites_folhas(conj, grupo)
        self.assertAlmostEqual(hi[0] - lo[0], L / 1000, places=5)
        self.assertAlmostEqual(hi[2] - lo[2], A / 1000, places=5)
        self.assertEqual(grupo['porta_parametros']['lateral_mm'], 30.0)

    def test_espessura_de_uma_folha_vale_para_a_porta(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        folhas = addon._folhas_portas(grupo)
        # espessura livre (nao arredonda mais para 15/18/20/30)
        folhas[0].chapa_espessura_mm = 21.0
        for folha in addon._folhas_portas(grupo):
            self.assertEqual(folha.chapa_espessura_mm, 21.0)
            self.assertAlmostEqual(folha.dimensions.z, 0.021, places=5)
        self.assertEqual(grupo['porta_parametros']['espessura_mm'], 21.0)
        # a face de tras continua no plano do vao
        lo, _ = self.limites_folhas(conj, grupo)
        L, A, P, E = addon._caixa_do_modulo(conj)
        self.assertAlmostEqual(lo[1], -P / 2000 - 0.021, places=5)
        conj.conj_largura_mm = L + 100
        bpy.context.view_layer.update()
        for folha in addon._folhas_portas(grupo):
            self.assertEqual(folha.chapa_espessura_mm, 21.0)

    def test_reconfigurar_nao_volta_a_espessura(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        addon._folhas_portas(grupo)[0].chapa_espessura_mm = 20.0
        self.assertEqual(bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', editar=True, grupo_nome=grupo.name,
            dobradica='RETA', folhas=2), {'FINISHED'})
        for folha in addon._folhas_portas(grupo):
            self.assertEqual(folha.chapa_espessura_mm, 20.0)

    # ------------------------------------------- edicao da porta colocada
    def aba_portas(self):
        bpy.context.scene.cabinet_aba = 'PORTAS'
        return addon._widgets_gaveta(bpy.context, 320, 1400)

    def test_niveis_de_selecao_modulo_porta_folha(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        folha = addon._folhas_portas(grupo)[1]
        addon._selecionar_chapa_hud(bpy.context, folha)
        self.assertEqual(bpy.context.object, conj)
        self.assertEqual(addon._nivel_da_selecao(bpy.context, folha), 'MODULO')
        addon._selecionar_porta_hud(bpy.context, folha, 'PORTA')
        self.assertEqual(bpy.context.object, grupo)
        self.assertEqual(set(bpy.context.selected_objects),
                         {grupo, *addon._folhas_portas(grupo)})
        self.assertEqual(addon._nivel_da_selecao(bpy.context, folha), 'PORTA')
        self.assertIsNone(addon._alvo_hud(bpy.context))
        addon._selecionar_porta_hud(bpy.context, folha, 'FOLHA')
        self.assertEqual(list(bpy.context.selected_objects), [folha])
        self.assertEqual(addon._nivel_da_selecao(bpy.context, folha), 'FOLHA')
        self.assertIsNone(addon._alvo_hud(bpy.context))
        # Shift soma a porta a' selecao em vez de troca-la
        addon._selecionar_chapa_hud(bpy.context, folha)          # o modulo
        addon._selecionar_porta_hud(bpy.context, folha, 'PORTA', somar=True)
        self.assertIn(conj, bpy.context.selected_objects)
        self.assertEqual(bpy.context.object, grupo)
        # folha sozinha tambem desliga o contorno nativo (conta como porta)
        addon._selecionar_porta_hud(bpy.context, folha, 'FOLHA')
        self.assertIn(folha.name, addon._grupos_selecionados(bpy.context.view_layer))

    def test_aba_mostra_a_porta_selecionada_e_nao_a_cena(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)       # reta, 2 folhas
        cena = bpy.context.scene
        antes = {p: getattr(cena, p) for p in addon._PROPS_PORTAS_CENA}
        self.addCleanup(lambda: [setattr(cena, p, v) for p, v in antes.items()])
        cena.porta_dobradica = 'CURVA'
        cena.porta_folhas = 1
        cena.porta_folga_mm = 7.0
        addon._selecionar_porta_hud(bpy.context, addon._folhas_portas(grupo)[0],
                                    'PORTA')
        widgets = self.aba_portas()
        acesos = {v[5][1]: v[5] for v in widgets
                  if v[5] and v[5][0] == 'escolha' and v[5][3]}
        # a dobradica e' automatica: nem aparece na aba (pedido do usuario)
        self.assertNotIn('Dobradica', [v[4] for v in widgets])
        self.assertEqual(acesos['porta_folhas'][2], 2)
        self.assertEqual(acesos['porta_folhas'][5], grupo.name)
        folga = next(v[5] for v in widgets if v[5] and v[5][0] == 'medida'
                     and v[5][2] == 'ui_porta_folga')
        self.assertEqual((folga[1], folga[4]), ('porta', 0.0))
        rotulos = [v[4] for v in widgets]
        # sem cabecalho "Porta N de M - vao L x A" (nome/medida repetidos)
        self.assertFalse(any(r.startswith('Porta ') and 'vao' in r
                             for r in rotulos))
        botao = next(v[5] for v in widgets if v[5] and v[5][0] == 'portas')
        self.assertTrue(botao[4])

    def test_editar_parametro_muda_so_aquela_porta(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        cena_antes = bpy.context.scene.porta_dobradica
        self.assertEqual(addon._editar_parametro_porta(
            bpy.context, grupo, 'dobradica', 'SUPER_CURVA'), '')
        self.assertEqual(grupo['porta_parametros']['dobradica'], 'SUPER_CURVA')
        self.assertEqual(bpy.context.scene.porta_dobradica, cena_antes)
        # embutida: as folhas ficam DENTRO do modulo
        L, A, P, E = addon._caixa_do_modulo(conj)
        lo, hi = self.limites_folhas(conj, grupo)
        self.assertGreater(lo[0], -L / 2000)
        self.assertLess(hi[0], L / 2000)
        # e ela continua acompanhando o modulo
        conj.conj_largura_mm = L + 100
        bpy.context.view_layer.update()
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], L + 100 - 2 * E,
                               places=2)
        self.assertEqual(addon._editar_parametro_porta(
            bpy.context, grupo, 'folhas', 1), '')
        self.assertEqual(len(addon._folhas_portas(grupo)), 1)

    def test_valor_invalido_nao_muda_a_porta(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        antes = dict(grupo['porta_parametros'])
        coords = [tuple(f.matrix_world @ v.co) for f in addon._folhas_portas(grupo)
                  for v in f.data.vertices]
        self.assertTrue(addon._editar_parametro_porta(
            bpy.context, grupo, 'folga_mm', 5000.0))
        self.assertEqual(dict(grupo['porta_parametros']), antes)
        self.assertEqual(coords, [tuple(f.matrix_world @ v.co)
                                  for f in addon._folhas_portas(grupo)
                                  for v in f.data.vertices])

    def test_campos_da_aba_e_espessura_editam_a_porta(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        addon._selecionar_porta_hud(bpy.context, addon._folhas_portas(grupo)[0],
                                    'FOLHA')
        self.assertEqual(bpy.ops.object.cabinet_editar_medida_gaveta(
            'EXEC_DEFAULT', dono='porta', objeto=bpy.context.object.name,
            propriedade='ui_porta_folga', valor=0.003), {'FINISHED'})
        self.assertAlmostEqual(grupo['porta_parametros']['folga_mm'], 3.0)
        modo, campos, dono = addon._medidas_gaveta(bpy.context)
        self.assertEqual((modo, dono), ('PORTA', 'porta'))
        self.assertEqual([c[2] for c in campos], ['', '', 'ui_porta_espessura'])
        self.assertEqual(bpy.ops.object.cabinet_editar_medida_gaveta(
            'EXEC_DEFAULT', dono='porta', objeto=bpy.context.object.name,
            propriedade='ui_porta_espessura', valor=0.021), {'FINISHED'})
        for folha in addon._folhas_portas(grupo):
            self.assertEqual(folha.chapa_espessura_mm, 21.0)   # livre

    def test_bloco_de_medidas_da_porta_igual_nas_duas_abas(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        addon._selecionar_porta_hud(bpy.context, addon._folhas_portas(grupo)[0],
                                    'PORTA')
        alvo = {'medida', 'modo'}   # rodape da aba Portas e' enxuto

        def bloco(aba):
            bpy.context.scene.cabinet_aba = aba
            widgets = addon._widgets_gaveta(bpy.context, 320, 1400)
            corte = max((v[1] for v in widgets
                         if v[5] and v[5][0] == 'separador'), default=-1e9)
            return [v[:4] + (v[5][0],) for v in widgets
                    if v[5] and v[5][0] in alvo and v[1] > corte]

        self.assertEqual(relativo(bloco('PORTAS')), relativo(bloco('MODULOS')))
        self.assertNotIn('modo', [b[4] for b in bloco('MODULOS')])

    # ------------------------------------------------ wizard (Epico 1)
    def test_quatro_cliques_coberturas_e_dobradica(self):
        # Desenho do usuario: 1 = canto da porta, 2 = do vao, 3 = vao
        # oposto, 4 = porta oposta. Cobertura de cada lado em espessuras.
        E = 18.0
        bordas = [Vector((-18, 382, 0)), Vector((573, -18, 0))]
        vaos = [Vector((0, 364, 0)), Vector((564, 0, 0))]
        cob = addon._coberturas_dos_cantos(bordas, vaos, E)
        self.assertEqual([cob[k] for k in addon.COBERTURAS_LADOS],
                         [1.0, 0.5, 1.0, 1.0])
        self.assertEqual(addon._lados_fora_do_padrao(cob), [])
        # +-2 mm ainda e' reta; 40 mm a mais, nao
        self.assertEqual(addon._encaixar_cobertura(19.5, E), 1.0)
        self.assertEqual(addon._lados_fora_do_padrao(addon._coberturas_dos_cantos(
            [Vector((-58, 382, 0)), bordas[1]], vaos, E)), ['cobertura_esq_e'])
        # clique 1 e 2 no mesmo ponto: a margem do par 3-4 vale para ele,
        # contada para DENTRO a partir do clique
        novos, espelhados = addon._espelhar_margem(
            [Vector((-18, 382, 0)), Vector((582, -18, 0))],
            [Vector((-18, 382, 0)), Vector((564, 0, 0))])
        self.assertEqual(espelhados, [True, False])
        self.assertEqual(novos[0].to_tuple(), (0.0, 364.0, 0.0))
        # os dois pares no mesmo ponto: nada se espelha
        self.assertEqual(addon._espelhar_margem(vaos, vaos)[1], [False, False])
        # dobradica automatica pela cobertura do lado dela
        self.assertEqual([addon._dobradica_da_cobertura(f) for f in (1.0, 0.5)],
                         ['RETA', 'CURVA'])
        self.assertEqual(addon._dobradica_da_cobertura(0.0, embutida=True),
                         'SUPER_CURVA')
        self.assertTrue(addon._porta_embutida(dict.fromkeys(
            addon.COBERTURAS_LADOS, 0.0)))
        self.assertFalse(addon._porta_embutida(cob))
        # bordas das dobradicas: as da FOLHA (vao + cobertura)
        arestas = addon._arestas_da_porta(564.0, 364.0, cob, E, 'GIRO')
        self.assertEqual([a['lado'] for a in arestas], ['ESQUERDA', 'DIREITA'])
        self.assertEqual(arestas[0]['a'].x, -18.0)
        self.assertEqual(arestas[1]['a'].x, 573.0)
        cima, = addon._arestas_da_porta(564.0, 364.0, cob, E, 'BASCULANTE')
        self.assertEqual((cima['lado'], cima['a'].y), ('CIMA', 382.0))

    def test_ferragens_em_segmentos_iguais_com_margem(self):
        self.assertEqual(addon._posicoes_ferragens(700.0, 3, 100.0),
                         [100.0, 350.0, 600.0])
        self.assertEqual(addon._posicoes_ferragens(700.0, 1, 100.0), [350.0])
        self.assertEqual(addon._posicoes_ferragens(100.0, 2, 80.0), [50.0, 50.0])
        self.assertEqual(addon._posicoes_ferragens(500.0, 0, 100.0), [])
        # padroes de marcenaria (editaveis no wizard)
        self.assertEqual([addon._qtd_dobradicas_padrao(a)
                          for a in (700, 900, 1200, 1800, 2200)],
                         [2, 2, 3, 4, 5])
        self.assertEqual(addon._qtd_pistoes_padrao(560), 1)
        self.assertEqual(addon._qtd_pistoes_padrao(800), 2)
        self.assertEqual(addon._offset_pistoes_padrao(525), 175)
        self.assertEqual(addon.MARGEM_DOBRADICAS_PADRAO, 100.0)

    def test_porta_guarda_as_ferragens_do_wizard(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        # sem wizard: 0 = automatico, lado esquerdo
        p = grupo['porta_parametros']
        self.assertEqual((p['dobradicas_qtd'], p['dobradica_lado']), (0, 'ESQUERDA'))
        # a aba continua lendo a porta sem tropecar nos campos novos
        valores = addon._valores_portas(bpy.context.scene, grupo)
        self.assertEqual(valores['dobradica_lado'], 'ESQUERDA')
        addon._carregar_portas_na_cena(bpy.context.scene, grupo)

    def test_campos_da_porta_seguem_a_abertura(self):
        # Com a porta selecionada os campos aparecem e seguem o tipo dela
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        addon._selecionar_porta_hud(bpy.context, addon._folhas_portas(grupo)[0],
                                    'PORTA')
        bpy.context.scene.cabinet_aba = 'PORTAS'

        def props():
            return {v[5][2] for v in addon._widgets_gaveta(bpy.context, 320, 1400)
                    if v[5] and v[5][0] == 'medida'
                    and v[5][2].startswith('ui_porta_')}

        self.assertIn('ui_porta_folga', props())
        self.assertNotIn('ui_porta_recuo_correr', props())
        self.assertEqual(addon._editar_parametro_porta(
            bpy.context, grupo, 'abertura', 'CORRER'), '')
        self.assertIn('ui_porta_recuo_correr', props())
        self.assertNotIn('ui_porta_afastamento', props())

    def test_previa_e_execucao_usam_o_mesmo_vao(self):
        from types import SimpleNamespace
        conj, cima, baixo = self.duas_fileiras()
        folha = addon._folhas_portas(cima)[-1]
        a = conj.matrix_world @ Vector((-0.3, -0.15, 0))
        b = conj.matrix_world @ Vector((0.3, -0.168, 0.682))
        chapa = addon._chapas_do_conjunto(conj)[0]
        tipo = addon.OBJECT_OT_apanhar_vao_portas
        # 4 cliques: porta e vao no mesmo ponto nos dois cantos
        falso = SimpleNamespace(_pontos=[(a, chapa), (a, chapa), (b, folha)],
                                _imantado=b, _objeto_imantado=folha,
                                _frente='NEG_Y')
        falso._referencia = lambda a, b: tipo._referencia(falso, a, b)
        falso._centro = lambda a, b: tipo._centro(falso, a, b)
        caixas = tipo._previa(falso)
        self.assertEqual(len(caixas), 2)
        esperados = [p for caixa in caixas for p in caixa]
        reais = [f.matrix_world @ v.co for f in addon._folhas_portas(baixo)
                 for v in f.data.vertices]
        for p in reais:
            self.assertLess(min((p - q).length for q in esperados), 1e-5)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestPortas)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
addon.register()
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de portas')
