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
_geometria = _prateleiras = _divisorias = None

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
CHAVE_REFERENCIA = 'gavetas_referencia'
CHAVE_ENCAIXE = 'gavetas_encaixe'

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
    'coberturas_mm': [],             # esq, dir, baixo, cima medidos na fonte
    'individuais': {},              # indice -> escolhas so' desta gaveta
    'folgas_mm': [],                # separacoes, de baixo para cima
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
    cabem = [c for c in TRILHOS[tipo]['comprimentos'] if c <= disponivel + 1e-3]
    return max(cabem) if cabem else None


def parametros_da_unidade(p, indice):
    return dict(p, **p.get('individuais', {}).get(str(indice), {}))


def folgas(p):
    n = max(1, int(p['quantidade']))
    valores = p.get('folgas_mm') or ()
    return (list(map(float, valores)) if len(valores) == n-1
            else [float(p['entre_gavetas_mm'])] * (n-1))


def coberturas(p):
    valores = p.get('coberturas_mm') or ()
    if len(valores) == 4:
        return list(map(float,valores))
    c = (max(0.0,float(p['lateral_mm'])-float(p['folga_frontal_mm']))
         if p['cobertura']=='SOBREPOSTA' else -float(p['folga_frontal_mm']))
    return [c]*4


def frentes(largura, altura, p):
    """[(x0, x1, z0, z1)] das frentes, de BAIXO para cima."""
    n = max(1, int(p['quantidade']))
    esq,direita,baixo,cima = coberturas(p)
    z0,z1 = -baixo,altura+cima
    separacoes = folgas(p)
    if any(v < 0 for v in separacoes):
        raise ValueError('Espacamento entre gavetas nao pode ser negativo')
    util = z1 - z0 - sum(separacoes)
    pesos = [float(v) for v in (p.get('proporcoes') or ())]
    if len(pesos) != n or min(pesos, default=0.0) <= 0.0:
        pesos = [1.0] * n
    alturas = [util * v / sum(pesos) for v in pesos]
    if min(alturas) < ALTURA_MIN_FRENTE_MM:
        raise ValueError("Gavetas demais para a altura: frente de %d mm"
                         % round(min(alturas)))
    saida, z = [], z0
    for i,a in enumerate(alturas):
        q = parametros_da_unidade(p,i)
        esq,dir_,_baixo,_cima = coberturas(q)
        inicio = float(q.get('x_mm',-esq))
        fim = inicio+float(q['largura_mm']) if 'largura_mm' in q else largura+dir_
        saida.append((inicio, fim, z, z + a))
        z += a + (separacoes[i] if i < n-1 else 0)
    return saida


def calcular(largura, altura, p):
    """Tudo de cada gaveta em caixas (x0, x1, y0, y1, z0, z1) mm:
    {'trilho_mm', 'gavetas': [{'frente', 'caixa': [(peca, nome, caixa,
    eixo)], 'fixos': [caixa], 'moveis': [caixa]}]}."""
    if largura < LARGURA_MIN_VAO_MM-1e-3 or altura < ALTURA_MIN_FRENTE_MM-1e-3:
        raise ValueError("Vao pequeno demais para gaveta (%d x %d mm)"
                         % (round(largura), round(altura)))
    unidades = [_calcular_unidade(largura,altura,parametros_da_unidade(p,i),f)
                for i,f in enumerate(frentes(largura,altura,p))]
    return {'trilho_mm':unidades[0]['trilho_mm'], 'gavetas':unidades}


def _calcular_unidade(largura, altura, p, frente):
    trilho = TRILHOS[p['trilho']]
    e = float(p['espessura_frente_mm'])
    if e <= 0:raise ValueError('A espessura da frente deve ser maior que zero')
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
    x0,x1,z0,z1 = frente
    esq,dir_,_baixo,_cima = coberturas(p)
    origem_x, fim_x = x0+esq, x1-dir_
    if origem_x < -1e-3 or fim_x > largura+1e-3:
        raise ValueError('A largura individual ultrapassa o vao do conjunto')
    largura = fim_x-origem_x
    if largura < LARGURA_MIN_VAO_MM-1e-3:
        raise ValueError('A gaveta nao deixa largura para a caixa')
    folga_lado = trilho['folga_lado']
    bx0, bx1 = folga_lado, largura - folga_lado
    if bx1 - bx0 < LARGURA_MIN_VAO_MM - 2 * folga_lado:
        raise ValueError("O vao nao deixa largura para a caixa")
    by0, by1 = inicio, inicio + comprimento
    ec, ef = ESPESSURA_CAIXA_MM, FUNDO_CAIXA_MM
    s0, s1 = max(0.0, z0), min(altura, z1)
    cz0, cz1 = s0 + trilho['caixa_baixo'], s1 - FOLGA_TOPO_CAIXA_MM
    # DXF/matrizes usam float32: 40 mm pode voltar como 39,99994.
    if cz1 - cz0 < ALTURA_MIN_CAIXA_MM - 1e-3:
        raise ValueError("A frente nao deixa altura para a caixa")
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
    dados = {'frente': (x0, x1, fy0, fy1, z0, z1), 'caixa': caixa,
                  'fixos': fixos, 'moveis': moveis}
    dados['caixa'] = [(peca,nome,(a+origem_x,b+origem_x,c,d,e,f),eixo)
                      for peca,nome,(a,b,c,d,e,f),eixo in dados['caixa']]
    for tipo in ('fixos','moveis'):
        dados[tipo] = [(a+origem_x,b+origem_x,c,d,e,f) for a,b,c,d,e,f in dados[tipo]]
    dados['trilho_mm'] = comprimento
    return dados


# ------------------------------------------------------------ vao
def _limites(conj):
    return _portas._limites_locais_modulo(conj)


def referencia(grupo):
    valores = grupo.get(CHAVE_REFERENCIA)
    return Matrix([valores[i:i + 3] for i in (0, 3, 6)]) if valores else Matrix.Identity(3)


def limites_na_referencia(conj, ref, limites=None):
    if limites is None and all((ref.col[k]-Matrix.Identity(3).col[k]).length<1e-6 for k in range(3)):
        # Pecas modeladas inclinadas podem ter cantos imaginarios na
        # bound_box. Na referencia original conservar os limites reais.
        return _limites(conj)
    if limites is None:
        inv=ref.transposed().to_4x4() @ conj.matrix_world.inverted()
        pts=[inv @ (o.matrix_world @ Vector(v))*1000 for o in _modulos._chapas_do_conjunto(conj)
             if not o.get('eh_prateleira') for v in o.bound_box]
        return (Vector(tuple(min(v[k] for v in pts) for k in range(3))),
                Vector(tuple(max(v[k] for v in pts) for k in range(3))))
    lo, hi = limites if limites is not None else _limites(conj)
    pontos = [ref.transposed() @ Vector((x, y, z))
              for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    return (Vector(tuple(min(v[k] for v in pontos) for k in range(3))),
            Vector(tuple(max(v[k] for v in pontos) for k in range(3))))


def referencia_do_vao(conj, ponto_a, ponto_b, limites=None):
    """Diagonal define a frente, em qualquer face. Recuos ate' 50 mm
    entre referencias nao inclinam um vao ortogonal (prateleira/base)."""
    a=_portas._local_no_modulo(conj,ponto_a)
    b=_portas._local_no_modulo(conj,ponto_b)
    d=b-a;d.z=0
    if d.length<1:return Matrix.Identity(3)
    if min(abs(d.x),abs(d.y))<=50:
        d=Vector((1,0,0)) if abs(d.x)>=abs(d.y) else Vector((0,1,0))
    direita=d.normalized();cima=Vector((0,0,1))
    dentro=cima.cross(direita)
    lo,hi=limites if limites is not None else _limites(conj)
    if dentro.dot((lo+hi-a-b)/2)<0:
        direita=-direita;dentro=-dentro
    return Matrix((direita,dentro,cima)).transposed()


def pontos_internos_do_vao(conj, pontos, nomes, ref, limites=None):
    """Referencia sobre a chapa: o vao fica ABAIXO da de cima e ACIMA
    da de baixo. Laterais usam a face interna, sem atravessar a madeira."""
    mundo=conj.matrix_world @ ref.to_4x4();inv=mundo.inverted()
    saida=[inv @ Vector(p)*1000 for p in pontos]
    for i,nome in enumerate(nomes):
        obj=bpy.data.objects.get(nome or '')
        if obj is None or _chapas.MARCA_CHAPA not in obj:continue
        n=(inv.to_3x3() @ obj.matrix_world.to_3x3().col[2]).normalized()
        vs=[inv @ (obj.matrix_world @ Vector(v))*1000 for v in obj.bound_box]
        if abs(n.z)>.995:
            saida[i].z=(min if i==0 else max)(v.z for v in vs)
        elif abs(n.x)>.995:
            saida[i].x=(max if i==0 else min)(v.x for v in vs)
    lo,hi=limites_na_referencia(conj,ref,limites)
    e=float(_portas._espessura_do_vao(conj))
    for v in saida:
        v.x=max(lo.x+e,min(hi.x-e,v.x))
        v.z=max(lo.z+e,min(hi.z-e,v.z))
    return [mundo @ (v/1000) for v in saida]


def profundidade_disponivel(conj, matriz, largura, altura, limite):
    """Menor espaco livre ate' as costas, amostrado no vao. Ray cast
    nativo, so' ao confirmar pontos; nao varrer vertices no arraste."""
    direcao=matriz.to_3x3().col[1].normalized()
    pecas=[o for o in _modulos._chapas_do_conjunto(conj)
           if not o.get('eh_prateleira')]
    distancias=[max(0,float(limite))]
    for x in (.25,largura/2,largura-.25):
        for z in (.25,altura/2,altura-.25):
            inicio=matriz @ (Vector((x,.1,z))/1000)
            for obj in pecas:
                inv=obj.matrix_world.inverted();d=inv.to_3x3()@direcao
                hit,ponto,normal,_f=obj.ray_cast(inv@inicio,d.normalized(),distance=max(0,limite)/1000*d.length)
                if not hit:continue
                n=(inv.to_3x3().transposed()@normal).normalized()
                if n.dot(direcao)>-.1:continue
                distancia=(obj.matrix_world@ponto-matriz.translation).dot(direcao)*1000
                if distancia>.15:distancias.append(distancia)
    return min(distancias)


def margens_do_vao(conj, ponto_a, ponto_b, referencial=None, limites=None, limites_referencia=None):
    """(esq, dir, baixo, cima, frente) mm do vao marcado na diagonal
    (pontos de mundo), medidos da caixa do modulo."""
    ref=referencial if referencial is not None else Matrix.Identity(3)
    if limites_referencia is not None:
        lo,hi=limites_referencia
    elif limites is None:
        lo,hi=limites_na_referencia(conj,ref)
    else:
        pontos=[ref.transposed()@Vector((x,y,z)) for x in (limites[0].x,limites[1].x)
                for y in (limites[0].y,limites[1].y) for z in (limites[0].z,limites[1].z)]
        lo=Vector(tuple(min(v[k] for v in pontos) for k in range(3)))
        hi=Vector(tuple(max(v[k] for v in pontos) for k in range(3)))
    a = ref.transposed()@_portas._local_no_modulo(conj, ponto_a)
    b = ref.transposed()@_portas._local_no_modulo(conj, ponto_b)
    return (min(a.x, b.x) - lo.x, hi.x - max(a.x, b.x),
            min(a.z, b.z) - lo.z, hi.z - max(a.z, b.z),
            max(0.0, max(a.y, b.y) - lo.y))


def vao(grupo):
    """(largura, altura, matriz do grupo no modulo) pelas margens atuais.
    Redimensionar o modulo move o bloco e recalcula estas margens."""
    conj = modulo_do_grupo(grupo)
    margens = list(grupo.get(CHAVE_MARGENS) or (0, 0, 0, 0, 0))
    if conj is None or _limites(conj) is None:
        largura, altura = grupo.get(CHAVE_VAO) or (500.0, 200.0)
        return float(largura), float(altura), grupo.matrix_basis.copy()
    ref = referencia(grupo)
    lo, hi = limites_na_referencia(conj, ref)
    esq, dir_, baixo, cima, frente = margens
    origem = Vector((lo.x + esq, lo.y + frente, lo.z + baixo))
    largura = hi.x - dir_ - origem.x
    altura = hi.z - cima - origem.z
    matriz = ref.to_4x4() @ Matrix.Translation(origem / 1000.0)
    return _divisorias.limitar_vao(grupo, largura, altura, matriz)


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
    materiais_individuais = {}
    for i, gaveta in antigas.items():
        contagem={}
        for obj in gaveta.children:
            tipo=obj.get(MARCA_PECA)
            if tipo and tipo!='TRILHO':
                ordinal=contagem.get(tipo,0)
                contagem[tipo]=ordinal+1
                materiais_individuais[i,tipo,ordinal]=[(s.link,s.material) for s in obj.material_slots]
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
        individual = parametros_da_unidade(p,i)
        gaveta = bpy.data.objects.new('Gaveta %d' % (i + 1), None)
        _colecao(grupo).objects.link(gaveta)
        gaveta.empty_display_size = 0.02
        gaveta.hide_render = True
        gaveta[MARCA_GAVETA] = 1
        gaveta[CHAVE_INDICE] = i
        gaveta[CHAVE_TRILHO_MM] = float(d['trilho_mm'])
        gaveta.parent = grupo
        gaveta.matrix_parent_inverse = Matrix.Identity(4)
        # frente CURVA (pedido do usuario, do gaveteiro de canto do
        # Promob): arco de flecha `frente_curva_mm` para FORA, as pontas
        # no plano da frente reta (`_chapas._malha_arco`)
        curva = float(individual.get('frente_curva_mm') or 0.0)
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
        modelo=p.get('individuais',{}).get(str(i),{}).get('puxador',puxadores.get(i,p['puxador']))
        pux = colocar_puxador(gaveta, modelo)
        ajustes = ajustes_puxadores.get(i,{}) if modelo==puxadores.get(i,p['puxador']) else {}
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
    for i,gaveta in enumerate(gavetas_do_grupo(grupo)):
        contagem={}
        for obj in gaveta.children:
            tipo=obj.get(MARCA_PECA)
            ordinal=contagem.get(tipo,0)
            contagem[tipo]=ordinal+1
            slots=materiais_individuais.get((i,tipo,ordinal))
            if slots is not None:
                obj.data.materials.clear()
                for link,mat in slots:
                    obj.data.materials.append(mat)
                    obj.material_slots[-1].link=link
                    obj.material_slots[-1].material=mat
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


def criar_gavetas(context, conj, margens, p, referencial=None):
    """Grupo de gavetas novo no modulo `conj`. Devolve o grupo."""
    p = dict(PARAMETROS_PADRAO, **p)
    nome = 'Gavetas %s' % conj.name
    grupo = bpy.data.objects.new(nome, None)
    # Presets antigos podem ter a montagem sem MARCA_COLECAO_MODULO.
    # O sistema precisa ficar no asset, nao solto na raiz da cena.
    colecao = (_modulos._colecao_do_modulo(conj)
               or next(iter(conj.users_collection), context.scene.collection))
    colecao.objects.link(grupo)
    grupo.empty_display_type = 'PLAIN_AXES'
    grupo.empty_display_size = 0.05
    grupo.hide_render = True
    grupo[MARCA_GRUPO] = 1
    grupo[CHAVE_MODULO] = conj.name
    grupo[CHAVE_PARAMETROS] = p
    grupo[CHAVE_MARGENS] = [float(m) for m in margens]
    if referencial is not None:
        grupo[CHAVE_REFERENCIA] = [v for linha in referencial for v in linha]
    grupo.parent = conj
    try:
        montar(grupo)
        _divisorias.particionar_grupo(grupo)
    except ValueError:
        for o in list(reversed(grupo.children_recursive)):
            _remover(o)
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
        eixos = grupo.matrix_world.to_3x3().normalized()
        mudanca = [sum(abs(eixos.col[k][a]) * ((hi[a]-lo[a])-(hi_antes[a]-lo_antes[a]))
                       * 1000 for a in range(3)) for k in range(3)]
        _adaptar_espaco(grupo, mudanca)


def _minimos(grupo):
    p = parametros(grupo)
    unidades = [parametros_da_unidade(p, i) for i in range(int(p['quantidade']))]
    profundidade = max(TRILHOS[q['trilho']]['comprimentos'][0]
                      + float(q['recuo_mm']) + FOLGA_FUNDO_MODULO_MM
                      + (float(q['espessura_frente_mm']) if q['cobertura']=='EMBUTIDA' else 0)
                      for q in unidades)
    # Limite analitico da mesma caixa usada em calcular: uma falha de
    # largura/profundidade nao deve ser confundida com falta de altura.
    n=len(unidades)
    pesos=list(p.get('proporcoes') or [])
    if len(pesos)!=n or min(pesos,default=0)<=0:pesos=[1.]*n
    _e,_d,baixo,cima=coberturas(p)
    util=0.
    for i,q in enumerate(unidades):
        corte=(max(0.,baixo) if i==0 else 0.)+(max(0.,cima) if i==n-1 else 0.)
        minimo=max(ALTURA_MIN_FRENTE_MM,ALTURA_MIN_CAIXA_MM+TRILHOS[q['trilho']]['caixa_baixo']+FOLGA_TOPO_CAIXA_MM+corte)
        util=max(util,minimo*sum(pesos)/pesos[i])
    altura=util+sum(folgas(p))-baixo-cima
    atual_l,atual_a=map(float,grupo[CHAVE_VAO])
    try:calcular(atual_l,atual_a,p)
    except ValueError:altura=min(altura,atual_a)
    else:
        # Coberturas importadas podem colocar varias frentes fora dos
        # limites Z do vao. Validar a caixa completa nesses casos.
        lo,hi=0.,atual_a
        for _ in range(18):
            meio=(lo+hi)/2
            try:calcular(atual_l,meio,p)
            except ValueError:lo=meio
            else:hi=meio
        altura=hi
    return LARGURA_MIN_VAO_MM+.01, profundidade+.01, altura+.01


def limitar_medidas(conj, lo, hi, alvo):
    """Nao achatar um trilho de catalogo ou cruzar duas chapas.
    O modulo pode encolher as gavetas ate' o menor sistema que cabe.
    """
    saida=list(alvo)
    for grupo in grupos_do_modulo(conj):
        largura, altura=grupo[CHAVE_VAO]
        dimensoes=(largura, float(parametros(grupo)['profundidade_mm']), altura)
        minimos=_minimos(grupo)
        eixos=grupo.matrix_world.to_3x3().normalized()
        for k in range(3):
            a=max(range(3),key=lambda a:abs(eixos.col[k][a]))
            if abs(eixos.col[k][a]) < .999: continue
            minimo=(hi[a]-lo[a])*1000-dimensoes[k]+minimos[k]
            indice=(0,2,1)[a]
            saida[indice]=max(saida[indice], minimo)
    for grupo in _prateleiras.grupos_do_modulo(conj):
        p=_prateleiras.parametros(grupo)
        l,a,_m=_prateleiras.vao(grupo)
        dims=(l,float(p['profundidade_mm']),a)
        minimos=(_prateleiras.MENOR_LADO_MM+2*float(p['folga_lateral_mm']),
                 _prateleiras.MENOR_LADO_MM+float(p['recuo_mm']),
                 int(p['quantidade'])*float(p['espessura_mm'])+.01)
        eixos=grupo.matrix_world.to_3x3().normalized()
        for k in range(3):
            a=max(range(3),key=lambda a:abs(eixos.col[k][a]))
            if abs(eixos.col[k][a])<.999:continue
            indice=(0,2,1)[a]
            saida[indice]=max(saida[indice],(hi[a]-lo[a])*1000-dims[k]+minimos[k])
    # Preset antigo com parametros internos inconsistentes nao pode
    # CRESCER quando a pessoa pediu para diminuir.
    atual=[(hi[k]-lo[k])*1000 for k in (0,2,1)]
    return [min(atual[i],saida[i]) if alvo[i]<atual[i] else saida[i]
            for i in range(3)]


def _reencaixar_existentes(grupo, largura, altura, p):
    """Atualiza pecas existentes. Identidades, materiais e selecao ficam;
    o Blender transforma as malhas dos trilhos em uma unica operacao.
    """
    dados=calcular(largura, altura, p)
    def trilhos(objs, caixas):
        objs=sorted((o for o in objs if o.get(MARCA_PECA)=='TRILHO'),
                    key=lambda o:o.matrix_basis.translation.x)
        for o, caixa in zip(objs, caixas):
            m, medidas=_matriz_da_caixa(caixa, 2)
            extensao=[max(v.co[k] for v in o.data.vertices)-min(v.co[k] for v in o.data.vertices) for k in range(3)]
            o.data.transform(Matrix.Diagonal(Vector(tuple(medidas[k]/1000/extensao[k] for k in range(3)))).to_4x4())
            o.matrix_basis=m
    for indice,(gaveta, d) in enumerate(zip(gavetas_do_grupo(grupo), dados['gavetas'])):
        pecas={'FRENTE':[frente_da_gaveta(gaveta)]}
        for o in gaveta.children:
            tipo=o.get(MARCA_PECA)
            if tipo and tipo not in ('FRENTE','TRILHO'):pecas.setdefault(tipo,[]).append(o)
        for lista in pecas.values():lista.sort(key=lambda o:o.matrix_basis.translation.x)
        for tipo, nome, caixa, eixo in [('FRENTE','Frente',d['frente'],1),*d['caixa']]:
            o=pecas[tipo].pop(0)
            if tipo=='FRENTE':
                curva=float(parametros_da_unidade(p,indice).get('frente_curva_mm') or 0)
                if curva>0:o['chapa_arco_mm']=curva
                elif 'chapa_arco_mm' in o:
                    del o['chapa_arco_mm']
                    o.data.clear_geometry()   # frente parametrica que voltou a ser reta
            m, medidas=_matriz_da_caixa(caixa,eixo)
            o.matrix_basis=m
            ocupado=_chapas._ocupado[0]
            _chapas._ocupado[0]=True
            try:o.chapa_largura_mm,o.chapa_comprimento_mm,o.chapa_espessura_mm=medidas
            finally:_chapas._ocupado[0]=ocupado
            _chapas.gerar_malha_chapa(o)
        trilhos(gaveta.children,d['moveis'])
        gaveta[CHAVE_TRILHO_MM]=float(d['trilho_mm'])
        definir_abertura(gaveta,float(gaveta.get(CHAVE_ABERTURA,0)))
    # Fixos ordenados primeiro pela altura, depois pelo lado.
    fixos=sorted((o for o in grupo.children if o.get(MARCA_PECA)=='TRILHO'),
                 key=lambda o:(round(o.matrix_basis.translation.z,5),o.matrix_basis.translation.x))
    for i,d in enumerate(dados['gavetas']):trilhos(fixos[2*i:2*i+2],d['fixos'])
    grupo[CHAVE_VAO]=(largura,altura)
    grupo[CHAVE_PARAMETROS]=p
    grupo[CHAVE_TRILHO_MM]=float(dados['trilho_mm'])


def _adaptar_espaco(grupo, mudanca, curvas=None, seguir_largura=False):
    """Preserva o tamanho escolhido ate' faltar espaco; ao devolver o
    armario, devolve tambem a escolha original (incluindo profundidades).
    """
    largura,altura=map(float,grupo[CHAVE_VAO]);p=parametros(grupo)
    atual=[largura,float(p['profundidade_mm']),altura]
    estado=grupo.get(CHAVE_ENCAIXE)
    assinatura=repr((atual,p))
    if not estado or estado['ultimo'] != assinatura:
        grupo[CHAVE_ENCAIXE]=dict(desejado=atual,parametros=p,ultimo=assinatura)
        estado=grupo[CHAVE_ENCAIXE]
    desejado=list(estado['desejado'])
    novo=[min(desejado[k],atual[k]+mudanca[k]) for k in range(3)]
    if seguir_largura:novo[0]=atual[0]+mudanca[0]
    mudou_curva=bool(curvas and any(abs(float(parametros_da_unidade(p,i).get('frente_curva_mm') or 0)-v)>.01
                                   for i,v in curvas.items()))
    if max(abs(a-b) for a,b in zip(novo,atual)) < .01 and not mudou_curva:return
    parametros_novos=estado['parametros'].to_dict()
    parametros_novos['profundidade_mm']=novo[1]
    for q in parametros_novos.get('individuais',{}).values():
        if 'profundidade_mm' in q:q['profundidade_mm']=min(float(q['profundidade_mm']),novo[1])
        if 'largura_mm' in q:
            proporcao=novo[0]/desejado[0]
            q['largura_mm']*=proporcao
            if 'x_mm' in q:q['x_mm']*=proporcao
    for i,v in (curvas or {}).items():
        parametros_novos.setdefault('individuais',{}).setdefault(str(i),{})['frente_curva_mm']=v
    _reencaixar_existentes(grupo,novo[0],novo[2],parametros_novos)
    grupo[CHAVE_ENCAIXE]['ultimo']=repr(([float(v) for v in novo],parametros(grupo)))


def acompanhar_forma(conj, desloc):
    """Plano da frente acompanha o braco; profundidade so' muda em Y
    da propria gaveta. Nunca aplicar a deformacao vertice a vertice nela.
    """
    mundo=conj.matrix_world;inv=mundo.inverted()
    planos=[]
    for g in grupos_do_modulo(conj):
        l,a=map(float,g[CHAVE_VAO]);p=float(parametros(g)['profundidade_mm'])
        m=inv @ g.matrix_world;eixos=m.to_3x3().normalized()
        frente=[m @ (Vector((x,0,0))/1000)*1000 for x in (0,l)]
        fundo=[v+eixos.col[1]*p for v in frente]
        planos.append((g,l,p,eixos,frente,fundo,_minimos(g)))
    def transportar(plano,fator):
        g,l,p,eixos,frente,fundo,_min=plano
        fs=[v+desloc(v)*fator for v in frente]
        direcao=fs[1]-fs[0];direcao.z=0
        largura=direcao.length
        x=direcao.normalized() if largura>1e-6 else eixos.col[0]
        y=eixos.col[2].cross(x).normalized()
        bs=[v+desloc(v)*fator for v in fundo]
        profundidade=min((b-f).dot(y) for f,b in zip(fs,bs))
        return fs,x,y,largura,profundidade
    fator=1.
    if any(transportar(pl,1)[3]<min(pl[1],pl[-1][0])-.001
           or transportar(pl,1)[4]<min(pl[2],pl[-1][1])-.001 for pl in planos):
        baixo,cima=0.,1.
        for _ in range(20):
            meio=(baixo+cima)/2
            cabe=all((lambda d: d[3]>=min(pl[1],pl[-1][0]) and d[4]>=min(pl[2],pl[-1][1]))(transportar(pl,meio))
                     for pl in planos)
            if cabe:baixo=meio
            else:cima=meio
        fator=baixo
    for pl in planos:
        g,l,p,eixos,frente,_fundo,_min=pl
        fs,x,y,largura,profundidade=transportar(pl,fator)
        ref=Matrix((x,y,eixos.col[2])).transposed()
        local=ref.to_4x4();local.translation=fs[0]/1000
        g.matrix_world=mundo @ local
        g[CHAVE_REFERENCIA]=[v for linha in ref for v in linha]
        curvas={}
        params=parametros(g)
        for i in range(int(params['quantidade'])):
            flecha=float(parametros_da_unidade(params,i).get('frente_curva_mm') or 0)
            if flecha<=0:continue
            centro=(frente[0]+frente[1])/2-eixos.col[1]*flecha
            centro+=desloc(centro)*fator
            curvas[i]=max(0.,-(centro-(fs[0]+fs[1])/2).dot(y))
        _adaptar_espaco(g,[largura-l,profundidade-p,0],curvas,seguir_largura=True)
    return fator


def atualizar_gavetas_do_conjunto(conj):
    """Redimensionar a caixa nao redimensiona as gavetas internas.
    Recalcula as margens para a edicao direta partir das mesmas medidas."""
    for grupo in grupos_do_modulo(conj):
        ref = referencia(grupo)
        lo, hi = limites_na_referencia(conj, ref)
        largura, altura = grupo[CHAVE_VAO]
        # A origem do modulo compensa os filhos pela matrix_parent_inverse.
        origem = ref.transposed() @ ((conj.matrix_world.inverted() @ grupo.matrix_world).translation * 1000.0)
        grupo[CHAVE_MARGENS] = (origem.x - lo.x, hi.x - origem.x - largura,
                                origem.z - lo.z, hi.z - origem.z - altura,
                                origem.y - lo.y)


def editar_individual(context,grupo,indice,nome,valor,lado=None,previa=False):
    """Altura cede/recebe da vizinha; bordas do conjunto nao andam.
    Previa muda so' parametros/contorno, sem destruir malhas no mousemove.
    """
    antes = parametros(grupo)
    novo = grupo[CHAVE_PARAMETROS].to_dict()
    largura,altura,_m = vao(grupo)
    n = int(antes['quantidade'])
    if not 0 <= indice < n:
        return 'Gaveta nao encontrada'
    fs = frentes(largura,altura,antes)
    alturas = [f[3]-f[2] for f in fs]
    if nome=='altura' and n==1:
        margens=list(grupo[CHAVE_MARGENS])
        k=2 if lado=='max' else 3
        delta=float(valor)-alturas[0]
        if margens[k]-delta < -1e-3:return 'A gaveta ultrapassa o vao do modulo'
        margens[k]-=delta
        try:calcular(largura,altura+delta,antes)
        except ValueError as erro:return str(erro)
        grupo[CHAVE_MARGENS]=margens
        if not previa:montar(grupo)
        return None
    if nome == 'altura':
        vizinha = indice-1 if lado=='max' else indice+1
        if lado is None and vizinha >= n:vizinha=indice-1
        if not 0 <= vizinha < n:
            return 'Borda externa fixa: edite pelo lado da gaveta vizinha'
        delta = float(valor)-alturas[indice]
        alturas[indice] += delta
        alturas[vizinha] -= delta
        novo['proporcoes'] = alturas
    elif nome in ('abaixo_mm','acima_mm'):
        k = indice-1 if nome=='abaixo_mm' else indice
        if not 0 <= k < n-1:return 'Esta borda pertence ao conjunto'
        separacoes = folgas(antes)
        delta = float(valor)-separacoes[k]
        alturas[k if nome=='abaixo_mm' else k+1] -= delta
        separacoes[k] = float(valor)
        novo.update(folgas_mm=separacoes,proporcoes=alturas)
    else:
        q = novo.setdefault('individuais',{}).setdefault(str(indice),{})
        if nome == 'largura':
            q['x_mm'] = fs[indice][1]-float(valor) if lado=='max' else fs[indice][0]
            q['largura_mm'] = float(valor)
        elif nome in PARAMETROS_PADRAO and nome not in ('quantidade','proporcoes','individuais','folgas_mm','entre_gavetas_mm'):
            q[nome] = valor
            if nome in ('cobertura','folga_frontal_mm'):q['coberturas_mm']=[]
            if nome=='profundidade_mm' and lado=='max':
                anterior=parametros_da_unidade(antes,indice)
                q['recuo_mm']=float(anterior['recuo_mm'])-(float(valor)-float(anterior[nome]))
        else:return 'Parametro individual desconhecido'
    if nome in ('altura','abaixo_mm','acima_mm') and min(alturas) < ALTURA_MIN_FRENTE_MM:
        return 'Nao cabe: a gaveta vizinha ficaria pequena demais'
    try:calcular(largura,altura,dict(PARAMETROS_PADRAO,**novo))
    except ValueError as erro:return str(erro)
    grupo[CHAVE_PARAMETROS] = novo
    if not previa:montar(grupo)
    return None


def normalizar_alturas(grupo):
    """Iguala as frentes no mesmo vao, conservando folgas e escolhas.
    Validar ANTES: as gavetas das pontas podem ficar sem altura de caixa.
    """
    novo = grupo[CHAVE_PARAMETROS].to_dict()
    novo['proporcoes'] = []
    largura, altura, _matriz = vao(grupo)
    try:
        calcular(largura, altura, dict(PARAMETROS_PADRAO, **novo))
    except ValueError as erro:
        return str(erro)
    grupo[CHAVE_PARAMETROS] = novo
    montar(grupo)
    return None


class OBJECT_OT_normalizar_gavetas(Operator):
    bl_idname = 'object.cabinet_normalizar_gavetas'
    bl_label = 'Normalizar alturas'
    bl_description = 'Iguala as alturas de todas as gavetas deste conjunto, preservando folgas e ajustes individuais'
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        grupo = grupo_de(context.object)
        return (grupo is not None and getattr(context, 'mode', '') == 'OBJECT'
                and int(parametros(grupo)['quantidade']) > 1)

    def execute(self, context):
        erro = normalizar_alturas(grupo_de(context.object))
        if erro:
            self.report({'WARNING'}, erro)
            return {'CANCELLED'}
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


def editar(context, grupo, nome, valor):
    """Muda um parametro (aba Gavetas). Devolve o erro (e desfaz) ou None."""
    nome = nome[len('gavetas_'):] if nome.startswith('gavetas_') else nome
    if nome.startswith('individual_'):
        _prefixo,indice,prop = nome.split('_',2)
        return editar_individual(context,grupo,int(indice),prop,valor)
    antes = grupo[CHAVE_PARAMETROS].to_dict()
    novo = dict(antes)
    if nome == 'quantidade':
        valor = max(1, min(MAXIMO_GAVETAS, int(valor)))
        if valor != int(antes.get('quantidade', 1)):
            novo.pop('proporcoes', None)      # outra quantidade: iguais
            novo.pop('folgas_mm',None)
            novo.pop('individuais',None)
    novo[nome] = valor
    if nome=='entre_gavetas_mm':novo.pop('folgas_mm',None)
    for q in novo.get('individuais',{}).values():
        q.pop(nome,None)                     # no grupo, escolha vale para todas
    if nome in ('cobertura', 'folga_frontal_mm'):
        novo.pop('coberturas_mm', None)  # escolha manual substitui a referencia
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
        p=grupo[CHAVE_PARAMETROS].to_dict()
        p.setdefault('individuais',{}).setdefault(str(int(gaveta[CHAVE_INDICE])),{})['puxador']=valor
        grupo[CHAVE_PARAMETROS]=p
        return None
    return editar(context, grupo, 'puxador', valor)


# ------------------------------------------------------------ abertura
def curso(gaveta):
    grupo = grupo_de(gaveta)
    return float(gaveta.get(CHAVE_TRILHO_MM,grupo.get(CHAVE_TRILHO_MM,0))) if grupo is not None else 0.0


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
    m = matriz_hud(grupo)
    return [m @ (Vector((i * largura, j * prof, k * altura)) / 1000.0)
            for k in (0, 1) for j in (0, 1) for i in (0, 1)]


def matriz_hud(grupo):
    conj=modulo_do_grupo(grupo)
    return conj.matrix_world @ vao(grupo)[2] if conj is not None else grupo.matrix_world


def linhas_hud(grupo, chapas):
    """Linhas da HUD (tipo 'gavetas'): L nas arestas em X, P em Y, A em
    Z; a quina mais perto do mouse fica parada, como no modulo."""
    cantos = cantos_hud(grupo)
    letras = {0: 'L', 1: 'P', 2: 'A'}
    linhas = []
    todas = grupo.select_get()
    for eixo, arestas in enumerate(_hud.ARESTAS_EIXO if todas else ()):
        for i, j in arestas:
            linhas.append({'tipo': 'gavetas', 'objeto': grupo, 'modo': 'GAVETAS',
                           'eixo': eixo, 'letra': letras[eixo],
                           'face': (letras[eixo],), 'cantos': (i, j),
                           'chapas': chapas, 'pontos': [cantos[i], cantos[j]]})
    p = parametros(grupo)
    largura,altura,_m = vao(grupo)
    matriz=matriz_hud(grupo)
    try:dados=calcular(largura,altura,p)['gavetas']
    except ValueError:return cantos,linhas
    unidades={int(g[CHAVE_INDICE]):g for g in gavetas_do_grupo(grupo)}
    if not todas:cantos=[]
    for indice,d in enumerate(dados):
        g = unidades.get(indice)
        if not todas and (g is None or not g.select_get()):continue
        q=parametros_da_unidade(p,indice)
        x0,x1,y0,_y1,z0,z1=d['frente']
        aberto=float(g.get(CHAVE_ABERTURA,0)) if g is not None else 0
        deslocamento=-aberto*d['trilho_mm']
        pontos=[matriz @ (Vector((x,y+deslocamento,z))/1000)
                for z in (z0,z1) for y in (y0,y0+float(q['profundidade_mm'])) for x in (x0,x1)]
        if not todas:cantos.extend(pontos)
        for eixo,arestas in enumerate(_hud.ARESTAS_EIXO):
            for i,j in arestas:
                linhas.append(dict(tipo='gavetas',objeto=grupo,modo='GAVETAS',
                    eixo=eixo,letra=letras[eixo],face=(letras[eixo],indice),
                    cantos=(i,j),chapas=chapas,prioridade=1,pontos=[pontos[i],pontos[j]]))
                if eixo==2 and len(dados)>1 and indice in (0,len(dados)-1):
                    linhas[-1]['lado_fixo']='min' if indice==0 else 'max'
    return cantos, linhas


def valor(grupo, chave):
    if len(chave)>1:
        largura,altura,_m=vao(grupo)
        f=frentes(largura,altura,parametros(grupo))[chave[1]]
        return {'L':f[1]-f[0],'A':f[3]-f[2],
                'P':float(parametros_da_unidade(parametros(grupo),chave[1])['profundidade_mm'])}[chave[0]]
    largura, altura, prof = medidas(grupo)
    return {'L': largura, 'A': altura, 'P': prof}[chave[0]]


def aplicar(context, grupo, chave, novo, lado=None, previa=False):
    """Medida da HUD/aba: L e A mudam a MARGEM do lado que anda (a quina
    perto do mouse fica); P e' a profundidade."""
    letra = chave[0] if isinstance(chave, (tuple, list)) else chave
    if isinstance(chave,(tuple,list)) and len(chave)>1:
        nome={'L':'largura','A':'altura','P':'profundidade_mm'}[letra]
        return editar_individual(context,grupo,chave[1],nome,novo,lado,previa)
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
        largura,altura,matriz=vao(grupo)
        ref=referencia(grupo)
        lo,hi=limites_na_referencia(conj,ref)
        base=ref.transposed() @ ((conj.matrix_world.inverted() @ grupo.matrix_world).translation*1000)
        limite=profundidade_disponivel(conj,grupo.matrix_world,largura,altura,hi.y-base.y)
        return editar(bpy.context, grupo, 'profundidade_mm', min(limite,max(100.0, local.y)))
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
                # RNA do translate recebe os eixos em LINHAS. Mathutils
                # guarda-os nas colunas; sem transpor, gira ao contrario.
                orient_matrix=tuple(tuple(l) for l in grupo.matrix_world.to_3x3().transposed()),
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


_snap_criacao = [None]


def _estado_criacao():
    return (_assistente_gavetas[0] or _prateleiras._assistente_prateleiras[0]
            or _divisorias._assistente_divisorias[0]
            or (_solda._conexao_manual[0] if (_solda._conexao_manual[0] or {}).get('snap_nativo') else None))


def _terminar_snap_criacao():
    s=_snap_criacao[0]
    _snap_criacao[0]=None
    if s:
        cena=bpy.data.scenes.get(s['cena'])
        if cena is not None:cena.cursor.location=s['cursor']
        for nome,valor in s['bloqueados']:
            obj=bpy.data.objects.get(nome)
            if obj is not None:obj.hide_select=valor
        for janela in bpy.context.window_manager.windows:
            for area in janela.screen.areas:
                if area.as_pointer()==s['area']:area.spaces.active.overlay.show_cursor=s['mostrar_cursor']
    if bpy.app.timers.is_registered(_acompanhar_snap_criacao):bpy.app.timers.unregister(_acompanhar_snap_criacao)


def _acompanhar_snap_criacao():
    s=_snap_criacao[0];w=_estado_criacao()
    if not s or w is None:return None
    ativa=any(o.bl_idname=='OBJECT_OT_cabinet_marcar_ponto_vao'
              for janela in bpy.context.window_manager.windows for o in janela.modal_operators)
    if not ativa:
        w['cancelar']=True
        _terminar_snap_criacao()
        return None
    cena=bpy.data.scenes.get(s['cena'])
    if cena is not None:
        w['cursor']=cena.cursor.location.copy()
        for janela in bpy.context.window_manager.windows:
            for area in janela.screen.areas:
                if area.as_pointer()==s['area']:area.tag_redraw()
    return 1/60


def _objeto_do_ponto_criacao(context, ponto):
    area=context.area;regiao=context.region;rv3d=area.spaces.active.region_3d
    tela=view3d_utils.location_3d_to_region_2d(regiao,rv3d,ponto)
    if tela is not None:
        origem=view3d_utils.region_2d_to_origin_3d(regiao,rv3d,tela)
        direcao=view3d_utils.region_2d_to_vector_3d(regiao,rv3d,tela)
        hit,co,_n,_f,obj,_m=context.scene.ray_cast(context.evaluated_depsgraph_get(),origem,direcao)
        if hit and obj is not None and (co-ponto).length<.005:return obj.original.name
    # Quina exata pode ficar na tangente do raio. Consultar so' o modulo
    # ativo (BVH nativo), sem ler/projetar vertices de toda a cena.
    conj=_portas._modulo_da_chapa(context.object) if context.object is not None else None
    if conj is not None:
        melhor=None
        for obj in _modulos._chapas_do_conjunto(conj):
            inv=obj.matrix_world.inverted()
            hit,co,_n,_f=obj.closest_point_on_mesh(inv@ponto)
            if hit:
                d=(obj.matrix_world@co-ponto).length
                if d<.002 and (melhor is None or d<melhor[0]):melhor=(d,obj.name)
        if melhor:return melhor[1]
    return None


class OBJECT_OT_confirmar_ponto_vao(Operator):
    bl_idname='object.cabinet_confirmar_ponto_vao'
    bl_label='Confirmar Ponto do Vao'
    bl_options={'INTERNAL'}

    def execute(self,context):
        w=_estado_criacao()
        if w is None:
            _terminar_snap_criacao();return {'CANCELLED'}
        try:
            ponto=context.scene.cursor.location.copy()
            nome=_objeto_do_ponto_criacao(context,ponto) if w['etapa'] not in ('PROFUNDIDADE','SOLDA') else None
            w['ponto_confirmado']=(ponto,nome)
        except Exception:
            w['cancelar']=True
            raise
        finally:
            _terminar_snap_criacao()
        return {'FINISHED'}


class OBJECT_OT_marcar_ponto_vao(Macro):
    bl_idname='object.cabinet_marcar_ponto_vao'
    bl_label='Marcar Ponto do Vao'
    bl_options={'INTERNAL'}


def registrar_macro_criacao():
    OBJECT_OT_marcar_ponto_vao.define('TRANSFORM_OT_translate')
    OBJECT_OT_marcar_ponto_vao.define('OBJECT_OT_cabinet_confirmar_ponto_vao')


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
        return min(self._w.get('maxprof',float('inf')),max(100.0, mm))

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
        return criar_gavetas(context, conj, margens, p,self._w.get('referencia'))

    def _selecionar_grupo(self, context, grupo):
        selecionar(context, grupo, 'GRUPO')

    # ---------------------------------------------- tela e ima
    def _mouse(self, event):
        return Vector((event.mouse_x - self._regiao.x, event.mouse_y - self._regiao.y))

    def _tela(self, ponto):
        return view3d_utils.location_3d_to_region_2d(self._regiao, self._rv3d, ponto)

    def _imantar(self, mouse):
        # A criacao usa TRANSFORM_OT_translate, assim como as ancoras.
        # Nunca montar uma lista de vertices avaliados aqui.
        return self._w.get('cursor'), self._w.get('cursor_obj')

    def _iniciar_snap_nativo(self,context):
        w=self._w
        if _snap_criacao[0] is not None:return
        with context.temp_override(area=self._area,region=self._regiao):
            bloqueados=[]
            for obj in context.visible_objects:
                if (obj.name not in w['alvos_snap'] if 'alvos_snap' in w else
                    obj.type=='MESH' and _chapas.MARCA_CHAPA not in obj and 'eh_peca_curva' not in obj):
                    bloqueados.append((obj.name,obj.hide_select));obj.hide_select=True
            _snap_criacao[0]=dict(cena=context.scene.name,area=self._area.as_pointer(),
                cursor=tuple(context.scene.cursor.location),mostrar_cursor=self._area.spaces.active.overlay.show_cursor,
                bloqueados=bloqueados)
            ponto=w.get('cursor')
            if ponto is None:ponto=context.scene.cursor.location.copy()
            context.scene.cursor.location=ponto
            self._area.spaces.active.overlay.show_cursor=False
            params=dict(cursor_transform=True,snap=True,snap_elements=set(w.get('elementos_snap',('VERTEX','EDGE_MIDPOINT'))),
                        snap_target='CENTER',snap_align=False,use_snap_selectable=True)
            if w.get('soltar_confirma'):params['release_confirm']=True
            if w['etapa']=='PROFUNDIDADE':
                _d,matriz=self._dados()
                params.update(orient_type='GLOBAL',orient_matrix_type='GLOBAL',
                    orient_matrix=tuple(tuple(l) for l in matriz.to_3x3().transposed()),constraint_axis=(False,True,False))
            try:
                bpy.ops.object.cabinet_marcar_ponto_vao('INVOKE_DEFAULT',TRANSFORM_OT_translate=params)
            except Exception:
                _terminar_snap_criacao();raise
        w['snap_pendente']=True
        bpy.app.timers.register(_acompanhar_snap_criacao,first_interval=.02)

    def _raio(self, mouse):
        origem = view3d_utils.region_2d_to_origin_3d(self._regiao, self._rv3d, mouse)
        direcao = view3d_utils.region_2d_to_vector_3d(self._regiao, self._rv3d, mouse)
        return origem, direcao

    def _no_plano_da_frente(self, mouse):
        conj = bpy.data.objects.get(self._w.get('modulo', ''))
        if conj is None:
            return None
        origem, direcao = self._raio(mouse)
        ref=self._w.get('referencia',Matrix.Identity(3))
        normal = (conj.matrix_world.to_3x3()@ref.col[1]).normalized()
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
        ref=w.get('referencia')
        if ref is None:
            ref=referencia_do_vao(conj,*w['pontos'][:2],limites=w.get('limites'))
            w['referencia']=ref
        if 'limites_ref' not in w:
            w['limites_ref']=limites_na_referencia(conj,ref)
        lo,hi=w['limites_ref']
        margens = margens_do_vao(conj, *w['pontos'][:2],referencial=ref,limites_referencia=w['limites_ref'])
        largura = hi.x - margens[1] - lo.x - margens[0]
        altura = hi.z - margens[3] - lo.z - margens[2]
        origem = (lo.x + margens[0], lo.y + margens[4], lo.z + margens[2])
        try:
            dados = self._calcular(largura, altura, w['p'])
        except ValueError as erro:
            w['recado'] = str(erro)
            return None, conj.matrix_world @ ref.to_4x4() @ Matrix.Translation(Vector(origem)/1000)
        w['vao'] = (largura, altura)
        return dados, conj.matrix_world @ ref.to_4x4() @ Matrix.Translation(Vector(origem)/1000)

    def _definir_vao(self, conj):
        w=self._w
        ref=referencia_do_vao(conj,*w['pontos'],limites=w.get('limites'))
        w['pontos']=pontos_internos_do_vao(conj,w['pontos'],w.get('nomes',('', '')),ref)
        w['referencia']=ref
        lo,hi=limites_na_referencia(conj,ref)
        w['limites_ref']=(lo,hi)
        margens=margens_do_vao(conj,*w['pontos'],referencial=ref,limites_referencia=(lo,hi))
        largura=hi.x-lo.x-margens[0]-margens[1]
        altura=hi.z-lo.z-margens[2]-margens[3]
        origem=Vector((lo.x+margens[0],lo.y+margens[4],lo.z+margens[2]))
        matriz=conj.matrix_world @ ref.to_4x4() @ Matrix.Translation(origem/1000)
        w['maxprof']=profundidade_disponivel(conj,matriz,largura,altura,hi.y-origem.y)
        w['p']['profundidade_mm']=w['maxprof']
        if self.ITEM[0]=='gaveta' and margens[4]>.1:w['p']['cobertura']='EMBUTIDA'

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
                ref=referencia_do_vao(conj,*pontos,limites=w.get('limites'))
                mundo=conj.matrix_world @ ref.to_4x4()
                inv = mundo.inverted()
                a, b = inv @ pontos[0], inv @ pontos[1]
                y=max(a.y,b.y)
                cantos = [mundo @ Vector(c) for c in
                          ((a.x, y, a.z), (b.x, y, a.z), (b.x, y, b.z), (a.x, y, b.z))]
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
        if not any(o.type=='MESH' for o in context.visible_objects):
            self.report({'WARNING'}, "Nenhuma malha visivel para o ima")
            return {'CANCELLED'}
        self._w = {'etapa': 'CANTO1', 'regiao': self._regiao_ptr, 'pontos': [],
                   'cursor': None, 'modulo': '', 'p': self._parametros_padrao(),
                   'botoes': [], 'bolinhas': [], 'snap_tela': None,
                   'mouse': None, 'recado': self.RECADOS['CANTO1'], 'pergunta': ''}
        self._w['iniciar_snap']=True
        self._estado[0] = self._w
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            self._desenhar, (), 'WINDOW', 'POST_VIEW')
        self._handler_2d = bpy.types.SpaceView3D.draw_handler_add(
            _assistente._desenhar_assistente_2d, (self._w,), 'WINDOW', 'POST_PIXEL')
        context.window.cursor_modal_set('CROSSHAIR')
        context.window_manager.modal_handler_add(self)
        self._timer=context.window_manager.event_timer_add(.02,window=context.window)
        self._area.header_text_set(self._w['recado'])
        _eventos._redesenhar_viewports(context)
        return {'RUNNING_MODAL'}

    def _encerrar(self, context):
        _terminar_snap_criacao()
        timer=getattr(self,'_timer',None)
        if timer is not None:
            context.window_manager.event_timer_remove(timer);self._timer=None
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
        if etapa in ('CANTO1','CANTO2'):w['iniciar_snap']=True
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
        eixo = matriz.to_3x3().col[1].normalized()
        base = matriz.translation
        if event.alt:
            self._iniciar_snap_nativo(context)
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
        try:
            return self._modal(context,event)
        except Exception:
            self._encerrar(context)
            raise

    def _modal(self, context, event):
        w = self._w
        if w.get('cancelar'):
            self._encerrar(context);return {'CANCELLED'}
        confirmado=w.pop('ponto_confirmado',None)
        if confirmado is not None:
            w['snap_pendente']=False
            ponto,nome=confirmado
            w['cursor'],w['cursor_obj']=ponto,nome
            if w['etapa']=='PROFUNDIDADE':
                self._receber_profundidade(ponto)
                if self._dados()[0] is not None:return self._depois_da_profundidade(context)
                return {'RUNNING_MODAL'}
            return self._aceitar_canto(context,ponto,nome)
        if w.pop('iniciar_snap',False):
            self._iniciar_snap_nativo(context)
            return {'RUNNING_MODAL'}
        if w.get('snap_pendente'):return {'PASS_THROUGH'}
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
                w['iniciar_snap']=True
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
            return self._aceitar_canto(context,ponto,nome)
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

    def _receber_profundidade(self,ponto):
        _d,matriz=self._dados()
        mm=(ponto-matriz.translation).dot(matriz.to_3x3().col[1].normalized())*1000
        self._w['p']['profundidade_mm']=self._limitar_profundidade(mm)

    def _aceitar_canto(self,context,ponto,nome):
        w=self._w
        if w['etapa'] == 'CANTO1':
            obj = bpy.data.objects.get(nome or '')
            conj = _portas._modulo_da_chapa(obj) if obj is not None else None
            if conj is None:
                w['recado'] = 'Marque o vao dentro de um modulo'
                self._area.header_text_set(w['recado'])
                w['iniciar_snap']=True
                return {'RUNNING_MODAL'}
            w['modulo'] = conj.name
            w['pontos'] = [ponto.copy()]
            w['nomes']=[nome]
            w['limites']=_limites(conj)
            self._comecar_no_modulo(conj, ponto)
            self._ir('CANTO2')
            return {'RUNNING_MODAL'}
        conj=bpy.data.objects.get(w['modulo'])
        if conj is None:
            self._encerrar(context);return {'CANCELLED'}
        w['pontos'].append(ponto.copy())
        w['nomes'].append(nome)
        w.pop('referencia',None)
        self._definir_vao(conj)
        dados, _m = self._dados()
        if dados is None:
            # nao cabe: o 2o canto se marca de novo (o recado diz o porque)
            w['pontos'] = w['pontos'][:1]
            w['nomes']=w['nomes'][:1]
            w.pop('referencia',None)
            w.pop('limites_ref',None)
            self._area.header_text_set(w['recado'])
            w['iniciar_snap']=True
            return {'RUNNING_MODAL'}
        self._ir('QUANTIDADE')
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
            grupo = self._criar_grupo(context, conj, margens_do_vao(conj, *pontos,referencial=w.get('referencia'),limites_referencia=w.get('limites_ref')), p)
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
    _terminar_snap_criacao()
    _terminar_ancora_nativa()
    _arraste_slider[0] = None
    _slider_hover[0] = None
    _assistente_gavetas[0] = None
