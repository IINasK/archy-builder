"""Native interface editors: persistent identity and scene commands."""
from contextlib import contextmanager
import bpy
from bpy.types import NodeTree, GizmoGroup
from .. import gaveta_eventos as _gaveta_eventos

_gaveta = _biblioteca_faixa = _eventos = None
TIPO_MENU = 'ArchyBuilderMenu'
TIPO_BIBLIOTECA = 'ArchyBuilderBiblioteca'
MARCA_INTERFACE = 'cabinet_interface'
_keymaps = [[]]


class CABINET_NT_menu(NodeTree):
    bl_idname = TIPO_MENU
    bl_label = 'Archy Builder'
    bl_icon = 'NODETREE'


class CABINET_NT_biblioteca(NodeTree):
    bl_idname = TIPO_BIBLIOTECA
    bl_label = "Archy Builder Library"
    bl_icon = 'ASSET_MANAGER'


def eh_editor(area, tipo=None):
    return bool(area is not None and getattr(area, 'type', None) == 'NODE_EDITOR'
                and getattr(area.spaces.active, 'tree_type', None) in ((tipo,) if tipo else (TIPO_MENU, TIPO_BIBLIOTECA)))


def configurar(area, tipo=TIPO_MENU):
    area.type = 'NODE_EDITOR'
    area.ui_type = tipo
    espaco = area.spaces.active
    # In 4.2, the gizmo map only draws with an open tree. This empty ID belongs to the
    # interface, never to materials or Geometry Nodes.
    arvore = next((a for a in bpy.data.node_groups
                   if a.bl_idname == tipo and a.get(MARCA_INTERFACE)), None)
    if arvore is None:
        arvore = bpy.data.node_groups.new('Interface ' + ('Archy Builder' if tipo == TIPO_MENU else "Archy Builder Library"), tipo)
        arvore[MARCA_INTERFACE] = True
        arvore.use_fake_user = True
    espaco.node_tree = arvore
    espaco.pin = True
    espaco.show_region_ui = False
    espaco.show_region_toolbar = False
    espaco.show_region_header = tipo == TIPO_MENU
    if hasattr(espaco, 'show_gizmo'):
        espaco.show_gizmo = True
    espaco.overlay.show_overlays = False
    area.show_menus = False
    area.tag_redraw()


def reparar(screen):
    if _eventos._desfazendo[0]:
        return
    for area in screen.areas:
        if eh_editor(area):
            if area.spaces.active.node_tree is None:
                configurar(area, area.spaces.active.tree_type)
            chave = _gaveta._CHAVE_GAVETA if eh_editor(area, TIPO_MENU) else _biblioteca_faixa.CHAVE_AREA
            # Consume the old marker to avoid reconverting a viewport the user later
            # chose in the editor selector.
            screen[chave] = 0


LOCAIS = {'object.cabinet_interagir_gaveta', 'object.cabinet_arrastar_preset',
          'object.cabinet_editar_medida_gaveta', 'object.cabinet_digitar_nome_grupo',
          'object.cabinet_opcoes_gaveta'}


@contextmanager
def contexto_do_comando(context, identificador):
    if not eh_editor(getattr(context, 'area', None)) or identificador in LOCAIS:
        yield
        return
    area = _biblioteca_faixa.viewport(context.screen)
    regiao = next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None
    if regiao is None:
        raise RuntimeError("Open a 3D viewport to use this command")
    with context.temp_override(area=area, region=regiao):
        yield


def executar(context, identificador, modo='INVOKE_DEFAULT', **props):
    modulo, nome = identificador.split('.')
    with contexto_do_comando(context, identificador):
        return getattr(getattr(bpy.ops, modulo), nome)(modo, **props)


def pode_executar(identificador):
    try:
        modulo, nome = identificador.split('.')
        with contexto_do_comando(bpy.context, identificador):
            return getattr(getattr(bpy.ops, modulo), nome).poll()
    except (AttributeError, RuntimeError):
        return False


class NODE_GGT_cabinet_gaveta(_gaveta_eventos._GizmosGaveta, GizmoGroup):
    bl_idname = 'NODE_GGT_cabinet_gaveta'
    bl_label = 'Archy Builder'
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'SCALE'}

    @classmethod
    def poll(cls, context):
        return eh_editor(context.area)


@bpy.app.handlers.persistent
def _ao_carregar(*_args):
    if not bpy.app.timers.is_registered(_gaveta._reconectar_gavetas):
        bpy.app.timers.register(_gaveta._reconectar_gavetas, first_interval=.1)


def registrar():
    if _ao_carregar not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_ao_carregar)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is not None:
        km = kc.keymaps.new(name='Node Editor', space_type='NODE_EDITOR')
        for evento in ('LEFTMOUSE', 'RIGHTMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
                       'MIDDLEMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM'):
            valor = 'ANY' if evento.startswith('TRACKPAD') else 'PRESS'
            kmi = km.keymap_items.new('object.cabinet_interagir_gaveta', evento, valor, head=True, any=True)
            _keymaps[0].append((km, kmi))


def desregistrar():
    if _ao_carregar in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_ao_carregar)
    for km, kmi in _keymaps[0]:
        km.keymap_items.remove(kmi)
    _keymaps[0].clear()
    # The user may have selected this editor in an existing area; disabling the add-on
    # must not merge or destroy that area.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if eh_editor(area):
                chave = _gaveta._CHAVE_GAVETA if eh_editor(area, TIPO_MENU) else _biblioteca_faixa.CHAVE_AREA
                screen[chave] = 0
            for espaco in area.spaces:
                if (espaco.type == 'NODE_EDITOR' and
                        espaco.tree_type in (TIPO_MENU, TIPO_BIBLIOTECA)):
                    espaco.node_tree = None
                    espaco.pin = False
                    espaco.tree_type = 'ShaderNodeTree'
                    espaco.show_region_header = True
    for arvore in list(bpy.data.node_groups):
        if arvore.get(MARCA_INTERFACE) and arvore.bl_idname in (TIPO_MENU, TIPO_BIBLIOTECA):
            bpy.data.node_groups.remove(arvore)
