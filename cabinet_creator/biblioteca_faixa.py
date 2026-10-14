"""Biblioteca horizontal acima do menu e da cena, com areas nativas.

O split termina no tique seguinte: cada etapa guarda so' nomes e valores,
nunca referencias de areas que o Blender pode destruir ao fechar/juntar.
"""
import os
import time
import hashlib
import bpy
import blf
from bpy.types import Operator
from bpy.props import StringProperty, IntProperty

_gaveta = _gaveta_eventos = _biblioteca = _materiais = _perguntas = None
CHAVE_AREA = 'cabinet_biblioteca_area'
CHAVE_CENA = 'cabinet_viewport_area'
CHAVE_LAYOUT = 'cabinet_layout'
CHAVE_RECOLHIDA = 'cabinet_biblioteca_recolhida'
CHAVE_ALTURA = 'cabinet_biblioteca_altura'
_pendentes = [{}]
_catalogos = [{}]
_alturas = [{}]
ALTURA_INICIAL = 180
ALTURA_CATEGORIA = 18
PASSO_CATEGORIA = 20
TOPO_CATEGORIA = 23
ALTURA_COMPACTA = 160
INTERVALO_NIVEIS = 24


def area_da_faixa(screen):
    ptr = int(screen.get(CHAVE_AREA, 0)) if screen else 0
    return next((a for a in screen.areas if a.type == 'VIEW_3D'
                 and a.as_pointer() == ptr), None) if screen else None


def eh_faixa(context):
    area = getattr(context, 'area', None)
    return area is not None and area == area_da_faixa(getattr(context, 'screen', None))


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
    espaco = area.spaces.active
    for nome in ('show_region_ui', 'show_region_toolbar', 'show_region_header',
                 'show_region_tool_header', 'show_region_hud', 'show_gizmo_context',
                 'show_gizmo_tool', 'show_gizmo_navigate'):
        setattr(espaco, nome, False)
    espaco.show_gizmo = True
    espaco.overlay.show_overlays = False
    area.tag_redraw()


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
        # A area_close so' junta o menu com o vizinho da mesma altura.
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
    for janela in bpy.context.window_manager.windows:
        screen = janela.screen
        estado = _pendentes[0].get(screen.name)
        if estado is None:
            continue
        estado['tentativas'] += 1
        if estado['tentativas'] > 100:
            print('[Cabinet Creator] nao foi possivel preparar a biblioteca superior')
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
            screen[CHAVE_AREA] = str(topo.as_pointer())
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
        configurar_interface(menu)
        screen[_gaveta._CHAVE_GAVETA] = str(menu.as_pointer())
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
    if screen.get(CHAVE_LAYOUT) != 2:
        return
    ocultas = [a for a in screen.areas if a.type == 'VIEW_3D'
               and not a.spaces.active.show_region_header
               and not a.spaces.active.overlay.show_overlays]
    # A largura so' descreve o menu antigo; a faixa inteira e' mais larga.
    if area_da_faixa(screen) is None and len(ocultas) == 2:
        topo = max(ocultas, key=lambda a: a.y)
        menu = next(a for a in ocultas if a != topo)
        if topo.y >= menu.y + menu.height - 5 and topo.width > menu.width:
            screen[CHAVE_AREA] = str(topo.as_pointer())
            screen[_gaveta._CHAVE_GAVETA] = str(menu.as_pointer())
    cena = viewport(screen)
    if cena is not None:
        screen[CHAVE_CENA] = str(cena.as_pointer())


def esquecer():
    _pendentes[0].clear()
    _catalogos[0].clear()
    for janela in bpy.context.window_manager.windows:
        _cancelar_altura(janela)
    _alturas[0].clear()
    if bpy.app.timers.is_registered(_ajustar_alturas):
        bpy.app.timers.unregister(_ajustar_alturas)
    if bpy.app.timers.is_registered(configurar_pendentes):
        bpy.app.timers.unregister(configurar_pendentes)


def _linha(context, itens, x, y, w, valores, nivel, selecionado, pai=None,
           prefixo='cabinet_carrossel'):
    if not valores or w < 50:
        return
    chave = '%s_%d_%s' % (prefixo, nivel, str(pai))
    if len(chave.encode('utf-8')) > 63:
        chave = prefixo + '_' + hashlib.sha1(chave.encode('utf-8')).hexdigest()[:24]
    ordenados = sorted(valores, key=str.casefold)
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
    # Medir o fim tambem: nomes de larguras diferentes nao podem deixar
    # a ultima categoria fora do alcance da seta/roda.
    limite = max(0, len(ordenados) - len(cabem(0, espaco, inverso=True))) if rola else 0
    inicio = max(0, min(limite, int(context.screen.get(chave, 0))))
    fatia = cabem(inicio, espaco) if rola else completa
    if inicio > 0:
        itens.append((x, y, 14, ALTURA_CATEGORIA, '', ('rolar_nivel', chave, -1, limite)))
    if inicio + len(fatia) < len(ordenados):
        itens.append((x + w - 14, y, 14, ALTURA_CATEGORIA, '', ('rolar_nivel', chave, 1, limite)))
    bx = x + 17 if rola else x
    for valor, bw in fatia:
        itens.append((bx, y, bw, ALTURA_CATEGORIA, valor,
                      ('navegar', nivel, valor, chave, limite, valor == selecionado)))
        bx += bw + 2


def invalidar():
    _catalogos[0].clear()


def _indice(materiais):
    pasta = _biblioteca.pasta_biblioteca()
    leitor = _materiais.ler_materiais if materiais else _biblioteca.indice_completo
    chave = (pasta, materiais, id(leitor), id(_biblioteca.itens_de_fabrica))
    agora = time.monotonic()
    guardado = _catalogos[0].get(chave)
    # Nem JSON nem milhares de caminhos nem stat em rede a cada redraw.
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
    """Cada nivel conserva seu carrossel; o vao separa os grupos de abas."""
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
        desejadas.append(max(50, min(livre, usado)))
    tamanhos = [0] * len(linhas)
    pendentes = list(range(len(linhas)))
    restante = livre
    # Os niveis curtos nao desperdicam uma coluna inteira; a sobra fica
    # para os que precisam rolar, sem esmagar o nivel vizinho.
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
            itens.append((x - INTERVALO_NIVEIS / 2, y + 3, 1,
                          ALTURA_CATEGORIA - 6, '', ('separador',)))
        _linha(context, itens, x, y, w, filhos, nivel, escolhido, pai, prefixo)
        x += w + INTERVALO_NIVEIS


def widgets(context, largura, altura):
    """Uma fila de fotos. So' os itens visiveis viram widgets/texturas."""
    escala = max(1.0, context.preferences.system.ui_scale)
    w, h = largura / escala, altura / escala
    itens = []
    s = context.scene
    for i, (modo, nome) in enumerate(_gaveta.MODOS_BIBLIOTECA):
        itens.append((6 + i * 64, h - TOPO_CATEGORIA, 61, ALTURA_CATEGORIA, nome,
                      ('biblioteca', modo, s.cabinet_bib_modo == modo)))
    recolhida = bool(context.screen.get(CHAVE_RECOLHIDA))
    itens.append((max(6, w - 66), h - TOPO_CATEGORIA, 60, ALTURA_CATEGORIA,
                  'Expandir' if recolhida else 'Recolher',
                  ('operador', 'object.cabinet_recolher_biblioteca')))
    if recolhida:
        return [(x * escala, y * escala, bw * escala, bh * escala, nome, acao)
                for x, y, bw, bh, nome, acao in itens]
    linhas, daqui, prefixo = catalogo(context)
    compacto = h < ALTURA_COMPACTA
    capacidade = _capacidade_niveis(h, w)
    chave_niveis = _chave_niveis(context)
    limite_niveis = max(0, len(linhas) - 1 - capacidade)
    inicio_niveis = max(0, min(limite_niveis, int(context.screen.get(chave_niveis, limite_niveis))))
    visiveis = linhas[:1] + linhas[1 + inicio_niveis:1 + inicio_niveis + capacidade]
    for i, (nivel, filhos, escolhido, pai) in enumerate(visiveis[:1] if compacto else visiveis):
        y = h - TOPO_CATEGORIA - PASSO_CATEGORIA * i
        x = 140 if i == 0 else 6
        disponivel = w - x - (74 + 21 * len(_gaveta.BOTOES_BIBLIOTECA[s.cabinet_bib_modo])
                               if i == 0 else 6)
        _linha(context, itens, x, y, disponivel, filhos, nivel, escolhido, pai, prefixo)
    if compacto:
        _subcategorias_em_linha(context, itens, visiveis[1:], w,
                               h - TOPO_CATEGORIA - PASSO_CATEGORIA, prefixo)
    filas = min(2, len(visiveis)) if compacto else len(visiveis)
    y = h - 27 - PASSO_CATEGORIA * (max(1, filas) - 1)
    material = s.cabinet_bib_modo == 'MATERIAIS'
    lado = min(68 + (s.chapa_tam_bloco - 2) * 14, max(0, y - (53 if material else 29)))
    if lado < 12:
        daqui = []   # faixa quase recolhida: nao criar alvos fora da area
    bw, bh = lado + 10, lado + 27
    caminho = repr(
        _biblioteca.trilha_da_cena(s) if s.cabinet_bib_modo == 'MODULOS'
        else (s.cabinet_mat_n1, s.cabinet_mat_n2, s.cabinet_mat_n3))
    chave = 'cabinet_faixa_itens_' + s.cabinet_bib_modo + '_' + hashlib.sha1(
        caminho.encode('utf-8')).hexdigest()[:20]
    rola = len(daqui) > max(1, int((w - 12 + 8) // (bw + 8)))
    n = max(1, int((w - (64 if rola else 12) + 8) // (bw + 8)))
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
            for j, nome in enumerate(('Edit.', 'Apagar')):
                itens.append((bx + j * (sw + 4), by - 24, sw, 21, nome,
                              ('material_item', it, j)))
    # Ferramentas do catalogo permanecem acessiveis, sem abrir arquivos no draw.
    botoes = _gaveta.BOTOES_BIBLIOTECA[s.cabinet_bib_modo]
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
            context.region.height / escala, context.region.width / escala))
        chave = _chave_niveis(context)
        context.screen[chave] = max(0, min(limite, int(context.screen.get(chave, limite)) + passo))
        context.area.tag_redraw()
        return
    alvo = next((v[5] for v in itens if v[5] and v[5][0] in ('navegar', 'rolar_nivel')
                 and v[0] <= event.mouse_region_x <= v[0] + v[2]
                 and v[1] <= event.mouse_region_y <= v[1] + v[3]), None)
    if alvo is None:
        # Sobre a foto ou o vao entre fotos, rola a galeria inteira.
        alvo = next((v[5] for v in itens if v[5] and v[5][0] == 'rolar_nivel'
                     and 'faixa_itens' in v[5][1]
                     and v[1] <= event.mouse_region_y <= v[1] + v[3]), None)
    if alvo:
        chave, limite = (alvo[3], alvo[4]) if alvo[0] == 'navegar' else (alvo[1], alvo[3])
        context.screen[chave] = max(0, min(limite, int(context.screen.get(chave, 0)) + passo))
    else:
        pass
    context.area.tag_redraw()


def _chave_niveis(context):
    s = context.scene
    caminho = _biblioteca.trilha_da_cena(s) if s.cabinet_bib_modo == 'MODULOS' else (
        s.cabinet_mat_n1, s.cabinet_mat_n2, s.cabinet_mat_n3)
    return 'cabinet_faixa_niveis_' + hashlib.sha1(repr(caminho).encode('utf-8')).hexdigest()[:20]


def _capacidade_niveis(altura, largura=None):
    if altura < ALTURA_COMPACTA and largura is not None:
        return max(1, int((largura - 12 + INTERVALO_NIVEIS) // (80 + INTERVALO_NIVEIS)))
    # Reserva uma foto e o nome; materiais ainda tem Editar/Apagar abaixo.
    return max(1, int((altura - 112) // PASSO_CATEGORIA))


def opcoes_do_item(it):
    protegido = bool(it.get('fabrica'))
    bloqueado = _biblioteca.item_bloqueado(it) or protegido
    return (('Inserir', 'IMPORT', True),
            ('Editar', 'GREASEPENCIL', not bloqueado),
            ('Desbloquear' if bloqueado else 'Bloquear',
             'LOCKED' if bloqueado else 'UNLOCKED', not protegido))


def abrir_menu_item(context, it):
    """Menu contextual solicitado para foto E nome, somente no RELEASE."""
    if not _perguntas._abrir_pergunta(context):
        return False
    # Capturar valores, nao o operador modal que sera' limpo ao terminar.
    pasta, arquivo = it['pasta'], it['arquivo']
    opcoes = opcoes_do_item(it)
    def desenhar(menu, _context):
        menu.layout.operator_context = 'INVOKE_DEFAULT'
        for indice, (rotulo, icone, habilitado) in enumerate(opcoes):
            linha = menu.layout.row()
            linha.enabled = habilitado
            op = linha.operator('object.cabinet_acao_item_biblioteca', text=rotulo, icon=icone)
            op.pasta, op.arquivo, op.indice = pasta, arquivo, indice
    context.window_manager.popup_menu(desenhar, title=it.get('nome', 'Modulo'))
    return True


class OBJECT_OT_acao_item_biblioteca(Operator):
    bl_idname = 'object.cabinet_acao_item_biblioteca'
    bl_label = 'Acao do Item da Biblioteca'
    bl_options = {'INTERNAL'}
    pasta: StringProperty(options={'SKIP_SAVE'})
    arquivo: StringProperty(options={'SKIP_SAVE'})
    indice: IntProperty(min=0, max=2, options={'SKIP_SAVE'})

    def execute(self, context):
        # Reconsultar: o bloqueio pode mudar enquanto o menu esta' aberto.
        it = _indice(False)['por_arquivo'].get((self.pasta, self.arquivo))
        if it is None:
            self.report({'WARNING'}, 'Item removido da biblioteca')
            return {'CANCELLED'}
        if not opcoes_do_item(it)[self.indice][2]:
            self.report({'WARNING'}, 'Modelo protegido ou bloqueado')
            return {'CANCELLED'}
        if _gaveta_eventos._eh_modelo_do_criador(it):
            if _gaveta_eventos._modelo_do_criador(self, context, it, self.indice):
                bpy.ops.object.cabinet_posicionar_puxador('INVOKE_DEFAULT')
            return {'FINISHED'}
        props = dict(pasta=self.pasta, arquivo=self.arquivo)
        if self.indice == 0:
            return bpy.ops.object.cabinet_inserir_preset(tipo=it.get('tipo', 'modulo'), **props)
        if self.indice == 1:
            bpy.ops.object.cabinet_editar_modelo('INVOKE_DEFAULT', **props)
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
    # O simulador usa eventos virtuais: nunca mover o mouse real do
    # usuario nas janelas de teste que ficam em segundo plano.
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
                # O poll nativo exige mouse na fronteira (active_region
                # nula). Deferir permite processar o movimento e restaurar
                # imediatamente o mouse ao botao depois do resize.
                _mover_cursor(janela, area.x + area.width // 2, area.y)
                estado['warp'] = True
            elif estado['tiques'] > 20:
                if estado['warp'] and estado['mouse']:
                    _mover_cursor(janela, *estado['mouse'])
                janela.screen[CHAVE_RECOLHIDA] = estado['recolhida_antes']
                _alturas[0].pop(janela.screen.name, None)
                print('[Cabinet Creator] mova a fronteira nativa para ajustar a altura')
    return 0.02 if _alturas[0] else None


class OBJECT_OT_recolher_biblioteca(Operator):
    bl_idname = 'object.cabinet_recolher_biblioteca'
    bl_label = 'Recolher ou Expandir Biblioteca'

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
