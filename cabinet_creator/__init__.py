bl_info = {
    "name": "Cabinet Creator",
    "author": "Douglas",
    "version": (176, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > gaveta esquerda",
    "doc_url": "",
    "description": "Armarios parametricos: chapas com malha editavel e espessura imune a escala",
    "category": "Object",
}

import bpy, bmesh, colorsys, math, os, re, uuid, json, gpu, blf, time
import bpy.utils.previews
from gpu_extras.batch import batch_for_shader
from bpy.props import (FloatProperty, BoolProperty, EnumProperty,
                       StringProperty, IntProperty, IntVectorProperty,
                       FloatVectorProperty)
from mathutils import Matrix, Vector
from mathutils.geometry import intersect_line_plane
from bpy_extras import view3d_utils
from bpy.types import Gizmo, GizmoGroup, Operator, Panel

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
            if _eh_puxador_parametrico(filho):
                posicionar_puxador(filho)
        return
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= L
        v.co.y *= C
        v.co.z *= E
    # Perfil filho: a faixa dele sai da MALHA, as props seguem nominais
    # (medida da porta, adjacencia e HUD leem as props, nao a malha).
    rebaixos = _rebaixos_da_chapa(obj)
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
    _gravar_cantos(obj)
    obj.data.update()
    if rebaixos:
        obj['chapa_rebaixos'] = ','.join(sorted(rebaixos))
    elif 'chapa_rebaixos' in obj:
        del obj['chapa_rebaixos']
    # puxadores parametricos acompanham a chapa nova
    for filho in obj.children:
        if _eh_puxador_parametrico(filho):
            posicionar_puxador(filho)


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
    e engrossa a chapa para DENTRO do movel (ver aplicar_espessura_chapa)."""
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
    # e' refeita com a espessura nova (ver `_espessura_da_folha_mudou`).
    if MARCA_FOLHA in self and _espessura_da_folha_mudou(self, alvo):
        return
    if (MARCA_CHAPA not in self
            or e_velha is None or abs(e_velha - alvo) < 1e-4):
        gerar_malha_chapa(self)
        return
    aplicar_espessura_chapa(self, alvo, e_velha)


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
                  if not _eh_puxador_parametrico(f)}
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
    if _ocupado[0] or _desfazendo[0]:
        # logo apos um undo os dados acabaram de voltar (ver
        # `_depois_de_desfazer`): nada a recalcular, e mexer aqui derrubava
        return
    # trocar a selecao tambem passa por aqui: o contorno acompanha na
    # hora, sem esperar o timer
    sincronizar_contornos()
    # apagou/duplicou algo: as ferragens das portas se conferem depois
    # (num timer: remover objeto dentro do handler do depsgraph nao)
    if len(bpy.data.objects) != _contagem_objetos[0]:
        _contagem_objetos[0] = len(bpy.data.objects)
        if not bpy.app.timers.is_registered(_conferir_ferragens):
            bpy.app.timers.register(_conferir_ferragens, first_interval=0.0)

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
        absorver_conjuntos()
        normalizar_chapas()        # o modal acabou: recalcula tudo
        return

    # sem modal envolvido (ex.: escala definida por script/painel)
    absorver_conjuntos()
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
                if _vizinho_da_ponta(V, "%s_%s" % (eixo, lado)) is not None:
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
            if o.parent == conj and o.type == 'MESH' and MARCA_CHAPA in o]


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
        pts.extend(_cantos(o))
    if not pts:
        return None
    return ([min(p[i] for p in pts) for i in range(3)],
            [max(p[i] for p in pts) for i in range(3)])


def _vizinhos_gravados(C):
    """Vizinhos anotados em C pela deteccao de adjacencia (sentido C -> N)."""
    saida = []
    for eixo in ('x', 'y'):
        for lado in ('pos', 'neg'):
            N = _resolver_vizinho(C, C.get('adj_%s_%s_uid' % (eixo, lado), ''),
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
    `_resolver_vizinho`, para nao custar o arquivo inteiro a cada clique.
    """
    chapas = [o for o in bpy.data.objects if o.type == 'MESH'
              and MARCA_CHAPA in o and o.parent == obj.parent]
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
    if obj is None or MARCA_CHAPA not in obj:
        return []
    if obj.parent is not None and MARCA_CONJUNTO in obj.parent:
        return _chapas_do_conjunto(obj.parent)
    return _grupo_solto(obj, simetrico)


def _caixa_do_conjunto(conj):
    """Bounding box em coordenadas de mundo das chapas filhas."""
    return _caixa_de(_chapas_do_conjunto(conj))


def _eixo_local_alinhado(obj, a):
    """Qual eixo local (0=largura, 1=comprimento, 2=espessura) esta'
    alinhado com o eixo de mundo a; devolve tambem a meia-extensao."""
    eixos = _eixos(obj)
    meias = _meias(obj)
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

    _ocupado[0] = True
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
                c = _centro(C)[a]
                f_min, f_max = c - h, c + h
                if i_loc == 2:
                    # eixo de ESPESSURA: extensao nao muda
                    if abs(f_min - lo[a]) < TOL_BORDA:
                        novo_c = m1 + h
                    elif abs(f_max - hi[a]) < TOL_BORDA:
                        novo_c = M1 - h
                    else:
                        novo_c = p + (c - p) * razao
                    nc = _centro(C); nc[a] = novo_c; _definir_centro(C, nc)
                else:
                    nf_min = p + (f_min - p) * razao
                    nf_max = p + (f_max - p) * razao
                    _escrever_dim(C, i_loc, (nf_max - nf_min) / 2.0)
                    nc = _centro(C); nc[a] = (nf_max + nf_min) / 2.0; _definir_centro(C, nc)
            lo[a], hi[a] = m1, M1
            # `_centro` le matrix_world: sem atualizar aqui, o eixo
            # seguinte gravava de volta o centro ANTIGO e desfazia o
            # deslocamento deste -- a peca crescia pelo meio, ignorando
            # a ancora.
            bpy.context.view_layer.update()
    finally:
        _ocupado[0] = False

    for C in chapas:
        gerar_malha_chapa(C)
    pai = chapas[0].parent if chapas else None
    if pai is not None and MARCA_CONJUNTO in pai:
        _acompanhar_acessorios(pai, lo_antes, hi_antes, lo, hi)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    aplicar_adjacencia(chapas)


def _acompanhar_acessorios(conj, lo_antes, hi_antes, lo, hi):
    """Acessorio (pe', cabideiro, peca curva) nao estica: segue a face
    do modulo de que esta' mais perto, em cada eixo de mundo, mantendo a
    distancia ate' ela. Medido na caixa de ANTES, nada fica guardado --
    se o usuario mover o acessorio, a regra vale da posicao nova.
    """
    for acc in [o for o in conj.children if MARCA_ACESSORIO in o]:
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

    _ocupado[0] = True
    try:
        for C in chapas:
            eixos = _eixos(C)
            ez = eixos[2]
            alin = [abs(ez[a]) for a in range(3)]
            a = alin.index(max(alin))          # eixo de mundo da espessura
            h_velho = C.chapa_espessura_mm / 2000.0
            c = _centro(C)[a]
            f_min, f_max = c - h_velho, c + h_velho
            C.chapa_espessura_mm = nova_e
            h_novo = nova_e / 2000.0
            if abs(f_min - lo[a]) < TOL_BORDA:
                nc = _centro(C); nc[a] = f_min + h_novo; _definir_centro(C, nc)
            elif abs(f_max - hi[a]) < TOL_BORDA:
                nc = _centro(C); nc[a] = f_max - h_novo; _definir_centro(C, nc)
            else:
                pass                                     # interna: centro fica
    finally:
        _ocupado[0] = False

    for C in chapas:
        gerar_malha_chapa(C)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    aplicar_adjacencia(chapas)


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
    ez = _eixos(C)[2]
    a = max(range(3), key=lambda i: abs(ez[i]))   # eixo de mundo da espessura

    _ocupado[0] = True
    try:
        C.chapa_espessura_mm = e_velha_mm
        cx = _caixa_de(grupo)
        C.chapa_espessura_mm = nova_e
    finally:
        _ocupado[0] = False

    h_velho = e_velha_mm / 2000.0
    h_novo = nova_e / 2000.0
    c = _centro(C)[a]
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
        _ocupado[0] = True
        try:
            nc = _centro(C)
            nc[a] = novo_c
            _definir_centro(C, nc)
        finally:
            _ocupado[0] = False

    gerar_malha_chapa(C)
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
    if pai is not None and MARCA_CONJUNTO in pai:
        reposicionar_origem(pai)


def reposicionar_origem(conj):
    """Leva a ORIGEM (o Empty) para a posicao real do movel -- centro da
    caixa em X/Y e base em Z -- compensando os filhos para que nada se
    mexa na tela.

    Antes era o contrario: a origem ficava parada e o movel deslizava em
    relacao a ela a cada redimensionamento, porque o crescimento ancora
    no canto minimo da caixa.
    """
    if conj is None or MARCA_CONJUNTO not in conj:
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
    _ocupado[0] = True
    try:
        conj.location = alvo
        bpy.context.view_layer.update()
        for o in filhos:
            o.matrix_parent_inverse = conj.matrix_world.inverted()
            o.matrix_world = mundos[o.name]
    finally:
        _ocupado[0] = False


# ============================================ MEDIDAS DE SELECAO LIVRE
# O wireframe ja' e' generico -- recebe tres medidas e desenha o box.
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


def _upd_conj_dim(self, context):
    if _ocupado[0]:
        return
    redimensionar_conjunto(self)


def redimensionar_conjunto(conj, ancoras=None):
    """Aplica as medidas `conj_*` ao modulo (ver `redimensionar_grupo`)."""
    redimensionar_grupo(_chapas_do_conjunto(conj),
                        (conj.conj_largura_mm, conj.conj_altura_mm,
                         conj.conj_profundidade_mm), ancoras)
    reposicionar_origem(conj)
    atualizar_portas_do_conjunto(conj)


def _upd_conj_espessura(self, context):
    if _ocupado[0]:
        return
    val = self.conj_espessura_mm
    alvo = _espessura_livre(val)
    if abs(val - alvo) > 1e-6:
        _ocupado[0] = True
        try:
            self.conj_espessura_mm = alvo
        finally:
            _ocupado[0] = False
    aplicar_espessura_grupo(_chapas_do_conjunto(self), self.conj_espessura_mm)
    atualizar_portas_do_conjunto(self)
    reposicionar_origem(self)


def sincronizar_medidas_conjunto(conj):
    """Le a caixa real e grava nas propriedades, sem disparar recalculo."""
    m = medir_conjunto(conj)
    if not m:
        return
    _ocupado[0] = True
    try:
        conj.conj_largura_mm, conj.conj_altura_mm, conj.conj_profundidade_mm = m
        chapas = _chapas_do_conjunto(conj)
        if chapas:
            conj.conj_espessura_mm = chapas[0].chapa_espessura_mm
    finally:
        _ocupado[0] = False


class OBJECT_OT_detectar_adjacencia(Operator):
    """Memoriza quais chapas encostam uma na outra (selecione todas)"""
    bl_idname = "object.cabinet_detectar_adjacencia"
    bl_label = "Detectar Adjacencia"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sel = [o for o in context.selected_objects if o.type == 'MESH' and MARCA_CHAPA in o]
        if len(sel) < 2:
            self.report({'WARNING'}, "Selecione pelo menos 2 chapas")
            return {'CANCELLED'}
        n = detectar_adjacencia(sel)
        self.report({'INFO'}, "%d encoste(s) memorizado(s) em %d chapa(s)" % (n, len(sel)))
        return {'FINISHED'}


class OBJECT_OT_sincronizar_conjunto(Operator):
    """Le as medidas reais das pecas e atualiza os campos do modulo"""
    bl_idname = "object.cabinet_sincronizar"
    bl_label = "Ler Medidas Atuais"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        conj = context.object
        if conj is None or MARCA_CONJUNTO not in conj:
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
                if o.type == 'MESH' and MARCA_CHAPA in o]

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
    pts = [p for o in chapas for p in _cantos(o)]
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
    if conj is None or MARCA_CONJUNTO not in conj or not nome:
        return False
    antigo = conj.name
    colecao = _colecao_do_modulo(conj)
    nome = _nome_livre(nome, ignorar=(conj, colecao))
    conj.name = nome
    if colecao is not None:
        colecao.name = nome
    for o in bpy.data.objects:
        if MARCA_PORTAS in o and o.get(CHAVE_MODULO_PORTA) == antigo:
            o[CHAVE_MODULO_PORTA] = conj.name
    return True


def agrupar_chapas(context, sel, nome=''):
    """Empty de conjunto no centro X/Y e base Z das chapas, que viram
    filhas dele sem sair do lugar, numa Collection com o mesmo nome.
    Devolve o conjunto, ja' ativo."""
    pts = []
    for o in sel:
        pts.extend(_cantos(o))
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
    conj[MARCA_CONJUNTO] = 1
    _ocultar_empty(conj)
    context.view_layer.update()

    for o in sel:
        mw = o.matrix_world.copy()
        o.parent = conj
        o.matrix_parent_inverse = conj.matrix_world.inverted()
        o.matrix_world = mw
        _mover_para_colecao(o, colecao)

    # adjacencia e' pre-requisito do conjunto funcionar sem vao
    detectar_adjacencia(sel)
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
        if conj.type != 'EMPTY' or MARCA_CONJUNTO not in conj:
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
        _ocupado[0] = True
        try:
            conj.scale = (1.0, 1.0, 1.0)
            for o in filhos:
                o.matrix_basis = ((pai_novo @ o.matrix_parent_inverse)
                                  .inverted() @ mundos[o.name])
        finally:
            _ocupado[0] = False
        try:
            sincronizar_medidas_conjunto(conj)
        except Exception as e:
            print("[Cabinet Creator] sincronizar:", e)


# ================================================== BIBLIOTECA / ASSETS
# Salva chapas e modulos na biblioteca de assets do Blender, para
# reaproveitar via Asset Browser (arrastar para a cena).
#
# Cada preset vira um .blend proprio dentro da pasta da biblioteca.
# Um arquivo por preset evita ter que reabrir e mesclar um .blend
# compartilhado a cada gravacao.
SUBPASTA_BIB = "Cabinet Creator"
# Raiz UNICA dos catalogos do Asset Browser. Trocar o CAMINHO de um
# catalogo e' seguro desde que o UUID nao mude: o .blend guarda o UUID,
# e e' por ele que o Blender reencontra o asset. Por isso as raizes
# antigas sao RENOMEADAS (mesmo UUID), nunca recriadas.
CAT_RAIZ = "Cabinet Creator"
RAIZES_ANTIGAS = ("Chapa G3",)

# Uma unica biblioteca de assets. Os nomes abaixo sao os que o addon ja'
# registrou em versoes anteriores e agora precisa recolher.
NOME_BIBLIOTECA = "Cabinet Creator"
BIBLIOTECAS_ANTIGAS = (
    "Chapa G3 (fabrica)", "Chapa G3 (equipe)",
    "Cabinet Creator (fabrica)", "Cabinet Creator (equipe)",
)
CAT_CHAPAS = CAT_RAIZ + "/Chapas"
CAT_MODULOS = CAT_RAIZ + "/Modulos"


def _pasta_addon():
    """A pasta `biblioteca/` que viaja dentro do addon."""
    return os.path.join(os.path.dirname(__file__), "biblioteca")


def _prefs():
    try:
        return bpy.context.preferences.addons[__package__].preferences
    except Exception:
        return None


# ------------------------------------------------ opcoes (engrenagem)
# (fator para mm, sufixo, casas decimais na tela)
UNIDADES_MEDIDA = {'MM': (1.0, 'mm', 1), 'CM': (10.0, 'cm', 2),
                   'M': (1000.0, 'm', 3)}
# Atalhos do seletor de cor; o resto se escolhe no quadrado + matiz.
# 'TEMA' (so' nas linhas) = cor do texto do tema, a mesma da gaveta.
CORES_ATALHO = (('BRANCO', (1.0, 1.0, 1.0)), ('CINZA', (0.55, 0.55, 0.55)),
                ('PRETO', (0.04, 0.04, 0.04)), ('CIANO', (0.2, 0.85, 1.0)),
                ('LARANJA', (1.0, 0.35, 0.05)), ('AMARELO', (1.0, 0.85, 0.1)),
                ('VERDE', (0.3, 0.9, 0.35)))
COR_REALCE_PADRAO = (1.0, 0.35, 0.05)
# (minimo, maximo, passo do arraste) dos campos de faixa da engrenagem
FAIXAS_OPCOES = {'hud_espessura_linha': (1.0, 50.0, 0.5),
                 'hud_tamanho_rotulo': (1, 50, 1)}
OPCOES_PADRAO = {'unidade_padrao': 'MM', 'hud_espessura_linha': 1.5,
                 'hud_linha_tema': True, 'hud_rgb_linha': (1.0, 1.0, 1.0),
                 'hud_rgb_realce': COR_REALCE_PADRAO, 'hud_realce_gizmo': False,
                 'hud_tamanho_rotulo': 14,
                 'ocultar_contorno_grupo': True, 'tecla_corrente': 'ALT'}
# Sem preferencias (add-on carregado por script, testes) as opcoes
# vivem aqui, para a engrenagem continuar funcionando.
_opcoes_sem_preferencias = dict(OPCOES_PADRAO)


def _opcao(nome):
    p = _prefs()
    if p is not None and hasattr(p, nome):
        valor = getattr(p, nome)
        # cor vem como bpy_prop_array, que nao compara nem se guarda
        return tuple(valor) if nome.startswith('hud_rgb_') else valor
    return _opcoes_sem_preferencias[nome]


def _definir_opcao(nome, valor):
    p = _prefs()
    if p is not None and hasattr(p, nome):
        setattr(p, nome, valor)
    else:
        _opcoes_sem_preferencias[nome] = valor
    # a HUD mora na viewport vizinha: sem isto a mudanca so' aparece
    # no proximo movimento do mouse la'
    try:
        for janela in bpy.context.window_manager.windows:
            for area in janela.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        pass
    if nome == 'ocultar_contorno_grupo':
        sincronizar_contornos()


def _texto_medida(mm):
    """Medida em mm escrita na unidade padrao, com sufixo."""
    fator, sufixo, casas = UNIDADES_MEDIDA[_opcao('unidade_padrao')]
    return '%.*f %s' % (casas, mm / fator, sufixo)


def _numero_na_unidade(mm):
    """So' o numero, na unidade padrao -- o texto inicial ao digitar."""
    fator, _sufixo, casas = UNIDADES_MEDIDA[_opcao('unidade_padrao')]
    return '%g' % round(mm / fator, casas + 2)


def pasta_biblioteca():
    """A UNICA biblioteca: a da empresa, que mora dentro do addon.

    Nao ha' mais separacao fabrica/equipe -- era ela que produzia duas
    entradas no seletor do Asset Browser. Quem quiser a biblioteca numa
    pasta de rede aponta `pasta_biblioteca` nas Preferencias.

    ATENCAO: gravar dentro do addon so' e' seguro porque a pasta e' o
    repositorio da empresa (junction feita por vincular_blender.py).
    Numa instalacao por .zip, uma atualizacao sobrescreve a pasta --
    nesse caso configure a pasta de rede nas Preferencias.
    """
    p = _prefs()
    if p and getattr(p, "pasta_biblioteca", ""):
        destino = bpy.path.abspath(p.pasta_biblioteca)
    else:
        destino = _pasta_addon()
    try:
        os.makedirs(destino, exist_ok=True)
    except Exception as e:
        print("[Cabinet Creator] biblioteca:", e)
    return destino


def registrar_bibliotecas(silencioso=True):
    """Registra as duas pastas como bibliotecas de assets do Blender,
    sem duplicar caso ja' estejam registradas."""
    registradas = []
    libs = bpy.context.preferences.filepaths.asset_libraries
    caminho = pasta_biblioteca()
    alvo = os.path.normcase(os.path.normpath(caminho))

    # A limpeza vem ANTES do registro. Uma entrada antiga podia apontar
    # para ESTA mesma pasta: removendo depois, o registro era pulado por
    # "ja' existe" e em seguida a entrada sumia -- o usuario ficava sem
    # biblioteca nenhuma ate' a proxima execucao.
    for i in range(len(libs) - 1, -1, -1):
        if libs[i].name in BIBLIOTECAS_ANTIGAS:
            try:
                libs.remove(libs[i])
            except Exception as e:
                if not silencioso:
                    print("[Cabinet Creator] remover biblioteca antiga:", e)

    ja = any(os.path.normcase(os.path.normpath(bpy.path.abspath(l.path))) == alvo
             for l in libs if l.path)
    if not ja:
        try:
            bpy.ops.preferences.asset_library_add(directory=caminho)
            libs[-1].name = NOME_BIBLIOTECA
            registradas.append(NOME_BIBLIOTECA)
        except Exception as e:
            if not silencioso:
                print("[Cabinet Creator] registro falhou:", e)

    # a cascata tem de existir ANTES do primeiro save, senao o Asset
    # Browser abre sem nenhuma pasta
    try:
        _garantir_catalogos(caminho)
    except Exception as e:
        if not silencioso:
            print("[Cabinet Creator] catalogos:", e)
    return registradas




def caminhos_catalogo():
    """Toda a ARVORE como caminhos de catalogo, em cascata.

    Cada nivel ganha a SUA propria linha: o Blender ate' desenha os pais
    implicitos, mas so' da' para ARQUIVAR um asset num nivel que exista
    como catalogo de verdade -- e a ideia e' poder arquivar em qualquer
    altura da cascata.
    """
    caminhos = [CAT_RAIZ]
    arvores = [ARVORE]
    try:
        arvores.append(_niveis_do_indice())
    except Exception as e:
        print("[Cabinet Creator] niveis do indice:", e)
    for arv in arvores:
        for n1, filhos in arv.items():
            caminhos.append("%s/%s" % (CAT_RAIZ, n1))
            for n2, netos in filhos.items():
                caminhos.append("%s/%s/%s" % (CAT_RAIZ, n1, n2))
                for n3 in netos:
                    caminhos.append("%s/%s/%s/%s" % (CAT_RAIZ, n1, n2, n3))
    return list(dict.fromkeys(caminhos))


def catalogo_de(n1, n2="", n3=""):
    """Caminho de catalogo mais fundo para os niveis escolhidos."""
    partes = [x for x in (n1, n2, n3) if x]
    if not partes:
        return ""
    return CAT_RAIZ + "/" + "/".join(partes)


def _migrar_raiz(caminho):
    """Troca uma raiz antiga pela atual, preservando o resto do caminho."""
    for velha in RAIZES_ANTIGAS:
        if caminho == velha:
            return CAT_RAIZ
        if caminho.startswith(velha + "/"):
            return CAT_RAIZ + caminho[len(velha):]
    return caminho


def _garantir_catalogos(raiz, extras=()):
    """Cria/atualiza o blender_assets.cats.txt com a cascata do addon.

    Linhas ja' existentes sao PRESERVADAS com o mesmo UUID: os presets
    guardam o UUID do catalogo dentro do .blend, entao gerar um novo
    faria o asset sumir da arvore do Asset Browser.
    """
    arq = os.path.join(raiz, "blender_assets.cats.txt")
    existentes = {}
    if os.path.exists(arq):
        for linha in open(arq, encoding="utf-8"):
            linha = linha.strip()
            if not linha or linha.startswith("#") or linha.startswith("VERSION"):
                continue
            partes = linha.split(":")
            if len(partes) >= 2:
                # raiz antiga vira a nova MANTENDO o UUID: assim o asset
                # continua achando o catalogo e nao sobra arvore dupla
                existentes.setdefault(_migrar_raiz(partes[1]), partes[0])
    for cam in list(caminhos_catalogo()) + [x for x in extras if x]:
        existentes.setdefault(cam, str(uuid.uuid4()))
    # nome simples = caminho com tracos, convencao do Blender
    texto = "VERSION 1\n\n" + "".join(
        "%s:%s:%s\n" % (existentes[cam], cam, cam.replace("/", "-"))
        for cam in sorted(existentes))
    _gravar_se_mudou(arq, texto)
    return existentes


def _gravar_se_mudou(arq, texto):
    """Grava `texto` em `arq` so' se mudou, e de forma ATOMICA.

    Todo registro do add-on passa por aqui. Antes o arquivo era reaberto
    com "w" (zera e regrava) a cada vez: com dois Blenders registrando
    juntos (o harness roda suites em paralelo; o usuario pode abrir dois),
    um lia o arquivo ja' zerado pelo outro e gerava UUID NOVO para todos
    os catalogos -- os presets perdiam a categoria (visto em 2026-10-09).
    Temporario + os.replace nunca mostra o arquivo pela metade. newline
    explicito: o .gitattributes forca LF (sem ele o Windows grava CRLF).
    """
    try:
        with open(arq, encoding="utf-8", newline="") as f:
            if f.read() == texto:
                return False
    except FileNotFoundError:
        pass
    temporario = "%s.%d.tmp" % (arq, os.getpid())
    with open(temporario, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
    for _tentativa in range(20):
        try:
            os.replace(temporario, arq)
            return True
        except PermissionError:
            # o Windows recusa a troca enquanto outro processo le
            time.sleep(0.05)
    try:
        os.remove(temporario)
    except OSError:
        pass
    return False


def refiliar_preset(caminho, niveis):
    """Reassina o catalogo de um preset JA' gravado no disco.

    O catalogo mora dentro do .blend (`asset_data.catalog_id`), nao no
    indice.json -- entao a unica forma de mover um preset de categoria
    e' carregar o datablock do asset, trocar o id e regravar o arquivo.

    Devolve (ok, mensagem).
    """
    cam = catalogo_de(*niveis)
    if not cam:
        return False, "item sem categoria no indice"
    if not os.path.exists(caminho):
        return False, "arquivo nao encontrado"
    ids = _garantir_catalogos(os.path.dirname(caminho), extras=(cam,))

    antes_col = set(bpy.data.collections)
    antes_obj = set(bpy.data.objects)
    with bpy.data.libraries.load(caminho) as (de, para):
        para.collections = list(de.collections)
        para.objects = list(de.objects)
    novas_col = [c for c in bpy.data.collections if c not in antes_col]
    novos_obj = [o for o in bpy.data.objects if o not in antes_obj]

    def limpar():
        for c in novas_col:
            try:
                bpy.data.collections.remove(c)
            except Exception:
                pass
        for o in novos_obj:
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass

    alvos = [d for d in list(novas_col) + list(novos_obj) if d.asset_data]
    if not alvos:
        limpar()
        return False, "nenhum asset dentro do arquivo"

    # so' o catalog_id e' gravavel: o Blender deriva o nome simples
    for d in alvos:
        d.asset_data.catalog_id = ids[cam]

    blocos = set(novas_col)
    for o in novos_obj:
        blocos.add(o)
        if o.data:
            blocos.add(o.data)
    try:
        bpy.data.libraries.write(caminho, blocos, fake_user=True,
                                 compress=True)
    except Exception as e:
        limpar()
        return False, str(e)
    limpar()
    return True, cam


LADO_PREVIEW = 128


def _pixels_png(caminho, lado=LADO_PREVIEW):
    """Le um PNG e devolve os pixels prontos para uma ImagePreview."""
    img = None
    try:
        img = bpy.data.images.load(caminho)
        # 'Raw' evita a conversao de espaco de cor: a preview guarda os
        # mesmos valores que o PNG, sem ganhar nem perder gama
        try:
            img.colorspace_settings.name = 'Raw'
        except Exception:
            pass
        if tuple(img.size) != (lado, lado):
            img.scale(lado, lado)
        return list(img.pixels)
    except Exception as e:
        print("[Cabinet Creator] preview:", e)
        return None
    finally:
        if img is not None:
            try:
                bpy.data.images.remove(img)
            except Exception:
                pass


def aplicar_preview_png(caminho_blend, caminho_png):
    """Grava a foto do preset DENTRO do .blend, como preview do asset.

    `asset_generate_preview()` NAO serve: ele so' enfileira um job
    assincrono de render, e o arquivo e' gravado antes de o job
    terminar -- por isso os presets chegavam ao Asset Browser com a
    preview vazia (128x128 zerada) e apareciam com o icone generico.
    Escrever os pixels a mao e' sincrono e sobrevive a gravacao.
    """
    if not os.path.exists(caminho_blend):
        return False, "blend nao encontrado"
    if not os.path.exists(caminho_png):
        return False, "sem foto (.png) ao lado do preset"
    pixels = _pixels_png(caminho_png)
    if not pixels:
        return False, "nao consegui ler a foto"

    antes_col = set(bpy.data.collections)
    antes_obj = set(bpy.data.objects)
    with bpy.data.libraries.load(caminho_blend) as (de, para):
        para.collections = list(de.collections)
        para.objects = list(de.objects)
    novas_col = [c for c in bpy.data.collections if c not in antes_col]
    novos_obj = [o for o in bpy.data.objects if o not in antes_obj]

    def limpar():
        for c in novas_col:
            try:
                bpy.data.collections.remove(c)
            except Exception:
                pass
        for o in novos_obj:
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass

    alvos = [d for d in list(novas_col) + list(novos_obj) if d.asset_data]
    if not alvos:
        limpar()
        return False, "nenhum asset dentro do arquivo"

    lado = (LADO_PREVIEW, LADO_PREVIEW)
    for d in alvos:
        try:
            d.preview_ensure()
        except Exception:
            pass
        pv = d.preview
        if pv is None:
            continue
        pv.image_size = lado
        pv.image_pixels_float = pixels
        # sem o nivel de icone o Asset Browser cai no icone generico
        pv.icon_size = lado
        pv.icon_pixels_float = pixels

    blocos = set(novas_col)
    for o in novos_obj:
        blocos.add(o)
        if o.data:
            blocos.add(o.data)
    try:
        bpy.data.libraries.write(caminho_blend, blocos, fake_user=True,
                                 compress=True)
    except Exception as e:
        limpar()
        return False, str(e)
    limpar()
    return True, "%d asset(s)" % len(alvos)


class OBJECT_OT_regerar_previews(Operator):
    """Regrava as fotos dos presets dentro dos .blend, para o Asset
    Browser deixar de mostrar o icone generico"""
    bl_idname = "object.cabinet_regerar_previews"
    bl_label = "Regerar Previews da Biblioteca"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        feitos, falhas = 0, []
        for it in indice_completo():
            blend = os.path.join(it["pasta"], it["arquivo"])
            png = os.path.join(
                it["pasta"], os.path.splitext(it["arquivo"])[0] + ".png")
            ok, msg = aplicar_preview_png(blend, png)
            if ok:
                feitos += 1
            else:
                falhas.append("%s: %s" % (it.get("nome", "?"), msg))
        for f in falhas:
            print("[Cabinet Creator] preview:", f)
        if falhas:
            self.report({'WARNING'},
                        "%d preview(s) gravada(s), %d sem foto -- salve o "
                        "preset de novo" % (feitos, len(falhas)))
        else:
            self.report({'INFO'}, "%d preview(s) gravada(s)" % feitos)
        return {'FINISHED'}


class OBJECT_OT_refiliar_catalogos(Operator):
    """Arquiva os presets da equipe nos catalogos da cascata, conforme a
    categoria de cada um no indice"""
    bl_idname = "object.cabinet_refiliar"
    bl_label = "Reorganizar Catalogos"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        feitos, falhas = 0, []
        for it in indice_completo():
            ok, msg = refiliar_preset(
                os.path.join(it["pasta"], it["arquivo"]), _niveis_de(it))
            if ok:
                feitos += 1
            else:
                falhas.append("%s: %s" % (it.get("nome", "?"), msg))
        for f in falhas:
            print("[Cabinet Creator] refiliar:", f)
        if falhas:
            self.report({'WARNING'},
                        "%d movido(s), %d falha(s) -- ver console"
                        % (feitos, len(falhas)))
        else:
            self.report({'INFO'}, "%d preset(s) reorganizado(s)" % feitos)
        return {'FINISHED'}


def _nome_arquivo_seguro(nome):
    limpo = "".join(ch if (ch.isalnum() or ch in " -_") else "_" for ch in nome).strip()
    return (limpo or "sem_nome").replace(" ", "_")


def salvar_na_biblioteca(objs, nome, como_colecao, niveis=None):
    """Grava os objetos num .blend da biblioteca.

    como_colecao=True agrupa tudo numa Collection e marca a COLLECTION
    como asset -- necessario para modulos, porque arrastar um objeto
    traz so' aquele objeto, enquanto arrastar uma colecao traz o
    conjunto inteiro.

    `niveis` = (n1, n2, n3): arquiva o asset no catalogo da CATEGORIA,
    que e' o que o Asset Browser mostra na cascata a esquerda. Sem
    niveis cai no catalogo por tipo (Chapas/Modulos), como antes.
    """
    raiz = destino = pasta_biblioteca()
    # sem niveis cai no catalogo por tipo; ele entra como extra para
    # existir no .cats.txt sem sujar o nivel 1 da cascata
    cam_cat = (catalogo_de(*niveis) if niveis else "") or (
        CAT_MODULOS if como_colecao else CAT_CHAPAS)
    ids_cat = _garantir_catalogos(raiz, extras=(cam_cat,))

    blocos = set()
    if como_colecao:
        col = bpy.data.collections.new(nome)
        for o in objs:
            col.objects.link(o)
        col.asset_mark()
        if col.asset_data:
            col.asset_data.catalog_id = ids_cat[cam_cat]
            col.asset_data.description = "Modulo G3 - %d peca(s)" % len(objs)
            col.asset_data.tags.new("chapa-g3")
        blocos.add(col)
    else:
        for o in objs:
            o.asset_mark()
            if o.asset_data:
                o.asset_data.catalog_id = ids_cat[cam_cat]
                o.asset_data.tags.new("chapa-g3")
    for o in objs:
        blocos.add(o)
        if o.data:
            blocos.add(o.data)

    # A preview do Asset Browser NAO e' gerada aqui: `asset_generate_preview`
    # e' assincrono e nunca chega a tempo da gravacao. Quem a grava e'
    # `aplicar_preview_png`, depois que a foto do preset existe.

    arquivo = os.path.join(destino, _nome_arquivo_seguro(nome) + ".blend")
    bpy.data.libraries.write(arquivo, blocos, fake_user=True, compress=True)

    if como_colecao:
        # a colecao foi criada so' para empacotar o asset
        bpy.data.collections.remove(col)
    return arquivo


# ======================================= ARVORE DA BIBLIOTECA (3 niveis)
# Cascata horizontal: nivel 1 no topo, nivel 2 abaixo ao clicar, nivel 3
# abaixo do 2. Ramos com lista vazia no nivel 3 terminam no nivel 2.
AMBIENTES = ["Sala", "Cozinha", "Varanda", "Quarto", "Banheiro", "Externo"]

ARVORE = {
    "Armarios": {
        "Sala":     ["Inferiores", "Superiores", "Cantos", "Estantes"],
        "Cozinha":  ["Inferiores", "Superiores", "Cantos", "Torres"],
        "Varanda":  ["Inferiores", "Superiores", "Bancadas"],
        "Quarto":   ["Inferiores", "Superiores", "Closets", "Gaveteiros"],
        "Banheiro": ["Gabinetes", "Espelheiras", "Nichos"],
        "Externo":  ["Inferiores", "Superiores", "Bancadas"],
    },
    "Chapas":     {"Avulsas": []},
    "Portas":     {"Abrir": [], "Correr": [], "Basculante": []},
    "Puxadores":  {"Perfil": [], "Alca": [], "Cava": []},
    "Dobradicas": {"Comuns": [], "Amortecidas": [], "Especiais": []},
}


def _niveis_de(it):
    """Le os 3 niveis de um item do indice, aceitando o formato antigo
    (categoria/subcategoria) para nao invalidar indices ja' gravados."""
    n1 = it.get("n1")
    if n1:
        return n1, it.get("n2", ""), it.get("n3", "")
    cat, sub = it.get("categoria", ""), it.get("subcategoria", "")
    if cat in AMBIENTES:
        return "Armarios", cat, sub
    return cat, sub, ""


def _niveis_do_indice():
    """Categorias que EXISTEM nos presets salvos, alem das da ARVORE.

    E' o que integra as duas pontas: uma subcategoria digitada no "+"
    do painel N passa a aparecer na cascata e tambem vira catalogo.
    """
    extra = {}
    for it in indice_completo():
        a, b, c = _niveis_de(it)
        if not a:
            continue
        ramo = extra.setdefault(a, {})
        if b:
            filhos = ramo.setdefault(b, [])
            if c and c not in filhos:
                filhos.append(c)
    return extra


def _filhos_n2(n1):
    vistos = list(ARVORE.get(n1, {}).keys())
    for k in _niveis_do_indice().get(n1, {}):
        if k not in vistos:
            vistos.append(k)
    return vistos


def _filhos_n3(n1, n2):
    vistos = list(ARVORE.get(n1, {}).get(n2, []))
    for k in _niveis_do_indice().get(n1, {}).get(n2, []):
        if k not in vistos:
            vistos.append(k)
    return vistos


def _conta(itens, n1, n2=None, n3=None):
    n = 0
    for it in itens:
        a, b, c = _niveis_de(it)
        if a != n1:
            continue
        if n2 is not None and b != n2:
            continue
        if n3 is not None and c != n3:
            continue
        n += 1
    return n


NOME_INDICE = "indice.json"


def _ler_indice(pasta):
    """Indice em JSON ao lado dos .blend. Existe para o painel listar os
    presets sem precisar abrir cada arquivo -- abrir .blend so' para
    montar a lista deixaria a interface travada."""
    arq = os.path.join(pasta, NOME_INDICE)
    if not os.path.exists(arq):
        return []
    try:
        with open(arq, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("[Cabinet Creator] indice ilegivel:", e)
        return []


def _gravar_indice(pasta, itens):
    try:
        # newline explicito: o .gitattributes do projeto forca LF
        with open(os.path.join(pasta, NOME_INDICE), "w",
                  encoding="utf-8", newline="\n") as f:
            json.dump(itens, f, ensure_ascii=False, indent=1)
            f.write("\n")
    except Exception as e:
        print("[Cabinet Creator] nao gravei o indice:", e)


def indice_completo():
    """Le o indice da biblioteca da empresa."""
    pasta = pasta_biblioteca()
    itens = []
    for it in _ler_indice(pasta):
        it = dict(it)
        it["origem"] = "biblioteca"
        it["pasta"] = pasta
        itens.append(it)
    return itens


def registrar_no_indice(pasta, nome, arquivo, n1, n2, n3, tipo):
    itens = [i for i in _ler_indice(pasta)
             if not (i.get("arquivo") == os.path.basename(arquivo))]
    itens.append({"nome": nome, "arquivo": os.path.basename(arquivo),
                  "n1": n1, "n2": n2, "n3": n3, "tipo": tipo})
    _gravar_indice(pasta, itens)


def _itens_de(categoria, subcategoria):
    return [i for i in indice_completo()
            if i.get("categoria") == categoria and i.get("subcategoria") == subcategoria]


def inserir_preset(context, pasta, arquivo, tipo, destino=None):
    """Carrega o .blend do preset na cena e seleciona o que veio.

    Devolve (novos, raizes, erro). `destino` e' o deslocamento aplicado
    as raizes; sem ele o preset vai para o cursor 3D em vez de ser
    despejado na origem.
    """
    caminho = os.path.join(pasta, arquivo)
    if not os.path.exists(caminho):
        return [], [], "Arquivo nao encontrado: " + caminho
    antes = set(bpy.data.objects)
    with bpy.data.libraries.load(caminho) as (de, para):
        if tipo == "modulo" and de.collections:
            para.collections = list(de.collections)
        else:
            para.objects = list(de.objects)
    novas_cols = [c for c in bpy.data.collections
                  if c.library is None and c.name not in
                  [x.name for x in context.scene.collection.children]]
    for c in novas_cols:
        if any(o not in antes for o in c.objects):
            context.scene.collection.children.link(c)
    for o in bpy.data.objects:
        if o not in antes and o.name not in [x.name for c in novas_cols for x in c.objects]:
            if o.name not in context.scene.collection.objects:
                try:
                    context.scene.collection.objects.link(o)
                except Exception:
                    pass
    novos = [o for o in bpy.data.objects if o not in antes]

    raizes = [o for o in novos if o.parent is None or o.parent not in novos]
    desloc = context.scene.cursor.location.copy() if destino is None else destino
    for o in raizes:
        o.location = o.location + desloc

    for o in context.selected_objects:
        o.select_set(False)
    for o in novos:
        try:
            o.select_set(True)
        except Exception:
            pass
    return novos, raizes, ""


class OBJECT_OT_inserir_preset(Operator):
    """Traz o preset da biblioteca para o cursor 3D"""
    bl_idname = "object.cabinet_inserir_preset"
    bl_label = "Inserir"
    bl_options = {'REGISTER', 'UNDO'}

    pasta: bpy.props.StringProperty()
    arquivo: bpy.props.StringProperty()
    tipo: bpy.props.StringProperty(default="modulo")

    def execute(self, context):
        novos, _raizes, erro = inserir_preset(
            context, self.pasta, self.arquivo, self.tipo)
        if erro:
            self.report({'ERROR'}, erro)
            return {'CANCELLED'}
        self.report({'INFO'}, "%d objeto(s) inserido(s)" % len(novos))
        return {'FINISHED'}


# O segundo clique do duplo na foto pode tremer um pouco
RAIO_DUPLO_CLIQUE_PX = 8


class OBJECT_OT_arrastar_preset(Operator):
    """Arrasta com mira e caixa exata antes de inserir na cena"""
    bl_idname = "object.cabinet_arrastar_preset"
    bl_label = "Arrastar para a Cena"
    bl_options = {'REGISTER', 'UNDO'}

    # SKIP_SAVE: as props do operador persistem entre execucoes no
    # Blender, e o arraste precisa descobri-las de novo a cada vez
    pasta: bpy.props.StringProperty(options={'SKIP_SAVE'})
    arquivo: bpy.props.StringProperty(options={'SKIP_SAVE'})
    tipo: bpy.props.StringProperty(default="modulo", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        # Sem preset nas props, o arraste comecou sobre a grade: o bloco
        # sob o cursor e' lido em context.button_operator, que entrega as
        # propriedades do botao apontado (o mesmo recurso que o Blender
        # usa para "Atribuir Atalho" no menu de contexto de um botao).
        if not self.arquivo:
            alvo = getattr(context, "button_operator", None)
            # O botao de importacao, o cadeado e o lapis tambem carregam
            # `arquivo`: so' miniatura e nome (este proprio operador)
            # valem como pega do arraste.
            origem = getattr(getattr(alvo, "bl_rna", None), "identifier", "")
            arquivo = (getattr(alvo, "arquivo", "")
                       if origem.endswith("cabinet_arrastar_preset") else "")
            if not arquivo:
                # arraste em qualquer outro lugar da sidebar: devolve o
                # evento para o Blender, senao sliders parariam de andar
                return {'PASS_THROUGH'}
            self.pasta = getattr(alvo, "pasta", "")
            self.arquivo = arquivo
            self.tipo = getattr(alvo, "tipo", "modulo") or "modulo"
            self._arrastando = True
            self._mouse_inicio = (event.mouse_x, event.mouse_y)
            self._moveu = False
        else:
            self._arrastando = _eh_area_gaveta(context)
            self._mouse_inicio = (event.mouse_x, event.mouse_y)
            self._moveu = not self._arrastando

        # relogio do 1o clique: o duplo na foto e' medido a partir dele
        self._instante_inicio = time.monotonic()
        # a grade vive na sidebar, entao a regiao do evento NAO e' a
        # viewport: a janela de desenho tem de ser procurada na area
        self._area_preview = context.area
        if _eh_area_gaveta(context):
            self._area_preview = next(
                (a for a in context.screen.areas
                 if a.type == 'VIEW_3D' and a != context.area
                 and a.x > context.area.x
                 and a.y == context.area.y), None)
        self._regiao = next(
            (r for r in self._area_preview.regions if r.type == 'WINDOW'), None
        ) if self._area_preview else None
        self._rv3d = getattr(self._area_preview.spaces.active, "region_3d", None
                             ) if self._area_preview else None
        if self._regiao is None or self._rv3d is None:
            self.report({'ERROR'}, "Sem viewport 3D para posicionar")
            return {'CANCELLED'}
        # O draw handler pode ser chamado no primeiro redraw logo depois de
        # registrado; deixe o filtro de regiao pronto antes desse momento.
        self._regiao_ptr = self._regiao.as_pointer()

        self._selecionados_antes = list(context.selected_objects)
        self._ativo_antes = context.view_layer.objects.active
        colecoes_antes = set(bpy.data.collections)
        self._novos = []
        self._raizes = []
        self._colecoes_novas = []

        # O preset entra oculto como staging. So' se torna visivel quando
        # o usuario solta dentro da viewport; cancelar apaga tudo.
        novos, raizes, erro = inserir_preset(
            context, self.pasta, self.arquivo, self.tipo,
            destino=Vector((0.0, 0.0, 0.0)))
        self._novos = list(novos or [])
        self._raizes = list(raizes or [])
        self._colecoes_novas = [c for c in bpy.data.collections
                                if c not in colecoes_antes]
        if erro:
            self._apagar()
            self._restaurar_selecao(context)
            self.report({'ERROR'}, erro)
            return {'CANCELLED'}
        if not self._novos:
            self._apagar()
            self._restaurar_selecao(context)
            self.report({'WARNING'}, "O preset nao trouxe nenhum objeto")
            return {'CANCELLED'}

        self._base = {o: o.location.copy() for o in self._raizes}
        self._altura = context.scene.cursor.location.z
        self._alvo = None
        self._normal = Vector((0.0, 0.0, 1.0))
        self._bbox_atual = []
        self._valido = False
        self._em_superficie = False
        self._handler_preview = None

        try:
            self._preparar_bbox(context)
            self._ocultar_staging(context)
            self._handler_preview = bpy.types.SpaceView3D.draw_handler_add(
                self._desenhar_preview, (), 'WINDOW', 'POST_VIEW')
        except Exception as e:
            print("[Cabinet Creator] preview do arraste:", e)
            self._apagar()
            self._restaurar_selecao(context)
            self.report({'ERROR'}, "Nao consegui preparar o preview")
            return {'CANCELLED'}

        try:
            item = _achar_item(self.pasta, self.arquivo)
            nome = item.get("nome", self.arquivo) if item else self.arquivo
            context.workspace.status_text_set(
                "Arrastando %s | Solte: inserir | Botao direito: cancelar"
                % nome)
        except Exception:
            pass
        self._mover(context, event)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _preparar_bbox(self, context):
        """Mede o staging avaliado e define a ancora no centro da base."""
        context.view_layer.update()
        try:
            dep = context.evaluated_depsgraph_get()
        except Exception:
            dep = None
        pontos = []
        for obj in self._novos:
            if obj.type in TIPOS_COM_VOLUME:
                pontos.extend(_cantos_avaliados(obj, dep))
        if not pontos:
            pontos = [o.matrix_world.translation.copy() for o in self._raizes]
        if not pontos:
            raise RuntimeError("preset sem geometria")

        lo = Vector(tuple(min(p[i] for p in pontos) for i in range(3)))
        hi = Vector(tuple(max(p[i] for p in pontos) for i in range(3)))
        self._bbox_base = (
            Vector((lo.x, lo.y, lo.z)), Vector((hi.x, lo.y, lo.z)),
            Vector((hi.x, hi.y, lo.z)), Vector((lo.x, hi.y, lo.z)),
            Vector((lo.x, lo.y, hi.z)), Vector((hi.x, lo.y, hi.z)),
            Vector((hi.x, hi.y, hi.z)), Vector((lo.x, hi.y, hi.z)),
        )
        self._ancora_base = Vector((
            (lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, lo.z))
        diagonal = (hi - lo).length
        self._tamanho_mira = max(0.04, min(diagonal * 0.08, 0.35))

    def _ocultar_staging(self, context):
        """Esconde a geometria real para deixar somente o preview GPU."""
        self._visibilidade = []
        for obj in self._novos:
            self._visibilidade.append(
                (obj, bool(obj.hide_viewport), bool(obj.hide_get())))
            obj.hide_set(True)
            obj.hide_viewport = True
        context.view_layer.update()

    def _restaurar_staging(self):
        for obj, global_oculto, local_oculto in getattr(
                self, "_visibilidade", []):
            try:
                obj.hide_viewport = global_oculto
                obj.hide_set(local_oculto)
            except (ReferenceError, RuntimeError):
                pass

    def _restaurar_selecao(self, context):
        try:
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in self._selecionados_antes:
                if obj.name in bpy.data.objects:
                    obj.select_set(True)
            if (self._ativo_antes is not None and
                    self._ativo_antes.name in bpy.data.objects):
                context.view_layer.objects.active = self._ativo_antes
        except (ReferenceError, RuntimeError):
            pass

    def _encerrar_visual(self, context):
        if self._handler_preview is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(
                    self._handler_preview, 'WINDOW')
            except Exception:
                pass
            self._handler_preview = None
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
        if context.area is not None:
            context.area.tag_redraw()
        if getattr(self, '_area_preview', None) is not None:
            self._area_preview.tag_redraw()

    def _desenhar_preview(self):
        """Desenha box e mira sobre a viewport sem criar geometria."""
        if not self._valido or not self._bbox_atual:
            return
        regiao = getattr(bpy.context, "region", None)
        if regiao is None or regiao.as_pointer() != self._regiao_ptr:
            return

        arestas = (
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        )
        linhas_box = []
        for a, b in arestas:
            linhas_box.extend((self._bbox_atual[a], self._bbox_atual[b]))

        normal = self._normal.normalized()
        referencia = (Vector((0.0, 0.0, 1.0))
                      if abs(normal.z) < 0.9 else Vector((1.0, 0.0, 0.0)))
        tangente = normal.cross(referencia).normalized()
        bitangente = normal.cross(tangente).normalized()
        tamanho = self._tamanho_mira
        alvo = self._alvo
        linhas_mira = (
            alvo - tangente * tamanho, alvo + tangente * tamanho,
            alvo - bitangente * tamanho, alvo + bitangente * tamanho,
            alvo - normal * tamanho * 0.35,
            alvo + normal * tamanho * 0.35,
        )

        try:
            gpu.state.blend_set('ALPHA')
            gpu.state.depth_test_set('NONE')
            gpu.state.line_width_set(1.5)
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            shader.bind()
            shader.uniform_float("color", (0.1, 1.0, 0.2, 0.9))
            batch_for_shader(
                shader, 'LINES', {"pos": linhas_box}).draw(shader)
            shader.uniform_float(
                "color", (1.0, 0.85, 0.1, 1.0)
                if self._em_superficie else (0.9, 0.9, 0.9, 1.0))
            batch_for_shader(
                shader, 'LINES', {"pos": linhas_mira}).draw(shader)
        except Exception as e:
            print("[Cabinet Creator] desenho do preview:", e)
        finally:
            try:
                gpu.state.line_width_set(1.0)
                gpu.state.depth_test_set('NONE')
                gpu.state.blend_set('NONE')
            except Exception:
                pass

    def _na_viewport(self, event):
        """O solte so' vale dentro da viewport, como no arraste nativo."""
        dx = event.mouse_x - self._regiao.x
        dy = event.mouse_y - self._regiao.y
        return 0 <= dx < self._regiao.width and 0 <= dy < self._regiao.height

    def _mover(self, context, event):
        """Usa raycast na cena e plano do cursor como contingencia."""
        if not self._na_viewport(event):
            self._valido = False
            self._area_preview.tag_redraw()
            return
        coord = (event.mouse_x - self._regiao.x, event.mouse_y - self._regiao.y)
        try:
            origem = view3d_utils.region_2d_to_origin_3d(
                self._regiao, self._rv3d, coord)
            direcao = view3d_utils.region_2d_to_vector_3d(
                self._regiao, self._rv3d, coord)
        except Exception:
            return
        alvo = None
        normal = Vector((0.0, 0.0, 1.0))
        self._em_superficie = False
        try:
            dep = context.evaluated_depsgraph_get()
            acerto, local, normal_hit, _face, obj_hit, _matriz = (
                context.scene.ray_cast(
                    dep, origem, direcao, distance=1000000.0))
            if acerto and obj_hit not in self._novos:
                alvo = local.copy()
                normal = normal_hit.copy()
                self._em_superficie = True
        except Exception as e:
            print("[Cabinet Creator] raycast do arraste:", e)
        if alvo is None:
            alvo = intersect_line_plane(
                origem, origem + direcao * 1000.0,
                Vector((0.0, 0.0, self._altura)),
                Vector((0.0, 0.0, 1.0)))
        if alvo is None:        # raio paralelo ao plano: nada a fazer
            self._valido = False
            self._area_preview.tag_redraw()
            return
        deslocamento = alvo - self._ancora_base
        for o in self._raizes:
            base = self._base.get(o)
            if base is not None:
                o.location = base + deslocamento
        self._alvo = alvo
        self._normal = normal
        self._bbox_atual = [p + deslocamento for p in self._bbox_base]
        self._valido = True
        self._area_preview.tag_redraw()

    def _apagar(self):
        for o in list(self._novos):
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass
        for colecao in list(getattr(self, "_colecoes_novas", [])):
            try:
                if colecao.name in bpy.data.collections:
                    bpy.data.collections.remove(colecao)
            except (ReferenceError, RuntimeError):
                pass

    def _cancelar(self, context):
        self._encerrar_visual(context)
        self._apagar()
        self._restaurar_selecao(context)
        if context.area is not None:
            context.area.tag_redraw()
        return {'CANCELLED'}

    def _duplo_clique_na_foto(self, context, event):
        """Segundo clique, rapido e no mesmo lugar do que abriu o
        posicionador, fora da viewport.

        Medido AQUI, pelo relogio: o Blender entrega esse segundo clique
        como PRESS, nao DOUBLE_CLICK (confirmado no log do usuario --
        PRESS 67 ms depois do RELEASE), porque o primeiro foi consumido
        pela gaveta. Esperando so' DOUBLE_CLICK, o PRESS caia no "clique
        fora da viewport" e cancelava a insercao.
        """
        if (event.type != 'LEFTMOUSE'
                or event.value not in {'PRESS', 'DOUBLE_CLICK'}
                or self._na_viewport(event)):
            return False
        if event.value == 'DOUBLE_CLICK':
            return True
        try:
            limite = context.preferences.inputs.mouse_double_click_time
        except Exception:
            limite = 350
        dx = event.mouse_x - self._mouse_inicio[0]
        dy = event.mouse_y - self._mouse_inicio[1]
        return ((time.monotonic() - self._instante_inicio) * 1000.0 <= limite
                and dx * dx + dy * dy <= RAIO_DUPLO_CLIQUE_PX ** 2)

    def _no_cursor(self, context):
        """Centro da base do preset no cursor 3D, e confirma."""
        deslocamento = context.scene.cursor.location - self._ancora_base
        for o in self._raizes:
            base = self._base.get(o)
            if base is not None:
                o.location = base + deslocamento
        self._valido = True
        return self._confirmar(context)

    def _confirmar(self, context):
        self._encerrar_visual(context)
        self._restaurar_staging()
        try:
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in self._novos:
                obj.select_set(True)
            if self._raizes:
                context.view_layer.objects.active = self._raizes[0]
            elif self._novos:
                context.view_layer.objects.active = self._novos[0]
            context.view_layer.update()
        except (ReferenceError, RuntimeError):
            pass
        self.report({'INFO'}, "%d objeto(s) inserido(s)" % len(self._novos))
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            if self._arrastando and not self._moveu:
                dx = event.mouse_x - self._mouse_inicio[0]
                dy = event.mouse_y - self._mouse_inicio[1]
                # O limiar evita transformar um clique com pequena
                # oscilacao involuntaria em arraste.
                self._moveu = (dx * dx + dy * dy) >= 36
            self._mover(context, event)
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE':   # DIAGNOSTICO TEMPORARIO
            _log_clique('posicionador %s viewport=%s arrastando=%s moveu=%s'
                        % (event.value, self._na_viewport(event),
                           self._arrastando, self._moveu))
        if self._duplo_clique_na_foto(context, event):
            # Duplo clique na FOTO (o primeiro clique abriu este
            # posicionador): entra direto no cursor 3D, sem mirar.
            return self._no_cursor(context)
        if event.type == 'LEFTMOUSE':
            confirma = 'RELEASE' if self._arrastando else 'PRESS'
            if event.value == confirma:
                if self._arrastando and not self._moveu:
                    # O clique sem arraste ativa o mesmo posicionador. Esse
                    # fallback e' indispensavel porque algumas versoes/temas
                    # do Blender retêm o drag do botao da interface.
                    self._arrastando = False
                    try:
                        context.workspace.status_text_set(
                            "Posicionamento ativo | Clique na viewport: "
                            "inserir | Botao direito: cancelar")
                    except Exception:
                        pass
                    return {'RUNNING_MODAL'}
                if not self._na_viewport(event):
                    return self._cancelar(context)
                if not self._valido:
                    self.report({'WARNING'}, "Posicione dentro da viewport")
                    return self._cancelar(context)
                return self._confirmar(context)
        if (event.type in {'RET', 'NUMPAD_ENTER'} and
                event.value == 'PRESS'):
            if not self._valido:
                self.report({'WARNING'}, "Posicione dentro da viewport")
                return {'RUNNING_MODAL'}
            return self._confirmar(context)
        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            return self._cancelar(context)
        if event.type == 'WINDOW_DEACTIVATE':
            return self._cancelar(context)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._cancelar(context)


class OBJECT_OT_navegar(Operator):
    """Seleciona um nivel da cascata"""
    bl_idname = "object.cabinet_navegar"
    bl_label = "Navegar"

    nivel: bpy.props.IntProperty(default=1)
    valor: bpy.props.StringProperty()

    def execute(self, context):
        s = context.scene
        if self.nivel == 1:
            s.chapa_n1 = "" if s.chapa_n1 == self.valor else self.valor
            s.chapa_n2 = ""
            s.chapa_n3 = ""
        elif self.nivel == 2:
            s.chapa_n2 = "" if s.chapa_n2 == self.valor else self.valor
            s.chapa_n3 = ""
        else:
            s.chapa_n3 = "" if s.chapa_n3 == self.valor else self.valor
        return {'FINISHED'}


# ======================================= MINIATURAS E WIREFRAME DE MEDIDAS
_previews = [None]

# O canvas e o scale do template sao fixos de proposito: alargar a sidebar
# nao deve ampliar a representacao. Cada proporcao e' normalizada para ocupar
# a area util maxima sem deformar ou ultrapassar as margens internas.
WIREFRAME_LARGURA_PX = 160
WIREFRAME_ALTURA_PX = 160
WIREFRAME_MARGEM_ESQUERDA_PX = 14.0
WIREFRAME_MARGEM_DIREITA_PX = 2.0
WIREFRAME_MARGEM_Y_PX = 20.0
WIREFRAME_LINHA_PX = 0.45
WIREFRAME_ESCALA_MIN_UI = 5.0
WIREFRAME_ESCALA_MAX_UI = 9.0
WIREFRAME_ESCALA_ESTREITA_MAX_UI = WIREFRAME_ESCALA_MAX_UI
WIREFRAME_LARGURA_EMPILHAR_PX = 310.0
MEDIDAS_LARGURA_COLUNA_UNICA_PX = 210.0
MEDIDAS_OCUPACAO_COLUNA_UNICA = 0.80
MEDIDAS_LARGURA_CONTROLES_UI = 4.5
WIREFRAME_CACHE_MAX = 48
MINIMO_ESPESSURA_WIREFRAME = 0.07
WIREFRAME_PREFIXO = "wireframe:v15:"
_wireframe_ordem = []

# Vertices: frente (0, 1, 5, 4), fundo (2, 3, 7, 6) e ligacoes.
_ARESTAS_WIREFRAME = (
    (0, 1), (1, 5), (5, 4), (4, 0),
    (2, 3), (3, 7), (7, 6), (6, 2),
    (0, 2), (1, 3), (5, 7), (4, 6),
)

# Fonte minima 5x7. Os indicadores fazem parte do buffer procedural e nao
# dependem de fontes instaladas no sistema.
_FONTE_WIREFRAME = {
    'A': ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    'E': ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    'L': ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    'P': ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
}


def _colecao_previews():
    if _previews[0] is None:
        _previews[0] = bpy.utils.previews.new()
    return _previews[0]


def _cor_wireframe(context):
    """Cor de texto do tema, para contrastar em temas claros e escuros."""
    try:
        cor = context.preferences.themes[0].user_interface.wcol_regular.text
        return tuple(max(0.0, min(1.0, float(v))) for v in cor[:3])
    except Exception:
        return (0.9, 0.9, 0.9)


def _caixas_das_folhas(largura, altura, profundidade, folhas):
    """Vertices das folhas na face frontal, nos eixos da caixa.

    Proporcoes de DESENHO, nao medidas: o preview e' um esquema. A
    folha recua 4% das bordas e avanca 8% da profundidade, que e' o que
    deixa a blocagem legivel em 160 px.
    """
    if folhas <= 0:
        return []
    recuo = min(largura, altura) * 0.04
    fundo = max(profundidade * 0.08, 1e-6)
    vao = largura - 2.0 * recuo
    if vao <= 0.0 or altura - 2.0 * recuo <= 0.0:
        return []
    vaz = vao * 0.02
    passo = (vao + vaz) / folhas
    z0, z1 = recuo, altura - recuo
    caixas = []
    for i in range(folhas):
        x0 = recuo + i * passo
        x1 = x0 + passo - vaz
        caixas.append([(x0, 0.0, z0), (x1, 0.0, z0),
                       (x0, fundo, z0), (x1, fundo, z0),
                       (x0, 0.0, z1), (x1, 0.0, z1),
                       (x0, fundo, z1), (x1, fundo, z1)])
    return caixas


def _pontos_wireframe(largura, altura, profundidade, extras=()):
    """Projeta a 45 graus e ajusta a proporcao a area util do canvas.

    `extras` sao vertices nos MESMOS eixos da caixa (por exemplo as
    folhas); voltam projetados logo apos os 8 cantos, para que nada
    saia com escala diferente da caixa.
    """
    medidas = (float(largura), float(altura), float(profundidade))
    if not all(math.isfinite(v) and v > 0.0 for v in medidas):
        return None
    L, A, P = medidas
    vertices = (
        (0.0, 0.0, 0.0), (L, 0.0, 0.0),
        (0.0, P, 0.0), (L, P, 0.0),
        (0.0, 0.0, A),   (L, 0.0, A),
        (0.0, P, A),     (L, P, A),
    ) + tuple(extras)
    diagonal = math.sqrt(0.5)  # cos(45) == sin(45)
    projetados = [(x - y * diagonal, z + y * diagonal)
                  for x, y, z in vertices]
    # Os limites saem dos 8 cantos da CAIXA: incluir as folhas mudaria
    # a escala e o modulo apareceria menor do que e'.
    caixa = projetados[:8]
    min_x = min(p[0] for p in caixa)
    max_x = max(p[0] for p in caixa)
    min_y = min(p[1] for p in caixa)
    max_y = max(p[1] for p in caixa)
    largura_proj = max_x - min_x
    altura_proj = max_y - min_y
    util_l = (WIREFRAME_LARGURA_PX - WIREFRAME_MARGEM_ESQUERDA_PX -
              WIREFRAME_MARGEM_DIREITA_PX)
    util_a = WIREFRAME_ALTURA_PX - 2.0 * WIREFRAME_MARGEM_Y_PX
    if (largura_proj <= 0.0 or altura_proj <= 0.0 or
            util_l <= 0.0 or util_a <= 0.0):
        return None

    escala = min(util_l / largura_proj, util_a / altura_proj)
    desenho_l = largura_proj * escala
    desenho_a = altura_proj * escala
    dx = WIREFRAME_MARGEM_ESQUERDA_PX - min_x * escala
    dy = (WIREFRAME_ALTURA_PX - desenho_a) / 2.0 - min_y * escala
    return [(x * escala + dx, y * escala + dy) for x, y in projetados]


def _desenhar_segmento(buffer, p0, p1, cor):
    """Rasteriza um segmento antialias somente dentro de sua caixa local."""
    largura = WIREFRAME_LARGURA_PX
    altura = WIREFRAME_ALTURA_PX
    x0, y0 = p0
    x1, y1 = p1
    vx, vy = x1 - x0, y1 - y0
    comp2 = vx * vx + vy * vy
    if comp2 <= 1e-12:
        return
    raio = WIREFRAME_LINHA_PX / 2.0
    alcance = raio + 1.0
    xa = max(0, int(math.floor(min(x0, x1) - alcance)))
    xb = min(largura - 1, int(math.ceil(max(x0, x1) + alcance)))
    ya = max(0, int(math.floor(min(y0, y1) - alcance)))
    yb = min(altura - 1, int(math.ceil(max(y0, y1) + alcance)))
    cr, cg, cb = cor

    for y in range(ya, yb + 1):
        py = y + 0.5
        for x in range(xa, xb + 1):
            px = x + 0.5
            t = ((px - x0) * vx + (py - y0) * vy) / comp2
            t = max(0.0, min(1.0, t))
            perto_x = x0 + t * vx
            perto_y = y0 + t * vy
            distancia = math.hypot(px - perto_x, py - perto_y)
            cobertura = max(0.0, min(1.0, raio + 0.75 - distancia))
            if cobertura <= 0.0:
                continue
            # ImagePreview usa a origem embaixo; os pontos tambem usam Y para
            # cima, portanto nao e' preciso inverter a linha neste buffer.
            i = (y * largura + x) * 4
            if cobertura > buffer[i + 3]:
                buffer[i] = cr
                buffer[i + 1] = cg
                buffer[i + 2] = cb
                buffer[i + 3] = cobertura


def _desenhar_indicador(buffer, letra, x, y, cor, escala=2):
    """Desenha uma letra 5x7 centralizada em (x, y)."""
    glifo = _FONTE_WIREFRAME.get(letra)
    if glifo is None:
        return
    largura = len(glifo[0]) * escala
    altura = len(glifo) * escala
    inicio_x = int(round(x - largura / 2.0))
    inicio_y = int(round(y - altura / 2.0))
    cr, cg, cb = cor
    for linha, bits in enumerate(reversed(glifo)):
        for coluna, bit in enumerate(bits):
            if bit != '1':
                continue
            for sy in range(escala):
                py = inicio_y + linha * escala + sy
                if py < 0 or py >= WIREFRAME_ALTURA_PX:
                    continue
                for sx in range(escala):
                    px = inicio_x + coluna * escala + sx
                    if px < 0 or px >= WIREFRAME_LARGURA_PX:
                        continue
                    i = (py * WIREFRAME_LARGURA_PX + px) * 4
                    buffer[i] = cr
                    buffer[i + 1] = cg
                    buffer[i + 2] = cb
                    buffer[i + 3] = 1.0


def _meio_wireframe(p0, p1):
    return ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)


def _desenhar_indicadores(buffer, pontos, cor, modo, trocado=False):
    """Identifica as direcoes sem adicionar cotas ou linhas auxiliares.

    'INDIVIDUAL' (chapa): L, A e E. Na chapa a aresta VERTICAL do
        desenho e' a espessura -- `_visual_wireframe` passa a espessura
        na posicao da altura -- e a aresta que recua e' a altura da peca.
    'GRUPO' (modulo de chapas): L, A, P e mais o E na quina inferior
        direita. A espessura nao tem aresta propria no modulo, mas e'
        medida dele e precisa aparecer.
    'LIVRE' (objeto sem assinatura do addon): so' L, A e P. Sem chapas
        no meio, nao existe espessura para anunciar.
    """
    topo = _meio_wireframe(pontos[6], pontos[7])
    fundo = _meio_wireframe(pontos[0], pontos[2])
    vertical = _meio_wireframe(pontos[2], pontos[6])
    _desenhar_indicador(buffer, 'P' if trocado else 'L',
                        topo[0], topo[1] + 10.0, cor)

    if modo == 'INDIVIDUAL':
        _desenhar_indicador(
            buffer, 'E', max(5.0, vertical[0] - 9.0), vertical[1], cor)
        _desenhar_indicador(
            buffer, 'A', fundo[0] - 9.0, fundo[1] - 8.0, cor)
        return

    if modo == 'PORTA':
        _desenhar_indicador(
            buffer, 'A', max(5.0, vertical[0] - 9.0), vertical[1], cor)
        _desenhar_indicador(
            buffer, 'E', fundo[0] - 9.0, fundo[1] - 8.0, cor)
        return

    _desenhar_indicador(
        buffer, 'A', max(5.0, vertical[0] - 9.0), vertical[1], cor)
    _desenhar_indicador(
        buffer, 'L' if trocado else 'P', fundo[0] - 9.0, fundo[1] - 8.0, cor)
    if modo == 'GRUPO':
        # Canto inferior direito da projecao. A letra desce para a
        # margem de baixo em vez de sair pela direita: a margem lateral
        # e' de poucos pixels e `_desenhar_indicador` corta calado.
        quina = pontos[1]
        _desenhar_indicador(
            buffer, 'E', quina[0] - 8.0, quina[1] - 9.0, cor)


def _rasterizar_wireframe(largura, altura, profundidade, cor, modo='GRUPO',
                         folhas=0, trocado=False):
    """Pixels RGBA das 12 arestas do box, mais as folhas na frente."""
    caixas = _caixas_das_folhas(largura, altura, profundidade, folhas)
    extras = [v for caixa in caixas for v in caixa]
    pontos = _pontos_wireframe(largura, altura, profundidade, extras)
    if pontos is None:
        return None
    n = WIREFRAME_LARGURA_PX * WIREFRAME_ALTURA_PX * 4
    buffer = [0.0] * n
    for a, b in _ARESTAS_WIREFRAME:
        _desenhar_segmento(buffer, pontos[a], pontos[b], cor)
    for i in range(len(caixas)):
        base = 8 + i * 8
        for a, b in _ARESTAS_WIREFRAME:
            _desenhar_segmento(buffer, pontos[base + a], pontos[base + b], cor)
    _desenhar_indicadores(buffer, pontos, cor, modo, trocado)
    return _centralizar_wireframe(buffer)


def _centralizar_wireframe(buffer):
    """Centraliza o conteudo VISIVEL, incluindo as letras L/A/P/E."""
    largura, altura = WIREFRAME_LARGURA_PX, WIREFRAME_ALTURA_PX
    ocupados = [i // 4 for i in range(0, len(buffer), 4)
                if buffer[i + 3] > 0.0]
    if not ocupados:
        return buffer
    xs = [p % largura for p in ocupados]
    ys = [p // largura for p in ocupados]
    dx = int(round(((largura - 1) - (min(xs) + max(xs))) / 2.0))
    dy = int(round(((altura - 1) - (min(ys) + max(ys))) / 2.0))
    if dx == 0 and dy == 0:
        return buffer
    centralizado = [0.0] * len(buffer)
    for p in ocupados:
        x, y = p % largura, p // largura
        nx, ny = x + dx, y + dy
        if 0 <= nx < largura and 0 <= ny < altura:
            origem = p * 4
            destino = (ny * largura + nx) * 4
            centralizado[destino:destino + 4] = buffer[origem:origem + 4]
    return centralizado


# ==================================== BARRA DE TAMANHO (estilo volume)
# O bpy nao tem slider de trilho fino com knob redondo: o `slider=True`
# nativo pinta a barra inteira e escreve o valor por cima. Esta aqui e'
# rasterizada -- mesma tecnica do wireframe -- e fica clicavel porque e'
# montada em FATIAS: cada fatia e' um botao de operador que grava o seu
# proprio valor, e o clique cai na fatia certa sem precisar adivinhar
# coordenada nenhuma (o bpy nao informa onde o botao foi desenhado).
BARRA_PREFIXO = "barra:v2:"
BARRA_PX = 40               # lado da fatia rasterizada, em pixels
PX_FATIA_BARRA = 18.0       # largura que o icone ocupa ao ser desenhado
PX_BOTAO_BIBLIOTECA = 34.0  # o botao do Asset Browser, ao lado da barra
BARRA_TRILHO = 0.14         # espessura do trilho, fracao do lado
BARRA_KNOB = 0.62           # diametro do knob, fracao do lado
AMOSTRAS_BARRA = 4          # supersampling por pixel (4x4)
COR_BARRA_VAZIA = (0.322, 0.298, 0.290)
COR_BARRA_CHEIA = (1.0, 1.0, 1.0)


def _cobertura_disco(x, y, cx, cy, raio, amostras=AMOSTRAS_BARRA):
    """Quanto do pixel (x, y) o disco cobre, de 0 a 1.

    Supersampling na marra: o icone e' reduzido pelo Blender na hora de
    desenhar, e um circulo cru vira losango depois dessa reducao.
    """
    dentro = 0
    passo = 1.0 / amostras
    for sy in range(amostras):
        py = y - 0.5 + (sy + 0.5) * passo
        for sx in range(amostras):
            px = x - 0.5 + (sx + 0.5) * passo
            if math.hypot(px - cx, py - cy) <= raio:
                dentro += 1
    return dentro / float(amostras * amostras)


def _fatia_barra(indice, ativo, ultimo):
    """Pixels RGBA de UMA fatia: trecho do trilho + knob se for a ativa.

    O trilho vem cheio ate' a fatia ativa e vazio depois dela, que e' a
    leitura imediata de "quanto esta' ligado".
    """
    lado = BARRA_PX
    buffer = [0.0] * (lado * lado * 4)
    meio = (lado - 1) / 2.0
    meia_esp = max(1.0, lado * BARRA_TRILHO / 2.0)
    raio = lado * BARRA_KNOB / 2.0
    cor = COR_BARRA_CHEIA if indice <= ativo else COR_BARRA_VAZIA

    for y in range(lado):
        dy = abs(y - meio)
        for x in range(lado):
            alfa, c = 0.0, cor
            # trilho: faixa horizontal, bordas suavizadas
            if dy <= meia_esp - 0.5:
                alfa = 1.0
            elif dy <= meia_esp + 0.5:
                alfa = meia_esp + 0.5 - dy
            # pontas arredondadas so' nas fatias das extremidades
            if indice == 0 and x < meia_esp:
                alfa = min(alfa, _cobertura_disco(x, y, meia_esp, meio,
                                                  meia_esp))
            if indice == ultimo and x > lado - 1 - meia_esp:
                alfa = min(alfa, _cobertura_disco(
                    x, y, lado - 1 - meia_esp, meio, meia_esp))
            # knob por cima, sempre branco
            if indice == ativo:
                cob = _cobertura_disco(x, y, meio, meio, raio)
                if cob > 0.0:
                    if cob >= alfa:
                        c = COR_BARRA_CHEIA
                    alfa = max(alfa, cob)
            if alfa <= 0.0:
                continue
            i = (y * lado + x) * 4
            buffer[i] = c[0]
            buffer[i + 1] = c[1]
            buffer[i + 2] = c[2]
            buffer[i + 3] = min(1.0, alfa)
    return buffer


def _icone_fatia_barra(indice, ativo, ultimo):
    """icon_id de uma fatia, reaproveitado pelo cache de previews."""
    chave = BARRA_PREFIXO + "%d:%d:%d" % (indice, ativo, ultimo)
    colecao = _colecao_previews()
    if chave not in colecao:
        try:
            preview = colecao.new(chave)
            tamanho = (BARRA_PX, BARRA_PX)
            pixels = _fatia_barra(indice, ativo, ultimo)
            preview.icon_size = tamanho
            preview.icon_pixels_float = pixels
            preview.image_size = tamanho
            preview.image_pixels_float = pixels
        except Exception as e:
            print("[Cabinet Creator] barra:", e)
            return 0
    try:
        return colecao[chave].icon_id
    except Exception:
        return 0


def _metrica_barra(context, disponivel=None):
    """(fatias, largura logica da celula, compressao) da barra.

    Um lugar so' porque o DESENHO e o ARRASTE precisam concordar: se a
    celula medir diferente dos dois lados, o knob anda fora do dedo.
    """
    prop = bpy.types.Scene.bl_rna.properties["chapa_tam_bloco"]
    fatias = prop.hard_max - prop.hard_min + 1
    if disponivel is None:
        disponivel = max(1.0, PX_FATIA_BARRA * fatias)
    disponivel = max(1.0, disponivel)
    # scale_x encolhe a celula ate' o tamanho do icone; acima de 1.0 nao
    # adianta (o icone nao estica), entao a celula fica menor que o alvo
    compressao = min(1.0, PX_FATIA_BARRA * fatias / disponivel)
    celula = min(PX_FATIA_BARRA, disponivel / fatias)
    return fatias, celula, compressao


# ====================================== FOTO CLICAVEL (fatiada)
# `template_icon` amplia a foto mas NAO recebe evento, e o icone de um
# botao de operador nao passa de ~16 px por mais que se aumente
# scale_x/scale_y (medido). Para a foto inteira ficar clicavel ela e'
# cortada em ladrilhos, cada um o icone de um botao: o mosaico parece
# uma imagem so' e qualquer ponto dela aciona o posicionador.
FOTO_PREFIXO = "foto:v2:"
# Rasterizar em 24 e desenhar em 16 obrigava o Blender a reamostrar
# cada ladrilho (1,5x) e aparecia bandeamento nas faces lisas. Os
# dois tamanhos precisam ser IGUAIS: assim o desenho e' 1:1.
FOTO_TILE_PX = 16
# 16 px e' a largura REAL com que o Blender desenha o icone de um
# botao; 18 deixava 2 px de fresta e o mosaico virava xadrez.
PX_TILE_FOTO = 16.0
# Alvo da CELULA, de proposito menor que o icone: mirar nos 16 px
# exige acertar a largura do bloco na mosca, e ela e' estimada --
# qualquer desvio abre fresta e a foto fica picotada. Com folga, a
# celula fica sempre abaixo do icone em qualquer largura.
PX_ALVO_CELULA = 16.0
# ui_units_x sozinho nao encosta as colunas: sobra folga lateral
# em cada celula. O valor abaixo foi achado por captura de tela.
COMPRESSAO_TILE_FOTO = 0.7


# Folgas medidas por captura: o box da lista come' um tanto da
# largura do painel, e cada bloco tem a sua propria margem interna.
PADDING_GRADE = 34.0
PADDING_BLOCO = 12.0


def _metrica_blocos(context, tamanho):
    """(colunas, largura de cada bloco) da grade de presets.

    As colunas precisam ser EXPLICITAS. Com `columns=0` quem decide a
    largura do bloco e' o bpy, e a foto clicavel -- um mosaico de
    icones de 16 px -- so' fica sem fresta quando essa largura e'
    conhecida: `ui_units_x` e' ignorado dentro do grid_flow (medido) e
    `scale_x` encolhe o proprio icone, deformando a imagem.
    """
    util = max(1.0, _largura_painel(context) - PADDING_GRADE)
    # O mosaico da foto so' fica sem listras quando a celula
    # (largura_do_bloco / ladrilhos) cai perto dos 16 px do icone.
    # Blocos largos demais fazem a conta desviar e aparecem bandas;
    # 20 px por grau de tamanho mantem o bloco na faixa que fecha.
    alvo = max(64.0, float(tamanho) * 20.0)
    colunas = max(1, min(6, int(util // alvo)))
    return colunas, util / colunas


def _foto_clicavel_ligada():
    """Preferencia: foto clicavel (mosaico) ou foto perfeita."""
    p = _prefs()
    return bool(p and getattr(p, "foto_clicavel", False))


def _tiles_foto(pasta, png, lado):
    """icon_id de cada ladrilho da foto, em grade `lado` x `lado`.

    Devolve as linhas de CIMA para BAIXO, que e' a ordem em que a UI
    desenha -- os pixels do Blender vem de baixo para cima.
    """
    colecao = _colecao_previews()
    base = FOTO_PREFIXO + "%s|%s:%d:" % (pasta, png, lado)
    if (base + "0:0") not in colecao:
        n = lado * FOTO_TILE_PX
        pixels = _pixels_png(os.path.join(pasta, png), n)
        if not pixels:
            return None
        for j in range(lado):
            for i in range(lado):
                buf = []
                for y in range(FOTO_TILE_PX):
                    ini = ((j * FOTO_TILE_PX + y) * n
                           + i * FOTO_TILE_PX) * 4
                    buf.extend(pixels[ini:ini + FOTO_TILE_PX * 4])
                try:
                    pv = colecao.new(base + "%d:%d" % (i, j))
                except Exception as e:
                    print("[Cabinet Creator] foto:", e)
                    return None
                tam = (FOTO_TILE_PX, FOTO_TILE_PX)
                pv.icon_size = tam
                pv.icon_pixels_float = buf
                pv.image_size = tam
                pv.image_pixels_float = buf
    try:
        return [[colecao[base + "%d:%d" % (i, j)].icon_id
                 for i in range(lado)]
                for j in range(lado - 1, -1, -1)]
    except Exception as e:
        print("[Cabinet Creator] foto:", e)
        return None


class OBJECT_OT_definir_tamanho(Operator):
    """Tamanho das miniaturas da biblioteca.

    A barra responde a CLIQUE, nao a arraste, e isso nao tem conserto
    pela API: o bpy nao permite criar um tipo de widget novo. Um botao
    de painel e' tratado pelo handler de UI, que consome o PRESS antes
    de qualquer keymap -- nem `head=True` no keymap "User Interface"
    passa na frente. O que se desenha (imagem, icone) nao recebe
    evento; o que recebe evento (botao) nao se desenha do nosso jeito.
    Ja' foi tentado: keymap PRESS e CLICK_DRAG + modal relativo.
    """
    bl_idname = "object.cabinet_tamanho"
    bl_label = "Tamanho dos Blocos"

    valor: bpy.props.IntProperty(default=5)

    def execute(self, context):
        context.scene.chapa_tam_bloco = self.valor
        return {'FINISHED'}


def _chave_wireframe(modo, largura, altura, profundidade, cor, folhas=0):
    medidas = tuple(round(float(v), 1)
                    for v in (largura, altura, profundidade))
    rgb = tuple(round(float(v) * 255.0) for v in cor)
    return WIREFRAME_PREFIXO + "%s:%.1f:%.1f:%.1f:%d:%d:%d:%d" % (
        modo, medidas[0], medidas[1], medidas[2], rgb[0], rgb[1], rgb[2],
        int(folhas))


def _registrar_uso_wireframe(chave, colecao):
    if chave in _wireframe_ordem:
        _wireframe_ordem.remove(chave)
    _wireframe_ordem.append(chave)
    while len(_wireframe_ordem) > WIREFRAME_CACHE_MAX:
        antiga = _wireframe_ordem.pop(0)
        if antiga in colecao:
            try:
                del colecao[antiga]
            except Exception:
                pass


def _icone_wireframe(context, modo, largura, altura, profundidade, folhas=0):
    """Cria ou reutiliza o icon_id horizontal para estas medidas."""
    cor = _cor_wireframe(context)
    chave = _chave_wireframe(modo, largura, altura, profundidade, cor, folhas)
    colecao = _colecao_previews()
    if chave not in colecao:
        pixels = _rasterizar_wireframe(
            largura, altura, profundidade, cor, modo=modo, folhas=folhas)
        if pixels is None:
            return 0
        try:
            preview = colecao.new(chave)
            tamanho = (WIREFRAME_LARGURA_PX, WIREFRAME_ALTURA_PX)
            # Preenche ambos porque a versao do Blender decide qual nivel
            # usar conforme a escala pedida por template_icon.
            preview.icon_size = tamanho
            preview.icon_pixels_float = pixels
            preview.image_size = tamanho
            preview.image_pixels_float = pixels
        except Exception as e:
            if chave in colecao:
                try:
                    del colecao[chave]
                except Exception:
                    pass
            print("[Cabinet Creator] wireframe:", e)
            return 0
    _registrar_uso_wireframe(chave, colecao)
    return colecao[chave].icon_id


def _chave_preview(pasta, arquivo):
    return os.path.join(pasta, arquivo)


def icone_do_item(it):
    """icon_value da foto do preset, ou 0 se nao houver."""
    png = it.get("foto") or (os.path.splitext(it["arquivo"])[0] + ".png")
    caminho = os.path.join(it["pasta"], png)
    if not os.path.exists(caminho):
        return 0
    col = _colecao_previews()
    chave = _chave_preview(it["pasta"], png)
    if chave not in col:
        try:
            col.load(chave, caminho, 'IMAGE')
        except Exception:
            return 0
    return col[chave].icon_id


def _ocupacao_alpha_png(caminho):
    """Maior fracao ocupada pelo alfa, em X ou Y, ou zero se vazio."""
    imagem = None
    try:
        imagem = bpy.data.images.load(caminho, check_existing=False)
        largura, altura = imagem.size
        if largura <= 0 or altura <= 0:
            return 0.0
        # Blender 4.2 nao aceita `step` diretamente no bpy_prop_array.
        alpha = list(imagem.pixels)[3::4]
        min_x, min_y = largura, altura
        max_x = max_y = -1
        for indice, valor in enumerate(alpha):
            if valor <= 0.01:
                continue
            x = indice % largura
            y = indice // largura
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
        if max_x < min_x or max_y < min_y:
            return 0.0
        return max((max_x - min_x + 1) / largura,
                   (max_y - min_y + 1) / altura)
    except Exception as e:
        print("[Cabinet Creator] leitura do alfa:", e)
        return 0.0
    finally:
        if imagem is not None:
            try:
                bpy.data.images.remove(imagem)
            except (ReferenceError, RuntimeError):
                pass


def capturar_viewport(destino_png, camera=None, isolar=None):
    """Foto do modelo a partir da viewport.

    NAO renderiza: usa render OpenGL, ou seja, as cores da propria
    viewport. Overlays desligados removem grade, eixos, gizmos e icones.
    O PNG sai em RGBA transparente e, sem camera explicita, o alvo e'
    enquadrado automaticamente para ocupar a miniatura.

    camera  -- se informada, usa a vista dela. Se nao, e a viewport ja'
               estiver em vista de camera, mantem essa vista; caso
               contrario usa o enquadramento atual da viewport.
    isolar  -- lista de objetos que devem aparecer. Todo o resto da cena
               e' ocultado durante a captura e restaurado depois, para
               que um modulo dentro de uma composicao maior saia sozinho
               na foto.
    """
    cena = bpy.context.scene
    ant = (cena.render.filepath, cena.render.image_settings.file_format,
           cena.render.image_settings.color_mode,
           cena.render.resolution_x, cena.render.resolution_y,
           cena.render.resolution_percentage, cena.render.film_transparent)
    area = next((a for a in bpy.context.screen.areas if a.type == 'VIEW_3D'), None)
    if area is None:
        return False, "Nenhuma viewport 3D visivel"

    espaco = area.spaces.active
    r3d = espaco.region_3d
    ov_ant = espaco.overlay.show_overlays
    vista_ant = (r3d.view_distance, r3d.view_location.copy(),
                 r3d.view_rotation.copy(), r3d.view_perspective,
                 r3d.view_camera_zoom, tuple(r3d.view_camera_offset))
    cam_ant = cena.camera
    selecionados_ant = list(bpy.context.selected_objects)
    ativo_ant = bpy.context.view_layer.objects.active
    escondidos = []
    enquadrar = []

    try:
        if isolar is not None:
            manter = set()
            for o in isolar:
                manter.add(o.name)
                for f in bpy.data.objects:
                    if f.parent is o:
                        manter.add(f.name)
            for o in bpy.context.view_layer.objects:
                if o.name not in manter and not o.hide_get():
                    o.hide_set(True)
                    escondidos.append(o)
                elif o.name in manter:
                    enquadrar.append(o)

        cena.render.image_settings.file_format = 'PNG'
        cena.render.image_settings.color_mode = 'RGBA'
        cena.render.resolution_x = 512
        cena.render.resolution_y = 512
        cena.render.resolution_percentage = 100
        cena.render.film_transparent = True
        cena.render.filepath = destino_png
        espaco.overlay.show_overlays = False

        if camera is not None:
            cena.camera = camera
            r3d.view_perspective = 'CAMERA'
        # Sem camera preserva a orientacao escolhida pelo usuario, mas
        # ajusta centro e distancia para o alvo ocupar a miniatura.

        regiao = next((r for r in area.regions if r.type == 'WINDOW'), None)
        with bpy.context.temp_override(area=area, region=regiao):
            if camera is None and enquadrar:
                # A captura quadrada nao tem a mesma proporcao da viewport
                # larga. ORTHO preserva o angulo, mantem o centro e evita
                # o deslocamento lateral que a perspectiva produziria.
                r3d.view_perspective = 'ORTHO'
                for o in bpy.context.selected_objects:
                    o.select_set(False)
                for o in enquadrar:
                    try:
                        o.select_set(True)
                    except (ReferenceError, RuntimeError):
                        pass
                bpy.context.view_layer.objects.active = enquadrar[0]
                bpy.ops.view3d.view_selected(use_all_regions=False)
                # Uma pequena folga evita cortar antialiasing e objetos
                # muito largos/altos junto ao limite do PNG.
                r3d.view_distance *= 1.12
            bpy.ops.render.opengl(write_still=True, view_context=True)
            if camera is None and enquadrar:
                # `view_selected` enquadra usando a proporcao da viewport,
                # mas o PNG e' quadrado. Mede o alfa real e faz uma segunda
                # passagem para ocupar o mesmo espaco em qualquer sidebar.
                ocupacao = _ocupacao_alpha_png(destino_png)
                if ocupacao > 0.01:
                    fator = max(0.25, min(2.0, ocupacao / 0.82))
                    if abs(fator - 1.0) > 0.03:
                        r3d.view_distance *= fator
                        bpy.ops.render.opengl(write_still=True,
                                              view_context=True)
        return True, destino_png
    except Exception as e:
        return False, str(e)
    finally:
        for o in escondidos:
            try:
                o.hide_set(False)
            except Exception:
                pass
        espaco.overlay.show_overlays = ov_ant
        (r3d.view_distance, r3d.view_location, r3d.view_rotation,
         r3d.view_perspective, r3d.view_camera_zoom,
         r3d.view_camera_offset) = vista_ant
        cena.camera = cam_ant
        for o in bpy.context.selected_objects:
            o.select_set(False)
        for o in selecionados_ant:
            try:
                o.select_set(True)
            except (ReferenceError, RuntimeError):
                pass
        if ativo_ant is not None and ativo_ant.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = ativo_ant
        (cena.render.filepath, cena.render.image_settings.file_format,
         cena.render.image_settings.color_mode,
         cena.render.resolution_x, cena.render.resolution_y,
         cena.render.resolution_percentage, cena.render.film_transparent) = ant


def viewport_em_camera():
    area = next((a for a in bpy.context.screen.areas if a.type == 'VIEW_3D'), None)
    if area is None:
        return False
    return area.spaces.active.region_3d.view_perspective == 'CAMERA'


def _achar_item(pasta, arquivo):
    for it in indice_completo():
        if it["pasta"] == pasta and it["arquivo"] == arquivo:
            return it
    return None


# ========================================== BLOQUEIO E RENOMEAR DOS BLOCOS
def _atualizar_item(pasta, arquivo, mudancas):
    itens = _ler_indice(pasta)
    for i in itens:
        if i.get("arquivo") == arquivo:
            i.update(mudancas)
    _gravar_indice(pasta, itens)


def item_bloqueado(it):
    """Com uma biblioteca so', o cadeado e' por item: nao ha' mais uma
    origem "de fabrica" que force o bloqueio."""
    return bool(it.get("bloqueado", False))


class OBJECT_OT_alternar_bloqueio(Operator):
    """Bloqueia ou desbloqueia a edicao deste bloco"""
    bl_idname = "object.cabinet_bloqueio"
    bl_label = "Bloquear/Desbloquear"

    pasta: bpy.props.StringProperty()
    arquivo: bpy.props.StringProperty()

    def execute(self, context):
        it = _achar_item(self.pasta, self.arquivo)
        if it is None:
            return {'CANCELLED'}
        _atualizar_item(self.pasta, self.arquivo,
                        {"bloqueado": not bool(it.get("bloqueado", False))})
        return {'FINISHED'}


class OBJECT_OT_editar_modelo(Operator):
    """Editar nome, categoria e foto do modelo"""
    bl_idname = "object.cabinet_editar_modelo"
    bl_label = "Editar Modelo"
    bl_options = {'REGISTER'}

    pasta: bpy.props.StringProperty()
    arquivo: bpy.props.StringProperty()
    nome: bpy.props.StringProperty(name="Nome")
    n1: bpy.props.EnumProperty(name="Categoria",
                               items=lambda s, c: [(k, k, "") for k in ARVORE.keys()])
    n2: bpy.props.StringProperty(name="Subcategoria")
    n3: bpy.props.StringProperty(name="Tipo")
    tirar_foto: bpy.props.BoolProperty(
        name="Capturar foto da viewport", default=False,
        description="Salva o enquadramento atual da viewport 3D como foto do modelo")

    def invoke(self, context, event):
        it = _achar_item(self.pasta, self.arquivo)
        if it:
            self.nome = it.get("nome", "")
            a, b, c = _niveis_de(it)
            try:
                self.n1 = a or "Armarios"
            except Exception:
                pass
            self.n2, self.n3 = b, c
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        lay = self.layout
        lay.prop(self, "nome")
        lay.prop(self, "n1")
        lay.prop(self, "n2")
        lay.prop(self, "n3")
        lay.separator()
        it = _achar_item(self.pasta, self.arquivo)
        icone = icone_do_item(it) if it else 0
        cx = lay.box()
        cx.label(text="Foto do modelo")
        if icone:
            cx.template_icon(icon_value=icone, scale=6.0)
        else:
            cx.label(text="sem foto", icon='IMAGE_DATA')
        cx.prop(self, "tirar_foto")

    def execute(self, context):
        it = _achar_item(self.pasta, self.arquivo)
        if it is None:
            self.report({'ERROR'}, "Preset nao encontrado no indice")
            return {'CANCELLED'}
        if item_bloqueado(it):
            self.report({'WARNING'}, "Bloco bloqueado: destrave o cadeado")
            return {'CANCELLED'}

        png = os.path.splitext(self.arquivo)[0] + ".png"
        if self.tirar_foto:
            cam = next((o for o in context.selected_objects if o.type == 'CAMERA'), None)
            alvo = [o for o in context.selected_objects if o.type != 'CAMERA']
            ok, msg = capturar_viewport(os.path.join(self.pasta, png), cam,
                                        isolar=alvo or None)
            if not ok:
                self.report({'WARNING'}, "Foto falhou: " + msg)
            else:
                chave = _chave_preview(self.pasta, png)
                col = _colecao_previews()
                if chave in col:
                    del col[chave]

        itens = _ler_indice(self.pasta)
        for i in itens:
            if i.get("arquivo") == self.arquivo:
                i["nome"] = self.nome
                i["n1"] = self.n1
                i["n2"] = self.n2
                i["n3"] = self.n3
                i.pop("categoria", None)
                i.pop("subcategoria", None)
                i["foto"] = png
        _gravar_indice(self.pasta, itens)
        self.report({'INFO'}, "Modelo atualizado")
        return {'FINISHED'}


class OBJECT_OT_salvar_biblioteca(Operator):
    """Salva a selecao na biblioteca de assets do Blender"""
    bl_idname = "object.cabinet_salvar_biblioteca"
    bl_label = "Salvar na Biblioteca"
    bl_options = {'REGISTER'}

    nome: bpy.props.StringProperty(name="Nome do preset", default="Preset")
    n1: bpy.props.EnumProperty(name="Categoria",
                               items=lambda s, c: [(k, k, "") for k in ARVORE.keys()])
    n2: bpy.props.StringProperty(name="Subcategoria", default="")
    n3: bpy.props.StringProperty(name="Tipo", default="")
    como_modulo: bpy.props.BoolProperty(
        name="Como modulo (varias pecas)", default=True,
        description="Ligado: salva como Collection (arrasta o conjunto inteiro). "
                    "Desligado: salva cada chapa como objeto separado")

    def invoke(self, context, event):
        sel = [o for o in context.selected_objects]
        if len(sel) == 1 and sel[0].type == 'MESH':
            self.como_modulo = False
            self.nome = sel[0].name
        elif sel:
            self.nome = "Modulo"
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        sel = [o for o in context.selected_objects]
        if not sel:
            self.report({'WARNING'}, "Nada selecionado")
            return {'CANCELLED'}
        # inclui filhos dos Empties de conjunto selecionados
        completos = list(sel)
        for o in sel:
            if MARCA_CONJUNTO in o:
                completos += [f for f in bpy.data.objects if f.parent == o]
        completos = list(dict.fromkeys(completos))
        # os niveis sao resolvidos ANTES de gravar: e' deles que sai o
        # catalogo em que o asset vai ser arquivado
        n2 = self.n2 or (_filhos_n2(self.n1) or [""])[0]
        n3 = self.n3 or (_filhos_n3(self.n1, n2) or [""])[0]
        try:
            arq = salvar_na_biblioteca(completos, self.nome, self.como_modulo,
                                       niveis=(self.n1, n2, n3))
            png = os.path.splitext(os.path.basename(arq))[0] + ".png"
            # Todo preset precisa nascer com representacao visual. Nao e'
            # uma preferencia do usuario nem pode ser desativada no dialogo.
            cam = next((o for o in sel if o.type == 'CAMERA'), None)
            alvo = [o for o in completos if o.type != 'CAMERA']
            okf, msg = capturar_viewport(
                os.path.join(pasta_biblioteca(), png), cam,
                isolar=alvo or None)
            if not okf:
                self.report({'ERROR'}, "Foto obrigatoria falhou: " + msg)
                return {'CANCELLED'}
            # a mesma foto vira a preview do asset dentro do .blend
            okp, msgp = aplicar_preview_png(
                arq, os.path.join(pasta_biblioteca(), png))
            if not okp:
                print("[Cabinet Creator] preview do asset:", msgp)
            registrar_no_indice(pasta_biblioteca(), self.nome, arq,
                                self.n1, n2, n3,
                                "modulo" if self.como_modulo else "objeto")
        except Exception as e:
            self.report({'ERROR'}, "Falha ao salvar: %s" % e)
            return {'CANCELLED'}
        self.report({'INFO'}, "Salvo em %s" % arq)
        return {'FINISHED'}


# Fracao da altura da viewport que sobra para a viewport ao abrir a
# biblioteca embaixo dela.
FRACAO_ASSET_BROWSER = 0.35


def _apontar_asset_browser():
    """Aponta o Asset Browser recem-aberto para a biblioteca do addon.

    Roda adiado porque `params` do SpaceFileBrowser so' passa a existir
    depois que a area e' desenhada pela primeira vez. As areas sao
    relidas do window_manager a cada chamada -- guardar a referencia
    arriscaria usar um ponteiro morto se a area fosse fechada antes.
    """
    try:
        for janela in bpy.context.window_manager.windows:
            for area in janela.screen.areas:
                if area.type != 'FILE_BROWSER':
                    continue
                params = getattr(area.spaces.active, "params", None)
                if params is None:
                    continue
                # so' mexe em quem ainda esta' no padrao ("All
                # Libraries"): um browser que o usuario ja' apontou para
                # outra biblioteca nao pode ser sequestrado
                atual = getattr(params, "asset_library_reference", "")
                if atual in ("", "ALL"):
                    try:
                        params.asset_library_reference = NOME_BIBLIOTECA
                    except Exception as e:
                        print("[Cabinet Creator] biblioteca:", e)
                area.tag_redraw()
    except Exception as e:
        print("[Cabinet Creator] asset browser:", e)
    return None


def _area_asset_browser(tela):
    for area in tela.areas:
        if area.type == 'FILE_BROWSER' and area.ui_type == 'ASSETS':
            return area
    return None


class OBJECT_OT_abrir_asset_browser(Operator):
    """Abre a biblioteca do Blender embaixo da viewport; clique de novo
    para fechar"""
    bl_idname = "object.cabinet_asset_browser"
    bl_label = "Abrir no Asset Browser"

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        registrar_bibliotecas()
        tela = context.window.screen

        # ja' aberto: o mesmo botao fecha
        aberto = _area_asset_browser(tela)
        if aberto is not None:
            alvo = next((r for r in aberto.regions if r.type == 'WINDOW'),
                        None)
            try:
                with context.temp_override(area=aberto, region=alvo):
                    bpy.ops.screen.area_close()
                return {'FINISHED'}
            except Exception as e:
                print("[Cabinet Creator] fechar browser:", e)
                self.report({'WARNING'}, "Feche a area a mao")
                return {'CANCELLED'}

        # Uma JANELA nova nao serve: `Window.width/height` sao somente
        # leitura e nenhum operador aceita tamanho, entao ela nasceria
        # quase do tamanho da tela e esconderia o trabalho. Dividir a
        # viewport da uma area pequena, com o modelo sempre a' vista.
        area = context.area
        janela = next((r for r in area.regions if r.type == 'WINDOW'), None)
        antes = {a.as_pointer() for a in tela.areas}
        try:
            with context.temp_override(area=area, region=janela):
                bpy.ops.screen.area_split(direction='HORIZONTAL',
                                          factor=FRACAO_ASSET_BROWSER)
        except Exception as e:
            print("[Cabinet Creator] dividir area:", e)
            self.report({'WARNING'}, "Nao consegui abrir a biblioteca")
            return {'CANCELLED'}

        nova = next((a for a in tela.areas if a.as_pointer() not in antes),
                    None)
        if nova is None:
            self.report({'WARNING'}, "Nao consegui abrir a biblioteca")
            return {'CANCELLED'}
        try:
            nova.type = 'FILE_BROWSER'
            nova.ui_type = 'ASSETS'
        except Exception as e:
            print("[Cabinet Creator] asset browser:", e)
            self.report({'WARNING'}, "Troque o editor para Asset Browser")
            return {'CANCELLED'}
        # params so' nasce depois do primeiro desenho da area
        bpy.app.timers.register(_apontar_asset_browser, first_interval=0.2)
        return {'FINISHED'}


class OBJECT_OT_abrir_pasta_biblioteca(Operator):
    """Mostra o caminho da biblioteca no Explorer"""
    bl_idname = "object.cabinet_abrir_biblioteca"
    bl_label = "Abrir Pasta da Biblioteca"

    def execute(self, context):
        destino = pasta_biblioteca()
        bpy.ops.wm.path_open(filepath=destino)
        self.report({'INFO'}, destino)
        return {'FINISHED'}


# =========================== REDE DE SEGURANCA: verificacao por timer
# O handler de depsgraph depende de uma atualizacao chegar DEPOIS que o
# operador modal sai de cena. Se a ultima atualizacao acontecer ainda
# com o modal registrado e nenhuma outra vier em seguida, o recalculo
# nunca dispararia. Este timer fecha essa brecha: a cada 0.2s verifica
# se existe alguma chapa com escala != 1 e nenhum modal ativo.
INTERVALO_TIMER = 0.2


def _ha_modal_ativo():
    try:
        for win in bpy.context.window_manager.windows:
            if len(win.modal_operators) > 0:
                return True
    except Exception:
        pass
    return False


def _transformando():
    """Mover, girar ou escalar (G/R/S, gizmo nativo) em andamento.

    A HUD le a geometria e o alvo do hover de ANTES do gesto: desenhada
    durante ele, a seta e as linhas ficavam voando no lugar de origem.
    """
    try:
        for janela in bpy.context.window_manager.windows:
            for op in janela.modal_operators:
                if op.bl_idname.upper().startswith('TRANSFORM'):
                    return True
    except Exception:
        pass
    return False


def verificar_periodicamente():
    sincronizar_contornos()
    if not _ocupado[0] and not _ha_modal_ativo():
        try:
            absorver_conjuntos()
            normalizar_chapas()
            absorver_edicoes_de_malha()
            _conferir_rebaixos()
            _sincronizar_medidas_ativas()
        except Exception as e:
            print("[Cabinet Creator] erro no timer:", e)
    return INTERVALO_TIMER


# ------------------------------------------- contorno nativo da selecao
# Um clique seleciona o modulo inteiro, e o Blender pinta de laranja o
# contorno de cada chapa. Nao existe contorno por objeto na API: o
# `show_outline_selected` vale para a viewport inteira. Entao ele e'
# desligado enquanto houver modulo/porta selecionado e DEVOLVIDO depois.
#
# Nunca se liga ou desliga as cegas: so' se desliga o que estava ligado,
# e so' se religa o que foi este add-on quem desligou. Quem ja' trabalha
# com o contorno desligado nao ve diferenca nenhuma, e quem o religa na
# mao durante a edicao manda naquela viewport ate' trocar de selecao.
_contornos_desligados = set()   # as_pointer() das viewports desligadas
_contornos_do_usuario = {}      # as_pointer() -> grupos da edicao


def _novo_contorno(ptr, ligado, grupos):
    """Valor novo do contorno de UMA viewport (None = nao mexer).

    `grupos`: nomes dos modulos/portas selecionados (vazio = nenhum).
    """
    if not grupos:
        _contornos_do_usuario.pop(ptr, None)
        if ptr in _contornos_desligados:
            _contornos_desligados.discard(ptr)
            if not ligado:
                return True
        return None
    if _contornos_do_usuario.get(ptr) == grupos:
        return None
    _contornos_do_usuario.pop(ptr, None)
    if ptr in _contornos_desligados:
        if ligado:
            # religado na mao no meio da edicao: o usuario quer ver
            _contornos_desligados.discard(ptr)
            _contornos_do_usuario[ptr] = grupos
        return None
    if ligado:
        _contornos_desligados.add(ptr)
        return False
    # ja' estava desligado antes: nao e' nosso, nao se devolve nada
    _contornos_do_usuario[ptr] = grupos
    return None


def _grupos_selecionados(view_layer):
    # Nao percorre `view_layer.objects.selected`: logo apos um Ctrl+Z essa
    # colecao ainda pode trazer bases da memoria velha, e o Blender caia
    # criando o objeto Python (crash do usuario, 2x). `select_get` acha a
    # base de cada objeto nosso na hora.
    try:
        return frozenset(o.name for o in bpy.data.objects
                         if (MARCA_CONJUNTO in o or MARCA_PORTAS in o
                             or MARCA_FOLHA in o)
                         and o.select_get(view_layer=view_layer))
    except Exception:
        return frozenset()


def _viewports_da_janela(janela):
    """Viewports da janela, menos a gaveta (que nao tem overlay)."""
    screen = janela.screen
    gaveta = _area_gaveta(screen)
    for area in screen.areas:
        if area.type == 'VIEW_3D' and area != gaveta:
            yield area.spaces.active


def sincronizar_contornos(devolver=False):
    """Aplica `_novo_contorno` a cada viewport aberta.

    `devolver=True` religa tudo que o add-on desligou, sem esquecer
    quem o usuario religou: e' o caminho de salvar, abrir e desligar.
    """
    try:
        janelas = bpy.context.window_manager.windows
    except Exception:
        return
    for janela in janelas:
        try:
            grupos = frozenset()
            if not devolver and _opcao('ocultar_contorno_grupo'):
                grupos = _grupos_selecionados(janela.view_layer)
            for espaco in _viewports_da_janela(janela):
                overlay = espaco.overlay
                ptr = espaco.as_pointer()
                if devolver:
                    if ptr in _contornos_desligados:
                        _contornos_desligados.discard(ptr)
                        overlay.show_outline_selected = True
                    continue
                novo = _novo_contorno(ptr, overlay.show_outline_selected,
                                      grupos)
                if novo is not None:
                    overlay.show_outline_selected = novo
        except Exception as e:
            print("[Cabinet Creator] contorno:", e)


@bpy.app.handlers.persistent
def _devolver_contornos(*_args):
    """Antes de salvar ou abrir: o .blend guarda o estado do usuario,
    nunca o desligamento temporario."""
    sincronizar_contornos(devolver=True)


@bpy.app.handlers.persistent
def _retomar_contornos(*_args):
    sincronizar_contornos()


@bpy.app.handlers.persistent
def _esquecer_contornos(*_args):
    # arquivo novo: os ponteiros antigos podem ser reaproveitados
    _contornos_desligados.clear()
    _contornos_do_usuario.clear()
    sincronizar_contornos()


@bpy.app.handlers.persistent
def _esquecer_referencias(*_args):
    """Antes de desfazer/refazer/abrir: o hover da HUD guarda OBJETOS, que
    essas acoes liberam (ver `_alvo_vivo`). O proximo movimento do mouse
    acha o alvo de novo."""
    _hover_hud.clear()


# Ctrl+Z / Ctrl+Shift+Z: os dados acabaram de ser recarregados e o
# primeiro recalculo da cena chama o handler do depsgraph -- ler a selecao
# ali derrubava o Blender (crash do usuario, 2x, depois de criar porta).
# Entre o undo e o proximo tique o handler nao faz nada; o timer devolve
# o contorno. Fora do undo nada muda: o contorno segue na hora.
_desfazendo = [False]


@bpy.app.handlers.persistent
def _antes_de_desfazer(*_args):
    _desfazendo[0] = True
    _esquecer_referencias()


@bpy.app.handlers.persistent
def _depois_de_desfazer(*_args):
    _desfazendo[0] = True
    if not bpy.app.timers.is_registered(_fim_do_desfazer):
        bpy.app.timers.register(_fim_do_desfazer, first_interval=0.0)


def _fim_do_desfazer():
    _desfazendo[0] = False
    sincronizar_contornos()
    return None


HANDLERS_REFERENCIAS = (('undo_pre', _antes_de_desfazer),
                        ('redo_pre', _antes_de_desfazer),
                        ('undo_post', _depois_de_desfazer),
                        ('redo_post', _depois_de_desfazer),
                        ('load_pre', _esquecer_referencias))

HANDLERS_CONTORNO = (('save_pre', _devolver_contornos),
                     ('save_post', _retomar_contornos),
                     ('load_pre', _devolver_contornos),
                     ('load_post', _esquecer_contornos))


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


# ====================================================== SELECAO
# 1 clique seleciona o MODULO inteiro (o realce nativo do Blender acende
# em todas as pecas); 2 cliques isolam a chapa sob o cursor.
#
# As entradas ficam no keyconfig do ADDON, avaliado antes do padrao.
# Quando o poll falha -- fora do Object Mode, ou com a opcao desligada
# nas Preferencias -- o evento cai para o `view3d.select` nativo e o
# comportamento normal do Blender volta inteiro.


def _aba_da_selecao(obj):
    """Aba da gaveta que cuida de `obj`, ou None (objeto que nao e' nosso)."""
    if obj is None:
        return None
    if MARCA_PUXADOR in obj:
        return 'PUXADORES'
    if MARCA_PORTAS in obj or MARCA_FOLHA in obj:
        return 'PORTAS'
    if MARCA_CONJUNTO in obj or MARCA_CHAPA in obj:
        return 'MODULOS'
    return None


def _seguir_selecao_na_gaveta(context):
    """A gaveta vai para a aba do que o CLIQUE na viewport selecionou
    (pedido do usuario): porta -> Portas, modulo -> Modulos, puxador ->
    Puxadores. So' no clique: o add-on tambem troca o ativo sozinho (criar
    porta deixa o modulo ativo) e ai' a aba nao pode pular."""
    camada = getattr(context, 'view_layer', None)
    ativo = camada.objects.active if camada is not None else None
    if ativo is None or not ativo.select_get():
        return
    aba = _aba_da_selecao(ativo)
    if aba is None or context.scene.cabinet_aba == aba:
        return
    context.scene.cabinet_aba = aba
    tela = getattr(context, 'screen', None)
    if tela is not None:
        # como o clique na aba: comeca do topo e fecha as opcoes
        tela[_CHAVE_ROLAGEM] = 0
        _fechar_opcoes(tela)
    _redesenhar_viewports(context)


def familia_de(obj):
    """Tudo que deve acender junto com obj: as chapas do grupo mais o
    Empty do conjunto.

    Selecionar o pai JUNTO com os filhos e' seguro: o Blender nao
    transforma duas vezes o filho cujo pai tambem esta' selecionado.
    """
    if obj is None:
        return []
    portas = _grupo_portas(obj)
    if portas is not None:
        return [portas] + _folhas_portas(portas)
    if MARCA_CONJUNTO in obj:
        return [obj] + _chapas_do_conjunto(obj)
    if MARCA_CHAPA not in obj:
        return []
    chapas = grupo_de(obj, simetrico=True)
    pai = obj.parent
    if pai is not None and MARCA_CONJUNTO in pai:
        return [pai] + chapas
    return chapas


class OBJECT_OT_selecionar(Operator):
    """Clique seleciona o modulo inteiro; clique duplo isola a chapa"""
    bl_idname = "object.cabinet_selecionar"
    bl_label = "Selecionar Modulo"
    bl_options = {'UNDO'}

    modo: EnumProperty(
        name="Modo", default='GRUPO',
        items=[('GRUPO', "Grupo", "Seleciona o modulo inteiro"),
               ('INDIVIDUAL', "Individual", "Seleciona so' a chapa clicada")])
    # espelham as props do view3d.select: sao repassadas tal e qual.
    # SKIP_SAVE em TODAS: a entrada do keymap so' preenche as que cita,
    # e o resto vinha do ULTIMO uso. Depois de um Shift+clique o clique
    # simples herdava toggle=True e somava em vez de trocar a selecao.
    location: IntVectorProperty(size=2, options={'SKIP_SAVE'})
    extend: BoolProperty(default=False, options={'SKIP_SAVE'})
    deselect: BoolProperty(default=False, options={'SKIP_SAVE'})
    toggle: BoolProperty(default=False, options={'SKIP_SAVE'})
    deselect_all: BoolProperty(default=False, options={'SKIP_SAVE'})
    select_passthrough: BoolProperty(default=False, options={'SKIP_SAVE'})
    # Entrada do CLICK (soltou sem arrastar): termina o que o PRESS
    # deixou passar, como o par PRESS/CLICK do keymap nativo
    clique: BoolProperty(default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        p = _prefs()
        if p is not None and not p.selecao_por_grupo:
            return False
        return (context.mode == 'OBJECT' and context.area is not None
                and context.area.type == 'VIEW_3D'
                and not _eh_area_gaveta(context))

    def invoke(self, context, event):
        resultado = self._invoke(context, event)
        _seguir_selecao_na_gaveta(context)
        _log_clique('selecionar %s/%s modo=%s clique=%s pass=%s -> %s | ativo=%s n=%d nivel_gravado=%s' % (
            getattr(event, 'type', '?'), getattr(event, 'value', '?'),
            self.modo, self.clique,
            self.select_passthrough, sorted(resultado),
            context.object.name if context.object else None,
            len(context.selected_objects),
            _clique_chapa_hud.get(context.region.as_pointer())))
        return resultado

    def _invoke(self, context, event):
        self.location = (event.mouse_region_x, event.mouse_region_y)
        chave = context.region.as_pointer()
        pendente = _clique_pendente.pop(chave, None)
        if self.clique:
            return self._soltou(context, pendente)
        if _slider_sob_mouse(context, self.location) is not None:
            # a bolinha do slider: no keyconfig do usuario esta entrada vem
            # antes da do slider, e selecionar aqui esconderia o slider
            return {'PASS_THROUGH'}
        ferragem = _ferragem_sob_mouse(context, self.location)
        if ferragem is not None:
            if self.modo == 'INDIVIDUAL':
                # duplo = a PECA, selecao nativa: Tab, G/R/S, modificadores
                _selecionar_peca(context, ferragem,
                                 somar=self.toggle or self.extend)
            else:
                # dobradica/pistao: todas as do modulo, no modo delas
                _selecionar_ferragem(context, ferragem,
                                     somar=self.toggle or self.extend)
            return {'FINISHED'}
        # qualquer outro clique sai do modo de edicao das ferragens
        _ferragens_selecionadas[0] = None
        atingido = _raio_hud(context, self.location)
        _log_clique('  raio=%s anterior=%s' % (
            atingido and atingido[0].name, _clique_chapa_hud.get(chave)))
        if atingido is not None and MARCA_CHAPA in atingido[0]:
            obj = atingido[0]
            anterior = _clique_chapa_hud.get(chave) or ('', 'MODULO')
            mesmo = anterior[0] == obj.name
            if MARCA_FOLHA in obj and _grupo_portas(obj) is not None:
                # Porta (backlog do usuario, Epico 3): clique = a PORTA
                # inteira (nunca o modulo); duplo = UMA folha ("aba").
                # Shift soma. Ferragens nao entram (selecao propria).
                somar = self.toggle or self.extend
                if (self.modo != 'INDIVIDUAL' and self.select_passthrough
                        and not somar and obj.select_get()):
                    familia = {_grupo_portas(obj), *_folhas_portas(
                        _grupo_portas(obj))}
                    if any(o not in familia for o in context.selected_objects):
                        # varios selecionados: o arraste leva todos; se
                        # soltar sem arrastar, o CLICK deixa so' a porta
                        _clique_pendente[chave] = obj.name
                        return {'PASS_THROUGH', 'CANCELLED'}
                _selecionar_porta_hud(
                    context, obj,
                    'FOLHA' if self.modo == 'INDIVIDUAL' else 'PORTA',
                    somar=somar)
                return {'FINISHED'}
            if self.modo != 'INDIVIDUAL':
                _clique_chapa_hud[chave] = (obj.name,
                                            _nivel_da_selecao(context, obj))
            somar = self.toggle or self.extend
            if somar and MARCA_FOLHA not in obj:
                _somar_peca(context, obj, duplo=self.modo == 'INDIVIDUAL')
                return {'FINISHED'}
            if (self.select_passthrough and not somar
                    and self.modo != 'INDIVIDUAL' and obj.select_get()):
                familia = set(_familia_do_clique(obj)) | {obj}
                if any(o not in familia for o in context.selected_objects):
                    # Clicou num item JA' selecionado junto com outros:
                    # no PRESS nada muda, senao o arraste so' levaria
                    # este. Se soltar sem arrastar, o CLICK deixa so' ele.
                    _clique_pendente[chave] = obj.name
                    # Como o view3d.select nativo: CANCELLED + PASS_THROUGH.
                    # Com FINISHED o Blender da' o PRESS por consumido e
                    # nao gera o CLICK (alem de gravar um undo vazio).
                    return {'PASS_THROUGH', 'CANCELLED'}
            _selecionar_chapa_hud(context, obj,
                                  self.modo == 'INDIVIDUAL' and mesmo,
                                  somar=somar)
            return {'FINISHED'}
        return self.execute(context)

    def _soltou(self, context, pendente):
        """CLICK depois de um PRESS de CHAPA que deixou passar: so' o
        modulo dela. Todo o resto e' do CLICK nativo -- para objeto comum
        o Blender ja' deixa so' o clicado, e recriar isso aqui e' o que
        NAO se quer."""
        atingido = _raio_hud(context, self.location)
        if (pendente is None or atingido is None
                or atingido[0].name != pendente):
            return {'PASS_THROUGH'}
        if MARCA_FOLHA in atingido[0] and _grupo_portas(atingido[0]) is not None:
            _selecionar_porta_hud(context, atingido[0], 'PORTA')
            return {'FINISHED'}
        _selecionar_chapa_hud(context, atingido[0])
        return {'FINISHED'}

    def execute(self, context):
        # a escolha de QUEM foi clicado continua sendo do Blender; este
        # operador so' amplia (ou estreita) o resultado depois
        try:
            r = bpy.ops.view3d.select(
                'EXEC_DEFAULT',
                location=tuple(self.location),
                extend=self.extend, deselect=self.deselect,
                toggle=self.toggle, deselect_all=self.deselect_all,
                select_passthrough=self.select_passthrough)
        except Exception as e:
            print("[Cabinet Creator] selecao:", e)
            return {'CANCELLED'}
        if 'PASS_THROUGH' in r or 'CANCELLED' in r:
            return r

        obj = context.object
        familia = familia_de(obj)
        if not familia:
            return r

        # se o clique DESLIGOU a peca (shift), o grupo inteiro apaga junto
        ligado = obj.select_get()
        for o in familia:
            try:
                o.select_set(False if self.modo == 'INDIVIDUAL' else ligado)
            except Exception:
                pass
        if self.modo == 'INDIVIDUAL':
            obj.select_set(True)
        context.view_layer.objects.active = obj
        return r


_keymaps = []

# DIAGNOSTICO TEMPORARIO do clique duplo (remover depois): grava cada
# clique na viewport e, ao registrar, como os atalhos ficaram no keymap.
ARQUIVO_LOG_CLIQUES = os.path.join(
    os.environ.get('TEMP') or os.environ.get('TMP') or os.path.expanduser('~'),
    'cabinet_cliques.log')


def _log_clique(texto):
    try:
        with open(ARQUIVO_LOG_CLIQUES, 'a', encoding='utf-8') as f:
            f.write('%.3f %s\n' % (time.time(), texto))
    except Exception:
        pass


def _log_keymaps():
    try:
        wm = bpy.context.window_manager
        _log_clique('--- registro; dbl_click_time=%s ms' % (
            bpy.context.preferences.inputs.mouse_double_click_time))
        for nome in ('addon', 'user', 'active'):
            kc = getattr(wm.keyconfigs, nome, None)
            km = kc.keymaps.get('3D View') if kc else None
            if km is None:
                _log_clique('%s: sem 3D View' % nome)
                continue
            for kmi in km.keymap_items:
                if kmi.idname.startswith('object.cabinet') or (
                        kmi.type == 'LEFTMOUSE' and kmi.idname.startswith('view3d.select')):
                    _log_clique('%s: %s %s %s shift=%s ctrl=%s ativo=%s modo=%s' % (
                        nome, kmi.idname, kmi.type, kmi.value, kmi.shift,
                        kmi.ctrl, kmi.active,
                        getattr(kmi.properties, 'modo', '-')))
    except Exception as e:
        _log_clique('keymaps: erro %s' % e)
    return None

# (valor do evento, shift, modo, props repassadas ao view3d.select)
# O PRESS simples leva select_passthrough para preservar o arraste: o
# clique sobre uma peca JA' selecionada nao desmonta a selecao, senao
# nao daria para arrastar o modulo inteiro depois de seleciona-lo.
# O CLICK so' age quando o PRESS de uma CHAPA deixou passar: o CLICK
# nativo deixaria so' a chapa, nao o modulo. Para o resto ele devolve
# PASS_THROUGH e quem desseleciona os outros e' o proprio Blender.
_ENTRADAS_KEYMAP = (
    ('PRESS', False, 'GRUPO',
     {"deselect_all": True, "select_passthrough": True}),
    ('CLICK', False, 'GRUPO', {"deselect_all": True, "clique": True}),
    ('PRESS', True, 'GRUPO', {"toggle": True}),
    ('DOUBLE_CLICK', False, 'INDIVIDUAL', {"deselect_all": True}),
    # Shift+duplo: isola a chapa DENTRO da selecao (ver `_somar_peca`)
    ('DOUBLE_CLICK', True, 'INDIVIDUAL', {"toggle": True}),
)


def registrar_keymaps():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:          # Blender em background nao monta keyconfig
        return
    km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
    # Esta entrada so' aceita eventos na area exclusiva da gaveta.
    kmi = km.keymap_items.new("object.cabinet_interagir_gaveta",
                              'LEFTMOUSE', 'PRESS', head=True)
    _keymaps.append((km, kmi))
    for evento in ('WHEELUPMOUSE', 'WHEELDOWNMOUSE'):
        kmi = km.keymap_items.new("object.cabinet_interagir_gaveta",
                                  evento, 'PRESS', head=True)
        _keymaps.append((km, kmi))
    for valor, shift, modo, props in _ENTRADAS_KEYMAP:
        kmi = km.keymap_items.new("object.cabinet_selecionar",
                                  'LEFTMOUSE', valor, shift=shift)
        kmi.properties.modo = modo
        for chave, v in props.items():
            setattr(kmi.properties, chave, v)
        _keymaps.append((km, kmi))

    # Correntes: a tecla escolhida nas opcoes, segurada, mostra a
    # corrente (o operador devolve o evento: Alt/Ctrl/Shift seguem
    # valendo para tudo o mais).
    for tecla in TECLAS_CORRENTE:
        for valor in ('PRESS', 'RELEASE'):
            kmi = km.keymap_items.new("object.cabinet_tecla_corrente",
                                      tecla, valor, any=True)
            kmi.properties.tecla = tecla
            kmi.properties.apertou = valor == 'PRESS'
            _keymaps.append((km, kmi))
    kmi = km.keymap_items.new("object.cabinet_clique_corrente",
                              'LEFTMOUSE', 'PRESS', any=True, head=True)
    _keymaps.append((km, kmi))
    # Slider de abertura das folhas: clique SEM modificador, antes da
    # selecao; fora de um slider o operador devolve o evento.
    kmi = km.keymap_items.new("object.cabinet_abrir_porta",
                              'LEFTMOUSE', 'PRESS', head=True)
    _keymaps.append((km, kmi))

    # Posicionador a partir da grade. O keymap "User Interface" e' o
    # unico que enxerga botoes de painel. O gesto de ARRASTAR raramente
    # chega aqui (o handler de UI consome o PRESS antes), mas o
    # CLIQUE-para-posicionar do operador funciona de qualquer forma.
    km_ui = kc.keymaps.new(name="User Interface", space_type='EMPTY')
    kmi = km_ui.keymap_items.new("object.cabinet_arrastar_preset",
                                 'LEFTMOUSE', 'PRESS', head=True)
    _keymaps.append((km_ui, kmi))


def remover_keymaps():
    for km, kmi in _keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _keymaps.clear()


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
    ('ui_porta_folga', 'porta_folga_mm', 'Folga no perimetro', 0.0),
    ('ui_porta_entre_folhas', 'porta_entre_folhas_mm', 'Entre folhas', 0.0),
    ('ui_porta_afastamento', 'porta_afastamento_mm', 'Afastamento', 0.0),
    ('ui_porta_recuo_embutida', 'porta_recuo_embutida_mm',
     'Recuo da embutida', 0.0),
    ('ui_porta_recuo_correr', 'porta_recuo_correr_mm',
     'Recuo para trilhos', 0.1),
    ('ui_porta_sobreposicao', 'porta_sobreposicao_mm', 'Sobreposicao', 0.0),
    ('ui_porta_entre_planos', 'porta_entre_planos_mm',
     'Entre planos', 0.1),
)


# Campo da gaveta -> parametro do grupo, para editar uma porta colocada.
_PARAMETRO_DA_MEDIDA_PORTA = dict(
    [(m[0], m[1][len('porta_'):]) for m in MEDIDAS_PORTAS]
    + [('ui_porta_espessura', 'espessura_mm')])


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
        'folga_mm': s.porta_folga_mm,
        'entre_folhas_mm': s.porta_entre_folhas_mm,
        'afastamento_mm': s.porta_afastamento_mm,
        'recuo_embutida_mm': s.porta_recuo_embutida_mm,
        'recuo_correr_mm': s.porta_recuo_correr_mm,
        'sobreposicao_mm': s.porta_sobreposicao_mm,
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
        elif nome in {'abertura', 'dobradica'}:
            setattr(s, 'porta_' + nome, valor)
        elif nome in _PARAMETROS_PORTAS and hasattr(s, 'porta_' + nome):
            # as ferragens do wizard (lado, quantidades) moram so' na porta
            setattr(s, 'porta_' + nome, float(valor))


_PARAMETROS_PORTAS = (
    'abertura', 'folhas', 'dobradica', 'espessura_mm', 'lateral_mm',
    'folga_mm', 'entre_folhas_mm', 'afastamento_mm', 'recuo_embutida_mm',
    'recuo_correr_mm', 'sobreposicao_mm', 'entre_planos_mm',
    'dobradica_lado', 'dobradicas_qtd', 'dobradicas_margem_mm',
    'pistoes_qtd', 'pistoes_offset_mm',
)


def _grupo_portas(obj):
    if obj is not None and MARCA_PORTAS in obj:
        return obj
    if (obj is not None and MARCA_FOLHA in obj and obj.parent is not None
            and MARCA_PORTAS in obj.parent):
        return obj.parent
    return None


def _folhas_portas(grupo):
    return sorted((o for o in grupo.children if MARCA_FOLHA in o),
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
            return _espessura_livre(caixa[3])
    for obj in objetos:
        if obj is not None and MARCA_CHAPA in obj and MARCA_FOLHA not in obj:
            return _espessura_livre(obj.chapa_espessura_mm)
    return float(padrao)


def _espessura_da_porta_nova(modulo, objetos=(), padrao=ESPESSURA_PADRAO_PORTA):
    """A porta nasce com a espessura do modulo; depois se edita no E da folha.

    Apoiada em outra porta, herda a dela: duas fileiras no mesmo
    modulo saem com a mesma espessura.
    """
    for obj in objetos:
        if obj is not None and MARCA_FOLHA in obj:
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
    limites = _limites_mundo(bpy.context, {obj_a, obj_b})
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
# embutida e correr = a borda ele para DENTRO do vao. A "Folga no
# perimetro" soma por cima. Cobertura fora do padrao (o usuario marcou o
# canto e confirmou) vale como marcada.
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
    return [p['folga_mm'] - (_cobertura_mm(float(p[k]), lateral) if k in p
                             else cobertura)
            for k in COBERTURAS_LADOS]


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
    tolerancia = TOL_BORDA * 1000.0
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
        if obj is None or obj.type != 'MESH' or MARCA_CHAPA not in obj:
            continue
        zs = [v.co.z for v in obj.data.vertices]
        if not zs:
            continue
        meio, metade = (max(zs) + min(zs)) / 2.0, (max(zs) - min(zs)) / 2.0
        local = obj.matrix_world.inverted() @ originais[i]
        if metade <= 2 * TOL_BORDA or abs(local.z - meio) > TOL_BORDA:
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
                         modulo=None, objetos=(None, None), portas=None):
    """Converte cantos externos e encontros com portas em vao interno.

    `portas`: os cantos da PORTA (cliques 1 e 4 do wizard; a e b sao os
    do vao). Devolve (vao, pontos em mundo, apoios, coberturas por lado).

    O calculador recebe sempre o vao livre. Normalizar ANTES dele evita
    somar a cobertura duas vezes e serve tanto ao gesto quanto ao execute.
    """
    largura_em = _largura_do_vao(referencia, a, b)
    base = _base_da_frente(referencia, frente, largura_em)
    pontos = [base @ Vector(p) * 1000.0 for p in (a, b)]
    bordas, espelhados = None, [False, False]
    if portas is not None:
        bordas = [base @ Vector(p) * 1000.0 for p in portas]
        pontos, espelhados = _espelhar_margem(bordas, pontos)
    originais = [p.copy() for p in pontos]
    tolerancia = TOL_BORDA * 1000.0
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
        if grupo is None or MARCA_FOLHA not in obj:
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
        for indice in ancoras:
            # encostado em outra porta: quem manda e' o apoio
            coberturas.pop(COBERTURAS_LADOS[indice], None)
    elif _cobertura_porta(parametros) > 0:
        coberturas = {COBERTURAS_LADOS[i]: 0.5 for i in range(4)
                      if meias >> i & 1}
    else:
        coberturas = {}
    return vao, mundo, ancoras, coberturas


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
        sobreposicao = p['sobreposicao_mm'] if n > 1 else 0.0
        l = (util + (n - 1) * sobreposicao) / n
        passo = l - sobreposicao
        if passo <= 0 or (n > 2 and 2 * passo < l - 1e-6):
            raise ValueError("Sobreposicao excessiva: folhas no mesmo plano colidem")
    else:
        l = (util - (n - 1) * p['entre_folhas_mm']) / n
        passo = l + p['entre_folhas_mm']
    if l < 1.0 or a < 1.0:
        raise ValueError("Folgas maiores que o vao disponivel")
    saida = []
    for i in range(n):
        if correr:
            # Dois planos alternados. O recuo mede a FACE mais externa,
            # assim nem meia espessura invade o espaco reservado ao trilho.
            z = (-p['recuo_correr_mm'] - e / 2.0
                 - (i % 2) * (e + p['entre_planos_mm']))
        elif p['dobradica'] == 'SUPER_CURVA':
            z = -p['recuo_embutida_mm'] - e / 2.0
        else:
            z = _afastamento_porta(p) + e / 2.0
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
    if obj is None or MARCA_CHAPA not in obj:
        return None
    pai = obj.parent
    while pai is not None:
        if MARCA_CONJUNTO in pai:
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
              for o in _chapas_do_conjunto(conj) for v in o.data.vertices]
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
            if MARCA_PORTAS in o and o.get(CHAVE_MODULO_PORTA) == conj.name]


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
        fechada = _matriz_fechada(folha)
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
    if conj is None or MARCA_CONJUNTO not in conj:
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
    if (modulo is not None and MARCA_CONJUNTO in modulo
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
    if not guardados or nome not in _PARAMETROS_PORTAS:
        return 'Porta sem parametros para editar'
    parametros = dict(guardados)
    if nome == 'espessura_mm':
        valor = _espessura_livre(valor)
    parametros[nome] = valor
    if nome == 'abertura':
        parametros['folhas'] = min(int(parametros.get('folhas', 1)),
                                   LIMITES_FOLHAS[valor])
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
    ocupado_antes = _ocupado[0]
    _ocupado[0] = True
    try:
        if grupo is None:
            grupo = bpy.data.objects.new(_nome_da_porta(parametros), None)
            grupo['porta_nome_auto'] = grupo.name
            # dentro do grupo (Collection) do armario, junto das chapas
            colecao = (pai.users_collection[0] if pai is not None
                       and pai.users_collection else context.collection)
            colecao.objects.link(grupo)
            grupo[MARCA_PORTAS] = 1
            _ocultar_empty(grupo)
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
                malha = bpy.data.meshes.new("Porta")
                folha = bpy.data.objects.new("Folha_%02d" % (i + 1), malha)
                grupo.users_collection[0].objects.link(folha)
                folha[MARCA_CHAPA] = 1
                folha[MARCA_FOLHA] = 1
            folha['porta_indice'] = i
            folha.parent = grupo
            folha.matrix_parent_inverse = Matrix.Identity(4)
            # a abertura sobrevive a redimensionar (Fase 3)
            folha[CHAVE_CENTRO_FOLHA] = tuple(centro)
            folha.matrix_basis = _matriz_abertura(
                parametros, largura, len(calculadas), i, (l, a, e, centro),
                folha.get(CHAVE_ABERTURA, 0.0))
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
            for pux in [c for c in folha.children if MARCA_PUXADOR in c]:
                mundo = pux.matrix_world.copy()
                pux.parent = None
                pux.matrix_world = mundo
                orfaos.append(pux)
            for ferragem in [c for c in folha.children_recursive
                             if CHAVE_FERRAGEM in c]:
                _remover_ferragem(ferragem)
            malha = folha.data
            bpy.data.objects.remove(folha, do_unlink=True)
            if malha.users == 0:
                bpy.data.meshes.remove(malha)
        _montar_ferragens(grupo, parametros, largura, altura, calculadas)
    finally:
        _ocupado[0] = ocupado_antes
    for folha in _folhas_portas(grupo):
        gerar_malha_chapa(folha)
    context.view_layer.update()
    refazer = set()
    for pux in orfaos:
        folha = _folha_mais_proxima(pux, _folhas_portas(grupo))
        if (folha is not None and _eh_puxador_parametrico(pux)
                and pux['puxador_tipo'] == 'PERFIL'
                and pux.get('puxador_borda') in _rebaixos_da_chapa(folha)):
            # a folha que fica ja' tem perfil nessa borda: sobraria dobrado
            bpy.data.objects.remove(pux, do_unlink=True)
            continue
        _ligar_puxador(pux, folha)
        if folha is not None and _eh_puxador_parametrico(pux):
            refazer.add(folha.name)
    for nome in refazer:
        # parametrico vai para a mesma borda/fracao da folha nova
        gerar_malha_chapa(bpy.data.objects[nome])
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
    for pux in [c for c in folha.children if MARCA_PUXADOR in c
                and not _eh_puxador_parametrico(c)]:
        relativo = pux.matrix_parent_inverse @ pux.matrix_basis
        cantos = [relativo @ Vector(c) for c in pux.bound_box]
        travas = list(pux.get(CHAVE_TRAVAS_PUXADOR, (1, 1, 1)))
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
# duas chapas diferentes. Aqui o usuario fica em Modo Objeto: o cursor
# ganha um ima que gruda no vertice mais proximo, o primeiro clique
# fixa um canto e a previa das folhas acompanha o mouse ate' o segundo.
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
                if MARCA_CHAPA in obj:
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
# responde sozinho e o teste clica nelas.
OPCOES_CONFIRMAR = (('SIM', 'Sim, criar assim'), ('NAO', 'Nao, marcar de novo'))
OPCOES_FOLHAS = (('1', '1 folha'), ('2', '2 folhas'))
TIPOS_SOBREPOSTA = (('GIRO', 'Giro'), ('BASCULANTE', 'Basculante'))
TIPOS_EMBUTIDA = (('GIRO', 'Giro (Super Curva)'), ('CORRER', 'Correr'))
COR_FIO_COBERTURA = (1.0, 0.55, 0.1, 1.0)     # laranja (print do usuario)
COR_FIO_VAO = (1.0, 1.0, 1.0, 1.0)
COR_BORDA_EIXO = (0.25, 0.85, 0.3, 1.0)       # verde
MARGEM_DOBRADICAS_PADRAO = 100.0   # mm da quina: pratica de marcenaria
LIMITES_DOBRADICAS = (2, 6)
LIMITES_PISTOES = (1, 2)
_assistente_porta = [None]          # estado do wizard (o teste le daqui)


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
    aberta = _matriz_abertura(parametros, 0.0, 1, 0, folha, 1.0)
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


FACES_CAIXA = ((0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6),
               (0, 2, 6, 4), (1, 3, 7, 5))


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
# modelo cobre 12,75 mm da lateral; numa Reta de 18 mm a base entra uns
# 5 mm na chapa (na vida real e' o calco) -- presa na face, o canto da
# folha aberta e' que entrava no modulo.
PASTA_FERRAGENS = os.path.join(os.path.dirname(__file__), 'ferragens')
ARQUIVO_DOBRADICA_RETA = os.path.join(PASTA_FERRAGENS, 'dobradica_reta.blend')
PREFIXO_FURO = 'Cabinet Copo '        # Boolean do copo na folha
PECAS_REALCE_RIG = ('base', 'suporte', 'cabeca')
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
        len(_folhas_portas(grupo)), int(folha.get('porta_indice', 0)),
        _dados_da_folha(folha), folha.get(CHAVE_ABERTURA, 0.0))
    _girar_rigs(grupo, folha)


def _definir_abertura(context, folha, fracao):
    """Abre a folha `fracao` (0..1). Ferragens seguem por parentesco e o
    pistao pela mira."""
    grupo = _grupo_portas(folha)
    if grupo is None or MARCA_FOLHA not in folha:
        return False
    ocupado_antes = _ocupado[0]
    _ocupado[0] = True
    try:
        folha[CHAVE_ABERTURA] = max(0.0, min(1.0, float(fracao)))
        _posicionar_folha(grupo, folha)
    finally:
        _ocupado[0] = ocupado_antes
    context.view_layer.update()
    return True


def _dobradicas_da_porta(p, largura, altura, folhas):
    """[(aresta, distancias, indice da folha)]: onde vao as dobradicas
    (lado, quantidade e margem gravados pelo wizard)."""
    if p.get('abertura') == 'CORRER' or not folhas:
        return []
    lateral = float(p['lateral_mm'])
    cob = [float(p['folga_mm']) - i for i in _inicios_porta(p)]
    fracoes = {k: c / lateral for k, c in zip(COBERTURAS_LADOS, cob)}
    tipo = 'BASCULANTE' if p.get('abertura') == 'BASCULANTE' else 'GIRO'
    arestas = _arestas_da_porta(largura, altura, fracoes, lateral, tipo)
    lados = (['CIMA'] if tipo == 'BASCULANTE'
             else [_lado_da_folha(p, i, len(folhas)) for i in range(len(folhas))])
    margem = float(p.get('dobradicas_margem_mm', MARGEM_DOBRADICAS_PADRAO))
    saida = []
    for i, lado in enumerate(lados):
        aresta = next((a for a in arestas if a['lado'] == lado), arestas[0])
        comprimento = (aresta['b'] - aresta['a']).length
        qtd = (int(p.get('dobradicas_qtd', 0) or 0)
               or _qtd_dobradicas_padrao(comprimento))
        saida.append((aresta, _posicoes_ferragens(comprimento, qtd, margem), i))
    return saida


def _pistoes_da_porta(p, largura, altura, folhas):
    """Pistoes do basculante (mm, referencial do grupo, porta FECHADA).

    Modelo e posicao saem de `_pistao_do_vao` (automatico; o offset
    manual do wizard so' sobe, ate' o limite do pistao). Corpo e haste
    medem o FECHADO cada um: fechada a haste some no corpo, aberta os
    dois somam o aberto. Suporte = plaquinha na lateral (do eixo a' face
    interna) e pino nas costas da folha."""
    qtd = (int(p.get('pistoes_qtd', 0) or 0)
           or _qtd_pistoes_padrao(folhas[0][0]))
    g = _pistao_do_vao(altura, folhas[0],
                       float(p.get('pistoes_offset_mm', 0.0) or 0.0), p)
    meio = PISTAO_SUPORTE_LADO_MM / 2.0
    saida = []
    for lado in ('ESQUERDA', 'DIREITA')[:max(1, min(2, qtd))]:
        esquerda = lado == 'ESQUERDA'
        x = PISTAO_DA_LATERAL_MM if esquerda else largura - PISTAO_DA_LATERAL_MM
        na_lateral, na_folha, _aberta = _pontas_pistao(g, x, folhas[0])
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
                 for z in (na_folha.z, na_folha.z + PISTAO_SUPORTE_MM)]},
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
                              'matriz': _referencial_rig(
                                  aresta['dentro'], (ponto.x, ponto.y, fundo))})
            continue
        caixas = _caixas_dobradicas(aresta, distancias, centro[2] - e / 2.0)
        for k, (corpo, caneco) in enumerate(caixas):
            sufixo = '%s_%d' % (aresta['lado'], k)
            saida.append({'id': 'DOBRADICA_' + sufixo, 'tipo': 'DOBRADICA',
                          'folha': None, 'forma': 'CAIXA', 'cantos': corpo})
            saida.append({'id': 'CANECO_' + sufixo, 'tipo': 'CANECO',
                          'folha': i, 'forma': 'CILINDRO',
                          'origem': sum(caneco, Vector()) / 8.0,
                          'raio': CANECO_DIAMETRO_MM / 2.0,
                          'comprimento': CANECO_FUNDO_MM + CANECO_ABA_MM})
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


# ---- copias do rig da dobradica reta
COLECOES_DO_RIG = ('meshes', 'curves', 'armatures', 'materials',
                   'node_groups', 'images')
TIPO_DA_PECA_RIG = {'raiz': 'DOBRADICA_RIG', 'base': 'DOBRADICA',
                    'cabeca': 'CANECO', 'furo': 'DOBRADICA_FURO'}
# o que so' faz o rig funcionar nao aparece (o Blender ainda os avalia)
PECAS_OCULTAS_RIG = ('furo', 'controle', 'armacao', 'armacao_ik')


def _instanciar_rig(colecao, raiz_id):
    """Anexa uma copia do asset (modelo + rig do usuario, tal e qual) e
    devolve a raiz. Malhas, materiais e node groups repetidos voltam aos
    da 1a copia (`cabinet_origem`): o arquivo nao incha a cada porta."""
    antes = {nome: set(getattr(bpy.data, nome)) for nome in COLECOES_DO_RIG}
    with bpy.data.libraries.load(ARQUIVO_DOBRADICA_RETA, link=False) as (
            origem, destino):
        destino.objects = sorted(origem.objects)
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
    raiz = None
    for i, o in enumerate(o for o in destino.objects if o is not None):
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
            _ocultar_empty(o)
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
    folhas = _folhas_portas(grupo)
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
    folhas = _folhas_portas(grupo)
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
            if obj is None:
                obj = _instanciar_rig(colecao, item['id'])
                if obj is None:
                    continue
            obj.parent = grupo
            obj.matrix_parent_inverse = Matrix.Identity(4)
            matriz = item['matriz'].copy()
            matriz.translation = matriz.translation / 1000.0
            obj.matrix_basis = matriz
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
        if obj is None:
            nome = item['tipo'].title()
            obj = bpy.data.objects.new(
                nome, None if ponto else bpy.data.meshes.new(nome))
            colecao.objects.link(obj)
            obj[CHAVE_FERRAGEM] = item['tipo']
            obj[CHAVE_ID_FERRAGEM] = item['id']
            if ponto:
                _ocultar_empty(obj)
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
                    and any(m in o for m in (MARCA_CONJUNTO, MARCA_PORTAS,
                                             CHAVE_FERRAGEM))
                    and o.empty_display_size > TAMANHO_EMPTY_OCULTO * 1.5):
                _ocultar_empty(o)
        for o in [o for o in bpy.data.objects if CHAVE_FERRAGEM in o]:
            if not _vivo(o):
                continue        # saiu junto com a raiz do rig
            dono = o.parent
            while dono is not None and MARCA_PORTAS not in dono:
                dono = dono.parent
            if dono is None:
                _remover_ferragem(o)
        for grupo in [o for o in bpy.data.objects
                      if MARCA_PORTAS in o and o.get('porta_parametros')]:
            if _folhas_portas(grupo) and not _ferragens_portas(grupo):
                _refazer_ferragens(grupo)
        # armario apagado (X): a Collection dele nao fica vazia na cena
        for colecao in [c for c in bpy.data.collections
                        if c.get(MARCA_COLECAO_MODULO)
                        and not c.all_objects and not c.children]:
            bpy.data.collections.remove(colecao)
        _limpar_comodos_vazios()
    except Exception as e:
        print("[Cabinet Creator] ferragens:", e)
    return None


def _refazer_ferragens(grupo):
    """Ferragens de novo pelo que a porta guarda (desfazer arraste)."""
    p = grupo.get('porta_parametros')
    if not p:
        return
    folhas = _folhas_portas(grupo)
    ocupado_antes = _ocupado[0]
    _ocupado[0] = True
    try:
        _montar_ferragens(grupo, dict(p),
                          float(grupo.get('porta_vao_largura_mm', 0.0)),
                          float(grupo.get('porta_vao_altura_mm', 0.0)),
                          [_dados_da_folha(f) for f in folhas])
    finally:
        _ocupado[0] = ocupado_antes


def _botoes_assistente(ancora, opcoes, escala):
    """Botoes da caixa de escolha, ao lado de `ancora` (pixels)."""
    largura, altura, vao = 150 * escala, 26 * escala, 6 * escala
    x, y = ancora.x + 18 * escala, ancora.y - 14 * escala
    return [((x, y - i * (altura + vao), largura, altura), chave, texto)
            for i, (chave, texto) in enumerate(opcoes)]


def _botao_sob(botoes, mouse):
    for (x, y, w, h), chave, _t in botoes:
        if x <= mouse.x <= x + w and y <= mouse.y <= y + h:
            return chave
    return None


def _desenhar_assistente_2d(estado):
    """Caixa de escolha, bolinhas do snap e o recado do passo."""
    if estado is None:
        return
    regiao = getattr(bpy.context, 'region', None)
    if regiao is None or regiao.as_pointer() != estado['regiao']:
        return
    escala = max(1.0, bpy.context.preferences.system.ui_scale)
    realce = _cor_realce_hud()
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        for ponto in estado.get('bolinhas', ()):
            _bolinha_2d(shader, ponto, 6 * escala, (1.0, 1.0, 1.0, 1.0))
        if estado.get('snap_tela') is not None:
            _bolinha_2d(shader, estado['snap_tela'], 9 * escala, realce)
            _bolinha_2d(shader, estado['snap_tela'], 6 * escala,
                        (1.0, 1.0, 1.0, 1.0))
        blf.size(0, 12 * escala)
        for (x, y, w, h), chave, texto in estado.get('botoes', ()):
            borda = (realce if chave == estado.get('hover_botao')
                     else (0.35, 0.35, 0.35, 1.0))
            for (x0, y0, x1, y1), cor in (((x - 1, y - 1, x + w + 1, y + h + 1),
                                           borda),
                                          ((x, y, x + w, y + h),
                                           (0.06, 0.06, 0.06, 0.95))):
                shader.uniform_float('color', cor)
                batch_for_shader(shader, 'TRIS', {'pos': [
                    (x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1),
                    (x0, y1)]}).draw(shader)
            blf.position(0, x + 10 * escala, y + h / 2 - 4 * escala, 0)
            blf.color(0, 1.0, 1.0, 1.0, 1.0)
            blf.draw(0, texto)
        if estado.get('botoes') and estado.get('pergunta'):
            (x, y, _w, h), _c, _t = estado['botoes'][0]
            _caixa_texto_hud(x, y + h + 8 * escala, estado['pergunta'],
                             12 * escala, escala)
        # com caixa aberta a pergunta ja' esta' em cima dela; o recado no
        # mouse cobria o 2o botao
        if (estado.get('recado') and estado.get('mouse') is not None
                and not estado.get('botoes')):
            _caixa_texto_hud(estado['mouse'].x + 20 * escala,
                             estado['mouse'].y - 30 * escala,
                             estado['recado'], 12 * escala, escala)
    finally:
        gpu.state.blend_set('NONE')


class OBJECT_OT_apanhar_vao_portas(Operator):
    """Marca os 2 cantos do vao na viewport, com ima nos vertices"""
    bl_idname = "object.cabinet_apanhar_vao"
    bl_label = "Apanhar Vao das Portas"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    # ------------------------------------------------ ima
    def _mouse_na_regiao(self, event):
        # O apanhador costuma ser disparado da gaveta, que e' outra
        # area: mouse_region_* viria da gaveta, nao da viewport.
        return Vector((event.mouse_x - self._regiao.x,
                       event.mouse_y - self._regiao.y))

    def _imantar(self, event):
        alvo = self._mouse_na_regiao(event)
        melhor, melhor_obj, melhor_d = None, None, RAIO_IMA_PX
        for obj, vertices in self._alvos:
            for co in vertices:
                tela = view3d_utils.location_3d_to_region_2d(
                    self._regiao, self._rv3d, co)
                if tela is None:
                    continue
                d = (tela - alvo).length
                if d < melhor_d:
                    melhor, melhor_obj, melhor_d = co, obj, d
        self._imantado = melhor
        self._objeto_imantado = melhor_obj

    # ------------------------------------------------ previa
    def _referencia(self, obj_a, obj_b):
        """Mesma escolha de eixos que o operador fara' depois: os do
        modulo (pai comum), ou o mundo para porta solta."""
        if not OBJECT_OT_apanhar_vao_portas._associar(self, bpy.context):
            return Matrix.Identity(3)
        return _referencia_do_par(obj_a, obj_b)[0]

    def _associar(self, context):
        """Porta presa ao modulo? A corrente decide: a da porta que esta'
        sendo reposicionada, ou a da cena para porta nova."""
        alvo = bpy.data.objects.get(getattr(self, '_grupo_alvo', '') or '')
        if alvo is not None:
            return bool(alvo.get(CHAVE_MODULO_PORTA))
        return bool(getattr(context.scene, 'porta_associar', True))

    def _centro(self, obj_a, obj_b):
        """Ponto interno do movel, para saber que face olha para fora."""
        return _centro_do_movel(obj_a, obj_b)

    def _cliques(self):
        """Porta nova: 4 cliques (porta, vao, vao, porta). Reposicionar
        uma porta continua na diagonal de 2."""
        return 2 if getattr(self, '_grupo_alvo', '') else 4

    def _cantos_marcados(self):
        """Pontos ja' clicados e, enquanto marca, o que esta' sob o
        cursor. (Chamado pela classe: o teste usa um operador falso.)"""
        marcados = list(self._pontos)
        etapa = (getattr(self, '_w', None) or {}).get('etapa', 'DIAGONAL')
        if (etapa == 'DIAGONAL' and self._imantado is not None
                and len(marcados) < OBJECT_OT_apanhar_vao_portas._cliques(self)):
            marcados.append((self._imantado, self._objeto_imantado))
        return marcados

    def _previa(self):
        """Caixas das folhas pelos cantos marcados (o 4o pode ser o
        ponto sob o cursor).

        Usa os parametros da ABA, nao um padrao fixo: o que se ve
        arrastando tem de ser a porta que vai nascer. Quando a conta
        nao fecha, guarda o motivo em `_recado` -- antes a previa
        sumia calada e o usuario nao sabia o que estava errado.
        """
        tipo = OBJECT_OT_apanhar_vao_portas
        self._recado = ''
        marcados = tipo._cantos_marcados(self)
        portas = None
        if tipo._cliques(self) == 2:
            if len(marcados) < 2:
                return []
            (a, obj_a), (b, obj_b) = marcados[:2]
        else:
            if len(marcados) < 4:
                return []
            (p1, o1), (a, obj_a), (b, obj_b), (p4, o4) = marcados[:4]
            obj_a, obj_b = obj_a or o1, obj_b or o4
            portas = (p1, p4)
        obj_b = obj_b or obj_a
        # Reposicionando, os parametros sao os da porta e ela nao serve
        # de apoio para si mesma.
        alvo = bpy.data.objects.get(getattr(self, '_grupo_alvo', '') or '')
        parametros = _valores_portas(bpy.context.scene, alvo)
        apoios = tuple(None if alvo is not None and _grupo_portas(o) == alvo
                       else o for o in (obj_a, obj_b))
        if parametros['dobradica'] == 'ESCOLHER':
            parametros['dobradica'] = 'RETA'
        assistente = getattr(self, '_w', None)
        escolhas = assistente.get('escolhas', {}) if assistente else {}
        parametros.update(escolhas)
        # As mesmas espessuras que o operador vai resolver: a previa
        # tem de ser a porta que vai nascer.
        modulo = _modulo_da_chapa(obj_a)
        parametros['lateral_mm'] = _espessura_do_vao(modulo, apoios)
        if alvo is None:
            parametros['espessura_mm'] = _espessura_da_porta_nova(
                modulo, apoios)
        referencia = self._referencia(obj_a, obj_b)
        frente = _frente_automatica(referencia, a, b,
                                    self._centro(obj_a, obj_b))
        embutida = False
        try:
            (largura, altura, matriz), _, _, coberturas = _preparar_vao_portas(
                a, b, referencia, frente, parametros,
                modulo, apoios, portas=portas)
            parametros.update(coberturas)
            embutida = portas is not None and _porta_embutida(coberturas)
            if embutida and 'dobradica' not in escolhas:
                parametros['dobradica'] = 'SUPER_CURVA'
            folhas = _calcular_folhas_portas(largura, altura, parametros)
        except (ValueError, KeyError) as erro:
            self._recado = str(erro)
            return []
        self._recado = 'Vao %.0f x %.0f mm - %d folha(s)%s' % (
            largura, altura, len(folhas), ' - embutida' if embutida else '')
        if assistente is not None:
            _l, _a, e, centro = folhas[0]
            assistente.update(largura=largura, altura=altura,
                              matriz=matriz.copy(),
                              lateral=parametros['lateral_mm'],
                              coberturas=dict(coberturas), embutida=embutida,
                              costas=centro[2] - e / 2.0,
                              folha=(_l, _a, e, tuple(centro)),
                              parametros=dict(parametros))
        caixas = []
        for l, alt, e, centro in folhas:
            meia = Vector((l, alt, e)) / 2000.0
            c = Vector(centro) / 1000.0
            cantos = [matriz @ Vector((c.x + meia.x * sx,
                                       c.y + meia.y * sy,
                                       c.z + meia.z * sz))
                      for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
            caixas.append(cantos)
        return caixas

    def _desenhar(self):
        regiao = getattr(bpy.context, "region", None)
        if regiao is None or regiao.as_pointer() != self._regiao_ptr:
            return
        tema = bpy.context.preferences.themes[0]
        cor_ima = (*tema.view_3d.object_active, 1.0)
        cor_previa = (*tema.user_interface.wcol_regular.text, 0.9)
        linhas = []
        for cantos in self._previa():
            for i, j in ARESTAS_CAIXA:
                linhas.extend((cantos[i], cantos[j]))
        etapa = self._w.get('etapa')
        marcados = [p for p, _o in self._cantos_marcados()]
        arestas_cor = []
        if self._cliques() == 2:
            # reposicionar: a linha do 1o canto ate' o cursor
            if len(marcados) == 2:
                linhas.extend(marcados)
        elif etapa in {'DIAGONAL', 'CONFIRMAR'}:
            # o fio dos cliques (desenho do usuario): laranja = cobertura
            # (1-2 e 3-4), branco = o vao (2-3)
            for i in range(len(marcados) - 1):
                arestas_cor.append((COR_FIO_VAO if i == 1 else COR_FIO_COBERTURA,
                                    [marcados[i], marcados[i + 1]]))
        ferragens = []
        if etapa == 'EIXO':
            # a borda sob o mouse acende na cor da HUD
            destaque = (self._w.get('snap') or (None,))[0]
            for aresta in self._w.get('arestas', ()):
                arestas_cor.append((
                    _cor_realce_hud() if aresta is destaque else COR_BORDA_EIXO,
                    [self._mundo(aresta['a']), self._mundo(aresta['b'])]))
        caixas_ferragens = []
        if etapa in {'QUANTIDADE', 'MARGEM', 'PISTOES_QTD', 'PISTOES_OFFSET'}:
            caixas_ferragens, ferragens = self._ferragens_do_wizard()
        try:
            gpu.state.blend_set('ALPHA')
            gpu.state.depth_test_set('NONE')
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            shader.bind()
            if linhas:
                gpu.state.line_width_set(1.6)
                shader.uniform_float('color', cor_previa)
                batch_for_shader(shader, 'LINES', {'pos': linhas}).draw(shader)
            gpu.state.line_width_set(3.0)
            for cor, pontos in arestas_cor:
                shader.uniform_float('color', cor)
                batch_for_shader(shader, 'LINES', {'pos': pontos}).draw(shader)
            if caixas_ferragens:
                # volume da dobradica: faces translucidas + arestas
                realce = _cor_realce_hud()
                tris = [c[i] for c in caixas_ferragens for q in FACES_CAIXA
                        for i in (q[0], q[1], q[2], q[0], q[2], q[3])]
                shader.uniform_float('color', (*realce[:3], 0.28))
                batch_for_shader(shader, 'TRIS', {'pos': tris}).draw(shader)
                gpu.state.line_width_set(2.0)
                shader.uniform_float('color', realce)
                batch_for_shader(shader, 'LINES', {'pos': [
                    c[k] for c in caixas_ferragens for i, j in ARESTAS_CAIXA
                    for k in (i, j)]}).draw(shader)
            if ferragens:
                # pistao aberto: fio branco ate' a folha levantada
                gpu.state.line_width_set(1.5)
                shader.uniform_float('color', (1.0, 1.0, 1.0, 0.7))
                batch_for_shader(shader, 'LINES', {'pos': [
                    p for fio in ferragens for p in fio]}).draw(shader)
            marcas = [p[0] for p in self._pontos]
            if (self._imantado is not None and etapa == 'DIAGONAL'
                    and len(self._pontos) < self._cliques()):
                marcas.append(self._imantado)
            if marcas:
                gpu.state.point_size_set(11.0)
                shader.uniform_float('color', cor_ima)
                batch_for_shader(shader, 'POINTS',
                                 {'pos': marcas}).draw(shader)
        except Exception as e:
            print("[Cabinet Creator] previa do vao:", e)
        finally:
            try:
                gpu.state.line_width_set(1.0)
                gpu.state.point_size_set(1.0)
                gpu.state.blend_set('NONE')
            except Exception:
                pass

    # ------------------------------------------------ ciclo
    def _mundo(self, ponto_mm, z=0.0):
        """(x, y) em mm no referencial do vao -> ponto em mundo."""
        return self._w['matriz'] @ Vector((ponto_mm[0] / 1000.0,
                                            ponto_mm[1] / 1000.0, z))

    def _tela(self, ponto_mundo):
        return view3d_utils.location_3d_to_region_2d(
            self._regiao, self._rv3d, ponto_mundo)

    def _ferragens_do_wizard(self):
        """(caixas em mundo, fios dos pistoes abertos): o VOLUME de cada
        dobradica na face interna da chapa (corpo) e nas costas da folha
        (caneco); no basculante, tambem o de cada pistao fechado."""
        w = self._w
        aresta = w.get('aresta')
        if aresta is None:
            return [], []
        comprimento = (aresta['b'] - aresta['a']).length
        distancias = _posicoes_ferragens(comprimento, w['qtd'], w['margem'])
        # 2 folhas de giro: dobradicas nas DUAS bordas
        bordas = w['arestas'] if w.get('duas_bordas') else [aresta]
        caixas = [[w['matriz'] @ (p / 1000.0) for p in caixa]
                  for borda in bordas
                  for par in _caixas_dobradicas(borda, distancias,
                                                w.get('costas', 0.0))
                  for caixa in par]
        fios = []
        if w.get('pistoes') and w.get('folha'):
            # o VOLUME do pistao fechado (corpo, haste e suportes) no mesmo
            # realce das dobradicas, e um fio ate' onde ele vai aberto
            p = dict(_parametros_do_wizard(w), pistoes_qtd=w['pqtd'],
                     pistoes_offset_mm=w['poffset'])
            itens = _pistoes_da_porta(p, w['largura'], w['altura'],
                                      [w['folha']])
            caixas += [[w['matriz'] @ (v / 1000.0) for v in caixa]
                       for caixa in _caixas_dos_itens_pistao(itens)]
            g = _pistao_do_vao(w['altura'], w['folha'], w['poffset'], p)
            xs = (PISTAO_DA_LATERAL_MM, w['largura'] - PISTAO_DA_LATERAL_MM)
            for x in xs[:max(1, min(2, w['pqtd']))]:
                lateral, _fechada, aberta = _pontas_pistao(g, x, w['folha'])
                fios.append([w['matriz'] @ (lateral / 1000.0),
                             w['matriz'] @ (aberta / 1000.0)])
        return caixas, fios

    def _encerrar(self, context):
        _marcar_apanhando(False)
        _assistente_porta[0] = None
        if getattr(self, '_handler_2d', None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler_2d, 'WINDOW')
            self._handler_2d = None
        if self._area is not None:
            self._area.header_text_set(None)
        if self._handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
            self._handler = None
        if self._area is not None:
            self._area.tag_redraw()
        context.window.cursor_modal_restore()

    def invoke(self, context, event):
        self._area = context.area
        if _eh_area_gaveta(context):
            self._area = next(
                (a for a in context.screen.areas
                 if a.type == 'VIEW_3D' and a != context.area
                 and a.x > context.area.x and a.y == context.area.y), None)
        if self._area is None or self._area.type != 'VIEW_3D':
            self.report({'ERROR'}, "Sem viewport 3D para marcar o vao")
            return {'CANCELLED'}
        self._regiao = next((r for r in self._area.regions
                             if r.type == 'WINDOW'), None)
        self._rv3d = getattr(self._area.spaces.active, "region_3d", None)
        if self._regiao is None or self._rv3d is None:
            self.report({'ERROR'}, "Sem viewport 3D para marcar o vao")
            return {'CANCELLED'}
        self._regiao_ptr = self._regiao.as_pointer()

        # Com uma porta selecionada o gesto REPOSICIONA aquela porta: o
        # vao novo vem da diagonal, os parametros sao os dela.
        alvo = _grupo_portas(context.object)
        if alvo is not None and not alvo.get('porta_parametros'):
            alvo = None
        self._grupo_alvo = alvo.name if alvo is not None else ''

        # Um vao de mentira so' para validar os parametros: melhor
        # recusar agora do que deixar o usuario fazer o gesto inteiro
        # e so' entao descobrir que falta escolher a dobradica.
        try:
            _calcular_folhas_portas(
                1000.0, 1000.0, _valores_portas(context.scene, alvo))
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, "%s (aba Portas)" % erro)
            return {'CANCELLED'}

        self._alvos = _alvos_do_ima(context)
        if not self._alvos:
            self.report({'WARNING'}, "Nenhuma malha visivel para o ima")
            return {'CANCELLED'}
        self._pontos = []
        self._imantado = None
        self._objeto_imantado = None
        self._recado = ''
        self._handler = None
        self._w = {'etapa': 'DIAGONAL', 'regiao': self._regiao_ptr,
                   'botoes': [], 'escolhas': {}, 'bolinhas': [],
                   'snap_tela': None, 'mouse': None, 'recado': ''}
        _assistente_porta[0] = self._w
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            self._desenhar, (), 'WINDOW', 'POST_VIEW')
        self._handler_2d = bpy.types.SpaceView3D.draw_handler_add(
            _desenhar_assistente_2d, (self._w,), 'WINDOW', 'POST_PIXEL')
        _marcar_apanhando(True)
        context.window.cursor_modal_set('CROSSHAIR')
        context.window_manager.modal_handler_add(self)
        self.report({'INFO'}, self._instrucao())
        self._area.header_text_set(self._instrucao())
        return {'RUNNING_MODAL'}

    # ------------------------------------------------ wizard
    RECADOS = {
        'CONFIRMAR': 'A cobertura nao bate com reta, meia nem embutida',
        'FOLHAS': 'Quantas folhas?',
        'TIPO': 'Escolha a abertura',
        'EIXO': "Clique na borda das dobradicas (o tipo e' automatico)",
        'QUANTIDADE': 'Scroll: quantidade de dobradicas | clique confirma',
        'MARGEM': 'Mova em Y: distancia das quinas | clique confirma',
        'PISTOES_QTD': 'Scroll: quantidade de pistoes | clique confirma',
        'PISTOES_OFFSET': 'Posicao automatica | mova em Y para subir o '
                          'pistao | clique cria a porta',
    }
    PASSOS_CANTOS = ('1/4: canto da porta', '2/4: canto do vao',
                     '3/4: canto oposto do vao', '4/4: canto oposto da porta')
    PERGUNTAS = {'CONFIRMAR': (OPCOES_CONFIRMAR, 'As medidas estao corretas?'),
                 'FOLHAS': (OPCOES_FOLHAS, 'Quantas folhas?')}

    def _instrucao(self):
        if self._cliques() == 2:
            return 'Clique nos 2 cantos do vao (Esc cancela)'
        return ('Clique %s -- porta e vao no mesmo ponto: clique 2x '
                '(Esc cancela)' % self.PASSOS_CANTOS[min(len(self._pontos), 3)])

    def _ir(self, etapa, mouse=None):
        w = self._w
        w['etapa'] = etapa
        w['botoes'], w['hover_botao'], w['bolinhas'] = [], None, []
        w['snap_tela'], w['snap'] = None, None
        escala = max(1.0, bpy.context.preferences.system.ui_scale)
        ancora = mouse if mouse is not None else w.get('mouse') or Vector((200, 200))
        if etapa in self.PERGUNTAS or etapa == 'TIPO':
            opcoes, pergunta = self.PERGUNTAS.get(
                etapa, (w.get('tipos', ()), 'Abertura:'))
            w['botoes'] = _botoes_assistente(ancora, opcoes, escala)
            w['pergunta'] = pergunta
        elif etapa == 'EIXO':
            w['arestas'] = _arestas_da_porta(w['largura'], w['altura'],
                                             w['coberturas'], w['lateral'],
                                             w['tipo'])
        elif etapa == 'QUANTIDADE':
            comprimento = (w['aresta']['b'] - w['aresta']['a']).length
            w['qtd'] = _qtd_dobradicas_padrao(comprimento)
            w['margem'] = MARGEM_DOBRADICAS_PADRAO
        elif etapa in {'MARGEM', 'PISTOES_OFFSET'}:
            w['y0'] = ancora.y
            w['valor0'] = w['margem'] if etapa == 'MARGEM' else w['poffset']
            # mm por pixel medido no proprio eixo (vale de qualquer zoom)
            if etapa == 'MARGEM':
                a, b = w['aresta']['a'], w['aresta']['b']
            else:
                a, b = Vector((0, 0)), Vector((0, w['altura']))
            ta, tb = self._tela(self._mundo(a)), self._tela(self._mundo(b))
            px = (tb - ta).length if ta is not None and tb is not None else 0
            w['mm_por_px'] = ((b - a).length / px) if px > 1 else 1.0
        elif etapa == 'PISTOES_QTD':
            # o pistao nasce na posicao AUTOMATICA (modelo e ponto pela
            # conta do aberto = 2x fechado); o offset manual parte dela
            g = _pistao_do_vao(w['altura'], w['folha'],
                               p=_parametros_do_wizard(w))
            w['pistoes'] = True
            w['pqtd'] = _qtd_pistoes_padrao(w['largura'])
            w['poffset'] = w['poffset_auto'] = g['offset']
        w['recado'] = self.RECADOS.get(etapa, '')
        # a aba Portas revela cada categoria respondida
        _redesenhar_viewports(bpy.context)
        if etapa == 'CONFIRMAR':
            fora = _lados_fora_do_padrao(w['coberturas'])
            w['recado'] = 'Cobertura fora do padrao: %s' % ', '.join(
                k[len('cobertura_'):-len('_e')] for k in fora)
        self._area.header_text_set(w['recado'])
        self._area.tag_redraw()

    def _recomecar(self):
        """"Nao, marcar de novo": volta ao 1o clique."""
        self._pontos = []
        self._w.update(etapa='DIAGONAL', botoes=[], escolhas={},
                       pistoes=False, duas_bordas=False, aresta=None)
        self._area.header_text_set(self._instrucao())
        self._area.tag_redraw()

    def _escolher(self, context, chave):
        """Resposta de uma caixa (CONFIRMAR, FOLHAS ou TIPO)."""
        w = self._w
        escolhas = w['escolhas']
        if w['etapa'] == 'CONFIRMAR':
            if chave == 'NAO':
                self._recomecar()
            else:
                self._ir('FOLHAS')
            return None
        if w['etapa'] == 'FOLHAS':
            escolhas['folhas'] = int(chave)
            opcoes = TIPOS_EMBUTIDA if w['embutida'] else TIPOS_SOBREPOSTA
            w['tipos'] = tuple(t for t in opcoes
                               if LIMITES_FOLHAS[t[0]] >= escolhas['folhas'])
            if len(w['tipos']) == 1:
                # 2 folhas por cima so' podem ser de giro: nada a perguntar
                return self._escolher_abertura(context, w['tipos'][0][0])
            self._ir('TIPO')
            return None
        return self._escolher_abertura(context, chave)

    def _escolher_abertura(self, context, chave):
        w = self._w
        escolhas = w['escolhas']
        escolhas['abertura'] = chave
        if chave == 'CORRER':
            escolhas['dobradica'] = 'RETA'
            return self._criar(context)
        w['tipo'] = chave
        if w['embutida']:
            escolhas['dobradica'] = 'SUPER_CURVA'
        w['duas_bordas'] = chave == 'GIRO' and escolhas.get('folhas', 1) > 1
        if w['duas_bordas'] or chave == 'BASCULANTE':
            # sem perguntar a borda: duas folhas de giro levam dobradicas
            # nas DUAS; o basculante, sempre na de CIMA (pedido do usuario)
            w['arestas'] = _arestas_da_porta(w['largura'], w['altura'],
                                             w['coberturas'], w['lateral'],
                                             chave)
            self._fixar_borda(w['arestas'][0])
            self._ir('QUANTIDADE')
            return None
        self._ir('EIXO')
        return None

    def _fixar_borda(self, aresta):
        """Borda das dobradicas escolhida: o TIPO sai da cobertura dela."""
        w = self._w
        w['aresta'] = aresta
        chave = COBERTURAS_LADOS[INDICE_LADO[aresta['lado']]]
        w['escolhas'].update(
            dobradica=_dobradica_da_cobertura(
                float(w['coberturas'].get(chave, 1.0)), w['embutida']),
            dobradica_lado=aresta['lado'])

    def _snap_sob_mouse(self, mouse):
        """(borda, ponto na tela) da borda mais perto do mouse."""
        melhor = None
        for aresta in self._w.get('arestas', ()):
            a = self._tela(self._mundo(aresta['a']))
            b = self._tela(self._mundo(aresta['b']))
            if a is None or b is None:
                continue
            d = _distancia_segmento_hud(mouse, a, b)
            if d > RAIO_IMA_PX:
                continue
            seg = b - a
            t = ((mouse - a).dot(seg) / seg.length_squared
                 if seg.length_squared > 1e-9 else 0.0)
            if melhor is None or d < melhor[0]:
                melhor = (d, aresta, a + seg * max(0.0, min(1.0, t)))
        return melhor[1:] if melhor else None

    def _etapa_wizard(self, context, event):
        """Tudo depois dos cantos. Devolve o resultado do modal."""
        w = self._w
        mouse = self._mouse_na_regiao(event)
        w['mouse'] = mouse
        etapa = w['etapa']
        caixa = etapa in {'CONFIRMAR', 'FOLHAS', 'TIPO'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and etapa in {
                'QUANTIDADE', 'PISTOES_QTD'}:
            passo = 1 if event.type == 'WHEELUPMOUSE' else -1
            if etapa == 'QUANTIDADE':
                w['qtd'] = max(LIMITES_DOBRADICAS[0],
                               min(LIMITES_DOBRADICAS[1], w['qtd'] + passo))
                w['recado'] = '%d dobradicas (scroll) | clique confirma' % w['qtd']
            else:
                w['pqtd'] = max(LIMITES_PISTOES[0],
                                min(LIMITES_PISTOES[1], w['pqtd'] + passo))
                w['recado'] = '%d pistao(oes) (scroll) | clique confirma' % w['pqtd']
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type == 'MOUSEMOVE':
            if caixa:
                w['hover_botao'] = _botao_sob(w['botoes'], mouse)
            elif etapa == 'EIXO':
                achado = self._snap_sob_mouse(mouse)
                w['snap'] = achado
                w['snap_tela'] = achado[1] if achado else None
                if achado:
                    lado = achado[0]['lado']
                    fracao = float(w['coberturas'].get(
                        COBERTURAS_LADOS[INDICE_LADO[lado]], 1.0))
                    w['recado'] = 'Dobradicas na borda %s: %s' % (
                        lado.lower(), NOME_DOBRADICA[_dobradica_da_cobertura(
                            fracao, w['embutida'])])
                else:
                    w['recado'] = self.RECADOS['EIXO']
            elif etapa in {'MARGEM', 'PISTOES_OFFSET'}:
                delta = (mouse.y - w['y0']) * w['mm_por_px']
                if etapa == 'MARGEM':
                    comprimento = (w['aresta']['b'] - w['aresta']['a']).length
                    w['margem'] = max(0.0, min(comprimento / 2.0,
                                               w['valor0'] + delta))
                    w['recado'] = 'Margem %.0f mm | clique confirma' % w['margem']
                else:
                    # de cima para baixo: descer o mouse aumenta o offset,
                    # mas so' ate' onde o pistao alcanca com a porta aberta
                    g = _pistao_do_vao(w['altura'], w['folha'],
                                       max(1e-3, w['valor0'] - delta),
                                       _parametros_do_wizard(w))
                    w['poffset'] = g['offset']
                    limite = g['offset'] >= g['offset_max'] - 0.5
                    w['recado'] = ('Pistao %.0f mm a %.0f mm do topo%s | '
                                   'clique cria' % (
                                       g['aberto'], g['offset'],
                                       ' (curso maximo)' if limite else ''))
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if caixa:
            chave = _botao_sob(w['botoes'], mouse)
            if chave is None:
                return {'RUNNING_MODAL'}
            resultado = self._escolher(context, chave)
            return resultado or {'RUNNING_MODAL'}
        if etapa == 'EIXO':
            achado = self._snap_sob_mouse(mouse)
            if achado is None:
                return {'RUNNING_MODAL'}
            self._fixar_borda(achado[0])
            self._ir('QUANTIDADE', mouse)
            return {'RUNNING_MODAL'}
        if etapa == 'QUANTIDADE':
            self._ir('MARGEM', mouse)
            return {'RUNNING_MODAL'}
        if etapa == 'MARGEM':
            if w['tipo'] == 'BASCULANTE':
                self._ir('PISTOES_QTD', mouse)
                return {'RUNNING_MODAL'}
            return self._criar(context)
        if etapa == 'PISTOES_QTD':
            self._ir('PISTOES_OFFSET', mouse)
            return {'RUNNING_MODAL'}
        if etapa == 'PISTOES_OFFSET':
            return self._criar(context)
        return {'RUNNING_MODAL'}

    def _voltar(self):
        """Botao direito: uma etapa para tras."""
        w = self._w
        etapa = w['etapa']
        if etapa in {'CONFIRMAR', 'FOLHAS'}:
            # desfaz o 4o clique
            self._pontos = self._pontos[:3]
            w.update(etapa='DIAGONAL', botoes=[], escolhas={})
            self._area.header_text_set(self._instrucao())
            self._area.tag_redraw()
            return
        escolha_do_tipo = 'TIPO' if len(w.get('tipos', ())) > 1 else 'FOLHAS'
        borda_automatica = (w.get('duas_bordas')
                            or w.get('tipo') == 'BASCULANTE')
        anteriores = {'TIPO': 'FOLHAS', 'EIXO': escolha_do_tipo,
                      'QUANTIDADE': (escolha_do_tipo if borda_automatica
                                     else 'EIXO'),
                      'MARGEM': 'QUANTIDADE', 'PISTOES_QTD': 'MARGEM',
                      'PISTOES_OFFSET': 'PISTOES_QTD'}
        anterior = anteriores.get(etapa, 'FOLHAS')
        if anterior in {'FOLHAS', 'TIPO'}:
            folhas = w['escolhas'].get('folhas')
            w['escolhas'] = ({'folhas': folhas} if anterior == 'TIPO'
                             and folhas else {})
            w['duas_bordas'], w['aresta'] = False, None
        if anterior == 'MARGEM':
            w['pistoes'] = False
        self._ir(anterior)

    def _criar(self, context):
        w = self._w
        extras = dict(w['escolhas'])
        if w.get('aresta') is not None:
            extras.update(dobradicas_qtd=w['qtd'],
                          dobradicas_margem_mm=float(w['margem']))
        if w.get('pistoes'):
            # na automatica grava 0: o pistao acompanha o modulo redimensionado
            manual = abs(w['poffset'] - w.get('poffset_auto', 0.0)) > 0.5
            extras.update(pistoes_qtd=w['pqtd'],
                          pistoes_offset_mm=float(w['poffset']) if manual else 0.0)
        return self._concluir(context, extras)

    def modal(self, context, event):
        if self._w['etapa'] != 'DIAGONAL':
            if event.type == 'ESC' and event.value == 'PRESS':
                self._encerrar(context)
                return {'CANCELLED'}
            if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
                self._voltar()
                return {'RUNNING_MODAL'}
            return self._etapa_wizard(context, event)
        # Navegar precisa continuar funcionando durante a marcacao.
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._encerrar(context)
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            self._imantar(event)
            self._previa()
            self._area.header_text_set(' | '.join(
                t for t in (self._instrucao(), self._recado) if t))
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self._imantar(event)
            if self._imantado is None:
                self.report({'WARNING'}, "Aproxime de um vertice")
                return {'RUNNING_MODAL'}
            self._pontos.append((self._imantado.copy(),
                                 self._objeto_imantado))
            self._area.tag_redraw()
            if len(self._pontos) < self._cliques():
                self._area.header_text_set(self._instrucao())
                return {'RUNNING_MODAL'}
            if self._grupo_alvo:
                # reposicionar: so' a diagonal, com os parametros da porta
                return self._concluir(context)
            # porta nova: o wizard segue (folhas, tipo, borda, ferragens)
            self._w['matriz'] = None
            self._previa()
            if self._w.get('matriz') is None:
                self.report({'WARNING'}, self._recado or "Vao invalido")
                self._pontos = self._pontos[:3]
                return {'RUNNING_MODAL'}
            mouse = self._mouse_na_regiao(event)
            if _lados_fora_do_padrao(self._w['coberturas']):
                self._ir('CONFIRMAR', mouse)
            else:
                self._ir('FOLHAS', mouse)
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}

    def _concluir(self, context, extras=None):
        portas = None
        if len(self._pontos) >= 4:
            (p1, o1), (a, obj_a), (b, obj_b), (p4, o4) = self._pontos[:4]
            obj_a, obj_b = obj_a or o1, obj_b or o4
            portas = (p1, p4)
        else:
            (a, obj_a), (b, obj_b) = self._pontos[:2]
        self._encerrar(context)
        referencia, pai = _referencia_do_par(obj_a, obj_b)
        # Cenario 2: o canto do vao caiu numa chapa, entao o vao
        # pertence ao modulo que a contem e a porta fica vinculada a ele.
        modulo = _modulo_da_chapa(obj_a)
        if not self._associar(context):
            # corrente partida: porta solta, eixos do mundo, sem pai
            referencia, pai, modulo = Matrix.Identity(3), None, None
        ativa = obj_a.matrix_world.to_quaternion().to_matrix()
        s = context.scene
        parametros = _parametros_portas_da_cena(s)
        parametros.update(extras or {})
        try:
            # EXEC_DEFAULT, nao INVOKE: os parametros ja' vieram da aba
            # Portas, entao nao ha' dialogo nenhum para abrir.
            bpy.ops.object.cabinet_portas(
                'EXEC_DEFAULT', capturado=True,
                ponto_a=a, ponto_b=b,
                quatro_pontos=portas is not None,
                porta_a=portas[0] if portas else (0.0, 0.0, 0.0),
                porta_b=portas[1] if portas else (0.0, 0.0, 0.0),
                objeto_a_nome=obj_a.name, objeto_b_nome=obj_b.name,
                referencia=tuple(v for linha in referencia for v in linha),
                referencia_ativa=tuple(v for linha in ativa for v in linha),
                pai_nome=pai.name if pai is not None else '',
                modulo_nome=modulo.name if modulo is not None else '',
                centro=self._centro(obj_a, obj_b),
                orientacao='AUTO', frente='AUTO',
                grupo_alvo=self._grupo_alvo,
                **parametros)
        except RuntimeError as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        return {'FINISHED'}


class OBJECT_OT_portas_parametricas(Operator):
    """Cria portas por 2 vertices diagonais ou reconfigura o grupo selecionado"""
    bl_idname = "object.cabinet_portas"
    bl_label = "Portas Parametricas"
    bl_options = {'REGISTER', 'UNDO'}

    editar: BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})
    grupo_nome: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    # Reposicionar: o vao novo e' marcado na viewport, mas a porta e' uma
    # que ja' existe -- os parametros sao os DELA e o grupo e' reusado.
    grupo_alvo: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    capturado: BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})
    ponto_a: FloatVectorProperty(size=3, options={'HIDDEN'})
    ponto_b: FloatVectorProperty(size=3, options={'HIDDEN'})
    # Wizard de 4 cliques: ponto_a/b sao os cantos do VAO e porta_a/b os
    # da PORTA (a cobertura de cada lado sai da diferenca).
    quatro_pontos: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})
    porta_a: FloatVectorProperty(size=3, options={'HIDDEN', 'SKIP_SAVE'})
    porta_b: FloatVectorProperty(size=3, options={'HIDDEN', 'SKIP_SAVE'})
    referencia: FloatVectorProperty(
        size=9, default=(1, 0, 0, 0, 1, 0, 0, 0, 1), options={'HIDDEN'})
    referencia_ativa: FloatVectorProperty(
        size=9, default=(1, 0, 0, 0, 1, 0, 0, 0, 1), options={'HIDDEN'})
    pai_nome: StringProperty(options={'HIDDEN'})
    modulo_nome: StringProperty(options={'HIDDEN'})
    objeto_a_nome: StringProperty(options={'HIDDEN'})
    objeto_b_nome: StringProperty(options={'HIDDEN'})
    orientacao: EnumProperty(
        name="Eixos do vao", default='AUTO',
        items=[('AUTO', "Pai comum / mundo", "Usa os eixos do pai comum, se existir"),
               ('MUNDO', "Mundo", "Largura X/Y e altura Z do mundo"),
               ('ATIVO', "Objeto ativo", "Para um movel rotacionado sem pai; altura Z local")])
    centro: FloatVectorProperty(size=3, options={'HIDDEN'})
    # Fora da interface: a face sai sempre da diagonal. Fica so' para
    # script e teste forcarem uma face.
    frente: EnumProperty(
        name="Frente", default='AUTO', options={'HIDDEN', 'SKIP_SAVE'},
        description="Direcao para fora, nos eixos do pai comum ou do mundo",
        items=[('AUTO', "Automatica",
                "Deduz a face pelos dois pontos marcados"),
               ('NEG_Y', "-Y (frontal)", "Exterior em -Y"),
               ('POS_Y', "+Y (traseira)", "Exterior em +Y"),
               ('NEG_X', "-X (esquerda)", "Exterior em -X"),
               ('POS_X', "+X (direita)", "Exterior em +X"),
               ('NEG_Z', "-Z (embaixo)", "Exterior em -Z"),
               ('POS_Z', "+Z (em cima)", "Exterior em +Z")])
    abertura: EnumProperty(name="Abertura", items=ITENS_ABERTURA,
                           default='GIRO', update=_limitar_folhas_portas)
    folhas: IntProperty(name="Folhas", default=1, min=1, max=4,
                        update=_limitar_folhas_portas)
    dobradica: EnumProperty(name="Dobradica / posicionamento",
                            items=ITENS_DOBRADICA, default='RETA')
    # So' o padrao quando o vao nao tem chapa nem modulo: no resto as
    # duas vem de `_espessura_do_vao` / `_espessura_da_porta_nova`.
    espessura_mm: EnumProperty(
        name="Espessura da porta (mm)", default='18',
        options={'HIDDEN', 'SKIP_SAVE'},
        items=[(str(int(e)), str(int(e)), "mm") for e in ESPESSURAS_PERMITIDAS])
    lateral_mm: EnumProperty(
        name="Espessura da lateral (mm)", default='18',
        options={'HIDDEN', 'SKIP_SAVE'},
        items=[(str(int(e)), str(int(e)), "mm") for e in ESPESSURAS_PERMITIDAS])
    folga_mm: FloatProperty(name="Folga no perimetro (mm)", default=0, min=0)
    entre_folhas_mm: FloatProperty(name="Folga entre folhas (mm)", default=2, min=0)
    afastamento_mm: FloatProperty(name="Afastamento frontal (mm)", default=0, min=0)
    recuo_embutida_mm: FloatProperty(name="Recuo da embutida (mm)", default=0, min=0)
    recuo_correr_mm: FloatProperty(
        name="Recuo para trilhos (mm)", default=30, min=0.1,
        description="Distancia da borda frontal ate a face externa da primeira folha")
    sobreposicao_mm: FloatProperty(name="Sobreposicao entre folhas (mm)", default=20, min=0)
    entre_planos_mm: FloatProperty(name="Folga entre planos (mm)", default=2, min=0.1)
    # Ferragens escolhidas no wizard (0 = automatico pela medida)
    dobradica_lado: EnumProperty(
        name="Lado das dobradicas", default='ESQUERDA',
        items=[('ESQUERDA', "Esquerda", ""), ('DIREITA', "Direita", ""),
               ('CIMA', "Cima", "Basculante")])
    dobradicas_qtd: IntProperty(name="Dobradicas", default=0, min=0, max=8)
    dobradicas_margem_mm: FloatProperty(name="Margem das dobradicas (mm)",
                                        default=100.0, min=0)
    pistoes_qtd: IntProperty(name="Pistoes", default=0, min=0, max=2)
    pistoes_offset_mm: FloatProperty(
        name="Pistao: distancia do topo (mm)", default=0.0, min=0,
        description="0 = automatico; manual so' ate' o curso do pistao")

    @classmethod
    def poll(cls, context):
        # Em Modo Objeto o vao pode chegar do apanhador
        # (`cabinet_apanhar_vao`), que passa os pontos ja' prontos; o
        # invoke e' quem valida o que faltar.
        return context.mode in {'EDIT_MESH', 'OBJECT'}

    def _capturar(self, context):
        a, b, ref, pai, obj_a, obj_b = _capturar_vertices_portas(
            context, com_objetos=True)
        self.ponto_a, self.ponto_b = a, b
        self.referencia = tuple(v for linha in ref for v in linha)
        ativa = context.edit_object.matrix_world.to_quaternion().to_matrix()
        self.referencia_ativa = tuple(v for linha in ativa for v in linha)
        self.pai_nome = pai.name if pai is not None else ''
        self.objeto_a_nome, self.objeto_b_nome = obj_a.name, obj_b.name
        modulo = _modulo_da_chapa(obj_a)
        self.modulo_nome = modulo.name if modulo is not None else ''
        if not getattr(context.scene, 'porta_associar', True):
            # corrente partida: solta, nos eixos do mundo (o centro do
            # movel ainda serve para saber que face olha para fora)
            self.referencia = tuple(v for linha in Matrix.Identity(3)
                                    for v in linha)
            self.pai_nome = self.modulo_nome = ''
        if modulo is not None:
            self.centro = _centro_do_movel(obj_a, obj_b)
        else:
            # Sem modulo, as origens: a caixa de dois pontos no mesmo
            # plano empata com eles e a frente ficava ao contrario.
            self.centro = (obj_a.matrix_world.translation
                           + obj_b.matrix_world.translation) / 2
        self.capturado = True

    def _ref(self):
        valores = self.referencia_ativa if self.orientacao == 'ATIVO' else self.referencia
        return (Matrix.Identity(3) if self.orientacao == 'MUNDO' else
                Matrix([valores[i:i + 3] for i in (0, 3, 6)]))

    def _objetos(self):
        alvo = bpy.data.objects.get(self.grupo_alvo) if self.grupo_alvo else None
        objetos = (bpy.data.objects.get(self.objeto_a_nome),
                   bpy.data.objects.get(self.objeto_b_nome))
        # A porta que se reposiciona nao serve de apoio para ela mesma.
        return tuple(None if o is not None and alvo is not None
                     and _grupo_portas(o) == alvo else o for o in objetos)

    def _preparar_vao(self):
        return _preparar_vao_portas(
            self.ponto_a, self.ponto_b, self._ref(), self._frente_resolvida(),
            self._parametros(), bpy.data.objects.get(self.modulo_nome),
            self._objetos(), portas=((self.porta_a, self.porta_b)
                                     if self.quatro_pontos else None))

    def _vao(self):
        return self._preparar_vao()[0]

    def _frente_resolvida(self):
        return _resolver_frente(self.frente, self._ref(), self.ponto_a,
                                self.ponto_b, self.centro)

    def _parametros(self):
        p = {nome: getattr(self, nome) for nome in _PARAMETROS_PORTAS}
        p['espessura_mm'] = float(self.espessura_mm)
        p['lateral_mm'] = float(self.lateral_mm)
        alvo = bpy.data.objects.get(self.grupo_alvo) if self.grupo_alvo else None
        if alvo is not None and alvo.get('porta_parametros'):
            p.update(_valores_portas(bpy.context.scene, alvo))
            # reposicionar mantem a cobertura de cada lado
            guardados = alvo['porta_parametros']
            p.update({k: float(guardados[k]) for k in COBERTURAS_LADOS
                      if k in guardados})
            p['lateral_mm'] = _espessura_do_vao(
                bpy.data.objects.get(self.modulo_nome), self._objetos(),
                p['lateral_mm'])
            return p
        if self.editar:
            # Reconfigurar nao mexe em espessura: a da porta vive no E
            # das folhas e a da lateral, no modulo.
            grupo = (bpy.data.objects.get(self.grupo_nome) if self.grupo_nome
                     else _grupo_portas(bpy.context.object))
            guardados = (grupo.get('porta_parametros') or {}) if grupo else {}
            for nome in ('espessura_mm', 'lateral_mm'):
                if nome in guardados:
                    p[nome] = float(guardados[nome])
            vinculado = (bpy.data.objects.get(grupo.get(CHAVE_MODULO_PORTA, ''))
                         if grupo else None)
            if vinculado is not None:
                p['lateral_mm'] = _espessura_do_vao(vinculado,
                                                    padrao=p['lateral_mm'])
            return p
        modulo = bpy.data.objects.get(self.modulo_nome)
        objetos = self._objetos()
        p['lateral_mm'] = _espessura_do_vao(modulo, objetos, p['lateral_mm'])
        p['espessura_mm'] = _espessura_da_porta_nova(modulo, objetos,
                                                     p['espessura_mm'])
        return p

    def invoke(self, context, event):
        try:
            if context.mode == 'OBJECT' and _grupo_portas(context.object) is not None:
                self.editar = True
            if self.editar:
                grupo = _grupo_portas(context.object)
                if grupo is None or context.mode != 'OBJECT':
                    raise ValueError("Selecione um grupo de portas no Modo Objeto")
                self.grupo_nome = grupo.name
                for nome, valor in grupo['porta_parametros'].items():
                    if nome in {'espessura_mm', 'lateral_mm'}:
                        # o enum so' tem as convencionais; espessura livre
                        # (25, 70...) vem do grupo em `_parametros`
                        texto = str(int(valor))
                        if float(valor) in ESPESSURAS_PERMITIDAS:
                            setattr(self, nome, texto)
                    elif nome in _PARAMETROS_PORTAS:
                        setattr(self, nome, valor)
            else:
                # Pontos ja' apanhados na viewport dispensam o Modo
                # Edicao; sem eles, cai na captura por vertices.
                if not self.capturado:
                    self._capturar(context)
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=440)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        try:
            if self.editar:
                grupo = bpy.data.objects.get(self.grupo_nome)
                largura = grupo['porta_vao_largura_mm']
                altura = grupo['porta_vao_altura_mm']
            else:
                layout.prop(self, 'orientacao')
                if self.orientacao == 'AUTO':
                    layout.label(text="Eixos: " + (self.pai_nome or "Mundo"))
                largura, altura, _ = self._vao()
            layout.label(text="Vao: %.1f x %.1f mm" % (largura, altura))
        except (ValueError, KeyError, TypeError) as erro:
            largura = altura = None
            layout.label(text=str(erro), icon='ERROR')
        layout.prop(self, 'abertura')
        linha = layout.row()
        linha.enabled = self.abertura != 'BASCULANTE'
        linha.prop(self, 'folhas')
        layout.label(text="Permitido: 1 a %d folha(s)" % LIMITES_FOLHAS[self.abertura])
        if self.abertura != 'CORRER':
            caixa = layout.box()
            caixa.label(text="Qual dobradica / posicionamento?")
            caixa.prop(self, 'dobradica', text="")
            if self.dobradica in {'RETA', 'CURVA'}:
                caixa.prop(self, 'afastamento_mm')
            elif self.dobradica == 'SUPER_CURVA':
                caixa.prop(self, 'recuo_embutida_mm')
            if self.folhas > 1:
                layout.prop(self, 'entre_folhas_mm')
        else:
            layout.label(text="Embutidas, em dois planos alternados")
            layout.prop(self, 'recuo_correr_mm')
            if self.folhas > 1:
                layout.prop(self, 'sobreposicao_mm')
                layout.prop(self, 'entre_planos_mm')
        layout.prop(self, 'folga_mm')
        if largura is not None:
            try:
                folhas = _calcular_folhas_portas(largura, altura, self._parametros())
                l, a, e, _ = folhas[0]
                layout.label(text="Cada folha: %.1f x %.1f x %.0f mm" % (l, a, e))
                if self.abertura == 'CORRER':
                    fundo = max(-f[3][2] + e / 2 for f in folhas)
                    layout.label(text="Profundidade ocupada desde a borda: %.1f mm" % fundo)
            except ValueError as erro:
                layout.label(text=str(erro), icon='ERROR')
        layout.label(text="Blocagem: somente os solidos das portas", icon='INFO')

    def check(self, context):
        return True

    def execute(self, context):
        try:
            grupo = None
            pai = None
            if self.editar:
                grupo = bpy.data.objects.get(self.grupo_nome) if self.grupo_nome else _grupo_portas(context.object)
                if grupo is None or MARCA_PORTAS not in grupo:
                    raise ValueError("Grupo de portas nao encontrado")
                largura = grupo['porta_vao_largura_mm']
                altura = grupo['porta_vao_altura_mm']
                matriz = grupo.matrix_world.copy()
                largura, altura, matriz = _vao_com_ancoras(
                    grupo, (largura, altura, matriz), self._parametros())
            else:
                if not self.capturado:
                    self._capturar(context)
                (largura, altura, matriz), pontos, ancoras, coberturas = self._preparar_vao()
                pai = bpy.data.objects.get(self.pai_nome) if self.pai_nome else None
                modulo = bpy.data.objects.get(self.modulo_nome)
                if modulo is not None:
                    pai = modulo
                if pai is not None and abs(pai.matrix_world.determinant()) < 1e-12:
                    raise ValueError("O pai do vao tem escala zero")
                grupo = (bpy.data.objects.get(self.grupo_alvo)
                         if self.grupo_alvo else None)
            parametros = self._parametros()
            if not self.editar:
                parametros.update(coberturas)
                if self.quatro_pontos and parametros['abertura'] != 'CORRER':
                    # dobradica automatica: a cobertura do lado dela
                    lado = parametros.get('dobradica_lado', 'ESQUERDA')
                    chave = COBERTURAS_LADOS[INDICE_LADO.get(lado, 0)]
                    parametros['dobradica'] = _dobradica_da_cobertura(
                        float(parametros.get(chave, 1.0)),
                        _porta_embutida(coberturas))
            _calcular_folhas_portas(largura, altura, parametros)
            # Validacoes ocorrem ainda em Edit Mode; erro/cancelamento
            # conserva os dois vertices e nao deixa objetos incompletos.
            if context.mode == 'EDIT_MESH' and not self.editar:
                bpy.ops.object.mode_set(mode='OBJECT')
            if self.editar:
                frente = grupo.get('porta_frente', 'NEG_Y')
                largura_em = grupo.get('porta_largura_em', 'X')
            else:
                frente = self._frente_resolvida()
                largura_em = _largura_do_vao(self._ref(), self.ponto_a,
                                             self.ponto_b)
            if grupo is not None and not self.editar:
                # Reposicionar: vinculos antigos saem; o pai passa a ser o
                # do vao novo (o modulo dele, se houver).
                for chave in [k for k in grupo.keys()
                              if k.startswith('porta_ancora_')
                              or k in {CHAVE_MODULO_PORTA, CHAVE_FOLGAS_PORTA,
                                       CHAVE_RECUO_PORTA}]:
                    del grupo[chave]
                if grupo.parent != pai:
                    grupo.parent = pai
                    if pai is not None:
                        grupo.matrix_parent_inverse = pai.matrix_world.inverted()
            grupo = _aplicar_portas(context, grupo, matriz, pai,
                                    largura, altura, parametros,
                                    frente=frente, largura_em=largura_em)
            if not self.editar:
                for indice, folha in ancoras.items():
                    grupo['porta_ancora_%d' % indice] = folha
            # Cenario 2: as folgas ate' as faces do modulo, em
            # espessuras, sao o que mantem a porta acompanhando o
            # redimensionamento depois.
            modulo = bpy.data.objects.get(self.modulo_nome)
            if modulo is not None and not self.editar:
                medido = _folgas_do_vao(modulo, *pontos, frente, largura_em)
                if medido is not None:
                    grupo[CHAVE_MODULO_PORTA] = modulo.name
                    grupo[CHAVE_FOLGAS_PORTA] = list(medido[0])
                    grupo[CHAVE_RECUO_PORTA] = medido[1]
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        for obj in context.selected_objects:
            obj.select_set(False)
        grupo.select_set(True)
        for folha in _folhas_portas(grupo):
            folha.select_set(True)
        context.view_layer.objects.active = grupo
        # Com modulo vinculado, ele vira o ativo: o painel passa a
        # mostrar as medidas do conjunto e o wireframe a volumetria do
        # modulo com as portas na frente (etapa 3).
        vinculado = bpy.data.objects.get(grupo.get(CHAVE_MODULO_PORTA, ''))
        if vinculado is not None:
            vinculado.select_set(True)
            context.view_layer.objects.active = vinculado
        self.report({'INFO'}, "%d folha(s) - vao %.1f x %.1f mm" %
                    (self.folhas, largura, altura))
        return {'FINISHED'}


# ========================================================== IMPORTACAO
# Objetos de fora -- um armario baixado, uma porta modelada, puxadores --
# chegam com qualquer rotacao, escala e origem. O que decide e' a FORMA:
# uma chapa e' uma caixa fina. Daqui saem chapas, modulos, folhas de
# porta, acessorios e puxadores que o resto do add-on ja' sabe tratar.
ESPESSURA_MAXIMA_CHAPA_MM = 40.0   # mais grosso que isto nao e' chapa
PROPORCAO_MINIMA_CHAPA = 3.0       # lados >= 3x a espessura
ENCHIMENTO_MINIMO_CHAPA = 0.85     # area em faces alinhadas a caixa
GRUPOS_MAXIMOS_NORMAIS = 64        # peca curva: para de agrupar normais
# Modificadores que nao mudam a forma; os outros (solidify, array...)
# ja' entraram na medida da peca e dobrariam se ficassem.
MODIFICADORES_COSMETICOS = {'BEVEL', 'WEIGHTED_NORMAL', 'EDGE_SPLIT',
                            'TRIANGULATE'}


def _faces_em_mundo(obj):
    """[(normal, area)] e vertices da malha AVALIADA, em mundo."""
    try:
        dep = bpy.context.evaluated_depsgraph_get()
        avaliado = obj.evaluated_get(dep)
    except Exception:
        avaliado = obj
    malha = avaliado.to_mesh()
    try:
        bm = bmesh.new()
        try:
            bm.from_mesh(malha)
            bm.transform(obj.matrix_world)
            bm.normal_update()
            faces = []
            for face in bm.faces:
                area = face.calc_area()
                if area > 1e-12:
                    faces.append((face.normal.copy(), area))
            vertices = [v.co.copy() for v in bm.verts]
        finally:
            bm.free()
    finally:
        avaliado.to_mesh_clear()
    return faces, vertices


def _normais_dominantes(faces):
    """Direcoes de face agrupadas (sem sinal), da com mais area a menor."""
    grupos = []
    for normal, area in faces:
        for grupo in grupos:
            if abs(grupo[0].dot(normal)) > 0.995:
                grupo[1] += area
                break
        else:
            if len(grupos) < GRUPOS_MAXIMOS_NORMAIS:
                grupos.append([normal.normalized(), area])
    return sorted(grupos, key=lambda g: -g[1])


def _analisar_peca(obj):
    """Caixa orientada da peca e se ela e' uma chapa.

    Devolve {'chapa', 'base', 'dims', 'centro'} ou None. `base` tem as
    colunas X = largura, Y = comprimento, Z = espessura (a convencao da
    chapa); `dims` = (L, C, E) em mm. Os eixos saem da normal com mais
    area -- numa placa, as duas faces grandes -- e da maior face
    perpendicular a ela. Empates (um cubo) ficam com os eixos locais do
    objeto, para uma peca ja' alinhada nao girar a toa.
    """
    if obj is None or obj.type != 'MESH':
        return None
    faces, vertices = _faces_em_mundo(obj)
    if not vertices:
        return None
    m3 = obj.matrix_world.to_3x3()
    local = [m3.col[i].normalized() if m3.col[i].length > 1e-12
             else Vector([float(i == j) for j in range(3)]) for i in range(3)]
    grupos = _normais_dominantes(faces)
    a1 = grupos[0][0] if grupos else local[2]
    a2 = next((g[0] for g in grupos[1:] if abs(g[0].dot(a1)) < 0.02), None)
    if a2 is None:
        # Sem face perpendicular (disco, peca curva): o eixo local mais
        # perpendicular serve de referencia no plano.
        a2 = min(local, key=lambda e: abs(e.dot(a1)))
    a2 = (a2 - a1 * a2.dot(a1)).normalized()
    eixos = [a1, a2, a1.cross(a2).normalized()]
    faixas = []
    for eixo in eixos:
        projecoes = [v.dot(eixo) for v in vertices]
        faixas.append((min(projecoes), max(projecoes)))
    tamanho = [(hi - lo) * 1000.0 for lo, hi in faixas]
    iz = min(range(3), key=lambda i: (round(tamanho[i], 1),
                                      -abs(eixos[i].dot(local[2]))))
    resto = [i for i in range(3) if i != iz]
    ix = max(resto, key=lambda i: abs(eixos[i].dot(local[0])))
    iy = next(i for i in resto if i != ix)
    z = eixos[iz] if eixos[iz].dot(local[2]) >= 0 else -eixos[iz]
    x = eixos[ix] if eixos[ix].dot(local[0]) >= 0 else -eixos[ix]
    y = z.cross(x).normalized()
    centro = sum((eixos[i] * (faixas[i][0] + faixas[i][1]) / 2.0
                  for i in range(3)), Vector())
    L, C, E = tamanho[ix], tamanho[iy], tamanho[iz]
    total = sum(area for _n, area in faces) or 1.0
    alinhada = sum(area for n, area in faces
                   if any(abs(n.dot(e)) > 0.995 for e in eixos))
    chapa = (0.05 < E <= ESPESSURA_MAXIMA_CHAPA_MM
             and min(L, C) >= PROPORCAO_MINIMA_CHAPA * E
             and alinhada / total >= ENCHIMENTO_MINIMO_CHAPA)
    return {'chapa': chapa, 'base': Matrix((x, y, z)).transposed(),
            'dims': (L, C, E), 'centro': centro}


def converter_em_chapa(obj, analise=None):
    """Transforma um objeto qualquer em chapa SEM tira-lo do lugar.

    A orientacao vai para a ROTACAO (invariante 1: local Z = espessura),
    a escala volta a 1 e a malha vira a caixa parametrica. Ler
    `obj.dimensions` em eixos de mundo, como antes, transformava uma
    lateral em pe' (18 x 400 x 700) numa chapa de espessura 30.
    """
    analise = analise or _analisar_peca(obj)
    if analise is None:
        return None
    L, C, E = analise['dims']
    pai = obj.parent
    if pai is not None and any(abs(s - 1.0) > 1e-4
                               for s in pai.matrix_world.to_scale()):
        # Pai com escala (FBX costuma vir em 0.01) faria a chapa herdar
        # escala, e a normalizacao a converteria em medida errada.
        mundo = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = mundo
    for mod in list(obj.modifiers):
        if mod.type not in MODIFICADORES_COSMETICOS:
            obj.modifiers.remove(mod)
    if obj.data.shape_keys:
        obj.shape_key_clear()
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    obj.matrix_world = Matrix.LocRotScale(
        analise['centro'], analise['base'].to_quaternion(),
        Vector((1.0, 1.0, 1.0)))
    obj[MARCA_CHAPA] = 1
    _ocupado[0] = True
    try:
        obj.chapa_auto = True
        obj.chapa_largura_mm = max(1.0, L)
        obj.chapa_comprimento_mm = max(1.0, C)
        obj.chapa_espessura_mm = _espessura_livre(E)
    finally:
        _ocupado[0] = False
    gerar_malha_chapa(obj)
    return analise


def _malhas_soltas(context):
    """Malhas selecionadas que ainda nao sao porta nem puxador."""
    return [o for o in context.selected_objects
            if o.type == 'MESH' and MARCA_FOLHA not in o
            and MARCA_PUXADOR not in o]


class OBJECT_OT_converter_modulo(Operator):
    """Converte a selecao num modulo: placas viram chapas, o resto acessorio"""
    bl_idname = "object.cabinet_converter_modulo"
    bl_label = "Converter em Modulo"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(_malhas_soltas(context))

    def execute(self, context):
        analises = {}
        for obj in _malhas_soltas(context):
            analise = _analisar_peca(obj)
            if analise is not None:
                analises[obj] = analise
        if not analises:
            self.report({'WARNING'}, "Nenhuma malha com volume na selecao")
            return {'CANCELLED'}
        placas = [o for o, a in analises.items()
                  if a['chapa'] or MARCA_CHAPA in o]
        # Regra do usuario: se nada parece chapa, tudo vira chapa.
        if not placas:
            placas = list(analises)
        acessorios = [o for o in analises if o not in placas]
        for obj in placas:
            if MARCA_CHAPA not in obj:
                converter_em_chapa(obj, analises[obj])
        context.view_layer.update()
        conj = agrupar_chapas(context, placas)
        for obj in acessorios:
            mundo = obj.matrix_world.copy()
            obj.parent = conj
            obj.matrix_parent_inverse = conj.matrix_world.inverted()
            obj.matrix_world = mundo
            obj[MARCA_ACESSORIO] = 1
            colecao = _colecao_do_modulo(conj)
            if colecao is not None:
                _mover_para_colecao(obj, colecao)
        self.report({'INFO'}, "Modulo com %d chapa(s) e %d acessorio(s)"
                    % (len(placas), len(acessorios)))
        return {'FINISHED'}


# ---------------------------------------------------------- puxadores
class OBJECT_OT_converter_puxador(Operator):
    """Marca os objetos selecionados como puxador, preservando as medidas"""
    bl_idname = "object.cabinet_converter_puxador"
    bl_label = "Converter em Puxador"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(
            MARCA_CHAPA not in o for o in _malhas_soltas(context))

    def execute(self, context):
        marcados = 0
        for obj in _malhas_soltas(context):
            if MARCA_CHAPA in obj:
                continue        # chapa nao vira puxador por engano
            obj[MARCA_PUXADOR] = 1
            obj[CHAVE_TRAVAS_PUXADOR] = [1, 1, 1]
            marcados += 1
        self.report({'INFO'}, "%d puxador(es); ligue-os a uma porta pela corrente"
                    % marcados)
        return {'FINISHED'}


def _puxadores_e_folhas_da_selecao(context):
    puxadores = [o for o in context.selected_objects if MARCA_PUXADOR in o]
    folhas = []
    for obj in context.selected_objects:
        grupo = _grupo_portas(obj)
        if grupo is None:
            continue
        for folha in ([obj] if MARCA_FOLHA in obj else _folhas_portas(grupo)):
            if folha not in folhas:
                folhas.append(folha)
    return puxadores, folhas


class OBJECT_OT_vincular_puxador(Operator):
    """Liga os puxadores selecionados a porta selecionada"""
    bl_idname = "object.cabinet_vincular_puxador"
    bl_label = "Vincular Puxador e Porta"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        puxadores, folhas = _puxadores_e_folhas_da_selecao(context)
        return context.mode == 'OBJECT' and bool(puxadores) and bool(folhas)

    def execute(self, context):
        puxadores, folhas = _puxadores_e_folhas_da_selecao(context)
        context.view_layer.update()
        for pux in puxadores:
            _ligar_puxador(pux, _folha_mais_proxima(pux, folhas))
        self.report({'INFO'}, "%d puxador(es) ligado(s)" % len(puxadores))
        return {'FINISHED'}


def _referencial_do_puxador(pux):
    """Base em que L/A/P do puxador sao medidos e o indice de cada um.

    Ligado: o da chapa pai -- folha ou chapa avulsa -- (X largura,
    Y altura, Z espessura). Solto: o do mundo, com a convencao das
    medidas (L = X, A = Z, P = Y).
    """
    folha = pux.parent if pux.parent is not None and MARCA_CHAPA in pux.parent else None
    if folha is not None:
        return folha.matrix_world.to_3x3().normalized(), (0, 1, 2), folha
    return Matrix.Identity(3), (0, 2, 1), None


def _medidas_do_puxador(pux):
    base, indices, _folha = _referencial_do_puxador(pux)
    inversa = base.transposed()
    pontos = [inversa @ (pux.matrix_world @ Vector(c)) for c in pux.bound_box]
    tamanho = [(max(p[k] for p in pontos) - min(p[k] for p in pontos)) * 1000.0
               for k in range(3)]
    travas = list(pux.get(CHAVE_TRAVAS_PUXADOR, (1, 1, 1)))
    return [(nome, tamanho[k], 'pux_%d' % k, bool(travas[k]), k)
            for nome, k in zip(('Largura', 'Altura', 'Profundidade'), indices)]


def _redimensionar_puxador(pux, eixo, valor_mm):
    """Escala o puxador em UM eixo do referencial, pelo centro dele."""
    base, _indices, _folha = _referencial_do_puxador(pux)
    inversa = base.transposed()
    pontos = [inversa @ (pux.matrix_world @ Vector(c)) for c in pux.bound_box]
    c_min = min(p[eixo] for p in pontos)
    c_max = max(p[eixo] for p in pontos)
    if c_max - c_min < 1e-9:
        raise ValueError("Puxador sem medida nesse eixo")
    escala = [1.0, 1.0, 1.0]
    escala[eixo] = (valor_mm / 1000.0) / (c_max - c_min)
    centro = Vector()
    centro[eixo] = (c_min + c_max) / 2.0
    no_referencial = (Matrix.Translation(centro)
                      @ Matrix.Diagonal((*escala, 1.0))
                      @ Matrix.Translation(-centro))
    base4 = base.to_4x4()
    pux.matrix_world = base4 @ no_referencial @ base4.inverted() @ pux.matrix_world


# ------------------------------------------- porta a partir de objetos
def _caixa_no_referencial(objs, base):
    """(lo, hi) em mm dos vertices das malhas, nos eixos de `base`."""
    inversa = base.transposed()
    pontos = [inversa @ (o.matrix_world @ v.co) * 1000.0
              for o in objs for v in o.data.vertices]
    if not pontos:
        raise ValueError("Folha sem geometria")
    return (Vector(tuple(min(p[i] for p in pontos) for i in range(3))),
            Vector(tuple(max(p[i] for p in pontos) for i in range(3))))


def _vao_inverso(caixa, parametros):
    """O vao que, com estes parametros, gera folhas nesta caixa.

    O inverso de `_calcular_folhas_portas`: externo = vao - 2*inicio,
    com inicio = folga - cobertura; o plano do vao fica atras da folha
    (sobreposta) ou na frente dela (embutida/correr). Com isso uma porta
    importada e' regenerada exatamente onde estava.
    Devolve (largura, altura, origem) -- origem em mm, nos eixos da caixa.
    """
    lo, hi = caixa
    p = parametros
    esq, dir_, baixo, cima = _inicios_porta(p)
    largura = (hi.x - lo.x) + esq + dir_
    altura = (hi.y - lo.y) + baixo + cima
    if p['abertura'] == 'CORRER':
        plano = hi.z + p['recuo_correr_mm']
    elif p['dobradica'] == 'SUPER_CURVA':
        plano = hi.z + p['recuo_embutida_mm']
    else:
        plano = lo.z - _afastamento_porta(p)
    return largura, altura, Vector((lo.x - esq, lo.y - baixo, plano))


def _matriz_do_vao(base, origem_mm):
    matriz = base.to_4x4()
    matriz.translation = base @ (origem_mm / 1000.0)
    return matriz


def _frente_no_mundo(normal):
    i = max(range(3), key=lambda k: abs(normal[k]))
    return ('NEG_' if normal[i] < 0 else 'POS_') + 'XYZ'[i]


def _novo_grupo_portas(context, pai=None):
    grupo = bpy.data.objects.new("Portas", None)
    context.collection.objects.link(grupo)
    grupo[MARCA_PORTAS] = 1
    _ocultar_empty(grupo)
    grupo.parent = pai
    # As medidas sao de mundo, mesmo quando o pai tem escala.
    if pai is not None:
        grupo.matrix_parent_inverse = pai.matrix_world.inverted()
    return grupo


def _guardar_puxadores(grupo):
    return [(p, p.matrix_world.copy()) for f in _folhas_portas(grupo)
            for p in f.children if MARCA_PUXADOR in p]


def _devolver_puxadores(grupo, guardados):
    """Puxadores voltam ao lugar de antes, ligados a folha mais perto.

    Para operacoes que so' REORIENTAM a porta (frente, vinculo): a
    folha e' a mesma caixa no mesmo lugar, mas os eixos dela mudaram, e
    sem isto o puxador giraria junto.
    """
    folhas = _folhas_portas(grupo)
    for pux, mundo in guardados:
        pux.parent = None
        pux.matrix_world = mundo
    bpy.context.view_layer.update()
    for pux, _mundo in guardados:
        _ligar_puxador(pux, _folha_mais_proxima(pux, folhas))


def _direcao_da_vista(context):
    """Do movel para quem olha, se houver uma viewport a mao."""
    for area in getattr(context.screen, 'areas', ()):
        if area.type == 'VIEW_3D' and not _eh_area_gaveta_bruto(area):
            espaco = area.spaces.active
            rv3d = getattr(espaco, 'region_3d', None)
            if rv3d is not None:
                return rv3d.view_rotation @ Vector((0.0, 0.0, 1.0))
    return None


def _porta_de_objetos(context, objs):
    """Uma folha de porta a partir de objetos importados.

    A maior placa vira a folha; o resto vira puxador dela. A frente vai
    para o lado do puxador (e' nele que se pega); sem puxador, para quem
    olha. De pe', a altura e' o Z do mundo; deitada, a largura e' o lado
    maior. "Definir como frente" corrige o palpite.
    """
    analises = {o: a for o in objs for a in [_analisar_peca(o)] if a}
    if not analises:
        raise ValueError("Selecione os objetos da porta")
    placas = [o for o, a in analises.items() if a['chapa']] or list(analises)
    placa = max(placas, key=lambda o: analises[o]['dims'][0]
                * analises[o]['dims'][1])
    outros = [o for o in analises if o is not placa]
    analise = analises[placa]
    base, (L, C, E) = analise['base'], analise['dims']
    normal = base.col[2].copy()
    if outros:
        alvo = (sum((_centro_mundo(o) for o in outros), Vector()) / len(outros)
                - analise['centro'])
    else:
        alvo = _direcao_da_vista(context)
        if alvo is None:
            alvo = (Vector((0, 0, 1)) if abs(normal.z) > 0.7
                    else Vector((0, -1, 0)))
    if normal.dot(alvo) < 0:
        normal = -normal
    if abs(normal.z) < 0.7:
        cima = Vector((0.0, 0.0, 1.0))
    else:
        cima = (base.col[1] if C < L else base.col[0]).copy()
        if cima.dot(Vector((1.0, 1.0, 0.0))) < 0:
            cima = -cima
    cima = (cima - normal * cima.dot(normal)).normalized()
    direita = cima.cross(normal).normalized()
    referencial = Matrix((direita, normal.cross(direita), normal)).transposed()

    parametros = _parametros_portas_da_cena(context.scene, numerico=True)
    parametros['folhas'] = 1
    if parametros['abertura'] == 'CORRER':
        parametros['abertura'] = 'GIRO'
    if parametros['dobradica'] == 'ESCOLHER':
        parametros['dobradica'] = 'RETA'
    parametros['espessura_mm'] = _espessura_livre(E)
    converter_em_chapa(placa, analise)
    context.view_layer.update()
    largura, altura, origem = _vao_inverso(
        _caixa_no_referencial([placa], referencial), parametros)
    grupo = _novo_grupo_portas(context)
    grupo.matrix_world = _matriz_do_vao(referencial, origem)
    placa[MARCA_FOLHA] = 1
    placa['porta_indice'] = 0
    placa.parent = grupo
    placa.matrix_parent_inverse = Matrix.Identity(4)
    largura_em = 'X' if abs(direita.x) >= abs(direita.y) else 'Y'
    _aplicar_portas(context, grupo, _matriz_do_vao(referencial, origem), None,
                    largura, altura, parametros,
                    frente=_frente_no_mundo(normal), largura_em=largura_em)
    for obj in outros:
        obj[MARCA_PUXADOR] = 1
        obj[CHAVE_TRAVAS_PUXADOR] = [1, 1, 1]
        _ligar_puxador(obj, placa)
    return grupo


class OBJECT_OT_folha_de_objetos(Operator):
    """Converte os objetos selecionados (placa + puxador) numa porta"""
    bl_idname = "object.cabinet_folha_de_objetos"
    bl_label = "Converter em Porta"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(
            MARCA_CHAPA not in o or o.parent is None
            or MARCA_CONJUNTO not in o.parent for o in _malhas_soltas(context))

    def execute(self, context):
        try:
            grupo = _porta_de_objetos(context, _malhas_soltas(context))
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        for obj in context.selected_objects:
            obj.select_set(False)
        grupo.select_set(True)
        context.view_layer.objects.active = grupo
        self.report({'INFO'}, "Folha criada; selecione outra e agrupe em porta dupla")
        return {'FINISHED'}


def _grupos_da_selecao(context):
    grupos = []
    for obj in context.selected_objects:
        grupo = _grupo_portas(obj)
        if grupo is not None and grupo.get('porta_parametros') and grupo not in grupos:
            grupos.append(grupo)
    return grupos


def _fundir_portas(context, g1, g2):
    """Duas portas de uma folha cada viram uma porta dupla."""
    folhas = [_folhas_portas(g) for g in (g1, g2)]
    if any(len(f) != 1 for f in folhas):
        raise ValueError("Selecione duas portas de UMA folha cada")
    base = g1.matrix_world.to_3x3().normalized()
    outra = g2.matrix_world.to_3x3().normalized()
    if base.col[2].dot(outra.col[2]) < 0.999:
        raise ValueError("As folhas nao estao viradas para o mesmo lado")
    if base.col[1].dot(outra.col[1]) < 0.999:
        raise ValueError("Folhas com orientacao diferente; use Definir como frente")
    p1, p2 = dict(g1['porta_parametros']), g2['porta_parametros']
    if abs(float(p1['espessura_mm']) - float(p2['espessura_mm'])) > 0.01:
        raise ValueError("As folhas tem espessuras diferentes")
    f1, f2 = folhas[0][0], folhas[1][0]
    c1, c2 = (_caixa_no_referencial([f], base) for f in (f1, f2))
    if (abs(c1[0].z - c2[0].z) > 1.0 or abs(c1[1].z - c2[1].z) > 1.0):
        raise ValueError("As folhas nao estao no mesmo plano")
    if (abs(c1[0].y - c2[0].y) > 1.0 or abs(c1[1].y - c2[1].y) > 1.0):
        raise ValueError("As folhas tem alturas diferentes")
    if c2[0].x < c1[0].x:
        (f1, c1), (f2, c2) = (f2, c2), (f1, c1)
    fresta = c2[0].x - c1[1].x
    if fresta < -0.5:
        raise ValueError("As folhas se sobrepoem")
    lo = Vector(tuple(min(c1[0][i], c2[0][i]) for i in range(3)))
    hi = Vector(tuple(max(c1[1][i], c2[1][i]) for i in range(3)))
    p1['folhas'] = 2
    p1['entre_folhas_mm'] = max(0.0, fresta)
    if p1['abertura'] == 'BASCULANTE':
        p1['abertura'] = 'GIRO'
    largura, altura, origem = _vao_inverso((lo, hi), p1)
    _calcular_folhas_portas(largura, altura, p1)       # recusa antes de mexer
    modulo = bpy.data.objects.get(g1.get(CHAVE_MODULO_PORTA, ''))
    for indice, folha in enumerate((f1, f2)):
        if folha.parent != g1:
            mundo = folha.matrix_world.copy()
            folha.parent = g1
            folha.matrix_parent_inverse = Matrix.Identity(4)
            folha.matrix_basis = g1.matrix_world.inverted() @ mundo
        folha['porta_indice'] = indice
    for filho in list(g2.children):
        mundo = filho.matrix_world.copy()
        filho.parent = g1
        filho.matrix_parent_inverse = g1.matrix_world.inverted()
        filho.matrix_world = mundo
    bpy.data.objects.remove(g2, do_unlink=True)
    _aplicar_portas(context, g1, _matriz_do_vao(base, origem), g1.parent,
                    largura, altura, p1)
    if modulo is not None:
        _vincular_porta_modulo(context, g1, modulo)
    return g1


class OBJECT_OT_porta_dupla(Operator):
    """Converte duas portas de uma folha numa porta dupla"""
    bl_idname = "object.cabinet_porta_dupla"
    bl_label = "Converter em Porta Dupla"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(_grupos_da_selecao(context)) == 2

    def execute(self, context):
        g1, g2 = _grupos_da_selecao(context)
        try:
            grupo = _fundir_portas(context, g1, g2)
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        context.view_layer.objects.active = grupo
        self.report({'INFO'}, "Porta dupla criada")
        return {'FINISHED'}


# -------------------------------------------- vincular porta e modulo
def _vincular_porta_modulo(context, grupo, modulo):
    """A porta passa a pertencer ao modulo e a acompanha-lo.

    A ANCORA sao as faces do modulo, nao um ponto: a mesma convencao das
    portas criadas no vao (`_folgas_do_vao`). Os parametros sao deduzidos
    da posicao: atras da face do modulo = embutida; na frente, a
    cobertura das laterais diz reta (~E) ou curva (~E/2).
    """
    parametros = dict(grupo['porta_parametros'])
    folhas = _folhas_portas(grupo)
    caixa = _caixa_do_modulo(modulo)
    limites = _limites_locais_modulo(modulo)
    if not folhas or caixa is None or limites is None:
        raise ValueError("Porta ou modulo sem geometria")
    E = caixa[3]
    lo_m, hi_m = limites
    eixos_modulo = modulo.matrix_world.to_quaternion().to_matrix()
    local = eixos_modulo.transposed()
    base_porta = grupo.matrix_world.to_3x3().normalized()
    frente = _frente_no_mundo(local @ base_porta.col[2])
    direita = local @ base_porta.col[0]
    largura_em = 'X' if abs(direita.x) >= abs(direita.y) else 'Y'
    il, _ia, inormal = _eixos_da_frente(frente, largura_em)
    pontos = [_local_no_modulo(modulo, f.matrix_world @ v.co)
              for f in folhas for v in f.data.vertices]
    lo_p = [min(p[i] for p in pontos) for i in range(3)]
    hi_p = [max(p[i] for p in pontos) for i in range(3)]
    positiva = frente.startswith('POS')
    sinal = 1.0 if positiva else -1.0
    face = hi_m[inormal] if positiva else lo_m[inormal]
    tras = lo_p[inormal] if positiva else hi_p[inormal]
    diante = hi_p[inormal] if positiva else lo_p[inormal]
    afastado = sinal * (tras - face)
    parametros['lateral_mm'] = _espessura_do_vao(modulo, padrao=E)
    if parametros['abertura'] == 'CORRER':
        parametros['recuo_correr_mm'] = max(0.1, -sinal * (diante - face))
    elif afastado < -0.5:
        parametros['dobradica'] = 'SUPER_CURVA'
        parametros['recuo_embutida_mm'] = max(0.0, -sinal * (diante - face))
    else:
        parametros['afastamento_mm'] = max(0.0, afastado)
        cobertura = max(0.0, ((lo_m[il] + E) - lo_p[il]
                              + hi_p[il] - (hi_m[il] - E)) / 2.0)
        parametros['dobradica'] = 'RETA' if cobertura >= 0.75 * E else 'CURVA'
        ideal = E if parametros['dobradica'] == 'RETA' else E / 2.0
        parametros['folga_mm'] = max(0.0, ideal - cobertura)
    referencial = _base_da_frente(eixos_modulo, frente, largura_em).transposed()
    largura, altura, origem = _vao_inverso(
        _caixa_no_referencial(folhas, referencial), parametros)
    matriz = _matriz_do_vao(referencial, origem)
    _calcular_folhas_portas(largura, altura, parametros)  # recusa antes
    girou = any(abs(a - b) > 1e-4 for linha_a, linha_b in
                zip(base_porta, referencial) for a, b in zip(linha_a, linha_b))
    guardados = _guardar_puxadores(grupo) if girou else []
    if grupo.parent != modulo:
        mundo = grupo.matrix_world.copy()
        grupo.parent = modulo
        grupo.matrix_parent_inverse = modulo.matrix_world.inverted()
        grupo.matrix_world = mundo
    for i in range(4):
        if 'porta_ancora_%d' % i in grupo:
            del grupo['porta_ancora_%d' % i]
    _aplicar_portas(context, grupo, matriz, modulo, largura, altura,
                    parametros, frente=frente, largura_em=largura_em)
    if guardados:
        _devolver_puxadores(grupo, guardados)
    canto_b = matriz @ Vector((largura / 1000.0, altura / 1000.0, 0.0))
    medido = _folgas_do_vao(modulo, matriz.translation, canto_b, frente,
                            largura_em)
    if medido is None:
        raise ValueError("Modulo sem medidas para ancorar a porta")
    grupo[CHAVE_MODULO_PORTA] = modulo.name
    grupo[CHAVE_FOLGAS_PORTA] = list(medido[0])
    grupo[CHAVE_RECUO_PORTA] = medido[1]
    return grupo


def _porta_e_modulo_da_selecao(context):
    grupos = _grupos_da_selecao(context)
    modulos = []
    for obj in context.selected_objects:
        if _grupo_portas(obj) is not None:
            continue
        modulo = obj if MARCA_CONJUNTO in obj else _modulo_da_chapa(obj)
        if modulo is not None and modulo not in modulos:
            modulos.append(modulo)
    return grupos, modulos


class OBJECT_OT_vincular_porta(Operator):
    """Liga a porta (unica ou dupla) selecionada ao modulo selecionado"""
    bl_idname = "object.cabinet_vincular_porta"
    bl_label = "Vincular Porta e Modulo"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        grupos, modulos = _porta_e_modulo_da_selecao(context)
        return context.mode == 'OBJECT' and bool(grupos) and len(modulos) == 1

    def execute(self, context):
        grupos, modulos = _porta_e_modulo_da_selecao(context)
        try:
            for grupo in grupos:
                _vincular_porta_modulo(context, grupo, modulos[0])
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        self.report({'INFO'}, "%d porta(s) ligada(s) ao modulo; use "
                    "Reposicionar para encaixar no vao" % len(grupos))
        return {'FINISHED'}


# ------------------------------------- corrente Modulos | Portas
# A corrente e' o INTERRUPTOR de associacao (substituiu "Eixos do vao"):
# ligada = a porta pertence ao modulo e usa os eixos dele; partida = a
# porta e' solta, nos eixos do mundo. Com uma porta ATIVA (2o/3o nivel
# do clique) ela mostra e troca o estado DAQUELA porta; sem porta ativa,
# decide como nasce a proxima (`Scene.porta_associar`). O modulo
# selecionado tambem seleciona as portas dele -- por isso vale a ATIVA.
CHAVE_MODULO_ANTIGO = "porta_modulo_antigo"


def _porta_ativa(context):
    grupo = _grupo_portas(context.object)
    return grupo if grupo is not None and grupo.get('porta_parametros') else None


def _corrente_porta_ligada(context):
    grupo = _porta_ativa(context)
    if grupo is not None:
        return bool(grupo.get(CHAVE_MODULO_PORTA))
    return bool(getattr(context.scene, 'porta_associar', True))


def _desvincular_porta(grupo):
    """A porta fica onde esta', mas deixa de seguir o modulo."""
    antigo = grupo.get(CHAVE_MODULO_PORTA)
    mundo = grupo.matrix_world.copy()
    grupo.parent = None
    grupo.matrix_world = mundo
    for chave in (CHAVE_MODULO_PORTA, CHAVE_FOLGAS_PORTA, CHAVE_RECUO_PORTA):
        if chave in grupo:
            del grupo[chave]
    if antigo:
        # religar pela mesma corrente volta para o mesmo modulo
        grupo[CHAVE_MODULO_ANTIGO] = antigo


class OBJECT_OT_corrente_porta(Operator):
    """Associa a porta ao modulo (corrente ligada) ou ao mundo (partida).
    Sem porta ativa, vale para a proxima porta criada"""
    bl_idname = "object.cabinet_corrente_porta"
    bl_label = "Porta no Modulo / no Mundo"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        grupo = _porta_ativa(context)
        if grupo is None:
            s = context.scene
            s.porta_associar = not s.porta_associar
            self.report({'INFO'}, "Proxima porta: " + (
                "presa ao modulo" if s.porta_associar else "solta, no mundo"))
            return {'FINISHED'}
        if grupo.get(CHAVE_MODULO_PORTA):
            _desvincular_porta(grupo)
            self.report({'INFO'}, "Porta solta: eixos do mundo")
            return {'FINISHED'}
        _grupos, modulos = _porta_e_modulo_da_selecao(context)
        modulo = (modulos[0] if modulos else
                  bpy.data.objects.get(grupo.get(CHAVE_MODULO_ANTIGO, '')))
        if modulo is None or MARCA_CONJUNTO not in modulo:
            self.report({'WARNING'}, "Selecione tambem o modulo (Shift)")
            return {'CANCELLED'}
        try:
            _vincular_porta_modulo(context, grupo, modulo)
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        if CHAVE_MODULO_ANTIGO in grupo:
            del grupo[CHAVE_MODULO_ANTIGO]
        self.report({'INFO'}, "Porta presa ao modulo " + modulo.name)
        return {'FINISHED'}


# ---------------------------------------------------- definir a frente
def _definir_frente_porta(context, grupo, normal):
    """A face clicada passa a ser a FRENTE da porta.

    So' as faces grandes valem; a porta vira 180 graus em torno da
    altura, as folhas ficam no mesmo lugar e os puxadores tambem.
    Devolve False se a face clicada ja' era a frente.
    """
    base = grupo.matrix_world.to_3x3().normalized()
    alinhamento = Vector(normal).normalized().dot(base.col[2])
    if abs(alinhamento) < 0.9:
        raise ValueError("Clique numa das faces grandes da porta")
    if alinhamento > 0:
        return False
    cima, nova = base.col[1].copy(), -base.col[2]
    direita = cima.cross(nova).normalized()
    referencial = Matrix((direita, cima, nova)).transposed()
    parametros = dict(grupo['porta_parametros'])
    folhas = _folhas_portas(grupo)
    largura, altura, origem = _vao_inverso(
        _caixa_no_referencial(folhas, referencial), parametros)
    guardados = _guardar_puxadores(grupo)
    modulo = bpy.data.objects.get(grupo.get(CHAVE_MODULO_PORTA, ''))
    _aplicar_portas(context, grupo, _matriz_do_vao(referencial, origem),
                    grupo.parent, largura, altura, parametros,
                    frente=_frente_no_mundo(nova))
    _devolver_puxadores(grupo, guardados)
    if modulo is not None:
        _vincular_porta_modulo(context, grupo, modulo)
    return True


def _viewport_alvo(context):
    """(area, regiao, region_3d) da viewport onde clicar.

    Chamado da gaveta, que tambem e' uma VIEW_3D, o alvo e' a viewport
    vizinha -- a mesma regra do apanhador do vao.
    """
    area = context.area
    if area is not None and _eh_area_gaveta(context):
        area = next((a for a in context.screen.areas
                     if a.type == 'VIEW_3D' and a != context.area
                     and not _eh_area_gaveta_bruto(a)), None)
    if area is None or area.type != 'VIEW_3D':
        return None
    regiao = next((r for r in area.regions if r.type == 'WINDOW'), None)
    rv3d = getattr(area.spaces.active, 'region_3d', None)
    if regiao is None or rv3d is None:
        return None
    return area, regiao, rv3d


class OBJECT_OT_definir_frente(Operator):
    """Clique numa face grande da porta: ela passa a ser a frente"""
    bl_idname = "object.cabinet_definir_frente"
    bl_label = "Definir como Frente"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        grupo = _grupo_portas(context.object)
        return (context.mode == 'OBJECT' and grupo is not None
                and bool(grupo.get('porta_parametros')))

    def invoke(self, context, event):
        alvo = _viewport_alvo(context)
        if alvo is None:
            self.report({'ERROR'}, "Sem viewport 3D para clicar")
            return {'CANCELLED'}
        self._area, self._regiao, self._rv3d = alvo
        self._grupo = _grupo_portas(context.object).name
        self._area.header_text_set("Clique na face que e' a FRENTE da porta (Esc cancela)")
        context.window.cursor_modal_set('EYEDROPPER')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _encerrar(self, context):
        self._area.header_text_set(None)
        context.window.cursor_modal_restore()

    def modal(self, context, event):
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._encerrar(context)
            return {'CANCELLED'}
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        mouse = (event.mouse_x - self._regiao.x, event.mouse_y - self._regiao.y)
        origem = view3d_utils.region_2d_to_origin_3d(self._regiao, self._rv3d, mouse)
        direcao = view3d_utils.region_2d_to_vector_3d(self._regiao, self._rv3d, mouse)
        acertou, _ponto, normal, _face, obj, _matriz = context.scene.ray_cast(
            context.evaluated_depsgraph_get(), origem, direcao)
        grupo = bpy.data.objects.get(self._grupo)
        if not acertou or grupo is None or _grupo_portas(obj.original) != grupo:
            self.report({'WARNING'}, "Clique numa folha desta porta")
            return {'RUNNING_MODAL'}
        try:
            _definir_frente_porta(context, grupo, normal)
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, str(erro))
            return {'RUNNING_MODAL'}
        self._encerrar(context)
        return {'FINISHED'}


# ======================================== PUXADORES PARAMETRICOS
# Tres modelos prontos, montados no referencial da LINHA -- a borda da
# face onde o usuario clicou: X ao longo da borda, Y da borda para dentro
# da face, Z para fora da face. O estado mora no proprio puxador (borda,
# face, fracao, recuo) e `posicionar_puxador` refaz tudo a partir das
# PROPS da chapa: nao existe medida "antiga" para errar, entao porta,
# chapa ou modulo redimensionados levam o puxador junto.
MODELOS_PUXADOR = {
    # (nome, comprimento, recuo) em mm; perfil = borda inteira
    'PERFIL': ('Perfil', 0.0, 0.0),
    'ALCA': ('Alca', 148.0, 40.0),
    'BORDA': ('Borda', 60.0, 0.0),
}
ALTURA_PERFIL_MM = 30.0     # faixa da madeira que o perfil substitui
BORDAS_CHAPA = ('X-', 'X+', 'Y-', 'Y+')
MATERIAL_PUXADOR = "Puxador"


def _caixas_puxador(tipo, espessura, comprimento):
    """Caixas (x0, x1, y0, y1, z0, z1) em mm, no referencial da linha.

    PERFIL: perfil J rente as duas faces, no lugar da faixa cortada; a
    cava do dedo fica aberta na frente, entre a aba da borda e a placa
    da frente. ALCA: barra com duas pernas, de pe' na face. BORDA: tampa
    sentada na borda com uma aba fina caindo na frente da face.
    """
    meio, e = comprimento / 2.0, espessura
    if tipo == 'PERFIL':
        h = ALTURA_PERFIL_MM
        return [(-meio, meio, h - 2, h, -e, 0),     # base na madeira
                (-meio, meio, 15, h, -2, 0),        # frente, rente a face
                (-meio, meio, 0, h, -e, -e + 2),    # costas
                (-meio, meio, 0, 2, -e, -6)]        # aba na borda
    if tipo == 'ALCA':
        return [(-meio, meio, -5, 5, 20, 30),
                (-meio + 5, -meio + 15, -5, 5, 0, 20),
                (meio - 15, meio - 5, -5, 5, 0, 20)]
    return [(-meio, meio, -5, 0, -e, 8),
            (-meio, meio, -5, 15, 6, 8)]


def _material_puxador():
    material = bpy.data.materials.get(MATERIAL_PUXADOR)
    if material is None:
        material = bpy.data.materials.new(MATERIAL_PUXADOR)
        material.diffuse_color = (0.09, 0.09, 0.1, 1.0)
        material.metallic = 0.8
        material.roughness = 0.35
    return material


def gerar_malha_puxador(pux, espessura, comprimento):
    """Malha real por bmesh, como a da chapa (nada de escala)."""
    bm = bmesh.new()
    for x0, x1, y0, y1, z0, z1 in _caixas_puxador(
            pux['puxador_tipo'], espessura, comprimento):
        cubo = bmesh.ops.create_cube(bm, size=1.0)
        for v in cubo['verts']:
            v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0),
                           (y0 + y1) / 2 + v.co.y * (y1 - y0),
                           (z0 + z1) / 2 + v.co.z * (z1 - z0))) / 1000.0
    bm.to_mesh(pux.data)
    bm.free()
    pux.data.update()
    if not pux.data.materials:
        pux.data.materials.append(_material_puxador())


def _referencial_da_linha(chapa, borda, face):
    """(ao_longo, dentro, fora, ponto, tamanho) no espaco LOCAL da chapa.

    `ponto` e' o meio da borda, na superficie da face; `tamanho` o
    comprimento da borda em metros. Os tres vetores formam base direita
    (ao_longo = dentro x fora), entao a malha nunca sai invertida.
    """
    hx, hy, hz = _meias(chapa)
    sinal = 1.0 if borda.endswith('+') else -1.0
    fora = Vector((0.0, 0.0, 1.0 if face >= 0 else -1.0))
    if borda.startswith('Y'):
        dentro = Vector((0.0, -sinal, 0.0))
        ponto, tamanho = Vector((0.0, sinal * hy, fora.z * hz)), 2 * hx
    else:
        dentro = Vector((-sinal, 0.0, 0.0))
        ponto, tamanho = Vector((sinal * hx, 0.0, fora.z * hz)), 2 * hy
    return dentro.cross(fora), dentro, fora, ponto, tamanho


def _eh_puxador_parametrico(obj):
    return (obj is not None and MARCA_PUXADOR in obj
            and obj.get('puxador_tipo') in MODELOS_PUXADOR)


def posicionar_puxador(pux):
    """Refaz malha e lugar do puxador a partir da chapa pai.

    Comprimento fixo (perfil: a borda inteira), centro na FRACAO da
    borda -- o que estava no meio continua no meio --, recuo fixo da
    linha. Preso nas pontas: nunca passa da borda.
    """
    chapa = pux.parent
    if not _eh_puxador_parametrico(pux) or chapa is None or MARCA_CHAPA not in chapa:
        return False
    tipo = pux['puxador_tipo']
    ao_longo, dentro, fora, ponto, tamanho = _referencial_da_linha(
        chapa, pux.get('puxador_borda', 'Y+'), int(pux.get('puxador_face', 1)))
    if tipo == 'PERFIL':
        comprimento, x = tamanho * 1000.0, 0.0
    else:
        comprimento = float(pux.get('puxador_comprimento_mm',
                                    MODELOS_PUXADOR[tipo][1]))
        livre = max(0.0, tamanho - comprimento / 1000.0) / 2.0
        x = (float(pux.get('puxador_fracao', 0.5)) - 0.5) * tamanho
        x = max(-livre, min(livre, x))
    recuo = float(pux.get('puxador_recuo_mm', MODELOS_PUXADOR[tipo][2])) / 1000.0
    gerar_malha_puxador(pux, chapa.chapa_espessura_mm, comprimento)
    matriz = Matrix((ao_longo, dentro, fora)).transposed().to_4x4()
    matriz.translation = ponto + ao_longo * x + dentro * recuo
    pux.matrix_parent_inverse = Matrix.Identity(4)
    pux.matrix_basis = matriz
    return True


def _rebaixos_da_chapa(chapa):
    """{borda: metros} que os perfis filhos tiram da madeira."""
    return {f.get('puxador_borda', 'Y+'): ALTURA_PERFIL_MM / 1000.0
            for f in chapa.children
            if _eh_puxador_parametrico(f) and f['puxador_tipo'] == 'PERFIL'}


def _conferir_rebaixos():
    """Perfil apagado (X) ou movido: a chapa devolve a madeira.

    Sem isto a faixa cortada ficava vazia ate' a proxima mudanca de
    medida. So' olha quem tem `chapa_rebaixos`, entao custa pouco.
    """
    for obj in bpy.data.objects:
        gravado = obj.get('chapa_rebaixos')
        if gravado is None:
            continue
        if set(filter(None, gravado.split(','))) != set(_rebaixos_da_chapa(obj)):
            gerar_malha_chapa(obj)


def criar_puxador(context, chapa, tipo, borda, face, fracao=0.5):
    """Puxador novo pendurado na chapa (folha ou avulsa), ja' no lugar."""
    malha = bpy.data.meshes.new("Puxador")
    pux = bpy.data.objects.new("Puxador_" + MODELOS_PUXADOR[tipo][0], malha)
    (chapa.users_collection[0] if chapa.users_collection
     else context.collection).objects.link(pux)
    pux[MARCA_PUXADOR] = 1
    pux['puxador_tipo'] = tipo
    pux['puxador_borda'] = borda
    pux['puxador_face'] = 1 if face >= 0 else -1
    pux['puxador_fracao'] = max(0.0, min(1.0, float(fracao)))
    pux['puxador_comprimento_mm'] = MODELOS_PUXADOR[tipo][1]
    pux['puxador_recuo_mm'] = MODELOS_PUXADOR[tipo][2]
    pux.parent = chapa
    if tipo == 'PERFIL':
        # um perfil por borda: o novo substitui o velho
        for velho in [f for f in chapa.children if f != pux
                      and _eh_puxador_parametrico(f)
                      and f['puxador_tipo'] == 'PERFIL'
                      and f.get('puxador_borda') == borda]:
            bpy.data.objects.remove(velho, do_unlink=True)
        gerar_malha_chapa(chapa)        # corta a madeira e posiciona
    else:
        posicionar_puxador(pux)
    return pux


def _medidas_puxador_parametrico(pux):
    """Campos do bloco de medidas: comprimento e recuo, sem cadeado.

    O perfil nao tem o que editar (borda inteira, faixa fixa): a altura
    aparece so' para leitura (prop vazia = campo apagado).
    """
    tipo = pux['puxador_tipo']
    if tipo == 'PERFIL':
        return [('Altura do perfil', ALTURA_PERFIL_MM, '')]
    campos = [('Comprimento', float(pux.get('puxador_comprimento_mm',
                                            MODELOS_PUXADOR[tipo][1])),
               'puxp_comprimento')]
    if tipo == 'ALCA':
        campos.append(('Recuo', float(pux.get('puxador_recuo_mm',
                                              MODELOS_PUXADOR[tipo][2])),
                       'puxp_recuo'))
    return campos


# ---- ferramenta: clica numa linha, escolhe o ponto, scroll = snaps
_posicionador_puxador = [None]      # estado lido pelo desenho
_handler_posicionador = [None]
MAXIMO_SNAPS_PUXADOR = 15


def _snaps(n):
    """n subdivisoes da linha: 1 = centro, 2 = tercos, 3 = quartos..."""
    return [k / (n + 1) for k in range(1, n + 1)]


def _fracao_na_linha(a, b, mouse, n=0):
    """Mouse projetado no segmento a-b da tela; n >= 1 gruda no snap."""
    ab = b - a
    if ab.length_squared < 1e-9:
        t = 0.5
    else:
        t = max(0.0, min(1.0, (mouse - a).dot(ab) / ab.length_squared))
    if n >= 1:
        t = min(_snaps(n), key=lambda s: abs(s - t))
    return t


def _texto_fracao(t, n):
    if n >= 1:
        from fractions import Fraction
        f = Fraction(round(t * (n + 1)), n + 1)
        return '%d/%d' % (f.numerator, f.denominator)
    return '%d%%' % round(t * 100)


def _distancia_ao_segmento(p, a, b):
    ab = b - a
    if ab.length_squared < 1e-9:
        return (p - a).length
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (p - (a + ab * t)).length


def _borda_mais_proxima(segmentos, mouse):
    """{borda: (a, b) na tela} -> a borda mais perto do mouse."""
    if not segmentos:
        return None
    return min(segmentos, key=lambda b: _distancia_ao_segmento(
        mouse, *segmentos[b]))


def _bordas_da_face(chapa, face):
    """{borda: (ponta da fracao 0, ponta da fracao 1)} em MUNDO."""
    mundo = chapa.matrix_world
    bordas = {}
    for borda in BORDAS_CHAPA:
        ao_longo, _dentro, _fora, ponto, tamanho = _referencial_da_linha(
            chapa, borda, face)
        meio = ao_longo * (tamanho / 2.0)
        bordas[borda] = (mundo @ (ponto - meio), mundo @ (ponto + meio))
    return bordas


def _face_da_chapa(chapa, normal, direcao_vista):
    """+1 frente / -1 verso. Batendo na face estreita, vale a grande que
    esta' mais virada para quem olha."""
    eixo_z = chapa.matrix_world.to_3x3().col[2].normalized()
    local = chapa.matrix_world.to_3x3().inverted() @ normal
    if abs(local.z) >= max(abs(local.x), abs(local.y)):
        return 1 if local.z >= 0 else -1
    return 1 if eixo_z.dot(-direcao_vista) >= 0 else -1


def _quad_2d(a, b, largura):
    """Linha grossa em triangulos (line_width trava em 1 px em drivers)."""
    d = b - a
    if d.length < 1e-6:
        return []
    n = Vector((-d.y, d.x)).normalized() * (largura / 2.0)
    return [a + n, b + n, b - n, a + n, b - n, a - n]


def _desenhar_posicionador_puxador():
    estado = _posicionador_puxador[0]
    context = bpy.context
    if (estado is None or context.region is None
            or context.region.as_pointer() != estado['regiao']):
        return
    rv3d = context.region_data
    projetar = lambda p: view3d_utils.location_3d_to_region_2d(
        context.region, rv3d, p)
    escala = max(1.0, context.preferences.system.ui_scale)
    cor = _cor_linhas_hud(context)
    realce = _cor_realce_hud()
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    shader.bind()
    try:
        escolhida = estado.get('borda')
        for borda, (a, b) in estado.get('segmentos', {}).items():
            a2, b2 = projetar(a), projetar(b)
            if a2 is None or b2 is None:
                continue
            acesa = borda == escolhida
            shader.uniform_float('color', realce if acesa else (*cor[:3], 0.6))
            tris = _quad_2d(a2, b2, (5 if acesa else 2) * escala)
            if acesa and estado['fase'] == 'POSICAO':
                # riscos dos snaps atravessando a linha
                n = estado['n']
                d = (b2 - a2).normalized()
                lado = Vector((-d.y, d.x)) * 9 * escala
                for t in _snaps(n):
                    p = a2.lerp(b2, t)
                    tris += _quad_2d(p - lado, p + lado, 2 * escala)
            if tris:
                batch_for_shader(shader, 'TRIS', {'pos': tris}).draw(shader)
        if estado['fase'] == 'POSICAO' and escolhida in estado.get('segmentos', {}):
            a, b = estado['segmentos'][escolhida]
            ponto = projetar(a.lerp(b, estado['fracao']))
            if ponto is not None:
                texto = _texto_fracao(estado['fracao'], estado['n'])
                if estado['n'] == 0:
                    texto += '  (scroll: snaps)'
                _caixa_texto_hud(ponto.x + 14 * escala, ponto.y + 14 * escala,
                                 texto, 13 * escala, escala)
    finally:
        gpu.state.blend_set('NONE')


class OBJECT_OT_posicionar_puxador(Operator):
    """Clique numa borda da porta ou chapa; depois escolha o ponto nela
    (scroll para cima cria snaps: centro, tercos, quartos...)"""
    bl_idname = "object.cabinet_posicionar_puxador"
    bl_label = "Criar Puxador"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        alvo = _viewport_alvo(context)
        if alvo is None:
            self.report({'ERROR'}, "Sem viewport 3D para posicionar")
            return {'CANCELLED'}
        self._area, self._regiao, self._rv3d = alvo
        self._estado = {'regiao': self._regiao.as_pointer(), 'fase': 'LINHA',
                        'tipo': context.scene.cabinet_puxador_modelo,
                        'chapa': None, 'face': 1, 'borda': None,
                        'segmentos': {}, 'n': 0, 'fracao': 0.5, 'pux': None}
        _posicionador_puxador[0] = self._estado
        _redesenhar_viewports(context)
        if _handler_posicionador[0] is None:
            _handler_posicionador[0] = bpy.types.SpaceView3D.draw_handler_add(
                _desenhar_posicionador_puxador, (), 'WINDOW', 'POST_PIXEL')
        self._dica(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _dica(self, context):
        if self._estado['fase'] == 'LINHA':
            texto = ("Puxador %s: clique na BORDA onde ele vai | Esc cancela"
                     % MODELOS_PUXADOR[self._estado['tipo']][0])
        else:
            texto = ("Escolha o ponto | Scroll: snaps (%d) | Clique confirma"
                     " | Botao direito: outra borda" % self._estado['n'])
        self._area.header_text_set(texto)
        self._area.tag_redraw()

    def _mouse(self, event):
        return Vector((event.mouse_x - self._regiao.x,
                       event.mouse_y - self._regiao.y))

    def _projetados(self):
        projetar = lambda p: view3d_utils.location_3d_to_region_2d(
            self._regiao, self._rv3d, p)
        return {b: (projetar(a), projetar(c))
                for b, (a, c) in self._estado['segmentos'].items()
                if projetar(a) is not None and projetar(c) is not None}

    def _procurar_linha(self, context, mouse):
        estado = self._estado
        origem = view3d_utils.region_2d_to_origin_3d(self._regiao, self._rv3d, mouse)
        direcao = view3d_utils.region_2d_to_vector_3d(self._regiao, self._rv3d, mouse)
        acertou, _p, normal, _f, obj, _m = context.scene.ray_cast(
            context.evaluated_depsgraph_get(), origem, direcao)
        chapa = obj.original if acertou and obj is not None else None
        if chapa is not None and MARCA_PUXADOR in chapa:
            chapa = chapa.parent        # mirou no puxador: vale a chapa dele
        if chapa is None or MARCA_CHAPA not in chapa:
            estado.update(chapa=None, borda=None, segmentos={})
            return
        estado['chapa'] = chapa.name
        estado['face'] = _face_da_chapa(chapa, normal, direcao)
        estado['segmentos'] = _bordas_da_face(chapa, estado['face'])
        estado['borda'] = _borda_mais_proxima(self._projetados(), mouse)

    def _mover_puxador(self, mouse):
        estado = self._estado
        a, b = self._projetados().get(estado['borda'], (None, None))
        if a is None:
            return
        estado['fracao'] = _fracao_na_linha(a, b, mouse, estado['n'])
        pux = bpy.data.objects.get(estado['pux'] or '')
        if pux is not None:
            pux['puxador_fracao'] = estado['fracao']
            posicionar_puxador(pux)

    def _apagar_previa(self):
        pux = bpy.data.objects.get(self._estado['pux'] or '')
        if pux is not None:
            malha = pux.data
            bpy.data.objects.remove(pux, do_unlink=True)
            if malha.users == 0:
                bpy.data.meshes.remove(malha)
        self._estado['pux'] = None

    def _encerrar(self):
        _posicionador_puxador[0] = None
        for area in bpy.context.screen.areas if bpy.context.screen else ():
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        if _handler_posicionador[0] is not None:
            bpy.types.SpaceView3D.draw_handler_remove(
                _handler_posicionador[0], 'WINDOW')
            _handler_posicionador[0] = None
        self._area.header_text_set(None)
        self._area.tag_redraw()

    def cancel(self, context):
        self._apagar_previa()
        self._encerrar()

    def _confirmar(self, context, pux):
        for obj in context.selected_objects:
            obj.select_set(False)
        pux.select_set(True)
        context.view_layer.objects.active = pux
        self._encerrar()
        return {'FINISHED'}

    def modal(self, context, event):
        estado = self._estado
        rolagem = event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}
        if (event.type in {'MIDDLEMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM'}
                or event.type.startswith('NDOF')
                or (rolagem and estado['fase'] == 'LINHA')):
            return {'PASS_THROUGH'}        # orbitar/zoom continuam
        mouse = self._mouse(event)
        if event.type == 'MOUSEMOVE':
            if estado['fase'] == 'LINHA':
                self._procurar_linha(context, mouse)
            else:
                self._mover_puxador(mouse)
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if rolagem and event.value == 'PRESS':
            passo = 1 if event.type == 'WHEELUPMOUSE' else -1
            estado['n'] = max(0, min(MAXIMO_SNAPS_PUXADOR, estado['n'] + passo))
            self._mover_puxador(mouse)
            self._dica(context)
            return {'RUNNING_MODAL'}
        if event.type == 'ESC' and event.value == 'PRESS':
            self.cancel(context)
            return {'CANCELLED'}
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            if estado['fase'] == 'POSICAO':
                self._apagar_previa()
                estado['fase'] = 'LINHA'
                self._dica(context)
                return {'RUNNING_MODAL'}
            self.cancel(context)
            return {'CANCELLED'}
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if estado['fase'] == 'POSICAO':
            pux = bpy.data.objects.get(estado['pux'] or '')
            return self._confirmar(context, pux) if pux else {'RUNNING_MODAL'}
        self._procurar_linha(context, mouse)
        chapa = bpy.data.objects.get(estado['chapa'] or '')
        if chapa is None or estado['borda'] is None:
            return {'RUNNING_MODAL'}
        a, b = self._projetados()[estado['borda']]
        estado['fracao'] = _fracao_na_linha(a, b, mouse, estado['n'])
        pux = criar_puxador(context, chapa, estado['tipo'], estado['borda'],
                            estado['face'], estado['fracao'])
        if estado['tipo'] == 'PERFIL':
            return self._confirmar(context, pux)    # borda inteira: pronto
        estado['pux'] = pux.name
        estado['fase'] = 'POSICAO'
        self._dica(context)
        return {'RUNNING_MODAL'}


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
        convertidas = [o for o in alvos if converter_em_chapa(o) is not None]
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


def _grupo_ativo(context):
    o = context.object
    if o is None:
        return []
    if MARCA_CONJUNTO in o:
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
    _ocupado[0] = True
    try:
        s.grupo_largura_mm = (hi[0]-lo[0]) * 1000.0
        s.grupo_altura_mm = (hi[2]-lo[2]) * 1000.0
        s.grupo_profundidade_mm = (hi[1]-lo[1]) * 1000.0
        s.grupo_espessura_mm = chapas[0].chapa_espessura_mm
    finally:
        _ocupado[0] = False


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
        if MARCA_CONJUNTO in obj:
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
        elif MARCA_CHAPA in obj and _modo_chapa(context, obj) == 'GRUPO':
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
    if _ocupado[0]:
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
    if pai is not None and MARCA_CONJUNTO in pai:
        reposicionar_origem(pai)
        sincronizar_medidas_conjunto(pai)
        atualizar_portas_do_conjunto(pai)


def _upd_grupo_espessura(self, context):
    if _ocupado[0]:
        return
    val = self.grupo_espessura_mm
    alvo = _espessura_livre(val)
    if abs(val - alvo) > 1e-6:
        _ocupado[0] = True
        try:
            self.grupo_espessura_mm = alvo
        finally:
            _ocupado[0] = False
    chapas = _grupo_ativo(context)
    if chapas:
        aplicar_espessura_grupo(chapas, alvo)
        pai = chapas[0].parent
        if pai is not None and MARCA_CONJUNTO in pai:
            reposicionar_origem(pai)
            sincronizar_medidas_conjunto(pai)
            atualizar_portas_do_conjunto(pai)


class OBJECT_OT_sincronizar_grupo(Operator):
    """Le as medidas reais do grupo e atualiza os campos"""
    bl_idname = "object.cabinet_sincronizar_grupo"
    bl_label = "Ler Medidas do Grupo"

    def execute(self, context):
        sincronizar_grupo(context)
        return {'FINISHED'}


# ========================================== PRATELEIRA DE ASSETS
# O arrastar-e-soltar de verdade -- o MESMO do Asset Browser do Blender
# -- so' existe em editores nativos. `UILayout` nao expoe nada que
# inicie um arraste, e o `template_asset_view`, que os paineis usavam
# para isso, foi removido (nao existe mais no 5.x, junto com
# `bpy.types.AssetHandle`). Ou seja: a grade da sidebar nao tem como
# iniciar um arraste, por construcao da API.
#
# A AssetShelf, porem, E' registravel em Python e fica dentro da propria
# viewport. O arraste nativo vem LIGADO de fabrica: os pinceis do
# Blender e' que pedem 'NO_ASSET_DRAG' para desliga-lo. Nao pedindo
# nada, o item e' arrastavel e o solte cai no dropbox nativo da
# viewport, identico ao do Asset Browser.


class VIEW3D_AST_cabinet_creator(bpy.types.AssetShelf):
    """Prateleira com os presets: arraste o modulo direto para a cena."""
    bl_idname = "VIEW3D_AST_cabinet_creator"
    bl_space_type = 'VIEW_3D'
    bl_options = {'STORE_ENABLED_CATALOGS_IN_PREFERENCES'}
    bl_default_preview_size = 96
    # allowlist: so' o que faz sentido soltar na cena
    filter_object = True
    filter_group = True

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and not _eh_area_gaveta(context)

    @classmethod
    def asset_poll(cls, asset):
        return asset.id_type in {'OBJECT', 'COLLECTION'}


class OBJECT_OT_prateleira(Operator):
    """Mostra/esconde a prateleira de assets na viewport -- e' de la'
    que se ARRASTA o modulo para a cena"""
    bl_idname = "object.cabinet_prateleira"
    bl_label = "Prateleira de Assets"

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        registrar_bibliotecas()
        # Gravar show_region_asset_shelf direto falha com "read-only"
        # dependendo do contexto (o botao vive na sidebar, nao na
        # viewport). O operador de regiao do proprio Blender resolve
        # sempre -- e' o mesmo que o menu Ver usa.
        janela = next((r for r in context.area.regions
                       if r.type == 'WINDOW'), None)
        try:
            with context.temp_override(area=context.area, region=janela):
                bpy.ops.screen.region_toggle(region_type='ASSET_SHELF')
        except Exception as e:
            print("[Cabinet Creator] prateleira:", e)
            self.report({'WARNING'}, "Use Ver > Prateleira de Assets")
            return {'CANCELLED'}
        if getattr(context.space_data, "show_region_asset_shelf", False):
            self.report({'INFO'},
                        "Escolha a biblioteca 'Cabinet Creator' e arraste")
        return {'FINISHED'}


class CabinetCreatorPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    pasta_biblioteca: bpy.props.StringProperty(
        name="Pasta da biblioteca",
        subtype='DIR_PATH',
        description="Vazio: usa a pasta do proprio addon (a biblioteca da "
                    "empresa). Aponte para uma pasta de rede para "
                    "compartilhar entre os computadores",
        default="")

    foto_clicavel: bpy.props.BoolProperty(
        name="Foto do preset clicavel",
        description="Liga o clique na FOTO para posicionar o modulo. Em "
                    "troca a imagem pode aparecer listrada: ela e' montada "
                    "em ladrilhos e o bpy nao deixa fixar a largura deles, "
                    "entao so' fecha em certas larguras da barra lateral. "
                    "Desligado, a foto sai perfeita e o clique fica no nome",
        default=False)

    selecao_por_grupo: bpy.props.BoolProperty(
        name="Clique seleciona o modulo inteiro",
        description="Um clique acende todas as pecas do modulo; dois "
                    "cliques isolam a chapa. Desligado, o clique volta a "
                    "ser o do Blender",
        default=True)

    # Opcoes da engrenagem da gaveta. Ficam nas preferencias porque valem
    # para todo arquivo, nao para uma cena.
    unidade_padrao: bpy.props.EnumProperty(
        name="Unidade padrao", default='MM',
        description="Unidade de um numero digitado sem unidade",
        items=[(k, v[1], "") for k, v in UNIDADES_MEDIDA.items()])
    hud_espessura_linha: bpy.props.FloatProperty(
        name="Espessura das linhas", default=1.5,
        min=FAIXAS_OPCOES['hud_espessura_linha'][0],
        max=FAIXAS_OPCOES['hud_espessura_linha'][1])
    # Cores com nome novo (eram Enum): reaproveitar o nome faria o
    # Blender ler o inteiro gravado do Enum antigo como cor.
    # COLOR_GAMMA: o valor vai direto para a tela, como as cores do tema.
    hud_linha_tema: bpy.props.BoolProperty(
        name="Linhas na cor do tema", default=True)
    hud_rgb_linha: bpy.props.FloatVectorProperty(
        name="Cor das linhas", subtype='COLOR_GAMMA', size=3,
        min=0.0, max=1.0, default=(1.0, 1.0, 1.0))
    hud_rgb_realce: bpy.props.FloatVectorProperty(
        name="Cor do realce", subtype='COLOR_GAMMA', size=3,
        min=0.0, max=1.0, default=COR_REALCE_PADRAO)
    hud_realce_gizmo: bpy.props.BoolProperty(
        name="Realce nas cores do gizmo", default=False,
        description="L vermelho (X), A azul (Z), P verde (Y), E laranja")
    hud_tamanho_rotulo: bpy.props.IntProperty(
        name="Tamanho dos rotulos", default=14,
        min=FAIXAS_OPCOES['hud_tamanho_rotulo'][0],
        max=FAIXAS_OPCOES['hud_tamanho_rotulo'][1])
    tecla_corrente: bpy.props.EnumProperty(
        name="Correntes", default='ALT',
        items=[('ALT', "Segurar Alt", ""), ('CTRL', "Segurar Ctrl", ""),
               ('SHIFT', "Segurar Shift", ""), ('SEMPRE', "Sempre", "")],
        description="Quando as correntes de adjacencia aparecem")
    ocultar_contorno_grupo: bpy.props.BoolProperty(
        name="Ocultar o contorno do Blender no modulo", default=True,
        description="Com um modulo ou porta selecionado, desliga o "
                    "contorno de selecao da viewport e devolve o estado "
                    "anterior ao terminar")

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "selecao_por_grupo")
        layout.prop(self, "foto_clicavel")
        for nome in OPCOES_PADRAO:
            layout.prop(self, nome)
        layout.separator()
        layout.prop(self, "pasta_biblioteca")
        layout.label(text="Em uso: " + pasta_biblioteca(),
                     icon='ASSET_MANAGER')
        layout.operator("object.cabinet_registrar_bibliotecas", icon='FILE_REFRESH')
        layout.operator("object.cabinet_refiliar", icon='ASSET_MANAGER')
        layout.operator("object.cabinet_regerar_previews", icon='IMAGE_DATA')


class OBJECT_OT_registrar_bibliotecas(Operator):
    """Registra as pastas do addon como bibliotecas de assets"""
    bl_idname = "object.cabinet_registrar_bibliotecas"
    bl_label = "Registrar Bibliotecas no Blender"

    def execute(self, context):
        novas = registrar_bibliotecas(silencioso=False)
        if novas:
            self.report({'INFO'}, "Registrada(s): " + ", ".join(novas))
        else:
            self.report({'INFO'}, "Bibliotecas ja estavam registradas")
        return {'FINISHED'}


class OBJECT_OT_modo_medidas(Operator):
    """Alterna a edicao entre uma chapa e o conjunto"""
    bl_idname = "object.cabinet_modo_medidas"
    bl_label = "Modo de Medidas"
    bl_options = {'INTERNAL'}

    modo: StringProperty()

    def execute(self, context):
        obj = context.object
        if obj is None:
            return {'CANCELLED'}
        if self.modo == 'INDIVIDUAL' and MARCA_CONJUNTO in obj:
            chapas = _chapas_do_conjunto(obj)
            if not chapas:
                self.report({'WARNING'}, "Modulo sem chapas")
                return {'CANCELLED'}
            alvo = chapas[0]
            for selecionado in context.selected_objects:
                selecionado.select_set(False)
            alvo.select_set(True)
            context.view_layer.objects.active = alvo
            alvo.chapa_modo = 'INDIVIDUAL'
        elif MARCA_CHAPA in obj:
            obj.chapa_modo = self.modo
        elif self.modo != 'GRUPO':
            return {'CANCELLED'}
        return {'FINISHED'}


# ================================================ AJUSTE A' LARGURA
# O bpy nao mede texto nem informa quanto cabe num botao: ele so' corta
# pela direita, comendo o final do rotulo. Para decidir layout e
# encurtar nomes na mao, a largura da regiao e' convertida em pixels
# logicos e o texto e' estimado por estes valores.
# Medidos por captura de tela: com 6.5/10 o rotulo "Adjacencia" ainda
# era cortado numa sidebar de 280px. Estes valores sao propositalmente
# conservadores -- errar para o lado de sobrar espaco nao corta texto.
PX_CARACTERE = 7.5
PX_FOLGA_BOTAO = 14.0
PX_ICONE = 22.0
# largura minima para um botao de categoria continuar legivel
PX_MIN_NIVEL = 64.0


def _largura_painel(context):
    """Largura da regiao em pixels logicos (descontada a escala da UI)."""
    regiao = getattr(context, "region", None)
    try:
        escala = context.preferences.system.ui_scale or 1.0
    except Exception:
        escala = 1.0
    if regiao is None or not regiao.width:
        return 200.0
    return regiao.width / escala


def _px_botao(rotulo, com_icone=True):
    return (len(rotulo) * PX_CARACTERE + PX_FOLGA_BOTAO
            + (PX_ICONE if com_icone else 0.0))


def _abreviar(texto, limite):
    """Encurta o NOME; quem chama concatena o sufixo depois, para que a
    contagem nunca seja o pedaco cortado."""
    if limite >= len(texto):
        return texto
    return texto[:max(1, limite)]


# ===================================================== GAVETA ESQUERDA
# Area VIEW_3D independente: nao mover a regiao N do usuario. O desenho
# POST_PIXEL e os eventos abaixo nao passam pelo handler de UILayout;
# portanto a barra recebe PRESS/MOUSEMOVE/RELEASE de verdade.
_handler_gaveta = [None]
_fotos_gaveta = {}
_imagens_gaveta = set()
_edicao_gaveta = [None]
# Realces animados: chave -> [valor atual, alvo, instante]. A chave
# e' (ponteiro da area, nome do widget), porque agora a alca e os
# campos de medida usam o MESMO glow.
_realces = {}
# Deslize do carrossel: chave da categoria -> [indice atual, alvo,
# instante]. O indice inteiro continua sendo a verdade (clique, arraste
# e testes leem ele da screen); isto aqui e' so' a posicao INTERMEDIARIA
# por onde a fila passa, para a troca virar movimento e nao um corte.
_deslizes = {}
DURACAO_DESLIZE = 0.09
_CHAVE_GAVETA = "cabinet_gaveta_area"
_CHAVE_PENDENTE = "cabinet_gaveta_pendente"
_CHAVE_ROLAGEM = "cabinet_gaveta_rolagem"
# Biblioteca: painel FIXO embaixo, com rolagem propria. A divisoria e'
# guardada como FRACAO da altura util, para acompanhar o resize da area.
_CHAVE_ROLAGEM_BIB = "cabinet_gaveta_rolagem_bib"
_CHAVE_DIVISA = "cabinet_gaveta_divisa"
DIVISA_PADRAO = 0.5            # pedido do usuario: metade para baixo
ALTURA_MIN_PAINEL_GAVETA = 90  # nenhum dos dois paineis some ao arrastar
FOLGA_DIVISA_GAVETA = 5        # meia altura da faixa que pega a divisoria
_cursor_divisa = [False]       # o cursor de redimensionar esta' posto
# Engrenagem aberta: a gaveta mostra as opcoes no lugar do conteudo da aba
_CHAVE_OPCOES = "cabinet_gaveta_opcoes"
# Lista suspensa aberta (nome da opcao) e seletor de cor aberto
_CHAVE_SUSPENSO = "cabinet_gaveta_suspenso"
_CHAVE_COR = "cabinet_gaveta_cor"
ALVO_PREFERENCIAS = '@preferencias'   # alvo da 'escolha' que grava opcao
_LARGURA_MAX_GAVETA = 564
# Largura LOGICA a partir da qual Largura, Altura e Profundidade (e a
# Espessura) ficam na mesma linha. A gaveta abre exatamente nela: e' o
# menor tamanho com as medidas lado a lado (pedido do usuario).
LARGURA_MEDIDAS_EM_LINHA = 480
_LARGURA_PADRAO_GAVETA = LARGURA_MEDIDAS_EM_LINHA


def _largura_inicial_gaveta(context):
    """Px de area com que a gaveta abre. A escala da UI entra igual ao
    corte de `_colunas_medidas`; +2 cobre o arredondamento do split,
    que senao abriria 1 px abaixo do corte, com as medidas em 2 linhas."""
    escala = max(1.0, context.preferences.system.ui_scale)
    return math.ceil(_LARGURA_PADRAO_GAVETA * escala) + 2


def _area_gaveta(screen):
    ptr = int(screen.get(_CHAVE_GAVETA, 0)) if screen else 0
    return next((a for a in screen.areas
                 if a.type == 'VIEW_3D' and a.as_pointer() == ptr), None)


def _eh_area_gaveta(context):
    return (context.area is not None and context.screen is not None
            and context.area == _area_gaveta(context.screen))


def _limitar_largura_gaveta():
    # Area.width e' somente leitura. Corrigir a divisoria apos o resize,
    # nunca disputar eventos com um operador modal do usuario.
    # Com a UI ampliada a largura inicial passa de 564 px; o teto nunca
    # fica abaixo dela, senao as medidas voltariam a quebrar a linha.
    teto = max(_LARGURA_MAX_GAVETA, _largura_inicial_gaveta(bpy.context))
    for janela in bpy.context.window_manager.windows:
        if getattr(janela, 'modal_operators', ()):
            continue
        painel = _area_gaveta(janela.screen)
        if painel is None:
            continue
        painel.spaces.active.show_gizmo = True
        if painel.width <= teto:
            continue
        direita = painel.x + painel.width
        vizinho = next((a for a in janela.screen.areas
                        if a.type == 'VIEW_3D' and 0 <= a.x - direita <= 5
                        and a.y == painel.y and a.height == painel.height), None)
        if vizinho is None:
            continue
        regiao = next((r for r in painel.regions if r.type == 'WINDOW'), None)
        with bpy.context.temp_override(window=janela, area=painel, region=regiao):
            if bpy.ops.screen.area_move.poll():
                bpy.ops.screen.area_move(x=direita,
                    y=painel.y + painel.height // 2,
                    delta=teto - painel.width)
    return 0.3


def _configurar_gavetas():
    # A geometria da area nova so' fica disponivel no tique seguinte ao split.
    pendente = False
    for janela in bpy.context.window_manager.windows:
        screen = janela.screen
        ptr = int(screen.get(_CHAVE_PENDENTE, 0))
        if not ptr:
            continue
        principal = next((a for a in screen.areas
                          if a.as_pointer() == ptr), None)
        if principal is None:
            screen[_CHAVE_PENDENTE] = 0
            continue
        candidatas = [a for a in screen.areas
                      if a.type == 'VIEW_3D' and a != principal
                      and a.y == principal.y and a.height == principal.height
                      and a.x < principal.x]
        if not candidatas:
            pendente = True
            continue
        painel = max(candidatas, key=lambda a: a.x)
        espaco = painel.spaces.active
        espaco.show_region_ui = False
        espaco.show_region_toolbar = False
        espaco.show_region_header = False
        espaco.show_region_tool_header = False
        espaco.show_region_hud = False
        espaco.show_gizmo = True
        espaco.show_gizmo_context = False
        espaco.show_gizmo_tool = False
        espaco.show_gizmo_navigate = False
        espaco.overlay.show_overlays = False
        screen[_CHAVE_GAVETA] = str(painel.as_pointer())
        screen[_CHAVE_PENDENTE] = 0
        painel.tag_redraw()
        principal.tag_redraw()
    return 0.05 if pendente else None


def _reconectar_gavetas():
    # Ponteiros de areas nao sobrevivem a recarga de um arquivo .blend.
    for janela in bpy.context.window_manager.windows:
        screen = janela.screen
        if not screen.get(_CHAVE_GAVETA) or _area_gaveta(screen):
            continue
        candidatos = [a for a in screen.areas
                      if a.type == 'VIEW_3D' and a.width < 600
                      and not a.spaces.active.show_region_header
                      and not a.spaces.active.show_region_toolbar
                      and not a.spaces.active.overlay.show_overlays]
        if len(candidatos) == 1:
            screen[_CHAVE_GAVETA] = str(candidatos[0].as_pointer())
            candidatos[0].tag_redraw()
        else:
            screen[_CHAVE_GAVETA] = 0
    return None


def _fechar_gavetas_registradas():
    for janela in bpy.context.window_manager.windows:
        screen = janela.screen
        painel = _area_gaveta(screen)
        screen[_CHAVE_GAVETA] = 0
        screen[_CHAVE_PENDENTE] = 0
        if painel is None:
            continue
        try:
            with bpy.context.temp_override(window=janela, screen=screen,
                                           area=painel):
                bpy.ops.screen.area_close()
        except Exception as e:
            print("[Cabinet Creator] fechar gaveta ao desativar:", e)


def _retangulo_gaveta(x, y, largura, altura, cor):
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {'pos': (
        (x, y), (x + largura, y), (x + largura, y + altura),
        (x, y), (x + largura, y + altura), (x, y + altura))})
    shader.bind()
    shader.uniform_float('color', cor)
    batch.draw(shader)


def _retangulo_arredondado_gaveta(x, y, largura, altura, raio, cor,
                                 esquerda_reta=False):
    raio = min(raio, largura / 2.0, altura / 2.0)
    pontos = []
    cantos = (
            (x + largura - raio, y + raio, -90),
            (x + largura - raio, y + altura - raio, 0),
            (x + raio, y + altura - raio, 90),
            (x + raio, y + raio, 180))
    for i, (cx, cy, inicio) in enumerate(cantos):
        if esquerda_reta and i >= 2:
            pontos.append((x, y + altura if i == 2 else y))
            continue
        for passo in range(5):
            angulo = math.radians(inicio + passo * 90 / 4)
            pontos.append((cx + raio * math.cos(angulo),
                           cy + raio * math.sin(angulo)))
    centro = (x + largura / 2.0, y + altura / 2.0)
    vertices = []
    for i, ponto in enumerate(pontos):
        vertices.extend((centro, ponto, pontos[(i + 1) % len(pontos)]))
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {'pos': vertices})
    shader.bind()
    shader.uniform_float('color', cor)
    batch.draw(shader)


def _texto_gaveta(x, y, texto, tamanho=12, cor=None):
    if cor is None:
        cor = (*bpy.context.preferences.themes[0].user_interface.wcol_regular.text, 1)
    blf.size(0, tamanho)
    blf.color(0, *cor)
    blf.position(0, x, y, 0)
    blf.draw(0, texto)


def _texto_cabivel_gaveta(x, y, texto, largura, tamanho=12, cor=None):
    for fonte in range(tamanho, 8, -1):
        blf.size(0, fonte)
        if blf.dimensions(0, texto)[0] <= largura:
            _texto_gaveta(x, y, texto, fonte, cor)
            return
    blf.size(0, 9)
    while texto and blf.dimensions(0, texto + '...')[0] > largura:
        texto = texto[:-1]
    _texto_gaveta(x, y, texto + '...' if texto else '', 9, cor)


def _cores_gaveta():
    tema = bpy.context.preferences.themes[0]
    return tema.user_interface.wcol_regular, (*tema.properties.space.back, 1)


def _botao_gaveta(x, y, w, h, ativo=False, secao=False, cor=None):
    cores, painel = _cores_gaveta()
    borda = (*cores.outline[:3], 1)
    fundo = tuple(cores.inner_sel if ativo else cores.inner) if not secao else painel
    if cor is not None:
        fundo = cor
    _retangulo_arredondado_gaveta(x, y, w, h, 4, borda)
    if w > 2 and h > 2:
        _retangulo_arredondado_gaveta(
            x + 1, y + 1, w - 2, h - 2, 3, fundo)


def _grupos_de_porta(obj):
    """Grupos de porta ligados ao que esta' selecionado.

    No cenario 1 (objeto generico) a porta nao tem vinculo com nada:
    so' aparece na SELECAO. Sem olhar para ela, o preview ficava sem
    porta nenhuma logo depois de criar.
    """
    grupo = _grupo_portas(obj)
    if grupo is not None:
        return [grupo]
    if obj is not None and MARCA_CONJUNTO in obj:
        vinculados = _portas_do_conjunto(obj)
        if vinculados:
            return vinculados
    modulo = _modulo_da_chapa(obj)
    if modulo is not None:
        vinculados = _portas_do_conjunto(modulo)
        if vinculados:
            return vinculados
    achados = []
    for selecionado in getattr(bpy.context, 'selected_objects', ()):
        alvo = _grupo_portas(selecionado)
        if alvo is not None and alvo not in achados:
            achados.append(alvo)
    return achados


def _espessura_visivel(dimensoes):
    """Engrossa a aresta fina o bastante para ela aparecer.

    Uma chapa de 18 mm ao lado de 2000 mm da menos de 1% do desenho --
    sai sub-pixel e o preview parece uma folha de papel. O desenho e'
    um esquema, entao a espessura ganha um minimo; as outras duas
    medidas ficam intactas.
    """
    largura, espessura, profundidade = dimensoes
    minimo = max(largura, profundidade) * MINIMO_ESPESSURA_WIREFRAME
    return (largura, max(espessura, minimo), profundidade)


def _folhas_para_wireframe(obj, modo):
    """Quantas folhas o preview deve mostrar.

    No modo INDIVIDUAL o desenho e' de UMA chapa; porta ali nao existe
    e as folhas apareciam dentro da peca, que e' o que quebrava a
    visualizacao.
    """
    if modo == 'INDIVIDUAL':
        return 0
    return sum(len(_folhas_portas(g)) for g in _grupos_de_porta(obj))


def _frente_da_porta(obj):
    """Em que face do modulo a porta foi montada ('' se nao ha' porta)."""
    for grupo in _grupos_de_porta(obj):
        frente = grupo.get('porta_frente')
        folhas = _folhas_portas(grupo)
        modulo = _modulo_da_chapa(folhas[0]) if folhas else None
        if modulo is not None and grupo.get('porta_parametros'):
            # Arquivos antigos podem guardar a normal invertida. A face
            # do desenho segue a posicao real, sem alterar essas portas.
            base = modulo.matrix_world.to_quaternion().to_matrix().transposed()
            normal = base @ grupo.matrix_world.to_3x3().col[2]
            eixo = max(range(3), key=lambda i: abs(normal[i]))
            posicao = _local_no_modulo(modulo, grupo.matrix_world.translation)
            limites = _limites_locais_modulo(modulo)
            centro = (sum(p[eixo] for p in limites) / 2 if limites else 0)
            return ('NEG_' if posicao[eixo] < centro else 'POS_') + 'XYZ'[eixo]
        if frente:
            return frente
    return ''


def _porta_para_wireframe(obj):
    """(largura, altura, espessura, folhas) da porta, ou None.

    Na aba Portas o desenho mostra SO' a porta, entao as medidas sao as
    do vao e a espessura das folhas -- nao as do modulo.
    """
    for grupo in _grupos_de_porta(obj):
        folhas = _folhas_portas(grupo)
        if not folhas:
            continue
        try:
            largura = float(grupo['porta_vao_largura_mm'])
            altura = float(grupo['porta_vao_altura_mm'])
        except (KeyError, TypeError, ValueError):
            continue
        espessura = max(1.0, float(folhas[0].chapa_espessura_mm))
        return largura, altura, espessura, len(folhas)
    return None


def _geometria_wireframe(obj, modo):
    """Medidas, vertices e arestas reais no referencial frontal do preview.

    Contar folhas perde fileiras, alturas parciais e planos de correr.
    Ler a malha preserva tudo isso, inclusive edicoes da geometria.
    """
    if modo == 'INDIVIDUAL' or obj is None:
        return None
    grupos = [g for g in _grupos_de_porta(obj) if g.get('porta_parametros')]
    folhas = [f for g in grupos for f in _folhas_portas(g)]
    modulo = obj if MARCA_CONJUNTO in obj else _modulo_da_chapa(obj)
    grupo = _grupo_portas(obj)
    if modulo is None and grupo is not None:
        modulo = bpy.data.objects.get(grupo.get(CHAVE_MODULO_PORTA, ''))
    corpo = _chapas_do_conjunto(modulo) if modulo is not None else []
    alvos = folhas if modo == 'PORTA' else corpo + folhas
    if not alvos:
        return None
    referencia = (modulo.matrix_world.to_quaternion().to_matrix()
                  if modulo is not None else Matrix.Identity(3))
    frente = _frente_da_porta(obj) or 'NEG_Y'
    if frente.endswith('Z'):
        # Porta deitada: o modulo continua de pe' no desenho, visto de
        # frente, com a tampa em cima (ou embaixo).
        frente = 'NEG_Y'
    normal = referencia @ Vector(NORMAIS_FRENTE[frente])
    cima = referencia @ Vector((0, 0, 1))
    base = Matrix((cima.cross(normal).normalized(), -normal, cima))
    vertices, arestas, caixa = [], [], []
    for alvo in alvos:
        pontos = [base @ (alvo.matrix_world @ v.co) * 1000
                  for v in alvo.data.vertices]
        inicio = len(vertices)
        arestas.extend((inicio + a, inicio + b) for a, b in
                       (e.vertices for e in alvo.data.edges))
        vertices.extend(pontos)
        if modo == 'PORTA' or alvo in corpo:
            caixa.extend(pontos)
    if not vertices or not arestas:
        return None
    caixa = caixa or vertices
    lo = Vector(tuple(min(v[i] for v in caixa) for i in range(3)))
    hi = Vector(tuple(max(v[i] for v in caixa) for i in range(3)))
    dimensoes = (hi.x - lo.x, hi.z - lo.z, hi.y - lo.y)
    if min(dimensoes) <= 0:
        return None
    return dimensoes, [tuple(v - lo) for v in vertices], arestas


def _modo_chapa(context, obj):
    """Individual ou Grupo sai da SELECAO, nao de um botao.

    Um objeto so' selecionado = Individual (a chapa isolada pelo duplo
    clique, ou uma chapa solta). Mais de um = Grupo (o modulo inteiro
    acende com o clique simples). Os botoes da gaveta so' mostram.
    """
    selecionados = list(getattr(context, 'selected_objects', ()) or ())
    return 'INDIVIDUAL' if len(selecionados) <= 1 else 'GRUPO'


def _medidas_da_porta(obj, grupo):
    """L/A so' leitura e E editavel, no nivel porta ou folha.

    L/A de uma folha nao se editam: o proximo recalculo das folhas
    (modulo redimensionado, folga mudada) apagaria a mudanca. A
    espessura e' da porta inteira -- folhas de uma porta sao iguais.
    """
    folhas = _folhas_portas(grupo)
    if MARCA_FOLHA in obj:
        largura, altura = obj.chapa_largura_mm, obj.chapa_comprimento_mm
    else:
        inversa = grupo.matrix_world.inverted()
        pontos = [inversa @ (f.matrix_world @ v.co) * 1000.0
                  for f in folhas for v in f.data.vertices]
        largura = (max(p.x for p in pontos) - min(p.x for p in pontos)
                   if pontos else 0.0)
        altura = (max(p.y for p in pontos) - min(p.y for p in pontos)
                  if pontos else 0.0)
    espessura = float(grupo['porta_parametros'].get(
        'espessura_mm', folhas[0].chapa_espessura_mm if folhas
        else ESPESSURA_PADRAO_PORTA))
    return [('Largura', largura, ''), ('Altura', altura, ''),
            ('Espessura', espessura, 'ui_porta_espessura')]


def _medidas_gaveta(context):
    obj = context.object
    if obj is not None and MARCA_CONJUNTO in obj:
        campos = [('Largura', obj.conj_largura_mm, 'ui_conj_largura'),
                  ('Altura', obj.conj_altura_mm, 'ui_conj_altura'),
                  ('Profundidade', obj.conj_profundidade_mm,
                   'ui_conj_profundidade'),
                  ('Espessura', obj.conj_espessura_mm,
                   'ui_conj_espessura')]
        return 'GRUPO', campos, 'objeto'
    grupo = _grupo_portas(obj)
    if grupo is not None and grupo.get('porta_parametros'):
        return 'PORTA', _medidas_da_porta(obj, grupo), 'porta'
    if _eh_puxador_parametrico(obj):
        return 'PUXADOR', _medidas_puxador_parametrico(obj), 'puxador'
    if obj is not None and MARCA_PUXADOR in obj:
        # (nome, valor, prop) como os outros; a trava vai no 4o campo
        return 'PUXADOR', [(n, v, p, t) for n, v, p, t, _k
                           in _medidas_do_puxador(obj)], 'puxador'
    if obj is not None and MARCA_CHAPA in obj:
        if _modo_chapa(context, obj) == 'GRUPO':
            s = context.scene
            campos = [('Largura', s.grupo_largura_mm, 'ui_grupo_largura'),
                      ('Altura', s.grupo_altura_mm, 'ui_grupo_altura'),
                      ('Profundidade', s.grupo_profundidade_mm,
                       'ui_grupo_profundidade'),
                      ('Espessura', s.grupo_espessura_mm,
                       'ui_grupo_espessura')]
            return 'GRUPO', campos, 'cena'
        campos = [('Largura', obj.chapa_largura_mm, 'ui_chapa_largura'),
                  ('Altura', obj.chapa_comprimento_mm,
                   'ui_chapa_comprimento'),
                  ('Espessura', obj.chapa_espessura_mm,
                   'ui_chapa_espessura')]
        return 'INDIVIDUAL', campos, 'objeto'
    medido = medir_selecao(context)
    if medido:
        editavel = obj is not None and medido[3] == 1
        if editavel:
            valores = (obj.dimensions.x * 1000.0,
                       obj.dimensions.z * 1000.0,
                       obj.dimensions.y * 1000.0)
        else:
            valores = medido[:3]
        return 'LIVRE', [
            ('Largura', valores[0], 'dimensions_0' if editavel else ''),
            ('Altura', valores[1], 'dimensions_2' if editavel else ''),
            ('Profundidade', valores[2], 'dimensions_1' if editavel else '')
        ], 'livre' if editavel else ''
    return 'LIVRE', [], ''


def _linha_cascata_gaveta(itens, x, y, largura, valores, nivel, selecionado,
                         indice, pai=None):
    if not valores:
        return y
    chave = 'cabinet_carrossel_%d_%s' % (nivel, str(pai))
    colunas = min(len(valores), max(1, int((largura - 48) // 110)))
    limite = len(valores) - colunas
    inicio = max(0, min(limite, int(bpy.context.screen.get(chave, 0))))
    bw = (largura - 48 - 4 * (colunas - 1)) / colunas
    itens.append((x, y, 20, 25, '', ('rolar_nivel', chave, -1, limite)))
    itens.append((x + largura - 20, y, 20, 25, '',
                  ('rolar_nivel', chave, 1, limite)))

    # As posicoes saem daqui, nao do desenho: assim o retangulo de
    # clique acompanha a peca enquanto ela anda. Desenhar por cima de
    # um hit-test parado faria o usuario errar o alvo em movimento.
    deslize = _deslizar(chave, inicio)
    primeiro = int(math.floor(deslize))
    sobra = deslize - primeiro
    # Em movimento entra UMA peca a mais, a que esta' surgindo na
    # borda; o recorte do desenho corta o que passa do trilho.
    extra = 1 if sobra else 0
    ordenados = sorted(valores, key=str.casefold)
    for posicao in range(primeiro, primeiro + colunas + extra):
        if not 0 <= posicao < len(ordenados):
            continue
        valor = ordenados[posicao]
        if nivel == 1:
            conta = _conta(indice, valor)
        elif nivel == 2:
            conta = _conta(indice, pai, valor)
        else:
            conta = _conta(indice, pai[0], pai[1], valor)
        itens.append((x + 24 + (posicao - primeiro - sobra) * (bw + 4), y,
                      bw, 25, '%s (%d)' % (_abreviar(valor, 13), conta),
                      ('navegar', nivel, valor, chave, limite, selecionado == valor)))
    return y - 39


def _linha_escolha_gaveta(itens, x, y, w, rotulo, prop, opcoes, atual,
                          ativo=True, alvo='', por_linha=None):
    """Rotulo mais uma fila de segmentos: a alternativa ao dropdown.

    O bpy nao desenha menu suspenso aqui, e popup e' justamente o que
    esta' saindo da frente do usuario. Segmento tem a vantagem de
    mostrar TODAS as opcoes sem clique nenhum. `por_linha=1` empilha as
    opcoes em coluna (Abertura | Dobradica lado a lado na aba Portas).
    """
    if rotulo:
        # 23 deixava o primeiro segmento 2 px por cima do rotulo
        itens.append((x, y, w, 20, rotulo, None))
        y -= 26
    # 52 px e' o menor segmento onde um rotulo curto ainda cabe
    if por_linha is None:
        por_linha = max(1, min(len(opcoes), int(w // 52)))
    for inicio in range(0, len(opcoes), por_linha):
        fatia = opcoes[inicio:inicio + por_linha]
        bw = (w - 4 * (len(fatia) - 1)) / len(fatia)
        for i, (valor, texto) in enumerate(fatia):
            # `alvo` = nome do grupo de portas quando a fila edita uma
            # porta colocada; vazio = parametro da cena (porta nova).
            itens.append((x + i * (bw + 4), y, bw, 25, texto,
                          ('escolha', prop, valor, valor == atual, ativo,
                           alvo)))
        y -= 29
    return y


def _colunas_medidas(context, largura, n):
    """Colunas dos campos de medida pela largura LOGICA da gaveta:
    todos numa linha (>= 480), dois (>= 240) ou um. Vale para o bloco
    fixo e para as medidas da porta, que assim ficam alinhados."""
    logica = largura / max(1.0, context.preferences.system.ui_scale)
    return max(1, n if logica >= LARGURA_MEDIDAS_EM_LINHA
               else 2 if logica >= 240 else 1)


def _bloco_medidas_gaveta(context, itens, x, y, w, largura, metade,
                          modos=True):
    """Medidas, wireframe e rodape -- o bloco fixo das TRES abas.

    Saber o que esta' selecionado e quanto mede vale tanto montando o
    modulo quanto configurando a porta dele, entao este bloco nao
    pertence a uma aba so'. Nao ha' botao de sincronizar: o handler
    rele as medidas sozinho (`_sincronizar_medidas_ativas`).
    """
    obj = context.object
    y += 23
    modo, campos, dono = _medidas_gaveta(context)
    # Na aba Portas edita-se o conjunto das folhas, nunca uma peca
    # isolada: alternar Individual/Grupo ali nao significa nada.
    if (modos and obj is not None and modo != 'PORTA'
            and (MARCA_CHAPA in obj or MARCA_CONJUNTO in obj)):
        for i, nome in enumerate(('Individual', 'Grupo')):
            itens.append((x + i * (metade + 6), y, metade, 25, nome,
                          ('modo', nome.upper(), modo == nome.upper())))
        y -= 33
    if campos:
        # Campos tem 37 px de altura; afastar das abas de modo acima.
        y -= 8
        colunas = _colunas_medidas(context, largura, len(campos))
        largura_campo = (w - 6 * (colunas - 1)) / colunas
        # Puxador: cadeado no fim de cada linha. Travado, a medida nao
        # muda quando a porta muda; destravado, estica junto.
        for i, campo in enumerate(campos):
            nome, valor, prop = campo[:3]
            # so' o importado tem trava (4o campo); o parametrico nao
            cadeado = 22 if modo == 'PUXADOR' and len(campo) > 3 else 0
            linha, coluna = divmod(i, colunas)
            cx = x + coluna * (largura_campo + 6)
            itens.append((cx, y - linha * 43, largura_campo - cadeado, 37,
                          '%s: %s' % (nome, _texto_medida(valor)),
                          ('medida', dono, prop, nome, valor)))
            if cadeado:
                itens.append((cx + largura_campo - cadeado + 2,
                              y - linha * 43, cadeado - 2, 37, '',
                              ('cadeado', obj.name, int(prop[-1]),
                               bool(campo[3]))))
        y -= (math.ceil(len(campos) / colunas) - 1) * 43 + 42
    # Sem rodape: nome do item, "Chapa" e "Auto-regenerar" sairam a
    # pedido do usuario (a chapa sempre guarda o que foi modelado).
    return y


def _botoes_gaveta(itens, x, y, w, botoes):
    """Botoes de texto em duas colunas quando cabem; devolve o y seguinte."""
    colunas = 2 if w >= 240 else 1
    bw = (w - 6 * (colunas - 1)) / colunas
    for i, (rotulo, op) in enumerate(botoes):
        linha, coluna = divmod(i, colunas)
        itens.append((x + coluna * (bw + 6), y - linha * 34, bw, 28, rotulo,
                      ('operador', op)))
    return y - math.ceil(len(botoes) / colunas) * 34


def _aba_puxadores_gaveta(context, itens, x, y, w, s):
    """Puxador pronto: escolhe o modelo aqui e usa "Criar Puxador", no
    TOPO da aba, laranja como o "Criar Portas" (clica na borda, escolhe o
    ponto). Puxador de
    fora: converter, ligar (corrente) e travar. Como na aba Portas, o
    nome do item nao aparece (pedido do usuario).

    As medidas (e os cadeados do importado) ficam no bloco fixo de cima;
    aqui fica o caminho para chegar la'.
    """
    itens.append((x, y + 31, w, 1, '', ('separador',)))
    y = _linha_escolha_gaveta(
        itens, x, y, w, 'Modelo do puxador', 'cabinet_puxador_modelo',
        tuple((k, v[0]) for k, v in MODELOS_PUXADOR.items()),
        s.cabinet_puxador_modelo)
    y -= 4
    obj = context.object
    if _eh_puxador_parametrico(obj):
        texto = '%s na borda %s' % (MODELOS_PUXADOR[obj['puxador_tipo']][0],
                                    obj.get('puxador_borda', '?'))
    elif obj is not None and MARCA_PUXADOR in obj:
        ligado = obj.parent is not None and MARCA_CHAPA in obj.parent
        texto = 'Ligado a uma porta' if ligado else 'Solto: ligue a uma porta'
    else:
        texto = 'Puxador de fora: selecione o objeto'
    itens.append((x, y, w, 26, texto, None))
    y -= 34
    y = _botoes_gaveta(itens, x, y, w, (
        ('Converter em puxador', 'object.cabinet_converter_puxador'),))
    itens.append((x, y, w, 22, 'Puxador + porta: corrente acima', None))
    return itens


def _valores_portas(s, grupo=None):
    """O que a aba MOSTRA: os parametros da porta selecionada, ou os da
    cena quando nao ha' porta (a proxima a ser criada).

    Ler direto do grupo, em vez de copiar para a cena, e' o que impede
    a aba de exibir os valores da ULTIMA porta como se fossem desta.
    """
    valores = _parametros_portas_da_cena(s, numerico=True)
    guardados = (grupo.get('porta_parametros') or {}) if grupo else {}
    for nome, valor in guardados.items():
        if nome not in valores:
            continue
        if nome in {'abertura', 'dobradica', 'dobradica_lado'}:
            valores[nome] = str(valor)
        elif nome in {'folhas', 'dobradicas_qtd', 'pistoes_qtd'}:
            valores[nome] = int(valor)
        else:
            valores[nome] = float(valor)
    return valores


def _aba_portas_gaveta(context, itens, x, y, w, s):
    """Tudo o que morava no popup de Portas Parametricas.

    Sem porta selecionada, a aba prepara a PROXIMA porta (valores da
    cena). Com porta ou folha selecionada (duplo clique), ela mostra e
    edita AQUELA porta, na hora -- e criar fica desligado.
    """
    # Ordem: medidas da porta logo abaixo do bloco de medidas (SO' com
    # porta selecionada), separador, escolhas. "Criar Portas" fica no
    # topo da aba (`_widgets_aba_gaveta`).
    # No vao de 9 px que o rodape deixa, nao dentro do item seguinte.
    itens.append((x, y + 31, w, 1, '', ('separador',)))
    grupo = _grupo_portas(context.object)
    if grupo is not None and not grupo.get('porta_parametros'):
        grupo = None
    alvo = grupo.name if grupo is not None else ''
    valores = _valores_portas(s, grupo)
    # Sem cabecalho "Porta N de M - vao L x A": nada de nome nem medida
    # repetida na aba (pedido do usuario); o bloco de cima ja' mede.
    topo = y + 26               # topo da 1a linha, como o de um rotulo

    # Sem espessuras aqui: a da porta e' o E do bloco de medidas e a da
    # lateral e' a do modulo.
    correr = valores['abertura'] == 'CORRER'
    medidas = []
    if correr:
        medidas.append(('ui_porta_recuo_correr', 'porta_recuo_correr_mm',
                        'Recuo para trilhos'))
        if valores['folhas'] > 1:
            medidas.append(('ui_porta_sobreposicao', 'porta_sobreposicao_mm',
                            'Sobreposicao'))
            medidas.append(('ui_porta_entre_planos', 'porta_entre_planos_mm',
                            'Entre planos'))
    else:
        if valores['dobradica'] in {'RETA', 'CURVA'}:
            medidas.append(('ui_porta_afastamento', 'porta_afastamento_mm',
                            'Afastamento'))
        elif valores['dobradica'] == 'SUPER_CURVA':
            medidas.append(('ui_porta_recuo_embutida',
                            'porta_recuo_embutida_mm', 'Recuo da embutida'))
        if valores['folhas'] > 1:
            medidas.append(('ui_porta_entre_folhas', 'porta_entre_folhas_mm',
                            'Entre folhas'))
    medidas.append(('ui_porta_folga', 'porta_folga_mm', 'Folga no perimetro'))
    if grupo is None:
        # Folgas, afastamentos e vaos nao se definem ANTES de desenhar a
        # porta (backlog do usuario, Epico 2.1/2.4): a criacao usa os
        # valores da cena e os campos aparecem com a porta selecionada.
        medidas = []

    if medidas:
        # Mesma regra de colunas do bloco de cima: as duas linhas de
        # campos ficam alinhadas (layout do usuario: 3 + 3 na larga).
        colunas = _colunas_medidas(context, w + 24, len(medidas))
        largura_campo = (w - 6 * (colunas - 1)) / colunas
        linhas = math.ceil(len(medidas) / colunas)
        for i, (prop_ui, prop_mm, rotulo) in enumerate(medidas):
            linha, coluna = divmod(i, colunas)
            valor = valores[prop_mm[len('porta_'):]]
            itens.append((x + coluna * (largura_campo + 6),
                          topo - 37 - linha * 43, largura_campo, 37,
                          '%s: %s' % (rotulo, _texto_medida(valor)),
                          ('medida', 'porta', prop_ui, rotulo, valor)))
        fundo_campos = topo - 37 - (linhas - 1) * 43
        itens.append((x, fundo_campos - 10, w, 1, '', ('separador',)))
        y = fundo_campos - 10 - 9 - 20      # rotulo da 1a fila de escolhas

    # A MESMA ordem das perguntas do wizard (pedido do usuario), e cada
    # categoria so' APARECE depois de respondida no wizard; porta pronta
    # selecionada mostra todas. Durante o wizard a fila so' mostra (quem
    # decide e' a caixa da viewport); a dobradica nao aparece: e'
    # automatica (sai dos 4 cliques).
    assistente = _assistente_porta[0] if grupo is None else None
    escolhas = (assistente or {}).get('escolhas', {})
    editavel = grupo is not None
    filas = []
    if editavel or 'folhas' in escolhas:
        abertura = valores['abertura'] if editavel else escolhas.get('abertura')
        # no wizard, antes da abertura, a caixa oferecia 1 | 2
        limite = LIMITES_FOLHAS.get(abertura, 1 if editavel else 2)
        filas.append(('Folhas', 'porta_folhas',
                      tuple((n, str(n)) for n in range(1, limite + 1)),
                      valores['folhas'] if editavel else escolhas['folhas']))
    if editavel or 'abertura' in escolhas:
        (prop, rotulo, opcoes), = ESCOLHAS_PORTAS
        filas.append((rotulo, prop, opcoes, valores['abertura'] if editavel
                      else escolhas['abertura']))
    for i, (rotulo, prop, opcoes, atual) in enumerate(filas):
        if i:
            itens.append((x, y + 30, w, 1, '', ('separador',)))
        y = _linha_escolha_gaveta(itens, x, y, w, rotulo, prop, opcoes, atual,
                                  ativo=editavel, alvo=alvo) - 10
    if filas:
        y += 6

    # Medida da folha nao se repete aqui; so' o ERRO aparece, quando a
    # configuracao nao cabe no vao da porta selecionada.
    if grupo is not None:
        try:
            _calcular_folhas_portas(grupo['porta_vao_largura_mm'],
                                    grupo['porta_vao_altura_mm'], valores)
        except (ValueError, KeyError, TypeError) as erro:
            itens.append((x, y, w, 22, str(erro), None))
            y -= 26

    # Porta selecionada: reposicionar (diagonal no vao novo) e frente.
    # Sem porta, nada alem do "Criar Portas" (Converter em porta/dupla
    # sairam da aba a pedido do usuario; seguem no F3).
    if grupo is not None:
        y = _botoes_gaveta(itens, x, y, w, (
            ('Reposicionar no vao', 'object.cabinet_apanhar_vao'),
            ('Definir como frente', 'object.cabinet_definir_frente')))
    return itens


# botoes LARANJA do topo das abas: Criar Portas e Criar Puxador
BOTOES_CRIAR = ('portas', 'criar_puxador')
COR_CRIAR_PORTAS = (0.85, 0.38, 0.06, 1.0)        # laranja
COR_CRIAR_PORTAS_ATIVO = (1.0, 0.5, 0.12, 1.0)     # marcando o vao


def _botao_criar_portas(context):
    """(rotulo, acao) do "Criar Portas", no topo da aba Portas.

    Com porta selecionada o botao fica APAGADO: as mudancas ja' se
    aplicam na hora, e outra porta se cria voltando ao modulo. O rotulo
    carrega o estado (marcando o vao, ou o que impede de criar).
    """
    s = context.scene
    grupo = _grupo_portas(context.object)
    if grupo is not None and not grupo.get('porta_parametros'):
        grupo = None
    motivo = '' if grupo is not None else _motivo_portas(s)
    if _apanhando_vao[0]:
        rotulo = 'Marcando o vao... (Esc cancela)'
    elif motivo:
        rotulo = motivo
    else:
        rotulo = 'Criar Portas'
    return rotulo, ('portas', bool(grupo), _apanhando_vao[0], motivo,
                    grupo is not None)


def _botao_criar_puxador():
    """(rotulo, acao) do "Criar Puxador", no topo da aba Puxadores: a
    acao tem o MESMO formato da do "Criar Portas" (aceso = posicionando)."""
    posicionando = _posicionador_puxador[0] is not None
    rotulo = ('Posicionando o puxador... (Esc cancela)' if posicionando
              else 'Criar Puxador')
    return rotulo, ('criar_puxador', False, posicionando, '', False)


def _divisa_gaveta(context, altura):
    """Altura (y da regiao) da divisoria entre a aba e a biblioteca.

    Fica entre o pe' fixo e o cabecalho, sempre deixando
    ALTURA_MIN_PAINEL_GAVETA para cada lado; numa area baixa demais
    para os dois, cai no meio.
    """
    base, topo = ALTURA_RODAPE_GAVETA, altura - 48
    try:
        fracao = float(context.screen.get(_CHAVE_DIVISA, DIVISA_PADRAO))
    except Exception:
        fracao = DIVISA_PADRAO
    y = base + (topo - base) * fracao
    menor, maior = base + ALTURA_MIN_PAINEL_GAVETA, topo - ALTURA_MIN_PAINEL_GAVETA
    if menor > maior:
        return round((base + topo) / 2)
    return round(max(menor, min(maior, y)))


def _fracao_divisa(altura, y):
    """Inverso de `_divisa_gaveta`: o y do mouse vira a fracao gravada."""
    base, topo = ALTURA_RODAPE_GAVETA, altura - 48
    return max(0.0, min(1.0, (y - base) / max(1, topo - base)))


def _paineis_gaveta(conteudo):
    """(painel da aba, divisoria ou None, biblioteca) -- o conteudo se
    divide no widget 'divisa'."""
    i = next((i for i, v in enumerate(conteudo)
              if v[5] and v[5][0] == 'divisa'), None)
    if i is None:
        return conteudo, None, []
    return conteudo[:i], conteudo[i], conteudo[i + 1:]


def _limites_rolagem_gaveta(context, largura, altura):
    """(limite do painel da aba, limite da biblioteca). Cada painel rola
    ate' o ultimo widget passar inteiro pela borda de baixo DELE."""
    conteudo = _widgets_conteudo_gaveta(context, largura, altura, 0, 0)
    cima, divisa, baixo = _paineis_gaveta(conteudo[WIDGETS_CABECALHO:])
    piso_bib = 18 + ALTURA_RODAPE_GAVETA
    piso = (divisa[1] + divisa[3] / 2 + 10) if divisa else piso_bib
    limite = max(0, int(piso - min((v[1] for v in cima), default=piso)))
    limite_bib = max(0, int(piso_bib - min((v[1] for v in baixo),
                                           default=piso_bib)))
    return limite, limite_bib


def _limite_rolagem_gaveta(context, largura, altura):
    return _limites_rolagem_gaveta(context, largura, altura)[0]


ALTURA_RODAPE_GAVETA = 40      # faixa fixa da engrenagem, no pe' da gaveta
OP_OPCOES = 'object.cabinet_opcoes_gaveta'


ABAS_GAVETA = (('Modulos', 'Mod.', 'MODULOS'), ('Portas', 'Portas', 'PORTAS'),
               ('Puxadores', 'Pux.', 'PUXADORES'))
# As correntes entre as abas (porta no modulo, puxador na folha) foram
# DESCONTINUADAS a pedido do usuario: o cabecalho e' so' as tres abas.
# Os operadores seguem existindo (F3) -- so' sairam da gaveta.
OPERADORES_CORRENTE = ()
# As abas sao os primeiros widgets da lista, sempre nesta conta
WIDGETS_CABECALHO = len(ABAS_GAVETA) + len(OPERADORES_CORRENTE)


def _no_cabecalho(acao):
    """O que pode ser clicado na faixa do cabecalho: abas e correntes."""
    return bool(acao) and (acao[0] == 'aba' or (
        acao[0] == 'operador' and acao[1] in OPERADORES_CORRENTE))


def _widgets_gaveta(context, largura, altura, _rolagem=None,
                    _rolagem_bib=None):
    """Retangulos (x,y,w,h,rotulo,acao) compartilhados por desenho e hit-test.

    Ordem: cabecalho (abas e correntes), conteudo da aba, a DIVISORIA, a
    biblioteca e, por ultimo, o RODAPE fixo -- a engrenagem e, aberto, o
    painel de opcoes que sobe a partir dela. `_partes_gaveta` separa
    cabecalho/conteudo/rodape e `_paineis_gaveta` corta o conteudo na
    divisoria. Cada painel tem a sua rolagem.
    """
    if _rolagem is None or _rolagem_bib is None:
        limite, limite_bib = _limites_rolagem_gaveta(context, largura, altura)
        if _rolagem is None:
            _rolagem = max(0, min(limite, int(
                context.screen.get(_CHAVE_ROLAGEM, 0))))
        if _rolagem_bib is None:
            _rolagem_bib = max(0, min(limite_bib, int(
                context.screen.get(_CHAVE_ROLAGEM_BIB, 0))))
    itens = _widgets_conteudo_gaveta(context, largura, altura, _rolagem,
                                     _rolagem_bib)
    x, w = 12, max(24, min(540, largura - 24))
    rodape = _rodape_gaveta(context, x, w)
    painel = _retangulo_painel_opcoes(rodape)
    if painel is not None:
        # O que fica embaixo do painel nao aparece nem recebe clique. A
        # divisoria fica (o desenho corta os paineis nela), mas coberta
        # ela nao se arrasta.
        px, py, pw, ph = painel
        def coberto(v):
            return (v[0] < px + pw and px < v[0] + v[2]
                    and v[1] < py + ph and py < v[1] + v[3])
        itens = itens[:WIDGETS_CABECALHO] + [
            (v[:5] + (('divisa', False),) if coberto(v) else v)
            if v[5] and v[5][0] == 'divisa' else v
            for v in itens[WIDGETS_CABECALHO:]
            if (v[5] and v[5][0] == 'divisa') or not coberto(v)]
    return itens + rodape


def _widgets_interativos(context):
    """Widgets que podem receber mouse, do que esta' POR CIMA para baixo:
    lista suspensa aberta, rodape/painel, cabecalho e o conteudo que nao
    esta' escondido sob as duas faixas fixas."""
    altura = context.region.height
    cabecalho, conteudo, rodape = _partes_gaveta(
        _widgets_gaveta(context, context.region.width, altura))
    rodape, flutuante = _separar_flutuante(rodape)
    if flutuante:
        # A lista e' desenhada por ULTIMO mas atende PRIMEIRO; o fundo
        # dela engole o clique nas frestas e as linhas que ela cobre
        # saem do hit-test (e do hover) ate' ela fechar.
        fx, fy, fw, fh = flutuante[0][:4]
        rodape = flutuante[1:] + flutuante[:1] + [
            v for v in rodape
            if not (v[0] < fx + fw and fx < v[0] + v[2]
                    and v[1] < fy + fh and fy < v[1] + v[3])]
    # Widget cortado pela divisoria ou pelas faixas fixas recebe mouse SO'
    # na parte visivel (retangulo recortado ao painel): a foto do preset
    # mal cabe na metade de baixo, e exigir o widget inteiro deixava o
    # clique -- e o duplo clique -- na foto sem efeito nenhum.
    cima, divisa, baixo = _paineis_gaveta(conteudo)
    meio = (divisa[1] + divisa[3] / 2) if divisa else ALTURA_RODAPE_GAVETA
    folga = FOLGA_DIVISA_GAVETA if divisa else 0
    visiveis = ([divisa] if divisa and divisa[5][1] else [])
    for lista, piso, teto in ((cima, meio + folga, altura - 48),
                              (baixo, ALTURA_RODAPE_GAVETA, meio - folga)):
        for v in lista:
            recortado = _recortar_ao_painel(v, piso, teto)
            if recortado is not None:
                visiveis.append(recortado)
    return rodape + [v for v in cabecalho if _no_cabecalho(v[5])] + visiveis


def _recortar_ao_painel(v, piso, teto):
    """O widget como recebe mouse dentro da faixa [piso, teto] do painel:
    inteiro, recortado (so' a parte visivel) ou None.

    Icone (desenhado por gizmo, que nao respeita o recorte) e trilho do
    slider (que se mede pela altura do widget) so' valem inteiros.
    """
    x, y, w, h = v[:4]
    if y >= piso and y + h <= teto:
        return v
    if _icone_acao_gaveta(v[5]) or (v[5] and v[5][0] == 'slider'):
        return None
    baixo, alto = max(y, piso), min(y + h, teto)
    if alto - baixo < 8:        # fiapo: nao da' para mirar
        return None
    return (x, baixo, w, alto - baixo) + tuple(v[4:])


def _separar_flutuante(rodape):
    """(rodape, lista suspensa) -- a lista comeca no widget 'fundo'."""
    inicio = next((i for i, v in enumerate(rodape)
                   if v[5] and v[5][0] == 'fundo'), len(rodape))
    return rodape[:inicio], rodape[inicio:]


def _partes_gaveta(widgets):
    """(cabecalho, conteudo, rodape) -- o rodape comeca na engrenagem."""
    inicio = next((i for i, v in enumerate(widgets)
                   if v[5] == ('operador', OP_OPCOES)), len(widgets))
    return (widgets[:WIDGETS_CABECALHO], widgets[WIDGETS_CABECALHO:inicio],
            widgets[inicio:])


def _retangulo_painel_opcoes(rodape):
    """Fundo do painel de opcoes (x, y, w, h), ou None se fechado."""
    # a linha fixa do pe' (engrenagem, Criar Portas) nao e' do painel
    painel = [v for v in _separar_flutuante(rodape)[0]
              if v[1] >= ALTURA_RODAPE_GAVETA]
    if not painel:
        return None
    folga = 8
    x0 = min(v[0] for v in painel) - folga
    y0 = min(v[1] for v in painel) - folga
    x1 = max(v[0] + v[2] for v in painel) + folga
    y1 = max(v[1] + v[3] for v in painel) + folga
    return x0, y0, x1 - x0, y1 - y0


def _rodape_gaveta(context, x, w):
    """Engrenagem no pe' da gaveta e, aberto, o painel que sobe dela.

    O painel e' desenhado pela propria gaveta (popup do bpy fecha quando
    o mouse sai, ver DESIGN.md). Uma linha por opcao -- rotulo a
    esquerda, controle a direita; so' empilha em gaveta estreita:
    'suspenso' abre a lista flutuante, 'faixa' arrasta ou digita
    (FAIXAS_OPCOES) e 'cor' abre o seletor ali mesmo, empurrando o
    painel para cima. Tudo grava nas preferencias do add-on.
    """
    rodape = [(x, 7, 26, 26, '', ('operador', OP_OPCOES))]
    if _conexao_manual[0] is not None:
        # escolhendo vertices: o pe' vira o "Confirmar" (o mesmo do Enter)
        rodape.append((x + 32, 7, w - 32, 26, 'Confirmar conexao (Enter)',
                       ('operador', 'object.cabinet_confirmar_conexao')))
    tela = context.screen
    if not tela.get(_CHAVE_OPCOES):
        return rodape
    suspenso = tela.get(_CHAVE_SUSPENSO, '')
    cor_aberta = tela.get(_CHAVE_COR, '')
    largo = w >= 250 * max(1.0, context.preferences.system.ui_scale)
    rot_w = (w - 6) / 2 if largo else w
    cx, cw = (x + rot_w + 6, w - rot_w - 6) if largo else (x, w)
    painel = [(x, 0, w, 20, 'Opcoes', None)]
    flutuante = []
    y = -29
    for rotulo, tipo, nome in LINHAS_OPCOES:
        if largo:
            painel.append((x, y, rot_w, 25, rotulo, None))
        else:
            painel.append((x, y, w, 20, rotulo, None))
            y -= 26
        valor = _opcao(nome)
        if tipo == 'suspenso':
            opcoes = SUSPENSOS_OPCOES[nome]
            texto = next((t for v, t in opcoes if v == valor), str(valor))
            aberto = suspenso == nome
            painel.append((cx, y, cw, 25, texto,
                           ('suspenso', nome, aberto)))
            if aberto:
                # Lista colada embaixo do campo, por cima das linhas de
                # baixo (por isso as listas ficam nas primeiras linhas)
                n = len(opcoes)
                flutuante.append((cx, y - 4 - 25 * n - 3, cw, 25 * n + 6,
                                  '', ('fundo',)))
                for i, (v, t) in enumerate(opcoes):
                    flutuante.append((cx + 3, y - 4 - 25 * (i + 1), cw - 6,
                                      25, t, ('escolha', nome, v, v == valor,
                                              True, ALVO_PREFERENCIAS)))
        elif tipo == 'faixa':
            minimo, maximo, _passo = FAIXAS_OPCOES[nome]
            painel.append((cx, y, cw, 25, _texto_faixa(valor),
                           ('faixa', nome, valor, minimo, maximo)))
        else:
            rgb = _cor_opcao(nome)
            especial = _cor_especial(nome)
            texto = {'TEMA': 'Tema', 'GIZMO': 'Gizmo'}.get(especial) or (
                '#%02X%02X%02X' % tuple(round(c * 255) for c in rgb))
            painel.append((cx, y, cw, 25, texto,
                           ('cor', nome, 'amostra', rgb, cor_aberta == nome,
                            especial)))
            if cor_aberta == nome:
                y = _seletor_cor_gaveta(painel, x, y - 29, w, nome, rgb,
                                        especial)
        y -= 29
    # Montado de cima para baixo a partir de 0; sobe para encostar logo
    # acima da engrenagem -- o painel abre de baixo para cima.
    deslocar = ALTURA_RODAPE_GAVETA + 8 - min(v[1] for v in painel)
    return rodape + [(v[0], v[1] + deslocar, *v[2:])
                     for v in painel + flutuante]


# (rotulo, controle, opcao) -- as listas suspensas vem PRIMEIRO: abrem
# para baixo, por cima das linhas seguintes, e precisam delas embaixo.
LINHAS_OPCOES = (
    ('Unidade padrao', 'suspenso', 'unidade_padrao'),
    ('Contorno do Blender', 'suspenso', 'ocultar_contorno_grupo'),
    ('Correntes', 'suspenso', 'tecla_corrente'),
    ('Espessura das linhas', 'faixa', 'hud_espessura_linha'),
    ('Tamanho dos rotulos', 'faixa', 'hud_tamanho_rotulo'),
    ('Cor das linhas', 'cor', 'hud_rgb_linha'),
    ('Cor do realce', 'cor', 'hud_rgb_realce'),
)
SUSPENSOS_OPCOES = {
    'unidade_padrao': tuple((k, v[1]) for k, v in UNIDADES_MEDIDA.items()),
    'ocultar_contorno_grupo': ((True, 'Ocultar'), (False, 'Mostrar')),
    'tecla_corrente': (('ALT', 'Segurar Alt'), ('CTRL', 'Segurar Ctrl'),
                       ('SHIFT', 'Segurar Shift'), ('SEMPRE', 'Sempre')),
}
ALTURA_QUADRO_COR = 96
# Matiz de cada opcao de cor: cinza/branco/preto nao tem matiz, e sem
# isto o quadrado voltava ao vermelho ao arrastar no eixo de saturacao.
_matiz_cor = {}


def _fechar_suspenso(context):
    if context.screen.get(_CHAVE_SUSPENSO):
        context.screen[_CHAVE_SUSPENSO] = ''
        context.area.tag_redraw()


def _fechar_opcoes(tela):
    tela[_CHAVE_OPCOES] = 0
    tela[_CHAVE_SUSPENSO] = ''
    tela[_CHAVE_COR] = ''


def _valor_da_faixa(nome, fracao):
    """Posicao no trilho (0..1) -> valor da opcao, no passo dela."""
    minimo, maximo, passo = FAIXAS_OPCOES[nome]
    fracao = max(0.0, min(1.0, fracao))
    valor = round((minimo + fracao * (maximo - minimo)) / passo) * passo
    valor = max(minimo, min(maximo, valor))
    return int(valor) if isinstance(minimo, int) else float(valor)


def _cor_do_seletor(nome, parte, rgb, fx, fy):
    """Ponto clicado no quadro (fx=saturacao, fy=brilho) ou na matiz."""
    h, s, v = _hsv_opcao(nome, rgb)
    fx, fy = max(0.0, min(1.0, fx)), max(0.0, min(1.0, fy))
    if parte == 'matiz':
        h = _matiz_cor[nome] = fx
    else:
        s, v = fx, fy
    return colorsys.hsv_to_rgb(h, s, v)


def _aplicar_cor_opcao(nome, rgb):
    # escolher uma cor desliga o Tema / o Gizmo daquela opcao
    _definir_opcao(OPCAO_DO_ESPECIAL[ATALHO_ESPECIAL[nome]], False)
    _definir_opcao(nome, tuple(float(c) for c in rgb[:3]))


def _texto_faixa(valor):
    return ('%g' % round(float(valor), 2)).replace('.', ',') + ' px'


def _hsv_opcao(nome, rgb):
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    if s > 0.001 and v > 0.001:
        _matiz_cor[nome] = h
    return _matiz_cor.get(nome, h), s, v


def _cor_especial(nome):
    """'TEMA' (linhas na cor do tema), 'GIZMO' (realce por eixo) ou ''."""
    if nome == 'hud_rgb_linha' and _opcao('hud_linha_tema'):
        return 'TEMA'
    if nome == 'hud_rgb_realce' and _opcao('hud_realce_gizmo'):
        return 'GIZMO'
    return ''


# Atalho que nao e' uma cor so': o primeiro da fila de cada opcao
ATALHO_ESPECIAL = {'hud_rgb_linha': 'TEMA', 'hud_rgb_realce': 'GIZMO'}
OPCAO_DO_ESPECIAL = {'TEMA': 'hud_linha_tema', 'GIZMO': 'hud_realce_gizmo'}


def _seletor_cor_gaveta(painel, x, y, w, nome, rgb, especial):
    """Atalhos, quadrado saturacao x brilho e faixa de matiz, embaixo da
    amostra. Devolve o y da ultima linha ocupada (o laco desce 29)."""
    chave_especial = ATALHO_ESPECIAL[nome]
    atalhos = ((chave_especial, _cor_tema_linha() if chave_especial == 'TEMA'
                else COR_REALCE_PADRAO),) + CORES_ATALHO
    n = len(atalhos)
    lado = min(25, (w - 4 * (n - 1)) / n)
    for i, (chave, cor) in enumerate(atalhos):
        atual = especial == chave if chave in OPCAO_DO_ESPECIAL else (
            not especial and all(abs(a - b) < 0.002 for a, b in zip(cor, rgb)))
        painel.append((x + i * (lado + 4), y + 25 - lado, lado, lado,
                       'T' if chave == 'TEMA' else '',
                       ('cor', nome, 'atalho', cor, atual, chave)))
    base = y - 4 - ALTURA_QUADRO_COR
    painel.append((x, base, w, ALTURA_QUADRO_COR, '',
                   ('cor', nome, 'quadro', rgb)))
    painel.append((x, base - 20, w, 14, '', ('cor', nome, 'matiz', rgb)))
    # o laco desce 29 e a linha seguinte (25) fica 4 px abaixo da matiz
    return base - 20


def _widgets_conteudo_gaveta(context, largura, altura, _rolagem,
                             _rolagem_bib=0):
    """Cabecalho + painel da aba + divisoria + biblioteca."""
    itens = _widgets_aba_gaveta(context, largura, altura, _rolagem)
    x, w = 12, max(24, min(540, largura - 24))
    divisa = _divisa_gaveta(context, altura)
    # a linha e' desenhada de borda a borda; o retangulo de pegar fica
    # nas margens, como todo widget (regra de ouro da secao 6)
    itens.append((x, divisa - FOLGA_DIVISA_GAVETA, w,
                  2 * FOLGA_DIVISA_GAVETA, '', ('divisa', True)))
    _biblioteca_gaveta(context, itens, x, divisa - 34 + _rolagem_bib, w)
    return itens


def _widgets_aba_gaveta(context, largura, altura, _rolagem):
    s = context.scene
    # Mesmo se a area for alargada drasticamente, o menu permanece uma
    # coluna vertical legivel; miniaturas nao viram faixas gigantes.
    x, w = 12, max(24, min(540, largura - 24))
    itens = []
    metade = (w - 6) / 2
    # Cabecalho: Modulos | Portas | Puxadores, na largura toda (as
    # correntes entre elas foram descontinuadas)
    aba_w = (w - 2 * 4) / 3
    cx = x
    for rotulo, curto, acao in ABAS_GAVETA:
        itens.append((cx, altura - 40, aba_w, 29,
                      rotulo if aba_w >= 74 else curto, ('aba', acao)))
        cx += aba_w + 4
    y = altura - 105 + _rolagem
    if s.cabinet_aba in {'PORTAS', 'PUXADORES'}:
        # "Criar Portas" no TOPO da aba, logo abaixo das abas, largura
        # inteira e texto centralizado (backlog do usuario, Epico 2.3);
        # antes morava no pe' fixo ao lado da engrenagem. O "Criar
        # Puxador" segue o MESMO padrao (pedido do usuario).
        rotulo, acao = (_botao_criar_portas(context)
                        if s.cabinet_aba == 'PORTAS'
                        else _botao_criar_puxador())
        itens.append((x, altura - 48 - 8 - 30 + _rolagem, w, 30, rotulo, acao))
        y -= 38
    de_modulos = s.cabinet_aba == 'MODULOS'
    y = _bloco_medidas_gaveta(context, itens, x, y, w, largura, metade,
                              modos=de_modulos)
    if s.cabinet_aba == 'PORTAS':
        return _aba_portas_gaveta(context, itens, x, y, w, s)
    if s.cabinet_aba == 'PUXADORES':
        return _aba_puxadores_gaveta(context, itens, x, y, w, s)
    itens.append((x, y, w, 23, 'Montagem', None))
    y -= 31
    # Sem "Recalcular": o handler ja' normaliza as chapas ao fim de
    # todo S/G, e o botao so' repetia isso (pedido do usuario).
    # O ima (Adjacencia) virou a CORRENTE: com um objeto selecionado o
    # botao acende azul se ele esta' agregado (o clique desagrega) e fica
    # cinza se nao (o clique associa); com varios, conecta por distancia.
    # So' dois botoes (pedido do usuario): Agrupar e Converter sairam da
    # gaveta (seguem no F3); "Resetar distancia" (regua, azul com solda
    # fora da origem) volta a peca/modulo para a origem da solda.
    montagem = (('Corrente', OP_CORRENTE_OBJETO),
                ('Resetar distancia', OP_RESETAR_DISTANCIA))
    colunas = min(len(montagem), max(1, int(w // 36)))
    bw = (w - 6 * (colunas - 1)) / colunas
    for i, (rotulo, op) in enumerate(montagem):
        linha, coluna = divmod(i, colunas)
        estado = (_estado_corrente_objeto(context) if op == OP_CORRENTE_OBJETO
                  else _estado_resetar(context))
        acao = ('operador', op, estado)
        itens.append((x + coluna * (bw + 6), y - linha * 34,
                      bw, 28, rotulo, acao))
    linhas = -(-len(montagem) // colunas)
    y -= (linhas - 1) * 34
    pergunta = _pergunta_atual[0]
    if (pergunta is not None and pergunta['na_gaveta']
            and not pergunta.get('comodo')):
        y = _pergunta_na_gaveta(itens, x, y - 6, w, pergunta)
    return _secao_orcamento_gaveta(context, itens, x, y - 40, w)


def _secao_orcamento_gaveta(context, itens, x, y, w):
    """Orcamento para o ERP: o COMODO do modulo selecionado (UMA linha que
    expande; pedido do usuario: a grade fixa ocupava a aba) e o botao que
    copia o documento. O que o botao fez aparece nele e, havendo, as
    pendencias numa caixa preta logo abaixo."""
    # titulo como o de Montagem, sem separador (os da aba sao da cascata)
    itens.append((x, y, w, 23, 'Orcamento', None))
    y -= 31
    modulos = _modulos_da_selecao(context)
    if modulos:
        ativo = _modulo_do_objeto(context.object) or modulos[0]
        atual = _nome_comodo(_comodo_do_modulo(ativo))
        aberto = context.screen.get(_CHAVE_SUSPENSO, '') == SUSPENSO_COMODO
        itens.append((x, y, w, 25, 'Comodo: %s' % (atual or '(nenhum)'),
                      ('suspenso', SUSPENSO_COMODO, aberto)))
        y -= 29
        if aberto:
            # a lista abre DENTRO da aba, empurrando o resto para baixo
            opcoes = [(n, n) for n in _comodos_da_lista(context.scene)]
            if atual:
                opcoes.append((COMODO_NENHUM, 'Sem comodo'))
            opcoes.append((COMODO_OUTRO, 'Outro nome...'))
            y = _linha_escolha_gaveta(
                itens, x, y, w, '', ALVO_COMODO, tuple(opcoes), atual,
                alvo=ALVO_COMODO, por_linha=3 if w >= 300 else 2)
        pergunta = _pergunta_atual[0]
        if pergunta is not None and pergunta.get('comodo'):
            y = _pergunta_na_gaveta(itens, x, y + 23, w, pergunta) - 33
        y -= 4
    copiado = _orcamento_copiado[0]
    rotulo = 'Copiar orcamento (ERP)'
    if copiado is not None:
        rotulo = 'Copiado: %d modulo(s) - copiar de novo' % copiado['modulos']
    itens.append((x, y, w, 28, rotulo,
                  ('operador', OP_EXPORTAR_ORCAMENTO, copiado is not None)))
    if copiado is not None and copiado['pendencias']:
        texto = 'Pendencias:\n' + '\n'.join(
            '\n'.join(_quebrar_texto(p, w - 20))
            for p in copiado['pendencias'])
        linhas = texto.count('\n') + 1
        altura = 12 + 15 * linhas + 4
        itens.append((x, y - 6 - altura, w, altura, texto, ('pergunta',)))
    return itens


# ============================================== ORCAMENTO (ERP do usuario)
# O ERP da empresa le o orcamento em Markdown no padrao de um prompt de
# ditado: um bloco ```markdown e, fora dele, as Pendencias. Daqui sai SO'
# a marcenaria; o resto do documento fica como o prompt manda quando nada
# foi dito (Limpeza geral, Valores e Pagamento vazios, perfil investidor).
# Nada se inventa: a linha do modulo e' o NOME do grupo e os detalhes
# (portas, prateleiras, divisorias, puxadores) saem do 3D.
# O COMODO e' uma PASTA no Outliner (pedido do usuario): Collection
# marcada, na raiz da cena, com as Collections dos armarios dentro. Ela
# e' a unica fonte: arrastar o armario para outra pasta no Outliner
# tambem muda o comodo do orcamento.
MARCA_COLECAO_COMODO = "eh_colecao_comodo"
ALVO_COMODO = '@comodo'                  # alvo da 'escolha' que grava o comodo
SUSPENSO_COMODO = 'comodo'               # lista que expande na aba Modulos
COMODO_NENHUM = ''                       # volta o armario a' raiz
COMODO_OUTRO = '@outro'                  # abre o campo do nome digitado
OP_EXPORTAR_ORCAMENTO = 'object.cabinet_exportar_orcamento'
# Os comodos do prompt, na ORDEM do orcamento (os digitados vem depois,
# em ordem alfabetica). Varanda e' Sacada (regra do prompt). Com acento:
# e' o nome da pasta e o texto que o ERP le.
COMODOS = (
    'Cozinha', 'Copa', 'Sala', 'Quarto', 'Su\u00edte', 'Quarto su\u00edte',
    'Banheiro', 'Banheiro da su\u00edte', 'Lavabo', 'Lavanderia',
    '\u00c1rea de servi\u00e7o', 'Sacada', 'Escrit\u00f3rio', 'Closet',
)
SINONIMOS_COMODO = {'varanda': 'Sacada'}
# depois de copiar: o botao mostra o que fez e as pendencias ficam a'
# vista ate' a proxima copia, uma troca de comodo ou este tempo
SEGUNDOS_ORCAMENTO_COPIADO = 30.0
_orcamento_copiado = [None]      # {'modulos': n, 'pendencias': [...]}
# Nome que o add-on deu sozinho: o usuario nao disse que modulo e'.
NOME_AUTOMATICO_MODULO = re.compile(r'^(Armario \d+x\d+x\d+|Conjunto)$')
# (singular, plural) por modelo de porta e de puxador
PALAVRAS_PORTA = {
    'CORRER': ('porta de correr', 'portas de correr'),
    'BASCULANTE': ('porta basculante', 'portas basculantes'),
    'EMBUTIDA': ('porta embutida', 'portas embutidas'),
    'GIRO': ('porta', 'portas'),
}
PALAVRAS_PUXADOR = {'PERFIL': 'perfil', 'ALCA': 'al\u00e7a', 'BORDA': 'borda'}


def _modulo_do_objeto(obj):
    """Modulo de qualquer coisa nossa: ele mesmo, uma chapa dele, a porta
    ligada a ele (folha ou grupo) ou o puxador de uma delas."""
    if obj is None:
        return None
    if MARCA_CONJUNTO in obj:
        return obj
    if MARCA_PUXADOR in obj:
        obj = obj.parent
    grupo = _grupo_portas(obj)
    if grupo is not None:
        modulo = bpy.data.objects.get(grupo.get(CHAVE_MODULO_PORTA, ''))
        return modulo if modulo is not None and MARCA_CONJUNTO in modulo else None
    return _modulo_da_chapa(obj)


def _modulos_da_selecao(context):
    modulos = []
    for obj in [context.object, *(getattr(context, 'selected_objects', ())
                                   or ())]:
        modulo = _modulo_do_objeto(obj)
        if modulo is not None and modulo not in modulos:
            modulos.append(modulo)
    return modulos


def _nome_comodo(colecao):
    return _sem_sufixo(colecao.name) if colecao is not None else ''


def _limpar_nome_comodo(nome):
    nome = ' '.join((nome or '').split())
    return SINONIMOS_COMODO.get(nome.casefold(), nome)


def _pais_da_colecao(colecao, cena):
    return [c for c in (cena.collection, *bpy.data.collections)
            if colecao.name in c.children]


def _comodo_do_modulo(conj):
    """Pasta de comodo onde mora a Collection do armario, ou None."""
    colecao = _colecao_do_modulo(conj)
    if colecao is None:
        return None
    return next((c for c in bpy.data.collections
                 if c.get(MARCA_COLECAO_COMODO)
                 and colecao.name in c.children), None)


def _comodos_da_cena(cena):
    """Pastas de comodo que estao na cena (por nome sem o .001)."""
    pastas = {}
    for c in cena.collection.children_recursive:
        if c.get(MARCA_COLECAO_COMODO):
            pastas.setdefault(_nome_comodo(c), c)
    return pastas


def _comodos_da_lista(cena):
    """O que a lista oferece: os do prompt e os ja' digitados na cena."""
    digitados = sorted((n for n in _comodos_da_cena(cena) if n not in COMODOS),
                       key=str.casefold)
    return [*COMODOS, *digitados]


def _ordem_comodo(nome):
    return ((0, COMODOS.index(nome), '') if nome in COMODOS
            else (1, 0, nome.casefold()))


def _colecao_do_comodo(cena, nome):
    pasta = _comodos_da_cena(cena).get(nome)
    if pasta is None:
        pasta = bpy.data.collections.new(nome)
        pasta[MARCA_COLECAO_COMODO] = 1
        cena.collection.children.link(pasta)
    return pasta


def _garantir_colecao_modulo(cena, conj):
    """Armario de antes do v168 (sem Collection propria) ganha a dele:
    so' Collection entra na pasta do comodo."""
    colecao = _colecao_do_modulo(conj)
    if colecao is not None:
        return colecao
    nome = _nome_livre(conj.name, ignorar=(conj,))
    if nome != conj.name:
        nomear_grupo(conj, nome)
    colecao = bpy.data.collections.new(conj.name)
    colecao[MARCA_COLECAO_MODULO] = 1
    cena.collection.children.link(colecao)
    _mover_para_colecao(conj, colecao)
    return colecao


def _limpar_comodos_vazios():
    for pasta in [c for c in bpy.data.collections
                  if c.get(MARCA_COLECAO_COMODO)
                  and not c.all_objects and not c.children]:
        bpy.data.collections.remove(pasta)


def definir_comodo(cena, modulos, nome):
    """Poe a Collection de cada armario na pasta `nome` (vazio = raiz da
    cena). Devolve quantos armarios mudaram de lugar ou ja' estavam la'."""
    nome = _limpar_nome_comodo(nome)
    feitos = 0
    for conj in modulos:
        if conj is None or MARCA_CONJUNTO not in conj:
            continue
        colecao = _garantir_colecao_modulo(cena, conj)
        destino = (_colecao_do_comodo(cena, nome) if nome
                   else cena.collection)
        # liga antes de desligar: a Collection nunca fica sem dono
        if colecao.name not in destino.children:
            destino.children.link(colecao)
        for pai in _pais_da_colecao(colecao, cena):
            if pai != destino:
                pai.children.unlink(colecao)
        feitos += 1
    _limpar_comodos_vazios()
    _orcamento_copiado[0] = None
    return feitos


def _abrir_caixa_comodo(context):
    """"Outro nome...": o mesmo campo da caixa do nome do grupo, logo
    abaixo da linha do comodo. Guarda os armarios: o clique fora pode
    mudar a selecao antes do Enter."""
    nomes = [m.name for m in _modulos_da_selecao(context)]
    _nome_grupo_gaveta[0] = {'comodo': nomes, 'grupo': '', 'texto': '',
                             'cursor': 0, 'selecionado': False}
    op = 'object.cabinet_definir_comodo'
    _pergunta_atual[0] = {
        'texto': 'Nome do comodo', 'campo': True, 'na_gaveta': True,
        'comodo': True,
        'opcoes': [('OK', 'CHECKMARK', op, {'digitado': True}),
                   ('Cancelar', 'X', op, {'manter': True})]}


def _confirmar_campo_gaveta(estado):
    """Enter/OK no campo da caixa preta: nome do grupo ou do comodo."""
    if estado.get('comodo') is not None:
        modulos = [bpy.data.objects.get(n) for n in estado['comodo']]
        nome = _limpar_nome_comodo(estado['texto'])
        return bool(nome) and bool(definir_comodo(
            bpy.context.scene, modulos, nome))
    return nomear_grupo(bpy.data.objects.get(estado['grupo']), estado['texto'])


class OBJECT_OT_definir_comodo(Operator):
    """Poe os armarios selecionados na pasta do comodo (Outliner)"""
    bl_idname = 'object.cabinet_definir_comodo'
    bl_label = 'Comodo do Armario'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    nome: StringProperty(name='Comodo', options={'SKIP_SAVE'})
    # OK / Cancelar da caixa do "Outro nome..."
    digitado: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})
    manter: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        estado = _nome_grupo_gaveta[0]
        _redesenhar_viewports(context)
        if self.digitado or self.manter:
            _nome_grupo_gaveta[0] = _pergunta_atual[0] = None
            if self.manter or estado is None:
                return {'CANCELLED'}
            return ({'FINISHED'} if _confirmar_campo_gaveta(estado)
                    else {'CANCELLED'})
        if not definir_comodo(context.scene, _modulos_da_selecao(context),
                              self.nome):
            self.report({'WARNING'}, "Selecione um armario")
            return {'CANCELLED'}
        return {'FINISHED'}


def _quantos(n, palavras):
    singular, plural = palavras
    return '%d %s' % (n, singular if n == 1 else plural)


def _pecas_internas(conj):
    """(prateleiras, divisorias) no referencial do MODULO (girado vale):
    chapa deitada entre a de baixo e a de cima e chapa em pe' entre a da
    esquerda e a da direita. As das pontas sao base, tampo e laterais."""
    inversa = conj.matrix_world.to_3x3().normalized().inverted()
    posicoes = {0: [], 2: []}
    for chapa in _chapas_do_conjunto(conj):
        normal = inversa @ _eixos(chapa)[2]
        eixo = max(range(3), key=lambda i: abs(normal[i]))
        if eixo in posicoes:
            posicoes[eixo].append((inversa @ _centro(chapa))[eixo])

    def entre(valores):
        if len(valores) < 3:
            return 0
        baixo, alto = min(valores), max(valores)
        return sum(1 for v in valores
                   if baixo + TOL_BORDA < v < alto - TOL_BORDA)
    return entre(posicoes[2]), entre(posicoes[0])


def _detalhes_do_modulo(conj, puxadores):
    """O 3o andar do orcamento: so' o que o modelo 3D TEM."""
    detalhes = []
    portas = {}
    for grupo in _portas_do_conjunto(conj):
        p = grupo.get('porta_parametros') or {}
        tipo = p.get('abertura', 'GIRO')
        if tipo == 'GIRO' and p.get('dobradica') == 'SUPER_CURVA':
            tipo = 'EMBUTIDA'
        portas[tipo] = portas.get(tipo, 0) + len(_folhas_portas(grupo))
    for tipo, n in portas.items():
        if n:
            detalhes.append(_quantos(n, PALAVRAS_PORTA.get(
                tipo, PALAVRAS_PORTA['GIRO'])))
    prateleiras, divisorias = _pecas_internas(conj)
    detalhes.append(_quantos(prateleiras, ('prateleira interna',
                                           'prateleiras internas'))
                    if prateleiras else 'Sem prateleiras internas')
    if divisorias:
        detalhes.append(_quantos(divisorias, ('divis\u00f3ria interna',
                                              'divis\u00f3rias internas')))
    for tipo, n in puxadores.items():
        palavra = PALAVRAS_PUXADOR.get(tipo, '')
        detalhes.append(_quantos(n, ('puxador ' + palavra, 'puxadores '
                                     + palavra)).strip())
    return detalhes


def _puxadores_por_modulo(objetos):
    """{modulo: {tipo: quantidade}} -- importado (sem tipo) conta como ''."""
    contas = {}
    for pux in objetos:
        if MARCA_PUXADOR not in pux:
            continue
        modulo = _modulo_do_objeto(pux)
        if modulo is not None:
            tipos = contas.setdefault(modulo.name, {})
            tipo = pux.get('puxador_tipo', '')
            tipos[tipo] = tipos.get(tipo, 0) + 1
    return contas


def orcamento_da_cena(cena):
    """(texto, modulos exportados, pendencias) no padrao do ERP."""
    objetos = list(cena.objects)
    puxadores = _puxadores_por_modulo(objetos)
    por_comodo = {}
    pendencias = []
    modulos = sorted((o for o in objetos if MARCA_CONJUNTO in o
                      and _chapas_do_conjunto(o)),
                     key=lambda o: o.name.casefold())
    for conj in modulos:
        nome = _sem_sufixo(conj.name)
        comodo = _nome_comodo(_comodo_do_modulo(conj)) or None
        if NOME_AUTOMATICO_MODULO.match(nome):
            pendencias.append('- %s%s: n\u00e3o foi dito que m\u00f3dulo '
                              '\u00e9 (o nome do grupo ainda \u00e9 o '
                              'autom\u00e1tico).'
                              % (comodo + ', ' if comodo else '', nome))
        if comodo is None:
            pendencias.append('- %s: n\u00e3o foi dito o c\u00f4modo; o '
                              'm\u00f3dulo ficou fora do or\u00e7amento.'
                              % nome)
            continue
        por_comodo.setdefault(comodo, []).append(
            (nome, _detalhes_do_modulo(conj, puxadores.get(conj.name, {}))))
    soltas = [o for o in objetos if MARCA_CHAPA in o and MARCA_FOLHA not in o
              and _modulo_da_chapa(o) is None]
    if soltas:
        pendencias.append('- %s, fora de um arm\u00e1rio: n\u00e3o foi dito '
                          'a qual m\u00f3dulo pertence%s; ficou%s fora do '
                          'or\u00e7amento.' % (
                              _quantos(len(soltas), ('chapa solta',
                                                     'chapas soltas')),
                              'm' if len(soltas) > 1 else '',
                              'aram' if len(soltas) > 1 else ''))

    linhas = ['# Or\u00e7amento', 'cliente:', 'endereco:',
              'perfil: investidor', '']
    exportados = sum(len(v) for v in por_comodo.values())
    if exportados:
        # bloco sem conteudo nao tem cabecalho (regra do prompt)
        linhas += ['## M\u00f3veis', '']
        for comodo in sorted(por_comodo, key=_ordem_comodo):
            itens = por_comodo[comodo]
            linhas.append('### ' + comodo)
            for nome, detalhes in itens:
                linhas.append('- ' + nome)
                linhas += ['  - ' + d for d in detalhes]
            linhas.append('')
    # Limpeza: a unica coisa que entra sem pedir; sem Obras, e' a geral
    linhas += ['## Outros', '', '### Geral', '- Limpeza geral.', '',
               '## Valores', '- moveis:', '- obras:', '- eletros:',
               '- outros:', '',
               '## Pagamento', '- modalidade: entrada+parcelas',
               '- entrada:', '- parcelas:']
    texto = '```markdown\n' + '\n'.join(linhas) + '\n```\n\n'
    if pendencias:
        texto += ('Pend\u00eancias\n' + '\n'.join(pendencias)
                  + '\n\nQuer atualizar algum destes antes de eu refazer o '
                  'or\u00e7amento?\n')
    else:
        texto += 'Sem pend\u00eancias.\n'
    return texto, exportados, pendencias


def _apagar_orcamento_copiado():
    _orcamento_copiado[0] = None
    for janela in bpy.context.window_manager.windows:
        for area in janela.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
    return None


class OBJECT_OT_exportar_orcamento(Operator):
    """Copia os moveis da cena no padrao de orcamento do ERP (Markdown)"""
    bl_idname = OP_EXPORTAR_ORCAMENTO
    bl_label = "Copiar orcamento (ERP)"

    def execute(self, context):
        texto, exportados, pendencias = orcamento_da_cena(context.scene)
        context.window_manager.clipboard = texto
        # a gaveta mostra o que aconteceu (so' o relatorio na barra de
        # status passava despercebido: "copiar e nada acontece")
        _orcamento_copiado[0] = {'modulos': exportados,
                                 'pendencias': list(pendencias)}
        if bpy.app.timers.is_registered(_apagar_orcamento_copiado):
            bpy.app.timers.unregister(_apagar_orcamento_copiado)
        bpy.app.timers.register(_apagar_orcamento_copiado,
                                first_interval=SEGUNDOS_ORCAMENTO_COPIADO)
        _redesenhar_viewports(context)
        self.report({'WARNING'} if pendencias else {'INFO'},
                    "Orcamento copiado: %d modulo(s)%s" % (
                        exportados, ", %d pendencia(s)" % len(pendencias)
                        if pendencias else ""))
        return {'FINISHED'}


PX_CARACTERE_PERGUNTA = 6.4      # estimativa da largura de um caractere (11 px)


def _quebrar_texto(texto, largura):
    """Linhas que cabem em `largura` px (o bpy nao mede texto fora do
    desenho: estimativa por caractere, como os PX_* da gaveta)."""
    cabe = max(8, int(largura / PX_CARACTERE_PERGUNTA))
    linhas, atual = [], ''
    for palavra in texto.split():
        tentativa = (atual + ' ' + palavra).strip()
        if len(tentativa) > cabe and atual:
            linhas.append(atual)
            atual = palavra
        else:
            atual = tentativa
    return linhas + ([atual] if atual else [])


def _pergunta_na_gaveta(itens, x, topo, w, pergunta):
    """Caixa preta com a pergunta e as respostas lado a lado, a partir de
    `topo` (logo abaixo do botao que perguntou). Devolve o y de baixo."""
    texto = pergunta['texto']
    estado = _nome_grupo_gaveta[0]
    if pergunta.get('campo') and estado is not None:
        # o nome que se digita (Enter confirma), com o cursor
        texto += ': ' + _com_cursor(estado['texto'], estado['cursor'])
    linhas = _quebrar_texto(texto, w - 20)
    altura = 12 + 15 * len(linhas) + 8 + 26 + 10
    baixo = topo - altura
    itens.append((x, baixo, w, altura, '\n'.join(linhas), ('pergunta',)))
    n = len(pergunta['opcoes'])
    bw = (w - 20 - 6 * (n - 1)) / max(1, n)
    for i, (rotulo, _icone, _op, _props) in enumerate(pergunta['opcoes']):
        itens.append((x + 10 + i * (bw + 6), baixo + 10, bw, 26, rotulo,
                      ('resposta', i)))
    return baixo


def _biblioteca_gaveta(context, itens, x, y, w):
    """Biblioteca no painel de baixo, igual nas tres abas e sempre
    aberta: o titulo deixou de ser botao de abrir/fechar."""
    s = context.scene
    indice = indice_completo()
    bw = min(28, max(12, (w - 44) / 3))
    reserva = 3 * (bw + 4)
    itens.append((x, y, max(1, w - reserva), 26, 'Biblioteca (%d)' % len(indice),
                  None))
    for i, (rotulo, op) in enumerate((('Pasta', 'object.cabinet_abrir_biblioteca'),
                                     ('Assets', 'object.cabinet_prateleira'),
                                     ('Salvar +', 'object.cabinet_salvar_biblioteca'))):
        itens.append((x + w - reserva + 4 + i * (bw + 4), y, bw, 26, rotulo,
                      ('operador', op)))
    y -= 34
    y = _linha_cascata_gaveta(itens, x, y, w,
                              list(ARVORE.keys()), 1, s.chapa_n1, indice)
    if s.chapa_n1:
        itens.append((x, y + 31.5, w, 1, '', ('separador',)))
        y = _linha_cascata_gaveta(itens, x, y, w, _filhos_n2(s.chapa_n1),
                                  2, s.chapa_n2, indice, s.chapa_n1)
    if s.chapa_n1 and s.chapa_n2:
        filhos = _filhos_n3(s.chapa_n1, s.chapa_n2)
        if filhos:
            itens.append((x, y + 31.5, w, 1, '', ('separador',)))
        y = _linha_cascata_gaveta(itens, x, y, w, filhos,
                                  3, s.chapa_n3, indice,
                                  (s.chapa_n1, s.chapa_n2))
        if not filhos or s.chapa_n3:
            itens.append((x, y, min(w, 290), 26, 'Tamanho das miniaturas',
                          ('slider', None)))
            y -= 12
            daqui = [it for it in indice
                     if _niveis_de(it)[:2] == (s.chapa_n1, s.chapa_n2)
                     and (not filhos or _niveis_de(it)[2] == s.chapa_n3)]
            daqui.sort(key=lambda it: it.get('nome', '').casefold())
            # A foto nunca herda a largura da gaveta: e' sempre quadrada.
            lado_foto = 88 + (s.chapa_tam_bloco - 2) * 14
            bw = min(w, lado_foto + 10)
            colunas = max(1, int((w + 8) // (bw + 8)))
            altura_bloco = bw + 17
            for i, it in enumerate(daqui):
                linha, coluna = divmod(i, colunas)
                bx = x + coluna * (bw + 8)
                by = y - altura_bloco - linha * (altura_bloco + 30)
                itens.append((bx, by, bw, altura_bloco,
                              _abreviar(it.get('nome', ''), 17), ('preset', it)))
                acao = ('item', it)
                for j, rotulo in enumerate(('Ins.', 'Edit.', 'Trava')):
                    sw = (bw - 8) / 3
                    itens.append((bx + j * (sw + 4), by - 24,
                                  sw, 21, rotulo, (*acao, j)))
    return itens


def _desenhar_wireframe_gaveta(x, y, modo, largura, altura, profundidade,
                               folhas=0, trocado=False, escala=1.0):
    geometria = _geometria_wireframe(bpy.context.object, modo)
    if geometria is not None:
        (largura, altura, profundidade), extras, arestas = geometria
        arestas = [(a + 8, b + 8) for a, b in arestas]
    else:
        caixas = _caixas_das_folhas(largura, altura, profundidade, folhas)
        extras = [v for caixa in caixas for v in caixa]
        arestas = [(base + a, base + b)
                   for base in [0] + [8 + i * 8 for i in range(len(caixas))]
                   for a, b in _ARESTAS_WIREFRAME]
    pontos = _pontos_wireframe(largura, altura, profundidade, extras)
    if not pontos:
        return
    pontos = [(px * escala, py * escala) for px, py in pontos]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    segmentos = []
    for a, b in arestas:
        segmentos.extend(((x + pontos[a][0], y + pontos[a][1]),
                           (x + pontos[b][0], y + pontos[b][1])))
    shader.bind()
    cor = (*_cor_wireframe(bpy.context), 1)
    shader.uniform_float('color', cor)
    batch_for_shader(shader, 'LINES', {'pos': segmentos}).draw(shader)
    def rotulo(letra, ponto, dx=0, dy=0):
        _texto_gaveta(x + ponto[0] + dx, y + ponto[1] + dy,
                       letra, 14, cor)
    rotulo('P' if trocado else 'L',
           _meio_wireframe(pontos[6], pontos[7]), 0, 11)
    if modo == 'INDIVIDUAL':
        rotulo('E', _meio_wireframe(pontos[2], pontos[6]), -13)
        rotulo('A', _meio_wireframe(pontos[0], pontos[2]), -12, -8)
    elif modo == 'PORTA':
        # A porta tem largura, altura e espessura; profundidade nao.
        rotulo('A', _meio_wireframe(pontos[2], pontos[6]), -13)
        rotulo('E', _meio_wireframe(pontos[0], pontos[2]), -12, -8)
    else:
        rotulo('A', _meio_wireframe(pontos[2], pontos[6]), -13)
        # Com a porta em X, a aresta de cima passa a medir a
        # profundidade do modulo e a que recua, a largura.
        rotulo('L' if trocado else 'P',
               _meio_wireframe(pontos[0], pontos[2]), -12, -8)
        if modo == 'GRUPO':
            rotulo('E', pontos[1], 4, -13)


def _desenhar_foto_gaveta(it, x, y, w, h):
    png = it.get('foto') or os.path.splitext(it['arquivo'])[0] + '.png'
    caminho = os.path.join(it['pasta'], png)
    if not os.path.isfile(caminho):
        _texto_gaveta(x + 8, y + h / 2, 'Sem foto', 11)
        return
    try:
        entrada = _fotos_gaveta.get(caminho)
        stamp = os.path.getmtime(caminho)
        if entrada is None or entrada[0] != stamp:
            import numpy as np
            imagem = bpy.data.images.load(caminho, check_existing=False)
            try:
                largura, altura = imagem.size
                pixels = np.empty(largura * altura * 4, dtype=np.float32)
                imagem.pixels.foreach_get(pixels)
                alfa = pixels.reshape((altura, largura, 4))[:, :, 3]
                ys, xs = np.nonzero(alfa > (1.0 / 255.0))
                limites = ((int(xs.min()), int(ys.min()),
                            int(xs.max()) + 1, int(ys.max()) + 1)
                           if len(xs) else (0, 0, largura, altura))
                # PNG RGBA: preservar o alpha, sem achatar contra uma cor.
                dados = gpu.types.Buffer('FLOAT', largura * altura * 4,
                                          pixels)
                textura = gpu.types.GPUTexture(
                    (largura, altura), format='RGBA32F', data=dados)
                entrada = (stamp, textura, limites, largura, altura)
            finally:
                bpy.data.images.remove(imagem)
            _fotos_gaveta[caminho] = entrada
        _, textura, (x0, y0, x1, y1), iw, ih = entrada
        escala = min(w / (x1 - x0), h / (y1 - y0)) * 0.90
        dw, dh = (x1 - x0) * escala, (y1 - y0) * escala
        x, y = x + (w - dw) / 2, y + (h - dh) / 2
        w, h = dw, dh
        u0, v0, u1, v1 = x0 / iw, y0 / ih, x1 / iw, y1 / ih
        shader = gpu.shader.from_builtin('IMAGE')
        batch = batch_for_shader(shader, 'TRIS', {
            'pos': ((x, y), (x + w, y), (x + w, y + h),
                    (x, y), (x + w, y + h), (x, y + h)),
            'texCoord': ((u0, v0), (u1, v0), (u1, v1),
                         (u0, v0), (u1, v1), (u0, v1))})
        shader.bind()
        shader.uniform_sampler('image', textura)
        batch.draw(shader)
    except Exception as e:
        print('[Cabinet Creator] foto na gaveta:', e)
        _texto_gaveta(x + 8, y + h / 2, 'Foto indisponivel', 11)


def _trilho_miniaturas_gaveta(x, y, w, h):
    # Desenho e arraste usam os mesmos limites, sem incluir o rotulo.
    rotulo = min(145, w * 0.52)
    return x + rotulo + 8, y + h / 2, max(1, w - rotulo - 14)


def _animar_realces():
    areas = {a.as_pointer(): a for janela in bpy.context.window_manager.windows
             for a in janela.screen.areas if a.type == 'VIEW_3D'}
    agora = time.monotonic()
    animando = False
    for chave, estado in list(_realces.items()):
        if chave[0] not in areas:
            del _realces[chave]
            continue
        valor, alvo, instante = estado
        passo = max(0, agora - instante) / 0.16
        estado[0] += math.copysign(min(abs(alvo - valor), passo), alvo - valor)
        estado[2] = agora
        if estado[0] != valor:
            areas[chave[0]].tag_redraw()
        animando |= abs(estado[0] - alvo) > 0.0001

    # O deslize usa decaimento exponencial, nao passo fixo: assim
    # pular seis categorias de uma vez leva o mesmo tempo que pular
    # uma, desacelerando no fim como uma roleta.
    gavetas = [a for a in areas.values() if _eh_area_gaveta_bruto(a)]
    for chave, estado in list(_deslizes.items()):
        valor, alvo, instante = estado
        fatia = min(1.0, max(0.0, agora - instante) / DURACAO_DESLIZE)
        estado[0] = valor + (alvo - valor) * fatia
        estado[2] = agora
        if abs(estado[0] - alvo) < 0.002:
            estado[0] = alvo
        if estado[0] != valor:
            for area in gavetas:
                area.tag_redraw()
        animando |= estado[0] != alvo
    return 1.0 / 60 if animando else None


def _eh_area_gaveta_bruto(area):
    """Versao de `_eh_area_gaveta` que aceita a area solta."""
    for janela in bpy.context.window_manager.windows:
        if area in janela.screen.areas.values():
            return area == _area_gaveta(janela.screen)
    return False


def _deslizar(chave, alvo):
    """Posicao ANIMADA do carrossel rumo a `alvo`.

    Na primeira vez, e quando nada esta' em curso, devolve o proprio
    alvo -- entao fora de uma transicao o layout continua identico ao
    de antes, e os testes veem posicoes inteiras.
    """
    estado = _deslizes.get(chave)
    if estado is None:
        _deslizes[chave] = [float(alvo), float(alvo), time.monotonic()]
        return float(alvo)
    if estado[1] != alvo:
        estado[1], estado[2] = float(alvo), time.monotonic()
        if not bpy.app.timers.is_registered(_animar_realces):
            bpy.app.timers.register(_animar_realces, first_interval=0.0)
    return estado[0]


def _realcar(context, nome, ativo):
    """Liga ou desliga o glow de um widget, com transicao."""
    chave = (context.area.as_pointer(), nome)
    estado = _realces.setdefault(chave, [0.0, 0.0, time.monotonic()])
    alvo = float(ativo)
    if estado[1] != alvo:
        estado[1], estado[2] = alvo, time.monotonic()
    if estado[0] != alvo and not bpy.app.timers.is_registered(_animar_realces):
        bpy.app.timers.register(_animar_realces, first_interval=0.0)


def _valor_realce(context, nome):
    area = getattr(context, 'area', None)
    if area is None:
        return 0.0
    return _realces.get((area.as_pointer(), nome), (0.0,))[0]


def _glow_gaveta(x, y, w, h, raio, realce, cor, esquerda_reta=False):
    """Halo do widget aceso. Um so' lugar, para alca e botoes acenderem
    identicos.

    Liga o ALPHA por conta propria: `blf.draw` mexe no estado de blend
    e, sem isto, o halo do segundo widget em diante saia OPACO -- um
    bloco branco cobrindo o texto do botao.
    """
    if realce <= 0.0:
        return
    gpu.state.blend_set('ALPHA')
    for margem, alfa in ((6, 0.025), (4, 0.045), (2, 0.07)):
        _retangulo_arredondado_gaveta(
            x - margem, y - margem, w + 2 * margem, h + 2 * margem,
            raio + margem, (*cor, alfa * realce),
            esquerda_reta=esquerda_reta)


# ============================================= GRID DE MEDIDAS NA CENA
# Passar o mouse num campo de medida (ou abri-lo para edicao) desenha a
# caixa envolvente do alvo na viewport e ACENDE as quatro arestas do
# eixo daquele campo. Assim da' para ver o que vai mudar antes de
# mudar, em vez de descobrir por tentativa e erro.

# Qual eixo cada rotulo move, por modo de medida. INDIVIDUAL usa os
# eixos LOCAIS da chapa (X=largura, Y=comprimento, Z=espessura), porque
# a chapa pode estar girada e a Espessura continua sendo a aresta local
# Z. Os outros modos usam eixos de MUNDO na convencao do add-on
# (Largura=X, Altura=Z, Profundidade=Y). Espessura de modulo nao e'
# aresta da caixa: nao acende nada, de proposito.
EIXOS_MEDIDA = {
    'INDIVIDUAL': {'Largura': 0, 'Altura': 1, 'Espessura': 2},
    'GRUPO': {'Largura': 0, 'Altura': 2, 'Profundidade': 1},
    'LIVRE': {'Largura': 0, 'Altura': 2, 'Profundidade': 1},
}

# Cantos indexados por bits: i + 2*j + 4*k ao longo de u, v, w. Com
# essa ordem as quatro arestas de um eixo saem de uma conta simples,
# sem tabela escrita a mao.
ARESTAS_EIXO = (
    ((0, 1), (2, 3), (4, 5), (6, 7)),
    ((0, 2), (1, 3), (4, 6), (5, 7)),
    ((0, 4), (1, 5), (2, 6), (3, 7)),
)

_handler_grid = [None]
_realce_medida = [None]      # rotulo do campo aceso, ou None
_campos_gaveta = {}          # ponteiro do gizmo -> retangulo do campo


# ======================================== HUD PARAMETRICA NA VIEWPORT
_handler_hud_texto = [None]
_clique_chapa_hud = {}
# regiao -> nome da chapa cujo PRESS deixou passar (o CLICK leva o modulo)
_clique_pendente = {}
_hover_hud = {}             # regiao -> alvo espacial; nao vaza entre vistas
_edicao_hud = [None]
RAIO_ARESTA_HUD = 7.0
RAIO_CANTO_HUD = 10.0
LIMIAR_ARRASTE_HUD_PX = 4.0  # abaixo disto o gesto e' clique, nao arraste
COR_REALCE_HUD = (1.0, 0.35, 0.05, 1.0)   # padrao; a cor vem das opcoes


def _contexto_hud(context):
    """Onde a HUD existe. Durante G/R/S ela some inteira -- linhas,
    letras, seta e hover -- e volta quando o gesto termina."""
    if _transformando():
        _hover_hud.clear()
        return False
    return (context.mode == 'OBJECT' and context.area is not None
            and context.area.type == 'VIEW_3D'
            and context.region is not None and context.region.type == 'WINDOW'
            and context.region_data is not None and not _eh_area_gaveta(context))


def _raio_cru(context, posicao):
    """(objeto original, ponto, normal, face, matriz) sob o mouse."""
    if not _contexto_hud(context):
        return None
    origem = view3d_utils.region_2d_to_origin_3d(
        context.region, context.region_data, posicao)
    direcao = view3d_utils.region_2d_to_vector_3d(
        context.region, context.region_data, posicao)
    acertou, ponto, normal, face, obj, matriz = context.scene.ray_cast(
        context.evaluated_depsgraph_get(), origem, direcao)
    if not acertou or obj is None:
        return None
    return obj.original, ponto, normal, face, matriz


def _ferragem_sob_mouse(context, posicao):
    """A dobradica/pistao sob o mouse (o que tem modo de edicao), ou None."""
    atingido = _raio_cru(context, posicao)
    if atingido is None:
        return None
    obj = atingido[0]
    return obj if obj.get(CHAVE_FERRAGEM) in TIPOS_SELECAO_FERRAGEM else None


def _raio_hud(context, posicao):
    atingido = _raio_cru(context, posicao)
    if atingido is None:
        return None
    obj, ponto, normal, face, matriz = atingido
    if CHAVE_FERRAGEM in obj:
        # para quem pergunta "que porta e' esta": a ferragem vale pela
        # folha (o clique nela mesma e' de `_ferragem_sob_mouse`)
        dono = obj.parent
        if dono is not None and MARCA_PORTAS in dono:
            dono = (_folhas_portas(dono) or [None])[0]
        if dono is None or MARCA_FOLHA not in dono:
            return None
        # a face e' da ferragem, nao da folha: sem face (-1)
        return dono, ponto, normal, -1, dono.matrix_world.copy()
    return obj, ponto, normal, face, matriz


def _familia_do_clique(obj):
    """O que um clique simples em `obj` seleciona: o modulo com tudo
    dentro, ou o grupo solto da chapa."""
    modulo = _modulo_da_chapa(obj)
    if modulo is not None:
        # ferragem nao acende com o modulo (seleciona-se por si mesma)
        return [modulo, *(o for o in modulo.children_recursive
                          if CHAVE_FERRAGEM not in o)]
    return familia_de(obj)


def _somar_peca(context, obj, duplo=False):
    """Shift na viewport: SOMA a selecao, como no Blender (pedido do
    usuario).

    - Shift+clique: o modulo inteiro de `obj`; mas se o grupo dele ja'
      esta' em selecao INDIVIDUAL (parte dele selecionada), so' a chapa
      -- e clicar de novo na chapa ativa a tira, como o Shift nativo.
    - Shift+duplo clique: isola `obj` DENTRO da selecao: o resto do grupo
      dele sai, os outros grupos e chapas ficam. O 1o clique do duplo ja'
      somou o grupo, por isso o duplo so' encolhe o grupo de `obj`."""
    familia = [o for o in (_familia_do_clique(obj) or [obj]) if o.visible_get()]
    marcados = [o for o in familia if o.select_get()]
    inteiro = len(marcados) == len(familia)
    if not duplo and (not marcados or inteiro):
        _selecionar_chapa_hud(context, obj, somar=True)
        return
    ativo = context.view_layer.objects.active
    if duplo:
        if inteiro:
            for o in familia:
                o.select_set(False)
        obj.select_set(True)
    elif obj.select_get() and ativo == obj:
        obj.select_set(False)
        if context.area:
            context.area.tag_redraw()
        return
    else:
        obj.select_set(True)
    _ocupado[0] = True
    try:
        obj.chapa_modo = 'INDIVIDUAL'
    finally:
        _ocupado[0] = False
    context.view_layer.objects.active = obj
    if context.area:
        context.area.tag_redraw()


def _selecionar_chapa_hud(context, obj, individual=False, somar=False):
    """A selecao e o modo de medidas mudam juntos, inclusive para portas.

    `somar` (Shift) junta o modulo a selecao em vez de troca-la: e' assim
    que se seleciona mais de um item para editar a medida de todos."""
    modulo = _modulo_da_chapa(obj)
    familia = _familia_do_clique(obj)
    if not somar:
        for selecionado in context.selected_objects:
            selecionado.select_set(False)
    for alvo in ([obj] if individual else familia or [obj]):
        alvo.select_set(True)
    _ocupado[0] = True
    try:
        obj.chapa_modo = 'INDIVIDUAL' if individual else 'GRUPO'
    finally:
        _ocupado[0] = False
    context.view_layer.objects.active = obj if individual or modulo is None else modulo
    if not individual and modulo is None:
        sincronizar_grupo(context)
    if context.area:
        context.area.tag_redraw()


def _nivel_da_selecao(context, obj):
    """Em que nivel a porta de `obj` esta' selecionada agora.

    'PORTA' = o grupo inteiro, 'FOLHA' = uma folha dele, 'MODULO' =
    qualquer outra coisa. Lido ANTES do clique que vai mudar a selecao.
    """
    grupo = _grupo_portas(obj)
    ativo = context.object
    if grupo is None or ativo is None:
        return 'MODULO'
    if ativo == grupo:
        return 'PORTA'
    if MARCA_FOLHA in ativo and _grupo_portas(ativo) == grupo:
        return 'FOLHA'
    return 'MODULO'


def _selecionar_porta_hud(context, folha, nivel, somar=False):
    """Nivel PORTA: o grupo e todas as folhas. Nivel FOLHA: so' ela.
    `somar` (Shift) junta a selecao em vez de troca-la."""
    grupo = _grupo_portas(folha)
    if grupo is None:
        return
    if not somar:
        for selecionado in context.selected_objects:
            selecionado.select_set(False)
    if nivel == 'PORTA':
        for alvo in [grupo, *_folhas_portas(grupo)]:
            alvo.select_set(True)
        context.view_layer.objects.active = grupo
    else:
        folha.select_set(True)
        _ocupado[0] = True
        try:
            folha.chapa_modo = 'INDIVIDUAL'
        finally:
            _ocupado[0] = False
        context.view_layer.objects.active = folha
    if context.area:
        context.area.tag_redraw()


def _caixa_hud_objetos(objetos, matriz=None):
    """Uma caixa compartilhada pelo desenho e pelo hit-test."""
    matriz = matriz if matriz is not None else Matrix.Identity(4)
    inversa = matriz.inverted()
    pontos = []
    for o in objetos:
        if o.type != 'MESH':
            continue
        if MARCA_CHAPA in o:
            # medida NOMINAL: o perfil tira uma faixa da malha, nao da chapa
            pontos += [inversa @ p for p in _cantos(o)]
        else:
            pontos += [inversa @ (o.matrix_world @ Vector(v)) for v in o.bound_box]
    if not pontos:
        return None
    lo = Vector(tuple(min(p[i] for p in pontos) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in pontos) for i in range(3)))
    return [matriz @ p for p in _cantos_caixa(
        lo, Vector((hi.x-lo.x, 0, 0)), Vector((0, hi.y-lo.y, 0)),
        Vector((0, 0, hi.z-lo.z)))]


def _alvo_hud(context):
    """O item do objeto ATIVO (o 1o de `_itens_da_selecao`), ou None."""
    obj = context.object
    if obj is None or not obj.select_get():
        return None
    if MARCA_CHAPA not in obj and MARCA_CONJUNTO not in obj:
        return None
    itens = _itens_hud(context)
    return itens[0] if itens else None


def _itens_hud(context):
    """Itens que a HUD mostra: TODOS os da selecao, cada um com o seu
    contorno (pedido do usuario: com dois modulos so' o ultimo aparecia).
    Porta e folha ativas se editam pela gaveta: L/A de uma folha mexida
    na HUD seria apagado no proximo recalculo das folhas."""
    obj = context.object
    if (obj is not None and obj.select_get()
            and (MARCA_PORTAS in obj or MARCA_FOLHA in obj)):
        return []
    return _itens_da_selecao(context)


def _geometrias_hud(context):
    return [g for g in (_geometria_do_item(*item) for item in _itens_hud(context))
            if g is not None]


def _alvo_e_do_item(geometria, alvo):
    """O alvo aceso pertence a este item? So' ele acende, mostra a seta
    e ganha a letra E -- os outros itens desenham normal."""
    if not alvo:
        return False
    if alvo['tipo'] == 'espessura':
        return (geometria['modo'] == 'INDIVIDUAL'
                and alvo['objeto'] in geometria['chapas'])
    if alvo['tipo'] == 'ancora':
        return alvo['objeto'] == geometria['objeto']
    identidade = _identidade_hud(alvo)
    return any(_identidade_hud(l) == identidade for l in geometria['linhas'])


def _linha_gap_hud(grupo):
    folhas = _folhas_portas(grupo)
    if len(folhas) != 2:
        return None
    inversa = grupo.matrix_world.inverted()
    caixas = [[inversa @ (f.matrix_world @ Vector(v)) for v in f.bound_box]
              for f in folhas]
    caixas.sort(key=lambda caixa: min(p.x for p in caixa))
    x = (max(p.x for p in caixas[0]) + min(p.x for p in caixas[1])) / 2
    baixo = max(min(p.y for p in caixa) for caixa in caixas)
    cima = min(max(p.y for p in caixa) for caixa in caixas)
    frente = max(p.z for caixa in caixas for p in caixa)
    if cima <= baixo:
        return None
    return [grupo.matrix_world @ Vector((x, y, frente)) for y in (baixo, cima)]


def _geometria_hud(context):
    """Linhas de dimensao, contornos das portas e cantos em MUNDO."""
    alvo = _alvo_hud(context)
    if alvo is None:
        return None
    return _geometria_do_item(*alvo)


def _chave_do_item(obj, chapas):
    if MARCA_CONJUNTO in obj:
        return ('M', obj.name)
    return ('C', tuple(sorted(c.name for c in chapas)))


def _chave_do_alvo(alvo):
    return _chave_do_item(alvo['objeto'], alvo.get('chapas') or [alvo['objeto']])


def _itens_da_selecao(context):
    """Os itens independentes da selecao, como (objeto, modo, chapas), o
    do objeto ativo primeiro.

    Sem ordem de hierarquia (pedido do usuario: dois grupos, um grupo e
    uma chapa, duas chapas, em qualquer ordem):
    - modulo com o Empty selecionado = o modulo inteiro (GRUPO), uma vez
      so', por mais pecas que acendam com ele;
    - grupo solto de chapas (adjacencia) todo selecionado = GRUPO;
    - qualquer outra chapa vale SOZINHA (INDIVIDUAL): a isolada pelo
      duplo clique ou somada com Shift, mesmo dentro de um modulo.
    Porta, puxador e acessorio vem junto com o modulo, nao sao itens.
    """
    selecionados = list(getattr(context, 'selected_objects', ()) or ())
    marcados = set(selecionados)
    ativo = getattr(context, 'active_object', None)
    if ativo in marcados:
        selecionados.remove(ativo)
        selecionados.insert(0, ativo)
    itens, chaves = [], set()

    def somar(obj, modo, chapas):
        chave = _chave_do_item(obj, chapas)
        if chave not in chaves:
            chaves.add(chave)
            itens.append((obj, modo, chapas))

    for o in selecionados:
        if any(m in o for m in (MARCA_PORTAS, MARCA_FOLHA, MARCA_PUXADOR,
                                MARCA_ACESSORIO)):
            continue
        if MARCA_CONJUNTO in o:
            if ('M', o.name) not in chaves:
                somar(o, 'GRUPO', _chapas_do_conjunto(o))
            continue
        if MARCA_CHAPA not in o or o.type != 'MESH':
            continue
        modulo = _modulo_da_chapa(o)
        if modulo is not None and modulo in marcados:
            if ('M', modulo.name) not in chaves:
                somar(modulo, 'GRUPO', _chapas_do_conjunto(modulo))
            continue
        if modulo is None and len(marcados) > 1:
            grupo = grupo_de(o) or [o]
            if len(grupo) > 1 and all(c in marcados for c in grupo):
                somar(o, 'GRUPO', grupo)
                continue
        somar(o, 'INDIVIDUAL', [o])
    return itens


def _geometria_do_item(obj, modo, chapas):
    """A geometria da HUD de UM item -- o ativo ou, na edicao de varios
    itens, cada modulo/chapa que entra na conta."""
    matriz = obj.matrix_world if modo == 'INDIVIDUAL' else None
    cantos = _caixa_hud_objetos(chapas, matriz)
    if cantos is None:
        return None
    letras = ('L', 'A', 'E') if modo == 'INDIVIDUAL' else ('L', 'P', 'A')
    linhas = []
    for eixo, arestas in enumerate(ARESTAS_EIXO):
        for i, j in arestas:
            linhas.append({'tipo': 'medida', 'objeto': obj, 'modo': modo,
                           'eixo': eixo, 'letra': letras[eixo],
                           'cantos': (i, j), 'chapas': chapas,
                           'pontos': [cantos[i], cantos[j]]})
    grupos = _grupos_de_porta(obj) if modo == 'GRUPO' else []
    for grupo in grupos:
        if any(float(f.get(CHAVE_ABERTURA, 0.0)) > 0.0
               for f in _folhas_portas(grupo)):
            # porta aberta (pedido do usuario): a caixa envolveria o giro
            # inteiro e a folga ate' o modulo nao existe -- nada da porta
            continue
        caixa = _caixa_hud_objetos(_folhas_portas(grupo), grupo.matrix_world)
        if caixa is None:
            continue
        for arestas in ARESTAS_EIXO:
            for i, j in arestas:
                linhas.append({'tipo': 'contorno_porta', 'objeto': grupo,
                               'pontos': [caixa[i], caixa[j]]})
        gap = _linha_gap_hud(grupo)
        if gap is not None:
            linhas.append({'tipo': 'gap', 'objeto': grupo,
                           'letra': '', 'pontos': gap})
    return {'objeto': obj, 'modo': modo, 'chapas': chapas,
            'cantos': cantos, 'linhas': linhas}


def _distancia_segmento_hud(mouse, a, b):
    direcao = b - a
    fator = ((mouse - a).dot(direcao) / direcao.length_squared
             if direcao.length_squared > 1e-12 else 0)
    ponto = a + direcao * max(0, min(1, fator))
    return (mouse - ponto).length


def _projetar_hud(context, ponto):
    return view3d_utils.location_3d_to_region_2d(
        context.region, context.region_data, ponto)


def _identidade_hud(alvo):
    if alvo is None:
        return None
    return (alvo['tipo'], alvo['objeto'].as_pointer(),
            alvo.get('eixo'), alvo.get('canto'), alvo.get('face'))


def _acertar_linhas_hud(geometria, mouse, projetar, escala=1, cantos=True):
    """Distancia em pixels: funciona em perspectiva, ortografica e orbitando.

    `cantos=False` ignora as quinas: escolhendo a linha do proximo item
    so' medidas interessam, nunca mover o modulo."""
    mouse = Vector(mouse)
    obj = geometria['objeto']
    if cantos and geometria['modo'] == 'GRUPO' and MARCA_CONJUNTO in obj:
        cantos = [(i, projetar(p)) for i, p in enumerate(geometria['cantos'])]
        proximos = [(mouse-p).length for i, p in cantos if p is not None]
        if proximos and min(proximos) <= RAIO_CANTO_HUD * escala:
            i, ponto = min(((i, p) for i, p in cantos if p is not None),
                           key=lambda item: (mouse-item[1]).length)
            return {'tipo': 'ancora', 'objeto': obj, 'canto': i,
                    'pontos': [geometria['cantos'][i]]}
    candidatos = []
    for linha in geometria['linhas']:
        if linha['tipo'] == 'contorno_porta':
            continue
        a, b = (projetar(p) for p in linha['pontos'])
        if a is None or b is None:
            continue
        distancia = _distancia_segmento_hud(mouse, a, b)
        if distancia <= RAIO_ARESTA_HUD * escala:
            candidatos.append((distancia, linha, a, b))
    if not candidatos:
        return None
    _d, linha, a, b = min(candidatos, key=lambda item: item[0])
    if linha['tipo'] == 'medida':
        # A quina mais perto do mouse fica PARADA e o movel cresce para
        # o outro lado -- modulo (L/A/P) e chapa individual (L/A/E: a
        # Espessura tambem tem seta nas quinas, pedido do usuario). Em
        # ARESTAS_EIXO o primeiro canto e' o do lado minimo do eixo.
        # Copia: a linha da geometria e' compartilhada.
        lado = 'min' if (mouse - a).length <= (mouse - b).length else 'max'
        pontos = linha['pontos'] if lado == 'min' else linha['pontos'][::-1]
        linha = dict(linha, lado=lado, pontos=list(pontos))
    return linha


def _face_espessura_hud(context, posicao, chapas):
    atingido = _raio_hud(context, posicao)
    if atingido is None:
        return None
    obj, _ponto, normal, face, matriz = atingido
    if obj not in chapas or MARCA_CHAPA not in obj:
        return None
    normal_local = (matriz.to_3x3().transposed() @ normal).normalized()
    # As faces largas tem normal Z local. Somente o topo estreito e
    # as laterais da espessura devem oferecer esta edicao.
    if abs(normal_local.z) > 0.5:
        return None
    avaliado = obj.evaluated_get(context.evaluated_depsgraph_get())
    if face < 0 or face >= len(avaliado.data.polygons):
        return None
    poligono = avaliado.data.polygons[face]
    pontos = [matriz @ avaliado.data.vertices[i].co for i in poligono.vertices]
    return {'tipo': 'espessura', 'objeto': obj, 'face': face,
            'letra': 'E', 'pontos': pontos + pontos[:1]}


def _distancia_alvo_hud(alvo, mouse, projetar):
    """Pixels do mouse ate' o alvo (quina ou linha) -- desempata itens."""
    pontos = [projetar(p) for p in alvo['pontos'][:2]]
    if any(p is None for p in pontos):
        return float('inf')
    if len(pontos) == 1:
        return (Vector(mouse) - pontos[0]).length
    return _distancia_segmento_hud(Vector(mouse), *pontos)


def _acertar_hud(context, posicao):
    """Quina ou linha mais perto do mouse entre TODOS os itens da
    selecao; quina antes de linha, como dentro de um item."""
    if not _contexto_hud(context):
        return None
    geometrias = _geometrias_hud(context)
    if not geometrias:
        return None
    escala = context.preferences.system.ui_scale
    projetar = lambda p: _projetar_hud(context, p)
    melhor = None
    for geometria in geometrias:
        alvo = _acertar_linhas_hud(geometria, posicao, projetar, escala)
        if alvo is None:
            continue
        chave = (alvo['tipo'] != 'ancora',
                 _distancia_alvo_hud(alvo, posicao, projetar))
        if melhor is None or chave < melhor[0]:
            melhor = (chave, alvo)
    if melhor is not None:
        return melhor[1]
    # E pertence apenas a chapa individual. No modulo a espessura
    # continua sendo editada na gaveta, mesmo com ela aberta.
    chapas = [c for g in geometrias if g['modo'] == 'INDIVIDUAL'
              for c in g['chapas']]
    if chapas:
        return _face_espessura_hud(context, posicao, chapas)
    return None


def _alvo_vivo(alvo):
    """Os objetos do alvo guardado ainda existem?

    Ctrl+Z, abrir arquivo e apagar liberam os objetos, mas a referencia
    Python guardada no hover continua com o endereco velho (o Blender de
    release nao a invalida). Desenhar com ela le' memoria liberada e o
    crash sai depois, em lugar aleatorio (visto no depsgraph e no
    alocador do Python). `as_pointer()` so' devolve o endereco guardado,
    sem tocar o objeto.
    """
    try:
        vivos = {o.as_pointer() for o in bpy.data.objects}
        return all(o.as_pointer() in vivos for o in
                   [alvo['objeto'], *(alvo.get('chapas') or ())])
    except (ReferenceError, KeyError, TypeError):
        return False


def _realce_hud(context):
    edicao = _edicao_hud[0]
    if edicao is not None and edicao['regiao'] == context.region.as_pointer():
        return edicao['alvo']
    chave = context.region.as_pointer()
    alvo = _hover_hud.get(chave)
    if alvo is not None and not _alvo_vivo(alvo):
        _hover_hud.pop(chave, None)
        return None
    return alvo


def _segmentos_hud(geometria, alvo):
    normais, acesos = [], []
    identidade = _identidade_hud(alvo)
    for linha in geometria['linhas']:
        destino = acesos if _identidade_hud(linha) == identidade else normais
        destino.extend(linha['pontos'])
    if alvo and alvo['tipo'] == 'espessura':
        for a, b in zip(alvo['pontos'], alvo['pontos'][1:]):
            acesos.extend((a, b))
    return normais, acesos


def _desenhos_hud(context):
    """[(geometria, alvo aceso)] do que a HUD mostra agora.

    Normalmente e' so' o item ativo. Na edicao de varios itens: os ja'
    escolhidos aparecem so' com a medida escolhida (acesa) -- nao da'
    para escolher o mesmo objeto de novo --, os outros com todas as
    linhas, acendendo a que esta' sob o mouse.
    """
    estado = _edicao_hud[0]
    if (estado is None or not estado.get('todos')
            or estado['regiao'] != context.region.as_pointer()):
        aceso = _realce_hud(context)
        return [(g, aceso if _alvo_e_do_item(g, aceso) else None)
                for g in _geometrias_hud(context)]
    escolhidos = {_chave_do_alvo(a): a for a in estado['itens']}
    hover = estado.get('hover')
    desenhos = []
    for item in estado['todos']:
        geometria = _geometria_do_item(*item)
        if geometria is None:
            continue
        chave = _chave_do_item(item[0], item[2])
        if chave in escolhidos:
            alvo = escolhidos[chave]
            geometria = dict(geometria, linhas=[
                l for l in geometria['linhas']
                if _identidade_hud(l) == _identidade_hud(alvo)])
            desenhos.append((geometria, alvo))
        else:
            # ainda sem seta: pisca (`_piscar_pendentes`)
            desenhos.append((dict(geometria, pendente=True),
                             hover if hover is not None
                             and _chave_do_alvo(hover) == chave else None))
    return desenhos


# Varios itens: escolhida a seta do primeiro, os que ainda precisam de
# seta dao uma piscada de luz nas linhas (pedido do usuario).
DURACAO_PISCADA_HUD = 0.9           # s: duas piscadas
_piscada_hud = [0.0]                # instante em que a piscada comecou


def _brilho_piscada(agora=None):
    """0..1: duas piscadas em DURACAO_PISCADA_HUD, depois apaga."""
    t = (time.time() if agora is None else agora) - _piscada_hud[0]
    if t < 0 or t > DURACAO_PISCADA_HUD:
        return 0.0
    return abs(math.sin(t * math.tau / DURACAO_PISCADA_HUD))


def _animar_piscada():
    """Timer: redesenha as viewports enquanto a piscada dura."""
    try:
        for janela in bpy.context.window_manager.windows:
            for area in janela.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception as e:
        print("[Cabinet Creator] piscada:", e)
        return None
    if time.time() - _piscada_hud[0] > DURACAO_PISCADA_HUD:
        return None
    return 1 / 30


def _piscar_pendentes():
    _piscada_hud[0] = time.time()
    if not bpy.app.timers.is_registered(_animar_piscada):
        bpy.app.timers.register(_animar_piscada, first_interval=0.0)


def _principal_hud(context, desenhos):
    """Indice do desenho do item ATIVO quando ha' 2+ itens na HUD, ou None.

    Pedido do usuario: com varios selecionados nao se sabia qual e' a
    selecao principal (a que manda nas funcoes); a dela sai mais grossa."""
    if len(desenhos) < 2:
        return None
    item = _alvo_hud(context)
    if item is None:
        return None
    chave = _chave_do_item(item[0], item[2])
    for i, (geometria, _alvo) in enumerate(desenhos):
        if _chave_do_item(geometria['objeto'], geometria['chapas']) == chave:
            return i
    return None


def _espessura_principal_hud(espessura):
    """Levemente mais grossa: +40% da escolhida, no minimo 1 px."""
    return espessura + max(1.0, 0.4 * espessura)


def _desenhar_hud_3d(context):
    if not _contexto_hud(context):
        return
    normais, acesos, pendentes, principais = [], {}, [], []
    desenhos = _desenhos_hud(context)
    principal = _principal_hud(context, desenhos)
    for indice, (geometria, alvo) in enumerate(desenhos):
        n, a = _segmentos_hud(geometria, alvo)
        if indice == principal:
            principais += n
        else:
            normais += n
        if geometria.get('pendente'):
            pendentes += n
        if a:
            # uma cor por medida acesa (realce do gizmo: L, A e P diferem)
            acesos.setdefault(_cor_realce_hud(_letra_do_alvo(alvo)),
                              []).extend(a)
    # Pecas associadas que se separaram: linha acesa (a corrente no meio
    # dela e' um botao do VIEW3D_GGT_correntes_cabinet)
    for corrente in _correntes_hud(context):
        acesos.setdefault(_cor_realce_hud(), []).extend(corrente['pontos'])
    if not normais and not acesos and not principais:
        return
    cor = _cor_linhas_hud(context)
    espessura = float(_opcao('hud_espessura_linha'))
    # POLYLINE: `line_width_set` com o shader comum para em poucos
    # pixels (ou em 1) conforme o driver/backend, e a faixa vai a 50.
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    try:
        gpu.state.blend_set('ALPHA')
        # Contorno parametricamente selecionavel de qualquer angulo.
        gpu.state.depth_test_set('NONE')
        shader.bind()
        shader.uniform_float('viewportSize', (context.region.width,
                                              context.region.height))
        shader.uniform_float('lineWidth', espessura)
        shader.uniform_float('color', cor)
        brilho = _brilho_piscada() if pendentes else 0.0
        if brilho > 0:
            # luz por baixo das linhas dos itens que faltam orientar
            for folga, alfa in ((7.0, 0.18), (4.0, 0.35), (1.5, 0.9)):
                shader.uniform_float('lineWidth', espessura + folga * brilho)
                shader.uniform_float('color', (1.0, 1.0, 1.0, alfa * brilho))
                batch_for_shader(shader, 'LINES', {'pos': pendentes}).draw(shader)
            shader.uniform_float('lineWidth', espessura)
            shader.uniform_float('color', cor)
        if normais:
            batch_for_shader(shader, 'LINES', {'pos': normais}).draw(shader)
        if principais:
            # a selecao principal (ativa), entre varias
            shader.uniform_float('lineWidth', _espessura_principal_hud(espessura))
            batch_for_shader(shader, 'LINES', {'pos': principais}).draw(shader)
            shader.uniform_float('lineWidth', espessura)
        for realce, pontos in acesos.items():
            # Halo SOMADO a espessura (1.5 da' o 7/5/2.5 de sempre):
            # multiplicado, a 50 px ele cobria o modulo inteiro.
            for folga, alfa in ((5.5, 0.12), (3.5, 0.25), (1.0, 1)):
                shader.uniform_float('lineWidth', espessura + folga)
                shader.uniform_float('color', (*realce[:3], alfa))
                batch_for_shader(shader, 'LINES', {'pos': pontos}).draw(shader)
    finally:
        gpu.state.line_width_set(1)
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('NONE')


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
    return (_opcao('tecla_corrente') == 'SEMPRE'
            or _tecla_corrente_segurada[0])


def _folga_atual(C, ponta, N):
    """(folga em m, eixo u, extremo de C em u) entre a ponta `ponta` de
    C e a face memorizada do vizinho N, na geometria de AGORA."""
    eixo, lado = ponta.split('_')
    ex, ey, _ez = _eixos(C)
    u = ex if eixo == 'x' else ey
    hx, hy, _hz = _meias(C)
    h = hx if eixo == 'x' else hy
    extremo = _centro(C).dot(u) + (h if lado == 'pos' else -h)
    face = int(C.get('adj_%s_face' % ponta, 0 if lado == 'pos' else 1))
    return abs(_faixa(N, u)[face] - extremo), u, extremo


def _assinatura_canto(C, p):
    """Qual canto de C e' o ponto p, pelo SINAL no referencial da chapa
    ('+-+'): estavel quando a chapa muda de medida ou de lugar."""
    local = C.matrix_world.inverted() @ p
    return ''.join('+' if v > 0 else '-' for v in local)


def _canto_da_assinatura(C, assinatura):
    """Inverso de `_assinatura_canto`: o canto de C em mundo."""
    meias = _meias(C)
    local = Vector([(1 if s == '+' else -1) * m
                    for s, m in zip(assinatura, meias)])
    return C.matrix_world @ local


def _pares_da_ligacao(C, u, extremo, N):
    """Os 2 pares (vertice de C, vertice de N, assinatura) da ligacao:
    cada canto da ponta de C com o canto mais perto de N; ficam os dois
    mais curtos (de um lado e do outro da junta)."""
    ponta = [p for p in _cantos(C) if abs(p.dot(u) - extremo) < 1e-5]
    cantos_n = _cantos(N)
    pares = [(p, min(cantos_n, key=lambda q: (q - p).length)) for p in ponta]
    pares.sort(key=lambda par: (par[1] - par[0]).length)
    return [(p, q, _assinatura_canto(C, p)) for p, q in pares[:2]]


def _vizinho_da_ponta(C, ponta):
    nome = C.get('adj_' + ponta, '')
    uid = C.get('adj_%s_uid' % ponta, '')
    if not nome and not uid:
        return None
    N = _resolver_vizinho(C, uid, nome)
    return None if N is C else N


def _ligados_a(C):
    """Pecas ligadas a C pela adjacencia, em qualquer sentido."""
    ligados = {N for N in (_vizinho_da_ponta(C, p) for p in PONTAS) if N}
    for X in bpy.data.objects:
        if X is not C and MARCA_CHAPA in X and any(
                _vizinho_da_ponta(X, p) == C for p in PONTAS):
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
        if C.type != 'MESH' or MARCA_CHAPA not in C:
            continue
        for ponta in PONTAS:
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
    if (not _correntes_visiveis() or not _contexto_hud(context)
            or _eh_area_gaveta(context) or _conexao_manual[0] is not None):
        return []
    if getattr(context, 'region_data', None) is None:
        return []
    chapas = [c for _o, _m, pecas in _itens_hud(context) for c in pecas]
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
                              'meio': _projetar_hud(context, (p + q) / 2)})
    return correntes


RAIO_BOLINHA_PX = 9.0
_bolinha_hover = [None]          # (chapa, ponta, indice, lado) sob o mouse


def _bolinhas_da_corrente(context, corrente):
    """{'a': ponto na tela do vertice da chapa, 'b': do vertice alvo}."""
    p, q = corrente['pontos']
    return {lado: ponto for lado, ponto in (
        ('a', _projetar_hud(context, p)), ('b', _projetar_hud(context, q)))
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
    grupo, indice = _canto_porta_sob_mouse(context, posicao)
    if grupo is not None:
        ponto = _projetar_hud(context, _cantos_da_porta(grupo)[indice])
        candidatos.append(((ponto - mouse).length / (RAIO_BOLINHA_PX * escala),
                           'canto_porta', grupo, indice))
    grupo, tipo = _controle_ferragem_sob_mouse(context, posicao)
    if grupo is not None:
        ponto = next(_projetar_hud(context, c[1])
                     for c in _controles_ferragens(grupo, {tipo}))
        candidatos.append(((ponto - mouse).length / (RAIO_BOLINHA_PX * escala),
                           'ferragem', grupo, tipo))
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
        for ponta in PONTAS:
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
        reposicionar_origem(modulo)
        sincronizar_medidas_conjunto(modulo)
        atualizar_portas_do_conjunto(modulo)
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
    modulo = _modulo_da_chapa(C)
    if modulo is not None:
        mundo = C.matrix_world.copy()
        C.parent = None
        C.matrix_world = mundo
        # fora do armario, na RAIZ da cena (pedido do usuario)
        _mover_para_colecao(C, bpy.context.scene.collection)
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
            colecao = _colecao_do_modulo(modulo)
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
    eixos = _eixos(C)
    meias = _meias(C)
    centro = _centro(C)
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
    _ocupado[0] = True
    try:
        C.chapa_largura_mm, C.chapa_comprimento_mm = medidas
    finally:
        _ocupado[0] = False
    _definir_centro(C, centro + deslocamento)
    gerar_malha_chapa(C)
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
        modulo = next((m for m in (_modulo_da_chapa(N) for N in pecas)
                       if m is not None), None)
        if modulo is not None and _modulo_da_chapa(C) != modulo:
            mundo = C.matrix_world.copy()
            C.parent = modulo
            C.matrix_parent_inverse = modulo.matrix_world.inverted()
            C.matrix_world = mundo
            pecas |= set(_chapas_do_conjunto(modulo))
            bpy.context.view_layer.update()
            associar_por_distancia(C, pecas)
            _atualizar_modulo(modulo)
            return
    associar_por_distancia(C, pecas)


def _alvos_por_distancia(C, candidatos=None):
    """(alvos, pecas) da conexao por distancia: cada ponta de C ao alcance
    de um vizinho vai so' ATE' a face dele (fecha a folga, nao desliza).
    `candidatos` limita os vizinhos aos alvos selecionados."""
    outras = _chapas_candidatas(C, candidatos)
    alvos, pecas = [], set()
    eixos = _eixos(C)
    for i, eixo in enumerate(("x", "y")):
        for lado in ("pos", "neg"):
            achado = _melhor_vizinho(C, eixo, lado, outras,
                                     ALCANCE_CONEXAO_AUTOMATICA)
            if achado is None:
                continue
            N, folga, _face = achado
            pecas.add(N)
            u = eixos[i] * (1 if lado == "pos" else -1)
            for p in _cantos(C):
                s = _assinatura_canto(C, p)
                if s[i] == ('+' if lado == "pos" else '-'):
                    alvos.append((s, p + u * folga))
    return alvos, pecas | _vizinhos_por_distancia(C, candidatos=candidatos)


# As letras somem quando o item fica menor na tela que FATOR x o tamanho
# do rotulo: de longe, L/A/P empilhavam numa caixa de poucos pixels.
FATOR_ROTULO_HUD = 4.0
# Seta guia em pixels de tela (x ui_scale): fixa, nao depende da aresta
COMPRIMENTO_SETA_HUD = 90
ASA_SETA_HUD = 12


def _tamanho_na_tela(context, geometria):
    """Maior aresta de medida do item, em pixels de tela."""
    maior = 0.0
    for linha in geometria['linhas']:
        if linha['tipo'] != 'medida':
            continue
        a = _projetar_hud(context, linha['pontos'][0])
        b = _projetar_hud(context, linha['pontos'][-1])
        if a is not None and b is not None:
            maior = max(maior, (b - a).length)
    return maior


def _rotulos_cabem(context, geometria):
    escala = max(1.0, context.preferences.system.ui_scale)
    limite = FATOR_ROTULO_HUD * _opcao('hud_tamanho_rotulo') * escala
    return _tamanho_na_tela(context, geometria) >= limite


def _para_fora(ponto, centro, distancia):
    direcao = ponto - centro
    if direcao.length < 1e-6:
        direcao = Vector((0.0, 1.0))
    return ponto + direcao.normalized() * distancia


def _rotulos_hud(context, geometria, alvo):
    """[(letra, centro do texto na tela, aceso)].

    Cada letra vai para a aresta do seu eixo que esta' mais FORA na tela
    e e' empurrada para longe do centro da peca: sobre a propria aresta,
    numa chapa vista de cima, a letra caia em cima da face. Letras que
    se encostam andam mais para fora, cada uma na sua direcao.
    """
    escala = max(1.0, context.preferences.system.ui_scale)
    tamanho = _opcao('hud_tamanho_rotulo') * escala
    cantos = [p for p in (_projetar_hud(context, c)
                          for c in geometria['cantos']) if p is not None]
    if not cantos:
        return []
    centro = sum(cantos, Vector((0.0, 0.0))) / len(cantos)
    afastar = 8 * escala + tamanho * 0.7
    # longe demais: so' a letra acesa (hover/digitacao) continua
    cabem = _rotulos_cabem(context, geometria)
    rotulos = []
    for letra in ('L', 'A', 'P', 'E'):
        candidatos = []
        for linha in geometria['linhas']:
            if linha.get('letra') != letra:
                continue
            ponto = _projetar_hud(context, sum(linha['pontos'], Vector()) / 2)
            if ponto is not None:
                candidatos.append((ponto, linha))
        if candidatos:
            ponto, linha = max(candidatos,
                               key=lambda item: (item[0] - centro).length)
            aceso = _identidade_hud(linha) == _identidade_hud(alvo)
            if cabem or aceso:
                rotulos.append([letra, _para_fora(ponto, centro, afastar),
                                aceso])
    if alvo and alvo['tipo'] == 'espessura':
        rotulos = [r for r in rotulos if r[0] != 'E']
        ponto = _projetar_hud(context, sum(alvo['pontos'][:-1], Vector()) /
                              (len(alvo['pontos']) - 1))
        if ponto is not None:
            rotulos.append(['E', _para_fora(ponto, centro, afastar), True])
    minimo = tamanho * 1.3
    for i, rotulo in enumerate(rotulos):
        for _tentativa in range(12):
            if all((rotulo[1] - outro[1]).length >= minimo
                   for outro in rotulos[:i]):
                break
            rotulo[1] = _para_fora(rotulo[1], centro, minimo * 0.5)
    return [tuple(r) for r in rotulos]


def _desenhar_hud_texto():
    context = bpy.context
    if not _contexto_hud(context):
        return
    # porta selecionada nao tem HUD de medida, mas tem os 4 cantos e o
    # slider de abertura de cada folha; ferragens selecionadas, o realce
    _desenhar_ferragens_selecionadas(context)
    _desenhar_cantos_porta(context)
    _desenhar_sliders_porta(context)
    desenhos = _desenhos_hud(context)
    if not desenhos:
        return
    cor = _cor_linhas_hud(context)
    realce = _cor_realce_hud()
    escala = context.preferences.system.ui_scale
    tamanho = _opcao('hud_tamanho_rotulo') * escala
    edicao = _edicao_hud[0]
    nesta = edicao is not None and edicao['regiao'] == context.region.as_pointer()
    digitando = nesta and edicao.get('texto') is not None
    if digitando:
        edicao['caixas'] = []
    try:
        for geometria, alvo in desenhos:
            for letra, ponto, aceso in _rotulos_hud(context, geometria, alvo):
                blf.size(0, tamanho)
                # o ponto e' o CENTRO da letra (ja' fora da peca)
                largura_letra, altura_letra = blf.dimensions(0, letra)
                x, y = ponto.x - largura_letra / 2, ponto.y - altura_letra / 2
                blf.position(0, x, y, 0)
                blf.color(0, *(_cor_realce_hud(letra) if aceso else cor))
                blf.draw(0, letra)
                if digitando and aceso:
                    # O valor sai da PROPRIA letra, numa caixa preta com
                    # texto branco: repetir "L:" em outra cor ao lado so'
                    # poluia e sumia contra o fundo.
                    x_texto = x + blf.dimensions(0, letra)[0] + 6 * escala
                    # guardada para o clique DENTRO da caixa mover o cursor
                    edicao.setdefault('caixas', []).append(
                        (x_texto, y, tamanho, escala))
                    _caixa_texto_hud(x_texto, y, _com_cursor(
                        edicao['texto'], edicao.get('cursor', len(edicao['texto']))),
                        tamanho, escala)
            if alvo and alvo.get('lado'):
                _desenhar_seta_hud(context, alvo, geometria)
        _desenhar_bolinhas_correntes(context)
        alvo = _realce_hud(context)
        if alvo and alvo['tipo'] == 'ancora':
            ponto = _projetar_hud(context, alvo['pontos'][0])
            if ponto is not None:
                raio = RAIO_CANTO_HUD * context.preferences.system.ui_scale
                circulo = [(ponto.x + raio * math.cos(i*math.tau/32),
                            ponto.y + raio * math.sin(i*math.tau/32)) for i in range(33)]
                gpu.state.blend_set('ALPHA')
                gpu.state.line_width_set(2.5)
                shader = gpu.shader.from_builtin('UNIFORM_COLOR')
                shader.bind()
                shader.uniform_float('color', realce)
                batch_for_shader(shader, 'LINE_STRIP', {'pos': circulo}).draw(shader)
    finally:
        gpu.state.line_width_set(1)
        gpu.state.point_size_set(1)
        gpu.state.blend_set('NONE')


def _cor_tema_linha():
    return tuple(bpy.context.preferences.themes[0]
                 .user_interface.wcol_regular.text)[:3]


def _cor_opcao(nome):
    """RGB que a opcao de cor esta' mostrando (o tema ja' resolvido)."""
    if nome == 'hud_rgb_linha' and _opcao('hud_linha_tema'):
        return _cor_tema_linha()
    return tuple(_opcao(nome))[:3]


def _cor_linhas_hud(context):
    return (*_cor_opcao('hud_rgb_linha'), 1.0)


# Medida -> eixo do gizmo: largura X, profundidade Y, altura Z
EIXO_GIZMO_DA_LETRA = {'L': 'axis_x', 'P': 'axis_y', 'A': 'axis_z'}
EIXOS_GIZMO_PADRAO = {'axis_x': (1.0, 0.2, 0.32), 'axis_y': (0.54, 0.86, 0.0),
                      'axis_z': (0.16, 0.56, 1.0)}


def _cor_eixo_gizmo(eixo):
    """Cor do eixo no tema do usuario -- a mesma do gizmo nativo."""
    try:
        return tuple(getattr(bpy.context.preferences.themes[0]
                             .user_interface, eixo))[:3]
    except Exception:
        return EIXOS_GIZMO_PADRAO[eixo]


def _cor_realce_hud(letra=''):
    """Cor do que esta' aceso. Com o realce do gizmo, cada medida pinta
    na cor do eixo dela; espessura e o resto (quina, gap) ficam laranja."""
    if _opcao('hud_realce_gizmo'):
        eixo = EIXO_GIZMO_DA_LETRA.get(letra)
        return (*(_cor_eixo_gizmo(eixo) if eixo else COR_REALCE_PADRAO), 1.0)
    return (*_cor_opcao('hud_rgb_realce'), 1.0)


def _letra_do_alvo(alvo):
    if not alvo:
        return ''
    return 'E' if alvo['tipo'] == 'espessura' else alvo.get('letra', '')


def _caixa_texto_hud(x, y, texto, tamanho, escala):
    """Texto branco numa caixa preta: legivel contra qualquer fundo."""
    blf.size(0, tamanho)
    largura = blf.dimensions(0, texto)[0]
    altura = blf.dimensions(0, '0')[1]
    folga = 4 * escala
    x0, y0 = x - folga, y - folga
    x1, y1 = x + largura + folga, y + altura + folga
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float('color', (0.0, 0.0, 0.0, 0.88))
    batch_for_shader(shader, 'TRIS', {'pos': [
        (x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1), (x0, y1)]}).draw(shader)
    blf.position(0, x, y, 0)
    blf.color(0, 1.0, 1.0, 1.0, 1.0)
    blf.draw(0, texto)


def _desenhar_seta_hud(context, alvo, geometria):
    """Seta guia: sai da quina que fica parada e aponta para onde o
    movel vai crescer (estilo Promob). Desenhada em pixels, entao tem o
    mesmo tamanho de qualquer distancia.

    As pontas saem da geometria ATUAL (indices dos cantos), nao dos
    pontos guardados no hover: estes ficam para tras quando o movel
    muda de tamanho ou de lugar.
    """
    i, j = alvo.get('cantos', (None, None))
    if i is None or alvo['objeto'] != geometria['objeto']:
        return
    cantos = geometria['cantos']
    fixa, livre = (cantos[i], cantos[j]) if alvo['lado'] == 'min' else (cantos[j], cantos[i])
    a = _projetar_hud(context, fixa)
    b = _projetar_hud(context, livre)
    if a is None or b is None or (b - a).length < 1:
        return
    escala = max(1.0, context.preferences.system.ui_scale)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float('color', _cor_realce_hud(_letra_do_alvo(alvo)))
    batch_for_shader(shader, 'TRIS',
                     {'pos': _triangulos_seta_hud(a, b, escala)}).draw(shader)


def _triangulos_seta_hud(a, b, escala):
    """Ponto na quina parada, haste e ponta, tudo em triangulos.

    COMPRIMENTO_SETA_HUD e' o TETO, na tela: a seta nunca passa da
    propria aresta (pedido do usuario -- na E de 18 mm ela saia muito
    alem da chapa). Encolhendo, ponta, haste e ponto encolhem junto, sem
    a ponta comer a seta inteira. Limitar a uma FRACAO da aresta (45%)
    ja' foi tentado e a seta sumia; aqui ela vai ate' a aresta toda.
    Haste e ponto nao usam line_width / point_size, que o driver pode
    travar em 1 px.
    """
    direcao = (b - a).normalized()
    lateral = Vector((-direcao.y, direcao.x))
    cheio = COMPRIMENTO_SETA_HUD * escala
    comprimento = min(cheio, (b - a).length)
    ponta = a + direcao * comprimento
    # ponta: no maximo 45% da seta; haste e ponto acompanham a asa
    asa = min(ASA_SETA_HUD * escala, comprimento * 0.45 / 1.6)
    base = ponta - direcao * asa * 1.6
    meia = min(2.5 * escala, asa * 0.4)
    tris = [a + lateral * meia, base + lateral * meia, base - lateral * meia,
            a + lateral * meia, base - lateral * meia, a - lateral * meia,
            ponta, base + lateral * asa, base - lateral * asa]
    raio = min(6 * escala, asa * 0.5)
    volta = [a + Vector((math.cos(i * math.tau / 20),
                         math.sin(i * math.tau / 20))) * raio
             for i in range(21)]
    for p, q in zip(volta, volta[1:]):
        tris += [a, p, q]
    return tris


class VIEW3D_GT_hud_cabinet(Gizmo):
    """Captura apenas os contornos, cantos e faces interativos da HUD."""
    bl_idname = 'VIEW3D_GT_hud_cabinet'

    def draw(self, context):
        pass

    def test_select(self, context, location):
        if not _contexto_hud(context):
            return -1
        if _slider_sob_mouse(context, location) is not None:
            return -1       # a bolinha do slider de abertura e' de outro gizmo
        # Sobre uma corrente o clique e' DELE (outro gizmo): a quina e as
        # linhas da HUD ficam embaixo e nao podem roubar o pick.
        alvo_corrente = _alvo_da_corrente(context, location)
        corrente = alvo_corrente[1] if alvo_corrente else None
        bolinha = (_chave_bolinha(corrente, alvo_corrente[2])
                   if alvo_corrente and alvo_corrente[0] == 'bolinha' else None)
        if bolinha != _bolinha_hover[0]:
            _bolinha_hover[0] = bolinha
            context.area.tag_redraw()
        alvo = (None if corrente is not None
                else _acertar_hud(context, location))
        chave = context.region.as_pointer()
        antes = _hover_hud.get(chave)
        # O lado entra a parte: ele muda a SETA, mas nao o realce das
        # quatro arestas, que depende so' da identidade.
        if (_identidade_hud(alvo) != _identidade_hud(antes)
                or (alvo or {}).get('lado') != (antes or {}).get('lado')):
            _hover_hud[chave] = alvo
            context.area.tag_redraw()
        return 0 if alvo else -1


class VIEW3D_GGT_hud_cabinet(GizmoGroup):
    bl_idname = 'VIEW3D_GGT_hud_cabinet'
    bl_label = 'Medidas espaciais Cabinet Creator'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        return (_contexto_hud(context) and bool(_itens_hud(context))
                and not _apanhando_vao[0])

    def setup(self, context):
        self.hud = self.gizmos.new('VIEW3D_GT_hud_cabinet')
        self.hud.use_tooltip = False
        self.hud.target_set_operator('object.cabinet_arrastar_hud')

    def draw_prepare(self, context):
        if not self.hud.is_highlight and _edicao_hud[0] is None:
            _hover_hud.pop(context.region.as_pointer(), None)


class VIEW3D_GGT_correntes_cabinet(GizmoGroup):
    """Corrente no meio de cada ligacao de adjacencia cujas pecas se
    separaram: botao nativo (icone do tema, tooltip, hover) em pixels."""
    bl_idname = 'VIEW3D_GGT_correntes_cabinet'
    bl_label = 'Correntes de adjacencia Cabinet Creator'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'SCALE'}

    @classmethod
    def poll(cls, context):
        return (_contexto_hud(context) and not _eh_area_gaveta(context)
                and _alvo_hud(context) is not None and not _apanhando_vao[0]
                and _edicao_hud[0] is None)

    def setup(self, context):
        self.botoes = []

    def draw_prepare(self, context):
        # dois botoes por quina: corrente (desagrega) e regua (resetar)
        botoes = [(corrente, tipo, centro)
                  for corrente in _correntes_hud(context)
                  for tipo, centro in _botoes_da_corrente(context, corrente).items()]
        while len(self.botoes) < len(botoes):
            botao = self.gizmos.new('GIZMO_GT_button_2d')
            botao.draw_options = {'BACKDROP', 'OUTLINE'}
            botao.use_tooltip = True
            self.botoes.append(botao)
        realce = _cor_realce_hud()
        for botao in self.botoes:
            botao.hide = True
        for botao, (corrente, tipo, centro) in zip(self.botoes, botoes):
            botao.hide = False
            botao.icon = 'LINKED' if tipo == 'corrente' else 'DRIVER_DISTANCE'
            botao.scale_basis = RAIO_CORRENTE_PX
            botao.color = realce[:3]
            botao.alpha = 0.85
            botao.color_highlight = realce[:3]
            botao.alpha_highlight = 1.0
            botao.matrix_basis[0][3] = centro.x
            botao.matrix_basis[1][3] = centro.y
            if tipo == 'corrente':
                op = botao.target_set_operator('object.cabinet_desassociar')
                op.chapa = corrente['a'].name
            else:
                op = botao.target_set_operator(OP_RESETAR_DISTANCIA)
                op.chapa = corrente['movel'].name


class OBJECT_OT_desassociar(Operator):
    """Desagrega esta peca: todas as quinas dela se soltam e ela sai do modulo"""
    bl_idname = 'object.cabinet_desassociar'
    bl_label = 'Desagregar'
    bl_options = {'REGISTER', 'UNDO'}

    chapa: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        chapa = bpy.data.objects.get(self.chapa)
        if chapa is None or MARCA_CHAPA not in chapa:
            self.report({'WARNING'}, 'Peca nao encontrada')
            return {'CANCELLED'}
        if not agregado(chapa) and _modulo_da_chapa(chapa) is None:
            self.report({'INFO'}, "Esta peca ja' estava desagregada")
            return {'CANCELLED'}
        desagregar(chapa)
        _redesenhar_viewports(context)
        return {'FINISHED'}


def _redesenhar_viewports(context):
    for area in context.screen.areas if context.screen else ():
        if area.type == 'VIEW_3D':
            area.tag_redraw()


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
        return _correntes_visiveis() and _contexto_hud(context)

    def invoke(self, context, event):
        posicao = (event.mouse_region_x, event.mouse_region_y)
        alvo = _alvo_da_corrente(context, posicao)
        if alvo is None:
            return {'PASS_THROUGH'}
        tipo_alvo, corrente, tipo = alvo
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
            _redesenhar_viewports(context)
            return {'FINISHED'}
        desagregar(corrente['a'])
        _redesenhar_viewports(context)
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
        if self.tecla.split('_', 1)[-1] == _opcao('tecla_corrente'):
            if _tecla_corrente_segurada[0] != self.apertou:
                _tecla_corrente_segurada[0] = self.apertou
                _redesenhar_viewports(context)
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
            if o.type == 'MESH' and MARCA_CHAPA in o]


def _acao_corrente(context, medir=True):
    """(acao, peca, pecas) do botao Corrente pela selecao, ou None:
    ('grupo', None, pecas do grupo), ('desagregar', peca, [peca]),
    ('conectar', peca de fora, alvos ao alcance) ou ('vertices', peca,
    alvos -- vazio = qualquer chapa). Sem `medir` nao procura vizinhos
    (o desenho da gaveta so' precisa saber se e' azul ou cinza)."""
    selecionados = list(getattr(context, 'selected_objects', ()) or ())
    chapas = [o for o in selecionados if o.type == 'MESH' and MARCA_CHAPA in o]
    ativo = getattr(context, 'active_object', None)
    if ativo is not None and ativo not in selecionados:
        ativo = None
    if ativo is None and len(chapas) == 1:
        ativo = chapas[0]
    if ativo is None or (MARCA_CHAPA not in ativo and MARCA_CONJUNTO not in ativo):
        return None
    modulo = ativo if MARCA_CONJUNTO in ativo else _modulo_da_chapa(ativo)
    grupo = set(familia_de(ativo))
    if modulo is not None:
        grupo |= set(_chapas_do_conjunto(modulo))
    alvos = [c for c in chapas if c not in grupo]
    if alvos:
        if MARCA_CHAPA not in ativo:
            return None          # quem vai ate' o alvo e' UMA peca, nao um modulo
        if not medir:
            return ('conectar', ativo, alvos)
        _pontos, perto = _alvos_por_distancia(ativo, alvos)
        if perto:
            return ('conectar', ativo, alvos)
        return ('vertices', ativo, alvos)
    if MARCA_CHAPA in ativo and chapas == [ativo] and not any(
            MARCA_CONJUNTO in o for o in selecionados):
        if agregado(ativo) or modulo is not None:
            return ('desagregar', ativo, [ativo])
        return ('vertices', ativo, [])
    pecas = (_chapas_do_conjunto(modulo) if modulo is not None
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


def _abrir_pergunta(context):
    """Pop-up so' com janela: em --background o popup_menu derruba o
    Blender (EXCEPTION_ACCESS_VIOLATION). A resposta pendente fica gravada
    do mesmo jeito -- e' assim que os testes respondem."""
    return not bpy.app.background and getattr(context, 'window', None)


# ------------------------------------------------------- perguntas
# REGRA DE DESIGN (pedido do usuario, vale para tudo daqui em diante):
# pop-up SO' quando a acao veio da VIEWPORT (atalho, Alt+corrente/regua,
# Enter no modo de vertices). Veio de um botao da GAVETA: a pergunta
# aparece DENTRO dela, logo abaixo do botao, numa caixa preta
# (`_pergunta_na_gaveta`). Toda confirmacao passa por `_perguntar`.
_pergunta_atual = [None]   # {'texto', 'opcoes': [(rotulo, icone, op, props)], 'na_gaveta'}
_na_gaveta = [False]       # True enquanto a gaveta trata um clique


def _menu_pergunta(self, context):
    pergunta = _pergunta_atual[0]
    if pergunta is None:
        return
    for i, (rotulo, icone, _op, _props) in enumerate(pergunta['opcoes']):
        op = self.layout.operator('object.cabinet_responder_pergunta',
                                  text=rotulo, icon=icone)
        op.opcao = i


def _perguntar(context, texto, opcoes, na_gaveta=None):
    """Faz a pergunta no lugar certo: na gaveta (caixa preta) se o clique
    veio dela, em pop-up se veio da viewport."""
    na_gaveta = _na_gaveta[0] if na_gaveta is None else na_gaveta
    _pergunta_atual[0] = {'texto': texto, 'opcoes': list(opcoes),
                          'na_gaveta': bool(na_gaveta)}
    if na_gaveta:
        _redesenhar_viewports(context)
    elif _abrir_pergunta(context):
        context.window_manager.popup_menu(_menu_pergunta, title=texto,
                                          icon='QUESTION')


class OBJECT_OT_responder_pergunta(Operator):
    """Responde a pergunta pendente (caixa da gaveta ou pop-up)"""
    bl_idname = 'object.cabinet_responder_pergunta'
    bl_label = 'Responder'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    opcao: IntProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        pergunta, _pergunta_atual[0] = _pergunta_atual[0], None
        _redesenhar_viewports(context)
        if pergunta is None or not 0 <= self.opcao < len(pergunta['opcoes']):
            return {'CANCELLED'}
        _rotulo, _icone, idname, props = pergunta['opcoes'][self.opcao]
        modulo, nome = idname.split('.')
        resultado = getattr(getattr(bpy.ops, modulo), nome)(
            'EXEC_DEFAULT', **props)
        return {'FINISHED'} if 'FINISHED' in resultado else {'CANCELLED'}


def _perguntar_desagregar(context, pecas, todos):
    _desagregar_pendente[0] = sorted(o.name for o in pecas)
    op = 'object.cabinet_desagregar_selecao'
    _perguntar(context, PERGUNTA_DESAGREGAR_GRUPO if todos
               else PERGUNTA_DESAGREGAR_OBJETO,
               [('Sim, desagregar', 'CHECKMARK', op, {'desagregar': True}),
                ('Nao', 'X', op, {'desagregar': False})])


def _agrupar_soltas(context, C, pecas):
    """A Corrente juntou pecas que nao estao em armario nenhum: viram um
    GRUPO (pedido do usuario). Com armario de um lado, quem manda e' o
    "Juntar ao modulo?" -- aqui nada acontece. Devolve o grupo ou None."""
    pecas = {N for N in pecas if N is not None and MARCA_CHAPA in N}
    if (C is None or not pecas or _modulo_da_chapa(C) is not None
            or any(_modulo_da_chapa(N) is not None for N in pecas)):
        return None
    todas = {C} | pecas | set(grupo_de(C, simetrico=True))
    return agrupar_chapas(context, sorted(todas, key=lambda o: o.name))


# Caixa do nome na gaveta: o grupo ja' nasceu com a sugestao; o texto
# digitado aqui o renomeia (Enter/OK) ou fica a sugestao (Esc/Manter).
_nome_grupo_gaveta = [None]     # {'grupo', 'texto', 'cursor', 'selecionado'}


def _abrir_caixa_nome(conj):
    _nome_grupo_gaveta[0] = {'grupo': conj.name, 'texto': conj.name,
                             'cursor': len(conj.name), 'selecionado': True}
    _pergunta_atual[0] = {
        'texto': 'Nome do grupo', 'campo': True, 'na_gaveta': True,
        'opcoes': [('OK', 'CHECKMARK', 'object.cabinet_nomear_grupo',
                    {'digitado': True}),
                   ('Manter', 'X', 'object.cabinet_nomear_grupo',
                    {'manter': True})]}


def _pedir_nome_grupo(context, conj, na_gaveta=None):
    """Pergunta o nome do grupo novo no lugar certo: caixa com campo
    DENTRO da gaveta se o clique veio dela, pop-up se veio da viewport."""
    na_gaveta = _na_gaveta[0] if na_gaveta is None else na_gaveta
    if na_gaveta:
        _abrir_caixa_nome(conj)
        if _abrir_pergunta(context):
            bpy.ops.object.cabinet_digitar_nome_grupo('INVOKE_DEFAULT')
        _redesenhar_viewports(context)
    elif _abrir_pergunta(context):
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
        _redesenhar_viewports(context)
        if self.manter:
            return {'FINISHED'}
        if not nomear_grupo(bpy.data.objects.get(self.grupo), self.nome):
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
        _redesenhar_viewports(context)

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
            _nome_grupo_gaveta[0] = _pergunta_atual[0] = None
            self._redesenhar(context)
            return {'CANCELLED'}
        if event.type in {'RET', 'NUMPAD_ENTER'}:
            _nome_grupo_gaveta[0] = _pergunta_atual[0] = None
            _confirmar_campo_gaveta(estado)
            self._redesenhar(context)
            return {'FINISHED'}
        entrada = (context.window_manager.clipboard
                   if event.ctrl and event.type == 'V'
                   else '' if event.ctrl else event.unicode or '')
        if _tecla_no_texto(estado, event.type, entrada, event.ctrl):
            self._redesenhar(context)
        return {'RUNNING_MODAL'}


def _perguntar_juntar(context, origem, alvos, pecas, na_gaveta=None):
    _conexao_pendente[0] = {'origem': origem.name,
                            'alvos': [(s, tuple(q)) for s, q in alvos],
                            'pecas': sorted(o.name for o in pecas)}
    op = 'object.cabinet_juntar_modulo'
    _perguntar(context, 'Juntar ao modulo?',
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
                 if o is not None and MARCA_CHAPA in o]
        if not pecas:
            return {'CANCELLED'}
        n = desagregar_grupo(pecas)
        self.report({'INFO'}, '%d peca(s) desagregada(s)' % n)
        _redesenhar_viewports(context)
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
        modulo = next((m for m in (_modulo_da_chapa(N) for N in pecas)
                       if m is not None), None)
        if modulo is not None and _modulo_da_chapa(chapa) != modulo:
            _perguntar_juntar(context, chapa, alvos, pecas)
        else:
            associar_por_distancia(chapa, pecas, ALCANCE_CONEXAO_AUTOMATICA)
            conj = _agrupar_soltas(context, chapa, pecas)
            if conj is not None:
                _pedir_nome_grupo(context, conj)
        _redesenhar_viewports(context)
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
        _redesenhar_viewports(context)
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
        _conexao_manual[0]['pela_gaveta'] = _na_gaveta[0]
        _redesenhar_viewports(context)
        return {'FINISHED'}


def _desenhar_conexao_manual():
    """Cantos clicaveis, o escolhido e as pontas ja' conectadas."""
    estado = _conexao_manual[0]
    regiao = getattr(bpy.context, 'region', None)
    if estado is None or regiao is None or regiao.as_pointer() != estado['regiao']:
        return
    rv3d = bpy.context.region_data
    realce = _cor_realce_hud()
    cor = _cor_linhas_hud(bpy.context)
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
                batch_for_shader(shader, 'TRIS', {'pos': _quad_2d(
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
                 if o is not origem and o.type == 'MESH' and MARCA_CHAPA in o
                 and o.visible_get()]
    return [(o, _assinatura_canto(o, p), p) for o in pecas for p in _cantos(o)]


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
        if chapa is None or MARCA_CHAPA not in chapa:
            self.report({'WARNING'}, 'Selecione a chapa de origem')
            return {'CANCELLED'}
        alvo = _viewport_alvo(context)
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
        _redesenhar_viewports(context)
        return {'RUNNING_MODAL'}

    def _encerrar(self, context):
        try:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
        except Exception:
            pass
        self._area.header_text_set(None)
        estado, _conexao_manual[0] = _conexao_manual[0], None
        _redesenhar_viewports(context)
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


def _bolinha_2d(shader, ponto, raio, rgba):
    volta = [ponto + Vector((math.cos(i * math.tau / 20),
                             math.sin(i * math.tau / 20))) * raio
             for i in range(21)]
    tris = []
    for a, b in zip(volta, volta[1:]):
        tris += [ponto, a, b]
    shader.uniform_float('color', rgba)
    batch_for_shader(shader, 'TRIS', {'pos': tris}).draw(shader)


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
    realce = _cor_realce_hud()
    for corrente in correntes:
        for lado, ponto in _bolinhas_da_corrente(context, corrente).items():
            acesa = _chave_bolinha(corrente, lado) == _bolinha_hover[0]
            if acesa:
                _bolinha_2d(shader, ponto, 8 * escala, realce)
            _bolinha_2d(shader, ponto, (6 if acesa else 5) * escala,
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
    realce = _cor_realce_hud()
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    tela = lambda p: view3d_utils.location_3d_to_region_2d(regiao, rv3d, p)
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        for _s, ponto in _candidatos_ancora(estado):
            p = tela(ponto)
            if p is not None:
                _bolinha_2d(shader, p, 4 * escala, (0.75, 0.75, 0.75, 0.9))
        fixo = tela(estado['fixo'])
        solto = estado['mouse']
        if estado.get('alvo'):
            solto = tela(dict(_candidatos_ancora(estado))[estado['alvo']]) or solto
        if fixo is not None:
            shader.uniform_float('color', realce)
            batch_for_shader(shader, 'TRIS', {'pos': _quad_2d(
                fixo, solto, 3.0 * escala)}).draw(shader)
            _bolinha_2d(shader, fixo, 5 * escala, (1.0, 1.0, 1.0, 1.0))
        _bolinha_2d(shader, solto, 8 * escala, realce)
        _bolinha_2d(shader, solto, 6 * escala, (1.0, 1.0, 1.0, 1.0))
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
            p = _projetar_hud(context, ponto)
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


# ------------------------------------------ os 4 cantos da porta
# Pedido do usuario: clique simples na porta mostra os fios do wizard
# (laranja = cobertura, branco = vao) e, com Alt, as 4 bolinhas viram
# alcas: arrastar um canto ate' outro vertice refaz a porta como se os
# 4 cliques tivessem sido dados ali (cobertura e dobradica automaticas).
# Os cantos nao sao gravados: saem da porta (vao + cobertura de cada
# lado), entao acompanham o modulo quando ele muda.
_arraste_canto_porta = [None]    # estado do arraste de um canto


def _porta_veio_do_modulo(grupo):
    """A porta esta' selecionada so' porque o MODULO dela esta' (clique nas
    chapas). Ai' nada da porta se desenha -- dobradicas, linhas do vao,
    diagonal, cantos, sliders (pedido do usuario: visao mais limpa); a
    HUD do modulo ja' mostra o contorno dela."""
    modulo = grupo.parent
    while modulo is not None and MARCA_CONJUNTO not in modulo:
        modulo = modulo.parent
    return modulo is not None and modulo.select_get()


def _portas_com_cantos(context):
    """Portas selecionadas INTEIRAS (clique simples, nao a folha) por si
    mesmas, nao junto com o modulo."""
    return [o for o in getattr(context, 'selected_objects', ()) or ()
            if MARCA_PORTAS in o and o.get('porta_parametros')
            and o.get('porta_vao_largura_mm') is not None
            and not _porta_veio_do_modulo(o)]


def _cantos_da_porta(grupo):
    """Os 4 pontos do wizard em MUNDO, na ordem dos cliques: canto da
    porta e do vao em cima a esquerda, do vao e da porta embaixo a
    direita (o desenho do usuario)."""
    p = grupo['porta_parametros']
    L = float(grupo['porta_vao_largura_mm'])
    A = float(grupo['porta_vao_altura_mm'])
    # o ponto CLICADO (meio da espessura), nao a borda da folha: a meia
    # chapa recua o respiro, e o canto arrastado com Alt tem de reconhecer
    # a meia de novo
    padrao = (0.0 if p.get('abertura') == 'CORRER' else
              {'RETA': 1.0, 'CURVA': 0.5}.get(p.get('dobradica'), 0.0))
    lateral = float(p['lateral_mm'])
    cob = [float(p[k]) * lateral if k in p else padrao * lateral
           for k in COBERTURAS_LADOS]
    m = grupo.matrix_world
    return [m @ (Vector((x, y, 0.0)) / 1000.0) for x, y in (
        (-cob[0], A + cob[3]), (0.0, A), (L, 0.0), (L + cob[1], -cob[2]))]


def _coberturas_da_porta(grupo):
    p = grupo.get('porta_parametros') or {}
    return {k: float(p[k]) for k in COBERTURAS_LADOS if k in p}


def _canto_porta_sob_mouse(context, posicao):
    """(grupo, indice) da bolinha de canto sob o mouse (so' com Alt)."""
    if not _correntes_visiveis():
        return None, None
    raio = RAIO_BOLINHA_PX * max(1.0, context.preferences.system.ui_scale)
    mouse = Vector(posicao)
    melhor = None
    for grupo in _portas_com_cantos(context):
        for i, ponto in enumerate(_cantos_da_porta(grupo)):
            p = _projetar_hud(context, ponto)
            if p is None:
                continue
            d = (p - mouse).length
            if d <= raio and (melhor is None or d < melhor[0]):
                melhor = (d, grupo, i)
    return (melhor[1], melhor[2]) if melhor else (None, None)


COR_LINHAS_VAO = (1.0, 0.85, 0.1, 1.0)      # amarelo: o vao (pedido do usuario)


def _desenho_da_porta(grupo):
    """O que a porta selecionada mostra, em MUNDO: a caixa de cada folha
    e o retangulo do vao (faces internas das chapas). As ferragens nao:
    so' aparecem criando ou SELECIONADAS (`_caixas_ferragens`).
    Refeito da porta a cada desenho: acompanha o modulo."""
    p = dict(grupo['porta_parametros'])
    L = float(grupo['porta_vao_largura_mm'])
    A = float(grupo['porta_vao_altura_mm'])
    m = grupo.matrix_world
    mundo = lambda v: m @ (Vector(v) / 1000.0)
    desenho = {'folhas': [],
               'vao': [mundo((x, y, 0.0)) for x, y in
                       ((0, 0), (L, 0), (L, A), (0, A))]}
    try:
        folhas = _calcular_folhas_portas(L, A, p)
    except (ValueError, KeyError, TypeError):
        return desenho
    objetos = _folhas_portas(grupo)
    for i, (l, alt, e, centro) in enumerate(folhas):
        meia = Vector((l, alt, e)) / 2000.0
        # pela folha de verdade: o contorno abre junto com ela
        matriz = (objetos[i].matrix_world if i < len(objetos)
                  else m @ Matrix.Translation(Vector(centro) / 1000.0))
        desenho['folhas'].append([matriz @ Vector((meia.x * sx, meia.y * sy,
                                                   meia.z * sz))
                                  for sx in (-1, 1) for sy in (-1, 1)
                                  for sz in (-1, 1)])
    return desenho


def _desenhar_caixas_2d(context, shader, caixas, cor, escala):
    """Volume de ferragem em realce: faces translucidas + arestas (o
    mesmo desenho do wizard), por cima de tudo."""
    for caixa in caixas:
        tela = [_projetar_hud(context, v) for v in caixa]
        if any(v is None for v in tela):
            continue
        shader.uniform_float('color', (*cor[:3], 0.28))
        batch_for_shader(shader, 'TRIS', {'pos': [
            tela[i] for q in FACES_CAIXA
            for i in (q[0], q[1], q[2], q[0], q[2], q[3])]}).draw(shader)
        shader.uniform_float('color', cor)
        for i, j in ARESTAS_CAIXA:
            batch_for_shader(shader, 'TRIS', {'pos': _quad_2d(
                tela[i], tela[j], 1.2 * escala)}).draw(shader)


def _desenhar_cantos_porta(context):
    """Porta selecionada (print do usuario): contorno branco das folhas,
    linhas internas do vao em amarelo, os fios dos 4 cantos e, com Alt
    (ou arrastando), as 4 bolinhas brancas. As dobradicas nao (pedido do
    usuario): so' criando ou com elas selecionadas."""
    portas = _portas_com_cantos(context)
    if not portas:
        return
    estado = _arraste_canto_porta[0]
    escala = max(1.0, context.preferences.system.ui_scale)
    realce = _cor_realce_hud()
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        for grupo in portas:
            desenho = _desenho_da_porta(grupo)
            contornos = [(caixa, ARESTAS_CAIXA, COR_FIO_VAO)
                         for caixa in desenho['folhas']]
            contornos.append((desenho['vao'], ((0, 1), (1, 2), (2, 3), (3, 0)),
                              COR_LINHAS_VAO))
            for pontos, arestas, cor in contornos:
                tela = [_projetar_hud(context, v) for v in pontos]
                if any(v is None for v in tela):
                    continue
                shader.uniform_float('color', cor)
                for i, j in arestas:
                    batch_for_shader(shader, 'TRIS', {'pos': _quad_2d(
                        tela[i], tela[j], 1.4 * escala)}).draw(shader)
            arrastando = estado is not None and estado['grupo'] == grupo.name
            pontos = estado['pontos'] if arrastando else _cantos_da_porta(grupo)
            tela = [_projetar_hud(context, p) for p in pontos]
            if any(p is None for p in tela):
                continue
            for i in range(3):
                shader.uniform_float('color', COR_FIO_VAO if i == 1
                                     else COR_FIO_COBERTURA)
                batch_for_shader(shader, 'TRIS', {'pos': _quad_2d(
                    tela[i], tela[i + 1], 2.0 * escala)}).draw(shader)
            if not (arrastando or _correntes_visiveis()):
                continue
            for i, p in enumerate(tela):
                aceso = arrastando and i == estado['indice']
                if aceso:
                    _bolinha_2d(shader, p, 8 * escala, realce)
                _bolinha_2d(shader, p, (6 if aceso else 5) * escala,
                            (1.0, 1.0, 1.0, 1.0))
            if arrastando and estado.get('alvo') is None:
                _bolinha_2d(shader, estado['mouse'], 4 * escala, realce)
    finally:
        gpu.state.blend_set('NONE')


def _dentro_da_porta(obj, grupo):
    while obj is not None:
        if obj == grupo:
            return True
        obj = obj.parent
    return False


def _mover_cantos_porta(context, grupo, pontos, objetos=(None,) * 4):
    """Refaz a porta pelos 4 pontos (mundo), como o wizard faria."""
    modulo = bpy.data.objects.get(grupo.get(CHAVE_MODULO_PORTA, ''))
    if modulo is not None and MARCA_CONJUNTO not in modulo:
        modulo = None
    referencia = (modulo.matrix_world.to_quaternion().to_matrix()
                  if modulo is not None else Matrix.Identity(3))
    valores = tuple(v for linha in referencia for v in linha)
    pai = modulo if modulo is not None else grupo.parent
    folha = (_folhas_portas(grupo) or [None])[0]
    resultado = bpy.ops.object.cabinet_portas(
        'EXEC_DEFAULT', capturado=True, grupo_alvo=grupo.name,
        ponto_a=pontos[1], ponto_b=pontos[2], quatro_pontos=True,
        porta_a=pontos[0], porta_b=pontos[3],
        objeto_a_nome=objetos[1].name if objetos[1] is not None else '',
        objeto_b_nome=objetos[2].name if objetos[2] is not None else '',
        referencia=valores, referencia_ativa=valores,
        pai_nome=pai.name if pai is not None else '',
        modulo_nome=modulo.name if modulo is not None else '',
        orientacao='AUTO', frente=grupo.get('porta_frente', 'NEG_Y'))
    # quem cria deixa o MODULO ativo; aqui a porta continua selecionada
    # para o usuario seguir ajustando
    folha = (_folhas_portas(grupo) or [folha])[0]
    if folha is not None:
        _selecionar_porta_hud(context, folha, 'PORTA')
    return resultado


def _aplicar_cantos_porta(context, grupo, pontos, objetos, antigos):
    """Arraste solto: refaz a porta e, se a cobertura sair do padrao,
    pergunta (viewport: pop-up). "Nao" volta os cantos de antes."""
    resultado = _mover_cantos_porta(context, grupo, pontos, objetos)
    if 'FINISHED' not in resultado:
        return resultado
    if _lados_fora_do_padrao(_coberturas_da_porta(grupo)):
        planos = tuple(v for p in antigos for v in p)
        _perguntar(context, 'As medidas estao corretas?', [
            ('Sim', 'CHECKMARK', 'object.cabinet_cantos_porta',
             {'grupo': grupo.name, 'manter': True}),
            ('Nao', 'X', 'object.cabinet_cantos_porta',
             {'grupo': grupo.name, 'pontos': planos})], na_gaveta=False)
    return resultado


class OBJECT_OT_cantos_porta(Operator):
    """Refaz a porta pelos 4 cantos (resposta do "As medidas estao corretas?")"""
    bl_idname = 'object.cabinet_cantos_porta'
    bl_label = 'Cantos da Porta'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    grupo: StringProperty(options={'SKIP_SAVE'})
    pontos: FloatVectorProperty(size=12, options={'SKIP_SAVE'})
    manter: BoolProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        grupo = bpy.data.objects.get(self.grupo)
        if grupo is None or MARCA_PORTAS not in grupo:
            return {'CANCELLED'}
        if self.manter:
            return {'FINISHED'}
        v = list(self.pontos)
        pontos = [Vector(v[i:i + 3]) for i in range(0, 12, 3)]
        return _mover_cantos_porta(context, grupo, pontos)


class OBJECT_OT_arrastar_canto_porta(Operator):
    """Arraste um dos 4 cantos da porta (Alt) ate' outro vertice: a porta se refaz por ele"""
    bl_idname = 'object.cabinet_arrastar_canto_porta'
    bl_label = 'Mover Canto da Porta'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    grupo: StringProperty(options={'SKIP_SAVE'})
    indice: IntProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        grupo = bpy.data.objects.get(self.grupo)
        if (grupo is None or MARCA_PORTAS not in grupo
                or not 0 <= self.indice < 4 or context.region is None):
            return {'CANCELLED'}
        # vertices lidos UMA vez (como no wizard); a propria porta nao
        # serve de ima para si mesma
        self._alvos = [(o, vs) for o, vs in _alvos_do_ima(context)
                       if not _dentro_da_porta(o, grupo)]
        self._antigos = _cantos_da_porta(grupo)
        _arraste_canto_porta[0] = {
            'regiao': context.region.as_pointer(), 'grupo': grupo.name,
            'indice': self.indice, 'pontos': list(self._antigos),
            'alvo': None, 'objeto': None,
            'mouse': Vector((event.mouse_region_x, event.mouse_region_y))}
        self._area = context.area
        context.window_manager.modal_handler_add(self)
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _encerrar(self):
        estado, _arraste_canto_porta[0] = _arraste_canto_porta[0], None
        self._area.tag_redraw()
        return estado

    def cancel(self, context):
        self._encerrar()

    def _imantar(self, context, mouse):
        melhor = None
        for obj, vertices in self._alvos:
            for co in vertices:
                p = _projetar_hud(context, co)
                if p is None:
                    continue
                d = (p - mouse).length
                if d <= RAIO_IMA_PX and (melhor is None or d < melhor[0]):
                    melhor = (d, co, obj)
        return (melhor[1], melhor[2]) if melhor else (None, None)

    def modal(self, context, event):
        estado = _arraste_canto_porta[0]
        if estado is None:
            return {'CANCELLED'}
        mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self._encerrar()
            return {'CANCELLED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type == 'MOUSEMOVE':
            alvo, obj = self._imantar(context, mouse)
            estado.update(mouse=mouse, alvo=alvo, objeto=obj)
            pontos = list(self._antigos)
            if alvo is not None:
                pontos[self.indice] = alvo
            estado['pontos'] = pontos
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            alvo, obj = self._imantar(context, mouse)
            if alvo is None:
                alvo, obj = estado.get('alvo'), estado.get('objeto')
            self._encerrar()
            if alvo is None or (alvo - self._antigos[self.indice]).length < 1e-6:
                return {'CANCELLED'}
            grupo = bpy.data.objects.get(self.grupo)
            if grupo is None:
                return {'CANCELLED'}
            pontos = list(self._antigos)
            pontos[self.indice] = alvo
            objetos = [None] * 4
            objetos[self.indice] = obj
            resultado = _aplicar_cantos_porta(context, grupo, pontos, objetos,
                                              self._antigos)
            return {'FINISHED'} if 'FINISHED' in resultado else {'CANCELLED'}
        return {'RUNNING_MODAL'}


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
    while obj is not None and MARCA_PORTAS not in obj:
        obj = obj.parent
    return obj


def _portas_do_modulo_da(grupo):
    """As portas que acendem junto: as do modulo da porta (ou so' ela)."""
    modulo = bpy.data.objects.get(grupo.get(CHAVE_MODULO_PORTA, ''))
    if modulo is not None and MARCA_CONJUNTO in modulo:
        portas = [g for g in _portas_do_conjunto(modulo)
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
    _redesenhar_viewports(context)
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
    _redesenhar_viewports(context)


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
    caneco gira com a folha e o pistao estica pela mira."""
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
        return p, L, A, _calcular_folhas_portas(L, A, p)
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
            z = centro[2] - e / 2.0 - DOBRADICA_FUNDO_MM / 2.0
            meio = aresta['dentro'] * DOBRADICA_AVANCO_MM / 2.0
        a, b = aresta['a'] + meio, aresta['b'] + meio
        eixo = (b - a).normalized() if (b - a).length else Vector((0, 1))
        ponto = a + eixo * (distancias[0] if distancias else 0.0)
        saida.append(('DOBRADICA', mundo((*ponto, z)), mundo((*a, z)),
                      mundo((*b, z))))
    if 'PISTAO' in tipos and p.get('abertura') == 'BASCULANTE' and folhas:
        g = _pistao_do_vao(A, folhas[0],
                           float(p.get('pistoes_offset_mm', 0.0) or 0.0), p)
        lateral = _pontas_pistao(g, PISTAO_DA_LATERAL_MM, folhas[0])[0]
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
        return 'dobradicas_margem_mm', min(distancia, comprimento - distancia)
    g = _pistao_do_vao(A, folhas[0], max(1e-3, fracao * A), p)
    automatico = _pistao_do_vao(A, folhas[0], p=p)['offset']
    return ('pistoes_offset_mm',
            0.0 if abs(g['offset'] - automatico) <= 0.5 else g['offset'])


def _controle_ferragem_sob_mouse(context, posicao):
    """(grupo, tipo) do controlador sob o mouse (so' com Alt)."""
    if not _correntes_visiveis():
        return None, None
    raio = RAIO_BOLINHA_PX * max(1.0, context.preferences.system.ui_scale)
    mouse = Vector(posicao)
    melhor = None
    for grupo, tipos in _ferragens_em_edicao(context):
        for tipo, ponto, _a, _b in _controles_ferragens(grupo, tipos):
            p = _projetar_hud(context, ponto)
            if p is None:
                continue
            d = (p - mouse).length
            if d <= raio and (melhor is None or d < melhor[0]):
                melhor = (d, grupo, tipo)
    return (melhor[1], melhor[2]) if melhor else (None, None)


def _desenhar_ferragens_selecionadas(context):
    """Ferragens selecionadas em realce e, com Alt (ou arrastando), o
    controlador de cada tipo (bolinha branca; arrastando, o trilho)."""
    edicao = _ferragens_em_edicao(context)
    if not edicao:
        return
    escala = max(1.0, context.preferences.system.ui_scale)
    realce = _cor_realce_hud()
    arraste = _arraste_ferragem[0]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        for grupo, tipos in edicao:
            _desenhar_caixas_2d(context, shader,
                                _caixas_ferragens(grupo, tipos), realce, escala)
        for grupo, tipos in edicao:
            for tipo, ponto, a, b in _controles_ferragens(grupo, tipos):
                ativo = arraste == (grupo.name, tipo)
                if not (ativo or _correntes_visiveis()):
                    continue
                tela = [_projetar_hud(context, v) for v in (ponto, a, b)]
                if any(v is None for v in tela):
                    continue
                if ativo:
                    shader.uniform_float('color', (1.0, 1.0, 1.0, 0.6))
                    batch_for_shader(shader, 'TRIS', {'pos': _quad_2d(
                        tela[1], tela[2], 1.0 * escala)}).draw(shader)
                    _bolinha_2d(shader, tela[0], 8 * escala, realce)
                _bolinha_2d(shader, tela[0], (6 if ativo else 5) * escala,
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
        erro = _editar_parametro_porta(context, grupo, self._nome, valor)
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
            ta, tb = (_projetar_hud(context, v) for v in self._trilho)
            grupo = bpy.data.objects.get(self.grupo)
            if ta is not None and tb is not None and grupo is not None:
                fracao = _fracao_na_linha(ta, tb, mouse)
                resultado = _valor_do_controle(grupo, self.tipo, fracao)
                if resultado is not None:
                    self._aplicar(context, resultado[1])
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self._encerrar()
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


# ------------------------------------------ slider de abertura (Epico 4)
# Um por folha, so' com a porta (ou a folha) selecionada: na BASE da folha
# FECHADA, um pouco a' frente (fica parado enquanto ela abre, entao nao
# foge do mouse) e por cima de tudo (raio-X). Arrastar para a direita
# abre, para a esquerda fecha -- seja qual for o lado da dobradica.
# Grosso (pedido do usuario) e recuado das pontas da folha: em porta dupla
# os dois nunca se encostam no meio, sobra uma folga entre eles.
SLIDER_FRENTE_MM = 30.0
SLIDER_RECUO_MM = 40.0           # de cada ponta da folha (min.)
SLIDER_RECUO_FRACAO = 0.12       # ... ou esta fracao da largura
# Medidas em MM do mundo (pedido do usuario): longe, o slider encolhe na
# mesma proporcao da porta; perto, para no teto (2x). Calibrado na vista
# normal de um modulo (~1 px/mm): o desenho aprovado pelo usuario.
SLIDER_ESPESSURA_MM = 13.0       # altura do trilho
SLIDER_BOTAO_MM = 12.0           # raio da bolinha = o alcance do clique
SLIDER_TEXTO_MM = 13.0           # altura do valor
SLIDER_PX_POR_MM_MAX = 2.0       # teto da escala (por ui_scale)
SLIDER_TEXTO_MIN_PX = 7.0        # menor que isto o valor nao se le: some
SIMBOLO_GRAU = chr(0xB0)         # codigo so' em ASCII
_arraste_slider_porta = [None]   # nome da folha sendo arrastada
_slider_hover = [None]           # nome da folha com a bolinha sob o mouse


def _folhas_com_slider(context):
    folhas = []
    for o in getattr(context, 'selected_objects', ()) or ():
        if MARCA_PORTAS in o and o.get('porta_parametros'):
            grupo, candidatas = o, _folhas_portas(o)
        elif MARCA_FOLHA in o and _grupo_portas(o) is not None:
            grupo, candidatas = _grupo_portas(o), [o]
        else:
            continue
        if _porta_veio_do_modulo(grupo):
            continue        # modulo selecionado: sem sliders
        folhas += [f for f in candidatas if f not in folhas]
    return folhas


def _slider_no_mundo(folha):
    """As 2 pontas do slider em MUNDO: base da folha fechada, a' frente,
    recuadas das quinas (a folga entre os sliders de uma porta dupla)."""
    l, a, e, _centro = _dados_da_folha(folha)
    fechada = _matriz_fechada(folha)
    recuo = min(max(SLIDER_RECUO_MM, SLIDER_RECUO_FRACAO * l), 0.3 * l)
    return [fechada @ (Vector((sx * (l / 2.0 - recuo), -a / 2.0,
                               e / 2.0 + SLIDER_FRENTE_MM)) / 1000.0)
            for sx in (-1, 1)]


def _slider_na_tela(context, folha):
    """(inicio, fim) do slider em pixels, o inicio sempre a' esquerda."""
    pontos = [_projetar_hud(context, p) for p in _slider_no_mundo(folha)]
    if any(p is None for p in pontos) or (pontos[1] - pontos[0]).length < 1:
        return None
    return tuple(sorted(pontos, key=lambda p: p.x))


def _fracao_no_slider(inicio, fim, mouse):
    trilho = fim - inicio
    return max(0.0, min(1.0, (mouse - inicio).dot(trilho) / trilho.length_squared))


def _px_por_mm_do_slider(context, folha):
    """Pixels por mm no meio do slider, medidos na vertical da TELA (a
    inclinacao do trilho nao afina o desenho), com o teto."""
    rv3d = context.region_data
    a, b = _slider_no_mundo(folha)
    meio = (a + b) / 2.0
    cima = rv3d.view_rotation @ Vector((0.0, 1.0, 0.0))
    p, q = (_projetar_hud(context, v) for v in (meio, meio + cima * 0.1))
    teto = SLIDER_PX_POR_MM_MAX * max(1.0, context.preferences.system.ui_scale)
    if p is None or q is None:
        return teto
    return min((q - p).length / 100.0, teto)


def _botao_do_slider(context, folha):
    """Centro da bolinha do slider (pixels), ou None."""
    tela = _slider_na_tela(context, folha)
    if tela is None:
        return None
    return tela[0].lerp(tela[1], float(folha.get(CHAVE_ABERTURA, 0.0)))


def _slider_sob_mouse(context, posicao):
    """A folha cuja BOLINHA esta' sob o mouse, ou None. O alcance e' o
    tamanho da bolinha (pedido do usuario): o trilho nao pega o clique."""
    if getattr(context, 'region_data', None) is None:
        return None             # sem vista 3D nao ha' slider na tela
    mouse = Vector(posicao)
    melhor = None
    for folha in _folhas_com_slider(context):
        botao = _botao_do_slider(context, folha)
        if botao is None:
            continue
        # do tamanho da bolinha desenhada (3 px no minimo: ainda se pega)
        raio = max(3.0, SLIDER_BOTAO_MM * _px_por_mm_do_slider(context, folha))
        d = (botao - mouse).length
        if d <= raio and (melhor is None or d < melhor[0]):
            melhor = (d, folha)
    return melhor[1] if melhor else None


def _texto_abertura(folha):
    grupo = _grupo_portas(folha)
    p = (grupo.get('porta_parametros') or {}) if grupo is not None else {}
    fracao = float(folha.get(CHAVE_ABERTURA, 0.0))
    abertura = p.get('abertura', 'GIRO')
    if abertura == 'CORRER':
        l, a, e, centro = _dados_da_folha(folha)
        mm = (_matriz_abertura(p, float(grupo.get('porta_vao_largura_mm', 0.0)),
                               len(_folhas_portas(grupo)),
                               int(folha.get('porta_indice', 0)),
                               (l, a, e, centro), fracao).translation * 1000.0
              - Vector(centro)).length
        return '%d mm' % round(mm)
    maximo = (_giro_maximo_rig() if _usa_rig(p)
              else ABERTURA_MAX_GRAUS.get(abertura, 110.0))
    return '%d%s' % (round(maximo * fracao), SIMBOLO_GRAU)


def _desenhar_sliders_porta(context):
    folhas = _folhas_com_slider(context)
    if not folhas:
        return
    realce = _cor_realce_hud()
    arrastando = _arraste_slider_porta[0]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        for folha in folhas:
            tela = _slider_na_tela(context, folha)
            if tela is None:
                continue
            inicio, fim = tela
            fracao = float(folha.get(CHAVE_ABERTURA, 0.0))
            botao = inicio.lerp(fim, fracao)
            # tudo proporcional ao zoom: 1 "escala" = 1 mm na tela
            mm = _px_por_mm_do_slider(context, folha)
            grosso = SLIDER_ESPESSURA_MM * mm
            raio = SLIDER_BOTAO_MM * mm
            aceso = folha.name in (arrastando, _slider_hover[0])
            shader.bind()
            # cores opacas: com alfa, a emenda das pontas redondas apareceria
            _capsula_2d(shader, inicio, fim, grosso + 3.0 * mm,
                        (0.92, 0.92, 0.92, 1.0))
            _capsula_2d(shader, inicio, fim, grosso, (0.13, 0.13, 0.13, 1.0))
            if fracao > 0:
                _capsula_2d(shader, inicio, botao, grosso * 0.65, realce)
            if aceso:
                _bolinha_2d(shader, botao, raio + 3.0 * mm, realce)
            _bolinha_2d(shader, botao, raio, (1.0, 1.0, 1.0, 1.0))
            _bolinha_2d(shader, botao, raio * 0.45, realce)
            # o valor numa caixa preta, centrado acima do botao; pequeno
            # demais para ler, some (o slider continua)
            tamanho = SLIDER_TEXTO_MM * mm
            if tamanho >= SLIDER_TEXTO_MIN_PX:
                texto = _texto_abertura(folha)
                blf.size(0, tamanho)
                largura = blf.dimensions(0, texto)[0]
                _caixa_texto_hud(botao.x - largura / 2.0,
                                 botao.y + raio + 7.0 * mm, texto, tamanho,
                                 tamanho / 12.0)
                gpu.state.blend_set('ALPHA')
    finally:
        gpu.state.blend_set('NONE')


def _capsula_2d(shader, a, b, grossura, rgba):
    """Trilho com as pontas redondas (o slider)."""
    shader.uniform_float('color', rgba)
    quad = _quad_2d(a, b, grossura)
    if quad:
        batch_for_shader(shader, 'TRIS', {'pos': quad}).draw(shader)
    for ponta in (a, b):
        _bolinha_2d(shader, ponta, grossura / 2.0, rgba)


class OBJECT_OT_abrir_porta(Operator):
    """Arraste o slider da folha: para a direita abre, para a esquerda fecha"""
    bl_idname = 'object.cabinet_abrir_porta'
    bl_label = 'Abrir Porta'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    folha: StringProperty(options={'SKIP_SAVE'})
    fracao: FloatProperty(min=0.0, max=1.0, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return _contexto_hud(context)

    def execute(self, context):
        folha = bpy.data.objects.get(self.folha)
        if folha is None or not _definir_abertura(context, folha, self.fracao):
            return {'CANCELLED'}
        _redesenhar_viewports(context)
        return {'FINISHED'}

    def invoke(self, context, event):
        # do gizmo da bolinha (ou do keymap): fora dela o clique segue
        folha = _slider_sob_mouse(context, (event.mouse_region_x,
                                            event.mouse_region_y))
        if folha is None:
            return {'PASS_THROUGH'}
        self.folha = folha.name
        self._antes = float(folha.get(CHAVE_ABERTURA, 0.0))
        self._area = context.area
        # pegou a bolinha fora do centro: ela nao pula ate' o mouse
        self._desvio = self._fracao_do_mouse(context, event, folha) - self._antes
        _arraste_slider_porta[0] = folha.name
        context.window_manager.modal_handler_add(self)
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    @staticmethod
    def _fracao_do_mouse(context, event, folha):
        tela = _slider_na_tela(context, folha)
        if tela is None:
            return float(folha.get(CHAVE_ABERTURA, 0.0))
        return _fracao_no_slider(*tela, Vector((event.mouse_region_x,
                                                event.mouse_region_y)))

    def _arrastar(self, context, event):
        folha = bpy.data.objects.get(self.folha)
        if folha is None:
            return
        self.fracao = max(0.0, min(1.0, self._fracao_do_mouse(
            context, event, folha) - self._desvio))
        _definir_abertura(context, folha, self.fracao)
        self._area.tag_redraw()

    def _encerrar(self):
        _arraste_slider_porta[0] = None
        self._area.tag_redraw()

    def cancel(self, context):
        self._encerrar()

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            folha = bpy.data.objects.get(self.folha)
            if folha is not None:
                _definir_abertura(context, folha, self._antes)
            self._encerrar()
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            self._arrastar(context, event)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self._arrastar(context, event)
            self._encerrar()
            return {'FINISHED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}


class VIEW3D_GT_slider_porta(Gizmo):
    """A bolinha do slider de abertura; o hit-test e' do tamanho dela.

    Gizmo e nao so' keymap: o gizmo e' avaliado ANTES de qualquer keymap.
    No keyconfig do usuario a selecao vinha antes da entrada do slider
    (o head=True do add-on nao vale na ordem dele), limpava a selecao e
    o slider sumia antes de receber o clique."""
    bl_idname = 'VIEW3D_GT_slider_porta'

    def draw(self, context):
        pass

    def test_select(self, context, location):
        folha = (_slider_sob_mouse(context, location)
                 if _contexto_hud(context) else None)
        nome = folha.name if folha is not None else None
        if nome != _slider_hover[0]:
            _slider_hover[0] = nome
            context.area.tag_redraw()
        return 0 if folha is not None else -1


class VIEW3D_GGT_slider_porta(GizmoGroup):
    bl_idname = 'VIEW3D_GGT_slider_porta'
    bl_label = 'Slider de abertura das portas'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        return _contexto_hud(context) and bool(_folhas_com_slider(context))

    def setup(self, context):
        self.botao = self.gizmos.new('VIEW3D_GT_slider_porta')
        self.botao.use_tooltip = False
        self.botao.target_set_operator('object.cabinet_abrir_porta')

    def draw_prepare(self, context):
        if not self.botao.is_highlight and _slider_hover[0] is not None:
            _slider_hover[0] = None


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
    """(folga em m, eixo u, extremo) como o `_melhor_vizinho` grava:
    positiva = afastada, negativa = invadindo o vizinho."""
    eixo, lado = ponta.split('_')
    ex, ey, _ez = _eixos(C)
    u = ex if eixo == 'x' else ey
    hx, hy, _hz = _meias(C)
    h = hx if eixo == 'x' else hy
    extremo = _centro(C).dot(u) + (h if lado == 'pos' else -h)
    face = int(C.get('adj_%s_face' % ponta, 0 if lado == 'pos' else 1))
    alvo = _faixa(N, u)[face]
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
    if P.type == 'MESH' and not _malha_e_caixa(P.data):
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
    hx, hy, _hz = _meias(C)
    h = hx if eixo == 'x' else hy
    fixo = extremo - 2 * h if lado == 'pos' else extremo + 2 * h
    novo = extremo + delta * (1 if lado == 'pos' else -1)
    comprimento = abs(novo - fixo)
    if comprimento < 0.001:
        return False
    if abs(delta) < TOL_RESET_DISTANCIA:
        return _deformar_ancoras(C, ponta, N) or bool(residuos)
    centro = _centro(C)
    _ocupado[0] = True
    try:
        if eixo == 'x':
            C.chapa_largura_mm = comprimento * 1000.0
        else:
            C.chapa_comprimento_mm = comprimento * 1000.0
    finally:
        _ocupado[0] = False
    _definir_centro(C, centro + u * ((novo + fixo) / 2 - centro.dot(u)))
    gerar_malha_chapa(C)
    bpy.context.view_layer.update()
    _deformar_ancoras(C, ponta, N)
    return True


def resetar_pontas(escolhidas):
    """[(chapa, ponta)] -> quantas voltaram; os modulos se reacomodam."""
    n, modulos = 0, set()
    for C, ponta in escolhidas:
        if resetar_ponta(C, ponta):
            n += 1
            modulo = _modulo_da_chapa(C)
            if modulo is not None:
                modulos.add(modulo)
    for modulo in modulos:
        _atualizar_modulo(modulo)
    return n


def _restricoes_reset(M):
    """[(eixo de M, 'min'/'max', deslocamento em m)] que cada solda de M
    pede para voltar a origem -- as que ja' estao nela pedem 0 (ancoras).
    Devolve tambem se alguma esta' fora."""
    eixos = _eixos(M)
    restricoes, fora = [], False
    for C in bpy.data.objects:
        if C.type != 'MESH' or MARCA_CHAPA not in C:
            continue
        for ponta in PONTAS:
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
    eixos = _eixos(M)
    centro = _centro(M)
    medidas = [M.chapa_largura_mm, M.chapa_comprimento_mm]
    for i, (d_min, d_max) in enumerate(plano['lados']):
        centro = centro + eixos[i] * ((d_min + d_max) / 2)
        if i < 2:
            medidas[i] += (d_max - d_min) * 1000.0
    _ocupado[0] = True
    try:
        M.chapa_largura_mm, M.chapa_comprimento_mm = medidas
    finally:
        _ocupado[0] = False
    _definir_centro(M, centro)
    gerar_malha_chapa(M)
    bpy.context.view_layer.update()
    # o que as ancoras pedem e a translacao nao resolve: DEFORMA a peca
    # que se move -- a ponta dela, ou a face dela se ela e' o vizinho
    for C in bpy.data.objects:
        if C.type != 'MESH' or MARCA_CHAPA not in C:
            continue
        for ponta in PONTAS:
            N = _vizinho_da_ponta(C, ponta)
            if N is not None and M in (C, N):
                _deformar_ancoras(C, ponta, N, 'a' if M is C else 'b')
    modulo = _modulo_da_chapa(M)
    if modulo is not None:
        _atualizar_modulo(modulo)


def _soldas_de(P):
    """Quantas soldas P tem e quantas estao fora da origem."""
    total = fora = 0
    for C in bpy.data.objects:
        if C.type != 'MESH' or MARCA_CHAPA not in C:
            continue
        for ponta in PONTAS:
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
    alvo = _alvo_hud(context)
    if alvo is not None and alvo[1] == 'INDIVIDUAL' and alvo[0] in (a, b):
        return alvo[0]
    return _peca_afastada(a, b)


def _modo_reset(context, nome=''):
    """('CHAPA', M, None) ou ('GRUPO', pecas, foco) pela selecao ativa;
    `nome` = a peca da linha clicada na viewport. None sem item."""
    alvo = _alvo_hud(context)
    foco = bpy.data.objects.get(nome) if nome else None
    if alvo is None:
        if foco is not None and MARCA_CHAPA in foco:
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
                _perguntar(context, PERGUNTA_RESET, [
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
        _redesenhar_viewports(context)
        return {'FINISHED'}


def _propriedade_hud(alvo):
    if alvo['tipo'] == 'espessura':
        return 'chapa_espessura_mm'
    if alvo['tipo'] != 'medida':
        return None
    if alvo['modo'] == 'INDIVIDUAL':
        return ('chapa_largura_mm', 'chapa_comprimento_mm',
                'chapa_espessura_mm')[alvo['eixo']]
    return ('conj_largura_mm', 'conj_profundidade_mm',
            'conj_altura_mm')[alvo['eixo']]


def _valor_hud(alvo, context=None):
    if alvo['tipo'] == 'gap':
        return float(alvo['objeto']['porta_parametros']['entre_folhas_mm'])
    propriedade = _propriedade_hud(alvo)
    if propriedade.startswith('conj_') and MARCA_CONJUNTO not in alvo['objeto']:
        # caixa do proprio item (ver `_aplicar_valor_hud`)
        chapas = alvo.get('chapas') or grupo_de(alvo['objeto']) or [alvo['objeto']]
        lo, hi = _caixa_de(chapas)
        return (hi[alvo['eixo']] - lo[alvo['eixo']]) * 1000.0
    return float(getattr(alvo['objeto'], propriedade))


def _redimensionar_chapa_ancorada(chapa, eixo, valor_mm, lado):
    """Muda L (eixo 0), A (eixo 1) ou E (eixo 2) de UMA chapa sem mexer
    na face `lado` ('min'/'max' no eixo local). A malha da chapa e'
    centrada na origem: sem deslocar o centro ela cresceria pelos dois
    lados. Na E a seta escolhe a face parada, no lugar da regra
    "engrossa para dentro" de `aplicar_espessura_chapa`."""
    prop = ('chapa_largura_mm', 'chapa_comprimento_mm',
            'chapa_espessura_mm')[eixo]
    antes = getattr(chapa, prop)
    _ocupado[0] = True
    try:
        setattr(chapa, prop, valor_mm)
    finally:
        _ocupado[0] = False
    direcao = chapa.matrix_world.to_3x3().col[eixo].normalized()
    sinal = 1.0 if lado == 'min' else -1.0
    _definir_centro(chapa, _centro(chapa)
                    + direcao * sinal * (valor_mm - antes) / 2000.0)
    gerar_malha_chapa(chapa)


def _aplicar_valor_hud(context, alvo, valor):
    obj = alvo['objeto']
    if alvo['tipo'] == 'gap':
        parametros = dict(obj['porta_parametros'])
        parametros['entre_folhas_mm'] = max(0, valor)
        _aplicar_portas(context, obj, obj.matrix_world.copy(), obj.parent,
                        obj['porta_vao_largura_mm'], obj['porta_vao_altura_mm'],
                        parametros)
        _ocupado[0] = True
        try:
            _carregar_portas_na_cena(context.scene, obj)
        finally:
            _ocupado[0] = False
        return
    propriedade = _propriedade_hud(alvo)
    valor = max(20 if propriedade.startswith('conj_') else 1, valor)
    if propriedade == 'chapa_espessura_mm':
        valor = _espessura_livre(valor)
    # A quina perto do mouse (`lado`) fica parada; os outros eixos nao
    # mudam, entao a ancora deles tanto faz.
    ancoras = None
    if alvo.get('lado') and propriedade.startswith('conj_'):
        ancoras = ['min', 'min', 'min']
        ancoras[alvo['eixo']] = alvo['lado']
    if MARCA_CONJUNTO not in obj and propriedade.startswith('conj_'):
        # Grupo de chapas sem Empty. As medidas saem da CAIXA das chapas
        # do proprio item, nao dos campos da cena: estes sao do objeto
        # ativo, e na edicao de varios itens o item pode ser outro.
        chapas = alvo.get('chapas') or grupo_de(obj) or [obj]
        lo, hi = _caixa_de(chapas)
        medidas = [(hi[0] - lo[0]) * 1000.0, (hi[2] - lo[2]) * 1000.0,
                   (hi[1] - lo[1]) * 1000.0]            # L, A, P
        medidas[(0, 2, 1)[alvo['eixo']]] = valor
        redimensionar_grupo(chapas, medidas, ancoras)
        pai = chapas[0].parent
        if pai is not None and MARCA_CONJUNTO in pai:
            reposicionar_origem(pai)
            sincronizar_medidas_conjunto(pai)
            atualizar_portas_do_conjunto(pai)
        if context.object in chapas:
            sincronizar_grupo(context)          # a gaveta mostra o novo
        context.view_layer.update()
        return
    if (alvo.get('lado') and alvo.get('modo') == 'INDIVIDUAL'
            and alvo['tipo'] == 'medida'
            and propriedade in {'chapa_largura_mm', 'chapa_comprimento_mm',
                                'chapa_espessura_mm'}):
        _redimensionar_chapa_ancorada(obj, alvo['eixo'], valor, alvo['lado'])
        context.view_layer.update()
        return
    atualizar = (
        (lambda o, c: redimensionar_conjunto(o, ancoras))
        if propriedade.startswith('conj_') else
        _upd_espessura if propriedade == 'chapa_espessura_mm'
        else _upd_chapa)
    _ocupado[0] = True
    try:
        setattr(obj, propriedade, valor)
    finally:
        _ocupado[0] = False
    atualizar(obj, context)
    context.view_layer.update()


def _estado_arraste_hud(context, alvo):
    obj = alvo['objeto']
    modulo = obj if MARCA_CONJUNTO in obj else _modulo_da_chapa(obj)
    if modulo is None and MARCA_PORTAS in obj:
        modulo = obj.parent if obj.parent and MARCA_CONJUNTO in obj.parent else None
    objetos = [modulo, *modulo.children_recursive] if modulo else familia_de(obj)
    if not objetos:
        objetos = [obj]
    estado = []
    for o in objetos:
        if CHAVE_FERRAGEM in o:
            # refeitas a cada redimensionar (podem ate' sumir): no
            # cancelar saem de novo da porta, nunca de um backup
            continue
        props = {}
        if MARCA_CHAPA in o:
            props = {p: getattr(o, p) for p in
                     ('chapa_largura_mm', 'chapa_comprimento_mm', 'chapa_espessura_mm')}
        if MARCA_CONJUNTO in o:
            props.update({p: getattr(o, p) for p in
                          ('conj_largura_mm', 'conj_altura_mm', 'conj_profundidade_mm')})
        porta = ({p: dict(o[p]) if p == 'porta_parametros' else o[p] for p in
                  ('porta_parametros', 'porta_vao_largura_mm', 'porta_vao_altura_mm')}
                 if MARCA_PORTAS in o and 'porta_parametros' in o else {})
        if MARCA_FOLHA in o and CHAVE_CENTRO_FOLHA in o:
            porta[CHAVE_CENTRO_FOLHA] = tuple(o[CHAVE_CENTRO_FOLHA])
        vertices =[tuple(v.co) for v in o.data.vertices] if o.type == 'MESH' else None
        estado.append((o, o.matrix_world.copy(), o.matrix_parent_inverse.copy(),
                       props, porta, vertices))
    cena = {p: getattr(context.scene, p) for p in
            ('grupo_largura_mm', 'grupo_altura_mm', 'grupo_profundidade_mm',
             'grupo_espessura_mm') + _PROPS_PORTAS_CENA}
    return estado, cena


def _restaurar_arraste_hud(context, estado):
    objetos, cena = estado
    _ocupado[0] = True
    try:
        for obj, matriz, inversa, props, porta, vertices in objetos:
            for nome, valor in props.items():
                setattr(obj, nome, valor)
            for nome, valor in porta.items():
                obj[nome] = valor
            obj.matrix_parent_inverse = inversa
            obj.matrix_world = matriz
            if vertices is not None and len(vertices) == len(obj.data.vertices):
                for vertice, co in zip(obj.data.vertices, vertices):
                    vertice.co = co
                obj.data.update()
        for nome, valor in cena.items():
            setattr(context.scene, nome, valor)
        for obj, *_resto in objetos:
            if MARCA_PORTAS in obj:
                _refazer_ferragens(obj)
        context.view_layer.update()
    finally:
        _ocupado[0] = False


class OBJECT_OT_arrastar_hud(Operator):
    """Arrasta uma dimensao, uma espessura, o vao ou um canto do modulo"""
    bl_idname = 'object.cabinet_arrastar_hud'
    bl_label = 'Editar na Viewport'
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    @classmethod
    def poll(cls, context):
        return _contexto_hud(context)

    def invoke(self, context, event):
        alvo = _acertar_hud(context, (event.mouse_region_x, event.mouse_region_y))
        _log_clique('HUD pegou %s/%s alvo=%s' % (
            event.type, event.value, alvo and alvo.get('tipo')))
        if alvo is None or _edicao_hud[0] is not None:
            return {'CANCELLED'}
        self._alvo = alvo
        self._area = context.area
        self._arrastou = False
        self._inicio = Vector((event.mouse_region_x, event.mouse_region_y))
        self._backup = _estado_arraste_hud(context, alvo)
        self._origem = alvo['pontos'][0].copy()
        self._matriz = alvo['objeto'].matrix_world.copy()
        if alvo['tipo'] == 'ancora':
            self._ponto_mouse = view3d_utils.region_2d_to_location_3d(
                context.region, context.region_data, self._inicio, self._origem)
        else:
            if MARCA_CONJUNTO in alvo['objeto']:
                sincronizar_medidas_conjunto(alvo['objeto'])
            elif alvo.get('modo') == 'GRUPO':
                sincronizar_grupo(context)     # valor de partida real
            self._valor = _valor_hud(alvo, context)
            if alvo['tipo'] == 'gap':
                eixo = self._matriz.to_3x3().col[0].normalized()
            elif alvo['tipo'] == 'espessura':
                eixo = self._matriz.to_3x3().col[2].normalized()
            else:
                eixo = (alvo['pontos'][1] - alvo['pontos'][0]).normalized()
            # Escala de tela medida no proprio ponto: nao depende de
            # pixels fixos por mm nem de um angulo frontal da vista.
            a = _projetar_hud(context, self._origem)
            b = _projetar_hud(context, self._origem + eixo * 0.1)
            vetor = b-a if a is not None and b is not None else Vector((0, 0))
            if vetor.length < 1:
                # Eixo visto de ponta: usar a vertical da tela mantem
                # o arraste acessivel na vista alinhada ao eixo.
                vetor = Vector((0, 100))
            self._por_pixel = 100 / vetor.length
            self._direcao = vetor.normalized()
        _edicao_hud[0] = {'regiao': context.region.as_pointer(), 'alvo': alvo}
        self._backups = [self._backup]
        if alvo['tipo'] == 'medida' and alvo.get('lado'):
            # Varios itens selecionados: a SELECAO ja' diz o que se edita
            # (pedido do usuario -- sem "Editar como?"). Falta so' a seta
            # de cada um: os que ainda nao tem piscam, e cada clique numa
            # linha deles escolhe a quina parada. Todos orientados, o
            # valor digitado vale para todos.
            itens = _itens_hud(context)
            if (len(itens) > 1 and _chave_do_alvo(alvo)
                    in {_chave_do_item(o, c) for o, _m, c in itens}):
                _edicao_hud[0].update(fase='coletar', itens=[alvo],
                                      todos=itens, hover=None)
                _piscar_pendentes()
        context.window_manager.modal_handler_add(self)
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _encerrar(self):
        _edicao_hud[0] = None
        self._area.tag_redraw()

    def cancel(self, context):
        for backup in reversed(getattr(self, '_backups', [self._backup])):
            _restaurar_arraste_hud(context, backup)
        self._encerrar()

    def _comecar_digitacao(self):
        estado = _edicao_hud[0]
        estado['fase'] = None
        estado['hover'] = None
        estado['texto'] = _numero_na_unidade(_valor_hud(estado['itens'][0]))
        estado['cursor'] = len(estado['texto'])
        estado['selecionado'] = True
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _restantes(self):
        """Itens da selecao ainda sem linha escolhida -- so' eles mostram
        linhas para escolher; o mesmo objeto nao entra duas vezes."""
        estado = _edicao_hud[0]
        escolhidos = {_chave_do_alvo(a) for a in estado['itens']}
        return [item for item in estado['todos']
                if _chave_do_item(item[0], item[2]) not in escolhidos]

    def _multiplo(self, context, event):
        """Coleta a seta (linha + quina parada) de cada item que falta;
        o ultimo orientado leva direto a digitar o valor."""
        estado = _edicao_hud[0]
        mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}       # navegar continua valendo
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.cancel(context)
            return {'CANCELLED'}
        escala = context.preferences.system.ui_scale
        if event.type == 'MOUSEMOVE':
            estado['hover'] = None
            projetar = lambda p: _projetar_hud(context, p)
            for item in self._restantes():
                alvo = _acertar_linhas_hud(_geometria_do_item(*item), mouse,
                                           projetar, escala, cantos=False)
                if alvo is not None and alvo['tipo'] == 'medida':
                    estado['hover'] = alvo
                    break
            self._area.tag_redraw()
        elif (event.type == 'LEFTMOUSE' and event.value == 'PRESS'
              and estado.get('hover') is not None):
            alvo = estado['hover']
            self._backups.append(_estado_arraste_hud(context, alvo))
            estado['itens'].append(alvo)
            estado['hover'] = None
            if not self._restantes():
                return self._comecar_digitacao()
            _piscar_pendentes()          # os que faltam piscam de novo
            self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _digitar(self, context, event):
        """Medida do modulo por teclado, depois de um clique sem arraste.

        Sem previa a cada tecla: digitando 750, o modulo passaria por
        7 e 75 mm, e cada passagem reescala as pecas de novo.
        """
        estado = _edicao_hud[0]
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cancel(context)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and self._clique_na_caixa(event):
            # Clique DENTRO da caixa nao fecha: posiciona o cursor
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type in {'RET', 'NUMPAD_ENTER', 'LEFTMOUSE'}:
            try:
                valor = _ler_medida_digitada(estado['texto']) * 1000.0
                # Varios itens: cada um fica com o MESMO valor, cada um
                # ancorado na quina escolhida nele.
                for alvo in estado.get('itens') or [self._alvo]:
                    _aplicar_valor_hud(context, alvo, valor)
            except (ValueError, TypeError, ReferenceError) as erro:
                self.report({'WARNING'}, str(erro))
                return {'RUNNING_MODAL'}
            self._encerrar()
            return {'FINISHED'}
        entrada = (context.window_manager.clipboard
                   if event.ctrl and event.type == 'V'
                   else '' if event.ctrl else event.unicode or '')
        if _tecla_no_texto(estado, event.type, entrada, event.ctrl):
            self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _clique_na_caixa(self, event):
        """True (e o cursor no lugar) se o clique caiu numa caixa de texto
        desenhada -- as posicoes vem do ultimo desenho da HUD."""
        estado = _edicao_hud[0]
        mx, my = event.mouse_region_x, event.mouse_region_y
        texto = estado['texto']
        cursor = estado.get('cursor', len(texto))
        for x, y, tamanho, escala in estado.get('caixas') or ():
            largura = _medidor_blf(tamanho)
            blf.size(0, tamanho)
            altura = blf.dimensions(0, '0')[1]
            folga = 4 * escala
            if (x - folga <= mx <= x + largura(_com_cursor(texto, cursor)) + folga
                    and y - folga <= my <= y + altura + folga):
                estado['cursor'] = _cursor_no_x(texto, cursor, x, mx, largura)
                estado['selecionado'] = False
                return True
        return False

    def modal(self, context, event):
        if context.mode != 'OBJECT':
            self.cancel(context)
            return {'CANCELLED'}
        if (_edicao_hud[0] or {}).get('fase'):
            return self._multiplo(context, event)
        if (_edicao_hud[0] or {}).get('texto') is not None:
            return self._digitar(context, event)
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cancel(context)
            return {'CANCELLED'}
        mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if (not self._arrastou and self._alvo['tipo'] == 'medida'
                    and self._alvo.get('lado')):
                # Clique sem arrastar numa linha do modulo: a seta fica e
                # o valor passa a ser digitado (Enter confirma, Esc volta).
                texto = _numero_na_unidade(self._valor)
                _edicao_hud[0].update(texto=texto, cursor=len(texto),
                                      selecionado=True)
                self._area.tag_redraw()
                return {'RUNNING_MODAL'}
            self._encerrar()
            return {'FINISHED'}
        if event.type != 'MOUSEMOVE':
            return {'RUNNING_MODAL'}
        if not self._arrastou:
            # Tremida de clique nao e' arraste: sem este limiar o clique
            # nunca chegaria ao modo de digitar.
            if (mouse - self._inicio).length < LIMIAR_ARRASTE_HUD_PX:
                return {'RUNNING_MODAL'}
            self._arrastou = True
        try:
            if self._alvo['tipo'] == 'ancora':
                ponto = view3d_utils.region_2d_to_location_3d(
                    context.region, context.region_data, mouse, self._origem)
                matriz = self._matriz.copy()
                matriz.translation += ponto - self._ponto_mouse
                self._alvo['objeto'].matrix_world = matriz
                self._alvo['pontos'] = [self._origem + ponto - self._ponto_mouse]
                context.view_layer.update()
            else:
                delta = (mouse-self._inicio).dot(self._direcao) * self._por_pixel
                _aplicar_valor_hud(context, self._alvo, self._valor + delta)
        except (ValueError, TypeError, ReferenceError) as erro:
            self.report({'WARNING'}, str(erro))
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}


def _chave_widget(acao):
    """Identidade estavel do widget, usada para guardar o realce dele.

    Devolve None para o que NAO e' botao (decoracao, rotulo, trilho do
    slider): essas coisas nao acendem.
    """
    if not acao:
        return None
    verbo = acao[0]
    if verbo in {'wireframe', 'separador', 'slider', 'fundo', 'pergunta'}:
        return None
    if verbo == 'resposta':
        return 'resp:%d' % acao[1]
    if verbo in {'suspenso', 'faixa'}:
        return '%s:%s' % (verbo, acao[1])
    if verbo == 'cor':
        # quadro e matiz sao superficie de arraste, nao botao
        if acao[2] == 'amostra':
            return 'cor:' + acao[1]
        return 'cor:%s:%s' % (acao[1], acao[5]) if acao[2] == 'atalho' else None
    if verbo in BOTOES_CRIAR and len(acao) > 4 and acao[4]:
        return None             # botao apagado nao acende
    if verbo == 'cadeado':
        return 'cad:%d' % acao[2]
    if verbo == 'medida':
        return 'medida:' + acao[3]
    if verbo == 'modo':
        return None             # so' indicador: o modo sai da selecao
    if verbo == 'divisa':
        return 'divisa' if acao[1] else None    # coberta pelas opcoes
    if verbo == 'aba':
        return '%s:%s' % (verbo, acao[1])
    if verbo == 'escolha':
        return 'esc:%s:%s' % (acao[1], acao[2])
    if verbo == 'operador':
        # botao de texto apagado (selecao invalida) nao acende
        return None if _operador_apagado(acao) else 'op:' + acao[1]
    if verbo == 'navegar':
        return 'nav:%s:%s' % (acao[1], acao[2])
    if verbo == 'rolar_nivel':
        return 'rol:%s:%s' % (acao[1], acao[2])
    if verbo == 'preset':
        return 'preset:%s' % acao[1]['arquivo']
    if verbo == 'item':
        return 'item:%s:%s' % (acao[1]['arquivo'], acao[2])
    return verbo


def _cantos_caixa(origem, u, v, w):
    return [origem + u * i + v * j + w * k
            for k in (0, 1) for j in (0, 1) for i in (0, 1)]


def _alvos_da_medida(context, modo):
    """Objetos que a medida daquele modo governa."""
    obj = context.object
    if modo == 'GRUPO' and obj is not None:
        familia = [o for o in familia_de(obj) if o.type in TIPOS_COM_VOLUME]
        if familia:
            return familia
    return list(context.selected_objects)


def _caixa_da_medida(context, modo):
    """Os 8 cantos, em mundo, da caixa que o campo edita."""
    obj = context.object
    if modo == 'INDIVIDUAL' and obj is not None:
        # Caixa ORIENTADA pela chapa: girada, a espessura dela nao e'
        # o eixo vertical do mundo, e uma caixa alinhada ao mundo
        # acenderia a aresta errada.
        mw = obj.matrix_world
        try:
            if MARCA_CHAPA in obj:
                # nominal: o corte do perfil nao encolhe a chapa medida
                meias = Vector(_meias(obj))
                locais = [-meias, meias]
            else:
                locais = [Vector(c) for c in obj.bound_box]
        except Exception:
            return None
        if not locais:
            return None
        lo = [min(c[a] for c in locais) for a in range(3)]
        hi = [max(c[a] for c in locais) for a in range(3)]
        origem = mw @ Vector(lo)
        eixos = []
        for a in range(3):
            canto = list(lo)
            canto[a] = hi[a]
            eixos.append((mw @ Vector(canto)) - origem)
        return _cantos_caixa(origem, *eixos)

    limites = _limites_mundo(context, _alvos_da_medida(context, modo))
    if limites is None:
        return None
    lo, hi, _n = limites
    origem = Vector(lo)
    return _cantos_caixa(origem,
                         Vector((hi[0] - lo[0], 0.0, 0.0)),
                         Vector((0.0, hi[1] - lo[1], 0.0)),
                         Vector((0.0, 0.0, hi[2] - lo[2])))


def _definir_realce_medida(rotulo):
    """Guarda o campo aceso e manda a viewport se redesenhar.

    O glow mora na gaveta, mas a caixa aparece na area VIZINHA: sem
    este tag_redraw ela so' apareceria quando algo mais pedisse
    redesenho, e o realce pareceria intermitente.
    """
    if _realce_medida[0] == rotulo:
        return
    _realce_medida[0] = rotulo
    for janela in bpy.context.window_manager.windows:
        for area in janela.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _desenhar_grid_medidas():
    _desenhar_hud_3d(bpy.context)


class VIEW3D_GT_campo_gaveta(Gizmo):
    """Hit-test invisivel sobre o retangulo de UM widget da gaveta.

    Existe so' para ganhar `is_highlight`: o desenho da gaveta e' GPU e
    nao recebe evento de mouse, e um operador modal persistente roubaria
    evento de outros add-ons. O clique cai no mesmo operador que a
    keymap ja' dispara para a area inteira, entao nada muda ao clicar.

    Quando o widget tem icone, o disco do `GIZMO_GT_button_2d` fica de
    FORA deste hit-test: assim o gizmo do icone continua ganhando o
    pick ali e o tooltip dele nao se perde. O glow cobre os dois casos
    porque soma os dois `is_highlight`.
    """
    bl_idname = 'VIEW3D_GT_campo_gaveta'

    def draw(self, context):
        pass

    def test_select(self, context, location):
        alvo = _campos_gaveta.get(self.as_pointer())
        if not alvo:
            return -1
        x, y, w, h, icone = alvo
        px, py = location
        if not (x <= px <= x + w and y <= py <= y + h):
            return -1
        if icone is not None:
            cx, cy, raio = icone
            if (px - cx) ** 2 + (py - cy) ** 2 <= raio * raio:
                return -1
        return 0


def _degrade_gaveta(vertices, cores):
    """Triangulos com cor por vertice (quadro e faixa de matiz)."""
    shader = gpu.shader.from_builtin('SMOOTH_COLOR')
    batch_for_shader(shader, 'TRIS', {'pos': vertices,
                                      'color': cores}).draw(shader)


def _seta_suspensa_gaveta(x, y, w, h, aberta, cor):
    cx, cy = x + w - 12, y + h / 2
    pontos = (((cx - 4, cy - 2), (cx + 4, cy - 2), (cx, cy + 3)) if aberta
              else ((cx - 4, cy + 2), (cx + 4, cy + 2), (cx, cy - 3)))
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float('color', (*cor, 1))
    batch_for_shader(shader, 'TRIS', {'pos': pontos}).draw(shader)


def _anel_gaveta(cx, cy, raio, miolo):
    """Marcador do seletor: aro preto + branco em volta da cor escolhida,
    visivel sobre qualquer ponto do quadro."""
    for r, cor in ((raio + 1.5, (0, 0, 0, 1)), (raio, (1, 1, 1, 1)),
                   (raio - 2, (*miolo, 1))):
        _retangulo_arredondado_gaveta(cx - r, cy - r, 2 * r, 2 * r, r, cor)


def _listras_gizmo_gaveta(x, y, w, h):
    """Amostra do realce do gizmo: X, Y, Z e a espessura, lado a lado."""
    tons = [_cor_eixo_gizmo(e) for e in ('axis_x', 'axis_y', 'axis_z')]
    tons.append(COR_REALCE_PADRAO)
    for i, tom in enumerate(tons):
        _retangulo_gaveta(x + w * i / 4, y, w / 4, h, (*tom, 1))


def _desenhar_opcao_gaveta(context, x, y, w, h, rotulo, acao, cores, fundo):
    """Controles do painel de opcoes: lista suspensa, faixa e cor."""
    texto_cor = tuple(cores.text[:3])
    verbo = acao[0]
    if verbo == 'fundo':
        _retangulo_arredondado_gaveta(x - 1, y - 1, w + 2, h + 2, 6,
                                      (*cores.outline[:3], 1))
        _retangulo_arredondado_gaveta(x, y, w, h, 5, fundo)
        return
    if verbo == 'suspenso':
        _botao_gaveta(x, y, w, h, ativo=acao[2])
        _texto_cabivel_gaveta(x + 9, y + (h - 12) / 2, rotulo, w - 30)
        _seta_suspensa_gaveta(x, y, w, h, acao[2], texto_cor)
        return
    if verbo == 'faixa':
        _botao_gaveta(x, y, w, h)
        minimo, maximo = acao[3], acao[4]
        fracao = max(0.0, min(1.0, (acao[2] - minimo) / (maximo - minimo)))
        if fracao > 0:
            _retangulo_arredondado_gaveta(
                x + 1, y + 1, max(6, (w - 2) * fracao), h - 2, 3,
                (*cores.inner_sel[:3], 1))
        edicao = _edicao_gaveta[0]
        if (edicao is not None and edicao['propriedade'] == acao[1]
                and edicao['area'] == context.area.as_pointer()):
            texto, cursor = edicao['texto'], edicao['cursor']
            rotulo = texto[:cursor] + '|' + texto[cursor:]
        blf.size(0, 12)
        largura = min(blf.dimensions(0, rotulo)[0], w - 12)
        _texto_cabivel_gaveta(x + (w - largura) / 2, y + (h - 12) / 2,
                              rotulo, w - 12)
        return
    parte = acao[2]
    if parte == 'amostra':
        _botao_gaveta(x, y, w, h, ativo=acao[4])
        lado = min(34, w * 0.35)
        _retangulo_gaveta(x + 4, y + 4, lado, h - 8, (*cores.outline[:3], 1))
        if acao[5] == 'GIZMO':
            _listras_gizmo_gaveta(x + 5, y + 5, lado - 2, h - 10)
        else:
            _retangulo_gaveta(x + 5, y + 5, lado - 2, h - 10, (*acao[3], 1))
        _texto_cabivel_gaveta(x + lado + 10, y + (h - 12) / 2, rotulo,
                              w - lado - 32, 11)
        _seta_suspensa_gaveta(x, y, w, h, acao[4], texto_cor)
    elif parte == 'atalho':
        borda = texto_cor if acao[4] else tuple(cores.outline[:3])
        espessura = 2 if acao[4] else 1
        _retangulo_gaveta(x, y, w, h, (*borda, 1))
        if acao[5] == 'GIZMO':
            _listras_gizmo_gaveta(x + espessura, y + espessura,
                                  w - 2 * espessura, h - 2 * espessura)
        else:
            _retangulo_gaveta(x + espessura, y + espessura, w - 2 * espessura,
                              h - 2 * espessura, (*acao[3], 1))
        if rotulo:
            claro = sum(acao[3]) / 3 > 0.5
            blf.size(0, 10)
            lw, lh = blf.dimensions(0, rotulo)
            _texto_gaveta(x + (w - lw) / 2, y + (h - lh) / 2, rotulo, 10,
                          (0, 0, 0, 1) if claro else (1, 1, 1, 1))
    elif parte == 'quadro':
        h_, s, v = _hsv_opcao(acao[1], acao[3])
        puro = colorsys.hsv_to_rgb(h_, 1.0, 1.0)
        # Interpolar os 4 cantos (preto embaixo, branco e matiz pura em
        # cima) da' exatamente V * mistura(branco, matiz, S)
        a, b, c, d = (x, y), (x + w, y), (x + w, y + h), (x, y + h)
        preto, branco = (0, 0, 0, 1), (1, 1, 1, 1)
        _degrade_gaveta((a, b, c, a, c, d),
                        (preto, preto, (*puro, 1), preto, (*puro, 1), branco))
        _anel_gaveta(x + s * w, y + v * h, 6, acao[3])
    elif parte == 'matiz':
        vertices, tons = [], []
        for i in range(6):
            x0, x1 = x + w * i / 6, x + w * (i + 1) / 6
            c0 = (*colorsys.hsv_to_rgb(i / 6, 1, 1), 1)
            c1 = (*colorsys.hsv_to_rgb((i + 1) / 6, 1, 1), 1)
            vertices += [(x0, y), (x1, y), (x1, y + h),
                         (x0, y), (x1, y + h), (x0, y + h)]
            tons += [c0, c1, c1, c0, c1, c0]
        _degrade_gaveta(vertices, tons)
        h_ = _hsv_opcao(acao[1], acao[3])[0]
        mx = x + h_ * w
        _retangulo_gaveta(mx - 2.5, y - 2, 5, h + 4, (0, 0, 0, 1))
        _retangulo_gaveta(mx - 1.5, y - 1, 3, h + 2, (1, 1, 1, 1))
    gpu.state.blend_set('ALPHA')


def _medida_em_alerta(acao):
    """Campo de medida que sai em vermelho: Espessura acima do
    convencional (ESPESSURA_ALERTA_MM)."""
    try:
        return (acao[0] == 'medida' and acao[3] == 'Espessura'
                and _espessura_em_alerta(acao[4]))
    except (IndexError, TypeError, ValueError):
        return False


def _cor_alerta_gaveta():
    """Vermelho do TEMA (cor literal e' proibida, DESIGN.md sec. 5): o do
    erro do editor Info, clareado ate' ler bem sobre o fundo escuro."""
    tema = bpy.context.preferences.themes[0]
    for area, nome in (('info', 'info_error'), ('user_interface', 'axis_x')):
        try:
            cor = list(getattr(getattr(tema, area), nome))[:3]
        except Exception:
            continue
        topo = max(cor)
        if topo > 0:
            cor = [c * 0.95 / topo for c in cor] if topo < 0.95 else cor
            return (*cor, 1.0)
    return (*_cores_gaveta()[0].text[:3], 1.0)


def _intersecao_retangulos(a, b):
    """(x, y, w, h) comum a dois retangulos; largura/altura >= 0."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1 = min(a[0] + a[2], b[0] + b[2])
    y1 = min(a[1] + a[3], b[1] + b[3])
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0)


def _desenhar_divisa_gaveta(context, largura, meio, acao, cores):
    """Linha entre a aba e a biblioteca. Sob o mouse ela ganha o mesmo
    halo dos botoes e uma pega no centro: e' ali que se arrasta."""
    realce = _valor_realce(context, _chave_widget(acao)) if acao[1] else 0.0
    gpu.state.blend_set('ALPHA')
    if realce > 0.01:
        _glow_gaveta(0, meio - 1, largura, 2, 1, realce, cores.text)
    cor = tuple(c + (t - c) * realce for c, t in
                zip(cores.outline[:3], cores.text[:3]))
    _retangulo_gaveta(0, meio - 1 if realce > 0.5 else meio, largura,
                      2 if realce > 0.5 else 1, (*cor, 1))
    # pega: tres tracinhos no meio, como a divisoria de areas do Blender
    for i in (-1, 0, 1):
        _retangulo_gaveta(largura / 2 - 9, meio + i * 3 - 0.5, 18, 1,
                          (*cor, 0.55 + 0.45 * realce))


def _desenhar_gaveta(tela=False):
    context = bpy.context
    if context.region is None or context.region.type != 'WINDOW':
        return
    if not _eh_area_gaveta(context):
        if (context.area is not None and context.area.type == 'VIEW_3D'
                and (_area_gaveta(context.screen) is None
                     or context.area.x > _area_gaveta(context.screen).x)):
            centro = max(48, context.region.height * 0.12)
            realce = _valor_realce(context, 'alca')
            cores, _ = _cores_gaveta()
            gpu.state.blend_set('ALPHA')
            # o glow cresce so' para a direita: a alca encosta na borda
            _glow_gaveta(0, centro - 35, 26, 70, 5, realce, cores.text,
                         esquerda_reta=True)
            _retangulo_arredondado_gaveta(
                0, centro - 35, 26, 70, 5,
                (*(c + (t - c) * realce * 0.45
                   for c, t in zip(cores.outline[:3], cores.text)), 1),
                esquerda_reta=True)
            _retangulo_arredondado_gaveta(
                0, centro - 34, 25, 68, 4,
                (*(c + (t - c) * realce * 0.22
                   for c, t in zip(cores.inner[:3], cores.text)), 1),
                esquerda_reta=True)
            aberta = _area_gaveta(context.screen) is not None
            seta = (((9, centro), (16, centro - 7),
                     (16, centro + 7)) if aberta else
                    ((16, centro), (9, centro - 7),
                     (9, centro + 7)))
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            batch = batch_for_shader(shader, 'TRIS', {'pos': seta})
            shader.bind()
            shader.uniform_float('color', (*cores.text, 1))
            batch.draw(shader)
            gpu.state.blend_set('NONE')
        return
    # A tela da gaveta e' desenhada antes dos GIZMO_GT_button_2d.
    # POST_PIXEL cobre os icones nativos se desenhar o fundo por cima.
    if not tela:
        return
    largura, altura = context.region.width, context.region.height
    cores, fundo = _cores_gaveta()
    gpu.state.blend_set('ALPHA')
    _retangulo_gaveta(0, 0, largura, altura, fundo)
    _retangulo_gaveta(largura - 2, 0, 2, altura, (0.27, 0.27, 0.27, 1))
    widgets = _widgets_gaveta(context, largura, altura)
    # O cabecalho e' desenhado por ultimo, acima do conteudo rolavel.
    cabecalho, conteudo, rodape = _partes_gaveta(widgets)
    # A faixa do rodape (e o fundo do painel de opcoes) entra ENTRE o
    # conteudo e os botoes do rodape: o conteudo rola por baixo dela.
    faixa = (0, 0, 0, 0, '', ('faixa_rodape',))
    # Cada painel e' recortado no proprio retangulo: o da aba rola por
    # baixo do cabecalho e da divisoria, a biblioteca por baixo da
    # divisoria e do pe' fixo.
    cima, divisa, baixo = _paineis_gaveta(conteudo)
    meio = round(divisa[1] + divisa[3] / 2) if divisa else ALTURA_RODAPE_GAVETA
    recorte_cima = (0, meio + 1, largura, max(0, altura - 48 - meio - 1))
    recorte_baixo = (0, ALTURA_RODAPE_GAVETA, largura,
                     max(0, meio - ALTURA_RODAPE_GAVETA))
    recortes = ([recorte_cima] * len(cima) + [None] * bool(divisa)
                + [recorte_baixo] * len(baixo))
    for indice, (x, y, w, h, rotulo, acao) in enumerate(
            conteudo + [faixa] + rodape + cabecalho):
        painel = recortes[indice] if indice < len(recortes) else None
        if painel is not None:
            gpu.state.scissor_test_set(True)
            gpu.state.scissor_set(*(int(round(c)) for c in painel))
        else:
            gpu.state.scissor_test_set(False)
        if acao and acao[0] == 'divisa':
            _desenhar_divisa_gaveta(context, largura, meio, acao, cores)
            continue
        if acao == ('faixa_rodape',):
            _retangulo_gaveta(0, 0, largura, ALTURA_RODAPE_GAVETA, fundo)
            _retangulo_gaveta(0, ALTURA_RODAPE_GAVETA - 1, largura, 1,
                              (*cores.outline[:3], 1))
            painel = _retangulo_painel_opcoes(rodape)
            if painel is not None:
                px, py, pw, ph = painel
                _retangulo_arredondado_gaveta(px - 1, py - 1, pw + 2, ph + 2,
                                              6, (*cores.outline[:3], 1))
                _retangulo_arredondado_gaveta(px, py, pw, ph, 5, fundo)
            continue
        if y + h < 0 or y > altura:
            continue
        if acao and acao[0] == 'separador':
            _retangulo_gaveta(x, y, w, h, (*cores.outline[:3], 1))
            continue
        if acao and acao[0] in {'fundo', 'suspenso', 'faixa', 'cor'}:
            chave = _chave_widget(acao)
            if chave:
                _glow_gaveta(x, y, w, h, 4, _valor_realce(context, chave),
                             cores.text)
            _desenhar_opcao_gaveta(context, x, y, w, h, rotulo, acao,
                                   cores, fundo)
            continue
        if acao and acao[0] == 'pergunta':
            # caixa PRETA: destaca que a gaveta espera uma resposta
            _retangulo_arredondado_gaveta(x - 1, y - 1, w + 2, h + 2, 6,
                                          (*cores.outline[:3], 1))
            _retangulo_arredondado_gaveta(x, y, w, h, 5, (0.0, 0.0, 0.0, 0.92))
            for i, linha in enumerate(rotulo.split('\n')):
                _texto_gaveta(x + 10, y + h - 22 - i * 15, linha, 11,
                              (1.0, 1.0, 1.0, 1.0))
            continue
        if acao and acao[0] == 'wireframe':
            _desenhar_wireframe_gaveta(x, y, *acao[1:], escala=w / 160.0)
            continue
        if acao and acao[0] == 'slider':
            tx, ty, tw = _trilho_miniaturas_gaveta(x, y, w, h)
            largura_rotulo = tx - x - 12
            if largura_rotulo >= 135:
                _texto_cabivel_gaveta(x, y + 8, rotulo, largura_rotulo, 11)
            else:
                _texto_cabivel_gaveta(x, y + 15, 'Tamanho das', largura_rotulo, 11)
                _texto_cabivel_gaveta(x, y + 2, 'miniaturas', largura_rotulo, 11)
            valor = (context.scene.chapa_tam_bloco - 2) / 6.0
            _retangulo_gaveta(tx, ty - 1.5, tw, 3, tuple(cores.inner))
            _retangulo_arredondado_gaveta(
                tx + tw * valor - 6, ty - 6, 12, 12, 6, (*cores.text, 1))
            continue
        if acao and acao[0] == 'preset':
            _botao_gaveta(x, y, w, h)
            lado = min(w - 10, h - 27)
            _retangulo_gaveta(x + 5, y + 22, lado, lado, fundo)
            # BLF e outros widgets podem alterar o blend antes da foto.
            gpu.state.blend_set('ALPHA')
            _desenhar_foto_gaveta(acao[1], x + 5, y + 22, lado, lado)
            _texto_cabivel_gaveta(x + 5, y + 5, rotulo, w - 10, 11)
            continue
        # A peca que esta' entrando (ou saindo) invade a area das setas.
        # O recorte faz o carrossel parecer uma janela por onde a fila
        # passa, em vez de pecas aparecendo do nada.
        recortado = bool(acao and acao[0] == 'navegar')
        if recortado:
            # trilho do carrossel DENTRO do recorte do painel
            trilho = (12 + 24, int(y) - 1, max(0, largura - 24 - 48), 27)
            if painel is not None:
                trilho = _intersecao_retangulos(trilho, painel)
            gpu.state.scissor_test_set(True)
            gpu.state.scissor_set(*(int(round(c)) for c in trilho))

        ativo = bool(acao and (acao[0] in {'navegar', 'modo'} and acao[-1]
                               or acao[0] == 'escolha' and acao[3]
                               or acao[0] in BOTOES_CRIAR and acao[2]
                               # comparar, nunca hashear: a acao de preset
                               # e item da biblioteca leva um dict (v140:
                               # um set aqui derrubava a gaveta inteira)
                               or acao[0] == 'operador'
                               and acao[1] in (OP_CORRENTE_OBJETO,
                                               OP_RESETAR_DISTANCIA,
                                               OP_EXPORTAR_ORCAMENTO)
                               and len(acao) > 2 and acao[2]))
        # O halo vai ANTES do corpo do botao, como na alca: por cima
        # ele lavaria o texto em vez de circundar o widget.
        chave = _chave_widget(acao)
        if chave:
            _glow_gaveta(x, y, w, h, 4, _valor_realce(context, chave),
                         cores.text)
        apagado = bool(acao and acao[0] in BOTOES_CRIAR and len(acao) > 4
                       and acao[4]) or _operador_apagado(acao)
        # "Criar Portas" LARANJA desde o inicio (pedido do usuario): e' o
        # ponto de partida da aba; mais forte enquanto marca o vao
        cor = None
        if acao and acao[0] in BOTOES_CRIAR and not apagado:
            cor = COR_CRIAR_PORTAS_ATIVO if acao[2] else COR_CRIAR_PORTAS
        if not acao or acao[0] != 'cadeado':
            _botao_gaveta(x, y, w, h, ativo=ativo,
                          secao=acao is None or apagado, cor=cor)
        if acao and acao[0] == 'medida':
            edicao = _edicao_gaveta[0]
            editando = (edicao is not None and edicao['area'] == context.area.as_pointer()
                        and edicao['propriedade'] == acao[2])
            if editando:
                _botao_gaveta(x, y, w, h, ativo=True)
            # Espessura fora do convencional (> 60 mm): nome e valor em
            # vermelho. Alerta, nao trava -- o valor e' o que foi pedido.
            alerta = _cor_alerta_gaveta() if _medida_em_alerta(acao) else None
            _texto_cabivel_gaveta(x + 7, y + h - 14,
                                   acao[3], w - 14, 11, cor=alerta)
            valor = _texto_medida(acao[4])
            if editando:
                texto, cursor = edicao['texto'], edicao['cursor']
                valor = texto[:cursor] + '|' + texto[cursor:]
            _texto_cabivel_gaveta(x + 7, y + 6,
                                   valor, w - 14, 12, cor=alerta)
        elif acao and acao[0] in BOTOES_CRIAR:
            # "Criar Portas"/"Criar Puxador": largo, texto CENTRALIZADO
            blf.size(0, 12)
            largura_texto = min(blf.dimensions(0, rotulo)[0], w - 18)
            _texto_cabivel_gaveta(
                x + (w - largura_texto) / 2, y + (h - 12) / 2, rotulo, w - 18,
                cor=(*cores.text[:3], 0.4) if apagado else (1.0, 1.0, 1.0, 1.0))
        elif not _icone_acao_gaveta(acao):
            _texto_cabivel_gaveta(
                x + 9, y + (h - 12) / 2, rotulo, w - 18,
                cor=(*cores.text[:3], 0.4) if apagado else None)
        if recortado:
            gpu.state.scissor_test_set(False)
    gpu.state.scissor_test_set(False)
    _retangulo_gaveta(0, altura - 48, largura, 48,
                       fundo)
    for x, y, w, h, rotulo, acao in cabecalho:
        _glow_gaveta(x, y, w, h, 4,
                     _valor_realce(context, _chave_widget(acao)), cores.text)
        if acao[0] != 'aba':
            continue        # corrente: so' o icone, desenhado pelo gizmo
        _botao_gaveta(x, y, w, h,
                       ativo=context.scene.cabinet_aba == acao[1])
        _texto_cabivel_gaveta(x + 9, y + 8, rotulo, w - 18)
    gpu.state.blend_set('NONE')


def _unidade_nos_numeros_soltos(texto, sufixo):
    """"60 + 5mm" -> "60cm + 5mm" (com padrao cm).

    Sozinho, o parser do Blender da' a um numero sem unidade a unidade
    do VIZINHO -- 60 virava 60 mm. A regra combinada e' outra: sem
    unidade, vale a padrao. So' parcelas de soma/subtracao recebem o
    sufixo; fator de * ou / (o 2 de "2*30cm") continua numero puro.
    """
    fichas = re.findall(r'\d+\.?\d*|\.\d+|[A-Za-z]+|\S', texto)
    if not any(f.isalpha() for f in fichas):
        return texto          # sem unidade nenhuma: str_ref_unit resolve
    saida = []
    for i, ficha in enumerate(fichas):
        saida.append(ficha)
        if not (ficha[0].isdigit() or ficha[0] == '.'):
            continue
        antes = fichas[i - 1] if i > 0 else ''
        depois = fichas[i + 1] if i + 1 < len(fichas) else ''
        if depois.isalpha() or antes in {'*', '/'} or depois in {'*', '/'}:
            continue
        saida.append(sufixo)
    return ' '.join(saida)


_UNIDADE_RE = r'(?:mm|cm|m)(?![a-z])'


def _arrumar_texto_medida(texto):
    """O que o cursor livre deixa escrever e o usuario quer dizer:

    - "51cm00" (unidade digitada no MEIO do numero) -> "5100cm";
    - "500 + cm" (operador sem numero antes da unidade) -> "500cm";
    - "500 +" (conta pela metade) -> "500".
    """
    anterior = None
    while anterior != texto:
        anterior = texto
        texto = re.sub(r'(\d[\d.]*)(mm|cm|m)(\d[\d.]*)(?![a-z\d.])',
                       r'\1\3\2', texto, flags=re.I)
    texto = re.sub(r'\s*[+\-*/]\s*(?=' + _UNIDADE_RE + ')', '', texto,
                   flags=re.I)
    return re.sub(r'[\s+\-*/]+$', '', texto)


OPERADORES_MEDIDA = '+-*/'
LIMITE_TEXTO_MEDIDA = 80


def _tecla_no_texto(estado, tipo, entrada='', ctrl=False):
    """Uma tecla na caixa de digitar medida (HUD e gaveta). `estado` tem
    texto, cursor e selecionado (o texto inteiro, como a caixa abre).

    Pedido do usuario: um OPERADOR com o texto selecionado CONTINUA a
    conta em vez de apagar ("600" e '+' -> "600 + "). Devolve False se a
    tecla nao e' de edicao.
    """
    texto = estado['texto']
    cursor = min(estado.get('cursor', len(texto)), len(texto))
    if ctrl and tipo == 'A':
        estado['selecionado'] = True
        return True
    if tipo in {'LEFT_ARROW', 'RIGHT_ARROW', 'HOME', 'END'}:
        if tipo == 'HOME':
            cursor = 0
        elif tipo == 'END':
            cursor = len(texto)
        else:
            cursor += -1 if tipo == 'LEFT_ARROW' else 1
        estado.update(cursor=max(0, min(len(texto), cursor)), selecionado=False)
        return True
    entrada = ''.join(c for c in entrada if c.isprintable())[:LIMITE_TEXTO_MEDIDA]
    if not entrada and tipo not in {'BACK_SPACE', 'DEL'}:
        return False
    if estado.get('selecionado'):
        operador = entrada.strip()
        if len(operador) == 1 and operador in OPERADORES_MEDIDA and texto.strip():
            texto = (texto.rstrip() + ' ' + operador + ' ')[:LIMITE_TEXTO_MEDIDA]
            estado.update(texto=texto, cursor=len(texto), selecionado=False)
            return True
        texto, cursor = '', 0
    elif entrada:
        pass
    elif tipo == 'BACK_SPACE' and cursor:
        texto = texto[:cursor - 1] + texto[cursor:]
        cursor -= 1
    elif tipo == 'DEL':
        texto = texto[:cursor] + texto[cursor + 1:]
    if entrada in tuple(OPERADORES_MEDIDA) and texto[:cursor].strip():
        # Operador DIGITADO sai sempre com um espaco de cada lado, em
        # qualquer ponto da conta: "100+25" ficava fora do padrao de
        # "664 - 100" (print do usuario). Colado, entra como veio.
        antes = texto[:cursor].rstrip() + ' ' + entrada + ' '
        texto, cursor = antes + texto[cursor:].lstrip(), len(antes)
    elif entrada:
        texto = texto[:cursor] + entrada + texto[cursor:]
        cursor += len(entrada)
    texto = texto[:LIMITE_TEXTO_MEDIDA]
    estado.update(texto=texto, cursor=min(cursor, len(texto)),
                  selecionado=False)
    return True


def _cursor_no_x(texto, cursor, x_texto, mouse_x, largura):
    """Posicao do texto mais perto de um clique em x. O texto aparece com
    a barra '|' no cursor: depois dela as posicoes andam a largura dela.
    `largura(texto)` mede em pixels (blf no Blender)."""
    def x_de(i):
        mostrado = (texto[:i] if i <= cursor
                    else texto[:cursor] + '|' + texto[cursor:i])
        return x_texto + largura(mostrado)
    return min(range(len(texto) + 1), key=lambda i: abs(x_de(i) - mouse_x))


def _medidor_blf(tamanho):
    def largura(texto):
        blf.size(0, tamanho)
        return blf.dimensions(0, texto)[0]
    return largura


def _com_cursor(texto, cursor):
    cursor = min(cursor, len(texto))
    return texto[:cursor] + '|' + texto[cursor:]


def _ler_medida_digitada(texto):
    """Texto digitado -> metros.

    Aceita conta e unidades misturadas: "600 + 500", "600cm + 500mm",
    "1m - 20mm", "(600+500)/2". Numero sem unidade vale a unidade padrao
    das opcoes (mm de fabrica); virgula decimal tambem. O parser do
    Blender devolve ruido de float (1100.0001): arredonda em 0,01 mm.
    ValueError se nao for uma medida de 1 mm ou mais.
    """
    texto = _arrumar_texto_medida(texto.strip().replace(',', '.'))
    sufixo = UNIDADES_MEDIDA[_opcao('unidade_padrao')][1]
    texto = _unidade_nos_numeros_soltos(texto, sufixo)
    valor = bpy.utils.units.to_value('METRIC', 'LENGTH', texto,
                                     str_ref_unit='1 ' + sufixo)
    if not math.isfinite(valor) or valor < 0.001 - 1e-9:
        raise ValueError('Informe uma medida de pelo menos 1 mm')
    return round(valor * 1000.0, 2) / 1000.0


def _ler_numero_digitado(texto):
    """Numero puro das faixas da engrenagem ("14", "1,5", "10 + 4",
    "18px"). Quem prende no minimo/maximo e' quem grava."""
    texto = texto.strip().replace(',', '.').lower().replace('px', '')
    valor = bpy.utils.units.to_value('NONE', 'NONE', texto)
    if not math.isfinite(valor):
        raise ValueError('Informe um numero')
    return valor


class OBJECT_OT_editar_medida_gaveta(Operator):
    """Edita uma medida usando a mesma propriedade parametrica do painel N."""
    bl_idname = 'object.cabinet_editar_medida_gaveta'
    bl_label = 'Editar Medida'
    bl_options = {'REGISTER', 'UNDO'}

    dono: StringProperty(options={'SKIP_SAVE'})
    objeto: StringProperty(options={'SKIP_SAVE'})
    propriedade: StringProperty(options={'SKIP_SAVE'})
    valor: FloatProperty(name='Medida', subtype='DISTANCE', unit='LENGTH',
                         min=0.001, options={'SKIP_SAVE'})

    def invoke(self, context, event):
        if _edicao_gaveta[0] is not None:
            return {'CANCELLED'}
        self._area = context.area
        texto = (_texto_faixa(self.valor)[:-3] if self.dono == 'opcao'
                 else _numero_na_unidade(self.valor * 1000.0))
        self._estado = {'area': context.area.as_pointer(),
                        'propriedade': self.propriedade, 'texto': texto,
                        'cursor': len(texto), 'selecionado': True}
        _edicao_gaveta[0] = self._estado
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _encerrar(self):
        _edicao_gaveta[0] = None
        self._area.tag_redraw()

    def cancel(self, context):
        self._encerrar()

    def modal(self, context, event):
        if _edicao_gaveta[0] is not self._estado:
            return {'CANCELLED'}
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self._encerrar()
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and self._clique_no_campo(context, event):
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type in {'RET', 'NUMPAD_ENTER', 'LEFTMOUSE', 'TAB'}:
            try:
                self.valor = (_ler_numero_digitado(self._estado['texto'])
                              if self.dono == 'opcao' else
                              _ler_medida_digitada(self._estado['texto']))
            except (ValueError, TypeError) as e:
                self.report({'WARNING'}, str(e))
                return {'RUNNING_MODAL'}
            resultado = self.execute(context)
            self._encerrar()
            return resultado
        entrada = (context.window_manager.clipboard
                   if event.ctrl and event.type == 'V'
                   else '' if event.ctrl else event.unicode or '')
        if _tecla_no_texto(self._estado, event.type, entrada, event.ctrl):
            self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _clique_no_campo(self, context, event):
        """Clique DENTRO do campo em edicao: so' move o cursor (fora dele,
        confirma). As posicoes saem do mesmo calculo do desenho."""
        estado = self._estado
        mx, my = event.mouse_region_x, event.mouse_region_y
        try:
            widgets = _widgets_interativos(context)
        except Exception:
            return False
        for x, y, w, h, _r, acao in widgets:
            if not acao or not (x <= mx <= x + w and y <= my <= y + h):
                continue
            if not (acao[0] == 'medida' and acao[2] == estado['propriedade']
                    or acao[0] == 'faixa' and acao[1] == estado['propriedade']):
                continue
            texto, cursor = estado['texto'], estado['cursor']
            mostrado = _com_cursor(texto, cursor)
            disponivel = w - (14 if acao[0] == 'medida' else 12)
            tamanho = next((t for t in range(12, 8, -1)
                            if _medidor_blf(t)(mostrado) <= disponivel), 9)
            largura = _medidor_blf(tamanho)
            x_texto = (x + 7 if acao[0] == 'medida'
                       else x + (w - min(largura(mostrado), disponivel)) / 2)
            estado['cursor'] = _cursor_no_x(texto, cursor, x_texto, mx, largura)
            estado['selecionado'] = False
            return True
        return False

    def execute(self, context):
        if self.dono == 'opcao':
            # Faixa da engrenagem: numero puro, preso ao minimo e maximo
            minimo, maximo, _passo = FAIXAS_OPCOES[self.propriedade]
            valor = max(minimo, min(maximo, self.valor))
            _definir_opcao(self.propriedade, int(round(valor))
                           if isinstance(minimo, int) else round(valor, 2))
            return {'FINISHED'}
        if self.dono == 'puxador' and self.propriedade.startswith('puxp_'):
            # parametrico: grava o estado e deixa a chapa reposicionar
            pux = bpy.data.objects.get(self.objeto)
            if not _eh_puxador_parametrico(pux):
                self.report({'WARNING'}, 'Puxador nao encontrado')
                return {'CANCELLED'}
            pux['puxador_%s_mm' % self.propriedade[len('puxp_'):]] = (
                self.valor * 1000.0)
            posicionar_puxador(pux)
            return {'FINISHED'}
        if self.dono == 'puxador':
            pux = bpy.data.objects.get(self.objeto)
            try:
                _redimensionar_puxador(pux, int(self.propriedade[-1]),
                                       self.valor * 1000.0)
            except (ValueError, TypeError, AttributeError) as erro:
                self.report({'WARNING'}, str(erro))
                return {'CANCELLED'}
            return {'FINISHED'}
        if self.dono == 'porta':
            # Porta colocada: a medida e' um parametro do GRUPO, nao uma
            # propriedade de objeto ou da cena.
            grupo = _grupo_portas(bpy.data.objects.get(self.objeto))
            nome = _PARAMETRO_DA_MEDIDA_PORTA.get(self.propriedade)
            erro = (_editar_parametro_porta(context, grupo, nome,
                                            self.valor * 1000.0)
                    if grupo is not None and nome else
                    'Porta da medida nao encontrada')
            if erro:
                self.report({'WARNING'}, erro)
                return {'CANCELLED'}
            return {'FINISHED'}
        alvo = (context.scene if self.dono == 'cena'
                else bpy.data.objects.get(self.objeto))
        if alvo is None:
            self.report({'WARNING'}, 'Alvo da medida nao encontrado')
            return {'CANCELLED'}
        if self.dono == 'livre' and self.propriedade.startswith('dimensions_'):
            indice = int(self.propriedade[-1])
            dimensoes = list(alvo.dimensions)
            dimensoes[indice] = self.valor
            alvo.dimensions = dimensoes
            return {'FINISHED'}
        if not hasattr(alvo, self.propriedade):
            self.report({'WARNING'}, 'Propriedade da medida nao encontrada')
            return {'CANCELLED'}
        setattr(alvo, self.propriedade, self.valor)
        return {'FINISHED'}


class OBJECT_OT_interagir_gaveta(Operator):
    """Recebe clique e arraste diretamente na interface independente."""
    bl_idname = "object.cabinet_interagir_gaveta"
    bl_label = "Interagir com Gaveta Cabinet Creator"

    @classmethod
    def poll(cls, context):
        return _eh_area_gaveta(context)

    def invoke(self, context, event):
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            for wx, wy, w, h, _, acao in _widgets_gaveta(
                    context, context.region.width, context.region.height):
                if (acao and acao[0] in {'navegar', 'rolar_nivel'}
                        and wx <= event.mouse_region_x <= wx + w
                        and wy <= event.mouse_region_y <= wy + h):
                    chave, limite = ((acao[3], acao[4]) if acao[0] == 'navegar'
                                     else (acao[1], acao[3]))
                    passo = -1 if event.type == 'WHEELUPMOUSE' else 1
                    context.screen[chave] = max(0, min(limite,
                        int(context.screen.get(chave, 0)) + passo))
                    context.area.tag_redraw()
                    return {'FINISHED'}
            # Rola o painel que esta' sob o mouse: a aba em cima da
            # divisoria, a biblioteca embaixo.
            limites = _limites_rolagem_gaveta(
                context, context.region.width, context.region.height)
            de_baixo = event.mouse_region_y < _divisa_gaveta(
                context, context.region.height)
            chave = _CHAVE_ROLAGEM_BIB if de_baixo else _CHAVE_ROLAGEM
            limite = limites[1] if de_baixo else limites[0]
            atual = max(0, min(limite, int(context.screen.get(chave, 0))))
            passo = -85 if event.type == 'WHEELUPMOUSE' else 85
            context.screen[chave] = max(0, min(limite, atual + passo))
            context.area.tag_redraw()
            return {'FINISHED'}
        x, y = event.mouse_region_x, event.mouse_region_y
        for wx, wy, w, h, _rotulo, acao in _widgets_interativos(context):
            if acao and acao[0] == 'pergunta':
                # a caixa preta vem ANTES das respostas (fica por baixo no
                # desenho) e as contem: no clique ela nao pode engolir o
                # "Sim"/"Nao" -- quem atende sao os botoes
                continue
            dentro = wx <= x <= wx + w and wy <= y <= wy + h
            if acao and acao[0] == 'slider':
                tx, ty, tw = _trilho_miniaturas_gaveta(wx, wy, w, h)
                dentro = tx - 6 <= x <= tx + tw + 6 and abs(y - ty) <= h / 2
            if not dentro:
                continue
            # Lista suspensa aberta fecha com qualquer clique que nao
            # seja no proprio campo (a escolha grava e fecha junto)
            if not (acao and acao[0] == 'suspenso'):
                _fechar_suspenso(context)
            if acao is None:
                return {'FINISHED'}
            if acao[0] in {'wireframe', 'separador', 'fundo', 'pergunta'}:
                return {'FINISHED'}
            if acao[0] == 'aba':
                context.scene.cabinet_aba = acao[1]
                context.screen[_CHAVE_ROLAGEM] = 0
                _fechar_opcoes(context.screen)
            elif acao[0] == 'suspenso':
                context.screen[_CHAVE_SUSPENSO] = '' if acao[2] else acao[1]
            elif acao[0] == 'faixa':
                self._faixa = {'acao': acao, 'x': wx, 'w': w, 'inicio': x,
                               'arrastou': False}
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            elif acao[0] == 'cor' and acao[2] == 'amostra':
                context.screen[_CHAVE_COR] = '' if acao[4] else acao[1]
            elif acao[0] == 'cor' and acao[2] == 'atalho':
                if acao[5] in OPCAO_DO_ESPECIAL:
                    _definir_opcao(OPCAO_DO_ESPECIAL[acao[5]], True)
                else:
                    _aplicar_cor_opcao(acao[1], acao[3])
            elif acao[0] == 'cor':
                # quadro ou matiz: a cor segue o mouse enquanto segura
                self._cor = {'acao': acao, 'ret': (wx, wy, w, h),
                             'original': (_opcao(acao[1]), {
                                 n: _opcao(n) for n in OPCAO_DO_ESPECIAL.values()})}
                self._arrastar_cor(context, x, y)
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            elif acao[0] == 'divisa':
                if not acao[1]:
                    return {'FINISHED'}
                self._divisa = float(context.screen.get(
                    _CHAVE_DIVISA, DIVISA_PADRAO))
                context.window.cursor_modal_set('MOVE_Y')
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            elif acao[0] == 'navegar':
                self._carrossel = acao
                self._mouse_inicio = x
                self._indice_inicio = int(context.screen.get(acao[3], 0))
                self._arrastou = False
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            elif acao[0] == 'rolar_nivel':
                context.screen[acao[1]] = max(0, min(acao[3],
                    int(context.screen.get(acao[1], 0)) + acao[2]))
            elif acao[0] == 'modo':
                pass        # indicador: um objeto = individual, mais = grupo
            elif acao[0] == 'medida':
                if acao[2]:
                    bpy.ops.object.cabinet_editar_medida_gaveta(
                        'INVOKE_DEFAULT', dono=acao[1],
                        objeto=context.object.name if context.object else '',
                        propriedade=acao[2], valor=acao[4] / 1000.0)
            elif acao[0] == 'escolha':
                grupo = (bpy.data.objects.get(acao[5])
                         if len(acao) > 5 and acao[5] else None)
                if not acao[4]:
                    pass
                elif len(acao) > 5 and acao[5] == ALVO_PREFERENCIAS:
                    _definir_opcao(acao[1], acao[2])
                elif len(acao) > 5 and acao[5] == ALVO_COMODO:
                    if acao[2] == COMODO_OUTRO:
                        _abrir_caixa_comodo(context)
                        if _abrir_pergunta(context):
                            bpy.ops.object.cabinet_digitar_nome_grupo(
                                'INVOKE_DEFAULT')
                    else:
                        bpy.ops.object.cabinet_definir_comodo(nome=acao[2])
                elif grupo is not None:
                    # Porta ja' colocada: muda ela, na hora
                    erro = _editar_parametro_porta(
                        context, grupo, acao[1][len('porta_'):], acao[2])
                    if erro:
                        self.report({'WARNING'}, erro)
                    else:
                        bpy.ops.ed.undo_push(message='Editar porta')
                else:
                    setattr(context.scene, acao[1], acao[2])
            elif acao[0] == 'cadeado':
                pux = bpy.data.objects.get(acao[1])
                if pux is not None:
                    travas = list(pux.get(CHAVE_TRAVAS_PUXADOR, (1, 1, 1)))
                    travas[acao[2]] = 0 if travas[acao[2]] else 1
                    pux[CHAVE_TRAVAS_PUXADOR] = travas
                    bpy.ops.ed.undo_push(message='Cadeado do puxador')
            elif acao[0] == 'criar_puxador':
                if not acao[2]:         # ja' posicionando: Esc cancela
                    bpy.ops.object.cabinet_posicionar_puxador('INVOKE_DEFAULT')
            elif acao[0] == 'portas':
                if acao[3]:
                    self.report({'WARNING'}, acao[3])
                elif acao[2] or acao[1]:
                    # ja' marcando o vao, ou porta selecionada: criar
                    # outra porta e' a partir do modulo (clique simples)
                    pass
                else:
                    bpy.ops.object.cabinet_apanhar_vao('INVOKE_DEFAULT')
            elif acao[0] == 'preset':
                it = acao[1]
                bpy.ops.object.cabinet_arrastar_preset(
                    'INVOKE_DEFAULT', pasta=it['pasta'],
                    arquivo=it['arquivo'], tipo=it.get('tipo', 'modulo'))
            elif acao[0] == 'item':
                it, indice = acao[1], acao[2]
                if indice == 0:
                    bpy.ops.object.cabinet_inserir_preset(
                        pasta=it['pasta'], arquivo=it['arquivo'],
                        tipo=it.get('tipo', 'modulo'))
                elif indice == 1:
                    if not item_bloqueado(it):
                        bpy.ops.object.cabinet_editar_modelo(
                            'INVOKE_DEFAULT', pasta=it['pasta'],
                            arquivo=it['arquivo'])
                else:
                    bpy.ops.object.cabinet_bloqueio(
                        pasta=it['pasta'], arquivo=it['arquivo'])
            elif acao[0] == 'slider':
                self._inicio, _, self._largura = _trilho_miniaturas_gaveta(
                    wx, wy, w, h)
                self._atualizar(context, x)
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            elif acao[0] == 'resposta':
                bpy.ops.object.cabinet_responder_pergunta(opcao=acao[1])
            elif _operador_apagado(acao):
                pass            # apagado: a selecao nao serve, nada a fazer
            elif acao[1] in OPERADORES_NO_SOLTAR:
                # Dispara no SOLTAR, como botao do Blender: o pop-up que
                # ele abre ("tem certeza?") nasceria sob o mouse e o
                # RELEASE deste mesmo clique ja' escolheria a 1a opcao
                # (visto no teste de interface: desagregava sem perguntar).
                self._no_soltar = acao[1]
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            else:
                _na_gaveta[0] = True
                try:
                    modulo, nome = acao[1].split('.')
                    getattr(getattr(bpy.ops, modulo), nome)('INVOKE_DEFAULT')
                except Exception as e:
                    self.report({'WARNING'}, str(e))
                finally:
                    _na_gaveta[0] = False
            context.area.tag_redraw()
            return {'FINISHED'}
        _fechar_suspenso(context)       # clique no vazio tambem fecha
        return {'FINISHED'}

    def _atualizar(self, context, x):
        fracao = min(1.0, max(0.0, (x - self._inicio) / self._largura))
        context.scene.chapa_tam_bloco = 2 + round(fracao * 6)
        context.area.tag_redraw()

    def _arrastar_cor(self, context, x, y):
        acao = self._cor['acao']
        rx, ry, rw, rh = self._cor['ret']
        _aplicar_cor_opcao(acao[1], _cor_do_seletor(
            acao[1], acao[2], _cor_opcao(acao[1]),
            (x - rx) / rw, (y - ry) / rh))
        context.area.tag_redraw()

    def _modal_opcao(self, context, event):
        """Arraste da faixa ou do seletor de cor do painel de opcoes."""
        faixa = getattr(self, '_faixa', None)
        if event.type == 'MOUSEMOVE':
            if faixa is None:
                self._arrastar_cor(context, event.mouse_region_x,
                                   event.mouse_region_y)
                return {'RUNNING_MODAL'}
            if abs(event.mouse_region_x - faixa['inicio']) > LIMIAR_ARRASTE_HUD_PX:
                faixa['arrastou'] = True
            if faixa['arrastou']:
                nome = faixa['acao'][1]
                _definir_opcao(nome, _valor_da_faixa(
                    nome, (event.mouse_region_x - faixa['x']) / faixa['w']))
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if faixa is not None and not faixa['arrastou']:
                # clique sem arrastar: digita o valor, como nas medidas
                bpy.ops.object.cabinet_editar_medida_gaveta(
                    'INVOKE_DEFAULT', dono='opcao',
                    propriedade=faixa['acao'][1],
                    valor=float(_opcao(faixa['acao'][1])))
            context.area.tag_redraw()
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            if faixa is not None:
                _definir_opcao(faixa['acao'][1], faixa['acao'][2])
            else:
                nome = self._cor['acao'][1]
                cor, especiais = self._cor['original']
                _definir_opcao(nome, cor)
                for n, v in especiais.items():
                    _definir_opcao(n, v)
            context.area.tag_redraw()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def _modal_divisa(self, context, event):
        """Arraste da divisoria aba | biblioteca (sobe ou desce)."""
        if event.type == 'MOUSEMOVE':
            context.screen[_CHAVE_DIVISA] = _fracao_divisa(
                context.region.height, event.mouse_region_y)
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            # grava a posicao JA' limitada: assim a fracao nao fica
            # alem do minimo e o proximo arraste nao "pula"
            altura = context.region.height
            context.screen[_CHAVE_DIVISA] = _fracao_divisa(
                altura, _divisa_gaveta(context, altura))
            context.window.cursor_modal_restore()
            context.area.tag_redraw()
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            context.screen[_CHAVE_DIVISA] = self._divisa
            context.window.cursor_modal_restore()
            context.area.tag_redraw()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if hasattr(self, '_no_soltar'):
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                _na_gaveta[0] = True     # pergunta que nascer vem na gaveta
                try:
                    modulo, nome = self._no_soltar.split('.')
                    getattr(getattr(bpy.ops, modulo), nome)('INVOKE_DEFAULT')
                except Exception as e:
                    self.report({'WARNING'}, str(e))
                finally:
                    _na_gaveta[0] = False
                context.area.tag_redraw()
                return {'FINISHED'}
            if event.type in {'ESC', 'RIGHTMOUSE'}:
                return {'CANCELLED'}
            return {'RUNNING_MODAL'}
        if hasattr(self, '_divisa'):
            return self._modal_divisa(context, event)
        if hasattr(self, '_faixa') or hasattr(self, '_cor'):
            return self._modal_opcao(context, event)
        if hasattr(self, '_carrossel'):
            acao = self._carrossel
            if event.type == 'MOUSEMOVE':
                delta = self._mouse_inicio - event.mouse_region_x
                if abs(delta) > 6:
                    self._arrastou = True
                context.screen[acao[3]] = max(0, min(acao[4],
                    self._indice_inicio + round(delta / 60)))
                context.area.tag_redraw()
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                if not self._arrastou:
                    bpy.ops.object.cabinet_navegar(nivel=acao[1], valor=acao[2])
                context.area.tag_redraw()
                return {'FINISHED'}
            if event.type in {'ESC', 'RIGHTMOUSE'}:
                context.screen[acao[3]] = self._indice_inicio
                context.area.tag_redraw()
                return {'CANCELLED'}
            return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE':
            self._atualizar(context, event.mouse_region_x)
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class OBJECT_OT_opcoes_gaveta(Operator):
    """Opcoes: unidade padrao, linhas e rotulos das medidas"""
    bl_idname = "object.cabinet_opcoes_gaveta"
    bl_label = "Opcoes do Cabinet Creator"

    def execute(self, context):
        tela = context.screen
        aberto = tela.get(_CHAVE_OPCOES)
        _fechar_opcoes(tela)
        tela[_CHAVE_OPCOES] = 0 if aberto else 1
        tela[_CHAVE_ROLAGEM] = 0
        for area in tela.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}


class OBJECT_OT_alternar_gaveta(Operator):
    """Abre ou fecha a area exclusiva do addon a esquerda da viewport"""
    bl_idname = "object.cabinet_alternar_gaveta"
    bl_label = "Alternar Gaveta Cabinet Creator"

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and not _eh_area_gaveta(context))

    def execute(self, context):
        screen = context.screen
        painel = _area_gaveta(screen)
        if painel is not None:
            janela = context.window
            screen[_CHAVE_GAVETA] = 0
            try:
                with context.temp_override(window=janela, screen=screen,
                                           area=painel):
                    bpy.ops.screen.area_close()
            except Exception as e:
                screen[_CHAVE_GAVETA] = str(painel.as_pointer())
                self.report({'WARNING'}, "Nao consegui fechar a gaveta: %s" % e)
                return {'CANCELLED'}
            return {'FINISHED'}
        # Corrige o estado deixado pela versao antiga da gaveta, que
        # invertia a regiao N inteira para a esquerda.
        ui = next((r for r in context.area.regions if r.type == 'UI'), None)
        if ui is not None and ui.alignment == 'LEFT':
            with context.temp_override(area=context.area, region=ui):
                bpy.ops.screen.region_flip()
        screen[_CHAVE_PENDENTE] = str(context.area.as_pointer())
        try:
            # Teto de metade da viewport: numa tela estreita a gaveta
            # abre menor que o padrao, mas nunca engole a cena.
            largura = context.area.width
            fator = max(0.08, min(0.5, _largura_inicial_gaveta(context)
                                  / largura))
            with context.temp_override(area=context.area):
                bpy.ops.screen.area_split(direction='VERTICAL', factor=fator)
        except Exception as e:
            screen[_CHAVE_PENDENTE] = 0
            self.report({'WARNING'}, "Nao consegui abrir a gaveta: %s" % e)
            return {'CANCELLED'}
        if not bpy.app.timers.is_registered(_configurar_gavetas):
            bpy.app.timers.register(_configurar_gavetas, first_interval=0.05)
        return {'FINISHED'}


def _poll_operador(idname):
    try:
        modulo, nome = idname.split('.')
        return getattr(getattr(bpy.ops, modulo), nome).poll()
    except Exception:
        return False


def _operador_apagado(acao):
    """Botao de TEXTO cujo operador recusa a selecao atual: sai cinza,
    sem brilho e sem clique. (Botao de icone ja' esmaece pelo gizmo.)"""
    return bool(acao and acao[0] == 'operador'
                and not _icone_acao_gaveta(acao)
                and not _poll_operador(acao[1]))


def _icone_acao_gaveta(acao):
    if not acao:
        return None
    if acao[0] == 'operador':
        return {'object.cabinet_agrupar': 'GROUP',
                'object.cabinet_detectar_adjacencia': 'SNAP_ON',
                OP_CORRENTE_OBJETO: 'LINKED',
                OP_RESETAR_DISTANCIA: 'DRIVER_DISTANCE',
                'object.cabinet_normalizar': 'FILE_REFRESH',
                'object.cabinet_converter_modulo': 'IMPORT',
                'object.cabinet_opcoes_gaveta': 'PREFERENCES',
                'object.cabinet_vincular_porta': 'LINKED',
                'object.cabinet_vincular_puxador': 'LINKED',
                'object.cabinet_abrir_biblioteca': 'FILE_FOLDER',
                'object.cabinet_prateleira': 'ASSET_MANAGER',
                'object.cabinet_salvar_biblioteca': 'FILE_TICK'}.get(acao[1])
    if acao[0] == 'cadeado':
        return 'LOCKED' if acao[3] else 'UNLOCKED'
    if acao[0] == 'item':
        return ('IMPORT', 'GREASEPENCIL',
                'LOCKED' if item_bloqueado(acao[1]) else 'UNLOCKED')[acao[2]]
    if acao[0] == 'rolar_nivel':
        return 'TRIA_LEFT' if acao[2] < 0 else 'TRIA_RIGHT'
    return None


class VIEW3D_GT_alca_gaveta(Gizmo):
    """Hit-test da alca; o desenho unico fica no callback POST_PIXEL."""
    bl_idname = 'VIEW3D_GT_alca_gaveta'

    def draw(self, context):
        pass

    def test_select(self, context, location):
        x, y = location
        centro = max(48, context.region.height * 0.12)
        return 0 if 0 <= x <= 26 and abs(y - centro) <= 35 else -1


class VIEW3D_GGT_cabinet_gaveta(GizmoGroup):
    """Alca e icones nativos na interface independente."""
    bl_idname = "VIEW3D_GGT_cabinet_gaveta"
    bl_label = "Alca Cabinet Creator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'SCALE'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def setup(self, context):
        self.botoes = []
        self.campos = []
        alca = self.gizmos.new('VIEW3D_GT_alca_gaveta')
        alca.target_set_operator("object.cabinet_alternar_gaveta")
        alca.use_tooltip = True
        self.alca = alca

    def _preparar_hover(self, context, acesos_por_icone):
        """Um gizmo invisivel por widget clicavel, so' para ter hover.

        Vale para QUALQUER botao da gaveta, nao so' os campos de
        medida: o retangulo sob o mouse acende com o mesmo glow da
        alca. `acesos_por_icone` traz os widgets cujo gizmo de icone ja'
        esta' destacado, porque nesses o disco do icone fica fora do
        hit-test daqui (para nao roubar o tooltip dele).
        """
        # A faixa de 48 px do topo pertence ao cabecalho; so' as abas
        # sao clicaveis ali. Mesmo criterio do operador de clique.
        alvos = [v for v in _widgets_interativos(context)
                 if _chave_widget(v[5]) and v[1] >= 0]
        while len(self.campos) < len(alvos):
            campo = self.gizmos.new('VIEW3D_GT_campo_gaveta')
            # O clique cai no mesmo operador que a keymap ja' dispara
            # para a area inteira, entao clicar continua igual.
            campo.target_set_operator('object.cabinet_interagir_gaveta')
            campo.use_tooltip = False
            self.campos.append(campo)

        escala = max(1.0, context.preferences.system.ui_scale)
        _campos_gaveta.clear()
        acesos = set(acesos_por_icone)
        for campo, (x, y, w, h, _rotulo, acao) in zip(self.campos, alvos):
            campo.hide = False
            icone = None
            if _icone_acao_gaveta(acao):
                cx = x + w / 2
                icone = (cx, y + h / 2, 13.0 * escala)
            _campos_gaveta[campo.as_pointer()] = (x, y, w, h, icone)
            if campo.is_highlight:
                acesos.add(_chave_widget(acao))

        # Edicao aberta manda mais que o mouse: com o campo em foco o
        # usuario ja' esta' digitando aquela medida, ainda que o cursor
        # tenha saido de cima dele.
        medida_ativa = next(
            (v[5][3] for v in alvos if v[5][0] == 'medida'
             and _chave_widget(v[5]) in acesos), None)
        edicao = _edicao_gaveta[0]
        if edicao is not None:
            em_foco = next((v[5][3] for v in alvos if v[5][0] == 'medida'
                            and v[5][2] == edicao['propriedade']), None)
            if em_foco is not None:
                medida_ativa = em_foco
                acesos.add('medida:' + em_foco)

        for _x, _y, _w, _h, _rotulo, acao in alvos:
            chave = _chave_widget(acao)
            _realcar(context, chave, chave in acesos)
        _definir_realce_medida(medida_ativa)
        # Perto da divisoria o cursor vira a seta de redimensionar, como
        # na fronteira entre areas do Blender. So' na TRANSICAO: trocar a
        # cada redesenho brigaria com o cursor de quem mais o define.
        sobre = 'divisa' in acesos
        if sobre != _cursor_divisa[0]:
            _cursor_divisa[0] = sobre
            try:
                context.window.cursor_set('MOVE_Y' if sobre else 'DEFAULT')
            except Exception:
                pass

    def draw_prepare(self, context):
        gaveta = _eh_area_gaveta(context)
        self.alca.hide = gaveta
        for botao in self.botoes:
            botao.hide = True
        for campo in self.campos:
            campo.hide = True
        if gaveta:
            widgets = [v for v in _widgets_interativos(context)
                       if _icone_acao_gaveta(v[5]) and v[1] >= 0]
            assinatura = tuple(_icone_acao_gaveta(v[5]) for v in widgets)
            if assinatura != getattr(self, '_assinatura', None):
                for botao in self.botoes:
                    self.gizmos.remove(botao)
                self.botoes.clear()
                for icone in assinatura:
                    botao = self.gizmos.new('GIZMO_GT_button_2d')
                    botao.draw_options = set()
                    botao.icon = icone
                    botao.show_drag = False
                    botao.use_tooltip = True
                    self.botoes.append(botao)
                self._assinatura = assinatura
            cores, _ = _cores_gaveta()
            acesos_por_icone = set()
            for botao, (x, y, w, h, _, acao) in zip(self.botoes, widgets):
                botao.hide = False
                if botao.is_highlight:
                    acesos_por_icone.add(_chave_widget(acao))
                botao.color = cores.text
                # Corrente sem nada para ligar fica apagada: o poll do
                # operador e' o mesmo criterio que ele usa ao rodar.
                # Resetar sem solda fora da origem fica apagado
                apagado = (acao[0] == 'operador' and (
                    _no_cabecalho(acao) and not _poll_operador(acao[1])
                    or acao[1] == OP_RESETAR_DISTANCIA and not acao[2]))
                botao.alpha = 0.3 if apagado else 1
                botao.color_highlight = cores.text_sel
                botao.alpha_highlight = 0.3 if apagado else 1
                botao.hide_select = False
                botao.icon = _icone_acao_gaveta(acao)
                botao.scale_basis = 11
                botao.matrix_basis[0][3] = x + w / 2
                botao.matrix_basis[1][3] = y + h / 2
                if acao[0] == 'operador' and acao[1] in OPERADORES_NO_SOLTAR:
                    # o gizmo dispara no PRESS; a gaveta espera o soltar
                    botao.target_set_operator('object.cabinet_interagir_gaveta')
                elif acao[0] == 'operador':
                    botao.target_set_operator(acao[1])
                elif acao[0] in {'rolar_nivel', 'cadeado'}:
                    botao.target_set_operator('object.cabinet_interagir_gaveta')
                elif acao[0] == 'item':
                    it, indice = acao[1:]
                    nome = ('object.cabinet_inserir_preset',
                            'object.cabinet_editar_modelo',
                            'object.cabinet_bloqueio')[indice]
                    op = botao.target_set_operator(nome)
                    op.pasta, op.arquivo = it['pasta'], it['arquivo']
                    if indice == 0:
                        op.tipo = it.get('tipo', 'modulo')
                    botao.hide_select = indice == 1 and item_bloqueado(it)
            self._preparar_hover(context, acesos_por_icone)
            _desenhar_gaveta(tela=True)
            return
        _realcar(context, 'alca', self.alca.is_highlight)


class VIEW3D_PT_cabinet_creator(Panel):
    # O cabecalho e' a barra de abas; nao repetir um titulo ao lado dela.
    bl_label = ""
    bl_idname = "VIEW3D_PT_cabinet_creator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Cabinet Creator"
    bl_options = {'HEADER_LAYOUT_EXPAND'}

    @classmethod
    def poll(cls, context):
        return not _eh_area_gaveta(context)

    def draw_header(self, context):
        linha = self.layout.row(align=True)
        linha.prop(context.scene, 'cabinet_aba', expand=True)

    def draw(self, context):
        layout = self.layout
        if context.scene.cabinet_aba == 'PORTAS':
            self.desenhar_portas(context, layout)
        else:
            self.desenhar_medidas(context, layout)
            layout.separator()
            self.desenhar_biblioteca(context, layout)

    def desenhar_portas(self, context, layout):
        caixa = layout.box()
        caixa.label(text="Portas parametricas")
        grupo = _grupo_portas(context.object)
        if grupo is not None and context.mode == 'OBJECT':
            op = caixa.operator("object.cabinet_portas", text="Configurar Portas",
                                icon='PREFERENCES')
            op.editar = True
        else:
            caixa.label(text="2 vertices diagonais do vao interno")
            linha = caixa.row()
            linha.enabled = context.mode == 'EDIT_MESH'
            op = linha.operator("object.cabinet_portas", text="Criar Portas",
                                icon='MESH_CUBE')
            op.editar = False
            if context.mode != 'EDIT_MESH':
                caixa.label(text="Selecione as chapas e entre em Edicao")

    # ------------------------------------------------------- MEDIDAS
    def _abas_modo(self, layout, ativo):
        linha = layout.row(align=True)
        for modo, texto in (('INDIVIDUAL', "Individual"), ('GRUPO', "Grupo")):
            op = linha.operator(
                "object.cabinet_modo_medidas", text=texto,
                depress=(ativo == modo))
            op.modo = modo

    def _largura_logica(self, context):
        escala = max(0.5, float(context.preferences.system.ui_scale))
        return float(context.region.width) / escala

    def _painel_estreito(self, context):
        return self._largura_logica(context) < WIREFRAME_LARGURA_EMPILHAR_PX

    def _painel_muito_estreito(self, context):
        return (self._largura_logica(context) <
                MEDIDAS_LARGURA_COLUNA_UNICA_PX)

    def _escala_wireframe(self, context):
        """Escala responsiva com limites para nao sumir nem dominar o painel."""
        disponivel = max(0.0, self._largura_logica(context) - 24.0)
        escala = disponivel / 20.0
        maximo = (WIREFRAME_ESCALA_ESTREITA_MAX_UI
                  if self._painel_estreito(context)
                  else WIREFRAME_ESCALA_MAX_UI)
        return max(WIREFRAME_ESCALA_MIN_UI,
                   min(maximo, escala))

    def _corpo_medidas(self, caixa, context, separador=0.4):
        """Retorna controles e area visual, em linha ou empilhados."""
        estreito = self._painel_estreito(context)
        corpo = (caixa.column(align=True) if estreito
                 else caixa.row(align=False))
        if not estreito:
            # Afasta os controles da quina do box sem deslocar o preview.
            corpo.separator(factor=0.35)
        campos = corpo.column(align=True)
        # No modo estreito, toda a grade precisa usar o centro do box. Manter
        # este contêiner em LEFT faz o Blender compactar a largura útil pelo
        # tamanho natural dos widgets, deixando uma sobra maior à direita.
        campos.alignment = 'CENTER' if estreito else 'LEFT'
        if not estreito:
            # Reserva somente o necessario para rotulos e caixas. Uma coluna
            # maior comprime o preview na area direita antes da quebra.
            campos.ui_units_x = MEDIDAS_LARGURA_CONTROLES_UI
        campos.separator(factor=0.15 if estreito else separador)
        return campos, corpo, estreito

    def _grade_medidas(self, layout, estreito, coluna_unica, desenhadores):
        """Quebra a grade em duas colunas ou uma coluna no limite estreito."""
        if not estreito:
            for desenhar in desenhadores:
                desenhar(layout)
            return

        def desenhar_no_centro(desenhar, ocupacao=0.5):
            """Cria uma faixa central com margens laterais simetricas."""
            margem = (1.0 - ocupacao) * 0.5
            externo = layout.split(factor=margem)
            externo.column()
            restante = externo.column()
            proporcao_no_restante = ocupacao / (1.0 - margem)
            centro_direita = restante.split(factor=proporcao_no_restante)
            celula = centro_direita.column(align=True)
            celula.alignment = 'CENTER'
            desenhar(celula)
            centro_direita.column()

        if coluna_unica:
            for desenhar in desenhadores:
                desenhar_no_centro(
                    desenhar, MEDIDAS_OCUPACAO_COLUNA_UNICA)
            return

        for inicio in range(0, len(desenhadores), 2):
            par = desenhadores[inicio:inicio + 2]
            if len(par) == 2:
                # Sem largura fixa: as duas celulas dividem o espaco por
                # igual e o centro nao deriva para a esquerda ao comprimir.
                # `split` garante duas metades reais do espaco disponivel.
                # Duas `column` dentro de uma `row` podem ser compactadas pelo
                # Blender conforme a largura natural dos campos.
                linha = layout.split(factor=0.5, align=False)
                for desenhar in par:
                    celula = linha.column(align=True)
                    celula.alignment = 'CENTER'
                    desenhar(celula)
            else:
                desenhar_no_centro(par[0])

    def _visual_wireframe(self, layout, context, modo, medidas):
        """Desenha o preview responsivo entre os limites visualmente uteis."""
        coluna = layout.column(align=False)
        coluna.alignment = 'CENTER'
        icone = _icone_wireframe(context, modo, *medidas)
        if icone:
            linha = coluna.row(align=True)
            linha.alignment = 'CENTER'
            linha.template_icon(
                icon_value=icone, scale=self._escala_wireframe(context))
        else:
            coluna.label(text="", icon='MESH_CUBE')

    def _campo_medida(self, layout, dados, propriedade, texto):
        """Rotulo completo acima e campo compacto logo abaixo."""
        alinhamento = ('CENTER' if layout.alignment == 'CENTER' else 'LEFT')
        bloco = layout.column(align=True)
        bloco.alignment = alinhamento
        rotulo = bloco.row(align=True)
        rotulo.alignment = alinhamento
        rotulo.label(text=texto)
        valor = bloco.row(align=True)
        valor.alignment = alinhamento
        valor.prop(dados, propriedade, text="")

    def _rotulo_medida(self, layout, texto, valor_mm):
        """Versao so'-leitura do campo: selecao livre nao tem prop."""
        alinhamento = ('CENTER' if layout.alignment == 'CENTER' else 'LEFT')
        bloco = layout.column(align=True)
        bloco.alignment = alinhamento
        r = bloco.row(align=True)
        r.alignment = alinhamento
        r.label(text=texto)
        v = bloco.row(align=True)
        v.alignment = alinhamento
        v.label(text="%.1f mm" % valor_mm)

    def _campo_dimensao_objeto(self, layout, obj, indice, texto):
        """Dimensao nativa editavel; aceita mm, cm e m como o Blender."""
        alinhamento = ('CENTER' if layout.alignment == 'CENTER' else 'LEFT')
        bloco = layout.column(align=True)
        bloco.alignment = alinhamento
        rotulo = bloco.row(align=True)
        rotulo.alignment = alinhamento
        rotulo.label(text=texto)
        valor = bloco.row(align=True)
        valor.alignment = alinhamento
        valor.prop(obj, "dimensions", index=indice, text="")

    def _medidas_da_selecao(self, context, layout):
        """Caixa de QUALQUER selecao -- cubo, carro, curvas, o que for."""
        m = medir_selecao(context)
        if m is None:
            layout.label(text="Selecione uma chapa, um modulo ou "
                              "qualquer objeto", icon='INFO')
            return
        largura, altura, profundidade, quantos = m
        b = layout.box()
        b.label(text="Selecao (%d objeto%s)"
                     % (quantos, "" if quantos == 1 else "s"),
                icon='SHADING_BBOX')
        # Tres medidas ocupam menos altura que o preview maximo; a margem
        # superior maior centraliza o bloco e o afasta da quina do box.
        campos, visual, estreito = self._corpo_medidas(
            b, context, separador=1.2)
        volumes = [o for o in context.selected_objects
                   if o.type in TIPOS_COM_VOLUME]
        if quantos == 1 and len(volumes) == 1:
            obj = volumes[0]
            # Convencao do add-on: largura=X, altura=Z, profundidade=Y.
            self._grade_medidas(
                campos, estreito, self._painel_muito_estreito(context), [
                lambda lay: self._campo_dimensao_objeto(
                    lay, obj, 0, "Largura"),
                lambda lay: self._campo_dimensao_objeto(
                    lay, obj, 2, "Altura"),
                lambda lay: self._campo_dimensao_objeto(
                    lay, obj, 1, "Profundidade"),
            ])
            largura = obj.dimensions.x * 1000.0
            altura = obj.dimensions.z * 1000.0
            profundidade = obj.dimensions.y * 1000.0
        else:
            # A caixa conjunta de varios objetos nao tem uma unica escala
            # segura para editar; nesse caso as medidas continuam informativas.
            self._grade_medidas(
                campos, estreito, self._painel_muito_estreito(context), [
                lambda lay: self._rotulo_medida(lay, "Largura", largura),
                lambda lay: self._rotulo_medida(lay, "Altura", altura),
                lambda lay: self._rotulo_medida(
                    lay, "Profundidade", profundidade),
            ])
        self._visual_wireframe(visual, context, 'LIVRE',
                               (largura, altura, profundidade))

        # Este bloco so' aparece quando o objeto NAO tem a assinatura do
        # add-on -- e' por isso que ele mostra Altura no lugar de
        # Espessura. Em vez de deixar o usuario adivinhando, diz o
        # motivo e oferece a conversao.
        if (quantos == 1 and len(volumes) == 1
                and volumes[0].type == 'MESH'
                and MARCA_CHAPA not in volumes[0]):
            aviso = b.column(align=True)
            aviso.label(text="Objeto sem assinatura de chapa",
                        icon='INFO')
            aviso.operator("object.cabinet_marcar", icon='MOD_SOLIDIFY')

    def _lista_espessuras(self, layout, centralizar=False):
        linha = layout.row(align=True)
        linha.alignment = 'CENTER' if centralizar else 'LEFT'
        linha.label(text="15/18/20/30")

    def desenhar_medidas(self, context, layout):
        obj = context.object

        portas = _grupo_portas(obj)
        if portas is not None:
            caixa = layout.box()
            caixa.label(text="Vao: %.1f x %.1f mm" %
                        (portas['porta_vao_largura_mm'], portas['porta_vao_altura_mm']))
            caixa.label(text="%d folha(s)" % len(_folhas_portas(portas)))
            caixa.label(text="Use o botao Portas no topo do painel")
            return

        if obj is not None and MARCA_CONJUNTO in obj:
            self._abas_modo(layout, 'GRUPO')
            b = layout.box()
            b.label(text="Modulo (%d pecas)" % len(_chapas_do_conjunto(obj)), icon='MOD_BUILD')
            campos, visual, estreito = self._corpo_medidas(b, context)
            self._grade_medidas(
                campos, estreito, self._painel_muito_estreito(context), [
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_largura", "Largura"),
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_altura", "Altura"),
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_profundidade", "Profundidade"),
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_espessura", "Espessura"),
            ])
            self._lista_espessuras(campos, centralizar=estreito)
            self._visual_wireframe(
                visual, context, 'GRUPO',
                (obj.conj_largura_mm, obj.conj_altura_mm,
                 obj.conj_profundidade_mm))
            b.operator("object.cabinet_sincronizar", icon='FILE_REFRESH')
        elif obj is None or MARCA_CHAPA not in obj:
            self._medidas_da_selecao(context, layout)
        else:
            self._abas_modo(layout, _modo_chapa(context, obj))
            b = layout.box()
            if _modo_chapa(context, obj) == 'INDIVIDUAL':
                campos, visual, estreito = self._corpo_medidas(
                    b, context, separador=1.0)
                self._grade_medidas(
                    campos, estreito, self._painel_muito_estreito(context), [
                    lambda lay: self._campo_medida(
                        lay, obj, "ui_chapa_largura", "Largura"),
                    lambda lay: self._campo_medida(
                        lay, obj, "ui_chapa_comprimento", "Comprimento"),
                    lambda lay: self._campo_medida(
                        lay, obj, "ui_chapa_espessura", "Espessura"),
                ])
                self._lista_espessuras(campos, centralizar=estreito)
                self._visual_wireframe(
                    visual, context, 'INDIVIDUAL',
                    (obj.chapa_largura_mm, obj.chapa_espessura_mm,
                     obj.chapa_comprimento_mm))
            else:
                b.label(text="Grupo: %d peca(s)" % len(grupo_de(obj)), icon='MOD_BUILD')
                sc = context.scene
                campos, visual, estreito = self._corpo_medidas(b, context)
                self._grade_medidas(
                    campos, estreito, self._painel_muito_estreito(context), [
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_largura", "Largura"),
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_altura", "Altura"),
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_profundidade", "Profundidade"),
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_espessura", "Espessura"),
                ])
                self._lista_espessuras(campos, centralizar=estreito)
                self._visual_wireframe(
                    visual, context, 'GRUPO',
                    (sc.grupo_largura_mm, sc.grupo_altura_mm,
                     sc.grupo_profundidade_mm))
                b.operator("object.cabinet_sincronizar_grupo", icon='FILE_REFRESH')

        layout.separator()
        c = layout.column(align=True)
        c.label(text="Montagem:")
        # (idname, rotulo inteiro, rotulo curto, icone). O curto e' um
        # nome ESCOLHIDO, nao o inteiro truncado -- cortar seria o mesmo
        # defeito que a cascata acima evita.
        botoes = (
            ("object.cabinet_agrupar", "Agrupar Conjunto", "Agrupar",
             'OUTLINER_OB_EMPTY'),
            ("object.cabinet_detectar_adjacencia", "Detectar Adjacencia",
             "Adjacencia", 'SNAP_ON'),
            ("object.cabinet_normalizar", "Recalcular Chapas", "Recalcular",
             'FILE_REFRESH'),
        )
        largura = _largura_painel(context)
        if sum(_px_botao(b[2]) for b in botoes) <= largura:
            alvo, i_rotulo = c.row(align=True), 2      # lado a lado
        else:
            alvo, i_rotulo = c.column(align=True), 1   # empilhado
        for botao in botoes:
            alvo.operator(botao[0], text=botao[i_rotulo], icon=botao[3])

    # ---------------------------------------------------- BIBLIOTECA
    # Cascata HORIZONTAL: cada nivel e' uma linha de botoes. O nivel
    # selecionado fica azul (depress=True, o destaque nativo do Blender).
    def _linha_niveis(self, context, layout, nivel, valores, itens, sel,
                      pai=None):
        if not valores:
            return
        if nivel > 1:
            layout.separator(type='LINE')
        # O bpy corta o rotulo pela DIREITA, comendo justamente o "(N)".
        # Por isso a conta e' preservada e o NOME e' encurtado aqui.
        #
        # Antes de encurtar, porem, vale QUEBRAR A LINHA: espremer cinco
        # botoes numa sidebar estreita sobrava uma letra para cada um
        # ("P (0)" para Portas e Puxadores). A grade da mais largura a
        # cada botao e so' entao o nome e' resumido.
        disponivel = _largura_painel(context) - 16.0
        # O numero de colunas so' cresce enquanto o nome INTEIRO ainda
        # couber. Repartir por quantos cabem deixava o texto encolher ao
        # alargar a sidebar (mais colunas, cada uma mais estreita).
        maior = max(len(v) for v in valores) + 5      # folga do " (NN)"
        ideal = max(PX_MIN_NIVEL, maior * PX_CARACTERE + PX_FOLGA_BOTAO)
        colunas = max(1, min(len(valores), int(disponivel // ideal)))
        cabe = int((disponivel / colunas - PX_FOLGA_BOTAO) / PX_CARACTERE)
        linha = layout.grid_flow(row_major=True, columns=colunas,
                                 even_columns=True, align=True)
        for v in sorted(valores, key=str.casefold):
            if nivel == 1:
                n = _conta(itens, v)
            elif nivel == 2:
                n = _conta(itens, pai, v)
            else:
                n = _conta(itens, pai[0], pai[1], v)
            sufixo = " (%d)" % n
            nome = _abreviar(v, cabe - len(sufixo))
            op = linha.operator("object.cabinet_navegar",
                                text=nome + sufixo,
                                depress=(sel == v))
            op.nivel = nivel
            op.valor = v

    def desenhar_biblioteca(self, context, layout):
        s = context.scene
        itens = indice_completo()

        cab = layout.row(align=True)
        cab.prop(s, "chapa_bib_aberta",
                 icon='TRIA_DOWN' if s.chapa_bib_aberta else 'TRIA_RIGHT',
                 text="Biblioteca (%d)" % len(itens), toggle=True)
        cab.operator("object.cabinet_abrir_biblioteca", text="",
                     icon='FILE_FOLDER')
        # a prateleira nativa: unico lugar onde o arraste real existe
        cab.operator("object.cabinet_prateleira", text="", icon='ASSET_MANAGER')
        # o "+" adiciona a selecao atual a biblioteca
        cab.operator("object.cabinet_salvar_biblioteca", text="", icon='ADD')
        if not s.chapa_bib_aberta:
            return

        menu = layout.box()
        self._linha_niveis(context, menu, 1, list(ARVORE.keys()), itens,
                           s.chapa_n1)
        if s.chapa_n1:
            self._linha_niveis(context, menu, 2, _filhos_n2(s.chapa_n1),
                               itens, s.chapa_n2, pai=s.chapa_n1)
        if s.chapa_n1 and s.chapa_n2:
            self._linha_niveis(context, menu, 3,
                               _filhos_n3(s.chapa_n1, s.chapa_n2), itens,
                               s.chapa_n3, pai=(s.chapa_n1, s.chapa_n2))

        if not s.chapa_n1 or not s.chapa_n2:
            return
        filhos3 = _filhos_n3(s.chapa_n1, s.chapa_n2)
        if filhos3 and not s.chapa_n3:
            return

        daqui = []
        for it in itens:
            a, b, c = _niveis_de(it)
            if a == s.chapa_n1 and b == s.chapa_n2 and (not filhos3 or c == s.chapa_n3):
                daqui.append(it)
        daqui.sort(key=lambda i: (
            str(i.get("nome", "")).casefold(),
            str(i.get("arquivo", "")).casefold()))

        lista = layout.box()
        trilha = " > ".join(x for x in (s.chapa_n1, s.chapa_n2, s.chapa_n3) if x)
        # a trilha ("Armarios > Sala > Inferiores") saiu: os proprios
        # botoes da cascata, em azul, ja' dizem onde se esta'
        self._barra_tamanho(context, lista, s)
        if not daqui:
            lista.label(text="nenhum modelo aqui", icon='INFO')
            return

        # columns=0 faz o grid_flow calcular sozinho quantas colunas cabem
        # na largura atual do painel -- e' o mecanismo responsivo nativo.
        # As colunas so' precisam ser fixas no modo mosaico, onde a
        # largura do bloco define o tamanho da celula. Na foto normal
        # `columns=0` deixa o bpy distribuir, que e' o comportamento
        # responsivo nativo.
        if _foto_clicavel_ligada():
            colunas, _larg = _metrica_blocos(context, s.chapa_tam_bloco)
        else:
            colunas = 0
        grade = lista.grid_flow(row_major=True, columns=colunas,
                                even_columns=True, even_rows=True,
                                align=False)

        for it in daqui:
            icone = icone_do_item(it)
            travado = item_bloqueado(it)
            bloco = grade.column(align=True)

            # A foto e' um MOSAICO de botoes (ver FOTO CLICAVEL): assim
            # ela cresce com o tamanho escolhido E aciona o posicionador
            # em qualquer ponto, nao so' pelo nome.
            if icone and _foto_clicavel_ligada():
                self._foto_clicavel(context, bloco, it, icone)
            elif icone:
                bloco.template_icon(icon_value=icone,
                                    scale=float(s.chapa_tam_bloco))
            else:
                vazio = bloco.box()
                vazio.scale_y = float(s.chapa_tam_bloco) * 0.5
                vazio.label(text="", icon='IMAGE_DATA')

            # Duas linhas em vez de uma: no bloco estreito tudo junto
            # cortava o cadeado, e sem ele um preset travado nao teria
            # como ser destravado.
            acoes = bloco.column(align=True)

            # O nome chama o POSICIONADOR, igual a foto: o preset gruda
            # no cursor e o proximo clique na viewport confirma.
            op = acoes.operator("object.cabinet_arrastar_preset",
                                text=it["nome"])
            op.pasta = it["pasta"]
            op.arquivo = it["arquivo"]
            op.tipo = it.get("tipo", "modulo")

            botoes = acoes.row(align=True)
            # a seta insere direto no cursor 3D, sem posicionar
            oi = botoes.operator("object.cabinet_inserir_preset",
                                 text="", icon='IMPORT')
            oi.pasta = it["pasta"]
            oi.arquivo = it["arquivo"]
            oi.tipo = it.get("tipo", "modulo")

            # o lapis some com o cadeado fechado, o cadeado NUNCA some
            editar = botoes.row(align=True)
            editar.enabled = not travado
            oe = editar.operator(
                "object.cabinet_editar_modelo", text="", icon='GREASEPENCIL')
            oe.pasta = it["pasta"]
            oe.arquivo = it["arquivo"]
            self._cadeado(botoes, it, travado)

    def _foto_clicavel(self, context, layout, it, icone):
        """Mosaico de botoes com a foto: clicar em qualquer ponto
        aciona o posicionador, igual ao nome."""
        s = context.scene
        png = os.path.splitext(it["arquivo"])[0] + ".png"
        # o ladrilho tem tamanho FIXO: quem varia e' a quantidade deles
        _col, largura_bloco = _metrica_blocos(context, s.chapa_tam_bloco)
        lado = max(2, int(round(
            (largura_bloco - PADDING_BLOCO) / PX_ALVO_CELULA)))
        tiles = _tiles_foto(it["pasta"], png, lado)
        if not tiles:
            # sem os ladrilhos a foto ainda aparece, so' que nao clicavel
            layout.template_icon(icon_value=icone,
                                 scale=float(s.chapa_tam_bloco))
            return

        # Celula maior que o icone deixa fresta e o mosaico vira
        # xadrez. `ui_units_x` fixa a largura da linha em unidades de
        # UI (20 px cada), entao cada ladrilho recebe exatamente o
        # tamanho do icone -- sem precisar saber quantas colunas a
        # grade de blocos resolveu usar. scale_y fecha a fresta de cima.
        # A celula vale largura_do_bloco/lado. Se ela sobrar sobre o
        # icone de 16 px, fica uma fresta por coluna e a foto ganha
        # listras. scale_x encolhe a celula ate' o icone -- e quando a
        # celula fica MENOR que ele, o icone acompanha, sem fresta.
        grade = layout.column(align=True)
        grade.scale_y = PX_TILE_FOTO / 20.0
        for linha_tiles in tiles:
            linha = grade.row(align=True)
            for icon_id in linha_tiles:
                op = linha.operator("object.cabinet_arrastar_preset",
                                    text="", emboss=False,
                                    icon_value=icon_id)
                op.pasta = it["pasta"]
                op.arquivo = it["arquivo"]
                op.tipo = it.get("tipo", "modulo")

    def _barra_tamanho(self, context, layout, s):
        """Barra compacta de fatias clicaveis (ver BARRA DE TAMANHO).

        A largura e' RESERVADA por um split em vez de deixada ao
        alinhamento: com `alignment='RIGHT'` o botao assume uma largura
        natural bem maior que o icone e o trilho sai tracejado, e
        comprimir o bastante para fechar os vaos borrava o desenho.
        """
        prop = bpy.types.Scene.bl_rna.properties["chapa_tam_bloco"]
        menor, maior = prop.hard_min, prop.hard_max
        ultimo = maior - menor
        ativo = max(0, min(ultimo, int(s.chapa_tam_bloco) - menor))

        fatias, _celula, _c = _metrica_barra(context)
        util = PX_FATIA_BARRA * fatias
        largura = max(1.0, _largura_painel(context))
        # o que sobra a esquerda e' so' vao: joga a barra no canto
        fracao = max(0.02, min(0.92, 1.0 - (util + PX_BOTAO_BIBLIOTECA)
                               / largura))
        div = layout.split(factor=fracao)
        div.label(text="")
        direita = div.row(align=True)

        linha = direita.row(align=True)
        linha.scale_x = _metrica_barra(context, util)[2]
        for i in range(fatias):
            op = linha.operator(
                "object.cabinet_tamanho", text="", emboss=False,
                icon_value=_icone_fatia_barra(i, ativo, ultimo))
            op.valor = menor + i
        direita.operator("object.cabinet_asset_browser", text="",
                         icon='ASSET_MANAGER')

    def _cadeado(self, linha, it, travado):
        """Cadeado clicavel, alternando entre os dois sprites."""
        oc = linha.operator("object.cabinet_bloqueio", text="",
                            icon='LOCKED' if travado else 'UNLOCKED',
                            depress=travado)
        oc.pasta = it["pasta"]
        oc.arquivo = it["arquivo"]


CLASSES = (
    CabinetCreatorPreferences,
    OBJECT_OT_sincronizar_grupo,
    OBJECT_OT_sincronizar_conjunto,
    OBJECT_OT_registrar_bibliotecas,
    OBJECT_OT_refiliar_catalogos,
    OBJECT_OT_regerar_previews,
    OBJECT_OT_modo_medidas,
    OBJECT_OT_criar_chapa,
    OBJECT_OT_salvar_biblioteca,
    OBJECT_OT_abrir_pasta_biblioteca,
    OBJECT_OT_abrir_asset_browser,
    OBJECT_OT_definir_tamanho,
    OBJECT_OT_inserir_preset,
    OBJECT_OT_arrastar_preset,
    OBJECT_OT_prateleira,
    OBJECT_OT_selecionar,
    OBJECT_OT_navegar,
    OBJECT_OT_editar_modelo,
    OBJECT_OT_alternar_bloqueio,
    OBJECT_OT_agrupar_conjunto,
    OBJECT_OT_detectar_adjacencia,
    OBJECT_OT_criar_nicho,
    OBJECT_OT_exportar_orcamento,
    OBJECT_OT_definir_comodo,
    OBJECT_OT_apanhar_vao_portas,
    OBJECT_OT_portas_parametricas,
    OBJECT_OT_converter_modulo,
    OBJECT_OT_converter_puxador,
    OBJECT_OT_vincular_puxador,
    OBJECT_OT_folha_de_objetos,
    OBJECT_OT_porta_dupla,
    OBJECT_OT_vincular_porta,
    OBJECT_OT_corrente_porta,
    OBJECT_OT_definir_frente,
    OBJECT_OT_posicionar_puxador,
    OBJECT_OT_opcoes_gaveta,
    OBJECT_OT_editar_medida_gaveta,
    OBJECT_OT_arrastar_hud,
    OBJECT_OT_interagir_gaveta,
    OBJECT_OT_alternar_gaveta,
    OBJECT_OT_marcar_como_chapa,
    OBJECT_OT_normalizar,
    VIEW3D_GT_alca_gaveta,
    VIEW3D_GT_campo_gaveta,
    # o slider antes da HUD: a bolinha ganha o clique (gizmo e' avaliado
    # na ordem do registro)
    VIEW3D_GT_slider_porta,
    VIEW3D_GGT_slider_porta,
    VIEW3D_GT_hud_cabinet,
    VIEW3D_GGT_hud_cabinet,
    VIEW3D_GGT_correntes_cabinet,
    OBJECT_OT_desassociar,
    OBJECT_OT_tecla_corrente,
    OBJECT_OT_clique_corrente,
    OBJECT_OT_corrente_objeto,
    OBJECT_OT_desagregar_selecao,
    OBJECT_OT_responder_pergunta,
    OBJECT_OT_conectar_distancia,
    OBJECT_OT_conectar_vertices,
    OBJECT_OT_confirmar_conexao,
    OBJECT_OT_resetar_distancia,
    OBJECT_OT_arrastar_ancora,
    OBJECT_OT_arrastar_canto_porta,
    OBJECT_OT_arrastar_ferragem,
    OBJECT_OT_cantos_porta,
    OBJECT_OT_abrir_porta,
    OBJECT_OT_nomear_grupo,
    OBJECT_OT_digitar_nome_grupo,
    OBJECT_OT_juntar_modulo,
    VIEW3D_GGT_cabinet_gaveta,
    VIEW3D_AST_cabinet_creator,
)


# ------------------------------------------ operador terminado larga a cena
# Crash do usuario (repetivel): Ctrl+Z ENQUANTO a porta nascia. O Blender
# guarda o operador (REGISTER) depois que ele termina, e o wizard levava
# em `self` a lista de todos os objetos do ima: no undo seguinte esses
# objetos eram liberados/trocados com o Python ainda segurando-os, e a
# memoria do Python corrompia (crash depois, em lugar aleatorio). Todo
# operador MODAL, ao terminar ou cancelar, solta o que for dado da cena.
def _segura_dado(valor, fundo=0):
    if isinstance(valor, bpy.types.ID):
        return True
    if fundo >= 4:
        return False
    if isinstance(valor, (list, tuple, set, frozenset)):
        return any(_segura_dado(v, fundo + 1) for v in valor)
    if isinstance(valor, dict):
        # objeto como CHAVE tambem segura (ex.: {objeto: posicao})
        return any(_segura_dado(v, fundo + 1)
                   for par in valor.items() for v in par)
    return False


def _soltar_dados_blender(op):
    for nome, valor in list(getattr(op, '__dict__', {}).items()):
        if _segura_dado(valor):
            setattr(op, nome, None)


def _terminou(op, resultado):
    if isinstance(resultado, set) and resultado & {'FINISHED', 'CANCELLED'}:
        _soltar_dados_blender(op)
    return resultado


# Assinaturas EXPLICITAS: o Blender confere o numero de argumentos dos
# metodos do operador ao registrar (*args seria recusado).
def _envolver_evento(metodo):
    def envolvido(self, context, event):
        return _terminou(self, metodo(self, context, event))
    envolvido.larga_dados = True
    return envolvido


def _envolver_cancel(metodo):
    def envolvido(self, context):
        resultado = metodo(self, context)
        _soltar_dados_blender(self)
        return resultado
    envolvido.larga_dados = True
    return envolvido


def _larga_dados_ao_terminar(classe):
    for nome, envolver in (('invoke', _envolver_evento),
                           ('modal', _envolver_evento),
                           ('cancel', _envolver_cancel)):
        metodo = classe.__dict__.get(nome)
        if metodo is not None and not getattr(metodo, 'larga_dados', False):
            setattr(classe, nome, envolver(metodo))
    return classe


for _classe in CLASSES:
    if (isinstance(_classe, type) and issubclass(_classe, Operator)
            and 'modal' in _classe.__dict__):
        _larga_dados_ao_terminar(_classe)
del _classe


_PROPS_MEDIDA_UI_OBJETO = (
    "ui_chapa_largura", "ui_chapa_comprimento", "ui_chapa_espessura",
    "ui_conj_largura", "ui_conj_altura", "ui_conj_profundidade",
    "ui_conj_espessura",
)
_PROPS_MEDIDA_UI_CENA = (
    "ui_grupo_largura", "ui_grupo_altura", "ui_grupo_profundidade",
    "ui_grupo_espessura",
) + tuple(m[0] for m in MEDIDAS_PORTAS)
_PROPS_PORTAS_CENA = (
    "porta_abertura", "porta_dobradica", "porta_folhas", "porta_associar",
) + tuple(m[1] for m in MEDIDAS_PORTAS)


def _registrar_medida_ui(dono, nome_ui, nome_mm, nome, minimo_mm):
    """Expoe em metros para o parser nativo, mantendo o dado real em mm."""
    def obter(self):
        return float(getattr(self, nome_mm)) / 1000.0

    def definir(self, valor):
        setattr(self, nome_mm, float(valor) * 1000.0)

    setattr(dono, nome_ui, FloatProperty(
        name=nome,
        description="Sem sufixo usa a unidade da cena; aceita mm, cm e m",
        subtype='DISTANCE',
        unit='LENGTH',
        min=minimo_mm / 1000.0,
        precision=3,
        step=10,
        get=obter,
        set=definir))


def _garantir_unidade_padrao_mm():
    """Campos do addon usam milimetros como unidade implicita da cena."""
    # Durante addon_enable o Blender protege bpy.data com _RestrictData.
    # Adiar evita falha de ativacao e mantem esta configuracao fora do register.
    if not hasattr(bpy.data, "scenes"):
        if not bpy.app.timers.is_registered(_garantir_unidade_padrao_mm):
            bpy.app.timers.register(
                _garantir_unidade_padrao_mm, first_interval=0.0)
        return None
    for cena in bpy.data.scenes:
        unidades = cena.unit_settings
        unidades.system = 'METRIC'
        unidades.scale_length = 1.0
        unidades.length_unit = 'MILLIMETERS'


def register():
    if not bpy.app.timers.is_registered(_limitar_largura_gaveta):
        bpy.app.timers.register(_limitar_largura_gaveta,
                               first_interval=0.3, persistent=True)
    for c in CLASSES:
        bpy.utils.register_class(c)
    _handler_gaveta[0] = bpy.types.SpaceView3D.draw_handler_add(
        _desenhar_gaveta, (), 'WINDOW', 'POST_PIXEL')
    # POST_VIEW: a caixa vive em coordenada de MUNDO, junto da cena
    _handler_grid[0] = bpy.types.SpaceView3D.draw_handler_add(
        _desenhar_grid_medidas, (), 'WINDOW', 'POST_VIEW')
    _handler_hud_texto[0] = bpy.types.SpaceView3D.draw_handler_add(
        _desenhar_hud_texto, (), 'WINDOW', 'POST_PIXEL')
    bpy.app.timers.register(_reconectar_gavetas, first_interval=0.1)
    registrar_keymaps()
    # DIAGNOSTICO TEMPORARIO: o keymap mesclado so' existe depois do registro
    bpy.app.timers.register(_log_keymaps, first_interval=1.0)
    S = bpy.types.Scene
    # Os parametros das portas moram na Scene para a gaveta edita-los
    # sem popup (ver ESCOLHAS_PORTAS). Frente e espessuras nao estao
    # aqui de proposito: saem da diagonal e do modulo.
    # A corrente Modulos|Portas sem porta ativa: como nasce a proxima
    S.porta_associar = BoolProperty(
        name="Porta presa ao modulo", default=True,
        description="Ligada: a porta nova segue o modulo e usa os eixos "
                    "dele. Partida: porta solta, nos eixos do mundo")
    S.porta_abertura = EnumProperty(name="Abertura", items=ITENS_ABERTURA,
                                    default='GIRO',
                                    update=_limitar_folhas_cena)
    # Reta e' o padrao: nenhuma fila de segmentos pode ficar sem
    # nenhuma opcao acesa, e obrigar a escolha so' fazia o botao de
    # criar nascer bloqueado.
    S.porta_dobradica = EnumProperty(name="Dobradica",
                                     items=ITENS_DOBRADICA,
                                     default='RETA')
    # Dupla e' o padrao de armario; uma folha so' e' a excecao.
    S.porta_folhas = IntProperty(name="Folhas", default=2, min=1, max=4)
    for prop_ui, prop_mm, rotulo, minimo in MEDIDAS_PORTAS:
        padrao = {'porta_entre_folhas_mm': 2.0, 'porta_recuo_correr_mm': 30.0,
                  'porta_sobreposicao_mm': 20.0,
                  'porta_entre_planos_mm': 2.0}.get(prop_mm, 0.0)
        setattr(S, prop_mm, FloatProperty(name=rotulo, default=padrao,
                                          min=minimo))
        _registrar_medida_ui(S, prop_ui, prop_mm, rotulo, minimo)
    O = bpy.types.Object
    O.chapa_largura_mm = FloatProperty(
        name="Largura (mm)", default=600.0, min=1.0, update=_upd_chapa)
    O.chapa_comprimento_mm = FloatProperty(
        name="Comprimento (mm)", default=400.0, min=1.0, update=_upd_chapa)
    O.chapa_espessura_mm = FloatProperty(
        name="Espessura (mm)", default=18.0, min=1.0,
        description="Qualquer espessura; acima de 60 mm o campo fica vermelho",
        update=_upd_espessura)
    O.chapa_auto = BoolProperty(
        name="Auto-regenerar", default=True,
        description="Obsoleto: a chapa sempre preserva a malha modelada")
    O.conj_largura_mm = FloatProperty(
        name="Largura (mm)", default=600.0, min=20.0, update=_upd_conj_dim)
    O.conj_altura_mm = FloatProperty(
        name="Altura (mm)", default=400.0, min=20.0, update=_upd_conj_dim)
    O.conj_profundidade_mm = FloatProperty(
        name="Profundidade (mm)", default=300.0, min=20.0, update=_upd_conj_dim)
    O.conj_espessura_mm = FloatProperty(
        name="Espessura (mm)", default=18.0, min=1.0,
        description="Espessura de todas as chapas do modulo",
        update=_upd_conj_espessura)
    O.chapa_modo = EnumProperty(
        name="Modo", default='INDIVIDUAL',
        items=[('INDIVIDUAL', "Individual", "Medidas desta chapa"),
               ('GRUPO', "Grupo", "Medidas do modulo inteiro")])
    _registrar_medida_ui(
        O, "ui_chapa_largura", "chapa_largura_mm", "Largura", 1.0)
    _registrar_medida_ui(
        O, "ui_chapa_comprimento", "chapa_comprimento_mm", "Comprimento", 1.0)
    _registrar_medida_ui(
        O, "ui_chapa_espessura", "chapa_espessura_mm", "Espessura", 1.0)
    _registrar_medida_ui(
        O, "ui_conj_largura", "conj_largura_mm", "Largura", 20.0)
    _registrar_medida_ui(
        O, "ui_conj_altura", "conj_altura_mm", "Altura", 20.0)
    _registrar_medida_ui(
        O, "ui_conj_profundidade", "conj_profundidade_mm", "Profundidade", 20.0)
    _registrar_medida_ui(
        O, "ui_conj_espessura", "conj_espessura_mm", "Espessura", 1.0)

    S = bpy.types.Scene
    S.cabinet_aba = EnumProperty(
        name="Aba", default='MODULOS',
        items=[('MODULOS', "Modulos", "Medidas, montagem e biblioteca"),
               ('PORTAS', "Portas", "Criacao e configuracao de portas"),
               ('PUXADORES', "Puxadores", "Puxadores ligados as portas")])
    # modelo que a ferramenta de posicionar vai criar
    S.cabinet_puxador_modelo = EnumProperty(
        name="Modelo", default='ALCA',
        items=[(k, v[0], "") for k, v in MODELOS_PUXADOR.items()])
    S.chapa_bib_aberta = BoolProperty(name="Biblioteca", default=False)
    S.chapa_n1 = StringProperty(default="")
    S.chapa_n2 = StringProperty(default="")
    S.chapa_n3 = StringProperty(default="")
    # barra continua (estilo volume) no lugar dos tres degraus P/M/G
    # 7 degraus: com 11 a barra ocupava 70% da sidebar e nao cabia no
    # canto. A miniatura maior continua grande o bastante.
    S.chapa_tam_bloco = IntProperty(
        name="Tamanho", default=5, min=2, max=8,
        description="Tamanho das miniaturas na grade")
    S.grupo_largura_mm = FloatProperty(name="Largura (mm)", default=600.0, min=20.0, update=_upd_grupo_dim)
    S.grupo_altura_mm = FloatProperty(name="Altura (mm)", default=400.0, min=20.0, update=_upd_grupo_dim)
    S.grupo_profundidade_mm = FloatProperty(name="Profundidade (mm)", default=300.0, min=20.0, update=_upd_grupo_dim)
    S.grupo_espessura_mm = FloatProperty(name="Espessura (mm)", default=18.0, min=1.0, update=_upd_grupo_espessura)
    _registrar_medida_ui(
        S, "ui_grupo_largura", "grupo_largura_mm", "Largura", 20.0)
    _registrar_medida_ui(
        S, "ui_grupo_altura", "grupo_altura_mm", "Altura", 20.0)
    _registrar_medida_ui(
        S, "ui_grupo_profundidade", "grupo_profundidade_mm", "Profundidade", 20.0)
    _registrar_medida_ui(
        S, "ui_grupo_espessura", "grupo_espessura_mm", "Espessura", 1.0)

    _garantir_unidade_padrao_mm()

    if ao_atualizar_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(ao_atualizar_depsgraph)
    for evento, funcao in HANDLERS_CONTORNO + HANDLERS_REFERENCIAS:
        lista = getattr(bpy.app.handlers, evento)
        if funcao not in lista:
            lista.append(funcao)
    if not bpy.app.timers.is_registered(verificar_periodicamente):
        bpy.app.timers.register(verificar_periodicamente, persistent=True)
    # bpy.ops nao pode rodar dentro de register(): adia por um tique
    bpy.app.timers.register(_registrar_bibliotecas_adiado, first_interval=0.5)


def _registrar_bibliotecas_adiado():
    # funcao com NOME (nao lambda): o unregister precisa poder remove-la
    registrar_bibliotecas()
    return None


def unregister():
    _tecla_corrente_segurada[0] = False
    _conexao_pendente[0] = None
    _conexao_manual[0] = None
    _desagregar_pendente[0] = None
    _pergunta_reset[0] = ''
    _pergunta_atual[0] = None
    _na_gaveta[0] = False
    _arraste_ancora[0] = None
    _arraste_canto_porta[0] = None
    _arraste_ferragem[0] = None
    _ferragens_selecionadas[0] = None
    _dobradica_reta[0] = None
    _arraste_slider_porta[0] = None
    _slider_hover[0] = None
    _nome_grupo_gaveta[0] = None
    _orcamento_copiado[0] = None
    _contagem_objetos[0] = -1
    _bolinha_hover[0] = None
    for timer in (_log_keymaps, _registrar_bibliotecas_adiado,
                  _animar_piscada, _conferir_ferragens,
                  _apagar_orcamento_copiado):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
    _edicao_hud[0] = None
    _hover_hud.clear()
    _clique_chapa_hud.clear()
    _clique_pendente.clear()
    _edicao_gaveta[0] = None
    if bpy.app.timers.is_registered(_animar_realces):
        bpy.app.timers.unregister(_animar_realces)
    _realces.clear()
    _deslizes.clear()
    if bpy.app.timers.is_registered(_limitar_largura_gaveta):
        bpy.app.timers.unregister(_limitar_largura_gaveta)
    remover_keymaps()
    _fechar_gavetas_registradas()
    if _handler_gaveta[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler_gaveta[0], 'WINDOW')
        _handler_gaveta[0] = None
    if _handler_grid[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler_grid[0], 'WINDOW')
        _handler_grid[0] = None
    if _handler_hud_texto[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler_hud_texto[0], 'WINDOW')
        _handler_hud_texto[0] = None
    _campos_gaveta.clear()
    _realce_medida[0] = None
    _fotos_gaveta.clear()
    for nome in _imagens_gaveta:
        imagem = bpy.data.images.get(nome)
        if imagem is not None:
            bpy.data.images.remove(imagem)
    _imagens_gaveta.clear()
    if bpy.app.timers.is_registered(_configurar_gavetas):
        bpy.app.timers.unregister(_configurar_gavetas)
    if bpy.app.timers.is_registered(_reconectar_gavetas):
        bpy.app.timers.unregister(_reconectar_gavetas)
    if hasattr(bpy.types.Scene, 'cabinet_aba'):
        del bpy.types.Scene.cabinet_aba
    if hasattr(bpy.types.Scene, 'cabinet_puxador_modelo'):
        del bpy.types.Scene.cabinet_puxador_modelo
    _posicionador_puxador[0] = None
    if _handler_posicionador[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler_posicionador[0], 'WINDOW')
        _handler_posicionador[0] = None
    if bpy.app.timers.is_registered(_garantir_unidade_padrao_mm):
        bpy.app.timers.unregister(_garantir_unidade_padrao_mm)
    if _previews[0] is not None:
        try:
            bpy.utils.previews.remove(_previews[0])
        except Exception:
            pass
        _previews[0] = None
    _wireframe_ordem.clear()
    if bpy.app.timers.is_registered(verificar_periodicamente):
        bpy.app.timers.unregister(verificar_periodicamente)
    if bpy.app.timers.is_registered(_fim_do_desfazer):
        bpy.app.timers.unregister(_fim_do_desfazer)
    _desfazendo[0] = False
    if ao_atualizar_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(ao_atualizar_depsgraph)
    for evento, funcao in HANDLERS_CONTORNO + HANDLERS_REFERENCIAS:
        lista = getattr(bpy.app.handlers, evento)
        if funcao in lista:
            lista.remove(funcao)
    # desligar o add-on no meio da edicao nao pode deixar a viewport sem
    # contorno para sempre
    sincronizar_contornos(devolver=True)
    _contornos_do_usuario.clear()
    for nome in _PROPS_MEDIDA_UI_OBJETO:
        if hasattr(bpy.types.Object, nome):
            delattr(bpy.types.Object, nome)
    for nome in _PROPS_MEDIDA_UI_CENA + _PROPS_PORTAS_CENA:
        if hasattr(bpy.types.Scene, nome):
            delattr(bpy.types.Scene, nome)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
