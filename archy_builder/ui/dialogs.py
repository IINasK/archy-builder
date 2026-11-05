"""Yes/No questions (viewport popup, black box in the sidebar)."""

import bpy
from bpy.props import IntProperty
from bpy.types import Operator

# Used only at RUNTIME (circular imports): __init__ binds these aliases after loading
# all modules (`_ligar_modulos`).
_eventos = None
_editor = None

def _abrir_pergunta(context):
    """Only open a popup with a window: in --background, popup_menu crashes Blender
    (EXCEPTION_ACCESS_VIOLATION). The pending answer is still recorded; this is how
    tests supply answers."""
    return not bpy.app.background and getattr(context, 'window', None)


# ------------------------------------------------------- questions
# DESIGN RULE (user request, applies to all future actions): use a popup ONLY for
# actions originating in the VIEWPORT (shortcut, Alt+chain/ruler, Enter in vertex mode).
# For a SIDEBAR button, show the question INSIDE the sidebar, directly below the button,
# in a black box (`_pergunta_na_gaveta`). Every confirmation goes through `_perguntar`.
_pergunta_atual = [None]   # {'texto', 'opcoes': [(label, icon, operator, properties)],
                           # 'na_gaveta'}
_na_gaveta = [False]       # True while the sidebar handles a click.


def _menu_pergunta(self, context):
    pergunta = _pergunta_atual[0]
    if pergunta is None:
        return
    for i, (rotulo, icone, _op, _props) in enumerate(pergunta['opcoes']):
        op = self.layout.operator('object.cabinet_responder_pergunta',
                                  text=rotulo, icon=icone)
        op.opcao = i


def _perguntar(context, texto, opcoes, na_gaveta=None):
    """Ask in the appropriate place: a sidebar black box for sidebar clicks, a popup
    for viewport actions."""
    na_gaveta = _na_gaveta[0] if na_gaveta is None else na_gaveta
    _pergunta_atual[0] = {'texto': texto, 'opcoes': list(opcoes),
                          'na_gaveta': bool(na_gaveta)}
    if na_gaveta:
        _eventos._redesenhar_viewports(context)
    elif _abrir_pergunta(context):
        context.window_manager.popup_menu(_menu_pergunta, title=texto,
                                          icon='QUESTION')


class OBJECT_OT_responder_pergunta(Operator):
    """Answer the pending question (sidebar box or popup)."""
    bl_idname = 'object.cabinet_responder_pergunta'
    bl_label = "Answer"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    opcao: IntProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        pergunta, _pergunta_atual[0] = _pergunta_atual[0], None
        _eventos._redesenhar_viewports(context)
        if pergunta is None or not 0 <= self.opcao < len(pergunta['opcoes']):
            return {'CANCELLED'}
        _rotulo, _icone, idname, props = pergunta['opcoes'][self.opcao]
        resultado = _editor.executar(context, idname, 'EXEC_DEFAULT', **props)
        return {'FINISHED'} if 'FINISHED' in resultado else {'CANCELLED'}
