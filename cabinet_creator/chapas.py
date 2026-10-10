"""Chapa: marcadores, malha (bmesh), espessura livre, normalizacao,
o handler do depsgraph, a geometria em mundo, a deteccao da
adjacencia (solda) entre chapas e os operadores de criar/marcar chapa."""

import bpy, bmesh, math, uuid
from bpy.props import BoolProperty
from mathutils import Matrix, Vector
from bpy.types import Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_modulos = None
_eventos = None
_portas = None
_ferragens = None
_importacao = None
_puxadores = None
_solda = None

# Espessuras CONVENCIONAIS: so' opcoes/padrao (enum das portas). Nao
# limitam mais o campo (pedido do usuario): qualquer espessura vale, e
# acima de ESPESSURA_ALERTA_MM a gaveta pinta o campo de vermelho.
ESPESSURAS_PERMITIDAS = [15.0, 18.0, 20.0, 30.0]
ESPESSURA_ALERTA_MM = 60.0


def _espessura_livre(valor):
    """A espessura que o usuario pediu: positiva e sem ruido de float."""
    return round(max(1.0, float(valor)), 2)


def _espessura_em_alerta(valor):
    return float(valor) > ESPESSURA_ALERTA_MM + 1e-6

# Marcador ID. ATENCAO: propriedades criadas com bpy.props em
# bpy.types.Object sao RNA e NAO aparecem em `"x" in obj`.
# Os nomes das propriedades internas (chapa_*, eh_chapa, adj_*) sao
# deliberadamente mantidos do nome antigo do add-on: eles estao gravados
# dentro dos .blend dos presets. Renomea-los invalidaria toda a
# biblioteca ja' salva.
MARCA_CHAPA = "eh_chapa"
MARCA_CONJUNTO = "eh_conjunto_chapa"
MARCA_PORTAS = "eh_grupo_portas"
MARCA_FOLHA = "eh_folha_porta"
# Objetos de fora que entram no modulo/porta sem virar chapa (IMPORTACAO).
MARCA_ACESSORIO = "eh_acessorio"
MARCA_PUXADOR = "eh_puxador"
# Empties de amarracao (modulo, grupo de portas, ponta do pistao) ficam na
# cena: o parentesco do Blender e' o que move o armario inteiro, salva o
# preset e faz a porta seguir o modulo. Mas ninguem precisa ve-los
# (pedido do usuario: poluiam a vista): tamanho minimo do Blender.
TAMANHO_EMPTY_OCULTO = 0.0001


def _ocultar_empty(obj):
    if obj.type == 'EMPTY':
        obj.empty_display_type = 'PLAIN_AXES'
        obj.empty_display_size = TAMANHO_EMPTY_OCULTO


CHAVE_TRAVAS_PUXADOR = "puxador_travas"     # [L, A, P]: 1 = travado

_ocupado = [False]
_havia_modal = [False]   # lembra se um operador modal estava ativo


def _malha_e_caixa(malha):
    """A malha ainda e' a caixa que o add-on gera: 8 vertices, um em
    cada canto da propria caixa. Qualquer recorte, chanfro, furo ou
    vertice fora do canto faz dela uma malha MODELADA."""
    vertices = malha.vertices
    if len(vertices) == 0:
        return True             # malha nova: nasce caixa
    if len(vertices) != 8:
        return False
    lo = [min(v.co[i] for v in vertices) for i in range(3)]
    hi = [max(v.co[i] for v in vertices) for i in range(3)]
    cantos = set()
    for v in vertices:
        canto = []
        for i in range(3):
            if abs(v.co[i] - lo[i]) < 1e-6:
                canto.append(0)
            elif abs(v.co[i] - hi[i]) < 1e-6:
                canto.append(1)
            else:
                return False
        cantos.add(tuple(canto))
    return len(cantos) == 8


def _esticar_malha(obj, medidas):
    """Leva a malha MODELADA as medidas (m) sem apagar nada: cada
    vertice anda junto com a face do lado em que esta' (acima do meio,
    a face maxima; abaixo, a minima). Recortes e furos mantem o tamanho
    e a distancia ate' a borda mais proxima."""
    vertices = obj.data.vertices
    lo = [min(v.co[i] for v in vertices) for i in range(3)]
    hi = [max(v.co[i] for v in vertices) for i in range(3)]
    for v in vertices:
        co = v.co.copy()
        for i in range(3):
            meio, meia = (lo[i] + hi[i]) / 2.0, medidas[i] / 2.0
            if co[i] > meio:
                co[i] += (meio + meia) - hi[i]
            else:
                co[i] += (meio - meia) - lo[i]
        v.co = co
    obj.data.update()


def gerar_malha_chapa(obj):
    """Malha REAL via bmesh -> editavel em Edit Mode.
    X local = largura | Y local = comprimento | Z local = ESPESSURA.

    Nao existe mais "Auto-regenerar" (pedido do usuario: toda mudanca
    na chapa e' para ficar). Caixa padrao e' refeita; malha modelada no
    Modo Edicao e' ESTICADA (`_esticar_malha`), nunca substituida."""
    if obj is None or obj.type != 'MESH' or obj.mode == 'EDIT':
        return
    L = obj.chapa_largura_mm / 1000.0
    C = obj.chapa_comprimento_mm / 1000.0
    E = obj.chapa_espessura_mm / 1000.0
    if not _malha_e_caixa(obj.data):
        _esticar_malha(obj, (L, C, E))
        for filho in obj.children:
            if _puxadores._eh_puxador_parametrico(filho):
                _puxadores.posicionar_puxador(filho)
        return
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= L
        v.co.y *= C
        v.co.z *= E
    # Perfil filho: a faixa dele sai da MALHA, as props seguem nominais
    # (medida da porta, adjacencia e HUD leem as props, nao a malha).
    rebaixos = _puxadores._rebaixos_da_chapa(obj)
    for borda, corte in rebaixos.items():
        eixo = 0 if borda.startswith('X') else 1
        sinal = 1.0 if borda.endswith('+') else -1.0
        meia = (L if eixo == 0 else C) / 2.0
        corte = min(corte, meia * 2.0 - 0.001)
        for v in bm.verts:
            if v.co[eixo] * sinal > 0:
                v.co[eixo] = sinal * (meia - corte)
    bm.to_mesh(obj.data)
    bm.free()
    _solda._gravar_cantos(obj)
    obj.data.update()
    if rebaixos:
        obj['chapa_rebaixos'] = ','.join(sorted(rebaixos))
    elif 'chapa_rebaixos' in obj:
        del obj['chapa_rebaixos']
    # puxadores parametricos acompanham a chapa nova
    for filho in obj.children:
        if _puxadores._eh_puxador_parametrico(filho):
            _puxadores.posicionar_puxador(filho)


def _upd_chapa(self, context):
    if _ocupado[0]:
        return
    gerar_malha_chapa(self)


def _espessura_da_malha(obj):
    """Espessura REAL da malha, em mm. Quando o callback de update roda a
    PROP ja' foi trocada mas a malha ainda e' a antiga -- e' dela que sai
    a medida velha, necessaria para saber para que lado engrossar."""
    if obj is None or obj.type != 'MESH' or not obj.data.vertices:
        return None
    # sem multiplicar por scale.z: por invariante a escala em Z e'
    # descartada, entao a malha local e' o valor antigo da prop
    zs = [v.co.z for v in obj.data.vertices]
    return (max(zs) - min(zs)) * 1000.0


def _upd_espessura(self, context):
    """Arredonda o valor digitado para a espessura permitida mais proxima
    e engrossa a chapa para DENTRO do movel
    (ver `_modulos.aplicar_espessura_chapa`)."""
    if _ocupado[0]:
        return
    val = self.chapa_espessura_mm
    alvo = _espessura_livre(val)
    e_velha = _espessura_da_malha(self)
    if abs(val - alvo) > 1e-6:
        _ocupado[0] = True
        try:
            self.chapa_espessura_mm = alvo
        finally:
            _ocupado[0] = False
    # Folha de porta nao engrossa para dentro do modulo: a porta inteira
    # e' refeita com a espessura nova (ver `_portas._espessura_da_folha_mudou`).
    if MARCA_FOLHA in self and _portas._espessura_da_folha_mudou(self, alvo):
        return
    if (MARCA_CHAPA not in self
            or e_velha is None or abs(e_velha - alvo) < 1e-4):
        gerar_malha_chapa(self)
        return
    _modulos.aplicar_espessura_chapa(self, alvo, e_velha)


# ===================================================== NORMALIZACAO
def normalizar_chapas(objs=None):
    """Converte a escala acumulada em cada chapa em MEDIDA (mm) e zera
    a escala de volta para 1.

    REGRA CENTRAL: o componente Z local (espessura) e' DESCARTADO, nao
    convertido. Como Z local e' sempre a espessura -- esteja a peca
    deitada ou em pe' -- a espessura fica imune a escala em QUALQUER
    eixo do mundo.

    Devolve a lista de pecas ajustadas.
    """
    if objs is None:
        objs = bpy.data.objects
    alvos = []
    for obj in objs:
        if obj.type != 'MESH' or MARCA_CHAPA not in obj or obj.mode == 'EDIT':
            continue
        sx, sy, sz = obj.scale
        if abs(sx - 1) < 1e-6 and abs(sy - 1) < 1e-6 and abs(sz - 1) < 1e-6:
            continue
        alvos.append((obj, sx, sy, sz))
    if not alvos:
        return []

    _ocupado[0] = True
    try:
        for obj, sx, sy, sz in alvos:
            obj.chapa_largura_mm = obj.chapa_largura_mm * sx
            obj.chapa_comprimento_mm = obj.chapa_comprimento_mm * sy
            # sz (espessura) deliberadamente IGNORADO
            obj.scale = (1.0, 1.0, 1.0)
    finally:
        _ocupado[0] = False

    for obj, _sx, _sy, _sz in alvos:
        gerar_malha_chapa(obj)

    # fecha os vaos abertos pela aritmetica da escala
    try:
        aplicar_adjacencia()
    except Exception as e:
        print("[Cabinet Creator] adjacencia:", e)

    return [o for o, _a, _b, _c in alvos]


# Chapas que estavam em Modo Edicao no ultimo tique do timer (por nome)
_chapas_em_edicao = set()


def absorver_edicoes_de_malha():
    """Chapa que acabou de SAIR do Modo Edicao: a malha que o usuario
    mexeu vira medida (`absorver_malha_editada`).

    A HUD, a gaveta e a adjacencia leem as PROPS, nao a malha. Esticar
    um lado no Modo Edicao deixava o contorno da HUD com a medida velha
    (print do usuario). Olha so' a TRANSICAO: chapa importada com malha
    fora do centro e que ninguem editou nao tem a origem mexida.
    """
    agora, saidas = set(), []
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or MARCA_CHAPA not in obj:
            continue
        if obj.mode == 'EDIT':
            agora.add(obj.name)
        elif obj.name in _chapas_em_edicao:
            saidas.append(obj)
    _chapas_em_edicao.clear()
    _chapas_em_edicao.update(agora)
    for obj in saidas:
        try:
            absorver_malha_editada(obj)
        except Exception as e:
            print("[Cabinet Creator] absorver edicao:", e)


def absorver_malha_editada(obj):
    """Caixa local da malha -> largura/comprimento/espessura; a origem
    volta ao centro da caixa SEM a peca sair do lugar no mundo.

    Folha de porta fica de fora (edita-se pelo grupo), e chapa com perfil
    tambem: a faixa do perfil e' cortada de proposito so' na malha.
    Devolve True se mudou algo.
    """
    if (MARCA_FOLHA in obj or obj.get('chapa_rebaixos')
            or not obj.data.vertices
            or any(abs(s - 1.0) > 1e-6 for s in obj.scale)):
        return False
    cos = [v.co for v in obj.data.vertices]
    lo = Vector([min(c[i] for c in cos) for i in range(3)])
    hi = Vector([max(c[i] for c in cos) for i in range(3)])
    tamanho = (hi - lo) * 1000.0
    centro = (lo + hi) / 2.0
    antes = (obj.chapa_largura_mm, obj.chapa_comprimento_mm,
             obj.chapa_espessura_mm)
    if (all(abs(t - a) < 0.01 for t, a in zip(tamanho, antes))
            and centro.length < 1e-7):
        return False
    if centro.length >= 1e-7:
        # Filhos (puxador importado, acessorio) ficam onde estavam; o
        # parametrico e' refeito pelas props em gerar_malha_chapa.
        filhos = {f: f.matrix_world.copy() for f in obj.children
                  if not _puxadores._eh_puxador_parametrico(f)}
        mundo = obj.matrix_world.copy()
        obj.data.transform(Matrix.Translation(-centro))
        obj.matrix_world = mundo @ Matrix.Translation(centro)
        for filho, matriz in filhos.items():
            filho.matrix_world = matriz
    espessura = _espessura_livre(tamanho.z)
    _ocupado[0] = True
    try:
        obj.chapa_largura_mm = tamanho.x
        obj.chapa_comprimento_mm = tamanho.y
        obj.chapa_espessura_mm = espessura
    finally:
        _ocupado[0] = False
    gerar_malha_chapa(obj)
    obj.data.update()
    return True


# ============================= HANDLER: age SO' depois do modal acabar
def ao_atualizar_depsgraph(scene, depsgraph):
    """A chapa deforma normalmente durante o arraste do S (a ferramenta
    nativa do Blender trabalha sem interferencia). Assim que o operador
    modal termina -- Enter, clique ou Esc -- este handler detecta a
    transicao e recalcula todas as chapas de uma vez.

    Mexer na escala DURANTE o modal nao funciona: o operador guarda a
    escala inicial em cache e reaplica o fator a cada movimento do
    mouse, entao qualquer correcao feita no meio do arraste e'
    sobrescrita no quadro seguinte.
    """
    if _ocupado[0] or _eventos._desfazendo[0]:
        # logo apos um undo os dados acabaram de voltar (ver
        # `_eventos._depois_de_desfazer`): nada a recalcular, e mexer aqui derrubava
        return
    # trocar a selecao tambem passa por aqui: o contorno acompanha na
    # hora, sem esperar o timer
    _eventos.sincronizar_contornos()
    # apagou/duplicou algo: as ferragens das portas se conferem depois
    # (num timer: remover objeto dentro do handler do depsgraph nao)
    if len(bpy.data.objects) != _ferragens._contagem_objetos[0]:
        _ferragens._contagem_objetos[0] = len(bpy.data.objects)
        if not bpy.app.timers.is_registered(_ferragens._conferir_ferragens):
            bpy.app.timers.register(_ferragens._conferir_ferragens, first_interval=0.0)

    modal_ativo = False
    try:
        for win in bpy.context.window_manager.windows:
            if len(win.modal_operators) > 0:
                modal_ativo = True
                break
    except Exception:
        modal_ativo = False

    if modal_ativo:
        _havia_modal[0] = True     # arraste em andamento: nao tocar
        return

    if _havia_modal[0]:
        _havia_modal[0] = False
        _modulos.absorver_conjuntos()
        normalizar_chapas()        # o modal acabou: recalcula tudo
        return

    # sem modal envolvido (ex.: escala definida por script/painel)
    _modulos.absorver_conjuntos()
    normalizar_chapas()



# ===================================================== ADJACENCIA
# Guarda, para cada ponta da chapa (X- X+ Y- Y+), qual peca vizinha ela
# encosta e qual era a folga no momento da deteccao. Depois de qualquer
# recalculo, a chapa e' esticada/encurtada para reencontrar a mesma
# folga -- fechando o vao que a aritmetica da escala abre.
#
# O vao aparece porque, ao escalar por F, a POSICAO das laterais e' multi-
# plicada por F mas a ESPESSURA delas nao. Por lado: vao = (E/2)*(F-1).
PONTAS = ("x_neg", "x_pos", "y_neg", "y_pos")
TOL_ENCOSTE = 0.06   # 60mm: distancia maxima para considerar vizinhanca


def _garantir_uid(obj):
    """Identificador estavel da chapa. Necessario porque a adjacencia
    guardada por NOME quebra ao trazer um modulo da biblioteca: os nomes
    ganham sufixo (.001) e os vinculos apontariam para a peca errada."""
    if not obj.get("chapa_uid"):
        obj["chapa_uid"] = uuid.uuid4().hex[:12]
    return obj["chapa_uid"]


def _resolver_vizinho(C, uid, nome):
    """Procura o vizinho primeiro entre os IRMAOS (mesmo pai), para que
    copias de um mesmo modulo nao se confundam entre si."""
    if uid:
        irmaos = [o for o in bpy.data.objects
                  if o.parent == C.parent and o.get("chapa_uid") == uid]
        if len(irmaos) == 1:
            return irmaos[0]
        if len(irmaos) > 1:
            return min(irmaos, key=lambda o: (o.location - C.location).length)
    if nome and nome in bpy.data.objects:
        return bpy.data.objects[nome]
    return None


def _eixos(obj):
    """Eixos locais expressos em MUNDO. Usar rotation_euler (local) aqui
    quebrava assim que o Empty pai saia da origem: o espaco de
    referencia deixava de coincidir com o mundo e o teste de 'face
    encostada no limite' parava de reconhecer as pecas."""
    m = obj.matrix_world.to_3x3()
    return m.col[0].normalized(), m.col[1].normalized(), m.col[2].normalized()


def _centro(obj):
    return obj.matrix_world.translation.copy()


def _definir_centro(obj, novo):
    """Grava um centro de MUNDO respeitando pai e matrix_parent_inverse."""
    if obj.parent is not None:
        base = obj.parent.matrix_world @ obj.matrix_parent_inverse
        obj.location = base.inverted() @ novo
    else:
        obj.location = novo


def _meias(obj):
    return (obj.chapa_largura_mm / 2000.0,
            obj.chapa_comprimento_mm / 2000.0,
            obj.chapa_espessura_mm / 2000.0)


def _cantos(obj):
    ex, ey, ez = _eixos(obj)
    hx, hy, hz = _meias(obj)
    c = _centro(obj)
    pts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                pts.append(c + ex * (sx * hx) + ey * (sy * hy) + ez * (sz * hz))
    return pts


def _faixa(obj, d):
    p = [v.dot(d) for v in _cantos(obj)]
    return min(p), max(p)


def _sobrepoe(a, b, folga=1e-4):
    return (a[0] < b[1] + folga) and (b[0] < a[1] + folga)


# Conexao AUTOMATICA (botao Corrente, "conectar por distancia") so' ate'
# aqui (pedido do usuario). Mais longe ja' e' "selecionar vertice". O
# detectar_adjacencia (agrupar o modulo) segue com o TOL_ENCOSTE.
ALCANCE_CONEXAO_AUTOMATICA = 0.005


def _melhor_vizinho(C, eixo, lado, candidatos, alcance=None):
    """(vizinho, folga, face) mais proximo da ponta eixo/lado de C entre
    os `candidatos`, ou None. Mesma regra do detectar_adjacencia; o
    `alcance` (m) troca o TOL_ENCOSTE."""
    limite = TOL_ENCOSTE if alcance is None else alcance
    ex, ey, ez = _eixos(C)
    hx, hy, _hz = _meias(C)
    u, h = (ex, hx) if eixo == "x" else (ey, hy)
    perp = [w for w in (ex, ey, ez) if w is not u]
    ponta = _centro(C).dot(u) + (h if lado == "pos" else -h)
    melhor = None
    for N in candidatos:
        if N is C or N.type != 'MESH' or MARCA_CHAPA not in N:
            continue
        # so' considera vizinho que se sobrepoe nas outras direcoes
        if not all(_sobrepoe(_faixa(C, w), _faixa(N, w)) for w in perp):
            continue
        faces = _faixa(N, u)   # (min, max) do vizinho na direcao u
        # Ancora na face do vizinho MAIS PROXIMA da ponta.
        # Usar sempre a face distante embutia a espessura
        # antiga na folga: ao trocar a espessura, a peca era
        # empurrada para fora e o modulo crescia sozinho.
        i_face = 0 if abs(faces[0] - ponta) <= abs(faces[1] - ponta) else 1
        folga = (faces[i_face] - ponta) if lado == "pos" else (ponta - faces[i_face])
        if folga < -limite or folga > limite + 1e-9:
            continue
        if melhor is None or abs(folga) < abs(melhor[1]):
            melhor = (N, folga, i_face)
    return melhor


def _gravar_ligacao(C, eixo, lado, N, folga, face):
    if f"adj_{eixo}_{lado}_ancoras" in C:
        del C[f"adj_{eixo}_{lado}_ancoras"]   # solda nova: ancoras de fabrica
    C[f"adj_{eixo}_{lado}"] = N.name
    C[f"adj_{eixo}_{lado}_uid"] = _garantir_uid(N)
    C[f"adj_{eixo}_{lado}_folga"] = float(folga)
    C[f"adj_{eixo}_{lado}_face"] = int(face)


def detectar_adjacencia(objs):
    """Para cada ponta de cada chapa, acha a peca vizinha mais proxima
    naquela direcao e memoriza a folga atual."""
    chapas = [o for o in objs if o.type == 'MESH' and MARCA_CHAPA in o]
    for c in chapas:
        _garantir_uid(c)
    n = 0
    for C in chapas:
        for k in PONTAS:
            C[f"adj_{k}"] = ""
            C[f"adj_{k}_folga"] = 0.0
            if f"adj_{k}_ancoras" in C:
                del C[f"adj_{k}_ancoras"]
        for eixo in ("x", "y"):
            for lado in ("pos", "neg"):
                achado = _melhor_vizinho(C, eixo, lado, chapas)
                if achado is not None:
                    _gravar_ligacao(C, eixo, lado, *achado)
                    n += 1
    return n


def associar_por_distancia(C, vizinhos, alcance=None):
    """Liga UMA peca aos vizinhos ao alcance, sem recalcular as outras
    ligacoes deles (detectar_adjacencia zera tudo de quem recebe e
    perderia, por exemplo, a ligacao de um modulo com o vizinho de fora).
    As pontas de C sao refeitas; nos vizinhos, so' pontas VAZIAS ganham
    ligacao com C. Devolve quantas pontas ligou."""
    vizinhos = [v for v in vizinhos if v is not C and MARCA_CHAPA in v]
    _garantir_uid(C)
    n = 0
    for eixo in ("x", "y"):
        for lado in ("pos", "neg"):
            achado = _melhor_vizinho(C, eixo, lado, vizinhos, alcance)
            if achado is not None:
                _gravar_ligacao(C, eixo, lado, *achado)
                n += 1
    for V in vizinhos:
        for eixo in ("x", "y"):
            for lado in ("pos", "neg"):
                if _solda._vizinho_da_ponta(V, "%s_%s" % (eixo, lado)) is not None:
                    continue
                achado = _melhor_vizinho(V, eixo, lado, [C], alcance)
                if achado is not None:
                    _gravar_ligacao(V, eixo, lado, *achado)
                    n += 1
    return n


def _chapas_candidatas(C, candidatos=None):
    """As outras chapas da cena, ou so' as `candidatos` (os alvos
    selecionados antes da peca de fora)."""
    fonte = bpy.data.objects if candidatos is None else candidatos
    return [o for o in fonte
            if o is not C and o.type == 'MESH' and MARCA_CHAPA in o]


def _vizinhos_por_distancia(C, alcance=ALCANCE_CONEXAO_AUTOMATICA,
                            candidatos=None):
    """Chapas que ficariam ligadas a C por distancia (sem gravar nada):
    as que as pontas de C alcancam e as que alcancam C."""
    outras = _chapas_candidatas(C, candidatos)
    achados = set()
    for eixo in ("x", "y"):
        for lado in ("pos", "neg"):
            achado = _melhor_vizinho(C, eixo, lado, outras, alcance)
            if achado is not None:
                achados.add(achado[0])
    for V in outras:
        if V in achados:
            continue
        if any(_melhor_vizinho(V, e, l, [C], alcance) is not None
               for e in ("x", "y") for l in ("pos", "neg")):
            achados.add(V)
    return achados


def aplicar_adjacencia(objs=None):
    """Estica/encurta cada chapa nos eixos de largura e comprimento
    para reencontrar a folga memorizada com seus vizinhos."""
    if objs is None:
        objs = bpy.data.objects
    chapas = [o for o in objs if o.type == 'MESH' and MARCA_CHAPA in o
              and o.mode != 'EDIT']
    ajustadas = []
    _ocupado[0] = True
    try:
        for C in chapas:
            ex, ey, ez = _eixos(C)
            mudou = False
            # Centro mantido AQUI entre os eixos: relido de matrix_world, o
            # passo em Y perdia o deslocamento do X (matriz defasada, sem
            # view_layer.update -- que nao pode rodar dentro do handler).
            centro = _centro(C)
            for eixo, u in (("x", ex), ("y", ey)):
                hx, hy, hz = _meias(C)
                h = hx if eixo == "x" else hy
                centro_u = centro.dot(u)
                p_pos, p_neg = centro_u + h, centro_u - h
                alvo_pos, alvo_neg = p_pos, p_neg

                N = _resolver_vizinho(C, C.get(f"adj_{eixo}_pos_uid", ""), C.get(f"adj_{eixo}_pos", ""))
                if N is not None:
                    fp = int(C.get(f"adj_{eixo}_pos_face", 0))
                    alvo_pos = _faixa(N, u)[fp] - C.get(f"adj_{eixo}_pos_folga", 0.0)
                N = _resolver_vizinho(C, C.get(f"adj_{eixo}_neg_uid", ""), C.get(f"adj_{eixo}_neg", ""))
                if N is not None:
                    fn = int(C.get(f"adj_{eixo}_neg_face", 1))
                    alvo_neg = _faixa(N, u)[fn] + C.get(f"adj_{eixo}_neg_folga", 0.0)

                novo_h = (alvo_pos - alvo_neg) / 2.0
                if novo_h <= 0.0005:
                    continue
                novo_centro_u = (alvo_pos + alvo_neg) / 2.0
                if abs(novo_h - h) < 1e-7 and abs(novo_centro_u - centro_u) < 1e-7:
                    continue

                if eixo == "x":
                    C.chapa_largura_mm = novo_h * 2000.0
                else:
                    C.chapa_comprimento_mm = novo_h * 2000.0
                centro = centro + u * (novo_centro_u - centro_u)
                _definir_centro(C, centro)
                mudou = True
            if mudou:
                ajustadas.append(C)
    finally:
        _ocupado[0] = False

    for C in ajustadas:
        gerar_malha_chapa(C)
    return ajustadas


class OBJECT_OT_normalizar(Operator):
    """Recalcula as chapas selecionadas a partir da escala aplicada"""
    bl_idname = "object.cabinet_normalizar"
    bl_label = "Recalcular Chapas"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        alvo = context.selected_objects or bpy.data.objects
        ajustadas = normalizar_chapas(alvo)
        self.report({'INFO'}, "%d chapa(s) recalculada(s)" % len(ajustadas))
        return {'FINISHED'}


# ================================================== CRIACAO DE OBJETOS
def nova_chapa(nome, larg, comp, esp, loc_mm, rot_graus, context):
    malha = bpy.data.meshes.new(nome)
    obj = bpy.data.objects.new(nome, malha)
    context.collection.objects.link(obj)
    obj[MARCA_CHAPA] = 1
    _ocupado[0] = True
    try:
        obj.chapa_largura_mm = larg
        obj.chapa_comprimento_mm = comp
        obj.chapa_espessura_mm = esp
    finally:
        _ocupado[0] = False
    obj.location = tuple(v / 1000.0 for v in loc_mm)
    obj.rotation_euler = tuple(math.radians(a) for a in rot_graus)
    gerar_malha_chapa(obj)
    return obj


class OBJECT_OT_criar_chapa(Operator):
    """Cria uma chapa avulsa (600 x 400 x 18mm)"""
    bl_idname = "object.cabinet_criar"
    bl_label = "Criar Chapa"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = nova_chapa("Chapa", 600.0, 400.0, 18.0, (0, 0, 0), (0, 0, 0), context)
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {'FINISHED'}


class OBJECT_OT_criar_nicho(Operator):
    """Cria um nicho sem fundo: 2 laterais + tampo + base"""
    bl_idname = "object.cabinet_criar_nicho"
    bl_label = "Criar Nicho (sem fundo)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        L, A, P, E = 600.0, 400.0, 300.0, 18.0
        li = L - 2 * E
        pecas = [
            ("Lateral_Esq", A, P, E, (-(L / 2 - E / 2), 0, A / 2), (0, 90, 0)),
            ("Lateral_Dir", A, P, E, ((L / 2 - E / 2), 0, A / 2), (0, 90, 0)),
            ("Base",        li, P, E, (0, 0, E / 2), (0, 0, 0)),
            ("Tampo",       li, P, E, (0, 0, A - E / 2), (0, 0, 0)),
        ]
        for o in context.selected_objects:
            o.select_set(False)
        criadas = [nova_chapa(n, la, c, e, lo, r, context) for n, la, c, e, lo, r in pecas]
        for c in criadas:
            c.select_set(True)
        context.view_layer.objects.active = criadas[0]
        return {'FINISHED'}


class OBJECT_OT_marcar_como_chapa(Operator):
    """Converte o objeto selecionado em chapa G3"""
    bl_idname = "object.cabinet_marcar"
    bl_label = "Marcar como Chapa"
    bl_options = {'REGISTER', 'UNDO'}

    alternar: BoolProperty(default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'

    def execute(self, context):
        obj = context.object
        if self.alternar and MARCA_CHAPA in obj:
            if MARCA_FOLHA in obj:
                self.report({'WARNING'}, 'Folha parametrica: edite pelo grupo de portas')
                return {'CANCELLED'}
            # A conversao explicita preserva a malha e a hierarquia. Limpar
            # referencias evita que a adjacencia use a chapa ja' desativada.
            for chapa in bpy.data.objects:
                if MARCA_CHAPA not in chapa:
                    continue
                for ponta in PONTAS:
                    base = 'adj_' + ponta
                    vizinho = _resolver_vizinho(
                        chapa, chapa.get(base + '_uid', ''), chapa.get(base, ''))
                    if chapa == obj or vizinho == obj:
                        for sufixo in ('', '_uid', '_folga', '_face'):
                            if base + sufixo in chapa:
                                del chapa[base + sufixo]
            _ocupado[0] = True
            try:
                obj.chapa_auto = False
                del obj[MARCA_CHAPA]
            finally:
                _ocupado[0] = False
            return {'FINISHED'}
        # A medida sai da FORMA da peca (`converter_em_chapa`), nao de
        # `obj.dimensions` em eixos de mundo: assim uma lateral em pe'
        # vira chapa com a espessura certa e sem sair do lugar. Vale para
        # toda a selecao -- um armario importado tem dezenas de pecas.
        alvos = [o for o in context.selected_objects
                 if o.type == 'MESH' and MARCA_CHAPA not in o
                 and MARCA_PUXADOR not in o]
        if obj not in alvos and MARCA_CHAPA not in obj and MARCA_PUXADOR not in obj:
            alvos.append(obj)
        convertidas = [o for o in alvos if _importacao.converter_em_chapa(o) is not None]
        if not convertidas:
            self.report({'WARNING'}, "Nada com volume para converter")
            return {'CANCELLED'}
        if len(convertidas) == 1:
            c = convertidas[0]
            self.report({'INFO'}, "Chapa %.0f x %.0f x %.0f mm"
                        % (c.chapa_largura_mm, c.chapa_comprimento_mm,
                           c.chapa_espessura_mm))
        else:
            self.report({'INFO'}, "%d chapas convertidas" % len(convertidas))
        return {'FINISHED'}
