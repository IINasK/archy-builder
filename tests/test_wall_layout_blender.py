"""Existing composition: dimensions, redistribution, replacement and elevation appearance."""
import os
import sys
import math
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Vector, Quaternion

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon

C = addon.paredes_composicao
E = addon.paredes_edicao
P = addon.paredes


class TestComposicaoParedes(unittest.TestCase):
    def setUp(self):
        addon.eventos._fim_do_desfazer()
        E.encerrar()
        E._ultima_face[0] = None
        E._alvo_contexto[0] = None
        C.esquecer()
        P.esquecer()
        for chave in (C.CHAVE_GUIAS, C.CHAVE_GUIAS_MODO):
            if chave in bpy.context.scene:
                del bpy.context.scene[chave]
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for col in list(bpy.data.collections):
            bpy.data.collections.remove(col)
        bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1)
        for v in bm.verts:
            v.co.x *= 3
            v.co.y *= .15
            v.co.z *= 2.7
        m = bpy.data.meshes.new("Wall")
        bm.to_mesh(m)
        bm.free()
        self.parede = bpy.data.objects.new("Wall", m)
        bpy.context.scene.collection.objects.link(self.parede)
        self.parede.location = (0, 1.075, 1.35)
        self.area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        self.regiao = next(r for r in self.area.regions if r.type == 'WINDOW')
        self.area.spaces.active.region_3d.view_rotation = Quaternion((1, 0, 0), math.pi / 2)
        bpy.context.view_layer.update()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        E.encerrar()
        self.tmp.cleanup()

    def selecionar(self, obj):
        for o in bpy.context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

    def modulo(self, inicio=-1.4, base=0, largura=600, nome="Cabinet", altura=720):
        obj = addon.modulos.criar_armario(bpy.context, nome, largura, altura, 550, fundo=True)
        costas = Vector((inicio + largura / 2000, 1, base))
        P.colocar_na_parede(obj, self.parede, costas, Vector((0, -1, 0)))
        P.associar(obj, self.parede, costas, Vector((0, -1, 0)))
        bpy.context.view_layer.update()
        return obj

    def iniciar(self, ativo=None):
        self.selecionar(self.parede)
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            self.assertIsNone(E.iniciar(bpy.context, self.parede))
        if ativo:
            self.selecionar(ativo)
        C.atualizar(bpy.context)

    def tres(self):
        itens = [self.modulo(-1.4 + i * .8, nome='M%d' % i) for i in range(3)]
        self.iniciar(itens[0])
        return itens

    def confirmar_texto(self, modulo, propriedade, texto):
        avisos = []
        op = SimpleNamespace(objeto=modulo.name, propriedade=propriedade,
            _guia=lambda: None, report=lambda categoria, mensagem: avisos.append(mensagem),
            cancel=lambda contexto: C.OBJECT_OT_editar_cota_parede.cancel(None, contexto))
        C._edicao[0] = dict(objeto=modulo.name, propriedade=propriedade,
                            texto=texto, cursor=len(texto), selecionado=False)
        evento = SimpleNamespace(value='PRESS', type='RET', ctrl=False, unicode='')
        resultado = C.OBJECT_OT_editar_cota_parede._modal(op, bpy.context, evento)
        return resultado, avisos

    def test_zero_digitado_encosta_nos_limites_sem_mudar_dimensoes(self):
        # Regression, fixed in v366: the parser rejected 0 before domain validation.
        m = self.modulo(base=.3)
        self.iniciar(m)
        medidas = tuple(C.ficha(m, E._sessao[0])[k] for k in ('largura', 'altura', 'profundidade'))
        malhas = {o.name: o.data.as_pointer() for o in m.children_recursive if o.type == 'MESH'}
        vertices = {o.name: tuple(tuple(v.co) for v in o.data.vertices)
                    for o in m.children_recursive if o.type == 'MESH'}
        for prop in ('cota_inferior', 'cota_superior', 'vao_esquerdo', 'vao_direito', 'afastamento'):
            with self.subTest(cota=prop):
                if prop == 'afastamento':
                    self.assertIsNone(C.editar_modulo(bpy.context, m.name, prop, 50))
                resultado, avisos = self.confirmar_texto(m, prop, '0')
                self.assertEqual(resultado, {'FINISHED'}, avisos)
                atual = C.itens_da_face(bpy.context)[0]
                self.assertAlmostEqual(atual[prop], 0, places=5)
                for k, medida in zip(('largura', 'altura', 'profundidade'), medidas):
                    self.assertAlmostEqual(atual[k], medida, places=5)
                self.assertEqual({o.name: o.data.as_pointer() for o in m.children_recursive if o.type == 'MESH'}, malhas)
                self.assertEqual({o.name: tuple(tuple(v.co) for v in o.data.vertices)
                                  for o in m.children_recursive if o.type == 'MESH'}, vertices)
                self.assertIsNone(C._edicao[0])

    def test_zero_de_dimensao_e_distancia_negativa_seguem_recusados(self):
        m = self.modulo(base=.3)
        self.iniciar(m)
        antes = m.matrix_world.copy()
        for prop, texto in (('largura', '0'), ('altura', '0'), ('profundidade', '0'),
                             ('cota_inferior', '-1')):
            with self.subTest(cota=prop):
                resultado, avisos = self.confirmar_texto(m, prop, texto)
                self.assertEqual(resultado, {'RUNNING_MODAL'})
                self.assertTrue(avisos)
                self.assertEqual(m.matrix_world, antes)

    def test_zero_digitado_usa_topo_do_piso_real_sem_atravessar_o_apoio(self):
        # The wall extends to z = 0, but the actual floor occupies 0..100 mm, as in the project.
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1)
        for v in bm.verts:
            v.co.x *= 3
            v.co.y *= .8
            v.co.z *= .1
        malha = bpy.data.meshes.new('Piso 100 mm')
        bm.to_mesh(malha)
        bm.free()
        piso = bpy.data.objects.new('Piso 100 mm', malha)
        bpy.context.scene.collection.objects.link(piso)
        piso.location = (0, .6, .05)
        m = self.modulo(base=.1, altura=2500)
        self.iniciar(m)
        antes = m.matrix_world.copy()
        resultado, avisos = self.confirmar_texto(m, 'cota_inferior', '0')
        self.assertEqual(resultado, {'FINISHED'}, avisos)
        self.assertLess((m.matrix_world.translation - antes.translation).length, 1e-6)
        self.assertAlmostEqual(C.itens_da_face(bpy.context)[0]['cota_inferior'], 0, places=5)
        alvo = P.ponto_das_costas(m).copy()
        alvo.z = .05 + 1.25
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            ponto, erro = E.encaixar_na_face(bpy.context, m, alvo, E._sessao[0])
        self.assertIsNone(erro)
        self.assertAlmostEqual(ponto.z, .1, places=5)
        # The editing base moves to the support, but penetration into wood remains rejected.
        f = dict(C.ficha(m, E._sessao[0]), base=0)
        self.assertIsNotNone(C._validar_encaixe(bpy.context, E._sessao[0], f, (m.name,)))

    def test_parede_nao_tem_campo_de_medida_no_menu_nem_depois_de_sair(self):
        self.iniciar()
        for estado in (True, False):
            if not estado:
                E.encerrar()
            widgets = addon.gaveta._widgets_gaveta(bpy.context, 480, 1500)
            medidas = [w for w in widgets if w[5] and w[5][0] == 'medida']
            self.assertFalse(any(w[5][1] in {'livre', 'objeto', 'cota'} for w in medidas))
            self.assertFalse(any(w[5][2].startswith('dimensions_') for w in medidas))

    def test_escrita_direta_do_menu_na_parede_e_recusada(self):
        self.iniciar()
        antes = tuple(self.parede.dimensions)
        erro = addon.gaveta_eventos.aplicar_medida(bpy.context, 'livre', self.parede.name, 'dimensions_0', 5)
        self.assertIsNotNone(erro)
        self.assertEqual(tuple(self.parede.dimensions), antes)

    def test_visual_home_builder_e_restauracao(self):
        espaco = self.area.spaces.active
        antes = (espaco.shading.light, espaco.shading.color_type, espaco.overlay.show_extras,
                  espaco.overlay.show_relationship_lines, self.parede.display_type)
        self.iniciar()
        self.assertEqual(espaco.shading.light, 'FLAT')
        self.assertEqual(espaco.shading.color_type, 'OBJECT')
        self.assertFalse(espaco.overlay.show_extras)
        self.assertFalse(espaco.overlay.show_relationship_lines)
        self.assertEqual(self.parede.display_type, 'SOLID')
        E.encerrar()
        depois = (espaco.shading.light, espaco.shading.color_type, espaco.overlay.show_extras,
                   espaco.overlay.show_relationship_lines, self.parede.display_type)
        self.assertEqual(antes, depois)

    def test_largura_preserva_inicio_malhas_e_espessura(self):
        m = self.modulo()
        self.iniciar(m)
        meshes = {o.name: o.data.as_pointer() for o in m.children_recursive if o.type == 'MESH'}
        self.assertIsNone(C.editar_modulo(bpy.context, m.name, 'largura', 850))
        f = C.ficha(m, E._sessao[0])
        self.assertAlmostEqual(f['inicio'], -1.4, places=5)
        self.assertAlmostEqual(f['largura'], .85, places=5)
        self.assertEqual(meshes, {o.name: o.data.as_pointer() for o in m.children_recursive if o.type == 'MESH'})
        for o in m.children_recursive:
            if addon.chapas.MARCA_CHAPA in o and not addon.chapas.eh_dependente(o):
                self.assertAlmostEqual(o.chapa_espessura_mm, 18, places=4)

    def test_altura_profundidade_e_instalacao(self):
        m = self.modulo()
        self.iniciar(m)
        for prop, valor in (('altura', 800), ('profundidade', 600), ('instalacao', 200)):
            self.assertIsNone(C.editar_modulo(bpy.context, m.name, prop, valor))
        f = C.ficha(m, E._sessao[0])
        self.assertAlmostEqual(f['altura'], .8, places=5)
        self.assertAlmostEqual(f['profundidade'], .6, places=5)
        self.assertAlmostEqual(f['base'], .2, places=5)

    def test_afastamentos_esquerdo_e_direito_sao_do_modulo(self):
        m = self.modulo()
        self.iniciar(m)
        self.assertIsNone(C.editar_modulo(bpy.context, m.name, 'esquerda', 250))
        self.assertAlmostEqual(C.ficha(m, E._sessao[0])['inicio'], -1.25, places=5)
        self.assertIsNone(C.editar_modulo(bpy.context, m.name, 'direita', 100))
        self.assertAlmostEqual(C.ficha(m, E._sessao[0])['fim'], 1.4, places=5)

    def test_edicao_que_colide_ou_excede_face_nao_muda_objetos(self):
        m = self.modulo()
        vizinho = self.modulo(-.5, nome='Vizinho')
        self.iniciar(m)
        antes = tuple(m.matrix_world.translation)
        self.assertIsNotNone(C.editar_modulo(bpy.context, m.name, 'largura', 1800))
        self.assertIsNotNone(C.editar_modulo(bpy.context, m.name, 'altura', 3000))
        self.assertEqual(tuple(m.matrix_world.translation), antes)
        self.assertAlmostEqual(C.ficha(m, E._sessao[0])['largura'], .6, places=5)

    def test_modulo_em_parede_rotacionada_usa_os_eixos_locais(self):
        m = self.modulo()
        self.parede.rotation_euler.z = .6
        bpy.context.view_layer.update()
        P.manter_nas_paredes()
        self.iniciar(m)
        self.assertIsNone(C.editar_modulo(bpy.context, m.name, 'largura', 850))
        self.assertAlmostEqual(C.ficha(m, E._sessao[0])['largura'], .85, places=4)
        self.assertGreater(P.plano_do_modulo(m)[1].dot(Vector(E._sessao[0]['normal'])), .9999)

    def test_movimento_nativo_recalcula_vaos_sem_mover_vizinhos(self):
        a, b, c = self.tres()
        antes = c.matrix_world.copy()
        b.location.x += .1
        bpy.context.view_layer.update()
        P.manter_nas_paredes()
        C.atualizar(bpy.context)
        itens = C._resumo[0]['itens']
        segundo = next(f for f in itens if f['nome'] == b.name)
        self.assertAlmostEqual(segundo['vao_esquerdo'], .3, places=5)
        self.assertEqual(c.matrix_world, antes)

    def test_excluir_modulo_recalcula_vaos_preservando_posicoes(self):
        a, b, c = self.tres()
        antes = c.matrix_world.copy()
        for o in [b] + list(b.children_recursive):
            bpy.data.objects.remove(o, do_unlink=True)
        C.atualizar(bpy.context)
        primeiro = next(f for f in C._resumo[0]['itens'] if f['nome'] == a.name)
        self.assertAlmostEqual(primeiro['vao_direito'], 1, places=5)
        self.assertEqual(c.matrix_world, antes)

    def test_redistribuir_larguras_livres_desconta_folgas(self):
        self.tres()
        E.editar_parametro('esquerda', 50)
        E.editar_parametro('direita', 50)
        E.editar_parametro('espacamento', 20)
        self.assertEqual(bpy.ops.object.cabinet_redistribuir_parede(), {'FINISHED'})
        itens = C.itens_da_face(bpy.context)
        for f in itens:
            self.assertAlmostEqual(f['largura'], 2.86 / 3, places=5)
        self.assertAlmostEqual(itens[0]['inicio'], -1.45, places=5)
        self.assertAlmostEqual(itens[-1]['fim'], 1.45, places=5)

    def test_largura_fixa_e_preservada_e_so_livres_recebem_resto(self):
        a, b, c = self.tres()
        self.assertIsNone(C.fixar(bpy.context, b.name, True))
        self.assertEqual(bpy.ops.object.cabinet_redistribuir_parede(), {'FINISHED'})
        self.assertAlmostEqual(C.ficha(b, E._sessao[0])['largura'], .6, places=5)
        self.assertAlmostEqual(C.ficha(a, E._sessao[0])['largura'], 1.2, places=5)

    def test_sem_largura_livre_ou_sem_espaco_nao_redistribui(self):
        modulos = self.tres()
        for m in modulos:
            C.fixar(bpy.context, m.name, True)
        antes = [m.matrix_world.copy() for m in modulos]
        self.assertIn('erro', C.planejar_redistribuicao(bpy.context))
        self.assertEqual(antes, [m.matrix_world for m in modulos])

    def test_redistribuicao_nao_move_modulos_superiores(self):
        self.tres()
        superior = self.modulo(-1.4, base=1.7, nome="Above")
        primeiro = next(o for o in bpy.data.objects if o.name == 'M0')
        self.selecionar(primeiro)
        antes = superior.matrix_world.copy()
        self.assertEqual(bpy.ops.object.cabinet_redistribuir_parede(), {'FINISHED'})
        self.assertEqual(superior.matrix_world, antes)

    def test_falha_no_segundo_resize_restaura_primeiro(self):
        a, b, c = self.tres()
        antes = [C.ficha(o, E._sessao[0]) for o in (a, b, c)]
        original = addon.modulos.redimensionar_orientado
        chamadas = []
        def falhar(*args):
            chamadas.append(1)
            if len(chamadas) == 2:
                raise ValueError('Falha simulada')
            return original(*args)
        plano = C.planejar_redistribuicao(bpy.context)
        with patch.object(addon.modulos, 'redimensionar_orientado', falhar):
            self.assertIn('Falha simulada', C._transacao(bpy.context, plano['itens']))
        depois = [C.ficha(o, E._sessao[0]) for o in (a, b, c)]
        for f, g in zip(antes, depois):
            self.assertAlmostEqual(f['largura'], g['largura'], places=5)
            self.assertAlmostEqual(f['inicio'], g['inicio'], places=5)

    def preparar_troca(self):
        origem = self.modulo(nome='Modelo novo', largura=500)
        col = next(c for c in origem.users_collection if c.get('eh_colecao_modulo'))
        caminho = os.path.join(self.tmp.name, 'novo.blend')
        bpy.data.libraries.write(caminho, {col})
        for o in [origem] + list(origem.children_recursive):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(col)
        antigo = self.modulo(-.8, base=.3, largura=800, nome='Antigo')
        self.iniciar(antigo)
        self.assertEqual(bpy.ops.object.cabinet_trocar_modelo_parede(), {'FINISHED'})
        self.assertIsNone(E.preparar_modelo(bpy.context, self.tmp.name, 'novo.blend', 'modulo'))
        return antigo

    def test_substituir_modelo_preserva_tamanho_posicao_associacao(self):
        antigo = self.preparar_troca()
        C.fixar(bpy.context, antigo.name, True)
        nome = antigo.name
        antes = C.ficha(antigo, E._sessao[0])
        self.assertEqual(bpy.ops.object.cabinet_distribuir_parede(), {'FINISHED'})
        self.assertNotIn(nome, bpy.data.objects)
        itens = C.itens_da_face(bpy.context)
        self.assertEqual(len(itens), 1)
        for k in ('inicio', 'base', 'largura', 'altura', 'profundidade'):
            self.assertAlmostEqual(itens[0][k], antes[k], places=5)
        self.assertTrue(itens[0]['fixa'])

    # Regression, fixed in v302: the replacement stayed at the scene root outside
    # the original's room, consequently disappearing from the estimate.
    def test_substituir_modelo_mantem_o_comodo(self):
        antigo = self.preparar_troca()
        self.assertEqual(addon.orcamento.definir_comodo(bpy.context.scene, [antigo], "Kitchen"), 1)
        self.assertEqual(bpy.ops.object.cabinet_distribuir_parede(), {'FINISHED'})
        novo, = [o for o in bpy.data.objects if addon.chapas.MARCA_CONJUNTO in o]
        comodo = addon.orcamento._comodo_do_modulo(novo)
        self.assertIsNotNone(comodo)
        self.assertEqual(addon.orcamento._nome_comodo(comodo), "Kitchen")

    def test_substituicao_com_falha_preserva_original(self):
        antigo = self.preparar_troca()
        malhas = [o.data.as_pointer() for o in antigo.children_recursive if o.type == 'MESH']
        antes = E._dados_antes()
        with patch.object(addon.modulos, 'redimensionar_orientado', side_effect=ValueError('Incompativel')):
            self.assertIn('Incompativel', C.substituir(bpy.context))
        self.assertEqual(antes, E._dados_antes())
        self.assertEqual(malhas, [o.data.as_pointer() for o in antigo.children_recursive if o.type == 'MESH'])

    def test_cancelar_troca_nao_remove_original(self):
        antigo = self.preparar_troca()
        nome = antigo.name
        bpy.ops.object.cabinet_cancelar_previa_parede()
        self.assertIn(nome, bpy.data.objects)
        self.assertEqual(E._sessao[0]['substituir'], '')

    def test_cotas_laterais_e_hit_test_tem_apenas_modulos(self):
        a, b, c = self.tres()
        C._rotulos[0] = ((10, 20, 40, 20, a.name, 'largura', 600),)
        self.assertEqual(C.cota_sob(15, 25)[4], a.name)
        self.assertIsNone(C.cota_sob(0, 0))
        self.assertIn(C.OBJECT_OT_editar_cota_parede, addon.CLASSES)

    def test_undo_redo_de_redistribuir(self):
        self.tres()
        bpy.ops.ed.undo_push(message='Antes da composicao')
        bpy.ops.object.cabinet_redistribuir_parede()
        bpy.ops.ed.undo_push(message='Composicao concluida')
        bpy.ops.ed.undo()
        addon.eventos._fim_do_desfazer()
        E.verificar()
        self.assertFalse(E.ativa())
        parede = bpy.data.objects["Wall"]
        self.assertEqual(parede.display_type, 'TEXTURED')
        self.assertNotIn(E.CHAVE_VISUAL, parede)
        for o in bpy.data.objects:
            if addon.chapas.MARCA_CONJUNTO in o:
                self.assertAlmostEqual(P.caixa_do_modulo(o)[1].x - P.caixa_do_modulo(o)[0].x, .6, places=4)
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        E.verificar()
        self.assertNotIn(E.CHAVE_VISUAL, bpy.data.objects["Wall"])

    def test_observador_passivo_nao_bloqueia_sincronizacao_nativa(self):
        from types import SimpleNamespace
        self.assertFalse(addon.eventos.modal_interativo(SimpleNamespace(bl_idname='OBJECT_OT_cabinet_observar_parede')))
        for nome in ('TRANSFORM_OT_translate', 'OBJECT_OT_cabinet_editar_cota_parede', 'TRANSFORM_OT_resize'):
            self.assertTrue(addon.eventos.modal_interativo(SimpleNamespace(bl_idname=nome)))

    def test_composicao_nao_sobrepoe_widgets_nas_larguras_suportadas(self):
        self.tres()
        for largura in (190, 320, 564):
            caixas = [w[:4] for w in addon.gaveta._widgets_gaveta(bpy.context, largura, 2900)]
            for i, (ax, ay, aw, ah) in enumerate(caixas):
                for bx, by, bw, bh in caixas[i + 1:]:
                    self.assertFalse(ax < bx + bw - .01 and bx < ax + aw - .01
                                     and ay < by + bh - .01 and by < ay + ah - .01,
                                     (largura, (ax, ay, aw, ah), (bx, by, bw, bh)))

    def test_subconjunto_selecionado_preserva_vizinho_nao_selecionado(self):
        a, b, c = self.tres()
        b.select_set(True)
        antes = c.matrix_world.copy()
        self.assertEqual(bpy.ops.object.cabinet_redistribuir_parede(), {'FINISHED'})
        self.assertEqual(c.matrix_world, antes)
        self.assertAlmostEqual(C.ficha(b, E._sessao[0])['fim'], C.ficha(c, E._sessao[0])['inicio'], places=5)

    def test_cancelamento_da_cota_nao_muda_geometria(self):
        m = self.modulo()
        self.iniciar(m)
        antes = C.ficha(m, E._sessao[0])
        C._edicao[0] = dict(objeto=m.name, propriedade='largura', texto='900', cursor=3, selecionado=True)
        C.OBJECT_OT_editar_cota_parede.cancel(None, bpy.context)
        self.assertIsNone(C._edicao[0])
        self.assertEqual(antes, C.ficha(m, E._sessao[0]))

    def test_adicionar_modulo_recalcula_vizinhos_sem_redistribuir(self):
        a = self.modulo(-1.4, nome='A')
        self.iniciar(a)
        antes = a.matrix_world.copy()
        b = self.modulo(0, nome='B')
        C.atualizar(bpy.context)
        f = next(f for f in C._resumo[0]['itens'] if f['nome'] == a.name)
        self.assertAlmostEqual(f['vao_direito'], .8, places=5)
        self.assertEqual(a.matrix_world, antes)

    def test_undo_redo_da_substituicao_preserva_ambos_os_estados(self):
        antigo = self.preparar_troca()
        nome = antigo.name
        bpy.ops.ed.undo_push(message='Antes de trocar o modelo')
        bpy.ops.object.cabinet_distribuir_parede()
        bpy.ops.ed.undo_push(message='Modelo trocado')
        bpy.ops.ed.undo()
        addon.eventos._fim_do_desfazer()
        E.verificar()
        self.assertIn(nome, bpy.data.objects)
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        E.verificar()
        self.assertNotIn(nome, bpy.data.objects)

    def test_menu_da_composicao_sem_livre_fixa_nem_botoes(self):
        # User screenshot requested removing free/fixed, redistribute, replace-model
        # and unlink controls. Keep only the dimension cross.
        a, b, c = self.tres()
        C.fixar(bpy.context, b.name, True)
        itens = []
        C.widgets(bpy.context, itens, 0, 2000, 300)
        self.assertFalse([i for i in itens if i[5] and i[5][0] in {'escolha', 'operador'}])
        self.assertFalse([i for i in itens if i[4] in {"Free", 'Fixa'} or i[4].startswith('M1 ')])
        self.assertTrue([i for i in itens if i[5] and i[5][:2] == ('medida', 'parede_modulo')])

    def test_menu_da_composicao_some_sem_modulo_selecionado(self):
        self.tres()
        for o in bpy.context.selected_objects:
            o.select_set(False)
        itens = []
        self.assertEqual(C.widgets(bpy.context, itens, 0, 2000, 300), 2000)
        self.assertEqual(itens, [])

    def test_cotas_e1_e2_movem_apenas_modulo_selecionado(self):
        a, b, c = self.tres()
        antes = (a.matrix_world.copy(), c.matrix_world.copy())
        self.assertIsNone(C.editar_modulo(bpy.context, b.name, 'vao_esquerdo', 300))
        f = next(f for f in C.itens_da_face(bpy.context) if f['nome'] == b.name)
        self.assertAlmostEqual(f['vao_esquerdo'], .3, places=5)
        self.assertIsNone(C.editar_modulo(bpy.context, b.name, 'vao_direito', 250))
        f = next(f for f in C.itens_da_face(bpy.context) if f['nome'] == b.name)
        self.assertAlmostEqual(f['vao_direito'], .25, places=5)
        self.assertEqual(antes, (a.matrix_world, c.matrix_world))

    def porta(self, modulo):
        grupo = addon.portas.porta_no_modulo(modulo, folhas=2)
        return grupo, addon.portas._folhas_portas(grupo)[0]

    def clicar_porta(self, folha, modo='GRUPO', somar=False, passthrough=False, clique=False):
        from types import SimpleNamespace, MethodType
        op = SimpleNamespace(modo=modo, toggle=somar, extend=False, select_passthrough=passthrough,
                             clique=clique)
        op._soltou = MethodType(addon.selecao.OBJECT_OT_selecionar._soltou, op)
        evento = SimpleNamespace(mouse_region_x=100, mouse_region_y=100)
        with bpy.context.temp_override(area=self.area, region=self.regiao), \
             patch.object(addon.portas_viewport, '_slider_sob_mouse', return_value=None), \
             patch.object(addon.gavetas, 'slider_sob_mouse', return_value=None), \
             patch.object(addon.hud, '_ferragem_sob_mouse', return_value=None), \
             patch.object(addon.hud, '_raio_hud', return_value=(folha,)):
            resposta = addon.selecao.OBJECT_OT_selecionar._invoke(op, bpy.context, evento)
            addon.selecao._seguir_selecao_na_gaveta(bpy.context)
        return resposta

    def test_porta_na_parede_clique_modulo_duplo_so_folha_e_fora_do_2d_sem_excecao(self):
        m = self.modulo()
        grupo, folha = self.porta(m)
        self.iniciar()
        self.assertEqual(self.clicar_porta(folha), {'FINISHED'})
        self.assertEqual(bpy.context.object, m)
        self.assertEqual(bpy.context.scene.cabinet_aba, 'MODULOS')
        self.assertTrue(all(o.select_get() for o in (m, grupo, folha)))
        self.assertEqual(self.clicar_porta(folha, 'INDIVIDUAL'), {'FINISHED'})
        self.assertEqual(list(bpy.context.selected_objects), [folha])
        self.assertEqual(bpy.context.scene.cabinet_aba, 'PORTAS')
        E.encerrar()
        self.assertEqual(self.clicar_porta(folha), {'FINISHED'})
        self.assertEqual(bpy.context.object, grupo)
        self.assertFalse(m.select_get())

    def test_shift_e_click_nativo_em_porta_respeitam_o_escopo_modulo_na_parede(self):
        a, b, c = self.tres()
        grupo, folha = self.porta(b)
        C.atualizar(bpy.context)
        self.selecionar(a)
        self.assertEqual(self.clicar_porta(folha, somar=True), {'FINISHED'})
        self.assertTrue(a.select_get() and b.select_get())
        self.assertEqual(self.clicar_porta(folha, passthrough=True), {'PASS_THROUGH', 'CANCELLED'})
        self.assertTrue(a.select_get())
        self.assertEqual(self.clicar_porta(folha, clique=True), {'FINISHED'})
        self.assertEqual(bpy.context.object, b)
        self.assertFalse(a.select_get())

    def test_shift_duplo_na_porta_preserva_outros_modulos(self):
        a, b, c = self.tres()
        grupo, folha = self.porta(b)
        self.selecionar(a)
        self.clicar_porta(folha, somar=True)
        self.clicar_porta(folha, 'INDIVIDUAL', somar=True)
        self.assertTrue(a.select_get() and folha.select_get())
        self.assertFalse(b.select_get())
        self.assertFalse(grupo.select_get())

    def test_gaveta_e_prateleira_na_parede_clique_modulo_duplo_peca(self):
        a, b, c = self.tres()
        gavetas = addon.gavetas.criar_gavetas(bpy.context, a, (18, 18, 18, 300, 0),
                                              dict(quantidade=2, profundidade_mm=400))
        prateleiras = addon.prateleiras.criar_prateleiras(bpy.context, b, (18, 18, 18, 18, 0),
                                                          dict(quantidade=1, profundidade_mm=400))
        gaveta = next(o for o in gavetas.children_recursive
                      if o.type == 'MESH' and addon.chapas.MARCA_CHAPA in o)
        prateleira = addon.prateleiras.prateleiras_do_grupo(prateleiras)[0]
        C.atualizar(bpy.context)
        for modulo, peca in ((a, gaveta), (b, prateleira)):
            self.assertEqual(self.clicar_porta(peca), {'FINISHED'})
            self.assertEqual(bpy.context.object, modulo)
            familia = addon.hud._familia_do_clique(peca)
            self.assertTrue(all(o.select_get() for o in familia))
            self.assertEqual(self.clicar_porta(peca, 'INDIVIDUAL'), {'FINISHED'})
            self.assertFalse(modulo.select_get())
            self.assertTrue(peca.select_get())
        # Outside wall view, each type returns to its own selection behavior.
        E.encerrar()
        self.assertEqual(self.clicar_porta(gaveta), {'FINISHED'})
        self.assertFalse(a.select_get())

    def test_snap_de_vertice_temporario_e_devolvido(self):
        ajustes = bpy.context.scene.tool_settings
        ajustes.use_snap, ajustes.snap_elements, ajustes.snap_target = False, {'INCREMENT'}, 'CENTER'
        self.iniciar()
        self.assertTrue(ajustes.use_snap)
        # Always VERTEX; EDGE comes from guides in the default snap-enabled mode.
        self.assertIn('VERTEX', ajustes.snap_elements)
        self.assertEqual(ajustes.snap_target, 'CLOSEST')
        E.encerrar()
        self.assertFalse(ajustes.use_snap)
        self.assertEqual(set(ajustes.snap_elements), {'INCREMENT'})
        self.assertEqual(ajustes.snap_target, 'CENTER')

    def soltar_g(self, *modulos):
        # Native G marks cabinets; the timer fits them on release.
        bpy.context.view_layer.update()
        C._movidos[0] = {m.name for m in modulos}
        with bpy.context.temp_override(area=self.area, region=self.regiao), \
             patch.object(P, '_px_por_metro', return_value=1000.0):     # Snap range = 12 mm.
            return C.encaixar_movidos(bpy.context)

    def test_ima_2d_gruda_bordas_da_caixa_e_mantem_na_face(self):
        a, b, c = self.tres()
        b.location.x -= .195            # 5 mm gap to A's edge.
        b.location.z += .004            # 4 mm above the floor.
        self.assertTrue(self.soltar_g(b))
        f = C.ficha(b, E._sessao[0])
        self.assertAlmostEqual(f['inicio'], -.8, places=5)
        self.assertAlmostEqual(f['base'], 0, places=5)
        self.assertFalse(C._movidos[0])
        # Outside snap range: stay where the user released.
        b.location.x += .05
        self.assertFalse(self.soltar_g(b))
        self.assertAlmostEqual(C.ficha(b, E._sessao[0])['inicio'], -.75, places=5)
        # Outside the face, beyond the endpoint and below the floor: return inside.
        a.location.x -= 1.0
        a.location.z -= .5
        self.assertTrue(self.soltar_g(a))
        f = C.ficha(a, E._sessao[0])
        self.assertAlmostEqual(f['inicio'], -1.5, places=5)
        self.assertAlmostEqual(f['base'], 0, places=5)

    def test_lado_sob_o_mouse_e_ima_do_lado_inteiro(self):
        f = dict(inicio=0.0, fim=.6, base=0.0, largura=.6, altura=.72)
        self.assertEqual(C.lado_sob(f, .01, .3, .024), 'esquerda')
        self.assertEqual(C.lado_sob(f, .59, .3, .024), 'direita')
        self.assertEqual(C.lado_sob(f, .3, .71, .024), 'topo')
        self.assertEqual(C.lado_sob(f, .3, -.01, .024), 'base')
        # In the box center or at another object's height, neither side is grabbed.
        self.assertIsNone(C.lado_sob(f, .3, .36, .024))
        self.assertIsNone(C.lado_sob(f, .01, 1.5, .024))
        alvos = ([-.2, 1.0], [0.0, .9])
        # Only the grabbed side snaps; the other axis remains free.
        self.assertEqual(C.posicao_com_ima(f, -.195, .004, alvos, 'esquerda', .012),
                         (-.2, .004, [('x', -.2)]))
        inicio, base, _l = C.posicao_com_ima(f, .395, .004, alvos, 'esquerda', .012)
        self.assertAlmostEqual(inicio, .395)          # The right side does not count.
        inicio, base, _l = C.posicao_com_ima(f, .395, .004, alvos, 'direita', .012)
        self.assertAlmostEqual(inicio, .4)
        self.assertAlmostEqual(base, .004)
        # Without a grabbed side, use the nearest edge on each axis, as on G release.
        inicio, base, linhas = C.posicao_com_ima(f, -.195, .175, alvos, None, .012)
        self.assertAlmostEqual(inicio, -.2)
        self.assertAlmostEqual(base, .18)              # Top .895 -> .9.
        self.assertEqual(len(linhas), 2)

    def test_alt_gruda_quina_com_quina_no_plano(self):
        f = dict(inicio=0.0, fim=.6, base=0.0, largura=.6, altura=.72)
        quinas = [(-.2, .72)]
        # Mouse over the target corner moves the nearest box corner to it.
        inicio, base, linhas = C.posicao_com_ima(f, -.195, .725, ([], []), None, .012,
                                                 quinas, (-.195, .725))
        self.assertAlmostEqual(inicio, -.2)
        self.assertAlmostEqual(base, .72)
        self.assertEqual(linhas, [('x', -.2), ('z', .72)])
        # Far from a corner: no target means no movement; grabbed sides still apply.
        self.assertEqual(C.posicao_com_ima(f, -.1, .5, ([], []), None, .012, quinas, (-.1, .5))[:2],
                         (-.1, .5))
        inicio, base, linhas = C.posicao_com_ima(f, -.195, .5, ([-.2], []), None, .012,
                                                 quinas, (-.1, .5))
        self.assertAlmostEqual(inicio, -.2)
        self.assertEqual(linhas, [('x', -.2)])
        # Without Alt, laterais is False: only the corner snaps within its tolerance.
        self.assertEqual(C.posicao_com_ima(f, -.195, .5, ([-.2], []), None, .012,
                                           quinas, (-.1, .5), laterais=False), (-.195, .5, []))
        inicio, base, linhas = C.posicao_com_ima(f, -.19, .73, ([], []), None, .012,
                                                 quinas, (-.19, .73), laterais=False,
                                                 tolerancia_quina=.016)
        self.assertEqual((round(inicio, 6), round(base, 6)), (-.2, .72))

    def mover(self, modulo, grudar_em, destino, arrastar=False, alt=False, ctrl=False, esc=False):
        """Reproduce real operator events: G or drag on the cabinet, grabbing face point grudar_em (x, z) and releasing at destino."""
        from types import MethodType
        from bpy_extras import view3d_utils
        s = E._sessao[0]
        rv3d = self.area.spaces.active.region_3d
        u, ponto = Vector(s['u']), Vector(s['ponto'])

        def evento(x, z, tipo='MOUSEMOVE', valor='NOTHING'):
            p = ponto + u * (x - ponto.dot(u))
            p.z = z
            xy = view3d_utils.location_3d_to_region_2d(self.regiao, rv3d, p)
            return SimpleNamespace(type=tipo, value=valor, mouse_x=self.regiao.x + xy.x,
                                   mouse_y=self.regiao.y + xy.y, ctrl=ctrl, alt=alt,
                                   shift=False, oskey=False)
        op = SimpleNamespace(modulo=modulo.name, arrastar=arrastar)
        for nome in dir(C.OBJECT_OT_mover_na_parede):
            metodo = getattr(C.OBJECT_OT_mover_na_parede, nome)
            if callable(metodo) and nome.startswith(('_', 'invoke', 'modal', 'cancel')) \
                    and not nome.startswith('__'):
                setattr(op, nome, MethodType(metodo, op))

        class Contexto:
            window_manager = SimpleNamespace(modal_handler_add=lambda op: None)
            def __getattr__(self, nome):
                return getattr(bpy.context, nome)
        contexto = Contexto()
        with bpy.context.temp_override(area=self.area, region=self.regiao), \
             patch.object(P, '_px_por_metro', return_value=1000.0):     # Snap range = 12 mm.
            self.assertEqual(op.invoke(contexto, evento(*grudar_em, 'G', 'PRESS')), {'RUNNING_MODAL'})
            if arrastar:
                self.assertEqual(op.modal(contexto, evento(*grudar_em)), {'PASS_THROUGH'})
            op.modal(contexto, evento(*destino))
            self.assertIsNotNone(C._movendo[0])
            fim = (evento(*destino, 'ESC', 'PRESS') if esc else
                   evento(*destino, 'LEFTMOUSE', 'RELEASE' if arrastar else 'PRESS'))
            return op, op.modal(contexto, fim)

    def test_g_perto_da_lateral_gruda_so_ela_no_vizinho(self):
        a, b, c = self.tres()
        # Without Alt, movement is free and does not snap, as requested.
        op, fim = self.mover(b, (-.6, .36), (-.795, .364))
        self.assertAlmostEqual(C.ficha(b, E._sessao[0])['inicio'], -.795, delta=.002)
        op, fim = self.mover(b, (-.795, .364), (-.6, .36))
        # Alt: grab B by its left side, 5 mm from A's edge and 4 mm above.
        op, fim = self.mover(b, (-.6, .36), (-.795, .364), alt=True)
        self.assertEqual(fim, {'FINISHED'})
        self.assertEqual(op._lado, 'esquerda')
        f = C.ficha(b, E._sessao[0])
        self.assertAlmostEqual(f['inicio'], -.8, places=5)
        # Free: not even the floor snaps within 12 mm; float32 screen coordinates require delta.
        self.assertAlmostEqual(f['base'], .004, delta=.001)
        self.assertAlmostEqual(f['afastamento'], 0, places=5)   # Never leaves the plane.
        self.assertIsNone(C._movendo[0])
        # Grab at the center: each axis snaps its nearest edge, here the floor.
        op, fim = self.mover(b, (-.5, .3), (-.48, .296), alt=True)
        self.assertIsNone(op._lado)
        self.assertAlmostEqual(C.ficha(b, E._sessao[0])['base'], 0, places=5)

    def test_circulo_na_quina_sob_o_mouse_e_a_quina_pega_gruda(self):
        # User request from the Paint sketch: hovering near a cabinet corner highlights
        # the corner-snap circle. G/drag while highlighted grabs that corner,
        # which snaps to its nearest target corner.
        from bpy_extras import view3d_utils
        a, b, c = self.tres()
        s = E._sessao[0]
        f = C.ficha(b, s)
        self.assertEqual(C.quina_sob(f, -.595, .715, .016), (0, 1))
        self.assertIsNone(C.quina_sob(f, -.3, .36, .016))
        rv3d = self.area.spaces.active.region_3d
        u, ponto = Vector(s['u']), Vector(s['ponto'])

        def evento(x, z):
            p = ponto + u * (x - ponto.dot(u))
            p.z = z
            xy = view3d_utils.location_3d_to_region_2d(self.regiao, rv3d, p)
            return SimpleNamespace(type='MOUSEMOVE', mouse_x=self.regiao.x + xy.x,
                                   mouse_y=self.regiao.y + xy.y)
        with patch.object(P, '_px_por_metro', return_value=1000.0):     # 16 px = 16 mm.
            C.atualizar_quina_hover(evento(-.595, .715), self.regiao, rv3d)
            nome, (x, z) = C._quina_hover[0]
            self.assertEqual(nome, b.name)
            self.assertAlmostEqual(x, -.6, places=5)
            self.assertAlmostEqual(z, .72, places=5)
            C.atualizar_quina_hover(evento(-.3, .36), self.regiao, rv3d)
            self.assertIsNone(C._quina_hover[0])
        # Grab the upper-left corner and move it within 11 mm of A's upper corner.
        op, fim = self.mover(b, (-.595, .715), (-.79, .725), arrastar=True)
        self.assertEqual(op._quina, (0, 1))
        self.assertIsNone(op._lado)                 # Corner takes precedence over side.
        self.assertEqual(fim, {'FINISHED'})
        f = C.ficha(b, s)
        self.assertAlmostEqual(f['inicio'], -.8, places=5)
        self.assertAlmostEqual(f['base'], 0.0, places=5)
        # With a corner grabbed, only it snaps; far from a target corner, nothing snaps.
        inicio, base, linhas = C.posicao_com_ima(f, -.3, .2, ([], []), None, .012,
                                                 [(-.8, .72)], (-.3, .2), quina=(0, 1))
        self.assertEqual((inicio, base, linhas), (-.3, .2, []))

    def test_arraste_esquerdo_gruda_na_quina_sem_alt_e_esc_restaura(self):
        a, b, c = self.tres()
        # User request: corners snap when the mouse approaches, without Alt.
        # Left-drag B's lower corner to A's upper corner, with the mouse 14 px away;
        # side snapping has a 12 mm range.
        op, fim = self.mover(b, (-.6, 0), (-.79, .73), arrastar=True)
        self.assertEqual(fim, {'FINISHED'})
        f = C.ficha(b, E._sessao[0])
        self.assertAlmostEqual(f['inicio'], -.8, places=5)
        self.assertAlmostEqual(f['base'], .72, places=5)
        # Ctrl does nothing; only Alt enables side snapping. Esc restores position and point.
        antes = b.matrix_world.copy()
        ponto = tuple(b[P.CHAVE_PAREDE_PONTO])
        op, fim = self.mover(b, (-.6, .9), (-.3, 1.0), ctrl=True, esc=True)
        self.assertEqual(fim, {'CANCELLED'})
        for x, y in zip(sum(map(list, b.matrix_world), []), sum(map(list, antes), [])):
            self.assertAlmostEqual(x, y, places=5)
        for x, y in zip(b[P.CHAVE_PAREDE_PONTO], ponto):
            self.assertAlmostEqual(x, y, places=6)
        self.assertIsNone(C._movendo[0])

    def test_g_e_clique_no_modulo_da_parede_vao_para_o_mover(self):
        a, b, c = self.tres()
        porta = b.children_recursive[0]
        evento = SimpleNamespace(type='LEFTMOUSE', value='PRESS', mouse_x=10, mouse_y=10,
                                 shift=False, ctrl=False, alt=False, oskey=False)
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            with patch.object(addon.hud, '_raio_hud', return_value=(porta,)):
                self.assertEqual(E.modulo_para_mover(bpy.context, evento, self.regiao), b.name)
                evento.shift = True
                self.assertIsNone(E.modulo_para_mover(bpy.context, evento, self.regiao))
                evento.shift = False
                # With multiple cabinets selected, dragging remains native.
                for o in (a, b):
                    o.select_set(True)
                porta.select_set(True)
                self.assertIsNone(E.modulo_para_mover(bpy.context, evento, self.regiao))
            # G, the user's shortcut, with only the cabinet selected.
            self.selecionar(b)
            evento.type = 'G'
            with patch.object(E, '_tecla_de_mover', return_value=True):
                self.assertEqual(E.modulo_para_mover(bpy.context, evento, self.regiao), b.name)
                a.select_set(True)
                self.assertIsNone(E.modulo_para_mover(bpy.context, evento, self.regiao))
            with patch.object(E, '_tecla_de_mover', return_value=False):
                self.selecionar(b)
                self.assertIsNone(E.modulo_para_mover(bpy.context, evento, self.regiao))

    def test_ima_so_para_o_gesto_nativo_nunca_para_medida_digitada(self):
        a, b, c = self.tres()
        with patch.object(C._eventos, '_transformando', return_value=True):
            c.location.x += .01
            bpy.context.view_layer.update()
        self.assertIn(c.name, C._movidos[0])
        C._movidos[0] = set()
        with patch.object(C._eventos, '_transformando', return_value=False):
            c.location.x += .01
            bpy.context.view_layer.update()
        self.assertFalse(C._movidos[0])
        # A typed 5 mm stays 5 mm despite the 12 mm snap range.
        C._movidos[0] = {b.name}
        self.assertIsNone(C.editar_modulo(bpy.context, b.name, 'vao_esquerdo', 5))
        self.assertFalse(self.soltar_g())
        self.assertAlmostEqual(self.ficha_de(b)['vao_esquerdo'], .005, places=5)

    def test_cotas_acompanham_o_arraste_sem_reler_malhas(self):
        a, b, c = self.tres()
        antes = next(f for f in C._resumo[0]['itens'] if f['nome'] == b.name)
        with patch.object(P, 'caixa_do_modulo', side_effect=AssertionError('Releu a malha')), \
             patch.object(E, 'associados', side_effect=AssertionError('Refez a busca')):
            b.location.x += .1
            bpy.context.view_layer.update()
        depois = next(f for f in C._resumo[0]['itens'] if f['nome'] == b.name)
        self.assertAlmostEqual(depois['inicio'] - antes['inicio'], .1, places=5)
        self.assertAlmostEqual(depois['largura'], antes['largura'], places=6)
        self.assertAlmostEqual(depois['vao_esquerdo'], .3, places=5)
        vizinho = next(f for f in C._resumo[0]['itens'] if f['nome'] == c.name)
        self.assertAlmostEqual(vizinho['vao_esquerdo'], .1, places=5)
        # The regular tick reaches the same value.
        C.atualizar(bpy.context)
        conferido = next(f for f in C._resumo[0]['itens'] if f['nome'] == b.name)
        self.assertAlmostEqual(conferido['inicio'], depois['inicio'], places=6)

    def objeto_guias(self):
        return next((o for o in bpy.data.objects if C.MARCA_OBJETO_GUIAS in o), None)

    def alturas_das_guias(self):
        obj = self.objeto_guias()
        return sorted({round((obj.matrix_world @ v.co).z, 6) for v in obj.data.vertices})

    def ficha_de(self, obj):
        return next(f for f in C.itens_da_face(bpy.context) if f['nome'] == obj.name)

    def test_cotas_do_promob_inferior_superior_e_vizinhos(self):
        a, b, c = self.tres()
        alto = self.modulo(inicio=-1.4, base=1.5, nome='Alto')
        C.atualizar(bpy.context)
        baixo, cima = self.ficha_de(a), self.ficha_de(alto)
        self.assertAlmostEqual(baixo['cota_inferior'], 0, places=5)
        self.assertAlmostEqual(baixo['cota_superior'], 1.5 - .72, places=5)
        self.assertAlmostEqual(cima['cota_inferior'], 1.5 - .72, places=5)
        self.assertAlmostEqual(cima['cota_superior'], 2.7 - 1.5 - .72, places=5)
        # A lower neighbor does not count for the upper cabinet's previous/next distances.
        self.assertAlmostEqual(cima['vao_esquerdo'], .1, places=5)
        self.assertAlmostEqual(cima['vao_direito'], 1.5 + .8, places=5)
        self.assertIsNone(C.editar_modulo(bpy.context, alto.name, 'cota_inferior', 900))
        self.assertAlmostEqual(self.ficha_de(alto)['base'], .72 + .9, places=5)
        self.assertIsNone(C.editar_modulo(bpy.context, alto.name, 'cota_superior', 100))
        self.assertAlmostEqual(self.ficha_de(alto)['base'], 2.7 - .1 - .72, places=5)
        antes = alto.matrix_world.copy()
        self.assertIsNotNone(C.editar_modulo(bpy.context, alto.name, 'cota_superior', 5000))
        self.assertEqual(alto.matrix_world, antes)

    def test_afastamento_da_parede_resiste_ao_timer_e_ao_g(self):
        a, b, c = self.tres()
        self.assertAlmostEqual(self.ficha_de(b)['afastamento'], 0, places=6)
        self.assertIsNone(C.editar_modulo(bpy.context, b.name, 'afastamento', 50))
        self.assertAlmostEqual(self.ficha_de(b)['afastamento'], .05, places=5)
        self.assertAlmostEqual(b[P.CHAVE_AFASTAMENTO], 50)
        b.location.x += .05
        bpy.context.view_layer.update()
        P.manter_nas_paredes()
        f = self.ficha_de(b)
        self.assertAlmostEqual(f['afastamento'], .05, places=5)
        self.assertAlmostEqual(f['vao_esquerdo'], .25, places=5)
        self.assertIsNone(C.editar_modulo(bpy.context, b.name, 'afastamento', 0))
        self.assertNotIn(P.CHAVE_AFASTAMENTO, b)
        self.assertAlmostEqual(self.ficha_de(b)['afastamento'], 0, places=5)
        P.desassociar(b)
        self.assertNotIn(P.CHAVE_AFASTAMENTO, b)

    def test_menu_mostra_cotas_em_cruz_simetrica_e_estreita(self):
        a, b, c = self.tres()
        for largura, rotulos in ((564, ("Above", "Previous", "Offset", "Next", "Below")),
                                 (190, ("Above", "Prev", "Offset", "Next", "Below"))):
            itens = []
            C.widgets(bpy.context, itens, 12, 1000, largura - 24)
            campos = {i[5][2]: i for i in itens if i[5] and i[5][0] == 'medida'}
            self.assertEqual(set(campos), {'largura', 'altura', 'profundidade', 'cota_superior',
                                           'vao_esquerdo', 'afastamento', 'vao_direito', 'cota_inferior'})
            self.assertEqual(tuple(campos[n][5][3] for n in ('cota_superior', 'vao_esquerdo', 'afastamento',
                                                           'vao_direito', 'cota_inferior')), rotulos)
            self.assertTrue(all(i[2] <= C.LARGURA_CAMPO_COTA for i in campos.values()))
            meio = lambda n: campos[n][0] + campos[n][2] / 2
            for n in ('cota_superior', 'cota_inferior', 'altura'):
                self.assertAlmostEqual(meio(n), meio('afastamento'))
            self.assertAlmostEqual(meio('vao_esquerdo') + meio('vao_direito'), 2 * meio('afastamento'))
            self.assertAlmostEqual(meio('afastamento'), 12 + (largura - 24) / 2)
            self.assertGreater(campos['cota_superior'][1], campos['afastamento'][1])
            self.assertGreater(campos['afastamento'][1], campos['cota_inferior'][1])

    def test_guias_padrao_so_na_vista_da_parede_com_snap_de_aresta(self):
        ajustes = bpy.context.scene.tool_settings
        ajustes.snap_elements, ajustes.use_snap_selectable = {'INCREMENT'}, True
        self.assertIsNone(self.objeto_guias())
        self.iniciar()
        obj = self.objeto_guias()
        self.assertIsNotNone(obj)
        self.assertEqual(self.alturas_das_guias(), [a / 1000 for _n, a in C.GUIAS_PADRAO])
        # Each guide spans the face end to end, just in front of it, using short
        # mesh-based dashes for the dotted appearance requested by the user.
        s0, s1 = E._sessao[0]['regiao']['retangulo'][:2]
        xs = [v.co.x for v in obj.data.vertices]
        self.assertAlmostEqual(min(xs), s0, places=6)
        self.assertAlmostEqual(max(xs), s1, places=6)
        tracos = math.ceil((s1 - s0) / C.PASSO_GUIA_M - 1e-9)
        self.assertIn(len(obj.data.edges), (tracos * len(C.GUIAS_PADRAO),
                                            (tracos + 1) * len(C.GUIAS_PADRAO)))
        for aresta in obj.data.edges:
            a, b = (obj.data.vertices[i].co for i in aresta.vertices)
            self.assertLessEqual((b - a).length, C.TRACO_GUIA_M + 1e-6)
        self.assertTrue(obj.hide_select)
        self.assertEqual(set(ajustes.snap_elements), {'VERTEX', 'EDGE'})
        self.assertFalse(ajustes.use_snap_selectable)
        E.encerrar()
        self.assertIsNone(self.objeto_guias())
        self.assertEqual(set(ajustes.snap_elements), {'INCREMENT'})
        self.assertTrue(ajustes.use_snap_selectable)

    def test_guia_editada_no_menu_e_na_viewport(self):
        from types import SimpleNamespace, MethodType
        self.iniciar()
        self.assertIsNone(addon.gaveta_eventos.aplicar_medida(bpy.context, 'parede_guia', '', '1', .85))
        self.assertAlmostEqual(C.guias(bpy.context.scene)[1]['altura_mm'], 850)
        self.assertIn(.85, self.alturas_das_guias())
        self.assertIsNotNone(C.editar_guia(bpy.context, 1, 5000))
        self.assertIsNotNone(C.editar_guia(bpy.context, 1, 0))
        self.assertAlmostEqual(C.guias(bpy.context.scene)[1]['altura_mm'], 850)
        # Viewport label: same hit-test and text entry as dimensions.
        C._rotulos_guias[0] = ((10, 20, 60, 20, '', 'guia_4', 2150.0),)
        self.assertEqual(C.cota_sob(15, 25)[5], 'guia_4')
        op = SimpleNamespace(objeto='', propriedade='guia_4', report=lambda *a: None)
        op._guia = MethodType(C.OBJECT_OT_editar_cota_parede._guia, op)
        op.cancel = MethodType(C.OBJECT_OT_editar_cota_parede.cancel, op)
        C._edicao[0] = dict(objeto='', propriedade='guia_4', texto='2200', cursor=4, selecionado=False)
        evento = SimpleNamespace(value='PRESS', type='RET', ctrl=False, unicode='')
        self.assertEqual(C.OBJECT_OT_editar_cota_parede._modal(op, bpy.context, evento), {'FINISHED'})
        self.assertAlmostEqual(C.guias(bpy.context.scene)[4]['altura_mm'], 2200)
        self.assertIn(2.2, self.alturas_das_guias())
        self.assertIsNone(C._edicao[0])
        bpy.ops.object.cabinet_restaurar_guias_parede()
        self.assertEqual(self.alturas_das_guias(), [a / 1000 for _n, a in C.GUIAS_PADRAO])

    def test_guias_e_snap_ligam_e_desligam(self):
        ajustes = bpy.context.scene.tool_settings
        self.iniciar()
        self.assertIsNone(C.definir_modo_guias(bpy.context, 'VISIVEIS'))
        self.assertIsNotNone(self.objeto_guias())
        self.assertEqual(set(ajustes.snap_elements), {'VERTEX'})
        # Edges remain visible, but the native filter excludes them from snapping.
        self.assertTrue(ajustes.use_snap_selectable)
        self.assertIsNone(C.definir_modo_guias(bpy.context, 'OCULTAS'))
        self.assertIsNone(self.objeto_guias())
        self.assertEqual(set(ajustes.snap_elements), {'VERTEX'})
        self.assertIsNotNone(C.definir_modo_guias(bpy.context, 'OUTRO'))
        itens = []
        C.widgets_guias(bpy.context, itens, 0, 600, 300)
        modos = [i[5][2] for i in itens if i[5] and i[5][0] == 'escolha']
        self.assertEqual(modos, [m for m, _r in C.MODOS_GUIAS])
        self.assertEqual([i[5][2] for i in itens if i[5] and i[5][0] == 'escolha' and i[5][3]], ['OCULTAS'])
        self.assertIsNone(C.definir_modo_guias(bpy.context, 'SNAP'))
        self.assertIsNotNone(self.objeto_guias())
        self.assertEqual(set(ajustes.snap_elements), {'VERTEX', 'EDGE'})

    def test_rotulo_da_guia_acompanha_o_zoom(self):
        from types import SimpleNamespace
        self.iniciar()
        # Background ui_scale is 0; use a scale-1 context with a 14 px dimension label.
        maximo = 14
        contexto = SimpleNamespace(
            preferences=SimpleNamespace(system=SimpleNamespace(ui_scale=1.0)),
            region=self.regiao, region_data=self.area.spaces.active.region_3d,
            scene=bpy.context.scene)
        def tamanhos(px_por_metro):
            desenhados = []
            def projetar(regiao, rv, ponto):
                return Vector((300 + ponto.x * px_por_metro, 200 + ponto.z * px_por_metro))
            with patch.object(C, 'gpu'), patch.object(C, 'batch_for_shader'), \
                 patch.object(C, 'estilo_cotas', return_value={'tamanho': maximo}), \
                 patch.object(C._hud, '_caixa_texto_hud', side_effect=lambda *a: desenhados.append(a[3])), \
                 patch.object(C, 'texto_discreto', side_effect=lambda *a: desenhados.append(a[3])), \
                 patch.object(C.view3d_utils, 'location_3d_to_region_2d', side_effect=projetar):
                C.desenhar_guias(contexto)
            return desenhados
        perto, longe = tamanhos(1000), tamanhos(150)
        self.assertEqual(perto, [maximo] * len(C.GUIAS_PADRAO))
        self.assertAlmostEqual(longe[0], C.ALTURA_ROTULO_GUIA_M * 150, places=4)
        self.assertEqual(len(C._rotulos_guias[0]), len(C.GUIAS_PADRAO))
        # Too far away: neither label nor click target.
        self.assertEqual(tamanhos(50), [])
        self.assertEqual(C._rotulos_guias[0], ())

    def test_rotulo_da_guia_so_ganha_caixa_preta_com_o_mouse_em_cima(self):
        from types import SimpleNamespace
        self.iniciar()
        contexto = SimpleNamespace(
            preferences=SimpleNamespace(system=SimpleNamespace(ui_scale=1.0)),
            region=self.regiao, region_data=self.area.spaces.active.region_3d,
            scene=bpy.context.scene)
        def desenhar():
            caixas, discretos = [], []
            def projetar(regiao, rv, ponto):
                return Vector((300 + ponto.x * 1000, 200 + ponto.z * 1000))
            with patch.object(C, 'gpu'), patch.object(C, 'batch_for_shader'), \
                 patch.object(C, 'estilo_cotas', return_value={'tamanho': 14}), \
                 patch.object(C._hud, '_caixa_texto_hud', side_effect=lambda *a: caixas.append(a[2])), \
                 patch.object(C, 'texto_discreto', side_effect=lambda *a: discretos.append(a[2])), \
                 patch.object(C.view3d_utils, 'location_3d_to_region_2d', side_effect=projetar):
                C.desenhar_guias(contexto)
            return caixas, discretos
        caixas, discretos = desenhar()
        self.assertEqual(caixas, [])
        self.assertEqual(len(discretos), len(C.GUIAS_PADRAO))
        r = C._rotulos_guias[0][1]
        C.atualizar_guia_hover(r[0] + 2, r[1] + 2)
        self.assertEqual(C._guia_hover[0], 'guia_1')
        caixas, discretos = desenhar()
        self.assertEqual(len(caixas), 1)
        self.assertIn(C.GUIAS_PADRAO[1][0], caixas[0])
        self.assertEqual(len(discretos), len(C.GUIAS_PADRAO) - 1)
        C.atualizar_guia_hover(None, None)
        self.assertIsNone(C._guia_hover[0])

    def test_cursor_de_digitacao_pisca_na_posicao(self):
        desenhos = []
        def batch(shader, tipo, dados):
            from types import SimpleNamespace
            desenhos.append((tipo, dados['pos']))
            return SimpleNamespace(draw=lambda s: None)
        edicao = dict(objeto='', propriedade='guia_0', texto='1500', cursor=2, selecionado=False)
        with patch.object(C, 'gpu'), patch.object(C, 'batch_for_shader', side_effect=batch), \
             patch.object(C._hud, '_caixa_texto_hud'):
            with patch.object(C, 'cursor_aceso', return_value=True):
                C.caixa_editavel(100, 50, '1500 - Base do aereo', edicao, 14, 1)
            with patch.object(C, 'cursor_aceso', return_value=False):
                C.caixa_editavel(100, 50, '1500 - Base do aereo', edicao, 14, 1)
            edicao['selecionado'] = True
            with patch.object(C, 'cursor_aceso', return_value=False):
                C.caixa_editavel(100, 50, '1500 - Base do aereo', edicao, 14, 1)
        C.blf.size(0, 14)
        x = 100 + C.blf.dimensions(0, '1.5')[0]
        self.assertEqual([d[0] for d in desenhos], ['LINES', 'TRIS'])
        self.assertAlmostEqual(desenhos[0][1][0][0], x)
        self.assertTrue(C.cursor_aceso(0.1))
        self.assertFalse(C.cursor_aceso(C.PISCA_CURSOR_S + .1))

    def test_undo_que_devolve_guias_e_snap_e_limpo_pelo_timer(self):
        ajustes = bpy.context.scene.tool_settings
        ajustes.snap_elements, ajustes.snap_target = {'INCREMENT'}, 'CENTER'
        self.iniciar()
        guardado = dict(bpy.context.scene[E.CHAVE_SNAP])
        E.encerrar()
        # Undo snapshot restores object, marker and view snapping without a session.
        bpy.context.scene[E.CHAVE_SNAP] = guardado
        ajustes.snap_elements, ajustes.snap_target = {'VERTEX', 'EDGE'}, 'CLOSEST'
        sobra = bpy.data.objects.new("Wall guides", bpy.data.meshes.new("Wall guides"))
        sobra[C.MARCA_OBJETO_GUIAS] = 1
        bpy.context.scene.collection.objects.link(sobra)
        E.verificar()
        self.assertIsNone(self.objeto_guias())
        self.assertNotIn(E.CHAVE_SNAP, bpy.context.scene)
        self.assertEqual(set(ajustes.snap_elements), {'INCREMENT'})
        self.assertEqual(ajustes.snap_target, 'CENTER')

    def test_interior_usa_arestas_reais_sem_alterar_malha_e_ignora_portas_e_fundo(self):
        m = self.modulo()
        grupo, folha = self.porta(m)
        self.iniciar(m)
        C.atualizar(bpy.context)
        self.assertTrue(C._interiores[0])
        self.assertFalse(any(o.name in C._interiores[0] for o in addon.portas._folhas_portas(grupo)))
        self.assertFalse(any(bpy.data.objects[n].get('eh_fundo_modulo') for n in C._interiores[0]))
        for nome, dado in C._interiores[0].items():
            obj = bpy.data.objects[nome]
            antes = (obj.data.as_pointer(), tuple(tuple(v.co) for v in obj.data.vertices))
            pontos = {tuple(round(c, 6) for c in obj.matrix_world @ v.co) for v in obj.data.vertices}
            self.assertTrue(all(tuple(round(c, 6) for c in p) in pontos for p in dado['linhas']))
            self.assertEqual(antes, (obj.data.as_pointer(), tuple(tuple(v.co) for v in obj.data.vertices)))
        self.assertIsNotNone(C._handler_interior[0])
        E.encerrar()
        self.assertEqual(C._interiores[0], {})
        self.assertIsNone(C._handler_interior[0])

    def test_cache_interior_invalida_ao_editar_e_transformar_sem_reler_no_redraw(self):
        m = self.modulo()
        self.iniciar(m)
        bpy.context.view_layer.update()
        C.atualizar(bpy.context)
        with patch.object(C, '_arestas_avaliadas', side_effect=AssertionError('Releitura indevida')):
            C.atualizar(bpy.context)
            with patch.object(C, 'gpu'), patch.object(C, 'batch_for_shader'):
                with bpy.context.temp_override(area=self.area, region=self.regiao):
                    C.desenhar_interiores()
            with patch.object(C._eventos, '_ha_modal_ativo', return_value=True), \
                 patch.object(C, 'batch_for_shader') as desenho:
                with bpy.context.temp_override(area=self.area, region=self.regiao):
                    C.desenhar_interiores()
                desenho.assert_not_called()
        nome = next(iter(C._interiores[0]))
        obj = bpy.data.objects[nome]
        antes = C._interiores[0][nome]['linhas']
        obj.data.vertices[0].co.x += .02
        obj.data.update()
        bpy.context.view_layer.update()
        C.atualizar(bpy.context)
        self.assertNotEqual(antes, C._interiores[0][nome]['linhas'])
        antes = C._interiores[0][nome]['linhas']
        obj.location.z += .03
        bpy.context.view_layer.update()
        C.atualizar(bpy.context)
        self.assertNotEqual(antes, C._interiores[0][nome]['linhas'])

    def test_cotas_ficam_proximas_da_peca_selecionada_em_vez_do_fim_da_composicao(self):
        from types import SimpleNamespace
        a, b, c = self.tres()
        f = C.ficha(a, E._sessao[0])
        escala = 1
        class ContextoCotas:
            preferences = SimpleNamespace(system=SimpleNamespace(ui_scale=1), themes=bpy.context.preferences.themes)
            def __getattr__(self, nome):
                return getattr(bpy.context, nome)
        def projetar(regiao, rv, ponto):
            return Vector((300 + ponto.x * 100, 200 + ponto.z * 100))
        with bpy.context.temp_override(area=self.area, region=self.regiao), \
             patch.object(C, 'gpu'), patch.object(C, 'batch_for_shader'), \
             patch.object(C._hud, '_caixa_texto_hud'), \
             patch.object(C, 'modulo_em_edicao', return_value=a.name), \
             patch.object(C, 'area_livre', return_value=(0, 0, 2000, 2000)), \
             patch.object(C.view3d_utils, 'location_3d_to_region_2d', side_effect=projetar):
            C.desenhar(ContextoCotas())
        altura = next(r for r in C._rotulos[0] if r[5] == 'altura')
        self.assertAlmostEqual(altura[0] + 5, 300 + f['fim'] * 100 + 16 * escala, places=4)
        largura = next(r for r in C._rotulos[0] if r[4] == a.name and r[5] == 'largura')
        self.assertGreater(largura[1], 200 + f['base'] * 100 - 30 * escala)

    def test_cotas_contrastam_por_tema_claro_e_escuro_sem_usar_wire(self):
        from types import SimpleNamespace
        for texto, fundo in (((.95,.95,.95), (.12,.12,.12)), ((.05,.05,.05), (.8,.8,.8))):
            tema = SimpleNamespace(user_interface=SimpleNamespace(wcol_regular=
                                     SimpleNamespace(text=texto, inner=fundo)))
            estilo = C.estilo_cotas(SimpleNamespace(preferences=SimpleNamespace(themes=[tema])))
            self.assertEqual(estilo['linha'], (*texto, 1))
            self.assertEqual(estilo['halo'], (*fundo, 1))
            self.assertGreaterEqual(estilo['tamanho'], 14)
            self.assertGreater(abs(estilo['linha'][0] - estilo['halo'][0]), .7)

    def test_cota_desenha_halo_e_setas_antes_do_rotulo_editavel(self):
        self.tres()
        ordem = []
        def batch(*args, **kwargs):
            from types import SimpleNamespace
            ordem.append(('geometria', kwargs['pos'] if 'pos' in kwargs else args[2]['pos']))
            return SimpleNamespace(draw=lambda shader: ordem.append(('linha', None)))
        def projetar(regiao, rv, ponto):
            return Vector((300 + ponto.x * 100, 200 + ponto.z * 100))
        with bpy.context.temp_override(area=self.area, region=self.regiao), \
             patch.object(C, 'gpu') as gpu, patch.object(C, 'batch_for_shader', side_effect=batch), \
             patch.object(C._hud, '_caixa_texto_hud', side_effect=lambda *a: ordem.append(('texto', a))), \
             patch.object(C.view3d_utils, 'location_3d_to_region_2d', side_effect=projetar):
            C.desenhar(bpy.context)
        self.assertGreater(len(ordem[0][1]), 6)
        self.assertLess(max(i for i, a in enumerate(ordem) if a[0] == 'linha'),
                        min(i for i, a in enumerate(ordem) if a[0] == 'texto'))
        escala = bpy.context.preferences.system.ui_scale or 1.0
        self.assertIn(4 * escala, [c.args[0] for c in gpu.state.line_width_set.call_args_list])
        self.assertTrue(C._rotulos[0])

    def test_circulo_da_quina_e_desenhado_no_realce(self):
        # Corner-snap circle from the user's screenshot, at the corner under the mouse.
        a, b, c = self.tres()
        posicoes = []
        def batch(*args, **kwargs):
            from types import SimpleNamespace
            posicoes.append(kwargs['pos'] if 'pos' in kwargs else args[2]['pos'])
            return SimpleNamespace(draw=lambda shader: None)
        def projetar(regiao, rv, ponto):
            return Vector((300 + ponto.x * 100, 200 + ponto.z * 100))
        C._quina_hover[0] = (b.name, (-.6, .72))
        try:
            with bpy.context.temp_override(area=self.area, region=self.regiao), \
                 patch.object(C, 'gpu'), patch.object(C, 'batch_for_shader', side_effect=batch), \
                 patch.object(C._hud, '_caixa_texto_hud'), \
                 patch.object(C.view3d_utils, 'location_3d_to_region_2d', side_effect=projetar):
                C.desenhar(bpy.context)
        finally:
            C._quina_hover[0] = None
        centro = Vector((300 - 60, 200 + 72))
        raio = C.RAIO_QUINA_PX * (bpy.context.preferences.system.ui_scale or 1.0)
        no_circulo = [p for pos in posicoes for p in pos
                      if abs((Vector(p[:2]) - centro).length - raio) < 1e-3]
        self.assertGreaterEqual(len(no_circulo), 2 * 24)

    def desenhar_rotulos(self, projetar=None, livre=(0, 0, 2000, 2000)):
        """Return {(modulo, propriedade)} for dimensions currently drawn."""
        if projetar is None:
            def projetar(regiao, rv, ponto):
                return Vector((300 + ponto.x * 100, 200 + ponto.z * 100))
        with bpy.context.temp_override(area=self.area, region=self.regiao), \
             patch.object(C, 'gpu'), patch.object(C, 'batch_for_shader') as lotes, \
             patch.object(C._hud, '_caixa_texto_hud'), \
             patch.object(C, 'area_livre', return_value=livre), \
             patch.object(C.view3d_utils, 'location_3d_to_region_2d', side_effect=projetar):
            C.desenhar(bpy.context)
        self.lotes_desenho = lotes.call_args_list
        return {(r[4], r[5]) for r in C._rotulos[0]}

    def test_a1_a2_a3_identificam_medidas_e_profundidade_sai_da_quina(self):
        m = self.modulo(base=.3)
        self.iniciar(m)
        self.assertIsNone(C.editar_modulo(bpy.context, m.name, 'afastamento', 50))
        textos = []
        with patch.object(C, 'caixa_editavel', side_effect=lambda *args: textos.append(args[2])):
            self.desenhar_rotulos()
        f = C.ficha(m, E._sessao[0])
        for prop, prefixo in (('largura', 'A1: '), ('altura', 'A2: '), ('profundidade', "A3 Depth: ")):
            self.assertIn(prefixo + addon.opcoes._texto_medida(f[prop] * 1000), textos)
        self.assertIn("Offset " + addon.opcoes._texto_medida(50), textos)
        profundidade = next(r for r in C._rotulos[0] if r[5] == 'profundidade')
        quina = Vector((300 + f['fim'] * 100, 200 + f['base'] * 100))
        self.assertGreater(profundidade[0], quina.x)
        self.assertGreater(profundidade[1] + profundidade[3] / 2, quina.y)
        for r in C._rotulos[0]:
            if r is profundidade:
                continue
            self.assertFalse(profundidade[0] < r[0] + r[2] and profundidade[0] + profundidade[2] > r[0]
                             and profundidade[1] < r[1] + r[3] and profundidade[1] + profundidade[3] > r[1])
        linhas = [Vector(p) for chamada in self.lotes_desenho for p in chamada.args[2]['pos']]
        self.assertTrue(any((p - quina).length < 1e-5 for p in linhas))

    def test_a3_tem_hit_test_e_edita_profundidade_preservando_espessuras(self):
        m = self.modulo(base=.3)
        self.iniciar(m)
        espessuras = {o.name: o.chapa_espessura_mm for o in m.children_recursive
                      if addon.chapas.MARCA_CHAPA in o}
        self.desenhar_rotulos()
        r = next(r for r in C._rotulos[0] if r[5] == 'profundidade')
        alvo = C.cota_sob(r[0] + r[2] / 2, r[1] + r[3] / 2)
        self.assertEqual(alvo[4:6], (m.name, 'profundidade'))
        resultado, avisos = self.confirmar_texto(m, alvo[5], '600')
        self.assertEqual(resultado, {'FINISHED'}, avisos)
        f = C.ficha(m, E._sessao[0])
        self.assertAlmostEqual(f['profundidade'], .6, places=5)
        self.assertAlmostEqual(f['afastamento'], 0, places=5)
        self.assertEqual({o.name: o.chapa_espessura_mm for o in m.children_recursive
                          if addon.chapas.MARCA_CHAPA in o}, espessuras)

    def test_indicadores_permanecem_dentro_da_area_livre_perto_das_bordas(self):
        m = self.modulo(base=.3)
        self.iniciar(m)
        livre = (20, 10, 340, 240)
        for origem in (Vector((160, -20)), Vector((370, -20))):
            with self.subTest(origem=tuple(origem)):
                self.desenhar_rotulos(lambda reg, rv, p: origem + Vector((p.x*100, p.z*100)), livre)
                dimensoes = [r for r in C._rotulos[0] if r[5] in ('largura', 'altura', 'profundidade')]
                self.assertEqual(len(dimensoes), 3)
                for r in dimensoes:
                    self.assertGreaterEqual(r[0], livre[0] - 1e-5)
                    self.assertGreaterEqual(r[1], livre[1] - 1e-5)
                    self.assertLessEqual(r[0] + r[2], livre[2] + 1e-5)
                    self.assertLessEqual(r[1] + r[3], livre[3] + 1e-5)

    def test_dimensoes_sempre_visiveis_e_distancias_somem_ao_editar(self):
        # User request v368: A1/A2/A3 also when selected; resize hides only distances.
        a, b, c = self.tres()
        rotulos = self.desenhar_rotulos()
        self.assertIn((a.name, 'afastamento'), rotulos)
        self.assertIn((a.name, 'vao_direito'), rotulos)
        self.assertTrue({'largura', 'altura', 'profundidade'} <= {p for _n, p in rotulos})
        self.assertEqual({n for n, _p in rotulos}, {a.name})
        with patch.object(C, 'modulo_em_edicao', return_value=a.name):
            self.assertEqual(self.desenhar_rotulos(), {(a.name, p) for p in ('largura', 'altura', 'profundidade')})
        for o in bpy.context.selected_objects:
            o.select_set(False)
        C.atualizar(bpy.context)
        self.assertEqual(self.desenhar_rotulos(), set())

    def test_guias_de_movimento_saem_do_meio_de_cada_face(self):
        # User drawing's blue lines: left/right at mid-height,
        # bottom/top at the cabinet's mid-width.
        a, b, c = self.tres()
        f = next(x for x in C._resumo[0]['itens'] if x['nome'] == a.name)
        self.desenhar_rotulos()
        rotulos = {r[5]: r for r in C._rotulos[0]}
        meio_x = 300 + (f['inicio'] + f['fim']) / 2 * 100
        meio_z = 200 + (f['base'] + f['altura'] / 2) * 100
        escala = bpy.context.preferences.system.ui_scale or 1.0
        for prop in ('vao_esquerdo', 'vao_direito'):
            r = rotulos[prop]
            self.assertAlmostEqual(r[1] + r[3] / 2, meio_z, places=3)
        # Text may exceed a short opening's width; its center still follows the real dimension.
        self.assertAlmostEqual(rotulos['vao_esquerdo'][0] + rotulos['vao_esquerdo'][2] / 2,
                               300 + (f['inicio'] - f['vao_esquerdo'] / 2) * 100, places=3)
        self.assertAlmostEqual(rotulos['vao_direito'][0] + rotulos['vao_direito'][2] / 2,
                               300 + (f['fim'] + f['vao_direito'] / 2) * 100, places=3)
        r = rotulos['cota_superior']
        self.assertAlmostEqual(r[0] + 5, meio_x + 4 * escala, places=3)
        self.assertGreater(r[1], 200 + (f['base'] + f['altura']) * 100)

    def test_digitacao_pela_bolinha_entra_no_numero_da_cota_verde(self):
        # User screenshot: the HUD box overlapped the "703.0 mm" label.
        a, b, c = self.tres()
        desenhados = []
        def projetar(regiao, rv, ponto):
            return Vector((300 + ponto.x * 100, 200 + ponto.z * 100))
        estado = dict(regiao=0, alvo=dict(objeto=a, pontos=[Vector((0, 0, 0)), Vector((0, 0, 1))]),
                      texto='750', cursor=3, selecionado=True)
        addon.hud._edicao_hud[0] = estado
        try:
            self.assertEqual(C.digitacao_hud(), ('altura', estado))
            with bpy.context.temp_override(area=self.area, region=self.regiao), \
                 patch.object(C, 'gpu'), patch.object(C, 'batch_for_shader'), \
                 patch.object(C, 'caixa_editavel', side_effect=lambda *x: desenhados.append(x[2:4])), \
                 patch.object(C, 'area_livre', return_value=(0, 0, 2000, 2000)), \
                 patch.object(C.view3d_utils, 'location_3d_to_region_2d', side_effect=projetar):
                C.desenhar(bpy.context)
        finally:
            addon.hud._edicao_hud[0] = None
        self.assertIn(('750 mm', estado), desenhados)
        self.assertEqual(len(desenhados), 3)        # A1/A2/A3 without an extra HUD box.
        altura = next(r for r in C._rotulos[0] if r[5] == 'altura')
        self.assertEqual(estado['caixas'], [(altura[0] + 5, altura[1] + 4,
                                             estado['caixas'][0][2], estado['caixas'][0][3])])

    def test_modulo_em_edicao_pelo_arraste_ou_pelo_ponto_da_face(self):
        a, b, c = self.tres()
        try:
            self.assertIsNone(C.modulo_em_edicao())
            addon.hud._edicao_hud[0] = dict(regiao=0, alvo=dict(objeto=a))
            self.assertEqual(C.modulo_em_edicao(), a.name)
            addon.hud_volume._estado[0] = dict(objeto=b.name)
            self.assertEqual(C.modulo_em_edicao(), b.name)
        finally:
            addon.hud._edicao_hud[0] = None
            addon.hud_volume._estado[0] = None

    def test_seta_da_cota_fica_inteira_dentro_da_area_livre(self):
        # User note: arrowheads were clipped at the boundary.
        livre = (40, 0, 800, 600)
        a, b = C.recortar_cota(Vector((-200, 100)), Vector((300, 100)), livre, 8)
        self.assertEqual((a.x, b.x, a.y), (48, 300, 100))
        a, b = C.recortar_cota(Vector((100, 500)), Vector((100, 900)), livre, 8)
        self.assertEqual((a.y, b.y), (500, 592))
        self.assertEqual(C.recortar_cota(Vector((-300, 1)), Vector((-100, 1)), livre, 8), (None, None))
        janela = SimpleNamespace(type='WINDOW', x=0, y=0, width=800, height=600, alignment='NONE')
        regioes = [janela,
                   SimpleNamespace(type='TOOLS', x=0, y=0, width=40, height=600, alignment='LEFT'),
                   SimpleNamespace(type='ASSET_SHELF', x=0, y=0, width=800, height=70, alignment='BOTTOM'),
                   SimpleNamespace(type='HEADER', x=0, y=600, width=800, height=26, alignment='TOP'),
                   SimpleNamespace(type='UI', x=799, y=0, width=1, height=600, alignment='RIGHT')]
        contexto = SimpleNamespace(region=janela, area=SimpleNamespace(regions=regioes))
        self.assertEqual(C.area_livre(contexto), (40, 70, 800, 600))

    def test_hud_na_parede_so_edita_a_geometria_no_plano(self):
        # Face points and corner arrows on the wall; depth is seen end-on,
        # and the corner belongs to snapping, shown by the v334 circle.
        a, b, c = self.tres()
        H = addon.hud
        normal = Vector(E._sessao[0]['normal'])
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            geometria = H._geometrias_hud(bpy.context)[0]
            self.assertEqual({l['letra'] for l in geometria['linhas']}, {'L', 'A'})
            for l in geometria['linhas']:
                self.assertLess(abs((l['pontos'][1] - l['pontos'][0]).normalized().dot(normal)), .5)
            controles = addon.hud_volume.controles(geometria)
            self.assertEqual(len(controles), 4)
            ponto = H._projetar_hud(bpy.context, controles[0]['pontos'][1])
            self.assertIsNotNone(ponto)
            self.assertTrue(H._acertar_hud(bpy.context, ponto).get('controle_face'))
            canto = H._projetar_hud(bpy.context, geometria['cantos'][0])
            self.assertIsNone(H._acertar_hud(bpy.context, canto))
            # No edge arrows, as requested: only the dot edits.
            linha = geometria['linhas'][0]
            quarto = H._projetar_hud(bpy.context, linha['pontos'][0].lerp(linha['pontos'][1], .25))
            self.assertIsNone(H._acertar_hud(bpy.context, quarto))
            desenhos = []
            with patch.object(H, 'gpu'), \
                 patch.object(H, 'batch_for_shader', side_effect=lambda s, tipo, d: desenhos.append(tipo)
                              or SimpleNamespace(draw=lambda shader: None)):
                H._desenhar_controles_volume(bpy.context, geometria, None)
            self.assertEqual(desenhos, ['TRIS'] * 8)    # Four filled dots with halos.
            C._quina_hover[0] = (a.name, (0.0, 0.0))
            try:
                self.assertIsNone(H._acertar_hud(bpy.context, ponto))
            finally:
                C._quina_hover[0] = None

    def test_clique_no_ponto_da_face_vai_para_a_hud_e_nao_move(self):
        self.tres()
        janela, area, regiao = E._janela_da_sessao()
        op = SimpleNamespace(sessao=E._sessao[0]['id'])
        evento = SimpleNamespace(type='LEFTMOUSE', value='PRESS', mouse_x=regiao.x + 5,
                                 mouse_y=regiao.y + 5, shift=False, ctrl=False, alt=False, oskey=False)
        with patch.object(E, 'navegacao_de_saida', return_value=False), \
             patch.object(E._hud, '_acertar_hud', return_value={'tipo': 'medida'}), \
             patch.object(E, 'modulo_para_mover') as mover:
            self.assertEqual(E.OBJECT_OT_observar_parede._modal(op, bpy.context, evento), {'PASS_THROUGH'})
        mover.assert_not_called()


addon.register()
resultado = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestComposicaoParedes))
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError("Wall-layout tests failed")
