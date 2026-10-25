"""Vista de parede, isolamento nativo, distribuicao e rollback (sem biblioteca real)."""
import math
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import bpy
import bmesh
from mathutils import Vector, Quaternion

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

E = addon.paredes_edicao
P = addon.paredes


def caixa(nome, dimensoes, centro):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts:
        for i in range(3):
            v.co[i] *= dimensoes[i]
    malha = bpy.data.meshes.new(nome)
    bm.to_mesh(malha)
    bm.free()
    obj = bpy.data.objects.new(nome, malha)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = centro
    bpy.context.view_layer.update()
    return obj


class TestEdicaoParedes(unittest.TestCase):
    def setUp(self):
        addon.eventos._fim_do_desfazer()
        E.encerrar()
        E._ultima_face[0] = None
        P.esquecer()
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for col in list(bpy.data.collections):
            bpy.data.collections.remove(col)
        bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection
        self.area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        self.regiao = next(r for r in self.area.regions if r.type == 'WINDOW')
        self.area.spaces.active.region_3d.view_rotation = Quaternion((1, 0, 0), math.pi / 2)
        self.parede = caixa('Parede', (3, .15, 2.7), (0, 1.075, 1.35))
        self.extra = caixa('Outro objeto', (.2, .2, .2), (5, 0, 0))
        self.parede.select_set(True)
        bpy.context.view_layer.objects.active = self.parede
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        E.encerrar()
        self.tmp.cleanup()

    def iniciar(self):
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            erro = E.iniciar(bpy.context, self.parede)
        self.assertIsNone(erro)

    def modulo(self):
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.object.cabinet_criar_nicho()
        objetos = [o for o in bpy.context.scene.objects if addon.chapas.MARCA_CHAPA in o
                   and o.parent is None]
        for o in objetos:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objetos[0]
        bpy.ops.object.cabinet_agrupar()
        return next(o for o in bpy.context.selected_objects if addon.chapas.MARCA_CONJUNTO in o)

    def fixture(self, rotacao=0):
        modulo = self.modulo()
        modulo.rotation_euler.z = rotacao
        bpy.context.view_layer.update()
        colecao = next(c for c in modulo.users_collection if c.get('eh_colecao_modulo'))
        caminho = os.path.join(self.tmp.name, 'modelo.blend')
        bpy.data.libraries.write(caminho, {colecao})
        for obj in [modulo] + list(modulo.children_recursive):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(colecao)
        bpy.context.view_layer.update()
        return caminho

    def modelo(self):
        caminho = self.fixture()
        self.iniciar()
        self.assertIsNone(E.preparar_modelo(bpy.context, self.tmp.name, os.path.basename(caminho), 'modulo'))
        E._sessao[0]['escolhendo'] = False
        return E._sessao[0]

    def test_entrada_alinha_isola_sem_mudar_selecao(self):
        self.iniciar()
        espaco = self.area.spaces.active
        self.assertIsNotNone(espaco.local_view)
        self.assertTrue(E.esta_na_vista(self.parede, espaco, bpy.context))
        self.assertFalse(E.esta_na_vista(self.extra, espaco, bpy.context))
        self.assertTrue(self.parede.visible_get(viewport=espaco))
        self.assertFalse(self.extra.visible_get(viewport=espaco))
        self.assertEqual(bpy.context.object, self.parede)
        self.assertEqual(espaco.region_3d.view_perspective, 'ORTHO')
        self.assertGreater((espaco.region_3d.view_rotation @ Vector((0, 0, 1))).dot(Vector((0, -1, 0))), .999)

    def test_saida_revela_sem_revelar_ocultos_do_usuario(self):
        self.extra.hide_set(True)
        self.iniciar()
        E.encerrar()
        self.assertIsNone(self.area.spaces.active.local_view)
        self.assertTrue(self.extra.hide_get())
        self.assertFalse(self.parede.hide_get())
        self.assertIsNone(E._handler[0])

    def test_isolamento_anterior_e_restaurado(self):
        self.extra.select_set(True)
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            bpy.ops.view3d.localview(frame_selected=False)
        bpy.context.view_layer.update()
        antes = {o.name for o in bpy.context.scene.objects if E.esta_na_vista(o, self.area.spaces.active, bpy.context)}
        self.iniciar()
        E.encerrar()
        self.assertIsNotNone(self.area.spaces.active.local_view)
        bpy.context.view_layer.update()
        depois = {o.name for o in bpy.context.scene.objects if E.esta_na_vista(o, self.area.spaces.active, bpy.context)}
        self.assertEqual(antes, depois)
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            bpy.ops.view3d.localview(frame_selected=False)

    def test_girar_encerra_zoom_e_pan_permanecem(self):
        self.iniciar()
        rv = self.area.spaces.active.region_3d
        rv.view_distance *= .5
        rv.view_location.x += .3
        E.verificar()
        self.assertTrue(E.ativa())
        rv.view_rotation = Quaternion((0, 0, 1), .1) @ rv.view_rotation
        E.verificar()
        self.assertFalse(E.ativa())

    def test_parede_rotacionada_conserva_referencial(self):
        self.parede.rotation_euler.z = .6
        bpy.context.view_layer.update()
        self.iniciar()
        normal = Vector(E._sessao[0]['normal'])
        frente = self.area.spaces.active.region_3d.view_rotation @ Vector((0, 0, 1))
        self.assertGreater(frente.dot(normal), .99999)

    def test_face_clicada_tem_prioridade(self):
        E._ultima_face[0] = (self.parede.name, (0, .075, 0), (0, 1, 0), None)
        ponto, normal, regiao = E.face_do_objeto(bpy.context, self.parede)
        self.assertGreater(normal.y, .999)

    def test_duas_faces_do_mesmo_objeto_nao_misturam_modulos(self):
        modulo = self.modulo()
        P.colocar_na_parede(modulo, self.parede, Vector((0, 1.15, 0)), Vector((0, 1, 0)))
        P.associar(modulo, self.parede, Vector((0, 1.15, 0)), Vector((0, 1, 0)))
        self.assertFalse(E.associados(self.parede, Vector((0, 1, 0)), Vector((0, -1, 0)), bpy.context.scene.objects))

    def test_associados_e_descendentes_continuam_visiveis(self):
        modulo = self.modulo()
        costas, normal = Vector((0, 1, 0)), Vector((0, -1, 0))
        P.colocar_na_parede(modulo, self.parede, costas, normal)
        P.associar(modulo, self.parede, costas, normal)
        nomes = E._visiveis_da_face(bpy.context, self.parede, costas, normal)
        self.assertIn(modulo.name, nomes)
        self.assertTrue(all(o.name in nomes for o in modulo.children_recursive))

    def test_painel_aparece_para_malha_generica(self):
        itens = []
        E.widgets(bpy.context, itens, 12, 700, 400)
        self.assertIn('Paredes', [i[4] for i in itens])
        self.assertIn('object.cabinet_editar_parede', str(itens))

    def test_entrar_e_sair_da_parede_em_destaque_como_criar(self):
        # Pedido do usuario: o mesmo padrao do "Criar Prateleiras" (laranja,
        # 30 px, texto centrado); sair = laranja forte da etapa em andamento.
        import inspect
        G = addon.gaveta
        itens = []
        E.widgets(bpy.context, itens, 12, 700, 400)
        entrar = next(i for i in itens if i[5] == ('operador', 'object.cabinet_editar_parede'))
        self.assertEqual(entrar[3], 30)
        self.assertIn(entrar[5][1], G.OPERADORES_DESTAQUE)
        self.modelo()
        itens = []
        E.widgets(bpy.context, itens, 12, 2000, 400)
        sair = next(i for i in itens if i[5] == ('operador', 'object.cabinet_sair_parede'))
        self.assertEqual(sair[3], 30)
        self.assertEqual(sair[5][1], G.OPERADOR_DESTAQUE_ATIVO)
        self.assertIsInstance(G.OPERADORES_DESTAQUE, tuple)     # nunca hashear a acao
        fonte = inspect.getsource(addon.gaveta_desenho._desenhar_gaveta)
        self.assertIn('OPERADORES_DESTAQUE', fonte)
        self.assertIn('COR_CRIAR_PORTAS_ATIVO if acao[1] == _gaveta.OPERADOR_DESTAQUE_ATIVO', fonte)

    def test_menu_da_parede_sem_folgas_esquerda_direita_espacamento(self):
        # Print do usuario: "remover esses controladores do menu da parede".
        s = self.modelo()
        self.assertTrue(E.ativa(bpy.context))
        for modelo in (s['modelo'], None):
            s['modelo'] = modelo
            itens = []
            E.widgets(bpy.context, itens, 12, 2000, 400)
            nomes = {i[5][2] for i in itens if i[5] and i[5][:2] == ('medida', 'paredes')}
            self.assertFalse(nomes & {'esquerda', 'direita', 'espacamento'})
            self.assertFalse([i for i in itens if i[4].split(':')[0] in {'Esquerda', 'Direita', 'Espacamento'}])

    def test_modelo_e_inspecionado_sem_residuos(self):
        s = self.modelo()
        self.assertEqual(s['quantidade'], 1)
        self.assertGreater(s['altura'], 20)
        self.assertEqual({o.name for o in bpy.context.scene.objects
                          if addon.paredes_composicao.MARCA_OBJETO_GUIAS not in o},
                         {'Parede', 'Outro objeto'})
        self.assertFalse(any(addon.chapas.MARCA_CONJUNTO in o for o in bpy.data.objects))

    def test_distribuicao_desconta_folgas_e_espacamentos(self):
        s = self.modelo()
        s.update(quantidade=3, esquerda=50, direita=50, espacamento=20)
        plano = E.planejar(bpy.context)
        self.assertNotIn('erro', plano)
        self.assertAlmostEqual(plano['largura'], 2.86 / 3, places=6)
        self.assertAlmostEqual(plano['inicios'][0], -1.45, places=6)

    def test_falta_de_espaco_nao_cria_objetos(self):
        s = self.modelo()
        s.update(quantidade=100, esquerda=1400, direita=1400)
        antes = set(bpy.data.objects.keys())
        self.assertIsNotNone(E.criar_modulos(bpy.context))
        self.assertEqual(set(bpy.data.objects.keys()), antes)

    def test_confirmacao_cria_independentes_associados_e_preserva_espessura(self):
        s = self.modelo()
        s.update(quantidade=2, esquerda=50, direita=50)
        plano = E.planejar(bpy.context)
        self.assertEqual(bpy.ops.object.cabinet_distribuir_parede(), {'FINISHED'})
        modulos = [o for o in bpy.context.scene.objects if addon.chapas.MARCA_CONJUNTO in o]
        self.assertEqual(len(modulos), 2)
        malhas = [o.data for m in modulos for o in m.children_recursive if o.type == 'MESH']
        self.assertEqual(len(malhas), len(set(malhas)))
        for m in modulos:
            self.assertEqual(P.parede_do_modulo(m), self.parede)
            self.assertAlmostEqual(addon.modulos.medir_conjunto(m)[0], plano['largura'] * 1000, places=2)
            self.assertTrue(E.esta_na_vista(m, self.area.spaces.active, bpy.context))
            for o in m.children_recursive:
                if addon.chapas.MARCA_CHAPA in o:
                    self.assertAlmostEqual(o.chapa_espessura_mm, 18, places=3)

    def test_rollback_limpa_apenas_a_tentativa(self):
        s = self.modelo()
        s['quantidade'] = 2
        antes = E._dados_antes()
        uid_antes = self.parede.get(P.CHAVE_UID_PAREDE)
        original = addon.biblioteca.inserir_preset
        chamadas = []
        def falhar(*args, **kwargs):
            chamadas.append(1)
            if len(chamadas) == 2:
                raise ValueError('Falha simulada no segundo modulo')
            return original(*args, **kwargs)
        with patch.object(addon.biblioteca, 'inserir_preset', falhar):
            self.assertIn('Falha simulada', E.criar_modulos(bpy.context))
        self.assertEqual(antes, E._dados_antes())
        self.assertEqual(self.parede.get(P.CHAVE_UID_PAREDE), uid_antes)

    def test_apenas_obstaculos_com_sobreposicao_vertical(self):
        s = self.modelo()
        modulo = self.modulo()
        costas, n = Vector((0, 1, 1.8)), Vector((0, -1, 0))
        P.colocar_na_parede(modulo, self.parede, costas, n)
        P.associar(modulo, self.parede, costas, n)
        self.assertFalse(E.obstaculos(bpy.context, s, 0, .8, .5))
        self.assertTrue(E.obstaculos(bpy.context, s, 1.8, 2.6, .5))

    def test_contorno_com_abertura_recorta_faixa_so_na_altura_correspondente(self):
        contorno = []
        for pontos in (((0, 0, 0), (3, 0, 0), (3, 0, 3), (0, 0, 3)),
                       ((1, 0, 1), (2, 0, 1), (2, 0, 2), (1, 0, 2))):
            contorno += list(zip(pontos, pontos[1:] + pontos[:1]))
        regiao = {'retangulo': (0, 3, 0, 3), 'contorno': contorno}
        self.assertEqual(E.faixas_da_face(regiao, Vector((1, 0, 0)), 0, .9), [(0, 3)])
        self.assertEqual(E.faixas_da_face(regiao, Vector((1, 0, 0)), 0, 2.5), [(0, 1), (2, 3)])

    def test_retorno_de_parede_considera_profundidade(self):
        s = self.modelo()
        retorno = caixa('Retorno', (.15, 1, 2.7), (-1.425, .5, 1.35))
        plano = E.planejar(bpy.context)
        self.assertGreater(plano['faixa'][0], -1.36)
        self.assertLess(plano['faixa'][0], -1.34)

    def test_campos_e_quantidade_usam_o_mesmo_dono(self):
        self.modelo()
        self.assertIsNone(addon.gaveta_eventos.aplicar_medida(bpy.context, 'paredes', '', 'esquerda', .025))
        self.assertIsNone(addon.gaveta_eventos._aplicar_contador(bpy.context,
                         ('contador', E.ALVO_QUANTIDADE, 1, 1, 100, '', 'Quantidade'), 3))
        self.assertEqual(E._sessao[0]['esquerda'], 25)
        self.assertEqual(E._sessao[0]['quantidade'], 3)

    def test_trocar_modelo_substitui_previa_sem_criar_modulos(self):
        s = self.modelo()
        arquivo = s['modelo']['arquivo']
        self.assertIsNone(E.preparar_modelo(bpy.context, self.tmp.name, arquivo, 'modulo'))
        self.assertFalse(any(addon.chapas.MARCA_CONJUNTO in o for o in bpy.data.objects))

    def test_parametros_invalidos_nao_entram_na_previa(self):
        self.modelo()
        self.assertIsNotNone(E.editar_parametro('quantidade', 0))
        self.assertIsNotNone(E.editar_parametro('altura', float('nan')))
        self.assertIsNotNone(E.editar_parametro('esquerda', -1))

    def test_cancelamento_e_operadores_de_entrada(self):
        # Contratos registrados: ambas entradas compartilham o mesmo operador.
        self.assertTrue(hasattr(bpy.types, 'VIEW3D_MT_parede_cabinet'))
        self.assertIn(E.OBJECT_OT_editar_parede, addon.CLASSES)
        self.assertIn(E.OBJECT_OT_observar_parede, addon.CLASSES)
        self.modelo()
        self.assertEqual(bpy.ops.object.cabinet_escolher_vao_parede(), {'FINISHED'})
        self.assertEqual(bpy.ops.object.cabinet_cancelar_previa_parede(), {'FINISHED'})
        self.assertIsNone(E._sessao[0]['modelo'])
        self.assertEqual(bpy.ops.object.cabinet_sair_parede(), {'FINISHED'})

    def test_invalidacao_antes_do_undo_remove_sessao_e_handler(self):
        self.iniciar()
        addon.eventos._antes_de_desfazer()
        self.assertFalse(E.ativa())
        self.assertIsNone(E._handler[0])
        addon.eventos._desfazendo[0] = False

    def test_obstaculo_estreito_entre_as_amostras_nao_e_ignorado(self):
        s = self.modelo()
        caixa('Retorno estreito', (.15, .02, .04), (-1.425, .90, .17))
        plano = E.planejar(bpy.context)
        self.assertAlmostEqual(plano['faixa'][0], -1.35, places=5)

    def test_menu_ativo_sem_sobreposicao_em_todas_as_larguras(self):
        self.modelo()
        for largura in (190, 320, 564):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 2300)
            caixas = [v[:4] for v in widgets]
            for i, (ax, ay, aw, ah) in enumerate(caixas):
                for bx, by, bw, bh in caixas[i + 1:]:
                    self.assertFalse(ax < bx + bw - .01 and bx < ax + aw - .01
                         and ay < by + bh - .01 and by < ay + ah - .01,
                         (largura, (ax, ay, aw, ah), (bx, by, bw, bh)))

    def test_navegacao_respeita_operadores_nativos_e_remapeamento(self):
        evento = SimpleNamespace(value='PRESS')
        def contexto(operador):
            km = SimpleNamespace(keymap_items=SimpleNamespace(match_event=lambda e: SimpleNamespace(idname=operador)))
            return SimpleNamespace(window_manager=SimpleNamespace(keyconfigs=SimpleNamespace(user=SimpleNamespace(keymaps={'3D View': km}))))
        for operador in ('view3d.walk', 'view3d.fly', 'view3d.rotate', 'view3d.view_axis'):
            self.assertTrue(E.navegacao_de_saida(contexto(operador), evento))
        for operador in ('view3d.zoom', 'view3d.move', 'view3d.view_pan'):
            self.assertFalse(E.navegacao_de_saida(contexto(operador), evento))

    def test_modelo_invalido_preserva_modelo_preparado(self):
        s = self.modelo()
        antes = E._dados_antes()
        modelo = dict(s['modelo'])
        self.assertIsNotNone(E.preparar_modelo(bpy.context, self.tmp.name, 'ausente.blend', 'modulo'))
        self.assertEqual(s['modelo'], modelo)
        self.assertEqual(E._dados_antes(), antes)

    def test_salvar_encerra_isolamento_temporario(self):
        self.iniciar()
        caminho = os.path.join(self.tmp.name, 'teste.blend')
        bpy.ops.wm.save_as_mainfile(filepath=caminho)
        self.assertFalse(E.ativa())
        self.assertIsNone(self.area.spaces.active.local_view)

    def test_undo_redo_restaura_lote_sem_sessao_pendente(self):
        self.modelo()
        E._sessao[0]['quantidade'] = 2
        bpy.ops.ed.undo_push(message='Antes de distribuir na parede')
        self.assertEqual(bpy.ops.object.cabinet_distribuir_parede(), {'FINISHED'})
        bpy.ops.ed.undo_push(message='Distribuicao na parede concluida')
        bpy.ops.ed.undo()
        addon.eventos._fim_do_desfazer()
        self.assertFalse(E.ativa())
        self.assertFalse(any(addon.chapas.MARCA_CONJUNTO in o for o in bpy.data.objects))
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        self.assertEqual(sum(addon.chapas.MARCA_CONJUNTO in o for o in bpy.context.scene.objects), 2)

    def test_face_inclinada_nao_e_achatada_para_vertical(self):
        self.parede.rotation_euler.x = .1
        bpy.context.view_layer.update()
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            self.assertIsNotNone(E.iniciar(bpy.context, self.parede))
        self.assertFalse(E.ativa())

    def test_apagar_parede_encerra_a_sessao(self):
        self.iniciar()
        bpy.data.objects.remove(self.parede, do_unlink=True)
        E.verificar()
        self.assertFalse(E.ativa())

    def test_callbacks_de_desenho_nao_calculam_obstaculos(self):
        import inspect
        self.assertNotIn('planejar(', inspect.getsource(E.desenhar))
        self.assertNotIn('planejar(', inspect.getsource(E.widgets))

    def test_confirmacao_exige_escolha_do_vao(self):
        s = self.modelo()
        s['escolhendo'] = True
        antes = E._dados_antes()
        self.assertIn('Clique no vao', E.criar_modulos(bpy.context))
        self.assertEqual(antes, E._dados_antes())

    def test_contexto_direito_nao_reutiliza_parede_de_outro_clique(self):
        E._ultima_face[0] = ('Parede', (0, 0, 0), (0, -1, 0), 0)
        with patch.object(addon.hud, '_raio_cru', return_value=None):
            E.lembrar_face(bpy.context, (0, 0), contexto=True)
        self.assertEqual(E._alvo_contexto[0], '')

    def test_enquadramento_usa_projecao_nativa_sem_alterar_o_zoom_posterior(self):
        self.iniciar()
        s = E._sessao[0]
        s['enquadrando'] = True
        from unittest.mock import Mock
        contexto = SimpleNamespace(region=SimpleNamespace(width=1000, height=1000),
                    region_data=SimpleNamespace(view_distance=2), area=Mock())
        pontos = [Vector((0, 0)), Vector((0, 1600)), Vector((800, 0)), Vector((800, 1600))]
        with patch.object(E.view3d_utils, 'location_3d_to_region_2d', side_effect=pontos):
            E._enquadrar(contexto, s)
        self.assertAlmostEqual(contexto.region_data.view_distance, 4)

    def test_contorno_editado_sem_novos_vertices_e_relido_na_entrada(self):
        face = E.face_do_objeto(bpy.context, self.parede)
        for v in self.parede.data.vertices:
            v.co.x *= 1.5
        self.parede.data.update()
        bpy.context.view_layer.update()
        depois = E.face_do_objeto(bpy.context, self.parede)
        self.assertAlmostEqual(depois[2]['retangulo'][1] - depois[2]['retangulo'][0], 4.5)

    def test_troca_de_cena_encerra_sem_ocultar_a_nova_cena(self):
        self.iniciar()
        anterior = bpy.context.scene
        outra = bpy.data.scenes.new('Outra cena')
        try:
            bpy.context.window.scene = outra
            E.verificar()
            self.assertFalse(E.ativa())
            self.assertIsNone(self.area.spaces.active.local_view)
        finally:
            bpy.context.window.scene = anterior
            bpy.data.scenes.remove(outra)

    def test_observador_de_mouse_nao_recalcula_geometria(self):
        self.modelo()
        with patch.object(E, 'planejar', side_effect=AssertionError('Consulta no gesto')):
            E.verificar(atualizar_previa=False)
        self.assertTrue(E.ativa())

    # Regressao (era BUG, corrigido na 298): o modo 2D deixava a orbita em ORTHO.
    def test_orbita_volta_a_perspectiva_sem_desfazer_o_gesto(self):
        self.area.spaces.active.region_3d.view_perspective = 'PERSP'
        self.iniciar()
        rv = self.area.spaces.active.region_3d
        rv.view_rotation = Quaternion((0, 0, 1), .2) @ rv.view_rotation
        rotacao = rv.view_rotation.copy()
        E.verificar()
        self.assertFalse(E.ativa())
        self.assertEqual(rv.view_perspective, 'PERSP')
        self.assertGreater(abs(rv.view_rotation.dot(rotacao)), .99999)

    def test_saida_manual_restaura_projecao_anterior(self):
        for projecao in ('PERSP', 'ORTHO'):
            self.area.spaces.active.region_3d.view_perspective = projecao
            self.iniciar()
            E.encerrar()
            self.assertEqual(self.area.spaces.active.region_3d.view_perspective, projecao)

    def test_parede_solida_e_contorno_preto_temporarios(self):
        espaco = self.area.spaces.active
        espaco.shading.object_outline_color = (.3, .4, .5)
        antes = tuple(espaco.shading.object_outline_color)
        self.parede.display_type = 'WIRE'
        self.iniciar()
        self.assertEqual(self.parede.display_type, 'SOLID')
        self.assertTrue(espaco.shading.show_object_outline)
        self.assertEqual(tuple(espaco.shading.object_outline_color), (0, 0, 0))
        E.encerrar()
        self.assertEqual(tuple(espaco.shading.object_outline_color), antes)
        self.assertEqual(self.parede.display_type, 'WIRE')

    def inserir_imediato(self, caminho):
        antes = set(bpy.data.objects)
        with patch.object(addon.modulos, 'redimensionar_conjunto', side_effect=AssertionError('Resize indevido')):
            self.assertIsNone(E.inserir_modelo(bpy.context, self.tmp.name, os.path.basename(caminho), 'modulo'))
        return next(o for o in set(bpy.data.objects) - antes if addon.chapas.MARCA_CONJUNTO in o)

    def test_duplo_clique_mantem_tamanho_e_encadeia_pela_direita(self):
        caminho = self.fixture()
        self.iniciar()
        a = self.inserir_imediato(caminho)
        ficha_a = addon.paredes_composicao.ficha(a, E._sessao[0])
        b = self.inserir_imediato(caminho)
        ficha_b = addon.paredes_composicao.ficha(b, E._sessao[0])
        self.assertAlmostEqual(ficha_a['inicio'] + ficha_a['largura'] / 2, 0, places=5)
        self.assertAlmostEqual(ficha_a['largura'], ficha_b['largura'], places=5)
        self.assertAlmostEqual(ficha_a['fim'], ficha_b['inicio'], places=5)
        self.assertLess(ficha_b['largura'], 1)
        self.assertTrue(E.esta_na_vista(b, self.area.spaces.active, bpy.context))

    def test_fim_da_parede_volta_ao_centro_sem_encolher(self):
        caminho = self.fixture()
        self.iniciar()
        a = self.inserir_imediato(caminho)
        self.assertIsNone(E.posicionar_modelo(bpy.context, a, Vector((1.4, 1, .8))))
        b = self.inserir_imediato(caminho)
        f = addon.paredes_composicao.ficha(b, E._sessao[0])
        self.assertAlmostEqual(f['inicio'] + f['largura'] / 2, 0, places=5)
        self.assertAlmostEqual(f['largura'], addon.paredes_composicao.ficha(a, E._sessao[0])['largura'], places=5)

    def test_soltar_modelo_posiciona_no_ponto_sem_alterar_vertices(self):
        modulo = self.modulo()
        self.iniciar()
        malhas = {o.name: (o.data.as_pointer(), tuple(tuple(v.co) for v in o.data.vertices))
                   for o in modulo.children_recursive if o.type == 'MESH'}
        with patch.object(addon.modulos, 'redimensionar_conjunto', side_effect=AssertionError('Resize indevido')):
            self.assertIsNone(E.posicionar_modelo(bpy.context, modulo, Vector((-.7, 1, 1.2))))
        f = addon.paredes_composicao.ficha(modulo, E._sessao[0])
        self.assertAlmostEqual(f['inicio'] + f['largura'] / 2, -.7, places=5)
        self.assertAlmostEqual(f['base'] + f['altura'] / 2, 1.2, places=5)
        self.assertEqual(malhas, {o.name: (o.data.as_pointer(), tuple(tuple(v.co) for v in o.data.vertices))
                         for o in modulo.children_recursive if o.type == 'MESH'})
        self.assertEqual(P.parede_do_modulo(modulo), self.parede)
        self.assertEqual(E._sessao[0]['ultimo_modulo'], modulo.name)

    def test_inserir_modelo_muito_grande_falha_sem_residuos(self):
        caminho = self.fixture()
        for v in self.parede.data.vertices:
            v.co.x *= .1
        self.parede.data.update()
        bpy.context.view_layer.update()
        self.iniciar()
        antes = E._dados_antes()
        self.assertIn('tamanho original', E.inserir_modelo(bpy.context, self.tmp.name, os.path.basename(caminho), 'modulo'))
        self.assertEqual(E._dados_antes(), antes)

    def test_insercao_pelo_operador_nao_prepara_distribuicao_automatica(self):
        caminho = self.fixture()
        self.iniciar()
        with patch.object(E, 'preparar_modelo', side_effect=AssertionError('Preenchimento indevido')):
            self.assertEqual(bpy.ops.object.cabinet_inserir_preset(pasta=self.tmp.name,
                arquivo=os.path.basename(caminho), tipo='modulo'), {'FINISHED'})
        self.assertIsNone(E._sessao[0]['modelo'])

    def test_ultimo_na_face_oposta_nao_define_o_proximo(self):
        modulo = self.modulo()
        self.iniciar()
        n = Vector((0, 1, 0))
        P.colocar_na_parede(modulo, self.parede, Vector((0, 1.15, 0)), n)
        P.associar(modulo, self.parede, Vector((0, 1.15, 0)), n)
        E.registrar_posicionado(bpy.context, modulo)
        self.assertEqual(E._sessao[0]['ultimo_modulo'], '')

    def arraste_de_teste(self, caminho):
        from types import MethodType
        op = SimpleNamespace(pasta=self.tmp.name, arquivo=os.path.basename(caminho),
                             tipo='modulo', report=lambda *args: None)
        for nome in dir(addon.biblioteca.OBJECT_OT_arrastar_preset):
            metodo = getattr(addon.biblioteca.OBJECT_OT_arrastar_preset, nome)
            if callable(metodo) and not nome.startswith('__'):
                setattr(op, nome, MethodType(metodo, op))
        # Apenas o registro no event loop e' substituido; append, preview,
        # cancelamento e associacao usam seus contratos reais do Blender.
        class ContextoDoArraste:
            window_manager = SimpleNamespace(modal_handler_add=lambda op: None,
                                             event_timer_add=lambda *a, **k: object(),
                                             event_timer_remove=lambda tique: None)
            def __getattr__(self, nome):
                return getattr(bpy.context, nome)
        contexto = ContextoDoArraste()
        evento = SimpleNamespace(mouse_x=-100, mouse_y=-100)
        self.assertEqual(op.invoke(contexto, evento), {'RUNNING_MODAL'})
        return op

    def test_arraste_com_caixa_no_indice_so_carrega_ao_soltar(self):
        # Pedido do usuario (cena real travava): com a caixa gravada no
        # indice o arraste e' so' o wireframe; o .blend carrega ao soltar,
        # depois do aviso "Carregando...".
        B = addon.biblioteca
        caminho = self.fixture(math.pi / 2)
        arquivo = os.path.basename(caminho)
        B.registrar_no_indice(self.tmp.name, 'Modelo', caminho, 'A', 'B', 'C', 'modulo')
        self.assertIsNone(B.caixa_do_preset(self.tmp.name, arquivo))
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            op = self.arraste_de_teste(caminho)      # 1o: carrega e grava a caixa
            op._cancelar(bpy.context)
        registro = B.caixa_do_preset(self.tmp.name, arquivo)
        self.assertIsNotNone(registro)
        self.assertIn('modulo', registro)
        # o lado das costas vai no registro: a previa nao tem a porta
        self.assertEqual(registro['modulo']['costas'], 'POS_Y')
        antigo = dict(registro, modulo={k: v for k, v in registro['modulo'].items()
                                        if k != 'costas'})
        B._atualizar_item(self.tmp.name, arquivo, {B.CHAVE_CAIXA: antigo})
        self.assertIsNone(B.caixa_do_preset(self.tmp.name, arquivo))   # mede de novo
        B._atualizar_item(self.tmp.name, arquivo, {B.CHAVE_CAIXA: registro})
        acerto = P.raio_ate_parede(bpy.context, (-.4, -3, 1.2), (0, 1, 0), set())
        objetos = len(bpy.data.objects)
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            op = self.arraste_de_teste(caminho)
            self.assertIsNotNone(op._previa)
            self.assertEqual(len(bpy.data.objects), objetos)    # nada carregado
            op._arrastando, op._moveu = True, True
            evento = SimpleNamespace(type='LEFTMOUSE', value='RELEASE',
                      mouse_x=self.regiao.x + 300, mouse_y=self.regiao.y + 300)
            with patch.object(P, 'raio_ate_parede', return_value=acerto),                     patch.object(P, '_px_por_metro', return_value=None):
                op._mover(bpy.context, evento)
            self.assertTrue(op._valido)
            self.assertEqual(op.modal(bpy.context, evento), {'RUNNING_MODAL'})
            self.assertTrue(op._carregando)
            self.assertEqual(len(bpy.data.objects), objetos)    # so' o aviso
            evento.type, evento.value = 'MOUSEMOVE', 'NOTHING'
            self.assertEqual(op.modal(bpy.context, evento), {'RUNNING_MODAL'})
            evento.type = 'TIMER'
            self.assertEqual(op.modal(bpy.context, evento), {'FINISHED'})
        self.assertIsNone(op._handler_aviso)
        modulo = bpy.context.object     # o operador terminado ja' soltou os dados
        self.assertEqual(P.parede_do_modulo(modulo), self.parede)
        bpy.context.view_layer.update()
        lo, hi = P.caixa_do_modulo(modulo)
        pontos = [modulo.matrix_world @ Vector((x, y, z)) for x in (lo.x, hi.x)
                  for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
        self.assertAlmostEqual(max(p.y for p in pontos), 1.0, places=4)
        self.assertAlmostEqual((min(p.x for p in pontos) + max(p.x for p in pontos)) / 2, -.4, places=4)
        self.assertAlmostEqual((min(p.z for p in pontos) + max(p.z for p in pontos)) / 2, 1.2, places=4)
        # Duplo clique na foto (cursor 3D) tambem so' carrega no tique.
        cursor = bpy.context.scene.cursor
        cursor.location = (1.0, -2.0, .5)
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            op = self.arraste_de_teste(caminho)
            self.assertEqual(op._no_cursor(bpy.context), {'RUNNING_MODAL'})
            self.assertEqual(op._carregar(bpy.context), {'FINISHED'})
        lo, hi = B.medir_caixa(bpy.context, op._novos, op._raizes)
        for real, esperado in zip(((lo + hi) / 2).xy[:] + (lo.z,), (1.0, -2.0, .5)):
            self.assertAlmostEqual(real, esperado, places=4)
        cursor.location = (0, 0, 0)
        # .blend alterado (outro tamanho): a caixa gravada deixa de valer.
        with open(caminho, 'ab') as f:
            f.write(b'0')
        self.assertIsNone(B.caixa_do_preset(self.tmp.name, arquivo))

    def test_arraste_da_biblioteca_fora_da_edicao_encosta_as_costas_na_parede(self):
        # Relato do usuario: solto na parede, o armario ficava de pe' pela
        # base no ponto do raio e de lado. Fora da edicao 2D ele gira as
        # costas para a parede, centra no cursor e associa.
        caminho = self.fixture(math.pi / 2)
        acerto = P.raio_ate_parede(bpy.context, (-.4, -3, 1.2), (0, 1, 0), set())
        self.assertEqual(acerto[0], self.parede)
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            op = self.arraste_de_teste(caminho)
            op._arrastando, op._moveu = True, True
            evento = SimpleNamespace(type='LEFTMOUSE', value='RELEASE',
                      mouse_x=self.regiao.x + 300, mouse_y=self.regiao.y + 300)
            modulo = op._raizes[0]
            with patch.object(P, 'raio_ate_parede', return_value=acerto),                     patch.object(P, '_px_por_metro', return_value=None):
                op._mover(bpy.context, evento)
            self.assertTrue(op._valido)
            # costas (+Y) contra a parede, frente (-Y) para fora
            costas = modulo.matrix_world.to_3x3() @ Vector((0, 1, 0))
            self.assertGreater(costas.dot(Vector((0, 1, 0))), .999)
            # fora da parede o preset volta a' rotacao original
            with patch.object(P, 'raio_ate_parede', return_value=None):
                op._mover(bpy.context, evento)
            self.assertIsNone(op._na_parede)
            self.assertAlmostEqual(modulo.matrix_world.to_euler().z, math.pi / 2, places=4)
            with patch.object(P, 'raio_ate_parede', return_value=acerto),                     patch.object(P, '_px_por_metro', return_value=None):
                op._mover(bpy.context, evento)
            self.assertEqual(op.modal(bpy.context, evento), {'FINISHED'})
        self.assertEqual(P.parede_do_modulo(modulo), self.parede)
        lo, hi = P.caixa_do_modulo(modulo)
        bpy.context.view_layer.update()
        pontos = [modulo.matrix_world @ Vector((x, y, z)) for x in (lo.x, hi.x)
                  for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
        self.assertAlmostEqual(max(p.y for p in pontos), 1.0, places=4)
        self.assertAlmostEqual((min(p.x for p in pontos) + max(p.x for p in pontos)) / 2, -.4, places=4)
        # o cursor e' o centro do modulo, nao a base
        self.assertAlmostEqual((min(p.z for p in pontos) + max(p.z for p in pontos)) / 2, 1.2, places=4)

    def test_roda_no_arraste_da_biblioteca_troca_a_face_da_parede(self):
        # Pedido do usuario: rodar o scroll muda a face de referencia.
        caminho = self.fixture()
        acerto = P.raio_ate_parede(bpy.context, (-.4, -3, 1.2), (0, 1, 0), set())
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            op = self.arraste_de_teste(caminho)
            op._arrastando, op._moveu = True, True
            evento = SimpleNamespace(type='WHEELUPMOUSE', value='PRESS',
                      mouse_x=self.regiao.x + 300, mouse_y=self.regiao.y + 300)
            modulo = op._raizes[0]
            with patch.object(P, 'raio_ate_parede', return_value=acerto), \
                    patch.object(P, '_px_por_metro', return_value=None):
                op._mover(bpy.context, evento)
                self.assertEqual(op.modal(bpy.context, evento), {'RUNNING_MODAL'})
                self.assertTrue(op._valido)
                # +X do modulo contra a parede (+Y do mundo)
                self.assertGreater((modulo.matrix_world.to_3x3() @ Vector((1, 0, 0)))
                                   .dot(Vector((0, 1, 0))), .999)
                evento.type, evento.value = 'LEFTMOUSE', 'RELEASE'
                self.assertEqual(op.modal(bpy.context, evento), {'FINISHED'})
        self.assertEqual(modulo[P.CHAVE_COSTAS], 'POS_X')
        bpy.context.view_layer.update()
        self.assertAlmostEqual(P.ponto_das_costas(modulo).y, 1.0, places=4)
        self.assertFalse(P.manter_nas_paredes())

    def test_arraste_da_biblioteca_soltar_usa_coordenada_final_e_tamanho_original(self):
        caminho = self.fixture()
        self.iniciar()
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            op = self.arraste_de_teste(caminho)
            op._arrastando, op._moveu = True, True
            evento = SimpleNamespace(type='LEFTMOUSE', value='RELEASE',
                      mouse_x=self.regiao.x + 300, mouse_y=self.regiao.y + 300)
            with patch.object(E, 'ponto_no_evento', return_value=Vector((-.6, 1, 1.1))):
                self.assertEqual(op.modal(bpy.context, evento), {'FINISHED'})
        modulo = bpy.context.object
        f = addon.paredes_composicao.ficha(modulo, E._sessao[0])
        self.assertAlmostEqual(f['inicio'] + f['largura'] / 2, -.6, places=5)
        self.assertAlmostEqual(f['base'] + f['altura'] / 2, 1.1, places=5)
        self.assertLess(f['largura'], 1)
        self.assertTrue(modulo.visible_get(viewport=self.area.spaces.active))
        self.assertIsNone(op._novos)

    def test_duplo_clique_no_posicionador_da_biblioteca_confirma_sem_mirar(self):
        caminho = self.fixture()
        self.iniciar()
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            op = self.arraste_de_teste(caminho)
            evento = SimpleNamespace(type='LEFTMOUSE', value='PRESS', mouse_x=-100, mouse_y=-100)
            self.assertEqual(op.modal(bpy.context, evento), {'FINISHED'})
        f = addon.paredes_composicao.ficha(bpy.context.object, E._sessao[0])
        self.assertAlmostEqual(f['inicio'] + f['largura'] / 2, 0, places=5)
        self.assertIsNone(E._sessao[0]['modelo'])

    def test_cancelar_arraste_e_sair_do_modo_limpa_staging(self):
        caminho = self.fixture()
        self.iniciar()
        antes = E._dados_antes()
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            op = self.arraste_de_teste(caminho)
            E.encerrar()
            evento = SimpleNamespace(type='MOUSEMOVE', value='NOTHING', mouse_x=-100, mouse_y=-100)
            self.assertEqual(op.modal(bpy.context, evento), {'CANCELLED'})
        # Dados anexados e materiais auxiliares sao do appender; os objetos
        # e pastas da tentativa devem sair, os anteriores devem permanecer.
        # As guias sao da sessao: saem com ela, como a previa.
        self.assertEqual(set(bpy.data.objects.keys()), antes['objects'] - {'Guias da parede'})
        self.assertEqual(set(bpy.data.collections.keys()), antes['collections'])

    def test_raycast_do_posicionador_consulta_a_face_real_da_parede(self):
        self.iniciar()
        evento = SimpleNamespace(mouse_x=self.regiao.x + 300, mouse_y=self.regiao.y + 300)
        with patch.object(E.view3d_utils, 'region_2d_to_origin_3d', return_value=Vector((.4, -5, 1.3))), \
             patch.object(E.view3d_utils, 'region_2d_to_vector_3d', return_value=Vector((0, 1, 0))):
            ponto = E.ponto_no_evento(bpy.context, evento)
        self.assertIsNotNone(ponto)
        self.assertLess((ponto - Vector((.4, 1, 1.3))).length, .00001)

    def test_previa_repetida_em_parede_girada_confere_com_objeto_confirmado(self):
        caminho = self.fixture()
        self.parede.rotation_euler.z = .6
        bpy.context.view_layer.update()
        self.iniciar()
        s = E._sessao[0]
        u, plano = Vector(s['u']), Vector(s['ponto'])
        centro_parede = sum(s['regiao']['retangulo'][:2]) / 2
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            op = self.arraste_de_teste(caminho)
            malhas = {o.name: tuple(tuple(v.co) for v in o.data.vertices)
                       for o in op._novos if o.type == 'MESH'}
            op._arrastando, op._moveu = True, True
            evento = SimpleNamespace(type='MOUSEMOVE', value='NOTHING',
                      mouse_x=self.regiao.x + 300, mouse_y=self.regiao.y + 300)
            for deslocamento in (-.7, .2, -.4):
                x = centro_parede + deslocamento
                ponto = plano + u * (x - plano.dot(u))
                ponto.z = 1.2
                with patch.object(E, 'ponto_no_evento', return_value=ponto):
                    self.assertEqual(op.modal(bpy.context, evento), {'RUNNING_MODAL'})
                self.assertTrue(op._valido)
                centro = sum(op._bbox_atual, Vector()) / 8
                self.assertAlmostEqual(centro.dot(u), x, places=5)
            evento.type, evento.value = 'LEFTMOUSE', 'RELEASE'
            with patch.object(E, 'ponto_no_evento', return_value=ponto):
                self.assertEqual(op.modal(bpy.context, evento), {'FINISHED'})
        f = addon.paredes_composicao.ficha(bpy.context.object, s)
        self.assertAlmostEqual(f['inicio'] + f['largura'] / 2, centro_parede - .4, places=5)
        self.assertAlmostEqual(f['base'] + f['altura'] / 2, 1.2, places=5)
        self.assertEqual(malhas, {nome: tuple(tuple(v.co) for v in bpy.data.objects[nome].data.vertices) for nome in malhas})

    def test_arraste_direito_no_modulo_preserva_tamanho_e_define_o_ultimo(self):
        from types import MethodType
        modulo = self.modulo()
        self.iniciar()
        medidas = addon.modulos.medir_conjunto(modulo)
        op = SimpleNamespace(_modulo=modulo.name, _parede=self.parede.name,
             _arrastou=True, _regiao=self.regiao, _rv3d=self.area.spaces.active.region_3d,
             _caixa=P.caixa_do_modulo(modulo), _matriz=modulo.matrix_world.copy(),
             _ignorar={modulo.name, *(o.name for o in modulo.children_recursive)},
             _associacao={}, report=lambda *args: None)
        for nome in ('modal', '_mover', '_encerrar', '_status', '_restaurar'):
            setattr(op, nome, MethodType(getattr(P.OBJECT_OT_arrastar_na_parede, nome), op))
        evento = SimpleNamespace(type='RIGHTMOUSE', value='RELEASE', mouse_region_x=300, mouse_region_y=300)
        acerto = (self.parede, Vector((.4, 1, 1)), Vector((0, -1, 0)), E._sessao[0]['face'])
        with bpy.context.temp_override(area=self.area, region=self.regiao), \
             patch.object(P, '_raio_ignorando', return_value=acerto):
            self.assertEqual(op.modal(bpy.context, evento), {'FINISHED'})
        f = addon.paredes_composicao.ficha(modulo, E._sessao[0])
        self.assertAlmostEqual(f['inicio'] + f['largura'] / 2, .4, places=5)
        self.assertEqual(E._sessao[0]['ultimo_modulo'], modulo.name)
        for antes, depois in zip(medidas, addon.modulos.medir_conjunto(modulo)):
            self.assertAlmostEqual(antes, depois, places=3)

    def test_insercao_sobre_outro_modulo_encosta_no_vao_livre(self):
        caminho = self.fixture()
        self.iniciar()
        a = self.inserir_imediato(caminho)
        b = self.inserir_imediato(caminho)
        self.assertIsNone(E.posicionar_modelo(bpy.context, b, Vector((0, 1, .2))))
        fa, fb = (addon.paredes_composicao.ficha(o, E._sessao[0]) for o in (a, b))
        self.assertTrue(fb['fim'] <= fa['inicio'] + .00005 or fb['inicio'] >= fa['fim'] - .00005)
        self.assertAlmostEqual(fb['base'], 0, places=5)

    def test_parede_cheia_recusa_insercao_sem_residuos(self):
        caminho = self.fixture()
        self.iniciar()
        for i in range(5):
            self.inserir_imediato(caminho)
        antes = E._dados_antes()
        selecao = {o.name for o in bpy.context.selected_objects}
        self.assertIn('vao livre', E.inserir_modelo(bpy.context, self.tmp.name,
                                                   os.path.basename(caminho), 'modulo'))
        self.assertEqual(E._dados_antes(), antes)
        self.assertEqual({o.name for o in bpy.context.selected_objects}, selecao)

    def test_alvo_muito_alem_da_quina_limita_todo_o_volume(self):
        modulo = self.modulo()
        self.iniciar()
        s = E._sessao[0]
        for x, z in ((100, 100), (-100, -100)):
            self.assertIsNone(E.posicionar_modelo(bpy.context, modulo, Vector((x, 1, z))))
            f = addon.paredes_composicao.ficha(modulo, s)
            self.assertGreaterEqual(f['inicio'], -1.5 - .00005)
            self.assertLessEqual(f['fim'], 1.5 + .00005)
            self.assertGreaterEqual(f['base'], -.00005)
            self.assertLessEqual(f['base'] + f['altura'], 2.7 + .00005)

    def test_previa_e_mira_usam_envelope_aceito_de_preset_girado(self):
        caminho = self.fixture(rotacao=.65)
        self.parede.rotation_euler.z = .45
        bpy.context.view_layer.update()
        self.iniciar()
        s = E._sessao[0]
        u, plano = Vector(s['u']), Vector(s['ponto'])
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            op = self.arraste_de_teste(caminho)
            op._arrastando, op._moveu = True, True
            evento = SimpleNamespace(type='MOUSEMOVE', value='NOTHING',
                           mouse_x=self.regiao.x + 300, mouse_y=self.regiao.y + 300)
            ponto = plano + u * (s['regiao']['retangulo'][1] - plano.dot(u) - .001)
            ponto.z = .001
            with patch.object(E, 'ponto_no_evento', return_value=ponto):
                op.modal(bpy.context, evento)
            self.assertTrue(op._valido)
            previa = [p.copy() for p in op._bbox_atual]
            centro = sum(previa, Vector()) / 8
            self.assertAlmostEqual(centro.dot(u), op._alvo.dot(u), places=5)
            self.assertAlmostEqual(centro.z, op._alvo.z, places=5)
            self.assertGreater((op._alvo - ponto).length, .1)
            self.assertLessEqual(max(p.dot(u) for p in previa), s['regiao']['retangulo'][1] + .00005)
            self.assertGreaterEqual(min(p.z for p in previa), -.00005)
            evento.type, evento.value = 'LEFTMOUSE', 'RELEASE'
            with patch.object(E, 'ponto_no_evento', return_value=ponto):
                self.assertEqual(op.modal(bpy.context, evento), {'FINISHED'})
        f = addon.paredes_composicao.ficha(bpy.context.object, s)
        self.assertAlmostEqual(f['inicio'], min(p.dot(u) for p in previa), places=5)
        self.assertAlmostEqual(f['fim'], max(p.dot(u) for p in previa), places=5)
        self.assertAlmostEqual(f['base'], min(p.z for p in previa), places=5)

    def arraste_direito(self, modulo):
        from types import MethodType
        op = SimpleNamespace(_modulo=modulo.name, _parede=None, _arrastou=True,
             _regiao=self.regiao, _rv3d=self.area.spaces.active.region_3d,
             _caixa=P.caixa_do_modulo(modulo), _matriz=modulo.matrix_world.copy(),
             _ignorar={modulo.name, *(o.name for o in modulo.children_recursive)},
             _associacao={k: getattr(modulo[k], 'to_list', lambda: modulo[k])()
                          for k in P.CHAVES_ASSOCIACAO if k in modulo}, report=lambda *args: None)
        for nome in ('modal', '_mover', '_encerrar', '_status', '_restaurar'):
            setattr(op, nome, MethodType(getattr(P.OBJECT_OT_arrastar_na_parede, nome), op))
        return op

    def test_arraste_direito_para_o_limbo_desassocia_sem_mover(self):
        # Pedido do usuario: soltar fora de qualquer parede solta a
        # associacao; o movel fica na posicao de origem.
        modulo = self.modulo()
        n = Vector((0, -1, 0))
        P.colocar_na_parede(modulo, self.parede, Vector((0, 1, 0)), n)
        P.associar(modulo, self.parede, Vector((0, 1, 0)), n)
        bpy.context.view_layer.update()
        antes = modulo.matrix_world.copy()
        evento = SimpleNamespace(type='RIGHTMOUSE', value='RELEASE', mouse_region_x=300, mouse_region_y=300)
        acerto = (self.parede, Vector((.4, 1, 1)), n, 0)
        op = self.arraste_direito(modulo)
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            # passa por outra parede e termina no vazio
            with patch.object(P, '_raio_ignorando', return_value=acerto):
                op._mover(bpy.context, evento)
            with patch.object(P, '_raio_ignorando', return_value=None):
                self.assertEqual(op.modal(bpy.context, evento), {'FINISHED'})
        self.assertIsNone(P.parede_do_modulo(modulo))
        self.assertFalse(any(k in modulo for k in P.CHAVES_ASSOCIACAO))
        for x, y in zip(sum(map(list, modulo.matrix_world), []), sum(map(list, antes), [])):
            self.assertAlmostEqual(x, y, places=5)
        # Sem associacao, soltar no vazio continua so' cancelando.
        op = self.arraste_direito(modulo)
        with bpy.context.temp_override(area=self.area, region=self.regiao),              patch.object(P, '_raio_ignorando', return_value=None):
            self.assertEqual(op.modal(bpy.context, evento), {'CANCELLED'})

    def test_arraste_direito_tambem_limita_quina_e_evitar_colisao(self):
        caminho = self.fixture()
        self.iniciar()
        a = self.inserir_imediato(caminho)
        b = self.inserir_imediato(caminho)
        op = self.arraste_direito(b)
        evento = SimpleNamespace(type='RIGHTMOUSE', value='RELEASE', mouse_region_x=300, mouse_region_y=300)
        acerto = (self.parede, Vector((1.499, 1, .001)), Vector((0,-1,0)), E._sessao[0]['face'])
        with bpy.context.temp_override(area=self.area, region=self.regiao), \
             patch.object(P, '_raio_ignorando', return_value=acerto):
            self.assertEqual(op.modal(bpy.context, evento), {'FINISHED'})
        f = addon.paredes_composicao.ficha(b, E._sessao[0])
        self.assertAlmostEqual(f['fim'], 1.5, places=5)
        self.assertAlmostEqual(f['base'], 0, places=5)
        op = self.arraste_direito(b)
        acerto = (self.parede, Vector((0,1,.2)), Vector((0,-1,0)), E._sessao[0]['face'])
        with bpy.context.temp_override(area=self.area, region=self.regiao), \
             patch.object(P, '_raio_ignorando', return_value=acerto):
            self.assertEqual(op.modal(bpy.context, evento), {'FINISHED'})
        fa, fb = (addon.paredes_composicao.ficha(o, E._sessao[0]) for o in (a,b))
        self.assertTrue(fb['inicio'] >= fa['fim'] - .00005 or fb['fim'] <= fa['inicio'] + .00005)

    def test_arraste_sem_vao_restaurar_associacao_e_geometria(self):
        caminho = self.fixture()
        self.iniciar()
        for i in range(5):
            self.inserir_imediato(caminho)
        modulo = self.modulo()
        matriz = modulo.matrix_world.copy()
        op = self.arraste_direito(modulo)
        acerto = (self.parede, Vector((0,1,.2)), Vector((0,-1,0)), E._sessao[0]['face'])
        evento = SimpleNamespace(type='RIGHTMOUSE', value='RELEASE', mouse_region_x=300, mouse_region_y=300)
        with bpy.context.temp_override(area=self.area, region=self.regiao), \
             patch.object(P, '_raio_ignorando', return_value=acerto):
            self.assertEqual(op.modal(bpy.context, evento), {'CANCELLED'})
        self.assertEqual(modulo.matrix_world, matriz)
        self.assertIsNone(P.parede_do_modulo(modulo))

    def test_encaixe_considera_altura_e_ignora_face_oposta(self):
        caminho = self.fixture()
        self.iniciar()
        a = self.inserir_imediato(caminho)
        b = self.inserir_imediato(caminho)
        self.assertIsNone(E.posicionar_modelo(bpy.context, b, Vector((0,1,1.2))))
        f = addon.paredes_composicao.ficha(b, E._sessao[0])
        self.assertAlmostEqual(f['inicio'] + f['largura']/2, 0, places=5)
        P.colocar_na_parede(a, self.parede, Vector((0,1.15,0)), Vector((0,1,0)))
        P.associar(a, self.parede, Vector((0,1.15,0)), Vector((0,1,0)))
        self.assertIsNone(E.posicionar_modelo(bpy.context, b, Vector((0,1,.2))))
        f = addon.paredes_composicao.ficha(b, E._sessao[0])
        self.assertAlmostEqual(f['inicio'] + f['largura']/2, 0, places=5)

    def test_ultimo_modulo_continua_referencia_ao_reentrar_no_modo(self):
        caminho = self.fixture()
        self.iniciar()
        a = self.inserir_imediato(caminho)
        self.assertIsNone(E.posicionar_modelo(bpy.context, a, Vector((-.6, 1, .8))))
        E.encerrar()
        self.iniciar()
        self.assertEqual(E._sessao[0]['ultimo_modulo'], a.name)
        b = self.inserir_imediato(caminho)
        fichas = [addon.paredes_composicao.ficha(o, E._sessao[0]) for o in (a, b)]
        self.assertAlmostEqual(fichas[0]['fim'], fichas[1]['inicio'], places=5)

    def test_arestas_nativas_so_da_madeira_sao_restauradas_na_saida_e_no_undo(self):
        caminho = self.fixture()
        self.iniciar()
        modulo = self.inserir_imediato(caminho)
        chapas = [o for o in modulo.children_recursive if addon.chapas.MARCA_CHAPA in o]
        nomes = [o.name for o in chapas]
        self.assertTrue(all(o.show_wire and not o[E.CHAVE_FIOS] for o in chapas))
        self.assertNotIn(E.CHAVE_FIOS, self.parede)
        E.encerrar()
        self.assertTrue(all(not bpy.data.objects[n].show_wire and E.CHAVE_FIOS not in bpy.data.objects[n] for n in nomes))
        # Um snapshot nativo pode trazer a marca temporaria de volta.
        for n in nomes:
            obj = bpy.data.objects[n]
            obj[E.CHAVE_FIOS] = False
            obj.show_wire = True
        E.verificar()
        self.assertTrue(all(not bpy.data.objects[n].show_wire and E.CHAVE_FIOS not in bpy.data.objects[n] for n in nomes))

    def test_aresta_previamente_ligada_pelo_usuario_permanece_ligada(self):
        modulo = self.modulo()
        chapa = next(o for o in modulo.children_recursive if addon.chapas.MARCA_CHAPA in o)
        chapa.show_wire = True
        P.colocar_na_parede(modulo, self.parede, Vector((0, 1, 0)), Vector((0, -1, 0)))
        P.associar(modulo, self.parede, Vector((0, 1, 0)), Vector((0, -1, 0)))
        self.iniciar()
        self.assertTrue(chapa[E.CHAVE_FIOS])
        E.encerrar()
        self.assertTrue(chapa.show_wire)
        self.assertNotIn(E.CHAVE_FIOS, chapa)


addon.register()
resultado = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestEdicaoParedes))
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de edicao de paredes')
