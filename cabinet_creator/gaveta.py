"""Gaveta (UI desenhada por GPU): a area (abrir, reconectar, limitar a
largura), os primitivos de desenho, o layout dos widgets de cada aba --
a lista que o desenho e o hit-test leem -- e a animacao dos realces."""

import bpy, colorsys, math, os, gpu, blf, time
from gpu_extras.batch import batch_for_shader
from bpy.props import StringProperty
from mathutils import Matrix, Vector
from bpy.types import Operator

# usados ao CARREGAR (corpo de classe, constantes): ja' carregados antes
from . import opcoes as _opcoes
# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = None
_modulos = None
_biblioteca = None
_materiais = None
_portas = None
_ferragens = None
_gaveta_eventos = None
_importacao = None
_puxadores = None
_orcamento = None
_hud = None
_solda = None
_perguntas = None
_gaveta_desenho = None
_gavetas = None
_prateleiras = None
_formas = None

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
        if self.modo == 'INDIVIDUAL' and _chapas.MARCA_CONJUNTO in obj:
            chapas = _modulos._chapas_do_conjunto(obj)
            if not chapas:
                self.report({'WARNING'}, "Modulo sem chapas")
                return {'CANCELLED'}
            alvo = chapas[0]
            for selecionado in context.selected_objects:
                selecionado.select_set(False)
            alvo.select_set(True)
            context.view_layer.objects.active = alvo
            alvo.chapa_modo = 'INDIVIDUAL'
        elif _chapas.MARCA_CHAPA in obj:
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
# POST_PIXEL (`_gaveta_desenho._desenhar_gaveta`) e os eventos
# (`_gaveta_eventos.OBJECT_OT_interagir_gaveta`) nao passam pelo handler
# de UILayout; portanto a barra recebe PRESS/MOUSEMOVE/RELEASE de verdade.
_handler_gaveta = [None]
_biblioteca_faixa = None
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
            and (context.area == _area_gaveta(context.screen)
                 or _biblioteca_faixa.eh_faixa(context)))


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
        _biblioteca_faixa.reconectar(screen)
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
        _biblioteca_faixa.reconectar(screen)
        painel = _area_gaveta(screen)
        if painel is not None and screen.get(_biblioteca_faixa.CHAVE_LAYOUT) != 2:
            principal = _biblioteca_faixa.viewport(screen)
            if principal is not None:
                with bpy.context.temp_override(window=janela, area=principal):
                    _biblioteca_faixa.abrir(bpy.context)
            continue
        if not screen.get(_CHAVE_GAVETA) or painel:
            continue
        candidatos = [a for a in screen.areas
                      if a.type == 'VIEW_3D' and a.width < 600
                      and not a.spaces.active.show_region_header
                      and not a.spaces.active.show_region_toolbar
                      and not a.spaces.active.overlay.show_overlays]
        if len(candidatos) == 1:
            screen[_CHAVE_GAVETA] = str(candidatos[0].as_pointer())
            candidatos[0].tag_redraw()
            if screen.get(_biblioteca_faixa.CHAVE_LAYOUT) != 2:
                principal = _biblioteca_faixa.viewport(screen)
                if principal is not None:
                    with bpy.context.temp_override(window=janela, area=principal):
                        _biblioteca_faixa.abrir(bpy.context)
        else:
            screen[_CHAVE_GAVETA] = 0
    return None


def _fechar_gavetas_registradas():
    for janela in bpy.context.window_manager.windows:
        screen = janela.screen
        if _biblioteca_faixa.area_da_faixa(screen) is not None:
            _biblioteca_faixa.fechar(janela, screen)
            continue
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
    grupo = _portas._grupo_portas(obj)
    if grupo is not None:
        return [grupo]
    if obj is not None and _chapas.MARCA_CONJUNTO in obj:
        vinculados = _portas._portas_do_conjunto(obj)
        if vinculados:
            return vinculados
    modulo = _portas._modulo_da_chapa(obj)
    if modulo is not None:
        vinculados = _portas._portas_do_conjunto(modulo)
        if vinculados:
            return vinculados
    achados = []
    for selecionado in getattr(bpy.context, 'selected_objects', ()):
        alvo = _portas._grupo_portas(selecionado)
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
    minimo = max(largura, profundidade) * _biblioteca.MINIMO_ESPESSURA_WIREFRAME
    return (largura, max(espessura, minimo), profundidade)


def _folhas_para_wireframe(obj, modo):
    """Quantas folhas o preview deve mostrar.

    No modo INDIVIDUAL o desenho e' de UMA chapa; porta ali nao existe
    e as folhas apareciam dentro da peca, que e' o que quebrava a
    visualizacao.
    """
    if modo == 'INDIVIDUAL':
        return 0
    return sum(len(_portas._folhas_portas(g)) for g in _grupos_de_porta(obj))


def _frente_da_porta(obj):
    """Em que face do modulo a porta foi montada ('' se nao ha' porta)."""
    for grupo in _grupos_de_porta(obj):
        frente = grupo.get('porta_frente')
        folhas = _portas._folhas_portas(grupo)
        modulo = _portas._modulo_da_chapa(folhas[0]) if folhas else None
        if modulo is not None and grupo.get('porta_parametros'):
            # Arquivos antigos podem guardar a normal invertida. A face
            # do desenho segue a posicao real, sem alterar essas portas.
            base = modulo.matrix_world.to_quaternion().to_matrix().transposed()
            normal = base @ grupo.matrix_world.to_3x3().col[2]
            eixo = max(range(3), key=lambda i: abs(normal[i]))
            posicao = _portas._local_no_modulo(modulo, grupo.matrix_world.translation)
            limites = _portas._limites_locais_modulo(modulo)
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
        folhas = _portas._folhas_portas(grupo)
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
    folhas = [f for g in grupos for f in _portas._folhas_portas(g)]
    modulo = obj if _chapas.MARCA_CONJUNTO in obj else _portas._modulo_da_chapa(obj)
    grupo = _portas._grupo_portas(obj)
    if modulo is None and grupo is not None:
        modulo = bpy.data.objects.get(grupo.get(_portas.CHAVE_MODULO_PORTA, ''))
    corpo = _modulos._chapas_do_conjunto(modulo) if modulo is not None else []
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
    normal = referencia @ Vector(_portas.NORMAIS_FRENTE[frente])
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
    espessura e' da porta inteira -- folhas de uma porta sao iguais. A
    largura da folha de CORRER e' parametro da porta: essa se edita.
    """
    folhas = _portas._folhas_portas(grupo)
    if _chapas.MARCA_FOLHA in obj:
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
        else _portas.ESPESSURA_PADRAO_PORTA))
    if grupo['porta_parametros'].get('abertura') == 'CORRER' and folhas:
        # correr: a largura e' a da FOLHA (todas iguais) e se edita
        # (pedido do usuario); o conjunto mudaria ao correr
        nome = 'Largura' if _chapas.MARCA_FOLHA in obj or len(folhas) == 1             else 'Largura da folha'
        return [(nome, folhas[0].chapa_largura_mm, 'ui_porta_largura_folha'),
                ('Altura', folhas[0].chapa_comprimento_mm, ''),
                ('Espessura', espessura, 'ui_porta_espessura')]
    return [('Largura', largura, ''), ('Altura', altura, ''),
            ('Espessura', espessura, 'ui_porta_espessura')]


def _medidas_gaveta(context):
    obj = context.object
    if obj is not None and _chapas.MARCA_CONJUNTO in obj:
        campos = [('Largura', obj.conj_largura_mm, 'ui_conj_largura'),
                  ('Altura', obj.conj_altura_mm, 'ui_conj_altura'),
                  ('Profundidade', obj.conj_profundidade_mm,
                   'ui_conj_profundidade'),
                  ('Espessura', obj.conj_espessura_mm,
                   'ui_conj_espessura')]
        return 'GRUPO', campos, 'objeto'
    grupo = _portas._grupo_portas(obj)
    if grupo is not None and grupo.get('porta_parametros'):
        return 'PORTA', _medidas_da_porta(obj, grupo), 'porta'
    if _puxadores._eh_puxador_parametrico(obj):
        return 'PUXADOR', _puxadores._medidas_puxador_parametrico(obj), 'puxador'
    if obj is not None and _chapas.MARCA_PUXADOR in obj:
        # (nome, valor, prop) como os outros; a trava vai no 4o campo
        return 'PUXADOR', [(n, v, p, t) for n, v, p, t, _k
                           in _importacao._medidas_do_puxador(obj)], 'puxador'
    if obj is not None and _chapas.MARCA_CHAPA in obj:
        if _modo_chapa(context, obj) == 'GRUPO':
            s = context.scene
            campos = [('Largura', s.grupo_largura_mm, 'ui_grupo_largura'),
                      ('Altura', s.grupo_altura_mm, 'ui_grupo_altura'),
                      ('Profundidade', s.grupo_profundidade_mm,
                       'ui_grupo_profundidade'),
                      ('Espessura', s.grupo_espessura_mm,
                       'ui_grupo_espessura')]
            return 'GRUPO', campos, 'cena'
        cotas=_hud.campos_cotas(obj,'INDIVIDUAL',[obj])
        if any(nome not in ('A1','A2','E') for nome,_v,_p in cotas):
            return 'INDIVIDUAL',cotas,'cota'
        campos = [('Largura', obj.chapa_largura_mm, 'ui_chapa_largura'),
                  ('Altura', obj.chapa_comprimento_mm,
                   'ui_chapa_comprimento'),
                  ('Espessura', obj.chapa_espessura_mm,
                   'ui_chapa_espessura')]
        return 'INDIVIDUAL', campos, 'objeto'
    medido = _modulos.medir_selecao(context)
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
                         indice=None, pai=None, prefixo='cabinet_carrossel'):
    """`prefixo`: cada biblioteca (presets, materiais) rola a sua. Sem a
    quantidade de itens no botao (pedido do usuario: ocupava espaco)."""
    if not valores:
        return y
    chave = '%s_%d_%s' % (prefixo, nivel, str(pai))
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
        itens.append((x + 24 + (posicao - primeiro - sobra) * (bw + 4), y,
                      bw, 25, _abreviar(valor, 16),
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


# Carrossel de RETRATOS (pedido do usuario): no lugar dos nomes (Perfil,
# Alca, Borda; Giro, Basculante, Correr) a foto de cada opcao, como na
# biblioteca. Cada retrato e' uma 'escolha' comum -- o clique segue o
# mesmo caminho -- com a foto no 7o campo. Nao cabendo todos, setas nas
# pontas rolam de um em um (como a cascata da biblioteca).
LARGURA_RETRATO_MIN = 40        # limites do slider dos retratos
LARGURA_RETRATO_MAX = 128
ALTURA_ROTULO_RETRATO = 18
LARGURA_SLIDER_RETRATO = 72     # o slider pequeno ao lado do titulo


def _lado_retrato(w):
    """Lado de TODO retrato (puxador, abertura, dobradica): o mesmo
    quadrado em toda a gaveta (pedido do usuario), no tamanho do slider.
    So' encolhe quando tres nao cabem lado a lado -- as tres aberturas
    nunca viram carrossel de um so'."""
    lado = getattr(bpy.context.scene, 'cabinet_tam_retrato', 64)
    return max(1.0, min(float(lado), (w - 8) / 3))


def _titulo_com_slider(itens, x, y, w, rotulo, altura=20):
    """O titulo de uma fila de retratos e, na ponta direita dele, o
    slider que aumenta ou diminui TODOS os retratos. `altura` 23 = o
    titulo de categoria da aba da porta (`_titulo_secao`)."""
    # o slider na SUA caixa, da altura do titulo (auditoria visual: solto,
    # ele boiava ao lado de uma caixa encurtada); widget nenhum se sobrepoe
    lado = min(LARGURA_SLIDER_RETRATO, w / 2)
    itens.append((x, y, w - lado - 6, altura, rotulo, None))
    itens.append((x + w - lado, y, lado, altura, '', ('slider', 'retratos')))


def _carrossel_gaveta(itens, x, y, w, rotulo, prop, opcoes, atual,
                      ativo=True, alvo='', chave=''):
    """`opcoes` = (valor, texto, foto); foto = dict de `_desenhar_foto_gaveta`.
    Mesmo contrato de `_linha_escolha_gaveta`: `y` e' o do rotulo e volta
    o y da linha seguinte."""
    if rotulo:
        _titulo_com_slider(itens, x, y, w, rotulo)
        y -= 26
    n = len(opcoes)
    if not n:
        return y
    bw = _lado_retrato(w)
    cabe = n * bw + 4 * (n - 1) <= w + 0.01     # (w - 8) / 3 x 3 nao erra
    if cabe:
        colunas, inicio, x0 = n, 0, x
    else:
        bw = min(bw, w - 48)
        colunas = max(1, int((w - 48 + 4) // (bw + 4)))
        chave = chave or 'cabinet_carrossel_%s' % prop
        limite = n - colunas
        inicio = max(0, min(limite, int(bpy.context.screen.get(chave, 0))))
        x0 = x + 24
    altura = bw + ALTURA_ROTULO_RETRATO
    # o topo fica onde estaria o de uma fila de segmentos (25 px)
    base = y + 25 - altura
    if not cabe:
        for lado, dx in ((-1, x), (1, x + w - 20)):
            itens.append((dx, base, 20, altura, '',
                          ('rolar_nivel', chave, lado, limite)))
    for i, (valor, texto, foto) in enumerate(opcoes[inicio:inicio + colunas]):
        itens.append((x0 + i * (bw + 4), base, bw, altura, texto,
                      ('escolha', prop, valor, valor == atual, ativo, alvo,
                       foto)))
    return base - 29        # como depois de uma fila que terminasse em `base`


def _colunas_medidas(context, largura, n):
    """Colunas dos campos de medida pela largura LOGICA da gaveta:
    todos numa linha (>= 480), dois (>= 240) ou um. Vale para o bloco
    fixo e para as medidas da porta, que assim ficam alinhados."""
    logica = largura / max(1.0, context.preferences.system.ui_scale)
    return max(1, n if logica >= LARGURA_MEDIDAS_EM_LINHA
               else 2 if logica >= 240 else 1)


def _bloco_medidas_gaveta(context, itens, x, y, w, largura, metade,
                          modos=True, medidas=None):
    """Os campos de medida do item. So' a aba DONA do item os mostra
    (pedido do usuario: o menu mostra o que vale para o que esta'
    selecionado; o modulo nao aparece na aba Portas). `medidas` =
    (modo, campos, dono) prontos, como na porta que o wizard desenha.
    Nao ha' botao de sincronizar: o handler rele as medidas sozinho
    (`_modulos._sincronizar_medidas_ativas`).
    """
    obj = context.object
    y += 23
    modo, campos, dono = medidas or _medidas_gaveta(context)
    # Na aba Portas edita-se o conjunto das folhas, nunca uma peca
    # isolada: alternar Individual/Grupo ali nao significa nada.
    if (modos and obj is not None and modo != 'PORTA'
            and (_chapas.MARCA_CHAPA in obj or _chapas.MARCA_CONJUNTO in obj)):
        for i, nome in enumerate(('Individual', 'Grupo')):
            itens.append((x + i * (metade + 6), y, metade, 25, nome,
                          ('modo', nome.upper(), modo == nome.upper())))
        y -= 33
    if campos:
        # Campos tem 37 px de altura; afastar das abas de modo acima.
        y -= 8
        colunas = _colunas_medidas(context, largura, len(campos))
        if dono=='cota':colunas=min(3,colunas)
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
                          '%s: %s' % (_hud.rotulo_medida(nome), _opcoes._texto_medida(valor)),
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


def _modelos_puxador_gaveta():
    """Retratos do carrossel: os de fabrica (protegidos) e os do usuario,
    que moram na categoria Puxadores da biblioteca."""
    opcoes = [(t, _puxadores.MODELOS_PUXADOR[t][0],
               _biblioteca.foto_padrao('puxador_' + t))
              for t in _puxadores.MODELOS_PADRAO]
    for it in _puxadores.modelos_do_usuario():
        opcoes.append((_puxadores.valor_do_modelo('MODELO', it['arquivo']),
                       _abreviar(it.get('nome', ''), 14), it))
    return tuple(opcoes)


def _aba_puxadores_gaveta(context, itens, x, y, w, s, largura, metade):
    """Como as outras abas (pedido do usuario): nada selecionado = so' o
    "Criar Puxador" (no topo, fora daqui). Criando, aparece o MODELO num
    carrossel de retratos (clicavel: o posicionador troca na hora).
    Puxador selecionado: as medidas dele (e os cadeados do importado) e,
    no do add-on, o carrossel -- trocar refaz AQUELE puxador. Objeto de
    fora: "Usar como puxador" (vira modelo na biblioteca). Como na aba
    Portas, o nome do item nao aparece."""
    usando = _puxadores._usando_como_puxador[0]
    if usando is not None:
        itens.append((x, y + 26, w, 26,
                      'Clique na face do puxador que encosta na porta', None))
        return itens
    posicionando = _puxadores._posicionador_puxador[0]
    if posicionando is not None:
        _carrossel_gaveta(itens, x, y + 26, w, 'Modelo do puxador',
                          'cabinet_puxador_modelo', _modelos_puxador_gaveta(),
                          _puxadores.valor_do_modelo(
                              posicionando['tipo'], posicionando.get('arquivo', '')),
                          alvo=_portas.ALVO_ASSISTENTE)
        return itens
    obj = _selecionado(context)
    if obj is not None and _chapas.MARCA_PUXADOR in obj:
        y = _bloco_medidas_gaveta(context, itens, x, y, w, largura, metade,
                                  modos=False)
        itens.append((x, y + 31, w, 1, '', ('separador',)))
        if _puxadores._eh_puxador_parametrico(obj):
            _carrossel_gaveta(itens, x, y, w, 'Modelo do puxador',
                              'cabinet_puxador_modelo', _modelos_puxador_gaveta(),
                              _puxadores.valor_do_modelo(
                                  obj['puxador_tipo'], obj.get('puxador_modelo', '')),
                              alvo=ALVO_PUXADOR)
        else:
            ligado = obj.parent is not None and _chapas.MARCA_CHAPA in obj.parent
            itens.append((x, y, w, 26, 'Ligado a uma porta' if ligado
                          else 'Solto: ligue a uma porta', None))
        return itens
    if obj is not None and obj.type == 'MESH' and not any(
            m in obj for m in (_chapas.MARCA_CHAPA, _chapas.MARCA_CONJUNTO, _chapas.MARCA_PORTAS,
                               _chapas.MARCA_FOLHA, _chapas.MARCA_ACESSORIO, _ferragens.CHAVE_FERRAGEM)):
        _botoes_gaveta(itens, x, y + 26, w, (
            ('Usar como puxador', 'object.cabinet_usar_como_puxador'),))
    return itens


def _valores_portas(s, grupo=None):
    """O que a aba MOSTRA: os parametros da porta selecionada, ou os da
    cena quando nao ha' porta (a proxima a ser criada).

    Ler direto do grupo, em vez de copiar para a cena, e' o que impede
    a aba de exibir os valores da ULTIMA porta como se fossem desta.
    """
    valores = _portas._parametros_portas_da_cena(s, numerico=True)
    guardados = (grupo.get('porta_parametros') or {}) if grupo else {}
    for nome, valor in guardados.items():
        if nome not in valores:
            continue
        if nome in {'abertura', 'dobradica', 'dobradica_lado', 'trilho', 'folha'}:
            valores[nome] = str(valor)
        elif nome in {'folhas', 'dobradicas_qtd', 'pistoes_qtd'}:
            valores[nome] = int(valor)
        else:
            valores[nome] = float(valor)
    return valores


ETAPAS_FERRAGENS_ASSISTENTE = ('EIXO', 'QUANTIDADE', 'MARGEM',
                               'PISTOES_QTD', 'PISTOES_OFFSET')
# alvo da 'escolha' (e dono da 'medida') que edita as ferragens
# SELECIONADAS: vale para todas as portas do modulo delas
ALVO_FERRAGENS = '@ferragens'
# alvo da 'escolha' do modelo que troca o puxador SELECIONADO
ALVO_PUXADOR = '@puxador'


def _selecionado(context):
    """O objeto ativo, se ele esta' selecionado (ativo sem selecao nao
    conta: a gaveta mostra o que esta' SELECIONADO, pedido do usuario)."""
    obj = getattr(context, 'object', None)
    return obj if obj is not None and obj.select_get() else None


LARGURA_CONFIRMAR = 30           # o quadrado verde do "aceitar"
LARGURA_CAMPO_FOLHAS = 76        # o campo compacto "Folhas" da porta
# coluna do contador ao lado dos retratos; mais estreita, a secao
# empilha (com os retratos de 64 px, era o corte antigo de 260)
LARGURA_MIN_COLUNA_FERRAGENS = 120


def _secao_ferragens_gaveta(itens, x, y, w, dados, alvo, dono,
                            separar=True, abertura=None):
    """Dobradicas e pistoes EDITAVEIS, no layout do usuario (mockup):
    [abertura][dobradica][Dobradicas: < 2 >] numa linha e o afastamento
    embaixo; o "aceitar" da etapa e' o quadrado VERDE a' direita do campo
    que ela edita (`CONFIRMAR_ETAPA`, o mesmo do clique na viewport).
    Quantidade = contador (arrastar ou clicar nas metades), nao mais
    cinco segmentos. Serve ao wizard (alvo do modal, `abertura` = o
    retrato da escolhida) e as ferragens selecionadas (todas as portas
    do modulo). `dados[tipo]`: 'qtd' e 'mm' (None = ainda nao chegou
    la'), 'info', 'modelo' (retrato da dobradica) e 'confirmar' =
    (etapa, 'qtd' ou 'mm'). Devolve o y do rotulo seguinte."""

    def campo_com_aceite(cx, cy, cw, h, widget, parte):
        """O campo e, se a etapa e' dele, o quadrado verde colado."""
        conf = d.get('confirmar')
        if conf and conf[1] == parte:
            cw -= LARGURA_CONFIRMAR + 4
            itens.append((cx + cw + 4, cy, LARGURA_CONFIRMAR, h, '',
                          ('escolha', _portas.CONFIRMAR_ETAPA, conf[0], False,
                           True, alvo)))
        itens.append((cx, cy, cw) + widget)

    for tipo in ('DOBRADICA', 'PISTAO'):
        d = dados.get(tipo)
        if d is None:
            continue
        if separar:
            itens.append((x, y + 30, w, 1, '', ('separador',)))
        separar = True
        if tipo == 'DOBRADICA':
            rotulo, limites = 'Dobradicas', _portas.LIMITES_DOBRADICAS
            prop_qtd, prop_mm = 'dobradicas_qtd', 'dobradicas_margem_mm'
            nome_mm = 'Afastamento das quinas'
        else:
            rotulo, limites = 'Pistoes', _portas.LIMITES_PISTOES
            prop_qtd, prop_mm = 'pistoes_qtd', 'pistoes_offset_mm'
            nome_mm = 'Distancia do topo'
        if d.get('info'):
            rotulo = '%s: %s' % (rotulo, d['info'])
        # retratos: a abertura escolhida (clicar volta a' escolha) e o
        # tipo da dobradica, AUTOMATICO -- para ver, sem clique
        retratos = []
        if tipo == 'DOBRADICA' and abertura is not None:
            valor, texto, foto = abertura
            retratos.append((texto, ('escolha', 'porta_abertura', valor, True,
                                     True, _portas.ALVO_ASSISTENTE, foto)))
            _titulo_com_slider(itens, x, y, w, 'Abertura')
            y -= 26
        modelo = d.get('modelo')
        if tipo == 'DOBRADICA' and modelo in _portas.NOME_DOBRADICA:
            retratos.append((_portas.NOME_DOBRADICA[modelo],
                             ('escolha', 'dobradica', modelo, True, False, '',
                              _biblioteca.foto_padrao('dobradica_' + modelo))))
        topo = y + 20
        # o MESMO quadrado dos outros retratos (`_lado_retrato`)
        lado = _lado_retrato(w)
        altura = lado + ALTURA_ROTULO_RETRATO
        for i, (texto, acao) in enumerate(retratos):
            itens.append((x + i * (lado + 6), topo - altura, lado, altura,
                          texto, acao))
        ao_lado = bool(retratos) and (
            w - len(retratos) * (lado + 6) >= LARGURA_MIN_COLUNA_FERRAGENS)
        if ao_lado:
            cx = x + len(retratos) * (lado + 6)
            topo_coluna, fundo = topo, topo - altura
        else:
            cx = x
            topo_coluna = topo - altura - 6 if retratos else topo
            fundo = topo_coluna
        cw = x + w - cx
        if retratos and abertura is None:
            # sem o titulo "Abertura" (ferragens selecionadas), o slider
            # dos retratos vai na linha do rotulo
            _titulo_com_slider(itens, cx, topo_coluna - 20, cw, rotulo)
        else:
            itens.append((cx, topo_coluna - 20, cw, 20, rotulo, None))
        fundo = min(fundo, topo_coluna - 20)
        if d.get('qtd') is not None:
            cy = topo_coluna - 26 - 30
            campo_com_aceite(cx, cy, cw, 30, (
                30, str(d['qtd']), ('contador', prop_qtd, int(d['qtd']),
                                    limites[0], limites[1], alvo)), 'qtd')
            fundo = min(fundo, cy)
        if d.get('mm') is None:
            y = fundo - 34
            continue
        itens.append((x, fundo - 6, w, 1, '', ('separador',)))
        campo = fundo - 12 - 37
        campo_com_aceite(x, campo, w, 37, (
            37, '%s: %s' % (nome_mm, _opcoes._texto_medida(d['mm'])),
            ('medida', dono, prop_mm, nome_mm, d['mm'])), 'mm')
        y = campo - 42
    return y


def _retratos_abertura(opcoes):
    return tuple((v, t, _biblioteca.foto_padrao('abertura_' + v))
                 for v, t in opcoes)


def _filas_do_assistente(context, itens, x, y, w, largura, metade, a):
    """A aba Portas CRIANDO (pedido do usuario): tudo aparece etapa a
    etapa. Marcada a area, as medidas da porta (so' leitura: saem dos
    cliques); depois a copia da caixa da viewport, clicavel (quem
    responde e' o modal, em `_responder_pela_gaveta` do
    `_assistente.OBJECT_OT_apanhar_vao_portas`; respondida de novo,
    refaz dali); e as ferragens, EDITAVEIS assim que o wizard chega
    nelas (quantidade e afastamento das dobradicas, pistoes)."""
    etapa, escolhas = a.get('etapa'), a.get('escolhas', {})
    medidas = a.get('medidas_porta')
    if medidas:
        largura_mm, altura_mm, espessura = medidas
        y = _bloco_medidas_gaveta(
            context, itens, x, y, w, largura, metade, modos=False,
            medidas=('PORTA', [('Largura', largura_mm, ''),
                               ('Altura', altura_mm, ''),
                               ('Espessura', espessura, '')], 'porta'))
    itens.append((x, y + 31, w, 1, '', ('separador',)))
    filas = []
    if etapa == 'CONFIRMAR':
        filas.append(('As medidas estao corretas?', 'porta_confirmar',
                      _portas.OPCOES_CONFIRMAR, None))
    else:
        filas.append(('Quantas folhas?' if etapa == 'FOLHAS' else 'Folhas',
                      'porta_folhas',
                      tuple((int(k), t) for k, t in _portas.OPCOES_FOLHAS),
                      escolhas.get('folhas')))
    # escolhida, a abertura vira o 1o retrato da linha das dobradicas
    # (mockup do usuario); so' escolhendo aparecem as tres
    if etapa == 'TIPO' or ('abertura' in escolhas
                           and etapa not in ETAPAS_FERRAGENS_ASSISTENTE):
        filas.append(('Escolha a abertura' if etapa == 'TIPO' else 'Abertura',
                      'porta_abertura', a.get('tipos') or _portas.ESCOLHAS_PORTAS[0][2],
                      escolhas.get('abertura')))
    if etapa == 'MOLDURA' or (etapa in {'BASE', 'TRILHO'}
                              and 'tipo_correr' in escolhas):
        # cliques metade-metade num correr: a mesma caixa da viewport
        filas.append(('Porta embutida ou com moldura?', 'porta_tipo_correr',
                      _portas.TIPOS_CORRER, escolhas.get('tipo_correr')))
    if etapa in {'BASE', 'TRILHO'}:
        # com moldura: vai direto no chao (sem rodape) ou tem base?
        sem = escolhas.get('rodape_mm')
        filas.append(('A porta tem base?', 'porta_base', _portas.OPCOES_BASE,
                      None if sem is None else 'SEM' if sem <= 0 else 'COM'))
    if etapa == 'TRILHO':
        filas.append(('Qual trilho?', 'porta_trilho', _portas.OPCOES_TRILHO,
                      escolhas.get('trilho')))
    for i, (rotulo, pergunta, opcoes, atual) in enumerate(filas):
        if i:
            itens.append((x, y + 30, w, 1, '', ('separador',)))
        fila = (_carrossel_gaveta if pergunta == 'porta_abertura'
                else _linha_escolha_gaveta)
        if pergunta == 'porta_abertura':
            opcoes = _retratos_abertura(opcoes)
        y = fila(itens, x, y, w, rotulo, pergunta, opcoes,
                 atual, alvo=_portas.ALVO_ASSISTENTE) - 10
    if etapa not in ETAPAS_FERRAGENS_ASSISTENTE:
        return itens
    feitas = ETAPAS_FERRAGENS_ASSISTENTE[
        :ETAPAS_FERRAGENS_ASSISTENTE.index(etapa) + 1]
    aresta = a.get('aresta')
    if etapa == 'EIXO' or aresta is None:
        # o tipo sai da borda: o da borda sob o mouse (pedido do usuario,
        # "o tipo nao aparece"); a embutida e' Super Curva em qualquer uma
        snap = a.get('snap')
        modelo = 'SUPER_CURVA' if a.get('embutida') else None
        if snap:
            lado = _portas.COBERTURAS_LADOS[_portas.INDICE_LADO[snap[0]['lado']]]
            modelo = _portas._dobradica_da_cobertura(
                float(a.get('coberturas', {}).get(lado, 1.0)), a.get('embutida'))
        dobradicas = {'info': 'clique na borda delas', 'qtd': None,
                      'modelo': modelo}
    else:
        dobradicas = {'info': 'borda %s' % aresta['lado'].lower(),
                      'modelo': escolhas.get('dobradica'),
                      'qtd': a.get('qtd'), 'mm': a.get('margem')}
    # o "aceitar" (verde) fica no campo que a etapa edita
    confirmar = {'QUANTIDADE': ('DOBRADICA', 'qtd'), 'MARGEM': ('DOBRADICA', 'mm'),
                 'PISTOES_QTD': ('PISTAO', 'qtd'), 'PISTOES_OFFSET': ('PISTAO', 'mm')}
    dados = {'DOBRADICA': dobradicas}
    if 'PISTOES_QTD' in feitas and 'pqtd' in a:
        dados['PISTAO'] = {'qtd': a['pqtd'], 'mm': a.get('poffset')}
    if etapa in confirmar:
        tipo, parte = confirmar[etapa]
        dados[tipo]['confirmar'] = (etapa, parte)
    abertura = escolhas.get('abertura')
    retrato = next(((v, t, _biblioteca.foto_padrao('abertura_' + v))
                    for v, t in _portas.ESCOLHAS_PORTAS[0][2] if v == abertura),
                   None)
    _secao_ferragens_gaveta(itens, x, y, w, dados, _portas.ALVO_ASSISTENTE,
                            'assistente', abertura=retrato)
    return itens


def _aba_portas_gaveta(context, itens, x, y, w, s, largura, metade):
    """A aba mostra so' o que vale AGORA (pedido do usuario, para todas
    as abas): nada selecionado = so' o "Criar Portas" (no topo, fora
    daqui); criando = os campos etapa a etapa (`_filas_do_assistente`);
    ferragens selecionadas = so' as delas (quantidade e afastamento);
    porta ou folha selecionada = medidas, folhas, abertura e folgas
    DELA -- nada de dobradica, que e' da selecao das ferragens."""
    grupo = _portas._grupo_portas(_selecionado(context))
    if grupo is not None and not grupo.get('porta_parametros'):
        grupo = None
    assistente = _portas._assistente_porta[0]
    if (grupo is None and assistente is not None
            and assistente.get('etapa') != 'DIAGONAL'):
        return _filas_do_assistente(context, itens, x, y, w, largura, metade,
                                    assistente)
    ferragens = _ferragens._dados_ferragens_selecionadas(context)
    if ferragens:
        _secao_ferragens_gaveta(itens, x, y + 26, w, ferragens,
                                ALVO_FERRAGENS, 'ferragens', separar=False)
        return itens
    if grupo is None:
        return itens
    # Reposicionar (diagonal no vao novo) e frente EM CIMA das medidas,
    # com icone (pedido do usuario). Converter em porta/dupla sairam da
    # aba a pedido do usuario; seguem no F3.
    itens.append((x+w-28, y+26, 28, 28, 'Espelhar porta',
                  ('operador', 'object.cabinet_espelhar_porta')))
    topo = _botoes_gaveta(itens, x, y + 26, w-34, (
        ('Reposicionar no vao', 'object.cabinet_apanhar_vao'),
        ('Definir como frente', 'object.cabinet_definir_frente'))) + 28 - 4
    alvo = grupo.name
    valores = _valores_portas(s, grupo)
    moldura = _portas._correr_sobreposta(dict(grupo['porta_parametros']))

    def campo(prop_ui, rotulo):
        valor = valores[_portas._PARAMETRO_DA_MEDIDA_PORTA[prop_ui]]
        return ('%s: %s' % (rotulo, _opcoes._texto_medida(valor)),
                ('medida', 'porta', prop_ui, rotulo, valor))

    # Auditoria do usuario: a aba em CATEGORIAS com titulo (o mesmo de
    # Montagem/Orcamento), rotulos curtos que nao se cortam e campos
    # alinhados pela mesma regra de colunas. Sem cabecalho "Porta N de M":
    # nada de nome nem medida repetida (pedido do usuario).
    _modo, medidas, dono = _medidas_gaveta(context)
    topo = _titulo_secao(itens, x, topo, w, 'Porta')
    topo = _campos_em_linhas(context, itens, x, topo, w, [
        ('%s: %s' % (nome, _opcoes._texto_medida(valor)),
         ('medida', dono, prop, nome, valor)) for nome, valor, prop in medidas])

    # FOLHAS: campo COMPACTO na ponta da linha do "Entre planos" (pedido do
    # usuario; eram segmentos 1 2 3 4): arrastar de lado muda, clicar digita
    folhas = []
    if valores['folhas'] > 1:
        folhas.append(campo('ui_porta_entre_planos', 'Entre planos')
                      if valores['abertura'] == 'CORRER'
                      else campo('ui_porta_entre_folhas', 'Entre folhas'))
    topo = _titulo_secao(itens, x, topo - ESPACO_SECOES, w, 'Folhas')
    topo = _campos_em_linhas(
        context, itens, x, topo, w, folhas,
        compacto=(str(valores['folhas']),
                  ('contador', 'porta_folhas', int(valores['folhas']), 2 if valores['abertura'] == 'ZIGZAG' else 1,
                   _portas.LIMITES_FOLHAS.get(valores['abertura'], 1),
                   alvo, 'Folhas')))

    # Posicao da folha em relacao ao modulo (nao ha' "Folga no perimetro":
    # pedido do usuario, sempre zero). Com moldura, as medidas DELA.
    if moldura:
        secao, campos = 'Moldura', [campo('ui_porta_moldura', 'Espessura'),
                                    campo('ui_porta_rodape', 'Rodape')]
        if valores.get('trilho') != 'LEVE':
            # o leve nao tem testeira: o campo nao vale nada para ele
            campos.append(campo('ui_porta_testeira', 'Testeira'))
    elif valores['abertura'] == 'CORRER':
        secao, campos = 'Trilhos', [campo('ui_porta_recuo_correr', 'Recuo')]
    elif valores['dobradica'] == 'SUPER_CURVA':
        secao, campos = 'Posicao', [campo('ui_porta_recuo_embutida', 'Recuo')]
    else:
        secao, campos = 'Posicao', [campo('ui_porta_afastamento', 'Afastamento')]
    topo = _titulo_secao(itens, x, topo - ESPACO_SECOES, w, secao)
    topo = _campos_em_linhas(context, itens, x, topo, w, campos)
    if moldura:
        # o tipo de trilho da moldura (pesado/leve), trocavel na porta pronta
        topo = _linha_escolha_gaveta(
            itens, x, topo - 25, w, '', 'porta_trilho', _portas.OPCOES_TRILHO,
            valores.get('trilho', 'PESADO'), alvo=alvo) + 23   # passo 29 -> 31
    if valores['abertura'] == 'CORRER':
        # a folha: chapa ou o quadro de aluminio (estilo do Promob)
        topo = _linha_escolha_gaveta(
            itens, x, topo - 25, w, '', 'porta_folha', _portas.OPCOES_FOLHA_CORRER,
            valores.get('folha', 'CHAPA'), alvo=alvo) + 23

    # Abertura: a dobradica nao aparece, e' automatica (sai dos 4 cliques)
    (prop, rotulo, opcoes), = _portas.ESCOLHAS_PORTAS
    topo -= ESPACO_SECOES
    _titulo_com_slider(itens, x, topo - 23, w, rotulo, altura=23)
    y = _carrossel_gaveta(itens, x, topo - 31 - 25, w, '', prop,
                          _retratos_abertura(opcoes), valores['abertura'],
                          alvo=alvo) - 4

    # Medida da folha nao se repete aqui; so' o ERRO aparece, quando a
    # configuracao nao cabe no vao da porta selecionada.
    try:
        _portas._calcular_folhas_portas(grupo['porta_vao_largura_mm'],
                                grupo['porta_vao_altura_mm'], valores)
    except (ValueError, KeyError, TypeError) as erro:
        itens.append((x, y, w, 22, str(erro), None))
    return itens


ESPACO_SECOES = 8       # respiro a mais entre as categorias da aba


def _titulo_secao(itens, x, topo, w, texto):
    """Titulo de categoria (o de Montagem: 23 px) com o TOPO em `topo`;
    devolve o topo do que vem embaixo."""
    itens.append((x, topo - 23, w, 23, texto, None))
    return topo - 31


def _campos_em_linhas(context, itens, x, topo, w, campos, compacto=None):
    """Campos de valor (37 px, passo 43) a partir do TOPO, numa GRADE: a
    das medidas da porta (L/A/E: 3, 2 ou 1 coluna pela largura), a mesma
    em todas as categorias -- as colunas se alinham de uma secao a outra e
    campo sozinho nao estica (auditoria visual: "Entre planos" virava uma
    faixa de 460 px). `compacto` = (texto, acao) do campo estreito
    (LARGURA_CAMPO_FOLHAS) logo DEPOIS do ultimo; sem lugar na linha (uma
    coluna so'), o vizinho cede o espaco. Devolve o topo do que vem embaixo."""
    if not campos and compacto is None:
        return topo
    colunas = _colunas_medidas(context, w + 24, 3)
    coluna = (w - 6 * (colunas - 1)) / colunas
    posicoes = [[x + (i % colunas) * (coluna + 6), topo - 37 - (i // colunas) * 43,
                 coluna] for i in range(len(campos))]
    if compacto is not None:
        if not posicoes:
            posicoes.append([x, topo - 37, LARGURA_CAMPO_FOLHAS])
        else:
            ultimo = posicoes[-1]
            fim = ultimo[0] + ultimo[2] + 6
            if x + w - fim < LARGURA_CAMPO_FOLHAS:
                ultimo[2] -= LARGURA_CAMPO_FOLHAS + 6
                fim = ultimo[0] + ultimo[2] + 6
            posicoes.append([fim, ultimo[1], LARGURA_CAMPO_FOLHAS])
        campos = list(campos) + [compacto]
    for (cx, cy, largura_campo), (texto, acao) in zip(posicoes, campos):
        if acao and acao[0]=='medida':
            nome=acao[3]
            if texto.startswith(nome+':'):texto=_hud.rotulo_medida(nome)+texto[len(nome):]
        itens.append((cx, cy, largura_campo, 37, texto, acao))
    return min(p[1] for p in posicoes) - 6


# botoes LARANJA do topo das abas: Criar Portas e Criar Puxador
BOTOES_CRIAR = ('portas', 'gavetas', 'prateleiras', 'criar_puxador')
COR_CRIAR_PORTAS = (0.85, 0.38, 0.06, 1.0)        # laranja
COR_CRIAR_PORTAS_ATIVO = (1.0, 0.5, 0.12, 1.0)     # marcando o vao


def _botao_criar_portas(context):
    """(rotulo, acao) do "Criar Portas", no topo da aba Portas.

    Com porta selecionada o botao fica APAGADO: as mudancas ja' se
    aplicam na hora, e outra porta se cria voltando ao modulo. O rotulo
    carrega o estado (marcando o vao, ou o que impede de criar).
    """
    s = context.scene
    grupo = _portas._grupo_portas(context.object)
    if grupo is not None and not grupo.get('porta_parametros'):
        grupo = None
    motivo = '' if grupo is not None else _portas._motivo_portas(s)
    if _portas._apanhando_vao[0]:
        rotulo = 'Marcando o vao... (Esc cancela)'
    elif motivo:
        rotulo = motivo
    else:
        rotulo = 'Criar Portas'
    return rotulo, ('portas', bool(grupo), _portas._apanhando_vao[0], motivo,
                    grupo is not None)


def _botao_criar_gavetas():
    """(rotulo, acao) do "Criar Gavetas", no topo da aba Gavetas (o
    mesmo formato do "Criar Portas": aceso = marcando o vao)."""
    criando = _gavetas._criando()
    return (('Marcando o vao... (Esc cancela)' if criando else 'Criar Gavetas'),
            ('gavetas', False, criando, '', False))


def _botao_criar_prateleiras():
    """(rotulo, acao) do "Criar Prateleiras" (o formato do de gavetas)."""
    criando = _prateleiras._criando()
    return (('Marcando o vao... (Esc cancela)' if criando else 'Criar Prateleiras'),
            ('prateleiras', False, criando, '', False))


def _aba_prateleiras_gaveta(context, itens, x, y, w):
    """Como a aba Gavetas (pedido do usuario): nada selecionado = so' o
    "Criar Prateleiras"; criando = o recado da etapa; selecionadas
    (clique = todas do vao, duplo = uma) = o vao, a chapa e os VAOS --
    todos de baixo para cima, ou so' os dois da prateleira escolhida."""
    assistente = _prateleiras._assistente_prateleiras[0]
    if assistente is not None:
        itens.append((x, y + 26, w, 26, assistente.get('recado', ''), None))
        return itens
    obj = _selecionado(context)
    grupo = _prateleiras.grupo_de(obj) if obj is not None else None
    if grupo is None:
        return itens
    p = _prateleiras.parametros(grupo)
    largura_vao, altura_vao, profundidade = _prateleiras.medidas(grupo)
    prateleira = _prateleiras.individual_ativo(context, grupo)
    indice = int(prateleira[_prateleiras.CHAVE_INDICE]) if prateleira is not None else None
    if indice is not None:
        p = _prateleiras.parametros_individuais(p, indice)
        profundidade = p['profundidade_mm']

    def campo(nome, rotulo, valor):
        if indice is not None and nome in (*_prateleiras.CAMPOS_INDIVIDUAIS, 'largura'):
            nome = 'individual_%d_%s' % (indice, 'largura_mm' if nome == 'largura' else nome)
        return ('%s: %s' % (rotulo, _opcoes._texto_medida(valor)),
                ('medida', 'prateleiras', nome, rotulo, valor))

    topo = _titulo_secao(itens, x, y + 26, w, 'Prateleiras')
    campos = [campo('largura', 'Largura', prateleira.chapa_largura_mm if prateleira is not None else largura_vao)]
    if prateleira is None:
        campos.append(campo('altura', 'Altura', altura_vao))
    campos.append(campo('profundidade_mm', 'Profundidade', profundidade))
    previa = _prateleiras._quantidade_previa[0]
    quantidade = previa[1] if previa and previa[0] == grupo.name else p['quantidade']
    topo = _campos_em_linhas(context, itens, x, topo, w, campos,
        compacto=(str(quantidade),
                  ('contador', 'prateleiras_quantidade', int(p['quantidade']), 1,
                   _prateleiras.MAXIMO_PRATELEIRAS, grupo.name, 'Prateleiras')))
    topo = _titulo_secao(itens, x, topo - ESPACO_SECOES, w, 'Chapa')
    topo = _campos_em_linhas(context, itens, x, topo, w, [
        campo('espessura_mm', 'Espessura', p['espessura_mm']),
        campo('recuo_mm', 'Recuo', p['recuo_mm']),
        campo('folga_lateral_mm', 'Folga lateral', p['folga_lateral_mm'])])
    try:
        vaos = _prateleiras.vaos(altura_vao, _prateleiras.parametros(grupo))
    except ValueError as erro:
        itens.append((x, topo - 23 - ESPACO_SECOES, w, 22, str(erro), None))
        return itens
    topo = _titulo_secao(itens, x, topo - ESPACO_SECOES, w, 'Espacamento')
    topo = _linha_escolha_gaveta(itens, x, topo - 25, w, '', 'prateleiras_espacamento',
                                 _prateleiras.OPCOES_ESPACAMENTO, p['espacamento'],
                                 alvo=grupo.name) + 23
    if prateleira is not None:
        # duplo clique: so' os vaos DELA (mexer neles anda so' ela)
        k = int(prateleira.get(_prateleiras.CHAVE_INDICE, 0))
        campos = [campo('vao_%d' % k, 'Abaixo', vaos[k]),
                  campo('acima_%d' % k, 'Acima', vaos[k + 1])]
    else:
        # o mesmo entre todas e, embaixo, o de cada uma (1 = o de baixo;
        # o ultimo e' o de cima da mais alta)
        campos = [campo('entre_mm', 'Entre prateleiras', _prateleiras.entre(grupo))]
        campos += [campo('vao_%d' % k, 'Vao %d' % (k + 1), v) for k, v in enumerate(vaos)]
    _campos_em_linhas(context, itens, x, topo, w, campos)
    return itens


# alvo da 'escolha' do modelo do puxador das GAVETAS selecionadas
ALVO_PUXADOR_GAVETAS = '@puxador_gavetas'


def _aba_gavetas_gaveta(context, itens, x, y, w):
    """Como a aba Portas (pedido do usuario): nada selecionado = so' o
    "Criar Gavetas" (no topo); criando = o recado da etapa; gavetas
    selecionadas (clique = todas do vao, duplo = uma) = as medidas, a
    frente, o trilho e o puxador -- da gaveta escolhida ou de todas."""
    assistente = _gavetas._assistente_gavetas[0]
    if assistente is not None:
        itens.append((x, y + 26, w, 26, assistente.get('recado', ''), None))
        return itens
    obj = _selecionado(context)
    grupo = _gavetas.grupo_de(obj) if obj is not None else None
    if grupo is None or not (obj == grupo or _gavetas.MARCA_GAVETA in obj):
        return itens
    p = _gavetas.parametros(grupo)
    alvo = grupo.name
    largura_vao, altura_vao, profundidade = _gavetas.medidas(grupo)
    gaveta = obj if _gavetas.MARCA_GAVETA in obj else None
    indice = int(gaveta[_gavetas.CHAVE_INDICE]) if gaveta is not None else None
    if indice is not None:
        p = _gavetas.parametros_da_unidade(p,indice)
        largura_vao = _gavetas.valor(grupo,('L',indice))
        altura_vao = _gavetas.valor(grupo,('A',indice))
        profundidade = _gavetas.valor(grupo,('P',indice))

    def prop(nome):
        return 'individual_%d_%s' % (indice,nome) if indice is not None else nome

    def campo(nome, rotulo, valor):
        return ('%s: %s' % (rotulo, _opcoes._texto_medida(valor)),
                ('medida', 'gavetas', prop(nome), rotulo, valor))

    topo = _titulo_secao(itens, x, y + 26, w, 'Gaveta %d' % (indice+1) if indice is not None else 'Gavetas')
    topo = _campos_em_linhas(context, itens, x, topo, w, [
        campo('largura', 'Largura', largura_vao),
        campo('altura', 'Altura', altura_vao),
        campo('profundidade_mm', 'Profundidade', profundidade)],
        compacto=None if indice is not None else (str(p['quantidade']),
                  ('contador', 'gavetas_quantidade', int(p['quantidade']), 1,
                   _gavetas.MAXIMO_GAVETAS, alvo, 'Gavetas')))
    if int(p['quantidade']) > 1:
        itens.append((x, topo - 28, w, 28, 'Normalizar alturas',
                      ('operador', 'object.cabinet_normalizar_gavetas')))
        topo -= 34
    topo = _titulo_secao(itens, x, topo - ESPACO_SECOES, w, 'Frente')
    topo = _linha_escolha_gaveta(itens, x, topo - 25, w, '', prop('cobertura') if indice is not None else 'gavetas_cobertura',
                                 _gavetas.OPCOES_COBERTURA, p['cobertura'],
                                 alvo=alvo) + 23
    espacos = ([campo('entre_gavetas_mm','Entre gavetas',p['entre_gavetas_mm'])]
              if indice is None else [campo(nome,rotulo,_gavetas.folgas(p)[k])
                for nome,rotulo,k in (('abaixo_mm','Abaixo',indice-1),('acima_mm','Acima',indice))
                if 0 <= k < int(p['quantidade'])-1])
    topo = _campos_em_linhas(context, itens, x, topo, w, [
        campo('folga_frontal_mm', 'Espacamento frontal', p['folga_frontal_mm']),
        *espacos,
        campo('recuo_mm', 'Recuo', p['recuo_mm']),
        campo('espessura_frente_mm', 'Espessura', p['espessura_frente_mm']),
        # flecha do arco da frente (0 = reta): o gaveteiro de canto curvo
        campo('frente_curva_mm', 'Curva', float(p.get('frente_curva_mm') or 0.0))])
    topo = _titulo_secao(itens, x, topo - ESPACO_SECOES, w, 'Trilho %d mm' % round(
        _gavetas.curso(gaveta) if gaveta is not None else float(grupo.get(_gavetas.CHAVE_TRILHO_MM, 0.0))))
    topo = _linha_escolha_gaveta(itens, x, topo - 25, w, '', prop('trilho') if indice is not None else 'gavetas_trilho',
                                 _gavetas.OPCOES_TRILHO, p['trilho'],
                                 alvo=alvo) + 23
    # puxador: o duplo clique isola UMA gaveta (so' ela troca); o grupo
    # selecionado troca todas
    gaveta = obj if _gavetas.MARCA_GAVETA in obj else None
    atual = gaveta.get(_gavetas.CHAVE_PUXADOR, p['puxador']) if gaveta else p['puxador']
    _carrossel_gaveta(itens, x, topo - 23 - ESPACO_SECOES, w,
                      'Puxador desta gaveta' if gaveta else 'Puxador (todas)',
                      'gavetas_puxador', _modelos_puxador_gaveta(), atual,
                      alvo=ALVO_PUXADOR_GAVETAS)
    try:
        _gavetas.calcular(largura_vao, altura_vao, p)
    except ValueError as erro:
        itens.append((x, topo - 23 - ESPACO_SECOES - 160, w, 22, str(erro), None))
    return itens


def _botao_criar_puxador():
    """(rotulo, acao) do "Criar Puxador", no topo da aba Puxadores: a
    acao tem o MESMO formato da do "Criar Portas" (aceso = posicionando)."""
    posicionando = _puxadores._posicionador_puxador[0] is not None
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


def _rolar_ate_o_fim(context):
    """A aba acompanha quem cria: a etapa nova do wizard nasce no FIM do
    painel e, com os retratos, caia para baixo da divisoria sem ninguem
    ver. Chamado so' quando a etapa muda: rolar a' mao continua valendo."""
    tela = getattr(context, 'screen', None)
    area = _area_gaveta(tela) if tela is not None else None
    regiao = next((r for r in area.regions if r.type == 'WINDOW'),
                  None) if area is not None else None
    if regiao is None:
        return
    with context.temp_override(area=area, region=regiao):
        limite = _limite_rolagem_gaveta(bpy.context, regiao.width,
                                        regiao.height)
    tela[_CHAVE_ROLAGEM] = limite
    area.tag_redraw()


def _rolar_biblioteca_ate_pergunta(context):
    """A caixa "Apagar?" de um material nasce sob a fila dele e, numa
    fila de baixo, caia abaixo do pe' do painel (o "Nao" sumia). A
    biblioteca rola o NECESSARIO para a caixa aparecer inteira."""
    tela = getattr(context, 'screen', None)
    if tela is not None and _biblioteca_faixa.area_da_faixa(tela) is not None:
        _biblioteca_faixa.area_da_faixa(tela).tag_redraw()
        return
    area = _area_gaveta(tela) if tela is not None else None
    regiao = next((r for r in area.regions if r.type == 'WINDOW'),
                  None) if area is not None else None
    if regiao is None:
        return
    with context.temp_override(area=area, region=regiao):
        conteudo = _widgets_conteudo_gaveta(bpy.context, regiao.width,
                                            regiao.height, 0, 0)
        limite_bib = _limites_rolagem_gaveta(bpy.context, regiao.width,
                                             regiao.height)[1]
    baixo = _paineis_gaveta(conteudo[WIDGETS_CABECALHO:])[2]
    caixa = next((v for v in baixo if v[5] == ('pergunta',)), None)
    if caixa is None:
        return
    necessario = int(18 + ALTURA_RODAPE_GAVETA - caixa[1]) + 1
    if necessario > int(tela.get(_CHAVE_ROLAGEM_BIB, 0)):
        tela[_CHAVE_ROLAGEM_BIB] = min(limite_bib, necessario)
    area.tag_redraw()


ALTURA_RODAPE_GAVETA = 40      # faixa fixa da engrenagem, no pe' da gaveta
OP_OPCOES = 'object.cabinet_opcoes_gaveta'


ABAS_GAVETA = (('Modulos', 'Mod.', 'MODULOS'), ('Portas', 'Portas', 'PORTAS'),
               ('Gavetas', 'Gav.', 'GAVETAS'), ('Prateleiras', 'Prat.', 'PRATELEIRAS'),
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
    if _biblioteca_faixa.eh_faixa(context):
        return _biblioteca_faixa.widgets(context, largura, altura)
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
    if _biblioteca_faixa.eh_faixa(context):
        return _biblioteca_faixa.interativos(context)
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
    if _gaveta_eventos._icone_acao_gaveta(v[5]) or (v[5] and v[5][0] == 'slider'):
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
    (`_opcoes.FAIXAS_OPCOES`) e 'cor' abre o seletor ali mesmo, empurrando o
    painel para cima. Tudo grava nas preferencias do add-on.
    """
    rodape = [(x, 7, 26, 26, '', ('operador', OP_OPCOES))]
    if _solda._conexao_manual[0] is not None:
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
        valor = _opcoes._opcao(nome)
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
            minimo, maximo, _passo = _opcoes.FAIXAS_OPCOES[nome]
            painel.append((cx, y, cw, 25, _texto_faixa(valor),
                           ('faixa', nome, valor, minimo, maximo)))
        else:
            rgb = _hud._cor_opcao(nome)
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
    _botao_orcamento_opcoes(painel, x, y, w)
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
    'unidade_padrao': tuple((k, v[1]) for k, v in _opcoes.UNIDADES_MEDIDA.items()),
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
    minimo, maximo, passo = _opcoes.FAIXAS_OPCOES[nome]
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
    _opcoes._definir_opcao(OPCAO_DO_ESPECIAL[ATALHO_ESPECIAL[nome]], False)
    _opcoes._definir_opcao(nome, tuple(float(c) for c in rgb[:3]))


def _texto_faixa(valor):
    return ('%g' % round(float(valor), 2)).replace('.', ',') + ' px'


def _hsv_opcao(nome, rgb):
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    if s > 0.001 and v > 0.001:
        _matiz_cor[nome] = h
    return _matiz_cor.get(nome, h), s, v


def _cor_especial(nome):
    """'TEMA' (linhas na cor do tema), 'GIZMO' (realce por eixo) ou ''."""
    if nome == 'hud_rgb_linha' and _opcoes._opcao('hud_linha_tema'):
        return 'TEMA'
    if nome == 'hud_rgb_realce' and _opcoes._opcao('hud_realce_gizmo'):
        return 'GIZMO'
    return ''


# Atalho que nao e' uma cor so': o primeiro da fila de cada opcao
ATALHO_ESPECIAL = {'hud_rgb_linha': 'TEMA', 'hud_rgb_realce': 'GIZMO'}
OPCAO_DO_ESPECIAL = {'TEMA': 'hud_linha_tema', 'GIZMO': 'hud_realce_gizmo'}


def _seletor_cor_gaveta(painel, x, y, w, nome, rgb, especial):
    """Atalhos, quadrado saturacao x brilho e faixa de matiz, embaixo da
    amostra. Devolve o y da ultima linha ocupada (o laco desce 29)."""
    chave_especial = ATALHO_ESPECIAL[nome]
    atalhos = ((chave_especial, _hud._cor_tema_linha() if chave_especial == 'TEMA'
                else _opcoes.COR_REALCE_PADRAO),) + _opcoes.CORES_ATALHO
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
    if context.screen.get(_biblioteca_faixa.CHAVE_LAYOUT) == 2:
        return itens
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
    # Cabecalho: as abas, na largura toda (as
    # correntes entre elas foram descontinuadas)
    aba_w = (w - 4 * (len(ABAS_GAVETA) - 1)) / len(ABAS_GAVETA)
    cx = x
    for rotulo, curto, acao in ABAS_GAVETA:
        itens.append((cx, altura - 40, aba_w, 29,
                      rotulo if aba_w >= 74 else curto, ('aba', acao)))
        cx += aba_w + 4
    y = altura - 105 + _rolagem
    if s.cabinet_aba in {'PORTAS', 'GAVETAS', 'PRATELEIRAS', 'PUXADORES'}:
        # "Criar Portas" no TOPO da aba, logo abaixo das abas, largura
        # inteira e texto centralizado (backlog do usuario, Epico 2.3);
        # antes morava no pe' fixo ao lado da engrenagem. O "Criar
        # Puxador" segue o MESMO padrao (pedido do usuario).
        rotulo, acao = (_botao_criar_portas(context)
                        if s.cabinet_aba == 'PORTAS'
                        else _botao_criar_gavetas() if s.cabinet_aba == 'GAVETAS'
                        else _botao_criar_prateleiras() if s.cabinet_aba == 'PRATELEIRAS'
                        else _botao_criar_puxador())
        itens.append((x, altura - 48 - 8 - 30 + _rolagem, w, 30, rotulo, acao))
        y -= 38
    # Cada aba mostra SO' o que vale para a selecao (pedido do usuario):
    # o bloco de medidas e' da aba dona do item, nao fixo nas tres.
    if s.cabinet_aba == 'PORTAS':
        return _aba_portas_gaveta(context, itens, x, y, w, s, largura, metade)
    if s.cabinet_aba == 'PUXADORES':
        return _aba_puxadores_gaveta(context, itens, x, y, w, s, largura,
                                     metade)
    if s.cabinet_aba == 'GAVETAS':
        return _aba_gavetas_gaveta(context, itens, x, y, w)
    if s.cabinet_aba == 'PRATELEIRAS':
        return _aba_prateleiras_gaveta(context, itens, x, y, w)
    return _aba_modulos_gaveta(context, itens, x, y, w, largura, metade)


def _aba_modulos_gaveta(context, itens, x, y, w, largura, metade):
    """Modulo ou chapa selecionado: medidas (Individual | Grupo) e
    Montagem e o comodo; objeto de fora: as medidas dele. Nada
    selecionado: nada (a biblioteca, embaixo, e' a criacao desta aba; o
    orcamento, da cena inteira, mora nas Opcoes)."""
    obj = _selecionado(context)
    nosso = (obj is not None and _chapas.MARCA_FOLHA not in obj
             and (_chapas.MARCA_CHAPA in obj or _chapas.MARCA_CONJUNTO in obj))
    de_fora = obj is not None and not any(
        m in obj for m in (_chapas.MARCA_CHAPA, _chapas.MARCA_CONJUNTO, _chapas.MARCA_PORTAS,
                           _chapas.MARCA_FOLHA, _chapas.MARCA_PUXADOR, _chapas.MARCA_ACESSORIO,
                           _ferragens.CHAVE_FERRAGEM))
    pergunta = _perguntas._pergunta_atual[0]
    pendente = (pergunta is not None and pergunta['na_gaveta']
                and not pergunta.get('comodo') and not pergunta.get('biblioteca'))
    if nosso or de_fora:
        y = _bloco_medidas_gaveta(context, itens, x, y, w, largura, metade)
    if not (nosso or pendente):
        return _secao_orcamento_gaveta(context, itens, x, y, w)
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
    montagem = (('Corrente', _solda.OP_CORRENTE_OBJETO),
                ('Resetar distancia', _solda.OP_RESETAR_DISTANCIA))
    colunas = min(len(montagem), max(1, int(w // 36)))
    bw = (w - 6 * (colunas - 1)) / colunas
    for i, (rotulo, op) in enumerate(montagem):
        linha, coluna = divmod(i, colunas)
        estado = (_solda._estado_corrente_objeto(context) if op == _solda.OP_CORRENTE_OBJETO
                  else _solda._estado_resetar(context))
        acao = ('operador', op, estado)
        itens.append((x + coluna * (bw + 6), y - linha * 34,
                      bw, 28, rotulo, acao))
    linhas = -(-len(montagem) // colunas)
    y -= (linhas - 1) * 34
    pergunta = _perguntas._pergunta_atual[0]
    if (pergunta is not None and pergunta['na_gaveta']
            and not pergunta.get('comodo') and not pergunta.get('biblioteca')):
        y = _pergunta_na_gaveta(itens, x, y - 6, w, pergunta)
    return _secao_orcamento_gaveta(context, itens, x, y - 40, w)


def _secao_orcamento_gaveta(context, itens, x, y, w):
    """O COMODO do modulo selecionado, que agrupa o orcamento (UMA linha
    que expande; pedido do usuario: a grade fixa ocupava a aba). O botao
    que gera o orcamento e' da cena inteira: mora nas Opcoes."""
    modulos = _orcamento._modulos_da_selecao(context)
    if not modulos:
        return itens
    # titulo como o de Montagem, sem separador (os da aba sao da cascata)
    itens.append((x, y, w, 23, 'Orcamento', None))
    y -= 31
    ativo = _orcamento._modulo_do_objeto(context.object) or modulos[0]
    atual = _orcamento._nome_comodo(_orcamento._comodo_do_modulo(ativo))
    aberto = context.screen.get(_CHAVE_SUSPENSO, '') == _orcamento.SUSPENSO_COMODO
    itens.append((x, y, w, 25, 'Comodo: %s' % (atual or '(nenhum)'),
                  ('suspenso', _orcamento.SUSPENSO_COMODO, aberto)))
    y -= 29
    if aberto:
        # a lista abre DENTRO da aba, empurrando o resto para baixo
        opcoes = [(n, n) for n in _orcamento._comodos_da_lista(context.scene)]
        if atual:
            opcoes.append((_orcamento.COMODO_NENHUM, 'Sem comodo'))
        opcoes.append((_orcamento.COMODO_OUTRO, 'Outro nome...'))
        y = _linha_escolha_gaveta(
            itens, x, y, w, '', _orcamento.ALVO_COMODO, tuple(opcoes), atual,
            alvo=_orcamento.ALVO_COMODO, por_linha=3 if w >= 300 else 2)
    pergunta = _perguntas._pergunta_atual[0]
    if pergunta is not None and pergunta.get('comodo'):
        _pergunta_na_gaveta(itens, x, y + 23, w, pergunta)
    return itens


def _botao_orcamento_opcoes(painel, x, y, w):
    """"Gerar orcamento" no fim das Opcoes (pedido do usuario: o add-on e'
    vendido, nao e' coisa de um ERP so'). Abre o "Salvar como" e grava o
    .txt; o que fez aparece no botao e, havendo, as pendencias numa caixa
    preta logo abaixo. Devolve o y de baixo."""
    gerado = _orcamento._orcamento_gerado[0]
    rotulo = 'Gerar orcamento (.txt)'
    if gerado is not None:
        rotulo = 'Salvo: %d modulo(s) - gerar de novo' % gerado['modulos']
    y -= 6
    painel.append((x, y, w, 28, rotulo,
                   ('operador', _orcamento.OP_EXPORTAR_ORCAMENTO, gerado is not None)))
    if gerado is not None and gerado['pendencias']:
        texto = 'Pendencias:\n' + '\n'.join(
            '\n'.join(_quebrar_texto(p, w - 20))
            for p in gerado['pendencias'])
        linhas = texto.count('\n') + 1
        altura = 12 + 15 * linhas + 4
        y -= 6 + altura
        painel.append((x, y, w, altura, texto, ('pergunta',)))
    return y


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


LARGURA_MIN_RESPOSTA = 70   # px: abaixo disto as respostas quebram a fila


def _pergunta_na_gaveta(itens, x, topo, w, pergunta):
    """Caixa preta com a pergunta e as respostas lado a lado, a partir de
    `topo` (logo abaixo do botao que perguntou). Devolve o y de baixo."""
    texto = pergunta['texto']
    estado = _solda._nome_grupo_gaveta[0]
    if pergunta.get('campo') and estado is not None:
        # o nome que se digita (Enter confirma), com o cursor
        texto += ': ' + _gaveta_desenho._com_cursor(estado['texto'], estado['cursor'])
    linhas = _quebrar_texto(texto, w - 20)
    n = len(pergunta['opcoes'])
    # muitas respostas (os comodos da pintura rapida) quebram em filas
    por_fila = max(1, min(n, int((w - 20 + 6) // (LARGURA_MIN_RESPOSTA + 6))))
    filas = -(-n // por_fila)
    altura = 12 + 15 * len(linhas) + 8 + 26 * filas + 6 * (filas - 1) + 10
    baixo = topo - altura
    itens.append((x, baixo, w, altura, '\n'.join(linhas), ('pergunta',)))
    bw = (w - 20 - 6 * (por_fila - 1)) / por_fila
    for i, (rotulo, _icone, _op, _props) in enumerate(pergunta['opcoes']):
        fila, coluna = divmod(i, por_fila)
        itens.append((x + 10 + coluna * (bw + 6),
                      baixo + 10 + (filas - 1 - fila) * 32, bw, 26, rotulo,
                      ('resposta', i)))
    return baixo


# Icones a' direita do titulo, por biblioteca: presets (pasta, Asset
# Browser, salvar a selecao) ou materiais (pasta, novo material)
BOTOES_BIBLIOTECA = {
    'MODULOS': (('Pasta', 'object.cabinet_abrir_biblioteca'),
                ('Assets', 'object.cabinet_prateleira'),
                ('Salvar +', 'object.cabinet_salvar_biblioteca')),
    'MATERIAIS': (('Pasta', 'object.cabinet_abrir_biblioteca'),
                  ('Novo +', 'object.cabinet_novo_material')),
}
TITULO_BIBLIOTECA = 'Biblioteca'
MODOS_BIBLIOTECA = (('MODULOS', 'Modulos'), ('MATERIAIS', 'Materiais'))


def _cabecalho_biblioteca(context, itens, x, y, w, contagens):
    """Titulo, os dois botoes Modulos | Materiais AO LADO dele (pedido do
    usuario; gaveta estreita: na linha de baixo) e os icones a' direita.
    A contagem vai no botao de cada biblioteca. Devolve o y seguinte."""
    modo = context.scene.cabinet_bib_modo
    botoes = BOTOES_BIBLIOTECA[modo]
    bw = min(28, max(12, (w - 44) / 3))
    reserva = len(botoes) * (bw + 4)
    largura_titulo = _px_botao(TITULO_BIBLIOTECA, False)
    sobra = w - reserva - largura_titulo - 4
    ao_lado = sobra >= 2 * PX_MIN_NIVEL + 4
    # o titulo e' o PRIMEIRO widget do painel (o teste de rolagem o acha)
    itens.append((x, y, largura_titulo if ao_lado else max(1, w - reserva), 26,
                  TITULO_BIBLIOTECA, None))
    for i, (rotulo, op) in enumerate(botoes):
        itens.append((x + w - reserva + 4 + i * (bw + 4), y, bw, 26, rotulo,
                      ('operador', op)))
    if ao_lado:
        # segmento (25) centrado no titulo (26)
        mx, mw, my = x + largura_titulo + 4, sobra, y + 0.5
        y -= 34
    else:
        mx, mw, my = x, w, y - 33
        y -= 33 + 33
    sw = (mw - 4) / 2
    for i, (valor, nome) in enumerate(MODOS_BIBLIOTECA):
        completo = '%s (%d)' % (nome, contagens[valor])
        rotulo = completo if _px_botao(completo, False) <= sw else nome
        itens.append((mx + i * (sw + 4), my, sw, 25, rotulo,
                      ('biblioteca', valor, valor == modo)))
    return y


def _biblioteca_gaveta(context, itens, x, y, w):
    """Biblioteca no painel de baixo, igual nas tres abas e sempre
    aberta: o titulo deixou de ser botao de abrir/fechar. Duas
    bibliotecas, a mesma cascata: presets (Modulos) e Materiais."""
    s = context.scene
    indice = _biblioteca.indice_completo()
    materiais = _materiais.ler_materiais()
    y = _cabecalho_biblioteca(context, itens, x, y, w,
                              {'MODULOS': len(indice), 'MATERIAIS': len(materiais)})
    if s.cabinet_bib_modo == 'MATERIAIS':
        return _materiais_gaveta(context, itens, x, y, w, materiais)
    # os de fabrica (puxadores, dobradicas) entram travados na cascata
    indice = indice + _biblioteca.itens_de_fabrica()
    # Cascata SEM limite de niveis (pedido do usuario): um carrossel por
    # nivel do caminho escolhido, e o de baixo dele enquanto houver filhos
    # (Armarios > Cozinha > Altos > Despenseiros). Ramo vazio nao aparece.
    trilha = _biblioteca.trilha_da_cena(s)
    for nivel in range(1, len(trilha) + 2):
        pai = trilha[:nivel - 1]
        filhos = _biblioteca.filhos_de(indice, pai)
        if not filhos:
            break
        if nivel > 1:
            itens.append((x, y + 31.5, w, 1, '', ('separador',)))
        # o pai do nivel 1 e' None (a chave de rolagem de sempre); o do 2,
        # o nome do 1; do 3 em diante, a tupla
        chave_pai = None if nivel == 1 else (pai[0] if nivel == 2 else tuple(pai))
        y = _linha_cascata_gaveta(itens, x, y, w, filhos, nivel,
                                  trilha[nivel - 1] if len(trilha) >= nivel else '',
                                  indice, chave_pai)
        if len(trilha) < nivel:
            break
    daqui = _biblioteca.itens_em(indice, trilha) if trilha else []
    if daqui:
        itens.append((x, y, min(w, 290), 26, 'Tamanho das miniaturas',
                      ('slider', None)))
        y -= 12
        daqui.sort(key=lambda it: it.get('nome', '').casefold())
        bw, colunas, altura_bloco = _grade_biblioteca(s, w)
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


def _grade_biblioteca(s, w):
    """(lado do bloco, colunas, altura do bloco) da grade de miniaturas,
    a mesma para presets e materiais (slider "Tamanho das miniaturas").
    A foto nunca herda a largura da gaveta: e' sempre quadrada."""
    lado_foto = 88 + (s.chapa_tam_bloco - 2) * 14
    bw = min(w, lado_foto + 10)
    return bw, max(1, int((w + 8) // (bw + 8))), bw + 17


def _materiais_gaveta(context, itens, x, y, w, materiais):
    """A cascata dos materiais (MDF/MDP > categoria) e, no fim dela, a
    grade de esferas: clicar pinta a selecao (`cabinet_aplicar_material`);
    embaixo de cada uma, Editar e Apagar. A esfera do material da selecao
    acende. O "Apagar?" abre logo abaixo da fila do material."""
    s = context.scene
    prefixo = 'cabinet_carrossel_mat'
    y = _linha_cascata_gaveta(itens, x, y, w, _materiais.filhos_n1(materiais),
                              1, s.cabinet_mat_n1, materiais, prefixo=prefixo)
    if not s.cabinet_mat_n1:
        return itens
    itens.append((x, y + 31.5, w, 1, '', ('separador',)))
    y = _linha_cascata_gaveta(itens, x, y, w,
                              _materiais.filhos_n2(materiais, s.cabinet_mat_n1),
                              2, s.cabinet_mat_n2, materiais, s.cabinet_mat_n1,
                              prefixo=prefixo)
    if not s.cabinet_mat_n2:
        return itens
    filhos = _materiais.filhos_n3(materiais, s.cabinet_mat_n1, s.cabinet_mat_n2)
    if filhos:
        itens.append((x, y + 31.5, w, 1, '', ('separador',)))
        y = _linha_cascata_gaveta(itens, x, y, w, filhos, 3, s.cabinet_mat_n3,
                                  materiais, (s.cabinet_mat_n1, s.cabinet_mat_n2),
                                  prefixo=prefixo)
        if not s.cabinet_mat_n3:
            return itens
    itens.append((x, y, min(w, 290), 26, 'Tamanho das miniaturas',
                  ('slider', None)))
    y -= 12
    daqui = [it for it in materiais
             if (it['n1'], it['n2']) == (s.cabinet_mat_n1, s.cabinet_mat_n2)
             and (not filhos or it['n3'] == s.cabinet_mat_n3)]
    daqui.sort(key=lambda it: it['nome'].casefold())
    aplicada = _materiais.chave_aplicada(_selecionado(context))
    pergunta = _perguntas._pergunta_atual[0]
    pendente = (_materiais.chave_da_caixa()
                if pergunta is not None and pergunta.get('biblioteca') else None)
    bw, colunas, altura_bloco = _grade_biblioteca(s, w)
    sw = (bw - 4) / 2
    topo = y
    for inicio in range(0, len(daqui), colunas):
        fila = daqui[inicio:inicio + colunas]
        by = topo - altura_bloco
        for coluna, it in enumerate(fila):
            bx = x + coluna * (bw + 8)
            itens.append((bx, by, bw, altura_bloco, _abreviar(it['nome'], 17),
                          ('material', it, it['chave'] == aplicada)))
            for j, rotulo in enumerate(('Edit.', 'Apagar')):
                itens.append((bx + j * (sw + 4), by - 24, sw, 21, rotulo,
                              ('material_item', it, j)))
        topo = by - 30
        if pendente and any(it['chave'] == pendente for it in fila):
            topo = _pergunta_na_gaveta(itens, x, topo, w, pergunta) - 8
    return itens


def _desenhar_wireframe_gaveta(x, y, modo, largura, altura, profundidade,
                               folhas=0, trocado=False, escala=1.0):
    geometria = _geometria_wireframe(bpy.context.object, modo)
    if geometria is not None:
        (largura, altura, profundidade), extras, arestas = geometria
        arestas = [(a + 8, b + 8) for a, b in arestas]
    else:
        caixas = _biblioteca._caixas_das_folhas(largura, altura, profundidade, folhas)
        extras = [v for caixa in caixas for v in caixa]
        arestas = [(base + a, base + b)
                   for base in [0] + [8 + i * 8 for i in range(len(caixas))]
                   for a, b in _biblioteca._ARESTAS_WIREFRAME]
    pontos = _biblioteca._pontos_wireframe(largura, altura, profundidade, extras)
    if not pontos:
        return
    pontos = [(px * escala, py * escala) for px, py in pontos]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    segmentos = []
    for a, b in arestas:
        segmentos.extend(((x + pontos[a][0], y + pontos[a][1]),
                           (x + pontos[b][0], y + pontos[b][1])))
    shader.bind()
    cor = (*_biblioteca._cor_wireframe(bpy.context), 1)
    shader.uniform_float('color', cor)
    batch_for_shader(shader, 'LINES', {'pos': segmentos}).draw(shader)
    def rotulo(letra, ponto, dx=0, dy=0):
        _texto_gaveta(x + ponto[0] + dx, y + ponto[1] + dy,
                       letra, 14, cor)
    rotulo('P' if trocado else 'L',
           _biblioteca._meio_wireframe(pontos[6], pontos[7]), 0, 11)
    if modo == 'INDIVIDUAL':
        rotulo('E', _biblioteca._meio_wireframe(pontos[2], pontos[6]), -13)
        rotulo('A', _biblioteca._meio_wireframe(pontos[0], pontos[2]), -12, -8)
    elif modo == 'PORTA':
        # A porta tem largura, altura e espessura; profundidade nao.
        rotulo('A', _biblioteca._meio_wireframe(pontos[2], pontos[6]), -13)
        rotulo('E', _biblioteca._meio_wireframe(pontos[0], pontos[2]), -12, -8)
    else:
        rotulo('A', _biblioteca._meio_wireframe(pontos[2], pontos[6]), -13)
        # Com a porta em X, a aresta de cima passa a medir a
        # profundidade do modulo e a que recua, a largura.
        rotulo('L' if trocado else 'P',
               _biblioteca._meio_wireframe(pontos[0], pontos[2]), -12, -8)
        if modo == 'GRUPO':
            rotulo('E', pontos[1], 4, -13)


LIMITE_BYTES_FOTOS = 64 * 1024 * 1024


def _guardar_foto_gaveta(caminho, entrada):
    _fotos_gaveta.pop(caminho, None)
    _fotos_gaveta[caminho] = entrada
    total = sum(e[3] * e[4] * 4 for e in _fotos_gaveta.values())
    while total > LIMITE_BYTES_FOTOS and len(_fotos_gaveta) > 1:
        chave = next(iter(_fotos_gaveta))
        antiga = _fotos_gaveta.pop(chave)
        total -= antiga[3] * antiga[4] * 4


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
                # PNG de preview nao precisa de 32 bits por canal: em
                # telas largas, RGBA8 mantem toda a fila no cache sem thrash.
                # A API aceita somente Buffer FLOAT, mesmo quando o
                # armazenamento da textura e' RGBA8 (conversao na GPU).
                dados = gpu.types.Buffer('FLOAT', largura * altura * 4,
                                          pixels)
                textura = gpu.types.GPUTexture(
                    (largura, altura), format='RGBA8', data=dados)
                entrada = (stamp, textura, limites, largura, altura)
            finally:
                bpy.data.images.remove(imagem)
            _guardar_foto_gaveta(caminho, entrada)
        elif caminho in _fotos_gaveta:
            _fotos_gaveta[caminho] = _fotos_gaveta.pop(caminho)
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


def _trilho_slider_gaveta(acao, x, y, w, h):
    """(inicio, y, largura) do trilho de qualquer slider: o dos retratos
    (sem rotulo, o widget inteiro) ou o das miniaturas da biblioteca."""
    if acao[1] == 'retratos':
        return x + 10, y + h / 2, max(1, w - 20)
    return _trilho_miniaturas_gaveta(x, y, w, h)


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
            return area in (_area_gaveta(janela.screen),
                            _biblioteca_faixa.area_da_faixa(janela.screen))
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
