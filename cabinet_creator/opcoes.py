"""Opcoes da engrenagem (preferencias do add-on) e unidade das medidas."""

import bpy, os

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_biblioteca = _eventos = None

def _pasta_addon():
    """A pasta `biblioteca/` que viaja dentro do addon."""
    return os.path.join(os.path.dirname(__file__), "biblioteca")


def _prefs():
    try:
        return bpy.context.preferences.addons[__package__].preferences
    except Exception:
        return None


# ------------------------------------------------ opcoes (engrenagem)
# (fator para mm, sufixo, casas decimais na tela)
UNIDADES_MEDIDA = {'MM': (1.0, 'mm', 1), 'CM': (10.0, 'cm', 2),
                   'M': (1000.0, 'm', 3)}
# Atalhos do seletor de cor; o resto se escolhe no quadrado + matiz.
# 'TEMA' (so' nas linhas) = cor do texto do tema, a mesma da gaveta.
CORES_ATALHO = (('BRANCO', (1.0, 1.0, 1.0)), ('CINZA', (0.55, 0.55, 0.55)),
                ('PRETO', (0.04, 0.04, 0.04)), ('CIANO', (0.2, 0.85, 1.0)),
                ('LARANJA', (1.0, 0.35, 0.05)), ('AMARELO', (1.0, 0.85, 0.1)),
                ('VERDE', (0.3, 0.9, 0.35)))
COR_REALCE_PADRAO = (1.0, 0.35, 0.05)
# (minimo, maximo, passo do arraste) dos campos de faixa da engrenagem
FAIXAS_OPCOES = {'hud_espessura_linha': (1.0, 50.0, 0.5),
                 'hud_tamanho_rotulo': (1, 50, 1)}
OPCOES_PADRAO = {'unidade_padrao': 'MM', 'hud_espessura_linha': 1.5,
                 'hud_linha_tema': True, 'hud_rgb_linha': (1.0, 1.0, 1.0),
                 'hud_rgb_realce': COR_REALCE_PADRAO, 'hud_realce_gizmo': False,
                 'hud_tamanho_rotulo': 14,
                 'ocultar_contorno_grupo': True, 'tecla_corrente': 'ALT'}
# Sem preferencias (add-on carregado por script, testes) as opcoes
# vivem aqui, para a engrenagem continuar funcionando.
_opcoes_sem_preferencias = dict(OPCOES_PADRAO)


def _opcao(nome):
    p = _prefs()
    if p is not None and hasattr(p, nome):
        valor = getattr(p, nome)
        # cor vem como bpy_prop_array, que nao compara nem se guarda
        return tuple(valor) if nome.startswith('hud_rgb_') else valor
    return _opcoes_sem_preferencias[nome]


def _definir_opcao(nome, valor):
    p = _prefs()
    if p is not None and hasattr(p, nome):
        setattr(p, nome, valor)
    else:
        _opcoes_sem_preferencias[nome] = valor
    # a HUD mora na viewport vizinha: sem isto a mudanca so' aparece
    # no proximo movimento do mouse la'
    try:
        for janela in bpy.context.window_manager.windows:
            for area in janela.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        pass
    if nome == 'ocultar_contorno_grupo':
        _eventos.sincronizar_contornos()


def _texto_medida(mm):
    """Medida em mm escrita na unidade padrao, com sufixo."""
    fator, sufixo, casas = UNIDADES_MEDIDA[_opcao('unidade_padrao')]
    return '%.*f %s' % (casas, mm / fator, sufixo)


def _numero_na_unidade(mm):
    """So' o numero, na unidade padrao -- o texto inicial ao digitar."""
    fator, _sufixo, casas = UNIDADES_MEDIDA[_opcao('unidade_padrao')]
    return '%g' % round(mm / fator, casas + 2)


class CabinetCreatorPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    pasta_biblioteca: bpy.props.StringProperty(
        name="Pasta da biblioteca",
        subtype='DIR_PATH',
        description="Vazio: usa a pasta do proprio addon (a biblioteca da "
                    "empresa). Aponte para uma pasta de rede para "
                    "compartilhar entre os computadores",
        default="")

    foto_clicavel: bpy.props.BoolProperty(
        name="Foto do preset clicavel",
        description="Liga o clique na FOTO para posicionar o modulo. Em "
                    "troca a imagem pode aparecer listrada: ela e' montada "
                    "em ladrilhos e o bpy nao deixa fixar a largura deles, "
                    "entao so' fecha em certas larguras da barra lateral. "
                    "Desligado, a foto sai perfeita e o clique fica no nome",
        default=False)

    selecao_por_grupo: bpy.props.BoolProperty(
        name="Clique seleciona o modulo inteiro",
        description="Um clique acende todas as pecas do modulo; dois "
                    "cliques isolam a chapa. Desligado, o clique volta a "
                    "ser o do Blender",
        default=True)

    # Opcoes da engrenagem da gaveta. Ficam nas preferencias porque valem
    # para todo arquivo, nao para uma cena.
    unidade_padrao: bpy.props.EnumProperty(
        name="Unidade padrao", default='MM',
        description="Unidade de um numero digitado sem unidade",
        items=[(k, v[1], "") for k, v in UNIDADES_MEDIDA.items()])
    hud_espessura_linha: bpy.props.FloatProperty(
        name="Espessura das linhas", default=1.5,
        min=FAIXAS_OPCOES['hud_espessura_linha'][0],
        max=FAIXAS_OPCOES['hud_espessura_linha'][1])
    # Cores com nome novo (eram Enum): reaproveitar o nome faria o
    # Blender ler o inteiro gravado do Enum antigo como cor.
    # COLOR_GAMMA: o valor vai direto para a tela, como as cores do tema.
    hud_linha_tema: bpy.props.BoolProperty(
        name="Linhas na cor do tema", default=True)
    hud_rgb_linha: bpy.props.FloatVectorProperty(
        name="Cor das linhas", subtype='COLOR_GAMMA', size=3,
        min=0.0, max=1.0, default=(1.0, 1.0, 1.0))
    hud_rgb_realce: bpy.props.FloatVectorProperty(
        name="Cor do realce", subtype='COLOR_GAMMA', size=3,
        min=0.0, max=1.0, default=COR_REALCE_PADRAO)
    hud_realce_gizmo: bpy.props.BoolProperty(
        name="Realce nas cores do gizmo", default=False,
        description="L vermelho (X), A azul (Z), P verde (Y), E laranja")
    hud_tamanho_rotulo: bpy.props.IntProperty(
        name="Tamanho dos rotulos", default=14,
        min=FAIXAS_OPCOES['hud_tamanho_rotulo'][0],
        max=FAIXAS_OPCOES['hud_tamanho_rotulo'][1])
    tecla_corrente: bpy.props.EnumProperty(
        name="Correntes", default='ALT',
        items=[('ALT', "Segurar Alt", ""), ('CTRL', "Segurar Ctrl", ""),
               ('SHIFT', "Segurar Shift", ""), ('SEMPRE', "Sempre", "")],
        description="Quando as correntes de adjacencia aparecem")
    ocultar_contorno_grupo: bpy.props.BoolProperty(
        name="Ocultar o contorno do Blender no modulo", default=True,
        description="Com um modulo ou porta selecionado, desliga o "
                    "contorno de selecao da viewport e devolve o estado "
                    "anterior ao terminar")

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "selecao_por_grupo")
        layout.prop(self, "foto_clicavel")
        for nome in OPCOES_PADRAO:
            layout.prop(self, nome)
        layout.separator()
        layout.prop(self, "pasta_biblioteca")
        layout.label(text="Em uso: " + _biblioteca.pasta_biblioteca(),
                     icon='ASSET_MANAGER')
        layout.operator("object.cabinet_registrar_bibliotecas", icon='FILE_REFRESH')
        layout.operator("object.cabinet_refiliar", icon='ASSET_MANAGER')
        layout.operator("object.cabinet_regerar_previews", icon='IMAGE_DATA')
