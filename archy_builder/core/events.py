"""Safety timer, native selection outlines and undo (Ctrl+Z) handlers."""

import bpy

# Used only at runtime (circular imports): __init__ binds these
# aliases after loading all modules (`_ligar_modulos`).
_chapas = _modulos = _opcoes = _puxadores = _gaveta = _hud = _paredes = None
_ferragens = _prateleiras = _selecao = _formas = _divisorias = None
_frentes = _solda = _fundos = None
_hud_volume = None
_gavetas = None
_paredes_edicao = _paredes_selecao = None
_alvenaria = None
_instalacoes = None
_editor = None
_areas_criacao = None
_visibilidade = None

# =========================== SAFETY NET: timer checks
# The depsgraph handler depends on an update arriving AFTER the modal
# operator finishes. If its last update occurs while the modal is still
# registered, with no subsequent update, recalculation never runs.
# This timer closes that gap: every 0.2 s, check for panel scale != 1
# with no active modal.
INTERVALO_TIMER = 0.2


def modal_interativo(operador):
    # The wall observer only forwards events: it must not capture G/Tab
    # or prevent synchronization after the native gesture finishes.
    return getattr(operador, 'bl_idname', '') != 'OBJECT_OT_cabinet_observar_parede'


def _ha_modal_ativo():
    try:
        for win in bpy.context.window_manager.windows:
            if any(modal_interativo(op) for op in win.modal_operators):
                return True
    except Exception:
        pass
    return False


def _transformando():
    """Native move/rotate/scale (G/R/S or gizmo) in progress.

    HUD geometry/hover targets come from BEFORE the gesture; drawing them
    during it left arrows and lines floating at the old location.
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
    # The timer may fire before the undo-completion callback. Apply the
    # same depsgraph guard BEFORE querying selection/meshes.
    if _desfazendo[0]:
        return INTERVALO_TIMER
    _areas_criacao.verificar()
    _visibilidade.verificar()
    try:
        _paredes_edicao.verificar()
    except Exception as erro:
        _paredes_edicao.encerrar()
        print("[Archy Builder] wall editing:", erro)
    sincronizar_contornos()
    if not _chapas._ocupado[0] and not _ha_modal_ativo():
        try:
            _prateleiras.concluir_edicao()
            _selecao.concluir_edicao_grupo(bpy.context)
            _modulos.absorver_conjuntos(no_timer=True)
            _divisorias.atualizar_dependentes()
            _chapas.normalizar_chapas()
            _chapas.absorver_edicoes_de_malha()
            _solda.normalizar_pendentes()
            _prateleiras.sincronizar_exclusoes_da_cena()
            _fundos.verificar()
            _frentes.processar_pendentes()
            _puxadores._conferir_rebaixos()
            _modulos._sincronizar_medidas_ativas()
            # Linked cabinet: follow the wall/return to its plane.
            _paredes.manter_nas_paredes()
            _alvenaria.verificar()
            _instalacoes.verificar()
            # Rig controller/cutter: only the slider opens the door.
            _ferragens.ocultar_pecas_do_rig()
            _paredes.atualizar_guias()
        except Exception as e:
            print("[Archy Builder] timer error:", e)
    return INTERVALO_TIMER


# ------------------------------------------- native selection outline
# One click selects the whole cabinet; Blender outlines every panel
# orange. The API has no per-object outline: show_outline_selected
# affects the whole viewport. Disable it for add-on-only selections
# and RESTORE it for mixed selections.
#
# Never toggle blindly: disable only an enabled setting and restore only
# what THIS add-on disabled. Users already working without outlines
# see no change. Manually reenabling during editing governs that viewport
# until the selection changes.
_contornos_desligados = set()   # as_pointer() of viewports whose outlines were disabled.
_contornos_do_usuario = {}      # as_pointer() -> editing groups.
_origens_ocultas = set()        # (space pointer, native property).
_origens_do_usuario = {}


def _novo_contorno(ptr, ligado, grupos):
    """Same legacy contract with shared property ownership tracking."""
    return _novo_overlay(ptr, ligado, grupos, _contornos_desligados,
                         _contornos_do_usuario)


def _novo_overlay(ptr, ligado, grupos, desligados, usuario):
    """Restore only what we disabled; respect manual changes per selection."""
    if not grupos:
        usuario.pop(ptr, None)
        if ptr in desligados:
            desligados.discard(ptr)
            if not ligado:
                return True
        return None
    if usuario.get(ptr) == grupos:
        return None
    usuario.pop(ptr, None)
    if ptr in desligados:
        if ligado:
            # Manually reenabled during editing: the user wants it visible.
            desligados.discard(ptr)
            usuario[ptr] = grupos
        return None
    if ligado:
        desligados.add(ptr)
        return False
    # Already disabled beforehand: not ours to restore.
    usuario[ptr] = grupos
    return None


def _grupos_selecionados(view_layer, marcas=None):
    # Do not traverse `view_layer.objects.selected`: immediately after Ctrl+Z,
    # it may retain old-memory bases, crashing Blender when creating Python
    # objects (two user crashes). `select_get` resolves each add-on object's
    # current base on demand.
    try:
        if marcas is None:
            marcas = (_chapas.MARCA_CONJUNTO, _chapas.MARCA_PORTAS, _chapas.MARCA_FOLHA)
        return frozenset(o.name for o in bpy.data.objects
                         if any(marca in o for marca in marcas)
                         and o.select_get(view_layer=view_layer))
    except Exception:
        return frozenset()


def _viewports_da_janela(janela):
    """Window viewports excluding the sidebar, which has no overlay."""
    screen = janela.screen
    for area in screen.areas:
        if area.type == 'VIEW_3D' and not _gaveta._eh_area_gaveta_bruto(area):
            yield area.spaces.active


def _selecao_exige_contorno_nativo(view_layer, grupos):
    """HUD outlines do not represent an ordinary object added with Shift."""
    for obj in view_layer.objects:
        if not obj.select_get(view_layer=view_layer):
            continue
        dono = obj
        while dono is not None and dono.name not in grupos:
            dono = dono.parent
        if (dono is None and _selecao._aba_da_selecao(obj) is None
                and _ferragens.CHAVE_FERRAGEM not in obj):
            return True
    return False


def _sincronizar_origens(espaco, grupos, devolver=False):
    """Two native flags: selected origins and all origins."""
    for nome in ('show_object_origins', 'show_object_origins_all'):
        chave = (espaco.as_pointer(), nome)
        if devolver:
            if chave in _origens_ocultas:
                _origens_ocultas.discard(chave)
                setattr(espaco.overlay, nome, True)
            continue
        novo = _novo_overlay(chave, getattr(espaco.overlay, nome), grupos,
                             _origens_ocultas, _origens_do_usuario)
        if novo is not None:
            setattr(espaco.overlay, nome, novo)


def sincronizar_contornos(devolver=False):
    """Synchronize native outlines/origins with independent preferences.

    `devolver=True` restores everything disabled by the add-on while
    respecting user reenabling; used for save, load and disable.
    """
    if devolver:
        # All screens, not just active: another workspace's viewport state
        # is also saved to .blend.
        try:
            for tela in bpy.data.screens:
                for area in tela.areas:
                    if area.type != 'VIEW_3D':
                        continue
                    espaco = area.spaces.active
                    _sincronizar_origens(espaco, frozenset(), True)
                    if espaco.as_pointer() in _contornos_desligados:
                        _contornos_desligados.discard(espaco.as_pointer())
                        espaco.overlay.show_outline_selected = True
        except Exception as e:
            print("[Archy Builder] outline:", e)
        return
    try:
        janelas = bpy.context.window_manager.windows
    except Exception:
        return
    for janela in janelas:
        try:
            grupos = frozenset()
            grupos_origens = frozenset()
            if _opcoes._opcao('ocultar_contorno_grupo'):
                grupos = _grupos_selecionados(janela.view_layer)
                if grupos and _selecao_exige_contorno_nativo(janela.view_layer, grupos):
                    grupos = frozenset()
            if _opcoes._opcao('ocultar_origens_grupo'):
                grupos_origens = _grupos_selecionados(janela.view_layer,
                    (_chapas.MARCA_CONJUNTO, _chapas.MARCA_PORTAS,
                     _gavetas.MARCA_GRUPO, _prateleiras.MARCA_GRUPO, _divisorias.MARCA_GRUPO))
            for espaco in _viewports_da_janela(janela):
                _sincronizar_origens(espaco, grupos_origens)
                overlay = espaco.overlay
                ptr = espaco.as_pointer()
                novo = _novo_contorno(ptr, overlay.show_outline_selected,
                                      grupos)
                if novo is not None:
                    overlay.show_outline_selected = novo
        except Exception as e:
            print("[Archy Builder] outline:", e)


@bpy.app.handlers.persistent
def _devolver_contornos(*_args):
    """Before saving/loading, restore user state so .blend never stores
    temporary disabled settings."""
    sincronizar_contornos(devolver=True)


@bpy.app.handlers.persistent
def _retomar_contornos(*_args):
    sincronizar_contornos()


@bpy.app.handlers.persistent
def _esquecer_contornos(*_args):
    # New file: old pointer values can be reused.
    _contornos_desligados.clear()
    _contornos_do_usuario.clear()
    _origens_ocultas.clear()
    _origens_do_usuario.clear()
    sincronizar_contornos()


@bpy.app.handlers.persistent
def _esquecer_referencias(*_args):
    """Before undo/redo/load, clear HUD hover OBJECTS that these actions free
    (see `_hud._alvo_vivo`). The next mouse movement resolves the target again."""
    _visibilidade.esquecer_edicao()
    _paredes_edicao.encerrar()
    _paredes_selecao.esquecer()
    _paredes_edicao._ultima_face[0] = None
    _paredes_edicao._alvo_contexto[0] = None
    _hud._hover_hud.clear()
    _hud_volume.terminar()
    _areas_criacao.esquecer()
    _paredes.esquecer()
    _alvenaria.esquecer()
    _instalacoes.esquecer()
    _prateleiras.esquecer()
    _fundos.esquecer()
    _selecao._edicao_grupo[0] = None
    _formas.esquecer()
    _frentes.esquecer()
    _solda._cache_ancoras[0].clear()
    _solda._normalizar_pendente[0] = True
    _chapas._chapas_em_edicao.clear()
    _chapas._havia_modal[0] = False
    _ferragens._contagem_objetos[0] = None


# Ctrl+Z / Ctrl+Shift+Z reload data; initial scene recalculation calls
# the depsgraph handler. Reading selection there crashed Blender
# twice for the user after creating a door.
# Between undo and the next tick the handler does nothing; the timer
# restores outlines. Outside undo, outlines still follow immediately.
_desfazendo = [False]


@bpy.app.handlers.persistent
def _antes_de_desfazer(*_args):
    _paredes_edicao.encerrar()
    # Undo inside Edit Mode retains current scope as names/signatures only.
    edicao = _prateleiras._edicao[0] if bpy.context.mode == 'EDIT_MESH' else None
    grupo = _selecao._edicao_grupo[0] if bpy.context.mode == 'EDIT_MESH' else None
    # Redoing Tab still needs to measure confirmed geometry. Keeping names
    # preserves that transition without retaining IDs freed by undo.
    chapas = set(_chapas._chapas_em_edicao) if bpy.context.mode == 'EDIT_MESH' else set()
    _desfazendo[0] = True
    _esquecer_referencias()
    _prateleiras._edicao[0] = edicao
    _selecao._edicao_grupo[0] = grupo
    _chapas._chapas_em_edicao.update(chapas)


@bpy.app.handlers.persistent
def _depois_de_desfazer(*_args):
    _desfazendo[0] = True
    if not bpy.app.timers.is_registered(_fim_do_desfazer):
        bpy.app.timers.register(_fim_do_desfazer, first_interval=0.0)


def _fim_do_desfazer():
    _desfazendo[0] = False
    # Depsgraph may still be copying restored IDs. Rebuild pending
    # references in the normal timer, outside this completion callback.
    sincronizar_contornos()
    return None


@bpy.app.handlers.persistent
def _encerrar_area_criacao(*_args):
    _areas_criacao.esquecer()


HANDLERS_REFERENCIAS = (('undo_pre', _antes_de_desfazer),
                        ('redo_pre', _antes_de_desfazer),
                        ('undo_post', _depois_de_desfazer),
                        ('redo_post', _depois_de_desfazer),
                        ('load_pre', _esquecer_referencias),
                        ('save_pre', _encerrar_area_criacao))

@bpy.app.handlers.persistent
def _encerrar_vista_parede(*_args):
    _paredes_edicao.encerrar()


HANDLERS_CONTORNO = (('save_pre', _devolver_contornos),
                     ('save_pre', _encerrar_vista_parede),
                     ('save_post', _retomar_contornos),
                     ('load_pre', _devolver_contornos),
                     ('load_post', _esquecer_contornos))


def _redesenhar_viewports(context):
    for area in context.screen.areas if context.screen else ():
        if area.type == 'VIEW_3D' or _editor.eh_editor(area):
            area.tag_redraw()
