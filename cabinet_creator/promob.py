"""Promob -> sistemas do add-on (pedido do usuario: "integracao, nao
importacao bruta"). O DXF do Promob so' traz SOLIDOS; aqui eles viram o
que o add-on sabe tratar: a frente com dobradica vira PORTA nativa (as
dobradicas sao as NOSSAS), a frente com caixa atras vira GAVETAS nativas
(trilho nosso), o quadro de aluminio de correr vira porta de CORRER com a
folha "Quadro de aluminio" (trilho nosso), o fundo fino e as travessas do
topo viram as pecas DEPENDENTES do modulo. Ferragem do Promob (trilho,
dobradica, puxador, cesto, eletro) nunca entra.

A COR da camada separa as pecas (levantamento dos DXF do usuario):
7 = chapa (MDF), 253 = ferragem, 254 = aluminio/vidro (quadro de correr,
cesto), 8 = puxador, 28 = acessorio de torre, 250-252 = eletro.

`planejar` e' so' conta (caixas em mm de MUNDO, frente em -Y); `aplicar`
mexe na cena. Portas/gavetas so' para frentes de pe' viradas para -Y: a
diagonal (45 graus) continua chapa -- a `formas` gira e estica ela.
"""

import bpy
from mathutils import Vector

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _modulos = _portas = _gavetas = None

COR_CHAPA = 7
COR_FERRAGEM = 253
COR_ALUMINIO = 254
# sem tabela de camadas (DXF de teste, outro exportador): tudo e' chapa
CORES_CHAPA = {COR_CHAPA, None, 0, 256}

TOL_FRENTE_MM = 3.0          # frente: a ate' 3 mm da face da frente do modulo
FRENTE_MINIMA_MM = (100.0, 60.0)   # largura, altura
DOBRADICA_MAXIMA_MM = 70.0   # peca de ferragem pequena = dobradica
ALCANCE_DOBRADICA_MM = 60.0  # atras da frente
LATERAL_GAVETA_MINIMA_MM = 150.0   # comprimento da lateral da caixa
CESTO_MINIMO_MM = (80.0, 150.0, 80.0)  # cesto aramado (cor 254): L, P, A
FOLGA_PILHA_MM = 12.0        # entre frentes da mesma pilha de gavetas
FOLGA_PAR_MM = 8.0           # entre as duas folhas de uma porta dupla
QUADRO_CORRER_MM = (18.0, 30.0)    # fundo do perfil do quadro de correr
FUNDO_MAXIMO_MM = 8.0
TRAVESSA_MAXIMA_MM = 120.0


# ------------------------------------------------------------ caixas
def peca(obj, lo, hi, eixo=None, curva=False, espessura=0.0, cor=COR_CHAPA):
    """Dados de uma peca para o plano: caixa de mundo em mm, o eixo da
    espessura (0/1/2; None = curva) e a espessura (a da curva vem a parte)."""
    return {'obj': obj, 'lo': list(lo), 'hi': list(hi), 'eixo': eixo,
            'curva': curva, 'cor': cor,
            'espessura': espessura or (hi[eixo] - lo[eixo] if eixo is not None else 0.0)}


def _tam(p, k):
    return p['hi'][k] - p['lo'][k]


def _centro(p, k):
    return (p['lo'][k] + p['hi'][k]) / 2.0


def _cruza(a, b, k, folga=0.0):
    return a['lo'][k] - folga < b['hi'][k] and b['lo'][k] - folga < a['hi'][k]


def _dentro(a, b, k, folga=0.0):
    """a cabe em b no eixo k."""
    return a['lo'][k] >= b['lo'][k] - folga and a['hi'][k] <= b['hi'][k] + folga


def _uniao(pecas):
    return {'lo': [min(p['lo'][k] for p in pecas) for k in range(3)],
            'hi': [max(p['hi'][k] for p in pecas) for k in range(3)]}


# ------------------------------------------------------------ leitura
def _dobradicas(frente, ferragens):
    """Dobradicas (ferragem pequena) que tocam a frente por tras."""
    plano = frente['hi'][1]
    return [f for f in ferragens
            if f['cor'] == COR_FERRAGEM
            and max(_tam(f, k) for k in range(3)) <= DOBRADICA_MAXIMA_MM
            and _cruza(f, frente, 0, 10.0) and _cruza(f, frente, 2, 10.0)
            and f['lo'][1] < plano + ALCANCE_DOBRADICA_MM and f['hi'][1] > plano - 5.0]


def _lado_dobradica(frente, dobradicas):
    """'ESQUERDA' | 'DIREITA' | 'CIMA' (basculante) | None."""
    largura, altura = _tam(frente, 0), _tam(frente, 2)
    xs = [_centro(d, 0) for d in dobradicas]
    zs = [_centro(d, 2) for d in dobradicas]
    if min(zs) >= frente['lo'][2] + 0.7 * altura:
        return 'CIMA'
    if max(xs) <= frente['lo'][0] + 0.3 * largura:
        return 'ESQUERDA'
    if min(xs) >= frente['hi'][0] - 0.3 * largura:
        return 'DIREITA'
    return None


def _caixa_de_gaveta(frente, corpo, costas):
    """As pecas da caixa atras da frente (laterais, contrafrente, traseira,
    fundo) ou [] se nao ha' caixa: >= 2 laterais (de pe', normal X)
    compridas, tudo DENTRO do vao atras da frente e longe das costas do
    modulo (`costas`, y mm) -- a base, as laterais e o fundo do modulo,
    que a frente inteirica cobre, nao sao da caixa."""
    x0, x1, z0, z1 = vao_atras(corpo, frente, frente['hi'][1], costas)
    vao = {'lo': [x0, 0.0, z0], 'hi': [x1, 0.0, z1]}
    pecas = [p for p in corpo
             if _dentro(p, vao, 0, 2.0) and _dentro(p, vao, 2, 2.0)
             and p['lo'][1] >= frente['lo'][1] - 1.0
             and p['hi'][1] < costas - 15.0]
    laterais = [p for p in pecas if p['eixo'] == 0
                and _tam(p, 1) >= LATERAL_GAVETA_MINIMA_MM]
    return pecas if len(laterais) >= 2 else []


ALCANCE_VAO_MM = 40.0        # chapa do vao: a ate' isto da borda da frente
ALCANCE_COSTAS_MM = 30.0     # peca da caixa do modulo: vai ate' as costas


def _estrutural(p, costas):
    """Peca da CAIXA do modulo (lateral, divisoria, base, tampo: vao ate'
    as costas) ou travessa (estreita); a caixa da gaveta nao e'."""
    return (costas is None or p['hi'][1] >= costas - ALCANCE_COSTAS_MM
            or (p['eixo'] == 2 and _tam(p, 1) <= TRAVESSA_MAXIMA_MM))


def vao_atras(corpo, caixa, plano, costas=None, alcance=None):
    """O vao (x0, x1, z0, z1) mm atras de `caixa`: as faces das chapas do
    corpo que chegam a' frente (`plano`, a face de tras das frentes) mais
    perto do centro dela, se estiverem PERTO da borda da frente. Lado sem
    chapa (gavetas embaixo de uma porta, sem travessa entre elas): a borda
    da frente menos a cobertura medida nos outros lados."""
    cx, cz = _centro(caixa, 0), _centro(caixa, 2)
    y = plano + 5.0
    tocam = [p for p in corpo if p['lo'][1] <= y <= p['hi'][1]]
    # a lateral e o fundo da caixa da GAVETA nao delimitam o vao
    tocam = [p for p in tocam if _estrutural(p, costas)]
    achados = [
        max((p['hi'][0] for p in tocam if p['hi'][0] <= cx
             and p['lo'][2] < cz < p['hi'][2]), default=None),
        min((p['lo'][0] for p in tocam if p['lo'][0] >= cx
             and p['lo'][2] < cz < p['hi'][2]), default=None),
        max((p['hi'][2] for p in tocam if p['hi'][2] <= cz
             and p['lo'][0] < cx < p['hi'][0]), default=None),
        min((p['lo'][2] for p in tocam if p['lo'][2] >= cz
             and p['lo'][0] < cx < p['hi'][0]), default=None),
    ]
    bordas = [caixa['lo'][0], caixa['hi'][0], caixa['lo'][2], caixa['hi'][2]]
    sinais = (1.0, -1.0, 1.0, -1.0)            # para DENTRO da frente
    alcance = ALCANCE_VAO_MM if alcance is None else alcance
    validos = [a if a is not None and abs(a - b) <= alcance else None
               for a, b in zip(achados, bordas)]
    cobre = [s * (v - b) if v is not None else None
             for v, b, s in zip(validos, bordas, sinais)]

    def cobertura(k):
        # a do OUTRO eixo (as gavetas cobrem igual dos 4 lados, a medida
        # dos lados); sem ela, a do lado oposto; sem nada, rente
        outros = [c for j, c in enumerate(cobre) if c is not None and j // 2 != k // 2]
        if not outros:
            outros = [c for c in cobre if c is not None]
        return sum(outros) / len(outros) if outros else 0.0
    return tuple(v if v is not None else b + s * cobertura(k)
                 for k, (v, b, s) in enumerate(zip(validos, bordas, sinais)))


def _profundidade(corpo, caixa, plano, padrao):
    """Do plano da frente ate' a 1a chapa atras (o fundo), no centro."""
    cx, cz = _centro(caixa, 0), _centro(caixa, 2)
    atras = [p['lo'][1] for p in corpo if p['eixo'] == 1
             and p['lo'][1] > plano + 50.0
             and p['lo'][0] < cx < p['hi'][0] and p['lo'][2] < cz < p['hi'][2]]
    return (min(atras) - plano) if atras else padrao


def _pilhas(gavetas):
    """Frentes de gaveta empilhadas (mesma largura, coladas) de baixo
    para cima."""
    pilhas = []
    for g in sorted(gavetas, key=lambda g: g['frente']['lo'][2]):
        f = g['frente']
        for pilha in pilhas:
            topo = pilha[-1]['frente']
            if (abs(topo['lo'][0] - f['lo'][0]) <= 5.0
                    and abs(topo['hi'][0] - f['hi'][0]) <= 5.0
                    and 0.0 <= f['lo'][2] - topo['hi'][2] <= FOLGA_PILHA_MM):
                pilha.append(g)
                break
        else:
            pilhas.append([g])
    return pilhas


def _pares(portas):
    """Portas de GIRO lado a lado (mesma altura, coladas, dobradicas para
    fora) viram UMA porta dupla."""
    soltas = sorted(portas, key=lambda p: p['frente']['lo'][0])
    grupos = []
    while soltas:
        a = soltas.pop(0)
        par = next((b for b in soltas
                    if a['lado'] == 'ESQUERDA' and b['lado'] == 'DIREITA'
                    and abs(a['frente']['lo'][2] - b['frente']['lo'][2]) <= 3.0
                    and abs(a['frente']['hi'][2] - b['frente']['hi'][2]) <= 3.0
                    and 0.0 <= b['frente']['lo'][0] - a['frente']['hi'][0] <= FOLGA_PAR_MM),
                   None)
        if par is not None:
            soltas.remove(par)
            grupos.append([a, par])
        else:
            grupos.append([a])
    return grupos


def planejar(pecas, ferragens):
    """O que cada peca do modulo vira. `pecas` = as chapas e curvas do
    modulo (`peca`), `ferragens` = as que nao sao chapa (com a cor).
    Devolve {'portas': [{'folhas': [frente], 'lado', 'vao', 'plano'}],
    'gavetas': [{'frentes', 'vao', 'plano', 'profundidade', 'curva'}],
    'correr': [{'quadros', 'vao', 'plano'}], 'remover': [peca],
    'fundo': peca|None, 'travessas': [(peca, lado)]}."""
    plano = {'portas': [], 'gavetas': [], 'correr': [], 'remover': [],
             'fundo': None, 'travessas': []}
    if not pecas:
        return plano
    ymin = min(p['lo'][1] for p in pecas)
    frentes = [p for p in pecas if p['lo'][1] <= ymin + TOL_FRENTE_MM
               and (p['eixo'] == 1 or p['curva'])
               and _tam(p, 0) >= FRENTE_MINIMA_MM[0]
               and _tam(p, 2) >= FRENTE_MINIMA_MM[1]]
    corpo = [p for p in pecas if p not in frentes]
    costas = max(p['hi'][1] for p in pecas)
    # cesto aramado (gavetao, porta-temperos): a gaveta do Promob sem
    # caixa de MDF -- vira gaveta NOSSA (caixa e trilho do add-on)
    cestos = [c for c in ferragens if c['cor'] == COR_ALUMINIO
              and all(_tam(c, k) >= CESTO_MINIMO_MM[k] for k in range(3))]
    com_frente = set()
    portas, gavetas, usadas = [], [], set()
    for f in frentes:
        caixa = _caixa_de_gaveta(f, corpo, costas)
        dob = _dobradicas(f, ferragens) if not f['curva'] else []
        atras = [c for c in cestos
                 if f['lo'][0] - 5.0 <= _centro(c, 0) <= f['hi'][0] + 5.0
                 and f['lo'][2] - 5.0 <= _centro(c, 2) <= f['hi'][2] + 5.0]
        com_frente.update(id(c) for c in atras)
        if (caixa or atras) and not dob:
            gavetas.append({'frente': f, 'caixa': caixa})
            usadas.update(id(p) for p in caixa)
        elif dob and not f['curva']:
            lado = _lado_dobradica(f, dob)
            if lado is not None:
                portas.append({'frente': f, 'lado': lado})
    # a caixa de uma gaveta nao delimita o vao da outra
    corpo = [p for p in corpo if id(p) not in usadas]
    for pilha in _pilhas(gavetas):
        fs = [g['frente'] for g in pilha]
        uniao = _uniao(fs)
        # a face de tras das frentes (na curva, a das pontas do arco)
        face = max(f['hi'][1] for f in fs)
        curva = any(f['curva'] for f in fs)
        plano['gavetas'].append({
            'frentes': fs, 'plano': face,
            'vao': vao_atras(corpo, uniao, face, costas),
            'profundidade': _profundidade(corpo, uniao, face, 500.0),
            'curva': curva})
        plano['remover'] += fs + [p for g in pilha for p in g['caixa']]
    # cesto SEM frente de chapa (a frente era do cesto do Promob): gaveta
    # no vao inteiro em que ele esta', com a frente do add-on
    for c in cestos:
        if id(c) in com_frente or c['lo'][1] > ymin + 20.0:
            continue
        x0, x1, z0, z1 = vao_atras(corpo, c, ymin, costas, alcance=1e9)
        caixa = {'lo': [x0, ymin, z0], 'hi': [x1, ymin, z1]}
        plano['gavetas'].append({
            'frentes': [], 'plano': ymin, 'vao': (x0, x1, z0, z1),
            'profundidade': _profundidade(corpo, caixa, ymin, 500.0),
            'curva': False})
    for grupo in _pares(portas):
        fs = [g['frente'] for g in grupo]
        uniao = _uniao(fs)
        face = max(f['hi'][1] for f in fs)
        plano['portas'].append({
            'folhas': fs, 'lado': grupo[0]['lado'] if len(grupo) == 1 else 'ESQUERDA',
            'plano': face, 'vao': vao_atras(corpo, uniao, face, costas)})
        plano['remover'] += fs
    # correr: os quadros de aluminio na frente do modulo (o vidro de
    # dentro e os trilhos do Promob ficam de fora)
    caixa_modulo = _uniao(pecas)
    quadros = [f for f in ferragens if f['cor'] == COR_ALUMINIO
               and QUADRO_CORRER_MM[0] <= _tam(f, 1) <= QUADRO_CORRER_MM[1]
               and _tam(f, 0) >= 300.0 and _tam(f, 2) >= 300.0
               and _dentro(f, caixa_modulo, 0, 5.0) and _dentro(f, caixa_modulo, 2, 5.0)
               and f['lo'][1] <= ymin + 80.0]
    if quadros:
        uniao = _uniao(quadros)
        plano['correr'].append({'quadros': quadros, 'plano': ymin,
                                'vao': vao_atras(corpo, uniao, ymin, costas)})
    # fundo e travessas do topo: as pecas dependentes do modulo
    restantes = [p for p in corpo if id(p) not in {id(r) for r in plano['remover']}]
    if restantes:
        caixa = _uniao(restantes)
        L, A = _tam(caixa, 0), _tam(caixa, 2)
        fundos = [p for p in restantes if p['eixo'] == 1
                  and p['espessura'] <= FUNDO_MAXIMO_MM
                  and p['hi'][1] >= caixa['hi'][1] - 30.0
                  and _tam(p, 0) * _tam(p, 2) >= 0.5 * L * A]
        if len(fundos) == 1:
            plano['fundo'] = fundos[0]
        deitadas = [p for p in restantes if p['eixo'] == 2
                    and p['hi'][2] >= caixa['hi'][2] - 1.0]
        tampo = any(_tam(p, 1) > TRAVESSA_MAXIMA_MM for p in deitadas)
        if not tampo:
            for p in deitadas:
                if (_tam(p, 1) <= TRAVESSA_MAXIMA_MM and _tam(p, 0) >= 0.8 * (L - 2 * p['espessura'])):
                    if p['lo'][1] <= caixa['lo'][1] + 5.0:
                        plano['travessas'].append((p, 'FRENTE'))
                    elif p['hi'][1] >= caixa['hi'][1] - 5.0:
                        plano['travessas'].append((p, 'TRAS'))
    return plano


# ------------------------------------------------------------ cena
def _local(conj, ponto_mm):
    return conj.matrix_world.inverted() @ (Vector(ponto_mm) / 1000.0) * 1000.0


def _mundo(conj, x, y, z):
    return Vector((x, y, z)) / 1000.0


def _chapa_vizinha(conj, x, z):
    """Uma chapa do modulo para o `objeto_a` do operador de portas."""
    chapas = _modulos._chapas_do_conjunto(conj)
    return min(chapas, key=lambda c: (c.matrix_world.translation * 1000.0
                                      - Vector((x, 0.0, z))).xz.length).name


def _porta(conj, porta, vao, plano, **opcoes):
    """Porta nativa pelos 4 pontos do wizard (porta, vao, vao, porta), no
    plano da frente do corpo -- o caminho de `_portas.porta_no_modulo`."""
    x0, x1, z0, z1 = vao
    px0, px1, pz0, pz1 = porta
    pontos = [_mundo(conj, px0, plano, pz1), _mundo(conj, x0, plano, z1),
              _mundo(conj, x1, plano, z0), _mundo(conj, px1, plano, pz0)]
    referencia = tuple(v for linha in conj.matrix_world.to_quaternion().to_matrix()
                       for v in linha)
    antes = set(_portas._portas_do_conjunto(conj))
    resultado = bpy.ops.object.cabinet_portas(
        'EXEC_DEFAULT', capturado=True, ponto_a=pontos[1], ponto_b=pontos[2],
        quatro_pontos=True, porta_a=pontos[0], porta_b=pontos[3],
        referencia=referencia, pai_nome=conj.name, modulo_nome=conj.name,
        objeto_a_nome=_chapa_vizinha(conj, x0, z1), frente='NEG_Y', folga_mm=0,
        **opcoes)
    if 'FINISHED' not in resultado:
        return None
    novas = [g for g in _portas._portas_do_conjunto(conj) if g not in antes]
    return novas[-1] if novas else None


def _gavetas_do_plano(context, conj, g):
    lo, hi = _portas._limites_locais_modulo(conj)
    x0, x1, z0, z1 = g['vao']
    a = _local(conj, (x0, g['plano'], z0))
    b = _local(conj, (x1, g['plano'], z1))
    margens = (a.x - lo.x, hi.x - b.x, a.z - lo.z, hi.z - b.z, max(0.0, a.y - lo.y))
    fs = g['frentes']
    E = float(conj.conj_espessura_mm) or 18.0
    if not fs:
        # cesto sem frente: uma gaveta de frente nossa, cobrindo o vao
        p = dict(quantidade=1, lateral_mm=E, espessura_frente_mm=E,
                 profundidade_mm=round(g['profundidade'], 1))
        try:
            return _gavetas.criar_gavetas(context, conj, margens, p)
        except ValueError as erro:
            print('[Cabinet Creator] cesto do Promob em %s: %s' % (conj.name, erro))
            return None
    cobre = x0 - min(f['lo'][0] for f in fs)
    sobreposta = cobre > 1.0
    folga = (max(0.0, E - cobre) if sobreposta
             else max(0.0, min(f['lo'][0] for f in fs) - x0))
    vaos = [fs[i + 1]['lo'][2] - fs[i]['hi'][2] for i in range(len(fs) - 1)]
    curva = g['curva']
    espessura = max(1.0, min(f['espessura'] for f in fs))
    p = dict(quantidade=len(fs),
             proporcoes=[_tam(f, 2) for f in fs] if len(fs) > 1 else [],
             cobertura='SOBREPOSTA' if sobreposta else 'EMBUTIDA',
             folga_frontal_mm=round(folga, 1),
             entre_gavetas_mm=round(sum(vaos) / len(vaos), 1) if vaos else 3.0,
             espessura_frente_mm=round(espessura, 1), lateral_mm=E,
             profundidade_mm=round(g['profundidade'], 1),
             frente_curva_mm=(round(max(0.0, max(_tam(f, 1) for f in fs) - espessura), 1)
                              if curva else 0.0),
             puxador='NENHUM' if curva else 'PERFIL')
    try:
        return _gavetas.criar_gavetas(context, conj, margens, p)
    except ValueError as erro:
        print('[Cabinet Creator] gavetas do Promob em %s: %s' % (conj.name, erro))
        return None


def _cobertura_nossa(borda, vao, E, lados):
    """A borda da porta nos lados da DOBRADICA vai para a cobertura do
    add-on: perto da espessura inteira = Reta (cobre E; o respiro de 2 mm
    e' nosso), perto da metade = Curva. O Promob deixa 5 mm (cobre 10 de
    15), que a regra de 75% chamaria de Curva. Os outros lados ficam como
    vieram (o rodape do balcao, por exemplo)."""
    borda = list(borda)
    sinais = (-1.0, 1.0, -1.0, 1.0)            # para FORA do vao
    for k in lados:
        cobre = sinais[k] * (borda[k] - vao[k])
        if cobre >= 0.6 * E:
            borda[k] = vao[k] + sinais[k] * E
        elif cobre >= 0.2 * E:
            borda[k] = vao[k] + sinais[k] * E / 2.0
    return borda


def aplicar(context, conj, plano):
    """Cria no modulo `conj` (ja' so' com o corpo) as portas, gavetas e
    portas de correr do plano. Devolve {'portas', 'gavetas', 'correr'}."""
    feitos = {'portas': 0, 'gavetas': 0, 'correr': 0}
    for g in plano['gavetas']:
        if _gavetas_do_plano(context, conj, g) is not None:
            feitos['gavetas'] += 1
    for p in plano['portas']:
        uniao = _uniao(p['folhas'])
        opcoes = {'folhas': len(p['folhas'])}
        if p['lado'] == 'CIMA':
            opcoes.update(abertura='BASCULANTE', dobradica_lado='CIMA', folhas=1)
        else:
            opcoes.update(abertura='GIRO', dobradica_lado=p['lado'])
        borda = _cobertura_nossa(
            [uniao['lo'][0], uniao['hi'][0], uniao['lo'][2], uniao['hi'][2]],
            p['vao'], float(conj.conj_espessura_mm) or 18.0,
            {'CIMA': (3,), 'ESQUERDA': (0,), 'DIREITA': (1,)}[p['lado']]
            if len(p['folhas']) == 1 else (0, 1))
        if _porta(conj, borda, p['vao'], p['plano'], **opcoes) is not None:
            feitos['portas'] += 1
    for c in plano['correr']:
        n = min(len(c['quadros']), _portas.LIMITES_FOLHAS['CORRER'])
        grupo = _porta(conj, c['vao'], c['vao'], c['plano'], abertura='CORRER',
                       folhas=n, tipo_correr='EMBUTIDA')
        if grupo is not None:
            _portas._editar_parametro_porta(context, grupo, 'folha', 'QUADRO')
            feitos['correr'] += 1
    return feitos


def marcar_dependentes(conj, plano):
    """O fundo fino e as travessas do Promob viram as dependentes do
    modulo (refeitas pela caixa: `_modulos.ajustar_dependentes`)."""
    lo, hi = _modulos._caixa_local_estrutural(conj) or (None, None)
    for p, lado in plano['travessas']:
        tr = p['obj']
        tr[_chapas.MARCA_TRAVESSA] = 1
        tr[_modulos.CHAVE_LADO_TRAVESSA] = lado
        _chapas._ocupado[0] = True
        try:
            # o ajuste so' troca a posicao: os eixos tem de ser os dele
            tr.chapa_comprimento_mm = _tam(p, 1)
            tr.matrix_world = conj.matrix_world.to_quaternion().to_matrix().to_4x4()
        finally:
            _chapas._ocupado[0] = False
    fundo = plano['fundo']
    if fundo is not None and hi is not None:
        fundo['obj'][_chapas.MARCA_FUNDO] = 1
        recuo = hi.y - _local(conj, fundo['hi'])[1]
        conj[_modulos.CHAVE_RECUO_FUNDO] = max(0.0, round(recuo, 1))
    if plano['travessas'] or fundo is not None:
        bpy.context.view_layer.update()
        # o E do modulo sai da caixa, agora sem o fundo
        _modulos.sincronizar_medidas_conjunto(conj)
        _modulos.ajustar_dependentes(conj)
