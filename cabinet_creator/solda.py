"""Correntes da solda (adjacencia): desagregar, conectar, ancoras,
regua (resetar distancia) e o nome do grupo que a Corrente cria."""

import bpy, math, json, gpu
from gpu_extras.batch import batch_for_shader
from bpy.props import BoolProperty, StringProperty, IntProperty
from mathutils import Vector
from bpy_extras import view3d_utils
from bpy.types import Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = None
_modulos = None
_opcoes = None
_eventos = None
_selecao = None
_portas = None
_ferragens = None
_importacao = None
_puxadores = None
_gaveta = None
_orcamento = None
_hud = None
_perguntas = None
_portas_viewport = None
_gaveta_desenho = None

# ------------------------------------------- correntes de adjacencia
# A adjacencia (a SOLDA) liga a PONTA de uma chapa a FACE de outra e
# grava a folga daquele momento -- a origem da solda. Cada ligacao associa
# 2 pares de vertices (as quinas da junta). Regras do usuario:
# - so' com a tecla das opcoes segurada (Alt por padrao);
# - aparecem TODAS as quinas soldadas do item cuja folga saiu da origem
#   mais de LIMIAR_CORRENTE_VIEWPORT (antes: so' a mais perto da camera);
# - cada linha tem a corrente (desagrega o objeto inteiro, `desagregar`)
#   e, a direita, a regua (`cabinet_resetar_distancia`: volta a solda).
LIMIAR_CORRENTE_VIEWPORT = 0.005     # m de desvio da origem da solda
RAIO_CORRENTE_PX = 14.0
VAO_BOTOES_CORRENTE_PX = 13.0        # corrente a esquerda, regua a direita
TECLAS_CORRENTE = ('LEFT_ALT', 'RIGHT_ALT', 'LEFT_CTRL', 'RIGHT_CTRL',
                   'LEFT_SHIFT', 'RIGHT_SHIFT')
_tecla_corrente_segurada = [False]


def _correntes_visiveis():
    return (_opcoes._opcao('tecla_corrente') == 'SEMPRE'
            or _tecla_corrente_segurada[0])


def _folga_atual(C, ponta, N):
    """(folga em m, eixo u, extremo de C em u) entre a ponta `ponta` de
    C e a face memorizada do vizinho N, na geometria de AGORA."""
    eixo, lado = ponta.split('_')
    ex, ey, _ez = _chapas._eixos(C)
    u = ex if eixo == 'x' else ey
    hx, hy, _hz = _chapas._meias(C)
    h = hx if eixo == 'x' else hy
    extremo = _chapas._centro(C).dot(u) + (h if lado == 'pos' else -h)
    face = int(C.get('adj_%s_face' % ponta, 0 if lado == 'pos' else 1))
    return abs(_chapas._faixa(N, u)[face] - extremo), u, extremo


def _assinatura_canto(C, p):
    """Qual canto de C e' o ponto p, pelo SINAL no referencial da chapa
    ('+-+'): estavel quando a chapa muda de medida ou de lugar."""
    local = C.matrix_world.inverted() @ p
    return ''.join('+' if v > 0 else '-' for v in local)


def _canto_da_assinatura(C, assinatura):
    """Inverso de `_assinatura_canto`: o canto de C em mundo."""
    meias = _chapas._meias(C)
    local = Vector([(1 if s == '+' else -1) * m
                    for s, m in zip(assinatura, meias)])
    return C.matrix_world @ local


def _pares_da_ligacao(C, u, extremo, N):
    """Os 2 pares (vertice de C, vertice de N, assinatura) da ligacao:
    cada canto da ponta de C com o canto mais perto de N; ficam os dois
    mais curtos (de um lado e do outro da junta)."""
    ponta = [p for p in _chapas._cantos(C) if abs(p.dot(u) - extremo) < 1e-5]
    cantos_n = _chapas._cantos(N)
    pares = [(p, min(cantos_n, key=lambda q: (q - p).length)) for p in ponta]
    pares.sort(key=lambda par: (par[1] - par[0]).length)
    return [(p, q, _assinatura_canto(C, p)) for p, q in pares[:2]]


def _vizinho_da_ponta(C, ponta):
    nome = C.get('adj_' + ponta, '')
    uid = C.get('adj_%s_uid' % ponta, '')
    if not nome and not uid:
        return None
    N = _chapas._resolver_vizinho(C, uid, nome)
    return None if N is C else N


def _ligados_a(C):
    """Pecas ligadas a C pela adjacencia, em qualquer sentido."""
    ligados = {N for N in (_vizinho_da_ponta(C, p) for p in _chapas.PONTAS) if N}
    for X in bpy.data.objects:
        if X is not C and _chapas.MARCA_CHAPA in X and any(
                _vizinho_da_ponta(X, p) == C for p in _chapas.PONTAS):
            ligados.add(X)
    return ligados


def agregado(C):
    """Ligada (agregada) a alguma peca? E' o azul do botao Corrente."""
    return bool(_ligados_a(C))


def _ligacoes_adjacencia(chapas_item, limiar=None):
    """Ligacoes que tocam o item e cuja folga saiu da ORIGEM da solda (a
    gravada) `limiar` ou mais (m; padrao LIMIAR_CORRENTE_VIEWPORT).
    A adjacencia e' gravada so' na peca que encosta (ponta dela ->
    vizinho), entao varre a cena toda: o vizinho de fora pode ser quem
    guarda a ligacao."""
    limiar = LIMIAR_CORRENTE_VIEWPORT if limiar is None else limiar
    item = set(chapas_item)
    ligacoes = []
    for C in bpy.data.objects:
        if C.type != 'MESH' or _chapas.MARCA_CHAPA not in C:
            continue
        for ponta in _chapas.PONTAS:
            N = _vizinho_da_ponta(C, ponta)
            if N is None or (C not in item and N not in item):
                continue
            folga, u, extremo = _folga_com_sinal(C, ponta, N)
            desvio, residuos = _medida_solda(C, ponta, N)
            if _tamanho_desvio(desvio, residuos) < limiar:
                continue            # na origem da solda: sem corrente
            ancoras = _ancoras_da_ligacao(C, ponta, N, u, extremo)
            pares = [(_vertice_da_assinatura(C, sc),
                      _vertice_da_assinatura(N, sn), sc) for sc, sn in ancoras]
            # Com ancoras gravadas cada par tem o SEU desvio: o que ja'
            # encostou some (a print do usuario: ele ficava desenhado em
            # cima do vertice, sobrepondo bolinha e botoes)
            sentido = u if ponta.endswith('pos') else -u
            memorizada = float(C.get('adj_%s_folga' % ponta, 0.0))
            soltos = ([(q - sentido * memorizada - p).length >= limiar
                       for p, q, _s in pares]
                      if _ancoras_gravadas(C, ponta) else [True] * len(pares))
            ligacoes.append({'a': C, 'b': N, 'ponta': ponta,
                             'folga': folga, 'desvio': desvio,
                             'ancoras': ancoras, 'pares': pares,
                             'soltos': soltos})
    return ligacoes


def _correntes_hud(context):
    """[corrente] de TODAS as quinas soldadas e fora da origem dos itens
    da HUD: uma por par de vertices, com o 'meio' em pixels e a peca que
    a regua move ('movel')."""
    if (not _correntes_visiveis() or not _hud._contexto_hud(context)
            or _gaveta._eh_area_gaveta(context) or _conexao_manual[0] is not None):
        return []
    if getattr(context, 'region_data', None) is None:
        return []
    chapas = [c for _o, _m, pecas in _hud._itens_hud(context) for c in pecas]
    correntes = []
    for ligacao in _ligacoes_adjacencia(chapas):
        movel = _peca_da_regua(context, ligacao['a'], ligacao['b'])
        for k, ((p, q, assinatura), ancora) in enumerate(
                zip(ligacao['pares'], ligacao['ancoras'])):
            if not ligacao['soltos'][k]:
                continue            # esse par ja' encostou: some
            correntes.append({'a': ligacao['a'], 'b': ligacao['b'],
                              'ponta': ligacao['ponta'], 'movel': movel,
                              'assinatura': assinatura, 'pontos': [p, q],
                              'indice': k, 'ancora': ancora,
                              'meio': _hud._projetar_hud(context, (p + q) / 2)})
    return correntes


RAIO_BOLINHA_PX = 9.0
_bolinha_hover = [None]          # (chapa, ponta, indice, lado) sob o mouse


def _bolinhas_da_corrente(context, corrente):
    """{'a': ponto na tela do vertice da chapa, 'b': do vertice alvo}."""
    p, q = corrente['pontos']
    return {lado: ponto for lado, ponto in (
        ('a', _hud._projetar_hud(context, p)), ('b', _hud._projetar_hud(context, q)))
        if ponto is not None}


def _bolinha_sob_mouse(context, posicao):
    """(corrente, 'a' | 'b') da bolinha branca sob o mouse, ou (None, None).
    'a' = o vertice da chapa soldada, 'b' = onde ele encosta."""
    raio = RAIO_BOLINHA_PX * max(1.0, context.preferences.system.ui_scale)
    mouse = Vector(posicao)
    melhor = None
    for corrente in _correntes_hud(context):
        for lado, ponto in _bolinhas_da_corrente(context, corrente).items():
            d = (ponto - mouse).length
            if d <= raio and (melhor is None or d < melhor[0]):
                melhor = (d, corrente, lado)
    return (melhor[1], melhor[2]) if melhor else (None, None)


def _chave_bolinha(corrente, lado):
    return (corrente['a'].name, corrente['ponta'], corrente['indice'], lado)


def _botoes_da_corrente(context, corrente):
    """{'corrente': centro, 'regua': centro} em pixels (lado a lado)."""
    if corrente['meio'] is None:
        return {}
    vao = VAO_BOTOES_CORRENTE_PX * max(1.0, context.preferences.system.ui_scale)
    return {'corrente': corrente['meio'] - Vector((vao, 0)),
            'regua': corrente['meio'] + Vector((vao, 0))}


def _botao_corrente_sob_mouse(context, posicao):
    """(corrente, 'corrente' | 'regua') sob o mouse, ou (None, None)."""
    raio = RAIO_CORRENTE_PX * max(1.0, context.preferences.system.ui_scale)
    mouse = Vector(posicao)
    melhor = None
    for corrente in _correntes_hud(context):
        for tipo, centro in _botoes_da_corrente(context, corrente).items():
            d = (centro - mouse).length
            if d <= raio and (melhor is None or d < melhor[0]):
                melhor = (d, corrente, tipo)
    return (melhor[1], melhor[2]) if melhor else (None, None)


def _alvo_da_corrente(context, posicao):
    """('bolinha', corrente, lado), ('botao', corrente, tipo) ou None: o
    MAIS PERTO do mouse. Numa linha curta na tela a bolinha da ponta fica
    sob o botao -- primeiro que achasse roubava o clique do outro."""
    mouse = Vector(posicao)
    escala = max(1.0, context.preferences.system.ui_scale)
    candidatos = []
    corrente, lado = _bolinha_sob_mouse(context, posicao)
    if corrente is not None:
        ponto = _bolinhas_da_corrente(context, corrente)[lado]
        candidatos.append(((ponto - mouse).length / (RAIO_BOLINHA_PX * escala),
                           'bolinha', corrente, lado))
    corrente, tipo = _botao_corrente_sob_mouse(context, posicao)
    if corrente is not None:
        centro = _botoes_da_corrente(context, corrente)[tipo]
        candidatos.append(((centro - mouse).length / (RAIO_CORRENTE_PX * escala),
                           'botao', corrente, tipo))
    grupo, indice = _portas_viewport._canto_porta_sob_mouse(context, posicao)
    if grupo is not None:
        ponto = _hud._projetar_hud(context, _portas_viewport._cantos_da_porta(grupo)[indice])
        candidatos.append(((ponto - mouse).length / (RAIO_BOLINHA_PX * escala),
                           'canto_porta', grupo, indice))
    grupo, tipo = _ferragens._controle_ferragem_sob_mouse(context, posicao)
    if grupo is not None:
        ponto = next(_hud._projetar_hud(context, c[1])
                     for c in _ferragens._controles_ferragens(grupo, {tipo}))
        candidatos.append(((ponto - mouse).length / (RAIO_BOLINHA_PX * escala),
                           'ferragem', grupo, tipo))
    pux = _puxadores._puxador_sob_mouse(context, posicao)
    if pux is not None:
        ponto = _hud._projetar_hud(context, _puxadores._ancora_do_puxador(pux))
        candidatos.append(((ponto - mouse).length / (RAIO_BOLINHA_PX * escala),
                           'puxador', pux, None))
    if not candidatos:
        return None
    return min(candidatos, key=lambda c: c[0])[1:]


def _corrente_sob_mouse(context, posicao):
    """Corrente cujo botao OU bolinha esta' sob o mouse (o clique e' dela,
    nao da HUD de baixo)."""
    return (_botao_corrente_sob_mouse(context, posicao)[0]
            or _bolinha_sob_mouse(context, posicao)[0])


def desassociar(a, b):
    """Apaga TODAS as ligacoes entre a e b, dos dois lados. Devolve
    quantas pontas foram desligadas."""
    n = 0
    for C, N in ((a, b), (b, a)):
        for ponta in _chapas.PONTAS:
            if _vizinho_da_ponta(C, ponta) != N:
                continue
            base = 'adj_' + ponta
            for sufixo in ('', '_uid', '_folga', '_face', '_ancoras'):
                if base + sufixo in C:
                    del C[base + sufixo]
            n += 1
    return n


def _atualizar_modulo(modulo):
    try:
        bpy.context.view_layer.update()
        _modulos.reposicionar_origem(modulo)
        _modulos.sincronizar_medidas_conjunto(modulo)
        _portas.atualizar_portas_do_conjunto(modulo)
    except Exception as e:
        print("[Cabinet Creator] atualizar modulo:", e)


def desagregar(C):
    """Desassocia TODAS as quinas de C de uma vez (pedido do usuario: a
    quina clicada vale pelo objeto inteiro) e, se C estava num modulo,
    tira C dele sem sair do lugar. Devolve quantas pecas soltou."""
    soltas, modulo = _soltar(C)
    if modulo is not None:
        _atualizar_modulo(modulo)
    return soltas


def _soltar(C):
    """Apaga as ligacoes de C e o tira do modulo sem sair do lugar.
    Devolve (pecas desligadas, modulo de onde saiu ou None)."""
    soltas = 0
    for N in _ligados_a(C):
        desassociar(C, N)
        soltas += 1
    modulo = _portas._modulo_da_chapa(C)
    if modulo is not None:
        mundo = C.matrix_world.copy()
        C.parent = None
        C.matrix_world = mundo
        # fora do armario, na RAIZ da cena (pedido do usuario)
        _modulos._mover_para_colecao(C, bpy.context.scene.collection)
    return soltas, modulo


def desagregar_grupo(pecas):
    """Desagrega TODAS as pecas de uma vez ("desagregar todos os itens
    deste grupo"). O modulo que fica sem filho nenhum e' apagado: um
    Empty vazio so' sobraria na cena com medidas de nada."""
    modulos = set()
    for C in pecas:
        _n, modulo = _soltar(C)
        if modulo is not None:
            modulos.add(modulo)
    for modulo in modulos:
        if modulo.children:
            _atualizar_modulo(modulo)
        else:
            colecao = _modulos._colecao_do_modulo(modulo)
            bpy.data.objects.remove(modulo, do_unlink=True)
            if colecao is not None and not colecao.all_objects:
                bpy.data.collections.remove(colecao)
    return len(pecas)


def _puxar_por_pares(C, pares):
    """Leva os cantos de C aos destinos: [(assinatura em C, ponto alvo)].

    Em cada eixo da chapa (largura, comprimento) a ponta que tem cantos
    puxados vai ate' a media dos alvos -- a outra ponta fica, e a chapa
    estica; sem canto puxado naquele eixo ela so' translada. A espessura
    nunca estica: translada. O alvo nao se mexe (a peca e' que vai a ele).
    """
    if not pares:
        return
    eixos = _chapas._eixos(C)
    meias = _chapas._meias(C)
    centro = _chapas._centro(C)
    deslocamento = Vector((0, 0, 0))
    medidas = [C.chapa_largura_mm, C.chapa_comprimento_mm]
    for i in range(3):
        u, h = eixos[i], meias[i]
        c = centro.dot(u)
        mais = [alvo.dot(u) for s, alvo in pares if s[i] == '+']
        menos = [alvo.dot(u) for s, alvo in pares if s[i] == '-']
        if i < 2 and (mais or menos):
            novo_mais = sum(mais) / len(mais) if mais else c + h
            novo_menos = sum(menos) / len(menos) if menos else c - h
            if novo_mais - novo_menos > 0.001:
                medidas[i] = (novo_mais - novo_menos) * 1000.0
                deslocamento += u * ((novo_mais + novo_menos) / 2 - c)
                continue
        media = sum((alvo - _canto_da_assinatura(C, s)).dot(u)
                    for s, alvo in pares) / len(pares)
        deslocamento += u * media
    _chapas._ocupado[0] = True
    try:
        C.chapa_largura_mm, C.chapa_comprimento_mm = medidas
    finally:
        _chapas._ocupado[0] = False
    _chapas._definir_centro(C, centro + deslocamento)
    _chapas.gerar_malha_chapa(C)
    bpy.context.view_layer.update()


def juntar_conexao(C, alvos, pecas, juntar):
    """Fim de uma associacao. alvos = [(assinatura do canto de C, ponto
    alvo)], pecas = as pecas alvo. `juntar` (resposta do "Juntar ao
    modulo?"): puxa os cantos de C ate' os alvos -- o alvo fica PARADO --,
    entra no modulo do alvo e associa. Sem juntar, so' associa o que ja'
    estiver ao alcance, sem mover nada."""
    pecas = {N for N in pecas if N is not None and N is not C}
    if juntar and alvos:
        _puxar_por_pares(C, alvos)
        modulo = next((m for m in (_portas._modulo_da_chapa(N) for N in pecas)
                       if m is not None), None)
        if modulo is not None and _portas._modulo_da_chapa(C) != modulo:
            mundo = C.matrix_world.copy()
            C.parent = modulo
            C.matrix_parent_inverse = modulo.matrix_world.inverted()
            C.matrix_world = mundo
            pecas |= set(_modulos._chapas_do_conjunto(modulo))
            bpy.context.view_layer.update()
            _chapas.associar_por_distancia(C, pecas)
            _atualizar_modulo(modulo)
            return
    _chapas.associar_por_distancia(C, pecas)


def _alvos_por_distancia(C, candidatos=None):
    """(alvos, pecas) da conexao por distancia: cada ponta de C ao alcance
    de um vizinho vai so' ATE' a face dele (fecha a folga, nao desliza).
    `candidatos` limita os vizinhos aos alvos selecionados."""
    outras = _chapas._chapas_candidatas(C, candidatos)
    alvos, pecas = [], set()
    eixos = _chapas._eixos(C)
    for i, eixo in enumerate(("x", "y")):
        for lado in ("pos", "neg"):
            achado = _chapas._melhor_vizinho(C, eixo, lado, outras,
                                     _chapas.ALCANCE_CONEXAO_AUTOMATICA)
            if achado is None:
                continue
            N, folga, _face = achado
            pecas.add(N)
            u = eixos[i] * (1 if lado == "pos" else -1)
            for p in _chapas._cantos(C):
                s = _assinatura_canto(C, p)
                if s[i] == ('+' if lado == "pos" else '-'):
                    alvos.append((s, p + u * folga))
    return alvos, pecas | _chapas._vizinhos_por_distancia(C, candidatos=candidatos)


class OBJECT_OT_desassociar(Operator):
    """Desagrega esta peca: todas as quinas dela se soltam e ela sai do modulo"""
    bl_idname = 'object.cabinet_desassociar'
    bl_label = 'Desagregar'
    bl_options = {'REGISTER', 'UNDO'}

    chapa: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        chapa = bpy.data.objects.get(self.chapa)
        if chapa is None or _chapas.MARCA_CHAPA not in chapa:
            self.report({'WARNING'}, 'Peca nao encontrada')
            return {'CANCELLED'}
        if not agregado(chapa) and _portas._modulo_da_chapa(chapa) is None:
            self.report({'INFO'}, "Esta peca ja' estava desagregada")
            return {'CANCELLED'}
        desagregar(chapa)
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


class OBJECT_OT_clique_corrente(Operator):
    """Clique na corrente (desagrega) ou na regua (resetar) com a tecla segurada"""
    bl_idname = 'object.cabinet_clique_corrente'
    bl_label = 'Desagregar pela Corrente'
    bl_options = {'INTERNAL', 'UNDO'}

    # O botao nativo da corrente (GIZMO_GT_button_2d) so' aceita clique
    # SEM modificador -- e a corrente so' aparece com Alt/Ctrl/Shift
    # segurado. Este atalho (qualquer modificador, na frente da selecao)
    # pega o clique; fora de uma corrente o evento segue intacto.
    @classmethod
    def poll(cls, context):
        return _correntes_visiveis() and _hud._contexto_hud(context)

    def invoke(self, context, event):
        posicao = (event.mouse_region_x, event.mouse_region_y)
        alvo = _alvo_da_corrente(context, posicao)
        if alvo is None:
            return {'PASS_THROUGH'}
        tipo_alvo, corrente, tipo = alvo
        if tipo_alvo == 'puxador':
            # ancora do puxador: arrastar ate' outra borda do grupo
            bpy.ops.object.cabinet_arrastar_puxador(
                'INVOKE_DEFAULT', puxador=corrente.name)
            return {'FINISHED'}
        if tipo_alvo == 'ferragem':
            # controlador da dobradica (borda) ou do pistao (lateral)
            bpy.ops.object.cabinet_arrastar_ferragem(
                'INVOKE_DEFAULT', grupo=corrente.name, tipo=tipo)
            return {'FINISHED'}
        if tipo_alvo == 'canto_porta':
            # canto da porta: arrastar ate' outro vertice refaz a porta
            bpy.ops.object.cabinet_arrastar_canto_porta(
                'INVOKE_DEFAULT', grupo=corrente.name, indice=tipo)
            return {'FINISHED'}
        if tipo_alvo == 'bolinha':
            # bolinha branca: arrastar a ancora ate' outro vertice
            bpy.ops.object.cabinet_arrastar_ancora(
                'INVOKE_DEFAULT', chapa=corrente['a'].name,
                ponta=corrente['ponta'], indice=corrente['indice'], lado=tipo)
            return {'FINISHED'}
        if tipo == 'regua':
            # a regua pode perguntar ("vai mudar de medida"): o operador
            # espera o SOLTAR deste clique para abrir o pop-up
            # (este operador nao tem modal: devolver o RUNNING_MODAL do
            # reset aqui o cancelava)
            bpy.ops.object.cabinet_resetar_distancia(
                'INVOKE_DEFAULT', chapa=corrente['movel'].name,
                esperar_soltar=True)
            _eventos._redesenhar_viewports(context)
            return {'FINISHED'}
        desagregar(corrente['a'])
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


class OBJECT_OT_tecla_corrente(Operator):
    """Segurar a tecla das opcoes mostra a corrente; soltar esconde"""
    bl_idname = 'object.cabinet_tecla_corrente'
    bl_label = 'Mostrar Correntes'
    bl_options = {'INTERNAL'}

    tecla: StringProperty(options={'SKIP_SAVE'})
    apertou: BoolProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        # o evento SEMPRE segue adiante: Alt/Ctrl/Shift continuam valendo
        # para o Blender e para os outros atalhos
        if self.tecla.split('_', 1)[-1] == _opcoes._opcao('tecla_corrente'):
            if _tecla_corrente_segurada[0] != self.apertou:
                _tecla_corrente_segurada[0] = self.apertou
                _eventos._redesenhar_viewports(context)
        return {'PASS_THROUGH'}


# ------------------------------------------ botao Corrente da gaveta
# Regras do usuario (a selecao diz o que o clique faz):
# - UMA peca (individual, nao o grupo): agregada -> "desagregar esse
#   objeto do grupo?"; solta -> "selecionar vertice" direto.
# - o GRUPO (clique no modulo, ou pecas ligadas) -> "desagregar todos
#   os itens deste grupo?".
# - alvo(s) primeiro e, por ULTIMO (o ativo do Blender), a peca de fora:
#   conecta por distancia ate' ALCANCE_CONEXAO_AUTOMATICA; mais longe,
#   "selecionar vertice" so' com os cantos dos alvos.
OP_CORRENTE_OBJETO = 'object.cabinet_corrente_objeto'
# Botoes da gaveta que abrem pop-up ou modal: disparam no SOLTAR, pela
# propria gaveta (interagir_gaveta). Pelo gizmo do icone, o pop-up nascia
# sob o mouse e o RELEASE ja' respondia; e o modal aberto pelo gizmo
# prendia os cliques da gaveta -- o "Confirmar" do pe' nao chegava.
OPERADORES_NO_SOLTAR = {OP_CORRENTE_OBJETO,
                        'object.cabinet_resetar_distancia'}
_desagregar_pendente = [None]    # pecas esperando o "tem certeza?"
_conexao_pendente = [None]       # alvos esperando o "Juntar ao modulo?"
_conexao_manual = [None]         # estado do modo "selecionar vertice"
RAIO_VERTICE_PX = 16.0
PERGUNTA_DESAGREGAR_GRUPO = ('Voce tem certeza que deseja desagregar todos '
                             'os itens deste grupo?')
PERGUNTA_DESAGREGAR_OBJETO = ('Voce realmente deseja desagregar esse '
                              'objeto do grupo?')


def _chapas_selecionadas(context):
    return [o for o in getattr(context, 'selected_objects', ()) or ()
            if o.type == 'MESH' and _chapas.MARCA_CHAPA in o]


def _acao_corrente(context, medir=True):
    """(acao, peca, pecas) do botao Corrente pela selecao, ou None:
    ('grupo', None, pecas do grupo), ('desagregar', peca, [peca]),
    ('conectar', peca de fora, alvos ao alcance) ou ('vertices', peca,
    alvos -- vazio = qualquer chapa). Sem `medir` nao procura vizinhos
    (o desenho da gaveta so' precisa saber se e' azul ou cinza)."""
    selecionados = list(getattr(context, 'selected_objects', ()) or ())
    chapas = [o for o in selecionados if o.type == 'MESH' and _chapas.MARCA_CHAPA in o]
    ativo = getattr(context, 'active_object', None)
    if ativo is not None and ativo not in selecionados:
        ativo = None
    if ativo is None and len(chapas) == 1:
        ativo = chapas[0]
    if ativo is None or (_chapas.MARCA_CHAPA not in ativo and _chapas.MARCA_CONJUNTO not in ativo):
        return None
    modulo = ativo if _chapas.MARCA_CONJUNTO in ativo else _portas._modulo_da_chapa(ativo)
    grupo = set(_selecao.familia_de(ativo))
    if modulo is not None:
        grupo |= set(_modulos._chapas_do_conjunto(modulo))
    alvos = [c for c in chapas if c not in grupo]
    if alvos:
        if _chapas.MARCA_CHAPA not in ativo:
            return None          # quem vai ate' o alvo e' UMA peca, nao um modulo
        if not medir:
            return ('conectar', ativo, alvos)
        _pontos, perto = _alvos_por_distancia(ativo, alvos)
        if perto:
            return ('conectar', ativo, alvos)
        return ('vertices', ativo, alvos)
    if _chapas.MARCA_CHAPA in ativo and chapas == [ativo] and not any(
            _chapas.MARCA_CONJUNTO in o for o in selecionados):
        if agregado(ativo) or modulo is not None:
            return ('desagregar', ativo, [ativo])
        return ('vertices', ativo, [])
    pecas = (_modulos._chapas_do_conjunto(modulo) if modulo is not None
             else [c for c in chapas if c in grupo])
    if not pecas:
        return None
    return ('grupo', None, pecas)


def _estado_corrente_objeto(context):
    """True (azul: o clique desagrega) / False (cinza: o clique associa) /
    None (nada que a corrente faca com esta selecao)."""
    acao = _acao_corrente(context, medir=False)
    if acao is None:
        return None
    return acao[0] in ('grupo', 'desagregar')


def _perguntar_desagregar(context, pecas, todos):
    _desagregar_pendente[0] = sorted(o.name for o in pecas)
    op = 'object.cabinet_desagregar_selecao'
    _perguntas._perguntar(context, PERGUNTA_DESAGREGAR_GRUPO if todos
               else PERGUNTA_DESAGREGAR_OBJETO,
               [('Sim, desagregar', 'CHECKMARK', op, {'desagregar': True}),
                ('Nao', 'X', op, {'desagregar': False})])


def _agrupar_soltas(context, C, pecas):
    """A Corrente juntou pecas que nao estao em armario nenhum: viram um
    GRUPO (pedido do usuario). Com armario de um lado, quem manda e' o
    "Juntar ao modulo?" -- aqui nada acontece. Devolve o grupo ou None."""
    pecas = {N for N in pecas if N is not None and _chapas.MARCA_CHAPA in N}
    if (C is None or not pecas or _portas._modulo_da_chapa(C) is not None
            or any(_portas._modulo_da_chapa(N) is not None for N in pecas)):
        return None
    todas = {C} | pecas | set(_modulos.grupo_de(C, simetrico=True))
    return _modulos.agrupar_chapas(context, sorted(todas, key=lambda o: o.name))


# Caixa do nome na gaveta: o grupo ja' nasceu com a sugestao; o texto
# digitado aqui o renomeia (Enter/OK) ou fica a sugestao (Esc/Manter).
_nome_grupo_gaveta = [None]     # {'grupo', 'texto', 'cursor', 'selecionado'}


def _abrir_caixa_nome(conj):
    _nome_grupo_gaveta[0] = {'grupo': conj.name, 'texto': conj.name,
                             'cursor': len(conj.name), 'selecionado': True}
    _perguntas._pergunta_atual[0] = {
        'texto': 'Nome do grupo', 'campo': True, 'na_gaveta': True,
        'opcoes': [('OK', 'CHECKMARK', 'object.cabinet_nomear_grupo',
                    {'digitado': True}),
                   ('Manter', 'X', 'object.cabinet_nomear_grupo',
                    {'manter': True})]}


def _pedir_nome_grupo(context, conj, na_gaveta=None):
    """Pergunta o nome do grupo novo no lugar certo: caixa com campo
    DENTRO da gaveta se o clique veio dela, pop-up se veio da viewport."""
    na_gaveta = _perguntas._na_gaveta[0] if na_gaveta is None else na_gaveta
    if na_gaveta:
        _abrir_caixa_nome(conj)
        if _perguntas._abrir_pergunta(context):
            bpy.ops.object.cabinet_digitar_nome_grupo('INVOKE_DEFAULT')
        _eventos._redesenhar_viewports(context)
    elif _perguntas._abrir_pergunta(context):
        bpy.ops.object.cabinet_nomear_grupo('INVOKE_DEFAULT', grupo=conj.name,
                                            nome=conj.name)


class OBJECT_OT_nomear_grupo(Operator):
    """Da' nome ao grupo (armario): o Empty e a Collection dele"""
    bl_idname = 'object.cabinet_nomear_grupo'
    bl_label = 'Nome do Grupo'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    grupo: StringProperty(options={'SKIP_SAVE', 'HIDDEN'})
    nome: StringProperty(name='Nome', options={'SKIP_SAVE'})
    # OK da caixa da gaveta: vale o texto digitado nela
    digitado: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})
    # "Manter" da caixa: fica a sugestao, so' fecha
    manter: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def execute(self, context):
        estado = _nome_grupo_gaveta[0]
        if self.digitado or self.manter:
            _nome_grupo_gaveta[0] = None
            if estado is None:
                return {'CANCELLED'}
            self.grupo = estado['grupo']
            self.nome = estado['texto'] if self.digitado else ''
        _eventos._redesenhar_viewports(context)
        if self.manter:
            return {'FINISHED'}
        if not _modulos.nomear_grupo(bpy.data.objects.get(self.grupo), self.nome):
            return {'CANCELLED'}
        return {'FINISHED'}


class OBJECT_OT_digitar_nome_grupo(Operator):
    """Digita o nome do grupo na caixa da gaveta (Enter confirma, Esc mantem)"""
    bl_idname = 'object.cabinet_digitar_nome_grupo'
    bl_label = 'Digitar Nome do Grupo'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        if _nome_grupo_gaveta[0] is None:
            return {'CANCELLED'}
        self._area = context.area
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _redesenhar(self, context):
        _eventos._redesenhar_viewports(context)

    def modal(self, context, event):
        estado = _nome_grupo_gaveta[0]
        if estado is None:
            # respondida pelos botoes da caixa (cada um com o seu undo)
            self._redesenhar(context)
            return {'CANCELLED'}
        if event.value != 'PRESS' or event.type in {
                'LEFTMOUSE', 'MIDDLEMOUSE', 'RIGHTMOUSE', 'WHEELUPMOUSE',
                'WHEELDOWNMOUSE', 'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            # o clique vai para a gaveta (OK / Manter) e para a viewport
            return {'PASS_THROUGH'}
        if event.type == 'ESC':
            _nome_grupo_gaveta[0] = _perguntas._pergunta_atual[0] = None
            self._redesenhar(context)
            return {'CANCELLED'}
        if event.type in {'RET', 'NUMPAD_ENTER'}:
            _nome_grupo_gaveta[0] = _perguntas._pergunta_atual[0] = None
            _orcamento._confirmar_campo_gaveta(estado)
            self._redesenhar(context)
            return {'FINISHED'}
        entrada = (context.window_manager.clipboard
                   if event.ctrl and event.type == 'V'
                   else '' if event.ctrl else event.unicode or '')
        if _gaveta_desenho._tecla_no_texto(estado, event.type, entrada, event.ctrl):
            self._redesenhar(context)
        return {'RUNNING_MODAL'}


def _perguntar_juntar(context, origem, alvos, pecas, na_gaveta=None):
    _conexao_pendente[0] = {'origem': origem.name,
                            'alvos': [(s, tuple(q)) for s, q in alvos],
                            'pecas': sorted(o.name for o in pecas)}
    op = 'object.cabinet_juntar_modulo'
    _perguntas._perguntar(context, 'Juntar ao modulo?',
               [('Sim, juntar', 'CHECKMARK', op, {'juntar': True}),
                ('Nao', 'X', op, {'juntar': False})], na_gaveta)


def _nomes(objs):
    return json.dumps([o.name for o in objs])


def _objetos_dos_nomes(texto):
    """Lista de objetos de um JSON de nomes; None se vazio (= todos)."""
    if not texto:
        return None
    try:
        nomes = json.loads(texto)
    except ValueError:
        return None
    return [o for o in (bpy.data.objects.get(n) for n in nomes) if o is not None]


class OBJECT_OT_corrente_objeto(Operator):
    """Corrente: agrega ou desagrega pela selecao (azul = agregado). Alvos primeiro, peca de fora por ultimo"""
    bl_idname = OP_CORRENTE_OBJETO
    bl_label = 'Corrente'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.mode == 'OBJECT' and _conexao_manual[0] is None
                and _estado_corrente_objeto(context) is not None)

    def invoke(self, context, event):
        acao = _acao_corrente(context)
        if acao is None:
            self.report({'WARNING'}, 'Selecione a peca (ou os alvos e, por '
                        'ultimo, a peca de fora)')
            return {'CANCELLED'}
        tipo, peca, pecas = acao
        if tipo in ('grupo', 'desagregar'):
            _perguntar_desagregar(context, pecas, tipo == 'grupo')
            return {'FINISHED'}
        if tipo == 'conectar':
            return bpy.ops.object.cabinet_conectar_distancia(
                origem=peca.name, alvos=_nomes(pecas))
        return bpy.ops.object.cabinet_conectar_vertices(
            'INVOKE_DEFAULT', origem=peca.name,
            destinos=_nomes(pecas) if pecas else '')

    def execute(self, context):
        return self.invoke(context, None)


class OBJECT_OT_desagregar_selecao(Operator):
    """Resposta do "tem certeza?": desagrega a peca ou o grupo inteiro"""
    bl_idname = 'object.cabinet_desagregar_selecao'
    bl_label = 'Desagregar'
    bl_options = {'REGISTER', 'UNDO'}

    desagregar: BoolProperty(default=True, options={'SKIP_SAVE'})

    def execute(self, context):
        nomes, _desagregar_pendente[0] = _desagregar_pendente[0], None
        if not nomes or not self.desagregar:
            return {'CANCELLED'}
        pecas = [o for o in (bpy.data.objects.get(n) for n in nomes)
                 if o is not None and _chapas.MARCA_CHAPA in o]
        if not pecas:
            return {'CANCELLED'}
        n = desagregar_grupo(pecas)
        self.report({'INFO'}, '%d peca(s) desagregada(s)' % n)
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


class OBJECT_OT_conectar_distancia(Operator):
    """Liga a peca as vizinhas ao alcance (ate' 5 mm)"""
    bl_idname = 'object.cabinet_conectar_distancia'
    bl_label = 'Conectar por Distancia'
    bl_options = {'REGISTER', 'UNDO'}

    origem: StringProperty(options={'SKIP_SAVE'})
    # JSON com os nomes dos alvos selecionados; vazio = qualquer chapa
    alvos: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        chapa = bpy.data.objects.get(self.origem)
        if chapa is None:
            return {'CANCELLED'}
        alvos, pecas = _alvos_por_distancia(chapa,
                                            _objetos_dos_nomes(self.alvos))
        if not pecas:
            self.report({'WARNING'}, 'Nenhuma peca ao alcance')
            return {'CANCELLED'}
        modulo = next((m for m in (_portas._modulo_da_chapa(N) for N in pecas)
                       if m is not None), None)
        if modulo is not None and _portas._modulo_da_chapa(chapa) != modulo:
            _perguntar_juntar(context, chapa, alvos, pecas)
        else:
            _chapas.associar_por_distancia(chapa, pecas, _chapas.ALCANCE_CONEXAO_AUTOMATICA)
            conj = _agrupar_soltas(context, chapa, pecas)
            if conj is not None:
                _pedir_nome_grupo(context, conj)
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


class OBJECT_OT_recalcular_ancoragem(Operator):
    """Refaz as soldas das chapas selecionadas pelo lugar onde estao agora
(copias do Ctrl+D ganham identidade propria)"""
    bl_idname = 'object.cabinet_recalcular_ancoragem'
    bl_label = 'Recalcular Ancoragem'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(_chapas_selecionadas(context))

    def execute(self, context):
        chapas = _chapas_selecionadas(context)
        context.view_layer.update()         # posicoes de agora (invariante 6)
        n = _chapas.recalcular_ancoragem(chapas)
        _eventos._redesenhar_viewports(context)
        self.report({'INFO'}, "%d solda(s) refeita(s) em %d chapa(s)"
                    % (n, len(chapas)))
        return {'FINISHED'}


class OBJECT_OT_juntar_modulo(Operator):
    """Resposta do "Juntar ao modulo?": puxa a peca ate' o alvo (que fica parado)"""
    bl_idname = 'object.cabinet_juntar_modulo'
    bl_label = 'Juntar ao Modulo'
    bl_options = {'REGISTER', 'UNDO'}

    juntar: BoolProperty(default=True, options={'SKIP_SAVE'})

    def execute(self, context):
        pendente, _conexao_pendente[0] = _conexao_pendente[0], None
        if not pendente:
            return {'CANCELLED'}
        chapa = bpy.data.objects.get(pendente['origem'])
        if chapa is None:
            return {'CANCELLED'}
        pecas = {bpy.data.objects.get(n) for n in pendente['pecas']}
        juntar_conexao(chapa, [(s, Vector(q)) for s, q in pendente['alvos']],
                       pecas, self.juntar)
        if self.juntar:
            conj = _agrupar_soltas(context, chapa, pecas)
            if conj is not None:
                _pedir_nome_grupo(context, conj)
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


class OBJECT_OT_confirmar_conexao(Operator):
    """Termina a escolha de vertices (o mesmo que Enter)"""
    bl_idname = 'object.cabinet_confirmar_conexao'
    bl_label = 'Confirmar Conexao'

    @classmethod
    def poll(cls, context):
        return _conexao_manual[0] is not None

    def execute(self, context):
        _conexao_manual[0]['confirmar'] = True
        # confirmado pelo botao da gaveta: "Juntar ao modulo?" vem nela
        _conexao_manual[0]['pela_gaveta'] = _perguntas._na_gaveta[0]
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


def _desenhar_conexao_manual():
    """Cantos clicaveis, o escolhido e as pontas ja' conectadas."""
    estado = _conexao_manual[0]
    regiao = getattr(bpy.context, 'region', None)
    if estado is None or regiao is None or regiao.as_pointer() != estado['regiao']:
        return
    rv3d = bpy.context.region_data
    realce = _hud._cor_realce_hud()
    cor = _hud._cor_linhas_hud(bpy.context)
    escala = max(1.0, bpy.context.preferences.system.ui_scale)

    def tela(ponto):
        return view3d_utils.location_3d_to_region_2d(regiao, rv3d, ponto)

    def bolinha(ponto, raio, rgba):
        p = tela(ponto)
        if p is None:
            return
        volta = [p + Vector((math.cos(i * math.tau / 16),
                             math.sin(i * math.tau / 16))) * raio
                 for i in range(17)]
        tris = []
        for a, b in zip(volta, volta[1:]):
            tris += [p, a, b]
        shader.uniform_float('color', rgba)
        batch_for_shader(shader, 'TRIS', {'pos': tris}).draw(shader)

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        for _obj, _s, ponto in _candidatos_conexao(estado):
            bolinha(ponto, 4 * escala, (*cor[:3], 0.8))
        for s, nome, sn in estado['pares']:
            origem = bpy.data.objects.get(estado['origem'])
            alvo = bpy.data.objects.get(nome)
            if origem is None or alvo is None:
                continue
            a = tela(_canto_da_assinatura(origem, s))
            b = tela(_canto_da_assinatura(alvo, sn))
            if a is not None and b is not None:
                shader.uniform_float('color', realce)
                batch_for_shader(shader, 'TRIS', {'pos': _puxadores._quad_2d(
                    a, b, 2.0 * escala)}).draw(shader)
                bolinha(_canto_da_assinatura(origem, s), 6 * escala, realce)
                bolinha(_canto_da_assinatura(alvo, sn), 6 * escala, realce)
        if estado.get('escolhido'):
            bolinha(estado['escolhido'][1], 7 * escala, realce)
        if estado.get('hover'):
            bolinha(estado['hover'][2], 7 * escala, (*realce[:3], 0.6))
    finally:
        gpu.state.blend_set('NONE')


def _candidatos_conexao(estado):
    """[(objeto, assinatura, ponto)] clicaveis na fase atual: os cantos da
    chapa de origem, ou os das outras chapas (o destino)."""
    origem = bpy.data.objects.get(estado['origem'])
    if origem is None:
        return []
    if estado['fase'] == 'origem':
        pecas = [origem]
    else:
        # alvos selecionados antes da peca de fora: so' os cantos deles
        destinos = _objetos_dos_nomes(estado.get('destinos'))
        pecas = [o for o in (bpy.data.objects if destinos is None else destinos)
                 if o is not origem and o.type == 'MESH' and _chapas.MARCA_CHAPA in o
                 and o.visible_get()]
    return [(o, _assinatura_canto(o, p), p) for o in pecas for p in _chapas._cantos(o)]


class OBJECT_OT_conectar_vertices(Operator):
    """Selecionar vertice: clique no canto da chapa e depois no canto onde ela deve grudar. Enter confirma"""
    bl_idname = 'object.cabinet_conectar_vertices'
    bl_label = 'Selecionar Vertice'
    bl_options = {'REGISTER'}

    origem: StringProperty(options={'SKIP_SAVE'})
    # JSON com os nomes dos alvos; vazio = cantos de qualquer chapa
    destinos: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and _conexao_manual[0] is None

    def invoke(self, context, event):
        chapa = (bpy.data.objects.get(self.origem) if self.origem
                 else context.object)
        if chapa is None or _chapas.MARCA_CHAPA not in chapa:
            self.report({'WARNING'}, 'Selecione a chapa de origem')
            return {'CANCELLED'}
        alvo = _importacao._viewport_alvo(context)
        if alvo is None:
            self.report({'ERROR'}, 'Sem viewport 3D para clicar')
            return {'CANCELLED'}
        self._area, self._regiao, self._rv3d = alvo
        _conexao_manual[0] = {'origem': chapa.name, 'pares': [],
                              'destinos': self.destinos,
                              'fase': 'origem', 'escolhido': None,
                              'hover': None, 'confirmar': False,
                              'regiao': self._regiao.as_pointer()}
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            _desenhar_conexao_manual, (), 'WINDOW', 'POST_PIXEL')
        self._area.header_text_set(
            "Selecionar vertice: canto da chapa, depois onde ela gruda | "
            "Enter: confirmar | Botao direito: desfazer | Esc: cancelar")
        context.window_manager.modal_handler_add(self)
        _eventos._redesenhar_viewports(context)
        return {'RUNNING_MODAL'}

    def _encerrar(self, context):
        try:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
        except Exception:
            pass
        self._area.header_text_set(None)
        estado, _conexao_manual[0] = _conexao_manual[0], None
        _eventos._redesenhar_viewports(context)
        return estado

    def _na_viewport(self, event):
        dx, dy = event.mouse_x - self._regiao.x, event.mouse_y - self._regiao.y
        return 0 <= dx < self._regiao.width and 0 <= dy < self._regiao.height

    def _sob_mouse(self, event):
        mouse = Vector((event.mouse_x - self._regiao.x,
                        event.mouse_y - self._regiao.y))
        raio = RAIO_VERTICE_PX * max(1.0, bpy.context.preferences.system.ui_scale)
        melhor = None
        for obj, s, ponto in _candidatos_conexao(_conexao_manual[0]):
            p = view3d_utils.location_3d_to_region_2d(self._regiao, self._rv3d,
                                                      ponto)
            if p is None:
                continue
            d = (p - mouse).length
            if d <= raio and (melhor is None or d < melhor[0]):
                melhor = (d, (obj, s, ponto))
        return melhor[1] if melhor else None

    def _terminar(self, context):
        estado = self._encerrar(context)
        origem = bpy.data.objects.get(estado['origem'])
        if origem is None or not estado['pares']:
            return {'CANCELLED'}
        alvos = [(s, _canto_da_assinatura(bpy.data.objects[nome], sn))
                 for s, nome, sn in estado['pares']
                 if nome in bpy.data.objects]
        pecas = {bpy.data.objects.get(nome) for _s, nome, _sn in estado['pares']}
        _perguntar_juntar(context, origem, alvos, pecas,
                          estado.get('pela_gaveta', False))
        return {'FINISHED'}

    def modal(self, context, event):
        estado = _conexao_manual[0]
        if estado is None:
            return {'CANCELLED'}
        if estado.get('confirmar'):
            return self._terminar(context)
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            return self._terminar(context)
        if event.type == 'ESC' and event.value == 'PRESS':
            self._encerrar(context)
            return {'CANCELLED'}
        if not self._na_viewport(event):
            return {'PASS_THROUGH'}     # a gaveta (Confirmar) segue viva
        if event.type == 'MOUSEMOVE':
            estado['hover'] = self._sob_mouse(event)
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            if estado['fase'] == 'destino':
                estado.update(fase='origem', escolhido=None)
            elif estado['pares']:
                estado['pares'].pop()
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            alvo = self._sob_mouse(event)
            if alvo is not None:
                obj, s, ponto = alvo
                if estado['fase'] == 'origem':
                    estado.update(fase='destino', escolhido=(s, ponto))
                else:
                    estado['pares'].append((estado['escolhido'][0],
                                            obj.name, s))
                    estado.update(fase='origem', escolhido=None)
                estado['hover'] = None
                self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._encerrar(context)


def _desenhar_bolinhas_correntes(context):
    """Bolinha branca em cada ponta das linhas das correntes (Alt): e' a
    ancora, arrastavel; a sob o mouse cresce e ganha o realce."""
    correntes = _correntes_hud(context)
    if not correntes or _arraste_ancora[0] is not None:
        return
    escala = max(1.0, context.preferences.system.ui_scale)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    shader.bind()
    realce = _hud._cor_realce_hud()
    for corrente in correntes:
        for lado, ponto in _bolinhas_da_corrente(context, corrente).items():
            acesa = _chave_bolinha(corrente, lado) == _bolinha_hover[0]
            if acesa:
                _hud._bolinha_2d(shader, ponto, 8 * escala, realce)
            _hud._bolinha_2d(shader, ponto, (6 if acesa else 5) * escala,
                        (1.0, 1.0, 1.0, 1.0))


# ------------------------------------------------ arrastar a ancora
_arraste_ancora = [None]         # estado do arraste da bolinha


def _candidatos_ancora(estado):
    """[(assinatura, ponto)] dos vertices onde a bolinha pode cair: os da
    chapa (lado 'a', QUAL vertice e' soldado) ou os do vizinho (lado
    'b', ONDE ele encosta)."""
    C = bpy.data.objects.get(estado['chapa'])
    N = _vizinho_da_ponta(C, estado['ponta']) if C is not None else None
    if N is None:
        return []
    return _ancoras_da_malha(C if estado['lado'] == 'a' else N)


def _desenhar_arraste_ancora():
    estado = _arraste_ancora[0]
    regiao = getattr(bpy.context, 'region', None)
    if estado is None or regiao is None or regiao.as_pointer() != estado['regiao']:
        return
    rv3d = bpy.context.region_data
    escala = max(1.0, bpy.context.preferences.system.ui_scale)
    realce = _hud._cor_realce_hud()
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    tela = lambda p: view3d_utils.location_3d_to_region_2d(regiao, rv3d, p)
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        for _s, ponto in _candidatos_ancora(estado):
            p = tela(ponto)
            if p is not None:
                _hud._bolinha_2d(shader, p, 4 * escala, (0.75, 0.75, 0.75, 0.9))
        fixo = tela(estado['fixo'])
        solto = estado['mouse']
        if estado.get('alvo'):
            solto = tela(dict(_candidatos_ancora(estado))[estado['alvo']]) or solto
        if fixo is not None:
            shader.uniform_float('color', realce)
            batch_for_shader(shader, 'TRIS', {'pos': _puxadores._quad_2d(
                fixo, solto, 3.0 * escala)}).draw(shader)
            _hud._bolinha_2d(shader, fixo, 5 * escala, (1.0, 1.0, 1.0, 1.0))
        _hud._bolinha_2d(shader, solto, 8 * escala, realce)
        _hud._bolinha_2d(shader, solto, 6 * escala, (1.0, 1.0, 1.0, 1.0))
    finally:
        gpu.state.blend_set('NONE')


class OBJECT_OT_arrastar_ancora(Operator):
    """Arraste a bolinha da corrente ate' outro vertice: troca a ancora da solda (a chapa vai la' pela regua)"""
    bl_idname = 'object.cabinet_arrastar_ancora'
    bl_label = 'Ajustar Ancora da Solda'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    chapa: StringProperty(options={'SKIP_SAVE'})
    ponta: StringProperty(options={'SKIP_SAVE'})
    indice: IntProperty(options={'SKIP_SAVE'})
    lado: StringProperty(default='b', options={'SKIP_SAVE'})

    def invoke(self, context, event):
        C = bpy.data.objects.get(self.chapa)
        N = _vizinho_da_ponta(C, self.ponta) if C is not None else None
        if N is None or context.region is None:
            return {'CANCELLED'}
        ancoras = _ancoras_da_ligacao(C, self.ponta, N)
        if not 0 <= self.indice < len(ancoras):
            return {'CANCELLED'}
        sc, sn = ancoras[self.indice]
        outra = (N, sn) if self.lado == 'a' else (C, sc)
        _arraste_ancora[0] = {
            'regiao': context.region.as_pointer(), 'chapa': C.name,
            'ponta': self.ponta, 'lado': self.lado, 'alvo': None,
            'fixo': _vertice_da_assinatura(*outra),
            'mouse': Vector((event.mouse_region_x, event.mouse_region_y))}
        self._area = context.area
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            _desenhar_arraste_ancora, (), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _encerrar(self):
        try:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
        except Exception:
            pass
        estado, _arraste_ancora[0] = _arraste_ancora[0], None
        self._area.tag_redraw()
        return estado

    def cancel(self, context):
        self._encerrar()

    def _imantar(self, context, mouse):
        """Assinatura do vertice candidato sob o mouse (ima por TELA)."""
        raio = RAIO_VERTICE_PX * max(1.0, context.preferences.system.ui_scale)
        melhor = None
        for assinatura, ponto in _candidatos_ancora(_arraste_ancora[0]):
            p = _hud._projetar_hud(context, ponto)
            if p is None:
                continue
            d = (p - mouse).length
            if d <= raio and (melhor is None or d < melhor[0]):
                melhor = (d, assinatura)
        return melhor[1] if melhor else None

    def modal(self, context, event):
        estado = _arraste_ancora[0]
        if estado is None:
            return {'CANCELLED'}
        mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self._encerrar()
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            estado['mouse'] = mouse
            estado['alvo'] = self._imantar(context, mouse)
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            alvo = self._imantar(context, mouse) or estado.get('alvo')
            self._encerrar()
            if alvo is None:
                return {'CANCELLED'}
            return self._gravar(alvo)
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def _gravar(self, alvo):
        C = bpy.data.objects.get(self.chapa)
        N = _vizinho_da_ponta(C, self.ponta) if C is not None else None
        if N is None:
            return {'CANCELLED'}
        ancoras = list(_ancoras_da_ligacao(C, self.ponta, N))
        sc, sn = ancoras[self.indice]
        novo = (alvo, sn) if self.lado == 'a' else (sc, alvo)
        if novo == ancoras[self.indice]:
            return {'CANCELLED'}
        ancoras[self.indice] = novo
        _gravar_ancoras(C, self.ponta, ancoras)
        self.report({'INFO'}, 'Ancora trocada; a regua leva a chapa ate' + "' la'")
        return {'FINISHED'}


# ------------------------------------------ resetar distancia
# Pedido do usuario: "volta para a origem da solda". O botao da gaveta
# (regua) fica AZUL quando a peca/modulo ativo tem solda fora da origem
# (folga diferente da gravada). Quem se mexe sai da SELECAO:
# - chapa unica ativa: ELA se move ate' todas as soldas dela voltarem; se
#   para isso precisar mudar de medida (o modulo mudou muito), pergunta;
# - modulo (grupo) ativo: o GRUPO se adapta a chapa -- as pontas soldadas
#   esticam ate' ela, e o modulo se redimensiona se preciso.
# Na viewport (Alt) a regua de cada quina faz o mesmo, pela peca da linha.
OP_RESETAR_DISTANCIA = 'object.cabinet_resetar_distancia'
TOL_RESET_DISTANCIA = 0.0005     # m: abaixo disto a solda esta' na origem
PERGUNTA_RESET = ('A chapa vai mudar de medida para voltar a solda. '
                  'Mover mesmo assim?')
_pergunta_reset = ['']           # chapa esperando a resposta


def _folga_com_sinal(C, ponta, N):
    """(folga em m, eixo u, extremo) como o `_chapas._melhor_vizinho` grava:
    positiva = afastada, negativa = invadindo o vizinho."""
    eixo, lado = ponta.split('_')
    ex, ey, _ez = _chapas._eixos(C)
    u = ex if eixo == 'x' else ey
    hx, hy, _hz = _chapas._meias(C)
    h = hx if eixo == 'x' else hy
    extremo = _chapas._centro(C).dot(u) + (h if lado == 'pos' else -h)
    face = int(C.get('adj_%s_face' % ponta, 0 if lado == 'pos' else 1))
    alvo = _chapas._faixa(N, u)[face]
    return (alvo - extremo if lado == 'pos' else extremo - alvo), u, extremo


def _pontas_fora_do_lugar(chapas):
    """Soldas que tocam `chapas` fora da origem (qualquer desvio)."""
    return _ligacoes_adjacencia(chapas, TOL_RESET_DISTANCIA)


# ---- ancoras da solda (pedido do usuario)
# Cada solda liga 2 vertices da chapa a 2 vertices do vizinho. De fabrica
# sao os cantos mais perto (`_pares_da_ligacao`); com Alt o usuario arrasta
# a bolinha de cada ponta para outro vertice das duas pecas e a escolha
# fica gravada em `adj_<ponta>_ancoras` ("+-+|-++", chapa|vizinho). So'
# troca a ancora: a chapa vai la' na regua. Vertices que nao cabem na
# mesma reta (um em cima, outro embaixo) DEFORMAM a ponta da chapa: o
# canto e o do outro lado da espessura vao juntos, a chapa fica torta.
def _ancoras_gravadas(C, ponta):
    lista = C.get('adj_%s_ancoras' % ponta)
    if not lista:
        return None
    try:
        ancoras = [tuple(str(x).split('|')) for x in lista]
    except Exception:
        return None
    return ancoras if all(len(a) == 2 for a in ancoras) else None


def _ancoras_da_ligacao(C, ponta, N, u=None, extremo=None):
    """[(assinatura em C, assinatura em N)]: as gravadas ou as de fabrica."""
    gravadas = _ancoras_gravadas(C, ponta)
    if gravadas:
        return gravadas
    if u is None:
        _folga, u, extremo = _folga_com_sinal(C, ponta, N)
    return [(sc, _assinatura_canto(N, q))
            for _p, q, sc in _pares_da_ligacao(C, u, extremo, N)]


def _parceiro_espessura(P, assinatura):
    """A ancora do OUTRO lado da espessura (Z local): no canto, o sinal de
    Z trocado; num vertice qualquer, o mais perto dele na face oposta."""
    if not assinatura.startswith('v'):
        return assinatura[:2] + ('-' if assinatura[2] == '+' else '+')
    indices = _indices_da_assinatura(P, assinatura)
    if not indices:
        return assinatura
    co = P.data.vertices[indices[0]].co
    opostos = [v for v in P.data.vertices if v.co.z * co.z < 0]
    if not opostos:
        return assinatura
    v = min(opostos, key=lambda v: (v.co.x - co.x) ** 2 + (v.co.y - co.y) ** 2)
    return 'v%d' % v.index


def _ancoras_da_malha(P):
    """[(ancora, ponto)] de TODOS os vertices de P onde a bolinha pode
    cair: os 8 cantos da caixa, ou cada vertice da malha modelada (o
    chanfro da print do usuario nao era alcancavel so' com os cantos)."""
    if P.type == 'MESH' and not _chapas._malha_e_caixa(P.data):
        mundo = P.matrix_world
        return [('v%d' % v.index, mundo @ v.co) for v in P.data.vertices]
    return [(s, _vertice_da_assinatura(P, s))
            for s in (a + b + c for a in '+-' for b in '+-' for c in '+-')]


def _gravar_ancoras(C, ponta, ancoras):
    C['adj_%s_ancoras' % ponta] = ['%s|%s' % a for a in ancoras]


# Cada vertice da caixa guarda o canto de ORIGEM num atributo: deformada
# pelas ancoras, um canto pode cruzar a origem da peca (a lateral entorta
# a espessura inteira) e o sinal da coordenada passava a apontar o vertice
# ERRADO (teste: ancora 13,5 mm fora). O atributo anda com o vertice.
ATRIBUTO_CANTO = 'cabinet_canto'


def _codigo_assinatura(assinatura):
    return sum(1 << i for i, c in enumerate(assinatura) if c == '+')


def _gravar_cantos(P):
    """Marca os 8 vertices da caixa com o canto de cada um (pelo lado em
    que estao do centro dela -- vale enquanto ela nao entortou)."""
    malha = getattr(P, 'data', None)
    if malha is None or len(malha.vertices) != 8:
        return
    centro = sum((v.co for v in malha.vertices), Vector()) / 8.0
    atributo = (malha.attributes.get(ATRIBUTO_CANTO)
                or malha.attributes.new(ATRIBUTO_CANTO, 'INT', 'POINT'))
    for v in malha.vertices:
        atributo.data[v.index].value = _codigo_assinatura(''.join(
            '+' if c > m else '-' for c, m in zip(v.co, centro)))


def _indices_da_assinatura(P, assinatura):
    """Indice do vertice da ancora: 'v12' = o vertice 12 da malha (malha
    modelada, ex. o chanfro); canto '+-+' = o do atributo de canto (so' na
    caixa de 8 vertices -- numa malha que ganhou vertices o atributo vem 0
    nos novos); sem ele, pelos sinais no referencial da peca."""
    if P is None or P.type != 'MESH':
        return []
    if assinatura.startswith('v'):
        try:
            indice = int(assinatura[1:])
        except ValueError:
            return []
        return [indice] if 0 <= indice < len(P.data.vertices) else []
    atributo = P.data.attributes.get(ATRIBUTO_CANTO)
    if (atributo is not None and len(P.data.vertices) == 8
            and len(atributo.data) == 8):
        codigo = _codigo_assinatura(assinatura)
        achados = [i for i, d in enumerate(atributo.data) if d.value == codigo]
        if achados:
            return achados[:1]
    sinais = [1.0 if c == '+' else -1.0 for c in assinatura]
    candidatos = [v for v in P.data.vertices
                  if all(c * s > 0 for c, s in zip(v.co, sinais))]
    if not candidatos:
        return []
    return [max(candidatos, key=lambda v: sum(
        c * s for c, s in zip(v.co, sinais))).index]


def _vertice_da_assinatura(P, assinatura):
    """O vertice REAL (mundo) da ancora: a chapa deformada pelas ancoras
    sai do canto nominal das props."""
    indices = _indices_da_assinatura(P, assinatura)
    if not indices:
        if assinatura.startswith('v'):
            return P.matrix_world.translation.copy()   # vertice sumiu
        return _canto_da_assinatura(P, assinatura)
    return P.matrix_world @ P.data.vertices[indices[0]].co


def _medida_solda(C, ponta, N):
    """(delta, residuos) da solda C->N: `delta` = quanto a ponta de C tem
    que andar PARA FORA para voltar a origem; `residuos` = [(assinatura,
    vetor)] do que sobra por vertice quando as ancoras nao cabem numa
    reta (vazio sem ancoras gravadas)."""
    folga, u, _extremo = _folga_com_sinal(C, ponta, N)
    memorizada = float(C.get('adj_%s_folga' % ponta, 0.0))
    ancoras = _ancoras_gravadas(C, ponta)
    if not ancoras:
        return folga - memorizada, []
    sentido = u if ponta.endswith('pos') else -u
    itens = [(sc, _vertice_da_assinatura(N, sn) - sentido * memorizada
              - _vertice_da_assinatura(C, sc)) for sc, sn in ancoras]
    delta = sum(d.dot(sentido) for _s, d in itens) / len(itens)
    return delta, [(sc, d - sentido * delta) for sc, d in itens]


def _tamanho_desvio(delta, residuos):
    return max([abs(delta)] + [r.length for _s, r in residuos])


def _deformar_ancoras(C, ponta, N, lado='a'):
    """Encosta os vertices ancorados: lado 'a' leva os de C (a ponta) ate'
    os do vizinho; lado 'b' leva os de N ate' os de C -- e' a peca que se
    move (a ativa) que entorta. Cada canto vai junto com o do outro lado
    da espessura dele: a espessura nao muda, a chapa fica torta."""
    ancoras = _ancoras_gravadas(C, ponta)
    if not ancoras:
        return False
    _folga, u, _e = _folga_com_sinal(C, ponta, N)
    sentido = u if ponta.endswith('pos') else -u
    memorizada = float(C.get('adj_%s_folga' % ponta, 0.0))
    peca = C if lado == 'a' else N
    if peca.data.attributes.get(ATRIBUTO_CANTO) is None:
        _gravar_cantos(peca)        # malha de versao antiga: marca antes
    inversa = peca.matrix_world.inverted().to_3x3()
    mudou = False
    for sc, sn in ancoras:
        vc = _vertice_da_assinatura(C, sc)
        vn = _vertice_da_assinatura(N, sn)
        if lado == 'a':
            assinatura, d = sc, vn - sentido * memorizada - vc
        else:
            assinatura, d = sn, vc + sentido * memorizada - vn
        if d.length < TOL_RESET_DISTANCIA:
            continue
        local = inversa @ d
        parceiro = _parceiro_espessura(peca, assinatura)
        indices = set(_indices_da_assinatura(peca, assinatura)
                      + _indices_da_assinatura(peca, parceiro))
        for i in indices:
            peca.data.vertices[i].co += local
        mudou = True
    if mudou:
        peca.data.update()
        bpy.context.view_layer.update()
    return mudou


def resetar_ponta(C, ponta):
    """Leva a ponta `ponta` de C ate' a folga memorizada com o vizinho;
    a outra ponta fica parada e a chapa estica (ou encolhe). Com ancoras
    gravadas, estica pela media e deforma o resto (`_deformar_ancoras`)."""
    N = _vizinho_da_ponta(C, ponta)
    if N is None:
        return False
    eixo, lado = ponta.split('_')
    _folga, u, extremo = _folga_com_sinal(C, ponta, N)
    delta, residuos = _medida_solda(C, ponta, N)
    hx, hy, _hz = _chapas._meias(C)
    h = hx if eixo == 'x' else hy
    fixo = extremo - 2 * h if lado == 'pos' else extremo + 2 * h
    novo = extremo + delta * (1 if lado == 'pos' else -1)
    comprimento = abs(novo - fixo)
    if comprimento < 0.001:
        return False
    if abs(delta) < TOL_RESET_DISTANCIA:
        return _deformar_ancoras(C, ponta, N) or bool(residuos)
    centro = _chapas._centro(C)
    _chapas._ocupado[0] = True
    try:
        if eixo == 'x':
            C.chapa_largura_mm = comprimento * 1000.0
        else:
            C.chapa_comprimento_mm = comprimento * 1000.0
    finally:
        _chapas._ocupado[0] = False
    _chapas._definir_centro(C, centro + u * ((novo + fixo) / 2 - centro.dot(u)))
    _chapas.gerar_malha_chapa(C)
    bpy.context.view_layer.update()
    _deformar_ancoras(C, ponta, N)
    return True


def resetar_pontas(escolhidas):
    """[(chapa, ponta)] -> quantas voltaram; os modulos se reacomodam."""
    n, modulos = 0, set()
    for C, ponta in escolhidas:
        if resetar_ponta(C, ponta):
            n += 1
            modulo = _portas._modulo_da_chapa(C)
            if modulo is not None:
                modulos.add(modulo)
    for modulo in modulos:
        _atualizar_modulo(modulo)
    return n


def _restricoes_reset(M):
    """[(eixo de M, 'min'/'max', deslocamento em m)] que cada solda de M
    pede para voltar a origem -- as que ja' estao nela pedem 0 (ancoras).
    Devolve tambem se alguma esta' fora."""
    eixos = _chapas._eixos(M)
    restricoes, fora = [], False
    for C in bpy.data.objects:
        if C.type != 'MESH' or _chapas.MARCA_CHAPA not in C:
            continue
        for ponta in _chapas.PONTAS:
            N = _vizinho_da_ponta(C, ponta)
            if N is None or M not in (C, N):
                continue
            _folga, u, _extremo = _folga_com_sinal(C, ponta, N)
            delta, residuos = _medida_solda(C, ponta, N)
            fora = fora or (_tamanho_desvio(delta, residuos)
                            >= TOL_RESET_DISTANCIA)
            positiva = ponta.endswith('pos')
            sentido = u if positiva else -u      # para fora da ponta de C
            if M is C:
                # a PONTA de M anda ate' a face do vizinho
                i = 0 if ponta[0] == 'x' else 1
                lado = 'max' if positiva else 'min'
                vetor = sentido * delta
            else:
                # a FACE de M anda ate' a ponta do vizinho
                i = max(range(3), key=lambda k: abs(eixos[k].dot(u)))
                face = int(C.get('adj_%s_face' % ponta, 0 if positiva else 1))
                mesmo = eixos[i].dot(u) > 0
                lado = (('min' if face == 0 else 'max') if mesmo
                        else ('max' if face == 0 else 'min'))
                vetor = -sentido * delta
            restricoes.append((i, lado, vetor.dot(eixos[i]),
                               bool(_ancoras_gravadas(C, ponta))))
    return restricoes, fora


def _plano_reset_chapa(M):
    """{'lados': [(d_min, d_max)] por eixo de M, 'muda_medida'} para M
    voltar as soldas a origem, ou None se ja' estao todas nela. Lados
    opostos pedindo deslocamentos diferentes = esticar (muda a medida);
    a espessura nunca estica: ali vale a media."""
    restricoes, fora = _restricoes_reset(M)
    if not fora:
        return None
    lados, muda = [], False
    def do_lado(i, qual):
        # Num mesmo lado, as soldas NORMAIS mandam no movimento inteiro; as
        # ancoradas so' valem se forem as unicas -- o resto delas a
        # deformacao resolve. Media das duas tirava a base do lugar para
        # atender meio caminho do tampo ancorado.
        todas = [(d, ancorada) for k, lado, d, ancorada in restricoes
                 if k == i and lado == qual]
        normais = [d for d, ancorada in todas if not ancorada]
        return normais or [d for d, _a in todas]

    for i in range(3):
        mins = do_lado(i, 'min')
        maxs = do_lado(i, 'max')
        d_min = sum(mins) / len(mins) if mins else None
        d_max = sum(maxs) / len(maxs) if maxs else None
        if d_min is None and d_max is None:
            lados.append((0.0, 0.0))
            continue
        d_min = d_max if d_min is None else d_min
        d_max = d_min if d_max is None else d_max
        if abs(d_max - d_min) >= TOL_RESET_DISTANCIA:
            if i == 2:
                d_min = d_max = (d_min + d_max) / 2
            else:
                muda = True
        lados.append((d_min, d_max))
    return {'lados': lados, 'muda_medida': muda}


def _aplicar_reset_chapa(M, plano):
    eixos = _chapas._eixos(M)
    centro = _chapas._centro(M)
    medidas = [M.chapa_largura_mm, M.chapa_comprimento_mm]
    for i, (d_min, d_max) in enumerate(plano['lados']):
        centro = centro + eixos[i] * ((d_min + d_max) / 2)
        if i < 2:
            medidas[i] += (d_max - d_min) * 1000.0
    _chapas._ocupado[0] = True
    try:
        M.chapa_largura_mm, M.chapa_comprimento_mm = medidas
    finally:
        _chapas._ocupado[0] = False
    _chapas._definir_centro(M, centro)
    _chapas.gerar_malha_chapa(M)
    bpy.context.view_layer.update()
    # o que as ancoras pedem e a translacao nao resolve: DEFORMA a peca
    # que se move -- a ponta dela, ou a face dela se ela e' o vizinho
    for C in bpy.data.objects:
        if C.type != 'MESH' or _chapas.MARCA_CHAPA not in C:
            continue
        for ponta in _chapas.PONTAS:
            N = _vizinho_da_ponta(C, ponta)
            if N is not None and M in (C, N):
                _deformar_ancoras(C, ponta, N, 'a' if M is C else 'b')
    modulo = _portas._modulo_da_chapa(M)
    if modulo is not None:
        _atualizar_modulo(modulo)


def _soldas_de(P):
    """Quantas soldas P tem e quantas estao fora da origem."""
    total = fora = 0
    for C in bpy.data.objects:
        if C.type != 'MESH' or _chapas.MARCA_CHAPA not in C:
            continue
        for ponta in _chapas.PONTAS:
            N = _vizinho_da_ponta(C, ponta)
            if N is None or P not in (C, N):
                continue
            total += 1
            if _tamanho_desvio(*_medida_solda(C, ponta, N)) >= TOL_RESET_DISTANCIA:
                fora += 1
    return total, fora


def _peca_afastada(a, b):
    """Das duas pecas da solda, a que se AFASTOU: todas as soldas dela
    estao fora da origem (na print do usuario, a lateral)."""
    def razao(P):
        total, fora = _soldas_de(P)
        return fora / total if total else 0.0
    return a if razao(a) > razao(b) else b


def _peca_da_regua(context, a, b):
    """A peca que a regua da linha a-b passa ao reset: a chapa unica
    ativa, se for uma das duas; senao a que se afastou."""
    alvo = _hud._alvo_hud(context)
    if alvo is not None and alvo[1] == 'INDIVIDUAL' and alvo[0] in (a, b):
        return alvo[0]
    return _peca_afastada(a, b)


def _modo_reset(context, nome=''):
    """('CHAPA', M, None) ou ('GRUPO', pecas, foco) pela selecao ativa;
    `nome` = a peca da linha clicada na viewport. None sem item."""
    alvo = _hud._alvo_hud(context)
    foco = bpy.data.objects.get(nome) if nome else None
    if alvo is None:
        if foco is not None and _chapas.MARCA_CHAPA in foco:
            return ('CHAPA', foco, None)
        return None
    obj, modo, chapas = alvo
    if modo == 'INDIVIDUAL':
        return ('CHAPA', foco if foco is not None else obj, None)
    return ('GRUPO', chapas, foco)


def _soldas_do_grupo(pecas, foco=None):
    ligacoes = _pontas_fora_do_lugar(pecas)
    if foco is not None:
        ligacoes = [l for l in ligacoes if foco in (l['a'], l['b'])]
    return ligacoes


def _estado_resetar(context):
    """True (azul: ha' solda fora da origem) ou None (apagado)."""
    try:
        modo = _modo_reset(context)
    except (ReferenceError, AttributeError):
        return None
    if modo is None:
        return None
    if modo[0] == 'CHAPA':
        return True if _plano_reset_chapa(modo[1]) is not None else None
    return True if _soldas_do_grupo(modo[1]) else None


class OBJECT_OT_resetar_distancia(Operator):
    """Resetar distancia: volta as soldas para a origem. Chapa ativa: ela se move; modulo ativo: o modulo se adapta a chapa"""
    bl_idname = OP_RESETAR_DISTANCIA
    bl_label = 'Resetar Distancia'
    bl_options = {'REGISTER', 'UNDO'}

    chapa: StringProperty(options={'SKIP_SAVE'})
    forcar: BoolProperty(options={'SKIP_SAVE'})
    cancelar: BoolProperty(options={'SKIP_SAVE'})
    # Chamado de um PRESS (regua com Alt): o `event` do bpy.ops ja' pode
    # trazer o RELEASE do mesmo clique (visto no log), entao quem chama
    # avisa que o soltar ainda vem.
    esperar_soltar: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and _conexao_manual[0] is None

    def _vai_perguntar(self, context):
        modo = _modo_reset(context, self.chapa)
        if self.forcar or modo is None or modo[0] != 'CHAPA':
            return False
        plano = _plano_reset_chapa(modo[1])
        return bool(plano and plano['muda_medida'])

    def invoke(self, context, event):
        # Pop-up aberto no PRESS nasce sob o mouse e o RELEASE do mesmo
        # clique ja' responde (visto no botao Corrente): espera o soltar.
        apertando = self.esperar_soltar or (
            event is not None and event.type == 'LEFTMOUSE'
            and event.value == 'PRESS')
        if apertando and self._vai_perguntar(context):
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        return self.execute(context)

    def modal(self, context, event):
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return self.execute(context)
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            return {'CANCELLED'}
        return {'PASS_THROUGH'}

    def execute(self, context):
        if self.cancelar:
            _pergunta_reset[0] = ''
            return {'CANCELLED'}
        modo = _modo_reset(context, self.chapa)
        if modo is None:
            self.report({'WARNING'}, 'Selecione a chapa ou o modulo')
            return {'CANCELLED'}
        if modo[0] == 'CHAPA':
            M = modo[1]
            plano = _plano_reset_chapa(M)
            if plano is None:
                self.report({'INFO'}, "As soldas ja' estao na origem")
                return {'CANCELLED'}
            if plano['muda_medida'] and not self.forcar:
                _pergunta_reset[0] = M.name
                _perguntas._perguntar(context, PERGUNTA_RESET, [
                    ('Sim, mover', 'CHECKMARK', OP_RESETAR_DISTANCIA,
                     {'chapa': M.name, 'forcar': True}),
                    ('Nao', 'X', OP_RESETAR_DISTANCIA, {'cancelar': True})])
                return {'CANCELLED'}
            _pergunta_reset[0] = ''
            _aplicar_reset_chapa(M, plano)
            self.report({'INFO'}, '%s voltou a origem da solda' % M.name)
        else:
            ligacoes = _soldas_do_grupo(modo[1], modo[2])
            if not ligacoes:
                self.report({'INFO'}, "As soldas ja' estao na origem")
                return {'CANCELLED'}
            n = resetar_pontas([(l['a'], l['ponta']) for l in ligacoes])
            self.report({'INFO'}, '%d ponta(s) voltaram a solda' % n)
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}
