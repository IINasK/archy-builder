"""Unified harness: run every suite in every Blender version.

Only Blender is required; its bundled Python can run this file:
    blender --background --factory-startup --python tests/run_tests.py
    blender ... --python tests/run_tests.py -- --versions 5.2 --suites hud
    blender ... --python tests/run_tests.py -- --gui     (includes GUI)

Each suite runs in a separate factory-startup Blender process, in parallel, without inheriting scenes, preferences or module state. Exit with code 1 if a suite fails, does not run or runs fewer tests than its recorded floor: silently missing tests are precisely the hidden failures this harness catches.

Suites tests/test_*_blender.py are headless. Suites tests/gui_*.py open a real window with simulated events and run only with --gui."""
import argparse
import glob
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTES = os.path.join(RAIZ, 'tests')
PASTA_BLENDER = r'C:\Program Files\Blender Foundation'
# Per-suite test floors: falling below one means tests were inadvertently deleted
# or skipped. Increase the floor as coverage grows; never silently lower it.
# v304 deliberately removed 1 door, 3 drawer and 1 geometry test with the
# Python snap engine (_alvos_do_ima, IndiceSnapGavetas and labels);
# snapping now uses Blender's native engine.
# v309 deliberately removed 3 geometry tests with the angle detector
# (pontos_notaveis), as requested; area and curve-snap tests remain.
PISO = {
    'language':8,
    'packaging':3,
    'installations':22,
    'masonry':16,
    'openings':9,
    'lighting':10,
    'rooms':61,
    'measurements':21,
    'visibility': 26,
    'creation_areas': 58,
    'editor': 21,
    'wall_selection': 45,
    'backs': 30,
    'welding': 16,
    'library_joints': 22,
    'internal_repairs': 10,
    'internal_audit': 9,
    'wall_layout': 73,
    'wall_editor': 86,
    'organization': 12,
    'partitions': 42,
    'structure': 51, 'sidebar': 86, 'doors': 165, 'hud': 214,
    'importing': 80, 'handles': 40, 'snapshot': 7, 'operators': 59, 'fronts': 29,
    'library': 86, 'coverage': 5, 'gui_interaction': 63,
    'estimates': 17, 'walls': 39, 'cabinets': 20, 'shapes': 62, 'drawers': 62,
    'geometry': 5, 'shelves': 60, 'migrations': 14,
    'library_strip': 31, 'gui_library_strip': 7,
}
LIMITE_SEGUNDOS = 300


def _argumentos():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser(prog='run_tests')
    p.add_argument('--versions', nargs='*', default=None, help='e.g. 5.2 4.2 (default: all installed)', dest='versoes', metavar='VERSIONS')
    p.add_argument('--suites', nargs='*', default=None,
                   help='e.g. hud sidebar (default: all)')
    p.add_argument('--gui', action='store_true',
                   help='include suites that open a window (gui_*.py)')
    p.add_argument('--sequential', action='store_true', dest='sequencial')
    p.add_argument('--update', action='store_true', help='rewrite snapshots (intentional changes only; review the diff)', dest='atualizar')
    return p.parse_args(argv)


def _blenders(pedidas):
    achados = {}
    for exe in glob.glob(os.path.join(PASTA_BLENDER, 'Blender *', 'blender.exe')):
        versao = os.path.basename(os.path.dirname(exe)).split(' ', 1)[1]
        achados[versao] = exe
    if pedidas:
        faltando = [v for v in pedidas if v not in achados]
        if faltando:
            raise SystemExit('Blender not installed: %s' % ', '.join(faltando))
        return {v: achados[v] for v in pedidas}
    return dict(sorted(achados.items(), reverse=True))


SUITE_ALIASES = {'empacotamento': 'packaging', 'instalacoes': 'installations', 'alvenaria': 'masonry', 'esquadrias': 'openings', 'iluminacao': 'lighting', 'ambientes': 'rooms', 'medidas': 'measurements', 'visibilidade': 'visibility', 'areas_criacao': 'creation_areas', 'paredes_selecao': 'wall_selection', 'fundos': 'backs', 'solda': 'welding', 'soldas_biblioteca': 'library_joints', 'correcao_internos': 'internal_repairs', 'auditoria_internos': 'internal_audit', 'paredes_composicao': 'wall_layout', 'paredes_edicao': 'wall_editor', 'organizacao': 'organization', 'divisorias': 'partitions', 'estrutura': 'structure', 'gaveta': 'sidebar', 'portas': 'doors', 'importacao': 'importing', 'puxadores': 'handles', 'operadores': 'operators', 'frentes': 'fronts', 'biblioteca': 'library', 'cobertura': 'coverage', 'orcamento': 'estimates', 'paredes': 'walls', 'armarios': 'cabinets', 'formas': 'shapes', 'gavetas': 'drawers', 'geometria': 'geometry', 'prateleiras': 'shelves', 'migracoes': 'migrations', 'biblioteca_faixa': 'library_strip', 'gui_interacao': 'gui_interaction', 'gui_biblioteca_faixa': 'gui_library_strip'}


def _suites(pedidas, gui):
    if pedidas:
        pedidas = [SUITE_ALIASES.get(nome, nome) for nome in pedidas]
    nomes = {}
    for caminho in sorted(glob.glob(os.path.join(TESTES, 'test_*_blender.py'))):
        nome = re.match(r'test_(.+)_blender\.py', os.path.basename(caminho)).group(1)
        nomes[nome] = (caminho, False)
    if gui:
        for caminho in sorted(glob.glob(os.path.join(TESTES, 'gui_*.py'))):
            nome = os.path.splitext(os.path.basename(caminho))[0]
            nomes[nome] = (caminho, True)
    if pedidas:
        return {n: c for n, c in nomes.items() if n in pedidas}
    return nomes


def _rodar(blender, suite, caminho, gui, atualizar=False):
    comando = [blender, '--factory-startup', '--python-exit-code', '1']
    if gui:
        # Fixed window dimensions provide reproducible layouts without stealing focus.
        comando += ['--enable-event-simulate', '--no-window-focus',
                    '--window-geometry', '0', '0', '1600', '900']
    else:
        comando += ['--background']
    comando += ['--python', caminho]
    inicio = time.monotonic()
    try:
        ambiente = dict(os.environ)
        if atualizar:
            ambiente['CABINET_ATUALIZAR_SNAPSHOTS'] = '1'
        saida = subprocess.run(comando, cwd=RAIZ, capture_output=True, env=ambiente,
                               text=True, encoding='utf-8', errors='replace',
                               # The library rewrites the sample and thumbnails;
                               # this I/O exceeded 300 s with the repaired presets.
                               timeout=600 if suite == 'library' else LIMITE_SEGUNDOS)
        texto, codigo = saida.stdout + saida.stderr, saida.returncode
    except subprocess.TimeoutExpired as e:
        texto = (e.stdout or '') + (e.stderr or '') if isinstance(
            e.stdout, str) else ''
        codigo = 'TIMEOUT'
    rodados = re.search(r'^Ran (\d+) tests?', texto, re.M)
    rodados = int(rodados.group(1)) if rodados else 0
    falhas = re.findall(r'^(?:FAIL|ERROR): (\S+)', texto, re.M)
    ok = codigo == 0 and re.search(r'^OK\b', texto, re.M) is not None
    piso = PISO.get(suite, 1)
    if ok and rodados < piso:
        ok = False
        falhas.append('ran %d tests, expected at least %d (missing tests?)'
                      % (rodados, piso))
    return {'ok': ok, 'rodados': rodados, 'falhas': falhas, 'codigo': codigo,
            'segundos': time.monotonic() - inicio, 'texto': texto}


def main():
    args = _argumentos()
    blenders = _blenders(args.versoes)
    suites = _suites(args.suites, args.gui)
    if not blenders or not suites:
        raise SystemExit('Nothing to run (versions=%s suites=%s)'
                         % (list(blenders), list(suites)))
    tarefas = [(v, exe, s, c, g) for v, exe in blenders.items()
               for s, (c, g) in suites.items()]
    # GUI suites compete for the screen, so always run them sequentially.
    paralelas = [t for t in tarefas if not t[4]]
    janelas = [t for t in tarefas if t[4]]
    resultados = {}
    trabalhadores = 1 if args.sequencial else min(6, os.cpu_count() or 2)
    with ThreadPoolExecutor(trabalhadores) as pool:
        # Only the first version rewrites snapshots; two versions writing the same
        # file concurrently would race.
        primeira = next(iter(blenders))
        futuros = {pool.submit(_rodar, exe, s, c, g,
                               args.atualizar and v == primeira): (v, s)
                   for v, exe, s, c, g in paralelas}
        for futuro, chave in futuros.items():
            resultados[chave] = futuro.result()
    for v, exe, s, c, g in janelas:
        resultados[(v, s)] = _rodar(exe, s, c, g)

    print('\n' + '=' * 64)
    print('%-8s %-14s %6s %8s  %s' % ('version', 'suite', 'tests', 'time', 'result'))
    print('-' * 64)
    falhou = False
    for (v, s), r in sorted(resultados.items()):
        estado = 'OK' if r['ok'] else 'FAILED'
        falhou |= not r['ok']
        print('%-8s %-14s %6d %7.1fs  %s' % (v, s, r['rodados'],
                                            r['segundos'], estado))
        if not r['ok']:
            for f in r['falhas'][:10] or ['exit code %s' % r['codigo']]:
                print('           - %s' % f)
    print('=' * 64)
    total = sum(r['rodados'] for r in resultados.values())
    print('%d tests across %d runs: %s' % (
        total, len(resultados), 'FAILED' if falhou else 'ALL PASSED'))
    if falhou:
        # The complete first failure message helps diagnose issues without another run.
        primeiro = next(r for r in resultados.values() if not r['ok'])
        print('\n--- first failed suite output (tail) ---')
        print(primeiro['texto'][-4000:])
    sys.stdout.flush()
    if falhou:
        # Without --python-exit-code, Blender exits with 0 even after an exception.
        os._exit(1)


if __name__ == '__main__':
    try:
        main()
    except SystemExit as e:
        # --python-exit-code applies only to exceptions; SystemExit(0) is success.
        if e.code not in (0, None):
            raise RuntimeError('harness: %s' % e.code)
