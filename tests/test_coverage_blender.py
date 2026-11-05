"""Run: blender --background --factory-startup --python-exit-code 1 --python tests/test_coverage_blender.py

Harness coverage contract. Fail when:
- No test mentions a registered class (operator, gizmo, panel, shelf, etc.) and SEM_TESTE_ACEITO has no justified exemption.
- An entry in SEM_TESTE_ACEITO has gained coverage; this list may only shrink.
- A suite has no runner floor, which would let deleted tests pass silently.
- No test checks a stored snapshot.

Untested functionality fails here on introduction, rather than months later when someone notices it stopped working."""
import glob
import os
import re
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import importlib.util

import bpy  # noqa: F401  (the runner executes everything inside Blender)

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import archy_builder as addon  # noqa: E402

# Class -> reason it is not yet tested. This list may only shrink:
# remove each entry when covered; the test below enforces this.
SEM_TESTE_ACEITO = {
    'OBJECT_OT_abrir_asset_browser':
        'Only the unregistered legacy panel calls it; splits an area',
    'VIEW3D_AST_archy_builder': 'AssetShelf: native Blender drag',
    'OBJECT_OT_registrar_bibliotecas':
        'Changes USER preferences (asset_libraries)',
    'OBJECT_OT_modo_medidas':
        'Only the unregistered legacy panel calls it',
    'OBJECT_OT_definir_tamanho':
        'Only the unregistered legacy panel calls it',
}


def _texto_dos_testes():
    arquivos = [c for c in glob.glob(os.path.join(AQUI, '*.py'))
                if os.path.basename(c) != os.path.basename(__file__)]
    textos = []
    for caminho in arquivos:
        with open(caminho, encoding='utf-8') as f:
            textos.append(f.read())
    return '\n'.join(textos)


def _chaves(classe):
    chaves = {classe.__name__}
    idname = getattr(classe, 'bl_idname', '') or ''
    if '.' in idname:
        chaves.add(idname.split('.', 1)[1])      # cabinet_xxx
    elif idname and idname not in (classe.__name__, addon.__name__):
        # The preferences bl_idname is the package name, present in every
        # 'import archy_builder'; that would count as coverage without testing it.
        chaves.add(idname)
    return chaves


class TestCobertura(unittest.TestCase):

    def test_library_timeout_survives_english_suite_rename(self):
        spec = importlib.util.spec_from_file_location(
            'archy_test_runner', os.path.join(AQUI, 'run_tests.py'))
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        output = SimpleNamespace(stdout='Ran 100 tests\nOK\n', stderr='', returncode=0)
        with patch.object(runner.subprocess, 'run', return_value=output) as execute:
            for name, seconds in (('library', 600), ('coverage', 300)):
                with self.subTest(suite=name):
                    self.assertTrue(runner._rodar('blender', name, 'suite.py', False)['ok'])
                    self.assertEqual(execute.call_args.kwargs['timeout'], seconds)

    def setUp(self):
        self.texto = _texto_dos_testes()

    def citado(self, classe):
        return any(re.search(r'\b%s\b' % re.escape(k), self.texto)
                   for k in _chaves(classe))

    def test_toda_classe_registrada_tem_teste(self):
        sem = sorted(c.__name__ for c in addon.CLASSES
                     if not self.citado(c)
                     and c.__name__ not in SEM_TESTE_ACEITO)
        self.assertFalse(sem, "Class(es) with no test coverage: %s -- add a test or justify an exemption in SEM_TESTE_ACEITO" % sem)

    def test_lista_de_excecoes_so_encolhe(self):
        nomes = {c.__name__ for c in addon.CLASSES}
        sobrando = sorted(n for n in SEM_TESTE_ACEITO if n not in nomes)
        self.assertFalse(sobrando, "Exemption for a class that no longer exists: %s" % sobrando)
        ja_cobertas = sorted(c.__name__ for c in addon.CLASSES
                             if c.__name__ in SEM_TESTE_ACEITO
                             and self.citado(c))
        self.assertFalse(ja_cobertas, "Already covered; remove from SEM_TESTE_ACEITO: %s" % ja_cobertas)

    def test_toda_suite_tem_piso_no_executor(self):
        with open(os.path.join(AQUI, 'run_tests.py'), encoding='utf-8') as f:
            executor = f.read()
        piso = re.search(r'PISO = \{(.*?)\}', executor, re.S).group(1)
        suites = [re.match(r'test_(.+)_blender\.py', os.path.basename(c)).group(1)
                  for c in glob.glob(os.path.join(AQUI, 'test_*_blender.py'))]
        suites += [os.path.splitext(os.path.basename(c))[0]
                   for c in glob.glob(os.path.join(AQUI, 'gui_*.py'))]
        sem_piso = sorted(s for s in suites if "'%s'" % s not in piso)
        self.assertFalse(sem_piso, "Suite without a floor in run_tests.PISO: %s"
                         % sem_piso)

    def test_todo_snapshot_e_conferido(self):
        with open(os.path.join(AQUI, 'test_snapshot_blender.py'),
                  encoding='utf-8') as f:
            suite = f.read()
        orfaos = sorted(
            os.path.splitext(os.path.basename(c))[0]
            for c in glob.glob(os.path.join(AQUI, 'snapshots', '*.json'))
            if "'%s'" % os.path.splitext(os.path.basename(c))[0] not in suite)
        self.assertFalse(orfaos, "Snapshot not checked by any test: %s" % orfaos)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestCobertura)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError("Coverage contract failed")
