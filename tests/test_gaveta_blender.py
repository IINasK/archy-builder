"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_gaveta_blender.py"""
import os
import sys
import inspect
import unittest
from types import SimpleNamespace

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon


class TestGaveta(unittest.TestCase):
    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        self.cena = bpy.context.scene
        self.cena.cabinet_aba = 'MODULOS'
        self.cena.chapa_bib_aberta = True
        self.cena.chapa_n1 = 'Armarios'
        self.cena.chapa_n2 = 'Sala'
        self.cena.chapa_n3 = 'Inferiores'
        # Os parametros das portas moram na Scene e sobrevivem de um
        # teste para o outro; sem isto um teste ajusta a dobradica e o
        # seguinte falha por um motivo que nao e' dele.
        for nome in addon._PROPS_PORTAS_CENA:
            self.cena.property_unset(nome)

    def widgets(self):
        return addon._widgets_gaveta(bpy.context, 320, 1200)

    def test_medidas_e_wireframe_da_selecao(self):
        tipos = [a[0] for *_, a in self.widgets() if a]
        self.assertEqual(tipos.count('medida'), 3)
        self.assertIn('wireframe', tipos)
        self.assertNotIn('divisor_medidas', tipos)
        largo = addon._widgets_gaveta(bpy.context, 480, 1200)
        medidas = [v for v in largo if v[5] and v[5][0] == 'medida']
        self.assertEqual(len({v[1] for v in medidas}), 1)
        divisores = [v for v in largo if v[5]
                     and v[5][0] == 'divisor_medidas']
        self.assertEqual(len(divisores), 0)
        medio = [v for v in self.widgets() if v[5] and v[5][0] == 'medida']
        self.assertEqual(len({v[1] for v in medio}), 2)

    def test_objeto_livre_editavel(self):
        objeto = bpy.context.object
        resultado = bpy.ops.object.cabinet_editar_medida_gaveta(
            dono='livre', objeto=objeto.name,
            propriedade='dimensions_2', valor=1.25)
        self.assertEqual(resultado, {'FINISHED'})
        self.assertAlmostEqual(objeto.dimensions.z, 1.25)

    def test_rodape_abas_e_divisorias(self):
        bpy.ops.object.cabinet_marcar()
        bpy.context.object.chapa_modo = 'INDIVIDUAL'
        widgets = addon._widgets_gaveta(bpy.context, 564, 1200)
        por_tipo = lambda tipo: [v for v in widgets if v[5] and v[5][0] == tipo]
        for tipo in ('aba', 'modo'):
            abas = por_tipo(tipo)
            self.assertEqual(abas[-1][0] + abas[-1][2], 552)
        rodape = [por_tipo(tipo)[0] for tipo in ('chapa', 'auto', 'nome_objeto')]
        self.assertEqual(len({v[1] for v in rodape}), 1)
        self.assertEqual(rodape[-1][4], bpy.context.object.name)
        niveis = {v[5][1]: v[1] for v in por_tipo('navegar')}
        for divisor, nivel in zip(por_tipo('separador'), (1, 2)):
            centro = divisor[1] + divisor[3] / 2
            self.assertEqual(centro, (niveis[nivel] + niveis[nivel + 1] + 25) / 2)

    def test_alca_hit_test_retangular(self):
        ctx = SimpleNamespace(region=SimpleNamespace(height=1000))
        teste = addon.VIEW3D_GT_alca_gaveta.test_select
        self.assertEqual(teste(None, ctx, (1, 86)), 0)
        self.assertEqual(teste(None, ctx, (25, 154)), 0)
        self.assertEqual(teste(None, ctx, (27, 120)), -1)
        self.assertEqual(teste(None, ctx, (10, 160)), -1)

    def test_quatro_medidas_responsivas_sem_sobrepor_abas(self):
        bpy.ops.object.empty_add()
        bpy.context.object[addon.MARCA_CONJUNTO] = 1
        for largura, linhas in ((564, 1), (320, 2), (190, 4)):
            widgets = addon._widgets_gaveta(bpy.context, largura, 1200)
            medidas = [v for v in widgets if v[5] and v[5][0] == 'medida']
            abas = [v for v in widgets if v[5] and v[5][0] == 'modo']
            self.assertEqual(len(medidas), 4)
            self.assertEqual(len({v[1] for v in medidas}), linhas)
            self.assertLess(max(v[1] + v[3] for v in medidas), abas[0][1])

    def test_edicao_inline_confirma_unidades_e_cancela(self):
        classe = addon.OBJECT_OT_editar_medida_gaveta
        objeto = bpy.context.object
        op = SimpleNamespace(valor=2.0, propriedade='dimensions_2',
                             dono='livre', objeto=objeto.name)
        op._encerrar = lambda: classe._encerrar(op)
        op.execute = lambda ctx: classe.execute(op, ctx)
        op.report = lambda *_: None
        area = SimpleNamespace(as_pointer=lambda: 123, tag_redraw=lambda: None)
        ctx = SimpleNamespace(area=area, scene=self.cena,
            window_manager=SimpleNamespace(modal_handler_add=lambda _: None))
        evento = lambda tipo, texto='': SimpleNamespace(
            type=tipo, value='PRESS', ctrl=False, unicode=texto)
        for texto, esperado in (('1250', 1.25), ('80 cm', 0.8), ('1,5 m', 1.5)):
            self.assertEqual(classe.invoke(op, ctx, None), {'RUNNING_MODAL'})
            classe.modal(op, ctx, evento('TEXTINPUT', texto))
            self.assertEqual(classe.modal(op, ctx, evento('RET')), {'FINISHED'})
            bpy.context.view_layer.update()
            self.assertAlmostEqual(objeto.dimensions.z, esperado, places=6)
            self.assertIsNone(addon._edicao_gaveta[0])
        classe.invoke(op, ctx, None)
        classe.modal(op, ctx, evento('TEXTINPUT', '900'))
        self.assertEqual(classe.modal(op, ctx, evento('ESC')), {'CANCELLED'})
        self.assertAlmostEqual(objeto.dimensions.z, 1.5)

    def test_carrossel_arraste_nao_seleciona_categoria(self):
        widgets = self.widgets()
        acao = next(v[5] for v in widgets if v[5] and v[5][0] == 'navegar')
        original = self.cena.chapa_n1
        op = SimpleNamespace(_carrossel=acao, _mouse_inicio=200,
                             _indice_inicio=0, _arrastou=False)
        ctx = SimpleNamespace(screen=bpy.context.screen,
                              area=SimpleNamespace(tag_redraw=lambda: None))
        evento = SimpleNamespace(type='MOUSEMOVE', mouse_region_x=50)
        addon.OBJECT_OT_interagir_gaveta.modal(op, ctx, evento)
        self.assertGreater(ctx.screen[acao[3]], 0)
        evento = SimpleNamespace(type='LEFTMOUSE', value='RELEASE')
        addon.OBJECT_OT_interagir_gaveta.modal(op, ctx, evento)
        self.assertEqual(original, self.cena.chapa_n1)
        ctx.screen[acao[3]] = 0

    def test_medidas_parametricas_da_chapa(self):
        bpy.ops.object.cabinet_marcar()
        tipos = [a[0] for *_, a in self.widgets() if a]
        self.assertEqual(tipos.count('medida'), 3)
        self.assertIn('auto', tipos)
        self.assertIn('wireframe', tipos)
        resultado = bpy.ops.object.cabinet_editar_medida_gaveta(
            dono='objeto', objeto=bpy.context.object.name,
            propriedade='ui_chapa_largura', valor=1.5)
        self.assertEqual(resultado, {'FINISHED'})
        self.assertAlmostEqual(bpy.context.object.chapa_largura_mm, 1500.0)

    def test_cascata_e_presets_com_acoes(self):
        widgets = self.widgets()
        tipos = [a[0] for *_, a in widgets if a]
        self.assertIn('navegar', tipos)
        self.assertEqual(tipos.count('separador'), 2)
        self.assertTrue(all(v[3] == 1 for v in widgets
                            if v[5] and v[5][0] == 'separador'))
        self.assertIn('preset', tipos)
        self.assertIn('item', tipos)
        self.assertIn('slider', tipos)
        self.assertIn('rolar_nivel', tipos)
        for nivel in (1, 2, 3):
            linhas = {v[1] for v in widgets if v[5] and
                      v[5][0] == 'navegar' and v[5][1] == nivel}
            self.assertEqual(len(linhas), 1)

    def test_desmarcar_preserva_malha_e_limpa_vinculos(self):
        bpy.ops.object.cabinet_marcar()
        obj = bpy.context.object
        malha = [tuple(v.co) for v in obj.data.vertices]
        vizinho = obj.copy()
        bpy.context.collection.objects.link(vizinho)
        vizinho['adj_x_pos'] = obj.name
        vizinho['adj_x_pos_uid'] = addon._garantir_uid(obj)
        bpy.ops.object.cabinet_marcar(alternar=True)
        self.assertNotIn(addon.MARCA_CHAPA, obj)
        self.assertFalse(obj.chapa_auto)
        self.assertEqual(malha, [tuple(v.co) for v in obj.data.vertices])
        self.assertNotIn('adj_x_pos_uid', vizinho)

    def test_aba_portas(self):
        self.cena.cabinet_aba = 'PORTAS'
        tipos = [a[0] for *_, a in self.widgets() if a]
        self.assertIn('portas', tipos)

    def portas(self, largura=320):
        self.cena.cabinet_aba = 'PORTAS'
        return addon._widgets_gaveta(bpy.context, largura, 1400)

    def escolhas(self, largura=320):
        alvo = {}
        for *_, acao in self.portas(largura):
            if acao and acao[0] == 'escolha':
                alvo.setdefault(acao[1], []).append(acao[2])
        return alvo

    def test_aba_portas_traz_o_que_estava_no_popup(self):
        # O popup saiu: toda opcao dele tem que estar visivel na aba.
        alvo = self.escolhas()
        for prop in ('porta_frente', 'porta_orientacao', 'porta_abertura',
                     'porta_folhas', 'porta_espessura', 'porta_dobradica'):
            self.assertIn(prop, alvo, prop)
        self.assertEqual(alvo['porta_espessura'],
                         [str(int(e)) for e in addon.ESPESSURAS_PERMITIDAS])
        # a dobradica exige escolha: ESCOLHER nao e' oferecido
        self.assertNotIn('ESCOLHER', alvo['porta_dobradica'])
        rotulos = [v[4] for v in self.portas()]
        self.assertIn('Escolha a dobradica', rotulos)

    def test_escolha_escreve_na_cena(self):
        acao = next(v[5] for v in self.portas()
                    if v[5] and v[5][0] == 'escolha'
                    and v[5][1] == 'porta_abertura' and v[5][2] == 'CORRER')
        self.assertEqual(addon.OBJECT_OT_interagir_gaveta.poll(bpy.context),
                         addon._eh_area_gaveta(bpy.context))
        setattr(bpy.context.scene, acao[1], acao[2])
        self.assertEqual(self.cena.porta_abertura, 'CORRER')

    def test_campos_seguem_a_abertura(self):
        self.cena.porta_abertura = 'GIRO'
        self.cena.porta_dobradica = 'RETA'
        self.cena.porta_folhas = 2
        props = {v[5][2] for v in self.portas()
                 if v[5] and v[5][0] == 'medida'}
        self.assertIn('ui_porta_afastamento', props)
        self.assertIn('ui_porta_entre_folhas', props)
        self.assertNotIn('ui_porta_recuo_correr', props)

        self.cena.porta_abertura = 'CORRER'
        props = {v[5][2] for v in self.portas()
                 if v[5] and v[5][0] == 'medida'}
        self.assertIn('ui_porta_recuo_correr', props)
        self.assertNotIn('ui_porta_afastamento', props)
        # correr nao usa dobradica
        self.assertNotIn('porta_dobradica', self.escolhas())

    def test_folhas_limitadas_pela_abertura(self):
        self.cena.porta_folhas = 4
        self.cena.porta_abertura = 'BASCULANTE'
        self.assertEqual(self.cena.porta_folhas, 1)
        self.assertEqual(self.escolhas()['porta_folhas'], [1])
        self.cena.porta_abertura = 'CORRER'
        self.assertEqual(self.escolhas()['porta_folhas'], [1, 2, 3, 4])

    def test_segmento_escolhido_acende(self):
        # Sem isto o usuario nao enxerga qual opcao esta' valendo.
        self.cena.porta_abertura = 'CORRER'
        acesos = [v[5] for v in self.portas()
                  if v[5] and v[5][0] == 'escolha'
                  and v[5][1] == 'porta_abertura' and v[5][3]]
        self.assertEqual([a[2] for a in acesos], ['CORRER'])
        fonte = inspect.getsource(addon._desenhar_gaveta)
        self.assertIn("acao[0] == 'escolha' and acao[3]", fonte)

    def test_nenhum_widget_da_aba_portas_se_sobrepoe(self):
        # O campo de medida tem 37 px e as filas de segmento deixam 29:
        # sem respiro ele cobria a fila de cima.
        for largura in (190, 320, 564):
            caixas = [(v[0], v[1], v[2], v[3]) for v in self.portas(largura)]
            for i, (ax, ay, aw, ah) in enumerate(caixas):
                for bx, by, bw, bh in caixas[i + 1:]:
                    sobrepoe = (ax < bx + bw - 0.01 and bx < ax + aw - 0.01
                                and ay < by + bh - 0.01
                                and by < ay + ah - 0.01)
                    self.assertFalse(sobrepoe,
                                     'largura %d: %s cobre %s'
                                     % (largura, (ax, ay, aw, ah),
                                        (bx, by, bw, bh)))

    def test_aba_portas_cabe_na_gaveta(self):
        for largura in (190, 320, 564):
            for x, _y, w, _h, _r, _a in self.portas(largura):
                self.assertGreaterEqual(x, 0)
                self.assertLessEqual(x + w, min(largura - 12, 552) + 0.01)

    def test_caixas_das_folhas_ficam_dentro_do_box(self):
        caixas = addon._caixas_das_folhas(600.0, 800.0, 400.0, 2)
        self.assertEqual(len(caixas), 2)
        for caixa in caixas:
            self.assertEqual(len(caixa), 8)
            for x, y, z in caixa:
                self.assertGreaterEqual(x, 0.0)
                self.assertLessEqual(x, 600.0)
                self.assertGreaterEqual(z, 0.0)
                self.assertLessEqual(z, 800.0)
                # as folhas ficam na FRENTE, nao no fundo
                self.assertLessEqual(y, 400.0 * 0.5)
        self.assertEqual(addon._caixas_das_folhas(600.0, 800.0, 400.0, 0), [])

    def test_folhas_nao_mudam_a_escala_do_box(self):
        # A escala sai dos 8 cantos da caixa; se as folhas entrassem na
        # conta, o modulo apareceria menor do que e'.
        sem = addon._pontos_wireframe(600.0, 800.0, 400.0)
        extras = [v for c in addon._caixas_das_folhas(600.0, 800.0, 400.0, 3)
                  for v in c]
        com = addon._pontos_wireframe(600.0, 800.0, 400.0, extras)
        self.assertEqual(sem, com[:8])
        self.assertEqual(len(com), 8 + len(extras))

    def test_wireframe_leva_a_contagem_de_folhas(self):
        acao = next(v[5] for v in self.widgets()
                    if v[5] and v[5][0] == 'wireframe')
        self.assertEqual(len(acao), 6)
        self.assertEqual(acao[5], 0)

    def test_folhas_para_wireframe_encontra_pelas_duas_pontas(self):
        bpy.ops.object.empty_add()
        conj = bpy.context.object
        conj[addon.MARCA_CONJUNTO] = 1
        bpy.ops.object.empty_add()
        grupo = bpy.context.object
        grupo[addon.MARCA_PORTAS] = 1
        grupo[addon.CHAVE_MODULO_PORTA] = conj.name
        grupo.parent = conj
        for i in range(2):
            malha = bpy.data.meshes.new('Folha')
            folha = bpy.data.objects.new('Folha_%d' % i, malha)
            bpy.context.collection.objects.link(folha)
            folha[addon.MARCA_CHAPA] = 1
            folha[addon.MARCA_FOLHA] = 1
            folha.parent = grupo
        # pelo modulo e pela propria porta
        self.assertEqual(addon._folhas_para_wireframe(conj), 2)
        self.assertEqual(addon._folhas_para_wireframe(grupo), 2)
        bpy.ops.mesh.primitive_cube_add()
        self.assertEqual(addon._folhas_para_wireframe(bpy.context.object), 0)

    def botao_portas(self):
        return next((v[4], v[5]) for v in self.portas()
                    if v[5] and v[5][0] == 'portas')

    def test_botao_diz_o_que_falta_em_vez_de_nao_fazer_nada(self):
        # REGRESSAO: a dobradica nasce em ESCOLHER, o operador recusava
        # e o aviso nao chegava na gaveta -- clicar parecia nao fazer
        # nada. Agora o proprio botao carrega o motivo.
        self.assertEqual(self.cena.porta_dobradica, 'ESCOLHER')
        rotulo, acao = self.botao_portas()
        self.assertTrue(acao[3])
        self.assertIn('dobradica', acao[3])
        self.assertEqual(rotulo, acao[3])

        self.cena.porta_dobradica = 'RETA'
        rotulo, acao = self.botao_portas()
        self.assertEqual(acao[3], '')
        self.assertEqual(rotulo, 'Criar Portas')

    def test_botao_acende_enquanto_marca_o_vao(self):
        self.cena.porta_dobradica = 'RETA'
        _, acao = self.botao_portas()
        self.assertFalse(acao[2])
        addon._apanhando_vao[0] = True
        try:
            rotulo, acao = self.botao_portas()
            self.assertTrue(acao[2])
            self.assertIn('Marcando', rotulo)
        finally:
            addon._apanhando_vao[0] = False
        fonte = inspect.getsource(addon._desenhar_gaveta)
        self.assertIn("acao[0] == 'portas' and acao[2]", fonte)

    def test_motivo_portas_reflete_a_aba(self):
        self.cena.porta_dobradica = 'RETA'
        self.assertEqual(addon._motivo_portas(self.cena), '')
        self.cena.porta_folga_mm = 5000.0
        self.assertTrue(addon._motivo_portas(self.cena))

    def test_padrao_e_porta_dupla(self):
        self.assertEqual(self.cena.porta_folhas, 2)
        self.assertEqual(self.cena.porta_abertura, 'GIRO')

    def test_espessuras_saem_numericas_para_o_calculo(self):
        # REGRESSAO: as espessuras sao Enum, ou seja STRING. O operador
        # quer a string, mas quem CALCULA quebra com texto -- a previa
        # e a aba morriam com TypeError.
        p = addon._parametros_portas_da_cena(self.cena)
        self.assertIsInstance(p['espessura_mm'], str)
        n = addon._parametros_portas_da_cena(self.cena, numerico=True)
        self.assertIsInstance(n['espessura_mm'], float)
        self.assertIsInstance(n['lateral_mm'], float)
        n['dobradica'] = 'RETA'
        self.assertTrue(addon._calcular_folhas_portas(600.0, 800.0, n))

    def test_aba_portas_com_grupo_selecionado_nao_quebra(self):
        # A aba mostra a previa das folhas do grupo; um TypeError ali
        # derrubaria o desenho da gaveta INTEIRA, nao so' a linha.
        bpy.ops.object.empty_add()
        grupo = bpy.context.object
        grupo[addon.MARCA_PORTAS] = 1
        grupo['porta_vao_largura_mm'] = 600.0
        grupo['porta_vao_altura_mm'] = 800.0
        grupo['porta_parametros'] = {'abertura': 'GIRO', 'folhas': 2,
                                     'dobradica': 'RETA'}
        self.cena.porta_dobradica = 'RETA'
        rotulos = [v[4] for v in self.portas()]
        self.assertTrue(any('Cada folha' in r for r in rotulos), rotulos)
        self.assertTrue(any('Ler parametros' in r for r in rotulos))

    def test_parametros_da_cena_cobrem_o_operador(self):
        # Se faltar um nome, o operador cai no default e o usuario ve
        # um valor que a aba nao mostra.
        p = addon._parametros_portas_da_cena(self.cena)
        self.assertEqual(set(p), set(addon._PARAMETROS_PORTAS))

    def test_ler_do_grupo_traz_os_parametros(self):
        guardado = {'abertura': 'CORRER', 'folhas': 3, 'dobradica': 'RETA',
                    'espessura_mm': 20.0, 'lateral_mm': 15.0,
                    'folga_mm': 4.0, 'entre_folhas_mm': 2.0,
                    'afastamento_mm': 0.0, 'recuo_embutida_mm': 0.0,
                    'recuo_correr_mm': 25.0, 'sobreposicao_mm': 30.0,
                    'entre_planos_mm': 2.0}
        bpy.ops.object.empty_add()
        falso = bpy.context.object
        falso['porta_parametros'] = guardado
        addon._carregar_portas_na_cena(self.cena, falso)
        self.assertEqual(self.cena.porta_abertura, 'CORRER')
        self.assertEqual(self.cena.porta_folhas, 3)
        self.assertEqual(self.cena.porta_espessura, '20')
        self.assertEqual(self.cena.porta_lateral, '15')
        self.assertAlmostEqual(self.cena.porta_folga_mm, 4.0)
        self.assertAlmostEqual(self.cena.porta_recuo_correr_mm, 25.0)

    def test_criar_portas_nao_abre_popup(self):
        # INVOKE abriria o dialogo; os parametros ja' vem da aba.
        fonte = inspect.getsource(addon.OBJECT_OT_apanhar_vao_portas._concluir)
        self.assertIn("'EXEC_DEFAULT'", fonte)
        self.assertNotIn("'INVOKE_DEFAULT'", fonte)

    def test_responsividade_das_miniaturas(self):
        for largura in (190, 320, 620, 2056):
            widgets = addon._widgets_gaveta(bpy.context, largura, 1200)
            self.assertTrue(all(v[0] + v[2] <= min(largura - 12, 552)
                                for v in widgets))
            fotos = [v for v in widgets if v[5] and v[5][0] == 'preset']
            self.assertTrue(fotos)
            for x, _y, w, h, _rotulo, _acao in fotos:
                self.assertLessEqual(x + w, largura - 12 + 0.01)
                self.assertAlmostEqual(w - 10, h - 27)
                self.assertLessEqual(x + w, 552)

    def test_slider_compacto_mantem_extremos_do_arraste(self):
        for largura in (190, 320, 564):
            slider = next(v for v in addon._widgets_gaveta(
                bpy.context, largura, 1200) if v[5] and v[5][0] == 'slider')
            x, y, w, h = slider[:4]
            inicio, _, trilho = addon._trilho_miniaturas_gaveta(x, y, w, h)
            self.assertLessEqual(w, 290)
            self.assertGreater(inicio, x)
            self.assertLessEqual(inicio + trilho + 6, x + w)
            op = SimpleNamespace(_inicio=inicio, _largura=trilho)
            ctx = SimpleNamespace(scene=self.cena,
                                  area=SimpleNamespace(tag_redraw=lambda: None))
            for posicao, esperado in ((inicio, 2), (inicio + trilho, 8)):
                addon.OBJECT_OT_interagir_gaveta._atualizar(op, ctx, posicao)
                self.assertEqual(self.cena.chapa_tam_bloco, esperado)

    def test_medidas_estreitas_e_limite_da_rolagem(self):
        largura, altura = 190, 400
        inicio = addon._widgets_gaveta(bpy.context, largura, altura,
                                       _rolagem=0)
        medidas = [v for v in inicio if v[5] and v[5][0] == 'medida']
        self.assertEqual(len({v[0] for v in medidas}), 1)
        self.assertTrue(all(v[0] + v[2] <= largura - 12 for v in medidas))
        limite = addon._limite_rolagem_gaveta(bpy.context, largura, altura)
        self.assertGreater(limite, 0)
        bpy.context.screen['cabinet_gaveta_rolagem'] = 9999
        fim = addon._widgets_gaveta(bpy.context, largura, altura)
        self.assertEqual(fim[2][1] - inicio[2][1], limite)
        bpy.context.screen['cabinet_gaveta_rolagem'] = 0


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestGaveta)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes da gaveta')
