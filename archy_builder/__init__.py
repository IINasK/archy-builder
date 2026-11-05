bl_info = {
    "name": "Archy Builder",
    "author": "Douglas",
    "version": (410, 0, 0),
    "blender": (4, 0, 0),
    "location": "Archy Builder editor / View3D > left sidebar",
    "doc_url": "https://github.com/IINasK/archy-builder",
    "description": "Fitted furniture, woodworking, architecture and interiors in Blender",
    "category": "Object",
}

"""Archy Builder: fitted furniture, architecture and interiors in Blender.

Each responsibility has its own module; see ARCHITECTURE.md. This entry point
owns metadata, explicit loading, cross-module references and registration.
Modules call their owners through module references such as `_portas.x`.
"""
# F3 > Reload Scripts / disable and re-enable the add-on: reload modules in the same
# order (otherwise Blender would only reload this file).
if "_MODULOS" in locals():
    import importlib
    for _modulo in _MODULOS:
        importlib.reload(_modulo)

import sys
import bpy
import bpy.utils.previews
from bpy.props import (FloatProperty, BoolProperty, EnumProperty,
                       StringProperty, IntProperty)
from bpy.types import Operator

# LOAD order: at import time, each module only uses modules loaded before it.
from .cabinetry import panels as _chapas
chapas = _chapas
sys.modules[__name__ + ".chapas"] = _chapas
from .cabinetry import cabinets as _modulos
modulos = _modulos
sys.modules[__name__ + ".modulos"] = _modulos
from .integrations import library as _biblioteca
biblioteca = _biblioteca
sys.modules[__name__ + ".biblioteca"] = _biblioteca
from .integrations import materials as _materiais
materiais = _materiais
sys.modules[__name__ + ".materiais"] = _materiais
from .core import options as _opcoes
opcoes = _opcoes
sys.modules[__name__ + ".opcoes"] = _opcoes
from .core import events as _eventos
eventos = _eventos
sys.modules[__name__ + ".eventos"] = _eventos
from .ui import selection as _selecao
selecao = _selecao
sys.modules[__name__ + ".selecao"] = _selecao
from .cabinetry import doors as _portas
portas = _portas
sys.modules[__name__ + ".portas"] = _portas
from .cabinetry import hardware as _ferragens
ferragens = _ferragens
sys.modules[__name__ + ".ferragens"] = _ferragens
from .cabinetry import door_assistant as _assistente
assistente = _assistente
sys.modules[__name__ + ".assistente"] = _assistente
from .ui import sidebar_events as _gaveta_eventos
gaveta_eventos = _gaveta_eventos
sys.modules[__name__ + ".gaveta_eventos"] = _gaveta_eventos
from .integrations import importing as _importacao
importacao = _importacao
sys.modules[__name__ + ".importacao"] = _importacao
from .cabinetry import handles as _puxadores
puxadores = _puxadores
sys.modules[__name__ + ".puxadores"] = _puxadores
from .ui import wireframe as _arame
arame = _arame
sys.modules[__name__ + ".arame"] = _arame
from .ui import sidebar as _gaveta
gaveta = _gaveta
sys.modules[__name__ + ".gaveta"] = _gaveta
from .ui import library_strip as _biblioteca_faixa
biblioteca_faixa = _biblioteca_faixa
sys.modules[__name__ + ".biblioteca_faixa"] = _biblioteca_faixa
from .integrations import estimates as _orcamento
orcamento = _orcamento
sys.modules[__name__ + ".orcamento"] = _orcamento
from .ui import hud as _hud
hud = _hud
sys.modules[__name__ + ".hud"] = _hud
from .ui import volume_hud as _hud_volume
hud_volume = _hud_volume
sys.modules[__name__ + ".hud_volume"] = _hud_volume
from .cabinetry import welding as _solda
solda = _solda
sys.modules[__name__ + ".solda"] = _solda
from .ui import dialogs as _perguntas
perguntas = _perguntas
sys.modules[__name__ + ".perguntas"] = _perguntas
from .ui import door_controls as _portas_viewport
portas_viewport = _portas_viewport
sys.modules[__name__ + ".portas_viewport"] = _portas_viewport
from .ui import sidebar_drawing as _gaveta_desenho
gaveta_desenho = _gaveta_desenho
sys.modules[__name__ + ".gaveta_desenho"] = _gaveta_desenho
from .architecture import walls as _paredes
paredes = _paredes
sys.modules[__name__ + ".paredes"] = _paredes
from .architecture import wall_selection as _paredes_selecao
paredes_selecao = _paredes_selecao
sys.modules[__name__ + ".paredes_selecao"] = _paredes_selecao
from .architecture import wall_editor as _paredes_edicao
paredes_edicao = _paredes_edicao
sys.modules[__name__ + ".paredes_edicao"] = _paredes_edicao
from .architecture import wall_layout as _paredes_composicao
paredes_composicao = _paredes_composicao
sys.modules[__name__ + ".paredes_composicao"] = _paredes_composicao
from .cabinetry import shapes as _formas
formas = _formas
sys.modules[__name__ + ".formas"] = _formas
from .cabinetry import drawers as _gavetas
gavetas = _gavetas
sys.modules[__name__ + ".gavetas"] = _gavetas
from .cabinetry import shelves as _prateleiras
prateleiras = _prateleiras
sys.modules[__name__ + ".prateleiras"] = _prateleiras
from .cabinetry import partitions as _divisorias
divisorias = _divisorias
sys.modules[__name__ + ".divisorias"] = _divisorias
from .cabinetry import backs as _fundos
fundos = _fundos
sys.modules[__name__ + ".fundos"] = _fundos
from .integrations import native_conversion as _promob
promob = _promob
sys.modules[__name__ + ".promob"] = _promob
from .core import geometry as _geometria
geometria = _geometria
sys.modules[__name__ + ".geometria"] = _geometria
from .cabinetry import fronts as _frentes
frentes = _frentes
sys.modules[__name__ + ".frentes"] = _frentes
from .ui import legacy_panel as _painel_legado
painel_legado = _painel_legado
sys.modules[__name__ + ".painel_legado"] = _painel_legado
from .ui import editor as _editor
editor = _editor
sys.modules[__name__ + ".editor"] = _editor
from .ui import creation_areas as _areas_criacao
areas_criacao = _areas_criacao
sys.modules[__name__ + ".areas_criacao"] = _areas_criacao
from .ui import visibility as _visibilidade
visibilidade = _visibilidade
sys.modules[__name__ + ".visibilidade"] = _visibilidade
from .architecture import rooms as _ambientes
ambientes = _ambientes
sys.modules[__name__ + ".ambientes"] = _ambientes
from .architecture import masonry as _alvenaria
alvenaria = _alvenaria
sys.modules[__name__ + ".alvenaria"] = _alvenaria
from .architecture import installations as _instalacoes
instalacoes = _instalacoes
sys.modules[__name__ + ".instalacoes"] = _instalacoes
from .architecture import openings as _esquadrias
esquadrias = _esquadrias
sys.modules[__name__ + ".esquadrias"] = _esquadrias
from .architecture import lighting as _iluminacao
iluminacao = _iluminacao
sys.modules[__name__ + ".iluminacao"] = _iluminacao

_MODULOS = (_chapas, _modulos, _biblioteca, _materiais, _opcoes, _eventos, _selecao,
            _portas, _ferragens, _assistente, _gaveta_eventos, _importacao,
            _puxadores, _arame, _gaveta, _orcamento, _hud, _solda, _perguntas,
            _portas_viewport, _gaveta_desenho, _paredes, _formas, _gavetas, _prateleiras, _promob,
            _geometria, _frentes, _biblioteca_faixa, _painel_legado, _divisorias, _hud_volume,
            _paredes_edicao, _paredes_composicao, _fundos, _paredes_selecao, _editor, _areas_criacao, _visibilidade, _ambientes, _alvenaria,
            _instalacoes, _esquadrias, _iluminacao)


_MODULE_ALIASES = {
    "opcoes": _opcoes,
    "eventos": _eventos,
    "geometria": _geometria,
    "chapas": _chapas,
    "modulos": _modulos,
    "portas": _portas,
    "gavetas": _gavetas,
    "prateleiras": _prateleiras,
    "divisorias": _divisorias,
    "formas": _formas,
    "frentes": _frentes,
    "fundos": _fundos,
    "solda": _solda,
    "ferragens": _ferragens,
    "puxadores": _puxadores,
    "assistente": _assistente,
    "gaveta": _gaveta,
    "gaveta_desenho": _gaveta_desenho,
    "gaveta_eventos": _gaveta_eventos,
    "editor": _editor,
    "selecao": _selecao,
    "hud": _hud,
    "hud_volume": _hud_volume,
    "biblioteca_faixa": _biblioteca_faixa,
    "arame": _arame,
    "perguntas": _perguntas,
    "painel_legado": _painel_legado,
    "areas_criacao": _areas_criacao,
    "visibilidade": _visibilidade,
    "portas_viewport": _portas_viewport,
    "alvenaria": _alvenaria,
    "ambientes": _ambientes,
    "paredes": _paredes,
    "paredes_selecao": _paredes_selecao,
    "paredes_edicao": _paredes_edicao,
    "paredes_composicao": _paredes_composicao,
    "instalacoes": _instalacoes,
    "esquadrias": _esquadrias,
    "iluminacao": _iluminacao,
    "biblioteca": _biblioteca,
    "materiais": _materiais,
    "orcamento": _orcamento,
    "importacao": _importacao,
    "promob": _promob,
}


def _ligar_modulos():
    """Bind historical domain references to their single canonical module."""
    for modulo in _MODULOS:
        for nome, outro in _MODULE_ALIASES.items():
            apelido = "_" + nome
            if hasattr(modulo, apelido):
                setattr(modulo, apelido, outro)


_ligar_modulos()


CLASSES = (
    _selecao.VIEW3D_MT_grupo_porta,
    _selecao.OBJECT_OT_selecionar_montagem_porta,
    _selecao.OBJECT_OT_esconder_porta,
    _areas_criacao.OBJECT_OT_definir_area,
    _areas_criacao.OBJECT_OT_aplicar_area,
    _areas_criacao.OBJECT_OT_cancelar_area,
    _areas_criacao.OBJECT_OT_internos,
    _areas_criacao.OBJECT_OT_portas_internos,
    _visibilidade.OBJECT_OT_alternar_partes,
    _visibilidade.OBJECT_OT_editar_grupo_visual,
    _editor.CABINET_NT_menu,
    _editor.CABINET_NT_biblioteca,
    _fundos.OBJECT_OT_criar_fundo,
    _fundos.OBJECT_OT_desassociar_fundo,
    _paredes_composicao.OBJECT_OT_redistribuir_parede,
    _paredes_composicao.OBJECT_OT_trocar_modelo_parede,
    _paredes_composicao.OBJECT_OT_editar_cota_parede,
    _paredes_composicao.OBJECT_OT_mover_na_parede,
    _paredes_composicao.OBJECT_OT_restaurar_guias_parede,
    _paredes_edicao.OBJECT_OT_editar_parede,
    _paredes_edicao.OBJECT_OT_confirmar_ponto_parede,
    _paredes_edicao.OBJECT_OT_marcar_ponto_parede,
    _paredes_edicao.OBJECT_OT_confirmar_area_parede,
    _paredes_edicao.OBJECT_OT_voltar_area_parede,
    _paredes_edicao.OBJECT_OT_cancelar_area_parede,
    _paredes_edicao.OBJECT_OT_sair_parede,
    _paredes_edicao.OBJECT_OT_escolher_vao_parede,
    _paredes_edicao.OBJECT_OT_cancelar_previa_parede,
    _paredes_edicao.OBJECT_OT_distribuir_parede,
    _paredes_edicao.OBJECT_OT_observar_parede,
    _paredes_edicao.VIEW3D_MT_parede_cabinet,
    _biblioteca_faixa.OBJECT_OT_recolher_biblioteca,
    _biblioteca_faixa.OBJECT_OT_acao_item_biblioteca,
    _biblioteca_faixa.OBJECT_OT_lugar_biblioteca,
    _opcoes.ArchyBuilderPreferences,
    _modulos.OBJECT_OT_sincronizar_grupo,
    _modulos.OBJECT_OT_sincronizar_conjunto,
    _modulos.OBJECT_OT_fundo_modulo,
    _importacao.OBJECT_OT_importar_promob,
    _geometria.OBJECT_OT_calcular_areas,
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
    _selecao.OBJECT_OT_selecionar,
    _biblioteca.OBJECT_OT_navegar,
    _materiais.OBJECT_OT_aplicar_material,
    _materiais.OBJECT_OT_vincular_materiais,
    _materiais.VIEW3D_MT_vinculos,
    _materiais.OBJECT_OT_novo_material,
    _materiais.OBJECT_OT_editar_material,
    _materiais.OBJECT_OT_apagar_material,
    _materiais.OBJECT_OT_pintar_modulos,
    _biblioteca.OBJECT_OT_editar_modelo,
    _biblioteca.OBJECT_OT_alternar_bloqueio,
    _modulos.OBJECT_OT_agrupar_conjunto,
    _selecao.OBJECT_OT_editar_grupo,
    _portas.OBJECT_OT_espelhar_porta,
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
    _hud.OBJECT_OT_confirmar_quina_hud,
    _hud.OBJECT_OT_mover_quina_hud,
    _hud_volume.OBJECT_OT_confirmar_volume,
    _hud_volume.OBJECT_OT_observar_volume,
    _hud_volume.OBJECT_OT_transformar_volume,
    _gaveta_eventos.OBJECT_OT_interagir_gaveta,
    _gaveta_eventos.OBJECT_OT_alternar_gaveta,
    _chapas.OBJECT_OT_marcar_como_chapa,
    _chapas.OBJECT_OT_normalizar,
    _gaveta_eventos.VIEW3D_GT_alca_gaveta,
    _gaveta_desenho.VIEW3D_GT_campo_gaveta,
    # Register the slider before the HUD so its dot wins the click; gizmos are evaluated
    # in registration order.
    _portas_viewport.VIEW3D_GT_slider_porta,
    _portas_viewport.VIEW3D_GGT_slider_porta,
    _gavetas.VIEW3D_GT_slider_gaveta,
    _gavetas.VIEW3D_GGT_slider_gaveta,
    _gavetas.OBJECT_OT_criar_gavetas,
    _gavetas.OBJECT_OT_normalizar_gavetas,
    _gavetas.OBJECT_OT_abrir_gaveta,
    _gavetas.OBJECT_OT_arrastar_ponto_gaveta,
    _gavetas.OBJECT_OT_confirmar_ancora_gaveta,
    _gavetas.OBJECT_OT_confirmar_ponto_vao,
    _gavetas.OBJECT_OT_marcar_ponto_vao,
    _gavetas.OBJECT_OT_mover_ancora_gaveta,
    _prateleiras.OBJECT_OT_criar_prateleiras,
    _prateleiras.OBJECT_OT_referencia_prateleira,
    _prateleiras.OBJECT_OT_alinhar_prateleiras,
    _divisorias.OBJECT_OT_criar_divisorias,
    _hud.VIEW3D_GT_hud_cabinet,
    _hud.VIEW3D_GGT_hud_cabinet,
    _hud.VIEW3D_GGT_correntes_cabinet,
    # Wall guides: the number is a gizmo so it takes precedence over selection (keymap).
    _paredes.VIEW3D_GT_guia_parede,
    _paredes.VIEW3D_GGT_guias_parede,
    _paredes.OBJECT_OT_definir_alvenaria,
    _alvenaria.OBJECT_OT_classificar_alvenaria,
    _alvenaria.OBJECT_OT_confirmar_alvenaria,
    _alvenaria.OBJECT_OT_visualizar_alvenaria,
    _instalacoes.OBJECT_OT_instalar,
    _instalacoes.OBJECT_OT_acao_instalacao,
    _iluminacao.OBJECT_OT_rebaixar_faces,
    _ambientes.OBJECT_OT_definir_ambiente,
    _ambientes.OBJECT_OT_editar_ambientes,
    _ambientes.OBJECT_OT_cor_ambiente,
    _paredes.OBJECT_OT_arrastar_na_parede,
    _paredes.OBJECT_OT_guia_parede,
    _paredes.OBJECT_OT_desassociar_parede,
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
    _solda.OBJECT_OT_acao_criacao_solda,
    _solda.OBJECT_OT_resetar_distancia,
    _solda.OBJECT_OT_arrastar_ancora,
    _solda.OBJECT_OT_confirmar_ancora_solda,
    _solda.OBJECT_OT_mover_ancora_solda,
    _portas_viewport.OBJECT_OT_arrastar_canto_porta,
    _portas_viewport.OBJECT_OT_confirmar_canto_porta,
    _portas_viewport.OBJECT_OT_mover_canto_porta,
    _ferragens.OBJECT_OT_arrastar_ferragem,
    _puxadores.OBJECT_OT_arrastar_puxador,
    _puxadores.OBJECT_OT_usar_como_puxador,
    _portas_viewport.OBJECT_OT_cantos_porta,
    _portas_viewport.OBJECT_OT_abrir_porta,
    _solda.OBJECT_OT_nomear_grupo,
    _solda.OBJECT_OT_digitar_nome_grupo,
    _solda.OBJECT_OT_juntar_modulo,
    _gaveta_eventos.VIEW3D_GGT_cabinet_gaveta,
    _editor.NODE_GGT_cabinet_gaveta,
    _biblioteca.VIEW3D_AST_archy_builder,
)


# ------------------------------------------ finished operators release the scene
# Reproducible user crash: Ctrl+Z WHILE a door was being created. Blender retains
# REGISTER operators after completion, and the wizard kept the list of all snap objects
# in `self`. On the next undo, those objects were freed/replaced while Python still held
# them, corrupting Python memory and causing a later crash at an arbitrary location.
# Every MODAL operator releases all scene data on completion or cancellation.
def _segura_dado(valor, fundo=0):
    if isinstance(valor, bpy.types.ID):
        return True
    if fundo >= 4:
        return False
    if isinstance(valor, (list, tuple, set, frozenset)):
        return any(_segura_dado(v, fundo + 1) for v in valor)
    if isinstance(valor, dict):
        # Objects held as dictionary KEYS also retain references (e.g. {object:
        # position}).
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


# EXPLICIT signatures: Blender checks operator method argument counts during
# registration (*args would be rejected).
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
        metodo = getattr(classe,nome,None)
        if metodo is not None and not getattr(metodo, 'larga_dados', False):
            setattr(classe, nome, envolver(metodo))
    return classe


for _classe in CLASSES:
    if (isinstance(_classe, type) and issubclass(_classe, Operator)
            and getattr(getattr(_classe,'modal',None),'__code__',None) is not None):
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
    """Expose meters to the native parser while keeping the actual data in mm."""
    def obter(self):
        return float(getattr(self, nome_mm)) / 1000.0

    def definir(self, valor):
        setattr(self, nome_mm, float(valor) * 1000.0)

    setattr(dono, nome_ui, FloatProperty(
        name=nome,
        description="Without a suffix, uses the scene unit; accepts mm, cm and m",
        subtype='DISTANCE',
        unit='LENGTH',
        min=minimo_mm / 1000.0,
        precision=3,
        step=10,
        get=obter,
        set=definir))


def _garantir_unidade_padrao_mm():
    """Add-on fields use millimeters as the scene's implicit unit."""
    # During addon_enable, Blender protects bpy.data with _RestrictData. Deferring
    # avoids activation failure and keeps this setup outside register.
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
    _paredes_selecao.esquecer()
    if not bpy.app.timers.is_registered(_gaveta._limitar_largura_gaveta):
        bpy.app.timers.register(_gaveta._limitar_largura_gaveta,
                               first_interval=0.3, persistent=True)
    for c in CLASSES:
        bpy.utils.register_class(c)
    _portas_viewport.registrar_macro_canto()
    _solda.registrar_macro_ancora()
    _gavetas.registrar_macro_ancora()
    _hud_volume.registrar_macro()
    _hud.registrar_macro_quina()
    _gavetas.registrar_macro_criacao()
    _paredes_edicao.registrar_macro_area()
    _gaveta._handler_gaveta[0] = bpy.types.SpaceView3D.draw_handler_add(
        _gaveta_desenho._desenhar_gaveta, (), 'WINDOW', 'POST_PIXEL')
    # POST_VIEW: the box uses WORLD coordinates, alongside the scene.
    _hud._handler_grid[0] = bpy.types.SpaceView3D.draw_handler_add(
        _hud._desenhar_grid_medidas, (), 'WINDOW', 'POST_VIEW')
    _hud._handler_hud_texto[0] = bpy.types.SpaceView3D.draw_handler_add(
        _hud._desenhar_hud_texto, (), 'WINDOW', 'POST_PIXEL')
    _ambientes._handler[0]=bpy.types.SpaceView3D.draw_handler_add(
        _ambientes.desenhar,(), 'WINDOW','POST_VIEW')
    bpy.app.timers.register(_gaveta._reconectar_gavetas, first_interval=0.1)
    _selecao.registrar_keymaps()
    _editor.registrar()
    S = bpy.types.Scene
    # Door parameters live on Scene so the sidebar can edit them without a popup (see
    # `_portas.ESCOLHAS_PORTAS`). Front dimensions and thicknesses are deliberately
    # absent: they come from the diagonal and cabinet. The Cabinets|Doors chain with no
    # active door controls how the next door is created.
    S.porta_associar = BoolProperty(
        name="Door attached to cabinet", default=True,
        description="Linked: the new door follows the cabinet and uses its axes. Unlinked: freestanding door, using world axes")
    S.porta_abertura = EnumProperty(name="Opening", items=_portas.ITENS_ABERTURA,
                                    default='GIRO',
                                    update=_portas._limitar_folhas_cena)
    # Straight is the default: every segmented row must have an active option. Requiring
    # an explicit choice merely left the creation button disabled initially.
    S.porta_dobradica = EnumProperty(name="Hinge",
                                     items=_portas.ITENS_DOBRADICA,
                                     default='RETA')
    # Framed sliding-door track (requested during creation).
    S.porta_trilho = EnumProperty(name="Track", items=_portas.ITENS_TRILHO,
                                  default='PESADO')
    # Sliding-door leaf: panel or aluminum frame.
    S.porta_folha = EnumProperty(name="Leaf", items=_portas.ITENS_FOLHA_CORRER,
                                 default='CHAPA')
    # Double doors are the cabinet default; a single leaf is the exception.
    S.porta_folhas = IntProperty(name="Leaves", default=2, min=1, max=8)
    for prop_ui, prop_mm, rotulo, minimo in _portas.MEDIDAS_PORTAS:
        padrao = _portas.PADRAO_MEDIDAS_PORTAS.get(prop_mm, 0.0)
        setattr(S, prop_mm, FloatProperty(name=rotulo, default=padrao,
                                          min=minimo))
        _registrar_medida_ui(S, prop_ui, prop_mm, rotulo, minimo)
    O = bpy.types.Object
    O.chapa_largura_mm = FloatProperty(
        name="Width (mm)", default=600.0, min=1.0, update=_chapas._upd_chapa)
    O.chapa_comprimento_mm = FloatProperty(
        name="Length (mm)", default=400.0, min=1.0, update=_chapas._upd_chapa)
    O.chapa_espessura_mm = FloatProperty(
        name="Thickness (mm)", default=18.0, min=1.0,
        description="Any thickness; the field turns red above 60 mm",
        update=_chapas._upd_espessura)
    O.chapa_auto = BoolProperty(
        name="Auto-regenerate", default=True,
        description="Obsolete: the panel always preserves its modeled mesh")
    O.conj_largura_mm = FloatProperty(
        name="Width (mm)", default=600.0, min=20.0, update=_modulos._upd_conj_dim)
    O.conj_altura_mm = FloatProperty(
        name="Height (mm)", default=400.0, min=20.0, update=_modulos._upd_conj_dim)
    O.conj_profundidade_mm = FloatProperty(
        name="Depth (mm)", default=300.0, min=20.0, update=_modulos._upd_conj_dim)
    O.conj_espessura_mm = FloatProperty(
        name="Thickness (mm)", default=18.0, min=1.0,
        description="Thickness of all panels in the cabinet",
        update=_modulos._upd_conj_espessura)
    O.chapa_modo = EnumProperty(
        name="Mode", default='INDIVIDUAL',
        items=[('INDIVIDUAL', "Individual", "Dimensions of this panel"),
               ('GRUPO', "Group", "Dimensions of the entire cabinet")])
    _registrar_medida_ui(
        O, "ui_chapa_largura", "chapa_largura_mm", "Width", 1.0)
    _registrar_medida_ui(
        O, "ui_chapa_comprimento", "chapa_comprimento_mm", "Length", 1.0)
    _registrar_medida_ui(
        O, "ui_chapa_espessura", "chapa_espessura_mm", "Thickness", 1.0)
    _registrar_medida_ui(
        O, "ui_conj_largura", "conj_largura_mm", "Width", 20.0)
    _registrar_medida_ui(
        O, "ui_conj_altura", "conj_altura_mm", "Height", 20.0)
    _registrar_medida_ui(
        O, "ui_conj_profundidade", "conj_profundidade_mm", "Depth", 20.0)
    _registrar_medida_ui(
        O, "ui_conj_espessura", "conj_espessura_mm", "Thickness", 1.0)

    S = bpy.types.Scene
    S.cabinet_aba = EnumProperty(
        name="Tab", default='MODULOS',
        items=[('MODULOS', "Modules", "Dimensions, assembly and library"),
               ('PORTAS', "Doors", "Door creation and configuration"),
               ('FUNDOS', "Back Panels", "Back panels and links to internal components"),
               ('GAVETAS', "Drawers", "Drawer creation and configuration"),
               ('PRATELEIRAS', "Shelves", "Internal shelves: quantity, thickness and gaps"),
               ('DIVISORIAS', "Partitions", "Vertical partitions that divide internal systems into sections"),
               ('PUXADORES', "Handles", "Handles attached to doors"),
               ('ALVENARIA', "Masonry", "Walls, floor, ceiling and installations")])
    # Model created by the placement tool; default = PERFIL (user request).
    S.cabinet_puxador_modelo = EnumProperty(
        name="Model", default='PERFIL',
        items=[(k, v[0], "") for k, v in _puxadores.MODELOS_PUXADOR.items()])
    # The user's model .blend when the model choice is 'MODELO'.
    S.cabinet_puxador_arquivo = StringProperty(default="")
    S.chapa_bib_aberta = BoolProperty(name="Library", default=False)
    S.chapa_n1 = StringProperty(default="")
    S.chapa_n2 = StringProperty(default="")
    S.chapa_n3 = StringProperty(default="")
    # Cascade levels BEYOND the third (the library has no depth limit), separated by /.
    S.chapa_n_mais = StringProperty(default="")
    # The library shows presets (Cabinets) or Materials, each with its own cascade
    # (buttons beside the title).
    S.cabinet_bib_modo = EnumProperty(
        name="Library", default='MODULOS',
        items=[('MODULOS', "Modules", "Cabinet and part presets"),
               ('MATERIAIS', "Materials", "MDF and MDP colors")])
    S.cabinet_mat_n1 = StringProperty(default="")
    S.cabinet_mat_n2 = StringProperty(default="")
    S.cabinet_mat_n3 = StringProperty(default="")
    # Continuous volume-style bar instead of the three S/M/L steps. Seven steps: eleven
    # used 70% of the sidebar and did not fit in the corner. The largest thumbnail
    # remains large enough.
    S.chapa_tam_bloco = IntProperty(
        name="Size", default=5, min=2, max=8,
        description="Thumbnail size in the grid")
    # Side length (px) of EVERY sidebar image: handle, opening, hinge. All use the same
    # square; the slider beside the title changes it.
    S.cabinet_tam_retrato = IntProperty(
        name="Preview size", default=64,
        min=_gaveta.LARGURA_RETRATO_MIN, max=_gaveta.LARGURA_RETRATO_MAX)
    S.grupo_largura_mm = FloatProperty(name="Width (mm)", default=600.0, min=20.0, update=_modulos._upd_grupo_dim)
    S.grupo_altura_mm = FloatProperty(name="Height (mm)", default=400.0, min=20.0, update=_modulos._upd_grupo_dim)
    S.grupo_profundidade_mm = FloatProperty(name="Depth (mm)", default=300.0, min=20.0, update=_modulos._upd_grupo_dim)
    S.grupo_espessura_mm = FloatProperty(name="Thickness (mm)", default=18.0, min=1.0, update=_modulos._upd_grupo_espessura)
    _registrar_medida_ui(
        S, "ui_grupo_largura", "grupo_largura_mm", "Width", 20.0)
    _registrar_medida_ui(
        S, "ui_grupo_altura", "grupo_altura_mm", "Height", 20.0)
    _registrar_medida_ui(
        S, "ui_grupo_profundidade", "grupo_profundidade_mm", "Depth", 20.0)
    _registrar_medida_ui(
        S, "ui_grupo_espessura", "grupo_espessura_mm", "Thickness", 1.0)

    _garantir_unidade_padrao_mm()
    bpy.types.VIEW3D_MT_object_context_menu.append(_portas.menu_contexto_porta)
    bpy.types.VIEW3D_MT_object_context_menu.append(_paredes_edicao.menu_contexto)
    bpy.types.VIEW3D_MT_edit_mesh_context_menu.append(_paredes_edicao.menu_contexto)

    if _chapas.ao_atualizar_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_chapas.ao_atualizar_depsgraph)
    if _paredes_composicao.invalidar_interiores not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_paredes_composicao.invalidar_interiores)
    if _paredes_composicao.acompanhar_arraste not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_paredes_composicao.acompanhar_arraste)
    for evento, funcao in _eventos.HANDLERS_CONTORNO + _eventos.HANDLERS_REFERENCIAS + _visibilidade.HANDLERS:
        lista = getattr(bpy.app.handlers, evento)
        if funcao not in lista:
            lista.append(funcao)
    _solda._normalizar_pendente[0] = True
    if not bpy.app.timers.is_registered(_eventos.verificar_periodicamente):
        bpy.app.timers.register(_eventos.verificar_periodicamente, persistent=True)
    # bpy.ops cannot run inside register(): defer by one tick.
    bpy.app.timers.register(_registrar_bibliotecas_adiado, first_interval=0.5)
    bpy.app.timers.register(_preparar_frentes_adiado, first_interval=0.0)


def _preparar_frentes_adiado():
    _frentes.preparar_cena()
    return None


def _registrar_bibliotecas_adiado():
    # Use a NAMED function rather than a lambda so unregister can remove it.
    _biblioteca.registrar_bibliotecas()
    return None


def unregister():
    if _ambientes._handler[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_ambientes._handler[0],'WINDOW')
        _ambientes._handler[0]=None
    _ambientes.esquecer()
    _alvenaria.esquecer()
    _instalacoes.esquecer()
    _gaveta_desenho._apresentacao_medida.cache_clear()
    _visibilidade.suspender()
    _areas_criacao.esquecer()
    _paredes_edicao.encerrar()
    _paredes_composicao.esquecer()
    _paredes_edicao._ultima_face[0] = None
    _paredes_edicao._alvo_contexto[0] = None
    _paredes_edicao._aviso[0] = ''
    _paredes_edicao._sequencia[0] = 0
    _paredes_selecao.limpar_exibicoes(forcar=True)
    _paredes_selecao._limpeza_pendente[0] = False
    bpy.types.VIEW3D_MT_object_context_menu.remove(_paredes_edicao.menu_contexto)
    bpy.types.VIEW3D_MT_edit_mesh_context_menu.remove(_paredes_edicao.menu_contexto)
    _solda.encerrar_conexao_nativa()
    bpy.types.VIEW3D_MT_object_context_menu.remove(_portas.menu_contexto_porta)
    _solda._tecla_corrente_segurada[0] = False
    _solda._conexao_pendente[0] = None
    _solda._conexao_manual[0] = None
    _solda._cache_ancoras[0].clear()
    _solda._desagregar_pendente[0] = None
    _solda._pergunta_reset[0] = ''
    _perguntas._pergunta_atual[0] = None
    _perguntas._na_gaveta[0] = False
    _solda._terminar_ancora_solda()     # Cursor, hide_select, drawing and timer.
    # Restore cursor/hide_select and remove the timer for an active drag.
    _portas_viewport._terminar_canto_nativo()
    _ferragens._arraste_ferragem[0] = None
    _ferragens._ferragens_selecionadas[0] = None
    _ferragens._dobradica_reta[0] = None
    _puxadores._puxador_perfil[0] = None
    _puxadores._puxador_borda[0] = None
    _puxadores._arraste_puxador[0] = None
    _puxadores._usando_como_puxador[0] = None
    _arame._arame_rig[0] = None
    _arame._arame_perfil[0] = None
    _arame._arame_borda[0] = None
    _arame._arame_parafuso[0] = None
    _puxadores._corte_perfil[0] = None
    _arame._lotes_arame.clear()
    _arame._contornos_ferragem.clear()
    _portas_viewport._arraste_slider_porta[0] = None
    _portas_viewport._slider_hover[0] = None
    _solda._nome_grupo_gaveta[0] = None
    _solda._normalizar_pendente[0] = False
    _orcamento._orcamento_gerado[0] = None
    _ferragens._contagem_objetos[0] = None
    _ferragens._perfis_trilho_moldura[0] = None
    _solda._bolinha_hover[0] = None
    for timer in (_registrar_bibliotecas_adiado,
                  _hud._animar_piscada, _ferragens._conferir_ferragens,
                  _chapas._separar_copias_no_timer,
                  _orcamento._apagar_orcamento_gerado):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
    _hud_volume.terminar(bpy.context, cancelar=True)
    _hud_volume._remover_observador()
    _hud._edicao_hud[0] = None
    _hud._terminar_quina_nativa()      # Active native corner drag.
    _hud._hover_hud.clear()
    _hud._clique_chapa_hud.clear()
    _hud._clique_pendente.clear()
    _paredes.esquecer()
    _formas.esquecer()
    _gavetas.esquecer()
    _fundos.esquecer()
    _biblioteca_faixa.esquecer()
    _prateleiras.esquecer()
    _divisorias.esquecer()
    _gaveta._edicao_gaveta[0] = None
    if bpy.app.timers.is_registered(_gaveta._animar_realces):
        bpy.app.timers.unregister(_gaveta._animar_realces)
    _gaveta._realces.clear()
    if bpy.app.timers.is_registered(_gaveta._limitar_largura_gaveta):
        bpy.app.timers.unregister(_gaveta._limitar_largura_gaveta)
    _selecao.remover_keymaps()
    _editor.desregistrar()
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
    _materiais._texturas_esfera.clear()
    _materiais._cache[0] = None
    _materiais._apagar_pendente[0] = None
    _materiais._pintar_pendente[0] = None
    _materiais._clique_esfera[0] = None
    if bpy.app.timers.is_registered(_gaveta._configurar_gavetas):
        bpy.app.timers.unregister(_gaveta._configurar_gavetas)
    if bpy.app.timers.is_registered(_gaveta._reconectar_gavetas):
        bpy.app.timers.unregister(_gaveta._reconectar_gavetas)
    if hasattr(bpy.types.Scene, 'cabinet_aba'):
        del bpy.types.Scene.cabinet_aba
    for nome in ('cabinet_puxador_modelo', 'cabinet_puxador_arquivo',
                 'cabinet_tam_retrato', 'cabinet_bib_modo', 'cabinet_mat_n1',
                 'cabinet_mat_n2', 'cabinet_mat_n3', 'chapa_n_mais'):
        if hasattr(bpy.types.Scene, nome):
            delattr(bpy.types.Scene, nome)
    _puxadores._contornos_modelo.clear()
    _portas._apanhando_vao[0] = False
    _portas._assistente_porta[0] = None
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
    _frentes.encerrar()
    if bpy.app.timers.is_registered(_preparar_frentes_adiado):
        bpy.app.timers.unregister(_preparar_frentes_adiado)
    if _chapas.ao_atualizar_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_chapas.ao_atualizar_depsgraph)
    if _paredes_composicao.invalidar_interiores in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_paredes_composicao.invalidar_interiores)
    if _paredes_composicao.acompanhar_arraste in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_paredes_composicao.acompanhar_arraste)
    for evento, funcao in _eventos.HANDLERS_CONTORNO + _eventos.HANDLERS_REFERENCIAS + _visibilidade.HANDLERS:
        lista = getattr(bpy.app.handlers, evento)
        if funcao in lista:
            lista.remove(funcao)
    # Disabling the add-on during editing must not leave the viewport permanently
    # without outlines.
    _eventos.sincronizar_contornos(devolver=True)
    _eventos._contornos_desligados.clear()
    _eventos._contornos_do_usuario.clear()
    _eventos._origens_ocultas.clear()
    _eventos._origens_do_usuario.clear()
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
