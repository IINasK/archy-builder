"""Modulo (conjunto): medidas, redimensionar, agrupar em Empty +
Collection, medidas da selecao livre e do grupo da cena."""

import bpy
from bpy.props import StringProperty
from mathutils import Matrix, Vector
from bpy.types import Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _portas = _gaveta = None

# ================================================= MODULO (CONJUNTO)
# Ao agrupar, o Empty deixa de ser so' um pai e passa a ter as medidas
# do modulo: largura, altura, profundidade e espessura.
#
# Regra: as medidas EXTERNAS mandam. Ao mudar qualquer uma delas, as
# pecas se acomodam por dentro mantendo a espessura discreta, e a
# adjacencia fecha as juntas. Ao mudar a ESPESSURA, o contorno externo
# nao se mexe: as chapas engrossam/afinam para dentro e as pecas que
# vao de uma ponta a outra se contraem ou se expandem para acompanhar.
TOL_BORDA = 0.0015   # 1.5mm: tolerancia para considerar face "no limite"


def _chapas_do_conjunto(conj):
    return [o for o in bpy.data.objects
            if o.parent == conj and o.type == 'MESH' and _chapas.MARCA_CHAPA in o]


def _caixa_de(chapas):
    """Bounding box em mundo de uma lista qualquer de chapas.
    Atualiza o depsgraph antes: matrix_world so' fica correto depois do
    recalculo, e ler antes devolvia a caixa da operacao ANTERIOR."""
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    pts = []
    for o in chapas:
        pts.extend(_chapas._cantos(o))
    if not pts:
        return None
    return ([min(p[i] for p in pts) for i in range(3)],
            [max(p[i] for p in pts) for i in range(3)])


def _vizinhos_gravados(C):
    """Vizinhos anotados em C pela deteccao de adjacencia (sentido C -> N)."""
    saida = []
    for eixo in ('x', 'y'):
        for lado in ('pos', 'neg'):
            N = _chapas._resolver_vizinho(C, C.get('adj_%s_%s_uid' % (eixo, lado), ''),
                                  C.get('adj_%s_%s' % (eixo, lado), ''))
            if N is not None:
                saida.append(N)
    return saida


def _grupo_solto(obj, simetrico):
    """Fecho transitivo da adjacencia para uma chapa sem Conjunto.

    Os vinculos de adjacencia sao de MAO UNICA: uma prateleira aponta
    para as laterais, mas nenhuma lateral aponta para a prateleira.
    Com simetrico=True o mapa e' montado nos dois sentidos, senao a
    travessia comecando por uma lateral perde as pecas internas.

    A varredura fica restrita aos IRMAOS (mesmo pai), igual a regra de
    `_chapas._resolver_vizinho`, para nao custar o arquivo inteiro a cada clique.
    """
    chapas = [o for o in bpy.data.objects if o.type == 'MESH'
              and _chapas.MARCA_CHAPA in o and o.parent == obj.parent]
    ligacoes = {o.name: set() for o in chapas}
    porta = {o.name: o for o in chapas}
    for C in chapas:
        for N in _vizinhos_gravados(C):
            if N.name not in ligacoes:
                continue
            ligacoes[C.name].add(N.name)
            if simetrico:
                ligacoes[N.name].add(C.name)
    vistos, fila = {obj.name}, [obj.name]
    while fila:
        for viz in ligacoes.get(fila.pop(), ()):
            if viz not in vistos:
                vistos.add(viz)
                fila.append(viz)
    return [porta[n] for n in vistos if n in porta]


def grupo_de(obj, simetrico=False):
    """Define o GRUPO de uma chapa: se ela pertence a um Conjunto,
    e' o conjunto inteiro; senao, e' ela mais tudo que estiver ligado
    a ela por adjacencia (transitivamente).

    simetrico=True tambem segue os vinculos ao contrario -- e' o que a
    SELECAO quer (o modulo visivel inteiro). O recalculo de medidas
    continua no modo estrito para nao mudar de escopo sozinho.
    """
    if obj is None or _chapas.MARCA_CHAPA not in obj:
        return []
    if obj.parent is not None and _chapas.MARCA_CONJUNTO in obj.parent:
        return _chapas_do_conjunto(obj.parent)
    return _grupo_solto(obj, simetrico)


def _caixa_do_conjunto(conj):
    """Bounding box em coordenadas de mundo das chapas filhas."""
    return _caixa_de(_chapas_do_conjunto(conj))


def _eixo_local_alinhado(obj, a):
    """Qual eixo local (0=largura, 1=comprimento, 2=espessura) esta'
    alinhado com o eixo de mundo a; devolve tambem a meia-extensao."""
    eixos = _chapas._eixos(obj)
    meias = _chapas._meias(obj)
    alin = [abs(eixos[i][a]) for i in range(3)]
    i = alin.index(max(alin))
    return i, meias[i]


def _escrever_dim(obj, i_local, meia_m):
    if i_local == 0:
        obj.chapa_largura_mm = meia_m * 2000.0
    elif i_local == 1:
        obj.chapa_comprimento_mm = meia_m * 2000.0


def medir_conjunto(conj):
    cx = _caixa_do_conjunto(conj)
    if cx is None:
        return None
    lo, hi = cx
    return ((hi[0]-lo[0])*1000.0, (hi[2]-lo[2])*1000.0, (hi[1]-lo[1])*1000.0)


def redimensionar_grupo(chapas, alvo_LAP_mm, ancoras=None):
    """Leva a caixa externa do modulo para largura/altura/profundidade
    pedidas. Pecas cuja ESPESSURA corre naquele eixo mantem a espessura
    e sao ancoradas ao limite em que ja' estavam; as demais sao
    reescaladas proporcionalmente.

    `ancoras` diz, por eixo de MUNDO (X, Y, Z), que lado fica parado:
    'min' (padrao, o de sempre) ou 'max'. E' o que deixa a HUD esticar
    o movel a partir da quina mais perto do mouse."""
    cx = _caixa_de(chapas)
    if cx is None:
        return
    lo, hi = cx
    lo_antes, hi_antes = list(lo), list(hi)
    L, A, P = alvo_LAP_mm
    alvo_mm = (L, P, A)   # ordem dos eixos de mundo: X, Y, Z
    ancoras = ancoras or ('min', 'min', 'min')

    _chapas._ocupado[0] = True
    try:
        for a in range(3):
            velho = hi[a] - lo[a]
            novo = alvo_mm[a] / 1000.0
            if velho < 1e-6 or abs(novo - velho) < 1e-7:
                continue
            razao = novo / velho
            # p e' o ponto fixo; m1..M1 a faixa nova do eixo
            p = hi[a] if ancoras[a] == 'max' else lo[a]
            m1 = p - novo if ancoras[a] == 'max' else p
            M1 = m1 + novo
            for C in chapas:
                i_loc, h = _eixo_local_alinhado(C, a)
                c = _chapas._centro(C)[a]
                f_min, f_max = c - h, c + h
                if i_loc == 2:
                    # eixo de ESPESSURA: extensao nao muda
                    if abs(f_min - lo[a]) < TOL_BORDA:
                        novo_c = m1 + h
                    elif abs(f_max - hi[a]) < TOL_BORDA:
                        novo_c = M1 - h
                    else:
                        novo_c = p + (c - p) * razao
                    nc = _chapas._centro(C); nc[a] = novo_c; _chapas._definir_centro(C, nc)
                else:
                    nf_min = p + (f_min - p) * razao
                    nf_max = p + (f_max - p) * razao
                    _escrever_dim(C, i_loc, (nf_max - nf_min) / 2.0)
                    nc = _chapas._centro(C); nc[a] = (nf_max + nf_min) / 2.0; _chapas._definir_centro(C, nc)
            lo[a], hi[a] = m1, M1
            # `_centro` le matrix_world: sem atualizar aqui, o eixo
            # seguinte gravava de volta o centro ANTIGO e desfazia o
            # deslocamento deste -- a peca crescia pelo meio, ignorando
            # a ancora.
            bpy.context.view_layer.update()
    finally:
        _chapas._ocupado[0] = False

    for C in chapas:
        _chapas.gerar_malha_chapa(C)
    pai = chapas[0].parent if chapas else None
    if pai is not None and _chapas.MARCA_CONJUNTO in pai:
        _acompanhar_acessorios(pai, lo_antes, hi_antes, lo, hi)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    _chapas.aplicar_adjacencia(chapas)


def _acompanhar_acessorios(conj, lo_antes, hi_antes, lo, hi):
    """Acessorio (pe', cabideiro, peca curva) nao estica: segue a face
    do modulo de que esta' mais perto, em cada eixo de mundo, mantendo a
    distancia ate' ela. Medido na caixa de ANTES, nada fica guardado --
    se o usuario mover o acessorio, a regra vale da posicao nova.
    """
    for acc in [o for o in conj.children if _chapas.MARCA_ACESSORIO in o]:
        cantos = [acc.matrix_world @ Vector(c) for c in acc.bound_box]
        delta = Vector()
        for a in range(3):
            c_min = min(p[a] for p in cantos)
            c_max = max(p[a] for p in cantos)
            perto_do_min = (c_min - lo_antes[a]) <= (hi_antes[a] - c_max)
            delta[a] = (lo[a] - lo_antes[a] if perto_do_min
                        else hi[a] - hi_antes[a])
        if delta.length > 1e-9:
            matriz = acc.matrix_world.copy()
            matriz.translation += delta
            acc.matrix_world = matriz


def aplicar_espessura_grupo(chapas, nova_e):
    """Troca a espessura de todas as chapas do modulo SEM mover o
    contorno externo: cada peca cresce/encolhe para DENTRO a partir do
    limite em que estava encostada. A adjacencia depois expande ou
    contrai as pecas que ligam uma ponta a outra."""
    cx = _caixa_de(chapas)
    if cx is None:
        return
    lo, hi = cx

    _chapas._ocupado[0] = True
    try:
        for C in chapas:
            eixos = _chapas._eixos(C)
            ez = eixos[2]
            alin = [abs(ez[a]) for a in range(3)]
            a = alin.index(max(alin))          # eixo de mundo da espessura
            h_velho = C.chapa_espessura_mm / 2000.0
            c = _chapas._centro(C)[a]
            f_min, f_max = c - h_velho, c + h_velho
            C.chapa_espessura_mm = nova_e
            h_novo = nova_e / 2000.0
            if abs(f_min - lo[a]) < TOL_BORDA:
                nc = _chapas._centro(C); nc[a] = f_min + h_novo; _chapas._definir_centro(C, nc)
            elif abs(f_max - hi[a]) < TOL_BORDA:
                nc = _chapas._centro(C); nc[a] = f_max - h_novo; _chapas._definir_centro(C, nc)
            else:
                pass                                     # interna: centro fica
    finally:
        _chapas._ocupado[0] = False

    for C in chapas:
        _chapas.gerar_malha_chapa(C)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    _chapas.aplicar_adjacencia(chapas)


def aplicar_espessura_chapa(C, nova_e, e_velha_mm):
    """Troca a espessura de UMA chapa fazendo-a crescer para DENTRO do
    movel: a face que esta' no limite externo do grupo fica parada e a
    adjacencia encolhe as pecas internas para caber.

    Sem isto a chapa engrossava a partir do CENTRO -- metade sobrava
    para fora do movel, metade invadia a peca vizinha.

    `e_velha_mm` vem da malha porque, no callback de update, a prop ja'
    foi trocada; a caixa do grupo tambem e' medida com a espessura
    antiga de volta no lugar, senao a propria expansao ja' teria
    deslocado o limite usado como referencia.
    """
    grupo = grupo_de(C) or [C]
    ez = _chapas._eixos(C)[2]
    a = max(range(3), key=lambda i: abs(ez[i]))   # eixo de mundo da espessura

    _chapas._ocupado[0] = True
    try:
        C.chapa_espessura_mm = e_velha_mm
        cx = _caixa_de(grupo)
        C.chapa_espessura_mm = nova_e
    finally:
        _chapas._ocupado[0] = False

    h_velho = e_velha_mm / 2000.0
    h_novo = nova_e / 2000.0
    c = _chapas._centro(C)[a]
    f_min, f_max = c - h_velho, c + h_velho
    novo_c = None
    # chapa avulsa (sem conjunto nem adjacencia) nao tem "dentro do
    # movel": continua crescendo a partir do centro
    if cx is not None and len(grupo) > 1:
        lo, hi = cx
        if abs(f_min - lo[a]) < TOL_BORDA:
            novo_c = f_min + h_novo      # encostada no limite minimo
        elif abs(f_max - hi[a]) < TOL_BORDA:
            novo_c = f_max - h_novo      # encostada no limite maximo
    # chapa interna (prateleira, divisoria): cresce a partir do centro

    if novo_c is not None:
        _chapas._ocupado[0] = True
        try:
            nc = _chapas._centro(C)
            nc[a] = novo_c
            _chapas._definir_centro(C, nc)
        finally:
            _chapas._ocupado[0] = False

    _chapas.gerar_malha_chapa(C)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    # SEM aplicar_adjacencia (pedido do usuario): engrossar UMA chapa nao
    # mexe em mais nada. A adjacencia global puxava de volta ate' a peca
    # afastada de proposito ("grudava nas soldas"); a solda que sair da
    # origem fica para a regua (`cabinet_resetar_distancia`). O E do
    # MODULO (`aplicar_espessura_grupo`) continua acomodando as pecas.
    pai = C.parent
    if pai is not None and _chapas.MARCA_CONJUNTO in pai:
        reposicionar_origem(pai)


def reposicionar_origem(conj):
    """Leva a ORIGEM (o Empty) para a posicao real do movel -- centro da
    caixa em X/Y e base em Z -- compensando os filhos para que nada se
    mexa na tela.

    Antes era o contrario: a origem ficava parada e o movel deslizava em
    relacao a ela a cada redimensionamento, porque o crescimento ancora
    no canto minimo da caixa.
    """
    if conj is None or _chapas.MARCA_CONJUNTO not in conj:
        return
    chapas = _chapas_do_conjunto(conj)
    if not chapas:
        return
    # sem isto as matrizes lidas abaixo podem estar defasadas e a origem
    # so' se moveria na operacao SEGUINTE
    bpy.context.view_layer.update()
    # TODOS os filhos ficam parados, nao so' as chapas: acessorio e
    # grupo de portas andariam junto com a origem.
    filhos = list(conj.children)
    mundos = {o.name: o.matrix_world.copy() for o in filhos}
    pts = []
    for o in chapas:
        pts.extend([o.matrix_world @ v.co for v in o.data.vertices])
    if not pts:
        return
    alvo = Vector((
        (min(p.x for p in pts) + max(p.x for p in pts)) / 2.0,
        (min(p.y for p in pts) + max(p.y for p in pts)) / 2.0,
        min(p.z for p in pts),
    ))
    if (alvo - conj.matrix_world.translation).length < 1e-6:
        return
    _chapas._ocupado[0] = True
    try:
        conj.location = alvo
        bpy.context.view_layer.update()
        for o in filhos:
            o.matrix_parent_inverse = conj.matrix_world.inverted()
            o.matrix_world = mundos[o.name]
    finally:
        _chapas._ocupado[0] = False


# ============================================ MEDIDAS DE SELECAO LIVRE
# O wireframe da gaveta (`_gaveta._desenhar_wireframe_gaveta`) ja' e'
# generico -- recebe tres medidas e desenha o box.
# O que faltava era MEDIR uma selecao qualquer: um cubo, um carro com
# dezenas de malhas e curvas, o que for.

# Tipos que ocupam espaco. Empty/camera/luz tem bound_box degenerado na
# propria origem e esticariam a caixa ate' um ponto sem geometria.
TIPOS_COM_VOLUME = {
    'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'CURVES',
    'POINTCLOUD', 'VOLUME', 'GREASEPENCIL', 'GPENCIL', 'LATTICE',
}


# Para estes tipos o bound_box descreve os PONTOS DE CONTROLE, nao a
# geometria desenhada: uma curva com bevel mede o mesmo com e sem bevel,
# e as alcas do bezier incham a caixa. Neles a malha avaliada e' a unica
# medida fiel; nos demais o bound_box avaliado ja' inclui modificadores.
TIPOS_BBOX_INFIEL = {'CURVE', 'SURFACE', 'FONT', 'META'}


def _cantos_avaliados(obj, dep):
    """Pontos que delimitam o objeto em MUNDO.

    Usa o objeto AVALIADO, para que modificador, bevel e extrude entrem
    com a forma que aparece na tela e nao com a geometria crua.
    """
    alvo = obj
    if dep is not None:
        try:
            alvo = obj.evaluated_get(dep)
        except Exception:
            alvo = obj
    m = obj.matrix_world

    if obj.type in TIPOS_BBOX_INFIEL:
        malha = None
        try:
            malha = alvo.to_mesh()
        except Exception:
            malha = None
        if malha is not None:
            try:
                if len(malha.vertices):
                    return [m @ v.co.copy() for v in malha.vertices]
            finally:
                try:
                    alvo.to_mesh_clear()
                except Exception:
                    pass

    try:
        return [m @ Vector(c) for c in alvo.bound_box]
    except Exception:
        return []


def _limites_mundo(context, objs):
    """(minimos, maximos, quantos) em MUNDO, ou None se nada tem volume."""
    objs = [o for o in objs if o.type in TIPOS_COM_VOLUME]
    if not objs:
        return None
    try:
        dep = context.evaluated_depsgraph_get()
    except Exception:
        dep = None

    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    contados = 0
    for o in objs:
        pts = _cantos_avaliados(o, dep)
        if not pts:
            continue
        contados += 1
        for pt in pts:
            for a in range(3):
                lo[a] = min(lo[a], pt[a])
                hi[a] = max(hi[a], pt[a])
    return (lo, hi, contados) if contados else None


def medir_selecao(context):
    """Caixa envolvente do que estiver selecionado.

    Devolve (largura, altura, profundidade) em mm -- eixos de mundo
    (X, Z, Y), a mesma convencao das medidas de modulo -- e quantos
    objetos entraram na conta. Devolve None se nada tem volume.
    """
    limites = _limites_mundo(context, context.selected_objects)
    if limites is None:
        return None
    lo, hi, contados = limites
    return ((hi[0] - lo[0]) * 1000.0,      # largura  = X
            (hi[2] - lo[2]) * 1000.0,      # altura   = Z
            (hi[1] - lo[1]) * 1000.0,      # profund. = Y
            contados)


# ================================== CAMPOS DO MODULO, AGRUPAR E GRUPOS
def _upd_conj_dim(self, context):
    if _chapas._ocupado[0]:
        return
    redimensionar_conjunto(self)


def redimensionar_conjunto(conj, ancoras=None):
    """Aplica as medidas `conj_*` ao modulo (ver `redimensionar_grupo`)."""
    redimensionar_grupo(_chapas_do_conjunto(conj),
                        (conj.conj_largura_mm, conj.conj_altura_mm,
                         conj.conj_profundidade_mm), ancoras)
    reposicionar_origem(conj)
    _portas.atualizar_portas_do_conjunto(conj)


def _upd_conj_espessura(self, context):
    if _chapas._ocupado[0]:
        return
    val = self.conj_espessura_mm
    alvo = _chapas._espessura_livre(val)
    if abs(val - alvo) > 1e-6:
        _chapas._ocupado[0] = True
        try:
            self.conj_espessura_mm = alvo
        finally:
            _chapas._ocupado[0] = False
    aplicar_espessura_grupo(_chapas_do_conjunto(self), self.conj_espessura_mm)
    _portas.atualizar_portas_do_conjunto(self)
    reposicionar_origem(self)


def sincronizar_medidas_conjunto(conj):
    """Le a caixa real e grava nas propriedades, sem disparar recalculo."""
    m = medir_conjunto(conj)
    if not m:
        return
    _chapas._ocupado[0] = True
    try:
        conj.conj_largura_mm, conj.conj_altura_mm, conj.conj_profundidade_mm = m
        chapas = _chapas_do_conjunto(conj)
        if chapas:
            conj.conj_espessura_mm = chapas[0].chapa_espessura_mm
    finally:
        _chapas._ocupado[0] = False


class OBJECT_OT_detectar_adjacencia(Operator):
    """Memoriza quais chapas encostam uma na outra (selecione todas)"""
    bl_idname = "object.cabinet_detectar_adjacencia"
    bl_label = "Detectar Adjacencia"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sel = [o for o in context.selected_objects if o.type == 'MESH' and _chapas.MARCA_CHAPA in o]
        if len(sel) < 2:
            self.report({'WARNING'}, "Selecione pelo menos 2 chapas")
            return {'CANCELLED'}
        n = _chapas.detectar_adjacencia(sel)
        self.report({'INFO'}, "%d encoste(s) memorizado(s) em %d chapa(s)" % (n, len(sel)))
        return {'FINISHED'}


class OBJECT_OT_sincronizar_conjunto(Operator):
    """Le as medidas reais das pecas e atualiza os campos do modulo"""
    bl_idname = "object.cabinet_sincronizar"
    bl_label = "Ler Medidas Atuais"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        conj = context.object
        if conj is None or _chapas.MARCA_CONJUNTO not in conj:
            self.report({'WARNING'}, "Selecione o Empty do modulo")
            return {'CANCELLED'}
        sincronizar_medidas_conjunto(conj)
        return {'FINISHED'}


class OBJECT_OT_agrupar_conjunto(Operator):
    """Agrupa as chapas selecionadas num conjunto (Empty pai)"""
    bl_idname = "object.cabinet_agrupar"
    bl_label = "Agrupar Conjunto"
    bl_options = {'REGISTER', 'UNDO'}

    # o nome do grupo (pedido do usuario): F3 e' viewport, entao pop-up
    nome: StringProperty(name="Nome do grupo", options={'SKIP_SAVE'})

    def _selecao(self, context):
        return [o for o in context.selected_objects
                if o.type == 'MESH' and _chapas.MARCA_CHAPA in o]

    def invoke(self, context, event):
        sel = self._selecao(context)
        if not sel:
            return self.execute(context)
        if not self.nome:
            self.nome = _nome_sugerido_grupo(sel)
        return context.window_manager.invoke_props_dialog(self, width=320)

    def execute(self, context):
        sel = self._selecao(context)
        if not sel:
            self.report({'WARNING'}, "Nenhuma chapa selecionada")
            return {'CANCELLED'}
        conj = agrupar_chapas(context, sel, self.nome)
        self.report({'INFO'}, "%s: %d chapa(s) + adjacencia detectada"
                    % (conj.name, len(sel)))
        return {'FINISHED'}


# Cada armario e' um GRUPO com nome (pedido do usuario): uma Collection
# propria com o mesmo nome do Empty pai; dentro dela as chapas, o grupo
# da porta ("Porta Dupla"...) e as ferragens. A Collection e' marcada:
# so' ela se renomeia junto e some quando o grupo acaba.
MARCA_COLECAO_MODULO = "eh_colecao_modulo"


def _nome_sugerido_grupo(chapas):
    """"Armario LxAxP" (mm, eixos do mundo) -- o que a caixa ja' traz."""
    pts = [p for o in chapas for p in _chapas._cantos(o)]
    if not pts:
        return "Armario"
    medida = [round((max(p[i] for p in pts) - min(p[i] for p in pts)) * 1000)
              for i in range(3)]
    return "Armario %dx%dx%d" % (medida[0], medida[2], medida[1])


def _mover_para_colecao(obj, colecao):
    """O objeto (e os filhos) passa a morar SO' em `colecao`."""
    for o in [obj, *obj.children_recursive]:
        if colecao not in o.users_collection:
            colecao.objects.link(o)
        for c in list(o.users_collection):
            if c != colecao:
                c.objects.unlink(o)


def _nome_livre(nome, ignorar=()):
    """`nome` (ou "nome.001"...) livre como objeto E como Collection: os
    dois tem nomes independentes e o grupo precisa do MESMO nos dois."""
    candidato, n = nome[:59], 0
    while any(d is not None and d not in ignorar
              for d in (bpy.data.objects.get(candidato),
                        bpy.data.collections.get(candidato))):
        n += 1
        candidato = '%s.%03d' % (nome[:59], n)
    return candidato


def _colecao_do_modulo(conj):
    if conj is None:
        return None
    return next((c for c in conj.users_collection
                 if c.get(MARCA_COLECAO_MODULO)), None)


def nomear_grupo(conj, nome):
    """Renomeia o grupo: o Empty, a Collection dele e o vinculo das portas
    (elas guardam o NOME do modulo em `porta_modulo`)."""
    nome = (nome or '').strip()
    if conj is None or _chapas.MARCA_CONJUNTO not in conj or not nome:
        return False
    antigo = conj.name
    colecao = _colecao_do_modulo(conj)
    nome = _nome_livre(nome, ignorar=(conj, colecao))
    conj.name = nome
    if colecao is not None:
        colecao.name = nome
    for o in bpy.data.objects:
        if _chapas.MARCA_PORTAS in o and o.get(_portas.CHAVE_MODULO_PORTA) == antigo:
            o[_portas.CHAVE_MODULO_PORTA] = conj.name
    return True


def agrupar_chapas(context, sel, nome=''):
    """Empty de conjunto no centro X/Y e base Z das chapas, que viram
    filhas dele sem sair do lugar, numa Collection com o mesmo nome.
    Devolve o conjunto, ja' ativo."""
    pts = []
    for o in sel:
        pts.extend(_chapas._cantos(o))
    cx = (min(p.x for p in pts) + max(p.x for p in pts)) / 2
    cy = (min(p.y for p in pts) + max(p.y for p in pts)) / 2
    cz = min(p.z for p in pts)

    nome = _nome_livre((nome or '').strip() or _nome_sugerido_grupo(sel))
    colecao = bpy.data.collections.new(nome)
    colecao[MARCA_COLECAO_MODULO] = 1
    context.scene.collection.children.link(colecao)
    conj = bpy.data.objects.new(nome, None)
    colecao.objects.link(conj)
    conj.location = (cx, cy, cz)
    conj[_chapas.MARCA_CONJUNTO] = 1
    _chapas._ocultar_empty(conj)
    context.view_layer.update()

    for o in sel:
        mw = o.matrix_world.copy()
        o.parent = conj
        o.matrix_parent_inverse = conj.matrix_world.inverted()
        o.matrix_world = mw
        _mover_para_colecao(o, colecao)

    # adjacencia e' pre-requisito do conjunto funcionar sem vao
    _chapas.detectar_adjacencia(sel)
    sincronizar_medidas_conjunto(conj)

    for o in context.selected_objects:
        o.select_set(False)
    conj.select_set(True)
    context.view_layer.objects.active = conj
    return conj


def absorver_conjuntos():
    """Converte a escala aplicada num Empty de conjunto em escala real
    das chapas filhas, zerando a escala do Empty."""
    for conj in list(bpy.data.objects):
        if conj.type != 'EMPTY' or _chapas.MARCA_CONJUNTO not in conj:
            continue
        sx, sy, sz = conj.scale
        if abs(sx-1) < 1e-6 and abs(sy-1) < 1e-6 and abs(sz-1) < 1e-6:
            continue
        filhos = [o for o in bpy.data.objects if o.parent == conj]
        mundos = {o.name: o.matrix_world.copy() for o in filhos}
        # O mundo do Empty SEM escala, calculado aqui: depois de zerar a
        # escala o matrix_world dele so' muda no proximo update, e o setter
        # `o.matrix_world = ...` dos filhos usava o pai ainda escalado --
        # as chapas voltavam ao tamanho antigo (S no modulo nao fazia
        # nada). view_layer.update nao pode: isto roda no handler.
        local, rotacao, _escala = conj.matrix_world.decompose()
        pai_novo = Matrix.LocRotScale(local, rotacao, Vector((1, 1, 1)))
        _chapas._ocupado[0] = True
        try:
            conj.scale = (1.0, 1.0, 1.0)
            for o in filhos:
                o.matrix_basis = ((pai_novo @ o.matrix_parent_inverse)
                                  .inverted() @ mundos[o.name])
        finally:
            _chapas._ocupado[0] = False
        try:
            sincronizar_medidas_conjunto(conj)
        except Exception as e:
            print("[Cabinet Creator] sincronizar:", e)


def _grupo_ativo(context):
    o = context.object
    if o is None:
        return []
    if _chapas.MARCA_CONJUNTO in o:
        return _chapas_do_conjunto(o)
    return grupo_de(o)


def sincronizar_grupo(context):
    """Le a caixa real do grupo e grava nos campos da cena."""
    chapas = _grupo_ativo(context)
    cx = _caixa_de(chapas)
    if cx is None:
        return
    lo, hi = cx
    s = context.scene
    _chapas._ocupado[0] = True
    try:
        s.grupo_largura_mm = (hi[0]-lo[0]) * 1000.0
        s.grupo_altura_mm = (hi[2]-lo[2]) * 1000.0
        s.grupo_profundidade_mm = (hi[1]-lo[1]) * 1000.0
        s.grupo_espessura_mm = chapas[0].chapa_espessura_mm
    finally:
        _chapas._ocupado[0] = False


def _sincronizar_medidas_ativas():
    """Faz o papel dos antigos botoes "Sincronizar": os campos do modulo
    (ou do grupo) ativo voltam a mostrar a caixa REAL depois que o
    usuario move ou escala uma peca solta.

    Roda so' no TIMER, nunca no handler de depsgraph: `_caixa_de` chama
    `view_layer.update()`, que dentro do handler reentraria nele. E so'
    escreve o que mudou: gravar o mesmo valor tambem marca o depsgraph.
    """
    context = bpy.context
    obj = getattr(context, 'object', None)
    if obj is None or getattr(obj, 'mode', 'OBJECT') != 'OBJECT':
        return
    try:
        if _chapas.MARCA_CONJUNTO in obj:
            medidas = medir_conjunto(obj)
            if not medidas:
                return
            chapas = _chapas_do_conjunto(obj)
            real = tuple(medidas) + (
                (chapas[0].chapa_espessura_mm,) if chapas else ())
            campos = (obj.conj_largura_mm, obj.conj_altura_mm,
                      obj.conj_profundidade_mm, obj.conj_espessura_mm)
            if any(abs(a - b) > 0.01 for a, b in zip(real, campos)):
                sincronizar_medidas_conjunto(obj)
        elif _chapas.MARCA_CHAPA in obj and _gaveta._modo_chapa(context, obj) == 'GRUPO':
            chapas = _grupo_ativo(context)
            caixa = _caixa_de(chapas)
            if caixa is None:
                return
            lo, hi = caixa
            s = context.scene
            real = ((hi[0] - lo[0]) * 1000.0, (hi[2] - lo[2]) * 1000.0,
                    (hi[1] - lo[1]) * 1000.0, chapas[0].chapa_espessura_mm)
            campos = (s.grupo_largura_mm, s.grupo_altura_mm,
                      s.grupo_profundidade_mm, s.grupo_espessura_mm)
            if any(abs(a - b) > 0.01 for a, b in zip(real, campos)):
                sincronizar_grupo(context)
    except Exception as e:
        print("[Cabinet Creator] sincronizar medidas:", e)


def _upd_grupo_dim(self, context):
    if _chapas._ocupado[0]:
        return
    redimensionar_grupo_da_cena(self, context)


def redimensionar_grupo_da_cena(s, context, ancoras=None):
    """Aplica as medidas `grupo_*` da cena ao grupo ativo."""
    chapas = _grupo_ativo(context)
    if not chapas:
        return
    redimensionar_grupo(chapas, (s.grupo_largura_mm, s.grupo_altura_mm,
                                 s.grupo_profundidade_mm), ancoras)
    pai = chapas[0].parent if chapas else None
    if pai is not None and _chapas.MARCA_CONJUNTO in pai:
        reposicionar_origem(pai)
        sincronizar_medidas_conjunto(pai)
        _portas.atualizar_portas_do_conjunto(pai)


def _upd_grupo_espessura(self, context):
    if _chapas._ocupado[0]:
        return
    val = self.grupo_espessura_mm
    alvo = _chapas._espessura_livre(val)
    if abs(val - alvo) > 1e-6:
        _chapas._ocupado[0] = True
        try:
            self.grupo_espessura_mm = alvo
        finally:
            _chapas._ocupado[0] = False
    chapas = _grupo_ativo(context)
    if chapas:
        aplicar_espessura_grupo(chapas, alvo)
        pai = chapas[0].parent
        if pai is not None and _chapas.MARCA_CONJUNTO in pai:
            reposicionar_origem(pai)
            sincronizar_medidas_conjunto(pai)
            _portas.atualizar_portas_do_conjunto(pai)


class OBJECT_OT_sincronizar_grupo(Operator):
    """Le as medidas reais do grupo e atualiza os campos"""
    bl_idname = "object.cabinet_sincronizar_grupo"
    bl_label = "Ler Medidas do Grupo"

    def execute(self, context):
        sincronizar_grupo(context)
        return {'FINISHED'}
