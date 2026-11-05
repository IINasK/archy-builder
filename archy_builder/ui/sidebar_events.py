"""Gaveta: eventos -- cliques, edicao de medidas, abrir/fechar a area --
e o grupo de gizmos (alca, icones e hover) que dispara o desenho."""

import bpy
from bpy.props import FloatProperty, StringProperty
from bpy.types import Gizmo, GizmoGroup, Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = None
_alvenaria = None
_instalacoes = _esquadrias = None
_iluminacao = None
_biblioteca = None
_opcoes = None
_eventos = None
_portas = None
_ferragens = None
_assistente = None
_importacao = None
_puxadores = None
_gaveta = None
_orcamento = None
_hud = None
_solda = None
_perguntas = None
_gaveta_desenho = None
_materiais = None
_gavetas = None
_prateleiras = None
_divisorias = _fundos = None
_formas = None
_biblioteca_faixa = None
_paredes_edicao = None
_editor = None
_areas_criacao = None
_paredes_composicao = None
_paredes = None
_ambientes = None

def _gaveta_sob_evento(context, event):
    """(area, regiao) da gaveta se o mouse do evento esta' nela, senao
    None. Para os modais (wizard, posicionador): a gaveta continua sendo
    da gaveta enquanto eles rodam."""
    areas = (_gaveta._area_gaveta(context.screen),
             _biblioteca_faixa.area_da_faixa(context.screen)) if context.screen else ()
    for area in areas:
        regiao = next((r for r in area.regions if r.type == 'WINDOW'),
                      None) if area is not None else None
        if regiao is not None:
            x, y = event.mouse_x - regiao.x, event.mouse_y - regiao.y
            if 0 <= x < regiao.width and 0 <= y < regiao.height:
                return area, regiao
    return None


def _limite_duplo_clique(context):
    try:
        return context.preferences.inputs.mouse_double_click_time
    except Exception:
        return 350


def _objeto_sob_mouse(context, event):
    """NOME do objeto sob o mouse numa viewport que nao e' a gaveta (o
    mesmo raio do clique da HUD), ou ''. Nome, nunca o objeto: quem chama
    e' modal (ver `_larga_dados_ao_terminar`)."""
    for area in context.screen.areas:
        if area.type != 'VIEW_3D' or _gaveta._eh_area_gaveta_bruto(area):
            continue
        regiao = next((r for r in area.regions if r.type == 'WINDOW'), None)
        if regiao is None:
            continue
        x, y = event.mouse_x - regiao.x, event.mouse_y - regiao.y
        if 0 <= x < regiao.width and 0 <= y < regiao.height:
            with context.temp_override(area=area, region=regiao):
                atingido = _hud._raio_hud(context, (x, y))
            return atingido[0].name if atingido is not None else ''
    return ''


def _acao_da_gaveta(context, event, area, regiao):
    """A acao do widget da gaveta sob o mouse (o mesmo hit-test dela)."""
    x, y = event.mouse_x - regiao.x, event.mouse_y - regiao.y
    with context.temp_override(area=area, region=regiao):
        for wx, wy, w, h, _rotulo, acao in _gaveta._widgets_interativos(context):
            if _biblioteca_faixa.caixa_categoria(acao):
                continue
            if acao and wx <= x <= wx + w and wy <= y <= wy + h:
                return acao
    return None


class OBJECT_OT_editar_medida_gaveta(Operator):
    """Edita uma medida usando a mesma propriedade parametrica do painel N."""
    bl_idname = 'object.cabinet_editar_medida_gaveta'
    bl_label = 'Editar Medida'
    bl_options = {'REGISTER', 'UNDO'}

    dono: StringProperty(options={'SKIP_SAVE'})
    objeto: StringProperty(options={'SKIP_SAVE'})
    propriedade: StringProperty(options={'SKIP_SAVE'})
    valor: FloatProperty(name='Medida', subtype='DISTANCE', unit='LENGTH',
                         min=0.0, options={'SKIP_SAVE'})

    def invoke(self, context, event):
        if _gaveta._edicao_gaveta[0] is not None:
            return {'CANCELLED'}
        self._area = context.area
        texto = (_gaveta._texto_faixa(self.valor)[:-3] if self.dono == 'opcao'
                 else str(int(round(self.valor))) if self.dono == 'contador'
                 else _opcoes._numero_na_unidade(self.valor * 1000.0))
        self._estado = {'area': context.area.as_pointer(),
                        'propriedade': self.propriedade, 'texto': texto,
                        'cursor': len(texto), 'selecionado': False,
                        'medida':self.dono not in {'opcao','contador'}}
        _gaveta._edicao_gaveta[0] = self._estado
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _encerrar(self):
        _gaveta._edicao_gaveta[0] = None
        self._area.tag_redraw()

    def cancel(self, context):
        self._encerrar()

    def modal(self, context, event):
        if _gaveta._edicao_gaveta[0] is not self._estado:
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
                self.valor = (_gaveta_desenho._ler_numero_digitado(self._estado['texto'])
                              if self.dono in {'opcao', 'contador'} else
                              _gaveta_desenho._ler_medida_digitada(
                                  self._estado['texto'],
                                  # o mesmo piso do arraste: curva/folga aceitam 0
                                  0.0 if self.dono in DONOS_DE_PARAMETRO else 0.001))
            except (ValueError, TypeError) as e:
                self.report({'WARNING'}, str(e))
                return {'RUNNING_MODAL'}
            resultado = self.execute(context)
            self._encerrar()
            return resultado
        entrada = (context.window_manager.clipboard
                   if event.ctrl and event.type == 'V'
                   else '' if event.ctrl else event.unicode or '')
        if _gaveta_desenho._tecla_no_texto(self._estado, event.type, entrada, event.ctrl, getattr(event, 'shift', False)):
            self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _clique_no_campo(self, context, event):
        """Clique DENTRO do campo em edicao: so' move o cursor (fora dele,
        confirma). As posicoes saem do mesmo calculo do desenho."""
        estado = self._estado
        mx, my = event.mouse_region_x, event.mouse_region_y
        try:
            widgets = _gaveta._widgets_interativos(context)
        except Exception:
            return False
        for x, y, w, h, _r, acao in widgets:
            if not acao or not (x <= mx <= x + w and y <= my <= y + h):
                continue
            # o campo de contador (Folhas) se desenha como o de medida
            campo = acao[0] == 'medida' or _gaveta_desenho._eh_campo_contador(acao)
            if not (acao[0] == 'medida' and acao[2] == estado['propriedade']
                    or acao[0] in {'faixa', 'contador'}
                    and acao[1] == estado['propriedade']):
                continue
            texto, cursor = estado['texto'], estado['cursor']
            mostrado = _gaveta_desenho._com_cursor(texto, cursor,medida=estado.get('medida',False))
            disponivel = w - (14 if campo else 12)
            tamanho = next((t for t in range(12, 8, -1)
                            if _gaveta_desenho._medidor_blf(t)(mostrado) <= disponivel), 9)
            largura = _gaveta_desenho._medidor_blf(tamanho)
            x_texto = (x + 7 if campo
                       else x + (w - min(largura(mostrado), disponivel)) / 2)
            pos = _gaveta_desenho._cursor_no_x(texto, cursor, x_texto, mx, largura,medida=estado.get('medida',False))
            _gaveta_desenho._posicionar_cursor_texto(estado, pos, getattr(event, 'shift', False))
            return True
        return False

    def execute(self, context):
        erro = aplicar_medida(context, self.dono, self.objeto,
                              self.propriedade, self.valor)
        if erro:
            self.report({'WARNING'}, erro)
            return {'CANCELLED'}
        # A previa pertence ao undo da criacao, nao a cada valor digitado.
        if self.dono=='solda_criacao':return {'CANCELLED'}
        return {'FINISHED'}


def aplicar_medida(context, dono, objeto, propriedade, valor, previa=False):
    """Grava `valor` (METROS) no dono da medida; devolve o erro ou None.
    Serve a' digitacao e ao ARRASTE do campo (pedido do usuario: arrastar
    de lado muda o valor) -- que nao pode empilhar um undo por pixel."""
    if dono=='solda_criacao':return _solda.editar_criacao_solda(valor,indice=int(propriedade) if propriedade.isdigit() else None)
    if dono=='solda':return _solda.editar_distancia_solda(objeto,propriedade,valor)
    if dono == 'instalacao':
        grupo = _alvenaria.grupo_de(bpy.data.objects.get(objeto))
        return _instalacoes.editar_cota(grupo, propriedade, valor) if grupo else 'Instalacao nao encontrada'
    if dono == 'instalacao_tamanho':
        grupo = _alvenaria.grupo_de(bpy.data.objects.get(objeto))
        return _instalacoes.editar_medida(grupo, int(propriedade), valor) if grupo else 'Instalacao nao encontrada'
    if dono == 'forro':
        grupo = _alvenaria.grupo_de(bpy.data.objects.get(objeto))
        return _iluminacao.editar_forro(grupo, propriedade, valor) if grupo else 'Forro nao encontrado'
    if dono == 'parede_modulo':
        return _paredes_composicao.editar_modulo(context, objeto, propriedade, valor * 1000)
    if dono == 'parede_guia':
        return _paredes_composicao.editar_guia(context, int(propriedade), valor * 1000)
    if dono in {'livre', 'objeto', 'cota'} and _paredes_composicao.parede(bpy.data.objects.get(objeto)):
        return 'As medidas da parede sao editadas apenas pelas ferramentas nativas do Blender'
    if dono == 'paredes':
        return _paredes_edicao.editar_parametro(propriedade, valor * 1000)
    if dono == 'opcao':
        # Faixa da engrenagem: numero puro, preso ao minimo e maximo
        minimo, maximo, _passo = _opcoes.FAIXAS_OPCOES[propriedade]
        valor = max(minimo, min(maximo, valor))
        _opcoes._definir_opcao(propriedade, int(round(valor))
                               if isinstance(minimo, int) else round(valor, 2))
        return None
    if dono=='cota':
        alvo=bpy.data.objects.get(objeto)
        if alvo is None:return 'Objeto da cota nao encontrado'
        try:_hud._aplicar_valor_hud(context,_hud.alvo_cota(alvo,propriedade),valor*1000)
        except (ValueError,TypeError,KeyError) as erro:return str(erro)
        return None
    if dono == 'contador':
        # campo de contador digitado (Folhas da porta): numero inteiro;
        # `objeto` = o alvo do contador
        return _aplicar_contador(context, ('contador', propriedade, None,
                                           None, None, objeto),
                                 int(round(valor)))
    if dono == 'puxador' and propriedade.startswith('puxp_'):
        # parametrico: grava o estado e deixa a chapa reposicionar
        pux = bpy.data.objects.get(objeto)
        if not _puxadores._eh_puxador_parametrico(pux):
            return 'Puxador nao encontrado'
        pux['puxador_%s_mm' % propriedade[len('puxp_'):]] = valor * 1000.0
        _puxadores.posicionar_puxador(pux)
        return None
    if dono == 'puxador':
        pux = bpy.data.objects.get(objeto)
        try:
            _importacao._redimensionar_puxador(pux, int(propriedade[-1]),
                                               valor * 1000.0)
        except (ValueError, TypeError, AttributeError) as erro:
            return str(erro)
        return None
    if dono == 'assistente':
        # criando a porta: vai para o estado do wizard
        # FloatProperty e' float de 32 bits: 0.08 m voltava 79.9999982
        _assistente._editar_assistente(propriedade, round(valor * 1000.0, 3))
        _eventos._redesenhar_viewports(context)
        return None
    if dono == 'ferragens':
        return _ferragens._editar_ferragens_selecionadas(
            context, propriedade, round(valor * 1000.0, 3)) or None
    if dono == 'forma':
        # modulo em L/diagonal/curvo: 'P1:2' -> ('P1', 2)
        conj = bpy.data.objects.get(objeto)
        if conj is None or conj.type!='MESH':
            return 'Selecione uma chapa individual para editar seu formato'
        letra, canto = propriedade.split(':')
        if _formas.forma_do_modulo(conj) is None:
            return 'O modulo nao tem mais esse formato'
        _formas.aplicar(context, conj, (letra, int(canto)), valor * 1000.0)
        return None
    if dono == 'area_criacao':
        return _areas_criacao.aplicar(context, _areas_criacao.objeto(), (propriedade,), valor * 1000)
    if dono == 'fundos':
        try:
            _fundos.editar(context, bpy.data.objects.get(objeto), propriedade, valor*1000)
        except ValueError as erro:
            return str(erro)
        return None
    if dono in ('gavetas', 'prateleiras', 'divisorias'):
        sistema = {'gavetas': _gavetas, 'prateleiras': _prateleiras, 'divisorias': _divisorias}[dono]
        grupo = sistema.grupo_de(bpy.data.objects.get(objeto))
        if grupo is None:
            return '%s nao encontradas' % dono.capitalize()
        if dono=='gavetas' and propriedade.startswith('individual_'):
            _prefixo,indice,nome=propriedade.split('_',2)
            return _gavetas.editar_individual(context,grupo,int(indice),nome,valor*1000,previa=previa)
        if propriedade in ('largura', 'altura'):
            return sistema.aplicar(context, grupo, ('L' if propriedade == 'largura'
                                                    else 'A',), valor * 1000.0)
        return sistema.editar(context, grupo, propriedade, valor * 1000.0)
    if dono == 'porta':
        # Porta colocada: a medida e' um parametro do GRUPO, nao uma
        # propriedade de objeto ou da cena.
        grupo = _portas._grupo_portas(bpy.data.objects.get(objeto))
        nome = _portas._PARAMETRO_DA_MEDIDA_PORTA.get(propriedade)
        if grupo is None or not nome:
            return 'Porta da medida nao encontrada'
        return _portas._editar_parametro_porta(context, grupo, nome,
                                               valor * 1000.0) or None
    alvo = (context.scene if dono == 'cena'
            else bpy.data.objects.get(objeto))
    if alvo is None:
        return 'Alvo da medida nao encontrado'
    if dono == 'livre' and propriedade.startswith('dimensions_'):
        dimensoes = list(alvo.dimensions)
        dimensoes[int(propriedade[-1])] = valor
        alvo.dimensions = dimensoes
        return None
    if not hasattr(alvo, propriedade):
        return 'Propriedade da medida nao encontrada'
    setattr(alvo, propriedade, valor)
    return None


# ---- ARRASTAR um campo de valor (pedido do usuario): clicar e arrastar
# de lado muda o numero -- direita aumenta, esquerda diminui -- como os
# campos do Blender. Sem arrastar, o clique abre a digitacao como antes.
# Shift = fino, Ctrl = grosso. Um undo so', no fim; Esc devolve.
METROS_POR_PX = 0.001            # 1 mm por pixel
FATOR_FINO, FATOR_GROSSO = 0.1, 10.0
PX_POR_UNIDADE_CONTADOR = 24     # contador (dobradicas, pistoes)
# medidas que podem chegar a zero (afastamentos, folgas); o resto
# (largura, espessura...) para em 1 mm
DONOS_DE_PARAMETRO = {'assistente', 'ferragens', 'porta', 'opcao', 'gavetas',
                      'prateleiras', 'divisorias', 'fundos', 'paredes', 'parede_modulo',
                      'solda_criacao', 'solda', 'instalacao'}


def _passo_do_arraste(event):
    return METROS_POR_PX * (FATOR_FINO if event.shift else
                            FATOR_GROSSO if event.ctrl else 1.0)


def _aplicar_contador(context, acao, valor):
    """Contador da gaveta (quantidade de dobradicas/pistoes): o wizard ou
    as ferragens selecionadas; com o NOME de um grupo de portas no alvo,
    as folhas daquela porta. Devolve o erro ou None."""
    prop, alvo = acao[1], acao[5]
    if prop == _paredes_edicao.ALVO_QUANTIDADE:
        return _paredes_edicao.editar_parametro('quantidade', valor)
    grupo = (bpy.data.objects.get(alvo)
             if alvo not in {_portas.ALVO_ASSISTENTE, _gaveta.ALVO_FERRAGENS}
             else None)
    if alvo == _portas.ALVO_ASSISTENTE:
        _assistente._editar_assistente(prop, valor)
        erro = None
    elif prop.startswith('forma_angulo_') and grupo is not None:
        if grupo.type!='MESH':
            return 'Selecione uma chapa individual para editar seu formato'
        _formas.aplicar(context, grupo, ('ANG', int(prop.rsplit('_', 1)[1])),
                        float(valor))
        erro = None
    elif grupo is not None and _gavetas.MARCA_GRUPO in grupo:
        erro = _gavetas.editar(context, grupo, prop, valor)
    elif grupo is not None and _prateleiras.MARCA_GRUPO in grupo:
        erro = _prateleiras.editar(context, grupo, prop, valor, somente_grupo=True)
    elif grupo is not None and _prateleiras.MARCA_PRATELEIRA in grupo:
        erro = _prateleiras.editar_quantidade_local(context, _prateleiras.grupo_de(grupo), grupo, valor)
    elif grupo is not None:
        # digitado pode vir qualquer numero: o limite e' o da abertura
        parametros = dict(grupo.get('porta_parametros') or {})
        limite = _portas.LIMITES_FOLHAS.get(parametros.get('abertura'), 1)
        minimo = 2 if parametros.get('abertura') == 'ZIGZAG' else 1
        if prop == 'porta_folhas' and not minimo <= valor <= limite:
            return 'Esta abertura aceita de %d a %d folha(s)' % (minimo, limite)
        erro = _portas._editar_parametro_porta(
            context, grupo, prop[len('porta_'):], valor) or None
    else:
        erro = _ferragens._editar_ferragens_selecionadas(context, prop, valor)
    _eventos._redesenhar_viewports(context)
    return erro


def _eh_modelo_do_criador(it):
    return bool(it.get('fabrica')) or (
        _biblioteca._niveis_de(it)[0] == _puxadores.CATEGORIA_PUXADORES)


def _modelo_do_criador(op, context, it, indice):
    """Clique num modelo do criador na biblioteca (foto ou icone). O de
    PUXADOR, na foto ou no Inserir do clique direito, abre o "Criar Puxador" com ele --
    funcional, nao so' o 3D (o arrasto nativo do Asset Browser traz so' o
    3D): devolve 'CRIAR' e quem chama abre no SOLTAR. O de fabrica e'
    protegido: "Edit." e cadeado so' avisam. O do usuario edita e trava
    como qualquer item."""
    fabrica = it.get('fabrica')
    if indice != 0:
        if fabrica:
            op.report({'INFO'}, "Modelo de fabrica: protegido")
        elif indice == 1:
            if not _biblioteca.item_bloqueado(it):
                _editor.executar(context, 'object.cabinet_editar_modelo',
                    pasta=it['pasta'], arquivo=it['arquivo'])
        else:
            bpy.ops.object.cabinet_bloqueio(pasta=it['pasta'],
                                            arquivo=it['arquivo'])
        return None
    if fabrica == 'dobradica':
        op.report({'INFO'}, "A dobradica entra com a porta: Criar Portas")
        return None
    if fabrica:
        _puxadores.escolher_modelo(context.scene, it['valor'])
    else:
        _puxadores.escolher_modelo(context.scene, 'MODELO', it['arquivo'])
    context.scene.cabinet_aba = 'PUXADORES'
    return 'CRIAR'


class OBJECT_OT_interagir_gaveta(Operator):
    """Recebe clique e arraste diretamente na interface independente."""
    bl_idname = "object.cabinet_interagir_gaveta"
    bl_label = "Interagir com Gaveta Archy Builder"
    dica: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        return properties.dica or cls.bl_label

    @classmethod
    def poll(cls, context):
        return _gaveta._eh_area_gaveta(context)

    def _botao_direito(self, context, event):
        """Foto/nome do modulo: menu no soltar; material: pintura rapida."""
        x, y = event.mouse_region_x, event.mouse_region_y
        acao = next((a for wx, wy, w, h, _r, a in _gaveta._widgets_interativos(context)
                     if a and a[0] in ('material', 'preset')
                     and wx <= x <= wx + w and wy <= y <= wy + h), None)
        if acao is None:
            return {'FINISHED'} if _biblioteca_faixa.eh_faixa(context) else {'PASS_THROUGH'}
        if acao[0] == 'preset':
            self._menu_item = dict(acao[1])
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        if not _materiais.perguntar_pintar(context, acao[1]):
            self.report({'WARNING'}, "Nenhum modulo na cena para pintar")
        context.area.tag_redraw()
        return {'FINISHED'}

    def invoke(self, context, event):
        if event.type in {'MIDDLEMOUSE', 'TRACKPADZOOM'}:
            return {'FINISHED'}
        if event.type == 'RIGHTMOUSE':
            return self._botao_direito(context, event)
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'TRACKPADPAN'}:
            if _biblioteca_faixa.eh_faixa(context):
                if event.type != 'TRACKPADPAN':
                    _biblioteca_faixa.rolar(context, event)
                return {'FINISHED'}
            for wx, wy, w, h, _, acao in _gaveta._widgets_interativos(context):
                if (acao and acao[:2] == ('slider', 'instalacao') and event.type != 'TRACKPADPAN'
                        and wx <= event.mouse_region_x <= wx+w and wy <= event.mouse_region_y <= wy+h):
                    obj = bpy.data.objects.get(acao[2])
                    if obj:
                        passo = .05 if event.type == 'WHEELUPMOUSE' else -.05
                        _esquadrias.abrir(obj, acao[3], acao[4]+passo)
                        bpy.ops.ed.undo_push(message='Abertura da esquadria')
                        _eventos._redesenhar_viewports(context)
                    return {'FINISHED'}
                if (acao and acao[0] in {'navegar', 'rolar_nivel'}
                        and event.type != 'TRACKPADPAN'
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
            if not _gaveta.ALTURA_RODAPE_GAVETA < event.mouse_region_y < context.region.height - 48:
                return {'FINISHED'}
            limites = _gaveta._limites_rolagem_gaveta(
                context, context.region.width, context.region.height)
            de_baixo = (context.screen.get(_biblioteca_faixa.CHAVE_LAYOUT) != 2
                        and event.mouse_region_y < _gaveta._divisa_gaveta(
                            context, context.region.height))
            chave = _gaveta._CHAVE_ROLAGEM_BIB if de_baixo else _gaveta._CHAVE_ROLAGEM
            limite = limites[1] if de_baixo else limites[0]
            atual = max(0, min(limite, int(context.screen.get(chave, 0))))
            passo = (event.mouse_y - event.mouse_prev_y if event.type == 'TRACKPADPAN'
                     else -85 if event.type == 'WHEELUPMOUSE' else 85)
            context.screen[chave] = max(0, min(limite, atual + passo))
            context.area.tag_redraw()
            return {'FINISHED'}
        x, y = event.mouse_region_x, event.mouse_region_y
        for wx, wy, w, h, _rotulo, acao in _gaveta._widgets_interativos(context):
            if acao and acao[0] == 'pergunta':
                # a caixa preta vem ANTES das respostas (fica por baixo no
                # desenho) e as contem: no clique ela nao pode engolir o
                # "Sim"/"Nao" -- quem atende sao os botoes
                continue
            dentro = wx <= x <= wx + w and wy <= y <= wy + h
            if acao and acao[0] == 'slider':
                tx, ty, tw = _gaveta._trilho_slider_gaveta(acao, wx, wy, w, h)
                dentro = tx - 6 <= x <= tx + tw + 6 and abs(y - ty) <= h / 2
            if not dentro:
                continue
            # Lista suspensa aberta fecha com qualquer clique que nao
            # seja no proprio campo (a escolha grava e fecha junto)
            if not (acao and acao[0] == 'suspenso'):
                _gaveta._fechar_suspenso(context)
            if acao is None:
                return {'FINISHED'}
            if acao[0] in {'wireframe', 'separador', 'fundo', 'pergunta'}:
                return {'FINISHED'}
            if acao[0] == 'aba':
                context.scene.cabinet_aba = acao[1]
                context.screen[_gaveta._CHAVE_ROLAGEM] = 0
                _gaveta._fechar_opcoes(context.screen)
            elif acao[0] == 'rolagem':
                base, tamanho = _gaveta._alca_rolagem(wy, h, acao[2], acao[3])
                original = max(0, min(acao[2], acao[3]))
                atual = original if base <= y <= base + tamanho else round(
                    acao[2] * max(0, min(1, (wy + h - tamanho / 2 - y) / max(1, h - tamanho))))
                context.screen[acao[1]] = atual
                self._rolagem = dict(chave=acao[1], limite=acao[2], original=original,
                    atual=atual, inicio=y, percurso=max(1, h - tamanho))
                context.window_manager.modal_handler_add(self)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            elif acao[0] == 'suspenso':
                context.screen[_gaveta._CHAVE_SUSPENSO] = '' if acao[2] else acao[1]
            elif acao[0] == 'faixa':
                self._faixa = {'acao': acao, 'x': wx, 'w': w, 'inicio': x,
                               'arrastou': False}
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            elif acao[0] == 'cor' and acao[2] == 'amostra':
                context.screen[_gaveta._CHAVE_COR] = '' if acao[4] else acao[1]
            elif acao[0] == 'cor' and acao[2] == 'atalho':
                if acao[5] in _gaveta.OPCAO_DO_ESPECIAL:
                    _opcoes._definir_opcao(_gaveta.OPCAO_DO_ESPECIAL[acao[5]], True)
                else:
                    _gaveta._aplicar_cor_opcao(acao[1], acao[3])
            elif acao[0] == 'cor':
                # quadro ou matiz: a cor segue o mouse enquanto segura
                self._cor = {'acao': acao, 'ret': (wx, wy, w, h),
                             'original': (_opcoes._opcao(acao[1]), {
                                 n: _opcoes._opcao(n) for n in _gaveta.OPCAO_DO_ESPECIAL.values()})}
                self._arrastar_cor(context, x, y)
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            elif acao[0] == 'divisa':
                if not acao[1]:
                    return {'FINISHED'}
                self._divisa = float(context.screen.get(
                    _gaveta._CHAVE_DIVISA, _gaveta.DIVISA_PADRAO))
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
            elif acao[0] == 'nivel':
                # linha da lista suspensa da cascata (ja' fechada acima);
                # a escolhida de novo nao fecha o nivel, como no DXF
                if not acao[3]:
                    if isinstance(acao[1], tuple) and acao[1][0] == _instalacoes.ALVO:
                        _instalacoes.definir_categoria(context, acao[1][1], acao[2])
                    else:
                        bpy.ops.object.cabinet_navegar(nivel=acao[1], valor=acao[2])
            elif acao[0] == 'modo':
                pass        # indicador: um objeto = individual, mais = grupo
            elif acao[0] == 'medida':
                if acao[2]:
                    # arrastar muda o valor; soltar sem arrastar digita
                    self._campo = {
                        'acao': acao, 'x0': x, 'arrastou': False,
                        'objeto': context.object.name if context.object else ''}
                    if acao[1]=='cota':
                        alvo=_hud.alvo_cota(context.object,acao[2])
                        self._campo['backup_cota']=_hud._estado_arraste_hud(context,alvo)
                    if acao[1] == 'parede_modulo':
                        grupo = _paredes.modulo_de(context.object)
                        self._campo['objeto'] = grupo.name
                        self._campo['backup_cota'] = _hud._estado_arraste_hud(context,
                                                              dict(objeto=grupo, tipo='modulo'))
                    if acao[1]=='gavetas':
                        grupo=_gavetas.grupo_de(context.object)
                        if grupo is not None:
                            self._campo['objeto']=grupo.name
                            if acao[2].startswith('individual_'):
                                self._campo['backup_gavetas']=_gavetas.copia(grupo)
                    if acao[1] == 'divisorias':
                        grupo = _divisorias.grupo_de(context.object)
                        self._campo['objeto'] = grupo.name
                        self._campo['backup_divisorias'] = _divisorias.copia(grupo)
                    if acao[1] == 'fundos':
                        self._campo['backup_fundos'] = _fundos.copia(context,self._campo['objeto'])
                    context.window_manager.modal_handler_add(self)
                    return {'RUNNING_MODAL'}
            elif acao[0] == 'contador':
                self._campo = {'acao': acao, 'x0': x, 'arrastou': False,
                               'meio': wx + w / 2, 'valor': acao[2]}
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            elif acao[0] == 'escolha':
                grupo = (bpy.data.objects.get(acao[5])
                         if len(acao) > 5 and acao[5] else None)
                if acao[1]=='solda_acao':
                    bpy.ops.object.cabinet_acao_criacao_solda(acao=acao[2])
                elif len(acao) > 5 and acao[5] == _instalacoes.ALVO:
                    if acao[1] == 'tipo_instalacao':
                        context.screen[_instalacoes.CHAVE_TIPO_MENU] = acao[2]
                    elif acao[1] == 'modelo_instalacao':
                        # O arraste nasce no editor de origem, como o preset da biblioteca.
                        bpy.ops.object.cabinet_instalar('INVOKE_DEFAULT', modelo=acao[2], arrastar=True)
                    elif acao[1] == 'acao_instalacao':
                        _editor.executar(context, 'object.cabinet_acao_instalacao', acao=acao[2])
                elif len(acao)>5 and acao[5]==_alvenaria.ALVO_TIPO:
                    if acao[1] == 'alvenaria_visual':
                        _editor.executar(context, 'object.cabinet_visualizar_alvenaria', modo='EXEC_DEFAULT')
                    elif acao[1] == 'criar_alvenaria':
                        context.screen[_alvenaria.CHAVE_ABRIR] = acao[2]
                        if acao[2]:
                            context.scene.cabinet_aba = 'ALVENARIA'
                            context.screen[_gaveta._CHAVE_ROLAGEM] = 0
                    else:
                        context.screen[_alvenaria.CHAVE_ABRIR] = False
                        self._no_soltar = 'object.cabinet_classificar_alvenaria'
                        self._props_no_soltar = {'tipo': acao[2], 'editar': acao[1] == 'editar_alvenaria'}
                        context.window_manager.modal_handler_add(self)
                        return {'RUNNING_MODAL'}
                elif len(acao)>5 and acao[5]==_ambientes.ALVO:
                    if acao[1]=='ambiente_visivel':
                        context.scene[_ambientes.CHAVE_CORES]=not acao[2]
                        _eventos._redesenhar_viewports(context)
                        context.area.tag_redraw();return {'FINISHED'}
                    context.scene[_ambientes.CHAVE_NOME]=acao[2]
                    if acao[1]=='ambiente_cor':
                        self._no_soltar='object.cabinet_cor_ambiente'
                        self._props_no_soltar={'nome':acao[2]}
                        context.window_manager.modal_handler_add(self)
                        return {'RUNNING_MODAL'}
                    if acao[1]=='ambiente_nome':
                        self._no_soltar='object.cabinet_definir_ambiente'
                        self._props_no_soltar={'nome':acao[2]}
                        if not acao[2]:self._props_no_soltar['limpar']=True
                        context.window_manager.modal_handler_add(self)
                        return {'RUNNING_MODAL'}
                elif len(acao)>5 and acao[5]==_paredes_edicao.ALVO_AREA:
                    _paredes_edicao.definir_metodo(context,acao[2])
                elif len(acao)>5 and acao[5] == _fundos.ALVO_MENU:
                    try:
                        obj = context.object
                        fundo = obj if obj is not None and _chapas.MARCA_FUNDO in obj else None
                        _fundos.editar(context, fundo, acao[1], acao[2])
                        bpy.ops.ed.undo_push(message='Editar fundo')
                    except ValueError as erro:
                        self.report({'WARNING'},str(erro))
                elif acao[1] == _paredes_composicao.CHAVE_FIXA:
                    erro = _paredes_composicao.fixar(context, acao[5], acao[2])
                    if erro:
                        self.report({'WARNING'}, erro)
                    else:
                        bpy.ops.ed.undo_push(message='Fixar largura do modulo')
                elif not acao[4] or (len(acao) > 5
                                   and acao[5] == _portas.ALVO_ASSISTENTE):
                    pass        # a fila do wizard e' atendida pelo modal dele
                elif len(acao) > 5 and acao[5] == _paredes_composicao.ALVO_GUIAS:
                    erro = _paredes_composicao.definir_modo_guias(context, acao[2])
                    if erro:
                        self.report({'WARNING'}, erro)
                    else:
                        bpy.ops.ed.undo_push(message='Guias da parede')
                elif len(acao) > 5 and acao[5] == _gaveta.ALVO_FERRAGENS:
                    erro = _ferragens._editar_ferragens_selecionadas(
                        context, acao[1], acao[2])
                    if erro:
                        self.report({'WARNING'}, erro)
                    bpy.ops.ed.undo_push(message='Editar ferragens')
                elif len(acao) > 5 and acao[5] == _gaveta.ALVO_PUXADOR_GAVETAS:
                    erro = _gavetas.trocar_puxador(context, acao[2])
                    if erro:
                        self.report({'WARNING'}, erro)
                    bpy.ops.ed.undo_push(message='Puxador das gavetas')
                elif grupo is not None and _gavetas.MARCA_GRUPO in grupo:
                    erro = _gavetas.editar(context, grupo, acao[1], acao[2])
                    if erro:
                        self.report({'WARNING'}, erro)
                    else:
                        bpy.ops.ed.undo_push(message='Editar gavetas')
                elif grupo is not None and _prateleiras.MARCA_GRUPO in grupo:
                    erro = _prateleiras.editar(context, grupo, acao[1], acao[2])
                    if erro:
                        self.report({'WARNING'}, erro)
                    else:
                        bpy.ops.ed.undo_push(message='Editar prateleiras')
                elif len(acao) > 5 and acao[5] == _gaveta.ALVO_PUXADOR:
                    _puxadores._trocar_modelo_puxador(_gaveta._selecionado(context), acao[2])
                    bpy.ops.ed.undo_push(message='Trocar modelo do puxador')
                elif len(acao) > 5 and acao[5] == _gaveta.ALVO_PREFERENCIAS:
                    _opcoes._definir_opcao(acao[1], acao[2])
                elif len(acao) > 5 and acao[5] == _orcamento.ALVO_COMODO:
                    if acao[2] == _orcamento.COMODO_OUTRO:
                        _orcamento._abrir_caixa_comodo(context)
                        if _perguntas._abrir_pergunta(context):
                            bpy.ops.object.cabinet_digitar_nome_grupo(
                                'INVOKE_DEFAULT')
                    else:
                        bpy.ops.object.cabinet_definir_comodo(nome=acao[2])
                elif grupo is not None:
                    # Porta ja' colocada: muda ela, na hora
                    erro = _portas._editar_parametro_porta(
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
                    travas = list(pux.get(_chapas.CHAVE_TRAVAS_PUXADOR, (1, 1, 1)))
                    travas[acao[2]] = 0 if travas[acao[2]] else 1
                    pux[_chapas.CHAVE_TRAVAS_PUXADOR] = travas
                    bpy.ops.ed.undo_push(message='Cadeado do puxador')
            elif acao[0] == 'criar_puxador':
                if not acao[2]:         # ja' posicionando: Esc cancela
                    _editor.executar(context, 'object.cabinet_posicionar_puxador')
            elif acao[0] in {'gavetas', 'prateleiras', 'divisorias'}:
                if not acao[2]:
                    _perguntas._na_gaveta[0] = True
                    try:
                        _editor.executar(context, _areas_criacao.DESTINOS[acao[0].upper()])
                    finally:
                        _perguntas._na_gaveta[0] = False
            elif acao[0] == 'portas':
                if acao[3]:
                    self.report({'WARNING'}, acao[3])
                elif acao[2] or acao[1]:
                    # ja' marcando o vao, ou porta selecionada: criar
                    # outra porta e' a partir do modulo (clique simples)
                    pass
                else:
                    _editor.executar(context, 'object.cabinet_apanhar_vao')
            elif acao[0] == 'preset' and _eh_modelo_do_criador(acao[1]):
                if _modelo_do_criador(self, context, acao[1], 0):
                    # abre modal: no SOLTAR, como `_solda.OPERADORES_NO_SOLTAR`
                    self._no_soltar = 'object.cabinet_posicionar_puxador'
                    context.window_manager.modal_handler_add(self)
                    return {'RUNNING_MODAL'}
            elif acao[0] == 'biblioteca':
                # Modulos | Materiais: a outra biblioteca comeca do topo
                context.scene.cabinet_bib_modo = acao[1]
                context.screen[_gaveta._CHAVE_ROLAGEM_BIB] = 0
            elif acao[0] == 'material':
                # um clique NAO pinta (pedido do usuario: evita o clique
                # errado); duplo = a selecao, arrastar = onde soltar
                chave = acao[1]['chave']
                if _materiais.duplo_clique_na_esfera(
                        chave, event.mouse_x, event.mouse_y,
                        _limite_duplo_clique(context)):
                    bpy.ops.object.cabinet_aplicar_material(chave=chave)
                else:
                    self._material = {'chave': chave,
                                      'nome': _materiais.nome_do_material(acao[1]),
                                      'x0': event.mouse_x, 'y0': event.mouse_y,
                                      'arrastou': False}
                    context.window_manager.modal_handler_add(self)
                    return {'RUNNING_MODAL'}
            elif acao[0] == 'material_item' and acao[2] == 0:
                # o dialogo abre no SOLTAR: no PRESS o release do mesmo
                # clique cairia nele
                self._no_soltar = 'object.cabinet_editar_material'
                self._props_no_soltar = {'chave': acao[1]['chave']}
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            elif acao[0] == 'material_item':
                _materiais.perguntar_apagar(context, acao[1])
            elif acao[0] == 'preset':
                it = acao[1]
                bpy.ops.object.cabinet_arrastar_preset(
                    'INVOKE_DEFAULT', pasta=it['pasta'],
                    arquivo=it['arquivo'], tipo=it.get('tipo', 'modulo'))
            elif acao[0] == 'slider':
                self._inicio, _, self._largura = _gaveta._trilho_slider_gaveta(
                    acao, wx, wy, w, h)
                self._slider = acao[1]
                if acao[1] == 'instalacao':
                    self._abertura = acao[2:5]
                self._atualizar(context, x)
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            elif acao[0] == 'resposta':
                bpy.ops.object.cabinet_responder_pergunta(opcao=acao[1])
            elif _operador_apagado(acao):
                pass            # apagado: a selecao nao serve, nada a fazer
            elif acao[1] in _solda.OPERADORES_NO_SOLTAR:
                # Dispara no SOLTAR, como botao do Blender: o pop-up que
                # ele abre ("tem certeza?") nasceria sob o mouse e o
                # RELEASE deste mesmo clique ja' escolheria a 1a opcao
                # (visto no teste de interface: desagregava sem perguntar).
                self._no_soltar = acao[1]
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            else:
                _perguntas._na_gaveta[0] = True
                try:
                    _editor.executar(context, acao[1])
                except Exception as e:
                    self.report({'WARNING'}, str(e))
                finally:
                    _perguntas._na_gaveta[0] = False
            context.area.tag_redraw()
            return {'FINISHED'}
        _gaveta._fechar_suspenso(context)       # clique no vazio tambem fecha
        return {'FINISHED'}

    def _atualizar(self, context, x):
        fracao = min(1.0, max(0.0, (x - self._inicio) / self._largura))
        if getattr(self, '_slider', None) == 'instalacao':
            nome, folha, _ = self._abertura
            obj = bpy.data.objects.get(nome)
            if obj:
                _esquadrias.abrir(obj, folha, fracao)
                _eventos._redesenhar_viewports(context)
            return
        if getattr(self, '_slider', None) == 'retratos':
            # tamanho de TODOS os retratos (puxador, abertura, dobradica)
            menor, maior = _gaveta.LARGURA_RETRATO_MIN, _gaveta.LARGURA_RETRATO_MAX
            context.scene.cabinet_tam_retrato = menor + round(fracao * (maior - menor))
        else:
            context.scene.chapa_tam_bloco = 2 + round(fracao * 6)
        context.area.tag_redraw()

    def _modal_rolagem(self, context, event):
        estado = self._rolagem
        if event.type == 'MOUSEMOVE':
            valor = estado['atual'] + round((estado['inicio'] - event.mouse_region_y)
                                           * estado['limite'] / estado['percurso'])
            context.screen[estado['chave']] = max(0, min(estado['limite'], valor))
            context.area.tag_redraw()
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            context.screen[estado['chave']] = estado['original']
            context.area.tag_redraw()
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        return {'RUNNING_MODAL'}

    def _arrastar_cor(self, context, x, y):
        acao = self._cor['acao']
        rx, ry, rw, rh = self._cor['ret']
        _gaveta._aplicar_cor_opcao(acao[1], _gaveta._cor_do_seletor(
            acao[1], acao[2], _hud._cor_opcao(acao[1]),
            (x - rx) / rw, (y - ry) / rh))
        context.area.tag_redraw()

    def _modal_campo(self, context, event):
        """Arraste de um campo de valor ('medida') ou do contador."""
        campo = self._campo
        acao = campo['acao']
        contador = acao[0] == 'contador'
        if event.type == 'MOUSEMOVE':
            dx = event.mouse_region_x - campo['x0']
            if abs(dx) > _hud.LIMIAR_ARRASTE_HUD_PX:
                campo['arrastou'] = True
            if not campo['arrastou']:
                return {'RUNNING_MODAL'}
            if contador:
                valor = max(acao[3], min(acao[4], acao[2] + round(
                    dx / PX_POR_UNIDADE_CONTADOR)))
                if valor != campo['valor']:
                    campo['valor'] = valor
                    if acao[1] == 'prateleiras_quantidade':
                        _prateleiras._quantidade_previa[0] = (acao[5], valor)
                    else:
                        _aplicar_contador(context, acao, valor)
            else:
                # conta desde o CLIQUE (o limiar nao come pixels); trocar
                # Shift/Ctrl no meio rebaseia ali, sem pular
                if 'passo' not in campo:
                    campo.update(base=acao[4] / 1000.0, x_base=campo['x0'],
                                 passo=_passo_do_arraste(event))
                elif campo['passo'] != _passo_do_arraste(event):
                    campo.update(base=campo['atual'],
                                 x_base=event.mouse_region_x,
                                 passo=_passo_do_arraste(event))
                minimo = 0.0 if acao[1] in DONOS_DE_PARAMETRO else 0.001
                valor = max(minimo, campo['base'] + campo['passo']
                            * (event.mouse_region_x - campo['x_base']))
                campo['atual'] = valor
                if 'backup_cota' in campo:
                    _hud.restaurar_cota(context,campo['backup_cota'],campo['objeto'])
                aplicar_medida(context, acao[1], campo['objeto'], acao[2],
                               valor,previa='backup_gavetas' in campo)
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            _prateleiras._quantidade_previa[0] = None
            # o wizard nao vai para o undo: so' o que ja' esta' na cena
            no_wizard = acao[0] == 'medida' and acao[1] in {'assistente', 'paredes','solda_criacao'} or (
                contador and (acao[5] == _portas.ALVO_ASSISTENTE
                              or acao[1] == _paredes_edicao.ALVO_QUANTIDADE))
            if campo['arrastou']:
                if contador and acao[1] == 'prateleiras_quantidade':
                    erro = _aplicar_contador(context, acao, campo['valor'])
                    if erro:
                        self.report({'WARNING'}, erro)
                if 'backup_gavetas' in campo:
                    grupo=bpy.data.objects.get(campo['objeto'])
                    if grupo is not None:_gavetas.montar(grupo)
                if not no_wizard:
                    bpy.ops.ed.undo_push(message='Arrastar medida')
            elif _gaveta_desenho._eh_campo_contador(acao):
                # campo de contador (Folhas): o clique digita, como as
                # medidas -- qualquer numero; quem limita e' quem grava
                bpy.ops.object.cabinet_editar_medida_gaveta(
                    'INVOKE_DEFAULT', dono='contador', objeto=acao[5],
                    propriedade=acao[1], valor=float(acao[2]))
            elif contador:
                # clique: a metade direita soma um, a esquerda tira
                passo = 1 if event.mouse_region_x >= campo['meio'] else -1
                valor = max(acao[3], min(acao[4], acao[2] + passo))
                if valor != acao[2]:
                    erro = _aplicar_contador(context, acao, valor)
                    if erro:
                        self.report({'WARNING'}, erro)
                    elif not no_wizard:
                        bpy.ops.ed.undo_push(message='Editar ferragens')
            else:
                bpy.ops.object.cabinet_editar_medida_gaveta(
                    'INVOKE_DEFAULT', dono=acao[1], objeto=campo['objeto'],
                    propriedade=acao[2], valor=acao[4] / 1000.0)
            context.area.tag_redraw()
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            _prateleiras._quantidade_previa[0] = None
            if campo['arrastou']:       # devolve o valor de antes
                if 'backup_cota' in campo:
                    _hud.restaurar_cota(context,campo['backup_cota'],campo['objeto'])
                elif 'backup_gavetas' in campo:
                    _gavetas.restaurar(campo['backup_gavetas'])
                elif 'backup_divisorias' in campo:
                    _divisorias.restaurar(campo['backup_divisorias'])
                elif 'backup_fundos' in campo:
                    _fundos.restaurar(context,campo['backup_fundos'])
                elif contador:
                    if acao[1] != 'prateleiras_quantidade':
                        _aplicar_contador(context, acao, acao[2])
                else:
                    aplicar_medida(context, acao[1], campo['objeto'], acao[2],
                                   acao[4] / 1000.0)
            context.area.tag_redraw()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def _modal_opcao(self, context, event):
        """Arraste da faixa ou do seletor de cor do painel de opcoes."""
        faixa = getattr(self, '_faixa', None)
        if event.type == 'MOUSEMOVE':
            if faixa is None:
                self._arrastar_cor(context, event.mouse_region_x,
                                   event.mouse_region_y)
                return {'RUNNING_MODAL'}
            if abs(event.mouse_region_x - faixa['inicio']) > _hud.LIMIAR_ARRASTE_HUD_PX:
                faixa['arrastou'] = True
            if faixa['arrastou']:
                nome = faixa['acao'][1]
                _opcoes._definir_opcao(nome, _gaveta._valor_da_faixa(
                    nome, (event.mouse_region_x - faixa['x']) / faixa['w']))
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if faixa is not None and not faixa['arrastou']:
                # clique sem arrastar: digita o valor, como nas medidas
                bpy.ops.object.cabinet_editar_medida_gaveta(
                    'INVOKE_DEFAULT', dono='opcao',
                    propriedade=faixa['acao'][1],
                    valor=float(_opcoes._opcao(faixa['acao'][1])))
            context.area.tag_redraw()
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            if faixa is not None:
                _opcoes._definir_opcao(faixa['acao'][1], faixa['acao'][2])
            else:
                nome = self._cor['acao'][1]
                cor, especiais = self._cor['original']
                _opcoes._definir_opcao(nome, cor)
                for n, v in especiais.items():
                    _opcoes._definir_opcao(n, v)
            context.area.tag_redraw()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def _modal_divisa(self, context, event):
        """Arraste da divisoria aba | biblioteca (sobe ou desce)."""
        if event.type == 'MOUSEMOVE':
            context.screen[_gaveta._CHAVE_DIVISA] = _gaveta._fracao_divisa(
                context.region.height, event.mouse_region_y)
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            # grava a posicao JA' limitada: assim a fracao nao fica
            # alem do minimo e o proximo arraste nao "pula"
            altura = context.region.height
            context.screen[_gaveta._CHAVE_DIVISA] = _gaveta._fracao_divisa(
                altura, _gaveta._divisa_gaveta(context, altura))
            context.window.cursor_modal_restore()
            context.area.tag_redraw()
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            context.screen[_gaveta._CHAVE_DIVISA] = self._divisa
            context.window.cursor_modal_restore()
            context.area.tag_redraw()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def _modal_material(self, context, event):
        """Esfera arrastada da gaveta: o pincel segue o mouse e, ao soltar
        numa viewport, pinta o que esta' embaixo (`pecas_do_solte`)."""
        estado = self._material
        if event.type == 'MOUSEMOVE':
            if not estado['arrastou']:
                dx = event.mouse_x - estado['x0']
                dy = event.mouse_y - estado['y0']
                raio = _biblioteca.RAIO_DUPLO_CLIQUE_PX
                if dx * dx + dy * dy <= raio * raio:
                    return {'RUNNING_MODAL'}
                estado['arrastou'] = True
                _materiais._clique_esfera[0] = None     # arraste nao e' 1o clique
                context.window.cursor_modal_set('PAINT_BRUSH')
                try:
                    context.workspace.status_text_set(
                        "%s | Solte sobre um modulo, porta ou peca | "
                        "Botao direito: cancelar" % estado['nome'])
                except Exception:
                    pass
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self._encerrar_material(context)
            if estado['arrastou']:
                alvo = _objeto_sob_mouse(context, event)
                if alvo:
                    bpy.ops.object.cabinet_aplicar_material(
                        chave=estado['chave'], alvo=alvo)
                elif _gaveta_sob_evento(context, event) is None:
                    self.report({'WARNING'},
                                "Solte o material sobre um modulo, porta ou peca")
            context.area.tag_redraw()
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._encerrar_material(context)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def _encerrar_material(self, context):
        if self._material['arrastou']:
            context.window.cursor_modal_restore()
            try:
                context.workspace.status_text_set(None)
            except Exception:
                pass

    def cancel(self, context):
        if hasattr(self, '_material'):
            self._encerrar_material(context)

    def modal(self, context, event):
        if hasattr(self, '_menu_item'):
            if event.type == 'RIGHTMOUSE' and event.value == 'RELEASE':
                _biblioteca_faixa.abrir_menu_item(context, self._menu_item)
                return {'FINISHED'}
            if event.type == 'ESC':
                return {'CANCELLED'}
            return {'RUNNING_MODAL'}
        if hasattr(self, '_material'):
            return self._modal_material(context, event)
        if hasattr(self, '_no_soltar'):
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                _perguntas._na_gaveta[0] = True     # pergunta que nascer vem na gaveta
                try:
                    _editor.executar(context, self._no_soltar, **getattr(self, '_props_no_soltar', {}))
                except Exception as e:
                    self.report({'WARNING'}, str(e))
                finally:
                    _perguntas._na_gaveta[0] = False
                context.area.tag_redraw()
                return {'FINISHED'}
            if event.type in {'ESC', 'RIGHTMOUSE'}:
                return {'CANCELLED'}
            return {'RUNNING_MODAL'}
        if hasattr(self, '_campo'):
            return self._modal_campo(context, event)
        if hasattr(self, '_rolagem'):
            return self._modal_rolagem(context, event)
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
            if getattr(self, '_slider', None) == 'instalacao':
                bpy.ops.ed.undo_push(message='Abertura da esquadria')
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            if getattr(self, '_slider', None) == 'instalacao':
                nome, folha, anterior = self._abertura
                obj = bpy.data.objects.get(nome)
                if obj:
                    _esquadrias.abrir(obj, folha, anterior)
                    _eventos._redesenhar_viewports(context)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class OBJECT_OT_opcoes_gaveta(Operator):
    """Opcoes: unidade padrao, linhas e rotulos das medidas"""
    bl_idname = "object.cabinet_opcoes_gaveta"
    bl_label = "Opcoes do Archy Builder"

    def execute(self, context):
        tela = context.screen
        aberto = tela.get(_gaveta._CHAVE_OPCOES)
        _gaveta._fechar_opcoes(tela)
        tela[_gaveta._CHAVE_OPCOES] = 0 if aberto else 1
        tela[_gaveta._CHAVE_ROLAGEM] = 0
        for area in tela.areas:
            if area.type == 'VIEW_3D' or _editor.eh_editor(area):
                area.tag_redraw()
        return {'FINISHED'}


class OBJECT_OT_alternar_gaveta(Operator):
    """Abre ou fecha a area exclusiva do addon a esquerda da viewport"""
    bl_idname = "object.cabinet_alternar_gaveta"
    bl_label = "Alternar Gaveta Archy Builder"

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and not _gaveta._eh_area_gaveta(context))

    def execute(self, context):
        screen = context.screen
        if _biblioteca_faixa.area_da_faixa(screen) is not None:
            _biblioteca_faixa.fechar(context.window, screen)
            return {'FINISHED'}
        if _biblioteca_faixa.acoplada(screen):
            # biblioteca dentro do menu: abre/fecha so' a area do menu
            if _gaveta._area_gaveta(screen) is not None:
                _biblioteca_faixa.fechar(context.window, screen)
            else:
                _biblioteca_faixa.abrir_menu(context)
            return {'FINISHED'}
        _biblioteca_faixa.abrir(context)
        return {'FINISHED'}


def _poll_operador(idname):
    try:
        return _editor.pode_executar(idname)
    except Exception:
        return False


def _operador_apagado(acao):
    """Botao de TEXTO cujo operador recusa a selecao atual: sai cinza,
    sem brilho e sem clique. (Botao de icone ja' esmaece pelo gizmo.)"""
    return bool(acao and acao[0] == 'operador'
                and (not _icone_acao_gaveta(acao) or _icone_ao_lado(acao))
                and not _poll_operador(acao[1]))


# O texto explica a acao; o gizmo so' desenha o icone a' esquerda.
# O clique inteiro continua na gaveta para respeitar o soltar do mouse.
ICONES_AO_LADO = {'object.cabinet_apanhar_vao': 'PIVOT_BOUNDBOX',
                  'object.cabinet_alternar_partes': 'HIDE_OFF',
                  'object.cabinet_editar_grupo_visual': 'GREASEPENCIL',
                  'object.cabinet_desassociar_fundo': 'UNPINNED',
                  'object.cabinet_definir_frente': 'AXIS_FRONT',
                  'object.cabinet_corrente_objeto': 'LINKED',
                  'object.cabinet_resetar_distancia': 'DRIVER_DISTANCE'}


def _icone_ao_lado(acao):
    return bool(acao and acao[0] == 'operador' and acao[1] in ICONES_AO_LADO)


def _centro_icone(x, y, w, h, acao):
    """Onde o gizmo do icone fica: no meio do botao, ou na ponta
    esquerda do botao de texto com icone."""
    compacto = acao and acao[0] == 'operador' and acao[1] in {
        'object.cabinet_alternar_partes', 'object.cabinet_editar_grupo_visual'}
    return (x + h / 2 + 2 if _icone_ao_lado(acao) and not compacto else x + w / 2), y + h / 2


def _icone_acao_gaveta(acao):
    if not acao:
        return None
    if acao[0] == 'escolha' and acao[1] in {'ambiente_visivel', 'alvenaria_visual'}:
        return 'HIDE_OFF' if acao[2] else 'HIDE_ON'
    if acao[:2] == ('operador', 'object.cabinet_alternar_partes'):
        return 'HIDE_ON' if acao[2] else 'HIDE_OFF'
    if _icone_ao_lado(acao):
        return ICONES_AO_LADO[acao[1]]
    if acao[0] == 'escolha' and acao[1] == _portas.CONFIRMAR_ETAPA:
        # o "aceitar" verde: o visto PRONTO do Blender (o desenhado a' mao
        # saia serrilhado, pedido do usuario)
        return 'CHECKMARK'
    if acao[0] == 'operador':
        if acao[1] == 'object.cabinet_portas_internos':
            return 'HIDE_OFF' if acao[2] else 'HIDE_ON'
        return {'object.cabinet_agrupar': 'GROUP',
                'object.cabinet_espelhar_porta': 'MOD_MIRROR',
                'object.cabinet_detectar_adjacencia': 'SNAP_ON',
                _solda.OP_CORRENTE_OBJETO: 'LINKED',
                _solda.OP_RESETAR_DISTANCIA: 'DRIVER_DISTANCE',
                'object.cabinet_normalizar': 'FILE_REFRESH',
                'object.cabinet_converter_modulo': 'IMPORT',
                'object.cabinet_opcoes_gaveta': 'PREFERENCES',
                'object.cabinet_vincular_porta': 'LINKED',
                'object.cabinet_vincular_puxador': 'LINKED',
                'object.cabinet_abrir_biblioteca': 'FILE_FOLDER',
                'object.cabinet_salvar_biblioteca': 'FILE_TICK',
                'object.cabinet_novo_material': 'ADD',
                _biblioteca_faixa.OP_LUGAR: 'WINDOW'}.get(acao[1])
    if acao[0] == 'material_item':
        return ('GREASEPENCIL', 'TRASH')[acao[2]]
    if acao[0] == 'cadeado':
        return 'LOCKED' if acao[3] else 'UNLOCKED'
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


class _GizmosGaveta:
    """Mesmo pool nativo de botoes/campos nos editores e na alca da cena."""
    def setup(self, context):
        self.botoes = []
        self.campos = []
        self.operadores_campos = []
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
        alvos = [v for v in _gaveta._widgets_interativos(context)
                 if _gaveta_desenho._chave_widget(v[5]) and v[1] >= 0]
        while len(self.campos) < len(alvos):
            campo = self.gizmos.new('VIEW3D_GT_campo_gaveta')
            # O clique cai no mesmo operador que a keymap ja' dispara
            # para a area inteira, entao clicar continua igual.
            self.operadores_campos.append(campo.target_set_operator('object.cabinet_interagir_gaveta'))
            campo.use_tooltip = False
            self.campos.append(campo)

        escala = max(1.0, context.preferences.system.ui_scale)
        # Duas areas usam este grupo: apagar tudo aqui invalidava os
        # hit-tests do menu sempre que a faixa era redesenhada.
        for campo in self.campos:
            _hud._campos_gaveta.pop(campo.as_pointer(), None)
        acesos = set(acesos_por_icone)
        for campo, op, (x, y, w, h, _rotulo, acao) in zip(self.campos, self.operadores_campos, alvos):
            campo.hide = False
            campo.use_tooltip = bool(acao and acao[0] in ('preset', 'material', 'navegar'))
            if campo.use_tooltip:
                op.dica = acao[1].get('nome', '') if acao[0] in ('preset', 'material') else str(acao[2])
            icone = None
            if _icone_acao_gaveta(acao):
                raio = min(13.0 * escala, min(w, h) / 2) if _biblioteca_faixa.eh_faixa(context) else 13.0 * escala
                icone = _centro_icone(x, y, w, h, acao) + (raio,)
            _hud._campos_gaveta[campo.as_pointer()] = (x, y, w, h, icone)
            if _biblioteca_faixa.caixa_categoria(acao):
                _hud._campos_gaveta[campo.as_pointer()] += (
                    _biblioteca_faixa.retangulos_filhos((x, y, w, h, _rotulo, acao), alvos),)
            if campo.is_highlight:
                acesos.add(_gaveta_desenho._chave_widget(acao))

        _biblioteca_faixa.realces_das_categorias(alvos, acesos)
        # Edicao aberta manda mais que o mouse: com o campo em foco o
        # usuario ja' esta' digitando aquela medida, ainda que o cursor
        # tenha saido de cima dele.
        medida_ativa = next(
            (v[5][3] for v in alvos if v[5][0] == 'medida'
             and _gaveta_desenho._chave_widget(v[5]) in acesos), None)
        edicao = _gaveta._edicao_gaveta[0]
        if edicao is not None:
            em_foco = next((v[5] for v in alvos if v[5][0] == 'medida'
                            and v[5][2] == edicao['propriedade']), None)
            if em_foco is not None:
                medida_ativa = em_foco[3]
                acesos.add(_gaveta_desenho._chave_widget(em_foco))
            elif any(_gaveta_desenho._eh_campo_contador(v[5])
                     and v[5][1] == edicao['propriedade'] for v in alvos):
                acesos.add('cont:' + edicao['propriedade'])

        for _x, _y, _w, _h, _rotulo, acao in alvos:
            chave = _gaveta_desenho._chave_widget(acao)
            _gaveta._realcar(context, chave, chave in acesos)
        _hud._definir_realce_medida(medida_ativa)
        # Perto da divisoria o cursor vira a seta de redimensionar, como
        # na fronteira entre areas do Blender. So' na TRANSICAO: trocar a
        # cada redesenho brigaria com o cursor de quem mais o define.
        sobre = 'divisa' in acesos
        if sobre != _gaveta._cursor_divisa[0]:
            _gaveta._cursor_divisa[0] = sobre
            try:
                context.window.cursor_set('MOVE_Y' if sobre else 'DEFAULT')
            except Exception:
                pass

    def draw_prepare(self, context):
        gaveta = _gaveta._eh_area_gaveta(context)
        self.alca.hide = gaveta
        for botao in self.botoes:
            botao.hide = True
        for campo in self.campos:
            campo.hide = True
        if gaveta:
            widgets = [v for v in _gaveta._widgets_interativos(context)
                       if _icone_acao_gaveta(v[5]) and v[1] >= 0]
            if not hasattr(self, 'botoes_por_icone'):
                self.botoes_por_icone = {}
            usados = {}
            cores, _ = _gaveta._cores_gaveta()
            acesos_por_icone = set()
            for x, y, w, h, _, acao in widgets:
                icone = _icone_acao_gaveta(acao)
                indice = usados.get(icone, 0)
                usados[icone] = indice + 1
                chave = (icone, indice)
                botao = self.botoes_por_icone.get(chave)
                if botao is None:
                    # Button2D fixa o icone no primeiro desenho nativo.
                    # Outro simbolo exige outro gizmo, sem liberar o antigo.
                    botao = self.gizmos.new('GIZMO_GT_button_2d')
                    botao.icon = icone
                    botao.draw_options = set()
                    botao.show_drag = False
                    botao.use_tooltip = True
                    self.botoes.append(botao)
                    self.botoes_por_icone[chave] = botao
                botao.hide = False
                if botao.is_highlight:
                    acesos_por_icone.add(_gaveta_desenho._chave_widget(acao))
                botao.color = cores.text
                # Corrente sem nada para ligar fica apagada: o poll do
                # operador e' o mesmo criterio que ele usa ao rodar.
                # Resetar sem solda fora da origem fica apagado
                apagado = (acao[0] == 'operador' and (
                    _gaveta._no_cabecalho(acao) and not _poll_operador(acao[1])
                    or acao[1] == _solda.OP_RESETAR_DISTANCIA and not acao[2])
                    or _operador_apagado(acao))
                botao.alpha = 0.3 if apagado else 1
                botao.color_highlight = cores.text_sel
                botao.alpha_highlight = 0.3 if apagado else 1
                botao.hide_select = False
                botao.scale_basis = min(11, min(w, h) / (2 * max(1.0, context.preferences.system.ui_scale))) if _biblioteca_faixa.eh_faixa(context) else 11
                ao_lado = _icone_ao_lado(acao)
                # o texto ao lado ja' diz o que e': sem o tooltip do
                # operador da gaveta, que nao diria nada
                botao.use_tooltip = not ao_lado
                cx, cy = _centro_icone(x, y, w, h, acao)
                botao.matrix_basis[0][3] = cx
                botao.matrix_basis[1][3] = cy
                if _editor.eh_editor(context.area) or ao_lado or (acao[0] == 'operador'
                               and acao[1] in _solda.OPERADORES_NO_SOLTAR):
                    # o gizmo dispara no PRESS; a gaveta espera o soltar.
                    # Com texto ao lado, o clique no icone e' o do botao
                    # inteiro (o wizard e' modal: pelo gizmo prendia a gaveta)
                    botao.target_set_operator('object.cabinet_interagir_gaveta')
                elif acao[0] == 'operador':
                    botao.target_set_operator(acao[1])
                elif acao[0] in {'rolar_nivel', 'cadeado', 'escolha',
                                 'material_item'}:
                    botao.target_set_operator('object.cabinet_interagir_gaveta')
            self._preparar_hover(context, acesos_por_icone)
            _gaveta_desenho._desenhar_gaveta(tela=True)
            return
        _gaveta._realcar(context, 'alca', self.alca.is_highlight)


class VIEW3D_GGT_cabinet_gaveta(_GizmosGaveta, GizmoGroup):
    bl_idname = 'VIEW3D_GGT_cabinet_gaveta'
    bl_label = 'Alca Archy Builder'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'SCALE'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'
