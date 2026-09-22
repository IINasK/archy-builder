bl_info = {
    "name": "Cabinet Creator",
    "author": "Douglas",
    "version": (39, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > N > Cabinet Creator",
    "doc_url": "",
    "description": "Armarios parametricos: chapas com malha editavel e espessura imune a escala",
    "category": "Object",
}

import bpy, bmesh, math, os, uuid, json
import bpy.utils.previews
from bpy.props import FloatProperty, BoolProperty, EnumProperty, StringProperty
from mathutils import Vector
from bpy.types import Operator, Panel

ESPESSURAS_PERMITIDAS = [15.0, 18.0, 20.0, 30.0]

# Marcador ID. ATENCAO: propriedades criadas com bpy.props em
# bpy.types.Object sao RNA e NAO aparecem em `"x" in obj`.
# Os nomes das propriedades internas (chapa_*, eh_chapa, adj_*) sao
# deliberadamente mantidos do nome antigo do add-on: eles estao gravados
# dentro dos .blend dos presets. Renomea-los invalidaria toda a
# biblioteca ja' salva.
MARCA_CHAPA = "eh_chapa"
MARCA_CONJUNTO = "eh_conjunto_chapa"

_ocupado = [False]
_havia_modal = [False]   # lembra se um operador modal estava ativo


def gerar_malha_chapa(obj):
    """Malha REAL via bmesh -> editavel em Edit Mode.
    X local = largura | Y local = comprimento | Z local = ESPESSURA."""
    if obj is None or obj.type != 'MESH' or obj.mode == 'EDIT':
        return
    if not obj.chapa_auto:
        return
    L = obj.chapa_largura_mm / 1000.0
    C = obj.chapa_comprimento_mm / 1000.0
    E = obj.chapa_espessura_mm / 1000.0
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= L
        v.co.y *= C
        v.co.z *= E
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def _upd_chapa(self, context):
    if _ocupado[0]:
        return
    gerar_malha_chapa(self)


def _upd_espessura(self, context):
    """Arredonda o valor digitado para a espessura permitida mais proxima."""
    if _ocupado[0]:
        return
    val = self.chapa_espessura_mm
    alvo = min(ESPESSURAS_PERMITIDAS, key=lambda v: abs(v - val))
    if abs(val - alvo) > 1e-6:
        _ocupado[0] = True
        try:
            self.chapa_espessura_mm = alvo
        finally:
            _ocupado[0] = False
    gerar_malha_chapa(self)


# ===================================================== NORMALIZACAO
def normalizar_chapas(objs=None):
    """Converte a escala acumulada em cada chapa em MEDIDA (mm) e zera
    a escala de volta para 1.

    REGRA CENTRAL: o componente Z local (espessura) e' DESCARTADO, nao
    convertido. Como Z local e' sempre a espessura -- esteja a peca
    deitada ou em pe' -- a espessura fica imune a escala em QUALQUER
    eixo do mundo.

    Devolve a lista de pecas ajustadas.
    """
    if objs is None:
        objs = bpy.data.objects
    alvos = []
    for obj in objs:
        if obj.type != 'MESH' or MARCA_CHAPA not in obj or obj.mode == 'EDIT':
            continue
        sx, sy, sz = obj.scale
        if abs(sx - 1) < 1e-6 and abs(sy - 1) < 1e-6 and abs(sz - 1) < 1e-6:
            continue
        alvos.append((obj, sx, sy, sz))
    if not alvos:
        return []

    _ocupado[0] = True
    try:
        for obj, sx, sy, sz in alvos:
            obj.chapa_largura_mm = obj.chapa_largura_mm * sx
            obj.chapa_comprimento_mm = obj.chapa_comprimento_mm * sy
            # sz (espessura) deliberadamente IGNORADO
            obj.scale = (1.0, 1.0, 1.0)
    finally:
        _ocupado[0] = False

    for obj, _sx, _sy, _sz in alvos:
        gerar_malha_chapa(obj)

    # fecha os vaos abertos pela aritmetica da escala
    try:
        aplicar_adjacencia()
    except Exception as e:
        print("[Cabinet Creator] adjacencia:", e)

    return [o for o, _a, _b, _c in alvos]


# ============================= HANDLER: age SO' depois do modal acabar
def ao_atualizar_depsgraph(scene, depsgraph):
    """A chapa deforma normalmente durante o arraste do S (a ferramenta
    nativa do Blender trabalha sem interferencia). Assim que o operador
    modal termina -- Enter, clique ou Esc -- este handler detecta a
    transicao e recalcula todas as chapas de uma vez.

    Mexer na escala DURANTE o modal nao funciona: o operador guarda a
    escala inicial em cache e reaplica o fator a cada movimento do
    mouse, entao qualquer correcao feita no meio do arraste e'
    sobrescrita no quadro seguinte.
    """
    if _ocupado[0]:
        return

    modal_ativo = False
    try:
        for win in bpy.context.window_manager.windows:
            if len(win.modal_operators) > 0:
                modal_ativo = True
                break
    except Exception:
        modal_ativo = False

    if modal_ativo:
        _havia_modal[0] = True     # arraste em andamento: nao tocar
        return

    if _havia_modal[0]:
        _havia_modal[0] = False
        absorver_conjuntos()
        normalizar_chapas()        # o modal acabou: recalcula tudo
        return

    # sem modal envolvido (ex.: escala definida por script/painel)
    absorver_conjuntos()
    normalizar_chapas()



# ===================================================== ADJACENCIA
# Guarda, para cada ponta da chapa (X- X+ Y- Y+), qual peca vizinha ela
# encosta e qual era a folga no momento da deteccao. Depois de qualquer
# recalculo, a chapa e' esticada/encurtada para reencontrar a mesma
# folga -- fechando o vao que a aritmetica da escala abre.
#
# O vao aparece porque, ao escalar por F, a POSICAO das laterais e' multi-
# plicada por F mas a ESPESSURA delas nao. Por lado: vao = (E/2)*(F-1).
PONTAS = ("x_neg", "x_pos", "y_neg", "y_pos")
TOL_ENCOSTE = 0.06   # 60mm: distancia maxima para considerar vizinhanca


def _garantir_uid(obj):
    """Identificador estavel da chapa. Necessario porque a adjacencia
    guardada por NOME quebra ao trazer um modulo da biblioteca: os nomes
    ganham sufixo (.001) e os vinculos apontariam para a peca errada."""
    if not obj.get("chapa_uid"):
        obj["chapa_uid"] = uuid.uuid4().hex[:12]
    return obj["chapa_uid"]


def _resolver_vizinho(C, uid, nome):
    """Procura o vizinho primeiro entre os IRMAOS (mesmo pai), para que
    copias de um mesmo modulo nao se confundam entre si."""
    if uid:
        irmaos = [o for o in bpy.data.objects
                  if o.parent == C.parent and o.get("chapa_uid") == uid]
        if len(irmaos) == 1:
            return irmaos[0]
        if len(irmaos) > 1:
            return min(irmaos, key=lambda o: (o.location - C.location).length)
    if nome and nome in bpy.data.objects:
        return bpy.data.objects[nome]
    return None


def _eixos(obj):
    """Eixos locais expressos em MUNDO. Usar rotation_euler (local) aqui
    quebrava assim que o Empty pai saia da origem: o espaco de
    referencia deixava de coincidir com o mundo e o teste de 'face
    encostada no limite' parava de reconhecer as pecas."""
    m = obj.matrix_world.to_3x3()
    return m.col[0].normalized(), m.col[1].normalized(), m.col[2].normalized()


def _centro(obj):
    return obj.matrix_world.translation.copy()


def _definir_centro(obj, novo):
    """Grava um centro de MUNDO respeitando pai e matrix_parent_inverse."""
    if obj.parent is not None:
        base = obj.parent.matrix_world @ obj.matrix_parent_inverse
        obj.location = base.inverted() @ novo
    else:
        obj.location = novo


def _meias(obj):
    return (obj.chapa_largura_mm / 2000.0,
            obj.chapa_comprimento_mm / 2000.0,
            obj.chapa_espessura_mm / 2000.0)


def _cantos(obj):
    ex, ey, ez = _eixos(obj)
    hx, hy, hz = _meias(obj)
    c = _centro(obj)
    pts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                pts.append(c + ex * (sx * hx) + ey * (sy * hy) + ez * (sz * hz))
    return pts


def _faixa(obj, d):
    p = [v.dot(d) for v in _cantos(obj)]
    return min(p), max(p)


def _sobrepoe(a, b, folga=1e-4):
    return (a[0] < b[1] + folga) and (b[0] < a[1] + folga)


def detectar_adjacencia(objs):
    """Para cada ponta de cada chapa, acha a peca vizinha mais proxima
    naquela direcao e memoriza a folga atual."""
    chapas = [o for o in objs if o.type == 'MESH' and MARCA_CHAPA in o]
    for c in chapas:
        _garantir_uid(c)
    n = 0
    for C in chapas:
        for k in PONTAS:
            C[f"adj_{k}"] = ""
            C[f"adj_{k}_folga"] = 0.0
        ex, ey, ez = _eixos(C)
        hx, hy, hz = _meias(C)
        for eixo, u, h in (("x", ex, hx), ("y", ey, hy)):
            perp = [w for w in (ex, ey, ez) if w is not u]
            for lado in ("pos", "neg"):
                ponta = _centro(C).dot(u) + (h if lado == "pos" else -h)
                melhor, melhor_folga, melhor_face = None, None, 0
                for N in chapas:
                    if N is C:
                        continue
                    # so' considera vizinho que se sobrepoe nas outras direcoes
                    if not all(_sobrepoe(_faixa(C, w), _faixa(N, w)) for w in perp):
                        continue
                    faces = _faixa(N, u)   # (min, max) do vizinho na direcao u
                    # Ancora na face do vizinho MAIS PROXIMA da ponta.
                    # Usar sempre a face distante embutia a espessura
                    # antiga na folga: ao trocar a espessura, a peca era
                    # empurrada para fora e o modulo crescia sozinho.
                    i_face = 0 if abs(faces[0] - ponta) <= abs(faces[1] - ponta) else 1
                    folga = (faces[i_face] - ponta) if lado == "pos" else (ponta - faces[i_face])
                    if folga < -TOL_ENCOSTE or folga > TOL_ENCOSTE:
                        continue
                    if melhor is None or abs(folga) < abs(melhor_folga):
                        melhor, melhor_folga, melhor_face = N, folga, i_face
                if melhor is not None:
                    C[f"adj_{eixo}_{lado}"] = melhor.name
                    C[f"adj_{eixo}_{lado}_uid"] = _garantir_uid(melhor)
                    C[f"adj_{eixo}_{lado}_folga"] = float(melhor_folga)
                    C[f"adj_{eixo}_{lado}_face"] = int(melhor_face)
                    n += 1
    return n


def aplicar_adjacencia(objs=None):
    """Estica/encurta cada chapa nos eixos de largura e comprimento
    para reencontrar a folga memorizada com seus vizinhos."""
    if objs is None:
        objs = bpy.data.objects
    chapas = [o for o in objs if o.type == 'MESH' and MARCA_CHAPA in o
              and o.mode != 'EDIT' and o.chapa_auto]
    ajustadas = []
    _ocupado[0] = True
    try:
        for C in chapas:
            ex, ey, ez = _eixos(C)
            mudou = False
            for eixo, u in (("x", ex), ("y", ey)):
                hx, hy, hz = _meias(C)
                h = hx if eixo == "x" else hy
                centro_u = _centro(C).dot(u)
                p_pos, p_neg = centro_u + h, centro_u - h
                alvo_pos, alvo_neg = p_pos, p_neg

                N = _resolver_vizinho(C, C.get(f"adj_{eixo}_pos_uid", ""), C.get(f"adj_{eixo}_pos", ""))
                if N is not None:
                    fp = int(C.get(f"adj_{eixo}_pos_face", 0))
                    alvo_pos = _faixa(N, u)[fp] - C.get(f"adj_{eixo}_pos_folga", 0.0)
                N = _resolver_vizinho(C, C.get(f"adj_{eixo}_neg_uid", ""), C.get(f"adj_{eixo}_neg", ""))
                if N is not None:
                    fn = int(C.get(f"adj_{eixo}_neg_face", 1))
                    alvo_neg = _faixa(N, u)[fn] + C.get(f"adj_{eixo}_neg_folga", 0.0)

                novo_h = (alvo_pos - alvo_neg) / 2.0
                if novo_h <= 0.0005:
                    continue
                novo_centro_u = (alvo_pos + alvo_neg) / 2.0
                if abs(novo_h - h) < 1e-7 and abs(novo_centro_u - centro_u) < 1e-7:
                    continue

                if eixo == "x":
                    C.chapa_largura_mm = novo_h * 2000.0
                else:
                    C.chapa_comprimento_mm = novo_h * 2000.0
                _definir_centro(C, _centro(C) + u * (novo_centro_u - centro_u))
                mudou = True
            if mudou:
                ajustadas.append(C)
    finally:
        _ocupado[0] = False

    for C in ajustadas:
        gerar_malha_chapa(C)
    return ajustadas


# ================================================= MODULO (CONJUNTO)
# Ao agrupar, o Empty deixa de ser so' um pai e passa a ter as medidas
# do modulo: largura, altura, profundidade e espessura.
#
# Regra: as medidas EXTERNAS mandam. Ao mudar qualquer uma delas, as
# pecas se acomodam por dentro mantendo a espessura discreta, e a
# adjacencia fecha as juntas. Ao mudar a ESPESSURA, o contorno externo
# nao se mexe: as chapas engrossam/afinam para dentro e as pecas que
# vao de uma ponta a outra se contraem ou se expandem para acompanhar.
TOL_BORDA = 0.0015   # 1.5mm: tolerancia para considerar face "no limite"


def _chapas_do_conjunto(conj):
    return [o for o in bpy.data.objects
            if o.parent == conj and o.type == 'MESH' and MARCA_CHAPA in o]


def _caixa_de(chapas):
    """Bounding box em mundo de uma lista qualquer de chapas.
    Atualiza o depsgraph antes: matrix_world so' fica correto depois do
    recalculo, e ler antes devolvia a caixa da operacao ANTERIOR."""
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    pts = []
    for o in chapas:
        pts.extend(_cantos(o))
    if not pts:
        return None
    return ([min(p[i] for p in pts) for i in range(3)],
            [max(p[i] for p in pts) for i in range(3)])


def grupo_de(obj):
    """Define o GRUPO de uma chapa: se ela pertence a um Conjunto,
    e' o conjunto inteiro; senao, e' ela mais tudo que estiver ligado
    a ela por adjacencia (transitivamente)."""
    if obj is None or MARCA_CHAPA not in obj:
        return []
    if obj.parent is not None and MARCA_CONJUNTO in obj.parent:
        return _chapas_do_conjunto(obj.parent)
    vistos, fila = {obj.name: obj}, [obj]
    while fila:
        C = fila.pop()
        for eixo in ('x', 'y'):
            for lado in ('pos', 'neg'):
                N = _resolver_vizinho(C, C.get('adj_%s_%s_uid' % (eixo, lado), ''),
                                      C.get('adj_%s_%s' % (eixo, lado), ''))
                if N is not None and N.name not in vistos:
                    vistos[N.name] = N
                    fila.append(N)
    return list(vistos.values())


def _caixa_do_conjunto(conj):
    """Bounding box em coordenadas de mundo das chapas filhas."""
    return _caixa_de(_chapas_do_conjunto(conj))


def _eixo_local_alinhado(obj, a):
    """Qual eixo local (0=largura, 1=comprimento, 2=espessura) esta'
    alinhado com o eixo de mundo a; devolve tambem a meia-extensao."""
    eixos = _eixos(obj)
    meias = _meias(obj)
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


def redimensionar_grupo(chapas, alvo_LAP_mm):
    """Leva a caixa externa do modulo para largura/altura/profundidade
    pedidas. Pecas cuja ESPESSURA corre naquele eixo mantem a espessura
    e sao ancoradas ao limite em que ja' estavam; as demais sao
    reescaladas proporcionalmente."""
    cx = _caixa_de(chapas)
    if cx is None:
        return
    lo, hi = cx
    L, A, P = alvo_LAP_mm
    alvo_mm = (L, P, A)   # ordem dos eixos de mundo: X, Y, Z

    _ocupado[0] = True
    try:
        for a in range(3):
            velho = hi[a] - lo[a]
            novo = alvo_mm[a] / 1000.0
            if velho < 1e-6 or abs(novo - velho) < 1e-7:
                continue
            razao = novo / velho
            m0, m1 = lo[a], lo[a]          # ancora o canto minimo
            M1 = m1 + novo
            for C in chapas:
                i_loc, h = _eixo_local_alinhado(C, a)
                c = _centro(C)[a]
                f_min, f_max = c - h, c + h
                if i_loc == 2:
                    # eixo de ESPESSURA: extensao nao muda
                    if abs(f_min - lo[a]) < TOL_BORDA:
                        novo_c = m1 + h
                    elif abs(f_max - hi[a]) < TOL_BORDA:
                        novo_c = M1 - h
                    else:
                        novo_c = m1 + (c - m0) * razao
                    nc = _centro(C); nc[a] = novo_c; _definir_centro(C, nc)
                else:
                    nf_min = m1 + (f_min - m0) * razao
                    nf_max = m1 + (f_max - m0) * razao
                    _escrever_dim(C, i_loc, (nf_max - nf_min) / 2.0)
                    nc = _centro(C); nc[a] = (nf_max + nf_min) / 2.0; _definir_centro(C, nc)
            lo[a], hi[a] = m1, M1
    finally:
        _ocupado[0] = False

    for C in chapas:
        gerar_malha_chapa(C)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    aplicar_adjacencia(chapas)


def aplicar_espessura_grupo(chapas, nova_e):
    """Troca a espessura de todas as chapas do modulo SEM mover o
    contorno externo: cada peca cresce/encolhe para DENTRO a partir do
    limite em que estava encostada. A adjacencia depois expande ou
    contrai as pecas que ligam uma ponta a outra."""
    cx = _caixa_de(chapas)
    if cx is None:
        return
    lo, hi = cx

    _ocupado[0] = True
    try:
        for C in chapas:
            eixos = _eixos(C)
            ez = eixos[2]
            alin = [abs(ez[a]) for a in range(3)]
            a = alin.index(max(alin))          # eixo de mundo da espessura
            h_velho = C.chapa_espessura_mm / 2000.0
            c = _centro(C)[a]
            f_min, f_max = c - h_velho, c + h_velho
            C.chapa_espessura_mm = nova_e
            h_novo = nova_e / 2000.0
            if abs(f_min - lo[a]) < TOL_BORDA:
                nc = _centro(C); nc[a] = f_min + h_novo; _definir_centro(C, nc)
            elif abs(f_max - hi[a]) < TOL_BORDA:
                nc = _centro(C); nc[a] = f_max - h_novo; _definir_centro(C, nc)
            else:
                pass                                     # interna: centro fica
    finally:
        _ocupado[0] = False

    for C in chapas:
        gerar_malha_chapa(C)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    aplicar_adjacencia(chapas)


def reposicionar_origem(conj):
    """Leva a ORIGEM (o Empty) para a posicao real do movel -- centro da
    caixa em X/Y e base em Z -- compensando os filhos para que nada se
    mexa na tela.

    Antes era o contrario: a origem ficava parada e o movel deslizava em
    relacao a ela a cada redimensionamento, porque o crescimento ancora
    no canto minimo da caixa.
    """
    if conj is None or MARCA_CONJUNTO not in conj:
        return
    chapas = _chapas_do_conjunto(conj)
    if not chapas:
        return
    # sem isto as matrizes lidas abaixo podem estar defasadas e a origem
    # so' se moveria na operacao SEGUINTE
    bpy.context.view_layer.update()
    mundos = {o.name: o.matrix_world.copy() for o in chapas}
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
    _ocupado[0] = True
    try:
        conj.location = alvo
        bpy.context.view_layer.update()
        for o in chapas:
            o.matrix_parent_inverse = conj.matrix_world.inverted()
            o.matrix_world = mundos[o.name]
    finally:
        _ocupado[0] = False


def _upd_conj_dim(self, context):
    if _ocupado[0]:
        return
    redimensionar_grupo(_chapas_do_conjunto(self),
                        (self.conj_largura_mm, self.conj_altura_mm, self.conj_profundidade_mm))
    reposicionar_origem(self)


def _upd_conj_espessura(self, context):
    if _ocupado[0]:
        return
    val = self.conj_espessura_mm
    alvo = min(ESPESSURAS_PERMITIDAS, key=lambda v: abs(v - val))
    if abs(val - alvo) > 1e-6:
        _ocupado[0] = True
        try:
            self.conj_espessura_mm = alvo
        finally:
            _ocupado[0] = False
    aplicar_espessura_grupo(_chapas_do_conjunto(self), self.conj_espessura_mm)
    reposicionar_origem(self)


def sincronizar_medidas_conjunto(conj):
    """Le a caixa real e grava nas propriedades, sem disparar recalculo."""
    m = medir_conjunto(conj)
    if not m:
        return
    _ocupado[0] = True
    try:
        conj.conj_largura_mm, conj.conj_altura_mm, conj.conj_profundidade_mm = m
        chapas = _chapas_do_conjunto(conj)
        if chapas:
            conj.conj_espessura_mm = chapas[0].chapa_espessura_mm
    finally:
        _ocupado[0] = False


class OBJECT_OT_detectar_adjacencia(Operator):
    """Memoriza quais chapas encostam uma na outra (selecione todas)"""
    bl_idname = "object.cabinet_detectar_adjacencia"
    bl_label = "Detectar Adjacencia"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sel = [o for o in context.selected_objects if o.type == 'MESH' and MARCA_CHAPA in o]
        if len(sel) < 2:
            self.report({'WARNING'}, "Selecione pelo menos 2 chapas")
            return {'CANCELLED'}
        n = detectar_adjacencia(sel)
        self.report({'INFO'}, "%d encoste(s) memorizado(s) em %d chapa(s)" % (n, len(sel)))
        return {'FINISHED'}


class OBJECT_OT_sincronizar_conjunto(Operator):
    """Le as medidas reais das pecas e atualiza os campos do modulo"""
    bl_idname = "object.cabinet_sincronizar"
    bl_label = "Ler Medidas Atuais"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        conj = context.object
        if conj is None or MARCA_CONJUNTO not in conj:
            self.report({'WARNING'}, "Selecione o Empty do modulo")
            return {'CANCELLED'}
        sincronizar_medidas_conjunto(conj)
        return {'FINISHED'}


class OBJECT_OT_agrupar_conjunto(Operator):
    """Agrupa as chapas selecionadas num conjunto (Empty pai)"""
    bl_idname = "object.cabinet_agrupar"
    bl_label = "Agrupar Conjunto"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sel = [o for o in context.selected_objects if o.type == 'MESH' and MARCA_CHAPA in o]
        if not sel:
            self.report({'WARNING'}, "Nenhuma chapa selecionada")
            return {'CANCELLED'}

        pts = []
        for o in sel:
            pts.extend(_cantos(o))
        cx = (min(p.x for p in pts) + max(p.x for p in pts)) / 2
        cy = (min(p.y for p in pts) + max(p.y for p in pts)) / 2
        cz = min(p.z for p in pts)

        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(cx, cy, cz))
        conj = context.active_object
        conj.name = "Conjunto"
        conj[MARCA_CONJUNTO] = 1
        conj.empty_display_size = 0.15

        for o in sel:
            mw = o.matrix_world.copy()
            o.parent = conj
            o.matrix_parent_inverse = conj.matrix_world.inverted()
            o.matrix_world = mw

        # adjacencia e' pre-requisito do conjunto funcionar sem vao
        detectar_adjacencia(sel)
        sincronizar_medidas_conjunto(conj)

        for o in context.selected_objects:
            o.select_set(False)
        conj.select_set(True)
        context.view_layer.objects.active = conj
        self.report({'INFO'}, "Conjunto com %d chapa(s) + adjacencia detectada" % len(sel))
        return {'FINISHED'}


def absorver_conjuntos():
    """Converte a escala aplicada num Empty de conjunto em escala real
    das chapas filhas, zerando a escala do Empty."""
    for conj in list(bpy.data.objects):
        if conj.type != 'EMPTY' or MARCA_CONJUNTO not in conj:
            continue
        sx, sy, sz = conj.scale
        if abs(sx-1) < 1e-6 and abs(sy-1) < 1e-6 and abs(sz-1) < 1e-6:
            continue
        filhos = [o for o in bpy.data.objects if o.parent == conj]
        mundos = {o.name: o.matrix_world.copy() for o in filhos}
        _ocupado[0] = True
        try:
            conj.scale = (1.0, 1.0, 1.0)
        finally:
            _ocupado[0] = False
        for o in filhos:
            o.matrix_world = mundos[o.name]
        try:
            sincronizar_medidas_conjunto(conj)
        except Exception as e:
            print("[Cabinet Creator] sincronizar:", e)


# ================================================== BIBLIOTECA / ASSETS
# Salva chapas e modulos na biblioteca de assets do Blender, para
# reaproveitar via Asset Browser (arrastar para a cena).
#
# Cada preset vira um .blend proprio dentro da pasta da biblioteca.
# Um arquivo por preset evita ter que reabrir e mesclar um .blend
# compartilhado a cada gravacao.
SUBPASTA_BIB = "Cabinet Creator"
CAT_CHAPAS = "Cabinet Creator/Chapas"
CAT_MODULOS = "Cabinet Creator/Modulos"


def _pasta_fabrica():
    """Presets que vem JUNTO com o addon (somente leitura na pratica).
    Vantagem: instalar o addon ja' traz os blocos, sem setup extra."""
    return os.path.join(os.path.dirname(__file__), "biblioteca")


def _prefs():
    try:
        return bpy.context.preferences.addons[__package__].preferences
    except Exception:
        return None


def _pasta_equipe():
    """Biblioteca compartilhada, configuravel nas Preferencias do addon.
    Aponte para uma pasta de rede e todos os computadores da empresa
    enxergam os mesmos presets."""
    p = _prefs()
    if p and p.pasta_equipe:
        return bpy.path.abspath(p.pasta_equipe)
    return os.path.join(os.path.expanduser("~"), "Documents", "Blender", "Assets", "Cabinet Creator")


def registrar_bibliotecas(silencioso=True):
    """Registra as duas pastas como bibliotecas de assets do Blender,
    sem duplicar caso ja' estejam registradas."""
    registradas = []
    libs = bpy.context.preferences.filepaths.asset_libraries
    for nome, caminho in (("Cabinet Creator (fabrica)", _pasta_fabrica()),
                          ("Cabinet Creator (equipe)", _pasta_equipe())):
        try:
            os.makedirs(caminho, exist_ok=True)
        except Exception as e:
            if not silencioso:
                print("[Cabinet Creator] nao criei", caminho, e)
            continue
        alvo = os.path.normcase(os.path.normpath(caminho))
        ja = any(os.path.normcase(os.path.normpath(bpy.path.abspath(l.path))) == alvo
                 for l in libs if l.path)
        if ja:
            continue
        try:
            bpy.ops.preferences.asset_library_add(directory=caminho)
            libs[-1].name = nome
            registradas.append(nome)
        except Exception as e:
            if not silencioso:
                print("[Cabinet Creator] registro falhou:", e)
    return registradas


def _pasta_biblioteca():
    """Destino de gravacao: sempre a biblioteca da EQUIPE.
    Nunca grava na pasta de fabrica -- ela e' sobrescrita a cada
    atualizacao do addon e os presets do usuario se perderiam."""
    destino = _pasta_equipe()
    os.makedirs(destino, exist_ok=True)
    return destino, destino


def _garantir_catalogos(raiz):
    """Cria/atualiza o blender_assets.cats.txt com os catalogos do addon."""
    arq = os.path.join(raiz, "blender_assets.cats.txt")
    existentes = {}
    if os.path.exists(arq):
        for linha in open(arq, encoding="utf-8"):
            linha = linha.strip()
            if not linha or linha.startswith("#") or linha.startswith("VERSION"):
                continue
            partes = linha.split(":")
            if len(partes) >= 2:
                existentes[partes[1]] = partes[0]
    ids = {}
    for cam in (CAT_CHAPAS, CAT_MODULOS):
        ids[cam] = existentes.get(cam) or str(uuid.uuid4())
        existentes[cam] = ids[cam]
    with open(arq, "w", encoding="utf-8") as f:
        f.write("VERSION 1\n\n")
        for cam, cid in sorted(existentes.items(), key=lambda kv: kv[1]):
            f.write("%s:%s:%s\n" % (cid, cam, cam.split("/")[-1].replace("/", "-")))
    return ids


def _nome_arquivo_seguro(nome):
    limpo = "".join(ch if (ch.isalnum() or ch in " -_") else "_" for ch in nome).strip()
    return (limpo or "sem_nome").replace(" ", "_")


def salvar_na_biblioteca(objs, nome, como_colecao):
    """Grava os objetos num .blend da biblioteca.

    como_colecao=True agrupa tudo numa Collection e marca a COLLECTION
    como asset -- necessario para modulos, porque arrastar um objeto
    traz so' aquele objeto, enquanto arrastar uma colecao traz o
    conjunto inteiro.
    """
    raiz, destino = _pasta_biblioteca()
    ids_cat = _garantir_catalogos(raiz)

    blocos = set()
    if como_colecao:
        col = bpy.data.collections.new(nome)
        for o in objs:
            col.objects.link(o)
        col.asset_mark()
        if col.asset_data:
            col.asset_data.catalog_id = ids_cat[CAT_MODULOS]
            col.asset_data.description = "Modulo G3 - %d peca(s)" % len(objs)
            col.asset_data.tags.new("chapa-g3")
        blocos.add(col)
        alvo_preview = col
    else:
        for o in objs:
            o.asset_mark()
            if o.asset_data:
                o.asset_data.catalog_id = ids_cat[CAT_CHAPAS]
                o.asset_data.tags.new("chapa-g3")
        alvo_preview = objs[0]
    for o in objs:
        blocos.add(o)
        if o.data:
            blocos.add(o.data)

    try:
        alvo_preview.asset_generate_preview()
    except Exception as e:
        print("[Cabinet Creator] preview:", e)

    arquivo = os.path.join(destino, _nome_arquivo_seguro(nome) + ".blend")
    bpy.data.libraries.write(arquivo, blocos, fake_user=True, compress=True)

    if como_colecao:
        # a colecao foi criada so' para empacotar o asset
        bpy.data.collections.remove(col)
    return arquivo


# ======================================= ARVORE DA BIBLIOTECA (3 niveis)
# Cascata horizontal: nivel 1 no topo, nivel 2 abaixo ao clicar, nivel 3
# abaixo do 2. Ramos com lista vazia no nivel 3 terminam no nivel 2.
AMBIENTES = ["Sala", "Cozinha", "Varanda", "Quarto", "Banheiro", "Externo"]

ARVORE = {
    "Armarios": {
        "Sala":     ["Inferiores", "Superiores", "Cantos", "Estantes"],
        "Cozinha":  ["Inferiores", "Superiores", "Cantos", "Torres"],
        "Varanda":  ["Inferiores", "Superiores", "Bancadas"],
        "Quarto":   ["Inferiores", "Superiores", "Closets", "Gaveteiros"],
        "Banheiro": ["Gabinetes", "Espelheiras", "Nichos"],
        "Externo":  ["Inferiores", "Superiores", "Bancadas"],
    },
    "Chapas":     {"Avulsas": []},
    "Portas":     {"Abrir": [], "Correr": [], "Basculante": []},
    "Puxadores":  {"Perfil": [], "Alca": [], "Cava": []},
    "Dobradicas": {"Comuns": [], "Amortecidas": [], "Especiais": []},
}


def _niveis_de(it):
    """Le os 3 niveis de um item do indice, aceitando o formato antigo
    (categoria/subcategoria) para nao invalidar indices ja' gravados."""
    n1 = it.get("n1")
    if n1:
        return n1, it.get("n2", ""), it.get("n3", "")
    cat, sub = it.get("categoria", ""), it.get("subcategoria", "")
    if cat in AMBIENTES:
        return "Armarios", cat, sub
    return cat, sub, ""


def _filhos_n2(n1):
    return list(ARVORE.get(n1, {}).keys())


def _filhos_n3(n1, n2):
    return list(ARVORE.get(n1, {}).get(n2, []))


def _conta(itens, n1, n2=None, n3=None):
    n = 0
    for it in itens:
        a, b, c = _niveis_de(it)
        if a != n1:
            continue
        if n2 is not None and b != n2:
            continue
        if n3 is not None and c != n3:
            continue
        n += 1
    return n


NOME_INDICE = "indice.json"


def _ler_indice(pasta):
    """Indice em JSON ao lado dos .blend. Existe para o painel listar os
    presets sem precisar abrir cada arquivo -- abrir .blend so' para
    montar a lista deixaria a interface travada."""
    arq = os.path.join(pasta, NOME_INDICE)
    if not os.path.exists(arq):
        return []
    try:
        with open(arq, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("[Cabinet Creator] indice ilegivel:", e)
        return []


def _gravar_indice(pasta, itens):
    try:
        with open(os.path.join(pasta, NOME_INDICE), "w", encoding="utf-8") as f:
            json.dump(itens, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[Cabinet Creator] nao gravei o indice:", e)


def indice_completo():
    """Junta os presets de fabrica com os da equipe, marcando a origem."""
    itens = []
    for origem, pasta in (("fabrica", _pasta_fabrica()), ("equipe", _pasta_equipe())):
        for it in _ler_indice(pasta):
            it = dict(it)
            it["origem"] = origem
            it["pasta"] = pasta
            itens.append(it)
    return itens


def registrar_no_indice(pasta, nome, arquivo, n1, n2, n3, tipo):
    itens = [i for i in _ler_indice(pasta)
             if not (i.get("arquivo") == os.path.basename(arquivo))]
    itens.append({"nome": nome, "arquivo": os.path.basename(arquivo),
                  "n1": n1, "n2": n2, "n3": n3, "tipo": tipo})
    _gravar_indice(pasta, itens)


def _itens_de(categoria, subcategoria):
    return [i for i in indice_completo()
            if i.get("categoria") == categoria and i.get("subcategoria") == subcategoria]


class OBJECT_OT_inserir_preset(Operator):
    """Traz o preset da biblioteca para a cena"""
    bl_idname = "object.cabinet_inserir_preset"
    bl_label = "Inserir"
    bl_options = {'REGISTER', 'UNDO'}

    pasta: bpy.props.StringProperty()
    arquivo: bpy.props.StringProperty()
    tipo: bpy.props.StringProperty(default="modulo")

    def execute(self, context):
        caminho = os.path.join(self.pasta, self.arquivo)
        if not os.path.exists(caminho):
            self.report({'ERROR'}, "Arquivo nao encontrado: " + caminho)
            return {'CANCELLED'}
        antes = set(bpy.data.objects)
        with bpy.data.libraries.load(caminho) as (de, para):
            if self.tipo == "modulo" and de.collections:
                para.collections = list(de.collections)
            else:
                para.objects = list(de.objects)
        novas_cols = [c for c in bpy.data.collections
                      if c.library is None and c.name not in
                      [x.name for x in context.scene.collection.children]]
        for c in novas_cols:
            if any(o not in antes for o in c.objects):
                context.scene.collection.children.link(c)
        for o in bpy.data.objects:
            if o not in antes and o.name not in [x.name for c in novas_cols for x in c.objects]:
                if o.name not in context.scene.collection.objects:
                    try:
                        context.scene.collection.objects.link(o)
                    except Exception:
                        pass
        novos = [o for o in bpy.data.objects if o not in antes]

        # leva o preset para o cursor 3D em vez de despeja-lo na origem
        raizes = [o for o in novos if o.parent is None or o.parent not in novos]
        desloc = context.scene.cursor.location.copy()
        for o in raizes:
            o.location = o.location + desloc

        for o in context.selected_objects:
            o.select_set(False)
        for o in novos:
            try:
                o.select_set(True)
            except Exception:
                pass
        self.report({'INFO'}, "%d objeto(s) inserido(s)" % len(novos))
        return {'FINISHED'}


class OBJECT_OT_navegar(Operator):
    """Seleciona um nivel da cascata"""
    bl_idname = "object.cabinet_navegar"
    bl_label = "Navegar"

    nivel: bpy.props.IntProperty(default=1)
    valor: bpy.props.StringProperty()

    def execute(self, context):
        s = context.scene
        if self.nivel == 1:
            s.chapa_n1 = "" if s.chapa_n1 == self.valor else self.valor
            s.chapa_n2 = ""
            s.chapa_n3 = ""
        elif self.nivel == 2:
            s.chapa_n2 = "" if s.chapa_n2 == self.valor else self.valor
            s.chapa_n3 = ""
        else:
            s.chapa_n3 = "" if s.chapa_n3 == self.valor else self.valor
        return {'FINISHED'}


# ======================================= MINIATURAS E WIREFRAME DE MEDIDAS
_previews = [None]

# O canvas e o scale do template sao fixos de proposito: alargar a sidebar
# nao deve ampliar a representacao. Cada proporcao e' normalizada para ocupar
# a area util maxima sem deformar ou ultrapassar as margens internas.
WIREFRAME_LARGURA_PX = 320
WIREFRAME_ALTURA_PX = 160
WIREFRAME_MARGEM_X_PX = 28.0
WIREFRAME_MARGEM_Y_PX = 28.0
WIREFRAME_LINHA_PX = 1.4
WIREFRAME_ESCALA_UI = 20.0
WIREFRAME_CACHE_MAX = 48
WIREFRAME_PREFIXO = "wireframe:v7:"
_wireframe_ordem = []

# Vertices: frente (0, 1, 5, 4), fundo (2, 3, 7, 6) e ligacoes.
_ARESTAS_WIREFRAME = (
    (0, 1), (1, 5), (5, 4), (4, 0),
    (2, 3), (3, 7), (7, 6), (6, 2),
    (0, 2), (1, 3), (5, 7), (4, 6),
)

# Fonte minima 5x7. Os indicadores fazem parte do buffer procedural e nao
# dependem de fontes instaladas no sistema.
_FONTE_WIREFRAME = {
    'A': ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    'C': ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    'L': ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    'P': ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
}


def _colecao_previews():
    if _previews[0] is None:
        _previews[0] = bpy.utils.previews.new()
    return _previews[0]


def _cor_wireframe(context):
    """Cor de texto do tema, para contrastar em temas claros e escuros."""
    try:
        cor = context.preferences.themes[0].user_interface.wcol_regular.text
        return tuple(max(0.0, min(1.0, float(v))) for v in cor[:3])
    except Exception:
        return (0.9, 0.9, 0.9)


def _pontos_wireframe(largura, altura, profundidade):
    """Projeta a 45 graus e ajusta a proporcao a area util do canvas."""
    medidas = (float(largura), float(altura), float(profundidade))
    if not all(math.isfinite(v) and v > 0.0 for v in medidas):
        return None
    L, A, P = medidas
    vertices = (
        (0.0, 0.0, 0.0), (L, 0.0, 0.0),
        (0.0, P, 0.0), (L, P, 0.0),
        (0.0, 0.0, A),   (L, 0.0, A),
        (0.0, P, A),     (L, P, A),
    )
    diagonal = math.sqrt(0.5)  # cos(45) == sin(45)
    projetados = [(x - y * diagonal, z + y * diagonal)
                  for x, y, z in vertices]
    min_x = min(p[0] for p in projetados)
    max_x = max(p[0] for p in projetados)
    min_y = min(p[1] for p in projetados)
    max_y = max(p[1] for p in projetados)
    largura_proj = max_x - min_x
    altura_proj = max_y - min_y
    util_l = WIREFRAME_LARGURA_PX - 2.0 * WIREFRAME_MARGEM_X_PX
    util_a = WIREFRAME_ALTURA_PX - 2.0 * WIREFRAME_MARGEM_Y_PX
    if (largura_proj <= 0.0 or altura_proj <= 0.0 or
            util_l <= 0.0 or util_a <= 0.0):
        return None

    escala = min(util_l / largura_proj, util_a / altura_proj)
    desenho_l = largura_proj * escala
    desenho_a = altura_proj * escala
    dx = (WIREFRAME_LARGURA_PX - desenho_l) / 2.0 - min_x * escala
    dy = (WIREFRAME_ALTURA_PX - desenho_a) / 2.0 - min_y * escala
    return [(x * escala + dx, y * escala + dy) for x, y in projetados]


def _desenhar_segmento(buffer, p0, p1, cor):
    """Rasteriza um segmento antialias somente dentro de sua caixa local."""
    largura = WIREFRAME_LARGURA_PX
    altura = WIREFRAME_ALTURA_PX
    x0, y0 = p0
    x1, y1 = p1
    vx, vy = x1 - x0, y1 - y0
    comp2 = vx * vx + vy * vy
    if comp2 <= 1e-12:
        return
    raio = WIREFRAME_LINHA_PX / 2.0
    alcance = raio + 1.0
    xa = max(0, int(math.floor(min(x0, x1) - alcance)))
    xb = min(largura - 1, int(math.ceil(max(x0, x1) + alcance)))
    ya = max(0, int(math.floor(min(y0, y1) - alcance)))
    yb = min(altura - 1, int(math.ceil(max(y0, y1) + alcance)))
    cr, cg, cb = cor

    for y in range(ya, yb + 1):
        py = y + 0.5
        for x in range(xa, xb + 1):
            px = x + 0.5
            t = ((px - x0) * vx + (py - y0) * vy) / comp2
            t = max(0.0, min(1.0, t))
            perto_x = x0 + t * vx
            perto_y = y0 + t * vy
            distancia = math.hypot(px - perto_x, py - perto_y)
            cobertura = max(0.0, min(1.0, raio + 0.75 - distancia))
            if cobertura <= 0.0:
                continue
            # ImagePreview usa a origem embaixo; os pontos tambem usam Y para
            # cima, portanto nao e' preciso inverter a linha neste buffer.
            i = (y * largura + x) * 4
            if cobertura > buffer[i + 3]:
                buffer[i] = cr
                buffer[i + 1] = cg
                buffer[i + 2] = cb
                buffer[i + 3] = cobertura


def _desenhar_indicador(buffer, letra, x, y, cor, escala=2):
    """Desenha uma letra 5x7 centralizada em (x, y)."""
    glifo = _FONTE_WIREFRAME.get(letra)
    if glifo is None:
        return
    largura = len(glifo[0]) * escala
    altura = len(glifo) * escala
    inicio_x = int(round(x - largura / 2.0))
    inicio_y = int(round(y - altura / 2.0))
    cr, cg, cb = cor
    for linha, bits in enumerate(reversed(glifo)):
        for coluna, bit in enumerate(bits):
            if bit != '1':
                continue
            for sy in range(escala):
                py = inicio_y + linha * escala + sy
                if py < 0 or py >= WIREFRAME_ALTURA_PX:
                    continue
                for sx in range(escala):
                    px = inicio_x + coluna * escala + sx
                    if px < 0 or px >= WIREFRAME_LARGURA_PX:
                        continue
                    i = (py * WIREFRAME_LARGURA_PX + px) * 4
                    buffer[i] = cr
                    buffer[i + 1] = cg
                    buffer[i + 2] = cb
                    buffer[i + 3] = 1.0


def _meio_wireframe(p0, p1):
    return ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)


def _desenhar_indicadores(buffer, pontos, cor, modo):
    """Identifica as direcoes sem adicionar cotas ou linhas auxiliares."""
    topo = _meio_wireframe(pontos[6], pontos[7])
    fundo = _meio_wireframe(pontos[0], pontos[2])
    _desenhar_indicador(buffer, 'L', topo[0], topo[1] + 16.0, cor)
    if modo == 'INDIVIDUAL':
        _desenhar_indicador(
            buffer, 'C', fundo[0] - 15.0, fundo[1] - 14.0, cor)
    else:
        vertical = _meio_wireframe(pontos[2], pontos[6])
        _desenhar_indicador(
            buffer, 'A', vertical[0] - 18.0, vertical[1], cor)
        _desenhar_indicador(
            buffer, 'P', fundo[0] - 15.0, fundo[1] - 14.0, cor)


def _rasterizar_wireframe(largura, altura, profundidade, cor, modo='GRUPO'):
    """Devolve pixels RGBA transparentes das 12 arestas do box."""
    pontos = _pontos_wireframe(largura, altura, profundidade)
    if pontos is None:
        return None
    n = WIREFRAME_LARGURA_PX * WIREFRAME_ALTURA_PX * 4
    buffer = [0.0] * n
    for a, b in _ARESTAS_WIREFRAME:
        _desenhar_segmento(buffer, pontos[a], pontos[b], cor)
    _desenhar_indicadores(buffer, pontos, cor, modo)
    return buffer


def _chave_wireframe(modo, largura, altura, profundidade, cor):
    medidas = tuple(round(float(v), 1)
                    for v in (largura, altura, profundidade))
    rgb = tuple(round(float(v) * 255.0) for v in cor)
    return WIREFRAME_PREFIXO + "%s:%.1f:%.1f:%.1f:%d:%d:%d" % (
        modo, medidas[0], medidas[1], medidas[2], rgb[0], rgb[1], rgb[2])


def _registrar_uso_wireframe(chave, colecao):
    if chave in _wireframe_ordem:
        _wireframe_ordem.remove(chave)
    _wireframe_ordem.append(chave)
    while len(_wireframe_ordem) > WIREFRAME_CACHE_MAX:
        antiga = _wireframe_ordem.pop(0)
        if antiga in colecao:
            try:
                del colecao[antiga]
            except Exception:
                pass


def _icone_wireframe(context, modo, largura, altura, profundidade):
    """Cria ou reutiliza o icon_id horizontal para estas medidas."""
    cor = _cor_wireframe(context)
    chave = _chave_wireframe(modo, largura, altura, profundidade, cor)
    colecao = _colecao_previews()
    if chave not in colecao:
        pixels = _rasterizar_wireframe(
            largura, altura, profundidade, cor, modo=modo)
        if pixels is None:
            return 0
        try:
            preview = colecao.new(chave)
            tamanho = (WIREFRAME_LARGURA_PX, WIREFRAME_ALTURA_PX)
            # Preenche os dois niveis: template_icon pode escolher o buffer
            # de icone ou imagem conforme a escala do Blender.
            preview.icon_size = tamanho
            preview.icon_pixels_float = pixels
            preview.image_size = tamanho
            preview.image_pixels_float = pixels
        except Exception as e:
            if chave in colecao:
                try:
                    del colecao[chave]
                except Exception:
                    pass
            print("[Cabinet Creator] wireframe:", e)
            return 0
    _registrar_uso_wireframe(chave, colecao)
    return colecao[chave].icon_id


def _chave_preview(pasta, arquivo):
    return os.path.join(pasta, arquivo)


def icone_do_item(it):
    """icon_value da foto do preset, ou 0 se nao houver."""
    png = it.get("foto") or (os.path.splitext(it["arquivo"])[0] + ".png")
    caminho = os.path.join(it["pasta"], png)
    if not os.path.exists(caminho):
        return 0
    col = _colecao_previews()
    chave = _chave_preview(it["pasta"], png)
    if chave not in col:
        try:
            col.load(chave, caminho, 'IMAGE')
        except Exception:
            return 0
    return col[chave].icon_id


def capturar_viewport(destino_png, camera=None, isolar=None):
    """Foto do modelo a partir da viewport.

    NAO renderiza: usa render OpenGL, ou seja, as cores da propria
    viewport. Overlays desligados removem grade, eixos, gizmos e icones.

    camera  -- se informada, usa a vista dela. Se nao, e a viewport ja'
               estiver em vista de camera, mantem essa vista; caso
               contrario usa o enquadramento atual da viewport.
    isolar  -- lista de objetos que devem aparecer. Todo o resto da cena
               e' ocultado durante a captura e restaurado depois, para
               que um modulo dentro de uma composicao maior saia sozinho
               na foto.
    """
    cena = bpy.context.scene
    ant = (cena.render.filepath, cena.render.image_settings.file_format,
           cena.render.resolution_x, cena.render.resolution_y,
           cena.render.resolution_percentage, cena.render.film_transparent)
    area = next((a for a in bpy.context.screen.areas if a.type == 'VIEW_3D'), None)
    if area is None:
        return False, "Nenhuma viewport 3D visivel"

    espaco = area.spaces.active
    r3d = espaco.region_3d
    ov_ant = espaco.overlay.show_overlays
    persp_ant = r3d.view_perspective
    cam_ant = cena.camera
    escondidos = []

    try:
        if isolar is not None:
            manter = set()
            for o in isolar:
                manter.add(o.name)
                for f in bpy.data.objects:
                    if f.parent is o:
                        manter.add(f.name)
            for o in bpy.context.view_layer.objects:
                if o.name not in manter and not o.hide_get():
                    o.hide_set(True)
                    escondidos.append(o)

        cena.render.image_settings.file_format = 'PNG'
        cena.render.resolution_x = 512
        cena.render.resolution_y = 512
        cena.render.resolution_percentage = 100
        cena.render.filepath = destino_png
        espaco.overlay.show_overlays = False

        if camera is not None:
            cena.camera = camera
            r3d.view_perspective = 'CAMERA'
        # sem camera: mantem o que ja' esta' na tela (inclusive se ja'
        # estiver em vista de camera) -- o enquadramento e' do usuario

        regiao = next((r for r in area.regions if r.type == 'WINDOW'), None)
        with bpy.context.temp_override(area=area, region=regiao):
            bpy.ops.render.opengl(write_still=True, view_context=True)
        return True, destino_png
    except Exception as e:
        return False, str(e)
    finally:
        for o in escondidos:
            try:
                o.hide_set(False)
            except Exception:
                pass
        espaco.overlay.show_overlays = ov_ant
        r3d.view_perspective = persp_ant
        cena.camera = cam_ant
        (cena.render.filepath, cena.render.image_settings.file_format,
         cena.render.resolution_x, cena.render.resolution_y,
         cena.render.resolution_percentage, cena.render.film_transparent) = ant


def viewport_em_camera():
    area = next((a for a in bpy.context.screen.areas if a.type == 'VIEW_3D'), None)
    if area is None:
        return False
    return area.spaces.active.region_3d.view_perspective == 'CAMERA'


def _achar_item(pasta, arquivo):
    for it in indice_completo():
        if it["pasta"] == pasta and it["arquivo"] == arquivo:
            return it
    return None


# ============================== BLOQUEIO, RENOMEAR E ORDEM DOS BLOCOS
def _atualizar_item(pasta, arquivo, mudancas):
    itens = _ler_indice(pasta)
    for i in itens:
        if i.get("arquivo") == arquivo:
            i.update(mudancas)
    _gravar_indice(pasta, itens)


def item_bloqueado(it):
    """Presets de fabrica sao sempre bloqueados: a pasta deles e'
    sobrescrita a cada atualizacao do addon."""
    if it.get("origem") == "fabrica":
        return True
    return bool(it.get("bloqueado", False))


class OBJECT_OT_alternar_bloqueio(Operator):
    """Bloqueia ou desbloqueia a edicao deste bloco"""
    bl_idname = "object.cabinet_bloqueio"
    bl_label = "Bloquear/Desbloquear"

    pasta: bpy.props.StringProperty()
    arquivo: bpy.props.StringProperty()

    def execute(self, context):
        it = _achar_item(self.pasta, self.arquivo)
        if it is None:
            return {'CANCELLED'}
        if it.get("origem") == "fabrica":
            self.report({'WARNING'}, "Preset de fabrica e' sempre bloqueado")
            return {'CANCELLED'}
        _atualizar_item(self.pasta, self.arquivo,
                        {"bloqueado": not bool(it.get("bloqueado", False))})
        return {'FINISHED'}


class OBJECT_OT_renomear_item(Operator):
    """Renomear este bloco"""
    bl_idname = "object.cabinet_renomear"
    bl_label = "Renomear"
    bl_options = {'REGISTER'}

    pasta: bpy.props.StringProperty()
    arquivo: bpy.props.StringProperty()
    nome: bpy.props.StringProperty(name="Nome")

    def invoke(self, context, event):
        it = _achar_item(self.pasta, self.arquivo)
        if it is None:
            return {'CANCELLED'}
        if item_bloqueado(it):
            self.report({'WARNING'}, "Bloco bloqueado: destrave o cadeado")
            return {'CANCELLED'}
        self.nome = it.get("nome", "")
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        self.layout.prop(self, "nome")

    def execute(self, context):
        it = _achar_item(self.pasta, self.arquivo)
        if it is None or item_bloqueado(it):
            return {'CANCELLED'}
        _atualizar_item(self.pasta, self.arquivo, {"nome": self.nome})
        return {'FINISHED'}


class OBJECT_OT_mover_item(Operator):
    """Move o bloco na ordem da grade.

    O Blender nao expoe reordenacao por arraste em paineis -- nem
    UIList tem isso, ela usa setas. Estas setas sao o equivalente
    disponivel na API.
    """
    bl_idname = "object.cabinet_mover"
    bl_label = "Mover"

    pasta: bpy.props.StringProperty()
    arquivo: bpy.props.StringProperty()
    direcao: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        itens = _ler_indice(self.pasta)
        for n, i in enumerate(itens):
            if "ordem" not in i:
                i["ordem"] = n
        itens.sort(key=lambda i: i.get("ordem", 0))
        idx = next((n for n, i in enumerate(itens)
                    if i.get("arquivo") == self.arquivo), None)
        if idx is None:
            return {'CANCELLED'}
        novo = idx + self.direcao
        if novo < 0 or novo >= len(itens):
            return {'CANCELLED'}
        itens[idx], itens[novo] = itens[novo], itens[idx]
        for n, i in enumerate(itens):
            i["ordem"] = n
        _gravar_indice(self.pasta, itens)
        return {'FINISHED'}


class OBJECT_OT_editar_modelo(Operator):
    """Editar nome, categoria e foto do modelo"""
    bl_idname = "object.cabinet_editar_modelo"
    bl_label = "Editar Modelo"
    bl_options = {'REGISTER'}

    pasta: bpy.props.StringProperty()
    arquivo: bpy.props.StringProperty()
    nome: bpy.props.StringProperty(name="Nome")
    n1: bpy.props.EnumProperty(name="Categoria",
                               items=lambda s, c: [(k, k, "") for k in ARVORE.keys()])
    n2: bpy.props.StringProperty(name="Subcategoria")
    n3: bpy.props.StringProperty(name="Tipo")
    tirar_foto: bpy.props.BoolProperty(
        name="Capturar foto da viewport", default=False,
        description="Salva o enquadramento atual da viewport 3D como foto do modelo")

    def invoke(self, context, event):
        it = _achar_item(self.pasta, self.arquivo)
        if it:
            self.nome = it.get("nome", "")
            a, b, c = _niveis_de(it)
            try:
                self.n1 = a or "Armarios"
            except Exception:
                pass
            self.n2, self.n3 = b, c
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        lay = self.layout
        lay.prop(self, "nome")
        lay.prop(self, "n1")
        lay.prop(self, "n2")
        lay.prop(self, "n3")
        lay.separator()
        it = _achar_item(self.pasta, self.arquivo)
        icone = icone_do_item(it) if it else 0
        cx = lay.box()
        cx.label(text="Foto do modelo")
        if icone:
            cx.template_icon(icon_value=icone, scale=6.0)
        else:
            cx.label(text="sem foto", icon='IMAGE_DATA')
        cx.prop(self, "tirar_foto")

    def execute(self, context):
        it = _achar_item(self.pasta, self.arquivo)
        if it is None:
            self.report({'ERROR'}, "Preset nao encontrado no indice")
            return {'CANCELLED'}
        if item_bloqueado(it):
            self.report({'WARNING'}, "Bloco bloqueado: destrave o cadeado")
            return {'CANCELLED'}

        png = os.path.splitext(self.arquivo)[0] + ".png"
        if self.tirar_foto:
            cam = next((o for o in context.selected_objects if o.type == 'CAMERA'), None)
            alvo = [o for o in context.selected_objects if o.type != 'CAMERA']
            ok, msg = capturar_viewport(os.path.join(self.pasta, png), cam,
                                        isolar=alvo or None)
            if not ok:
                self.report({'WARNING'}, "Foto falhou: " + msg)
            else:
                chave = _chave_preview(self.pasta, png)
                col = _colecao_previews()
                if chave in col:
                    del col[chave]

        itens = _ler_indice(self.pasta)
        for i in itens:
            if i.get("arquivo") == self.arquivo:
                i["nome"] = self.nome
                i["n1"] = self.n1
                i["n2"] = self.n2
                i["n3"] = self.n3
                i.pop("categoria", None)
                i.pop("subcategoria", None)
                i["foto"] = png
        _gravar_indice(self.pasta, itens)
        self.report({'INFO'}, "Modelo atualizado")
        return {'FINISHED'}


class OBJECT_OT_salvar_biblioteca(Operator):
    """Salva a selecao na biblioteca de assets do Blender"""
    bl_idname = "object.cabinet_salvar_biblioteca"
    bl_label = "Salvar na Biblioteca"
    bl_options = {'REGISTER'}

    nome: bpy.props.StringProperty(name="Nome do preset", default="Preset")
    n1: bpy.props.EnumProperty(name="Categoria",
                               items=lambda s, c: [(k, k, "") for k in ARVORE.keys()])
    n2: bpy.props.StringProperty(name="Subcategoria", default="")
    n3: bpy.props.StringProperty(name="Tipo", default="")
    com_foto: bpy.props.BoolProperty(
        name="Gerar foto da viewport", default=True,
        description="Usa as cores da viewport, sem grade nem icones. "
                    "Se houver uma camera na selecao, usa a vista dela")
    como_modulo: bpy.props.BoolProperty(
        name="Como modulo (varias pecas)", default=True,
        description="Ligado: salva como Collection (arrasta o conjunto inteiro). "
                    "Desligado: salva cada chapa como objeto separado")

    def invoke(self, context, event):
        sel = [o for o in context.selected_objects]
        if len(sel) == 1 and sel[0].type == 'MESH':
            self.como_modulo = False
            self.nome = sel[0].name
        elif sel:
            self.nome = "Modulo"
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        sel = [o for o in context.selected_objects]
        if not sel:
            self.report({'WARNING'}, "Nada selecionado")
            return {'CANCELLED'}
        # inclui filhos dos Empties de conjunto selecionados
        completos = list(sel)
        for o in sel:
            if MARCA_CONJUNTO in o:
                completos += [f for f in bpy.data.objects if f.parent == o]
        completos = list(dict.fromkeys(completos))
        try:
            arq = salvar_na_biblioteca(completos, self.nome, self.como_modulo)
            n2 = self.n2 or (_filhos_n2(self.n1) or [""])[0]
            n3 = self.n3 or (_filhos_n3(self.n1, n2) or [""])[0]
            png = os.path.splitext(os.path.basename(arq))[0] + ".png"
            if self.com_foto:
                cam = next((o for o in sel if o.type == 'CAMERA'), None)
                alvo = [o for o in completos if o.type != 'CAMERA']
                okf, msg = capturar_viewport(os.path.join(_pasta_equipe(), png), cam,
                                             isolar=alvo or None)
                if not okf:
                    self.report({'WARNING'}, "Foto falhou: " + msg)
            registrar_no_indice(_pasta_equipe(), self.nome, arq, self.n1, n2, n3,
                                "modulo" if self.como_modulo else "objeto")
        except Exception as e:
            self.report({'ERROR'}, "Falha ao salvar: %s" % e)
            return {'CANCELLED'}
        self.report({'INFO'}, "Salvo em %s" % arq)
        return {'FINISHED'}


class OBJECT_OT_abrir_pasta_biblioteca(Operator):
    """Mostra o caminho da biblioteca no Explorer"""
    bl_idname = "object.cabinet_abrir_biblioteca"
    bl_label = "Abrir Pasta da Biblioteca"

    def execute(self, context):
        raiz, destino = _pasta_biblioteca()
        bpy.ops.wm.path_open(filepath=destino)
        self.report({'INFO'}, destino)
        return {'FINISHED'}


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


def verificar_periodicamente():
    if not _ocupado[0] and not _ha_modal_ativo():
        try:
            absorver_conjuntos()
            normalizar_chapas()
        except Exception as e:
            print("[Cabinet Creator] erro no timer:", e)
    return INTERVALO_TIMER


class OBJECT_OT_normalizar(Operator):
    """Recalcula as chapas selecionadas a partir da escala aplicada"""
    bl_idname = "object.cabinet_normalizar"
    bl_label = "Recalcular Chapas"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        alvo = context.selected_objects or bpy.data.objects
        ajustadas = normalizar_chapas(alvo)
        self.report({'INFO'}, "%d chapa(s) recalculada(s)" % len(ajustadas))
        return {'FINISHED'}


# ================================================== CRIACAO DE OBJETOS
def nova_chapa(nome, larg, comp, esp, loc_mm, rot_graus, context):
    malha = bpy.data.meshes.new(nome)
    obj = bpy.data.objects.new(nome, malha)
    context.collection.objects.link(obj)
    obj[MARCA_CHAPA] = 1
    _ocupado[0] = True
    try:
        obj.chapa_largura_mm = larg
        obj.chapa_comprimento_mm = comp
        obj.chapa_espessura_mm = esp
    finally:
        _ocupado[0] = False
    obj.location = tuple(v / 1000.0 for v in loc_mm)
    obj.rotation_euler = tuple(math.radians(a) for a in rot_graus)
    gerar_malha_chapa(obj)
    return obj


class OBJECT_OT_criar_chapa(Operator):
    """Cria uma chapa avulsa (600 x 400 x 18mm)"""
    bl_idname = "object.cabinet_criar"
    bl_label = "Criar Chapa"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = nova_chapa("Chapa", 600.0, 400.0, 18.0, (0, 0, 0), (0, 0, 0), context)
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {'FINISHED'}


class OBJECT_OT_criar_nicho(Operator):
    """Cria um nicho sem fundo: 2 laterais + tampo + base"""
    bl_idname = "object.cabinet_criar_nicho"
    bl_label = "Criar Nicho (sem fundo)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        L, A, P, E = 600.0, 400.0, 300.0, 18.0
        li = L - 2 * E
        pecas = [
            ("Lateral_Esq", A, P, E, (-(L / 2 - E / 2), 0, A / 2), (0, 90, 0)),
            ("Lateral_Dir", A, P, E, ((L / 2 - E / 2), 0, A / 2), (0, 90, 0)),
            ("Base",        li, P, E, (0, 0, E / 2), (0, 0, 0)),
            ("Tampo",       li, P, E, (0, 0, A - E / 2), (0, 0, 0)),
        ]
        for o in context.selected_objects:
            o.select_set(False)
        criadas = [nova_chapa(n, la, c, e, lo, r, context) for n, la, c, e, lo, r in pecas]
        for c in criadas:
            c.select_set(True)
        context.view_layer.objects.active = criadas[0]
        return {'FINISHED'}


class OBJECT_OT_marcar_como_chapa(Operator):
    """Converte o objeto selecionado em chapa G3"""
    bl_idname = "object.cabinet_marcar"
    bl_label = "Marcar como Chapa"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'

    def execute(self, context):
        obj = context.object
        obj[MARCA_CHAPA] = 1
        gerar_malha_chapa(obj)
        return {'FINISHED'}


def _grupo_ativo(context):
    o = context.object
    if o is None:
        return []
    if MARCA_CONJUNTO in o:
        return _chapas_do_conjunto(o)
    return grupo_de(o)


def sincronizar_grupo(context):
    """Le a caixa real do grupo e grava nos campos da cena."""
    chapas = _grupo_ativo(context)
    cx = _caixa_de(chapas)
    if cx is None:
        return
    lo, hi = cx
    s = context.scene
    _ocupado[0] = True
    try:
        s.grupo_largura_mm = (hi[0]-lo[0]) * 1000.0
        s.grupo_altura_mm = (hi[2]-lo[2]) * 1000.0
        s.grupo_profundidade_mm = (hi[1]-lo[1]) * 1000.0
        s.grupo_espessura_mm = chapas[0].chapa_espessura_mm
    finally:
        _ocupado[0] = False


def _upd_grupo_dim(self, context):
    if _ocupado[0]:
        return
    chapas = _grupo_ativo(context)
    if not chapas:
        return
    redimensionar_grupo(chapas, (self.grupo_largura_mm, self.grupo_altura_mm,
                                 self.grupo_profundidade_mm))
    pai = chapas[0].parent if chapas else None
    if pai is not None and MARCA_CONJUNTO in pai:
        reposicionar_origem(pai)


def _upd_grupo_espessura(self, context):
    if _ocupado[0]:
        return
    val = self.grupo_espessura_mm
    alvo = min(ESPESSURAS_PERMITIDAS, key=lambda v: abs(v - val))
    if abs(val - alvo) > 1e-6:
        _ocupado[0] = True
        try:
            self.grupo_espessura_mm = alvo
        finally:
            _ocupado[0] = False
    chapas = _grupo_ativo(context)
    if chapas:
        aplicar_espessura_grupo(chapas, alvo)
        pai = chapas[0].parent
        if pai is not None and MARCA_CONJUNTO in pai:
            reposicionar_origem(pai)


class OBJECT_OT_sincronizar_grupo(Operator):
    """Le as medidas reais do grupo e atualiza os campos"""
    bl_idname = "object.cabinet_sincronizar_grupo"
    bl_label = "Ler Medidas do Grupo"

    def execute(self, context):
        sincronizar_grupo(context)
        return {'FINISHED'}


class CabinetCreatorPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    pasta_equipe: bpy.props.StringProperty(
        name="Biblioteca da equipe",
        subtype='DIR_PATH',
        description="Pasta onde os presets sao gravados. Aponte para uma "
                    "pasta de rede para compartilhar entre os computadores",
        default="")

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "pasta_equipe")
        layout.label(text="De fabrica: " + _pasta_fabrica(), icon='FILE_FOLDER')
        layout.label(text="Em uso: " + _pasta_equipe(), icon='ASSET_MANAGER')
        layout.operator("object.cabinet_registrar_bibliotecas", icon='FILE_REFRESH')


class OBJECT_OT_registrar_bibliotecas(Operator):
    """Registra as pastas do addon como bibliotecas de assets"""
    bl_idname = "object.cabinet_registrar_bibliotecas"
    bl_label = "Registrar Bibliotecas no Blender"

    def execute(self, context):
        novas = registrar_bibliotecas(silencioso=False)
        if novas:
            self.report({'INFO'}, "Registrada(s): " + ", ".join(novas))
        else:
            self.report({'INFO'}, "Bibliotecas ja estavam registradas")
        return {'FINISHED'}


class OBJECT_OT_modo_medidas(Operator):
    """Alterna a edicao entre uma chapa e o conjunto"""
    bl_idname = "object.cabinet_modo_medidas"
    bl_label = "Modo de Medidas"
    bl_options = {'INTERNAL'}

    modo: StringProperty()

    def execute(self, context):
        obj = context.object
        if obj is None:
            return {'CANCELLED'}
        if self.modo == 'INDIVIDUAL' and MARCA_CONJUNTO in obj:
            chapas = _chapas_do_conjunto(obj)
            if not chapas:
                self.report({'WARNING'}, "Modulo sem chapas")
                return {'CANCELLED'}
            alvo = chapas[0]
            for selecionado in context.selected_objects:
                selecionado.select_set(False)
            alvo.select_set(True)
            context.view_layer.objects.active = alvo
            alvo.chapa_modo = 'INDIVIDUAL'
        elif MARCA_CHAPA in obj:
            obj.chapa_modo = self.modo
        elif self.modo != 'GRUPO':
            return {'CANCELLED'}
        return {'FINISHED'}


class VIEW3D_PT_cabinet_creator(Panel):
    bl_label = "Cabinet Creator"
    bl_idname = "VIEW3D_PT_cabinet_creator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Cabinet Creator"

    def draw(self, context):
        layout = self.layout
        self.desenhar_medidas(context, layout)
        layout.separator()
        self.desenhar_biblioteca(context, layout)

    # ------------------------------------------------------- MEDIDAS
    def _abas_modo(self, layout, ativo):
        linha = layout.row(align=True)
        for modo, texto in (('INDIVIDUAL', "Individual"), ('GRUPO', "Grupo")):
            op = linha.operator(
                "object.cabinet_modo_medidas", text=texto,
                depress=(ativo == modo))
            op.modo = modo

    def _visual_wireframe(self, layout, context, modo, medidas):
        """Desenha o preview em tamanho fixo, independente da sidebar."""
        coluna = layout.column(align=False)
        coluna.alignment = 'CENTER'
        icone = _icone_wireframe(context, modo, *medidas)
        if icone:
            coluna.template_icon(
                icon_value=icone, scale=WIREFRAME_ESCALA_UI)
        else:
            coluna.label(text="", icon='MESH_CUBE')

    def _campo_medida(self, layout, dados, propriedade, texto):
        """Rotulo completo acima e campo compacto logo abaixo."""
        bloco = layout.column(align=True)
        bloco.alignment = 'LEFT'
        rotulo = bloco.row(align=True)
        rotulo.alignment = 'LEFT'
        rotulo.label(text=texto)
        valor = bloco.row(align=True)
        valor.alignment = 'LEFT'
        valor.prop(dados, propriedade, text="")

    def _lista_espessuras(self, layout):
        linha = layout.row(align=True)
        linha.alignment = 'LEFT'
        linha.label(text="15/18/20/30")

    def desenhar_medidas(self, context, layout):
        obj = context.object

        if obj is not None and MARCA_CONJUNTO in obj:
            self._abas_modo(layout, 'GRUPO')
            b = layout.box()
            b.label(text="Modulo (%d pecas)" % len(_chapas_do_conjunto(obj)), icon='MOD_BUILD')
            corpo = b.row(align=False)
            campos = corpo.column(align=True)
            campos.alignment = 'LEFT'
            campos.ui_units_x = 9.2
            self._campo_medida(campos, obj, "ui_conj_largura", "Largura")
            self._campo_medida(campos, obj, "ui_conj_altura", "Altura")
            self._campo_medida(
                campos, obj, "ui_conj_profundidade", "Profundidade")
            self._campo_medida(
                campos, obj, "ui_conj_espessura", "Espessura")
            self._lista_espessuras(campos)
            self._visual_wireframe(
                corpo, context, 'GRUPO',
                (obj.conj_largura_mm, obj.conj_altura_mm,
                 obj.conj_profundidade_mm))
            b.operator("object.cabinet_sincronizar", icon='FILE_REFRESH')
        elif obj is None or MARCA_CHAPA not in obj:
            layout.label(text="Selecione uma chapa ou um modulo", icon='INFO')
        else:
            self._abas_modo(layout, obj.chapa_modo)
            b = layout.box()
            if obj.chapa_modo == 'INDIVIDUAL':
                corpo = b.row(align=False)
                campos = corpo.column(align=True)
                campos.alignment = 'LEFT'
                campos.ui_units_x = 9.2
                self._campo_medida(
                    campos, obj, "ui_chapa_largura", "Largura")
                self._campo_medida(
                    campos, obj, "ui_chapa_comprimento", "Comprimento")
                self._campo_medida(
                    campos, obj, "ui_chapa_espessura", "Espessura")
                self._lista_espessuras(campos)
                self._visual_wireframe(
                    corpo, context, 'INDIVIDUAL',
                    (obj.chapa_largura_mm, obj.chapa_espessura_mm,
                     obj.chapa_comprimento_mm))
                b.prop(obj, "chapa_auto")
            else:
                b.label(text="Grupo: %d peca(s)" % len(grupo_de(obj)), icon='MOD_BUILD')
                sc = context.scene
                corpo = b.row(align=False)
                campos = corpo.column(align=True)
                campos.alignment = 'LEFT'
                campos.ui_units_x = 9.2
                self._campo_medida(
                    campos, sc, "ui_grupo_largura", "Largura")
                self._campo_medida(
                    campos, sc, "ui_grupo_altura", "Altura")
                self._campo_medida(
                    campos, sc, "ui_grupo_profundidade", "Profundidade")
                self._campo_medida(
                    campos, sc, "ui_grupo_espessura", "Espessura")
                self._lista_espessuras(campos)
                self._visual_wireframe(
                    corpo, context, 'GRUPO',
                    (sc.grupo_largura_mm, sc.grupo_altura_mm,
                     sc.grupo_profundidade_mm))
                b.operator("object.cabinet_sincronizar_grupo", icon='FILE_REFRESH')

        layout.separator()
        c = layout.column(align=True)
        c.label(text="Montagem:")
        c.operator("object.cabinet_agrupar", icon='OUTLINER_OB_EMPTY')
        c.operator("object.cabinet_detectar_adjacencia", icon='SNAP_ON')
        c.operator("object.cabinet_normalizar", icon='FILE_REFRESH')

    # ---------------------------------------------------- BIBLIOTECA
    # Cascata HORIZONTAL: cada nivel e' uma linha de botoes. O nivel
    # selecionado fica azul (depress=True, o destaque nativo do Blender).
    def _linha_niveis(self, layout, nivel, valores, itens, sel, pai=None):
        if not valores:
            return
        linha = layout.row(align=True)
        for v in valores:
            if nivel == 1:
                n = _conta(itens, v)
            elif nivel == 2:
                n = _conta(itens, pai, v)
            else:
                n = _conta(itens, pai[0], pai[1], v)
            op = linha.operator("object.cabinet_navegar",
                                text="%s (%d)" % (v, n),
                                depress=(sel == v))
            op.nivel = nivel
            op.valor = v

    def desenhar_biblioteca(self, context, layout):
        s = context.scene
        itens = indice_completo()

        cab = layout.row(align=True)
        cab.prop(s, "chapa_bib_aberta",
                 icon='TRIA_DOWN' if s.chapa_bib_aberta else 'TRIA_RIGHT',
                 text="Biblioteca (%d)" % len(itens), toggle=True)
        # o "+" adiciona a selecao atual a biblioteca
        cab.operator("object.cabinet_salvar_biblioteca", text="", icon='ADD')
        if not s.chapa_bib_aberta:
            return

        menu = layout.box()
        self._linha_niveis(menu, 1, list(ARVORE.keys()), itens, s.chapa_n1)
        if s.chapa_n1:
            self._linha_niveis(menu, 2, _filhos_n2(s.chapa_n1), itens,
                               s.chapa_n2, pai=s.chapa_n1)
        if s.chapa_n1 and s.chapa_n2:
            self._linha_niveis(menu, 3, _filhos_n3(s.chapa_n1, s.chapa_n2), itens,
                               s.chapa_n3, pai=(s.chapa_n1, s.chapa_n2))

        if not s.chapa_n1 or not s.chapa_n2:
            return
        filhos3 = _filhos_n3(s.chapa_n1, s.chapa_n2)
        if filhos3 and not s.chapa_n3:
            return

        daqui = []
        for it in itens:
            a, b, c = _niveis_de(it)
            if a == s.chapa_n1 and b == s.chapa_n2 and (not filhos3 or c == s.chapa_n3):
                daqui.append(it)
        daqui.sort(key=lambda i: (i.get("ordem", 9999), i.get("nome", "")))

        lista = layout.box()
        trilha = " > ".join(x for x in (s.chapa_n1, s.chapa_n2, s.chapa_n3) if x)
        cab2 = lista.row(align=True)
        cab2.label(text=trilha, icon='ASSET_MANAGER')
        cab2.prop(s, "chapa_tam_bloco", text="")
        if not daqui:
            lista.label(text="nenhum modelo aqui", icon='INFO')
            lista.operator("object.cabinet_abrir_biblioteca", icon='FILE_FOLDER')
            return

        # columns=0 faz o grid_flow calcular sozinho quantas colunas cabem
        # na largura atual do painel -- e' o mecanismo responsivo nativo.
        grade = lista.grid_flow(row_major=True, columns=0,
                                even_columns=True, even_rows=True, align=False)

        for n, it in enumerate(daqui):
            icone = icone_do_item(it)
            travado = item_bloqueado(it)
            bloco = grade.box().column(align=True)

            topo = bloco.row(align=True)
            if icone:
                # com imagem: cadeado a esquerda, tres barrinhas a direita
                # (o layout do bpy nao permite sobrepor o icone a imagem)
                self._cadeado(topo, it, travado)
                topo.separator()
                self._menu(topo, it, travado)
            else:
                # sem imagem: tres barrinhas na extrema esquerda
                self._menu(topo, it, travado)
                topo.separator()
                self._cadeado(topo, it, travado)

            if icone:
                bloco.template_icon(icon_value=icone,
                                    scale=float(s.chapa_tam_bloco))
            else:
                vazio = bloco.box()
                vazio.scale_y = float(s.chapa_tam_bloco) * 0.5
                vazio.label(text="", icon='IMAGE_DATA')

            oi = bloco.operator("object.cabinet_inserir_preset",
                                text=it["nome"], icon='IMPORT')
            oi.pasta = it["pasta"]
            oi.arquivo = it["arquivo"]
            oi.tipo = it.get("tipo", "modulo")

            if not travado:
                setas = bloco.row(align=True)
                oa = setas.operator("object.cabinet_mover", text="", icon='TRIA_LEFT')
                oa.pasta = it["pasta"]; oa.arquivo = it["arquivo"]; oa.direcao = -1
                ob = setas.operator("object.cabinet_mover", text="", icon='TRIA_RIGHT')
                ob.pasta = it["pasta"]; ob.arquivo = it["arquivo"]; ob.direcao = 1
                oe = setas.operator("object.cabinet_editar_modelo", text="", icon='GREASEPENCIL')
                oe.pasta = it["pasta"]; oe.arquivo = it["arquivo"]

        lista.separator()
        lista.operator("object.cabinet_abrir_biblioteca", icon='FILE_FOLDER')

    def _cadeado(self, linha, it, travado):
        """Cadeado clicavel, alternando entre os dois sprites."""
        oc = linha.operator("object.cabinet_bloqueio", text="",
                            icon='LOCKED' if travado else 'UNLOCKED',
                            depress=travado)
        oc.pasta = it["pasta"]
        oc.arquivo = it["arquivo"]

    def _menu(self, linha, it, travado):
        """Tres barrinhas -- so' aparece com o cadeado destravado."""
        if travado:
            linha.label(text="", icon='BLANK1')
            return
        om = linha.operator("object.cabinet_renomear", text="", icon='COLLAPSEMENU')
        om.pasta = it["pasta"]
        om.arquivo = it["arquivo"]


CLASSES = (
    CabinetCreatorPreferences,
    OBJECT_OT_sincronizar_grupo,
    OBJECT_OT_sincronizar_conjunto,
    OBJECT_OT_registrar_bibliotecas,
    OBJECT_OT_modo_medidas,
    OBJECT_OT_criar_chapa,
    OBJECT_OT_salvar_biblioteca,
    OBJECT_OT_abrir_pasta_biblioteca,
    OBJECT_OT_inserir_preset,
    OBJECT_OT_navegar,
    OBJECT_OT_editar_modelo,
    OBJECT_OT_alternar_bloqueio,
    OBJECT_OT_renomear_item,
    OBJECT_OT_mover_item,
    OBJECT_OT_agrupar_conjunto,
    OBJECT_OT_detectar_adjacencia,
    OBJECT_OT_criar_nicho,
    OBJECT_OT_marcar_como_chapa,
    OBJECT_OT_normalizar,
    VIEW3D_PT_cabinet_creator,
)


_PROPS_MEDIDA_UI_OBJETO = (
    "ui_chapa_largura", "ui_chapa_comprimento", "ui_chapa_espessura",
    "ui_conj_largura", "ui_conj_altura", "ui_conj_profundidade",
    "ui_conj_espessura",
)
_PROPS_MEDIDA_UI_CENA = (
    "ui_grupo_largura", "ui_grupo_altura", "ui_grupo_profundidade",
    "ui_grupo_espessura",
)


def _registrar_medida_ui(dono, nome_ui, nome_mm, nome, minimo_mm):
    """Expoe em metros para o parser nativo, mantendo o dado real em mm."""
    def obter(self):
        return float(getattr(self, nome_mm)) / 1000.0

    def definir(self, valor):
        setattr(self, nome_mm, float(valor) * 1000.0)

    setattr(dono, nome_ui, FloatProperty(
        name=nome,
        description="Sem sufixo usa a unidade da cena; aceita mm, cm e m",
        subtype='DISTANCE',
        unit='LENGTH',
        min=minimo_mm / 1000.0,
        precision=3,
        step=10,
        get=obter,
        set=definir))


def _garantir_unidade_padrao_mm():
    """Campos do addon usam milimetros como unidade implicita da cena."""
    # Durante addon_enable o Blender protege bpy.data com _RestrictData.
    # Adiar evita falha de ativacao e mantem esta configuracao fora do register.
    if not hasattr(bpy.data, "scenes"):
        if not bpy.app.timers.is_registered(_garantir_unidade_padrao_mm):
            bpy.app.timers.register(
                _garantir_unidade_padrao_mm, first_interval=0.0)
        return None
    for cena in bpy.data.scenes:
        unidades = cena.unit_settings
        unidades.system = 'METRIC'
        unidades.scale_length = 1.0
        unidades.length_unit = 'MILLIMETERS'


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    O = bpy.types.Object
    O.chapa_largura_mm = FloatProperty(
        name="Largura (mm)", default=600.0, min=1.0, update=_upd_chapa)
    O.chapa_comprimento_mm = FloatProperty(
        name="Comprimento (mm)", default=400.0, min=1.0, update=_upd_chapa)
    O.chapa_espessura_mm = FloatProperty(
        name="Espessura (mm)", default=18.0, min=1.0,
        description="Digite a espessura; sera arredondada para 15, 18, 20 ou 30",
        update=_upd_espessura)
    O.chapa_auto = BoolProperty(
        name="Auto-regenerar", default=True,
        description="Desligue para editar a malha a mao sem sobrescrever")
    O.conj_largura_mm = FloatProperty(
        name="Largura (mm)", default=600.0, min=20.0, update=_upd_conj_dim)
    O.conj_altura_mm = FloatProperty(
        name="Altura (mm)", default=400.0, min=20.0, update=_upd_conj_dim)
    O.conj_profundidade_mm = FloatProperty(
        name="Profundidade (mm)", default=300.0, min=20.0, update=_upd_conj_dim)
    O.conj_espessura_mm = FloatProperty(
        name="Espessura (mm)", default=18.0, min=1.0,
        description="Espessura de todas as chapas do modulo; sera arredondada",
        update=_upd_conj_espessura)
    O.chapa_modo = EnumProperty(
        name="Modo", default='INDIVIDUAL',
        items=[('INDIVIDUAL', "Individual", "Medidas desta chapa"),
               ('GRUPO', "Grupo", "Medidas do modulo inteiro")])
    _registrar_medida_ui(
        O, "ui_chapa_largura", "chapa_largura_mm", "Largura", 1.0)
    _registrar_medida_ui(
        O, "ui_chapa_comprimento", "chapa_comprimento_mm", "Comprimento", 1.0)
    _registrar_medida_ui(
        O, "ui_chapa_espessura", "chapa_espessura_mm", "Espessura", 1.0)
    _registrar_medida_ui(
        O, "ui_conj_largura", "conj_largura_mm", "Largura", 20.0)
    _registrar_medida_ui(
        O, "ui_conj_altura", "conj_altura_mm", "Altura", 20.0)
    _registrar_medida_ui(
        O, "ui_conj_profundidade", "conj_profundidade_mm", "Profundidade", 20.0)
    _registrar_medida_ui(
        O, "ui_conj_espessura", "conj_espessura_mm", "Espessura", 1.0)

    S = bpy.types.Scene
    S.chapa_bib_aberta = BoolProperty(name="Biblioteca", default=False)
    S.chapa_n1 = StringProperty(default="")
    S.chapa_n2 = StringProperty(default="")
    S.chapa_n3 = StringProperty(default="")
    S.chapa_tam_bloco = EnumProperty(
        name="Tamanho", default='5',
        items=[('3', "P", "Blocos pequenos"), ('5', "M", "Blocos medios"),
               ('8', "G", "Blocos grandes")])
    S.grupo_largura_mm = FloatProperty(name="Largura (mm)", default=600.0, min=20.0, update=_upd_grupo_dim)
    S.grupo_altura_mm = FloatProperty(name="Altura (mm)", default=400.0, min=20.0, update=_upd_grupo_dim)
    S.grupo_profundidade_mm = FloatProperty(name="Profundidade (mm)", default=300.0, min=20.0, update=_upd_grupo_dim)
    S.grupo_espessura_mm = FloatProperty(name="Espessura (mm)", default=18.0, min=1.0, update=_upd_grupo_espessura)
    _registrar_medida_ui(
        S, "ui_grupo_largura", "grupo_largura_mm", "Largura", 20.0)
    _registrar_medida_ui(
        S, "ui_grupo_altura", "grupo_altura_mm", "Altura", 20.0)
    _registrar_medida_ui(
        S, "ui_grupo_profundidade", "grupo_profundidade_mm", "Profundidade", 20.0)
    _registrar_medida_ui(
        S, "ui_grupo_espessura", "grupo_espessura_mm", "Espessura", 1.0)

    _garantir_unidade_padrao_mm()

    if ao_atualizar_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(ao_atualizar_depsgraph)
    if not bpy.app.timers.is_registered(verificar_periodicamente):
        bpy.app.timers.register(verificar_periodicamente, persistent=True)
    # bpy.ops nao pode rodar dentro de register(): adia por um tique
    bpy.app.timers.register(lambda: (registrar_bibliotecas(), None)[1], first_interval=0.5)


def unregister():
    if bpy.app.timers.is_registered(_garantir_unidade_padrao_mm):
        bpy.app.timers.unregister(_garantir_unidade_padrao_mm)
    if _previews[0] is not None:
        try:
            bpy.utils.previews.remove(_previews[0])
        except Exception:
            pass
        _previews[0] = None
    _wireframe_ordem.clear()
    if bpy.app.timers.is_registered(verificar_periodicamente):
        bpy.app.timers.unregister(verificar_periodicamente)
    if ao_atualizar_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(ao_atualizar_depsgraph)
    for nome in _PROPS_MEDIDA_UI_OBJETO:
        if hasattr(bpy.types.Object, nome):
            delattr(bpy.types.Object, nome)
    for nome in _PROPS_MEDIDA_UI_CENA:
        if hasattr(bpy.types.Scene, nome):
            delattr(bpy.types.Scene, nome)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
