"""Ferragens: o rig da dobradica reta do usuario, pistoes, montagem
das ferragens na porta, abertura da folha e a edicao das
ferragens selecionadas."""

import bpy, bmesh, math, os, json, gpu
from gpu_extras.batch import batch_for_shader
from bpy.props import StringProperty
from mathutils import Matrix, Vector
from bpy.types import Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = None
_modulos = None
_eventos = None
_portas = None
_puxadores = None
_gaveta = None
_orcamento = None
_hud = None
_solda = None

# ============================== FERRAGENS, PIVO E ABERTURA (Fase 3)
# Backlog do usuario (Epico 1.7/1.8 e Epico 4). A folha continua uma
# chapa CENTRADA e filha direta do grupo (`_grupo_portas`, `_cantos`, HUD
# e puxadores dependem disso): o pivo NAO e' um Empty nem a origem
# deslocada -- a abertura entra na matrix_basis dela como um giro em
# volta da borda da dobradica: quina das COSTAS na sobreposta, da FRENTE
# na embutida (`_eixo_da_dobradica`). Correr desliza no trilho.
# Ferragens: malhas que a porta refaz (as caixas) ou posiciona (o rig) a cada
# `_aplicar_portas`. Corpo da dobradica e haste do pistao sao filhos do
# GRUPO (ficam no modulo); caneco e corpo do pistao, da FOLHA (giram com
# ela). Pistao = rigging de verdade: cada metade tem um Damped Track
# mirando a outra ponta, entao encolhe e estica sozinho com o angulo.
# A haste fica na ponta de BAIXO (na lateral), como pedem os fabricantes;
# os suportes (plaquinha na lateral, pino na folha) seguem o mesmo pai.
CHAVE_FERRAGEM = 'porta_ferragem'          # tipo; marca a ferragem
CHAVE_ID_FERRAGEM = 'porta_ferragem_id'    # estavel: reaproveita o objeto
CHAVE_ABERTURA = 'porta_fracao_aberta'     # na folha: 0 fechada .. 1 aberta
CHAVE_CENTRO_FOLHA = 'porta_centro_mm'     # centro da folha FECHADA
ABERTURA_MAX_GRAUS = {'GIRO': 110.0, 'BASCULANTE': 90.0}
PISTAO_DA_LATERAL_MM = 25.0      # do eixo do pistao a' face interna
TRILHO_ALTURA_MM = 15.0
NOME_MIRA_PISTAO = 'Cabinet Mira'


def _lado_da_folha(p, indice, n):
    """Lado das dobradicas de UMA folha de giro (2 folhas: uma de cada)."""
    if n > 1:
        return 'ESQUERDA' if indice == 0 else 'DIREITA'
    lado = p.get('dobradica_lado', 'ESQUERDA')
    return lado if lado in ('ESQUERDA', 'DIREITA') else 'ESQUERDA'


# ---- Dobradica RETA de verdade: o modelo e o rig do usuario
# (`extrair_dobradica.py` tira UMA dobradica do arquivo dele, sem refazer
# malha nem rig). Cada dobradica da porta Reta e' uma copia desse asset:
# armature com driver (0,385 x o controlador) + IK que fecha o braco, e
# a CABECA (copo) e' quem leva a porta. A folha do add-on continua filha
# do grupo (invariante): ela faz o MESMO movimento da cabeca pela tabela
# medida no asset (`_passo_rig`), e o controlador de cada copia gira o
# rig junto -- os dois andam sincronizados. O copo fura a folha por um
# Boolean com o cortador do asset (filho da cabeca).
# Referencial da raiz do asset: -X = para dentro do movel, +Y = frente,
# Z = eixo das dobradicas. A da direita e a do basculante sao a MESMA
# peca girada (o modelo e' simetrico em cima/baixo), nunca espelhada.
# A raiz vai pela FOLHA, como no modelo: `borda_porta_mm` para dentro da
# borda dela e `costas_mm` atras das costas (o copo e' furado a uma
# distancia fixa da borda). Assim a folha abre como a do usuario. O
# modelo cobre 12,75 mm da lateral; a Reta de 18 mm cobre 16, e a placa
# base entrava ~3 mm na chapa (print do usuario). Levar o rig INTEIRO a'
# face fazia o canto da folha aberta entrar no modulo; entao, como o
# parafuso de cobertura da dobradica de verdade, so' a PLACA (e o suporte,
# se passar da face) anda ate' a face interna -- copo e porta ficam.
PASTA_FERRAGENS = os.path.join(os.path.dirname(__file__), 'ferragens')
ARQUIVO_DOBRADICA_RETA = os.path.join(PASTA_FERRAGENS, 'dobradica_reta.blend')
PREFIXO_FURO = 'Cabinet Copo '        # Boolean do copo na folha
PECAS_REALCE_RIG = ('base', 'suporte', 'cabeca')
# x mais externo (mm, raiz do asset, +X = para dentro da chapa) das pecas
# que o ajuste de cobertura leva a' face interna; medido no asset (v2)
FACE_PECAS_CALCO = {'base': 0.0, 'suporte': -2.71}
# as malhas do arame da previa que vao junto (filhas delas no asset)
MALHAS_CALCO = {'Dobradica Base': 'base', 'Dobradica Parafuso.001': 'base',
                'Dobradica Parafuso.002': 'base', 'Dobradica Suporte': 'suporte',
                'Dobradica Parafuso': 'suporte', 'Dobradica Pino.002': 'suporte'}


def _calco_rig(cobertura):
    """{peca: mm para DENTRO do movel} que a placa e o suporte andam para
    nao entrar na chapa: a raiz fica `cobertura - borda_porta_mm` para
    fora da face interna (a folha cobre mais que o modelo)."""
    fora = float(cobertura) - _dados_dobradica_reta()['borda_porta_mm']
    return {peca: max(0.0, fora + x) for peca, x in FACE_PECAS_CALCO.items()}


def _matriz_calco(mm):
    """Translacao (m) na raiz do asset: -X = para dentro do movel."""
    return Matrix.Translation((-mm / 1000.0, 0.0, 0.0))
_dobradica_reta = [None]              # o .json do asset, lido uma vez


def _dados_dobradica_reta():
    """{'costas_mm', 'tabela': [(controle, giro, tx, ty)], ...} ou None
    (sem o asset a Reta volta ao eixo fixo)."""
    if _dobradica_reta[0] is None:
        try:
            with open(os.path.join(PASTA_FERRAGENS, 'dobradica_reta.json'),
                      encoding='utf-8') as f:
                dados = json.load(f)
            dados['tabela'] = [tuple(float(v) for v in linha)
                               for linha in dados['tabela']]
            dados['costas_mm'] = float(dados['costas_mm'])
            dados['borda_porta_mm'] = float(dados['borda_porta_mm'])
            dados['folga_modulo_mm'] = float(dados.get('folga_modulo_mm', 0.0))
            _dobradica_reta[0] = dados
        except (OSError, ValueError, KeyError, TypeError):
            _dobradica_reta[0] = {}
    if not _dobradica_reta[0] or not os.path.exists(ARQUIVO_DOBRADICA_RETA):
        return None
    return _dobradica_reta[0]


def _usa_rig(p):
    return (p.get('dobradica') == 'RETA'
            and p.get('abertura') in ('GIRO', 'BASCULANTE')
            and _dados_dobradica_reta() is not None)


def _afastamento_porta(p):
    """Costas da folha ate' a frente do modulo (mm). Na Reta com o rig, no
    minimo a folga do modelo do usuario (1,86 mm): o rig foi feito com ela
    e, encostada, o canto da folha aberta entrava no modulo."""
    afastamento = float(p['afastamento_mm'])
    if _usa_rig(p):
        afastamento = max(afastamento, _dados_dobradica_reta()['folga_modulo_mm'])
    return afastamento


def _giro_maximo_rig():
    return abs(_dados_dobradica_reta()['tabela'][-1][1])


def _passo_rig(fracao):
    """(graus do controlador, giro, tx, ty) com a folha aberta `fracao`
    do giro maximo -- linear no ANGULO da folha (o controlador nao e')."""
    tabela = _dados_dobradica_reta()['tabela']
    alvo = max(0.0, min(1.0, float(fracao))) * tabela[-1][1]
    for a, b in zip(tabela, tabela[1:]):
        if (a[1] - alvo) * (b[1] - alvo) <= 0.0:
            t = 0.0 if b[1] == a[1] else (alvo - a[1]) / (b[1] - a[1])
            return tuple(x + (y - x) * t for x, y in zip(a, b))
    return tabela[-1] if fracao > 0 else tabela[0]


def _referencial_rig(dentro, origem):
    """Matriz (mm) da raiz do asset: -X = `dentro`, +Y = frente do vao."""
    x = -Vector((dentro[0], dentro[1], 0.0)).normalized()
    y = Vector((0.0, 0.0, 1.0))
    m = Matrix((x, y, x.cross(y))).transposed().to_4x4()
    m.translation = Vector(origem)
    return m


def _movimento_rig(dentro, origem_mm, fracao):
    """Transformacao (metros, referencial do grupo) que a cabeca da
    dobradica -- e a folha presa nela -- faz aberta `fracao`."""
    raiz = _referencial_rig(dentro, Vector(origem_mm) / 1000.0)
    _controle, giro, tx, ty = _passo_rig(fracao)
    passo = (Matrix.Translation((tx / 1000.0, ty / 1000.0, 0.0))
             @ Matrix.Rotation(math.radians(giro), 4, 'Z'))
    return raiz @ passo @ raiz.inverted()


def _eixo_da_dobradica(p, e):
    """Altura do eixo de giro sobre as COSTAS da folha (mm).

    Sobreposta (Reta/Curva) gira na quina das COSTAS, como a dobradica de
    caneco real: aberta, as costas da folha ficam rente a' face de fora da
    lateral (ou do tampo, no basculante) e a borda encosta na frente do
    movel. Girando pela quina da frente sobrava um vao da espessura da
    folha (print do usuario). A embutida gira pela FRENTE: pelas costas ela
    entraria na lateral."""
    return float(e) if p.get('dobradica') == 'SUPER_CURVA' else 0.0


def _matriz_abertura(p, largura, n, indice, folha, fracao):
    """matrix_basis (metros, referencial do grupo) da folha `indice`
    aberta `fracao` (0..1). `folha` = (l, a, e, centro) em mm, fechada."""
    l, a, e, centro = folha
    c = Vector(centro)
    fechada = Matrix.Translation(c / 1000.0)
    fracao = max(0.0, min(1.0, float(fracao)))
    if fracao <= 0.0:
        return fechada
    abertura = p.get('abertura', 'GIRO')
    if abertura == 'CORRER':
        # cada folha corre para o meio, por cima da vizinha
        sobra = float(p.get('sobreposicao_mm', 0.0)) if n > 1 else 0.0
        sentido = 1.0 if n == 1 or c.x < largura / 2.0 - 1e-6 else -1.0
        passo = Vector((sentido * fracao * (l - sobra), 0.0, 0.0))
        return Matrix.Translation(passo / 1000.0) @ fechada
    if _usa_rig(p):
        # Reta: o movimento medido no rig do usuario, a partir da raiz
        # da dobradica (pela borda e pelas costas da folha)
        dados = _dados_dobradica_reta()
        fundo, borda = c.z - e / 2.0 - dados['costas_mm'], dados['borda_porta_mm']
        if abertura == 'BASCULANTE':
            dentro, origem = (0.0, -1.0), (c.x, c.y + a / 2.0 - borda, fundo)
        elif _lado_da_folha(p, indice, n) == 'ESQUERDA':
            dentro, origem = (1.0, 0.0), (c.x - l / 2.0 + borda, c.y, fundo)
        else:
            dentro, origem = (-1.0, 0.0), (c.x + l / 2.0 - borda, c.y, fundo)
        return _movimento_rig(dentro, origem, fracao) @ fechada
    eixo_z = c.z + _eixo_da_dobradica(p, e) - e / 2.0
    if abertura == 'BASCULANTE':
        pivo = Vector((c.x, c.y + a / 2.0, eixo_z))
        giro = Matrix.Rotation(
            -math.radians(ABERTURA_MAX_GRAUS['BASCULANTE']) * fracao, 4, 'X')
    else:
        esquerda = _lado_da_folha(p, indice, n) == 'ESQUERDA'
        pivo = Vector((c.x - l / 2.0 if esquerda else c.x + l / 2.0,
                       c.y, eixo_z))
        angulo = math.radians(ABERTURA_MAX_GRAUS['GIRO']) * fracao
        giro = Matrix.Rotation(-angulo if esquerda else angulo, 4, 'Y')
    pivo = pivo / 1000.0
    return (Matrix.Translation(pivo) @ giro @ Matrix.Translation(-pivo)
            @ fechada)


def _dados_da_folha(folha):
    """(l, a, e, centro) da folha FECHADA, em mm."""
    centro = folha.get(CHAVE_CENTRO_FOLHA)
    if centro is None:
        centro = folha.matrix_basis.translation * 1000.0
    return (float(folha.chapa_largura_mm), float(folha.chapa_comprimento_mm),
            float(folha.chapa_espessura_mm), tuple(float(v) for v in centro))


def _matriz_fechada(folha):
    """matrix_world da folha como se estivesse fechada (quem mede o vao
    por uma folha de apoio nao pode ver a porta aberta)."""
    centro = folha.get(CHAVE_CENTRO_FOLHA)
    if centro is None or folha.parent is None:
        return folha.matrix_world.copy()
    return folha.parent.matrix_world @ Matrix.Translation(
        Vector(tuple(centro)) / 1000.0)


def _posicionar_folha(grupo, folha):
    p = grupo.get('porta_parametros') or {}
    folha.matrix_basis = _matriz_abertura(
        p, float(grupo.get('porta_vao_largura_mm', 0.0)),
        len(_portas._folhas_portas(grupo)), int(folha.get('porta_indice', 0)),
        _dados_da_folha(folha), folha.get(CHAVE_ABERTURA, 0.0))
    _girar_rigs(grupo, folha)


def _definir_abertura(context, folha, fracao):
    """Abre a folha `fracao` (0..1). Ferragens seguem por parentesco e o
    pistao pela mira."""
    grupo = _portas._grupo_portas(folha)
    if grupo is None or _chapas.MARCA_FOLHA not in folha:
        return False
    ocupado_antes = _chapas._ocupado[0]
    _chapas._ocupado[0] = True
    try:
        folha[CHAVE_ABERTURA] = max(0.0, min(1.0, float(fracao)))
        _posicionar_folha(grupo, folha)
    finally:
        _chapas._ocupado[0] = ocupado_antes
    context.view_layer.update()
    return True


def _dobradicas_da_porta(p, largura, altura, folhas):
    """[(aresta, distancias, indice da folha)]: onde vao as dobradicas
    (lado, quantidade e margem gravados pelo wizard)."""
    if p.get('abertura') == 'CORRER' or not folhas:
        return []
    lateral = float(p['lateral_mm'])
    cob = [float(p['folga_mm']) - i for i in _portas._inicios_porta(p)]
    fracoes = {k: c / lateral for k, c in zip(_portas.COBERTURAS_LADOS, cob)}
    tipo = 'BASCULANTE' if p.get('abertura') == 'BASCULANTE' else 'GIRO'
    arestas = _portas._arestas_da_porta(largura, altura, fracoes, lateral, tipo)
    lados = (['CIMA'] if tipo == 'BASCULANTE'
             else [_lado_da_folha(p, i, len(folhas)) for i in range(len(folhas))])
    margem = float(p.get('dobradicas_margem_mm', _portas.MARGEM_DOBRADICAS_PADRAO))
    saida = []
    for i, lado in enumerate(lados):
        aresta = next((a for a in arestas if a['lado'] == lado), arestas[0])
        comprimento = (aresta['b'] - aresta['a']).length
        qtd = (int(p.get('dobradicas_qtd', 0) or 0)
               or _portas._qtd_dobradicas_padrao(comprimento))
        # vale tambem para a porta gravada antes do limite
        qtd, ajustada = _portas._ajustar_dobradicas(comprimento, qtd, margem)
        saida.append((aresta, _portas._posicoes_ferragens(comprimento, qtd, ajustada), i))
    return saida


def _pistoes_da_porta(p, largura, altura, folhas):
    """Pistoes do basculante (mm, referencial do grupo, porta FECHADA).

    Modelo e posicao saem de `_pistao_do_vao` (automatico; o offset
    manual do wizard so' sobe, ate' o limite do pistao). Corpo e haste
    medem o FECHADO cada um: fechada a haste some no corpo, aberta os
    dois somam o aberto. Suporte = plaquinha na lateral (do eixo a' face
    interna) e pino nas costas da folha."""
    qtd = (int(p.get('pistoes_qtd', 0) or 0)
           or _portas._qtd_pistoes_padrao(folhas[0][0]))
    g = _portas._pistao_do_vao(altura, folhas[0],
                       float(p.get('pistoes_offset_mm', 0.0) or 0.0), p)
    meio = _portas.PISTAO_SUPORTE_LADO_MM / 2.0
    saida = []
    for lado in ('ESQUERDA', 'DIREITA')[:max(1, min(2, qtd))]:
        esquerda = lado == 'ESQUERDA'
        x = PISTAO_DA_LATERAL_MM if esquerda else largura - PISTAO_DA_LATERAL_MM
        na_lateral, na_folha, _aberta = _portas._pontas_pistao(g, x, folhas[0])
        face = 0.0 if esquerda else largura
        s = lado[0]
        saida += [
            {'id': 'PISTAO_PONTO_' + s, 'tipo': 'PISTAO_PONTO', 'folha': 0,
             'forma': 'PONTO', 'origem': na_folha},
            {'id': 'PISTAO_CORPO_' + s, 'tipo': 'PISTAO_CORPO', 'folha': 0,
             'forma': 'HASTE', 'origem': na_folha,
             'raio': g['corpo'] / 2.0, 'comprimento': g['fechado'],
             'mira': 'PISTAO_HASTE_' + s},
            {'id': 'PISTAO_HASTE_' + s, 'tipo': 'PISTAO_HASTE', 'folha': None,
             'forma': 'HASTE', 'origem': na_lateral,
             'raio': g['haste'] / 2.0, 'comprimento': g['fechado'],
             'mira': 'PISTAO_PONTO_' + s},
            {'id': 'PISTAO_SUPORTE_LATERAL_' + s, 'tipo': 'PISTAO_SUPORTE',
             'folha': None, 'forma': 'CAIXA', 'cantos': [
                 Vector((xx, na_lateral.y + dy, na_lateral.z + dz))
                 for xx in (face, x) for dy in (-meio, meio)
                 for dz in (-meio, meio)]},
            {'id': 'PISTAO_SUPORTE_FOLHA_' + s, 'tipo': 'PISTAO_SUPORTE',
             'folha': 0, 'forma': 'CAIXA', 'cantos': [
                 Vector((x + dx, na_folha.y + dy, z))
                 for dx in (-meio, meio) for dy in (-meio, meio)
                 for z in (na_folha.z, na_folha.z + _portas.PISTAO_SUPORTE_MM)]},
        ]
    return saida


def _prisma(origem, destino, raio, comprimento):
    """8 cantos (ordem de ARESTAS_CAIXA) de um prisma quadrado de lado
    2*raio, de `origem` rumo a `destino`: o volume de um cilindro."""
    eixo = destino - origem
    eixo = eixo.normalized() if eixo.length > 1e-9 else Vector((0, 0, 1))
    n1 = eixo.orthogonal().normalized()
    n2 = eixo.cross(n1)
    return [origem + eixo * u + n1 * v + n2 * t
            for u in (0.0, comprimento) for v in (-raio, raio)
            for t in (-raio, raio)]


def _caixas_dos_itens_pistao(itens):
    """Volumes (mm) do pistao FECHADO a partir dos itens de
    `_pistoes_da_porta`: suportes como sao, corpo e haste rumo a' mira."""
    por_id = {item['id']: item for item in itens}
    caixas = []
    for item in itens:
        if item['forma'] == 'CAIXA':
            caixas.append(list(item['cantos']))
        elif item['forma'] == 'HASTE' and item.get('mira') in por_id:
            caixas.append(_prisma(Vector(item['origem']),
                                  Vector(por_id[item['mira']]['origem']),
                                  item['raio'], item['comprimento']))
    return caixas


def _ferragens_da_porta(p, largura, altura, folhas):
    """O que montar (mm, referencial do grupo, porta FECHADA): uma lista
    de {'id', 'tipo', 'folha' (indice; None = no grupo), 'forma', ...}."""
    saida = []
    rig = _usa_rig(p)
    for aresta, distancias, i in _dobradicas_da_porta(p, largura, altura, folhas):
        _l, _a, e, centro = folhas[i]
        if rig:
            # Reta: a dobradica de verdade (asset do usuario), raiz pela
            # borda e pelas costas da folha (`_referencial_rig`)
            dados = _dados_dobradica_reta()
            fundo = centro[2] - e / 2.0 - dados['costas_mm']
            eixo = aresta['b'] - aresta['a']
            eixo = eixo.normalized() if eixo.length else Vector((0, 1))
            recuo = aresta['dentro'] * (dados['borda_porta_mm']
                                        - aresta['cobertura'])
            for k, d in enumerate(distancias):
                ponto = aresta['a'] + eixo * d + recuo
                saida.append({'id': 'RIG_%s_%d' % (aresta['lado'], k),
                              'tipo': 'DOBRADICA_RIG', 'folha': None,
                              'forma': 'RIG', 'indice_folha': i,
                              'calco': _calco_rig(aresta['cobertura']),
                              'matriz': _referencial_rig(
                                  aresta['dentro'], (ponto.x, ponto.y, fundo))})
            continue
        caixas = _portas._caixas_dobradicas(aresta, distancias, centro[2] - e / 2.0)
        for k, (corpo, caneco) in enumerate(caixas):
            sufixo = '%s_%d' % (aresta['lado'], k)
            saida.append({'id': 'DOBRADICA_' + sufixo, 'tipo': 'DOBRADICA',
                          'folha': None, 'forma': 'CAIXA', 'cantos': corpo})
            saida.append({'id': 'CANECO_' + sufixo, 'tipo': 'CANECO',
                          'folha': i, 'forma': 'CILINDRO',
                          'origem': sum(caneco, Vector()) / 8.0,
                          'raio': _portas.CANECO_DIAMETRO_MM / 2.0,
                          'comprimento': _portas.CANECO_FUNDO_MM + _portas.CANECO_ABA_MM})
    abertura = p.get('abertura')
    if abertura == 'BASCULANTE' and folhas:
        saida += _pistoes_da_porta(p, largura, altura, folhas)
    elif abertura == 'CORRER' and folhas:
        zs = [c[2] + s * e / 2.0 for _l, _a, e, c in folhas for s in (-1, 1)]
        saida.append({'id': 'TRILHO', 'tipo': 'TRILHO', 'folha': None,
                      'forma': 'CAIXA', 'cantos': [
                          Vector((x, y, z)) for x in (0.0, largura)
                          for y in (altura - TRILHO_ALTURA_MM, altura)
                          for z in (min(zs), max(zs))]})
    return saida


def _origem_da_ferragem(item):
    if item['forma'] == 'CAIXA':
        return sum(item['cantos'], Vector()) / len(item['cantos'])
    return Vector(item['origem'])


def _malha_da_ferragem(malha, item):
    """Caixa (centrada), caneco (cilindro em Z, centrado) ou metade de
    pistao (cilindro de 0 a +Y: o Damped Track aponta o Y para a mira)."""
    bm = bmesh.new()
    try:
        if item['forma'] == 'CAIXA':
            lo = Vector(tuple(min(v[k] for v in item['cantos']) for k in range(3)))
            hi = Vector(tuple(max(v[k] for v in item['cantos']) for k in range(3)))
            bmesh.ops.create_cube(bm, size=1.0)
            bmesh.ops.scale(bm, vec=(hi - lo) / 1000.0, verts=bm.verts)
        else:
            raio = item['raio'] / 1000.0
            fundo = item['comprimento'] / 1000.0
            bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False,
                                  segments=24, radius1=raio, radius2=raio,
                                  depth=fundo)
            if item['forma'] == 'HASTE':
                bmesh.ops.rotate(bm, cent=(0.0, 0.0, 0.0), verts=bm.verts,
                                 matrix=Matrix.Rotation(-math.pi / 2, 3, 'X'))
                bmesh.ops.translate(bm, vec=(0.0, fundo / 2.0, 0.0),
                                    verts=bm.verts)
        bm.to_mesh(malha)
    finally:
        bm.free()
    malha.update()


def _ferragens_portas(grupo):
    return [o for o in grupo.children_recursive if CHAVE_FERRAGEM in o]


def _vivo(idb):
    """False se o objeto ja' foi apagado (a referencia Python sobra)."""
    try:
        idb.name
        return True
    except ReferenceError:
        return False


DADOS_POR_TIPO = {'MESH': 'meshes', 'CURVE': 'curves', 'ARMATURE': 'armatures'}


def _remover_ferragem(obj):
    """Apaga a ferragem e o que pende dela (o rig da dobradica inteiro);
    a malha so' sai se ninguem mais a usa (as copias do rig dividem)."""
    if not _vivo(obj):
        return
    for o in [*obj.children_recursive, obj]:
        dados, colecao = o.data, DADOS_POR_TIPO.get(o.type)
        bpy.data.objects.remove(o, do_unlink=True)
        if dados is not None and colecao and dados.users == 0:
            getattr(bpy.data, colecao).remove(dados)


# Nomes das pecas que o add-on cria: portugues, sem sublinhado (pedido do
# usuario). Nome nao e' chave de nada (tipo e id ficam nas props).
NOMES_FERRAGEM = {'DOBRADICA': 'Dobradica Corpo', 'CANECO': 'Dobradica Copo',
                  'PISTAO_CORPO': 'Pistao Corpo', 'PISTAO_HASTE': 'Pistao Haste',
                  'PISTAO_PONTO': 'Pistao Ponta',
                  'PISTAO_SUPORTE': 'Pistao Suporte', 'TRILHO': 'Trilho'}


def _padronizar_nome(obj, nome):
    """Objeto (e a malha so' dele) com `nome`, se ainda nao tem: arquivo
    antigo trazia 'Pistao_Corpo', 'Folha_01'... O .001 do Blender fica."""
    if _portas._sem_sufixo(obj.name) != nome:
        obj.name = nome
    dados = obj.data
    if (dados is not None and dados.users == 1 and not dados.library
            and _portas._sem_sufixo(dados.name) != nome):
        dados.name = nome


# ---- copias do rig da dobradica reta
COLECOES_DO_RIG = ('meshes', 'curves', 'armatures', 'materials',
                   'node_groups', 'images')
TIPO_DA_PECA_RIG = {'raiz': 'DOBRADICA_RIG', 'base': 'DOBRADICA',
                    'cabeca': 'CANECO', 'furo': 'DOBRADICA_FURO'}
# o que so' faz o rig funcionar nao aparece (o Blender ainda os avalia)
PECAS_OCULTAS_RIG = ('furo', 'controle', 'armacao', 'armacao_ik')
def ocultar_pecas_do_rig(objetos=None):
    """Esconde de novo o que so' faz o rig funcionar (controlador, furo do
    copo, armacoes). Relato do usuario: o arco do controlador aparecia na
    porta -- e ela e' aberta pelo SLIDER do add-on, nunca por ele. O
    `hide_set` e' da camada de visualizacao, nao do objeto: preset
    inserido, objeto anexado ou camada nova o traziam de volta. Devolve
    quantas reapareceram."""
    camada = bpy.context.view_layer
    escondidas = 0
    for o in objetos if objetos is not None else bpy.data.objects:
        if o.get('cabinet_peca') not in PECAS_OCULTAS_RIG:
            continue
        try:
            if not o.hide_render:
                o.hide_render = True
            if o.name in camada.objects and not o.hide_get():
                o.select_set(False)
                o.hide_set(True)
                escondidas += 1
        except (ReferenceError, RuntimeError):
            pass
    return escondidas


def _anexar_sem_repetir(caminho, tipo, nomes=None):
    """Anexa os `tipo` ('objects', 'meshes'...) de um asset do add-on e
    devolve os novos. Malhas, materiais, imagens e node groups que ja'
    vieram antes (mesmo `cabinet_origem`) voltam aos de antes: o arquivo
    nao incha a cada porta."""
    antes = {nome: set(getattr(bpy.data, nome)) for nome in COLECOES_DO_RIG}
    with bpy.data.libraries.load(caminho, link=False) as (origem, destino):
        setattr(destino, tipo, sorted(n for n in getattr(origem, tipo)
                                      if nomes is None or n in nomes))
    novos = [d for d in getattr(destino, tipo) if d is not None]
    for nome in COLECOES_DO_RIG:
        dados = getattr(bpy.data, nome)
        velhos = {d.get('cabinet_origem'): d for d in antes[nome]
                  if d.get('cabinet_origem')}
        for novo in [d for d in dados if d not in antes[nome]]:
            chave = novo.get('cabinet_origem')
            if chave and chave in velhos:
                novo.user_remap(velhos[chave])
                dados.remove(novo)
            elif chave:
                velhos[chave] = novo
    return [d for d in novos if _vivo(d)]


def _instanciar_rig(colecao, raiz_id):
    """Anexa uma copia do asset (modelo + rig do usuario, tal e qual) e
    devolve a raiz."""
    raiz = None
    for i, o in enumerate(_anexar_sem_repetir(ARQUIVO_DOBRADICA_RETA,
                                              'objects')):
        colecao.objects.link(o)
        peca = o.get('cabinet_peca', 'peca')
        o[CHAVE_FERRAGEM] = TIPO_DA_PECA_RIG.get(peca, 'DOBRADICA_PECA')
        o[CHAVE_ID_FERRAGEM] = (raiz_id if peca == 'raiz'
                                else '%s:%02d' % (raiz_id, i))
        if peca in PECAS_OCULTAS_RIG:
            o.hide_render = True
            o.hide_set(True)
        if peca == 'raiz':
            raiz = o
            _chapas._ocultar_empty(o)
    return raiz


def _solver_rapido():
    """O Boolean rapido: 'FAST' no 4.x, 'FLOAT' no 5.x."""
    itens = bpy.types.BooleanModifier.bl_rna.properties['solver'].enum_items
    return 'FAST' if 'FAST' in itens.keys() else 'FLOAT'


def _furar_folhas(folhas, cortadores):
    """Boolean do copo em cada folha: um por cortador das dobradicas dela
    (`cortadores` = {indice: [objetos]}); os que sobram saem."""
    for i, folha in enumerate(folhas):
        quer = {c.name: c for c in cortadores.get(i, ())}
        for m in [m for m in folha.modifiers if m.name.startswith(PREFIXO_FURO)]:
            if m.type == 'BOOLEAN' and m.object is not None and m.object.name in quer:
                quer.pop(m.object.name)
            else:
                folha.modifiers.remove(m)
        for cortador in quer.values():
            m = folha.modifiers.new(PREFIXO_FURO + cortador.name, 'BOOLEAN')
            m.operation = 'DIFFERENCE'
            m.solver = _solver_rapido()
            m.object = cortador


def _girar_rigs(grupo, folha=None):
    """Controlador de cada dobradica reta no angulo da folha dela (o
    driver e o IK do asset fazem o resto)."""
    folhas = _portas._folhas_portas(grupo)
    for o in _ferragens_portas(grupo):
        if o.get('cabinet_peca') != 'controle':
            continue
        indice = int(o.get('porta_ferragem_folha', 0))
        if indice >= len(folhas) or (folha is not None and folhas[indice] != folha):
            continue
        graus = _passo_rig(folhas[indice].get(CHAVE_ABERTURA, 0.0))[0]
        o.rotation_euler.z = -math.radians(graus)


def _montar_ferragens(grupo, parametros, largura, altura, calculadas):
    """Cria/atualiza/remove as ferragens da porta (chamado com
    `_ocupado`, depois que as folhas existem). Reaproveita pelo id."""
    existentes = {}
    for o in _ferragens_portas(grupo):
        if not _vivo(o):
            continue            # saiu junto com a raiz (rig duplicado)
        if o.get(CHAVE_ID_FERRAGEM) in existentes:
            _remover_ferragem(o)
        else:
            existentes[o.get(CHAVE_ID_FERRAGEM)] = o
    folhas = _portas._folhas_portas(grupo)
    colecao = grupo.users_collection[0]
    feitos = {}
    cortadores = {}
    for item in _ferragens_da_porta(parametros, largura, altura, calculadas):
        obj = existentes.pop(item['id'], None)
        if obj is not None and not _vivo(obj):
            obj = None
        if obj is not None and obj.get(CHAVE_FERRAGEM) != item['tipo']:
            # outro tipo com o mesmo id: nunca reaproveitar (a malha do
            # rig e' dividida entre as copias)
            _remover_ferragem(obj)
            obj = None
        if item['forma'] == 'RIG':
            if (obj is not None and int(obj.get('cabinet_versao', 1))
                    != int(_dados_dobradica_reta().get('versao', 1))):
                # copia de asset antigo (nomes em ingles, furo velho): troca
                _remover_ferragem(obj)
                obj = None
            if obj is None:
                obj = _instanciar_rig(colecao, item['id'])
                if obj is None:
                    continue
            obj.parent = grupo
            obj.matrix_parent_inverse = Matrix.Identity(4)
            matriz = item['matriz'].copy()
            matriz.translation = matriz.translation / 1000.0
            obj.matrix_basis = matriz
            for parte in obj.children_recursive:
                peca = parte.get('cabinet_peca')
                if peca not in item.get('calco', {}):
                    continue
                # a pose do asset, guardada na 1a vez: o calco nao acumula
                if 'cabinet_pose_asset' not in parte:
                    parte['cabinet_pose_asset'] = [
                        v for linha in parte.matrix_basis for v in linha]
                pose = parte['cabinet_pose_asset']
                pose = Matrix([pose[i * 4:i * 4 + 4] for i in range(4)])
                inversa = parte.matrix_parent_inverse
                parte.matrix_basis = (inversa.inverted_safe()
                                      @ _matriz_calco(item['calco'][peca])
                                      @ inversa @ pose)
            for parte in [obj, *obj.children_recursive]:
                parte.hide_select = False
                existentes.pop(parte.get(CHAVE_ID_FERRAGEM), None)
                parte['porta_ferragem_folha'] = item['indice_folha']
                if parte.get('cabinet_peca') == 'furo':
                    cortadores.setdefault(item['indice_folha'], []).append(parte)
            continue
        ponto = item['forma'] == 'PONTO'
        if obj is not None and ponto != (obj.type == 'EMPTY'):
            _remover_ferragem(obj)
            obj = None
        nome = item.get('nome') or NOMES_FERRAGEM.get(item['tipo'],
                                                      item['tipo'].title())
        if obj is None:
            obj = bpy.data.objects.new(
                nome, None if ponto else bpy.data.meshes.new(nome))
            colecao.objects.link(obj)
            obj[CHAVE_FERRAGEM] = item['tipo']
            obj[CHAVE_ID_FERRAGEM] = item['id']
            if ponto:
                _chapas._ocultar_empty(obj)
        _padronizar_nome(obj, nome)
        # selecionavel (duplo clique / Outliner) e editavel; arquivo
        # antigo trazia hide_select
        obj.hide_select = False
        if not ponto:
            _malha_da_ferragem(obj.data, item)
        indice = item['folha']
        origem = _origem_da_ferragem(item)
        if indice is not None and indice < len(folhas):
            pai = folhas[indice]
            origem = origem - Vector(calculadas[indice][3])
        else:
            pai = grupo
        obj.parent = pai
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.matrix_basis = Matrix.Translation(origem / 1000.0)
        feitos[item['id']] = (obj, item)
    for obj, item in feitos.values():
        mira = feitos.get(item.get('mira'), (None, None))[0]
        restricoes = [r for r in obj.constraints if r.name == NOME_MIRA_PISTAO]
        if mira is None:
            for r in restricoes:
                obj.constraints.remove(r)
            continue
        r = restricoes[0] if restricoes else obj.constraints.new('DAMPED_TRACK')
        r.name = NOME_MIRA_PISTAO
        r.target = mira
        r.track_axis = 'TRACK_Y'
    for obj in existentes.values():
        _remover_ferragem(obj)
    _furar_folhas(folhas, cortadores)
    _girar_rigs(grupo)


_contagem_objetos = [-1]    # o handler so' confere quando ela muda


def _conferir_ferragens():
    """Timer: ferragem nao acende com a porta, entao apagar ou duplicar a
    porta nao a leva. Ferragem sem porta sai; porta sem
    nenhuma (duplicada, ou de antes da Fase 3) ganha as dela. De quebra,
    Empty de amarracao de arquivo/preset antigo fica invisivel."""
    try:
        for o in bpy.data.objects:
            if (o.type == 'EMPTY'
                    and any(m in o for m in (_chapas.MARCA_CONJUNTO, _chapas.MARCA_PORTAS,
                                             CHAVE_FERRAGEM))
                    and o.empty_display_size > _chapas.TAMANHO_EMPTY_OCULTO * 1.5):
                _chapas._ocultar_empty(o)
        for o in [o for o in bpy.data.objects if CHAVE_FERRAGEM in o]:
            if not _vivo(o):
                continue        # saiu junto com a raiz do rig
            dono = o.parent
            while dono is not None and _chapas.MARCA_PORTAS not in dono:
                dono = dono.parent
            if dono is None:
                _remover_ferragem(o)
        for grupo in [o for o in bpy.data.objects
                      if _chapas.MARCA_PORTAS in o and o.get('porta_parametros')]:
            if _portas._folhas_portas(grupo) and not _ferragens_portas(grupo):
                _refazer_ferragens(grupo)
        # armario apagado (X): a Collection dele nao fica vazia na cena
        for colecao in [c for c in bpy.data.collections
                        if c.get(_modulos.MARCA_COLECAO_MODULO)
                        and not c.all_objects and not c.children]:
            bpy.data.collections.remove(colecao)
        _orcamento._limpar_comodos_vazios()
    except Exception as e:
        print("[Cabinet Creator] ferragens:", e)
    return None


def _refazer_ferragens(grupo):
    """Ferragens de novo pelo que a porta guarda (desfazer arraste)."""
    p = grupo.get('porta_parametros')
    if not p:
        return
    folhas = _portas._folhas_portas(grupo)
    ocupado_antes = _chapas._ocupado[0]
    _chapas._ocupado[0] = True
    try:
        _montar_ferragens(grupo, dict(p),
                          float(grupo.get('porta_vao_largura_mm', 0.0)),
                          float(grupo.get('porta_vao_altura_mm', 0.0)),
                          [_dados_da_folha(f) for f in folhas])
    finally:
        _chapas._ocupado[0] = ocupado_antes


def _dados_ferragens_selecionadas(context):
    """{tipo: {'qtd', 'mm', 'info'}} das ferragens selecionadas, pelos
    parametros da 1a porta (editar vale para todas), ou None."""
    edicao = _ferragens_em_edicao(context)
    if not edicao:
        return None
    grupo, tipos = edicao[0]
    medidas = _porta_calculada(grupo)
    if medidas is None:
        return None
    p, _largura, altura, folhas = medidas
    dados = {}
    if 'DOBRADICA' in tipos:
        dobradicas = _dobradicas_da_porta(p, _largura, altura, folhas)
        if dobradicas:
            aresta, distancias, _i = dobradicas[0]
            dados['DOBRADICA'] = {
                'qtd': len(distancias),
                # a margem que VALE (a gravada antes do limite pode passar)
                'mm': distancias[0] if len(distancias) > 1 else float(
                    p.get('dobradicas_margem_mm', _portas.MARGEM_DOBRADICAS_PADRAO)),
                'info': _portas.NOME_DOBRADICA.get(p.get('dobradica'), ''),
                'modelo': p.get('dobradica')}
    if 'PISTAO' in tipos and p.get('abertura') == 'BASCULANTE' and folhas:
        offset = float(p.get('pistoes_offset_mm', 0.0) or 0.0)
        dados['PISTAO'] = {
            'qtd': (int(p.get('pistoes_qtd', 0) or 0)
                    or _portas._qtd_pistoes_padrao(folhas[0][0])),
            'mm': _portas._pistao_do_vao(altura, folhas[0], offset, p)['offset']}
    return dados or None


def _valor_ferragem(grupo, nome, valor):
    """O valor que se grava: o offset do pistao trava no curso (e volta
    a 0, o automatico, quando cai nele); quantidade e margem das
    dobradicas, so' o que cabe na borda (`_portas._ajustar_dobradicas`)."""
    medidas = _porta_calculada(grupo)
    if nome in {'dobradicas_margem_mm', 'dobradicas_qtd'}:
        dobradicas = (_dobradicas_da_porta(*medidas) if medidas is not None
                      else None)
        if not dobradicas:
            return (max(0.0, float(valor)) if nome == 'dobradicas_margem_mm'
                    else int(valor))
        aresta, distancias, _i = dobradicas[0]
        comprimento = (aresta['b'] - aresta['a']).length
        margem = float(medidas[0].get('dobradicas_margem_mm',
                                      _portas.MARGEM_DOBRADICAS_PADRAO))
        if nome == 'dobradicas_qtd':
            return _portas._ajustar_dobradicas(comprimento, int(valor), margem)[0]
        return _portas._ajustar_dobradicas(comprimento, len(distancias),
                                           float(valor))[1]
    if nome != 'pistoes_offset_mm':
        return int(valor)
    if medidas is None:
        return float(valor)
    p, _l, altura, folhas = medidas
    g = _portas._pistao_do_vao(altura, folhas[0], max(1e-3, float(valor)), p)
    automatico = _portas._pistao_do_vao(altura, folhas[0], p=p)['offset']
    return 0.0 if abs(g['offset'] - automatico) <= 0.5 else g['offset']


def _editar_ferragens_selecionadas(context, nome, valor):
    """Quantidade/afastamento editados na gaveta com as ferragens
    selecionadas: todas as portas do modulo delas. Refazer a porta mexe
    na selecao: as ferragens continuam selecionadas depois."""
    estado = _ferragens_selecionadas[0]
    erro = ''
    for grupo, _tipos in _ferragens_em_edicao(context):
        erro = _portas._editar_parametro_porta(
            context, grupo, nome, _valor_ferragem(grupo, nome, valor)) or erro
    for o in context.selected_objects:
        o.select_set(False)
    context.view_layer.objects.active = None
    _ferragens_selecionadas[0] = estado
    _eventos._redesenhar_viewports(context)
    return erro


# ------------------------------------- ferragens selecionadas (edicao)
# Pedido do usuario: dobradicas e pistoes so' aparecem (realce laranja,
# volume como no wizard) CRIANDO a porta ou SELECIONADOS. Clique numa
# dobradica (corpo ou caneco) = todas as dobradicas do MODULO; num pistao
# (qualquer parte) = todos os pistoes; Shift soma (ou tira) o outro tipo.
# A selecao do Blender esvazia: porta, modulo e puxadores ficam sem
# contorno. Com Alt, um controlador por porta e tipo: o da dobradica
# corre na borda (margem, espelhada nas duas pontas), o do pistao na
# lateral (distancia do topo, travada no curso dele). A ferragem segue
# fora da selecao do Blender (duplo clique = UMA peca, nativa): a do tipo
# mora aqui, por NOME.
TIPOS_SELECAO_FERRAGEM = {
    'DOBRADICA': 'DOBRADICA', 'CANECO': 'DOBRADICA',
    'DOBRADICA_PECA': 'DOBRADICA',      # braco, pino, parafuso do rig
    'PISTAO_CORPO': 'PISTAO', 'PISTAO_HASTE': 'PISTAO',
    'PISTAO_SUPORTE': 'PISTAO'}
_ferragens_selecionadas = [None]   # {'portas': [nomes], 'tipos': [..]}
_arraste_ferragem = [None]         # (grupo, tipo) do controlador arrastado
ORDEM_BOUND_BOX = (0, 1, 3, 2, 4, 5, 7, 6)   # = a ordem de ARESTAS_CAIXA


def _grupo_da_ferragem(obj):
    while obj is not None and _chapas.MARCA_PORTAS not in obj:
        obj = obj.parent
    return obj


def _portas_do_modulo_da(grupo):
    """As portas que acendem junto: as do modulo da porta (ou so' ela)."""
    modulo = bpy.data.objects.get(grupo.get(_portas.CHAVE_MODULO_PORTA, ''))
    if modulo is not None and _chapas.MARCA_CONJUNTO in modulo:
        portas = [g for g in _portas._portas_do_conjunto(modulo)
                  if g.get('porta_parametros')]
        if grupo in portas:
            return portas
    return [grupo]


def _selecionar_ferragem(context, obj, somar=False):
    """Clique numa ferragem: as do mesmo TIPO do modulo inteiro. Shift
    soma o outro tipo (ou tira o mesmo, como o Shift nativo)."""
    tipo = TIPOS_SELECAO_FERRAGEM.get(obj.get(CHAVE_FERRAGEM))
    grupo = _grupo_da_ferragem(obj)
    if tipo is None or grupo is None:
        return False
    portas = [g.name for g in _portas_do_modulo_da(grupo)]
    atual = _ferragens_selecionadas[0]
    tipos = {tipo}
    if somar and atual is not None and set(atual['portas']) == set(portas):
        tipos = set(atual['tipos']) ^ {tipo}
    for o in context.selected_objects:
        o.select_set(False)
    context.view_layer.objects.active = None
    _ferragens_selecionadas[0] = ({'portas': portas, 'tipos': sorted(tipos)}
                                  if tipos else None)
    if tipos and context.scene.cabinet_aba != 'PORTAS':
        # a gaveta vai a' aba do item clicado (quantidade e afastamento
        # das ferragens moram na aba Portas)
        context.scene.cabinet_aba = 'PORTAS'
        tela = getattr(context, 'screen', None)
        if tela is not None:
            tela[_gaveta._CHAVE_ROLAGEM] = 0
            _gaveta._fechar_opcoes(tela)
    _eventos._redesenhar_viewports(context)
    return True


def _selecionar_peca(context, obj, somar=False):
    """Duplo clique numa ferragem: SO' aquela peca, selecao do Blender
    (pedido do usuario: nada fica fora da edicao nativa). Malha de peca
    do rig e' dividida entre as copias: editar uma edita todas."""
    if not somar:
        for o in context.selected_objects:
            o.select_set(False)
    _ferragens_selecionadas[0] = None
    obj.select_set(True)
    context.view_layer.objects.active = obj
    _eventos._redesenhar_viewports(context)


def _ferragens_em_edicao(context):
    """[(grupo, tipos)] das ferragens selecionadas. Vale enquanto nada
    mais estiver selecionado no Blender (qualquer selecao encerra)."""
    estado = _ferragens_selecionadas[0]
    if estado is None:
        return []
    if getattr(context, 'selected_objects', None):
        _ferragens_selecionadas[0] = None
        return []
    saida = []
    for nome in estado['portas']:
        grupo = bpy.data.objects.get(nome)
        if grupo is not None and grupo.get('porta_parametros'):
            saida.append((grupo, set(estado['tipos'])))
    return saida


def _caixas_ferragens(grupo, tipos):
    """Volume (8 cantos em MUNDO) das malhas de verdade dos `tipos`: o
    caneco gira com a folha e o pistao estica pela mira. Nao e' desenhado
    (o realce e' o arame, `_arame_ferragens`): mede onde cada uma esta'."""
    ordem = ('DOBRADICA', 'CANECO', 'PISTAO_CORPO', 'PISTAO_HASTE',
             'PISTAO_SUPORTE', 'DOBRADICA_PECA')
    # do rig da reta, so' o volume das pecas grandes (base, suporte e
    # cabeca): parafuso e pino viravam um enxame de caixinhas
    ferragens = sorted(
        (o for o in _ferragens_portas(grupo)
         if TIPOS_SELECAO_FERRAGEM.get(o.get(CHAVE_FERRAGEM)) in tipos
         and ('cabinet_peca' not in o
              or o['cabinet_peca'] in PECAS_REALCE_RIG)),
        key=lambda o: (ordem.index(o[CHAVE_FERRAGEM]),
                       o.get(CHAVE_ID_FERRAGEM, '')))
    return [[o.matrix_world @ Vector(o.bound_box[k]) for k in ORDEM_BOUND_BOX]
            for o in ferragens]


def _porta_calculada(grupo):
    """(parametros, largura, altura, folhas FECHADAS) da porta, ou None."""
    p = dict(grupo.get('porta_parametros') or {})
    try:
        L = float(grupo['porta_vao_largura_mm'])
        A = float(grupo['porta_vao_altura_mm'])
        return p, L, A, _portas._calcular_folhas_portas(L, A, p)
    except (ValueError, KeyError, TypeError):
        return None


def _controles_ferragens(grupo, tipos):
    """[(tipo, ponto, a, b)] em MUNDO: o controlador de cada tipo e o
    trilho em que ele corre (de a ate' b). Dobradica: a 1a da 1a borda,
    correndo na borda. Pistao: a fixacao da lateral do 1o, do topo do
    vao (a) ate' a base (b)."""
    medidas = _porta_calculada(grupo)
    if medidas is None:
        return []
    p, L, A, folhas = medidas
    m = grupo.matrix_world
    mundo = lambda v: m @ (Vector(v) / 1000.0)
    saida = []
    dobradicas = _dobradicas_da_porta(p, L, A, folhas)
    if 'DOBRADICA' in tipos and dobradicas:
        aresta, distancias, i = dobradicas[0]
        _l, _a, e, centro = folhas[i]
        if _usa_rig(p):
            # na raiz do rig da reta (pela borda da folha, como la')
            dados = _dados_dobradica_reta()
            z = centro[2] - e / 2.0 - dados['costas_mm']
            meio = aresta['dentro'] * (dados['borda_porta_mm']
                                       - aresta['cobertura'])
        else:
            z = centro[2] - e / 2.0 - _portas.DOBRADICA_FUNDO_MM / 2.0
            meio = aresta['dentro'] * _portas.DOBRADICA_AVANCO_MM / 2.0
        a, b = aresta['a'] + meio, aresta['b'] + meio
        eixo = (b - a).normalized() if (b - a).length else Vector((0, 1))
        ponto = a + eixo * (distancias[0] if distancias else 0.0)
        saida.append(('DOBRADICA', mundo((*ponto, z)), mundo((*a, z)),
                      mundo((*b, z))))
    if 'PISTAO' in tipos and p.get('abertura') == 'BASCULANTE' and folhas:
        g = _portas._pistao_do_vao(A, folhas[0],
                           float(p.get('pistoes_offset_mm', 0.0) or 0.0), p)
        lateral = _portas._pontas_pistao(g, PISTAO_DA_LATERAL_MM, folhas[0])[0]
        saida.append(('PISTAO', mundo(lateral),
                      mundo((lateral.x, A, lateral.z)),
                      mundo((lateral.x, 0.0, lateral.z))))
    return saida


def _valor_do_controle(grupo, tipo, fracao):
    """(parametro, valor) com o controlador a `fracao` (0..1) do trilho.
    Dobradica: margem espelhada (passar do meio conta da outra ponta).
    Pistao: distancia do topo, travada no curso (no automatico grava 0,
    que acompanha o modulo)."""
    medidas = _porta_calculada(grupo)
    if medidas is None:
        return None
    p, L, A, folhas = medidas
    fracao = max(0.0, min(1.0, fracao))
    if tipo == 'DOBRADICA':
        dobradicas = _dobradicas_da_porta(p, L, A, folhas)
        if not dobradicas:
            return None
        aresta = dobradicas[0][0]
        comprimento = (aresta['b'] - aresta['a']).length
        distancia = fracao * comprimento
        return 'dobradicas_margem_mm', _portas._ajustar_dobradicas(
            comprimento, len(dobradicas[0][1]),
            min(distancia, comprimento - distancia))[1]
    g = _portas._pistao_do_vao(A, folhas[0], max(1e-3, fracao * A), p)
    automatico = _portas._pistao_do_vao(A, folhas[0], p=p)['offset']
    return ('pistoes_offset_mm',
            0.0 if abs(g['offset'] - automatico) <= 0.5 else g['offset'])


def _controle_ferragem_sob_mouse(context, posicao):
    """(grupo, tipo) do controlador sob o mouse (so' com Alt)."""
    if not _solda._correntes_visiveis():
        return None, None
    raio = _solda.RAIO_BOLINHA_PX * max(1.0, context.preferences.system.ui_scale)
    mouse = Vector(posicao)
    melhor = None
    for grupo, tipos in _ferragens_em_edicao(context):
        for tipo, ponto, _a, _b in _controles_ferragens(grupo, tipos):
            p = _hud._projetar_hud(context, ponto)
            if p is None:
                continue
            d = (p - mouse).length
            if d <= raio and (melhor is None or d < melhor[0]):
                melhor = (d, grupo, tipo)
    return (melhor[1], melhor[2]) if melhor else (None, None)


def _desenhar_ferragens_selecionadas(context):
    """Com Alt (ou arrastando), o controlador de cada tipo das ferragens
    selecionadas (bolinha branca; arrastando, o trilho). O realce delas e'
    o arame, desenhado em 3D (`_desenhar_aramados`)."""
    edicao = _ferragens_em_edicao(context)
    if not edicao:
        return
    escala = max(1.0, context.preferences.system.ui_scale)
    realce = _hud._cor_realce_hud()
    arraste = _arraste_ferragem[0]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        for grupo, tipos in edicao:
            for tipo, ponto, a, b in _controles_ferragens(grupo, tipos):
                ativo = arraste == (grupo.name, tipo)
                if not (ativo or _solda._correntes_visiveis()):
                    continue
                tela = [_hud._projetar_hud(context, v) for v in (ponto, a, b)]
                if any(v is None for v in tela):
                    continue
                if ativo:
                    shader.uniform_float('color', (1.0, 1.0, 1.0, 0.6))
                    batch_for_shader(shader, 'TRIS', {'pos': _puxadores._quad_2d(
                        tela[1], tela[2], 1.0 * escala)}).draw(shader)
                    _hud._bolinha_2d(shader, tela[0], 8 * escala, realce)
                _hud._bolinha_2d(shader, tela[0], (6 if ativo else 5) * escala,
                            (1.0, 1.0, 1.0, 1.0))
    finally:
        gpu.state.blend_set('NONE')


class OBJECT_OT_arrastar_ferragem(Operator):
    """Arraste o controlador (Alt): a dobradica corre na borda, o pistao na lateral"""
    bl_idname = 'object.cabinet_arrastar_ferragem'
    bl_label = 'Mover Ferragem'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    grupo: StringProperty(options={'SKIP_SAVE'})
    tipo: StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        grupo = bpy.data.objects.get(self.grupo)
        if (grupo is None or not grupo.get('porta_parametros')
                or self.tipo not in {'DOBRADICA', 'PISTAO'}
                or context.region is None):
            return {'CANCELLED'}
        controle = next((c for c in _controles_ferragens(grupo, {self.tipo})
                         if c[0] == self.tipo), None)
        if controle is None:
            return {'CANCELLED'}
        # o trilho e' lido UMA vez: refazer a porta nao o mexe
        self._trilho = (controle[2].copy(), controle[3].copy())
        self._nome = ('dobradicas_margem_mm' if self.tipo == 'DOBRADICA'
                      else 'pistoes_offset_mm')
        self._antes = float(grupo['porta_parametros'].get(self._nome, 0.0)
                            or 0.0)
        self._estado = _ferragens_selecionadas[0]
        _arraste_ferragem[0] = (self.grupo, self.tipo)
        self._area = context.area
        context.window_manager.modal_handler_add(self)
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _aplicar(self, context, valor):
        grupo = bpy.data.objects.get(self.grupo)
        if grupo is None:
            return
        guardado = float(grupo['porta_parametros'].get(self._nome, 0.0) or 0.0)
        if abs(guardado - valor) < 0.05:
            return
        erro = _portas._editar_parametro_porta(context, grupo, self._nome, valor)
        if erro:
            print("[Cabinet Creator] ferragem:", erro)
        # refazer a porta mexe na selecao: as ferragens continuam a dela
        for o in context.selected_objects:
            o.select_set(False)
        context.view_layer.objects.active = None
        _ferragens_selecionadas[0] = self._estado

    def _encerrar(self):
        _arraste_ferragem[0] = None
        self._area.tag_redraw()

    def cancel(self, context):
        self._encerrar()

    def modal(self, context, event):
        if _arraste_ferragem[0] is None:
            return {'CANCELLED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self._aplicar(context, self._antes)
            self._encerrar()
            return {'CANCELLED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type == 'MOUSEMOVE':
            mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            # o trilho (MUNDO) na tela; a mesma conta do puxador
            ta, tb = (_hud._projetar_hud(context, v) for v in self._trilho)
            grupo = bpy.data.objects.get(self.grupo)
            if ta is not None and tb is not None and grupo is not None:
                fracao = _puxadores._fracao_na_linha(ta, tb, mouse)
                resultado = _valor_do_controle(grupo, self.tipo, fracao)
                if resultado is not None:
                    self._aplicar(context, resultado[1])
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self._encerrar()
            return {'FINISHED'}
        return {'RUNNING_MODAL'}
