"""Local view of a wall face and preset distribution on that face.

The session stores only names and numbers: undo can destroy any ID.
Geometry and coordinates belong to walls; resizing belongs to cabinets."""

import math
import time
import bpy
import numpy as np
import blf
import gpu
from bpy.props import StringProperty
from bpy.types import Operator, Menu, Macro
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector, Quaternion
from mathutils.geometry import intersect_line_plane
from mathutils.bvhtree import BVHTree

_paredes = _modulos = _biblioteca = _chapas = _hud = None
_gaveta = _opcoes = _eventos = _biblioteca_faixa = None
_paredes_composicao = _paredes_selecao = None
_ambientes = None
_alvenaria = None
_gavetas = None

_sessao = [None]
_ultima_face = [None]
_alvo_contexto = [None]
_sequencia = [0]
_aviso = ['']
_handler = [None]
_plano = [None]
_escolha_area = [None]
_snap_area = [None]
ALVO_AREA = '__PAREDE_AREA__'
METODOS_AREA = (('AUTO',"Automatic"),('PONTOS',"By points"))
ALVO_QUANTIDADE = 'paredes_quantidade'
CHAVE_VISUAL = 'cabinet_parede_exibicao_2d'
CHAVE_ORDEM = 'parede_ordem_posicionamento'
CHAVE_FIOS = 'cabinet_parede_arestas_2d'
CHAVE_SNAP = 'cabinet_parede_snap_2d'
SNAP_DA_VISTA = {'use_snap': True, 'snap_elements': {'VERTEX'},
                 'snap_target': 'CLOSEST', 'use_snap_translate': True,
                 'use_snap_selectable': False}


def superficie(obj):
    return (obj is not None and obj.type == 'MESH'
            and not obj.get(_paredes_selecao.MARCA_EXIBICAO)
            and not obj.get(_paredes_selecao.MARCA_MODULO_RECORTADO)
            and not _paredes.eh_movel(obj) and _alvenaria.grupo_de(obj) is None)


def lembrar_face(context, posicao, contexto=False):
    """Observe only the raycast; Blender still owns selection."""
    acerto = _hud._raio_cru(context, posicao)
    if contexto:
        _alvo_contexto[0] = acerto[0].name if acerto and superficie(acerto[0]) else ''
    if acerto and superficie(acerto[0]) and _paredes.eixos_da_parede(acerto[2]):
        obj, ponto, normal, face, _matriz = acerto
        _ultima_face[0] = (obj.name, tuple(obj.matrix_world.inverted_safe() @ ponto),
                          tuple(obj.matrix_world.to_3x3().transposed() @ normal), face)


def face_do_objeto(context, obj):
    if not superficie(obj):
        return None
    # Tab can change the outline without changing the vertex count.
    # Read this on entry, never while drawing the sidebar.
    _paredes._retangulos.clear()
    anterior = _ultima_face[0]
    if anterior and anterior[0] == obj.name:
        ponto = obj.matrix_world @ Vector(anterior[1])
        normal = _paredes._normal_no_mundo(obj, anterior[2])
        regiao = _paredes.regiao_da_parede(obj, ponto, normal,
                    context.evaluated_depsgraph_get(), anterior[3])
        if regiao:
            return ponto, normal, regiao
    # The Outliner supplies no face: choose the largest face toward the view.
    area = viewport(context)
    frente = (area.spaces.active.region_3d.view_rotation @ Vector((0, 0, 1))
              if area else Vector((0, -1, 0)))
    avaliado = obj.evaluated_get(context.evaluated_depsgraph_get())
    normal_mundo = obj.matrix_world.to_3x3().inverted_safe().transposed()
    candidatas = []
    for poly in avaliado.data.polygons:
        normal = (normal_mundo @ poly.normal).normalized()
        if (_paredes.eixos_da_parede(normal) and normal.dot(frente) > 0
                and (not _paredes.alvenaria_definida(obj)
                     or _alvenaria.superficie(obj, poly.index, normal, avaliado.data) == 'PAREDE')):
            # Evaluate area in world space, including walls with scale.
            escala_area = abs(obj.matrix_world.to_3x3().determinant()) * (
                normal_mundo @ poly.normal).length
            candidatas.append((poly.area * escala_area, normal.dot(frente), poly.index))
    if not candidatas:
        return None
    indice = max(candidatas)[2]
    poly = avaliado.data.polygons[indice]
    ponto = obj.matrix_world @ poly.center
    normal = (normal_mundo @ poly.normal).normalized()
    regiao = _paredes.regiao_da_parede(obj, ponto, normal,
                                     context.evaluated_depsgraph_get(), indice)
    return (ponto, normal, regiao) if regiao else None


def viewport(context):
    s = _sessao[0]
    if s:
        return next((a for a in context.screen.areas
                     if a.as_pointer() == s['area']), None) if context.screen else None
    return _biblioteca_faixa.viewport(context.screen) if context.screen else None


def _janela_da_sessao():
    s = _sessao[0]
    if s is None:
        return None, None, None
    for janela in bpy.context.window_manager.windows:
        if janela.as_pointer() != s['janela']:
            continue
        area = next((a for a in janela.screen.areas if a.as_pointer() == s['area']), None)
        regiao = next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None
        return janela, area, regiao
    return None, None, None


def ativa(context=None):
    s = _sessao[0]
    return bool(s and (context is None or (context.scene.name == s['cena']
                and context.window and context.window.as_pointer() == s['janela'])))


def associados(parede, ponto, normal, objetos, regiao=None):
    """Also filter by plane: one object can have two opposite faces."""
    resultado = []
    for obj in objetos:
        if _chapas.MARCA_CONJUNTO not in obj or _paredes.parede_do_modulo(obj) != parede:
            continue
        plano = _paredes.plano_do_modulo(obj, parede)
        if plano and plano[1].dot(normal) >= _paredes.COPLANAR_MIN and abs(
                (plano[0] - ponto).dot(normal)) <= _paredes.TOLERANCIA_PLANO_M:
            if regiao is not None:
                if regiao.get('delimitada'):
                    editaveis = (_sessao[0] or {}).get('editaveis', ())
                    restritos = (_sessao[0] or {}).get('restritos', ())
                    if obj.name not in editaveis and obj.name not in restritos and not _paredes_selecao.modulo_na_regiao(obj,regiao,normal):
                        continue
                    resultado.append(obj)
                    continue
                propria = _paredes.regiao_da_parede(parede, plano[0], plano[1],
                        bpy.context.evaluated_depsgraph_get(), obj.get(_paredes.CHAVE_PAREDE_FACE))
                if propria is None or propria['face'] not in regiao['faces']:
                    continue
            resultado.append(obj)
    return resultado


def _visiveis_da_face(context, parede, ponto, normal):
    manter = {parede.name}
    for modulo in associados(parede, ponto, normal, context.scene.objects,
                             _sessao[0]['regiao'] if ativa(context) else None):
        manter.add(modulo.name)
        manter.update(o.name for o in modulo.children_recursive)
    return manter


def _aplicar_isolamento(context, area, manter):
    espaco = area.spaces.active
    s = _sessao[0]
    s['local_anterior'] = espaco.local_view is not None
    context.view_layer.update()
    s['membros_anteriores'] = [o.name for o in context.scene.objects
                                if espaco.local_view and esta_na_vista(o, espaco, context)]
    if not espaco.local_view:
        selecionados = [o.name for o in context.selected_objects]
        ativo = context.view_layer.objects.active
        nome_ativo = ativo.name if ativo else ''
        try:
            for obj in context.selected_objects:
                obj.select_set(False)
            for nome in manter:
                obj = context.view_layer.objects.get(nome)
                if obj is not None and not obj.hide_get() and not obj.hide_viewport:
                    obj.select_set(True)
            bpy.ops.view3d.localview(frame_selected=False)
        finally:
            for obj in context.selected_objects:
                obj.select_set(False)
            for nome in selecionados:
                obj = context.view_layer.objects.get(nome)
                if obj is not None:
                    obj.select_set(True)
            context.view_layer.objects.active = context.view_layer.objects.get(nome_ativo)
    if espaco.local_view is None:
        raise ValueError("Could not isolate the wall in this viewport")
    for obj in context.scene.objects:
        obj.local_view_set(espaco, obj.name in manter)
    context.view_layer.update()


def esta_na_vista(obj, espaco, context):
    # In 4.2, the getter reads base_local_view_bits from the evaluated copy; the setter writes
    # to the layer's Base. The 5.x getter reads Base directly.
    if bpy.app.version < (4, 3, 0):
        obj = obj.evaluated_get(context.evaluated_depsgraph_get())
    return obj.local_view_get(espaco)


def modulo_da_peca(context, obj):
    """In the isolated viewport, any component of a cabinet on the face (door,
    drawer, shelf, or handle) represents that cabinet: native G moves
    the whole cabinet, as requested by the user."""
    if (obj is None or not ativa(context) or context.area is None
            or context.area.as_pointer() != _sessao[0]['area']):
        return None
    modulo = _paredes.modulo_de(obj)
    resumo = _paredes_composicao._resumo[0]
    if modulo and modulo_editavel(modulo) and resumo and any(f['nome'] == modulo.name for f in resumo['itens']):
        return modulo
    return None


def modulo_editavel(modulo):
    # Eligibility is determined on entry, not by position after a gesture.
    return not _sessao[0] or modulo is None or modulo.name not in _sessao[0].get('restritos', ())


def _tecla_de_mover(context, event):
    """The user's native G keymap shortcut, which may have been reassigned."""
    configs = context.window_manager.keyconfigs.user
    mapas = (configs.keymaps.get(nome) for nome in ('Object Mode', '3D View'))
    return any(getattr(km and km.keymap_items.match_event(event), 'idname', '')
               == 'transform.translate' for km in mapas)


def modulo_para_mover(context, event, regiao):
    """Name of the cabinet moved along the wall plane by the user's G shortcut
    or left drag (`OBJECT_OT_mover_na_parede`), or None to let Blender handle it.
    With multiple cabinets selected, G and drag remain native; 2D snapping
    is applied on release."""
    if event.value != 'PRESS' or event.shift or event.ctrl or event.alt or event.oskey:
        return None
    if event.type == 'LEFTMOUSE':
        atingido = _hud._raio_hud(context, (event.mouse_x - regiao.x, event.mouse_y - regiao.y))
        obj = atingido[0] if atingido else None
        modulo = modulo_da_peca(context, obj)
        if modulo is None or (obj.select_get() and any(
                _paredes.modulo_de(o) != modulo
                for o in context.selected_objects)):
            return None
        return modulo.name
    if not _tecla_de_mover(context, event):
        return None
    obj = context.object
    modulo = modulo_da_peca(context, obj) if obj is not None and obj.select_get() else None
    if modulo is None or any(_paredes.modulo_de(o) != modulo
                             for o in context.selected_objects):
        return None
    return modulo.name


def _preparar_fios(objetos):
    # Wood only: hardware wireframes would expose triangles and rig controls.
    for obj in objetos:
        if obj.type == 'MESH' and _chapas.MARCA_CHAPA in obj:
            if CHAVE_FIOS not in obj:
                obj[CHAVE_FIOS] = obj.show_wire
            obj.show_wire = True


def _restaurar_fios():
    for obj in bpy.data.objects:
        if CHAVE_FIOS in obj:
            obj.show_wire = bool(obj[CHAVE_FIOS])
            del obj[CHAVE_FIOS]


def _preparar_visual(area, parede):
    espaco = area.spaces.active
    s = _sessao[0]
    s['visual'] = {
        'shading': {k: getattr(espaco.shading, k) for k in ('type', 'light', 'color_type', 'show_xray', 'show_object_outline')},
        'overlay': {k: getattr(espaco.overlay, k) for k in ('show_floor', 'show_axis_x', 'show_axis_y',
                                'show_relationship_lines', 'show_extras', 'show_outline_selected')},
        'parede_exibicao': parede.display_type,
    }
    s['visual']['shading']['object_outline_color'] = tuple(espaco.shading.object_outline_color)
    # Native outlines highlight the components without hiding the wall surface.
    espaco.shading.type = 'SOLID'
    espaco.shading.light = 'FLAT'
    espaco.shading.color_type = 'OBJECT'
    espaco.shading.show_xray = False
    espaco.shading.show_object_outline = True
    espaco.shading.object_outline_color = (0, 0, 0)
    for k in s['visual']['overlay']:
        setattr(espaco.overlay, k, False)
    parede[CHAVE_VISUAL] = parede.display_type
    parede.display_type = 'SOLID'
    _preparar_fios(o for o in bpy.context.scene.objects if o.visible_get(viewport=espaco))
    # Use NATIVE vertex snapping during this view: G aligns corners
    # without Ctrl; B selects the source vertex. Restore on exit.
    _guardar_snap(bpy.context.scene)


def _guardar_snap(cena):
    # Keep the previous state ON THE SCENE: undo restores tool_settings from the snapshot
    # along with the marker, so the timer can restore the user's snap settings.
    ajustes = cena.tool_settings
    cena[CHAVE_SNAP] = {k: ','.join(sorted(getattr(ajustes, k))) if k == 'snap_elements'
                        else getattr(ajustes, k) for k in SNAP_DA_VISTA}
    for k, valor in SNAP_DA_VISTA.items():
        setattr(ajustes, k, valor)


def _devolver_snap(cena):
    anterior = cena.get(CHAVE_SNAP)
    if anterior is None:
        return
    ajustes = cena.tool_settings
    for k in SNAP_DA_VISTA:
        if k not in anterior:
            continue
        valor = anterior[k]
        if k == 'snap_elements':
            valor = {e for e in str(valor).split(',') if e}
        elif k == 'snap_target':
            valor = str(valor)
        else:
            valor = bool(valor)
        setattr(ajustes, k, valor)
    del cena[CHAVE_SNAP]


def _restaurar_visual(area, s):
    visual = s.get('visual')
    if visual is None:
        return
    espaco = area.spaces.active
    for k, valor in visual['shading'].items():
        setattr(espaco.shading, k, valor)
    for k, valor in visual['overlay'].items():
        setattr(espaco.overlay, k, valor)
    parede = bpy.data.objects.get(s['parede'])
    if parede and parede.display_type in {'WIRE', 'SOLID'}:
        parede.display_type = visual['parede_exibicao']
    if parede and CHAVE_VISUAL in parede:
        del parede[CHAVE_VISUAL]
    cena = bpy.data.scenes.get(s['cena'])
    if cena is not None:
        _devolver_snap(cena)
    _restaurar_fios()


def iniciar(context, obj, face=None, recortar=False):
    if _eventos._desfazendo[0]:
        return "Wait for undo/redo processing"
    face = face if face is not None else face_do_objeto(context, obj)
    area = viewport(context)
    if face is None or area is None:
        return "Select a planar vertical face facing the view"
    ponto, normal, regiao = face
    n, u = _paredes.eixos_da_parede(normal)
    # The initial version does not project sloped walls as vertical ones.
    # Reject BEFORE ending the session: a wrong face must not discard the current session.
    if abs(normal.z) > 0.001:
        return "2D editing requires a vertical face"
    encerrar()
    # After ending the session: switching walls has already restored the user's view.
    perspectiva_anterior = area.spaces.active.region_3d.view_perspective
    _sequencia[0] = time.monotonic_ns()
    _sessao[0] = {
        'id': _sequencia[0], 'janela': context.window.as_pointer(),
        'area': area.as_pointer(), 'cena': context.scene.name,
        'camada': context.view_layer.name,
        'parede': obj.name, 'ponto': tuple(ponto), 'normal': tuple(n),
        'u': tuple(u), 'face': regiao['face'],
        'regiao': dict(regiao, retangulo=tuple(regiao['retangulo']),
                      contorno=[(tuple(a), tuple(b)) for a, b in regiao['contorno']],delimitada=recortar),
        'modelo': None, 'substituir': '', 'ultimo_modulo': '',
        'perspectiva_anterior': perspectiva_anterior,
        'escolhendo': False, 's': sum(regiao['retangulo'][:2]) / 2,
        'quantidade': 1, 'esquerda': 0.0, 'direita': 0.0, 'espacamento': 0.0,
        'ajuste_maximo': context.scene.get('parede_ajuste_maximo_mm', 10.0),
        'instalacao': regiao['retangulo'][2] * 1000.0,
        'altura': 720.0, 'profundidade': 550.0,
        'local_anterior': False, 'membros_anteriores': [],
        'enquadrando': True,
        'recorte_explicito': recortar, 'exibicao': '',
        'parede_matriz': _paredes._assinatura(obj.matrix_world),
    }
    reg = next(r for r in area.regions if r.type == 'WINDOW')
    try:
        regiao = _regiao_acima_do_apoio(context, _sessao[0])
        if regiao is not _sessao[0]['regiao']:
            recortar = True
            _sessao[0].update(regiao=regiao, recorte_explicito=True,
                             instalacao=regiao['retangulo'][2] * 1000)
        with context.temp_override(area=area, region=reg):
            manter=_visiveis_da_face(context,obj,ponto,n)
            for instalado in context.scene.objects:
                if _alvenaria.MARCA not in instalado or _alvenaria.apoio_de(instalado) != obj:
                    continue
                resolvido = _alvenaria.resolver(instalado)
                if resolvido and resolvido[1].to_3x3().col[2].dot(n) > .999:
                    centro = resolvido[1].translation
                    s0, s1, z0, z1 = regiao['retangulo']
                    if s0 <= centro.dot(u) <= s1 and z0 <= centro.z <= z1:
                        manter.update(o.name for o in (instalado, *instalado.children) if not o.hide_select)
            if recortar:
                exibicao=_paredes_selecao.criar_exibicao(context,obj,regiao)
                _sessao[0]['exibicao']=exibicao.name
                manter.add(exibicao.name)
                modulos = associados(obj, ponto, n, context.scene.objects, regiao)
                editaveis, bloqueados, exibicoes = _paredes_selecao.recortar_modulos(context, modulos, regiao, n)
                _sessao[0]['editaveis'] = editaveis
                _sessao[0]['restritos'] = {m.name for m in modulos} - editaveis
                manter.difference_update(bloqueados)
                manter.update(exibicoes)
            _aplicar_isolamento(context, area, manter)
            if recortar:
                obj.local_view_set(area.spaces.active,False)
            _preparar_visual(area, obj)
            rv = area.spaces.active.region_3d
            rot = Matrix((u, Vector((0, 0, 1)), n)).transposed().to_quaternion()
            s0, s1, z0, z1 = regiao['retangulo']
            rv.view_rotation = rot
            rv.view_perspective = 'ORTHO'
            rv.view_location = ponto + u * ((s0 + s1) / 2 - ponto.dot(u))
            rv.view_location.z = (z0 + z1) / 2
            aspecto = reg.width / max(1, reg.height)
            rv.view_distance = max(z1 - z0, (s1 - s0) / aspecto) * 1.4
            _sessao[0]['rotacao'] = tuple(rv.view_rotation)
            if not bpy.app.background:
                bpy.ops.object.cabinet_observar_parede('INVOKE_DEFAULT')
        _handler[0] = bpy.types.SpaceView3D.draw_handler_add(desenhar, (), 'WINDOW', 'POST_PIXEL')
        _paredes._uid_da_parede(obj)
        modulos = associados(obj, ponto, n, context.scene.objects, regiao)
        ultimo = max(modulos, key=lambda o: o.get(CHAVE_ORDEM, 0), default=None)
        _sessao[0]['ultimo_modulo'] = ultimo.name if ultimo else ''
        _paredes_composicao.atualizar(context)
        _paredes_composicao.sincronizar_guias(context)
    except Exception as erro:
        encerrar()
        return str(erro)
    _aviso[0] = ''
    _redesenhar()
    return None


def encerrar(perspectiva=False):
    encerrar_escolha()
    s = _sessao[0]
    if s is None:
        return
    janela, area, regiao = _janela_da_sessao()
    if s.get('categorias'):
        if janela and area and regiao:
            with bpy.context.temp_override(window=janela,area=area,region=regiao):
                _ambientes.sair_categorias_2d(bpy.context)
        else:_ambientes.encerrar_selecao()
    cena_atual = janela.scene if janela else None
    camada_atual = janela.view_layer.name if janela else ''
    try:
        if area and area.type == 'VIEW_3D':
            _restaurar_visual(area, s)
        if area and area.type == 'VIEW_3D' and area.spaces.active.local_view:
            cena = bpy.data.scenes.get(s['cena']) or janela.scene
            camada = cena.view_layers.get(s['camada']) or cena.view_layers[0]
            # Local View queries the window's REAL scene in C. Overriding
            # only scene/view_layer mixes Bases from different scenes
            # and crashes 4.2/5.2. Restore in the actual window without redrawing.
            janela.scene = cena
            janela.view_layer = camada
            with bpy.context.temp_override(window=janela, area=area, region=regiao):
                if s['local_anterior']:
                    membros = set(s['membros_anteriores'])
                    for obj in cena.objects:
                        obj.local_view_set(area.spaces.active, obj.name in membros)
                else:
                    # Blender restores the previous viewpoint when leaving Local
                    # View. Keeping the current view lets the orbit gesture continue.
                    rv = area.spaces.active.region_3d
                    vista = (rv.view_rotation.copy(), rv.view_location.copy(),
                             rv.view_distance, rv.view_perspective)
                    bpy.ops.view3d.localview(frame_selected=False)
                    rv.view_rotation, rv.view_location, rv.view_distance, rv.view_perspective = vista
                camada.update()
        if area and area.type == 'VIEW_3D':
            rv = area.spaces.active.region_3d
            if rv.view_perspective == 'ORTHO' and (perspectiva or s.get('perspectiva_anterior') == 'PERSP'):
                rv.view_perspective = 'PERSP'
    finally:
        _restaurar_fios()
        if janela and cena_atual and janela.scene != cena_atual:
            janela.scene = cena_atual
            janela.view_layer = cena_atual.view_layers.get(camada_atual) or cena_atual.view_layers[0]
        _sessao[0] = None
        if not _eventos._desfazendo[0]:
            _paredes_selecao.limpar_exibicoes()
        _paredes_composicao.esquecer()
        _paredes_composicao.remover_objeto_guias()
        _plano[0] = None
        if _handler[0] is not None:
            bpy.types.SpaceView3D.draw_handler_remove(_handler[0], 'WINDOW')
            _handler[0] = None
        _redesenhar()


def _redesenhar():
    _paredes._redesenhar()


def verificar(atualizar_previa=True):
    if _eventos._desfazendo[0]:
        return
    if not ativa():
        _paredes_selecao.limpar_exibicoes()
        _restaurar_fios()
        # Undo/redo may restore the temporary appearance stored in the
        # snapshot. The marker identifies only changes made by 2D mode.
        guias = False
        for obj in bpy.context.scene.objects:
            if CHAVE_VISUAL in obj:
                if obj.display_type in {'WIRE', 'SOLID'}:
                    obj.display_type = obj[CHAVE_VISUAL]
                del obj[CHAVE_VISUAL]
            guias = guias or _paredes_composicao.MARCA_OBJETO_GUIAS in obj
        if guias:
            _paredes_composicao.remover_objeto_guias()
        for cena in bpy.data.scenes:
            _devolver_snap(cena)
        return
    s = _sessao[0]
    janela, area, regiao = _janela_da_sessao()
    if (area is None or area.type != 'VIEW_3D' or janela.scene.name != s['cena']
            or bpy.data.objects.get(s['parede']) is None):
        encerrar()
        return
    rv = area.spaces.active.region_3d
    if s.get('recorte_explicito'):
        fonte=bpy.data.objects.get(s['parede'])
        if (bpy.data.objects.get(s.get('exibicao','')) is None or
                fonte is not None and (fonte.data.is_editmode and not s.get('categorias')
                                       or _paredes._assinatura(fonte.matrix_world)!=s['parede_matriz'])):
            encerrar()
            return
        if fonte is not None and bpy.context.object!=fonte and any(o.select_get() for o in bpy.context.selected_objects):
            fonte.select_set(False)
    mudou = abs(rv.view_rotation.dot(Quaternion(s['rotacao']))) < 0.999999
    if mudou or rv.view_perspective != 'ORTHO' or area.spaces.active.local_view is None:
        encerrar(perspectiva=mudou)
    elif s.get('categorias'):
        fonte=bpy.data.objects.get(s['parede'])
        if fonte is None or not fonte.data.is_editmode:
            with bpy.context.temp_override(window=janela,area=area,region=regiao):
                _ambientes.sair_categorias_2d(bpy.context)
    elif atualizar_previa:
        with bpy.context.temp_override(window=janela, area=area, region=regiao):
            if s.get('enquadrando') and not bpy.app.background:
                _enquadrar(bpy.context, s)
            _paredes_composicao.encaixar_movidos(bpy.context)
            _paredes_composicao.atualizar(bpy.context)
            if s['modelo'] is None:
                return
            plano = planejar(bpy.context, s)
            if plano != _plano[0]:
                _plano[0] = plano
                _redesenhar()


def _enquadrar(context, s):
    # The native projection updates only on redraw. Adjusting on the next tick
    # accounts for the lens, aspect ratio, and ACTUAL region size.
    u, ponto = Vector(s['u']), Vector(s['ponto'])
    s0, s1, z0, z1 = s['regiao']['retangulo']
    projetados = []
    for x in (s0, s1):
        for z in (z0, z1):
            p = ponto + u * (x - ponto.dot(u))
            p.z = z
            q = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, p)
            if q is not None:
                projetados.append(q)
    if len(projetados) != 4:
        return
    fator = max((max(p.x for p in projetados) - min(p.x for p in projetados)) / (context.region.width * .8),
                (max(p.y for p in projetados) - min(p.y for p in projetados)) / (context.region.height * .8))
    if abs(fator - 1) > .02:
        context.region_data.view_distance *= fator
        context.area.tag_redraw()
    else:
        s['enquadrando'] = False


def navegacao_de_saida(context, event):
    """Query the user's keymap, including Walk/Fly before the first movement."""
    if event.value not in {'PRESS', 'ANY', 'NOTHING'}:
        return False
    operadores = {'view3d.walk', 'view3d.fly', 'view3d.rotate', 'view3d.view_axis',
                  'view3d.view_orbit', 'view3d.view_persportho', 'view3d.view_camera'}
    km = context.window_manager.keyconfigs.user.keymaps.get('3D View')
    item = km.keymap_items.match_event(event) if km else None
    return item is not None and item.idname in operadores


def contexto_painel(context):
    escolha=_escolha_area[0]
    if escolha:
        return bpy.data.objects.get(escolha['objeto'])
    if ativa(context):
        return bpy.data.objects.get(_sessao[0]['parede'])
    obj = context.object
    return obj if superficie(obj) and obj.select_get() else None


def widgets(context, itens, x, topo, w, compacto=False):
    obj = contexto_painel(context)
    if obj is None or not (_paredes.alvenaria_definida(obj) or ativa(context)):
        return topo
    s_faces = _ambientes._edicao_faces[0]
    if s_faces and s_faces.get('classificar'):
        return topo
    topo = _gaveta._titulo_secao(itens, x, topo + 26, w, "Masonry")
    def botao(rotulo, operador, altura=28):
        nonlocal topo
        topo -= altura
        itens.append((x, topo, w, altura, rotulo, ('operador', operador)))
        topo -= 6
    # Enter/exit: a 30 px orange button like "Create Shelves"
    # (`_gaveta.OPERADORES_DESTAQUE`).
    if not ativa(context):
        if context.mode=='EDIT_MESH':
            return _ambientes.widgets(context,itens,obj,x,topo,w)
        topo-=30
        metade=(w-6)/2
        itens.append((x,topo,metade,30,"Edit in 2D",('operador','object.cabinet_editar_parede')))
        itens.append((x+metade+6,topo,metade,30,"Edit categories",('operador','object.cabinet_editar_ambientes')))
        topo-=6
        topo-=30
        itens.append((x,topo,w,30,"Disassemble Masonry",('operador','object.cabinet_definir_alvenaria',False,'desagregar')))
        topo-=6
        if _aviso[0]:
            itens.append((x, topo - 20, w, 20, _aviso[0], None))
            topo -= 26
        return topo - (12 if compacto else 58)
    s = _sessao[0]
    if s.get('categorias'):
        return _ambientes.widgets(context,itens,obj,x,topo,w)
    botao("Exit wall editing", 'object.cabinet_sair_parede', 30)
    botao("Edit categories",'object.cabinet_editar_ambientes')
    topo = _paredes_composicao.widgets(context, itens, x, topo - 12, w)
    topo = _paredes_composicao.widgets_guias(context, itens, x, topo, w)
    itens.append((x, topo - 37, w, 37, "Maximum adjustment: %s" % _opcoes._texto_medida(s['ajuste_maximo']),
                  ('medida', 'paredes', 'ajuste_maximo', "Maximum adjustment", s['ajuste_maximo'])))
    topo -= 45
    # Left/Right/Spacing gaps were removed from the menu at the user's request;
    # distribution still uses the session values.
    if s['modelo'] is None:
        mensagem = "Choose the new model from the library" if s.get('substituir') else "Choose a cabinet from the library"
        itens.append((x, topo - 20, w, 20, mensagem, None))
        return topo - 58
    itens.append((x, topo - 20, w, 20, s['modelo']['nome'], None))
    topo -= 28
    if s.get('substituir'):
        itens.append((x, topo - 20, w, 20, "Keeps position, size and attachment", None))
        topo -= 26
        botao("Replace cabinet", 'object.cabinet_distribuir_parede')
        botao("Cancel preview", 'object.cabinet_cancelar_previa_parede')
        return topo - 58
    campos = []
    for nome, rotulo in (('instalacao', "Installation"), ('altura', "Height"),
                         ('profundidade', "Depth")):
        campos.append(('%s: %s' % (rotulo, _opcoes._texto_medida(s[nome])),
                       ('medida', 'paredes', nome, rotulo, s[nome])))
    campos.append((str(s['quantidade']),
                  ('contador', ALVO_QUANTIDADE, s['quantidade'], 1, 100,
                   '', "Quantity")))
    topo = _gaveta._campos_em_linhas(context, itens, x, topo, w, campos)
    botao("Click the opening in the viewport" if s['escolhendo'] else "Choose opening on wall",
          'object.cabinet_escolher_vao_parede')
    plano = _plano[0] or {'erro': "Calculating preview..."}
    mensagem = plano.get('erro') or "Width per cabinet: %s" % _opcoes._texto_medida(plano['largura'] * 1000)
    itens.append((x, topo - 20, w, 20, mensagem, None))
    topo -= 26
    botao("Replace cabinet" if s.get('substituir') else "Create cabinets", 'object.cabinet_distribuir_parede')
    botao("Cancel preview", 'object.cabinet_cancelar_previa_parede')
    return topo - 58


def editar_parametro(nome, valor):
    s = _sessao[0]
    if s is None:
        return "Wall editing has ended"
    if nome == 'quantidade':
        if not 1 <= valor <= 100 or int(valor) != valor:
            return "Quantity must be an integer between 1 and 100"
        s[nome] = int(valor)
    elif nome in ('instalacao', 'altura', 'profundidade', 'esquerda', 'direita', 'espacamento', 'ajuste_maximo'):
        if not math.isfinite(valor) or valor < 0:
            return "The dimension must be positive or zero"
        s[nome] = valor
        if nome == 'ajuste_maximo':
            bpy.context.scene['parede_ajuste_maximo_mm'] = valor
    else:
        return "Unknown wall parameter"
    _redesenhar()
    _plano[0] = None
    return None


def _dados_antes():
    return {nome: set(getattr(bpy.data, nome).keys()) for nome in
            ('objects', 'collections', 'meshes', 'curves', 'materials', 'node_groups',
             'actions', 'images', 'cameras', 'lights', 'armatures', 'lattices', 'metaballs')}


def _limpar_tentativa(antes):
    for nome, existentes in antes.items():
        dados = getattr(bpy.data, nome)
        for item in list(dados):
            if item.name not in existentes:
                dados.remove(item, do_unlink=True)


def ponto_no_evento(context, event):
    """Query only the edited wall using native raycasting, including openings."""
    if not ativa(context):
        return None
    janela, area, regiao = _janela_da_sessao()
    xy = (event.mouse_x - regiao.x, event.mouse_y - regiao.y)
    if not (0 <= xy[0] < regiao.width and 0 <= xy[1] < regiao.height):
        return None
    rv = area.spaces.active.region_3d
    origem = view3d_utils.region_2d_to_origin_3d(regiao, rv, xy)
    direcao = view3d_utils.region_2d_to_vector_3d(regiao, rv, xy)
    s = _sessao[0]
    parede = bpy.data.objects.get(s.get('exibicao') or s['parede'])
    if parede is None:
        return None
    inversa = parede.matrix_world.inverted_safe()
    avaliado = parede.evaluated_get(context.evaluated_depsgraph_get())
    acertou, local, normal, face = avaliado.ray_cast(inversa @ origem, inversa.to_3x3() @ direcao)
    if not acertou or (not s.get('recorte_explicito') and face not in s['regiao']['faces']):
        return None
    return parede.matrix_world @ local


def posicao_do_modelo(context, modulo, ponto=None, caixa=None):
    """Place at the cursor or to the right of the last cabinet, without resizing its mesh."""
    s = _sessao[0]
    if not ativa(context):
        return None, "Wall editing has ended"
    caixa = caixa or _paredes.caixa_do_modulo(modulo)
    if caixa is None:
        return None, "The model must contain a complete cabinet"
    alvo = _alvo_do_modelo(context, modulo, ponto, caixa)
    return encaixar_na_face(context, modulo, alvo, s, caixa)


def _alvo_do_modelo(context, modulo, ponto, caixa):
    s = _sessao[0]
    lo, hi = caixa
    escala = _paredes.escala_no_referencial(modulo)
    largura, altura = (hi.x - lo.x) * escala.x, (hi.z - lo.z) * escala.z
    s0, s1, z0, z1 = s['regiao']['retangulo']
    esquerda, direita = s0 + s['esquerda'] / 1000, s1 - s['direita'] / 1000
    u, n, plano = (Vector(s[k]) for k in ('u', 'normal', 'ponto'))
    if ponto is None:
        ultimo = next((f for f in _paredes_composicao.itens_da_face(context)
                       if f['nome'] == s.get('ultimo_modulo')), None)
        centro = ultimo['fim'] + s['espacamento'] / 1000 + largura / 2 if ultimo else (s0 + s1) / 2
        if centro + largura / 2 > direita + .00005:
            centro = (s0 + s1) / 2
        base = ultimo['base'] if ultimo else max(z0, _paredes.ponto_das_costas(modulo, caixa).z)
    else:
        centro, base = ponto.dot(u), ponto.z - altura / 2
        janela, area, regiao = _janela_da_sessao()
        px = _paredes._px_por_metro(regiao, area.spaces.active.region_3d, ponto, u)
        if px:
            centro, base = _paredes.posicao_no_arraste(s['regiao']['retangulo'], centro,
                base, largura, altura, _paredes.SNAP_PX / px)
    alvo = plano + u * (centro - plano.dot(u))
    alvo.z = base + altura / 2
    return alvo


def encaixe_do_modelo(context, modulo, ponto=None, caixa=None, cache=None):
    caixa = caixa or _paredes.caixa_do_modulo(modulo)
    costas, erro = posicao_do_modelo(context, modulo, ponto, caixa)
    if not erro or caixa is None or not ativa(context):
        return costas, caixa, erro
    alvo = _alvo_do_modelo(context, modulo, ponto, caixa)
    costas, caixa, ajuste = ajustar_na_face(context, modulo, alvo, _sessao[0], caixa, cache)
    return costas, caixa, ('%s | %s' % (erro, ajuste)) if ajuste else None


def _objetos_vigentes_do_modelo(modulo, novos=None):
    # Resizing can remove/recreate hardware: the appended list no longer represents the assembly.
    objetos = [modulo, *modulo.children_recursive]
    if isinstance(novos, list):
        novos[:] = objetos
    return objetos


def registrar_posicionado(context, modulo, novos=()):
    """Include the instance in isolation and store only the last cabinet's name."""
    if modulo is None or _paredes.parede_do_modulo(modulo) is None:
        return
    _ambientes.atribuir(context,modulo)
    # The order survives leaving 2D or reopening the file without retaining global IDs.
    modulo[CHAVE_ORDEM] = time.time()
    objetos = _objetos_vigentes_do_modelo(modulo, novos)
    if not ativa(context):
        return
    s = _sessao[0]
    parede = bpy.data.objects.get(s['parede'])
    if modulo not in associados(parede, Vector(s['ponto']), Vector(s['normal']),
                                 context.scene.objects, s['regiao']):
        return
    s['ultimo_modulo'] = modulo.name
    s.setdefault('editaveis', set()).add(modulo.name)
    janela, area, regiao = _janela_da_sessao()
    if area.spaces.active.local_view:
        for obj in objetos:
            obj.local_view_set(area.spaces.active, True)
            if s['local_anterior'] and obj.name not in s['membros_anteriores']:
                s['membros_anteriores'].append(obj.name)
    context.view_layer.update()
    _preparar_fios(objetos)
    _paredes_composicao.atualizar(context)
    _redesenhar()


def posicionar_modelo(context, modulo, ponto=None, novos=()):
    original = _paredes.caixa_do_modulo(modulo)
    costas, caixa, erro = encaixe_do_modelo(context, modulo, ponto, original)
    if erro:
        return erro
    s = _sessao[0]
    erro = aplicar_ajuste_do_modelo(modulo, caixa, novos)
    if erro:
        return erro
    parede = bpy.data.objects[s['parede']]
    normal = Vector(s['normal'])
    _paredes.colocar_na_parede(modulo, parede, costas, normal)
    _paredes.associar(modulo, parede, costas, normal, s['face'])
    registrar_posicionado(context, modulo, novos)
    return None


def aplicar_ajuste_do_modelo(modulo, caixa, novos=None):
    try:
        return _redimensionar_modelo(modulo, caixa)
    finally:
        # Also on failure: cancellation must remove the current generated objects.
        _objetos_vigentes_do_modelo(modulo, novos)


def _redimensionar_modelo(modulo, caixa):
    original = _paredes.caixa_do_modulo(modulo)
    if any(abs((caixa[1] - caixa[0])[i] - (original[1] - original[0])[i]) > 1e-7 for i in range(3)):
        escala = _paredes.escala_no_referencial(modulo)
        medidas = tuple(abs((caixa[1] - caixa[0])[i] * escala[i]) * 1000 for i in (0, 2, 1))
        try:
            _modulos.redimensionar_orientado(modulo, _paredes.medidas_na_parede(modulo, medidas))
        except (ValueError, RuntimeError) as erro:
            return "Could not adjust the cabinet: %s" % erro
        # The domain may reject a physical minimum; never confirm a fictitious bounding box.
        real = _paredes.caixa_do_modulo(modulo)
        if real is None or any(abs((real[1] - real[0])[i] - (caixa[1] - caixa[0])[i]) > .00005 for i in range(3)):
            return "The adjustment exceeds the physical minimum dimensions of the cabinet panels"
    return None


def inserir_modelo(context, pasta, arquivo, tipo):
    """Immediate insertion reuses append; distribution remains explicit."""
    if _sessao[0].get('substituir'):
        return preparar_modelo(context, pasta, arquivo, tipo)
    antes = _dados_antes()
    selecionados = [o.name for o in context.selected_objects]
    ativo = context.object.name if context.object else ''
    try:
        novos, raizes, erro = _biblioteca.inserir_preset(context, pasta, arquivo, tipo, Vector((0, 0, 0)))
        if erro:
            raise ValueError(erro)
        modulos = [o for o in raizes if _chapas.MARCA_CONJUNTO in o]
        if tipo != 'modulo' or len(modulos) != 1 or len(raizes) != 1:
            raise ValueError("Choose a single complete cabinet")
        erro = posicionar_modelo(context, modulos[0], novos=novos)
        if erro:
            raise ValueError(erro)
        context.view_layer.objects.active = modulos[0]
        return None
    except Exception as erro:
        _limpar_tentativa(antes)
        for nome in selecionados:
            obj = context.view_layer.objects.get(nome)
            if obj:
                obj.select_set(True)
        context.view_layer.objects.active = context.view_layer.objects.get(ativo)
        return str(erro)


def preparar_modelo(context, pasta, arquivo, tipo):
    if not ativa(context):
        return "Enter wall editing"
    if tipo != 'modulo':
        return "Choose a complete cabinet from the library"
    antes = _dados_antes()
    selecao = [o.name for o in context.selected_objects]
    ativo = context.object.name if context.object else ''
    try:
        novos, raizes, erro = _biblioteca.inserir_preset(context, pasta, arquivo, tipo, Vector((0, 0, 0)))
        if erro:
            return erro
        modulos = [o for o in novos if _chapas.MARCA_CONJUNTO in o]
        if len(modulos) != 1 or any(o != modulos[0] for o in raizes):
            return "The model must contain a single complete cabinet"
        modulo = modulos[0]
        medidas = _modulos.medir_conjunto(modulo)
        if not medidas or min(medidas) <= 0:
            return "The model has no valid dimensions"
        medidas = _paredes.medidas_na_parede(modulo, medidas)
        s = _sessao[0]
        s.update(modelo={'pasta': pasta, 'arquivo': arquivo, 'tipo': tipo,
                         'nome': modulo.name}, altura=medidas[1], profundidade=medidas[2],
                 instalacao=max(s['regiao']['retangulo'][2] * 1000, modulo.matrix_world.translation.z * 1000),
                 escolhendo=True)
        if s.get('substituir'):
            alvo = bpy.data.objects.get(s['substituir'])
            if alvo is None:
                return "The cabinet to be replaced was removed"
            atual = _paredes_composicao.ficha(alvo, s)
            s.update(altura=atual['altura'] * 1000, profundidade=atual['profundidade'] * 1000,
                     instalacao=atual['base'] * 1000, quantidade=1, escolhendo=False)
        _plano[0] = None
        _aviso[0] = ''
    except Exception as erro:
        return str(erro)
    finally:
        _limpar_tentativa(antes)
        for obj in context.selected_objects:
            obj.select_set(False)
        for nome in selecao:
            obj = context.view_layer.objects.get(nome)
            if obj:
                obj.select_set(True)
        context.view_layer.objects.active = context.view_layer.objects.get(ativo)
        _redesenhar()
    return None


def _contorno_em_lote(regiao):
    """Outline as a numpy (k, 2, 3) array, stored on the region itself."""
    lote = regiao.get('_contorno_np')
    if lote is None:
        lote = np.array([(tuple(a), tuple(b)) for a, b in regiao['contorno']],
                        dtype=np.float64).reshape(-1, 2, 3)
        regiao['_contorno_np'] = lote
    return lote


def _intersectar_faixas(faixas, outras):
    return [(max(a, c), min(b, d)) for a, b in faixas for c, d in outras
            if min(b, d) - max(a, c) > 1e-6]


def faixas_da_face(regiao, u, base, topo):
    """Clip to the actual outline: holes and sloped sides are not usable area."""
    s0, s1, z0, z1 = regiao['retangulo']
    if base < z0 - 1e-6 or topo > z1 + 1e-6 or topo <= base:
        return []
    # A cabinet touching the edge may extend micrometers beyond it due to floating point
    # coordinates. Sampling outside the outline would invalidate an already tolerated fit.
    base, topo = max(z0, base), min(z1, topo)
    # Batch the queries: a real house wall has hundreds of outline edges,
    # and the Python loop was costly on every mouse movement (v321).
    lote = _contorno_em_lote(regiao)
    az, bz = lote[:, 0, 2], lote[:, 1, 2]
    u = np.array(tuple(u), dtype=np.float64)
    sa, sb = lote[:, 0] @ u, lote[:, 1] @ u
    pontas = np.concatenate((az, bz))
    pontas = pontas[(pontas > base) & (pontas < topo)]
    alturas = np.unique(np.concatenate((
        [base + 1e-7, topo - 1e-7], np.maximum(base + 1e-7, pontas - 1e-7),
        np.minimum(topo - 1e-7, pontas + 1e-7))))
    faixas = [(s0, s1)]
    for z in alturas:
        corta = ((az <= z) & (z < bz)) | ((bz <= z) & (z < az))
        t = (z - az[corta]) / (bz[corta] - az[corta])
        cruzamentos = np.sort(sa[corta] + (sb[corta] - sa[corta]) * t).tolist()
        faixas = _intersectar_faixas(faixas, list(zip(cruzamentos[::2], cruzamentos[1::2])))
    return faixas


def faixas_livres(context, s, base, topo, profundidade, excluir=()):
    """The same free area for insertion, dragging, editing, and distribution."""
    faixas = faixas_da_face(s['regiao'], Vector(s['u']), base, topo)
    for a, b in obstaculos(context, s, base, topo, profundidade, excluir):
        faixas = [(c, d) for c0, d0 in faixas for c, d in
                  ((c0, min(d0, a)), (max(c0, b), d0)) if d - c > 1e-6]
    return faixas


def _alturas_para_ajuste(context, s, profundidade, excluir):
    """Actual supports from the same BVH/clipping used for collision checks."""
    z0, z1 = s['regiao']['retangulo'][2:]
    alturas = [z0, z1]
    ponto, n, u = (Vector(s[k]) for k in ('ponto', 'normal', 'u'))
    parede = bpy.data.objects.get(s['parede'])
    for obj in associados(parede, ponto, n, context.scene.objects, s['regiao']):
        if obj.name not in excluir:
            ficha = _paredes_composicao.ficha(obj, s)
            alturas.extend((ficha['base'], ficha['base'] + ficha['altura']))
    dep = context.evaluated_depsgraph_get()
    for obj in context.scene.objects:
        if not superficie(obj):
            continue
        avaliado = obj.evaluated_get(dep)
        cx = _caixa_no_referencial(avaliado, u, n, ponto)
        if cx[3] <= z0 + 1e-6 or cx[2] >= z1 - 1e-6 or cx[5] <= 1e-5 or cx[4] >= profundidade:
            continue
        for a, b in _faces_no_volume(obj, avaliado, dep, s, z0, z1, profundidade, alturas=True):
            alturas.extend((a, b))
    return sorted({max(z0, min(z1, round(z, 6))) for z in alturas})


def _regiao_acima_do_apoio(context, s):
    """The visible base and dimension reference must not be buried in the actual floor."""
    regiao = s['regiao']
    s0, s1, z0, z1 = regiao['retangulo']
    # Only the wall contact strip defines the floor; furniture farther
    # forward remains a local obstacle without raising the entire wall.
    profundidade = _paredes.TOLERANCIA_PLANO_M
    parede = bpy.data.objects.get(s['parede'])
    ponto, n, u = (Vector(s[k]) for k in ('ponto', 'normal', 'u'))
    excluir = tuple(o.name for o in associados(parede, ponto, n, context.scene.objects, regiao))
    alturas = [z0, *(z for z in _alturas_para_ajuste(context, s, profundidade, excluir)
                     if z0 + 1e-6 < z < z1 - 1e-6), z1]
    base = z0
    for a, b in zip(alturas, alturas[1:]):
        if (not faixas_da_face(regiao, u, a, b) or
                faixas_livres(context, s, a, b, profundidade, excluir)):
            break
        base = b
    if base <= z0 + 1e-6 or base >= z1 - 1e-6:
        return regiao
    cantos = []
    for x, z in ((s0, base), (s1, base), (s1, z1), (s0, z1)):
        p = ponto + u * (x - ponto.dot(u))
        p.z = z
        cantos.append(p)
    return _paredes_selecao.recortar(regiao, cantos, n)


def ajustar_na_face(context, modulo, ponto, s, caixa, cache=None):
    """Reduce width/height within the limit; resize the wood only on confirmation."""
    limite = context.scene.get('parede_ajuste_maximo_mm', 10.0) / 1000
    erro = "No clear opening within the maximum adjustment of %.1f mm" % (limite * 1000)
    if not math.isfinite(limite) or limite <= 0:
        return None, caixa, erro
    escala = _paredes.escala_no_referencial(modulo)
    lo, hi = caixa
    largura, altura, prof = (abs((hi[i] - lo[i]) * escala[i]) for i in (0, 2, 1))
    minima_l, minima_a = max(.02, largura - limite), max(.02, altura - limite)
    s0, s1, z0, z1 = s['regiao']['retangulo']
    if s1 - s0 < minima_l - .00005 or z1 - z0 < minima_a - .00005:
        return None, caixa, erro
    cache = {} if cache is None else cache
    chave = (s['parede'], tuple(s['normal']), tuple(s['ponto']), tuple(s['regiao']['retangulo']), prof)
    if chave not in cache:
        cache.clear()
        cache[chave] = _alturas_para_ajuste(context, s, prof, (modulo.name,))
    alturas = cache[chave]
    alvo_base = max(z0, min(z1 - min(altura, z1 - z0), ponto.z - altura / 2))
    bases = {alvo_base, z0, max(z0, z1 - altura)}
    bases.update(z for z in alturas if z0 <= z <= z1 - minima_a + 1e-6)
    opcoes = set()
    for base in bases:
        for topo in [min(z1, base + altura), *alturas]:
            a = topo - base
            # Keep the opening under the cursor; do not jump to another row.
            if minima_a - 1e-6 <= a <= altura + 1e-6 and base - 1e-6 <= ponto.z <= topo + 1e-6:
                opcoes.add((base, min(altura, a)))
    melhor = None
    u, plano = Vector(s['u']), Vector(s['ponto'])
    for base, a in sorted(opcoes, key=lambda ba: (altura - ba[1], abs(ba[0] - alvo_base))):
        if melhor is not None and altura - a > melhor[0] + 1e-6:
            break
        faixa = ('faixas', base, a, prof)
        # The numeric cache belongs to the drag; confirmation repeats the query.
        if faixa not in cache:
            cache[faixa] = faixas_livres(context, s, base, base + a, prof, (modulo.name,))
        for inicio, fim in cache[faixa]:
            inicio = max(inicio, s0 + s.get('esquerda', 0) / 1000)
            fim = min(fim, s1 - s.get('direita', 0) / 1000)
            l = min(largura, fim - inicio)
            if l < minima_l - 1e-6:
                continue
            centro = max(inicio + l / 2, min(fim - l / 2, ponto.dot(u)))
            ordem = (largura - l + altura - a, abs(base - alvo_base) + abs(centro - ponto.dot(u)))
            if melhor is None or ordem < melhor[:2]:
                melhor = (*ordem, centro, base, l, a)
    if melhor is None:
        return None, caixa, erro
    _, _, centro, base, l, a = melhor
    costas = plano + u * (centro - plano.dot(u))
    costas.z = base
    alto = hi.copy()
    alto.x, alto.z = lo.x + l / abs(escala.x), lo.z + a / abs(escala.z)
    return costas, (lo.copy(), alto), None


def encaixar_na_face(context, modulo, ponto, s, caixa=None, tolerancia=0):
    """Constrain the entire volume and choose the valid opening nearest the target.

    Also accept a face outside 2D editing: right drag uses the same
    constraints without duplicating a placement tool or resizing components."""
    if _paredes.alvenaria_definida(bpy.data.objects.get(s['parede'])):
        p=_paredes.ponto_livre_na_face(modulo,ponto,s,caixa,tolerancia)
        return p, None if p is not None else "The model must contain a complete cabinet"
    caixa = caixa or _paredes.caixa_do_modulo(modulo)
    if caixa is None:
        return None, "The model must contain a complete cabinet"
    lo, hi = caixa
    escala = _paredes.escala_no_referencial(modulo)
    largura, altura, profundidade = (abs((hi[i] - lo[i]) * escala[i]) for i in (0, 2, 1))
    s0, s1, z0, z1 = s['regiao']['retangulo']
    esquerda, direita = s0 + s.get('esquerda', 0) / 1000, s1 - s.get('direita', 0) / 1000
    if min(largura, altura, profundidade) <= 0:
        return None, "The model has no valid dimensions"
    if largura > direita - esquerda + .00005 or altura > z1 - z0 + .00005:
        return None, "The original model size does not fit on the wall"
    u, plano = Vector(s['u']), Vector(s['ponto'])
    centro, base = ponto.dot(u), ponto.z - altura / 2
    if tolerancia:
        centro, base = _paredes.posicao_no_arraste(s['regiao']['retangulo'], centro,
                         base, largura, altura, tolerancia)
    base = max(z0, min(z1 - altura, base))
    faixas = faixas_livres(context, s, base, base + altura, profundidade, (modulo.name,))
    candidatos = []
    for a, b in faixas:
        a, b = max(a, esquerda), min(b, direita)
        if b - a >= largura - .00005:
            candidatos.append(max(a + largura / 2, min(b - largura / 2, centro)))
    if not candidatos:
        return None, "No clear opening without overlapping another cabinet or extending beyond the wall"
    centro = min(candidatos, key=lambda c: abs(c - centro))
    costas = plano + u * (centro - plano.dot(u))
    costas.z = base
    return costas, None


def _caixa_no_referencial(obj, u, n, plano):
    pontos = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return (min(p.dot(u) for p in pontos), max(p.dot(u) for p in pontos),
            min(p.z for p in pontos), max(p.z for p in pontos),
            min((p - plano).dot(n) for p in pontos), max((p - plano).dot(n) for p in pontos))


def _recortar_poligono(pontos, eixo, limite, sinal):
    """Clip only candidate faces found by the native BVH."""
    saida = []
    for a, b in zip(pontos, pontos[1:] + pontos[:1]):
        da, db = sinal * (a[eixo] - limite), sinal * (b[eixo] - limite)
        if da >= 0:
            saida.append(a)
        if (da >= 0) != (db >= 0):
            saida.append(a + (b - a) * (da / (da - db)))
    return saida


def _faces_no_volume(obj, avaliado, dep, s, base, topo, profundidade, alturas=False):
    """Native spatial query without scanning scene vertices during the gesture."""
    u, n, ponto = (Vector(s[k]) for k in ('u', 'normal', 'ponto'))
    s0, s1 = s['regiao']['retangulo'][:2]
    centro = ponto + u * ((s0 + s1) / 2 - ponto.dot(u)) + n * profundidade / 2
    centro.z = (base + topo) / 2
    raio = Vector(((s1 - s0) / 2, (topo - base) / 2, profundidade / 2)).length
    inversa = obj.matrix_world.inverted_safe()
    # Conservative bound for object nonuniform scale/shear.
    raio *= sum(inversa.to_3x3().col[i].length for i in range(3))
    arvore = BVHTree.FromObject(obj, dep)
    if arvore is None:
        return []
    indices = {acerto[2] for acerto in arvore.find_nearest_range(inversa @ centro, raio)}
    intervalos = []
    for indice in indices:
        poly = avaliado.data.polygons[indice]
        pontos = []
        for i in poly.vertices:
            p = obj.matrix_world @ avaliado.data.vertices[i].co
            pontos.append(Vector((p.dot(u), p.z, (p - ponto).dot(n))))
        for eixo, limite, sinal in ((0, s0, 1), (0, s1, -1), (1, base + 1e-6, 1),
                 (1, topo - 1e-6, -1), (2, 1e-5, 1), (2, profundidade - 1e-6, -1)):
            pontos = _recortar_poligono(pontos, eixo, limite, sinal)
            if not pontos:
                break
        if pontos:
            a, b = min(p.x for p in pontos), max(p.x for p in pontos)
            if b - a > 1e-6:
                intervalos.append((min(p.y for p in pontos), max(p.y for p in pontos)) if alturas else (a, b))
    return intervalos


def obstaculos(context, s, base, topo, profundidade, excluir=()):
    context.view_layer.update()
    parede = bpy.data.objects.get(s['parede'])
    ponto, n, u = (Vector(s[k]) for k in ('ponto', 'normal', 'u'))
    resultado = []
    modulos = associados(parede, ponto, n, context.scene.objects, s['regiao'])
    for modulo in modulos:
        if modulo.name in excluir:
            continue
        caixa = _paredes.caixa_do_modulo(modulo)
        if caixa is None:
            continue
        lo, hi = caixa
        pontos = [_paredes.referencial(modulo) @ Vector((x, y, z)) for x in (lo.x, hi.x)
                  for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
        if min(p.z for p in pontos) < topo - 1e-6 and max(p.z for p in pontos) > base + 1e-6:
            resultado.append((min(p.dot(u) for p in pontos), max(p.dot(u) for p in pontos)))
    # Query neighboring walls through the evaluated mesh. Raycasting is
    # native; the box is only an initial rejection test, never the final boundary.
    dep = context.evaluated_depsgraph_get()
    for obj in context.scene.objects:
        if not superficie(obj):
            continue
        avaliado = obj.evaluated_get(dep)
        cx = _caixa_no_referencial(avaliado, u, n, ponto)
        if cx[3] <= base + 1e-6 or cx[2] >= topo - 1e-6 or cx[5] <= 1e-5 or cx[4] >= profundidade:
            continue
        resultado.extend(_faces_no_volume(obj, avaliado, dep, s, base, topo, profundidade))
        # Horizontal axes of adjacent walls: samples at both ends
        # and the middle of the volume avoid missing an L-shaped return.
        inversa = obj.matrix_world.inverted_safe()
        direcao = (inversa.to_3x3() @ u).normalized()
        for z in (base + 1e-5, (base + topo) / 2, topo - 1e-5):
            for d in (1e-5, profundidade / 2, profundidade - 1e-5):
                inicio = ponto + u * (cx[0] - ponto.dot(u) - 0.01) + n * d
                inicio.z = z
                local = inversa @ inicio
                entradas = []
                for _ in range(32):
                    acertou, pos, normal, indice = avaliado.ray_cast(local, direcao)
                    if not acertou:
                        break
                    mundo = obj.matrix_world @ pos
                    valor = mundo.dot(u)
                    if valor > cx[1] + 1e-5:
                        break
                    entradas.append(valor)
                    local = pos + direcao * 1e-6
                for a, b in zip(entradas[::2], entradas[1::2]):
                    if b - a > 1e-6:
                        resultado.append((a, b))
    return resultado


def planejar(context, s=None):
    s = s or _sessao[0]
    if s is None or s.get('modelo') is None:
        return {'erro': "Choose a cabinet from the library"}
    if s.get('substituir'):
        return _paredes_composicao.planejar_troca(context, s)
    quantidade = s['quantidade']
    base, altura, profundidade = (s[k] / 1000.0 for k in ('instalacao', 'altura', 'profundidade'))
    if quantidade < 1 or min(altura, profundidade) < 0.02:
        return {'erro': "Invalid quantity or dimensions"}
    u = Vector(s['u'])
    faixas = faixas_livres(context, s, base, base + altura, profundidade)
    faixa = next(((a, b) for a, b in faixas if a - 1e-6 <= s['s'] <= b + 1e-6), None)
    if faixa is None:
        return {'erro': "Choose a clear opening compatible with the height"}
    inicio = faixa[0] + s['esquerda'] / 1000
    fim = faixa[1] - s['direita'] / 1000
    espaco = s['espacamento'] / 1000
    largura = (fim - inicio - (quantidade - 1) * espaco) / quantidade
    if largura < 0.02:
        return {'erro': "Not enough space for the quantity and clearances"}
    return {'largura': largura, 'altura': altura, 'profundidade': profundidade,
            'base': base, 'inicios': [inicio + i * (largura + espaco) for i in range(quantidade)],
            'faixa': faixa}


def criar_modulos(context):
    s = _sessao[0]
    if s and s.get('substituir'):
        return _paredes_composicao.substituir(context)
    if s and s['escolhendo']:
        return "Click the wall opening before creating cabinets"
    plano = planejar(context, s)
    if plano.get('erro'):
        return plano['erro']
    parede = bpy.data.objects.get(s['parede'])
    if parede is None:
        return "Wall not found"
    antes = _dados_antes()
    selecionados = [o.name for o in context.selected_objects]
    ativo = context.object.name if context.object else ''
    uid_antes = parede.get(_paredes.CHAVE_UID_PAREDE)
    try:
        criados = []
        for inicio in plano['inicios']:
            m = s['modelo']
            novos, raizes, erro = _biblioteca.inserir_preset(context, m['pasta'], m['arquivo'], m['tipo'], Vector((0, 0, 0)))
            if erro:
                raise ValueError(erro)
            conjuntos = [o for o in novos if _chapas.MARCA_CONJUNTO in o]
            if len(conjuntos) != 1:
                raise ValueError("The model no longer contains a single cabinet")
            conj = conjuntos[0]
            # The plane uses wall axes; the cabinet may be rotated.
            largura, altura, profundidade = _paredes.medidas_na_parede(
                conj, (plano['largura'], plano['altura'], plano['profundidade']))
            ocupado = _chapas._ocupado[0]
            _chapas._ocupado[0] = True
            try:
                conj.conj_largura_mm = largura * 1000
                conj.conj_altura_mm = altura * 1000
                conj.conj_profundidade_mm = profundidade * 1000
            finally:
                _chapas._ocupado[0] = ocupado
            _modulos.redimensionar_conjunto(conj)
            real = _paredes.medidas_na_parede(conj, _modulos.medir_conjunto(conj))
            if any(abs(a / 1000 - plano[k]) > 0.00005 for a, k in zip(real, ('largura', 'altura', 'profundidade'))):
                raise ValueError("The model cannot accommodate these dimensions while preserving its joints")
            u, n, ponto = (Vector(s[k]) for k in ('u', 'normal', 'ponto'))
            costas = ponto + u * (inicio + plano['largura'] / 2 - ponto.dot(u))
            costas.z = plano['base']
            _paredes.colocar_na_parede(conj, parede, costas, n)
            _paredes.associar(conj, parede, costas, n, s['face'])
            context.view_layer.update()
            criados += [o.name for o in novos]
        janela, area, regiao = _janela_da_sessao()
        if area and area.spaces.active.local_view:
            for nome in criados:
                bpy.data.objects[nome].local_view_set(area.spaces.active, True)
                if s['local_anterior']:
                    s['membros_anteriores'].append(nome)
            context.view_layer.update()
        s['modelo'] = None
        s['escolhendo'] = False
    except Exception as erro:
        _limpar_tentativa(antes)
        if uid_antes is None and _paredes.CHAVE_UID_PAREDE in parede:
            del parede[_paredes.CHAVE_UID_PAREDE]
        for nome in selecionados:
            obj = context.view_layer.objects.get(nome)
            if obj:
                obj.select_set(True)
        context.view_layer.objects.active = context.view_layer.objects.get(ativo)
        return str(erro)
    finally:
        _redesenhar()
    return None


def desenhar():
    context = bpy.context
    if not ativa(context) or context.area.as_pointer() != _sessao[0]['area']:
        return
    s = _sessao[0]
    _paredes_composicao.desenhar_guias(context)
    _paredes_composicao.desenhar(context)
    if s['modelo'] is None or _eventos._desfazendo[0]:
        return
    plano = _plano[0]
    if plano is None:
        return
    if plano.get('erro'):
        return
    n, u, ponto = (Vector(s[k]) for k in ('normal', 'u', 'ponto'))
    cor = _hud._cor_realce_hud()
    segmentos, rotulos = [], []
    for inicio in plano['inicios']:
        pontos = []
        for z in (plano['base'], plano['base'] + plano['altura']):
            for x in (inicio, inicio + plano['largura']):
                p = ponto + u * (x - ponto.dot(u)) + n * 0.002
                p.z = z
                pontos.append(view3d_utils.location_3d_to_region_2d(context.region, context.region_data, p))
        if any(p is None for p in pontos):
            continue
        for a, b in ((0, 1), (1, 3), (3, 2), (2, 0)):
            segmentos.extend((pontos[a], pontos[b]))
        rotulos.append(((pontos[2] + pontos[3]) / 2, _opcoes._texto_medida(plano['largura'] * 1000)))
    if segmentos:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        try:
            shader.bind()
            shader.uniform_float('color', cor)
            batch_for_shader(shader, 'LINES', {'pos': segmentos}).draw(shader)
            blf.size(0, 12 * context.preferences.system.ui_scale)
            blf.color(0, *cor)
            for p, texto in rotulos:
                blf.position(0, p.x, p.y + 6, 0)
                blf.draw(0, texto)
        finally:
            gpu.state.blend_set('NONE')


def _janela_da_escolha():
    e=_escolha_area[0]
    if e:
        for janela in bpy.context.window_manager.windows:
            if janela.as_pointer()==e['janela']:
                area=next((a for a in janela.screen.areas if a.as_pointer()==e['area']),None)
                regiao=next((r for r in area.regions if r.type=='WINDOW'),None) if area else None
                return janela,area,regiao
    return None,None,None


def encerrar_escolha():
    e=_escolha_area[0]
    if e is None:
        return
    _gavetas.terminar_cursor_nativo(_snap_area)
    janela,area,_regiao=_janela_da_escolha()
    _escolha_area[0]=None
    if e.get('handler') is not None:
        bpy.types.SpaceView3D.draw_handler_remove(e['handler'],'WINDOW')
    if e.get('timer') is not None:
        try:
            bpy.context.window_manager.event_timer_remove(e['timer'])
        except (ReferenceError,RuntimeError):
            pass
    if area is not None:
        area.header_text_set(None)
        area.tag_redraw()
    if janela is not None:
        janela.cursor_modal_restore()
    _paredes_selecao.esquecer()
    _redesenhar()


def preparar_escolha(context,obj):
    if _eventos._desfazendo[0]:
        return "Wait for undo/redo processing"
    if not superficie(obj) or context.mode!='OBJECT':
        return "Select the floor plan or wall mesh"
    encerrar()
    area=viewport(context)
    if area is None:
        return "No 3D viewport to choose the wall"
    regiao=next((r for r in area.regions if r.type=='WINDOW'),None)
    if regiao is None:
        return "No 3D region to choose the wall"
    _paredes_selecao.limpar_exibicoes()
    e=dict(objeto=obj.name,cena=context.scene.name,janela=context.window.as_pointer(),
           area=area.as_pointer(),regiao=regiao.as_pointer(),metodo=context.scene.get('parede_metodo_selecao','AUTO'),
           pontos=[],base=None,candidata=None,cursor=None,erro='',acao='')
    _escolha_area[0]=e
    _aviso[0]=''
    try:
        e['handler']=bpy.types.SpaceView3D.draw_handler_add(_desenhar_escolha,(),'WINDOW','POST_PIXEL')
        e['timer']=context.window_manager.event_timer_add(.1,window=context.window)
        context.window.cursor_modal_set('CROSSHAIR')
        area.header_text_set("Choose wall: click confirms | Enter accepts | Right-click/Esc cancels")
    except Exception:
        encerrar_escolha()
        raise
    _redesenhar()
    return None


def definir_metodo(context,metodo):
    if metodo not in dict(METODOS_AREA):
        raise ValueError("Invalid wall selection method")
    context.scene['parede_metodo_selecao']=metodo
    e=_escolha_area[0]
    if e:
        e.update(metodo=metodo,pontos=[],base=None,candidata=None,cursor=None,erro='')
    _redesenhar()


def raio_da_escolha(context, regiao, rv, xy):
    # The wall is already chosen: neither the ceiling nor other objects participate.
    e = _escolha_area[0]
    obj = bpy.data.objects.get(e['objeto']) if e else None
    if obj is None:
        return None
    inicio = view3d_utils.region_2d_to_origin_3d(regiao, rv, xy)
    direcao = view3d_utils.region_2d_to_vector_3d(regiao, rv, xy)
    inversa = obj.matrix_world.inverted_safe()
    dep = context.evaluated_depsgraph_get()
    avaliado = obj.evaluated_get(dep)
    culling = context.space_data.shading.show_backface_culling
    for _ in range(len(avaliado.data.polygons) + 1):
        ok, ponto, normal, face = obj.ray_cast(inversa @ inicio,
            (inversa.to_3x3() @ direcao).normalized(), depsgraph=dep)
        if not ok:
            return None
        ponto, normal = obj.matrix_world @ ponto, _paredes._normal_no_mundo(obj, normal)
        indice = avaliado.data.polygons[face].material_index
        material = obj.material_slots[indice].material if indice < len(obj.material_slots) else None
        costas_ocultas = culling or material is not None and material.use_backface_culling
        if abs(normal.z) <= .001 and (not costas_ocultas or normal.dot(direcao) < 0):
            return obj, ponto, normal, face
        # Monolithic floor plans may also contain the ceiling in the same mesh.
        inicio = ponto + direcao * 1e-5


def preparar_snap_area(context):
    e = _escolha_area[0]
    base = (e['base'] or e['candidata']) if e else None
    if base is None or e['cursor'] is None:
        return None
    if e['base'] is None:
        e['base'] = base
    _gavetas.iniciar_cursor_nativo(context, _snap_area, {}, Vector(e['cursor']),
                                  lambda obj: obj.name != e['objeto'])
    # The shared helper filters Mesh objects; curves/text can also
    # supply native snap points and must be excluded from this choice.
    for obj in context.visible_objects:
        if obj.type != 'MESH' and obj.name != e['objeto']:
            _snap_area[0]['bloqueados'].append((obj.name, obj.hide_select))
            obj.hide_select = True
        elif obj.name == e['objeto'] and obj.hide_select:
            _snap_area[0]['bloqueados'].append((obj.name, True))
            obj.hide_select = False
    n, u = _paredes.eixos_da_parede(Vector(base['normal']))
    return dict(_gavetas.PARAMETROS_CURSOR_NATIVO, snap_elements={'VERTEX'},
                orient_type='GLOBAL', orient_matrix_type='GLOBAL',
                orient_matrix=tuple(tuple(v) for v in (u, Vector((0, 0, 1)), n)),
                constraint_axis=(True, True, False))


def acompanhar_snap_area(context):
    e = _escolha_area[0]
    if _snap_area[0] is None or e is None:
        return
    if _gavetas.acompanhar_cursor_nativo(_snap_area, 'OBJECT_OT_cabinet_marcar_ponto_parede'):
        e['cursor'] = tuple(context.scene.cursor.location)
    else:
        e['acao'] = 'CANCELAR'


class OBJECT_OT_confirmar_ponto_parede(Operator):
    bl_idname = 'object.cabinet_confirmar_ponto_parede'
    bl_label = "Confirm Wall Point"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        try:
            e = _escolha_area[0]
            if e is None:
                return {'CANCELLED'}
            e['cursor'] = tuple(context.scene.cursor.location)
            acao_escolha(context, 'PONTO')
            return {'FINISHED'}
        finally:
            _gavetas.terminar_cursor_nativo(_snap_area)


class OBJECT_OT_marcar_ponto_parede(Macro):
    bl_idname = 'object.cabinet_marcar_ponto_parede'
    bl_label = "Mark Wall Point"
    bl_options = {'INTERNAL'}


def registrar_macro_area():
    OBJECT_OT_marcar_ponto_parede.define('TRANSFORM_OT_translate')
    OBJECT_OT_marcar_ponto_parede.define('OBJECT_OT_cabinet_confirmar_ponto_parede')


def atualizar_escolha(context,xy):
    e=_escolha_area[0]
    janela,area,regiao=_janela_da_escolha()
    if e is None or area is None or not(0<=xy[0]<regiao.width and 0<=xy[1]<regiao.height):
        return
    rv=area.spaces.active.region_3d
    if e['metodo']=='PONTOS' and e['base'] is not None:
        inicio=view3d_utils.region_2d_to_origin_3d(regiao,rv,xy)
        direcao=view3d_utils.region_2d_to_vector_3d(regiao,rv,xy)
        ponto=intersect_line_plane(inicio,inicio+direcao,Vector(e['base']['ponto']),Vector(e['base']['normal']),False)
        e['cursor']=tuple(ponto) if ponto is not None else None
    else:
        with context.temp_override(window=janela,area=area,region=regiao):
            acerto=raio_da_escolha(context,regiao,rv,xy)
            e['candidata']=None
            if acerto:
                obj,ponto,normal,indice=acerto
                try:
                    p,n,r=_paredes_selecao.automatica(context,obj,ponto,normal,indice)
                    e['candidata']=dict(objeto=obj.name,ponto=tuple(p),normal=tuple(n),regiao=r,matriz=_paredes._assinatura(obj.matrix_world))
                    e['cursor']=tuple(ponto)
                    e['erro']=''
                except ValueError as erro:
                    e['erro']=str(erro)
                    e['cursor']=None
    area.tag_redraw()


def acao_escolha(context,acao):
    e=_escolha_area[0]
    if not e:
        return 'CANCELLED'
    if acao=='CANCELAR':
        encerrar_escolha()
        return 'CANCELLED'
    if acao=='VOLTAR':
        if e['pontos']:
            e['pontos'].pop()
        if not e['pontos']:
            e['base']=None
        e['erro']=''
        _redesenhar()
        return 'RUNNING_MODAL'
    if acao=='PONTO' and e['metodo']=='PONTOS':
        if e['base'] is None:
            e['base']=e['candidata']
        if e['base'] is not None and e['cursor'] is not None:
            e['pontos'].append(tuple(e['cursor']))
        _redesenhar()
        return 'RUNNING_MODAL'
    if acao not in {'PONTO','CONFIRMAR'}:
        return 'RUNNING_MODAL'
    base=e['base'] if e['metodo']=='PONTOS' else e['candidata']
    if base is None:
        e['erro']="Point to the desired wall"
        return 'RUNNING_MODAL'
    obj=bpy.data.objects.get(base['objeto'])
    if obj is None or ('matriz' in base and base['matriz']!=_paredes._assinatura(obj.matrix_world)):
        e['erro']="The wall changed; remove the points and select the area again"
        return 'RUNNING_MODAL'
    try:
        regiao=(_paredes_selecao.recortar(base['regiao'],e['pontos'],Vector(base['normal']))
                if e['metodo']=='PONTOS' else base['regiao'])
    except ValueError as erro:
        e['erro']=str(erro)
        _redesenhar()
        return 'RUNNING_MODAL'
    obj=bpy.data.objects.get(base['objeto'])
    face=(Vector(base['ponto']),Vector(base['normal']),regiao)
    encerrar_escolha()
    if obj is not None and context.object!=obj:
        for selecionado in context.selected_objects:
            selecionado.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active=obj
    erro=iniciar(context,obj,face=face,recortar=True) if obj is not None else "The wall no longer exists"
    _aviso[0]=erro or ''
    return 'CANCELLED' if erro else 'FINISHED'


def _desenhar_escolha():
    e=_escolha_area[0]
    context=bpy.context
    if not e or _eventos._desfazendo[0] or context.region.as_pointer()!=e['regiao']:
        return
    rv=context.region_data
    tela=lambda p:view3d_utils.location_3d_to_region_2d(context.region,rv,Vector(p))
    realce=_hud._cor_realce_hud()
    if e['candidata'] and (e['metodo']=='AUTO' or not e['pontos']):
        _paredes._desenhar_face_alvo(e['candidata']['regiao'],tela,realce,context.region,rv)
    if e['metodo']=='PONTOS' and e['pontos']:
        pontos=list(e['pontos'])
        if e['cursor'] is not None:
            pontos.append(e['cursor'])
        segmentos=[v for a,b in zip(pontos,pontos[1:]) if tela(a) is not None and tela(b) is not None for v in (tela(a),tela(b))]
        shader=gpu.shader.from_builtin('UNIFORM_COLOR')
        try:
            gpu.state.blend_set('ALPHA');gpu.state.line_width_set(2)
            shader.bind();shader.uniform_float('color',realce)
            if segmentos:
                batch_for_shader(shader,'LINES',{'pos':segmentos}).draw(shader)
            marcas=[tela(p) for p in e['pontos'] if tela(p) is not None]
            if marcas:
                gpu.state.point_size_set(5)
                batch_for_shader(shader,'POINTS',{'pos':marcas}).draw(shader)
        finally:
            gpu.state.point_size_set(1);gpu.state.line_width_set(1);gpu.state.blend_set('NONE')


def entrar_por_vertices(context,obj,somente_faces=False,aceitar_ilhas=False):
    try:
        face=_paredes_selecao.dos_vertices(context,obj,somente_faces=somente_faces,aceitar_ilhas=aceitar_ilhas)
    except ValueError as erro:
        return str(erro)
    bpy.ops.object.mode_set(mode='OBJECT')
    return iniciar(context,obj,face=face,recortar=True)


class OBJECT_OT_editar_parede(Operator):
    bl_idname = 'object.cabinet_editar_parede'
    bl_label = "Edit wall"
    objeto: StringProperty(options={'SKIP_SAVE'})

    def invoke(self,context,event):
        obj=bpy.data.objects.get(self.objeto) if self.objeto else context.object
        if not _paredes.alvenaria_definida(obj):
            self.report({'WARNING'},"Select the mesh and use Define Masonry")
            return {'CANCELLED'}
        if _ambientes._retorno[0] and _ambientes._retorno[0]['objeto']==obj.name:
            erro=_ambientes.retomar_parede(context)
            if erro:self.report({'WARNING'},erro)
            return {'CANCELLED'} if erro else {'FINISHED'}
        if context.mode=='EDIT_MESH':
            erro=entrar_por_vertices(context,obj)
            _aviso[0]=erro or ''
            if erro:self.report({'WARNING'},erro)
            return {'CANCELLED'} if erro else {'FINISHED'}
        try:self.editor_faces=_ambientes.preparar_selecao(context,obj,parede_2d=True)
        except ValueError as erro:
            _aviso[0]=str(erro);self.report({'WARNING'},str(erro))
            return {'CANCELLED'}
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self,context,event):
        if getattr(self,'editor_faces',None):
            try:return _ambientes.evento_selecao(context,event,self.editor_faces)
            except Exception:
                _ambientes.encerrar_selecao();raise
        try:
            e=_escolha_area[0]
            janela,area,regiao=_janela_da_escolha()
            if e is None:return {'CANCELLED'}
            if (area is None or context.scene.name!=e['cena'] or _eventos._desfazendo[0]
                    or bpy.data.objects.get(e['objeto']) is None):
                encerrar_escolha();return {'CANCELLED'}
            if event.type == 'TIMER':
                acompanhar_snap_area(context)
            acao=e.pop('acao','')
            if acao:return {acao_escolha(context,acao)}
            if event.value=='PRESS':
                if event.type in {'ESC','RIGHTMOUSE'}:return {acao_escolha(context,'CANCELAR')}
                if event.type=='BACK_SPACE':return {acao_escolha(context,'VOLTAR')}
                if event.type in {'RET','NUMPAD_ENTER'}:return {acao_escolha(context,'CONFIRMAR')}
            xy=(event.mouse_x-regiao.x,event.mouse_y-regiao.y)
            dentro=0<=xy[0]<regiao.width and 0<=xy[1]<regiao.height
            if event.type=='MOUSEMOVE' and dentro:
                atualizar_escolha(context,xy)
            if event.type=='LEFTMOUSE' and event.value=='PRESS' and dentro:
                atualizar_escolha(context,xy)
                if e['metodo'] == 'PONTOS':
                    with context.temp_override(window=janela, area=area, region=regiao):
                        parametros = preparar_snap_area(context)
                        if parametros is not None:
                            bpy.ops.object.cabinet_marcar_ponto_parede('INVOKE_DEFAULT',
                                TRANSFORM_OT_translate=parametros)
                    return {'RUNNING_MODAL'}
                return {acao_escolha(context,'PONTO')}
            if not dentro or event.type in {'MIDDLEMOUSE','WHEELUPMOUSE','WHEELDOWNMOUSE','NDOF_MOTION'} or navegacao_de_saida(context,event):
                return {'PASS_THROUGH'}
            return {'RUNNING_MODAL'}
        except Exception:
            encerrar_escolha()
            raise

    def cancel(self,context):
        if getattr(self,'editor_faces',None):_ambientes.encerrar_selecao()
        encerrar_escolha()

    def execute(self, context):
        obj = bpy.data.objects.get(self.objeto) if self.objeto else context.object
        erro = (_ambientes.retomar_parede(context) if _ambientes._retorno[0] and obj is not None
                and _ambientes._retorno[0]['objeto']==obj.name else
                entrar_por_vertices(context,obj) if context.mode=='EDIT_MESH' else iniciar(context, obj))
        _aviso[0] = erro or ''
        if erro:
            self.report({'WARNING'}, erro)
        return {'CANCELLED'} if erro else {'FINISHED'}


class OBJECT_OT_sair_parede(Operator):
    bl_idname = 'object.cabinet_sair_parede'
    bl_label = "Exit wall editing"

    def execute(self, context):
        encerrar()
        return {'FINISHED'}


class AcaoDaArea:
    @classmethod
    def poll(cls,context):
        return _escolha_area[0] is not None

    def execute(self,context):
        if _escolha_area[0] is None:
            return {'CANCELLED'}
        _escolha_area[0]['acao']=self.ACAO
        _redesenhar()
        return {'FINISHED'}


class OBJECT_OT_confirmar_area_parede(AcaoDaArea,Operator):
    bl_idname='object.cabinet_area_parede_confirmar'
    bl_label="Confirm wall area"
    ACAO='CONFIRMAR'


class OBJECT_OT_voltar_area_parede(AcaoDaArea,Operator):
    bl_idname='object.cabinet_area_parede_voltar'
    bl_label="Remove last point"
    ACAO='VOLTAR'


class OBJECT_OT_cancelar_area_parede(AcaoDaArea,Operator):
    bl_idname='object.cabinet_area_parede_cancelar'
    bl_label="Cancel wall selection"
    ACAO='CANCELAR'


class OBJECT_OT_escolher_vao_parede(Operator):
    bl_idname = 'object.cabinet_escolher_vao_parede'
    bl_label = "Choose opening on wall"

    def execute(self, context):
        if not ativa(context):
            return {'CANCELLED'}
        _sessao[0]['escolhendo'] = True
        return {'FINISHED'}


class OBJECT_OT_cancelar_previa_parede(Operator):
    bl_idname = 'object.cabinet_cancelar_previa_parede'
    bl_label = "Cancel preview"

    def execute(self, context):
        if ativa(context):
            _sessao[0]['modelo'] = None
            _sessao[0]['substituir'] = ''
            _sessao[0]['escolhendo'] = False
            _redesenhar()
        return {'FINISHED'}


class OBJECT_OT_distribuir_parede(Operator):
    bl_idname = 'object.cabinet_distribuir_parede'
    bl_label = "Create cabinets on wall"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not ativa(context):
            return {'CANCELLED'}
        erro = criar_modulos(context)
        if erro:
            self.report({'WARNING'}, erro)
            return {'CANCELLED'}
        return {'FINISHED'}


class OBJECT_OT_observar_parede(Operator):
    bl_idname = 'object.cabinet_observar_parede'
    bl_label = "Observe wall navigation"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        self.sessao = _sessao[0]['id']
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        try:
            return self._modal(context, event)
        except Exception:
            encerrar()
            raise

    def cancel(self, context):
        if ativa() and _sessao[0]['id'] == self.sessao:
            encerrar()

    def _modal(self, context, event):
        if not ativa() or _sessao[0]['id'] != self.sessao:
            return {'FINISHED'}
        if _eventos._desfazendo[0]:
            return {'PASS_THROUGH'}
        if _paredes_composicao._edicao[0] is not None:
            return {'PASS_THROUGH'}
        janela, area, regiao = _janela_da_sessao()
        if area is None:
            encerrar()
            return {'FINISHED'}
        na_vista = (regiao.x <= event.mouse_x < regiao.x + regiao.width
                    and regiao.y <= event.mouse_y < regiao.y + regiao.height)
        if na_vista:
            with context.temp_override(window=janela, area=area, region=regiao):
                if navegacao_de_saida(context, event):
                    encerrar(perspectiva=True)
                    return {'PASS_THROUGH'}
                s = _sessao[0]
                if s.get('categorias'):
                    return {'PASS_THROUGH'}
                if not s['escolhendo'] and event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                    cota = _paredes_composicao.cota_sob(event.mouse_x - regiao.x, event.mouse_y - regiao.y)
                    if cota:
                        bpy.ops.object.cabinet_editar_cota_parede('INVOKE_DEFAULT',
                            objeto=cota[4], propriedade=cota[5])
                        return {'RUNNING_MODAL'}
                if event.type == 'MOUSEMOVE' and not s['escolhendo']:
                    # The corner circle near the mouse (corner snapping).
                    _paredes_composicao.atualizar_quina_hover(event, regiao, context.region_data)
                    _paredes_composicao.atualizar_guia_hover(event.mouse_x - regiao.x,
                                                             event.mouse_y - regiao.y)
                if (not s['escolhendo'] and event.type == 'LEFTMOUSE' and event.value == 'PRESS'
                        and _hud._acertar_hud(context, (event.mouse_x - regiao.x,
                                                        event.mouse_y - regiao.y))):
                    # Face point or corner arrow: the HUD gizmo edits geometry.
                    return {'PASS_THROUGH'}
                modulo = None if s['escolhendo'] else modulo_para_mover(context, event, regiao)
                if modulo is not None:
                    arrastar = event.type == 'LEFTMOUSE'
                    bpy.ops.object.cabinet_mover_na_parede('INVOKE_DEFAULT', modulo=modulo,
                                                           arrastar=arrastar)
                    # Pass the click through to selection; G is handled entirely here.
                    return {'PASS_THROUGH'} if arrastar else {'RUNNING_MODAL'}
                if s['escolhendo']:
                    if event.type == 'ESC' and event.value == 'PRESS':
                        s['modelo'] = None
                        s['escolhendo'] = False
                        _redesenhar()
                        return {'RUNNING_MODAL'}
                    if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                        xy = (event.mouse_x - regiao.x, event.mouse_y - regiao.y)
                        origem = view3d_utils.region_2d_to_origin_3d(regiao, context.region_data, xy)
                        direcao = view3d_utils.region_2d_to_vector_3d(regiao, context.region_data, xy)
                        ponto = intersect_line_plane(origem, origem + direcao,
                                      Vector(s['ponto']), Vector(s['normal']))
                        if ponto is not None:
                            s['s'] = ponto.dot(Vector(s['u']))
                            s['escolhendo'] = False
                            _plano[0] = None
                            _redesenhar()
                        return {'RUNNING_MODAL'}
                elif s['modelo'] is not None and event.type == 'ESC' and event.value == 'PRESS':
                    s['modelo'] = None
                    _plano[0] = None
                    _redesenhar()
                    return {'RUNNING_MODAL'}
        else:
            if _paredes_composicao._quina_hover[0] is not None:
                _paredes_composicao._quina_hover[0] = None      # The mouse left the view.
                _redesenhar()
            _paredes_composicao.atualizar_guia_hover(None, None)
        verificar(atualizar_previa=False)
        return {'PASS_THROUGH'}


class VIEW3D_MT_parede_cabinet(Menu):
    bl_idname = 'VIEW3D_MT_parede_cabinet'
    bl_label = 'Archy Builder'

    def draw(self, context):
        op = self.layout.operator('object.cabinet_editar_parede', text="Edit wall")
        op.objeto = _alvo_contexto[0] or ''


def menu_contexto(self, context):
    alvo = _alvo_contexto[0]
    obj = context.edit_object if context.mode=='EDIT_MESH' else bpy.data.objects.get(alvo) if alvo is not None else context.object
    if superficie(obj) and context.mode in {'OBJECT','EDIT_MESH'}:
        self.layout.separator()
        self.layout.menu('VIEW3D_MT_parede_cabinet')
