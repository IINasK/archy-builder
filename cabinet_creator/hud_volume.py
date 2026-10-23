"""Gesto de resize da caixa: ponto temporario e transformador do Blender.

A HUD escolhe a cota; o dono da cota continua decidindo a geometria.
Nenhum vertice e' procurado aqui: B, Ctrl e teclado pertencem ao translate.
"""
import bpy
from mathutils import Matrix, Vector
from bpy.types import Operator, Macro

_hud = None
_eventos = None
_opcoes = None
_estado = [None]
_timer_observador = [None]
_assinatura_mapa_snap = [None]
NOME_MAPA_SNAP = 'Cabinet Observador da Base do Snap'
_CAMPOS_EVENTO = ('type', 'value', 'any', 'shift', 'ctrl', 'alt', 'oskey',
                  'key_modifier', 'direction', 'repeat', 'hyper')


def controles(geometria):
    """Seis centros de face, so' no envelope convencional (8 cantos)."""
    if (not _opcoes._opcao('hud_pontos_apoio') or len(geometria['cantos']) != 8 or (geometria['modo'] != 'GRUPO'
            and _hud._sistema_hud(geometria['modo']) is None)):
        return []
    controles = []
    for eixo in range(3):
        linha = next((l for l in geometria['linhas']
                      if l.get('eixo') == eixo and l.get('cantos')
                      and l.get('editavel', True)
                      and elegivel(dict(l, lado='min'))), None)
        if linha is None:
            continue
        centros = [sum((p for i, p in enumerate(geometria['cantos'])
                        if bool(i & (1 << eixo)) == bool(lado)), Vector()) / 4
                   for lado in (0, 1)]
        for lado in (0, 1):
            controles.append(dict(linha, controle_face=True,
                lado='min' if lado else 'max', pontos=[centros[1-lado], centros[lado]]))
    return controles


def elegivel(alvo):
    return (alvo.get('lado') in {'min', 'max'}
            and not alvo.get('seta_real')
            and (alvo['tipo'] == 'medida' or (
                _hud._sistema_hud(alvo['tipo']) is not None
                and len(alvo.get('face', ())) == 1
                and alvo['face'][0] in {'L', 'A', 'P'})))


def _guardar(valor):
    # Nomes sobrevivem ao undo; RNA de objetos em globais nao sobrevive.
    if isinstance(valor, bpy.types.Object):
        return {'__objeto_hud__': valor.name}
    if isinstance(valor, dict):
        return {k: _guardar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return type(valor)(_guardar(v) for v in valor)
    return valor.copy() if isinstance(valor, (Vector, Matrix)) else valor


def _recuperar(valor):
    if isinstance(valor, dict):
        if '__objeto_hud__' in valor:
            obj = bpy.data.objects.get(valor['__objeto_hud__'])
            if obj is None:
                raise ValueError('O alvo da medida nao existe mais')
            return obj
        return {k: _recuperar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return type(valor)(_recuperar(v) for v in valor)
    return valor


def preparar(context, alvo, backup):
    ponto = alvo['pontos'][1].copy()
    eixo = (ponto - alvo['pontos'][0]).normalized()
    # A linha aponta da face parada para a movel, inclusive no lado minimo.
    auxiliar = Vector((0, 0, 1)) if abs(eixo.z) < .9 else Vector((0, 1, 0))
    y = auxiliar.cross(eixo).normalized()
    base = Matrix((eixo, y, eixo.cross(y)))
    obj = alvo['objeto']
    proprias = [o for o in [obj, *obj.children_recursive]
                if o.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}]
    bloqueados = [(o.name, o.hide_select) for o in proprias]
    alvo_numerico = dict(alvo)
    if _hud._sistema_hud(alvo['tipo']) is not None:
        # Montar gavetas pode refazer filhos; o alvo e' o grupo, nao essas pecas.
        alvo_numerico.pop('chapas', None)
    _estado[0] = dict(alvo=_guardar(alvo_numerico), backup=_guardar(backup),
        objeto=obj.name, modo=alvo.get('modo'),
        cena=context.scene.name, area=context.area.as_pointer(),
        regiao=context.region.as_pointer(), cursor=tuple(context.scene.cursor.location),
        mostrar_cursor=context.space_data.overlay.show_cursor, bloqueados=bloqueados,
        selecao=[o.name for o in context.view_layer.objects if o.select_get()],
        ativo=context.view_layer.objects.active.name if context.view_layer.objects.active else None,
        inicio=tuple(ponto), eixo=tuple(eixo), valor=_hud._valor_hud(alvo, context),
        deslocamento_base_mm=0.0, ultimo=None)
    for o in proprias:
        o.hide_select = True
    context.scene.cursor.location = ponto
    context.space_data.overlay.show_cursor = False
    # Comeca livre, mesmo quando o ima global esta' ligado. B ativa a
    # escolha/ancoragem nativa explicitamente durante o translate.
    return dict(cursor_transform=True, snap=False, snap_elements={'VERTEX'},
        snap_target='CENTER', snap_align=False, use_snap_selectable=True,
        release_confirm=True, orient_type='GLOBAL', orient_matrix_type='GLOBAL',
        orient_matrix=tuple(tuple(l) for l in base), constraint_axis=(True, False, False))


def atualizar(context):
    estado = _estado[0]
    if not estado or _eventos._desfazendo[0]:
        return
    ponto = tuple(context.scene.cursor.location)
    if ponto == estado['ultimo']:
        return
    alvo = _recuperar(estado['alvo'])
    valor = estado['valor'] + estado['deslocamento_base_mm'] + (Vector(ponto) - Vector(estado['inicio'])).dot(
        Vector(estado['eixo'])) * 1000.0
    # Cada previa parte da mesma referencia, nunca da ultima malha esticada.
    _hud._restaurar_arraste_hud(context, _recuperar(estado['backup']))
    try:
        _hud._aplicar_valor_hud(context, alvo, max(.001, valor))
        estado.pop('erro', None)
    except ValueError as erro:
        # Uma restricao fisica nao encerra o translate ainda vivo. O mouse
        # pode voltar a uma medida valida, ou Esc pode cancelar normalmente.
        estado['erro'] = str(erro)
        _hud._restaurar_arraste_hud(context, _recuperar(estado['backup']))
    # Gavetas refazem as pecas. O filtro de snap tambem vale para os novos IDs.
    bloqueados = dict(estado['bloqueados'])
    for obj in [alvo['objeto'], *alvo['objeto'].children_recursive]:
        if obj.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}:
            bloqueados.setdefault(obj.name, obj.hide_select)
            obj.hide_select = True
    estado['bloqueados'] = list(bloqueados.items())
    estado['ultimo'] = ponto
    alvo['pontos'] = [alvo['pontos'][0], alvo['pontos'][0] + Vector(estado['eixo'])
                      * _hud._valor_hud(alvo, context) / 1000.0]
    _hud._edicao_hud[0] = dict(regiao=estado['regiao'], alvo=alvo, nativo=True)


def preparar_base_snap(context):
    """B passa a ancorar na geometria ATUAL, sem perder o arraste anterior."""
    estado = _estado[0]
    if not estado or _eventos._desfazendo[0]:
        return
    # Absorve inclusive o ultimo movimento que o timer ainda nao desenhou.
    # O Blender zera seu deslocamento ao escolher a base; o nosso passa a
    # partir da medida ATUAL. Backup e inicio originais ficam para Esc/undo.
    atualizar(context)
    alvo = _recuperar(estado['alvo'])
    estado['deslocamento_base_mm'] = _hud._valor_hud(alvo, context) - estado['valor']
    context.view_layer.update()
    estado['ultimo'] = None
    estado.pop('erro', None)
    _hud._edicao_hud[0] = None
    _hud._hover_hud.clear()


def _mapa_eventos_snap(context):
    configs = context.window_manager.keyconfigs
    origem = configs.user.keymaps.get('Transform Modal Map') if configs.user else None
    if origem is None or configs.addon is None:
        return None
    itens = [i for i in origem.keymap_items if i.active and i.propvalue in {
        'EDIT_SNAP_SOURCE_ON', 'EDIT_SNAP_SOURCE_OFF'}]
    assinatura = tuple(tuple(getattr(i, p, None) for p in _CAMPOS_EVENTO) for i in itens)
    mapa = configs.addon.keymaps.get(NOME_MAPA_SNAP)
    if mapa is None or _assinatura_mapa_snap[0] != assinatura:
        if mapa is None:
            mapa = configs.addon.keymaps.new(name=NOME_MAPA_SNAP)
        for item in list(mapa.keymap_items):
            mapa.keymap_items.remove(item)
        for item in itens:
            # match_event faz poll do OPERADOR: itens modais tem idname
            # vazio e nunca casam nessa API. O espelho normal conserva os
            # atalhos; o matcher continua NATIVO, sem refazer seus filtros.
            novo = mapa.keymap_items.new(OBJECT_OT_observar_volume.bl_idname, item.type, item.value)
            for prop in _CAMPOS_EVENTO:
                if hasattr(item, prop) and hasattr(novo, prop):
                    setattr(novo, prop, getattr(item, prop))
        _assinatura_mapa_snap[0] = assinatura
    return mapa


def _evento_base_snap(context, event):
    mapa = _mapa_eventos_snap(context)
    return mapa is not None and mapa.keymap_items.match_event(event) is not None


def _remover_observador():
    timer = _timer_observador[0]
    _timer_observador[0] = None
    if timer is not None:
        bpy.context.window_manager.event_timer_remove(timer)
    config = bpy.context.window_manager.keyconfigs.addon
    mapa = config.keymaps.get(NOME_MAPA_SNAP) if config else None
    if mapa is not None:
        config.keymaps.remove(mapa)
    _assinatura_mapa_snap[0] = None


def terminar(context=None, cancelar=False, remover_timer=True):
    estado = _estado[0]
    _estado[0] = None
    try:
        if estado:
            try:
                if cancelar and context is not None and not _eventos._desfazendo[0]:
                    _hud._restaurar_arraste_hud(context, _recuperar(estado['backup']))
            finally:
                _devolver_contexto(estado)
    finally:
        _hud._edicao_hud[0] = None
        _hud._hover_hud.clear()
        if remover_timer and bpy.app.timers.is_registered(_acompanhar):
            bpy.app.timers.unregister(_acompanhar)


def _devolver_contexto(estado):
    cena = bpy.data.scenes.get(estado['cena'])
    if cena is not None:
        cena.cursor.location = estado['cursor']
    for nome, bloqueado in estado['bloqueados']:
        obj = bpy.data.objects.get(nome)
        if obj is not None:
            obj.hide_select = bloqueado
    camada = bpy.context.view_layer
    if camada is not None and not _eventos._desfazendo[0]:
        selecionados = set(estado['selecao'])
        for obj in camada.objects:
            if obj.select_get() != (obj.name in selecionados):
                obj.select_set(obj.name in selecionados)
        camada.objects.active = camada.objects.get(estado['ativo']) if estado['ativo'] else None
    for janela in bpy.context.window_manager.windows:
        for area in janela.screen.areas:
            if area.as_pointer() == estado['area'] and area.type == 'VIEW_3D':
                area.spaces.active.overlay.show_cursor = estado['mostrar_cursor']
                area.tag_redraw()


def _acompanhar():
    estado = _estado[0]
    if not estado:
        return None
    if _eventos._desfazendo[0]:
        return .05
    for janela in bpy.context.window_manager.windows:
        if janela.scene.name != estado['cena']:
            continue
        for area in janela.screen.areas:
            if area.as_pointer() != estado['area']:
                continue
            regiao = next((r for r in area.regions if r.type == 'WINDOW'), None)
            with bpy.context.temp_override(window=janela, area=area, region=regiao):
                try:
                    if not any(o.bl_idname == 'OBJECT_OT_cabinet_transformar_volume'
                               for o in janela.modal_operators):
                        terminar(bpy.context, cancelar=True, remover_timer=False)
                        return None
                    atualizar(bpy.context)
                    area.tag_redraw()
                except Exception as erro:
                    # O transformador ainda possui o cursor. Conservar o
                    # estado ate' confirmar/Esc garante que ele seja devolvido.
                    print('[Cabinet Creator] resize:', erro)
                    estado['erro'] = str(erro)
                    estado['ultimo'] = tuple(bpy.context.scene.cursor.location)
                    _hud._edicao_hud[0] = None
                    _hud._hover_hud.clear()
                    return 1.0 / 30.0
            return 1.0 / 30.0
    cena = bpy.data.scenes.get(estado['cena'])
    if cena is not None:
        with bpy.context.temp_override(scene=cena, view_layer=cena.view_layers[0]):
            terminar(bpy.context, cancelar=True, remover_timer=False)
    else:
        terminar(remover_timer=False)
    return None


def iniciar(context, alvo, backup):
    parametros = preparar(context, alvo, backup)
    try:
        resultado = bpy.ops.object.cabinet_transformar_volume(
            'INVOKE_DEFAULT', TRANSFORM_OT_translate=parametros)
        if 'RUNNING_MODAL' not in resultado:
            terminar(context, cancelar=True)
            return False
        # Inserido depois, observa ANTES do translate e devolve TODOS os
        # eventos a ele. Nao substitui o keymap nem o snap do Blender.
        bpy.ops.object.cabinet_observar_volume('INVOKE_DEFAULT')
        bpy.app.timers.register(_acompanhar, first_interval=0.0)
        return True
    except Exception:
        terminar(context, cancelar=True)
        raise


class OBJECT_OT_observar_volume(Operator):
    bl_idname = 'object.cabinet_observar_volume'
    bl_label = 'Sincronizar Base do Volume'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        if not _estado[0]:
            return {'CANCELLED'}
        self._sessao = id(_estado[0])
        _remover_observador()
        _timer_observador[0] = context.window_manager.event_timer_add(.03, window=context.window)
        try:
            context.window_manager.modal_handler_add(self)
        except Exception:
            _remover_observador()
            raise
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not _estado[0]:
            # O tick deixa este handler sair mesmo sem outro movimento do
            # mouse apos confirmar. Unregister remove o timer diretamente.
            _remover_observador()
            return {'FINISHED', 'PASS_THROUGH'}
        if id(_estado[0]) != self._sessao:
            return {'FINISHED', 'PASS_THROUGH'}
        if _eventos._desfazendo[0]:
            return {'PASS_THROUGH'}
        try:
            if _evento_base_snap(context, event):
                preparar_base_snap(context)
        except Exception as erro:
            terminar(context, cancelar=True)
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED', 'PASS_THROUGH'}
        return {'PASS_THROUGH'}

    def cancel(self, context):
        if _estado[0] and id(_estado[0]) == self._sessao:
            terminar(context, cancelar=True)


class OBJECT_OT_confirmar_volume(Operator):
    bl_idname = 'object.cabinet_confirmar_volume'
    bl_label = 'Confirmar Volume'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        if not _estado[0]:
            return {'CANCELLED'}
        try:
            atualizar(context)
            if _estado[0].get('erro'):
                raise ValueError(_estado[0]['erro'])
        except Exception as erro:
            terminar(context, cancelar=True)
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        terminar()
        return {'FINISHED'}


class OBJECT_OT_transformar_volume(Macro):
    bl_idname = 'object.cabinet_transformar_volume'
    bl_label = 'Editar Volume'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}


def registrar_macro():
    OBJECT_OT_transformar_volume.define('TRANSFORM_OT_translate')
    OBJECT_OT_transformar_volume.define('OBJECT_OT_cabinet_confirmar_volume')
