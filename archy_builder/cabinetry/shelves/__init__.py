"""Internal shelves grouped in a cabinet opening. Create like drawers
with two diagonal clicks (upper left/lower right), then scroll for
count. Depth extends to the back; front clearance is SETBACK. Edit
count, thickness and group/per-shelf spacing on the dedicated tab.

Use the drawer-group frame: parented to the cabinet, origin at opening
LOWER LEFT on the front plane, X=width, Z=height, Y=INWARD. All in mm.

EQUAL spacing divides the opening into n+1 equal gaps. FREE stores
the gap BELOW each shelf; the top gap is the remainder. Changing ONE
gap moves only its upper shelf; the next gap yields and others stay put.
"""

import bpy
import bmesh
import hashlib
from array import array
from mathutils import Matrix, Vector
from bpy.types import Operator

# The assistant inherits from drawers at LOAD time; __init__ loads them first.
from ... import gavetas as _gavetas

# Used only at runtime (circular imports): __init__ binds these
# aliases after loading all modules (`_ligar_modulos`).
_chapas = _modulos = _portas = _hud = _eventos = _gaveta_eventos = _selecao = _divisorias = None

# Markers saved in .blend files; renaming breaks existing files.
MARCA_GRUPO = 'eh_grupo_prateleiras'
MARCA_PRATELEIRA = 'eh_prateleira'
CHAVE_MODULO = 'prateleiras_modulo'
CHAVE_PARAMETROS = 'prateleiras_parametros'
CHAVE_REFERENCIA = 'prateleiras_referencia'
CHAVE_MARGENS = 'prateleiras_margens_mm'  # Cabinet left, right, bottom, top, front.
CHAVE_VAO = 'prateleiras_vao_mm'          # Width, height (without a cabinet).
CHAVE_INDICE = 'prateleira_indice'
CHAVE_DETALHAMENTO = 'prateleira_detalhamento_uid'
CHAVE_ENCAIXE = 'prateleiras_encaixe'

PARAMETROS_PADRAO = {
    'quantidade': 1,
    'espessura_mm': 18.0,
    'profundidade_mm': 500.0,      # Opening front plane to shelf rear.
    'recuo_mm': 0.0,               # Shelf-front inward setback.
    'folga_lateral_mm': 0.0,       # Each side, adjustable at the pin.
    'espacamento': 'IGUAL',
    'vaos_mm': [],                 # FREE: gap BELOW each shelf.
}
OPCOES_ESPACAMENTO = (('IGUAL', "Equal"), ('LIVRE', "Free"))
MAXIMO_PRATELEIRAS = 20
MENOR_LADO_MM = 50.0
TOL_MM = 0.01


# ------------------------------------------------------------ lookup
def grupo_de(obj):
    """Shelf group for `obj`, whether the group itself or a shelf."""
    while obj is not None:
        if MARCA_GRUPO in obj:
            return obj
        obj = obj.parent
    return None


def prateleiras_do_grupo(grupo):
    return sorted((o for o in grupo.children if MARCA_PRATELEIRA in o),
                  key=lambda o: int(o.get(CHAVE_INDICE, 0)))


def grupos_do_modulo(conj):
    return [o for o in conj.children if MARCA_GRUPO in o]


def modulo_do_grupo(grupo):
    pai = grupo.parent
    while pai is not None:
        if _chapas.MARCA_CONJUNTO in pai:
            return pai
        pai = pai.parent
    modulo = bpy.data.objects.get(grupo.get(CHAVE_MODULO, ''))
    if modulo is not None and _chapas.MARCA_CONJUNTO in modulo:
        return modulo
    return None


def _como_dict(valor):
    return valor.to_dict() if hasattr(valor, 'to_dict') else dict(valor or {})


def parametros(grupo):
    p = dict(PARAMETROS_PADRAO)
    p.update(_como_dict(grupo.get(CHAVE_PARAMETROS)))
    p['vaos_mm'] = [float(v) for v in (p.get('vaos_mm') or ())]
    return p


CAMPOS_INDIVIDUAIS = ('espessura_mm', 'profundidade_mm', 'recuo_mm',
                      'folga_lateral_mm', 'largura_mm')
_referencia_pendente = [None]
_quantidade_previa = [None]  # Value displayed during drag without assembling meshes.
_edicao = [None]  # Names/signatures only: undo frees scene data.


def parametros_individuais(p, indice):
    resultado = dict(p)
    individuais = p.get('individuais') or ()
    if indice < len(individuais):
        resultado.update(individuais[indice])
    return resultado


def individual_ativo(context, grupo):
    obj = context.view_layer.objects.active
    if (obj is None or MARCA_PRATELEIRA not in obj or obj.parent != grupo
            or not obj.select_get()):
        return None
    # An explicitly selected Empty establishes global scope.
    if any(o.type == 'EMPTY' and (o == grupo or o == modulo_do_grupo(grupo))
           for o in context.selected_objects):
        return None
    estado = edicao_atual(context)
    if estado and grupo.name in estado.get('globais', ()):
        return None
    if sum(MARCA_PRATELEIRA in o for o in context.selected_objects) != 1:
        return None
    return obj


def detalhamento(grupo, fonte):
    """Local span between external supports; copies store only a UID.

    Recalculate limits from current gaps rather than a stored box that
    would become stale after support movement, undo or cabinet resize.
    """
    atuais = prateleiras_do_grupo(grupo)
    uid = fonte.get(CHAVE_DETALHAMENTO)
    unidades = ([o for o in atuais if o.get(CHAVE_DETALHAMENTO) == uid]
                if uid else [fonte])
    indices = [int(o[CHAVE_INDICE]) for o in unidades]
    primeiro, ultimo = min(indices), max(indices)
    if indices != list(range(primeiro, ultimo + 1)):
        raise ValueError("Another shelf separates the subdivisions")
    p = parametros(grupo)
    largura, altura, _m = vao(grupo)
    dados = calcular(largura, altura, p)
    caixas = dados['prateleiras']
    return dict(unidades=unidades, quantidade=len(unidades), primeiro=primeiro, ultimo=ultimo,
                baixo=caixas[primeiro - 1][5] if primeiro else 0.,
                cima=caixas[ultimo + 1][4] if ultimo + 1 < len(caixas) else altura,
                vaos=dados['vaos'][primeiro:ultimo + 2], caixas=caixas[primeiro:ultimo + 1])


def editar_quantidade_local(context, grupo, fonte, quantidade, redistribuir=False):
    """Subdivide only the unit's local span; never rebuild the rest."""
    if context.mode != 'OBJECT' or _eventos._desfazendo[0]:
        return "Finish editing before subdividing the shelf"
    _sincronizar_disposicao(grupo)
    antes = parametros(grupo)
    atuais = prateleiras_do_grupo(grupo)
    try:
        detalhe = detalhamento(grupo, fonte)
        antigas = detalhe['unidades']
        limite = MAXIMO_PRATELEIRAS - len(atuais) + len(antigas)
        quantidade = max(0, min(limite, int(quantidade)))
        if quantidade == len(antigas) and not redistribuir:
            return None
        # On reduction, retain the unit chosen by the user.
        manter = antigas[:quantidade]
        if quantidade and fonte not in manter:
            manter[-1] = fonte
            manter.sort(key=lambda o: int(o[CHAVE_INDICE]))
        modelo = parametros_individuais(antes, int(fonte[CHAVE_INDICE]))
        individuais = [dict(parametros_individuais(antes, int(o[CHAVE_INDICE]))) for o in manter]
        individuais += [dict(modelo) for _ in range(quantidade - len(manter))]
        individuais = [{k: v for k, v in p.items() if k in (*CAMPOS_INDIVIDUAIS, 'x_mm')}
                       for p in individuais]
        local = dict(antes, quantidade=quantidade, espacamento='IGUAL', vaos_mm=[],
                     individuais=individuais)
        dados = calcular(vao(grupo)[0], detalhe['cima'] - detalhe['baixo'], local)
    except ValueError as erro:
        return str(erro)
    criadas = []
    try:
        for i in range(quantidade - len(manter)):
            criadas.append(_copiar_prateleira(grupo, len(atuais) + i, fonte))
    except Exception:
        for obj in criadas:
            _gavetas._remover(obj)
        raise
    unidades = manter + criadas
    uid = fonte.get(CHAVE_DETALHAMENTO) or _chapas._garantir_uid(fonte)
    bpy.context.view_layer.update()
    for obj in criadas:
        obj.select_set(False)
    inversa = grupo.matrix_world.inverted_safe()
    for obj, caixa in zip(unidades, dados['prateleiras']):
        base = min((inversa @ obj.matrix_world @ Vector(c)).z for c in obj.bound_box) * 1000
        delta = grupo.matrix_world.to_3x3() @ Vector((0, 0, (detalhe['baixo'] + caixa[4] - base) / 1000))
        mundo = obj.matrix_world.copy()
        mundo.translation += delta
        obj.matrix_world = mundo
        obj[CHAVE_DETALHAMENTO] = uid
    inicio, fim = detalhe['primeiro'], detalhe['ultimo'] + 1
    novas = atuais[:inicio] + unidades + atuais[fim:]
    ajustes = [dict(v) for v in antes.get('individuais') or ()]
    ajustes += [{} for _ in range(len(atuais) - len(ajustes))]
    p = dict(antes, quantidade=len(novas), individuais=ajustes[:inicio] + individuais + ajustes[fim:])
    grupo[CHAVE_PARAMETROS] = p
    for i, obj in enumerate(novas):
        obj[CHAVE_INDICE] = i
    for obj in antigas:
        if obj not in unidades:
            _gavetas._remover(obj)
    bpy.context.view_layer.update()
    _sincronizar_disposicao(grupo)
    if CHAVE_ENCAIXE in grupo:
        del grupo[CHAVE_ENCAIXE]
    if quantidade == 0:
        selecionar(context, grupo, 'GRUPO')
    _hud._hover_hud.clear()
    return None


def preparar_subdivisao_vao(grupo, indice):
    _sincronizar_disposicao(grupo)
    p = parametros(grupo); atuais = prateleiras_do_grupo(grupo)
    largura, altura, _m = vao(grupo)
    caixas = calcular(largura, altura, p)['prateleiras']
    if not 0 <= indice <= len(caixas):
        raise ValueError("The opening no longer exists")
    fonte = atuais[min(indice, len(atuais)-1)] if atuais else None
    modelo = parametros_individuais(p, int(fonte[CHAVE_INDICE])) if fonte else dict(p)
    modelo = {k:v for k,v in modelo.items() if k in (*CAMPOS_INDIVIDUAIS, 'x_mm')}
    return dict(grupo=grupo.name, baixo=caixas[indice-1][5] if indice else 0.,
        cima=caixas[indice][4] if indice < len(caixas) else altura,
        p=_portas._copiar_parametros(p), originais=[o.name for o in atuais],
        fonte=fonte.name if fonte else '', novas=[], quantidade=0,
        modelo=modelo,
        encaixe=_portas._copiar_parametros(grupo.get(CHAVE_ENCAIXE)))


def subdividir_vao(context, grupo, estado, quantidade):
    """Insert only into empty space; supports/other shelves retain Mesh and pose."""
    if context.mode != 'OBJECT' or _eventos._desfazendo[0]:
        raise ValueError("Finish editing before subdividing the opening")
    if estado['grupo'] != grupo.name or any(n not in bpy.data.objects for n in estado['originais']):
        raise ValueError("The opening structure changed")
    quantidade = int(quantidade)
    if not 0 <= quantidade <= MAXIMO_PRATELEIRAS-len(estado['originais']):
        raise ValueError("Shelf count outside the allowed range")
    modelo = estado['modelo']
    local = dict(estado['p'], quantidade=quantidade, espacamento='IGUAL', vaos_mm=[],
                 individuais=[dict(modelo) for _ in range(quantidade)])
    dados = calcular(vao(grupo)[0], estado['cima']-estado['baixo'], local)
    novas = [bpy.data.objects[n] for n in estado['novas'] if n in bpy.data.objects]
    fonte = bpy.data.objects.get(estado['fonte'])
    criadas = []
    try:
        for i in range(len(novas), quantidade):
            criadas.append(_copiar_prateleira(grupo, i, fonte) if fonte else
                _nova_prateleira(grupo, i, _material_do_modulo(modulo_do_grupo(grupo))))
    except Exception:
        for obj in criadas:
            _gavetas._remover(obj)
        raise
    for obj in novas[quantidade:]:
        _gavetas._remover(obj)
    novas = novas[:quantidade] + criadas
    if quantidade == 0:
        cancelar_subdivisao_vao(grupo, estado)
        estado.update(novas=[], quantidade=0)
        return
    context.view_layer.update()
    inv = grupo.matrix_world.inverted_safe()
    for obj, caixa in zip(novas, dados['prateleiras']):
        baixo = estado['baixo'] + caixa[4]
        if fonte:
            base = min((inv @ obj.matrix_world @ Vector(c)).z for c in obj.bound_box) * 1000
            mundo = obj.matrix_world.copy()
            mundo.translation += grupo.matrix_world.to_3x3() @ Vector((0,0,(baixo-base)/1000))
            obj.matrix_world = mundo
        else:
            _vestir(obj, (*caixa[:4], baixo, estado['baixo']+caixa[5]))
        obj.select_set(False)
    context.view_layer.update()
    originais = [bpy.data.objects[n] for n in estado['originais']]
    todos = sorted(originais+novas, key=lambda o: min((inv @ o.matrix_world @ Vector(c)).z for c in o.bound_box))
    antigos = estado['p'].get('individuais') or ()
    ajustes = {n: dict(antigos[i]) if i < len(antigos) else {} for i,n in enumerate(estado['originais'])}
    grupo[CHAVE_PARAMETROS] = dict(estado['p'], quantidade=len(todos),
        individuais=[ajustes.get(o.name, dict(modelo)) for o in todos])
    for i, obj in enumerate(todos):
        obj[CHAVE_INDICE] = i
    _sincronizar_disposicao(grupo)
    estado.update(novas=[o.name for o in novas], quantidade=quantidade)
    _hud._hover_hud.clear()


def cancelar_subdivisao_vao(grupo, estado):
    for nome in estado['novas']:
        obj = bpy.data.objects.get(nome)
        if obj is not None:
            _gavetas._remover(obj)
    for i, nome in enumerate(estado['originais']):
        obj = bpy.data.objects.get(nome)
        if obj is not None:
            obj[CHAVE_INDICE] = i
    grupo[CHAVE_PARAMETROS] = estado['p']
    if estado['encaixe'] is not None:
        grupo[CHAVE_ENCAIXE] = estado['encaixe']
    elif CHAVE_ENCAIXE in grupo:
        del grupo[CHAVE_ENCAIXE]
    bpy.context.view_layer.update()


def _digital(obj):
    """Compare only on Tab entry/exit or addition, never redraw."""
    h = hashlib.sha1()
    for itens, campo, tipo, tamanho in ((obj.data.vertices, 'co', 'f', 3),
                                       (obj.data.edges, 'vertices', 'i', 2),
                                       (obj.data.loops, 'vertex_index', 'i', 1),
                                       (obj.data.polygons, 'loop_total', 'i', 1)):
        valores = array(tipo, [0]) * (tamanho * len(itens))
        itens.foreach_get(campo, valores)
        h.update(valores.tobytes())
    p = parametros_individuais(parametros(obj.parent), int(obj[CHAVE_INDICE]))
    h.update(repr(tuple(float(p[k]) for k in CAMPOS_INDIVIDUAIS if k != 'largura_mm')).encode())
    # Groove/cutout configuration also distinguishes templates.
    h.update(repr(sorted((k, str(obj[k])) for k in obj.keys()
                         if k.startswith('chapa_') and k not in
                         {'chapa_uid', 'chapa_edicao'})).encode())
    h.update(repr([slot.material.name if slot.material else ''
                   for slot in obj.material_slots]).encode())
    for modificador in obj.modifiers:
        valores = []
        for prop in modificador.bl_rna.properties:
            if prop.identifier in {'name', 'rna_type'} or prop.is_readonly:
                continue
            if prop.type in {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'}:
                valor = getattr(modificador, prop.identifier)
                valores.append((prop.identifier, tuple(valor) if prop.is_array else valor))
        h.update(repr((modificador.type, valores)).encode())
    return h.digest()


def _gravar_individual(p, indice, valores):
    lista = [dict(v) for v in (p.get('individuais') or ())]
    while len(lista) <= indice:
        lista.append({})
    lista[indice].update(valores)
    p['individuais'] = lista


def _copiar_prateleira(grupo, indice, fonte):
    obj = fonte.copy()
    obj.data = fonte.data.copy()
    obj.name = "Shelf %d" % (indice + 1)
    _gavetas._colecao(grupo).objects.link(obj)
    obj.parent = grupo
    for chave in list(obj.keys()):
        if chave.startswith('adj_') or chave in ('chapa_uid', 'chapa_edicao', CHAVE_DETALHAMENTO):
            del obj[chave]
    _chapas._garantir_uid(obj)
    obj[CHAVE_INDICE] = indice
    return obj


def quantas_no_modulo(conj):
    """This system's cabinet shelves, counted by estimates."""
    return sum(len(prateleiras_do_grupo(g)) for g in grupos_do_modulo(conj))


def sincronizar_exclusoes(grupo):
    """Absorb deletions/unlinks before editing parameters or rebuilding."""
    return _sincronizar_disposicao(grupo, somente_exclusoes=True)


def _sincronizar_disposicao(grupo, somente_exclusoes=False):
    """Read NATIVE boxes in opening coordinates without moving wood.

    Old indices identify surviving choices; compacting before copying
    would assign a deleted shelf's model to another shelf.
    """
    if (_eventos._desfazendo[0] or bpy.context.mode != 'OBJECT'):
        return False
    atuais = prateleiras_do_grupo(grupo)
    p = parametros(grupo)
    indices = [int(o.get(CHAVE_INDICE, 0)) for o in atuais]
    mesmos_indices = int(p['quantidade']) == len(atuais) and indices == list(range(len(atuais)))
    if somente_exclusoes and mesmos_indices:
        return False
    inversa = grupo.matrix_world.inverted_safe()
    disposicao = []
    for obj, indice in zip(atuais, indices):
        matriz = inversa @ obj.matrix_world
        zs = [(matriz @ Vector(c)).z * 1000.0 for c in obj.bound_box]
        disposicao.append((obj, indice, min(zs), max(zs)))
    # G can cross another unit: E fields stay bottom-to-top, while
    # individual choices follow the SAME panel.
    disposicao.sort(key=lambda item: item[2])
    individuais, g, topo = [], [], 0.0
    for obj, indice, baixo, cima in disposicao:
        individuais.append(dict((p.get('individuais') or ())[indice])
                            if indice < len(p.get('individuais') or ()) else {})
        g.append(baixo - topo)
        topo = cima
    try:
        anteriores = (list(p.get('vaos_mm') or ()) if p['espacamento'] == 'LIVRE'
                      else vaos(vao(grupo)[1], p)[:-1])
    except ValueError:
        anteriores = []
    if (mesmos_indices and [d[1] for d in disposicao] == indices
            and len(anteriores) == len(g)
            and all(abs(a - b) <= TOL_MM for a, b in zip(anteriores, g))):
        return False
    p.update(quantidade=len(atuais), espacamento='LIVRE', vaos_mm=g,
             individuais=individuais)
    grupo[CHAVE_PARAMETROS] = p
    for indice, (obj, _antigo, _baixo, _cima) in enumerate(disposicao):
        if obj.get(CHAVE_INDICE) != indice:
            obj[CHAVE_INDICE] = indice
    # Previous fitting must not resurrect old positions/settings.
    if CHAVE_ENCAIXE in grupo:
        del grupo[CHAVE_ENCAIXE]
    return True


def sincronizar_exclusoes_da_cena():
    """Deletions AND positions, only in the stable timer after Tab absorption."""
    if (_eventos._desfazendo[0] or _chapas._ocupado[0]
            or bpy.context.mode != 'OBJECT'):
        return
    mudou = False
    for grupo in bpy.data.objects:
        if MARCA_GRUPO in grupo:
            if _divisorias.CHAVE_BLOCAGEM not in grupo:
                _divisorias.garantir_blocagem(grupo)
                mudou = True
            mudou = _sincronizar_disposicao(grupo) or mudou
    if mudou:
        _eventos._redesenhar_viewports(bpy.context)


# ------------------------------------------------------------ calculation
def vaos(altura, p):
    """n+1 gaps in mm, bottom to top: the gap below each shelf, then
    the gap above the highest shelf."""
    n = max(0, int(p['quantidade']))
    e = float(p['espessura_mm'])
    livre = altura - sum(float(parametros_individuais(p, i)['espessura_mm'])
                         for i in range(n))
    if livre < -TOL_MM:
        raise ValueError("%d shelves of %g mm do not fit in %d mm"
                         % (n, e, round(altura)))
    gravados = [float(v) for v in (p.get('vaos_mm') or ())]
    if p.get('espacamento') == 'LIVRE' and len(gravados) == n:
        topo = livre - sum(gravados)
        if topo < -TOL_MM:
            raise ValueError("Shelves exceed the opening top by %d mm"
                             % round(-topo))
        if gravados and min(gravados) < -TOL_MM:
            raise ValueError("Negative gap between shelves")
        return gravados + [max(0.0, topo)]
    return [max(0.0, livre) / (n + 1)] * (n + 1)


def calcular(largura, altura, p):
    """Return {'prateleiras': [(x0, x1, y0, y1, z0, z1)], 'vaos': [n + 1]}."""
    g = vaos(altura, p)
    caixas, z = [], 0.0
    for k in range(len(g) - 1):
        unidade = parametros_individuais(p, k)
        e = float(unidade['espessura_mm'])
        folga = float(unidade['folga_lateral_mm'])
        l = float(unidade.get('largura_mm', largura - 2 * folga))
        y0, y1 = float(unidade['recuo_mm']), float(unidade['profundidade_mm'])
        if e <= 0:
            raise ValueError("Shelf thickness must be greater than zero")
        if l < MENOR_LADO_MM or l > largura + TOL_MM:
            raise ValueError("Opening too narrow for a shelf (%d mm)" % round(largura))
        if y1 - y0 < MENOR_LADO_MM:
            raise ValueError("Shelf too shallow: %d mm" % round(y1 - y0))
        z += g[k]
        x0 = float(unidade.get('x_mm', (largura - l) / 2))
        if x0 < -TOL_MM or x0 + l > largura + TOL_MM:
            raise ValueError("The shelf exceeds the opening width")
        caixas.append((x0, x0 + l, y0, y1, z, z + e))
        z += e
    return {'prateleiras': caixas, 'vaos': g}


def mover_vao(altura, p, k, valor, de_baixo=False):
    """Bottom gaps (n) with gap `k` set to `valor`: move ONLY the upper shelf,
    or lower with `de_baixo` (Above for the chosen shelf). The top gap
    has only a lower shelf. Its other neighboring gap yields.
    Raise ValueError if that gap would be negative."""
    g = vaos(altura, p)
    n = len(g) - 1
    if not 0 <= k <= n or (de_baixo and k == 0):
        raise ValueError("Opening %d does not exist" % (k + 1))
    valor = max(0.0, float(valor))
    vizinho = k - 1 if de_baixo or k == n else k + 1
    g[vizinho] -= valor - g[k]
    g[k] = valor
    if g[vizinho] < -TOL_MM:
        raise ValueError("Does not fit: %d mm missing in opening %d"
                         % (round(-g[vizinho]), vizinho + 1))
    return g[:n]


# ------------------------------------------------------------ opening
def vao(grupo):
    """(width, height, group matrix in cabinet) for TODAY's opening:
    retain margins and let the opening follow the cabinet."""
    conj = modulo_do_grupo(grupo)
    if conj is None or _gavetas._limites(conj) is None:
        largura, altura = grupo.get(CHAVE_VAO) or (500.0, 300.0)
        return float(largura), float(altura), grupo.matrix_basis.copy()
    valores=grupo.get(CHAVE_REFERENCIA)
    ref=Matrix([valores[i:i+3] for i in (0,3,6)]) if valores else Matrix.Identity(3)
    lo, hi = _gavetas.limites_na_referencia(conj,ref)
    esq, dir_, baixo, cima, frente = list(grupo.get(CHAVE_MARGENS) or (0, 0, 0, 0, 0))
    origem = Vector((lo.x + esq, lo.y + frente, lo.z + baixo))
    return _divisorias.limitar_vao(grupo, hi.x - dir_ - origem.x,
        hi.z - cima - origem.z, ref.to_4x4() @ Matrix.Translation(origem / 1000.0))


def profundidade_ate_o_fundo(conj, ponto):
    """Front plane through world `ponto` to the cabinet BACK's front face,
    or cabinet rear without a back. Shelves must not enter the back groove."""
    lo, hi = _gavetas._limites(conj)
    inversa = conj.matrix_world.inverted()
    limite = hi.y
    for chapa in _modulos._chapas_do_conjunto(conj):
        if _chapas.MARCA_FUNDO in chapa:
            n=(inversa @ chapa.matrix_world).to_3x3().col[2].normalized()
            if abs(n.y)<.995:
                continue
            ys = [(inversa @ (chapa.matrix_world @ v.co)).y * 1000.0
                  for v in chapa.data.vertices]
            if ys:
                limite = min(limite, min(ys))
    return max(MENOR_LADO_MM, limite - _portas._local_no_modulo(conj, ponto).y)


# ------------------------------------------------------------ assembly
def _material_do_modulo(conj):
    for chapa in _modulos._estruturais(_modulos._chapas_do_conjunto(conj)):
        for slot in chapa.material_slots:
            if slot.material is not None:
                return slot.material
    return None


def _vestir(obj, caixa):
    """Fit the SAME panel `obj` to a group-space box in mm so isolated
    shelf selection survives editing."""
    matriz, (l, c, e) = _gavetas._matriz_da_caixa(caixa, 2)
    pose = (obj.matrix_parent_inverse != Matrix.Identity(4)
            or obj.matrix_basis != matriz)
    if pose:
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.matrix_basis = matriz
    mudou = not obj.data.vertices or any(abs(a - b) > .001 for a, b in zip(
        (obj.chapa_largura_mm, obj.chapa_comprimento_mm, obj.chapa_espessura_mm), (l, c, e)))
    if mudou:
        _chapas._ocupado[0] = True
        try:
            obj.chapa_largura_mm, obj.chapa_comprimento_mm = l, c
            obj.chapa_espessura_mm = e
            obj.chapa_auto = True
        finally:
            _chapas._ocupado[0] = False
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        _chapas.gerar_malha_chapa(obj)
    return pose or mudou


def _nova_prateleira(grupo, indice, material):
    nome = "Shelf %d" % (indice + 1)
    obj = bpy.data.objects.new(nome, bpy.data.meshes.new(nome))
    _gavetas._colecao(grupo).objects.link(obj)
    obj[_chapas.MARCA_CHAPA] = 1
    obj[MARCA_PRATELEIRA] = 1
    obj.parent = grupo
    if material is not None:
        _gavetas._pintar([obj], material)
    return obj


def montar(grupo, referencia=None):
    """Rebuild shelves from current parameters/opening using the SAME panels;
    remove surplus, create missing panels with existing materials.
    Raise ValueError without mutation if they cannot fit."""
    p = parametros(grupo)
    largura, altura, matriz = vao(grupo)
    dados = calcular(largura, altura, p)
    mudou = grupo.matrix_parent_inverse != Matrix.Identity(4)
    if mudou:
        grupo.matrix_parent_inverse = Matrix.Identity(4)
    conj = modulo_do_grupo(grupo)
    if conj is not None and grupo.matrix_basis != matriz:
        grupo.matrix_basis = matriz
        mudou = True
    if tuple(grupo.get(CHAVE_VAO, ())) != (largura, altura):
        grupo[CHAVE_VAO] = (largura, altura)
    atuais = prateleiras_do_grupo(grupo)
    mudou = mudou or len(atuais) < len(dados['prateleiras'])
    material = (_gavetas._material_de(atuais)
                or (_material_do_modulo(conj) if conj is not None else None))
    for velha in atuais[len(dados['prateleiras']):]:
        _gavetas._remover(velha)
        mudou = True
    for i, caixa in enumerate(dados['prateleiras']):
        obj = (atuais[i] if i < len(atuais) else
               _copiar_prateleira(grupo, i, referencia) if referencia is not None else
               _nova_prateleira(grupo, i, material))
        if obj.get(CHAVE_INDICE) != i:
            obj[CHAVE_INDICE] = i
        mudou = _vestir(obj, caixa) or mudou
    # Writing an unchanged pose still invalidates depsgraph/snap BVHs.
    # The ruler need not reevaluate shelves already in the correct pose.
    if mudou:
        bpy.context.view_layer.update()


def criar_prateleiras(context, conj, margens, p, pecas=None, referencial=None, blocagem_uid=None):
    """Create a shelf group in cabinet `conj`; return the group."""
    p = dict(PARAMETROS_PADRAO, **p)
    grupo = bpy.data.objects.new("Shelves %s" % conj.name, None)
    colecao = (_modulos._colecao_do_modulo(conj)
               or next(iter(conj.users_collection), context.scene.collection))
    colecao.objects.link(grupo)
    grupo.empty_display_type = 'PLAIN_AXES'
    grupo.empty_display_size = 0.05
    grupo.hide_render = True
    grupo[MARCA_GRUPO] = 1
    grupo[CHAVE_MODULO] = conj.name
    grupo[CHAVE_PARAMETROS] = p
    if referencial is not None:
        grupo[CHAVE_REFERENCIA]=[v for linha in referencial for v in linha]
    grupo[CHAVE_MARGENS] = [float(m) for m in margens]
    grupo.parent = conj
    grupo[_divisorias.CHAVE_BLOCAGEM] = blocagem_uid or _chapas._garantir_uid(grupo)
    try:
        if pecas:
            for obj in pecas:
                obj[MARCA_PRATELEIRA] = 1
            largura, altura, matriz = vao(grupo)
            dados = calcular(largura, altura, p)
            mundo = conj.matrix_world @ matriz
            for i, (obj, caixa) in enumerate(zip(pecas, dados['prateleiras'])):
                nova, dims = _gavetas._matriz_da_caixa(caixa, 2)
                # Reorient the SAME mesh: L shapes/curves must not become boxes.
                if obj.data.users > 1:
                    obj.data = obj.data.copy()
                obj.data.transform((mundo @ nova).inverted() @ obj.matrix_world)
                obj.parent = grupo
                obj[MARCA_PRATELEIRA] = 1
                obj[CHAVE_INDICE] = i
                for chave in [k for k in obj.keys() if k.startswith('adj_')]:
                    del obj[chave]
        montar(grupo)
        if not pecas:
            _divisorias.particionar_grupo(grupo)
    except ValueError:
        for o in list(grupo.children):
            _gavetas._remover(o)
        _gavetas._remover(grupo)
        raise
    return grupo


def ajustar_ao_espaco(grupo, atual, capacidade):
    """Remember the choice; consume clearance before shrinking the block."""
    p = parametros(grupo)
    assinatura = repr((list(atual), p))
    estado = grupo.get(CHAVE_ENCAIXE)
    if not estado or estado.get('bloco_atual') != assinatura:
        grupo[CHAVE_ENCAIXE] = dict(medidas=list(atual), bloco_atual=assinatura,
            profundidade=float(p['profundidade_mm']), vaos=list(p['vaos_mm']),
            individuais=p.get('individuais', []), ultimo='')
        estado = grupo[CHAVE_ENCAIXE]
    novo = [min(float(v), capacidade[k]) for k,v in enumerate(estado['medidas'])]
    p['profundidade_mm'] = novo[1]
    grupo[CHAVE_PARAMETROS] = p
    estado['ultimo'] = repr((p['profundidade_mm'],p['vaos_mm'],p.get('individuais', [])))
    estado['bloco_atual'] = repr((novo,p))
    return novo


def atualizar_do_conjunto(conj):
    """Rebuild in the transported opening, keeping choices until space runs out."""
    for grupo in grupos_do_modulo(conj):
        try:
            sincronizar_exclusoes(grupo)
            p=parametros(grupo)
            _l,altura,matriz=vao(grupo)
            atual=repr((p['profundidade_mm'],p['vaos_mm'],p.get('individuais', [])))
            estado=grupo.get(CHAVE_ENCAIXE)
            if not estado or estado['ultimo']!=atual:
                grupo[CHAVE_ENCAIXE]=dict(profundidade=float(p['profundidade_mm']),
                                          vaos=list(p['vaos_mm']),ultimo=atual,
                                          individuais=p.get('individuais', []))
                estado=grupo[CHAVE_ENCAIXE]
            ref=matriz.to_3x3().normalized()
            _lo,hi=_gavetas.limites_na_referencia(conj,ref)
            origem=ref.transposed() @ matriz.translation*1000
            limite=hi.y-origem.y
            if 'medidas' in estado:
                # Transport already subtracted support thickness. The outer box
                # must not restore a depth that cannot fit.
                limite=min(limite,float(p['profundidade_mm']))
            p['profundidade_mm']=max(float(p['recuo_mm'])+MENOR_LADO_MM,
                                     min(float(estado['profundidade']),limite))
            for i, unidade in enumerate(estado.get('individuais') or ()):
                modelo = _como_dict(unidade)
                if 'profundidade_mm' in modelo:
                    modelo['profundidade_mm'] = max(
                        float(modelo.get('recuo_mm', p['recuo_mm'])) + MENOR_LADO_MM,
                        min(float(modelo['profundidade_mm']), limite))
                _gravar_individual(p, i, modelo)
            if p['espacamento']=='LIVRE' and len(estado['vaos'])==int(p['quantidade']):
                desejados=list(estado['vaos'])
                livre=max(0,altura-sum(float(parametros_individuais(p, i)['espessura_mm'])
                                      for i in range(int(p['quantidade']))))
                fator=min(1,livre/max(sum(desejados),.001))
                p['vaos_mm']=[v*fator for v in desejados]
            if p != parametros(grupo):
                grupo[CHAVE_PARAMETROS]=p
            ultimo=repr((p['profundidade_mm'],p['vaos_mm'],p.get('individuais', [])))
            if grupo[CHAVE_ENCAIXE]['ultimo'] != ultimo:
                grupo[CHAVE_ENCAIXE]['ultimo']=ultimo
            montar(grupo)
            if 'medidas' in grupo[CHAVE_ENCAIXE]:
                l,a=grupo[CHAVE_VAO]
                grupo[CHAVE_ENCAIXE]['bloco_atual'] = repr(([float(l),float(p['profundidade_mm']),float(a)],p))
        except ValueError as erro:
            print("[Archy Builder] shelves in %s: %s" % (conj.name, erro))


def _parametros_editados(grupo, nome, valor):
    p = parametros(grupo)
    n = int(p['quantidade'])
    _largura, altura, _m = vao(grupo)
    if nome == 'quantidade':
        valor = max(0, min(MAXIMO_PRATELEIRAS, int(valor)))
        if valor != n and n and p['espacamento'] == 'LIVRE':
            # Keep common spacing if it fits; unequal individual gaps cannot
            # follow the new count, so use equal spacing.
            baixo = vaos(altura, p)[:n]
            uniforme = max(baixo) - min(baixo) <= TOL_MM
            cabe = valor * (baixo[0] + float(p['espessura_mm'])) <= altura + TOL_MM
            if uniforme and cabe:
                p['vaos_mm'] = [baixo[0]] * valor
            else:
                p.update(espacamento='IGUAL', vaos_mm=[])
        p['quantidade'] = valor
    elif nome == 'espacamento':
        # FREE starts from current gaps to avoid jumps when switching.
        p['vaos_mm'] = vaos(altura, p)[:n] if valor == 'LIVRE' else []
        p['espacamento'] = valor
    elif nome == 'entre_mm':
        p.update(espacamento='LIVRE', vaos_mm=[max(0.0, float(valor))] * n)
    elif nome.startswith('vao_'):
        p.update(espacamento='LIVRE',
                 vaos_mm=mover_vao(altura, p, int(nome[len('vao_'):]), valor))
    elif nome.startswith('acima_'):
        # Gap above shelf K, moving THAT shelf rather than the one above.
        p.update(espacamento='LIVRE', vaos_mm=mover_vao(
            altura, p, int(nome[len('acima_'):]) + 1, valor, de_baixo=True))
    elif nome in PARAMETROS_PADRAO:
        p[nome] = max(0.0, float(valor))
    else:
        raise ValueError("Unknown shelf parameter: %s" % nome)
    return p


def editar(context, grupo, nome, valor, referencia=None, somente_grupo=False):
    """Change a Shelves-tab parameter; return error and restore state, or None."""
    estado = edicao_atual(context)
    global_ = estado and grupo.name in estado['globais']
    if context.mode == 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='OBJECT')
    concluir_edicao()
    sincronizar_exclusoes(grupo)
    nome = nome[len('prateleiras_'):] if nome.startswith('prateleiras_') else nome
    antes = parametros(grupo)
    fonte = referencia or (None if global_ or somente_grupo else individual_ativo(context, grupo))
    if nome == 'quantidade' and fonte is not None and referencia is None:
        return editar_quantidade_local(context, grupo, fonte, valor)
    if nome.startswith('vao_') and fonte is not None:
        try:
            trecho = detalhamento(grupo, fonte)
        except ValueError as erro:
            return str(erro)
        # The last local field is the gap ABOVE the last copy. Move that copy,
        # never the support delimiting the next span.
        if int(nome[len('vao_'):]) == trecho['ultimo'] + 1:
            nome = 'acima_%d' % trecho['ultimo']
    if nome.startswith('individual_'):
        _prefixo, indice, campo = nome.split('_', 2)
        return editar_individual(context, grupo, int(indice), campo, valor)
    if nome in CAMPOS_INDIVIDUAIS and fonte is not None:
        return editar_individual(context, grupo, int(fonte[CHAVE_INDICE]), nome, valor)
    if nome == 'quantidade' and int(valor) > int(antes['quantidade']):
        atuais = prateleiras_do_grupo(grupo)
        if fonte is None and len({_digital(o) for o in atuais}) > 1:
            _referencia_pendente[0] = dict(grupo=grupo.name, quantidade=int(valor),
                                         regiao=None, mouse=None)
            if not bpy.app.background and not bpy.app.timers.is_registered(_abrir_referencia):
                bpy.app.timers.register(_abrir_referencia, first_interval=0.01)
            return None
        fonte = fonte or (atuais[0] if atuais else None)
    try:
        p = _parametros_editados(grupo, nome, valor)
        if nome in CAMPOS_INDIVIDUAIS:
            for unidade in p.get('individuais') or ():
                unidade.pop(nome, None)
        if nome == 'quantidade':
            quantidade = int(p['quantidade'])
            p['individuais'] = list(p.get('individuais') or ())[:quantidade]
            if fonte is not None:
                modelo = parametros_individuais(antes, int(fonte[CHAVE_INDICE]))
                for i in range(int(antes['quantidade']), quantidade):
                    _gravar_individual(p, i, {k: modelo[k] for k in CAMPOS_INDIVIDUAIS
                                              if k in modelo})
            if p['espacamento'] == 'LIVRE':
                try:
                    vaos(vao(grupo)[1], p)
                except ValueError:
                    # Template thickness may differ from the group default:
                    # redistribute again if the gaps cannot fit.
                    p.update(espacamento='IGUAL', vaos_mm=[])
        grupo[CHAVE_PARAMETROS] = p
        montar(grupo, referencia=fonte)
    except ValueError as erro:
        grupo[CHAVE_PARAMETROS] = antes
        montar(grupo)
        return str(erro)
    return None


def editar_individual(context, grupo, indice, nome, valor):
    if nome not in CAMPOS_INDIVIDUAIS:
        return "Unknown individual parameter"
    antes = parametros(grupo)
    if not 0 <= indice < int(antes['quantidade']):
        return "Shelf not found"
    p = parametros(grupo)
    if nome == 'largura_mm':
        largura = vao(grupo)[0]
        if not MENOR_LADO_MM <= float(valor) <= largura + TOL_MM:
            return "Width exceeds the shelf opening"
        nome, valor = 'folga_lateral_mm', max(0., (largura - float(valor)) / 2)
    fonte = prateleiras_do_grupo(grupo)[indice]
    try:
        indices = [int(o[CHAVE_INDICE]) for o in detalhamento(grupo, fonte)['unidades']]
    except ValueError as erro:
        return str(erro)
    for k in indices:
        _gravar_individual(p, k, {nome: max(0., float(valor))})
    if nome == 'espessura_mm':
        altura = vao(grupo)[1]
        g = vaos(altura, antes)
        for k in indices:
            g[k + 1] -= float(valor) - float(parametros_individuais(antes, k)[nome])
        if min(g) < -TOL_MM:
            return "Does not fit: insufficient space above the shelf"
        p.update(espacamento='LIVRE', vaos_mm=g[:-1])
    try:
        calcular(*vao(grupo)[:2], p)
        grupo[CHAVE_PARAMETROS] = p
        montar(grupo)
    except ValueError as erro:
        grupo[CHAVE_PARAMETROS] = antes
        return str(erro)
    return None


def resolver_referencia(context, obj):
    pedido = _referencia_pendente[0]
    if (not pedido or obj is None or MARCA_PRATELEIRA not in obj
            or obj.parent is None or obj.parent.name != pedido['grupo']):
        return "Select a shelf in this group"
    grupo = obj.parent
    quantidade = pedido['quantidade']
    _referencia_pendente[0] = None
    return editar(context, grupo, 'quantidade', quantidade, referencia=obj)


def iniciar_edicao(context, malhas, global_):
    """Blender handles multi-object editing; propagate once on exit.
    Retaining Mesh IDs is essential for Edit Mode undo.
    """
    registros, globais = {}, []
    for obj in malhas:
        grupo = grupo_de(obj)
        if grupo is not None and MARCA_PRATELEIRA in obj:
            registros.setdefault(grupo.name, {})[obj.name] = _digital(obj)
    for nome in registros:
        if global_:
            globais.append(nome)
    if registros:
        _edicao[0] = dict(grupos=registros, globais=globais,
                          ativo=context.view_layer.objects.active.name)


def edicao_atual(context):
    """Undo can return to Edit Mode with the Empty selected again. Recover
    from NATIVE selection and measure the restored mesh once; do not
    reapply a reference from a later editing session.
    """
    if _edicao[0]:
        return _edicao[0]
    if context.mode == 'EDIT_MESH':
        editando = list(context.objects_in_mode)
        if not any(MARCA_PRATELEIRA in o for o in editando):
            return None
        malhas = _selecao.malhas_para_editar(context)
        for obj in editando:
            obj.update_from_editmode()
        iniciar_edicao(context, malhas or editando, bool(malhas))
    return _edicao[0]


def concluir_edicao():
    if not edicao_atual(bpy.context) or bpy.context.mode == 'EDIT_MESH':
        return
    estado, _edicao[0] = _edicao[0], None
    for nome, digitais in estado['grupos'].items():
        grupo = bpy.data.objects.get(nome)
        if grupo is None:
            continue
        atuais = prateleiras_do_grupo(grupo)
        alteradas = [o for o in atuais if o.name in digitais and _digital(o) != digitais[o.name]]
        if not alteradas:
            continue
        for obj in alteradas:
            _chapas.absorver_malha_editada(obj)
        fonte = next((o for o in alteradas if o.name == estado['ativo']), alteradas[0])
        alvos = atuais if nome in estado['globais'] else alteradas
        p = parametros(grupo)
        largura = vao(grupo)[0]
        for obj in alvos:
            if nome in estado['globais'] and obj != fonte:
                # Do not replace the datablock: native undo still references it.
                bm = bmesh.new()
                try:
                    bm.from_mesh(fonte.data)
                    bm.to_mesh(obj.data)
                finally:
                    bm.free()
                obj.data.update()
                for chave in list(obj.keys()):
                    if chave.startswith('chapa_') and chave != 'chapa_uid':
                        del obj[chave]
                for chave in fonte.keys():
                    if chave.startswith('chapa_') and chave not in ('chapa_uid', 'chapa_edicao'):
                        valor = fonte[chave]
                        obj[chave] = valor.to_dict() if hasattr(valor, 'to_dict') else valor
                _chapas.absorver_malha_editada(obj)
            k = int(obj[CHAVE_INDICE])
            modelo = parametros_individuais(p, int(fonte[CHAVE_INDICE]) if nome in estado['globais'] else k)
            _gravar_individual(p, k, dict(espessura_mm=float(obj.chapa_espessura_mm),
                profundidade_mm=float(modelo['recuo_mm']) + obj.chapa_comprimento_mm,
                recuo_mm=float(modelo['recuo_mm']),
                folga_lateral_mm=max(0., (largura - obj.chapa_largura_mm) / 2)))
        grupo[CHAVE_PARAMETROS] = p
        # Position comes from confirmed mesh geometry for individual and
        # multi-object Tab. Do not rebuild or redistribute these openings.
        _sincronizar_disposicao(grupo)


def _abrir_referencia():
    if _referencia_pendente[0] and not bpy.app.background:
        bpy.ops.object.cabinet_referencia_prateleira('INVOKE_DEFAULT')
    return None


def atualizar_aviso_referencia(context, event):
    pedido = _referencia_pendente[0]
    if pedido is None:
        return
    pedido.update(mouse=None, regiao=None)
    # WINDOW coordinates: the modal starts in a menu, but the notice belongs
    # to the viewport under the cursor. Retain no RNA areas/regions in state.
    if _gaveta_eventos._gaveta_sob_evento(context, event) is None:
        for area in context.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            regiao = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if regiao is None:
                continue
            x, y = event.mouse_x - regiao.x, event.mouse_y - regiao.y
            if 0 <= x < regiao.width and 0 <= y < regiao.height:
                pedido.update(mouse=Vector((x, y)), regiao=regiao.as_pointer(),
                              recado=OBJECT_OT_referencia_prateleira.bl_label)
                break
    _eventos._redesenhar_viewports(context)


class OBJECT_OT_referencia_prateleira(Operator):
    """Choose the template for new shelves in the viewport."""
    bl_idname = 'object.cabinet_referencia_prateleira'
    bl_label = "Select the Reference Shelf"
    bl_options = {'INTERNAL', 'UNDO'}

    def invoke(self, context, event):
        if not _referencia_pendente[0]:
            return {'CANCELLED'}
        atualizar_aviso_referencia(context, event)
        context.workspace.status_text_set("Select the reference shelf | Esc: cancel")
        context.window_manager.modal_handler_add(self)
        _eventos._redesenhar_viewports(context)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        _referencia_pendente[0] = None
        context.workspace.status_text_set(None)
        _eventos._redesenhar_viewports(context)

    def modal(self, context, event):
        if not _referencia_pendente[0] or event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cancel(context)
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            atualizar_aviso_referencia(context, event)
            return {'PASS_THROUGH'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            obj = bpy.data.objects.get(_gaveta_eventos._objeto_sob_mouse(context, event))
            try:
                erro = resolver_referencia(context, obj)
            except Exception:
                self.cancel(context)
                raise
            if erro:
                self.report({'WARNING'}, erro)
                if _referencia_pendente[0]:
                    return {'RUNNING_MODAL'}
            self.cancel(context)
            return {'CANCELLED'} if erro else {'FINISHED'}
        return {'PASS_THROUGH'}


def entre(grupo):
    """Tab Between Shelves value: the mean of bottom gaps."""
    _largura, altura, _m = vao(grupo)
    try:
        baixo = vaos(altura, parametros(grupo))[:-1]
    except ValueError:
        return 0.0
    return sum(baixo) / len(baixo) if baixo else 0.0


class OBJECT_OT_alinhar_prateleiras(Operator):
    bl_idname = 'object.cabinet_alinhar_prateleiras'
    bl_label = "Center Spacing"
    bl_description = "Equalize the gaps above and below the selected shelf; for a group, distribute all shelves"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        grupo = grupo_de(context.object)
        return (grupo is not None and getattr(context, 'mode', '') == 'OBJECT'
                and bool(prateleiras_do_grupo(grupo)))

    def execute(self, context):
        grupo = grupo_de(context.object)
        # Native deletion may not have reached the timer yet: the unit index
        # must correspond to surviving supports.
        sincronizar_exclusoes(grupo)
        unidade = individual_ativo(context, grupo)
        if unidade is None:
            erro = editar(context, grupo, 'espacamento', 'IGUAL')
        else:
            indice = int(unidade[CHAVE_INDICE])
            if unidade.get(CHAVE_DETALHAMENTO):
                erro = editar_quantidade_local(context, grupo, unidade,
                    detalhamento(grupo, unidade)['quantidade'], redistribuir=True)
                if erro:
                    self.report({'WARNING'}, erro)
                    return {'CANCELLED'}
                _eventos._redesenhar_viewports(context)
                return {'FINISHED'}
            g = vaos(vao(grupo)[1], parametros(grupo))
            erro = editar(context, grupo, 'vao_%d' % indice,
                          (g[indice] + g[indice + 1]) / 2)
        if erro:
            self.report({'WARNING'}, erro)
            return {'CANCELLED'}
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


# ------------------------------------------------------------ selection
def selecionar(context, obj, nivel, somar=False):
    """'GRUPO' selects all shelves in the opening; 'PRATELEIRA' only `obj`'s shelf."""
    grupo = grupo_de(obj)
    if grupo is None:
        return False
    _divisorias.garantir_blocagem(grupo)
    if nivel == 'PRATELEIRA' and MARCA_PRATELEIRA in obj:
        alvos, ativo = [obj], obj
    else:
        alvos = [o for g in _divisorias.grupos_da_blocagem(grupo) for o in [g, *prateleiras_do_grupo(g)]]
        ativo = grupo
    if not somar:
        for o in context.selected_objects:
            o.select_set(False)
    for o in alvos:
        if o.visible_get():
            o.select_set(True)
    context.view_layer.objects.active = ativo
    if context.area:
        context.area.tag_redraw()
    return True


def selecionados(context):
    """Groups with the group OR a shelf selected."""
    grupos = []
    for o in getattr(context, 'selected_objects', ()) or ():
        g = grupo_de(o)
        if g is not None and g not in grupos:
            grupos.append(g)
    return grupos


# ------------------------------------------------------------ HUD
def medidas(grupo):
    """(width, height, depth) in mm displayed by the HUD and tab."""
    largura, altura, _m = vao(grupo)
    return largura, altura, float(parametros(grupo)['profundidade_mm'])


def linhas_hud(grupo, chapas):
    if individual_ativo(bpy.context, grupo) is not None:
        return _linhas_hud_grupo(grupo, chapas)
    return _divisorias.linhas_da_blocagem(grupo, chapas, _linhas_hud_grupo)


def _linhas_hud_grupo(grupo, chapas):
    """Shelf HUD lines: L/P/A on the opening box like drawers, plus one line
    per GAP with its value beside it. Drag or click/type moves only
    that gap's upper shelf."""
    largura, altura, prof = medidas(grupo)
    m = grupo.matrix_world
    unidade = individual_ativo(bpy.context, grupo)
    detalhe = None
    if unidade is not None:
        try:
            detalhe = detalhamento(grupo, unidade)
        except ValueError:
            pass
    x0, x1, y0, y1, z0, z1 = 0., largura, 0., prof, 0., altura
    if detalhe:
        caixas = detalhe['caixas']
        x0, x1 = min(c[0] for c in caixas), max(c[1] for c in caixas)
        y0, y1 = min(c[2] for c in caixas), max(c[3] for c in caixas)
        z0, z1 = detalhe['baixo'], detalhe['cima']
    cantos = [m @ (Vector(((x0, x1)[i], (y0, y1)[j], (z0, z1)[k])) / 1000.0)
              for k in (0, 1) for j in (0, 1) for i in (0, 1)]
    letras = {0: 'L', 1: 'P', 2: 'A'}
    linhas = []
    for eixo, arestas in enumerate(_hud.ARESTAS_EIXO):
        for i, j in arestas:
            # Supports bound the local span. Gap dimensions edit positions;
            # this frame does not resize the global block.
            linhas.append({'tipo': 'contorno_forma' if detalhe else 'prateleiras',
                           'editavel': not bool(detalhe), 'objeto': grupo, 'modo': 'PRATELEIRAS',
                           'eixo': eixo, 'letra': None if detalhe else letras[eixo],
                           'face': (letras[eixo],), 'cantos': (i, j),
                           'chapas': chapas, 'pontos': [cantos[i], cantos[j]]})
    p = parametros(grupo)
    try:
        dados = calcular(largura, altura, p)
    except ValueError:
        return cantos, linhas
    caixas = dados['prateleiras']
    x, y = (x0 + x1) / 2.0, y0
    indices = range(detalhe['primeiro'], detalhe['ultimo'] + 2) if detalhe else range(len(dados['vaos']))
    for k in indices:
        z0 = caixas[k - 1][5] if k > 0 else 0.0
        z1 = caixas[k][4] if k < len(caixas) else altura
        if z1 - z0 < 1.0:
            continue
        linhas.append({'tipo': 'prateleiras', 'objeto': grupo, 'modo': 'PRATELEIRAS',
                       'letra': None, 'face': ('V', k), 'vao': True, 'chapas': chapas,
                       'pontos': [m @ (Vector((x, y, z)) / 1000.0) for z in (z0, z1)]})
    return cantos, linhas


def valor(grupo, chave):
    if chave[0] == 'V':
        _largura, altura, _m = vao(grupo)
        return vaos(altura, parametros(grupo))[chave[1]]
    largura, altura, prof = medidas(grupo)
    return {'L': largura, 'A': altura, 'P': prof}[chave[0]]


def aplicar(context, grupo, chave, novo, lado=None):
    """HUD/tab dimension: V edits one gap; L/A change the moving side's
    MARGIN with the mouse-nearest corner fixed; P edits depth."""
    sincronizar_exclusoes(grupo)
    chave = tuple(chave) if isinstance(chave, (tuple, list)) else (chave,)
    letra = chave[0]
    if letra == 'V':
        return editar(context, grupo, 'vao_%d' % chave[1], novo)
    if letra == 'P':
        novo = max(MENOR_LADO_MM, float(novo))
        antes = list(grupo.get(CHAVE_MARGENS) or (0, 0, 0, 0, 0))
        if lado == 'max':
            margens = list(antes)
            margens[4] -= novo - valor(grupo, ('P',))
            grupo[CHAVE_MARGENS] = margens
        erro = editar(context, grupo, 'profundidade_mm', novo)
        if erro:
            grupo[CHAVE_MARGENS] = antes
            montar(grupo)
        return erro
    margens = list(grupo.get(CHAVE_MARGENS) or (0, 0, 0, 0, 0))
    variacao = float(novo) - valor(grupo, (letra,))
    if letra == 'L':
        indice = 1 if lado != 'max' else 0
    else:
        indice = 3 if lado != 'max' else 2
    antes = list(margens)
    margens[indice] = max(0.0, margens[indice] - variacao)
    grupo[CHAVE_MARGENS] = margens
    try:
        montar(grupo)
    except ValueError as erro:
        grupo[CHAVE_MARGENS] = antes
        montar(grupo)
        return str(erro)
    return None


def copia(grupo):
    """State restored by Esc during HUD dragging (`restaurar`)."""
    return (grupo.name, parametros(grupo), list(grupo.get(CHAVE_MARGENS) or ()))


def restaurar(estado):
    nome, p, margens = estado
    grupo = bpy.data.objects.get(nome)
    if grupo is None:
        return
    grupo[CHAVE_PARAMETROS] = p
    grupo[CHAVE_MARGENS] = margens
    try:
        montar(grupo)
    except ValueError as erro:
        print("[Archy Builder] shelves:", erro)


# ------------------------------------------------------------ assistant
_assistente_prateleiras = [None]
RECADOS = {
    'CANTO1': "Click the TOP LEFT corner of the opening (Esc cancels)",
    'CANTO2': "Click the BOTTOM RIGHT corner of the opening",
    'QUANTIDADE': "Scroll: shelf count | Click: create",
}


def _criando():
    return _assistente_prateleiras[0] is not None


class OBJECT_OT_criar_prateleiras(_gavetas.AssistenteDoVao, Operator):
    """Create shelves in an opening: two diagonal corners and count."""
    bl_idname = 'object.cabinet_criar_prateleiras'
    bl_label = "Create Shelves"
    bl_options = {'REGISTER', 'UNDO'}

    _estado = _assistente_prateleiras
    RECADOS = RECADOS
    MAXIMO = MAXIMO_PRATELEIRAS
    ITEM = ('prateleira', 'prateleiras')
    ABA = 'PRATELEIRAS'
    FIM_QUANTIDADE = "Click to create"

    def _parametros_padrao(self):
        return dict(PARAMETROS_PADRAO, vaos_mm=[])

    def _calcular(self, largura, altura, p):
        return calcular(largura, altura, p)

    def _caixas_da_previa(self, dados):
        return dados['prateleiras']

    def _comecar_no_modulo(self, conj, ponto):
        p = self._w['p']
        p['espessura_mm'] = float(_portas._espessura_do_vao(conj))
        # Only TWO points: no depth step; extend to the back
        # (`_definir_vao`, without click-time mesh scans).
        # Front clearance is the tab's Setback value.

    def _depois_da_quantidade(self, context):
        return self._criar(context)

    def _criar_grupo(self, context, conj, margens, p):
        return criar_prateleiras(context, conj, margens, p,referencial=self._w.get('referencia'))

    def _selecionar_grupo(self, context, grupo):
        selecionar(context, grupo, 'GRUPO')


def esquecer():
    _assistente_prateleiras[0] = None
    _quantidade_previa[0] = None
    if _referencia_pendente[0] and bpy.context.workspace is not None:
        bpy.context.workspace.status_text_set(None)
    _referencia_pendente[0] = None
    _edicao[0] = None
    if bpy.app.timers.is_registered(_abrir_referencia):
        bpy.app.timers.unregister(_abrir_referencia)
