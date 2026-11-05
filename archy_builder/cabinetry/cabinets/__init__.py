"""Cabinet assemblies: dimensions, resizing, Empty/Collection grouping,
and measurements of arbitrary selections and the scene group."""

import bpy
from bpy.props import StringProperty
from mathutils import Matrix, Vector
from bpy.types import Operator

# Used only at runtime (circular imports): __init__ binds these
# aliases after loading all modules (`_ligar_modulos`).
_chapas = _portas = _gaveta = _gavetas = _formas = _prateleiras = _divisorias = _solda = _fundos = None

# ================================================= CABINET ASSEMBLY
# Grouping gives the Empty cabinet dimensions in addition to its
# parent role: width, height, depth and thickness.
#
# Rule: EXTERNAL dimensions govern. When one changes,
# parts fit inside while retaining their specified thickness, and
# adjacency closes the joints. Changing THICKNESS leaves the external
# outline fixed: panels thicken/thin inward, and parts spanning
# the cabinet shrink or expand to follow.
TOL_BORDA = 0.0015   # 1.5 mm tolerance for considering a face on the boundary.


def _chapas_do_conjunto(conj):
    return [o for o in bpy.data.objects
            if o.parent == conj and o.type == 'MESH' and _chapas.MARCA_CHAPA in o]


def _estruturais(chapas):
    """Exclude the back: it has its own thickness and is not resized
    proportionally (see `ajustar_fundo`)."""
    return [c for c in chapas if not _chapas.eh_dependente(c)]


def _espessura_de(chapas):
    """Cabinet/group E comes from a body part, never the back
    (alphabetically, "Fundo" precedes "Lateral", which made cabinet E 5)."""
    caixa = _estruturais(chapas) or chapas
    # Use the MOST COMMON thickness (ties: first): in DXF imports, the first
    # part can be a 6 mm back or a thin shelf.
    valores = [round(c.chapa_espessura_mm, 2) for c in caixa]
    return max(valores, key=lambda v: (valores.count(v), -valores.index(v)))


def _caixa_de(chapas):
    """World bounding box of any list of panels.
    Update the depsgraph first: matrix_world is correct only after
    evaluation; earlier reads returned the PREVIOUS operation's box."""
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    pts = []
    for o in chapas:
        pts.extend(_chapas._cantos(o))
    if not pts:
        return None
    return ([min(p[i] for p in pts) for i in range(3)],
            [max(p[i] for p in pts) for i in range(3)])


def _vizinhos_gravados(C):
    """Neighbors recorded on C by adjacency detection (direction C -> N)."""
    saida = []
    for eixo in ('x', 'y'):
        for lado in ('pos', 'neg'):
            N = _chapas._resolver_vizinho(C, C.get('adj_%s_%s_uid' % (eixo, lado), ''),
                                  C.get('adj_%s_%s' % (eixo, lado), ''))
            if N is not None:
                saida.append(N)
    return saida


def _grupo_solto(obj, simetrico):
    """Transitive adjacency closure for a panel outside an assembly.

    Adjacency links are ONE-WAY: a shelf points to its sides,
    but neither side points back to the shelf.
    simetrico=True builds both directions so traversal from a side
    also reaches internal parts.

    Scan only SIBLINGS (same parent), matching `_chapas._resolver_vizinho`,
    to avoid scanning the whole file on each click.
    """
    chapas = [o for o in bpy.data.objects if o.type == 'MESH'
              and _chapas.MARCA_CHAPA in o and o.parent == obj.parent]
    ligacoes = {o.name: set() for o in chapas}
    porta = {o.name: o for o in chapas}
    restricoes = _solda.restricoes_adjacencia(chapas)
    for C in chapas:
        for N, _face, _folga in restricoes[C].values():
            if N.name not in ligacoes:
                continue
            ligacoes[C.name].add(N.name)
            if simetrico:
                ligacoes[N.name].add(C.name)
    vistos, fila = {obj.name}, [obj.name]
    while fila:
        for viz in ligacoes.get(fila.pop(), ()):
            if viz not in vistos:
                vistos.add(viz)
                fila.append(viz)
    return [porta[n] for n in vistos if n in porta]


def grupo_de(obj, simetrico=False):
    """Determine a panel's GROUP: its entire assembly if it belongs to one;
    otherwise the panel and everything transitively linked by adjacency.

    simetrico=True also follows reverse links, as SELECTION needs
    the whole visible cabinet. Dimension recalculation remains strict
    to avoid silently changing its scope.
    """
    if obj is None or _chapas.MARCA_CHAPA not in obj:
        return []
    if obj.parent is not None and _chapas.MARCA_CONJUNTO in obj.parent:
        return _chapas_do_conjunto(obj.parent)
    return _grupo_solto(obj, simetrico)


def pecas_do_envelope(conj):
    """Parts counted as the CABINET: its panels plus a framed sliding
    door's frame, which becomes part of the envelope for L/A/P and HUD.
    Measurement only: `redimensionar_conjunto` still resizes the body,
    and the frame follows its door."""
    return _chapas_do_conjunto(conj) + [
        o for g in _portas._portas_do_conjunto(conj)
        for o in _portas._moldura_da_porta(g)]


def _caixa_do_conjunto(conj):
    """World-space bounding box of the cabinet envelope."""
    return _caixa_de(pecas_do_envelope(conj))


def _acrescimo_da_moldura(conj):
    """Constant (L, A, P) additions to the body box, in mm, from the frame
    (thickness, tracks, plinth, fascia); they do not grow with the cabinet."""
    corpo, envelope = _caixa_de(_chapas_do_conjunto(conj)), _caixa_do_conjunto(conj)
    if corpo is None or envelope is None:
        return (0.0, 0.0, 0.0)
    medida = lambda c, a: (c[1][a] - c[0][a]) * 1000.0
    return tuple(medida(envelope, a) - medida(corpo, a) for a in (0, 2, 1))


def _eixo_local_alinhado(obj, a):
    """Local axis (0=width, 1=length, 2=thickness) aligned with world axis a;
    also return its half-extent."""
    eixos = _chapas._eixos(obj)
    meias = _chapas._meias(obj)
    alin = [abs(eixos[i][a]) for i in range(3)]
    i = alin.index(max(alin))
    return i, meias[i]


def _escrever_dim(obj, i_local, meia_m):
    if i_local == 0:
        obj.chapa_largura_mm = meia_m * 2000.0
    elif i_local == 1:
        obj.chapa_comprimento_mm = meia_m * 2000.0


def medir_conjunto(conj):
    cx = _caixa_do_conjunto(conj)
    if cx is None:
        return None
    lo, hi = cx
    return ((hi[0]-lo[0])*1000.0, (hi[2]-lo[2])*1000.0, (hi[1]-lo[1])*1000.0)


def redimensionar_grupo(chapas, alvo_LAP_mm, ancoras=None):
    """Resize the cabinet's external box to the requested width/height/depth.
    Parts whose THICKNESS lies on that axis keep their thickness and
    anchor to their existing boundary; other parts scale proportionally.

    `ancoras` specifies the fixed side for each WORLD axis (X, Y, Z):
    'min' (the historical default) or 'max'. This lets the HUD resize
    from the cabinet corner nearest the mouse."""
    chapas = _estruturais(chapas)
    cx = _caixa_de(chapas)
    if cx is None:
        return
    lo, hi = cx
    lo_antes, hi_antes = list(lo), list(hi)
    L, A, P = alvo_LAP_mm
    pai = chapas[0].parent if chapas else None
    if pai is not None and _chapas.MARCA_CONJUNTO in pai:
        _portas.preparar_referencias_vaos(pai)
        L,A,P = _gavetas.limitar_medidas(pai,lo,hi,(L,A,P))
    alvo_mm = (L, P, A)   # World axis order: X, Y, Z.
    ancoras = ancoras or ('min', 'min', 'min')

    _chapas._ocupado[0] = True
    try:
        for a in range(3):
            velho = hi[a] - lo[a]
            novo = alvo_mm[a] / 1000.0
            if velho < 1e-6 or abs(novo - velho) < 1e-7:
                continue
            razao = novo / velho
            # p is the fixed point; m1..M1 is the new axis range.
            p = hi[a] if ancoras[a] == 'max' else lo[a]
            m1 = p - novo if ancoras[a] == 'max' else p
            M1 = m1 + novo
            for C in chapas:
                i_loc, h = _eixo_local_alinhado(C, a)
                c = _chapas._centro(C)[a]
                f_min, f_max = c - h, c + h
                if i_loc == 2:
                    # THICKNESS axis: keep its extent.
                    if abs(f_min - lo[a]) < TOL_BORDA:
                        novo_c = m1 + h
                    elif abs(f_max - hi[a]) < TOL_BORDA:
                        novo_c = M1 - h
                    else:
                        novo_c = p + (c - p) * razao
                    nc = _chapas._centro(C); nc[a] = novo_c; _chapas._definir_centro(C, nc)
                else:
                    nf_min = p + (f_min - p) * razao
                    nf_max = p + (f_max - p) * razao
                    _escrever_dim(C, i_loc, (nf_max - nf_min) / 2.0)
                    nc = _chapas._centro(C); nc[a] = (nf_max + nf_min) / 2.0; _chapas._definir_centro(C, nc)
            lo[a], hi[a] = m1, M1
            # `_centro` reads matrix_world: without an update here, the next
            # axis wrote back the OLD center and undid this displacement,
            # making the part grow about its center and ignore
            # the anchor.
            bpy.context.view_layer.update()
    finally:
        _chapas._ocupado[0] = False

    for C in chapas:
        _chapas.gerar_malha_chapa(C)
    pai = chapas[0].parent if chapas else None
    if pai is not None and _chapas.MARCA_CONJUNTO in pai:
        _acompanhar_acessorios(pai, lo_antes, hi_antes, lo, hi)
        _gavetas.acompanhar_redimensionamento(pai, lo_antes, hi_antes, lo, hi)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    _chapas.aplicar_adjacencia(chapas)
    if pai is not None and _chapas.MARCA_CONJUNTO in pai:
        ajustar_dependentes(pai)


def _acompanhar_acessorios(conj, lo_antes, hi_antes, lo, hi):
    """Do not stretch accessories (feet, hanging rails, curved parts).
    For each world axis, follow the nearest cabinet face while retaining
    the distance to it. Measure against the OLD box; store nothing,
    so moving an accessory makes the rule use its new position.
    """
    for acc in [o for o in conj.children if _chapas.MARCA_ACESSORIO in o]:
        cantos = [acc.matrix_world @ Vector(c) for c in acc.bound_box]
        delta = Vector()
        for a in range(3):
            c_min = min(p[a] for p in cantos)
            c_max = max(p[a] for p in cantos)
            perto_do_min = (c_min - lo_antes[a]) <= (hi_antes[a] - c_max)
            delta[a] = (lo[a] - lo_antes[a] if perto_do_min
                        else hi[a] - hi_antes[a])
        if delta.length > 1e-9:
            matriz = acc.matrix_world.copy()
            matriz.translation += delta
            acc.matrix_world = matriz


def aplicar_espessura_grupo(chapas, nova_e):
    """Change every cabinet panel's thickness WITHOUT moving the external
    outline: each part grows/shrinks INWARD from its existing boundary.
    Adjacency then expands/contracts spanning parts. The back retains
    its own thickness and is rebuilt to the new box."""
    chapas = _estruturais(chapas)
    cx = _caixa_de(chapas)
    if cx is None:
        return
    lo, hi = cx

    _chapas._ocupado[0] = True
    try:
        for C in chapas:
            eixos = _chapas._eixos(C)
            ez = eixos[2]
            alin = [abs(ez[a]) for a in range(3)]
            a = alin.index(max(alin))          # World thickness axis.
            h_velho = C.chapa_espessura_mm / 2000.0
            c = _chapas._centro(C)[a]
            f_min, f_max = c - h_velho, c + h_velho
            C.chapa_espessura_mm = nova_e
            h_novo = nova_e / 2000.0
            if abs(f_min - lo[a]) < TOL_BORDA:
                nc = _chapas._centro(C); nc[a] = f_min + h_novo; _chapas._definir_centro(C, nc)
            elif abs(f_max - hi[a]) < TOL_BORDA:
                nc = _chapas._centro(C); nc[a] = f_max - h_novo; _chapas._definir_centro(C, nc)
            else:
                pass                                     # Internal part: keep its center.
    finally:
        _chapas._ocupado[0] = False

    for C in chapas:
        _chapas.gerar_malha_chapa(C)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    _chapas.aplicar_adjacencia(chapas)
    pai = chapas[0].parent if chapas else None
    if pai is not None and _chapas.MARCA_CONJUNTO in pai:
        ajustar_dependentes(pai)


def aplicar_espessura_chapa(C, nova_e, e_velha_mm):
    """Thicken ONE panel INWARD: hold the face on the group's external
    boundary fixed and let adjacency shrink internal parts to fit.

    Otherwise the panel grew about its CENTER, half outside the cabinet
    and half into its neighbor.

    `e_velha_mm` comes from the mesh because the update callback sees
    the property already changed. Measure the group box with the old
    thickness restored too, or the expansion itself would already have
    shifted the reference boundary.
    """
    grupo = grupo_de(C) or [C]
    ez = _chapas._eixos(C)[2]
    a = max(range(3), key=lambda i: abs(ez[i]))   # World thickness axis.

    _chapas._ocupado[0] = True
    try:
        C.chapa_espessura_mm = e_velha_mm
        cx = _caixa_de(grupo)
        C.chapa_espessura_mm = nova_e
    finally:
        _chapas._ocupado[0] = False

    h_velho = e_velha_mm / 2000.0
    h_novo = nova_e / 2000.0
    c = _chapas._centro(C)[a]
    f_min, f_max = c - h_velho, c + h_velho
    novo_c = None
    # A loose panel (no assembly or adjacency) has no cabinet interior:
    # keep growing it about its center.
    if cx is not None and len(grupo) > 1:
        lo, hi = cx
        if abs(f_min - lo[a]) < TOL_BORDA:
            novo_c = f_min + h_novo      # Touching the minimum boundary.
        elif abs(f_max - hi[a]) < TOL_BORDA:
            novo_c = f_max - h_novo      # Touching the maximum boundary.
    # Internal panel (shelf, partition): grow about its center.

    if novo_c is not None:
        _chapas._ocupado[0] = True
        try:
            nc = _chapas._centro(C)
            nc[a] = novo_c
            _chapas._definir_centro(C, nc)
        finally:
            _chapas._ocupado[0] = False

    _chapas.gerar_malha_chapa(C)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    # Do NOT call aplicar_adjacencia: changing ONE panel's thickness must
    # leave everything else alone. Global adjacency pulled back even parts
    # deliberately moved away ("stuck to welds"). A joint displaced from
    # its origin is handled by the ruler (`cabinet_resetar_distancia`).
    # CABINET E (`aplicar_espessura_grupo`) still refits the other parts.
    pai = C.parent
    if pai is not None and _chapas.MARCA_CONJUNTO in pai:
        reposicionar_origem(pai)


def reposicionar_origem(conj):
    """Move the ORIGIN (Empty) to the cabinet's actual XY center and Z base,
    compensating children so nothing moves visually.

    Previously the origin stayed fixed and the cabinet slid relative to it
    on every resize, because growth anchors to the box's minimum corner.
    """
    if conj is None or _chapas.MARCA_CONJUNTO not in conj:
        return
    chapas = _chapas_do_conjunto(conj)
    if not chapas:
        return
    # Without this, the matrices read below may be stale and the origin
    # would move only on the NEXT operation.
    bpy.context.view_layer.update()
    # Keep ALL children fixed, not just panels: accessories and door groups
    # would otherwise follow the origin.
    filhos = list(conj.children)
    mundos = {o.name: o.matrix_world.copy() for o in filhos}
    pts = []
    for o in chapas:
        pts.extend([o.matrix_world @ v.co for v in o.data.vertices])
    if not pts:
        return
    alvo = Vector((
        (min(p.x for p in pts) + max(p.x for p in pts)) / 2.0,
        (min(p.y for p in pts) + max(p.y for p in pts)) / 2.0,
        min(p.z for p in pts),
    ))
    if (alvo - conj.matrix_world.translation).length < 1e-6:
        return
    _chapas._ocupado[0] = True
    try:
        conj.location = alvo
        bpy.context.view_layer.update()
        for o in filhos:
            if conj.matrix_world.determinant() < 0:
                # Keep reflection on the parent, without negative panel scale.
                _chapas._definir_centro(o, mundos[o.name].translation)
            else:
                o.matrix_parent_inverse = conj.matrix_world.inverted()
                o.matrix_world = mundos[o.name]
    finally:
        _chapas._ocupado[0] = False


# ============================================ ARBITRARY SELECTION DIMENSIONS
# The sidebar wireframe (`_gaveta._desenhar_wireframe_gaveta`) is already
# generic: it takes three dimensions and draws a box.
# What was missing was MEASURING arbitrary selections: a cube, a car
# with dozens of meshes and curves, or any other geometry.

# Types that occupy space. Empty/camera/light bound_box degenerates to
# their origin, which would extend the box to a point with no geometry.
TIPOS_COM_VOLUME = {
    'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'CURVES',
    'POINTCLOUD', 'VOLUME', 'GREASEPENCIL', 'GPENCIL', 'LATTICE',
}


# For these types, bound_box describes CONTROL POINTS, not the displayed
# geometry: a beveled curve has the same bounds with or without bevel,
# and Bezier handles inflate the box. Only the evaluated mesh is accurate;
# for other types the evaluated bound_box already includes modifiers.
TIPOS_BBOX_INFIEL = {'CURVE', 'SURFACE', 'FONT', 'META'}


def _cantos_avaliados(obj, dep):
    """Points bounding the object in WORLD space.

    Use the EVALUATED object so modifiers, bevel and extrusion contribute
    the displayed shape rather than the raw geometry.
    """
    alvo = obj
    if dep is not None:
        try:
            alvo = obj.evaluated_get(dep)
        except Exception:
            alvo = obj
    m = obj.matrix_world

    if obj.type in TIPOS_BBOX_INFIEL:
        malha = None
        try:
            malha = alvo.to_mesh()
        except Exception:
            malha = None
        if malha is not None:
            try:
                if len(malha.vertices):
                    return [m @ v.co.copy() for v in malha.vertices]
            finally:
                try:
                    alvo.to_mesh_clear()
                except Exception:
                    pass

    try:
        return [m @ Vector(c) for c in alvo.bound_box]
    except Exception:
        return []


def _limites_mundo(context, objs):
    """World-space (minima, maxima, count), or None if nothing has volume."""
    objs = [o for o in objs if o.type in TIPOS_COM_VOLUME]
    if not objs:
        return None
    try:
        dep = context.evaluated_depsgraph_get()
    except Exception:
        dep = None

    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    contados = 0
    for o in objs:
        pts = _cantos_avaliados(o, dep)
        if not pts:
            continue
        contados += 1
        for pt in pts:
            for a in range(3):
                lo[a] = min(lo[a], pt[a])
                hi[a] = max(hi[a], pt[a])
    return (lo, hi, contados) if contados else None


def medir_selecao(context):
    """Bounding box of the current selection.

    Return (width, height, depth) in mm on WORLD axes (X, Z, Y),
    matching cabinet dimension conventions, and the number of objects
    included. Return None if nothing has volume.
    """
    limites = _limites_mundo(context, context.selected_objects)
    if limites is None:
        return None
    lo, hi, contados = limites
    return ((hi[0] - lo[0]) * 1000.0,      # Width  = X.
            (hi[2] - lo[2]) * 1000.0,      # Height = Z.
            (hi[1] - lo[1]) * 1000.0,      # Depth  = Y.
            contados)


# ================================== CABINET FIELDS, GROUPING AND GROUPS
# ------------------------------------------------------------- back
# User requirement: a 5 mm panel back set slightly INSIDE the cabinet.
# Research (woodworking forums, Festool/Sawmill Creek; Cortecloud;
# ClubArq): no published standard; grooves are 12-18 mm from the rear
# edge (15 most often cited), about 8 mm deep. Rear space accommodates
# uneven walls and moisture clearance (>= 10 mm). User chose 15 mm setback.
ESPESSURA_FUNDO_MM = 5.0
RECUO_FUNDO_MM = 15.0         # From the rear edge to the back panel's rear face.
CANAL_FUNDO_MM = 8.0          # Groove depth in sides/base/top.
FOLGA_CANAL_FUNDO_MM = 1.0    # The back does not reach the groove bottom.
CHAVE_RECUO_FUNDO = 'fundo_recuo_mm'    # On the cabinet (ID property).


def fundo_do_modulo(conj):
    return next((o for o in conj.children if _chapas.MARCA_FUNDO in o), None)


def fundos_do_modulo(conj):
    return [o for o in conj.children if _chapas.MARCA_FUNDO in o]


def guardar_formato_fundo(conj, fundo):
    """A partial/orthogonal back must not become the whole box rectangle."""
    lo, hi = _caixa_local_estrutural(conj)
    inv = conj.matrix_world.inverted()
    vs = [inv @ (fundo.matrix_world @ v.co) * 1000 for v in fundo.data.vertices]
    a = Vector(tuple(min(v[k] for v in vs) for k in range(3)))
    b = Vector(tuple(max(v[k] for v in vs) for k in range(3)))
    fundo['fundo_margens_mm'] = [d for k in range(3) for d in (a[k]-lo[k], hi[k]-b[k])]


def _ajustar_fundo_por_formato(conj, fundo, lo, hi):
    m = conj.matrix_world.inverted() @ fundo.matrix_world
    eixos = [max(range(3), key=lambda k: abs(m.to_3x3().col[j][k])) for j in range(3)]
    margens = list(fundo['fundo_margens_mm'])
    a = Vector(tuple(lo[k]+margens[2*k] for k in range(3)))
    b = Vector(tuple(hi[k]-margens[2*k+1] for k in range(3)))
    normal = eixos[2]
    recuo=float(conj.get(CHAVE_RECUO_FUNDO,RECUO_FUNDO_MM))
    if 'fundo_recuo_base_mm' not in fundo:fundo['fundo_recuo_base_mm']=recuo
    delta=recuo-float(fundo['fundo_recuo_base_mm'])
    if margens[2*normal] < margens[2*normal+1]:
        a[normal]+=delta
        b[normal] = a[normal]+fundo.chapa_espessura_mm
    else:
        b[normal]-=delta
        a[normal] = b[normal]-fundo.chapa_espessura_mm
    _chapas._ocupado[0] = True
    try:
        fundo.chapa_largura_mm = max(1, b[eixos[0]]-a[eixos[0]])
        fundo.chapa_comprimento_mm = max(1, b[eixos[1]]-a[eixos[1]])
        m.translation = (a+b)/2000
        fundo.matrix_world = conj.matrix_world @ m
    finally:
        _chapas._ocupado[0] = False
    _chapas.gerar_malha_chapa(fundo)


def medidas_do_fundo(L, A, E, recuo=RECUO_FUNDO_MM):
    """Back CUT (width, height) and setback in mm: the internal opening
    plus penetration into each side's groove."""
    entra = CANAL_FUNDO_MM - FOLGA_CANAL_FUNDO_MM
    return L - 2.0 * E + 2.0 * entra, A - 2.0 * E + 2.0 * entra, recuo


def _caixa_local_estrutural(conj):
    """Body-part bounds (lo, hi) in mm on cabinet axes, excluding the back."""
    inversa = conj.matrix_world.inverted()
    pontos = [inversa @ (o.matrix_world @ v.co) * 1000.0
              for o in _estruturais(_chapas_do_conjunto(conj))
              for v in o.data.vertices]
    if not pontos:
        return None
    return (Vector(tuple(min(p[i] for p in pontos) for i in range(3))),
            Vector(tuple(max(p[i] for p in pontos) for i in range(3))))


def ajustar_fundo(conj):
    """Rebuild the back from the CURRENT cabinet box: between sides, base
    and top, extending into grooves, with its rear face `fundo_recuo_mm`
    from the rear edge (cabinet +Y; see `_portas._folgas_do_vao`). No back: no-op."""
    for novo in fundos_do_modulo(conj):
        if 'fundo_tipo' in novo:
            _fundos.ajustar_ao_modulo(novo)
    legados = [o for o in fundos_do_modulo(conj) if 'fundo_tipo' not in o]
    fundo = next(iter(legados), None)
    caixa = _caixa_local_estrutural(conj) if fundo is not None else None
    if caixa is None:
        return False
    lo, hi = caixa
    modelados = [o for o in legados if 'fundo_margens_mm' in o]
    if modelados:
        for obj in modelados:
            _ajustar_fundo_por_formato(conj, obj, lo, hi)
        return True
    E = float(conj.conj_espessura_mm) or 18.0
    recuo = float(conj.get(CHAVE_RECUO_FUNDO, RECUO_FUNDO_MM))
    largura, altura, _r = medidas_do_fundo(hi.x - lo.x, hi.z - lo.z, E, recuo)
    esp = fundo.chapa_espessura_mm
    centro = Vector(((lo.x + hi.x) / 2.0, hi.y - recuo - esp / 2.0,
                     (lo.z + hi.z) / 2.0)) / 1000.0
    _chapas._ocupado[0] = True
    try:
        fundo.chapa_largura_mm = max(1.0, largura)
        fundo.chapa_comprimento_mm = max(1.0, altura)
        # Panel: X width, Y length (cabinet HEIGHT), Z thickness
        # (cabinet depth): upright, rotated 90 degrees about X.
        fundo.matrix_world = (conj.matrix_world @ Matrix.Translation(centro)
                              @ Matrix.Rotation(1.5707963267948966, 4, 'X'))
    finally:
        _chapas._ocupado[0] = False
    _chapas.gerar_malha_chapa(fundo)
    return True


# A countertop base cabinet is open at the top: two panel crosspieces
# between the sides, one flush with the front and the other with the rear,
# replace the top panel and support the countertop/sink.
LARGURA_TRAVESSA_MM = 70.0
LADOS_TRAVESSA = (('FRENTE', "Front Rail"), ('TRAS', "Rear Rail"))
CHAVE_LADO_TRAVESSA = 'travessa_lado'


def travessas_do_modulo(conj):
    return [o for o in conj.children if _chapas.MARCA_TRAVESSA in o]


def ajustar_travessas(conj):
    """Rebuild crosspieces from the CURRENT box: between sides, at the top,
    with cabinet thickness. Each stays flush with its edge (front = -Y)
    and retains its width, including user edits."""
    travessas = travessas_do_modulo(conj)
    caixa = _caixa_local_estrutural(conj) if travessas else None
    if caixa is None:
        return False
    lo, hi = caixa
    E = float(conj.conj_espessura_mm) or 18.0
    _chapas._ocupado[0] = True
    try:
        for tr in travessas:
            largura = tr.chapa_comprimento_mm
            frente = tr.get(CHAVE_LADO_TRAVESSA, 'FRENTE') == 'FRENTE'
            y = lo.y + largura / 2.0 if frente else hi.y - largura / 2.0
            tr.chapa_largura_mm = max(1.0, (hi.x - lo.x) - 2.0 * E)
            tr.chapa_espessura_mm = E
            centro = Vector(((lo.x + hi.x) / 2.0, y, hi.z - E / 2.0)) / 1000.0
            tr.matrix_world = conj.matrix_world @ Matrix.Translation(centro)
    finally:
        _chapas._ocupado[0] = False
    for tr in travessas:
        _chapas.gerar_malha_chapa(tr)
    return True


def adicionar_travessas(conj, context=None, largura=LARGURA_TRAVESSA_MM):
    """The two open-top crosspieces; keep existing ones."""
    context = context or bpy.context
    existentes = {t.get(CHAVE_LADO_TRAVESSA) for t in travessas_do_modulo(conj)}
    colecao = _colecao_do_modulo(conj)
    for lado, nome in LADOS_TRAVESSA:
        if lado in existentes:
            continue
        tr = _chapas.nova_chapa(nome, 100.0, largura, conj.conj_espessura_mm,
                                (0, 0, 0), (0, 0, 0), context)
        tr[_chapas.MARCA_TRAVESSA] = 1
        tr[CHAVE_LADO_TRAVESSA] = lado
        tr.parent = conj
        tr.matrix_parent_inverse = conj.matrix_world.inverted()
        if colecao is not None:
            _mover_para_colecao(tr, colecao)
    context.view_layer.update()
    ajustar_travessas(conj)
    return travessas_do_modulo(conj)


def ajustar_dependentes(conj):
    """Rebuild the back and crosspieces from the new cabinet box."""
    ajustar_travessas(conj)
    ajustar_fundo(conj)


def adicionar_fundo(conj, context=None, recuo=RECUO_FUNDO_MM,
                    espessura=ESPESSURA_FUNDO_MM):
    """Add or adjust the cabinet back; return the back panel."""
    context = context or bpy.context
    conj[CHAVE_RECUO_FUNDO] = float(recuo)
    fundo = fundo_do_modulo(conj)
    if fundo is None:
        fundo = _chapas.nova_chapa("Back Panel", 100.0, 100.0, espessura,
                                   (0, 0, 0), (0, 0, 0), context)
        fundo[_chapas.MARCA_FUNDO] = 1
        fundo.parent = conj
        fundo.matrix_parent_inverse = conj.matrix_world.inverted()
        colecao = _colecao_do_modulo(conj) or next(iter(conj.users_collection),None)
        if colecao is not None:
            _mover_para_colecao(fundo, colecao)
    else:
        _chapas._ocupado[0] = True
        try:
            for obj in fundos_do_modulo(conj):obj.chapa_espessura_mm = espessura
        finally:
            _chapas._ocupado[0] = False
    context.view_layer.update()
    ajustar_fundo(conj)
    return fundo


def remover_fundo(conj):
    fundos = fundos_do_modulo(conj)
    if not fundos:
        return False
    for fundo in fundos:
        _fundos.remover_canal(fundo)
        malha = fundo.data
        bpy.data.objects.remove(fundo, do_unlink=True)
        if malha is not None and malha.users == 0:
            bpy.data.meshes.remove(malha)
    if CHAVE_RECUO_FUNDO in conj:
        del conj[CHAVE_RECUO_FUNDO]
    return True


class OBJECT_OT_fundo_modulo(Operator):
    """Cabinet panel back fitted into grooves and set back from the rear
    edge; follows cabinet dimensions."""
    bl_idname = 'object.cabinet_fundo_modulo'
    bl_label = "Cabinet Back"
    bl_options = {'REGISTER', 'UNDO'}

    recuo_mm: bpy.props.FloatProperty(
        name="Recess (mm)", default=RECUO_FUNDO_MM, min=0.0,
        description="From the cabinet's rear edge to the back of the back panel")
    espessura_mm: bpy.props.FloatProperty(
        name="Thickness (mm)", default=ESPESSURA_FUNDO_MM, min=1.0)
    remover: bpy.props.BoolProperty(name="Remove Back", default=False,
                                    options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return any(_conj_de(o) is not None for o in context.selected_objects)

    def invoke(self, context, event):
        conj = next((_conj_de(o) for o in context.selected_objects
                     if _conj_de(o) is not None), None)
        fundo = fundo_do_modulo(conj) if conj is not None else None
        if conj is not None:
            self.recuo_mm = float(conj.get(CHAVE_RECUO_FUNDO, RECUO_FUNDO_MM))
        if fundo is not None:
            self.espessura_mm = fundo.chapa_espessura_mm
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        modulos = {_conj_de(o) for o in context.selected_objects} - {None}
        for conj in modulos:
            if self.remover:
                remover_fundo(conj)
            else:
                adicionar_fundo(conj, context, self.recuo_mm, self.espessura_mm)
        return {'FINISHED'} if modulos else {'CANCELLED'}


def criar_armario(context, nome, L, A, P, E=18.0, fundo=True, topo='TAMPO'):
    """Create a NATIVE cabinet using add-on panels only: full-height sides,
    a base between them, and a top (`topo`='TAMPO') or two crosspieces
    ('TRAVESSAS', open top). With `fundo`, add a 5 mm grooved back.
    EXTERNAL dimensions in mm; create at the origin, front toward -Y.
    Return the cabinet Empty, already active."""
    li = L - 2.0 * E
    pecas = [
        ("Left Side", A, P, E, (-(L / 2 - E / 2), 0, A / 2), (0, 90, 0)),
        ("Right Side", A, P, E, ((L / 2 - E / 2), 0, A / 2), (0, 90, 0)),
        ("Base", li, P, E, (0, 0, E / 2), (0, 0, 0)),
    ]
    if topo == 'TAMPO':
        pecas.append(("Top", li, P, E, (0, 0, A - E / 2), (0, 0, 0)))
    criadas = [_chapas.nova_chapa(n, la, c, e, lo, r, context)
               for n, la, c, e, lo, r in pecas]
    context.view_layer.update()
    conj = agrupar_chapas(context, criadas, nome)
    if topo == 'TRAVESSAS':
        adicionar_travessas(conj, context)
    if fundo:
        adicionar_fundo(conj, context)
    return conj


def _conj_de(obj):
    while obj is not None:
        if _chapas.MARCA_CONJUNTO in obj:
            return obj
        obj = obj.parent
    return None


def _upd_conj_dim(self, context):
    if _chapas._ocupado[0]:
        return
    redimensionar_conjunto(self)


def atualizar_sistemas_do_conjunto(conj, internos=True):
    """Body already applied: doors/supports, drawers, then shelves.

    Each domain retains its calculations and geometry writes. Restoring
    the reference must update ONLY doors: rebuilding internals here
    would erase the fittings that resize has just restored.
    """
    if conj is None or _chapas.MARCA_CONJUNTO not in conj:
        return
    _portas.atualizar_do_conjunto(conj)
    if internos:
        _gavetas.atualizar_gavetas_do_conjunto(conj)
        _prateleiras.atualizar_do_conjunto(conj)


def redimensionar_conjunto(conj, ancoras=None):
    """Apply `conj_*` cabinet dimensions (see `redimensionar_grupo`).
    They describe the ENVELOPE including its frame: subtract the frame's
    constant additions for the body target; the frame follows the door."""
    alvo = (conj.conj_largura_mm, conj.conj_altura_mm, conj.conj_profundidade_mm)
    real = medir_conjunto(conj)
    mudam = [i for i in range(3) if abs(real[i]-alvo[i])>.01] if real else []
    acrescimo = _acrescimo_da_moldura(conj)
    if mudam:
        _portas.preparar_referencias_vaos(conj)
    if len(mudam)==1:
        eixo=(0,2,1)[mudam[0]]
        _formas._preparar_edicao(conj,('CAIXA',eixo),
                                 (ancoras or ('min','min','min'))[eixo])
        # Other fields may have followed an oblique part's projection
        # during reduction. Edit only the requested axis.
        base=medir_conjunto(conj)
        alvo=tuple(alvo[i] if i==mudam[0] else base[i] for i in range(3))
        if abs(alvo[mudam[0]]-base[mudam[0]])<.01:
            # Restoring the reference is not a new back or adjacency assembly:
            # restore the original fittings too.
            atualizar_sistemas_do_conjunto(conj, internos=False)
            sincronizar_medidas_conjunto(conj)
            _formas.concluir_edicao(conj)
            return
    redimensionar_grupo(_chapas_do_conjunto(conj),
                        tuple(max(20.0, a - e) for a, e in zip(alvo, acrescimo)),
                        ancoras)
    reposicionar_origem(conj)
    atualizar_sistemas_do_conjunto(conj)
    real=medir_conjunto(conj)
    if real and any(abs(a-b)>.01 for a,b in zip(real,alvo)):
        sincronizar_medidas_conjunto(conj)
    _formas.concluir_edicao(conj)


def redimensionar_orientado(conj, medidas_mm):
    """Apply the existing resize on cabinet axes, including rotated walls."""
    matriz = conj.matrix_world.copy()
    ocupado = _chapas._ocupado[0]
    try:
        _chapas._ocupado[0] = True
        escalas = [abs(s) * (-1 if conj.scale[i] < 0 else 1)
                   for i,s in enumerate(matriz.to_scale())]
        conj.matrix_world = Matrix.Diagonal((*escalas, 1.0))
        bpy.context.view_layer.update()
        try:
            conj.conj_largura_mm, conj.conj_altura_mm, conj.conj_profundidade_mm = medidas_mm
        finally:
            _chapas._ocupado[0] = ocupado
        redimensionar_conjunto(conj)
    finally:
        _chapas._ocupado[0] = True
        try:
            conj.matrix_world = matriz
            bpy.context.view_layer.update()
        finally:
            _chapas._ocupado[0] = ocupado


def _upd_conj_espessura(self, context):
    if _chapas._ocupado[0]:
        return
    val = self.conj_espessura_mm
    alvo = _chapas._espessura_livre(val)
    if abs(val - alvo) > 1e-6:
        _chapas._ocupado[0] = True
        try:
            self.conj_espessura_mm = alvo
        finally:
            _chapas._ocupado[0] = False
    aplicar_espessura_grupo(_chapas_do_conjunto(self), self.conj_espessura_mm)
    atualizar_sistemas_do_conjunto(self)
    reposicionar_origem(self)


def sincronizar_medidas_conjunto(conj):
    """Read the actual box into properties without triggering recalculation."""
    m = medir_conjunto(conj)
    if not m:
        return
    _chapas._ocupado[0] = True
    try:
        conj.conj_largura_mm, conj.conj_altura_mm, conj.conj_profundidade_mm = m
        chapas = _chapas_do_conjunto(conj)
        if chapas:
            conj.conj_espessura_mm = _espessura_de(chapas)
    finally:
        _chapas._ocupado[0] = False


class OBJECT_OT_detectar_adjacencia(Operator):
    """Record which panels touch each other; select all relevant panels."""
    bl_idname = "object.cabinet_detectar_adjacencia"
    bl_label = "Detect Adjacency"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sel = [o for o in context.selected_objects if o.type == 'MESH' and _chapas.MARCA_CHAPA in o]
        if len(sel) < 2:
            self.report({'WARNING'}, "Select at least 2 panels")
            return {'CANCELLED'}
        n = _chapas.detectar_adjacencia(sel)
        self.report({'INFO'}, "%d contact(s) stored on %d panel(s)" % (n, len(sel)))
        return {'FINISHED'}


class OBJECT_OT_sincronizar_conjunto(Operator):
    """Read actual part dimensions and update cabinet fields."""
    bl_idname = "object.cabinet_sincronizar"
    bl_label = "Read Current Dimensions"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        conj = context.object
        if conj is None or _chapas.MARCA_CONJUNTO not in conj:
            self.report({'WARNING'}, "Select the cabinet Empty")
            return {'CANCELLED'}
        sincronizar_medidas_conjunto(conj)
        return {'FINISHED'}


class OBJECT_OT_agrupar_conjunto(Operator):
    """Group selected panels into an assembly with an Empty parent."""
    bl_idname = "object.cabinet_agrupar"
    bl_label = "Group Assembly"
    bl_options = {'REGISTER', 'UNDO'}

    # User-defined group name: F3 runs in the viewport, so use a popup.
    nome: StringProperty(name="Group name", options={'SKIP_SAVE'})

    def _selecao(self, context):
        return [o for o in context.selected_objects
                if o.type == 'MESH' and _chapas.MARCA_CHAPA in o]

    def invoke(self, context, event):
        sel = self._selecao(context)
        if not sel:
            return self.execute(context)
        if not self.nome:
            self.nome = _nome_sugerido_grupo(sel)
        return context.window_manager.invoke_props_dialog(self, width=320)

    def execute(self, context):
        sel = self._selecao(context)
        if not sel:
            self.report({'WARNING'}, "No panel selected")
            return {'CANCELLED'}
        conj = agrupar_chapas(context, sel, self.nome)
        self.report({'INFO'}, "%s: %d panel(s) + adjacency detected"
                    % (conj.name, len(sel)))
        return {'FINISHED'}


# Each cabinet is a named GROUP: its own Collection shares the parent
# Empty's name and contains panels, the door group ("Porta Dupla", etc.)
# and hardware. Mark that Collection so only it follows renaming
# and disappears when the group is removed.
MARCA_COLECAO_MODULO = "eh_colecao_modulo"


def _nome_sugerido_grupo(chapas):
    """"Armario LxAxP" in mm on world axes, as already measured by the box."""
    pts = [p for o in chapas for p in _chapas._cantos(o)]
    if not pts:
        return "Cabinet"
    medida = [round((max(p[i] for p in pts) - min(p[i] for p in pts)) * 1000)
              for i in range(3)]
    return "Cabinet %dx%dx%d" % (medida[0], medida[2], medida[1])


def _mover_para_colecao(obj, colecao):
    """Move the object and its children exclusively into `colecao`."""
    for o in [obj, *obj.children_recursive]:
        if colecao not in o.users_collection:
            colecao.objects.link(o)
        for c in list(o.users_collection):
            if c != colecao:
                c.objects.unlink(o)


def _nome_livre(nome, ignorar=()):
    """Find `nome` (or "nome.001", etc.) free as BOTH object and Collection.
    Their name spaces are independent; the group needs the SAME name in both."""
    candidato, n = nome[:59], 0
    while any(d is not None and d not in ignorar
              for d in (bpy.data.objects.get(candidato),
                        bpy.data.collections.get(candidato))):
        n += 1
        candidato = '%s.%03d' % (nome[:59], n)
    return candidato


def _colecao_do_modulo(conj):
    if conj is None:
        return None
    return next((c for c in conj.users_collection
                 if c.get(MARCA_COLECAO_MODULO)), None)


def _colecao_de_organizacao(colecao):
    """Append preserves the native tag, including in legacy presets.

    The asset's containing folder differs from the assembly Collection;
    it need not acquire the assembly's identity to be removed when empty.
    """
    asset = colecao.asset_data
    return (colecao.library is None and colecao.override_library is None
            and (bool(colecao.get(MARCA_COLECAO_MODULO))
                 or (asset is not None and asset.tags.get('chapa-g3') is not None)))


def limpar_organizacao_vazia():
    """Native Delete can leave hidden assembly Empties behind.

    Only known groups without surviving parts are residue; an ordinary
    user Empty preserves its assembly and folder.
    """
    marcas = (_chapas.MARCA_CONJUNTO, _chapas.MARCA_PORTAS,
              _gavetas.MARCA_GRUPO, _gavetas.MARCA_GAVETA,
              _prateleiras.MARCA_GRUPO, _divisorias.MARCA_GRUPO)

    def organizacao(o):
        return (o.type == 'EMPTY' and o.library is None
                and o.override_library is None and any(m in o for m in marcas))

    candidatos = {o.name for o in bpy.data.objects
                  if _chapas.MARCA_CONJUNTO in o and organizacao(o)}
    # If Delete removed the parent too, subgroups can remain in the folder.
    # An empty shelf group inside a live cabinet remains editable.
    for c in bpy.data.collections:
        if (_colecao_de_organizacao(c)
                and all(organizacao(o) for o in c.all_objects)):
            candidatos.update(o.name for o in c.all_objects)
    for nome in candidatos:
        modulo = bpy.data.objects.get(nome)
        if modulo is None:
            continue
        familia = list(modulo.children_recursive)
        if all(organizacao(o) for o in familia):
            for o in reversed(familia):
                bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.objects.remove(modulo, do_unlink=True)
    # Work from the innermost folder outward; never remove ordinary folders.
    while True:
        vazias = [c for c in bpy.data.collections
                  if _colecao_de_organizacao(c) and not c.all_objects
                  and not c.children]
        if not vazias:
            break
        for c in vazias:
            bpy.data.collections.remove(c)


def _garantir_colecao_modulo(cena, conj):
    """Normalize a legacy assembly before inserting a part or room.

    An exclusive preset Collection may have lost only its marker.
    A shared folder must not become a cabinet or take its other objects along.
    """
    colecao = _colecao_do_modulo(conj)
    if colecao is not None:
        return colecao
    familia = {conj, *conj.children_recursive}
    colecao = next((c for c in conj.users_collection
                    if c.name == conj.name and not c.is_embedded_data
                    and not c.get('eh_colecao_comodo')
                    and all(o in familia for o in c.all_objects)), None)
    if colecao is None:
        nome = _nome_livre(conj.name, ignorar=(conj,))
        if nome != conj.name:
            nomear_grupo(conj, nome)
        colecao = bpy.data.collections.new(conj.name)
        cena.collection.children.link(colecao)
    colecao[MARCA_COLECAO_MODULO] = 1
    _mover_para_colecao(conj, colecao)
    return colecao


def nomear_grupo(conj, nome):
    """Rename the Empty, Collection and door/drawer links storing its name."""
    nome = (nome or '').strip()
    if conj is None or _chapas.MARCA_CONJUNTO not in conj or not nome:
        return False
    antigo = conj.name
    colecao = _colecao_do_modulo(conj)
    nome = _nome_livre(nome, ignorar=(conj, colecao))
    conj.name = nome
    if colecao is not None:
        colecao.name = nome
    for o in bpy.data.objects:
        if _chapas.MARCA_PORTAS in o and o.get(_portas.CHAVE_MODULO_PORTA) == antigo:
            o[_portas.CHAVE_MODULO_PORTA] = conj.name
    for grupo in _gavetas.grupos_do_modulo(conj):
        grupo[_gavetas.CHAVE_MODULO] = conj.name
    return True


def agrupar_chapas(context, sel, nome=''):
    """Create an assembly Empty at panel XY center and Z base, reparenting
    panels without movement into a same-name Collection.
    Return the assembly, already active."""
    pts = []
    for o in sel:
        pts.extend(_chapas._cantos(o))
    cx = (min(p.x for p in pts) + max(p.x for p in pts)) / 2
    cy = (min(p.y for p in pts) + max(p.y for p in pts)) / 2
    cz = min(p.z for p in pts)

    nome = _nome_livre((nome or '').strip() or _nome_sugerido_grupo(sel))
    colecao = bpy.data.collections.new(nome)
    colecao[MARCA_COLECAO_MODULO] = 1
    context.scene.collection.children.link(colecao)
    conj = bpy.data.objects.new(nome, None)
    colecao.objects.link(conj)
    conj.location = (cx, cy, cz)
    conj[_chapas.MARCA_CONJUNTO] = 1
    _chapas._ocultar_empty(conj)
    context.view_layer.update()

    for o in sel:
        mw = o.matrix_world.copy()
        o.parent = conj
        o.matrix_parent_inverse = conj.matrix_world.inverted()
        o.matrix_world = mw
        _mover_para_colecao(o, colecao)

    # Adjacency is required for an assembly without gaps.
    _chapas.detectar_adjacencia(sel)
    sincronizar_medidas_conjunto(conj)

    for o in context.selected_objects:
        o.select_set(False)
    conj.select_set(True)
    context.view_layer.objects.active = conj
    return conj


def absorver_conjuntos(no_timer=False):
    """Convert an assembly Empty's applied scale into actual child-panel
    dimensions, resetting the Empty's scale."""
    for conj in list(bpy.data.objects):
        if conj.type != 'EMPTY' or _chapas.MARCA_CONJUNTO not in conj:
            continue
        sx, sy, sz = conj.scale
        # Unit-magnitude reflection belongs to native Mirror, not resize.
        if all(abs(abs(s)-1) < 1e-6 for s in (sx,sy,sz)):
            continue
        sinais = tuple(-1.0 if s < 0 else 1.0 for s in (sx,sy,sz))
        sistemas = _gavetas.grupos_do_modulo(conj) or _prateleiras.grupos_do_modulo(conj)
        if sistemas and min(abs(sx),abs(sy),abs(sz)) > 0:
            # The handler must not update the depsgraph or refit systems.
            # The existing timer completes through the SAME dimension resize.
            if not no_timer:
                continue
            # Nominal `_cantos` discards thickness scale: during S, measure
            # the NATIVE box before removing that scale.
            pontos = [o.matrix_world @ Vector(v) for o in _chapas_do_conjunto(conj)
                      for v in o.bound_box]
            lo = Vector(tuple(min(p[k] for p in pontos) for k in range(3)))
            hi = Vector(tuple(max(p[k] for p in pontos) for k in range(3)))
            # Measuring on cabinet axes avoids inflating the projected box
            # when R precedes S or Mirror.
            inversa = conj.matrix_world.to_3x3().normalized().inverted()
            locais = [inversa @ p for p in pontos]
            alvo = tuple((max(p[k] for p in locais)-min(p[k] for p in locais))*1000
                         for k in (0,2,1))
            caixa = (lo,hi)
            ocupado = _chapas._ocupado[0]
            _chapas._ocupado[0] = True
            try:
                conj.scale = sinais
                bpy.context.view_layer.update()
                conj.conj_largura_mm,conj.conj_altura_mm,conj.conj_profundidade_mm = alvo
            finally:
                _chapas._ocupado[0] = ocupado
            redimensionar_orientado(conj, alvo)
            atual = _caixa_de(_chapas_do_conjunto(conj))
            if caixa and atual:
                mundo = conj.matrix_world.copy()
                mundo.translation += Vector(caixa[0])-Vector(atual[0])
                conj.matrix_world = mundo
                bpy.context.view_layer.update()
            continue
        filhos = [o for o in bpy.data.objects if o.parent == conj]
        mundos = {o.name: o.matrix_world.copy() for o in filhos}
        # Compute the Empty's unscaled world matrix here: after resetting scale,
        # its matrix_world changes only at the next update. Setting children's
        # `o.matrix_world = ...` used the still-scaled parent, returning panels
        # to their old size (S on a cabinet did nothing).
        # view_layer.update is unavailable here because this runs in the handler.
        if min(sx,sy,sz) < 0:
            if min(abs(sx),abs(sy),abs(sz)) < 1e-9:
                continue
            pai_novo = conj.matrix_world @ Matrix.Diagonal((1/abs(sx),1/abs(sy),1/abs(sz),1))
        else:
            local, rotacao, _escala = conj.matrix_world.decompose()
            pai_novo = Matrix.LocRotScale(local, rotacao, Vector((1, 1, 1)))
        _chapas._ocupado[0] = True
        try:
            conj.scale = sinais
            for o in filhos:
                o.matrix_basis = ((pai_novo @ o.matrix_parent_inverse)
                                  .inverted() @ mundos[o.name])
        finally:
            _chapas._ocupado[0] = False
        try:
            sincronizar_medidas_conjunto(conj)
        except Exception as e:
            print("[Archy Builder] synchronize:", e)


def _grupo_ativo(context):
    o = context.object
    if o is None:
        return []
    if _chapas.MARCA_CONJUNTO in o:
        return _chapas_do_conjunto(o)
    return grupo_de(o)


def sincronizar_grupo(context):
    """Read the group's actual box into scene fields."""
    chapas = _grupo_ativo(context)
    cx = _caixa_de(chapas)
    if cx is None:
        return
    lo, hi = cx
    s = context.scene
    _chapas._ocupado[0] = True
    try:
        s.grupo_largura_mm = (hi[0]-lo[0]) * 1000.0
        s.grupo_altura_mm = (hi[2]-lo[2]) * 1000.0
        s.grupo_profundidade_mm = (hi[1]-lo[1]) * 1000.0
        s.grupo_espessura_mm = _espessura_de(chapas)
    finally:
        _chapas._ocupado[0] = False


def _sincronizar_medidas_ativas():
    """Replace the old Synchronize buttons: active cabinet/group fields
    reflect the ACTUAL box after a user moves or scales a loose part.

    Run only in the TIMER, never the depsgraph handler: `_caixa_de` calls
    `view_layer.update()`, which would reenter the handler. Write only
    changed values; writing the same value still tags the depsgraph.
    """
    context = bpy.context
    obj = getattr(context, 'object', None)
    if obj is None or getattr(obj, 'mode', 'OBJECT') != 'OBJECT':
        return
    try:
        if _chapas.MARCA_CONJUNTO in obj:
            medidas = medir_conjunto(obj)
            if not medidas:
                return
            chapas = _chapas_do_conjunto(obj)
            real = tuple(medidas) + (
                (_espessura_de(chapas),) if chapas else ())
            campos = (obj.conj_largura_mm, obj.conj_altura_mm,
                      obj.conj_profundidade_mm, obj.conj_espessura_mm)
            if any(abs(a - b) > 0.01 for a, b in zip(real, campos)):
                sincronizar_medidas_conjunto(obj)
        elif _chapas.MARCA_CHAPA in obj and _gaveta._modo_chapa(context, obj) == 'GRUPO':
            chapas = _grupo_ativo(context)
            caixa = _caixa_de(chapas)
            if caixa is None:
                return
            lo, hi = caixa
            s = context.scene
            real = ((hi[0] - lo[0]) * 1000.0, (hi[2] - lo[2]) * 1000.0,
                    (hi[1] - lo[1]) * 1000.0, _espessura_de(chapas))
            campos = (s.grupo_largura_mm, s.grupo_altura_mm,
                      s.grupo_profundidade_mm, s.grupo_espessura_mm)
            if any(abs(a - b) > 0.01 for a, b in zip(real, campos)):
                sincronizar_grupo(context)
    except Exception as e:
        print("[Archy Builder] synchronize dimensions:", e)


def _upd_grupo_dim(self, context):
    if _chapas._ocupado[0]:
        return
    redimensionar_grupo_da_cena(self, context)


def redimensionar_grupo_da_cena(s, context, ancoras=None):
    """Apply scene `grupo_*` dimensions to the active group."""
    chapas = _grupo_ativo(context)
    if not chapas:
        return
    redimensionar_grupo(chapas, (s.grupo_largura_mm, s.grupo_altura_mm,
                                 s.grupo_profundidade_mm), ancoras)
    pai = chapas[0].parent if chapas else None
    if pai is not None and _chapas.MARCA_CONJUNTO in pai:
        reposicionar_origem(pai)
        sincronizar_medidas_conjunto(pai)
        atualizar_sistemas_do_conjunto(pai)


def _upd_grupo_espessura(self, context):
    if _chapas._ocupado[0]:
        return
    val = self.grupo_espessura_mm
    alvo = _chapas._espessura_livre(val)
    if abs(val - alvo) > 1e-6:
        _chapas._ocupado[0] = True
        try:
            self.grupo_espessura_mm = alvo
        finally:
            _chapas._ocupado[0] = False
    chapas = _grupo_ativo(context)
    if chapas:
        aplicar_espessura_grupo(chapas, alvo)
        pai = chapas[0].parent
        if pai is not None and _chapas.MARCA_CONJUNTO in pai:
            reposicionar_origem(pai)
            sincronizar_medidas_conjunto(pai)
            atualizar_sistemas_do_conjunto(pai)


class OBJECT_OT_sincronizar_grupo(Operator):
    """Read actual group dimensions and update the fields."""
    bl_idname = "object.cabinet_sincronizar_grupo"
    bl_label = "Read Group Dimensions"

    def execute(self, context):
        sincronizar_grupo(context)
        return {'FINISHED'}
