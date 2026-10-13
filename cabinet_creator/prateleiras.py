"""Prateleiras internas (pedido do usuario): um grupo de prateleiras num
vao do modulo, criado como as gavetas -- 2 cliques na diagonal do vao
(cima-esq e baixo-dir: so' 2 pontos, pedido do usuario) e scroll = quantas;
a profundidade vai ate' o fundo e a folga da frente e' o RECUO -- e
editado na aba propria: quantidade, espessura, espacamento entre elas e o
de CADA uma.

Referencial: o do grupo de gavetas (filho do modulo, origem no canto de
BAIXO a' ESQUERDA do vao, no plano da frente; X = largura, Z = altura,
Y = para DENTRO). Tudo em mm.

Espacamento IGUAL divide o vao (n + 1 vaos iguais); LIVRE guarda o vao
ABAIXO de cada prateleira e o de cima e' o que sobra. Mudar UM vao anda so'
a prateleira de cima dele (o vao seguinte cede): as outras ficam paradas.
"""

import bpy
from mathutils import Matrix, Vector
from bpy.types import Operator

# o assistente herda o das gavetas AO CARREGAR (o __init__ as carrega antes)
from . import gavetas as _gavetas

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _modulos = _portas = _hud = None

# Marcas gravadas no .blend (renomear quebra arquivos salvos)
MARCA_GRUPO = 'eh_grupo_prateleiras'
MARCA_PRATELEIRA = 'eh_prateleira'
CHAVE_MODULO = 'prateleiras_modulo'
CHAVE_PARAMETROS = 'prateleiras_parametros'
CHAVE_MARGENS = 'prateleiras_margens_mm'  # esq, dir, baixo, cima, frente (do modulo)
CHAVE_VAO = 'prateleiras_vao_mm'          # largura, altura (sem modulo)
CHAVE_INDICE = 'prateleira_indice'

PARAMETROS_PADRAO = {
    'quantidade': 1,
    'espessura_mm': 18.0,
    'profundidade_mm': 500.0,      # do plano da frente do vao ao fim dela
    'recuo_mm': 0.0,               # a frente da prateleira para dentro
    'folga_lateral_mm': 0.0,       # de cada lado (regulavel, no pino)
    'espacamento': 'IGUAL',
    'vaos_mm': [],                 # LIVRE: o vao ABAIXO de cada uma
}
OPCOES_ESPACAMENTO = (('IGUAL', 'Igual'), ('LIVRE', 'Livre'))
MAXIMO_PRATELEIRAS = 20
MENOR_LADO_MM = 50.0
TOL_MM = 0.01


# ------------------------------------------------------------ busca
def grupo_de(obj):
    """O grupo de prateleiras de `obj` (ele mesmo ou uma prateleira)."""
    while obj is not None:
        if MARCA_GRUPO in obj:
            return obj
        obj = obj.parent
    return None


def prateleiras_do_grupo(grupo):
    return sorted((o for o in grupo.children if MARCA_PRATELEIRA in o),
                  key=lambda o: int(o.get(CHAVE_INDICE, 0)))


def grupos_do_modulo(conj):
    return [o for o in conj.children if MARCA_GRUPO in o]


def modulo_do_grupo(grupo):
    modulo = bpy.data.objects.get(grupo.get(CHAVE_MODULO, ''))
    if modulo is not None and _chapas.MARCA_CONJUNTO in modulo:
        return modulo
    return None


def _como_dict(valor):
    return valor.to_dict() if hasattr(valor, 'to_dict') else dict(valor or {})


def parametros(grupo):
    p = dict(PARAMETROS_PADRAO)
    p.update(_como_dict(grupo.get(CHAVE_PARAMETROS)))
    p['vaos_mm'] = [float(v) for v in (p.get('vaos_mm') or ())]
    return p


def quantas_no_modulo(conj):
    """Prateleiras deste sistema no modulo (o orcamento conta)."""
    return sum(len(prateleiras_do_grupo(g)) for g in grupos_do_modulo(conj))


# ------------------------------------------------------------ calculo
def vaos(altura, p):
    """[n + 1] vaos em mm, de baixo para cima: o de baixo de cada
    prateleira e, por ultimo, o de cima da mais alta."""
    n = max(1, int(p['quantidade']))
    e = float(p['espessura_mm'])
    livre = altura - n * e
    if livre < -TOL_MM:
        raise ValueError("%d prateleiras de %g mm nao cabem em %d mm"
                         % (n, e, round(altura)))
    gravados = [float(v) for v in (p.get('vaos_mm') or ())]
    if p.get('espacamento') == 'LIVRE' and len(gravados) == n:
        topo = livre - sum(gravados)
        if topo < -TOL_MM:
            raise ValueError("As prateleiras passam do topo do vao em %d mm"
                             % round(-topo))
        if min(gravados) < -TOL_MM:
            raise ValueError("Vao negativo entre as prateleiras")
        return gravados + [max(0.0, topo)]
    return [max(0.0, livre) / (n + 1)] * (n + 1)


def calcular(largura, altura, p):
    """{'prateleiras': [(x0, x1, y0, y1, z0, z1)], 'vaos': [n + 1]}."""
    e = float(p['espessura_mm'])
    folga = float(p['folga_lateral_mm'])
    y0, y1 = float(p['recuo_mm']), float(p['profundidade_mm'])
    if e <= 0.0:
        raise ValueError("Espessura da prateleira tem de ser maior que zero")
    if largura - 2 * folga < MENOR_LADO_MM:
        raise ValueError("Vao estreito demais para prateleira (%d mm)" % round(largura))
    if y1 - y0 < MENOR_LADO_MM:
        raise ValueError("Prateleira rasa demais: %d mm" % round(y1 - y0))
    g = vaos(altura, p)
    caixas, z = [], 0.0
    for k in range(len(g) - 1):
        z += g[k]
        caixas.append((folga, largura - folga, y0, y1, z, z + e))
        z += e
    return {'prateleiras': caixas, 'vaos': g}


def mover_vao(altura, p, k, valor, de_baixo=False):
    """Os vaos de baixo (n) com o vao `k` em `valor`: anda SO' a
    prateleira de cima dele -- ou, `de_baixo`, a de baixo (o "Acima" da
    prateleira escolhida); o do topo so' tem a de baixo. O vizinho do
    outro lado dela cede. ValueError se ele ficaria negativo."""
    g = vaos(altura, p)
    n = len(g) - 1
    if not 0 <= k <= n or (de_baixo and k == 0):
        raise ValueError("Vao %d nao existe" % (k + 1))
    valor = max(0.0, float(valor))
    vizinho = k - 1 if de_baixo or k == n else k + 1
    g[vizinho] -= valor - g[k]
    g[k] = valor
    if g[vizinho] < -TOL_MM:
        raise ValueError("Nao cabe: faltam %d mm no vao %d"
                         % (round(-g[vizinho]), vizinho + 1))
    return g[:n]


# ------------------------------------------------------------ vao
def vao(grupo):
    """(largura, altura, matriz do grupo no modulo) do vao de HOJE: as
    margens ficam e o vao acompanha o modulo."""
    conj = modulo_do_grupo(grupo)
    if conj is None or _gavetas._limites(conj) is None:
        largura, altura = grupo.get(CHAVE_VAO) or (500.0, 300.0)
        return float(largura), float(altura), grupo.matrix_basis.copy()
    lo, hi = _gavetas._limites(conj)
    esq, dir_, baixo, cima, frente = list(grupo.get(CHAVE_MARGENS) or (0, 0, 0, 0, 0))
    origem = Vector((lo.x + esq, lo.y + frente, lo.z + baixo))
    return (hi.x - dir_ - origem.x, hi.z - cima - origem.z,
            Matrix.Translation(origem / 1000.0))


def profundidade_ate_o_fundo(conj, ponto):
    """Do plano da frente (o de `ponto`, mundo) ate' a face da frente do
    FUNDO do modulo -- sem fundo, ate' as costas. A prateleira nao entra
    no canal do fundo."""
    lo, hi = _gavetas._limites(conj)
    inversa = conj.matrix_world.inverted()
    limite = hi.y
    for chapa in _modulos._chapas_do_conjunto(conj):
        if _chapas.MARCA_FUNDO in chapa:
            ys = [(inversa @ (chapa.matrix_world @ v.co)).y * 1000.0
                  for v in chapa.data.vertices]
            if ys:
                limite = min(limite, min(ys))
    return max(MENOR_LADO_MM, limite - _portas._local_no_modulo(conj, ponto).y)


# ------------------------------------------------------------ montagem
def _material_do_modulo(conj):
    for chapa in _modulos._estruturais(_modulos._chapas_do_conjunto(conj)):
        for slot in chapa.material_slots:
            if slot.material is not None:
                return slot.material
    return None


def _vestir(obj, caixa):
    """Leva a chapa `obj` a' caixa (mm, no grupo) -- a mesma chapa: a
    selecao (duplo clique numa prateleira) sobrevive a' edicao."""
    matriz, (l, c, e) = _gavetas._matriz_da_caixa(caixa, 2)
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = matriz
    _chapas._ocupado[0] = True
    try:
        obj.chapa_largura_mm, obj.chapa_comprimento_mm = l, c
        obj.chapa_espessura_mm = e
        obj.chapa_auto = True
    finally:
        _chapas._ocupado[0] = False
    _chapas.gerar_malha_chapa(obj)


def _nova_prateleira(grupo, indice, material):
    nome = 'Prateleira %d' % (indice + 1)
    obj = bpy.data.objects.new(nome, bpy.data.meshes.new(nome))
    _gavetas._colecao(grupo).objects.link(obj)
    obj[_chapas.MARCA_CHAPA] = 1
    obj[MARCA_PRATELEIRA] = 1
    obj.parent = grupo
    if material is not None:
        _gavetas._pintar([obj], material)
    return obj


def montar(grupo):
    """Refaz as prateleiras pelos parametros e pelo vao de hoje, nas
    MESMAS chapas (sobra apaga, falta cria com o material das outras).
    Levanta ValueError (e nao mexe em nada) se nao couber."""
    p = parametros(grupo)
    largura, altura, matriz = vao(grupo)
    dados = calcular(largura, altura, p)
    grupo.matrix_parent_inverse = Matrix.Identity(4)
    conj = modulo_do_grupo(grupo)
    if conj is not None:
        grupo.matrix_basis = matriz
    grupo[CHAVE_VAO] = (largura, altura)
    atuais = prateleiras_do_grupo(grupo)
    material = (_gavetas._material_de(atuais)
                or (_material_do_modulo(conj) if conj is not None else None))
    for velha in atuais[len(dados['prateleiras']):]:
        _gavetas._remover(velha)
    for i, caixa in enumerate(dados['prateleiras']):
        obj = atuais[i] if i < len(atuais) else _nova_prateleira(grupo, i, material)
        obj[CHAVE_INDICE] = i
        _vestir(obj, caixa)
    bpy.context.view_layer.update()


def criar_prateleiras(context, conj, margens, p):
    """Grupo de prateleiras novo no modulo `conj`. Devolve o grupo."""
    p = dict(PARAMETROS_PADRAO, **p)
    grupo = bpy.data.objects.new('Prateleiras %s' % conj.name, None)
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
        for o in list(grupo.children):
            _gavetas._remover(o)
        _gavetas._remover(grupo)
        raise
    return grupo


def atualizar_do_conjunto(conj):
    """O modulo mudou de medida: as prateleiras seguem o vao (margens
    fixas). Se nao couberem mais, ficam como estavam."""
    for grupo in grupos_do_modulo(conj):
        try:
            montar(grupo)
        except ValueError as erro:
            print("[Cabinet Creator] prateleiras de %s: %s" % (conj.name, erro))


def _parametros_editados(grupo, nome, valor):
    p = parametros(grupo)
    n = int(p['quantidade'])
    _largura, altura, _m = vao(grupo)
    if nome == 'quantidade':
        valor = max(1, min(MAXIMO_PRATELEIRAS, int(valor)))
        if valor != n and p['espacamento'] == 'LIVRE':
            # o mesmo espacamento entre todas continua (se couber); os
            # vaos diferentes de cada uma nao tem como seguir: iguais
            baixo = vaos(altura, p)[:n]
            uniforme = max(baixo) - min(baixo) <= TOL_MM
            cabe = valor * (baixo[0] + float(p['espessura_mm'])) <= altura + TOL_MM
            if uniforme and cabe:
                p['vaos_mm'] = [baixo[0]] * valor
            else:
                p.update(espacamento='IGUAL', vaos_mm=[])
        p['quantidade'] = valor
    elif nome == 'espacamento':
        # LIVRE parte dos vaos de hoje: nada pula ao trocar
        p['vaos_mm'] = vaos(altura, p)[:n] if valor == 'LIVRE' else []
        p['espacamento'] = valor
    elif nome == 'entre_mm':
        p.update(espacamento='LIVRE', vaos_mm=[max(0.0, float(valor))] * n)
    elif nome.startswith('vao_'):
        p.update(espacamento='LIVRE',
                 vaos_mm=mover_vao(altura, p, int(nome[len('vao_'):]), valor))
    elif nome.startswith('acima_'):
        # o vao de cima da prateleira K, andando ELA (nao a de cima)
        p.update(espacamento='LIVRE', vaos_mm=mover_vao(
            altura, p, int(nome[len('acima_'):]) + 1, valor, de_baixo=True))
    elif nome in PARAMETROS_PADRAO:
        p[nome] = max(0.0, float(valor))
    else:
        raise ValueError("Parametro de prateleira desconhecido: %s" % nome)
    return p


def editar(context, grupo, nome, valor):
    """Muda um parametro (aba Prateleiras). Devolve o erro (e desfaz) ou None."""
    nome = nome[len('prateleiras_'):] if nome.startswith('prateleiras_') else nome
    antes = parametros(grupo)
    try:
        grupo[CHAVE_PARAMETROS] = _parametros_editados(grupo, nome, valor)
        montar(grupo)
    except ValueError as erro:
        grupo[CHAVE_PARAMETROS] = antes
        montar(grupo)
        return str(erro)
    return None


def entre(grupo):
    """O "Entre prateleiras" da aba: a media dos vaos de baixo."""
    _largura, altura, _m = vao(grupo)
    try:
        baixo = vaos(altura, parametros(grupo))[:-1]
    except ValueError:
        return 0.0
    return sum(baixo) / len(baixo)


# ------------------------------------------------------------ selecao
def selecionar(context, obj, nivel, somar=False):
    """'GRUPO' = todas as prateleiras do vao; 'PRATELEIRA' = so' a de `obj`."""
    grupo = grupo_de(obj)
    if grupo is None:
        return False
    if nivel == 'PRATELEIRA' and MARCA_PRATELEIRA in obj:
        alvos, ativo = [obj], obj
    else:
        alvos, ativo = [grupo, *prateleiras_do_grupo(grupo)], grupo
    if not somar:
        for o in context.selected_objects:
            o.select_set(False)
    for o in alvos:
        if o.visible_get():
            o.select_set(True)
    context.view_layer.objects.active = ativo
    if context.area:
        context.area.tag_redraw()
    return True


def selecionados(context):
    """Grupos com o grupo OU uma prateleira selecionado."""
    grupos = []
    for o in getattr(context, 'selected_objects', ()) or ():
        g = grupo_de(o)
        if g is not None and g not in grupos:
            grupos.append(g)
    return grupos


# ------------------------------------------------------------ HUD
def medidas(grupo):
    """(largura, altura, profundidade) mm que a HUD e a aba mostram."""
    largura, altura, _m = vao(grupo)
    return largura, altura, float(parametros(grupo)['profundidade_mm'])


def linhas_hud(grupo, chapas):
    """Linhas da HUD (tipo 'prateleiras'): L/P/A na caixa do vao, como
    as gavetas, e uma linha por VAO entre as prateleiras (o valor ao
    lado; arrastar ou clicar e digitar anda so' a prateleira de cima)."""
    largura, altura, prof = medidas(grupo)
    m = grupo.matrix_world
    cantos = [m @ (Vector((i * largura, j * prof, k * altura)) / 1000.0)
              for k in (0, 1) for j in (0, 1) for i in (0, 1)]
    letras = {0: 'L', 1: 'P', 2: 'A'}
    linhas = []
    for eixo, arestas in enumerate(_hud.ARESTAS_EIXO):
        for i, j in arestas:
            linhas.append({'tipo': 'prateleiras', 'objeto': grupo, 'modo': 'PRATELEIRAS',
                           'eixo': eixo, 'letra': letras[eixo],
                           'face': (letras[eixo],), 'cantos': (i, j),
                           'chapas': chapas, 'pontos': [cantos[i], cantos[j]]})
    p = parametros(grupo)
    try:
        dados = calcular(largura, altura, p)
    except ValueError:
        return cantos, linhas
    caixas = dados['prateleiras']
    x, y = largura / 2.0, float(p['recuo_mm'])
    for k in range(len(dados['vaos'])):
        z0 = caixas[k - 1][5] if k > 0 else 0.0
        z1 = caixas[k][4] if k < len(caixas) else altura
        if z1 - z0 < 1.0:
            continue
        linhas.append({'tipo': 'prateleiras', 'objeto': grupo, 'modo': 'PRATELEIRAS',
                       'letra': None, 'face': ('V', k), 'vao': True, 'chapas': chapas,
                       'pontos': [m @ (Vector((x, y, z)) / 1000.0) for z in (z0, z1)]})
    return cantos, linhas


def valor(grupo, chave):
    if chave[0] == 'V':
        _largura, altura, _m = vao(grupo)
        return vaos(altura, parametros(grupo))[chave[1]]
    largura, altura, prof = medidas(grupo)
    return {'L': largura, 'A': altura, 'P': prof}[chave[0]]


def aplicar(context, grupo, chave, novo, lado=None):
    """Medida da HUD/aba: V = um vao; L e A mudam a MARGEM do lado que
    anda (a quina perto do mouse fica); P e' a profundidade."""
    chave = tuple(chave) if isinstance(chave, (tuple, list)) else (chave,)
    letra = chave[0]
    if letra == 'V':
        return editar(context, grupo, 'vao_%d' % chave[1], novo)
    if letra == 'P':
        return editar(context, grupo, 'profundidade_mm', max(MENOR_LADO_MM, float(novo)))
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
    """O que o Esc do arraste da HUD devolve (`restaurar`)."""
    return (grupo.name, parametros(grupo), list(grupo.get(CHAVE_MARGENS) or ()))


def restaurar(estado):
    nome, p, margens = estado
    grupo = bpy.data.objects.get(nome)
    if grupo is None:
        return
    grupo[CHAVE_PARAMETROS] = p
    grupo[CHAVE_MARGENS] = margens
    try:
        montar(grupo)
    except ValueError as erro:
        print("[Cabinet Creator] prateleiras:", erro)


# ------------------------------------------------------------ assistente
_assistente_prateleiras = [None]
RECADOS = {
    'CANTO1': "Clique no canto de CIMA a' ESQUERDA do vao (Esc cancela)",
    'CANTO2': "Clique no canto de BAIXO a' DIREITA do vao",
    'QUANTIDADE': 'Scroll: quantas prateleiras | clique cria',
}


def _criando():
    return _assistente_prateleiras[0] is not None


class OBJECT_OT_criar_prateleiras(_gavetas.AssistenteDoVao, Operator):
    """Cria prateleiras num vao: 2 cantos na diagonal e a quantidade"""
    bl_idname = 'object.cabinet_criar_prateleiras'
    bl_label = 'Criar Prateleiras'
    bl_options = {'REGISTER', 'UNDO'}

    _estado = _assistente_prateleiras
    RECADOS = RECADOS
    MAXIMO = MAXIMO_PRATELEIRAS
    ITEM = ('prateleira', 'prateleiras')
    ABA = 'PRATELEIRAS'
    FIM_QUANTIDADE = 'clique cria'

    def _parametros_padrao(self):
        return dict(PARAMETROS_PADRAO, vaos_mm=[])

    def _calcular(self, largura, altura, p):
        return calcular(largura, altura, p)

    def _caixas_da_previa(self, dados):
        return dados['prateleiras']

    def _comecar_no_modulo(self, conj, ponto):
        p = self._w['p']
        p['espessura_mm'] = float(_portas._espessura_do_vao(conj))
        # SO' 2 pontos (pedido do usuario): sem etapa de profundidade, ela
        # vai ate' o fundo; a folga da frente e' o Recuo da aba
        p['profundidade_mm'] = profundidade_ate_o_fundo(conj, ponto)

    def _depois_da_quantidade(self, context):
        return self._criar(context)

    def _criar_grupo(self, context, conj, margens, p):
        return criar_prateleiras(context, conj, margens, p)

    def _selecionar_grupo(self, context, grupo):
        selecionar(context, grupo, 'GRUPO')


def esquecer():
    _assistente_prateleiras[0] = None
