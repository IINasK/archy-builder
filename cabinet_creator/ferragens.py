"""Ferragens: o rig da dobradica reta do usuario, pistoes, montagem
das ferragens na porta, abertura da folha e a edicao das
ferragens selecionadas."""

import bpy, bmesh, math, os, json, gpu
from gpu_extras.batch import batch_for_shader
from bpy.props import StringProperty
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

_promob = None
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
_arame = None

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
# Trilho do correr (foto do usuario): em CIMA, um U alto com um canal
# fundo por folha -- ela entra e sobra folga para levantar e tirar; em
# BAIXO, uma chapa baixa com uma guia por folha, onde ela fica em pe'.
TRILHO_CIMA_ALTURA_MM = 35.0    # do perfil de cima inteiro
TRILHO_CIMA_CHAPA_MM = 2.0      # a chapa do topo dele
TRILHO_LEVANTAR_MM = 10.0       # da folha ate' a chapa do topo
TRILHO_PAREDE_MM = 2.0          # paredes de fora dos dois perfis
TRILHO_BAIXO_CHAPA_MM = 3.0     # a chapa do perfil de baixo
TRILHO_GUIA_MM = 5.0            # altura da guia sob cada folha
TRILHO_GUIA_LARGURA_MM = 4.0


def altura_trilho_baixo():
    """Do fundo do vao ate' o pe' da folha de correr (mm)."""
    return TRILHO_BAIXO_CHAPA_MM + TRILHO_GUIA_MM
NOME_MIRA_PISTAO = 'Cabinet Mira'


def _lado_da_folha(p, indice, n):
    """Lado das dobradicas de UMA folha de giro (2 folhas: uma de cada)."""
    escolhido = p.get('dobradicas_lados_folhas', {}).get(str(indice))
    if p.get('abertura') == 'GIRO' and escolhido in ('ESQUERDA', 'DIREITA'):
        return escolhido
    if n > 1 and p.get('abertura') != 'ZIGZAG':
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
# Parafuso padrao (pedido do usuario: o mesmo nas dobradicas e puxadores):
# chipboard 3,5 x 14 cabeca CHATA Phillips de `gerar_parafuso.py` (a foto
# de referencia do usuario), em tamanho real. Origem = centro da cabeca NA
# SUPERFICIE da peca; +Z = para fora, cabeca escareada e haste em -Z. A
# cabeca (5,78) nao afunda ate' o fim: o topo fica SALIENCIA acima (o
# refinamento do usuario). O nome novo (era a panela) e a VERSAO fazem as
# cenas carregarem este, nao reusarem a malha velha (`_anexar_sem_repetir`
# deduplica por origem + versao).
ARQUIVO_PARAFUSO = os.path.join(PASTA_FERRAGENS, 'parafuso.blend')
NOME_PARAFUSO = 'Parafuso Chipboard 3,5x14 Chata'
VERSAO_PARAFUSO = 2          # 1 = cabeca de 7 mm rente (326)
COMPRIMENTO_PARAFUSO_MM = 14.0
RAIO_CABECA_PARAFUSO_MM = 2.889
SALIENCIA_PARAFUSO_MM = 0.876
PARAFUSOS_ANTIGOS = {'Parafuso Chipboard 3,5x14'}   # a panela (323): trocar
# Trilhos da porta de correr COM MOLDURA: os perfis de aluminio do
# guarda-roupa do usuario (`extrair_trilho_moldura.py`), como poligonos da
# secao (u = das costas para a frente, v = da base para cima), extrudados
# na largura. Em cima, dois canais (meio de cada, medido no perfil); em
# baixo, duas guias, cujo meio fica sob o meio dos canais.
ARQUIVO_TRILHO_MOLDURA = os.path.join(PASTA_FERRAGENS, 'trilho_moldura.json')
CANAIS_TRILHO_MOLDURA_MM = (16.75, 47.0)      # (costas, frente)
MEIO_GUIAS_TRILHO_BAIXO_MM = 23.8
_perfis_trilho_moldura = [None]


def perfil_trilho_moldura(lado):
    """{'profundidade_mm', 'altura_mm', 'poligonos'} do trilho 'CIMA' ou
    'BAIXO' (lido uma vez)."""
    if _perfis_trilho_moldura[0] is None:
        with open(ARQUIVO_TRILHO_MOLDURA, encoding='utf-8') as arq:
            _perfis_trilho_moldura[0] = json.load(arq)['trilhos']
    return _perfis_trilho_moldura[0][lado]
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
    return {peca: fora + x for peca, x in FACE_PECAS_CALCO.items()}


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
    return ((p.get('dobradica') == 'RETA' or p.get('dobradica_modelo_reta'))
            and p.get('abertura') in ('GIRO', 'BASCULANTE', 'ZIGZAG')
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


def _curso_correr(p, largura, n, l, x):
    """(x fechada, x aberta) do CENTRO da folha de correr de largura `l`
    fechada em `x` (mm, no vao): cada folha tem o seu trilho, entao corre
    ate' a OUTRA ponta do vao, por cima das vizinhas (a unica e as da
    esquerda vao para a direita)."""
    esq, dir_ = _portas._inicios_porta(p)[:2]
    inicio, fim = esq + l / 2.0, largura - dir_ - l / 2.0
    if fim < inicio:
        return x, x
    return x, (fim if x < (inicio + fim) / 2.0 - 1e-6 else inicio)


def _eixo_da_dobradica(p, e):
    """Altura do eixo de giro sobre as COSTAS da folha (mm).

    Sobreposta (Reta/Curva) gira na quina das COSTAS, como a dobradica de
    caneco real: aberta, as costas da folha ficam rente a' face de fora da
    lateral (ou do tampo, no basculante) e a borda encosta na frente do
    movel. Girando pela quina da frente sobrava um vao da espessura da
    folha (print do usuario). A embutida gira pela FRENTE: pelas costas ela
    entraria na lateral."""
    return float(e) if p.get('dobradica') == 'SUPER_CURVA' else 0.0


def _junta_zigzag(p, anterior, atual, indice):
    """Eixo comum das duas metades, alternado entre frente e costas."""
    ca, cb = Vector(anterior[3]), Vector(atual[3])
    z = cb.z + (atual[2] / 2 + 4.5) * (1 if indice % 2 == 0 else -1)
    return Vector(((ca.x + cb.x) / 2, cb.y, z))


def _matrizes_zigzag(p, largura, folhas, fracao):
    """Cadeia calculada uma vez: cada junta herda a pose da precedente."""
    simples = dict(p, abertura='GIRO', folhas=1)
    primeira = _matriz_abertura(simples, largura, 1, 0, folhas[0], fracao)
    movimento = primeira @ Matrix.Translation(-Vector(folhas[0][3]) / 1000)
    giro = math.atan2(movimento[0][2], movimento[0][0])
    saida = [primeira]
    for i in range(1, len(folhas)):
        eixo = _junta_zigzag(p, folhas[i - 1], folhas[i], i) / 1000
        angulo = giro * (-2 if i % 2 else 2)
        movimento = (movimento @ Matrix.Translation(eixo)
                     @ Matrix.Rotation(angulo, 4, 'Y') @ Matrix.Translation(-eixo))
        saida.append(movimento @ Matrix.Translation(Vector(folhas[i][3]) / 1000))
    return saida


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
    if abertura == 'ZIGZAG':
        folhas = _portas._calcular_folhas_portas(largura, a + sum(_portas._inicios_porta(p)[2:]), p)
        return _matrizes_zigzag(p, largura, folhas, fracao)[indice]
    if abertura == 'CORRER':
        fechado, destino = _curso_correr(p, largura, n, l, c.x)
        passo = Vector(((destino - fechado) * fracao, 0.0, 0.0))
        return Matrix.Translation(passo / 1000.0) @ fechada
    if _usa_rig(p):
        # Reta: o movimento medido no rig do usuario, a partir da raiz
        # da dobradica (pela borda e pelas costas da folha)
        dados = _dados_dobradica_reta()
        fundo, borda = c.z - e / 2.0 - dados['costas_mm'], dados['borda_porta_mm']
        if abertura == 'BASCULANTE':
            sinal = -1 if p.get('basculante_invertida') else 1
            dentro, origem = (0.0, -sinal), (c.x, c.y + sinal*(a/2.0-borda), fundo)
        elif _lado_da_folha(p, indice, n) == 'ESQUERDA':
            dentro, origem = (1.0, 0.0), (c.x - l / 2.0 + borda, c.y, fundo)
        else:
            dentro, origem = (-1.0, 0.0), (c.x + l / 2.0 - borda, c.y, fundo)
        return _movimento_rig(dentro, origem, fracao) @ fechada
    eixo_z = c.z + _eixo_da_dobradica(p, e) - e / 2.0
    if abertura == 'BASCULANTE':
        sinal = -1 if p.get('basculante_invertida') else 1
        pivo = Vector((c.x, c.y + sinal*a/2.0, eixo_z))
        giro = Matrix.Rotation(
            -sinal*math.radians(ABERTURA_MAX_GRAUS['BASCULANTE']) * fracao, 4, 'X')
    else:
        esquerda = _lado_da_folha(p, indice, n) == 'ESQUERDA'
        if p.get('dobradica_articulada'):
            folga = float(p.get('dobradica_junta_mm', 4)) / 2
            pivo = Vector((c.x - l / 2 - folga if esquerda else c.x + l / 2 + folga,
                           c.y, c.z - e / 2 - 4.5))
        else:
            pivo = Vector((c.x - l / 2.0 if esquerda else c.x + l / 2.0, c.y, eixo_z))
        angulo = math.radians(float(p.get('abertura_limite_graus',ABERTURA_MAX_GRAUS['GIRO']))) * fracao
        if p.get('dobradica_articulada'):
            angulo = math.radians(180) * fracao * float(p.get('dobradica_articulada_sinal', -1 if esquerda else 1))
            giro = Matrix.Rotation(angulo, 4, 'Y')
        else:
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
    grupo = folha.parent
    apoio = grupo.get('porta_apoio_folha')
    mundo = (_matriz_fechada(apoio) @ grupo.matrix_basis
             if isinstance(apoio, bpy.types.Object) else grupo.matrix_world)
    return mundo @ Matrix.Translation(
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
        fracao = max(0.0, min(1.0, float(fracao)))
        if (folha.get('porta_curva_modelada') and grupo.get('porta_limite_pendente')
                and len(_portas._folhas_portas(grupo))==1
                and abs(fracao-float(folha.get(CHAVE_ABERTURA,0)))>1e-6):
            limite=_promob._limite_curvo_no_corpo(grupo,folha)
            novos=_portas._copiar_parametros(grupo['porta_parametros'])
            if limite is None:novos.pop('abertura_limite_graus',None)
            else:novos['abertura_limite_graus']=limite
            grupo['porta_parametros']=novos;grupo['porta_limite_pendente']=False
            grupo['porta_limite_validado']=limite is not None
        p = grupo.get('porta_parametros') or {}
        if p.get('abertura') == 'ZIGZAG':
            folhas = _portas._folhas_portas(grupo)
            matrizes = _matrizes_zigzag(p, float(grupo['porta_vao_largura_mm']),
                                       [_dados_da_folha(f) for f in folhas], fracao)
            for f, matriz in zip(folhas, matrizes):
                f[CHAVE_ABERTURA] = fracao
                f.matrix_basis = matriz
            _girar_rigs(grupo)
        else:
            folha[CHAVE_ABERTURA] = fracao
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
    if tipo == 'BASCULANTE' and p.get('basculante_invertida'):
        aresta = arestas[0]
        arestas = [dict(aresta, lado='BAIXO', a=Vector((aresta['a'].x, 0)),
                        b=Vector((aresta['b'].x, 0)), dentro=Vector((0, 1)), cobertura=cob[2])]
    lado_basculante = 'BAIXO' if p.get('basculante_invertida') else 'CIMA'
    lados = ([lado_basculante] if tipo == 'BASCULANTE'
             else [_lado_da_folha(p, i, len(folhas)) for i in range(len(folhas))])
    margem = float(p.get('dobradicas_margem_mm', _portas.MARGEM_DOBRADICAS_PADRAO))
    saida = []
    for i, lado in enumerate(lados):
        aresta = next((a for a in arestas if a['lado'] == lado), arestas[0])
        if p.get('abertura') == 'GIRO' and str(i) in p.get('dobradicas_lados_folhas', {}):
            l, a, _e, c = folhas[i]
            # Uma folha parcial invertida prende na SUA borda, nunca na
            # borda oposta do vao inteiro.
            borda = c[0] + (-l / 2 if lado == 'ESQUERDA' else l / 2)
            x = borda + (aresta['cobertura'] if lado == 'ESQUERDA' else -aresta['cobertura'])
            aresta = dict(aresta, a=Vector((x, c[1]-a/2)), b=Vector((x, c[1]+a/2)))
        if p.get('abertura') == 'ZIGZAG' and i > 0:
            l, a, _e, c = folhas[i]
            x = c[0] + (-l / 2 if lado == 'ESQUERDA' else l / 2)
            aresta = dict(aresta, a=Vector((x, c[1] - a / 2)),
                          b=Vector((x, c[1] + a / 2)))
        comprimento = (aresta['b'] - aresta['a']).length
        qtd = (int(p.get('dobradicas_qtd', 0) or 0)
               or _portas._qtd_dobradicas_padrao(comprimento))
        # vale tambem para a porta gravada antes do limite
        qtd, ajustada = _portas._ajustar_dobradicas(comprimento, qtd, margem)
        referencia = p.get('dobradicas_referencia', {}).get(str(i))
        distancias = (_portas._posicoes_ferragens(comprimento, qtd, ajustada)
                      if referencia is None else [float(f) * comprimento for f in referencia])
        if referencia is not None:
            # Ao encolher demais o vao, o limite fisico ainda prevalece.
            minimo = _portas.PASSO_MIN_DOBRADICAS_MM
            if (any(d < _portas.MARGEM_MIN_DOBRADICAS_MM or
                    d > comprimento - _portas.MARGEM_MIN_DOBRADICAS_MM for d in distancias)
                    or any(b - a < minimo for a, b in zip(distancias, distancias[1:]))):
                distancias = _portas._posicoes_ferragens(comprimento, qtd, ajustada)
        saida.append((aresta, distancias, i))
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
                       float(p.get('pistoes_offset_mm', 0.0) or 0.0),
                       dict(p, basculante_invertida=False))
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
    if p.get('basculante_invertida'):
        centro = 2 * folhas[0][3][1]
        for item in saida:
            if 'origem' in item:
                v = item['origem'].copy(); v.y = centro-v.y; item['origem'] = v
            if 'cantos' in item:
                item['cantos'] = [Vector((v.x, centro-v.y, v.z)) for v in item['cantos']]
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


def _volume_articulacao(p, folhas, i, y, sufixo):
    """Volumetria nativa: placas, linguetas intercaladas, eixo e parafusos.

    Cada metade pertence a uma folha; o eixo coincide com o da abertura.
    E' representacao geometrica, sem importar ferragens do Promob.
    """
    l, a, e, c = folhas[i]
    zig = p.get('abertura') == 'ZIGZAG'
    sinal = 1 if _lado_da_folha(p, i, len(folhas)) == 'ESQUERDA' else -1
    if zig:
        q = _junta_zigzag(p, folhas[i - 1], folhas[i], i)
        face = 1 if i % 2 == 0 else -1
        apoio = i - 1
        plano_apoio = folhas[apoio][3][2] + face * folhas[apoio][2] / 2
    else:
        gap = float(p.get('dobradica_junta_mm', 4)) / 2
        q = Vector((c[0] - sinal * (l / 2 + gap), y, c[2] - e / 2 - 4.5))
        face, apoio = -1, None
        plano_apoio = float(p.get('dobradica_apoio_plano_mm', 0))
    q.y = y
    saida = []
    def caixa(nome, pai, x0, x1, z0, z1, h=50):
        lo, hi = Vector((min(x0, x1), y - h / 2, min(z0, z1))), Vector((max(x0, x1), y + h / 2, max(z0, z1)))
        cantos = [Vector((x, yy, z)) for x in (lo.x, hi.x) for yy in (lo.y, hi.y) for z in (lo.z, hi.z)]
        saida.append(dict(id=sufixo + nome, nome='Dobradica Articulada ' + nome,
                         tipo='DOBRADICA' if pai == apoio else 'CANECO',
                         folha=pai, forma='CAIXA', cantos=cantos))
    for nome, pai, direcao, plano, faixas in (
            ('Apoio', apoio, -sinal, plano_apoio, ((-25, -15), (-5, 5), (15, 25))),
            ('Folha', i, sinal, c[2] + face * e / 2, ((-14.5, -5.5), (5.5, 14.5)))):
        # A placa encosta na madeira. O pescoco liga-a ao eixo saliente.
        caixa('Placa ' + nome, pai, q.x + direcao * 5, q.x + direcao * 31, plano, plano + face * 3)
        caixa('Braco ' + nome, pai, q.x, q.x + direcao * 9, plano + face * 3, q.z, 30)
        for k, (baixo, cima) in enumerate(faixas):
            saida.append(dict(id=sufixo + nome + str(k), nome='Dobradica Articulada No ' + nome,
                tipo='DOBRADICA' if pai == apoio else 'CANECO', folha=pai, forma='CILINDRO',
                origem=Vector((q.x, y + (baixo + cima) / 2, q.z)),
                raio=4.5, comprimento=cima - baixo, eixo='Y'))
        for k, dy in enumerate((-17, 17)):
            # o parafuso padrao, assentado na face de fora da placa
            saida.append(dict(id=sufixo + 'Parafuso' + nome + str(k), nome='Dobradica Articulada Parafuso',
                tipo='DOBRADICA' if pai == apoio else 'CANECO', folha=pai, forma='PARAFUSO',
                origem=Vector((q.x + direcao * 23, y + dy, plano + face * 3)), sentido=face))
    saida.append(dict(id=sufixo + 'Eixo', nome='Dobradica Articulada Eixo', tipo='DOBRADICA',
        folha=apoio, forma='CILINDRO', origem=q, raio=2.5, comprimento=53, eixo='Y'))
    return saida


def _apoios_obliquos(conj, matriz, p, largura, altura, folhas):
    """Face REAL de apoio, por dobradica. Uma quina encostada nao e' encaixe.

    Ray cast nativo so' ao reconstruir; abrir pelo slider nao consulta
    malhas. A face inteira da placa precisa caber, sem entrar na madeira.
    """
    if (conj is None or p.get('abertura') not in ('GIRO', 'ZIGZAG')
            or p.get('dobradica_articulada') or _usa_rig(p)):
        return {}
    inversa = matriz.inverted()
    chapas = _modulos._estruturais(_modulos._chapas_do_conjunto(conj))
    apoios = {}
    for aresta, ds, i in _dobradicas_da_porta(p, largura, altura, folhas):
        if p.get('abertura') == 'ZIGZAG' and i > 0:
            continue
        e, centro = folhas[i][2:]
        costas = centro[2] - e / 2
        caixas = _portas._caixas_dobradicas(aresta, ds, costas)
        dentro = Vector((*aresta['dentro'], 0))
        direcao = (matriz.to_3x3() @ -dentro).normalized()
        for k, (_, caneco) in enumerate(caixas):
            c = sum(caneco, Vector()) / 8
            candidatos = []
            for obj in chapas:
                if obj.type != 'MESH' or obj.mode != 'OBJECT':
                    continue
                im = obj.matrix_world.inverted()
                dl = im.to_3x3() @ direcao
                profundidades = (15,25,35,45,55,65,75,95) if p.get('dobradica_apoio_real') else (25,35,45,55)
                for fundo in profundidades:
                    origem = matriz @ (Vector((c.x, c.y, costas - fundo)) / 1000)
                    hit, ponto, normal, face = obj.ray_cast(im @ origem,
                        dl.normalized(), distance=.12 * dl.length)
                    if not hit:
                        continue
                    nw = (im.to_3x3().transposed() @ normal).normalized()
                    n = (matriz.to_3x3().transposed() @ nw).normalized()
                    limite = 1.001 if p.get('dobradica_apoio_real') else .995
                    if abs(n.y) > .02 or not .15 < n.dot(dentro) < limite:
                        continue
                    q = inversa @ (obj.matrix_world @ ponto) * 1000
                    t = Vector((0, 1, 0)).cross(n).normalized()
                    if t.z < 0:
                        t = -t
                    cantos = [q + t * u + Vector((0, v, 0)) + n * z
                              for u in (-14, 14) for v in (-21, 21) for z in (0, 3)]
                    # As quatro quinas da face encostada, nao o menor erro
                    # entre todos os vertices (que aprovava uma ponta so').
                    cabe = True
                    for v in cantos[::2]:
                        local = im @ (matriz @ (v / 1000))
                        ok, perto, no, fi = obj.closest_point_on_mesh(local)
                        if (not ok or (obj.matrix_world.to_3x3() @ (local - perto)).length > .00005
                                or abs(no.dot(normal)) < .999):
                            cabe = False
                            break
                    if cabe:
                        candidatos.append((abs(fundo - 35), (q - c).length,
                            dict(objeto=obj, ponto=q, normal=n, cantos=cantos)))
            if candidatos:
                apoios[i, k] = min(candidatos, key=lambda a: a[:2])[2]
    return apoios


def _dobradica_obliqua(apoio, caneco, i, sufixo, costas):
    """Placa no plano da lateral e braco ligado a' folha por mira nativa."""
    q, n = apoio['ponto'], apoio['normal']
    copo = sum(caneco, Vector()) / 8
    ponta = Vector((copo.x, copo.y, costas - 5))
    origem = q + n * 4
    return [
        dict(id='DOBRADICA_' + sufixo, nome='Dobradica Base Angular', tipo='DOBRADICA',
             folha=None, forma='PRISMA', cantos=apoio['cantos'], apoio=apoio['objeto']),
        dict(id='ART_PONTA_' + sufixo, nome='Dobradica Mira Angular', tipo='DOBRADICA_PONTO',
             folha=i, forma='PONTO', origem=ponta),
        dict(id='ART_BRACO_' + sufixo, nome='Dobradica Braco Angular', tipo='DOBRADICA',
             folha=None, forma='BRACO', origem=origem, comprimento=(ponta - origem).length,
             destino=ponta, mira='ART_PONTA_' + sufixo),
    ]


def _ferragens_da_porta(p, largura, altura, folhas, apoios=None):
    """O que montar (mm, referencial do grupo, porta FECHADA): uma lista
    de {'id', 'tipo', 'folha' (indice; None = no grupo), 'forma', ...}."""
    saida = []
    rig = _usa_rig(p)
    for aresta, distancias, i in _dobradicas_da_porta(p, largura, altura, folhas):
        _l, _a, e, centro = folhas[i]
        if p.get('dobradica_articulada') or (p.get('abertura') == 'ZIGZAG' and i > 0):
            eixo = (aresta['b'] - aresta['a']).normalized()
            for k, d in enumerate(distancias):
                saida += _volume_articulacao(p, folhas, i, (aresta['a'] + eixo * d).y,
                                             'ART_%d_%d_' % (i, k))
            continue
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
                identificador = ('RIG_%d_%s_%d' % (i, aresta['lado'], k)
                    if p.get('dobradicas_lados_folhas') else 'RIG_%s_%d' % (aresta['lado'], k))
                saida.append({'id': identificador,
                              'tipo': 'DOBRADICA_RIG', 'folha': None,
                              'forma': 'RIG', 'indice_folha': i,
                              'calco': _calco_rig(aresta['cobertura']),
                              'matriz': _referencial_rig(
                                  aresta['dentro'], (ponto.x, ponto.y, fundo))})
            continue
        caixas = _portas._caixas_dobradicas(aresta, distancias, centro[2] - e / 2.0)
        for k, (corpo, caneco) in enumerate(caixas):
            sufixo = '%s_%d' % (aresta['lado'], k)
            if p.get('dobradicas_lados_folhas'):
                sufixo = '%d_%s' % (i, sufixo)
            apoio = (apoios or {}).get((i, k))
            if apoio:
                saida += _dobradica_obliqua(apoio, caneco, i, sufixo, centro[2] - e / 2)
            else:
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
        saida += _trilhos_correr(p, largura, altura, folhas)
    return saida


def _caixa_mm(x0, x1, y0, y1, z0, z1):
    return [Vector((x, y, z)) for x in (x0, x1) for y in (y0, y1)
            for z in (z0, z1)]


def _trilhos_correr(p, largura, altura, folhas):
    """Blocagem dos trilhos (foto do usuario), o vao inteiro de largura.
    CIMA: U alto -- chapa no topo e paredes por fora e entre os canais (no
    vao entre os planos), um canal por folha. BAIXO: chapa baixa com uma
    guia sob o meio de cada folha (ela fica em pe' nela). Com moldura,
    os perfis do usuario (`_trilhos_moldura`)."""
    if _portas._correr_sobreposta(p):
        return _trilhos_moldura(p, largura, altura)
    e = folhas[0][2]
    entre = float(p.get('entre_planos_mm', 0.0))
    frente = max(c[2] + e / 2.0 for _l, _a, _e, c in folhas)
    fundo = min(c[2] - e / 2.0 for _l, _a, _e, c in folhas)
    z0, z1 = fundo - TRILHO_PAREDE_MM, frente + TRILHO_PAREDE_MM
    # do vao inteiro (embutida) ou da cobertura (sobreposta): pelas folhas
    x0 = min(0.0, min(c[0] - l / 2.0 for l, _a, _e, c in folhas))
    x1 = max(largura, max(c[0] + l / 2.0 for l, _a, _e, c in folhas))
    y0 = min(c[1] - a / 2.0 for _l, a, _e, c in folhas) - altura_trilho_baixo()
    y1 = (max(c[1] + a / 2.0 for _l, a, _e, c in folhas)
          + TRILHO_LEVANTAR_MM + TRILHO_CIMA_CHAPA_MM)
    paredes = [(frente, z1), (z0, fundo)]
    for _l, _a, _e, c in folhas:
        costas = c[2] - e / 2.0
        if costas - 1e-6 > fundo:
            paredes.append((costas - entre, costas))
    topo = y1 - TRILHO_CIMA_CHAPA_MM
    cima = [_caixa_mm(x0, x1, topo, y1, z0, z1)]
    cima += [_caixa_mm(x0, x1, y1 - TRILHO_CIMA_ALTURA_MM, topo, a, b)
             for a, b in paredes if b - a > 1e-6]
    chapa = y0 + TRILHO_BAIXO_CHAPA_MM
    baixo = [_caixa_mm(x0, x1, y0, chapa, z0, z1)]
    meia = TRILHO_GUIA_LARGURA_MM / 2.0
    baixo += [_caixa_mm(x0, x1, chapa, y0 + altura_trilho_baixo(),
                        c[2] - meia, c[2] + meia)
              for _l, _a, _e, c in folhas]
    return [{'id': 'TRILHO_' + lado, 'tipo': 'TRILHO', 'nome': nome,
             'folha': None, 'forma': 'CAIXAS', 'caixas': caixas}
            for lado, nome, caixas in (('CIMA', 'Trilho Superior', cima),
                                       ('BAIXO', 'Trilho Inferior', baixo))]


def _trilhos_moldura(p, largura, altura):
    """Os dois perfis do usuario na largura da moldura (entre os
    revestimentos): o de cima com a folha entrando `INSERCAO_CANAL_MM`
    no canal, o de baixo sob o pe' dela, na base da moldura."""
    lateral = float(p['lateral_mm'])
    x = (-lateral, largura + lateral)
    trilho_cima, _base, base_baixo, _fundo = _portas._alturas_moldura(p, altura)
    costas = _portas.TRILHO_MOLDURA_COSTAS_MM
    if _portas._trilho_leve(p):
        # LEVE: o U de embutir do usuario dentro de cada canal fresado --
        # embaixo na face de cima da base, em cima espelhado na face de
        # baixo da base de cima. Chapa fina (pontas abertas), como o dele
        leve = perfil_trilho_moldura('LEVE')
        return [{'id': 'TRILHO_' + lado, 'tipo': 'TRILHO', 'nome': nome,
                 'folha': None, 'forma': 'PERFIL', 'x': x, 'aberto': True,
                 'poligonos': [[(costas + u, y0 + sinal * v) for u, v in poligono]
                               for poligono in leve['poligonos']]}
                for lado, nome, y0, sinal in (
                    ('CIMA', 'Trilho Superior', trilho_cima, -1.0),
                    ('BAIXO', 'Trilho Inferior', base_baixo, 1.0))]
    meio = costas + sum(CANAIS_TRILHO_MOLDURA_MM) / 2.0
    lugares = (('CIMA', 'Trilho Superior', costas, trilho_cima),
               ('BAIXO', 'Trilho Inferior', meio - MEIO_GUIAS_TRILHO_BAIXO_MM,
                base_baixo))
    return [{'id': 'TRILHO_' + lado, 'tipo': 'TRILHO', 'nome': nome,
             'folha': None, 'forma': 'PERFIL', 'x': x,
             # secao no referencial da porta: (z, y) em mm
             'poligonos': [[(z0 + u, y0 + v) for u, v in poligono]
                           for poligono in perfil_trilho_moldura(lado)['poligonos']]}
            for lado, nome, z0, y0 in lugares]


def _limites_perfil(item):
    """(lo, hi) em mm da caixa do perfil extrudado."""
    pontos = [zy for poligono in item['poligonos'] for zy in poligono]
    lo = Vector((item['x'][0], min(y for _z, y in pontos), min(z for z, _y in pontos)))
    hi = Vector((item['x'][1], max(y for _z, y in pontos), max(z for z, _y in pontos)))
    return lo, hi


def _origem_da_ferragem(item):
    if item['forma'] == 'PERFIL':
        lo, hi = _limites_perfil(item)
        return (lo + hi) / 2.0
    if item['forma'] in {'CAIXA', 'PRISMA'}:
        return sum(item['cantos'], Vector()) / len(item['cantos'])
    if item['forma'] == 'CAIXAS':
        cantos = [v for caixa in item['caixas'] for v in caixa]
        lo = Vector(tuple(min(v[k] for v in cantos) for k in range(3)))
        hi = Vector(tuple(max(v[k] for v in cantos) for k in range(3)))
        return (lo + hi) / 2.0
    return Vector(item['origem'])


def _malha_da_ferragem(malha, item):
    """Caixa (centrada), caneco (cilindro em Z, centrado) ou metade de
    pistao (cilindro de 0 a +Y: o Damped Track aponta o Y para a mira)."""
    bm = bmesh.new()
    try:
        if item['forma'] == 'PERFIL':
            # cada poligono da secao extrudado de x0 a x1 (o perfil do
            # usuario e' feito de pedacos sobrepostos: um prisma por pedaco)
            origem = _origem_da_ferragem(item)
            # `aberto` (o U do trilho leve): chapa fina, contorno sem
            # fechar e sem tampas, como a malha do usuario
            aberto = item.get('aberto', False)
            for poligono in item['poligonos']:
                pontas = [[bm.verts.new((Vector((x, y, z)) - origem) / 1000.0)
                           for z, y in poligono] for x in item['x']]
                n = len(poligono)
                for i in range(n - 1 if aberto else n):
                    j = (i + 1) % n
                    bm.faces.new((pontas[0][i], pontas[0][j],
                                  pontas[1][j], pontas[1][i]))
                if not aberto:
                    bm.faces.new(pontas[0][::-1])
                    bm.faces.new(pontas[1])
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        elif item['forma'] == 'PRISMA':
            # Preservar os cantos orientados: uma AABB desorientava a base
            # de 135 graus e voltava a entrar na madeira.
            origem = _origem_da_ferragem(item)
            vs = [bm.verts.new((v - origem) / 1000) for v in item['cantos']]
            for face in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
                         (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
                bm.faces.new([vs[k] for k in face])
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        elif item['forma'] == 'BRACO':
            novos = bmesh.ops.create_cube(bm, size=1)['verts']
            bmesh.ops.scale(bm, vec=(.012, item['comprimento'] / 1000, .006), verts=novos)
            bmesh.ops.translate(bm, vec=(0, item['comprimento'] / 2000, 0), verts=novos)
        elif item['forma'] in {'CAIXA', 'CAIXAS'}:
            # varias caixas numa malha so', em volta da origem do item
            origem = _origem_da_ferragem(item)
            for cantos in item.get('caixas') or [item['cantos']]:
                lo = Vector(tuple(min(v[k] for v in cantos) for k in range(3)))
                hi = Vector(tuple(max(v[k] for v in cantos) for k in range(3)))
                novos = bmesh.ops.create_cube(bm, size=1.0)['verts']
                bmesh.ops.scale(bm, vec=(hi - lo) / 1000.0, verts=novos)
                bmesh.ops.translate(bm, vec=((lo + hi) / 2.0 - origem) / 1000.0,
                                    verts=novos)
        elif item['forma'] == 'PARAFUSO':
            # cabeca para fora da placa (`sentido` em Z), haste na madeira
            modelo = malha_parafuso()
            if modelo is not None:
                bm.from_mesh(modelo)
                if item.get('sentido', 1) < 0:
                    bmesh.ops.rotate(bm, cent=(0, 0, 0), verts=bm.verts,
                                     matrix=Matrix.Rotation(math.pi, 3, 'X'))
                malha.materials.clear()
                for material in modelo.materials:
                    malha.materials.append(material)
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
            elif item.get('eixo') == 'Y':
                bmesh.ops.rotate(bm, cent=(0, 0, 0), verts=bm.verts,
                                 matrix=Matrix.Rotation(-math.pi / 2, 3, 'X'))
        bm.to_mesh(malha)
    finally:
        bm.free()
    malha.update()


def _ferragens_portas(grupo):
    return [o for o in grupo.children_recursive
            if CHAVE_FERRAGEM in o and _grupo_da_ferragem(o) == grupo]


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
    partes = [*obj.children_recursive, obj]
    dados = {o.data for o in partes if o.data is not None and o.type in DADOS_POR_TIPO}
    # Uma remocao nativa evita refazer as referencias da cena por parafuso.
    bpy.data.batch_remove(ids=partes)
    sem_usuarios = [d for d in dados if d.users == 0]
    if sem_usuarios:
        bpy.data.batch_remove(ids=sem_usuarios)


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


def preparar_malhas_para_editar(context, malhas):
    """O espelho precisa virar vertices antes de mover a dobradica no Tab.

    Copias unicas conservam a geometria avaliada e o rig. Materializar
    na ordem da pilha preserva tambem espelhos posteriores a subdivisao.
    """
    for obj in malhas:
        if CHAVE_FERRAGEM not in obj or obj.get('cabinet_peca') in PECAS_OCULTAS_RIG:
            continue
        espelhos = [i for i, m in enumerate(obj.modifiers) if m.type == 'MIRROR' and m.show_viewport]
        if not espelhos:
            continue
        aplicar = [m.name for i, m in enumerate(obj.modifiers)
                   if i <= espelhos[-1] and m.show_viewport]
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        with context.temp_override(object=obj, active_object=obj,
                selected_objects=[obj], selected_editable_objects=[obj]):
            for nome in aplicar:
                bpy.ops.object.modifier_apply(modifier=nome)


def iniciar_edicao_rigs(malhas, recuperar=False):
    """So' nomes e numeros: o undo pode liberar os objetos desta edicao."""
    registros = {}
    for obj in malhas:
        raiz = obj
        while raiz is not None and raiz.get('cabinet_peca') != 'raiz':
            raiz = raiz.parent
        if raiz is not None:
            if recuperar:
                pontos = list(obj.data.get('cabinet_rig_edicao', ()))
                matriz = list(obj.data.get('cabinet_rig_edicao_matriz', ()))
                if not pontos or len(matriz) != 16:
                    continue
            else:
                pontos = [c for v in obj.data.vertices for c in v.co]
                matriz = [c for linha in raiz.matrix_basis for c in linha]
                # A referencia entra no undo nativo da Mesh. So' o estado
                # Python se perde ao desfazer a saida do Edit Mode.
                obj.data['cabinet_rig_edicao'] = pontos
                obj.data['cabinet_rig_edicao_matriz'] = matriz
            registro = registros.setdefault(raiz.name, dict(matriz=matriz, pecas={}))
            registro['pecas'][obj.name] = [
                tuple(pontos[i:i + 3]) for i in range(0, len(pontos), 3)]
    return registros


def concluir_edicao_rigs(registros):
    """Translacao rigida das pecas move a montagem inteira, inclusive o furo.

    Modelar vertices de uma peca continua nativo. Deslocar uma ou varias
    pecas inteiras leva a dobradica, sem deformar bracos, IK ou parafusos.
    """
    if bpy.context.mode != 'OBJECT' or _eventos._desfazendo[0]:
        return
    bpy.context.view_layer.update()
    for nome, registro in registros.items():
        raiz = bpy.data.objects.get(nome)
        if raiz is None or raiz.get('cabinet_peca') != 'raiz':
            continue
        movidas, deslocamento = [], None
        for nome_peca, pontos in registro['pecas'].items():
            obj = bpy.data.objects.get(nome_peca)
            if (obj is None or obj.type != 'MESH' or obj.data.is_editmode
                    or len(obj.data.vertices) != len(pontos) or not pontos):
                break
            delta = obj.data.vertices[0].co - Vector(pontos[0])
            if any((v.co - Vector(p) - delta).length > .000001
                   for v, p in zip(obj.data.vertices, pontos)):
                break
            if delta.length < .000001:
                continue
            mundo = obj.matrix_world.to_3x3() @ delta
            if deslocamento is not None and (mundo - deslocamento).length > .000001:
                break
            deslocamento = mundo
            movidas.append((obj, delta))
        else:
            if not movidas:
                continue
            grupo = _grupo_da_ferragem(raiz)
            if grupo is None:
                continue
            # Devolver a translacao da madeira da ferragem para a raiz
            # preserva a mesma Mesh e faz auxiliares/curvas acompanharem.
            for obj, delta in movidas:
                obj.data.transform(Matrix.Translation(-delta))
                obj.data.update()
            matriz = registro['matriz']
            matriz = Matrix([matriz[i:i + 4] for i in range(0, 16, 4)])
            matriz.translation += grupo.matrix_world.inverted_safe().to_3x3() @ deslocamento
            # Undo de Edit Mode pode conservar a raiz ja' deslocada pela
            # saida anterior. A pose inicial impede aplicar o delta duas vezes.
            aplicado = matriz.translation - raiz.matrix_basis.translation
            raiz.matrix_basis = matriz
            anterior = Vector(raiz.get('porta_ferragem_deslocamento_mm', (0, 0, 0)))
            raiz['porta_ferragem_deslocamento_mm'] = anterior + aplicado * 1000
            bpy.context.view_layer.update()
    for registro in registros.values():
        for nome in registro['pecas']:
            obj = bpy.data.objects.get(nome)
            if obj is not None and obj.type == 'MESH':
                obj.data.pop('cabinet_rig_edicao', None)
                obj.data.pop('cabinet_rig_edicao_matriz', None)


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
    vieram antes (mesmo `cabinet_origem` e `cabinet_versao`) voltam aos de
    antes: o arquivo nao incha a cada porta. A versao separa o asset
    refeito com o mesmo nome (o parafuso) da copia velha da cena."""
    antes = {nome: set(getattr(bpy.data, nome)) for nome in COLECOES_DO_RIG}
    with bpy.data.libraries.load(caminho, link=False) as (origem, destino):
        setattr(destino, tipo, sorted(n for n in getattr(origem, tipo)
                                      if nomes is None or n in nomes))
    novos = [d for d in getattr(destino, tipo) if d is not None]
    chave_de = lambda d: (d.get('cabinet_origem'), d.get('cabinet_versao'))
    for nome in COLECOES_DO_RIG:
        dados = getattr(bpy.data, nome)
        velhos = {}
        for dado in antes[nome]:
            if dado.get('cabinet_origem'):
                velhos.setdefault(chave_de(dado), []).append(dado)
        for novo in [d for d in dados if d not in antes[nome]]:
            chave = chave_de(novo)
            atributos = ({a.name: (a.domain, a.data_type) for a in novo.attributes}
                         if nome == 'meshes' else None)
            # Tab conserva a marca do asset; so' o comparador nativo distingue
            # a malha original de uma copia modelada ou com Mirror aplicado.
            igual = next((d for d in velhos.get(chave, ()) if nome != 'meshes'
                or (len(d.vertices) == len(novo.vertices)
                    and {a.name: (a.domain, a.data_type) for a in d.attributes} == atributos
                    and d.unit_test_compare(mesh=novo, threshold=1e-7) == 'Same')), None)
            if chave[0] and igual is not None:
                novo.user_remap(igual)
                dados.remove(novo)
            elif chave[0]:
                velhos.setdefault(chave, []).append(novo)
    return [d for d in novos if _vivo(d)]


def parafuso_atual(malha):
    """A malha e' o parafuso padrao DESTA versao?"""
    return (malha.get('cabinet_origem') == NOME_PARAFUSO
            and malha.get('cabinet_versao') == VERSAO_PARAFUSO)


def malha_parafuso():
    """A malha do parafuso padrao (carregada uma vez; deduplicada pelo
    `cabinet_origem`), ou None sem o asset. A da cena vale no lugar da do
    asset: o arame dela e' acertado aqui (`marcar_arame_parafuso`)."""
    malha = next((m for m in bpy.data.meshes if parafuso_atual(m) and not m.library), None)
    if malha is None and os.path.exists(ARQUIVO_PARAFUSO):
        novas = _anexar_sem_repetir(ARQUIVO_PARAFUSO, 'meshes', {NOME_PARAFUSO})
        malha = novas[0] if novas else None
    if malha is not None:
        _arame.marcar_arame_parafuso(malha)
    return malha


def _copiar_rig(modelo):
    """Copia Objects nativos; pais, IK e drivers ficam dentro da nova dobradica."""
    partes = [modelo, *modelo.children_recursive]
    copias = {o: o.copy() for o in partes}
    for original, copia in copias.items():
        if original.parent in copias:
            copia.parent = copias[original.parent]
        # Trocar o pai reinicializa a inversa; conservar o referencial do asset.
        copia.matrix_parent_inverse = original.matrix_parent_inverse.copy()
        componentes = [*copia.constraints, *copia.modifiers]
        if copia.pose is not None:
            componentes += [c for osso in copia.pose.bones for c in osso.constraints]
        for componente in componentes:
            for prop in componente.bl_rna.properties:
                if prop.type != 'POINTER' or prop.is_readonly:
                    continue
                alvo = getattr(componente, prop.identifier)
                if isinstance(alvo, bpy.types.Object) and alvo in copias:
                    setattr(componente, prop.identifier, copias[alvo])
        if copia.animation_data is not None:
            for curva in copia.animation_data.drivers:
                for variavel in curva.driver.variables:
                    for alvo in variavel.targets:
                        if isinstance(alvo.id, bpy.types.Object) and alvo.id in copias:
                            alvo.id = copias[alvo.id]
    return list(copias.values())


def _instanciar_rig(colecao, raiz_id, modelo=None):
    """Carrega o asset uma vez na montagem; demais rigs copiam a instancia nova."""
    objetos = (_copiar_rig(modelo) if modelo is not None else
               _anexar_sem_repetir(ARQUIVO_DOBRADICA_RETA, 'objects'))
    id_modelo = modelo.get(CHAVE_ID_FERRAGEM) if modelo is not None else None
    raiz = None
    for i, o in enumerate(objetos):
        colecao.objects.link(o)
        peca = o.get('cabinet_peca', 'peca')
        o[CHAVE_FERRAGEM] = TIPO_DA_PECA_RIG.get(peca, 'DOBRADICA_PECA')
        o[CHAVE_ID_FERRAGEM] = (raiz_id + o[CHAVE_ID_FERRAGEM][len(id_modelo):]
            if id_modelo else raiz_id if peca == 'raiz' else '%s:%02d' % (raiz_id, i))
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


def _ajustar_espaco_miras(grupo):
    """O braco angular acompanha o espelho pelo referencial comum da porta."""
    for obj in _ferragens_portas(grupo):
        for r in obj.constraints:
            if r.type == 'STRETCH_TO' and r.name == NOME_MIRA_PISTAO:
                # Em WORLD o solver inverte a espessura do braco no Mirror.
                if r.owner_space != 'CUSTOM' or r.target_space != 'CUSTOM' or r.space_object != grupo:
                    r.owner_space = r.target_space = 'CUSTOM'
                    r.space_object = grupo


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
    modelo_rig = None
    conj = _portas._modulo_da_chapa(folhas[0]) if folhas else None
    matriz = (_matriz_fechada(grupo.parent) @ grupo.matrix_basis
              if grupo.get('porta_apoio_folha') else grupo.matrix_world.copy())
    apoios = _apoios_obliquos(conj, matriz, parametros, largura, altura, calculadas)
    for item in _ferragens_da_porta(parametros, largura, altura, calculadas, apoios):
        obj = existentes.pop(item['id'], None)
        deslocamento_rig = (tuple(obj.get('porta_ferragem_deslocamento_mm', (0, 0, 0)))
                           if obj is not None and _vivo(obj) else (0, 0, 0))
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
                obj = _instanciar_rig(colecao, item['id'], modelo=modelo_rig)
                if obj is None:
                    continue
                if modelo_rig is None:
                    modelo_rig = obj
            obj['porta_ferragem_deslocamento_mm'] = deslocamento_rig
            obj.parent = grupo
            obj.matrix_parent_inverse = Matrix.Identity(4)
            matriz = item['matriz'].copy()
            matriz.translation = matriz.translation / 1000.0
            matriz.translation += Vector(obj.get('porta_ferragem_deslocamento_mm', (0, 0, 0))) / 1000
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
        if item.get('apoio') is not None:
            obj['porta_ferragem_apoio'] = item['apoio']
        elif 'porta_ferragem_apoio' in obj:
            del obj['porta_ferragem_apoio']
        if not ponto:
            if obj.data.users > 1:
                obj.data = obj.data.copy()
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
        if (pai.get('porta_curva_modelada') and item['tipo']=='CANECO'
                and item['forma']=='CILINDRO'):
            # A flecha ocupa parte da espessura util sob o copo. Sentar
            # o volume na superficie REAL, sem atravessar a face visivel.
            # BVH nativo so' ao montar; abrir/hover nao faz estas consultas.
            zmax=max(v.co.z for v in pai.data.vertices)+.1
            fronts=[]
            for j in range(16):
                angulo=j*math.tau/16
                x=origem.x/1000+item['raio']/1000*math.cos(angulo)
                y=origem.y/1000+item['raio']/1000*math.sin(angulo)
                hit,ponto,_n,_face=pai.ray_cast(Vector((x,y,zmax)),Vector((0,0,-1)))
                if hit:fronts.append(ponto.z)
            if fronts:
                topo=origem.z/1000+item['comprimento']/2000
                if topo>min(fronts)-.0005:
                    obj.location.z-=topo-min(fronts)+.0005
        if item['forma'] == 'BRACO':
            y = (item['destino'] - item['origem']).normalized()
            x = Vector((0, 1, 0))
            pose = Matrix((x, y, x.cross(y))).transposed().to_4x4()
            pose.translation = origem / 1000
            obj.matrix_basis = pose
        feitos[item['id']] = (obj, item)
    for obj, item in feitos.values():
        mira = feitos.get(item.get('mira'), (None, None))[0]
        restricoes = [r for r in obj.constraints if r.name == NOME_MIRA_PISTAO]
        if mira is None:
            for r in restricoes:
                obj.constraints.remove(r)
            continue
        tipo = 'STRETCH_TO' if item['forma'] == 'BRACO' else 'DAMPED_TRACK'
        for r in list(restricoes):
            if r.type != tipo:
                obj.constraints.remove(r)
                restricoes.remove(r)
        r = restricoes[0] if restricoes else obj.constraints.new(tipo)
        r.name = NOME_MIRA_PISTAO
        r.target = mira
        if tipo == 'STRETCH_TO':
            r.rest_length = item['comprimento'] / 1000
            r.volume = 'NO_VOLUME'
            r.keep_axis = 'PLANE_X'
        else:
            r.track_axis = 'TRACK_Y'
    for obj in existentes.values():
        _remover_ferragem(obj)
    _furar_folhas(folhas, cortadores)
    _ajustar_espaco_miras(grupo)
    _girar_rigs(grupo)
    grupo['porta_ferragens_encaixe'] = 1


_contagem_objetos = [-1]    # o handler so' confere quando ela muda


def _conferir_ferragens():
    """Timer: ferragem nao acende com a porta, entao apagar ou duplicar a
    porta nao a leva. Ferragem sem porta sai; porta sem
    nenhuma (duplicada, ou de antes da Fase 3) ganha as dela. De quebra,
    Empty de amarracao de arquivo/preset antigo fica invisivel."""
    # O timer agendado pelo depsgraph pode sobreviver ao inicio de Tab,
    # undo ou de outro operador: adiar, sem perder a limpeza pendente.
    if (_eventos._desfazendo[0] or _chapas._ocupado[0]
            or bpy.context.mode != 'OBJECT' or _eventos._ha_modal_ativo()):
        return _eventos.INTERVALO_TIMER
    try:
        for o in bpy.data.objects:
            if (o.type == 'EMPTY'
                    and any(m in o for m in (_chapas.MARCA_CONJUNTO, _chapas.MARCA_PORTAS,
                                             CHAVE_FERRAGEM))
                    and o.empty_display_size > _chapas.TAMANHO_EMPTY_OCULTO * 1.5):
                _chapas._ocultar_empty(o)
        portas_vivas = {g.name for g in bpy.data.objects
                        if _chapas.MARCA_PORTAS in g and _portas._folhas_portas(g)}
        residuos = set()
        for o in bpy.data.objects:
            if (CHAVE_FERRAGEM not in o or o.library is not None
                    or o.override_library is not None):
                continue
            dono = _grupo_da_ferragem(o)
            if dono is None or dono.name not in portas_vivas:
                residuos.add(o)
        # Nunca levar junto um filho comum do usuario. Conserva tambem
        # seus pais, para nao alterar a transformacao de quem fica.
        protegidos = {o for o in residuos if any(c not in residuos for c in o.children)}
        for o in list(protegidos):
            pai = o.parent
            while pai in residuos:
                protegidos.add(pai)
                pai = pai.parent
        for o in residuos - protegidos:
            dados, colecao = o.data, DADOS_POR_TIPO.get(o.type)
            bpy.data.objects.remove(o, do_unlink=True)
            if dados is not None and colecao and dados.users == 0:
                getattr(bpy.data, colecao).remove(dados)
        for grupo in [o for o in bpy.data.objects
                      if _chapas.MARCA_PORTAS in o and o.get('porta_parametros')]:
            _ajustar_espaco_miras(grupo)
            if _portas._folhas_portas(grupo) and not _ferragens_portas(grupo):
                _refazer_ferragens(grupo)
            elif _ferragens_antigas(grupo):
                _refazer_ferragens(grupo)
            elif not grupo.get('porta_ferragens_encaixe'):
                atualizar_encaixe_antigo(grupo)
        _modulos.limpar_organizacao_vazia()
        _orcamento._limpar_comodos_vazios()
    except Exception as e:
        print("[Cabinet Creator] ferragens:", e)
    return None


def _ferragens_antigas(grupo):
    """Rig da Reta de outra versao do asset ou parafuso que nao e' o padrao
    atual. Relato do usuario: os presets da biblioteca e as cenas guardam a
    Reta original, com o parafuso de REGULAGEM do braco nas placas de
    fixacao, e so' refazendo a porta ela vinha nova. O timer troca UMA vez
    (refeita, a versao bate)."""
    dados = _dados_dobradica_reta()
    versao = int(dados.get('versao', 1)) if dados else None
    for o in _ferragens_portas(grupo):
        if (versao is not None and o.get('cabinet_peca') == 'raiz'
                and int(o.get('cabinet_versao', 1)) != versao):
            return True
        malha = o.data if o.type == 'MESH' else None
        if malha is not None and (malha.get('cabinet_origem') in PARAFUSOS_ANTIGOS or (
                malha.get('cabinet_origem') == NOME_PARAFUSO and not parafuso_atual(malha))):
            return True
    return False


def atualizar_encaixe_antigo(grupo):
    """Preset/cena anterior: atualizar so' os volumes com apoio obliquo.
    As pecas editadas de outros modelos, o rig e a abertura sobrevivem.
    """
    folhas = _portas._folhas_portas(grupo)
    if not folhas or any(o.mode != 'OBJECT' for o in grupo.children_recursive):
        return False
    p, L, A, calculadas = _porta_calculada(grupo)
    conj = _portas._modulo_da_chapa(folhas[0])
    apoios = _apoios_obliquos(conj, grupo.matrix_world, p, L, A, calculadas)
    if apoios:
        _refazer_ferragens(grupo)
    else:
        grupo['porta_ferragens_encaixe'] = 1
    return bool(apoios)


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
                'info': ('Articulada' if p.get('dobradica_articulada') else
                         'Reta' if _usa_rig(p) else
                         _portas.NOME_DOBRADICA.get(p.get('dobradica'), '')),
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
    'PISTAO_SUPORTE': 'PISTAO',
    'TRILHO': 'TRILHO'}             # do correr: so' o arame, nada a editar
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
             'PISTAO_SUPORTE', 'DOBRADICA_PECA', 'TRILHO')
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
        # Os parametros INTEIROS: arrastar apaga `dobradicas_referencia`
        # (arranjo medido do Promob), que so' a margem nao traz de volta.
        self._antes = _portas._copiar_parametros(grupo['porta_parametros'])
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
        self._refazer(context, _portas._editar_parametro_porta(
            context, grupo, self._nome, valor))

    def _restaurar(self, context):
        grupo = bpy.data.objects.get(self.grupo)
        if (grupo is not None and
                _portas._copiar_parametros(grupo['porta_parametros']) != self._antes):
            self._refazer(context, _portas._refazer_porta(context, grupo, self._antes))

    def _refazer(self, context, erro):
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
            self._restaurar(context)
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
