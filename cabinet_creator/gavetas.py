"""Gavetas do MOVEL (nao confundir com a "gaveta", o menu GPU a' esquerda):
um grupo de gavetas num vao do modulo -- frente, caixa e trilhos --, o
assistente que cria (2 cliques na diagonal do vao, scroll = quantas,
mouse = profundidade, trilho), a abertura por slider, a HUD de medidas e
os 3 pontos editaveis com Alt.

Referencial: o grupo e' filho do modulo, nos eixos dele, com a origem no
canto de BAIXO a' ESQUERDA do vao, no plano da frente. X = largura, Z =
altura, Y = profundidade (para DENTRO do modulo: a frente fica em -Y).
Tudo em mm. O trilho ainda e' uma BLOCAGEM em tamanho real (pedido do
usuario: o modelo de verdade nao esta' pronto).
"""

import math

import bpy, bmesh, blf, gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree
from bpy_extras import view3d_utils
from bpy.props import FloatProperty, IntProperty, StringProperty
from bpy.types import Gizmo, GizmoGroup, Operator, Macro

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _modulos = _portas = _puxadores = _hud = _assistente = None
_eventos = _gaveta = _solda = _portas_viewport = _selecao = None
_geometria = None

# Marcas gravadas no .blend (renomear quebra arquivos salvos)
MARCA_GRUPO = 'eh_grupo_gavetas'
MARCA_GAVETA = 'eh_gaveta'
MARCA_PECA = 'gaveta_peca'           # FRENTE, LATERAL, ..., TRILHO
CHAVE_MODULO = 'gavetas_modulo'
CHAVE_PARAMETROS = 'gavetas_parametros'
CHAVE_MARGENS = 'gavetas_margens_mm'  # esq, dir, baixo, cima, frente (do modulo)
CHAVE_VAO = 'gavetas_vao_mm'          # largura, altura (sem modulo)
CHAVE_INDICE = 'gaveta_indice'
CHAVE_ABERTURA = 'gaveta_fracao_aberta'
CHAVE_PUXADOR = 'gaveta_puxador'      # valor do modelo (como o carrossel)
CHAVE_TRILHO_MM = 'gavetas_trilho_mm'

PARAMETROS_PADRAO = {
    'quantidade': 1,
    'trilho': 'TELESCOPICO',          # padrao (pedido do usuario)
    'cobertura': 'SOBREPOSTA',
    'folga_frontal_mm': 2.0,          # respiro da frente no perimetro
    'entre_gavetas_mm': 3.0,          # entre uma frente e a outra
    'recuo_mm': 0.0,                  # frente para dentro (porta de correr)
    'profundidade_mm': 500.0,         # do plano da frente ao fundo
    'espessura_frente_mm': 18.0,
    'lateral_mm': 18.0,               # chapa do modulo que a frente cobre
    'puxador': 'PERFIL',
    'frente_curva_mm': 0.0,           # flecha do arco da frente (0 = reta)
    # alturas das frentes em PROPORCAO, de baixo para cima (a importacao
    # do Promob traz frentes desiguais); vazia ou de outro tamanho = iguais
    'proporcoes': [],
}
OPCOES_TRILHO = (('TELESCOPICO', 'Telescopico'), ('OCULTO', 'Oculto'))
OPCOES_COBERTURA = (('SOBREPOSTA', 'Sobreposta'), ('EMBUTIDA', 'Embutida'))
MAXIMO_GAVETAS = 10

# Trilhos (catalogo): folga de cada lado entre o vao e a caixa, o quanto
# a caixa fica acima do fundo da fatia dela e os comprimentos de linha
TRILHOS = {
    'TELESCOPICO': {'folga_lado': 12.7, 'caixa_baixo': 15.0,
                    'comprimentos': tuple(range(250, 701, 50))},
    'OCULTO': {'folga_lado': 5.0, 'caixa_baixo': 20.0,
               'comprimentos': (270, 300, 350, 400, 450, 500, 550)},
}
TELESCOPICO_ALTURA_MM = 45.0         # perfil fixo; o movel tem 35
TELESCOPICO_ESPESSURA_MM = 12.7
OCULTO_LARGURA_MM = 40.0
ESPESSURA_CAIXA_MM = 15.0
FUNDO_CAIXA_MM = 6.0
FOLGA_TOPO_CAIXA_MM = 25.0           # da caixa ate' o topo da fatia
FOLGA_FUNDO_MODULO_MM = 10.0         # do fim do trilho ate' as costas
ALTURA_MIN_FRENTE_MM = 60.0
ALTURA_MIN_CAIXA_MM = 40.0
LARGURA_MIN_VAO_MM = 100.0
NOME_MATERIAL_TRILHO = 'Trilho Gaveta'

# chapa: eixo da espessura (no referencial do grupo) -> colunas X, Y, Z
EIXOS_PECA = {
    0: ((0, 1, 0), (0, 0, 1), (1, 0, 0)),     # lateral da caixa
    1: ((1, 0, 0), (0, 0, 1), (0, -1, 0)),    # frente, contrafrente, traseira
    2: ((1, 0, 0), (0, 1, 0), (0, 0, 1)),     # fundo
}
ARESTAS = ((0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7),
           (0, 4), (1, 5), (2, 6), (3, 7))


# ------------------------------------------------------------ busca
def grupo_de(obj):
    """O grupo de gavetas de `obj` (ele mesmo, uma gaveta ou uma peca)."""
    while obj is not None:
        if MARCA_GRUPO in obj:
            return obj
        obj = obj.parent
    return None


def gaveta_de(obj):
    while obj is not None:
        if MARCA_GAVETA in obj:
            return obj
        if MARCA_GRUPO in obj:
            return None
        obj = obj.parent
    return None


def gavetas_do_grupo(grupo):
    return sorted((o for o in grupo.children if MARCA_GAVETA in o),
                  key=lambda o: int(o.get(CHAVE_INDICE, 0)))


def grupos_do_modulo(conj):
    return [o for o in conj.children if MARCA_GRUPO in o]


def modulo_do_grupo(grupo):
    # Preset inserido/renomeado pode guardar o nome do modulo original.
    # A hierarquia real prevalece, inclusive se aquele nome ainda existir.
    pai = grupo.parent
    while pai is not None:
        if _chapas.MARCA_CONJUNTO in pai:
            return pai
        pai = pai.parent
    modulo = bpy.data.objects.get(grupo.get(CHAVE_MODULO, ''))
    if modulo is not None and _chapas.MARCA_CONJUNTO in modulo:
        return modulo
    return None


def parametros(grupo):
    p = dict(PARAMETROS_PADRAO)
    dados = grupo.get(CHAVE_PARAMETROS)
    p.update(dados.to_dict() if dados is not None else {})
    return p


def frente_da_gaveta(gaveta):
    return next((o for o in gaveta.children if o.get(MARCA_PECA) == 'FRENTE'), None)


# ------------------------------------------------------------ calculo
def trilho_que_cabe(tipo, disponivel):
    """O maior comprimento de linha que cabe em `disponivel` mm, ou None."""
    cabem = [c for c in TRILHOS[tipo]['comprimentos'] if c <= disponivel + 1e-6]
    return max(cabem) if cabem else None


def frentes(largura, altura, p):
    """[(x0, x1, z0, z1)] das frentes, de BAIXO para cima."""
    n = max(1, int(p['quantidade']))
    folga, g = float(p['folga_frontal_mm']), float(p['entre_gavetas_mm'])
    if p['cobertura'] == 'SOBREPOSTA':
        c = max(0.0, float(p['lateral_mm']) - folga)
        x0, x1, z0, z1 = -c, largura + c, -c, altura + c
    else:
        x0, x1, z0, z1 = folga, largura - folga, folga, altura - folga
    util = z1 - z0 - (n - 1) * g
    pesos = [float(v) for v in (p.get('proporcoes') or ())]
    if len(pesos) != n or min(pesos, default=0.0) <= 0.0:
        pesos = [1.0] * n
    alturas = [util * v / sum(pesos) for v in pesos]
    if min(alturas) < ALTURA_MIN_FRENTE_MM:
        raise ValueError("Gavetas demais para a altura: frente de %d mm"
                         % round(min(alturas)))
    saida, z = [], z0
    for a in alturas:
        saida.append((x0, x1, z, z + a))
        z += a + g
    return saida


def calcular(largura, altura, p):
    """Tudo de cada gaveta em caixas (x0, x1, y0, y1, z0, z1) mm:
    {'trilho_mm', 'gavetas': [{'frente', 'caixa': [(peca, nome, caixa,
    eixo)], 'fixos': [caixa], 'moveis': [caixa]}]}."""
    if largura < LARGURA_MIN_VAO_MM or altura < ALTURA_MIN_FRENTE_MM:
        raise ValueError("Vao pequeno demais para gaveta (%d x %d mm)"
                         % (round(largura), round(altura)))
    trilho = TRILHOS[p['trilho']]
    e = float(p['espessura_frente_mm'])
    recuo = float(p['recuo_mm'])
    if p['cobertura'] == 'SOBREPOSTA':
        fy0, fy1 = recuo - e, recuo
    else:
        fy0, fy1 = recuo, recuo + e
    inicio = fy1                             # a caixa nasce atras da frente
    disponivel = float(p['profundidade_mm']) - inicio - FOLGA_FUNDO_MODULO_MM
    comprimento = trilho_que_cabe(p['trilho'], disponivel)
    if comprimento is None:
        raise ValueError("Profundidade de %d mm: o menor trilho %s tem %d mm"
                         % (round(disponivel), dict(OPCOES_TRILHO)[p['trilho']].lower(),
                            trilho['comprimentos'][0]))
    folga_lado = trilho['folga_lado']
    bx0, bx1 = folga_lado, largura - folga_lado
    if bx1 - bx0 < LARGURA_MIN_VAO_MM - 2 * folga_lado:
        raise ValueError("O vao nao deixa largura para a caixa")
    by0, by1 = inicio, inicio + comprimento
    ec, ef = ESPESSURA_CAIXA_MM, FUNDO_CAIXA_MM
    saida = []
    for i, (x0, x1, z0, z1) in enumerate(frentes(largura, altura, p)):
        s0, s1 = max(0.0, z0), min(altura, z1)
        cz0, cz1 = s0 + trilho['caixa_baixo'], s1 - FOLGA_TOPO_CAIXA_MM
        if cz1 - cz0 < ALTURA_MIN_CAIXA_MM:
            raise ValueError("A frente %d nao deixa altura para a caixa" % (i + 1))
        caixa = [
            ('FUNDO', 'Fundo', (bx0, bx1, by0, by1, cz0, cz0 + ef), 2),
            ('LATERAL', 'Lateral Esquerda', (bx0, bx0 + ec, by0, by1, cz0 + ef, cz1), 0),
            ('LATERAL', 'Lateral Direita', (bx1 - ec, bx1, by0, by1, cz0 + ef, cz1), 0),
            ('CONTRAFRENTE', 'Contrafrente',
             (bx0 + ec, bx1 - ec, by0, by0 + ec, cz0 + ef, cz1), 1),
            ('TRASEIRA', 'Traseira',
             (bx0 + ec, bx1 - ec, by1 - ec, by1, cz0 + ef, cz1), 1),
        ]
        fixos, moveis = [], []
        if p['trilho'] == 'TELESCOPICO':
            meio = cz0 + min(35.0, (cz1 - cz0) / 2.0)
            t = TELESCOPICO_ESPESSURA_MM / 2.0
            for xa, xb, xc, xd in ((0.0, t, t, 2 * t),
                                   (largura - t, largura, largura - 2 * t, largura - t)):
                fixos.append((xa, xb, by0, by1, meio - TELESCOPICO_ALTURA_MM / 2,
                              meio + TELESCOPICO_ALTURA_MM / 2))
                moveis.append((xc, xd, by0, by1, meio - 17.5, meio + 17.5))
        else:
            for xa in (bx0, bx1 - OCULTO_LARGURA_MM):
                fixos.append((xa, xa + OCULTO_LARGURA_MM, by0, by1, s0 + 2.0, s0 + 12.0))
                moveis.append((xa, xa + OCULTO_LARGURA_MM, by0, by1, s0 + 12.0, cz0))
        saida.append({'frente': (x0, x1, fy0, fy1, z0, z1), 'caixa': caixa,
                      'fixos': fixos, 'moveis': moveis})
    return {'trilho_mm': comprimento, 'gavetas': saida}


# ------------------------------------------------------------ vao
def _limites(conj):
    return _portas._limites_locais_modulo(conj)


def margens_do_vao(conj, ponto_a, ponto_b):
    """(esq, dir, baixo, cima, frente) mm do vao marcado na diagonal
    (pontos de mundo), medidos da caixa do modulo."""
    lo, hi = _limites(conj)
    a = _portas._local_no_modulo(conj, ponto_a)
    b = _portas._local_no_modulo(conj, ponto_b)
    return (min(a.x, b.x) - lo.x, hi.x - max(a.x, b.x),
            min(a.z, b.z) - lo.z, hi.z - max(a.z, b.z),
            max(0.0, min(a.y, b.y) - lo.y))


def vao(grupo):
    """(largura, altura, matriz do grupo no modulo) pelas margens atuais.
    Redimensionar o modulo move o bloco e recalcula estas margens."""
    conj = modulo_do_grupo(grupo)
    margens = list(grupo.get(CHAVE_MARGENS) or (0, 0, 0, 0, 0))
    if conj is None or _limites(conj) is None:
        largura, altura = grupo.get(CHAVE_VAO) or (500.0, 200.0)
        return float(largura), float(altura), grupo.matrix_basis.copy()
    lo, hi = _limites(conj)
    esq, dir_, baixo, cima, frente = margens
    origem = Vector((lo.x + esq, lo.y + frente, lo.z + baixo))
    largura = hi.x - dir_ - origem.x
    altura = hi.z - cima - origem.z
    return largura, altura, Matrix.Translation(origem / 1000.0)


def _mundo_do_vao(conj, origem_mm):
    return conj.matrix_world @ Matrix.Translation(Vector(origem_mm) / 1000.0)


# ------------------------------------------------------------ montagem
def _matriz_da_caixa(caixa, eixo):
    x0, x1, y0, y1, z0, z1 = caixa
    medidas = Vector((x1 - x0, y1 - y0, z1 - z0))
    colunas = [Vector(c) for c in EIXOS_PECA[eixo]]
    rotacao = Matrix(colunas).transposed()
    centro = Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)) / 1000.0
    dims = tuple(abs(c.dot(medidas)) for c in colunas)
    return Matrix.Translation(centro) @ rotacao.to_4x4(), dims


def _colecao(grupo):
    return (grupo.users_collection[0] if grupo.users_collection
            else bpy.context.scene.collection)


def _nova_chapa(grupo, pai, nome, caixa, eixo, peca, extras=None):
    obj = bpy.data.objects.new(nome, bpy.data.meshes.new(nome))
    _colecao(grupo).objects.link(obj)
    obj[_chapas.MARCA_CHAPA] = 1
    obj[MARCA_PECA] = peca
    for chave, valor in (extras or {}).items():
        obj[chave] = valor
    obj.parent = pai
    obj.matrix_parent_inverse = Matrix.Identity(4)
    matriz, (l, c, e) = _matriz_da_caixa(caixa, eixo)
    obj.matrix_basis = matriz
    _chapas._ocupado[0] = True
    try:
        obj.chapa_largura_mm, obj.chapa_comprimento_mm = l, c
        obj.chapa_espessura_mm = e
        obj.chapa_auto = True
    finally:
        _chapas._ocupado[0] = False
    _chapas.gerar_malha_chapa(obj)
    return obj


def _material_trilho():
    mat = bpy.data.materials.get(NOME_MATERIAL_TRILHO)
    if mat is None:
        mat = bpy.data.materials.new(NOME_MATERIAL_TRILHO)
        mat.diffuse_color = (0.55, 0.57, 0.6, 1.0)
    return mat


def _novo_trilho(grupo, pai, nome, caixa):
    """Blocagem do trilho: uma caixa nas medidas reais."""
    x0, x1, y0, y1, z0, z1 = caixa
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co = Vector((v.co.x * (x1 - x0), v.co.y * (y1 - y0),
                           v.co.z * (z1 - z0))) / 1000.0
        malha = bpy.data.meshes.new(nome)
        bm.to_mesh(malha)
    finally:
        bm.free()
    malha.materials.append(_material_trilho())
    obj = bpy.data.objects.new(nome, malha)
    _colecao(grupo).objects.link(obj)
    obj[MARCA_PECA] = 'TRILHO'
    obj.parent = pai
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = Matrix.Translation(
        Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)) / 1000.0)
    return obj


def _remover(obj):
    malha = obj.data if obj.type == 'MESH' else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if malha is not None and malha.users == 0:
        bpy.data.meshes.remove(malha)


def _material_de(objs):
    for o in objs:
        for slot in getattr(o, 'material_slots', ()):
            if slot.material is not None:
                return slot.material
    return None


def _pintar(objs, mat):
    if mat is None:
        return
    for obj in objs:
        if not obj.material_slots:
            obj.data.materials.append(None)
        for slot in obj.material_slots:
            slot.link = 'OBJECT'
            slot.material = mat


def colocar_puxador(gaveta, valor):
    """Puxador na borda de CIMA da frente, na face de fora (frente em -Y)."""
    frente = frente_da_gaveta(gaveta)
    if frente is None:
        return None
    for velho in [f for f in frente.children if _chapas.MARCA_PUXADOR in f]:
        _remover(velho)
    gaveta[CHAVE_PUXADOR] = valor
    if not valor or valor == 'NENHUM':
        _chapas.gerar_malha_chapa(frente)        # devolve a madeira do perfil
        return None
    tipo, arquivo = _puxadores.modelo_do_valor(valor)
    if tipo not in _puxadores.MODELOS_PUXADOR:
        return None
    # chapa da frente: X = largura, Y = altura (Y+ = cima), Z = fora
    return _puxadores.criar_puxador(bpy.context, frente, tipo, 'Y+', 1,
                                    arquivo=arquivo)


def montar(grupo):
    """Refaz as gavetas do grupo pelos parametros e pelo vao de hoje.
    Ficam a abertura, o puxador de cada gaveta e o material (frente e
    caixa). Levanta ValueError (e nao mexe em nada) se nao couber."""
    p = parametros(grupo)
    largura, altura, matriz = vao(grupo)
    dados = calcular(largura, altura, p)
    antigas = {int(g.get(CHAVE_INDICE, 0)): g for g in gavetas_do_grupo(grupo)}
    selecionadas = {i for i, g in antigas.items() if g.select_get()}
    grupo_selecionado = grupo.select_get()
    ativo = gaveta_de(bpy.context.view_layer.objects.active)
    indice_ativo = next((i for i, g in antigas.items() if g == ativo), None)
    fracoes = {i: float(g.get(CHAVE_ABERTURA, 0.0)) for i, g in antigas.items()}
    puxadores = {i: g.get(CHAVE_PUXADOR, p['puxador']) for i, g in antigas.items()}
    ajustes_puxadores = {}
    for i, gaveta in antigas.items():
        frente = frente_da_gaveta(gaveta)
        pux = next((o for o in frente.children if _puxadores._eh_puxador_parametrico(o)),
                   None) if frente is not None else None
        if pux is not None:
            ajustes_puxadores[i] = {k: pux[k] for k in (
                'puxador_borda', 'puxador_face', 'puxador_fracao',
                'puxador_comprimento_mm', 'puxador_recuo_mm') if k in pux}
    pecas = [o for o in grupo.children_recursive if o.get(MARCA_PECA)]
    mat_frente = _material_de([o for o in pecas if o.get(MARCA_PECA) == 'FRENTE'])
    mat_caixa = _material_de([o for o in pecas if o.get(MARCA_PECA) not in ('FRENTE', 'TRILHO')])
    for o in list(reversed(grupo.children_recursive)):
        _remover(o)
    grupo.matrix_parent_inverse = Matrix.Identity(4)
    modulo = modulo_do_grupo(grupo)
    if modulo is not None:
        grupo[CHAVE_MODULO] = modulo.name
        grupo.matrix_basis = matriz
    grupo[CHAVE_VAO] = (largura, altura)
    grupo[CHAVE_TRILHO_MM] = float(dados['trilho_mm'])
    frentes_novas, caixas_novas = [], []
    for i, d in enumerate(dados['gavetas']):
        gaveta = bpy.data.objects.new('Gaveta %d' % (i + 1), None)
        _colecao(grupo).objects.link(gaveta)
        gaveta.empty_display_size = 0.02
        gaveta.hide_render = True
        gaveta[MARCA_GAVETA] = 1
        gaveta[CHAVE_INDICE] = i
        gaveta.parent = grupo
        gaveta.matrix_parent_inverse = Matrix.Identity(4)
        # frente CURVA (pedido do usuario, do gaveteiro de canto do
        # Promob): arco de flecha `frente_curva_mm` para FORA, as pontas
        # no plano da frente reta (`_chapas._malha_arco`)
        curva = float(p.get('frente_curva_mm') or 0.0)
        frentes_novas.append(_nova_chapa(
            grupo, gaveta, 'Frente Gaveta %d' % (i + 1), d['frente'], 1, 'FRENTE',
            {'chapa_arco_mm': curva} if curva > 0.0 else None))
        for peca, nome, caixa, eixo in d['caixa']:
            caixas_novas.append(_nova_chapa(grupo, gaveta, '%s Gaveta %d' % (nome, i + 1),
                                            caixa, eixo, peca))
        for lado, caixa in zip(('Esquerdo', 'Direito'), d['fixos']):
            _novo_trilho(grupo, grupo, 'Trilho %s Gaveta %d' % (lado, i + 1), caixa)
        for lado, caixa in zip(('Esquerdo', 'Direito'), d['moveis']):
            _novo_trilho(grupo, gaveta, 'Corredica %s Gaveta %d' % (lado, i + 1), caixa)
        pux = colocar_puxador(gaveta, puxadores.get(i, p['puxador']))
        ajustes = ajustes_puxadores.get(i, {})
        if pux is not None and any(pux.get(k) != v for k, v in ajustes.items()
                                  if k != 'puxador_comprimento_mm' or
                                  pux.get('puxador_tipo') != 'PERFIL'):
            for chave, valor in ajustes.items():
                pux[chave] = valor
            # O perfil precisa recortar a borda escolhida; os outros
            # puxadores so' refazem o lugar e as medidas individuais.
            if pux.get('puxador_tipo') == 'PERFIL' and pux.get('puxador_borda') != 'Y+':
                _chapas.gerar_malha_chapa(pux.parent)
            else:
                _puxadores.posicionar_puxador(pux)
        definir_abertura(gaveta, fracoes.get(i, 0.0))
    _pintar(frentes_novas, mat_frente)
    _pintar(caixas_novas, mat_caixa)
    bpy.context.view_layer.update()
    # As chapas sao refeitas, mas a selecao continua no mesmo nivel.
    if grupo_selecionado:
        selecionar(bpy.context, grupo, 'GRUPO', somar=True)
    else:
        novas = {int(g[CHAVE_INDICE]): g for g in gavetas_do_grupo(grupo)}
        for i in sorted(selecionadas):
            if i in novas:
                selecionar(bpy.context, novas[i], 'GAVETA', somar=True)
        if indice_ativo in novas:
            bpy.context.view_layer.objects.active = novas[indice_ativo]


def criar_gavetas(context, conj, margens, p):
    """Grupo de gavetas novo no modulo `conj`. Devolve o grupo."""
    p = dict(PARAMETROS_PADRAO, **p)
    nome = 'Gavetas %s' % conj.name
    grupo = bpy.data.objects.new(nome, None)
    colecao = _modulos._colecao_do_modulo(conj) or context.scene.collection
    colecao.objects.link(grupo)
    grupo.empty_display_type = 'PLAIN_AXES'
    grupo.empty_display_size = 0.05
    grupo.hide_render = True
    grupo[MARCA_GRUPO] = 1
    grupo[CHAVE_MODULO] = conj.name
    grupo[CHAVE_PARAMETROS] = p
    grupo[CHAVE_MARGENS] = [float(m) for m in margens]
    grupo.parent = conj
    try:
        montar(grupo)
    except ValueError:
        _remover(grupo)
        raise
    return grupo


def acompanhar_redimensionamento(conj, lo_antes, hi_antes, lo, hi):
    """Move o bloco inteiro pela face mais proxima, sem esticar pecas.
    Usa o vao FECHADO de antes: abrir uma gaveta nao muda sua ancoragem."""
    for grupo in grupos_do_modulo(conj):
        largura, altura = grupo[CHAVE_VAO]
        profundidade = float(parametros(grupo)['profundidade_mm'])
        cantos = [grupo.matrix_world @ (Vector((x, y, z)) / 1000.0)
                  for x in (0.0, largura) for y in (0.0, profundidade)
                  for z in (0.0, altura)]
        delta = Vector()
        for eixo in range(3):
            minimo = min(p[eixo] for p in cantos)
            maximo = max(p[eixo] for p in cantos)
            # Empate ancora no minimo; erro de float nao deve trocar de face.
            perto_do_min = (minimo - lo_antes[eixo]) <= (hi_antes[eixo] - maximo) + 1e-6
            delta[eixo] = (lo[eixo] - lo_antes[eixo] if perto_do_min
                           else hi[eixo] - hi_antes[eixo])
        if delta.length > 1e-9:
            matriz = grupo.matrix_world.copy()
            matriz.translation += delta
            grupo.matrix_world = matriz


def atualizar_gavetas_do_conjunto(conj):
    """Redimensionar a caixa nao redimensiona as gavetas internas.
    Recalcula as margens para a edicao direta partir das mesmas medidas."""
    lo, hi = _limites(conj)
    for grupo in grupos_do_modulo(conj):
        largura, altura = grupo[CHAVE_VAO]
        # A origem do modulo compensa os filhos pela matrix_parent_inverse.
        origem = (conj.matrix_world.inverted() @ grupo.matrix_world).translation * 1000.0
        grupo[CHAVE_MARGENS] = (origem.x - lo.x, hi.x - origem.x - largura,
                                origem.z - lo.z, hi.z - origem.z - altura,
                                origem.y - lo.y)


def editar(context, grupo, nome, valor):
    """Muda um parametro (aba Gavetas). Devolve o erro (e desfaz) ou None."""
    nome = nome[len('gavetas_'):] if nome.startswith('gavetas_') else nome
    antes = grupo[CHAVE_PARAMETROS].to_dict()
    novo = dict(antes)
    if nome == 'quantidade':
        valor = max(1, min(MAXIMO_GAVETAS, int(valor)))
        if valor != int(antes.get('quantidade', 1)):
            novo.pop('proporcoes', None)      # outra quantidade: iguais
    novo[nome] = valor
    grupo[CHAVE_PARAMETROS] = novo
    try:
        montar(grupo)
    except ValueError as erro:
        grupo[CHAVE_PARAMETROS] = antes
        montar(grupo)
        return str(erro)
    if nome == 'puxador':
        for gaveta in gavetas_do_grupo(grupo):
            colocar_puxador(gaveta, valor)
    return None


def trocar_puxador(context, valor):
    """Carrossel da aba: uma gaveta selecionada (duplo clique) troca so'
    a dela; o grupo, todas (e vira o padrao do grupo)."""
    obj = context.object
    gaveta, grupo = gaveta_de(obj), grupo_de(obj)
    if grupo is None:
        return 'Selecione as gavetas'
    if gaveta is not None and MARCA_GRUPO not in obj:
        colocar_puxador(gaveta, valor)
        return None
    return editar(context, grupo, 'puxador', valor)


# ------------------------------------------------------------ abertura
def curso(gaveta):
    grupo = grupo_de(gaveta)
    return float(grupo.get(CHAVE_TRILHO_MM, 0.0)) if grupo is not None else 0.0


def definir_abertura(gaveta, fracao):
    """Trilho de extensao total: aberta = o comprimento do trilho."""
    fracao = max(0.0, min(1.0, float(fracao)))
    gaveta[CHAVE_ABERTURA] = fracao
    gaveta.matrix_basis = Matrix.Translation(
        Vector((0.0, -fracao * curso(gaveta) / 1000.0, 0.0)))
    return True


# ------------------------------------------------------------ selecao
def selecionar(context, obj, nivel, somar=False):
    """'GRUPO' = todas as gavetas do vao; 'GAVETA' = so' a de `obj`."""
    grupo = grupo_de(obj)
    if grupo is None:
        return False
    alvo = gaveta_de(obj) if nivel == 'GAVETA' else None
    alvo = alvo or grupo
    if not somar:
        for o in context.selected_objects:
            o.select_set(False)
    for o in [alvo, *alvo.children_recursive]:
        if o.visible_get() and _chapas.MARCA_PUXADOR not in o:
            o.select_set(True)
    context.view_layer.objects.active = alvo
    if context.area:
        context.area.tag_redraw()
    return True


def selecionados(context):
    """Grupos de gavetas com o grupo OU uma gaveta selecionado (e ativo
    entre eles) -- o modulo selecionado nao conta."""
    grupos = []
    for o in getattr(context, 'selected_objects', ()) or ():
        if MARCA_GRUPO in o or MARCA_GAVETA in o:
            g = grupo_de(o)
            modulo = modulo_do_grupo(g) if g is not None else None
            if modulo is not None and modulo.select_get():
                continue
            if g is not None and g not in grupos:
                grupos.append(g)
    return grupos


def gavetas_com_slider(context):
    saida = []
    for o in getattr(context, 'selected_objects', ()) or ():
        grupo = grupo_de(o)
        modulo = modulo_do_grupo(grupo) if grupo is not None else None
        if modulo is not None and modulo.select_get():
            continue
        if MARCA_GRUPO in o:
            candidatas = gavetas_do_grupo(o)
        elif MARCA_GAVETA in o:
            candidatas = [o]
        else:
            continue
        saida += [g for g in candidatas if g not in saida]
    return saida


# ------------------------------------------------------------ HUD
def medidas(grupo):
    """(largura, altura, profundidade) mm que a HUD e a aba mostram."""
    largura, altura, _m = vao(grupo)
    return largura, altura, float(parametros(grupo)['profundidade_mm'])


def cantos_hud(grupo):
    """8 quinas (mundo) da caixa do vao com a profundidade; indice
    i + 2j + 4k ao longo de X, Y (profundidade), Z."""
    largura, altura, prof = medidas(grupo)
    m = grupo.matrix_world
    return [m @ (Vector((i * largura, j * prof, k * altura)) / 1000.0)
            for k in (0, 1) for j in (0, 1) for i in (0, 1)]


def linhas_hud(grupo, chapas):
    """Linhas da HUD (tipo 'gavetas'): L nas arestas em X, P em Y, A em
    Z; a quina mais perto do mouse fica parada, como no modulo."""
    cantos = cantos_hud(grupo)
    letras = {0: 'L', 1: 'P', 2: 'A'}
    linhas = []
    for eixo, arestas in enumerate(_hud.ARESTAS_EIXO):
        for i, j in arestas:
            linhas.append({'tipo': 'gavetas', 'objeto': grupo, 'modo': 'GAVETAS',
                           'eixo': eixo, 'letra': letras[eixo],
                           'face': (letras[eixo],), 'cantos': (i, j),
                           'chapas': chapas, 'pontos': [cantos[i], cantos[j]]})
    return cantos, linhas


def valor(grupo, chave):
    largura, altura, prof = medidas(grupo)
    return {'L': largura, 'A': altura, 'P': prof}[chave[0]]


def aplicar(context, grupo, chave, novo, lado=None):
    """Medida da HUD/aba: L e A mudam a MARGEM do lado que anda (a quina
    perto do mouse fica); P e' a profundidade."""
    letra = chave[0] if isinstance(chave, (tuple, list)) else chave
    if letra == 'P':
        novo = max(100.0, float(novo))
        if lado != 'max':
            return editar(context, grupo, 'profundidade_mm', novo)
        antes = list(grupo[CHAVE_MARGENS])
        margens = list(antes)
        # Costas fixas: a frente anda pelo delta da profundidade.
        margens[4] -= novo - valor(grupo, ('P',))
        grupo[CHAVE_MARGENS] = margens
        erro = editar(context, grupo, 'profundidade_mm', novo)
        if erro:
            grupo[CHAVE_MARGENS] = antes
            montar(grupo)
        return erro
    margens = list(grupo.get(CHAVE_MARGENS) or (0, 0, 0, 0, 0))
    variacao = float(novo) - valor(grupo, (letra,))
    if letra == 'L':
        indice = 1 if lado != 'max' else 0
    else:
        indice = 3 if lado != 'max' else 2
    antes = list(margens)
    margens[indice] = max(0.0, margens[indice] - variacao)
    grupo[CHAVE_MARGENS] = margens
    try:
        montar(grupo)
    except ValueError as erro:
        grupo[CHAVE_MARGENS] = antes
        montar(grupo)
        return str(erro)
    return None


def copia(grupo):
    """Parametros copiados, sem referencias a pecas que montar apaga."""
    return (grupo.name, grupo[CHAVE_PARAMETROS].to_dict(), list(grupo[CHAVE_MARGENS]))


def restaurar(estado):
    nome, p, margens = estado
    grupo = bpy.data.objects.get(nome)
    if grupo is None:
        return
    grupo[CHAVE_PARAMETROS] = p
    grupo[CHAVE_MARGENS] = margens
    montar(grupo)


# ---- os 3 pontos com Alt (pedido do usuario): as duas quinas da frente
# na diagonal (de cima a' esquerda e de baixo a' direita) e a
# profundidade; arrastar com ima nos vertices refaz o vao
_arraste_ponto = [None]


def pontos_editaveis(grupo):
    largura, altura, prof = medidas(grupo)
    m = grupo.matrix_world
    return [m @ (Vector(p) / 1000.0) for p in
            ((0.0, 0.0, altura), (largura, 0.0, 0.0), (largura / 2.0, prof, 0.0))]


def ponto_sob_mouse(context, posicao):
    """(grupo, indice) do ponto sob o mouse (so' com Alt)."""
    if not _solda._correntes_visiveis():
        return None, None
    raio = _solda.RAIO_BOLINHA_PX * max(1.0, context.preferences.system.ui_scale)
    mouse = Vector(posicao)
    melhor = None
    for grupo in selecionados(context):
        for i, ponto in enumerate(pontos_editaveis(grupo)):
            p = _hud._projetar_hud(context, ponto)
            if p is None:
                continue
            d = (p - mouse).length
            if d <= raio and (melhor is None or d < melhor[0]):
                melhor = (d, grupo, i)
    return (melhor[1], melhor[2]) if melhor else (None, None)


def _aplicar_ponto(grupo, indice, ponto_mundo):
    """Leva o ponto `indice` a `ponto_mundo` (margens ou profundidade)."""
    conj = modulo_do_grupo(grupo)
    if conj is None:
        return 'Gavetas sem modulo'
    local = grupo.matrix_world.inverted() @ Vector(ponto_mundo) * 1000.0
    if indice == 2:
        return editar(bpy.context, grupo, 'profundidade_mm', max(100.0, local.y))
    largura, altura, _p = medidas(grupo)
    margens = list(grupo.get(CHAVE_MARGENS) or (0, 0, 0, 0, 0))
    antes = list(margens)
    if indice == 0:          # de cima a' esquerda
        margens[0] += local.x
        margens[3] -= local.z - altura
    else:                    # de baixo a' direita
        margens[1] -= local.x - largura
        margens[2] += local.z
    grupo[CHAVE_MARGENS] = margens
    try:
        montar(grupo)
    except ValueError as erro:
        grupo[CHAVE_MARGENS] = antes
        montar(grupo)
        return str(erro)
    return None


def _dentro(obj, grupo):
    while obj is not None:
        if obj == grupo:
            return True
        obj = obj.parent
    return False


def _ponto_livre(context, grupo, indice, mouse):
    """Sem ima: a quina anda no plano da frente; a profundidade, no eixo
    dela (o ponto da reta mais perto do raio do mouse)."""
    regiao, rv3d = context.region, context.region_data
    origem = view3d_utils.region_2d_to_origin_3d(regiao, rv3d, mouse)
    direcao = view3d_utils.region_2d_to_vector_3d(regiao, rv3d, mouse)
    m = grupo.matrix_world
    eixos = m.to_3x3()
    if indice < 2:
        normal = eixos.col[1].normalized()
        base = m.translation
        d = direcao.dot(normal)
        if abs(d) < 1e-6:
            return None
        return origem + direcao * ((base - origem).dot(normal) / d)
    p0 = pontos_editaveis(grupo)[2]
    eixo = eixos.col[1].normalized()
    w0 = p0 - origem
    a, b, c = eixo.dot(eixo), eixo.dot(direcao), direcao.dot(direcao)
    d, e = eixo.dot(w0), direcao.dot(w0)
    den = a * c - b * b
    if abs(den) < 1e-9:
        return None
    s = (b * e - c * d) / den
    return p0 + eixo * s


class IndiceSnapGavetas:
    """Pontos em mundo indexados na tela durante UM arraste.
    Movimentos do mouse consultam a arvore; so' navegar refaz a projecao."""

    def __init__(self, alvos):
        # NumPy vem com o Blender. Carregar so' no arraste evita custo no register.
        import numpy as np
        self._pontos = np.asarray([co for _nome, pontos in alvos for co in pontos],
                                  dtype=np.float32).reshape((-1, 3))
        self._vista = None
        self._arvore = None

    def _reconstruir(self, matriz, largura, altura):
        import numpy as np
        self._arvore = None
        if not len(self._pontos):
            return
        m = np.asarray(matriz, dtype=np.float32)
        # Mesma projecao de location_3d_to_region_2d, em lote: w > 0.
        clip = self._pontos @ m[:, :3].T + m[:, 3]
        indices = np.flatnonzero(clip[:, 3] > 0)
        clip = clip[indices]
        tela = (clip[:, :2] / clip[:, 3, None] + 1) * np.asarray(
            (largura / 2.0, altura / 2.0), dtype=np.float32)
        raio = _portas.RAIO_IMA_PX
        visiveis = (np.isfinite(tela).all(axis=1) &
                    (tela[:, 0] >= -raio) & (tela[:, 0] <= largura + raio) &
                    (tela[:, 1] >= -raio) & (tela[:, 1] <= altura + raio))
        # Vertices coincidentes (frente/costas, soldas) nao precisam de
        # milhares de entradas iguais. A primeira preserva a prioridade.
        unicos = {}
        for indice, (x, y) in zip(indices[visiveis], tela[visiveis]):
            unicos.setdefault((float(x), float(y)), int(indice))
        if not unicos:
            return
        arvore = KDTree(len(unicos))
        for (x, y), indice in unicos.items():
            arvore.insert((x, y, 0.0), indice)
        arvore.balance()
        self._arvore = arvore

    def buscar(self, context, mouse):
        regiao, rv3d = context.region, context.region_data
        matriz = tuple(tuple(linha) for linha in rv3d.perspective_matrix)
        vista = (regiao.width, regiao.height, matriz)
        if vista != self._vista:
            self._reconstruir(matriz, regiao.width, regiao.height)
            self._vista = vista
        if self._arvore is None:
            return None
        ponto = Vector((mouse[0], mouse[1], 0.0))
        _co, indice, distancia = self._arvore.find(ponto)
        if distancia > _portas.RAIO_IMA_PX:
            return None
        # Empate na tela continua escolhendo o primeiro ponto, como antes.
        empatados = self._arvore.find_range(ponto, distancia + 1e-5)
        _co, indice, _dist = min(empatados, key=lambda item: (item[2], item[1]))
        return Vector(self._pontos[indice])


def _preparar_ancora_nativa(context, grupo, indice):
    """O cursor e' so' o ponto temporario: o translate nativo nao move
    nenhum objeto selecionado. A macro faz translate + aplicar num undo."""
    ponto = pontos_editaveis(grupo)[indice]
    # O filtro nativo ONLY_SELECTABLE evita BVHs das ferragens e que a
    # propria frente capture a ancora. O bloqueio dura so' esta macro.
    proprias = {o.name for o in grupo.children_recursive}
    bloqueados = []
    for obj in context.visible_objects:
        dono = obj
        acessorio = False
        while dono is not None:
            if ('eh_puxador' in dono or
                    ('eh_acessorio' in dono and 'eh_peca_curva' not in dono)):
                acessorio = True
                break
            dono = dono.parent
        if obj.type == 'MESH' and (obj.name in proprias or acessorio):
            bloqueados.append((obj.name, obj.hide_select))
            obj.hide_select = True
    _arraste_ponto[0] = {
        'nativo': True, 'regiao': context.region.as_pointer(),
        'area': context.area.as_pointer(), 'cena': context.scene.name,
        'grupo': grupo.name, 'indice': indice, 'ponto': ponto.copy(), 'ima': False,
        'cursor': tuple(context.scene.cursor.location),
        'mostrar_cursor': context.space_data.overlay.show_cursor,
        'bloqueados': bloqueados,
    }
    context.space_data.overlay.show_cursor = False
    context.scene.cursor.location = ponto
    return dict(cursor_transform=True, snap=True,
                snap_elements={'VERTEX', 'EDGE_MIDPOINT'}, snap_target='CENTER',
                snap_align=False, use_snap_selectable=True, release_confirm=True,
                orient_type='GLOBAL', orient_matrix_type='GLOBAL',
                orient_matrix=tuple(tuple(l) for l in grupo.matrix_world.to_3x3()),
                constraint_axis=(True, False, True) if indice < 2 else (False, True, False))


def _terminar_ancora_nativa(remover_timer=True):
    estado = _arraste_ponto[0]
    if estado and estado.get('nativo'):
        for nome, oculto in estado.get('bloqueados', ()):
            obj = bpy.data.objects.get(nome)
            if obj is not None:
                obj.hide_select = oculto
        cena = bpy.data.scenes.get(estado['cena'])
        if cena is not None:
            cena.cursor.location = estado['cursor']
        for janela in bpy.context.window_manager.windows:
            for area in janela.screen.areas:
                if area.as_pointer() == estado['area'] and area.type == 'VIEW_3D':
                    area.spaces.active.overlay.show_cursor = estado['mostrar_cursor']
                    area.tag_redraw()
    _arraste_ponto[0] = None
    if remover_timer and bpy.app.timers.is_registered(_acompanhar_ancora_nativa):
        bpy.app.timers.unregister(_acompanhar_ancora_nativa)


def _acompanhar_ancora_nativa():
    """Le so' a posicao do cursor, nunca malhas. Esc da macro tambem
    devolve o cursor/overlay quando o translate nativo termina cancelado."""
    estado = _arraste_ponto[0]
    if not estado or not estado.get('nativo'):
        return None
    ativa = any(op.bl_idname == 'OBJECT_OT_cabinet_mover_ancora_gaveta'
                for janela in bpy.context.window_manager.windows for op in janela.modal_operators)
    cena = bpy.data.scenes.get(estado['cena'])
    if not ativa or cena is None:
        _terminar_ancora_nativa(remover_timer=False)
        return None
    estado['ponto'] = cena.cursor.location.copy()
    for janela in bpy.context.window_manager.windows:
        for area in janela.screen.areas:
            if area.as_pointer() == estado['area']:
                area.tag_redraw()
    return 1.0 / 60.0


class OBJECT_OT_confirmar_ancora_gaveta(Operator):
    bl_idname = 'object.cabinet_confirmar_ancora_gaveta'
    bl_label = 'Confirmar Ancora das Gavetas'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        estado = _arraste_ponto[0]
        if not estado or not estado.get('nativo'):
            return {'CANCELLED'}
        grupo = bpy.data.objects.get(estado['grupo'])
        indice = estado['indice']
        ponto = context.scene.cursor.location.copy()
        _terminar_ancora_nativa()
        if grupo is None:
            return {'CANCELLED'}
        erro = _aplicar_ponto(grupo, indice, ponto)
        if erro:
            self.report({'WARNING'}, erro)
            return {'CANCELLED'}
        return {'FINISHED'}


class OBJECT_OT_mover_ancora_gaveta(Macro):
    bl_idname = 'object.cabinet_mover_ancora_gaveta'
    bl_label = 'Editar Ancora das Gavetas'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}


def registrar_macro_ancora():
    OBJECT_OT_mover_ancora_gaveta.define('TRANSFORM_OT_translate')
    OBJECT_OT_mover_ancora_gaveta.define('OBJECT_OT_cabinet_confirmar_ancora_gaveta')


class OBJECT_OT_arrastar_ponto_gaveta(Operator):
    """Arraste uma quina da frente ou a profundidade das gavetas (Alt): ima nos vertices"""
    bl_idname = 'object.cabinet_arrastar_ponto_gaveta'
    bl_label = 'Mover Ponto das Gavetas'
    bl_options = {'INTERNAL'}

    grupo: StringProperty(options={'SKIP_SAVE'})
    indice: IntProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        grupo = bpy.data.objects.get(self.grupo)
        if grupo is None or MARCA_GRUPO not in grupo or context.region is None:
            return {'CANCELLED'}
        if self.indice not in (0, 1, 2):
            return {'CANCELLED'}
        parametros = _preparar_ancora_nativa(context, grupo, self.indice)
        try:
            resultado = bpy.ops.object.cabinet_mover_ancora_gaveta(
                'INVOKE_DEFAULT', TRANSFORM_OT_translate=parametros)
        except Exception:
            _terminar_ancora_nativa()
            raise
        if 'RUNNING_MODAL' not in resultado:
            _terminar_ancora_nativa()
            return {'CANCELLED'}
        bpy.app.timers.register(_acompanhar_ancora_nativa, first_interval=0.0)
        return {'FINISHED'}


# ------------------------------------------------------------ slider
# Um por gaveta, com o grupo (ou a gaveta) selecionado: na FRENTE dela,
# no meio da altura e um pouco a' frente, e anda junto com a gaveta --
# a gaveta aberta nunca o cobre (pedido do usuario); desenhado por cima
# de tudo. Arrastar para a direita abre.
SLIDER_FRENTE_MM = 30.0
SLIDER_RECUO_FRACAO = 0.18
_arraste_slider = [None]     # {'gaveta', 'tela': (inicio, fim)}
_slider_hover = [None]


def _slider_no_mundo(gaveta):
    frente = frente_da_gaveta(gaveta)
    if frente is None:
        return None
    hx = frente.chapa_largura_mm / 2.0
    recuo = max(30.0, SLIDER_RECUO_FRACAO * 2 * hx)
    e = frente.chapa_espessura_mm / 2.0
    # chapa da frente: X = largura, Z = para fora
    return [frente.matrix_world @ (Vector((s * (hx - recuo), 0.0,
                                           e + SLIDER_FRENTE_MM)) / 1000.0)
            for s in (-1, 1)]


def _slider_na_tela(context, gaveta):
    estado = _arraste_slider[0]
    if estado is not None and estado['gaveta'] == gaveta.name:
        return estado['tela']        # parado enquanto arrasta
    mundo = _slider_no_mundo(gaveta)
    if mundo is None:
        return None
    pontos = [_hud._projetar_hud(context, p) for p in mundo]
    if any(p is None for p in pontos) or (pontos[1] - pontos[0]).length < 1:
        return None
    return tuple(sorted(pontos, key=lambda p: p.x))


def _botao(context, gaveta):
    tela = _slider_na_tela(context, gaveta)
    if tela is None:
        return None
    return tela[0].lerp(tela[1], float(gaveta.get(CHAVE_ABERTURA, 0.0)))


def slider_sob_mouse(context, posicao):
    if getattr(context, 'region_data', None) is None:
        return None
    mouse = Vector(posicao)
    raio = 12.0 * max(1.0, context.preferences.system.ui_scale)
    melhor = None
    for gaveta in gavetas_com_slider(context):
        b = _botao(context, gaveta)
        if b is None:
            continue
        d = (b - mouse).length
        if d <= raio and (melhor is None or d < melhor[0]):
            melhor = (d, gaveta)
    return melhor[1] if melhor else None


def desenhar(context):
    """Sliders das gavetas selecionadas e, com Alt, os 3 pontos."""
    gavetas = gavetas_com_slider(context)
    grupos = selecionados(context)
    if not (gavetas or grupos):
        return
    escala = max(1.0, context.preferences.system.ui_scale)
    realce = _hud._cor_realce_hud()
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        for gaveta in gavetas:
            tela = _slider_na_tela(context, gaveta)
            if tela is None:
                continue
            inicio, fim = tela
            fracao = float(gaveta.get(CHAVE_ABERTURA, 0.0))
            botao = inicio.lerp(fim, fracao)
            grosso, raio = 9.0 * escala, 8.0 * escala
            _portas_viewport._capsula_2d(shader, inicio, fim, grosso + 3 * escala,
                                         (0.92, 0.92, 0.92, 1.0))
            _portas_viewport._capsula_2d(shader, inicio, fim, grosso, (0.13, 0.13, 0.13, 1.0))
            if fracao > 0:
                _portas_viewport._capsula_2d(shader, inicio, botao, grosso * 0.65, realce)
            if gaveta.name in (_slider_hover[0], (_arraste_slider[0] or {}).get('gaveta')):
                _hud._bolinha_2d(shader, botao, raio + 3 * escala, realce)
            _hud._bolinha_2d(shader, botao, raio, (1.0, 1.0, 1.0, 1.0))
            _hud._bolinha_2d(shader, botao, raio * 0.45, realce)
            texto = '%d mm' % round(fracao * curso(gaveta))
            tamanho = 11 * escala
            blf.size(0, tamanho)
            largura = blf.dimensions(0, texto)[0]
            _hud._caixa_texto_hud(botao.x - largura / 2.0, botao.y + raio + 6 * escala,
                                  texto, tamanho, escala)
            gpu.state.blend_set('ALPHA')
            shader.bind()
        estado = _arraste_ponto[0]
        if not (_solda._correntes_visiveis() or estado is not None):
            return
        for grupo in grupos:
            pontos = pontos_editaveis(grupo)
            arrastando = estado is not None and estado['grupo'] == grupo.name
            if arrastando:
                pontos[estado['indice']] = estado['ponto']
            for i, ponto in enumerate(pontos):
                p = _hud._projetar_hud(context, ponto)
                if p is None:
                    continue
                aceso = arrastando and i == estado['indice']
                if aceso:
                    _hud._bolinha_2d(shader, p, 8 * escala, realce)
                _hud._bolinha_2d(shader, p, (6 if aceso else 5) * escala,
                                 (1.0, 1.0, 1.0, 1.0))
    finally:
        gpu.state.blend_set('NONE')


class OBJECT_OT_abrir_gaveta(Operator):
    """Arraste o slider da gaveta: para a direita abre, para a esquerda fecha"""
    bl_idname = 'object.cabinet_abrir_gaveta'
    bl_label = 'Abrir Gaveta'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    gaveta: StringProperty(options={'SKIP_SAVE'})
    fracao: FloatProperty(min=0.0, max=1.0, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return _hud._contexto_hud(context)

    def execute(self, context):
        gaveta = bpy.data.objects.get(self.gaveta)
        if gaveta is None or MARCA_GAVETA not in gaveta:
            return {'CANCELLED'}
        definir_abertura(gaveta, self.fracao)
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}

    def invoke(self, context, event):
        gaveta = slider_sob_mouse(context, (event.mouse_region_x, event.mouse_region_y))
        if gaveta is None:
            return {'PASS_THROUGH'}
        self.gaveta = gaveta.name
        self._antes = float(gaveta.get(CHAVE_ABERTURA, 0.0))
        self._area = context.area
        tela = _slider_na_tela(context, gaveta)
        _arraste_slider[0] = {'gaveta': gaveta.name, 'tela': tela}
        self._desvio = self._fracao(event) - self._antes
        context.window_manager.modal_handler_add(self)
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _fracao(self, event):
        inicio, fim = _arraste_slider[0]['tela']
        trilho = fim - inicio
        mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        return max(0.0, min(1.0, (mouse - inicio).dot(trilho) / trilho.length_squared))

    def _encerrar(self):
        _arraste_slider[0] = None
        self._area.tag_redraw()

    def cancel(self, context):
        self._encerrar()

    def modal(self, context, event):
        gaveta = bpy.data.objects.get(self.gaveta)
        if gaveta is None or _arraste_slider[0] is None:
            return {'CANCELLED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            definir_abertura(gaveta, self._antes)
            self._encerrar()
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE', 'LEFTMOUSE'}:
            self.fracao = max(0.0, min(1.0, self._fracao(event) - self._desvio))
            definir_abertura(gaveta, self.fracao)
            self._area.tag_redraw()
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self._encerrar()
                return {'FINISHED'}
            return {'RUNNING_MODAL'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}


class VIEW3D_GT_slider_gaveta(Gizmo):
    """A bolinha do slider da gaveta: gizmo ganha da selecao (keymap)."""
    bl_idname = 'VIEW3D_GT_slider_gaveta'

    def draw(self, context):
        pass

    def test_select(self, context, location):
        gaveta = (slider_sob_mouse(context, location)
                  if _hud._contexto_hud(context) else None)
        nome = gaveta.name if gaveta is not None else None
        if nome != _slider_hover[0]:
            _slider_hover[0] = nome
            context.area.tag_redraw()
        return 0 if gaveta is not None else -1


class VIEW3D_GGT_slider_gaveta(GizmoGroup):
    bl_idname = 'VIEW3D_GGT_slider_gaveta'
    bl_label = 'Slider de abertura das gavetas'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        return _hud._contexto_hud(context) and bool(gavetas_com_slider(context))

    def setup(self, context):
        self.botao = self.gizmos.new('VIEW3D_GT_slider_gaveta')
        self.botao.use_tooltip = False
        self.botao.target_set_operator('object.cabinet_abrir_gaveta')

    def draw_prepare(self, context):
        if not self.botao.is_highlight and _slider_hover[0] is not None:
            _slider_hover[0] = None


# ------------------------------------------------------------ assistente
# "Criar Gavetas" (pedido do usuario): 2 cliques na diagonal do vao (de
# cima a' esquerda a baixo a' direita, ima nos vertices) -> scroll =
# quantas -> mouse = profundidade (Alt gruda num vertice) -> o trilho.
_assistente_gavetas = [None]      # estado do wizard (a aba mostra o recado)
RECADOS = {
    'CANTO1': "Clique no canto de CIMA a' ESQUERDA do vao (Esc cancela)",
    'CANTO2': "Clique no canto de BAIXO a' DIREITA do vao",
    'QUANTIDADE': 'Scroll: quantas gavetas | clique confirma',
    'PROFUNDIDADE': 'Mova: profundidade | Alt gruda num vertice | clique confirma',
    'TRILHO': 'Qual trilho?',
}


def _criando():
    return _assistente_gavetas[0] is not None


class AssistenteDoVao:
    """O assistente que marca um vao do modulo: 2 cliques na diagonal ->
    scroll = quantas -> mouse = profundidade -> trilho. As PRATELEIRAS usam
    o mesmo (`prateleiras.OBJECT_OT_criar_prateleiras`), parando na
    quantidade; o que muda entre os dois sao os ganchos logo abaixo. Mixin, nao Operator: subclasse de operador
    registrado nao se registra de novo."""
    _estado = _assistente_gavetas
    RECADOS = RECADOS
    MAXIMO = MAXIMO_GAVETAS
    ITEM = ('gaveta', 'gavetas')
    ABA = 'GAVETAS'
    FIM_QUANTIDADE = 'clique confirma'

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    # ---------------------------------------------- ganchos
    def _parametros_padrao(self):
        return dict(PARAMETROS_PADRAO)

    def _calcular(self, largura, altura, p):
        return calcular(largura, altura, p)

    def _caixas_da_previa(self, dados):
        """Caixas (x0, x1, y0, y1, z0, z1) que a previa contorna."""
        caixas = []
        for d in dados['gavetas']:
            caixas += [d['frente']] + [c[2] for c in d['caixa'][:1]] + d['fixos']
        return caixas

    def _comecar_no_modulo(self, conj, ponto):
        p = self._w['p']
        p['lateral_mm'] = float(_portas._espessura_do_vao(conj))
        p['espessura_frente_mm'] = p['lateral_mm']
        lo, hi = _limites(conj)
        p['profundidade_mm'] = hi.y - lo.y

    def _limitar_profundidade(self, mm):
        return max(100.0, mm)

    def _recado_profundidade(self, dados):
        return 'Profundidade %d mm (trilho %d) | Alt gruda | clique confirma' % (
            round(self._w['p']['profundidade_mm']), dados['trilho_mm'])

    def _depois_da_quantidade(self, context):
        self._ir('PROFUNDIDADE')
        return {'RUNNING_MODAL'}

    def _depois_da_profundidade(self, context):
        self._ir('TRILHO')
        return {'RUNNING_MODAL'}

    def _criar_grupo(self, context, conj, margens, p):
        return criar_gavetas(context, conj, margens, p)

    def _selecionar_grupo(self, context, grupo):
        selecionar(context, grupo, 'GRUPO')

    # ---------------------------------------------- tela e ima
    def _mouse(self, event):
        return Vector((event.mouse_x - self._regiao.x, event.mouse_y - self._regiao.y))

    def _tela(self, ponto):
        return view3d_utils.location_3d_to_region_2d(self._regiao, self._rv3d, ponto)

    def _imantar(self, mouse):
        melhor = None
        for nome, vertices in self._alvos:
            for co in vertices:
                p = self._tela(co)
                if p is None:
                    continue
                d = (p - mouse).length
                if d <= _portas.RAIO_IMA_PX and (melhor is None or d < melhor[0]):
                    melhor = (d, co, nome)
        _geometria.marcar_rotulo(self._w, melhor[1] if melhor else None)
        return (melhor[1], melhor[2]) if melhor else (None, None)

    def _raio(self, mouse):
        origem = view3d_utils.region_2d_to_origin_3d(self._regiao, self._rv3d, mouse)
        direcao = view3d_utils.region_2d_to_vector_3d(self._regiao, self._rv3d, mouse)
        return origem, direcao

    def _no_plano_da_frente(self, mouse):
        conj = bpy.data.objects.get(self._w.get('modulo', ''))
        if conj is None:
            return None
        origem, direcao = self._raio(mouse)
        normal = conj.matrix_world.to_3x3().col[1].normalized()
        base = self._w['pontos'][0]
        d = direcao.dot(normal)
        if abs(d) < 1e-6:
            return None
        return origem + direcao * ((base - origem).dot(normal) / d)

    def _superficie(self, context, mouse):
        origem, direcao = self._raio(mouse)
        acertou, ponto, _n, _f, obj, _m = context.scene.ray_cast(
            context.evaluated_depsgraph_get(), origem, direcao)
        return (ponto, obj.original.name) if acertou and obj is not None else (None, None)

    # ---------------------------------------------- previa
    def _dados(self):
        """(dados de `calcular`, matriz do vao no mundo) ou (None, None)."""
        w = self._w
        conj = bpy.data.objects.get(w.get('modulo', ''))
        if conj is None or len(w['pontos']) < 2:
            return None, None
        margens = margens_do_vao(conj, *w['pontos'][:2])
        lo, hi = _limites(conj)
        largura = hi.x - margens[1] - lo.x - margens[0]
        altura = hi.z - margens[3] - lo.z - margens[2]
        origem = (lo.x + margens[0], lo.y + margens[4], lo.z + margens[2])
        try:
            dados = self._calcular(largura, altura, w['p'])
        except ValueError as erro:
            w['recado'] = str(erro)
            return None, _mundo_do_vao(conj, origem)
        w['vao'] = (largura, altura)
        return dados, _mundo_do_vao(conj, origem)

    def _desenhar(self):
        regiao = getattr(bpy.context, 'region', None)
        if regiao is None or regiao.as_pointer() != self._regiao_ptr:
            return
        w = self._w
        linhas_vao, linhas = [], []
        pontos = list(w['pontos'])
        if w['etapa'] == 'CANTO2' and w.get('cursor') is not None:
            pontos.append(w['cursor'])
        if len(pontos) == 2 and w['etapa'] == 'CANTO2':
            conj = bpy.data.objects.get(w.get('modulo', ''))
            if conj is not None:
                inv = conj.matrix_world.inverted()
                a, b = inv @ pontos[0], inv @ pontos[1]
                cantos = [conj.matrix_world @ Vector(c) for c in
                          ((a.x, a.y, a.z), (b.x, a.y, a.z), (b.x, a.y, b.z), (a.x, a.y, b.z))]
                for i in range(4):
                    linhas_vao += [cantos[i], cantos[(i + 1) % 4]]
        dados, matriz = (self._dados() if w['etapa'] in ('QUANTIDADE', 'PROFUNDIDADE', 'TRILHO')
                         else (None, None))
        if dados is not None:
            for caixa in self._caixas_da_previa(dados):
                x0, x1, y0, y1, z0, z1 = caixa
                c = [matriz @ (Vector((x, y, z)) / 1000.0)
                     for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
                for i, j in ARESTAS:
                    linhas += [c[i], c[j]]
        try:
            gpu.state.blend_set('ALPHA')
            gpu.state.depth_test_set('NONE')
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            shader.bind()
            gpu.state.line_width_set(2.0)
            if linhas_vao:
                shader.uniform_float('color', _portas.COR_FIO_VAO)
                batch_for_shader(shader, 'LINES', {'pos': linhas_vao}).draw(shader)
            if linhas:
                shader.uniform_float('color', (1.0, 1.0, 1.0, 0.85))
                batch_for_shader(shader, 'LINES', {'pos': linhas}).draw(shader)
            marcas = list(w['pontos'])
            if w.get('cursor') is not None and w['etapa'] in ('CANTO1', 'CANTO2'):
                marcas.append(w['cursor'])
            if marcas:
                gpu.state.point_size_set(11.0)
                tema = bpy.context.preferences.themes[0]
                shader.uniform_float('color', (*tema.view_3d.object_active, 1.0))
                batch_for_shader(shader, 'POINTS', {'pos': marcas}).draw(shader)
        except Exception as e:
            print("[Cabinet Creator] previa das %s:" % self.ITEM[1], e)
        finally:
            gpu.state.line_width_set(1.0)
            gpu.state.point_size_set(1.0)
            gpu.state.blend_set('NONE')

    # ---------------------------------------------- ciclo
    def invoke(self, context, event):
        self._area = context.area
        if _gaveta._eh_area_gaveta(context):
            self._area = next(
                (a for a in context.screen.areas
                 if a.type == 'VIEW_3D' and a != context.area
                 and a.x > context.area.x and a.y == context.area.y), None)
        if self._area is None or self._area.type != 'VIEW_3D':
            self.report({'ERROR'}, "Sem viewport 3D para marcar o vao")
            return {'CANCELLED'}
        self._regiao = next((r for r in self._area.regions if r.type == 'WINDOW'), None)
        self._rv3d = getattr(self._area.spaces.active, 'region_3d', None)
        if self._regiao is None or self._rv3d is None:
            self.report({'ERROR'}, "Sem viewport 3D para marcar o vao")
            return {'CANCELLED'}
        self._regiao_ptr = self._regiao.as_pointer()
        self._alvos = [(o.name, vs) for o, vs in _portas._alvos_do_ima(context)
                       if grupo_de(o) is None]
        if not self._alvos:
            self.report({'WARNING'}, "Nenhuma malha visivel para o ima")
            return {'CANCELLED'}
        self._w = {'etapa': 'CANTO1', 'regiao': self._regiao_ptr, 'pontos': [],
                   'cursor': None, 'modulo': '', 'p': self._parametros_padrao(),
                   'botoes': [], 'bolinhas': [], 'snap_tela': None,
                   'mouse': None, 'recado': self.RECADOS['CANTO1'], 'pergunta': ''}
        self._estado[0] = self._w
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            self._desenhar, (), 'WINDOW', 'POST_VIEW')
        self._handler_2d = bpy.types.SpaceView3D.draw_handler_add(
            _assistente._desenhar_assistente_2d, (self._w,), 'WINDOW', 'POST_PIXEL')
        context.window.cursor_modal_set('CROSSHAIR')
        context.window_manager.modal_handler_add(self)
        self._area.header_text_set(self._w['recado'])
        _eventos._redesenhar_viewports(context)
        return {'RUNNING_MODAL'}

    def _encerrar(self, context):
        self._estado[0] = None
        for nome in ('_handler', '_handler_2d'):
            h = getattr(self, nome, None)
            if h is not None:
                bpy.types.SpaceView3D.draw_handler_remove(h, 'WINDOW')
                setattr(self, nome, None)
        if self._area is not None:
            self._area.header_text_set(None)
            self._area.tag_redraw()
        context.window.cursor_modal_restore()
        _eventos._redesenhar_viewports(context)

    def cancel(self, context):
        self._encerrar(context)

    def _ir(self, etapa):
        w = self._w
        w['etapa'] = etapa
        w['botoes'], w['hover_botao'] = [], None
        w['recado'] = self.RECADOS[etapa]
        if etapa == 'TRILHO':
            escala = max(1.0, bpy.context.preferences.system.ui_scale)
            w['botoes'] = _assistente._botoes_assistente(
                w.get('mouse') or Vector((200, 200)), OPCOES_TRILHO, escala,
                (self._regiao.width, self._regiao.height), 'Qual trilho?')
            w['pergunta'] = 'Qual trilho?'
        elif etapa == 'QUANTIDADE':
            self._recado_quantidade()
        self._area.header_text_set(w['recado'])
        self._area.tag_redraw()
        _eventos._redesenhar_viewports(bpy.context)

    def _recado_quantidade(self):
        w = self._w
        n = w['p']['quantidade']
        w['recado'] = '%d %s | scroll muda, %s' % (n, self.ITEM[n > 1], self.FIM_QUANTIDADE)
        self._dados()

    def _profundidade(self, context, event, mouse):
        """Profundidade pelo mouse: o ponto do eixo de profundidade (do
        meio do vao, para dentro) mais perto do raio; Alt gruda num vertice."""
        w = self._w
        conj = bpy.data.objects.get(w['modulo'])
        dados, matriz = self._dados()
        if matriz is None:
            return
        eixo = conj.matrix_world.to_3x3().col[1].normalized()
        base = matriz.translation
        if event.alt:
            ponto, _nome = self._imantar(mouse)
            if ponto is not None:
                w['p']['profundidade_mm'] = self._limitar_profundidade(
                    (ponto - base).dot(eixo) * 1000.0)
                w['snap_tela'] = self._tela(ponto)
                return
        w['snap_tela'] = None
        origem, direcao = self._raio(mouse)
        w0 = base - origem
        a, b, c = 1.0, eixo.dot(direcao), direcao.dot(direcao)
        d, e = eixo.dot(w0), direcao.dot(w0)
        den = a * c - b * b
        if abs(den) > 1e-9:
            w['p']['profundidade_mm'] = self._limitar_profundidade((b * e - c * d) / den * 1000.0)

    def modal(self, context, event):
        w = self._w
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._encerrar(context)
            return {'CANCELLED'}
        if event.type == 'MIDDLEMOUSE':
            return {'PASS_THROUGH'}
        mouse = self._mouse(event)
        dentro = 0 <= mouse.x < self._regiao.width and 0 <= mouse.y < self._regiao.height
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            if w['etapa'] != 'QUANTIDADE':
                return {'PASS_THROUGH'}
            n = w['p']['quantidade'] + (1 if event.type == 'WHEELUPMOUSE' else -1)
            w['p']['quantidade'] = max(1, min(self.MAXIMO, n))
            self._recado_quantidade()
            self._area.header_text_set(w['recado'])
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE' or event.type in {'LEFT_ALT', 'RIGHT_ALT'}:
            w['mouse'] = mouse
            if w['etapa'] in ('CANTO1', 'CANTO2'):
                ponto, nome = self._imantar(mouse)
                if ponto is None and w['etapa'] == 'CANTO2':
                    ponto = self._no_plano_da_frente(mouse)
                elif ponto is None:
                    ponto, nome = self._superficie(context, mouse)
                w['cursor'], w['cursor_obj'] = ponto, nome
            elif w['etapa'] == 'PROFUNDIDADE':
                self._profundidade(context, event, mouse)
                dados, _m = self._dados()
                if dados is not None:
                    w['recado'] = self._recado_profundidade(dados)
                self._area.header_text_set(w['recado'])
            elif w['etapa'] == 'TRILHO':
                w['hover_botao'] = _assistente._botao_sob(w['botoes'], mouse)
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS' and w['etapa'] == 'TRILHO':
            return self._criar(context, trilho='TELESCOPICO')
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS' or not dentro:
            return {'RUNNING_MODAL'} if dentro else {'PASS_THROUGH'}
        if w['etapa'] in ('CANTO1', 'CANTO2'):
            ponto, nome = w.get('cursor'), w.get('cursor_obj')
            if ponto is None:
                return {'RUNNING_MODAL'}
            if w['etapa'] == 'CANTO1':
                obj = bpy.data.objects.get(nome or '')
                conj = _portas._modulo_da_chapa(obj) if obj is not None else None
                if conj is None:
                    w['recado'] = 'Marque o vao dentro de um modulo'
                    self._area.header_text_set(w['recado'])
                    return {'RUNNING_MODAL'}
                w['modulo'] = conj.name
                w['pontos'] = [ponto.copy()]
                self._comecar_no_modulo(conj, ponto)
                self._ir('CANTO2')
                return {'RUNNING_MODAL'}
            w['pontos'].append(ponto.copy())
            dados, _m = self._dados()
            if dados is None:
                # nao cabe: o 2o canto se marca de novo (o recado diz o porque)
                w['pontos'] = w['pontos'][:1]
                self._area.header_text_set(w['recado'])
                return {'RUNNING_MODAL'}
            self._ir('QUANTIDADE')
            return {'RUNNING_MODAL'}
        if w['etapa'] == 'QUANTIDADE':
            dados, _m = self._dados()
            if dados is None:
                self._area.header_text_set(w['recado'])
                return {'RUNNING_MODAL'}
            return self._depois_da_quantidade(context)
        if w['etapa'] == 'PROFUNDIDADE':
            dados, _m = self._dados()
            if dados is None:
                self._area.header_text_set(w['recado'])
                return {'RUNNING_MODAL'}
            return self._depois_da_profundidade(context)
        if w['etapa'] == 'TRILHO':
            chave = _assistente._botao_sob(w['botoes'], mouse)
            if chave is not None:
                return self._criar(context, trilho=chave)
        return {'RUNNING_MODAL'}

    def _criar(self, context, **extra):
        w = self._w
        conj = bpy.data.objects.get(w['modulo'])
        p = dict(w['p'], **extra)
        pontos = list(w['pontos'])
        self._encerrar(context)
        if conj is None:
            return {'CANCELLED'}
        try:
            grupo = self._criar_grupo(context, conj, margens_do_vao(conj, *pontos), p)
        except ValueError as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        self._selecionar_grupo(context, grupo)
        context.scene.cabinet_aba = self.ABA
        return {'FINISHED'}


class OBJECT_OT_criar_gavetas(AssistenteDoVao, Operator):
    """Cria gavetas num vao: 2 cantos na diagonal, quantidade, profundidade e trilho"""
    bl_idname = 'object.cabinet_criar_gavetas'
    bl_label = 'Criar Gavetas'
    bl_options = {'REGISTER', 'UNDO'}


def esquecer():
    _terminar_ancora_nativa()
    _arraste_slider[0] = None
    _slider_hover[0] = None
    _assistente_gavetas[0] = None
