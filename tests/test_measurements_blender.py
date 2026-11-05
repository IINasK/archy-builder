"""Localized dimensions, editing without losing text and HUD presentation."""
import os,sys,tempfile,unittest
from unittest.mock import patch
import bpy
from types import SimpleNamespace
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon
G=addon.gaveta_desenho


class TestMedidas(unittest.TestCase):
    def setUp(self):
        G._apresentacao_medida.cache_clear()
        self.p=patch.object(addon.opcoes,'_opcao',return_value='MM');self.p.start()
        self.addCleanup(self.p.stop)

    def test_ctrl_z_e_redo_restauram_texto_cursor_e_selecao_sem_undo_da_cena(self):
        # Regression v392: Ctrl+Z was ignored or inserted its shortcut's Unicode character.
        estado=dict(texto='100',cursor=3,selecionado=False)
        G._tecla_no_texto(estado,'PLUS','+')
        G._tecla_no_texto(estado,'V','50cm')
        with patch.object(bpy.ops.ed,'undo') as undo:
            self.assertTrue(G._tecla_no_texto(estado,'Z','z',ctrl=True))
            self.assertEqual(estado['texto'],'100 + ')
            G._tecla_no_texto(estado,'Z',ctrl=True)
            self.assertEqual((estado['texto'],estado['cursor']),('100',3))
            G._tecla_no_texto(estado,'Z',ctrl=True,shift=True)
            G._tecla_no_texto(estado,'Y',ctrl=True)
            self.assertEqual(estado['texto'],'100 + 50cm')
            undo.assert_not_called()
        G._tecla_no_texto(estado,'Z',ctrl=True)
        G._tecla_no_texto(estado,'V','20cm')
        G._tecla_no_texto(estado,'Y',ctrl=True)
        self.assertEqual(estado['texto'],'100 + 20cm')
        vazio=dict(texto='7',cursor=1,selecionado=False)
        self.assertTrue(G._tecla_no_texto(vazio,'Z',ctrl=True))
        self.assertEqual(vazio['texto'],'7')

    def test_entrada_do_menu_nao_seleciona_tudo_e_backspace_apaga_so_um(self):
        # Regression v392: entering a field and pressing Backspace cleared the entire value.
        classe=addon.gaveta_eventos.OBJECT_OT_editar_medida_gaveta
        area=SimpleNamespace(as_pointer=lambda:123,tag_redraw=lambda:None)
        ctx=SimpleNamespace(area=area,window_manager=SimpleNamespace(modal_handler_add=lambda _:None))
        op=SimpleNamespace(valor=1.234,dono='livre',propriedade='dimensions_2')
        with patch.object(addon.gaveta,'_edicao_gaveta',[None]):
            self.assertEqual(classe.invoke(op,ctx,None),{'RUNNING_MODAL'})
            G._tecla_no_texto(op._estado,'BACK_SPACE')
            self.assertEqual(op._estado['texto'],'123')
            self.assertFalse(op._estado['selecionado'])

    def test_valor_sem_unidade_na_soma_usa_padrao_e_nao_unidade_vizinha(self):
        for unidade,metros,final in (('MM',.6,'600 mm'),('CM',1.5,'150 cm'),('M',100.5,'100,5 m')):
            with patch.object(addon.opcoes,'_opcao',return_value=unidade):
                self.assertEqual(G._ler_medida_digitada('100 + 50CM'),metros)
                self.assertTrue(G._com_cursor('100 + 50CM',10,medida=True).endswith(' = '+final))

    def test_shift_seleciona_trecho_ctrl_a_tudo_e_undo_recupera_o_trecho(self):
        estado=dict(texto='12345',cursor=5,selecionado=False)
        for _ in range(2):G._tecla_no_texto(estado,'LEFT_ARROW',shift=True)
        self.assertEqual(G._selecao_no_texto(estado),(3,5))
        G._tecla_no_texto(estado,'V','67')
        self.assertEqual(estado['texto'],'12367')
        G._tecla_no_texto(estado,'Z',ctrl=True)
        self.assertEqual(G._selecao_no_texto(estado),(3,5))
        G._tecla_no_texto(estado,'BACK_SPACE')
        self.assertEqual(estado['texto'],'123')
        G._tecla_no_texto(estado,'A',ctrl=True)
        self.assertEqual(G._selecao_no_texto(estado),(0,3))
        G._tecla_no_texto(estado,'DEL')
        self.assertEqual(estado['texto'],'')

    def test_realce_mapeia_milhar_sem_selecionar_unidade_ou_resultado(self):
        estado=dict(texto='1234 + 5',cursor=4,selecionado=True,ancora=0)
        with patch.object(G._gaveta,'_retangulo_gaveta') as retangulo:
            G._realcar_selecao_texto(10,20,estado,14,medida=True)
        G.blf.size(0,14)
        args=retangulo.call_args.args
        self.assertAlmostEqual(args[0],10)
        self.assertAlmostEqual(args[2],G.blf.dimensions(0,'1.234')[0])
        cor=bpy.context.preferences.themes[0].user_interface.wcol_regular.inner_sel
        self.assertEqual(args[-1],(*cor[:3],1))
        estado['selecionado']=False
        with patch.object(G._gaveta,'_retangulo_gaveta') as retangulo:
            G._realcar_selecao_texto(10,20,estado,14,medida=True)
        retangulo.assert_not_called()

    def test_modais_do_menu_hud_e_parede_encaminham_undo_e_shift_sem_aplicar_medida(self):
        def evento(tipo,entrada='',ctrl=False,shift=False):
            return SimpleNamespace(type=tipo,value='PRESS',unicode=entrada,ctrl=ctrl,shift=shift)
        area=SimpleNamespace(tag_redraw=lambda:None)
        ctx=SimpleNamespace(window_manager=SimpleNamespace(clipboard=''),area=area)
        rotas=(('menu',addon.gaveta_eventos.OBJECT_OT_editar_medida_gaveta.modal),
               ('hud',addon.hud.OBJECT_OT_arrastar_hud._digitar),
               ('guia',addon.paredes.OBJECT_OT_guia_parede._digitar),
               ('parede',addon.paredes_composicao.OBJECT_OT_editar_cota_parede._modal))
        for nome,modal in rotas:
            with self.subTest(nome=nome):
                estado=dict(texto='100',cursor=3,selecionado=False)
                op=SimpleNamespace(_estado=estado,_area=area)
                with patch.object(addon.gaveta,'_edicao_gaveta',[estado]), \
                     patch.object(addon.hud,'_edicao_hud',[estado]), \
                     patch.object(addon.paredes,'_edicao_guia',[estado]), \
                     patch.object(addon.paredes_composicao,'_edicao',[estado]), \
                     patch.object(addon.paredes_edicao,'ativa',return_value=True), \
                     patch.object(addon.paredes_edicao,'_redesenhar'), \
                     patch.object(addon.gaveta_eventos,'aplicar_medida') as aplicar:
                    modal(op,ctx,evento('TEXTINPUT','5'))
                    self.assertEqual(estado['texto'],'1005')
                    modal(op,ctx,evento('Z','z',ctrl=True))
                    self.assertEqual(estado['texto'],'100')
                    modal(op,ctx,evento('Z','Z',ctrl=True,shift=True))
                    self.assertEqual(estado['texto'],'1005')
                    modal(op,ctx,evento('LEFT_ARROW',shift=True))
                    self.assertEqual(G._selecao_no_texto(estado),(3,4))
                    aplicar.assert_not_called()

    def test_hud_entra_com_cursor_no_fim_sem_selecao_automatica(self):
        estado=dict(itens=[{}])
        op=SimpleNamespace(_area=SimpleNamespace(tag_redraw=lambda:None))
        with patch.object(addon.hud,'_edicao_hud',[estado]), \
             patch.object(addon.hud,'_valor_hud',return_value=1234):
            addon.hud.OBJECT_OT_arrastar_hud._comecar_digitacao(op)
            G._tecla_no_texto(estado,'BACK_SPACE')
        self.assertEqual(estado['texto'],'123')

    def test_selecao_por_shift_clique_e_seta_colapsa_para_borda(self):
        estado=dict(texto='12345',cursor=5,selecionado=False)
        G._posicionar_cursor_texto(estado,2,shift=True)
        self.assertEqual(G._selecao_no_texto(estado),(2,5))
        G._tecla_no_texto(estado,'LEFT_ARROW')
        self.assertEqual((estado['cursor'],estado['selecionado']),(2,False))
        G._posicionar_cursor_texto(estado,5,shift=True)
        G._tecla_no_texto(estado,'RIGHT_ARROW')
        self.assertEqual((estado['cursor'],estado['selecionado']),(5,False))
        G._tecla_no_texto(estado,'HOME',shift=True)
        G._tecla_no_texto(estado,'V','8')
        self.assertEqual(estado['texto'],'8')

    def test_exemplos_de_digitacao_formatam_unidade_e_separadores(self):
        for entrada,esperado in (('1','1| mm'),('.1','0,1| mm'),('1234','1.234| mm'),
            ('12345','12.345| mm'),('12345.67','12.345,67| mm'),('12345,67','12.345,67| mm')):
            with self.subTest(entrada=entrada):
                self.assertEqual(G._com_cursor(entrada,len(entrada),medida=True),esperado)

    def test_texto_de_medida_segue_unidade_configurada_sem_zeros_artificiais(self):
        for unidade,valor,esperado in (('MM',12345.67,'12.345,67 mm'),
            ('CM',12345.67,'1.234,567 cm'),('M',12345.67,'12,34567 m'),('MM',-.00001,'0 mm')):
            with patch.object(addon.opcoes,'_opcao',return_value=unidade):
                self.assertEqual(addon.opcoes._texto_medida(valor),esperado)

    def test_conta_conserva_expressao_e_mostra_resultado(self):
        self.assertEqual(G._com_cursor('.2 + .5',7,medida=True),'0,2 + 0,5| = 0,7 mm')
        self.assertAlmostEqual(G._ler_medida_digitada('.2 + .5',minimo=0),.0007)

    def test_cursor_mapeia_digitos_sem_tratar_milhar_como_decimal(self):
        for cursor,esperado in enumerate(('|1.234 mm','1|.234 mm','1.2|34 mm','1.23|4 mm','1.234| mm')):
            self.assertEqual(G._com_cursor('1234',cursor,medida=True),esperado)
        for cursor,x in enumerate((0,1,3,4,5)):
            self.assertEqual(G._cursor_no_x('1234',4,0,x,len,medida=True),cursor)

    def test_editar_no_meio_apagar_e_colar_conserva_buffer_original(self):
        estado=dict(texto='1234',cursor=2,selecionado=False)
        G._tecla_no_texto(estado,'FIVE','5')
        self.assertEqual(estado['texto'],'12534')
        self.assertEqual(G._com_cursor(estado['texto'],estado['cursor'],medida=True),'12.5|34 mm')
        G._tecla_no_texto(estado,'BACK_SPACE')
        self.assertEqual(estado['texto'],'1234')
        self.assertEqual(G._com_cursor(estado['texto'],estado['cursor'],medida=True),'1.2|34 mm')
        G._tecla_no_texto(estado,'A',ctrl=True)
        G._tecla_no_texto(estado,'V','12.345,67mm')
        self.assertAlmostEqual(G._ler_medida_digitada(estado['texto']),12.34567)

    def test_zero_a_esquerda_sinal_e_decimal_incompleto(self):
        for texto,esperado in (('.','0,| mm'),('12345.','12.345,| mm'),
            ('-.1','-0,1| mm'),('0.10','0,10| mm')):
            self.assertEqual(G._com_cursor(texto,len(texto),medida=True),esperado)

    def test_previa_de_conta_incompleta_ou_divisao_por_zero_nao_interrompe_edicao(self):
        for texto in ('1234 + ','1234 / 0','(1234 + 2','-'):
            self.assertNotIn(' = ',G._com_cursor(texto,len(texto),medida=True))

    def test_previa_na_unidade_atual_e_conta_com_unidades_misturadas(self):
        with patch.object(addon.opcoes,'_opcao',return_value='CM'):
            self.assertEqual(G._com_cursor('2 + 3',5,medida=True),'2 + 3| = 5 cm')
        self.assertEqual(G._com_cursor('1m + 2cm',8,medida=True),'1m + 2cm| = 1.020 mm')

    def test_parser_aceita_milhar_com_virgula_e_conserva_ponto_decimal_original(self):
        for texto,metros in (('12.345,67mm',12.34567),
            ('1.234mm',.00123),('12345.67mm',12.34567),('1.234,5 + .5',1.235)):
            self.assertAlmostEqual(G._ler_medida_digitada(texto),metros,places=5)
        self.assertEqual(G._ler_medida_digitada('1.234.567 mm'),G._ler_medida_digitada('1234567 mm'))

    def test_repetir_redesenho_reutiliza_previa_sem_refazer_calculo(self):
        with patch.object(G,'_ler_medida_digitada',wraps=G._ler_medida_digitada) as parser:
            for _ in range(20):G._com_cursor('.2 + .5',7,medida=True)
            self.assertEqual(parser.call_count,1)
            self.assertGreater(G._apresentacao_medida.cache_info().hits,0)

    def test_trocar_unidade_durante_edicao_atualiza_sufixo_do_mesmo_buffer(self):
        self.assertEqual(G._com_cursor('1234',4,medida=True),'1.234| mm')
        with patch.object(addon.opcoes,'_opcao',return_value='CM'):
            self.assertEqual(G._com_cursor('1234',4,medida=True),'1.234| cm')
        with patch.object(addon.opcoes,'_opcao',return_value='M'):
            self.assertEqual(G._com_cursor('1234',4,medida=True),'1.234| m')

    def test_nomes_contadores_e_pixels_nao_recebem_unidade_de_medida(self):
        self.assertEqual(G._com_cursor('Armario 1234',12),'Armario 1234|')
        self.assertEqual(G._com_cursor('1234',4),'1234|')
        self.assertEqual(G._ler_numero_digitado('10 + 4'),14)

    def test_caixa_preta_reutiliza_os_cantos_arredondados_do_menu(self):
        with patch.object(addon.hud,'gpu'),patch.object(addon.hud.blf,'draw'), \
             patch.object(addon.gaveta,'_retangulo_arredondado_gaveta') as fundo:
            addon.hud._caixa_texto_hud(10,20,'12.345,67 mm',14,1)
        self.assertEqual(fundo.call_args.args[4],4)
        self.assertEqual(fundo.call_args.args[-1],(0,0,0,.88))


with tempfile.TemporaryDirectory(prefix='medidas_') as pasta, \
     patch.object(addon.opcoes,'_pasta_addon',return_value=pasta), \
     patch.object(addon.biblioteca,'pasta_biblioteca',return_value=pasta):
    addon.register()
    try:resultado=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestMedidas))
    finally:addon.unregister()
    if not resultado.wasSuccessful():raise RuntimeError("Formatted-dimension tests failed")
