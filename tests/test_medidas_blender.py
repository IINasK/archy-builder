"""Medidas localizadas, edicao sem perder o texto e apresentacao da HUD."""
import os,sys,tempfile,unittest
from unittest.mock import patch
import bpy
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon
G=addon.gaveta_desenho


class TestMedidas(unittest.TestCase):
    def setUp(self):
        G._apresentacao_medida.cache_clear()
        self.p=patch.object(addon.opcoes,'_opcao',return_value='MM');self.p.start()
        self.addCleanup(self.p.stop)

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
    if not resultado.wasSuccessful():raise RuntimeError('Falha nas medidas formatadas')
