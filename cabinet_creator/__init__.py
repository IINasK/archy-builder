bl_info = {
    "name": "Cabinet Creator",
    "author": "Douglas",
    "version": (183, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > gaveta esquerda",
    "doc_url": "",
    "description": "Armarios parametricos: chapas com malha editavel e espessura imune a escala",
    "category": "Object",
}

"""Cabinet Creator: moveis planejados no Blender.

O add-on e' um PACOTE: cada area mora no seu modulo (mapa no CLAUDE.md).
Aqui ficam so' o bl_info, a ordem de carga, a ligacao entre os modulos e o
registro. Um modulo chama outro pelo apelido `_nome` (ex.: `_portas.x`).
"""
# F3 > Reload Scripts / desligar e ligar o add-on: recarrega os modulos na
# mesma ordem (sem isto o Blender so' recarregaria este arquivo)
if "_MODULOS" in locals():
    import importlib
    for _modulo in _MODULOS:
        importlib.reload(_modulo)

import bpy
import bpy.utils.previews
from bpy.props import (FloatProperty, BoolProperty, EnumProperty,
                       StringProperty, IntProperty)
from bpy.types import Operator

# Na ordem de CARGA: cada um so' usa, ao carregar, os que vem antes dele.
from . import chapas as _chapas
from . import modulos as _modulos
from . import biblioteca as _biblioteca
from . import opcoes as _opcoes
from . import eventos as _eventos
from . import selecao as _selecao
from . import portas as _portas
from . import ferragens as _ferragens
from . import assistente as _assistente
from . import gaveta_eventos as _gaveta_eventos
from . import importacao as _importacao
from . import puxadores as _puxadores
from . import arame as _arame
from . import gaveta as _gaveta
from . import orcamento as _orcamento
from . import hud as _hud
from . import solda as _solda
from . import perguntas as _perguntas
from . import portas_viewport as _portas_viewport
from . import gaveta_desenho as _gaveta_desenho
from . import painel_legado as _painel_legado

_MODULOS = (_chapas, _modulos, _biblioteca, _opcoes, _eventos, _selecao,
            _portas, _ferragens, _assistente, _gaveta_eventos, _importacao,
            _puxadores, _arame, _gaveta, _orcamento, _hud, _solda, _perguntas,
            _portas_viewport, _gaveta_desenho, _painel_legado)


def _ligar_modulos():
    """Liga os apelidos `_nome` de cada modulo aos modulos de verdade: as
    chamadas entre areas sao circulares (a gaveta chama as portas, que
    chamam a gaveta), entao so' se ligam depois de todos carregados."""
    for modulo in _MODULOS:
        for outro in _MODULOS:
            nome = '_' + outro.__name__.rsplit('.', 1)[-1]
            if hasattr(modulo, nome):
                setattr(modulo, nome, outro)


_ligar_modulos()


CLASSES = (
    _opcoes.CabinetCreatorPreferences,
    _modulos.OBJECT_OT_sincronizar_grupo,
    _modulos.OBJECT_OT_sincronizar_conjunto,
    _biblioteca.OBJECT_OT_registrar_bibliotecas,
    _biblioteca.OBJECT_OT_refiliar_catalogos,
    _biblioteca.OBJECT_OT_regerar_previews,
    _gaveta.OBJECT_OT_modo_medidas,
    _chapas.OBJECT_OT_criar_chapa,
    _biblioteca.OBJECT_OT_salvar_biblioteca,
    _biblioteca.OBJECT_OT_abrir_pasta_biblioteca,
    _biblioteca.OBJECT_OT_abrir_asset_browser,
    _biblioteca.OBJECT_OT_definir_tamanho,
    _biblioteca.OBJECT_OT_inserir_preset,
    _biblioteca.OBJECT_OT_arrastar_preset,
    _biblioteca.OBJECT_OT_prateleira,
    _selecao.OBJECT_OT_selecionar,
    _biblioteca.OBJECT_OT_navegar,
    _biblioteca.OBJECT_OT_editar_modelo,
    _biblioteca.OBJECT_OT_alternar_bloqueio,
    _modulos.OBJECT_OT_agrupar_conjunto,
    _modulos.OBJECT_OT_detectar_adjacencia,
    _chapas.OBJECT_OT_criar_nicho,
    _orcamento.OBJECT_OT_exportar_orcamento,
    _orcamento.OBJECT_OT_definir_comodo,
    _assistente.OBJECT_OT_apanhar_vao_portas,
    _assistente.OBJECT_OT_portas_parametricas,
    _importacao.OBJECT_OT_converter_modulo,
    _importacao.OBJECT_OT_converter_puxador,
    _importacao.OBJECT_OT_vincular_puxador,
    _importacao.OBJECT_OT_folha_de_objetos,
    _importacao.OBJECT_OT_porta_dupla,
    _importacao.OBJECT_OT_vincular_porta,
    _importacao.OBJECT_OT_corrente_porta,
    _importacao.OBJECT_OT_definir_frente,
    _puxadores.OBJECT_OT_posicionar_puxador,
    _gaveta_eventos.OBJECT_OT_opcoes_gaveta,
    _gaveta_eventos.OBJECT_OT_editar_medida_gaveta,
    _hud.OBJECT_OT_arrastar_hud,
    _gaveta_eventos.OBJECT_OT_interagir_gaveta,
    _gaveta_eventos.OBJECT_OT_alternar_gaveta,
    _chapas.OBJECT_OT_marcar_como_chapa,
    _chapas.OBJECT_OT_normalizar,
    _gaveta_eventos.VIEW3D_GT_alca_gaveta,
    _gaveta_desenho.VIEW3D_GT_campo_gaveta,
    # o slider antes da HUD: a bolinha ganha o clique (gizmo e' avaliado
    # na ordem do registro)
    _portas_viewport.VIEW3D_GT_slider_porta,
    _portas_viewport.VIEW3D_GGT_slider_porta,
    _hud.VIEW3D_GT_hud_cabinet,
    _hud.VIEW3D_GGT_hud_cabinet,
    _hud.VIEW3D_GGT_correntes_cabinet,
    _solda.OBJECT_OT_desassociar,
    _solda.OBJECT_OT_tecla_corrente,
    _solda.OBJECT_OT_clique_corrente,
    _solda.OBJECT_OT_corrente_objeto,
    _solda.OBJECT_OT_desagregar_selecao,
    _perguntas.OBJECT_OT_responder_pergunta,
    _solda.OBJECT_OT_conectar_distancia,
    _solda.OBJECT_OT_recalcular_ancoragem,
    _solda.OBJECT_OT_conectar_vertices,
    _solda.OBJECT_OT_confirmar_conexao,
    _solda.OBJECT_OT_resetar_distancia,
    _solda.OBJECT_OT_arrastar_ancora,
    _portas_viewport.OBJECT_OT_arrastar_canto_porta,
    _ferragens.OBJECT_OT_arrastar_ferragem,
    _puxadores.OBJECT_OT_arrastar_puxador,
    _portas_viewport.OBJECT_OT_cantos_porta,
    _portas_viewport.OBJECT_OT_abrir_porta,
    _solda.OBJECT_OT_nomear_grupo,
    _solda.OBJECT_OT_digitar_nome_grupo,
    _solda.OBJECT_OT_juntar_modulo,
    _gaveta_eventos.VIEW3D_GGT_cabinet_gaveta,
    _biblioteca.VIEW3D_AST_cabinet_creator,
)


# ------------------------------------------ operador terminado larga a cena
# Crash do usuario (repetivel): Ctrl+Z ENQUANTO a porta nascia. O Blender
# guarda o operador (REGISTER) depois que ele termina, e o wizard levava
# em `self` a lista de todos os objetos do ima: no undo seguinte esses
# objetos eram liberados/trocados com o Python ainda segurando-os, e a
# memoria do Python corrompia (crash depois, em lugar aleatorio). Todo
# operador MODAL, ao terminar ou cancelar, solta o que for dado da cena.
def _segura_dado(valor, fundo=0):
    if isinstance(valor, bpy.types.ID):
        return True
    if fundo >= 4:
        return False
    if isinstance(valor, (list, tuple, set, frozenset)):
        return any(_segura_dado(v, fundo + 1) for v in valor)
    if isinstance(valor, dict):
        # objeto como CHAVE tambem segura (ex.: {objeto: posicao})
        return any(_segura_dado(v, fundo + 1)
                   for par in valor.items() for v in par)
    return False


def _soltar_dados_blender(op):
    for nome, valor in list(getattr(op, '__dict__', {}).items()):
        if _segura_dado(valor):
            setattr(op, nome, None)


def _terminou(op, resultado):
    if isinstance(resultado, set) and resultado & {'FINISHED', 'CANCELLED'}:
        _soltar_dados_blender(op)
    return resultado


# Assinaturas EXPLICITAS: o Blender confere o numero de argumentos dos
# metodos do operador ao registrar (*args seria recusado).
def _envolver_evento(metodo):
    def envolvido(self, context, event):
        return _terminou(self, metodo(self, context, event))
    envolvido.larga_dados = True
    return envolvido


def _envolver_cancel(metodo):
    def envolvido(self, context):
        resultado = metodo(self, context)
        _soltar_dados_blender(self)
        return resultado
    envolvido.larga_dados = True
    return envolvido


def _larga_dados_ao_terminar(classe):
    for nome, envolver in (('invoke', _envolver_evento),
                           ('modal', _envolver_evento),
                           ('cancel', _envolver_cancel)):
        metodo = classe.__dict__.get(nome)
        if metodo is not None and not getattr(metodo, 'larga_dados', False):
            setattr(classe, nome, envolver(metodo))
    return classe


for _classe in CLASSES:
    if (isinstance(_classe, type) and issubclass(_classe, Operator)
            and 'modal' in _classe.__dict__):
        _larga_dados_ao_terminar(_classe)
del _classe


_PROPS_MEDIDA_UI_OBJETO = (
    "ui_chapa_largura", "ui_chapa_comprimento", "ui_chapa_espessura",
    "ui_conj_largura", "ui_conj_altura", "ui_conj_profundidade",
    "ui_conj_espessura",
)
_PROPS_MEDIDA_UI_CENA = (
    "ui_grupo_largura", "ui_grupo_altura", "ui_grupo_profundidade",
    "ui_grupo_espessura",
) + tuple(m[0] for m in _portas.MEDIDAS_PORTAS)


def _registrar_medida_ui(dono, nome_ui, nome_mm, nome, minimo_mm):
    """Expoe em metros para o parser nativo, mantendo o dado real em mm."""
    def obter(self):
        return float(getattr(self, nome_mm)) / 1000.0

    def definir(self, valor):
        setattr(self, nome_mm, float(valor) * 1000.0)

    setattr(dono, nome_ui, FloatProperty(
        name=nome,
        description="Sem sufixo usa a unidade da cena; aceita mm, cm e m",
        subtype='DISTANCE',
        unit='LENGTH',
        min=minimo_mm / 1000.0,
        precision=3,
        step=10,
        get=obter,
        set=definir))


def _garantir_unidade_padrao_mm():
    """Campos do addon usam milimetros como unidade implicita da cena."""
    # Durante addon_enable o Blender protege bpy.data com _RestrictData.
    # Adiar evita falha de ativacao e mantem esta configuracao fora do register.
    if not hasattr(bpy.data, "scenes"):
        if not bpy.app.timers.is_registered(_garantir_unidade_padrao_mm):
            bpy.app.timers.register(
                _garantir_unidade_padrao_mm, first_interval=0.0)
        return None
    for cena in bpy.data.scenes:
        unidades = cena.unit_settings
        unidades.system = 'METRIC'
        unidades.scale_length = 1.0
        unidades.length_unit = 'MILLIMETERS'


def register():
    if not bpy.app.timers.is_registered(_gaveta._limitar_largura_gaveta):
        bpy.app.timers.register(_gaveta._limitar_largura_gaveta,
                               first_interval=0.3, persistent=True)
    for c in CLASSES:
        bpy.utils.register_class(c)
    _gaveta._handler_gaveta[0] = bpy.types.SpaceView3D.draw_handler_add(
        _gaveta_desenho._desenhar_gaveta, (), 'WINDOW', 'POST_PIXEL')
    # POST_VIEW: a caixa vive em coordenada de MUNDO, junto da cena
    _hud._handler_grid[0] = bpy.types.SpaceView3D.draw_handler_add(
        _hud._desenhar_grid_medidas, (), 'WINDOW', 'POST_VIEW')
    _hud._handler_hud_texto[0] = bpy.types.SpaceView3D.draw_handler_add(
        _hud._desenhar_hud_texto, (), 'WINDOW', 'POST_PIXEL')
    bpy.app.timers.register(_gaveta._reconectar_gavetas, first_interval=0.1)
    _selecao.registrar_keymaps()
    # DIAGNOSTICO TEMPORARIO: o keymap mesclado so' existe depois do registro
    bpy.app.timers.register(_selecao._log_keymaps, first_interval=1.0)
    S = bpy.types.Scene
    # Os parametros das portas moram na Scene para a gaveta edita-los
    # sem popup (ver `_portas.ESCOLHAS_PORTAS`). Frente e espessuras nao estao
    # aqui de proposito: saem da diagonal e do modulo.
    # A corrente Modulos|Portas sem porta ativa: como nasce a proxima
    S.porta_associar = BoolProperty(
        name="Porta presa ao modulo", default=True,
        description="Ligada: a porta nova segue o modulo e usa os eixos "
                    "dele. Partida: porta solta, nos eixos do mundo")
    S.porta_abertura = EnumProperty(name="Abertura", items=_portas.ITENS_ABERTURA,
                                    default='GIRO',
                                    update=_portas._limitar_folhas_cena)
    # Reta e' o padrao: nenhuma fila de segmentos pode ficar sem
    # nenhuma opcao acesa, e obrigar a escolha so' fazia o botao de
    # criar nascer bloqueado.
    S.porta_dobradica = EnumProperty(name="Dobradica",
                                     items=_portas.ITENS_DOBRADICA,
                                     default='RETA')
    # Dupla e' o padrao de armario; uma folha so' e' a excecao.
    S.porta_folhas = IntProperty(name="Folhas", default=2, min=1, max=4)
    for prop_ui, prop_mm, rotulo, minimo in _portas.MEDIDAS_PORTAS:
        padrao = {'porta_entre_folhas_mm': 2.0, 'porta_recuo_correr_mm': 30.0,
                  'porta_sobreposicao_mm': 20.0,
                  'porta_entre_planos_mm': 2.0}.get(prop_mm, 0.0)
        setattr(S, prop_mm, FloatProperty(name=rotulo, default=padrao,
                                          min=minimo))
        _registrar_medida_ui(S, prop_ui, prop_mm, rotulo, minimo)
    O = bpy.types.Object
    O.chapa_largura_mm = FloatProperty(
        name="Largura (mm)", default=600.0, min=1.0, update=_chapas._upd_chapa)
    O.chapa_comprimento_mm = FloatProperty(
        name="Comprimento (mm)", default=400.0, min=1.0, update=_chapas._upd_chapa)
    O.chapa_espessura_mm = FloatProperty(
        name="Espessura (mm)", default=18.0, min=1.0,
        description="Qualquer espessura; acima de 60 mm o campo fica vermelho",
        update=_chapas._upd_espessura)
    O.chapa_auto = BoolProperty(
        name="Auto-regenerar", default=True,
        description="Obsoleto: a chapa sempre preserva a malha modelada")
    O.conj_largura_mm = FloatProperty(
        name="Largura (mm)", default=600.0, min=20.0, update=_modulos._upd_conj_dim)
    O.conj_altura_mm = FloatProperty(
        name="Altura (mm)", default=400.0, min=20.0, update=_modulos._upd_conj_dim)
    O.conj_profundidade_mm = FloatProperty(
        name="Profundidade (mm)", default=300.0, min=20.0, update=_modulos._upd_conj_dim)
    O.conj_espessura_mm = FloatProperty(
        name="Espessura (mm)", default=18.0, min=1.0,
        description="Espessura de todas as chapas do modulo",
        update=_modulos._upd_conj_espessura)
    O.chapa_modo = EnumProperty(
        name="Modo", default='INDIVIDUAL',
        items=[('INDIVIDUAL', "Individual", "Medidas desta chapa"),
               ('GRUPO', "Grupo", "Medidas do modulo inteiro")])
    _registrar_medida_ui(
        O, "ui_chapa_largura", "chapa_largura_mm", "Largura", 1.0)
    _registrar_medida_ui(
        O, "ui_chapa_comprimento", "chapa_comprimento_mm", "Comprimento", 1.0)
    _registrar_medida_ui(
        O, "ui_chapa_espessura", "chapa_espessura_mm", "Espessura", 1.0)
    _registrar_medida_ui(
        O, "ui_conj_largura", "conj_largura_mm", "Largura", 20.0)
    _registrar_medida_ui(
        O, "ui_conj_altura", "conj_altura_mm", "Altura", 20.0)
    _registrar_medida_ui(
        O, "ui_conj_profundidade", "conj_profundidade_mm", "Profundidade", 20.0)
    _registrar_medida_ui(
        O, "ui_conj_espessura", "conj_espessura_mm", "Espessura", 1.0)

    S = bpy.types.Scene
    S.cabinet_aba = EnumProperty(
        name="Aba", default='MODULOS',
        items=[('MODULOS', "Modulos", "Medidas, montagem e biblioteca"),
               ('PORTAS', "Portas", "Criacao e configuracao de portas"),
               ('PUXADORES', "Puxadores", "Puxadores ligados as portas")])
    # modelo que a ferramenta de posicionar vai criar
    S.cabinet_puxador_modelo = EnumProperty(
        name="Modelo", default='ALCA',
        items=[(k, v[0], "") for k, v in _puxadores.MODELOS_PUXADOR.items()])
    S.chapa_bib_aberta = BoolProperty(name="Biblioteca", default=False)
    S.chapa_n1 = StringProperty(default="")
    S.chapa_n2 = StringProperty(default="")
    S.chapa_n3 = StringProperty(default="")
    # barra continua (estilo volume) no lugar dos tres degraus P/M/G
    # 7 degraus: com 11 a barra ocupava 70% da sidebar e nao cabia no
    # canto. A miniatura maior continua grande o bastante.
    S.chapa_tam_bloco = IntProperty(
        name="Tamanho", default=5, min=2, max=8,
        description="Tamanho das miniaturas na grade")
    S.grupo_largura_mm = FloatProperty(name="Largura (mm)", default=600.0, min=20.0, update=_modulos._upd_grupo_dim)
    S.grupo_altura_mm = FloatProperty(name="Altura (mm)", default=400.0, min=20.0, update=_modulos._upd_grupo_dim)
    S.grupo_profundidade_mm = FloatProperty(name="Profundidade (mm)", default=300.0, min=20.0, update=_modulos._upd_grupo_dim)
    S.grupo_espessura_mm = FloatProperty(name="Espessura (mm)", default=18.0, min=1.0, update=_modulos._upd_grupo_espessura)
    _registrar_medida_ui(
        S, "ui_grupo_largura", "grupo_largura_mm", "Largura", 20.0)
    _registrar_medida_ui(
        S, "ui_grupo_altura", "grupo_altura_mm", "Altura", 20.0)
    _registrar_medida_ui(
        S, "ui_grupo_profundidade", "grupo_profundidade_mm", "Profundidade", 20.0)
    _registrar_medida_ui(
        S, "ui_grupo_espessura", "grupo_espessura_mm", "Espessura", 1.0)

    _garantir_unidade_padrao_mm()

    if _chapas.ao_atualizar_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_chapas.ao_atualizar_depsgraph)
    for evento, funcao in _eventos.HANDLERS_CONTORNO + _eventos.HANDLERS_REFERENCIAS:
        lista = getattr(bpy.app.handlers, evento)
        if funcao not in lista:
            lista.append(funcao)
    if not bpy.app.timers.is_registered(_eventos.verificar_periodicamente):
        bpy.app.timers.register(_eventos.verificar_periodicamente, persistent=True)
    # bpy.ops nao pode rodar dentro de register(): adia por um tique
    bpy.app.timers.register(_registrar_bibliotecas_adiado, first_interval=0.5)


def _registrar_bibliotecas_adiado():
    # funcao com NOME (nao lambda): o unregister precisa poder remove-la
    _biblioteca.registrar_bibliotecas()
    return None


def unregister():
    _solda._tecla_corrente_segurada[0] = False
    _solda._conexao_pendente[0] = None
    _solda._conexao_manual[0] = None
    _solda._desagregar_pendente[0] = None
    _solda._pergunta_reset[0] = ''
    _perguntas._pergunta_atual[0] = None
    _perguntas._na_gaveta[0] = False
    _solda._arraste_ancora[0] = None
    _portas_viewport._arraste_canto_porta[0] = None
    _ferragens._arraste_ferragem[0] = None
    _ferragens._ferragens_selecionadas[0] = None
    _ferragens._dobradica_reta[0] = None
    _puxadores._puxador_perfil[0] = None
    _puxadores._arraste_puxador[0] = None
    _arame._arame_rig[0] = None
    _arame._arame_perfil[0] = None
    _puxadores._corte_perfil[0] = None
    _arame._lotes_arame.clear()
    _portas_viewport._arraste_slider_porta[0] = None
    _portas_viewport._slider_hover[0] = None
    _solda._nome_grupo_gaveta[0] = None
    _orcamento._orcamento_copiado[0] = None
    _ferragens._contagem_objetos[0] = -1
    _solda._bolinha_hover[0] = None
    for timer in (_selecao._log_keymaps, _registrar_bibliotecas_adiado,
                  _hud._animar_piscada, _ferragens._conferir_ferragens,
                  _chapas._separar_copias_no_timer,
                  _orcamento._apagar_orcamento_copiado):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
    _hud._edicao_hud[0] = None
    _hud._hover_hud.clear()
    _hud._clique_chapa_hud.clear()
    _hud._clique_pendente.clear()
    _gaveta._edicao_gaveta[0] = None
    if bpy.app.timers.is_registered(_gaveta._animar_realces):
        bpy.app.timers.unregister(_gaveta._animar_realces)
    _gaveta._realces.clear()
    _gaveta._deslizes.clear()
    if bpy.app.timers.is_registered(_gaveta._limitar_largura_gaveta):
        bpy.app.timers.unregister(_gaveta._limitar_largura_gaveta)
    _selecao.remover_keymaps()
    _gaveta._fechar_gavetas_registradas()
    if _gaveta._handler_gaveta[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_gaveta._handler_gaveta[0], 'WINDOW')
        _gaveta._handler_gaveta[0] = None
    if _hud._handler_grid[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_hud._handler_grid[0], 'WINDOW')
        _hud._handler_grid[0] = None
    if _hud._handler_hud_texto[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_hud._handler_hud_texto[0], 'WINDOW')
        _hud._handler_hud_texto[0] = None
    _hud._campos_gaveta.clear()
    _hud._realce_medida[0] = None
    _gaveta._fotos_gaveta.clear()
    for nome in _gaveta._imagens_gaveta:
        imagem = bpy.data.images.get(nome)
        if imagem is not None:
            bpy.data.images.remove(imagem)
    _gaveta._imagens_gaveta.clear()
    if bpy.app.timers.is_registered(_gaveta._configurar_gavetas):
        bpy.app.timers.unregister(_gaveta._configurar_gavetas)
    if bpy.app.timers.is_registered(_gaveta._reconectar_gavetas):
        bpy.app.timers.unregister(_gaveta._reconectar_gavetas)
    if hasattr(bpy.types.Scene, 'cabinet_aba'):
        del bpy.types.Scene.cabinet_aba
    if hasattr(bpy.types.Scene, 'cabinet_puxador_modelo'):
        del bpy.types.Scene.cabinet_puxador_modelo
    _puxadores._posicionador_puxador[0] = None
    if _puxadores._handler_posicionador[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_puxadores._handler_posicionador[0], 'WINDOW')
        _puxadores._handler_posicionador[0] = None
    if bpy.app.timers.is_registered(_garantir_unidade_padrao_mm):
        bpy.app.timers.unregister(_garantir_unidade_padrao_mm)
    if _biblioteca._previews[0] is not None:
        try:
            bpy.utils.previews.remove(_biblioteca._previews[0])
        except Exception:
            pass
        _biblioteca._previews[0] = None
    _biblioteca._wireframe_ordem.clear()
    if bpy.app.timers.is_registered(_eventos.verificar_periodicamente):
        bpy.app.timers.unregister(_eventos.verificar_periodicamente)
    if bpy.app.timers.is_registered(_eventos._fim_do_desfazer):
        bpy.app.timers.unregister(_eventos._fim_do_desfazer)
    _eventos._desfazendo[0] = False
    if _chapas.ao_atualizar_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_chapas.ao_atualizar_depsgraph)
    for evento, funcao in _eventos.HANDLERS_CONTORNO + _eventos.HANDLERS_REFERENCIAS:
        lista = getattr(bpy.app.handlers, evento)
        if funcao in lista:
            lista.remove(funcao)
    # desligar o add-on no meio da edicao nao pode deixar a viewport sem
    # contorno para sempre
    _eventos.sincronizar_contornos(devolver=True)
    _eventos._contornos_do_usuario.clear()
    for nome in _PROPS_MEDIDA_UI_OBJETO:
        if hasattr(bpy.types.Object, nome):
            delattr(bpy.types.Object, nome)
    for nome in _PROPS_MEDIDA_UI_CENA + _portas._PROPS_PORTAS_CENA:
        if hasattr(bpy.types.Scene, nome):
            delattr(bpy.types.Scene, nome)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
