"""Timer de seguranca, contorno nativo da selecao e handlers do
desfazer (Ctrl+Z)."""

import bpy

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
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

# =========================== REDE DE SEGURANCA: verificacao por timer
# O handler de depsgraph depende de uma atualizacao chegar DEPOIS que o
# operador modal sai de cena. Se a ultima atualizacao acontecer ainda
# com o modal registrado e nenhuma outra vier em seguida, o recalculo
# nunca dispararia. Este timer fecha essa brecha: a cada 0.2s verifica
# se existe alguma chapa com escala != 1 e nenhum modal ativo.
INTERVALO_TIMER = 0.2


def modal_interativo(operador):
    # O observador da parede so' repassa eventos; nao segura G/Tab nem
    # pode impedir a sincronizacao depois de o gesto nativo terminar.
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
    # O timer pode vencer antes do callback que encerra o undo. A mesma
    # guarda do depsgraph deve valer ANTES de consultar selecao/malhas.
    if _desfazendo[0]:
        return INTERVALO_TIMER
    _areas_criacao.verificar()
    _visibilidade.verificar()
    try:
        _paredes_edicao.verificar()
    except Exception as erro:
        _paredes_edicao.encerrar()
        print('[Cabinet Creator] edicao de parede:', erro)
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
            # modulo associado: segue a parede / volta ao plano dela
            _paredes.manter_nas_paredes()
            _alvenaria.verificar()
            _instalacoes.verificar()
            # controlador/furo do rig: so' o slider abre a porta
            _ferragens.ocultar_pecas_do_rig()
            _paredes.atualizar_guias()
        except Exception as e:
            print("[Cabinet Creator] erro no timer:", e)
    return INTERVALO_TIMER


# ------------------------------------------- contorno nativo da selecao
# Um clique seleciona o modulo inteiro, e o Blender pinta de laranja o
# contorno de cada chapa. Nao existe contorno por objeto na API: o
# `show_outline_selected` vale para a viewport inteira. Entao ele e'
# desligado na selecao exclusiva do add-on e DEVOLVIDO na selecao mista.
#
# Nunca se liga ou desliga as cegas: so' se desliga o que estava ligado,
# e so' se religa o que foi este add-on quem desligou. Quem ja' trabalha
# com o contorno desligado nao ve diferenca nenhuma, e quem o religa na
# mao durante a edicao manda naquela viewport ate' trocar de selecao.
_contornos_desligados = set()   # as_pointer() das viewports desligadas
_contornos_do_usuario = {}      # as_pointer() -> grupos da edicao
_origens_ocultas = set()        # (ponteiro do espaco, propriedade nativa)
_origens_do_usuario = {}


def _novo_contorno(ptr, ligado, grupos):
    """Mesmo contrato legado, com controle de propriedade compartilhado."""
    return _novo_overlay(ptr, ligado, grupos, _contornos_desligados,
                         _contornos_do_usuario)


def _novo_overlay(ptr, ligado, grupos, desligados, usuario):
    """So' devolve o que desligamos; respeita intervencao manual por selecao."""
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
            # religado na mao no meio da edicao: o usuario quer ver
            desligados.discard(ptr)
            usuario[ptr] = grupos
        return None
    if ligado:
        desligados.add(ptr)
        return False
    # ja' estava desligado antes: nao e' nosso, nao se devolve nada
    usuario[ptr] = grupos
    return None


def _grupos_selecionados(view_layer, marcas=None):
    # Nao percorre `view_layer.objects.selected`: logo apos um Ctrl+Z essa
    # colecao ainda pode trazer bases da memoria velha, e o Blender caia
    # criando o objeto Python (crash do usuario, 2x). `select_get` acha a
    # base de cada objeto nosso na hora.
    try:
        if marcas is None:
            marcas = (_chapas.MARCA_CONJUNTO, _chapas.MARCA_PORTAS, _chapas.MARCA_FOLHA)
        return frozenset(o.name for o in bpy.data.objects
                         if any(marca in o for marca in marcas)
                         and o.select_get(view_layer=view_layer))
    except Exception:
        return frozenset()


def _viewports_da_janela(janela):
    """Viewports da janela, menos a gaveta (que nao tem overlay)."""
    screen = janela.screen
    for area in screen.areas:
        if area.type == 'VIEW_3D' and not _gaveta._eh_area_gaveta_bruto(area):
            yield area.spaces.active


def _selecao_exige_contorno_nativo(view_layer, grupos):
    """O contorno da HUD nao representa um objeto comum somado com Shift."""
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
    """Duas flags nativas: origens selecionadas e todas as origens."""
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
    """Sincroniza contorno e origens nativos, com preferencias independentes.

    `devolver=True` religa tudo que o add-on desligou, sem esquecer
    quem o usuario religou: e' o caminho de salvar, abrir e desligar.
    """
    if devolver:
        # Todas as telas, nao so' a ativa: a viewport de outro workspace
        # tambem vai para o .blend.
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
            print("[Cabinet Creator] contorno:", e)
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
    _origens_ocultas.clear()
    _origens_do_usuario.clear()
    sincronizar_contornos()


@bpy.app.handlers.persistent
def _esquecer_referencias(*_args):
    """Antes de desfazer/refazer/abrir: o hover da HUD guarda OBJETOS, que
    essas acoes liberam (ver `_hud._alvo_vivo`). O proximo movimento do mouse
    acha o alvo de novo."""
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


# Ctrl+Z / Ctrl+Shift+Z: os dados acabaram de ser recarregados e o
# primeiro recalculo da cena chama o handler do depsgraph -- ler a selecao
# ali derrubava o Blender (crash do usuario, 2x, depois de criar porta).
# Entre o undo e o proximo tique o handler nao faz nada; o timer devolve
# o contorno. Fora do undo nada muda: o contorno segue na hora.
_desfazendo = [False]


@bpy.app.handlers.persistent
def _antes_de_desfazer(*_args):
    _paredes_edicao.encerrar()
    # Undo dentro do Edit Mode conserva o escopo atual (so' nomes/digitais).
    edicao = _prateleiras._edicao[0] if bpy.context.mode == 'EDIT_MESH' else None
    grupo = _selecao._edicao_grupo[0] if bpy.context.mode == 'EDIT_MESH' else None
    # Refazer Tab ainda precisa medir a malha confirmada. Guardar nomes
    # conserva essa transicao sem reter IDs que o undo vai liberar.
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
    # O depsgraph ainda pode estar copiando os IDs restaurados. As
    # referencias pendentes voltam pelo timer normal, fora deste fecho.
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
