bl_info = {
    "name": "Cabinet Creator",
    "author": "Douglas",
    "version": (67, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > N > Cabinet Creator",
    "doc_url": "",
    "description": "Armarios parametricos: chapas com malha editavel e espessura imune a escala",
    "category": "Object",
}

import bpy, bmesh, math, os, uuid, json, gpu
import bpy.utils.previews
from gpu_extras.batch import batch_for_shader
from bpy.props import (FloatProperty, BoolProperty, EnumProperty,
                       StringProperty, IntProperty, IntVectorProperty)
from mathutils import Vector
from mathutils.geometry import intersect_line_plane
from bpy_extras import view3d_utils
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


def medir_selecao(context):
    """Caixa envolvente do que estiver selecionado.

    Devolve (largura, altura, profundidade) em mm -- eixos de mundo
    (X, Z, Y), a mesma convencao das medidas de modulo -- e quantos
    objetos entraram na conta. Devolve None se nada tem volume.
    """
    objs = [o for o in context.selected_objects
            if o.type in TIPOS_COM_VOLUME]
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
    if not contados:
        return None
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
        alvo_preview = col
    else:
        for o in objs:
            o.asset_mark()
            if o.asset_data:
                o.asset_data.catalog_id = ids_cat[cam_cat]
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
            self._arrastando = False
            self._mouse_inicio = (event.mouse_x, event.mouse_y)
            self._moveu = True

        # a grade vive na sidebar, entao a regiao do evento NAO e' a
        # viewport: a janela de desenho tem de ser procurada na area
        self._regiao = next(
            (r for r in context.area.regions if r.type == 'WINDOW'), None)
        self._rv3d = getattr(context.space_data, "region_3d", None)
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
            context.area.tag_redraw()
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
            context.area.tag_redraw()
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
        context.area.tag_redraw()

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
WIREFRAME_PREFIXO = "wireframe:v13:"
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
    """Identifica as direcoes sem adicionar cotas ou linhas auxiliares."""
    topo = _meio_wireframe(pontos[6], pontos[7])
    fundo = _meio_wireframe(pontos[0], pontos[2])
    _desenhar_indicador(buffer, 'L', topo[0], topo[1] + 10.0, cor)
    if modo == 'INDIVIDUAL':
        _desenhar_indicador(
            buffer, 'C', fundo[0] - 9.0, fundo[1] - 8.0, cor)
    else:
        vertical = _meio_wireframe(pontos[2], pontos[6])
        _desenhar_indicador(
            buffer, 'A', max(5.0, vertical[0] - 9.0), vertical[1], cor)
        _desenhar_indicador(
            buffer, 'P', fundo[0] - 9.0, fundo[1] - 8.0, cor)


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
    return _centralizar_wireframe(buffer)


def _centralizar_wireframe(buffer):
    """Centraliza o conteudo VISIVEL, incluindo as letras L/A/P/C."""
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
            registrar_no_indice(pasta_biblioteca(), self.nome, arq,
                                self.n1, n2, n3,
                                "modulo" if self.como_modulo else "objeto")
        except Exception as e:
            self.report({'ERROR'}, "Falha ao salvar: %s" % e)
            return {'CANCELLED'}
        self.report({'INFO'}, "Salvo em %s" % arq)
        return {'FINISHED'}


def _apontar_asset_browser():
    """Aponta o Asset Browser recem-aberto para a biblioteca do addon.

    Roda adiado porque `params` do SpaceFileBrowser so' passa a existir
    depois que a area e' desenhada pela primeira vez. A janela e'
    relida do window_manager a cada chamada -- guardar a referencia
    arriscaria usar um ponteiro morto se ela fosse fechada antes.
    """
    try:
        janelas = bpy.context.window_manager.windows
        if not len(janelas):
            return None
        area = janelas[-1].screen.areas[0]
        if area.type == 'FILE_BROWSER':
            params = getattr(area.spaces.active, "params", None)
            if params is not None:
                params.asset_library_reference = NOME_BIBLIOTECA
    except Exception as e:
        print("[Cabinet Creator] asset browser:", e)
    return None


class OBJECT_OT_abrir_asset_browser(Operator):
    """Abre a biblioteca no Asset Browser do Blender, em outra janela"""
    bl_idname = "object.cabinet_asset_browser"
    bl_label = "Abrir no Asset Browser"

    def execute(self, context):
        registrar_bibliotecas()
        wm = context.window_manager
        antes = len(wm.windows)
        try:
            bpy.ops.wm.window_new()
        except Exception as e:
            print("[Cabinet Creator] nova janela:", e)
            self.report({'WARNING'}, "Nao consegui abrir a janela")
            return {'CANCELLED'}
        if len(wm.windows) <= antes:
            self.report({'WARNING'}, "Nao consegui abrir a janela")
            return {'CANCELLED'}
        try:
            area = wm.windows[-1].screen.areas[0]
            area.type = 'FILE_BROWSER'
            area.ui_type = 'ASSETS'
        except Exception as e:
            print("[Cabinet Creator] asset browser:", e)
            self.report({'WARNING'}, "Troque o editor para Asset Browser")
            return {'CANCELLED'}
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
                and context.area.type == 'VIEW_3D')

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
    for valor, shift, modo, props in _ENTRADAS_KEYMAP:
        kmi = km.keymap_items.new("object.cabinet_selecionar",
                                  'LEFTMOUSE', valor, shift=shift)
        kmi.properties.modo = modo
        for chave, v in props.items():
            setattr(kmi.properties, chave, v)
        _keymaps.append((km, kmi))

    # Arraste a partir da grade da biblioteca. O keymap "User Interface"
    # e' o que enxerga os botoes dos paineis. O PRESS precisa ser capturado
    # antes que o proprio botao consuma o gesto; o modal distingue clique
    # de arraste por distancia e devolve PASS_THROUGH em qualquer controle
    # que nao seja uma miniatura ou nome de preset.
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
        return context.mode == 'OBJECT'

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

    selecao_por_grupo: bpy.props.BoolProperty(
        name="Clique seleciona o modulo inteiro",
        description="Um clique acende todas as pecas do modulo; dois "
                    "cliques isolam a chapa. Desligado, o clique volta a "
                    "ser o do Blender",
        default=True)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "selecao_por_grupo")
        layout.separator()
        layout.prop(self, "pasta_biblioteca")
        layout.label(text="Em uso: " + pasta_biblioteca(),
                     icon='ASSET_MANAGER')
        layout.operator("object.cabinet_registrar_bibliotecas", icon='FILE_REFRESH')
        layout.operator("object.cabinet_refiliar", icon='ASSET_MANAGER')


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
PX_CARACTERE = 6.5
PX_FOLGA_BOTAO = 10.0
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
        self._visual_wireframe(visual, context, 'GRUPO',
                               (largura, altura, profundidade))

    def _lista_espessuras(self, layout, centralizar=False):
        linha = layout.row(align=True)
        linha.alignment = 'CENTER' if centralizar else 'LEFT'
        linha.label(text="15/18/20/30")

    def desenhar_medidas(self, context, layout):
        obj = context.object

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
        cab2 = lista.row(align=True)
        cab2.label(text=trilha)
        cab2.prop(s, "chapa_tam_bloco", text="", slider=True)
        cab2.operator("object.cabinet_asset_browser", text="",
                      icon='ASSET_MANAGER')
        if not daqui:
            lista.label(text="nenhum modelo aqui", icon='INFO')
            return

        # columns=0 faz o grid_flow calcular sozinho quantas colunas cabem
        # na largura atual do painel -- e' o mecanismo responsivo nativo.
        grade = lista.grid_flow(row_major=True, columns=0,
                                even_columns=True, even_rows=True, align=False)

        for n, it in enumerate(daqui):
            icone = icone_do_item(it)
            travado = item_bloqueado(it)
            bloco = grade.column(align=True)

            # So' `template_icon` amplia a foto de verdade. Botoes de
            # operador limitam qualquer preview ao icone pequeno de 16 px;
            # por isso o posicionador clicavel fica no nome logo abaixo.
            if icone:
                bloco.template_icon(icon_value=icone,
                                    scale=float(s.chapa_tam_bloco))
            else:
                vazio = bloco.box()
                vazio.scale_y = float(s.chapa_tam_bloco) * 0.5
                vazio.label(text="", icon='IMAGE_DATA')

            # A seta preserva a insercao direta no cursor 3D. O nome chama
            # o posicionador e conserva o highlight nativo no hover.
            acoes = bloco.row(align=True)
            oi = acoes.operator("object.cabinet_inserir_preset",
                                text="", icon='IMPORT')
            oi.pasta = it["pasta"]
            oi.arquivo = it["arquivo"]
            oi.tipo = it.get("tipo", "modulo")

            op = acoes.operator("object.cabinet_arrastar_preset",
                                text=it["nome"])
            op.pasta = it["pasta"]
            op.arquivo = it["arquivo"]
            op.tipo = it.get("tipo", "modulo")

            # Nome, edicao e bloqueio formam uma unica linha. O lapis
            # continua visivel quando travado, mas fica desabilitado.
            editar = acoes.row(align=True)
            editar.enabled = not travado
            oe = editar.operator(
                "object.cabinet_editar_modelo", text="", icon='GREASEPENCIL')
            oe.pasta = it["pasta"]
            oe.arquivo = it["arquivo"]
            self._cadeado(acoes, it, travado)

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
    OBJECT_OT_modo_medidas,
    OBJECT_OT_criar_chapa,
    OBJECT_OT_salvar_biblioteca,
    OBJECT_OT_abrir_pasta_biblioteca,
    OBJECT_OT_abrir_asset_browser,
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
    OBJECT_OT_marcar_como_chapa,
    OBJECT_OT_normalizar,
    VIEW3D_PT_cabinet_creator,
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
    registrar_keymaps()
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
    # barra continua (estilo volume) no lugar dos tres degraus P/M/G
    S.chapa_tam_bloco = IntProperty(
        name="Tamanho", default=5, min=2, max=12,
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
    remover_keymaps()
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
