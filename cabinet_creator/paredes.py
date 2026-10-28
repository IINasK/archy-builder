"""Paredes, como no Promob: o modulo ARRASTADO com o botao direito e solto
numa superficie vertical encosta as COSTAS nela e fica ASSOCIADO (pedido
do usuario). Parede = QUALQUER superficie vertical que nao seja movel do
add-on; os limites dela (pontas, piso, teto) sao as faces do mesmo plano.

Associado de verdade: o modulo guarda a parede (UID gravado nela) e o
ponto das costas no referencial dela. Mover/girar a parede leva o modulo;
mover/girar o modulo (G/R, medida nova) o devolve ao plano -- so' desliza
nele. Selecionado, mostra as guias ate' as pontas, o piso e o teto; clicar
no numero digita, arrastar de lado muda.

Referencial do modulo (ver `_portas._folgas_do_vao`): Empty no centro X/Y
e na base Z. As costas sao o lado OPOSTO a' porta (pedido do usuario: o
preset com a porta em X encostava a lateral), gravado em `parede_costas`;
a roda do mouse no arraste troca. A caixa das funcoes daqui ja' vem girada
para o "referencial da parede" (`caixa_do_modulo`): X ao longo dela, costas
em +Y."""

import bpy, math, uuid
import numpy as np
import blf, gpu
from gpu_extras.batch import batch_for_shader
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector
from bpy.types import Gizmo, GizmoGroup, Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _portas = _ferragens = _hud = _opcoes = _gaveta = _gavetas = None
_gaveta_desenho = None
_paredes_edicao = _paredes_selecao = None

# ID props gravadas nos .blend (nao renomear: ver invariante 2)
CHAVE_UID_PAREDE = 'cabinet_parede_uid'     # na superficie
CHAVE_PAREDE = 'parede_uid'                 # no modulo: qual parede
CHAVE_PAREDE_NOME = 'parede_nome'           # dica (Shift+D copia o UID)
CHAVE_PAREDE_PONTO = 'parede_ponto'         # costas no referencial dela
CHAVE_PAREDE_NORMAL = 'parede_normal'       # normal no referencial dela
CHAVE_PAREDE_FACE = 'parede_face'           # a FACE: indice na malha avaliada
CHAVE_AFASTAMENTO = 'parede_afastamento_mm' # folga costas-parede (Promob)
CHAVE_COSTAS = 'parede_costas'              # lado do modulo contra a parede

# lado das costas -> quartos de volta em Z que o levam a +Y; nesta ordem a
# roda gira o modulo de 90 em 90 graus
GIRO_COSTAS = {'POS_Y': 0, 'POS_X': 1, 'NEG_Y': 2, 'NEG_X': 3}
LADOS_COSTAS = tuple(GIRO_COSTAS)
OPOSTO = {'POS_Y': 'NEG_Y', 'NEG_Y': 'POS_Y', 'POS_X': 'NEG_X', 'NEG_X': 'POS_X'}

INCLINACAO_MAX = 0.5        # |normal.z| acima disto e' piso/teto/tampo
TOLERANCIA_PLANO_M = 0.002  # faces a ate' 2 mm do plano sao a mesma parede
COPLANAR_MIN = 0.999        # cosseno entre normais da mesma parede
SNAP_PX = 12                # pontas, piso e teto grudam a 12 px
LIMIAR_ARRASTE_PX = 6
DESLOCAMENTO_GUIA_M = 0.001  # as guias ficam 1 mm a' frente da parede
LADOS = ('esquerda', 'direita', 'piso', 'teto')
NOMES_LADO = {'esquerda': 'Esquerda', 'direita': 'Direita',
              'piso': 'Piso', 'teto': 'Teto'}
Z = Vector((0.0, 0.0, 1.0))

# Estado global: so' NOMES e vetores, nunca objetos (Ctrl+Z libera a
# memoria deles; ver CLAUDE.md, armadilhas da API)
_conferidos = {}        # modulo -> (assinatura da parede, do modulo)
_retangulos = {}        # (objeto, matriz, malha) -> [regioes de `regiao_da_parede`]
_guias = [None]         # guias do modulo ativo (ver `calcular_guias`)
_rotulos = {}           # regiao -> [(lado, x0, y0, x1, y1, direcao, mm/px)]
_hover_guia = [None]    # lado sob o mouse
_edicao_guia = [None]   # {'lado', 'texto', 'cursor', 'selecionado'}
_arraste_parede = [None]  # {'modulo', 'valido'}: previa do arraste


# ------------------------------------------------------------- geometria
def eh_movel(obj):
    """Peca ou grupo do add-on: nunca e' parede."""
    marcas = (_chapas.MARCA_CHAPA, _chapas.MARCA_CONJUNTO, _chapas.MARCA_PORTAS,
              _chapas.MARCA_FOLHA, _chapas.MARCA_PUXADOR, _chapas.MARCA_ACESSORIO,
              _chapas.MARCA_MOLDURA, _ferragens.CHAVE_FERRAGEM)
    while obj is not None:
        if any(m in obj for m in marcas):
            return True
        obj = obj.parent
    return False


def modulo_de(obj):
    """O modulo (Empty do conjunto) de `obj` -- ele mesmo, uma chapa, a
    porta ou uma ferragem dele --, ou None."""
    while obj is not None:
        if _chapas.MARCA_CONJUNTO in obj:
            return obj
        obj = obj.parent
    return None


def eixos_da_parede(normal):
    """(n, u): normal HORIZONTAL da parede e o "para a direita" de quem a
    olha de frente. None se a superficie nao e' vertical."""
    normal = Vector(normal)
    if normal.length < 1e-9 or abs(normal.normalized().z) > INCLINACAO_MAX:
        return None
    n = Vector((normal.x, normal.y, 0.0)).normalized()
    return n, Z.cross(n)


def rotacao_na_parede(n, u):
    """Costas (+Y do modulo) contra a parede: X = u, Y = -n, Z = Z."""
    return Matrix((u, -n, Z)).transposed()


def _assinatura(matriz):
    return tuple(round(v, 6) for linha in matriz for v in linha)


def _normal_no_mundo(parede, normal_local):
    return (parede.matrix_world.to_3x3().inverted_safe().transposed()
            @ Vector(normal_local)).normalized()


def _ler(colecao, atributo, n, largura=1, tipo=np.float64):
    # foreach_get so' e' rapido no tipo nativo (float32/int32); a conta e'
    # feita depois, no tipo pedido.
    dados = np.empty(n * largura, dtype=np.int32 if np.issubdtype(tipo, np.integer) else np.float32)
    colecao.foreach_get(atributo, dados)
    dados = dados.astype(tipo)
    return dados.reshape(n, largura) if largura > 1 else dados


def _ler_atributo(malha, nome, campo, n, largura, reserva):
    """Atributo interno da malha (`.corner_edge`, `position`...): lido em
    bloco, ~100x mais rapido que `loops.edge_index` numa casa real.
    `reserva` = (colecao, atributo) antigo, se o atributo nao existir."""
    atributo = malha.attributes.get(nome)
    inteiro = nome.startswith('.')
    tipo = np.int64 if inteiro else np.float64
    if atributo is not None and len(atributo.data) == n:
        return _ler(atributo.data, campo, n, largura, tipo)
    return _ler(reserva[0], reserva[1], n, largura, tipo)


def _faixas(inicios, totais):
    """Indices de todas as faixas [inicio, inicio + total), concatenados."""
    if not len(totais):
        return np.empty(0, dtype=np.int64)
    fins = np.cumsum(totais)
    return np.repeat(inicios - (fins - totais), totais) + np.arange(fins[-1])


def _calcular_regiao(malha, mundo, ponto, normal, face, u, orientacao_min=None, conferir_vertices=False):
    """Regiao da face em lote (numpy): uma casa real tem centenas de milhares
    de faces, e o laco em Python por face travava o Blender a cada passo do
    mouse (relato do usuario, v321)."""
    n_faces = len(malha.polygons)
    if not n_faces:
        return None
    m3 = np.array(mundo.to_3x3(), dtype=np.float64)
    desloc = np.array(mundo.translation, dtype=np.float64)
    rot_normal = np.array(mundo.to_3x3().inverted_safe().transposed(), dtype=np.float64)
    lidas = getattr(malha, 'polygon_normals', None)
    normais = (_ler(lidas, 'vector', n_faces, 3) if lidas is not None
               else _ler(malha.polygons, 'normal', n_faces, 3)) @ rot_normal.T
    normais /= np.maximum(np.linalg.norm(normais, axis=1), 1e-12)[:, None]
    n_lacos = len(malha.loops)
    inicios = _ler(malha.polygons, 'loop_start', n_faces, tipo=np.int64)
    totais = np.diff(np.append(inicios, n_lacos))
    vertices_dos_lacos = _ler_atributo(malha, '.corner_vert', 'value', n_lacos, 1,
                                       (malha.loops, 'vertex_index'))
    vertices = _ler_atributo(malha, 'position', 'vector', len(malha.vertices), 3,
                             (malha.vertices, 'co')) @ m3.T + desloc
    # centro = media dos vertices, como o `poly.center` do Blender
    centros = np.add.reduceat(vertices[vertices_dos_lacos], inicios) / totais[:, None]
    n = np.array(normal, dtype=np.float64)
    coplanar = normais @ n >= (COPLANAR_MIN if orientacao_min is None else orientacao_min)
    if conferir_vertices:
        perto=np.abs((vertices-np.array(ponto))@n)<=TOLERANCIA_PLANO_M
        coplanar &= np.logical_and.reduceat(perto[vertices_dos_lacos],inicios)
    distancias = (centros - np.array(ponto)) @ n
    if face is not None and 0 <= face < n_faces and coplanar[face] \
            and abs(distancias[face]) <= TOLERANCIA_PLANO_M:
        semente = int(face)
    else:
        candidatas = np.flatnonzero(coplanar & (np.abs(distancias) <= TOLERANCIA_PLANO_M))
        if not len(candidatas):
            return None
        semente = int(candidatas[np.argmin(np.linalg.norm(
            centros[candidatas] - np.array(ponto), axis=1))])
    no_plano = np.flatnonzero(coplanar & (np.abs((centros - centros[semente]) @ n)
                                          <= TOLERANCIA_PLANO_M))
    # Vizinhas por aresta, so' entre as faces do plano.
    arestas_dos_lacos = _ler_atributo(malha, '.corner_edge', 'value', n_lacos, 1,
                                      (malha.loops, 'edge_index'))
    lacos = _faixas(inicios[no_plano], totais[no_plano])
    dona = np.repeat(np.arange(len(no_plano)), totais[no_plano])
    arestas = arestas_dos_lacos[lacos]
    ordem = np.argsort(arestas, kind='stable')
    arestas_ord, dona_ord = arestas[ordem], dona[ordem]
    par = np.flatnonzero(arestas_ord[1:] == arestas_ord[:-1])
    a, b = dona_ord[par], dona_ord[par + 1]
    origem = np.concatenate((a, b))
    destino = np.concatenate((b, a))
    ordem = np.argsort(origem, kind='stable')
    origem, destino = origem[ordem], destino[ordem]
    ponteiro = np.searchsorted(origem, np.arange(len(no_plano) + 1))
    visitada = np.zeros(len(no_plano), dtype=bool)
    fronteira = np.array([int(np.searchsorted(no_plano, semente))])
    visitada[fronteira] = True
    while len(fronteira):
        vizinhas = destino[_faixas(ponteiro[fronteira], ponteiro[fronteira + 1]
                                   - ponteiro[fronteira])]
        vizinhas = np.unique(vizinhas[~visitada[vizinhas]])
        visitada[vizinhas] = True
        fronteira = vizinhas
    faces = no_plano[visitada]
    # Pontos, contorno (aresta de uma face so') e leque de triangulos.
    lacos = _faixas(inicios[faces], totais[faces])
    usadas, vezes = np.unique(arestas_dos_lacos[lacos], return_counts=True)
    borda = usadas[vezes == 1]
    pontas = _ler_atributo(malha, '.edge_verts', 'value', len(malha.edges), 2,
                           (malha.edges, 'vertices'))[borda]
    usados = vertices[np.unique(vertices_dos_lacos[lacos])]
    posicao = lacos - np.repeat(inicios[faces], totais[faces])
    total = np.repeat(totais[faces], totais[faces])
    meio = lacos[(posicao >= 1) & (posicao <= total - 2)]
    primeiro = np.repeat(inicios[faces], totais[faces] - 2)
    triangulos = np.stack((vertices[vertices_dos_lacos[primeiro]],
                           vertices[vertices_dos_lacos[meio]],
                           vertices[vertices_dos_lacos[meio + 1]]), axis=1).reshape(-1, 3)
    u = np.array(u, dtype=np.float64)
    return {
        'face': semente,
        'faces': frozenset(faces.tolist()),
        'retangulo': (float((usados @ u).min()), float((usados @ u).max()),
                      float(usados[:, 2].min()), float(usados[:, 2].max())),
        'contorno': [(Vector(vertices[i]), Vector(vertices[j])) for i, j in pontas],
        # numpy (n, 3), float32: vai direto para a GPU
        'triangulos': triangulos.astype(np.float32),
        'normal': tuple(n), 'plano': tuple(centros[semente]),
    }


def _face_no_plano(malha, mundo, ponto, normal, face):
    if face is None or not 0 <= face < len(malha.polygons):
        return False
    poly = malha.polygons[face]
    return ((mundo.to_3x3().inverted_safe().transposed() @ poly.normal).normalized().dot(normal)
            >= COPLANAR_MIN and abs((mundo @ poly.center - ponto).dot(normal)) <= TOLERANCIA_PLANO_M)


def regiao_da_parede(parede, ponto, normal, dep=None, face=None):
    """A PAREDE e' a face clicada mais as vizinhas no mesmo plano (pedido
    do usuario: associar a' FACE, nao ao objeto -- uma sala inteira num
    objeto so' tem uma parede por face). Devolve {'face' (semente),
    'faces', 'retangulo' (s0, s1, z0, z1 em m: s ao longo de u a partir da
    origem do mundo, z de mundo), 'contorno' [(a, b)] e 'triangulos' (numpy)
    em mundo} ou None se a superficie nao e' parede.

    A regiao calculada vale para TODAS as faces dela: o mouse andando pela
    mesma parede so' consulta o cache."""
    s=_paredes_edicao._sessao[0]
    if s and s.get('recorte_explicito') and parede is not None and parede.name==s['parede']:
        n=Vector(s['normal'])
        if Vector(normal).dot(n)>=COPLANAR_MIN and abs((Vector(ponto)-Vector(s['ponto'])).dot(n))<=TOLERANCIA_PLANO_M:
            return s['regiao'] if _paredes_selecao.ponto_na_regiao(s['regiao'],Vector(ponto),Vector(s['u'])) else None
    eixos = eixos_da_parede(normal)
    if eixos is None or parede is None or parede.type != 'MESH':
        return None
    _n, u = eixos
    normal = Vector(normal).normalized()
    ponto = Vector(ponto)
    origem = parede.evaluated_get(dep) if dep is not None else parede
    malha = origem.data
    mundo = parede.matrix_world
    chave = (parede.name, _assinatura(mundo), len(malha.polygons), len(malha.vertices))
    conhecidas = _retangulos.setdefault(chave, [])
    no_plano = [r for r in conhecidas
                if normal.dot(Vector(r['normal'])) >= COPLANAR_MIN
                and abs((ponto - Vector(r['plano'])).dot(normal)) <= TOLERANCIA_PLANO_M]
    for regiao in no_plano:
        if face in regiao['faces']:
            return regiao if regiao['face'] == face else dict(regiao, face=face)
    if no_plano and not _face_no_plano(malha, mundo, ponto, normal, face):
        # Sem indice valido (associacao antiga, malha refeita): o timer
        # pergunta a cada tique, e recalcular a casa toda travava.
        s, z = ponto.dot(u), ponto.z
        for regiao in no_plano:
            s0, s1, z0, z1 = regiao['retangulo']
            if s0 - TOLERANCIA_PLANO_M <= s <= s1 + TOLERANCIA_PLANO_M \
                    and z0 - TOLERANCIA_PLANO_M <= z <= z1 + TOLERANCIA_PLANO_M:
                return regiao
    regiao = _calcular_regiao(malha, mundo, ponto, normal, face, u)
    if regiao is not None:
        if len(_retangulos) > 16 or len(conhecidas) > 64:
            _retangulos.clear()
            conhecidas = _retangulos.setdefault(chave, [])
        conhecidas.append(regiao)
    return regiao


def retangulo_da_parede(parede, ponto, normal, dep=None, face=None):
    """(s0, s1, z0, z1) da parede (`regiao_da_parede`), ou None."""
    regiao = regiao_da_parede(parede, ponto, normal, dep, face)
    return regiao['retangulo'] if regiao is not None else None


def caixa_local_do_modulo(conj):
    """(lo, hi) da caixa das chapas nos eixos do modulo, em m, ou None."""
    limites = _portas._limites_locais_modulo(conj)
    if limites is None:
        return None
    lo, hi = limites
    return lo / 1000.0, hi / 1000.0


def frente_do_modulo(conj, caixa_local=None):
    """Lado ('NEG_Y', 'POS_X'...) das folhas de porta e frentes de gaveta,
    ou None. Pela POSICAO de cada uma (o centro fica na face que ela
    fecha): nao depende de como a peca foi girada."""
    caixa_local = caixa_local or caixa_local_do_modulo(conj)
    if caixa_local is None:
        return None
    lo, hi = caixa_local
    centro, meio = (lo + hi) / 2.0, (hi - lo) / 2.0
    inversa = conj.matrix_world.inverted_safe()
    frentes = [f for g in _portas._portas_do_conjunto(conj) for f in _portas._folhas_portas(g)]
    frentes += [o for o in conj.children_recursive if o.get(_gavetas.MARCA_PECA) == 'FRENTE']
    votos = {}
    for peca in frentes:
        if peca.type != 'MESH':
            continue
        p = inversa @ (peca.matrix_world @ (sum((Vector(c) for c in peca.bound_box), Vector()) / 8.0))
        razoes = [abs(p[i] - centro[i]) / meio[i] if meio[i] > 1e-6 else 0.0 for i in (0, 1)]
        eixo = 0 if razoes[0] > razoes[1] else 1
        if razoes[eixo] < 0.5:          # no meio do modulo: nao e' frente
            continue
        lado = ('NEG_' if p[eixo] < centro[eixo] else 'POS_') + 'XY'[eixo]
        votos[lado] = votos.get(lado, 0) + 1
    if not votos:
        return None
    # empate fica com a frente comum (-Y)
    return max(votos, key=lambda lado: (votos[lado], lado == 'NEG_Y'))


def lado_das_costas(conj, caixa_local=None):
    """O lado gravado (roda do mouse ou associacao), senao o oposto a'
    porta; sem porta, +Y (a frente comum e' -Y)."""
    lado = conj.get(CHAVE_COSTAS)
    if lado in GIRO_COSTAS:
        return lado
    frente = frente_do_modulo(conj, caixa_local)
    return OPOSTO[frente] if frente else 'POS_Y'


def giro_das_costas(lado):
    """Rotacao (3x3) dos eixos do modulo para os da parede (costas em +Y)."""
    return Matrix.Rotation(math.pi / 2.0 * GIRO_COSTAS[lado], 3, 'Z')


def girar_caixa(caixa_local, lado):
    """A caixa local vista no referencial da parede (`giro_das_costas`)."""
    lo, hi = caixa_local
    giro = giro_das_costas(lado)
    cantos = [giro @ Vector((x, y, 0.0)) for x in (lo.x, hi.x) for y in (lo.y, hi.y)]
    return (Vector((min(p.x for p in cantos), min(p.y for p in cantos), lo.z)),
            Vector((max(p.x for p in cantos), max(p.y for p in cantos), hi.z)))


def caixa_do_modulo(conj):
    """(lo, hi) da caixa das chapas no referencial da PAREDE (X ao longo
    dela, costas em +Y; ver `referencial`), em m, ou None."""
    local = caixa_local_do_modulo(conj)
    if local is None:
        return None
    return girar_caixa(local, lado_das_costas(conj, local))


def referencial(conj):
    """Matriz de mundo do referencial da parede: leva a caixa de
    `caixa_do_modulo` ao mundo."""
    return conj.matrix_world @ giro_das_costas(lado_das_costas(conj)).transposed().to_4x4()


def girar_costas(conj, passos):
    """Roda do mouse no arraste: a face seguinte do modulo vai contra a
    parede (pedido do usuario)."""
    i = LADOS_COSTAS.index(lado_das_costas(conj))
    conj[CHAVE_COSTAS] = LADOS_COSTAS[(i + passos) % len(LADOS_COSTAS)]
    return conj[CHAVE_COSTAS]


def passos_da_roda(event):
    """+1/-1 na roda do mouse, 0 nos outros eventos."""
    return {'WHEELUPMOUSE': 1, 'WHEELDOWNMOUSE': -1}.get(event.type, 0)


def medidas_na_parede(conj, medidas):
    """(L, A, P) do modulo como a parede ve: no giro de 90 a largura ao
    longo dela e' a profundidade do modulo (e vice-versa)."""
    if GIRO_COSTAS[lado_das_costas(conj)] % 2:
        return (medidas[2], medidas[1], medidas[0])
    return tuple(medidas)


def escala_no_referencial(conj):
    """Escala do Empty nos eixos da parede: o giro de 90 troca X e Y."""
    escala = conj.matrix_world.to_scale()
    if GIRO_COSTAS[lado_das_costas(conj)] % 2:
        escala.x, escala.y = escala.y, escala.x
    return escala


def afastamento(conj):
    """Folga (m) entre as costas do modulo e o plano da parede."""
    return max(0.0, float(conj.get(CHAVE_AFASTAMENTO, 0.0))) / 1000.0


def definir_afastamento(conj, valor_m):
    if valor_m > 1e-9:
        conj[CHAVE_AFASTAMENTO] = round(valor_m * 1000.0, 4)
    elif CHAVE_AFASTAMENTO in conj:
        del conj[CHAVE_AFASTAMENTO]


def ponto_das_costas(conj, caixa=None):
    """Centro da base das costas do modulo, em mundo."""
    caixa = caixa or caixa_do_modulo(conj)
    if caixa is None:
        return None
    lo, hi = caixa
    return referencial(conj) @ Vector(((lo.x + hi.x) / 2.0, hi.y, lo.z))


def matriz_na_parede(conj, costas, n, u, caixa=None):
    """Matriz de mundo do modulo com o centro da base das costas em
    `costas` (NO plano da parede) mais o afastamento dele, virado para
    fora da parede. A escala do Empty fica."""
    caixa = caixa or caixa_do_modulo(conj)
    lo, hi = caixa
    escala = conj.matrix_world.to_scale()
    lado = lado_das_costas(conj)
    if conj.get(CHAVE_COSTAS) != lado:
        # gravado ANTES de mover: depois, as filhas ficam defasadas ate' o
        # proximo update e a porta seria lida no lugar antigo
        conj[CHAVE_COSTAS] = lado
    giro = giro_das_costas(lado)
    local = giro.transposed() @ Vector(((lo.x + hi.x) / 2.0, hi.y, lo.z))
    local = Vector((local.x * escala.x, local.y * escala.y, local.z * escala.z))
    rotacao = rotacao_na_parede(n, u) @ giro
    costas = Vector(costas) + Vector(n).normalized() * afastamento(conj)
    return (Matrix.Translation(costas - rotacao @ local)
            @ rotacao.to_4x4() @ Matrix.Diagonal((*escala, 1.0)))


# ---------------------------------------------------------- associacao
def _uid_da_parede(parede):
    uid = parede.get(CHAVE_UID_PAREDE)
    if not uid:
        uid = uuid.uuid4().hex
        parede[CHAVE_UID_PAREDE] = uid
    return uid


def parede_do_modulo(conj):
    """A parede associada ao modulo, ou None. Pelo UID (renomear nao
    solta); o nome so' desempata a parede duplicada (Shift+D copia o UID)."""
    uid = conj.get(CHAVE_PAREDE)
    if not uid:
        return None
    dica = bpy.data.objects.get(conj.get(CHAVE_PAREDE_NOME, ''))
    if dica is not None and dica.get(CHAVE_UID_PAREDE) == uid:
        return dica
    return next((o for o in bpy.data.objects
                 if o.get(CHAVE_UID_PAREDE) == uid), None)


def associar(conj, parede, costas, normal, face=None):
    """Grava a associacao a' FACE: o objeto (UID), o indice da face e o
    ponto das costas e a normal no referencial dele (assim a parede pode
    andar e girar levando o modulo). Se a malha mudar e o indice nao bater
    mais, vale a face do mesmo plano mais perto (`_calcular_regiao`)."""
    conj[CHAVE_PAREDE] = _uid_da_parede(parede)
    conj[CHAVE_PAREDE_NOME] = parede.name
    # gravado: a porta mudada depois nao gira o modulo associado
    conj[CHAVE_COSTAS] = lado_das_costas(conj)
    if face is not None:
        conj[CHAVE_PAREDE_FACE] = int(face)
    elif CHAVE_PAREDE_FACE in conj:
        del conj[CHAVE_PAREDE_FACE]
    gravar_ponto(conj, parede, costas)
    conj[CHAVE_PAREDE_NORMAL] = tuple(
        (parede.matrix_world.to_3x3().transposed() @ Vector(normal)).normalized())
    _conferidos.pop(conj.name, None)


def gravar_ponto(conj, parede, costas):
    conj[CHAVE_PAREDE_PONTO] = tuple(parede.matrix_world.inverted_safe() @ Vector(costas))


CHAVES_ASSOCIACAO = (CHAVE_PAREDE, CHAVE_PAREDE_NOME, CHAVE_PAREDE_PONTO,
                     CHAVE_PAREDE_NORMAL, CHAVE_PAREDE_FACE, CHAVE_AFASTAMENTO,
                     CHAVE_COSTAS)


def desassociar(conj):
    for chave in CHAVES_ASSOCIACAO:
        if chave in conj:
            del conj[chave]
    _conferidos.pop(conj.name, None)


def plano_do_modulo(conj, parede=None):
    """(costas gravadas, normal) em mundo, ou None."""
    parede = parede or parede_do_modulo(conj)
    if parede is None or CHAVE_PAREDE_PONTO not in conj:
        return None
    return (parede.matrix_world @ Vector(conj[CHAVE_PAREDE_PONTO]),
            _normal_no_mundo(parede, conj[CHAVE_PAREDE_NORMAL]))


def colocar_na_parede(conj, parede, costas, normal, caixa=None):
    """Leva o modulo para `costas` (no plano) e grava o ponto."""
    eixos = eixos_da_parede(normal)
    caixa = caixa or caixa_do_modulo(conj)
    if eixos is None or caixa is None:
        return False
    conj.matrix_world = matriz_na_parede(conj, costas, *eixos, caixa=caixa)
    gravar_ponto(conj, parede, costas)
    return True


def _projetar_no_plano(ponto, plano_ponto, n):
    ponto = Vector(ponto)
    return ponto - n * (ponto - Vector(plano_ponto)).dot(n)


def manter_nas_paredes(context=None):
    """Chamado pelo timer de seguranca (fora de modal): a parede que andou
    leva os modulos dela; o modulo que andou (G/R, medida) volta ao plano
    da parede -- associado, ele so' desliza nela."""
    mudou = False
    vivos = set()
    for conj in [o for o in bpy.data.objects if o.get(CHAVE_PAREDE)]:
        vivos.add(conj.name)
        parede = parede_do_modulo(conj)
        plano = plano_do_modulo(conj, parede) if parede is not None else None
        if plano is None:
            continue
        assinatura = (_assinatura(parede.matrix_world), _assinatura(conj.matrix_world))
        antes = _conferidos.get(conj.name)
        if antes == assinatura:
            continue
        costas_gravadas, normal = plano
        eixos = eixos_da_parede(normal)
        if CHAVE_COSTAS not in conj:
            # associado antes de `parede_costas`: grava o lado oposto a' porta
            # (o arraste mede a caixa dos vizinhos a cada movimento)
            conj[CHAVE_COSTAS] = lado_das_costas(conj)
            mudou = True
        caixa = caixa_do_modulo(conj)
        if eixos is None or caixa is None:
            continue
        n, u = eixos
        if antes is not None and antes[0] != assinatura[0]:
            destino = costas_gravadas          # a parede andou: vai junto
        else:
            destino = _projetar_no_plano(ponto_das_costas(conj, caixa),
                                         costas_gravadas, n)
        nova = matriz_na_parede(conj, destino, n, u, caixa)
        if _assinatura(nova) != _assinatura(conj.matrix_world):
            conj.matrix_world = nova
            mudou = True
        if (Vector(destino) - costas_gravadas).length > 1e-7:
            gravar_ponto(conj, parede, destino)
        _conferidos[conj.name] = (_assinatura(parede.matrix_world),
                                  _assinatura(nova))
    for nome in [k for k in _conferidos if k not in vivos]:
        del _conferidos[nome]
    if mudou:
        (context or bpy.context).view_layer.update()
    return mudou


# --------------------------------------------------------------- guias
def calcular_guias(conj, dep=None):
    """{'modulo', 'valores' (mm por lado), 'linhas' (lado -> (a, b) em
    mundo, b na ponta do MODULO), 'contorno' (bordas da FACE, [(a, b)])}
    ou None. Esquerda/direita como quem olha a parede de frente."""
    parede = parede_do_modulo(conj)
    plano = plano_do_modulo(conj, parede) if parede is not None else None
    caixa = caixa_do_modulo(conj)
    if plano is None or caixa is None:
        return None
    costas, normal = plano
    eixos = eixos_da_parede(normal)
    if eixos is None:
        return None
    n, u = eixos
    regiao = regiao_da_parede(parede, costas, normal, dep,
                              conj.get(CHAVE_PAREDE_FACE))
    if regiao is None:
        return None
    s0, s1, z0, z1 = regiao['retangulo']
    lo, hi = caixa
    escala = escala_no_referencial(conj)
    largura = (hi.x - lo.x) * escala.x
    altura = (hi.z - lo.z) * escala.z
    sc, base = costas.dot(u), costas.z
    esq, dir_ = sc - largura / 2.0, sc + largura / 2.0
    topo = base + altura
    frente = n * DESLOCAMENTO_GUIA_M
    meio_z, meio_s = base + altura / 2.0, sc

    def ponto(s, z):
        # no plano das costas: s ao longo de u, z de mundo
        return costas + u * (s - sc) + Z * (z - base) + frente
    return {
        'modulo': conj.name,
        'valores': {'esquerda': (esq - s0) * 1000.0, 'direita': (s1 - dir_) * 1000.0,
                    'piso': (base - z0) * 1000.0, 'teto': (z1 - topo) * 1000.0},
        'linhas': {'esquerda': (ponto(s0, meio_z), ponto(esq, meio_z)),
                   'direita': (ponto(s1, meio_z), ponto(dir_, meio_z)),
                   'piso': (ponto(meio_s, z0), ponto(meio_s, base)),
                   'teto': (ponto(meio_s, z1), ponto(meio_s, topo))},
        'contorno': [(a + frente, b + frente) for a, b in regiao['contorno']],
    }


def aplicar_guia(conj, lado, valor_mm, dep=None):
    """Leva o modulo para ficar a `valor_mm` daquele lado da parede."""
    guias = calcular_guias(conj, dep)
    if guias is None:
        return False
    atual = guias['valores'][lado]
    delta = (float(valor_mm) - atual) / 1000.0
    costas, normal = plano_do_modulo(conj)
    _n, u = eixos_da_parede(normal)
    passo = {'esquerda': u * delta, 'direita': -u * delta,
             'piso': Z * delta, 'teto': -Z * delta}[lado]
    return colocar_na_parede(conj, parede_do_modulo(conj), costas + passo, normal)


def _modulo_das_guias(context):
    """O modulo ativo, selecionado e associado (as guias sao dele)."""
    camada = getattr(context, 'view_layer', None)
    ativo = camada.objects.active if camada is not None else None
    conj = modulo_de(ativo)
    if conj is None or not conj.get(CHAVE_PAREDE) or not conj.select_get():
        return None
    return conj


def atualizar_guias(context=None):
    """Recalcula as guias do modulo ativo FORA do desenho (o desenho nao
    avalia o depsgraph): timer e modais chamam."""
    context = context or bpy.context
    conj = _modulo_das_guias(context)
    if conj is None:
        if _guias[0] is not None:
            _guias[0] = None
            _redesenhar()
        return
    try:
        dep = context.evaluated_depsgraph_get()
    except Exception:
        dep = None
    antes = _guias[0]
    _guias[0] = calcular_guias(conj, dep)
    if _resumo(antes) != _resumo(_guias[0]):
        _redesenhar()


def _resumo(guias):
    if guias is None:
        return None
    return guias['modulo'], tuple(round(v, 3) for v in guias['valores'].values())


def _redesenhar():
    for janela in bpy.context.window_manager.windows:
        for area in janela.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


# ------------------------------------------------------------- desenho
def _texto_do_valor(lado, valor):
    edicao = _edicao_guia[0]
    if edicao is not None and edicao['lado'] == lado:
        return _gaveta_desenho._com_cursor(edicao['texto'], edicao['cursor'])
    return _opcoes._numero_na_unidade(valor)


def desenhar_guias(context):
    """Linhas das guias e os numeros (POST_PIXEL, chamado pela HUD)."""
    regiao = context.region
    _rotulos.pop(regiao.as_pointer(), None)
    rv3d = context.region_data

    def tela(p):
        return view3d_utils.location_3d_to_region_2d(regiao, rv3d, p)
    realce = _hud._cor_realce_hud()
    arraste = _arraste_parede[0]
    if arraste is not None and arraste.get('valido'):
        _desenhar_face_alvo(arraste, tela, realce, regiao, rv3d)
    guias = _guias[0]
    if guias is None:
        return
    conj = bpy.data.objects.get(guias['modulo'])
    if conj is None or not (conj.select_get() or (
            arraste is not None and arraste['modulo'] == conj.name)):
        return
    escala = context.preferences.system.ui_scale
    tamanho = _opcoes._opcao('hud_tamanho_rotulo') * escala
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    rotulos = []
    try:
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(1.0)
        shader.bind()
        if arraste is None:
            # a face da parede, discreta (no arraste ela vem acesa)
            pares = _segmentos_na_tela(guias['contorno'], tela)
            if pares:
                shader.uniform_float('color', (*realce[:3], 0.35))
                batch_for_shader(shader, 'LINES', {'pos': pares}).draw(shader)
        gpu.state.line_width_set(2.0)
        for lado in LADOS:
            a3, b3 = guias['linhas'][lado]
            a, b = tela(a3), tela(b3)
            if a is None or b is None:
                continue
            aceso = _hover_guia[0] == lado or (
                _edicao_guia[0] is not None and _edicao_guia[0]['lado'] == lado)
            shader.uniform_float('color', (1.0, 1.0, 1.0, 1.0) if aceso else realce)
            linha = b - a
            perpendicular = (Vector((-linha.y, linha.x)).normalized() * 5 * escala
                             if linha.length > 1 else Vector((0, 0)))
            batch_for_shader(shader, 'LINES', {'pos': [
                a, b, a - perpendicular, a + perpendicular,
                b - perpendicular, b + perpendicular]}).draw(shader)
            texto = _texto_do_valor(lado, guias['valores'][lado])
            blf.size(0, tamanho)
            largura, altura = blf.dimensions(0, texto)[0], blf.dimensions(0, '0')[1]
            meio = (a + b) / 2.0
            x, y = meio.x - largura / 2.0, meio.y - altura / 2.0
            _hud._caixa_texto_hud(x, y, texto, tamanho, escala)
            shader.bind()
            folga = 4 * escala
            mm_por_px = ((b3 - a3).length * 1000.0 / linha.length
                         if linha.length > 1 else 1.0)
            # arrastar no sentido parede -> modulo AUMENTA a distancia
            rotulos.append((lado, x - folga, y - folga, x + largura + folga,
                            y + altura + folga,
                            linha.normalized() if linha.length > 1 else Vector((1, 0)),
                            mm_por_px))
    except Exception as e:
        print("[Cabinet Creator] guias da parede:", e)
    finally:
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')
    _rotulos[regiao.as_pointer()] = rotulos


def _segmentos_na_tela(segmentos, tela):
    pares = []
    for a, b in segmentos:
        a2, b2 = tela(a), tela(b)
        if a2 is not None and b2 is not None:
            pares += [a2, b2]
    return pares


def _na_tela_em_lote(regiao, rv3d, pontos):
    """`location_3d_to_region_2d` em lote (numpy); None se algum ponto
    fica atras da camera. A parede de uma casa real tem milhares de
    triangulos: um a um, o desenho travava."""
    if not len(pontos):
        return None
    pm = np.array(rv3d.perspective_matrix, dtype=np.float64)
    h = np.c_[pontos, np.ones(len(pontos))] @ pm.T
    if (h[:, 3] <= 1e-9).any():
        return None
    xy = h[:, :2] / h[:, 3:4]
    return np.stack(((1 + xy[:, 0]) * regiao.width / 2,
                     (1 + xy[:, 1]) * regiao.height / 2), axis=1).astype(np.float32)


def _desenhar_face_alvo(arraste, tela, realce, regiao, rv3d):
    """A face que vai receber o modulo: veu translucido e contorno
    grosso na cor de realce."""
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    try:
        gpu.state.blend_set('ALPHA')
        shader.bind()
        triangulos = _na_tela_em_lote(regiao, rv3d, arraste['triangulos'])
        if triangulos is not None:
            shader.uniform_float('color', (*realce[:3], 0.18))
            batch_for_shader(shader, 'TRIS', {'pos': triangulos}).draw(shader)
        pares = _segmentos_na_tela(arraste['contorno'], tela)
        if pares:
            gpu.state.line_width_set(3.0)
            shader.uniform_float('color', (*realce[:3], 1.0))
            batch_for_shader(shader, 'LINES', {'pos': pares}).draw(shader)
    except Exception as e:
        print("[Cabinet Creator] realce da parede:", e)
    finally:
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')


def rotulo_sob(context, posicao):
    x, y = posicao
    for rotulo in _rotulos.get(context.region.as_pointer(), ()):
        if rotulo[1] <= x <= rotulo[3] and rotulo[2] <= y <= rotulo[4]:
            return rotulo
    return None


# ------------------------------------------------------ arraste (direito)
def _raio_ignorando(context, regiao, rv3d, coord, ignorar):
    """(objeto, ponto, normal, face) do 1o acerto fora de `ignorar`.

    O modulo encostado tem as costas NO plano da parede: pular o acerto
    nele (andando 0,1 mm) atravessava a face da parede e pegava o outro
    lado dela ou nada -- o modulo piscava e, solto, "nao era parede"
    (relato do usuario). Achado o objeto, o raio e' refeito so' contra
    ele, da camera: a 1a face DELE, com o indice exato."""
    inicio = view3d_utils.region_2d_to_origin_3d(regiao, rv3d, coord)
    direcao = view3d_utils.region_2d_to_vector_3d(regiao, rv3d, coord)
    return raio_ate_parede(context, inicio, direcao, ignorar)


def raio_ate_parede(context, inicio, direcao, ignorar):
    """O mesmo, com o raio em mundo (sem a tela: o teste usa)."""
    inicio, direcao = Vector(inicio), Vector(direcao).normalized()
    dep = context.evaluated_depsgraph_get()
    s=_paredes_edicao._sessao[0]
    if s and s.get('recorte_explicito') and _paredes_edicao.ativa(context):
        exibicao=bpy.data.objects.get(s.get('exibicao',''))
        fonte=_paredes_selecao.fonte_da_exibicao(exibicao)
        if fonte is None or fonte.name in ignorar:
            return None
        inversa=exibicao.matrix_world.inverted_safe()
        ok,p,n,_indice=exibicao.ray_cast(inversa@inicio,(inversa.to_3x3()@direcao).normalized(),depsgraph=dep)
        if not ok:
            return None
        return fonte,exibicao.matrix_world@p,Vector(s['normal']),s['face']
    origem = inicio
    for _vez in range(32):
        acertou, ponto, normal, face, obj, _m = context.scene.ray_cast(
            dep, origem, direcao)
        if not acertou or obj is None:
            return None
        original = obj.original
        fonte=_paredes_selecao.fonte_da_exibicao(original)
        if fonte is not None:
            return fonte,ponto,normal,int(original.get('parede_origem_face',0))
        if original.name in ignorar:
            origem = ponto + direcao * 1e-4
            continue
        if original.type == 'MESH':
            inversa = original.matrix_world.inverted_safe()
            ok, local, normal_local, face_local = original.ray_cast(
                inversa @ inicio, (inversa.to_3x3() @ direcao).normalized(),
                depsgraph=dep)
            if ok:
                mundo = original.matrix_world
                ponto = mundo @ local
                normal = (mundo.to_3x3().inverted_safe().transposed()
                          @ normal_local).normalized()
                face = face_local
        return original, ponto, normal, face
    return None


def _px_por_metro(regiao, rv3d, ponto, eixo):
    a = view3d_utils.location_3d_to_region_2d(regiao, rv3d, ponto)
    b = view3d_utils.location_3d_to_region_2d(regiao, rv3d, ponto + eixo * 0.1)
    if a is None or b is None or (b - a).length < 1e-6:
        return None
    return (b - a).length / 0.1


def posicao_no_arraste(retangulo, s, base, largura, altura, tolerancia):
    """Gruda nas pontas, no piso e no teto a menos de `tolerancia` (m)."""
    s0, s1, z0, z1 = retangulo
    if abs((s - largura / 2.0) - s0) <= tolerancia:
        s = s0 + largura / 2.0
    elif abs(s1 - (s + largura / 2.0)) <= tolerancia:
        s = s1 - largura / 2.0
    if abs(base - z0) <= tolerancia:
        base = z0
    elif abs(z1 - (base + altura)) <= tolerancia:
        base = z1 - altura
    return s, base


class OBJECT_OT_arrastar_na_parede(Operator):
    """Botao direito segurado num modulo: solte numa parede para encostar
    as costas nela e associar (clique sem arrastar abre o menu)"""
    bl_idname = 'object.cabinet_arrastar_na_parede'
    bl_label = "Associar a' Parede"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        preferencias = getattr(context.window_manager.keyconfigs.active,
                               'preferences', None)
        return (context.mode == 'OBJECT' and context.area is not None
                and context.area.type == 'VIEW_3D'
                and not _gaveta._eh_area_gaveta(context)
                # quem seleciona com o direito: o botao e' do Blender
                and getattr(preferencias, 'select_mouse', 'LEFT') != 'RIGHT')

    def invoke(self, context, event):
        _paredes_edicao.lembrar_face(context, (event.mouse_region_x, event.mouse_region_y), contexto=True)
        atingido = _hud._raio_cru(context, (event.mouse_region_x,
                                            event.mouse_region_y))
        conj = modulo_de(atingido[0]) if atingido is not None else None
        if conj is None:
            return {'PASS_THROUGH'}         # o menu de contexto de sempre
        self._modulo = conj.name
        self._ignorar = {conj.name, *(o.name for o in conj.children_recursive)}
        self._inicio = Vector((event.mouse_region_x, event.mouse_region_y))
        self._arrastou = False
        self._matriz = conj.matrix_world.copy()
        # COPIA (to_list): o array da ID prop morre no `desassociar`
        self._associacao = {k: getattr(conj[k], 'to_list', lambda: conj[k])()
                            for k in CHAVES_ASSOCIACAO if k in conj}
        self._regiao = context.region
        self._rv3d = context.region_data
        self._caixa = caixa_do_modulo(conj)
        self._parede = None
        # Solto onde nao ha' parede (o "limbo"): desassocia sem mover.
        self._limbo = False
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _restaurar(self, context):
        conj = bpy.data.objects.get(self._modulo)
        if conj is None:
            return
        conj.matrix_world = self._matriz
        desassociar(conj)
        for chave, valor in self._associacao.items():
            conj[chave] = valor
        context.view_layer.update()

    def _encerrar(self, context):
        _arraste_parede[0] = None
        try:
            context.window.cursor_modal_restore()
            context.workspace.status_text_set(None)
        except Exception:
            pass
        atualizar_guias(context)
        context.area.tag_redraw()

    def _mover(self, context, event):
        conj = bpy.data.objects.get(self._modulo)
        if conj is None or self._caixa is None:
            return
        coord = (event.mouse_region_x, event.mouse_region_y)
        acerto = _raio_ignorando(context, self._regiao, self._rv3d, coord,
                                 self._ignorar)
        dep = context.evaluated_depsgraph_get()
        regiao, motivo = None, "Arraste ate' uma parede"
        if acerto is not None:
            parede, ponto, normal, face = acerto
            if eh_movel(parede):
                motivo = "Movel nao e' parede"
            elif eixos_da_parede(normal) is None:
                motivo = "Superficie nao e' vertical (piso, teto ou tampo)"
            elif parede.type != 'MESH':
                motivo = "So' malha vira parede"
            else:
                regiao = regiao_da_parede(parede, ponto, normal, dep, face)
        if regiao is None:
            # fora de parede: o modulo volta para onde estava
            self._parede = None
            self._limbo = True
            conj.matrix_world = self._matriz
            _arraste_parede[0] = {'modulo': self._modulo, 'valido': False}
            _guias[0] = None
            if self._associacao:
                motivo = "Solte para desassociar da parede (o movel fica onde estava)"
            self._status(context, motivo)
            return
        self._limbo = False
        n, u = eixos_da_parede(normal)
        sessao = dict(parede=parede.name, regiao=regiao, ponto=tuple(ponto),
                      normal=tuple(n), u=tuple(u))
        if _paredes_edicao.ativa(context):
            atual = _paredes_edicao._sessao[0]
            if atual['parede'] == parede.name and regiao['face'] in atual['regiao']['faces']:
                sessao = atual
        px = _px_por_metro(self._regiao, self._rv3d, ponto, u)
        costas, erro = _paredes_edicao.encaixar_na_face(context, conj, ponto, sessao,
                                self._caixa, SNAP_PX / px if px else 0)
        if erro:
            self._parede = None
            self._restaurar(context)
            _arraste_parede[0] = {'modulo': self._modulo, 'valido': False}
            _guias[0] = None
            self._status(context, erro)
            return
        conj.matrix_world = matriz_na_parede(conj, costas, n, u, self._caixa)
        associar(conj, parede, costas, normal, regiao['face'])
        self._parede = parede.name
        # realce da FACE que vai receber o modulo (pedido do usuario)
        frente = n * DESLOCAMENTO_GUIA_M
        _arraste_parede[0] = {
            'modulo': self._modulo, 'valido': True,
            'contorno': [(a + frente, b + frente) for a, b in regiao['contorno']],
            'triangulos': regiao['triangulos'] + np.array(frente, dtype=np.float32)}
        context.view_layer.update()
        _guias[0] = calcular_guias(conj, dep)
        self._status(context, "Solte para associar a' parede %s (face %d)"
                     % (parede.name, regiao['face']))

    def _status(self, context, texto):
        try:
            context.workspace.status_text_set(texto + " | Roda: trocar a face | Esc: cancelar")
        except Exception:
            pass

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            if not self._arrastou:
                if (mouse - self._inicio).length < LIMIAR_ARRASTE_PX:
                    return {'RUNNING_MODAL'}
                self._arrastou = True
                context.window.cursor_modal_set('HAND')
            self._mover(context, event)
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        passos = passos_da_roda(event)
        if passos and self._arrastou:
            conj = bpy.data.objects.get(self._modulo)
            if conj is not None:
                girar_costas(conj, passos)
                self._caixa = caixa_do_modulo(conj)
                self._mover(context, event)
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'RIGHTMOUSE' and event.value == 'RELEASE':
            if not self._arrastou:
                # clique simples: o menu de contexto, como sempre (no
                # SOLTAR: no PRESS o release responderia a 1a opcao)
                self._encerrar(context)
                bpy.ops.wm.call_menu('INVOKE_DEFAULT',
                                     name='VIEW3D_MT_object_context_menu')
                return {'CANCELLED'}
            self._mover(context, event)
            if self._parede is None and self._limbo and self._associacao:
                # Pedido do usuario: arrastar para fora de qualquer parede
                # solta a associacao; o movel fica na posicao de origem.
                self._restaurar(context)
                desassociar(bpy.data.objects[self._modulo])
                self._encerrar(context)
                self.report({'INFO'}, "Modulo desassociado da parede")
                return {'FINISHED'}
            if self._parede is None:
                self._restaurar(context)
                self._encerrar(context)
                self.report({'WARNING'}, "Solte o modulo sobre uma parede")
                return {'CANCELLED'}
            # O ultimo modulo solto e' a referencia do proximo duplo clique.
            _paredes_edicao.registrar_posicionado(context, bpy.data.objects[self._modulo])
            self._encerrar(context)
            self.report({'INFO'}, "Modulo associado a' parede %s" % self._parede)
            return {'FINISHED'}
        if (event.type == 'ESC' and event.value == 'PRESS') or (
                event.type == 'LEFTMOUSE' and event.value == 'PRESS'):
            self._restaurar(context)
            self._encerrar(context)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._restaurar(context)
        self._encerrar(context)


# ------------------------------------------------- editar uma guia
class OBJECT_OT_guia_parede(Operator):
    """Distancia do modulo a' parede: arraste de lado para mudar, clique
    para digitar"""
    bl_idname = 'object.cabinet_guia_parede'
    bl_label = "Distancia a' Parede"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    @classmethod
    def poll(cls, context):
        return _hud._contexto_hud(context) and _guias[0] is not None

    def invoke(self, context, event):
        rotulo = rotulo_sob(context, (event.mouse_region_x, event.mouse_region_y))
        conj = bpy.data.objects.get(_guias[0]['modulo']) if _guias[0] else None
        if rotulo is None or conj is None:
            return {'CANCELLED'}
        self._lado, self._direcao, self._mm_por_px = rotulo[0], rotulo[5], rotulo[6]
        self._modulo = conj.name
        self._matriz = conj.matrix_world.copy()
        self._ponto = tuple(conj[CHAVE_PAREDE_PONTO])
        self._valor = _guias[0]['valores'][self._lado]
        self._inicio = Vector((event.mouse_region_x, event.mouse_region_y))
        self._arrastou = False
        self._area = context.area
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _aplicar(self, context, valor):
        conj = bpy.data.objects.get(self._modulo)
        if conj is None:
            return
        dep = context.evaluated_depsgraph_get()
        aplicar_guia(conj, self._lado, valor, dep)
        context.view_layer.update()
        _guias[0] = calcular_guias(conj, dep)
        self._area.tag_redraw()

    def _restaurar(self, context):
        conj = bpy.data.objects.get(self._modulo)
        if conj is not None:
            conj.matrix_world = self._matriz
            conj[CHAVE_PAREDE_PONTO] = self._ponto
            context.view_layer.update()
        _edicao_guia[0] = None
        atualizar_guias(context)
        self._area.tag_redraw()

    def cancel(self, context):
        self._restaurar(context)

    def _digitar(self, context, event):
        estado = _edicao_guia[0]
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self._restaurar(context)
            return {'CANCELLED'}
        if event.type in {'RET', 'NUMPAD_ENTER', 'LEFTMOUSE'}:
            try:
                valor = _gaveta_desenho._ler_medida_digitada(estado['texto']) * 1000.0
            except (ValueError, TypeError) as erro:
                self.report({'WARNING'}, str(erro))
                return {'RUNNING_MODAL'}
            _edicao_guia[0] = None
            self._aplicar(context, valor)
            return {'FINISHED'}
        entrada = (context.window_manager.clipboard
                   if event.ctrl and event.type == 'V'
                   else '' if event.ctrl else event.unicode or '')
        if _gaveta_desenho._tecla_no_texto(estado, event.type, entrada, event.ctrl):
            self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if _edicao_guia[0] is not None:
            return self._digitar(context, event)
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._restaurar(context)
            return {'CANCELLED'}
        mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self._arrastou:
                return {'FINISHED'}
            # clique sem arrastar: digita a distancia (Enter confirma)
            texto = _opcoes._numero_na_unidade(self._valor)
            _edicao_guia[0] = {'lado': self._lado, 'texto': texto,
                               'cursor': len(texto), 'selecionado': True}
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE':
            if not self._arrastou:
                if (mouse - self._inicio).length < LIMIAR_ARRASTE_PX:
                    return {'RUNNING_MODAL'}
                self._arrastou = True
            delta = (mouse - self._inicio).dot(self._direcao) * self._mm_por_px
            self._aplicar(context, max(0.0, self._valor + delta))
        return {'RUNNING_MODAL'}


class OBJECT_OT_desassociar_parede(Operator):
    """Solta os modulos selecionados da parede (ficam onde estao)"""
    bl_idname = 'object.cabinet_desassociar_parede'
    bl_label = 'Desassociar da Parede'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        modulos = {modulo_de(o) for o in context.selected_objects} - {None}
        soltos = [m for m in modulos if m.get(CHAVE_PAREDE)]
        if not soltos:
            self.report({'WARNING'}, "Nenhum modulo associado a parede na selecao")
            return {'CANCELLED'}
        for conj in soltos:
            desassociar(conj)
        atualizar_guias(context)
        return {'FINISHED'}


# --------------------------------------------- gizmo dos numeros
class VIEW3D_GT_guia_parede(Gizmo):
    """Pick dos numeros das guias (o desenho e' da HUD): o clique neles
    ganha da selecao, que e' keymap."""
    bl_idname = 'VIEW3D_GT_guia_parede'

    def draw(self, context):
        pass

    def test_select(self, context, location):
        rotulo = rotulo_sob(context, location)
        lado = rotulo[0] if rotulo is not None else None
        if lado != _hover_guia[0]:
            _hover_guia[0] = lado
            context.area.tag_redraw()
        return 0 if rotulo is not None else -1


class VIEW3D_GGT_guias_parede(GizmoGroup):
    bl_idname = 'VIEW3D_GGT_guias_parede'
    bl_label = 'Guias da parede Cabinet Creator'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        return _hud._contexto_hud(context) and _guias[0] is not None

    def setup(self, context):
        self.guia = self.gizmos.new('VIEW3D_GT_guia_parede')
        self.guia.use_tooltip = False
        self.guia.target_set_operator('object.cabinet_guia_parede')


def esquecer():
    """Undo/abrir: nada guardado aponta para dado velho."""
    _conferidos.clear()
    _retangulos.clear()
    _guias[0] = None
    _rotulos.clear()
    _hover_guia[0] = None
    _edicao_guia[0] = None
    _arraste_parede[0] = None
