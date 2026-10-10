"""Timer de seguranca, contorno nativo da selecao e handlers do
desfazer (Ctrl+Z)."""

import bpy

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _modulos = _opcoes = _puxadores = _gaveta = _hud = None

# =========================== REDE DE SEGURANCA: verificacao por timer
# O handler de depsgraph depende de uma atualizacao chegar DEPOIS que o
# operador modal sai de cena. Se a ultima atualizacao acontecer ainda
# com o modal registrado e nenhuma outra vier em seguida, o recalculo
# nunca dispararia. Este timer fecha essa brecha: a cada 0.2s verifica
# se existe alguma chapa com escala != 1 e nenhum modal ativo.
INTERVALO_TIMER = 0.2


def _ha_modal_ativo():
    try:
        for win in bpy.context.window_manager.windows:
            if len(win.modal_operators) > 0:
                return True
    except Exception:
        pass
    return False


def _transformando():
    """Mover, girar ou escalar (G/R/S, gizmo nativo) em andamento.

    A HUD le a geometria e o alvo do hover de ANTES do gesto: desenhada
    durante ele, a seta e as linhas ficavam voando no lugar de origem.
    """
    try:
        for janela in bpy.context.window_manager.windows:
            for op in janela.modal_operators:
                if op.bl_idname.upper().startswith('TRANSFORM'):
                    return True
    except Exception:
        pass
    return False


def verificar_periodicamente():
    sincronizar_contornos()
    if not _chapas._ocupado[0] and not _ha_modal_ativo():
        try:
            _modulos.absorver_conjuntos()
            _chapas.normalizar_chapas()
            _chapas.absorver_edicoes_de_malha()
            _puxadores._conferir_rebaixos()
            _modulos._sincronizar_medidas_ativas()
        except Exception as e:
            print("[Cabinet Creator] erro no timer:", e)
    return INTERVALO_TIMER


# ------------------------------------------- contorno nativo da selecao
# Um clique seleciona o modulo inteiro, e o Blender pinta de laranja o
# contorno de cada chapa. Nao existe contorno por objeto na API: o
# `show_outline_selected` vale para a viewport inteira. Entao ele e'
# desligado enquanto houver modulo/porta selecionado e DEVOLVIDO depois.
#
# Nunca se liga ou desliga as cegas: so' se desliga o que estava ligado,
# e so' se religa o que foi este add-on quem desligou. Quem ja' trabalha
# com o contorno desligado nao ve diferenca nenhuma, e quem o religa na
# mao durante a edicao manda naquela viewport ate' trocar de selecao.
_contornos_desligados = set()   # as_pointer() das viewports desligadas
_contornos_do_usuario = {}      # as_pointer() -> grupos da edicao


def _novo_contorno(ptr, ligado, grupos):
    """Valor novo do contorno de UMA viewport (None = nao mexer).

    `grupos`: nomes dos modulos/portas selecionados (vazio = nenhum).
    """
    if not grupos:
        _contornos_do_usuario.pop(ptr, None)
        if ptr in _contornos_desligados:
            _contornos_desligados.discard(ptr)
            if not ligado:
                return True
        return None
    if _contornos_do_usuario.get(ptr) == grupos:
        return None
    _contornos_do_usuario.pop(ptr, None)
    if ptr in _contornos_desligados:
        if ligado:
            # religado na mao no meio da edicao: o usuario quer ver
            _contornos_desligados.discard(ptr)
            _contornos_do_usuario[ptr] = grupos
        return None
    if ligado:
        _contornos_desligados.add(ptr)
        return False
    # ja' estava desligado antes: nao e' nosso, nao se devolve nada
    _contornos_do_usuario[ptr] = grupos
    return None


def _grupos_selecionados(view_layer):
    # Nao percorre `view_layer.objects.selected`: logo apos um Ctrl+Z essa
    # colecao ainda pode trazer bases da memoria velha, e o Blender caia
    # criando o objeto Python (crash do usuario, 2x). `select_get` acha a
    # base de cada objeto nosso na hora.
    try:
        return frozenset(o.name for o in bpy.data.objects
                         if (_chapas.MARCA_CONJUNTO in o or _chapas.MARCA_PORTAS in o
                             or _chapas.MARCA_FOLHA in o)
                         and o.select_get(view_layer=view_layer))
    except Exception:
        return frozenset()


def _viewports_da_janela(janela):
    """Viewports da janela, menos a gaveta (que nao tem overlay)."""
    screen = janela.screen
    gaveta = _gaveta._area_gaveta(screen)
    for area in screen.areas:
        if area.type == 'VIEW_3D' and area != gaveta:
            yield area.spaces.active


def sincronizar_contornos(devolver=False):
    """Aplica `_novo_contorno` a cada viewport aberta.

    `devolver=True` religa tudo que o add-on desligou, sem esquecer
    quem o usuario religou: e' o caminho de salvar, abrir e desligar.
    """
    try:
        janelas = bpy.context.window_manager.windows
    except Exception:
        return
    for janela in janelas:
        try:
            grupos = frozenset()
            if not devolver and _opcoes._opcao('ocultar_contorno_grupo'):
                grupos = _grupos_selecionados(janela.view_layer)
            for espaco in _viewports_da_janela(janela):
                overlay = espaco.overlay
                ptr = espaco.as_pointer()
                if devolver:
                    if ptr in _contornos_desligados:
                        _contornos_desligados.discard(ptr)
                        overlay.show_outline_selected = True
                    continue
                novo = _novo_contorno(ptr, overlay.show_outline_selected,
                                      grupos)
                if novo is not None:
                    overlay.show_outline_selected = novo
        except Exception as e:
            print("[Cabinet Creator] contorno:", e)


@bpy.app.handlers.persistent
def _devolver_contornos(*_args):
    """Antes de salvar ou abrir: o .blend guarda o estado do usuario,
    nunca o desligamento temporario."""
    sincronizar_contornos(devolver=True)


@bpy.app.handlers.persistent
def _retomar_contornos(*_args):
    sincronizar_contornos()


@bpy.app.handlers.persistent
def _esquecer_contornos(*_args):
    # arquivo novo: os ponteiros antigos podem ser reaproveitados
    _contornos_desligados.clear()
    _contornos_do_usuario.clear()
    sincronizar_contornos()


@bpy.app.handlers.persistent
def _esquecer_referencias(*_args):
    """Antes de desfazer/refazer/abrir: o hover da HUD guarda OBJETOS, que
    essas acoes liberam (ver `_hud._alvo_vivo`). O proximo movimento do mouse
    acha o alvo de novo."""
    _hud._hover_hud.clear()


# Ctrl+Z / Ctrl+Shift+Z: os dados acabaram de ser recarregados e o
# primeiro recalculo da cena chama o handler do depsgraph -- ler a selecao
# ali derrubava o Blender (crash do usuario, 2x, depois de criar porta).
# Entre o undo e o proximo tique o handler nao faz nada; o timer devolve
# o contorno. Fora do undo nada muda: o contorno segue na hora.
_desfazendo = [False]


@bpy.app.handlers.persistent
def _antes_de_desfazer(*_args):
    _desfazendo[0] = True
    _esquecer_referencias()


@bpy.app.handlers.persistent
def _depois_de_desfazer(*_args):
    _desfazendo[0] = True
    if not bpy.app.timers.is_registered(_fim_do_desfazer):
        bpy.app.timers.register(_fim_do_desfazer, first_interval=0.0)


def _fim_do_desfazer():
    _desfazendo[0] = False
    sincronizar_contornos()
    return None


HANDLERS_REFERENCIAS = (('undo_pre', _antes_de_desfazer),
                        ('redo_pre', _antes_de_desfazer),
                        ('undo_post', _depois_de_desfazer),
                        ('redo_post', _depois_de_desfazer),
                        ('load_pre', _esquecer_referencias))

HANDLERS_CONTORNO = (('save_pre', _devolver_contornos),
                     ('save_post', _retomar_contornos),
                     ('load_pre', _devolver_contornos),
                     ('load_post', _esquecer_contornos))


def _redesenhar_viewports(context):
    for area in context.screen.areas if context.screen else ():
        if area.type == 'VIEW_3D':
            area.tag_redraw()
