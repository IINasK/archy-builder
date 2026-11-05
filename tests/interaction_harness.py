"""Interface test harness using real click and key events.

Follows Blender's official tests/python/ui_simulate and easy_keys pattern: open a window with --enable-event-simulate, which ignores physical mouse and keyboard input. Each test is a generator advanced by a timer; yield lets the main loop process events and redraw. Yielding datetime.timedelta(...) waits for that elapsed time.

Known limitations (Blender source; see CLAUDE.md):
- The simulator does not generate DOUBLE_CLICK (check_double_click = false). Two clicks arrive as PRESS, RELEASE, PRESS, RELEASE. Modal operators never receive DOUBLE_CLICK, even from a physical mouse, so this covers modals; keymap DOUBLE_CLICK for three-level selection requires physical input.
- Timer exceptions are otherwise only printed. This harness captures them and exits with os._exit(codigo); the runner also enforces a timeout.

Run through: blender ... --python tests/run_tests.py -- --gui"""
import datetime
import os
import sys
import time
import traceback

import bpy
from bpy_extras import view3d_utils

TICKS = 4               # Upstream uses 4 ticks: 3 works, but 4 provides a safety margin.
LIMITE_SEGUNDOS = 120


class Mouse:
    """Simulated mouse and keyboard input in window coordinates."""

    def __init__(self, janela):
        self.janela = janela
        self.x, self.y = janela.width // 2, janela.height // 2

    def mover(self, x, y):
        self.x, self.y = int(round(x)), int(round(y))
        self.janela.event_simulate('MOUSEMOVE', 'NOTHING', x=self.x, y=self.y)

    def apertar(self, botao='LEFTMOUSE', **mods):
        """mods: alt/ctrl/shift=True. The simulator includes only explicitly supplied modifiers; physical keyboard state is ignored."""
        self.janela.event_simulate(botao, 'PRESS', x=self.x, y=self.y, **mods)

    def soltar(self, botao='LEFTMOUSE', **mods):
        self.janela.event_simulate(botao, 'RELEASE', x=self.x, y=self.y,
                                   **mods)

    def clicar(self, botao='LEFTMOUSE', **mods):
        self.apertar(botao, **mods)
        self.soltar(botao, **mods)

    def tecla(self, tipo, caractere=''):
        if caractere:
            self.janela.event_simulate(tipo, 'PRESS', unicode=caractere,
                                       x=self.x, y=self.y)
        else:
            self.janela.event_simulate(tipo, 'PRESS', x=self.x, y=self.y)
        self.janela.event_simulate(tipo, 'RELEASE', x=self.x, y=self.y)

    def digitar(self, texto):
        # '+' and '*' are available as event types only on the numeric keypad.
        nomes = {'.': 'PERIOD', ',': 'COMMA', '-': 'MINUS',
                 '+': 'NUMPAD_PLUS', '*': 'NUMPAD_ASTERIX', '/': 'SLASH',
                 ' ': 'SPACE'}
        nomes.update({str(i): n for i, n in enumerate(
            ('ZERO', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN',
             'EIGHT', 'NINE'))})
        for c in texto:
            self.tecla(nomes.get(c, c.upper()), c)


def viewport_principal(janela, gaveta=None):
    """Return (area, regiao, region_3d) for the largest VIEW_3D other than the sidebar."""
    areas = [a for a in janela.screen.areas
             if a.type == 'VIEW_3D' and a != gaveta]
    area = max(areas, key=lambda a: a.width * a.height)
    regiao = next(r for r in area.regions if r.type == 'WINDOW')
    return area, regiao, area.spaces.active.region_3d


def na_tela(regiao, rv3d, ponto):
    """Convert a 3D point to window coordinates for event_simulate."""
    p = view3d_utils.location_3d_to_region_2d(regiao, rv3d, ponto)
    return None if p is None else (regiao.x + p.x, regiao.y + p.y)


class Pular(Exception):
    """Raise inside a test to skip it with a reason."""


class ErrosDeCallback:
    """A sys.stderr wrapper that counts callback tracebacks from sidebar drawing, gizmos and timers. Blender otherwise only prints them, allowing tests to pass with a broken sidebar (v140: tabs, icons and background disappeared while all 26 tests passed). Exclude tracebacks from harness assertion failures."""
    MARCA = 'Traceback (most recent call last)'

    def __init__(self, original):
        self.original = original
        self.contagem = 0
        self.proprio = False
        self.trecho = ''
        self._colhendo = 0

    def write(self, texto):
        if not self.proprio:
            if self.MARCA in texto:
                self.contagem += 1
                if not self.trecho:
                    self._colhendo = 2000
            if self._colhendo > 0:
                self.trecho += texto[:self._colhendo]
                self._colhendo -= len(texto)
        return self.original.write(texto)

    def flush(self):
        self.original.flush()

    def __getattr__(self, nome):
        return getattr(self.original, nome)


class Resultado:
    def __init__(self):
        self.rodados, self.falhas, self.pulados = 0, [], []


def rodar(testes, preparar=None, limpar=None):
    """Run test generators sequentially, emitting unittest-style output (Ran N tests / OK / FAIL:) for the runner to count."""
    prefs = bpy.context.preferences
    prefs.view.show_splash = False
    prefs.view.smooth_view = 0
    prefs.view.use_save_prompt = False
    prefs.filepaths.use_auto_save_temporary_files = False
    janela = bpy.context.window_manager.windows[0]
    mouse = Mouse(janela)
    resultado = Resultado()
    erros = ErrosDeCallback(sys.stderr)
    sys.stderr = erros
    fila = list(testes)
    estado = {'gerador': None, 'nome': '', 'ticks': 0,
              'prazo': time.monotonic() + LIMITE_SEGUNDOS, 'preparado': False}

    def sair(codigo):
        print('\n' + '-' * 70)
        print('Ran %d tests' % resultado.rodados)
        pulados = (' (skipped=%d)' % len(resultado.pulados)
                   if resultado.pulados else '')
        print('OK' + pulados if not resultado.falhas else
              'FAILED (failures=%d)' % len(resultado.falhas))
        sys.stdout.flush()
        os._exit(codigo)   # sys.exit inside a timer sometimes leaves the window open.

    def proximo():
        if estado['gerador'] is None:
            if not fila:
                sair(1 if resultado.falhas else 0)
            teste = fila.pop(0)
            estado['nome'] = teste.__name__
            if limpar is not None:
                limpar(janela)
            estado['gerador'] = teste(janela, mouse)
            estado['erros'] = erros.contagem
            erros.trecho = ''
            resultado.rodados += 1
            print('%s ...' % estado['nome'])
        try:
            valor = next(estado['gerador'])
        except StopIteration:
            estado['gerador'] = None
            if erros.contagem > estado['erros']:
                # A callback failed during the test: count it as a failure even if
                # all assertions passed.
                print('FAIL: %s' % estado['nome'])
                print('%d callback error(s) (drawing/gizmo/timer):'
                      % (erros.contagem - estado['erros']))
                print(erros.trecho)
                resultado.falhas.append(estado['nome'])
                return 0.0
            print('%s ... ok' % estado['nome'])
            return 0.0
        except Pular as motivo:
            print('%s ... skipped %r' % (estado['nome'], str(motivo)))
            resultado.pulados.append(estado['nome'])
            estado['gerador'] = None
            return 0.0
        except Exception:
            print('FAIL: %s' % estado['nome'])
            erros.proprio = True
            traceback.print_exc()
            erros.proprio = False
            resultado.falhas.append(estado['nome'])
            estado['gerador'] = None
            return 0.0
        if isinstance(valor, datetime.timedelta):
            return valor.total_seconds()
        return 0.0

    def passo():
        try:
            if time.monotonic() > estado['prazo']:
                print('FAIL: TIMEOUT in %s' % estado['nome'])
                resultado.falhas.append(estado['nome'] + ' (timeout)')
                sair(3)
            if not estado['preparado']:
                estado['preparado'] = True
                if preparar is not None:
                    preparar(janela)
                return 0.5
            if getattr(bpy.context.window_manager,
                       'is_event_handling_break', False):
                return 0.0
            if estado['ticks'] < TICKS:
                estado['ticks'] += 1
                return 0.0
            estado['ticks'] = 0
            return proximo()
        except Exception:
            erros.proprio = True
            traceback.print_exc()
            erros.proprio = False
            resultado.falhas.append(estado['nome'] or '<harness>')
            sair(1)

    bpy.app.timers.register(passo, first_interval=0.5, persistent=True)


def esperar(segundos):
    return datetime.timedelta(seconds=segundos)
