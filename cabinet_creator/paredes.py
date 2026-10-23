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
e na base Z, frente em -Y -- as costas sao a face +Y."""

import bpy, uuid
import blf, gpu
from gpu_extras.batch import batch_for_shader
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector
from bpy.types import Gizmo, GizmoGroup, Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _portas = _ferragens = _hud = _opcoes = _gaveta = None
_gaveta_desenho = None
_paredes_edicao = None

# ID props gravadas nos .blend (nao renomear: ver invariante 2)
CHAVE_UID_PAREDE = 'cabinet_parede_uid'     # na superficie
CHAVE_PAREDE = 'parede_uid'                 # no modulo: qual parede
CHAVE_PAREDE_NOME = 'parede_nome'           # dica (Shift+D copia o UID)
CHAVE_PAREDE_PONTO = 'parede_ponto'         # costas no referencial dela
CHAVE_PAREDE_NORMAL = 'parede_normal'       # normal no referencial dela
CHAVE_PAREDE_FACE = 'parede_face'           # a FACE: indice na malha avaliada

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
_retangulos = {}        # chave da face -> `regiao_da_parede`
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


def _mapa_de_vizinhas(malha):
    """aresta (v1, v2) -> faces que a usam."""
    mapa = {}
    for poly in malha.polygons:
        for chave in poly.edge_keys:
            mapa.setdefault(chave, []).append(poly.index)
    return mapa


def _face_semente(malha, mundo, ponto, normal, face):
    """A face clicada; se o indice sumiu (malha refeita) ou nao bate mais
    com o plano, a face do plano mais perto do ponto."""
    rotacao_normal = mundo.to_3x3().inverted_safe().transposed()

    def no_plano(poly):
        return ((rotacao_normal @ poly.normal).normalized().dot(normal) >= COPLANAR_MIN
                and abs((mundo @ poly.center - ponto).dot(normal)) <= TOLERANCIA_PLANO_M)
    if face is not None and 0 <= face < len(malha.polygons) and no_plano(malha.polygons[face]):
        return face
    candidatas = [poly for poly in malha.polygons if no_plano(poly)]
    if not candidatas:
        return None
    return min(candidatas, key=lambda poly: (mundo @ poly.center - ponto).length).index


def regiao_da_parede(parede, ponto, normal, dep=None, face=None):
    """A PAREDE e' a face clicada mais as vizinhas no mesmo plano (pedido
    do usuario: associar a' FACE, nao ao objeto -- uma sala inteira num
    objeto so' tem uma parede por face). Devolve {'face' (semente),
    'retangulo' (s0, s1, z0, z1 em m: s ao longo de u a partir da origem do
    mundo, z de mundo), 'contorno' [(a, b)] e 'triangulos' em mundo} ou
    None se a superficie nao e' parede."""
    eixos = eixos_da_parede(normal)
    if eixos is None or parede is None or parede.type != 'MESH':
        return None
    _n, u = eixos
    normal = Vector(normal).normalized()
    ponto = Vector(ponto)
    origem = parede.evaluated_get(dep) if dep is not None else parede
    malha = origem.data
    mundo = parede.matrix_world
    chave = (parede.name, _assinatura(mundo), len(malha.polygons),
             len(malha.vertices), face, round(ponto.dot(normal), 4),
             tuple(round(c, 4) for c in normal))
    if chave in _retangulos:
        return _retangulos[chave]
    semente = _face_semente(malha, mundo, ponto, normal, face)
    regiao = None
    if semente is not None:
        rotacao_normal = mundo.to_3x3().inverted_safe().transposed()
        base = malha.polygons[semente]
        plano = mundo @ base.center
        vizinhas = _mapa_de_vizinhas(malha)
        faces, fila = {semente}, [semente]
        while fila:
            for chave_aresta in malha.polygons[fila.pop()].edge_keys:
                for outra in vizinhas[chave_aresta]:
                    if outra in faces:
                        continue
                    poly = malha.polygons[outra]
                    if ((rotacao_normal @ poly.normal).normalized().dot(normal) < COPLANAR_MIN
                            or abs((mundo @ poly.center - plano).dot(normal))
                            > TOLERANCIA_PLANO_M):
                        continue
                    faces.add(outra)
                    fila.append(outra)
        pontos = {i: mundo @ malha.vertices[i].co
                  for f in faces for i in malha.polygons[f].vertices}
        uso = {}
        triangulos = []
        for f in faces:
            poly = malha.polygons[f]
            for chave_aresta in poly.edge_keys:
                uso[chave_aresta] = uso.get(chave_aresta, 0) + 1
            vs = list(poly.vertices)
            for a, b in zip(vs[1:], vs[2:]):     # leque: face de parede e' convexa
                triangulos += [pontos[vs[0]], pontos[a], pontos[b]]
        regiao = {
            'face': semente,
            'faces': tuple(sorted(faces)),
            'retangulo': (min(p.dot(u) for p in pontos.values()),
                          max(p.dot(u) for p in pontos.values()),
                          min(p.z for p in pontos.values()),
                          max(p.z for p in pontos.values())),
            # aresta de uma face so' da regiao = borda da parede
            'contorno': [(pontos[a], pontos[b]) for (a, b), n in uso.items() if n == 1],
            'triangulos': triangulos,
        }
    if len(_retangulos) > 64:
        _retangulos.clear()
    _retangulos[chave] = regiao
    return regiao


def retangulo_da_parede(parede, ponto, normal, dep=None, face=None):
    """(s0, s1, z0, z1) da parede (`regiao_da_parede`), ou None."""
    regiao = regiao_da_parede(parede, ponto, normal, dep, face)
    return regiao['retangulo'] if regiao is not None else None


def caixa_do_modulo(conj):
    """(lo, hi) da caixa das chapas nos eixos do modulo, em m, ou None."""
    limites = _portas._limites_locais_modulo(conj)
    if limites is None:
        return None
    lo, hi = limites
    return lo / 1000.0, hi / 1000.0


def ponto_das_costas(conj, caixa=None):
    """Centro da base das costas do modulo, em mundo."""
    caixa = caixa or caixa_do_modulo(conj)
    if caixa is None:
        return None
    lo, hi = caixa
    return conj.matrix_world @ Vector(((lo.x + hi.x) / 2.0, hi.y, lo.z))


def matriz_na_parede(conj, costas, n, u, caixa=None):
    """Matriz de mundo do modulo com o centro da base das costas em
    `costas` e virado para fora da parede. A escala do Empty fica."""
    caixa = caixa or caixa_do_modulo(conj)
    lo, hi = caixa
    escala = conj.matrix_world.to_scale()
    local = Vector(((lo.x + hi.x) / 2.0, hi.y, lo.z))
    local = Vector((local.x * escala.x, local.y * escala.y, local.z * escala.z))
    rotacao = rotacao_na_parede(n, u)
    return (Matrix.Translation(Vector(costas) - rotacao @ local)
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
    mais, vale a face do mesmo plano mais perto (`_face_semente`)."""
    conj[CHAVE_PAREDE] = _uid_da_parede(parede)
    conj[CHAVE_PAREDE_NOME] = parede.name
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
                     CHAVE_PAREDE_NORMAL, CHAVE_PAREDE_FACE)


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
    escala = conj.matrix_world.to_scale()
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
        _desenhar_face_alvo(arraste, tela, realce)
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


def _desenhar_face_alvo(arraste, tela, realce):
    """A face que vai receber o modulo: veu translucido e contorno
    grosso na cor de realce."""
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    try:
        gpu.state.blend_set('ALPHA')
        shader.bind()
        triangulos = [tela(p) for p in arraste['triangulos']]
        if triangulos and all(p is not None for p in triangulos):
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
    origem = inicio
    for _vez in range(32):
        acertou, ponto, normal, face, obj, _m = context.scene.ray_cast(
            dep, origem, direcao)
        if not acertou or obj is None:
            return None
        original = obj.original
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
            conj.matrix_world = self._matriz
            _arraste_parede[0] = {'modulo': self._modulo, 'valido': False}
            _guias[0] = None
            self._status(context, motivo)
            return
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
            'triangulos': [p + frente for p in regiao['triangulos']]}
        context.view_layer.update()
        _guias[0] = calcular_guias(conj, dep)
        self._status(context, "Solte para associar a' parede %s (face %d)"
                     % (parede.name, regiao['face']))

    def _status(self, context, texto):
        try:
            context.workspace.status_text_set(texto + " | Esc: cancelar")
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
        if event.type == 'RIGHTMOUSE' and event.value == 'RELEASE':
            if not self._arrastou:
                # clique simples: o menu de contexto, como sempre (no
                # SOLTAR: no PRESS o release responderia a 1a opcao)
                self._encerrar(context)
                bpy.ops.wm.call_menu('INVOKE_DEFAULT',
                                     name='VIEW3D_MT_object_context_menu')
                return {'CANCELLED'}
            self._mover(context, event)
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
