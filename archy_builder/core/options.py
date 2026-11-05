"""Gear-menu options (add-on preferences) and measurement units."""

import bpy, os

# Used only at runtime (circular imports): __init__ binds these
# aliases after loading all modules (`_ligar_modulos`).
_biblioteca = _eventos = None
DIRECTION_LABELS = {'CIMA':'Top', 'BAIXO':'Bottom', 'ESQUERDA':'Left',
                    'DIREITA':'Right', 'ACIMA':'Above', 'ABAIXO':'Below',
                    'FRENTE':'Front', 'TRAS':'Back'}

def _pasta_addon():
    """The `assets/library/` folder bundled with the add-on."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets/library")


def _prefs():
    try:
        return bpy.context.preferences.addons[__package__.rsplit(".", 1)[0]].preferences
    except Exception:
        return None


# ------------------------------------------------ options (gear menu)
# (mm conversion factor, suffix, display decimal places).
UNIDADES_MEDIDA = {'MM': (1.0, 'mm', 1), 'CM': (10.0, 'cm', 2),
                   'M': (1000.0, 'm', 3)}
# Color-picker shortcuts; choose other colors in the square/hue controls.
# 'TEMA', for lines only, uses theme text color, matching the sidebar.
CORES_ATALHO = (('BRANCO', (1.0, 1.0, 1.0)), ('CINZA', (0.55, 0.55, 0.55)),
                ('PRETO', (0.04, 0.04, 0.04)), ('CIANO', (0.2, 0.85, 1.0)),
                ('LARANJA', (1.0, 0.35, 0.05)), ('AMARELO', (1.0, 0.85, 0.1)),
                ('VERDE', (0.3, 0.9, 0.35)))
COR_REALCE_PADRAO = (1.0, 0.35, 0.05)
# (minimum, maximum, drag step) for gear-menu range fields.
FAIXAS_OPCOES = {'hud_espessura_linha': (1.0, 50.0, 0.5),
                 'hud_tamanho_rotulo': (1, 50, 1)}
OPCOES_PADRAO = {'unidade_padrao': 'MM', 'hud_espessura_linha': 1.5,
                 'hud_linha_tema': True, 'hud_rgb_linha': (1.0, 1.0, 1.0),
                 'hud_rgb_realce': COR_REALCE_PADRAO, 'hud_realce_gizmo': False,
                 'hud_tamanho_rotulo': 14,
                 'ocultar_contorno_grupo': True, 'ocultar_origens_grupo': True,
                 'hud_pontos_apoio': True, 'hud_setas_quinas': True,
                 'tecla_corrente': 'ALT'}
# Remember settings without gear-menu controls: library location chosen
# with Location (applies to every file, not only the screen) and
# whether it was ever chosen (`lugar_escolhido`).
OPCOES_INTERNAS = {'biblioteca_lugar': 'MENU', 'biblioteca_lugar_definido': False}
# Without preferences (script-loaded add-on/tests), keep options here
# so the gear menu still works.
_opcoes_sem_preferencias = {**OPCOES_PADRAO, **OPCOES_INTERNAS}


def _opcao(nome):
    p = _prefs()
    if p is not None and hasattr(p, nome):
        valor = getattr(p, nome)
        # Colors arrive as bpy_prop_array, unsuitable for comparison/storage.
        return tuple(valor) if nome.startswith('hud_rgb_') else valor
    return _opcoes_sem_preferencias[nome]


def _definir_opcao(nome, valor):
    p = _prefs()
    if p is not None and hasattr(p, nome):
        setattr(p, nome, valor)
    else:
        _opcoes_sem_preferencias[nome] = valor
    # HUD lives in the neighboring viewport: without this, changes appear
    # only on its next mouse movement.
    try:
        for janela in bpy.context.window_manager.windows:
            for area in janela.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        pass
    if nome in {'ocultar_contorno_grupo', 'ocultar_origens_grupo'}:
        _eventos.sincronizar_contornos()


def _numero_formatado(valor, casas=5):
    texto = format(valor, ',.%df' % casas).rstrip('0').rstrip('.')
    if texto == '-0':
        texto = '0'
    return texto.replace(',', '_').replace('.', ',').replace('_', '.')


def _texto_medida(mm, unidade=None):
    """Format a measurement in mm using the default unit and suffix."""
    unidade = unidade or _opcao('unidade_padrao')
    fator, sufixo, _casas = UNIDADES_MEDIDA[unidade]
    return '%s %s' % (_numero_formatado(mm / fator, {'MM': 2, 'CM': 3, 'M': 5}[unidade]), sufixo)


def _numero_na_unidade(mm):
    """Number only in the default unit, used as initial typed-input text."""
    fator, _sufixo, casas = UNIDADES_MEDIDA[_opcao('unidade_padrao')]
    return '%g' % round(mm / fator, casas + 2)


class ArchyBuilderPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__.rsplit(".", 1)[0]

    pasta_biblioteca: bpy.props.StringProperty(
        name="Library folder",
        subtype='DIR_PATH',
        description="Empty: uses the add-on's own folder (the company library). Choose a network folder to share between computers",
        default="")

    foto_clicavel: bpy.props.BoolProperty(
        name="Clickable preset photo",
        description="Enables clicking the PHOTO to place the cabinet. The image may appear striped: it is assembled from tiles, and bpy does not allow fixing their width, so they only align at certain sidebar widths. When disabled, the photo displays perfectly and the name is clickable",
        default=False)

    selecao_por_grupo: bpy.props.BoolProperty(
        name="Click selects the entire cabinet",
        description="One click highlights all cabinet parts; two clicks isolate the panel. When disabled, clicking uses Blender's behavior",
        default=True)

    # Sidebar gear-menu options live in preferences because they apply
    # to every file rather than one scene.
    unidade_padrao: bpy.props.EnumProperty(
        name="Default unit", default='MM',
        description="Unit for a number entered without a unit",
        items=[(k, v[1], "") for k, v in UNIDADES_MEDIDA.items()])
    hud_espessura_linha: bpy.props.FloatProperty(
        name="Line thickness", default=1.5,
        min=FAIXAS_OPCOES['hud_espessura_linha'][0],
        max=FAIXAS_OPCOES['hud_espessura_linha'][1])
    # Colors use new names, formerly Enum properties: reusing names would
    # make Blender read saved enum integers as colors.
    # COLOR_GAMMA passes values directly to display, like theme colors.
    hud_linha_tema: bpy.props.BoolProperty(
        name="Use theme color for lines", default=True)
    hud_rgb_linha: bpy.props.FloatVectorProperty(
        name="Line color", subtype='COLOR_GAMMA', size=3,
        min=0.0, max=1.0, default=(1.0, 1.0, 1.0))
    hud_rgb_realce: bpy.props.FloatVectorProperty(
        name="Highlight color", subtype='COLOR_GAMMA', size=3,
        min=0.0, max=1.0, default=COR_REALCE_PADRAO)
    hud_realce_gizmo: bpy.props.BoolProperty(
        name="Use gizmo colors for highlights", default=False,
        description="L red (X), A blue (Z), P green (Y), E orange")
    hud_tamanho_rotulo: bpy.props.IntProperty(
        name="Label size", default=14,
        min=FAIXAS_OPCOES['hud_tamanho_rotulo'][0],
        max=FAIXAS_OPCOES['hud_tamanho_rotulo'][1])
    tecla_corrente: bpy.props.EnumProperty(
        name="Links", default='ALT',
        items=[('ALT', "Hold Alt", ""), ('CTRL', "Hold Ctrl", ""),
               ('SHIFT', "Hold Shift", ""), ('SEMPRE', "Always", "")],
        description="When adjacency links appear")
    ocultar_contorno_grupo: bpy.props.BoolProperty(
        name="Hide Blender's outline on the cabinet", default=True,
        description="When a cabinet or door is selected, disables the viewport selection outline and restores the previous state when finished")
    ocultar_origens_grupo: bpy.props.BoolProperty(
        name="Hide origins in group", default=True,
        description="Hides native origin points when selecting a group; restores the previous setting when selecting a part or leaving the group")
    hud_pontos_apoio: bpy.props.BoolProperty(
        name="Support dots", default=True,
        description="Shows circular controls at the centers of the volume faces")
    hud_setas_quinas: bpy.props.BoolProperty(
        name="Corner guides", default=True,
        description="Shows the resize direction when hovering over dimensions")
    biblioteca_lugar: bpy.props.EnumProperty(
        name="Library location", default='MENU',
        items=[('FAIXA', "Top strip", "Above the menu and scene"),
               ('MENU', "Inside the sidebar", "Below the sidebar divider")],
        description="Where the library opens in any file. The Library location button changes and saves this setting")
    biblioteca_lugar_definido: bpy.props.BoolProperty(
        default=False, options={'HIDDEN'},
        description="The location has already been chosen using the button (previously it was stored only in the file)")

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "selecao_por_grupo")
        layout.prop(self, "foto_clicavel")
        for nome in OPCOES_PADRAO:
            layout.prop(self, nome)
        layout.prop(self, "biblioteca_lugar")
        layout.separator()
        layout.prop(self, "pasta_biblioteca")
        layout.label(text="In use: " + _biblioteca.pasta_biblioteca(),
                     icon='ASSET_MANAGER')
        layout.operator("object.cabinet_registrar_bibliotecas", icon='FILE_REFRESH')
        layout.operator("object.cabinet_refiliar", icon='ASSET_MANAGER')
        layout.operator("object.cabinet_regerar_previews", icon='IMAGE_DATA')
