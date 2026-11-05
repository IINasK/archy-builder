"""Door creation wizard (two clicks plus choice boxes) and the
parametric door operator."""

import bpy, gpu, blf
from gpu_extras.batch import batch_for_shader
from bpy.props import (FloatProperty, BoolProperty, EnumProperty,
                       StringProperty, IntProperty, FloatVectorProperty)
from mathutils import Matrix, Vector
from bpy_extras import view3d_utils
from bpy.types import Operator
_opcoes = None

# Used at LOAD time (class bodies/constants): already loaded earlier.
from .. import chapas as _chapas
from .. import portas as _portas
# Used only at runtime (circular imports): __init__ binds these
# aliases after loading all modules (`_ligar_modulos`).
_eventos = _ferragens = _gaveta_eventos = _arame = _gaveta = _hud = None
_modulos = None
_gavetas = None
_areas_criacao = None

PX_CARACTERE_ASSISTENTE = 7.0    # Estimated width of a 12 px character.
MARGEM_CAIXA_ASSISTENTE = 10.0   # Pixels between the box and viewport edge.


def _botoes_assistente(ancora, opcoes, escala, tamanho=None, pergunta=''):
    """Choice-box buttons beside `ancora` (pixels).

    `tamanho` is region (width, height). The ENTIRE box, with its question
    above the buttons, must fit: completing a door near the edge used to
    clip it. Place left of the mouse if there is no room on the right;
    move up/down near the bottom/top."""
    largura, altura, vao = 150 * escala, 26 * escala, 6 * escala
    x, y = ancora.x + 18 * escala, ancora.y - 14 * escala
    colunas, linhas = 1, len(opcoes)
    if tamanho is not None:
        margem = MARGEM_CAIXA_ASSISTENTE * escala
        cabecalho = (8 + 12 + 4) * escala if pergunta else 0
        if len(opcoes) > 4:
            # Eight leaves in a short viewport require multiple columns.
            disponivel = max(1, tamanho[0] - 2 * margem)
            cabem = max(1, int((tamanho[1] - 2 * margem - cabecalho + vao) / (altura + vao)))
            colunas = min((len(opcoes) + cabem - 1) // cabem,
                          max(1, int((disponivel + vao) / (72 * escala + vao))))
            linhas = (len(opcoes) + colunas - 1) // colunas
            largura = min(largura, (disponivel - vao * (colunas - 1)) / colunas)
            altura = min(altura, max(1, (tamanho[1] - 2 * margem - cabecalho - vao * (linhas - 1)) / linhas))
        # The question text can be wider than the buttons.
        bloco = min(tamanho[0] - 2 * margem, max(colunas * largura + (colunas - 1) * vao,
                     (len(pergunta) * PX_CARACTERE_ASSISTENTE + 8) * escala))
        if x + bloco > tamanho[0] - margem:
            x = ancora.x - 18 * escala - bloco
        x = max(margem, min(x, tamanho[0] - margem - bloco))
        fundo = y - (linhas - 1) * (altura + vao)
        topo = y + altura + ((8 + 12 + 4) * escala if pergunta else 0)
        if fundo < margem:
            y += margem - fundo
        elif topo > tamanho[1] - margem:
            y -= topo - (tamanho[1] - margem)
    return [((x + (i // linhas) * (largura + vao), y - (i % linhas) * (altura + vao), largura, altura), chave, texto)
            for i, (chave, texto) in enumerate(opcoes)]


def _botao_sob(botoes, mouse):
    for (x, y, w, h), chave, _t in botoes:
        if x <= mouse.x <= x + w and y <= mouse.y <= y + h:
            return chave
    return None


def _desenhar_assistente_2d(estado):
    """Choice box, snap dots and step prompt."""
    if estado is None:
        return
    regiao = getattr(bpy.context, 'region', None)
    if regiao is None or regiao.as_pointer() != estado['regiao']:
        return
    escala = max(1.0, bpy.context.preferences.system.ui_scale)
    realce = _hud._cor_realce_hud()
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        for ponto in estado.get('bolinhas', ()):
            _hud._bolinha_2d(shader, ponto, 6 * escala, (1.0, 1.0, 1.0, 1.0))
        if estado.get('snap_tela') is not None:
            _hud._bolinha_2d(shader, estado['snap_tela'], 9 * escala, realce)
            _hud._bolinha_2d(shader, estado['snap_tela'], 6 * escala,
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
            _hud._caixa_texto_hud(x, y + h + 8 * escala, estado['pergunta'],
                             12 * escala, escala)
        # With a box open, its question is already above it; the mouse prompt
        # would cover the second button.
        if (estado.get('recado') and estado.get('mouse') is not None
                and not estado.get('botoes')):
            # Keep the prompt unclipped too: move it to the other side of the
            # mouse near an edge (blf measures it here, during drawing).
            blf.size(0, 12 * escala)
            largura = blf.dimensions(0, estado['recado'])[0]
            margem = MARGEM_CAIXA_ASSISTENTE * escala
            x = estado['mouse'].x + 20 * escala
            if x + largura > regiao.width - margem:
                x = estado['mouse'].x - 20 * escala - largura
            x = max(margem, min(x, regiao.width - margem - largura))
            y = estado['mouse'].y - 30 * escala
            if y < margem:
                y = estado['mouse'].y + 20 * escala
            y = max(margem, min(y, regiao.height - margem - 12 * escala))
            _hud._caixa_texto_hud(x, y, estado['recado'], 12 * escala, escala)
    finally:
        gpu.state.blend_set('NONE')


class OBJECT_OT_apanhar_vao_portas(Operator):
    """Mark two opening corners in the viewport with vertex snapping."""
    bl_idname = "object.cabinet_apanhar_vao"
    bl_label = "Capture Door Opening"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    # ------------------------------------------------ snapping
    def _mouse_na_regiao(self, event):
        # Capture usually starts from the sidebar, a different area:
        # mouse_region_* would refer to the sidebar rather than the viewport.
        return Vector((event.mouse_x - self._regiao.x,
                       event.mouse_y - self._regiao.y))

    def _imantar(self, event):
        """Use NATIVE snap points (the cursor from `cabinet_marcar_ponto_vao`,
        as in `gavetas.AssistenteDoVao`). Previously each click read all
        visible meshes and every mouse move projected every vertex in Python."""
        w = getattr(self, '_w', None) or {}
        cursor = w.get('cursor')
        self._imantado = cursor.copy() if cursor is not None else None
        self._objeto_imantado = bpy.data.objects.get(w.get('cursor_obj') or '')

    # ------------------------------------------------ preview
    def _referencia(self, obj_a, obj_b):
        """Use the operator's eventual axes: the cabinet's common parent axes,
        or world axes for a loose door."""
        if not OBJECT_OT_apanhar_vao_portas._associar(self, bpy.context):
            return Matrix.Identity(3)
        return _portas._referencia_do_par(obj_a, obj_b)[0]

    def _associar(self, context):
        """The chain determines cabinet attachment: the repositioned door's
        chain, or the scene chain for a new door."""
        alvo = bpy.data.objects.get(getattr(self, '_grupo_alvo', '') or '')
        if alvo is not None:
            return bool(alvo.get(_portas.CHAVE_MODULO_PORTA))
        return bool(getattr(context.scene, 'porta_associar', True))

    def _centro(self, obj_a, obj_b):
        """Interior cabinet point used to determine which face points outward."""
        return _portas._centro_do_movel(obj_a, obj_b)

    def _cliques(self):
        """Creation and repositioning share the same diagonal."""
        return 2

    def _cantos_marcados(self):
        """Clicked points, plus the point under the cursor during capture.
        Called through the class because tests use a fake operator."""
        marcados = list(self._pontos)
        etapa = (getattr(self, '_w', None) or {}).get('etapa', 'DIAGONAL')
        if (etapa == 'DIAGONAL' and self._imantado is not None
                and len(marcados) < OBJECT_OT_apanhar_vao_portas._cliques(self)):
            marcados.append((self._imantado, self._objeto_imantado))
        return marcados

    def _previa(self):
        """Leaf boxes from the diagonal, including the point under the cursor.

        Use TAB parameters rather than fixed defaults: the drag preview must
        match the door to be created. If calculation fails, store the reason
        in `_recado`; the preview used to disappear without explanation.
        """
        tipo = OBJECT_OT_apanhar_vao_portas
        self._recado = ''
        marcados = tipo._cantos_marcados(self)
        portas = None
        if len(marcados) >= 4:
            # Preserve the old capture API; the UI marks only two points.
            (p1, o1), (a, obj_a), (b, obj_b), (p4, o4) = marcados[:4]
            obj_a, obj_b = obj_a or o1, obj_b or o4
            portas = (p1, p4)
        else:
            if len(marcados) < 2:
                return []
            (a, obj_a), (b, obj_b) = marcados[:2]
            if not getattr(self, '_grupo_alvo', ''):
                # The same solver finds internal faces and measures coverage
                # to both clicked boundaries, without additional gestures.
                portas = (a, b)
        obj_b = obj_b or obj_a
        # Repositioning uses the door's parameters; the door must not
        # serve as its own support.
        alvo = bpy.data.objects.get(getattr(self, '_grupo_alvo', '') or '')
        parametros = _gaveta._valores_portas(bpy.context.scene, alvo)
        apoios = tuple(None if alvo is not None and _portas._grupo_portas(o) == alvo
                       else o for o in (obj_a, obj_b))
        if parametros['dobradica'] == 'ESCOLHER':
            parametros['dobradica'] = 'RETA'
        assistente = getattr(self, '_w', None)
        area = (assistente or {}).get('area_livre')
        escolhas = assistente.get('escolhas', {}) if assistente else {}
        parametros.update(escolhas)
        # Use the thicknesses the operator will resolve: the preview must
        # match the final door (broken chain = no cabinet,
        # as in `_concluir`).
        modulo = (_portas._modulo_da_chapa(obj_a)
                  if tipo._associar(self, bpy.context) else None)
        if area and tipo._associar(self, bpy.context):
            modulo = bpy.data.objects.get(area['modulo'])
        parametros['lateral_mm'] = _portas._espessura_do_vao(modulo, apoios)
        if alvo is None:
            parametros['espessura_mm'] = _portas._espessura_da_porta_nova(
                modulo, apoios)
        referencia = (_areas_criacao._matriz(area['matriz']).to_3x3()
                      if area else self._referencia(obj_a, obj_b))
        frente = ('NEG_Y' if area else _portas._frente_automatica(referencia, a, b,
                                    self._centro(obj_a, obj_b)))
        embutida = False
        try:
            if area:
                largura, altura, matriz = _areas_criacao.vao_porta(area)
                coberturas = dict.fromkeys(_portas.COBERTURAS_LADOS, 0.0)
                modulo = bpy.data.objects.get(area['modulo'])
            else:
                (largura, altura, matriz), _, _, coberturas = _portas._preparar_vao_portas(
                    a, b, referencia, frente, parametros,
                    modulo, apoios, portas=portas,
                    forcar=escolhas.get('tipo_correr', ''))
            parametros.update(coberturas)
            if alvo is None and _portas._correr_sobreposta(parametros):
                # With a frame, the leaf starts at 18 mm (heavy) or 15 mm (light).
                parametros['espessura_mm'] = _portas._espessura_porta_do_trilho(parametros)
            embutida = portas is not None and _portas._porta_embutida(coberturas)
            if portas is not None and parametros['abertura'] != 'CORRER':
                lado = parametros.get('dobradica_lado', 'ESQUERDA')
                chave = _portas.COBERTURAS_LADOS[_portas.INDICE_LADO.get(lado, 0)]
                parametros['dobradica'] = _portas._dobradica_da_cobertura(
                    float(parametros.get(chave, 1.0)), embutida)
            folhas = _portas._calcular_folhas_portas(largura, altura, parametros)
        except (ValueError, KeyError) as erro:
            self._recado = str(erro)
            return []
        self._recado = "Opening %.0f x %.0f mm - %d leaf/leaves%s" % (
            largura, altura, len(folhas), " - inset" if embutida else '')
        if assistente is not None:
            _l, _a, e, centro = folhas[0]
            # Dimensions of the ENTIRE door (all leaves): the sidebar displays
            # them as soon as the area is marked.
            xs = [c[0] + s * l / 2.0 for l, _al, _e, c in folhas
                  for s in (-1, 1)]
            ys = [c[1] + s * al / 2.0 for _l2, al, _e, c in folhas
                  for s in (-1, 1)]
            assistente['medidas_porta'] = (max(xs) - min(xs),
                                           max(ys) - min(ys), e)
            assistente.update(largura=largura, altura=altura,
                              matriz=matriz.copy(), folhas=list(folhas),
                              lateral=parametros['lateral_mm'],
                              coberturas=dict(coberturas), embutida=embutida,
                              costas=centro[2] - e / 2.0,
                              folha=(_l, _a, e, tuple(centro)),
                              modulo_nome=modulo.name if modulo else '',
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
        if self._w.get('snap_pendente'):
            # Native translate owns events: the preview follows the cursor.
            self._imantar(None)
        tema = bpy.context.preferences.themes[0]
        cor_ima = (*tema.view_3d.object_active, 1.0)
        cor_previa = (*tema.user_interface.wcol_regular.text, 0.9)
        linhas = []
        for cantos in self._previa():
            for i, j in _portas.ARESTAS_CAIXA:
                linhas.extend((cantos[i], cantos[j]))
        etapa = self._w.get('etapa')
        marcados = [p for p, _o in self._cantos_marcados()]
        arestas_cor = []
        if etapa in {'DIAGONAL', 'CONFIRMAR'} and len(marcados) == 2:
            linhas.extend(marcados)
        ferragens = []
        if etapa == 'EIXO':
            # Highlight the edge under the mouse in the HUD color.
            destaque = (self._w.get('snap') or (None,))[0]
            for aresta in self._w.get('arestas', ()):
                arestas_cor.append((
                    _hud._cor_realce_hud() if aresta is destaque else _portas.COR_BORDA_EIXO,
                    [self._mundo(aresta['a']), self._mundo(aresta['b'])]))
        pecas_arame, pontos_arame = [], []
        if etapa in {'QUANTIDADE', 'MARGEM', 'PISTOES_QTD', 'PISTOES_OFFSET'}:
            pecas_arame, pontos_arame, ferragens = self._ferragens_do_wizard()
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
            if ferragens:
                # Open piston: white line to the raised leaf.
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
            # Hardware: its actual wireframe, drawn at HUD line thickness.
            _arame._desenhar_arame(bpy.context, pecas_arame, pontos_arame,
                            matriz=self._w.get('matriz'))
        except Exception as e:
            print("[Archy Builder] opening preview:", e)
        finally:
            try:
                gpu.state.line_width_set(1.0)
                gpu.state.point_size_set(1.0)
                gpu.state.blend_set('NONE')
            except Exception:
                pass

    # ------------------------------------------------ lifecycle
    def _mundo(self, ponto_mm, z=0.0):
        """Opening-space (x, y) in mm -> world point."""
        return self._w['matriz'] @ Vector((ponto_mm[0] / 1000.0,
                                            ponto_mm[1] / 1000.0, z))

    def _tela(self, ponto_mundo):
        return view3d_utils.location_3d_to_region_2d(
            self._regiao, self._rv3d, ponto_mundo)

    def _ferragens_do_wizard(self):
        """Return (rig parts, points, open-piston lines) for the wizard's door.
        Use wireframes of the ACTUAL hardware assembled by the door
        (`_ferragens_da_porta`; the straight hinge uses the user's rig),
        in opening coordinates (m). Include pistons only once the wizard
        reaches their step."""
        w = self._w
        if w.get('aresta') is None or not w.get('folhas'):
            return [], [], []
        p = dict(_portas._parametros_do_wizard(w), dobradicas_qtd=w['qtd'],
                 dobradicas_margem_mm=w['margem'])
        if w.get('pistoes'):
            p.update(pistoes_qtd=w['pqtd'], pistoes_offset_mm=w['poffset'])
        try:
            conj = bpy.data.objects.get(w.get('modulo_nome', ''))
            apoios = _ferragens._apoios_obliquos(conj, w['matriz'], p,
                w['largura'], w['altura'], w['folhas']) if conj else {}
            itens = _ferragens._ferragens_da_porta(p, w['largura'], w['altura'],
                                        w['folhas'], apoios)
        except (ValueError, KeyError, TypeError):
            return [], [], []
        if not w.get('pistoes'):
            itens = [i for i in itens if not i['tipo'].startswith('PISTAO')]
        pecas, pontos = _arame._arame_dos_itens(itens)
        fios = []
        if w.get('pistoes') and w.get('folha'):
            # Also draw a line to the piston's position with the door open.
            g = _portas._pistao_do_vao(w['altura'], w['folha'], w['poffset'], p)
            xs = (_ferragens.PISTAO_DA_LATERAL_MM, w['largura'] - _ferragens.PISTAO_DA_LATERAL_MM)
            for x in xs[:max(1, min(2, w['pqtd']))]:
                lateral, _fechada, aberta = _portas._pontas_pistao(g, x, w['folha'])
                fios.append([w['matriz'] @ (lateral / 1000.0),
                             w['matriz'] @ (aberta / 1000.0)])
        return pecas, pontos, fios

    def _encerrar(self, context):
        _gavetas._terminar_snap_criacao()
        timer = getattr(self, '_timer', None)
        if timer is not None:
            context.window_manager.event_timer_remove(timer)
            self._timer = None
        _portas._marcar_apanhando(False)
        _portas._assistente_porta[0] = None
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
        if context.window is not None:
            context.window.cursor_modal_restore()

    def cancel(self, context):
        # Loading a file/closing a window cancels externally: without cleanup,
        # handlers, cursor and `_apanhando_vao` (which disables HUD) stayed stuck.
        self._encerrar(context)

    def invoke(self, context, event):
        self._area = context.area
        if _gaveta._eh_area_gaveta(context):
            self._area = next(
                (a for a in context.screen.areas
                 if a.type == 'VIEW_3D' and a != context.area
                 and a.x > context.area.x and a.y == context.area.y), None)
        if self._area is None or self._area.type != 'VIEW_3D':
            self.report({'ERROR'}, "No 3D viewport to mark the opening")
            return {'CANCELLED'}
        self._regiao = next((r for r in self._area.regions
                             if r.type == 'WINDOW'), None)
        self._rv3d = getattr(self._area.spaces.active, "region_3d", None)
        if self._regiao is None or self._rv3d is None:
            self.report({'ERROR'}, "No 3D viewport to mark the opening")
            return {'CANCELLED'}
        self._regiao_ptr = self._regiao.as_pointer()
        area = _areas_criacao.consumir('PORTAS')

        # With a door selected, the gesture REPOSITIONS it: the new opening
        # comes from the diagonal and retains that door's parameters.
        alvo = _portas._grupo_portas(context.object)
        if alvo is not None and not alvo.get('porta_parametros'):
            alvo = None
        self._grupo_alvo = alvo.name if alvo is not None else ''

        # Use a placeholder opening to validate parameters now, rather than
        # letting the user complete the gesture before discovering
        # that a hinge still needs selecting.
        try:
            _portas._calcular_folhas_portas(
                1000.0, 1000.0, _gaveta._valores_portas(context.scene, alvo))
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, "%s (Doors tab)" % erro)
            return {'CANCELLED'}

        _ferragens._ferragens_selecionadas[0] = None    # Creation ends the previous selection.
        if area is None and not any(o.type == 'MESH' for o in context.visible_objects):
            self.report({'WARNING'}, "No visible mesh for snapping")
            return {'CANCELLED'}
        self._pontos = []
        self._imantado = None
        self._objeto_imantado = None
        self._recado = ''
        self._handler = None
        self._engolir_soltar = False
        self._w = {'etapa': 'DIAGONAL', 'regiao': self._regiao_ptr,
                   'botoes': [], 'escolhas': {}, 'bolinhas': [],
                   'snap_tela': None, 'mouse': None, 'recado': '',
                   'snap_nativo': True, 'cursor': None, 'iniciar_snap': True}
        if area:
            m = _areas_criacao._matriz(area['matriz'])
            l, _prof, a = area['medidas']
            modulo = bpy.data.objects.get(area['modulo'])
            self._pontos = [(m @ Vector((0, 0, a / 1000)), modulo),
                            (m @ Vector((l / 1000, 0, 0)), modulo)]
            self._w.update(area_livre=area, iniciar_snap=False, etapa='FOLHAS')
            self._previa()
            self._ir('FOLHAS')
        _portas._assistente_porta[0] = self._w
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            self._desenhar, (), 'WINDOW', 'POST_VIEW')
        self._handler_2d = bpy.types.SpaceView3D.draw_handler_add(
            _desenhar_assistente_2d, (self._w,), 'WINDOW', 'POST_PIXEL')
        _portas._marcar_apanhando(True)
        context.window.cursor_modal_set('CROSSHAIR')
        context.window_manager.modal_handler_add(self)
        # Wake the modal when the native macro confirms or cancels.
        self._timer = context.window_manager.event_timer_add(.02, window=context.window)
        self.report({'INFO'}, self._instrucao())
        self._area.header_text_set(self._instrucao())
        return {'RUNNING_MODAL'}

    # ------------------------------------------------ wizard
    RECADOS = {
        'CONFIRMAR': "The overlay does not match a full-overlay, half-overlay or inset hinge",
        'FOLHAS': "How many leaves?",
        'TIPO': "Choose the opening type",
        # Mixed midpoint clicks: one pair coincides, the other does not.
        'MOLDURA': "The clicks do not match: inset or framed?",
        'BASE': "Does the door have a base (toe kick) or reach the floor?",
        'TRILHO': "Heavy-duty track (aluminum) or light-duty track (routed grooves)?",
        'EIXO': "Click the hinge edge (the type is automatic)",
        'QUANTIDADE': "Scroll: hinge count | click confirms",
        'MARGEM': "Move in Y: distance from corners | click confirms",
        'PISTOES_QTD': "Scroll: gas stay count | click confirms",
        'PISTOES_OFFSET': "Automatic position | move in Y to raise the gas stay | click creates the door",
    }
    PASSOS_CANTOS = ("1/2: first door corner", "2/2: opposite door corner")
    PERGUNTAS = {'CONFIRMAR': (_portas.OPCOES_CONFIRMAR, "Are the dimensions correct?"),
                 'FOLHAS': (_portas.OPCOES_FOLHAS, "How many leaves?"),
                 'MOLDURA': (_portas.TIPOS_CORRER, "Inset or framed door?"),
                 'BASE': (_portas.OPCOES_BASE, "Does the door have a base?"),
                 'TRILHO': (_portas.OPCOES_TRILHO, "Which track?")}
    ETAPAS_CAIXA = ('CONFIRMAR', 'FOLHAS', 'TIPO', 'MOLDURA', 'BASE', 'TRILHO')

    def _instrucao(self):
        return "Click %s (Esc cancels)" % self.PASSOS_CANTOS[min(len(self._pontos), 1)]

    def _ir(self, etapa, mouse=None):
        w = self._w
        w['etapa'] = etapa
        w['botoes'], w['hover_botao'], w['bolinhas'] = [], None, []
        w['snap_tela'], w['snap'] = None, None
        escala = max(1.0, bpy.context.preferences.system.ui_scale)
        ancora = mouse if mouse is not None else w.get('mouse') or Vector((200, 200))
        if etapa in self.PERGUNTAS or etapa == 'TIPO':
            opcoes, pergunta = self.PERGUNTAS.get(
                etapa, (w.get('tipos', ()), "Opening:"))
            w['botoes'] = _botoes_assistente(
                ancora, opcoes, escala,
                (self._regiao.width, self._regiao.height), pergunta)
            w['pergunta'] = pergunta
        elif etapa == 'EIXO':
            w['arestas'] = _portas._arestas_da_porta(w['largura'], w['altura'],
                                             w['coberturas'], w['lateral'],
                                             w['tipo'])
        elif etapa == 'QUANTIDADE':
            comprimento = (w['aresta']['b'] - w['aresta']['a']).length
            _ajustar_dobradicas_wizard(w, _portas._qtd_dobradicas_padrao(comprimento),
                                       _portas.MARGEM_DOBRADICAS_PADRAO)
        elif etapa in {'MARGEM', 'PISTOES_OFFSET'}:
            w['y0'] = ancora.y
            w['valor0'] = w['margem'] if etapa == 'MARGEM' else w['poffset']
            # mm per pixel measured on the actual axis, valid at any zoom.
            if etapa == 'MARGEM':
                a, b = w['aresta']['a'], w['aresta']['b']
            else:
                a, b = Vector((0, 0)), Vector((0, w['altura']))
            ta, tb = self._tela(self._mundo(a)), self._tela(self._mundo(b))
            px = (tb - ta).length if ta is not None and tb is not None else 0
            w['mm_por_px'] = ((b - a).length / px) if px > 1 else 1.0
        elif etapa == 'PISTOES_QTD':
            # The piston starts at its AUTOMATIC model/position (open = 2x closed);
            # manual offset is measured from there.
            g = _portas._pistao_do_vao(w['altura'], w['folha'],
                               p=_portas._parametros_do_wizard(w))
            w['pistoes'] = True
            w['pqtd'] = _portas._qtd_pistoes_padrao(w['largura'])
            w['poffset'] = w['poffset_auto'] = g['offset']
        w['recado'] = self.RECADOS.get(etapa, '')
        # The Doors tab reveals each answered category.
        _eventos._redesenhar_viewports(bpy.context)
        if etapa == 'CONFIRMAR':
            fora = _portas._lados_fora_do_padrao(w['coberturas'])
            w['recado'] = "Nonstandard overlay: %s" % ', '.join(
                k[len('cobertura_'):-len('_e')] for k in fora)
        self._area.header_text_set(w['recado'])
        self._area.tag_redraw()

    def _recomecar(self):
        """"No, mark again": return to the first click."""
        self._pontos = []
        self._w.update(etapa='DIAGONAL', botoes=[], escolhas={},
                       pistoes=False, duas_bordas=False, aresta=None,
                       iniciar_snap=True)
        self._area.header_text_set(self._instrucao())
        self._area.tag_redraw()

    def _escolher(self, context, chave):
        """Answer a choice box (CONFIRMAR, FOLHAS, TIPO, MOLDURA, BASE or TRILHO)."""
        w = self._w
        escolhas = w['escolhas']
        if w['etapa'] == 'MOLDURA':
            escolhas['tipo_correr'] = chave
            if chave == 'MOLDURA':
                self._ir('BASE')
                return None
            escolhas.pop('rodape_mm', None)
            return self._criar(context)
        if w['etapa'] == 'BASE':
            # No base means no plinth: the frame sits directly on the floor.
            padrao = (getattr(context.scene, 'porta_rodape_mm', 0.0) if context
                      else 0.0) or _portas.PADRAO_MEDIDAS_PORTAS['porta_rodape_mm']
            escolhas['rodape_mm'] = 0.0 if chave == 'SEM' else float(padrao)
            self._ir('TRILHO')          # Track choice: heavy or light.
            return None
        if w['etapa'] == 'TRILHO':
            escolhas['trilho'] = chave
            return self._criar(context)
        if w['etapa'] == 'CONFIRMAR':
            if chave == 'NAO':
                self._recomecar()
            else:
                self._ir('FOLHAS')
            return None
        if w['etapa'] == 'FOLHAS':
            escolhas['folhas'] = int(chave)
            opcoes = _portas.TIPOS_EMBUTIDA if w['embutida'] else _portas.TIPOS_SOBREPOSTA
            w['tipos'] = tuple(t for t in opcoes
                               if (2 if t[0] == 'ZIGZAG' else 1) <= escolhas['folhas'] <= _portas.LIMITES_FOLHAS[t[0]])
            if len(w['tipos']) == 1:
                # Only one option: no question needed.
                return self._escolher_abertura(context, w['tipos'][0][0])
            self._ir('TIPO')
            return None
        return self._escolher_abertura(context, chave)

    def _metade_metade(self):
        """Mixed-coverage boundaries require an explicit sliding-door type."""
        if len(self._pontos) < 4:
            coberturas = self._w.get('coberturas', {})
            lados = [float(coberturas.get(k, 0)) > 1e-6 for k in _portas.COBERTURAS_LADOS]
            return any(lados) and not all(lados)
        (p1, _o1), (a, _oa), (b, _ob), (p4, _o4) = self._pontos[:4]
        tolerancia = _modulos.TOL_BORDA
        juntos = [(Vector(p1) - Vector(a)).length <= tolerancia,
                  (Vector(p4) - Vector(b)).length <= tolerancia]
        return juntos[0] != juntos[1]

    def _escolher_abertura(self, context, chave):
        w = self._w
        escolhas = w['escolhas']
        escolhas['abertura'] = chave
        escolhas.pop('tipo_correr', None)
        escolhas.pop('rodape_mm', None)
        escolhas.pop('trilho', None)
        if chave == 'CORRER':
            escolhas['dobradica'] = 'RETA'
            if self._metade_metade():
                # One clicked pair coincides and the other does not: the gesture
                # does not distinguish inset from framed installation.
                self._ir('MOLDURA')
                return None
            if not w.get('embutida'):
                self._ir('BASE')        # With a frame: does it have a base/plinth?
                return None
            return self._criar(context)
        w['tipo'] = chave
        if w['embutida']:
            escolhas['dobradica'] = 'SUPER_CURVA'
        w['duas_bordas'] = chave == 'GIRO' and escolhas.get('folhas', 1) > 1
        if w['duas_bordas'] or chave == 'BASCULANTE':
            # Do not ask for an edge: two swing leaves have hinges on BOTH;
            # lift-up doors always use the TOP edge, as requested.
            w['arestas'] = _portas._arestas_da_porta(w['largura'], w['altura'],
                                             w['coberturas'], w['lateral'],
                                             chave)
            self._fixar_borda(w['arestas'][0])
            self._ir('QUANTIDADE')
            return None
        self._ir('EIXO')
        return None

    def _fixar_borda(self, aresta):
        """Chosen hinge edge: its coverage determines the TYPE."""
        w = self._w
        w['aresta'] = aresta
        chave = _portas.COBERTURAS_LADOS[_portas.INDICE_LADO[aresta['lado']]]
        w['escolhas'].update(
            dobradica=_portas._dobradica_da_cobertura(
                float(w['coberturas'].get(chave, 1.0)), w['embutida']),
            dobradica_lado=aresta['lado'])

    def _snap_sob_mouse(self, mouse):
        """Return (edge, screen point) for the edge nearest the mouse."""
        melhor = None
        for aresta in self._w.get('arestas', ()):
            a = self._tela(self._mundo(aresta['a']))
            b = self._tela(self._mundo(aresta['b']))
            if a is None or b is None:
                continue
            d = _hud._distancia_segmento_hud(mouse, a, b)
            if d > _portas.RAIO_IMA_PX:
                continue
            seg = b - a
            t = ((mouse - a).dot(seg) / seg.length_squared
                 if seg.length_squared > 1e-9 else 0.0)
            if melhor is None or d < melhor[0]:
                melhor = (d, aresta, a + seg * max(0.0, min(1.0, t)))
        return melhor[1:] if melhor else None

    def _etapa_wizard(self, context, event):
        """Everything after the corners; return the modal result."""
        w = self._w
        mouse = self._mouse_na_regiao(event)
        w['mouse'] = mouse
        etapa = w['etapa']
        caixa = etapa in self.ETAPAS_CAIXA
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and etapa in {
                'QUANTIDADE', 'PISTOES_QTD'}:
            passo = 1 if event.type == 'WHEELUPMOUSE' else -1
            if etapa == 'QUANTIDADE':
                _ajustar_dobradicas_wizard(w, w['qtd'] + passo, w['margem'])
                w['recado'] = "%d hinges (scroll) | click confirms" % w['qtd']
            else:
                w['pqtd'] = max(_portas.LIMITES_PISTOES[0],
                                min(_portas.LIMITES_PISTOES[1], w['pqtd'] + passo))
                w['recado'] = "%d gas stay(s) (scroll) | click confirms" % w['pqtd']
            _eventos._redesenhar_viewports(context)       # The sidebar displays the count.
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
                        _portas.COBERTURAS_LADOS[_portas.INDICE_LADO[lado]], 1.0))
                    w['recado'] = "Hinges on edge %s: %s" % (
                        _opcoes.DIRECTION_LABELS[lado].lower(), _portas.NOME_DOBRADICA[_portas._dobradica_da_cobertura(
                            fracao, w['embutida'])])
                else:
                    w['recado'] = self.RECADOS['EIXO']
                # The sidebar displays the type for the edge under the mouse.
                _eventos._redesenhar_viewports(context)
            elif etapa in {'MARGEM', 'PISTOES_OFFSET'}:
                if w.pop('rebase', False):
                    # Sidebar input: mouse adjustment starts from the typed value.
                    w['y0'] = mouse.y
                    w['valor0'] = (w['margem'] if etapa == 'MARGEM'
                                   else w['poffset'])
                delta = (mouse.y - w['y0']) * w['mm_por_px']
                if etapa == 'MARGEM':
                    _ajustar_dobradicas_wizard(w, w['qtd'], w['valor0'] + delta)
                    w['recado'] = "Margin %.0f mm | click confirms" % w['margem']
                else:
                    # Top to bottom: lowering the mouse increases the offset,
                    # limited to the piston's reach with the door open.
                    g = _portas._pistao_do_vao(w['altura'], w['folha'],
                                       max(1e-3, w['valor0'] - delta),
                                       _portas._parametros_do_wizard(w))
                    w['poffset'] = g['offset']
                    limite = g['offset'] >= g['offset_max'] - 0.5
                    w['recado'] = ("Gas stay %.0f mm at %.0f mm from top%s | click creates" % (
                                       g['aberto'], g['offset'],
                                       " (maximum stroke)" if limite else ''))
                _eventos._redesenhar_viewports(context)   # Margin/offset in the sidebar.
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
        return self._confirmar_etapa(context, mouse) or {'RUNNING_MODAL'}

    def _confirmar_etapa(self, context, mouse=None):
        """Viewport click OR sidebar Confirm: count and offset can be confirmed
        there too. Without `mouse` (sidebar action), rebase the next step on
        the viewport mouse when it returns, rather than its old position."""
        w = self._w
        etapa = w['etapa']
        seguinte = {'QUANTIDADE': 'MARGEM', 'PISTOES_QTD': 'PISTOES_OFFSET'}
        if etapa == 'MARGEM' and w['tipo'] == 'BASCULANTE':
            seguinte['MARGEM'] = 'PISTOES_QTD'
        if etapa in seguinte:
            self._ir(seguinte[etapa], mouse)
            if mouse is None:
                w['rebase'] = True
            return None
        if etapa in {'MARGEM', 'PISTOES_OFFSET'}:
            return self._criar(context)
        return None

    def _voltar(self):
        """Right-click: go back one step."""
        w = self._w
        etapa = w['etapa']
        if w.get('area_livre') and etapa in {'CONFIRMAR', 'FOLHAS'}:
            self._ir('FOLHAS')
            return
        if etapa in {'CONFIRMAR', 'FOLHAS'}:
            # Keep the first corner to mark only the opposite one again.
            self._pontos = self._pontos[:1]
            w.update(etapa='DIAGONAL', botoes=[], escolhas={}, iniciar_snap=True)
            self._area.header_text_set(self._instrucao())
            self._area.tag_redraw()
            return
        escolha_do_tipo = 'TIPO' if len(w.get('tipos', ())) > 1 else 'FOLHAS'
        borda_automatica = (w.get('duas_bordas')
                            or w.get('tipo') == 'BASCULANTE')
        anteriores = {'TIPO': 'FOLHAS', 'MOLDURA': escolha_do_tipo,
                      'BASE': ('MOLDURA' if 'tipo_correr' in w['escolhas']
                               else escolha_do_tipo),
                      'TRILHO': 'BASE',
                      'EIXO': escolha_do_tipo,
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
            # Automatic mode stores 0 so the piston follows cabinet resizing.
            manual = abs(w['poffset'] - w.get('poffset_auto', 0.0)) > 0.5
            extras.update(pistoes_qtd=w['pqtd'],
                          pistoes_offset_mm=float(w['poffset']) if manual else 0.0)
        return self._concluir(context, extras)

    def _responder_pela_gaveta(self, context, pergunta, chave):
        """The Doors-tab row mirrors the viewport choice box. Answering an
        already answered question restarts from there and discards later steps."""
        w = self._w
        if pergunta in {'dobradicas_qtd', 'pistoes_qtd'}:
            _editar_assistente(pergunta, chave)    # Value only; do not advance.
            return None
        if pergunta == _portas.CONFIRMAR_ETAPA:
            # A button from an earlier step is no longer valid.
            return (self._confirmar_etapa(context) if chave == w['etapa']
                    else None)
        if pergunta == 'porta_confirmar':
            if w['etapa'] != 'CONFIRMAR':
                return None
            return self._escolher(context, chave)
        if pergunta == 'porta_tipo_correr':
            if w['etapa'] not in {'MOLDURA', 'BASE'}:
                return None
            w['etapa'] = 'MOLDURA'          # Answered again: restart from this step.
            return self._escolher(context, chave)
        if pergunta == 'porta_base':
            if w['etapa'] not in {'BASE', 'TRILHO'}:
                return None
            w['etapa'] = 'BASE'             # Answered again: restart from this step.
            return self._escolher(context, chave)
        if pergunta == 'porta_trilho':
            if w['etapa'] != 'TRILHO':
                return None
            return self._escolher(context, chave)
        if w['etapa'] == 'CONFIRMAR':
            return None
        folhas = w['escolhas'].get('folhas')
        w.update(duas_bordas=False, aresta=None, pistoes=False)
        if pergunta == 'porta_folhas':
            w.update(escolhas={}, etapa='FOLHAS')
            return self._escolher(context, str(chave))
        if folhas is None:
            return None
        if (pergunta == 'porta_abertura' and w['etapa'] != 'TIPO'
                and chave == w['escolhas'].get('abertura')):
            # The image of the chosen opening on the hinge row:
            # return to the choice, showing all three options.
            w['escolhas'] = {'folhas': folhas}
            self._ir('TIPO')
            return None
        w.update(escolhas={'folhas': folhas}, etapa='TIPO')
        return self._escolher_abertura(context, chave)

    def modal(self, context, event):
        try:
            return OBJECT_OT_apanhar_vao_portas._modal(self, context, event)
        except Exception:
            # An intermediate error used to strand handlers, timer, snap and disabled HUD.
            self._encerrar(context)
            raise

    def _modal(self, context, event):
        w = self._w
        if w.get('cancelar'):           # Esc/right-click during native translate.
            self._encerrar(context)
            return {'CANCELLED'}
        confirmado = w.pop('ponto_confirmado', None)
        if confirmado is not None:
            w['snap_pendente'] = False
            w['cursor'], w['cursor_obj'] = confirmado
            self._imantar(event)
            return self._marcar_canto(context, event)
        if w.pop('iniciar_snap', False) and w.get('etapa') == 'DIAGONAL':
            self._iniciar_snap(context)
            return {'RUNNING_MODAL'}
        if w.get('snap_pendente'):
            return {'PASS_THROUGH'}
        if self._w.get('etapa') != getattr(self, '_etapa_vista', None):
            # New step: scroll the Doors tab to its new row at the bottom.
            self._etapa_vista = self._w.get('etapa')
            _gaveta._rolar_ate_o_fim(context)
        if (event.type == 'LEFTMOUSE' and event.value == 'RELEASE'
                and self._engolir_soltar):
            # The release of a sidebar answer click must be consumed: the row
            # has changed and it would hit another widget.
            self._engolir_soltar = False
            return {'RUNNING_MODAL'}
        gaveta = (_gaveta_eventos._gaveta_sob_evento(context, event)
                  if event.type != 'ESC' else None)
        if gaveta is not None:
            # In the sidebar, the mouse belongs to its hover, tabs, scrolling and fields;
            # the wizard handles only rows mirroring viewport choices.
            if (event.type == 'LEFTMOUSE' and event.value == 'PRESS'
                    and self._w['etapa'] != 'DIAGONAL'):
                acao = _gaveta_eventos._acao_da_gaveta(context, event, *gaveta)
                if (acao and acao[0] == 'escolha' and len(acao) > 5
                        and acao[5] == _portas.ALVO_ASSISTENTE):
                    self._engolir_soltar = True
                    resultado = self._responder_pela_gaveta(
                        context, acao[1], acao[2])
                    _eventos._redesenhar_viewports(context)
                    return resultado or {'RUNNING_MODAL'}
            return {'PASS_THROUGH'}
        if self._w['etapa'] != 'DIAGONAL':
            if event.type == 'ESC' and event.value == 'PRESS':
                self._encerrar(context)
                return {'CANCELLED'}
            if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
                self._voltar()
                return {'RUNNING_MODAL'}
            return self._etapa_wizard(context, event)
        # Navigation must remain available during capture.
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
            return self._marcar_canto(context, event)
        return {'RUNNING_MODAL'}

    def _iniciar_snap(self, context):
        # Shared native snap protocol: fix it at its owner, do not copy it.
        _gavetas.AssistenteDoVao._iniciar_snap_nativo(self, context)

    def _marcar_canto(self, context, event):
        """Accept the snap point as the next corner."""
        if self._imantado is None or self._objeto_imantado is None:
            # Without a part, the opening has neither axes nor a cabinet.
            self.report({'WARNING'}, "Click a panel vertex")
            self._w['iniciar_snap'] = True
            return {'RUNNING_MODAL'}
        self._pontos.append((self._imantado.copy(),
                             self._objeto_imantado))
        self._area.tag_redraw()
        if len(self._pontos) < self._cliques():
            self._area.header_text_set(self._instrucao())
            self._w['iniciar_snap'] = True
            return {'RUNNING_MODAL'}
        if self._grupo_alvo:
            # Reposition: only the diagonal, using the door's parameters.
            return self._concluir(context)
        # New door: continue the wizard (leaves, type, edge, hardware).
        self._w['matriz'] = None
        self._previa()
        if self._w.get('matriz') is None:
            self.report({'WARNING'}, self._recado or "Invalid opening")
            self._pontos = self._pontos[:1]
            self._w['iniciar_snap'] = True
            return {'RUNNING_MODAL'}
        mouse = self._mouse_na_regiao(event)
        if _portas._lados_fora_do_padrao(self._w['coberturas']):
            self._ir('CONFIRMAR', mouse)
        else:
            self._ir('FOLHAS', mouse)
        return {'RUNNING_MODAL'}

    def _concluir(self, context, extras=None):
        if self._w.get('area_livre'):
            return self._concluir_area(context, extras)
        portas = None
        if len(self._pontos) >= 4:
            (p1, o1), (a, obj_a), (b, obj_b), (p4, o4) = self._pontos[:4]
            obj_a, obj_b = obj_a or o1, obj_b or o4
            portas = (p1, p4)
        else:
            (a, obj_a), (b, obj_b) = self._pontos[:2]
            if not self._grupo_alvo:
                portas = (a, b)
        self._encerrar(context)
        referencia, pai = _portas._referencia_do_par(obj_a, obj_b)
        # Scenario 2: the opening corner landed on a panel, so its opening
        # belongs to that panel's cabinet and the door is linked to it.
        modulo = _portas._modulo_da_chapa(obj_a)
        if not self._associar(context):
            # Broken chain: loose door, world axes, no parent.
            referencia, pai, modulo = Matrix.Identity(3), None, None
        ativa = obj_a.matrix_world.to_quaternion().to_matrix()
        s = context.scene
        parametros = _portas._parametros_portas_da_cena(s)
        parametros.update(extras or {})
        try:
            # Use EXEC_DEFAULT, not INVOKE: parameters already come from the
            # Doors tab, so there is no dialog to open.
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


    def _concluir_area(self, context, extras):
        area = self._w['area_livre']
        parametros = _portas._parametros_portas_da_cena(context.scene)
        parametros.update(extras or {})
        largura, altura, matriz = _areas_criacao.vao_porta(area)
        modulo = area['modulo'] if self._associar(context) else ''
        pontos = [tuple(p) for p, _obj in self._pontos[:2]]
        self._encerrar(context)
        return bpy.ops.object.cabinet_portas('EXEC_DEFAULT', capturado=True,
            area_definida=True, matriz_area=tuple(v for linha in matriz for v in linha),
            medidas_area=(largura, altura), ponto_a=pontos[0], ponto_b=pontos[1],
            modulo_nome=modulo, quatro_pontos=True,
            referencia=tuple(v for linha in _areas_criacao._matriz(area['matriz']).to_3x3() for v in linha),
            **parametros)


class OBJECT_OT_portas_parametricas(Operator):
    """Create doors from two diagonal vertices or reconfigure the selected group."""
    bl_idname = "object.cabinet_portas"
    bl_label = "Parametric Doors"
    bl_options = {'REGISTER', 'UNDO'}

    editar: BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})
    grupo_nome: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    # Repositioning uses an existing door with a newly marked opening:
    # retain its parameters and reuse its group.
    grupo_alvo: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    capturado: BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})
    area_definida: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})
    matriz_area: FloatVectorProperty(size=16, options={'HIDDEN', 'SKIP_SAVE'})
    medidas_area: FloatVectorProperty(size=2, options={'HIDDEN', 'SKIP_SAVE'})
    ponto_a: FloatVectorProperty(size=3, options={'HIDDEN'})
    ponto_b: FloatVectorProperty(size=3, options={'HIDDEN'})
    # Legacy explicit-coverage API. In the two-click wizard, door/opening
    # start with the same bounds; the solver finds internal faces.
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
        name="Opening axes", default='AUTO',
        items=[('AUTO', "Common parent / world", "Uses the common parent's axes, if one exists"),
               ('MUNDO', "World", "World X/Y width and Z height"),
               ('ATIVO', "Active object", "For a rotated cabinet without a parent; local Z height")])
    centro: FloatVectorProperty(size=3, options={'HIDDEN'})
    # Outside the UI, where the diagonal always determines the face:
    # retain this only for scripts/tests forcing a face.
    frente: EnumProperty(
        name="Front", default='AUTO', options={'HIDDEN', 'SKIP_SAVE'},
        description="Outward direction, using the common parent's axes or world axes",
        items=[('AUTO', "Automatic",
                "Infers the face from the two marked points"),
               ('NEG_Y', "-Y (front)", "Outward along -Y"),
               ('POS_Y', "+Y (back)", "Outward along +Y"),
               ('NEG_X', "-X (left)", "Outward along -X"),
               ('POS_X', "+X (right)", "Outward along +X"),
               ('NEG_Z', "-Z (below)", "Outward along -Z"),
               ('POS_Z', "+Z (above)", "Outward along +Z")])
    abertura: EnumProperty(name="Opening", items=_portas.ITENS_ABERTURA,
                           default='GIRO', update=_portas._limitar_folhas_portas)
    folhas: IntProperty(name="Leaves", default=1, min=1, max=8,
                        update=_portas._limitar_folhas_portas)
    dobradica: EnumProperty(name="Hinge / placement",
                            items=_portas.ITENS_DOBRADICA, default='RETA')
    # Defaults only when the opening has neither panel nor cabinet;
    # otherwise use `_espessura_do_vao` / `_espessura_da_porta_nova`.
    espessura_mm: EnumProperty(
        name="Door thickness (mm)", default='18',
        options={'HIDDEN', 'SKIP_SAVE'},
        items=[(str(int(e)), str(int(e)), "mm") for e in _chapas.ESPESSURAS_PERMITIDAS])
    lateral_mm: EnumProperty(
        name="Side panel thickness (mm)", default='18',
        options={'HIDDEN', 'SKIP_SAVE'},
        items=[(str(int(e)), str(int(e)), "mm") for e in _chapas.ESPESSURAS_PERMITIDAS])
    # No field (always zero); retain for callers such as imports.
    folga_mm: FloatProperty(name="Perimeter clearance (mm)", default=0, min=0,
                            options={'HIDDEN', 'SKIP_SAVE'})
    entre_folhas_mm: FloatProperty(name="Gap between leaves (mm)", default=2, min=0)
    afastamento_mm: FloatProperty(name="Front clearance (mm)", default=0, min=0)
    recuo_embutida_mm: FloatProperty(name="Inset door recess (mm)", default=0, min=0)
    recuo_correr_mm: FloatProperty(
        name="Track recess (mm)", default=30, min=0.1,
        description="Distance from the front edge to the outer face of the first leaf")
    entre_planos_mm: FloatProperty(name="Gap between planes (mm)", default=2, min=0.1)
    # Sliding-door frame (`_portas._pecas_moldura`).
    moldura_mm: FloatProperty(
        name="Frame thickness (mm)", min=1.0,
        default=_portas.PADRAO_MEDIDAS_PORTAS['porta_moldura_mm'])
    rodape_mm: FloatProperty(
        name="Toe kick (mm)", min=0.0,
        default=_portas.PADRAO_MEDIDAS_PORTAS['porta_rodape_mm'])
    testeira_mm: FloatProperty(
        name="Fascia (mm)", min=0.0,
        default=_portas.PADRAO_MEDIDAS_PORTAS['porta_testeira_mm'])
    trilho: EnumProperty(name="Track", items=_portas.ITENS_TRILHO,
                         default='PESADO')
    folha: EnumProperty(name="Leaf", items=_portas.ITENS_FOLHA_CORRER,
                        default='CHAPA')
    # Answer to inset or framed installation for mixed midpoint clicks.
    tipo_correr: EnumProperty(
        name="Sliding", default='AUTO', options={'HIDDEN', 'SKIP_SAVE'},
        items=[('AUTO', "From clicks", "")]
        + [(k, t, "") for k, t in _portas.TIPOS_CORRER])
    # Hardware chosen in the wizard (0 = automatic from dimensions).
    dobradica_lado: EnumProperty(
        name="Hinge side", default='ESQUERDA',
        items=[('ESQUERDA', "Left", ""), ('DIREITA', "Right", ""),
               ('CIMA', "Top", "Lift-up")])
    dobradicas_qtd: IntProperty(name="Hinges", default=0, min=0, max=8)
    dobradicas_margem_mm: FloatProperty(name="Hinge margin (mm)",
                                        default=100.0, min=0)
    pistoes_qtd: IntProperty(name="Gas Stays", default=0, min=0, max=2)
    pistoes_offset_mm: FloatProperty(
        name="Gas stay: distance from top (mm)", default=0.0, min=0,
        description="0 = automatic; manual adjustment limited to the gas stay stroke")

    @classmethod
    def poll(cls, context):
        # In Object Mode the opening can come from the capture operator
        # (`cabinet_apanhar_vao`) with ready-to-use points;
        # invoke validates anything still missing.
        return context.mode in {'EDIT_MESH', 'OBJECT'}

    def _capturar(self, context):
        a, b, ref, pai, obj_a, obj_b = _portas._capturar_vertices_portas(
            context, com_objetos=True)
        self.ponto_a, self.ponto_b = a, b
        self.referencia = tuple(v for linha in ref for v in linha)
        ativa = context.edit_object.matrix_world.to_quaternion().to_matrix()
        self.referencia_ativa = tuple(v for linha in ativa for v in linha)
        self.pai_nome = pai.name if pai is not None else ''
        self.objeto_a_nome, self.objeto_b_nome = obj_a.name, obj_b.name
        modulo = _portas._modulo_da_chapa(obj_a)
        self.modulo_nome = modulo.name if modulo is not None else ''
        if not getattr(context.scene, 'porta_associar', True):
            # Broken chain: loose on world axes (the cabinet center still
            # determines which face points outward).
            self.referencia = tuple(v for linha in Matrix.Identity(3)
                                    for v in linha)
            self.pai_nome = self.modulo_nome = ''
        if modulo is not None:
            self.centro = _portas._centro_do_movel(obj_a, obj_b)
        else:
            # Without a cabinet, use origins: a coplanar two-point box ties
            # against them and previously reversed the front.
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
        # A repositioned door must not support itself.
        return tuple(None if o is not None and alvo is not None
                     and _portas._grupo_portas(o) == alvo else o for o in objetos)

    def _preparar_vao(self):
        if self.area_definida:
            largura, altura = self.medidas_area
            matriz = _areas_criacao._matriz(self.matriz_area)
            _areas_criacao.validar_plano((largura, altura), matriz)
            return ((largura, altura, matriz), [Vector(self.ponto_a), Vector(self.ponto_b)],
                    {}, dict.fromkeys(_portas.COBERTURAS_LADOS, 0.0))
        return _portas._preparar_vao_portas(
            self.ponto_a, self.ponto_b, self._ref(), self._frente_resolvida(),
            self._parametros(), bpy.data.objects.get(self.modulo_nome),
            self._objetos(), portas=((self.porta_a, self.porta_b)
                                     if self.quatro_pontos else None),
            forcar='' if self.tipo_correr == 'AUTO' else self.tipo_correr)

    def _vao(self):
        return self._preparar_vao()[0]

    def _frente_resolvida(self):
        return _portas._resolver_frente(self.frente, self._ref(), self.ponto_a,
                                self.ponto_b, self.centro)

    def _parametros(self):
        p = {nome: getattr(self, nome) for nome in _portas._PARAMETROS_PORTAS}
        p['espessura_mm'] = float(self.espessura_mm)
        p['lateral_mm'] = float(self.lateral_mm)
        alvo = bpy.data.objects.get(self.grupo_alvo) if self.grupo_alvo else None
        if alvo is not None and alvo.get('porta_parametros'):
            p.update(_gaveta._valores_portas(bpy.context.scene, alvo))
            # Repositioning preserves each side's coverage.
            guardados = alvo['porta_parametros']
            p.update({k: float(guardados[k]) for k in _portas.COBERTURAS_LADOS
                      if k in guardados})
            p['lateral_mm'] = _portas._espessura_do_vao(
                bpy.data.objects.get(self.modulo_nome), self._objetos(),
                p['lateral_mm'])
            return p
        if self.editar:
            # Reconfiguration does not change thickness: leaf E owns door thickness,
            # while the cabinet owns side thickness.
            grupo = (bpy.data.objects.get(self.grupo_nome) if self.grupo_nome
                     else _portas._grupo_portas(bpy.context.object))
            guardados = (grupo.get('porta_parametros') or {}) if grupo else {}
            copia = _portas._copiar_parametros(guardados)
            if all(p.get(k) == copia.get(k) for k in
                   ('dobradicas_qtd', 'dobradicas_margem_mm', 'dobradica_lado', 'folhas', 'abertura')):
                if 'dobradicas_referencia' in copia:
                    p['dobradicas_referencia'] = copia['dobradicas_referencia']
            if (p['abertura'] == 'GIRO' and p['dobradica'] == copia.get('dobradica')
                    and copia.get('dobradica_articulada')):
                p['dobradica_articulada'] = True
                p['dobradica_apoio_plano_mm'] = copia['dobradica_apoio_plano_mm']
                for nome in ('dobradica_articulada_sinal', 'dobradica_junta_mm'):
                    if nome in copia:
                        p[nome] = copia[nome]
            for nome in ('espessura_mm', 'lateral_mm'):
                if nome in guardados:
                    p[nome] = float(guardados[nome])
            vinculado = (bpy.data.objects.get(grupo.get(_portas.CHAVE_MODULO_PORTA, ''))
                         if grupo else None)
            if vinculado is not None:
                p['lateral_mm'] = _portas._espessura_do_vao(vinculado,
                                                    padrao=p['lateral_mm'])
            return p
        modulo = bpy.data.objects.get(self.modulo_nome)
        objetos = self._objetos()
        p['lateral_mm'] = _portas._espessura_do_vao(modulo, objetos, p['lateral_mm'])
        p['espessura_mm'] = _portas._espessura_da_porta_nova(modulo, objetos,
                                                     p['espessura_mm'])
        return p

    def invoke(self, context, event):
        try:
            if context.mode == 'OBJECT' and _portas._grupo_portas(context.object) is not None:
                self.editar = True
            if self.editar:
                grupo = _portas._grupo_portas(context.object)
                if grupo is None or context.mode != 'OBJECT':
                    raise ValueError("Select a door group in Object Mode")
                self.grupo_nome = grupo.name
                for nome, valor in grupo['porta_parametros'].items():
                    if nome in {'espessura_mm', 'lateral_mm'}:
                        # The enum contains standard thicknesses only; free thickness
                        # (25, 70, etc.) comes from the group in `_parametros`.
                        texto = str(int(valor))
                        if float(valor) in _chapas.ESPESSURAS_PERMITIDAS:
                            setattr(self, nome, texto)
                    elif nome in _portas._PARAMETROS_PORTAS:
                        setattr(self, nome, valor)
            else:
                # Points already captured in the viewport avoid Edit Mode;
                # without them, fall back to vertex capture.
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
                    layout.label(text="Axes: " + (self.pai_nome or "World"))
                largura, altura, _ = self._vao()
            layout.label(text="Opening: %.1f x %.1f mm" % (largura, altura))
        except (ValueError, KeyError, TypeError) as erro:
            largura = altura = None
            layout.label(text=str(erro), icon='ERROR')
        layout.prop(self, 'abertura')
        linha = layout.row()
        linha.enabled = self.abertura != 'BASCULANTE'
        linha.prop(self, 'folhas')
        layout.label(text="Allowed: 1 to %d leaf/leaves" % _portas.LIMITES_FOLHAS[self.abertura])
        if self.abertura != 'CORRER':
            caixa = layout.box()
            caixa.label(text="Which hinge / placement?")
            caixa.prop(self, 'dobradica', text="")
            if self.dobradica in {'RETA', 'CURVA'}:
                caixa.prop(self, 'afastamento_mm')
            elif self.dobradica == 'SUPER_CURVA':
                caixa.prop(self, 'recuo_embutida_mm')
            if self.folhas > 1:
                layout.prop(self, 'entre_folhas_mm')
        else:
            layout.label(text="Inset, one on each track")
            layout.prop(self, 'recuo_correr_mm')
            if self.folhas > 1:
                layout.prop(self, 'entre_planos_mm')
        if largura is not None:
            try:
                folhas = _portas._calcular_folhas_portas(largura, altura, self._parametros())
                l, a, e, _ = folhas[0]
                layout.label(text="Each leaf: %.1f x %.1f x %.0f mm" % (l, a, e))
                if self.abertura == 'CORRER':
                    fundo = max(-f[3][2] + e / 2 for f in folhas)
                    layout.label(text="Depth occupied from the edge: %.1f mm" % fundo)
            except ValueError as erro:
                layout.label(text=str(erro), icon='ERROR')
        layout.label(text="Blockout: door solids only", icon='INFO')

    def check(self, context):
        return True

    def execute(self, context):
        try:
            grupo = None
            pai = None
            if self.editar:
                grupo = bpy.data.objects.get(self.grupo_nome) if self.grupo_nome else _portas._grupo_portas(context.object)
                if grupo is None or _chapas.MARCA_PORTAS not in grupo:
                    raise ValueError("Door group not found")
                largura = grupo['porta_vao_largura_mm']
                altura = grupo['porta_vao_altura_mm']
                matriz = grupo.matrix_world.copy()
                largura, altura, matriz = _portas._vao_com_ancoras(
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
                    raise ValueError("The opening's parent has zero scale")
                grupo = (bpy.data.objects.get(self.grupo_alvo)
                         if self.grupo_alvo else None)
            parametros = self._parametros()
            if not self.editar:
                parametros.update(coberturas)
                if not self.grupo_alvo and _portas._correr_sobreposta(parametros):
                    # New framed door: track leaf thickness (18 heavy, 15 light).
                    parametros['espessura_mm'] = _portas._espessura_porta_do_trilho(parametros)
                if self.quatro_pontos and parametros['abertura'] != 'CORRER':
                    # Automatic hinge type: use coverage on its own side.
                    lado = parametros.get('dobradica_lado', 'ESQUERDA')
                    chave = _portas.COBERTURAS_LADOS[_portas.INDICE_LADO.get(lado, 0)]
                    parametros['dobradica'] = _portas._dobradica_da_cobertura(
                        float(parametros.get(chave, 1.0)),
                        _portas._porta_embutida(coberturas))
            _portas._calcular_folhas_portas(largura, altura, parametros)
            # Validate while still in Edit Mode; errors/cancellation preserve
            # both vertices and leave no incomplete objects.
            if context.mode == 'EDIT_MESH' and not self.editar:
                bpy.ops.object.mode_set(mode='OBJECT')
            if self.editar:
                frente = grupo.get('porta_frente', 'NEG_Y')
                largura_em = grupo.get('porta_largura_em', 'X')
            else:
                frente = self._frente_resolvida()
                largura_em = _portas._largura_do_vao(self._ref(), self.ponto_a,
                                             self.ponto_b)
            if grupo is not None and not self.editar:
                # Reposition: remove old links; use the new opening's parent
                # (its cabinet, if any).
                for chave in [k for k in grupo.keys()
                              if k.startswith('porta_ancora_')
                              or k.startswith('porta_vao_')
                              or k in {_portas.CHAVE_MODULO_PORTA, _portas.CHAVE_FOLGAS_PORTA,
                                       _portas.CHAVE_RECUO_PORTA, 'porta_apoio_folha'}]:
                    del grupo[chave]
                if grupo.parent != pai:
                    grupo.parent = pai
                    if pai is not None:
                        grupo.matrix_parent_inverse = pai.matrix_world.inverted()
            grupo = _portas._aplicar_portas(context, grupo, matriz, pai,
                                    largura, altura, parametros,
                                    frente=frente, largura_em=largura_em)
            if not self.editar:
                for indice, folha in ancoras.items():
                    grupo['porta_ancora_%d' % indice] = folha
            # Scenario 2: clearances to cabinet faces, expressed in
            # thickness units, make the door follow subsequent
            # cabinet resizing.
            modulo = bpy.data.objects.get(self.modulo_nome)
            if modulo is not None and not self.editar:
                medido = _portas._folgas_do_vao(modulo, *pontos, frente, largura_em)
                if medido is not None:
                    grupo[_portas.CHAVE_MODULO_PORTA] = modulo.name
                    grupo[_portas.CHAVE_FOLGAS_PORTA] = list(medido[0])
                    grupo[_portas.CHAVE_RECUO_PORTA] = medido[1]
                    # Only now does the door belong to the cabinet: include its frame
                    # in cabinet dimensions (`pecas_do_envelope`).
                    _modulos.sincronizar_medidas_conjunto(modulo)
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        for obj in context.selected_objects:
            obj.select_set(False)
        grupo.select_set(True)
        for folha in _portas._folhas_portas(grupo):
            folha.select_set(True)
        context.view_layer.objects.active = grupo
        # With a linked cabinet, make it active: the panel displays
        # assembly dimensions and the wireframe displays the cabinet
        # volume with doors in front (step 3).
        vinculado = bpy.data.objects.get(grupo.get(_portas.CHAVE_MODULO_PORTA, ''))
        if vinculado is not None:
            vinculado.select_set(True)
            context.view_layer.objects.active = vinculado
        self.report({'INFO'}, "%d leaf/leaves - opening %.1f x %.1f mm" %
                    (self.folhas, largura, altura))
        return {'FINISHED'}


def _ajustar_dobradicas_wizard(w, qtd, margem):
    """Store wizard count and margin already fitting the chosen edge
    (`_portas._ajustar_dobradicas`: no overlapping hinges)."""
    comprimento = (w['aresta']['b'] - w['aresta']['a']).length
    w['qtd'], w['margem'] = _portas._ajustar_dobradicas(comprimento, qtd, margem)


def _editar_assistente(nome, valor):
    """Like `_ferragens._editar_ferragens_selecionadas` for sidebar input,
    but during door creation: write wizard state. At the mouse-Y step,
    the next movement starts from the typed value."""
    w = _portas._assistente_porta[0]
    if w is None:
        return
    if nome == 'dobradicas_qtd' and w.get('aresta') is not None:
        _ajustar_dobradicas_wizard(w, int(valor), w['margem'])
    elif nome == 'dobradicas_qtd':
        w['qtd'] = max(_portas.LIMITES_DOBRADICAS[0],
                       min(_portas.LIMITES_DOBRADICAS[1], int(valor)))
    elif nome == 'pistoes_qtd':
        w['pqtd'] = max(_portas.LIMITES_PISTOES[0], min(_portas.LIMITES_PISTOES[1], int(valor)))
    elif nome == 'dobradicas_margem_mm' and w.get('aresta') is not None:
        _ajustar_dobradicas_wizard(w, w['qtd'], float(valor))
        w['rebase'] = True
    elif nome == 'pistoes_offset_mm' and w.get('folha'):
        w['poffset'] = _portas._pistao_do_vao(
            w['altura'], w['folha'], max(1e-3, float(valor)),
            _portas._parametros_do_wizard(w))['offset']
        w['rebase'] = True
