"""Divisorias: divisao de vao, madeira nativa e sistemas independentes."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from mathutils import Matrix, Vector
import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon
D, G, P = addon.divisorias, addon.gavetas, addon.prateleiras


class TestDivisorias(unittest.TestCase):
    def setUp(self):
        addon.eventos._desfazendo[0] = False
        addon.chapas._ocupado[0] = False
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for c in list(bpy.data.collections):
            bpy.data.collections.remove(c)
        bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection
        bpy.context.view_layer.update()
        self.conj = addon.modulos.criar_armario(bpy.context, 'Caixa teste', 1000, 1200, 550)
        bpy.context.view_layer.update()
        self.lo, self.hi = G._limites(self.conj)

    def sistemas(self):
        # Maleiro no alto, tres gavetas embaixo; vao total da caixa.
        g = G.criar_gavetas(bpy.context, self.conj, (18, 18, 18, 582, 0),
            dict(quantidade=3, profundidade_mm=500, cobertura='EMBUTIDA', puxador='SEM'))
        p = P.criar_prateleiras(bpy.context, self.conj, (18, 18, 18, 18, 0),
            dict(quantidade=1, profundidade_mm=500, espacamento='LIVRE', vaos_mm=[950]))
        return g, p

    def criar(self, n=1, **p):
        return D.criar_divisorias(bpy.context, self.conj, (18, 18, 18, 18, 0),
            dict(quantidade=n, profundidade_mm=500, **p))

    def test_criar_divisorias_usa_assistente_e_snap_nativos(self):
        self.assertTrue(issubclass(D.OBJECT_OT_criar_divisorias, G.AssistenteDoVao))
        self.assertIn(D.OBJECT_OT_criar_divisorias, addon.CLASSES)
        estado = {'etapa': 'CANTO1'}
        D._assistente_divisorias[0] = estado
        try:
            self.assertIs(G._estado_criacao(), estado)
        finally:
            D.esquecer()
        grupo = self.criar()
        chapa, = D.pecas(grupo)
        self.assertAlmostEqual(chapa.chapa_espessura_mm, 18, places=3)
        self.assertTrue(all(abs(s - 1) < 1e-6 for s in chapa.scale))

    def test_tres_gavetas_viram_seis_e_maleiro_duas_prateleiras(self):
        g, p = self.sistemas()
        malha = P.prateleiras_do_grupo(p)[0].data.as_pointer()
        self.criar()
        gs, ps = G.grupos_do_modulo(self.conj), P.grupos_do_modulo(self.conj)
        self.assertEqual(len(gs), 2)
        self.assertEqual(sum(len(G.gavetas_do_grupo(o)) for o in gs), 6)
        self.assertEqual(sum(len(P.prateleiras_do_grupo(o)) for o in ps), 2)
        for o in gs + ps:
            dono = G if G.MARCA_GRUPO in o else P
            self.assertAlmostEqual(dono.vao(o)[0], 473, delta=.01)
        self.assertEqual(P.prateleiras_do_grupo(p)[0].data.as_pointer(), malha)
        f0 = G.frente_da_gaveta(G.gavetas_do_grupo(gs[0])[0])
        f1 = G.frente_da_gaveta(G.gavetas_do_grupo(gs[1])[0])
        self.assertIsNot(f0.data, f1.data)

    def test_varias_divisorias_repartem_a_espessura_correta(self):
        self.sistemas()
        grupo = self.criar(2)
        self.assertEqual(len(D.pecas(grupo)), 2)
        self.assertEqual(sum(len(G.gavetas_do_grupo(g)) for g in G.grupos_do_modulo(self.conj)), 9)
        for g in G.grupos_do_modulo(self.conj):
            self.assertAlmostEqual(G.vao(g)[0], (964 - 36) / 3, delta=.01)

    def test_sistemas_criados_depois_respeitam_a_divisoria(self):
        self.criar()
        self.sistemas()
        self.assertEqual(sum(len(G.gavetas_do_grupo(g)) for g in G.grupos_do_modulo(self.conj)), 6)
        self.assertEqual(sum(len(P.prateleiras_do_grupo(g)) for g in P.grupos_do_modulo(self.conj)), 2)

    def test_sistemas_novos_respeitam_divisorias_criadas_separadamente(self):
        self.criar(vaos_mm=[300, 646])
        self.criar(vaos_mm=[646, 300])
        self.sistemas()
        self.assertEqual(sum(len(G.gavetas_do_grupo(g)) for g in G.grupos_do_modulo(self.conj)), 9)
        self.assertEqual(sum(len(P.prateleiras_do_grupo(g)) for g in P.grupos_do_modulo(self.conj)), 3)

    def test_falha_de_espaco_nao_modifica_cena(self):
        self.sistemas()
        nomes = set(bpy.data.objects.keys())
        geometrias = {o.name: [tuple(v.co) for v in o.data.vertices]
                      for o in bpy.data.objects if o.type == 'MESH'}
        with self.assertRaises(ValueError):
            self.criar(10)
        self.assertEqual(set(bpy.data.objects.keys()), nomes)
        for nome, coords in geometrias.items():
            self.assertEqual([tuple(v.co) for v in bpy.data.objects[nome].data.vertices], coords)

    def test_material_espessura_topologia_e_altura_da_prateleira_preservados(self):
        _g, p = self.sistemas()
        prateleira, = P.prateleiras_do_grupo(p)
        mat = bpy.data.materials.new('Madeira teste')
        prateleira.data.materials.append(mat)
        z = prateleira.matrix_world.translation.z
        self.criar()
        for grupo in P.grupos_do_modulo(self.conj):
            obj, = P.prateleiras_do_grupo(grupo)
            self.assertIs(obj.material_slots[0].material, mat)
            self.assertAlmostEqual(obj.chapa_espessura_mm, 18, delta=.01)
            self.assertAlmostEqual(obj.matrix_world.translation.z, z, delta=1e-6)
            bm = bmesh.new()
            try:
                bm.from_mesh(obj.data)
                self.assertTrue(all(e.is_manifold for e in bm.edges))
                self.assertGreater(bm.calc_volume(), 0)
            finally:
                bm.free()

    def test_configuracoes_individuais_e_abertura_sao_copiadas(self):
        g, _p = self.sistemas()
        p = G.parametros(g)
        p['proporcoes'] = [1, 2, 1]
        p['individuais'] = {'1': {'recuo_mm': 5}}
        g[G.CHAVE_PARAMETROS] = p
        G.montar(g)
        G.definir_abertura(G.gavetas_do_grupo(g)[1], .5)
        self.criar()
        for grupo in G.grupos_do_modulo(self.conj):
            q = G.parametros(grupo)
            self.assertEqual(q['proporcoes'], [1, 2, 1])
            self.assertEqual(q['individuais']['1']['recuo_mm'], 5)
            self.assertAlmostEqual(G.gavetas_do_grupo(grupo)[1][G.CHAVE_ABERTURA], .5)

    def test_divisoria_parcial_separa_so_prateleiras_atingidas(self):
        p = P.criar_prateleiras(bpy.context, self.conj, (18, 18, 18, 18, 0),
            dict(quantidade=3, profundidade_mm=500))
        antes = [(o.name, o.matrix_world.copy(), o.data.as_pointer())
                 for o in P.prateleiras_do_grupo(p)]
        D.criar_divisorias(bpy.context, self.conj, (18, 18, 18, 650, 0),
                          dict(quantidade=1, profundidade_mm=500))
        grupos = P.grupos_do_modulo(self.conj)
        self.assertEqual(sum(len(P.prateleiras_do_grupo(g)) for g in grupos), 4)
        for nome, matriz, mesh in antes[1:]:
            obj = bpy.data.objects[nome]
            self.assertEqual(obj.matrix_world, matriz)
            self.assertEqual(obj.data.as_pointer(), mesh)

    def test_resize_do_modulo_mantem_divisoria_e_sistemas_encostados(self):
        self.sistemas()
        grupo = self.criar()
        self.conj.conj_largura_mm = 1200
        addon.modulos.absorver_conjuntos()
        D.atualizar_dependentes()
        for g in G.grupos_do_modulo(self.conj):
            self.assertAlmostEqual(G.vao(g)[0], 573, delta=.02)
        self.assertAlmostEqual(D.pecas(grupo)[0].chapa_espessura_mm, 18, delta=.01)

    def test_outro_modulo_e_sistemas_fora_do_corte_nao_mudam(self):
        outro = addon.modulos.criar_armario(bpy.context, 'Vizinho teste', 600, 800, 400)
        grupo = P.criar_prateleiras(bpy.context, outro, (18, 18, 18, 18, 0),
                                    dict(quantidade=1, profundidade_mm=350))
        objeto = P.prateleiras_do_grupo(grupo)[0]
        antes = (objeto.data.as_pointer(), objeto.matrix_world.copy())
        self.criar()
        self.assertEqual(len(P.grupos_do_modulo(outro)), 1)
        self.assertEqual((objeto.data.as_pointer(), objeto.matrix_world), antes)

    def test_puxadores_seguem_as_seis_frentes_sem_compartilhar_malhas(self):
        g, _p = self.sistemas()
        p = G.parametros(g)
        p['puxador'] = 'PERFIL'
        g[G.CHAVE_PARAMETROS] = p
        for gaveta in G.gavetas_do_grupo(g):
            G.colocar_puxador(gaveta, 'PERFIL')
        self.criar()
        puxadores = [o for grupo in G.grupos_do_modulo(self.conj)
                     for o in grupo.children_recursive if addon.puxadores._eh_puxador_parametrico(o)]
        self.assertEqual(len(puxadores), 6)
        self.assertEqual(len({o.data.as_pointer() for o in puxadores}), 6)
        for pux in puxadores:
            self.assertIsNotNone(G.gaveta_de(pux))
            addon.puxadores.posicionar_puxador(pux)

    def test_invalidar_um_campo_nao_deixa_sistemas_parcialmente_redimensionados(self):
        self.sistemas()
        grupo = self.criar()
        antes = [(o.name, G.vao(o)[0], o.matrix_basis.copy()) for o in G.grupos_do_modulo(self.conj)]
        self.assertIsNotNone(D.editar(bpy.context, grupo, 'vao_0', 80))
        for nome, largura, pose in antes:
            o = bpy.data.objects[nome]
            self.assertAlmostEqual(G.vao(o)[0], largura, delta=.01)
            self.assertEqual(o.matrix_basis, pose)

    def test_modulo_girado_divide_no_seu_referencial(self):
        self.conj.rotation_euler.z = .7
        self.conj.location = (2, 3, 1)
        bpy.context.view_layer.update()
        self.sistemas()
        self.criar()
        for grupo in G.grupos_do_modulo(self.conj):
            self.assertAlmostEqual(G.vao(grupo)[0], 473, delta=.01)

    def test_copia_nativa_conserva_inversa_de_parentesco_de_presets(self):
        _g, p = self.sistemas()
        chapa = P.prateleiras_do_grupo(p)[0]
        matriz = chapa.matrix_basis.copy()
        chapa.matrix_parent_inverse = Matrix.Translation((.1, -.2, .05))
        chapa.matrix_basis = chapa.matrix_parent_inverse.inverted() @ matriz
        bpy.context.view_layer.update()
        antes = chapa.matrix_world.copy()
        copia = D._duplicar(p)
        bpy.context.view_layer.update()
        obj = P.prateleiras_do_grupo(copia)[0]
        for r, s in zip(obj.matrix_world, antes):
            for x, y in zip(r, s):
                self.assertAlmostEqual(x, y, delta=1e-6)
        for o in [*copia.children_recursive, copia]:
            G._remover(o)
        self.criar()
        for grupo in P.grupos_do_modulo(self.conj):
            self.assertAlmostEqual(P.prateleiras_do_grupo(grupo)[0].matrix_world.translation.z,
                                   antes.translation.z, delta=1e-6)

    def test_gap_e_espessura_atualizam_os_apoios(self):
        self.sistemas()
        grupo = self.criar()
        self.assertIsNone(D.editar(bpy.context, grupo, 'vao_0', 400))
        self.assertEqual(sorted(round(G.vao(g)[0]) for g in G.grupos_do_modulo(self.conj)), [400, 546])
        self.assertIsNone(D.editar(bpy.context, grupo, 'espessura_mm', 22))
        self.assertEqual(sorted(round(G.vao(g)[0]) for g in G.grupos_do_modulo(self.conj)), [471, 471])

    def test_restaurar_campo_devolve_divisoria_e_sistemas(self):
        self.sistemas()
        grupo = self.criar()
        estado = D.copia(grupo)
        D.editar(bpy.context, grupo, 'vao_0', 400)
        D.restaurar(estado)
        for g in G.grupos_do_modulo(self.conj):
            self.assertAlmostEqual(G.vao(g)[0], 473, delta=.01)

    def test_aba_campos_selecao_e_limites_do_menu(self):
        grupo = self.criar()
        D.selecionar(bpy.context, D.pecas(grupo)[0])
        self.assertEqual(addon.selecao._aba_da_selecao(bpy.context.object), 'DIVISORIAS')
        for largura in (190, 320, 482, 564):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1600)
            self.assertTrue(any(w[5] and w[5][0] == 'divisorias' for w in widgets))
            campos = [w for w in widgets if w[5] and w[5][:2] == ('medida', 'divisorias')]
            self.assertGreaterEqual(len(campos), 7)
            self.assertTrue(all(w[0] + w[2] <= min(largura - 12, 552) + .01 for w in campos))

    def test_undo_redo_restaura_quantidades_e_malhas_nativas(self):
        self.sistemas()
        nomes = set(bpy.data.objects.keys())
        bpy.ops.ed.undo_push(message='Antes de dividir')
        self.criar()
        bpy.ops.ed.undo_push(message='Vao dividido')
        self.conj = None
        bpy.ops.ed.undo()
        addon.eventos._fim_do_desfazer()
        self.assertEqual(set(bpy.data.objects.keys()), nomes)
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        self.conj = next(o for o in bpy.data.objects if addon.chapas.MARCA_CONJUNTO in o)
        self.assertEqual(sum(len(G.gavetas_do_grupo(g)) for g in G.grupos_do_modulo(self.conj)), 6)


with tempfile.TemporaryDirectory(prefix='cabinet_divisorias_') as pasta:
    with patch.object(addon.biblioteca, 'pasta_biblioteca', return_value=pasta), \
         patch.object(addon.opcoes, '_pasta_addon', return_value=pasta):
        addon.register()
        try:
            resultado = unittest.TextTestRunner(verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(TestDivisorias))
        finally:
            addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de divisorias')
