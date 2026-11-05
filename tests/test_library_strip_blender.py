"""Layout, catalogo e cache da faixa horizontal, sem gravar biblioteca real."""
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock
import bpy
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import cabinet_creator as addon
F = addon.biblioteca_faixa
PASTA = tempfile.mkdtemp(prefix='cabinet_faixa_')
addon.opcoes._pasta_addon = lambda: PASTA
addon.biblioteca.pasta_biblioteca = lambda: PASTA


class TestFaixa(unittest.TestCase):
    def setUp(self):
        F.invalidar()
        bpy.context.scene.cabinet_bib_modo = 'MODULOS'
        addon.biblioteca.definir_trilha(bpy.context.scene, ('Armarios','Cozinha','Cantos'))
        self.ctx = SimpleNamespace(scene=bpy.context.scene, screen={},
                                  preferences=bpy.context.preferences)
        addon.perguntas._pergunta_atual[0] = None
        self.indice = [dict(nome='Canto %05d' % i, arquivo='%d.blend' % i,
                            pasta=PASTA, niveis=['Armarios','Cozinha','Cantos'])
                       for i in range(10000)]
        self.patches = [patch.object(addon.biblioteca, 'indice_completo', return_value=self.indice),
                        patch.object(addon.biblioteca, 'itens_de_fabrica', return_value=[])]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        addon.perguntas._pergunta_atual[0] = None
        bpy.context.screen.pop(F.CHAVE_LAYOUT, None)

    def test_catalogo_preserva_niveis_profundos(self):
        self.indice[:] = [dict(nome='Item', arquivo='item.blend', pasta=PASTA,
                              niveis=['A','B','C','D','E','F'])]
        addon.biblioteca.definir_trilha(self.ctx.scene, ('A','B','C','D','E','F'))
        linhas, itens, _prefixo = F.catalogo(self.ctx)
        self.assertEqual(len(linhas), 6)
        self.assertEqual(len(itens), 1)

    def test_so_itens_visiveis_viram_widgets(self):
        fake = SimpleNamespace(data=SimpleNamespace(libraries=SimpleNamespace(
            load=lambda *a, **kw: self.fail('abriu blend'))))
        with patch.object(F, 'bpy', fake):
            widgets = F.widgets(self.ctx, 1600, 240)
        fotos = [v for v in widgets if v[5] and v[5][0] == 'preset']
        self.assertTrue(1 < len(fotos) < 25)
        self.assertEqual(len({round(v[1], 3) for v in fotos}), 1)
        seta = next(v[5] for v in widgets if v[5] and v[5][0] == 'rolar_nivel'
                    and 'faixa_itens' in v[5][1])
        self.ctx.screen[seta[1]] = 50
        outros = [v for v in F.widgets(self.ctx, 1600, 240) if v[5] and v[5][0] == 'preset']
        self.assertEqual(outros[0][5][1]['nome'], 'Canto 00050')

    def test_botao_assets_descontinuado(self):
        # Pedido do usuario: o botao "Assets" (prateleira nativa) saiu da
        # faixa e do menu; o operador dele nao existe mais.
        operadores = {v[5][1] for v in F.widgets(self.ctx, 1600, 240)
                      if v[5] and v[5][0] == 'operador'}
        self.assertTrue(operadores)
        self.assertNotIn('object.cabinet_prateleira', operadores)
        for botoes in addon.gaveta.BOTOES_BIBLIOTECA.values():
            self.assertNotIn('object.cabinet_prateleira', [op for _n, op in botoes])
        self.assertFalse(hasattr(bpy.types, 'OBJECT_OT_cabinet_prateleira'))
        self.assertFalse(hasattr(addon.biblioteca, 'OBJECT_OT_prateleira'))

    def test_lugar_da_biblioteca_faixa_ou_menu(self):
        tela = bpy.context.screen
        tela.pop(F.CHAVE_LUGAR, None)
        # padrao (pedido do usuario): na lateral esquerda, dentro do menu
        self.assertEqual(addon.opcoes.OPCOES_INTERNAS['biblioteca_lugar'], 'MENU')
        self.assertEqual(addon.opcoes.CabinetCreatorPreferences.__annotations__[
            'biblioteca_lugar'].keywords['default'], 'MENU')
        self.assertTrue(F.acoplada(tela))
        self.assertIn(F.OBJECT_OT_lugar_biblioteca, addon.CLASSES)
        # O botao: no cabecalho da faixa e no pe' da biblioteca do menu.
        lugar = lambda ws: [v for v in ws if v[5] == ('operador', F.OP_LUGAR)]
        faixa = F.widgets(self.ctx, 1600, 240)
        self.assertEqual(len(lugar(faixa)), 1)
        ferramentas = [v for v in faixa if v[5] and v[5][0] == 'operador']
        self.assertFalse([(a, b) for i, a in enumerate(ferramentas) for b in ferramentas[i + 1:]
                          if a[0] < b[0] + b[2] and b[0] < a[0] + a[2]])
        self.assertEqual(len(lugar(addon.gaveta._widgets_gaveta(bpy.context, 320, 900))), 1)
        tela[F.CHAVE_LAYOUT] = 2
        self.assertFalse(lugar(addon.gaveta._widgets_gaveta(bpy.context, 320, 900)))
        try:
            # O clique so' agenda: fechar a area que atende o clique a
            # liberaria debaixo do operador. A troca vem no timer.
            with patch.object(F, '_trocar_agora') as trocar:
                self.assertEqual(bpy.ops.object.cabinet_lugar_biblioteca(), {'FINISHED'})
                trocar.assert_not_called()
                self.assertIn(tela.name, F._menus_pendentes[0])
                self.assertTrue(bpy.app.timers.is_registered(F._abrir_menus_pendentes))
                self.assertIsNone(F._abrir_menus_pendentes())
                trocar.assert_called_once()
            # Escolhido o menu, reconectar nao o migra mais para a faixa.
            tela[F.CHAVE_LAYOUT] = 1
            for lugar_escolhido, migra in (('MENU', False), ('FAIXA', True)):
                F.definir_lugar(lugar_escolhido, tela)
                self.assertEqual(F.acoplada(tela), lugar_escolhido == 'MENU')
                with patch.object(F, 'abrir') as abrir, \
                     patch.object(addon.gaveta, '_area_gaveta',
                                  return_value=SimpleNamespace(type='VIEW_3D', x=0, y=0, width=10, height=10)), \
                     patch.object(addon.editor, 'configurar'):
                    addon.gaveta._reconectar_gavetas()
                self.assertEqual(abrir.called, migra, lugar_escolhido)
        finally:
            tela.pop(F.CHAVE_LUGAR, None)
            for nome, valor in addon.opcoes.OPCOES_INTERNAS.items():
                addon.opcoes._definir_opcao(nome, valor)
            F.esquecer()
        self.assertFalse(F._menus_pendentes[0])
        self.assertFalse(bpy.app.timers.is_registered(F._abrir_menus_pendentes))

    def test_lugar_escolhido_vale_para_todo_arquivo(self):
        # Pedido do usuario: lembrar a escolha do lugar da biblioteca. Ela
        # ficava so' na screen do arquivo; agora fica nas preferencias.
        O = addon.opcoes
        tela = bpy.context.screen
        try:
            for nome, valor in O.OPCOES_INTERNAS.items():
                O._definir_opcao(nome, valor)
            # screen de arquivo antigo marcada: vira a preferencia, uma vez
            tela[F.CHAVE_LUGAR] = 'MENU'
            self.assertTrue(F.acoplada(tela))
            self.assertEqual(O._opcao('biblioteca_lugar'), 'MENU')
            self.assertTrue(O._opcao('biblioteca_lugar_definido'))
            # outro arquivo, screen sem marca: segue a escolha
            self.assertTrue(F.acoplada({'outra': 1}))
            # o botao troca o que esta' aberto e grava na preferencia
            F.definir_lugar('FAIXA', tela)
            cena = SimpleNamespace(as_pointer=lambda: 1)
            with patch.object(F, 'viewport', return_value=cena),                  patch.object(F, 'area_da_faixa', return_value=None),                  patch.object(addon.gaveta, '_area_gaveta', return_value=None):
                F._trocar_agora(bpy.context.window, tela)
            self.assertEqual(O._opcao('biblioteca_lugar'), 'MENU')
            self.assertEqual(tela[F.CHAVE_LUGAR], 'MENU')
            # screen antiga marcada nao desfaz mais a escolha feita
            F.definir_lugar('FAIXA')
            self.assertFalse(F.acoplada({F.CHAVE_LUGAR: 'MENU'}))
        finally:
            tela.pop(F.CHAVE_LUGAR, None)
            for nome, valor in O.OPCOES_INTERNAS.items():
                O._definir_opcao(nome, valor)
            F.esquecer()

    def test_menu_novo_nao_tem_biblioteca_nem_divisoria(self):
        bpy.context.screen[F.CHAVE_LAYOUT] = 2
        widgets = addon.gaveta._widgets_gaveta(bpy.context, 480, 900)
        self.assertFalse(any(v[5] and v[5][0] in
                             ('preset','material','biblioteca','divisa') for v in widgets))

    def test_miniaturas_crescem_com_a_area_sem_ultrapassar_altura_ou_largura(self):
        self.ctx.preferences = SimpleNamespace(system=SimpleNamespace(ui_scale=1))
        self.ctx.scene.chapa_tam_bloco = 5
        caminho = tuple(addon.biblioteca.trilha_da_cena(self.ctx.scene))
        def fotos(largura, altura):
            return [v for v in F.widgets(self.ctx, largura, altura) if v[5] and v[5][0] == 'preset']
        pequenas = fotos(2823, 180)
        grandes = fotos(2823, 718)
        self.assertGreater(grandes[0][2], pequenas[0][2] * 4)
        self.assertLess(len(grandes), len(pequenas))
        self.assertEqual(len({v[1] for v in grandes}), 1)
        for largura, altura in ((2823, 718), (400, 718), (700, 100), (1000, 180)):
            with self.subTest(largura=largura, altura=altura):
                atuais = fotos(largura, altura)
                self.assertTrue(atuais)
                self.assertTrue(all(v[0] >= 0 and v[1] >= 0
                    and v[0] + v[2] <= largura + .01 and v[1] + v[3] <= altura + .01
                    for v in atuais))
        self.assertEqual(self.ctx.scene.chapa_tam_bloco, 5)
        self.assertEqual(tuple(addon.biblioteca.trilha_da_cena(self.ctx.scene)), caminho)

    def test_cache_de_fotos_tem_orcamento_de_memoria(self):
        cache = addon.gaveta._fotos_gaveta
        antigo = dict(cache)
        cache.clear()
        try:
            with patch.object(addon.gaveta, 'LIMITE_BYTES_FOTOS', 1024):
                for i in range(10):
                    addon.gaveta._guardar_foto_gaveta(str(i), (0, None, None, 8, 8))
                self.assertEqual(list(cache), ['6', '7', '8', '9'])
        finally:
            cache.clear()
            cache.update(antigo)

    def test_materiais_mantem_esfera_e_edicao_sem_pintar_no_layout(self):
        self.ctx.scene.cabinet_bib_modo = 'MATERIAIS'
        self.ctx.scene.cabinet_mat_n1 = 'MDF'
        self.ctx.scene.cabinet_mat_n2 = 'LisOs'
        self.ctx.scene.cabinet_mat_n3 = ''
        it = dict(nome='Branco', chave='branco', n1='MDF', n2='LisOs', n3='', cor=[1,1,1,1])
        with patch.object(addon.materiais, 'ler_materiais', return_value=[it]):
            widgets = F.widgets(self.ctx, 1000, 240)
        self.assertEqual(sum(v[5][0] == 'material' for v in widgets if v[5]), 1)
        self.assertEqual(sum(v[5][0] == 'material_item' for v in widgets if v[5]), 2)

    def test_pergunta_respostas_ficam_na_faixa(self):
        addon.perguntas._pergunta_atual[0] = dict(biblioteca=True, texto='Pintar?',
            opcoes=[('Sim','','',{}),('Nao','','',{})])
        widgets = F.widgets(self.ctx, 1000, 240)
        caixas = [v for v in widgets if v[5] and v[5][0] in ('pergunta','resposta')]
        self.assertEqual(len(caixas), 3)
        self.assertTrue(all(v[1] >= 0 and v[1] + v[3] <= 240 for v in caixas))

    def test_recolhida_mantem_botao_para_expandir(self):
        self.ctx.screen[F.CHAVE_RECOLHIDA] = 1
        widgets = F.widgets(self.ctx, 1000, 42)
        self.assertEqual(len(widgets), 3)
        self.assertEqual(widgets[-1][4], 'Expandir')
        self.assertIn(F.OBJECT_OT_recolher_biblioteca, addon.CLASSES)

    def test_layout_nao_excede_largura_nas_escalas(self):
        for escala in (1.0, 1.5, 2.0):
            self.ctx.preferences = SimpleNamespace(system=SimpleNamespace(ui_scale=escala))
            for w in (700, 1400, 2000):
                widgets = F.widgets(self.ctx, w, 240 * escala)
                self.assertTrue(all(0 <= v[0] and v[0] + v[2] <= w + 0.1 for v in widgets))

    def test_redesenho_reusa_indice_e_invalidacao_rele(self):
        leitor = addon.biblioteca.indice_completo
        F.catalogo(self.ctx)
        for _ in range(100):
            F.widgets(self.ctx, 1600, 240)
        self.assertEqual(leitor.call_count, 1)
        F.invalidar()
        F.catalogo(self.ctx)
        self.assertEqual(leitor.call_count, 2)

    def test_caminho_profundo_mantem_fotos_e_shift_roda_mostra_pais(self):
        caminho = tuple('Nivel %d' % i for i in range(1, 15))
        self.indice[:] = [dict(nome='Item', arquivo='item.blend', pasta=PASTA,
                              niveis=list(caminho))]
        addon.biblioteca.definir_trilha(self.ctx.scene, caminho)
        self.ctx.region = SimpleNamespace(width=1000, height=180)
        self.ctx.area = SimpleNamespace(tag_redraw=lambda: None)
        antes = F.widgets(self.ctx, 1000, 180)
        foto = next(v for v in antes if v[5] and v[5][0] == 'preset')
        self.assertGreaterEqual(foto[1], 0)
        visiveis = [v[5][1] for v in antes if v[5] and v[5][0] == 'navegar']
        self.assertIn(14, visiveis)
        F.rolar(self.ctx, SimpleNamespace(type='WHEELUPMOUSE', shift=True, mouse_region_y=180))
        depois = [v[5][1] for v in F.widgets(self.ctx, 1000, 180) if v[5] and v[5][0] == 'navegar']
        self.assertLess(min(n for n in depois if n > 1), min(n for n in visiveis if n > 1))
        self.assertNotIn(14, depois)

    def test_chaves_de_rolagem_cabem_em_idproperty_mesmo_com_nome_longo(self):
        caminho = ('Armarios', 'Ambiente ' * 20, 'Categoria ' * 20)
        self.indice[:] = [dict(nome='Item', arquivo='item.blend', pasta=PASTA, niveis=list(caminho))]
        addon.biblioteca.definir_trilha(self.ctx.scene, caminho)
        for v in F.widgets(self.ctx, 1000, 240):
            acao = v[5]
            if acao and acao[0] in ('navegar', 'rolar_nivel'):
                chave = acao[3] if acao[0] == 'navegar' else acao[1]
                self.assertLessEqual(len(chave.encode('utf-8')), 63)
                bpy.context.screen[chave] = 1
                bpy.context.screen.pop(chave, None)

    def test_muitas_respostas_rolam_sem_perder_a_ultima(self):
        self.ctx.region = SimpleNamespace(width=1000, height=240)
        self.ctx.area = SimpleNamespace(tag_redraw=lambda: None)
        addon.perguntas._pergunta_atual[0] = dict(biblioteca=True, texto='Comodo?',
            opcoes=[('Comodo %d' % i, '', '', {}) for i in range(200)])
        for _ in range(50):
            F.rolar(self.ctx, SimpleNamespace(type='WHEELDOWNMOUSE', shift=False, mouse_region_y=90))
        respostas = [v[5][1] for v in F.interativos(self.ctx) if v[5] and v[5][0] == 'resposta']
        self.assertIn(199, respostas)

    def test_categorias_compactas_e_modulos_sem_linha_de_botoes(self):
        self.ctx.preferences = SimpleNamespace(system=SimpleNamespace(ui_scale=1))
        widgets = F.widgets(self.ctx, 1000, 180)
        categorias = [v for v in widgets if v[5] and v[5][0] == 'navegar']
        self.assertTrue(all(v[3] == 18 for v in categorias))
        alturas = sorted({v[1] for v in categorias})
        self.assertTrue(all(b - a == 20 for a, b in zip(alturas, alturas[1:])))
        self.assertFalse(any(v[5] and v[5][0] == 'item' for v in widgets))
        fotos = [v for v in widgets if v[5] and v[5][0] == 'preset']
        self.assertTrue(all(v[1] >= 0 for v in fotos))
        self.assertLess(categorias[-1][2], 58)

    def test_setas_de_categorias_so_aparecem_com_conteudo_oculto(self):
        def linha(largura, nomes):
            itens = []
            F._linha(self.ctx, itens, 6, 100, largura, nomes, 1, '')
            return itens
        # 3 botoes de 32 + 2 intervalos de 2: a borda exata ja' cabe.
        itens = linha(100, ['A', 'B', 'C'])
        self.assertFalse(any(v[5][0] == 'rolar_nivel' for v in itens))
        self.assertEqual(itens[0][0], 6)
        itens = linha(99, ['A', 'B', 'C'])
        seta = next(v[5] for v in itens if v[5][0] == 'rolar_nivel')
        self.assertEqual(seta[2], 1)
        self.ctx.screen[seta[1]] = seta[3]
        fim = linha(99, ['A', 'B', 'C'])
        self.assertEqual([v[5][2] for v in fim if v[5][0] == 'rolar_nivel'], [-1])
        self.assertEqual([v[4] for v in fim if v[5][0] == 'navegar'], ['C'])
        self.assertFalse(any(v[5][0] == 'rolar_nivel' for v in linha(100, ['A', 'B', 'C'])))
        self.ctx.screen.clear()
        nomes = ['A', 'B', 'C', 'D', 'Extremidade muito longa']
        itens = linha(100, nomes)
        seta = next(v[5] for v in itens if v[5][0] == 'rolar_nivel')
        self.ctx.screen[seta[1]] = seta[3]
        self.assertIn(nomes[-1], [v[4] for v in linha(100, nomes) if v[5][0] == 'navegar'])

    def test_faixa_baixa_alinha_niveis_com_separacao_e_fotos_acessiveis(self):
        self.indice[:] = [dict(nome='Item', arquivo='item.blend', pasta=PASTA,
                              niveis=['A', 'B', 'C', 'D'])]
        addon.biblioteca.definir_trilha(self.ctx.scene, ('A', 'B', 'C', 'D'))
        for escala in (1, 1.5, 2):
            self.ctx.preferences = SimpleNamespace(system=SimpleNamespace(ui_scale=escala))
            for altura in (100, 120, 150):
                widgets = F.widgets(self.ctx, 1000 * escala, altura * escala)
                grupos = [v for v in widgets if v[5] and v[5][0] == 'navegar' and v[5][1] > 1]
                self.assertEqual({v[5][1] for v in grupos}, {2, 3, 4})
                self.assertEqual(len({v[1] for v in grupos}), 1)
                for a, b in zip(grupos, grupos[1:]):
                    self.assertGreaterEqual(b[0] - (a[0] + a[2]), F.INTERVALO_NIVEIS * escala)
                self.assertEqual(sum(v[5] == ('separador', 'biblioteca') for v in widgets), 4)
                self.assertTrue(any(v[5] and v[5][0] == 'preset' for v in widgets))
                self.assertTrue(all(0 <= v[0] and v[0] + v[2] <= 1000 * escala + .01
                                    and 0 <= v[1] and v[1] + v[3] <= altura * escala for v in widgets))
        self.ctx.preferences = SimpleNamespace(system=SimpleNamespace(ui_scale=1))
        alto = F.widgets(self.ctx, 1000, 180)
        self.assertEqual(len({v[1] for v in alto if v[5] and v[5][0] == 'navegar'}), 1)

    def test_todos_os_grupos_incluindo_modos_tem_caixa_e_divisoria_na_mesma_linha(self):
        self.ctx.scene.cabinet_mat_n1 = 'MDF'
        self.ctx.scene.cabinet_mat_n2 = 'Lisos'
        self.ctx.scene.cabinet_mat_n3 = ''
        materiais = patch.object(addon.materiais, 'ler_materiais', return_value=[
            dict(nome='Branco', chave='branco', n1='MDF', n2='Lisos', n3='', cor=[1, 1, 1, 1])])
        materiais.start()
        self.addCleanup(materiais.stop)
        self.indice[:] = [dict(nome='Item', arquivo='item.blend', pasta=PASTA,
                              niveis=['Armarios', 'Cozinha', 'Baixos', 'Cantos'])]
        addon.biblioteca.definir_trilha(self.ctx.scene, ('Armarios', 'Cozinha', 'Baixos', 'Cantos'))
        for modo in ('MODULOS', 'MATERIAIS'):
            self.ctx.scene.cabinet_bib_modo = modo
            for altura in (100, 180, 320):
                with self.subTest(modo=modo, altura=altura):
                    itens = F.widgets(self.ctx, 1600, altura)
                    caixas = [v for v in itens if F.caixa_categoria(v[5])]
                    self.assertEqual(len(caixas), 5 if modo == 'MODULOS' else 3)
                    botoes = [v for v in itens if v[5] and v[5][0] in ('biblioteca', 'navegar')]
                    self.assertEqual(len({v[1] for v in botoes}), 1)
                    for botao in botoes:
                        self.assertEqual(sum(botao[:4] in F.retangulos_filhos(c, itens) for c in caixas), 1)
                    separadores = [v for v in itens if v[5] == ('separador', 'biblioteca')]
                    self.assertEqual(len(separadores), len(caixas) - 1)
                    for antes, separador, depois in zip(caixas, separadores, caixas[1:]):
                        self.assertLessEqual(antes[0] + antes[2], separador[0])
                        self.assertLessEqual(separador[0] + separador[2], depois[0])

    def test_hover_de_aba_realca_so_a_caixa_daquela_categoria(self):
        itens = F.widgets(self.ctx, 1600, 180)
        chave = addon.gaveta_desenho._chave_widget
        caixas = [v for v in itens if F.caixa_categoria(v[5])]
        for caixa in caixas:
            filhos = F.retangulos_filhos(caixa, itens)
            filho = next(v for v in itens if v[:4] in filhos and chave(v[5]))
            acesos = {chave(filho[5])}
            F.realces_das_categorias(itens, acesos)
            self.assertEqual({chave(c[5]) for c in caixas if chave(c[5]) in acesos}, {chave(caixa[5])})
            vazio = {chave(caixa[5])}
            F.realces_das_categorias(itens, vazio)
            self.assertNotIn(chave(caixa[5]), vazio)

    def test_caixa_tem_hover_no_espaco_vazio_sem_roubar_o_hit_test_da_aba(self):
        itens = F.widgets(self.ctx, 1600, 180)
        caixa = next(v for v in itens if F.caixa_categoria(v[5]))
        filhos = F.retangulos_filhos(caixa, itens)
        gizmo = SimpleNamespace(as_pointer=lambda: 4242)
        addon.hud._campos_gaveta[4242] = (*caixa[:4], None, filhos)
        try:
            teste = addon.gaveta_desenho.VIEW3D_GT_campo_gaveta.test_select
            self.assertEqual(teste(gizmo, None, (caixa[0] + 1, caixa[1] + 1)), 0)
            for x, y, w, h in filhos:
                self.assertEqual(teste(gizmo, None, (x + w / 2, y + h / 2)), -1)
        finally:
            addon.hud._campos_gaveta.pop(4242, None)
        self.ctx.region = SimpleNamespace(width=1600, height=180)
        interativos = F.interativos(self.ctx)
        self.assertGreater(interativos.index(caixa), max(interativos.index(v) for v in itens if v[:4] in filhos))

    def test_roda_no_padding_da_caixa_rola_apenas_seu_nivel(self):
        self.ctx.preferences = SimpleNamespace(system=SimpleNamespace(ui_scale=1))
        self.ctx.region = SimpleNamespace(width=700, height=180)
        self.ctx.area = SimpleNamespace(tag_redraw=lambda: None)
        niveis = [(1, ['Armarios'], 'Armarios', None),
                  (2, ['Ambiente %02d' % i for i in range(30)], '', 'Armarios'),
                  (3, ['Categoria %02d' % i for i in range(30)], '', ('Armarios', 'Cozinha'))]
        with patch.object(F, 'catalogo', return_value=(niveis, [], 'cabinet_carrossel')):
            itens = F.widgets(self.ctx, 700, 180)
            alvo = next(v for v in itens if v[5] and v[5][0] == 'navegar' and v[5][1] == 3)
            caixa = next(v for v in itens if F.caixa_categoria(v[5]) and alvo[:4] in F.retangulos_filhos(v, itens))
            vizinho = next(v for v in itens if v[5] and v[5][0] == 'navegar' and v[5][1] == 2)
            F.rolar(self.ctx, SimpleNamespace(type='WHEELDOWNMOUSE', shift=False,
                mouse_region_x=caixa[0] + 1, mouse_region_y=caixa[1] + 1))
            self.assertEqual(self.ctx.screen[alvo[5][3]], 1)
            self.assertEqual(self.ctx.screen.get(vizinho[5][3], 0), 0)

    def test_roda_em_subcategoria_horizontal_nao_rola_o_nivel_vizinho(self):
        self.ctx.preferences = SimpleNamespace(system=SimpleNamespace(ui_scale=1))
        self.ctx.region = SimpleNamespace(width=700, height=120)
        self.ctx.area = SimpleNamespace(tag_redraw=lambda: None)
        niveis = [(1, ['Armarios'], 'Armarios', None),
                  (2, ['Ambiente %02d' % i for i in range(30)], 'Ambiente 00', 'Armarios'),
                  (3, ['Categoria %02d' % i for i in range(30)], 'Categoria 00', ('Armarios', 'Ambiente 00'))]
        with patch.object(F, 'catalogo', return_value=(niveis, [], 'cabinet_carrossel')):
            widgets = F.widgets(self.ctx, 700, 120)
            grupo = next(v for v in widgets if v[5] and v[5][0] == 'navegar' and v[5][1] == 3)
            vizinho = next(v for v in widgets if v[5] and v[5][0] == 'navegar' and v[5][1] == 2)
            F.rolar(self.ctx, SimpleNamespace(type='WHEELDOWNMOUSE', shift=False,
                mouse_region_x=grupo[0] + grupo[2] / 2, mouse_region_y=grupo[1] + grupo[3] / 2))
            self.assertEqual(self.ctx.screen[grupo[5][3]], 1)
            self.assertEqual(self.ctx.screen.get(vizinho[5][3], 0), 0)

    def test_niveis_profundos_na_faixa_baixa_continuam_acessiveis(self):
        caminho = tuple('Nivel %d' % i for i in range(14))
        self.indice[:] = [dict(nome='Item', arquivo='item.blend', pasta=PASTA, niveis=list(caminho))]
        addon.biblioteca.definir_trilha(self.ctx.scene, caminho)
        self.ctx.preferences = SimpleNamespace(system=SimpleNamespace(ui_scale=1))
        self.ctx.region = SimpleNamespace(width=400, height=110)
        self.ctx.area = SimpleNamespace(tag_redraw=lambda: None)
        vistos = set()
        for _ in range(15):
            widgets = F.widgets(self.ctx, 400, 110)
            vistos.update(v[5][1] for v in widgets if v[5] and v[5][0] == 'navegar')
            self.assertTrue(all(v[0] >= 0 and v[0] + v[2] <= 400 for v in widgets))
            F.rolar(self.ctx, SimpleNamespace(type='WHEELUPMOUSE', shift=True))
        self.assertEqual(vistos, set(range(1, 15)))
        self.assertFalse(any(v[5] and v[5][0] == 'preset' for v in F.widgets(self.ctx, 400, 70)))

    def test_setas_das_fotos_reagem_ao_resize_e_nao_ocupam_filas_vazias(self):
        self.ctx.preferences = SimpleNamespace(system=SimpleNamespace(ui_scale=1))
        self.indice[:] = self.indice[:5]
        def fila(largura):
            itens = F.widgets(self.ctx, largura, 240)
            fotos = [v for v in itens if v[5] and v[5][0] == 'preset']
            setas = [v[5] for v in itens if v[5] and v[5][0] == 'rolar_nivel'
                     and 'faixa_itens' in v[5][1]]
            return fotos, setas
        fotos, _ = fila(1000)
        largura_exata = 12 + 5 * fotos[0][2] + 4 * 8
        fotos, setas = fila(largura_exata)
        self.assertEqual(len(fotos), 5)
        self.assertFalse(setas)
        self.assertEqual(fotos[0][0], 6)
        fotos, setas = fila(largura_exata - 1)
        self.assertEqual([v[2] for v in setas], [1])
        chave, limite = setas[0][1], setas[0][3]
        self.ctx.screen[chave] = limite
        fotos, setas = fila(largura_exata - 1)
        self.assertEqual([v[2] for v in setas], [-1])
        self.assertEqual(fotos[-1][5][1]['nome'], 'Canto 00004')
        fotos, setas = fila(largura_exata)
        self.assertFalse(setas)
        self.assertEqual(fotos[0][5][1]['nome'], 'Canto 00000')
        self.indice.clear()
        F.invalidar()
        self.assertFalse(any(v[5] and v[5][0] == 'rolar_nivel'
                             for v in F.widgets(self.ctx, 1000, 240)))

    def test_menu_preserva_protecao_e_alterna_rotulo_do_cadeado(self):
        self.assertEqual(F.opcoes_do_item({})[2][0], 'Bloquear')
        opcoes = F.opcoes_do_item(dict(bloqueado=True))
        self.assertFalse(opcoes[1][2])
        self.assertEqual(opcoes[2], ('Desbloquear', 'LOCKED', True))
        fabrica = F.opcoes_do_item(dict(fabrica='puxador'))
        self.assertEqual([v[2] for v in fabrica], [True, False, False])

    def test_menu_vincula_acoes_ao_item_e_background_nao_abre_popup(self):
        it = self.indice[0]
        chamadas = []
        def popup(desenhar, **kw):
            self.assertEqual(kw['title'], it['nome'])
            class Linha:
                enabled = True
                def operator(linha, nome, **kw):
                    props = SimpleNamespace()
                    chamadas.append((nome, kw['text'], linha, props))
                    return props
            menu = SimpleNamespace(layout=SimpleNamespace(row=Linha))
            desenhar(menu, self.ctx)
        self.ctx.window_manager = SimpleNamespace(popup_menu=popup)
        with patch.object(addon.perguntas, '_abrir_pergunta', return_value=True):
            self.assertTrue(F.abrir_menu_item(self.ctx, it))
        self.assertEqual(len(chamadas), 3)
        for indice, (op, nome, linha, props) in enumerate(chamadas):
            self.assertEqual(op, F.OBJECT_OT_acao_item_biblioteca.bl_idname)
            self.assertEqual((props.pasta, props.arquivo, props.indice),
                             (it['pasta'], it['arquivo'], indice))
        chamadas.clear()
        self.assertFalse(F.abrir_menu_item(self.ctx, it))
        self.assertFalse(chamadas)

    def test_acoes_do_menu_usam_operadores_existentes(self):
        it = self.indice[0]
        ops = SimpleNamespace(object=SimpleNamespace(cabinet_inserir_preset=Mock(return_value={'FINISHED'}),
            cabinet_editar_modelo=Mock(return_value={'RUNNING_MODAL'}),
            cabinet_bloqueio=Mock(return_value={'FINISHED'})))
        op = SimpleNamespace(pasta=it['pasta'], arquivo=it['arquivo'], report=Mock())
        with patch.object(F, 'bpy', SimpleNamespace(ops=ops)), \
             patch.object(addon.editor, 'bpy', SimpleNamespace(ops=ops)):
            for indice in range(3):
                op.indice = indice
                self.assertEqual(F.OBJECT_OT_acao_item_biblioteca.execute(op, self.ctx), {'FINISHED'})
        ops.object.cabinet_inserir_preset.assert_called_once_with(
            pasta=it['pasta'], arquivo=it['arquivo'], tipo='modulo')
        ops.object.cabinet_editar_modelo.assert_called_once_with(
            'INVOKE_DEFAULT', pasta=it['pasta'], arquivo=it['arquivo'])
        ops.object.cabinet_bloqueio.assert_called_once_with(pasta=it['pasta'], arquivo=it['arquivo'])

    def test_menu_reconfere_bloqueio_e_item_removido_antes_da_acao(self):
        it = self.indice[0]
        op = SimpleNamespace(pasta=it['pasta'], arquivo=it['arquivo'], indice=1, report=Mock())
        it['bloqueado'] = True
        self.assertEqual(F.OBJECT_OT_acao_item_biblioteca.execute(op, self.ctx), {'CANCELLED'})
        self.indice.clear()
        F.invalidar()
        op.indice = 0
        self.assertEqual(F.OBJECT_OT_acao_item_biblioteca.execute(op, self.ctx), {'CANCELLED'})

    def test_modelo_de_puxador_abre_criador_em_vez_de_inserir_malha(self):
        it = self.indice[0]
        it['niveis'] = ['Puxadores', 'Teste']
        op = SimpleNamespace(pasta=it['pasta'], arquivo=it['arquivo'], indice=0, report=Mock())
        posicionar = Mock(return_value={'RUNNING_MODAL'})
        with patch.object(addon.gaveta_eventos, '_modelo_do_criador', return_value='CRIAR') as criador, \
             patch.object(addon.editor, 'bpy', SimpleNamespace(ops=SimpleNamespace(object=SimpleNamespace(
                 cabinet_posicionar_puxador=posicionar)))):
            self.assertEqual(F.OBJECT_OT_acao_item_biblioteca.execute(op, self.ctx), {'FINISHED'})
        criador.assert_called_once_with(op, self.ctx, it, 0)
        posicionar.assert_called_once_with('INVOKE_DEFAULT')


addon.register()
resultado = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestFaixa))
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha na faixa da biblioteca')
