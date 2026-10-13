"""Gaveta: desenho dos widgets (callback POST_PIXEL), o gizmo de hover
dos campos e a caixa de digitar medida -- teclas, cursor e leitura do
texto em metros --, que a HUD tambem usa."""

import bpy, colorsys, math, re, gpu, blf
from gpu_extras.batch import batch_for_shader
from bpy.types import Gizmo

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = None
_opcoes = None
_gaveta_eventos = None
_gaveta = None
_orcamento = None
_hud = None
_solda = None
def _eh_campo_contador(acao):
    """Contador com rotulo (7o campo): o "Folhas" da porta, desenhado
    como campo de medida -- arrastar muda, clicar digita -- em vez do
    `< 2 >` das ferragens, que soma/tira pela metade clicada."""
    return bool(acao and acao[0] == 'contador' and len(acao) > 6)


def _chave_widget(acao):
    """Identidade estavel do widget, usada para guardar o realce dele.

    Devolve None para o que NAO e' botao (decoracao, rotulo, trilho do
    slider): essas coisas nao acendem.
    """
    if not acao:
        return None
    verbo = acao[0]
    if verbo in {'wireframe', 'separador', 'slider', 'fundo', 'pergunta'}:
        return None
    if verbo == 'resposta':
        return 'resp:%d' % acao[1]
    if verbo in {'suspenso', 'faixa'}:
        return '%s:%s' % (verbo, acao[1])
    if verbo == 'cor':
        # quadro e matiz sao superficie de arraste, nao botao
        if acao[2] == 'amostra':
            return 'cor:' + acao[1]
        return 'cor:%s:%s' % (acao[1], acao[5]) if acao[2] == 'atalho' else None
    if verbo in _gaveta.BOTOES_CRIAR and len(acao) > 4 and acao[4]:
        return None             # botao apagado nao acende
    if verbo == 'cadeado':
        return 'cad:%d' % acao[2]
    if verbo == 'medida':
        # prop + nome: "Espessura" da porta e da moldura sao campos distintos
        return 'medida:%s:%s' % (acao[2], acao[3])
    if verbo == 'modo':
        return None             # so' indicador: o modo sai da selecao
    if verbo == 'divisa':
        return 'divisa' if acao[1] else None    # coberta pelas opcoes
    if verbo == 'aba':
        return '%s:%s' % (verbo, acao[1])
    if verbo == 'escolha':
        return 'esc:%s:%s' % (acao[1], acao[2])
    if verbo == 'operador':
        # botao de texto apagado (selecao invalida) nao acende
        return None if _gaveta_eventos._operador_apagado(acao) else 'op:' + acao[1]
    if verbo == 'navegar':
        return 'nav:%s:%s' % (acao[1], acao[2])
    if verbo == 'contador':
        return 'cont:%s' % acao[1]
    if verbo == 'rolar_nivel':
        return 'rol:%s:%s' % (acao[1], acao[2])
    if verbo == 'preset':
        return 'preset:%s' % acao[1]['arquivo']
    if verbo == 'item':
        return 'item:%s:%s' % (acao[1]['arquivo'], acao[2])
    return verbo


class VIEW3D_GT_campo_gaveta(Gizmo):
    """Hit-test invisivel sobre o retangulo de UM widget da gaveta.

    Existe so' para ganhar `is_highlight`: o desenho da gaveta e' GPU e
    nao recebe evento de mouse, e um operador modal persistente roubaria
    evento de outros add-ons. O clique cai no mesmo operador que a
    keymap ja' dispara para a area inteira, entao nada muda ao clicar.

    Quando o widget tem icone, o disco do `GIZMO_GT_button_2d` fica de
    FORA deste hit-test: assim o gizmo do icone continua ganhando o
    pick ali e o tooltip dele nao se perde. O glow cobre os dois casos
    porque soma os dois `is_highlight`.
    """
    bl_idname = 'VIEW3D_GT_campo_gaveta'

    def draw(self, context):
        pass

    def test_select(self, context, location):
        alvo = _hud._campos_gaveta.get(self.as_pointer())
        if not alvo:
            return -1
        x, y, w, h, icone = alvo
        px, py = location
        if not (x <= px <= x + w and y <= py <= y + h):
            return -1
        if icone is not None:
            cx, cy, raio = icone
            if (px - cx) ** 2 + (py - cy) ** 2 <= raio * raio:
                return -1
        return 0


def _degrade_gaveta(vertices, cores):
    """Triangulos com cor por vertice (quadro e faixa de matiz)."""
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
    """Marcador do seletor: aro preto + branco em volta da cor escolhida,
    visivel sobre qualquer ponto do quadro."""
    for r, cor in ((raio + 1.5, (0, 0, 0, 1)), (raio, (1, 1, 1, 1)),
                   (raio - 2, (*miolo, 1))):
        _gaveta._retangulo_arredondado_gaveta(cx - r, cy - r, 2 * r, 2 * r, r, cor)


def _listras_gizmo_gaveta(x, y, w, h):
    """Amostra do realce do gizmo: X, Y, Z e a espessura, lado a lado."""
    tons = [_hud._cor_eixo_gizmo(e) for e in ('axis_x', 'axis_y', 'axis_z')]
    tons.append(_opcoes.COR_REALCE_PADRAO)
    for i, tom in enumerate(tons):
        _gaveta._retangulo_gaveta(x + w * i / 4, y, w / 4, h, (*tom, 1))


def _desenhar_opcao_gaveta(context, x, y, w, h, rotulo, acao, cores, fundo):
    """Controles do painel de opcoes: lista suspensa, faixa e cor."""
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
        if (edicao is not None and edicao['propriedade'] == acao[1]
                and edicao['area'] == context.area.as_pointer()):
            texto, cursor = edicao['texto'], edicao['cursor']
            rotulo = texto[:cursor] + '|' + texto[cursor:]
        blf.size(0, 12)
        largura = min(blf.dimensions(0, rotulo)[0], w - 12)
        _gaveta._texto_cabivel_gaveta(x + (w - largura) / 2, y + (h - 12) / 2,
                              rotulo, w - 12)
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
        # Interpolar os 4 cantos (preto embaixo, branco e matiz pura em
        # cima) da' exatamente V * mistura(branco, matiz, S)
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
    """Campo de medida que sai em vermelho: Espessura acima do
    convencional (`_chapas.ESPESSURA_ALERTA_MM`)."""
    try:
        return (acao[0] == 'medida' and acao[3] == 'Espessura'
                and _chapas._espessura_em_alerta(acao[4]))
    except (IndexError, TypeError, ValueError):
        return False


def _cor_alerta_gaveta():
    """Vermelho do TEMA (cor literal e' proibida, DESIGN.md sec. 5): o do
    erro do editor Info, clareado ate' ler bem sobre o fundo escuro."""
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
    """(x, y, w, h) comum a dois retangulos; largura/altura >= 0."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1 = min(a[0] + a[2], b[0] + b[2])
    y1 = min(a[1] + a[3], b[1] + b[3])
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0)


def _desenhar_divisa_gaveta(context, largura, meio, acao, cores):
    """Linha entre a aba e a biblioteca. Sob o mouse ela ganha o mesmo
    halo dos botoes e uma pega no centro: e' ali que se arrasta."""
    realce = _gaveta._valor_realce(context, _chave_widget(acao)) if acao[1] else 0.0
    gpu.state.blend_set('ALPHA')
    if realce > 0.01:
        _gaveta._glow_gaveta(0, meio - 1, largura, 2, 1, realce, cores.text)
    cor = tuple(c + (t - c) * realce for c, t in
                zip(cores.outline[:3], cores.text[:3]))
    _gaveta._retangulo_gaveta(0, meio - 1 if realce > 0.5 else meio, largura,
                      2 if realce > 0.5 else 1, (*cor, 1))
    # pega: tres tracinhos no meio, como a divisoria de areas do Blender
    for i in (-1, 0, 1):
        _gaveta._retangulo_gaveta(largura / 2 - 9, meio + i * 3 - 0.5, 18, 1,
                          (*cor, 0.55 + 0.45 * realce))


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
            # o glow cresce so' para a direita: a alca encosta na borda
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
    # A tela da gaveta e' desenhada antes dos GIZMO_GT_button_2d.
    # POST_PIXEL cobre os icones nativos se desenhar o fundo por cima.
    if not tela:
        return
    largura, altura = context.region.width, context.region.height
    cores, fundo = _gaveta._cores_gaveta()
    gpu.state.blend_set('ALPHA')
    _gaveta._retangulo_gaveta(0, 0, largura, altura, fundo)
    _gaveta._retangulo_gaveta(largura - 2, 0, 2, altura, (0.27, 0.27, 0.27, 1))
    widgets = _gaveta._widgets_gaveta(context, largura, altura)
    # O cabecalho e' desenhado por ultimo, acima do conteudo rolavel.
    cabecalho, conteudo, rodape = _gaveta._partes_gaveta(widgets)
    # A faixa do rodape (e o fundo do painel de opcoes) entra ENTRE o
    # conteudo e os botoes do rodape: o conteudo rola por baixo dela.
    faixa = (0, 0, 0, 0, '', ('faixa_rodape',))
    # Cada painel e' recortado no proprio retangulo: o da aba rola por
    # baixo do cabecalho e da divisoria, a biblioteca por baixo da
    # divisoria e do pe' fixo.
    cima, divisa, baixo = _gaveta._paineis_gaveta(conteudo)
    meio = round(divisa[1] + divisa[3] / 2) if divisa else _gaveta.ALTURA_RODAPE_GAVETA
    recorte_cima = (0, meio + 1, largura, max(0, altura - 48 - meio - 1))
    recorte_baixo = (0, _gaveta.ALTURA_RODAPE_GAVETA, largura,
                     max(0, meio - _gaveta.ALTURA_RODAPE_GAVETA))
    recortes = ([recorte_cima] * len(cima) + [None] * bool(divisa)
                + [recorte_baixo] * len(baixo))
    for indice, (x, y, w, h, rotulo, acao) in enumerate(
            conteudo + [faixa] + rodape + cabecalho):
        painel = recortes[indice] if indice < len(recortes) else None
        if painel is not None:
            gpu.state.scissor_test_set(True)
            gpu.state.scissor_set(*(int(round(c)) for c in painel))
        else:
            gpu.state.scissor_test_set(False)
        if acao and acao[0] == 'divisa':
            _desenhar_divisa_gaveta(context, largura, meio, acao, cores)
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
        if acao and acao[0] == 'separador':
            _gaveta._retangulo_gaveta(x, y, w, h, (*cores.outline[:3], 1))
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
            # caixa PRETA: destaca que a gaveta espera uma resposta
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
        if acao and acao[0] == 'slider' and acao[1] == 'retratos':
            # o pequeno, ao lado do titulo: a caixa dele (a do titulo),
            # trilho e bolinha
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
                _gaveta._texto_cabivel_gaveta(x, y + 15, 'Tamanho das', largura_rotulo, 11)
                _gaveta._texto_cabivel_gaveta(x, y + 2, 'miniaturas', largura_rotulo, 11)
            valor = (context.scene.chapa_tam_bloco - 2) / 6.0
            _gaveta._retangulo_gaveta(tx, ty - 1.5, tw, 3, tuple(cores.inner))
            _gaveta._retangulo_arredondado_gaveta(
                tx + tw * valor - 6, ty - 6, 12, 12, 6, (*cores.text, 1))
            continue
        if acao and acao[0] == 'preset':
            _gaveta._botao_gaveta(x, y, w, h)
            lado = min(w - 10, h - 27)
            _gaveta._retangulo_gaveta(x + 5, y + 22, lado, lado, fundo)
            # BLF e outros widgets podem alterar o blend antes da foto.
            gpu.state.blend_set('ALPHA')
            _gaveta._desenhar_foto_gaveta(acao[1], x + 5, y + 22, lado, lado)
            _gaveta._texto_cabivel_gaveta(x + 5, y + 5, rotulo, w - 10, 11)
            continue
        # A peca que esta' entrando (ou saindo) invade a area das setas.
        # O recorte faz o carrossel parecer uma janela por onde a fila
        # passa, em vez de pecas aparecendo do nada.
        recortado = bool(acao and acao[0] == 'navegar')
        if recortado:
            # trilho do carrossel DENTRO do recorte do painel
            trilho = (12 + 24, int(y) - 1, max(0, largura - 24 - 48), 27)
            if painel is not None:
                trilho = _intersecao_retangulos(trilho, painel)
            gpu.state.scissor_test_set(True)
            gpu.state.scissor_set(*(int(round(c)) for c in trilho))

        aceitar = bool(acao and acao[0] == 'escolha'
                       and acao[1] == _portas.CONFIRMAR_ETAPA)
        ativo = bool(acao and (acao[0] in {'navegar', 'modo', 'biblioteca'} and acao[-1]
                               or acao[0] == 'escolha' and acao[3]
                               or acao[0] == 'contador'
                               and not _eh_campo_contador(acao)
                               or acao[0] in _gaveta.BOTOES_CRIAR and acao[2]
                               # comparar, nunca hashear: a acao de preset
                               # e item da biblioteca leva um dict (v140:
                               # um set aqui derrubava a gaveta inteira)
                               or acao[0] == 'operador'
                               and acao[1] in (_solda.OP_CORRENTE_OBJETO,
                                               _solda.OP_RESETAR_DISTANCIA,
                                               _orcamento.OP_EXPORTAR_ORCAMENTO)
                               and len(acao) > 2 and acao[2]))
        # O halo vai ANTES do corpo do botao, como na alca: por cima
        # ele lavaria o texto em vez de circundar o widget.
        chave = _chave_widget(acao)
        if chave:
            _gaveta._glow_gaveta(x, y, w, h, 4, _gaveta._valor_realce(context, chave),
                         cores.text)
        apagado = bool(acao and acao[0] in _gaveta.BOTOES_CRIAR and len(acao) > 4
                       and acao[4]) or _gaveta_eventos._operador_apagado(acao)
        # "Criar Portas" LARANJA desde o inicio (pedido do usuario): e' o
        # ponto de partida da aba; mais forte enquanto marca o vao
        cor = None
        if acao and acao[0] in _gaveta.BOTOES_CRIAR and not apagado:
            cor = _gaveta.COR_CRIAR_PORTAS_ATIVO if acao[2] else _gaveta.COR_CRIAR_PORTAS
        elif aceitar:
            cor = COR_ACEITAR       # o "aceitar" da etapa (mockup do usuario)
        if not acao or acao[0] != 'cadeado':
            _gaveta._botao_gaveta(x, y, w, h, ativo=ativo,
                          secao=acao is None or apagado, cor=cor)
        campo_contador = _eh_campo_contador(acao)
        if acao and (acao[0] == 'medida' or campo_contador):
            edicao = _gaveta._edicao_gaveta[0]
            editando = (edicao is not None and edicao['area'] == context.area.as_pointer()
                        and edicao['propriedade'] == acao[1 if campo_contador else 2])
            if editando:
                _gaveta._botao_gaveta(x, y, w, h, ativo=True)
            # Espessura fora do convencional (> 60 mm): nome e valor em
            # vermelho. Alerta, nao trava -- o valor e' o que foi pedido.
            alerta = (_cor_alerta_gaveta() if not campo_contador
                      and _medida_em_alerta(acao) else None)
            _gaveta._texto_cabivel_gaveta(x + 7, y + h - 14,
                                   acao[6 if campo_contador else 3], w - 14, 11,
                                   cor=alerta)
            valor = rotulo if campo_contador else _opcoes._texto_medida(acao[4])
            if editando:
                texto, cursor = edicao['texto'], edicao['cursor']
                valor = texto[:cursor] + '|' + texto[cursor:]
            _gaveta._texto_cabivel_gaveta(x + 7, y + 6,
                                   valor, w - 14, 12, cor=alerta)
        elif acao and acao[0] in _gaveta.BOTOES_CRIAR:
            # "Criar Portas"/"Criar Puxador": largo, texto CENTRALIZADO
            blf.size(0, 12)
            largura_texto = min(blf.dimensions(0, rotulo)[0], w - 18)
            _gaveta._texto_cabivel_gaveta(
                x + (w - largura_texto) / 2, y + (h - 12) / 2, rotulo, w - 18,
                cor=(*cores.text[:3], 0.4) if apagado else (1.0, 1.0, 1.0, 1.0))
        elif acao and acao[0] == 'contador':
            # o valor no meio e as setas que dizem "arraste ou clique"
            blf.size(0, 13)
            largura_texto = blf.dimensions(0, rotulo)[0]
            _gaveta._texto_gaveta(x + (w - largura_texto) / 2, y + (h - 12) / 2,
                                  rotulo, 13)
            setas = (*cores.text[:3], 0.55)
            _gaveta._texto_gaveta(x + 7, y + (h - 12) / 2, '<', 12, setas)
            _gaveta._texto_gaveta(x + w - 14, y + (h - 12) / 2, '>', 12, setas)
        elif acao and acao[0] == 'escolha' and len(acao) > 6 and acao[6]:
            # retrato do carrossel: a foto em cima, o nome centrado embaixo
            gpu.state.blend_set('ALPHA')
            _gaveta._desenhar_foto_gaveta(acao[6], x + 4, y + 18, w - 8, h - 22)
            blf.size(0, 11)
            largura_texto = min(blf.dimensions(0, rotulo)[0], w - 8)
            _gaveta._texto_cabivel_gaveta(x + (w - largura_texto) / 2, y + 5,
                                          rotulo, w - 8, 11)
        elif _gaveta_eventos._icone_ao_lado(acao):
            # o icone (gizmo) na ponta esquerda, o texto depois dele
            _gaveta._texto_cabivel_gaveta(
                x + h + 4, y + (h - 12) / 2, rotulo, w - h - 13,
                cor=(*cores.text[:3], 0.4) if apagado else None)
        elif not _gaveta_eventos._icone_acao_gaveta(acao):
            _gaveta._texto_cabivel_gaveta(
                x + 9, y + (h - 12) / 2, rotulo, w - 18,
                cor=(*cores.text[:3], 0.4) if apagado else None)
        if recortado:
            gpu.state.scissor_test_set(False)
    gpu.state.scissor_test_set(False)
    _gaveta._retangulo_gaveta(0, altura - 48, largura, 48,
                       fundo)
    for x, y, w, h, rotulo, acao in cabecalho:
        _gaveta._glow_gaveta(x, y, w, h, 4,
                     _gaveta._valor_realce(context, _chave_widget(acao)), cores.text)
        if acao[0] != 'aba':
            continue        # corrente: so' o icone, desenhado pelo gizmo
        _gaveta._botao_gaveta(x, y, w, h,
                       ativo=context.scene.cabinet_aba == acao[1])
        _gaveta._texto_cabivel_gaveta(x + 9, y + 8, rotulo, w - 18)
    gpu.state.blend_set('NONE')


COR_ACEITAR = (0.13, 0.66, 0.30, 1.0)    # o visto e' o icone CHECKMARK


def _unidade_nos_numeros_soltos(texto, sufixo):
    """"60 + 5mm" -> "60cm + 5mm" (com padrao cm).

    Sozinho, o parser do Blender da' a um numero sem unidade a unidade
    do VIZINHO -- 60 virava 60 mm. A regra combinada e' outra: sem
    unidade, vale a padrao. So' parcelas de soma/subtracao recebem o
    sufixo; fator de * ou / (o 2 de "2*30cm") continua numero puro.
    """
    fichas = re.findall(r'\d+\.?\d*|\.\d+|[A-Za-z]+|\S', texto)
    if not any(f.isalpha() for f in fichas):
        return texto          # sem unidade nenhuma: str_ref_unit resolve
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
    """O que o cursor livre deixa escrever e o usuario quer dizer:

    - "51cm00" (unidade digitada no MEIO do numero) -> "5100cm";
    - "500 + cm" (operador sem numero antes da unidade) -> "500cm";
    - "500 +" (conta pela metade) -> "500".
    """
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


def _tecla_no_texto(estado, tipo, entrada='', ctrl=False):
    """Uma tecla na caixa de digitar medida (HUD e gaveta). `estado` tem
    texto, cursor e selecionado (o texto inteiro, como a caixa abre).

    Pedido do usuario: um OPERADOR com o texto selecionado CONTINUA a
    conta em vez de apagar ("600" e '+' -> "600 + "). Devolve False se a
    tecla nao e' de edicao.
    """
    texto = estado['texto']
    cursor = min(estado.get('cursor', len(texto)), len(texto))
    if ctrl and tipo == 'A':
        estado['selecionado'] = True
        return True
    if tipo in {'LEFT_ARROW', 'RIGHT_ARROW', 'HOME', 'END'}:
        if tipo == 'HOME':
            cursor = 0
        elif tipo == 'END':
            cursor = len(texto)
        else:
            cursor += -1 if tipo == 'LEFT_ARROW' else 1
        estado.update(cursor=max(0, min(len(texto), cursor)), selecionado=False)
        return True
    entrada = ''.join(c for c in entrada if c.isprintable())[:LIMITE_TEXTO_MEDIDA]
    if not entrada and tipo not in {'BACK_SPACE', 'DEL'}:
        return False
    if estado.get('selecionado'):
        operador = entrada.strip()
        if len(operador) == 1 and operador in OPERADORES_MEDIDA and texto.strip():
            texto = (texto.rstrip() + ' ' + operador + ' ')[:LIMITE_TEXTO_MEDIDA]
            estado.update(texto=texto, cursor=len(texto), selecionado=False)
            return True
        texto, cursor = '', 0
    elif entrada:
        pass
    elif tipo == 'BACK_SPACE' and cursor:
        texto = texto[:cursor - 1] + texto[cursor:]
        cursor -= 1
    elif tipo == 'DEL':
        texto = texto[:cursor] + texto[cursor + 1:]
    if entrada in tuple(OPERADORES_MEDIDA) and texto[:cursor].strip():
        # Operador DIGITADO sai sempre com um espaco de cada lado, em
        # qualquer ponto da conta: "100+25" ficava fora do padrao de
        # "664 - 100" (print do usuario). Colado, entra como veio.
        antes = texto[:cursor].rstrip() + ' ' + entrada + ' '
        texto, cursor = antes + texto[cursor:].lstrip(), len(antes)
    elif entrada:
        texto = texto[:cursor] + entrada + texto[cursor:]
        cursor += len(entrada)
    texto = texto[:LIMITE_TEXTO_MEDIDA]
    estado.update(texto=texto, cursor=min(cursor, len(texto)),
                  selecionado=False)
    return True


def _cursor_no_x(texto, cursor, x_texto, mouse_x, largura):
    """Posicao do texto mais perto de um clique em x. O texto aparece com
    a barra '|' no cursor: depois dela as posicoes andam a largura dela.
    `largura(texto)` mede em pixels (blf no Blender)."""
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


def _com_cursor(texto, cursor):
    cursor = min(cursor, len(texto))
    return texto[:cursor] + '|' + texto[cursor:]


def _ler_medida_digitada(texto):
    """Texto digitado -> metros.

    Aceita conta e unidades misturadas: "600 + 500", "600cm + 500mm",
    "1m - 20mm", "(600+500)/2". Numero sem unidade vale a unidade padrao
    das opcoes (mm de fabrica); virgula decimal tambem. O parser do
    Blender devolve ruido de float (1100.0001): arredonda em 0,01 mm.
    ValueError se nao for uma medida de 1 mm ou mais.
    """
    texto = _arrumar_texto_medida(texto.strip().replace(',', '.'))
    sufixo = _opcoes.UNIDADES_MEDIDA[_opcoes._opcao('unidade_padrao')][1]
    texto = _unidade_nos_numeros_soltos(texto, sufixo)
    valor = bpy.utils.units.to_value('METRIC', 'LENGTH', texto,
                                     str_ref_unit='1 ' + sufixo)
    if not math.isfinite(valor) or valor < 0.001 - 1e-9:
        raise ValueError('Informe uma medida de pelo menos 1 mm')
    return round(valor * 1000.0, 2) / 1000.0


def _ler_numero_digitado(texto):
    """Numero puro das faixas da engrenagem ("14", "1,5", "10 + 4",
    "18px"). Quem prende no minimo/maximo e' quem grava."""
    texto = texto.strip().replace(',', '.').lower().replace('px', '')
    valor = bpy.utils.units.to_value('NONE', 'NONE', texto)
    if not math.isfinite(valor):
        raise ValueError('Informe um numero')
    return valor
