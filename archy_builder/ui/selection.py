"""Layered selection (click = cabinet, double click = part) and keymaps."""

import bpy
_visibilidade = None
_alvenaria = None
from bpy.props import BoolProperty, EnumProperty, IntVectorProperty
from bpy.types import Operator, Menu

# Used only at RUNTIME (circular imports): __init__ binds these aliases after loading
# all modules (`_ligar_modulos`).
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

# ====================================================== SELECTION
# One click selects the whole CABINET (Blender's native highlight lights every part);
# two clicks isolate the panel under the cursor.
#
# Entries belong to the ADDON keyconfig, evaluated before the default. When poll fails
# (outside Object Mode or with the option disabled in Preferences), the event falls
# through to native `view3d.select`, fully restoring normal Blender behavior.


def _puxador_do_clique(obj):
    while obj is not None:
        if _chapas.MARCA_PUXADOR in obj:
            return obj
        obj = obj.parent
    return None


def _selecionar_puxador(context, puxador, somar=False):
    # Ancestry identifies the assembly but does not expand accessory selection: clicking
    # an accessory opens only its own functions.
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
    """Sidebar tab responsible for `obj`, or None for an object outside the add-on."""
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
    """Switch the sidebar to the tab matching a viewport CLICK selection (user
    request): door -> Doors, cabinet -> Cabinets, handle -> Handles. Only on clicks:
    the add-on also changes the active object itself (door creation leaves the
    cabinet active), which must not make tabs jump."""
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
        # Like clicking a tab: start at the top and close options.
        tela[_gaveta._CHAVE_ROLAGEM] = 0
        _gaveta._fechar_opcoes(tela)
    _eventos._redesenhar_viewports(context)


def objetos_na_camada(context, objetos):
    """Parent may retain deleted IDs; the native View Layer determines selection."""
    camada = context.view_layer.objects
    return [o for o in objetos if camada.get(o.name) == o]


def montagem_da_porta(context):
    grupo = _ferragens._grupo_da_ferragem(context.object)
    return objetos_na_camada(context, [grupo, *grupo.children_recursive]) if grupo else []


class OBJECT_OT_selecionar_montagem_porta(Operator):
    """Select the door with handles, hardware and all other components."""
    bl_idname = 'object.cabinet_selecionar_montagem_porta'
    bl_label = "Door Group"
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
    """Hide the entire door in the View Layer, including attached components."""
    bl_idname = 'object.cabinet_esconder_porta'
    bl_label = "Hide Door and Attached Components"
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
    bl_label = "Select Group"

    def draw(self, context):
        self.layout.operator_context = 'EXEC_DEFAULT'
        self.layout.operator(OBJECT_OT_selecionar_montagem_porta.bl_idname, icon='OUTLINER_OB_GROUP_INSTANCE')
        self.layout.separator()
        self.layout.operator_menu_enum('object.select_grouped', 'type', text="Blender Groups")


def familia_de(obj):
    """Everything highlighted with obj: the group's panels plus its assembly Empty.

    Selecting the parent TOGETHER with its children is safe: Blender does not
    transform a child twice when its parent is also selected."""
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
    """An outside click ends individual scope, including across viewports."""
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
    """Click selects the whole cabinet; double click isolates the panel."""
    bl_idname = "object.cabinet_selecionar"
    bl_label = "Select Cabinet"
    bl_options = {'UNDO'}

    modo: EnumProperty(
        name="Mode", default='GRUPO',
        items=[('GRUPO', "Group", "Select the entire cabinet"),
               ('INDIVIDUAL', "Individual", "Select only the clicked panel")])
    # Mirror view3d.select properties and forward them unchanged. ALL use SKIP_SAVE:
    # keymap entries set only the listed properties, and others used to come from the
    # LAST invocation. After Shift+click, a plain click inherited toggle=True and added
    # to selection instead of replacing it.
    location: IntVectorProperty(size=2, options={'SKIP_SAVE'})
    extend: BoolProperty(default=False, options={'SKIP_SAVE'})
    deselect: BoolProperty(default=False, options={'SKIP_SAVE'})
    toggle: BoolProperty(default=False, options={'SKIP_SAVE'})
    deselect_all: BoolProperty(default=False, options={'SKIP_SAVE'})
    select_passthrough: BoolProperty(default=False, options={'SKIP_SAVE'})
    # CLICK entry (release without dragging): finish what PRESS passed through, like the
    # native keymap's PRESS/CLICK pair.
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
            # Slider dot: in the user's keyconfig, this entry precedes the slider entry;
            # selecting here would hide the slider.
            return {'PASS_THROUGH'}
        ferragem = _hud._ferragem_sob_mouse(context, self.location)
        if ferragem is not None:
            if not (self.toggle or self.extend):
                _encerrar_edicao_fora(context, ferragem)
            if self.modo == 'INDIVIDUAL':
                # Double click = PART, native selection: Tab, G/R/S, modifiers.
                _ferragens._selecionar_peca(context, ferragem,
                                 somar=self.toggle or self.extend)
            else:
                # Hinge/gas strut: all such parts in the cabinet, in their own mode.
                _ferragens._selecionar_ferragem(context, ferragem,
                                     somar=self.toggle or self.extend)
            return {'FINISHED'}
        # Any other click exits hardware editing mode.
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
                # An already isolated scope takes precedence over wall-view cabinet
                # selection.
                _selecionar_puxador(context, puxador, somar=self.toggle or self.extend)
                return {'FINISHED'}
        modulo_parede = (_paredes_edicao.modulo_da_peca(context, atingido[0])
                         if atingido is not None else None)
        if modulo_parede is not None and self.modo != 'INDIVIDUAL':
            # Wall view: a single click on ANY part selects the cabinet (user request),
            # so native G moves the entire unit. Double clicks still use the per-type
            # branches below.
            obj = atingido[0]
            if self.toggle or self.extend:
                _hud._somar_peca(context, obj)
                return {'FINISHED'}
            if self.select_passthrough and obj.select_get():
                familia = set(_hud._familia_do_clique(obj, context))
                if any(o not in familia for o in context.selected_objects):
                    # Multiple cabinets: dragging moves all; CLICK without dragging
                    # leaves only this one selected (`_soltou`).
                    _hud._clique_pendente[chave] = obj.name
                    return {'PASS_THROUGH', 'CANCELLED'}
            _hud._selecionar_chapa_hud(context, obj)
            return {'FINISHED'}
        if atingido is not None and _chapas.MARCA_FUNDO in atingido[0]:
            _fundos.selecionar(context, atingido[0], somar=self.toggle or self.extend)
            return {'FINISHED'}
        if puxador is not None and puxador.parent is not None:
            # A single click targets the actual part (leaf, drawer front or panel): use
            # the branches below as if clicking it directly.
            atingido = (puxador.parent, *atingido[1:])
        if atingido is not None and _gavetas.grupo_de(atingido[0]) is not None:
            # DRAWER (user request, like doors): click = every drawer in the opening,
            # double click = only this one; Shift adds. Clicking the cabinet body still
            # selects the cabinet.
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
            # SHELVES, like drawers: click = all in the opening, double click = only
            # this one (the tab shows its gaps); Shift adds.
            _prateleiras.selecionar(context, atingido[0],
                                    'PRATELEIRA' if self.modo == 'INDIVIDUAL' else 'GRUPO',
                                    somar=self.toggle or self.extend)
            return {'FINISHED'}
        if atingido is not None and _chapas.MARCA_CHAPA in atingido[0]:
            obj = atingido[0]
            anterior = _hud._clique_chapa_hud.get(chave) or ('', 'MODULO')
            mesmo = anterior[0] == obj.name
            if _chapas.MARCA_FOLHA in obj and _portas._grupo_portas(obj) is not None:
                # Door (user backlog, Epic 3): click = WHOLE DOOR (never the cabinet);
                # double click = ONE leaf. Shift adds. Hardware is excluded and has its
                # own selection.
                somar = self.toggle or self.extend
                if (self.modo != 'INDIVIDUAL' and self.select_passthrough
                        and not somar and obj.select_get()):
                    familia = {_portas._grupo_portas(obj), *_portas._folhas_portas(_portas._grupo_portas(obj))}
                    if any(o not in familia for o in context.selected_objects):
                        # Multiple selected items: dragging moves all; release without
                        # dragging makes CLICK leave only the door selected.
                        _hud._clique_pendente[chave] = obj.name
                        return {'PASS_THROUGH', 'CANCELLED'}
                if modulo_parede is not None and somar:
                    # Shift+double click in wall view isolates the leaf WITHIN the
                    # cabinet added by the first click.
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
                    # Click on an item ALREADY selected with others: change nothing on
                    # PRESS, otherwise dragging would move only this item. On release
                    # without dragging, CLICK leaves only it selected.
                    _hud._clique_pendente[chave] = obj.name
                    # Like native view3d.select: CANCELLED + PASS_THROUGH. With
                    # FINISHED, Blender considers PRESS consumed and generates no CLICK
                    # (and records an empty undo step).
                    return {'PASS_THROUGH', 'CANCELLED'}
            _hud._selecionar_chapa_hud(context, obj,
                                  self.modo == 'INDIVIDUAL' and mesmo,
                                  somar=somar)
            return {'FINISHED'}
        return self.execute(context)

    def _soltou(self, context, pendente):
        """CLICK after a PANEL PRESS passed through: select only its cabinet. All other
        cases belong to native CLICK; for an ordinary object Blender already selects
        only the clicked item, and that behavior must not be recreated here."""
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
        # Blender still decides WHICH object was clicked; this operator only expands or
        # narrows the resulting selection afterward.
        try:
            r = bpy.ops.view3d.select(
                'EXEC_DEFAULT',
                location=tuple(self.location),
                extend=self.extend, deselect=self.deselect,
                toggle=self.toggle, deselect_all=self.deselect_all,
                select_passthrough=self.select_passthrough)
        except Exception as e:
            print("[Archy Builder] selection:", e)
            return {'CANCELLED'}
        if 'PASS_THROUGH' in r or 'CANCELLED' in r:
            return r

        obj = context.object
        familia = objetos_na_camada(context, familia_de(obj))
        if not familia:
            return r

        # If the click DESELECTED the part (Shift), deselect the whole group too.
        ligado = obj.select_get()
        for o in familia:
            o.select_set(False if self.modo == 'INDIVIDUAL' else ligado, view_layer=context.view_layer)
        if self.modo == 'INDIVIDUAL':
            obj.select_set(True)
        context.view_layer.objects.active = obj
        return r


def malhas_para_editar(context):
    """Only explicitly selected groups expand native editing scope. Double-clicking a
    panel still enters only that part."""
    marcas = (_chapas.MARCA_CONJUNTO, _chapas.MARCA_PORTAS,
              _gavetas.MARCA_GRUPO, _gavetas.MARCA_GAVETA,
              _prateleiras.MARCA_GRUPO, _divisorias.MARCA_GRUPO)
    grupos = [o for o in context.selected_objects if o.type == 'EMPTY'
              and any(m in o for m in marcas)]
    return objetos_na_camada(context, dict.fromkeys(o for g in grupos for o in g.children_recursive
                if o.type == 'MESH' and not o.hide_render
                and o.get('cabinet_peca') not in _ferragens.PECAS_OCULTAS_RIG))


_edicao_grupo = [None]  # Names only: undo/opening a file frees objects.


def recuperar_edicao_grupo(context):
    if _edicao_grupo[0] is not None or not malhas_para_editar(context):
        return
    # Undo may restore Edit Mode without Python state. Empties Blender kept selected
    # still identify the scope.
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
    # Exiting through the mode selector also reaches this timer path. If the user has
    # already changed selection, that new choice takes precedence.
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
    """Open group meshes in Blender's native Edit Mode."""
    bl_idname = 'object.cabinet_editar_grupo'
    bl_label = "Edit Group Meshes"
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
            # The selected Empty defines cabinet scope. Blender retains it in Edit Mode
            # and through undo; removing it spread the HUD across all panels when
            # leaving Tab.
            if o.type != 'EMPTY':
                o.select_set(False)
        for o in malhas:
            # Hardware shares meshes with other cabinets. Editing this assembly must
            # never alter another copy in the scene.
            if o.data.users > 1:
                o.data = o.data.copy()
            o.hide_set(False)
            o.hide_select = False
            o.select_set(True)
            _chapas.preparar_uvs_chapa(o)
        _ferragens.preparar_malhas_para_editar(context, malhas)
        # The native transform operator updates UVs/colors during the gesture,
        # preserving texture density on stretched faces too.
        context.scene.tool_settings.use_transform_correct_face_attributes = True
        context.view_layer.objects.active = ativo if ativo in malhas else malhas[0]
        _prateleiras.iniciar_edicao(context, malhas, global_)
        _edicao_grupo[0] = dict(selecao=selecionados, ativo=ativo.name,
                               durante=[o.name for o in context.selected_objects],
                               ferragens=_ferragens.iniciar_edicao_rigs(malhas))
        bpy.ops.object.mode_set(mode='EDIT')
        # A quick Tab may finish before the next timer tick.
        _chapas.absorver_edicoes_de_malha()
        return {'FINISHED'}


_keymaps = []

# (event value, shift, mode, properties forwarded to view3d.select)
# Plain PRESS uses select_passthrough to preserve dragging: clicking an ALREADY selected
# part must not dismantle selection, otherwise the whole selected cabinet could not be
# dragged. CLICK acts only when a PANEL PRESS passed through: native CLICK would leave
# only the panel, not the cabinet. All other cases return PASS_THROUGH so Blender itself
# deselects the other objects.
_ENTRADAS_KEYMAP = (
    ('PRESS', False, 'GRUPO',
     {"deselect_all": True, "select_passthrough": True}),
    ('CLICK', False, 'GRUPO', {"deselect_all": True, "clique": True}),
    ('PRESS', True, 'GRUPO', {"toggle": True}),
    ('DOUBLE_CLICK', False, 'INDIVIDUAL', {"deselect_all": True}),
    # Shift+double click: isolate the panel WITHIN selection (see `_hud._somar_peca`).
    ('DOUBLE_CLICK', True, 'INDIVIDUAL', {"toggle": True}),
)


def registrar_keymaps():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:          # Background Blender does not create a keyconfig.
        return
    km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
    # This entry accepts events only in the sidebar's dedicated area.
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

    # Chains: holding the key chosen in options shows the chain (the operator passes the
    # event through, so Alt/Ctrl/Shift still work everywhere else).
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
    # Leaf opening slider: click WITHOUT modifiers, before selection; outside a slider
    # the operator passes the event through.
    kmi = km.keymap_items.new("object.cabinet_abrir_porta",
                              'LEFTMOUSE', 'PRESS', head=True)
    _keymaps.append((km, kmi))

    # Walls (as in the DXF): hold the RIGHT button on a cabinet to drag it to a wall.
    # Use 'Object Mode' because the context menu lives there (and that keymap precedes
    # '3D View'); outside cabinets the operator passes the event through and the menu
    # opens normally.
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
    # RIGHT button in the sidebar (quick painting over a material): also register here
    # before the context menu; poll only accepts the sidebar.
    kmi = km_obj.keymap_items.new("object.cabinet_interagir_gaveta",
                                  'RIGHTMOUSE', 'PRESS', head=True)
    _keymaps.append((km_obj, kmi))

    # Placement from the grid. The 'User Interface' keymap is the only one that sees
    # panel buttons. DRAG rarely reaches here (the UI handler consumes PRESS first), but
    # the operator's CLICK-to-place works regardless.
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
