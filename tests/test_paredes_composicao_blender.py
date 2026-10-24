"""Composicao existente: cotas, redistribuicao, substituicao e visual de elevacao."""
import os
import sys
import math
import tempfile
import unittest
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Vector, Quaternion

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

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
        m = bpy.data.meshes.new('Parede')
        bm.to_mesh(m)
        bm.free()
        self.parede = bpy.data.objects.new('Parede', m)
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

    def modulo(self, inicio=-1.4, base=0, largura=600, nome='Modulo', altura=720):
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
        superior = self.modulo(-1.4, base=1.7, nome='Superior')
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

    # Regressao (era BUG, corrigido na 302): o substituto ficava na raiz da
    # cena, fora do comodo do original e, por isso, fora do orcamento.
    def test_substituir_modelo_mantem_o_comodo(self):
        antigo = self.preparar_troca()
        self.assertEqual(addon.orcamento.definir_comodo(bpy.context.scene, [antigo], 'Cozinha'), 1)
        self.assertEqual(bpy.ops.object.cabinet_distribuir_parede(), {'FINISHED'})
        novo, = [o for o in bpy.data.objects if addon.chapas.MARCA_CONJUNTO in o]
        comodo = addon.orcamento._comodo_do_modulo(novo)
        self.assertIsNotNone(comodo)
        self.assertEqual(addon.orcamento._nome_comodo(comodo), 'Cozinha')

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
        parede = bpy.data.objects['Parede']
        self.assertEqual(parede.display_type, 'TEXTURED')
        self.assertNotIn(E.CHAVE_VISUAL, parede)
        for o in bpy.data.objects:
            if addon.chapas.MARCA_CONJUNTO in o:
                self.assertAlmostEqual(P.caixa_do_modulo(o)[1].x - P.caixa_do_modulo(o)[0].x, .6, places=4)
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        E.verificar()
        self.assertNotIn(E.CHAVE_VISUAL, bpy.data.objects['Parede'])

    def test_observador_passivo_nao_bloqueia_sincronizacao_nativa(self):
        from types import SimpleNamespace
        self.assertFalse(addon.eventos.modal_interativo(SimpleNamespace(bl_idname='OBJECT_OT_cabinet_observar_parede')))
        for nome in ('TRANSFORM_OT_translate', 'OBJECT_OT_cabinet_editar_cota_parede', 'TRANSFORM_OT_resize'):
            self.assertTrue(addon.eventos.modal_interativo(SimpleNamespace(bl_idname=nome)))

    def test_composicao_nao_sobrepoe_widgets_nas_larguras_suportadas(self):
        self.tres()
        for largura in (190, 320, 564):
            caixas = [w[:4] for w in addon.gaveta._widgets_gaveta(bpy.context, largura, 2400)]
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

    def test_livre_fixa_tem_um_unico_segmento_ativo_por_modulo(self):
        a, b, c = self.tres()
        C.fixar(bpy.context, b.name, True)
        widgets = addon.gaveta._widgets_gaveta(bpy.context, 480, 2400)
        escolhas = [w[5] for w in widgets if w[5] and w[5][:2] == ('escolha', C.CHAVE_FIXA)]
        for modulo in (a, b, c):
            linha = [a for a in escolhas if a[5] == modulo.name]
            self.assertEqual(len(linha), 2)
            self.assertEqual(sum(a[3] for a in linha), 1)
            self.assertTrue(all(a[4] for a in linha))

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
        escala = bpy.context.preferences.system.ui_scale
        self.assertIn(4 * escala, [c.args[0] for c in gpu.state.line_width_set.call_args_list])
        self.assertTrue(C._rotulos[0])


addon.register()
resultado = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestComposicaoParedes))
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de composicao de paredes')
