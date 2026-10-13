"""Portas parametricas: parametros, vao, cobertura, calculo das folhas,
vinculo com o modulo, o ima do apanhador e as constantes e contas do
wizard (pistoes, caixas das dobradicas); o modal mora em `assistente`."""

import bpy, bmesh, math
from mathutils import Matrix, Vector

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _modulos = _ferragens = _puxadores = None

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
# A FRENTE nao e' escolha: sai sempre da diagonal (`_frente_automatica`).
# As espessuras tambem nao: a da lateral e' a do modulo e a da porta
# se edita no campo E da folha, como a de qualquer chapa.
# Os EIXOS do vao tambem nao: saem do vinculo (a corrente) -- porta do
# modulo usa os eixos dele, porta solta usa o mundo (`_referencia_do_par`).
ESCOLHAS_PORTAS = (
    ('porta_abertura', 'Abertura', (('GIRO', 'Giro'),
                                    ('BASCULANTE', 'Basculante'),
                                    ('CORRER', 'Correr'))),
)
# (prop em metros, prop em mm, rotulo, minimo em mm)
MEDIDAS_PORTAS = (
    ('ui_porta_entre_folhas', 'porta_entre_folhas_mm', 'Entre folhas', 0.0),
    ('ui_porta_afastamento', 'porta_afastamento_mm', 'Afastamento', 0.0),
    ('ui_porta_recuo_embutida', 'porta_recuo_embutida_mm',
     'Recuo da embutida', 0.0),
    ('ui_porta_recuo_correr', 'porta_recuo_correr_mm',
     'Recuo para trilhos', 0.1),
    ('ui_porta_entre_planos', 'porta_entre_planos_mm',
     'Entre planos', 0.1),
    # moldura da porta de correr (pedido do usuario: editaveis)
    ('ui_porta_moldura', 'porta_moldura_mm', 'Espessura', 1.0),
    ('ui_porta_rodape', 'porta_rodape_mm', 'Rodape', 0.0),
    ('ui_porta_testeira', 'porta_testeira_mm', 'Testeira', 0.0),
)
# padrao das medidas da porta (as que nao comecam em zero)
PADRAO_MEDIDAS_PORTAS = {'porta_entre_folhas_mm': 2.0,
                         'porta_recuo_correr_mm': 30.0,
                         'porta_entre_planos_mm': 2.0,
                         # moldura: tudo 15 mm (pedido do usuario); rodape
                         # e testeira do guarda-roupa de exemplo dele
                         'porta_moldura_mm': 15.0,
                         'porta_rodape_mm': 100.0,
                         'porta_testeira_mm': 80.0}


# Campo da gaveta -> parametro do grupo, para editar uma porta colocada.
_PARAMETRO_DA_MEDIDA_PORTA = dict(
    [(m[0], m[1][len('porta_'):]) for m in MEDIDAS_PORTAS]
    + [('ui_porta_espessura', 'espessura_mm'),
       ('ui_porta_largura_folha', 'largura_folha_mm')])


def _parametros_portas_da_cena(s, numerico=False):
    """Os mesmos nomes que `_PARAMETROS_PORTAS` espera.

    As espessuras nao moram mais na Scene: saem do modulo na hora de
    criar (`_espessura_do_vao`). Aqui vai so' o padrao, para o
    dicionario continuar completo. No operador elas sao Enum -- ou
    seja, STRING --, mas `_calcular_folhas_portas` faz conta com elas
    e quebra com texto: quem for calcular direto pede `numerico=True`.
    """
    converter = float if numerico else (lambda v: v)
    padrao = '%d' % ESPESSURA_PADRAO_PORTA
    return {
        'abertura': s.porta_abertura,
        'folhas': s.porta_folhas,
        'dobradica': s.porta_dobradica,
        'espessura_mm': converter(padrao),
        'lateral_mm': converter(padrao),
        # sem campo (pedido do usuario: sempre zero); so' a porta importada
        # grava uma, para nascer onde estava (`importacao`)
        'folga_mm': 0.0,
        'entre_folhas_mm': s.porta_entre_folhas_mm,
        'afastamento_mm': s.porta_afastamento_mm,
        'recuo_embutida_mm': s.porta_recuo_embutida_mm,
        'recuo_correr_mm': s.porta_recuo_correr_mm,
        'entre_planos_mm': s.porta_entre_planos_mm,
        # Ferragens (wizard de criacao): 0 = automatico pela medida da
        # folha (`_qtd_dobradicas_padrao`, `_qtd_pistoes_padrao`,
        # `_pistao_do_vao`); o wizard grava os escolhidos.
        'dobradica_lado': 'ESQUERDA',
        'dobradicas_qtd': 0,
        'dobradicas_margem_mm': MARGEM_DOBRADICAS_PADRAO,
        'pistoes_qtd': 0,
        'pistoes_offset_mm': 0.0,
    }


def _carregar_portas_na_cena(s, grupo):
    """Traz os parametros de um grupo existente para a gaveta."""
    guardados = grupo.get('porta_parametros') or {}
    for nome, valor in guardados.items():
        if nome in {'espessura_mm', 'lateral_mm'}:
            continue    # moram no grupo e no modulo, nao na aba
        elif nome == 'folhas':
            s.porta_folhas = int(valor)
        elif nome in {'abertura', 'dobradica', 'trilho', 'folha'}:
            setattr(s, 'porta_' + nome, valor)
        elif nome in _PARAMETROS_PORTAS and hasattr(s, 'porta_' + nome):
            # as ferragens do wizard (lado, quantidades) moram so' na porta
            setattr(s, 'porta_' + nome, float(valor))


_PARAMETROS_PORTAS = (
    'abertura', 'folhas', 'dobradica', 'espessura_mm', 'lateral_mm',
    'folga_mm', 'entre_folhas_mm', 'afastamento_mm', 'recuo_embutida_mm',
    'recuo_correr_mm', 'entre_planos_mm',
    'moldura_mm', 'rodape_mm', 'testeira_mm', 'trilho', 'folha',
    'dobradica_lado', 'dobradicas_qtd', 'dobradicas_margem_mm',
    'pistoes_qtd', 'pistoes_offset_mm',
)


def _grupo_portas(obj):
    if obj is not None and _chapas.MARCA_PORTAS in obj:
        return obj
    if (obj is not None and _chapas.MARCA_FOLHA in obj and obj.parent is not None
            and _chapas.MARCA_PORTAS in obj.parent):
        return obj.parent
    return None


def _folhas_portas(grupo):
    return sorted((o for o in grupo.children if _chapas.MARCA_FOLHA in o),
                  key=lambda o: o.get('porta_indice', 0))


def _capturar_vertices_portas(context, com_objetos=False):
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
    resultado = marcados[0][1], marcados[1][1], referencia, pai
    return resultado + (marcados[0][0], marcados[1][0]) if com_objetos else resultado


def _referencia_do_par(obj_a, obj_b):
    """Orientacao do vao a partir do ancestral comum das duas pecas.

    E' o ancestral que da' os eixos do modulo; a rotacao individual de
    uma lateral nao serve, porque o Z local dela e' a espessura.
    """
    # O grupo de portas tem Y=altura; nao e' a base do armario.
    modulo = _modulo_da_chapa(obj_a)
    if modulo is not None and modulo == _modulo_da_chapa(obj_b):
        return modulo.matrix_world.to_quaternion().to_matrix(), modulo
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


NORMAIS_FRENTE = {'NEG_Y': (0, -1, 0), 'POS_Y': (0, 1, 0),
                  'NEG_X': (-1, 0, 0), 'POS_X': (1, 0, 0),
                  'NEG_Z': (0, 0, -1), 'POS_Z': (0, 0, 1)}
ESPESSURA_PADRAO_PORTA = 18.0


def _frente_automatica(referencia, ponto_a, ponto_b, centro):
    """Qual face o vao ocupa, deduzida dos dois pontos marcados.

    O eixo que NAO varia entre os dois pontos e' a normal da face --
    inclusive Z: diagonal puxada sem mudar a altura e' porta deitada
    (tampa de bau no canto alemao, por exemplo). O lado sai da
    comparacao com o centro do movel: o vao fica na face voltada para
    fora, nunca na oposta. Empate fica com Y, depois X: a frente comum.
    """
    base = referencia.transposed()
    a = base @ Vector(ponto_a)
    b = base @ Vector(ponto_b)
    c = base @ Vector(centro)
    eixo = min((1, 0, 2), key=lambda i: abs(a[i] - b[i]))
    return ('NEG_' if a[eixo] < c[eixo] else 'POS_') + 'XYZ'[eixo]


def _resolver_frente(frente, referencia, ponto_a, ponto_b, centro):
    if frente != 'AUTO':
        return frente
    return _frente_automatica(referencia, ponto_a, ponto_b, centro)


def _largura_do_vao(referencia, ponto_a, ponto_b):
    """Em porta deitada, por qual eixo corre a LARGURA ('X' ou 'Y').

    De pe' a altura e' sempre Z e isto nao importa. Deitada, a largura
    e' o lado MAIOR da diagonal: e' por ele que as folhas se dividem.
    O resultado fica gravado no grupo, senao um redimensionamento que
    invertesse os lados giraria a porta.
    """
    base = referencia.transposed()
    d = base @ (Vector(ponto_b) - Vector(ponto_a))
    return 'X' if abs(d.x) >= abs(d.y) else 'Y'


def _base_da_frente(referencia, frente, largura_em='X'):
    """Linhas (direita, cima, normal) do vao: X=largura, Y=altura, Z=fora."""
    normal = referencia @ Vector(NORMAIS_FRENTE[frente])
    if frente.endswith('Z'):
        cima = referencia @ Vector((0, 1, 0) if largura_em == 'X'
                                   else (1, 0, 0))
    else:
        cima = referencia @ Vector((0, 0, 1))
    return Matrix((cima.cross(normal).normalized(), cima, normal))


def _eixos_da_frente(frente, largura_em='X'):
    """Indices (largura, altura, normal) nos eixos do modulo."""
    if frente.endswith('Y'):
        return 0, 2, 1
    if frente.endswith('X'):
        return 1, 2, 0
    return (0, 1, 2) if largura_em == 'X' else (1, 0, 2)


def _espessura_do_vao(modulo, objetos=(), padrao=ESPESSURA_PADRAO_PORTA):
    """Espessura das chapas que fecham o vao: a da LATERAL.

    Era um campo da aba que repetia o E do modulo -- e quando os dois
    discordavam a porta sobrava para fora. Com modulo, vale o dele;
    sem modulo, a da chapa clicada.
    """
    if modulo is not None:
        caixa = _caixa_do_modulo(modulo)
        if caixa is not None and caixa[3] > 0:
            return _chapas._espessura_livre(caixa[3])
    for obj in objetos:
        if obj is not None and _chapas.MARCA_CHAPA in obj and _chapas.MARCA_FOLHA not in obj:
            return _chapas._espessura_livre(obj.chapa_espessura_mm)
    return float(padrao)


def _espessura_da_porta_nova(modulo, objetos=(), padrao=ESPESSURA_PADRAO_PORTA):
    """A porta nasce com a espessura do modulo; depois se edita no E da folha.

    Apoiada em outra porta, herda a dela: duas fileiras no mesmo
    modulo saem com a mesma espessura.
    """
    for obj in objetos:
        if obj is not None and _chapas.MARCA_FOLHA in obj:
            return float(obj.chapa_espessura_mm)
    return _espessura_do_vao(modulo, objetos, padrao)


def _centro_do_movel(obj_a, obj_b):
    """Ponto interno do movel, para saber que face olha para fora.

    Nao serve a origem do modulo: ela fica na BASE (ver
    `reposicionar_origem`), e uma porta na face de baixo sairia
    apontando para cima.
    """
    modulo = _modulo_da_chapa(obj_a)
    if modulo is not None:
        limites = _limites_locais_modulo(modulo)
        if limites is not None:
            lo, hi = limites
            return modulo.matrix_world @ ((lo + hi) / 2000.0)
        return modulo.matrix_world.translation.copy()
    limites = _modulos._limites_mundo(bpy.context, {obj_a, obj_b})
    if limites is None:
        return (Vector(obj_a.matrix_world.translation)
                + Vector(obj_b.matrix_world.translation)) / 2.0
    lo, hi, _n = limites
    return Vector(((lo[i] + hi[i]) / 2.0 for i in range(3)))


def _mapear_vao_portas(ponto_a, ponto_b, referencia, frente, largura_em=None):
    """Base ortonormal: X=largura, Y=altura, Z=fora do movel."""
    if largura_em is None:
        largura_em = _largura_do_vao(referencia, ponto_a, ponto_b)
    base = _base_da_frente(referencia, frente, largura_em).transposed()
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


# A folha NUNCA fica rente a' borda do armario (pedidos do usuario, com
# print): em toda cobertura padrao sobra este respiro. Reta = espessura
# MENOS ele; Curva = metade menos ele (duas portas dividindo a chapa do
# meio se encostavam: 18 mm -> 7 mm cada, 4 mm entre as folhas);
# embutida e correr = a borda ele para DENTRO do vao. A folga (`folga_mm`,
# sem campo: so' a importada grava) soma por cima. Cobertura fora do
# padrao (o usuario marcou o canto e confirmou) vale como marcada.
RESPIRO_PORTA_MM = 2.0


def _cobertura_mm(fracao, lateral):
    """mm que a folha cobre da chapa, pela fracao da espessura (negativo
    = a borda fica dentro do vao)."""
    if abs(fracao - 1.0) < 1e-9:
        return lateral - RESPIRO_PORTA_MM
    if abs(fracao - 0.5) < 1e-9:
        return max(0.0, lateral / 2.0 - RESPIRO_PORTA_MM)
    if abs(fracao) < 1e-9:
        return -RESPIRO_PORTA_MM
    return fracao * lateral


def _cobertura_porta(p):
    fracao = (0.0 if p['abertura'] == 'CORRER'
              else {'RETA': 1.0, 'CURVA': 0.5}.get(p['dobradica'], 0.0))
    return _cobertura_mm(fracao, p['lateral_mm'])


# Cobertura de cada lado da folha (esq, dir, baixo, cima: mesmo indice de
# `porta_ancora_*`) em FRACAO da espessura da lateral: 1 = cobre a chapa
# inteira, 0.5 = metade, 0 = borda no vao. Sai dos 4 cliques do wizard
# (canto da porta x canto do vao) ou do clique no meio da espessura; lado
# sem chave cobre o que a dobradica manda. Fracao, nao mm: a porta
# acompanha a espessura do modulo. Chaves soltas (nao lista: lista vira
# IDPropertyArray, que nem compara igual), fora de `_PARAMETROS_PORTAS`
# (sao do vao, nao padrao da cena).
COBERTURAS_LADOS = ('cobertura_esq_e', 'cobertura_dir_e',
                    'cobertura_baixo_e', 'cobertura_cima_e')
INDICE_LADO = {'ESQUERDA': 0, 'DIREITA': 1, 'BAIXO': 2, 'CIMA': 3}
TOL_COBERTURA_MM = 2.0      # reta / meia / embutida: +-2 mm


def _inicios_porta(p):
    """Quanto cada borda da folha (esq, dir, baixo, cima) entra no vao:
    folga - cobertura (negativo = cobre a chapa)."""
    cobertura = _cobertura_porta(p)
    lateral = p['lateral_mm']
    inicios = [p['folga_mm'] - (_cobertura_mm(float(p[k]), lateral) if k in p
                                else cobertura)
               for k in COBERTURAS_LADOS]
    if p.get('abertura') == 'CORRER' and _correr_sobreposta(p):
        # com moldura a folha cobre a frente do modulo (pedido do usuario):
        # de pe' no trilho de baixo (`_pe_da_folha_moldura`) ate' o topo
        # dele; a moldura soma o resto acima (e abaixo, com rodape)
        inicios[2] = _pe_da_folha_moldura(p)
        inicios[3] = -float(lateral)
    elif p.get('abertura') == 'CORRER':
        # em pe' na guia do trilho de baixo; em cima, entra no canal com
        # folga para levantar e tirar (o trilho da foto do usuario). O
        # trilho fica na borda do vao
        borda = [min(0.0, i) for i in inicios]
        inicios[2] = borda[2] + _ferragens.altura_trilho_baixo()
        inicios[3] = (borda[3] + _ferragens.TRILHO_CIMA_CHAPA_MM
                      + _ferragens.TRILHO_LEVANTAR_MM)
    return inicios


def _correr_sobreposta(p):
    """Correr que COBRE a chapa em algum lado = porta COM MOLDURA (pedido
    do usuario: cliques canto de fora -> de dentro, o gesto das portas por
    cima): folhas e trilhos na FRENTE do modulo, dentro da moldura
    (`_pecas_moldura`). A que fica no vao, recuada, e' a EMBUTIDA."""
    if p.get('abertura') != 'CORRER':
        return False
    lateral = float(p.get('lateral_mm', ESPESSURA_PADRAO_PORTA))
    return any(_cobertura_mm(float(p[k]), lateral) > 1e-6
               for k in COBERTURAS_LADOS if k in p)


# ------------------------------------------------ correr COM MOLDURA
# O guarda-roupa de exemplo do usuario: revestimento nas duas laterais,
# base do trilho + testeira em cima, base do trilho + rodape embaixo, tudo
# de `moldura_mm` (15); a moldura SOMA acima e abaixo do modulo e as
# folhas (18) cobrem a frente inteira dele. Trilhos = os perfis de
# aluminio do usuario (`_ferragens.perfil_trilho_moldura`), dois canais:
# uma folha em cada, alternando. Referencial da porta: x no vao, y para
# cima, z para FORA (0 = frente do modulo).
TRILHO_MOLDURA_COSTAS_MM = 16.0   # da frente do modulo as costas do trilho
TRILHO_MOLDURA_FRENTE_MM = 4.0    # da frente do trilho a' testeira
INSERCAO_CANAL_MM = 15.0          # quanto a folha entra no canal de cima
ESPESSURA_PORTA_MOLDURA_MM = 18.0
# Resposta do "Porta embutida ou com moldura?" (cliques metade-metade):
# a cobertura de todos os lados (`_preparar_vao_portas`)
TIPOS_CORRER = (('EMBUTIDA', 'Porta embutida'),
                ('MOLDURA', 'Porta com moldura'))
COBERTURA_DO_TIPO_CORRER = {'EMBUTIDA': 0.0, 'MOLDURA': 1.0}
# Com moldura, o wizard pergunta a BASE (pedido do usuario): ha' armario
# de correr que vai direto no chao, sem a chapa frontal de baixo (o
# rodape). Sem base = rodape 0 (a peca some); depois, o campo Rodape.
OPCOES_BASE = (('COM', 'Com rodape'), ('SEM', 'Sem rodape'))
# TIPO DE TRILHO, tambem perguntado (pedido do usuario): PESADO = os perfis
# de aluminio do guarda-roupa (sobre a base, canal alto em cima); LEVE =
# o do "Trilho exemplo" -- dois canais FRESADOS nas bases da moldura (em
# cima da de baixo, embaixo da de cima) com o perfil em U de embutir,
# aba rente a' chapa. Os canais do leve ficam a 17,3 mm um do outro: a
# folha de 18 nao cabe, a do leve nasce de 15.
ITENS_TRILHO = (('PESADO', "Trilho pesado", "Perfis de aluminio"),
                ('LEVE', "Trilho leve", "Canais fresados na chapa"))
OPCOES_TRILHO = tuple((k, t) for k, t, _d in ITENS_TRILHO)
ESPESSURA_PORTA_TRILHO = {'PESADO': ESPESSURA_PORTA_MOLDURA_MM, 'LEVE': 15.0}
FOLGA_TOPO_TRILHO_LEVE_MM = 5.0   # da folha a' base de cima: levantar e tirar
# FOLHA da porta de correr (pedido do usuario: a "diferenciada" do
# despenseiro do Promob vira estilo NOSSO): chapa de MDF ou QUADRO de
# aluminio -- perfil de 23 mm de fundo e 10 de face em volta de um painel
# de 5 mm (vidro, espelho, MDF) a 6 mm da frente, entrando 5 no perfil
# (medidas do Promob). O trilho continua o do add-on.
ITENS_FOLHA_CORRER = (('CHAPA', "Chapa", "Folha de MDF"),
                      ('QUADRO', "Quadro de aluminio",
                       "Perfil de aluminio em volta de um painel fino"))
OPCOES_FOLHA_CORRER = tuple((k, t) for k, t, _d in ITENS_FOLHA_CORRER)
ESPESSURA_QUADRO_MM = 23.0
FACE_QUADRO_MM = 10.0
PAINEL_QUADRO_MM = 5.0
PAINEL_FRENTE_MM = 6.0
PAINEL_ENTRA_MM = 5.0
NOME_MATERIAL_QUADRO = 'Aluminio Quadro'
NOME_MATERIAL_PAINEL = 'Painel Quadro'


def _moldura_mm(p):
    return float(p.get('moldura_mm', PADRAO_MEDIDAS_PORTAS['porta_moldura_mm']))


def _trilho_leve(p):
    return p.get('trilho') == 'LEVE'


def _perfil_trilho(p, lado='CIMA'):
    """O perfil (`_ferragens.perfil_trilho_moldura`) do tipo de trilho:
    no leve, o mesmo U em cima e embaixo."""
    return _ferragens.perfil_trilho_moldura('LEVE' if _trilho_leve(p) else lado)


def _canais_moldura(p):
    """(costas, frente): meio dos canais, a partir das costas do trilho."""
    if _trilho_leve(p):
        return tuple(_perfil_trilho(p)['canais_mm'])
    return _ferragens.CANAIS_TRILHO_MOLDURA_MM


def _espessura_porta_do_trilho(p):
    return ESPESSURA_PORTA_TRILHO.get(p.get('trilho'), ESPESSURA_PORTA_MOLDURA_MM)


def _folha_quadro(p):
    return p.get('abertura') == 'CORRER' and p.get('folha') == 'QUADRO'


def _material_solido(nome, cor):
    mat = bpy.data.materials.get(nome)
    if mat is None:
        mat = bpy.data.materials.new(nome)
        mat.diffuse_color = cor
    return mat


def _vestir_folha(folha, p):
    """Quadro de aluminio liga a malha do quadro (`_chapas._malha_quadro`)
    e os 2 materiais dela; chapa volta a' caixa. Sem `_ocupado` aqui:
    sao ID props, nao props com update."""
    if _folha_quadro(p):
        folha['chapa_quadro_mm'] = FACE_QUADRO_MM
        folha['chapa_painel_mm'] = PAINEL_QUADRO_MM
        folha['chapa_painel_frente_mm'] = PAINEL_FRENTE_MM
        folha['chapa_painel_entra_mm'] = PAINEL_ENTRA_MM
        mats = folha.data.materials
        if len(mats) < 2:
            # pintura do usuario (slot do objeto) fica no 1o: o perfil
            while len(mats) < 2:
                mats.append(None)
            mats[0] = mats[0] or _material_solido(NOME_MATERIAL_QUADRO,
                                                  (0.62, 0.64, 0.67, 1.0))
            mats[1] = _material_solido(NOME_MATERIAL_PAINEL, (0.55, 0.7, 0.75, 1.0))
        return
    if 'chapa_quadro_mm' in folha:
        for chave in ('chapa_quadro_mm', 'chapa_painel_mm', 'chapa_painel_frente_mm',
                      'chapa_painel_entra_mm'):
            if chave in folha:
                del folha[chave]
        folha.data.clear_geometry()          # nasce caixa de novo
        mats = folha.data.materials
        while len(mats) > 1:
            mats.pop()
        if len(mats) and mats[0] is not None and mats[0].name == NOME_MATERIAL_QUADRO:
            mats[0] = None


def _avanco_moldura(p):
    """Da frente do modulo a' face da testeira (mm)."""
    return (TRILHO_MOLDURA_COSTAS_MM + _perfil_trilho(p)['profundidade_mm']
            + TRILHO_MOLDURA_FRENTE_MM + _moldura_mm(p))


def _sem_base(p):
    """Rodape zerado = a moldura vai direto no chao (pergunta do wizard)."""
    return float(p.get('rodape_mm', PADRAO_MEDIDAS_PORTAS['porta_rodape_mm'])) <= 0.0


def _topo_base_baixo(p):
    """y (mm, referencial da porta) do TOPO da base de baixo, onde o
    trilho assenta. A base encosta no fundo do modulo (y = -lateral), sem
    fresta (print do usuario: sobrava um vao de 6 mm entre ela e o
    modulo): com rodape, ela fica logo ABAIXO dele e o rodape desce; sem
    base, ela fica no chao, no nivel do fundo do modulo."""
    lateral = float(p['lateral_mm'])
    return -lateral + (_moldura_mm(p) if _sem_base(p) else 0.0)


def _pe_da_folha_moldura(p):
    """y do pe' da folha com moldura: em cima do trilho de baixo (no
    leve, sobre a aba do U, rente a' chapa)."""
    sobre = (_perfil_trilho(p)['aba_mm'] if _trilho_leve(p)
             else _ferragens.perfil_trilho_moldura('BAIXO')['altura_mm'])
    return _topo_base_baixo(p) + sobre


def _alturas_moldura(p, altura):
    """(y do trilho de cima, y da base de cima, y da base de baixo, y da
    face de baixo da base de baixo), em mm no referencial da porta. No
    leve o trilho de cima e' EMBUTIDO na base de cima: os dois y sao a
    face de baixo dela, uma folga acima do topo da folha."""
    lateral = float(p['lateral_mm'])
    if _trilho_leve(p):
        trilho_cima = base_cima = altura + lateral + FOLGA_TOPO_TRILHO_LEVE_MM
    else:
        trilho_cima = altura + lateral - INSERCAO_CANAL_MM
        base_cima = (trilho_cima
                     + _ferragens.perfil_trilho_moldura('CIMA')['altura_mm'])
    base_baixo = _topo_base_baixo(p)
    return trilho_cima, base_cima, base_baixo, base_baixo - _moldura_mm(p)


def _canais_das_bases(p):
    """{peca: (x locais mm, largura, fundo, lado)} dos canais fresados nas
    bases da moldura do trilho LEVE (`_chapas._malha_com_canais`): em cima
    da de baixo (lado +1), embaixo da de cima (-1). x local da base = z da
    porta menos o meio do avanco (eixo 1 de `EIXOS_PECA_MOLDURA`)."""
    if not _trilho_leve(p):
        return {}
    leve = _perfil_trilho(p)
    meio = _avanco_moldura(p) / 2.0
    xs = [TRILHO_MOLDURA_COSTAS_MM + c - meio for c in leve['canais_mm']]
    dados = (xs, leve['canal_largura_mm'], leve['canal_fundo_mm'])
    return {'BASE_BAIXO': dados + (1,), 'BASE_CIMA': dados + (-1,)}


# (colunas X, Y, Z locais no referencial da porta) pelo eixo da espessura:
# a chapa e' X = largura, Y = comprimento, Z = espessura (invariante 1)
EIXOS_PECA_MOLDURA = {
    0: ((0, 0, 1), (0, 1, 0), (-1, 0, 0)),   # lateral: fundo x altura
    1: ((0, 0, 1), (1, 0, 0), (0, 1, 0)),    # base: fundo x largura
    2: ((1, 0, 0), (0, 1, 0), (0, 0, 1)),    # testeira/rodape: de frente
}


def _pecas_moldura(p, largura, altura, profundidade=0.0):
    """[(id, nome, caixa (x0, x1, y0, y1, z0, z1) mm, eixo da espessura)]
    da moldura; vazia fora da porta de correr com moldura. `profundidade`
    = a do modulo: o revestimento das laterais vai das costas dele a'
    frente da moldura."""
    if not _correr_sobreposta(p):
        return []
    lateral, t = float(p['lateral_mm']), _moldura_mm(p)
    avanco = _avanco_moldura(p)
    _trilho, base_cima, base_baixo, fundo_baixo = _alturas_moldura(p, altura)
    teto = base_cima + t
    piso = fundo_baixo - float(p.get('rodape_mm', 0.0))
    x0, x1 = -lateral, largura + lateral
    # o trilho LEVE nao tem fechamento frontal em cima (print do usuario):
    # a folha corre a' vista ate' a base de cima
    testeira = 0.0 if _trilho_leve(p) else float(p.get('testeira_mm', 0.0))
    pecas = [
        ('LATERAL_ESQ', 'Moldura Lateral Esquerda',
         (x0 - t, x0, piso, teto, -profundidade, avanco), 0),
        ('LATERAL_DIR', 'Moldura Lateral Direita',
         (x1, x1 + t, piso, teto, -profundidade, avanco), 0),
        ('BASE_CIMA', 'Moldura Base Superior',
         (x0, x1, base_cima, teto, 0.0, avanco), 1),
        ('TESTEIRA', 'Moldura Testeira',
         (x0, x1, base_cima - testeira, base_cima, avanco - t, avanco), 2),
        ('BASE_BAIXO', 'Moldura Base Inferior',
         (x0, x1, fundo_baixo, base_baixo, 0.0, avanco), 1),
        ('RODAPE', 'Moldura Rodape',
         (x0, x1, piso, fundo_baixo, avanco - t, avanco), 2),
    ]
    # rodape/testeira zerados: a peca nao existe
    return [peca for peca in pecas
            if min(peca[2][1] - peca[2][0], peca[2][3] - peca[2][2],
                   peca[2][5] - peca[2][4]) > 0.5]


def _matriz_peca_moldura(caixa, eixo):
    """(matriz_basis em m, (largura, comprimento, espessura) mm)."""
    x0, x1, y0, y1, z0, z1 = caixa
    medidas = (x1 - x0, y1 - y0, z1 - z0)
    colunas = [Vector(c) for c in EIXOS_PECA_MOLDURA[eixo]]
    rotacao = Matrix(colunas).transposed()        # vetores como COLUNAS
    centro = Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)) / 1000.0
    dims = tuple(abs(c.dot(Vector(medidas))) for c in colunas)
    return Matrix.Translation(centro) @ rotacao.to_4x4(), dims


def _montar_moldura(grupo, pecas, canais=None):
    """Cria/atualiza/remove as chapas da moldura (com `_ocupado`), pelo
    id da peca, como as folhas. `canais` = os fresados das bases do trilho
    leve (`_canais_das_bases`). Devolve as que ficaram."""
    canais = canais or {}
    existentes = {}
    for o in list(grupo.children):
        if _chapas.MARCA_MOLDURA in o:
            if o.get('porta_moldura_peca') in existentes:
                _remover_chapa(o)
            else:
                existentes[o.get('porta_moldura_peca')] = o
    feitas = []
    for chave, nome, caixa, eixo in pecas:
        obj = existentes.pop(chave, None)
        if obj is None:
            obj = bpy.data.objects.new(nome, bpy.data.meshes.new(nome))
            grupo.users_collection[0].objects.link(obj)
            obj[_chapas.MARCA_CHAPA] = 1
            obj[_chapas.MARCA_MOLDURA] = 1
            obj['porta_moldura_peca'] = chave
        elif obj.data.users > 1:
            obj.data = obj.data.copy()
        _ferragens._padronizar_nome(obj, nome)
        obj.parent = grupo
        obj.matrix_parent_inverse = Matrix.Identity(4)
        matriz, (l, c, e) = _matriz_peca_moldura(caixa, eixo)
        obj.matrix_basis = matriz
        obj.chapa_largura_mm = l
        obj.chapa_comprimento_mm = c
        obj.chapa_espessura_mm = e
        obj.chapa_auto = True
        _gravar_canais(obj, canais.get(chave))
        feitas.append(obj)
    for obj in existentes.values():
        _remover_chapa(obj)
    return feitas


CHAVES_CANAIS = ('chapa_canais', 'chapa_canal_largura', 'chapa_canal_fundo',
                 'chapa_canal_lado')


def _gravar_canais(obj, dados):
    """Canais fresados ao longo do comprimento da chapa (os da base do
    trilho leve), que `_chapas._malha_com_canais` corta na malha; None tira."""
    if dados is None:
        if 'chapa_canais' in obj:
            # voltou ao pesado: malha vazia nasce caixa de novo (a com
            # canais seria "modelada" e esticada com os canais junto)
            obj.data.clear_geometry()
        for chave in CHAVES_CANAIS:
            if chave in obj:
                del obj[chave]
        return
    xs, largura, fundo, lado = dados
    obj['chapa_canais'] = [float(x) for x in xs]
    obj['chapa_canal_largura'] = float(largura)
    obj['chapa_canal_fundo'] = float(fundo)
    obj['chapa_canal_lado'] = int(lado)


def _remover_chapa(obj):
    malha = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if malha is not None and malha.users == 0:
        bpy.data.meshes.remove(malha)


def _moldura_da_porta(grupo):
    return [o for o in grupo.children if _chapas.MARCA_MOLDURA in o]


def _espessura_da_moldura_mudou(peca, espessura):
    """O E de UMA peca vale para a moldura inteira (como a folha)."""
    grupo = peca.parent
    if (grupo is None or _chapas.MARCA_PORTAS not in grupo
            or not grupo.get('porta_parametros')):
        return False
    erro = _editar_parametro_porta(bpy.context, grupo, 'moldura_mm', espessura)
    if erro:
        print("[Cabinet Creator] espessura da moldura:", erro)
        return False
    return True


def _encaixar_cobertura(mm, lateral):
    """Cobertura medida (mm) -> fracao da espessura, presa em reta (1),
    meia (0.5) ou embutida (0) quando estiver a TOL_COBERTURA_MM delas."""
    for fracao in (1.0, 0.5, 0.0):
        if abs(mm - fracao * lateral) <= TOL_COBERTURA_MM:
            return fracao
    return mm / lateral


def _coberturas_dos_cantos(bordas, vaos, lateral):
    """{chave: fracao} de cada lado: dos cantos da PORTA (cliques 1 e 4)
    ate' os do VAO (2 e 3), em mm no referencial da porta."""
    bx, by = [p.x for p in bordas], [p.y for p in bordas]
    vx, vy = [p.x for p in vaos], [p.y for p in vaos]
    mm = (min(vx) - min(bx), max(bx) - max(vx),
          min(vy) - min(by), max(by) - max(vy))
    return {k: _encaixar_cobertura(c, lateral)
            for k, c in zip(COBERTURAS_LADOS, mm)}


def _espelhar_margem(bordas, vaos):
    """Clique 1 e 2 no MESMO ponto (ou 3 e 4): a margem do outro par vale
    tambem para este, contada para DENTRO a partir do clique (pedido do
    usuario). Devolve (vaos, quais foram espelhados). Os dois pares sem
    margem: nada muda (o vao sai da conversao de sempre)."""
    tolerancia = _modulos.TOL_BORDA * 1000.0
    margens = [Vector(((v - b).x, (v - b).y)) for b, v in zip(bordas, vaos)]
    zeros = [m.length <= tolerancia for m in margens]
    novos = [v.copy() for v in vaos]
    espelhados = [False, False]
    for i in (0, 1):
        if zeros[i] and not zeros[1 - i]:
            for eixo in (0, 1):
                dentro = 1 if vaos[1 - i][eixo] > bordas[i][eixo] else -1
                novos[i][eixo] = (bordas[i][eixo]
                                  + dentro * abs(margens[1 - i][eixo]))
            espelhados[i] = True
    return novos, espelhados


def _lados_fora_do_padrao(coberturas):
    """Lados cuja cobertura nao e' reta, meia nem embutida: o wizard
    pergunta se as medidas estao corretas."""
    return [k for k in COBERTURAS_LADOS
            if k in coberturas and coberturas[k] not in (0.0, 0.5, 1.0)]


def _porta_embutida(coberturas):
    """Nenhum lado cobre a chapa: a porta fica DENTRO do vao."""
    return bool(coberturas) and all(f <= 0.0 for f in coberturas.values())


NOME_DOBRADICA = {'RETA': 'Reta', 'CURVA': 'Curva',
                  'SUPER_CURVA': 'Super Curva'}


def _dobradica_da_cobertura(fracao, embutida=False):
    """A dobradica sai da cobertura do lado dela (pedido do usuario; nao
    se escolhe por enquanto): espessura inteira = Reta, metade = Curva,
    porta dentro do vao = Super Curva."""
    if embutida:
        return 'SUPER_CURVA'
    return 'RETA' if fracao >= 0.75 else 'CURVA'


def _meias_do_vao(a, b, base, objetos, pontos):
    """Ponto marcado no meio da espessura de uma chapa (o ima oferece o
    meio das arestas de espessura): o vao vai ate' a face da chapa que
    olha para o outro ponto, e aquele lado cobre so' meia espessura.

    Ajusta `pontos` (mm, no referencial `base`) e devolve os lados (bits).
    """
    meias = 0
    originais = (Vector(a), Vector(b))
    for i, obj in enumerate(objetos):
        if obj is None or obj.type != 'MESH' or _chapas.MARCA_CHAPA not in obj:
            continue
        zs = [v.co.z for v in obj.data.vertices]
        if not zs:
            continue
        meio, metade = (max(zs) + min(zs)) / 2.0, (max(zs) - min(zs)) / 2.0
        local = obj.matrix_world.inverted() @ originais[i]
        if metade <= 2 * _modulos.TOL_BORDA or abs(local.z - meio) > _modulos.TOL_BORDA:
            continue
        espessura = base @ (obj.matrix_world.to_3x3() @ Vector((0, 0, 1)))
        eixo = 0 if abs(espessura.x) >= abs(espessura.y) else 1
        if abs(espessura.normalized()[eixo]) < 0.9:
            continue        # espessura fora do plano da porta
        alvo = (base @ originais[1 - i])[eixo] * 1000.0
        sinal = 1 if alvo > pontos[i][eixo] else -1
        pontos[i][eixo] = ((base @ originais[i])[eixo]
                           + sinal * metade * espessura.length) * 1000.0
        meias |= 1 << (2 * eixo + (0 if sinal > 0 else 1))
    return meias


def _preparar_vao_portas(a, b, referencia, frente, parametros,
                         modulo=None, objetos=(None, None), portas=None,
                         forcar=''):
    """Converte cantos externos e encontros com portas em vao interno.

    `portas`: os cantos da PORTA (cliques 1 e 4 do wizard; a e b sao os
    do vao). Devolve (vao, pontos em mundo, apoios, coberturas por lado).
    `forcar` = resposta do "embutida ou com moldura?" (`TIPOS_CORRER`):
    o vao e' o de DENTRO do modulo (o canto clicado por fora volta para
    dentro da chapa) e a cobertura de todos os lados e' a da resposta.

    O calculador recebe sempre o vao livre. Normalizar ANTES dele evita
    somar a cobertura duas vezes e serve tanto ao gesto quanto ao execute.
    """
    largura_em = _largura_do_vao(referencia, a, b)
    base = _base_da_frente(referencia, frente, largura_em)
    pontos = [base @ Vector(p) * 1000.0 for p in (a, b)]
    bordas, espelhados = None, [False, False]
    forcada = COBERTURA_DO_TIPO_CORRER.get(forcar)
    if portas is not None:
        bordas = [base @ Vector(p) * 1000.0 for p in portas]
        if forcada is None or modulo is None:
            # sem modulo nao ha' chapa para achar o canto de dentro: o
            # par do mesmo ponto copia a margem do outro, como sempre
            pontos, espelhados = _espelhar_margem(bordas, pontos)
    originais = [p.copy() for p in pontos]
    tolerancia = _modulos.TOL_BORDA * 1000.0
    ancoras = {}
    if modulo is not None:
        L, A, P, E = _caixa_do_modulo(modulo)
        lo, hi = _limites_locais_modulo(modulo) or (
            Vector((-L / 2, -P / 2, 0)), Vector((L / 2, P / 2, A)))
        cantos = [base @ (modulo.matrix_world @ (Vector((x, y, z)) / 1000)) * 1000
                  for x in (lo.x, hi.x) for y in (lo.y, hi.y)
                  for z in (lo.z, hi.z)]
        for eixo in (0, 1):
            lo = min(p[eixo] for p in cantos)
            hi = max(p[eixo] for p in cantos)
            for ponto, espelhado in zip(pontos, espelhados):
                if espelhado:
                    continue        # ja' veio exato da margem do outro par
                if abs(ponto[eixo] - lo) <= tolerancia:
                    ponto[eixo] = lo + E
                elif abs(ponto[eixo] - hi) <= tolerancia:
                    ponto[eixo] = hi - E
    meias = _meias_do_vao(a, b, base, tuple(
        None if e else o for o, e in zip(objetos, espelhados)), pontos)
    for i, obj in enumerate(objetos):
        grupo = _grupo_portas(obj)
        if grupo is None or _chapas.MARCA_FOLHA not in obj:
            continue
        cantos = [base @ (obj.matrix_world @ v.co) * 1000.0
                  for v in obj.data.vertices]
        if not cantos:
            continue
        # A face da folha esta' a uma espessura do vao. Usa o plano
        # original para nao criar a proxima porta um degrau a frente.
        pontos[i].z = (base @ grupo.matrix_world.translation).z * 1000.0
        for eixo in (0, 1):
            lo = min(p[eixo] for p in cantos)
            hi = max(p[eixo] for p in cantos)
            outro = originais[1 - i][eixo]
            sinal = (1 if outro > hi + tolerancia else
                     -1 if outro < lo - tolerancia else 0)
            borda = hi if sinal > 0 else lo
            if not sinal or abs(originais[i][eixo] - borda) > tolerancia:
                continue
            ajuste = (_cobertura_porta(parametros)
                      + max(parametros['entre_folhas_mm'], parametros['folga_mm'])
                      - parametros['folga_mm'])
            pontos[i][eixo] = borda + sinal * ajuste
            # Indice do limite no referencial da porta (X esq/dir, Y baixo/cima).
            ancoras[2 * eixo + (0 if sinal > 0 else 1)] = obj
    mundo = [base.transposed() @ (p / 1000.0) for p in pontos]
    if any((pontos[1][i] - pontos[0][i]) * (originais[1][i] - originais[0][i]) <= 0
           for i in (0, 1)):
        raise ValueError("As bordas e folgas nao deixam espaco para o vao")
    vao = _mapear_vao_portas(*mundo, referencia, frente, largura_em)
    if bordas is not None:
        coberturas = _coberturas_dos_cantos(bordas, pontos,
                                            parametros['lateral_mm'])
        if forcada is not None:
            coberturas = {k: forcada for k in COBERTURAS_LADOS}
        for indice in ancoras:
            # encostado em outra porta: quem manda e' o apoio
            coberturas.pop(COBERTURAS_LADOS[indice], None)
    elif _cobertura_porta(parametros) > 0:
        coberturas = {COBERTURAS_LADOS[i]: 0.5 for i in range(4)
                      if meias >> i & 1}
    else:
        coberturas = {}
    return vao, mundo, ancoras, coberturas


# Porta de correr (pedido do usuario): cada folha no SEU trilho -- uma,
# duas, tres ou quatro, todas correm o vao inteiro, uma por cima da
# outra. Sem largura digitada, a folha unica tem METADE do vao (sobra
# para onde correr) e as varias o cobrem, cruzando
# `SOBREPOSICAO_CORRER_MM` com a vizinha. A largura digitada
# (`CHAVE_LARGURA_CORRER`, chave solta como as coberturas: e' desta
# porta, nao padrao da cena) vale para todas e nunca passa do vao. Nao ha'
# campo de sobreposicao: com a largura e as folhas espalhadas no vao ela
# e' consequencia, (n x largura - vao) / (n - 1) -- o usuario a recusou.
CHAVE_LARGURA_CORRER = 'largura_folha_mm'
SOBREPOSICAO_CORRER_MM = 20.0


def _largura_folha_correr(p, util, n):
    escolhida = float(p.get(CHAVE_LARGURA_CORRER, 0.0) or 0.0)
    if escolhida > 0:
        return min(escolhida, util)
    if n == 1:
        return util / 2.0
    return (util + (n - 1) * SOBREPOSICAO_CORRER_MM) / n


def _plano_correr(p, e, indice, n=1):
    """Centro (z, mm) da folha `indice` de correr: um trilho por folha,
    a 1a na frente. O recuo mede a FACE mais externa, assim nem meia
    espessura invade o espaco reservado ao trilho. Sobreposta: na frente
    do modulo, a de tras encostada na parede do trilho (que encosta nele)."""
    passo = e + float(p['entre_planos_mm'])
    if _correr_sobreposta(p):
        # com moldura: no meio de um dos DOIS canais do trilho do usuario,
        # a 1a na frente e as outras alternando
        costas, frente = _canais_moldura(p)
        return TRILHO_MOLDURA_COSTAS_MM + (frente if indice % 2 == 0 else costas)
    return -float(p['recuo_correr_mm']) - e / 2.0 - indice * passo


def _calcular_folhas_portas(largura, altura, parametros):
    """Retorna (L, A, E, centro_mm) por folha; nenhuma ferragem e' criada."""
    p = parametros
    abertura, n = p['abertura'], p['folhas']
    if abertura not in LIMITES_FOLHAS or not 1 <= n <= LIMITES_FOLHAS[abertura]:
        raise ValueError("Quantidade de folhas invalida para esta abertura")
    # .get: porta antiga (e dicionario de teste) nao tem as ferragens
    numericos = [largura, altura] + [float(p.get(k, 0.0)) for k in
                                    _PARAMETROS_PORTAS if k.endswith('_mm')]
    if not all(math.isfinite(v) and v >= 0 for v in numericos):
        raise ValueError("As medidas devem ser finitas e nao negativas")
    e, lateral = p['espessura_mm'], p['lateral_mm']
    if not (e > 0 and lateral > 0):
        raise ValueError("A espessura deve ser maior que zero")
    correr = abertura == 'CORRER'
    if not correr and p['dobradica'] not in {'RETA', 'CURVA', 'SUPER_CURVA'}:
        raise ValueError("Escolha a dobradica: reta, curva ou super curva")
    esq, dir_, baixo, cima = _inicios_porta(p)
    util = largura - esq - dir_
    a = altura - baixo - cima
    if correr:
        if p['recuo_correr_mm'] <= 0:
            raise ValueError("Portas de correr exigem recuo positivo para os trilhos")
        l = _largura_folha_correr(p, util, n)
        # as folhas se espalham pelo vao, a 1a encostada a' esquerda e a
        # ultima a' direita (a unica fica a' esquerda: corre para a outra)
        if l > util + 1e-6:
            raise ValueError("Vao estreito demais para as folhas")
        passo = (util - l) / (n - 1) if n > 1 else 0.0
    else:
        l = (util - (n - 1) * p['entre_folhas_mm']) / n
        passo = l + p['entre_folhas_mm']
    if l < 1.0 or a < 1.0:
        raise ValueError("Folgas maiores que o vao disponivel")
    saida = []
    for i in range(n):
        if correr:
            z = _plano_correr(p, e, i, n)
        elif p['dobradica'] == 'SUPER_CURVA':
            z = -p['recuo_embutida_mm'] - e / 2.0
        else:
            z = _ferragens._afastamento_porta(p) + e / 2.0
        saida.append((l, a, e,
                      (esq + l / 2.0 + i * passo,
                       baixo + a / 2.0, z)))
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
    if obj is None or _chapas.MARCA_CHAPA not in obj:
        return None
    pai = obj.parent
    while pai is not None:
        if _chapas.MARCA_CONJUNTO in pai:
            return pai
        pai = pai.parent
    return None


def _caixa_do_modulo(conj):
    """(L, A, P, E) em mm do modulo, ou None se faltar medida."""
    try:
        limites = _limites_locais_modulo(conj)
        if limites is not None:
            lo, hi = limites
            return (hi.x - lo.x, hi.z - lo.z, hi.y - lo.y,
                    float(conj.conj_espessura_mm))
        return (float(conj.conj_largura_mm), float(conj.conj_altura_mm),
                float(conj.conj_profundidade_mm),
                float(conj.conj_espessura_mm))
    except (AttributeError, TypeError, ValueError):
        return None


def _limites_locais_modulo(conj):
    """Caixa das chapas, sem portas; campos antigos podem estar defasados."""
    inversa = conj.matrix_world.inverted()
    pontos = [inversa @ (o.matrix_world @ v.co) * 1000
              for o in _modulos._chapas_do_conjunto(conj) for v in o.data.vertices]
    if not pontos:
        return None
    return (Vector(tuple(min(p[i] for p in pontos) for i in range(3))),
            Vector(tuple(max(p[i] for p in pontos) for i in range(3))))


def _local_no_modulo(conj, ponto):
    """Ponto de mundo nos eixos do modulo, em mm."""
    return conj.matrix_world.inverted() @ Vector(ponto) * 1000.0


def _folgas_do_vao(conj, ponto_a, ponto_b, frente, largura_em='X'):
    """Folgas (esq, dir, baixo, cima) em ESPESSURAS mais o recuo em mm.

    O Empty do conjunto fica no centro X/Y e na base Z (ver
    `reposicionar_origem`), entao a caixa local vai de -L/2 a L/2 em X,
    de -P/2 a P/2 em Y e de 0 a A em Z. "Baixo/cima" sao os lados do
    eixo da ALTURA da porta -- numa tampa deitada, a profundidade.
    """
    caixa = _caixa_do_modulo(conj)
    if caixa is None:
        return None
    L, A, P, E = caixa
    if E <= 0.0:
        return None
    lo, hi = _limites_locais_modulo(conj) or (
        Vector((-L / 2, -P / 2, 0)), Vector((L / 2, P / 2, A)))
    a = _local_no_modulo(conj, ponto_a)
    b = _local_no_modulo(conj, ponto_b)
    il, ia, inormal = _eixos_da_frente(frente, largura_em)
    esq, dir_ = min(a[il], b[il]) - lo[il], hi[il] - max(a[il], b[il])
    baixo, cima = min(a[ia], b[ia]) - lo[ia], hi[ia] - max(a[ia], b[ia])
    recuo = (min(a[inormal], b[inormal]) - lo[inormal]
             if frente.startswith('NEG')
             else hi[inormal] - max(a[inormal], b[inormal]))
    return ((esq / E, dir_ / E, baixo / E, cima / E), recuo)


def _vao_do_modulo(conj, folgas, recuo, frente, largura_em='X'):
    """Refaz (largura, altura, matriz) do vao a partir do modulo de hoje."""
    caixa = _caixa_do_modulo(conj)
    if caixa is None:
        return None
    L, A, P, E = caixa
    lo, hi = _limites_locais_modulo(conj) or (
        Vector((-L / 2, -P / 2, 0)), Vector((L / 2, P / 2, A)))
    esq, dir_, baixo, cima = (f * E for f in folgas)
    il, ia, inormal = _eixos_da_frente(frente, largura_em)
    canto_a, canto_b = Vector(), Vector()
    canto_a[il], canto_b[il] = lo[il] + esq, hi[il] - dir_
    canto_a[ia], canto_b[ia] = lo[ia] + baixo, hi[ia] - cima
    canto_a[inormal] = canto_b[inormal] = (
        lo[inormal] + recuo if frente.startswith('NEG')
        else hi[inormal] - recuo)
    mundo = conj.matrix_world
    referencia = mundo.to_quaternion().to_matrix()
    return _mapear_vao_portas(mundo @ (canto_a / 1000.0),
                              mundo @ (canto_b / 1000.0),
                              referencia, frente, largura_em)


def _portas_do_conjunto(conj):
    """Grupos de porta vinculados a este modulo."""
    return [o for o in bpy.data.objects
            if _chapas.MARCA_PORTAS in o and o.get(CHAVE_MODULO_PORTA) == conj.name]


def _vao_com_ancoras(grupo, vao, parametros):
    """Atualiza limites apoiados em folhas ja' existentes, sem acumular folga."""
    largura, altura, matriz = vao
    inversa = matriz.inverted()
    limites = [0.0, largura, 0.0, altura]
    ajuste = (_cobertura_porta(parametros)
              + max(parametros['entre_folhas_mm'], parametros['folga_mm'])
              - parametros['folga_mm'])
    for indice in range(4):
        folha = grupo.get('porta_ancora_%d' % indice)
        if not isinstance(folha, bpy.types.Object) or folha.type != 'MESH':
            continue
        # fechada: a porta de apoio aberta nao muda o vao desta
        fechada = _ferragens._matriz_fechada(folha)
        valores = [(inversa @ (fechada @ v.co))[indice // 2] * 1000
                   for v in folha.data.vertices]
        if valores:
            limites[indice] = (max(valores) + ajuste if indice % 2 == 0
                                else min(valores) - ajuste)
    matriz = matriz @ Matrix.Translation(Vector((limites[0], limites[2], 0)) / 1000)
    largura, altura = limites[1] - limites[0], limites[3] - limites[2]
    if largura < 1 or altura < 1:
        raise ValueError("A porta de apoio nao deixa espaco para o vao")
    return largura, altura, matriz


def atualizar_portas_do_conjunto(conj):
    """Refaz as folhas depois que o modulo mudou de medida.

    Chamado DEPOIS de `redimensionar_grupo` / `aplicar_espessura_grupo`,
    nunca durante: as folhas leem as medidas ja' aplicadas.
    """
    if conj is None or _chapas.MARCA_CONJUNTO not in conj:
        return
    pendentes = _portas_do_conjunto(conj)
    ordenados = []
    # Apoios primeiro: nomes alfabeticos nao representam a dependencia.
    while pendentes:
        livres = [g for g in pendentes if not any(
            _grupo_portas(g.get('porta_ancora_%d' % i)) in pendentes
            for i in range(4))]
        if not livres:
            print("[Cabinet Creator] ciclo entre portas de apoio")
            break
        ordenados.extend(livres)
        pendentes = [g for g in pendentes if g not in livres]
    for grupo in ordenados:
        folgas = grupo.get(CHAVE_FOLGAS_PORTA)
        parametros = grupo.get('porta_parametros')
        if not folgas or not parametros:
            continue
        frente = grupo.get('porta_frente', 'NEG_Y')
        largura_em = grupo.get('porta_largura_em', 'X')
        # A lateral E' a chapa do modulo: guardar a de quando a porta
        # nasceu fazia a porta reta sobrar para fora ao afinar o modulo.
        parametros = dict(parametros)
        parametros['lateral_mm'] = _espessura_do_vao(
            conj, padrao=parametros.get('lateral_mm', ESPESSURA_PADRAO_PORTA))
        try:
            vao = _vao_do_modulo(conj, list(folgas),
                                 float(grupo.get(CHAVE_RECUO_PORTA, 0.0)),
                                 frente, largura_em)
            if vao is None:
                continue
            largura, altura, matriz = _vao_com_ancoras(grupo, vao, parametros)
            _aplicar_portas(bpy.context, grupo, matriz, conj,
                            largura, altura, dict(parametros))
        except (ValueError, KeyError, TypeError) as e:
            print("[Cabinet Creator] porta vinculada:", e)


def _reaplicar_portas(context, grupo, parametros):
    """Refaz as folhas no vao que o grupo ja' tem, respeitando apoios."""
    largura, altura, matriz = _vao_com_ancoras(
        grupo, (grupo['porta_vao_largura_mm'], grupo['porta_vao_altura_mm'],
                grupo.matrix_world.copy()), parametros)
    return _aplicar_portas(context, grupo, matriz, grupo.parent,
                           largura, altura, parametros)


def _refazer_porta(context, grupo, parametros):
    """Grava parametros novos numa porta JA' colocada e refaz as folhas.

    Devolve '' ou o motivo da recusa. Valida ANTES de gravar: valor
    recusado nao pode deixar a porta pela metade. Vinculada a um modulo,
    refaz pelo modulo, que tambem refaz as portas apoiadas nesta.
    """
    try:
        _calcular_folhas_portas(float(grupo['porta_vao_largura_mm']),
                                float(grupo['porta_vao_altura_mm']),
                                parametros)
    except (ValueError, KeyError, TypeError) as erro:
        return str(erro)
    modulo = bpy.data.objects.get(grupo.get(CHAVE_MODULO_PORTA, ''))
    if (modulo is not None and _chapas.MARCA_CONJUNTO in modulo
            and grupo.get(CHAVE_FOLGAS_PORTA)):
        grupo['porta_parametros'] = dict(parametros)
        atualizar_portas_do_conjunto(modulo)
        return ''
    try:
        _reaplicar_portas(context, grupo, parametros)
    except (ValueError, KeyError, TypeError) as erro:
        return str(erro)
    return ''


def _editar_parametro_porta(context, grupo, nome, valor):
    """Muda UM parametro de uma porta colocada (aba Portas, nivel porta)."""
    guardados = grupo.get('porta_parametros') if grupo is not None else None
    if not guardados or nome not in _PARAMETROS_PORTAS + (CHAVE_LARGURA_CORRER,):
        return 'Porta sem parametros para editar'
    parametros = dict(guardados)
    if nome in {'espessura_mm', 'moldura_mm'}:
        valor = _chapas._espessura_livre(valor)
    elif nome == CHAVE_LARGURA_CORRER:
        valor = max(1.0, float(valor))
    parametros[nome] = valor
    if nome in {'abertura', 'folhas'}:
        # outra tipologia: a largura volta a' do padrao dela
        parametros.pop(CHAVE_LARGURA_CORRER, None)
    if nome == 'abertura':
        parametros['folhas'] = min(int(parametros.get('folhas', 1)),
                                   LIMITES_FOLHAS[valor])
    if nome == 'trilho':
        # outro trilho, outra folha: a de 18 nao cabe nos canais do leve
        parametros['espessura_mm'] = _espessura_porta_do_trilho(parametros)
    if nome == 'folha' or (nome == 'trilho' and _folha_quadro(parametros)):
        # o quadro tem o fundo do perfil; a chapa volta a' do trilho
        parametros['espessura_mm'] = (
            ESPESSURA_QUADRO_MM if _folha_quadro(parametros)
            else _espessura_porta_do_trilho(parametros) if _correr_sobreposta(parametros)
            else ESPESSURA_PADRAO_PORTA)
    return _refazer_porta(context, grupo, parametros)


def _espessura_da_folha_mudou(folha, espessura):
    """O E de UMA folha vale para a porta inteira.

    Uma porta nao tem folhas de espessuras diferentes. Sem propagar, as
    outras folhas ficavam com a antiga e o proximo redimensionamento
    devolvia o valor guardado.
    """
    grupo = _grupo_portas(folha)
    if grupo is None or not grupo.get('porta_parametros'):
        return False
    erro = _editar_parametro_porta(bpy.context, grupo, 'espessura_mm', espessura)
    if erro:
        print("[Cabinet Creator] espessura da porta:", erro)
        return False
    return True


def _nome_da_porta(p):
    """Nome do grupo da porta pelo modelo (pedido do usuario)."""
    abertura = p.get('abertura', 'GIRO')
    if abertura == 'CORRER':
        return "Porta de Correr"
    if abertura == 'BASCULANTE':
        return "Porta Basculante"
    folhas = "Dupla" if int(p.get('folhas', 1)) > 1 else "Unica"
    if p.get('dobradica') == 'SUPER_CURVA':
        return "Porta Embutida " + folhas
    return "Porta " + folhas


def _sem_sufixo(nome):
    """"Porta Dupla.001" -> "Porta Dupla" (o .NNN do Blender)."""
    base, ponto, fim = nome.rpartition('.')
    return base if ponto and len(fim) == 3 and fim.isdigit() else nome


def _renomear_porta(grupo, p):
    """O nome segue o modelo -- a nao ser que o usuario o tenha trocado."""
    novo = _nome_da_porta(p)
    anterior = grupo.get('porta_nome_auto')
    if anterior is None or _sem_sufixo(grupo.name) == anterior:
        if _sem_sufixo(grupo.name) != novo:
            grupo.name = novo
        grupo['porta_nome_auto'] = novo


def _aplicar_portas(context, grupo, matriz, pai, largura, altura,
                    parametros, frente='', largura_em=''):
    """Valida antes de alterar a cena; reutiliza folhas e seus materiais."""
    calculadas = _calcular_folhas_portas(largura, altura, parametros)
    antigas = _folhas_portas(grupo) if grupo is not None else []
    if any(o.type != 'MESH' or o.mode != 'OBJECT' for o in antigas):
        raise ValueError("Saia do Modo Edicao das portas antes de reconfigurar")
    ocupado_antes = _chapas._ocupado[0]
    _chapas._ocupado[0] = True
    try:
        if grupo is None:
            grupo = bpy.data.objects.new(_nome_da_porta(parametros), None)
            grupo['porta_nome_auto'] = grupo.name
            # dentro do grupo (Collection) do armario, junto das chapas
            colecao = (pai.users_collection[0] if pai is not None
                       and pai.users_collection else context.collection)
            colecao.objects.link(grupo)
            grupo[_chapas.MARCA_PORTAS] = 1
            _chapas._ocultar_empty(grupo)
            grupo.parent = pai
            # As medidas sao de mundo, mesmo quando o pai tem escala.
            if pai is not None:
                grupo.matrix_parent_inverse = pai.matrix_world.inverted()
        # O vao se desloca ao redimensionar: atualizar so' as dimensoes
        # deixava a origem antiga e a porta escapava da borda do modulo.
        grupo.matrix_world = matriz
        _renomear_porta(grupo, parametros)
        grupo['porta_parametros'] = dict(parametros)
        grupo['porta_vao_largura_mm'] = largura
        grupo['porta_vao_altura_mm'] = altura
        if frente:
            grupo['porta_frente'] = frente
        if largura_em:
            grupo['porta_largura_em'] = largura_em
        for i, (l, a, e, centro) in enumerate(calculadas):
            antigo = None
            if i < len(antigas):
                folha = antigas[i]
                if folha.data.users > 1:
                    folha.data = folha.data.copy()
                antigo = (folha.chapa_largura_mm, folha.chapa_comprimento_mm,
                          folha.chapa_espessura_mm)
            else:
                malha = bpy.data.meshes.new("Folha %02d" % (i + 1))
                folha = bpy.data.objects.new("Folha %02d" % (i + 1), malha)
                grupo.users_collection[0].objects.link(folha)
                folha[_chapas.MARCA_CHAPA] = 1
                folha[_chapas.MARCA_FOLHA] = 1
            _ferragens._padronizar_nome(folha, "Folha %02d" % (i + 1))
            folha['porta_indice'] = i
            folha.parent = grupo
            folha.matrix_parent_inverse = Matrix.Identity(4)
            # a abertura sobrevive a redimensionar (Fase 3)
            folha[_ferragens.CHAVE_CENTRO_FOLHA] = tuple(centro)
            folha.matrix_basis = _ferragens._matriz_abertura(
                parametros, largura, len(calculadas), i, (l, a, e, centro),
                folha.get(_ferragens.CHAVE_ABERTURA, 0.0))
            folha.chapa_largura_mm = l
            folha.chapa_comprimento_mm = a
            folha.chapa_espessura_mm = e
            folha.chapa_auto = True
            if antigo is not None:
                _ajustar_puxadores(folha, antigo, (l, a, e))
        # Apenas folhas geradas que deixaram de existir na nova tipologia.
        # O puxador delas nao some junto: fica solto no lugar e depois
        # passa para a folha que sobrou mais perto.
        orfaos = []
        for folha in antigas[len(calculadas):]:
            for pux in [c for c in folha.children if _chapas.MARCA_PUXADOR in c]:
                mundo = pux.matrix_world.copy()
                pux.parent = None
                pux.matrix_world = mundo
                orfaos.append(pux)
            for ferragem in [c for c in folha.children_recursive
                             if _ferragens.CHAVE_FERRAGEM in c]:
                _ferragens._remover_ferragem(ferragem)
            malha = folha.data
            bpy.data.objects.remove(folha, do_unlink=True)
            if malha.users == 0:
                bpy.data.meshes.remove(malha)
        _ferragens._montar_ferragens(grupo, parametros, largura, altura, calculadas)
        modulo = pai if pai is not None and _chapas.MARCA_CONJUNTO in pai else None
        caixa = _caixa_do_modulo(modulo) if modulo is not None else None
        moldura = _montar_moldura(grupo, _pecas_moldura(
            parametros, largura, altura, caixa[2] if caixa else 0.0),
            _canais_das_bases(parametros))
    finally:
        _chapas._ocupado[0] = ocupado_antes
    for folha in _folhas_portas(grupo) + moldura:
        _chapas.gerar_malha_chapa(folha)
    context.view_layer.update()
    if modulo is not None:
        # a moldura e' parte da caixa do armario (pedido do usuario): as
        # medidas do modulo passam a conta-la (ou deixam, se ela saiu)
        _modulos.sincronizar_medidas_conjunto(modulo)
    refazer = set()
    for pux in orfaos:
        folha = _folha_mais_proxima(pux, _folhas_portas(grupo))
        if (folha is not None and _puxadores._eh_puxador_parametrico(pux)
                and pux['puxador_tipo'] == 'PERFIL'
                and pux.get('puxador_borda') in _puxadores._rebaixos_da_chapa(folha)):
            # a folha que fica ja' tem perfil nessa borda: sobraria dobrado
            bpy.data.objects.remove(pux, do_unlink=True)
            continue
        _ligar_puxador(pux, folha)
        if folha is not None and _puxadores._eh_puxador_parametrico(pux):
            refazer.add(folha.name)
    for nome in refazer:
        # parametrico vai para a mesma borda/fracao da folha nova
        _chapas.gerar_malha_chapa(bpy.data.objects[nome])
    return grupo


def _centro_mundo(obj):
    cantos = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return sum(cantos, Vector()) / len(cantos)


def _folha_mais_proxima(obj, folhas):
    centro = _centro_mundo(obj)
    return min(folhas, key=lambda f: (f.matrix_world.translation - centro).length,
               default=None)


def _ligar_puxador(pux, folha):
    """Pendura o puxador na folha SEM tira-lo do lugar.

    A inversa fica identidade: assim `matrix_basis` E' a posicao do
    puxador no referencial da folha (X largura, Y altura, Z espessura,
    origem no centro), que e' onde `_ajustar_puxadores` faz as contas.
    """
    if folha is None:
        return
    mundo = pux.matrix_world.copy()
    pux.parent = folha
    pux.matrix_parent_inverse = Matrix.Identity(4)
    pux.matrix_basis = folha.matrix_world.inverted() @ mundo


def _ajustar_puxadores(folha, antigo, novo):
    """A folha mudou de (L, A, E) antigo para novo: o puxador acompanha.

    Eixo TRAVADO: mesma medida, mesma distancia ate' a borda da folha
    de que estava mais perto. DESTRAVADO: estica junto com a folha,
    proporcional a partir do centro dela (o puxador distorce).
    Parametrico (`puxador_tipo`) fica de fora: `posicionar_puxador` o
    refaz pelas props da folha, no gancho de `gerar_malha_chapa`.
    """
    for pux in [c for c in folha.children if _chapas.MARCA_PUXADOR in c
                and not _puxadores._eh_puxador_parametrico(c)]:
        relativo = pux.matrix_parent_inverse @ pux.matrix_basis
        cantos = [relativo @ Vector(c) for c in pux.bound_box]
        travas = list(pux.get(_chapas.CHAVE_TRAVAS_PUXADOR, (1, 1, 1)))
        deslocar, escala = Vector(), [1.0, 1.0, 1.0, 1.0]
        for k in range(3):
            meia_antes, meia_nova = antigo[k] / 2000.0, novo[k] / 2000.0
            if abs(meia_nova - meia_antes) < 1e-9 or meia_antes <= 0:
                continue
            if travas[k]:
                c_min = min(p[k] for p in cantos)
                c_max = max(p[k] for p in cantos)
                sinal = 1 if (meia_antes - c_max) <= (c_min + meia_antes) else -1
                deslocar[k] = sinal * (meia_nova - meia_antes)
            else:
                escala[k] = meia_nova / meia_antes
        pux.matrix_parent_inverse = Matrix.Identity(4)
        pux.matrix_basis = (Matrix.Translation(deslocar)
                            @ Matrix.Diagonal(escala) @ relativo)


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
# duas chapas diferentes. No apanhador (`cabinet_apanhar_vao`, modulo
# `assistente`) o usuario fica em Modo Objeto: o cursor
# ganha um ima que gruda no vertice mais proximo, o primeiro clique
# fixa um canto e a previa das folhas acompanha o mouse ate' o segundo.
# Aqui ficam so' o ima (`_alvos_do_ima`) e as constantes dele.
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
                pontos = [m @ v.co.copy() for v in malha.vertices]
                if _chapas.MARCA_CHAPA in obj:
                    # Porta que cobre METADE de uma chapa (pedido do
                    # usuario): o meio de cada aresta da espessura (Z
                    # local) tambem pega, ja' na diagonal.
                    for aresta in malha.edges:
                        p, q = (malha.vertices[i].co for i in aresta.vertices)
                        d = q - p
                        if d.length > 1e-6 and abs(d.normalized().z) > 0.99:
                            pontos.append(m @ ((p + q) / 2.0))
                alvos.append((obj, pontos))
        finally:
            try:
                avaliado.to_mesh_clear()
            except Exception:
                pass
    return alvos


# ---- WIZARD DE CRIACAO (backlog do usuario, Epico 1)
# 4 cliques (desenho do usuario): 1 = canto da PORTA, 2 = canto do VAO,
# 3 = canto oposto do vao, 4 = canto oposto da porta. Os fios 1-2 e 3-4
# (laranja) sao a cobertura de cada lado; 2-3 (branco), o vao. Dai' saem
# a folha, o vao e a dobradica (automatica: espessura inteira = Reta,
# metade = Curva, dentro do vao = Super Curva). Cobertura fora disso
# pergunta "As medidas estao corretas?". Depois, na ordem que a aba
# tambem segue: FOLHAS (1 | 2), TIPO (so' o que nao se deduz: Giro |
# Basculante, ou Giro | Correr na embutida), BORDA das dobradicas
# (clique; nao se pergunta no basculante, sempre CIMA, nem com 2 folhas),
# QUANTIDADE (scroll), MARGEM (mouse em Y) e, no basculante, PISTOES:
# quantidade (scroll) e posicao, que nasce AUTOMATICA e o mouse em Y so'
# sobe (descer passa do curso do pistao). As caixas sao
# desenhadas pelo proprio modal (nao popup_menu): o soltar do clique nao
# responde sozinho e o teste clica nelas. O modal e as caixas moram em
# `assistente`; aqui ficam as constantes e as contas que ele usa.
OPCOES_CONFIRMAR = (('SIM', 'Sim, criar assim'), ('NAO', 'Nao, marcar de novo'))
OPCOES_FOLHAS = (('1', '1 folha'), ('2', '2 folhas'))
# botao da gaveta que confirma a etapa do wizard (valor = a etapa)
CONFIRMAR_ETAPA = 'confirmar_etapa'
# por cima: o correr vem COM MOLDURA (pedido do usuario: o gesto de fora
# para dentro e' o da porta que avanca na frente do modulo)
TIPOS_SOBREPOSTA = (('GIRO', 'Giro'), ('BASCULANTE', 'Basculante'),
                    ('CORRER', 'Correr'))
TIPOS_EMBUTIDA = (('GIRO', 'Giro (Super Curva)'), ('CORRER', 'Correr'))
COR_FIO_COBERTURA = (1.0, 0.55, 0.1, 1.0)     # laranja (print do usuario)
COR_FIO_VAO = (1.0, 1.0, 1.0, 1.0)
COR_BORDA_EIXO = (0.25, 0.85, 0.3, 1.0)       # verde
MARGEM_DOBRADICAS_PADRAO = 100.0   # mm da quina: pratica de marcenaria
LIMITES_DOBRADICAS = (2, 6)
LIMITES_PISTOES = (1, 2)
_assistente_porta = [None]          # estado do wizard (o teste le daqui)
# alvo da 'escolha' da aba Portas que responde ao wizard (a copia da caixa)
ALVO_ASSISTENTE = '@assistente'


def _qtd_dobradicas_padrao(comprimento_mm):
    """Pela altura da folha (pratica de marcenaria; o scroll muda)."""
    for teto, n in ((900, 2), (1600, 3), (2000, 4)):
        if comprimento_mm <= teto:
            return n
    return 5


def _parametros_do_wizard(w):
    """Os parametros da porta que o wizard vai criar: os da previa (vao,
    coberturas, espessuras) com as respostas dadas ate' aqui."""
    return dict(w.get('parametros') or {}, **w.get('escolhas', {}))


def _qtd_pistoes_padrao(largura_mm):
    """Um em cada lateral com folha larga; um so' em aereo pequeno."""
    return 2 if largura_mm > 600 else 1


# Pistoes a gas de movel de verdade: (aberto centro a centro, diametro do
# corpo, diametro da haste), em mm. 155/195 = Metrol NS-FF-6-60/-80 (15x6);
# 245 = o "10 polegadas" de armario (100 N, 18x8); 290-450 = serie 8 mm da
# Metrol (18x8). Regra do usuario para a conta: porta 100% aberta = pistao
# no DOBRO do fechado (o curso real fica entre 60 e 90% do fechado).
PISTOES_CATALOGO = ((155.0, 15.0, 6.0), (195.0, 15.0, 6.0),
                    (245.0, 18.0, 8.0), (290.0, 18.0, 8.0),
                    (350.0, 18.0, 8.0), (410.0, 18.0, 8.0),
                    (450.0, 18.0, 8.0))
RAZAO_PISTAO = 2.0               # aberto / fechado
PISTAO_RECUO_MM = 50.0           # eixo da fixacao da lateral atras da folha
PISTAO_SUPORTE_MM = 10.0         # pino da folha: altura do suporte
PISTAO_SUPORTE_LADO_MM = 24.0    # largura/altura das plaquinhas
PISTAO_DA_DOBRADICA_MIN_MM = 30.0  # o suporte da folha nao sobe mais que isto
PISTAO_FRACAO_DO_VAO = 2.0 / 3.0   # fixacao da lateral no 2/3 de cima do vao


def _geometria_pistao(aberto, folha, cob_topo, abrir, offset=0.0):
    """Onde vai UM pistao de `aberto` mm no basculante.

    No corte da lateral: `d` = quanto o suporte da folha desce do topo
    dela, `vs` = quanto a fixacao da lateral desce do mesmo topo (`recuo`
    atras das costas). Fechado o pistao mede aberto/RAZAO (dai' vs = d +
    k); `abrir` leva o ponto da folha fechada a' folha ABERTA -- giro no
    eixo ou o movimento do rig da dobradica reta (`_matriz_abertura`) --
    e o `d` e' o que faz o pistao medir `aberto` la' (busca binaria: o
    alcance cresce com d).

    `offset` (mm do TOPO DO VAO ate' a fixacao da lateral, 0 =
    automatico) e' a posicao manual: o fechado continua o mesmo e so'
    vale ate' onde o pistao alcanca aberto (o automatico e' o maximo).
    """
    _l, a, _e, centro = folha
    topo, costas = centro[1] + a / 2.0, centro[2] - _e / 2.0
    fechado = aberto / RAZAO_PISTAO
    dz = PISTAO_RECUO_MM - PISTAO_SUPORTE_MM
    k = math.sqrt(max(0.0, fechado * fechado - dz * dz))

    def alcance(d):
        na_folha = Vector((0.0, topo - d, costas - PISTAO_SUPORTE_MM))
        lateral = Vector((0.0, topo - d - k, costas - PISTAO_RECUO_MM))
        return (abrir(na_folha) - lateral).length

    baixo, cima = PISTAO_DA_DOBRADICA_MIN_MM, max(PISTAO_DA_DOBRADICA_MIN_MM, a)
    if alcance(baixo) >= aberto:
        d_max = baixo
    elif alcance(cima) <= aberto:
        d_max = cima
    else:
        for _passo in range(60):
            meio = (baixo + cima) / 2.0
            if alcance(meio) < aberto:
                baixo = meio
            else:
                cima = meio
        d_max = (baixo + cima) / 2.0
    d = d_max
    if offset > 0.0:
        d = max(PISTAO_DA_DOBRADICA_MIN_MM, min(d_max, offset + cob_topo - k))
    vs = d + k
    return {'aberto': aberto, 'fechado': fechado, 'd': d, 'vs': vs,
            'offset': vs - cob_topo, 'offset_max': d_max + k - cob_topo,
            'offset_min': PISTAO_DA_DOBRADICA_MIN_MM + k - cob_topo,
            # quanto o pistao mede com a porta aberta (= `aberto` no automatico)
            'alcance': alcance(d), 'abrir': abrir}


def _pistao_do_vao(altura, folha, offset=0.0, p=None):
    """Escolhe o pistao do catalogo e o posiciona. `folha` = (l, a, e,
    centro) FECHADA, no referencial do vao (topo do vao em y = `altura`).

    O MAIOR que cabe (mais braco para a porta) com a fixacao da lateral
    nos 2/3 de cima do vao e o suporte da folha dentro dela; vao baixo
    demais fica com o menor. `p` (parametros) diz como a folha abre."""
    _l, a, e, centro = folha
    cob_topo = centro[1] + a / 2.0 - altura
    parametros = dict(p or {})
    parametros['abertura'] = 'BASCULANTE'
    aberta = _ferragens._matriz_abertura(parametros, 0.0, 1, 0, folha, 1.0)
    c = Vector(centro)

    def abrir(ponto):
        return (aberta @ ((ponto - c) / 1000.0)) * 1000.0

    escolhido = PISTOES_CATALOGO[0]
    for modelo in reversed(PISTOES_CATALOGO):
        g = _geometria_pistao(modelo[0], folha, cob_topo, abrir)
        if (g['offset'] <= altura * PISTAO_FRACAO_DO_VAO
                and g['d'] <= a - PISTAO_DA_DOBRADICA_MIN_MM):
            escolhido = modelo
            break
    g = _geometria_pistao(escolhido[0], folha, cob_topo, abrir, offset)
    g.update(corpo=escolhido[1], haste=escolhido[2])
    return g


def _pontas_pistao(g, x, folha):
    """(lateral, folha fechada, folha aberta) em mm, referencial do vao."""
    _l, a, e, centro = folha
    topo, costas = centro[1] + a / 2.0, centro[2] - e / 2.0
    na_folha = Vector((x, topo - g['d'], costas - PISTAO_SUPORTE_MM))
    return (Vector((x, topo - g['vs'], costas - PISTAO_RECUO_MM)),
            na_folha, g['abrir'](na_folha))


def _posicoes_ferragens(comprimento, qtd, margem):
    """Distancias (mm, do inicio do eixo) de `qtd` ferragens em segmentos
    iguais, as das pontas a `margem` das quinas."""
    if qtd <= 0:
        return []
    if qtd == 1:
        return [comprimento / 2.0]
    margem = max(0.0, min(margem, comprimento / 2.0))
    passo = (comprimento - 2.0 * margem) / (qtd - 1)
    return [margem + i * passo for i in range(qtd)]


def _arestas_da_porta(largura, altura, coberturas, lateral, tipo):
    """Onde podem ir as dobradicas, no referencial do vao (mm; x = largura,
    y = altura): ESQUERDA/DIREITA no giro, CIMA no basculante.

    A linha fica na FACE INTERNA da chapa daquele lado (a borda do vao,
    lado de dentro da espessura marcada nos cliques 1-2), nao na borda da
    folha: e' ali que o corpo da dobradica se prende (pedido do usuario,
    com print). O comprimento e' o da FOLHA (as margens contam das quinas
    dela). `dentro` aponta para o interior do movel; `cobertura` (mm) e'
    quanto a folha passa da linha para fora -- o caneco fica na folha."""
    cob = [_cobertura_mm(float(coberturas.get(k, 0.0)), lateral)
           for k in COBERTURAS_LADOS]
    x0, x1 = -cob[0], largura + cob[1]
    y0, y1 = -cob[2], altura + cob[3]
    lados = {
        'ESQUERDA': (Vector((0.0, y0)), Vector((0.0, y1)), Vector((1, 0)), cob[0]),
        'DIREITA': (Vector((largura, y0)), Vector((largura, y1)),
                    Vector((-1, 0)), cob[1]),
        'CIMA': (Vector((x0, altura)), Vector((x1, altura)), Vector((0, -1)),
                 cob[3]),
    }
    usados = ('CIMA',) if tipo == 'BASCULANTE' else ('ESQUERDA', 'DIREITA')
    return [{'lado': lado, 'a': lados[lado][0], 'b': lados[lado][1],
             'dentro': lados[lado][2], 'cobertura': lados[lado][3]}
            for lado in usados]


# Volume de uma dobradica de caneco de 35 mm (padrao das ocultas; ver o
# plano das portas): o CORPO (calco + braco) preso na face interna da
# lateral, atras da folha, e o CANECO furado nas costas da folha. Medidas
# aproximadas -- servem para ver o espaco ocupado, nao para usinar.
DOBRADICA_ALTURA_MM = 50.0     # ao longo da borda
DOBRADICA_AVANCO_MM = 22.0     # da face interna para dentro do movel
DOBRADICA_FUNDO_MM = 70.0      # das costas da folha para tras
CANECO_DIAMETRO_MM = 35.0
CANECO_FUNDO_MM = 12.0         # furo na folha (~11,5-13 mm)
# o que o copo (aba + cabeca do braco) sobe das costas da folha: todo
# dentro do furo ele sumia na malha da porta (print do usuario)
CANECO_ABA_MM = 4.0
CANECO_BORDA_MM = 5.0          # da borda da folha ao furo (centro ~22,5)
# Duas dobradicas nunca se sobrepoem (relato do usuario: a margem ia ate'
# o meio da borda e empilhava todas): de centro a centro, o corpo e mais
# esta folga; e a da ponta fica inteira na folha.
FOLGA_ENTRE_DOBRADICAS_MM = 10.0
PASSO_MIN_DOBRADICAS_MM = DOBRADICA_ALTURA_MM + FOLGA_ENTRE_DOBRADICAS_MM
MARGEM_MIN_DOBRADICAS_MM = DOBRADICA_ALTURA_MM / 2.0


def _ajustar_dobradicas(comprimento, qtd, margem):
    """(qtd, margem) que cabem numa borda de `comprimento` mm: a margem
    entre a dobradica inteira na folha e o maximo que ainda deixa
    `PASSO_MIN_DOBRADICAS_MM` entre vizinhas; a quantidade, ate' onde
    cabe (nunca abaixo do minimo de LIMITES_DOBRADICAS)."""
    util = comprimento - 2.0 * MARGEM_MIN_DOBRADICAS_MM
    cabem = int(max(0.0, util) // PASSO_MIN_DOBRADICAS_MM) + 1
    qtd = max(LIMITES_DOBRADICAS[0], min(LIMITES_DOBRADICAS[1], cabem, int(qtd)))
    maximo = (comprimento - (qtd - 1) * PASSO_MIN_DOBRADICAS_MM) / 2.0
    # porta pequena demais para `qtd`: a ponta ainda manda (nada fora da folha)
    margem = max(MARGEM_MIN_DOBRADICAS_MM, min(float(margem), maximo))
    return qtd, min(margem, comprimento / 2.0)


def _caixa_da_ferragem(centro, eixo, dentro, faixa_u, faixa_v, faixa_z):
    """8 cantos (mm) na ordem das caixas da previa (ARESTAS_CAIXA)."""
    return [Vector((*(centro + eixo * u + dentro * v), z))
            for u in faixa_u for v in faixa_v for z in faixa_z]


def _caixas_dobradicas(aresta, distancias, costas_mm):
    """[(corpo, caneco)] por dobradica: as caixas (mm, referencial do vao)
    do espaco que cada uma ocupa. `costas_mm` = z das costas da folha."""
    a, b = aresta['a'], aresta['b']
    eixo = (b - a).normalized() if (b - a).length else Vector((0, 1))
    dentro = aresta['dentro']
    borda = -float(aresta.get('cobertura', 0.0))     # borda da folha
    meia, raio = DOBRADICA_ALTURA_MM / 2.0, CANECO_DIAMETRO_MM / 2.0
    caixas = []
    for d in distancias:
        centro = a + eixo * d
        corpo = _caixa_da_ferragem(
            centro, eixo, dentro, (-meia, meia), (0.0, DOBRADICA_AVANCO_MM),
            (costas_mm - DOBRADICA_FUNDO_MM, costas_mm))
        caneco = _caixa_da_ferragem(
            centro, eixo, dentro, (-raio, raio),
            (borda + CANECO_BORDA_MM,
             borda + CANECO_BORDA_MM + CANECO_DIAMETRO_MM),
            (costas_mm - CANECO_ABA_MM, costas_mm + CANECO_FUNDO_MM))
        caixas.append((corpo, caneco))
    return caixas


# props da Scene que a aba Portas usa para a PROXIMA porta (o arraste da
# HUD guarda e devolve todas no Esc)
_PROPS_PORTAS_CENA = (
    "porta_abertura", "porta_dobradica", "porta_folhas", "porta_associar",
) + tuple(m[1] for m in MEDIDAS_PORTAS)
