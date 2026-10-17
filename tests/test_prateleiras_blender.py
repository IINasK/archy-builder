"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_prateleiras_blender.py

Prateleiras internas (pedido do usuario): grupo de prateleiras num vao do
modulo, criado como as gavetas (2 cliques na diagonal, scroll = quantas,
mouse = profundidade), com aba propria: quantidade, espessura, o
espacamento entre elas e o de CADA uma (na aba e na HUD).

O assistente com eventos de verdade esta' em `gui_interacao.py`.
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

P = addon.prateleiras


class TestPrateleiras(unittest.TestCase):
    def test_aviso_de_referencia_segue_mouse_e_troca_de_viewport(self):
        primeira = SimpleNamespace(type='WINDOW', x=300, y=100, width=600, height=500,
                                  as_pointer=lambda: 123)
        segunda = SimpleNamespace(type='WINDOW', x=900, y=100, width=400, height=500,
                                 as_pointer=lambda: 456)
        ctx = SimpleNamespace(screen=SimpleNamespace(areas=[
            SimpleNamespace(type='VIEW_3D', regions=[primeira]),
            SimpleNamespace(type='VIEW_3D', regions=[segunda])]))
        P._referencia_pendente[0] = dict(grupo='Grupo', quantidade=5, regiao=None, mouse=None)
        with patch.object(addon.gaveta_eventos, '_gaveta_sob_evento', return_value=None), \
             patch.object(addon.eventos, '_redesenhar_viewports') as redesenhar:
            for x, y, regiao, esperado in ((410, 290, 123, (110, 190)),
                                           (470, 330, 123, (170, 230)),
                                           (1000, 400, 456, (100, 300))):
                evento = SimpleNamespace(type='MOUSEMOVE', mouse_x=x, mouse_y=y)
                resultado = P.OBJECT_OT_referencia_prateleira.modal(None, ctx, evento)
                self.assertEqual(resultado, {'PASS_THROUGH'})
                pedido = P._referencia_pendente[0]
                self.assertEqual(tuple(pedido['mouse']), esperado)
                self.assertEqual(pedido['regiao'], regiao)
                self.assertEqual(pedido['recado'], 'Selecione a prateleira de referencia')
                self.assertEqual(pedido['quantidade'], 5)
            self.assertEqual(redesenhar.call_count, 3)

    def test_aviso_de_referencia_some_fora_da_viewport_e_sobre_o_menu(self):
        regiao = SimpleNamespace(type='WINDOW', x=300, y=100, width=600, height=500,
                                 as_pointer=lambda: 123)
        ctx = SimpleNamespace(screen=SimpleNamespace(areas=[
            SimpleNamespace(type='VIEW_3D', regions=[regiao])]))
        P._referencia_pendente[0] = dict(grupo='Grupo', quantidade=5, regiao=123,
                                         mouse=Vector((50, 60)))
        with patch.object(addon.eventos, '_redesenhar_viewports'), \
             patch.object(addon.gaveta_eventos, '_gaveta_sob_evento', return_value=None):
            P.atualizar_aviso_referencia(ctx, SimpleNamespace(mouse_x=50, mouse_y=50))
            self.assertIsNone(P._referencia_pendente[0]['regiao'])
            self.assertIsNone(P._referencia_pendente[0]['mouse'])
            P.atualizar_aviso_referencia(ctx, SimpleNamespace(mouse_x=450, mouse_y=350))
            self.assertEqual(tuple(P._referencia_pendente[0]['mouse']), (150, 250))
        with patch.object(addon.eventos, '_redesenhar_viewports'), \
             patch.object(addon.gaveta_eventos, '_gaveta_sob_evento', return_value=('menu', 'regiao')):
            P.atualizar_aviso_referencia(ctx, SimpleNamespace(mouse_x=450, mouse_y=350))
            self.assertIsNone(P._referencia_pendente[0]['mouse'])
            self.assertIsNone(P._referencia_pendente[0]['regiao'])

    def test_aumento_reparte_vaos_pela_espessura_real_da_matriz(self):
        grupo = self.prateleiras()
        atuais = P.prateleiras_do_grupo(grupo)
        for obj in atuais:
            P.selecionar(bpy.context, obj, 'PRATELEIRA')
            self.assertIsNone(P.editar(bpy.context, grupo, 'espessura_mm', 80))
        P.selecionar(bpy.context, grupo, 'GRUPO')
        self.assertIsNone(P.editar(bpy.context, grupo, 'entre_mm', 80))
        P.selecionar(bpy.context, atuais[1], 'PRATELEIRA')
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 5))
        self.assertEqual(P.parametros(grupo)['espacamento'], 'IGUAL')
        self.assertTrue(all(abs(o.chapa_espessura_mm - 80) < .001
                            for o in P.prateleiras_do_grupo(grupo)))
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 5)

    def test_arrastar_quantidade_exibe_previa_sem_montar_e_esc_cancela(self):
        grupo = self.prateleiras()
        P.selecionar(bpy.context, grupo, 'GRUPO')
        ev = addon.gaveta_eventos
        acao = ('contador', 'prateleiras_quantidade', 3, 1, 20, grupo.name, 'Prateleiras')
        op = SimpleNamespace(_campo=dict(acao=acao, x0=0, arrastou=False, valor=3, meio=20))
        ctx = SimpleNamespace(area=SimpleNamespace(tag_redraw=lambda: None))
        mover = SimpleNamespace(type='MOUSEMOVE', mouse_region_x=48)
        with patch.object(P, 'montar', wraps=P.montar) as montar:
            self.assertEqual(ev.OBJECT_OT_interagir_gaveta._modal_campo(op, ctx, mover), {'RUNNING_MODAL'})
            self.assertEqual(P._quantidade_previa[0], (grupo.name, 5))
            widgets = addon.gaveta._widgets_gaveta(bpy.context, 480, 1400)
            self.assertTrue(any(w[4] == '5' and w[5] and w[5][:2] == acao[:2] for w in widgets))
            self.assertEqual(P.parametros(grupo)['quantidade'], 3)
            cancelar = SimpleNamespace(type='ESC', value='PRESS')
            self.assertEqual(ev.OBJECT_OT_interagir_gaveta._modal_campo(op, ctx, cancelar), {'CANCELLED'})
            self.assertFalse(montar.called)
        self.assertIsNone(P._quantidade_previa[0])

    def test_undo_retorna_ao_edit_mode_com_escopo_global_e_redo_o_conserva(self):
        grupo = self.prateleiras()
        nome = grupo.name
        atuais = P.prateleiras_do_grupo(grupo)
        self.recortar(atuais[1])
        P.selecionar(bpy.context, grupo, 'GRUPO')
        bpy.ops.ed.undo_push(message='Antes de editar prateleiras')
        bpy.ops.object.cabinet_editar_grupo()
        self.editar_vertice_nativo(atuais[1])
        bpy.ops.ed.undo_push(message='Recorte global')
        bpy.ops.object.cabinet_editar_grupo()
        bpy.ops.ed.undo_push(message='Concluiu recorte')
        bpy.ops.ed.undo()
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        self.assertTrue(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
        self.assertIn(nome, P.edicao_atual(bpy.context)['globais'])
        bpy.ops.ed.redo()
        self.assertEqual(bpy.context.mode, 'OBJECT')
        P.concluir_edicao()
        grupo = bpy.data.objects[nome]
        self.assertIsNone(P._edicao[0])
        atuais = P.prateleiras_do_grupo(grupo)
        self.assertTrue(all(self.geometria(o) == self.geometria(atuais[0]) for o in atuais))
        bpy.ops.ed.undo()
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        self.assertTrue(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
        self.editar_vertice_nativo(bpy.context.object)
        bpy.ops.object.cabinet_editar_grupo()
        atuais = P.prateleiras_do_grupo(bpy.data.objects[nome])
        self.assertTrue(all(self.geometria(o) == self.geometria(atuais[0]) for o in atuais))

    def test_referencia_modal_clique_rejeita_corpo_e_retoma_no_mesmo_evento(self):
        grupo = self.prateleiras()
        fonte = P.prateleiras_do_grupo(grupo)[1]
        self.recortar(fonte)
        P.selecionar(bpy.context, grupo, 'GRUPO')
        P.editar(bpy.context, grupo, 'quantidade', 4)
        avisos = []
        op = SimpleNamespace(cancel=lambda ctx: P.OBJECT_OT_referencia_prateleira.cancel(None, ctx),
                             report=lambda tipo, texto: avisos.append(texto))
        evento = SimpleNamespace(type='LEFTMOUSE', value='PRESS')
        with patch.object(addon.gaveta_eventos, '_objeto_sob_mouse', return_value=self.conj.name):
            self.assertEqual(P.OBJECT_OT_referencia_prateleira.modal(op, bpy.context, evento), {'RUNNING_MODAL'})
        self.assertTrue(avisos)
        with patch.object(addon.gaveta_eventos, '_objeto_sob_mouse', return_value=fonte.name):
            self.assertEqual(P.OBJECT_OT_referencia_prateleira.modal(op, bpy.context, evento), {'FINISHED'})
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 4)
        self.assertEqual(self.geometria(P.prateleiras_do_grupo(grupo)[-1]), self.geometria(fonte))

    def test_matriz_unica_recortada_dispensa_escolha_sem_selecao_individual(self):
        grupo = self.prateleiras()
        atuais = P.prateleiras_do_grupo(grupo)
        for obj in atuais:
            self.recortar(obj)
        P.selecionar(bpy.context, grupo, 'GRUPO')
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 4))
        self.assertIsNone(P._referencia_pendente[0])
        self.assertEqual(self.geometria(P.prateleiras_do_grupo(grupo)[-1]), self.geometria(atuais[0]))

    def test_parametro_durante_tab_global_conclui_edicao_e_aplica_a_todas(self):
        grupo = self.prateleiras()
        P.selecionar(bpy.context, grupo, 'GRUPO')
        bpy.ops.object.cabinet_editar_grupo()
        self.assertIsNone(P.editar(bpy.context, grupo, 'profundidade_mm', 420))
        self.assertEqual(bpy.context.mode, 'OBJECT')
        self.assertTrue(all(abs(o.chapa_comprimento_mm - 420) < .001
                            for o in P.prateleiras_do_grupo(grupo)))

    def test_matrizes_individuais_reencaixam_na_profundidade_e_voltam_sem_perder_recorte(self):
        grupo = self.prateleiras()
        fonte = P.prateleiras_do_grupo(grupo)[1]
        self.recortar(fonte)
        P.selecionar(bpy.context, fonte, 'PRATELEIRA')
        P.editar(bpy.context, grupo, 'profundidade_mm', 420)
        P.editar(bpy.context, grupo, 'quantidade', 4)
        antes = [self.geometria(o) for o in P.prateleiras_do_grupo(grupo)]
        self.conj.conj_profundidade_mm = 100
        self.assertTrue(all(o.chapa_comprimento_mm <= 100.01
                            for o in P.prateleiras_do_grupo(grupo)))
        self.conj.conj_profundidade_mm = 560
        self.assertEqual([self.geometria(o) for o in P.prateleiras_do_grupo(grupo)], antes)

    def recortar(self, obj):
        # Um chanfro assimetrico distingue a geometria sem mudar a caixa.
        obj.data.vertices[0].co.x += .035
        obj.data.vertices[0].co.y += .025
        obj.data.update()

    def geometria(self, obj):
        return ([tuple(round(c, 7) for c in v.co) for v in obj.data.vertices],
                [tuple(f.vertices) for f in obj.data.polygons])

    def editar_vertice_nativo(self, obj):
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.verts[0].co.x += .037
        bm.verts[0].co.y += .021
        bmesh.update_edit_mesh(obj.data)

    def test_tab_individual_isola_malha_compartilhada_e_preserva_vizinhas(self):
        grupo = self.prateleiras()
        a, b, c = P.prateleiras_do_grupo(grupo)
        b.data = a.data
        antes = [self.geometria(o) for o in (a, c)]
        P.selecionar(bpy.context, b, 'PRATELEIRA')
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual(list(bpy.context.objects_in_mode), [b])
        self.editar_vertice_nativo(b)
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual([self.geometria(o) for o in (a, c)], antes)
        self.assertNotEqual(self.geometria(a), self.geometria(b))
        P.montar(grupo)
        self.assertNotEqual(self.geometria(a), self.geometria(b))

    def test_tab_modulo_propaga_recorte_sem_alterar_outro_modulo(self):
        grupo = self.prateleiras()
        fora = self.prateleiras()
        antes = [self.geometria(o) for o in P.prateleiras_do_grupo(fora)]
        # O segundo vao fica em outro modulo, mesmo que use o mesmo Mesh.
        outro = bpy.data.objects.new('Outro modulo', None)
        bpy.context.scene.collection.objects.link(outro)
        fora.parent = outro
        for o in bpy.context.selected_objects:
            o.select_set(False)
        self.conj.select_set(True)
        bpy.context.view_layer.objects.active = self.conj
        bpy.ops.object.cabinet_editar_grupo()
        atuais = P.prateleiras_do_grupo(grupo)
        ids_malha = [o.data.as_pointer() for o in atuais]
        self.editar_vertice_nativo(atuais[0])
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual([o.data.as_pointer() for o in atuais], ids_malha)
        self.assertTrue(all(self.geometria(o) == self.geometria(atuais[0]) for o in atuais))
        self.assertEqual([self.geometria(o) for o in P.prateleiras_do_grupo(fora)], antes)
        self.assertEqual(len({o.data.as_pointer() for o in atuais}), 3)

    def test_tab_global_com_tipos_diferentes_so_propaga_se_houver_edicao(self):
        grupo = self.prateleiras()
        atuais = P.prateleiras_do_grupo(grupo)
        self.recortar(atuais[1])
        antes = [self.geometria(o) for o in atuais]
        P.selecionar(bpy.context, grupo, 'GRUPO')
        bpy.ops.object.cabinet_editar_grupo()
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual([self.geometria(o) for o in atuais], antes)
        P.selecionar(bpy.context, grupo, 'GRUPO')
        bpy.ops.object.cabinet_editar_grupo()
        self.editar_vertice_nativo(atuais[1])
        # Saida pelo seletor nativo de modo tambem conclui no timer existente.
        bpy.ops.object.mode_set(mode='OBJECT')
        P.concluir_edicao()
        self.assertTrue(all(self.geometria(o) == self.geometria(atuais[1]) for o in atuais))

    def test_quantidade_herda_selecao_geometria_material_modificador_e_parametros(self):
        grupo = self.prateleiras()
        fonte = P.prateleiras_do_grupo(grupo)[1]
        self.recortar(fonte)
        P.selecionar(bpy.context, fonte, 'PRATELEIRA')
        P.editar(bpy.context, grupo, 'profundidade_mm', 425)
        fonte.modifiers.new('Arredondar', 'BEVEL').width = .002
        mat = bpy.data.materials.new('Madeira da matriz')
        fonte.data.materials.append(mat)
        esperado = self.geometria(fonte)
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 5))
        self.assertIsNone(P._referencia_pendente[0])
        atuais = P.prateleiras_do_grupo(grupo)
        for obj in atuais[3:]:
            self.assertEqual(self.geometria(obj), esperado)
            self.assertEqual(obj.modifiers[0].width, fonte.modifiers[0].width)
            self.assertEqual(obj.data.materials[0], mat)
            self.assertAlmostEqual(obj.chapa_comprimento_mm, 425)
            self.assertNotEqual(obj['chapa_uid'], fonte.get('chapa_uid'))
            self.assertNotEqual(obj.data, fonte.data)
        self.assertEqual(bpy.context.object, fonte)
        self.assertAlmostEqual(atuais[0].chapa_comprimento_mm, 540)

    def test_tipos_diferentes_pedem_referencia_e_so_adicionam_apos_clique_valido(self):
        grupo = self.prateleiras()
        fonte = P.prateleiras_do_grupo(grupo)[1]
        self.recortar(fonte)
        P.selecionar(bpy.context, grupo, 'GRUPO')
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 4))
        self.assertEqual(P.parametros(grupo)['quantidade'], 3)
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 3)
        self.assertIsNotNone(P._referencia_pendente[0])
        self.assertIsNotNone(P.resolver_referencia(bpy.context, self.conj))
        outro = self.prateleiras()
        self.assertIsNotNone(P.resolver_referencia(bpy.context, P.prateleiras_do_grupo(outro)[0]))
        self.assertIsNone(P.resolver_referencia(bpy.context, fonte))
        self.assertEqual(self.geometria(P.prateleiras_do_grupo(grupo)[-1]), self.geometria(fonte))
        self.assertIsNone(P._referencia_pendente[0])

    def test_referencia_modal_esc_nao_altera_quantidade_nem_geometria(self):
        grupo = self.prateleiras()
        self.recortar(P.prateleiras_do_grupo(grupo)[0])
        P.selecionar(bpy.context, grupo, 'GRUPO')
        antes = [self.geometria(o) for o in P.prateleiras_do_grupo(grupo)]
        P.editar(bpy.context, grupo, 'quantidade', 6)
        op = SimpleNamespace(cancel=lambda ctx: P.OBJECT_OT_referencia_prateleira.cancel(None, ctx))
        evento = SimpleNamespace(type='ESC', value='PRESS')
        self.assertEqual(P.OBJECT_OT_referencia_prateleira.modal(op, bpy.context, evento), {'CANCELLED'})
        self.assertIsNone(P._referencia_pendente[0])
        self.assertEqual(P.parametros(grupo)['quantidade'], 3)
        self.assertEqual([self.geometria(o) for o in P.prateleiras_do_grupo(grupo)], antes)
        self.assertIn(P.OBJECT_OT_referencia_prateleira, addon.CLASSES)

    def test_parametros_individuais_nao_movem_nem_redimensionam_as_vizinhas(self):
        grupo = self.prateleiras()
        a, b, c = P.prateleiras_do_grupo(grupo)
        P.selecionar(bpy.context, b, 'PRATELEIRA')
        antes = [(self.geometria(o), o.matrix_basis.copy()) for o in (a, c)]
        for campo, valor in (('espessura_mm', 30), ('profundidade_mm', 420),
                             ('recuo_mm', 15), ('largura_mm', 700)):
            self.assertIsNone(P.editar(bpy.context, grupo, campo, valor))
        self.assertEqual([(self.geometria(o), o.matrix_basis) for o in (a, c)], antes)
        self.assertAlmostEqual(b.chapa_espessura_mm, 30)
        self.assertAlmostEqual(b.chapa_largura_mm, 700)
        self.assertAlmostEqual(b.chapa_comprimento_mm, 405)
        P.selecionar(bpy.context, grupo, 'GRUPO')
        self.assertIsNone(P.editar(bpy.context, grupo, 'espessura_mm', 25))
        self.assertTrue(all(abs(o.chapa_espessura_mm - 25) < .001 for o in (a, b, c)))

    def test_reducao_dispensa_referencia_e_adicao_inviavel_nao_muda_o_grupo(self):
        grupo = self.prateleiras()
        fonte = P.prateleiras_do_grupo(grupo)[0]
        self.recortar(fonte)
        P.selecionar(bpy.context, grupo, 'GRUPO')
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 2))
        self.assertIsNone(P._referencia_pendente[0])
        self.assertIsNone(P.editar(bpy.context, grupo, 'espessura_mm', 200))
        P.selecionar(bpy.context, fonte, 'PRATELEIRA')
        antes = P.parametros(grupo)
        self.assertIsNotNone(P.editar(bpy.context, grupo, 'quantidade', 5))
        self.assertEqual(P.parametros(grupo), antes)
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 2)

    def test_reduzir_modulo_reencaixa_vaos_livres_e_devolve_originais(self):
        grupo=self.prateleiras(espacamento='LIVRE',vaos_mm=[100,200,50])
        antes=self.alturas(grupo)
        self.conj.conj_altura_mm=100
        l,a,m=P.vao(grupo)
        self.assertGreaterEqual(min(P.vaos(a,P.parametros(grupo))),-.01)
        self.assertLess(self.alturas(grupo)[-1]+18,a+.01)
        self.conj.conj_altura_mm=700
        self.assertEqual(antes,self.alturas(grupo))

    def test_prateleiras_do_assistente_conservam_referencia_da_face_lateral(self):
        ref=Matrix.Rotation(1.57079632679,3,'Z')
        pontos=[Vector((-.4,-.262,.682)),Vector((-.4,.262,.018))]
        ref=addon.gavetas.referencia_do_vao(self.conj,*pontos)
        margens=addon.gavetas.margens_do_vao(self.conj,*pontos,referencial=ref)
        grupo=P.criar_prateleiras(bpy.context,self.conj,margens,
                  dict(quantidade=2,profundidade_mm=700),referencial=ref)
        self.assertGreater(grupo.matrix_world.to_3x3().col[1].dot(Vector((1,0,0))),.999)
        self.assertIsNone(P.editar(bpy.context,grupo,'espessura_mm',15))
        self.assertGreater(grupo.matrix_world.to_3x3().col[1].dot(Vector((1,0,0))),.999)
        self.assertAlmostEqual(P.medidas(grupo)[0],524,places=2)
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for colecao in list(bpy.data.collections):
            bpy.data.collections.remove(colecao)
        camada = bpy.context.view_layer
        camada.active_layer_collection = camada.layer_collection
        P.esquecer()
        # balcao 800 x 700 x 560, chapa 18: o vao de dentro e' 764 x 664
        self.conj = addon.modulos.criar_armario(bpy.context, 'Balcao', 800, 700, 560,
                                                fundo=False)
        bpy.context.view_layer.update()

    def prateleiras(self, **p):
        padrao = dict(quantidade=3, espessura_mm=18.0, profundidade_mm=540.0)
        padrao.update(p)
        return P.criar_prateleiras(bpy.context, self.conj, (18, 18, 18, 18, 0), padrao)

    def alturas(self, grupo):
        """z de baixo de cada prateleira, em mm, no grupo."""
        inversa = grupo.matrix_world.inverted()
        return [round((inversa @ o.matrix_world.translation).z * 1000.0
                      - o.chapa_espessura_mm / 2.0, 3) for o in P.prateleiras_do_grupo(grupo)]

    def test_calculo_igual_e_livre(self):
        p = dict(P.PARAMETROS_PADRAO, quantidade=3, espessura_mm=18.0, profundidade_mm=500.0)
        dados = P.calcular(764.0, 664.0, p)
        # 664 - 3 x 18 = 610 em 4 vaos iguais
        self.assertEqual([round(v, 3) for v in dados['vaos']], [152.5] * 4)
        self.assertAlmostEqual(dados['prateleiras'][1][4], 152.5 * 2 + 18.0)
        # LIVRE: o de cima e' o que sobra
        livre = dict(p, espacamento='LIVRE', vaos_mm=[100.0, 200.0, 50.0])
        self.assertAlmostEqual(P.vaos(664.0, livre)[-1], 610.0 - 350.0)
        with self.assertRaisesRegex(ValueError, 'passam do topo'):
            P.vaos(664.0, dict(livre, vaos_mm=[300.0, 300.0, 100.0]))
        with self.assertRaisesRegex(ValueError, 'nao cabem'):
            P.calcular(764.0, 664.0, dict(p, quantidade=20, espessura_mm=40.0))
        with self.assertRaisesRegex(ValueError, 'rasa'):
            P.calcular(764.0, 664.0, dict(p, recuo_mm=480.0))

    def test_mover_um_vao_anda_so_uma_prateleira(self):
        p = dict(P.PARAMETROS_PADRAO, quantidade=3, espessura_mm=18.0)
        # vao 2 (entre a 1a e a 2a) em 100: so' a 2a desce; o 3o cede
        self.assertEqual([round(v, 3) for v in P.mover_vao(664.0, p, 1, 100.0)],
                         [152.5, 100.0, 205.0])
        # o do topo em 100: a mais alta sobe (o vao de baixo dela cresce)
        self.assertEqual([round(v, 3) for v in P.mover_vao(664.0, p, 3, 100.0)],
                         [152.5, 152.5, 205.0])
        # o "Acima" da 2a: anda ELA (o vao de baixo dela cede)
        self.assertEqual([round(v, 3) for v in P.mover_vao(664.0, p, 2, 100.0, de_baixo=True)],
                         [152.5, 205.0, 100.0])
        with self.assertRaisesRegex(ValueError, 'Nao cabe'):
            P.mover_vao(664.0, p, 1, 400.0)

    def test_cria_chapas_no_vao_sem_mexer_no_modulo(self):
        antes = addon.modulos.medir_conjunto(self.conj)
        chapas = len(addon.modulos._chapas_do_conjunto(self.conj))
        grupo = self.prateleiras(folga_lateral_mm=1.0, recuo_mm=20.0)
        prateleiras = P.prateleiras_do_grupo(grupo)
        self.assertEqual(len(prateleiras), 3)
        self.assertEqual(grupo.parent, self.conj)
        for o in prateleiras:
            self.assertIn(addon.chapas.MARCA_CHAPA, o)
            self.assertAlmostEqual(o.chapa_largura_mm, 764.0 - 2.0, places=3)
            self.assertAlmostEqual(o.chapa_comprimento_mm, 540.0 - 20.0, places=3)
            self.assertAlmostEqual(o.chapa_espessura_mm, 18.0, places=3)
        self.assertEqual(self.alturas(grupo), [152.5, 323.0, 493.5])
        # o modulo nao ganha chapa nem muda de medida
        self.assertEqual(len(addon.modulos._chapas_do_conjunto(self.conj)), chapas)
        for a, b in zip(antes, addon.modulos.medir_conjunto(self.conj)):
            self.assertAlmostEqual(a, b, places=3)
        # o orcamento conta as prateleiras; a pintura pega todas
        self.assertEqual(addon.orcamento._pecas_internas(self.conj)[0], 3)
        self.assertEqual(len(addon.materiais.pecas_dos_alvos([grupo])), 3)

    def test_editar_na_mesma_chapa_e_desfaz_o_que_nao_cabe(self):
        grupo = self.prateleiras()
        segunda = P.prateleiras_do_grupo(grupo)[1]
        nome = segunda.name
        self.assertIsNone(P.editar(bpy.context, grupo, 'espessura_mm', 25.0))
        self.assertEqual(P.prateleiras_do_grupo(grupo)[1].name, nome)   # a mesma
        self.assertAlmostEqual(segunda.chapa_espessura_mm, 25.0, places=3)
        # entre todas: LIVRE com o mesmo vao; mais uma continua com ele
        self.assertIsNone(P.editar(bpy.context, grupo, 'entre_mm', 120.0))
        self.assertEqual(self.alturas(grupo), [120.0, 265.0, 410.0])
        self.assertIsNone(P.editar(bpy.context, grupo, 'prateleiras_quantidade', 4))
        self.assertEqual(self.alturas(grupo), [120.0, 265.0, 410.0, 555.0])
        # 5 a 120 nao cabem: volta a dividir igual
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 5))
        self.assertEqual(P.parametros(grupo)['espacamento'], 'IGUAL')
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 5)
        # nao cabe: devolve o erro e fica como estava
        erro = P.editar(bpy.context, grupo, 'espessura_mm', 200.0)
        self.assertIn('nao cabem', erro)
        self.assertEqual(P.parametros(grupo)['espessura_mm'], 25.0)
        # LIVRE parte dos vaos de hoje; IGUAL divide de novo
        antes = self.alturas(grupo)
        self.assertIsNone(P.editar(bpy.context, grupo, 'espacamento', 'LIVRE'))
        self.assertEqual(self.alturas(grupo), antes)
        self.assertIsNone(P.editar(bpy.context, grupo, 'vao_0', 50.0))
        self.assertEqual(self.alturas(grupo)[0], 50.0)
        self.assertEqual(self.alturas(grupo)[1:], antes[1:])
        self.assertIsNone(P.editar(bpy.context, grupo, 'espacamento', 'IGUAL'))
        self.assertEqual(self.alturas(grupo), antes)

    def test_modulo_que_muda_de_medida_leva_as_prateleiras(self):
        grupo = self.prateleiras()
        self.conj.conj_largura_mm = 1000.0          # dispara o redimensionar
        bpy.context.view_layer.update()
        self.assertAlmostEqual(P.medidas(grupo)[0], 964.0, places=2)
        self.assertAlmostEqual(P.prateleiras_do_grupo(grupo)[0].chapa_largura_mm, 964.0, places=2)

    def test_profundidade_para_no_fundo(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Alto', 600, 900, 400)
        bpy.context.view_layer.update()
        fundo = next(c for c in addon.modulos._chapas_do_conjunto(conj)
                     if addon.chapas.MARCA_FUNDO in c)
        inversa = conj.matrix_world.inverted()
        frente_do_fundo = min((inversa @ (fundo.matrix_world @ v.co)).y * 1000.0
                              for v in fundo.data.vertices)
        lo, _hi = addon.gavetas._limites(conj)
        ponto = conj.matrix_world @ (Vector((0.0, lo.y, 300.0)) / 1000.0)
        self.assertAlmostEqual(P.profundidade_ate_o_fundo(conj, ponto),
                               frente_do_fundo - lo.y, places=2)
        self.assertLess(P.profundidade_ate_o_fundo(conj, ponto), 400.0 - 15.0)

    def test_selecao_hud_e_vaos_editaveis(self):
        grupo = self.prateleiras()
        segunda = P.prateleiras_do_grupo(grupo)[1]
        self.assertEqual(addon.selecao._aba_da_selecao(segunda), 'PRATELEIRAS')
        P.selecionar(bpy.context, segunda, 'GRUPO')
        self.assertEqual(bpy.context.view_layer.objects.active, grupo)
        self.assertFalse(self.conj.select_get())
        itens = addon.hud._itens_da_selecao(bpy.context)
        self.assertEqual([(o.name, modo) for o, modo, _c in itens],
                         [(grupo.name, 'PRATELEIRAS')])
        geometria = addon.hud._geometria_do_item(*itens[0])
        vaos = [l for l in geometria['linhas'] if l.get('vao')]
        self.assertEqual([l['face'] for l in vaos], [('V', k) for k in range(4)])
        self.assertEqual({l['letra'] for l in geometria['linhas'] if not l.get('vao')},
                         {'L', 'A', 'P'})
        # a linha do 2o vao: arrastar/digitar anda so' a 2a prateleira
        self.assertAlmostEqual(addon.hud._valor_hud(vaos[1]), 152.5, places=3)
        addon.hud._aplicar_valor_hud(bpy.context, vaos[1], 100.0)
        self.assertEqual(self.alturas(grupo), [152.5, 270.5, 493.5])
        # o Esc do arraste devolve os parametros
        estado = addon.hud._estado_arraste_hud(bpy.context, vaos[1])
        addon.hud._aplicar_valor_hud(bpy.context, vaos[1], 60.0)
        addon.hud._restaurar_arraste_hud(bpy.context, estado)
        self.assertEqual(self.alturas(grupo), [152.5, 270.5, 493.5])
        # duplo clique: so' ela
        P.selecionar(bpy.context, segunda, 'PRATELEIRA')
        self.assertEqual(bpy.context.view_layer.objects.active, segunda)
        self.assertEqual(len(addon.hud._itens_da_selecao(bpy.context)), 1)

    def test_aba_prateleiras_e_campos_editaveis(self):
        cena = bpy.context.scene
        cena.cabinet_aba = 'PRATELEIRAS'
        widgets = addon.gaveta._widgets_gaveta(bpy.context, 480, 1400)
        self.assertTrue(any(v[5] and v[5][0] == 'prateleiras' for v in widgets))
        self.assertIn('Prateleiras', [v[4] for v in widgets if v[5] and v[5][0] == 'aba'])
        grupo = self.prateleiras()
        P.selecionar(bpy.context, grupo, 'GRUPO')
        acoes = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 480, 1400) if v[5]]
        self.assertTrue(any(a[0] == 'contador' and a[1] == 'prateleiras_quantidade'
                            for a in acoes))
        self.assertTrue(any(a[0] == 'escolha' and a[1] == 'prateleiras_espacamento'
                            for a in acoes))
        medidas = {a[2] for a in acoes if a[0] == 'medida' and a[1] == 'prateleiras'}
        self.assertTrue({'largura', 'altura', 'profundidade_mm', 'espessura_mm', 'recuo_mm',
                         'folga_lateral_mm', 'entre_mm', 'vao_0', 'vao_3'} <= medidas, medidas)
        # uma so' (duplo): os dois vaos dela
        segunda = P.prateleiras_do_grupo(grupo)[1]
        P.selecionar(bpy.context, segunda, 'PRATELEIRA')
        acoes = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 480, 1400) if v[5]]
        rotulos = {a[3]: a[2] for a in acoes if a[0] == 'medida' and a[1] == 'prateleiras'}
        self.assertEqual((rotulos.get('Abaixo'), rotulos.get('Acima')), ('vao_1', 'acima_1'))
        self.assertNotIn('Entre prateleiras', rotulos)
        self.assertEqual(rotulos['Largura'], 'individual_1_largura_mm')
        for largura in (190, 320, 564):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1400)
            self.assertTrue(any(w[5] and w[5][:2] == ('contador', 'prateleiras_quantidade')
                                for w in widgets))
        # os campos chegam pelos mesmos caminhos da porta/gavetas
        ev = addon.gaveta_eventos
        self.assertIsNone(ev.aplicar_medida(bpy.context, 'prateleiras', segunda.name,
                                            'acima_1', 0.1))
        self.assertEqual(self.alturas(grupo), [152.5, 375.5, 493.5])
        self.assertIsNone(ev._aplicar_contador(
            bpy.context, ('contador', 'prateleiras_quantidade', 3, 1, 20, grupo.name), 2))
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 2)
        self.assertIn('OBJECT_OT_criar_prateleiras', [c.__name__ for c in addon.CLASSES])
        # so' 2 pontos (pedido do usuario): o clique da quantidade ja' cria,
        # sem a etapa de profundidade das gavetas
        self.assertNotIn('PROFUNDIDADE', P.OBJECT_OT_criar_prateleiras.RECADOS)
        self.assertIsNot(P.OBJECT_OT_criar_prateleiras._depois_da_quantidade,
                         addon.gavetas.AssistenteDoVao._depois_da_quantidade)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestPrateleiras)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de prateleiras')
