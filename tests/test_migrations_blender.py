"""Ferramentas de manutencao: somente pastas temporarias e --help.

Nao executa migracoes sobre a biblioteca real nem importa DXFs do usuario.
"""
import ast
import contextlib
import importlib
import inspect
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import bpy

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
import cabinet_creator as addon
import tools.migrations.adjust_fits as base
import tools.library.integrate_dxf_library as integracao

SCRIPTS = (
    'tools.migrations.consolidate_library_variants',
    'tools.migrations.repair_library_internals',
    'tools.migrations.adjust_fits',
    'tools.migrations.adjust_left_opening',
    'tools.migrations.adjust_hinges',
    'tools.migrations.adjust_backs_and_doors',
    'tools.migrations.adjust_doors',
    'tools.migrations.refresh_library_photos',
    'tools.migrations.audit_and_repair_integration',
    'tools.library.integrate_dxf_library',
    'tools.migrations.refine_library_connections_v249',
    'tools.migrations.refine_corners',
    'tools.migrations.refine_diagonal_fronts_v251',
    'tools.migrations.standardize_profile_handles',
    'tools.migrations.repair_reversed_curved_doors',
    'tools.migrations.refine_library_joints',
    'tools.migrations.refine_diagonal_clearance_v252',
)


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

    def test_ajuda_dos_scripts_nao_executa_migracao(self):
        diag = importlib.import_module('tools.migrations.refine_diagonal_fronts_v251')
        anterior = diag.validar
        try:
            for nome in SCRIPTS + ('tools.audit.audit_library_internals',):
                saida = io.StringIO()
                with self.subTest(script=nome), patch.object(sys, 'argv', [nome, '--', '--help']), \
                     contextlib.redirect_stdout(saida), self.assertRaises(SystemExit) as fim:
                    runpy.run_path(str(RAIZ.joinpath(*nome.split('.')).with_suffix('.py')), run_name='__main__')
                self.assertEqual(fim.exception.code, 0)
                self.assertIn('--destino', saida.getvalue())
        finally:
            diag.validar = anterior
        self.assertEqual(list(self.biblioteca.iterdir()), [])

    def test_direct_cli_from_external_directory_keeps_help_read_only(self):
        environment = os.environ.copy()
        environment.pop('PYTHONPATH', None)
        for relative in ('migrations/adjust_hinges.py', 'migrations/adjust_doors.py',
                         'library/integrate_dxf_library.py', 'audit/audit_library_internals.py'):
            with self.subTest(script=relative):
                result = subprocess.run(
                    [bpy.app.binary_path, '--background', '--factory-startup',
                     '--python-exit-code', '1', '--python', str(RAIZ / 'tools' / relative),
                     '--', '--help'], cwd=self.raiz, env=environment,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding='utf-8', errors='replace', timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn('--destino', result.stdout)
                self.assertNotIn('Traceback', result.stdout)
        self.assertEqual(list(self.raiz.iterdir()), [self.biblioteca])

    def test_source_paths_are_explicit_before_preparing(self):
        scripts = (
            ('library/import_dxf_library.py', []),
            ('library/integrate_dxf_library.py', ['--destino', str(self.destino)]),
            ('migrations/adjust_doors.py', ['--destino', str(self.destino)]),
            ('migrations/audit_and_repair_integration.py', ['--destino', str(self.destino)]),
            ('migrations/refine_corners.py', ['--destino', str(self.destino)]),
            ('migrations/repair_library_internals.py', ['--destino', str(self.destino)]),
        )
        for relative, arguments in scripts:
            errors = io.StringIO()
            with self.subTest(script=relative), \
                 patch.object(sys, 'argv', [relative, '--', *arguments]), \
                 contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as result:
                runpy.run_path(str(RAIZ / 'tools' / relative), run_name='__main__')
            self.assertEqual(result.exception.code, 2)
            self.assertIn('source', errors.getvalue().lower())
            self.assertEqual(list(self.raiz.iterdir()), [self.biblioteca])

    def test_hardware_resources_stay_in_addon_after_relocation(self):
        resources = (
            ('hardware/extract_hinge.py', 'DESTINO', 'ferragens'),
            ('hardware/extract_hinge_wireframe.py', 'JSON', 'ferragens/dobradica_reta.json'),
            ('hardware/extract_profile_handle.py', 'DESTINO', 'ferragens'),
            ('hardware/extract_edge_handle.py', 'DESTINO', 'ferragens'),
            ('hardware/extract_light_track.py', 'DESTINO', 'ferragens/trilho_moldura.json'),
            ('hardware/extract_frame_track.py', 'DESTINO', 'ferragens/trilho_moldura.json'),
            ('hardware/generate_screw.py', 'DESTINO', 'ferragens'),
            ('hardware/replace_hinge_screws.py', 'FERRAGENS', 'ferragens'),
            ('library/generate_default_photos.py', 'PASTA', 'fotos'),
        )
        for relative, variable, expected in resources:
            source = RAIZ / 'tools' / relative
            tree = ast.parse(source.read_text(encoding='utf-8'))
            # Evaluate only path declarations: importing extractors would overwrite real assets.
            paths = [node for node in tree.body if isinstance(node, ast.Assign)
                     and all(isinstance(target, ast.Name) and target.id in ('AQUI', variable)
                             for target in node.targets)]
            scope = {'__file__': str(source), 'Path': Path, 'os': os}
            exec(compile(ast.Module(body=paths, type_ignores=[]), str(source), 'exec'), scope)
            with self.subTest(script=relative):
                self.assertEqual(Path(scope[variable]), RAIZ / 'cabinet_creator' / expected)

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

    def preparar_retiradas(self):
        mod=importlib.import_module('tools.migrations.consolidate_library_variants')
        itens=[dict(arquivo=n+'.blend',nome=n,tipo='modulo',n1='Armarios',n2='Cozinha',n3='Diagonais',
                    niveis=['Armarios','Cozinha','Inferiores','Diagonais'],extra='preservado')
               for n in ('Curvo','RetoEsquerdo','RetoDireito')]
        for i in itens:
            for extensao in ('.blend','.png'):
                (self.biblioteca/Path(i['arquivo']).with_suffix(extensao)).write_bytes(i['nome'].encode())
        (self.biblioteca/'indice.json').write_text(json.dumps(itens),encoding='utf-8')
        (self.biblioteca/'blender_assets.cats.txt').write_text('UUID original',encoding='utf-8')
        plano=[dict(arquivo='Curvo.blend',motivo='Diagonal com frente curva'),
               dict(arquivo='RetoEsquerdo.blend',motivo='Espelhado',mantido='RetoDireito.blend')]
        mod.preparar(str(self.biblioteca),str(self.destino),plano)
        return mod,itens

    def test_retirada_conserva_variante_reta_metadados_catalogo_e_backup(self):
        mod,itens=self.preparar_retiradas();antes=self.hashes()
        mod.publicar(self.destino)
        self.assertEqual(json.loads((self.biblioteca/'indice.json').read_text()),[itens[-1]])
        self.assertEqual((self.biblioteca/'blender_assets.cats.txt').read_text(),'UUID original')
        for nome in ('Curvo.blend','Curvo.png','RetoEsquerdo.blend','RetoEsquerdo.png','indice.json'):
            self.assertEqual(base.digital(self.destino/'originais'/nome),antes[nome])
        self.assertFalse((self.biblioteca/'Curvo.blend').exists())
        self.assertTrue((self.biblioteca/'RetoDireito.blend').exists())

    def test_retirada_recusa_backup_ou_biblioteca_alterados_antes_de_escrever(self):
        mod,itens=self.preparar_retiradas()
        for local in (self.biblioteca/'RetoDireito.blend',self.destino/'originais/Curvo.png'):
            original=local.read_bytes();local.write_bytes(b'alterado');antes=self.hashes()
            with self.assertRaises(RuntimeError):mod.publicar(self.destino)
            self.assertEqual(self.hashes(),antes);local.write_bytes(original)

    def test_retirada_falha_na_exclusao_restaura_arquivos_e_indice(self):
        mod,itens=self.preparar_retiradas();antes=self.hashes();excluir=Path.unlink
        def falhar(caminho,*args,**kwargs):
            if caminho.name=='RetoEsquerdo.png':raise OSError('Falha simulada')
            return excluir(caminho,*args,**kwargs)
        with patch.object(Path,'unlink',falhar),self.assertRaises(OSError):mod.publicar(self.destino)
        self.assertEqual(self.hashes(),antes)
        self.assertFalse(json.loads((self.destino/'manifesto.json').read_text())['publicado'])


if __name__ == '__main__':
    addon.register()
    try:
        resultado = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(TestMigracoes))
    finally:
        addon.unregister()
    if not resultado.wasSuccessful():
        raise RuntimeError('Falha nos testes das migracoes')
