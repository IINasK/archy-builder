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
import bmesh
import hashlib
from array import array
from mathutils import Matrix, Vector
from bpy.types import Operator

# o assistente herda o das gavetas AO CARREGAR (o __init__ as carrega antes)
from .. import gavetas as _gavetas

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _modulos = _portas = _hud = _eventos = _gaveta_eventos = _selecao = _divisorias = None

# Marcas gravadas no .blend (renomear quebra arquivos salvos)
MARCA_GRUPO = 'eh_grupo_prateleiras'
MARCA_PRATELEIRA = 'eh_prateleira'
CHAVE_MODULO = 'prateleiras_modulo'
CHAVE_PARAMETROS = 'prateleiras_parametros'
CHAVE_REFERENCIA = 'prateleiras_referencia'
CHAVE_MARGENS = 'prateleiras_margens_mm'  # esq, dir, baixo, cima, frente (do modulo)
CHAVE_VAO = 'prateleiras_vao_mm'          # largura, altura (sem modulo)
CHAVE_INDICE = 'prateleira_indice'
CHAVE_DETALHAMENTO = 'prateleira_detalhamento_uid'
CHAVE_ENCAIXE = 'prateleiras_encaixe'

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
    pai = grupo.parent
    while pai is not None:
        if _chapas.MARCA_CONJUNTO in pai:
            return pai
        pai = pai.parent
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


CAMPOS_INDIVIDUAIS = ('espessura_mm', 'profundidade_mm', 'recuo_mm',
                      'folga_lateral_mm', 'largura_mm')
_referencia_pendente = [None]
_quantidade_previa = [None]  # Valor exibido durante arraste, sem montar malhas.
_edicao = [None]  # Nomes e digitais apenas: undo libera os dados da cena.


def parametros_individuais(p, indice):
    resultado = dict(p)
    individuais = p.get('individuais') or ()
    if indice < len(individuais):
        resultado.update(individuais[indice])
    return resultado


def individual_ativo(context, grupo):
    obj = context.view_layer.objects.active
    if (obj is None or MARCA_PRATELEIRA not in obj or obj.parent != grupo
            or not obj.select_get()):
        return None
    # Um Empty selecionado explicitamente determina o escopo global.
    if any(o.type == 'EMPTY' and (o == grupo or o == modulo_do_grupo(grupo))
           for o in context.selected_objects):
        return None
    estado = edicao_atual(context)
    if estado and grupo.name in estado.get('globais', ()):
        return None
    if sum(MARCA_PRATELEIRA in o for o in context.selected_objects) != 1:
        return None
    return obj


def detalhamento(grupo, fonte):
    """Trecho local entre apoios externos; copias guardam so' um UID.

    Os limites sao recalculados dos vaos atuais, nao uma caixa gravada
    que ficaria velha ao mover apoios, desfazer ou redimensionar o modulo.
    """
    atuais = prateleiras_do_grupo(grupo)
    uid = fonte.get(CHAVE_DETALHAMENTO)
    unidades = ([o for o in atuais if o.get(CHAVE_DETALHAMENTO) == uid]
                if uid else [fonte])
    indices = [int(o[CHAVE_INDICE]) for o in unidades]
    primeiro, ultimo = min(indices), max(indices)
    if indices != list(range(primeiro, ultimo + 1)):
        raise ValueError('As subdivisoes estao separadas por outra prateleira')
    p = parametros(grupo)
    largura, altura, _m = vao(grupo)
    dados = calcular(largura, altura, p)
    caixas = dados['prateleiras']
    return dict(unidades=unidades, quantidade=len(unidades), primeiro=primeiro, ultimo=ultimo,
                baixo=caixas[primeiro - 1][5] if primeiro else 0.,
                cima=caixas[ultimo + 1][4] if ultimo + 1 < len(caixas) else altura,
                vaos=dados['vaos'][primeiro:ultimo + 2], caixas=caixas[primeiro:ultimo + 1])


def editar_quantidade_local(context, grupo, fonte, quantidade, redistribuir=False):
    """Subdivide apenas o trecho da unidade; o restante nunca e' remontado."""
    if context.mode != 'OBJECT' or _eventos._desfazendo[0]:
        return 'Conclua a edicao antes de subdividir a prateleira'
    _sincronizar_disposicao(grupo)
    antes = parametros(grupo)
    atuais = prateleiras_do_grupo(grupo)
    try:
        detalhe = detalhamento(grupo, fonte)
        antigas = detalhe['unidades']
        limite = MAXIMO_PRATELEIRAS - len(atuais) + len(antigas)
        quantidade = max(0, min(limite, int(quantidade)))
        if quantidade == len(antigas) and not redistribuir:
            return None
        # Ao reduzir, a unidade que o usuario escolheu sobrevive.
        manter = antigas[:quantidade]
        if quantidade and fonte not in manter:
            manter[-1] = fonte
            manter.sort(key=lambda o: int(o[CHAVE_INDICE]))
        modelo = parametros_individuais(antes, int(fonte[CHAVE_INDICE]))
        individuais = [dict(parametros_individuais(antes, int(o[CHAVE_INDICE]))) for o in manter]
        individuais += [dict(modelo) for _ in range(quantidade - len(manter))]
        individuais = [{k: v for k, v in p.items() if k in (*CAMPOS_INDIVIDUAIS, 'x_mm')}
                       for p in individuais]
        local = dict(antes, quantidade=quantidade, espacamento='IGUAL', vaos_mm=[],
                     individuais=individuais)
        dados = calcular(vao(grupo)[0], detalhe['cima'] - detalhe['baixo'], local)
    except ValueError as erro:
        return str(erro)
    criadas = []
    try:
        for i in range(quantidade - len(manter)):
            criadas.append(_copiar_prateleira(grupo, len(atuais) + i, fonte))
    except Exception:
        for obj in criadas:
            _gavetas._remover(obj)
        raise
    unidades = manter + criadas
    uid = fonte.get(CHAVE_DETALHAMENTO) or _chapas._garantir_uid(fonte)
    bpy.context.view_layer.update()
    for obj in criadas:
        obj.select_set(False)
    inversa = grupo.matrix_world.inverted_safe()
    for obj, caixa in zip(unidades, dados['prateleiras']):
        base = min((inversa @ obj.matrix_world @ Vector(c)).z for c in obj.bound_box) * 1000
        delta = grupo.matrix_world.to_3x3() @ Vector((0, 0, (detalhe['baixo'] + caixa[4] - base) / 1000))
        mundo = obj.matrix_world.copy()
        mundo.translation += delta
        obj.matrix_world = mundo
        obj[CHAVE_DETALHAMENTO] = uid
    inicio, fim = detalhe['primeiro'], detalhe['ultimo'] + 1
    novas = atuais[:inicio] + unidades + atuais[fim:]
    ajustes = [dict(v) for v in antes.get('individuais') or ()]
    ajustes += [{} for _ in range(len(atuais) - len(ajustes))]
    p = dict(antes, quantidade=len(novas), individuais=ajustes[:inicio] + individuais + ajustes[fim:])
    grupo[CHAVE_PARAMETROS] = p
    for i, obj in enumerate(novas):
        obj[CHAVE_INDICE] = i
    for obj in antigas:
        if obj not in unidades:
            _gavetas._remover(obj)
    bpy.context.view_layer.update()
    _sincronizar_disposicao(grupo)
    if CHAVE_ENCAIXE in grupo:
        del grupo[CHAVE_ENCAIXE]
    if quantidade == 0:
        selecionar(context, grupo, 'GRUPO')
    _hud._hover_hud.clear()
    return None


def preparar_subdivisao_vao(grupo, indice):
    _sincronizar_disposicao(grupo)
    p = parametros(grupo); atuais = prateleiras_do_grupo(grupo)
    largura, altura, _m = vao(grupo)
    caixas = calcular(largura, altura, p)['prateleiras']
    if not 0 <= indice <= len(caixas):
        raise ValueError('O vao nao existe mais')
    fonte = atuais[min(indice, len(atuais)-1)] if atuais else None
    modelo = parametros_individuais(p, int(fonte[CHAVE_INDICE])) if fonte else dict(p)
    modelo = {k:v for k,v in modelo.items() if k in (*CAMPOS_INDIVIDUAIS, 'x_mm')}
    return dict(grupo=grupo.name, baixo=caixas[indice-1][5] if indice else 0.,
        cima=caixas[indice][4] if indice < len(caixas) else altura,
        p=_portas._copiar_parametros(p), originais=[o.name for o in atuais],
        fonte=fonte.name if fonte else '', novas=[], quantidade=0,
        modelo=modelo,
        encaixe=_portas._copiar_parametros(grupo.get(CHAVE_ENCAIXE)))


def subdividir_vao(context, grupo, estado, quantidade):
    """Insere so' no vao vazio; apoios e outras prateleiras conservam a Mesh e a pose."""
    if context.mode != 'OBJECT' or _eventos._desfazendo[0]:
        raise ValueError('Conclua a edicao antes de subdividir o vao')
    if estado['grupo'] != grupo.name or any(n not in bpy.data.objects for n in estado['originais']):
        raise ValueError('A estrutura do vao foi alterada')
    quantidade = int(quantidade)
    if not 0 <= quantidade <= MAXIMO_PRATELEIRAS-len(estado['originais']):
        raise ValueError('Quantidade fora do limite das prateleiras')
    modelo = estado['modelo']
    local = dict(estado['p'], quantidade=quantidade, espacamento='IGUAL', vaos_mm=[],
                 individuais=[dict(modelo) for _ in range(quantidade)])
    dados = calcular(vao(grupo)[0], estado['cima']-estado['baixo'], local)
    novas = [bpy.data.objects[n] for n in estado['novas'] if n in bpy.data.objects]
    fonte = bpy.data.objects.get(estado['fonte'])
    criadas = []
    try:
        for i in range(len(novas), quantidade):
            criadas.append(_copiar_prateleira(grupo, i, fonte) if fonte else
                _nova_prateleira(grupo, i, _material_do_modulo(modulo_do_grupo(grupo))))
    except Exception:
        for obj in criadas:
            _gavetas._remover(obj)
        raise
    for obj in novas[quantidade:]:
        _gavetas._remover(obj)
    novas = novas[:quantidade] + criadas
    if quantidade == 0:
        cancelar_subdivisao_vao(grupo, estado)
        estado.update(novas=[], quantidade=0)
        return
    context.view_layer.update()
    inv = grupo.matrix_world.inverted_safe()
    for obj, caixa in zip(novas, dados['prateleiras']):
        baixo = estado['baixo'] + caixa[4]
        if fonte:
            base = min((inv @ obj.matrix_world @ Vector(c)).z for c in obj.bound_box) * 1000
            mundo = obj.matrix_world.copy()
            mundo.translation += grupo.matrix_world.to_3x3() @ Vector((0,0,(baixo-base)/1000))
            obj.matrix_world = mundo
        else:
            _vestir(obj, (*caixa[:4], baixo, estado['baixo']+caixa[5]))
        obj.select_set(False)
    context.view_layer.update()
    originais = [bpy.data.objects[n] for n in estado['originais']]
    todos = sorted(originais+novas, key=lambda o: min((inv @ o.matrix_world @ Vector(c)).z for c in o.bound_box))
    antigos = estado['p'].get('individuais') or ()
    ajustes = {n: dict(antigos[i]) if i < len(antigos) else {} for i,n in enumerate(estado['originais'])}
    grupo[CHAVE_PARAMETROS] = dict(estado['p'], quantidade=len(todos),
        individuais=[ajustes.get(o.name, dict(modelo)) for o in todos])
    for i, obj in enumerate(todos):
        obj[CHAVE_INDICE] = i
    _sincronizar_disposicao(grupo)
    estado.update(novas=[o.name for o in novas], quantidade=quantidade)
    _hud._hover_hud.clear()


def cancelar_subdivisao_vao(grupo, estado):
    for nome in estado['novas']:
        obj = bpy.data.objects.get(nome)
        if obj is not None:
            _gavetas._remover(obj)
    for i, nome in enumerate(estado['originais']):
        obj = bpy.data.objects.get(nome)
        if obj is not None:
            obj[CHAVE_INDICE] = i
    grupo[CHAVE_PARAMETROS] = estado['p']
    if estado['encaixe'] is not None:
        grupo[CHAVE_ENCAIXE] = estado['encaixe']
    elif CHAVE_ENCAIXE in grupo:
        del grupo[CHAVE_ENCAIXE]
    bpy.context.view_layer.update()


def _digital(obj):
    """Comparacao so' ao entrar/sair de Tab ou adicionar, nunca no redraw."""
    h = hashlib.sha1()
    for itens, campo, tipo, tamanho in ((obj.data.vertices, 'co', 'f', 3),
                                       (obj.data.edges, 'vertices', 'i', 2),
                                       (obj.data.loops, 'vertex_index', 'i', 1),
                                       (obj.data.polygons, 'loop_total', 'i', 1)):
        valores = array(tipo, [0]) * (tamanho * len(itens))
        itens.foreach_get(campo, valores)
        h.update(valores.tobytes())
    p = parametros_individuais(parametros(obj.parent), int(obj[CHAVE_INDICE]))
    h.update(repr(tuple(float(p[k]) for k in CAMPOS_INDIVIDUAIS if k != 'largura_mm')).encode())
    # Configuracao de canais/recortes tambem distingue as matrizes.
    h.update(repr(sorted((k, str(obj[k])) for k in obj.keys()
                         if k.startswith('chapa_') and k not in
                         {'chapa_uid', 'chapa_edicao'})).encode())
    h.update(repr([slot.material.name if slot.material else ''
                   for slot in obj.material_slots]).encode())
    for modificador in obj.modifiers:
        valores = []
        for prop in modificador.bl_rna.properties:
            if prop.identifier in {'name', 'rna_type'} or prop.is_readonly:
                continue
            if prop.type in {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'}:
                valor = getattr(modificador, prop.identifier)
                valores.append((prop.identifier, tuple(valor) if prop.is_array else valor))
        h.update(repr((modificador.type, valores)).encode())
    return h.digest()


def _gravar_individual(p, indice, valores):
    lista = [dict(v) for v in (p.get('individuais') or ())]
    while len(lista) <= indice:
        lista.append({})
    lista[indice].update(valores)
    p['individuais'] = lista


def _copiar_prateleira(grupo, indice, fonte):
    obj = fonte.copy()
    obj.data = fonte.data.copy()
    obj.name = 'Prateleira %d' % (indice + 1)
    _gavetas._colecao(grupo).objects.link(obj)
    obj.parent = grupo
    for chave in list(obj.keys()):
        if chave.startswith('adj_') or chave in ('chapa_uid', 'chapa_edicao', CHAVE_DETALHAMENTO):
            del obj[chave]
    _chapas._garantir_uid(obj)
    obj[CHAVE_INDICE] = indice
    return obj


def quantas_no_modulo(conj):
    """Prateleiras deste sistema no modulo (o orcamento conta)."""
    return sum(len(prateleiras_do_grupo(g)) for g in grupos_do_modulo(conj))


def sincronizar_exclusoes(grupo):
    """Absorve exclusoes/desvinculos antes de editar parametros ou remontar."""
    return _sincronizar_disposicao(grupo, somente_exclusoes=True)


def _sincronizar_disposicao(grupo, somente_exclusoes=False):
    """Le as caixas NATIVAS no referencial do vao, sem mover madeira.

    Os indices antigos identificam os ajustes sobreviventes; compactar
    antes de copia-los atribuiria o modelo apagado a outra prateleira.
    """
    if (_eventos._desfazendo[0] or bpy.context.mode != 'OBJECT'):
        return False
    atuais = prateleiras_do_grupo(grupo)
    p = parametros(grupo)
    indices = [int(o.get(CHAVE_INDICE, 0)) for o in atuais]
    mesmos_indices = int(p['quantidade']) == len(atuais) and indices == list(range(len(atuais)))
    if somente_exclusoes and mesmos_indices:
        return False
    inversa = grupo.matrix_world.inverted_safe()
    disposicao = []
    for obj, indice in zip(atuais, indices):
        matriz = inversa @ obj.matrix_world
        zs = [(matriz @ Vector(c)).z * 1000.0 for c in obj.bound_box]
        disposicao.append((obj, indice, min(zs), max(zs)))
    # G pode atravessar outra unidade: os campos E continuam de baixo
    # para cima, e as escolhas individuais acompanham a MESMA chapa.
    disposicao.sort(key=lambda item: item[2])
    individuais, g, topo = [], [], 0.0
    for obj, indice, baixo, cima in disposicao:
        individuais.append(dict((p.get('individuais') or ())[indice])
                            if indice < len(p.get('individuais') or ()) else {})
        g.append(baixo - topo)
        topo = cima
    try:
        anteriores = (list(p.get('vaos_mm') or ()) if p['espacamento'] == 'LIVRE'
                      else vaos(vao(grupo)[1], p)[:-1])
    except ValueError:
        anteriores = []
    if (mesmos_indices and [d[1] for d in disposicao] == indices
            and len(anteriores) == len(g)
            and all(abs(a - b) <= TOL_MM for a, b in zip(anteriores, g))):
        return False
    p.update(quantidade=len(atuais), espacamento='LIVRE', vaos_mm=g,
             individuais=individuais)
    grupo[CHAVE_PARAMETROS] = p
    for indice, (obj, _antigo, _baixo, _cima) in enumerate(disposicao):
        if obj.get(CHAVE_INDICE) != indice:
            obj[CHAVE_INDICE] = indice
    # O encaixe anterior nao pode ressuscitar posicoes/ajustes antigos.
    if CHAVE_ENCAIXE in grupo:
        del grupo[CHAVE_ENCAIXE]
    return True


def sincronizar_exclusoes_da_cena():
    """Exclusoes E posicoes, so' no timer estavel, depois de absorver Tab."""
    if (_eventos._desfazendo[0] or _chapas._ocupado[0]
            or bpy.context.mode != 'OBJECT'):
        return
    mudou = False
    for grupo in bpy.data.objects:
        if MARCA_GRUPO in grupo:
            if _divisorias.CHAVE_BLOCAGEM not in grupo:
                _divisorias.garantir_blocagem(grupo)
                mudou = True
            mudou = _sincronizar_disposicao(grupo) or mudou
    if mudou:
        _eventos._redesenhar_viewports(bpy.context)


# ------------------------------------------------------------ calculo
def vaos(altura, p):
    """[n + 1] vaos em mm, de baixo para cima: o de baixo de cada
    prateleira e, por ultimo, o de cima da mais alta."""
    n = max(0, int(p['quantidade']))
    e = float(p['espessura_mm'])
    livre = altura - sum(float(parametros_individuais(p, i)['espessura_mm'])
                         for i in range(n))
    if livre < -TOL_MM:
        raise ValueError("%d prateleiras de %g mm nao cabem em %d mm"
                         % (n, e, round(altura)))
    gravados = [float(v) for v in (p.get('vaos_mm') or ())]
    if p.get('espacamento') == 'LIVRE' and len(gravados) == n:
        topo = livre - sum(gravados)
        if topo < -TOL_MM:
            raise ValueError("As prateleiras passam do topo do vao em %d mm"
                             % round(-topo))
        if gravados and min(gravados) < -TOL_MM:
            raise ValueError("Vao negativo entre as prateleiras")
        return gravados + [max(0.0, topo)]
    return [max(0.0, livre) / (n + 1)] * (n + 1)


def calcular(largura, altura, p):
    """{'prateleiras': [(x0, x1, y0, y1, z0, z1)], 'vaos': [n + 1]}."""
    g = vaos(altura, p)
    caixas, z = [], 0.0
    for k in range(len(g) - 1):
        unidade = parametros_individuais(p, k)
        e = float(unidade['espessura_mm'])
        folga = float(unidade['folga_lateral_mm'])
        l = float(unidade.get('largura_mm', largura - 2 * folga))
        y0, y1 = float(unidade['recuo_mm']), float(unidade['profundidade_mm'])
        if e <= 0:
            raise ValueError('Espessura da prateleira tem de ser maior que zero')
        if l < MENOR_LADO_MM or l > largura + TOL_MM:
            raise ValueError('Vao estreito demais para prateleira (%d mm)' % round(largura))
        if y1 - y0 < MENOR_LADO_MM:
            raise ValueError('Prateleira rasa demais: %d mm' % round(y1 - y0))
        z += g[k]
        x0 = float(unidade.get('x_mm', (largura - l) / 2))
        if x0 < -TOL_MM or x0 + l > largura + TOL_MM:
            raise ValueError('A prateleira ultrapassa a largura do vao')
        caixas.append((x0, x0 + l, y0, y1, z, z + e))
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
    valores=grupo.get(CHAVE_REFERENCIA)
    ref=Matrix([valores[i:i+3] for i in (0,3,6)]) if valores else Matrix.Identity(3)
    lo, hi = _gavetas.limites_na_referencia(conj,ref)
    esq, dir_, baixo, cima, frente = list(grupo.get(CHAVE_MARGENS) or (0, 0, 0, 0, 0))
    origem = Vector((lo.x + esq, lo.y + frente, lo.z + baixo))
    return _divisorias.limitar_vao(grupo, hi.x - dir_ - origem.x,
        hi.z - cima - origem.z, ref.to_4x4() @ Matrix.Translation(origem / 1000.0))


def profundidade_ate_o_fundo(conj, ponto):
    """Do plano da frente (o de `ponto`, mundo) ate' a face da frente do
    FUNDO do modulo -- sem fundo, ate' as costas. A prateleira nao entra
    no canal do fundo."""
    lo, hi = _gavetas._limites(conj)
    inversa = conj.matrix_world.inverted()
    limite = hi.y
    for chapa in _modulos._chapas_do_conjunto(conj):
        if _chapas.MARCA_FUNDO in chapa:
            n=(inversa @ chapa.matrix_world).to_3x3().col[2].normalized()
            if abs(n.y)<.995:
                continue
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
    pose = (obj.matrix_parent_inverse != Matrix.Identity(4)
            or obj.matrix_basis != matriz)
    if pose:
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.matrix_basis = matriz
    mudou = not obj.data.vertices or any(abs(a - b) > .001 for a, b in zip(
        (obj.chapa_largura_mm, obj.chapa_comprimento_mm, obj.chapa_espessura_mm), (l, c, e)))
    if mudou:
        _chapas._ocupado[0] = True
        try:
            obj.chapa_largura_mm, obj.chapa_comprimento_mm = l, c
            obj.chapa_espessura_mm = e
            obj.chapa_auto = True
        finally:
            _chapas._ocupado[0] = False
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        _chapas.gerar_malha_chapa(obj)
    return pose or mudou


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


def montar(grupo, referencia=None):
    """Refaz as prateleiras pelos parametros e pelo vao de hoje, nas
    MESMAS chapas (sobra apaga, falta cria com o material das outras).
    Levanta ValueError (e nao mexe em nada) se nao couber."""
    p = parametros(grupo)
    largura, altura, matriz = vao(grupo)
    dados = calcular(largura, altura, p)
    mudou = grupo.matrix_parent_inverse != Matrix.Identity(4)
    if mudou:
        grupo.matrix_parent_inverse = Matrix.Identity(4)
    conj = modulo_do_grupo(grupo)
    if conj is not None and grupo.matrix_basis != matriz:
        grupo.matrix_basis = matriz
        mudou = True
    if tuple(grupo.get(CHAVE_VAO, ())) != (largura, altura):
        grupo[CHAVE_VAO] = (largura, altura)
    atuais = prateleiras_do_grupo(grupo)
    mudou = mudou or len(atuais) < len(dados['prateleiras'])
    material = (_gavetas._material_de(atuais)
                or (_material_do_modulo(conj) if conj is not None else None))
    for velha in atuais[len(dados['prateleiras']):]:
        _gavetas._remover(velha)
        mudou = True
    for i, caixa in enumerate(dados['prateleiras']):
        obj = (atuais[i] if i < len(atuais) else
               _copiar_prateleira(grupo, i, referencia) if referencia is not None else
               _nova_prateleira(grupo, i, material))
        if obj.get(CHAVE_INDICE) != i:
            obj[CHAVE_INDICE] = i
        mudou = _vestir(obj, caixa) or mudou
    # Escrever a mesma pose tambem invalida o depsgraph e os BVHs do
    # snap. A regua nao precisa reavaliar prateleiras que ja' estao certas.
    if mudou:
        bpy.context.view_layer.update()


def criar_prateleiras(context, conj, margens, p, pecas=None, referencial=None, blocagem_uid=None):
    """Grupo de prateleiras novo no modulo `conj`. Devolve o grupo."""
    p = dict(PARAMETROS_PADRAO, **p)
    grupo = bpy.data.objects.new('Prateleiras %s' % conj.name, None)
    colecao = (_modulos._colecao_do_modulo(conj)
               or next(iter(conj.users_collection), context.scene.collection))
    colecao.objects.link(grupo)
    grupo.empty_display_type = 'PLAIN_AXES'
    grupo.empty_display_size = 0.05
    grupo.hide_render = True
    grupo[MARCA_GRUPO] = 1
    grupo[CHAVE_MODULO] = conj.name
    grupo[CHAVE_PARAMETROS] = p
    if referencial is not None:
        grupo[CHAVE_REFERENCIA]=[v for linha in referencial for v in linha]
    grupo[CHAVE_MARGENS] = [float(m) for m in margens]
    grupo.parent = conj
    grupo[_divisorias.CHAVE_BLOCAGEM] = blocagem_uid or _chapas._garantir_uid(grupo)
    try:
        if pecas:
            for obj in pecas:
                obj[MARCA_PRATELEIRA] = 1
            largura, altura, matriz = vao(grupo)
            dados = calcular(largura, altura, p)
            mundo = conj.matrix_world @ matriz
            for i, (obj, caixa) in enumerate(zip(pecas, dados['prateleiras'])):
                nova, dims = _gavetas._matriz_da_caixa(caixa, 2)
                # Reorientar a MESMA malha: L/curva nao pode virar caixa.
                if obj.data.users > 1:
                    obj.data = obj.data.copy()
                obj.data.transform((mundo @ nova).inverted() @ obj.matrix_world)
                obj.parent = grupo
                obj[MARCA_PRATELEIRA] = 1
                obj[CHAVE_INDICE] = i
                for chave in [k for k in obj.keys() if k.startswith('adj_')]:
                    del obj[chave]
        montar(grupo)
        if not pecas:
            _divisorias.particionar_grupo(grupo)
    except ValueError:
        for o in list(grupo.children):
            _gavetas._remover(o)
        _gavetas._remover(grupo)
        raise
    return grupo


def ajustar_ao_espaco(grupo, atual, capacidade):
    """Memoriza a escolha, consumindo a folga antes de diminuir o bloco."""
    p = parametros(grupo)
    assinatura = repr((list(atual), p))
    estado = grupo.get(CHAVE_ENCAIXE)
    if not estado or estado.get('bloco_atual') != assinatura:
        grupo[CHAVE_ENCAIXE] = dict(medidas=list(atual), bloco_atual=assinatura,
            profundidade=float(p['profundidade_mm']), vaos=list(p['vaos_mm']),
            individuais=p.get('individuais', []), ultimo='')
        estado = grupo[CHAVE_ENCAIXE]
    novo = [min(float(v), capacidade[k]) for k,v in enumerate(estado['medidas'])]
    p['profundidade_mm'] = novo[1]
    grupo[CHAVE_PARAMETROS] = p
    estado['ultimo'] = repr((p['profundidade_mm'],p['vaos_mm'],p.get('individuais', [])))
    estado['bloco_atual'] = repr((novo,p))
    return novo


def atualizar_do_conjunto(conj):
    """Remonta no vao transportado, conservando a escolha ate' faltar espaco."""
    for grupo in grupos_do_modulo(conj):
        try:
            sincronizar_exclusoes(grupo)
            p=parametros(grupo)
            _l,altura,matriz=vao(grupo)
            atual=repr((p['profundidade_mm'],p['vaos_mm'],p.get('individuais', [])))
            estado=grupo.get(CHAVE_ENCAIXE)
            if not estado or estado['ultimo']!=atual:
                grupo[CHAVE_ENCAIXE]=dict(profundidade=float(p['profundidade_mm']),
                                          vaos=list(p['vaos_mm']),ultimo=atual,
                                          individuais=p.get('individuais', []))
                estado=grupo[CHAVE_ENCAIXE]
            ref=matriz.to_3x3().normalized()
            _lo,hi=_gavetas.limites_na_referencia(conj,ref)
            origem=ref.transposed() @ matriz.translation*1000
            limite=hi.y-origem.y
            if 'medidas' in estado:
                # O transporte ja' descontou a chapa de apoio. A caixa
                # externa nao pode devolver a profundidade que nao cabe.
                limite=min(limite,float(p['profundidade_mm']))
            p['profundidade_mm']=max(float(p['recuo_mm'])+MENOR_LADO_MM,
                                     min(float(estado['profundidade']),limite))
            for i, unidade in enumerate(estado.get('individuais') or ()):
                modelo = _como_dict(unidade)
                if 'profundidade_mm' in modelo:
                    modelo['profundidade_mm'] = max(
                        float(modelo.get('recuo_mm', p['recuo_mm'])) + MENOR_LADO_MM,
                        min(float(modelo['profundidade_mm']), limite))
                _gravar_individual(p, i, modelo)
            if p['espacamento']=='LIVRE' and len(estado['vaos'])==int(p['quantidade']):
                desejados=list(estado['vaos'])
                livre=max(0,altura-sum(float(parametros_individuais(p, i)['espessura_mm'])
                                      for i in range(int(p['quantidade']))))
                fator=min(1,livre/max(sum(desejados),.001))
                p['vaos_mm']=[v*fator for v in desejados]
            if p != parametros(grupo):
                grupo[CHAVE_PARAMETROS]=p
            ultimo=repr((p['profundidade_mm'],p['vaos_mm'],p.get('individuais', [])))
            if grupo[CHAVE_ENCAIXE]['ultimo'] != ultimo:
                grupo[CHAVE_ENCAIXE]['ultimo']=ultimo
            montar(grupo)
            if 'medidas' in grupo[CHAVE_ENCAIXE]:
                l,a=grupo[CHAVE_VAO]
                grupo[CHAVE_ENCAIXE]['bloco_atual'] = repr(([float(l),float(p['profundidade_mm']),float(a)],p))
        except ValueError as erro:
            print("[Archy Builder] prateleiras de %s: %s" % (conj.name, erro))


def _parametros_editados(grupo, nome, valor):
    p = parametros(grupo)
    n = int(p['quantidade'])
    _largura, altura, _m = vao(grupo)
    if nome == 'quantidade':
        valor = max(0, min(MAXIMO_PRATELEIRAS, int(valor)))
        if valor != n and n and p['espacamento'] == 'LIVRE':
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


def editar(context, grupo, nome, valor, referencia=None, somente_grupo=False):
    """Muda um parametro (aba Prateleiras). Devolve o erro (e desfaz) ou None."""
    estado = edicao_atual(context)
    global_ = estado and grupo.name in estado['globais']
    if context.mode == 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='OBJECT')
    concluir_edicao()
    sincronizar_exclusoes(grupo)
    nome = nome[len('prateleiras_'):] if nome.startswith('prateleiras_') else nome
    antes = parametros(grupo)
    fonte = referencia or (None if global_ or somente_grupo else individual_ativo(context, grupo))
    if nome == 'quantidade' and fonte is not None and referencia is None:
        return editar_quantidade_local(context, grupo, fonte, valor)
    if nome.startswith('vao_') and fonte is not None:
        try:
            trecho = detalhamento(grupo, fonte)
        except ValueError as erro:
            return str(erro)
        # O ultimo campo local e' o vao ACIMA da ultima copia. Quem
        # se move e' ela, nunca o apoio que delimita o proximo trecho.
        if int(nome[len('vao_'):]) == trecho['ultimo'] + 1:
            nome = 'acima_%d' % trecho['ultimo']
    if nome.startswith('individual_'):
        _prefixo, indice, campo = nome.split('_', 2)
        return editar_individual(context, grupo, int(indice), campo, valor)
    if nome in CAMPOS_INDIVIDUAIS and fonte is not None:
        return editar_individual(context, grupo, int(fonte[CHAVE_INDICE]), nome, valor)
    if nome == 'quantidade' and int(valor) > int(antes['quantidade']):
        atuais = prateleiras_do_grupo(grupo)
        if fonte is None and len({_digital(o) for o in atuais}) > 1:
            _referencia_pendente[0] = dict(grupo=grupo.name, quantidade=int(valor),
                                         regiao=None, mouse=None)
            if not bpy.app.background and not bpy.app.timers.is_registered(_abrir_referencia):
                bpy.app.timers.register(_abrir_referencia, first_interval=0.01)
            return None
        fonte = fonte or (atuais[0] if atuais else None)
    try:
        p = _parametros_editados(grupo, nome, valor)
        if nome in CAMPOS_INDIVIDUAIS:
            for unidade in p.get('individuais') or ():
                unidade.pop(nome, None)
        if nome == 'quantidade':
            quantidade = int(p['quantidade'])
            p['individuais'] = list(p.get('individuais') or ())[:quantidade]
            if fonte is not None:
                modelo = parametros_individuais(antes, int(fonte[CHAVE_INDICE]))
                for i in range(int(antes['quantidade']), quantidade):
                    _gravar_individual(p, i, {k: modelo[k] for k in CAMPOS_INDIVIDUAIS
                                              if k in modelo})
            if p['espacamento'] == 'LIVRE':
                try:
                    vaos(vao(grupo)[1], p)
                except ValueError:
                    # A espessura da matriz pode diferir do padrao do
                    # grupo: repartir de novo quando os vaos nao couberem.
                    p.update(espacamento='IGUAL', vaos_mm=[])
        grupo[CHAVE_PARAMETROS] = p
        montar(grupo, referencia=fonte)
    except ValueError as erro:
        grupo[CHAVE_PARAMETROS] = antes
        montar(grupo)
        return str(erro)
    return None


def editar_individual(context, grupo, indice, nome, valor):
    if nome not in CAMPOS_INDIVIDUAIS:
        return 'Parametro individual desconhecido'
    antes = parametros(grupo)
    if not 0 <= indice < int(antes['quantidade']):
        return 'Prateleira nao encontrada'
    p = parametros(grupo)
    if nome == 'largura_mm':
        largura = vao(grupo)[0]
        if not MENOR_LADO_MM <= float(valor) <= largura + TOL_MM:
            return 'Largura fora do vao da prateleira'
        nome, valor = 'folga_lateral_mm', max(0., (largura - float(valor)) / 2)
    fonte = prateleiras_do_grupo(grupo)[indice]
    try:
        indices = [int(o[CHAVE_INDICE]) for o in detalhamento(grupo, fonte)['unidades']]
    except ValueError as erro:
        return str(erro)
    for k in indices:
        _gravar_individual(p, k, {nome: max(0., float(valor))})
    if nome == 'espessura_mm':
        altura = vao(grupo)[1]
        g = vaos(altura, antes)
        for k in indices:
            g[k + 1] -= float(valor) - float(parametros_individuais(antes, k)[nome])
        if min(g) < -TOL_MM:
            return 'Nao cabe: falta espaco acima da prateleira'
        p.update(espacamento='LIVRE', vaos_mm=g[:-1])
    try:
        calcular(*vao(grupo)[:2], p)
        grupo[CHAVE_PARAMETROS] = p
        montar(grupo)
    except ValueError as erro:
        grupo[CHAVE_PARAMETROS] = antes
        return str(erro)
    return None


def resolver_referencia(context, obj):
    pedido = _referencia_pendente[0]
    if (not pedido or obj is None or MARCA_PRATELEIRA not in obj
            or obj.parent is None or obj.parent.name != pedido['grupo']):
        return 'Selecione uma prateleira deste grupo'
    grupo = obj.parent
    quantidade = pedido['quantidade']
    _referencia_pendente[0] = None
    return editar(context, grupo, 'quantidade', quantidade, referencia=obj)


def iniciar_edicao(context, malhas, global_):
    """O Blender faz a edicao multiobjeto; propagar uma vez ao sair.
    Conservar os IDs de Mesh e' necessario para o undo de Edit Mode.
    """
    registros, globais = {}, []
    for obj in malhas:
        grupo = grupo_de(obj)
        if grupo is not None and MARCA_PRATELEIRA in obj:
            registros.setdefault(grupo.name, {})[obj.name] = _digital(obj)
    for nome in registros:
        if global_:
            globais.append(nome)
    if registros:
        _edicao[0] = dict(grupos=registros, globais=globais,
                          ativo=context.view_layer.objects.active.name)


def edicao_atual(context):
    """Undo pode voltar ao Edit Mode com o Empty novamente selecionado.
    Recuperar da selecao NATIVA e medir uma vez a malha ja' restaurada;
    nao reaplicar a referencia de uma sessao de edicao posterior.
    """
    if _edicao[0]:
        return _edicao[0]
    if context.mode == 'EDIT_MESH':
        editando = list(context.objects_in_mode)
        if not any(MARCA_PRATELEIRA in o for o in editando):
            return None
        malhas = _selecao.malhas_para_editar(context)
        for obj in editando:
            obj.update_from_editmode()
        iniciar_edicao(context, malhas or editando, bool(malhas))
    return _edicao[0]


def concluir_edicao():
    if not edicao_atual(bpy.context) or bpy.context.mode == 'EDIT_MESH':
        return
    estado, _edicao[0] = _edicao[0], None
    for nome, digitais in estado['grupos'].items():
        grupo = bpy.data.objects.get(nome)
        if grupo is None:
            continue
        atuais = prateleiras_do_grupo(grupo)
        alteradas = [o for o in atuais if o.name in digitais and _digital(o) != digitais[o.name]]
        if not alteradas:
            continue
        for obj in alteradas:
            _chapas.absorver_malha_editada(obj)
        fonte = next((o for o in alteradas if o.name == estado['ativo']), alteradas[0])
        alvos = atuais if nome in estado['globais'] else alteradas
        p = parametros(grupo)
        largura = vao(grupo)[0]
        for obj in alvos:
            if nome in estado['globais'] and obj != fonte:
                # Nao trocar o datablock: o undo nativo ainda o referencia.
                bm = bmesh.new()
                try:
                    bm.from_mesh(fonte.data)
                    bm.to_mesh(obj.data)
                finally:
                    bm.free()
                obj.data.update()
                for chave in list(obj.keys()):
                    if chave.startswith('chapa_') and chave != 'chapa_uid':
                        del obj[chave]
                for chave in fonte.keys():
                    if chave.startswith('chapa_') and chave not in ('chapa_uid', 'chapa_edicao'):
                        valor = fonte[chave]
                        obj[chave] = valor.to_dict() if hasattr(valor, 'to_dict') else valor
                _chapas.absorver_malha_editada(obj)
            k = int(obj[CHAVE_INDICE])
            modelo = parametros_individuais(p, int(fonte[CHAVE_INDICE]) if nome in estado['globais'] else k)
            _gravar_individual(p, k, dict(espessura_mm=float(obj.chapa_espessura_mm),
                profundidade_mm=float(modelo['recuo_mm']) + obj.chapa_comprimento_mm,
                recuo_mm=float(modelo['recuo_mm']),
                folga_lateral_mm=max(0., (largura - obj.chapa_largura_mm) / 2)))
        grupo[CHAVE_PARAMETROS] = p
        # A posicao vem da malha confirmada, tanto no Tab individual
        # quanto no multiobjeto. Nao remontar nem repartir estes vaos.
        _sincronizar_disposicao(grupo)


def _abrir_referencia():
    if _referencia_pendente[0] and not bpy.app.background:
        bpy.ops.object.cabinet_referencia_prateleira('INVOKE_DEFAULT')
    return None


def atualizar_aviso_referencia(context, event):
    pedido = _referencia_pendente[0]
    if pedido is None:
        return
    pedido.update(mouse=None, regiao=None)
    # Coordenadas da JANELA: o modal nasce no menu, mas o aviso pertence
    # a' viewport sob o cursor. Nao guardar areas/regioes RNA no estado.
    if _gaveta_eventos._gaveta_sob_evento(context, event) is None:
        for area in context.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            regiao = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if regiao is None:
                continue
            x, y = event.mouse_x - regiao.x, event.mouse_y - regiao.y
            if 0 <= x < regiao.width and 0 <= y < regiao.height:
                pedido.update(mouse=Vector((x, y)), regiao=regiao.as_pointer(),
                              recado=OBJECT_OT_referencia_prateleira.bl_label)
                break
    _eventos._redesenhar_viewports(context)


class OBJECT_OT_referencia_prateleira(Operator):
    """Escolhe na viewport a matriz das novas prateleiras"""
    bl_idname = 'object.cabinet_referencia_prateleira'
    bl_label = 'Selecione a prateleira de referencia'
    bl_options = {'INTERNAL', 'UNDO'}

    def invoke(self, context, event):
        if not _referencia_pendente[0]:
            return {'CANCELLED'}
        atualizar_aviso_referencia(context, event)
        context.workspace.status_text_set('Selecione a prateleira de referencia | Esc cancela')
        context.window_manager.modal_handler_add(self)
        _eventos._redesenhar_viewports(context)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        _referencia_pendente[0] = None
        context.workspace.status_text_set(None)
        _eventos._redesenhar_viewports(context)

    def modal(self, context, event):
        if not _referencia_pendente[0] or event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cancel(context)
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            atualizar_aviso_referencia(context, event)
            return {'PASS_THROUGH'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            obj = bpy.data.objects.get(_gaveta_eventos._objeto_sob_mouse(context, event))
            try:
                erro = resolver_referencia(context, obj)
            except Exception:
                self.cancel(context)
                raise
            if erro:
                self.report({'WARNING'}, erro)
                if _referencia_pendente[0]:
                    return {'RUNNING_MODAL'}
            self.cancel(context)
            return {'CANCELLED'} if erro else {'FINISHED'}
        return {'PASS_THROUGH'}


def entre(grupo):
    """O "Entre prateleiras" da aba: a media dos vaos de baixo."""
    _largura, altura, _m = vao(grupo)
    try:
        baixo = vaos(altura, parametros(grupo))[:-1]
    except ValueError:
        return 0.0
    return sum(baixo) / len(baixo) if baixo else 0.0


class OBJECT_OT_alinhar_prateleiras(Operator):
    bl_idname = 'object.cabinet_alinhar_prateleiras'
    bl_label = 'Centralizar espacamento'
    bl_description = 'Iguala os vaos acima e abaixo da prateleira selecionada; no grupo, distribui todas'
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        grupo = grupo_de(context.object)
        return (grupo is not None and getattr(context, 'mode', '') == 'OBJECT'
                and bool(prateleiras_do_grupo(grupo)))

    def execute(self, context):
        grupo = grupo_de(context.object)
        # A exclusao nativa pode ainda nao ter passado pelo timer: o indice
        # da unidade tem de corresponder aos apoios que restaram.
        sincronizar_exclusoes(grupo)
        unidade = individual_ativo(context, grupo)
        if unidade is None:
            erro = editar(context, grupo, 'espacamento', 'IGUAL')
        else:
            indice = int(unidade[CHAVE_INDICE])
            if unidade.get(CHAVE_DETALHAMENTO):
                erro = editar_quantidade_local(context, grupo, unidade,
                    detalhamento(grupo, unidade)['quantidade'], redistribuir=True)
                if erro:
                    self.report({'WARNING'}, erro)
                    return {'CANCELLED'}
                _eventos._redesenhar_viewports(context)
                return {'FINISHED'}
            g = vaos(vao(grupo)[1], parametros(grupo))
            erro = editar(context, grupo, 'vao_%d' % indice,
                          (g[indice] + g[indice + 1]) / 2)
        if erro:
            self.report({'WARNING'}, erro)
            return {'CANCELLED'}
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


# ------------------------------------------------------------ selecao
def selecionar(context, obj, nivel, somar=False):
    """'GRUPO' = todas as prateleiras do vao; 'PRATELEIRA' = so' a de `obj`."""
    grupo = grupo_de(obj)
    if grupo is None:
        return False
    _divisorias.garantir_blocagem(grupo)
    if nivel == 'PRATELEIRA' and MARCA_PRATELEIRA in obj:
        alvos, ativo = [obj], obj
    else:
        alvos = [o for g in _divisorias.grupos_da_blocagem(grupo) for o in [g, *prateleiras_do_grupo(g)]]
        ativo = grupo
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
    if individual_ativo(bpy.context, grupo) is not None:
        return _linhas_hud_grupo(grupo, chapas)
    return _divisorias.linhas_da_blocagem(grupo, chapas, _linhas_hud_grupo)


def _linhas_hud_grupo(grupo, chapas):
    """Linhas da HUD (tipo 'prateleiras'): L/P/A na caixa do vao, como
    as gavetas, e uma linha por VAO entre as prateleiras (o valor ao
    lado; arrastar ou clicar e digitar anda so' a prateleira de cima)."""
    largura, altura, prof = medidas(grupo)
    m = grupo.matrix_world
    unidade = individual_ativo(bpy.context, grupo)
    detalhe = None
    if unidade is not None:
        try:
            detalhe = detalhamento(grupo, unidade)
        except ValueError:
            pass
    x0, x1, y0, y1, z0, z1 = 0., largura, 0., prof, 0., altura
    if detalhe:
        caixas = detalhe['caixas']
        x0, x1 = min(c[0] for c in caixas), max(c[1] for c in caixas)
        y0, y1 = min(c[2] for c in caixas), max(c[3] for c in caixas)
        z0, z1 = detalhe['baixo'], detalhe['cima']
    cantos = [m @ (Vector(((x0, x1)[i], (y0, y1)[j], (z0, z1)[k])) / 1000.0)
              for k in (0, 1) for j in (0, 1) for i in (0, 1)]
    letras = {0: 'L', 1: 'P', 2: 'A'}
    linhas = []
    for eixo, arestas in enumerate(_hud.ARESTAS_EIXO):
        for i, j in arestas:
            # O trecho local e' limitado pelos apoios. As cotas dos vaos
            # editam a posicao; esta moldura nao redimensiona o bloco global.
            linhas.append({'tipo': 'contorno_forma' if detalhe else 'prateleiras',
                           'editavel': not bool(detalhe), 'objeto': grupo, 'modo': 'PRATELEIRAS',
                           'eixo': eixo, 'letra': None if detalhe else letras[eixo],
                           'face': (letras[eixo],), 'cantos': (i, j),
                           'chapas': chapas, 'pontos': [cantos[i], cantos[j]]})
    p = parametros(grupo)
    try:
        dados = calcular(largura, altura, p)
    except ValueError:
        return cantos, linhas
    caixas = dados['prateleiras']
    x, y = (x0 + x1) / 2.0, y0
    indices = range(detalhe['primeiro'], detalhe['ultimo'] + 2) if detalhe else range(len(dados['vaos']))
    for k in indices:
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
    sincronizar_exclusoes(grupo)
    chave = tuple(chave) if isinstance(chave, (tuple, list)) else (chave,)
    letra = chave[0]
    if letra == 'V':
        return editar(context, grupo, 'vao_%d' % chave[1], novo)
    if letra == 'P':
        novo = max(MENOR_LADO_MM, float(novo))
        antes = list(grupo.get(CHAVE_MARGENS) or (0, 0, 0, 0, 0))
        if lado == 'max':
            margens = list(antes)
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
        print("[Archy Builder] prateleiras:", erro)


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
        # vai ate' o fundo (`_definir_vao`, sem varrer malha no clique); a
        # folga da frente e' o Recuo da aba

    def _depois_da_quantidade(self, context):
        return self._criar(context)

    def _criar_grupo(self, context, conj, margens, p):
        return criar_prateleiras(context, conj, margens, p,referencial=self._w.get('referencia'))

    def _selecionar_grupo(self, context, grupo):
        selecionar(context, grupo, 'GRUPO')


def esquecer():
    _assistente_prateleiras[0] = None
    _quantidade_previa[0] = None
    if _referencia_pendente[0] and bpy.context.workspace is not None:
        bpy.context.workspace.status_text_set(None)
    _referencia_pendente[0] = None
    _edicao[0] = None
    if bpy.app.timers.is_registered(_abrir_referencia):
        bpy.app.timers.unregister(_abrir_referencia)
