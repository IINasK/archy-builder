"""Auditoria geometrica: contatos, penetracao, rotacao e recortes reais."""
from pathlib import Path
import sys
import tempfile
import unittest

from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import auditar_internos_biblioteca as auditoria


class TestAuditoriaInternos(unittest.TestCase):
    def caixa(self, origem=(0, 0, 0), dimensoes=(10, 10, 10), angulo=0):
        matriz = Matrix.Translation(origem) @ Matrix.Rotation(angulo, 4, 'Z')
        return auditoria.caixa(matriz, dimensoes)

    def test_contato_e_ruido_abaixo_da_tolerancia_nao_sao_colisao(self):
        a = self.caixa()
        for x in (10, 9.9):
            with self.subTest(x=x):
                b = self.caixa((x, 0, 0))
                self.assertIsNone(auditoria.intersecao_de_envelopes(a, b))
                self.assertIsNone(auditoria.ponto_de_colisao(a, b))

    def test_penetracao_positiva_retorna_ponto_dentro_das_duas_pecas(self):
        a, b = self.caixa(), self.caixa((9.5, 0, 0))
        ponto = auditoria.ponto_de_colisao(a, b)
        self.assertIsNotNone(ponto)
        from mathutils import Vector
        self.assertTrue(auditoria.dentro(Vector(ponto), a))
        self.assertTrue(auditoria.dentro(Vector(ponto), b))

    def test_peca_inteiramente_contida_nao_exige_superficies_cruzadas(self):
        a, b = self.caixa(), self.caixa((2, 2, 2), (2, 2, 2))
        self.assertFalse(a['arvore'].overlap(b['arvore']))
        self.assertIsNotNone(auditoria.ponto_de_colisao(a, b))

    def test_placas_cruzadas_sem_centros_nem_vertices_dentro(self):
        a = self.caixa((-10, -1, 0), (20, 2, 2))
        b = self.caixa((5, -5, 0), (2, 20, 2))
        self.assertIsNotNone(auditoria.ponto_de_colisao(a, b))

    def test_malha_aberta_nao_recebe_confirmacao_de_volume(self):
        fechada = self.caixa()
        aberta = auditoria.geometria(fechada['pontos'], fechada['faces'][:-1])
        self.assertTrue(fechada['fechada'])
        self.assertFalse(aberta['fechada'])
        self.assertIsNone(auditoria.ponto_de_colisao(aberta, self.caixa((2, 2, 2))))

    def test_referenciais_girados_usam_os_eixos_das_pecas(self):
        a = self.caixa(dimensoes=(20, 2, 2), angulo=.6)
        b = self.caixa((0, 4, 0), (20, 2, 2), angulo=.6)
        self.assertIsNone(auditoria.intersecao_de_envelopes(a, b))
        self.assertIsNotNone(auditoria.ponto_de_colisao(a, self.caixa((5, 2, 0))))

    def test_recorte_em_l_nao_vira_colisao_pela_caixa_retangular(self):
        perfil = ((0, 0), (10, 0), (10, 3), (3, 3), (3, 10), (0, 10))
        pontos = [(x, y, z) for z in (0, 2) for x, y in perfil]
        faces = [list(reversed(range(6))), list(range(6, 12))]
        faces += [[i, (i+1) % 6, (i+1) % 6+6, i+6] for i in range(6)]
        recortada = auditoria.geometria(pontos, faces)
        dentro_do_recorte = self.caixa((5, 5, .2), (2, 2, 1))
        self.assertIsNotNone(auditoria.intersecao_de_envelopes(recortada, dentro_do_recorte))
        self.assertIsNone(auditoria.ponto_de_colisao(recortada, dentro_do_recorte))

    def test_destino_dentro_da_biblioteca_e_recusado_antes_de_ler(self):
        with tempfile.TemporaryDirectory() as pasta:
            biblioteca = Path(pasta) / 'biblioteca'
            biblioteca.mkdir()
            with self.assertRaises(ValueError):
                auditoria.auditar(biblioteca, biblioteca / 'relatorio')
            self.assertFalse(list(biblioteca.iterdir()))

    def test_excesso_e_medido_no_referencial_girado_do_vao(self):
        from mathutils import Vector
        m = Matrix.Translation((100, 200, 300)) @ Matrix.Rotation(.7, 4, 'Z')
        pontos = [m @ Vector(v) for v in ((-2, 0, 0), (8, 12, 9))]
        for valor, esperado in zip(auditoria.excessos(pontos, m, (10, 10, 10)), (2, 2, 0)):
            self.assertAlmostEqual(valor, esperado, places=4)


resultado = unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(TestAuditoriaInternos))
if not resultado.wasSuccessful():
    raise RuntimeError('Auditoria de internos reprovada')
