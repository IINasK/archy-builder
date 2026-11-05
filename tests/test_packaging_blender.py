"""Distribuicao da licenca e reconstrucao do ZIP em pasta descartavel."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from tools.development import build


class TestEmpacotamento(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.pkg = self.raiz/'cabinet_creator';self.pkg.mkdir()
        for nome in ('LICENSE','NOTICE'):
            (self.raiz/nome).write_bytes((RAIZ/nome).read_bytes())

    def gerar(self):
        with patch.object(build,'RAIZ',str(self.raiz)), \
             patch.object(build,'PKG',str(self.pkg)), \
             patch.object(build,'DIST',str(self.raiz/'dist')), contextlib.redirect_stdout(io.StringIO()):
            build.main()
        return self.raiz/'dist'/'archy_builder.zip'

    def test_pacote_inclui_licenca_oficial_sem_backups_ou_temporarios(self):
        for nome in ('__init__.py','modelo.blend','modelo.blend1','modelo.blend2','codigo.pyc','parcial.tmp'):
            (self.pkg/nome).write_bytes(b'prova')
        (self.pkg/'__pycache__').mkdir();(self.pkg/'__pycache__'/'codigo.pyc').write_bytes(b'cache')
        with zipfile.ZipFile(self.gerar()) as pacote:
            self.assertEqual(set(pacote.namelist()), {'cabinet_creator/__init__.py','cabinet_creator/modelo.blend',
                             'cabinet_creator/LICENSE','cabinet_creator/NOTICE'})
            for nome in ('LICENSE','NOTICE'):
                self.assertEqual(pacote.read('cabinet_creator/'+nome),(RAIZ/nome).read_bytes())
            self.assertIn(b'CC0 1.0 Universal',pacote.read('cabinet_creator/LICENSE'))

    def test_recriar_pacote_descarta_conteudo_da_versao_anterior(self):
        (self.pkg/'primeiro.py').write_bytes(b'antigo')
        self.gerar()
        (self.pkg/'primeiro.py').unlink()
        (self.pkg/'atual.py').write_bytes(b'novo')
        with zipfile.ZipFile(self.gerar()) as pacote:
            self.assertNotIn('cabinet_creator/primeiro.py',pacote.namelist())
            self.assertEqual(pacote.read('cabinet_creator/atual.py'),b'novo')
            self.assertEqual(pacote.read('cabinet_creator/LICENSE'),(RAIZ/'LICENSE').read_bytes())


resultado=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestEmpacotamento))
if not resultado.wasSuccessful():raise RuntimeError('Falha nas provas de empacotamento')
