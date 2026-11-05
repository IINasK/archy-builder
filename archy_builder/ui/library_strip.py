"""Horizontal library above the menu and scene, using native areas.

Splitting completes on the next tick: each stage stores only names and values, never
area references Blender may destroy when closing or merging."""
import os
import time
import hashlib
import bpy
import blf
from bpy.types import Operator
from bpy.props import StringProperty, IntProperty

_gaveta = _gaveta_eventos = _gaveta_desenho = _biblioteca = _materiais = _perguntas = None
_opcoes = None
_editor = _eventos = None
CHAVE_AREA = 'cabinet_biblioteca_area'
CHAVE_CENA = 'cabinet_viewport_area'
CHAVE_LAYOUT = 'cabinet_layout'
CHAVE_RECOLHIDA = 'cabinet_biblioteca_recolhida'
CHAVE_ALTURA = 'cabinet_biblioteca_altura'
# Chosen location (user request): 'MENU' (default: on the left, inside the menu below
# the divider) or 'FAIXA' (above the menu and scene). Applies to EVERY file: stored in
# preferences (`lugar_escolhido`); the screen holds only a copy. An old file's value
# becomes the preference on first use.
CHAVE_LUGAR = 'cabinet_biblioteca_lugar'
OP_LUGAR = 'object.cabinet_lugar_biblioteca'
_pendentes = [{}]
_menus_pendentes = [{}]     # Screen -> pointer to the scene area to split.
_catalogos = [{}]
_alturas = [{}]
ALTURA_INICIAL = 180
ALTURA_CATEGORIA = 18
TOPO_CATEGORIA = 26
ALTURA_COMPACTA = 160
INTERVALO_NIVEIS = 12
MARGEM_CATEGORIA = 3


def area_da_faixa(screen):
    nativa = next((a for a in screen.areas if _editor.eh_editor(a, _editor.TIPO_BIBLIOTECA)), None) if screen else None
    if nativa is not None:
        return nativa
    ptr = int(screen.get(CHAVE_AREA, 0)) if screen else 0
    return next((a for a in screen.areas if a.type == 'VIEW_3D'
                 and a.as_pointer() == ptr), None) if screen else None


def eh_faixa(context):
    area = getattr(context, 'area', None)
    return area is not None and (_editor.eh_editor(area, _editor.TIPO_BIBLIOTECA)
                                or area == area_da_faixa(getattr(context, 'screen', None)))


def viewport(screen):
    ptr = int(screen.get(CHAVE_CENA, 0)) if screen else 0
    menu = _gaveta._area_gaveta(screen)
    faixa = area_da_faixa(screen)
    areas = [a for a in screen.areas if a.type == 'VIEW_3D' and a not in (menu, faixa)]
    vizinho = next((a for a in areas if menu is not None and
                    abs(a.x - (menu.x + menu.width)) < 6 and
                    abs(a.y - menu.y) < 6 and abs(a.height - menu.height) < 6), None)
    return next((a for a in areas if a.as_pointer() == ptr),
                vizinho or max(areas, key=lambda a: a.width * a.height, default=None))


def configurar_interface(area):
    _editor.configurar(area, _editor.TIPO_BIBLIOTECA)


def _vista(area):
    rv = area.spaces.active.region_3d
    return dict(location=tuple(rv.view_location), rotation=tuple(rv.view_rotation),
                distance=rv.view_distance, perspective=rv.view_perspective)


def _restaurar_vista(area, dados):
    rv = area.spaces.active.region_3d
    rv.view_location = dados['location']
    rv.view_rotation = dados['rotation']
    rv.view_distance = dados['distance']
    rv.view_perspective = dados['perspective']


def abrir(context):
    screen = context.screen
    if screen.name in _pendentes[0]:
        return False
    principal = context.area
    menu = _gaveta._area_gaveta(screen)
    if menu is not None:
        principal = viewport(screen)
        # area_close only joins the menu with a neighbor of equal height.
        with context.temp_override(area=menu):
            bpy.ops.screen.area_close()
        screen[_gaveta._CHAVE_GAVETA] = 0
    estado = dict(etapa='INICIO', principal=principal.as_pointer(),
                  vista=_vista(principal), tentativas=0)
    _pendentes[0][screen.name] = estado
    if not bpy.app.timers.is_registered(configurar_pendentes):
        bpy.app.timers.register(configurar_pendentes, first_interval=0.05)
    return True


def configurar_pendentes():
    if _eventos._desfazendo[0]:
        return .05
    for janela in bpy.context.window_manager.windows:
        screen = janela.screen
        estado = _pendentes[0].get(screen.name)
        if estado is None:
            continue
        estado['tentativas'] += 1
        if estado['tentativas'] > 100:
            print("[Archy Builder] could not prepare the upper library")
            fechar(janela, screen)
            continue
        principal = next((a for a in screen.areas
                          if a.as_pointer() == estado['principal']), None)
        if principal is None:
            _pendentes[0].pop(screen.name, None)
            continue
        if estado['etapa'] == 'INICIO':
            estado['retangulo'] = (principal.x, principal.y, principal.width, principal.height)
            escala = max(1.0, bpy.context.preferences.system.ui_scale)
            altura = min(principal.height * 0.38, ALTURA_INICIAL * escala)
            with bpy.context.temp_override(window=janela, area=principal):
                bpy.ops.screen.area_split(direction='HORIZONTAL',
                                           factor=1 - altura / max(1, principal.height))
            estado['etapa'] = 'TOPO'
            continue
        x, y, w, h = estado['retangulo']
        if estado['etapa'] == 'TOPO':
            candidatas = [a for a in screen.areas if a.type == 'VIEW_3D'
                          and abs(a.x - x) < 5 and abs(a.width - w) < 6
                          and y <= a.y < y + h and a.height < h - 5]
            if len(candidatas) != 2:
                continue
            topo = max(candidatas, key=lambda a: a.y)
            inferior = min(candidatas, key=lambda a: a.y)
            configurar_interface(topo)
            screen[CHAVE_AREA] = 0
            screen[CHAVE_ALTURA] = topo.height
            screen[CHAVE_RECOLHIDA] = 0
            estado['retangulo'] = (inferior.x, inferior.y, inferior.width, inferior.height)
            estado['principal'] = inferior.as_pointer()
            with bpy.context.temp_override(window=janela, area=inferior):
                fator = min(0.5, _gaveta._largura_inicial_gaveta(bpy.context) / inferior.width)
                bpy.ops.screen.area_split(direction='VERTICAL', factor=fator)
            estado['etapa'] = 'MENU'
            continue
        candidatas = [a for a in screen.areas if a.type == 'VIEW_3D'
                      and abs(a.y - y) < 5 and abs(a.height - h) < 6
                      and x <= a.x < x + w]
        if len(candidatas) != 2:
            continue
        menu = min(candidatas, key=lambda a: a.x)
        cena = max(candidatas, key=lambda a: a.x)
        _editor.configurar(menu)
        screen[_gaveta._CHAVE_GAVETA] = 0
        screen[CHAVE_CENA] = str(cena.as_pointer())
        screen[CHAVE_LAYOUT] = 2
        _restaurar_vista(cena, estado['vista'])
        cena.tag_redraw()
        _pendentes[0].pop(screen.name, None)
    return 0.05 if _pendentes[0] else None


def fechar(janela, screen):
    _pendentes[0].pop(screen.name, None)
    _cancelar_altura(janela)
    for area in (_gaveta._area_gaveta(screen), area_da_faixa(screen)):
        if area is not None:
            with bpy.context.temp_override(window=janela, area=area):
                bpy.ops.screen.area_close()
    for chave in (_gaveta._CHAVE_GAVETA, CHAVE_AREA, CHAVE_CENA):
        screen[chave] = 0


def reconectar(screen):
    if _eventos._desfazendo[0]:
        return
    _editor.reparar(screen)
    if screen.get(CHAVE_LAYOUT) != 2:
        return
    ocultas = [a for a in screen.areas if a.type == 'VIEW_3D'
               and not a.spaces.active.show_region_header
               and not a.spaces.active.overlay.show_overlays]
    # Width describes only the old menu; the full strip is wider.
    if (area_da_faixa(screen) is None and len(ocultas) == 2
            and (screen.get(CHAVE_AREA) or screen.get(_gaveta._CHAVE_GAVETA))):
        topo = max(ocultas, key=lambda a: a.y)
        menu = next(a for a in ocultas if a != topo)
        if topo.y >= menu.y + menu.height - 5 and topo.width > menu.width:
            _editor.configurar(topo, _editor.TIPO_BIBLIOTECA)
            _editor.configurar(menu)
            screen[CHAVE_AREA] = screen[_gaveta._CHAVE_GAVETA] = 0
    menu = _gaveta._area_gaveta(screen)
    faixa = area_da_faixa(screen)
    if menu is not None and _editor.eh_editor(menu, _editor.TIPO_MENU):
        candidatas = [a for a in ocultas if abs(a.x - menu.x) < 6
                      and abs(a.y - menu.y - menu.height) < 6
                      and a.width > menu.width]
        if faixa is not None and faixa.type == 'VIEW_3D':
            _editor.configurar(faixa, _editor.TIPO_BIBLIOTECA)
            screen[CHAVE_AREA] = 0
        elif faixa is None and screen.get(CHAVE_AREA) and len(candidatas) == 1:
            _editor.configurar(candidatas[0], _editor.TIPO_BIBLIOTECA)
            screen[CHAVE_AREA] = 0
    cena = viewport(screen)
    if cena is not None:
        screen[CHAVE_CENA] = str(cena.as_pointer())


def esquecer():
    _pendentes[0].clear()
    _menus_pendentes[0].clear()
    _catalogos[0].clear()
    for janela in bpy.context.window_manager.windows:
        _cancelar_altura(janela)
    _alturas[0].clear()
    if bpy.app.timers.is_registered(_ajustar_alturas):
        bpy.app.timers.unregister(_ajustar_alturas)
    if bpy.app.timers.is_registered(configurar_pendentes):
        bpy.app.timers.unregister(configurar_pendentes)
    if bpy.app.timers.is_registered(_abrir_menus_pendentes):
        bpy.app.timers.unregister(_abrir_menus_pendentes)


def lugar_escolhido(screen=None):
    """'FAIXA' or 'MENU' from add-on preferences (user request: remember the choice
    across files). Before this preference existed, the choice lived only on the
    screen: the first marked screen supplies the preference."""
    if not _opcoes._opcao('biblioteca_lugar_definido'):
        antigo = screen.get(CHAVE_LUGAR) if screen else None
        if antigo in ('FAIXA', 'MENU'):
            definir_lugar(antigo)
    return _opcoes._opcao('biblioteca_lugar')


def definir_lugar(lugar, screen=None):
    _opcoes._definir_opcao('biblioteca_lugar', lugar)
    _opcoes._definir_opcao('biblioteca_lugar_definido', True)
    if screen:
        screen[CHAVE_LUGAR] = lugar


def acoplada(screen):
    """The library lives inside the menu rather than in the top strip."""
    return bool(screen) and lugar_escolhido(screen) == 'MENU'


def abrir_menu(context):
    """Only the menu left of the current area, with the library inside it (interactive
    divider in the middle, `gaveta.DIVISA_PADRAO`)."""
    screen = context.screen
    screen[CHAVE_LAYOUT] = 1
    screen[_gaveta._CHAVE_PENDENTE] = str(context.area.as_pointer())
    # Cap at half the screen: on narrow screens, open the menu smaller than the default.
    fator = max(0.08, min(0.5, _gaveta._largura_inicial_gaveta(context)
                          / max(1, context.area.width)))
    with context.temp_override(area=context.area):
        bpy.ops.screen.area_split(direction='VERTICAL', factor=fator)
    if not bpy.app.timers.is_registered(_gaveta._configurar_gavetas):
        bpy.app.timers.register(_gaveta._configurar_gavetas, first_interval=0.05)


def trocar_lugar(context):
    """Strip <-> menu on the TIMER: the click originates inside the menu or strip;
    closing the area serving the operator would free it from under the operator.
    Store only the screen name."""
    screen = context.screen
    if viewport(screen) is None:
        return "No viewport available for the library"
    _menus_pendentes[0][screen.name] = None
    if not bpy.app.timers.is_registered(_abrir_menus_pendentes):
        bpy.app.timers.register(_abrir_menus_pendentes, first_interval=0.0)
    return None


def _trocar_agora(janela, screen):
    principal = viewport(screen)
    if principal is None:
        return
    # Switch what is actually OPEN: an old file may open with the strip while
    # preferences already specify the menu.
    no_menu = (area_da_faixa(screen) is None
               and (_gaveta._area_gaveta(screen) is not None or acoplada(screen)))
    if no_menu:
        definir_lugar('FAIXA', screen)
        with bpy.context.temp_override(window=janela, area=principal):
            abrir(bpy.context)
        return
    definir_lugar('MENU', screen)
    ptr = principal.as_pointer()
    if area_da_faixa(screen) is not None or _gaveta._area_gaveta(screen) is not None:
        fechar(janela, screen)
    # Merged area geometry only exists on the next tick.
    _menus_pendentes[0][screen.name] = ptr
    if not bpy.app.timers.is_registered(_abrir_menus_pendentes):
        bpy.app.timers.register(_abrir_menus_pendentes, first_interval=0.05)


def _abrir_menus_pendentes():
    for janela in bpy.context.window_manager.windows:
        screen = janela.screen
        if screen.name not in _menus_pendentes[0]:
            continue
        ptr = _menus_pendentes[0].pop(screen.name)
        if ptr is None:
            _trocar_agora(janela, screen)
            continue
        # The scene area may have been merged: use the largest remaining viewport.
        principal = next((a for a in screen.areas if a.as_pointer() == ptr), None) or max(
            (a for a in screen.areas if a.type == 'VIEW_3D'),
            key=lambda a: a.width * a.height, default=None)
        if principal is not None:
            with bpy.context.temp_override(window=janela, area=principal):
                abrir_menu(bpy.context)
    # Registering from within the timer's own tick is ignored: keep it alive while
    # switching to the menu still awaits the scene-area split.
    return 0.05 if _menus_pendentes[0] else None


class OBJECT_OT_lugar_biblioteca(Operator):
    """Move the library from the top strip into the menu, or back."""
    bl_idname = OP_LUGAR
    bl_label = "Library location"

    def execute(self, context):
        erro = trocar_lugar(context)
        if erro:
            self.report({'WARNING'}, erro)
            return {'CANCELLED'}
        return {'FINISHED'}


def _linha(context, itens, x, y, w, valores, nivel, selecionado, pai=None,
           prefixo='cabinet_carrossel'):
    if not valores or w < 50:
        return
    chave = '%s_%d_%s' % (prefixo, nivel, str(pai))
    if len(chave.encode('utf-8')) > 63:
        chave = prefixo + '_' + hashlib.sha1(chave.encode('utf-8')).hexdigest()[:24]
    ordenados = list(valores) if nivel == 0 else sorted(valores, key=str.casefold)
    blf.size(0, 10)
    def cabem(inicio, espaco, inverso=False):
        fatia, usado = [], 0
        for k in range(inicio, len(ordenados)):
            valor = ordenados[-1 - k] if inverso else ordenados[k]
            bw = min(espaco, max(32, blf.dimensions(0, valor)[0] + 12))
            intervalo = 2 if fatia else 0
            if usado + intervalo + bw > espaco:
                break
            fatia.append((valor, bw))
            usado += intervalo + bw
        return fatia
    completa = cabem(0, w)
    rola = len(completa) < len(ordenados)
    espaco = w - 34 if rola else w
    # Measure the end too: varying name widths must not put the last category beyond
    # arrow/wheel reach.
    limite = max(0, len(ordenados) - len(cabem(0, espaco, inverso=True))) if rola else 0
    inicio = max(0, min(limite, int(context.screen.get(chave, 0))))
    fatia = cabem(inicio, espaco) if rola else completa
    if inicio > 0:
        itens.append((x, y, 14, ALTURA_CATEGORIA, '', ('rolar_nivel', chave, -1, limite)))
    if inicio + len(fatia) < len(ordenados):
        itens.append((x + w - 14, y, 14, ALTURA_CATEGORIA, '', ('rolar_nivel', chave, 1, limite)))
    bx = x + 17 if rola else x
    for valor, bw in fatia:
        acao = (('biblioteca', dict((nome, modo) for modo, nome in _gaveta.MODOS_BIBLIOTECA)[valor],
                 valor == selecionado) if nivel == 0 else
                ('navegar', nivel, valor, chave, limite, valor == selecionado))
        itens.append((bx, y, bw, ALTURA_CATEGORIA, valor,
                      acao))
        bx += bw + 2


def invalidar():
    _catalogos[0].clear()


def _indice(materiais):
    pasta = _biblioteca.pasta_biblioteca()
    leitor = _materiais.ler_materiais if materiais else _biblioteca.indice_completo
    chave = (pasta, materiais, id(leitor), id(_biblioteca.itens_de_fabrica))
    agora = time.monotonic()
    guardado = _catalogos[0].get(chave)
    # No JSON, thousands of paths or network stat calls on every redraw.
    if guardado and agora - guardado['instante'] < 0.25:
        return guardado
    caminho = os.path.join(pasta, _materiais.NOME_ARQUIVO if materiais else _biblioteca.NOME_INDICE)
    try:
        st = os.stat(caminho)
        assinatura = (st.st_mtime_ns, st.st_size)
    except OSError:
        assinatura = None
    if guardado and guardado['assinatura'] == assinatura:
        guardado['instante'] = agora
        return guardado
    todos = leitor() if materiais else leitor() + _biblioteca.itens_de_fabrica()
    niveis = (lambda it: tuple(v for v in (it.get('n1'), it.get('n2'), it.get('n3')) if v)
              ) if materiais else _biblioteca.caminho_de
    filhos, itens = {}, {}
    for it in todos:
        caminho = niveis(it)
        itens.setdefault(caminho, []).append(it)
        for k, nome in enumerate(caminho):
            filhos.setdefault(caminho[:k], set()).add(nome)
    guardado = dict(assinatura=assinatura, instante=agora,
                   por_arquivo={(it.get('pasta', pasta), it['arquivo']): it
                                for it in todos if it.get('arquivo')},
                   filhos={pai: sorted(nomes, key=str.casefold) for pai, nomes in filhos.items()},
                   itens={pai: sorted(valores, key=lambda it: it.get('nome', '').casefold())
                          for pai, valores in itens.items()})
    if len(_catalogos[0]) >= 4:
        _catalogos[0].pop(next(iter(_catalogos[0])))
    _catalogos[0][chave] = guardado
    return guardado


def catalogo(context):
    s = context.scene
    materiais = s.cabinet_bib_modo == 'MATERIAIS'
    trilha = tuple(v for v in (s.cabinet_mat_n1, s.cabinet_mat_n2, s.cabinet_mat_n3) if v
                  ) if materiais else _biblioteca.trilha_da_cena(s)
    prefixo = 'cabinet_carrossel_mat' if materiais else 'cabinet_carrossel'
    indice = _indice(materiais)
    linhas = []
    for nivel in range(1, len(trilha) + 2):
        pai = tuple(trilha[:nivel - 1])
        filhos = indice['filhos'].get(pai, [])
        if not filhos:
            break
        linhas.append((nivel, filhos, trilha[nivel - 1] if len(trilha) >= nivel else '',
                       None if nivel == 1 else pai[0] if nivel == 2 else pai))
        if len(trilha) < nivel:
            break
    return linhas, indice['itens'].get(trilha, []) if trilha else [], prefixo


def _subcategorias_em_linha(context, itens, linhas, largura, y, prefixo):
    """One box per level, including the Cabinets/Materials selector. Tabs and hover
    targets share the same rectangles."""
    if not linhas:
        return
    livre = largura - 12 - INTERVALO_NIVEIS * (len(linhas) - 1)
    blf.size(0, 10)
    desejadas = []
    for _nivel, filhos, _escolhido, _pai in linhas:
        usado = 0
        for nome in filhos:
            usado += (2 if usado else 0) + max(32, blf.dimensions(0, nome)[0] + 12)
            if usado >= livre:
                break
        desejadas.append(max(56, min(livre, usado + 2 * MARGEM_CATEGORIA)))
    tamanhos = [0] * len(linhas)
    pendentes = list(range(len(linhas)))
    restante = livre
    if linhas[0][0] == 0:
        # Keep both modes fully visible when levels fit; in a narrow strip the carousel
        # still provides access to both.
        tamanhos[0] = min(desejadas[0], max(56, livre - 56 * (len(linhas) - 1)))
        restante -= tamanhos[0]
        pendentes.remove(0)
    # Short levels do not waste a whole column; give spare space to levels needing
    # scrolling without squeezing their neighbors.
    while pendentes:
        cota = restante / len(pendentes)
        curtos = [i for i in pendentes if desejadas[i] <= cota]
        if not curtos:
            for i in pendentes:
                tamanhos[i] = cota
            break
        for i in curtos:
            tamanhos[i] = desejadas[i]
            restante -= tamanhos[i]
            pendentes.remove(i)
    x = 6
    for i, ((nivel, filhos, escolhido, pai), w) in enumerate(zip(linhas, tamanhos)):
        if i:
            itens.append((x - INTERVALO_NIVEIS / 2 - 1, y - 1, 2,
                          ALTURA_CATEGORIA + 2, '', ('separador', 'biblioteca')))
        chave = hashlib.sha1(repr((prefixo, nivel, pai)).encode('utf-8')).hexdigest()[:20]
        itens.append((x, y - MARGEM_CATEGORIA, w,
                      ALTURA_CATEGORIA + 2 * MARGEM_CATEGORIA, '',
                      ('fundo', 'categoria_biblioteca', chave)))
        _linha(context, itens, x + MARGEM_CATEGORIA, y, w - 2 * MARGEM_CATEGORIA,
               filhos, nivel, escolhido, pai, prefixo)
        x += w + INTERVALO_NIVEIS


def caixa_categoria(acao):
    return bool(acao and acao[:2] == ('fundo', 'categoria_biblioteca'))


def retangulos_filhos(caixa, itens):
    """The background receives hover only in space not belonging to a tab."""
    x, y, w, h = caixa[:4]
    return [v[:4] for v in itens if v[5] and not caixa_categoria(v[5])
            and v[5][0] != 'separador'
            and x <= v[0] and v[0] + v[2] <= x + w + .01
            and y <= v[1] and v[1] + v[3] <= y + h + .01]


def realces_das_categorias(itens, acesos):
    chave = _gaveta_desenho._chave_widget
    for caixa in itens:
        if caixa_categoria(caixa[5]):
            # The outline belongs to TAB hover, not the empty background.
            acesos.discard(chave(caixa[5]))
            filhos = retangulos_filhos(caixa, itens)
            if any(v[:4] in filhos and chave(v[5]) in acesos for v in itens):
                acesos.add(chave(caixa[5]))


def widgets(context, largura, altura):
    """One image row. Only visible items become widgets/textures."""
    escala = max(1.0, context.preferences.system.ui_scale)
    w, h = largura / escala, altura / escala
    itens = []
    s = context.scene
    recolhida = bool(context.screen.get(CHAVE_RECOLHIDA))
    if recolhida:
        for i, (modo, nome) in enumerate(_gaveta.MODOS_BIBLIOTECA):
            itens.append((6 + i * 64, h - TOPO_CATEGORIA, 61, ALTURA_CATEGORIA, nome,
                          ('biblioteca', modo, s.cabinet_bib_modo == modo)))
    itens.append((max(6, w - 66), h - TOPO_CATEGORIA, 60, ALTURA_CATEGORIA,
                  "Expand" if recolhida else "Collapse",
                  ('operador', 'object.cabinet_recolher_biblioteca')))
    if recolhida:
        return [(x * escala, y * escala, bw * escala, bh * escala, nome, acao)
                for x, y, bw, bh, nome, acao in itens]
    linhas, daqui, prefixo = catalogo(context)
    capacidade = _capacidade_niveis(w)
    chave_niveis = _chave_niveis(context)
    limite_niveis = max(0, len(linhas) - 1 - capacidade)
    inicio_niveis = max(0, min(limite_niveis, int(context.screen.get(chave_niveis, limite_niveis))))
    visiveis = linhas[:1] + linhas[1 + inicio_niveis:1 + inicio_niveis + capacidade]
    modos = [nome for _modo, nome in _gaveta.MODOS_BIBLIOTECA]
    escolhido = dict(_gaveta.MODOS_BIBLIOTECA)[s.cabinet_bib_modo]
    grupos = [(0, modos, escolhido, None), *visiveis]
    # +1: the button moving the library into the menu (OP_LUGAR).
    ferramentas = 74 + 21 * (len(_gaveta.BOTOES_BIBLIOTECA[s.cabinet_bib_modo]) + 1)
    _subcategorias_em_linha(context, itens, grupos, w - ferramentas,
                           h - TOPO_CATEGORIA, prefixo)
    y = h - 35
    material = s.cabinet_bib_modo == 'MATERIAIS'
    reserva = 53 if material else 29
    disponivel = max(0, y - reserva)
    referencia = ALTURA_INICIAL - 35 - reserva
    tamanho = (68 + (s.chapa_tam_bloco - 2) * 14) * disponivel / referencia
    # Aspect ratio follows area height. Width must still fit alongside the arrows, even
    # in a tall, narrow library.
    lado = min(tamanho, disponivel, max(0, w - (74 if len(daqui) > 1 else 22)))
    if lado < 12:
        daqui = []   # Nearly collapsed strip: do not create targets outside the area.
    bw, bh = lado + 10, lado + 27
    caminho = repr(
        _biblioteca.trilha_da_cena(s) if s.cabinet_bib_modo == 'MODULOS'
        else (s.cabinet_mat_n1, s.cabinet_mat_n2, s.cabinet_mat_n3))
    chave = 'cabinet_faixa_itens_' + s.cabinet_bib_modo + '_' + hashlib.sha1(
        caminho.encode('utf-8')).hexdigest()[:20]
    rola = len(daqui) > max(1, int((w - 12 + 8 + 1e-6) // (bw + 8)))
    n = max(1, int((w - (64 if rola else 12) + 8 + 1e-6) // (bw + 8)))
    limite = max(0, len(daqui) - n)
    inicio = max(0, min(limite, int(context.screen.get(chave, 0))))
    by = y - bh
    if inicio > 0:
        itens.append((8, by, 20, bh, '', ('rolar_nivel', chave, -1, limite)))
    if inicio < limite:
        itens.append((w - 28, by, 20, bh, '', ('rolar_nivel', chave, 1, limite)))
    aplicada = _materiais.chave_aplicada(_gaveta._selecionado(context))
    for i, it in enumerate(daqui[inicio:inicio + n]):
        bx = (32 if rola else 6) + i * (bw + 8)
        acao = ('material', it, it['chave'] == aplicada) if material else ('preset', it)
        itens.append((bx, by, bw, bh, it.get('nome', ''), acao))
        if material:
            sw = (bw - 4) / 2
            for j, nome in enumerate(('Edit.', "Delete")):
                itens.append((bx + j * (sw + 4), by - 24, sw, 21, nome,
                              ('material_item', it, j)))
    # Catalog tools remain accessible without opening files during drawing.
    botoes = _gaveta.BOTOES_BIBLIOTECA[s.cabinet_bib_modo] + (("Location", OP_LUGAR),)
    for i, (nome, op) in enumerate(botoes):
        itens.append((w - 87 - i * 21, h - TOPO_CATEGORIA, 18, ALTURA_CATEGORIA,
                      nome, ('operador', op)))
    pergunta = _perguntas._pergunta_atual[0]
    if pergunta and pergunta.get('biblioteca'):
        caixa, _limite, _chave = _caixa_pergunta(context, w, h, pergunta)
        itens += caixa
    return [(x * escala, by * escala, bw * escala, bh * escala, nome, acao)
            for x, by, bw, bh, nome, acao in itens]


def interativos(context):
    itens = widgets(context, context.region.width, context.region.height)
    pergunta = next((v for v in itens if v[5] == ('pergunta',)), None)
    if pergunta:
        x, y, w, h = pergunta[:4]
        respostas = [v for v in itens if v[5] and v[5][0] == 'resposta']
        escala = max(1.0, context.preferences.system.ui_scale)
        fundo = _gaveta._recortar_ao_painel(pergunta, 4 * escala, context.region.height - 40 * escala)
        x, y, w, h = fundo[:4] if fundo else (0, 0, 0, 0)
        itens = respostas + ([fundo] if fundo else []) + [v for v in itens if not (
            v == pergunta or v in respostas or
            v[0] < x + w and x < v[0] + v[2] and v[1] < y + h and y < v[1] + v[3])]
    # The background does not intercept tab clicks. Its gizmo only serves empty space,
    # and the operator also handles it last.
    itens = [v for v in itens if not caixa_categoria(v[5])] + [v for v in itens if caixa_categoria(v[5])]
    return [v for v in itens if v[1] >= 0 and v[1] + v[3] <= context.region.height
            and v[0] >= 0 and v[0] + v[2] <= context.region.width]


def rolar(context, event):
    passo = -1 if event.type == 'WHEELUPMOUSE' else 1
    itens = widgets(context, context.region.width, context.region.height)
    escala = max(1.0, context.preferences.system.ui_scale)
    pergunta = _perguntas._pergunta_atual[0]
    if pergunta and pergunta.get('biblioteca'):
        _caixa, limite, chave = _caixa_pergunta(context, context.region.width / escala,
                                              context.region.height / escala, pergunta)
        context.screen[chave] = max(0, min(limite, int(context.screen.get(chave, 0)) + passo * 32))
        context.area.tag_redraw()
        return
    if getattr(event, 'shift', False):
        linhas, _itens, _p = catalogo(context)
        limite = max(0, len(linhas) - 1 - _capacidade_niveis(
            context.region.width / escala))
        chave = _chave_niveis(context)
        context.screen[chave] = max(0, min(limite, int(context.screen.get(chave, limite)) + passo))
        context.area.tag_redraw()
        return
    alvo = next((v[5] for v in itens if v[5] and v[5][0] in ('navegar', 'rolar_nivel')
                 and v[0] <= event.mouse_region_x <= v[0] + v[2]
                 and v[1] <= event.mouse_region_y <= v[1] + v[3]), None)
    if alvo is None:
        caixa = next((v for v in itens if caixa_categoria(v[5])
                      and v[0] <= event.mouse_region_x <= v[0] + v[2]
                      and v[1] <= event.mouse_region_y <= v[1] + v[3]), None)
        filhos = retangulos_filhos(caixa, itens) if caixa else []
        alvo = next((v[5] for v in itens if v[:4] in filhos
                     and v[5] and v[5][0] in ('navegar', 'rolar_nivel')), None)
    if alvo is None:
        # Over an image or the gap between images, scroll the entire gallery.
        alvo = next((v[5] for v in itens if v[5] and v[5][0] == 'rolar_nivel'
                     and 'faixa_itens' in v[5][1]
                     and v[1] <= event.mouse_region_y <= v[1] + v[3]), None)
    if alvo:
        chave, limite = (alvo[3], alvo[4]) if alvo[0] == 'navegar' else (alvo[1], alvo[3])
        context.screen[chave] = max(0, min(limite, int(context.screen.get(chave, 0)) + passo))
    context.area.tag_redraw()


def _chave_niveis(context):
    s = context.scene
    caminho = _biblioteca.trilha_da_cena(s) if s.cabinet_bib_modo == 'MODULOS' else (
        s.cabinet_mat_n1, s.cabinet_mat_n2, s.cabinet_mat_n3)
    return 'cabinet_faixa_niveis_' + hashlib.sha1(repr(caminho).encode('utf-8')).hexdigest()[:20]


def _capacidade_niveis(largura):
    return max(1, int((largura - 137 - 12 - 112) // (56 + INTERVALO_NIVEIS)) - 1)


def opcoes_do_item(it):
    protegido = bool(it.get('fabrica'))
    bloqueado = _biblioteca.item_bloqueado(it) or protegido
    return (("Insert", 'IMPORT', True),
            ("Edit", 'GREASEPENCIL', not bloqueado),
            ("Unlock" if bloqueado else "Lock",
             'LOCKED' if bloqueado else 'UNLOCKED', not protegido))


def abrir_menu_item(context, it):
    """Requested context menu for BOTH image and name, only on RELEASE."""
    if not _perguntas._abrir_pergunta(context):
        return False
    # Capture values, not the modal operator that will be cleared on completion.
    pasta, arquivo = it['pasta'], it['arquivo']
    opcoes = opcoes_do_item(it)
    def desenhar(menu, _context):
        menu.layout.operator_context = 'INVOKE_DEFAULT'
        for indice, (rotulo, icone, habilitado) in enumerate(opcoes):
            linha = menu.layout.row()
            linha.enabled = habilitado
            op = linha.operator('object.cabinet_acao_item_biblioteca', text=rotulo, icon=icone)
            op.pasta, op.arquivo, op.indice = pasta, arquivo, indice
    context.window_manager.popup_menu(desenhar, title=it.get('nome', "Cabinet"))
    return True


class OBJECT_OT_acao_item_biblioteca(Operator):
    bl_idname = 'object.cabinet_acao_item_biblioteca'
    bl_label = "Library Item Action"
    bl_options = {'INTERNAL'}
    pasta: StringProperty(options={'SKIP_SAVE'})
    arquivo: StringProperty(options={'SKIP_SAVE'})
    indice: IntProperty(min=0, max=2, options={'SKIP_SAVE'})

    def execute(self, context):
        # Recheck: lock state may change while the menu is open.
        it = _indice(False)['por_arquivo'].get((self.pasta, self.arquivo))
        if it is None:
            self.report({'WARNING'}, "Item removed from library")
            return {'CANCELLED'}
        if not opcoes_do_item(it)[self.indice][2]:
            self.report({'WARNING'}, "Model is protected or locked")
            return {'CANCELLED'}
        if _gaveta_eventos._eh_modelo_do_criador(it):
            if _gaveta_eventos._modelo_do_criador(self, context, it, self.indice):
                _editor.executar(context, 'object.cabinet_posicionar_puxador')
            return {'FINISHED'}
        props = dict(pasta=self.pasta, arquivo=self.arquivo)
        if self.indice == 0:
            return bpy.ops.object.cabinet_inserir_preset(tipo=it.get('tipo', 'modulo'), **props)
        if self.indice == 1:
            _editor.executar(context, 'object.cabinet_editar_modelo', **props)
            return {'FINISHED'}
        return bpy.ops.object.cabinet_bloqueio(**props)


def _caixa_pergunta(context, w, h, pergunta):
    caixa = []
    _gaveta._pergunta_na_gaveta(caixa, 8, h - 40, max(100, w - 16), pergunta)
    limite = max(0, caixa[0][3] - (h - 44))
    assinatura = pergunta['texto'] + repr([op[0] for op in pergunta['opcoes']])
    chave = 'cabinet_faixa_pergunta_' + hashlib.sha1(assinatura.encode('utf-8')).hexdigest()[:20]
    offset = max(0, min(limite, int(context.screen.get(chave, 0))))
    return [(x, y + offset, bw, bh, nome, acao) for x, y, bw, bh, nome, acao in caixa], limite, chave


def redimensionar_altura(context, desejada, mouse=None):
    _alturas[0][context.screen.name] = dict(altura=desejada, mouse=mouse, tiques=0, warp=False,
                                         recolhida_antes=bool(context.screen.get(CHAVE_RECOLHIDA)))
    if not bpy.app.timers.is_registered(_ajustar_alturas):
        bpy.app.timers.register(_ajustar_alturas, first_interval=0.02)


def _mover_cursor(janela, x, y):
    # The simulator uses virtual events: never move the user's real mouse in background
    # test windows.
    if bpy.app.use_event_simulate:
        janela.event_simulate('MOUSEMOVE', 'NOTHING', x=int(x), y=int(y))
    else:
        janela.cursor_warp(int(x), int(y))


def _cancelar_altura(janela):
    estado = _alturas[0].pop(janela.screen.name, None)
    if estado and estado['warp'] and estado['mouse']:
        _mover_cursor(janela, *estado['mouse'])


def _ajustar_alturas():
    for janela in bpy.context.window_manager.windows:
        estado = _alturas[0].get(janela.screen.name)
        if estado is None:
            continue
        area = area_da_faixa(janela.screen)
        if area is None:
            _alturas[0].pop(janela.screen.name, None)
            continue
        estado['tiques'] += 1
        with bpy.context.temp_override(window=janela, area=area, region=None):
            if bpy.ops.screen.area_move.poll():
                bpy.ops.screen.area_move(x=area.x + area.width // 2, y=area.y,
                                         delta=int(area.height - estado['altura']))
                if estado['warp'] and estado['mouse']:
                    _mover_cursor(janela, *estado['mouse'])
                _alturas[0].pop(janela.screen.name, None)
                area.tag_redraw()
            elif not estado['warp'] and estado['mouse']:
                # Native poll requires the mouse on the boundary (active_region is
                # null). Deferring allows movement to be processed and the mouse
                # restored to the button immediately after resizing.
                _mover_cursor(janela, area.x + area.width // 2, area.y)
                estado['warp'] = True
            elif estado['tiques'] > 20:
                if estado['warp'] and estado['mouse']:
                    _mover_cursor(janela, *estado['mouse'])
                janela.screen[CHAVE_RECOLHIDA] = estado['recolhida_antes']
                _alturas[0].pop(janela.screen.name, None)
                print("[Archy Builder] move the native border to adjust height")
    return 0.02 if _alturas[0] else None


class OBJECT_OT_recolher_biblioteca(Operator):
    bl_idname = 'object.cabinet_recolher_biblioteca'
    bl_label = "Collapse or Expand Library"

    @classmethod
    def poll(cls, context):
        return area_da_faixa(context.screen) is not None

    def invoke(self, context, event):
        self._mouse = (event.mouse_x, event.mouse_y)
        return self.execute(context)

    def execute(self, context):
        screen = context.screen
        area = area_da_faixa(screen)
        recolhida = bool(screen.get(CHAVE_RECOLHIDA))
        if not recolhida:
            screen[CHAVE_ALTURA] = area.height
        desejada = float(screen.get(CHAVE_ALTURA, ALTURA_INICIAL)) if recolhida else 30 * max(
            1.0, context.preferences.system.ui_scale)
        redimensionar_altura(context, desejada, getattr(self, '_mouse', None))
        screen[CHAVE_RECOLHIDA] = not recolhida
        area.tag_redraw()
        return {'FINISHED'}
