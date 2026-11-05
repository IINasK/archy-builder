"""Sidebar: widget drawing (POST_PIXEL callback), field hover gizmo and dimension input
box (keys, cursor and text parsing in meters), also used by the HUD."""

import bpy, colorsys, math, re, gpu, blf
from functools import lru_cache
from contextlib import redirect_stderr
from io import StringIO
_visibilidade = None
from gpu_extras.batch import batch_for_shader
from bpy.types import Gizmo

# Used only at RUNTIME (circular imports): __init__ binds these aliases after loading
# all modules (`_ligar_modulos`).
_chapas = None
_opcoes = None
_gaveta_eventos = None
_gaveta = None
_orcamento = None
_hud = None
_solda = None
_portas = None
_materiais = None
_biblioteca_faixa = None
_instalacoes = None

def _eh_campo_contador(acao):
    """Labeled counter (seventh field): the door's Leaves control, drawn like a
    dimension field (drag changes, click types) instead of the hardware '< 2 >'
    control that increments/decrements according to the clicked half."""
    return bool(acao and acao[0] == 'contador' and len(acao) > 6)


def _chave_widget(acao):
    """Stable widget identity used to store its highlight.

    Return None for items that are NOT buttons (decoration, labels, slider track):
    these do not glow."""
    if not acao:
        return None
    if _biblioteca_faixa.caixa_categoria(acao):
        return 'categoria:' + acao[2]
    verbo = acao[0]
    if verbo in {'wireframe', 'separador', 'slider', 'fundo', 'pergunta', 'rotulo'}:
        return None
    if verbo == 'resposta':
        return 'resp:%d' % acao[1]
    if verbo in {'suspenso', 'faixa'}:
        return '%s:%s' % (verbo, acao[1])
    if verbo == 'rolagem':
        return 'rolagem:' + acao[1]
    if verbo == 'cor':
        # The color square and hue strip are drag surfaces, not buttons.
        if acao[2] == 'amostra':
            return 'cor:' + acao[1]
        return 'cor:%s:%s' % (acao[1], acao[5]) if acao[2] == 'atalho' else None
    if verbo in _gaveta.BOTOES_CRIAR and len(acao) > 4 and acao[4]:
        return None             # Disabled buttons do not glow.
    if verbo == 'cadeado':
        return 'cad:%d' % acao[2]
    if verbo == 'medida':
        # Property + name: door Thickness and frame Thickness are distinct fields.
        return 'medida:%s:%s' % (acao[2], acao[3])
    if verbo == 'modo':
        return None             # Indicator only: mode comes from selection.
    if verbo == 'divisa':
        return 'divisa' if acao[1] else None    # Covered by options.
    if verbo == 'aba':
        return '%s:%s' % (verbo, acao[1])
    if verbo == 'escolha':
        return 'esc:%s:%s' % (acao[1], acao[2])
    if verbo == 'operador':
        # Disabled text buttons (invalid selection) do not glow.
        return None if _gaveta_eventos._operador_apagado(acao) else 'op:' + acao[1]
    if verbo == 'navegar':
        return 'nav:%s:%s' % (acao[1], acao[2])
    if verbo == 'nivel':
        return 'niv:%s:%s' % (acao[1], acao[2])
    if verbo == 'contador':
        return 'cont:%s' % acao[1]
    if verbo == 'rolar_nivel':
        return 'rol:%s:%s' % (acao[1], acao[2])
    if verbo == 'preset':
        return 'preset:%s' % acao[1]['arquivo']
    if verbo == 'biblioteca':
        return 'bib:%s' % acao[1]
    if verbo == 'material':
        return 'mat:%s' % acao[1]['chave']
    if verbo == 'material_item':
        return 'matitem:%s:%s' % (acao[1]['chave'], acao[2])
    return verbo


class VIEW3D_GT_campo_gaveta(Gizmo):
    """Invisible hit-test over ONE sidebar widget rectangle.

    Exists only to obtain `is_highlight`: the GPU-drawn sidebar receives no mouse
    events, and a persistent modal operator would steal events from other add-ons.
    Clicking invokes the same operator the keymap already uses for the entire area,
    preserving click behavior.

    When a widget has an icon, exclude the `GIZMO_GT_button_2d` disc from this
    hit-test so the icon gizmo still wins picking there and retains its tooltip. The
    glow covers both by combining their `is_highlight` states."""
    bl_idname = 'VIEW3D_GT_campo_gaveta'

    def draw(self, context):
        pass

    def test_select(self, context, location):
        alvo = _hud._campos_gaveta.get(self.as_pointer())
        if not alvo:
            return -1
        x, y, w, h, icone = alvo[:5]
        px, py = location
        if not (x <= px <= x + w and y <= py <= y + h):
            return -1
        if len(alvo) > 5 and any(bx <= px <= bx + bw and by <= py <= by + bh
                                 for bx, by, bw, bh in alvo[5]):
            return -1
        if icone is not None:
            cx, cy, raio = icone
            if (px - cx) ** 2 + (py - cy) ** 2 <= raio * raio:
                return -1
        return 0


def _degrade_gaveta(vertices, cores):
    """Triangles with per-vertex color (color square and hue strip)."""
    shader = gpu.shader.from_builtin('SMOOTH_COLOR')
    batch_for_shader(shader, 'TRIS', {'pos': vertices,
                                      'color': cores}).draw(shader)


def _seta_suspensa_gaveta(x, y, w, h, aberta, cor):
    cx, cy = x + w - 12, y + h / 2
    pontos = (((cx - 4, cy - 2), (cx + 4, cy - 2), (cx, cy + 3)) if aberta
              else ((cx - 4, cy + 2), (cx + 4, cy + 2), (cx, cy - 3)))
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float('color', (*cor, 1))
    batch_for_shader(shader, 'TRIS', {'pos': pontos}).draw(shader)


def _anel_gaveta(cx, cy, raio, miolo):
    """Picker marker: black and white rings around the chosen color, visible anywhere
    on the square."""
    for r, cor in ((raio + 1.5, (0, 0, 0, 1)), (raio, (1, 1, 1, 1)),
                   (raio - 2, (*miolo, 1))):
        _gaveta._retangulo_arredondado_gaveta(cx - r, cy - r, 2 * r, 2 * r, r, cor)


def _listras_gizmo_gaveta(x, y, w, h):
    """Gizmo highlight sample: X, Y, Z and thickness, side by side."""
    tons = [_hud._cor_eixo_gizmo(e) for e in ('axis_x', 'axis_y', 'axis_z')]
    tons.append(_opcoes.COR_REALCE_PADRAO)
    for i, tom in enumerate(tons):
        _gaveta._retangulo_gaveta(x + w * i / 4, y, w / 4, h, (*tom, 1))


def _desenhar_opcao_gaveta(context, x, y, w, h, rotulo, acao, cores, fundo):
    """Options panel controls: dropdown, strip and color."""
    texto_cor = tuple(cores.text[:3])
    verbo = acao[0]
    if verbo == 'fundo':
        _gaveta._retangulo_arredondado_gaveta(x - 1, y - 1, w + 2, h + 2, 6,
                                      (*cores.outline[:3], 1))
        _gaveta._retangulo_arredondado_gaveta(x, y, w, h, 5, fundo)
        return
    if verbo == 'suspenso':
        _gaveta._botao_gaveta(x, y, w, h, ativo=acao[2])
        _gaveta._texto_cabivel_gaveta(x + 9, y + (h - 12) / 2, rotulo, w - 30)
        _seta_suspensa_gaveta(x, y, w, h, acao[2], texto_cor)
        return
    if verbo == 'faixa':
        _gaveta._botao_gaveta(x, y, w, h)
        minimo, maximo = acao[3], acao[4]
        fracao = max(0.0, min(1.0, (acao[2] - minimo) / (maximo - minimo)))
        if fracao > 0:
            _gaveta._retangulo_arredondado_gaveta(
                x + 1, y + 1, max(6, (w - 2) * fracao), h - 2, 3,
                (*cores.inner_sel[:3], 1))
        edicao = _gaveta._edicao_gaveta[0]
        editando = (edicao is not None and edicao['propriedade'] == acao[1]
                    and edicao['area'] == context.area.as_pointer())
        if editando:
            texto, cursor = edicao['texto'], edicao['cursor']
            rotulo = _com_cursor(texto,cursor,medida=edicao.get('medida',False))
        blf.size(0, 12)
        largura = min(blf.dimensions(0, rotulo)[0], w - 12)
        if editando:
            _texto_editavel_gaveta(x + (w - largura) / 2, y + (h - 12) / 2, edicao, w - 12)
        else:
            _gaveta._texto_cabivel_gaveta(x + (w - largura) / 2, y + (h - 12) / 2, rotulo, w - 12)
        return
    parte = acao[2]
    if parte == 'amostra':
        _gaveta._botao_gaveta(x, y, w, h, ativo=acao[4])
        lado = min(34, w * 0.35)
        _gaveta._retangulo_gaveta(x + 4, y + 4, lado, h - 8, (*cores.outline[:3], 1))
        if acao[5] == 'GIZMO':
            _listras_gizmo_gaveta(x + 5, y + 5, lado - 2, h - 10)
        else:
            _gaveta._retangulo_gaveta(x + 5, y + 5, lado - 2, h - 10, (*acao[3], 1))
        _gaveta._texto_cabivel_gaveta(x + lado + 10, y + (h - 12) / 2, rotulo,
                              w - lado - 32, 11)
        _seta_suspensa_gaveta(x, y, w, h, acao[4], texto_cor)
    elif parte == 'atalho':
        borda = texto_cor if acao[4] else tuple(cores.outline[:3])
        espessura = 2 if acao[4] else 1
        _gaveta._retangulo_gaveta(x, y, w, h, (*borda, 1))
        if acao[5] == 'GIZMO':
            _listras_gizmo_gaveta(x + espessura, y + espessura,
                                  w - 2 * espessura, h - 2 * espessura)
        else:
            _gaveta._retangulo_gaveta(x + espessura, y + espessura, w - 2 * espessura,
                              h - 2 * espessura, (*acao[3], 1))
        if rotulo:
            claro = sum(acao[3]) / 3 > 0.5
            blf.size(0, 10)
            lw, lh = blf.dimensions(0, rotulo)
            _gaveta._texto_gaveta(x + (w - lw) / 2, y + (h - lh) / 2, rotulo, 10,
                          (0, 0, 0, 1) if claro else (1, 1, 1, 1))
    elif parte == 'quadro':
        h_, s, v = _gaveta._hsv_opcao(acao[1], acao[3])
        puro = colorsys.hsv_to_rgb(h_, 1.0, 1.0)
        # Interpolating the four corners (black below, white and pure hue above) gives
        # exactly V * mix(white, hue, S).
        a, b, c, d = (x, y), (x + w, y), (x + w, y + h), (x, y + h)
        preto, branco = (0, 0, 0, 1), (1, 1, 1, 1)
        _degrade_gaveta((a, b, c, a, c, d),
                        (preto, preto, (*puro, 1), preto, (*puro, 1), branco))
        _anel_gaveta(x + s * w, y + v * h, 6, acao[3])
    elif parte == 'matiz':
        vertices, tons = [], []
        for i in range(6):
            x0, x1 = x + w * i / 6, x + w * (i + 1) / 6
            c0 = (*colorsys.hsv_to_rgb(i / 6, 1, 1), 1)
            c1 = (*colorsys.hsv_to_rgb((i + 1) / 6, 1, 1), 1)
            vertices += [(x0, y), (x1, y), (x1, y + h),
                         (x0, y), (x1, y + h), (x0, y + h)]
            tons += [c0, c1, c1, c0, c1, c0]
        _degrade_gaveta(vertices, tons)
        h_ = _gaveta._hsv_opcao(acao[1], acao[3])[0]
        mx = x + h_ * w
        _gaveta._retangulo_gaveta(mx - 2.5, y - 2, 5, h + 4, (0, 0, 0, 1))
        _gaveta._retangulo_gaveta(mx - 1.5, y - 1, 3, h + 2, (1, 1, 1, 1))
    gpu.state.blend_set('ALPHA')


def _medida_em_alerta(acao):
    """Dimension field drawn red: thickness beyond the conventional limit
    (`_chapas.ESPESSURA_ALERTA_MM`)."""
    try:
        return (acao[0] == 'medida' and (acao[3] == "Thickness" or acao[1]=='cota' and acao[3]=='E')
                and _chapas._espessura_em_alerta(acao[4]))
    except (IndexError, TypeError, ValueError):
        return False


def _cor_alerta_gaveta():
    """THEME red (literal colors are forbidden, DESIGN.md sec. 5): Info editor error
    color, lightened for readability on a dark background."""
    tema = bpy.context.preferences.themes[0]
    for area, nome in (('info', 'info_error'), ('user_interface', 'axis_x')):
        try:
            cor = list(getattr(getattr(tema, area), nome))[:3]
        except Exception:
            continue
        topo = max(cor)
        if topo > 0:
            cor = [c * 0.95 / topo for c in cor] if topo < 0.95 else cor
            return (*cor, 1.0)
    return (*_gaveta._cores_gaveta()[0].text[:3], 1.0)


def _intersecao_retangulos(a, b):
    """Intersection (x, y, w, h) of two rectangles; width/height >= 0."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1 = min(a[0] + a[2], b[0] + b[2])
    y1 = min(a[1] + a[3], b[1] + b[3])
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0)


def _desenhar_divisa_gaveta(context, largura, meio, acao, cores):
    """Line between the tab and library. Hover gives it the same halo as buttons and a
    central grip for dragging."""
    realce = _gaveta._valor_realce(context, _chave_widget(acao)) if acao[1] else 0.0
    gpu.state.blend_set('ALPHA')
    if realce > 0.01:
        _gaveta._glow_gaveta(0, meio - 1, largura, 2, 1, realce, cores.text)
    cor = tuple(c + (t - c) * realce for c, t in
                zip(cores.outline[:3], cores.text[:3]))
    _gaveta._retangulo_gaveta(0, meio - 1 if realce > 0.5 else meio, largura,
                      2 if realce > 0.5 else 1, (*cor, 1))
    # Grip: three short central lines, like Blender's area divider.
    for i in (-1, 0, 1):
        _gaveta._retangulo_gaveta(largura / 2 - 9, meio + i * 3 - 0.5, 18, 1,
                          (*cor, 0.55 + 0.45 * realce))


def _segmentos_igualar_vaos(x, y, w, h):
    """User-requested symbol: two outward arrows and a central bar. Button-local
    coordinates shared with the visual audit."""
    cx, cy, lado = x + w / 2, y + h / 2, min(w, h)
    segmentos = [(0, -.28), (0, .28)]
    for sinal in (-1, 1):
        segmentos.extend(((sinal * .12, 0), (sinal * .36, 0),
                          (sinal * .24, -.12), (sinal * .36, 0),
                          (sinal * .24, .12), (sinal * .36, 0)))
    return [(cx + px * lado, cy + py * lado) for px, py in segmentos]


def _desenhar_igualar_vaos(x, y, w, h, cor):
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float('viewportSize', gpu.state.viewport_get()[2:])
    shader.uniform_float('lineWidth', max(1.5, min(w, h) / 18.5))
    shader.uniform_float('color', cor)
    batch_for_shader(shader, 'LINES', {'pos': _segmentos_igualar_vaos(x, y, w, h)}).draw(shader)


def _cor_contorno_categorias(cores):
    """Theme gray: navigation does not inherit the blue selection color."""
    tom = sum(.7 * t + .3 * b for t, b in zip(cores.text[:3], cores.outline[:3])) / 3
    return (tom, tom, tom, 1)


def _desenhar_gaveta(tela=False):
    context = bpy.context
    if context.region is None or context.region.type != 'WINDOW':
        return
    if not _gaveta._eh_area_gaveta(context):
        if (context.area is not None and context.area.type == 'VIEW_3D'
                and (_gaveta._area_gaveta(context.screen) is None
                     or context.area.x > _gaveta._area_gaveta(context.screen).x)):
            centro = max(48, context.region.height * 0.12)
            realce = _gaveta._valor_realce(context, 'alca')
            cores, _ = _gaveta._cores_gaveta()
            gpu.state.blend_set('ALPHA')
            # Glow grows only to the right: the handle touches the edge.
            _gaveta._glow_gaveta(0, centro - 35, 26, 70, 5, realce, cores.text,
                         esquerda_reta=True)
            _gaveta._retangulo_arredondado_gaveta(
                0, centro - 35, 26, 70, 5,
                (*(c + (t - c) * realce * 0.45
                   for c, t in zip(cores.outline[:3], cores.text)), 1),
                esquerda_reta=True)
            _gaveta._retangulo_arredondado_gaveta(
                0, centro - 34, 25, 68, 4,
                (*(c + (t - c) * realce * 0.22
                   for c, t in zip(cores.inner[:3], cores.text)), 1),
                esquerda_reta=True)
            aberta = _gaveta._area_gaveta(context.screen) is not None
            seta = (((9, centro), (16, centro - 7),
                     (16, centro + 7)) if aberta else
                    ((16, centro), (9, centro - 7),
                     (9, centro + 7)))
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            batch = batch_for_shader(shader, 'TRIS', {'pos': seta})
            shader.bind()
            shader.uniform_float('color', (*cores.text, 1))
            batch.draw(shader)
            gpu.state.blend_set('NONE')
        return
    # Draw the sidebar surface before GIZMO_GT_button_2d. A POST_PIXEL background drawn
    # on top covers native icons.
    if not tela:
        return
    largura, altura = context.region.width, context.region.height
    cores, fundo = _gaveta._cores_gaveta()
    gpu.state.blend_set('ALPHA')
    _gaveta._retangulo_gaveta(0, 0, largura, altura, fundo)
    _gaveta._retangulo_gaveta(largura - 2, 0, 2, altura, (0.27, 0.27, 0.27, 1))
    widgets = _gaveta._widgets_gaveta(context, largura, altura)
    # Draw the header last, above scrollable content.
    cabecalho, conteudo, rodape = _gaveta._partes_gaveta(widgets)
    faixa_biblioteca = _biblioteca_faixa.eh_faixa(context)
    escala_faixa = max(1.0, context.preferences.system.ui_scale) if faixa_biblioteca else 1.0
    if faixa_biblioteca:
        cabecalho, conteudo, rodape = [], widgets, []
    # The footer strip (and options-panel background) goes BETWEEN content and footer
    # buttons: content scrolls beneath it.
    faixa = (0, 0, 0, 0, '', ('faixa_rodape',))
    # Clip each panel to its own rectangle: tab content scrolls beneath the header and
    # divider; library content scrolls beneath the divider and fixed footer.
    cima, divisa, baixo = _gaveta._paineis_gaveta(conteudo)
    meio = round(divisa[1] + divisa[3] / 2) if divisa else _gaveta.ALTURA_RODAPE_GAVETA
    piso_cima = meio + _visibilidade.altura(context) + 1
    recorte_cima = (0, piso_cima, largura, max(0, altura - 48 - piso_cima))
    recorte_baixo = (0, _gaveta.ALTURA_RODAPE_GAVETA, largura,
                     max(0, meio - _gaveta.ALTURA_RODAPE_GAVETA))
    recortes = ([recorte_cima] * len(cima) + [None] * bool(divisa)
                + [recorte_baixo] * len(baixo))
    if faixa_biblioteca:
        recortes = [(0, 0, largura, altura)] * len(conteudo)
    for indice, (x, y, w, h, rotulo, acao) in enumerate(
            conteudo + ([] if faixa_biblioteca else [faixa]) + rodape + cabecalho):
        painel = recortes[indice] if indice < len(recortes) else None
        if faixa_biblioteca and acao and acao[0] in ('pergunta', 'resposta'):
            escala = max(1.0, context.preferences.system.ui_scale)
            painel = (0, 4 * escala, largura, max(0, altura - 44 * escala))
        if painel is not None:
            gpu.state.scissor_test_set(True)
            gpu.state.scissor_set(*(int(round(c)) for c in painel))
        else:
            gpu.state.scissor_test_set(False)
        if acao and acao[0] == 'divisa':
            _desenhar_divisa_gaveta(context, largura, meio, acao, cores)
            continue
        if acao and acao[0] == 'rolagem':
            base, tamanho = _gaveta._alca_rolagem(y, h, acao[2], acao[3])
            _gaveta._retangulo_arredondado_gaveta(x, y, w, h, 4, tuple(cores.inner))
            realce = _gaveta._valor_realce(context, _chave_widget(acao))
            _gaveta._retangulo_arredondado_gaveta(x, base, w, tamanho, 4,
                                               (*cores.text[:3], .55 + .35 * realce))
            continue
        if acao == ('faixa_rodape',):
            _gaveta._retangulo_gaveta(0, 0, largura, _gaveta.ALTURA_RODAPE_GAVETA, fundo)
            _gaveta._retangulo_gaveta(0, _gaveta.ALTURA_RODAPE_GAVETA - 1, largura, 1,
                              (*cores.outline[:3], 1))
            painel = _gaveta._retangulo_painel_opcoes(rodape)
            if painel is not None:
                px, py, pw, ph = painel
                _gaveta._retangulo_arredondado_gaveta(px - 1, py - 1, pw + 2, ph + 2,
                                              6, (*cores.outline[:3], 1))
                _gaveta._retangulo_arredondado_gaveta(px, py, pw, ph, 5, fundo)
            continue
        if y + h < 0 or y > altura:
            continue
        if acao == ('rotulo',):
            _gaveta._texto_cabivel_gaveta(x, y + (h - 12) / 2, rotulo, w, 12)
            continue
        if acao and acao[0] == 'separador':
            cor = _cor_contorno_categorias(cores) if acao == ('separador', 'biblioteca') else (*cores.outline[:3], 1)
            _gaveta._retangulo_gaveta(x, y, w, h, cor)
            continue
        if _biblioteca_faixa.caixa_categoria(acao):
            realce = _gaveta._valor_realce(context, _chave_widget(acao))
            borda = (*_cor_contorno_categorias(cores)[:3], realce)
            tom = sum(c + (t - c) * (.18 + .45 * realce)
                      for c, t in zip(fundo[:3], cores.inner[:3])) / 3
            cor = (tom, tom, tom)
            gpu.state.blend_set('ALPHA')
            _gaveta._retangulo_arredondado_gaveta(x, y, w, h, 4 * escala_faixa, borda)
            margem = escala_faixa
            _gaveta._retangulo_arredondado_gaveta(x + margem, y + margem,
                max(0, w - 2 * margem), max(0, h - 2 * margem), 3 * escala_faixa, (*cor, 1))
            continue
        if acao and acao[0] in {'fundo', 'suspenso', 'faixa', 'cor'}:
            chave = _chave_widget(acao)
            if chave:
                _gaveta._glow_gaveta(x, y, w, h, 4, _gaveta._valor_realce(context, chave),
                             cores.text)
            _desenhar_opcao_gaveta(context, x, y, w, h, rotulo, acao,
                                   cores, fundo)
            continue
        if acao and acao[0] == 'pergunta':
            # BLACK box: emphasize that the sidebar is awaiting an answer.
            _gaveta._retangulo_arredondado_gaveta(x - 1, y - 1, w + 2, h + 2, 6,
                                          (*cores.outline[:3], 1))
            _gaveta._retangulo_arredondado_gaveta(x, y, w, h, 5, (0.0, 0.0, 0.0, 0.92))
            for i, linha in enumerate(rotulo.split('\n')):
                _gaveta._texto_gaveta(x + 10, y + h - 22 - i * 15, linha, 11,
                              (1.0, 1.0, 1.0, 1.0))
            continue
        if acao and acao[0] == 'wireframe':
            _gaveta._desenhar_wireframe_gaveta(x, y, *acao[1:], escala=w / 160.0)
            continue
        if acao and acao[:2] == ('escolha', 'modelo_instalacao'):
            _gaveta._botao_gaveta(x, y, w, h)
            it = _instalacoes.item_do_modelo(acao[2])
            gpu.state.blend_set('ALPHA')
            _gaveta._desenhar_foto_gaveta(it, x+5, y+22, w-10, h-27)
            _gaveta._texto_cabivel_gaveta(x+6, y+5, rotulo, w-12, 11)
            continue
        if acao and acao[:2] == ('slider', 'instalacao'):
            tx, ty, tw = _gaveta._trilho_slider_gaveta(acao, x, y, w, h)
            _gaveta._texto_cabivel_gaveta(x+10, y+h-10, rotulo, w-20, 10)
            _gaveta._retangulo_gaveta(tx, ty-3, tw, 2, tuple(cores.inner))
            _gaveta._retangulo_arredondado_gaveta(tx+tw*acao[4]-4, ty-6, 8, 8, 4, (*cores.text, 1))
            continue
        if acao and acao[0] == 'slider' and acao[1] == 'retratos':
            # Small slider beside the title: its title-row box, track and dot.
            _gaveta._botao_gaveta(x, y, w, h, secao=True)
            tx, ty, tw = _gaveta._trilho_slider_gaveta(acao, x, y, w, h)
            menor, maior = _gaveta.LARGURA_RETRATO_MIN, _gaveta.LARGURA_RETRATO_MAX
            valor = min(1.0, max(0.0, (getattr(context.scene, 'cabinet_tam_retrato', 64)
                                       - menor) / (maior - menor)))
            _gaveta._retangulo_gaveta(tx, ty - 1.5, tw, 3, tuple(cores.inner))
            _gaveta._retangulo_arredondado_gaveta(
                tx + tw * valor - 5, ty - 5, 10, 10, 5, (*cores.text, 1))
            continue
        if acao and acao[0] == 'slider':
            tx, ty, tw = _gaveta._trilho_miniaturas_gaveta(x, y, w, h)
            largura_rotulo = tx - x - 12
            if largura_rotulo >= 135:
                _gaveta._texto_cabivel_gaveta(x, y + 8, rotulo, largura_rotulo, 11)
            else:
                _gaveta._texto_cabivel_gaveta(x, y + 15, "Size of", largura_rotulo, 11)
                _gaveta._texto_cabivel_gaveta(x, y + 2, 'thumbnails', largura_rotulo, 11)
            valor = (context.scene.chapa_tam_bloco - 2) / 6.0
            _gaveta._retangulo_gaveta(tx, ty - 1.5, tw, 3, tuple(cores.inner))
            _gaveta._retangulo_arredondado_gaveta(
                tx + tw * valor - 6, ty - 6, 12, 12, 6, (*cores.text, 1))
            continue
        if acao and acao[0] == 'preset':
            _gaveta._botao_gaveta(x, y, w, h)
            lado = min(w - 10 * escala_faixa, h - 27 * escala_faixa)
            _gaveta._retangulo_gaveta(x + 5 * escala_faixa, y + 22 * escala_faixa, lado, lado, fundo)
            # BLF and other widgets may change blending before the image.
            gpu.state.blend_set('ALPHA')
            _gaveta._desenhar_foto_gaveta(acao[1], x + 5 * escala_faixa, y + 22 * escala_faixa, lado, lado)
            _gaveta._texto_cabivel_gaveta(x + 5 * escala_faixa, y + 5 * escala_faixa,
                                         rotulo, w - 10 * escala_faixa, round(11 * escala_faixa))
            continue
        if acao and acao[0] == 'material':
            # Preset block with a color SPHERE instead of an image; lit = selection's
            # material.
            chave = _chave_widget(acao)
            _gaveta._glow_gaveta(x, y, w, h, 4, _gaveta._valor_realce(context, chave),
                                 cores.text)
            _gaveta._botao_gaveta(x, y, w, h, ativo=acao[2])
            lado = min(w - 10 * escala_faixa, h - 27 * escala_faixa)
            _gaveta._retangulo_gaveta(x + 5 * escala_faixa, y + 22 * escala_faixa, lado, lado, fundo)
            _materiais.desenhar_esfera(acao[1]['cor'], x + 5 * escala_faixa,
                                      y + 22 * escala_faixa, lado, lado)
            _gaveta._texto_cabivel_gaveta(x + 5 * escala_faixa, y + 5 * escala_faixa,
                                         rotulo, w - 10 * escala_faixa, round(11 * escala_faixa))
            continue
        # An entering or exiting item extends into the arrow area. Clipping makes the
        # carousel look like a window through which the row passes, rather than items
        # appearing from nowhere.
        recortado = bool(acao and acao[0] == 'navegar' and not faixa_biblioteca)
        if recortado:
            # Carousel track INSIDE the panel clip.
            trilho = (12 + 24, int(y) - 1, max(0, largura - 24 - 48), 27)
            if painel is not None:
                trilho = _intersecao_retangulos(trilho, painel)
            gpu.state.scissor_test_set(True)
            gpu.state.scissor_set(*(int(round(c)) for c in trilho))

        aceitar = bool(acao and acao[0] == 'escolha'
                       and acao[1] == _portas.CONFIRMAR_ETAPA)
        ativo = bool(acao and (acao[0] in {'navegar', 'modo', 'biblioteca', 'nivel'} and acao[-1]
                               or acao[0] == 'aba' and _gaveta._aba_no_menu(context.scene) == acao[1]
                               or acao[0] == 'escolha' and acao[3]
                               or acao[0] == 'contador'
                               and not _eh_campo_contador(acao)
                               or acao[0] in _gaveta.BOTOES_CRIAR and acao[2]
                               # Compare, never hash: preset actions and library items
                               # contain a dict (v140: a set here crashed the entire
                               # sidebar).
                               or acao[0] == 'operador'
                               and acao[1] in (_solda.OP_CORRENTE_OBJETO,
                                               _solda.OP_RESETAR_DISTANCIA,
                                               _orcamento.OP_EXPORTAR_ORCAMENTO)
                               and len(acao) > 2 and acao[2]))
        # Draw the halo BEFORE the button body, as with the handle: drawing it on top
        # would wash out text instead of surrounding the widget.
        chave = _chave_widget(acao)
        if chave and not (faixa_biblioteca and acao[0] in {'navegar', 'biblioteca', 'rolar_nivel'}):
            _gaveta._glow_gaveta(x, y, w, h, 4, _gaveta._valor_realce(context, chave),
                         cores.text)
        apagado = bool(acao and acao[0] in _gaveta.BOTOES_CRIAR and len(acao) > 4
                       and acao[4]) or _gaveta_eventos._operador_apagado(acao)
        # Create Doors is ORANGE from the start (user request): the tab's starting
        # point, brighter while marking the opening.
        cor = None
        destaque = bool(acao and acao[0] == 'operador'
                        and acao[1] in _gaveta.OPERADORES_DESTAQUE)
        if acao and acao[0] in _gaveta.BOTOES_CRIAR and not apagado:
            cor = _gaveta.COR_CRIAR_PORTAS_ATIVO if acao[2] else _gaveta.COR_CRIAR_PORTAS
        elif acao and acao[:2]==('operador','object.cabinet_definir_alvenaria') and len(acao)>3 and acao[3]=='desagregar' and not apagado:
            cor = _cor_alerta_gaveta()
        elif acao and acao[0] == 'escolha' and acao[1] in {'criar_alvenaria', 'editar_alvenaria'}:
            cor = _gaveta.COR_CRIAR_PORTAS
        elif destaque and not apagado:
            cor = (_gaveta.COR_CRIAR_PORTAS_ATIVO if acao[1] == _gaveta.OPERADOR_DESTAQUE_ATIVO
                   else _gaveta.COR_CRIAR_PORTAS)
        elif aceitar:
            cor = COR_ACEITAR       # Step acceptance control (user mockup).
        if not acao or acao[0] != 'cadeado':
            _gaveta._botao_gaveta(x, y, w, h, ativo=ativo,
                          secao=acao is None or apagado, cor=cor)
        campo_contador = _eh_campo_contador(acao)
        if acao and acao[:2]==('escolha','ambiente_cor'):
            _gaveta._retangulo_arredondado_gaveta(x+3,y+3,w-6,h-6,2,(*acao[6],1))
            continue
        if acao and (acao[0] == 'medida' or campo_contador):
            edicao = _gaveta._edicao_gaveta[0]
            editando = (edicao is not None and edicao['area'] == context.area.as_pointer()
                        and edicao['propriedade'] == acao[1 if campo_contador else 2])
            if editando:
                _gaveta._botao_gaveta(x, y, w, h, ativo=True)
            # Unconventional thickness (> 60 mm): name and value in red. Warn without
            # blocking; preserve the requested value.
            alerta = (_cor_alerta_gaveta() if not campo_contador
                      and _medida_em_alerta(acao) else None)
            _gaveta._texto_cabivel_gaveta(x + 7, y + h - 14,
                                   (acao[6] if campo_contador else _hud.rotulo_medida(acao[3])), w - 14, 11,
                                   cor=alerta)
            valor = rotulo if campo_contador else _opcoes._texto_medida(acao[4])
            if editando:
                _texto_editavel_gaveta(x + 7, y + 6, edicao, w - 14, cor=alerta)
            else:
                _gaveta._texto_cabivel_gaveta(x + 7, y + 6, valor, w - 14, 12, cor=alerta)
        elif acao and (acao[0] in _gaveta.BOTOES_CRIAR or destaque):
            # Create Doors/Create Handle: wide with CENTERED text.
            blf.size(0, 12)
            largura_texto = min(blf.dimensions(0, rotulo)[0], w - 18)
            _gaveta._texto_cabivel_gaveta(
                x + (w - largura_texto) / 2, y + (h - 12) / 2, rotulo, w - 18,
                cor=(*cores.text[:3], 0.4) if apagado else (1.0, 1.0, 1.0, 1.0))
        elif acao and acao[0] == 'escolha' and acao[1] in {
                'criar_alvenaria', 'editar_alvenaria', 'tipo_alvenaria', 'tipo_instalacao'}:
            blf.size(0, 12)
            largura_texto = min(blf.dimensions(0, rotulo)[0], w-8)
            _gaveta._texto_cabivel_gaveta(x+(w-largura_texto)/2, y+(h-12)/2,
                                          rotulo, w-8, 12)
        elif acao and acao[0] == 'contador':
            # Value in the middle and arrows indicating drag or click.
            blf.size(0, 13)
            largura_texto = blf.dimensions(0, rotulo)[0]
            _gaveta._texto_gaveta(x + (w - largura_texto) / 2, y + (h - 12) / 2,
                                  rotulo, 13)
            setas = (*cores.text[:3], 0.55)
            _gaveta._texto_gaveta(x + 7, y + (h - 12) / 2, '<', 12, setas)
            _gaveta._texto_gaveta(x + w - 14, y + (h - 12) / 2, '>', 12, setas)
        elif acao and acao[0] == 'escolha' and len(acao) > 6 and acao[6]:
            # Carousel image: picture above, name centered below.
            gpu.state.blend_set('ALPHA')
            _gaveta._desenhar_foto_gaveta(acao[6], x + 4, y + 18, w - 8, h - 22)
            blf.size(0, 11)
            largura_texto = min(blf.dimensions(0, rotulo)[0], w - 8)
            _gaveta._texto_cabivel_gaveta(x + (w - largura_texto) / 2, y + 5,
                                          rotulo, w - 8, 11)
        elif acao == ('operador', 'object.cabinet_alinhar_prateleiras'):
            _desenhar_igualar_vaos(x, y, h, h,
                (*cores.text[:3], .4 if apagado else 1.0))
            _gaveta._texto_cabivel_gaveta(x + h + 4, y + (h - 12) / 2,
                rotulo, w - h - 13, cor=(*cores.text[:3], .4) if apagado else None)
        elif _gaveta_eventos._icone_ao_lado(acao):
            # Icon gizmo at the left end, followed by text.
            _gaveta._texto_cabivel_gaveta(
                x + h + 4, y + (h - 12) / 2, rotulo, w - h - 13,
                cor=(*cores.text[:3], 0.4) if apagado else None)
        elif not _gaveta_eventos._icone_acao_gaveta(acao):
            compacto = faixa_biblioteca and acao and acao[0] in ('navegar', 'biblioteca', 'operador')
            margem = (6 if compacto else 9) * escala_faixa
            fonte = round((10 if compacto else 12) * escala_faixa)
            _gaveta._texto_cabivel_gaveta(
                x + margem, y + (h - fonte) / 2,
                rotulo, w - 2 * margem, fonte,
                cor=(*cores.text[:3], 0.4) if apagado else None)
        if recortado:
            gpu.state.scissor_test_set(False)
    gpu.state.scissor_test_set(False)
    if not faixa_biblioteca:
        _gaveta._retangulo_gaveta(0, altura - 48, largura, 48, fundo)
    for x, y, w, h, rotulo, acao in cabecalho:
        _gaveta._glow_gaveta(x, y, w, h, 4,
                     _gaveta._valor_realce(context, _chave_widget(acao)), cores.text)
        if acao[0] == 'suspenso':
            _desenhar_opcao_gaveta(context, x, y, w, h, rotulo, acao, cores, fundo)
            continue
        if acao[0] != 'aba':
            continue        # Chain: icon only, drawn by the gizmo.
        _gaveta._botao_gaveta(x, y, w, h,
                       ativo=_gaveta._aba_no_menu(context.scene) == acao[1])
        _gaveta._texto_cabivel_gaveta(x + 9, y + 8, rotulo, w - 18)
    gpu.state.blend_set('NONE')


COR_ACEITAR = (0.13, 0.66, 0.30, 1.0)    # The tick is the CHECKMARK icon.


def _unidade_nos_numeros_soltos(texto, sufixo):
    """'60 + 5mm' -> '60cm + 5mm' (with cm as default).

    Blender's parser alone gives a unitless number its NEIGHBOR's unit, turning 60
    into 60 mm. The agreed rule differs: unitless numbers use the default. Only
    additive/subtractive terms receive the suffix; multiplication/division factors
    (the 2 in '2*30cm') remain plain numbers."""
    fichas = re.findall(r'\d+\.?\d*|\.\d+|[A-Za-z]+|\S', texto)
    if not any(f.isalpha() for f in fichas):
        return texto          # No units anywhere: str_ref_unit handles it.
    saida = []
    for i, ficha in enumerate(fichas):
        saida.append(ficha)
        if not (ficha[0].isdigit() or ficha[0] == '.'):
            continue
        antes = fichas[i - 1] if i > 0 else ''
        depois = fichas[i + 1] if i + 1 < len(fichas) else ''
        if depois.isalpha() or antes in {'*', '/'} or depois in {'*', '/'}:
            continue
        saida.append(sufixo)
    return ' '.join(saida)


_UNIDADE_RE = r'(?:mm|cm|m)(?![a-z])'


def _arrumar_texto_medida(texto):
    """Interpret input allowed by the freely positioned cursor as the user intends:

    - '51cm00' (unit typed INSIDE the number) -> '5100cm';
    - '500 + cm' (operator without a number before the unit) -> '500cm';
    - '500 +' (unfinished expression) -> '500'."""
    anterior = None
    while anterior != texto:
        anterior = texto
        texto = re.sub(r'(\d[\d.]*)(mm|cm|m)(\d[\d.]*)(?![a-z\d.])',
                       r'\1\3\2', texto, flags=re.I)
    texto = re.sub(r'\s*[+\-*/]\s*(?=' + _UNIDADE_RE + ')', '', texto,
                   flags=re.I)
    return re.sub(r'[\s+\-*/]+$', '', texto)


OPERADORES_MEDIDA = '+-*/'
LIMITE_TEXTO_MEDIDA = 80


def _selecao_no_texto(estado):
    cursor = min(estado.get('cursor', len(estado['texto'])), len(estado['texto']))
    if not estado.get('selecionado'):
        return cursor, cursor
    return tuple(sorted((estado.get('ancora', 0), cursor)))


def _posicionar_cursor_texto(estado, cursor, shift=False):
    cursor = max(0, min(len(estado['texto']), cursor))
    if shift:
        estado.setdefault('ancora', estado['cursor'])
        estado['selecionado'] = estado['ancora'] != cursor
    else:
        estado.pop('ancora', None)
        estado['selecionado'] = False
    estado['cursor'] = cursor


def _tecla_no_texto(estado, tipo, entrada='', ctrl=False, shift=False):
    """Local text undo; never invoke scene undo during typing."""
    chaves = ('texto', 'cursor', 'selecionado', 'ancora')
    antes = tuple(estado.get(k) for k in chaves)
    if ctrl and tipo in {'Z', 'Y'}:
        refazer = tipo == 'Y' or shift
        origem, destino = ('refazer', 'desfazer') if refazer else ('desfazer', 'refazer')
        pilha = estado.get(origem)
        if pilha:
            estado.setdefault(destino, []).append(antes)
            for k, valor in zip(chaves, pilha.pop()):
                if valor is None: estado.pop(k, None)
                else: estado[k] = valor
        return True
    tratado = _editar_texto(estado, tipo, entrada, ctrl, shift)
    if estado['texto'] != antes[0]:
        pilha = estado.setdefault('desfazer', [])
        pilha.append(antes)
        del pilha[:-LIMITE_TEXTO_MEDIDA]
        estado['refazer'] = []
    return tratado


def _editar_texto(estado, tipo, entrada, ctrl, shift):
    texto = estado['texto']
    cursor = min(estado.get('cursor', len(texto)), len(texto))
    if ctrl and tipo == 'A':
        estado.update(selecionado=True, ancora=0, cursor=len(texto))
        return True
    if tipo in {'LEFT_ARROW', 'RIGHT_ARROW', 'HOME', 'END'}:
        if tipo == 'HOME':
            cursor = 0
        elif tipo == 'END':
            cursor = len(texto)
        elif estado.get('selecionado') and not shift:
            cursor = _selecao_no_texto(estado)[0 if tipo == 'LEFT_ARROW' else 1]
        else:
            cursor += -1 if tipo == 'LEFT_ARROW' else 1
        _posicionar_cursor_texto(estado, cursor, shift)
        return True
    if ctrl and tipo != 'V':
        return False
    entrada = ''.join(c for c in entrada if c.isprintable())[:LIMITE_TEXTO_MEDIDA]
    if not entrada and tipo not in {'BACK_SPACE', 'DEL'}:
        return False
    if estado.get('selecionado'):
        inicio, fim = _selecao_no_texto(estado)
        operador = entrada.strip()
        if (inicio == 0 and fim == len(texto) and len(operador) == 1
                and operador in OPERADORES_MEDIDA and texto.strip()):
            texto = (texto.rstrip() + ' ' + operador + ' ')[:LIMITE_TEXTO_MEDIDA]
            estado.update(texto=texto, cursor=len(texto), selecionado=False)
            estado.pop('ancora', None)
            return True
        texto, cursor = texto[:inicio] + texto[fim:], inicio
    elif entrada:
        pass
    elif tipo == 'BACK_SPACE' and cursor:
        texto = texto[:cursor - 1] + texto[cursor:]
        cursor -= 1
    elif tipo == 'DEL':
        texto = texto[:cursor] + texto[cursor + 1:]
    if entrada in tuple(OPERADORES_MEDIDA) and texto[:cursor].strip():
        # TYPED operators always get a space on each side, anywhere in the expression:
        # '100+25' was inconsistent with '664 - 100' (user screenshot). Pasted text is
        # retained as supplied.
        antes = texto[:cursor].rstrip() + ' ' + entrada + ' '
        texto, cursor = antes + texto[cursor:].lstrip(), len(antes)
    elif entrada:
        texto = texto[:cursor] + entrada + texto[cursor:]
        cursor += len(entrada)
    texto = texto[:LIMITE_TEXTO_MEDIDA]
    estado.update(texto=texto, cursor=min(cursor, len(texto)),
                  selecionado=False)
    estado.pop('ancora', None)
    return True


def _realcar_selecao_texto(x, y, estado, tamanho, medida=False, barra=True, largura=None):
    """Highlight only the selected input buffer; exclude automatic units/results."""
    inicio, fim = _selecao_no_texto(estado)
    if inicio == fim:
        return
    texto = estado['texto']
    mapa = tuple(range(len(texto) + 1))
    if medida:
        texto, mapa = _apresentacao_medida(texto, _opcoes._opcao('unidade_padrao'))
    cursor = estado['cursor']
    def prefixo(i):
        pos, c = mapa[i], mapa[cursor]
        return texto[:pos] if not barra or i <= cursor else texto[:c] + '|' + texto[c:pos]
    blf.size(0, tamanho)
    a, b = (blf.dimensions(0, prefixo(i))[0] for i in (inicio, fim))
    if largura is not None:
        a, b = min(a, largura), min(b, largura)
    if b > a:
        # The wcol_text selection background is nearly black, invisible on the black
        # HUD.
        cor = bpy.context.preferences.themes[0].user_interface.wcol_regular.inner_sel
        _gaveta._retangulo_gaveta(x + a, y - 2, b - a, blf.dimensions(0, '0')[1] + 4, (*cor[:3], 1))


def _texto_editavel_gaveta(x, y, estado, largura, tamanho=12, cor=None):
    medida = estado.get('medida', False)
    texto = _com_cursor(estado['texto'], estado['cursor'], medida=medida)
    fonte = next((t for t in range(tamanho, 8, -1)
                  if _medidor_blf(t)(texto) <= largura), 9)
    _realcar_selecao_texto(x, y, estado, fonte, medida=medida, largura=largura)
    _gaveta._texto_cabivel_gaveta(x, y, texto, largura, tamanho, cor=cor)


def _cursor_no_x(texto, cursor, x_texto, mouse_x, largura, medida=False):
    """Text position nearest a click at x. Text displays a '|' at the cursor, so
    positions after it shift by its width. `largura(texto)` measures pixels (blf in
    Blender)."""
    if medida:
        mostrado, mapa = _apresentacao_medida(texto, _opcoes._opcao('unidade_padrao'))
        pos = mapa[min(cursor,len(texto))]
        return min(range(len(texto)+1),key=lambda i:abs(x_texto+largura(
            mostrado[:mapa[i]] if mapa[i]<=pos else mostrado[:pos]+'|'+mostrado[pos:mapa[i]])-mouse_x))
    def x_de(i):
        mostrado = (texto[:i] if i <= cursor
                    else texto[:cursor] + '|' + texto[cursor:i])
        return x_texto + largura(mostrado)
    return min(range(len(texto) + 1), key=lambda i: abs(x_de(i) - mouse_x))


def _medidor_blf(tamanho):
    def largura(texto):
        blf.size(0, tamanho)
        return blf.dimensions(0, texto)[0]
    return largura


_NUMEROS_MEDIDA = re.compile(r'\d[\d.,]*|[.,]\d*')


def _numero_digitado(token):
    decimal = token.rfind(',') if ',' in token else token.rfind('.')
    if ',' not in token and token.count('.') > 1 and re.fullmatch(r'\d{1,3}(?:\.\d{3})+',token):
        decimal = -1
    inteiro = ''.join(c for c in token[:decimal] if c.isdigit()) if decimal>=0 else ''.join(c for c in token if c.isdigit())
    fracao = ''.join(c for c in token[decimal+1:] if c.isdigit()) if decimal>=0 else ''
    return inteiro or '0', fracao, decimal


def _normalizar_numeros(texto):
    def numero(m):
        inteiro, fracao, decimal = _numero_digitado(m.group())
        return inteiro + ('.'+fracao if decimal>=0 else '')
    return _NUMEROS_MEDIDA.sub(numero,texto)


@lru_cache(maxsize=128)
def _apresentacao_medida(texto, unidade):
    # Keep the buffer as typed: thousands separators must not change the
    # expression/cursor.
    partes=[];mapa=[0]*(len(texto)+1);fim=0;tamanho=0
    for m in _NUMEROS_MEDIDA.finditer(texto):
        for i in range(fim,m.start()):
            mapa[i]=tamanho;partes.append(texto[i]);tamanho+=1
        token=m.group();inteiro,fracao,decimal=_numero_digitado(token)
        grupos=[]
        for i in range(len(inteiro),0,-3):grupos.insert(0,inteiro[max(0,i-3):i])
        agrupado='.'.join(grupos)
        mostrado=agrupado+(','+fracao if decimal>=0 else '')
        for j in range(len(token)+1):
            if decimal>=0 and j>decimal:
                pos=len(agrupado)+1+sum(c.isdigit() for c in token[decimal+1:j])
            else:
                digitos=sum(c.isdigit() for c in token[:j])
                pos=0 if not digitos else digitos+(max(0,digitos-1+(-len(inteiro))%3)//3)
                if digitos==len(inteiro):pos=len(agrupado)
            mapa[m.start()+j]=tamanho+pos
        partes.append(mostrado);tamanho+=len(mostrado);fim=m.end()
    for i in range(fim,len(texto)):
        mapa[i]=tamanho;partes.append(texto[i]);tamanho+=1
    mapa[-1]=tamanho
    mostrado=''.join(partes)
    conta=bool(re.search(r'[+*/()]|(?<=\S)\s*-',texto))
    resultado=None
    if conta and texto.count('(')==texto.count(')') and not re.search(r'[+*/(-]\s*$',texto):
        try:
            # Incomplete previews do not print native errors on every keystroke; Enter
            # validates normally.
            with redirect_stderr(StringIO()):
                resultado=_ler_medida_digitada(texto,minimo=-math.inf)*1000
        except (ValueError,TypeError,OverflowError,ZeroDivisionError):pass
    if resultado is not None:
        mostrado+=' = '+_opcoes._texto_medida(resultado,unidade)
    elif not re.search(_UNIDADE_RE,texto,re.I):
        mostrado+=' '+_opcoes.UNIDADES_MEDIDA[unidade][1]
    return mostrado,tuple(mapa)


def _com_cursor(texto, cursor, medida=False):
    cursor = min(cursor, len(texto))
    if medida:
        texto,mapa=_apresentacao_medida(texto,_opcoes._opcao('unidade_padrao'))
        cursor=mapa[cursor]
    return texto[:cursor] + '|' + texto[cursor:]


def _ler_medida_digitada(texto, minimo=0.001):
    """Typed text -> meters.

    Accept expressions and mixed units: '600 + 500', '600cm + 500mm', '1m - 20mm',
    '(600+500)/2'. Unitless numbers use the default unit in options (factory default
    mm); decimal commas also work. Blender's parser returns floating-point noise
    (1100.0001): round to 0.01 mm. Raise ValueError below `minimo` (meters): 1 mm,
    or 0 for gaps/offsets."""
    texto = _arrumar_texto_medida(_normalizar_numeros(texto.strip()))
    sufixo = _opcoes.UNIDADES_MEDIDA[_opcoes._opcao('unidade_padrao')][1]
    texto = _unidade_nos_numeros_soltos(texto, sufixo)
    valor = bpy.utils.units.to_value('METRIC', 'LENGTH', texto,
                                     str_ref_unit='1 ' + sufixo)
    if not math.isfinite(valor) or valor < minimo - 1e-9:
        raise ValueError("Enter a measurement of at least %g mm" % (minimo * 1000.0))
    return round(valor * 1000.0, 2) / 1000.0


def _ler_numero_digitado(texto):
    """Plain number from options sliders ('14', '1,5', '10 + 4', '18px'). The writer
    clamps to minimum/maximum."""
    texto = texto.strip().replace(',', '.').lower().replace('px', '')
    valor = bpy.utils.units.to_value('NONE', 'NONE', texto)
    if not math.isfinite(valor):
        raise ValueError("Enter a number")
    return valor
