"""Harness unico: roda TODAS as suites em TODAS as versoes do Blender.

Execute (so' o Blender e' necessario; o Python dele roda isto):

    blender --background --factory-startup --python tests/rodar_testes.py
    blender ... --python tests/rodar_testes.py -- --versoes 5.2 --suites hud
    blender ... --python tests/rodar_testes.py -- --gui     (inclui GUI)

Cada suite roda num Blender SEPARADO (`--factory-startup`), em paralelo:
uma suite nao herda cena, preferencias nem estado de modulo de outra.
O processo termina com codigo 1 se qualquer suite falhar, nao rodar ou
rodar menos testes do que o piso gravado -- teste que some calado e'
justamente a quebra oculta que este harness existe para pegar.

Suites `tests/test_*_blender.py` sao headless. Suites `tests/gui_*.py`
abrem uma janela de verdade (eventos simulados); so' rodam com --gui.
"""
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
# Piso de testes por suite: cair abaixo disto = teste apagado/pulado sem
# querer. Subir o numero quando a suite crescer (nunca baixar calado).
# v304: portas -1, gavetas -3, geometria -1 de proposito -- os testes do
# ima em Python (`_alvos_do_ima`, `IndiceSnapGavetas`, rotulos) sairam com
# ele; o snap agora e' o nativo do Blender.
# v309: geometria -3 de proposito -- o detector de angulos (`pontos_notaveis`)
# saiu a pedido do usuario; ficam os testes de area e do snap da curva.
PISO = {
    'correcao_internos': 10,
    'auditoria_internos': 9,
    'paredes_composicao': 67,
    'paredes_edicao': 68,
    'organizacao': 9,
    'divisorias': 24,
    'estrutura': 51, 'gaveta': 71, 'portas': 154, 'hud': 174,
    'importacao': 80, 'puxadores': 24, 'snapshot': 7, 'operadores': 49, 'frentes': 29,
    'biblioteca': 84, 'cobertura': 4, 'gui_interacao': 58,
    'orcamento': 17, 'paredes': 15, 'armarios': 20, 'formas': 62, 'gavetas': 50,
    'geometria': 5, 'prateleiras': 53, 'migracoes': 11,
    'biblioteca_faixa': 31, 'gui_biblioteca_faixa': 7,
}
LIMITE_SEGUNDOS = 300


def _argumentos():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser(prog='rodar_testes')
    p.add_argument('--versoes', nargs='*', default=None,
                   help='ex.: 5.2 4.2 (padrao: todas as instaladas)')
    p.add_argument('--suites', nargs='*', default=None,
                   help='ex.: hud gaveta (padrao: todas)')
    p.add_argument('--gui', action='store_true',
                   help='inclui as suites que abrem janela (gui_*.py)')
    p.add_argument('--sequencial', action='store_true')
    p.add_argument('--atualizar', action='store_true',
                   help='regrava os snapshots (mudanca INTENCIONAL; revise o diff)')
    return p.parse_args(argv)


def _blenders(pedidas):
    achados = {}
    for exe in glob.glob(os.path.join(PASTA_BLENDER, 'Blender *', 'blender.exe')):
        versao = os.path.basename(os.path.dirname(exe)).split(' ', 1)[1]
        achados[versao] = exe
    if pedidas:
        faltando = [v for v in pedidas if v not in achados]
        if faltando:
            raise SystemExit('Blender nao instalado: %s' % ', '.join(faltando))
        return {v: achados[v] for v in pedidas}
    return dict(sorted(achados.items(), reverse=True))


def _suites(pedidas, gui):
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
        # janela de tamanho fixo (layout reproduzivel) e sem roubar o foco
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
                               # A biblioteca regrava a amostra e as miniaturas;
                               # esse I/O excedeu 300 s com os presets reparados.
                               timeout=600 if suite == 'biblioteca' else LIMITE_SEGUNDOS)
        texto, codigo = saida.stdout + saida.stderr, saida.returncode
    except subprocess.TimeoutExpired as e:
        texto = (e.stdout or '') + (e.stderr or '') if isinstance(
            e.stdout, str) else ''
        codigo = 'TEMPO'
    rodados = re.search(r'^Ran (\d+) tests?', texto, re.M)
    rodados = int(rodados.group(1)) if rodados else 0
    falhas = re.findall(r'^(?:FAIL|ERROR): (\S+)', texto, re.M)
    ok = codigo == 0 and re.search(r'^OK\b', texto, re.M) is not None
    piso = PISO.get(suite, 1)
    if ok and rodados < piso:
        ok = False
        falhas.append('rodou %d testes, piso e\' %d (teste sumiu?)'
                      % (rodados, piso))
    return {'ok': ok, 'rodados': rodados, 'falhas': falhas, 'codigo': codigo,
            'segundos': time.monotonic() - inicio, 'texto': texto}


def main():
    args = _argumentos()
    blenders = _blenders(args.versoes)
    suites = _suites(args.suites, args.gui)
    if not blenders or not suites:
        raise SystemExit('Nada para rodar (versoes=%s suites=%s)'
                         % (list(blenders), list(suites)))
    tarefas = [(v, exe, s, c, g) for v, exe in blenders.items()
               for s, (c, g) in suites.items()]
    # Suites de GUI disputam a tela: sempre uma de cada vez.
    paralelas = [t for t in tarefas if not t[4]]
    janelas = [t for t in tarefas if t[4]]
    resultados = {}
    trabalhadores = 1 if args.sequencial else min(6, os.cpu_count() or 2)
    with ThreadPoolExecutor(trabalhadores) as pool:
        # snapshot regravado por UMA versao so' (a primeira): duas
        # gravando o mesmo arquivo em paralelo dariam corrida
        primeira = next(iter(blenders))
        futuros = {pool.submit(_rodar, exe, s, c, g,
                               args.atualizar and v == primeira): (v, s)
                   for v, exe, s, c, g in paralelas}
        for futuro, chave in futuros.items():
            resultados[chave] = futuro.result()
    for v, exe, s, c, g in janelas:
        resultados[(v, s)] = _rodar(exe, s, c, g)

    print('\n' + '=' * 64)
    print('%-8s %-14s %6s %8s  %s' % ('versao', 'suite', 'testes', 'tempo', 'resultado'))
    print('-' * 64)
    falhou = False
    for (v, s), r in sorted(resultados.items()):
        estado = 'OK' if r['ok'] else 'FALHOU'
        falhou |= not r['ok']
        print('%-8s %-14s %6d %7.1fs  %s' % (v, s, r['rodados'],
                                            r['segundos'], estado))
        if not r['ok']:
            for f in r['falhas'][:10] or ['codigo de saida %s' % r['codigo']]:
                print('           - %s' % f)
    print('=' * 64)
    total = sum(r['rodados'] for r in resultados.values())
    print('%d testes em %d execucoes: %s' % (
        total, len(resultados), 'FALHOU' if falhou else 'TUDO OK'))
    if falhou:
        # o primeiro texto de falha inteiro ajuda a diagnosticar sem rodar de novo
        primeiro = next(r for r in resultados.values() if not r['ok'])
        print('\n--- saida da primeira suite que falhou (final) ---')
        print(primeiro['texto'][-4000:])
    sys.stdout.flush()
    if falhou:
        # Sem --python-exit-code o Blender sai com 0 mesmo apos excecao.
        os._exit(1)


try:
    main()
except SystemExit as e:
    # --python-exit-code so' vale para excecao; SystemExit(0) e' sucesso
    if e.code not in (0, None):
        raise RuntimeError('harness: %s' % e.code)
