"""Trava a ESTRUTURA do addon contra alteracao acidental.

Execute: blender --background --factory-startup --python-exit-code 1 \
    --python tests/test_estrutura_blender.py

Os outros arquivos de teste checam COMPORTAMENTO (a gaveta responde,
a porta encaixa). Este aqui checa DECISOES DE ARQUITETURA: coisas que
funcionam hoje e que uma refatoracao bem-intencionada quebraria sem
perceber. Cada falha aqui deve ser lida como "isto era de proposito;
confirme com o dono antes de mudar", nunca como "conserte o teste".

Ver DESIGN.md para o porque de cada decisao travada aqui.
"""
import inspect
import re
import os
import sys
import unittest

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon


# Vocabulario fechado das acoes de widget. `_widgets_gaveta` devolve
# tuplas (x, y, w, h, rotulo, acao) e `acao[0]` e' o verbo que
# `OBJECT_OT_interagir_gaveta` despacha. Verbo novo que nao esteja aqui
# e' quase sempre duplicata de um existente com outro nome.
VERBOS = frozenset({
    'aba', 'auto', 'biblioteca', 'chapa', 'item', 'medida', 'modo',
    'navegar', 'nome_objeto', 'operador', 'portas', 'preset',
    'rolar_nivel', 'separador', 'slider', 'wireframe', 'escolha',
    'ler_portas',
})

# Classes definidas no modulo que NAO entram em CLASSES de proposito.
# VIEW3D_PT_cabinet_creator e' o painel N legado: a gaveta o substituiu,
# mas ele ficou no arquivo como referencia. Nao registre sem pedir.
NAO_REGISTRADAS = frozenset({'VIEW3D_PT_cabinet_creator'})


def classes_do_modulo():
    bases = (bpy.types.Operator, bpy.types.Panel, bpy.types.Gizmo,
             bpy.types.GizmoGroup, bpy.types.AssetShelf,
             bpy.types.AddonPreferences)
    return {nome: obj for nome, obj in vars(addon).items()
            if inspect.isclass(obj) and issubclass(obj, bases)
            and obj.__module__ == addon.__name__}


class TestArquiteturaDaGaveta(unittest.TestCase):
    """A gaveta e' uma AREA, nao um overlay na viewport principal."""

    def test_gaveta_abre_como_area_dividida(self):
        # Migrar para overlay foi avaliado e RECUSADO: dividiria a
        # pilha de eventos, o estado de GPU e o canto superior esquerdo
        # com addons que tambem desenham na viewport (BlenderKit).
        # A area propria e' imune aos tres.
        fonte = inspect.getsource(addon.OBJECT_OT_alternar_gaveta.execute)
        self.assertIn('screen.area_split', fonte)
        self.assertIn('screen.area_close', fonte)
        self.assertEqual(addon._CHAVE_GAVETA, 'cabinet_gaveta_area')

    def test_area_e_localizada_por_ponteiro_na_screen(self):
        # Ponteiro de area nao sobrevive a recarga de .blend; por isso
        # existe _reconectar_gavetas. Trocar por busca "a primeira
        # VIEW_3D estreita" reabre o bug das areas fantasma.
        self.assertTrue(callable(addon._area_gaveta))
        self.assertTrue(callable(addon._reconectar_gavetas))
        fonte = inspect.getsource(addon._area_gaveta)
        self.assertIn('as_pointer()', fonte)
        self.assertIsNone(addon._area_gaveta(bpy.context.screen))

    def test_largura_e_corrigida_por_timer_nunca_por_modal(self):
        # Area.width e' somente leitura. O timer corrige a divisoria
        # DEPOIS do resize e pula janelas com modal ativo, para nunca
        # disputar evento com um operador do usuario.
        fonte = inspect.getsource(addon._limitar_largura_gaveta)
        self.assertIn('modal_operators', fonte)
        self.assertIn('screen.area_move', fonte)
        self.assertEqual(addon._LARGURA_MAX_GAVETA, 564)

    def test_desenho_e_um_handler_post_pixel(self):
        self.assertIsNotNone(addon._handler_gaveta[0])


class TestAlca(unittest.TestCase):
    """A alca e' um Gizmo com hit-test proprio, sem operador modal."""

    def test_alca_e_gizmo_com_test_select(self):
        self.assertTrue(issubclass(addon.VIEW3D_GT_alca_gaveta,
                                   bpy.types.Gizmo))
        self.assertTrue(hasattr(addon.VIEW3D_GT_alca_gaveta, 'test_select'))
        self.assertIn(addon.VIEW3D_GT_alca_gaveta, addon.CLASSES)
        ctx = type('C', (), {'region': type('R', (), {'height': 1000})()})()
        self.assertEqual(
            addon.VIEW3D_GT_alca_gaveta.test_select(None, ctx, (300, 300)), -1)

    def test_alca_nao_desenha_pelo_gizmo(self):
        # O desenho e' unico, no callback POST_PIXEL. Se o Gizmo voltar
        # a desenhar (BACKDROP/OUTLINE de GIZMO_GT_button_2d), a alca
        # aparece duas vezes, uma por cima da outra.
        fonte = inspect.getsource(addon.VIEW3D_GT_alca_gaveta.draw)
        self.assertIn('pass', fonte)
        self.assertNotIn('draw_options', fonte)

    def test_alternar_gaveta_nao_e_modal(self):
        # Alca via modal roubaria evento de outros addons na viewport.
        self.assertFalse(hasattr(addon.OBJECT_OT_alternar_gaveta, 'modal'))

    def test_geometria_da_alca_bate_com_o_desenho(self):
        # test_select e o retangulo desenhado no POST_PIXEL sao dois
        # trechos separados: se um mudar sem o outro, a alca fica com
        # area clicavel deslocada do que se ve.
        fonte = inspect.getsource(addon._desenhar_gaveta)
        self.assertIn('max(48, context.region.height * 0.12)', fonte)
        hit = inspect.getsource(addon.VIEW3D_GT_alca_gaveta.test_select)
        self.assertIn('max(48, context.region.height * 0.12)', hit)
        self.assertIn('0 <= x <= 26', hit)
        self.assertIn('abs(y - centro) <= 35', hit)


class TestHigieneDeGPU(unittest.TestCase):
    def test_blend_sempre_desligado_no_fim(self):
        # Estado de GPU vaza para quem desenhar depois -- inclusive
        # para outros addons, se um dia a gaveta dividir area com eles.
        # Nao da' para contar ALPHA e NONE (o ALPHA e' religado dentro
        # do laco de widgets); o que importa e' que TODO caminho de
        # saida desligue. Hoje sao dois: a alca e a gaveta.
        chamadas = re.findall(r"blend_set\('(\w+)'\)",
                              inspect.getsource(addon._desenhar_gaveta))
        self.assertEqual(chamadas[-1], 'NONE')
        self.assertEqual(chamadas.count('NONE'), 2,
                         'caminho de saida novo tem que fechar o blend')


class TestGridDeMedidas(unittest.TestCase):
    """A caixa na cena e o eixo que cada campo acende."""

    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        addon._realce_medida[0] = None

    def test_tabela_de_eixos_cobre_todos_os_rotulos(self):
        # Rotulo sem eixo nao acende nada e o usuario fica sem saber o
        # que vai mudar -- exatamente o problema que a grid resolve.
        # Espessura de modulo e' a unica ausencia proposital: nao e'
        # aresta da caixa.
        bpy.ops.mesh.primitive_cube_add()
        for modo, esperados in (('LIVRE', {'Largura', 'Altura',
                                           'Profundidade'}),
                                ('INDIVIDUAL', {'Largura', 'Altura',
                                                'Espessura'}),
                                ('GRUPO', {'Largura', 'Altura',
                                           'Profundidade'})):
            self.assertTrue(
                esperados <= set(addon.EIXOS_MEDIDA[modo]), modo)
        self.assertNotIn('Profundidade', addon.EIXOS_MEDIDA['INDIVIDUAL'])
        self.assertNotIn('Espessura', addon.EIXOS_MEDIDA['GRUPO'])

    def test_eixos_seguem_a_convencao_do_addon(self):
        # Modulo e objeto livre: Largura=X, Altura=Z, Profundidade=Y.
        for modo in ('GRUPO', 'LIVRE'):
            self.assertEqual(addon.EIXOS_MEDIDA[modo]['Largura'], 0)
            self.assertEqual(addon.EIXOS_MEDIDA[modo]['Altura'], 2)
            self.assertEqual(addon.EIXOS_MEDIDA[modo]['Profundidade'], 1)
        # Chapa: eixos LOCAIS, com a espessura no Z dela.
        self.assertEqual(addon.EIXOS_MEDIDA['INDIVIDUAL'],
                         {'Largura': 0, 'Altura': 1, 'Espessura': 2})

    def test_arestas_batem_com_a_indexacao_por_bits(self):
        # Cada eixo tem 4 arestas, e os dois cantos de uma aresta do
        # eixo `a` diferem exatamente no bit de `a`.
        vistos = set()
        for a, arestas in enumerate(addon.ARESTAS_EIXO):
            self.assertEqual(len(arestas), 4)
            for i, j in arestas:
                self.assertEqual(j - i, 1 << a)
                vistos.add((i, j))
        self.assertEqual(len(vistos), 12)

    def test_caixa_livre_envolve_o_objeto(self):
        bpy.ops.mesh.primitive_cube_add(size=2.0)
        bpy.context.object.location = (5.0, 0.0, 0.0)
        bpy.context.view_layer.update()
        cantos = addon._caixa_da_medida(bpy.context, 'LIVRE')
        self.assertEqual(len(cantos), 8)
        for a, esperado in enumerate((4.0, -1.0, -1.0)):
            self.assertAlmostEqual(min(c[a] for c in cantos), esperado,
                                   places=5)
        # a aresta do eixo 0 mede a largura
        i, j = addon.ARESTAS_EIXO[0][0]
        self.assertAlmostEqual((cantos[j] - cantos[i]).length, 2.0, places=5)

    def test_caixa_da_chapa_acompanha_a_rotacao(self):
        # Chapa girada: a Espessura continua sendo a aresta LOCAL Z,
        # nao a vertical do mundo. Caixa alinhada ao mundo acenderia
        # a aresta errada.
        obj = addon.nova_chapa('Girada', 600.0, 400.0, 18.0,
                               (0.0, 0.0, 0.0), (0.0, 90.0, 0.0),
                               bpy.context)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.context.view_layer.update()
        cantos = addon._caixa_da_medida(bpy.context, 'INDIVIDUAL')
        eixo = addon.EIXOS_MEDIDA['INDIVIDUAL']['Espessura']
        i, j = addon.ARESTAS_EIXO[eixo][0]
        aresta = cantos[j] - cantos[i]
        self.assertAlmostEqual(aresta.length, 0.018, places=5)
        # girada 90 graus em Y, a espessura deitou no eixo X do mundo
        self.assertAlmostEqual(abs(aresta.normalized().x), 1.0, places=4)
        self.assertEqual(obj.chapa_espessura_mm, 18.0)

    def test_sem_realce_nao_desenha(self):
        # A caixa so' aparece com o mouse num campo ou com ele em
        # edicao; fora disso a viewport fica limpa.
        self.assertIsNone(addon._realce_medida[0])
        addon._desenhar_grid_medidas()   # nao pode levantar

    def test_handler_do_grid_e_post_view(self):
        # POST_PIXEL desenharia em coordenada de tela, e a caixa vive
        # em coordenada de mundo, junto da cena.
        self.assertIsNotNone(addon._handler_grid[0])
        fonte = inspect.getsource(addon.register)
        self.assertIn("_desenhar_grid_medidas, (), 'WINDOW', 'POST_VIEW'",
                      fonte)

    def test_campo_e_gizmo_sem_modal(self):
        # Mesmo motivo da alca: hover e clique por Gizmo, nunca por
        # operador modal persistente.
        self.assertTrue(issubclass(addon.VIEW3D_GT_campo_gaveta,
                                   bpy.types.Gizmo))
        self.assertIn(addon.VIEW3D_GT_campo_gaveta, addon.CLASSES)
        self.assertIn('pass',
                      inspect.getsource(addon.VIEW3D_GT_campo_gaveta.draw))

    def test_glow_e_o_mesmo_da_alca(self):
        # "Glow igual o da alca": tem que ser a MESMA funcao, nao uma
        # copia que diverge na primeira alteracao.
        fonte = inspect.getsource(addon._desenhar_gaveta)
        self.assertGreaterEqual(fonte.count('_glow_gaveta('), 2)
        halo = inspect.getsource(addon._glow_gaveta)
        self.assertIn('((6, 0.025), (4, 0.045), (2, 0.07))', halo)

    def test_glow_liga_o_proprio_blend(self):
        # REGRESSAO: blf.draw deixa o estado de blend alterado, entao
        # o halo do SEGUNDO widget em diante saia opaco -- um bloco
        # branco por cima do texto (visto em Altura e Profundidade).
        # O halo nao pode depender de quem desenhou antes dele.
        halo = inspect.getsource(addon._glow_gaveta)
        self.assertIn("blend_set('ALPHA')", halo)
        self.assertLess(halo.index("blend_set('ALPHA')"),
                        halo.index('for margem'))

    def test_glow_vai_antes_do_corpo_do_botao(self):
        # Por cima, o halo lava o texto em vez de circundar o widget.
        fonte = inspect.getsource(addon._desenhar_gaveta)
        self.assertLess(fonte.index('_glow_gaveta(x, y, w, h, 4'),
                        fonte.index('_botao_gaveta(x, y, w, h, ativo=ativo'))

    def test_todo_botao_tem_chave_de_realce(self):
        # O glow vale para QUALQUER botao: todo verbo clicavel precisa
        # de uma chave, e so' a decoracao pode ficar sem.
        bpy.ops.mesh.primitive_cube_add()
        cena = bpy.context.scene
        cena.cabinet_aba = 'MODULOS'
        cena.chapa_bib_aberta = True
        cena.chapa_n1 = 'Armarios'
        sem_chave = set()
        for largura in (190, 320, 564):
            for _x, _y, _w, _h, _r, acao in addon._widgets_gaveta(
                    bpy.context, largura, 1200):
                if acao and addon._chave_widget(acao) is None:
                    sem_chave.add(acao[0])
        self.assertEqual(sem_chave - {'wireframe', 'separador',
                                      'nome_objeto', 'slider'}, set())

    def test_chaves_de_realce_nao_colidem(self):
        # Duas chaves iguais acenderiam os dois widgets juntos.
        bpy.ops.mesh.primitive_cube_add()
        cena = bpy.context.scene
        cena.cabinet_aba = 'MODULOS'
        cena.chapa_bib_aberta = True
        cena.chapa_n1 = 'Armarios'
        chaves = [addon._chave_widget(v[5]) for v in addon._widgets_gaveta(
            bpy.context, 320, 1200) if addon._chave_widget(v[5])]
        self.assertEqual(len(chaves), len(set(chaves)))

    def test_hit_test_poupa_o_disco_do_icone(self):
        # O gizmo do icone precisa continuar ganhando o pick em cima
        # dele, senao o tooltip some. O glow cobre os dois porque soma
        # os dois is_highlight.
        teste = addon.VIEW3D_GT_campo_gaveta.test_select
        giz = type('G', (), {'as_pointer': lambda self: 4242})()
        addon._campos_gaveta[4242] = (10, 10, 200, 40, (110, 30, 13))
        try:
            self.assertEqual(teste(giz, None, (20, 30)), 0)
            self.assertEqual(teste(giz, None, (110, 30)), -1)
            self.assertEqual(teste(giz, None, (300, 30)), -1)
        finally:
            addon._campos_gaveta.clear()


class TestCarrosselDeslizante(unittest.TestCase):
    """O carrossel anda como roleta em vez de trocar os nomes secamente."""

    CHAVE = 'cabinet_carrossel_1_None'

    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        cena = bpy.context.scene
        cena.cabinet_aba = 'MODULOS'
        cena.chapa_bib_aberta = True
        cena.chapa_n1 = ''
        addon._deslizes.clear()
        bpy.context.screen[self.CHAVE] = 0

    def tearDown(self):
        addon._deslizes.clear()
        bpy.context.screen[self.CHAVE] = 0

    def navegar(self, largura=320):
        return [v for v in addon._widgets_gaveta(bpy.context, largura, 1200)
                if v[5] and v[5][0] == 'navegar' and v[5][1] == 1]

    def test_parado_o_layout_e_o_mesmo_de_antes(self):
        # Sem transicao em curso, as posicoes tem que ser as inteiras
        # de sempre: nada de meia peca sobrando na tela em repouso.
        itens = self.navegar()
        self.assertTrue(itens)
        self.assertEqual(addon._deslizes[self.CHAVE][0],
                         addon._deslizes[self.CHAVE][1])
        largos = {round(v[2], 6) for v in itens}
        self.assertEqual(len(largos), 1)
        passo = round(itens[1][0] - itens[0][0], 6) if len(itens) > 1 else None
        if passo is not None:
            self.assertAlmostEqual(passo, largos.pop() + 4, places=5)

    def test_em_movimento_entra_uma_peca_a_mais(self):
        # A peca que surge na borda so' existe durante a transicao; e'
        # ela que da' a impressao de fila andando.
        parado = len(self.navegar())
        addon._deslizes[self.CHAVE] = [0.5, 1.0, 0.0]
        andando = self.navegar()
        self.assertEqual(len(andando), parado + 1)
        # e a fila esta' deslocada meio passo para a esquerda
        self.assertLess(andando[0][0], 12 + 24)

    def test_hit_test_acompanha_o_movimento(self):
        # O retangulo de clique sai do MESMO lugar que o desenho. Se o
        # desenho animasse sozinho, o usuario erraria o alvo em
        # movimento -- e o glow acenderia a peca errada.
        addon._deslizes[self.CHAVE] = [0.0, 1.0, 0.0]
        a = self.navegar()
        addon._deslizes[self.CHAVE] = [0.6, 1.0, 0.0]
        b = self.navegar()
        nome = lambda v: v[5][2]
        comum = set(map(nome, a)) & set(map(nome, b))
        self.assertTrue(comum)
        for valor in comum:
            xa = next(v[0] for v in a if nome(v) == valor)
            xb = next(v[0] for v in b if nome(v) == valor)
            self.assertLess(xb, xa)

    def test_indice_inteiro_continua_sendo_a_verdade(self):
        # O deslize e' so' visual: quem manda no conteudo e' o inteiro
        # guardado na screen, que clique, arraste e testes leem.
        todos = sorted(addon.ARVORE.keys(), key=str.casefold)
        bpy.context.screen[self.CHAVE] = 2
        addon._deslizes.clear()
        parados = [v[5][2] for v in self.navegar()]
        self.assertEqual(parados[0], todos[2])

        # No meio do caminho a fila mostra de ONDE veio, nao para onde
        # vai -- e' isso que se ve andando. O alvo e' que segue o
        # inteiro da screen.
        addon._deslizes[self.CHAVE] = [0.0, 2.0, 0.0]
        em_transito = [v[5][2] for v in self.navegar()]
        self.assertEqual(em_transito[0], todos[0])
        self.assertEqual(addon._deslizes[self.CHAVE][1], 2.0)

        # e ao terminar, para exatamente no que a screen manda
        addon._deslizes[self.CHAVE] = [2.0, 2.0, 0.0]
        self.assertEqual([v[5][2] for v in self.navegar()], parados)

    def test_deslizar_nao_anima_na_primeira_vez(self):
        # Abrir a biblioteca nao pode disparar uma roleta do nada.
        addon._deslizes.clear()
        self.assertEqual(addon._deslizar('novo', 3), 3.0)
        self.assertEqual(addon._deslizes['novo'][0],
                         addon._deslizes['novo'][1])

    def test_desenho_recorta_o_trilho(self):
        # Sem scissor a peca que entra apareceria por cima das setas.
        fonte = inspect.getsource(addon._desenhar_gaveta)
        self.assertIn('scissor_test_set(True)', fonte)
        self.assertIn('scissor_test_set(False)', fonte)
        self.assertIn("acao[0] == 'navegar'", fonte)


class TestContratoDosWidgets(unittest.TestCase):
    """_widgets_gaveta e' a fronteira entre layout e desenho."""

    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        cena = bpy.context.scene
        cena.cabinet_aba = 'MODULOS'
        cena.chapa_bib_aberta = True
        cena.chapa_n1 = 'Armarios'
        cena.chapa_n2 = 'Sala'
        cena.chapa_n3 = 'Inferiores'

    def todos(self):
        """Widgets de varios estados e larguras, achatados."""
        saida = []
        cena = bpy.context.scene
        for aba in ('MODULOS', 'PORTAS'):
            cena.cabinet_aba = aba
            for largura in (190, 320, 564):
                saida += addon._widgets_gaveta(bpy.context, largura, 1200)
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
        self.assertFalse(novos, 'verbo de widget novo: %s -- confirme que '
                                'nao e duplicata e acrescente a VERBOS' % novos)

    def test_nada_desenha_fora_da_gaveta(self):
        for largura in (190, 320, 564, 2056):
            for x, y, w, h, _r, _a in addon._widgets_gaveta(
                    bpy.context, largura, 1200):
                self.assertGreaterEqual(x, 0)
                self.assertLessEqual(x + w, min(largura - 12, 552) + 0.01)
                self.assertGreaterEqual(w, 0)
                self.assertGreaterEqual(h, 0)

    def test_largura_maxima_respeitada_em_tela_larga(self):
        # A gaveta para de crescer em 564 px: texto em coluna muito
        # larga fica ilegivel e a miniatura vira faixa.
        larguras = {w[0] + w[2] for w in
                    addon._widgets_gaveta(bpy.context, 2056, 1200)}
        self.assertLessEqual(max(larguras), addon._LARGURA_MAX_GAVETA - 12)


class TestEstruturaDaChapa(unittest.TestCase):
    """Invariantes do modulo basico. Quebrar isto invalida a biblioteca."""

    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)

    def chapa(self, larg=600.0, comp=400.0, esp=18.0):
        return addon.nova_chapa('Teste', larg, comp, esp,
                                (0.0, 0.0, 0.0), (0.0, 0.0, 0.0),
                                bpy.context)

    def test_marcadores_sao_id_props_e_nao_rna(self):
        # `MARCA_CHAPA in obj` so' funciona com ID prop. Se alguem
        # trocar por bpy.props, o teste `in` passa a dar False sempre
        # e a biblioteca inteira para de ser reconhecida.
        obj = self.chapa()
        self.assertIn(addon.MARCA_CHAPA, obj)
        rna = {p.identifier for p in obj.bl_rna.properties}
        for marca in (addon.MARCA_CHAPA, addon.MARCA_CONJUNTO,
                      addon.MARCA_PORTAS, addon.MARCA_FOLHA):
            self.assertNotIn(marca, rna)

    def test_nomes_gravados_nos_presets_nao_mudam(self):
        # Estes literais estao dentro dos .blend da biblioteca.
        self.assertEqual(addon.MARCA_CHAPA, 'eh_chapa')
        self.assertEqual(addon.MARCA_CONJUNTO, 'eh_conjunto_chapa')
        self.assertEqual(addon.MARCA_PORTAS, 'eh_grupo_portas')
        self.assertEqual(addon.MARCA_FOLHA, 'eh_folha_porta')

    def test_eixos_locais_x_largura_y_comprimento_z_espessura(self):
        obj = self.chapa(600.0, 400.0, 18.0)
        self.assertAlmostEqual(obj.dimensions.x, 0.6, places=5)
        self.assertAlmostEqual(obj.dimensions.y, 0.4, places=5)
        self.assertAlmostEqual(obj.dimensions.z, 0.018, places=5)

    def test_escala_vira_medida_e_z_e_descartado(self):
        obj = self.chapa(600.0, 400.0, 18.0)
        obj.scale = (2.0, 0.5, 7.0)
        addon.normalizar_chapas([obj])
        bpy.context.view_layer.update()
        self.assertAlmostEqual(obj.chapa_largura_mm, 1200.0, places=3)
        self.assertAlmostEqual(obj.chapa_comprimento_mm, 200.0, places=3)
        self.assertAlmostEqual(obj.chapa_espessura_mm, 18.0, places=3)
        for eixo in obj.scale:
            self.assertAlmostEqual(eixo, 1.0, places=5)

    def test_espessura_arredonda_para_as_permitidas(self):
        self.assertEqual(addon.ESPESSURAS_PERMITIDAS, [15.0, 18.0, 20.0, 30.0])
        obj = self.chapa()
        for pedido, esperado in ((16.0, 15.0), (19.0, 18.0),
                                 (26.0, 30.0), (999.0, 30.0)):
            obj.chapa_espessura_mm = pedido
            self.assertEqual(obj.chapa_espessura_mm, esperado)

    def test_vizinhanca_gravada_por_uid(self):
        # Preset inserido ganha sufixo .001; por nome a adjacencia
        # apontaria para o objeto errado.
        a = self.chapa()
        b = addon.nova_chapa('Vizinha', 600.0, 400.0, 18.0,
                             (600.0, 0.0, 0.0), (0.0, 0.0, 0.0),
                             bpy.context)
        bpy.context.view_layer.update()
        self.assertGreater(addon.detectar_adjacencia([a, b]), 0)
        self.assertEqual(a['adj_x_pos_uid'], b['chapa_uid'])
        self.assertEqual(b['adj_x_neg_uid'], a['chapa_uid'])
        # o nome tambem e' gravado, mas so' como pista para o log
        self.assertEqual(a['adj_x_pos'], b.name)
        self.assertNotEqual(addon._garantir_uid(a), addon._garantir_uid(b))
        # e' estavel: chamar de novo nao gera outro uid
        self.assertEqual(addon._garantir_uid(a), a['chapa_uid'])

    def test_guarda_de_reentrancia_existe(self):
        self.assertEqual(addon._ocupado, [False])


class TestRegistro(unittest.TestCase):
    def test_toda_classe_bpy_entra_em_classes(self):
        registradas = {c.__name__ for c in addon.CLASSES}
        faltando = set(classes_do_modulo()) - registradas - NAO_REGISTRADAS
        self.assertFalse(faltando, 'classe fora de CLASSES: %s -- todo '
                                   'Operator/Gizmo/Panel novo precisa entrar '
                                   'na tupla' % faltando)

    def test_classes_sem_duplicata(self):
        nomes = [c.__name__ for c in addon.CLASSES]
        self.assertEqual(len(nomes), len(set(nomes)))

    def test_idname_dos_operadores_segue_o_padrao(self):
        for classe in addon.CLASSES:
            if issubclass(classe, bpy.types.Operator):
                self.assertTrue(classe.bl_idname.startswith('object.cabinet_'),
                                '%s: bl_idname deve ser object.cabinet_<acao>'
                                % classe.__name__)

    def test_unregister_desfaz_tudo(self):
        addon.unregister()
        try:
            self.assertIsNone(addon._handler_gaveta[0])
            self.assertEqual(addon._keymaps, [])
            for timer in (addon._limitar_largura_gaveta,
                          addon._configurar_gavetas,
                          addon._reconectar_gavetas,
                          addon._animar_realces,
                          addon.verificar_periodicamente):
                self.assertFalse(bpy.app.timers.is_registered(timer),
                                 '%s continuou registrado' % timer.__name__)
            self.assertNotIn(addon.ao_atualizar_depsgraph,
                             bpy.app.handlers.depsgraph_update_post)
        finally:
            addon.register()


addon.register()
carregar = unittest.defaultTestLoader.loadTestsFromTestCase
suite = unittest.TestSuite([carregar(c) for c in (
    TestArquiteturaDaGaveta, TestAlca, TestHigieneDeGPU, TestGridDeMedidas,
    TestCarrosselDeslizante,
    TestContratoDosWidgets, TestEstruturaDaChapa, TestRegistro)])
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de estrutura')
