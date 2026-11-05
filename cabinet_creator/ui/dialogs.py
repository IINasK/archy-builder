"""Perguntas Sim/Nao (pop-up na viewport, caixa preta na gaveta)."""

import bpy
from bpy.props import IntProperty
from bpy.types import Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_eventos = None
_editor = None

def _abrir_pergunta(context):
    """Pop-up so' com janela: em --background o popup_menu derruba o
    Blender (EXCEPTION_ACCESS_VIOLATION). A resposta pendente fica gravada
    do mesmo jeito -- e' assim que os testes respondem."""
    return not bpy.app.background and getattr(context, 'window', None)


# ------------------------------------------------------- perguntas
# REGRA DE DESIGN (pedido do usuario, vale para tudo daqui em diante):
# pop-up SO' quando a acao veio da VIEWPORT (atalho, Alt+corrente/regua,
# Enter no modo de vertices). Veio de um botao da GAVETA: a pergunta
# aparece DENTRO dela, logo abaixo do botao, numa caixa preta
# (`_pergunta_na_gaveta`). Toda confirmacao passa por `_perguntar`.
_pergunta_atual = [None]   # {'texto', 'opcoes': [(rotulo, icone, op, props)], 'na_gaveta'}
_na_gaveta = [False]       # True enquanto a gaveta trata um clique


def _menu_pergunta(self, context):
    pergunta = _pergunta_atual[0]
    if pergunta is None:
        return
    for i, (rotulo, icone, _op, _props) in enumerate(pergunta['opcoes']):
        op = self.layout.operator('object.cabinet_responder_pergunta',
                                  text=rotulo, icon=icone)
        op.opcao = i


def _perguntar(context, texto, opcoes, na_gaveta=None):
    """Faz a pergunta no lugar certo: na gaveta (caixa preta) se o clique
    veio dela, em pop-up se veio da viewport."""
    na_gaveta = _na_gaveta[0] if na_gaveta is None else na_gaveta
    _pergunta_atual[0] = {'texto': texto, 'opcoes': list(opcoes),
                          'na_gaveta': bool(na_gaveta)}
    if na_gaveta:
        _eventos._redesenhar_viewports(context)
    elif _abrir_pergunta(context):
        context.window_manager.popup_menu(_menu_pergunta, title=texto,
                                          icon='QUESTION')


class OBJECT_OT_responder_pergunta(Operator):
    """Responde a pergunta pendente (caixa da gaveta ou pop-up)"""
    bl_idname = 'object.cabinet_responder_pergunta'
    bl_label = 'Responder'
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
