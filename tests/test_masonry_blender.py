"""Classificacao, cotas e vinculos em cenas descartaveis."""
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon

A = addon.alvenaria
P = addon.paredes


class TestAlvenaria(unittest.TestCase):
    def setUp(self):
        addon.eventos._fim_do_desfazer()
        addon.ambientes.encerrar_selecao()
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add(size=4)
        self.apoio = bpy.context.object
        A.esquecer()

    def tearDown(self):
        addon.ambientes.encerrar_selecao()
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

    def marcar_faces(self, indices):
        bm = bmesh.from_edit_mesh(self.apoio.data)
        for i, face in enumerate(bm.faces):
            face.select_set(i in indices)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(self.apoio.data, loop_triangles=False, destructive=False)
        addon.ambientes.guardar_selecao(self.apoio)

    def valores(self):
        camada = self.apoio.data.attributes.get(A.ATR_TIPO)
        return [f.value for f in camada.data] if camada else []

    def test_classifica_tipos_independentes_sem_recriar_malha(self):
        dados = self.apoio.data
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(dados)
        for i, tipo in enumerate(A.TIPOS):
            for n, face in enumerate(bm.faces):
                face.select_set(n == i)
            self.assertEqual(bpy.ops.object.cabinet_classificar_alvenaria(tipo=tipo),
                             {'FINISHED'})
        bpy.ops.object.mode_set(mode='OBJECT')
        self.assertIs(self.apoio.data, dados)
        self.assertEqual([A.superficie(self.apoio, i, (0, 0, 1)) for i in range(4)],
                         ['PAREDE', 'PISO', 'TETO', None])

    def test_alvenaria_legada_usa_normal(self):
        self.apoio[P.CHAVE_ALVENARIA] = True
        self.assertEqual([A.superficie(self.apoio, 0, n) for n in
                          ((0, -1, 0), (0, 0, 1), (0, 0, -1))],
                         list(A.TIPOS))

    def test_cotas_e_vinculo_acompanham_transformacao_rigida(self):
        obj = self.vinculado()
        antes = A.cotas(obj)
        self.assertAlmostEqual(antes['esquerda'], 1.5)
        self.assertIsNone(A.editar_cota(obj, 'esquerda', .25))
        self.assertAlmostEqual(A.cotas(obj)['esquerda'], .25)
        posicao = obj.matrix_world.translation.copy()
        self.apoio.location.x += 3
        bpy.context.view_layer.update()
        A.verificar()
        self.assertAlmostEqual(obj.matrix_world.translation.x, posicao.x + 3)
        self.assertAlmostEqual(A.cotas(obj)['esquerda'], .25)

    def test_remover_face_preserva_ultima_pose(self):
        obj = self.vinculado()
        antes = obj.matrix_world.copy()
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(self.apoio.data)
        camada = bm.faces.layers.int[A.ATR_FACE]
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f[camada]], context='FACES')
        bmesh.update_edit_mesh(self.apoio.data)
        bpy.ops.object.mode_set(mode='OBJECT')
        A.esquecer()
        A.verificar()
        self.assertTrue(obj[A.CHAVE_SEM_APOIO])
        self.assertEqual(obj.matrix_world, antes)

    def test_menu_em_tres_larguras_conserva_tipos_na_mesma_linha(self):
        tela = bpy.context.screen
        tela[A.CHAVE_ABRIR] = True
        try:
            for largura in (190, 320, 564):
                itens = []
                A.widgets_classificar(bpy.context, itens, 12, 500, largura - 24)
                self.assertEqual([v[4] for v in itens], ['Criar Alvenaria', 'Parede', 'Piso', 'Teto'])
                self.assertEqual(len({v[1] for v in itens[1:]}), 1)
                self.assertAlmostEqual(itens[-1][0] + itens[-1][2], largura - 12)
        finally:
            del tela[A.CHAVE_ABRIR]

    def test_nova_alvenaria_so_e_gravada_ao_confirmar_pelo_menu(self):
        malha = self.apoio.data
        A.iniciar_edicao(bpy.context, 'PAREDE')
        self.marcar_faces([0, 1, 2, 3])
        self.assertFalse(P.alvenaria_definida(self.apoio))
        self.assertEqual(bpy.context.scene.cabinet_aba, 'ALVENARIA')
        itens = addon.gaveta._widgets_aba_gaveta(bpy.context, 320, 1100, 0)
        self.assertIn(('operador', 'object.cabinet_confirmar_alvenaria'), [v[5] for v in itens])
        self.assertEqual(bpy.ops.object.cabinet_confirmar_alvenaria(), {'FINISHED'})
        self.assertEqual(self.valores(), [1, 1, 1, 1, 0, 0])
        self.assertIs(self.apoio.data, malha)
        self.assertIsNone(addon.ambientes._edicao_faces[0])

    def test_enter_confirma_o_mesmo_registro_do_botao(self):
        token = A.iniciar_edicao(bpy.context, 'TETO')
        self.marcar_faces([5])
        s = addon.ambientes._edicao_faces[0]
        area = next(a for a in bpy.context.screen.areas if a.as_pointer() == s['area'])
        regiao = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(area=area, region=regiao):
            resultado = addon.ambientes.evento_selecao(bpy.context,
                         SimpleNamespace(type='RET', value='PRESS'), token)
        self.assertEqual(resultado, {'FINISHED'})
        self.assertEqual(self.valores(), [0, 0, 0, 0, 0, 3])

    def test_confirmacao_le_selecao_nativa_sem_esperar_timer(self):
        # Regressao (era BUG, corrigido na 403): o timer ainda nao viu o A nativo.
        A.iniciar_edicao(bpy.context, 'PAREDE')
        bpy.ops.mesh.select_all(action='SELECT')
        self.assertEqual(addon.ambientes._edicao_faces[0]['selecionadas'], ())
        self.assertEqual(bpy.ops.object.cabinet_confirmar_alvenaria(), {'FINISHED'})
        self.assertEqual(self.valores(), [1]*6)

    def test_seletor_de_tipos_ignora_categoria_e_soma_faces_nativas(self):
        camada = self.apoio.data.attributes.new(addon.ambientes.ATR_FACE, 'INT', 'FACE')
        for valor in camada.data:
            valor.value = 1
        A.iniciar_edicao(bpy.context, 'PAREDE')
        s = addon.ambientes._edicao_faces[0]
        self.assertEqual(s['grupos'][0], (0,))
        addon.ambientes.selecionar_face(bpy.context, self.apoio, 0)
        addon.ambientes.selecionar_face(bpy.context, self.apoio, 1, manual=True)
        self.assertEqual(set(s['selecionadas']), {0, 1})
        bpy.ops.object.cabinet_confirmar_alvenaria()
        self.assertEqual(self.valores(), [1, 1, 0, 0, 0, 0])
        self.assertEqual([v.value for v in self.apoio.data.attributes[addon.ambientes.ATR_FACE].data], [1]*6)

    def test_editar_carrega_tipo_e_remove_so_as_faces_desmarcadas(self):
        A.iniciar_edicao(bpy.context, 'PAREDE')
        self.marcar_faces([0, 1, 2, 3])
        bpy.ops.object.cabinet_confirmar_alvenaria()
        A.iniciar_edicao(bpy.context, 'PISO', editar=True)
        self.marcar_faces([4])
        bpy.ops.object.cabinet_confirmar_alvenaria()
        A.iniciar_edicao(bpy.context, 'PAREDE', editar=True)
        self.assertEqual(set(addon.ambientes._edicao_faces[0]['selecionadas']), {0, 1, 2, 3})
        self.marcar_faces([0, 2, 3])
        bpy.ops.object.cabinet_confirmar_alvenaria()
        self.assertEqual(self.valores(), [1, 0, 1, 1, 2, 0])

    def test_editar_legado_materializa_classificacao_sem_apagar_outros_tipos(self):
        self.apoio[P.CHAVE_ALVENARIA] = True
        A.iniciar_edicao(bpy.context, 'PAREDE', editar=True)
        bm = bmesh.from_edit_mesh(self.apoio.data)
        for face in bm.faces:
            face.select_set(False)
        addon.ambientes.guardar_selecao(self.apoio)
        bpy.ops.object.cabinet_confirmar_alvenaria()
        self.assertEqual(sorted(self.valores()), [0, 0, 0, 0, 2, 3])

    def test_criar_com_selecao_mista_escolhe_so_objeto_novo_mesmo_com_ativo_cadastrado(self):
        novo = self.apoio
        bpy.ops.mesh.primitive_cube_add(size=2)
        existente = bpy.context.object
        existente[P.CHAVE_ALVENARIA] = True
        antes = dict(existente.items())
        novo.select_set(True)
        self.assertIs(A.alvo_novo(bpy.context), novo)
        bpy.context.scene.cabinet_aba = 'ALVENARIA'
        itens = addon.gaveta._widgets_aba_gaveta(bpy.context, 564, 1400, 0)
        self.assertIn('Criar Alvenaria', [v[4] for v in itens])
        self.assertNotIn('Editar', [v[4] for v in itens])
        A.iniciar_edicao(bpy.context, 'PISO')
        self.assertIs(bpy.context.edit_object, novo)
        self.marcar_faces([0])
        bpy.ops.object.cabinet_confirmar_alvenaria()
        self.assertEqual(dict(existente.items()), antes)
        self.assertNotIn(A.ATR_TIPO, existente.data.attributes)
        self.assertEqual(self.valores(), [2, 0, 0, 0, 0, 0])

    def test_esc_cancela_sem_cadastrar_ou_alterar_faces(self):
        token = A.iniciar_edicao(bpy.context, 'PAREDE')
        self.marcar_faces([0, 1])
        s = addon.ambientes._edicao_faces[0]
        area = next(a for a in bpy.context.screen.areas if a.as_pointer() == s['area'])
        regiao = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(area=area, region=regiao):
            resultado = addon.ambientes.evento_selecao(bpy.context,
                        SimpleNamespace(type='ESC', value='PRESS'), token)
        self.assertEqual(resultado, {'CANCELLED'})
        self.assertFalse(P.alvenaria_definida(self.apoio))
        self.assertNotIn(A.ATR_TIPO, self.apoio.data.attributes)

    def test_cores_e_nomes_somente_no_editor_de_tipos(self):
        A.iniciar_edicao(bpy.context, 'PAREDE')
        self.marcar_faces([0, 1, 2, 3])
        A.atualizar_visual(self.apoio)
        s = addon.ambientes._edicao_faces[0]
        self.assertEqual({f['tipo'] for f in s['visual_tipos']['faces']}, {'PAREDE'})
        self.assertEqual(len(s['visual_tipos']['faces']), 4)
        with patch.object(A, 'gpu'), patch.object(A, 'batch_for_shader'), \
             patch.object(addon.ambientes, '_rotulo') as rotulo:
            A.desenhar_visual(bpy.context, self.apoio)
            self.assertEqual([c.args[3] for c in rotulo.call_args_list], ['Paredes']*4)
        bpy.ops.object.cabinet_confirmar_alvenaria()
        with patch.object(A, 'gpu') as gpu:
            A.desenhar_visual(bpy.context, self.apoio)
            self.assertFalse(gpu.mock_calls)
        bpy.ops.object.cabinet_editar_ambientes()
        with patch.object(A, 'gpu') as gpu:
            A.desenhar_visual(bpy.context, self.apoio)
            self.assertFalse(gpu.mock_calls)

    def test_aba_alvenaria_separa_instalacoes_e_modulos_preserva_editores(self):
        self.apoio[P.CHAVE_ALVENARIA] = True
        for aba in ('MODULOS', 'ALVENARIA'):
            bpy.context.scene.cabinet_aba = aba
            itens = addon.gaveta._widgets_aba_gaveta(bpy.context, 564, 1400, 0)
            nomes = [v[4] for v in itens]
            self.assertNotIn('Criar Alvenaria', nomes)
            if aba == 'MODULOS':
                self.assertIn('Editar em 2D', nomes)
                self.assertIn('Editar categorias', nomes)
                self.assertNotIn('Instalacoes', nomes)
            else:
                self.assertIn('Editar', nomes)
                self.assertIn('Instalacoes', nomes)
                self.assertNotIn('Editar em 2D', nomes)
                tipos = next(i for i,v in enumerate(itens) if v[5] and v[5][:2] == ('escolha','tipo_instalacao'))
                editar = next(i for i,v in enumerate(itens) if v[4] == 'Editar')
                self.assertLess(editar, tipos)
                olho = next(v for v in itens if v[5] and v[5][:2] == ('escolha','alvenaria_visual'))
                self.assertEqual(olho[1], itens[tipos][1])

    def test_criar_aparece_primeiro_para_nao_cadastrada_e_some_apos_cadastro(self):
        for largura in (190, 320, 564):
            bpy.context.scene.cabinet_aba = 'MODULOS'
            itens = addon.gaveta._widgets_aba_gaveta(bpy.context, largura, 1400, 0)
            topo = addon.gaveta._tamanho_cabecalho(itens)
            self.assertEqual(itens[topo][4], 'Criar Alvenaria')
        self.apoio[P.CHAVE_ALVENARIA] = True
        itens = []
        A.widgets_classificar(bpy.context, itens, 12, 500, 296)
        self.assertEqual(itens, [])

    def vinculado(self):
        self.apoio[P.CHAVE_ALVENARIA] = True
        face = next(f for f in self.apoio.data.polygons if f.normal.y < -.9)
        obj = bpy.data.objects.new('Instalacao de prova', None)
        bpy.context.collection.objects.link(obj)
        obj[A.MARCA] = 'PROVA'
        obj['cabinet_instalacao_medidas'] = (1., 1., .1)
        A.vincular(obj, self.apoio, face.index,
                   A.referencial(Vector((0, -2, 0)), face.normal), 'PAREDE')
        bpy.context.view_layer.update()
        return obj


with tempfile.TemporaryDirectory(prefix='alvenaria_') as pasta, \
     patch.object(addon.opcoes, '_pasta_addon', return_value=pasta), \
     patch.object(addon.biblioteca, 'pasta_biblioteca', return_value=pasta):
    addon.register()
    try:
        resultado = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(TestAlvenaria))
    finally:
        addon.unregister()
    if not resultado.wasSuccessful():
        raise RuntimeError('Falha nas provas de alvenaria')
