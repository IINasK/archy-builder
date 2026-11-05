"""Door selected in the viewport: corners (Alt) and opening slider."""

import bpy, gpu, blf
from gpu_extras.batch import batch_for_shader
from bpy.props import (FloatProperty, BoolProperty, StringProperty,
                       IntProperty, FloatVectorProperty)
from mathutils import Matrix, Vector
from bpy.types import Gizmo, GizmoGroup, Operator, Macro

# Used only at RUNTIME (circular imports): __init__ binds these aliases after loading
# all modules (`_ligar_modulos`).
_chapas = None
_eventos = None
_portas = None
_ferragens = None
_puxadores = None
_hud = None
_solda = None
_perguntas = None
_frentes = None
_gavetas = None

# ------------------------------------------ the four door corners
# User request: a single click on the door shows the wizard lines (orange = overlay,
# white = opening). With Alt, the four dots become handles: dragging a corner to another
# vertex recreates the door as if the four clicks had been placed there (automatic
# overlay and hinge). Corners are not stored: they are derived from the door (opening +
# overlay on each side), so they follow cabinet changes.
_arraste_canto_porta = [None]    # Corner drag state.


def _porta_veio_do_modulo(grupo):
    """The door is selected only because its CABINET is selected (panel click). Draw
    none of the door controls: hinges, opening lines, diagonal, corners or sliders
    (user request for a cleaner view). The cabinet HUD already shows its outline."""
    modulo = grupo.parent
    while modulo is not None and _chapas.MARCA_CONJUNTO not in modulo:
        modulo = modulo.parent
    return modulo is not None and modulo.select_get()


def _portas_com_cantos(context):
    """WHOLE doors selected independently (single click, not a leaf), rather than as
    part of a cabinet selection."""
    return [o for o in getattr(context, 'selected_objects', ()) or ()
            if _chapas.MARCA_PORTAS in o and o.get('porta_parametros')
            and o.get('porta_vao_largura_mm') is not None
            and not _porta_veio_do_modulo(o)]


def _folhas_com_contorno(context):
    """Leaves selected WITHOUT the whole door (double click): native outlines are
    disabled, so without the add-on's white outline nothing appeared selected (user
    request)."""
    selecionados = getattr(context, 'selected_objects', ()) or ()
    saida = []
    for o in selecionados:
        grupo = (_portas._grupo_portas(o) if _chapas.MARCA_FOLHA in o
                 else None)
        if (grupo is not None and not grupo.select_get()
                and not _porta_veio_do_modulo(grupo)):
            saida.append(o)
    return saida


def _caixa_da_folha(folha):
    """Eight leaf corners (WORLD space), in `ARESTAS_CAIXA` order."""
    l, a, e, _centro = _ferragens._dados_da_folha(folha)
    meia = Vector((l, a, e)) / 2000.0
    return [folha.matrix_world @ Vector((meia.x * sx, meia.y * sy, meia.z * sz))
            for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]


def _referencia_tem_perfil(ref):
    """A flat box preserves the wizard's opening/overlays, not its vertices."""
    if 'plana_retangular' in ref:
        return not ref['plana_retangular']
    for base, topo in (('frente', 'cima_frente'), ('tras', 'cima_tras')):
        baixo, cima = ref.get(base, ()), ref.get(topo, ())
        if len(baixo) > 2 or len(cima) > 2:
            return True
        if len(baixo) < 2 or len(cima) < 2:
            continue
        origem = Vector(baixo[0])
        normal = (Vector(baixo[-1])-origem).cross(Vector(cima[0])-origem)
        if normal.length_squared <= 1e-20:
            continue
        normal.normalize()
        if any(abs((Vector(p)-origem).dot(normal)) > 1e-7
               for p in cima):
            return True
    return False


def _perfil_da_folha(folha, fechada=False, interno=False):
    """Vertices already referenced during assembly; no mesh searches during redraw."""
    ref = _frentes.referencia(folha) if _frentes is not None else None
    if ref is not None:
        return (_frentes.perfil(folha, fechada=fechada, interno=interno)
                if _referencia_tem_perfil(ref) else None)
    pontos = folha.get('porta_linha_frente')
    if not pontos or len(pontos) <= 2:
        return None
    matriz = (_ferragens._matriz_fechada(folha) if fechada else folha.matrix_world)
    hy = folha.chapa_comprimento_mm / 2000.0
    baixo, cima = [], []
    for p in pontos:
        p = Vector(p)
        if interno:
            p.z -= folha.chapa_espessura_mm / 1000.0
        a, b = p.copy(), p.copy()
        a.y, b.y = -hy, hy
        baixo.append(matriz @ a)
        cima.append(matriz @ b)
    return baixo, cima


def _contorno_da_folha(folha):
    if _frentes is not None:
        contorno = _frentes.contorno(folha)
        if contorno is not None:
            return contorno
    perfil = _perfil_da_folha(folha)
    if perfil is None:
        return _caixa_da_folha(folha), _portas.ARESTAS_CAIXA
    baixo, cima = perfil
    m = len(baixo)
    arestas = [(i,i+1) for i in range(m-1)]
    arestas += [(i+m,i+m+1) for i in range(m-1)]
    arestas += [(0,m),(m-1,2*m-1)]
    for i in range(1,m-1):
        # Smooth curves get no stripes; the folded corner remains legible.
        if (baixo[i]-baixo[i-1]).normalized().dot((baixo[i+1]-baixo[i]).normalized()) < .866:
            arestas.append((i,i+m))
    return baixo+cima, arestas


def _cantos_da_porta(grupo):
    """The four wizard points in WORLD space, in click order: door corner and opening
    corner at the upper left, then opening corner and door corner at the lower right
    (the user's drawing)."""
    folhas = _portas._folhas_portas(grupo)
    if len(folhas) == 1:
        fora = _perfil_da_folha(folhas[0], fechada=True)
        dentro = _perfil_da_folha(folhas[0], fechada=True, interno=True)
        if fora and dentro:
            return [fora[1][0], dentro[1][0], dentro[0][-1], fora[0][-1]]
    p = grupo['porta_parametros']
    L = float(grupo['porta_vao_largura_mm'])
    A = float(grupo['porta_vao_altura_mm'])
    # The CLICKED point (mid-thickness), not the leaf edge: half-overlay panels set the
    # clearance back, and an Alt-dragged corner must recognize half-overlay again.
    padrao = (0.0 if p.get('abertura') == 'CORRER' else
              {'RETA': 1.0, 'CURVA': 0.5}.get(p.get('dobradica'), 0.0))
    lateral = float(p['lateral_mm'])
    cob = [float(p[k]) * lateral if k in p else padrao * lateral
           for k in _portas.COBERTURAS_LADOS]
    m = grupo.matrix_world
    return [m @ (Vector((x, y, 0.0)) / 1000.0) for x, y in (
        (-cob[0], A + cob[3]), (0.0, A), (L, 0.0), (L + cob[1], -cob[2]))]


# Alt drags only the wizard's TWO clicked door corners (user request): upper left and
# lower right. The opening corners are only drawn.
CANTOS_DO_GESTO = (0, 3)


def _coberturas_da_porta(grupo):
    p = grupo.get('porta_parametros') or {}
    return {k: float(p[k]) for k in _portas.COBERTURAS_LADOS if k in p}


def _canto_porta_sob_mouse(context, posicao):
    """(group, index) of the corner dot under the mouse (only with Alt)."""
    if not _solda._correntes_visiveis():
        return None, None
    raio = _solda.RAIO_BOLINHA_PX * max(1.0, context.preferences.system.ui_scale)
    mouse = Vector(posicao)
    melhor = None
    for grupo in _portas_com_cantos(context):
        cantos = _cantos_da_porta(grupo)
        for i in CANTOS_DO_GESTO:
            p = _hud._projetar_hud(context, cantos[i])
            if p is None:
                continue
            d = (p - mouse).length
            if d <= raio and (melhor is None or d < melhor[0]):
                melhor = (d, grupo, i)
    return (melhor[1], melhor[2]) if melhor else (None, None)


COR_LINHAS_VAO = (1.0, 0.85, 0.1, 1.0)      # Yellow: the opening (user request).


def _desenho_da_porta(grupo):
    """Selected door display in WORLD space: each leaf's box and the opening rectangle
    (inner panel faces). Hardware is excluded: it appears only during creation or
    when SELECTED (`_arame_ferragens`). Rebuilt from the door on every draw so it
    follows the cabinet."""
    p = dict(grupo['porta_parametros'])
    L = float(grupo['porta_vao_largura_mm'])
    A = float(grupo['porta_vao_altura_mm'])
    m = grupo.matrix_world
    mundo = lambda v: m @ (Vector(v) / 1000.0)
    desenho = {'folhas': [],
               'vao': [mundo((x, y, 0.0)) for x, y in
                       ((0, 0), (L, 0), (L, A), (0, A))]}
    try:
        folhas = _portas._calcular_folhas_portas(L, A, p)
    except (ValueError, KeyError, TypeError):
        return desenho
    objetos = _portas._folhas_portas(grupo)
    if len(objetos) == 1 and _perfil_da_folha(objetos[0]) is not None:
        folha = objetos[0]
        baixo, cima = _perfil_da_folha(folha, fechada=True, interno=True)
        desenho['vao'] = baixo+list(reversed(cima))
        pontos, arestas = _contorno_da_folha(folha)
        desenho['folhas'] = [pontos]
        desenho['arestas_folhas'] = [arestas]
        desenho['perfil'] = True
        return desenho
    for i, (l, alt, e, centro) in enumerate(folhas):
        if i < len(objetos):
            pontos, arestas = _contorno_da_folha(objetos[i])
            desenho['folhas'].append(pontos)
            desenho.setdefault('arestas_folhas', []).append(arestas)
            continue
        meia = Vector((l, alt, e)) / 2000.0
        # Leaf not created yet: use the calculated box.
        matriz = m @ Matrix.Translation(Vector(centro) / 1000.0)
        desenho['folhas'].append([matriz @ Vector((meia.x * sx, meia.y * sy,
                                                   meia.z * sz))
                                  for sx in (-1, 1) for sy in (-1, 1)
                                  for sz in (-1, 1)])
        desenho.setdefault('arestas_folhas', []).append(_portas.ARESTAS_CAIXA)
    return desenho


def _desenhar_cantos_porta(context):
    """Selected door (user screenshot): white leaf outlines, yellow inner opening
    lines, the diagonal between the two clicks and, with Alt (or during a drag), the
    two white dots. No hinges (user request): show those only during creation or
    when selected."""
    portas = _portas_com_cantos(context)
    folhas = _folhas_com_contorno(context)
    if not (portas or folhas):
        return
    estado = _arraste_canto_porta[0]
    escala = max(1.0, context.preferences.system.ui_scale)
    realce = _hud._cor_realce_hud()
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        for folha in folhas:
            # Leaf only: no opening, guide lines or corners (those belong to the whole
            # door).
            pontos, arestas = _contorno_da_folha(folha)
            tela = [_hud._projetar_hud(context, v) for v in pontos]
            if any(v is None for v in tela):
                continue
            shader.uniform_float('color', _portas.COR_FIO_VAO)
            for i, j in arestas:
                batch_for_shader(shader, 'TRIS', {'pos': _puxadores._quad_2d(
                    tela[i], tela[j], 1.4 * escala)}).draw(shader)
        for grupo in portas:
            desenho = _desenho_da_porta(grupo)
            contornos = [(caixa, desenho.get('arestas_folhas',
                         [_portas.ARESTAS_CAIXA]*len(desenho['folhas']))[i], _portas.COR_FIO_VAO)
                         for i,caixa in enumerate(desenho['folhas'])]
            n = len(desenho['vao'])
            contornos.append((desenho['vao'], [(i,(i+1)%n) for i in range(n)],
                              COR_LINHAS_VAO))
            for pontos, arestas, cor in contornos:
                tela = [_hud._projetar_hud(context, v) for v in pontos]
                if any(v is None for v in tela):
                    continue
                shader.uniform_float('color', cor)
                for i, j in arestas:
                    batch_for_shader(shader, 'TRIS', {'pos': _puxadores._quad_2d(
                        tela[i], tela[j], 1.4 * escala)}).draw(shader)
            arrastando = estado is not None and estado['grupo'] == grupo.name
            if arrastando:
                # The dragged corner is the native snap cursor.
                pontos = list(estado['antigos'])
                pontos[estado['indice']] = estado['ponto']
            else:
                pontos = _cantos_da_porta(grupo)
            tela = [_hud._projetar_hud(context, pontos[i]) for i in CANTOS_DO_GESTO]
            if any(p is None for p in tela):
                continue
            if not desenho.get('perfil'):
                # The wizard diagonal (it used to pass through curved doors).
                shader.uniform_float('color', _portas.COR_FIO_VAO)
                batch_for_shader(shader, 'TRIS', {'pos': _puxadores._quad_2d(
                    tela[0], tela[1], 2.0 * escala)}).draw(shader)
            if not (arrastando or _solda._correntes_visiveis()):
                continue
            for i, p in zip(CANTOS_DO_GESTO, tela):
                aceso = arrastando and i == estado['indice']
                if aceso:
                    _hud._bolinha_2d(shader, p, 8 * escala, realce)
                _hud._bolinha_2d(shader, p, (6 if aceso else 5) * escala,
                            (1.0, 1.0, 1.0, 1.0))
    finally:
        gpu.state.blend_set('NONE')


def _dentro_da_porta(obj, grupo):
    while obj is not None:
        if obj == grupo:
            return True
        obj = obj.parent
    return False


def _mover_cantos_porta(context, grupo, pontos, objetos=(None, None)):
    """Rebuild the door from the two WORLD clicks and their panels, as in the wizard:
    each side's overlay comes from where its point lands (outer corner = straight
    hinge, mid-thickness = half-overlay hinge, inner corner = inset hinge)."""
    modulo = bpy.data.objects.get(grupo.get(_portas.CHAVE_MODULO_PORTA, ''))
    if modulo is not None and _chapas.MARCA_CONJUNTO not in modulo:
        modulo = None
    referencia = (modulo.matrix_world.to_quaternion().to_matrix()
                  if modulo is not None else Matrix.Identity(3))
    valores = tuple(v for linha in referencia for v in linha)
    pai = modulo if modulo is not None else grupo.parent
    folha = (_portas._folhas_portas(grupo) or [None])[0]
    resultado = bpy.ops.object.cabinet_portas(
        'EXEC_DEFAULT', capturado=True, grupo_alvo=grupo.name,
        ponto_a=pontos[0], ponto_b=pontos[1], quatro_pontos=True,
        porta_a=pontos[0], porta_b=pontos[1],
        objeto_a_nome=objetos[0].name if objetos[0] is not None else '',
        objeto_b_nome=objetos[1].name if objetos[1] is not None else '',
        referencia=valores, referencia_ativa=valores,
        pai_nome=pai.name if pai is not None else '',
        modulo_nome=modulo.name if modulo is not None else '',
        orientacao='AUTO', frente=grupo.get('porta_frente', 'NEG_Y'))
    # Creation leaves the CABINET active; here the door stays selected so the user can
    # continue adjusting it.
    folha = (_portas._folhas_portas(grupo) or [folha])[0]
    if folha is not None:
        _hud._selecionar_porta_hud(context, folha, 'PORTA')
    return resultado


def _aplicar_cantos_porta(context, grupo, pontos, objetos, antigos,
                         objetos_antigos=(None, None)):
    """Drag released: rebuild the door and ask if the overlay is nonstandard (viewport
    popup). Answering No restores the previous two clicks."""
    resultado = _mover_cantos_porta(context, grupo, pontos, objetos)
    if 'FINISHED' not in resultado:
        return resultado
    if _portas._lados_fora_do_padrao(_coberturas_da_porta(grupo)):
        planos = tuple(v for p in antigos for v in p)
        nomes = [o.name if o is not None else '' for o in objetos_antigos]
        _perguntas._perguntar(context, "Are the dimensions correct?", [
            ("Yes", 'CHECKMARK', 'object.cabinet_cantos_porta',
             {'grupo': grupo.name, 'manter': True}),
            ("No", 'X', 'object.cabinet_cantos_porta',
             {'grupo': grupo.name, 'pontos': planos,
              'objeto_a': nomes[0], 'objeto_b': nomes[1]})], na_gaveta=False)
    return resultado


class OBJECT_OT_cantos_porta(Operator):
    """Rebuild the door from the two clicks (answer to 'Are the dimensions correct?')."""
    bl_idname = 'object.cabinet_cantos_porta'
    bl_label = "Door Corners"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    grupo: StringProperty(options={'SKIP_SAVE'})
    pontos: FloatVectorProperty(size=6, options={'SKIP_SAVE'})
    # The panel for each click: without it, mid-thickness cannot select a half-overlay
    # hinge.
    objeto_a: StringProperty(options={'SKIP_SAVE'})
    objeto_b: StringProperty(options={'SKIP_SAVE'})
    manter: BoolProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        grupo = bpy.data.objects.get(self.grupo)
        if grupo is None or _chapas.MARCA_PORTAS not in grupo:
            return {'CANCELLED'}
        if self.manter:
            return {'FINISHED'}
        v = list(self.pontos)
        pontos = [Vector(v[0:3]), Vector(v[3:6])]
        objetos = [bpy.data.objects.get(n) if n else None
                   for n in (self.objeto_a, self.objeto_b)]
        return _mover_cantos_porta(context, grupo, pontos, objetos)


def _preparar_canto_nativo(context, grupo, indice):
    """The cursor is the temporary corner; NATIVE snapping finds the destination
    (`_gavetas.iniciar_cursor_nativo`). Previously every visible mesh was read
    (to_mesh) on click and every vertex projected in Python on each movement,
    causing seconds of freezing."""
    antigos = _cantos_da_porta(grupo)
    # The door must not snap to itself; hardware/handles would only burden the BVH.
    _gavetas.iniciar_cursor_nativo(
        context, _arraste_canto_porta,
        {'regiao': context.region.as_pointer(), 'grupo': grupo.name,
         'indice': indice, 'antigos': list(antigos)},
        antigos[indice],
        lambda o: (_dentro_da_porta(o, grupo) or _ferragens.CHAVE_FERRAGEM in o
                   or _gavetas.acessorio_fora_do_snap(o)))
    return dict(_gavetas.PARAMETROS_CURSOR_NATIVO, snap_elements={'VERTEX'})


def _terminar_canto_nativo(remover_timer=True):
    estado = _gavetas.terminar_cursor_nativo(_arraste_canto_porta)
    if remover_timer and bpy.app.timers.is_registered(_acompanhar_canto_nativo):
        bpy.app.timers.unregister(_acompanhar_canto_nativo)
    return estado


def _acompanhar_canto_nativo():
    vivo = _gavetas.acompanhar_cursor_nativo(_arraste_canto_porta,
                                             'OBJECT_OT_cabinet_mover_canto_porta')
    return 1.0 / 60.0 if vivo else None


class OBJECT_OT_confirmar_canto_porta(Operator):
    bl_idname = 'object.cabinet_confirmar_canto_porta'
    bl_label = "Confirm Door Corner"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        estado = _arraste_canto_porta[0]
        if not estado:
            return {'CANCELLED'}
        ponto = context.scene.cursor.location.copy()
        estado = _terminar_canto_nativo()
        grupo = bpy.data.objects.get(estado['grupo'])
        indice, antigos = estado['indice'], estado['antigos']
        if grupo is None or (ponto - antigos[indice]).length < 1e-6:
            return {'CANCELLED'}
        antes = [antigos[i] for i in CANTOS_DO_GESTO]
        pontos = list(antes)
        pontos[CANTOS_DO_GESTO.index(indice)] = ponto
        resultado = _aplicar_cantos_porta(
            context, grupo, pontos, [_chapa_do_ponto(context, grupo, p) for p in pontos],
            antes, [_chapa_do_ponto(context, grupo, p) for p in antes])
        return {'FINISHED'} if 'FINISHED' in resultado else {'CANCELLED'}


def _chapa_do_ponto(context, grupo, ponto):
    """The clicked panel: native ray cast/BVH, only on release. Both panels matter:
    mid-thickness on either side can only be determined from its panel."""
    nome = (_gavetas._objeto_do_ponto_criacao(context, ponto)
            if context.area is not None and context.area.type == 'VIEW_3D' else None)
    obj = bpy.data.objects.get(nome or '')
    return None if obj is None or _dentro_da_porta(obj, grupo) else obj


class OBJECT_OT_mover_canto_porta(Macro):
    bl_idname = 'object.cabinet_mover_canto_porta'
    bl_label = "Move Door Corner"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}


def registrar_macro_canto():
    OBJECT_OT_mover_canto_porta.define('TRANSFORM_OT_translate')
    OBJECT_OT_mover_canto_porta.define('OBJECT_OT_cabinet_confirmar_canto_porta')


class OBJECT_OT_arrastar_canto_porta(Operator):
    """Drag either door corner (Alt) to another vertex to rebuild the door from it."""
    bl_idname = 'object.cabinet_arrastar_canto_porta'
    bl_label = "Move Door Corner"
    bl_options = {'INTERNAL'}

    grupo: StringProperty(options={'SKIP_SAVE'})
    indice: IntProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        grupo = bpy.data.objects.get(self.grupo)
        if (grupo is None or _chapas.MARCA_PORTAS not in grupo
                or self.indice not in CANTOS_DO_GESTO or context.region is None):
            return {'CANCELLED'}
        parametros = _preparar_canto_nativo(context, grupo, self.indice)
        try:
            resultado = bpy.ops.object.cabinet_mover_canto_porta(
                'INVOKE_DEFAULT', TRANSFORM_OT_translate=parametros)
        except Exception:
            _terminar_canto_nativo()
            raise
        if 'RUNNING_MODAL' not in resultado:
            _terminar_canto_nativo()
            return {'CANCELLED'}
        bpy.app.timers.register(_acompanhar_canto_nativo, first_interval=0.0)
        return {'FINISHED'}


# ------------------------------------------ opening slider (Epic 4)
# One per leaf, only when the door (or leaf) is selected: at the BASE of the CLOSED
# leaf, slightly in front (stationary while it opens, so it stays under the mouse),
# above everything else (X-ray). Drag right to open, left to close, regardless of hinge
# side. Thick (user request) and inset from the leaf ends: double-door sliders never
# touch in the middle; a gap remains.
SLIDER_FRENTE_MM = 30.0
SLIDER_RECUO_MM = 40.0           # Minimum inset from each leaf end.
SLIDER_RECUO_FRACAO = 0.12       # ...or this fraction of the width.
SLIDER_DEGRAU_MM = 40.0          # Sliding doors: vertically stacked sliders, one per
                                 # track.
# WORLD dimensions in MM (user request): at a distance, the slider shrinks with the
# door; close up, scale is capped at 2x. Calibrated in a normal cabinet view (~1 px/mm)
# to match the user-approved drawing.
SLIDER_ESPESSURA_MM = 13.0       # Track height.
SLIDER_BOTAO_MM = 12.0           # Dot radius = click reach.
SLIDER_TEXTO_MM = 13.0           # Value text height.
SLIDER_PX_POR_MM_MAX = 2.0       # Scale cap (per ui_scale).
SLIDER_TEXTO_MIN_PX = 7.0        # Below this size the value is unreadable: hide it.
SIMBOLO_GRAU = chr(0xB0)         # ASCII-only code.
_arraste_slider_porta = [None]   # Name of the leaf being dragged.
_slider_hover = [None]           # Name of the leaf whose dot is under the mouse.


def _folhas_com_slider(context):
    folhas = []
    for o in getattr(context, 'selected_objects', ()) or ():
        if _chapas.MARCA_PORTAS in o and o.get('porta_parametros'):
            grupo, candidatas = o, _portas._folhas_portas(o)
        elif _chapas.MARCA_FOLHA in o and _portas._grupo_portas(o) is not None:
            grupo, candidatas = _portas._grupo_portas(o), [o]
        else:
            continue
        if _porta_veio_do_modulo(grupo):
            continue        # Cabinet selected: no sliders.
        # Use .get: the leaf branch does not guarantee parameters (legacy group), and a
        # KeyError here used to reach GizmoGroup.poll.
        if (grupo.get('porta_parametros') or {}).get('abertura') == 'ZIGZAG':
            candidatas = _portas._folhas_portas(grupo)[-1:]
        folhas += [f for f in candidatas if f not in folhas]
    return folhas


def _slider_no_mundo(folha):
    """Slider endpoints in WORLD space: base of the closed leaf, slightly in front,
    inset from the corners (the gap between double-door sliders)."""
    l, a, e, centro = _ferragens._dados_da_folha(folha)
    fechada = _ferragens._matriz_fechada(folha)
    curso = _curso_do_slider(folha, l, centro)
    if curso is not None:
        # Sliding doors: from the closed leaf center to the open center (the dot moves
        # beneath the leaf), one level higher per track so sliders on multi-leaf doors
        # do not overlap.
        y = -a / 2.0 + int(folha.get('porta_indice', 0)) * SLIDER_DEGRAU_MM
        return [fechada @ (Vector((dx, y, e / 2.0 + SLIDER_FRENTE_MM)) / 1000.0)
                for dx in curso]
    recuo = min(max(SLIDER_RECUO_MM, SLIDER_RECUO_FRACAO * l), 0.3 * l)
    return [fechada @ (Vector((sx * (l / 2.0 - recuo), -a / 2.0,
                               e / 2.0 + SLIDER_FRENTE_MM)) / 1000.0)
            for sx in (-1, 1)]


def _curso_do_slider(folha, l, centro):
    """(0, displacement) from closed to open for a SLIDING leaf (mm along the opening's
    X), or None for other leaf types."""
    grupo = _portas._grupo_portas(folha)
    p = (grupo.get('porta_parametros') or {}) if grupo is not None else {}
    if p.get('abertura') != 'CORRER':
        return None
    fechado, destino = _ferragens._curso_correr(
        p, float(grupo.get('porta_vao_largura_mm', 0.0)),
        len(_portas._folhas_portas(grupo)), l, centro[0])
    return 0.0, destino - fechado


def _slider_na_tela(context, folha):
    """(start, end) of the slider in pixels, with start always on the left, except for
    sliding doors: it goes from the closed position to the open position (the dot
    follows the leaf)."""
    pontos = [_hud._projetar_hud(context, p) for p in _slider_no_mundo(folha)]
    if any(p is None for p in pontos) or (pontos[1] - pontos[0]).length < 1:
        return None
    if _curso_do_slider(folha, *_ferragens._dados_da_folha(folha)[::3]) is not None:
        return tuple(pontos)
    return tuple(sorted(pontos, key=lambda p: p.x))


def _fracao_no_slider(inicio, fim, mouse):
    trilho = fim - inicio
    return max(0.0, min(1.0, (mouse - inicio).dot(trilho) / trilho.length_squared))


def _px_por_mm_do_slider(context, folha):
    """Pixels per mm at the slider midpoint, measured along SCREEN vertical so track
    tilt does not thin the drawing; apply the cap."""
    rv3d = context.region_data
    a, b = _slider_no_mundo(folha)
    meio = (a + b) / 2.0
    cima = rv3d.view_rotation @ Vector((0.0, 1.0, 0.0))
    p, q = (_hud._projetar_hud(context, v) for v in (meio, meio + cima * 0.1))
    teto = SLIDER_PX_POR_MM_MAX * max(1.0, context.preferences.system.ui_scale)
    if p is None or q is None:
        return teto
    return min((q - p).length / 100.0, teto)


def _botao_do_slider(context, folha):
    """Slider dot center (pixels), or None."""
    tela = _slider_na_tela(context, folha)
    if tela is None:
        return None
    return tela[0].lerp(tela[1], float(folha.get(_ferragens.CHAVE_ABERTURA, 0.0)))


def _slider_sob_mouse(context, posicao):
    """Leaf whose DOT is under the mouse, or None. Hit reach equals dot size (user
    request): the track does not capture clicks."""
    if getattr(context, 'region_data', None) is None:
        return None             # Without a 3D view there is no onscreen slider.
    mouse = Vector(posicao)
    melhor = None
    for folha in _folhas_com_slider(context):
        botao = _botao_do_slider(context, folha)
        if botao is None:
            continue
        # Match the drawn dot size (minimum 3 px so it remains clickable).
        raio = max(3.0, SLIDER_BOTAO_MM * _px_por_mm_do_slider(context, folha))
        d = (botao - mouse).length
        if d <= raio and (melhor is None or d < melhor[0]):
            melhor = (d, folha)
    return melhor[1] if melhor else None


def _texto_abertura(folha):
    grupo = _portas._grupo_portas(folha)
    p = (grupo.get('porta_parametros') or {}) if grupo is not None else {}
    fracao = float(folha.get(_ferragens.CHAVE_ABERTURA, 0.0))
    abertura = p.get('abertura', 'GIRO')
    if abertura == 'CORRER':
        l, a, e, centro = _ferragens._dados_da_folha(folha)
        mm = (_ferragens._matriz_abertura(p, float(grupo.get('porta_vao_largura_mm', 0.0)),
                               len(_portas._folhas_portas(grupo)),
                               int(folha.get('porta_indice', 0)),
                               (l, a, e, centro), fracao).translation * 1000.0
              - Vector(centro)).length
        return '%d mm' % round(mm)
    maximo = (_ferragens._giro_maximo_rig() if _ferragens._usa_rig(p)
              else float(p.get('abertura_limite_graus',_ferragens.ABERTURA_MAX_GRAUS.get(abertura, 110.0))))
    return '%d%s' % (round(maximo * fracao), SIMBOLO_GRAU)


def _desenhar_sliders_porta(context):
    folhas = _folhas_com_slider(context)
    if not folhas:
        return
    realce = _hud._cor_realce_hud()
    arrastando = _arraste_slider_porta[0]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        for folha in folhas:
            tela = _slider_na_tela(context, folha)
            if tela is None:
                continue
            inicio, fim = tela
            fracao = float(folha.get(_ferragens.CHAVE_ABERTURA, 0.0))
            botao = inicio.lerp(fim, fracao)
            # Everything scales with zoom: one scale unit = 1 mm onscreen.
            mm = _px_por_mm_do_slider(context, folha)
            grosso = SLIDER_ESPESSURA_MM * mm
            raio = SLIDER_BOTAO_MM * mm
            aceso = folha.name in (arrastando, _slider_hover[0])
            shader.bind()
            # Opaque colors: alpha would expose the join between the rounded ends.
            _capsula_2d(shader, inicio, fim, grosso + 3.0 * mm,
                        (0.92, 0.92, 0.92, 1.0))
            _capsula_2d(shader, inicio, fim, grosso, (0.13, 0.13, 0.13, 1.0))
            if fracao > 0:
                _capsula_2d(shader, inicio, botao, grosso * 0.65, realce)
            if aceso:
                _hud._bolinha_2d(shader, botao, raio + 3.0 * mm, realce)
            _hud._bolinha_2d(shader, botao, raio, (1.0, 1.0, 1.0, 1.0))
            _hud._bolinha_2d(shader, botao, raio * 0.45, realce)
            # Value in a black box centered above the button; hide it when too small to
            # read (the slider remains).
            tamanho = SLIDER_TEXTO_MM * mm
            if tamanho >= SLIDER_TEXTO_MIN_PX:
                texto = _texto_abertura(folha)
                blf.size(0, tamanho)
                largura = blf.dimensions(0, texto)[0]
                _hud._caixa_texto_hud(botao.x - largura / 2.0,
                                 botao.y + raio + 7.0 * mm, texto, tamanho,
                                 tamanho / 12.0)
                gpu.state.blend_set('ALPHA')
    finally:
        gpu.state.blend_set('NONE')


def _capsula_2d(shader, a, b, grossura, rgba):
    """Track with rounded ends (the slider)."""
    shader.uniform_float('color', rgba)
    quad = _puxadores._quad_2d(a, b, grossura)
    if quad:
        batch_for_shader(shader, 'TRIS', {'pos': quad}).draw(shader)
    for ponta in (a, b):
        _hud._bolinha_2d(shader, ponta, grossura / 2.0, rgba)


class OBJECT_OT_abrir_porta(Operator):
    """Drag the leaf slider: right opens, left closes."""
    bl_idname = 'object.cabinet_abrir_porta'
    bl_label = "Open Door"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    folha: StringProperty(options={'SKIP_SAVE'})
    fracao: FloatProperty(min=0.0, max=1.0, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return _hud._contexto_hud(context)

    def execute(self, context):
        folha = bpy.data.objects.get(self.folha)
        if folha is None or not _ferragens._definir_abertura(context, folha, self.fracao):
            return {'CANCELLED'}
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}

    def invoke(self, context, event):
        # From the dot gizmo (or keymap): clicks outside it pass through.
        folha = _slider_sob_mouse(context, (event.mouse_region_x,
                                            event.mouse_region_y))
        if folha is None:
            return {'PASS_THROUGH'}
        self.folha = folha.name
        self._antes = float(folha.get(_ferragens.CHAVE_ABERTURA, 0.0))
        self._area = context.area
        # An off-center grab must not make the dot jump to the mouse.
        self._desvio = self._fracao_do_mouse(context, event, folha) - self._antes
        _arraste_slider_porta[0] = folha.name
        context.window_manager.modal_handler_add(self)
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    @staticmethod
    def _fracao_do_mouse(context, event, folha):
        tela = _slider_na_tela(context, folha)
        if tela is None:
            return float(folha.get(_ferragens.CHAVE_ABERTURA, 0.0))
        return _fracao_no_slider(*tela, Vector((event.mouse_region_x,
                                                event.mouse_region_y)))

    def _arrastar(self, context, event):
        folha = bpy.data.objects.get(self.folha)
        if folha is None:
            return
        self.fracao = max(0.0, min(1.0, self._fracao_do_mouse(
            context, event, folha) - self._desvio))
        _ferragens._definir_abertura(context, folha, self.fracao)
        self._area.tag_redraw()

    def _encerrar(self):
        _arraste_slider_porta[0] = None
        self._area.tag_redraw()

    def cancel(self, context):
        self._encerrar()

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            folha = bpy.data.objects.get(self.folha)
            if folha is not None:
                _ferragens._definir_abertura(context, folha, self._antes)
            self._encerrar()
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            self._arrastar(context, event)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self._arrastar(context, event)
            self._encerrar()
            return {'FINISHED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}


class VIEW3D_GT_slider_porta(Gizmo):
    """Opening slider dot; its hit area matches its size.

    Use a gizmo, not only a keymap: gizmos are evaluated BEFORE any keymap. In the
    user's keyconfig, selection preceded the slider entry (the add-on's head=True
    does not affect that ordering), cleared selection and made the slider disappear
    before receiving the click."""
    bl_idname = 'VIEW3D_GT_slider_porta'

    def draw(self, context):
        pass

    def test_select(self, context, location):
        folha = (_slider_sob_mouse(context, location)
                 if _hud._contexto_hud(context) else None)
        nome = folha.name if folha is not None else None
        if nome != _slider_hover[0]:
            _slider_hover[0] = nome
            context.area.tag_redraw()
        return 0 if folha is not None else -1


class VIEW3D_GGT_slider_porta(GizmoGroup):
    bl_idname = 'VIEW3D_GGT_slider_porta'
    bl_label = "Door Opening Slider"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        return _hud._contexto_hud(context) and bool(_folhas_com_slider(context))

    def setup(self, context):
        self.botao = self.gizmos.new('VIEW3D_GT_slider_porta')
        self.botao.use_tooltip = False
        self.botao.target_set_operator('object.cabinet_abrir_porta')

    def draw_prepare(self, context):
        if not self.botao.is_highlight and _slider_hover[0] is not None:
            _slider_hover[0] = None
