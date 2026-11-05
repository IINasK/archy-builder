"""Weld uniqueness by real objects, registration and axial compatibility."""
import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon


class TestSoldaUnica(unittest.TestCase):
    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        self.s = addon.solda
        lista = bpy.app.handlers.depsgraph_update_post
        self.handler = addon.chapas.ao_atualizar_depsgraph in lista
        if self.handler:
            lista.remove(addon.chapas.ao_atualizar_depsgraph)

    def tearDown(self):
        if self.handler:
            bpy.app.handlers.depsgraph_update_post.append(addon.chapas.ao_atualizar_depsgraph)
        addon.eventos._desfazendo[0] = False
        addon.chapas._ocupado[0] = False

    def chapa(self, nome, x=0.):
        obj = addon.chapas.nova_chapa(nome, 400, 300, 18, (x, 0, 0), (0, 0, 0), bpy.context)
        bpy.context.view_layer.update()
        return obj

    def legado(self, c, ponta, n, folga=0.):
        c['adj_'+ponta] = n.name
        c['adj_'+ponta+'_uid'] = addon.chapas._garantir_uid(n)
        c['adj_'+ponta+'_face'] = 0 if ponta.endswith('pos') else 1
        c['adj_'+ponta+'_folga'] = folga

    def arestas(self):
        return [(c, p, n) for c in bpy.data.objects if 'eh_chapa' in c
                for p in addon.chapas.PONTAS if (n := self.s._vizinho_da_ponta(c, p)) is not None]

    def test_writer_impede_repetir_par_inclusive_no_sentido_inverso(self):
        a, b, c = self.chapa('A'), self.chapa('B', 400), self.chapa('C', 800)
        self.assertTrue(addon.chapas._gravar_ligacao(a, 'x', 'pos', b, 0., 0))
        self.assertFalse(addon.chapas._gravar_ligacao(a, 'y', 'pos', b, 0., 0))
        self.assertFalse(addon.chapas._gravar_ligacao(b, 'x', 'neg', a, 0., 1))
        self.assertTrue(addon.chapas._gravar_ligacao(b, 'x', 'pos', c, 0., 0))
        self.assertEqual(len(self.arestas()), 2)
        self.assertEqual(self.s.restricoes_adjacencia([b])[b]['x_neg'][0], a)

    def test_normalizar_reciprocos_preserva_os_dois_encaixes_axiais(self):
        a, b = self.chapa('A'), self.chapa('B', 450)
        self.legado(a, 'x_pos', b)
        self.legado(b, 'x_neg', a)
        r = self.s.normalizar_ligacoes([a, b])
        self.assertEqual((r['ligacoes'], r['removidas']), (1, 1))
        self.assertEqual(len(self.arestas()), 1)
        medidas = {o.name: (o.matrix_world.copy(), o.chapa_largura_mm) for o in (a, b)}
        for origem, destino, ponta in ((a, b, 'x_pos'), (b, a, 'x_neg')):
            addon.chapas.aplicar_adjacencia([origem])
            bpy.context.view_layer.update()
            extremo = addon.chapas._faixa(origem, Vector((1, 0, 0)))[1 if ponta.endswith('pos') else 0]
            alvo = addon.chapas._faixa(destino, Vector((1, 0, 0)))[0 if ponta.endswith('pos') else 1]
            self.assertAlmostEqual(extremo, alvo, places=6)
            self.assertAlmostEqual(origem.chapa_espessura_mm, 18., places=5)
            matriz, largura = medidas[origem.name]
            addon.chapas._ocupado[0] = True
            try:
                origem.chapa_largura_mm = largura
                origem.matrix_world = matriz
            finally:
                addon.chapas._ocupado[0] = False
            addon.chapas.gerar_malha_chapa(origem)
            bpy.context.view_layer.update()
        self.assertEqual(self.s.normalizar_ligacoes([b, a])['alteradas'], [])

    def test_otimizar_reciprocos_preserva_restricoes_dos_dois_extremos(self):
        a, b = self.chapa('A'), self.chapa('B', 400)
        self.legado(a, 'x_pos', b)
        self.legado(b, 'x_neg', a)
        addon.chapas.otimizar_adjacencia([a, b])
        self.assertEqual(len(self.arestas()), 1)
        mapa = self.s.restricoes_adjacencia([a, b])
        for origem, ponta, destino, face in ((a, 'x_pos', b, 0), (b, 'x_neg', a, 1)):
            self.assertIn(ponta, mapa[origem])
            vizinho, face_atual, gap = mapa[origem][ponta]
            self.assertIs(vizinho, destino)
            self.assertEqual(face_atual, face)
            self.assertAlmostEqual(gap, 0., places=7)

    def test_regravar_mesma_ponta_conserva_restricao_do_outro_extremo(self):
        a, b = self.chapa('A'), self.chapa('B', 400)
        addon.chapas._gravar_ligacao(a, 'x', 'pos', b, 0., 0)
        addon.chapas._gravar_ligacao(b, 'x', 'neg', a, .007, 1)
        antes = self.s.restricoes_adjacencia([a, b])
        self.assertEqual(antes[b]['x_neg'], (a, 1, .007))
        addon.chapas._gravar_ligacao(a, 'x', 'pos', b, 0., 0)
        self.assertEqual(len(self.arestas()), 1)
        self.assertEqual(self.s.restricoes_adjacencia([a, b]), antes)

    def test_conflito_axial_independe_da_ordem_e_nao_altera_metadados(self):
        a, b, c = self.chapa('A'), self.chapa('B', 400), self.chapa('C', 800)
        self.legado(b, 'x_neg', a)
        self.s._gravar_restricoes(b, 'x_neg', a, [(a, 'x_pos', b, 0, 0.)])
        self.legado(a, 'x_pos', c, .025)
        antes = {o.name: repr(sorted((k, str(v)) for k, v in o.items())) for o in (a, b, c)}
        resultados = []
        for ordem in ((b, a, c), (a, b, c)):
            with patch.object(self.s, 'bpy', SimpleNamespace(data=SimpleNamespace(objects=ordem))):
                try:
                    mapa = self.s.restricoes_adjacencia([a, b, c])
                except ValueError:
                    resultados.append(None)
                else:
                    resultados.append(mapa[a]['x_pos'])
        self.assertEqual(resultados[0], resultados[1])
        # The domain may reject the conflict or prioritize the primary; never depend on file order.
        if resultados[0] is not None:
            self.assertEqual(resultados[0], (c, 0, .025))
        self.assertEqual({o.name: repr(sorted((k, str(v)) for k, v in o.items())) for o in (a, b, c)}, antes)

    def test_default_neg_legado_preserva_face_e_largura_sem_prop_face(self):
        a, b = self.chapa('A'), self.chapa('B', -400)
        self.legado(a, 'x_neg', b)
        del a['adj_x_neg_face']
        antes = a.matrix_world.copy()
        self.assertEqual(self.s.restricoes_adjacencia([a])[a]['x_neg'][:2], (b, 1))
        self.assertAlmostEqual(self.s._folga_com_sinal(a, 'x_neg', b)[0], 0., places=7)
        addon.chapas.aplicar_adjacencia([a])
        bpy.context.view_layer.update()
        self.assertAlmostEqual(a.chapa_largura_mm, 400., places=4)
        for atual, anterior in zip(a.matrix_world, antes):
            self.assertLess((atual-anterior).length, 1e-7)

    def test_b_afastado_100mm_nao_puxa_a_50mm_quando_c_e_prioritario(self):
        a, b, c = self.chapa('A'), self.chapa('B', 400), self.chapa('C', 800)
        b.location.y = .3
        self.legado(b, 'y_neg', a)
        self.s._gravar_restricoes(b, 'y_neg', a, [(a, 'x_pos', b, 0, 0.)])
        self.legado(a, 'x_pos', c, .4)
        b.location.x += .1
        bpy.context.view_layer.update()
        antes = {o.name: o.matrix_world.copy() for o in (a, b, c)}
        self.assertIs(self.s.restricoes_adjacencia([a])[a]['x_pos'][0], c)
        self.assertEqual(self.s._pontas_fora_do_lugar([a, b, c]), [])
        self.assertIsNone(self.s._plano_reset_chapa(a))
        self.assertFalse(self.s.resetar_ponta(b, 'y_neg'))
        for o in (a, b, c):
            self.assertEqual(o.matrix_world, antes[o.name])

    def test_migracao_escolhe_minimo_real_no_mundo_sem_mover_malhas(self):
        a, b = self.chapa('A'), self.chapa('B', 530)
        b.rotation_euler.z = .7
        b.scale = (.8, 1.7, 1.)
        bpy.context.view_layer.update()
        self.legado(a, 'x_pos', b)
        antes = {o.name: (o.matrix_world.copy(), [tuple(v.co) for v in o.data.vertices],
                         [tuple(f.vertices) for f in o.data.polygons]) for o in (a, b)}
        minimo = min((a.matrix_world@v.co-b.matrix_world@w.co).length
                     for v in a.data.vertices for w in b.data.vertices)
        self.s.normalizar_ligacoes([a, b], recalcular_ancoras=True)
        c, p, n = self.arestas()[0]
        sc, sn = self.s._ancoras_gravadas(c, p)[0]
        distancia = (self.s._vertice_da_assinatura(c, sc)-self.s._vertice_da_assinatura(n, sn)).length
        self.assertAlmostEqual(distancia, minimo, places=6)
        self.assertIsNone(self.s._plano_reset_chapa(c))
        for o in (a, b):
            self.assertEqual((o.matrix_world, [tuple(v.co) for v in o.data.vertices],
                              [tuple(f.vertices) for f in o.data.polygons]), antes[o.name])
        self.assertEqual(self.s.normalizar_ligacoes([a, b], True)['alteradas'], [])

    def test_compatibilidade_nao_cadastra_chapa_afastada_como_nova_origem(self):
        a, b = self.chapa('A'), self.chapa('B', 430)
        self.s._registrar_pares_reais(a, {('x_pos', b.name): [('v0', 'v0')]})
        a['adj_x_pos_manual'] = True
        a['adj_x_pos_direcoes'] = json.dumps([(1, 0, 0)])
        registro = a['adj_x_pos_origens']
        a.location.y += .12
        bpy.context.view_layer.update()
        self.legado(b, 'x_neg', a)
        self.s.normalizar_ligacoes([a, b])
        self.assertEqual(a['adj_x_pos_origens'], registro)
        self.assertGreater(self.s._desvio_ancora(a, 'x_pos', b, 0, 'v0', 'v0').length, .1)
        self.assertEqual(len(self.arestas()), 1)

    def test_mesmo_vertice_em_destinos_distintos_nao_perde_conexao(self):
        a, b, c = self.chapa('A'), self.chapa('B', 400), self.chapa('C', 800)
        self.s._registrar_pares_reais(a, {('x_pos', b.name): [('v0', 'v0')],
                                         ('y_pos', c.name): [('v0', 'v0')]})
        self.s.normalizar_ligacoes([a, b, c], True)
        self.assertEqual(len(self.arestas()), 2)

    def test_plano_manual_duplicado_e_destino_invalido_nao_apagam_terceiros(self):
        a, b, c = self.chapa('A'), self.chapa('B', 400), self.chapa('C', 800)
        self.s._registrar_pares_reais(a, {('x_pos', c.name): [('v0', 'v0')]})
        antes = repr(sorted((k, str(v)) for k, v in a.items()))
        for pares in ([('v0', b.name, 'v0'), ('v1', b.name, 'v1')], [('v0', b.name, 'v999')]):
            with self.assertRaises(ValueError):
                self.s._plano_ancoras_reais(a, pares)
        with self.assertRaises(ValueError):
            self.s._registrar_pares_reais(a, {('x_pos', b.name): [('v0', 'v0')]})
        self.assertEqual(repr(sorted((k, str(v)) for k, v in a.items())), antes)

    def test_duplicatas_de_uid_nao_colapsam_pares_de_objetos_diferentes(self):
        a, b, c, d = [self.chapa(nome, i*400) for i, nome in enumerate('ABCD')]
        pai = bpy.data.objects.new('Outro modulo', None)
        bpy.context.scene.collection.objects.link(pai)
        c.parent = d.parent = pai
        a['chapa_uid'] = c['chapa_uid'] = 'uid-origem'
        b['chapa_uid'] = d['chapa_uid'] = 'uid-destino'
        self.legado(a, 'x_pos', b)
        self.legado(c, 'x_pos', d)
        self.assertEqual(self.s.normalizar_ligacoes([a, b, c, d])['ligacoes'], 2)
        self.assertEqual(len(self.arestas()), 2)

    def test_normalizar_nao_toca_dados_durante_undo_ou_edit_mode(self):
        a, b = self.chapa('A'), self.chapa('B', 400)
        self.legado(a, 'x_pos', b)
        self.legado(b, 'x_neg', a)
        addon.eventos._desfazendo[0] = True
        with self.assertRaises(ValueError):
            self.s.normalizar_ligacoes([a, b])
        addon.eventos._desfazendo[0] = False
        bpy.ops.object.select_all(action='DESELECT')
        a.select_set(True)
        bpy.context.view_layer.objects.active = a
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            with self.assertRaises(ValueError):
                self.s.normalizar_ligacoes([a, b])
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        self.assertEqual(len(self.arestas()), 2)

    def test_compatibilidade_preserva_origem_e_direcao_do_mesmo_indice(self):
        a, b = self.chapa('A'), self.chapa('B', 430)
        self.legado(a, 'x_pos', b)
        a['adj_x_pos_manual'] = True
        self.s._gravar_ancoras(a, 'x_pos', [('v0', 'v7'), ('v0', 'v0')])
        a['adj_x_pos_origens'] = json.dumps([(1, 2, 3), (4, 5, 6)])
        a['adj_x_pos_direcoes'] = json.dumps([(1, 0, 0), (0, 1, 0)])
        self.s.normalizar_ligacoes([a, b])
        self.assertEqual(self.s._ancoras_gravadas(a, 'x_pos'), [('v0', 'v0')])
        self.assertEqual(json.loads(a['adj_x_pos_origens']), [[4, 5, 6]])
        self.assertEqual(json.loads(a['adj_x_pos_direcoes']), [[0, 1, 0]])

    def test_undo_redo_normaliza_no_timer_sem_reter_objetos_liberados(self):
        a, b = self.chapa('A'), self.chapa('B', 430)
        self.legado(a, 'x_pos', b)
        self.legado(b, 'x_neg', a)
        bpy.ops.ed.undo_push(message='Soldas antigas')
        self.s.normalizar_ligacoes([a, b])
        bpy.ops.ed.undo_push(message='Solda unica')
        a = b = None
        for _ in range(2):
            bpy.ops.ed.undo()
            self.assertEqual(len(self.arestas()), 2)
            self.s.normalizar_pendentes()
            self.assertEqual(len(self.arestas()), 2)
            addon.eventos._fim_do_desfazer()
            self.s.normalizar_pendentes()
            self.assertEqual(len(self.arestas()), 1)
            bpy.ops.ed.redo()
            addon.eventos._fim_do_desfazer()
            self.s.normalizar_pendentes()
            self.assertEqual(len(self.arestas()), 1)

    def test_vertice_nativo_estavel_conserva_parceiro_da_espessura(self):
        a = self.chapa('Chapa subdividida')
        bm = bmesh.new()
        try:
            bm.from_mesh(a.data)
            bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=1, use_grid_fill=True)
            bm.to_mesh(a.data)
        finally:
            bm.free()
        a.data.update()
        assinatura = self.s._ancora_estavel(a, 'v0')
        self.assertTrue(assinatura.startswith('u'))
        parceiro = self.s._parceiro_espessura(a, assinatura)
        self.assertTrue(self.s._indices_da_assinatura(a, parceiro))
        self.assertNotEqual(assinatura, parceiro)
        distancia = (self.s._vertice_da_assinatura(a, assinatura)-self.s._vertice_da_assinatura(a, parceiro)).length
        self.assertAlmostEqual(distancia, .018, places=6)


addon.register()
resultado = unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(TestSoldaUnica))
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError("Unique-weld tests failed")
