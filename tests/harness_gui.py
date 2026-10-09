"""Harness de testes de INTERFACE (cliques e teclas de verdade).

Segue o padrao oficial do Blender (tests/python/ui_simulate, easy_keys):
o Blender abre COM janela e `--enable-event-simulate`, que ignora o
mouse/teclado reais; cada teste e' um GERADOR rodado por um timer, e cada
`yield` deixa o loop principal processar os eventos e redesenhar. Um
`yield datetime.timedelta(...)` espera aquele tempo de relogio.

Limites conhecidos (fonte do Blender, ver CLAUDE.md):
- o simulador NAO gera DOUBLE_CLICK (`check_double_click = false`): dois
  cliques chegam como PRESS, RELEASE, PRESS, RELEASE. Modal nunca recebe
  DOUBLE_CLICK nem do mouse real, entao isso cobre os modais; o
  DOUBLE_CLICK de keymap (selecao em 3 camadas) so' com entrada real.
- excecao num timer so' e' impressa: aqui tudo e' capturado e o processo
  sai com `sys.exit(codigo)`; o executor ainda tem tempo-limite.

Rodado pelo executor:  blender ... --python tests/rodar_testes.py -- --gui
"""
import datetime
import os
import sys
import time
import traceback

import bpy
from bpy_extras import view3d_utils

TICKS = 4               # o upstream usa 4 ("3 funciona, 4 por seguranca")
LIMITE_SEGUNDOS = 120


class Mouse:
    """Mouse e teclado simulados, em coordenadas da JANELA."""

    def __init__(self, janela):
        self.janela = janela
        self.x, self.y = janela.width // 2, janela.height // 2

    def mover(self, x, y):
        self.x, self.y = int(round(x)), int(round(y))
        self.janela.event_simulate('MOUSEMOVE', 'NOTHING', x=self.x, y=self.y)

    def apertar(self, botao='LEFTMOUSE', **mods):
        """mods: alt/ctrl/shift=True -- o simulador so' poe no evento os
        modificadores passados (o estado real do teclado e' ignorado)."""
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
        # '+' e '*' so' existem no teclado numerico como tipo de evento
        nomes = {'.': 'PERIOD', ',': 'COMMA', '-': 'MINUS',
                 '+': 'NUMPAD_PLUS', '*': 'NUMPAD_ASTERIX', '/': 'SLASH',
                 ' ': 'SPACE'}
        nomes.update({str(i): n for i, n in enumerate(
            ('ZERO', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN',
             'EIGHT', 'NINE'))})
        for c in texto:
            self.tecla(nomes.get(c, c.upper()), c)


def viewport_principal(janela, gaveta=None):
    """(area, regiao, region_3d) da maior VIEW_3D que nao e' a gaveta."""
    areas = [a for a in janela.screen.areas
             if a.type == 'VIEW_3D' and a != gaveta]
    area = max(areas, key=lambda a: a.width * a.height)
    regiao = next(r for r in area.regions if r.type == 'WINDOW')
    return area, regiao, area.spaces.active.region_3d


def na_tela(regiao, rv3d, ponto):
    """Ponto 3D -> coordenada da JANELA (para event_simulate)."""
    p = view3d_utils.location_3d_to_region_2d(regiao, rv3d, ponto)
    return None if p is None else (regiao.x + p.x, regiao.y + p.y)


class Pular(Exception):
    """Levante dentro do teste para pula-lo com um motivo."""


class ErrosDeCallback:
    """sys.stderr que conta os tracebacks de CALLBACK (desenho da gaveta,
    gizmo, timer): o Blender so' os IMPRIME e o teste passava com a gaveta
    quebrada (v140: abas, icones e fundo sumiram e os 26 testes passaram).
    Os tracebacks do proprio harness (falha de teste) nao contam."""
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
    """Roda os geradores `testes` em sequencia; saida no formato do
    unittest (Ran N tests / OK / FAIL:) para o executor contar."""
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
        os._exit(codigo)   # sys.exit num timer deixa a janela viva as vezes

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
                # quebrou um callback durante o teste: e' falha, mesmo
                # com todos os asserts passando
                print('FAIL: %s' % estado['nome'])
                print('%d erro(s) em callback (desenho/gizmo/timer):'
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
                print('FAIL: TEMPO ESGOTADO em %s' % estado['nome'])
                resultado.falhas.append(estado['nome'] + ' (tempo)')
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
