"""Formas de PLANTA: o modulo que nao e' caixa -- canto em L (RECORTE),
diagonal (CHANFRO) e curvo (CURVA) -- lido da propria geometria e editado
pela HUD: a profundidade de CADA lado (P1/P2), o raio R e as medidas
totais (L/P) sem deformar o canto.

A forma nao fica gravada: sai das pecas a cada mudanca (como as medidas
L/A/P). Cada quina da caixa e' medida andando da quina para dentro ate'
a primeira peca: recuo constante = recorte, linear = diagonal, que cai
rapido = curva.
"""

import math

import bpy
from mathutils import Matrix, Vector
from mathutils.geometry import convex_hull_2d

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _modulos = _portas = None

# Recuo menor que isto numa quina e' folga de porta/fita, nao forma
TOL_FORMA_MM = 30.0
# Recorte em L: o braco que falta. Menor que isto e' a quina de tras
# aberta (passagem de cano), nao muda o desenho nem ganha medida
RECORTE_MINIMO_MM = 100.0
# Faixa em volta da face interna que anda junto com ela: porta,
# travessa e a ponta das pecas que chegam nela
FAIXA_MM = 100.0
# Peca cortada pelo plano do esticar mais fina que isto anda inteira
RIGIDA_MM = 60.0
# Na diagonal, o que esta' ate' esta distancia do lado anda inteiro (a
# lateral nao entorta); dali ate' a outra ponta, cada vez menos
MARGEM_CHANFRO_MM = 30.0
SEGMENTOS_ARCO = 16
MENOR_LADO_MM = 50.0      # nenhuma edicao deixa um lado menor que isto
# A diagonal do lado inteiro: sobra ate' isto = a quina AFIADA (vai ate'
# ela); mais = a ponta acaba na ESPESSURA de uma chapa (a prateleira da
# cantoneira encosta na face de dentro da lateral), e o trecho que sobra,
# ate' ESPESSURA_PONTA_MM, e' so' contorno (a ponta da chapa, sem medida)
PONTA_AFIADA_MM = 3.0
ESPESSURA_PONTA_MM = 40.0
# Peca curva do Promob (porta/painel em arco): nao e' chapa, mas deforma
# junto com a forma (gravado no .blend)
MARCA_CURVA = "eh_peca_curva"

# Quinas da caixa em ordem anti-horaria: (sinal em X, sinal em Y)
QUINAS = ((-1, -1), (1, -1), (1, 1), (-1, 1))

_cache = {}     # nome do modulo -> (assinatura, forma)


def esquecer():
    _cache.clear()


def matriz_do_modulo(conj):
    loc, rot, _escala = conj.matrix_world.decompose()
    return Matrix.LocRotScale(loc, rot, Vector((1.0, 1.0, 1.0)))


def _pecas(conj):
    """Chapas da caixa e pecas curvas: o que desenha a planta."""
    return [o for o in conj.children if o.type == 'MESH' and (
        (_chapas.MARCA_CHAPA in o and not _chapas.eh_dependente(o))
        or MARCA_CURVA in o)]


def _assinatura(conj, pecas):
    def matriz(m):
        return tuple(round(v, 6) for linha in m for v in linha)
    return (matriz(conj.matrix_world),) + tuple(
        (o.name, matriz(o.matrix_world), len(o.data.vertices),
         round(getattr(o, 'chapa_largura_mm', 0.0), 3),
         round(getattr(o, 'chapa_comprimento_mm', 0.0), 3)) for o in pecas)


def _planta(conj, pecas):
    """(poligonos 2D, lo, hi) em mm no referencial do modulo. Chapa
    deitada entra com o contorno de verdade (recorte, curva); o resto,
    com o casco convexo da projecao."""
    inversa = matriz_do_modulo(conj).inverted()
    poligonos, todos = [], []
    for o in pecas:
        mundo = inversa @ o.matrix_world
        pts = [mundo @ v.co * 1000.0 for v in o.data.vertices]
        if not pts:
            continue
        todos += pts
        eixo_z = (mundo.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
        faces = []
        if _chapas.MARCA_CHAPA in o and abs(eixo_z.z) > 0.99:
            faces = [[(pts[i].x, pts[i].y) for i in f.vertices]
                     for f in o.data.polygons if f.normal.z > 0.99]
        if not faces:
            planos = [(p.x, p.y) for p in pts]
            faces = [[planos[i] for i in convex_hull_2d(planos)]]
        poligonos += faces
    if not todos:
        return None
    lo = Vector([min(p[i] for p in todos) for i in range(3)])
    hi = Vector([max(p[i] for p in todos) for i in range(3)])
    return poligonos, lo, hi


def _cortes(poligonos, eixo, valor):
    """Onde a reta (coordenada `eixo` = valor) cruza as bordas: a OUTRA
    coordenada de cada cruzamento."""
    outro = 1 - eixo
    saida = []
    for pol in poligonos:
        for i in range(len(pol)):
            a, b = pol[i - 1], pol[i]
            da, db = a[eixo] - valor, b[eixo] - valor
            if da == db:
                if da == 0:
                    saida += [a[outro], b[outro]]
                continue
            if da * db <= 0:
                f = da / (da - db)
                saida.append(a[outro] + f * (b[outro] - a[outro]))
    return saida


def _recuo(poligonos, lo, hi, k, eixo, t):
    """Distancia (mm) da quina k ate' a primeira peca andando ao longo
    de `eixo`, numa reta a `t` mm do lado da caixa."""
    sx, sy = QUINAS[k]
    if eixo == 0:
        y = hi.y - t if sy > 0 else lo.y + t
        xs = _cortes(poligonos, 1, y)
        if not xs:
            return hi.x - lo.x
        return max(0.0, hi.x - max(xs) if sx > 0 else min(xs) - lo.x)
    x = hi.x - t if sx > 0 else lo.x + t
    ys = _cortes(poligonos, 0, x)
    if not ys:
        return hi.y - lo.y
    return max(0.0, hi.y - max(ys) if sy > 0 else min(ys) - lo.y)


def _feicao(poligonos, lo, hi, k):
    """O que falta na quina k: None ou {'tipo', 'a' (perna em X), 'b'
    (perna em Y)}. Na metade da perna b o recuo e' ~a no recorte, ~a/2
    na diagonal e ~0.13a na curva (quarto de circulo)."""
    a = _recuo(poligonos, lo, hi, k, 0, 1.0)
    b = _recuo(poligonos, lo, hi, k, 1, 1.0)
    largura, fundo = hi.x - lo.x, hi.y - lo.y
    inteira_a, inteira_b = a > largura - TOL_FORMA_MM, b > fundo - TOL_FORMA_MM
    if a < TOL_FORMA_MM or b < TOL_FORMA_MM:
        return None
    meio = _recuo(poligonos, lo, hi, k, 0, b / 2.0)
    if inteira_a or inteira_b:
        # a DIAGONAL que toma o lado inteiro (cantoneira, modulo de ponta:
        # pedido do usuario, a linha branca seguia a caixa) -- ou os dois
        # (modulo triangular): so' chanfro, com a perna do lado inteiro ate'
        # a outra quina se ela for afiada
        if not 0.3 * a <= meio <= 0.75 * a:
            return None
        if inteira_a and largura - a <= PONTA_AFIADA_MM:
            a = largura
        if inteira_b and fundo - b <= PONTA_AFIADA_MM:
            b = fundo
        return {'tipo': 'CHANFRO', 'a': a, 'b': b}
    if meio > 0.75 * a:
        # o fundo do recorte (porta, travessa), nao a ponta do outro braco
        b = _recuo(poligonos, lo, hi, k, 1, a / 2.0)
        if min(meio, b) < RECORTE_MINIMO_MM:
            return None
        return {'tipo': 'RECORTE', 'a': meio, 'b': b}
    if meio >= 0.3 * a:
        return {'tipo': 'CHANFRO', 'a': a, 'b': b}
    # O arco sai TANGENTE ao lado: perto dele o recuo ja' e' bem menor que
    # o raio e o segmento reto do poligono pesa demais (12 segmentos davam
    # +4 mm). Do circulo, (R - f)^2 = 2Rt - t^2: medido a 1/4 e 1/2 da
    # perna, la' dentro do arco, nos dois lados.
    amostras = []
    for eixo, perna in ((0, b), (1, a)):
        for fracao in (0.25, 0.5):
            t = perna * fracao
            f = _recuo(poligonos, lo, hi, k, eixo, t)
            amostras.append((f + t) + math.sqrt(2.0 * f * t))
    raio = sum(amostras) / len(amostras)
    return {'tipo': 'CURVA', 'a': raio, 'b': raio}


def forma_do_modulo(conj):
    """{'lo', 'hi' (mm, referencial do modulo), 'cantos': [4 x feicao]}
    ou None quando o modulo e' uma caixa."""
    if conj is None or _chapas.MARCA_CONJUNTO not in conj:
        return None
    pecas = _pecas(conj)
    if len(pecas) < 2:
        return None
    assinatura = _assinatura(conj, pecas)
    guardado = _cache.get(conj.name)
    if guardado is not None and guardado[0] == assinatura:
        return guardado[1]
    forma = None
    planta = _planta(conj, pecas)
    if planta is not None:
        poligonos, lo, hi = planta
        cantos = [_feicao(poligonos, lo, hi, k) for k in range(4)]
        if any(cantos):
            forma = {'lo': lo, 'hi': hi, 'cantos': cantos}
    _cache[conj.name] = (assinatura, forma)
    return forma


# ------------------------------------------------------------ contorno
def _quina(forma, k):
    sx, sy = QUINAS[k]
    lo, hi = forma['lo'], forma['hi']
    return (hi.x if sx > 0 else lo.x), (hi.y if sy > 0 else lo.y)


def _pontos_do_canto(forma, k):
    """[(x, y, sobe)] do canto k em ordem anti-horaria; `sobe` = tem
    aresta vertical (nao nos pontos do meio do arco)."""
    sx, sy = QUINAS[k]
    xc, yc = _quina(forma, k)
    f = forma['cantos'][k]
    if f is None:
        return [(xc, yc, True)]
    a, b = f['a'], f['b']
    px, py = (xc - sx * a, yc), (xc, yc - sy * b)
    x_antes = sx * sy < 0          # chega pelo lado horizontal
    primeiro, segundo = (px, py) if x_antes else (py, px)
    if f['tipo'] == 'RECORTE':
        return [(*primeiro, True), (xc - sx * a, yc - sy * b, True),
                (*segundo, True)]
    if f['tipo'] == 'CHANFRO':
        return [(*primeiro, True), (*segundo, True)]
    cx, cy = xc - sx * a, yc - sy * b
    pontos = []
    for i in range(SEGMENTOS_ARCO + 1):
        t = i / SEGMENTOS_ARCO
        angulo = (1.0 - t if x_antes else t) * math.pi / 2.0
        pontos.append((cx + sx * a * math.cos(angulo),
                       cy + sy * b * math.sin(angulo),
                       i in (0, SEGMENTOS_ARCO)))
    return pontos


def contorno(forma):
    """Pontos da planta [(x, y, sobe)] em ordem anti-horaria."""
    return [p for k in range(4) for p in _pontos_do_canto(forma, k)]


def segmentos(forma):
    """Arestas da planta: {'a', 'b', 'chave', 'letra', 'direcao',
    'cantos'}. `chave` None = so' contorno. Lado inteiro = L ou P total
    (de min para max, `cantos` = quinas da caixa); lado que chega num
    recorte/diagonal = P1 (vertical) ou P2 (horizontal), de `a` (ponta
    de fora) para `b` (a que anda); diagonal e curva = R."""
    pontos = [_pontos_do_canto(forma, k) for k in range(4)]
    saida = []
    for k in range(4):
        f = forma['cantos'][k]
        sx, sy = QUINAS[k]
        for p, q in zip(pontos[k], pontos[k][1:]):
            if (Vector(p[:2]) - Vector(q[:2])).length < 1.0:
                continue
            seg = {'a': p[:2], 'b': q[:2], 'chave': None, 'letra': None,
                   'direcao': None, 'cantos': None}
            if f['tipo'] in ('CHANFRO', 'CURVA'):
                raiz = math.sqrt(0.5)
                seg.update(chave=('R', k), letra='R',
                           direcao=(-sx * raiz, -sy * raiz))
            saida.append(seg)
        j = (k + 1) % 4
        g = forma['cantos'][j]
        p, q = pontos[k][-1][:2], pontos[j][0][:2]
        if (Vector(p) - Vector(q)).length < 1.0:
            continue                # a diagonal tomou o lado inteiro
        horizontal = k in (0, 2)
        seg = {'a': p, 'b': q, 'chave': None, 'letra': None,
               'direcao': None, 'cantos': None}
        if f is None and g is None:
            eixo = 0 if horizontal else 1
            a, b = sorted((p, q), key=lambda c: c[eixo])
            if horizontal:
                nivel = 0 if k == 0 else 2
                cantos = (nivel, nivel + 1)
            else:
                cantos = (1, 3) if k == 1 else (0, 2)
            seg.update(a=a, b=b, chave=('L',) if horizontal else ('P',),
                       letra='L' if horizontal else 'P', cantos=cantos)
        elif (f is None) != (g is None):
            com, kc = (f, k) if f is not None else (g, j)
            if (com['tipo'] in ('RECORTE', 'CHANFRO')
                    and (Vector(p) - Vector(q)).length > ESPESSURA_PONTA_MM):
                # (mais curto e' a ponta da chapa onde a diagonal acaba)
                fora, dentro = (q, p) if f is not None else (p, q)
                letra = 'P2' if horizontal else 'P1'
                seg.update(a=fora, b=dentro, chave=(letra, kc), letra=letra)
        saida.append(seg)
    return saida


def valor(conj, chave):
    """Medida (mm) que a linha `chave` da HUD mostra."""
    forma = forma_do_modulo(conj)
    if forma is None:
        raise ValueError("O modulo nao tem mais esse formato")
    if chave[0] == 'L':
        return forma['hi'].x - forma['lo'].x
    if chave[0] == 'P':
        return forma['hi'].y - forma['lo'].y
    if chave[0] == 'R':
        f = forma['cantos'][chave[1]]
        if f is None:
            raise ValueError("O canto nao tem mais diagonal nem curva")
        return (f['a'] + f['b']) / 2.0
    if chave[0] == 'ANG':
        # angulo da diagonal com o lado da FRENTE (o da perna a)
        f = forma['cantos'][chave[1]]
        if f is None or f['tipo'] != 'CHANFRO':
            raise ValueError("O canto nao tem mais diagonal")
        return math.degrees(math.atan2(f['b'], f['a']))
    for seg in segmentos(forma):
        if seg['chave'] == tuple(chave):
            return (Vector(seg['a']) - Vector(seg['b'])).length
    raise ValueError("O modulo nao tem mais essa medida")


# ------------------------------------------------------------- edicao
def _no_canto(forma, k, p):
    """(X', Y'): coordenadas a partir da quina k, para dentro."""
    sx, sy = QUINAS[k]
    xc, yc = _quina(forma, k)
    return sx * (xc - p.x), sy * (yc - p.y)


def _reajustar(o, era_caixa, cima):
    """Chapa com vertices mexidos volta a' convencao: malha centrada na
    origem e L/C nas props. Caixa que entortou (porta diagonal com uma
    ponta movida) e' refeita: gira em volta da vertical e estica."""
    malha = o.data
    if era_caixa and not _chapas._malha_e_caixa(malha):
        _refazer_caixa(o, cima)
        return
    vs = malha.vertices
    lo = Vector([min(v.co[i] for v in vs) for i in range(3)])
    hi = Vector([max(v.co[i] for v in vs) for i in range(3)])
    centro = (lo + hi) / 2.0
    if centro.length > 1e-9:
        malha.transform(Matrix.Translation(-centro))
        o.matrix_world = o.matrix_world @ Matrix.Translation(centro)
    _chapas._ocupado[0] = True
    try:
        o.chapa_largura_mm = (hi.x - lo.x) * 1000.0
        o.chapa_comprimento_mm = (hi.y - lo.y) * 1000.0
    finally:
        _chapas._ocupado[0] = False
    malha.update()


def _refazer_caixa(o, cima):
    rot = o.matrix_world.to_3x3().normalized()
    eixos = [rot.col[i].normalized() for i in range(3)]
    vertical = max(range(3), key=lambda i: abs(eixos[i].dot(cima)))
    medidas = (o.chapa_largura_mm, o.chapa_comprimento_mm, o.chapa_espessura_mm)
    longo = max((i for i in range(3) if i != vertical), key=lambda i: medidas[i])
    if longo == 2:
        return
    mundo = o.matrix_world
    mais = [mundo @ v.co for v in o.data.vertices if v.co[longo] > 0]
    menos = [mundo @ v.co for v in o.data.vertices if v.co[longo] < 0]
    if not mais or not menos:
        return
    d = sum(mais, Vector()) / len(mais) - sum(menos, Vector()) / len(menos)
    d -= cima * d.dot(cima)
    velho = eixos[longo] - cima * eixos[longo].dot(cima)
    if d.length < 1e-6 or velho.length < 1e-6:
        return
    angulo = math.atan2(cima.dot(velho.cross(d)), velho.dot(d))
    nova = Matrix.Rotation(angulo, 3, cima) @ rot
    centro = sum((mundo @ v.co for v in o.data.vertices), Vector()) / len(o.data.vertices)
    _chapas._ocupado[0] = True
    try:
        setattr(o, ('chapa_largura_mm', 'chapa_comprimento_mm')[longo],
                d.length * 1000.0)
    finally:
        _chapas._ocupado[0] = False
    o.matrix_world = Matrix.LocRotScale(centro, nova.to_quaternion(),
                                        Vector((1.0, 1.0, 1.0)))
    o.data.clear_geometry()
    _chapas.gerar_malha_chapa(o)       # malha vazia nasce caixa


def _deformar(conj, desloc, rigida=None):
    """Aplica `desloc(p) -> Vector` (mm, referencial do modulo) a cada
    vertice das pecas. `rigida(pts, deslocs)` pode devolver UM
    deslocamento para a peca inteira (anda sem esticar). Acessorio comum
    anda inteiro pelo deslocamento do proprio centro."""
    matriz = matriz_do_modulo(conj)
    inversa = matriz.inverted()
    giro = matriz.to_3x3()
    cima = giro.col[2].normalized()
    pecas = _pecas(conj)
    for o in pecas + [o for o in conj.children if o not in pecas
                      and _chapas.MARCA_ACESSORIO in o]:
        mundo = o.matrix_world.copy()
        if o.type != 'MESH' or o not in pecas:
            centro = sum((inversa @ (mundo @ Vector(c)) for c in o.bound_box),
                         Vector()) / 8.0 * 1000.0
            d = desloc(centro)
            if d.length > 1e-6:
                o.matrix_world = Matrix.Translation(giro @ d / 1000.0) @ mundo
            continue
        para_modulo = inversa @ mundo
        pts = [para_modulo @ v.co * 1000.0 for v in o.data.vertices]
        deslocs = [desloc(p) for p in pts]
        inteira = rigida(pts, deslocs) if rigida is not None else None
        if inteira is not None:
            deslocs = [inteira] * len(pts)
        if all(d.length < 1e-6 for d in deslocs):
            continue
        if all((d - deslocs[0]).length < 1e-6 for d in deslocs):
            o.matrix_world = Matrix.Translation(giro @ deslocs[0] / 1000.0) @ mundo
            continue
        if o.data.users > 1:
            o.data = o.data.copy()
        era_caixa = _chapas._malha_e_caixa(o.data)
        volta = para_modulo.inverted()
        for v, p, d in zip(o.data.vertices, pts, deslocs):
            v.co = volta @ ((p + d) / 1000.0)
        o.data.update()
        if _chapas.MARCA_CHAPA in o:
            _reajustar(o, era_caixa, cima)
    bpy.context.view_layer.update()


def _rigida_na_faixa(forma, k, eixo, centro, faixa=FAIXA_MM):
    """Peca INTEIRA na faixa da face que anda (travessa, porta da frente
    do braco) vai junto sem esticar, mesmo a parte que entra no outro
    braco."""
    def rigida(pts, deslocs):
        if not any(d.length > 1e-6 for d in deslocs):
            return None
        coords = [_no_canto(forma, k, p)[eixo] for p in pts]
        if min(coords) >= centro - faixa and max(coords) <= centro + faixa:
            return max(deslocs, key=lambda d: d.length)
        return None
    return rigida


def _mover_perna(conj, forma, k, perna, variacao):
    """Aumenta a perna `perna` ('a' em X, 'b' em Y) da feicao da quina k
    em `variacao` mm: a face interna (ou a ponta da diagonal) anda para
    dentro do modulo; o outro braco fica onde esta'."""
    f = forma['cantos'][k]
    if f is None or f['tipo'] not in ('RECORTE', 'CHANFRO'):
        return
    sx, sy = QUINAS[k]
    largura, fundo = forma['hi'].x - forma['lo'].x, forma['hi'].y - forma['lo'].y
    eixo = 0 if perna == 'a' else 1
    lado = largura if eixo == 0 else fundo
    outra = 0.0
    vizinha = forma['cantos'][_vizinha(k, eixo)]
    if vizinha is not None:
        outra = vizinha['a' if eixo == 0 else 'b']
    atual = f[perna]
    novo = min(max(atual + variacao, TOL_FORMA_MM + 5.0),
               lado - outra - MENOR_LADO_MM)
    variacao = novo - atual
    if abs(variacao) < 1e-6:
        return
    passo = Vector((-sx * variacao, 0.0, 0.0)) if eixo == 0 else \
        Vector((0.0, -sy * variacao, 0.0))
    ao_longo = f[perna]                         # onde esta' a face que anda
    largura_coluna = f['b' if eixo == 0 else 'a']
    if f['tipo'] == 'RECORTE':
        def peso(p):
            c = _no_canto(forma, k, p)
            if (ao_longo - FAIXA_MM <= c[eixo] <= ao_longo + FAIXA_MM
                    and c[1 - eixo] <= largura_coluna + FAIXA_MM):
                return 1.0
            return 0.0
    else:
        def peso(p):
            c = _no_canto(forma, k, p)
            longe, junto = c[eixo], c[1 - eixo]
            if junto > largura_coluna or longe > ao_longo + 2 * FAIXA_MM:
                return 0.0
            px = 1.0 if junto <= MARGEM_CHANFRO_MM else (
                (largura_coluna - junto) / max(largura_coluna - MARGEM_CHANFRO_MM, 1.0))
            py = 1.0 if longe <= ao_longo + FAIXA_MM else (
                (ao_longo + 2 * FAIXA_MM - longe) / FAIXA_MM)
            return max(0.0, px) * max(0.0, py)
    _deformar(conj, lambda p: passo * peso(p),
              _rigida_na_faixa(forma, k, eixo, ao_longo))


def _vizinha(k, eixo):
    """A outra quina do mesmo lado da caixa: no lado horizontal (perna a)
    ou no vertical (perna b)."""
    sx, sy = QUINAS[k]
    alvo = (-sx, sy) if eixo == 0 else (sx, -sy)
    return QUINAS.index(alvo)


def _corte(forma, eixo):
    """(posicao do plano que estica o total, folga ate' onde encolher).
    Com recorte/diagonal, o plano passa na coluna DELE (so' um braco ali:
    o outro braco nao muda de profundidade); com curva, fora dela (o arco
    nao deforma)."""
    lo, hi = forma['lo'][eixo], forma['hi'][eixo]
    colunas, ocupado = [], []
    for k, f in enumerate(forma['cantos']):
        if f is None:
            continue
        sx, sy = QUINAS[k]
        sinal = sx if eixo == 0 else sy
        perna = f['a'] if eixo == 0 else f['b']
        borda = hi if sinal > 0 else lo
        faixa = sorted((borda, borda - sinal * perna))
        ocupado.append(faixa)
        if f['tipo'] in ('RECORTE', 'CHANFRO'):
            colunas.append(faixa)
    if colunas:
        a, b = max(colunas, key=lambda c: c[1] - c[0])
        return (a + b) / 2.0, (b - a) / 2.0
    livres, inicio = [], lo
    for a, b in sorted(ocupado):
        if a > inicio:
            livres.append((inicio, a))
        inicio = max(inicio, b)
    if hi > inicio:
        livres.append((inicio, hi))
    if not livres:
        return (lo + hi) / 2.0, (hi - lo) / 4.0
    a, b = max(livres, key=lambda c: c[1] - c[0])
    return (a + b) / 2.0, (b - a) / 2.0


def _esticar_total(conj, forma, eixo, variacao, lado):
    """L (eixo 0) ou P (eixo 1) total: um plano corta o modulo e o lado
    oposto a `lado` ('min'/'max', o que fica parado) anda `variacao`."""
    corte, folga = _corte(forma, eixo)
    variacao = max(variacao, -(folga - 10.0))
    if abs(variacao) < 1e-6:
        return
    anda_max = lado != 'max'
    passo = Vector((0.0, 0.0, 0.0))
    passo[eixo] = variacao if anda_max else -variacao

    def do_lado(c):
        return c > corte if anda_max else c < corte

    def rigida(pts, deslocs):
        coords = [p[eixo] for p in pts]
        if min(coords) < corte < max(coords) and max(coords) - min(coords) < RIGIDA_MM:
            return passo if do_lado((min(coords) + max(coords)) / 2.0) else Vector()
        return None
    _deformar(conj, lambda p: passo if do_lado(p[eixo]) else Vector(), rigida)


def _mudar_raio(conj, forma, k, raio):
    """Curva: os vertices da quina vao para o arco novo, em todas as
    pecas -- prateleira, base, porta curva. Cada um anda na RADIAL e
    mantem a distancia ate' o arco: a porta curva continua com a mesma
    espessura (escalar engrossava 15 mm para 22)."""
    f = forma['cantos'][k]
    a, b = f['a'], f['b']
    limite = [forma['hi'].x - forma['lo'].x, forma['hi'].y - forma['lo'].y]
    inversa = matriz_do_modulo(conj).inverted()
    for o in _pecas(conj):
        para_modulo = inversa @ o.matrix_world
        for v in o.data.vertices:
            x, y = _no_canto(forma, k, para_modulo @ v.co * 1000.0)
            # o primeiro vertice reto depois do arco limita o raio novo
            if y <= 2.0 and x > a + 2.0:
                limite[0] = min(limite[0], x)
            if x <= 2.0 and y > b + 2.0:
                limite[1] = min(limite[1], y)
    raio = min(max(raio, TOL_FORMA_MM + 5.0), min(limite) - 2.0)
    sx, sy = QUINAS[k]

    def desloc(p):
        x, y = _no_canto(forma, k, p)
        if x > a + 0.5 or y > b + 0.5:
            return Vector()
        radial = Vector((x - a, y - b))
        if radial.length < 1e-6:
            return Vector()
        novo = Vector((raio, raio)) + radial.normalized() * (radial.length - a + raio)
        return Vector((-sx * (novo.x - x), -sy * (novo.y - y), 0.0))
    _deformar(conj, desloc)


def aplicar(context, conj, chave, novo, lado=None):
    """Leva a medida `chave` da forma a `novo` mm (arraste/digitacao da HUD)."""
    forma = forma_do_modulo(conj)
    if forma is None:
        return
    variacao = novo - valor(conj, chave)
    if abs(variacao) < 1e-4:
        return
    tipo = chave[0]
    if tipo in ('L', 'P'):
        _esticar_total(conj, forma, 0 if tipo == 'L' else 1, variacao, lado or 'min')
    elif tipo in ('P1', 'P2'):
        # lado mais comprido = perna menor
        _mover_perna(conj, forma, chave[1], 'b' if tipo == 'P1' else 'a', -variacao)
    elif tipo == 'ANG':
        # pedido do usuario: a frente do canto (P2, perna a) fica e a
        # ponta do outro lado (P1) anda ate' dar o angulo
        k = chave[1]
        f = forma['cantos'][k]
        angulo = math.radians(max(5.0, min(85.0, float(novo))))
        if (f['b'] >= forma['hi'].y - forma['lo'].y - TOL_FORMA_MM
                and f['a'] < forma['hi'].x - forma['lo'].x - TOL_FORMA_MM):
            # a diagonal toma o lado INTEIRO: ele fica, a frente anda
            _mover_perna(conj, forma, k, 'a', f['b'] / math.tan(angulo) - f['a'])
        else:
            _mover_perna(conj, forma, k, 'b', f['a'] * math.tan(angulo) - f['b'])
    elif tipo == 'R':
        k = chave[1]
        f = forma['cantos'][k]
        if f['tipo'] == 'CURVA':
            _mudar_raio(conj, forma, k, novo)
        else:
            # diagonal: as duas pernas ficam iguais ao "raio"
            _mover_perna(conj, forma, k, 'b', novo - f['b'])
            _cache.pop(conj.name, None)
            forma = forma_do_modulo(conj)
            if forma is not None and forma['cantos'][k] is not None:
                _mover_perna(conj, forma, k, 'a', novo - forma['cantos'][k]['a'])
    _cache.pop(conj.name, None)
    _modulos.reposicionar_origem(conj)
    _modulos.sincronizar_medidas_conjunto(conj)
    _portas.atualizar_portas_do_conjunto(conj)
    context.view_layer.update()
