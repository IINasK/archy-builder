"""Protect the add-on's structure from accidental changes.

Run: blender --background --factory-startup --python-exit-code 1 --python tests/test_structure_blender.py

Other tests check behavior, such as a responsive sidebar or a fitting door. These check architectural decisions that work today but could be broken by a well-intentioned refactor. Read failures as intentional design requiring owner agreement before changing it, never as an instruction to weaken the test.

See DESIGN.md for the reasoning behind each protected decision."""
import inspect
import re
import os
import sys
import unittest

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon


# Closed vocabulary of widget actions. _widgets_gaveta returns tuples
# (x, y, w, h, rotulo, acao); acao[0] is the verb dispatched by
# OBJECT_OT_interagir_gaveta. A new verb absent here is almost always
# an existing action duplicated under another name.
VERBOS = frozenset({
    'aba', 'auto', 'biblioteca', 'chapa', 'medida', 'modo',
    'navegar', 'nome_objeto', 'operador', 'portas', 'preset',
    'rolar_nivel', 'separador', 'slider', 'wireframe', 'escolha',
    'ler_portas', 'cadeado', 'suspenso', 'faixa', 'cor', 'fundo',
    'divisa', 'pergunta', 'resposta', 'nivel', 'rolagem', 'rotulo',
})

# Classes intentionally defined in the module but excluded from CLASSES.
# VIEW3D_PT_archy_builder is the legacy N panel, replaced by the sidebar
# but retained as a reference. Do not register it without asking.
NAO_REGISTRADAS = frozenset({'VIEW3D_PT_archy_builder'})


def classes_do_modulo():
    bases = (bpy.types.Operator, bpy.types.Panel, bpy.types.Gizmo,
             bpy.types.GizmoGroup, bpy.types.AssetShelf,
             bpy.types.AddonPreferences)
    return {nome: obj for nome, obj in vars(addon).items()
            if inspect.isclass(obj) and issubclass(obj, bases)
            and obj.__module__ == addon.__name__}


class TestArquiteturaDaGaveta(unittest.TestCase):
    """The sidebar is an area, not an overlay in the main viewport."""

    def test_gaveta_abre_como_area_dividida(self):
        # Migration to an overlay was evaluated and rejected: it would share event
        # handling, GPU state and the upper-left corner with other viewport-drawing
        # add-ons such as BlenderKit.
        # A dedicated area avoids all three conflicts.
        fonte = (inspect.getsource(addon.biblioteca_faixa.configurar_pendentes)
                 + inspect.getsource(addon.biblioteca_faixa.fechar))
        self.assertIn('screen.area_split', fonte)
        self.assertIn('screen.area_close', fonte)
        self.assertEqual(addon.gaveta._CHAVE_GAVETA, 'cabinet_gaveta_area')

    def test_area_e_localizada_por_identidade_nativa_com_migracao_do_ponteiro(self):
        # The v365 migration retains the pointer only for legacy data; the subtype
        # saved in the .blend prevents capturing a user's viewport.
        self.assertTrue(callable(addon.gaveta._area_gaveta))
        self.assertTrue(callable(addon.gaveta._reconectar_gavetas))
        fonte = inspect.getsource(addon.gaveta._area_gaveta)
        self.assertIn('_editor.TIPO_MENU', fonte)
        self.assertIn('as_pointer()', fonte)
        self.assertIsNone(addon.gaveta._area_gaveta(bpy.context.screen))

    def test_largura_e_corrigida_por_timer_nunca_por_modal(self):
        # Area.width is read-only. The timer adjusts the divider after resize and skips
        # windows with an active modal operator, avoiding event competition
        # with the user's operator.
        fonte = inspect.getsource(addon.gaveta._limitar_largura_gaveta)
        self.assertIn('modal_operators', fonte)
        self.assertIn('screen.area_move', fonte)
        self.assertEqual(addon.gaveta._LARGURA_MAX_GAVETA, 564)

    def test_gaveta_abre_na_menor_largura_com_medidas_em_linha(self):
        # User request: open at exactly the minimum width fitting Width, Height
        # and Depth on one row, neither narrower nor wider.
        self.assertEqual(addon.gaveta._LARGURA_PADRAO_GAVETA,
                         addon.gaveta.LARGURA_MEDIDAS_EM_LINHA)
        fonte = inspect.getsource(addon.biblioteca_faixa.configurar_pendentes)
        self.assertIn('_largura_inicial_gaveta', fonte)
        bpy.ops.mesh.primitive_cube_add()
        try:
            bpy.context.scene.cabinet_aba = 'MODULOS'
            def linhas(largura):
                medidas = [v for v in addon.gaveta._widgets_gaveta(
                    bpy.context, largura, 1200)
                    if v[5] and v[5][0] == 'medida']
                self.assertEqual(len(medidas), 3)
                return len({v[1] for v in medidas})
            inicial = addon.gaveta._largura_inicial_gaveta(bpy.context)
            self.assertEqual(linhas(inicial), 1)
            self.assertEqual(linhas(inicial - 3), 2)
        finally:
            bpy.ops.object.delete(use_global=False)

    def test_desenho_e_um_handler_post_pixel(self):
        self.assertIsNotNone(addon.gaveta._handler_gaveta[0])


class TestAlca(unittest.TestCase):
    """The handle is a gizmo with its own hit-test and no modal operator."""

    def test_alca_e_gizmo_com_test_select(self):
        self.assertTrue(issubclass(addon.gaveta_eventos.VIEW3D_GT_alca_gaveta,
                                   bpy.types.Gizmo))
        self.assertTrue(hasattr(addon.gaveta_eventos.VIEW3D_GT_alca_gaveta, 'test_select'))
        self.assertIn(addon.gaveta_eventos.VIEW3D_GT_alca_gaveta, addon.CLASSES)
        ctx = type('C', (), {'region': type('R', (), {'height': 1000})()})()
        self.assertEqual(
            addon.gaveta_eventos.VIEW3D_GT_alca_gaveta.test_select(None, ctx, (300, 300)), -1)

    def test_alca_nao_desenha_pelo_gizmo(self):
        # Only the POST_PIXEL callback draws it. If the gizmo draws again through
        # GIZMO_GT_button_2d BACKDROP/OUTLINE, the handle appears twice,
        # one image over the other.
        fonte = inspect.getsource(addon.gaveta_eventos.VIEW3D_GT_alca_gaveta.draw)
        self.assertIn('pass', fonte)
        self.assertNotIn('draw_options', fonte)

    def test_alternar_gaveta_nao_e_modal(self):
        # A modal handle would steal viewport events from other add-ons.
        self.assertFalse(hasattr(addon.gaveta_eventos.OBJECT_OT_alternar_gaveta, 'modal'))

    def test_geometria_da_alca_bate_com_o_desenho(self):
        # test_select and the POST_PIXEL rectangle are separate code paths;
        # changing one without the other offsets the clickable area
        # from what is drawn.
        fonte = inspect.getsource(addon.gaveta_desenho._desenhar_gaveta)
        self.assertIn('max(48, context.region.height * 0.12)', fonte)
        hit = inspect.getsource(addon.gaveta_eventos.VIEW3D_GT_alca_gaveta.test_select)
        self.assertIn('max(48, context.region.height * 0.12)', hit)
        self.assertIn('0 <= x <= 26', hit)
        self.assertIn('abs(y - centro) <= 35', hit)


class TestHigieneDeGPU(unittest.TestCase):
    def test_blend_sempre_desligado_no_fim(self):
        # GPU state leaks into subsequent drawing, including other add-ons
        # if the sidebar ever shares their area.
        # Counting ALPHA and NONE is insufficient because ALPHA is reenabled inside
        # the widget loop. Every exit path must disable it;
        # currently those paths are the handle and sidebar.
        chamadas = re.findall(r"blend_set\('(\w+)'\)",
                              inspect.getsource(addon.gaveta_desenho._desenhar_gaveta))
        self.assertEqual(chamadas[-1], 'NONE')
        self.assertEqual(chamadas.count('NONE'), 2,
                         "New exit path must disable blending")


class TestGridDeMedidas(unittest.TestCase):
    """The scene box and the axis highlighted by each field."""

    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        addon.hud._realce_medida[0] = None

    def test_tabela_de_eixos_cobre_todos_os_rotulos(self):
        # A label without an axis highlights nothing and obscures what will change;
        # this is precisely what the grid resolves.
        # Cabinet thickness is the only intentional omission because it is not
        # a box edge.
        bpy.ops.mesh.primitive_cube_add()
        for modo, esperados in (('LIVRE', {"Width", "Height",
                                           "Depth"}),
                                ('INDIVIDUAL', {"Width", "Height",
                                                "Thickness"}),
                                ('GRUPO', {"Width", "Height",
                                           "Depth"})):
            self.assertTrue(
                esperados <= set(addon.hud.EIXOS_MEDIDA[modo]), modo)
        self.assertNotIn("Depth", addon.hud.EIXOS_MEDIDA['INDIVIDUAL'])
        self.assertNotIn("Thickness", addon.hud.EIXOS_MEDIDA['GRUPO'])

    def test_eixos_seguem_a_convencao_do_addon(self):
        # Cabinet and free object: Width = X, Height = Z, Depth = Y.
        for modo in ('GRUPO', 'LIVRE'):
            self.assertEqual(addon.hud.EIXOS_MEDIDA[modo]["Width"], 0)
            self.assertEqual(addon.hud.EIXOS_MEDIDA[modo]["Height"], 2)
            self.assertEqual(addon.hud.EIXOS_MEDIDA[modo]["Depth"], 1)
        # Panel: local axes, with thickness on local Z.
        self.assertEqual(addon.hud.EIXOS_MEDIDA['INDIVIDUAL'],
                         {"Width": 0, "Height": 1, "Thickness": 2})

    def test_arestas_batem_com_a_indexacao_por_bits(self):
        # Each axis has four edges; the two corners of an edge along axis a
        # differ in exactly bit a.
        vistos = set()
        for a, arestas in enumerate(addon.hud.ARESTAS_EIXO):
            self.assertEqual(len(arestas), 4)
            for i, j in arestas:
                self.assertEqual(j - i, 1 << a)
                vistos.add((i, j))
        self.assertEqual(len(vistos), 12)

    def test_caixa_livre_envolve_o_objeto(self):
        bpy.ops.mesh.primitive_cube_add(size=2.0)
        bpy.context.object.location = (5.0, 0.0, 0.0)
        bpy.context.view_layer.update()
        cantos = addon.hud._caixa_da_medida(bpy.context, 'LIVRE')
        self.assertEqual(len(cantos), 8)
        for a, esperado in enumerate((4.0, -1.0, -1.0)):
            self.assertAlmostEqual(min(c[a] for c in cantos), esperado,
                                   places=5)
        # An edge of axis 0 measures width.
        i, j = addon.hud.ARESTAS_EIXO[0][0]
        self.assertAlmostEqual((cantos[j] - cantos[i]).length, 2.0, places=5)

    def test_caixa_da_chapa_acompanha_a_rotacao(self):
        # Rotated panel: thickness remains the local Z edge, not world vertical.
        # A world-aligned box would highlight
        # the wrong edge.
        obj = addon.chapas.nova_chapa('Girada', 600.0, 400.0, 18.0,
                               (0.0, 0.0, 0.0), (0.0, 90.0, 0.0),
                               bpy.context)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.context.view_layer.update()
        cantos = addon.hud._caixa_da_medida(bpy.context, 'INDIVIDUAL')
        eixo = addon.hud.EIXOS_MEDIDA['INDIVIDUAL']["Thickness"]
        i, j = addon.hud.ARESTAS_EIXO[eixo][0]
        aresta = cantos[j] - cantos[i]
        self.assertAlmostEqual(aresta.length, 0.018, places=5)
        # Rotated 90 degrees around Y, thickness lies along world X.
        self.assertAlmostEqual(abs(aresta.normalized().x), 1.0, places=4)
        self.assertEqual(obj.chapa_espessura_mm, 18.0)

    def test_sem_realce_nao_desenha(self):
        # The box appears only while hovering over or editing a field;
        # otherwise the viewport remains clear.
        self.assertIsNone(addon.hud._realce_medida[0])
        addon.hud._desenhar_grid_medidas()   # Must not raise.

    def test_handler_do_grid_e_post_view(self):
        # POST_PIXEL would draw in screen coordinates, but the box belongs
        # in world coordinates with the scene.
        self.assertIsNotNone(addon.hud._handler_grid[0])
        fonte = inspect.getsource(addon.register)
        self.assertIn("_desenhar_grid_medidas, (), 'WINDOW', 'POST_VIEW'",
                      fonte)

    def test_campo_e_gizmo_sem_modal(self):
        # Same reason as the handle: hover and click use a gizmo,
        # never a persistent modal operator.
        self.assertTrue(issubclass(addon.gaveta_desenho.VIEW3D_GT_campo_gaveta,
                                   bpy.types.Gizmo))
        self.assertIn(addon.gaveta_desenho.VIEW3D_GT_campo_gaveta, addon.CLASSES)
        self.assertIn('pass',
                      inspect.getsource(addon.gaveta_desenho.VIEW3D_GT_campo_gaveta.draw))

    def test_glow_e_o_mesmo_da_alca(self):
        # Glow matching the handle must use the same function, not a copy
        # that diverges on the first change.
        fonte = inspect.getsource(addon.gaveta_desenho._desenhar_gaveta)
        self.assertGreaterEqual(fonte.count('_glow_gaveta('), 2)
        halo = inspect.getsource(addon.gaveta._glow_gaveta)
        self.assertIn('((6, 0.025), (4, 0.045), (2, 0.07))', halo)

    def test_glow_liga_o_proprio_blend(self):
        # Regression: blf.draw changes blend state, making the second and later widgets'
        # halos opaque white blocks over text, observed on Height
        # and Depth.
        # The halo must not depend on what drew before it.
        halo = inspect.getsource(addon.gaveta._glow_gaveta)
        self.assertIn("blend_set('ALPHA')", halo)
        self.assertLess(halo.index("blend_set('ALPHA')"),
                        halo.index('for margem'))

    def test_glow_vai_antes_do_corpo_do_botao(self):
        # Drawing on top washes out text instead of surrounding the widget.
        fonte = inspect.getsource(addon.gaveta_desenho._desenhar_gaveta)
        self.assertLess(fonte.index('_glow_gaveta(x, y, w, h, 4'),
                        fonte.index('_botao_gaveta(x, y, w, h, ativo=ativo'))

    def test_todo_botao_tem_chave_de_realce(self):
        # Glow applies to every button: each clickable verb needs a key;
        # only decoration may omit one.
        bpy.ops.mesh.primitive_cube_add()
        cena = bpy.context.scene
        cena.cabinet_aba = 'MODULOS'
        cena.chapa_bib_aberta = True
        cena.chapa_n1 = "Cabinets"
        sem_chave = set()
        for largura in (190, 320, 564):
            for _x, _y, _w, _h, _r, acao in addon.gaveta._widgets_gaveta(
                    bpy.context, largura, 1200):
                # The v387 strip remains without selection; disabled buttons do not highlight.
                if addon.visibilidade.eh_acao(acao) and addon.gaveta_eventos._operador_apagado(acao):
                    continue
                if acao and addon.gaveta_desenho._chave_widget(acao) is None:
                    sem_chave.add(acao[0])
        self.assertEqual(sem_chave - {'wireframe', 'separador',
                                        'nome_objeto', 'slider', 'rotulo'}, set())

    def test_chaves_de_realce_nao_colidem(self):
        # Two identical keys would highlight both widgets together.
        bpy.ops.mesh.primitive_cube_add()
        cena = bpy.context.scene
        cena.cabinet_aba = 'MODULOS'
        cena.chapa_bib_aberta = True
        cena.chapa_n1 = "Cabinets"
        chaves = [addon.gaveta_desenho._chave_widget(v[5]) for v in addon.gaveta._widgets_gaveta(
            bpy.context, 320, 1200) if addon.gaveta_desenho._chave_widget(v[5])]
        self.assertEqual(len(chaves), len(set(chaves)))

    def test_hit_test_poupa_o_disco_do_icone(self):
        # The icon gizmo must still win picking over its own area or its tooltip
        # disappears. Glow covers both targets by combining
        # their is_highlight states.
        teste = addon.gaveta_desenho.VIEW3D_GT_campo_gaveta.test_select
        giz = type('G', (), {'as_pointer': lambda self: 4242})()
        addon.hud._campos_gaveta[4242] = (10, 10, 200, 40, (110, 30, 13))
        try:
            self.assertEqual(teste(giz, None, (20, 30)), 0)
            self.assertEqual(teste(giz, None, (110, 30)), -1)
            self.assertEqual(teste(giz, None, (300, 30)), -1)
        finally:
            addon.hud._campos_gaveta.clear()


class TestListaSuspensaDaCascata(unittest.TestCase):
    """Library inside the menu: each cascade level is a dropdown field with a floating list, like Promob, as requested. This replaces the sliding carousel; the top strip retains its own rows."""

    NOME = 'cabinet_carrossel_1'

    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        cena = bpy.context.scene
        cena.cabinet_aba = 'MODULOS'
        cena.cabinet_bib_modo = 'MODULOS'
        cena.chapa_bib_aberta = True
        cena.chapa_n1 = ''
        bpy.context.screen[addon.gaveta._CHAVE_SUSPENSO] = ''

    def tearDown(self):
        bpy.context.screen[addon.gaveta._CHAVE_SUSPENSO] = ''

    def widgets(self):
        return addon.gaveta._widgets_gaveta(bpy.context, 320, 1200)

    def campo(self, itens):
        return next(v for v in addon.gaveta._partes_gaveta(itens)[1]
                    if v[5] and v[5][0] == 'suspenso' and len(v[5]) > 3)

    def test_um_campo_por_nivel_sem_carrossel(self):
        itens = self.widgets()
        campos = [v for v in addon.gaveta._partes_gaveta(itens)[1]
                  if v[5] and v[5][0] == 'suspenso' and len(v[5]) > 3]
        self.assertEqual([v[5][3] for v in campos], [1])
        B = addon.biblioteca
        esperado = sorted(B.filhos_de(B.indice_completo() + B.itens_de_fabrica(), ()), key=str.casefold)
        self.assertEqual(list(campos[0][5][4]), esperado)
        self.assertEqual(campos[0][4], "Choose...")
        self.assertFalse([v for v in itens if v[5] and v[5][0] in ('navegar', 'rolar_nivel')])

    def test_lista_flutua_embaixo_do_campo_e_cobre_o_conteudo(self):
        bpy.context.screen[addon.gaveta._CHAVE_SUSPENSO] = self.NOME
        itens = self.widgets()
        campo = self.campo(itens)
        _cab, conteudo, rodape = addon.gaveta._partes_gaveta(itens)
        _rodape, flutuante = addon.gaveta._separar_flutuante(rodape)
        fundo, linhas = flutuante[0], flutuante[1:]
        self.assertEqual(fundo[5], ('fundo',))
        self.assertEqual([v[5][2] for v in linhas], list(campo[5][4]))
        self.assertTrue(all(v[5][:2] == ('nivel', 1) for v in linhas))
        self.assertLessEqual(fundo[1] + fundo[3], campo[1])
        self.assertEqual((fundo[0], fundo[2]), (campo[0], campo[2]))
        fx, fy, fw, fh = fundo[:4]
        for v in conteudo:
            if v[5] and v[5][0] == 'divisa':
                continue
            self.assertFalse(v[0] < fx + fw and fx < v[0] + v[2]
                             and v[1] < fy + fh and fy < v[1] + v[3], v)
        # When collapsed, hide the list and leave only that level's field.
        bpy.context.screen[addon.gaveta._CHAVE_SUSPENSO] = ''
        self.assertFalse([v for v in self.widgets() if v[5] and v[5][0] == 'nivel'])

    def test_sem_espaco_abre_em_cima_ou_em_colunas(self):
        valores = tuple('Categoria %02d' % i for i in range(20))
        def lista(y, piso, teto, n):
            campo = (10, y, 200, 25, 'x', ('suspenso', self.NOME, True, 1, valores[:n], ''))
            return addon.gaveta._lista_da_cascata([campo], piso, teto)
        em_cima = lista(50, 40, 600, 5)
        self.assertGreaterEqual(em_cima[0][1], 50 + 25)
        colunas = lista(100, 40, 200, 20)
        self.assertEqual(len(colunas) - 1, 20)
        for v in colunas:
            self.assertGreaterEqual(v[1], 40)
            self.assertLessEqual(v[1] + v[3], 200)
        linhas = colunas[1:]
        for i, a in enumerate(linhas):
            for b in linhas[i + 1:]:
                self.assertFalse(a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
                                 and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])
        # A field clipped by scrolling must not leave floating content detached on screen.
        self.assertEqual(lista(30, 40, 600, 5), [])

    def test_cada_linha_acende_sozinha(self):
        # Without an identity per row, hovering one would highlight the whole list.
        bpy.context.screen[addon.gaveta._CHAVE_SUSPENSO] = self.NOME
        linhas = [v for v in self.widgets() if v[5] and v[5][0] == 'nivel']
        chaves = [addon.gaveta_desenho._chave_widget(v[5]) for v in linhas]
        self.assertGreater(len(chaves), 1)
        self.assertEqual(len(set(chaves)), len(chaves))

    def test_materiais_tem_lista_propria(self):
        # Preset and material cascades are distinct; opening one must not open the other.
        cena = bpy.context.scene
        cena.cabinet_bib_modo = 'MATERIAIS'
        try:
            bpy.context.screen[addon.gaveta._CHAVE_SUSPENSO] = self.NOME
            itens = self.widgets()
            self.assertFalse([v for v in itens if v[5] and v[5][0] == 'nivel'])
            campo = self.campo(itens)
            self.assertEqual(campo[5][1], 'cabinet_carrossel_mat_1')
            bpy.context.screen[addon.gaveta._CHAVE_SUSPENSO] = campo[5][1]
            linhas = [v[5][2] for v in self.widgets() if v[5] and v[5][0] == 'nivel']
            self.assertEqual(linhas, list(campo[5][4]))
        finally:
            cena.cabinet_bib_modo = 'MODULOS'

    def test_escolher_linha_navega_fecha_e_repetir_nao_fecha_nivel(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        tela = bpy.context.screen
        tela[addon.gaveta._CHAVE_SUSPENSO] = self.NOME
        linha = next(v for v in self.widgets() if v[5] and v[5][0] == 'nivel')
        ctx = SimpleNamespace(screen=tela, scene=bpy.context.scene,
                              area=SimpleNamespace(tag_redraw=lambda: None),
                              region=SimpleNamespace(width=320, height=1200))
        evento = SimpleNamespace(type='LEFTMOUSE', value='PRESS',
                                 mouse_region_x=linha[0] + 2, mouse_region_y=linha[1] + 2)
        classe = addon.gaveta_eventos.OBJECT_OT_interagir_gaveta
        op = SimpleNamespace(report=lambda *a: None)
        with patch.object(addon.gaveta, '_widgets_interativos', return_value=[linha]):
            classe.invoke(op, ctx, evento)
        self.assertEqual(list(addon.biblioteca.trilha_da_cena(bpy.context.scene)), [linha[5][2]])
        self.assertEqual(tela[addon.gaveta._CHAVE_SUSPENSO], '')
        repetida = linha[:5] + (('nivel', 1, linha[5][2], True),)
        with patch.object(addon.gaveta, '_widgets_interativos', return_value=[repetida]):
            classe.invoke(op, ctx, evento)
        self.assertEqual(list(addon.biblioteca.trilha_da_cena(bpy.context.scene)), [linha[5][2]])


class TestContratoDosWidgets(unittest.TestCase):
    """_widgets_gaveta is the boundary between layout and drawing."""

    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        cena = bpy.context.scene
        cena.cabinet_aba = 'MODULOS'
        cena.chapa_bib_aberta = True
        cena.chapa_n1 = "Cabinets"
        cena.chapa_n2 = "Living Room"
        cena.chapa_n3 = "Base Cabinets"

    def todos(self):
        """Return flattened widgets across multiple states and widths."""
        saida = []
        cena = bpy.context.scene
        for aba in ('MODULOS', 'PORTAS'):
            cena.cabinet_aba = aba
            for largura in (190, 320, 564):
                saida += addon.gaveta._widgets_gaveta(bpy.context, largura, 1200)
        cena.cabinet_aba = 'MODULOS'
        return saida

    def test_tupla_de_seis_elementos(self):
        for widget in self.todos():
            self.assertEqual(len(widget), 6)
            x, y, w, h, rotulo, acao = widget
            for valor in (x, y, w, h):
                self.assertIsInstance(valor, (int, float))
            self.assertIsInstance(rotulo, str)
            if acao is not None:
                self.assertIsInstance(acao, tuple)
                self.assertIsInstance(acao[0], str)

    def test_vocabulario_de_acoes_esta_congelado(self):
        marcado = self.todos()
        bpy.ops.object.cabinet_marcar()
        usados = {w[5][0] for w in marcado + self.todos() if w[5]}
        novos = usados - VERBOS
        self.assertFalse(novos, "New widget verb: %s -- confirm it is not a duplicate and add it to VERBOS" % novos)

    def test_nada_desenha_fora_da_gaveta(self):
        for largura in (190, 320, 564, 2056):
            for x, y, w, h, _r, _a in addon.gaveta._widgets_gaveta(
                    bpy.context, largura, 1200):
                self.assertGreaterEqual(x, 0)
                self.assertLessEqual(x + w, min(largura - 12, 552) + 0.01)
                self.assertGreaterEqual(w, 0)
                self.assertGreaterEqual(h, 0)

    def test_largura_maxima_respeitada_em_tela_larga(self):
        # The sidebar stops growing at 564 px: overly wide text columns become
        # unreadable and thumbnails become strips.
        larguras = {w[0] + w[2] for w in
                    addon.gaveta._widgets_gaveta(bpy.context, 2056, 1200)}
        self.assertLessEqual(max(larguras), addon.gaveta._LARGURA_MAX_GAVETA - 12)


class TestEstruturaDaChapa(unittest.TestCase):
    """Basic-module invariants; breaking these invalidates the library."""

    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)

    def chapa(self, larg=600.0, comp=400.0, esp=18.0):
        return addon.chapas.nova_chapa('Teste', larg, comp, esp,
                                (0.0, 0.0, 0.0), (0.0, 0.0, 0.0),
                                bpy.context)

    def test_marcadores_sao_id_props_e_nao_rna(self):
        # MARCA_CHAPA in obj works only for ID properties. Replacing them with bpy.props
        # would make membership always return False and prevent recognition
        # of the entire library.
        obj = self.chapa()
        self.assertIn(addon.chapas.MARCA_CHAPA, obj)
        rna = {p.identifier for p in obj.bl_rna.properties}
        for marca in (addon.chapas.MARCA_CHAPA, addon.chapas.MARCA_CONJUNTO,
                      addon.chapas.MARCA_PORTAS, addon.chapas.MARCA_FOLHA):
            self.assertNotIn(marca, rna)

    def test_nomes_gravados_nos_presets_nao_mudam(self):
        # These literals are stored inside library .blend files.
        self.assertEqual(addon.chapas.MARCA_CHAPA, 'eh_chapa')
        self.assertEqual(addon.chapas.MARCA_CONJUNTO, 'eh_conjunto_chapa')
        self.assertEqual(addon.chapas.MARCA_PORTAS, 'eh_grupo_portas')
        self.assertEqual(addon.chapas.MARCA_FOLHA, 'eh_folha_porta')

    def test_eixos_locais_x_largura_y_comprimento_z_espessura(self):
        obj = self.chapa(600.0, 400.0, 18.0)
        self.assertAlmostEqual(obj.dimensions.x, 0.6, places=5)
        self.assertAlmostEqual(obj.dimensions.y, 0.4, places=5)
        self.assertAlmostEqual(obj.dimensions.z, 0.018, places=5)

    def test_escala_vira_medida_e_z_e_descartado(self):
        obj = self.chapa(600.0, 400.0, 18.0)
        obj.scale = (2.0, 0.5, 7.0)
        addon.chapas.normalizar_chapas([obj])
        bpy.context.view_layer.update()
        self.assertAlmostEqual(obj.chapa_largura_mm, 1200.0, places=3)
        self.assertAlmostEqual(obj.chapa_comprimento_mm, 200.0, places=3)
        self.assertAlmostEqual(obj.chapa_espessura_mm, 18.0, places=3)
        for eixo in obj.scale:
            self.assertAlmostEqual(eixo, 1.0, places=5)

    def test_espessura_livre_e_alerta_acima_de_60(self):
        # User request: thickness is not restricted to conventional values,
        # which remain only choices/defaults. Above 60 mm, the sidebar paints
        # both field name and value red.
        self.assertEqual(addon.chapas.ESPESSURAS_PERMITIDAS, [15.0, 18.0, 20.0, 30.0])
        self.assertEqual(addon.chapas.ESPESSURA_ALERTA_MM, 60.0)
        obj = self.chapa()
        for pedido in (16.0, 19.0, 26.0, 75.0):
            obj.chapa_espessura_mm = pedido
            self.assertAlmostEqual(obj.chapa_espessura_mm, pedido, places=3)
            self.assertAlmostEqual(obj.dimensions.z, pedido / 1000, places=5)
        for valor, alerta in ((18.0, False), (60.0, False), (60.5, True)):
            acao = ('medida', 'objeto', 'ui_chapa_espessura', "Thickness",
                    valor)
            self.assertEqual(addon.gaveta_desenho._medida_em_alerta(acao), alerta, valor)
        # Thickness only: a width of 600 must not highlight anything.
        self.assertFalse(addon.gaveta_desenho._medida_em_alerta(
            ('medida', 'objeto', 'ui_chapa_largura', "Width", 600.0)))
        r, g, b, a = addon.gaveta_desenho._cor_alerta_gaveta()
        self.assertGreater(r, max(g, b))

    def test_vizinhanca_gravada_por_uid(self):
        # Inserted presets gain .001 suffixes; name-based adjacency would point
        # to the wrong object.
        a = self.chapa()
        b = addon.chapas.nova_chapa('Vizinha', 600.0, 400.0, 18.0,
                             (600.0, 0.0, 0.0), (0.0, 0.0, 0.0),
                             bpy.context)
        bpy.context.view_layer.update()
        self.assertGreater(addon.chapas.detectar_adjacencia([a, b]), 0)
        self.assertEqual(a['adj_x_pos_uid'], b['chapa_uid'])
        # Rule v359: the single edge also preserves reverse fitting without duplicating
        # the record or losing UID identity.
        self.assertIsNone(addon.solda._vizinho_da_ponta(b, 'x_neg'))
        reversa = addon.solda.restricoes_adjacencia([b])[b]['x_neg']
        self.assertIs(reversa[0], a)
        # The name is also stored, but only as a log hint.
        self.assertEqual(a['adj_x_pos'], b.name)
        b.name = 'Vizinha renomeada.001'
        self.assertIs(addon.solda._vizinho_da_ponta(a, 'x_pos'), b)
        self.assertNotEqual(addon.chapas._garantir_uid(a), addon.chapas._garantir_uid(b))
        # Stable: another call does not generate a new UID.
        self.assertEqual(addon.chapas._garantir_uid(a), a['chapa_uid'])

    def test_guarda_de_reentrancia_existe(self):
        self.assertEqual(addon.chapas._ocupado, [False])

    def test_malha_modelada_nunca_e_substituida(self):
        # Without auto-regeneration, as requested, dimension changes on a modeled panel
        # stretch its mesh while preserving cutouts and holes at the same size
        # and distance from the nearest edge.
        obj = self.chapa(600.0, 400.0, 18.0)
        self.assertTrue(addon.chapas._malha_e_caixa(obj.data))
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        # A cut 50 mm from edge +X: a loop splitting the width.
        bmesh.ops.bisect_plane(
            bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
            plane_co=(0.25, 0, 0), plane_no=(1, 0, 0))
        bm.to_mesh(obj.data)
        bm.free()
        n = len(obj.data.vertices)
        self.assertGreater(n, 8)
        self.assertFalse(addon.chapas._malha_e_caixa(obj.data))
        obj.chapa_largura_mm = 1000.0          # +400: 200 on each side.
        xs = sorted({round(v.co.x, 6) for v in obj.data.vertices})
        self.assertEqual(len(obj.data.vertices), n)      # Nothing deleted.
        self.assertEqual(xs, [-0.5, 0.45, 0.5])          # Cut at 50 mm.
        self.assertAlmostEqual(obj.dimensions.x, 1.0, places=5)
        obj.chapa_espessura_mm = 70.0          # The same applies to free thickness.
        self.assertAlmostEqual(obj.dimensions.z, 0.070, places=5)
        self.assertEqual(len(obj.data.vertices), n)
        # The default box is still rebuilt normally.
        caixa = self.chapa(600.0, 400.0, 18.0)
        caixa.chapa_largura_mm = 800.0
        self.assertTrue(addon.chapas._malha_e_caixa(caixa.data))
        self.assertAlmostEqual(caixa.dimensions.x, 0.8, places=5)

    def test_sair_do_modo_edicao_preserva_o_que_foi_modelado(self):
        obj = self.chapa(600.0, 400.0, 18.0)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.bisect_plane(
            bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
            plane_co=(0.1, 0, 0), plane_no=(1, 0, 0))
        for v in bm.verts:             # And stretches side +X by 100 mm.
            if v.co.x > 0.2:
                v.co.x += 0.1
        bm.to_mesh(obj.data)
        bm.free()
        n = len(obj.data.vertices)
        addon.chapas._chapas_em_edicao.add(obj.name)
        addon.chapas.absorver_edicoes_de_malha()
        self.assertAlmostEqual(obj.chapa_largura_mm, 700.0, places=3)
        self.assertEqual(len(obj.data.vertices), n)      # The cut remains.

    def test_sair_do_modo_edicao_atualiza_as_medidas(self):
        # User screenshot: one side was stretched in Edit Mode, but the HUD outline,
        # which reads properties, retained the old dimension.
        obj = addon.chapas.nova_chapa('Esticada', 600.0, 400.0, 18.0,
                               (1000.0, 0.0, 0.0), (0.0, 0.0, 90.0),
                               bpy.context)
        intocada = self.chapa()
        bpy.context.view_layer.update()
        esquerda = min(addon.chapas._cantos(obj), key=lambda p: p.y)
        # Edit Mode: only local side +X moves 200 mm.
        for v in obj.data.vertices:
            if v.co.x > 0:
                v.co.x += 0.2
        for v in intocada.data.vertices:     # Changed, but without a transition.
            v.co.x += 0.1
        addon.chapas._chapas_em_edicao.add(obj.name)
        addon.chapas.absorver_edicoes_de_malha()
        bpy.context.view_layer.update()
        self.assertAlmostEqual(obj.chapa_largura_mm, 800.0, places=3)
        self.assertAlmostEqual(obj.chapa_comprimento_mm, 400.0, places=3)
        self.assertAlmostEqual(obj.chapa_espessura_mm, 18.0, places=3)
        # The part stays in place: the fixed side remains fixed, and the origin returns
        # to the box center, making the mesh symmetric again.
        xs = [v.co.x for v in obj.data.vertices]
        self.assertAlmostEqual(min(xs), -max(xs), places=5)
        cantos = addon.chapas._cantos(obj)
        self.assertAlmostEqual(min(p.y for p in cantos), esquerda.y, places=5)
        self.assertAlmostEqual(max(p.y for p in cantos),
                               esquerda.y + 0.8, places=5)
        # No transition means no change; off-center imports stay untouched.
        self.assertAlmostEqual(intocada.chapa_largura_mm, 600.0, places=3)
        self.assertEqual(addon.chapas._chapas_em_edicao, set())


class TestRegistro(unittest.TestCase):
    def test_toda_classe_bpy_entra_em_classes(self):
        registradas = {c.__name__ for c in addon.CLASSES}
        faltando = set(classes_do_modulo()) - registradas - NAO_REGISTRADAS
        self.assertFalse(faltando, "Class missing from CLASSES: %s -- every new Operator/Gizmo/Panel must be included in the tuple" % faltando)

    def test_classes_sem_duplicata(self):
        nomes = [c.__name__ for c in addon.CLASSES]
        self.assertEqual(len(nomes), len(set(nomes)))

    def test_idname_dos_operadores_segue_o_padrao(self):
        for classe in addon.CLASSES:
            if issubclass(classe, bpy.types.Operator):
                self.assertTrue(classe.bl_idname.startswith('object.cabinet_'),
                                "%s: bl_idname must be object.cabinet_<acao>"
                                % classe.__name__)

    def test_unregister_desfaz_tudo(self):
        addon.unregister()
        try:
            self.assertIsNone(addon.gaveta._handler_gaveta[0])
            self.assertEqual(addon.selecao._keymaps, [])
            for timer in (addon.gaveta._limitar_largura_gaveta,
                          addon.gaveta._configurar_gavetas,
                          addon.gaveta._reconectar_gavetas,
                          addon.gaveta._animar_realces,
                          addon.eventos.verificar_periodicamente):
                self.assertFalse(bpy.app.timers.is_registered(timer),
                                 "%s remained registered" % timer.__name__)
            self.assertNotIn(addon.chapas.ao_atualizar_depsgraph,
                             bpy.app.handlers.depsgraph_update_post)
        finally:
            addon.register()


class TestPacote(unittest.TestCase):
    """The add-on is a package with one module per area, as requested: a single 19,000-line file made every change cumbersome."""

    def test_todo_modulo_esta_na_ordem_de_carga(self):
        pasta = os.path.dirname(addon.__file__)
        from pathlib import Path
        raiz = Path(pasta)
        # Sector initializers only define package boundaries; every implementation
        # must still be explicitly loaded, including nested domain packages.
        setores = {'core', 'cabinetry', 'architecture', 'ui', 'integrations'}
        self.assertEqual({p.name for p in raiz.iterdir()
                          if p.is_dir() and (p/'__init__.py').is_file()}, setores,
                         'Unexpected root package escapes explicit loading')
        import ast
        for setor in setores:
            # Boundary packages are declarations, never a hidden second loader.
            arvore = ast.parse((raiz/setor/'__init__.py').read_text(encoding='utf-8'))
            self.assertTrue(all(isinstance(no, ast.Expr)
                                and isinstance(no.value, ast.Constant)
                                and isinstance(no.value.value, str) for no in arvore.body))
        arquivos = {str(p.relative_to(raiz)).replace('\\', '/')
                    for setor in setores for p in (raiz/setor).rglob('*.py')
                    if p != raiz/setor/'__init__.py'}
        carregados = {str(Path(m.__file__).relative_to(raiz)).replace('\\', '/')
                      for m in addon._MODULOS}
        self.assertEqual(arquivos, carregados)
        self.assertEqual({p.name for p in raiz.glob('*.py')}, {'__init__.py'})

    def test_apelidos_entre_modulos_estao_ligados(self):
        # _portas.x uses an alias linked at runtime by _ligar_modulos;
        # a forgotten None would fail only when called.
        nomes = {'_' + nome: m for nome, m in addon._MODULE_ALIASES.items()}
        for modulo in addon._MODULOS:
            for apelido, alvo in nomes.items():
                if apelido in vars(modulo):
                    self.assertIs(vars(modulo)[apelido], alvo,
                                  '%s.%s' % (modulo.__name__, apelido))

    def test_modulo_nao_importa_nome_solto_de_outro(self):
        # from .portas import x copies the name: patching addon.portas.x in a test
        # or reloading would not reach the other module.
        import ast
        for modulo in addon._MODULOS:
            with open(modulo.__file__, encoding='utf-8') as f:
                arvore = ast.parse(f.read())
            for no in ast.walk(arvore):
                if isinstance(no, ast.ImportFrom) and no.level:
                    self.assertIsNone(no.module, '%s: from .%s import ...'
                                      % (modulo.__name__, no.module))


addon.register()
carregar = unittest.defaultTestLoader.loadTestsFromTestCase
suite = unittest.TestSuite([carregar(c) for c in (
    TestArquiteturaDaGaveta, TestAlca, TestHigieneDeGPU, TestGridDeMedidas,
    TestListaSuspensaDaCascata,
    TestContratoDosWidgets, TestEstruturaDaChapa, TestRegistro,
    TestPacote)])
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError("Structure tests failed")
