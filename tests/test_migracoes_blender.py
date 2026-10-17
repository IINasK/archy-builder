"""Ferramentas de manutencao: somente pastas temporarias e --help.

Nao executa migracoes sobre a biblioteca real nem importa DXFs do usuario.
"""
import contextlib
import importlib
import inspect
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
import cabinet_creator as addon
import ajustar_encaixes_promob as base
import integrar_bibliotecas_promob as integracao

SCRIPTS = ('ajustar_encaixes_promob', 'ajustar_abertura_esquerda',
           'ajustar_dobradicas_promob', 'ajustar_fundos_portas_promob',
           'ajustar_portas_promob', 'atualizar_fotos_biblioteca',
           'auditar_integracao_promob', 'integrar_bibliotecas_promob',
           'refinar_biblioteca249', 'refinar_cantos_promob',
           'refinar_diagonais251', 'refinar_diagonais252')


class TestMigracoes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cabinet_migracao_')
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.biblioteca = self.raiz / 'biblioteca'
        self.biblioteca.mkdir()
        self.destino = self.raiz / 'preparo'

    def preparar_arquivos(self):
        self.destino.mkdir()
        for pasta in ('originais', 'novos'):
            (self.destino / pasta).mkdir()
        arquivos = []
        for nome in ('a.blend', 'b.png'):
            (self.biblioteca / nome).write_bytes(('antes ' + nome).encode())
            shutil.copy2(self.biblioteca / nome, self.destino / 'originais' / nome)
            (self.destino / 'novos' / nome).write_bytes(('depois ' + nome).encode())
            arquivos.append(dict(nome=nome, original=base.digital(self.biblioteca / nome),
                                 novo=base.digital(self.destino / 'novos' / nome)))
        manifesto = dict(biblioteca=str(self.biblioteca), arquivos=arquivos,
                         fontes={}, modulos=[], publicado=False)
        (self.destino / 'manifesto.json').write_text(json.dumps(manifesto), encoding='utf-8')
        return manifesto

    def hashes(self):
        return {p.name: base.digital(p) for p in self.biblioteca.iterdir() if p.is_file()}

    def test_destino_externo_e_pastas_internas_com_capitalizacao(self):
        base.validar_destino(str(self.biblioteca), str(self.destino))
        for destino in (self.biblioteca, self.biblioteca / 'preparo'):
            with self.subTest(destino=destino), self.assertRaises(ValueError):
                base.validar_destino(str(self.biblioteca).upper(), str(destino))

    def test_validacao_resolve_alias_de_pasta_antes_de_comparar(self):
        alias = str(self.raiz / 'alias')
        realpath = os.path.realpath
        with patch.object(base.os.path, 'realpath', side_effect=lambda p:
                          str(self.biblioteca / 'preparo') if p == alias else realpath(p)):
            with self.assertRaises(ValueError):
                base.validar_destino(str(self.biblioteca), alias)

    def test_todas_as_preparacoes_recusam_escrever_dentro_da_biblioteca(self):
        for nome in SCRIPTS[:-1]:
            mod = importlib.import_module(nome)
            args = {p: str(self.raiz / 'fonte-inexistente')
                    for p in inspect.signature(mod.preparar).parameters}
            args.update(biblioteca=str(self.biblioteca), destino=str(self.biblioteca / 'preparo'))
            with self.subTest(script=nome), self.assertRaises(ValueError):
                mod.preparar(**args)
            self.assertEqual(list(self.biblioteca.iterdir()), [])

    def test_ajuda_dos_doze_scripts_nao_executa_migracao(self):
        diag = importlib.import_module('refinar_diagonais251')
        anterior = diag.validar
        try:
            for nome in SCRIPTS:
                saida = io.StringIO()
                with self.subTest(script=nome), patch.object(sys, 'argv', [nome, '--', '--help']), \
                     contextlib.redirect_stdout(saida), self.assertRaises(SystemExit) as fim:
                    runpy.run_path(str(RAIZ / (nome + '.py')), run_name='__main__')
                self.assertEqual(fim.exception.code, 0)
                self.assertIn('--destino', saida.getvalue())
        finally:
            diag.validar = anterior
        self.assertEqual(list(self.biblioteca.iterdir()), [])

    def test_publicacao_confere_todos_os_hashes_antes_da_primeira_escrita(self):
        self.preparar_arquivos();antes = self.hashes()
        (self.destino / 'novos' / 'b.png').write_bytes(b'alterado depois da verificacao')
        for mod in (base, integracao):
            with self.subTest(publicador=mod.__name__), self.assertRaises(RuntimeError):
                mod.publicar(str(self.destino))
            self.assertEqual(self.hashes(), antes)

    def test_publicacao_conserva_backup_e_atualiza_manifesto(self):
        self.preparar_arquivos();antes = self.hashes()
        base.publicar(str(self.destino))
        self.assertTrue(json.loads((self.destino / 'manifesto.json').read_text())['publicado'])
        for nome,sha in antes.items():
            self.assertEqual(base.digital(self.destino / 'originais' / nome), sha)
            self.assertEqual(base.digital(self.biblioteca / nome),
                             base.digital(self.destino / 'novos' / nome))

    def test_rollback_restaura_o_primeiro_arquivo_se_o_segundo_falhar(self):
        self.preparar_arquivos();antes = self.hashes();copiar = shutil.copyfile
        for mod in (base, integracao):
            def falhar(origem, alvo, *args, **kwargs):
                if str(origem).endswith(os.path.join('novos', 'b.png')):
                    raise OSError('Falha de copia simulada')
                return copiar(origem, alvo, *args, **kwargs)
            with self.subTest(publicador=mod.__name__), patch.object(shutil, 'copyfile', side_effect=falhar), \
                 self.assertRaises(OSError):
                mod.publicar(str(self.destino))
            self.assertEqual(self.hashes(), antes)
            self.assertFalse(json.loads((self.destino / 'manifesto.json').read_text())['publicado'])

    def test_nomes_de_manifesto_nao_escapam_da_pasta(self):
        for nome in ('../fora.blend', '..\\fora.blend', '/fora.blend'):
            with self.subTest(nome=nome), self.assertRaises(ValueError):
                base.caminho_da_peca(str(self.biblioteca), nome)


if __name__ == '__main__':
    addon.register()
    try:
        resultado = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(TestMigracoes))
    finally:
        addon.unregister()
    if not resultado.wasSuccessful():
        raise RuntimeError('Falha nos testes das migracoes')
