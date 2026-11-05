"""Selecao em camadas (clique = modulo, duplo = peca) e os keymaps."""

import bpy
_visibilidade = None
_alvenaria = None
from bpy.props import BoolProperty, EnumProperty, IntVectorProperty
from bpy.types import Operator, Menu

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = None
_modulos = None
_opcoes = None
_eventos = None
_portas = None
_ferragens = None
_gaveta = None
_hud = None
_solda = None
_portas_viewport = None
_gavetas = None
_prateleiras = None
_divisorias = None
_formas = None
_paredes_edicao = None
_fundos = None

# ====================================================== SELECAO
# 1 clique seleciona o MODULO inteiro (o realce nativo do Blender acende
# em todas as pecas); 2 cliques isolam a chapa sob o cursor.
#
# As entradas ficam no keyconfig do ADDON, avaliado antes do padrao.
# Quando o poll falha -- fora do Object Mode, ou com a opcao desligada
# nas Preferencias -- o evento cai para o `view3d.select` nativo e o
# comportamento normal do Blender volta inteiro.


def _puxador_do_clique(obj):
    while obj is not None:
        if _chapas.MARCA_PUXADOR in obj:
            return obj
        obj = obj.parent
    return None


def _selecionar_puxador(context, puxador, somar=False):
    # A ascendencia identifica a montagem, mas nao amplia a selecao do
    # acessorio: clicar nele abre so' as suas proprias funcoes.
    ligado = not puxador.select_get() if somar else True
    if not somar:
        for obj in context.selected_objects:
            obj.select_set(False)
    puxador.select_set(ligado)
    if ligado:
        context.view_layer.objects.active = puxador
    elif context.view_layer.objects.active == puxador:
        context.view_layer.objects.active = next(
            (o for o in context.selected_objects if o != puxador and o.select_get()), None)


def _aba_da_selecao(obj):
    """Aba da gaveta que cuida de `obj`, ou None (objeto que nao e' nosso)."""
    if obj is None:
        return None
    if _alvenaria.grupo_de(obj) is not None:
        return 'ALVENARIA'
    if _chapas.MARCA_PUXADOR in obj:
        return 'PUXADORES'
    if _chapas.MARCA_FUNDO in obj:
        return 'FUNDOS'
    if _gavetas.grupo_de(obj) is not None:
        return 'GAVETAS'
    if _prateleiras.grupo_de(obj) is not None:
        return 'PRATELEIRAS'
    if _divisorias.grupo_de(obj) is not None:
        return 'DIVISORIAS'
    if _chapas.MARCA_PORTAS in obj or _chapas.MARCA_FOLHA in obj:
        return 'PORTAS'
    if _chapas.MARCA_CONJUNTO in obj or _chapas.MARCA_CHAPA in obj:
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
        tela[_gaveta._CHAVE_ROLAGEM] = 0
        _gaveta._fechar_opcoes(tela)
    _eventos._redesenhar_viewports(context)


def objetos_na_camada(context, objetos):
    """Parent pode conservar IDs apagados; a View Layer nativa decide a selecao."""
    camada = context.view_layer.objects
    return [o for o in objetos if camada.get(o.name) == o]


def montagem_da_porta(context):
    grupo = _ferragens._grupo_da_ferragem(context.object)
    return objetos_na_camada(context, [grupo, *grupo.children_recursive]) if grupo else []


class OBJECT_OT_selecionar_montagem_porta(Operator):
    """Seleciona a porta com puxadores, ferragens e demais componentes"""
    bl_idname = 'object.cabinet_selecionar_montagem_porta'
    bl_label = 'Grupo da porta'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(montagem_da_porta(context))

    def invoke(self, context, event):
        return bpy.ops.wm.call_menu(name='VIEW3D_MT_cabinet_grupo_porta')

    def execute(self, context):
        objetos = [o for o in montagem_da_porta(context)
                   if not o.hide_select and o.visible_get(view_layer=context.view_layer)]
        if not objetos:
            return {'CANCELLED'}
        ativo = context.object
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in objetos:
            obj.select_set(True)
        context.view_layer.objects.active = ativo if ativo in objetos else objetos[0]
        return {'FINISHED'}


class OBJECT_OT_esconder_porta(Operator):
    """Oculta na View Layer a porta inteira, incluindo seus agregados"""
    bl_idname = 'object.cabinet_esconder_porta'
    bl_label = 'Esconder porta e agregados'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return OBJECT_OT_selecionar_montagem_porta.poll(context)

    def execute(self, context):
        objetos = montagem_da_porta(context)
        if not objetos:
            return {'CANCELLED'}
        for obj in objetos:
            obj.select_set(False)
            obj.hide_set(True, view_layer=context.view_layer)
        if context.view_layer.objects.active in objetos:
            context.view_layer.objects.active = None
        _hud._hover_hud.clear()
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


class VIEW3D_MT_grupo_porta(Menu):
    bl_idname = 'VIEW3D_MT_cabinet_grupo_porta'
    bl_label = 'Selecionar grupo'

    def draw(self, context):
        self.layout.operator_context = 'EXEC_DEFAULT'
        self.layout.operator(OBJECT_OT_selecionar_montagem_porta.bl_idname, icon='OUTLINER_OB_GROUP_INSTANCE')
        self.layout.separator()
        self.layout.operator_menu_enum('object.select_grouped', 'type', text='Grupos do Blender')


def familia_de(obj):
    """Tudo que deve acender junto com obj: as chapas do grupo mais o
    Empty do conjunto.

    Selecionar o pai JUNTO com os filhos e' seguro: o Blender nao
    transforma duas vezes o filho cujo pai tambem esta' selecionado.
    """
    if obj is None:
        return []
    if _puxador_do_clique(obj) is not None:
        return []
    portas = _portas._grupo_portas(obj)
    if portas is not None:
        return [portas] + _portas._folhas_portas(portas)
    if _chapas.MARCA_CONJUNTO in obj:
        return [obj] + _modulos._chapas_do_conjunto(obj)
    if _chapas.MARCA_CHAPA not in obj:
        return []
    chapas = _modulos.grupo_de(obj, simetrico=True)
    pai = obj.parent
    if pai is not None and _chapas.MARCA_CONJUNTO in pai:
        return [pai] + chapas
    return chapas


def _encerrar_edicao_fora(context, atingido):
    """Um clique fora encerra o escopo individual, inclusive entre viewports."""
    memoria = _hud._clique_chapa_hud.get(context.region.as_pointer())
    anterior = ((bpy.data.objects.get(memoria[0]) if memoria else None)
                or getattr(context, 'object', None))
    if anterior is None or _chapas.MARCA_CHAPA not in anterior:
        return
    modulo = _portas._modulo_da_chapa(anterior)
    if atingido is anterior or (modulo is not None
            and _portas._modulo_da_chapa(atingido) == modulo):
        return
    _hud._clique_chapa_hud.clear()
    _hud._clique_pendente.clear()
    _hud._hover_hud.clear()
    ocupado = _chapas._ocupado[0]
    _chapas._ocupado[0] = True
    try:
        anterior.chapa_modo = 'GRUPO'
    finally:
        _chapas._ocupado[0] = ocupado


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
        p = _opcoes._prefs()
        if _visibilidade._edicao[0]:
            return False
        if p is not None and not p.selecao_por_grupo:
            return False
        return (context.mode == 'OBJECT' and context.area is not None
                and context.area.type == 'VIEW_3D'
                and not _gaveta._eh_area_gaveta(context))

    def invoke(self, context, event):
        _paredes_edicao.lembrar_face(context, (event.mouse_region_x, event.mouse_region_y))
        resultado = self._invoke(context, event)
        _seguir_selecao_na_gaveta(context)
        return resultado

    def _invoke(self, context, event):
        self.location = (event.mouse_region_x, event.mouse_region_y)
        chave = context.region.as_pointer()
        pendente = _hud._clique_pendente.pop(chave, None)
        if self.clique:
            return self._soltou(context, pendente)
        if (_portas_viewport._slider_sob_mouse(context, self.location) is not None
                or _gavetas.slider_sob_mouse(context, self.location) is not None):
            # a bolinha do slider: no keyconfig do usuario esta entrada vem
            # antes da do slider, e selecionar aqui esconderia o slider
            return {'PASS_THROUGH'}
        ferragem = _hud._ferragem_sob_mouse(context, self.location)
        if ferragem is not None:
            if not (self.toggle or self.extend):
                _encerrar_edicao_fora(context, ferragem)
            if self.modo == 'INDIVIDUAL':
                # duplo = a PECA, selecao nativa: Tab, G/R/S, modificadores
                _ferragens._selecionar_peca(context, ferragem,
                                 somar=self.toggle or self.extend)
            else:
                # dobradica/pistao: todas as do modulo, no modo delas
                _ferragens._selecionar_ferragem(context, ferragem,
                                     somar=self.toggle or self.extend)
            return {'FINISHED'}
        # qualquer outro clique sai do modo de edicao das ferragens
        _ferragens._ferragens_selecionadas[0] = None
        atingido = _hud._raio_hud(context, self.location)
        if not (self.toggle or self.extend):
            _encerrar_edicao_fora(context, atingido[0] if atingido is not None else None)
        montagem = _alvenaria.grupo_de(atingido[0]) if atingido else None
        if montagem is not None:
            alvo = atingido[0] if self.modo == 'INDIVIDUAL' else montagem
            if not (self.toggle or self.extend):
                for anterior in context.selected_objects:
                    anterior.select_set(False)
            familia = (alvo, *alvo.children) if alvo == montagem else (alvo,)
            for peca in objetos_na_camada(context, familia):
                if not peca.hide_select and peca.visible_get(view_layer=context.view_layer):
                    peca.select_set(True)
            alvo.select_set(True)
            context.view_layer.objects.active = alvo
            return {'FINISHED'}
        puxador = _puxador_do_clique(atingido[0]) if atingido is not None else None
        if puxador is not None:
            gaveta = _gavetas.gaveta_de(puxador)
            grupo = _gavetas.grupo_de(puxador)
            isolada = (gaveta is not None and grupo is not None
                       and gaveta.select_get() and not grupo.select_get())
            if (self.modo == 'INDIVIDUAL' or isolada
                    or (puxador.select_get() and context.view_layer.objects.active == puxador)):
                # O escopo ja' isolado vale antes da selecao do modulo na parede.
                _selecionar_puxador(context, puxador, somar=self.toggle or self.extend)
                return {'FINISHED'}
        modulo_parede = (_paredes_edicao.modulo_da_peca(context, atingido[0])
                         if atingido is not None else None)
        if modulo_parede is not None and self.modo != 'INDIVIDUAL':
            # Vista da parede: clique simples em QUALQUER peca e' o modulo
            # (pedido do usuario), para o G nativo levar o movel inteiro.
            # O duplo continua nos ramos de cada tipo, abaixo.
            obj = atingido[0]
            if self.toggle or self.extend:
                _hud._somar_peca(context, obj)
                return {'FINISHED'}
            if self.select_passthrough and obj.select_get():
                familia = set(_hud._familia_do_clique(obj, context))
                if any(o not in familia for o in context.selected_objects):
                    # varios modulos: o arraste leva todos; o CLICK sem
                    # arrastar deixa so' este (`_soltou`)
                    _hud._clique_pendente[chave] = obj.name
                    return {'PASS_THROUGH', 'CANCELLED'}
            _hud._selecionar_chapa_hud(context, obj)
            return {'FINISHED'}
        if atingido is not None and _chapas.MARCA_FUNDO in atingido[0]:
            _fundos.selecionar(context, atingido[0], somar=self.toggle or self.extend)
            return {'FINISHED'}
        if puxador is not None and puxador.parent is not None:
            # Clique simples vale pela peca em que ele esta' (folha, frente
            # da gaveta ou chapa): segue os ramos abaixo como se fosse nela.
            atingido = (puxador.parent, *atingido[1:])
        if atingido is not None and _gavetas.grupo_de(atingido[0]) is not None:
            # GAVETA (pedido do usuario, como a porta): clique = todas as
            # gavetas do vao, duplo = so' aquela; Shift soma. O corpo do
            # modulo continua selecionando o modulo.
            grupo=_gavetas.grupo_de(atingido[0])
            somar=self.toggle or self.extend
            individual=(self.modo=='INDIVIDUAL' or (somar and not grupo.select_get()
                and any(g.select_get() for g in _gavetas.gavetas_do_grupo(grupo))))
            _gavetas.selecionar(context, atingido[0],
                                'GAVETA' if individual else 'GRUPO',somar=somar)
            return {'FINISHED'}
        if atingido is not None and _divisorias.grupo_de(atingido[0]) is not None:
            _divisorias.selecionar(context, atingido[0],
                'INDIVIDUAL' if self.modo == 'INDIVIDUAL' else 'GRUPO',
                somar=self.toggle or self.extend)
            return {'FINISHED'}
        if atingido is not None and _prateleiras.grupo_de(atingido[0]) is not None:
            # PRATELEIRAS, como as gavetas: clique = todas do vao, duplo =
            # so' aquela (a aba mostra os vaos dela); Shift soma
            _prateleiras.selecionar(context, atingido[0],
                                    'PRATELEIRA' if self.modo == 'INDIVIDUAL' else 'GRUPO',
                                    somar=self.toggle or self.extend)
            return {'FINISHED'}
        if atingido is not None and _chapas.MARCA_CHAPA in atingido[0]:
            obj = atingido[0]
            anterior = _hud._clique_chapa_hud.get(chave) or ('', 'MODULO')
            mesmo = anterior[0] == obj.name
            if _chapas.MARCA_FOLHA in obj and _portas._grupo_portas(obj) is not None:
                # Porta (backlog do usuario, Epico 3): clique = a PORTA
                # inteira (nunca o modulo); duplo = UMA folha ("aba").
                # Shift soma. Ferragens nao entram (selecao propria).
                somar = self.toggle or self.extend
                if (self.modo != 'INDIVIDUAL' and self.select_passthrough
                        and not somar and obj.select_get()):
                    familia = {_portas._grupo_portas(obj), *_portas._folhas_portas(_portas._grupo_portas(obj))}
                    if any(o not in familia for o in context.selected_objects):
                        # varios selecionados: o arraste leva todos; se
                        # soltar sem arrastar, o CLICK deixa so' a porta
                        _hud._clique_pendente[chave] = obj.name
                        return {'PASS_THROUGH', 'CANCELLED'}
                if modulo_parede is not None and somar:
                    # Shift+duplo na vista da parede isola a folha DENTRO
                    # do modulo que o primeiro clique somou
                    _hud._somar_peca(context, obj, duplo=True)
                    return {'FINISHED'}
                _hud._selecionar_porta_hud(
                    context, obj,
                    'FOLHA' if self.modo == 'INDIVIDUAL' else 'PORTA',
                    somar=somar)
                return {'FINISHED'}
            if self.modo != 'INDIVIDUAL':
                _hud._clique_chapa_hud[chave] = (obj.name,
                                            _hud._nivel_da_selecao(context, obj))
            somar = self.toggle or self.extend
            if somar and _chapas.MARCA_FOLHA not in obj:
                _hud._somar_peca(context, obj, duplo=self.modo == 'INDIVIDUAL')
                return {'FINISHED'}
            if (self.select_passthrough and not somar
                    and self.modo != 'INDIVIDUAL' and obj.select_get()):
                familia = set(_hud._familia_do_clique(obj, context)) | {obj}
                if any(o not in familia for o in context.selected_objects):
                    # Clicou num item JA' selecionado junto com outros:
                    # no PRESS nada muda, senao o arraste so' levaria
                    # este. Se soltar sem arrastar, o CLICK deixa so' ele.
                    _hud._clique_pendente[chave] = obj.name
                    # Como o view3d.select nativo: CANCELLED + PASS_THROUGH.
                    # Com FINISHED o Blender da' o PRESS por consumido e
                    # nao gera o CLICK (alem de gravar um undo vazio).
                    return {'PASS_THROUGH', 'CANCELLED'}
            _hud._selecionar_chapa_hud(context, obj,
                                  self.modo == 'INDIVIDUAL' and mesmo,
                                  somar=somar)
            return {'FINISHED'}
        return self.execute(context)

    def _soltou(self, context, pendente):
        """CLICK depois de um PRESS de CHAPA que deixou passar: so' o
        modulo dela. Todo o resto e' do CLICK nativo -- para objeto comum
        o Blender ja' deixa so' o clicado, e recriar isso aqui e' o que
        NAO se quer."""
        atingido = _hud._raio_hud(context, self.location)
        if not (self.toggle or self.extend):
            _encerrar_edicao_fora(context, atingido[0] if atingido is not None else None)
        if (pendente is None or atingido is None
                or atingido[0].name != pendente):
            return {'PASS_THROUGH'}
        if _chapas.MARCA_FOLHA in atingido[0] and _portas._grupo_portas(atingido[0]) is not None:
            if _paredes_edicao.modulo_da_peca(context, atingido[0]):
                _hud._selecionar_chapa_hud(context, atingido[0])
            else:
                _hud._selecionar_porta_hud(context, atingido[0], 'PORTA')
            return {'FINISHED'}
        _hud._selecionar_chapa_hud(context, atingido[0])
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
        familia = objetos_na_camada(context, familia_de(obj))
        if not familia:
            return r

        # se o clique DESLIGOU a peca (shift), o grupo inteiro apaga junto
        ligado = obj.select_get()
        for o in familia:
            o.select_set(False if self.modo == 'INDIVIDUAL' else ligado, view_layer=context.view_layer)
        if self.modo == 'INDIVIDUAL':
            obj.select_set(True)
        context.view_layer.objects.active = obj
        return r


def malhas_para_editar(context):
    """So' grupos selecionados explicitamente ampliam a edicao nativa.
    Duplo clique numa chapa continua entrando apenas naquela peca.
    """
    marcas = (_chapas.MARCA_CONJUNTO, _chapas.MARCA_PORTAS,
              _gavetas.MARCA_GRUPO, _gavetas.MARCA_GAVETA,
              _prateleiras.MARCA_GRUPO, _divisorias.MARCA_GRUPO)
    grupos = [o for o in context.selected_objects if o.type == 'EMPTY'
              and any(m in o for m in marcas)]
    return objetos_na_camada(context, dict.fromkeys(o for g in grupos for o in g.children_recursive
                if o.type == 'MESH' and not o.hide_render
                and o.get('cabinet_peca') not in _ferragens.PECAS_OCULTAS_RIG))


_edicao_grupo = [None]  # So' nomes: undo/abrir arquivo liberam os objetos.


def recuperar_edicao_grupo(context):
    if _edicao_grupo[0] is not None or not malhas_para_editar(context):
        return
    # Undo pode devolver Edit Mode sem o estado Python. Os Empties que
    # o Blender conservou selecionados ainda identificam o escopo.
    ativo, alvo = context.object, None
    while ativo is not None:
        if ativo.type == 'EMPTY' and ativo.select_get():
            alvo = ativo
        ativo = ativo.parent
    if alvo is not None:
        nomes = [o.name for o in context.selected_objects]
        _edicao_grupo[0] = dict(selecao=nomes, durante=nomes, ativo=alvo.name,
            ferragens=_ferragens.iniciar_edicao_rigs(malhas_para_editar(context), recuperar=True))


def concluir_edicao_grupo(context):
    if context.mode != 'OBJECT' or _edicao_grupo[0] is None:
        return
    estado, _edicao_grupo[0] = _edicao_grupo[0], None
    _ferragens.concluir_edicao_rigs(estado.get('ferragens', {}))
    _formas.esquecer()
    # Sair pelo seletor de modo tambem chega aqui no timer. Se o usuario
    # ja' mudou a selecao, essa nova escolha tem prioridade.
    atuais = {o.name for o in context.selected_objects}
    if atuais != set(estado['durante']):
        return
    for obj in context.selected_objects:
        obj.select_set(obj.name in estado['selecao'])
    for nome in estado['selecao']:
        obj = context.view_layer.objects.get(nome)
        if obj is not None:
            obj.select_set(True)
    ativo = context.view_layer.objects.get(estado['ativo'])
    if ativo is not None and ativo.select_get():
        context.view_layer.objects.active = ativo
    _hud._hover_hud.clear()


class OBJECT_OT_editar_grupo(Operator):
    """Abre as malhas do grupo no Edit Mode original do Blender"""
    bl_idname = 'object.cabinet_editar_grupo'
    bl_label = 'Editar Malhas do Grupo'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if context.mode == 'EDIT_MESH':
            prateleiras = _prateleiras.edicao_atual(context)
            recuperar_edicao_grupo(context)
            return (_edicao_grupo[0] is not None or bool(malhas_para_editar(context))
                    or prateleiras is not None)
        return context.mode == 'OBJECT' and (bool(malhas_para_editar(context)) or
            (context.object is not None and _prateleiras.MARCA_PRATELEIRA in context.object))

    def execute(self, context):
        if context.mode == 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='OBJECT')
            _prateleiras.concluir_edicao()
            concluir_edicao_grupo(context)
            return {'FINISHED'}
        _prateleiras.concluir_edicao()
        concluir_edicao_grupo(context)
        malhas = malhas_para_editar(context)
        global_ = bool(malhas)
        ativo = context.view_layer.objects.active or next(iter(context.selected_objects), None)
        if not malhas and ativo is not None and _prateleiras.MARCA_PRATELEIRA in ativo:
            malhas = [ativo]
        if not malhas:
            return {'CANCELLED'}
        selecionados = [o.name for o in context.selected_objects]
        for o in context.selected_objects:
            # O Empty selecionado e' o escopo do modulo. O Blender o
            # conserva no Edit Mode e no undo; remove-lo espalhava a HUD
            # por todas as chapas ao sair do Tab.
            if o.type != 'EMPTY':
                o.select_set(False)
        for o in malhas:
            # A ferragem compartilha a malha com outros modulos. Editar
            # esta montagem nunca deve alterar outra copia na cena.
            if o.data.users > 1:
                o.data = o.data.copy()
            o.hide_set(False)
            o.hide_select = False
            o.select_set(True)
            _chapas.preparar_uvs_chapa(o)
        _ferragens.preparar_malhas_para_editar(context, malhas)
        # O transformador nativo atualiza UVs/cores durante o gesto,
        # mantendo a densidade da textura tambem nas faces que esticam.
        context.scene.tool_settings.use_transform_correct_face_attributes = True
        context.view_layer.objects.active = ativo if ativo in malhas else malhas[0]
        _prateleiras.iniciar_edicao(context, malhas, global_)
        _edicao_grupo[0] = dict(selecao=selecionados, ativo=ativo.name,
                               durante=[o.name for o in context.selected_objects],
                               ferragens=_ferragens.iniciar_edicao_rigs(malhas))
        bpy.ops.object.mode_set(mode='EDIT')
        # Um Tab rapido pode terminar antes do proximo tique do timer.
        _chapas.absorver_edicoes_de_malha()
        return {'FINISHED'}


_keymaps = []

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
    # Shift+duplo: isola a chapa DENTRO da selecao (ver `_hud._somar_peca`)
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
    for tecla in _solda.TECLAS_CORRENTE:
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

    # Paredes (como no Promob): botao DIREITO segurado num modulo o
    # arrasta ate' uma parede. No "Object Mode" porque o menu de contexto
    # mora la' (e esse keymap vem antes do "3D View"); fora de modulo o
    # operador devolve o evento e o menu abre como sempre.
    km_obj = kc.keymaps.new(name="Object Mode", space_type='EMPTY')
    kmi=km_obj.keymap_items.new('wm.call_menu','L','PRESS',ctrl=True,head=True)
    kmi.properties.name='VIEW3D_MT_cabinet_vinculos'
    _keymaps.append((km_obj,kmi))
    kmi = km_obj.keymap_items.new('object.cabinet_selecionar_montagem_porta', 'G', 'PRESS', shift=True)
    _keymaps.append((km_obj, kmi))
    km_modo = kc.keymaps.new(name='Object Non-modal', space_type='EMPTY')
    kmi = km_modo.keymap_items.new('object.cabinet_editar_grupo', 'TAB', 'PRESS', head=True)
    _keymaps.append((km_modo, kmi))
    kmi = km_obj.keymap_items.new("object.cabinet_arrastar_na_parede",
                                  'RIGHTMOUSE', 'PRESS', head=True)
    _keymaps.append((km_obj, kmi))
    # botao DIREITO na gaveta (pintura rapida sobre um material): tambem
    # aqui, antes do menu de contexto; o poll so' aceita a gaveta
    kmi = km_obj.keymap_items.new("object.cabinet_interagir_gaveta",
                                  'RIGHTMOUSE', 'PRESS', head=True)
    _keymaps.append((km_obj, kmi))

    # Posicionador a partir da grade. O keymap "User Interface" e' o
    # unico que enxerga botoes de painel. O gesto de ARRASTAR raramente
    # chega aqui (o handler de UI consome o PRESS antes), mas o
    # CLIQUE-para-posicionar do operador funciona de qualquer forma.
    km_ui = kc.keymaps.new(name="User Interface", space_type='EMPTY')
    kmi = km_ui.keymap_items.new("object.cabinet_arrastar_preset",
                                 'LEFTMOUSE', 'PRESS', head=True)
    _keymaps.append((km_ui, kmi))


def remover_keymaps():
    _edicao_grupo[0] = None
    for km, kmi in _keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _keymaps.clear()
