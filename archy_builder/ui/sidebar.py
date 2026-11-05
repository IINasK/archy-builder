"""Sidebar (GPU-drawn UI): area lifecycle (open, reconnect, limit width), drawing
primitives, per-tab widget layouts shared by drawing and hit-testing, and highlight
animation."""

import bpy, colorsys, math, os, gpu, blf, time
from gpu_extras.batch import batch_for_shader
from bpy.props import StringProperty
from mathutils import Matrix, Vector
from bpy.types import Operator

# Used at LOAD time (class bodies, constants): already loaded earlier.
from .. import opcoes as _opcoes
# Used only at RUNTIME (circular imports): __init__ binds these aliases after loading
# all modules (`_ligar_modulos`).
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
_divisorias = _fundos = None
_formas = None
_paredes_edicao = None
_paredes_composicao = None
_paredes = None
_eventos = None
_editor = None
_areas_criacao = None
_visibilidade = None
_alvenaria = None
_instalacoes = None

class OBJECT_OT_modo_medidas(Operator):
    """Switch editing between a panel and its assembly."""
    bl_idname = "object.cabinet_modo_medidas"
    bl_label = "Measurement Mode"
    bl_options = {'INTERNAL'}

    modo: StringProperty()

    def execute(self, context):
        obj = context.object
        if obj is None:
            return {'CANCELLED'}
        if self.modo == 'INDIVIDUAL' and _chapas.MARCA_CONJUNTO in obj:
            chapas = _modulos._chapas_do_conjunto(obj)
            if not chapas:
                self.report({'WARNING'}, "Cabinet has no panels")
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


# ================================================ FIT TO WIDTH
# bpy neither measures text nor reports how much fits a button: it only truncates from
# the right, removing label endings. To choose layouts and shorten names manually,
# convert region width to logical pixels and estimate text using these values. Measured
# from screenshots: with 6.5/10, the Adjacency label was still clipped in a 280 px
# sidebar. These values are deliberately conservative: spare space is preferable to
# clipped text.
PX_CARACTERE = 7.5
PX_FOLGA_BOTAO = 14.0
PX_ICONE = 22.0
# Minimum width for a category button to remain readable.
PX_MIN_NIVEL = 64.0


def _largura_painel(context):
    """Region width in logical pixels, excluding UI scale."""
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
    """Shorten the NAME; the caller appends the suffix afterward so the count is never
    truncated."""
    if limite >= len(texto):
        return texto
    return texto[:max(1, limite)]


# ===================================================== LEFT SIDEBAR
# Independent native editor: do not move the user's N-region. GPU drawing
# (`_gaveta_desenho._desenhar_gaveta`) and events
# (`_gaveta_eventos.OBJECT_OT_interagir_gaveta`) bypass the UILayout handler, so the bar
# receives actual PRESS/MOUSEMOVE/RELEASE events.
_handler_gaveta = [None]
_biblioteca_faixa = None
_fotos_gaveta = {}
_edicao_gaveta = [None]
# Animated highlights: key -> [current value, target, timestamp]. Key = (area pointer,
# widget name), since the handle and dimension fields now use the SAME glow.
_realces = {}
_CHAVE_GAVETA = "cabinet_gaveta_area"
_CHAVE_PENDENTE = "cabinet_gaveta_pendente"
_CHAVE_ROLAGEM = "cabinet_gaveta_rolagem"
# Library: FIXED lower panel with its own scrolling. Store the divider as a FRACTION of
# usable height so it follows area resizing.
_CHAVE_ROLAGEM_BIB = "cabinet_gaveta_rolagem_bib"
_CHAVE_DIVISA = "cabinet_gaveta_divisa"
DIVISA_PADRAO = 0.5            # User request: lower half.
ALTURA_MIN_PAINEL_GAVETA = 90  # Neither panel disappears while dragging.
FOLGA_DIVISA_GAVETA = 5        # Half-height of the divider's grab strip.
_cursor_divisa = [False]       # The resize cursor is active.
# Options gear open: show options instead of tab content.
_CHAVE_OPCOES = "cabinet_gaveta_opcoes"
# Open dropdown (option name) and open color picker.
_CHAVE_SUSPENSO = "cabinet_gaveta_suspenso"
_CHAVE_COR = "cabinet_gaveta_cor"
ALVO_PREFERENCIAS = '@preferencias'   # Target of the 'escolha' action that saves an
                                      # option.
_LARGURA_MAX_GAVETA = 564
# LOGICAL width at which Width, Height, Depth and Thickness share one row. The sidebar
# opens at exactly this width: the smallest size allowing dimensions side by side (user
# request).
LARGURA_MEDIDAS_EM_LINHA = 480
_LARGURA_PADRAO_GAVETA = LARGURA_MEDIDAS_EM_LINHA


def _largura_inicial_gaveta(context):
    """Initial sidebar area width in pixels. Apply UI scale as at the
    `_colunas_medidas` threshold; +2 covers split rounding, which otherwise opened 1
    px below the threshold with dimensions wrapping to two rows."""
    escala = max(1.0, context.preferences.system.ui_scale)
    return math.ceil(_LARGURA_PADRAO_GAVETA * escala) + 2


def _area_gaveta(screen):
    nativa = next((a for a in screen.areas if _editor.eh_editor(a, _editor.TIPO_MENU)), None) if screen else None
    if nativa is not None:
        return nativa
    ptr = int(screen.get(_CHAVE_GAVETA, 0)) if screen else 0
    return next((a for a in screen.areas
                 if a.type == 'VIEW_3D' and a.as_pointer() == ptr), None)


def _eh_area_gaveta(context):
    return (context.area is not None and context.screen is not None
            and (_editor.eh_editor(context.area) or context.area == _area_gaveta(context.screen)
                 or _biblioteca_faixa.eh_faixa(context)))


def _limitar_largura_gaveta():
    # Area.width is read-only. Correct the divider after resize; never compete for
    # events with a user's modal operator. With enlarged UI, initial width exceeds 564
    # px; the cap must never be lower, or dimensions would wrap again.
    if _eventos._desfazendo[0]:
        return 0.3
    teto = max(_LARGURA_MAX_GAVETA, _largura_inicial_gaveta(bpy.context))
    for janela in bpy.context.window_manager.windows:
        _biblioteca_faixa.reconectar(janela.screen)
        if any(_eventos.modal_interativo(op) for op in getattr(janela, 'modal_operators', ())):
            continue
        painel = _area_gaveta(janela.screen)
        if (janela.screen.get(_CHAVE_GAVETA) and
                (painel is None or painel.type == 'VIEW_3D')):
            # Inactive workspaces receive valid areas only when opened.
            if not bpy.app.timers.is_registered(_reconectar_gavetas):
                bpy.app.timers.register(_reconectar_gavetas, first_interval=.05)
        if painel is None:
            continue
        if hasattr(painel.spaces.active, 'show_gizmo'):
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
    # New area geometry becomes available only on the tick after splitting.
    if _eventos._desfazendo[0]:
        return .05
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
        _editor.configurar(painel)
        screen[_CHAVE_GAVETA] = 0
        screen[_CHAVE_PENDENTE] = 0
        painel.tag_redraw()
        principal.tag_redraw()
    return 0.05 if pendente else None


def _reconectar_gavetas():
    # Area pointers do not survive reloading a .blend file.
    if _eventos._desfazendo[0]:
        return .1
    for janela in bpy.context.window_manager.windows:
        screen = janela.screen
        _editor.reparar(screen)
        _biblioteca_faixa.reconectar(screen)
        painel = _area_gaveta(screen)
        migrar = (painel is not None and painel.type == 'VIEW_3D'
                  and screen.get(_biblioteca_faixa.CHAVE_LAYOUT) != 2
                  and not _biblioteca_faixa.acoplada(screen))
        if migrar:
            principal = _biblioteca_faixa.viewport(screen)
            if principal is not None:
                with bpy.context.temp_override(window=janela, area=principal):
                    _biblioteca_faixa.abrir(bpy.context)
            continue
        if painel is not None:
            if painel.type == 'VIEW_3D':
                _editor.configurar(painel)
                screen[_CHAVE_GAVETA] = 0
            continue
        if not screen.get(_CHAVE_GAVETA):
            continue
        candidatos = [a for a in screen.areas
                      if a.type == 'VIEW_3D'
                      and not a.spaces.active.show_region_header
                      and not a.spaces.active.show_region_toolbar
                      and not a.spaces.active.overlay.show_overlays]
        if len(candidatos) == 1:
            _editor.configurar(candidatos[0])
            screen[_CHAVE_GAVETA] = 0
            candidatos[0].tag_redraw()
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
            print("[Archy Builder] close sidebar on disable:", e)


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
    """Door groups linked to the current selection.

    In scenario 1 (generic object), the door has no link to anything: it appears
    only in SELECTION. Ignoring it left the preview without any door immediately
    after creation."""
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
    """Thicken the narrow edge enough to make it visible.

    An 18 mm panel beside a 2000 mm dimension takes under 1% of the drawing:
    subpixel thickness makes the preview look like paper. This is a schematic, so
    impose a minimum drawn thickness while leaving the other two dimensions intact."""
    largura, espessura, profundidade = dimensoes
    minimo = max(largura, profundidade) * _biblioteca.MINIMO_ESPESSURA_WIREFRAME
    return (largura, max(espessura, minimo), profundidade)


def _folhas_para_wireframe(obj, modo):
    """Number of leaves to show in the preview.

    INDIVIDUAL mode draws ONE panel; no door exists there. Leaves appearing inside
    the part broke the visualization."""
    if modo == 'INDIVIDUAL':
        return 0
    return sum(len(_portas._folhas_portas(g)) for g in _grupos_de_porta(obj))


def _frente_da_porta(obj):
    """Cabinet face on which the door is mounted ('' if there is no door)."""
    for grupo in _grupos_de_porta(obj):
        frente = grupo.get('porta_frente')
        folhas = _portas._folhas_portas(grupo)
        modulo = _portas._modulo_da_chapa(folhas[0]) if folhas else None
        if modulo is not None and grupo.get('porta_parametros'):
            # Old files may store a reversed normal. Draw the face from its actual
            # position without altering those doors.
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
    """Door (width, height, thickness, leaves), or None.

    The Doors tab draws ONLY the door, so use opening dimensions and leaf thickness,
    not cabinet dimensions."""
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
    """Dimensions, actual vertices and edges in the preview's front reference frame.

    Counting leaves loses rows, partial heights and sliding planes. Reading the mesh
    preserves all of these, including geometry edits."""
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
        # Horizontal door: keep the cabinet upright in the drawing, viewed from the
        # front with its lid above (or below).
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
    """Individual or Group comes from SELECTION, not a button.

    One selected object = Individual (panel isolated by double click, or a
    standalone panel). More than one = Group (single click highlights the whole
    cabinet). Sidebar buttons are indicators only."""
    selecionados = list(getattr(context, 'selected_objects', ()) or ())
    return 'INDIVIDUAL' if len(selecionados) <= 1 else 'GRUPO'


def _medidas_da_porta(obj, grupo):
    """Read-only L/A and editable E at door or leaf level.

    Leaf L/A are not editable: the next leaf recalculation (cabinet resized, gap
    changed) would overwrite the change. Thickness belongs to the entire door: all
    its leaves match. SLIDING leaf width is a door parameter and is editable."""
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
        # Sliding doors: editable LEAF width (all leaves equal), per user request;
        # overall assembly width would change while sliding.
        nome = "Width" if _chapas.MARCA_FOLHA in obj or len(folhas) == 1             else "Leaf Width"
        return [(nome, folhas[0].chapa_largura_mm, 'ui_porta_largura_folha'),
                ("Height", folhas[0].chapa_comprimento_mm, ''),
                ("Thickness", espessura, 'ui_porta_espessura')]
    return [("Width", largura, ''), ("Height", altura, ''),
            ("Thickness", espessura, 'ui_porta_espessura')]


def _medidas_gaveta(context):
    obj = context.object
    if obj is not None and _chapas.MARCA_CONJUNTO in obj:
        campos = [("Width", obj.conj_largura_mm, 'ui_conj_largura'),
                  ("Height", obj.conj_altura_mm, 'ui_conj_altura'),
                  ("Depth", obj.conj_profundidade_mm,
                   'ui_conj_profundidade'),
                  ("Thickness", obj.conj_espessura_mm,
                   'ui_conj_espessura')]
        return 'GRUPO', campos, 'objeto'
    grupo = _portas._grupo_portas(obj)
    if grupo is not None and grupo.get('porta_parametros'):
        return 'PORTA', _medidas_da_porta(obj, grupo), 'porta'
    if _puxadores._eh_puxador_parametrico(obj):
        return 'PUXADOR', _puxadores._medidas_puxador_parametrico(obj), 'puxador'
    if obj is not None and _chapas.MARCA_PUXADOR in obj:
        # (name, value, property), as elsewhere; lock goes in the fourth field.
        return 'PUXADOR', [(n, v, p, t) for n, v, p, t, _k
                           in _importacao._medidas_do_puxador(obj)], 'puxador'
    if obj is not None and _chapas.MARCA_CHAPA in obj:
        if _modo_chapa(context, obj) == 'GRUPO':
            s = context.scene
            campos = [("Width", s.grupo_largura_mm, 'ui_grupo_largura'),
                      ("Height", s.grupo_altura_mm, 'ui_grupo_altura'),
                      ("Depth", s.grupo_profundidade_mm,
                       'ui_grupo_profundidade'),
                      ("Thickness", s.grupo_espessura_mm,
                       'ui_grupo_espessura')]
            return 'GRUPO', campos, 'cena'
        cotas=_hud.campos_cotas(obj,'INDIVIDUAL',[obj])
        if any(nome not in ('A1','A2','E') for nome,_v,_p in cotas):
            return 'INDIVIDUAL',cotas,'cota'
        campos = [("Width", obj.chapa_largura_mm, 'ui_chapa_largura'),
                  ("Height", obj.chapa_comprimento_mm,
                   'ui_chapa_comprimento'),
                  ("Thickness", obj.chapa_espessura_mm,
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
            ("Width", valores[0], 'dimensions_0' if editavel else ''),
            ("Height", valores[1], 'dimensions_2' if editavel else ''),
            ("Depth", valores[2], 'dimensions_1' if editavel else '')
        ], 'livre' if editavel else ''
    return 'LIVRE', [], ''


def _linha_cascata_gaveta(itens, x, y, largura, valores, nivel, selecionado,
                         indice=None, pai=None, prefixo='cabinet_carrossel'):
    """One library cascade level IN THE MENU = one dropdown field, as in the DXF (user
    request). Its list floats below it (`_lista_da_cascata`). `prefixo` separates
    presets from materials."""
    if not valores:
        return y
    nome = '%s_%d' % (prefixo, nivel)
    aberto = bpy.context.screen.get(_CHAVE_SUSPENSO, '') == nome
    ordenados = tuple(sorted(valores, key=str.casefold))
    itens.append((x, y, largura, 25, selecionado or "Choose...",
                  ('suspenso', nome, aberto, nivel, ordenados, selecionado)))
    return y - 39


ALTURA_LINHA_LISTA = 24


def _lista_da_cascata(itens, piso, teto):
    """Floating list for the open level: (background, rows...) or []. Open below the
    field, above if needed, or in columns if neither side has room. Exists only when
    the whole field is visible between `piso` and `teto`."""
    campo = next((v for v in itens if v[5] and v[5][0] == 'suspenso'
                  and v[5][2] and len(v[5]) > 3), None)
    if campo is None or campo[1] < piso or campo[1] + campo[3] > teto:
        return []
    cx, cy, cw, ch, _rotulo, (_v, _nome, _aberto, nivel, valores, atual) = campo
    altura = len(valores) * ALTURA_LINHA_LISTA
    embaixo, emcima = cy - 4 - piso, teto - (cy + ch + 4)
    espaco = embaixo if altura <= embaixo or embaixo >= emcima else emcima
    cabem = max(1, int((espaco - 6) // ALTURA_LINHA_LISTA))
    colunas = max(1, math.ceil(len(valores) / cabem))
    por_coluna = math.ceil(len(valores) / colunas)
    largura = (cw - 6 - 4 * (colunas - 1)) / colunas
    altura = por_coluna * ALTURA_LINHA_LISTA + 6
    y0 = cy - 4 - altura if espaco == embaixo else cy + ch + 4
    lista = [(cx, y0, cw, altura, '', ('fundo',))]
    for i, valor in enumerate(valores):
        coluna, linha = divmod(i, por_coluna)
        lista.append((cx + 3 + coluna * (largura + 4),
                      y0 + altura - 3 - (linha + 1) * ALTURA_LINHA_LISTA,
                      largura, ALTURA_LINHA_LISTA, valor,
                      ('nivel', nivel, valor, valor == atual)))
    return lista


def _linha_escolha_gaveta(itens, x, y, w, rotulo, prop, opcoes, atual,
                          ativo=True, alvo='', por_linha=None):
    """Label plus segmented row: the dropdown alternative.

    bpy does not draw a dropdown here, and popups are precisely what the user wants
    out of the way. Segments show ALL options without a click. `por_linha=1` stacks
    options in a column (Opening | Hinge side by side in the Doors tab)."""
    if rotulo:
        # 23 placed the first segment 2 px over the label.
        itens.append((x, y, w, 20, rotulo, None))
        y -= 26
    # 52 px is the smallest segment that still fits a short label.
    if por_linha is None:
        por_linha = max(1, min(len(opcoes), int(w // 52)))
    for inicio in range(0, len(opcoes), por_linha):
        fatia = opcoes[inicio:inicio + por_linha]
        bw = (w - 4 * (len(fatia) - 1)) / len(fatia)
        for i, (valor, texto) in enumerate(fatia):
            # `alvo` = door group name when the row edits a placed door; empty = scene
            # parameter for a new door.
            itens.append((x + i * (bw + 4), y, bw, 25, texto,
                          ('escolha', prop, valor, valor == atual, ativo,
                           alvo)))
        y -= 29
    return y


# IMAGE carousel (user request): show each option's image like the library instead of
# names (Profile, Pull, Edge; Swing, Tilt, Slide). Each image is a regular 'escolha'
# action using the same click path, with its image in the seventh field. If not all fit,
# arrows at the ends scroll one at a time like the library cascade.
LARGURA_RETRATO_MIN = 40        # Image-size slider limits.
LARGURA_RETRATO_MAX = 128
ALTURA_ROTULO_RETRATO = 18
LARGURA_SLIDER_RETRATO = 72     # Small slider beside the title.


def _lado_retrato(w):
    """Side length of EVERY image (handle, opening, hinge): the same square throughout
    the sidebar (user request), sized by the slider. Shrink only when three cannot
    fit side by side: the three opening types must never become a one-item carousel."""
    lado = getattr(bpy.context.scene, 'cabinet_tam_retrato', 64)
    return max(1.0, min(float(lado), (w - 8) / 3))


def _titulo_com_slider(itens, x, y, w, rotulo, altura=20):
    """Image-row title with a slider at its right end to resize ALL images. `altura` 23
    matches the door tab's category title (`_titulo_secao`)."""
    # Slider in its OWN title-height box (visual audit: detached, it floated beside a
    # shortened box); no widgets overlap.
    lado = min(LARGURA_SLIDER_RETRATO, w / 2)
    itens.append((x, y, w - lado - 6, altura, rotulo, None))
    itens.append((x + w - lado, y, lado, altura, '', ('slider', 'retratos')))


def _carrossel_gaveta(itens, x, y, w, rotulo, prop, opcoes, atual,
                      ativo=True, alvo='', chave=''):
    """`opcoes` = (value, text, image); image = dict from `_desenhar_foto_gaveta`. Same
    contract as `_linha_escolha_gaveta`: `y` is label y; return the next row's y."""
    if rotulo:
        _titulo_com_slider(itens, x, y, w, rotulo)
        y -= 26
    n = len(opcoes)
    if not n:
        return y
    bw = _lado_retrato(w)
    cabe = n * bw + 4 * (n - 1) <= w + 0.01     # (w - 8) / 3 x 3 has no rounding error.
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
    # Top aligns with where a segmented row would start (25 px).
    base = y + 25 - altura
    if not cabe:
        for lado, dx in ((-1, x), (1, x + w - 20)):
            itens.append((dx, base, 20, altura, '',
                          ('rolar_nivel', chave, lado, limite)))
    for i, (valor, texto, foto) in enumerate(opcoes[inicio:inicio + colunas]):
        itens.append((x0 + i * (bw + 4), base, bw, altura, texto,
                      ('escolha', prop, valor, valor == atual, ativo, alvo,
                       foto)))
    return base - 29        # As after a row ending at `base`.


def _colunas_medidas(context, largura, n):
    """Dimension-field columns by LOGICAL sidebar width: all in one row (>= 480), two
    (>= 240), or one. Applies to the fixed block and door dimensions so they align."""
    logica = largura / max(1.0, context.preferences.system.ui_scale)
    return max(1, n if logica >= LARGURA_MEDIDAS_EM_LINHA
               else 2 if logica >= 240 else 1)


def _bloco_medidas_gaveta(context, itens, x, y, w, largura, metade,
                          modos=True, medidas=None):
    """Item dimension fields. Only the item's OWNER tab shows them (user request: menus
    show what applies to selection; cabinets do not appear in the Doors tab).
    `medidas` = prepared (mode, fields, owner), as for the door drawn by the wizard.
    No synchronization button: the handler rereads dimensions automatically
    (`_modulos._sincronizar_medidas_ativas`)."""
    obj = context.object
    y += 23
    modo, campos, dono = medidas or _medidas_gaveta(context)
    # The Doors tab edits the leaf assembly, never an isolated part: toggling
    # Individual/Group there has no meaning.
    if (modos and obj is not None and modo != 'PORTA'
            and (_chapas.MARCA_CHAPA in obj or _chapas.MARCA_CONJUNTO in obj)):
        for i, (nome, identifier) in enumerate((('Individual', 'INDIVIDUAL'), ('Group', 'GRUPO'))):
            itens.append((x + i * (metade + 6), y, metade, 25, nome,
                          ('modo', identifier, modo == identifier)))
        y -= 33
    if campos:
        # Fields are 37 px high; separate them from the mode tabs above.
        y -= 8
        colunas = _colunas_medidas(context, largura, len(campos))
        if dono=='cota':colunas=min(3,colunas)
        largura_campo = (w - 6 * (colunas - 1)) / colunas
        # Handle: lock at each row end. Locked dimensions stay fixed when the door
        # changes; unlocked dimensions stretch with it.
        for i, campo in enumerate(campos):
            nome, valor, prop = campo[:3]
            # Only imported handles have locks (fourth field); parametric handles do
            # not.
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
    # No footer: item name, Panel and Auto-regenerate were removed at the user's request
    # (panels always retain modeled geometry).
    return y


def _botoes_gaveta(itens, x, y, w, botoes):
    """Text buttons in two columns when space allows; return the next y."""
    colunas = 2 if w >= 240 else 1
    bw = (w - 6 * (colunas - 1)) / colunas
    for i, (rotulo, op) in enumerate(botoes):
        linha, coluna = divmod(i, colunas)
        itens.append((x + coluna * (bw + 6), y - linha * 34, bw, 28, rotulo,
                      ('operador', op)))
    return y - math.ceil(len(botoes) / colunas) * 34


def _modelos_puxador_gaveta():
    """Carousel images: protected factory models and user models from the library's
    Handles category."""
    opcoes = [(t, _puxadores.MODELOS_PUXADOR[t][0],
               _biblioteca.foto_padrao('puxador_' + t))
              for t in _puxadores.MODELOS_PADRAO]
    for it in _puxadores.modelos_do_usuario():
        opcoes.append((_puxadores.valor_do_modelo('MODELO', it['arquivo']),
                       _abreviar(it.get('nome', ''), 14), it))
    return tuple(opcoes)


def _aba_puxadores_gaveta(context, itens, x, y, w, s, largura, metade):
    """Like other tabs (user request): no selection = only Create Handle at the top,
    outside this block. During creation, show the MODEL in an image carousel
    (clicking changes the placement model immediately). Selected handle: its
    dimensions (and imported-model locks), plus the carousel for add-on handles;
    switching rebuilds THAT handle. External object: Use as Handle (becomes a
    library model). As in the Doors tab, omit the item name."""
    usando = _puxadores._usando_como_puxador[0]
    if usando is not None:
        itens.append((x, y + 26, w, 26,
                      "Click the handle face that touches the door", None))
        return itens
    posicionando = _puxadores._posicionador_puxador[0]
    if posicionando is not None:
        _carrossel_gaveta(itens, x, y + 26, w, "Handle Model",
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
            _carrossel_gaveta(itens, x, y, w, "Handle Model",
                              'cabinet_puxador_modelo', _modelos_puxador_gaveta(),
                              _puxadores.valor_do_modelo(
                                  obj['puxador_tipo'], obj.get('puxador_modelo', '')),
                              alvo=ALVO_PUXADOR)
        else:
            ligado = obj.parent is not None and _chapas.MARCA_CHAPA in obj.parent
            itens.append((x, y, w, 26, "Linked to a door" if ligado
                          else "Detached: link to a door", None))
        return itens
    if obj is not None and obj.type == 'MESH' and not any(
            m in obj for m in (_chapas.MARCA_CHAPA, _chapas.MARCA_CONJUNTO, _chapas.MARCA_PORTAS,
                               _chapas.MARCA_FOLHA, _chapas.MARCA_ACESSORIO, _ferragens.CHAVE_FERRAGEM)):
        _botoes_gaveta(itens, x, y + 26, w, (
            ("Use as Handle", 'object.cabinet_usar_como_puxador'),))
    return itens


def _valores_portas(s, grupo=None):
    """What the tab SHOWS: selected door parameters, or scene parameters when there is
    no door (the next one to create).

    Reading directly from the group rather than copying to the scene prevents
    showing the LAST door's values as if they belonged to this one."""
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
# Target of the 'escolha' action (and owner of 'medida') editing SELECTED hardware:
# applies to all doors in its cabinet.
ALVO_FERRAGENS = '@ferragens'
# Target of the model 'escolha' action replacing the SELECTED handle.
ALVO_PUXADOR = '@puxador'


def _selecionado(context):
    """The active object, if selected (an unselected active object does not count: the
    sidebar shows what is SELECTED, per user request)."""
    obj = getattr(context, 'object', None)
    return obj if obj is not None and obj.select_get() else None


LARGURA_CONFIRMAR = 30           # Green acceptance square.
LARGURA_CAMPO_FOLHAS = 76        # Compact door Leaves field.
# Counter column beside images; below this width the section stacks (with 64 px images,
# the previous threshold was 260).
LARGURA_MIN_COLUNA_FERRAGENS = 120


def _secao_ferragens_gaveta(itens, x, y, w, dados, alvo, dono,
                            separar=True, abertura=None):
    """EDITABLE hinges and gas struts in the user's mockup layout:
    [opening][hinge][Hinges: < 2 >] in one row, with offset below. The step's
    acceptance control is the GREEN square right of the edited field
    (`CONFIRMAR_ETAPA`, same as the viewport click). Quantity uses a counter (drag
    or click halves), no longer five segments. Serves the wizard (modal target,
    `abertura` = chosen opening image) and selected hardware (all cabinet doors).
    `dados[tipo]`: 'qtd' and 'mm' (None = not reached yet), 'info', 'modelo' (hinge
    image), and 'confirmar' = (step, 'qtd' or 'mm'). Return the next label's y."""

    def campo_com_aceite(cx, cy, cw, h, widget, parte):
        """The field and, if this is its step, the adjacent green square."""
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
            rotulo, limites = "Hinges", _portas.LIMITES_DOBRADICAS
            prop_qtd, prop_mm = 'dobradicas_qtd', 'dobradicas_margem_mm'
            nome_mm = "Corner Offset"
        else:
            rotulo, limites = "Gas Stays", _portas.LIMITES_PISTOES
            prop_qtd, prop_mm = 'pistoes_qtd', 'pistoes_offset_mm'
            nome_mm = "Distance from Top"
        if d.get('info'):
            rotulo = '%s: %s' % (rotulo, d['info'])
        # Images: chosen opening (click returns to selection) and AUTOMATIC hinge type,
        # for viewing only, without clicking.
        retratos = []
        if tipo == 'DOBRADICA' and abertura is not None:
            valor, texto, foto = abertura
            retratos.append((texto, ('escolha', 'porta_abertura', valor, True,
                                     True, _portas.ALVO_ASSISTENTE, foto)))
            _titulo_com_slider(itens, x, y, w, "Opening")
            y -= 26
        modelo = d.get('modelo')
        if tipo == 'DOBRADICA' and modelo in _portas.NOME_DOBRADICA:
            retratos.append((_portas.NOME_DOBRADICA[modelo],
                             ('escolha', 'dobradica', modelo, True, False, '',
                              _biblioteca.foto_padrao('dobradica_' + modelo))))
        topo = y + 20
        # The SAME square as other images (`_lado_retrato`).
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
            # Without the Opening title (selected hardware), put the image-size slider
            # on the label row.
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
    """Doors tab during CREATION (user request): reveal everything step by step. After
    marking the area, show read-only door dimensions derived from clicks, then a
    clickable copy of the viewport box. The modal answers through
    `_responder_pela_gaveta` in `_assistente.OBJECT_OT_apanhar_vao_portas`;
    answering again rebuilds from that point. Hardware becomes EDITABLE as soon as
    the wizard reaches it (hinge/gas-strut counts and offsets)."""
    etapa, escolhas = a.get('etapa'), a.get('escolhas', {})
    medidas = a.get('medidas_porta')
    if medidas:
        largura_mm, altura_mm, espessura = medidas
        y = _bloco_medidas_gaveta(
            context, itens, x, y, w, largura, metade, modos=False,
            medidas=('PORTA', [("Width", largura_mm, ''),
                               ("Height", altura_mm, ''),
                               ("Thickness", espessura, '')], 'porta'))
    itens.append((x, y + 31, w, 1, '', ('separador',)))
    filas = []
    if etapa == 'CONFIRMAR':
        filas.append(("Are the dimensions correct?", 'porta_confirmar',
                      _portas.OPCOES_CONFIRMAR, None))
    else:
        filas.append(("How many leaves?" if etapa == 'FOLHAS' else "Leaves",
                      'porta_folhas',
                      tuple((int(k), t) for k, t in _portas.OPCOES_FOLHAS),
                      escolhas.get('folhas')))
    # Once chosen, the opening becomes the first image in the hinge row (user mockup);
    # all three appear only while choosing.
    if etapa == 'TIPO' or ('abertura' in escolhas
                           and etapa not in ETAPAS_FERRAGENS_ASSISTENTE):
        filas.append(("Choose the opening type" if etapa == 'TIPO' else "Opening",
                      'porta_abertura', a.get('tipos') or _portas.ESCOLHAS_PORTAS[0][2],
                      escolhas.get('abertura')))
    if etapa == 'MOLDURA' or (etapa in {'BASE', 'TRILHO'}
                              and 'tipo_correr' in escolhas):
        # Half-thickness clicks on both sides of a sliding door: same box as the
        # viewport.
        filas.append(("Inset or framed door?", 'porta_tipo_correr',
                      _portas.TIPOS_CORRER, escolhas.get('tipo_correr')))
    if etapa in {'BASE', 'TRILHO'}:
        # With a frame: straight to the floor (no plinth), or with a base?
        sem = escolhas.get('rodape_mm')
        filas.append(("Does the door have a base?", 'porta_base', _portas.OPCOES_BASE,
                      None if sem is None else 'SEM' if sem <= 0 else 'COM'))
    if etapa == 'TRILHO':
        filas.append(("Which track?", 'porta_trilho', _portas.OPCOES_TRILHO,
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
        # Type comes from the edge under the mouse (user request: type was not
        # appearing); inset always uses the full-crank hinge type.
        snap = a.get('snap')
        modelo = 'SUPER_CURVA' if a.get('embutida') else None
        if snap:
            lado = _portas.COBERTURAS_LADOS[_portas.INDICE_LADO[snap[0]['lado']]]
            modelo = _portas._dobradica_da_cobertura(
                float(a.get('coberturas', {}).get(lado, 1.0)), a.get('embutida'))
        dobradicas = {'info': "click their edge", 'qtd': None,
                      'modelo': modelo}
    else:
        side_label = _opcoes.DIRECTION_LABELS[aresta['lado']].lower()
        dobradicas = {'info': "%s edge" % side_label,
                      'modelo': escolhas.get('dobradica'),
                      'qtd': a.get('qtd'), 'mm': a.get('margem')}
    # Green acceptance control sits on the field edited by this step.
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
    """Show only what applies NOW (user request for every tab): no selection = only
    Create Doors at the top, outside this block; creation = step-by-step fields
    (`_filas_do_assistente`); selected hardware = only its counts and offsets;
    selected door or leaf = ITS dimensions, leaves, opening and gaps, with no hinge
    controls, which belong to hardware selection."""
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
    topo = y + 26 + 28
    itens.append((x, topo - 28, w, 28, "Hide Door and Attached Components",
                  ('operador', 'object.cabinet_esconder_porta')))
    topo -= 34
    alvo = grupo.name
    valores = _valores_portas(s, grupo)
    moldura = _portas._correr_sobreposta(dict(grupo['porta_parametros']))

    def campo(prop_ui, rotulo):
        valor = valores[_portas._PARAMETRO_DA_MEDIDA_PORTA[prop_ui]]
        return ('%s: %s' % (rotulo, _opcoes._texto_medida(valor)),
                ('medida', 'porta', prop_ui, rotulo, valor))

    # User audit: organize the tab into titled CATEGORIES (same title style as
    # Assembly/Estimate), short unclipped labels and fields aligned by a shared column
    # rule. No 'Door N of M' header: no names or repeated dimensions (user request).
    _modo, medidas, dono = _medidas_gaveta(context)
    topo = _titulo_secao(itens, x, topo, w, "Door")
    topo = _campos_em_linhas(context, itens, x, topo, w, [
        ('%s: %s' % (nome, _opcoes._texto_medida(valor)),
         ('medida', dono, prop, nome, valor)) for nome, valor, prop in medidas])

    # LEAVES: COMPACT field at the end of the Between Planes row (user request; formerly
    # segments 1 2 3 4). Sideways drag changes the value; click types.
    folhas = []
    if valores['folhas'] > 1:
        folhas.append(campo('ui_porta_entre_planos', "Between Planes")
                      if valores['abertura'] == 'CORRER'
                      else campo('ui_porta_entre_folhas', "Between Leaves"))
    topo = _titulo_secao(itens, x, topo - ESPACO_SECOES, w, "Leaves")
    topo = _campos_em_linhas(
        context, itens, x, topo, w, folhas,
        compacto=(str(valores['folhas']),
                  ('contador', 'porta_folhas', int(valores['folhas']), 2 if valores['abertura'] == 'ZIGZAG' else 1,
                   _portas.LIMITES_FOLHAS.get(valores['abertura'], 1),
                   alvo, "Leaves")))

    # Leaf position relative to the cabinet (no Perimeter Gap: always zero, per user
    # request). Framed doors show the FRAME's dimensions.
    if moldura:
        secao, campos = "Frame", [campo('ui_porta_moldura', "Thickness"),
                                    campo('ui_porta_rodape', "Toe Kick")]
        if valores.get('trilho') != 'LEVE':
            # The light track has no fascia: this field does not apply to it.
            campos.append(campo('ui_porta_testeira', "Fascia"))
    elif valores['abertura'] == 'CORRER':
        secao, campos = "Rails", [campo('ui_porta_recuo_correr', "Inset")]
    elif valores['dobradica'] == 'SUPER_CURVA':
        secao, campos = "Position", [campo('ui_porta_recuo_embutida', "Inset")]
    else:
        secao, campos = "Position", [campo('ui_porta_afastamento', "Offset")]
    topo = _titulo_secao(itens, x, topo - ESPACO_SECOES, w, secao)
    topo = _campos_em_linhas(context, itens, x, topo, w, campos)
    if moldura:
        # Frame track type (heavy/light), editable on a finished door.
        topo = _linha_escolha_gaveta(
            itens, x, topo - 25, w, '', 'porta_trilho', _portas.OPCOES_TRILHO,
            valores.get('trilho', 'PESADO'), alvo=alvo) + 23   # Step 29 -> 31.
    if valores['abertura'] == 'CORRER':
        # Leaf: panel or aluminum frame (DXF style).
        topo = _linha_escolha_gaveta(
            itens, x, topo - 25, w, '', 'porta_folha', _portas.OPCOES_FOLHA_CORRER,
            valores.get('folha', 'CHAPA'), alvo=alvo) + 23

    # Opening: omit the hinge; its type is automatic from both boundaries.
    (prop, rotulo, opcoes), = _portas.ESCOLHAS_PORTAS
    topo -= ESPACO_SECOES
    _titulo_com_slider(itens, x, topo - 23, w, rotulo, altura=23)
    y = _carrossel_gaveta(itens, x, topo - 31 - 25, w, '', prop,
                          _retratos_abertura(opcoes), valores['abertura'],
                          alvo=alvo) - 4

    # Do not repeat leaf dimensions here; show only the ERROR when the configuration
    # does not fit the selected door's opening.
    try:
        _portas._calcular_folhas_portas(grupo['porta_vao_largura_mm'],
                                grupo['porta_vao_altura_mm'], valores)
    except (ValueError, KeyError, TypeError) as erro:
        itens.append((x, y, w, 22, str(erro), None))
    return itens


ESPACO_SECOES = 8       # Extra spacing between tab categories.


def _titulo_secao(itens, x, topo, w, texto):
    """Category title (Assembly style: 23 px) with its TOP at `topo`; return the top of
    the following content."""
    itens.append((x, topo - 23, w, 23, texto, None))
    return topo - 31


def _campos_em_linhas(context, itens, x, topo, w, campos, compacto=None,
                      colunas_uniformes=False):
    """Value fields (37 px, step 43) starting at the TOP in a GRID, like door
    dimensions (L/A/E: three, two or one column by width). Use the same grid in
    every category: columns align across sections and lone fields do not stretch
    (visual audit: Between Planes became a 460 px strip). `compacto` = (text,
    action) for the narrow field (LARGURA_CAMPO_FOLHAS) immediately AFTER the last
    one; if the row is full (single column), its neighbor yields space.
    `colunas_uniformes` divides width among dimensions BEFORE reserving the counter;
    across multiple rows it retains the grid without squeezing the last dimension.
    Return the top of following content."""
    if not campos and compacto is None:
        return topo
    colunas = _colunas_medidas(context, w + 24, 3)
    coluna = (w - 6 * (colunas - 1)) / colunas
    if compacto is not None and colunas_uniformes and 0 < len(campos) <= colunas:
        colunas = len(campos)
        coluna = (w - LARGURA_CAMPO_FOLHAS - 6 * colunas) / colunas
    posicoes = [[x + (i % colunas) * (coluna + 6), topo - 37 - (i // colunas) * 43,
                 coluna] for i in range(len(campos))]
    if compacto is not None:
        if not posicoes:
            posicoes.append([x, topo - 37, LARGURA_CAMPO_FOLHAS])
        else:
            ultimo = posicoes[-1]
            fim = ultimo[0] + ultimo[2] + 6
            if x + w - fim < LARGURA_CAMPO_FOLHAS - 1e-6:
                if colunas_uniformes:
                    posicoes.append([x, ultimo[1] - 43, LARGURA_CAMPO_FOLHAS])
                else:
                    ultimo[2] -= LARGURA_CAMPO_FOLHAS + 6
                    fim = ultimo[0] + ultimo[2] + 6
                    posicoes.append([fim, ultimo[1], LARGURA_CAMPO_FOLHAS])
            else:
                posicoes.append([fim, ultimo[1], LARGURA_CAMPO_FOLHAS])
        campos = list(campos) + [compacto]
    for (cx, cy, largura_campo), (texto, acao) in zip(posicoes, campos):
        if acao and acao[0]=='medida':
            nome=acao[3]
            if texto.startswith(nome+':'):texto=_hud.rotulo_medida(nome)+texto[len(nome):]
        itens.append((cx, cy, largura_campo, 37, texto, acao))
    return min(p[1] for p in posicoes) - 6


# ORANGE buttons at tab tops: Create Doors and Create Handle.
BOTOES_CRIAR = ('portas', 'gavetas', 'prateleiras', 'divisorias', 'criar_puxador')
COR_CRIAR_PORTAS = (0.85, 0.38, 0.06, 1.0)        # Orange.
COR_CRIAR_PORTAS_ATIVO = (1.0, 0.5, 0.12, 1.0)     # Marking the opening.
# Enter/exit wall editing with the SAME pattern (user request): orange to enter, the
# brighter active-step orange to exit. Tuple, never set/dict: comparison must not hash
# the action.
OPERADORES_DESTAQUE = ('object.cabinet_definir_alvenaria', 'object.cabinet_editar_parede', 'object.cabinet_editar_ambientes', 'object.cabinet_sair_parede',
                      'object.cabinet_confirmar_alvenaria',
                      'object.cabinet_definir_ambiente', 'object.editmode_toggle',
                      'object.cabinet_aplicar_area', 'object.cabinet_definir_area', 'object.cabinet_internos',
                      'object.cabinet_conectar_vertices', 'object.cabinet_confirmar_conexao',
                      'object.cabinet_portas_internos')
OPERADOR_DESTAQUE_ATIVO = 'object.cabinet_sair_parede'


def _botao_criar_portas(context):
    """(label, action) for Create Doors at the top of the Doors tab.

    With a door selected, the button is DISABLED: changes apply immediately, and
    creating another door requires returning to the cabinet. The label conveys state
    (marking the opening or the reason creation is blocked)."""
    s = context.scene
    grupo = _portas._grupo_portas(context.object)
    if grupo is not None and not grupo.get('porta_parametros'):
        grupo = None
    motivo = '' if grupo is not None else _portas._motivo_portas(s)
    if _portas._apanhando_vao[0]:
        rotulo = "Marking the opening... (Esc cancels)"
    elif motivo:
        rotulo = motivo
    else:
        rotulo = "Create Doors"
    return rotulo, ('portas', bool(grupo), _portas._apanhando_vao[0], motivo,
                    grupo is not None)


def _botao_criar_gavetas():
    """(label, action) for Create Drawers at the top of the Drawers tab (same format as
    Create Doors: lit = marking the opening)."""
    criando = _gavetas._criando()
    return (("Marking the opening... (Esc cancels)" if criando else "Create Drawers"),
            ('gavetas', False, criando, '', False))


def _botao_criar_prateleiras():
    """(label, action) for Create Shelves, using the drawer-button format."""
    criando = _prateleiras._criando()
    return (("Marking the opening... (Esc cancels)" if criando else "Create Shelves"),
            ('prateleiras', False, criando, '', False))


def _aba_divisorias_gaveta(context, itens, x, y, w):
    assistente = _divisorias._assistente_divisorias[0]
    if assistente is not None:
        itens.append((x, y + 26, w, 26, assistente.get('recado', ''), None))
        return itens
    grupo = _divisorias.grupo_de(context.object)
    if grupo is None:
        return itens
    p = _divisorias.parametros(grupo)
    l, a, prof = _divisorias.medidas(grupo)
    def campo(nome, rotulo, valor):
        return ('%s: %s' % (rotulo, _opcoes._texto_medida(valor)),
                ('medida', 'divisorias', nome, rotulo, valor))
    topo = _titulo_secao(itens, x, y + 26, w, "Partitions")
    topo = _campos_em_linhas(context, itens, x, topo, w,
        [campo('largura', 'A1', l), campo('altura', 'A2', a),
         campo('profundidade_mm', 'A3', prof)], colunas_uniformes=True)
    topo = _titulo_secao(itens, x, topo - ESPACO_SECOES, w, "Panel")
    topo = _campos_em_linhas(context, itens, x, topo, w,
        [campo('espessura_mm', "Thickness", p['espessura_mm']),
         campo('recuo_mm', "Inset", p['recuo_mm'])])
    topo = _titulo_secao(itens, x, topo - ESPACO_SECOES, w, "Spacing")
    g = _divisorias.calcular(l, a, p)['vaos']
    _campos_em_linhas(context, itens, x, topo, w,
        [campo('vao_%d' % i, 'E%d' % (i + 1), v) for i, v in enumerate(g)])
    return itens


def _aba_prateleiras_gaveta(context, itens, x, y, w):
    """Like the Drawers tab (user request): no selection = only Create Shelves;
    creation = current-step message; selected shelves (click = all in the opening,
    double click = one) = opening, panel and GAPS, all bottom to top, E1..En+1,
    including individual selection."""
    assistente = _prateleiras._assistente_prateleiras[0]
    if assistente is not None:
        itens.append((x, y + 26, w, 26, assistente.get('recado', ''), None))
        return itens
    obj = _selecionado(context)
    grupo = _prateleiras.grupo_de(obj) if obj is not None else None
    if grupo is None:
        return itens
    y = _fundos.widgets_vinculo(context, itens, x, y, w)
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

    topo = _titulo_secao(itens, x, y + 26, w, "Shelves")
    campos = [campo('largura', "Width", prateleira.chapa_largura_mm if prateleira is not None else largura_vao)]
    if prateleira is None:
        campos.append(campo('altura', "Height", altura_vao))
    campos.append(campo('profundidade_mm', "Depth", profundidade))
    previa = _prateleiras._quantidade_previa[0]
    alvo_contador = prateleira or grupo
    detalhe = None
    if prateleira is not None:
        try:
            detalhe = _prateleiras.detalhamento(grupo, prateleira)
        except ValueError as erro:
            itens.append((x, topo - 23, w, 22, str(erro), None))
            return itens
    quantidade_atual = detalhe['quantidade'] if detalhe else int(p['quantidade'])
    quantidade = previa[1] if previa and previa[0] == alvo_contador.name else quantidade_atual
    topo = _campos_em_linhas(context, itens, x, topo, w, campos,
        colunas_uniformes=True,
        compacto=(str(quantidade),
                  ('contador', 'prateleiras_quantidade', quantidade_atual, 0,
                   _prateleiras.MAXIMO_PRATELEIRAS - int(p['quantidade']) + quantidade_atual,
                   alvo_contador.name, "Shelves")))
    topo = _titulo_secao(itens, x, topo - ESPACO_SECOES, w, "Panel")
    topo = _campos_em_linhas(context, itens, x, topo, w, [
        campo('espessura_mm', "Thickness", p['espessura_mm']),
        campo('recuo_mm', "Inset", p['recuo_mm']),
        campo('folga_lateral_mm', "Side Gap", p['folga_lateral_mm'])])
    try:
        vaos = _prateleiras.vaos(altura_vao, _prateleiras.parametros(grupo))
    except ValueError as erro:
        itens.append((x, topo - 23 - ESPACO_SECOES, w, 22, str(erro), None))
        return itens
    topo = _titulo_secao(itens, x, topo - ESPACO_SECOES, w, "Spacing")
    itens.append((x, topo - 37, w, 37, "Center Spacing",
                  ('operador', 'object.cabinet_alinhar_prateleiras')))
    topo -= 43
    indices = (range(detalhe['primeiro'], detalhe['ultimo'] + 2) if detalhe else range(len(vaos)))
    campos = [campo('vao_%d' % k, 'E%d' % (k + 1), vaos[k]) for k in indices]
    _campos_em_linhas(context, itens, x, topo, w, campos)
    return itens


# Target of the handle-model 'escolha' action for selected DRAWERS.
ALVO_PUXADOR_GAVETAS = '@puxador_gavetas'


def _aba_gavetas_gaveta(context, itens, x, y, w):
    """Like the Doors tab (user request): no selection = only Create Drawers at the
    top; creation = current-step message; selected drawers (click = all in the
    opening, double click = one) = dimensions, front, rail and handle for the chosen
    drawer or all of them."""
    assistente = _gavetas._assistente_gavetas[0]
    if assistente is not None:
        itens.append((x, y + 26, w, 26, assistente.get('recado', ''), None))
        return itens
    obj = _selecionado(context)
    grupo = _gavetas.grupo_de(obj) if obj is not None else None
    if grupo is None or not (obj == grupo or _gavetas.MARCA_GAVETA in obj):
        return itens
    y = _fundos.widgets_vinculo(context, itens, x, y, w)
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

    topo = _titulo_secao(itens, x, y + 26, w, "Drawer %d" % (indice+1) if indice is not None else "Drawers")
    topo = _campos_em_linhas(context, itens, x, topo, w, [
        campo('largura', "Width", largura_vao),
        campo('altura', "Height", altura_vao),
        campo('profundidade_mm', "Depth", profundidade)],
        compacto=None if indice is not None else (str(p['quantidade']),
                  ('contador', 'gavetas_quantidade', int(p['quantidade']), 1,
                   _gavetas.MAXIMO_GAVETAS, alvo, "Drawers")))
    if int(p['quantidade']) > 1:
        itens.append((x, topo - 28, w, 28, "Normalize Heights",
                      ('operador', 'object.cabinet_normalizar_gavetas')))
        topo -= 34
    topo = _titulo_secao(itens, x, topo - ESPACO_SECOES, w, "Front")
    topo = _linha_escolha_gaveta(itens, x, topo - 25, w, '', prop('cobertura') if indice is not None else 'gavetas_cobertura',
                                 _gavetas.OPCOES_COBERTURA, p['cobertura'],
                                 alvo=alvo) + 23
    espacos = ([campo('entre_gavetas_mm',"Between Drawers",p['entre_gavetas_mm'])]
              if indice is None else [campo(nome,rotulo,_gavetas.folgas(p)[k])
                for nome,rotulo,k in (('abaixo_mm',"Below",indice-1),('acima_mm',"Above",indice))
                if 0 <= k < int(p['quantidade'])-1])
    topo = _campos_em_linhas(context, itens, x, topo, w, [
        campo('folga_frontal_mm', "Front Spacing", p['folga_frontal_mm']),
        *espacos,
        campo('recuo_mm', "Inset", p['recuo_mm']),
        campo('espessura_frente_mm', "Thickness", p['espessura_frente_mm']),
        # Front arc sagitta (0 = straight): curved-corner drawer unit.
        campo('frente_curva_mm', "Curve", float(p.get('frente_curva_mm') or 0.0))])
    topo = _titulo_secao(itens, x, topo - ESPACO_SECOES, w, "Rail %d mm" % round(
        _gavetas.curso(gaveta) if gaveta is not None else float(grupo.get(_gavetas.CHAVE_TRILHO_MM, 0.0))))
    topo = _linha_escolha_gaveta(itens, x, topo - 25, w, '', prop('trilho') if indice is not None else 'gavetas_trilho',
                                 _gavetas.OPCOES_TRILHO, p['trilho'],
                                 alvo=alvo) + 23
    # Handle: double click isolates ONE drawer, changing only that one; selecting the
    # group changes all.
    gaveta = obj if _gavetas.MARCA_GAVETA in obj else None
    atual = gaveta.get(_gavetas.CHAVE_PUXADOR, p['puxador']) if gaveta else p['puxador']
    _carrossel_gaveta(itens, x, topo - 23 - ESPACO_SECOES, w,
                      "This Drawer's Handle" if gaveta else "Handle (All)",
                      'gavetas_puxador', _modelos_puxador_gaveta(), atual,
                      alvo=ALVO_PUXADOR_GAVETAS)
    try:
        _gavetas.calcular(largura_vao, altura_vao, p)
    except ValueError as erro:
        itens.append((x, topo - 23 - ESPACO_SECOES - 160, w, 22, str(erro), None))
    return itens


def _botao_criar_puxador():
    """(label, action) for Create Handle at the top of the Handles tab: SAME action
    format as Create Doors (lit = placing)."""
    posicionando = _puxadores._posicionador_puxador[0] is not None
    rotulo = ("Positioning the handle... (Esc cancels)" if posicionando
              else "Create Handle")
    return rotulo, ('criar_puxador', False, posicionando, '', False)


def _divisa_gaveta(context, altura):
    """Height (region y) of the divider between tab and library.

    Between fixed footer and header, always leaving ALTURA_MIN_PAINEL_GAVETA on each
    side; center it when the area is too short for both."""
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
    """Inverse of `_divisa_gaveta`: mouse y becomes the stored fraction."""
    base, topo = ALTURA_RODAPE_GAVETA, altura - 48
    return max(0.0, min(1.0, (y - base) / max(1, topo - base)))


def _paineis_gaveta(conteudo):
    """(tab panel, divider or None, library): content splits at the 'divisa' widget."""
    i = next((i for i, v in enumerate(conteudo)
              if v[5] and v[5][0] == 'divisa'), None)
    if i is None:
        return conteudo, None, []
    return conteudo[:i], conteudo[i], conteudo[i + 1:]


def _reservar_barras_gaveta(context, conteudo, largura, altura, rolagem, rolagem_bib, reservas):
    if not any(reservas):
        return conteudo
    n = _tamanho_cabecalho(conteudo)
    cima, divisa, baixo = _paineis_gaveta(conteudo[n:])
    # Reflow fields and images; covering their ends with the bar stole clicks.
    estreito = _widgets_conteudo_gaveta(context, min(largura, 564) - 12,
                                       altura, rolagem, rolagem_bib)
    menor_cima, _, menor_baixo = _paineis_gaveta(estreito[_tamanho_cabecalho(estreito):])
    return (conteudo[:n] + (menor_cima if reservas[0] else cima)
            + ([divisa] if divisa else []) + (menor_baixo if reservas[1] else baixo))


def _limites_rolagem_gaveta(context, largura, altura):
    """(tab-panel limit, library limit). Each panel scrolls until its final widget
    fully crosses ITS own bottom edge."""
    conteudo = _widgets_conteudo_gaveta(context, largura, altura, 0, 0)
    cima, divisa, baixo = _paineis_gaveta(conteudo[_tamanho_cabecalho(conteudo):])
    piso_bib = 18 + ALTURA_RODAPE_GAVETA
    piso = ((divisa[1] + divisa[3] / 2 + 10) if divisa else piso_bib) + _visibilidade.altura(context)
    limite = max(0, int(piso - min((v[1] for v in cima), default=piso)))
    limite_bib = max(0, int(piso_bib - min((v[1] for v in baixo),
                                           default=piso_bib)))
    conteudo = _reservar_barras_gaveta(context, conteudo, largura, altura, 0, 0,
                                      (limite > 0, limite_bib > 0))
    cima, _, baixo = _paineis_gaveta(conteudo[_tamanho_cabecalho(conteudo):])
    # Reserving the bar may shrink images: avoid layout oscillation at the threshold.
    limite = max(int(limite > 0), int(piso - min((v[1] for v in cima), default=piso)))
    limite_bib = max(int(limite_bib > 0), int(piso_bib - min((v[1] for v in baixo), default=piso_bib)))
    return limite, limite_bib


def _limite_rolagem_gaveta(context, largura, altura):
    return _limites_rolagem_gaveta(context, largura, altura)[0]


def _alca_rolagem(y, altura, limite, atual):
    minimo = min(24, altura / 2) if altura > 16 else altura
    tamanho = min(altura, max(minimo, altura * altura / (altura + limite)))
    base = y + (altura - tamanho) * (1 - max(0, min(limite, atual)) / limite)
    return base, tamanho


def _barras_rolagem_gaveta(context, largura, altura, limites, deslocamentos):
    meio = (_divisa_gaveta(context, altura)
            if context.screen.get(_biblioteca_faixa.CHAVE_LAYOUT) != 2 else None)
    faixas = (((meio + FOLGA_DIVISA_GAVETA if meio is not None else ALTURA_RODAPE_GAVETA) + _visibilidade.altura(context),
               altura - 48, _CHAVE_ROLAGEM),
              (ALTURA_RODAPE_GAVETA, meio - FOLGA_DIVISA_GAVETA if meio is not None else 0,
               _CHAVE_ROLAGEM_BIB))
    x = min(largura - 12, 552) - 8
    return [(x, piso + 4, 8, teto - piso - 8, '', ('rolagem', chave, limite, atual))
            for (piso, teto, chave), limite, atual in zip(faixas, limites, deslocamentos)
            if limite > 0 and teto - piso > 16]


def _rolar_ate_o_fim(context):
    """The tab follows creation: each new wizard step appears at the panel END and,
    with images, used to fall unseen below the divider. Called only on step changes
    so manual scrolling remains effective."""
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
    """A material's Delete? box appears below its row; on lower rows it fell below the
    panel footer, hiding No. Scroll the library only as MUCH as necessary to reveal
    the whole box."""
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
    baixo = _paineis_gaveta(conteudo[_tamanho_cabecalho(conteudo):])[2]
    caixa = next((v for v in baixo if v[5] == ('pergunta',)), None)
    if caixa is None:
        return
    necessario = int(18 + ALTURA_RODAPE_GAVETA - caixa[1]) + 1
    if necessario > int(tela.get(_CHAVE_ROLAGEM_BIB, 0)):
        tela[_CHAVE_ROLAGEM_BIB] = min(limite_bib, necessario)
    area.tag_redraw()


ALTURA_RODAPE_GAVETA = 40      # Fixed gear strip at the sidebar foot.
OP_OPCOES = 'object.cabinet_opcoes_gaveta'


ABAS_GAVETA = (("Modules", "Mod.", 'MODULOS'), ("Doors", "Doors", 'PORTAS'),
               ("Back Panels", "Backs", 'FUNDOS'),
               ("Drawers", "Draw.", 'GAVETAS'), ("Shelves / Partitions", 'Int.', 'PRATELEIRAS'),
               ("Handles", "Handle", 'PUXADORES'), ("Masonry", "Mason.", 'ALVENARIA'))
# Old chain operators remain in F3, outside the header.
OPERADORES_CORRENTE = ()
# Expanded-row count; the narrow header occupies only one widget.
WIDGETS_CABECALHO = len(ABAS_GAVETA) + len(OPERADORES_CORRENTE)
CHAVE_ABAS = 'cabinet_abas_gaveta'


def _aba_no_menu(scene):
    return 'PRATELEIRAS' if scene.cabinet_aba == 'DIVISORIAS' else scene.cabinet_aba


def _no_cabecalho(acao):
    """Navigation stays fixed, including when it becomes a dropdown."""
    return bool(acao) and (acao[0] == 'aba' or acao[:2] == ('suspenso', CHAVE_ABAS) or (
        acao[0] == 'operador' and acao[1] in OPERADORES_CORRENTE))


def _tamanho_cabecalho(widgets):
    # Prefix only: floating-list choices also use 'aba'.
    return next((i for i, v in enumerate(widgets) if not _no_cabecalho(v[5])), len(widgets))


def _cabecalho_gaveta(context, x, y, w):
    aba_w = (w - 4 * (len(ABAS_GAVETA) - 1)) / len(ABAS_GAVETA)
    blf.size(0, 12)
    if any(blf.dimensions(0, curto)[0] + 18 > aba_w for _, curto, _ in ABAS_GAVETA):
        atual = next(rotulo for rotulo, _, aba in ABAS_GAVETA if aba == _aba_no_menu(context.scene))
        aberto = context.screen.get(_CHAVE_SUSPENSO, '') == CHAVE_ABAS
        return [(x, y, w, 29, atual, ('suspenso', CHAVE_ABAS, aberto,
                 CHAVE_ABAS, tuple(a[0] for a in ABAS_GAVETA), atual))]
    return [(x + i * (aba_w + 4), y, aba_w, 29,
             rotulo if blf.dimensions(0, rotulo)[0] + 18 <= aba_w else curto, ('aba', aba))
            for i, (rotulo, curto, aba) in enumerate(ABAS_GAVETA)]


def _widgets_gaveta(context, largura, altura, _rolagem=None,
                    _rolagem_bib=None):
    """Rectangles (x,y,w,h,label,action) shared by drawing and hit-testing.

    Order: header (tabs and chains), tab content, DIVIDER, library, then the fixed
    FOOTER: gear and, when open, the options panel extending upward from it.
    `_partes_gaveta` separates header/content/footer; `_paineis_gaveta` splits
    content at the divider. Each panel scrolls independently."""
    if _biblioteca_faixa.eh_faixa(context):
        return _biblioteca_faixa.widgets(context, largura, altura)
    limite, limite_bib = _limites_rolagem_gaveta(context, largura, altura)
    if _rolagem is None or _rolagem_bib is None:
        if _rolagem is None:
            _rolagem = max(0, min(limite, int(
                context.screen.get(_CHAVE_ROLAGEM, 0))))
        if _rolagem_bib is None:
            _rolagem_bib = max(0, min(limite_bib, int(
                context.screen.get(_CHAVE_ROLAGEM_BIB, 0))))
    itens = _widgets_conteudo_gaveta(context, largura, altura, _rolagem,
                                     _rolagem_bib)
    itens = _reservar_barras_gaveta(context, itens, largura, altura,
        _rolagem, _rolagem_bib, (limite > 0, limite_bib > 0))
    n = _tamanho_cabecalho(itens)
    x, w = 12, max(24, min(540, largura - 24))
    rodape = _rodape_gaveta(context, x, w)
    fixos, lista_opcoes = _separar_flutuante(rodape)
    inicio_opcoes = next((i for i, v in enumerate(fixos) if v[1] >= ALTURA_RODAPE_GAVETA), len(fixos))
    rodape = fixos[:inicio_opcoes] + _visibilidade.widgets(context, x, w, altura) + fixos[inicio_opcoes:] + lista_opcoes
    painel = _retangulo_painel_opcoes(rodape)
    if painel is not None:
        # Content underneath the panel is neither visible nor clickable. The divider
        # remains (drawing clips panels there), but cannot be dragged while covered.
        px, py, pw, ph = painel
        def coberto(v):
            return (v[0] < px + pw and px < v[0] + v[2]
                    and v[1] < py + ph and py < v[1] + v[3])
        itens = itens[:n] + [
            (v[:5] + (('divisa', False),) if coberto(v) else v)
            if v[5] and v[5][0] == 'divisa' else v
            for v in itens[n:]
            if (v[5] and v[5][0] == 'divisa') or not coberto(v)]
    else:
        rodape += _barras_rolagem_gaveta(context, largura, altura,
            (limite, limite_bib), (_rolagem, _rolagem_bib))
    # Lists float above content and handle events first. The cascade stays below the
    # divider; tab navigation opens below the header.
    divisa = next((v for v in itens[n:]
                   if v[5] and v[5][0] == 'divisa'), None)
    lista = _lista_da_cascata(itens[:n], ALTURA_RODAPE_GAVETA, altura)
    if lista:
        # Reuse tab dispatch without navigating the library.
        abas = {rotulo: aba for rotulo, _, aba in ABAS_GAVETA}
        lista = [lista[0]] + [v[:5] + (('aba', abas[v[4]]),) for v in lista[1:]]
    else:
        cima, _, baixo = _paineis_gaveta(itens[n:])
        lista = _lista_da_cascata(cima, divisa[1]+divisa[3] if divisa else ALTURA_RODAPE_GAVETA,
                                  altura-48)
        if not lista:
            lista = _lista_da_cascata(baixo, ALTURA_RODAPE_GAVETA,
                                      divisa[1] if divisa else altura-48)
    if lista:
        fx, fy, fw, fh = lista[0][:4]
        itens = itens[:n] + [
            v for v in itens[n:]
            if (v[5] and v[5][0] == 'divisa') or not (
                v[0] < fx + fw and fx < v[0] + v[2] and v[1] < fy + fh and fy < v[1] + v[3])]
        rodape = rodape + lista
    return itens + rodape


def _widgets_interativos(context):
    """Mouse-receiving widgets from TOPMOST downward: open dropdown, footer/panel,
    header, then content not hidden under the two fixed strips."""
    if _biblioteca_faixa.eh_faixa(context):
        return _biblioteca_faixa.interativos(context)
    altura = context.region.height
    cabecalho, conteudo, rodape = _partes_gaveta(
        _widgets_gaveta(context, context.region.width, altura))
    rodape, flutuante = _separar_flutuante(rodape)
    rodape = [v for v in rodape if v[5] != ('rotulo',)]
    painel = _retangulo_painel_opcoes(rodape)
    if painel:
        px, py, pw, ph = painel
        rodape = [v for v in rodape if not (_visibilidade.eh_acao(v[5]) and
            v[0] < px + pw and px < v[0] + v[2] and v[1] < py + ph and py < v[1] + v[3])]
    if flutuante:
        # Draw the list LAST but handle it FIRST: its background consumes clicks in
        # gaps, while covered rows leave hit-testing (and hover) until it closes.
        fx, fy, fw, fh = flutuante[0][:4]
        rodape = flutuante[1:] + flutuante[:1] + [
            v for v in rodape
            if not (v[0] < fx + fw and fx < v[0] + v[2]
                    and v[1] < fy + fh and fy < v[1] + v[3])]
    # A widget clipped by the divider or fixed strips receives mouse input ONLY in its
    # visible portion (rectangle clipped to the panel). A preset image barely fits in
    # the lower half; requiring the whole widget made both clicks and double clicks on
    # the image ineffective.
    cima, divisa, baixo = _paineis_gaveta(conteudo)
    meio = (divisa[1] + divisa[3] / 2) if divisa else ALTURA_RODAPE_GAVETA
    folga = FOLGA_DIVISA_GAVETA if divisa else 0
    visiveis = ([divisa] if divisa and divisa[5][1] else [])
    for lista, piso, teto in ((cima, meio + folga + _visibilidade.altura(context), altura - 48),
                              (baixo, ALTURA_RODAPE_GAVETA, meio - folga)):
        for v in lista:
            recortado = _recortar_ao_painel(v, piso, teto)
            if recortado is not None:
                visiveis.append(recortado)
    return rodape + [v for v in cabecalho if _no_cabecalho(v[5])] + visiveis


def _recortar_ao_painel(v, piso, teto):
    """Widget mouse target within the panel's [piso, teto] range: whole, clipped to its
    visible portion, or None.

    Icons (drawn by gizmos that ignore clipping) and slider tracks (measured from
    widget height) are valid only when whole."""
    x, y, w, h = v[:4]
    if y >= piso and y + h <= teto:
        return v
    if _gaveta_eventos._icone_acao_gaveta(v[5]) or (v[5] and v[5][0] == 'slider'):
        return None
    baixo, alto = max(y, piso), min(y + h, teto)
    if alto - baixo < 8:        # Sliver: too small to target.
        return None
    return (x, baixo, w, alto - baixo) + tuple(v[4:])


def _separar_flutuante(rodape):
    """(footer, dropdown): the list starts at the 'fundo' widget."""
    inicio = next((i for i, v in enumerate(rodape)
                   if v[5] and v[5][0] == 'fundo'), len(rodape))
    return rodape[:inicio], rodape[inicio:]


def _partes_gaveta(widgets):
    """(header, content, footer): the footer starts at the gear."""
    inicio = next((i for i, v in enumerate(widgets)
                   if v[5] == ('operador', OP_OPCOES)), len(widgets))
    n = _tamanho_cabecalho(widgets)
    return (widgets[:n], widgets[n:inicio],
            widgets[inicio:])


def _retangulo_painel_opcoes(rodape):
    """Options-panel background (x, y, w, h), or None when closed."""
    # The fixed footer row (gear, Create Doors) is outside the panel.
    painel = [v for v in _separar_flutuante(rodape)[0]
              if v[1] >= ALTURA_RODAPE_GAVETA and not _visibilidade.eh_acao(v[5])
              and v[5] != ('rotulo',)
              and not (v[5] and v[5][0] == 'rolagem')]
    if not painel:
        return None
    folga = 8
    x0 = min(v[0] for v in painel) - folga
    y0 = min(v[1] for v in painel) - folga
    x1 = max(v[0] + v[2] for v in painel) + folga
    y1 = max(v[1] + v[3] for v in painel) + folga
    return x0, y0, x1 - x0, y1 - y0


def _rodape_gaveta(context, x, w):
    """Gear at the sidebar foot and, when open, the panel extending upward from it.

    The sidebar draws the panel itself (bpy popups close when the mouse leaves; see
    DESIGN.md). One row per option: label left, control right; stack only in narrow
    sidebars. 'suspenso' opens the floating list, 'faixa' supports dragging or
    typing (`_opcoes.FAIXAS_OPCOES`), and 'cor' opens an inline picker, pushing the
    panel upward. Everything saves to add-on preferences."""
    rodape = [(x, 7, 26, 26, '', ('operador', OP_OPCOES))]
    if _solda._conexao_manual[0] is not None and not _solda._conexao_manual[0].get('moderna'):
        # Choosing vertices: footer becomes Confirm, equivalent to Enter.
        rodape.append((x + 32, 7, w - 32, 26, "Confirm Connection (Enter)",
                       ('operador', 'object.cabinet_confirmar_conexao')))
    elif context.screen.get(_biblioteca_faixa.CHAVE_LAYOUT) != 2:
        # Library inside the menu: its footer returns it to the strip. The header has no
        # room without displacing Cabinets | Materials.
        rodape.append((x + 32, 7, 26, 26, '', ('operador', _biblioteca_faixa.OP_LUGAR)))
    tela = context.screen
    if not tela.get(_CHAVE_OPCOES):
        return rodape
    suspenso = tela.get(_CHAVE_SUSPENSO, '')
    cor_aberta = tela.get(_CHAVE_COR, '')
    largo = w >= 250 * max(1.0, context.preferences.system.ui_scale)
    rot_w = (w - 6) / 2 if largo else w
    cx, cw = (x + rot_w + 6, w - rot_w - 6) if largo else (x, w)
    painel = [(x, 0, w, 20, "Options", None)]
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
                # List directly below the field, over subsequent rows (hence lists
                # appear in the first rows).
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
            texto = {'TEMA': "Theme", 'GIZMO': 'Gizmo'}.get(especial) or (
                '#%02X%02X%02X' % tuple(round(c * 255) for c in rgb))
            painel.append((cx, y, cw, 25, texto,
                           ('cor', nome, 'amostra', rgb, cor_aberta == nome,
                            especial)))
            if cor_aberta == nome:
                y = _seletor_cor_gaveta(painel, x, y - 29, w, nome, rgb,
                                        especial)
        y -= 29
    _botao_orcamento_opcoes(painel, x, y, w)
    # Build downward from 0, then shift up to sit just above the gear: the panel opens
    # from bottom to top.
    deslocar = ALTURA_RODAPE_GAVETA + 8 - min(v[1] for v in painel)
    return rodape + [(v[0], v[1] + deslocar, *v[2:])
                     for v in painel + flutuante]


# (label, control, option): dropdowns come FIRST, opening downward over subsequent rows,
# which must be below them.
LINHAS_OPCOES = (
    ("Default unit", 'suspenso', 'unidade_padrao'),
    ("Blender Outline", 'suspenso', 'ocultar_contorno_grupo'),
    ("Group Origins", 'suspenso', 'ocultar_origens_grupo'),
    ("Support dots", 'suspenso', 'hud_pontos_apoio'),
    ("Corner guides", 'suspenso', 'hud_setas_quinas'),
    ("Links", 'suspenso', 'tecla_corrente'),
    ("Line thickness", 'faixa', 'hud_espessura_linha'),
    ("Label size", 'faixa', 'hud_tamanho_rotulo'),
    ("Line color", 'cor', 'hud_rgb_linha'),
    ("Highlight color", 'cor', 'hud_rgb_realce'),
)
SUSPENSOS_OPCOES = {
    'unidade_padrao': tuple((k, v[1]) for k, v in _opcoes.UNIDADES_MEDIDA.items()),
    'ocultar_contorno_grupo': ((True, "Hide"), (False, "Show")),
    'ocultar_origens_grupo': ((True, "Hide"), (False, "Show")),
    'hud_pontos_apoio': ((True, "On"), (False, "Off")),
    'hud_setas_quinas': ((True, "On"), (False, "Off")),
    'tecla_corrente': (('ALT', "Hold Alt"), ('CTRL', "Hold Ctrl"),
                       ('SHIFT', "Hold Shift"), ('SEMPRE', "Always")),
}
ALTURA_QUADRO_COR = 96
# Hue for each color option: gray/white/black have no hue. Without this, the square
# reverted to red when dragging along the saturation axis.
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
    """Track position (0..1) -> option value at its step size."""
    minimo, maximo, passo = _opcoes.FAIXAS_OPCOES[nome]
    fracao = max(0.0, min(1.0, fracao))
    valor = round((minimo + fracao * (maximo - minimo)) / passo) * passo
    valor = max(minimo, min(maximo, valor))
    return int(valor) if isinstance(minimo, int) else float(valor)


def _cor_do_seletor(nome, parte, rgb, fx, fy):
    """Clicked point in the square (fx=saturation, fy=brightness) or hue strip."""
    h, s, v = _hsv_opcao(nome, rgb)
    fx, fy = max(0.0, min(1.0, fx)), max(0.0, min(1.0, fy))
    if parte == 'matiz':
        h = _matiz_cor[nome] = fx
    else:
        s, v = fx, fy
    return colorsys.hsv_to_rgb(h, s, v)


def _aplicar_cor_opcao(nome, rgb):
    # Choosing a color disables Theme / Gizmo for that option.
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
    """'TEMA' (theme-colored lines), 'GIZMO' (per-axis highlighting) or ''."""
    if nome == 'hud_rgb_linha' and _opcoes._opcao('hud_linha_tema'):
        return 'TEMA'
    if nome == 'hud_rgb_realce' and _opcoes._opcao('hud_realce_gizmo'):
        return 'GIZMO'
    return ''


# Shortcut representing more than one color: first in each option's row.
ATALHO_ESPECIAL = {'hud_rgb_linha': 'TEMA', 'hud_rgb_realce': 'GIZMO'}
OPCAO_DO_ESPECIAL = {'TEMA': 'hud_linha_tema', 'GIZMO': 'hud_realce_gizmo'}


def _seletor_cor_gaveta(painel, x, y, w, nome, rgb, especial):
    """Shortcuts, saturation x brightness square and hue strip below the sample. Return
    the last occupied row's y (the loop descends by 29)."""
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
    # The loop descends by 29; the next row (25) sits 4 px below the hue strip.
    return base - 20


def _widgets_conteudo_gaveta(context, largura, altura, _rolagem,
                             _rolagem_bib=0):
    """Header + tab panel + divider + library."""
    itens = _widgets_aba_gaveta(context, largura, altura, _rolagem)
    if context.screen.get(_biblioteca_faixa.CHAVE_LAYOUT) == 2:
        return itens
    x, w = 12, max(24, min(540, largura - 24))
    divisa = _divisa_gaveta(context, altura)
    # Draw the line edge to edge; its grab rectangle stays within the margins like every
    # widget (section 6 golden rule).
    itens.append((x, divisa - FOLGA_DIVISA_GAVETA, w,
                  2 * FOLGA_DIVISA_GAVETA, '', ('divisa', True)))
    _biblioteca_gaveta(context, itens, x, divisa - 34 + _rolagem_bib, w)
    return itens


def _widgets_aba_gaveta(context, largura, altura, _rolagem):
    s = context.scene
    # Even if the area is drastically widened, the menu remains a readable vertical
    # column; thumbnails do not become giant strips.
    x, w = 12, max(24, min(540, largura - 24))
    itens = _cabecalho_gaveta(context, x, altura - 40, w)
    metade = (w - 6) / 2
    y = altura - 105 + _rolagem
    if _areas_criacao._estado[0] is not None:
        return _areas_criacao.widgets(context, itens, x, y + 54, w)
    pergunta = _perguntas._pergunta_atual[0]
    if pergunta and (pergunta.get('internos') or pergunta.get('portas_internos')) and pergunta['na_gaveta']:
        _pergunta_na_gaveta(itens, x, y + 54, w, pergunta)
        return itens
    solda=_solda._conexao_manual[0]
    if solda is not None and solda.get('moderna'):
        return _painel_criacao_solda(context,itens,x,y+54,w,solda)
    if s.cabinet_aba == 'ALVENARIA':
        instalacao = _alvenaria.grupo_de(context.object)
        if instalacao is not None:
            if instalacao.get(_alvenaria.MARCA) == 'REBAIXO':
                y = _titulo_secao(itens, x, y+26, w, instalacao.name)
            else:
                y = _alvenaria.widgets(context, itens, x, y, w)
            _instalacoes.widgets(context, itens, x, y, w, instalacao)
        else:
            _alvenaria.painel(context, itens, x, y, w)
        return itens
    if s.cabinet_aba == 'MODULOS' and _alvenaria.candidatos(context):
        y = _alvenaria.widgets_classificar(context, itens, x, y+30, w)-58
    if s.cabinet_aba in {'PORTAS', 'FUNDOS', 'GAVETAS', 'PRATELEIRAS', 'DIVISORIAS', 'PUXADORES'}:
        # Create Doors at the tab TOP, directly below the tabs, full width with centered
        # text (user backlog, Epic 2.3); previously in the fixed footer beside the gear.
        # Create Handle follows the SAME pattern (user request).
        rotulo, acao = (_botao_criar_portas(context)
                        if s.cabinet_aba == 'PORTAS'
                        else ("Create Back Panel", ('operador', 'object.cabinet_criar_fundo')) if s.cabinet_aba == 'FUNDOS'
                        else _botao_criar_gavetas() if s.cabinet_aba == 'GAVETAS'
                        else _botao_criar_prateleiras() if s.cabinet_aba == 'PRATELEIRAS'
                        else ("Marking the opening... (Esc cancels)" if _divisorias._criando() else "Create Partitions",
                              ('divisorias', False, _divisorias._criando(), '', False)) if s.cabinet_aba == 'DIVISORIAS'
                        else _botao_criar_puxador())
        if s.cabinet_aba in {'PRATELEIRAS', 'DIVISORIAS'} and not (_prateleiras._criando() or _divisorias._criando()):
            rotulo, acao = "Create Shelves or Partitions", ('operador', 'object.cabinet_internos')
        topo_criar = altura - 48 - 8 - 30 + _rolagem
        itens.append((x, topo_criar, w, 30, rotulo, acao))
        y -= 38
        if _areas_criacao.oferecer(context):
            rotulo = "Define by Plane" if s.cabinet_aba in {'PORTAS', 'FUNDOS'} else "Define by Volume"
            itens.append((x, y + 26, w, 30, rotulo, ('operador', 'object.cabinet_definir_area')))
            y -= 36
    if s.cabinet_aba == 'MODULOS':
        y = _paredes_edicao.widgets(context, itens, x, y, w)
    # Each tab shows ONLY what applies to selection (user request): the dimension block
    # belongs to the item's owner tab, rather than being fixed across all three.
    if s.cabinet_aba == 'PORTAS':
        return _aba_portas_gaveta(context, itens, x, y, w, s, largura, metade)
    if s.cabinet_aba == 'FUNDOS':
        return _fundos.widgets(context, itens, x, y, w)
    if s.cabinet_aba == 'PUXADORES':
        return _aba_puxadores_gaveta(context, itens, x, y, w, s, largura,
                                     metade)
    if s.cabinet_aba == 'GAVETAS':
        return _aba_gavetas_gaveta(context, itens, x, y, w)
    if s.cabinet_aba in {'PRATELEIRAS', 'DIVISORIAS'}:
        if _divisorias._criando() or _divisorias.grupo_de(_selecionado(context)) is not None:
            return _aba_divisorias_gaveta(context, itens, x, y, w)
        return _aba_prateleiras_gaveta(context, itens, x, y, w)
    return _aba_modulos_gaveta(context, itens, x, y, w, largura, metade)


def _aba_modulos_gaveta(context, itens, x, y, w, largura, metade):
    """Selected cabinet or panel: dimensions (Individual | Group), Assembly and room;
    external object: its dimensions. No selection: nothing (the library below
    handles creation for this tab; the scene-wide estimate lives in Options)."""
    obj = _selecionado(context)
    if _paredes_composicao.parede(obj) or (_paredes_edicao.ativa(context)
                                          and _paredes.modulo_de(obj) is not None):
        return itens
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
    itens.append((x, y, w, 23, "Assembly", None))
    y -= 31
    if nosso:
        itens.append((x, y, w, 28, "Create Weld",
                      ('operador', 'object.cabinet_conectar_vertices')))
        y -= 34
    # No Recalculate button: the handler already normalizes panels after every S/G, so
    # the button only repeated it (user request). The magnet (Adjacency) became the
    # CHAIN: with one object selected, blue means attached (click detaches), gray means
    # unattached (click associates); with multiple objects, connect by distance.
    # Creation has its own entry because an attached part's chain detaches it.
    # Group/Convert remain in F3.
    montagem = (("Link", _solda.OP_CORRENTE_OBJETO),
                ("Reset Distance", _solda.OP_RESETAR_DISTANCIA))
    colunas = 2 if w >= 240 else 1
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
    aviso=_solda.diagnostico_soldas(obj)
    if aviso:
        y-=31;itens.append((x,y,w,26,aviso,None))
        y-=26;itens.append((x,y,w,26,"Create another weld to repair",None))
    pergunta = _perguntas._pergunta_atual[0]
    if (pergunta is not None and pergunta['na_gaveta']
            and not pergunta.get('comodo') and not pergunta.get('biblioteca')):
        y = _pergunta_na_gaveta(itens, x, y - 6, w, pergunta)
    return _secao_orcamento_gaveta(context, itens, x, y - 40, w)


def _painel_criacao_solda(context,itens,x,topo,w,estado):
    topo=_titulo_secao(itens,x,topo,w,"Create Weld")
    recado={'origem':"1. Choose the source anchor",
            'destino':"2. Choose the end anchor",
            'confirmar':"Create this weld?"}[estado['fase']]
    itens.append((x,topo-26,w,26,recado,None));topo-=34
    valor=(estado['distancias'][-1] if estado['pares'] else estado.get('distancia_previa') or 0.)*1000
    topo=_campos_em_linhas(context,itens,x,topo,w,[
        ("Distance: "+_opcoes._texto_medida(valor),('medida','solda_criacao','distancia',"Distance",valor))])
    if estado['pares']:
        for rotulo,comando in (("Reset Distance",'RESETAR'),("Previous Step",'VOLTAR')):
            itens.append((x,topo-28,w,28,rotulo,('escolha','solda_acao',comando,False,True,'@solda')));topo-=34
        if estado['fase']=='confirmar':
            itens.append((x,topo-28,w,28,"Add Another Pair",('escolha','solda_acao','ADICIONAR',False,True,'@solda')));topo-=34
            itens.append((x,topo-28,w,28,"Create Weld",('operador','object.cabinet_confirmar_conexao')));topo-=34
    itens.append((x,topo-28,w,28,"Cancel Weld",('escolha','solda_acao','CANCELAR',False,True,'@solda')))
    itens.append((x,topo-62,w,26,"Alt: edit anchor",None))
    itens.append((x,topo-88,w,26,"Right click / Esc: cancel",None))
    itens.append((x,topo-114,w,26,"Backspace / Ctrl+Z: back",None))
    return itens


def _secao_orcamento_gaveta(context, itens, x, y, w):
    """Selected cabinet's ROOM, used to group the estimate (ONE expandable row; user
    request: the fixed grid occupied the tab). Generate Estimate applies to the
    entire scene and lives in Options."""
    modulos = _orcamento._modulos_da_selecao(context)
    if not modulos:
        return itens
    # Assembly-style title without a separator (tab separators belong to the cascade).
    itens.append((x, y, w, 23, "Estimate", None))
    y -= 31
    ativo = _orcamento._modulo_do_objeto(context.object) or modulos[0]
    atual = _orcamento._nome_comodo(_orcamento._comodo_do_modulo(ativo))
    aberto = context.screen.get(_CHAVE_SUSPENSO, '') == _orcamento.SUSPENSO_COMODO
    itens.append((x, y, w, 25, "Room: %s" % (atual or "(none)"),
                  ('suspenso', _orcamento.SUSPENSO_COMODO, aberto)))
    y -= 29
    if aberto:
        # Open the list INSIDE the tab, pushing subsequent content down.
        opcoes = [(n, n) for n in _orcamento._comodos_da_lista(context.scene)]
        if atual:
            opcoes.append((_orcamento.COMODO_NENHUM, "No Room"))
        opcoes.append((_orcamento.COMODO_OUTRO, "Other Name..."))
        y = _linha_escolha_gaveta(
            itens, x, y, w, '', _orcamento.ALVO_COMODO, tuple(opcoes), atual,
            alvo=_orcamento.ALVO_COMODO, por_linha=3 if w >= 300 else 2)
    pergunta = _perguntas._pergunta_atual[0]
    if pergunta is not None and pergunta.get('comodo'):
        _pergunta_na_gaveta(itens, x, y + 23, w, pergunta)
    return itens


def _botao_orcamento_opcoes(painel, x, y, w):
    """Generate Estimate at the end of Options (user request: the add-on is sold as a
    product, not tied to a single ERP). Open Save As and write the .txt; show the
    result on the button and any outstanding issues in a black box immediately
    below. Return the bottom y."""
    gerado = _orcamento._orcamento_gerado[0]
    rotulo = "Generate Estimate (.txt)"
    if gerado is not None:
        rotulo = "Saved: %d cabinet(s) - generate again" % gerado['modulos']
    y -= 6
    painel.append((x, y, w, 28, rotulo,
                   ('operador', _orcamento.OP_EXPORTAR_ORCAMENTO, gerado is not None)))
    if gerado is not None and gerado['pendencias']:
        texto = 'Pending items:\n' + '\n'.join(
            '\n'.join(_quebrar_texto(p, w - 20))
            for p in gerado['pendencias'])
        linhas = texto.count('\n') + 1
        altura = 12 + 15 * linhas + 4
        y -= 6 + altura
        painel.append((x, y, w, altura, texto, ('pergunta',)))
    return y


PX_CARACTERE_PERGUNTA = 6.4      # Estimated character width (11 px text).


def _quebrar_texto(texto, largura):
    """Lines fitting within `largura` px (bpy does not measure text outside drawing:
    estimate per character, like sidebar PX_* constants)."""
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


LARGURA_MIN_RESPOSTA = 70   # Pixels: below this width, answers wrap to another row.


def _pergunta_na_gaveta(itens, x, topo, w, pergunta):
    """Black box with the question and side-by-side answers, starting at `topo` just
    below the initiating button. Return the bottom y."""
    texto = pergunta['texto']
    estado = _solda._nome_grupo_gaveta[0]
    if pergunta.get('campo') and estado is not None:
        # Typed name with cursor (Enter confirms).
        texto += ': ' + _gaveta_desenho._com_cursor(estado['texto'], estado['cursor'])
    linhas = _quebrar_texto(texto, w - 20)
    n = len(pergunta['opcoes'])
    # Many answers (quick-paint rooms) wrap into rows.
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


# Icons right of the title, by library: presets (folder, Asset Browser, save selection)
# or materials (folder, new material).
BOTOES_BIBLIOTECA = {
    # Assets (the native shelf) was discontinued at the user's request.
    'MODULOS': (("Folder", 'object.cabinet_abrir_biblioteca'),
                ("Save +", 'object.cabinet_salvar_biblioteca')),
    'MATERIAIS': (("Folder", 'object.cabinet_abrir_biblioteca'),
                  ("New +", 'object.cabinet_novo_material')),
}
TITULO_BIBLIOTECA = "Library"
MODOS_BIBLIOTECA = (('MODULOS', "Modules"), ('MATERIAIS', "Materials"))


def _cabecalho_biblioteca(context, itens, x, y, w, contagens):
    """Title with Cabinets | Materials buttons BESIDE it (user request; below it in a
    narrow sidebar) and icons on the right. Each library's button carries its count.
    Return the next y."""
    modo = context.scene.cabinet_bib_modo
    botoes = BOTOES_BIBLIOTECA[modo]
    bw = min(28, max(12, (w - 44) / 3))
    reserva = len(botoes) * (bw + 4)
    largura_titulo = _px_botao(TITULO_BIBLIOTECA, False)
    sobra = w - reserva - largura_titulo - 4
    ao_lado = sobra >= 2 * PX_MIN_NIVEL + 4
    # The title is the panel's FIRST widget (the scrolling test locates it).
    itens.append((x, y, largura_titulo if ao_lado else max(1, w - reserva), 26,
                  TITULO_BIBLIOTECA, None))
    for i, (rotulo, op) in enumerate(botoes):
        itens.append((x + w - reserva + 4 + i * (bw + 4), y, bw, 26, rotulo,
                      ('operador', op)))
    if ao_lado:
        # Segment (25) centered on the title (26).
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
    """Library in the lower panel, identical across all three tabs and always open: the
    title no longer toggles it. Two libraries with the same cascade: presets
    (Cabinets) and Materials."""
    s = context.scene
    indice = _biblioteca.indice_completo()
    materiais = _materiais.ler_materiais()
    y = _cabecalho_biblioteca(context, itens, x, y, w,
                              {'MODULOS': len(indice), 'MATERIAIS': len(materiais)})
    if s.cabinet_bib_modo == 'MATERIAIS':
        return _materiais_gaveta(context, itens, x, y, w, materiais)
    # Factory items (handles, hinges) enter the cascade locked.
    indice = indice + _biblioteca.itens_de_fabrica()
    # UNLIMITED cascade depth (user request): one carousel per level of the chosen path,
    # plus its child level while children exist (Cabinets > Kitchen > Tall Units >
    # Pantries). Hide empty branches.
    trilha = _biblioteca.trilha_da_cena(s)
    for nivel in range(1, len(trilha) + 2):
        pai = trilha[:nivel - 1]
        filhos = _biblioteca.filhos_de(indice, pai)
        if not filhos:
            break
        if nivel > 1:
            itens.append((x, y + 31.5, w, 1, '', ('separador',)))
        # Level 1 parent is None (the existing scroll key); level 2 uses level 1's name;
        # level 3 onward uses a tuple.
        chave_pai = None if nivel == 1 else (pai[0] if nivel == 2 else tuple(pai))
        y = _linha_cascata_gaveta(itens, x, y, w, filhos, nivel,
                                  trilha[nivel - 1] if len(trilha) >= nivel else '',
                                  indice, chave_pai)
        if len(trilha) < nivel:
            break
    daqui = _biblioteca.itens_em(indice, trilha) if trilha else []
    if daqui:
        itens.append((x, y, min(w, 290), 26, "Thumbnail Size",
                      ('slider', None)))
        y -= 12
        daqui.sort(key=lambda it: it.get('nome', '').casefold())
        bw, colunas, altura_bloco = _grade_biblioteca(s, w)
        # Insert/Edit/Lock: RIGHT-click the image, like the strip (user request); no
        # button row beneath each cabinet.
        for i, it in enumerate(daqui):
            linha, coluna = divmod(i, colunas)
            bx = x + coluna * (bw + 8)
            by = y - altura_bloco - linha * (altura_bloco + 8)
            itens.append((bx, by, bw, altura_bloco,
                          _abreviar(it.get('nome', ''), 17), ('preset', it)))
    return itens


def _grade_biblioteca(s, w):
    """(block side, columns, block height) for the thumbnail grid, shared by presets
    and materials (Thumbnail Size slider). Images never inherit sidebar width: they
    remain square."""
    lado_foto = 88 + (s.chapa_tam_bloco - 2) * 14
    bw = min(w, lado_foto + 10)
    return bw, max(1, int((w + 8) // (bw + 8))), bw + 17


def _materiais_gaveta(context, itens, x, y, w, materiais):
    """Materials cascade (MDF/MDP > category), followed by the sphere grid: clicking
    paints selection (`cabinet_aplicar_material`), with Edit and Delete beneath each
    sphere. Highlight the selection's material sphere. Delete? opens directly below
    the material row."""
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
    itens.append((x, y, min(w, 290), 26, "Thumbnail Size",
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
            for j, rotulo in enumerate(('Edit.', "Delete")):
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
        # Doors have width, height and thickness, but no depth.
        rotulo('A', _biblioteca._meio_wireframe(pontos[2], pontos[6]), -13)
        rotulo('E', _biblioteca._meio_wireframe(pontos[0], pontos[2]), -12, -8)
    else:
        rotulo('A', _biblioteca._meio_wireframe(pontos[2], pontos[6]), -13)
        # With the door along X, the upper edge measures cabinet depth and the receding
        # edge measures width.
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
        _texto_gaveta(x + 8, y + h / 2, "No Photo", 11)
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
                # RGBA PNG: preserve alpha without flattening against a color. Preview
                # PNGs do not need 32 bits per channel: on wide screens RGBA8 keeps the
                # entire row cached without thrashing. The API accepts only FLOAT Buffer
                # even with RGBA8 texture storage (GPU conversion).
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
        print("[Archy Builder] sidebar photo:", e)
        _texto_gaveta(x + 8, y + h / 2, "Photo Unavailable", 11)


def _trilho_miniaturas_gaveta(x, y, w, h):
    # Drawing and dragging share the same bounds, excluding the label.
    rotulo = min(145, w * 0.52)
    return x + rotulo + 8, y + h / 2, max(1, w - rotulo - 14)


def _trilho_slider_gaveta(acao, x, y, w, h):
    """(start, y, width) of any slider track: images (no label, full widget) or library
    thumbnails."""
    if acao[1] in {'retratos', 'instalacao'}:
        return x + 10, y + h / 2, max(1, w - 20)
    return _trilho_miniaturas_gaveta(x, y, w, h)


def _animar_realces():
    areas = {a.as_pointer(): a for janela in bpy.context.window_manager.windows
             for a in janela.screen.areas if a.type == 'VIEW_3D' or _editor.eh_editor(a)}
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
    return 1.0 / 60 if animando else None


def _eh_area_gaveta_bruto(area):
    """Variant of `_eh_area_gaveta` accepting a standalone area."""
    if _editor.eh_editor(area):
        return True
    for janela in bpy.context.window_manager.windows:
        if area in janela.screen.areas.values():
            return area in (_area_gaveta(janela.screen),
                            _biblioteca_faixa.area_da_faixa(janela.screen))
    return False


def _realcar(context, nome, ativo):
    """Turn a widget's glow on or off with a transition."""
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
    """Highlighted widget halo, centralized so handles and buttons glow identically.

    Enable ALPHA explicitly: `blf.draw` changes blending state; without this, the
    second and subsequent halos were OPAQUE white blocks covering button text."""
    if realce <= 0.0:
        return
    gpu.state.blend_set('ALPHA')
    for margem, alfa in ((6, 0.025), (4, 0.045), (2, 0.07)):
        _retangulo_arredondado_gaveta(
            x - margem, y - margem, w + 2 * margem, h + 2 * margem,
            raio + margem, (*cor, alfa * realce),
            esquerda_reta=esquerda_reta)
