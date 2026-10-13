"""HUD parametrica na viewport: linhas, rotulos, setas, quinas e arraste,
os gizmos das correntes e o grid de medidas dos campos da gaveta."""

import bpy, math, gpu, blf, time
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from bpy_extras import view3d_utils
from bpy.types import Gizmo, GizmoGroup, Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = None
_modulos = None
_opcoes = None
_eventos = None
_selecao = None
_portas = None
_ferragens = None
_puxadores = None
_arame = None
_gaveta = None
_solda = None
_portas_viewport = None
_gaveta_desenho = None

# ============================================= GRID DE MEDIDAS NA CENA
# Passar o mouse num campo de medida (ou abri-lo para edicao) desenha a
# caixa envolvente do alvo na viewport e ACENDE as quatro arestas do
# eixo daquele campo. Assim da' para ver o que vai mudar antes de
# mudar, em vez de descobrir por tentativa e erro. Aqui so' as tabelas e
# o estado; as funcoes da secao sao `_caixa_da_medida`,
# `_definir_realce_medida` e `_desenhar_grid_medidas`.

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
    if _eventos._transformando():
        _hover_hud.clear()
        return False
    return (context.mode == 'OBJECT' and context.area is not None
            and context.area.type == 'VIEW_3D'
            and context.region is not None and context.region.type == 'WINDOW'
            and context.region_data is not None and not _gaveta._eh_area_gaveta(context))


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
    return obj if obj.get(_ferragens.CHAVE_FERRAGEM) in _ferragens.TIPOS_SELECAO_FERRAGEM else None


def _raio_hud(context, posicao):
    atingido = _raio_cru(context, posicao)
    if atingido is None:
        return None
    obj, ponto, normal, face, matriz = atingido
    if _ferragens.CHAVE_FERRAGEM in obj:
        # para quem pergunta "que porta e' esta": a ferragem vale pela
        # folha (o clique nela mesma e' de `_ferragem_sob_mouse`)
        dono = obj.parent
        if dono is not None and _chapas.MARCA_PORTAS in dono:
            dono = (_portas._folhas_portas(dono) or [None])[0]
        if dono is None or _chapas.MARCA_FOLHA not in dono:
            return None
        # a face e' da ferragem, nao da folha: sem face (-1)
        return dono, ponto, normal, -1, dono.matrix_world.copy()
    return obj, ponto, normal, face, matriz


def _familia_do_clique(obj):
    """O que um clique simples em `obj` seleciona: o modulo com tudo
    dentro, ou o grupo solto da chapa."""
    modulo = _portas._modulo_da_chapa(obj)
    if modulo is not None:
        # ferragem nao acende com o modulo (seleciona-se por si mesma)
        return [modulo, *(o for o in modulo.children_recursive
                          if _ferragens.CHAVE_FERRAGEM not in o)]
    return _selecao.familia_de(obj)


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
    _chapas._ocupado[0] = True
    try:
        obj.chapa_modo = 'INDIVIDUAL'
    finally:
        _chapas._ocupado[0] = False
    context.view_layer.objects.active = obj
    if context.area:
        context.area.tag_redraw()


def _selecionar_chapa_hud(context, obj, individual=False, somar=False):
    """A selecao e o modo de medidas mudam juntos, inclusive para portas.

    `somar` (Shift) junta o modulo a selecao em vez de troca-la: e' assim
    que se seleciona mais de um item para editar a medida de todos."""
    modulo = _portas._modulo_da_chapa(obj)
    familia = _familia_do_clique(obj)
    if not somar:
        for selecionado in context.selected_objects:
            selecionado.select_set(False)
    for alvo in ([obj] if individual else familia or [obj]):
        alvo.select_set(True)
    _chapas._ocupado[0] = True
    try:
        obj.chapa_modo = 'INDIVIDUAL' if individual else 'GRUPO'
    finally:
        _chapas._ocupado[0] = False
    context.view_layer.objects.active = obj if individual or modulo is None else modulo
    if not individual and modulo is None:
        _modulos.sincronizar_grupo(context)
    if context.area:
        context.area.tag_redraw()


def _nivel_da_selecao(context, obj):
    """Em que nivel a porta de `obj` esta' selecionada agora.

    'PORTA' = o grupo inteiro, 'FOLHA' = uma folha dele, 'MODULO' =
    qualquer outra coisa. Lido ANTES do clique que vai mudar a selecao.
    """
    grupo = _portas._grupo_portas(obj)
    ativo = context.object
    if grupo is None or ativo is None:
        return 'MODULO'
    if ativo == grupo:
        return 'PORTA'
    if _chapas.MARCA_FOLHA in ativo and _portas._grupo_portas(ativo) == grupo:
        return 'FOLHA'
    return 'MODULO'


def _selecionar_porta_hud(context, folha, nivel, somar=False):
    """Nivel PORTA: o grupo e todas as folhas. Nivel FOLHA: so' ela.
    `somar` (Shift) junta a selecao em vez de troca-la."""
    grupo = _portas._grupo_portas(folha)
    if grupo is None:
        return
    if not somar:
        for selecionado in context.selected_objects:
            selecionado.select_set(False)
    if nivel == 'PORTA':
        for alvo in [grupo, *_portas._folhas_portas(grupo)]:
            alvo.select_set(True)
        context.view_layer.objects.active = grupo
    else:
        folha.select_set(True)
        _chapas._ocupado[0] = True
        try:
            folha.chapa_modo = 'INDIVIDUAL'
        finally:
            _chapas._ocupado[0] = False
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
        if _chapas.MARCA_CHAPA in o:
            # medida NOMINAL: o perfil tira uma faixa da malha, nao da chapa
            pontos += [inversa @ p for p in _chapas._cantos(o)]
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
    if _chapas.MARCA_CHAPA not in obj and _chapas.MARCA_CONJUNTO not in obj:
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
            and (_chapas.MARCA_PORTAS in obj or _chapas.MARCA_FOLHA in obj)):
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
    folhas = _portas._folhas_portas(grupo)
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
    if _chapas.MARCA_CONJUNTO in obj:
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
        if any(m in o for m in (_chapas.MARCA_PORTAS, _chapas.MARCA_FOLHA, _chapas.MARCA_PUXADOR,
                                _chapas.MARCA_ACESSORIO)):
            continue
        if _chapas.MARCA_CONJUNTO in o:
            if ('M', o.name) not in chaves:
                somar(o, 'GRUPO', _modulos.pecas_do_envelope(o))
            continue
        if _chapas.MARCA_CHAPA not in o or o.type != 'MESH':
            continue
        modulo = _portas._modulo_da_chapa(o)
        if modulo is not None and modulo in marcados:
            if ('M', modulo.name) not in chaves:
                somar(modulo, 'GRUPO', _modulos.pecas_do_envelope(modulo))
            continue
        if modulo is None and len(marcados) > 1:
            grupo = _modulos.grupo_de(o) or [o]
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
    grupos = _gaveta._grupos_de_porta(obj) if modo == 'GRUPO' else []
    for grupo in grupos:
        if any(float(f.get(_ferragens.CHAVE_ABERTURA, 0.0)) > 0.0
               for f in _portas._folhas_portas(grupo)):
            # porta aberta (pedido do usuario): a caixa envolveria o giro
            # inteiro e a folga ate' o modulo nao existe -- nada da porta
            continue
        caixa = _caixa_hud_objetos(_portas._folhas_portas(grupo), grupo.matrix_world)
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
    if cantos and geometria['modo'] == 'GRUPO' and _chapas.MARCA_CONJUNTO in obj:
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
    if obj not in chapas or _chapas.MARCA_CHAPA not in obj:
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
    for corrente in _solda._correntes_hud(context):
        acesos.setdefault(_cor_realce_hud(), []).extend(corrente['pontos'])
    if not normais and not acesos and not principais:
        return
    cor = _cor_linhas_hud(context)
    espessura = float(_opcoes._opcao('hud_espessura_linha'))
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
    limite = FATOR_ROTULO_HUD * _opcoes._opcao('hud_tamanho_rotulo') * escala
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
    tamanho = _opcoes._opcao('hud_tamanho_rotulo') * escala
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
    _ferragens._desenhar_ferragens_selecionadas(context)
    _puxadores._desenhar_ancoras_puxador(context)
    _portas_viewport._desenhar_cantos_porta(context)
    _portas_viewport._desenhar_sliders_porta(context)
    desenhos = _desenhos_hud(context)
    if not desenhos:
        return
    cor = _cor_linhas_hud(context)
    realce = _cor_realce_hud()
    escala = context.preferences.system.ui_scale
    tamanho = _opcoes._opcao('hud_tamanho_rotulo') * escala
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
                    _caixa_texto_hud(x_texto, y, _gaveta_desenho._com_cursor(
                        edicao['texto'], edicao.get('cursor', len(edicao['texto']))),
                        tamanho, escala)
            if alvo and alvo.get('lado'):
                _desenhar_seta_hud(context, alvo, geometria)
        _solda._desenhar_bolinhas_correntes(context)
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
                if nesta and edicao.get('snap') is not None:
                    # grudou (Ctrl): bolinha cheia no centro da quina
                    _bolinha_2d(shader, ponto, raio * 0.45, realce)
    finally:
        gpu.state.line_width_set(1)
        gpu.state.point_size_set(1)
        gpu.state.blend_set('NONE')


def _cor_tema_linha():
    return tuple(bpy.context.preferences.themes[0]
                 .user_interface.wcol_regular.text)[:3]


def _cor_opcao(nome):
    """RGB que a opcao de cor esta' mostrando (o tema ja' resolvido)."""
    if nome == 'hud_rgb_linha' and _opcoes._opcao('hud_linha_tema'):
        return _cor_tema_linha()
    return tuple(_opcoes._opcao(nome))[:3]


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
    if _opcoes._opcao('hud_realce_gizmo'):
        eixo = EIXO_GIZMO_DA_LETRA.get(letra)
        return (*(_cor_eixo_gizmo(eixo) if eixo else _opcoes.COR_REALCE_PADRAO), 1.0)
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
        if _portas_viewport._slider_sob_mouse(context, location) is not None:
            return -1       # a bolinha do slider de abertura e' de outro gizmo
        # Sobre uma corrente o clique e' DELE (outro gizmo): a quina e as
        # linhas da HUD ficam embaixo e nao podem roubar o pick.
        alvo_corrente = _solda._alvo_da_corrente(context, location)
        corrente = alvo_corrente[1] if alvo_corrente else None
        bolinha = (_solda._chave_bolinha(corrente, alvo_corrente[2])
                   if alvo_corrente and alvo_corrente[0] == 'bolinha' else None)
        if bolinha != _solda._bolinha_hover[0]:
            _solda._bolinha_hover[0] = bolinha
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
                and not _portas._apanhando_vao[0])

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
        return (_contexto_hud(context) and not _gaveta._eh_area_gaveta(context)
                and _alvo_hud(context) is not None and not _portas._apanhando_vao[0]
                and _edicao_hud[0] is None)

    def setup(self, context):
        self.botoes = []

    def draw_prepare(self, context):
        # dois botoes por quina: corrente (desagrega) e regua (resetar)
        botoes = [(corrente, tipo, centro)
                  for corrente in _solda._correntes_hud(context)
                  for tipo, centro in _solda._botoes_da_corrente(context, corrente).items()]
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
            botao.scale_basis = _solda.RAIO_CORRENTE_PX
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
                op = botao.target_set_operator(_solda.OP_RESETAR_DISTANCIA)
                op.chapa = corrente['movel'].name


def _bolinha_2d(shader, ponto, raio, rgba):
    volta = [ponto + Vector((math.cos(i * math.tau / 20),
                             math.sin(i * math.tau / 20))) * raio
             for i in range(21)]
    tris = []
    for a, b in zip(volta, volta[1:]):
        tris += [ponto, a, b]
    shader.uniform_float('color', rgba)
    batch_for_shader(shader, 'TRIS', {'pos': tris}).draw(shader)


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
    if propriedade.startswith('conj_') and _chapas.MARCA_CONJUNTO not in alvo['objeto']:
        # caixa do proprio item (ver `_aplicar_valor_hud`)
        chapas = alvo.get('chapas') or _modulos.grupo_de(alvo['objeto']) or [alvo['objeto']]
        lo, hi = _modulos._caixa_de(chapas)
        return (hi[alvo['eixo']] - lo[alvo['eixo']]) * 1000.0
    return float(getattr(alvo['objeto'], propriedade))


def _redimensionar_chapa_ancorada(chapa, eixo, valor_mm, lado):
    """Muda L (eixo 0), A (eixo 1) ou E (eixo 2) de UMA chapa sem mexer
    na face `lado` ('min'/'max' no eixo local). A malha da chapa e'
    centrada na origem: sem deslocar o centro ela cresceria pelos dois
    lados. Na E a seta escolhe a face parada, no lugar da regra
    "engrossa para dentro" de `_modulos.aplicar_espessura_chapa`."""
    prop = ('chapa_largura_mm', 'chapa_comprimento_mm',
            'chapa_espessura_mm')[eixo]
    antes = getattr(chapa, prop)
    _chapas._ocupado[0] = True
    try:
        setattr(chapa, prop, valor_mm)
    finally:
        _chapas._ocupado[0] = False
    direcao = chapa.matrix_world.to_3x3().col[eixo].normalized()
    sinal = 1.0 if lado == 'min' else -1.0
    _chapas._definir_centro(chapa, _chapas._centro(chapa)
                    + direcao * sinal * (valor_mm - antes) / 2000.0)
    _chapas.gerar_malha_chapa(chapa)


def _aplicar_valor_hud(context, alvo, valor):
    obj = alvo['objeto']
    if alvo['tipo'] == 'gap':
        parametros = dict(obj['porta_parametros'])
        parametros['entre_folhas_mm'] = max(0, valor)
        _portas._aplicar_portas(context, obj, obj.matrix_world.copy(), obj.parent,
                        obj['porta_vao_largura_mm'], obj['porta_vao_altura_mm'],
                        parametros)
        _chapas._ocupado[0] = True
        try:
            _portas._carregar_portas_na_cena(context.scene, obj)
        finally:
            _chapas._ocupado[0] = False
        return
    propriedade = _propriedade_hud(alvo)
    valor = max(20 if propriedade.startswith('conj_') else 1, valor)
    if propriedade == 'chapa_espessura_mm':
        valor = _chapas._espessura_livre(valor)
    # A quina perto do mouse (`lado`) fica parada; os outros eixos nao
    # mudam, entao a ancora deles tanto faz.
    ancoras = None
    if alvo.get('lado') and propriedade.startswith('conj_'):
        ancoras = ['min', 'min', 'min']
        ancoras[alvo['eixo']] = alvo['lado']
    if _chapas.MARCA_CONJUNTO not in obj and propriedade.startswith('conj_'):
        # Grupo de chapas sem Empty. As medidas saem da CAIXA das chapas
        # do proprio item, nao dos campos da cena: estes sao do objeto
        # ativo, e na edicao de varios itens o item pode ser outro.
        chapas = alvo.get('chapas') or _modulos.grupo_de(obj) or [obj]
        lo, hi = _modulos._caixa_de(chapas)
        medidas = [(hi[0] - lo[0]) * 1000.0, (hi[2] - lo[2]) * 1000.0,
                   (hi[1] - lo[1]) * 1000.0]            # L, A, P
        medidas[(0, 2, 1)[alvo['eixo']]] = valor
        _modulos.redimensionar_grupo(chapas, medidas, ancoras)
        pai = chapas[0].parent
        if pai is not None and _chapas.MARCA_CONJUNTO in pai:
            _modulos.reposicionar_origem(pai)
            _modulos.sincronizar_medidas_conjunto(pai)
            _portas.atualizar_portas_do_conjunto(pai)
        if context.object in chapas:
            _modulos.sincronizar_grupo(context)          # a gaveta mostra o novo
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
        (lambda o, c: _modulos.redimensionar_conjunto(o, ancoras))
        if propriedade.startswith('conj_') else
        _chapas._upd_espessura if propriedade == 'chapa_espessura_mm'
        else _chapas._upd_chapa)
    _chapas._ocupado[0] = True
    try:
        setattr(obj, propriedade, valor)
    finally:
        _chapas._ocupado[0] = False
    atualizar(obj, context)
    context.view_layer.update()


def _estado_arraste_hud(context, alvo):
    obj = alvo['objeto']
    modulo = obj if _chapas.MARCA_CONJUNTO in obj else _portas._modulo_da_chapa(obj)
    if modulo is None and _chapas.MARCA_PORTAS in obj:
        modulo = obj.parent if obj.parent and _chapas.MARCA_CONJUNTO in obj.parent else None
    objetos = [modulo, *modulo.children_recursive] if modulo else _selecao.familia_de(obj)
    if not objetos:
        objetos = [obj]
    estado = []
    for o in objetos:
        if _ferragens.CHAVE_FERRAGEM in o:
            # refeitas a cada redimensionar (podem ate' sumir): no
            # cancelar saem de novo da porta, nunca de um backup
            continue
        props = {}
        if _chapas.MARCA_CHAPA in o:
            props = {p: getattr(o, p) for p in
                     ('chapa_largura_mm', 'chapa_comprimento_mm', 'chapa_espessura_mm')}
        if _chapas.MARCA_CONJUNTO in o:
            props.update({p: getattr(o, p) for p in
                          ('conj_largura_mm', 'conj_altura_mm', 'conj_profundidade_mm')})
        porta = ({p: dict(o[p]) if p == 'porta_parametros' else o[p] for p in
                  ('porta_parametros', 'porta_vao_largura_mm', 'porta_vao_altura_mm')}
                 if _chapas.MARCA_PORTAS in o and 'porta_parametros' in o else {})
        if _chapas.MARCA_FOLHA in o and _ferragens.CHAVE_CENTRO_FOLHA in o:
            porta[_ferragens.CHAVE_CENTRO_FOLHA] = tuple(o[_ferragens.CHAVE_CENTRO_FOLHA])
        vertices =[tuple(v.co) for v in o.data.vertices] if o.type == 'MESH' else None
        estado.append((o, o.matrix_world.copy(), o.matrix_parent_inverse.copy(),
                       props, porta, vertices))
    cena = {p: getattr(context.scene, p) for p in
            ('grupo_largura_mm', 'grupo_altura_mm', 'grupo_profundidade_mm',
             'grupo_espessura_mm') + _portas._PROPS_PORTAS_CENA}
    return estado, cena


def _restaurar_arraste_hud(context, estado):
    objetos, cena = estado
    _chapas._ocupado[0] = True
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
            if _chapas.MARCA_PORTAS in obj:
                _ferragens._refazer_ferragens(obj)
        context.view_layer.update()
    finally:
        _chapas._ocupado[0] = False


# Snap ao mover o modulo pela quina (Ctrl segurado): alcance em pixels.
RAIO_SNAP_QUINA_HUD = 20.0


def _quinas_de_snap(modulo):
    """Onde a quina arrastada gruda com Ctrl (pedido do usuario: snap
    ESPECIAL, so' em quinas de OUTROS armarios ou chapas -- nada de
    vertice qualquer, aresta ou grade). Armario = a caixa da HUD dele;
    chapa = os 8 cantos nominais. Pontos copiados: nenhum objeto fica
    guardado no operador."""
    proprios = {modulo, *modulo.children_recursive}
    quinas = []
    for o in bpy.context.view_layer.objects:
        if o in proprios:
            continue
        if _chapas.MARCA_CONJUNTO in o:
            # o Empty e' invisivel: vale o que as chapas mostram
            chapas = [c for c in _modulos._chapas_do_conjunto(o) if c.visible_get()]
            if chapas:
                quinas += _caixa_hud_objetos(chapas) or []
        elif _chapas.MARCA_CHAPA in o and o.type == 'MESH' and o.visible_get():
            quinas += _chapas._cantos(o)
    return quinas


def _snap_de_quina(context, ponto, quinas, escala=1.0):
    """A quina mais perto de `ponto` NA TELA, dentro do alcance, ou None.
    Quinas sobrepostas na tela (uma atras da outra): a mais perto em 3D."""
    tela = _projetar_hud(context, ponto)
    if tela is None:
        return None
    alcance = RAIO_SNAP_QUINA_HUD * escala
    perto = []
    for quina in quinas:
        p = _projetar_hud(context, quina)
        if p is not None and (p - tela).length <= alcance:
            perto.append(((p - tela).length, quina))
    if not perto:
        return None
    minimo = min(d for d, _q in perto)
    return min((q for d, q in perto if d <= minimo + 2.0 * escala),
               key=lambda q: (q - ponto).length).copy()


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
        _selecao._log_clique('HUD pegou %s/%s alvo=%s' % (
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
            self._quinas = None             # snap: medidas no 1o Ctrl
            self._mouse = self._inicio.copy()
        else:
            if _chapas.MARCA_CONJUNTO in alvo['objeto']:
                _modulos.sincronizar_medidas_conjunto(alvo['objeto'])
            elif alvo.get('modo') == 'GRUPO':
                _modulos.sincronizar_grupo(context)     # valor de partida real
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

    def _mover_pela_quina(self, context, mouse, snap):
        """Leva a quina pega ate' o mouse; com `snap` (Ctrl) ela gruda
        na quina de outro armario/chapa que estiver no alcance."""
        ponto = view3d_utils.region_2d_to_location_3d(
            context.region, context.region_data, mouse, self._origem)
        destino = self._origem + ponto - self._ponto_mouse
        grudou = None
        if snap:
            if self._quinas is None:
                self._quinas = _quinas_de_snap(self._alvo['objeto'])
            grudou = _snap_de_quina(context, destino, self._quinas,
                                    context.preferences.system.ui_scale)
            if grudou is not None:
                destino = grudou
        matriz = self._matriz.copy()
        matriz.translation += destino - self._origem
        self._alvo['objeto'].matrix_world = matriz
        self._alvo['pontos'] = [destino]
        _edicao_hud[0]['snap'] = grudou
        context.view_layer.update()

    def cancel(self, context):
        for backup in reversed(getattr(self, '_backups', [self._backup])):
            _restaurar_arraste_hud(context, backup)
        self._encerrar()

    def _comecar_digitacao(self):
        estado = _edicao_hud[0]
        estado['fase'] = None
        estado['hover'] = None
        estado['texto'] = _opcoes._numero_na_unidade(_valor_hud(estado['itens'][0]))
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
                valor = _gaveta_desenho._ler_medida_digitada(estado['texto']) * 1000.0
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
        if _gaveta_desenho._tecla_no_texto(estado, event.type, entrada, event.ctrl):
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
            largura = _gaveta_desenho._medidor_blf(tamanho)
            blf.size(0, tamanho)
            altura = blf.dimensions(0, '0')[1]
            folga = 4 * escala
            if (x - folga <= mx <= x + largura(_gaveta_desenho._com_cursor(texto, cursor)) + folga
                    and y - folga <= my <= y + altura + folga):
                estado['cursor'] = _gaveta_desenho._cursor_no_x(texto, cursor, x, mx, largura)
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
                texto = _opcoes._numero_na_unidade(self._valor)
                _edicao_hud[0].update(texto=texto, cursor=len(texto),
                                      selecionado=True)
                self._area.tag_redraw()
                return {'RUNNING_MODAL'}
            self._encerrar()
            return {'FINISHED'}
        if (event.type in {'LEFT_CTRL', 'RIGHT_CTRL'} and self._arrastou
                and self._alvo['tipo'] == 'ancora'
                and event.value in {'PRESS', 'RELEASE'}):
            # apertar/soltar o Ctrl parado ja' liga/desliga o snap
            self._mover_pela_quina(context, self._mouse,
                                   event.value == 'PRESS')
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
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
                self._mouse = mouse
                self._mover_pela_quina(context, mouse, event.ctrl)
            else:
                delta = (mouse-self._inicio).dot(self._direcao) * self._por_pixel
                _aplicar_valor_hud(context, self._alvo, self._valor + delta)
        except (ValueError, TypeError, ReferenceError) as erro:
            self.report({'WARNING'}, str(erro))
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}


# ---- grid de medidas na cena (tabelas e estado: `EIXOS_MEDIDA`,
# `_handler_grid`, `_realce_medida`)
def _cantos_caixa(origem, u, v, w):
    return [origem + u * i + v * j + w * k
            for k in (0, 1) for j in (0, 1) for i in (0, 1)]


def _alvos_da_medida(context, modo):
    """Objetos que a medida daquele modo governa."""
    obj = context.object
    if modo == 'GRUPO' and obj is not None:
        familia = [o for o in _selecao.familia_de(obj) if o.type in _modulos.TIPOS_COM_VOLUME]
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
            if _chapas.MARCA_CHAPA in obj:
                # nominal: o corte do perfil nao encolhe a chapa medida
                meias = Vector(_chapas._meias(obj))
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

    limites = _modulos._limites_mundo(context, _alvos_da_medida(context, modo))
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
    _arame._desenhar_aramados(bpy.context)
