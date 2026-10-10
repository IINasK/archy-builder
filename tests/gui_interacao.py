"""Testes de INTERFACE: cliques e teclas simulados numa janela de verdade.

Execute pelo executor (abre o Blender com janela, ~1 min):
    blender --background --factory-startup --python tests/rodar_testes.py -- --gui --suites gui_interacao

Cobre o que os testes headless nao alcancam: keymap real, gizmos com
hover, modais recebendo a sequencia real de eventos. Foi um furo desses
(o 2o clique do duplo chega como PRESS) que deixou o duplo clique na
foto quebrado sem nenhum teste acusar.
"""
import math
import os
import sys
import time

import bpy
from mathutils import Euler, Vector
from mathutils.geometry import intersect_line_plane
from bpy_extras import view3d_utils

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import cabinet_creator as addon  # noqa: E402
from harness_gui import (rodar, esperar, viewport_principal, na_tela,  # noqa: E402
                         Pular)


# ------------------------------------------------------------- apoio
def gaveta(janela):
    area = addon.gaveta._area_gaveta(janela.screen)
    assert area is not None, 'a gaveta nao abriu'
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def contexto(janela, area, regiao):
    return bpy.context.temp_override(window=janela, screen=janela.screen,
                                     area=area, region=regiao)


def viewport(janela):
    return viewport_principal(janela, addon.gaveta._area_gaveta(janela.screen))


def widget(janela, teste):
    """Centro, em coordenadas da janela, do widget CLICAVEL da gaveta
    para o qual teste(v) e' verdadeiro."""
    area, regiao = gaveta(janela)
    with contexto(janela, area, regiao):
        widgets = addon.gaveta._widgets_interativos(bpy.context)
    v = next((v for v in widgets if v[5] and teste(v)), None)
    assert v is not None, 'widget nao encontrado na gaveta'
    x, y, w, h = v[:4]
    return regiao.x + x + w / 2, regiao.y + y + h / 2


def criar_modulo(janela):
    area, regiao, _ = viewport(janela)
    with contexto(janela, area, regiao):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar()
    conj = next(o for o in bpy.data.objects if addon.chapas.MARCA_CONJUNTO in o)
    bpy.context.view_layer.update()
    return conj


def selecionar(janela, chapa, individual=False):
    area, regiao, _ = viewport(janela)
    with contexto(janela, area, regiao):
        addon.hud._selecionar_chapa_hud(bpy.context, chapa, individual=individual)


def caixa_mundo(objetos):
    pts = [o.matrix_world @ Vector(c) for o in objetos
           if o.type == 'MESH' for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def widget_titulo(janela):
    """Centro do titulo "Biblioteca (n)" (decoracao, sem acao)."""
    area, regiao = gaveta(janela)
    with contexto(janela, area, regiao):
        _c, conteudo, _r = addon.gaveta._partes_gaveta(addon.gaveta._widgets_gaveta(
            bpy.context, regiao.width, regiao.height))
    titulo = addon.gaveta._paineis_gaveta(conteudo)[2][0]
    assert titulo[4].startswith('Biblioteca'), titulo
    x, y, w, h = titulo[:4]
    return regiao.x + x + w / 2, regiao.y + y + h / 2


def exigir_biblioteca_legivel():
    """Os presets foram gravados pelo Blender 5.x, cujo formato de .blend
    o 4.x nao le ("not a blend file"). Ali o teste do CLIQUE nao tem
    o que provar: a falha e' do arquivo, registrada a parte."""
    if bpy.app.version < (5, 0, 0):
        raise Pular('biblioteca em formato .blend do 5.x: o %s nao le'
                    % bpy.app.version_string)


def mostrar_chapas_na_biblioteca(cena):
    cena.chapa_n1 = 'Chapas'
    cena.chapa_n2 = (addon.biblioteca._filhos_n2('Chapas') or [''])[0]
    cena.chapa_n3 = ''


def preparar(janela):
    addon.register()
    area, regiao, _ = viewport_principal(janela)
    with contexto(janela, area, regiao):
        bpy.ops.object.cabinet_alternar_gaveta()


def limpar(janela):
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    cena = bpy.context.scene
    cena.cabinet_aba = 'MODULOS'
    cena.cursor.location = (0.0, 0.0, 0.0)
    for nome in addon.portas._PROPS_PORTAS_CENA:
        cena.property_unset(nome)
    cena.chapa_n1, cena.chapa_n2, cena.chapa_n3 = 'Armarios', '', ''
    tela = janela.screen
    for chave in (addon.gaveta._CHAVE_ROLAGEM, addon.gaveta._CHAVE_ROLAGEM_BIB,
                  addon.gaveta._CHAVE_DIVISA, addon.gaveta._CHAVE_OPCOES):
        tela.pop(chave, None)
    addon.hud._hover_hud.clear()
    addon.portas_viewport._arraste_canto_porta[0] = None
    addon.portas_viewport._arraste_slider_porta[0] = None
    addon.hud._edicao_hud[0] = None
    addon.solda._tecla_corrente_segurada[0] = False
    addon.solda._conexao_pendente[0] = None
    addon.solda._desagregar_pendente[0] = None
    addon.solda._pergunta_reset[0] = ''
    addon.perguntas._pergunta_atual[0] = None
    addon.solda._arraste_ancora[0] = None


# ------------------------------------------------------------ testes
def test_gaveta_abre_na_largura_com_medidas_em_linha(janela, m):
    yield esperar(0.3)
    area, regiao = gaveta(janela)
    alvo = addon.gaveta._largura_inicial_gaveta(bpy.context)
    assert abs(area.width - alvo) <= 3, (area.width, alvo)
    conj = criar_modulo(janela)
    selecionar(janela, addon.modulos._chapas_do_conjunto(conj)[0])
    yield
    with contexto(janela, area, regiao):
        medidas = [v for v in addon.gaveta._widgets_gaveta(
            bpy.context, regiao.width, regiao.height)
            if v[5] and v[5][0] == 'medida']
    assert len(medidas) == 4 and len({v[1] for v in medidas}) == 1, \
        'L/A/P/E nao ficaram na mesma linha: %r' % [v[:4] for v in medidas]


def test_clique_na_aba_troca_a_aba(janela, m):
    m.mover(*widget(janela, lambda v: v[5] == ('aba', 'PORTAS')))
    yield
    m.clicar()
    yield
    assert bpy.context.scene.cabinet_aba == 'PORTAS'
    m.mover(*widget(janela, lambda v: v[5] == ('aba', 'MODULOS')))
    yield
    m.clicar()
    yield
    assert bpy.context.scene.cabinet_aba == 'MODULOS'


def test_arrastar_a_divisoria(janela, m):
    area, regiao = gaveta(janela)
    antes = addon.gaveta._divisa_gaveta(bpy.context, regiao.height)
    x, y = widget(janela, lambda v: v[5][0] == 'divisa')
    m.mover(x, y)
    yield
    m.apertar()
    yield
    for passo in range(1, 4):
        m.mover(x, y + 50 * passo)
        yield
    m.soltar()
    yield
    depois = addon.gaveta._divisa_gaveta(bpy.context, regiao.height)
    assert abs(depois - (antes + 150)) <= 2, (antes, depois)


def test_roda_rola_so_a_biblioteca(janela, m):
    area, regiao = gaveta(janela)
    janela.screen[addon.gaveta._CHAVE_DIVISA] = 0.1      # biblioteca baixinha
    yield
    with contexto(janela, area, regiao):
        _lim, lim_bib = addon.gaveta._limites_rolagem_gaveta(
            bpy.context, regiao.width, regiao.height)
    assert lim_bib > 0, 'biblioteca nao rola nem baixinha'
    # sobre o titulo "Biblioteca": em cima de um carrossel a roda
    # troca a categoria (rolagem propria dele), nao rola o painel
    m.mover(*widget_titulo(janela))
    yield
    m.clicar('WHEELDOWNMOUSE')
    yield
    assert janela.screen.get(addon.gaveta._CHAVE_ROLAGEM_BIB, 0) > 0
    assert janela.screen.get(addon.gaveta._CHAVE_ROLAGEM, 0) == 0


def test_duplo_clique_na_foto_insere_no_cursor(janela, m):
    exigir_biblioteca_legivel()
    cena = bpy.context.scene
    cena.cursor.location = (0.4, -0.2, 0.0)
    mostrar_chapas_na_biblioteca(cena)
    yield
    antes = set(bpy.data.objects)
    m.mover(*widget(janela, lambda v: v[5][0] == 'preset'))
    yield
    m.clicar()
    yield esperar(0.05)      # bem abaixo do tempo de duplo clique
    m.clicar()
    yield esperar(0.3)
    novos = [o for o in bpy.data.objects if o not in antes]
    assert novos, 'o duplo clique nao inseriu nada'
    assert all(not o.hide_get() for o in novos), 'ficou escondido (staging)'
    lo, hi = caixa_mundo(novos)
    base = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    assert (base - cena.cursor.location).length < 1e-4, (tuple(base),)


def test_clique_na_foto_e_depois_na_viewport_posiciona(janela, m):
    exigir_biblioteca_legivel()
    cena = bpy.context.scene
    mostrar_chapas_na_biblioteca(cena)
    yield
    antes = set(bpy.data.objects)
    m.mover(*widget(janela, lambda v: v[5][0] == 'preset'))
    yield
    m.clicar()
    yield esperar(0.6)       # passou do tempo de duplo: e' clique simples
    area, regiao, rv3d = viewport(janela)
    destino = Vector((1.0, 0.5, 0.0))
    x, y = na_tela(regiao, rv3d, destino)
    for t in (0.25, 0.5, 0.75, 1.0):
        m.mover(m.x + (x - m.x) * t, m.y + (y - m.y) * t)
        yield
    m.clicar()
    yield esperar(0.2)
    novos = [o for o in bpy.data.objects if o not in antes]
    assert novos, 'o posicionador nao inseriu nada'
    # onde o raio do mouse corta o plano do cursor (cena vazia)
    coord = (m.x - regiao.x, m.y - regiao.y)
    origem = view3d_utils.region_2d_to_origin_3d(regiao, rv3d, coord)
    direcao = view3d_utils.region_2d_to_vector_3d(regiao, rv3d, coord)
    esperado = intersect_line_plane(origem, origem + direcao * 1000,
                                    Vector((0, 0, 0)), Vector((0, 0, 1)))
    lo, hi = caixa_mundo(novos)
    base = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    assert (base - esperado).length < 2e-3, (tuple(base), tuple(esperado))


def test_clique_na_viewport_seleciona_o_modulo(janela, m):
    conj = criar_modulo(janela)
    bpy.ops.object.select_all(action='DESELECT')
    yield
    area, regiao, rv3d = viewport(janela)
    tampo = max(addon.modulos._chapas_do_conjunto(conj),
                key=lambda o: o.matrix_world.translation.z)
    m.mover(*na_tela(regiao, rv3d, tampo.matrix_world.translation))
    yield
    m.clicar()
    yield
    selecionados = set(bpy.context.selected_objects)
    assert selecionados == set(addon.selecao.familia_de(conj)), selecionados
    assert bpy.context.view_layer.objects.active == conj


def aproximar(janela, conj):
    """Vista centrada e perto do modulo: na vista de fabrica ele ocupa
    poucos pixels e a aresta fica dificil de mirar."""
    _area, _regiao, rv3d = viewport(janela)
    lo, hi = caixa_mundo(addon.modulos._chapas_do_conjunto(conj))
    rv3d.view_location = (lo + hi) / 2
    rv3d.view_distance = 2.2


def _linha_l(janela, conj):
    area, regiao, rv3d = viewport(janela)
    with contexto(janela, area, regiao):
        geometria = addon.hud._geometria_hud(bpy.context)
    for linha in (geometria or {}).get('linhas', []):
        if linha['tipo'] == 'medida' and linha['eixo'] == 0:
            a, b = (na_tela(regiao, rv3d, p) for p in linha['pontos'])
            if a and b and (Vector(b) - Vector(a)).length > 60:
                return geometria, linha, Vector(a), Vector(b)
    raise AssertionError('nenhuma linha L visivel o bastante: geometria=%s '
                         'linhas=%r' % (geometria is not None, [
                             (l['tipo'], l.get('eixo'), [na_tela(regiao, rv3d, p)
                                                          for p in l['pontos']])
                             for l in (geometria or {}).get('linhas', [])][:6]))


def test_arrastar_a_seta_da_hud_estica_com_a_quina_parada(janela, m):
    conj = criar_modulo(janela)
    selecionar(janela, addon.modulos._chapas_do_conjunto(conj)[0])
    aproximar(janela, conj)
    yield
    yield
    geometria, linha, a, b = _linha_l(janela, conj)
    fixa = geometria['cantos'][linha['cantos'][0]].copy()
    largura = conj.conj_largura_mm
    m.mover(*(a + (b - a) * 0.2))
    yield
    yield
    m.apertar()
    yield
    direcao = (b - a).normalized()
    inicio = Vector((m.x, m.y))
    for passo in range(1, 5):
        m.mover(*(inicio + direcao * 20 * passo))
        yield
    m.soltar()
    yield
    assert conj.conj_largura_mm > largura + 10, (largura, conj.conj_largura_mm)
    nova = addon.hud._geometria_do_item(conj, 'GRUPO',
                                    addon.modulos._chapas_do_conjunto(conj))
    assert (nova['cantos'][linha['cantos'][0]] - fixa).length < 1e-4


def test_clicar_na_seta_e_digitar_a_medida(janela, m):
    conj = criar_modulo(janela)
    selecionar(janela, addon.modulos._chapas_do_conjunto(conj)[0])
    aproximar(janela, conj)
    yield
    yield
    geometria, linha, a, b = _linha_l(janela, conj)
    fixa = geometria['cantos'][linha['cantos'][0]].copy()
    m.mover(*(a + (b - a) * 0.2))
    yield
    yield
    m.clicar()
    yield
    m.digitar('800')
    m.tecla('RET')
    yield
    assert abs(conj.conj_largura_mm - 800.0) < 1e-3, conj.conj_largura_mm
    nova = addon.hud._geometria_do_item(conj, 'GRUPO',
                                    addon.modulos._chapas_do_conjunto(conj))
    assert (nova['cantos'][linha['cantos'][0]] - fixa).length < 1e-4


def test_clique_dentro_do_campo_da_gaveta_move_o_cursor(janela, m):
    # O mesmo da HUD no campo da gaveta: clicar nele em edicao nao
    # confirma, leva o cursor; '+' com tudo selecionado continua a conta
    chapa = addon.chapas.nova_chapa('Campo', 600.0, 400.0, 18.0, (0, 0, 0),
                             (0, 0, 0), bpy.context)
    selecionar(janela, chapa, individual=True)
    yield
    campo = lambda v: v[5][0] == 'medida' and v[5][3] == 'Largura'
    cx, cy = widget(janela, campo)
    m.mover(cx, cy)
    yield
    m.clicar()
    yield
    estado = addon.gaveta._edicao_gaveta[0]
    assert estado is not None, 'o campo nao abriu'
    m.digitar('+50')
    yield
    assert estado['texto'].replace(' ', '').endswith('+50'), estado['texto']
    m.tecla('RET')
    yield
    assert abs(chapa.chapa_largura_mm - 650.0) < 1e-3, chapa.chapa_largura_mm
    m.mover(cx, cy)
    yield
    m.clicar()
    yield
    estado = addon.gaveta._edicao_gaveta[0]
    estado['texto'], estado['cursor'] = '650', 3
    area, regiao = gaveta(janela)
    with contexto(janela, area, regiao):
        x = next(v for v in addon.gaveta._widgets_interativos(bpy.context)
                 if v[5] and campo(v))[0]
    # logo depois do 6 (o texto comeca em x + 7)
    m.mover(regiao.x + x + 7 + addon.gaveta_desenho._medidor_blf(12)('6') + 1, cy)
    yield
    m.clicar()
    yield
    assert addon.gaveta._edicao_gaveta[0] is estado, 'o clique no campo fechou a edicao'
    assert estado['cursor'] == 1, estado['cursor']
    m.digitar('1')
    m.tecla('RET')
    yield
    assert abs(chapa.chapa_largura_mm - 6150.0) < 1e-3, chapa.chapa_largura_mm


def _nicho_com_lateral_afastada(janela, metros=0.2):
    conj = criar_modulo(janela)
    chapas = addon.modulos._chapas_do_conjunto(conj)
    direita = max(chapas, key=lambda o: o.matrix_world.translation.x)
    origem = direita.matrix_world.copy()
    direita.location.x += metros
    bpy.context.view_layer.update()
    area, regiao, rv3d = viewport(janela)
    rv3d.view_rotation = Euler((math.radians(70), 0,
                                math.radians(20))).to_quaternion()
    rv3d.view_location = (0.1, 0, 0.3)
    rv3d.view_distance = 2.6
    return conj, chapas, direita, origem


def test_resetar_pela_gaveta_move_a_chapa_ativa(janela, m):
    # Print do usuario: a lateral se afastou do nicho. Selecionada sozinha,
    # o botao regua da gaveta fica AZUL; o clique a devolve a solda.
    conj, chapas, direita, origem = _nicho_com_lateral_afastada(janela)
    selecionar(janela, direita, individual=True)
    yield
    yield
    regua = lambda v: v[5][:2] == ('operador', addon.solda.OP_RESETAR_DISTANCIA)
    area, regiao = gaveta(janela)
    with contexto(janela, area, regiao):
        botao = next(v for v in addon.gaveta._widgets_interativos(bpy.context)
                     if v[5] and regua(v))
    assert botao[5][2] is True, 'com a solda fora, o botao devia estar azul'
    m.mover(*widget(janela, regua))
    yield
    m.clicar()
    yield
    for a, b in zip(direita.matrix_world, origem):
        assert (a - b).length < 1e-5, 'a lateral nao voltou'
    assert addon.solda._pontas_fora_do_lugar(chapas) == [], 'soldas fora'


def test_regua_da_viewport_com_o_modulo_ativo_adapta_o_modulo(janela, m):
    # Alt: todas as quinas soldadas fora da origem, cada uma com corrente
    # e regua. Modulo ativo -> o MODULO se adapta a lateral (que fica).
    conj, chapas, direita, _origem = _nicho_com_lateral_afastada(janela)
    lateral = direita.matrix_world.copy()
    largura = conj.conj_largura_mm
    selecionar(janela, direita)                   # clique: o modulo
    area, regiao, rv3d = viewport(janela)
    yield
    yield
    m.janela.event_simulate('LEFT_ALT', 'PRESS', alt=True, x=m.x, y=m.y)
    yield
    with contexto(janela, area, regiao):
        correntes = addon.solda._correntes_hud(bpy.context)
        visiveis = [c for c in correntes if c['meio'] is not None]
        assert len(correntes) == 4, '%d quinas soldadas' % len(correntes)
        assert visiveis, 'nenhuma quina na tela'
        centro = addon.solda._botoes_da_corrente(bpy.context, visiveis[0])['regua']
    m.mover(regiao.x + centro.x, regiao.y + centro.y)
    yield
    yield
    m.clicar(alt=True)
    yield
    m.janela.event_simulate('LEFT_ALT', 'RELEASE', x=m.x, y=m.y)
    yield
    for a, b in zip(direita.matrix_world, lateral):
        assert (a - b).length < 1e-5, 'a lateral se mexeu (era o modulo)'
    assert addon.solda._pontas_fora_do_lugar(chapas) == [], 'soldas fora'
    assert abs(conj.conj_largura_mm - (largura + 200.0)) < 0.5, \
        conj.conj_largura_mm


def test_regua_que_muda_a_medida_pergunta_e_espera(janela, m):
    # Caso extremo: o tampo encolheu e, sozinho e ativo, so' volta a solda
    # da direita esticando. A regua pergunta "Mover mesmo assim?" e a
    # pergunta ESPERA: o soltar do proprio clique nao pode responder.
    conj, base, tampo = _caixote_aberto(janela)
    selecionar(janela, tampo, individual=True)
    area, regiao, rv3d = viewport(janela)
    rv3d.view_rotation = Euler((math.radians(70), 0,
                                math.radians(35))).to_quaternion()
    rv3d.view_location = (0.0, 0, 0.25)
    rv3d.view_distance = 2.2
    yield
    yield
    largura = tampo.chapa_largura_mm
    m.janela.event_simulate('LEFT_ALT', 'PRESS', alt=True, x=m.x, y=m.y)
    yield
    with contexto(janela, area, regiao):
        correntes = [c for c in addon.solda._correntes_hud(bpy.context)
                     if c['meio'] is not None]
        assert correntes and all(c['movel'] == tampo for c in correntes),             [c['movel'].name for c in correntes]
        centro = addon.solda._botoes_da_corrente(bpy.context, correntes[0])['regua']
    m.mover(regiao.x + centro.x, regiao.y + centro.y)
    yield
    yield
    m.clicar(alt=True)
    yield
    m.janela.event_simulate('LEFT_ALT', 'RELEASE', x=m.x, y=m.y)
    yield
    assert addon.solda._pergunta_reset[0] == tampo.name, 'nao perguntou'
    assert abs(tampo.chapa_largura_mm - largura) < 1e-6, \
        'o soltar do clique respondeu a pergunta sozinho'
    # veio da VIEWPORT (regua): essa sim e' pop-up
    assert not addon.perguntas._pergunta_atual[0]['na_gaveta'], 'regua devia ser pop-up'
    m.tecla('ESC')                               # fecha o pop-up
    yield
    with contexto(janela, area, regiao):
        assert bpy.ops.object.cabinet_resetar_distancia(
            chapa=tampo.name, forcar=True) == {'FINISHED'}
    assert abs(tampo.chapa_largura_mm - (largura + 250.0)) < 0.01


def test_arrastar_a_bolinha_troca_a_ancora(janela, m):
    # Alt: bolinhas brancas nas pontas das linhas. Arrastar a do lado da
    # lateral ate' outro vertice dela troca a ancora (so' isso: a chapa
    # vai la' pela regua).
    conj, chapas, direita, _origem = _nicho_com_lateral_afastada(janela)
    selecionar(janela, direita)
    area, regiao, rv3d = viewport(janela)
    yield
    yield
    m.janela.event_simulate('LEFT_ALT', 'PRESS', alt=True, x=m.x, y=m.y)
    yield
    with contexto(janela, area, regiao):
        correntes = [c for c in addon.solda._correntes_hud(bpy.context)
                     if 'b' in addon.solda._bolinhas_da_corrente(bpy.context, c)]
        assert correntes, 'nenhuma bolinha na tela'
        corrente = correntes[0]
        inicio = addon.solda._bolinhas_da_corrente(bpy.context, corrente)['b']
    tampo, ponta, k = corrente['a'], corrente['ponta'], corrente['indice']
    antes = addon.solda._ancoras_da_ligacao(tampo, ponta, direita)[k]
    # destino: outro vertice da lateral, visivel na tela
    with contexto(janela, area, regiao):
        opcoes = []
        for a in '+-':
            for b in '+-':
                for c in '+-':
                    s = a + b + c
                    p = addon.hud._projetar_hud(bpy.context,
                                            addon.solda._vertice_da_assinatura(direita, s))
                    if s != antes[1] and p is not None and (p - inicio).length > 30:
                        opcoes.append((s, p))
    destino, alvo = opcoes[0]
    m.mover(regiao.x + inicio.x, regiao.y + inicio.y)
    yield
    yield
    m.apertar(alt=True)
    yield
    assert addon.solda._arraste_ancora[0] is not None, 'a bolinha nao comecou a arrastar'
    for passo in range(1, 6):
        ponto = inicio + (alvo - inicio) * (passo / 5)
        m.mover(regiao.x + ponto.x, regiao.y + ponto.y)
        yield
    m.soltar(alt=True)
    yield
    m.janela.event_simulate('LEFT_ALT', 'RELEASE', x=m.x, y=m.y)
    yield
    assert addon.solda._arraste_ancora[0] is None, 'o arraste nao terminou'
    gravadas = addon.solda._ancoras_gravadas(tampo, ponta)
    assert gravadas and gravadas[k] == (antes[0], destino), gravadas


def _wizard_ate_o_tipo(janela, m):
    """Modulo de frente, "Criar Portas" da gaveta e os 2 cantos internos
    da diagonal. Devolve (conj, area, regiao, rv3d)."""
    conj = criar_modulo(janela)
    area, regiao, rv3d = viewport(janela)
    rv3d.view_rotation = Euler((math.pi / 2, 0, 0)).to_quaternion()
    lo, hi = caixa_mundo(addon.modulos._chapas_do_conjunto(conj))
    rv3d.view_location = (lo + hi) / 2
    rv3d.view_distance = 1.6
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.scene.cabinet_aba = 'PORTAS'
    return conj, area, regiao, rv3d


def _cantos_internos(conj):
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    a = conj.matrix_world @ (Vector((-L / 2 + E, -P / 2, E)) / 1000.0)
    b = conj.matrix_world @ (Vector((L / 2 - E, -P / 2, A - E)) / 1000.0)
    return a, b


def _clicar_no_mundo(m, regiao, rv3d, ponto):
    m.mover(*na_tela(regiao, rv3d, ponto))
    yield
    m.clicar()
    yield


def _clicar_botao_do_wizard(m, regiao, chave):
    w = addon.portas._assistente_porta[0]
    (x, y, bw, bh), _c, _t = next(b for b in w['botoes'] if b[1] == chave)
    m.mover(regiao.x + x + bw / 2, regiao.y + y + bh / 2)
    yield
    m.clicar()
    yield


def _clicar_na_fila(janela, m, prop, valor):
    m.mover(*widget(janela, lambda v: v[5][0] == 'escolha'
                    and v[5][1] == prop and v[5][2] == valor))
    yield
    yield
    m.clicar()
    yield


def _local(conj, x, y, z):
    return conj.matrix_world @ (Vector((x, y, z)) / 1000.0)


def _filas_da_aba(janela):
    """Filas de escolha que a aba Portas mostra agora, de cima para baixo."""
    area, regiao = gaveta(janela)
    with contexto(janela, area, regiao):
        widgets = addon.gaveta._widgets_interativos(bpy.context)
    filas = []
    for v in sorted(widgets, key=lambda v: -v[1]):
        if v[5] and v[5][0] == 'escolha' and v[5][1] not in filas:
            filas.append(v[5][1])
    return filas


def _abrir_wizard(janela, m):
    m.mover(*widget(janela, lambda v: v[5][0] == 'portas'))
    yield
    m.clicar()
    yield
    assert addon.portas._assistente_porta[0] is not None, 'Criar Portas nao abriu'


def test_wizard_quatro_cliques_meia_chapa_vira_curva(janela, m):
    # Desenho do usuario: 1 = canto da porta, 2 = do vao, 3 = vao oposto,
    # 4 = porta oposta. Porta na METADE das duas laterais = Curva, sem
    # escolher dobradica. Depois: folhas, abertura, borda, qtd, margem.
    conj, area, regiao, rv3d = _wizard_ate_o_tipo(janela, m)
    yield
    yield
    yield from _abrir_wizard(janela, m)
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    y = -P / 2
    for ponto in ((-L / 2 + E / 2, y, A), (-L / 2 + E, y, A - E),
                  (L / 2 - E, y, E), (L / 2 - E / 2, y, 0)):
        yield from _clicar_no_mundo(m, regiao, rv3d, _local(conj, *ponto))
    w = addon.portas._assistente_porta[0]
    assert w['etapa'] == 'FOLHAS', w['etapa']
    assert [w['coberturas'][k] for k in addon.portas.COBERTURAS_LADOS] == [
        0.5, 0.5, 1.0, 1.0], w['coberturas']
    # a aba Portas mostra a COPIA da pergunta quando o wizard chega nela
    assert _filas_da_aba(janela) == ['porta_folhas'], _filas_da_aba(janela)
    yield from _clicar_botao_do_wizard(m, regiao, '1')
    assert w['etapa'] == 'TIPO', w['etapa']
    assert [c for _r, c, _t in w['botoes']] == ['GIRO', 'BASCULANTE']
    assert _filas_da_aba(janela) == ['porta_folhas', 'porta_abertura'],         _filas_da_aba(janela)
    yield from _clicar_botao_do_wizard(m, regiao, 'GIRO')
    assert _filas_da_aba(janela) == ['porta_folhas', 'porta_abertura']
    assert w['etapa'] == 'EIXO', w['etapa']
    esquerda = next(a for a in w['arestas'] if a['lado'] == 'ESQUERDA')
    meio = (esquerda['a'] + esquerda['b']) / 2
    m.mover(*na_tela(regiao, rv3d, w['matriz'] @ Vector(
        (meio.x / 1000.0, meio.y / 1000.0, 0))))
    yield
    yield
    assert w['snap'] and w['snap'][0]['lado'] == 'ESQUERDA', w['snap']
    assert 'Curva' in w['recado'], w['recado']
    m.clicar()
    yield
    assert w['etapa'] == 'QUANTIDADE', w['etapa']
    assert w['escolhas']['dobradica'] == 'CURVA'
    assert w['escolhas']['dobradica_lado'] == 'ESQUERDA'
    padrao = w['qtd']
    m.janela.event_simulate('WHEELUPMOUSE', 'PRESS', x=m.x, y=m.y)
    yield
    assert w['qtd'] == padrao + 1, (padrao, w['qtd'])
    m.clicar()
    yield
    assert w['etapa'] == 'MARGEM'
    for passo in range(1, 4):
        m.mover(m.x, m.y + 10 * passo)
        yield
    margem = w['margem']
    assert margem > addon.portas.MARGEM_DOBRADICAS_PADRAO, margem
    m.clicar()
    yield
    assert addon.portas._assistente_porta[0] is None, 'o wizard nao terminou'
    grupo = addon.portas._portas_do_conjunto(conj)[0]
    p = grupo['porta_parametros']
    assert p['dobradica'] == 'CURVA' and p['abertura'] == 'GIRO', dict(p)
    assert p['folhas'] == 1 and p['cobertura_esq_e'] == 0.5, dict(p)
    assert p['dobradicas_qtd'] == padrao + 1 and p['dobradica_lado'] == 'ESQUERDA'
    assert abs(p['dobradicas_margem_mm'] - margem) < 1e-3


def test_wizard_basculante_com_pistoes(janela, m):
    # Basculante: dobradicas SEMPRE em CIMA (sem perguntar a borda) e os
    # pistoes na posicao automatica; o mouse em Y so' os sobe (descer
    # passaria do curso). Quina de fora = Reta, automatica.
    conj, area, regiao, rv3d = _wizard_ate_o_tipo(janela, m)
    yield
    yield
    yield from _abrir_wizard(janela, m)
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    y = -P / 2
    for ponto in ((-L / 2, y, A), (-L / 2 + E, y, A - E),
                  (L / 2 - E, y, E), (L / 2, y, 0)):
        yield from _clicar_no_mundo(m, regiao, rv3d, _local(conj, *ponto))
    w = addon.portas._assistente_porta[0]
    # respondido pela COPIA da caixa na aba Portas (pedido do usuario);
    # responder de novo uma fila ja' respondida refaz dali
    yield from _clicar_na_fila(janela, m, 'porta_folhas', 1)
    assert w['etapa'] == 'TIPO', w['etapa']
    yield from _clicar_na_fila(janela, m, 'porta_abertura', 'GIRO')
    assert w['etapa'] == 'EIXO', w['etapa']
    yield from _clicar_na_fila(janela, m, 'porta_abertura', 'BASCULANTE')
    assert w['etapa'] == 'QUANTIDADE', w['etapa']
    assert w['escolhas']['abertura'] == 'BASCULANTE', w['escolhas']
    # dobradicas EDITAVEIS na gaveta (pedido do usuario): a quantidade
    # pelos segmentos (sem avancar a etapa) e o afastamento digitado
    yield from _clicar_na_fila(janela, m, 'dobradicas_qtd', 3)
    assert (w['qtd'], w['etapa']) == (3, 'QUANTIDADE'), (w['qtd'], w['etapa'])
    m.mover(*widget(janela, lambda v: v[5][0] == 'medida'
                    and v[5][2] == 'dobradicas_margem_mm'))
    yield
    m.clicar()
    yield
    m.digitar('80')
    m.tecla('RET')
    yield
    assert abs(w['margem'] - 80.0) < 1e-6, w['margem']
    m.mover(regiao.x + regiao.width / 2, regiao.y + regiao.height / 2)
    yield
    assert w['aresta']['lado'] == 'CIMA'
    assert w['escolhas']['dobradica_lado'] == 'CIMA', w['escolhas']
    assert w['escolhas']['dobradica'] == 'RETA', w['escolhas']
    m.clicar()                                   # quantidade (3)
    yield
    m.clicar()                                   # margem (a digitada)
    yield
    assert w['etapa'] == 'PISTOES_QTD', w['etapa']
    assert w['pqtd'] == addon.portas._qtd_pistoes_padrao(w['largura'])
    m.janela.event_simulate('WHEELUPMOUSE', 'PRESS', x=m.x, y=m.y)
    yield
    assert w['pqtd'] == 2
    m.clicar()
    yield
    assert w['etapa'] == 'PISTOES_OFFSET'
    inicial = w['poffset']
    assert abs(inicial - w['poffset_auto']) < 1e-6
    for passo in range(1, 4):
        m.mover(m.x, m.y - 8 * passo)             # descer: trava no curso
        yield
    assert abs(w['poffset'] - inicial) < 1e-6, (inicial, w['poffset'])
    assert 'curso maximo' in w['recado'], w['recado']
    for passo in range(1, 6):
        m.mover(m.x, m.y + 8 * passo)             # subir: o pistao sobe
        yield
    assert w['poffset'] < inicial - 1, (inicial, w['poffset'])
    offset = w['poffset']
    area_g, regiao_g = gaveta(janela)
    with contexto(janela, area_g, regiao_g):
        campos = {v[5][2]: v[5][4] for v in addon.gaveta._widgets_gaveta(
            bpy.context, regiao_g.width, regiao_g.height)
            if v[5] and v[5][0] == 'medida'}
    assert abs(campos['pistoes_offset_mm'] - offset) < 1e-6, campos
    m.clicar()
    yield
    grupo = addon.portas._portas_do_conjunto(conj)[0]
    p = grupo['porta_parametros']
    assert p['abertura'] == 'BASCULANTE' and p['folhas'] == 1, dict(p)
    assert p['dobradica'] == 'RETA', dict(p)
    assert p['pistoes_qtd'] == 2 and abs(p['pistoes_offset_mm'] - offset) < 1e-3
    assert p['dobradicas_qtd'] == 3, dict(p)
    assert abs(p['dobradicas_margem_mm'] - 80.0) < 1e-3, dict(p)


def test_wizard_cobertura_fora_do_padrao_pergunta(janela, m):
    # Um par certo e o outro muito diferente: "As medidas estao
    # corretas?" na viewport; Nao = marcar de novo.
    conj, area, regiao, rv3d = _wizard_ate_o_tipo(janela, m)
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    y = -P / 2
    fora = _local(conj, L / 2 + 40, y, -40)
    with contexto(janela, area, regiao):
        bpy.ops.mesh.primitive_cube_add(size=0.002, location=fora)
    bpy.ops.object.select_all(action='DESELECT')
    yield
    yield
    yield from _abrir_wizard(janela, m)
    for ponto in ((-L / 2, y, A), (-L / 2 + E, y, A - E), (L / 2 - E, y, E)):
        yield from _clicar_no_mundo(m, regiao, rv3d, _local(conj, *ponto))
    yield from _clicar_no_mundo(m, regiao, rv3d, fora)
    w = addon.portas._assistente_porta[0]
    assert w['etapa'] == 'CONFIRMAR', w['etapa']
    assert w['pergunta'] == 'As medidas estao corretas?'
    yield from _clicar_botao_do_wizard(m, regiao, 'NAO')
    assert w['etapa'] == 'DIAGONAL' and not addon.portas._assistente_porta[0] is None
    m.tecla('ESC')
    yield
    assert addon.portas._assistente_porta[0] is None
    assert not addon.portas._portas_do_conjunto(conj)


def test_alt_arrasta_o_canto_da_porta(janela, m):
    # Pedido do usuario: clique simples na porta = os fios do wizard; com
    # Alt as 4 bolinhas viram alcas e o canto arrastado refaz a porta.
    conj, area, regiao, rv3d = _wizard_ate_o_tipo(janela, m)
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    y = -P / 2
    cliques = [_local(conj, *p) for p in (
        (-L / 2, y, A), (-L / 2 + E, y, A - E), (L / 2 - E, y, E),
        (L / 2 - E / 2, y, 0))]
    ref = tuple(v for linha in conj.matrix_world.to_quaternion().to_matrix()
                for v in linha)
    with contexto(janela, area, regiao):
        bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=cliques[1],
            ponto_b=cliques[2], quatro_pontos=True, porta_a=cliques[0],
            porta_b=cliques[3], referencia=ref, pai_nome=conj.name,
            modulo_nome=conj.name, frente='NEG_Y', folhas=1)
    grupo = addon.portas._portas_do_conjunto(conj)[0]
    assert grupo['porta_parametros']['cobertura_dir_e'] == 0.5
    with contexto(janela, area, regiao):
        addon.hud._selecionar_porta_hud(bpy.context, addon.portas._folhas_portas(grupo)[0],
                                    'PORTA')
    yield
    yield
    m.mover(*na_tela(regiao, rv3d, addon.portas_viewport._cantos_da_porta(grupo)[3]))
    yield
    m.janela.event_simulate('LEFT_ALT', 'PRESS', alt=True, x=m.x, y=m.y)
    yield
    yield
    m.apertar(alt=True)
    yield
    assert addon.portas_viewport._arraste_canto_porta[0] is not None, 'o canto nao pegou'
    assert any(o.bl_idname.endswith('cabinet_arrastar_canto_porta')
               for o in m.janela.modal_operators), 'o arraste nao abriu'
    destino = na_tela(regiao, rv3d, _local(conj, L / 2, y, 0))
    inicio = (m.x, m.y)
    for passo in range(1, 5):
        m.mover(inicio[0] + (destino[0] - inicio[0]) * passo / 4,
                inicio[1] + (destino[1] - inicio[1]) * passo / 4)
        yield
    m.soltar(alt=True)
    yield
    yield
    m.janela.event_simulate('LEFT_ALT', 'RELEASE', x=m.x, y=m.y)
    yield
    assert addon.portas_viewport._arraste_canto_porta[0] is None
    p = grupo['porta_parametros']
    assert p['cobertura_dir_e'] == 1.0, dict(p)
    assert grupo in addon.portas_viewport._portas_com_cantos(bpy.context)


def test_slider_abre_a_folha(janela, m):
    # Fase 3 (Epico 4): porta selecionada = um slider na base de cada
    # folha; arrastar para a direita abre (o clique NAO vira selecao).
    conj, area, regiao, rv3d = _wizard_ate_o_tipo(janela, m)
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    y = -P / 2
    cliques = [_local(conj, *p) for p in (
        (-L / 2, y, A), (-L / 2 + E, y, A - E), (L / 2 - E, y, E), (L / 2, y, 0))]
    ref = tuple(v for linha in conj.matrix_world.to_quaternion().to_matrix()
                for v in linha)
    with contexto(janela, area, regiao):
        bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=cliques[1],
            ponto_b=cliques[2], quatro_pontos=True, porta_a=cliques[0],
            porta_b=cliques[3], referencia=ref, pai_nome=conj.name,
            modulo_nome=conj.name, frente='NEG_Y', folhas=1)
    grupo = addon.portas._portas_do_conjunto(conj)[0]
    folha = addon.portas._folhas_portas(grupo)[0]
    bpy.ops.object.select_all(action='DESELECT')
    with contexto(janela, area, regiao):
        bpy.ops.ed.undo_push(message='Porta criada')
    yield
    # como o usuario: clique de verdade na folha seleciona a porta
    centro = folha.matrix_world.translation
    yield from _clicar_no_mundo(m, regiao, rv3d, centro)
    yield esperar(0.4)          # sem virar duplo clique
    assert grupo in addon.portas_viewport._portas_com_cantos(bpy.context), 'a porta nao selecionou'
    with contexto(janela, area, regiao):
        bpy.ops.ed.undo_push(message='Porta selecionada')
        inicio, fim = addon.portas_viewport._slider_na_tela(bpy.context, folha)
    # a bolinha (fracao 0 = no inicio) e' um gizmo (VIEW3D_GT_slider_porta,
    # grupo VIEW3D_GGT_slider_porta): vem antes de qualquer keymap. O
    # trilho fora dela nao pega; passar por cima dela acende
    with contexto(janela, area, regiao):
        assert addon.portas_viewport.VIEW3D_GGT_slider_porta.poll(bpy.context)
    # tamanho em mm do mundo (pedido do usuario): afastar 3x encolhe ~3x
    with contexto(janela, area, regiao):
        perto = addon.portas_viewport._px_por_mm_do_slider(bpy.context, folha)
    distancia = rv3d.view_distance
    rv3d.view_distance = distancia * 3
    yield
    with contexto(janela, area, regiao):
        longe = addon.portas_viewport._px_por_mm_do_slider(bpy.context, folha)
    rv3d.view_distance = distancia
    yield
    yield
    assert perto < addon.portas_viewport.SLIDER_PX_POR_MM_MAX, perto
    assert abs(longe / perto - 1 / 3) < 0.08, (perto, longe)
    with contexto(janela, area, regiao):
        inicio, fim = addon.portas_viewport._slider_na_tela(bpy.context, folha)
    raio = addon.portas_viewport.SLIDER_BOTAO_MM * perto
    m.mover(regiao.x + inicio.x + (fim.x - inicio.x) * 0.5,
            regiao.y + inicio.y + (fim.y - inicio.y) * 0.5)
    yield
    yield
    assert addon.portas_viewport._slider_hover[0] is None, 'o trilho pegou o hover'
    m.mover(regiao.x + inicio.x + raio * 0.6, regiao.y + inicio.y)
    yield
    yield
    assert addon.portas_viewport._slider_hover[0] == folha.name, 'a bolinha nao acendeu'
    m.apertar()
    yield
    assert addon.portas_viewport._arraste_slider_porta[0] == folha.name, 'o slider nao pegou'
    assert any(o.bl_idname.endswith('cabinet_abrir_porta')
               for o in m.janela.modal_operators), 'o arraste nao abriu'
    meio = inicio.lerp(fim, 0.5)
    for passo in range(1, 5):
        # pegou a 0.6 raio do centro: ela anda junto, sem pular
        m.mover(regiao.x + inicio.x + raio * 0.6
                + (meio.x - inicio.x) * passo / 4,
                regiao.y + inicio.y + (meio.y - inicio.y) * passo / 4)
        yield
    m.soltar()
    yield
    yield
    assert addon.portas_viewport._arraste_slider_porta[0] is None
    fracao = folha[addon.ferragens.CHAVE_ABERTURA]
    assert abs(fracao - 0.5) < 0.05, fracao
    # a porta continua selecionada (o clique foi do slider)
    assert grupo in addon.portas_viewport._portas_com_cantos(bpy.context)
    # Ctrl+Z desfaz a abertura
    m.apertar('Z', ctrl=True)
    m.soltar('Z', ctrl=True)
    yield
    yield
    # o undo troca os objetos: buscar de novo (a referencia antiga morreu)
    grupo = next(o for o in bpy.data.objects if addon.chapas.MARCA_PORTAS in o)
    folha = addon.portas._folhas_portas(grupo)[0]
    assert folha.get(addon.ferragens.CHAVE_ABERTURA, 0.0) == 0.0, folha.get(addon.ferragens.CHAVE_ABERTURA)


def test_digitar_com_operador_e_cursor_no_meio(janela, m):
    # Pedido do usuario: na caixa de digitar da HUD, '+' continua a conta
    # (nao apaga o "600"); clicar DENTRO da caixa nao fecha, so' leva o
    # cursor ate' ali; "6cm00" vale 600 cm.
    conj = criar_modulo(janela)
    selecionar(janela, addon.modulos._chapas_do_conjunto(conj)[0])
    aproximar(janela, conj)
    yield
    yield
    _geometria, _linha, a, b = _linha_l(janela, conj)
    largura = conj.conj_largura_mm
    m.mover(*(a + (b - a) * 0.2))
    yield
    yield
    m.clicar()
    yield
    m.digitar('+100')
    yield
    estado = addon.hud._edicao_hud[0]
    assert estado['texto'].replace(' ', '') == addon.opcoes._numero_na_unidade(
        largura).replace(' ', '') + '+100', estado['texto']
    m.tecla('RET')
    yield
    assert abs(conj.conj_largura_mm - (largura + 100)) < 1e-3, conj.conj_largura_mm
    # de novo: agora "600" e o clique ao lado do 6
    m.mover(*(a + (b - a) * 0.2))
    yield
    yield
    m.clicar()
    yield
    estado = addon.hud._edicao_hud[0]
    estado['texto'], estado['cursor'] = '600', 3
    yield
    area, regiao, _rv3d = viewport(janela)
    x, y, tamanho, _escala = estado['caixas'][0]
    meio = x + addon.gaveta_desenho._medidor_blf(tamanho)('6')
    m.mover(regiao.x + meio, regiao.y + y + 3)
    yield
    m.clicar()
    yield
    assert addon.hud._edicao_hud[0] is not None, 'o clique na caixa fechou a edicao'
    assert estado['cursor'] == 1, estado['cursor']
    m.digitar('cm')
    yield
    assert estado['texto'] == '6cm00', estado['texto']
    m.tecla('RET')
    yield
    assert abs(conj.conj_largura_mm - 6000.0) < 1e-3, conj.conj_largura_mm


def _duplo_clique_do_keymap(janela, shift=False):
    """O 2o clique de um duplo, como o keymap entrega: o simulador nao
    gera DOUBLE_CLICK (fonte do Blender), entao o operador e' chamado
    com as props da entrada DOUBLE_CLICK de `_ENTRADAS_KEYMAP`, no mesmo
    contexto e posicao de mouse de um clique real."""
    entrada = next(e for e in addon.selecao._ENTRADAS_KEYMAP
                   if e[0] == 'DOUBLE_CLICK' and e[1] == shift)
    area, regiao, _ = viewport(janela)
    with contexto(janela, area, regiao):
        return bpy.ops.object.cabinet_selecionar(
            'INVOKE_DEFAULT', modo=entrada[2], **entrada[3])


def test_selecao_da_porta_e_da_folha(janela, m):
    conj = criar_modulo(janela)
    area, regiao, rv3d = viewport(janela)
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    a = conj.matrix_world @ (Vector((-L / 2 + E, -P / 2, E)) / 1000.0)
    b = conj.matrix_world @ (Vector((L / 2 - E, -P / 2, A - E)) / 1000.0)
    with contexto(janela, area, regiao):
        bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            referencia=tuple(v for linha in
                             conj.matrix_world.to_quaternion().to_matrix()
                             for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name, frente='NEG_Y',
            dobradica='RETA', folhas=2)
    grupo = addon.portas._portas_do_conjunto(conj)[0]
    folha = addon.portas._folhas_portas(grupo)[0]
    bpy.ops.object.select_all(action='DESELECT')
    # vista de frente (olhando para +Y): a folha fica na frente de tudo
    rv3d.view_rotation = Euler((math.pi / 2, 0, 0)).to_quaternion()
    lo, hi = caixa_mundo(addon.modulos._chapas_do_conjunto(conj))
    rv3d.view_location = (lo + hi) / 2
    yield
    yield
    m.mover(*na_tela(regiao, rv3d, folha.matrix_world.translation))
    yield
    portas = {grupo, *addon.portas._folhas_portas(grupo)}
    # Backlog do usuario (Epico 3): clique na porta = a PORTA inteira,
    # nunca o modulo; duplo = UMA folha ("aba")
    m.clicar()
    yield
    selecionados = set(bpy.context.selected_objects)
    assert selecionados == portas, 'clique devia ir para a PORTA; ficou %s' % (
        sorted(o.name for o in selecionados))
    assert bpy.context.view_layer.objects.active == grupo
    # duplo (o 2o clique chega ao keymap como DOUBLE_CLICK): a folha
    m.clicar()
    yield
    _duplo_clique_do_keymap(janela)
    yield
    assert set(bpy.context.selected_objects) == {folha}, (
        'duplo clique devia ir para a FOLHA; ficou %s'
        % sorted(o.name for o in bpy.context.selected_objects))
    # so' a folha selecionada: o contorno laranja nativo segue desligado
    espaco = area.spaces.active
    assert not espaco.overlay.show_outline_selected,         'contorno nativo voltou com a folha selecionada'
    # clique de novo: a porta inteira outra vez
    m.clicar()
    yield
    assert set(bpy.context.selected_objects) == portas


def _modulo_em(janela, x):
    """Um modulo (nicho agrupado) com o centro em x metros."""
    area, regiao, _ = viewport(janela)
    antes = set(bpy.data.objects)
    with contexto(janela, area, regiao):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='DESELECT')
        for o in set(bpy.data.objects) - antes:
            o.select_set(True)
        bpy.ops.object.cabinet_agrupar()
    conj = next(o for o in set(bpy.data.objects) - antes
                if addon.chapas.MARCA_CONJUNTO in o)
    conj.location.x = x
    bpy.context.view_layer.update()
    return conj


def _chapas_visiveis(janela, conj):
    """{chapa: ponto na janela} das chapas que o raio acerta no proprio
    centro (as outras ficam atras de alguma peca nesta vista)."""
    area, regiao, rv3d = viewport(janela)
    saida = {}
    with contexto(janela, area, regiao):
        for chapa in addon.modulos._chapas_do_conjunto(conj):
            ponto = na_tela(regiao, rv3d, chapa.matrix_world.translation)
            if ponto is None:
                continue
            local = (ponto[0] - regiao.x, ponto[1] - regiao.y)
            acerto = addon.hud._raio_hud(bpy.context, local)
            if acerto is not None and acerto[0] == chapa:
                saida[chapa] = ponto
    return saida


def test_shift_soma_chapas_individuais_e_grupos(janela, m):
    # Pedido do usuario: clique = grupo; duplo = uma chapa; Shift+clique
    # em outra chapa do MESMO grupo soma so' ela. Com dois grupos
    # (clique + Shift+clique), Shift+duplo isola a chapa DENTRO da
    # selecao e o outro grupo fica.
    a = _modulo_em(janela, -0.5)
    b = _modulo_em(janela, 0.5)
    area, regiao, rv3d = viewport(janela)
    rv3d.view_rotation = Euler((math.radians(65), 0,
                                math.radians(25))).to_quaternion()
    rv3d.view_location = (0, 0, 0.3)
    rv3d.view_distance = 3.5
    bpy.ops.object.select_all(action='DESELECT')
    yield
    yield
    alvos_a, alvos_b = _chapas_visiveis(janela, a), _chapas_visiveis(janela, b)
    assert len(alvos_a) >= 2 and alvos_b, 'chapas fora de vista'
    (a1, p_a1), (a2, p_a2) = list(alvos_a.items())[:2]
    b1, p_b1 = next(iter(alvos_b.items()))
    grupo_a = {a, *a.children_recursive}
    grupo_b = {b, *b.children_recursive}
    # um grupo: clique, duplo, Shift+clique em outra chapa dele
    m.mover(*p_a1)
    yield
    m.clicar()
    yield
    assert set(bpy.context.selected_objects) == grupo_a, 'clique: grupo'
    m.clicar()
    yield
    _duplo_clique_do_keymap(janela)
    yield
    assert set(bpy.context.selected_objects) == {a1}, 'duplo: a chapa'
    m.mover(*p_a2)
    yield
    m.clicar(shift=True)
    yield
    selecao = set(bpy.context.selected_objects)
    assert selecao == {a1, a2}, 'Shift+clique devia somar so a chapa: %s' % (
        sorted(o.name for o in selecao))
    # dois grupos: clique em A, Shift+clique em B
    m.mover(*p_a1)
    yield
    m.clicar()
    yield
    m.mover(*p_b1)
    yield
    m.clicar(shift=True)
    yield
    assert set(bpy.context.selected_objects) == grupo_a | grupo_b,         'Shift+clique devia somar o grupo B'
    # Shift+duplo em A: so' a1 de A, B inteiro
    m.mover(*p_a1)
    yield
    m.clicar(shift=True)
    yield
    _duplo_clique_do_keymap(janela, shift=True)
    yield
    selecao = set(bpy.context.selected_objects)
    assert selecao == {a1} | grupo_b, 'Shift+duplo em A: %s' % (
        sorted(o.name for o in selecao))
    # Shift+duplo em B: a1 fica, b1 sozinha
    m.mover(*p_b1)
    yield
    m.clicar(shift=True)
    yield
    _duplo_clique_do_keymap(janela, shift=True)
    yield
    selecao = set(bpy.context.selected_objects)
    assert selecao == {a1, b1}, 'Shift+duplo em B: %s' % (
        sorted(o.name for o in selecao))


def test_dois_modulos_selecionados_editam_pela_hud_os_dois(janela, m):
    # Pedido do usuario: com dois modulos selecionados o contorno so'
    # aparecia no ultimo. A seta e a quina do modulo que NAO e' o ativo
    # tambem respondem ao mouse real; sem "Editar como?".
    a = _modulo_em(janela, -0.5)
    b = _modulo_em(janela, 0.5)
    area, regiao, rv3d = viewport(janela)
    rv3d.view_rotation = Euler((math.radians(65), 0,
                                math.radians(25))).to_quaternion()
    rv3d.view_location = (0, 0, 0.3)
    rv3d.view_distance = 3.0
    bpy.ops.object.select_all(action='DESELECT')
    yield
    yield
    alvos_a, alvos_b = _chapas_visiveis(janela, a), _chapas_visiveis(janela, b)
    m.mover(*next(iter(alvos_a.values())))
    yield
    m.clicar()
    yield
    m.mover(*next(iter(alvos_b.values())))
    yield
    m.clicar(shift=True)
    yield
    assert bpy.context.view_layer.objects.active == b
    with contexto(janela, area, regiao):
        desenhos = addon.hud._desenhos_hud(bpy.context)
    assert {g['objeto'] for g, _x in desenhos} == {a, b}, \
        'contorno devia aparecer nos dois: %s' % [g['objeto'].name
                                                 for g, _x in desenhos]
    # Seta L de A (nao ativo): os dois estao selecionados, entao os
    # dois se editam. B ainda sem seta pisca; a seta de B escolhida, o
    # valor digitado vale para os dois, cada um com a sua quina parada.
    linhas = {}
    for item in (a, b):
        geometria = addon.hud._geometria_do_item(item, 'GRUPO',
                                             addon.modulos._chapas_do_conjunto(item))
        for l in geometria['linhas']:
            if l['tipo'] == 'medida' and l['eixo'] == 0:
                p, q = (na_tela(regiao, rv3d, x) for x in l['pontos'])
                if p and q and (Vector(q) - Vector(p)).length > 60:
                    linhas[item] = (geometria['cantos'][l['cantos'][0]].copy(),
                                    Vector(p), Vector(q))
                    break
        assert item in linhas, 'linha L de %s fora de vista' % item.name
    fixa_a, ini, fim = linhas[a]
    m.mover(*(ini + (fim - ini) * 0.2))
    yield
    yield
    hover = addon.hud._hover_hud.get(regiao.as_pointer())
    assert hover and hover['objeto'] == a, 'a linha de A nao acendeu: %s' % (
        hover and hover['objeto'].name)
    m.clicar()
    yield
    estado = addon.hud._edicao_hud[0]
    assert estado and estado.get('fase') == 'coletar', estado
    assert not estado.get('botoes'), 'voltou o "Editar como?"'
    with contexto(janela, area, regiao):
        pendentes = [g['objeto'] for g, _x in addon.hud._desenhos_hud(bpy.context)
                     if g.get('pendente')]
    assert pendentes == [b], 'B devia piscar: %s' % pendentes
    assert time.time() - addon.hud._piscada_hud[0] < 5, 'nao piscou'
    fixa_b, ini, fim = linhas[b]
    m.mover(*(ini + (fim - ini) * 0.2))
    yield
    yield
    m.clicar()
    yield
    assert addon.hud._edicao_hud[0].get('texto') is not None, \
        'orientados os dois, devia digitar'
    m.digitar('900')
    m.tecla('RET')
    yield
    for item, fixa in ((a, fixa_a), (b, fixa_b)):
        assert abs(item.conj_largura_mm - 900.0) < 1e-3, item.conj_largura_mm
        nova = addon.hud._geometria_do_item(item, 'GRUPO',
                                        addon.modulos._chapas_do_conjunto(item))
        assert min((c - fixa).length for c in nova['cantos']) < 1e-4, \
            'a quina escolhida de %s saiu do lugar' % item.name
    # quina do modulo A: arrastar move so' ele
    geometria = addon.hud._geometria_do_item(a, 'GRUPO', addon.modulos._chapas_do_conjunto(a))
    canto = min((na_tela(regiao, rv3d, c) for c in geometria['cantos']
                 if na_tela(regiao, rv3d, c)),
                key=lambda c: c[0])            # a quina mais a esquerda
    pos_a, pos_b = a.matrix_world.translation.copy(), b.matrix_world.translation.copy()
    m.mover(*canto)
    yield
    yield
    hover = addon.hud._hover_hud.get(regiao.as_pointer())
    assert hover and hover['tipo'] == 'ancora' and hover['objeto'] == a, \
        'a quina de A nao acendeu: %s' % (hover and hover['tipo'])
    m.apertar()
    yield
    for passo in range(1, 5):
        m.mover(canto[0] - 15 * passo, canto[1])
        yield
    m.soltar()
    yield
    assert (a.matrix_world.translation - pos_a).length > 0.01, 'A nao moveu'
    assert (b.matrix_world.translation - pos_b).length < 1e-6, 'B moveu junto'


def test_quina_com_ctrl_gruda_na_quina_de_outro_modulo(janela, m):
    # Pedido do usuario: movendo o modulo pela quina, o Ctrl liga um snap
    # especial, so' em quinas de outros armarios ou chapas.
    a = _modulo_em(janela, -0.5)
    b = _modulo_em(janela, 0.5)
    area, regiao, rv3d = viewport(janela)
    rv3d.view_rotation = Euler((math.radians(65), 0,
                                math.radians(25))).to_quaternion()
    rv3d.view_location = (0, 0, 0.3)
    rv3d.view_distance = 3.0
    bpy.ops.object.select_all(action='DESELECT')
    yield
    yield
    m.mover(*next(iter(_chapas_visiveis(janela, a).values())))
    yield
    m.clicar()
    yield
    assert bpy.context.view_layer.objects.active == a
    cantos = lambda o: addon.hud._geometria_do_item(
        o, 'GRUPO', addon.modulos._chapas_do_conjunto(o))['cantos']
    na_vista = [(i, na_tela(regiao, rv3d, c)) for i, c in enumerate(cantos(a))]
    i, canto = min(((i, c) for i, c in na_vista if c), key=lambda x: x[1][0])
    alvo = cantos(b)[i].copy()
    destino = Vector(na_tela(regiao, rv3d, alvo)) + Vector((6, 4))
    m.mover(*canto)
    yield
    yield
    hover = addon.hud._hover_hud.get(regiao.as_pointer())
    assert hover and hover['tipo'] == 'ancora' and hover['objeto'] == a, \
        'a quina de A nao acendeu: %s' % (hover and hover['tipo'])
    m.apertar()
    yield
    janela.event_simulate('LEFT_CTRL', 'PRESS', ctrl=True, x=m.x, y=m.y)
    yield
    for passo in range(1, 6):
        m.x, m.y = (int(round(v)) for v in
                    Vector(canto) + (destino - Vector(canto)) * passo / 5)
        janela.event_simulate('MOUSEMOVE', 'NOTHING', ctrl=True, x=m.x, y=m.y)
        yield
    # Grudou numa quina de B perto do alvo: a da caixa ou a de uma chapa
    # dele (a espessura as separa por poucos pixels; vale a mais perto)
    grudou = addon.hud._edicao_hud[0].get('snap')
    assert grudou is not None, 'nao grudou'
    quinas_b = [q for q in addon.hud._quinas_de_snap(a)
                if (q - alvo).length < 0.05]
    assert min((q - grudou).length for q in quinas_b) < 1e-6, \
        'grudou fora das quinas de B'
    erro = (cantos(a)[i] - grudou).length
    assert erro < 1e-5, 'quina de A a %.4f m da quina' % erro
    alvo = grudou.copy()
    # soltando o Ctrl parado o snap sai; apertando de novo, volta
    janela.event_simulate('LEFT_CTRL', 'RELEASE', x=m.x, y=m.y)
    yield
    assert addon.hud._edicao_hud[0].get('snap') is None, 'Ctrl solto e grudado'
    assert min((c - alvo).length for c in cantos(a)) > 1e-3, 'nao soltou'
    janela.event_simulate('LEFT_CTRL', 'PRESS', ctrl=True, x=m.x, y=m.y)
    yield
    m.soltar(ctrl=True)
    yield
    janela.event_simulate('LEFT_CTRL', 'RELEASE', x=m.x, y=m.y)
    yield
    assert addon.hud._edicao_hud[0] is None, 'o arraste nao terminou'
    erro = min((c - alvo).length for c in cantos(a))
    assert erro < 1e-5, 'soltou fora da quina: %.4f m' % erro


def test_ctrl_z_com_o_mouse_na_hud_esquece_o_objeto(janela, m):
    # Crash do usuario: Ctrl+Z com o mouse sobre a HUD. O undo libera os
    # objetos, e o hover guardava um deles para o desenho seguinte (o
    # Blender caia depois, em lugar aleatorio).
    area, regiao, rv3d = viewport(janela)
    with contexto(janela, area, regiao):
        bpy.ops.ed.undo_push(message='Antes do modulo')
    conj = criar_modulo(janela)
    chapas = addon.modulos._chapas_do_conjunto(conj)
    selecionar(janela, chapas[0])
    with contexto(janela, area, regiao):
        bpy.ops.ed.undo_push(message='Modulo')
    rv3d.view_rotation = Euler((math.pi / 2, 0, 0)).to_quaternion()
    lo, hi = caixa_mundo(chapas)
    rv3d.view_location = (lo + hi) / 2
    rv3d.view_distance = 1.6
    yield
    yield
    geometria = addon.hud._geometria_do_item(conj, 'GRUPO', chapas)
    linha = next(l for l in geometria['linhas'] if l['tipo'] == 'medida'
                 and all(na_tela(regiao, rv3d, p) for p in l['pontos']))
    p, q = (Vector(na_tela(regiao, rv3d, x)) for x in linha['pontos'])
    m.mover(*(p + (q - p) * 0.3))
    yield
    yield
    assert addon.hud._hover_hud.get(regiao.as_pointer()), 'a linha nao acendeu'
    m.apertar('Z', ctrl=True)
    m.soltar('Z', ctrl=True)
    yield
    yield
    assert not any(addon.chapas.MARCA_CONJUNTO in o for o in bpy.data.objects),         'o Ctrl+Z nao desfez o modulo'
    assert all(addon.hud._alvo_vivo(a) for a in addon.hud._hover_hud.values()),         'o hover ficou com objeto liberado'
    # o handler do depsgraph esperou o undo assentar e ja' voltou
    assert not addon.eventos._desfazendo[0], 'o handler ficou desligado'
    m.mover(m.x + 6, m.y)
    yield
    yield


def test_hover_acende_o_botao_pelo_gizmo_da_gaveta(janela, m):
    # O hover vem do VIEW3D_GGT_cabinet_gaveta (um gizmo invisivel por
    # widget, `_preparar_hover`): sem ele o glow nunca acende.
    area, regiao = gaveta(janela)
    m.mover(*widget(janela, lambda v: v[5] == ('aba', 'PORTAS')))
    yield esperar(0.4)
    with contexto(janela, area, regiao):
        aceso = addon.gaveta._valor_realce(bpy.context, 'aba:PORTAS')
    assert aceso > 0.5, 'hover nao acendeu a aba (%.2f)' % aceso
    m.mover(regiao.x + regiao.width / 2, regiao.y + 20)   # pe' vazio
    yield esperar(0.6)
    with contexto(janela, area, regiao):
        apagado = addon.gaveta._valor_realce(bpy.context, 'aba:PORTAS')
    assert apagado < 0.1, 'o glow nao apagou ao sair (%.2f)' % apagado


def _porta_no_modulo(janela, conj):
    area, regiao, _ = viewport(janela)
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    a = conj.matrix_world @ (Vector((-L / 2 + E, -P / 2, E)) / 1000.0)
    b = conj.matrix_world @ (Vector((L / 2 - E, -P / 2, A - E)) / 1000.0)
    with contexto(janela, area, regiao):
        bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            referencia=tuple(v for linha in
                             conj.matrix_world.to_quaternion().to_matrix()
                             for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name, frente='NEG_Y',
            dobradica='RETA', folhas=1)
    return addon.portas._portas_do_conjunto(conj)[0]


def test_alt_arrasta_o_puxador_para_outra_borda(janela, m):
    # Pedido do usuario: com Alt a ancora do puxador vira uma bolinha;
    # arrastar leva-o a outra borda do GRUPO (snap de linha), virado
    # conforme ela. So' as bordas das folhas da porta valem.
    conj, area, regiao, rv3d = _wizard_ate_o_tipo(janela, m)
    grupo = _porta_no_modulo(janela, conj)
    folha = addon.portas._folhas_portas(grupo)[0]
    pux = addon.puxadores.criar_puxador(bpy.context, folha, 'ALCA', 'X+', 1, 0.5)
    bpy.ops.object.select_all(action='DESELECT')
    folha.select_set(True)
    bpy.context.view_layer.objects.active = folha
    yield
    yield
    m.mover(*na_tela(regiao, rv3d, addon.puxadores._ancora_do_puxador(pux)))
    yield
    m.janela.event_simulate('LEFT_ALT', 'PRESS', alt=True, x=m.x, y=m.y)
    yield
    yield
    m.apertar(alt=True)
    yield
    estado = addon.puxadores._arraste_puxador[0]
    assert estado is not None, 'a ancora do puxador nao pegou'
    a, b = addon.puxadores._bordas_da_face(folha, 1)['Y-']
    destino = na_tela(regiao, rv3d, a.lerp(b, 0.3))
    inicio = (m.x, m.y)
    for passo in range(1, 6):
        m.mover(inicio[0] + (destino[0] - inicio[0]) * passo / 5,
                inicio[1] + (destino[1] - inicio[1]) * passo / 5)
        yield
    assert len(estado['linhas']) == 4, 'so\' as bordas da folha: %d' % len(
        estado['linhas'])
    m.soltar(alt=True)
    yield
    m.janela.event_simulate('LEFT_ALT', 'RELEASE', x=m.x, y=m.y)
    yield
    assert addon.puxadores._arraste_puxador[0] is None, 'o arraste nao terminou'
    assert (pux.parent, pux['puxador_borda']) == (folha, 'Y-'), (
        pux.parent.name, pux['puxador_borda'])
    assert abs(pux['puxador_fracao'] - 0.3) < 0.05, pux['puxador_fracao']


def test_definir_frente_com_clique_na_face(janela, m):
    conj = criar_modulo(janela)
    grupo = _porta_no_modulo(janela, conj)
    folha = addon.portas._folhas_portas(grupo)[0]
    frente = grupo.matrix_world.to_3x3().col[2].normalized()
    assert frente.y < -0.99, tuple(frente)
    bpy.ops.object.select_all(action='DESELECT')
    folha.select_set(True)
    bpy.context.view_layer.objects.active = folha
    area, regiao, rv3d = viewport(janela)
    # vista de TRAS (olhando para -Y): o nicho nao tem fundo, o raio
    # bate direto na face de tras da folha
    rv3d.view_rotation = Euler((math.pi / 2, 0, math.pi)).to_quaternion()
    lo, hi = caixa_mundo(addon.modulos._chapas_do_conjunto(conj))
    rv3d.view_location = (lo + hi) / 2
    yield
    yield
    with contexto(janela, area, regiao):
        assert bpy.ops.object.cabinet_definir_frente('INVOKE_DEFAULT') \
            == {'RUNNING_MODAL'}
    m.mover(*na_tela(regiao, rv3d, folha.matrix_world.translation))
    yield
    m.clicar()
    yield
    nova = grupo.matrix_world.to_3x3().col[2].normalized()
    assert nova.y > 0.99, 'a frente nao virou para tras: %r' % (tuple(nova),)


def test_escalar_o_modulo_com_S(janela, m):
    # Bug achado pelo harness (corrigido na 126): S no Empty do modulo
    # nao surtia efeito -- as chapas voltavam ao tamanho antigo.
    conj = criar_modulo(janela)
    selecionar(janela, addon.modulos._chapas_do_conjunto(conj)[0])
    largura = conj.conj_largura_mm
    area, regiao, rv3d = viewport(janela)
    centro = na_tela(regiao, rv3d, conj.matrix_world.translation)
    m.mover(centro[0] + 60, centro[1])
    yield
    m.tecla('S')
    # com as suites em paralelo o S podia nao ter aberto a escala ainda e
    # o X/1.5/Enter caiam no vazio (largura intacta): espera o modal
    for _tentativa in range(25):
        yield
        if any(op.bl_idname == 'TRANSFORM_OT_resize'
               for op in janela.modal_operators):
            break
    m.tecla('X')            # so' na largura
    yield
    m.digitar('1.5')
    m.tecla('RET')
    # espessura imune a escala: as laterais seguem com 18 mm e so' a
    # POSICAO delas escala -- (L - E) * 1.5 + E, nao L * 1.5
    esperado = (largura - 18.0) * 1.5 + 18.0
    # handler/timer (0.2 s) absorvem e normalizam: espera a CONDICAO, nao
    # um tempo fixo -- com as suites em paralelo 0.6 s nao bastava (v146)
    for _tentativa in range(25):
        yield esperar(0.2)
        if (abs(conj.conj_largura_mm - esperado) < 0.5
                and all(abs(e - 1.0) < 1e-6 for e in conj.scale)):
            break
    assert abs(conj.conj_largura_mm - esperado) < 0.5, \
        (largura, esperado, conj.conj_largura_mm)
    for eixo in conj.scale:
        assert abs(eixo - 1.0) < 1e-6, tuple(conj.scale)
    for chapa in addon.modulos._chapas_do_conjunto(conj):
        assert abs(chapa.chapa_espessura_mm - 18.0) < 1e-3, chapa.name
        assert all(abs(s - 1.0) < 1e-6 for s in chapa.scale), chapa.name


def test_clique_na_corrente_desassocia(janela, m):
    # A corrente e' o botao do VIEW3D_GGT_correntes_cabinet (gizmo nativo
    # LINKED); com Alt segurado quem pega o clique e' cabinet_clique_corrente
    # (o gizmo nativo nao aceita clique com modificador). So' aparece com
    # a tecla das opcoes (Alt) segurada e a solda fora da origem; TODAS as
    # quinas; o clique desagrega a peca INTEIRA (todas as quinas).
    piso = addon.chapas.nova_chapa('Piso', 600.0, 400.0, 18.0, (0, 0, 9.0),
                            (0, 0, 0), bpy.context)
    lateral = addon.chapas.nova_chapa('Lateral', 720.0, 400.0, 18.0,
                               (319.0, 0, 360.0), (0, 90.0, 0), bpy.context)
    bpy.context.view_layer.update()
    addon.chapas.detectar_adjacencia([piso, lateral])
    lateral.location.x += 0.02          # 20 mm fora da origem da solda
    bpy.context.view_layer.update()
    selecionar(janela, piso)
    area, regiao, rv3d = viewport(janela)
    rv3d.view_location = (0.15, 0, 0.2)
    rv3d.view_distance = 2.5
    yield
    yield

    def corrente_visivel():
        with contexto(janela, area, regiao):
            return addon.solda._correntes_hud(bpy.context)

    assert corrente_visivel() == [], 'sem Alt a corrente nao aparece'
    m.janela.event_simulate('LEFT_ALT', 'PRESS', alt=True, x=m.x, y=m.y)
    yield
    correntes = corrente_visivel()
    assert len(correntes) == 2, 'com Alt: as 2 quinas, veio %d' % len(correntes)
    assert correntes[0]['meio'] is not None, 'a corrente ficou fora da tela'
    with contexto(janela, area, regiao):
        meio = addon.solda._botoes_da_corrente(bpy.context, correntes[0])['corrente']
    m.mover(regiao.x + meio.x, regiao.y + meio.y)
    yield
    yield
    m.clicar(alt=True)
    yield
    assert not addon.solda.agregado(piso), 'um clique e o piso segue agregado'
    assert addon.solda._ligacoes_adjacencia([piso, lateral]) == []
    assert corrente_visivel() == [], 'a corrente nao sumiu'
    m.janela.event_simulate('LEFT_ALT', 'RELEASE', x=m.x, y=m.y)
    yield
    assert not addon.solda._tecla_corrente_segurada[0], 'soltar o Alt nao escondeu'
    # o clique foi DA corrente: a selecao continua a mesma
    assert piso.select_get() and lateral.select_get()


def _caixote_aberto(janela):
    conj = criar_modulo(janela)
    chapas = addon.modulos._chapas_do_conjunto(conj)
    ordem = sorted(chapas, key=lambda o: o.matrix_world.translation.z)
    base, tampo = ordem[0], ordem[-1]
    for chapa in (base, tampo):
        addon.hud._redimensionar_chapa_ancorada(
            chapa, 0, chapa.chapa_largura_mm - 250.0, 'min')
    bpy.context.view_layer.update()
    return conj, base, tampo


def test_clique_na_corrente_tira_a_peca_do_modulo(janela, m):
    # 3a print: tampo e base recuados; o clique na corrente desagrega a
    # peca da corrente (todas as quinas) e ela SAI do modulo, no lugar.
    conj, base, tampo = _caixote_aberto(janela)
    selecionar(janela, base)
    area, regiao, rv3d = viewport(janela)
    rv3d.view_rotation = Euler((math.radians(70), 0,
                                math.radians(35))).to_quaternion()
    rv3d.view_location = (0.0, 0, 0.25)
    rv3d.view_distance = 2.2
    yield
    yield
    m.janela.event_simulate('LEFT_ALT', 'PRESS', alt=True, x=m.x, y=m.y)
    yield
    with contexto(janela, area, regiao):
        correntes = [c for c in addon.solda._correntes_hud(bpy.context)
                     if c['meio'] is not None]
        assert correntes, 'nenhuma corrente na tela'
        meio = addon.solda._botoes_da_corrente(bpy.context, correntes[0])['corrente']
    peca = correntes[0]['a']
    assert peca in (base, tampo)
    mundo = peca.matrix_world.copy()
    m.mover(regiao.x + meio.x, regiao.y + meio.y)
    yield
    yield
    m.clicar(alt=True)
    yield
    m.janela.event_simulate('LEFT_ALT', 'RELEASE', x=m.x, y=m.y)
    yield
    assert peca.parent is None, 'a peca continua no modulo'
    assert not addon.solda.agregado(peca)
    for a, b in zip(peca.matrix_world, mundo):
        assert (a - b).length < 1e-5, 'a peca saiu do lugar'
    outra = tampo if peca is base else base
    assert outra.parent == conj, 'a outra peca saiu junto'


def test_botao_corrente_associa_por_vertices_e_junta(janela, m):
    # Fluxo do botao Corrente (cabinet_corrente_objeto) com a peca
    # desagregada e nada ao alcance: modo "selecionar vertice"
    # (cabinet_conectar_vertices), canto da peca e depois o canto onde ela
    # gruda, 2 vezes; "Confirmar" no pe' da gaveta
    # (cabinet_confirmar_conexao); "Juntar ao modulo?" -> Sim
    # (cabinet_juntar_modulo). O modulo NAO e' puxado.
    conj = criar_modulo(janela)
    chapas = addon.modulos._chapas_do_conjunto(conj)
    direita = max(chapas, key=lambda o: o.matrix_world.translation.x)
    fixos = {o.name: o.matrix_world.copy() for o in chapas}
    prateleira = addon.chapas.nova_chapa('Prateleira', 400.0, 300.0, 18.0,
                                  (900.0, 0, 300.0), (0, 0, 0), bpy.context)
    bpy.context.view_layer.update()
    selecionar(janela, prateleira, individual=True)
    area, regiao, rv3d = viewport(janela)
    rv3d.view_rotation = Euler((math.radians(70), 0,
                                math.radians(20))).to_quaternion()
    rv3d.view_location = (0.6, 0, 0.2)
    rv3d.view_distance = 2.4
    yield
    yield
    botao = lambda v: v[5][:2] == ('operador', addon.solda.OP_CORRENTE_OBJETO)
    with contexto(janela, *gaveta(janela)):
        estado = addon.solda._estado_corrente_objeto(bpy.context)
    assert estado is False, 'prateleira solta devia deixar o botao cinza'
    m.mover(*widget(janela, botao))
    yield
    m.clicar()
    yield
    assert addon.solda._conexao_manual[0] is not None, 'nao entrou em selecionar vertice'
    fora_x = max(p.x for p in addon.chapas._cantos(direita))
    alvos = sorted((p for p in addon.chapas._cantos(direita)
                    if abs(p.x - fora_x) < 1e-6 and p.z < 0.01),
                   key=lambda p: p.y)
    cantos = sorted((p for p in addon.chapas._cantos(prateleira)
                     if addon.solda._assinatura_canto(prateleira, p)[0] == '-'
                     and addon.solda._assinatura_canto(prateleira, p)[2] == '-'),
                    key=lambda p: p.y)
    for p, q in zip(cantos, alvos):
        for ponto in (p, q):
            m.mover(*na_tela(regiao, rv3d, ponto))
            yield
            m.clicar()
            yield
    assert len(addon.solda._conexao_manual[0]['pares']) == 2, \
        addon.solda._conexao_manual[0]['pares']
    m.mover(*widget(janela, lambda v: v[5] == (
        'operador', 'object.cabinet_confirmar_conexao')))
    yield
    m.clicar()
    yield
    m.mover(*na_tela(regiao, rv3d, conj.matrix_world.translation))
    yield
    assert addon.solda._conexao_manual[0] is None, 'Confirmar nao encerrou'
    assert addon.solda._conexao_pendente[0] is not None, 'sem "Juntar ao modulo?"'
    # veio de um botao da GAVETA: a pergunta esta' NELA (caixa preta),
    # nao em pop-up -- clica no "Sim, juntar" de dentro da caixa
    assert addon.perguntas._pergunta_atual[0] and addon.perguntas._pergunta_atual[0]['na_gaveta'], \
        'a pergunta devia estar na gaveta'
    m.mover(*widget(janela, lambda v: v[5] == ('resposta', 0)))
    yield
    m.clicar()
    yield
    assert prateleira.parent == conj, 'nao entrou no modulo'
    assert addon.solda.agregado(prateleira)
    lo = min(p.x for p in addon.chapas._cantos(prateleira))
    assert abs(lo - fora_x) < 1e-5, "a ponta nao foi ate' a lateral (%f)" % lo
    for o in chapas:
        for a, b in zip(o.matrix_world, fixos[o.name]):
            assert (a - b).length < 1e-6, 'o modulo foi puxado (%s)' % o.name


def _vista_do_lado_direito(janela):
    area, regiao, rv3d = viewport(janela)
    rv3d.view_rotation = Euler((math.radians(70), 0,
                                math.radians(20))).to_quaternion()
    rv3d.view_location = (0.6, 0, 0.2)
    rv3d.view_distance = 2.4
    return area, regiao, rv3d


def test_alvo_primeiro_peca_de_fora_por_ultimo_conecta(janela, m):
    # Clique no modulo (o alvo), Shift+clique na prateleira a 3 mm (a
    # peca de fora, que vira o ativo), botao Corrente: conecta por
    # distancia -> "Juntar ao modulo?" -> Sim. O modulo NAO e' puxado.
    conj = criar_modulo(janela)
    chapas = addon.modulos._chapas_do_conjunto(conj)
    direita = max(chapas, key=lambda o: o.matrix_world.translation.x)
    fixos = {o.name: o.matrix_world.copy() for o in chapas}
    fora_x = max(p.x for p in addon.chapas._cantos(direita))
    prateleira = addon.chapas.nova_chapa('Prateleira', 400.0, 300.0, 18.0,
                                  (fora_x * 1000.0 + 3.0 + 200.0, 0, 300.0),
                                  (0, 0, 0), bpy.context)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.update()
    area, regiao, rv3d = _vista_do_lado_direito(janela)
    yield
    # a lateral direita: o centro do modulo fica embaixo da gaveta
    direita = max(chapas, key=lambda o: o.matrix_world.translation.x)
    m.mover(*na_tela(regiao, rv3d, direita.matrix_world.translation))
    yield
    m.clicar()
    yield
    assert set(bpy.context.selected_objects) == set(addon.selecao.familia_de(conj)),         'o clique nao pegou o modulo: %s' % bpy.context.selected_objects
    m.mover(*na_tela(regiao, rv3d, prateleira.matrix_world.translation))
    yield
    m.clicar(shift=True)
    yield
    assert bpy.context.view_layer.objects.active == prateleira,         'a peca de fora nao virou o ativo'
    assert all(o.select_get() for o in chapas), 'o Shift perdeu o alvo: %s' % (
        [o.name for o in bpy.context.selected_objects],)
    with contexto(janela, *gaveta(janela)):
        acao = addon.solda._acao_corrente(bpy.context)
    assert acao[:2] == ('conectar', prateleira), acao
    m.mover(*widget(janela, lambda v: v[5][:2] == (
        'operador', addon.solda.OP_CORRENTE_OBJETO)))
    yield
    m.clicar()
    yield
    assert addon.solda._conexao_pendente[0] is not None, 'sem "Juntar ao modulo?"'
    # veio de um botao da GAVETA: a pergunta esta' NELA (caixa preta),
    # nao em pop-up -- clica no "Sim, juntar" de dentro da caixa
    assert addon.perguntas._pergunta_atual[0] and addon.perguntas._pergunta_atual[0]['na_gaveta'], \
        'a pergunta devia estar na gaveta'
    m.mover(*widget(janela, lambda v: v[5] == ('resposta', 0)))
    yield
    m.clicar()
    yield
    assert prateleira.parent == conj, 'nao entrou no modulo'
    assert addon.solda.agregado(prateleira)
    lo = min(p.x for p in addon.chapas._cantos(prateleira))
    assert abs(lo - fora_x) < 1e-5, "a folga nao fechou (%f)" % lo
    for o in chapas:
        for a, b in zip(o.matrix_world, fixos[o.name]):
            assert (a - b).length < 1e-6, 'o modulo foi puxado (%s)' % o.name


def test_botao_corrente_no_grupo_pergunta_antes_de_desagregar(janela, m):
    conj = criar_modulo(janela)
    chapas = addon.modulos._chapas_do_conjunto(conj)
    area, regiao, rv3d = _vista_do_lado_direito(janela)
    bpy.ops.object.select_all(action='DESELECT')
    yield
    # a lateral direita: o centro do modulo fica embaixo da gaveta
    direita = max(chapas, key=lambda o: o.matrix_world.translation.x)
    m.mover(*na_tela(regiao, rv3d, direita.matrix_world.translation))
    yield
    m.clicar()
    yield
    assert set(bpy.context.selected_objects) == set(addon.selecao.familia_de(conj)),         'o clique nao pegou o modulo: %s' % bpy.context.selected_objects
    m.mover(*widget(janela, lambda v: v[5][:2] == (
        'operador', addon.solda.OP_CORRENTE_OBJETO)))
    yield
    m.clicar()
    yield
    assert addon.solda._desagregar_pendente[0] == sorted(o.name for o in chapas),         'sem "tem certeza que deseja desagregar todos os itens?" %s %s %s' % (
            addon.solda._desagregar_pendente[0],
            [o.name for o in bpy.context.selected_objects],
            bpy.context.view_layer.objects.active)
    assert all(o.parent == conj for o in chapas), 'desagregou sem perguntar'
    nome = conj.name
    # veio de um botao da GAVETA: a pergunta esta' NELA (caixa preta),
    # nao em pop-up -- clica no "Sim, desagregar" de dentro da caixa
    assert addon.perguntas._pergunta_atual[0] and addon.perguntas._pergunta_atual[0]['na_gaveta'], \
        'a pergunta devia estar na gaveta'
    m.mover(*widget(janela, lambda v: v[5] == ('resposta', 0)))
    yield
    m.clicar()
    yield
    assert nome not in bpy.data.objects, 'o modulo vazio ficou'
    assert all(o.parent is None and not addon.solda.agregado(o) for o in chapas)


def test_digitar_no_campo_da_gaveta(janela, m):
    chapa = addon.chapas.nova_chapa('Campo', 600.0, 400.0, 18.0, (0, 0, 0),
                             (0, 0, 0), bpy.context)
    selecionar(janela, chapa, individual=True)
    yield
    m.mover(*widget(janela, lambda v: v[5][0] == 'medida'
                    and v[5][3] == 'Largura'))
    yield
    m.clicar()
    yield
    m.digitar('750')
    m.tecla('RET')
    yield
    assert abs(chapa.chapa_largura_mm - 750.0) < 1e-3, chapa.chapa_largura_mm
    assert abs(chapa.dimensions.x - 0.75) < 1e-5


def test_comodo_e_copiar_orcamento_pela_gaveta(janela, m):
    # Orcamento do ERP: a linha do comodo expande, o clique na opcao poe
    # o armario na PASTA do comodo (Outliner) e fecha a lista; o botao
    # copia e diz na propria gaveta o que fez ("copiar e nada acontece").
    # A area de transferencia do usuario volta como estava no fim.
    conj = criar_modulo(janela)
    selecionar(janela, addon.modulos._chapas_do_conjunto(conj)[0])
    bpy.context.scene.cabinet_aba = 'MODULOS'
    yield
    yield
    wm = bpy.context.window_manager
    antes = wm.clipboard
    try:
        m.mover(*widget(janela, lambda v: v[5][:2] == (
            'suspenso', addon.orcamento.SUSPENSO_COMODO)))
        yield
        m.clicar()
        yield
        m.mover(*widget(janela, lambda v: v[5][0] == 'escolha'
                        and v[5][5] == addon.orcamento.ALVO_COMODO
                        and v[5][2] == 'Cozinha'))
        yield
        m.clicar()
        yield
        comodo = addon.orcamento._comodo_do_modulo(conj)
        assert comodo is not None and comodo.name == 'Cozinha', comodo
        assert bpy.context.screen.get(addon.gaveta._CHAVE_SUSPENSO, '') == '', \
            'a lista devia fechar depois da escolha'
        m.mover(*widget(janela, lambda v: v[5][:2] == (
            'operador', addon.orcamento.OP_EXPORTAR_ORCAMENTO)))
        yield
        m.clicar()
        yield
        copiado = wm.clipboard
        assert copiado == addon.orcamento.orcamento_da_cena(bpy.context.scene)[0]
        assert '### Cozinha\n- %s\n' % conj.name in copiado, copiado
        widget(janela, lambda v: v[5][:2] == (
            'operador', addon.orcamento.OP_EXPORTAR_ORCAMENTO) and v[5][2]
            and v[4].startswith('Copiado: 1 modulo(s)'))
    finally:
        wm.clipboard = antes
        addon.orcamento._apagar_orcamento_copiado()


def test_criar_puxador_no_topo_da_aba(janela, m):
    # Mesmo padrao do "Criar Portas": topo da aba, laranja; o clique
    # comeca o posicionamento e o botao avisa enquanto ele dura.
    bpy.context.scene.cabinet_aba = 'PUXADORES'
    yield
    m.mover(*widget(janela, lambda v: v[5][0] == 'criar_puxador'))
    yield
    m.clicar()
    yield
    try:
        assert addon.puxadores._posicionador_puxador[0] is not None, 'nao comecou'
        widget(janela, lambda v: v[5][0] == 'criar_puxador' and v[5][2]
               and v[4].startswith('Posicionando'))
    finally:
        m.tecla('ESC')
        yield
    assert addon.puxadores._posicionador_puxador[0] is None, 'Esc devia encerrar'


rodar([test_gaveta_abre_na_largura_com_medidas_em_linha,
       test_clique_na_aba_troca_a_aba,
       test_arrastar_a_divisoria,
       test_roda_rola_so_a_biblioteca,
       test_duplo_clique_na_foto_insere_no_cursor,
       test_clique_na_foto_e_depois_na_viewport_posiciona,
       test_clique_na_viewport_seleciona_o_modulo,
       test_arrastar_a_seta_da_hud_estica_com_a_quina_parada,
       test_clicar_na_seta_e_digitar_a_medida,
       test_digitar_no_campo_da_gaveta,
       test_comodo_e_copiar_orcamento_pela_gaveta,
       test_criar_puxador_no_topo_da_aba,
       test_digitar_com_operador_e_cursor_no_meio,
       test_wizard_quatro_cliques_meia_chapa_vira_curva,
       test_wizard_basculante_com_pistoes,
       test_wizard_cobertura_fora_do_padrao_pergunta,
       test_alt_arrasta_o_canto_da_porta,
       test_slider_abre_a_folha,
       test_resetar_pela_gaveta_move_a_chapa_ativa,
       test_regua_da_viewport_com_o_modulo_ativo_adapta_o_modulo,
       test_regua_que_muda_a_medida_pergunta_e_espera,
       test_arrastar_a_bolinha_troca_a_ancora,
       test_clique_dentro_do_campo_da_gaveta_move_o_cursor,
       test_selecao_da_porta_e_da_folha,
       test_shift_soma_chapas_individuais_e_grupos,
       test_dois_modulos_selecionados_editam_pela_hud_os_dois,
       test_quina_com_ctrl_gruda_na_quina_de_outro_modulo,
       test_ctrl_z_com_o_mouse_na_hud_esquece_o_objeto,
       test_hover_acende_o_botao_pelo_gizmo_da_gaveta,
       test_definir_frente_com_clique_na_face,
       test_alt_arrasta_o_puxador_para_outra_borda,
       test_escalar_o_modulo_com_S,
       test_clique_na_corrente_desassocia,
       test_clique_na_corrente_tira_a_peca_do_modulo,
       test_botao_corrente_associa_por_vertices_e_junta,
       test_alvo_primeiro_peca_de_fora_por_ultimo_conecta,
       test_botao_corrente_no_grupo_pergunta_antes_de_desagregar],
      preparar=preparar, limpar=limpar)
