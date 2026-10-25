"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_paredes_blender.py

Paredes, como no Promob (pedido do usuario): o modulo solto numa parede
encosta as COSTAS nela e fica ASSOCIADO; as guias medem ate' as pontas, o
piso e o teto, e digitar uma delas leva o modulo. A parede e' QUALQUER
superficie vertical que nao seja movel do add-on.

O arraste com o botao direito e o clique no numero da guia (modais, com
eventos de verdade) estao em `gui_interacao.py`.
"""
import math
import os
import sys
import unittest
from types import SimpleNamespace

import bpy
import bmesh
from mathutils import Euler, Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

P = addon.paredes


def caixa(nome, dims, centro):
    """Malha de caixa sem marcador (a parede que o usuario modelou)."""
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
    bpy.context.scene.collection.objects.link(obj)
    obj.location = centro
    bpy.context.view_layer.update()
    return obj


class TestParedes(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for colecao in list(bpy.data.collections):
            bpy.data.collections.remove(colecao)
        camada = bpy.context.view_layer
        camada.active_layer_collection = camada.layer_collection
        P.esquecer()
        # parede de 3000 x 2700, face da frente em y = 1 m olhando para -Y
        self.parede = caixa('Parede', (3.0, 0.15, 2.7), (0.0, 1.075, 1.35))

    def modulo(self):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        self.parede.select_set(False)
        bpy.ops.object.cabinet_agrupar()
        conj = next(o for o in bpy.data.objects
                    if addon.chapas.MARCA_CONJUNTO in o)
        bpy.context.view_layer.update()
        return conj

    def medidas(self, conj):
        lo, hi = P.caixa_do_modulo(conj)
        return (hi.x - lo.x) * 1000, (hi.z - lo.z) * 1000

    def encostar(self, conj, s=0.0, base=0.5):
        """O que o soltar do arraste faz, sem o mouse."""
        normal = Vector((0.0, -1.0, 0.0))
        costas = Vector((s, 1.0, base))
        self.assertTrue(P.colocar_na_parede(conj, self.parede, costas, normal))
        P.associar(conj, self.parede, costas, normal)
        bpy.context.view_layer.update()
        P.manter_nas_paredes()
        return costas

    def assertVetor(self, a, b, casas=4):
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=casas)

    def test_parede_e_superficie_vertical_que_nao_e_movel(self):
        n, u = P.eixos_da_parede(Vector((0.0, -1.0, 0.0)))
        self.assertVetor(n, (0, -1, 0))
        self.assertVetor(u, (1, 0, 0))        # a direita de quem olha a parede
        self.assertIsNone(P.eixos_da_parede(Vector((0.0, 0.0, 1.0))))    # piso
        self.assertIsNone(P.eixos_da_parede(Vector((0.0, -0.4, -0.9))))  # teto
        # as costas (+Y do modulo) apontam para dentro da parede
        self.assertVetor(P.rotacao_na_parede(n, u) @ Vector((0, 1, 0)), (0, 1, 0))
        conj = self.modulo()
        self.assertTrue(P.eh_movel(conj))
        self.assertTrue(P.eh_movel(addon.modulos._chapas_do_conjunto(conj)[0]))
        self.assertFalse(P.eh_movel(self.parede))

    def test_limites_da_parede_sao_as_faces_do_mesmo_plano(self):
        retangulo = P.retangulo_da_parede(
            self.parede, Vector((0.4, 1.0, 1.0)), Vector((0.0, -1.0, 0.0)))
        self.assertVetor(retangulo, (-1.5, 1.5, 0.0, 2.7))
        # a face de tras e' outra parede (normal oposta): pontas espelhadas
        retangulo = P.retangulo_da_parede(
            self.parede, Vector((0.4, 1.15, 1.0)), Vector((0.0, 1.0, 0.0)))
        self.assertVetor(retangulo, (-1.5, 1.5, 0.0, 2.7))

    def test_regiao_de_malha_pesada_em_lote_e_uma_vez_por_parede(self):
        # Cena real (relato do usuario): uma casa de centenas de milhares de
        # faces travava a cada passo do mouse. A regiao sai em lote e vale
        # para TODAS as faces dela: andar pela parede nao recalcula.
        import time
        from unittest.mock import patch
        casa = caixa('Casa', (3.0, 0.15, 2.7), (0.0, 5.075, 1.35))
        bm = bmesh.new()
        bm.from_mesh(casa.data)
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=120, use_grid_fill=True)
        bm.to_mesh(casa.data)
        bm.free()
        bpy.context.view_layer.update()
        self.assertGreater(len(casa.data.polygons), 80000)
        normal = Vector((0, -1, 0))
        dep = bpy.context.evaluated_depsgraph_get()
        inicio = time.perf_counter()
        a = P.regiao_da_parede(casa, Vector((-1.0, 5.0, .5)), normal, dep)
        self.assertLess(time.perf_counter() - inicio, 2.0)
        s0, s1, z0, z1 = a['retangulo']
        self.assertAlmostEqual(s1 - s0, 3.0, places=4)
        self.assertAlmostEqual(z1 - z0, 2.7, places=4)
        self.assertEqual(len(a['faces']), 121 * 121)
        # contorno = so' a borda da face (4 lados de 121 arestas)
        self.assertEqual(len(a['contorno']), 4 * 121)
        self.assertEqual(len(a['triangulos']), 3 * 2 * 121 * 121)
        outra = next(f for f in a['faces'] if f != a['face'])
        with patch.object(P, '_calcular_regiao', side_effect=AssertionError('recalculou')):
            b = P.regiao_da_parede(casa, Vector((1.0, 5.0, 2.0)), normal, dep, outra)
            # associacao antiga, sem indice: o retangulo do plano basta
            c = P.regiao_da_parede(casa, Vector((0.0, 5.0, 1.0)), normal, dep)
        self.assertEqual(b['face'], outra)
        self.assertEqual(b['retangulo'], a['retangulo'])
        self.assertEqual(c['faces'], a['faces'])

    def test_soltar_encosta_as_costas_e_mede_as_guias(self):
        conj = self.modulo()
        conj.rotation_euler = Euler((0, 0, math.radians(70)))  # torto antes
        bpy.context.view_layer.update()
        largura, altura = self.medidas(conj)
        self.encostar(conj, s=0.2, base=0.5)
        # virado para fora da parede, costas no plano y = 1 m
        self.assertVetor(conj.matrix_world.to_3x3() @ Vector((0, 1, 0)), (0, 1, 0))
        self.assertAlmostEqual(P.ponto_das_costas(conj).y, 1.0, places=5)
        guias = P.calcular_guias(conj)
        valores = guias['valores']
        self.assertAlmostEqual(valores['piso'], 500.0, places=2)
        self.assertAlmostEqual(valores['teto'], 2700.0 - 500.0 - altura, places=2)
        self.assertAlmostEqual(valores['esquerda'], 1700.0 - largura / 2, places=2)
        self.assertAlmostEqual(valores['direita'], 1300.0 - largura / 2, places=2)
        # cada linha vai da parede ao modulo, 1 mm a' frente dela
        a, b = guias['linhas']['piso']
        self.assertAlmostEqual(a.z, 0.0, places=5)
        self.assertAlmostEqual(b.z, 0.5, places=5)
        self.assertAlmostEqual(a.y, 1.0 - P.DESLOCAMENTO_GUIA_M, places=6)
        # o UID fica na parede, a parede no modulo
        self.assertEqual(conj[P.CHAVE_PAREDE], self.parede[P.CHAVE_UID_PAREDE])
        self.assertIs(P.parede_do_modulo(conj), self.parede)

    def test_digitar_a_guia_leva_o_modulo(self):
        # o desenho do usuario: 1000 da esquerda, 1200 do piso
        conj = self.modulo()
        largura, altura = self.medidas(conj)
        self.encostar(conj)
        self.assertTrue(P.aplicar_guia(conj, 'esquerda', 1000.0))
        self.assertTrue(P.aplicar_guia(conj, 'piso', 1200.0))
        valores = P.calcular_guias(conj)['valores']
        self.assertAlmostEqual(valores['esquerda'], 1000.0, places=2)
        self.assertAlmostEqual(valores['piso'], 1200.0, places=2)
        self.assertAlmostEqual(valores['direita'], 3000.0 - 1000.0 - largura, places=2)
        self.assertAlmostEqual(valores['teto'], 2700.0 - 1200.0 - altura, places=2)
        # pela direita e pelo teto tambem; as costas nao saem da parede
        P.aplicar_guia(conj, 'direita', 350.0)
        P.aplicar_guia(conj, 'teto', 200.0)
        valores = P.calcular_guias(conj)['valores']
        self.assertAlmostEqual(valores['direita'], 350.0, places=2)
        self.assertAlmostEqual(valores['teto'], 200.0, places=2)
        self.assertAlmostEqual(P.ponto_das_costas(conj).y, 1.0, places=5)

    def test_parede_que_anda_e_gira_leva_o_modulo(self):
        conj = self.modulo()
        self.encostar(conj, s=0.3, base=0.4)
        antes = P.calcular_guias(conj)['valores']
        self.parede.location.x += 0.5
        self.parede.rotation_euler.z = math.radians(90)
        bpy.context.view_layer.update()
        self.assertTrue(P.manter_nas_paredes())
        depois = P.calcular_guias(conj)['valores']
        for lado in P.LADOS:
            self.assertAlmostEqual(depois[lado], antes[lado], places=2, msg=lado)
        # girou junto: as costas agora apontam para +X... para dentro dela
        normal = P._normal_no_mundo(self.parede, conj[P.CHAVE_PAREDE_NORMAL])
        self.assertVetor(conj.matrix_world.to_3x3() @ Vector((0, 1, 0)), -normal)
        # parada, nada mais muda
        self.assertFalse(P.manter_nas_paredes())

    def test_modulo_movido_so_desliza_na_parede(self):
        conj = self.modulo()
        self.encostar(conj, s=0.0, base=0.5)
        # G para longe da parede e R torto: volta ao plano, guarda o resto
        conj.location += Vector((0.25, -0.4, 0.1))
        conj.rotation_euler.z += math.radians(30)
        bpy.context.view_layer.update()
        self.assertTrue(P.manter_nas_paredes())
        self.assertAlmostEqual(P.ponto_das_costas(conj).y, 1.0, places=5)
        self.assertVetor(conj.matrix_world.to_3x3() @ Vector((0, 1, 0)), (0, 1, 0))
        self.assertAlmostEqual(P.calcular_guias(conj)['valores']['piso'], 600.0, places=2)

    def test_desassociar_solta_o_modulo(self):
        conj = self.modulo()
        self.encostar(conj)
        for o in bpy.context.selected_objects:
            o.select_set(False)
        conj.select_set(True)
        bpy.context.view_layer.objects.active = conj
        self.assertEqual(bpy.ops.object.cabinet_desassociar_parede(), {'FINISHED'})
        self.assertNotIn(P.CHAVE_PAREDE, conj)
        conj.location.y -= 0.5
        bpy.context.view_layer.update()
        self.assertFalse(P.manter_nas_paredes())      # nao volta mais
        self.assertEqual(bpy.ops.object.cabinet_desassociar_parede(), {'CANCELLED'})

    def test_parede_duplicada_desempata_pelo_nome(self):
        conj = self.modulo()
        self.encostar(conj)
        copia = self.parede.copy()          # Shift+D: o UID vai junto
        bpy.context.scene.collection.objects.link(copia)
        self.assertIs(P.parede_do_modulo(conj), self.parede)
        self.parede.name = 'Parede Renomeada'   # renomear nao solta
        self.assertIn(P.parede_do_modulo(conj), {self.parede, copia})

    def test_arraste_gruda_nas_pontas_no_piso_e_no_teto(self):
        retangulo = (-1.5, 1.5, 0.0, 2.7)
        # a 1 cm da ponta esquerda e do piso: gruda (tolerancia 2 cm)
        s, base = P.posicao_no_arraste(retangulo, -1.5 + 0.3 + 0.01, 0.01,
                                       0.6, 0.7, 0.02)
        self.assertAlmostEqual(s, -1.2)
        self.assertAlmostEqual(base, 0.0)
        # perto da direita e do teto
        s, base = P.posicao_no_arraste(retangulo, 1.5 - 0.3 - 0.015, 2.0 - 0.01,
                                       0.6, 0.7, 0.02)
        self.assertAlmostEqual(s, 1.2)
        self.assertAlmostEqual(base, 2.0)
        # longe: fica onde esta'
        self.assertEqual(P.posicao_no_arraste(retangulo, 0.0, 1.0, 0.6, 0.7, 0.02),
                         (0.0, 1.0))

    def test_guias_so_do_modulo_ativo_selecionado_e_associado(self):
        conj = self.modulo()
        for o in bpy.context.selected_objects:
            o.select_set(False)
        conj.select_set(True)
        bpy.context.view_layer.objects.active = conj
        P.atualizar_guias()
        self.assertIsNone(P._guias[0])               # ainda solto
        self.encostar(conj)
        P.atualizar_guias()
        self.assertEqual(P._guias[0]['modulo'], conj.name)
        conj.select_set(False)
        P.atualizar_guias()
        self.assertIsNone(P._guias[0])
        # sem guias, o gizmo dos numeros (VIEW3D_GGT_guias_parede) nao
        # aparece e o operador da guia (cabinet_guia_parede) nao roda
        self.assertFalse(P.OBJECT_OT_guia_parede.poll(bpy.context))

    def test_raio_atravessa_o_modulo_encostado_e_acha_a_face_da_parede(self):
        # Regressao (relato do usuario, v202): com as costas NO plano da
        # parede, pular o modulo andando 0,1 mm atravessava a face dela e
        # o arraste pegava o outro lado da parede ou nada -- "nao e' parede"
        conj = self.modulo()
        self.encostar(conj, s=0.0, base=0.5)
        lateral = min(addon.modulos._chapas_do_conjunto(conj),
                      key=lambda c: c.matrix_world.translation.x)
        x = lateral.matrix_world.translation.x
        ignorar = {conj.name, *(o.name for o in conj.children_recursive)}
        # pela espessura da lateral: sai dela EXATAMENTE na face da parede
        acerto = P.raio_ate_parede(bpy.context, Vector((x, -3.0, 0.7)),
                                   Vector((0.0, 1.0, 0.0)), ignorar)
        self.assertIsNotNone(acerto)
        parede, ponto, normal, face = acerto
        self.assertIs(parede, self.parede)
        self.assertAlmostEqual(ponto.y, 1.0, places=5)        # a face da FRENTE
        self.assertVetor(normal, (0, -1, 0))
        self.assertVetor(self.parede.matrix_world.to_3x3()
                         @ self.parede.data.polygons[face].normal, (0, -1, 0))

    def sala(self):
        """Um objeto so' (como a sala do usuario, Geometry Nodes): na
        mesma linha y = 1, a parede A em dois quads ligados (-1.5..-0.5 e
        -0.5..0) e, depois de um vao, a parede B (0.5..1.5); a parede C,
        de lado, ligada a' A pela quina."""
        h = 2.7
        vs = [(-1.5, 1, 0), (-0.5, 1, 0), (-0.5, 1, h), (-1.5, 1, h),   # A1
              (0.0, 1, 0), (0.0, 1, h),                                # A2
              (0.5, 1, 0), (1.5, 1, 0), (1.5, 1, h), (0.5, 1, h),       # B
              (-1.5, -1, 0), (-1.5, -1, h)]                            # C
        faces = [(0, 1, 2, 3), (1, 4, 5, 2), (6, 7, 8, 9), (10, 0, 3, 11)]
        malha = bpy.data.meshes.new('Sala')
        malha.from_pydata(vs, [], faces)
        malha.update()
        obj = bpy.data.objects.new('Sala', malha)
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.update()
        return obj

    def test_associa_a_face_e_nao_ao_objeto(self):
        # pedido do usuario: a parede e' a FACE (com as vizinhas no mesmo
        # plano ligadas a ela), nao o objeto inteiro nem o plano inteiro
        sala = self.sala()
        frente = Vector((0.0, -1.0, 0.0))
        regiao = P.regiao_da_parede(sala, Vector((-1.0, 1.0, 1.0)), frente, face=0)
        self.assertEqual(regiao['face'], 0)
        self.assertVetor(regiao['retangulo'], (-1.5, 0.0, 0.0, 2.7))   # A1 + A2
        self.assertEqual(len(regiao['contorno']), 6)    # sem a aresta entre A1 e A2
        self.assertEqual(len(regiao['triangulos']), 2 * 2 * 3)
        b = P.regiao_da_parede(sala, Vector((1.0, 1.0, 1.0)), frente, face=2)
        self.assertVetor(b['retangulo'], (0.5, 1.5, 0.0, 2.7))         # so' a B
        # modulo na B: a esquerda mede da ponta da B, nao da A
        conj = self.modulo()
        largura, _altura = self.medidas(conj)
        costas = Vector((1.0, 1.0, 0.0))
        P.colocar_na_parede(conj, sala, costas, frente)
        P.associar(conj, sala, costas, frente, face=2)
        self.assertEqual(conj[P.CHAVE_PAREDE_FACE], 2)
        valores = P.calcular_guias(conj)['valores']
        self.assertAlmostEqual(valores['esquerda'], 500.0 - largura / 2, places=2)
        self.assertAlmostEqual(valores['direita'], 500.0 - largura / 2, places=2)
        # malha refeita (indice que nao bate): a face do plano mais perto
        conj[P.CHAVE_PAREDE_FACE] = 999
        P._retangulos.clear()
        self.assertAlmostEqual(P.calcular_guias(conj)['valores']['esquerda'],
                               500.0 - largura / 2, places=2)
        P.desassociar(conj)
        self.assertNotIn(P.CHAVE_PAREDE_FACE, conj)

    def modulo_com_porta_em_x(self):
        """Modulo com a porta na face +X (preset girado por dentro)."""
        conj = self.modulo()
        grupo = addon.portas.porta_no_modulo(conj)
        bpy.context.view_layer.update()
        self.assertEqual(P.frente_do_modulo(conj), 'NEG_Y')
        # gira a porta 90 graus em volta do Empty: da face -Y para a +X
        giro = (conj.matrix_world @ Matrix.Rotation(math.radians(90), 4, 'Z')
                @ conj.matrix_world.inverted())
        grupo.matrix_world = giro @ grupo.matrix_world
        bpy.context.view_layer.update()
        return conj

    def test_costas_sao_o_lado_oposto_a_porta(self):
        # Relato do usuario: o preset com a porta em X encostava a lateral
        # na parede. As costas sao SEMPRE o lado oposto a' porta.
        conj = self.modulo_com_porta_em_x()
        self.assertEqual(P.frente_do_modulo(conj), 'POS_X')
        self.assertEqual(P.lado_das_costas(conj), 'NEG_X')
        lo, hi = P.caixa_local_do_modulo(conj)
        self.encostar(conj, s=0.2, base=0.5)
        self.assertEqual(conj[P.CHAVE_COSTAS], 'NEG_X')      # gravado ao associar
        # a porta (+X do modulo) olha para fora da parede (-Y do mundo)
        self.assertVetor(conj.matrix_world.to_3x3() @ Vector((1, 0, 0)), (0, -1, 0))
        pontos = [conj.matrix_world @ Vector((x, y, z)) for x in (lo.x, hi.x)
                  for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
        self.assertAlmostEqual(max(p.y for p in pontos), 1.0, places=5)   # costas no plano
        self.assertAlmostEqual((min(p.x for p in pontos) + max(p.x for p in pontos)) / 2,
                               0.2, places=5)
        self.assertAlmostEqual(min(p.z for p in pontos), 0.5, places=5)
        # ao longo da parede vale a PROFUNDIDADE do modulo
        largura, _altura = self.medidas(conj)
        self.assertAlmostEqual(largura, (hi.y - lo.y) * 1000, places=3)
        guias = P.calcular_guias(conj)['valores']
        self.assertAlmostEqual(guias['esquerda'], 1700.0 - largura / 2, places=2)
        # o timer nao desfaz o giro
        self.assertFalse(P.manter_nas_paredes())

    def test_roda_do_mouse_troca_a_face_contra_a_parede(self):
        conj = self.modulo()
        self.encostar(conj)
        self.assertEqual(conj[P.CHAVE_COSTAS], 'POS_Y')
        dentro = {'POS_X': (1, 0, 0), 'NEG_Y': (0, -1, 0), 'NEG_X': (-1, 0, 0),
                  'POS_Y': (0, 1, 0)}
        vistos = []
        for _ in range(4):
            vistos.append(P.girar_costas(conj, P.passos_da_roda(
                SimpleNamespace(type='WHEELUPMOUSE'))))
            P.colocar_na_parede(conj, self.parede, Vector((0.0, 1.0, 0.5)), Vector((0, -1, 0)))
            bpy.context.view_layer.update()
            # o lado escolhido aponta para dentro da parede (+Y do mundo)
            self.assertVetor(conj.matrix_world.to_3x3() @ Vector(dentro[vistos[-1]]), (0, 1, 0))
            self.assertAlmostEqual(P.ponto_das_costas(conj).y, 1.0, places=5)
        self.assertEqual(vistos, ['POS_X', 'NEG_Y', 'NEG_X', 'POS_Y'])   # volta inteira
        self.assertEqual(P.girar_costas(conj, P.passos_da_roda(
            SimpleNamespace(type='WHEELDOWNMOUSE'))), 'NEG_X')
        self.assertEqual(P.passos_da_roda(SimpleNamespace(type='MOUSEMOVE')), 0)
        P.desassociar(conj)
        self.assertNotIn(P.CHAVE_COSTAS, conj)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestParedes)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de paredes')
