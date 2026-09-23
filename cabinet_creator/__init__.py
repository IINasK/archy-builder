bl_info = {
    "name": "Cabinet Creator",
    "author": "Douglas",
    "version": (87, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > gaveta esquerda",
    "doc_url": "",
    "description": "Armarios parametricos: chapas com malha editavel e espessura imune a escala",
    "category": "Object",
}

import bpy, bmesh, math, os, uuid, json, gpu, blf, time
import bpy.utils.previews
from gpu_extras.batch import batch_for_shader
from bpy.props import (FloatProperty, BoolProperty, EnumProperty,
                       StringProperty, IntProperty, IntVectorProperty,
                       FloatVectorProperty)
from mathutils import Matrix, Vector
from mathutils.geometry import intersect_line_plane
from bpy_extras import view3d_utils
from bpy.types import Gizmo, GizmoGroup, Operator, Panel

ESPESSURAS_PERMITIDAS = [15.0, 18.0, 20.0, 30.0]

# Marcador ID. ATENCAO: propriedades criadas com bpy.props em
# bpy.types.Object sao RNA e NAO aparecem em `"x" in obj`.
# Os nomes das propriedades internas (chapa_*, eh_chapa, adj_*) sao
# deliberadamente mantidos do nome antigo do add-on: eles estao gravados
# dentro dos .blend dos presets. Renomea-los invalidaria toda a
# biblioteca ja' salva.
MARCA_CHAPA = "eh_chapa"
MARCA_CONJUNTO = "eh_conjunto_chapa"
MARCA_PORTAS = "eh_grupo_portas"
MARCA_FOLHA = "eh_folha_porta"

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


def _espessura_da_malha(obj):
    """Espessura REAL da malha, em mm. Quando o callback de update roda a
    PROP ja' foi trocada mas a malha ainda e' a antiga -- e' dela que sai
    a medida velha, necessaria para saber para que lado engrossar."""
    if obj is None or obj.type != 'MESH' or not obj.data.vertices:
        return None
    # sem multiplicar por scale.z: por invariante a escala em Z e'
    # descartada, entao a malha local e' o valor antigo da prop
    zs = [v.co.z for v in obj.data.vertices]
    return (max(zs) - min(zs)) * 1000.0


def _upd_espessura(self, context):
    """Arredonda o valor digitado para a espessura permitida mais proxima
    e engrossa a chapa para DENTRO do movel (ver aplicar_espessura_chapa)."""
    if _ocupado[0]:
        return
    val = self.chapa_espessura_mm
    alvo = min(ESPESSURAS_PERMITIDAS, key=lambda v: abs(v - val))
    e_velha = _espessura_da_malha(self)
    if abs(val - alvo) > 1e-6:
        _ocupado[0] = True
        try:
            self.chapa_espessura_mm = alvo
        finally:
            _ocupado[0] = False
    if (MARCA_CHAPA not in self or not self.chapa_auto
            or e_velha is None or abs(e_velha - alvo) < 1e-4):
        gerar_malha_chapa(self)
        return
    aplicar_espessura_chapa(self, alvo, e_velha)


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


def _vizinhos_gravados(C):
    """Vizinhos anotados em C pela deteccao de adjacencia (sentido C -> N)."""
    saida = []
    for eixo in ('x', 'y'):
        for lado in ('pos', 'neg'):
            N = _resolver_vizinho(C, C.get('adj_%s_%s_uid' % (eixo, lado), ''),
                                  C.get('adj_%s_%s' % (eixo, lado), ''))
            if N is not None:
                saida.append(N)
    return saida


def _grupo_solto(obj, simetrico):
    """Fecho transitivo da adjacencia para uma chapa sem Conjunto.

    Os vinculos de adjacencia sao de MAO UNICA: uma prateleira aponta
    para as laterais, mas nenhuma lateral aponta para a prateleira.
    Com simetrico=True o mapa e' montado nos dois sentidos, senao a
    travessia comecando por uma lateral perde as pecas internas.

    A varredura fica restrita aos IRMAOS (mesmo pai), igual a regra de
    `_resolver_vizinho`, para nao custar o arquivo inteiro a cada clique.
    """
    chapas = [o for o in bpy.data.objects if o.type == 'MESH'
              and MARCA_CHAPA in o and o.parent == obj.parent]
    ligacoes = {o.name: set() for o in chapas}
    porta = {o.name: o for o in chapas}
    for C in chapas:
        for N in _vizinhos_gravados(C):
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
    """Define o GRUPO de uma chapa: se ela pertence a um Conjunto,
    e' o conjunto inteiro; senao, e' ela mais tudo que estiver ligado
    a ela por adjacencia (transitivamente).

    simetrico=True tambem segue os vinculos ao contrario -- e' o que a
    SELECAO quer (o modulo visivel inteiro). O recalculo de medidas
    continua no modo estrito para nao mudar de escopo sozinho.
    """
    if obj is None or MARCA_CHAPA not in obj:
        return []
    if obj.parent is not None and MARCA_CONJUNTO in obj.parent:
        return _chapas_do_conjunto(obj.parent)
    return _grupo_solto(obj, simetrico)


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


def aplicar_espessura_chapa(C, nova_e, e_velha_mm):
    """Troca a espessura de UMA chapa fazendo-a crescer para DENTRO do
    movel: a face que esta' no limite externo do grupo fica parada e a
    adjacencia encolhe as pecas internas para caber.

    Sem isto a chapa engrossava a partir do CENTRO -- metade sobrava
    para fora do movel, metade invadia a peca vizinha.

    `e_velha_mm` vem da malha porque, no callback de update, a prop ja'
    foi trocada; a caixa do grupo tambem e' medida com a espessura
    antiga de volta no lugar, senao a propria expansao ja' teria
    deslocado o limite usado como referencia.
    """
    grupo = grupo_de(C) or [C]
    ez = _eixos(C)[2]
    a = max(range(3), key=lambda i: abs(ez[i]))   # eixo de mundo da espessura

    _ocupado[0] = True
    try:
        C.chapa_espessura_mm = e_velha_mm
        cx = _caixa_de(grupo)
        C.chapa_espessura_mm = nova_e
    finally:
        _ocupado[0] = False

    h_velho = e_velha_mm / 2000.0
    h_novo = nova_e / 2000.0
    c = _centro(C)[a]
    f_min, f_max = c - h_velho, c + h_velho
    novo_c = None
    # chapa avulsa (sem conjunto nem adjacencia) nao tem "dentro do
    # movel": continua crescendo a partir do centro
    if cx is not None and len(grupo) > 1:
        lo, hi = cx
        if abs(f_min - lo[a]) < TOL_BORDA:
            novo_c = f_min + h_novo      # encostada no limite minimo
        elif abs(f_max - hi[a]) < TOL_BORDA:
            novo_c = f_max - h_novo      # encostada no limite maximo
    # chapa interna (prateleira, divisoria): cresce a partir do centro

    if novo_c is not None:
        _ocupado[0] = True
        try:
            nc = _centro(C)
            nc[a] = novo_c
            _definir_centro(C, nc)
        finally:
            _ocupado[0] = False

    gerar_malha_chapa(C)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    # adjacencia GLOBAL (como em normalizar_chapas) e nao restrita ao
    # grupo: os vinculos sao de mao unica -- uma prateleira aponta para
    # as laterais mas nenhuma lateral aponta para ela, entao grupo_de()
    # nao a alcanca e ela ficaria com a medida antiga
    aplicar_adjacencia()
    pai = C.parent
    if pai is not None and MARCA_CONJUNTO in pai:
        reposicionar_origem(pai)


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


# ============================================ MEDIDAS DE SELECAO LIVRE
# O wireframe ja' e' generico -- recebe tres medidas e desenha o box.
# O que faltava era MEDIR uma selecao qualquer: um cubo, um carro com
# dezenas de malhas e curvas, o que for.

# Tipos que ocupam espaco. Empty/camera/luz tem bound_box degenerado na
# propria origem e esticariam a caixa ate' um ponto sem geometria.
TIPOS_COM_VOLUME = {
    'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'CURVES',
    'POINTCLOUD', 'VOLUME', 'GREASEPENCIL', 'GPENCIL', 'LATTICE',
}


# Para estes tipos o bound_box descreve os PONTOS DE CONTROLE, nao a
# geometria desenhada: uma curva com bevel mede o mesmo com e sem bevel,
# e as alcas do bezier incham a caixa. Neles a malha avaliada e' a unica
# medida fiel; nos demais o bound_box avaliado ja' inclui modificadores.
TIPOS_BBOX_INFIEL = {'CURVE', 'SURFACE', 'FONT', 'META'}


def _cantos_avaliados(obj, dep):
    """Pontos que delimitam o objeto em MUNDO.

    Usa o objeto AVALIADO, para que modificador, bevel e extrude entrem
    com a forma que aparece na tela e nao com a geometria crua.
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
    """(minimos, maximos, quantos) em MUNDO, ou None se nada tem volume."""
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
    """Caixa envolvente do que estiver selecionado.

    Devolve (largura, altura, profundidade) em mm -- eixos de mundo
    (X, Z, Y), a mesma convencao das medidas de modulo -- e quantos
    objetos entraram na conta. Devolve None se nada tem volume.
    """
    limites = _limites_mundo(context, context.selected_objects)
    if limites is None:
        return None
    lo, hi, contados = limites
    return ((hi[0] - lo[0]) * 1000.0,      # largura  = X
            (hi[2] - lo[2]) * 1000.0,      # altura   = Z
            (hi[1] - lo[1]) * 1000.0,      # profund. = Y
            contados)


def _upd_conj_dim(self, context):
    if _ocupado[0]:
        return
    redimensionar_grupo(_chapas_do_conjunto(self),
                        (self.conj_largura_mm, self.conj_altura_mm, self.conj_profundidade_mm))
    reposicionar_origem(self)
    atualizar_portas_do_conjunto(self)


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
    atualizar_portas_do_conjunto(self)
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
# Raiz UNICA dos catalogos do Asset Browser. Trocar o CAMINHO de um
# catalogo e' seguro desde que o UUID nao mude: o .blend guarda o UUID,
# e e' por ele que o Blender reencontra o asset. Por isso as raizes
# antigas sao RENOMEADAS (mesmo UUID), nunca recriadas.
CAT_RAIZ = "Cabinet Creator"
RAIZES_ANTIGAS = ("Chapa G3",)

# Uma unica biblioteca de assets. Os nomes abaixo sao os que o addon ja'
# registrou em versoes anteriores e agora precisa recolher.
NOME_BIBLIOTECA = "Cabinet Creator"
BIBLIOTECAS_ANTIGAS = (
    "Chapa G3 (fabrica)", "Chapa G3 (equipe)",
    "Cabinet Creator (fabrica)", "Cabinet Creator (equipe)",
)
CAT_CHAPAS = CAT_RAIZ + "/Chapas"
CAT_MODULOS = CAT_RAIZ + "/Modulos"


def _pasta_addon():
    """A pasta `biblioteca/` que viaja dentro do addon."""
    return os.path.join(os.path.dirname(__file__), "biblioteca")


def _prefs():
    try:
        return bpy.context.preferences.addons[__package__].preferences
    except Exception:
        return None


def pasta_biblioteca():
    """A UNICA biblioteca: a da empresa, que mora dentro do addon.

    Nao ha' mais separacao fabrica/equipe -- era ela que produzia duas
    entradas no seletor do Asset Browser. Quem quiser a biblioteca numa
    pasta de rede aponta `pasta_biblioteca` nas Preferencias.

    ATENCAO: gravar dentro do addon so' e' seguro porque a pasta e' o
    repositorio da empresa (junction feita por vincular_blender.py).
    Numa instalacao por .zip, uma atualizacao sobrescreve a pasta --
    nesse caso configure a pasta de rede nas Preferencias.
    """
    p = _prefs()
    if p and getattr(p, "pasta_biblioteca", ""):
        destino = bpy.path.abspath(p.pasta_biblioteca)
    else:
        destino = _pasta_addon()
    try:
        os.makedirs(destino, exist_ok=True)
    except Exception as e:
        print("[Cabinet Creator] biblioteca:", e)
    return destino


def registrar_bibliotecas(silencioso=True):
    """Registra as duas pastas como bibliotecas de assets do Blender,
    sem duplicar caso ja' estejam registradas."""
    registradas = []
    libs = bpy.context.preferences.filepaths.asset_libraries
    caminho = pasta_biblioteca()
    alvo = os.path.normcase(os.path.normpath(caminho))

    # A limpeza vem ANTES do registro. Uma entrada antiga podia apontar
    # para ESTA mesma pasta: removendo depois, o registro era pulado por
    # "ja' existe" e em seguida a entrada sumia -- o usuario ficava sem
    # biblioteca nenhuma ate' a proxima execucao.
    for i in range(len(libs) - 1, -1, -1):
        if libs[i].name in BIBLIOTECAS_ANTIGAS:
            try:
                libs.remove(libs[i])
            except Exception as e:
                if not silencioso:
                    print("[Cabinet Creator] remover biblioteca antiga:", e)

    ja = any(os.path.normcase(os.path.normpath(bpy.path.abspath(l.path))) == alvo
             for l in libs if l.path)
    if not ja:
        try:
            bpy.ops.preferences.asset_library_add(directory=caminho)
            libs[-1].name = NOME_BIBLIOTECA
            registradas.append(NOME_BIBLIOTECA)
        except Exception as e:
            if not silencioso:
                print("[Cabinet Creator] registro falhou:", e)

    # a cascata tem de existir ANTES do primeiro save, senao o Asset
    # Browser abre sem nenhuma pasta
    try:
        _garantir_catalogos(caminho)
    except Exception as e:
        if not silencioso:
            print("[Cabinet Creator] catalogos:", e)
    return registradas




def caminhos_catalogo():
    """Toda a ARVORE como caminhos de catalogo, em cascata.

    Cada nivel ganha a SUA propria linha: o Blender ate' desenha os pais
    implicitos, mas so' da' para ARQUIVAR um asset num nivel que exista
    como catalogo de verdade -- e a ideia e' poder arquivar em qualquer
    altura da cascata.
    """
    caminhos = [CAT_RAIZ]
    arvores = [ARVORE]
    try:
        arvores.append(_niveis_do_indice())
    except Exception as e:
        print("[Cabinet Creator] niveis do indice:", e)
    for arv in arvores:
        for n1, filhos in arv.items():
            caminhos.append("%s/%s" % (CAT_RAIZ, n1))
            for n2, netos in filhos.items():
                caminhos.append("%s/%s/%s" % (CAT_RAIZ, n1, n2))
                for n3 in netos:
                    caminhos.append("%s/%s/%s/%s" % (CAT_RAIZ, n1, n2, n3))
    return list(dict.fromkeys(caminhos))


def catalogo_de(n1, n2="", n3=""):
    """Caminho de catalogo mais fundo para os niveis escolhidos."""
    partes = [x for x in (n1, n2, n3) if x]
    if not partes:
        return ""
    return CAT_RAIZ + "/" + "/".join(partes)


def _migrar_raiz(caminho):
    """Troca uma raiz antiga pela atual, preservando o resto do caminho."""
    for velha in RAIZES_ANTIGAS:
        if caminho == velha:
            return CAT_RAIZ
        if caminho.startswith(velha + "/"):
            return CAT_RAIZ + caminho[len(velha):]
    return caminho


def _garantir_catalogos(raiz, extras=()):
    """Cria/atualiza o blender_assets.cats.txt com a cascata do addon.

    Linhas ja' existentes sao PRESERVADAS com o mesmo UUID: os presets
    guardam o UUID do catalogo dentro do .blend, entao gerar um novo
    faria o asset sumir da arvore do Asset Browser.
    """
    arq = os.path.join(raiz, "blender_assets.cats.txt")
    existentes = {}
    if os.path.exists(arq):
        for linha in open(arq, encoding="utf-8"):
            linha = linha.strip()
            if not linha or linha.startswith("#") or linha.startswith("VERSION"):
                continue
            partes = linha.split(":")
            if len(partes) >= 2:
                # raiz antiga vira a nova MANTENDO o UUID: assim o asset
                # continua achando o catalogo e nao sobra arvore dupla
                existentes.setdefault(_migrar_raiz(partes[1]), partes[0])
    for cam in list(caminhos_catalogo()) + [x for x in extras if x]:
        existentes.setdefault(cam, str(uuid.uuid4()))
    # newline explicito: o .gitattributes do projeto forca LF e sem isto
    # o Python traduz para CRLF no Windows
    with open(arq, "w", encoding="utf-8", newline="\n") as f:
        f.write("VERSION 1\n\n")
        for cam in sorted(existentes):
            # nome simples = caminho com tracos, convencao do Blender
            f.write("%s:%s:%s\n" % (existentes[cam], cam,
                                    cam.replace("/", "-")))
    return existentes


def refiliar_preset(caminho, niveis):
    """Reassina o catalogo de um preset JA' gravado no disco.

    O catalogo mora dentro do .blend (`asset_data.catalog_id`), nao no
    indice.json -- entao a unica forma de mover um preset de categoria
    e' carregar o datablock do asset, trocar o id e regravar o arquivo.

    Devolve (ok, mensagem).
    """
    cam = catalogo_de(*niveis)
    if not cam:
        return False, "item sem categoria no indice"
    if not os.path.exists(caminho):
        return False, "arquivo nao encontrado"
    ids = _garantir_catalogos(os.path.dirname(caminho), extras=(cam,))

    antes_col = set(bpy.data.collections)
    antes_obj = set(bpy.data.objects)
    with bpy.data.libraries.load(caminho) as (de, para):
        para.collections = list(de.collections)
        para.objects = list(de.objects)
    novas_col = [c for c in bpy.data.collections if c not in antes_col]
    novos_obj = [o for o in bpy.data.objects if o not in antes_obj]

    def limpar():
        for c in novas_col:
            try:
                bpy.data.collections.remove(c)
            except Exception:
                pass
        for o in novos_obj:
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass

    alvos = [d for d in list(novas_col) + list(novos_obj) if d.asset_data]
    if not alvos:
        limpar()
        return False, "nenhum asset dentro do arquivo"

    # so' o catalog_id e' gravavel: o Blender deriva o nome simples
    for d in alvos:
        d.asset_data.catalog_id = ids[cam]

    blocos = set(novas_col)
    for o in novos_obj:
        blocos.add(o)
        if o.data:
            blocos.add(o.data)
    try:
        bpy.data.libraries.write(caminho, blocos, fake_user=True,
                                 compress=True)
    except Exception as e:
        limpar()
        return False, str(e)
    limpar()
    return True, cam


LADO_PREVIEW = 128


def _pixels_png(caminho, lado=LADO_PREVIEW):
    """Le um PNG e devolve os pixels prontos para uma ImagePreview."""
    img = None
    try:
        img = bpy.data.images.load(caminho)
        # 'Raw' evita a conversao de espaco de cor: a preview guarda os
        # mesmos valores que o PNG, sem ganhar nem perder gama
        try:
            img.colorspace_settings.name = 'Raw'
        except Exception:
            pass
        if tuple(img.size) != (lado, lado):
            img.scale(lado, lado)
        return list(img.pixels)
    except Exception as e:
        print("[Cabinet Creator] preview:", e)
        return None
    finally:
        if img is not None:
            try:
                bpy.data.images.remove(img)
            except Exception:
                pass


def aplicar_preview_png(caminho_blend, caminho_png):
    """Grava a foto do preset DENTRO do .blend, como preview do asset.

    `asset_generate_preview()` NAO serve: ele so' enfileira um job
    assincrono de render, e o arquivo e' gravado antes de o job
    terminar -- por isso os presets chegavam ao Asset Browser com a
    preview vazia (128x128 zerada) e apareciam com o icone generico.
    Escrever os pixels a mao e' sincrono e sobrevive a gravacao.
    """
    if not os.path.exists(caminho_blend):
        return False, "blend nao encontrado"
    if not os.path.exists(caminho_png):
        return False, "sem foto (.png) ao lado do preset"
    pixels = _pixels_png(caminho_png)
    if not pixels:
        return False, "nao consegui ler a foto"

    antes_col = set(bpy.data.collections)
    antes_obj = set(bpy.data.objects)
    with bpy.data.libraries.load(caminho_blend) as (de, para):
        para.collections = list(de.collections)
        para.objects = list(de.objects)
    novas_col = [c for c in bpy.data.collections if c not in antes_col]
    novos_obj = [o for o in bpy.data.objects if o not in antes_obj]

    def limpar():
        for c in novas_col:
            try:
                bpy.data.collections.remove(c)
            except Exception:
                pass
        for o in novos_obj:
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass

    alvos = [d for d in list(novas_col) + list(novos_obj) if d.asset_data]
    if not alvos:
        limpar()
        return False, "nenhum asset dentro do arquivo"

    lado = (LADO_PREVIEW, LADO_PREVIEW)
    for d in alvos:
        try:
            d.preview_ensure()
        except Exception:
            pass
        pv = d.preview
        if pv is None:
            continue
        pv.image_size = lado
        pv.image_pixels_float = pixels
        # sem o nivel de icone o Asset Browser cai no icone generico
        pv.icon_size = lado
        pv.icon_pixels_float = pixels

    blocos = set(novas_col)
    for o in novos_obj:
        blocos.add(o)
        if o.data:
            blocos.add(o.data)
    try:
        bpy.data.libraries.write(caminho_blend, blocos, fake_user=True,
                                 compress=True)
    except Exception as e:
        limpar()
        return False, str(e)
    limpar()
    return True, "%d asset(s)" % len(alvos)


class OBJECT_OT_regerar_previews(Operator):
    """Regrava as fotos dos presets dentro dos .blend, para o Asset
    Browser deixar de mostrar o icone generico"""
    bl_idname = "object.cabinet_regerar_previews"
    bl_label = "Regerar Previews da Biblioteca"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        feitos, falhas = 0, []
        for it in indice_completo():
            blend = os.path.join(it["pasta"], it["arquivo"])
            png = os.path.join(
                it["pasta"], os.path.splitext(it["arquivo"])[0] + ".png")
            ok, msg = aplicar_preview_png(blend, png)
            if ok:
                feitos += 1
            else:
                falhas.append("%s: %s" % (it.get("nome", "?"), msg))
        for f in falhas:
            print("[Cabinet Creator] preview:", f)
        if falhas:
            self.report({'WARNING'},
                        "%d preview(s) gravada(s), %d sem foto -- salve o "
                        "preset de novo" % (feitos, len(falhas)))
        else:
            self.report({'INFO'}, "%d preview(s) gravada(s)" % feitos)
        return {'FINISHED'}


class OBJECT_OT_refiliar_catalogos(Operator):
    """Arquiva os presets da equipe nos catalogos da cascata, conforme a
    categoria de cada um no indice"""
    bl_idname = "object.cabinet_refiliar"
    bl_label = "Reorganizar Catalogos"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        feitos, falhas = 0, []
        for it in indice_completo():
            ok, msg = refiliar_preset(
                os.path.join(it["pasta"], it["arquivo"]), _niveis_de(it))
            if ok:
                feitos += 1
            else:
                falhas.append("%s: %s" % (it.get("nome", "?"), msg))
        for f in falhas:
            print("[Cabinet Creator] refiliar:", f)
        if falhas:
            self.report({'WARNING'},
                        "%d movido(s), %d falha(s) -- ver console"
                        % (feitos, len(falhas)))
        else:
            self.report({'INFO'}, "%d preset(s) reorganizado(s)" % feitos)
        return {'FINISHED'}


def _nome_arquivo_seguro(nome):
    limpo = "".join(ch if (ch.isalnum() or ch in " -_") else "_" for ch in nome).strip()
    return (limpo or "sem_nome").replace(" ", "_")


def salvar_na_biblioteca(objs, nome, como_colecao, niveis=None):
    """Grava os objetos num .blend da biblioteca.

    como_colecao=True agrupa tudo numa Collection e marca a COLLECTION
    como asset -- necessario para modulos, porque arrastar um objeto
    traz so' aquele objeto, enquanto arrastar uma colecao traz o
    conjunto inteiro.

    `niveis` = (n1, n2, n3): arquiva o asset no catalogo da CATEGORIA,
    que e' o que o Asset Browser mostra na cascata a esquerda. Sem
    niveis cai no catalogo por tipo (Chapas/Modulos), como antes.
    """
    raiz = destino = pasta_biblioteca()
    # sem niveis cai no catalogo por tipo; ele entra como extra para
    # existir no .cats.txt sem sujar o nivel 1 da cascata
    cam_cat = (catalogo_de(*niveis) if niveis else "") or (
        CAT_MODULOS if como_colecao else CAT_CHAPAS)
    ids_cat = _garantir_catalogos(raiz, extras=(cam_cat,))

    blocos = set()
    if como_colecao:
        col = bpy.data.collections.new(nome)
        for o in objs:
            col.objects.link(o)
        col.asset_mark()
        if col.asset_data:
            col.asset_data.catalog_id = ids_cat[cam_cat]
            col.asset_data.description = "Modulo G3 - %d peca(s)" % len(objs)
            col.asset_data.tags.new("chapa-g3")
        blocos.add(col)
    else:
        for o in objs:
            o.asset_mark()
            if o.asset_data:
                o.asset_data.catalog_id = ids_cat[cam_cat]
                o.asset_data.tags.new("chapa-g3")
    for o in objs:
        blocos.add(o)
        if o.data:
            blocos.add(o.data)

    # A preview do Asset Browser NAO e' gerada aqui: `asset_generate_preview`
    # e' assincrono e nunca chega a tempo da gravacao. Quem a grava e'
    # `aplicar_preview_png`, depois que a foto do preset existe.

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


def _niveis_do_indice():
    """Categorias que EXISTEM nos presets salvos, alem das da ARVORE.

    E' o que integra as duas pontas: uma subcategoria digitada no "+"
    do painel N passa a aparecer na cascata e tambem vira catalogo.
    """
    extra = {}
    for it in indice_completo():
        a, b, c = _niveis_de(it)
        if not a:
            continue
        ramo = extra.setdefault(a, {})
        if b:
            filhos = ramo.setdefault(b, [])
            if c and c not in filhos:
                filhos.append(c)
    return extra


def _filhos_n2(n1):
    vistos = list(ARVORE.get(n1, {}).keys())
    for k in _niveis_do_indice().get(n1, {}):
        if k not in vistos:
            vistos.append(k)
    return vistos


def _filhos_n3(n1, n2):
    vistos = list(ARVORE.get(n1, {}).get(n2, []))
    for k in _niveis_do_indice().get(n1, {}).get(n2, []):
        if k not in vistos:
            vistos.append(k)
    return vistos


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
        # newline explicito: o .gitattributes do projeto forca LF
        with open(os.path.join(pasta, NOME_INDICE), "w",
                  encoding="utf-8", newline="\n") as f:
            json.dump(itens, f, ensure_ascii=False, indent=1)
            f.write("\n")
    except Exception as e:
        print("[Cabinet Creator] nao gravei o indice:", e)


def indice_completo():
    """Le o indice da biblioteca da empresa."""
    pasta = pasta_biblioteca()
    itens = []
    for it in _ler_indice(pasta):
        it = dict(it)
        it["origem"] = "biblioteca"
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


def inserir_preset(context, pasta, arquivo, tipo, destino=None):
    """Carrega o .blend do preset na cena e seleciona o que veio.

    Devolve (novos, raizes, erro). `destino` e' o deslocamento aplicado
    as raizes; sem ele o preset vai para o cursor 3D em vez de ser
    despejado na origem.
    """
    caminho = os.path.join(pasta, arquivo)
    if not os.path.exists(caminho):
        return [], [], "Arquivo nao encontrado: " + caminho
    antes = set(bpy.data.objects)
    with bpy.data.libraries.load(caminho) as (de, para):
        if tipo == "modulo" and de.collections:
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

    raizes = [o for o in novos if o.parent is None or o.parent not in novos]
    desloc = context.scene.cursor.location.copy() if destino is None else destino
    for o in raizes:
        o.location = o.location + desloc

    for o in context.selected_objects:
        o.select_set(False)
    for o in novos:
        try:
            o.select_set(True)
        except Exception:
            pass
    return novos, raizes, ""


class OBJECT_OT_inserir_preset(Operator):
    """Traz o preset da biblioteca para o cursor 3D"""
    bl_idname = "object.cabinet_inserir_preset"
    bl_label = "Inserir"
    bl_options = {'REGISTER', 'UNDO'}

    pasta: bpy.props.StringProperty()
    arquivo: bpy.props.StringProperty()
    tipo: bpy.props.StringProperty(default="modulo")

    def execute(self, context):
        novos, _raizes, erro = inserir_preset(
            context, self.pasta, self.arquivo, self.tipo)
        if erro:
            self.report({'ERROR'}, erro)
            return {'CANCELLED'}
        self.report({'INFO'}, "%d objeto(s) inserido(s)" % len(novos))
        return {'FINISHED'}


class OBJECT_OT_arrastar_preset(Operator):
    """Arrasta com mira e caixa exata antes de inserir na cena"""
    bl_idname = "object.cabinet_arrastar_preset"
    bl_label = "Arrastar para a Cena"
    bl_options = {'REGISTER', 'UNDO'}

    # SKIP_SAVE: as props do operador persistem entre execucoes no
    # Blender, e o arraste precisa descobri-las de novo a cada vez
    pasta: bpy.props.StringProperty(options={'SKIP_SAVE'})
    arquivo: bpy.props.StringProperty(options={'SKIP_SAVE'})
    tipo: bpy.props.StringProperty(default="modulo", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        # Sem preset nas props, o arraste comecou sobre a grade: o bloco
        # sob o cursor e' lido em context.button_operator, que entrega as
        # propriedades do botao apontado (o mesmo recurso que o Blender
        # usa para "Atribuir Atalho" no menu de contexto de um botao).
        if not self.arquivo:
            alvo = getattr(context, "button_operator", None)
            # O botao de importacao, o cadeado e o lapis tambem carregam
            # `arquivo`: so' miniatura e nome (este proprio operador)
            # valem como pega do arraste.
            origem = getattr(getattr(alvo, "bl_rna", None), "identifier", "")
            arquivo = (getattr(alvo, "arquivo", "")
                       if origem.endswith("cabinet_arrastar_preset") else "")
            if not arquivo:
                # arraste em qualquer outro lugar da sidebar: devolve o
                # evento para o Blender, senao sliders parariam de andar
                return {'PASS_THROUGH'}
            self.pasta = getattr(alvo, "pasta", "")
            self.arquivo = arquivo
            self.tipo = getattr(alvo, "tipo", "modulo") or "modulo"
            self._arrastando = True
            self._mouse_inicio = (event.mouse_x, event.mouse_y)
            self._moveu = False
        else:
            self._arrastando = _eh_area_gaveta(context)
            self._mouse_inicio = (event.mouse_x, event.mouse_y)
            self._moveu = not self._arrastando

        # a grade vive na sidebar, entao a regiao do evento NAO e' a
        # viewport: a janela de desenho tem de ser procurada na area
        self._area_preview = context.area
        if _eh_area_gaveta(context):
            self._area_preview = next(
                (a for a in context.screen.areas
                 if a.type == 'VIEW_3D' and a != context.area
                 and a.x > context.area.x
                 and a.y == context.area.y), None)
        self._regiao = next(
            (r for r in self._area_preview.regions if r.type == 'WINDOW'), None
        ) if self._area_preview else None
        self._rv3d = getattr(self._area_preview.spaces.active, "region_3d", None
                             ) if self._area_preview else None
        if self._regiao is None or self._rv3d is None:
            self.report({'ERROR'}, "Sem viewport 3D para posicionar")
            return {'CANCELLED'}
        # O draw handler pode ser chamado no primeiro redraw logo depois de
        # registrado; deixe o filtro de regiao pronto antes desse momento.
        self._regiao_ptr = self._regiao.as_pointer()

        self._selecionados_antes = list(context.selected_objects)
        self._ativo_antes = context.view_layer.objects.active
        colecoes_antes = set(bpy.data.collections)
        self._novos = []
        self._raizes = []
        self._colecoes_novas = []

        # O preset entra oculto como staging. So' se torna visivel quando
        # o usuario solta dentro da viewport; cancelar apaga tudo.
        novos, raizes, erro = inserir_preset(
            context, self.pasta, self.arquivo, self.tipo,
            destino=Vector((0.0, 0.0, 0.0)))
        self._novos = list(novos or [])
        self._raizes = list(raizes or [])
        self._colecoes_novas = [c for c in bpy.data.collections
                                if c not in colecoes_antes]
        if erro:
            self._apagar()
            self._restaurar_selecao(context)
            self.report({'ERROR'}, erro)
            return {'CANCELLED'}
        if not self._novos:
            self._apagar()
            self._restaurar_selecao(context)
            self.report({'WARNING'}, "O preset nao trouxe nenhum objeto")
            return {'CANCELLED'}

        self._base = {o: o.location.copy() for o in self._raizes}
        self._altura = context.scene.cursor.location.z
        self._alvo = None
        self._normal = Vector((0.0, 0.0, 1.0))
        self._bbox_atual = []
        self._valido = False
        self._em_superficie = False
        self._handler_preview = None

        try:
            self._preparar_bbox(context)
            self._ocultar_staging(context)
            self._handler_preview = bpy.types.SpaceView3D.draw_handler_add(
                self._desenhar_preview, (), 'WINDOW', 'POST_VIEW')
        except Exception as e:
            print("[Cabinet Creator] preview do arraste:", e)
            self._apagar()
            self._restaurar_selecao(context)
            self.report({'ERROR'}, "Nao consegui preparar o preview")
            return {'CANCELLED'}

        try:
            item = _achar_item(self.pasta, self.arquivo)
            nome = item.get("nome", self.arquivo) if item else self.arquivo
            context.workspace.status_text_set(
                "Arrastando %s | Solte: inserir | Botao direito: cancelar"
                % nome)
        except Exception:
            pass
        self._mover(context, event)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _preparar_bbox(self, context):
        """Mede o staging avaliado e define a ancora no centro da base."""
        context.view_layer.update()
        try:
            dep = context.evaluated_depsgraph_get()
        except Exception:
            dep = None
        pontos = []
        for obj in self._novos:
            if obj.type in TIPOS_COM_VOLUME:
                pontos.extend(_cantos_avaliados(obj, dep))
        if not pontos:
            pontos = [o.matrix_world.translation.copy() for o in self._raizes]
        if not pontos:
            raise RuntimeError("preset sem geometria")

        lo = Vector(tuple(min(p[i] for p in pontos) for i in range(3)))
        hi = Vector(tuple(max(p[i] for p in pontos) for i in range(3)))
        self._bbox_base = (
            Vector((lo.x, lo.y, lo.z)), Vector((hi.x, lo.y, lo.z)),
            Vector((hi.x, hi.y, lo.z)), Vector((lo.x, hi.y, lo.z)),
            Vector((lo.x, lo.y, hi.z)), Vector((hi.x, lo.y, hi.z)),
            Vector((hi.x, hi.y, hi.z)), Vector((lo.x, hi.y, hi.z)),
        )
        self._ancora_base = Vector((
            (lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, lo.z))
        diagonal = (hi - lo).length
        self._tamanho_mira = max(0.04, min(diagonal * 0.08, 0.35))

    def _ocultar_staging(self, context):
        """Esconde a geometria real para deixar somente o preview GPU."""
        self._visibilidade = []
        for obj in self._novos:
            self._visibilidade.append(
                (obj, bool(obj.hide_viewport), bool(obj.hide_get())))
            obj.hide_set(True)
            obj.hide_viewport = True
        context.view_layer.update()

    def _restaurar_staging(self):
        for obj, global_oculto, local_oculto in getattr(
                self, "_visibilidade", []):
            try:
                obj.hide_viewport = global_oculto
                obj.hide_set(local_oculto)
            except (ReferenceError, RuntimeError):
                pass

    def _restaurar_selecao(self, context):
        try:
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in self._selecionados_antes:
                if obj.name in bpy.data.objects:
                    obj.select_set(True)
            if (self._ativo_antes is not None and
                    self._ativo_antes.name in bpy.data.objects):
                context.view_layer.objects.active = self._ativo_antes
        except (ReferenceError, RuntimeError):
            pass

    def _encerrar_visual(self, context):
        if self._handler_preview is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(
                    self._handler_preview, 'WINDOW')
            except Exception:
                pass
            self._handler_preview = None
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
        if context.area is not None:
            context.area.tag_redraw()
        if getattr(self, '_area_preview', None) is not None:
            self._area_preview.tag_redraw()

    def _desenhar_preview(self):
        """Desenha box e mira sobre a viewport sem criar geometria."""
        if not self._valido or not self._bbox_atual:
            return
        regiao = getattr(bpy.context, "region", None)
        if regiao is None or regiao.as_pointer() != self._regiao_ptr:
            return

        arestas = (
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        )
        linhas_box = []
        for a, b in arestas:
            linhas_box.extend((self._bbox_atual[a], self._bbox_atual[b]))

        normal = self._normal.normalized()
        referencia = (Vector((0.0, 0.0, 1.0))
                      if abs(normal.z) < 0.9 else Vector((1.0, 0.0, 0.0)))
        tangente = normal.cross(referencia).normalized()
        bitangente = normal.cross(tangente).normalized()
        tamanho = self._tamanho_mira
        alvo = self._alvo
        linhas_mira = (
            alvo - tangente * tamanho, alvo + tangente * tamanho,
            alvo - bitangente * tamanho, alvo + bitangente * tamanho,
            alvo - normal * tamanho * 0.35,
            alvo + normal * tamanho * 0.35,
        )

        try:
            gpu.state.blend_set('ALPHA')
            gpu.state.depth_test_set('NONE')
            gpu.state.line_width_set(1.5)
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            shader.bind()
            shader.uniform_float("color", (0.1, 1.0, 0.2, 0.9))
            batch_for_shader(
                shader, 'LINES', {"pos": linhas_box}).draw(shader)
            shader.uniform_float(
                "color", (1.0, 0.85, 0.1, 1.0)
                if self._em_superficie else (0.9, 0.9, 0.9, 1.0))
            batch_for_shader(
                shader, 'LINES', {"pos": linhas_mira}).draw(shader)
        except Exception as e:
            print("[Cabinet Creator] desenho do preview:", e)
        finally:
            try:
                gpu.state.line_width_set(1.0)
                gpu.state.depth_test_set('NONE')
                gpu.state.blend_set('NONE')
            except Exception:
                pass

    def _na_viewport(self, event):
        """O solte so' vale dentro da viewport, como no arraste nativo."""
        dx = event.mouse_x - self._regiao.x
        dy = event.mouse_y - self._regiao.y
        return 0 <= dx < self._regiao.width and 0 <= dy < self._regiao.height

    def _mover(self, context, event):
        """Usa raycast na cena e plano do cursor como contingencia."""
        if not self._na_viewport(event):
            self._valido = False
            self._area_preview.tag_redraw()
            return
        coord = (event.mouse_x - self._regiao.x, event.mouse_y - self._regiao.y)
        try:
            origem = view3d_utils.region_2d_to_origin_3d(
                self._regiao, self._rv3d, coord)
            direcao = view3d_utils.region_2d_to_vector_3d(
                self._regiao, self._rv3d, coord)
        except Exception:
            return
        alvo = None
        normal = Vector((0.0, 0.0, 1.0))
        self._em_superficie = False
        try:
            dep = context.evaluated_depsgraph_get()
            acerto, local, normal_hit, _face, obj_hit, _matriz = (
                context.scene.ray_cast(
                    dep, origem, direcao, distance=1000000.0))
            if acerto and obj_hit not in self._novos:
                alvo = local.copy()
                normal = normal_hit.copy()
                self._em_superficie = True
        except Exception as e:
            print("[Cabinet Creator] raycast do arraste:", e)
        if alvo is None:
            alvo = intersect_line_plane(
                origem, origem + direcao * 1000.0,
                Vector((0.0, 0.0, self._altura)),
                Vector((0.0, 0.0, 1.0)))
        if alvo is None:        # raio paralelo ao plano: nada a fazer
            self._valido = False
            self._area_preview.tag_redraw()
            return
        deslocamento = alvo - self._ancora_base
        for o in self._raizes:
            base = self._base.get(o)
            if base is not None:
                o.location = base + deslocamento
        self._alvo = alvo
        self._normal = normal
        self._bbox_atual = [p + deslocamento for p in self._bbox_base]
        self._valido = True
        self._area_preview.tag_redraw()

    def _apagar(self):
        for o in list(self._novos):
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass
        for colecao in list(getattr(self, "_colecoes_novas", [])):
            try:
                if colecao.name in bpy.data.collections:
                    bpy.data.collections.remove(colecao)
            except (ReferenceError, RuntimeError):
                pass

    def _cancelar(self, context):
        self._encerrar_visual(context)
        self._apagar()
        self._restaurar_selecao(context)
        if context.area is not None:
            context.area.tag_redraw()
        return {'CANCELLED'}

    def _confirmar(self, context):
        self._encerrar_visual(context)
        self._restaurar_staging()
        try:
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in self._novos:
                obj.select_set(True)
            if self._raizes:
                context.view_layer.objects.active = self._raizes[0]
            elif self._novos:
                context.view_layer.objects.active = self._novos[0]
            context.view_layer.update()
        except (ReferenceError, RuntimeError):
            pass
        self.report({'INFO'}, "%d objeto(s) inserido(s)" % len(self._novos))
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            if self._arrastando and not self._moveu:
                dx = event.mouse_x - self._mouse_inicio[0]
                dy = event.mouse_y - self._mouse_inicio[1]
                # O limiar evita transformar um clique com pequena
                # oscilacao involuntaria em arraste.
                self._moveu = (dx * dx + dy * dy) >= 36
            self._mover(context, event)
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE':
            confirma = 'RELEASE' if self._arrastando else 'PRESS'
            if event.value == confirma:
                if self._arrastando and not self._moveu:
                    # O clique sem arraste ativa o mesmo posicionador. Esse
                    # fallback e' indispensavel porque algumas versoes/temas
                    # do Blender retêm o drag do botao da interface.
                    self._arrastando = False
                    try:
                        context.workspace.status_text_set(
                            "Posicionamento ativo | Clique na viewport: "
                            "inserir | Botao direito: cancelar")
                    except Exception:
                        pass
                    return {'RUNNING_MODAL'}
                if not self._na_viewport(event):
                    return self._cancelar(context)
                if not self._valido:
                    self.report({'WARNING'}, "Posicione dentro da viewport")
                    return self._cancelar(context)
                return self._confirmar(context)
        if (event.type in {'RET', 'NUMPAD_ENTER'} and
                event.value == 'PRESS'):
            if not self._valido:
                self.report({'WARNING'}, "Posicione dentro da viewport")
                return {'RUNNING_MODAL'}
            return self._confirmar(context)
        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            return self._cancelar(context)
        if event.type == 'WINDOW_DEACTIVATE':
            return self._cancelar(context)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._cancelar(context)


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
WIREFRAME_LARGURA_PX = 160
WIREFRAME_ALTURA_PX = 160
WIREFRAME_MARGEM_ESQUERDA_PX = 14.0
WIREFRAME_MARGEM_DIREITA_PX = 2.0
WIREFRAME_MARGEM_Y_PX = 20.0
WIREFRAME_LINHA_PX = 0.45
WIREFRAME_ESCALA_MIN_UI = 5.0
WIREFRAME_ESCALA_MAX_UI = 9.0
WIREFRAME_ESCALA_ESTREITA_MAX_UI = WIREFRAME_ESCALA_MAX_UI
WIREFRAME_LARGURA_EMPILHAR_PX = 310.0
MEDIDAS_LARGURA_COLUNA_UNICA_PX = 210.0
MEDIDAS_OCUPACAO_COLUNA_UNICA = 0.80
MEDIDAS_LARGURA_CONTROLES_UI = 4.5
WIREFRAME_CACHE_MAX = 48
WIREFRAME_PREFIXO = "wireframe:v15:"
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
    'E': ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
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


def _caixas_das_folhas(largura, altura, profundidade, folhas):
    """Vertices das folhas na face frontal, nos eixos da caixa.

    Proporcoes de DESENHO, nao medidas: o preview e' um esquema. A
    folha recua 4% das bordas e avanca 8% da profundidade, que e' o que
    deixa a blocagem legivel em 160 px.
    """
    if folhas <= 0:
        return []
    recuo = min(largura, altura) * 0.04
    fundo = max(profundidade * 0.08, 1e-6)
    vao = largura - 2.0 * recuo
    if vao <= 0.0 or altura - 2.0 * recuo <= 0.0:
        return []
    vaz = vao * 0.02
    passo = (vao + vaz) / folhas
    z0, z1 = recuo, altura - recuo
    caixas = []
    for i in range(folhas):
        x0 = recuo + i * passo
        x1 = x0 + passo - vaz
        caixas.append([(x0, 0.0, z0), (x1, 0.0, z0),
                       (x0, fundo, z0), (x1, fundo, z0),
                       (x0, 0.0, z1), (x1, 0.0, z1),
                       (x0, fundo, z1), (x1, fundo, z1)])
    return caixas


def _pontos_wireframe(largura, altura, profundidade, extras=()):
    """Projeta a 45 graus e ajusta a proporcao a area util do canvas.

    `extras` sao vertices nos MESMOS eixos da caixa (por exemplo as
    folhas); voltam projetados logo apos os 8 cantos, para que nada
    saia com escala diferente da caixa.
    """
    medidas = (float(largura), float(altura), float(profundidade))
    if not all(math.isfinite(v) and v > 0.0 for v in medidas):
        return None
    L, A, P = medidas
    vertices = (
        (0.0, 0.0, 0.0), (L, 0.0, 0.0),
        (0.0, P, 0.0), (L, P, 0.0),
        (0.0, 0.0, A),   (L, 0.0, A),
        (0.0, P, A),     (L, P, A),
    ) + tuple(extras)
    diagonal = math.sqrt(0.5)  # cos(45) == sin(45)
    projetados = [(x - y * diagonal, z + y * diagonal)
                  for x, y, z in vertices]
    # Os limites saem dos 8 cantos da CAIXA: incluir as folhas mudaria
    # a escala e o modulo apareceria menor do que e'.
    caixa = projetados[:8]
    min_x = min(p[0] for p in caixa)
    max_x = max(p[0] for p in caixa)
    min_y = min(p[1] for p in caixa)
    max_y = max(p[1] for p in caixa)
    largura_proj = max_x - min_x
    altura_proj = max_y - min_y
    util_l = (WIREFRAME_LARGURA_PX - WIREFRAME_MARGEM_ESQUERDA_PX -
              WIREFRAME_MARGEM_DIREITA_PX)
    util_a = WIREFRAME_ALTURA_PX - 2.0 * WIREFRAME_MARGEM_Y_PX
    if (largura_proj <= 0.0 or altura_proj <= 0.0 or
            util_l <= 0.0 or util_a <= 0.0):
        return None

    escala = min(util_l / largura_proj, util_a / altura_proj)
    desenho_l = largura_proj * escala
    desenho_a = altura_proj * escala
    dx = WIREFRAME_MARGEM_ESQUERDA_PX - min_x * escala
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
    """Identifica as direcoes sem adicionar cotas ou linhas auxiliares.

    'INDIVIDUAL' (chapa): L, A e E. Na chapa a aresta VERTICAL do
        desenho e' a espessura -- `_visual_wireframe` passa a espessura
        na posicao da altura -- e a aresta que recua e' a altura da peca.
    'GRUPO' (modulo de chapas): L, A, P e mais o E na quina inferior
        direita. A espessura nao tem aresta propria no modulo, mas e'
        medida dele e precisa aparecer.
    'LIVRE' (objeto sem assinatura do addon): so' L, A e P. Sem chapas
        no meio, nao existe espessura para anunciar.
    """
    topo = _meio_wireframe(pontos[6], pontos[7])
    fundo = _meio_wireframe(pontos[0], pontos[2])
    vertical = _meio_wireframe(pontos[2], pontos[6])
    _desenhar_indicador(buffer, 'L', topo[0], topo[1] + 10.0, cor)

    if modo == 'INDIVIDUAL':
        _desenhar_indicador(
            buffer, 'E', max(5.0, vertical[0] - 9.0), vertical[1], cor)
        _desenhar_indicador(
            buffer, 'A', fundo[0] - 9.0, fundo[1] - 8.0, cor)
        return

    _desenhar_indicador(
        buffer, 'A', max(5.0, vertical[0] - 9.0), vertical[1], cor)
    _desenhar_indicador(
        buffer, 'P', fundo[0] - 9.0, fundo[1] - 8.0, cor)
    if modo == 'GRUPO':
        # Canto inferior direito da projecao. A letra desce para a
        # margem de baixo em vez de sair pela direita: a margem lateral
        # e' de poucos pixels e `_desenhar_indicador` corta calado.
        quina = pontos[1]
        _desenhar_indicador(
            buffer, 'E', quina[0] - 8.0, quina[1] - 9.0, cor)


def _rasterizar_wireframe(largura, altura, profundidade, cor, modo='GRUPO',
                         folhas=0):
    """Pixels RGBA das 12 arestas do box, mais as folhas na frente."""
    caixas = _caixas_das_folhas(largura, altura, profundidade, folhas)
    extras = [v for caixa in caixas for v in caixa]
    pontos = _pontos_wireframe(largura, altura, profundidade, extras)
    if pontos is None:
        return None
    n = WIREFRAME_LARGURA_PX * WIREFRAME_ALTURA_PX * 4
    buffer = [0.0] * n
    for a, b in _ARESTAS_WIREFRAME:
        _desenhar_segmento(buffer, pontos[a], pontos[b], cor)
    for i in range(len(caixas)):
        base = 8 + i * 8
        for a, b in _ARESTAS_WIREFRAME:
            _desenhar_segmento(buffer, pontos[base + a], pontos[base + b], cor)
    _desenhar_indicadores(buffer, pontos, cor, modo)
    return _centralizar_wireframe(buffer)


def _centralizar_wireframe(buffer):
    """Centraliza o conteudo VISIVEL, incluindo as letras L/A/P/E."""
    largura, altura = WIREFRAME_LARGURA_PX, WIREFRAME_ALTURA_PX
    ocupados = [i // 4 for i in range(0, len(buffer), 4)
                if buffer[i + 3] > 0.0]
    if not ocupados:
        return buffer
    xs = [p % largura for p in ocupados]
    ys = [p // largura for p in ocupados]
    dx = int(round(((largura - 1) - (min(xs) + max(xs))) / 2.0))
    dy = int(round(((altura - 1) - (min(ys) + max(ys))) / 2.0))
    if dx == 0 and dy == 0:
        return buffer
    centralizado = [0.0] * len(buffer)
    for p in ocupados:
        x, y = p % largura, p // largura
        nx, ny = x + dx, y + dy
        if 0 <= nx < largura and 0 <= ny < altura:
            origem = p * 4
            destino = (ny * largura + nx) * 4
            centralizado[destino:destino + 4] = buffer[origem:origem + 4]
    return centralizado


# ==================================== BARRA DE TAMANHO (estilo volume)
# O bpy nao tem slider de trilho fino com knob redondo: o `slider=True`
# nativo pinta a barra inteira e escreve o valor por cima. Esta aqui e'
# rasterizada -- mesma tecnica do wireframe -- e fica clicavel porque e'
# montada em FATIAS: cada fatia e' um botao de operador que grava o seu
# proprio valor, e o clique cai na fatia certa sem precisar adivinhar
# coordenada nenhuma (o bpy nao informa onde o botao foi desenhado).
BARRA_PREFIXO = "barra:v2:"
BARRA_PX = 40               # lado da fatia rasterizada, em pixels
PX_FATIA_BARRA = 18.0       # largura que o icone ocupa ao ser desenhado
PX_BOTAO_BIBLIOTECA = 34.0  # o botao do Asset Browser, ao lado da barra
BARRA_TRILHO = 0.14         # espessura do trilho, fracao do lado
BARRA_KNOB = 0.62           # diametro do knob, fracao do lado
AMOSTRAS_BARRA = 4          # supersampling por pixel (4x4)
COR_BARRA_VAZIA = (0.322, 0.298, 0.290)
COR_BARRA_CHEIA = (1.0, 1.0, 1.0)


def _cobertura_disco(x, y, cx, cy, raio, amostras=AMOSTRAS_BARRA):
    """Quanto do pixel (x, y) o disco cobre, de 0 a 1.

    Supersampling na marra: o icone e' reduzido pelo Blender na hora de
    desenhar, e um circulo cru vira losango depois dessa reducao.
    """
    dentro = 0
    passo = 1.0 / amostras
    for sy in range(amostras):
        py = y - 0.5 + (sy + 0.5) * passo
        for sx in range(amostras):
            px = x - 0.5 + (sx + 0.5) * passo
            if math.hypot(px - cx, py - cy) <= raio:
                dentro += 1
    return dentro / float(amostras * amostras)


def _fatia_barra(indice, ativo, ultimo):
    """Pixels RGBA de UMA fatia: trecho do trilho + knob se for a ativa.

    O trilho vem cheio ate' a fatia ativa e vazio depois dela, que e' a
    leitura imediata de "quanto esta' ligado".
    """
    lado = BARRA_PX
    buffer = [0.0] * (lado * lado * 4)
    meio = (lado - 1) / 2.0
    meia_esp = max(1.0, lado * BARRA_TRILHO / 2.0)
    raio = lado * BARRA_KNOB / 2.0
    cor = COR_BARRA_CHEIA if indice <= ativo else COR_BARRA_VAZIA

    for y in range(lado):
        dy = abs(y - meio)
        for x in range(lado):
            alfa, c = 0.0, cor
            # trilho: faixa horizontal, bordas suavizadas
            if dy <= meia_esp - 0.5:
                alfa = 1.0
            elif dy <= meia_esp + 0.5:
                alfa = meia_esp + 0.5 - dy
            # pontas arredondadas so' nas fatias das extremidades
            if indice == 0 and x < meia_esp:
                alfa = min(alfa, _cobertura_disco(x, y, meia_esp, meio,
                                                  meia_esp))
            if indice == ultimo and x > lado - 1 - meia_esp:
                alfa = min(alfa, _cobertura_disco(
                    x, y, lado - 1 - meia_esp, meio, meia_esp))
            # knob por cima, sempre branco
            if indice == ativo:
                cob = _cobertura_disco(x, y, meio, meio, raio)
                if cob > 0.0:
                    if cob >= alfa:
                        c = COR_BARRA_CHEIA
                    alfa = max(alfa, cob)
            if alfa <= 0.0:
                continue
            i = (y * lado + x) * 4
            buffer[i] = c[0]
            buffer[i + 1] = c[1]
            buffer[i + 2] = c[2]
            buffer[i + 3] = min(1.0, alfa)
    return buffer


def _icone_fatia_barra(indice, ativo, ultimo):
    """icon_id de uma fatia, reaproveitado pelo cache de previews."""
    chave = BARRA_PREFIXO + "%d:%d:%d" % (indice, ativo, ultimo)
    colecao = _colecao_previews()
    if chave not in colecao:
        try:
            preview = colecao.new(chave)
            tamanho = (BARRA_PX, BARRA_PX)
            pixels = _fatia_barra(indice, ativo, ultimo)
            preview.icon_size = tamanho
            preview.icon_pixels_float = pixels
            preview.image_size = tamanho
            preview.image_pixels_float = pixels
        except Exception as e:
            print("[Cabinet Creator] barra:", e)
            return 0
    try:
        return colecao[chave].icon_id
    except Exception:
        return 0


def _metrica_barra(context, disponivel=None):
    """(fatias, largura logica da celula, compressao) da barra.

    Um lugar so' porque o DESENHO e o ARRASTE precisam concordar: se a
    celula medir diferente dos dois lados, o knob anda fora do dedo.
    """
    prop = bpy.types.Scene.bl_rna.properties["chapa_tam_bloco"]
    fatias = prop.hard_max - prop.hard_min + 1
    if disponivel is None:
        disponivel = max(1.0, PX_FATIA_BARRA * fatias)
    disponivel = max(1.0, disponivel)
    # scale_x encolhe a celula ate' o tamanho do icone; acima de 1.0 nao
    # adianta (o icone nao estica), entao a celula fica menor que o alvo
    compressao = min(1.0, PX_FATIA_BARRA * fatias / disponivel)
    celula = min(PX_FATIA_BARRA, disponivel / fatias)
    return fatias, celula, compressao


# ====================================== FOTO CLICAVEL (fatiada)
# `template_icon` amplia a foto mas NAO recebe evento, e o icone de um
# botao de operador nao passa de ~16 px por mais que se aumente
# scale_x/scale_y (medido). Para a foto inteira ficar clicavel ela e'
# cortada em ladrilhos, cada um o icone de um botao: o mosaico parece
# uma imagem so' e qualquer ponto dela aciona o posicionador.
FOTO_PREFIXO = "foto:v2:"
# Rasterizar em 24 e desenhar em 16 obrigava o Blender a reamostrar
# cada ladrilho (1,5x) e aparecia bandeamento nas faces lisas. Os
# dois tamanhos precisam ser IGUAIS: assim o desenho e' 1:1.
FOTO_TILE_PX = 16
# 16 px e' a largura REAL com que o Blender desenha o icone de um
# botao; 18 deixava 2 px de fresta e o mosaico virava xadrez.
PX_TILE_FOTO = 16.0
# Alvo da CELULA, de proposito menor que o icone: mirar nos 16 px
# exige acertar a largura do bloco na mosca, e ela e' estimada --
# qualquer desvio abre fresta e a foto fica picotada. Com folga, a
# celula fica sempre abaixo do icone em qualquer largura.
PX_ALVO_CELULA = 16.0
# ui_units_x sozinho nao encosta as colunas: sobra folga lateral
# em cada celula. O valor abaixo foi achado por captura de tela.
COMPRESSAO_TILE_FOTO = 0.7


# Folgas medidas por captura: o box da lista come' um tanto da
# largura do painel, e cada bloco tem a sua propria margem interna.
PADDING_GRADE = 34.0
PADDING_BLOCO = 12.0


def _metrica_blocos(context, tamanho):
    """(colunas, largura de cada bloco) da grade de presets.

    As colunas precisam ser EXPLICITAS. Com `columns=0` quem decide a
    largura do bloco e' o bpy, e a foto clicavel -- um mosaico de
    icones de 16 px -- so' fica sem fresta quando essa largura e'
    conhecida: `ui_units_x` e' ignorado dentro do grid_flow (medido) e
    `scale_x` encolhe o proprio icone, deformando a imagem.
    """
    util = max(1.0, _largura_painel(context) - PADDING_GRADE)
    # O mosaico da foto so' fica sem listras quando a celula
    # (largura_do_bloco / ladrilhos) cai perto dos 16 px do icone.
    # Blocos largos demais fazem a conta desviar e aparecem bandas;
    # 20 px por grau de tamanho mantem o bloco na faixa que fecha.
    alvo = max(64.0, float(tamanho) * 20.0)
    colunas = max(1, min(6, int(util // alvo)))
    return colunas, util / colunas


def _foto_clicavel_ligada():
    """Preferencia: foto clicavel (mosaico) ou foto perfeita."""
    p = _prefs()
    return bool(p and getattr(p, "foto_clicavel", False))


def _tiles_foto(pasta, png, lado):
    """icon_id de cada ladrilho da foto, em grade `lado` x `lado`.

    Devolve as linhas de CIMA para BAIXO, que e' a ordem em que a UI
    desenha -- os pixels do Blender vem de baixo para cima.
    """
    colecao = _colecao_previews()
    base = FOTO_PREFIXO + "%s|%s:%d:" % (pasta, png, lado)
    if (base + "0:0") not in colecao:
        n = lado * FOTO_TILE_PX
        pixels = _pixels_png(os.path.join(pasta, png), n)
        if not pixels:
            return None
        for j in range(lado):
            for i in range(lado):
                buf = []
                for y in range(FOTO_TILE_PX):
                    ini = ((j * FOTO_TILE_PX + y) * n
                           + i * FOTO_TILE_PX) * 4
                    buf.extend(pixels[ini:ini + FOTO_TILE_PX * 4])
                try:
                    pv = colecao.new(base + "%d:%d" % (i, j))
                except Exception as e:
                    print("[Cabinet Creator] foto:", e)
                    return None
                tam = (FOTO_TILE_PX, FOTO_TILE_PX)
                pv.icon_size = tam
                pv.icon_pixels_float = buf
                pv.image_size = tam
                pv.image_pixels_float = buf
    try:
        return [[colecao[base + "%d:%d" % (i, j)].icon_id
                 for i in range(lado)]
                for j in range(lado - 1, -1, -1)]
    except Exception as e:
        print("[Cabinet Creator] foto:", e)
        return None


class OBJECT_OT_definir_tamanho(Operator):
    """Tamanho das miniaturas da biblioteca.

    A barra responde a CLIQUE, nao a arraste, e isso nao tem conserto
    pela API: o bpy nao permite criar um tipo de widget novo. Um botao
    de painel e' tratado pelo handler de UI, que consome o PRESS antes
    de qualquer keymap -- nem `head=True` no keymap "User Interface"
    passa na frente. O que se desenha (imagem, icone) nao recebe
    evento; o que recebe evento (botao) nao se desenha do nosso jeito.
    Ja' foi tentado: keymap PRESS e CLICK_DRAG + modal relativo.
    """
    bl_idname = "object.cabinet_tamanho"
    bl_label = "Tamanho dos Blocos"

    valor: bpy.props.IntProperty(default=5)

    def execute(self, context):
        context.scene.chapa_tam_bloco = self.valor
        return {'FINISHED'}


def _chave_wireframe(modo, largura, altura, profundidade, cor, folhas=0):
    medidas = tuple(round(float(v), 1)
                    for v in (largura, altura, profundidade))
    rgb = tuple(round(float(v) * 255.0) for v in cor)
    return WIREFRAME_PREFIXO + "%s:%.1f:%.1f:%.1f:%d:%d:%d:%d" % (
        modo, medidas[0], medidas[1], medidas[2], rgb[0], rgb[1], rgb[2],
        int(folhas))


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


def _icone_wireframe(context, modo, largura, altura, profundidade, folhas=0):
    """Cria ou reutiliza o icon_id horizontal para estas medidas."""
    cor = _cor_wireframe(context)
    chave = _chave_wireframe(modo, largura, altura, profundidade, cor, folhas)
    colecao = _colecao_previews()
    if chave not in colecao:
        pixels = _rasterizar_wireframe(
            largura, altura, profundidade, cor, modo=modo, folhas=folhas)
        if pixels is None:
            return 0
        try:
            preview = colecao.new(chave)
            tamanho = (WIREFRAME_LARGURA_PX, WIREFRAME_ALTURA_PX)
            # Preenche ambos porque a versao do Blender decide qual nivel
            # usar conforme a escala pedida por template_icon.
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


def _ocupacao_alpha_png(caminho):
    """Maior fracao ocupada pelo alfa, em X ou Y, ou zero se vazio."""
    imagem = None
    try:
        imagem = bpy.data.images.load(caminho, check_existing=False)
        largura, altura = imagem.size
        if largura <= 0 or altura <= 0:
            return 0.0
        # Blender 4.2 nao aceita `step` diretamente no bpy_prop_array.
        alpha = list(imagem.pixels)[3::4]
        min_x, min_y = largura, altura
        max_x = max_y = -1
        for indice, valor in enumerate(alpha):
            if valor <= 0.01:
                continue
            x = indice % largura
            y = indice // largura
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
        if max_x < min_x or max_y < min_y:
            return 0.0
        return max((max_x - min_x + 1) / largura,
                   (max_y - min_y + 1) / altura)
    except Exception as e:
        print("[Cabinet Creator] leitura do alfa:", e)
        return 0.0
    finally:
        if imagem is not None:
            try:
                bpy.data.images.remove(imagem)
            except (ReferenceError, RuntimeError):
                pass


def capturar_viewport(destino_png, camera=None, isolar=None):
    """Foto do modelo a partir da viewport.

    NAO renderiza: usa render OpenGL, ou seja, as cores da propria
    viewport. Overlays desligados removem grade, eixos, gizmos e icones.
    O PNG sai em RGBA transparente e, sem camera explicita, o alvo e'
    enquadrado automaticamente para ocupar a miniatura.

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
           cena.render.image_settings.color_mode,
           cena.render.resolution_x, cena.render.resolution_y,
           cena.render.resolution_percentage, cena.render.film_transparent)
    area = next((a for a in bpy.context.screen.areas if a.type == 'VIEW_3D'), None)
    if area is None:
        return False, "Nenhuma viewport 3D visivel"

    espaco = area.spaces.active
    r3d = espaco.region_3d
    ov_ant = espaco.overlay.show_overlays
    vista_ant = (r3d.view_distance, r3d.view_location.copy(),
                 r3d.view_rotation.copy(), r3d.view_perspective,
                 r3d.view_camera_zoom, tuple(r3d.view_camera_offset))
    cam_ant = cena.camera
    selecionados_ant = list(bpy.context.selected_objects)
    ativo_ant = bpy.context.view_layer.objects.active
    escondidos = []
    enquadrar = []

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
                elif o.name in manter:
                    enquadrar.append(o)

        cena.render.image_settings.file_format = 'PNG'
        cena.render.image_settings.color_mode = 'RGBA'
        cena.render.resolution_x = 512
        cena.render.resolution_y = 512
        cena.render.resolution_percentage = 100
        cena.render.film_transparent = True
        cena.render.filepath = destino_png
        espaco.overlay.show_overlays = False

        if camera is not None:
            cena.camera = camera
            r3d.view_perspective = 'CAMERA'
        # Sem camera preserva a orientacao escolhida pelo usuario, mas
        # ajusta centro e distancia para o alvo ocupar a miniatura.

        regiao = next((r for r in area.regions if r.type == 'WINDOW'), None)
        with bpy.context.temp_override(area=area, region=regiao):
            if camera is None and enquadrar:
                # A captura quadrada nao tem a mesma proporcao da viewport
                # larga. ORTHO preserva o angulo, mantem o centro e evita
                # o deslocamento lateral que a perspectiva produziria.
                r3d.view_perspective = 'ORTHO'
                for o in bpy.context.selected_objects:
                    o.select_set(False)
                for o in enquadrar:
                    try:
                        o.select_set(True)
                    except (ReferenceError, RuntimeError):
                        pass
                bpy.context.view_layer.objects.active = enquadrar[0]
                bpy.ops.view3d.view_selected(use_all_regions=False)
                # Uma pequena folga evita cortar antialiasing e objetos
                # muito largos/altos junto ao limite do PNG.
                r3d.view_distance *= 1.12
            bpy.ops.render.opengl(write_still=True, view_context=True)
            if camera is None and enquadrar:
                # `view_selected` enquadra usando a proporcao da viewport,
                # mas o PNG e' quadrado. Mede o alfa real e faz uma segunda
                # passagem para ocupar o mesmo espaco em qualquer sidebar.
                ocupacao = _ocupacao_alpha_png(destino_png)
                if ocupacao > 0.01:
                    fator = max(0.25, min(2.0, ocupacao / 0.82))
                    if abs(fator - 1.0) > 0.03:
                        r3d.view_distance *= fator
                        bpy.ops.render.opengl(write_still=True,
                                              view_context=True)
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
        (r3d.view_distance, r3d.view_location, r3d.view_rotation,
         r3d.view_perspective, r3d.view_camera_zoom,
         r3d.view_camera_offset) = vista_ant
        cena.camera = cam_ant
        for o in bpy.context.selected_objects:
            o.select_set(False)
        for o in selecionados_ant:
            try:
                o.select_set(True)
            except (ReferenceError, RuntimeError):
                pass
        if ativo_ant is not None and ativo_ant.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = ativo_ant
        (cena.render.filepath, cena.render.image_settings.file_format,
         cena.render.image_settings.color_mode,
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


# ========================================== BLOQUEIO E RENOMEAR DOS BLOCOS
def _atualizar_item(pasta, arquivo, mudancas):
    itens = _ler_indice(pasta)
    for i in itens:
        if i.get("arquivo") == arquivo:
            i.update(mudancas)
    _gravar_indice(pasta, itens)


def item_bloqueado(it):
    """Com uma biblioteca so', o cadeado e' por item: nao ha' mais uma
    origem "de fabrica" que force o bloqueio."""
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
        _atualizar_item(self.pasta, self.arquivo,
                        {"bloqueado": not bool(it.get("bloqueado", False))})
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
        # os niveis sao resolvidos ANTES de gravar: e' deles que sai o
        # catalogo em que o asset vai ser arquivado
        n2 = self.n2 or (_filhos_n2(self.n1) or [""])[0]
        n3 = self.n3 or (_filhos_n3(self.n1, n2) or [""])[0]
        try:
            arq = salvar_na_biblioteca(completos, self.nome, self.como_modulo,
                                       niveis=(self.n1, n2, n3))
            png = os.path.splitext(os.path.basename(arq))[0] + ".png"
            # Todo preset precisa nascer com representacao visual. Nao e'
            # uma preferencia do usuario nem pode ser desativada no dialogo.
            cam = next((o for o in sel if o.type == 'CAMERA'), None)
            alvo = [o for o in completos if o.type != 'CAMERA']
            okf, msg = capturar_viewport(
                os.path.join(pasta_biblioteca(), png), cam,
                isolar=alvo or None)
            if not okf:
                self.report({'ERROR'}, "Foto obrigatoria falhou: " + msg)
                return {'CANCELLED'}
            # a mesma foto vira a preview do asset dentro do .blend
            okp, msgp = aplicar_preview_png(
                arq, os.path.join(pasta_biblioteca(), png))
            if not okp:
                print("[Cabinet Creator] preview do asset:", msgp)
            registrar_no_indice(pasta_biblioteca(), self.nome, arq,
                                self.n1, n2, n3,
                                "modulo" if self.como_modulo else "objeto")
        except Exception as e:
            self.report({'ERROR'}, "Falha ao salvar: %s" % e)
            return {'CANCELLED'}
        self.report({'INFO'}, "Salvo em %s" % arq)
        return {'FINISHED'}


# Fracao da altura da viewport que sobra para a viewport ao abrir a
# biblioteca embaixo dela.
FRACAO_ASSET_BROWSER = 0.35


def _apontar_asset_browser():
    """Aponta o Asset Browser recem-aberto para a biblioteca do addon.

    Roda adiado porque `params` do SpaceFileBrowser so' passa a existir
    depois que a area e' desenhada pela primeira vez. As areas sao
    relidas do window_manager a cada chamada -- guardar a referencia
    arriscaria usar um ponteiro morto se a area fosse fechada antes.
    """
    try:
        for janela in bpy.context.window_manager.windows:
            for area in janela.screen.areas:
                if area.type != 'FILE_BROWSER':
                    continue
                params = getattr(area.spaces.active, "params", None)
                if params is None:
                    continue
                # so' mexe em quem ainda esta' no padrao ("All
                # Libraries"): um browser que o usuario ja' apontou para
                # outra biblioteca nao pode ser sequestrado
                atual = getattr(params, "asset_library_reference", "")
                if atual in ("", "ALL"):
                    try:
                        params.asset_library_reference = NOME_BIBLIOTECA
                    except Exception as e:
                        print("[Cabinet Creator] biblioteca:", e)
                area.tag_redraw()
    except Exception as e:
        print("[Cabinet Creator] asset browser:", e)
    return None


def _area_asset_browser(tela):
    for area in tela.areas:
        if area.type == 'FILE_BROWSER' and area.ui_type == 'ASSETS':
            return area
    return None


class OBJECT_OT_abrir_asset_browser(Operator):
    """Abre a biblioteca do Blender embaixo da viewport; clique de novo
    para fechar"""
    bl_idname = "object.cabinet_asset_browser"
    bl_label = "Abrir no Asset Browser"

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        registrar_bibliotecas()
        tela = context.window.screen

        # ja' aberto: o mesmo botao fecha
        aberto = _area_asset_browser(tela)
        if aberto is not None:
            alvo = next((r for r in aberto.regions if r.type == 'WINDOW'),
                        None)
            try:
                with context.temp_override(area=aberto, region=alvo):
                    bpy.ops.screen.area_close()
                return {'FINISHED'}
            except Exception as e:
                print("[Cabinet Creator] fechar browser:", e)
                self.report({'WARNING'}, "Feche a area a mao")
                return {'CANCELLED'}

        # Uma JANELA nova nao serve: `Window.width/height` sao somente
        # leitura e nenhum operador aceita tamanho, entao ela nasceria
        # quase do tamanho da tela e esconderia o trabalho. Dividir a
        # viewport da uma area pequena, com o modelo sempre a' vista.
        area = context.area
        janela = next((r for r in area.regions if r.type == 'WINDOW'), None)
        antes = {a.as_pointer() for a in tela.areas}
        try:
            with context.temp_override(area=area, region=janela):
                bpy.ops.screen.area_split(direction='HORIZONTAL',
                                          factor=FRACAO_ASSET_BROWSER)
        except Exception as e:
            print("[Cabinet Creator] dividir area:", e)
            self.report({'WARNING'}, "Nao consegui abrir a biblioteca")
            return {'CANCELLED'}

        nova = next((a for a in tela.areas if a.as_pointer() not in antes),
                    None)
        if nova is None:
            self.report({'WARNING'}, "Nao consegui abrir a biblioteca")
            return {'CANCELLED'}
        try:
            nova.type = 'FILE_BROWSER'
            nova.ui_type = 'ASSETS'
        except Exception as e:
            print("[Cabinet Creator] asset browser:", e)
            self.report({'WARNING'}, "Troque o editor para Asset Browser")
            return {'CANCELLED'}
        # params so' nasce depois do primeiro desenho da area
        bpy.app.timers.register(_apontar_asset_browser, first_interval=0.2)
        return {'FINISHED'}


class OBJECT_OT_abrir_pasta_biblioteca(Operator):
    """Mostra o caminho da biblioteca no Explorer"""
    bl_idname = "object.cabinet_abrir_biblioteca"
    bl_label = "Abrir Pasta da Biblioteca"

    def execute(self, context):
        destino = pasta_biblioteca()
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


# ====================================================== SELECAO
# 1 clique seleciona o MODULO inteiro (o realce nativo do Blender acende
# em todas as pecas); 2 cliques isolam a chapa sob o cursor.
#
# As entradas ficam no keyconfig do ADDON, avaliado antes do padrao.
# Quando o poll falha -- fora do Object Mode, ou com a opcao desligada
# nas Preferencias -- o evento cai para o `view3d.select` nativo e o
# comportamento normal do Blender volta inteiro.


def familia_de(obj):
    """Tudo que deve acender junto com obj: as chapas do grupo mais o
    Empty do conjunto.

    Selecionar o pai JUNTO com os filhos e' seguro: o Blender nao
    transforma duas vezes o filho cujo pai tambem esta' selecionado.
    """
    if obj is None:
        return []
    portas = _grupo_portas(obj)
    if portas is not None:
        return [portas] + _folhas_portas(portas)
    if MARCA_CONJUNTO in obj:
        return [obj] + _chapas_do_conjunto(obj)
    if MARCA_CHAPA not in obj:
        return []
    chapas = grupo_de(obj, simetrico=True)
    pai = obj.parent
    if pai is not None and MARCA_CONJUNTO in pai:
        return [pai] + chapas
    return chapas


class OBJECT_OT_selecionar(Operator):
    """Clique seleciona o modulo inteiro; clique duplo isola a chapa"""
    bl_idname = "object.cabinet_selecionar"
    bl_label = "Selecionar Modulo"
    bl_options = {'UNDO'}

    modo: EnumProperty(
        name="Modo", default='GRUPO',
        items=[('GRUPO', "Grupo", "Seleciona o modulo inteiro"),
               ('INDIVIDUAL', "Individual", "Seleciona so' a chapa clicada")])
    # espelham as props do view3d.select: sao repassadas tal e qual
    location: IntVectorProperty(size=2, options={'SKIP_SAVE'})
    extend: BoolProperty(default=False)
    deselect: BoolProperty(default=False)
    toggle: BoolProperty(default=False)
    deselect_all: BoolProperty(default=False)
    select_passthrough: BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        p = _prefs()
        if p is not None and not p.selecao_por_grupo:
            return False
        return (context.mode == 'OBJECT' and context.area is not None
                and context.area.type == 'VIEW_3D'
                and not _eh_area_gaveta(context))

    def invoke(self, context, event):
        self.location = (event.mouse_region_x, event.mouse_region_y)
        return self.execute(context)

    def execute(self, context):
        # a escolha de QUEM foi clicado continua sendo do Blender; este
        # operador so' amplia (ou estreita) o resultado depois
        try:
            r = bpy.ops.view3d.select(
                'EXEC_DEFAULT',
                location=tuple(self.location),
                extend=self.extend, deselect=self.deselect,
                toggle=self.toggle, deselect_all=self.deselect_all,
                select_passthrough=self.select_passthrough)
        except Exception as e:
            print("[Cabinet Creator] selecao:", e)
            return {'CANCELLED'}
        if 'PASS_THROUGH' in r or 'CANCELLED' in r:
            return r

        obj = context.object
        familia = familia_de(obj)
        if not familia:
            return r

        # se o clique DESLIGOU a peca (shift), o grupo inteiro apaga junto
        ligado = obj.select_get()
        for o in familia:
            try:
                o.select_set(False if self.modo == 'INDIVIDUAL' else ligado)
            except Exception:
                pass
        if self.modo == 'INDIVIDUAL':
            obj.select_set(True)
        context.view_layer.objects.active = obj
        return r


_keymaps = []

# (valor do evento, shift, modo, props repassadas ao view3d.select)
# O PRESS simples leva select_passthrough para preservar o arraste: o
# clique sobre uma peca JA' selecionada nao desmonta a selecao, senao
# nao daria para arrastar o modulo inteiro depois de seleciona-lo.
_ENTRADAS_KEYMAP = (
    ('PRESS', False, 'GRUPO',
     {"deselect_all": True, "select_passthrough": True}),
    ('PRESS', True, 'GRUPO', {"toggle": True}),
    ('DOUBLE_CLICK', False, 'INDIVIDUAL', {"deselect_all": True}),
)


def registrar_keymaps():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:          # Blender em background nao monta keyconfig
        return
    km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
    # Esta entrada so' aceita eventos na area exclusiva da gaveta.
    kmi = km.keymap_items.new("object.cabinet_interagir_gaveta",
                              'LEFTMOUSE', 'PRESS', head=True)
    _keymaps.append((km, kmi))
    for evento in ('WHEELUPMOUSE', 'WHEELDOWNMOUSE'):
        kmi = km.keymap_items.new("object.cabinet_interagir_gaveta",
                                  evento, 'PRESS', head=True)
        _keymaps.append((km, kmi))
    for valor, shift, modo, props in _ENTRADAS_KEYMAP:
        kmi = km.keymap_items.new("object.cabinet_selecionar",
                                  'LEFTMOUSE', valor, shift=shift)
        kmi.properties.modo = modo
        for chave, v in props.items():
            setattr(kmi.properties, chave, v)
        _keymaps.append((km, kmi))

    # Posicionador a partir da grade. O keymap "User Interface" e' o
    # unico que enxerga botoes de painel. O gesto de ARRASTAR raramente
    # chega aqui (o handler de UI consome o PRESS antes), mas o
    # CLIQUE-para-posicionar do operador funciona de qualquer forma.
    km_ui = kc.keymaps.new(name="User Interface", space_type='EMPTY')
    kmi = km_ui.keymap_items.new("object.cabinet_arrastar_preset",
                                 'LEFTMOUSE', 'PRESS', head=True)
    _keymaps.append((km_ui, kmi))


def remover_keymaps():
    for km, kmi in _keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _keymaps.clear()


# ================================================ PORTAS PARAMETRICAS
LIMITES_FOLHAS = {'GIRO': 2, 'BASCULANTE': 1, 'CORRER': 4}
ITENS_ABERTURA = (
    ('GIRO', "Abrir (giro)", "Uma ou duas folhas"),
    ('BASCULANTE', "Basculante", "Exatamente uma folha"),
    ('CORRER', "Correr", "Uma a quatro folhas embutidas"),
)
ITENS_DOBRADICA = (
    ('ESCOLHER', "Escolha a dobradica...", "Escolha obrigatoria"),
    ('RETA', "Reta - sobreposta", "Cobre toda a espessura da lateral"),
    ('CURVA', "Curva - parcialmente sobreposta", "Cobre meia lateral"),
    ('SUPER_CURVA', "Super curva - embutida", "Dentro do vao"),
)
# A gaveta edita os parametros das portas direto, sem popup: por isso
# eles moram na Scene. O operador recebe tudo pronto e nunca abre
# dialogo. Rotulos curtos porque cada opcao vira um segmento de botao.
ESCOLHAS_PORTAS = (
    ('porta_frente', 'Frente', (('NEG_Y', '-Y'), ('POS_Y', '+Y'),
                                ('NEG_X', '-X'), ('POS_X', '+X'))),
    ('porta_orientacao', 'Eixos do vao', (('AUTO', 'Pai/mundo'),
                                          ('MUNDO', 'Mundo'),
                                          ('ATIVO', 'Ativo'))),
    ('porta_abertura', 'Abertura', (('GIRO', 'Giro'),
                                    ('BASCULANTE', 'Basculante'),
                                    ('CORRER', 'Correr'))),
)
# (prop em metros, prop em mm, rotulo, minimo em mm)
MEDIDAS_PORTAS = (
    ('ui_porta_folga', 'porta_folga_mm', 'Folga no perimetro', 0.0),
    ('ui_porta_entre_folhas', 'porta_entre_folhas_mm', 'Entre folhas', 0.0),
    ('ui_porta_afastamento', 'porta_afastamento_mm', 'Afastamento', 0.0),
    ('ui_porta_recuo_embutida', 'porta_recuo_embutida_mm',
     'Recuo da embutida', 0.0),
    ('ui_porta_recuo_correr', 'porta_recuo_correr_mm',
     'Recuo para trilhos', 0.1),
    ('ui_porta_sobreposicao', 'porta_sobreposicao_mm', 'Sobreposicao', 0.0),
    ('ui_porta_entre_planos', 'porta_entre_planos_mm',
     'Entre planos', 0.1),
)


def _parametros_portas_da_cena(s, numerico=False):
    """Os mesmos nomes que `_PARAMETROS_PORTAS` espera.

    As espessuras sao Enum -- ou seja, STRING. O operador quer a
    string (a prop dele tambem e' Enum), mas
    `_calcular_folhas_portas` faz conta com elas e quebra com texto:
    quem for calcular direto pede `numerico=True`.
    """
    converter = float if numerico else (lambda v: v)
    return {
        'abertura': s.porta_abertura,
        'folhas': s.porta_folhas,
        'dobradica': s.porta_dobradica,
        'espessura_mm': converter(s.porta_espessura),
        'lateral_mm': converter(s.porta_lateral),
        'folga_mm': s.porta_folga_mm,
        'entre_folhas_mm': s.porta_entre_folhas_mm,
        'afastamento_mm': s.porta_afastamento_mm,
        'recuo_embutida_mm': s.porta_recuo_embutida_mm,
        'recuo_correr_mm': s.porta_recuo_correr_mm,
        'sobreposicao_mm': s.porta_sobreposicao_mm,
        'entre_planos_mm': s.porta_entre_planos_mm,
    }


def _carregar_portas_na_cena(s, grupo):
    """Traz os parametros de um grupo existente para a gaveta."""
    guardados = grupo.get('porta_parametros') or {}
    for nome, valor in guardados.items():
        if nome == 'espessura_mm':
            s.porta_espessura = str(int(valor))
        elif nome == 'lateral_mm':
            s.porta_lateral = str(int(valor))
        elif nome == 'folhas':
            s.porta_folhas = int(valor)
        elif nome in {'abertura', 'dobradica'}:
            setattr(s, 'porta_' + nome, valor)
        elif nome in _PARAMETROS_PORTAS:
            setattr(s, 'porta_' + nome, float(valor))


_PARAMETROS_PORTAS = (
    'abertura', 'folhas', 'dobradica', 'espessura_mm', 'lateral_mm',
    'folga_mm', 'entre_folhas_mm', 'afastamento_mm', 'recuo_embutida_mm',
    'recuo_correr_mm', 'sobreposicao_mm', 'entre_planos_mm',
)


def _grupo_portas(obj):
    if obj is not None and MARCA_PORTAS in obj:
        return obj
    if (obj is not None and MARCA_FOLHA in obj and obj.parent is not None
            and MARCA_PORTAS in obj.parent):
        return obj.parent
    return None


def _folhas_portas(grupo):
    return sorted((o for o in grupo.children if MARCA_FOLHA in o),
                  key=lambda o: o.get('porta_indice', 0))


def _capturar_vertices_portas(context):
    """Le o BMesh vivo, inclusive selecao em duas chapas distintas."""
    if context.mode != 'EDIT_MESH':
        raise ValueError("Entre no Modo Edicao e selecione 2 vertices diagonais")
    marcados = []
    # Nao usar unique_data: instancias da mesma malha tem matrizes distintas.
    for obj in context.objects_in_mode:
        if obj.type != 'MESH':
            continue
        bm = bmesh.from_edit_mesh(obj.data)
        for vert in bm.verts:
            if vert.select and not vert.hide:
                marcados.append((obj, obj.matrix_world @ vert.co))
                if len(marcados) > 2:
                    raise ValueError("Selecione exatamente 2 vertices no total")
    if len(marcados) != 2:
        raise ValueError("Selecione exatamente 2 vertices no total")

    referencia, pai = _referencia_do_par(marcados[0][0], marcados[1][0])
    return marcados[0][1], marcados[1][1], referencia, pai


def _referencia_do_par(obj_a, obj_b):
    """Orientacao do vao a partir do ancestral comum das duas pecas.

    E' o ancestral que da' os eixos do modulo; a rotacao individual de
    uma lateral nao serve, porque o Z local dela e' a espessura.
    """
    ancestrais = []
    pai = obj_a.parent
    while pai is not None:
        ancestrais.append(pai)
        pai = pai.parent
    pai = obj_b.parent
    while pai is not None and pai not in ancestrais:
        pai = pai.parent
    referencia = (pai.matrix_world.to_quaternion().to_matrix()
                  if pai is not None else Matrix.Identity(3))
    return referencia, pai


def _mapear_vao_portas(ponto_a, ponto_b, referencia, frente):
    """Base ortonormal: X=largura, Y=altura, Z=fora do movel."""
    normais = {'NEG_Y': (0, -1, 0), 'POS_Y': (0, 1, 0),
               'NEG_X': (-1, 0, 0), 'POS_X': (1, 0, 0)}
    normal = referencia @ Vector(normais[frente])
    cima = referencia @ Vector((0, 0, 1))
    direita = cima.cross(normal).normalized()
    base = Matrix((direita, cima, normal)).transposed()
    a = base.transposed() @ Vector(ponto_a)
    b = base.transposed() @ Vector(ponto_b)
    if abs(a.z - b.z) > 0.0001:
        raise ValueError("Vertices fora do mesmo plano frontal; confira Frente")
    largura, altura = abs(a.x - b.x), abs(a.y - b.y)
    if largura < 0.001 or altura < 0.001:
        raise ValueError("Os vertices devem formar uma diagonal com largura e altura")
    origem = base @ Vector((min(a.x, b.x), min(a.y, b.y),
                             (a.z + b.z) / 2.0))
    matriz = base.to_4x4()
    matriz.translation = origem
    return largura * 1000.0, altura * 1000.0, matriz


def _calcular_folhas_portas(largura, altura, parametros):
    """Retorna (L, A, E, centro_mm) por folha; nenhuma ferragem e' criada."""
    p = parametros
    abertura, n = p['abertura'], p['folhas']
    if abertura not in LIMITES_FOLHAS or not 1 <= n <= LIMITES_FOLHAS[abertura]:
        raise ValueError("Quantidade de folhas invalida para esta abertura")
    numericos = [largura, altura] + [p[k] for k in _PARAMETROS_PORTAS
                                    if k.endswith('_mm')]
    if not all(math.isfinite(v) and v >= 0 for v in numericos):
        raise ValueError("As medidas devem ser finitas e nao negativas")
    e, lateral = p['espessura_mm'], p['lateral_mm']
    if e not in ESPESSURAS_PERMITIDAS or lateral not in ESPESSURAS_PERMITIDAS:
        raise ValueError("Use espessuras de 15, 18, 20 ou 30 mm")
    correr = abertura == 'CORRER'
    if not correr and p['dobradica'] not in {'RETA', 'CURVA', 'SUPER_CURVA'}:
        raise ValueError("Escolha a dobradica: reta, curva ou super curva")
    cobertura = (0.0 if correr else
                 {'RETA': lateral, 'CURVA': lateral / 2.0,
                  'SUPER_CURVA': 0.0}[p['dobradica']])
    inicio = p['folga_mm'] - cobertura
    util = largura - 2.0 * inicio
    a = altura - 2.0 * inicio
    if correr:
        if p['recuo_correr_mm'] <= 0:
            raise ValueError("Portas de correr exigem recuo positivo para os trilhos")
        sobreposicao = p['sobreposicao_mm'] if n > 1 else 0.0
        l = (util + (n - 1) * sobreposicao) / n
        passo = l - sobreposicao
        if passo <= 0 or (n > 2 and 2 * passo < l - 1e-6):
            raise ValueError("Sobreposicao excessiva: folhas no mesmo plano colidem")
    else:
        l = (util - (n - 1) * p['entre_folhas_mm']) / n
        passo = l + p['entre_folhas_mm']
    if l < 1.0 or a < 1.0:
        raise ValueError("Folgas maiores que o vao disponivel")
    saida = []
    for i in range(n):
        if correr:
            # Dois planos alternados. O recuo mede a FACE mais externa,
            # assim nem meia espessura invade o espaco reservado ao trilho.
            z = (-p['recuo_correr_mm'] - e / 2.0
                 - (i % 2) * (e + p['entre_planos_mm']))
        elif p['dobradica'] == 'SUPER_CURVA':
            z = -p['recuo_embutida_mm'] - e / 2.0
        else:
            z = p['afastamento_mm'] + e / 2.0
        saida.append((l, a, e,
                      (inicio + l / 2.0 + i * passo,
                       inicio + a / 2.0, z)))
    return saida


# ============================== VINCULO DA PORTA COM O MODULO (cenario 2)
# Quando o primeiro clique cai numa CHAPA, o vao pertence ao modulo que
# a contem. Guardar o vao em milimetros absolutos quebraria o vinculo no
# primeiro redimensionamento; por isso as quatro folgas ate' as faces do
# modulo sao guardadas em ESPESSURAS. Assim a porta acompanha tanto a
# largura/altura do modulo quanto a espessura das chapas, que e'
# exatamente o que delimita o vao.
CHAVE_MODULO_PORTA = "porta_modulo"
CHAVE_FOLGAS_PORTA = "porta_folgas_em_e"
CHAVE_RECUO_PORTA = "porta_recuo_frente_mm"


# Enquanto o apanhador roda, o botao da aba fica aceso. Sem isso o
# usuario nao tem como saber que a ferramenta esta' esperando os dois
# cliques na viewport.
_apanhando_vao = [False]


def _marcar_apanhando(ligado):
    if _apanhando_vao[0] == ligado:
        return
    _apanhando_vao[0] = ligado
    for janela in bpy.context.window_manager.windows:
        for area in janela.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _motivo_portas(s):
    """O que impede de criar a porta agora, ou '' se nada impede.

    O operador recusa parametros invalidos, mas o aviso dele nao chega
    a quem esta' olhando a gaveta -- clicar parecia nao fazer nada.
    Aqui o proprio botao passa a dizer o que falta.
    """
    try:
        _calcular_folhas_portas(1000.0, 1000.0,
                                _parametros_portas_da_cena(s, numerico=True))
    except (ValueError, KeyError, TypeError) as erro:
        return str(erro)
    return ''


def _modulo_da_chapa(obj):
    """Conjunto que contem esta chapa, subindo pelos pais."""
    if obj is None or MARCA_CHAPA not in obj:
        return None
    pai = obj.parent
    while pai is not None:
        if MARCA_CONJUNTO in pai:
            return pai
        pai = pai.parent
    return None


def _caixa_do_modulo(conj):
    """(L, A, P, E) em mm do modulo, ou None se faltar medida."""
    try:
        return (float(conj.conj_largura_mm), float(conj.conj_altura_mm),
                float(conj.conj_profundidade_mm),
                float(conj.conj_espessura_mm))
    except (AttributeError, TypeError, ValueError):
        return None


def _local_no_modulo(conj, ponto):
    """Ponto de mundo nos eixos do modulo, em mm."""
    return conj.matrix_world.inverted() @ Vector(ponto) * 1000.0


def _folgas_do_vao(conj, ponto_a, ponto_b, frente):
    """Folgas (esq, dir, baixo, cima) em ESPESSURAS mais o recuo em mm.

    O Empty do conjunto fica no centro X/Y e na base Z (ver
    `reposicionar_origem`), entao a caixa local vai de -L/2 a L/2 em X,
    de -P/2 a P/2 em Y e de 0 a A em Z.
    """
    caixa = _caixa_do_modulo(conj)
    if caixa is None:
        return None
    L, A, P, E = caixa
    if E <= 0.0:
        return None
    a = _local_no_modulo(conj, ponto_a)
    b = _local_no_modulo(conj, ponto_b)
    if frente in {'NEG_Y', 'POS_Y'}:
        esq, dir_ = min(a.x, b.x) + L / 2.0, L / 2.0 - max(a.x, b.x)
        recuo = (min(a.y, b.y) + P / 2.0 if frente == 'NEG_Y'
                 else P / 2.0 - max(a.y, b.y))
    else:
        esq, dir_ = min(a.y, b.y) + P / 2.0, P / 2.0 - max(a.y, b.y)
        recuo = (min(a.x, b.x) + L / 2.0 if frente == 'NEG_X'
                 else L / 2.0 - max(a.x, b.x))
    baixo, cima = min(a.z, b.z), A - max(a.z, b.z)
    return ((esq / E, dir_ / E, baixo / E, cima / E), recuo)


def _vao_do_modulo(conj, folgas, recuo, frente):
    """Refaz (largura, altura, matriz) do vao a partir do modulo de hoje."""
    caixa = _caixa_do_modulo(conj)
    if caixa is None:
        return None
    L, A, P, E = caixa
    esq, dir_, baixo, cima = (f * E for f in folgas)
    if frente in {'NEG_Y', 'POS_Y'}:
        x0, x1 = -L / 2.0 + esq, L / 2.0 - dir_
        plano = -P / 2.0 + recuo if frente == 'NEG_Y' else P / 2.0 - recuo
        canto_a = Vector((x0, plano, baixo))
        canto_b = Vector((x1, plano, A - cima))
    else:
        y0, y1 = -P / 2.0 + esq, P / 2.0 - dir_
        plano = -L / 2.0 + recuo if frente == 'NEG_X' else L / 2.0 - recuo
        canto_a = Vector((plano, y0, baixo))
        canto_b = Vector((plano, y1, A - cima))
    mundo = conj.matrix_world
    referencia = mundo.to_quaternion().to_matrix()
    return _mapear_vao_portas(mundo @ (canto_a / 1000.0),
                              mundo @ (canto_b / 1000.0),
                              referencia, frente)


def _portas_do_conjunto(conj):
    """Grupos de porta vinculados a este modulo."""
    return [o for o in bpy.data.objects
            if MARCA_PORTAS in o and o.get(CHAVE_MODULO_PORTA) == conj.name]


def atualizar_portas_do_conjunto(conj):
    """Refaz as folhas depois que o modulo mudou de medida.

    Chamado DEPOIS de `redimensionar_grupo` / `aplicar_espessura_grupo`,
    nunca durante: as folhas leem as medidas ja' aplicadas.
    """
    if conj is None or MARCA_CONJUNTO not in conj:
        return
    for grupo in _portas_do_conjunto(conj):
        folgas = grupo.get(CHAVE_FOLGAS_PORTA)
        parametros = grupo.get('porta_parametros')
        if not folgas or not parametros:
            continue
        frente = grupo.get('porta_frente', 'NEG_Y')
        try:
            vao = _vao_do_modulo(conj, list(folgas),
                                 float(grupo.get(CHAVE_RECUO_PORTA, 0.0)),
                                 frente)
            if vao is None:
                continue
            largura, altura, matriz = vao
            _aplicar_portas(bpy.context, grupo, matriz, conj,
                            largura, altura, dict(parametros))
        except (ValueError, KeyError, TypeError) as e:
            print("[Cabinet Creator] porta vinculada:", e)


def _aplicar_portas(context, grupo, matriz, pai, largura, altura,
                    parametros, frente=''):
    """Valida antes de alterar a cena; reutiliza folhas e seus materiais."""
    calculadas = _calcular_folhas_portas(largura, altura, parametros)
    antigas = _folhas_portas(grupo) if grupo is not None else []
    if any(o.type != 'MESH' or o.mode != 'OBJECT' for o in antigas):
        raise ValueError("Saia do Modo Edicao das portas antes de reconfigurar")
    ocupado_antes = _ocupado[0]
    _ocupado[0] = True
    try:
        if grupo is None:
            grupo = bpy.data.objects.new("Portas", None)
            context.collection.objects.link(grupo)
            grupo[MARCA_PORTAS] = 1
            grupo.empty_display_type = 'PLAIN_AXES'
            grupo.empty_display_size = 0.05
            grupo.parent = pai
            # As medidas sao de mundo, mesmo quando o pai tem escala.
            if pai is not None:
                grupo.matrix_parent_inverse = pai.matrix_world.inverted()
            grupo.matrix_world = matriz
        grupo['porta_parametros'] = dict(parametros)
        grupo['porta_vao_largura_mm'] = largura
        grupo['porta_vao_altura_mm'] = altura
        if frente:
            grupo['porta_frente'] = frente
        for i, (l, a, e, centro) in enumerate(calculadas):
            if i < len(antigas):
                folha = antigas[i]
                if folha.data.users > 1:
                    folha.data = folha.data.copy()
            else:
                malha = bpy.data.meshes.new("Porta")
                folha = bpy.data.objects.new("Porta_%02d" % (i + 1), malha)
                grupo.users_collection[0].objects.link(folha)
                folha[MARCA_CHAPA] = 1
                folha[MARCA_FOLHA] = 1
            folha['porta_indice'] = i
            folha.parent = grupo
            folha.matrix_parent_inverse = Matrix.Identity(4)
            folha.matrix_basis = Matrix.Translation(Vector(centro) / 1000.0)
            folha.chapa_largura_mm = l
            folha.chapa_comprimento_mm = a
            folha.chapa_espessura_mm = e
            folha.chapa_auto = True
        # Apenas folhas geradas que deixaram de existir na nova tipologia.
        for folha in antigas[len(calculadas):]:
            malha = folha.data
            bpy.data.objects.remove(folha, do_unlink=True)
            if malha.users == 0:
                bpy.data.meshes.remove(malha)
    finally:
        _ocupado[0] = ocupado_antes
    for folha in _folhas_portas(grupo):
        gerar_malha_chapa(folha)
    context.view_layer.update()
    return grupo


def _limitar_folhas_cena(self, context):
    """Abertura nova pode nao aceitar a quantidade de folhas atual."""
    limite = LIMITES_FOLHAS.get(self.porta_abertura, 1)
    if self.porta_folhas > limite:
        self.porta_folhas = limite


def _limitar_folhas_portas(self, context):
    limite = LIMITES_FOLHAS[self.abertura]
    if self.folhas > limite:
        self.folhas = limite


# ==================================== APANHADOR DO VAO DAS PORTAS
# Marcar o vao exigia entrar em Modo Edicao e selecionar 2 vertices em
# duas chapas diferentes. Aqui o usuario fica em Modo Objeto: o cursor
# ganha um ima que gruda no vertice mais proximo, o primeiro clique
# fixa um canto e a previa das folhas acompanha o mouse ate' o segundo.
RAIO_IMA_PX = 28.0          # alcance do ima, em pixels de tela
TETO_VERTICES_IMA = 60000   # acima disto o ima desiste de um objeto

ARESTAS_CAIXA = (
    (0, 1), (1, 3), (3, 2), (2, 0),
    (4, 5), (5, 7), (7, 6), (6, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
)


def _alvos_do_ima(context):
    """(objeto, vertices em MUNDO) de tudo que o ima pode pegar.

    Os vertices sao lidos UMA vez, no invoke: reavaliar o depsgraph a
    cada movimento do mouse derrubaria o quadro. Quem mexer na cena
    durante a marcacao precisa recomecar -- e' o preco justo.
    """
    try:
        dep = context.evaluated_depsgraph_get()
    except Exception:
        dep = None
    alvos = []
    for obj in context.visible_objects:
        if obj.type != 'MESH':
            continue
        avaliado = obj.evaluated_get(dep) if dep is not None else obj
        try:
            malha = avaliado.to_mesh()
        except Exception:
            malha = None
        if malha is None:
            continue
        try:
            if 0 < len(malha.vertices) <= TETO_VERTICES_IMA:
                m = obj.matrix_world
                alvos.append((obj, [m @ v.co.copy() for v in malha.vertices]))
        finally:
            try:
                avaliado.to_mesh_clear()
            except Exception:
                pass
    return alvos


class OBJECT_OT_apanhar_vao_portas(Operator):
    """Marca os 2 cantos do vao na viewport, com ima nos vertices"""
    bl_idname = "object.cabinet_apanhar_vao"
    bl_label = "Apanhar Vao das Portas"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    # ------------------------------------------------ ima
    def _mouse_na_regiao(self, event):
        # O apanhador costuma ser disparado da gaveta, que e' outra
        # area: mouse_region_* viria da gaveta, nao da viewport.
        return Vector((event.mouse_x - self._regiao.x,
                       event.mouse_y - self._regiao.y))

    def _imantar(self, event):
        alvo = self._mouse_na_regiao(event)
        melhor, melhor_obj, melhor_d = None, None, RAIO_IMA_PX
        for obj, vertices in self._alvos:
            for co in vertices:
                tela = view3d_utils.location_3d_to_region_2d(
                    self._regiao, self._rv3d, co)
                if tela is None:
                    continue
                d = (tela - alvo).length
                if d < melhor_d:
                    melhor, melhor_obj, melhor_d = co, obj, d
        self._imantado = melhor
        self._objeto_imantado = melhor_obj

    # ------------------------------------------------ previa
    def _referencia(self, obj_a, obj_b):
        """Mesma escolha de eixos que o operador fara' depois."""
        s = bpy.context.scene
        if s.porta_orientacao == 'MUNDO':
            return Matrix.Identity(3)
        if s.porta_orientacao == 'ATIVO':
            return obj_a.matrix_world.to_quaternion().to_matrix()
        return _referencia_do_par(obj_a, obj_b)[0]

    def _previa(self):
        """Caixas das folhas entre o ponto fixo e o ponto sob o cursor.

        Usa os parametros da ABA, nao um padrao fixo: o que se ve
        arrastando tem de ser a porta que vai nascer. Quando a conta
        nao fecha, guarda o motivo em `_recado` -- antes a previa
        sumia calada e o usuario nao sabia o que estava errado.
        """
        self._recado = ''
        if not self._pontos or self._imantado is None:
            return []
        a, obj_a = self._pontos[0]
        obj_b = self._objeto_imantado or obj_a
        parametros = _parametros_portas_da_cena(bpy.context.scene,
                                                numerico=True)
        # So' para DESENHAR: a escolha de verdade continua obrigatoria
        # e e' cobrada antes de comecar o gesto.
        if parametros['dobradica'] == 'ESCOLHER':
            parametros['dobradica'] = 'RETA'
        try:
            largura, altura, matriz = _mapear_vao_portas(
                a, self._imantado, self._referencia(obj_a, obj_b),
                self._frente)
            folhas = _calcular_folhas_portas(largura, altura, parametros)
        except (ValueError, KeyError) as erro:
            self._recado = str(erro)
            return []
        self._recado = 'Vao %.0f x %.0f mm - %d folha(s)' % (
            largura, altura, len(folhas))
        caixas = []
        for l, alt, e, centro in folhas:
            meia = Vector((l, alt, e)) / 2000.0
            c = Vector(centro) / 1000.0
            cantos = [matriz @ Vector((c.x + meia.x * sx,
                                       c.y + meia.y * sy,
                                       c.z + meia.z * sz))
                      for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
            caixas.append(cantos)
        return caixas

    def _desenhar(self):
        regiao = getattr(bpy.context, "region", None)
        if regiao is None or regiao.as_pointer() != self._regiao_ptr:
            return
        tema = bpy.context.preferences.themes[0]
        cor_ima = (*tema.view_3d.object_active, 1.0)
        cor_previa = (*tema.user_interface.wcol_regular.text, 0.9)
        linhas = []
        for cantos in self._previa():
            for i, j in ARESTAS_CAIXA:
                linhas.extend((cantos[i], cantos[j]))
        # a linha do primeiro canto ate' o cursor, para o gesto ter fio
        if self._pontos and self._imantado is not None:
            linhas.extend((self._pontos[0][0], self._imantado))
        try:
            gpu.state.blend_set('ALPHA')
            gpu.state.depth_test_set('NONE')
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            shader.bind()
            if linhas:
                gpu.state.line_width_set(1.6)
                shader.uniform_float('color', cor_previa)
                batch_for_shader(shader, 'LINES', {'pos': linhas}).draw(shader)
            marcas = [p[0] for p in self._pontos]
            if self._imantado is not None:
                marcas.append(self._imantado)
            if marcas:
                gpu.state.point_size_set(11.0)
                shader.uniform_float('color', cor_ima)
                batch_for_shader(shader, 'POINTS',
                                 {'pos': marcas}).draw(shader)
        except Exception as e:
            print("[Cabinet Creator] previa do vao:", e)
        finally:
            try:
                gpu.state.line_width_set(1.0)
                gpu.state.point_size_set(1.0)
                gpu.state.blend_set('NONE')
            except Exception:
                pass

    # ------------------------------------------------ ciclo
    def _encerrar(self, context):
        _marcar_apanhando(False)
        if self._area is not None:
            self._area.header_text_set(None)
        if self._handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
            self._handler = None
        if self._area is not None:
            self._area.tag_redraw()
        context.window.cursor_modal_restore()

    def invoke(self, context, event):
        self._area = context.area
        if _eh_area_gaveta(context):
            self._area = next(
                (a for a in context.screen.areas
                 if a.type == 'VIEW_3D' and a != context.area
                 and a.x > context.area.x and a.y == context.area.y), None)
        if self._area is None or self._area.type != 'VIEW_3D':
            self.report({'ERROR'}, "Sem viewport 3D para marcar o vao")
            return {'CANCELLED'}
        self._regiao = next((r for r in self._area.regions
                             if r.type == 'WINDOW'), None)
        self._rv3d = getattr(self._area.spaces.active, "region_3d", None)
        if self._regiao is None or self._rv3d is None:
            self.report({'ERROR'}, "Sem viewport 3D para marcar o vao")
            return {'CANCELLED'}
        self._regiao_ptr = self._regiao.as_pointer()

        # Um vao de mentira so' para validar os parametros: melhor
        # recusar agora do que deixar o usuario fazer o gesto inteiro
        # e so' entao descobrir que falta escolher a dobradica.
        try:
            _calcular_folhas_portas(
                1000.0, 1000.0,
                _parametros_portas_da_cena(context.scene, numerico=True))
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, "%s (aba Portas)" % erro)
            return {'CANCELLED'}

        self._alvos = _alvos_do_ima(context)
        if not self._alvos:
            self.report({'WARNING'}, "Nenhuma malha visivel para o ima")
            return {'CANCELLED'}
        self._pontos = []
        self._imantado = None
        self._objeto_imantado = None
        self._frente = context.scene.porta_frente
        self._recado = ''
        self._handler = None
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            self._desenhar, (), 'WINDOW', 'POST_VIEW')
        _marcar_apanhando(True)
        context.window.cursor_modal_set('CROSSHAIR')
        context.window_manager.modal_handler_add(self)
        self.report({'INFO'}, "Clique nos 2 cantos do vao (Esc cancela)")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        # Navegar precisa continuar funcionando durante a marcacao.
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._encerrar(context)
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            self._imantar(event)
            self._previa()
            self._area.header_text_set(
                self._recado or 'Clique nos 2 cantos do vao')
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self._imantar(event)
            if self._imantado is None:
                self.report({'WARNING'}, "Aproxime de um vertice")
                return {'RUNNING_MODAL'}
            self._pontos.append((self._imantado.copy(),
                                 self._objeto_imantado))
            self._area.tag_redraw()
            if len(self._pontos) < 2:
                return {'RUNNING_MODAL'}
            return self._concluir(context)
        return {'RUNNING_MODAL'}

    def _concluir(self, context):
        (a, obj_a), (b, obj_b) = self._pontos
        self._encerrar(context)
        referencia, pai = _referencia_do_par(obj_a, obj_b)
        # Cenario 2: o primeiro clique caiu numa chapa, entao o vao
        # pertence ao modulo que a contem e a porta fica vinculada a ele.
        modulo = _modulo_da_chapa(obj_a)
        ativa = obj_a.matrix_world.to_quaternion().to_matrix()
        s = context.scene
        try:
            # EXEC_DEFAULT, nao INVOKE: os parametros ja' vieram da aba
            # Portas, entao nao ha' dialogo nenhum para abrir.
            bpy.ops.object.cabinet_portas(
                'EXEC_DEFAULT', capturado=True,
                ponto_a=a, ponto_b=b,
                referencia=tuple(v for linha in referencia for v in linha),
                referencia_ativa=tuple(v for linha in ativa for v in linha),
                pai_nome=pai.name if pai is not None else '',
                modulo_nome=modulo.name if modulo is not None else '',
                orientacao=s.porta_orientacao, frente=s.porta_frente,
                **_parametros_portas_da_cena(s))
        except RuntimeError as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        return {'FINISHED'}


class OBJECT_OT_portas_parametricas(Operator):
    """Cria portas por 2 vertices diagonais ou reconfigura o grupo selecionado"""
    bl_idname = "object.cabinet_portas"
    bl_label = "Portas Parametricas"
    bl_options = {'REGISTER', 'UNDO'}

    editar: BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})
    grupo_nome: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    capturado: BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})
    ponto_a: FloatVectorProperty(size=3, options={'HIDDEN'})
    ponto_b: FloatVectorProperty(size=3, options={'HIDDEN'})
    referencia: FloatVectorProperty(
        size=9, default=(1, 0, 0, 0, 1, 0, 0, 0, 1), options={'HIDDEN'})
    referencia_ativa: FloatVectorProperty(
        size=9, default=(1, 0, 0, 0, 1, 0, 0, 0, 1), options={'HIDDEN'})
    pai_nome: StringProperty(options={'HIDDEN'})
    modulo_nome: StringProperty(options={'HIDDEN'})
    orientacao: EnumProperty(
        name="Eixos do vao", default='AUTO',
        items=[('AUTO', "Pai comum / mundo", "Usa os eixos do pai comum, se existir"),
               ('MUNDO', "Mundo", "Largura X/Y e altura Z do mundo"),
               ('ATIVO', "Objeto ativo", "Para um movel rotacionado sem pai; altura Z local")])
    frente: EnumProperty(
        name="Frente", default='NEG_Y',
        description="Direcao para fora, nos eixos do pai comum ou do mundo",
        items=[('NEG_Y', "-Y (frontal)", "Exterior em -Y"),
               ('POS_Y', "+Y (traseira)", "Exterior em +Y"),
               ('NEG_X', "-X (esquerda)", "Exterior em -X"),
               ('POS_X', "+X (direita)", "Exterior em +X")])
    abertura: EnumProperty(name="Abertura", items=ITENS_ABERTURA,
                           default='GIRO', update=_limitar_folhas_portas)
    folhas: IntProperty(name="Folhas", default=1, min=1, max=4,
                        update=_limitar_folhas_portas)
    dobradica: EnumProperty(name="Dobradica / posicionamento",
                            items=ITENS_DOBRADICA, default='ESCOLHER')
    espessura_mm: EnumProperty(
        name="Espessura da porta (mm)", default='18',
        items=[(str(int(e)), str(int(e)), "mm") for e in ESPESSURAS_PERMITIDAS])
    lateral_mm: EnumProperty(
        name="Espessura da lateral (mm)", default='18',
        items=[(str(int(e)), str(int(e)), "mm") for e in ESPESSURAS_PERMITIDAS])
    folga_mm: FloatProperty(name="Folga no perimetro (mm)", default=0, min=0)
    entre_folhas_mm: FloatProperty(name="Folga entre folhas (mm)", default=2, min=0)
    afastamento_mm: FloatProperty(name="Afastamento frontal (mm)", default=0, min=0)
    recuo_embutida_mm: FloatProperty(name="Recuo da embutida (mm)", default=0, min=0)
    recuo_correr_mm: FloatProperty(
        name="Recuo para trilhos (mm)", default=30, min=0.1,
        description="Distancia da borda frontal ate a face externa da primeira folha")
    sobreposicao_mm: FloatProperty(name="Sobreposicao entre folhas (mm)", default=20, min=0)
    entre_planos_mm: FloatProperty(name="Folga entre planos (mm)", default=2, min=0.1)

    @classmethod
    def poll(cls, context):
        # Em Modo Objeto o vao pode chegar do apanhador
        # (`cabinet_apanhar_vao`), que passa os pontos ja' prontos; o
        # invoke e' quem valida o que faltar.
        return context.mode in {'EDIT_MESH', 'OBJECT'}

    def _capturar(self, context):
        a, b, ref, pai = _capturar_vertices_portas(context)
        self.ponto_a, self.ponto_b = a, b
        self.referencia = tuple(v for linha in ref for v in linha)
        ativa = context.edit_object.matrix_world.to_quaternion().to_matrix()
        self.referencia_ativa = tuple(v for linha in ativa for v in linha)
        self.pai_nome = pai.name if pai is not None else ''
        self.capturado = True

    def _vao(self):
        valores = self.referencia_ativa if self.orientacao == 'ATIVO' else self.referencia
        ref = (Matrix.Identity(3) if self.orientacao == 'MUNDO' else
               Matrix([valores[i:i + 3] for i in (0, 3, 6)]))
        return _mapear_vao_portas(self.ponto_a, self.ponto_b, ref, self.frente)

    def _parametros(self):
        p = {nome: getattr(self, nome) for nome in _PARAMETROS_PORTAS}
        p['espessura_mm'] = float(self.espessura_mm)
        p['lateral_mm'] = float(self.lateral_mm)
        return p

    def invoke(self, context, event):
        try:
            if context.mode == 'OBJECT' and _grupo_portas(context.object) is not None:
                self.editar = True
            if self.editar:
                grupo = _grupo_portas(context.object)
                if grupo is None or context.mode != 'OBJECT':
                    raise ValueError("Selecione um grupo de portas no Modo Objeto")
                self.grupo_nome = grupo.name
                for nome, valor in grupo['porta_parametros'].items():
                    if nome in _PARAMETROS_PORTAS:
                        setattr(self, nome, str(int(valor)) if nome in
                                {'espessura_mm', 'lateral_mm'} else valor)
            else:
                # Pontos ja' apanhados na viewport dispensam o Modo
                # Edicao; sem eles, cai na captura por vertices.
                if not self.capturado:
                    self._capturar(context)
                # Toda instalacao exige uma escolha, mesmo apos usar F3 de novo.
                self.dobradica = 'ESCOLHER'
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=440)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        try:
            if self.editar:
                grupo = bpy.data.objects.get(self.grupo_nome)
                largura = grupo['porta_vao_largura_mm']
                altura = grupo['porta_vao_altura_mm']
            else:
                layout.prop(self, 'orientacao')
                layout.prop(self, 'frente')
                if self.orientacao == 'AUTO':
                    layout.label(text="Eixos: " + (self.pai_nome or "Mundo"))
                largura, altura, _ = self._vao()
            layout.label(text="Vao: %.1f x %.1f mm" % (largura, altura))
        except (ValueError, KeyError, TypeError) as erro:
            largura = altura = None
            layout.label(text=str(erro), icon='ERROR')
        layout.prop(self, 'abertura')
        linha = layout.row()
        linha.enabled = self.abertura != 'BASCULANTE'
        linha.prop(self, 'folhas')
        layout.label(text="Permitido: 1 a %d folha(s)" % LIMITES_FOLHAS[self.abertura])
        layout.prop(self, 'espessura_mm')
        if self.abertura != 'CORRER':
            caixa = layout.box()
            caixa.label(text="Qual dobradica / posicionamento?")
            caixa.prop(self, 'dobradica', text="")
            if self.dobradica in {'RETA', 'CURVA'}:
                caixa.prop(self, 'lateral_mm')
                caixa.prop(self, 'afastamento_mm')
            elif self.dobradica == 'SUPER_CURVA':
                caixa.prop(self, 'recuo_embutida_mm')
            if self.folhas > 1:
                layout.prop(self, 'entre_folhas_mm')
        else:
            layout.label(text="Embutidas, em dois planos alternados")
            layout.prop(self, 'recuo_correr_mm')
            if self.folhas > 1:
                layout.prop(self, 'sobreposicao_mm')
                layout.prop(self, 'entre_planos_mm')
        layout.prop(self, 'folga_mm')
        if largura is not None:
            try:
                folhas = _calcular_folhas_portas(largura, altura, self._parametros())
                l, a, e, _ = folhas[0]
                layout.label(text="Cada folha: %.1f x %.1f x %.0f mm" % (l, a, e))
                if self.abertura == 'CORRER':
                    fundo = max(-f[3][2] + e / 2 for f in folhas)
                    layout.label(text="Profundidade ocupada desde a borda: %.1f mm" % fundo)
            except ValueError as erro:
                layout.label(text=str(erro), icon='ERROR')
        layout.label(text="Blocagem: somente os solidos das portas", icon='INFO')

    def check(self, context):
        return True

    def execute(self, context):
        try:
            grupo = None
            pai = None
            if self.editar:
                grupo = bpy.data.objects.get(self.grupo_nome) if self.grupo_nome else _grupo_portas(context.object)
                if grupo is None or MARCA_PORTAS not in grupo:
                    raise ValueError("Grupo de portas nao encontrado")
                largura = grupo['porta_vao_largura_mm']
                altura = grupo['porta_vao_altura_mm']
                matriz = grupo.matrix_world.copy()
            else:
                if not self.capturado:
                    self._capturar(context)
                largura, altura, matriz = self._vao()
                pai = bpy.data.objects.get(self.pai_nome) if self.pai_nome else None
                if pai is not None and abs(pai.matrix_world.determinant()) < 1e-12:
                    raise ValueError("O pai do vao tem escala zero")
            parametros = self._parametros()
            _calcular_folhas_portas(largura, altura, parametros)
            # Validacoes ocorrem ainda em Edit Mode; erro/cancelamento
            # conserva os dois vertices e nao deixa objetos incompletos.
            if context.mode == 'EDIT_MESH' and not self.editar:
                bpy.ops.object.mode_set(mode='OBJECT')
            grupo = _aplicar_portas(context, grupo, matriz, pai,
                                    largura, altura, parametros,
                                    frente=self.frente)
            # Cenario 2: as folgas ate' as faces do modulo, em
            # espessuras, sao o que mantem a porta acompanhando o
            # redimensionamento depois.
            modulo = bpy.data.objects.get(self.modulo_nome)
            if modulo is not None and not self.editar:
                medido = _folgas_do_vao(modulo, self.ponto_a, self.ponto_b,
                                        self.frente)
                if medido is not None:
                    grupo[CHAVE_MODULO_PORTA] = modulo.name
                    grupo[CHAVE_FOLGAS_PORTA] = list(medido[0])
                    grupo[CHAVE_RECUO_PORTA] = medido[1]
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        for obj in context.selected_objects:
            obj.select_set(False)
        grupo.select_set(True)
        for folha in _folhas_portas(grupo):
            folha.select_set(True)
        context.view_layer.objects.active = grupo
        # Com modulo vinculado, ele vira o ativo: o painel passa a
        # mostrar as medidas do conjunto e o wireframe a volumetria do
        # modulo com as portas na frente (etapa 3).
        vinculado = bpy.data.objects.get(grupo.get(CHAVE_MODULO_PORTA, ''))
        if vinculado is not None:
            vinculado.select_set(True)
            context.view_layer.objects.active = vinculado
        self.report({'INFO'}, "%d folha(s) - vao %.1f x %.1f mm" %
                    (self.folhas, largura, altura))
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

    alternar: BoolProperty(default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'

    def execute(self, context):
        obj = context.object
        if self.alternar and MARCA_CHAPA in obj:
            if MARCA_FOLHA in obj:
                self.report({'WARNING'}, 'Folha parametrica: edite pelo grupo de portas')
                return {'CANCELLED'}
            # A conversao explicita preserva a malha e a hierarquia. Limpar
            # referencias evita que a adjacencia use a chapa ja' desativada.
            for chapa in bpy.data.objects:
                if MARCA_CHAPA not in chapa:
                    continue
                for ponta in PONTAS:
                    base = 'adj_' + ponta
                    vizinho = _resolver_vizinho(
                        chapa, chapa.get(base + '_uid', ''), chapa.get(base, ''))
                    if chapa == obj or vizinho == obj:
                        for sufixo in ('', '_uid', '_folga', '_face'):
                            if base + sufixo in chapa:
                                del chapa[base + sufixo]
            _ocupado[0] = True
            try:
                obj.chapa_auto = False
                del obj[MARCA_CHAPA]
            finally:
                _ocupado[0] = False
            return {'FINISHED'}
        # Sem ler as dimensoes atuais, `gerar_malha_chapa` reconstruia a
        # malha com os padroes (600x400x18) e o objeto perdia o tamanho
        # que tinha. As medidas vem da caixa em MUNDO: X=largura,
        # Y=comprimento, Z=espessura, a convencao da chapa.
        d = obj.dimensions
        largura = max(1.0, d.x * 1000.0)
        comprimento = max(1.0, d.y * 1000.0)
        espessura = min(ESPESSURAS_PERMITIDAS,
                        key=lambda v: abs(v - d.z * 1000.0))
        obj[MARCA_CHAPA] = 1
        _ocupado[0] = True
        try:
            obj.chapa_auto = True
            obj.chapa_largura_mm = largura
            obj.chapa_comprimento_mm = comprimento
            obj.chapa_espessura_mm = espessura
        finally:
            _ocupado[0] = False
        gerar_malha_chapa(obj)
        self.report({'INFO'}, "Chapa %.0f x %.0f x %.0f mm"
                    % (largura, comprimento, espessura))
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


# ========================================== PRATELEIRA DE ASSETS
# O arrastar-e-soltar de verdade -- o MESMO do Asset Browser do Blender
# -- so' existe em editores nativos. `UILayout` nao expoe nada que
# inicie um arraste, e o `template_asset_view`, que os paineis usavam
# para isso, foi removido (nao existe mais no 5.x, junto com
# `bpy.types.AssetHandle`). Ou seja: a grade da sidebar nao tem como
# iniciar um arraste, por construcao da API.
#
# A AssetShelf, porem, E' registravel em Python e fica dentro da propria
# viewport. O arraste nativo vem LIGADO de fabrica: os pinceis do
# Blender e' que pedem 'NO_ASSET_DRAG' para desliga-lo. Nao pedindo
# nada, o item e' arrastavel e o solte cai no dropbox nativo da
# viewport, identico ao do Asset Browser.


class VIEW3D_AST_cabinet_creator(bpy.types.AssetShelf):
    """Prateleira com os presets: arraste o modulo direto para a cena."""
    bl_idname = "VIEW3D_AST_cabinet_creator"
    bl_space_type = 'VIEW_3D'
    bl_options = {'STORE_ENABLED_CATALOGS_IN_PREFERENCES'}
    bl_default_preview_size = 96
    # allowlist: so' o que faz sentido soltar na cena
    filter_object = True
    filter_group = True

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and not _eh_area_gaveta(context)

    @classmethod
    def asset_poll(cls, asset):
        return asset.id_type in {'OBJECT', 'COLLECTION'}


class OBJECT_OT_prateleira(Operator):
    """Mostra/esconde a prateleira de assets na viewport -- e' de la'
    que se ARRASTA o modulo para a cena"""
    bl_idname = "object.cabinet_prateleira"
    bl_label = "Prateleira de Assets"

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        registrar_bibliotecas()
        # Gravar show_region_asset_shelf direto falha com "read-only"
        # dependendo do contexto (o botao vive na sidebar, nao na
        # viewport). O operador de regiao do proprio Blender resolve
        # sempre -- e' o mesmo que o menu Ver usa.
        janela = next((r for r in context.area.regions
                       if r.type == 'WINDOW'), None)
        try:
            with context.temp_override(area=context.area, region=janela):
                bpy.ops.screen.region_toggle(region_type='ASSET_SHELF')
        except Exception as e:
            print("[Cabinet Creator] prateleira:", e)
            self.report({'WARNING'}, "Use Ver > Prateleira de Assets")
            return {'CANCELLED'}
        if getattr(context.space_data, "show_region_asset_shelf", False):
            self.report({'INFO'},
                        "Escolha a biblioteca 'Cabinet Creator' e arraste")
        return {'FINISHED'}


class CabinetCreatorPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    pasta_biblioteca: bpy.props.StringProperty(
        name="Pasta da biblioteca",
        subtype='DIR_PATH',
        description="Vazio: usa a pasta do proprio addon (a biblioteca da "
                    "empresa). Aponte para uma pasta de rede para "
                    "compartilhar entre os computadores",
        default="")

    foto_clicavel: bpy.props.BoolProperty(
        name="Foto do preset clicavel",
        description="Liga o clique na FOTO para posicionar o modulo. Em "
                    "troca a imagem pode aparecer listrada: ela e' montada "
                    "em ladrilhos e o bpy nao deixa fixar a largura deles, "
                    "entao so' fecha em certas larguras da barra lateral. "
                    "Desligado, a foto sai perfeita e o clique fica no nome",
        default=False)

    selecao_por_grupo: bpy.props.BoolProperty(
        name="Clique seleciona o modulo inteiro",
        description="Um clique acende todas as pecas do modulo; dois "
                    "cliques isolam a chapa. Desligado, o clique volta a "
                    "ser o do Blender",
        default=True)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "selecao_por_grupo")
        layout.prop(self, "foto_clicavel")
        layout.separator()
        layout.prop(self, "pasta_biblioteca")
        layout.label(text="Em uso: " + pasta_biblioteca(),
                     icon='ASSET_MANAGER')
        layout.operator("object.cabinet_registrar_bibliotecas", icon='FILE_REFRESH')
        layout.operator("object.cabinet_refiliar", icon='ASSET_MANAGER')
        layout.operator("object.cabinet_regerar_previews", icon='IMAGE_DATA')


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


# ================================================ AJUSTE A' LARGURA
# O bpy nao mede texto nem informa quanto cabe num botao: ele so' corta
# pela direita, comendo o final do rotulo. Para decidir layout e
# encurtar nomes na mao, a largura da regiao e' convertida em pixels
# logicos e o texto e' estimado por estes valores.
# Medidos por captura de tela: com 6.5/10 o rotulo "Adjacencia" ainda
# era cortado numa sidebar de 280px. Estes valores sao propositalmente
# conservadores -- errar para o lado de sobrar espaco nao corta texto.
PX_CARACTERE = 7.5
PX_FOLGA_BOTAO = 14.0
PX_ICONE = 22.0
# largura minima para um botao de categoria continuar legivel
PX_MIN_NIVEL = 64.0


def _largura_painel(context):
    """Largura da regiao em pixels logicos (descontada a escala da UI)."""
    regiao = getattr(context, "region", None)
    try:
        escala = context.preferences.system.ui_scale or 1.0
    except Exception:
        escala = 1.0
    if regiao is None or not regiao.width:
        return 200.0
    return regiao.width / escala


def _px_botao(rotulo, com_icone=True):
    return (len(rotulo) * PX_CARACTERE + PX_FOLGA_BOTAO
            + (PX_ICONE if com_icone else 0.0))


def _abreviar(texto, limite):
    """Encurta o NOME; quem chama concatena o sufixo depois, para que a
    contagem nunca seja o pedaco cortado."""
    if limite >= len(texto):
        return texto
    return texto[:max(1, limite)]


# ===================================================== GAVETA ESQUERDA
# Area VIEW_3D independente: nao mover a regiao N do usuario. O desenho
# POST_PIXEL e os eventos abaixo nao passam pelo handler de UILayout;
# portanto a barra recebe PRESS/MOUSEMOVE/RELEASE de verdade.
_handler_gaveta = [None]
_fotos_gaveta = {}
_imagens_gaveta = set()
_edicao_gaveta = [None]
# Realces animados: chave -> [valor atual, alvo, instante]. A chave
# e' (ponteiro da area, nome do widget), porque agora a alca e os
# campos de medida usam o MESMO glow.
_realces = {}
# Deslize do carrossel: chave da categoria -> [indice atual, alvo,
# instante]. O indice inteiro continua sendo a verdade (clique, arraste
# e testes leem ele da screen); isto aqui e' so' a posicao INTERMEDIARIA
# por onde a fila passa, para a troca virar movimento e nao um corte.
_deslizes = {}
DURACAO_DESLIZE = 0.09
_CHAVE_GAVETA = "cabinet_gaveta_area"
_CHAVE_PENDENTE = "cabinet_gaveta_pendente"
_CHAVE_ROLAGEM = "cabinet_gaveta_rolagem"
_LARGURA_MAX_GAVETA = 564


def _area_gaveta(screen):
    ptr = int(screen.get(_CHAVE_GAVETA, 0)) if screen else 0
    return next((a for a in screen.areas
                 if a.type == 'VIEW_3D' and a.as_pointer() == ptr), None)


def _eh_area_gaveta(context):
    return (context.area is not None and context.screen is not None
            and context.area == _area_gaveta(context.screen))


def _limitar_largura_gaveta():
    # Area.width e' somente leitura. Corrigir a divisoria apos o resize,
    # nunca disputar eventos com um operador modal do usuario.
    for janela in bpy.context.window_manager.windows:
        if getattr(janela, 'modal_operators', ()):
            continue
        painel = _area_gaveta(janela.screen)
        if painel is None:
            continue
        painel.spaces.active.show_gizmo = True
        if painel.width <= _LARGURA_MAX_GAVETA:
            continue
        direita = painel.x + painel.width
        vizinho = next((a for a in janela.screen.areas
                        if a.type == 'VIEW_3D' and 0 <= a.x - direita <= 5
                        and a.y == painel.y and a.height == painel.height), None)
        if vizinho is None:
            continue
        regiao = next((r for r in painel.regions if r.type == 'WINDOW'), None)
        with bpy.context.temp_override(window=janela, area=painel, region=regiao):
            if bpy.ops.screen.area_move.poll():
                bpy.ops.screen.area_move(x=direita,
                    y=painel.y + painel.height // 2,
                    delta=_LARGURA_MAX_GAVETA - painel.width)
    return 0.3


def _configurar_gavetas():
    # A geometria da area nova so' fica disponivel no tique seguinte ao split.
    pendente = False
    for janela in bpy.context.window_manager.windows:
        screen = janela.screen
        ptr = int(screen.get(_CHAVE_PENDENTE, 0))
        if not ptr:
            continue
        principal = next((a for a in screen.areas
                          if a.as_pointer() == ptr), None)
        if principal is None:
            screen[_CHAVE_PENDENTE] = 0
            continue
        candidatas = [a for a in screen.areas
                      if a.type == 'VIEW_3D' and a != principal
                      and a.y == principal.y and a.height == principal.height
                      and a.x < principal.x]
        if not candidatas:
            pendente = True
            continue
        painel = max(candidatas, key=lambda a: a.x)
        espaco = painel.spaces.active
        espaco.show_region_ui = False
        espaco.show_region_toolbar = False
        espaco.show_region_header = False
        espaco.show_region_tool_header = False
        espaco.show_region_hud = False
        espaco.show_gizmo = True
        espaco.show_gizmo_context = False
        espaco.show_gizmo_tool = False
        espaco.show_gizmo_navigate = False
        espaco.overlay.show_overlays = False
        screen[_CHAVE_GAVETA] = str(painel.as_pointer())
        screen[_CHAVE_PENDENTE] = 0
        painel.tag_redraw()
        principal.tag_redraw()
    return 0.05 if pendente else None


def _reconectar_gavetas():
    # Ponteiros de areas nao sobrevivem a recarga de um arquivo .blend.
    for janela in bpy.context.window_manager.windows:
        screen = janela.screen
        if not screen.get(_CHAVE_GAVETA) or _area_gaveta(screen):
            continue
        candidatos = [a for a in screen.areas
                      if a.type == 'VIEW_3D' and a.width < 600
                      and not a.spaces.active.show_region_header
                      and not a.spaces.active.show_region_toolbar
                      and not a.spaces.active.overlay.show_overlays]
        if len(candidatos) == 1:
            screen[_CHAVE_GAVETA] = str(candidatos[0].as_pointer())
            candidatos[0].tag_redraw()
        else:
            screen[_CHAVE_GAVETA] = 0
    return None


def _fechar_gavetas_registradas():
    for janela in bpy.context.window_manager.windows:
        screen = janela.screen
        painel = _area_gaveta(screen)
        screen[_CHAVE_GAVETA] = 0
        screen[_CHAVE_PENDENTE] = 0
        if painel is None:
            continue
        try:
            with bpy.context.temp_override(window=janela, screen=screen,
                                           area=painel):
                bpy.ops.screen.area_close()
        except Exception as e:
            print("[Cabinet Creator] fechar gaveta ao desativar:", e)


def _retangulo_gaveta(x, y, largura, altura, cor):
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {'pos': (
        (x, y), (x + largura, y), (x + largura, y + altura),
        (x, y), (x + largura, y + altura), (x, y + altura))})
    shader.bind()
    shader.uniform_float('color', cor)
    batch.draw(shader)


def _retangulo_arredondado_gaveta(x, y, largura, altura, raio, cor,
                                 esquerda_reta=False):
    raio = min(raio, largura / 2.0, altura / 2.0)
    pontos = []
    cantos = (
            (x + largura - raio, y + raio, -90),
            (x + largura - raio, y + altura - raio, 0),
            (x + raio, y + altura - raio, 90),
            (x + raio, y + raio, 180))
    for i, (cx, cy, inicio) in enumerate(cantos):
        if esquerda_reta and i >= 2:
            pontos.append((x, y + altura if i == 2 else y))
            continue
        for passo in range(5):
            angulo = math.radians(inicio + passo * 90 / 4)
            pontos.append((cx + raio * math.cos(angulo),
                           cy + raio * math.sin(angulo)))
    centro = (x + largura / 2.0, y + altura / 2.0)
    vertices = []
    for i, ponto in enumerate(pontos):
        vertices.extend((centro, ponto, pontos[(i + 1) % len(pontos)]))
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {'pos': vertices})
    shader.bind()
    shader.uniform_float('color', cor)
    batch.draw(shader)


def _texto_gaveta(x, y, texto, tamanho=12, cor=None):
    if cor is None:
        cor = (*bpy.context.preferences.themes[0].user_interface.wcol_regular.text, 1)
    blf.size(0, tamanho)
    blf.color(0, *cor)
    blf.position(0, x, y, 0)
    blf.draw(0, texto)


def _texto_cabivel_gaveta(x, y, texto, largura, tamanho=12):
    for fonte in range(tamanho, 8, -1):
        blf.size(0, fonte)
        if blf.dimensions(0, texto)[0] <= largura:
            _texto_gaveta(x, y, texto, fonte)
            return
    blf.size(0, 9)
    while texto and blf.dimensions(0, texto + '...')[0] > largura:
        texto = texto[:-1]
    _texto_gaveta(x, y, texto + '...' if texto else '', 9)


def _cores_gaveta():
    tema = bpy.context.preferences.themes[0]
    return tema.user_interface.wcol_regular, (*tema.properties.space.back, 1)


def _botao_gaveta(x, y, w, h, ativo=False, secao=False):
    cores, painel = _cores_gaveta()
    borda = (*cores.outline[:3], 1)
    fundo = tuple(cores.inner_sel if ativo else cores.inner) if not secao else painel
    _retangulo_arredondado_gaveta(x, y, w, h, 4, borda)
    if w > 2 and h > 2:
        _retangulo_arredondado_gaveta(
            x + 1, y + 1, w - 2, h - 2, 3, fundo)


def _folhas_para_wireframe(obj):
    """Quantas folhas o preview deve mostrar para esta selecao.

    Etapa 3 da especificacao: o esquema da porta aparece no wireframe
    tanto quando o modulo esta' selecionado quanto quando a propria
    porta esta'.
    """
    grupo = _grupo_portas(obj)
    if grupo is not None:
        return len(_folhas_portas(grupo))
    if obj is not None and MARCA_CONJUNTO in obj:
        return sum(len(_folhas_portas(g)) for g in _portas_do_conjunto(obj))
    modulo = _modulo_da_chapa(obj)
    if modulo is not None:
        return sum(len(_folhas_portas(g)) for g in _portas_do_conjunto(modulo))
    return 0


def _medidas_gaveta(context):
    obj = context.object
    if obj is not None and MARCA_CONJUNTO in obj:
        campos = [('Largura', obj.conj_largura_mm, 'ui_conj_largura'),
                  ('Altura', obj.conj_altura_mm, 'ui_conj_altura'),
                  ('Profundidade', obj.conj_profundidade_mm,
                   'ui_conj_profundidade'),
                  ('Espessura', obj.conj_espessura_mm,
                   'ui_conj_espessura')]
        return 'GRUPO', campos, 'objeto'
    if obj is not None and MARCA_CHAPA in obj:
        if obj.chapa_modo == 'GRUPO':
            s = context.scene
            campos = [('Largura', s.grupo_largura_mm, 'ui_grupo_largura'),
                      ('Altura', s.grupo_altura_mm, 'ui_grupo_altura'),
                      ('Profundidade', s.grupo_profundidade_mm,
                       'ui_grupo_profundidade'),
                      ('Espessura', s.grupo_espessura_mm,
                       'ui_grupo_espessura')]
            return 'GRUPO', campos, 'cena'
        campos = [('Largura', obj.chapa_largura_mm, 'ui_chapa_largura'),
                  ('Altura', obj.chapa_comprimento_mm,
                   'ui_chapa_comprimento'),
                  ('Espessura', obj.chapa_espessura_mm,
                   'ui_chapa_espessura')]
        return 'INDIVIDUAL', campos, 'objeto'
    medido = medir_selecao(context)
    if medido:
        editavel = obj is not None and medido[3] == 1
        if editavel:
            valores = (obj.dimensions.x * 1000.0,
                       obj.dimensions.z * 1000.0,
                       obj.dimensions.y * 1000.0)
        else:
            valores = medido[:3]
        return 'LIVRE', [
            ('Largura', valores[0], 'dimensions_0' if editavel else ''),
            ('Altura', valores[1], 'dimensions_2' if editavel else ''),
            ('Profundidade', valores[2], 'dimensions_1' if editavel else '')
        ], 'livre' if editavel else ''
    return 'LIVRE', [], ''


def _linha_cascata_gaveta(itens, x, y, largura, valores, nivel, selecionado,
                         indice, pai=None):
    if not valores:
        return y
    chave = 'cabinet_carrossel_%d_%s' % (nivel, str(pai))
    colunas = min(len(valores), max(1, int((largura - 48) // 110)))
    limite = len(valores) - colunas
    inicio = max(0, min(limite, int(bpy.context.screen.get(chave, 0))))
    bw = (largura - 48 - 4 * (colunas - 1)) / colunas
    itens.append((x, y, 20, 25, '', ('rolar_nivel', chave, -1, limite)))
    itens.append((x + largura - 20, y, 20, 25, '',
                  ('rolar_nivel', chave, 1, limite)))

    # As posicoes saem daqui, nao do desenho: assim o retangulo de
    # clique acompanha a peca enquanto ela anda. Desenhar por cima de
    # um hit-test parado faria o usuario errar o alvo em movimento.
    deslize = _deslizar(chave, inicio)
    primeiro = int(math.floor(deslize))
    sobra = deslize - primeiro
    # Em movimento entra UMA peca a mais, a que esta' surgindo na
    # borda; o recorte do desenho corta o que passa do trilho.
    extra = 1 if sobra else 0
    ordenados = sorted(valores, key=str.casefold)
    for posicao in range(primeiro, primeiro + colunas + extra):
        if not 0 <= posicao < len(ordenados):
            continue
        valor = ordenados[posicao]
        if nivel == 1:
            conta = _conta(indice, valor)
        elif nivel == 2:
            conta = _conta(indice, pai, valor)
        else:
            conta = _conta(indice, pai[0], pai[1], valor)
        itens.append((x + 24 + (posicao - primeiro - sobra) * (bw + 4), y,
                      bw, 25, '%s (%d)' % (_abreviar(valor, 13), conta),
                      ('navegar', nivel, valor, chave, limite, selecionado == valor)))
    return y - 39


def _linha_escolha_gaveta(itens, x, y, w, rotulo, prop, opcoes, atual,
                          ativo=True):
    """Rotulo mais uma fila de segmentos: a alternativa ao dropdown.

    O bpy nao desenha menu suspenso aqui, e popup e' justamente o que
    esta' saindo da frente do usuario. Segmento tem a vantagem de
    mostrar TODAS as opcoes sem clique nenhum.
    """
    if rotulo:
        # 23 deixava o primeiro segmento 2 px por cima do rotulo
        itens.append((x, y, w, 20, rotulo, None))
        y -= 26
    # 52 px e' o menor segmento onde um rotulo curto ainda cabe
    por_linha = max(1, min(len(opcoes), int(w // 52)))
    for inicio in range(0, len(opcoes), por_linha):
        fatia = opcoes[inicio:inicio + por_linha]
        bw = (w - 4 * (len(fatia) - 1)) / len(fatia)
        for i, (valor, texto) in enumerate(fatia):
            itens.append((x + i * (bw + 4), y, bw, 25, texto,
                          ('escolha', prop, valor, valor == atual, ativo)))
        y -= 29
    return y


def _rodape_medidas_gaveta(itens, x, y, w, obj, modo):
    controles = []
    if obj is not None and obj.type == 'MESH':
        controles.append(('Chapa', ('chapa', MARCA_CHAPA in obj), 74))
        if MARCA_CHAPA in obj and modo == 'INDIVIDUAL':
            controles.append(('Auto-regenerar', ('auto', obj.chapa_auto), 132))
    cursor = x
    total = sum(c[2] for c in controles) + max(0, len(controles) - 1) * 6
    fator = min(1, w / max(1, total))
    for rotulo, acao, tamanho in controles:
        bw = tamanho * fator
        itens.append((cursor, y, bw, 26, rotulo, acao))
        cursor += bw + 6 * fator
    restante = x + w - cursor
    if restante < 65:
        cursor, restante = x, w
        y -= 29
    nome = obj.name if obj else 'Nenhuma selecao'
    itens.append((cursor, y, restante, 26, nome, ('nome_objeto',)))
    return y - 35


def _aba_portas_gaveta(context, itens, x, y, w, s):
    """Tudo o que morava no popup de Portas Parametricas.

    O popup saiu da frente: aqui as opcoes ficam visiveis o tempo todo
    e o operador e' chamado com os parametros ja' prontos.
    """
    grupo = _grupo_portas(context.object)
    if grupo is not None:
        itens.append((x, y, w, 26, 'Vao: %.1f x %.1f mm' % (
            grupo['porta_vao_largura_mm'],
            grupo['porta_vao_altura_mm']), None))
        y -= 30
        itens.append((x, y, w, 26,
                      '%d folha(s) no grupo' % len(_folhas_portas(grupo)),
                      None))
        y -= 30
        itens.append((x, y, w, 26, 'Ler parametros do grupo',
                      ('ler_portas', grupo.name)))
        y -= 34
    else:
        itens.append((x, y, w, 26, 'Clique nos 2 cantos do vao', None))
        y -= 30

    # Eixos e frente so' fazem sentido para um vao novo; o grupo ja'
    # guarda a matriz dele.
    for prop, rotulo, opcoes in ESCOLHAS_PORTAS:
        if grupo is not None and prop != 'porta_abertura':
            continue
        y = _linha_escolha_gaveta(itens, x, y, w, rotulo, prop, opcoes,
                                  getattr(s, prop))

    limite = LIMITES_FOLHAS[s.porta_abertura]
    y = _linha_escolha_gaveta(
        itens, x, y, w, 'Folhas (ate %d)' % limite, 'porta_folhas',
        tuple((n, str(n)) for n in range(1, limite + 1)), s.porta_folhas)

    y = _linha_escolha_gaveta(
        itens, x, y, w, 'Espessura da porta (mm)', 'porta_espessura',
        tuple((str(int(e)), str(int(e))) for e in ESPESSURAS_PERMITIDAS),
        s.porta_espessura)

    correr = s.porta_abertura == 'CORRER'
    medidas = []
    if not correr:
        y = _linha_escolha_gaveta(
            itens, x, y, w, 'Dobradica / posicionamento', 'porta_dobradica',
            (('RETA', 'Reta'), ('CURVA', 'Curva'),
             ('SUPER_CURVA', 'Super curva')), s.porta_dobradica)
        if s.porta_dobradica == 'ESCOLHER':
            itens.append((x, y, w, 22, 'Escolha a dobradica', None))
            y -= 26
        elif s.porta_dobradica in {'RETA', 'CURVA'}:
            y = _linha_escolha_gaveta(
                itens, x, y, w, 'Espessura da lateral (mm)', 'porta_lateral',
                tuple((str(int(e)), str(int(e)))
                      for e in ESPESSURAS_PERMITIDAS), s.porta_lateral)
            medidas.append(('ui_porta_afastamento', 'porta_afastamento_mm',
                            'Afastamento'))
        else:
            medidas.append(('ui_porta_recuo_embutida',
                            'porta_recuo_embutida_mm', 'Recuo da embutida'))
        if s.porta_folhas > 1:
            medidas.append(('ui_porta_entre_folhas', 'porta_entre_folhas_mm',
                            'Entre folhas'))
    else:
        itens.append((x, y, w, 22, 'Embutidas, em dois planos', None))
        y -= 26
        medidas.append(('ui_porta_recuo_correr', 'porta_recuo_correr_mm',
                        'Recuo para trilhos'))
        if s.porta_folhas > 1:
            medidas.append(('ui_porta_sobreposicao', 'porta_sobreposicao_mm',
                            'Sobreposicao'))
            medidas.append(('ui_porta_entre_planos', 'porta_entre_planos_mm',
                            'Entre planos'))
    medidas.append(('ui_porta_folga', 'porta_folga_mm', 'Folga no perimetro'))

    # Duas colunas quando cabem: sao campos curtos, um por linha
    # desperdicaria a altura toda da gaveta.
    colunas = 2 if w >= 240 else 1
    largura_campo = (w - 6 * (colunas - 1)) / colunas
    # O campo de medida tem 37 px de altura e as filas acima so' deixam
    # 29 de vao: sem este respiro ele cobre a fila de segmentos.
    y -= 14
    for i, (prop_ui, prop_mm, rotulo) in enumerate(medidas):
        linha, coluna = divmod(i, colunas)
        itens.append((x + coluna * (largura_campo + 6), y - linha * 43,
                      largura_campo, 37,
                      '%s: %.1f mm' % (rotulo, getattr(s, prop_mm)),
                      ('medida', 'cena', prop_ui, rotulo,
                       getattr(s, prop_mm))))
    y -= math.ceil(len(medidas) / colunas) * 43 + 4

    # Previa do resultado, com o vao do grupo quando existe
    if grupo is not None:
        try:
            folhas = _calcular_folhas_portas(
                grupo['porta_vao_largura_mm'], grupo['porta_vao_altura_mm'],
                _parametros_portas_da_cena(s, numerico=True))
            itens.append((x, y, w, 22, 'Cada folha: %.1f x %.1f x %.0f mm'
                          % folhas[0][:3], None))
        except (ValueError, KeyError, TypeError) as erro:
            itens.append((x, y, w, 22, str(erro), None))
        y -= 26

    motivo = _motivo_portas(s)
    if _apanhando_vao[0]:
        rotulo = 'Marcando o vao... (Esc cancela)'
    elif motivo:
        rotulo = motivo
    else:
        rotulo = 'Configurar Portas' if grupo else 'Criar Portas'
    itens.append((x, y, w, 31, rotulo,
                  ('portas', bool(grupo), _apanhando_vao[0], motivo)))
    return itens


def _limite_rolagem_gaveta(context, largura, altura):
    widgets = _widgets_gaveta(context, largura, altura, _rolagem=0)
    return max(0, int(18 - min((v[1] for v in widgets[2:]), default=18)))


def _widgets_gaveta(context, largura, altura, _rolagem=None):
    """Retangulos (x,y,w,h,rotulo,acao) compartilhados por desenho e hit-test."""
    if _rolagem is None:
        limite = _limite_rolagem_gaveta(context, largura, altura)
        _rolagem = max(0, min(limite, int(context.screen.get(_CHAVE_ROLAGEM, 0))))
    s = context.scene
    # Mesmo se a area for alargada drasticamente, o menu permanece uma
    # coluna vertical legivel; miniaturas nao viram faixas gigantes.
    x, w = 12, max(24, min(540, largura - 24))
    itens = []
    metade = (w - 6) / 2
    for i, (rotulo, acao) in enumerate((('Modulos', 'MODULOS'),
                                       ('Portas', 'PORTAS'))):
        itens.append((x + i * (metade + 6), altura - 40, metade, 29,
                      rotulo, ('aba', acao)))
    y = altura - 105 + _rolagem
    if s.cabinet_aba == 'PORTAS':
        return _aba_portas_gaveta(context, itens, x, y, w, s)
    obj = context.object
    y += 23
    modo, campos, dono = _medidas_gaveta(context)
    if obj is not None and (MARCA_CHAPA in obj or MARCA_CONJUNTO in obj):
        for i, nome in enumerate(('Individual', 'Grupo')):
            itens.append((x + i * (metade + 6), y, metade, 25, nome,
                          ('modo', nome.upper(), modo == nome.upper())))
        y -= 33
    if campos:
        # Campos tem 37 px de altura; afastar das abas de modo acima.
        y -= 8
        escala_ui = max(1.0, context.preferences.system.ui_scale)
        largura_logica = largura / escala_ui
        colunas = (len(campos) if largura_logica >= 480 else
                   2 if largura_logica >= 240 else 1)
        largura_campo = (w - 6 * (colunas - 1)) / colunas
        for i, (nome, valor, prop) in enumerate(campos):
            linha, coluna = divmod(i, colunas)
            itens.append((x + coluna * (largura_campo + 6),
                          y - linha * 43, largura_campo, 37,
                          '%s: %.1f mm' % (nome, valor),
                          ('medida', dono, prop, nome, valor)))
        valores = [v for _, v, _ in campos]
        if modo == 'INDIVIDUAL':
            dimensoes = (valores[0], valores[2], valores[1])
        else:
            dimensoes = tuple(valores[:3])
        y -= (math.ceil(len(campos) / colunas) - 1) * 43 + 50
        lado_wireframe = min(160, max(40, w - 28))
        itens.append((x + (w - lado_wireframe) / 2,
                      y - lado_wireframe, lado_wireframe, lado_wireframe,
                      '', ('wireframe', modo, *dimensoes,
                           _folhas_para_wireframe(obj))))
        y -= lado_wireframe + 17
        if obj is not None and MARCA_CONJUNTO in obj:
            itens.append((x, y, w, 27, 'Sincronizar conjunto',
                          ('operador', 'object.cabinet_sincronizar')))
            y -= 33
        elif obj is not None and MARCA_CHAPA in obj:
            if modo != 'INDIVIDUAL':
                itens.append((x, y, w, 27, 'Sincronizar grupo',
                              ('operador', 'object.cabinet_sincronizar_grupo')))
                y -= 33
    y = _rodape_medidas_gaveta(itens, x, y, w, obj, modo)
    itens.append((x, y, w, 23, 'Montagem', None))
    y -= 31
    colunas = min(3, max(1, int(w // 36)))
    bw = (w - 6 * (colunas - 1)) / colunas
    for i, (rotulo, op) in enumerate((('Agrupar', 'object.cabinet_agrupar'),
                       ('Adjacencia', 'object.cabinet_detectar_adjacencia'),
                       ('Recalcular', 'object.cabinet_normalizar'))):
        linha, coluna = divmod(i, colunas)
        itens.append((x + coluna * (bw + 6), y - linha * 34,
                      bw, 28, rotulo, ('operador', op)))
    y -= math.ceil(3 / colunas) * 34
    y -= 10
    indice = indice_completo()
    bw = min(28, max(12, (w - 44) / 3))
    reserva = 3 * (bw + 4)
    itens.append((x, y, max(1, w - reserva), 26, 'Biblioteca (%d)' % len(indice),
                  ('biblioteca',)))
    for i, (rotulo, op) in enumerate((('Pasta', 'object.cabinet_abrir_biblioteca'),
                                     ('Assets', 'object.cabinet_prateleira'),
                                     ('Salvar +', 'object.cabinet_salvar_biblioteca'))):
        itens.append((x + w - reserva + 4 + i * (bw + 4), y, bw, 26, rotulo,
                      ('operador', op)))
    y -= 34
    if not s.chapa_bib_aberta:
        return itens
    y = _linha_cascata_gaveta(itens, x, y, w,
                              list(ARVORE.keys()), 1, s.chapa_n1, indice)
    if s.chapa_n1:
        itens.append((x, y + 31.5, w, 1, '', ('separador',)))
        y = _linha_cascata_gaveta(itens, x, y, w, _filhos_n2(s.chapa_n1),
                                  2, s.chapa_n2, indice, s.chapa_n1)
    if s.chapa_n1 and s.chapa_n2:
        filhos = _filhos_n3(s.chapa_n1, s.chapa_n2)
        if filhos:
            itens.append((x, y + 31.5, w, 1, '', ('separador',)))
        y = _linha_cascata_gaveta(itens, x, y, w, filhos,
                                  3, s.chapa_n3, indice,
                                  (s.chapa_n1, s.chapa_n2))
        if not filhos or s.chapa_n3:
            itens.append((x, y, min(w, 290), 26, 'Tamanho das miniaturas',
                          ('slider', None)))
            y -= 12
            daqui = [it for it in indice
                     if _niveis_de(it)[:2] == (s.chapa_n1, s.chapa_n2)
                     and (not filhos or _niveis_de(it)[2] == s.chapa_n3)]
            daqui.sort(key=lambda it: it.get('nome', '').casefold())
            # A foto nunca herda a largura da gaveta: e' sempre quadrada.
            lado_foto = 88 + (s.chapa_tam_bloco - 2) * 14
            bw = min(w, lado_foto + 10)
            colunas = max(1, int((w + 8) // (bw + 8)))
            altura_bloco = bw + 17
            for i, it in enumerate(daqui):
                linha, coluna = divmod(i, colunas)
                bx = x + coluna * (bw + 8)
                by = y - altura_bloco - linha * (altura_bloco + 30)
                itens.append((bx, by, bw, altura_bloco,
                              _abreviar(it.get('nome', ''), 17), ('preset', it)))
                acao = ('item', it)
                for j, rotulo in enumerate(('Ins.', 'Edit.', 'Trava')):
                    sw = (bw - 8) / 3
                    itens.append((bx + j * (sw + 4), by - 24,
                                  sw, 21, rotulo, (*acao, j)))
    return itens


def _desenhar_wireframe_gaveta(x, y, modo, largura, altura, profundidade,
                               folhas=0, escala=1.0):
    caixas = _caixas_das_folhas(largura, altura, profundidade, folhas)
    extras = [v for caixa in caixas for v in caixa]
    pontos = _pontos_wireframe(largura, altura, profundidade, extras)
    if not pontos:
        return
    pontos = [(px * escala, py * escala) for px, py in pontos]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    segmentos = []
    bases = [0] + [8 + i * 8 for i in range(len(caixas))]
    for base in bases:
        for a, b in _ARESTAS_WIREFRAME:
            segmentos.extend(
                ((x + pontos[base + a][0], y + pontos[base + a][1]),
                 (x + pontos[base + b][0], y + pontos[base + b][1])))
    shader.bind()
    shader.uniform_float('color', (0.92, 0.93, 0.95, 1))
    batch_for_shader(shader, 'LINES', {'pos': segmentos}).draw(shader)
    def rotulo(letra, ponto, dx=0, dy=0):
        _texto_gaveta(x + ponto[0] + dx, y + ponto[1] + dy,
                       letra, 14, (0.95, 0.95, 0.97, 1))
    rotulo('L', _meio_wireframe(pontos[6], pontos[7]), 0, 11)
    if modo == 'INDIVIDUAL':
        rotulo('E', _meio_wireframe(pontos[2], pontos[6]), -13)
        rotulo('A', _meio_wireframe(pontos[0], pontos[2]), -12, -8)
    else:
        rotulo('A', _meio_wireframe(pontos[2], pontos[6]), -13)
        rotulo('P', _meio_wireframe(pontos[0], pontos[2]), -12, -8)
        if modo == 'GRUPO':
            rotulo('E', pontos[1], 4, -13)


def _desenhar_foto_gaveta(it, x, y, w, h):
    png = it.get('foto') or os.path.splitext(it['arquivo'])[0] + '.png'
    caminho = os.path.join(it['pasta'], png)
    if not os.path.isfile(caminho):
        _texto_gaveta(x + 8, y + h / 2, 'Sem foto', 11)
        return
    try:
        entrada = _fotos_gaveta.get(caminho)
        stamp = os.path.getmtime(caminho)
        if entrada is None or entrada[0] != stamp:
            import numpy as np
            imagem = bpy.data.images.load(caminho, check_existing=False)
            try:
                largura, altura = imagem.size
                pixels = np.empty(largura * altura * 4, dtype=np.float32)
                imagem.pixels.foreach_get(pixels)
                alfa = pixels.reshape((altura, largura, 4))[:, :, 3]
                ys, xs = np.nonzero(alfa > (1.0 / 255.0))
                limites = ((int(xs.min()), int(ys.min()),
                            int(xs.max()) + 1, int(ys.max()) + 1)
                           if len(xs) else (0, 0, largura, altura))
                # PNG RGBA: preservar o alpha, sem achatar contra uma cor.
                dados = gpu.types.Buffer('FLOAT', largura * altura * 4,
                                          pixels)
                textura = gpu.types.GPUTexture(
                    (largura, altura), format='RGBA32F', data=dados)
                entrada = (stamp, textura, limites, largura, altura)
            finally:
                bpy.data.images.remove(imagem)
            _fotos_gaveta[caminho] = entrada
        _, textura, (x0, y0, x1, y1), iw, ih = entrada
        escala = min(w / (x1 - x0), h / (y1 - y0)) * 0.90
        dw, dh = (x1 - x0) * escala, (y1 - y0) * escala
        x, y = x + (w - dw) / 2, y + (h - dh) / 2
        w, h = dw, dh
        u0, v0, u1, v1 = x0 / iw, y0 / ih, x1 / iw, y1 / ih
        shader = gpu.shader.from_builtin('IMAGE')
        batch = batch_for_shader(shader, 'TRIS', {
            'pos': ((x, y), (x + w, y), (x + w, y + h),
                    (x, y), (x + w, y + h), (x, y + h)),
            'texCoord': ((u0, v0), (u1, v0), (u1, v1),
                         (u0, v0), (u1, v1), (u0, v1))})
        shader.bind()
        shader.uniform_sampler('image', textura)
        batch.draw(shader)
    except Exception as e:
        print('[Cabinet Creator] foto na gaveta:', e)
        _texto_gaveta(x + 8, y + h / 2, 'Foto indisponivel', 11)


def _trilho_miniaturas_gaveta(x, y, w, h):
    # Desenho e arraste usam os mesmos limites, sem incluir o rotulo.
    rotulo = min(145, w * 0.52)
    return x + rotulo + 8, y + h / 2, max(1, w - rotulo - 14)


def _animar_realces():
    areas = {a.as_pointer(): a for janela in bpy.context.window_manager.windows
             for a in janela.screen.areas if a.type == 'VIEW_3D'}
    agora = time.monotonic()
    animando = False
    for chave, estado in list(_realces.items()):
        if chave[0] not in areas:
            del _realces[chave]
            continue
        valor, alvo, instante = estado
        passo = max(0, agora - instante) / 0.16
        estado[0] += math.copysign(min(abs(alvo - valor), passo), alvo - valor)
        estado[2] = agora
        if estado[0] != valor:
            areas[chave[0]].tag_redraw()
        animando |= abs(estado[0] - alvo) > 0.0001

    # O deslize usa decaimento exponencial, nao passo fixo: assim
    # pular seis categorias de uma vez leva o mesmo tempo que pular
    # uma, desacelerando no fim como uma roleta.
    gavetas = [a for a in areas.values() if _eh_area_gaveta_bruto(a)]
    for chave, estado in list(_deslizes.items()):
        valor, alvo, instante = estado
        fatia = min(1.0, max(0.0, agora - instante) / DURACAO_DESLIZE)
        estado[0] = valor + (alvo - valor) * fatia
        estado[2] = agora
        if abs(estado[0] - alvo) < 0.002:
            estado[0] = alvo
        if estado[0] != valor:
            for area in gavetas:
                area.tag_redraw()
        animando |= estado[0] != alvo
    return 1.0 / 60 if animando else None


def _eh_area_gaveta_bruto(area):
    """Versao de `_eh_area_gaveta` que aceita a area solta."""
    for janela in bpy.context.window_manager.windows:
        if area in janela.screen.areas.values():
            return area == _area_gaveta(janela.screen)
    return False


def _deslizar(chave, alvo):
    """Posicao ANIMADA do carrossel rumo a `alvo`.

    Na primeira vez, e quando nada esta' em curso, devolve o proprio
    alvo -- entao fora de uma transicao o layout continua identico ao
    de antes, e os testes veem posicoes inteiras.
    """
    estado = _deslizes.get(chave)
    if estado is None:
        _deslizes[chave] = [float(alvo), float(alvo), time.monotonic()]
        return float(alvo)
    if estado[1] != alvo:
        estado[1], estado[2] = float(alvo), time.monotonic()
        if not bpy.app.timers.is_registered(_animar_realces):
            bpy.app.timers.register(_animar_realces, first_interval=0.0)
    return estado[0]


def _realcar(context, nome, ativo):
    """Liga ou desliga o glow de um widget, com transicao."""
    chave = (context.area.as_pointer(), nome)
    estado = _realces.setdefault(chave, [0.0, 0.0, time.monotonic()])
    alvo = float(ativo)
    if estado[1] != alvo:
        estado[1], estado[2] = alvo, time.monotonic()
    if estado[0] != alvo and not bpy.app.timers.is_registered(_animar_realces):
        bpy.app.timers.register(_animar_realces, first_interval=0.0)


def _valor_realce(context, nome):
    area = getattr(context, 'area', None)
    if area is None:
        return 0.0
    return _realces.get((area.as_pointer(), nome), (0.0,))[0]


def _glow_gaveta(x, y, w, h, raio, realce, cor, esquerda_reta=False):
    """Halo do widget aceso. Um so' lugar, para alca e botoes acenderem
    identicos.

    Liga o ALPHA por conta propria: `blf.draw` mexe no estado de blend
    e, sem isto, o halo do segundo widget em diante saia OPACO -- um
    bloco branco cobrindo o texto do botao.
    """
    if realce <= 0.0:
        return
    gpu.state.blend_set('ALPHA')
    for margem, alfa in ((6, 0.025), (4, 0.045), (2, 0.07)):
        _retangulo_arredondado_gaveta(
            x - margem, y - margem, w + 2 * margem, h + 2 * margem,
            raio + margem, (*cor, alfa * realce),
            esquerda_reta=esquerda_reta)


# ============================================= GRID DE MEDIDAS NA CENA
# Passar o mouse num campo de medida (ou abri-lo para edicao) desenha a
# caixa envolvente do alvo na viewport e ACENDE as quatro arestas do
# eixo daquele campo. Assim da' para ver o que vai mudar antes de
# mudar, em vez de descobrir por tentativa e erro.

# Qual eixo cada rotulo move, por modo de medida. INDIVIDUAL usa os
# eixos LOCAIS da chapa (X=largura, Y=comprimento, Z=espessura), porque
# a chapa pode estar girada e a Espessura continua sendo a aresta local
# Z. Os outros modos usam eixos de MUNDO na convencao do add-on
# (Largura=X, Altura=Z, Profundidade=Y). Espessura de modulo nao e'
# aresta da caixa: nao acende nada, de proposito.
EIXOS_MEDIDA = {
    'INDIVIDUAL': {'Largura': 0, 'Altura': 1, 'Espessura': 2},
    'GRUPO': {'Largura': 0, 'Altura': 2, 'Profundidade': 1},
    'LIVRE': {'Largura': 0, 'Altura': 2, 'Profundidade': 1},
}

# Cantos indexados por bits: i + 2*j + 4*k ao longo de u, v, w. Com
# essa ordem as quatro arestas de um eixo saem de uma conta simples,
# sem tabela escrita a mao.
ARESTAS_EIXO = (
    ((0, 1), (2, 3), (4, 5), (6, 7)),
    ((0, 2), (1, 3), (4, 6), (5, 7)),
    ((0, 4), (1, 5), (2, 6), (3, 7)),
)

_handler_grid = [None]
_realce_medida = [None]      # rotulo do campo aceso, ou None
_campos_gaveta = {}          # ponteiro do gizmo -> retangulo do campo


def _chave_widget(acao):
    """Identidade estavel do widget, usada para guardar o realce dele.

    Devolve None para o que NAO e' botao (decoracao, rotulo, trilho do
    slider): essas coisas nao acendem.
    """
    if not acao:
        return None
    verbo = acao[0]
    if verbo in {'wireframe', 'separador', 'nome_objeto', 'slider'}:
        return None
    if verbo == 'medida':
        return 'medida:' + acao[3]
    if verbo in {'aba', 'modo'}:
        return '%s:%s' % (verbo, acao[1])
    if verbo == 'escolha':
        return 'esc:%s:%s' % (acao[1], acao[2])
    if verbo == 'operador':
        return 'op:' + acao[1]
    if verbo == 'navegar':
        return 'nav:%s:%s' % (acao[1], acao[2])
    if verbo == 'rolar_nivel':
        return 'rol:%s:%s' % (acao[1], acao[2])
    if verbo == 'preset':
        return 'preset:%s' % acao[1]['arquivo']
    if verbo == 'item':
        return 'item:%s:%s' % (acao[1]['arquivo'], acao[2])
    return verbo


def _cantos_caixa(origem, u, v, w):
    return [origem + u * i + v * j + w * k
            for k in (0, 1) for j in (0, 1) for i in (0, 1)]


def _alvos_da_medida(context, modo):
    """Objetos que a medida daquele modo governa."""
    obj = context.object
    if modo == 'GRUPO' and obj is not None:
        familia = [o for o in familia_de(obj) if o.type in TIPOS_COM_VOLUME]
        if familia:
            return familia
    return list(context.selected_objects)


def _caixa_da_medida(context, modo):
    """Os 8 cantos, em mundo, da caixa que o campo edita."""
    obj = context.object
    if modo == 'INDIVIDUAL' and obj is not None:
        # Caixa ORIENTADA pela chapa: girada, a espessura dela nao e'
        # o eixo vertical do mundo, e uma caixa alinhada ao mundo
        # acenderia a aresta errada.
        mw = obj.matrix_world
        try:
            locais = [Vector(c) for c in obj.bound_box]
        except Exception:
            return None
        if not locais:
            return None
        lo = [min(c[a] for c in locais) for a in range(3)]
        hi = [max(c[a] for c in locais) for a in range(3)]
        origem = mw @ Vector(lo)
        eixos = []
        for a in range(3):
            canto = list(lo)
            canto[a] = hi[a]
            eixos.append((mw @ Vector(canto)) - origem)
        return _cantos_caixa(origem, *eixos)

    limites = _limites_mundo(context, _alvos_da_medida(context, modo))
    if limites is None:
        return None
    lo, hi, _n = limites
    origem = Vector(lo)
    return _cantos_caixa(origem,
                         Vector((hi[0] - lo[0], 0.0, 0.0)),
                         Vector((0.0, hi[1] - lo[1], 0.0)),
                         Vector((0.0, 0.0, hi[2] - lo[2])))


def _definir_realce_medida(rotulo):
    """Guarda o campo aceso e manda a viewport se redesenhar.

    O glow mora na gaveta, mas a caixa aparece na area VIZINHA: sem
    este tag_redraw ela so' apareceria quando algo mais pedisse
    redesenho, e o realce pareceria intermitente.
    """
    if _realce_medida[0] == rotulo:
        return
    _realce_medida[0] = rotulo
    for janela in bpy.context.window_manager.windows:
        for area in janela.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _desenhar_grid_medidas():
    context = bpy.context
    area = getattr(context, 'area', None)
    if (area is None or area.type != 'VIEW_3D' or _eh_area_gaveta(context)
            or _realce_medida[0] is None):
        return
    try:
        modo, _campos, _dono = _medidas_gaveta(context)
        cantos = _caixa_da_medida(context, modo)
    except Exception as e:
        print("[Cabinet Creator] caixa de medidas:", e)
        return
    if not cantos:
        return
    eixo = EIXOS_MEDIDA.get(modo, {}).get(_realce_medida[0])

    caixa, aceso = [], []
    for a in range(3):
        destino = aceso if a == eixo else caixa
        for i, j in ARESTAS_EIXO[a]:
            destino.extend((cantos[i], cantos[j]))

    tema = context.preferences.themes[0]
    cor_caixa = (*tema.user_interface.wcol_regular.text, 0.55)
    cor_aceso = (*tema.view_3d.object_active, 1.0)
    try:
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind()
        gpu.state.line_width_set(1.5)
        shader.uniform_float('color', cor_caixa)
        batch_for_shader(shader, 'LINES', {'pos': caixa}).draw(shader)
        if aceso:
            gpu.state.line_width_set(3.0)
            shader.uniform_float('color', cor_aceso)
            batch_for_shader(shader, 'LINES', {'pos': aceso}).draw(shader)
    except Exception as e:
        print("[Cabinet Creator] grid de medidas:", e)
    finally:
        try:
            gpu.state.line_width_set(1.0)
            gpu.state.blend_set('NONE')
        except Exception:
            pass


class VIEW3D_GT_campo_gaveta(Gizmo):
    """Hit-test invisivel sobre o retangulo de UM widget da gaveta.

    Existe so' para ganhar `is_highlight`: o desenho da gaveta e' GPU e
    nao recebe evento de mouse, e um operador modal persistente roubaria
    evento de outros add-ons. O clique cai no mesmo operador que a
    keymap ja' dispara para a area inteira, entao nada muda ao clicar.

    Quando o widget tem icone, o disco do `GIZMO_GT_button_2d` fica de
    FORA deste hit-test: assim o gizmo do icone continua ganhando o
    pick ali e o tooltip dele nao se perde. O glow cobre os dois casos
    porque soma os dois `is_highlight`.
    """
    bl_idname = 'VIEW3D_GT_campo_gaveta'

    def draw(self, context):
        pass

    def test_select(self, context, location):
        alvo = _campos_gaveta.get(self.as_pointer())
        if not alvo:
            return -1
        x, y, w, h, icone = alvo
        px, py = location
        if not (x <= px <= x + w and y <= py <= y + h):
            return -1
        if icone is not None:
            cx, cy, raio = icone
            if (px - cx) ** 2 + (py - cy) ** 2 <= raio * raio:
                return -1
        return 0


def _desenhar_gaveta(tela=False):
    context = bpy.context
    if context.region is None or context.region.type != 'WINDOW':
        return
    if not _eh_area_gaveta(context):
        if (context.area is not None and context.area.type == 'VIEW_3D'
                and (_area_gaveta(context.screen) is None
                     or context.area.x > _area_gaveta(context.screen).x)):
            centro = max(48, context.region.height * 0.12)
            realce = _valor_realce(context, 'alca')
            cores, _ = _cores_gaveta()
            gpu.state.blend_set('ALPHA')
            # o glow cresce so' para a direita: a alca encosta na borda
            _glow_gaveta(0, centro - 35, 26, 70, 5, realce, cores.text,
                         esquerda_reta=True)
            _retangulo_arredondado_gaveta(
                0, centro - 35, 26, 70, 5,
                (*(c + (t - c) * realce * 0.45
                   for c, t in zip(cores.outline[:3], cores.text)), 1),
                esquerda_reta=True)
            _retangulo_arredondado_gaveta(
                0, centro - 34, 25, 68, 4,
                (*(c + (t - c) * realce * 0.22
                   for c, t in zip(cores.inner[:3], cores.text)), 1),
                esquerda_reta=True)
            aberta = _area_gaveta(context.screen) is not None
            seta = (((9, centro), (16, centro - 7),
                     (16, centro + 7)) if aberta else
                    ((16, centro), (9, centro - 7),
                     (9, centro + 7)))
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            batch = batch_for_shader(shader, 'TRIS', {'pos': seta})
            shader.bind()
            shader.uniform_float('color', (*cores.text, 1))
            batch.draw(shader)
            gpu.state.blend_set('NONE')
        return
    # A tela da gaveta e' desenhada antes dos GIZMO_GT_button_2d.
    # POST_PIXEL cobre os icones nativos se desenhar o fundo por cima.
    if not tela:
        return
    largura, altura = context.region.width, context.region.height
    cores, fundo = _cores_gaveta()
    gpu.state.blend_set('ALPHA')
    _retangulo_gaveta(0, 0, largura, altura, fundo)
    _retangulo_gaveta(largura - 2, 0, 2, altura, (0.27, 0.27, 0.27, 1))
    widgets = _widgets_gaveta(context, largura, altura)
    # O cabecalho e' desenhado por ultimo, acima do conteudo rolavel.
    for x, y, w, h, rotulo, acao in widgets[2:] + widgets[:2]:
        if y + h < 0 or y > altura:
            continue
        if acao and acao[0] == 'separador':
            _retangulo_gaveta(x, y, w, h, (*cores.outline[:3], 1))
            continue
        if acao and acao[0] == 'wireframe':
            _desenhar_wireframe_gaveta(x, y, *acao[1:], escala=w / 160.0)
            continue
        if acao and acao[0] == 'slider':
            tx, ty, tw = _trilho_miniaturas_gaveta(x, y, w, h)
            largura_rotulo = tx - x - 12
            if largura_rotulo >= 135:
                _texto_cabivel_gaveta(x, y + 8, rotulo, largura_rotulo, 11)
            else:
                _texto_cabivel_gaveta(x, y + 15, 'Tamanho das', largura_rotulo, 11)
                _texto_cabivel_gaveta(x, y + 2, 'miniaturas', largura_rotulo, 11)
            valor = (context.scene.chapa_tam_bloco - 2) / 6.0
            _retangulo_gaveta(tx, ty - 1.5, tw, 3, tuple(cores.inner))
            _retangulo_arredondado_gaveta(
                tx + tw * valor - 6, ty - 6, 12, 12, 6, (*cores.text, 1))
            continue
        if acao and acao[0] == 'preset':
            _botao_gaveta(x, y, w, h)
            lado = min(w - 10, h - 27)
            _retangulo_gaveta(x + 5, y + 22, lado, lado, fundo)
            # BLF e outros widgets podem alterar o blend antes da foto.
            gpu.state.blend_set('ALPHA')
            _desenhar_foto_gaveta(acao[1], x + 5, y + 22, lado, lado)
            _texto_cabivel_gaveta(x + 5, y + 5, rotulo, w - 10, 11)
            continue
        # A peca que esta' entrando (ou saindo) invade a area das setas.
        # O recorte faz o carrossel parecer uma janela por onde a fila
        # passa, em vez de pecas aparecendo do nada.
        recortado = bool(acao and acao[0] == 'navegar')
        if recortado:
            gpu.state.scissor_test_set(True)
            gpu.state.scissor_set(12 + 24, int(y) - 1,
                                  max(0, largura - 24 - 48), 27)

        ativo = bool(acao and (acao[0] in {'navegar', 'modo'} and acao[-1]
                               or acao[0] == 'escolha' and acao[3]
                               or acao[0] == 'portas' and acao[2]))
        # O halo vai ANTES do corpo do botao, como na alca: por cima
        # ele lavaria o texto em vez de circundar o widget.
        chave = _chave_widget(acao)
        if chave:
            _glow_gaveta(x, y, w, h, 4, _valor_realce(context, chave),
                         cores.text)
        if not acao or acao[0] not in {'chapa', 'auto', 'nome_objeto'}:
            _botao_gaveta(x, y, w, h, ativo=ativo, secao=acao is None)
        if acao and acao[0] in {'chapa', 'auto'}:
            _texto_cabivel_gaveta(x + 25, y + 7, rotulo, w - 25, 11)
        if acao and acao[0] == 'nome_objeto':
            _texto_cabivel_gaveta(x, y + 7, rotulo, w, 11)
            continue
        if acao and acao[0] == 'medida':
            edicao = _edicao_gaveta[0]
            editando = (edicao is not None and edicao['area'] == context.area.as_pointer()
                        and edicao['propriedade'] == acao[2])
            if editando:
                _botao_gaveta(x, y, w, h, ativo=True)
            _texto_cabivel_gaveta(x + 7, y + h - 14,
                                   acao[3], w - 14, 11)
            valor = ('%.1f mm' % acao[4])
            if editando:
                texto, cursor = edicao['texto'], edicao['cursor']
                valor = texto[:cursor] + '|' + texto[cursor:]
            _texto_cabivel_gaveta(x + 7, y + 6,
                                   valor, w - 14, 12)
        elif not _icone_acao_gaveta(acao):
            _texto_cabivel_gaveta(x + 9, y + (h - 12) / 2,
                                   rotulo, w - 18)
        if recortado:
            gpu.state.scissor_test_set(False)
    _retangulo_gaveta(0, altura - 48, largura, 48,
                       fundo)
    for x, y, w, h, rotulo, acao in widgets[:2]:
        _glow_gaveta(x, y, w, h, 4,
                     _valor_realce(context, _chave_widget(acao)), cores.text)
        _botao_gaveta(x, y, w, h,
                       ativo=context.scene.cabinet_aba == acao[1])
        _texto_cabivel_gaveta(x + 9, y + 8, rotulo, w - 18)
    gpu.state.blend_set('NONE')


class OBJECT_OT_editar_medida_gaveta(Operator):
    """Edita uma medida usando a mesma propriedade parametrica do painel N."""
    bl_idname = 'object.cabinet_editar_medida_gaveta'
    bl_label = 'Editar Medida'
    bl_options = {'REGISTER', 'UNDO'}

    dono: StringProperty(options={'SKIP_SAVE'})
    objeto: StringProperty(options={'SKIP_SAVE'})
    propriedade: StringProperty(options={'SKIP_SAVE'})
    valor: FloatProperty(name='Medida', subtype='DISTANCE', unit='LENGTH',
                         min=0.001, options={'SKIP_SAVE'})

    def invoke(self, context, event):
        if _edicao_gaveta[0] is not None:
            return {'CANCELLED'}
        self._area = context.area
        texto = '%g' % (self.valor * 1000.0)
        self._estado = {'area': context.area.as_pointer(),
                        'propriedade': self.propriedade, 'texto': texto,
                        'cursor': len(texto), 'selecionado': True}
        _edicao_gaveta[0] = self._estado
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _encerrar(self):
        _edicao_gaveta[0] = None
        self._area.tag_redraw()

    def cancel(self, context):
        self._encerrar()

    def modal(self, context, event):
        if _edicao_gaveta[0] is not self._estado:
            return {'CANCELLED'}
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self._encerrar()
            return {'CANCELLED'}
        if event.type in {'RET', 'NUMPAD_ENTER', 'LEFTMOUSE', 'TAB'}:
            try:
                texto = self._estado['texto'].strip().replace(',', '.')
                valor = bpy.utils.units.to_value(
                    'METRIC', 'LENGTH', texto, str_ref_unit='1 mm')
                if not math.isfinite(valor) or valor < 0.001:
                    raise ValueError('Informe uma medida de pelo menos 1 mm')
                self.valor = valor
            except (ValueError, TypeError) as e:
                self.report({'WARNING'}, str(e))
                return {'RUNNING_MODAL'}
            resultado = self.execute(context)
            self._encerrar()
            return resultado
        estado = self._estado
        texto, cursor = estado['texto'], estado['cursor']
        if event.ctrl and event.type == 'A':
            estado['selecionado'] = True
        elif event.type in {'LEFT_ARROW', 'RIGHT_ARROW', 'HOME', 'END'}:
            cursor = (0 if event.type == 'HOME' else len(texto) if event.type == 'END'
                      else max(0, min(len(texto), cursor + (-1 if event.type == 'LEFT_ARROW' else 1))))
            estado['selecionado'] = False
        else:
            entrada = (context.window_manager.clipboard if event.ctrl and event.type == 'V'
                       else event.unicode if not event.ctrl else '')
            if entrada or event.type in {'BACK_SPACE', 'DEL'}:
                if estado['selecionado']:
                    texto, cursor = '', 0
                if entrada:
                    entrada = ''.join(c for c in entrada if c.isprintable())[:80]
                    texto = texto[:cursor] + entrada + texto[cursor:]
                    cursor += len(entrada)
                elif event.type == 'BACK_SPACE' and cursor:
                    texto = texto[:cursor - 1] + texto[cursor:]
                    cursor -= 1
                elif event.type == 'DEL':
                    texto = texto[:cursor] + texto[cursor + 1:]
                estado['selecionado'] = False
        estado['texto'], estado['cursor'] = texto, cursor
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def execute(self, context):
        alvo = (context.scene if self.dono == 'cena'
                else bpy.data.objects.get(self.objeto))
        if alvo is None:
            self.report({'WARNING'}, 'Alvo da medida nao encontrado')
            return {'CANCELLED'}
        if self.dono == 'livre' and self.propriedade.startswith('dimensions_'):
            indice = int(self.propriedade[-1])
            dimensoes = list(alvo.dimensions)
            dimensoes[indice] = self.valor
            alvo.dimensions = dimensoes
            return {'FINISHED'}
        if not hasattr(alvo, self.propriedade):
            self.report({'WARNING'}, 'Propriedade da medida nao encontrada')
            return {'CANCELLED'}
        setattr(alvo, self.propriedade, self.valor)
        return {'FINISHED'}


class OBJECT_OT_interagir_gaveta(Operator):
    """Recebe clique e arraste diretamente na interface independente."""
    bl_idname = "object.cabinet_interagir_gaveta"
    bl_label = "Interagir com Gaveta Cabinet Creator"

    @classmethod
    def poll(cls, context):
        return _eh_area_gaveta(context)

    def invoke(self, context, event):
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            for wx, wy, w, h, _, acao in _widgets_gaveta(
                    context, context.region.width, context.region.height):
                if (acao and acao[0] in {'navegar', 'rolar_nivel'}
                        and wx <= event.mouse_region_x <= wx + w
                        and wy <= event.mouse_region_y <= wy + h):
                    chave, limite = ((acao[3], acao[4]) if acao[0] == 'navegar'
                                     else (acao[1], acao[3]))
                    passo = -1 if event.type == 'WHEELUPMOUSE' else 1
                    context.screen[chave] = max(0, min(limite,
                        int(context.screen.get(chave, 0)) + passo))
                    context.area.tag_redraw()
                    return {'FINISHED'}
            limite = _limite_rolagem_gaveta(
                context, context.region.width, context.region.height)
            atual = max(0, min(limite, int(context.screen.get(_CHAVE_ROLAGEM, 0))))
            passo = -85 if event.type == 'WHEELUPMOUSE' else 85
            context.screen[_CHAVE_ROLAGEM] = max(0, min(limite, atual + passo))
            context.area.tag_redraw()
            return {'FINISHED'}
        x, y = event.mouse_region_x, event.mouse_region_y
        for wx, wy, w, h, _rotulo, acao in _widgets_gaveta(
                context, context.region.width, context.region.height):
            if (y >= context.region.height - 48
                    and (not acao or acao[0] != 'aba')):
                continue
            dentro = wx <= x <= wx + w and wy <= y <= wy + h
            if acao and acao[0] == 'slider':
                tx, ty, tw = _trilho_miniaturas_gaveta(wx, wy, w, h)
                dentro = tx - 6 <= x <= tx + tw + 6 and abs(y - ty) <= h / 2
            if not dentro:
                continue
            if acao is None:
                return {'FINISHED'}
            if acao[0] in {'wireframe', 'separador', 'nome_objeto'}:
                return {'FINISHED'}
            if acao[0] == 'aba':
                context.scene.cabinet_aba = acao[1]
                context.screen[_CHAVE_ROLAGEM] = 0
            elif acao[0] == 'biblioteca':
                context.scene.chapa_bib_aberta = not context.scene.chapa_bib_aberta
            elif acao[0] == 'auto':
                context.object.chapa_auto = not context.object.chapa_auto
            elif acao[0] == 'chapa':
                bpy.ops.object.cabinet_marcar(alternar=True)
            elif acao[0] == 'navegar':
                self._carrossel = acao
                self._mouse_inicio = x
                self._indice_inicio = int(context.screen.get(acao[3], 0))
                self._arrastou = False
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            elif acao[0] == 'rolar_nivel':
                context.screen[acao[1]] = max(0, min(acao[3],
                    int(context.screen.get(acao[1], 0)) + acao[2]))
            elif acao[0] == 'modo':
                bpy.ops.object.cabinet_modo_medidas(modo=acao[1])
            elif acao[0] == 'medida':
                if acao[2]:
                    bpy.ops.object.cabinet_editar_medida_gaveta(
                        'INVOKE_DEFAULT', dono=acao[1],
                        objeto=context.object.name if context.object else '',
                        propriedade=acao[2], valor=acao[4] / 1000.0)
            elif acao[0] == 'escolha':
                if acao[4]:
                    setattr(context.scene, acao[1], acao[2])
            elif acao[0] == 'ler_portas':
                alvo = bpy.data.objects.get(acao[1])
                if alvo is not None:
                    _carregar_portas_na_cena(context.scene, alvo)
            elif acao[0] == 'portas':
                s = context.scene
                if acao[3]:
                    self.report({'WARNING'}, acao[3])
                elif acao[2]:
                    pass        # ja' esta' marcando o vao
                elif acao[1]:
                    grupo = _grupo_portas(context.object)
                    bpy.ops.object.cabinet_portas(
                        'EXEC_DEFAULT', editar=True, grupo_nome=grupo.name,
                        **_parametros_portas_da_cena(s))
                else:
                    bpy.ops.object.cabinet_apanhar_vao('INVOKE_DEFAULT')
            elif acao[0] == 'preset':
                it = acao[1]
                bpy.ops.object.cabinet_arrastar_preset(
                    'INVOKE_DEFAULT', pasta=it['pasta'],
                    arquivo=it['arquivo'], tipo=it.get('tipo', 'modulo'))
            elif acao[0] == 'item':
                it, indice = acao[1], acao[2]
                if indice == 0:
                    bpy.ops.object.cabinet_inserir_preset(
                        pasta=it['pasta'], arquivo=it['arquivo'],
                        tipo=it.get('tipo', 'modulo'))
                elif indice == 1:
                    if not item_bloqueado(it):
                        bpy.ops.object.cabinet_editar_modelo(
                            'INVOKE_DEFAULT', pasta=it['pasta'],
                            arquivo=it['arquivo'])
                else:
                    bpy.ops.object.cabinet_bloqueio(
                        pasta=it['pasta'], arquivo=it['arquivo'])
            elif acao[0] == 'slider':
                self._inicio, _, self._largura = _trilho_miniaturas_gaveta(
                    wx, wy, w, h)
                self._atualizar(context, x)
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            else:
                try:
                    modulo, nome = acao[1].split('.')
                    getattr(getattr(bpy.ops, modulo), nome)('INVOKE_DEFAULT')
                except Exception as e:
                    self.report({'WARNING'}, str(e))
            context.area.tag_redraw()
            return {'FINISHED'}
        return {'FINISHED'}

    def _atualizar(self, context, x):
        fracao = min(1.0, max(0.0, (x - self._inicio) / self._largura))
        context.scene.chapa_tam_bloco = 2 + round(fracao * 6)
        context.area.tag_redraw()

    def modal(self, context, event):
        if hasattr(self, '_carrossel'):
            acao = self._carrossel
            if event.type == 'MOUSEMOVE':
                delta = self._mouse_inicio - event.mouse_region_x
                if abs(delta) > 6:
                    self._arrastou = True
                context.screen[acao[3]] = max(0, min(acao[4],
                    self._indice_inicio + round(delta / 60)))
                context.area.tag_redraw()
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                if not self._arrastou:
                    bpy.ops.object.cabinet_navegar(nivel=acao[1], valor=acao[2])
                context.area.tag_redraw()
                return {'FINISHED'}
            if event.type in {'ESC', 'RIGHTMOUSE'}:
                context.screen[acao[3]] = self._indice_inicio
                context.area.tag_redraw()
                return {'CANCELLED'}
            return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE':
            self._atualizar(context, event.mouse_region_x)
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class OBJECT_OT_alternar_gaveta(Operator):
    """Abre ou fecha a area exclusiva do addon a esquerda da viewport"""
    bl_idname = "object.cabinet_alternar_gaveta"
    bl_label = "Alternar Gaveta Cabinet Creator"

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and not _eh_area_gaveta(context))

    def execute(self, context):
        screen = context.screen
        painel = _area_gaveta(screen)
        if painel is not None:
            janela = context.window
            screen[_CHAVE_GAVETA] = 0
            try:
                with context.temp_override(window=janela, screen=screen,
                                           area=painel):
                    bpy.ops.screen.area_close()
            except Exception as e:
                screen[_CHAVE_GAVETA] = str(painel.as_pointer())
                self.report({'WARNING'}, "Nao consegui fechar a gaveta: %s" % e)
                return {'CANCELLED'}
            return {'FINISHED'}
        # Corrige o estado deixado pela versao antiga da gaveta, que
        # invertia a regiao N inteira para a esquerda.
        ui = next((r for r in context.area.regions if r.type == 'UI'), None)
        if ui is not None and ui.alignment == 'LEFT':
            with context.temp_override(area=context.area, region=ui):
                bpy.ops.screen.region_flip()
        screen[_CHAVE_PENDENTE] = str(context.area.as_pointer())
        try:
            largura = context.area.width
            with context.temp_override(area=context.area):
                bpy.ops.screen.area_split(direction='VERTICAL',
                                          factor=max(0.08, min(0.35, 320 / largura)))
        except Exception as e:
            screen[_CHAVE_PENDENTE] = 0
            self.report({'WARNING'}, "Nao consegui abrir a gaveta: %s" % e)
            return {'CANCELLED'}
        if not bpy.app.timers.is_registered(_configurar_gavetas):
            bpy.app.timers.register(_configurar_gavetas, first_interval=0.05)
        return {'FINISHED'}


def _icone_acao_gaveta(acao):
    if not acao:
        return None
    if acao[0] == 'operador':
        return {'object.cabinet_agrupar': 'GROUP',
                'object.cabinet_detectar_adjacencia': 'SNAP_ON',
                'object.cabinet_normalizar': 'FILE_REFRESH',
                'object.cabinet_abrir_biblioteca': 'FILE_FOLDER',
                'object.cabinet_prateleira': 'ASSET_MANAGER',
                'object.cabinet_salvar_biblioteca': 'FILE_TICK'}.get(acao[1])
    if acao[0] == 'item':
        return ('IMPORT', 'GREASEPENCIL',
                'LOCKED' if item_bloqueado(acao[1]) else 'UNLOCKED')[acao[2]]
    if acao[0] == 'rolar_nivel':
        return 'TRIA_LEFT' if acao[2] < 0 else 'TRIA_RIGHT'
    if acao[0] in {'chapa', 'auto'}:
        return 'CHECKBOX_HLT' if acao[1] else 'CHECKBOX_DEHLT'
    return None


class VIEW3D_GT_alca_gaveta(Gizmo):
    """Hit-test da alca; o desenho unico fica no callback POST_PIXEL."""
    bl_idname = 'VIEW3D_GT_alca_gaveta'

    def draw(self, context):
        pass

    def test_select(self, context, location):
        x, y = location
        centro = max(48, context.region.height * 0.12)
        return 0 if 0 <= x <= 26 and abs(y - centro) <= 35 else -1


class VIEW3D_GGT_cabinet_gaveta(GizmoGroup):
    """Alca e icones nativos na interface independente."""
    bl_idname = "VIEW3D_GGT_cabinet_gaveta"
    bl_label = "Alca Cabinet Creator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'SCALE'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def setup(self, context):
        self.botoes = []
        self.campos = []
        alca = self.gizmos.new('VIEW3D_GT_alca_gaveta')
        alca.target_set_operator("object.cabinet_alternar_gaveta")
        alca.use_tooltip = True
        self.alca = alca

    def _preparar_hover(self, context, acesos_por_icone):
        """Um gizmo invisivel por widget clicavel, so' para ter hover.

        Vale para QUALQUER botao da gaveta, nao so' os campos de
        medida: o retangulo sob o mouse acende com o mesmo glow da
        alca. `acesos_por_icone` traz os widgets cujo gizmo de icone ja'
        esta' destacado, porque nesses o disco do icone fica fora do
        hit-test daqui (para nao roubar o tooltip dele).
        """
        # A faixa de 48 px do topo pertence ao cabecalho; so' as abas
        # sao clicaveis ali. Mesmo criterio do operador de clique.
        alvos = [v for v in _widgets_gaveta(
            context, context.region.width, context.region.height)
            if _chave_widget(v[5]) and v[1] >= 0
            and (v[5][0] == 'aba'
                 or v[1] + v[3] < context.region.height - 48)]
        while len(self.campos) < len(alvos):
            campo = self.gizmos.new('VIEW3D_GT_campo_gaveta')
            # O clique cai no mesmo operador que a keymap ja' dispara
            # para a area inteira, entao clicar continua igual.
            campo.target_set_operator('object.cabinet_interagir_gaveta')
            campo.use_tooltip = False
            self.campos.append(campo)

        escala = max(1.0, context.preferences.system.ui_scale)
        _campos_gaveta.clear()
        acesos = set(acesos_por_icone)
        for campo, (x, y, w, h, _rotulo, acao) in zip(self.campos, alvos):
            campo.hide = False
            icone = None
            if _icone_acao_gaveta(acao):
                cx = x + (10 if acao[0] in {'chapa', 'auto'} else w / 2)
                icone = (cx, y + h / 2, 13.0 * escala)
            _campos_gaveta[campo.as_pointer()] = (x, y, w, h, icone)
            if campo.is_highlight:
                acesos.add(_chave_widget(acao))

        # Edicao aberta manda mais que o mouse: com o campo em foco o
        # usuario ja' esta' digitando aquela medida, ainda que o cursor
        # tenha saido de cima dele.
        medida_ativa = next(
            (v[5][3] for v in alvos if v[5][0] == 'medida'
             and _chave_widget(v[5]) in acesos), None)
        edicao = _edicao_gaveta[0]
        if edicao is not None:
            em_foco = next((v[5][3] for v in alvos if v[5][0] == 'medida'
                            and v[5][2] == edicao['propriedade']), None)
            if em_foco is not None:
                medida_ativa = em_foco
                acesos.add('medida:' + em_foco)

        for _x, _y, _w, _h, _rotulo, acao in alvos:
            chave = _chave_widget(acao)
            _realcar(context, chave, chave in acesos)
        _definir_realce_medida(medida_ativa)

    def draw_prepare(self, context):
        gaveta = _eh_area_gaveta(context)
        self.alca.hide = gaveta
        for botao in self.botoes:
            botao.hide = True
        for campo in self.campos:
            campo.hide = True
        if gaveta:
            widgets = [v for v in _widgets_gaveta(
                context, context.region.width, context.region.height)
                if _icone_acao_gaveta(v[5]) and v[1] >= 0
                and v[1] + v[3] < context.region.height - 48]
            assinatura = tuple(_icone_acao_gaveta(v[5]) for v in widgets)
            if assinatura != getattr(self, '_assinatura', None):
                for botao in self.botoes:
                    self.gizmos.remove(botao)
                self.botoes.clear()
                for icone in assinatura:
                    botao = self.gizmos.new('GIZMO_GT_button_2d')
                    botao.draw_options = set()
                    botao.icon = icone
                    botao.show_drag = False
                    botao.use_tooltip = True
                    self.botoes.append(botao)
                self._assinatura = assinatura
            cores, _ = _cores_gaveta()
            acesos_por_icone = set()
            for botao, (x, y, w, h, _, acao) in zip(self.botoes, widgets):
                botao.hide = False
                if botao.is_highlight:
                    acesos_por_icone.add(_chave_widget(acao))
                botao.color = cores.text
                botao.alpha = 1
                botao.color_highlight = cores.text_sel
                botao.alpha_highlight = 1
                botao.hide_select = False
                botao.icon = _icone_acao_gaveta(acao)
                botao.scale_basis = 11
                botao.matrix_basis[0][3] = x + (10 if acao[0] in {'chapa', 'auto'} else w / 2)
                botao.matrix_basis[1][3] = y + h / 2
                if acao[0] == 'operador':
                    botao.target_set_operator(acao[1])
                elif acao[0] in {'rolar_nivel', 'auto'}:
                    botao.target_set_operator('object.cabinet_interagir_gaveta')
                elif acao[0] == 'chapa':
                    op = botao.target_set_operator('object.cabinet_marcar')
                    op.alternar = True
                elif acao[0] == 'item':
                    it, indice = acao[1:]
                    nome = ('object.cabinet_inserir_preset',
                            'object.cabinet_editar_modelo',
                            'object.cabinet_bloqueio')[indice]
                    op = botao.target_set_operator(nome)
                    op.pasta, op.arquivo = it['pasta'], it['arquivo']
                    if indice == 0:
                        op.tipo = it.get('tipo', 'modulo')
                    botao.hide_select = indice == 1 and item_bloqueado(it)
            self._preparar_hover(context, acesos_por_icone)
            _desenhar_gaveta(tela=True)
            return
        _realcar(context, 'alca', self.alca.is_highlight)


class VIEW3D_PT_cabinet_creator(Panel):
    # O cabecalho e' a barra de abas; nao repetir um titulo ao lado dela.
    bl_label = ""
    bl_idname = "VIEW3D_PT_cabinet_creator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Cabinet Creator"
    bl_options = {'HEADER_LAYOUT_EXPAND'}

    @classmethod
    def poll(cls, context):
        return not _eh_area_gaveta(context)

    def draw_header(self, context):
        linha = self.layout.row(align=True)
        linha.prop(context.scene, 'cabinet_aba', expand=True)

    def draw(self, context):
        layout = self.layout
        if context.scene.cabinet_aba == 'PORTAS':
            self.desenhar_portas(context, layout)
        else:
            self.desenhar_medidas(context, layout)
            layout.separator()
            self.desenhar_biblioteca(context, layout)

    def desenhar_portas(self, context, layout):
        caixa = layout.box()
        caixa.label(text="Portas parametricas")
        grupo = _grupo_portas(context.object)
        if grupo is not None and context.mode == 'OBJECT':
            op = caixa.operator("object.cabinet_portas", text="Configurar Portas",
                                icon='PREFERENCES')
            op.editar = True
        else:
            caixa.label(text="2 vertices diagonais do vao interno")
            linha = caixa.row()
            linha.enabled = context.mode == 'EDIT_MESH'
            op = linha.operator("object.cabinet_portas", text="Criar Portas",
                                icon='MESH_CUBE')
            op.editar = False
            if context.mode != 'EDIT_MESH':
                caixa.label(text="Selecione as chapas e entre em Edicao")

    # ------------------------------------------------------- MEDIDAS
    def _abas_modo(self, layout, ativo):
        linha = layout.row(align=True)
        for modo, texto in (('INDIVIDUAL', "Individual"), ('GRUPO', "Grupo")):
            op = linha.operator(
                "object.cabinet_modo_medidas", text=texto,
                depress=(ativo == modo))
            op.modo = modo

    def _largura_logica(self, context):
        escala = max(0.5, float(context.preferences.system.ui_scale))
        return float(context.region.width) / escala

    def _painel_estreito(self, context):
        return self._largura_logica(context) < WIREFRAME_LARGURA_EMPILHAR_PX

    def _painel_muito_estreito(self, context):
        return (self._largura_logica(context) <
                MEDIDAS_LARGURA_COLUNA_UNICA_PX)

    def _escala_wireframe(self, context):
        """Escala responsiva com limites para nao sumir nem dominar o painel."""
        disponivel = max(0.0, self._largura_logica(context) - 24.0)
        escala = disponivel / 20.0
        maximo = (WIREFRAME_ESCALA_ESTREITA_MAX_UI
                  if self._painel_estreito(context)
                  else WIREFRAME_ESCALA_MAX_UI)
        return max(WIREFRAME_ESCALA_MIN_UI,
                   min(maximo, escala))

    def _corpo_medidas(self, caixa, context, separador=0.4):
        """Retorna controles e area visual, em linha ou empilhados."""
        estreito = self._painel_estreito(context)
        corpo = (caixa.column(align=True) if estreito
                 else caixa.row(align=False))
        if not estreito:
            # Afasta os controles da quina do box sem deslocar o preview.
            corpo.separator(factor=0.35)
        campos = corpo.column(align=True)
        # No modo estreito, toda a grade precisa usar o centro do box. Manter
        # este contêiner em LEFT faz o Blender compactar a largura útil pelo
        # tamanho natural dos widgets, deixando uma sobra maior à direita.
        campos.alignment = 'CENTER' if estreito else 'LEFT'
        if not estreito:
            # Reserva somente o necessario para rotulos e caixas. Uma coluna
            # maior comprime o preview na area direita antes da quebra.
            campos.ui_units_x = MEDIDAS_LARGURA_CONTROLES_UI
        campos.separator(factor=0.15 if estreito else separador)
        return campos, corpo, estreito

    def _grade_medidas(self, layout, estreito, coluna_unica, desenhadores):
        """Quebra a grade em duas colunas ou uma coluna no limite estreito."""
        if not estreito:
            for desenhar in desenhadores:
                desenhar(layout)
            return

        def desenhar_no_centro(desenhar, ocupacao=0.5):
            """Cria uma faixa central com margens laterais simetricas."""
            margem = (1.0 - ocupacao) * 0.5
            externo = layout.split(factor=margem)
            externo.column()
            restante = externo.column()
            proporcao_no_restante = ocupacao / (1.0 - margem)
            centro_direita = restante.split(factor=proporcao_no_restante)
            celula = centro_direita.column(align=True)
            celula.alignment = 'CENTER'
            desenhar(celula)
            centro_direita.column()

        if coluna_unica:
            for desenhar in desenhadores:
                desenhar_no_centro(
                    desenhar, MEDIDAS_OCUPACAO_COLUNA_UNICA)
            return

        for inicio in range(0, len(desenhadores), 2):
            par = desenhadores[inicio:inicio + 2]
            if len(par) == 2:
                # Sem largura fixa: as duas celulas dividem o espaco por
                # igual e o centro nao deriva para a esquerda ao comprimir.
                # `split` garante duas metades reais do espaco disponivel.
                # Duas `column` dentro de uma `row` podem ser compactadas pelo
                # Blender conforme a largura natural dos campos.
                linha = layout.split(factor=0.5, align=False)
                for desenhar in par:
                    celula = linha.column(align=True)
                    celula.alignment = 'CENTER'
                    desenhar(celula)
            else:
                desenhar_no_centro(par[0])

    def _visual_wireframe(self, layout, context, modo, medidas):
        """Desenha o preview responsivo entre os limites visualmente uteis."""
        coluna = layout.column(align=False)
        coluna.alignment = 'CENTER'
        icone = _icone_wireframe(context, modo, *medidas)
        if icone:
            linha = coluna.row(align=True)
            linha.alignment = 'CENTER'
            linha.template_icon(
                icon_value=icone, scale=self._escala_wireframe(context))
        else:
            coluna.label(text="", icon='MESH_CUBE')

    def _campo_medida(self, layout, dados, propriedade, texto):
        """Rotulo completo acima e campo compacto logo abaixo."""
        alinhamento = ('CENTER' if layout.alignment == 'CENTER' else 'LEFT')
        bloco = layout.column(align=True)
        bloco.alignment = alinhamento
        rotulo = bloco.row(align=True)
        rotulo.alignment = alinhamento
        rotulo.label(text=texto)
        valor = bloco.row(align=True)
        valor.alignment = alinhamento
        valor.prop(dados, propriedade, text="")

    def _rotulo_medida(self, layout, texto, valor_mm):
        """Versao so'-leitura do campo: selecao livre nao tem prop."""
        alinhamento = ('CENTER' if layout.alignment == 'CENTER' else 'LEFT')
        bloco = layout.column(align=True)
        bloco.alignment = alinhamento
        r = bloco.row(align=True)
        r.alignment = alinhamento
        r.label(text=texto)
        v = bloco.row(align=True)
        v.alignment = alinhamento
        v.label(text="%.1f mm" % valor_mm)

    def _campo_dimensao_objeto(self, layout, obj, indice, texto):
        """Dimensao nativa editavel; aceita mm, cm e m como o Blender."""
        alinhamento = ('CENTER' if layout.alignment == 'CENTER' else 'LEFT')
        bloco = layout.column(align=True)
        bloco.alignment = alinhamento
        rotulo = bloco.row(align=True)
        rotulo.alignment = alinhamento
        rotulo.label(text=texto)
        valor = bloco.row(align=True)
        valor.alignment = alinhamento
        valor.prop(obj, "dimensions", index=indice, text="")

    def _medidas_da_selecao(self, context, layout):
        """Caixa de QUALQUER selecao -- cubo, carro, curvas, o que for."""
        m = medir_selecao(context)
        if m is None:
            layout.label(text="Selecione uma chapa, um modulo ou "
                              "qualquer objeto", icon='INFO')
            return
        largura, altura, profundidade, quantos = m
        b = layout.box()
        b.label(text="Selecao (%d objeto%s)"
                     % (quantos, "" if quantos == 1 else "s"),
                icon='SHADING_BBOX')
        # Tres medidas ocupam menos altura que o preview maximo; a margem
        # superior maior centraliza o bloco e o afasta da quina do box.
        campos, visual, estreito = self._corpo_medidas(
            b, context, separador=1.2)
        volumes = [o for o in context.selected_objects
                   if o.type in TIPOS_COM_VOLUME]
        if quantos == 1 and len(volumes) == 1:
            obj = volumes[0]
            # Convencao do add-on: largura=X, altura=Z, profundidade=Y.
            self._grade_medidas(
                campos, estreito, self._painel_muito_estreito(context), [
                lambda lay: self._campo_dimensao_objeto(
                    lay, obj, 0, "Largura"),
                lambda lay: self._campo_dimensao_objeto(
                    lay, obj, 2, "Altura"),
                lambda lay: self._campo_dimensao_objeto(
                    lay, obj, 1, "Profundidade"),
            ])
            largura = obj.dimensions.x * 1000.0
            altura = obj.dimensions.z * 1000.0
            profundidade = obj.dimensions.y * 1000.0
        else:
            # A caixa conjunta de varios objetos nao tem uma unica escala
            # segura para editar; nesse caso as medidas continuam informativas.
            self._grade_medidas(
                campos, estreito, self._painel_muito_estreito(context), [
                lambda lay: self._rotulo_medida(lay, "Largura", largura),
                lambda lay: self._rotulo_medida(lay, "Altura", altura),
                lambda lay: self._rotulo_medida(
                    lay, "Profundidade", profundidade),
            ])
        self._visual_wireframe(visual, context, 'LIVRE',
                               (largura, altura, profundidade))

        # Este bloco so' aparece quando o objeto NAO tem a assinatura do
        # add-on -- e' por isso que ele mostra Altura no lugar de
        # Espessura. Em vez de deixar o usuario adivinhando, diz o
        # motivo e oferece a conversao.
        if (quantos == 1 and len(volumes) == 1
                and volumes[0].type == 'MESH'
                and MARCA_CHAPA not in volumes[0]):
            aviso = b.column(align=True)
            aviso.label(text="Objeto sem assinatura de chapa",
                        icon='INFO')
            aviso.operator("object.cabinet_marcar", icon='MOD_SOLIDIFY')

    def _lista_espessuras(self, layout, centralizar=False):
        linha = layout.row(align=True)
        linha.alignment = 'CENTER' if centralizar else 'LEFT'
        linha.label(text="15/18/20/30")

    def desenhar_medidas(self, context, layout):
        obj = context.object

        portas = _grupo_portas(obj)
        if portas is not None:
            caixa = layout.box()
            caixa.label(text="Vao: %.1f x %.1f mm" %
                        (portas['porta_vao_largura_mm'], portas['porta_vao_altura_mm']))
            caixa.label(text="%d folha(s)" % len(_folhas_portas(portas)))
            caixa.label(text="Use o botao Portas no topo do painel")
            return

        if obj is not None and MARCA_CONJUNTO in obj:
            self._abas_modo(layout, 'GRUPO')
            b = layout.box()
            b.label(text="Modulo (%d pecas)" % len(_chapas_do_conjunto(obj)), icon='MOD_BUILD')
            campos, visual, estreito = self._corpo_medidas(b, context)
            self._grade_medidas(
                campos, estreito, self._painel_muito_estreito(context), [
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_largura", "Largura"),
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_altura", "Altura"),
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_profundidade", "Profundidade"),
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_espessura", "Espessura"),
            ])
            self._lista_espessuras(campos, centralizar=estreito)
            self._visual_wireframe(
                visual, context, 'GRUPO',
                (obj.conj_largura_mm, obj.conj_altura_mm,
                 obj.conj_profundidade_mm))
            b.operator("object.cabinet_sincronizar", icon='FILE_REFRESH')
        elif obj is None or MARCA_CHAPA not in obj:
            self._medidas_da_selecao(context, layout)
        else:
            self._abas_modo(layout, obj.chapa_modo)
            b = layout.box()
            if obj.chapa_modo == 'INDIVIDUAL':
                campos, visual, estreito = self._corpo_medidas(
                    b, context, separador=1.0)
                self._grade_medidas(
                    campos, estreito, self._painel_muito_estreito(context), [
                    lambda lay: self._campo_medida(
                        lay, obj, "ui_chapa_largura", "Largura"),
                    lambda lay: self._campo_medida(
                        lay, obj, "ui_chapa_comprimento", "Comprimento"),
                    lambda lay: self._campo_medida(
                        lay, obj, "ui_chapa_espessura", "Espessura"),
                ])
                self._lista_espessuras(campos, centralizar=estreito)
                campos.separator(factor=0.5)
                campos.prop(obj, "chapa_auto")
                self._visual_wireframe(
                    visual, context, 'INDIVIDUAL',
                    (obj.chapa_largura_mm, obj.chapa_espessura_mm,
                     obj.chapa_comprimento_mm))
            else:
                b.label(text="Grupo: %d peca(s)" % len(grupo_de(obj)), icon='MOD_BUILD')
                sc = context.scene
                campos, visual, estreito = self._corpo_medidas(b, context)
                self._grade_medidas(
                    campos, estreito, self._painel_muito_estreito(context), [
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_largura", "Largura"),
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_altura", "Altura"),
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_profundidade", "Profundidade"),
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_espessura", "Espessura"),
                ])
                self._lista_espessuras(campos, centralizar=estreito)
                self._visual_wireframe(
                    visual, context, 'GRUPO',
                    (sc.grupo_largura_mm, sc.grupo_altura_mm,
                     sc.grupo_profundidade_mm))
                b.operator("object.cabinet_sincronizar_grupo", icon='FILE_REFRESH')

        layout.separator()
        c = layout.column(align=True)
        c.label(text="Montagem:")
        # (idname, rotulo inteiro, rotulo curto, icone). O curto e' um
        # nome ESCOLHIDO, nao o inteiro truncado -- cortar seria o mesmo
        # defeito que a cascata acima evita.
        botoes = (
            ("object.cabinet_agrupar", "Agrupar Conjunto", "Agrupar",
             'OUTLINER_OB_EMPTY'),
            ("object.cabinet_detectar_adjacencia", "Detectar Adjacencia",
             "Adjacencia", 'SNAP_ON'),
            ("object.cabinet_normalizar", "Recalcular Chapas", "Recalcular",
             'FILE_REFRESH'),
        )
        largura = _largura_painel(context)
        if sum(_px_botao(b[2]) for b in botoes) <= largura:
            alvo, i_rotulo = c.row(align=True), 2      # lado a lado
        else:
            alvo, i_rotulo = c.column(align=True), 1   # empilhado
        for botao in botoes:
            alvo.operator(botao[0], text=botao[i_rotulo], icon=botao[3])

    # ---------------------------------------------------- BIBLIOTECA
    # Cascata HORIZONTAL: cada nivel e' uma linha de botoes. O nivel
    # selecionado fica azul (depress=True, o destaque nativo do Blender).
    def _linha_niveis(self, context, layout, nivel, valores, itens, sel,
                      pai=None):
        if not valores:
            return
        if nivel > 1:
            layout.separator(type='LINE')
        # O bpy corta o rotulo pela DIREITA, comendo justamente o "(N)".
        # Por isso a conta e' preservada e o NOME e' encurtado aqui.
        #
        # Antes de encurtar, porem, vale QUEBRAR A LINHA: espremer cinco
        # botoes numa sidebar estreita sobrava uma letra para cada um
        # ("P (0)" para Portas e Puxadores). A grade da mais largura a
        # cada botao e so' entao o nome e' resumido.
        disponivel = _largura_painel(context) - 16.0
        # O numero de colunas so' cresce enquanto o nome INTEIRO ainda
        # couber. Repartir por quantos cabem deixava o texto encolher ao
        # alargar a sidebar (mais colunas, cada uma mais estreita).
        maior = max(len(v) for v in valores) + 5      # folga do " (NN)"
        ideal = max(PX_MIN_NIVEL, maior * PX_CARACTERE + PX_FOLGA_BOTAO)
        colunas = max(1, min(len(valores), int(disponivel // ideal)))
        cabe = int((disponivel / colunas - PX_FOLGA_BOTAO) / PX_CARACTERE)
        linha = layout.grid_flow(row_major=True, columns=colunas,
                                 even_columns=True, align=True)
        for v in sorted(valores, key=str.casefold):
            if nivel == 1:
                n = _conta(itens, v)
            elif nivel == 2:
                n = _conta(itens, pai, v)
            else:
                n = _conta(itens, pai[0], pai[1], v)
            sufixo = " (%d)" % n
            nome = _abreviar(v, cabe - len(sufixo))
            op = linha.operator("object.cabinet_navegar",
                                text=nome + sufixo,
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
        cab.operator("object.cabinet_abrir_biblioteca", text="",
                     icon='FILE_FOLDER')
        # a prateleira nativa: unico lugar onde o arraste real existe
        cab.operator("object.cabinet_prateleira", text="", icon='ASSET_MANAGER')
        # o "+" adiciona a selecao atual a biblioteca
        cab.operator("object.cabinet_salvar_biblioteca", text="", icon='ADD')
        if not s.chapa_bib_aberta:
            return

        menu = layout.box()
        self._linha_niveis(context, menu, 1, list(ARVORE.keys()), itens,
                           s.chapa_n1)
        if s.chapa_n1:
            self._linha_niveis(context, menu, 2, _filhos_n2(s.chapa_n1),
                               itens, s.chapa_n2, pai=s.chapa_n1)
        if s.chapa_n1 and s.chapa_n2:
            self._linha_niveis(context, menu, 3,
                               _filhos_n3(s.chapa_n1, s.chapa_n2), itens,
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
        daqui.sort(key=lambda i: (
            str(i.get("nome", "")).casefold(),
            str(i.get("arquivo", "")).casefold()))

        lista = layout.box()
        trilha = " > ".join(x for x in (s.chapa_n1, s.chapa_n2, s.chapa_n3) if x)
        # a trilha ("Armarios > Sala > Inferiores") saiu: os proprios
        # botoes da cascata, em azul, ja' dizem onde se esta'
        self._barra_tamanho(context, lista, s)
        if not daqui:
            lista.label(text="nenhum modelo aqui", icon='INFO')
            return

        # columns=0 faz o grid_flow calcular sozinho quantas colunas cabem
        # na largura atual do painel -- e' o mecanismo responsivo nativo.
        # As colunas so' precisam ser fixas no modo mosaico, onde a
        # largura do bloco define o tamanho da celula. Na foto normal
        # `columns=0` deixa o bpy distribuir, que e' o comportamento
        # responsivo nativo.
        if _foto_clicavel_ligada():
            colunas, _larg = _metrica_blocos(context, s.chapa_tam_bloco)
        else:
            colunas = 0
        grade = lista.grid_flow(row_major=True, columns=colunas,
                                even_columns=True, even_rows=True,
                                align=False)

        for it in daqui:
            icone = icone_do_item(it)
            travado = item_bloqueado(it)
            bloco = grade.column(align=True)

            # A foto e' um MOSAICO de botoes (ver FOTO CLICAVEL): assim
            # ela cresce com o tamanho escolhido E aciona o posicionador
            # em qualquer ponto, nao so' pelo nome.
            if icone and _foto_clicavel_ligada():
                self._foto_clicavel(context, bloco, it, icone)
            elif icone:
                bloco.template_icon(icon_value=icone,
                                    scale=float(s.chapa_tam_bloco))
            else:
                vazio = bloco.box()
                vazio.scale_y = float(s.chapa_tam_bloco) * 0.5
                vazio.label(text="", icon='IMAGE_DATA')

            # Duas linhas em vez de uma: no bloco estreito tudo junto
            # cortava o cadeado, e sem ele um preset travado nao teria
            # como ser destravado.
            acoes = bloco.column(align=True)

            # O nome chama o POSICIONADOR, igual a foto: o preset gruda
            # no cursor e o proximo clique na viewport confirma.
            op = acoes.operator("object.cabinet_arrastar_preset",
                                text=it["nome"])
            op.pasta = it["pasta"]
            op.arquivo = it["arquivo"]
            op.tipo = it.get("tipo", "modulo")

            botoes = acoes.row(align=True)
            # a seta insere direto no cursor 3D, sem posicionar
            oi = botoes.operator("object.cabinet_inserir_preset",
                                 text="", icon='IMPORT')
            oi.pasta = it["pasta"]
            oi.arquivo = it["arquivo"]
            oi.tipo = it.get("tipo", "modulo")

            # o lapis some com o cadeado fechado, o cadeado NUNCA some
            editar = botoes.row(align=True)
            editar.enabled = not travado
            oe = editar.operator(
                "object.cabinet_editar_modelo", text="", icon='GREASEPENCIL')
            oe.pasta = it["pasta"]
            oe.arquivo = it["arquivo"]
            self._cadeado(botoes, it, travado)

    def _foto_clicavel(self, context, layout, it, icone):
        """Mosaico de botoes com a foto: clicar em qualquer ponto
        aciona o posicionador, igual ao nome."""
        s = context.scene
        png = os.path.splitext(it["arquivo"])[0] + ".png"
        # o ladrilho tem tamanho FIXO: quem varia e' a quantidade deles
        _col, largura_bloco = _metrica_blocos(context, s.chapa_tam_bloco)
        lado = max(2, int(round(
            (largura_bloco - PADDING_BLOCO) / PX_ALVO_CELULA)))
        tiles = _tiles_foto(it["pasta"], png, lado)
        if not tiles:
            # sem os ladrilhos a foto ainda aparece, so' que nao clicavel
            layout.template_icon(icon_value=icone,
                                 scale=float(s.chapa_tam_bloco))
            return

        # Celula maior que o icone deixa fresta e o mosaico vira
        # xadrez. `ui_units_x` fixa a largura da linha em unidades de
        # UI (20 px cada), entao cada ladrilho recebe exatamente o
        # tamanho do icone -- sem precisar saber quantas colunas a
        # grade de blocos resolveu usar. scale_y fecha a fresta de cima.
        # A celula vale largura_do_bloco/lado. Se ela sobrar sobre o
        # icone de 16 px, fica uma fresta por coluna e a foto ganha
        # listras. scale_x encolhe a celula ate' o icone -- e quando a
        # celula fica MENOR que ele, o icone acompanha, sem fresta.
        grade = layout.column(align=True)
        grade.scale_y = PX_TILE_FOTO / 20.0
        for linha_tiles in tiles:
            linha = grade.row(align=True)
            for icon_id in linha_tiles:
                op = linha.operator("object.cabinet_arrastar_preset",
                                    text="", emboss=False,
                                    icon_value=icon_id)
                op.pasta = it["pasta"]
                op.arquivo = it["arquivo"]
                op.tipo = it.get("tipo", "modulo")

    def _barra_tamanho(self, context, layout, s):
        """Barra compacta de fatias clicaveis (ver BARRA DE TAMANHO).

        A largura e' RESERVADA por um split em vez de deixada ao
        alinhamento: com `alignment='RIGHT'` o botao assume uma largura
        natural bem maior que o icone e o trilho sai tracejado, e
        comprimir o bastante para fechar os vaos borrava o desenho.
        """
        prop = bpy.types.Scene.bl_rna.properties["chapa_tam_bloco"]
        menor, maior = prop.hard_min, prop.hard_max
        ultimo = maior - menor
        ativo = max(0, min(ultimo, int(s.chapa_tam_bloco) - menor))

        fatias, _celula, _c = _metrica_barra(context)
        util = PX_FATIA_BARRA * fatias
        largura = max(1.0, _largura_painel(context))
        # o que sobra a esquerda e' so' vao: joga a barra no canto
        fracao = max(0.02, min(0.92, 1.0 - (util + PX_BOTAO_BIBLIOTECA)
                               / largura))
        div = layout.split(factor=fracao)
        div.label(text="")
        direita = div.row(align=True)

        linha = direita.row(align=True)
        linha.scale_x = _metrica_barra(context, util)[2]
        for i in range(fatias):
            op = linha.operator(
                "object.cabinet_tamanho", text="", emboss=False,
                icon_value=_icone_fatia_barra(i, ativo, ultimo))
            op.valor = menor + i
        direita.operator("object.cabinet_asset_browser", text="",
                         icon='ASSET_MANAGER')

    def _cadeado(self, linha, it, travado):
        """Cadeado clicavel, alternando entre os dois sprites."""
        oc = linha.operator("object.cabinet_bloqueio", text="",
                            icon='LOCKED' if travado else 'UNLOCKED',
                            depress=travado)
        oc.pasta = it["pasta"]
        oc.arquivo = it["arquivo"]


CLASSES = (
    CabinetCreatorPreferences,
    OBJECT_OT_sincronizar_grupo,
    OBJECT_OT_sincronizar_conjunto,
    OBJECT_OT_registrar_bibliotecas,
    OBJECT_OT_refiliar_catalogos,
    OBJECT_OT_regerar_previews,
    OBJECT_OT_modo_medidas,
    OBJECT_OT_criar_chapa,
    OBJECT_OT_salvar_biblioteca,
    OBJECT_OT_abrir_pasta_biblioteca,
    OBJECT_OT_abrir_asset_browser,
    OBJECT_OT_definir_tamanho,
    OBJECT_OT_inserir_preset,
    OBJECT_OT_arrastar_preset,
    OBJECT_OT_prateleira,
    OBJECT_OT_selecionar,
    OBJECT_OT_navegar,
    OBJECT_OT_editar_modelo,
    OBJECT_OT_alternar_bloqueio,
    OBJECT_OT_agrupar_conjunto,
    OBJECT_OT_detectar_adjacencia,
    OBJECT_OT_criar_nicho,
    OBJECT_OT_apanhar_vao_portas,
    OBJECT_OT_portas_parametricas,
    OBJECT_OT_editar_medida_gaveta,
    OBJECT_OT_interagir_gaveta,
    OBJECT_OT_alternar_gaveta,
    OBJECT_OT_marcar_como_chapa,
    OBJECT_OT_normalizar,
    VIEW3D_GT_alca_gaveta,
    VIEW3D_GT_campo_gaveta,
    VIEW3D_GGT_cabinet_gaveta,
    VIEW3D_AST_cabinet_creator,
)


_PROPS_MEDIDA_UI_OBJETO = (
    "ui_chapa_largura", "ui_chapa_comprimento", "ui_chapa_espessura",
    "ui_conj_largura", "ui_conj_altura", "ui_conj_profundidade",
    "ui_conj_espessura",
)
_PROPS_MEDIDA_UI_CENA = (
    "ui_grupo_largura", "ui_grupo_altura", "ui_grupo_profundidade",
    "ui_grupo_espessura",
) + tuple(m[0] for m in MEDIDAS_PORTAS)
_PROPS_PORTAS_CENA = (
    "porta_frente", "porta_orientacao", "porta_abertura", "porta_dobradica",
    "porta_folhas", "porta_espessura", "porta_lateral",
) + tuple(m[1] for m in MEDIDAS_PORTAS)


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
    if not bpy.app.timers.is_registered(_limitar_largura_gaveta):
        bpy.app.timers.register(_limitar_largura_gaveta,
                               first_interval=0.3, persistent=True)
    for c in CLASSES:
        bpy.utils.register_class(c)
    _handler_gaveta[0] = bpy.types.SpaceView3D.draw_handler_add(
        _desenhar_gaveta, (), 'WINDOW', 'POST_PIXEL')
    # POST_VIEW: a caixa vive em coordenada de MUNDO, junto da cena
    _handler_grid[0] = bpy.types.SpaceView3D.draw_handler_add(
        _desenhar_grid_medidas, (), 'WINDOW', 'POST_VIEW')
    bpy.app.timers.register(_reconectar_gavetas, first_interval=0.1)
    registrar_keymaps()
    S = bpy.types.Scene
    # Os parametros das portas moram na Scene para a gaveta edita-los
    # sem popup (ver ESCOLHAS_PORTAS).
    S.porta_frente = EnumProperty(
        name="Frente", default='NEG_Y',
        items=[(v, t, t) for v, t in
               (('NEG_Y', '-Y (frontal)'), ('POS_Y', '+Y (traseira)'),
                ('NEG_X', '-X (esquerda)'), ('POS_X', '+X (direita)'))])
    S.porta_orientacao = EnumProperty(
        name="Eixos do vao", default='AUTO',
        items=[(v, t, t) for v, t in
               (('AUTO', 'Pai comum / mundo'), ('MUNDO', 'Mundo'),
                ('ATIVO', 'Objeto ativo'))])
    S.porta_abertura = EnumProperty(name="Abertura", items=ITENS_ABERTURA,
                                    default='GIRO',
                                    update=_limitar_folhas_cena)
    S.porta_dobradica = EnumProperty(name="Dobradica",
                                     items=ITENS_DOBRADICA,
                                     default='ESCOLHER')
    # Dupla e' o padrao de armario; uma folha so' e' a excecao.
    S.porta_folhas = IntProperty(name="Folhas", default=2, min=1, max=4)
    S.porta_espessura = EnumProperty(
        name="Espessura da porta (mm)", default='18',
        items=[(str(int(e)), str(int(e)), "mm") for e in ESPESSURAS_PERMITIDAS])
    S.porta_lateral = EnumProperty(
        name="Espessura da lateral (mm)", default='18',
        items=[(str(int(e)), str(int(e)), "mm") for e in ESPESSURAS_PERMITIDAS])
    for prop_ui, prop_mm, rotulo, minimo in MEDIDAS_PORTAS:
        padrao = {'porta_entre_folhas_mm': 2.0, 'porta_recuo_correr_mm': 30.0,
                  'porta_sobreposicao_mm': 20.0,
                  'porta_entre_planos_mm': 2.0}.get(prop_mm, 0.0)
        setattr(S, prop_mm, FloatProperty(name=rotulo, default=padrao,
                                          min=minimo))
        _registrar_medida_ui(S, prop_ui, prop_mm, rotulo, minimo)
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
    S.cabinet_aba = EnumProperty(
        name="Aba", default='MODULOS',
        items=[('MODULOS', "Modulos", "Medidas, montagem e biblioteca"),
               ('PORTAS', "Portas", "Criacao e configuracao de portas")])
    S.chapa_bib_aberta = BoolProperty(name="Biblioteca", default=False)
    S.chapa_n1 = StringProperty(default="")
    S.chapa_n2 = StringProperty(default="")
    S.chapa_n3 = StringProperty(default="")
    # barra continua (estilo volume) no lugar dos tres degraus P/M/G
    # 7 degraus: com 11 a barra ocupava 70% da sidebar e nao cabia no
    # canto. A miniatura maior continua grande o bastante.
    S.chapa_tam_bloco = IntProperty(
        name="Tamanho", default=5, min=2, max=8,
        description="Tamanho das miniaturas na grade")
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
    _edicao_gaveta[0] = None
    if bpy.app.timers.is_registered(_animar_realces):
        bpy.app.timers.unregister(_animar_realces)
    _realces.clear()
    _deslizes.clear()
    if bpy.app.timers.is_registered(_limitar_largura_gaveta):
        bpy.app.timers.unregister(_limitar_largura_gaveta)
    remover_keymaps()
    _fechar_gavetas_registradas()
    if _handler_gaveta[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler_gaveta[0], 'WINDOW')
        _handler_gaveta[0] = None
    if _handler_grid[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler_grid[0], 'WINDOW')
        _handler_grid[0] = None
    _campos_gaveta.clear()
    _realce_medida[0] = None
    _fotos_gaveta.clear()
    for nome in _imagens_gaveta:
        imagem = bpy.data.images.get(nome)
        if imagem is not None:
            bpy.data.images.remove(imagem)
    _imagens_gaveta.clear()
    if bpy.app.timers.is_registered(_configurar_gavetas):
        bpy.app.timers.unregister(_configurar_gavetas)
    if bpy.app.timers.is_registered(_reconectar_gavetas):
        bpy.app.timers.unregister(_reconectar_gavetas)
    if hasattr(bpy.types.Scene, 'cabinet_aba'):
        del bpy.types.Scene.cabinet_aba
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
    for nome in _PROPS_MEDIDA_UI_CENA + _PROPS_PORTAS_CENA:
        if hasattr(bpy.types.Scene, nome):
            delattr(bpy.types.Scene, nome)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
