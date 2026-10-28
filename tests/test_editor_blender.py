"""Identidade nativa, persistencia e ponte de comandos do editor Cabinet Creator."""
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace, MethodType
from unittest.mock import patch
import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon
X, G, F = addon.editor, addon.gaveta, addon.biblioteca_faixa


class OBJECT_OT_contexto_teste(bpy.types.Operator):
    bl_idname = 'object.cabinet_teste_contexto'
    bl_label = 'Teste de contexto'

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        context.scene['area_teste'] = context.area.type
        context.scene['objeto_teste'] = context.object.name if context.object else ''
        return {'FINISHED'}


class TestEditor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.menu = next(a for a in bpy.context.screen.areas if a.type == 'PROPERTIES')
        self.cena = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        self.chaves = {k: bpy.context.screen.get(k) for k in
                       (G._CHAVE_GAVETA, F.CHAVE_AREA, F.CHAVE_LAYOUT, F.CHAVE_LUGAR)}
        F.definir_lugar('MENU', bpy.context.screen)
        bpy.ops.object.select_all(action='DESELECT')
        cubo = bpy.data.objects['Cube']
        cubo.select_set(True)
        bpy.context.view_layer.objects.active = cubo
        bpy.context.scene.cabinet_aba = 'MODULOS'
        X.configurar(self.menu)

    def tearDown(self):
        self.menu.type = 'PROPERTIES'
        for k, valor in self.chaves.items():
            if valor is None:
                bpy.context.screen.pop(k, None)
            else:
                bpy.context.screen[k] = valor
        self.tmp.cleanup()

    def contexto(self):
        regiao = next(r for r in self.menu.regions if r.type == 'WINDOW')
        return bpy.context.temp_override(area=self.menu, region=regiao)

    def test_tipos_nativos_e_gizmos_registrados_sem_viewport_de_fundo(self):
        self.assertIn(X.CABINET_NT_menu, addon.CLASSES)
        self.assertIn(X.CABINET_NT_biblioteca, addon.CLASSES)
        self.assertIn(X.NODE_GGT_cabinet_gaveta, addon.CLASSES)
        self.assertEqual(self.menu.type, 'NODE_EDITOR')
        self.assertEqual(self.menu.ui_type, X.TIPO_MENU)
        self.assertTrue(self.menu.spaces.active.node_tree.get(X.MARCA_INTERFACE))
        self.assertEqual(len(self.menu.spaces.active.node_tree.nodes), 0)
        self.assertGreater(len(self.menu.spaces.active.path), 0)
        with self.contexto():
            self.assertTrue(X.NODE_GGT_cabinet_gaveta.poll(bpy.context))
            self.assertFalse(addon.gaveta_eventos.VIEW3D_GGT_cabinet_gaveta.poll(bpy.context))

    def test_identidade_independe_de_ponteiros_gravados_na_screen(self):
        bpy.context.screen[G._CHAVE_GAVETA] = '1'
        self.assertEqual(G._area_gaveta(bpy.context.screen), self.menu)
        self.assertEqual(F.viewport(bpy.context.screen), self.cena)
        X.reparar(bpy.context.screen)
        self.assertEqual(bpy.context.screen[G._CHAVE_GAVETA], 0)

    def test_trocar_editor_nativo_por_viewport_nao_reabre_menu_ou_faixa(self):
        for tipo, chave in ((X.TIPO_MENU, G._CHAVE_GAVETA),
                            (X.TIPO_BIBLIOTECA, F.CHAVE_AREA)):
            X.configurar(self.menu, tipo)
            X.reparar(bpy.context.screen)
            self.assertEqual(bpy.context.screen.get(chave), 0)
            self.menu.type = 'VIEW_3D'
            self.menu.spaces.active.show_region_header = False
            self.menu.spaces.active.show_region_toolbar = False
            self.menu.spaces.active.overlay.show_overlays = False
            G._reconectar_gavetas()
            G._limitar_largura_gaveta()
            self.assertEqual(self.menu.type, 'VIEW_3D')

    def test_salvar_reabrir_restaura_editor_e_arvore_nativos(self):
        caminho = os.path.join(self.tmp.name, 'editor.blend')
        bpy.context.screen[G._CHAVE_GAVETA] = '1'
        bpy.ops.wm.save_as_mainfile(filepath=caminho)
        # Referencias de areas tambem nao sobrevivem ao carregamento.
        self.menu = self.cena = None
        bpy.ops.wm.open_mainfile(filepath=caminho, load_ui=True)
        self.menu = G._area_gaveta(bpy.context.screen)
        self.cena = F.viewport(bpy.context.screen)
        self.assertIsNotNone(self.menu)
        self.assertEqual(self.menu.ui_type, X.TIPO_MENU)
        self.assertIsNotNone(self.menu.spaces.active.node_tree)
        self.assertGreater(len(self.menu.spaces.active.path), 0)
        self.assertIsNotNone(self.cena)
        self.assertTrue(bpy.app.timers.is_registered(G._reconectar_gavetas))
        G._reconectar_gavetas()
        self.assertEqual(G._area_gaveta(bpy.context.screen), self.menu)

    def test_editor_de_biblioteca_tem_papel_proprio_e_mantem_cena(self):
        X.configurar(self.menu, X.TIPO_BIBLIOTECA)
        bpy.context.screen[F.CHAVE_AREA] = '1'
        self.assertEqual(F.area_da_faixa(bpy.context.screen), self.menu)
        self.assertEqual(F.viewport(bpy.context.screen), self.cena)
        with self.contexto():
            self.assertTrue(F.eh_faixa(bpy.context))
            self.assertTrue(G._eh_area_gaveta(bpy.context))
            self.assertTrue(G._widgets_interativos(bpy.context))

    def test_editor_comum_nao_e_capturado_nem_modificado(self):
        material = bpy.data.materials.new('Material de teste')
        material.use_nodes = True
        self.menu.ui_type = 'ShaderNodeTree'
        self.menu.spaces.active.node_tree = material.node_tree
        antes = [n.name for n in material.node_tree.nodes]
        X.reparar(bpy.context.screen)
        self.assertFalse(X.eh_editor(self.menu))
        self.assertEqual(self.menu.ui_type, 'ShaderNodeTree')
        self.assertEqual([n.name for n in material.node_tree.nodes], antes)

    def test_editor_mantem_objeto_selecao_e_comando_na_viewport_real(self):
        nome = bpy.context.object.name
        selecionados = [o.name for o in bpy.context.selected_objects]
        with self.contexto():
            self.assertEqual(bpy.context.object.name, nome)
            self.assertFalse(bpy.ops.object.cabinet_teste_contexto.poll())
            self.assertTrue(X.pode_executar('object.cabinet_teste_contexto'))
            self.assertEqual(X.executar(bpy.context, 'object.cabinet_teste_contexto'), {'FINISHED'})
            self.assertEqual(bpy.context.area, self.menu)
        self.assertEqual(bpy.context.scene['area_teste'], 'VIEW_3D')
        self.assertEqual(bpy.context.scene['objeto_teste'], nome)
        self.assertEqual([o.name for o in bpy.context.selected_objects], selecionados)

    def test_digitacao_e_arraste_de_preset_conservam_contexto_do_menu(self):
        with self.contexto():
            for nome in ('object.cabinet_editar_medida_gaveta', 'object.cabinet_arrastar_preset'):
                with X.contexto_do_comando(bpy.context, nome):
                    self.assertEqual(bpy.context.area, self.menu)
            self.assertTrue(addon.biblioteca.OBJECT_OT_arrastar_preset.poll(bpy.context))

    def test_sem_viewport_comando_avisa_sem_modificar_a_cena(self):
        self.cena.type = 'CONSOLE'
        try:
            with self.contexto():
                self.assertFalse(X.pode_executar('object.cabinet_teste_contexto'))
                with self.assertRaisesRegex(RuntimeError, 'viewport 3D'):
                    X.executar(bpy.context, 'object.cabinet_teste_contexto')
        finally:
            self.cena.type = 'VIEW_3D'

    def test_menu_legado_e_convertido_sem_reposicionar_a_viewport(self):
        self.menu.type = 'VIEW_3D'
        self.menu.spaces.active.show_region_header = False
        self.menu.spaces.active.show_region_toolbar = False
        self.menu.spaces.active.overlay.show_overlays = False
        bpy.context.screen[G._CHAVE_GAVETA] = '1'
        antes = tuple(self.cena.spaces.active.region_3d.view_rotation)
        G._reconectar_gavetas()
        self.assertEqual(self.menu.ui_type, X.TIPO_MENU)
        self.assertEqual(tuple(self.cena.spaces.active.region_3d.view_rotation), antes)

    def test_sem_marca_nao_converte_viewports_ocultas_do_usuario(self):
        self.menu.type = 'VIEW_3D'
        self.menu.spaces.active.show_region_header = False
        self.menu.spaces.active.show_region_toolbar = False
        self.menu.spaces.active.overlay.show_overlays = False
        bpy.context.screen.pop(G._CHAVE_GAVETA, None)
        G._reconectar_gavetas()
        self.assertEqual(self.menu.type, 'VIEW_3D')

    def test_faixa_legada_migra_quando_menu_ja_tem_identidade_nativa(self):
        def area(tipo, ponteiro, x, y, largura, altura):
            return SimpleNamespace(type=tipo, x=x, y=y, width=largura, height=altura,
                as_pointer=lambda: ponteiro, spaces=SimpleNamespace(active=SimpleNamespace(
                    tree_type=X.TIPO_MENU if tipo == 'NODE_EDITOR' else '',
                    node_tree=object(), show_region_header=False,
                    overlay=SimpleNamespace(show_overlays=False))))
        menu = area('NODE_EDITOR', 10, 0, 0, 200, 500)
        topo = area('VIEW_3D', 20, 0, 501, 800, 100)
        cena = area('VIEW_3D', 30, 201, 0, 599, 500)
        cena.spaces.active.show_region_header = True
        class Tela(dict):
            areas = [menu, topo, cena]
        tela = Tela({F.CHAVE_LAYOUT: 2, F.CHAVE_AREA: '99'})
        def configurar(alvo, tipo=X.TIPO_MENU):
            alvo.type = 'NODE_EDITOR'
            alvo.spaces.active.tree_type = tipo
        with patch.object(X, 'configurar', side_effect=configurar) as chamada:
            F.reconectar(tela)
            chamada.assert_called_once_with(topo, X.TIPO_BIBLIOTECA)
        self.assertEqual(tela[F.CHAVE_AREA], 0)
        self.assertEqual(F.area_da_faixa(tela), topo)
        self.assertEqual(F.viewport(tela), cena)

    def test_workpace_legado_agenda_reconexao_e_undo_nao_toca_layout(self):
        self.menu.type = 'VIEW_3D'
        bpy.context.screen[G._CHAVE_GAVETA] = '1'
        with patch.object(bpy.app.timers, 'is_registered', return_value=False), \
                patch.object(bpy.app.timers, 'register') as registrar:
            G._limitar_largura_gaveta()
            registrar.assert_called_once_with(G._reconectar_gavetas, first_interval=.05)
            registrar.reset_mock()
            addon.eventos._desfazendo[0] = True
            try:
                G._limitar_largura_gaveta()
                registrar.assert_not_called()
            finally:
                addon.eventos._fim_do_desfazer()

    def test_mudar_papel_e_reparar_arvore_nao_duplica_ids_da_interface(self):
        X.configurar(self.menu)
        antes = sum(bool(t.get(X.MARCA_INTERFACE)) for t in bpy.data.node_groups)
        for _ in range(3):
            self.menu.spaces.active.node_tree = None
            X.reparar(bpy.context.screen)
        self.assertEqual(sum(bool(t.get(X.MARCA_INTERFACE)) for t in bpy.data.node_groups), antes)
        self.assertEqual(self.menu.ui_type, X.TIPO_MENU)

    def test_clique_no_editor_troca_aba_sem_selecao_de_nos(self):
        nome = bpy.context.object.name
        with self.contexto():
            cab = G._partes_gaveta(G._widgets_gaveta(bpy.context, self.menu.width, self.menu.height))[0]
            def clicar(v):
                evento = SimpleNamespace(type='LEFTMOUSE', value='PRESS',
                    mouse_region_x=v[0]+v[2]/2, mouse_region_y=v[1]+v[3]/2)
                return addon.gaveta_eventos.OBJECT_OT_interagir_gaveta.invoke(SimpleNamespace(report=lambda *_: None), bpy.context, evento)
            if cab[0][5][0] == 'suspenso':
                clicar(cab[0])
                alvo = next(v for v in G._widgets_interativos(bpy.context) if v[5] == ('aba', 'PORTAS'))
            else:
                alvo = next(v for v in cab if v[5] == ('aba', 'PORTAS'))
            self.assertEqual(clicar(alvo), {'FINISHED'})
            self.assertEqual(bpy.context.scene.cabinet_aba, 'PORTAS')
            self.assertEqual(bpy.context.object.name, nome)

    def test_undo_redo_e_guarda_nao_criam_dados_durante_processamento_nativo(self):
        bpy.ops.ed.undo_push(message='Antes do movimento')
        bpy.context.object.location.x += 1
        bpy.context.view_layer.update()
        bpy.ops.ed.undo_push(message='Depois do movimento')
        bpy.ops.ed.undo()
        addon.eventos._fim_do_desfazer()
        X.reparar(bpy.context.screen)
        self.assertEqual(self.menu.ui_type, X.TIPO_MENU)
        self.assertIsNotNone(self.menu.spaces.active.node_tree)
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        X.reparar(bpy.context.screen)
        self.assertEqual(self.menu.ui_type, X.TIPO_MENU)
        self.menu.spaces.active.node_tree = None
        addon.eventos._desfazendo[0] = True
        try:
            X.reparar(bpy.context.screen)
            self.assertEqual(G._reconectar_gavetas(), .1)
            self.assertEqual(G._configurar_gavetas(), .05)
            self.assertEqual(F.configurar_pendentes(), .05)
            self.assertIsNone(self.menu.spaces.active.node_tree)
        finally:
            addon.eventos._fim_do_desfazer()
        X.reparar(bpy.context.screen)
        self.assertIsNotNone(self.menu.spaces.active.node_tree)

    def test_arraste_da_biblioteca_parte_do_editor_e_usa_a_regiao_3d(self):
        with bpy.context.temp_override(area=self.cena, region=next(r for r in self.cena.regions if r.type == 'WINDOW')):
            bpy.ops.object.select_all(action='DESELECT')
            bpy.ops.object.cabinet_criar_nicho()
            pecas = [o for o in bpy.context.scene.objects if addon.chapas.MARCA_CHAPA in o and o.parent is None]
            for o in pecas:
                o.select_set(True)
            bpy.context.view_layer.objects.active = pecas[0]
            bpy.ops.object.cabinet_agrupar()
            modulo = bpy.context.object
            colecao = next(c for c in modulo.users_collection if c.get('eh_colecao_modulo'))
            caminho = os.path.join(self.tmp.name, 'modelo.blend')
            bpy.data.libraries.write(caminho, {colecao})
            for o in [modulo, *modulo.children_recursive]:
                bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(colecao)
            bpy.context.view_layer.objects.active = bpy.data.objects['Cube']
            bpy.data.objects['Cube'].select_set(True)
        antes = set(bpy.data.objects.keys())
        with self.contexto():
            class Contexto:
                window_manager = SimpleNamespace(modal_handler_add=lambda op: None)
                def __getattr__(self, nome):
                    return getattr(bpy.context, nome)
            op = SimpleNamespace(pasta=self.tmp.name, arquivo='modelo.blend', tipo='modulo', report=lambda *_: None)
            for nome in dir(addon.biblioteca.OBJECT_OT_arrastar_preset):
                metodo = getattr(addon.biblioteca.OBJECT_OT_arrastar_preset, nome)
                if callable(metodo) and not nome.startswith('__'):
                    setattr(op, nome, MethodType(metodo, op))
            evento = SimpleNamespace(mouse_x=self.menu.x+10, mouse_y=self.menu.y+10)
            self.assertEqual(op.invoke(Contexto(), evento), {'RUNNING_MODAL'})
            try:
                self.assertTrue(op._arrastando)
                self.assertEqual(op._area_preview, self.cena)
                self.assertEqual(op._regiao, next(r for r in self.cena.regions if r.type == 'WINDOW'))
            finally:
                self.assertEqual(op._cancelar(bpy.context), {'CANCELLED'})
        self.assertEqual(set(bpy.data.objects.keys()), antes)

    def test_desregistrar_limpa_interface_sem_apagar_arvores_de_usuario(self):
        outra = bpy.data.node_groups.new('Geometria do usuario', 'GeometryNodeTree')
        nome = outra.name
        areas = {a.as_pointer() for a in bpy.context.screen.areas}
        X.desregistrar()
        try:
            self.assertNotIn(X._ao_carregar, bpy.app.handlers.load_post)
            self.assertFalse(X._keymaps[0])
            self.assertFalse(any(t.get(X.MARCA_INTERFACE) for t in bpy.data.node_groups))
            self.assertIn(nome, bpy.data.node_groups)
            self.assertEqual(self.menu.ui_type, 'ShaderNodeTree')
            self.assertEqual({a.as_pointer() for a in bpy.context.screen.areas}, areas)
        finally:
            X.registrar()
            X.configurar(self.menu)

    def test_excecao_no_comando_restaura_contexto_e_dois_editores_funcionam(self):
        outra = next(a for a in bpy.context.screen.areas if a.type == 'OUTLINER')
        X.configurar(outra)
        try:
            with bpy.context.temp_override(area=outra):
                self.assertTrue(G._eh_area_gaveta(bpy.context))
            with self.contexto():
                with self.assertRaises(ValueError):
                    with X.contexto_do_comando(bpy.context, 'object.cabinet_teste_contexto'):
                        self.assertEqual(bpy.context.area, self.cena)
                        raise ValueError('Falha de teste')
                self.assertEqual(bpy.context.area, self.menu)
        finally:
            outra.type = 'OUTLINER'


bpy.utils.register_class(OBJECT_OT_contexto_teste)
addon.register()
resultado = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestEditor))
addon.unregister()
bpy.utils.unregister_class(OBJECT_OT_contexto_teste)
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes do editor Cabinet Creator')
