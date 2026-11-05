"""Wizard de criacao da porta (2 cliques + caixas) e o operador
das portas parametricas."""

import bpy, gpu, blf
from gpu_extras.batch import batch_for_shader
from bpy.props import (FloatProperty, BoolProperty, EnumProperty,
                       StringProperty, IntProperty, FloatVectorProperty)
from mathutils import Matrix, Vector
from bpy_extras import view3d_utils
from bpy.types import Operator

# usados ao CARREGAR (corpo de classe, constantes): ja' carregados antes
from . import chapas as _chapas
from . import portas as _portas
# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_eventos = _ferragens = _gaveta_eventos = _arame = _gaveta = _hud = None
_modulos = None
_gavetas = None
_areas_criacao = None

PX_CARACTERE_ASSISTENTE = 7.0    # estimativa de um caractere de 12 px
MARGEM_CAIXA_ASSISTENTE = 10.0   # px entre a caixa e a borda da viewport


def _botoes_assistente(ancora, opcoes, escala, tamanho=None, pergunta=''):
    """Botoes da caixa de escolha, ao lado de `ancora` (pixels).

    `tamanho` = (largura, altura) da regiao: a caixa INTEIRA (pergunta em
    cima, botoes embaixo) tem de caber (pedido do usuario: terminando a
    porta perto da borda, a caixa saia cortada). Sem espaco a' direita
    ela vai para a esquerda do mouse; embaixo/em cima, ela sobe/desce."""
    largura, altura, vao = 150 * escala, 26 * escala, 6 * escala
    x, y = ancora.x + 18 * escala, ancora.y - 14 * escala
    colunas, linhas = 1, len(opcoes)
    if tamanho is not None:
        margem = MARGEM_CAIXA_ASSISTENTE * escala
        cabecalho = (8 + 12 + 4) * escala if pergunta else 0
        if len(opcoes) > 4:
            # Com oito folhas, uma viewport baixa exige varias colunas.
            disponivel = max(1, tamanho[0] - 2 * margem)
            cabem = max(1, int((tamanho[1] - 2 * margem - cabecalho + vao) / (altura + vao)))
            colunas = min((len(opcoes) + cabem - 1) // cabem,
                          max(1, int((disponivel + vao) / (72 * escala + vao))))
            linhas = (len(opcoes) + colunas - 1) // colunas
            largura = min(largura, (disponivel - vao * (colunas - 1)) / colunas)
            altura = min(altura, max(1, (tamanho[1] - 2 * margem - cabecalho - vao * (linhas - 1)) / linhas))
        # o texto da pergunta pode ser mais largo que os botoes
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
    """Caixa de escolha, bolinhas do snap e o recado do passo."""
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
        # com caixa aberta a pergunta ja' esta' em cima dela; o recado no
        # mouse cobria o 2o botao
        if (estado.get('recado') and estado.get('mouse') is not None
                and not estado.get('botoes')):
            # o recado tambem nao sai cortado: perto da borda ele vai para
            # o outro lado do mouse (aqui, no desenho, o blf mede)
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
        """O ponto vem do snap NATIVO (o cursor da macro `cabinet_marcar_ponto_vao`,
        como em `gavetas.AssistenteDoVao`). Antes toda malha visivel era lida no
        clique e cada vertice projetado em Python a cada movimento do mouse."""
        w = getattr(self, '_w', None) or {}
        cursor = w.get('cursor')
        self._imantado = cursor.copy() if cursor is not None else None
        self._objeto_imantado = bpy.data.objects.get(w.get('cursor_obj') or '')

    # ------------------------------------------------ previa
    def _referencia(self, obj_a, obj_b):
        """Mesma escolha de eixos que o operador fara' depois: os do
        modulo (pai comum), ou o mundo para porta solta."""
        if not OBJECT_OT_apanhar_vao_portas._associar(self, bpy.context):
            return Matrix.Identity(3)
        return _portas._referencia_do_par(obj_a, obj_b)[0]

    def _associar(self, context):
        """Porta presa ao modulo? A corrente decide: a da porta que esta'
        sendo reposicionada, ou a da cena para porta nova."""
        alvo = bpy.data.objects.get(getattr(self, '_grupo_alvo', '') or '')
        if alvo is not None:
            return bool(alvo.get(_portas.CHAVE_MODULO_PORTA))
        return bool(getattr(context.scene, 'porta_associar', True))

    def _centro(self, obj_a, obj_b):
        """Ponto interno do movel, para saber que face olha para fora."""
        return _portas._centro_do_movel(obj_a, obj_b)

    def _cliques(self):
        """Criar e reposicionar compartilham a mesma diagonal."""
        return 2

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
        """Caixas das folhas pela diagonal, incluindo o ponto sob o cursor.

        Usa os parametros da ABA, nao um padrao fixo: o que se ve
        arrastando tem de ser a porta que vai nascer. Quando a conta
        nao fecha, guarda o motivo em `_recado` -- antes a previa
        sumia calada e o usuario nao sabia o que estava errado.
        """
        tipo = OBJECT_OT_apanhar_vao_portas
        self._recado = ''
        marcados = tipo._cantos_marcados(self)
        portas = None
        if len(marcados) >= 4:
            # Compatibilidade da API de captura antiga; a UI so' marca dois.
            (p1, o1), (a, obj_a), (b, obj_b), (p4, o4) = marcados[:4]
            obj_a, obj_b = obj_a or o1, obj_b or o4
            portas = (p1, p4)
        else:
            if len(marcados) < 2:
                return []
            (a, obj_a), (b, obj_b) = marcados[:2]
            if not getattr(self, '_grupo_alvo', ''):
                # O mesmo solver encontra as faces internas e mede a
                # cobertura ate' os dois limites clicados, sem novos gestos.
                portas = (a, b)
        obj_b = obj_b or obj_a
        # Reposicionando, os parametros sao os da porta e ela nao serve
        # de apoio para si mesma.
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
        # As mesmas espessuras que o operador vai resolver: a previa
        # tem de ser a porta que vai nascer (corrente partida = sem modulo,
        # como em `_concluir`).
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
                # com moldura a folha nasce de 18 (pesado) ou 15 (leve)
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
        self._recado = 'Vao %.0f x %.0f mm - %d folha(s)%s' % (
            largura, altura, len(folhas), ' - embutida' if embutida else '')
        if assistente is not None:
            _l, _a, e, centro = folhas[0]
            # medidas da PORTA inteira (todas as folhas): a gaveta mostra
            # assim que a area fica marcada
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
            # o translate nativo segura os eventos: a previa segue o cursor
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
            # a borda sob o mouse acende na cor da HUD
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
            # as ferragens: o arame delas, na espessura da HUD
            _arame._desenhar_arame(bpy.context, pecas_arame, pontos_arame,
                            matriz=self._w.get('matriz'))
        except Exception as e:
            print("[Archy Builder] previa do vao:", e)
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
        """(pecas do rig, pontos, fios dos pistoes abertos) da porta que o
        wizard vai criar: o ARAME das ferragens de verdade (pedido do
        usuario) -- as MESMAS que a porta monta (`_ferragens_da_porta`;
        a Reta e' o rig do usuario) --, no referencial do vao (m). Os
        pistoes so' depois que o wizard chega neles."""
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
            # e um fio ate' onde o pistao vai com a porta aberta
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
        # Abrir arquivo/fechar janela cancela por fora: sem isto handlers,
        # cursor e `_apanhando_vao` (que desliga a HUD) ficavam presos.
        self._encerrar(context)

    def invoke(self, context, event):
        self._area = context.area
        if _gaveta._eh_area_gaveta(context):
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
        area = _areas_criacao.consumir('PORTAS')

        # Com uma porta selecionada o gesto REPOSICIONA aquela porta: o
        # vao novo vem da diagonal, os parametros sao os dela.
        alvo = _portas._grupo_portas(context.object)
        if alvo is not None and not alvo.get('porta_parametros'):
            alvo = None
        self._grupo_alvo = alvo.name if alvo is not None else ''

        # Um vao de mentira so' para validar os parametros: melhor
        # recusar agora do que deixar o usuario fazer o gesto inteiro
        # e so' entao descobrir que falta escolher a dobradica.
        try:
            _portas._calcular_folhas_portas(
                1000.0, 1000.0, _gaveta._valores_portas(context.scene, alvo))
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, "%s (aba Portas)" % erro)
            return {'CANCELLED'}

        _ferragens._ferragens_selecionadas[0] = None    # criar encerra aquela selecao
        if area is None and not any(o.type == 'MESH' for o in context.visible_objects):
            self.report({'WARNING'}, "Nenhuma malha visivel para o ima")
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
        # acorda o modal quando a macro nativa confirma ou cancela
        self._timer = context.window_manager.event_timer_add(.02, window=context.window)
        self.report({'INFO'}, self._instrucao())
        self._area.header_text_set(self._instrucao())
        return {'RUNNING_MODAL'}

    # ------------------------------------------------ wizard
    RECADOS = {
        'CONFIRMAR': 'A cobertura nao bate com reta, meia nem embutida',
        'FOLHAS': 'Quantas folhas?',
        'TIPO': 'Escolha a abertura',
        # cliques metade-metade (um par no mesmo ponto, o outro nao)
        'MOLDURA': 'Os cliques nao combinam: embutida ou com moldura?',
        'BASE': 'A porta tem base (rodape) ou vai direto no chao?',
        'TRILHO': 'Trilho pesado (aluminio) ou leve (canais fresados)?',
        'EIXO': "Clique na borda das dobradicas (o tipo e' automatico)",
        'QUANTIDADE': 'Scroll: quantidade de dobradicas | clique confirma',
        'MARGEM': 'Mova em Y: distancia das quinas | clique confirma',
        'PISTOES_QTD': 'Scroll: quantidade de pistoes | clique confirma',
        'PISTOES_OFFSET': 'Posicao automatica | mova em Y para subir o '
                          'pistao | clique cria a porta',
    }
    PASSOS_CANTOS = ('1/2: primeiro canto da porta', '2/2: canto oposto da porta')
    PERGUNTAS = {'CONFIRMAR': (_portas.OPCOES_CONFIRMAR, 'As medidas estao corretas?'),
                 'FOLHAS': (_portas.OPCOES_FOLHAS, 'Quantas folhas?'),
                 'MOLDURA': (_portas.TIPOS_CORRER, 'Porta embutida ou com moldura?'),
                 'BASE': (_portas.OPCOES_BASE, 'A porta tem base?'),
                 'TRILHO': (_portas.OPCOES_TRILHO, 'Qual trilho?')}
    ETAPAS_CAIXA = ('CONFIRMAR', 'FOLHAS', 'TIPO', 'MOLDURA', 'BASE', 'TRILHO')

    def _instrucao(self):
        return 'Clique %s (Esc cancela)' % self.PASSOS_CANTOS[min(len(self._pontos), 1)]

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
            g = _portas._pistao_do_vao(w['altura'], w['folha'],
                               p=_portas._parametros_do_wizard(w))
            w['pistoes'] = True
            w['pqtd'] = _portas._qtd_pistoes_padrao(w['largura'])
            w['poffset'] = w['poffset_auto'] = g['offset']
        w['recado'] = self.RECADOS.get(etapa, '')
        # a aba Portas revela cada categoria respondida
        _eventos._redesenhar_viewports(bpy.context)
        if etapa == 'CONFIRMAR':
            fora = _portas._lados_fora_do_padrao(w['coberturas'])
            w['recado'] = 'Cobertura fora do padrao: %s' % ', '.join(
                k[len('cobertura_'):-len('_e')] for k in fora)
        self._area.header_text_set(w['recado'])
        self._area.tag_redraw()

    def _recomecar(self):
        """"Nao, marcar de novo": volta ao 1o clique."""
        self._pontos = []
        self._w.update(etapa='DIAGONAL', botoes=[], escolhas={},
                       pistoes=False, duas_bordas=False, aresta=None,
                       iniciar_snap=True)
        self._area.header_text_set(self._instrucao())
        self._area.tag_redraw()

    def _escolher(self, context, chave):
        """Resposta de uma caixa (CONFIRMAR, FOLHAS, TIPO, MOLDURA, BASE ou
        TRILHO)."""
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
            # sem base = sem rodape: a moldura vai direto no chao
            padrao = (getattr(context.scene, 'porta_rodape_mm', 0.0) if context
                      else 0.0) or _portas.PADRAO_MEDIDAS_PORTAS['porta_rodape_mm']
            escolhas['rodape_mm'] = 0.0 if chave == 'SEM' else float(padrao)
            self._ir('TRILHO')          # e o trilho: pesado ou leve?
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
                # uma opcao so': nada a perguntar
                return self._escolher_abertura(context, w['tipos'][0][0])
            self._ir('TIPO')
            return None
        return self._escolher_abertura(context, chave)

    def _metade_metade(self):
        """Limites com coberturas mistas deixam o tipo de correr explicito."""
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
                # um par clicado no mesmo ponto e o outro nao: o gesto nao
                # diz se e' embutida ou com moldura (pedido do usuario)
                self._ir('MOLDURA')
                return None
            if not w.get('embutida'):
                self._ir('BASE')        # com moldura: tem base (rodape)?
                return None
            return self._criar(context)
        w['tipo'] = chave
        if w['embutida']:
            escolhas['dobradica'] = 'SUPER_CURVA'
        w['duas_bordas'] = chave == 'GIRO' and escolhas.get('folhas', 1) > 1
        if w['duas_bordas'] or chave == 'BASCULANTE':
            # sem perguntar a borda: duas folhas de giro levam dobradicas
            # nas DUAS; o basculante, sempre na de CIMA (pedido do usuario)
            w['arestas'] = _portas._arestas_da_porta(w['largura'], w['altura'],
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
        chave = _portas.COBERTURAS_LADOS[_portas.INDICE_LADO[aresta['lado']]]
        w['escolhas'].update(
            dobradica=_portas._dobradica_da_cobertura(
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
        """Tudo depois dos cantos. Devolve o resultado do modal."""
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
                w['recado'] = '%d dobradicas (scroll) | clique confirma' % w['qtd']
            else:
                w['pqtd'] = max(_portas.LIMITES_PISTOES[0],
                                min(_portas.LIMITES_PISTOES[1], w['pqtd'] + passo))
                w['recado'] = '%d pistao(oes) (scroll) | clique confirma' % w['pqtd']
            _eventos._redesenhar_viewports(context)       # a gaveta mostra o numero
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
                    w['recado'] = 'Dobradicas na borda %s: %s' % (
                        lado.lower(), _portas.NOME_DOBRADICA[_portas._dobradica_da_cobertura(
                            fracao, w['embutida'])])
                else:
                    w['recado'] = self.RECADOS['EIXO']
                # a gaveta mostra o tipo da borda sob o mouse
                _eventos._redesenhar_viewports(context)
            elif etapa in {'MARGEM', 'PISTOES_OFFSET'}:
                if w.pop('rebase', False):
                    # valor digitado na gaveta: o mouse parte dele
                    w['y0'] = mouse.y
                    w['valor0'] = (w['margem'] if etapa == 'MARGEM'
                                   else w['poffset'])
                delta = (mouse.y - w['y0']) * w['mm_por_px']
                if etapa == 'MARGEM':
                    _ajustar_dobradicas_wizard(w, w['qtd'], w['valor0'] + delta)
                    w['recado'] = 'Margem %.0f mm | clique confirma' % w['margem']
                else:
                    # de cima para baixo: descer o mouse aumenta o offset,
                    # mas so' ate' onde o pistao alcanca com a porta aberta
                    g = _portas._pistao_do_vao(w['altura'], w['folha'],
                                       max(1e-3, w['valor0'] - delta),
                                       _portas._parametros_do_wizard(w))
                    w['poffset'] = g['offset']
                    limite = g['offset'] >= g['offset_max'] - 0.5
                    w['recado'] = ('Pistao %.0f mm a %.0f mm do topo%s | '
                                   'clique cria' % (
                                       g['aberto'], g['offset'],
                                       ' (curso maximo)' if limite else ''))
                _eventos._redesenhar_viewports(context)   # margem/offset na gaveta
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
        """Clique na viewport OU "Confirmar" da gaveta (pedido do usuario:
        quantidade e afastamento tambem se confirmam la'). Sem `mouse`
        (veio da gaveta), a etapa seguinte parte do mouse na viewport
        quando ele voltar (`rebase`), nao de onde ele estava."""
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
        """Botao direito: uma etapa para tras."""
        w = self._w
        etapa = w['etapa']
        if w.get('area_livre') and etapa in {'CONFIRMAR', 'FOLHAS'}:
            self._ir('FOLHAS')
            return
        if etapa in {'CONFIRMAR', 'FOLHAS'}:
            # Conserva o primeiro canto para remarcar so' o oposto.
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
            # na automatica grava 0: o pistao acompanha o modulo redimensionado
            manual = abs(w['poffset'] - w.get('poffset_auto', 0.0)) > 0.5
            extras.update(pistoes_qtd=w['pqtd'],
                          pistoes_offset_mm=float(w['poffset']) if manual else 0.0)
        return self._concluir(context, extras)

    def _responder_pela_gaveta(self, context, pergunta, chave):
        """Fila da aba Portas = a caixa da viewport (pedido do usuario).
        Responder de novo uma pergunta ja' respondida refaz dali: o que
        vinha depois dela cai."""
        w = self._w
        if pergunta in {'dobradicas_qtd', 'pistoes_qtd'}:
            _editar_assistente(pergunta, chave)    # so' o valor; nao avanca
            return None
        if pergunta == _portas.CONFIRMAR_ETAPA:
            # o botao de uma etapa que ja' passou nao vale
            return (self._confirmar_etapa(context) if chave == w['etapa']
                    else None)
        if pergunta == 'porta_confirmar':
            if w['etapa'] != 'CONFIRMAR':
                return None
            return self._escolher(context, chave)
        if pergunta == 'porta_tipo_correr':
            if w['etapa'] not in {'MOLDURA', 'BASE'}:
                return None
            w['etapa'] = 'MOLDURA'          # respondida de novo: refaz dali
            return self._escolher(context, chave)
        if pergunta == 'porta_base':
            if w['etapa'] not in {'BASE', 'TRILHO'}:
                return None
            w['etapa'] = 'BASE'             # respondida de novo: refaz dali
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
            # o retrato da abertura ja' escolhida (linha das dobradicas):
            # volta a' escolha, com as tres a' vista
            w['escolhas'] = {'folhas': folhas}
            self._ir('TIPO')
            return None
        w.update(escolhas={'folhas': folhas}, etapa='TIPO')
        return self._escolher_abertura(context, chave)

    def modal(self, context, event):
        try:
            return OBJECT_OT_apanhar_vao_portas._modal(self, context, event)
        except Exception:
            # erro no meio prendia handlers, timer, snap e a HUD desligada
            self._encerrar(context)
            raise

    def _modal(self, context, event):
        w = self._w
        if w.get('cancelar'):           # Esc/direito no translate nativo
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
            # etapa nova: a aba Portas rola ate' ela (nasce no fim)
            self._etapa_vista = self._w.get('etapa')
            _gaveta._rolar_ate_o_fim(context)
        if (event.type == 'LEFTMOUSE' and event.value == 'RELEASE'
                and self._engolir_soltar):
            # o soltar do clique que respondeu pela gaveta: a fila ja'
            # mudou e ele cairia noutro widget
            self._engolir_soltar = False
            return {'RUNNING_MODAL'}
        gaveta = (_gaveta_eventos._gaveta_sob_evento(context, event)
                  if event.type != 'ESC' else None)
        if gaveta is not None:
            # Na gaveta o mouse e' DELA (hover, abas, rolagem, campos); o
            # wizard so' atende as filas que copiam a caixa da viewport.
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
            return self._marcar_canto(context, event)
        return {'RUNNING_MODAL'}

    def _iniciar_snap(self, context):
        # o protocolo comum do snap nativo (corrigir la', nao copiar)
        _gavetas.AssistenteDoVao._iniciar_snap_nativo(self, context)

    def _marcar_canto(self, context, event):
        """Aceita o ponto do snap como o proximo canto."""
        if self._imantado is None or self._objeto_imantado is None:
            # sem a peca o vao nao tem eixos nem modulo
            self.report({'WARNING'}, "Clique num vertice de uma chapa")
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
            # reposicionar: so' a diagonal, com os parametros da porta
            return self._concluir(context)
        # porta nova: o wizard segue (folhas, tipo, borda, ferragens)
        self._w['matriz'] = None
        self._previa()
        if self._w.get('matriz') is None:
            self.report({'WARNING'}, self._recado or "Vao invalido")
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
        # Cenario 2: o canto do vao caiu numa chapa, entao o vao
        # pertence ao modulo que a contem e a porta fica vinculada a ele.
        modulo = _portas._modulo_da_chapa(obj_a)
        if not self._associar(context):
            # corrente partida: porta solta, eixos do mundo, sem pai
            referencia, pai, modulo = Matrix.Identity(3), None, None
        ativa = obj_a.matrix_world.to_quaternion().to_matrix()
        s = context.scene
        parametros = _portas._parametros_portas_da_cena(s)
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
    area_definida: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})
    matriz_area: FloatVectorProperty(size=16, options={'HIDDEN', 'SKIP_SAVE'})
    medidas_area: FloatVectorProperty(size=2, options={'HIDDEN', 'SKIP_SAVE'})
    ponto_a: FloatVectorProperty(size=3, options={'HIDDEN'})
    ponto_b: FloatVectorProperty(size=3, options={'HIDDEN'})
    # API legada de cobertura explicita. No wizard de dois cliques os
    # mesmos limites iniciam porta/vao; o solver acha as faces internas.
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
    abertura: EnumProperty(name="Abertura", items=_portas.ITENS_ABERTURA,
                           default='GIRO', update=_portas._limitar_folhas_portas)
    folhas: IntProperty(name="Folhas", default=1, min=1, max=8,
                        update=_portas._limitar_folhas_portas)
    dobradica: EnumProperty(name="Dobradica / posicionamento",
                            items=_portas.ITENS_DOBRADICA, default='RETA')
    # So' o padrao quando o vao nao tem chapa nem modulo: no resto as
    # duas vem de `_espessura_do_vao` / `_espessura_da_porta_nova`.
    espessura_mm: EnumProperty(
        name="Espessura da porta (mm)", default='18',
        options={'HIDDEN', 'SKIP_SAVE'},
        items=[(str(int(e)), str(int(e)), "mm") for e in _chapas.ESPESSURAS_PERMITIDAS])
    lateral_mm: EnumProperty(
        name="Espessura da lateral (mm)", default='18',
        options={'HIDDEN', 'SKIP_SAVE'},
        items=[(str(int(e)), str(int(e)), "mm") for e in _chapas.ESPESSURAS_PERMITIDAS])
    # sem campo (sempre zero); fica para quem chama com ela (importacao)
    folga_mm: FloatProperty(name="Folga no perimetro (mm)", default=0, min=0,
                            options={'HIDDEN', 'SKIP_SAVE'})
    entre_folhas_mm: FloatProperty(name="Folga entre folhas (mm)", default=2, min=0)
    afastamento_mm: FloatProperty(name="Afastamento frontal (mm)", default=0, min=0)
    recuo_embutida_mm: FloatProperty(name="Recuo da embutida (mm)", default=0, min=0)
    recuo_correr_mm: FloatProperty(
        name="Recuo para trilhos (mm)", default=30, min=0.1,
        description="Distancia da borda frontal ate a face externa da primeira folha")
    entre_planos_mm: FloatProperty(name="Folga entre planos (mm)", default=2, min=0.1)
    # moldura do correr (`_portas._pecas_moldura`)
    moldura_mm: FloatProperty(
        name="Espessura da moldura (mm)", min=1.0,
        default=_portas.PADRAO_MEDIDAS_PORTAS['porta_moldura_mm'])
    rodape_mm: FloatProperty(
        name="Rodape (mm)", min=0.0,
        default=_portas.PADRAO_MEDIDAS_PORTAS['porta_rodape_mm'])
    testeira_mm: FloatProperty(
        name="Testeira (mm)", min=0.0,
        default=_portas.PADRAO_MEDIDAS_PORTAS['porta_testeira_mm'])
    trilho: EnumProperty(name="Trilho", items=_portas.ITENS_TRILHO,
                         default='PESADO')
    folha: EnumProperty(name="Folha", items=_portas.ITENS_FOLHA_CORRER,
                        default='CHAPA')
    # resposta do "embutida ou com moldura?" (cliques metade-metade)
    tipo_correr: EnumProperty(
        name="Correr", default='AUTO', options={'HIDDEN', 'SKIP_SAVE'},
        items=[('AUTO', "Pelos cliques", "")]
        + [(k, t, "") for k, t in _portas.TIPOS_CORRER])
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
            # corrente partida: solta, nos eixos do mundo (o centro do
            # movel ainda serve para saber que face olha para fora)
            self.referencia = tuple(v for linha in Matrix.Identity(3)
                                    for v in linha)
            self.pai_nome = self.modulo_nome = ''
        if modulo is not None:
            self.centro = _portas._centro_do_movel(obj_a, obj_b)
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
            # reposicionar mantem a cobertura de cada lado
            guardados = alvo['porta_parametros']
            p.update({k: float(guardados[k]) for k in _portas.COBERTURAS_LADOS
                      if k in guardados})
            p['lateral_mm'] = _portas._espessura_do_vao(
                bpy.data.objects.get(self.modulo_nome), self._objetos(),
                p['lateral_mm'])
            return p
        if self.editar:
            # Reconfigurar nao mexe em espessura: a da porta vive no E
            # das folhas e a da lateral, no modulo.
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
                    raise ValueError("Selecione um grupo de portas no Modo Objeto")
                self.grupo_nome = grupo.name
                for nome, valor in grupo['porta_parametros'].items():
                    if nome in {'espessura_mm', 'lateral_mm'}:
                        # o enum so' tem as convencionais; espessura livre
                        # (25, 70...) vem do grupo em `_parametros`
                        texto = str(int(valor))
                        if float(valor) in _chapas.ESPESSURAS_PERMITIDAS:
                            setattr(self, nome, texto)
                    elif nome in _portas._PARAMETROS_PORTAS:
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
        layout.label(text="Permitido: 1 a %d folha(s)" % _portas.LIMITES_FOLHAS[self.abertura])
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
            layout.label(text="Embutidas, uma em cada trilho")
            layout.prop(self, 'recuo_correr_mm')
            if self.folhas > 1:
                layout.prop(self, 'entre_planos_mm')
        if largura is not None:
            try:
                folhas = _portas._calcular_folhas_portas(largura, altura, self._parametros())
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
                grupo = bpy.data.objects.get(self.grupo_nome) if self.grupo_nome else _portas._grupo_portas(context.object)
                if grupo is None or _chapas.MARCA_PORTAS not in grupo:
                    raise ValueError("Grupo de portas nao encontrado")
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
                    raise ValueError("O pai do vao tem escala zero")
                grupo = (bpy.data.objects.get(self.grupo_alvo)
                         if self.grupo_alvo else None)
            parametros = self._parametros()
            if not self.editar:
                parametros.update(coberturas)
                if not self.grupo_alvo and _portas._correr_sobreposta(parametros):
                    # porta nova com moldura: folha do trilho (18 pesado, 15 leve)
                    parametros['espessura_mm'] = _portas._espessura_porta_do_trilho(parametros)
                if self.quatro_pontos and parametros['abertura'] != 'CORRER':
                    # dobradica automatica: a cobertura do lado dela
                    lado = parametros.get('dobradica_lado', 'ESQUERDA')
                    chave = _portas.COBERTURAS_LADOS[_portas.INDICE_LADO.get(lado, 0)]
                    parametros['dobradica'] = _portas._dobradica_da_cobertura(
                        float(parametros.get(chave, 1.0)),
                        _portas._porta_embutida(coberturas))
            _portas._calcular_folhas_portas(largura, altura, parametros)
            # Validacoes ocorrem ainda em Edit Mode; erro/cancelamento
            # conserva os dois vertices e nao deixa objetos incompletos.
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
                # Reposicionar: vinculos antigos saem; o pai passa a ser o
                # do vao novo (o modulo dele, se houver).
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
            # Cenario 2: as folgas ate' as faces do modulo, em
            # espessuras, sao o que mantem a porta acompanhando o
            # redimensionamento depois.
            modulo = bpy.data.objects.get(self.modulo_nome)
            if modulo is not None and not self.editar:
                medido = _portas._folgas_do_vao(modulo, *pontos, frente, largura_em)
                if medido is not None:
                    grupo[_portas.CHAVE_MODULO_PORTA] = modulo.name
                    grupo[_portas.CHAVE_FOLGAS_PORTA] = list(medido[0])
                    grupo[_portas.CHAVE_RECUO_PORTA] = medido[1]
                    # so' agora a porta e' "do modulo": a moldura entra nas
                    # medidas dele (`pecas_do_envelope`)
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
        # Com modulo vinculado, ele vira o ativo: o painel passa a
        # mostrar as medidas do conjunto e o wireframe a volumetria do
        # modulo com as portas na frente (etapa 3).
        vinculado = bpy.data.objects.get(grupo.get(_portas.CHAVE_MODULO_PORTA, ''))
        if vinculado is not None:
            vinculado.select_set(True)
            context.view_layer.objects.active = vinculado
        self.report({'INFO'}, "%d folha(s) - vao %.1f x %.1f mm" %
                    (self.folhas, largura, altura))
        return {'FINISHED'}


def _ajustar_dobradicas_wizard(w, qtd, margem):
    """Grava quantidade e margem do wizard ja' cabendo na borda escolhida
    (`_portas._ajustar_dobradicas`: nenhuma sobre a outra)."""
    comprimento = (w['aresta']['b'] - w['aresta']['a']).length
    w['qtd'], w['margem'] = _portas._ajustar_dobradicas(comprimento, qtd, margem)


def _editar_assistente(nome, valor):
    """Como `_ferragens._editar_ferragens_selecionadas` (valor digitado na
    gaveta), mas criando a porta: grava no estado do wizard. Na etapa do
    mouse em Y, o 1o movimento depois parte do valor digitado."""
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
