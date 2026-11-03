"""HUD parametrica na viewport: linhas, rotulos, setas, quinas e arraste,
os gizmos das correntes e o grid de medidas dos campos da gaveta."""

import bpy, math, gpu, blf, time, json
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from bpy_extras import view3d_utils
from bpy.types import Gizmo, GizmoGroup, Operator, Macro

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = None
_frentes = None
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
_paredes = None
_paredes_edicao = None
_paredes_composicao = None
_gaveta_desenho = None
_formas = None
_gavetas = None
_prateleiras = None
_divisorias = None
_assistente = None
_hud_volume = None
_areas_criacao = None
_visibilidade = None

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
RAIO_PONTO_PAREDE_PX = 5.0  # bolinha do centro da borda na parede: cheia e com halo
LIMIAR_ARRASTE_HUD_PX = 4.0  # abaixo disto o gesto e' clique, nao arraste
GRAUS_POR_PIXEL_HUD = 0.25   # arraste do arco do angulo da diagonal


def _contexto_hud(context):
    """Onde a HUD existe. Durante G/R/S ela some inteira -- linhas,
    letras, seta e hover -- e volta quando o gesto termina."""
    if _visibilidade._edicao[0] or _solda._conexao_manual[0] is not None or _solda._arraste_ancora[0] is not None:
        _hover_hud.clear()
        return False
    if _eventos._transformando() and not _hud_volume._estado[0]:
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
    restante = context.space_data.clip_end
    depsgraph = context.evaluated_depsgraph_get()
    while restante > 0:
        acertou, ponto, normal, face, obj, matriz = context.scene.ray_cast(
            depsgraph, origem, direcao, distance=restante)
        if not acertou or obj is None:
            return None
        if (not _visibilidade.esmaecido(obj.original)
                and obj.original.visible_get(view_layer=context.view_layer, viewport=context.space_data)):
            return obj.original, ponto, normal, face, matriz
        # O ray cast da cena inclui objetos fora da vista local. Seguir
        # pelo motor nativo evita selecionar a parede oculta diante do movel.
        passo = (ponto - origem).length + .00001
        restante -= passo
        origem = ponto + direcao * .00001
    return None


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


def _familia_do_clique(obj, context=None):
    """O que um clique simples em `obj` seleciona: o modulo com tudo
    dentro, ou o grupo solto da chapa."""
    modulo = _portas._modulo_da_chapa(obj)
    if modulo is not None:
        # ferragem nao acende com o modulo (seleciona-se por si mesma)
        familia = [modulo, *(o for o in modulo.children_recursive
                            if _ferragens.CHAVE_FERRAGEM not in o)]
    else:
        familia = _selecao.familia_de(obj)
    return _selecao.objetos_na_camada(context or bpy.context, familia)


def _somar_peca(context, obj, duplo=False):
    """Shift na viewport: SOMA a selecao, como no Blender (pedido do
    usuario).

    - Shift+clique: o modulo inteiro de `obj`; mas se o grupo dele ja'
      esta' em selecao INDIVIDUAL (parte dele selecionada), so' a chapa
      -- e clicar de novo na chapa ativa a tira, como o Shift nativo.
    - Shift+duplo clique: isola `obj` DENTRO da selecao: o resto do grupo
      dele sai, os outros grupos e chapas ficam. O 1o clique do duplo ja'
      somou o grupo, por isso o duplo so' encolhe o grupo de `obj`."""
    familia = [o for o in _familia_do_clique(obj, context) if o.visible_get(view_layer=context.view_layer)]
    if obj not in familia:
        return
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
    familia = _familia_do_clique(obj, context)
    alvos = _selecao.objetos_na_camada(context, [obj] if individual else familia or [obj])
    if not alvos:
        return
    if not somar:
        for selecionado in context.selected_objects:
            selecionado.select_set(False)
    for alvo in alvos:
        alvo.select_set(True, view_layer=context.view_layer)
    _chapas._ocupado[0] = True
    try:
        obj.chapa_modo = 'INDIVIDUAL' if individual else 'GRUPO'
    finally:
        _chapas._ocupado[0] = False
    # Shift conserva o grupo, mas a malha clicada e' a mestre dos operadores nativos.
    context.view_layer.objects.active = modulo if not individual and not somar and modulo in alvos else obj
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
    if ativo == grupo or (grupo.select_get() and _chapas.MARCA_FOLHA in ativo
                          and _portas._grupo_portas(ativo) == grupo):
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
    alvos = _selecao.objetos_na_camada(context,
        [grupo, *_portas._folhas_portas(grupo)] if nivel == 'PORTA' else [folha])
    if not alvos or folha not in alvos:
        return
    if not somar:
        for selecionado in context.selected_objects:
            selecionado.select_set(False)
    if nivel == 'PORTA':
        for alvo in alvos:
            alvo.select_set(True, view_layer=context.view_layer)
        context.view_layer.objects.active = grupo if not somar and grupo in alvos else folha
    else:
        folha.select_set(True, view_layer=context.view_layer)
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
    if _areas_criacao.escolhendo_frente():
        return None
    area = _areas_criacao.objeto()
    if area is not None:
        return area, 'AREA_CRIACAO', []
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
    if _areas_criacao.escolhendo_frente():
        return []
    area = _areas_criacao.objeto()
    if area is not None:
        return [(area, 'AREA_CRIACAO', [])]
    nativo = _hud_volume._estado[0]
    if nativo and nativo.get('modo') == 'INDIVIDUAL':
        # ONLY_SELECTABLE tira a chapa do snap destino e da selecao nativa.
        # O escopo visual fica no item que iniciou o gesto ate' confirmar/Esc.
        obj = bpy.data.objects.get(nativo['objeto'])
        return [(obj, 'INDIVIDUAL', [obj])] if obj is not None else []
    obj = context.object
    if (obj is not None and obj.select_get()
            and (_chapas.MARCA_PORTAS in obj or _chapas.MARCA_FOLHA in obj)):
        return []
    itens = _itens_da_selecao(context)
    orientacao = ('PRATELEIRAS' if _prateleiras.grupo_de(obj) is not None else
                  'DIVISORIAS' if _divisorias.grupo_de(obj) is not None else None)
    return [i for i in itens if not orientacao or i[1] not in {'PRATELEIRAS','DIVISORIAS'} or i[1] == orientacao]


def _geometrias_hud(context):
    geometrias = [g for g in (_geometria_do_item(*item) for item in _itens_hud(context))
                  if g is not None]
    if _paredes_edicao.ativa(context):
        geometrias = [_geometria_na_parede(g) for g in geometrias]
    return geometrias


def _geometria_na_parede(geometria):
    """Na vista da parede, so' as medidas NO plano dela: a profundidade
    se ve de ponta e seus pontos de face cairiam no meio do modulo, em
    cima do clique que move."""
    normal = Vector(_paredes_edicao._sessao[0]['normal'])
    linhas = [l for l in geometria['linhas']
              if abs((l['pontos'][-1] - l['pontos'][0]).normalized().dot(normal)) < .5]
    return dict(geometria, linhas=linhas)


def _hud_na_parede():
    """Na parede a HUD so' edita a geometria (pontos das faces e setas das
    quinas, pedido do usuario): a quina acesa do snap e o mover sao da
    composicao. Durante a edicao ela continua ate' o fim."""
    if _edicao_hud[0] is not None or _hud_volume._estado[0] is not None:
        return True
    return (_paredes_composicao._quina_hover[0] is None
            and _paredes_composicao._movendo[0] is None)


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
        pai = o.parent
        while pai is not None and not (
                pai in marcados and _chapas.MARCA_CONJUNTO in pai):
            pai = pai.parent
        if pai is not None and _chapas.MARCA_CONJUNTO in pai:
            # Os filhos acendem com o modulo, mas nao sao novos alvos.
            # O argumento era calculado ANTES de somar eliminar a copia:
            # cada peca/rig selecionado relia todas as chapas da cena.
            if ('M', pai.name) not in chaves:
                somar(pai, 'GRUPO', _modulos.pecas_do_envelope(pai))
            continue
        divisorias = _divisorias.grupo_de(o)
        if divisorias is not None:
            chave = ('D', divisorias.parent, divisorias.get(_divisorias.CHAVE_BLOCAGEM, divisorias.name))
            if chave not in chaves:
                chaves.add(chave)
                itens.append((divisorias, 'DIVISORIAS', []))
            continue
        prateleiras = _prateleiras.grupo_de(o)
        if prateleiras is not None:
            # prateleiras (o grupo ou uma, pelo duplo): as linhas do vao
            chave = ('PR', prateleiras.parent, prateleiras.get(_divisorias.CHAVE_BLOCAGEM, prateleiras.name))
            if chave not in chaves:
                chaves.add(chave)
                itens.append((prateleiras, 'PRATELEIRAS', []))
            continue
        grupo = _gavetas.grupo_de(o)
        if grupo is not None and (o == grupo or _gavetas.MARCA_GAVETA in o):
            # gavetas selecionadas: SO' elas tem linha (pedido do usuario)
            if ('G', grupo.name) not in chaves:
                chaves.add(('G', grupo.name))
                itens.append((grupo, 'GAVETAS', []))
            continue
        if grupo is not None and (grupo.select_get() or any(
                g.select_get() for g in _gavetas.gavetas_do_grupo(grupo))):
            continue            # peca de gaveta selecionada junto: e' a gaveta
        if grupo is not None and _portas._modulo_da_chapa(o) is None:
            continue
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


def _sistema_hud(tipo):
    """Mesmo dono para desenho, valor, edicao e cancelamento da cota."""
    return {'gavetas': _gavetas, 'prateleiras': _prateleiras, 'area_criacao': _areas_criacao,
            'divisorias': _divisorias}.get(tipo.lower()) if isinstance(tipo, str) else None


def _geometria_do_item(obj, modo, chapas):
    """A geometria da HUD de UM item -- o ativo ou, na edicao de varios
    itens, cada modulo/chapa que entra na conta."""
    dono = _sistema_hud(modo)
    if dono is not None:
        cantos, linhas = dono.linhas_hud(obj, chapas)
        _numerar_cotas(linhas)
        return {'objeto': obj, 'modo': modo, 'chapas': chapas,
                'cantos': cantos, 'linhas': linhas}
    secao=(obj.data.get(_chapas.CHAVE_ESPESSURA) if modo=='INDIVIDUAL'
           and obj.type=='MESH' and _chapas.MARCA_CHAPA in obj else None)
    if secao and secao.get('arestas'):
        cantos=[];linhas=[]
        for uid,aresta in secao['arestas'].items():
            pontos=[obj.matrix_world@Vector(p) for p in aresta['pontos']]
            cantos.extend(pontos)
            linha=dict(objeto=obj,modo=modo,chapas=chapas,seta_real=True,pontos=pontos)
            if aresta['espessura']:
                linha.update(tipo='medida',eixo=2,letra='E',borda_real=('E',int(uid)))
            else:
                linha.update(tipo='aresta',face=(int(uid),),letra='BORDA')
            linhas.append(linha)
        _numerar_cotas(linhas)
        return dict(objeto=obj,modo=modo,chapas=chapas,cantos=cantos,linhas=linhas)
    if secao and secao.get('dobrada') and secao.get('bordas'):
        cantos,linhas=_linhas_da_secao(obj,chapas,secao)
        _numerar_cotas(linhas)
        return dict(objeto=obj,modo=modo,chapas=chapas,cantos=cantos,linhas=linhas)
    # O escopo decide a referencia: o modulo e' sempre uma caixa.
    # So' a chapa isolada oferece o contorno/angulo de sua propria face.
    forma = (_formas.forma_do_modulo(obj) if modo == 'INDIVIDUAL'
             and obj.type == 'MESH' and _chapas.MARCA_CHAPA in obj else None)
    if forma is not None:
        cantos, linhas = _linhas_da_forma(obj, chapas, forma)
    else:
        matriz = obj.matrix_world if modo == 'INDIVIDUAL' else None
        cantos = _caixa_hud_objetos(chapas, matriz)
        if cantos is None:
            return None
        letras = ('L', 'A', 'E') if modo == 'INDIVIDUAL' else ('L', 'P', 'A')
        linhas = []
        for eixo, arestas in enumerate(ARESTAS_EIXO):
            for i, j in arestas:
                linhas.append(dict(tipo='medida', objeto=obj, modo=modo,
                    eixo=eixo, letra=letras[eixo], cantos=(i,j), chapas=chapas,
                    pontos=[cantos[i],cantos[j]]))
    if modo=='INDIVIDUAL':
        secao=obj.data.get(_chapas.CHAVE_ESPESSURA)
        if secao and secao.get('dobrada'):
            # E segue arestas transversais reais, nunca a flecha da dobra.
            espessuras=[l for l in linhas if l.get('letra')=='E']
            if espessuras:
                modelo=espessuras[0]
                linhas=[l for l in linhas if l.get('letra')!='E']
                for i,par in enumerate(secao['pares'].values()):
                    linha=dict(modelo,pontos=[obj.matrix_world@Vector(p) for p in par],
                               seta_real=True,borda_real=('E',i))
                    linha.pop('cantos',None)
                    linhas.append(linha)
        if secao and secao.get('deslocamento_mm',0)>secao.get('espessura_mm',0)+.01:
            linhas.append(dict(tipo='deslocamento',objeto=obj,modo=modo,chapas=chapas,
                letra='DESLOCAMENTO',eixo=2,seta_real=True,
                pontos=[obj.matrix_world@Vector(p) for p in secao['linha_deslocamento']]))
    _numerar_cotas(linhas)
    return dict(objeto=obj,modo=modo,chapas=chapas,cantos=cantos,linhas=linhas)


def _linhas_da_secao(obj, chapas, secao):
    """Contorno 3D da madeira editada, nunca uma extrusao do seu envelope.

    So' consome coordenadas preparadas fora do desenho. Frente e verso
    compartilham a cota sem somar diagonais internas da triangulacao.
    """
    matriz=obj.matrix_world;linhas=[];cantos=[];pares={}
    comum=dict(objeto=obj,modo='INDIVIDUAL',chapas=chapas)
    for uid,borda in secao['bordas'].items():
        a,aa,b,bb=[Vector(p) for p in borda]
        pares[tuple(a)]=(a,aa);pares[tuple(b)]=(b,bb)
        for lado in (0,1):
            pontos=[matriz@p for p in ((a,b) if lado==0 else (aa,bb))]
            linhas.append(dict(comum,tipo='aresta',face=(int(uid),),letra='BORDA',
                               seta_real=True,pontos=pontos))
            cantos.extend(pontos)
    for i,(a,b) in enumerate(pares.values()):
        linhas.append(dict(comum,tipo='medida',eixo=2,letra='E',seta_real=True,
                           borda_real=('E',i),pontos=[matriz@a,matriz@b]))
    if secao.get('deslocamento_mm',0)>secao['espessura_mm']+.01:
        # A projecao fica junto a uma borda baixa real e termina antes de E.
        # Nao atravessa o centro da peca nem prolonga sua caixa antiga.
        a,b=min(pares.values(),key=lambda par:((matriz@par[0]).z,-par[0].z))
        lo=min(p[0].z for p in pares.values());hi=max(p[0].z for p in pares.values())
        pontos=[matriz@Vector((a.x,a.y,z)) for z in (lo,hi)]
        linhas.append(dict(comum,tipo='deslocamento',eixo=2,letra='DESLOCAMENTO',
                           seta_real=True,pontos=pontos))
    escala=max(1.,getattr(bpy.context.preferences.system,'ui_scale',1.))
    for quina in secao.get('quinas',{}).values():
        p,a,b=[matriz@Vector(quina[k]) for k in ('ponto','a','b')]
        va,vb=a-p,b-p
        if min(va.length,vb.length)<1e-8:continue
        base=va.normalized();ate=vb.normalized()
        angulo=base.angle(ate);normal=ate-base*base.dot(ate)
        if normal.length<1e-8:continue
        mm_px=_mm_por_pixel(p)
        raio=min((RAIO_ARCO_ANGULO_PX*escala*mm_px if mm_px is not None else RAIO_ARCO_ANGULO_MM)/1000,
                 FRACAO_ARCO_ANGULO*min(va.length,vb.length))
        normal.normalize();pontos=[];anterior=None
        for i in range(PASSOS_ARCO_ANGULO+1):
            t=angulo*i/PASSOS_ARCO_ANGULO
            atual=p+raio*(base*math.cos(t)+normal*math.sin(t))
            if anterior is not None:pontos.extend((anterior,atual))
            anterior=atual
        linhas.append(dict(comum,tipo='angulo_aresta',face=tuple(quina['face']),
                           angulo=True,letra=None,vertice=p,pontos=pontos))
    return cantos,linhas


def _numerar_cotas(linhas):
    """Rotulos independem dos identificadores de edicao/arquivos antigos."""
    def chave(linha):
        if linha['tipo']=='aresta':return ('aresta',tuple(linha['face']))
        return (('forma',tuple(linha['face']),linha.get('plano','XY'))
                if linha['tipo']=='forma' else ('letra',linha['letra']))
    presentes={chave(l):l['letra'] for l in linhas if l.get('letra') and l['letra']!='E'}
    ordem=[k for letra in ('L','A','P') for k,l in presentes.items() if l==letra]
    ordem.extend(k for k in presentes if k not in ordem)
    numeros={k:'A%d'%(i+1) for i,k in enumerate(ordem)}
    for linha in linhas:
        letra=linha.get('letra')
        if letra:linha['rotulo']='E' if letra=='E' else numeros[chave(linha)]


def rotulo_medida(nome):
    """Mesma nomenclatura no menu e na HUD; props conservam seus nomes."""
    return {'Largura':'A1','Largura da folha':'A1','Altura':'A2','Profundidade':'A3'}.get(nome,nome)


def chave_cota(linha):
    """Identidade semantica, sem RNA nem numero A dependente da selecao."""
    return json.dumps([linha['tipo'],linha.get('eixo'),linha.get('face'),
                       linha.get('plano','XY')],separators=(',',':'))


def alvo_cota(obj, chave):
    modo='GRUPO' if _chapas.MARCA_CONJUNTO in obj else 'INDIVIDUAL'
    chapas=_modulos.pecas_do_envelope(obj) if modo=='GRUPO' else [obj]
    geo=_geometria_do_item(obj,modo,chapas)
    if geo:
        for linha in geo['linhas']:
            if linha.get('rotulo') and chave_cota(linha)==chave:return dict(linha,lado='min')
    # Arrastar abaixo do limiar esconde a cota, mas nao perde o gesto.
    try:tipo,eixo,face,plano=json.loads(chave)
    except (ValueError,TypeError):raise ValueError('Cota invalida')
    if tipo=='deslocamento' and modo=='INDIVIDUAL':
        return dict(tipo=tipo,objeto=obj,modo=modo,eixo=2,chapas=chapas)
    raise ValueError('A geometria nao possui mais essa cota')


def campos_cotas(obj, modo, chapas):
    """Menu e viewport editam os mesmos alvos e os mesmos valores."""
    geo=_geometria_do_item(obj,modo,chapas)
    campos={}
    for linha in geo['linhas'] if geo else ():
        nome=linha.get('rotulo')
        if not nome or nome in campos or linha.get('angulo'):continue
        campos[nome]=(nome,_valor_hud(linha),chave_cota(linha))
    return sorted(campos.values(),key=lambda c:(c[0]=='E',int(c[0][1:]) if c[0]!='E' else 0))


def _linhas_da_forma(obj, chapas, forma):
    """Modulo em L ou diagonal (`_formas`): a linha branca segue a
    PLANTA, em baixo e em cima. L/P totais nos lados inteiros (esticam
    sem deformar o canto), P1/P2 nos lados que chegam no canto (a
    profundidade de cada braco), R na diagonal e A nas quinas."""
    plano=forma.get('plano','XY')
    modo='INDIVIDUAL' if obj.type=='MESH' else 'GRUPO'
    matriz = _formas.matriz_do_modulo(obj,plano)
    letras={'XY':('L','P','A'),'XZ':('L','A','P'),'YZ':('P','A','L')}[plano]
    if modo=='INDIVIDUAL':letras=('L','A','E')
    lo, hi = forma['lo'], forma['hi']

    def mundo(x, y, z):
        return matriz @ (Vector((x, y, z)) / 1000.0)
    cantos = [mundo(lo.x if i == 0 else hi.x, lo.y if j == 0 else hi.y,
                    lo.z if k == 0 else hi.z)
              for k in (0, 1) for j in (0, 1) for i in (0, 1)]
    giro = matriz.to_3x3()
    linhas = []
    for seg in _formas.segmentos(forma):
        for k, z in enumerate((lo.z, hi.z)):
            pontos = [mundo(*seg['a'], z), mundo(*seg['b'], z)]
            if seg['chave'] is None:
                linhas.append({'tipo': 'contorno_forma', 'objeto': obj,
                               'pontos': pontos})
                continue
            linha = {'tipo': 'forma', 'objeto': obj, 'modo': modo,
                     'chapas': chapas, 'letra': seg['letra'], 'plano': plano,
                     'face': seg['chave'], 'pontos': pontos}
            if seg['direcao'] is not None:
                linha['direcao'] = (giro @ Vector((*seg['direcao'], 0.0))).normalized()
            if seg['cantos'] is not None:
                linha['cantos'] = tuple(c + 4 * k for c in seg['cantos'])
            if plano!='XY' or modo=='INDIVIDUAL':
                linha['letra']={'L':letras[0],'P':letras[1],
                                'P1':letras[1]+'1','P2':letras[0]+'1','R':'R'}.get(seg['letra'])
            linhas.append(linha)
    linhas += _arcos_da_diagonal(obj, chapas, forma, mundo)
    if plano!='XY':
        linhas += _arcos_da_diagonal(obj,chapas,forma,mundo,lo.z)
    for x, y, sobe in _formas.contorno(forma):
        if not sobe:
            continue
        pontos = [mundo(x, y, lo.z), mundo(x, y, hi.z)]
        # A normal de XZ aponta para -Y para conservar uma base direita.
        # A seta de P continua de min para max no eixo real do modulo.
        if plano=='XZ':pontos.reverse()
        quina = next((i + 2 * j for i in (0, 1) for j in (0, 1)
                      if abs(x - (lo.x, hi.x)[i]) < 1e-6
                      and abs(y - (lo.y, hi.y)[j]) < 1e-6), None)
        if quina is None:
            linhas.append({'tipo': 'contorno_forma', 'objeto': obj,
                           'pontos': pontos})
        else:
            eixo={'XY':2,'XZ':1,'YZ':0}[plano]
            linhas.append({'tipo': 'medida', 'objeto': obj, 'modo': modo,
                           'eixo': eixo, 'letra': letras[2], 'cantos': (quina, quina + 4),
                           'chapas': chapas, 'pontos': pontos, 'plano': plano})
    return cantos, linhas


# Arco do ANGULO nas pontas da diagonal (esboco do usuario): pequeno e
# colado na quina, como o do gizmo de angulo -- raio fixo NA TELA (a 70 mm
# ele atravessava a peca de perto), nunca mais que uma fracao do lado mais
# curto da quina; sem viewport (testes), em mm
RAIO_ARCO_ANGULO_PX = 26.0
FRACAO_ARCO_ANGULO = 0.25
RAIO_ARCO_ANGULO_MM = 30.0
PASSOS_ARCO_ANGULO = 12


def _mm_por_pixel(ponto):
    """Quantos mm vale 1 px de tela em `ponto` (mundo), ou None sem
    viewport."""
    contexto = bpy.context
    regiao, rv3d = getattr(contexto, 'region', None), getattr(contexto, 'region_data', None)
    if regiao is None or rv3d is None or getattr(regiao, 'type', '') != 'WINDOW':
        return None
    direita = rv3d.view_matrix.to_3x3().transposed().col[0].normalized() * 0.1
    a = view3d_utils.location_3d_to_region_2d(regiao, rv3d, ponto)
    b = view3d_utils.location_3d_to_region_2d(regiao, rv3d, ponto + direita)
    if a is None or b is None or (b - a).length < 1e-6:
        return None
    return 100.0 / (b - a).length


def _arcos_da_diagonal(obj, chapas, forma, mundo, altura=None):
    """Linhas da HUD com o arco do angulo nas DUAS pontas de cada diagonal,
    em cima: o angulo de DENTRO da planta ali (135 numa diagonal a 45).
    Cada arco e' uma linha 'forma' de face ('ANG', canto, ponta): passar o
    mouse acende, clicar digita o angulo, arrastar de lado gira."""
    linhas = []
    z = forma['hi'].z if altura is None else altura
    escala = max(1.0, getattr(bpy.context.preferences.system, 'ui_scale', 1.0))
    for k, f in enumerate(forma['cantos']):
        if f is None or f['tipo'] != 'CHANFRO':
            continue
        pa, pb = _formas.pontas_diagonal(forma, k)
        diagonal = (pb - pa)
        for ponta, vertice, outra in (('A', pa, pb), ('B', pb, pa)):
            lado, comprimento = _formas.lado_da_ponta(forma, k, ponta)
            if lado is None:
                continue
            mm_px = _mm_por_pixel(mundo(vertice.x, vertice.y, z))
            raio = (RAIO_ARCO_ANGULO_PX * escala * mm_px if mm_px is not None
                    else RAIO_ARCO_ANGULO_MM)
            raio = min(raio, FRACAO_ARCO_ANGULO * min(diagonal.length, comprimento))
            ate = (outra - vertice).normalized()
            inicio = math.atan2(lado.y, lado.x)
            giro = math.atan2(lado.x * ate.y - lado.y * ate.x, lado.dot(ate))
            pontos = []
            anterior = None
            for i in range(PASSOS_ARCO_ANGULO + 1):
                t = inicio + giro * i / PASSOS_ARCO_ANGULO
                p = mundo(vertice.x + raio * math.cos(t), vertice.y + raio * math.sin(t), z)
                if anterior is not None:
                    pontos += [anterior, p]
                anterior = p
            visto, base, sinal = _formas.dados_angulo_da_ponta(forma, k, ponta)
            linhas.append({'tipo': 'forma', 'objeto': obj, 'modo': 'INDIVIDUAL' if obj.type=='MESH' else 'GRUPO',
                           'chapas': chapas, 'letra': None, 'angulo': True,
                           'vertice': mundo(vertice.x, vertice.y, z),
                           'base': base, 'sinal': sinal,
                           'face': ('ANG', k, ponta), 'pontos': pontos})
            linhas[-1]['plano']=forma.get('plano','XY')
    return linhas


def _angulo_da_ponta(alvo):
    """O angulo de DENTRO da planta na ponta do arco `alvo`."""
    if alvo['tipo']=='angulo_aresta':
        secao=alvo['objeto'].data.get(_chapas.CHAVE_ESPESSURA,{})
        quina=secao.get('quinas',{}).get(':'.join(str(uid) for uid in alvo['face']))
        if not quina:raise ValueError('A quina nao existe mais')
        p,a,b=[Vector(quina[k]) for k in ('ponto','a','b')]
        return math.degrees((a-p).angle(b-p))
    if alvo['face'][0]=='JUNTA':return _formas.dados_junta(alvo['objeto'],alvo['face'])['angulo']
    forma = _formas.forma_do_modulo(alvo['objeto'],alvo.get('plano','XY'))
    k, ponta = alvo['face'][1:]
    if forma is None or forma['cantos'][k] is None:
        return 90.0
    return _formas.dados_angulo_da_ponta(forma, k, ponta)[0]


def _eh_angulo(alvo):
    return bool(alvo) and (alvo.get('tipo')=='angulo_aresta' or
        alvo.get('tipo')=='forma' and alvo.get('face',('',))[0] in ('ANG','JUNTA'))


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
            alvo.get('eixo'), alvo.get('canto'), None if alvo.get('face',('',))[0]=='BLOCO' else alvo.get('face'),alvo.get('plano','XY'),
            alvo.get('borda_real'))


def _acertar_linhas_hud(geometria, mouse, projetar, escala=1, cantos=True, so_faces=False):
    """Distancia em pixels: funciona em perspectiva, ortografica e orbitando.

    `cantos=False` ignora as quinas: escolhendo a linha do proximo item
    so' medidas interessam, nunca mover o modulo. `so_faces=True` (parede,
    pedido do usuario) deixa so' as bolinhas do centro das bordas: sem
    setas nas arestas e sem ancora na quina, que e' do snap."""
    mouse = Vector(mouse)
    obj = geometria['objeto']
    if cantos:
        raio = (RAIO_PONTO_PAREDE_PX + 3 if so_faces else 8) * escala
        centros = [(c, projetar(c['pontos'][1])) for c in _hud_volume.controles(geometria)]
        perto = [(c, (mouse-p).length) for c, p in centros
                 if p is not None and (mouse-p).length <= raio]
        if perto:
            return min(perto, key=lambda par: par[1])[0]
    if so_faces:
        return None
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
        if linha['tipo'] in ('contorno_porta', 'contorno_forma') or not linha.get('editavel',True):
            continue
        # linha de varios trechos (o arco do angulo): pares de pontos
        melhor = None
        for p, q in zip(linha['pontos'][0::2], linha['pontos'][1::2]):
            a, b = projetar(p), projetar(q)
            if a is None or b is None:
                continue
            distancia = _distancia_segmento_hud(mouse, a, b)
            if melhor is None or distancia < melhor[0]:
                melhor = (distancia, a, b)
        if melhor is not None and melhor[0] <= RAIO_ARESTA_HUD * escala:
            candidatos.append((melhor[0], linha, melhor[1], melhor[2]))
    if not candidatos:
        return None
    _d, linha, a, b = min(candidatos, key=lambda item: (item[0],-item[1].get('prioridade',0)))
    if linha['tipo'] == 'medida' or linha.get('cantos') or linha.get('seta_real'):
        # A quina mais perto do mouse fica PARADA e o movel cresce para
        # o outro lado -- modulo (L/A/P) e chapa individual (L/A/E: a
        # Espessura tambem tem seta nas quinas, pedido do usuario). Em
        # ARESTAS_EIXO o primeiro canto e' o do lado minimo do eixo.
        # Copia: a linha da geometria e' compartilhada.
        lado = linha.get('lado_fixo') or ('min' if (mouse - a).length <= (mouse - b).length else 'max')
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
    pontos = [projetar(p) for p in (alvo['pontos'][1:2]
              if alvo.get('controle_face') else alvo['pontos'][:2])]
    if any(p is None for p in pontos):
        return float('inf')
    if len(pontos) == 1:
        return (Vector(mouse) - pontos[0]).length
    return _distancia_segmento_hud(Vector(mouse), *pontos)


def _acertar_hud(context, posicao):
    """Quina ou linha mais perto do mouse entre TODOS os itens da
    selecao; quina antes de linha, como dentro de um item."""
    parede = _paredes_edicao.ativa(context)
    if not _contexto_hud(context) or (parede and not _hud_na_parede()):
        return None
    geometrias = _geometrias_hud(context)
    if not geometrias:
        return None
    escala = context.preferences.system.ui_scale
    projetar = lambda p: _projetar_hud(context, p)
    melhor = None
    for geometria in geometrias:
        alvo = _acertar_linhas_hud(geometria, posicao, projetar, escala, so_faces=parede)
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
    if chapas and not parede:
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
    nome=_realce_medida[0]
    if nome:
        nome=rotulo_medida(nome)
        for geo in _geometrias_hud(context):
            if geo['objeto']!=context.object:continue
            linha=next((l for l in geo['linhas'] if l.get('rotulo')==nome),None)
            if linha is not None:return dict(linha,lado='min')
    chave = context.region.as_pointer()
    alvo = _hover_hud.get(chave)
    if alvo is not None and not _alvo_vivo(alvo):
        _hover_hud.pop(chave, None)
        return None
    if (alvo and not _opcoes._opcao('hud_setas_quinas')
            and not alvo.get('controle_face')
            and (alvo.get('lado') or alvo['tipo']=='ancora')):
        return None
    if alvo and alvo.get('controle_face') and not _opcoes._opcao('hud_pontos_apoio'):
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
    parede = _paredes_edicao.ativa(context)
    if not _contexto_hud(context) or (parede and not _hud_na_parede()):
        return
    normais, acesos, pendentes, principais = [], {}, [], []
    desenhos = _desenhos_hud(context)
    principal = _principal_hud(context, desenhos)
    for indice, (geometria, alvo) in enumerate(desenhos):
        n, a = _segmentos_hud(geometria, alvo)
        if parede:
            n = []      # o contorno do modulo ja' e' o nativo: so' a aresta acesa
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
    for corrente in ([] if parede else _solda._correntes_hud(context)):
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
        if linha['tipo'] not in ('medida', 'forma', 'aresta') and _sistema_hud(linha['tipo']) is None:
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
    for letra in dict.fromkeys(l.get('rotulo',l.get('letra'))
                              for l in geometria['linhas'] if l.get('letra')):
        candidatos = []
        for linha in geometria['linhas']:
            if linha.get('rotulo',linha.get('letra')) != letra:
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
    # arco do angulo da diagonal: o valor em graus, do lado de fora do arco
    for linha in geometria['linhas']:
        if not linha.get('angulo'):
            continue
        meio = _projetar_hud(context, linha['pontos'][len(linha['pontos']) // 2])
        vertice = _projetar_hud(context, linha['vertice'])
        if meio is None or vertice is None:
            continue
        # o numero logo FORA do arco, na bissetriz (no meio dele tampava a
        # linha; no centro da forma ficava longe da quina)
        fora = meio - vertice
        ponto = meio + (fora.normalized() * tamanho if fora.length > 1e-6 else Vector())
        aceso = _identidade_hud(linha) == _identidade_hud(alvo)
        try:
            graus = _angulo_da_ponta(linha)
        except ValueError:
            continue
        if cabem or aceso:
            rotulos.append(['%d\u00b0' % round(graus), ponto, aceso])
    # vao entre prateleiras: o VALOR (sao varios, uma letra so' nao diria
    # qual), a' direita do meio da linha
    for linha in geometria['linhas']:
        if not linha.get('vao'):
            continue
        a, b = (_projetar_hud(context, p) for p in linha['pontos'][:2])
        if a is None or b is None:
            continue
        aceso = _identidade_hud(linha) == _identidade_hud(alvo)
        if cabem or aceso:
            texto = _opcoes._texto_medida(_valor_hud(linha)).rsplit(' ', 1)[0]
            blf.size(0, tamanho)
            meio = (a + b) / 2.0
            rotulos.append([texto, meio + Vector((
                blf.dimensions(0, texto)[0] / 2.0 + 6 * escala, 0.0)), aceso])
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
    parede = _paredes_edicao.ativa(context)
    if not _contexto_hud(context) or (parede and not _hud_na_parede()):
        return
    if not parede:
        if _prateleiras._referencia_pendente[0]:
            _assistente._desenhar_assistente_2d(_prateleiras._referencia_pendente[0])
        # porta selecionada nao tem HUD de medida, mas tem os 4 cantos e o
        # slider de abertura de cada folha; ferragens selecionadas, o realce
        _ferragens._desenhar_ferragens_selecionadas(context)
        _puxadores._desenhar_ancoras_puxador(context)
        _portas_viewport._desenhar_cantos_porta(context)
        _portas_viewport._desenhar_sliders_porta(context)
        _paredes.desenhar_guias(context)     # modulo associado a uma parede
        _gavetas.desenhar(context)           # sliders e, com Alt, os 3 pontos
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
    if digitando and not parede:
        edicao['caixas'] = []   # na parede a caixa e' o numero da cota verde
    try:
        for geometria, alvo in desenhos:
            _desenhar_controles_volume(context, geometria, alvo)
            for letra, ponto, aceso in ([] if parede else _rotulos_hud(context, geometria, alvo)):
                blf.size(0, tamanho)
                # o ponto e' o CENTRO da letra (ja' fora da peca)
                largura_letra, altura_letra = blf.dimensions(0, letra)
                x, y = ponto.x - largura_letra / 2, ponto.y - altura_letra / 2
                blf.position(0, x, y, 0)
                # pela letra do ALVO: o rotulo vem numerado ('A1'), fora
                # da tabela de eixos, e saia laranja ao lado da linha colorida
                blf.color(0, *(_cor_realce_hud(_letra_do_alvo(alvo)) if aceso else cor))
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
                        edicao['texto'], edicao.get('cursor', len(edicao['texto'])),
                        medida=not edicao.get('subdivisao_vao') and not _eh_angulo(edicao['alvo'])) +
                        (' prateleiras no vao' if edicao.get('subdivisao_vao') else ''),
                        tamanho, escala, edicao=edicao,
                        medida=not edicao.get('subdivisao_vao') and not _eh_angulo(edicao['alvo']))
            if alvo and alvo.get('lado') and not parede:
                _desenhar_seta_hud(context, alvo, geometria)
            if nesta and edicao.get('nativo') and alvo and not parede:
                ponto = _projetar_hud(context, alvo['pontos'][1])
                if ponto is not None:
                    texto = '%s: %s' % (alvo.get('rotulo', alvo.get('letra', '')),
                        _opcoes._texto_medida(_valor_hud(alvo, context)))
                    if (_hud_volume._estado[0] or {}).get('erro'):
                        texto += ' (limite)'
                    _caixa_texto_hud(ponto.x + 12 * escala, ponto.y + 12 * escala,
                                      texto, tamanho, escala)
        if not parede:
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
    finally:
        gpu.state.line_width_set(1)
        gpu.state.point_size_set(1)
        gpu.state.blend_set('NONE')


def _desenhar_controles_volume(context, geometria, alvo):
    escala = context.preferences.system.ui_scale
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(1.0)
    for controle in _hud_volume.controles(geometria):
        ponto = _projetar_hud(context, controle['pontos'][1])
        if ponto is None:
            continue
        aceso = (alvo and alvo.get('controle_face')
                  and _identidade_hud(alvo) == _identidade_hud(controle)
                  and alvo['lado'] == controle['lado'])
        cor = _cor_realce_hud() if aceso else _cor_linhas_hud(context)
        if _paredes_edicao.ativa(context):
            # Na parede ela e' o unico controle (pedido do usuario: mais
            # visivel): disco cheio sobre halo do tema, maior aceso.
            raio = (RAIO_PONTO_PAREDE_PX + (2 if aceso else 0)) * escala
            halo = _paredes_composicao.estilo_cotas(context)['halo']
            shader.bind()
            for r, c in ((raio + 2 * escala, halo), (raio, cor)):
                shader.uniform_float('color', (*c[:3], 1.0))
                batch_for_shader(shader, 'TRIS', {'pos': _disco_2d(ponto, r)}).draw(shader)
            continue
        raio = (3 if aceso else 2) * escala
        circulo = [(ponto.x + raio * math.cos(i*math.tau/24),
                    ponto.y + raio * math.sin(i*math.tau/24)) for i in range(25)]
        shader.bind()
        shader.uniform_float('color', cor)
        batch_for_shader(shader, 'LINE_STRIP', {'pos': circulo}).draw(shader)


def _disco_2d(centro, raio, passos=24):
    """Triangulos de um disco cheio em pixels."""
    volta = [centro + Vector((math.cos(i * math.tau / passos),
                              math.sin(i * math.tau / passos))) * raio
             for i in range(passos + 1)]
    return [p for a, b in zip(volta, volta[1:]) for p in (centro, a, b)]


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


def _caixa_texto_hud(x, y, texto, tamanho, escala, edicao=None, medida=True):
    """Texto branco numa caixa preta: legivel contra qualquer fundo."""
    blf.size(0, tamanho)
    largura = blf.dimensions(0, texto)[0]
    altura = blf.dimensions(0, '0')[1]
    folga = 4 * escala
    x0, y0 = x - folga, y - folga
    x1, y1 = x + largura + folga, y + altura + folga
    gpu.state.blend_set('ALPHA')
    _gaveta._retangulo_arredondado_gaveta(x0,y0,x1-x0,y1-y0,4*escala,(0.0,0.0,0.0,.88))
    if edicao is not None:
        _gaveta_desenho._realcar_selecao_texto(x, y, edicao, tamanho, medida=medida)
    blf.position(0, x, y, 0)
    blf.color(0, 1.0, 1.0, 1.0, 1.0)
    blf.draw(0, texto)


def _desenhar_seta_hud(context, alvo, geometria):
    """Seta guia: sai da quina que fica parada e aponta para onde o
    movel vai crescer (estilo Promob). Desenhada em pixels, entao tem o
    mesmo tamanho de qualquer distancia.

    As pontas saem da aresta da geometria ATUAL, nao dos
    pontos guardados no hover: estes ficam para tras quando o movel
    muda de tamanho ou de lugar.
    """
    if not _opcoes._opcao('hud_setas_quinas'):
        return
    if (not alvo.get('cantos') and not alvo.get('seta_real')) or alvo['objeto'] != geometria['objeto']:
        return
    linha=next((l for l in geometria['linhas'] if
                _identidade_hud(l)==_identidade_hud(alvo)
                and (alvo.get('face',('',))[0]!='BLOCO' or l.get('face')==alvo.get('face'))
                and (alvo.get('seta_real') or l.get('cantos')==alvo.get('cantos'))),None)
    if linha is None:return
    fixa,livre=linha['pontos'] if alvo['lado']=='min' else linha['pontos'][::-1]
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
                or (alvo or {}).get('face') != (antes or {}).get('face')
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
    bl_options = {'PERSISTENT', 'SCALE', 'SHOW_MODAL_ALL'}

    @classmethod
    def poll(cls, context):
        criacao = _solda._conexao_manual[0]
        if criacao and criacao.get('moderna'):
            return (context.mode == 'OBJECT' and context.region is not None
                    and context.region.as_pointer() == criacao['regiao']
                    and not _gaveta._eh_area_gaveta(context))
        return (_contexto_hud(context) and not _gaveta._eh_area_gaveta(context)
                and _alvo_hud(context) is not None and not _portas._apanhando_vao[0]
                and _edicao_hud[0] is None)

    def setup(self, context):
        self.botoes = []

    def draw_prepare(self, context):
        # dois botoes por quina: corrente (desagrega) e regua (resetar)
        correntes=_solda._correntes_hud(context)
        criando=bool(correntes and correntes[0].get('criacao'))
        if not hasattr(self,'botoes_criacao'):
            self.botoes_criacao=[];self.operadores_criacao=[]
        for botao in self.botoes+self.botoes_criacao:botao.hide=True
        pool=self.botoes_criacao if criando else self.botoes
        botoes = [(corrente, tipo, centro)
                  for corrente in correntes
                  for tipo, centro in _solda._botoes_da_corrente(context, corrente).items()]
        if not hasattr(self, 'operadores'):
            self.operadores = []
        while len(pool) < len(botoes):
            botao = self.gizmos.new('GIZMO_GT_button_2d')
            botao.draw_options = {'BACKDROP', 'OUTLINE'}
            botao.use_tooltip = True
            pool.append(botao)
        # Os slots alternam corrente/regua; religar no redraw invalida o tooltip nativo.
        operadores=self.operadores_criacao if criando else self.operadores
        while len(operadores) < len(pool):
            i = len(operadores)
            nome = ('object.cabinet_acao_criacao_solda' if criando else
                    'object.cabinet_desassociar' if i % 2 == 0 else _solda.OP_RESETAR_DISTANCIA)
            operadores.append(pool[i].target_set_operator(nome))
        realce = _cor_realce_hud()
        for botao in self.botoes:
            botao.hide = True
        for botao, op, (corrente, tipo, centro) in zip(pool, operadores, botoes):
            botao.hide = False
            botao.icon = 'LINKED' if tipo == 'corrente' else 'DRIVER_DISTANCE'
            botao.scale_basis = _solda.RAIO_CORRENTE_PX
            botao.color = realce[:3]
            botao.alpha = 0.85
            botao.color_highlight = realce[:3]
            botao.alpha_highlight = 1.0
            botao.matrix_basis[0][3] = centro.x
            botao.matrix_basis[1][3] = centro.y
            if criando:op.acao=('%s|%d'%('REMOVER' if tipo=='corrente' else 'RESETAR',corrente['indice']))
            else:op.chapa = corrente['movel'].name
        if not hasattr(self,'campos_distancia'):self.campos_distancia=[]
        campos=[(c,caixa) for c in correntes if (caixa:=_solda._campo_distancia_corrente(context,c))]
        while len(self.campos_distancia)<len(campos):
            campo=self.gizmos.new('VIEW3D_GT_campo_gaveta')
            campo.use_tooltip=False
            op=campo.target_set_operator('object.cabinet_editar_medida_gaveta')
            op.dono='solda'
            self.campos_distancia.append((campo,op))
        for campo,_op in self.campos_distancia:
            campo.hide=True;_campos_gaveta.pop(campo.as_pointer(),None)
        for (campo,op),(c,caixa) in zip(self.campos_distancia,campos):
            x,y,w,h,_texto,valor=caixa
            campo.hide=False
            _campos_gaveta[campo.as_pointer()]=(x-4,y-4,w+8,h+8,None)
            op.dono='solda_criacao' if c.get('criacao') else 'solda'
            op.objeto=c['a'].name
            op.propriedade=str(c['indice']) if c.get('criacao') else '%s|%d'%(c['ponta'],c['indice'])
            op.valor=valor


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
    if alvo['tipo']=='aresta':
        secao=alvo['objeto'].data.get(_chapas.CHAVE_ESPESSURA,{})
        real=secao.get('arestas',{}).get(str(alvo['face'][0]))
        if real:
            matriz=alvo['objeto'].matrix_world
            return ((matriz@Vector(real['pontos'][1]))-(matriz@Vector(real['pontos'][0]))).length*1000
        borda=secao.get('bordas',{}).get(str(alvo['face'][0]))
        if not borda:raise ValueError('A aresta nao existe mais')
        matriz=alvo['objeto'].matrix_world
        return ((matriz@Vector(borda[2]))-(matriz@Vector(borda[0]))).length*1000
    if alvo['tipo']=='deslocamento':
        return float(alvo['objeto'].data.get(_chapas.CHAVE_ESPESSURA,{}).get('deslocamento_mm',0))
    if _eh_angulo(alvo):
        return _angulo_da_ponta(alvo)
    if alvo['tipo'] == 'forma':
        return _formas.valor(alvo['objeto'], alvo['face'],alvo.get('plano','XY'))
    dono = _sistema_hud(alvo['tipo'])
    if dono is not None:
        return dono.valor(alvo['objeto'], alvo['face'])
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
    if alvo['tipo']=='aresta':
        _chapas.definir_aresta(obj,alvo['face'][0],valor,alvo.get('lado','min'))
        return
    if alvo['tipo']=='angulo_aresta':
        _chapas.definir_angulo_arestas(obj,alvo['face'],valor)
        return
    if alvo['tipo']=='deslocamento':
        _chapas.definir_deslocamento(obj,valor,alvo.get('lado','min'))
        return
    if alvo['tipo']=='forma' and (obj.type!='MESH' or alvo.get('modo')!='INDIVIDUAL'):
        raise ValueError('Selecione uma chapa individual para editar seu formato')
    if _eh_angulo(alvo):
        _formas.aplicar_angulo_interno(context, obj, alvo['face'][1],
                                      alvo['face'][2], valor,alvo.get('plano','XY'))
        return
    if alvo['tipo'] == 'forma':
        _formas.aplicar(context, obj, alvo['face'], valor, alvo.get('lado'),plano=alvo.get('plano','XY'))
        return
    dono = _sistema_hud(alvo['tipo'])
    if dono is not None:
        extras = {'previa':True} if alvo['tipo']=='gavetas' and (_edicao_hud[0] or {}).get('previa_gavetas') else {}
        erro = dono.aplicar(context, obj, alvo['face'], valor, alvo.get('lado'),**extras)
        if erro:
            raise ValueError(erro)
        return
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
            _modulos.atualizar_sistemas_do_conjunto(pai)
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
    dono = _sistema_hud(alvo['tipo'])
    if dono is not None:
        return alvo['tipo'].upper(), dono.copia(obj)
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
        porta = ({p: _portas._copiar_parametros(o[p]) for p in
                  ('porta_parametros', 'porta_vao_largura_mm', 'porta_vao_altura_mm')}
                 if _chapas.MARCA_PORTAS in o and 'porta_parametros' in o else {})
        if _chapas.MARCA_PORTAS in o:
            porta.update({p:_portas._copiar_parametros(o[p]) for p in o.keys()
                          if p.startswith('porta_vao_')})
        if _gavetas.MARCA_GRUPO in o:
            for chave in (_gavetas.CHAVE_MARGENS, _gavetas.CHAVE_VAO,
                          _gavetas.CHAVE_PARAMETROS, _gavetas.CHAVE_TRILHO_MM,
                          _gavetas.CHAVE_ENCAIXE, _gavetas.CHAVE_REFERENCIA):
                porta[chave] = (_portas._copiar_parametros(o[chave]) if chave in o else None)
        if _prateleiras.MARCA_GRUPO in o:
            for chave in (_prateleiras.CHAVE_MARGENS, _prateleiras.CHAVE_VAO,
                          _prateleiras.CHAVE_PARAMETROS, _prateleiras.CHAVE_ENCAIXE,
                          _prateleiras.CHAVE_REFERENCIA):
                porta[chave] = (_portas._copiar_parametros(o[chave]) if chave in o else None)
        if _gavetas.MARCA_GAVETA in o:
            porta[_gavetas.CHAVE_TRILHO_MM] = float(o.get(_gavetas.CHAVE_TRILHO_MM,0))
        if _chapas.MARCA_FOLHA in o and _ferragens.CHAVE_CENTRO_FOLHA in o:
            porta[_ferragens.CHAVE_CENTRO_FOLHA] = tuple(o[_ferragens.CHAVE_CENTRO_FOLHA])
        vertices =[tuple(v.co) for v in o.data.vertices] if o.type == 'MESH' else None
        estado.append((o, o.matrix_world.copy(), o.matrix_parent_inverse.copy(),
                       props, porta, vertices))
    cena = {p: getattr(context.scene, p) for p in
            ('grupo_largura_mm', 'grupo_altura_mm', 'grupo_profundidade_mm',
             'grupo_espessura_mm') + _portas._PROPS_PORTAS_CENA}
    return estado, cena


def restaurar_cota(context, estado, nome):
    _restaurar_arraste_hud(context,estado)
    _formas.esquecer()
    obj=bpy.data.objects.get(nome)
    if obj is not None and obj.type=='MESH':
        _chapas.preparar_espessura(obj)
        _frentes.preparar(obj,forcar=True)


def _restaurar_arraste_hud(context, estado):
    objetos, cena = estado
    dono = _sistema_hud(objetos)
    if dono is not None:
        dono.restaurar(cena)
        return
    _chapas._ocupado[0] = True
    try:
        for obj, matriz, inversa, props, porta, vertices in objetos:
            for nome, valor in props.items():
                setattr(obj, nome, valor)
            if _chapas.MARCA_PORTAS in obj:
                for nome in list(obj.keys()):
                    if nome.startswith('porta_vao_') and nome not in porta:del obj[nome]
            for nome, valor in porta.items():
                if valor is None:
                    if nome in obj:del obj[nome]
                else:obj[nome] = valor
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


# Mover o modulo pela quina: o cursor 3D e' a quina pega e o translate
# NATIVO o leva (Ctrl liga o snap de vertice do proprio Blender, o gesto
# de antes); um timer so' copia o cursor para o modulo. Antes as quinas
# da cena eram juntadas e projetadas em Python a cada movimento.
_arraste_quina = [None]


def _levar_quina(estado, ponto):
    obj = bpy.data.objects.get(estado['objeto'])
    if obj is None:
        return
    matriz = estado['matriz'].copy()
    matriz.translation += ponto - estado['origem']
    obj.matrix_world = matriz


def _preparar_quina_nativa(context, modulo, origem, matriz):
    """Estado + parametros do translate. A propria peca nao e' alvo do
    snap; puxador e ferragem so' pesariam o BVH."""
    proprios = {modulo.name, *(o.name for o in modulo.children_recursive)}
    _gavetas.iniciar_cursor_nativo(
        context, _arraste_quina,
        {'objeto': modulo.name, 'origem': origem.copy(), 'matriz': matriz.copy()},
        origem, lambda o: (o.name in proprios or _chapas.MARCA_PUXADOR in o
                           or _ferragens.CHAVE_FERRAGEM in o))
    # snap desligado: o Ctrl do translate liga (vertice = quina da chapa)
    return dict(_gavetas.PARAMETROS_CURSOR_NATIVO, snap=False, snap_elements={'VERTEX'})


def _terminar_quina_nativa(remover_timer=True):
    estado = _gavetas.terminar_cursor_nativo(_arraste_quina)
    if remover_timer and bpy.app.timers.is_registered(_acompanhar_quina_nativa):
        bpy.app.timers.unregister(_acompanhar_quina_nativa)
    return estado


def _acompanhar_quina_nativa():
    estado = _arraste_quina[0]
    if _gavetas.acompanhar_cursor_nativo(_arraste_quina, 'OBJECT_OT_cabinet_mover_quina_hud'):
        _levar_quina(estado, estado['ponto'])
        return 1.0 / 60.0
    if estado is not None:
        # Esc/direito no translate: o modulo volta para onde estava
        _levar_quina(estado, estado['origem'])
    return None


def _iniciar_quina_nativa(context, modulo, origem, matriz):
    parametros = _preparar_quina_nativa(context, modulo, origem, matriz)
    try:
        resultado = bpy.ops.object.cabinet_mover_quina_hud(
            'INVOKE_DEFAULT', TRANSFORM_OT_translate=parametros)
    except Exception:
        _terminar_quina_nativa()
        raise
    if 'RUNNING_MODAL' not in resultado:
        _terminar_quina_nativa()
        return False
    bpy.app.timers.register(_acompanhar_quina_nativa, first_interval=0.0)
    return True


class OBJECT_OT_confirmar_quina_hud(Operator):
    bl_idname = 'object.cabinet_confirmar_quina_hud'
    bl_label = 'Confirmar Quina do Modulo'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        if not _arraste_quina[0]:
            return {'CANCELLED'}
        ponto = context.scene.cursor.location.copy()
        estado = _terminar_quina_nativa()
        _levar_quina(estado, ponto)
        context.view_layer.update()
        return {'FINISHED'}


class OBJECT_OT_mover_quina_hud(Macro):
    bl_idname = 'object.cabinet_mover_quina_hud'
    bl_label = 'Mover Modulo pela Quina'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}


def registrar_macro_quina():
    OBJECT_OT_mover_quina_hud.define('TRANSFORM_OT_translate')
    OBJECT_OT_mover_quina_hud.define('OBJECT_OT_cabinet_confirmar_quina_hud')


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
            pass        # o arraste vai ao cursor nativo (`_iniciar_quina_nativa`)
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
            elif alvo.get('direcao') is not None:
                eixo = alvo['direcao']      # diagonal: cresce para dentro
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
            if _eh_angulo(alvo):
                # angulo: graus, de lado na tela (o mm por pixel nao serve)
                self._por_pixel = GRAUS_POR_PIXEL_HUD
                self._direcao = Vector((1.0, 0.0))
        _edicao_hud[0] = {'regiao': context.region.as_pointer(), 'alvo': alvo}
        if alvo['tipo']=='gavetas' and len(alvo['face'])>1:
            _edicao_hud[0]['previa_gavetas']=True
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
        if (_edicao_hud[0] or {}).get('previa_gavetas'):
            _gavetas.montar(self._alvo['objeto'])
        _edicao_hud[0] = None
        self._area.tag_redraw()

    def cancel(self, context):
        if getattr(self, '_subdivisao_vao', None):
            grupo = bpy.data.objects.get(self._subdivisao_vao['grupo'])
            if grupo is not None:
                _prateleiras.cancelar_subdivisao_vao(grupo, self._subdivisao_vao)
        if _edicao_hud[0] is not None:_edicao_hud[0].pop('previa_gavetas',None)
        for backup in reversed(getattr(self, '_backups', [self._backup])):
            _restaurar_arraste_hud(context, backup)
        self._encerrar()

    def _comecar_digitacao(self):
        estado = _edicao_hud[0]
        estado['fase'] = None
        estado['hover'] = None
        estado['texto'] = _opcoes._numero_na_unidade(_valor_hud(estado['itens'][0]))
        estado['cursor'] = len(estado['texto'])
        estado['selecionado'] = False
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
                if getattr(self, '_subdivisao_vao', None):
                    _prateleiras.subdividir_vao(context, self._alvo['objeto'],
                        self._subdivisao_vao, int(estado['texto']))
                    self._encerrar()
                    return {'FINISHED'}
                if _eh_angulo(self._alvo):
                    valor = float(estado['texto'].replace(',', '.').strip(' \u00b0'))
                else:
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
        if _gaveta_desenho._tecla_no_texto(estado, event.type, entrada, event.ctrl, getattr(event, 'shift', False)):
            self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _clique_na_caixa(self, event):
        """True (e o cursor no lugar) se o clique caiu numa caixa de texto
        desenhada -- as posicoes vem do ultimo desenho da HUD."""
        estado = _edicao_hud[0]
        mx, my = event.mouse_region_x, event.mouse_region_y
        texto = estado['texto']
        cursor = estado.get('cursor', len(texto))
        medida = not estado.get('subdivisao_vao') and not _eh_angulo(estado['alvo'])
        for x, y, tamanho, escala in estado.get('caixas') or ():
            largura = _gaveta_desenho._medidor_blf(tamanho)
            blf.size(0, tamanho)
            altura = blf.dimensions(0, '0')[1]
            folga = 4 * escala
            if (x - folga <= mx <= x + largura(_gaveta_desenho._com_cursor(texto, cursor,medida=medida)) + folga
                    and y - folga <= my <= y + altura + folga):
                pos = _gaveta_desenho._cursor_no_x(texto, cursor, x, mx, largura,medida=medida)
                _gaveta_desenho._posicionar_cursor_texto(estado, pos, getattr(event, 'shift', False))
                return True
        return False

    def modal(self, context, event):
        if context.mode != 'OBJECT':
            self.cancel(context)
            return {'CANCELLED'}
        if (event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'} and event.value == 'PRESS'
                and self._alvo['tipo'] == 'prateleiras' and self._alvo.get('face', ('',))[0] == 'V'):
            return self._rolar_prateleiras(context, event)
        if (_edicao_hud[0] or {}).get('fase'):
            return self._multiplo(context, event)
        if (_edicao_hud[0] or {}).get('texto') is not None:
            return self._digitar(context, event)
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cancel(context)
            return {'CANCELLED'}
        mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if (not self._arrastou and (_sistema_hud(self._alvo['tipo']) is not None or self._alvo['tipo'] in ('forma', 'aresta', 'angulo_aresta', 'deslocamento') or (
                    self._alvo['tipo'] == 'medida' and self._alvo.get('lado')))):
                # Clique sem arrastar numa linha do modulo: a seta fica e
                # o valor passa a ser digitado (Enter confirma, Esc volta).
                texto = (('%.1f' % self._valor).rstrip('0').rstrip('.')
                         if _eh_angulo(self._alvo)
                         else _opcoes._numero_na_unidade(self._valor))
                _edicao_hud[0].update(texto=texto, cursor=len(texto),
                                      selecionado=False)
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
            if _hud_volume.elegivel(self._alvo):
                # O modal nativo recebe B/Ctrl/teclado e possui o UNDO.
                # CANCELLED aqui evita um segundo passo sem mudanca.
                _hud_volume.iniciar(context, self._alvo, self._backup)
                return {'CANCELLED'}
            if self._alvo['tipo'] == 'ancora':
                # o translate nativo segue com o arraste e possui o UNDO
                modulo, origem, matriz = self._alvo['objeto'], self._origem, self._matriz
                self._encerrar()
                _iniciar_quina_nativa(context, modulo, origem, matriz)
                return {'CANCELLED'}
            self._arrastou = True
        try:
            delta = (mouse-self._inicio).dot(self._direcao) * self._por_pixel
            _aplicar_valor_hud(context, self._alvo, self._valor + delta)
        except (ValueError, TypeError, ReferenceError) as erro:
            self.report({'WARNING'}, str(erro))
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _rolar_prateleiras(self, context, event):
        try:
            estado = getattr(self, '_subdivisao_vao', None) or _prateleiras.preparar_subdivisao_vao(
                self._alvo['objeto'], self._alvo['face'][1])
            n = max(0, estado['quantidade'] + (1 if event.type == 'WHEELUPMOUSE' else -1))
            _prateleiras.subdividir_vao(context, self._alvo['objeto'], estado, n)
            self._subdivisao_vao = estado
            _edicao_hud[0].update(texto=str(n), cursor=len(str(n)), selecionado=False,
                                  subdivisao_vao=True, desfazer=[], refazer=[])
            _edicao_hud[0].pop('ancora', None)
            self._arrastou = True
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
