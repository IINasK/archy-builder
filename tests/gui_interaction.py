"""Interface tests: simulated clicks and keystrokes in a real window.

Run through the harness (opens a Blender window; about one minute):
    blender --background --factory-startup --python tests/run_tests.py -- --gui --suites gui_interacao

Covers behavior unavailable to headless tests: real keymaps, gizmo hover and modal event sequences. One such gap (the second double-click event arrives as PRESS) left photo double-clicking broken without a failing test."""
import math
import os
import sys
import time
import json
import tempfile
import shutil

import bpy
from mathutils import Euler, Vector
from mathutils.geometry import intersect_line_plane
from bpy_extras import view3d_utils

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import archy_builder as addon  # noqa: E402
from interaction_harness import (rodar, esperar, viewport_principal, na_tela,  # noqa: E402
                         Pular)


# Registration schedules catalog work, so the entire suite uses a copy beforehand.
_REAL = addon.opcoes._pasta_addon()
_GUARDA = tempfile.mkdtemp(prefix='cabinet_gui_guard_')
with open(os.path.join(_REAL, 'indice.json'), encoding='utf-8') as f:
    _indice = json.load(f)
_amostra, _contagem = [], {}
for _it in _indice:
    _caminho = addon.biblioteca.caminho_de(_it)
    if _contagem.get(_caminho, 0) >= 2:
        continue
    _contagem[_caminho] = _contagem.get(_caminho, 0) + 1
    _amostra.append(_it)
    for _nome in (_it['arquivo'], os.path.splitext(_it['arquivo'])[0] + '.png'):
        if os.path.isfile(os.path.join(_REAL, _nome)):
            shutil.copyfile(os.path.join(_REAL, _nome), os.path.join(_GUARDA, _nome))
with open(os.path.join(_GUARDA, 'indice.json'), 'w', encoding='utf-8') as f:
    json.dump(_amostra, f)
addon.biblioteca.pasta_biblioteca = lambda: _GUARDA
addon.opcoes._pasta_addon = lambda: _GUARDA


# ------------------------------------------------------------- helpers
def gaveta(janela):
    area = addon.gaveta._area_gaveta(janela.screen)
    assert area is not None, 'the sidebar did not open'
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def contexto(janela, area, regiao):
    return bpy.context.temp_override(window=janela, screen=janela.screen,
                                     area=area, region=regiao)


def viewport(janela):
    area = addon.biblioteca_faixa.viewport(janela.screen)
    regiao = next(r for r in area.regions if r.type == 'WINDOW')
    return area, regiao, area.spaces.active.region_3d


def widget(janela, teste):
    """Return the window-coordinate center of the clickable sidebar widget satisfying teste(v)."""
    for area in (addon.gaveta._area_gaveta(janela.screen),
                 addon.biblioteca_faixa.area_da_faixa(janela.screen)):
        if area is None:
            continue
        regiao = next(r for r in area.regions if r.type == 'WINDOW')
        with contexto(janela, area, regiao):
            widgets = addon.gaveta._widgets_interativos(bpy.context)
        v = next((v for v in widgets if v[5] and teste(v)), None)
        if v is not None:
            x, y, w, h = v[:4]
            return regiao.x + x + w / 2, regiao.y + y + h / 2
    raise AssertionError('widget not found in the interface')


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


def exigir_biblioteca_legivel():
    """These presets were saved by Blender 5.x; 4.x cannot read their .blend format ("not a blend file"). The click test cannot establish anything in that case; the file failure is recorded separately."""
    if bpy.app.version < (5, 0, 0):
        raise Pular('library uses Blender 5.x .blend format: %s cannot read it'
                    % bpy.app.version_string)


def mostrar_chapas_na_biblioteca(cena):
    cena.chapa_n1 = "Panels"
    cena.chapa_n2 = (addon.biblioteca._filhos_n2("Panels") or [''])[0]
    cena.chapa_n3 = ''


def preparar(janela):
    addon.register()
    area, regiao, _ = viewport_principal(janela)
    with contexto(janela, area, regiao):
        bpy.ops.object.cabinet_alternar_gaveta()


def limpar(janela):
    addon.areas_criacao.esquecer()
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    cena = bpy.context.scene
    cena.cabinet_aba = 'MODULOS'
    cena.cursor.location = (0.0, 0.0, 0.0)
    for nome in addon.portas._PROPS_PORTAS_CENA:
        cena.property_unset(nome)
    cena.chapa_n1, cena.chapa_n2, cena.chapa_n3 = "Cabinets", '', ''
    cena.cabinet_bib_modo = 'MODULOS'
    cena.cabinet_mat_n1 = cena.cabinet_mat_n2 = cena.cabinet_mat_n3 = ''
    addon.materiais._apagar_pendente[0] = None
    tela = janela.screen
    for chave in (addon.gaveta._CHAVE_ROLAGEM, addon.gaveta._CHAVE_ROLAGEM_BIB,
                  addon.gaveta._CHAVE_DIVISA, addon.gaveta._CHAVE_OPCOES):
        tela.pop(chave, None)
    addon.hud._hover_hud.clear()
    addon.portas_viewport._arraste_canto_porta[0] = None
    addon.portas_viewport._arraste_slider_porta[0] = None
    addon.gavetas.esquecer()
    addon.prateleiras.esquecer()
    addon.hud._edicao_hud[0] = None
    addon.solda._tecla_corrente_segurada[0] = False
    addon.solda._conexao_pendente[0] = None
    addon.solda._desagregar_pendente[0] = None
    addon.solda._pergunta_reset[0] = ''
    addon.perguntas._pergunta_atual[0] = None
    addon.solda._arraste_ancora[0] = None


# ------------------------------------------------------------ tests
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
        'L/A/P/E did not stay on the same line: %r' % [v[:4] for v in medidas]


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


def test_redimensiona_altura_da_biblioteca(janela, m):
    area = addon.biblioteca_faixa.area_da_faixa(janela.screen)
    regiao = next(r for r in area.regions if r.type == 'WINDOW')
    antes = area.height
    m.mover(area.x + area.width // 2, area.y)
    yield
    yield
    with contexto(janela, area, regiao):
        addon.biblioteca_faixa.redimensionar_altura(bpy.context, antes + 40, (m.x,m.y))
    yield esperar(0.4)
    assert abs(area.height - (antes + 40)) < 4, (antes, area.height)
    with contexto(janela, area, regiao):
        addon.biblioteca_faixa.redimensionar_altura(bpy.context, antes, (m.x,m.y))
    yield esperar(0.4)


def test_roda_rola_so_a_biblioteca(janela, m):
    s = bpy.context.scene
    s.cabinet_bib_modo = 'MATERIAIS'
    s.cabinet_mat_n1, s.cabinet_mat_n2, s.cabinet_mat_n3 = 'MDF', 'Roda', ''
    addon.materiais.gravar_materiais([dict(nome='Cor %02d' % i, n1='MDF', n2='Roda',
                                         n3='', cor='#888888') for i in range(30)])
    addon.biblioteca_faixa.invalidar()
    yield
    area = addon.biblioteca_faixa.area_da_faixa(janela.screen)
    regiao = next(r for r in area.regions if r.type == 'WINDOW')
    with contexto(janela, area, regiao):
        antes = next(v[5][1]['nome'] for v in addon.gaveta._widgets_interativos(bpy.context)
                     if v[5] and v[5][0] == 'material')
    m.mover(*widget(janela, lambda v: v[5][0] == 'material'))
    yield
    m.clicar('WHEELDOWNMOUSE')
    yield
    with contexto(janela, area, regiao):
        depois = next(v[5][1]['nome'] for v in addon.gaveta._widgets_interativos(bpy.context)
                      if v[5] and v[5][0] == 'material')
    assert depois != antes, (antes, depois)
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
    yield esperar(0.05)      # Well within the double-click interval.
    m.clicar()
    yield esperar(0.3)
    novos = [o for o in bpy.data.objects if o not in antes]
    assert novos, 'double click inserted nothing'
    assert all(not o.hide_get() for o in novos), 'remained hidden in staging'
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
    yield esperar(0.6)       # Past the double-click interval: this is a single click.
    area, regiao, rv3d = viewport(janela)
    destino = Vector((1.0, 0.5, 0.0))
    x, y = na_tela(regiao, rv3d, destino)
    for t in (0.25, 0.5, 0.75, 1.0):
        m.mover(m.x + (x - m.x) * t, m.y + (y - m.y) * t)
        yield
    m.clicar()
    yield esperar(0.2)
    novos = [o for o in bpy.data.objects if o not in antes]
    assert novos, 'the placement tool inserted nothing'
    # Where the mouse ray intersects the cursor plane in an empty scene.
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
    """Center the view close to the cabinet; the factory view leaves it only a few pixels wide, making its edge hard to target."""
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
    raise AssertionError('no sufficiently visible L line: geometry=%s lines=%r' % (geometria is not None, [
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


def test_circulo_da_face_translate_b_esc_e_undo(janela, m):
    conj = criar_modulo(janela)
    nome = conj.name
    selecionar(janela, addon.modulos._chapas_do_conjunto(conj)[0])
    aproximar(janela, conj)
    yield
    yield
    area, regiao, rv3d = viewport(janela)
    geo = addon.hud._geometria_do_item(conj, 'GRUPO', addon.modulos._chapas_do_conjunto(conj))
    controle = next(c for c in addon.hud_volume.controles(geo)
                    if c['eixo'] == 0 and c['lado'] == 'min')
    inicio = Vector(na_tela(regiao, rv3d, controle['pontos'][1]))
    largura = conj.conj_largura_mm
    cursor = bpy.context.scene.cursor.location.copy()
    m.mover(*inicio)
    yield
    m.apertar()
    yield
    m.mover(*(inicio + Vector((15, 0))))
    yield
    assert addon.hud_volume._estado[0] is not None
    m.tecla('B')
    yield
    # Esc also cancels while choosing the native snap base.
    m.tecla('ESC')
    m.soltar()
    yield
    assert addon.hud_volume._estado[0] is None
    assert abs(bpy.data.objects[nome].conj_largura_mm - largura) < .01
    assert (bpy.context.scene.cursor.location - cursor).length < 1e-6
    m.mover(*inicio)
    yield
    m.apertar()
    yield
    m.mover(*(inicio + Vector((15, 0))))
    yield
    m.digitar('50mm')
    m.tecla('RET')
    m.soltar()
    yield
    yield
    assert addon.hud_volume._estado[0] is None
    assert abs(bpy.data.objects[nome].conj_largura_mm - largura - 50) < .1
    with contexto(janela, area, regiao):
        bpy.ops.ed.undo()
    yield
    assert abs(bpy.data.objects[nome].conj_largura_mm - largura) < .01


def test_snap_b_depois_de_arrastar_face_nao_soma_deslocamento_anterior(janela, m):
    # Regression v290: B uses the current position without returning the panel to
    # its starting point. Snapping covers only the remaining distance to the fixed target.
    conj=criar_modulo(janela);nome=conj.name
    chapas=addon.modulos._chapas_do_conjunto(conj)
    lo,hi=caixa_mundo(chapas)
    base=Vector((hi.x,lo.y,lo.z))
    destino=base+Vector((.12,0,0))
    area,regiao,rv3d=viewport(janela)
    with contexto(janela,area,regiao):
        bpy.ops.mesh.primitive_cube_add(size=.02,location=destino+Vector((.01,.01,.01)))
    selecionar(janela,chapas[0]);aproximar(janela,conj)
    yield
    yield
    geo=addon.hud._geometria_do_item(conj,'GRUPO',chapas)
    controle=next(c for c in addon.hud_volume.controles(geo) if c['eixo']==0 and c['lado']=='min')
    inicio=Vector(na_tela(regiao,rv3d,controle['pontos'][1]))
    largura=conj.conj_largura_mm
    m.mover(*inicio)
    yield
    m.apertar()
    yield
    m.mover(*(inicio+Vector((60,0))))
    yield
    yield
    assert abs(conj.conj_largura_mm-largura)>1,'no preview appeared before B'
    largura_ao_apertar_b=conj.conj_largura_mm
    lo_atual,hi_atual=caixa_mundo(chapas)
    base_atual=Vector((hi_atual.x,lo_atual.y,lo_atual.z))
    m.tecla('B')
    yield
    assert abs(conj.conj_largura_mm-largura_ao_apertar_b)<.05,'B lost the previous drag'
    assert abs(addon.hud_volume._estado[0]['deslocamento_base_mm']-(largura_ao_apertar_b-largura))<.05,'B did not reach the observer'
    m.mover(*na_tela(regiao,rv3d,base_atual))
    yield
    m.tecla('B')
    yield
    assert abs(conj.conj_largura_mm-largura_ao_apertar_b)<.05,'confirming the base changed the measurement'
    m.mover(*na_tela(regiao,rv3d,destino))
    yield
    yield
    m.tecla('RET')
    m.soltar()
    yield
    yield
    assert addon.hud_volume._estado[0] is None
    assert addon.hud_volume._timer_observador[0] is None
    assert abs(bpy.data.objects[nome].conj_largura_mm-largura-120)<.2
    with contexto(janela,area,regiao):
        bpy.ops.ed.undo()
    yield
    assert abs(bpy.data.objects[nome].conj_largura_mm-largura)<.05


def test_snap_b_gavetas_em_corpo_dobrado_e_girado_alinha_vertice_real(janela, m):
    g=addon.gavetas
    conj=criar_modulo(janela)
    area,regiao,rv3d=viewport(janela)
    with contexto(janela,area,regiao):
        grupo=g.criar_gavetas(bpy.context,conj,(18,18,18,18,0),dict(quantidade=4,profundidade_mm=280))
    nome=grupo.name;largura=g.medidas(grupo)[0]
    conj.conj_largura_mm*=2
    conj.rotation_euler.z=math.pi/2
    bpy.context.view_layer.update()
    assert abs(g.medidas(grupo)[0]-largura)<.02
    inv=grupo.matrix_world.inverted();eixo=grupo.matrix_world.to_3x3().normalized().col[0]
    def ponta_da_frente():
        frente=g.frente_da_gaveta(g.gavetas_do_grupo(grupo)[0])
        return max((frente.matrix_world@v.co for v in frente.data.vertices),
                   key=lambda p:(round((inv@p).x,6),-round((inv@p).z,6),-round((inv@p).y,6)))
    base=ponta_da_frente()
    corpo=addon.modulos._chapas_do_conjunto(conj)
    destino=max((o.matrix_world@v.co for o in corpo for v in o.data.vertices),
                key=lambda p:(round((inv@p).x,6),-round((inv@p).z,6),-round((inv@p).y,6)))
    esperado=largura+(destino-base).dot(eixo)*1000
    with contexto(janela,area,regiao):g.selecionar(bpy.context,grupo,'GRUPO')
    aproximar(janela,conj)
    yield
    yield
    geo=addon.hud._geometria_do_item(grupo,'GAVETAS',[])
    controle=next(c for c in addon.hud_volume.controles(geo) if c['eixo']==0 and c['lado']=='min')
    inicio=Vector(na_tela(regiao,rv3d,controle['pontos'][1]))
    direcao=(Vector(na_tela(regiao,rv3d,controle['pontos'][1]+eixo*.1))-inicio).normalized()
    m.mover(*inicio)
    yield
    m.apertar()
    yield
    m.mover(*(inicio+direcao*45))
    yield
    yield
    atual=g.medidas(grupo)[0]
    assert abs(atual-largura)>1,'no drawer preview appeared'
    base_atual=ponta_da_frente()
    m.tecla('B')
    yield
    assert abs(g.medidas(grupo)[0]-atual)<.05,'drawers reverted to their previous size'
    assert abs(addon.hud_volume._estado[0]['deslocamento_base_mm']-(atual-largura))<.05,'B was not recognized'
    m.mover(*na_tela(regiao,rv3d,base_atual))
    yield
    m.tecla('B')
    yield
    m.mover(*na_tela(regiao,rv3d,destino))
    yield
    yield
    m.tecla('RET')
    m.soltar()
    yield
    yield
    assert addon.hud_volume._estado[0] is None
    assert abs(g.medidas(grupo)[0]-esperado)<.2
    assert abs((ponta_da_frente()-destino).dot(eixo))<.0002
    with contexto(janela,area,regiao):bpy.ops.ed.undo()
    yield
    assert abs(g.medidas(bpy.data.objects[nome])[0]-largura)<.05


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
    m.clicar('A', ctrl=True)
    m.digitar('800')
    m.tecla('RET')
    yield
    assert abs(conj.conj_largura_mm - 800.0) < 1e-3, conj.conj_largura_mm
    nova = addon.hud._geometria_do_item(conj, 'GRUPO',
                                    addon.modulos._chapas_do_conjunto(conj))
    assert (nova['cantos'][linha['cantos'][0]] - fixa).length < 1e-4


def test_clique_dentro_do_campo_da_gaveta_move_o_cursor(janela, m):
    # The sidebar field behaves like the HUD: clicking during editing moves the cursor
    # without confirming; Backspace, undo and selection require explicit commands.
    chapa = addon.chapas.nova_chapa('Campo', 600.0, 400.0, 18.0, (0, 0, 0),
                             (0, 0, 0), bpy.context)
    selecionar(janela, chapa, individual=True)
    yield
    campo = lambda v: v[5][0] == 'medida' and v[5][3] == "Width"
    cx, cy = widget(janela, campo)
    m.mover(cx, cy)
    yield
    m.clicar()
    yield
    estado = addon.gaveta._edicao_gaveta[0]
    assert estado is not None, 'the field did not open'
    assert not estado['selecionado'], estado
    m.tecla('BACK_SPACE')
    yield
    assert estado['texto'] == '60', estado['texto']
    m.clicar('Z', ctrl=True)
    yield
    assert estado['texto'] == '600', estado['texto']
    m.clicar('A', ctrl=True)
    yield
    assert estado['selecionado'], estado
    m.tecla('RIGHT_ARROW')
    yield
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
    # Immediately after the 6 (text starts at x + 7).
    m.mover(regiao.x + x + 7 + addon.gaveta_desenho._medidor_blf(12)('6') + 1, cy)
    yield
    m.clicar()
    yield
    assert addon.gaveta._edicao_gaveta[0] is estado, 'clicking the field ended editing'
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
    # User screenshot: the side panel moved away from the niche. Selected alone,
    # it has a blue sidebar ruler button; clicking restores its welded position.
    conj, chapas, direita, origem = _nicho_com_lateral_afastada(janela)
    selecionar(janela, direita, individual=True)
    yield
    yield
    regua = lambda v: v[5][:2] == ('operador', addon.solda.OP_RESETAR_DISTANCIA)
    area, regiao = gaveta(janela)
    with contexto(janela, area, regiao):
        botao = next(v for v in addon.gaveta._widgets_interativos(bpy.context)
                     if v[5] and regua(v))
    assert botao[5][2] is True, 'the button should be blue with the weld displaced'
    m.mover(*widget(janela, regua))
    yield
    m.clicar()
    yield
    for a, b in zip(direita.matrix_world, origem):
        assert (a - b).length < 1e-5, 'the side panel did not return'
    assert addon.solda._pontas_fora_do_lugar(chapas) == [], 'welds out of position'


def test_regua_da_viewport_com_o_modulo_ativo_adapta_o_modulo(janela, m):
    # Alt: all welded corners away from their origins have a chain and ruler.
    # With the cabinet active, the cabinet adapts to the stationary side panel.
    conj, chapas, direita, _origem = _nicho_com_lateral_afastada(janela)
    lateral = direita.matrix_world.copy()
    largura = conj.conj_largura_mm
    selecionar(janela, direita)                   # Click target: the cabinet.
    area, regiao, rv3d = viewport(janela)
    yield
    yield
    m.janela.event_simulate('LEFT_ALT', 'PRESS', alt=True, x=m.x, y=m.y)
    yield
    with contexto(janela, area, regiao):
        correntes = addon.solda._correntes_hud(bpy.context)
        visiveis = [c for c in correntes if c['meio'] is not None]
        assert len(correntes) == 4, '%d welded corners' % len(correntes)
        assert visiveis, 'no corner onscreen'
        centro = addon.solda._botoes_da_corrente(bpy.context, visiveis[0])['regua']
    m.mover(regiao.x + centro.x, regiao.y + centro.y)
    yield
    yield
    m.clicar(alt=True)
    yield
    m.janela.event_simulate('LEFT_ALT', 'RELEASE', x=m.x, y=m.y)
    yield
    for a, b in zip(direita.matrix_world, lateral):
        assert (a - b).length < 1e-5, 'the side panel moved instead of the cabinet'
    assert addon.solda._pontas_fora_do_lugar(chapas) == [], 'welds out of position'
    assert abs(conj.conj_largura_mm - (largura + 200.0)) < 0.5, \
        conj.conj_largura_mm


def test_regua_que_muda_a_medida_pergunta_e_espera(janela, m):
    # Extreme case: the top shrank and, selected alone, can only reach its right weld
    # by stretching. The ruler asks whether to move anyway; the question must wait:
    # releasing the click that opened it must not answer it.
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
    assert addon.solda._pergunta_reset[0] == tampo.name, 'no confirmation prompt appeared'
    assert abs(tampo.chapa_largura_mm - largura) < 1e-6, \
        'releasing the opening click answered the prompt'
    # Opened from the viewport ruler, so this question uses a popup.
    assert not addon.perguntas._pergunta_atual[0]['na_gaveta'], 'the ruler prompt should be a popup'
    m.tecla('ESC')                               # Close the popup.
    yield
    with contexto(janela, area, regiao):
        assert bpy.ops.object.cabinet_resetar_distancia(
            chapa=tampo.name, forcar=True) == {'FINISHED'}
    assert abs(tampo.chapa_largura_mm - (largura + 250.0)) < 0.01


def test_arrastar_a_bolinha_troca_a_ancora(janela, m):
    # Alt: white dots mark line endpoints. Dragging the side panel's dot to another
    # vertex changes only its anchor; the ruler subsequently moves the panel
    # to that position.
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
        assert correntes, 'no dot onscreen'
        corrente = correntes[0]
        inicio = addon.solda._bolinhas_da_corrente(bpy.context, corrente)['b']
    tampo, ponta, k = corrente['a'], corrente['ponta'], corrente['indice']
    antes = addon.solda._ancoras_da_ligacao(tampo, ponta, direita)[k]
    # Target: another side-panel vertex visible on screen.
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
    assert addon.solda._arraste_ancora[0] is not None, 'the dot did not start dragging'
    for passo in range(1, 6):
        ponto = inicio + (alvo - inicio) * (passo / 5)
        m.mover(regiao.x + ponto.x, regiao.y + ponto.y)
        yield
    m.soltar(alt=True)
    yield
    m.janela.event_simulate('LEFT_ALT', 'RELEASE', x=m.x, y=m.y)
    yield
    assert addon.solda._arraste_ancora[0] is None, 'the drag did not finish'
    gravadas = addon.solda._ancoras_gravadas(tampo, ponta)
    assert gravadas and gravadas[k] == (antes[0], destino), gravadas


def _wizard_ate_o_tipo(janela, m):
    """Front-facing cabinet, sidebar Create Doors action and two opposite inner corners. Return (conj, area, regiao, rv3d)."""
    conj = criar_modulo(janela)
    area, regiao, rv3d = viewport(janela)
    rv3d.view_rotation = Euler((math.pi / 2, 0, 0)).to_quaternion()
    lo, hi = caixa_mundo(addon.modulos._chapas_do_conjunto(conj))
    rv3d.view_location = (lo + hi) / 2
    rv3d.view_distance = 1.6
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.scene.cabinet_aba = 'PORTAS'
    return conj, area, regiao, rv3d


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


def _contador_ate(janela, m, prop, valor):
    """Click the counter halves (right increments, left decrements) until reaching valor."""
    for _ in range(8):
        area, regiao = gaveta(janela)
        with contexto(janela, area, regiao):
            v = next(v for v in addon.gaveta._widgets_interativos(bpy.context)
                     if v[5] and v[5][0] == 'contador' and v[5][1] == prop)
        if v[5][2] == valor:
            return
        x = v[0] + v[2] * (0.85 if valor > v[5][2] else 0.15)
        m.mover(regiao.x + x, regiao.y + v[1] + v[3] / 2)
        yield
        m.clicar()
        yield
    raise AssertionError('the counter did not reach %s' % valor)


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
    """Return the choices currently shown in the Doors tab, from top to bottom."""
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
    assert addon.portas._assistente_porta[0] is not None, 'Create Doors did not open'


def test_wizard_dois_cliques_meia_chapa_vira_curva(janela, m):
    # Two opposite limits resolve the opening without selecting other corners.
    # A door covering half of each side panel uses a half-overlay hinge automatically.
    # Then choose leaves, opening, edge, count and margin.
    conj, area, regiao, rv3d = _wizard_ate_o_tipo(janela, m)
    yield
    yield
    yield from _abrir_wizard(janela, m)
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    y = -P / 2
    for ponto in ((-L / 2 + E / 2, y, A), (L / 2 - E / 2, y, 0)):
        yield from _clicar_no_mundo(m, regiao, rv3d, _local(conj, *ponto))
    w = addon.portas._assistente_porta[0]
    assert w['etapa'] == 'FOLHAS', w['etapa']
    assert [w['coberturas'][k] for k in addon.portas.COBERTURAS_LADOS] == [
        0.5, 0.5, 1.0, 1.0], w['coberturas']
    # The Doors tab mirrors the question once the wizard reaches that step.
    assert _filas_da_aba(janela) == ['porta_folhas'], _filas_da_aba(janela)
    yield from _clicar_botao_do_wizard(m, regiao, '1')
    assert w['etapa'] == 'TIPO', w['etapa']
    # An overlay sliding door includes a frame by default, as requested.
    assert [c for _r, c, _t in w['botoes']] == ['GIRO', 'BASCULANTE', 'CORRER']
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
    assert "Curve" in w['recado'], w['recado']
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
    assert addon.portas._assistente_porta[0] is None, 'the wizard did not finish'
    grupo = addon.portas._portas_do_conjunto(conj)[0]
    p = grupo['porta_parametros']
    assert p['dobradica'] == 'CURVA' and p['abertura'] == 'GIRO', dict(p)
    assert p['folhas'] == 1 and p['cobertura_esq_e'] == 0.5, dict(p)
    assert p['dobradicas_qtd'] == padrao + 1 and p['dobradica_lado'] == 'ESQUERDA'
    assert abs(p['dobradicas_margem_mm'] - margem) < 1e-3


def test_wizard_correr_metade_metade_pergunta_moldura(janela, m):
    # One inner and one opposite outer limit make sliding-door placement ambiguous;
    # the dialog and its sidebar copy ask whether the door is inset or framed.
    # A framed door uses the entire cabinet.
    conj, area, regiao, rv3d = _wizard_ate_o_tipo(janela, m)
    yield
    yield
    yield from _abrir_wizard(janela, m)
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    y = -P / 2
    for ponto in ((-L / 2 + E, y, A - E), (L / 2, y, 0)):
        yield from _clicar_no_mundo(m, regiao, rv3d, _local(conj, *ponto))
    w = addon.portas._assistente_porta[0]
    assert w['etapa'] == 'FOLHAS', w['etapa']
    yield from _clicar_na_fila(janela, m, 'porta_folhas', 2)
    assert w['etapa'] == 'TIPO', w['etapa']        # Two overlay leaves: hinged or sliding.
    yield from _clicar_na_fila(janela, m, 'porta_abertura', 'CORRER')
    assert w['etapa'] == 'MOLDURA', w['etapa']
    assert 'porta_tipo_correr' in _filas_da_aba(janela), _filas_da_aba(janela)
    yield from _clicar_na_fila(janela, m, 'porta_tipo_correr', 'MOLDURA')
    # Framed: choose whether the door has a base; no plinth means directly on the floor.
    assert w['etapa'] == 'BASE', w['etapa']
    assert 'porta_base' in _filas_da_aba(janela), _filas_da_aba(janela)
    yield from _clicar_na_fila(janela, m, 'porta_base', 'SEM')
    # Then choose a heavy or light track, as requested.
    assert w['etapa'] == 'TRILHO', w['etapa']
    assert 'porta_trilho' in _filas_da_aba(janela), _filas_da_aba(janela)
    yield from _clicar_na_fila(janela, m, 'porta_trilho', 'LEVE')
    yield
    assert addon.portas._assistente_porta[0] is None, 'the wizard did not finish'
    grupo = addon.portas._portas_do_conjunto(conj)[0]
    p = grupo['porta_parametros']
    assert [p[k] for k in addon.portas.COBERTURAS_LADOS] == [1.0] * 4, dict(p)
    assert p['rodape_mm'] == 0.0, dict(p)
    assert p['trilho'] == 'LEVE', dict(p)
    pecas = {o['porta_moldura_peca'] for o in addon.portas._moldura_da_porta(grupo)}
    # No base means no plinth; a light track has no fascia.
    assert pecas == {'LATERAL_ESQ', 'LATERAL_DIR', 'BASE_CIMA', 'BASE_BAIXO'}, pecas


def test_wizard_basculante_com_pistoes(janela, m):
    # Lift-up door: hinges always go at the top without asking for an edge;
    # gas struts use their automatic positions. Mouse movement along Y only raises them
    # because lowering would exceed their travel. An outer corner selects full overlay automatically.
    conj, area, regiao, rv3d = _wizard_ate_o_tipo(janela, m)
    yield
    yield
    yield from _abrir_wizard(janela, m)
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    y = -P / 2
    for ponto in ((-L / 2, y, A), (L / 2, y, 0)):
        yield from _clicar_no_mundo(m, regiao, rv3d, _local(conj, *ponto))
    w = addon.portas._assistente_porta[0]
    # Answer through the dialog copy in the Doors tab, as requested;
    # answering an earlier row again rebuilds the choices from there.
    yield from _clicar_na_fila(janela, m, 'porta_folhas', 1)
    assert w['etapa'] == 'TIPO', w['etapa']
    yield from _clicar_na_fila(janela, m, 'porta_abertura', 'GIRO')
    assert w['etapa'] == 'EIXO', w['etapa']
    # Once selected, the opening becomes a single thumbnail in the hinge row;
    # clicking it restores the three opening choices.
    yield from _clicar_na_fila(janela, m, 'porta_abertura', 'GIRO')
    assert w['etapa'] == 'TIPO', w['etapa']
    yield from _clicar_na_fila(janela, m, 'porta_abertura', 'BASCULANTE')
    assert w['etapa'] == 'QUANTIDADE', w['etapa']
    assert w['escolhas']['abertura'] == 'BASCULANTE', w['escolhas']
    # Hinges are editable in the sidebar, as requested: adjust their count through
    # the segments without advancing the step, and type their spacing.
    yield from _contador_ate(janela, m, 'dobradicas_qtd', 3)
    assert (w['qtd'], w['etapa']) == (3, 'QUANTIDADE'), (w['qtd'], w['etapa'])
    m.mover(*widget(janela, lambda v: v[5][0] == 'medida'
                    and v[5][2] == 'dobradicas_margem_mm'))
    yield
    m.clicar()
    yield
    m.clicar('A', ctrl=True)
    m.digitar('80')
    m.tecla('RET')
    yield
    assert abs(w['margem'] - 80.0) < 1e-6, w['margem']
    m.mover(regiao.x + regiao.width / 2, regiao.y + regiao.height / 2)
    yield
    assert w['aresta']['lado'] == 'CIMA'
    assert w['escolhas']['dobradica_lado'] == 'CIMA', w['escolhas']
    assert w['escolhas']['dobradica'] == 'RETA', w['escolhas']
    # Confirm count and spacing through the sidebar, as requested.
    yield from _clicar_na_fila(janela, m, 'confirmar_etapa', 'QUANTIDADE')
    assert w['etapa'] == 'MARGEM', w['etapa']
    yield from _clicar_na_fila(janela, m, 'confirmar_etapa', 'MARGEM')
    assert w['etapa'] == 'PISTOES_QTD', w['etapa']
    m.mover(regiao.x + regiao.width / 2, regiao.y + regiao.height / 2)
    yield
    assert abs(w['margem'] - 80.0) < 1e-6, w['margem']     # The wizard did not advance.
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
        m.mover(m.x, m.y - 8 * passo)             # Downward movement stops at the travel limit.
        yield
    assert abs(w['poffset'] - inicial) < 1e-6, (inicial, w['poffset'])
    assert 'curso maximo' in w['recado'], w['recado']
    for passo in range(1, 6):
        m.mover(m.x, m.y + 8 * passo)             # Upward movement raises the gas strut.
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


def test_wizard_diagonal_invalida_e_voltar_preservam_primeiro_canto(janela, m):
    conj, area, regiao, rv3d = _wizard_ate_o_tipo(janela, m)
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    y = -P / 2
    bpy.ops.object.select_all(action='DESELECT')
    yield
    yield
    yield from _abrir_wizard(janela, m)
    for ponto in ((-L / 2, y, A), (-L / 2, y, A)):
        yield from _clicar_no_mundo(m, regiao, rv3d, _local(conj, *ponto))
    w = addon.portas._assistente_porta[0]
    assert w['etapa'] == 'DIAGONAL', w['etapa']
    yield from _clicar_no_mundo(m, regiao, rv3d, _local(conj, L / 2, y, 0))
    assert w['etapa'] == 'FOLHAS', w['etapa']
    m.tecla('RIGHTMOUSE')
    yield
    assert w['etapa'] == 'DIAGONAL', w['etapa']
    m.tecla('ESC')
    yield
    assert addon.portas._assistente_porta[0] is None
    assert not addon.portas._portas_do_conjunto(conj)


def test_alt_arrasta_o_canto_da_porta(janela, m):
    # User request: a single door click shows wizard outlines; with Alt, the two
    # selection dots become handles, and dragging a corner rebuilds the door.
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
    assert addon.portas_viewport._arraste_canto_porta[0] is not None, 'the corner was not grabbed'
    # Dragging uses native cursor translation through a macro, without Python snapping.
    assert any(o.bl_idname.endswith('cabinet_mover_canto_porta')
               for o in m.janela.modal_operators), 'the drag did not start'
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
    # Phase 3 (Epic 4): a selected door has a slider at each leaf's base;
    # dragging right opens it, and the click must not select anything.
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
    # Use a real click on the leaf to select the door, as a user would.
    centro = folha.matrix_world.translation
    yield from _clicar_no_mundo(m, regiao, rv3d, centro)
    yield esperar(0.4)          # Avoid creating a double click.
    assert grupo in addon.portas_viewport._portas_com_cantos(bpy.context), 'the door was not selected'
    with contexto(janela, area, regiao):
        bpy.ops.ed.undo_push(message='Porta selecionada')
        inicio, fim = addon.portas_viewport._slider_na_tela(bpy.context, folha)
    # The dot at fraction 0 is a gizmo (VIEW3D_GT_slider_porta,
    # group VIEW3D_GGT_slider_porta), which receives events before any keymap.
    # The track outside it is inactive; hovering over the dot highlights it.
    with contexto(janela, area, regiao):
        assert addon.portas_viewport.VIEW3D_GGT_slider_porta.poll(bpy.context)
    # Size uses world millimeters, as requested: moving 3x farther away shrinks it about 3x.
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
    assert addon.portas_viewport._slider_hover[0] is None, 'the track captured hover'
    m.mover(regiao.x + inicio.x + raio * 0.6, regiao.y + inicio.y)
    yield
    yield
    assert addon.portas_viewport._slider_hover[0] == folha.name, 'the dot did not highlight'
    m.apertar()
    yield
    assert addon.portas_viewport._arraste_slider_porta[0] == folha.name, 'the slider was not grabbed'
    assert any(o.bl_idname.endswith('cabinet_abrir_porta')
               for o in m.janela.modal_operators), 'the drag did not start'
    meio = inicio.lerp(fim, 0.5)
    for passo in range(1, 5):
        # Grab at 0.6 radii from the center: the dot follows without jumping.
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
    # The door remains selected because the slider consumed the click.
    assert grupo in addon.portas_viewport._portas_com_cantos(bpy.context)
    # Ctrl+Z undoes opening.
    m.apertar('Z', ctrl=True)
    m.soltar('Z', ctrl=True)
    yield
    yield
    # Undo replaces the objects, so fetch them again; the old references are invalid.
    grupo = next(o for o in bpy.data.objects if addon.chapas.MARCA_PORTAS in o)
    folha = addon.portas._folhas_portas(grupo)[0]
    assert folha.get(addon.ferragens.CHAVE_ABERTURA, 0.0) == 0.0, folha.get(addon.ferragens.CHAVE_ABERTURA)


def test_digitar_com_operador_e_cursor_no_meio(janela, m):
    # User request: '+' continues the HUD expression without erasing "600";
    # clicking inside the field moves the cursor without closing it;
    # "6cm00" evaluates to 600 cm.
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
    # Repeat with "600", clicking beside the 6.
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
    assert addon.hud._edicao_hud[0] is not None, 'clicking the box ended editing'
    assert estado['cursor'] == 1, estado['cursor']
    m.digitar('cm')
    yield
    assert estado['texto'] == '6cm00', estado['texto']
    m.tecla('RET')
    yield
    assert abs(conj.conj_largura_mm - 6000.0) < 1e-3, conj.conj_largura_mm


def _duplo_clique_do_keymap(janela, shift=False):
    """Deliver the second double-click event as the keymap does. Blender's simulator does not generate DOUBLE_CLICK, so invoke the operator using the DOUBLE_CLICK entry properties from _ENTRADAS_KEYMAP, with the context and mouse position of a real click."""
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
    # Front view looking toward +Y places the leaf in front of everything.
    rv3d.view_rotation = Euler((math.pi / 2, 0, 0)).to_quaternion()
    lo, hi = caixa_mundo(addon.modulos._chapas_do_conjunto(conj))
    rv3d.view_location = (lo + hi) / 2
    yield
    yield
    m.mover(*na_tela(regiao, rv3d, folha.matrix_world.translation))
    yield
    portas = {grupo, *addon.portas._folhas_portas(grupo)}
    # User backlog (Epic 3): clicking a door selects the whole door,
    # never the cabinet; double-clicking selects one leaf.
    m.clicar()
    yield
    selecionados = set(bpy.context.selected_objects)
    assert selecionados == portas, 'click should select the DOOR; got %s' % (
        sorted(o.name for o in selecionados))
    assert bpy.context.view_layer.objects.active == grupo
    # Double click: the second keymap event is DOUBLE_CLICK and selects the leaf.
    m.clicar()
    yield
    _duplo_clique_do_keymap(janela)
    yield
    assert set(bpy.context.selected_objects) == {folha}, (
        'double click should select the LEAF; got %s'
        % sorted(o.name for o in bpy.context.selected_objects))
    # With only the leaf selected, the native orange outline remains disabled.
    espaco = area.spaces.active
    assert not espaco.overlay.show_outline_selected,         'the native outline returned with the leaf selected'
    # Click again to select the whole door.
    m.clicar()
    yield
    assert set(bpy.context.selected_objects) == portas


def test_correr_duplo_clique_na_folha_e_clique_no_trilho(janela, m):
    # User request: double-clicking a leaf selects it with the add-on's white outline;
    # the native outline stays disabled. Without this feedback selection looked inert.
    # Clicking the track highlights it like the hinges.
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
    assert addon.portas._editar_parametro_porta(
        bpy.context, grupo, 'abertura', 'CORRER') == ''
    folha = addon.portas._folhas_portas(grupo)[0]
    bpy.ops.object.select_all(action='DESELECT')
    rv3d.view_rotation = Euler((math.pi / 2, 0, 0)).to_quaternion()
    lo, hi = caixa_mundo(addon.modulos._chapas_do_conjunto(conj))
    rv3d.view_location = (lo + hi) / 2
    yield
    yield
    m.mover(*na_tela(regiao, rv3d, folha.matrix_world.translation))
    yield
    m.clicar()
    yield
    portas = {grupo, *addon.portas._folhas_portas(grupo)}
    assert set(bpy.context.selected_objects) == portas, sorted(
        o.name for o in bpy.context.selected_objects)
    m.clicar()
    yield
    _duplo_clique_do_keymap(janela)
    yield
    assert set(bpy.context.selected_objects) == {folha}, sorted(
        o.name for o in bpy.context.selected_objects)
    with contexto(janela, area, regiao):
        contornos = addon.portas_viewport._folhas_com_contorno(bpy.context)
    assert contornos == [folha], 'the individually selected leaf lost its white outline'
    # Upper track: its front wall, above the leaf.
    p = grupo['porta_parametros']
    ponto = grupo.matrix_world @ (Vector((
        grupo['porta_vao_largura_mm'] / 2,
        grupo['porta_vao_altura_mm'] - addon.ferragens.TRILHO_CIMA_ALTURA_MM / 2,
        -p['recuo_correr_mm'] + addon.ferragens.TRILHO_PAREDE_MM / 2)) / 1000.0)
    yield esperar(0.6)          # Avoid creating a double click.
    m.mover(*na_tela(regiao, rv3d, ponto))
    yield
    m.clicar()
    yield
    with contexto(janela, area, regiao):
        edicao = addon.ferragens._ferragens_em_edicao(bpy.context)
    assert [(g, t) for g, t in edicao] == [(grupo, {'TRILHO'})], edicao
    with contexto(janela, area, regiao):
        _pecas, pontos = addon.arame._arame_ferragens(grupo, {'TRILHO'})
    assert pontos, 'the selected track lost its wireframe'


def _modulo_em(janela, x):
    """Create a cabinet (grouped niche) centered at x meters."""
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
    """Return {panel: window point} for panels whose centers the ray hits directly; other panels are occluded in this view."""
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
    # User request: click selects a group, double click selects one panel, and
    # Shift+click adds only another panel of that same group. With two selected groups
    # (click then Shift+click), Shift+double-click isolates a panel within the selection
    # while retaining the other group.
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
    assert len(alvos_a) >= 2 and alvos_b, 'panels out of view'
    (a1, p_a1), (a2, p_a2) = list(alvos_a.items())[:2]
    b1, p_b1 = next(iter(alvos_b.items()))
    grupo_a = {a, *a.children_recursive}
    grupo_b = {b, *b.children_recursive}
    # One group: click, double click, then Shift+click another of its panels.
    m.mover(*p_a1)
    yield
    m.clicar()
    yield
    assert set(bpy.context.selected_objects) == grupo_a, 'click should select the group'
    m.clicar()
    yield
    _duplo_clique_do_keymap(janela)
    yield
    assert set(bpy.context.selected_objects) == {a1}, 'double click should select the panel'
    m.mover(*p_a2)
    yield
    m.clicar(shift=True)
    yield
    selecao = set(bpy.context.selected_objects)
    assert selecao == {a1, a2}, 'Shift+click should add only the panel: %s' % (
        sorted(o.name for o in selecao))
    # Two groups: click A, then Shift+click B.
    m.mover(*p_a1)
    yield
    m.clicar()
    yield
    m.mover(*p_b1)
    yield
    m.clicar(shift=True)
    yield
    assert set(bpy.context.selected_objects) == grupo_a | grupo_b,         'Shift+click should add group B'
    # Shift+double-click A: retain only a1 from A and all of B.
    m.mover(*p_a1)
    yield
    m.clicar(shift=True)
    yield
    _duplo_clique_do_keymap(janela, shift=True)
    yield
    selecao = set(bpy.context.selected_objects)
    assert selecao == {a1} | grupo_b, 'Shift+double click on A: %s' % (
        sorted(o.name for o in selecao))
    # Shift+double-click B: retain a1 and only b1.
    m.mover(*p_b1)
    yield
    m.clicar(shift=True)
    yield
    _duplo_clique_do_keymap(janela, shift=True)
    yield
    selecao = set(bpy.context.selected_objects)
    assert selecao == {a1, b1}, 'Shift+double click on B: %s' % (
        sorted(o.name for o in selecao))


def test_dois_modulos_selecionados_editam_pela_hud_os_dois(janela, m):
    # User request: with two cabinets selected, only the last showed an outline.
    # The inactive cabinet's arrow and corner must also respond to real mouse input,
    # without asking how to edit.
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
        'outlines should appear on both: %s' % [g['objeto'].name
                                                 for g, _x in desenhos]
    # Width arrow on inactive A: both cabinets are selected, so both are edited.
    # B flashes until its arrow is chosen; then the typed value applies to both,
    # each retaining its own fixed corner.
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
        assert item in linhas, 'L line for %s is out of view' % item.name
    fixa_a, ini, fim = linhas[a]
    m.mover(*(ini + (fim - ini) * 0.2))
    yield
    yield
    hover = addon.hud._hover_hud.get(regiao.as_pointer())
    assert hover and hover['objeto'] == a, "A's line did not highlight: %s" % (
        hover and hover['objeto'].name)
    m.clicar()
    yield
    estado = addon.hud._edicao_hud[0]
    assert estado and estado.get('fase') == 'coletar', estado
    assert not estado.get('botoes'), 'the "How to Edit?" prompt returned'
    with contexto(janela, area, regiao):
        pendentes = [g['objeto'] for g, _x in addon.hud._desenhos_hud(bpy.context)
                     if g.get('pendente')]
    assert pendentes == [b], 'B should blink: %s' % pendentes
    assert time.time() - addon.hud._piscada_hud[0] < 5, 'did not blink'
    fixa_b, ini, fim = linhas[b]
    m.mover(*(ini + (fim - ini) * 0.2))
    yield
    yield
    m.clicar()
    yield
    assert addon.hud._edicao_hud[0].get('texto') is not None, \
        'typing should start once both are oriented'
    m.clicar('A', ctrl=True)
    m.digitar('900')
    m.tecla('RET')
    yield
    for item, fixa in ((a, fixa_a), (b, fixa_b)):
        assert abs(item.conj_largura_mm - 900.0) < 1e-3, item.conj_largura_mm
        nova = addon.hud._geometria_do_item(item, 'GRUPO',
                                        addon.modulos._chapas_do_conjunto(item))
        assert min((c - fixa).length for c in nova['cantos']) < 1e-4, \
            'the chosen corner of %s moved' % item.name
    # Dragging cabinet A's corner moves only A.
    geometria = addon.hud._geometria_do_item(a, 'GRUPO', addon.modulos._chapas_do_conjunto(a))
    canto = min((na_tela(regiao, rv3d, c) for c in geometria['cantos']
                 if na_tela(regiao, rv3d, c)),
                key=lambda c: c[0])            # The leftmost corner.
    pos_a, pos_b = a.matrix_world.translation.copy(), b.matrix_world.translation.copy()
    m.mover(*canto)
    yield
    yield
    hover = addon.hud._hover_hud.get(regiao.as_pointer())
    assert hover and hover['tipo'] == 'ancora' and hover['objeto'] == a, \
        "A's corner did not highlight: %s" % (hover and hover['tipo'])
    m.apertar()
    yield
    for passo in range(1, 5):
        m.mover(canto[0] - 15 * passo, canto[1])
        yield
    m.soltar()
    yield
    assert (a.matrix_world.translation - pos_a).length > 0.01, 'A did not move'
    assert (b.matrix_world.translation - pos_b).length < 1e-6, 'B moved along with A'


def test_quina_com_ctrl_gruda_na_quina_de_outro_modulo(janela, m):
    # User request: while moving a cabinet by its corner, Ctrl enables snapping
    # only to corners of other cabinets or panels.
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
        "A's corner did not highlight: %s" % (hover and hover['tipo'])
    m.apertar()
    yield
    # Dragging delegates to native cursor translation; Ctrl enables its vertex snap
    # to the corners of B's panels.
    for passo in range(1, 6):
        m.x, m.y = (int(round(v)) for v in
                    Vector(canto) + (destino - Vector(canto)) * passo / 5)
        janela.event_simulate('MOUSEMOVE', 'NOTHING', ctrl=True, x=m.x, y=m.y)
        yield
    assert addon.hud._arraste_quina[0] is not None, 'the native drag did not start'
    m.soltar(ctrl=True)
    yield
    yield
    janela.event_simulate('LEFT_CTRL', 'RELEASE', x=m.x, y=m.y)
    yield
    assert addon.hud._arraste_quina[0] is None, 'the drag did not finish'
    # Snap to a vertex of B near the target: either the cabinet-box corner or a panel
    # corner, separated by only a few pixels because of panel thickness.
    vertices_b = [o.matrix_world @ v.co for o in addon.modulos._chapas_do_conjunto(b)
                  for v in o.data.vertices if (o.matrix_world @ v.co - alvo).length < 0.05]
    erro = min((cantos(a)[i] - q).length for q in vertices_b)
    assert erro < 1e-5, "A's corner is %.4f m from a corner of B" % erro


def test_ctrl_z_com_o_mouse_na_hud_esquece_o_objeto(janela, m):
    # User crash: Ctrl+Z while hovering over the HUD. Undo freed the objects,
    # but hover retained one for the next redraw, causing Blender to crash later
    # at an apparently unrelated location.
    area, regiao, rv3d = viewport(janela)
    with contexto(janela, area, regiao):
        bpy.ops.ed.undo_push(message='Antes do modulo')
    conj = criar_modulo(janela)
    chapas = addon.modulos._chapas_do_conjunto(conj)
    selecionar(janela, chapas[0])
    with contexto(janela, area, regiao):
        bpy.ops.ed.undo_push(message="Cabinet")
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
    assert addon.hud._hover_hud.get(regiao.as_pointer()), 'the line did not highlight'
    m.apertar('Z', ctrl=True)
    m.soltar('Z', ctrl=True)
    yield
    yield
    assert not any(addon.chapas.MARCA_CONJUNTO in o for o in bpy.data.objects),         'Ctrl+Z did not undo the cabinet'
    assert all(addon.hud._alvo_vivo(a) for a in addon.hud._hover_hud.values()),         'hover retained a freed object'
    # The depsgraph handler waited for undo to settle and has resumed.
    assert not addon.eventos._desfazendo[0], 'the handler remained disabled'
    m.mover(m.x + 6, m.y)
    yield
    yield


def test_hover_acende_o_botao_pelo_gizmo_da_gaveta(janela, m):
    # Hover comes from VIEW3D_GGT_cabinet_gaveta: one invisible gizmo per widget,
    # prepared by _preparar_hover. Without it, the glow never appears.
    area, regiao = gaveta(janela)
    m.mover(*widget(janela, lambda v: v[5] == ('aba', 'PORTAS')))
    yield esperar(0.4)
    with contexto(janela, area, regiao):
        aceso = addon.gaveta._valor_realce(bpy.context, 'aba:PORTAS')
    assert aceso > 0.5, 'hover did not highlight the tab (%.2f)' % aceso
    m.mover(regiao.x + regiao.width / 2, regiao.y + 20)   # Empty footer.
    yield esperar(0.6)
    with contexto(janela, area, regiao):
        apagado = addon.gaveta._valor_realce(bpy.context, 'aba:PORTAS')
    assert apagado < 0.1, 'the glow did not fade after leaving (%.2f)' % apagado


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
    # User request: Alt turns the handle anchor into a dot; dragging moves it
    # to another group edge using line snapping and orients it to that edge.
    # Only edges of the door leaves are eligible.
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
    assert estado is not None, 'the handle anchor was not grabbed'
    a, b = addon.puxadores._bordas_da_face(folha, 1)['Y-']
    destino = na_tela(regiao, rv3d, a.lerp(b, 0.3))
    inicio = (m.x, m.y)
    for passo in range(1, 6):
        m.mover(inicio[0] + (destino[0] - inicio[0]) * passo / 5,
                inicio[1] + (destino[1] - inicio[1]) * passo / 5)
        yield
    assert len(estado['linhas']) == 4, 'expected only leaf edges: %d' % len(
        estado['linhas'])
    m.soltar(alt=True)
    yield
    m.janela.event_simulate('LEFT_ALT', 'RELEASE', x=m.x, y=m.y)
    yield
    assert addon.puxadores._arraste_puxador[0] is None, 'the drag did not finish'
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
    # Rear view looking toward -Y: the niche has no back, so the ray
    # hits the rear face of the leaf directly.
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
    assert nova.y > 0.99, 'the front did not turn backward: %r' % (tuple(nova),)


def test_escalar_o_modulo_com_S(janela, m):
    # Harness-discovered bug, fixed in v126: S on the cabinet Empty had no effect;
    # panels reverted to their previous sizes.
    conj = criar_modulo(janela)
    selecionar(janela, addon.modulos._chapas_do_conjunto(conj)[0])
    largura = conj.conj_largura_mm
    area, regiao, rv3d = viewport(janela)
    centro = na_tela(regiao, rv3d, conj.matrix_world.translation)
    m.mover(centro[0] + 60, centro[1])
    yield
    m.tecla('S')
    # With parallel suites, scaling might not start before X/1.5/Enter arrived,
    # leaving width unchanged. Wait for the modal operator.
    for _tentativa in range(25):
        yield
        if any(op.bl_idname == 'TRANSFORM_OT_resize'
               for op in janela.modal_operators):
            break
    m.tecla('X')            # Scale only the width.
    yield
    m.digitar('1.5')
    m.tecla('RET')
    # Thickness is unaffected by scale: side panels stay 18 mm thick and only their
    # positions scale: (L - E) * 1.5 + E, not L * 1.5.
    esperado = (largura - 18.0) * 1.5 + 18.0
    # The handler/timer (0.2 s) absorbs and normalizes scale. Wait for the condition,
    # not a fixed delay; 0.6 s was insufficient with parallel suites (v146).
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
    # The chain is the native LINKED button in VIEW3D_GGT_correntes_cabinet.
    # With Alt held, cabinet_clique_corrente handles the click because native gizmos
    # reject modified clicks. It appears only while the options key (Alt) is held
    # and the weld is away from its origin, at every corner.
    # Clicking detaches the entire part, including all its corners.
    piso = addon.chapas.nova_chapa("Floor", 600.0, 400.0, 18.0, (0, 0, 9.0),
                            (0, 0, 0), bpy.context)
    lateral = addon.chapas.nova_chapa('Lateral', 720.0, 400.0, 18.0,
                               (319.0, 0, 360.0), (0, 90.0, 0), bpy.context)
    bpy.context.view_layer.update()
    addon.chapas.detectar_adjacencia([piso, lateral])
    lateral.location.x += 0.02          # 20 mm away from the weld origin.
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

    assert corrente_visivel() == [], 'the chain should be hidden without Alt'
    m.janela.event_simulate('LEFT_ALT', 'PRESS', alt=True, x=m.x, y=m.y)
    yield
    correntes = corrente_visivel()
    assert len(correntes) == 2, 'expected 2 corners with Alt; got %d' % len(correntes)
    assert correntes[0]['meio'] is not None, 'the chain was offscreen'
    with contexto(janela, area, regiao):
        meio = addon.solda._botoes_da_corrente(bpy.context, correntes[0])['corrente']
    m.mover(regiao.x + meio.x, regiao.y + meio.y)
    yield
    yield
    m.clicar(alt=True)
    yield
    assert not addon.solda.agregado(piso), 'the floor remains attached after one click'
    assert addon.solda._ligacoes_adjacencia([piso, lateral]) == []
    assert corrente_visivel() == [], 'the chain did not disappear'
    m.janela.event_simulate('LEFT_ALT', 'RELEASE', x=m.x, y=m.y)
    yield
    assert not addon.solda._tecla_corrente_segurada[0], 'releasing Alt did not hide it'
    # The chain consumed the click, leaving selection unchanged.
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
    # Third screenshot: recessed top and base. Clicking the chain detaches all
    # corners of its part and removes it from the cabinet without moving it.
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
        assert correntes, 'no chain onscreen'
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
    assert peca.parent is None, 'the component remains in the cabinet'
    assert not addon.solda.agregado(peca)
    for a, b in zip(peca.matrix_world, mundo):
        assert (a - b).length < 1e-5, 'the component moved'
    outra = tampo if peca is base else base
    assert outra.parent == conj, 'the other component detached as well'


def test_botao_corrente_associa_por_vertices_e_junta(janela, m):
    # Chain-button flow (cabinet_corrente_objeto) with a detached part and no target
    # in range enters vertex-selection mode (cabinet_conectar_vertices).
    # Choose the part corner and destination corner twice, then confirm in the
    # sidebar footer (cabinet_confirmar_conexao).
    # Answer yes to joining the cabinet (cabinet_juntar_modulo).
    # The cabinet must not be pulled toward the part.
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
    assert estado is False, 'a detached shelf should make the button gray'
    m.mover(*widget(janela, botao))
    yield
    m.clicar()
    yield
    assert addon.solda._conexao_manual[0] is not None, 'did not enter vertex selection'
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
    assert addon.solda._conexao_manual[0] is None, 'Confirm did not finish'
    assert addon.solda._conexao_pendente[0] is not None, 'no "Join Cabinet?" prompt'
    # Opened by a sidebar button: the question appears there in a black box,
    # not a popup. Click its affirmative join response.
    assert addon.perguntas._pergunta_atual[0] and addon.perguntas._pergunta_atual[0]['na_gaveta'], \
        'the prompt should be in the sidebar'
    m.mover(*widget(janela, lambda v: v[5] == ('resposta', 0)))
    yield
    m.clicar()
    yield
    assert prateleira.parent == conj, 'did not join the cabinet'
    assert addon.solda.agregado(prateleira)
    lo = min(p.x for p in addon.chapas._cantos(prateleira))
    assert abs(lo - fora_x) < 1e-5, 'the end did not reach the side panel (%f)' % lo
    for o in chapas:
        for a, b in zip(o.matrix_world, fixos[o.name]):
            assert (a - b).length < 1e-6, 'the cabinet was pulled (%s)' % o.name


def _vista_do_lado_direito(janela):
    area, regiao, rv3d = viewport(janela)
    rv3d.view_rotation = Euler((math.radians(70), 0,
                                math.radians(20))).to_quaternion()
    rv3d.view_location = (0.6, 0, 0.2)
    rv3d.view_distance = 2.4
    return area, regiao, rv3d


def test_alvo_primeiro_peca_de_fora_por_ultimo_conecta(janela, m):
    # Click the cabinet target, then Shift+click the shelf 3 mm away to make that
    # external part active. The chain button connects by distance, then asks to join.
    # Answer yes; the cabinet must not be pulled toward the part.
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
    # Right side panel: the cabinet center is beneath the sidebar.
    direita = max(chapas, key=lambda o: o.matrix_world.translation.x)
    m.mover(*na_tela(regiao, rv3d, direita.matrix_world.translation))
    yield
    m.clicar()
    yield
    assert set(bpy.context.selected_objects) == set(addon.selecao.familia_de(conj)),         'click did not select the cabinet: %s' % bpy.context.selected_objects
    m.mover(*na_tela(regiao, rv3d, prateleira.matrix_world.translation))
    yield
    m.clicar(shift=True)
    yield
    assert bpy.context.view_layer.objects.active == prateleira,         'the external component did not become active'
    assert all(o.select_get() for o in chapas), 'Shift lost the target: %s' % (
        [o.name for o in bpy.context.selected_objects],)
    with contexto(janela, *gaveta(janela)):
        acao = addon.solda._acao_corrente(bpy.context)
    assert acao[:2] == ('conectar', prateleira), acao
    m.mover(*widget(janela, lambda v: v[5][:2] == (
        'operador', addon.solda.OP_CORRENTE_OBJETO)))
    yield
    m.clicar()
    yield
    assert addon.solda._conexao_pendente[0] is not None, 'no "Join Cabinet?" prompt'
    # Opened by a sidebar button: the question appears there in a black box,
    # not a popup. Click its affirmative join response.
    assert addon.perguntas._pergunta_atual[0] and addon.perguntas._pergunta_atual[0]['na_gaveta'], \
        'the prompt should be in the sidebar'
    m.mover(*widget(janela, lambda v: v[5] == ('resposta', 0)))
    yield
    m.clicar()
    yield
    assert prateleira.parent == conj, 'did not join the cabinet'
    assert addon.solda.agregado(prateleira)
    lo = min(p.x for p in addon.chapas._cantos(prateleira))
    assert abs(lo - fora_x) < 1e-5, 'the gap did not close (%f)' % lo
    for o in chapas:
        for a, b in zip(o.matrix_world, fixos[o.name]):
            assert (a - b).length < 1e-6, 'the cabinet was pulled (%s)' % o.name


def test_botao_corrente_no_grupo_pergunta_antes_de_desagregar(janela, m):
    conj = criar_modulo(janela)
    chapas = addon.modulos._chapas_do_conjunto(conj)
    area, regiao, rv3d = _vista_do_lado_direito(janela)
    bpy.ops.object.select_all(action='DESELECT')
    yield
    # Right side panel: the cabinet center is beneath the sidebar.
    direita = max(chapas, key=lambda o: o.matrix_world.translation.x)
    m.mover(*na_tela(regiao, rv3d, direita.matrix_world.translation))
    yield
    m.clicar()
    yield
    assert set(bpy.context.selected_objects) == set(addon.selecao.familia_de(conj)),         'click did not select the cabinet: %s' % bpy.context.selected_objects
    m.mover(*widget(janela, lambda v: v[5][:2] == (
        'operador', addon.solda.OP_CORRENTE_OBJETO)))
    yield
    m.clicar()
    yield
    assert addon.solda._desagregar_pendente[0] == sorted(o.name for o in chapas),         'no "Detach all items?" prompt: %s %s %s' % (
            addon.solda._desagregar_pendente[0],
            [o.name for o in bpy.context.selected_objects],
            bpy.context.view_layer.objects.active)
    assert all(o.parent == conj for o in chapas), 'detached without asking'
    nome = conj.name
    # Opened by a sidebar button: the question appears there in a black box,
    # not a popup. Click its affirmative detach response.
    assert addon.perguntas._pergunta_atual[0] and addon.perguntas._pergunta_atual[0]['na_gaveta'], \
        'the prompt should be in the sidebar'
    m.mover(*widget(janela, lambda v: v[5] == ('resposta', 0)))
    yield
    m.clicar()
    yield
    assert nome not in bpy.data.objects, 'the empty cabinet remained'
    assert all(o.parent is None and not addon.solda.agregado(o) for o in chapas)


def test_digitar_no_campo_da_gaveta(janela, m):
    chapa = addon.chapas.nova_chapa('Campo', 600.0, 400.0, 18.0, (0, 0, 0),
                             (0, 0, 0), bpy.context)
    selecionar(janela, chapa, individual=True)
    yield
    m.mover(*widget(janela, lambda v: v[5][0] == 'medida'
                    and v[5][3] == "Width"))
    yield
    m.clicar()
    yield
    m.clicar('A', ctrl=True)
    m.digitar('750')
    m.tecla('RET')
    yield
    assert abs(chapa.chapa_largura_mm - 750.0) < 1e-3, chapa.chapa_largura_mm
    assert abs(chapa.dimensions.x - 0.75) < 1e-5


def test_arrastar_o_campo_muda_o_valor(janela, m):
    # User request: dragging sideways on any value field increases rightward
    # and decreases leftward at 1 mm per pixel. Releasing without dragging still
    # opens text entry; one Ctrl+Z undoes the whole operation.
    chapa = addon.chapas.nova_chapa('Campo', 600.0, 400.0, 18.0, (0, 0, 0),
                                    (0, 0, 0), bpy.context)
    selecionar(janela, chapa, individual=True)
    yield
    m.mover(*widget(janela, lambda v: v[5][0] == 'medida'
                    and v[5][3] == "Width"))
    yield
    m.apertar()
    yield
    x0 = m.x
    for passo in range(1, 6):
        m.mover(x0 + 10 * passo, m.y)
        yield
    m.soltar()
    yield
    assert abs(chapa.chapa_largura_mm - 650.0) < 1e-3, chapa.chapa_largura_mm
    assert addon.gaveta._edicao_gaveta[0] is None, 'dragging should not open text entry'
    m.apertar()
    yield
    for passo in range(1, 4):
        m.mover(m.x - 10, m.y)
        yield
    m.soltar()
    yield
    assert abs(chapa.chapa_largura_mm - 620.0) < 1e-3, chapa.chapa_largura_mm


def janelas_do_salvar_como():
    return [(j, a) for j in bpy.context.window_manager.windows
            for a in j.screen.areas if a.type == 'FILE_BROWSER']


def test_comodo_e_gerar_orcamento_pelas_opcoes(janela, m):
    # The room row expands; choosing an entry moves the cabinet into that room's
    # Outliner folder and closes the list. Estimate generation is at the bottom
    # of Options (gear icon) and opens Blender's Save As dialog on click release,
    # like other buttons that open windows.
    conj = criar_modulo(janela)
    selecionar(janela, addon.modulos._chapas_do_conjunto(conj)[0])
    bpy.context.scene.cabinet_aba = 'MODULOS'
    yield
    yield
    try:
        m.mover(*widget(janela, lambda v: v[5][:2] == (
            'suspenso', addon.orcamento.SUSPENSO_COMODO)))
        yield
        m.clicar()
        yield
        m.mover(*widget(janela, lambda v: v[5][0] == 'escolha'
                        and v[5][5] == addon.orcamento.ALVO_COMODO
                        and v[5][2] == "Kitchen"))
        yield
        m.clicar()
        yield
        comodo = addon.orcamento._comodo_do_modulo(conj)
        assert comodo is not None and comodo.name == "Kitchen", comodo
        assert bpy.context.screen.get(addon.gaveta._CHAVE_SUSPENSO, '') == '', \
            'the list should close after choosing'
        m.mover(*widget(janela, lambda v: v[5] == (
            'operador', addon.gaveta.OP_OPCOES)))
        yield
        m.clicar()
        yield
        yield
        assert not janelas_do_salvar_como()
        m.mover(*widget(janela, lambda v: v[5][:2] == (
            'operador', addon.orcamento.OP_EXPORTAR_ORCAMENTO)))
        yield
        m.clicar()
        for _ in range(6):
            yield
            if janelas_do_salvar_como():
                break
        assert janelas_do_salvar_como(), 'Save As did not open'
    finally:
        for j, a in janelas_do_salvar_como():
            with bpy.context.temp_override(window=j, area=a):
                bpy.ops.file.cancel()
        addon.gaveta._fechar_opcoes(janela.screen)
        addon.orcamento._apagar_orcamento_gerado()


def test_criar_puxador_no_topo_da_aba(janela, m):
    # Same pattern as Create Doors: orange at the top of the tab. Clicking starts
    # placement, and the button indicates that placement is in progress.
    bpy.context.scene.cabinet_aba = 'PUXADORES'
    yield
    m.mover(*widget(janela, lambda v: v[5][0] == 'criar_puxador'))
    yield
    m.clicar()
    yield
    try:
        assert addon.puxadores._posicionador_puxador[0] is not None, 'did not start'
        widget(janela, lambda v: v[5][0] == 'criar_puxador' and v[5][2]
               and v[4].startswith('Posicionando'))
    finally:
        m.tecla('ESC')
        yield
    assert addon.puxadores._posicionador_puxador[0] is None, 'Esc should finish'


def test_usar_como_puxador_pela_gaveta(janela, m):
    # For an ungrouped external object, the use-as-handle action runs on release
    # and asks for the face touching the door. Save the model to the library
    # (a temporary directory here) with a real preview, then open the creator
    # with that model highlighted in the thumbnail carousel.
    import shutil
    import tempfile
    import bmesh
    from mathutils import Matrix
    pasta = tempfile.mkdtemp()
    original = addon.biblioteca.pasta_biblioteca
    addon.biblioteca.pasta_biblioteca = lambda: pasta
    try:
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Diagonal(
            (0.4, 0.06, 0.08, 1.0)))
        malha = bpy.data.meshes.new('Barra')
        bm.to_mesh(malha)
        bm.free()
        obj = bpy.data.objects.new('Barra', malha)
        bpy.context.collection.objects.link(obj)
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.context.scene.cabinet_aba = 'PUXADORES'
        yield
        yield
        m.mover(*widget(janela, lambda v: v[5][:2] == (
            'operador', 'object.cabinet_usar_como_puxador')))
        yield
        m.clicar()
        yield
        assert addon.puxadores._usando_como_puxador[0] is not None,             'no face-click prompt appeared'
        widget_texto = [v for v in addon.gaveta._widgets_gaveta(
            bpy.context, 320, 1400) if v[4].startswith('Clique na face')]
        assert widget_texto, 'the sidebar should explain what to do'
        area, regiao, rv3d = viewport(janela)
        m.mover(*na_tela(regiao, rv3d, Vector((0.0, 0.0, 0.04))))
        yield
        m.clicar()
        for _ in range(4):
            yield
        assert addon.puxadores._usando_como_puxador[0] is None
        (it,) = addon.puxadores.modelos_do_usuario()
        assert os.path.isfile(os.path.join(pasta, 'Barra.png')), "no photo"
        estado = addon.puxadores._posicionador_puxador[0]
        assert estado is not None and (estado['tipo'], estado['arquivo']) == (
            'MODELO', it['arquivo']), estado
        widget(janela, lambda v: v[5][0] == 'escolha' and len(v[5]) > 6
               and v[5][2] == 'MODELO:' + it['arquivo'] and v[5][3])
    finally:
        m.tecla('ESC')
        yield
        addon.biblioteca.pasta_biblioteca = original
        addon.puxadores.escolher_modelo(bpy.context.scene, 'PERFIL')   # The default.
        shutil.rmtree(pasta, True)


def test_materiais_pela_gaveta(janela, m):
    # A previous test may leave the native wall menu open.
    # Painting must start with the same clean interface as an isolated run.
    m.tecla('ESC')
    yield
    yield
    # Materials button beside the title -> MDF -> solid colors. One sphere click
    # does nothing; double-click paints the selected cabinet. Dragging a sphere
    # onto an unselected cabinet paints that cabinet. The trash action asks in the
    # black box immediately below; answering no deletes nothing. Redirect the library
    # to a temporary directory so nothing can write to the real library.
    import shutil
    import tempfile
    pasta = tempfile.mkdtemp()
    original = addon.biblioteca.pasta_biblioteca
    addon.biblioteca.pasta_biblioteca = lambda: pasta
    try:
        conj = criar_modulo(janela)
        selecionar(janela, addon.modulos._chapas_do_conjunto(conj)[0])
        yield
        passos = ((lambda v: v[5][:2] == ('biblioteca', 'MATERIAIS')),
                  (lambda v: v[5][:3] == ('navegar', 1, 'MDF')),
                  (lambda v: v[5][:3] == ('navegar', 2, "Solid Colors")))
        for alvo in passos:
            m.mover(*widget(janela, alvo))
            yield
            m.clicar()
            yield
        cena = bpy.context.scene
        assert (cena.cabinet_bib_modo, cena.cabinet_mat_n1, cena.cabinet_mat_n2) == (
            'MATERIAIS', 'MDF', "Solid Colors"), (cena.cabinet_bib_modo, cena.cabinet_mat_n1)
        # First grid entry alphabetically; the second row lies below the panel.
        areia = "MDF/Solid Colors//Sand"
        m.mover(*widget(janela, lambda v: v[5][0] == 'material'
                        and v[5][1]['chave'] == areia))
        yield
        chapas = addon.modulos._chapas_do_conjunto(conj)

        def nomes():
            return {c.material_slots[0].material.name
                    if c.material_slots and c.material_slots[0].material
                    else None for c in chapas}
        m.clicar()
        yield esperar(0.6)       # Past the double-click interval: a single click.
        assert nomes() == {None}, ('a single click painted the object', nomes())
        m.clicar()
        yield esperar(0.05)      # Well within the double-click interval.
        m.clicar()
        yield
        assert nomes() == {'MDF Areia'}, nomes()
        # The selected object's material sphere highlights.
        widget(janela, lambda v: v[5][0] == 'material' and v[5][2]
               and v[5][1]['chave'] == areia)
        m.mover(*widget(janela, lambda v: v[5][0] == 'material_item'
                        and v[5][1]['chave'] == areia and v[5][2] == 1))
        yield
        m.clicar()
        yield
        pergunta = addon.perguntas._pergunta_atual[0]
        assert pergunta is not None and pergunta.get('biblioteca'), pergunta
        m.mover(*widget(janela, lambda v: v[5] == ('resposta', 1)))     # No.
        yield
        m.clicar()
        yield
        assert addon.perguntas._pergunta_atual[0] is None
        assert addon.materiais.achar(areia) is not None, 'choosing No deleted the item'
        # Drag another sphere onto the unselected cabinet to paint it.
        bpy.ops.object.select_all(action='DESELECT')
        yield
        area_g = addon.biblioteca_faixa.area_da_faixa(janela.screen)
        regiao_g = next(r for r in area_g.regions if r.type == 'WINDOW')
        with contexto(janela, area_g, regiao_g):
            item = next(v[5][1] for v in addon.gaveta._widgets_interativos(
                bpy.context) if v[5] and v[5][0] == 'material'
                and v[5][1]['chave'] != areia)
        outro = addon.materiais.nome_do_material(item)
        m.mover(*widget(janela, lambda v: v[5][0] == 'material'
                        and v[5][1]['chave'] == item['chave']))
        yield
        _area, regiao, rv3d = viewport(janela)
        x, y = na_tela(regiao, rv3d, chapas[0].matrix_world.translation)
        m.apertar()
        yield
        for t in (0.25, 0.5, 0.75, 1.0):
            m.mover(m.x + (x - m.x) * t, m.y + (y - m.y) * t)
            yield
        m.soltar()
        yield
        assert nomes() == {outro}, (outro, nomes())
        assert not bpy.context.selected_objects, 'dropping changed the selection'
    finally:
        addon.biblioteca.pasta_biblioteca = original
        shutil.rmtree(pasta, True)


def test_arrastar_modulo_com_o_direito_ate_a_parede(janela, m):
    # Promob-style user request: hold the right mouse button on the cabinet and
    # release on the wall (cabinet_arrastar_na_parede) to place its back against
    # and associate it with that wall. Clicking a guide number
    # (VIEW3D_GGT_guias_parede / VIEW3D_GT_guia_parede -> cabinet_guia_parede) opens text entry.
    import bmesh
    P = addon.paredes
    conj = criar_modulo(janela)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x, v.co.y, v.co.z = v.co.x * 3.0, v.co.y * 0.15, v.co.z * 2.7
    malha = bpy.data.meshes.new("Wall")
    bm.to_mesh(malha)
    bm.free()
    parede = bpy.data.objects.new("Wall", malha)
    bpy.context.scene.collection.objects.link(parede)
    parede.location = (0.0, 1.075, 1.35)          # Front at y = 1 m.
    parede[addon.paredes.CHAVE_ALVENARIA]=True
    bpy.context.view_layer.update()
    yield
    _area, regiao, rv3d = viewport(janela)
    # The niche has no back, so its opening center is empty. Frame both targets
    # and start on a real panel without depending on the preceding test's view.
    rv3d.view_rotation = Euler((math.radians(75), 0, 0)).to_quaternion()
    rv3d.view_location = (0.0, 0.5, 0.8)
    rv3d.view_distance = 4.0
    yield
    tampo = next(o for o in addon.modulos._chapas_do_conjunto(conj)
                 if o.name.startswith("Top"))
    meio = tampo.matrix_world.translation
    m.mover(*na_tela(regiao, rv3d, meio))
    yield
    m.apertar('RIGHTMOUSE')
    yield
    assert any(o.bl_idname == 'OBJECT_OT_cabinet_arrastar_na_parede'
               for o in janela.modal_operators), 'dragging did not start on a panel'
    destino = na_tela(regiao, rv3d, Vector((-0.9, 1.0, 1.6)))
    for t in (0.25, 0.5, 0.75, 1.0):
        m.mover(m.x + (destino[0] - m.x) * t, m.y + (destino[1] - m.y) * t)
        yield
    m.soltar('RIGHTMOUSE')
    yield
    assert conj.get(P.CHAVE_PAREDE), 'the cabinet was not associated'
    assert conj[P.CHAVE_PAREDE] == parede.get(P.CHAVE_UID_PAREDE), dict(conj)
    assert abs(P.ponto_das_costas(conj).y - 1.0) < 1e-4, P.ponto_das_costas(conj)
    # Selection shows the guides; clicking the floor-guide number opens text entry.
    selecionar(janela, addon.modulos._chapas_do_conjunto(conj)[0])
    yield esperar(0.5)                 # The timer computes the guides.
    assert P._guias[0] is not None, 'no guides'
    rotulo = next(r for r in P._rotulos.get(regiao.as_pointer(), ())
                  if r[0] == 'piso')
    m.mover(regiao.x + (rotulo[1] + rotulo[3]) / 2,
            regiao.y + (rotulo[2] + rotulo[4]) / 2)
    yield
    m.clicar()
    yield
    assert P._edicao_guia[0] is not None, 'click did not open text entry'
    m.clicar('A', ctrl=True)
    m.digitar('1200')
    m.tecla('RET')
    yield
    assert P._edicao_guia[0] is None
    piso = P.calcular_guias(conj)['valores']['piso']
    assert abs(piso - 1200.0) < 0.01, piso


def test_botao_direito_no_material_pinta_o_comodo(janela, m):
    # Quick painting, as requested: right-click a material to choose cabinets by
    # room, then choose what to paint in the black box beneath the material;
    # no Blender context menu should appear.
    import shutil
    import tempfile
    pasta = tempfile.mkdtemp()
    original = addon.biblioteca.pasta_biblioteca
    addon.biblioteca.pasta_biblioteca = lambda: pasta
    try:
        area, regiao, _rv3d = viewport(janela)
        with contexto(janela, area, regiao):
            conj = addon.modulos.criar_armario(bpy.context, "Base Cabinet", 800, 720, 550)
            addon.portas.porta_no_modulo(conj, 2)
            addon.orcamento.definir_comodo(bpy.context.scene, [conj], "Kitchen")
        cena = bpy.context.scene
        cena.cabinet_bib_modo = 'MATERIAIS'
        cena.cabinet_mat_n1, cena.cabinet_mat_n2 = 'MDF', "Solid Colors"
        yield
        areia = "MDF/Solid Colors//Sand"
        m.mover(*widget(janela, lambda v: v[5][0] == 'material'
                        and v[5][1]['chave'] == areia))
        yield
        m.clicar('RIGHTMOUSE')
        yield
        pergunta = addon.perguntas._pergunta_atual[0]
        assert pergunta is not None and pergunta.get('biblioteca'), pergunta
        for rotulo in ('Cozinha (1)', "Box Only"):
            m.mover(*widget(janela, lambda v: v[5][0] == 'resposta'
                            and v[4] == rotulo))
            yield
            m.clicar()
            yield
        assert addon.perguntas._pergunta_atual[0] is None
        caixa = addon.materiais.pecas_do_modulo(conj, 'CAIXA')
        folhas = addon.materiais.pecas_do_modulo(conj, 'PORTAS')
        assert {c.material_slots[0].material.name for c in caixa} == {'MDF Areia'}
        assert not any(f.material_slots and f.material_slots[0].material
                       for f in folhas), 'painted the door'
    finally:
        addon.biblioteca.pasta_biblioteca = original
        bpy.context.scene.cabinet_bib_modo = 'MODULOS'
        shutil.rmtree(pasta, True)


# ------------------------------------------------------------ drawers
def _gavetas_de_frente(janela):
    """Front-facing niche, Drawers tab, nothing selected."""
    conj, area, regiao, rv3d = _wizard_ate_o_tipo(janela, None)
    bpy.context.scene.cabinet_aba = 'GAVETAS'
    return conj, area, regiao, rv3d


def _gavetas_prontas(janela, conj, n=3):
    area, regiao, _ = viewport(janela)
    with contexto(janela, area, regiao):
        E = conj.conj_espessura_mm
        grupo = addon.gavetas.criar_gavetas(
            bpy.context, conj, (E, E, E, E, 0),
            dict(quantidade=n, lateral_mm=E, espessura_frente_mm=E,
                 profundidade_mm=conj.conj_profundidade_mm))
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.ed.undo_push(message='Gavetas criadas')
    return grupo


def test_walk_entre_pontos_preserva_criacao_do_volume(janela, m):
    conj, area, regiao, rv = _gavetas_de_frente(janela)
    yield
    m.mover(*widget(janela, lambda v: v[5][0] == 'gavetas')); m.clicar()
    yield
    w = addon.gavetas._assistente_gavetas[0]
    L,A,P,E = conj.conj_largura_mm,conj.conj_altura_mm,conj.conj_profundidade_mm,conj.conj_espessura_mm
    yield from _clicar_no_mundo(m,regiao,rv,_local(conj,-L/2+E,-P/2,A-E))
    assert w['etapa']=='CANTO2'
    pontos=[tuple(p) for p in w['pontos']]
    assert addon.gavetas._snap_criacao[0] is None
    modo = bpy.context.preferences.inputs.navigation_mode
    gravidade = bpy.context.preferences.inputs.walk_navigation.use_gravity
    try:
        bpy.context.preferences.inputs.navigation_mode='WALK'
        bpy.context.preferences.inputs.walk_navigation.use_gravity=False
        m.mover(regiao.x+regiao.width/2,regiao.y+regiao.height/2)
        janela.event_simulate('ACCENT_GRAVE','PRESS',shift=True,x=m.x,y=m.y)
        janela.event_simulate('ACCENT_GRAVE','RELEASE',x=m.x,y=m.y)
        yield
        assert any(o.bl_idname=='VIEW3D_OT_walk' for o in janela.modal_operators), 'Walk did not start'
        inicio=rv.view_location.copy()
        m.apertar('D')
        yield
        yield
        yield
        m.soltar('D')
        yield
        assert (rv.view_location-inicio).length>1e-5, 'WASD did not move the camera'
        m.tecla('RET')
        yield
        assert addon.gavetas._assistente_gavetas[0] is w
        assert w['etapa']=='CANTO2' and [tuple(p) for p in w['pontos']]==pontos
        assert addon.gavetas._snap_criacao[0] is None
    finally:
        m.tecla('ESC')
        yield
        m.tecla('ESC')
        bpy.context.preferences.inputs.navigation_mode=modo
        bpy.context.preferences.inputs.walk_navigation.use_gravity=gravidade


def test_scroll_na_cota_subdivide_so_vao_e_esc_descarta_previa(janela, m):
    conj, area, regiao, rv = _gavetas_de_frente(janela)
    grupo = addon.prateleiras.criar_prateleiras(bpy.context,conj,(18,18,18,18,0),dict(quantidade=2,profundidade_mm=500))
    addon.prateleiras.selecionar(bpy.context,grupo,'GRUPO')
    originais={o.name:tuple(o.matrix_world.translation) for o in addon.prateleiras.prateleiras_do_grupo(grupo)}
    yield
    for confirmar in (True,False):
        linha=next(l for l in addon.prateleiras.linhas_hud(grupo,[])[1] if l.get('face')==('V',0))
        ponto=linha['pontos'][0].lerp(linha['pontos'][1],.35)
        m.mover(*na_tela(regiao,rv,ponto))
        yield
        m.clicar()
        yield
        estado=addon.hud._edicao_hud[0]
        assert estado and estado['alvo'].get('face')==('V',0), 'the opening dimension did not open'
        n=len(addon.prateleiras.prateleiras_do_grupo(grupo))
        for _ in range(2):
            janela.event_simulate('WHEELUPMOUSE','PRESS',x=m.x,y=m.y)
            yield
        assert len(addon.prateleiras.prateleiras_do_grupo(grupo))==n+2
        m.tecla('RET' if confirmar else 'ESC')
        yield
        assert addon.hud._edicao_hud[0] is None
        assert len(addon.prateleiras.prateleiras_do_grupo(grupo))==n+(2 if confirmar else 0)
        for nome,posicao in originais.items():
            assert (bpy.data.objects[nome].matrix_world.translation-Vector(posicao)).length<1e-6


def test_criar_gavetas_pelo_assistente(janela, m):
    # Three points in any order -> explicit front -> count -> rail.
    conj, area, regiao, rv3d = _gavetas_de_frente(janela)
    yield
    yield
    m.mover(*widget(janela, lambda v: v[5][0] == 'gavetas'))
    yield
    m.clicar()
    yield
    w = addon.gavetas._assistente_gavetas[0]
    assert w is not None, 'Create Drawers did not open'
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    y = -P / 2
    for ponto in ((-L / 2 + E, y, A - E), (L / 2 - E, y, E)):
        yield from _clicar_no_mundo(m, regiao, rv3d, _local(conj, *ponto))
    assert w['etapa'] == 'CANTO3', w['etapa']
    vista = rv3d.view_rotation.copy()
    rv3d.view_rotation = Euler((math.radians(65), 0, math.radians(-30))).to_quaternion()
    yield
    yield from _clicar_no_mundo(m, regiao, rv3d, _local(conj, L / 2 - E, P / 2, E))
    assert w['etapa'] == 'FRENTE', w['etapa']
    rv3d.view_rotation = vista
    yield
    yield from _clicar_no_mundo(m, regiao, rv3d, _local(conj, 0, y, A / 2))
    assert w['etapa'] == 'QUANTIDADE', w['etapa']
    for _ in range(2):
        m.janela.event_simulate('WHEELUPMOUSE', 'PRESS', x=m.x, y=m.y)
        yield
    assert w['p']['quantidade'] == 3, w['p']['quantidade']
    m.clicar()
    yield
    assert w['etapa'] == 'TRILHO', w['etapa']
    (x, yb, bw, bh), _c, _t = next(b for b in w['botoes'] if b[1] == 'TELESCOPICO')
    m.mover(regiao.x + x + bw / 2, regiao.y + yb + bh / 2)
    yield
    m.clicar()
    yield
    yield
    assert addon.gavetas._assistente_gavetas[0] is None
    grupo = next(o for o in bpy.data.objects if addon.gavetas.MARCA_GRUPO in o)
    assert len(addon.gavetas.gavetas_do_grupo(grupo)) == 3
    assert addon.gavetas.parametros(grupo)['trilho'] == 'TELESCOPICO'
    largura, altura, _p = addon.gavetas.medidas(grupo)
    assert abs(largura - (L - 2 * E)) < 1 and abs(altura - (A - 2 * E)) < 1, (largura, altura)
    assert bpy.context.scene.cabinet_aba == 'GAVETAS'
    assert bpy.context.view_layer.objects.active == grupo


def test_criar_prateleiras_pelo_assistente(janela, m):
    # The same 3D picker passes the box and front to the shelf owner.
    conj, area, regiao, rv3d = _wizard_ate_o_tipo(janela, None)
    bpy.context.scene.cabinet_aba = 'PRATELEIRAS'
    yield
    yield
    m.mover(*widget(janela, lambda v: v[5] == ('operador','object.cabinet_internos')))
    yield
    m.clicar()
    yield
    assert addon.areas_criacao._internos[0]['etapa'] == 'TIPO'
    m.mover(*widget(janela, lambda v: v[5] == ('resposta',0)));m.clicar()
    yield
    w = addon.prateleiras._assistente_prateleiras[0]
    assert w is not None, 'Create Shelves did not open'
    assert addon.gavetas._assistente_gavetas[0] is None
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    y = -P / 2
    for ponto in ((-L / 2 + E, y, A - E), (L / 2 - E, y, E)):
        yield from _clicar_no_mundo(m, regiao, rv3d, _local(conj, *ponto))
    assert w['etapa'] == 'CANTO3', w['etapa']
    vista = rv3d.view_rotation.copy()
    rv3d.view_rotation = Euler((math.radians(65), 0, math.radians(-30))).to_quaternion()
    yield
    yield from _clicar_no_mundo(m, regiao, rv3d, _local(conj, L / 2 - E, P / 2, E))
    assert w['etapa'] == 'FRENTE', w['etapa']
    rv3d.view_rotation = vista
    yield
    yield from _clicar_no_mundo(m, regiao, rv3d, _local(conj, 0, y, A / 2))
    assert w['etapa'] == 'QUANTIDADE', w['etapa']
    for _ in range(2):
        m.janela.event_simulate('WHEELUPMOUSE', 'PRESS', x=m.x, y=m.y)
        yield
    assert w['p']['quantidade'] == 3, w['p']['quantidade']
    m.clicar()
    yield
    yield
    assert addon.prateleiras._assistente_prateleiras[0] is None
    grupo = next(o for o in bpy.data.objects if addon.prateleiras.MARCA_GRUPO in o)
    assert len(addon.prateleiras.prateleiras_do_grupo(grupo)) == 3
    largura, altura, prof = addon.prateleiras.medidas(grupo)
    assert abs(largura - (L - 2 * E)) < 1 and abs(altura - (A - 2 * E)) < 1, (largura, altura)
    assert prof <= P + 0.5, prof
    assert bpy.context.scene.cabinet_aba == 'PRATELEIRAS'
    assert bpy.context.view_layer.objects.active == grupo


def test_clique_nas_prateleiras_todas_duplo_uma(janela, m):
    # Like drawers: clicking a shelf selects all shelves in the opening and their
    # tab; double-click selects only that shelf and shows its below/above distances.
    conj, area, regiao, rv3d = _wizard_ate_o_tipo(janela, None)
    with contexto(janela, area, regiao):
        E = conj.conj_espessura_mm
        grupo = addon.prateleiras.criar_prateleiras(
            bpy.context, conj, (E, E, E, E, 0),
            dict(quantidade=2, espessura_mm=E, profundidade_mm=conj.conj_profundidade_mm - 20))
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.ed.undo_push(message='Prateleiras criadas')
    bpy.context.scene.cabinet_aba = 'MODULOS'
    rv3d.view_rotation = Euler((math.radians(65), 0, math.radians(-30))).to_quaternion()
    yield
    alvo = addon.prateleiras.prateleiras_do_grupo(grupo)[1]
    yield from _clicar_no_mundo(m, regiao, rv3d, alvo.matrix_world.translation)
    yield esperar(0.4)
    assert bpy.context.view_layer.objects.active == grupo, bpy.context.object
    assert bpy.context.scene.cabinet_aba == 'PRATELEIRAS'
    assert not conj.select_get()
    m.clicar()
    yield
    _duplo_clique_do_keymap(janela)
    yield
    assert set(bpy.context.selected_objects) == {alvo}, bpy.context.selected_objects
    rotulos = [v[4] for v in addon.gaveta._widgets_gaveta(
        bpy.context, 480, 1400) if v[5] and v[5][0] == 'medida']
    assert any(r.startswith("Below") for r in rotulos), rotulos


def test_escape_na_marcacao_nativa_do_vao(janela, m):
    # Regressions v240: Esc during native translation must also finish the parent
    # wizard without leaving cursor state, locks or drawing callbacks behind.
    conj, area, regiao, rv3d = _wizard_ate_o_tipo(janela, None)
    cursor = bpy.context.scene.cursor.location.copy()
    nomes = set(bpy.data.objects.keys())
    bloqueios = {o.name: o.hide_select for o in bpy.data.objects}
    mostrar = area.spaces.active.overlay.show_cursor
    with contexto(janela, area, regiao):
        bpy.ops.object.cabinet_criar_prateleiras('INVOKE_DEFAULT')
    yield
    assert addon.gavetas._snap_criacao[0] is not None
    m.mover(*na_tela(regiao, rv3d, _local(conj, 0, 0, 0)))
    yield
    m.tecla('ESC')
    yield
    yield
    assert addon.prateleiras._assistente_prateleiras[0] is None
    assert addon.gavetas._snap_criacao[0] is None
    assert set(bpy.data.objects.keys()) == nomes
    assert (bpy.context.scene.cursor.location - cursor).length < 1e-6
    assert area.spaces.active.overlay.show_cursor == mostrar
    assert all(bpy.data.objects[n].hide_select == v for n, v in bloqueios.items())
    assert not any(o.bl_idname in {'OBJECT_OT_cabinet_marcar_ponto_vao',
                                  'OBJECT_OT_cabinet_criar_prateleiras'}
                   for o in janela.modal_operators)


def test_clique_no_puxador_da_gaveta_abre_puxadores(janela, m):
    conj, area, regiao, rv3d = _gavetas_de_frente(janela)
    grupo = _gavetas_prontas(janela, conj)
    gavetas = addon.gavetas.gavetas_do_grupo(grupo)
    frente = addon.gavetas.frente_da_gaveta(gavetas[1])
    pux = next(o for o in frente.children if addon.chapas.MARCA_PUXADOR in o)
    with contexto(janela, area, regiao):
        addon.puxadores._trocar_modelo_puxador(pux, 'ALCA')
        addon.gavetas.selecionar(bpy.context, grupo, 'GRUPO')
    yield
    yield from _clicar_no_mundo(m, regiao, rv3d, pux.matrix_world.translation)
    yield esperar(0.4)
    # Single click selects the front/drawers; double click selects the handle.
    assert bpy.context.view_layer.objects.active == grupo, bpy.context.object
    assert not pux.select_get()
    yield from _clicar_no_mundo(m, regiao, rv3d, pux.matrix_world.translation)
    yield
    _duplo_clique_do_keymap(janela)
    yield esperar(0.4)
    assert set(bpy.context.selected_objects) == {pux}, bpy.context.selected_objects
    assert bpy.context.view_layer.objects.active == pux
    assert bpy.context.scene.cabinet_aba == 'PUXADORES'
    assert not addon.gavetas.gavetas_com_slider(bpy.context)
    assert not addon.hud._itens_da_selecao(bpy.context)
    yield from _clicar_no_mundo(m, regiao, rv3d, frente.matrix_world @ Vector((0.12, -0.025, 0.011)))
    yield esperar(0.4)
    assert bpy.context.view_layer.objects.active == grupo
    assert bpy.context.scene.cabinet_aba == 'GAVETAS'
    assert not pux.select_get()


def test_slider_abre_a_gaveta_e_clique_seleciona(janela, m):
    # Clicking the front selects all drawers; only they have HUD outlines.
    # The slider dot (VIEW3D_GT_slider_gaveta in VIEW3D_GGT_slider_gaveta)
    # opens through cabinet_abrir_gaveta and moves with the front,
    # so an open drawer cannot obscure its slider.
    conj, area, regiao, rv3d = _gavetas_de_frente(janela)
    grupo = _gavetas_prontas(janela, conj)
    gaveta = addon.gavetas.gavetas_do_grupo(grupo)[1]
    frente = addon.gavetas.frente_da_gaveta(gaveta)
    rv3d.view_rotation = Euler((math.radians(65), 0, math.radians(-30))).to_quaternion()
    yield
    yield from _clicar_no_mundo(m, regiao, rv3d, frente.matrix_world.translation)
    yield esperar(0.4)
    assert bpy.context.view_layer.objects.active == grupo, bpy.context.object
    with contexto(janela, area, regiao):
        assert addon.gavetas.VIEW3D_GGT_slider_gaveta.poll(bpy.context)
        inicio, fim = addon.gavetas._slider_na_tela(bpy.context, gaveta)
    m.mover(regiao.x + inicio.x, regiao.y + inicio.y)
    yield
    yield
    assert addon.gavetas._slider_hover[0] == gaveta.name, 'the dot did not highlight'
    m.apertar()
    yield
    assert any(o.bl_idname.endswith('cabinet_abrir_gaveta')
               for o in m.janela.modal_operators), 'the drag did not start'
    meio = inicio.lerp(fim, 0.5)
    for passo in range(1, 5):
        m.mover(regiao.x + inicio.x + (meio.x - inicio.x) * passo / 4,
                regiao.y + inicio.y + (meio.y - inicio.y) * passo / 4)
        yield
    m.soltar()
    yield
    yield
    fracao = gaveta[addon.gavetas.CHAVE_ABERTURA]
    assert abs(fracao - 0.5) < 0.06, fracao
    assert bpy.context.view_layer.objects.active == grupo


def _linha_editavel_gavetas(janela, grupo, letra, lado, indice=None):
    area, regiao, rv3d = viewport(janela)
    with contexto(janela, area, regiao):
        geometria = addon.hud._geometria_do_item(grupo, 'GAVETAS', [])
        for linha in geometria['linhas']:
            face=(letra,) if indice is None else (letra,indice)
            if linha['letra'] != letra or linha['face']!=face:
                continue
            a, b = [Vector(na_tela(regiao, rv3d, p)) for p in linha['pontos']]
            if (b - a).length < 40:
                continue
            ponto = a.lerp(b, 0.2 if lado == 'min' else 0.8)
            posicao = (ponto.x - regiao.x, ponto.y - regiao.y)
            if addon.gavetas.slider_sob_mouse(bpy.context, posicao) is not None:
                continue
            alvo = addon.hud._acertar_hud(bpy.context,
                                        posicao)
            if (alvo and alvo['tipo'] == 'gavetas' and alvo['face'] == face
                    and alvo['lado'] == lado):
                inicio, fim = [Vector(na_tela(regiao, rv3d, p)) for p in alvo['pontos']]
                return alvo, ponto, (fim - inicio).normalized()
    raise AssertionError('drawer line not found: %s/%s' % (letra, lado))


def test_altura_de_uma_gaveta_com_previa_esc_e_digitacao(janela,m):
    conj,area,regiao,rv3d=_gavetas_de_frente(janela)
    conj.conj_profundidade_mm=560
    grupo=_gavetas_prontas(janela,conj)
    with contexto(janela,area,regiao):
        addon.gavetas.selecionar(bpy.context,grupo,'GRUPO')
    rv3d.view_rotation=Euler((math.radians(65),0,math.radians(-30))).to_quaternion()
    yield
    yield
    antes=addon.gavetas.medidas(grupo)
    altura=addon.gavetas.valor(grupo,('A',1))
    objetos=[o.name for o in grupo.children_recursive]
    _alvo,inicio,direcao=_linha_editavel_gavetas(janela,grupo,'A','min',1)
    m.mover(*inicio)
    yield
    m.apertar()
    yield
    m.mover(*(inicio+direcao*20))
    yield
    assert addon.hud._edicao_hud[0].get('previa_gavetas')
    assert objetos==[o.name for o in grupo.children_recursive]
    assert addon.gavetas.valor(grupo,('A',1))>altura
    m.tecla('ESC');m.soltar()
    yield
    assert abs(addon.gavetas.valor(grupo,('A',1))-altura)<.1
    _alvo,inicio,_direcao=_linha_editavel_gavetas(janela,grupo,'A','min',1)
    m.mover(*inicio)
    yield
    m.apertar()
    yield
    m.soltar()
    yield
    m.clicar('A', ctrl=True)
    m.digitar('%dmm' % round(altura+20));m.tecla('RET')
    yield
    assert abs(addon.gavetas.valor(grupo,('A',1))-round(altura+20))<.1
    assert addon.gavetas.medidas(grupo)==antes


def test_arrastar_gavetas_redimensiona_sem_mexer_no_armario(janela, m):
    conj, area, regiao, rv3d = _gavetas_de_frente(janela)
    conj.conj_profundidade_mm = 560.0
    grupo = _gavetas_prontas(janela, conj)
    with contexto(janela, area, regiao):
        addon.gavetas.selecionar(bpy.context, grupo, 'GRUPO')
    rv3d.view_rotation = Euler((math.radians(65), 0, math.radians(-30))).to_quaternion()
    modulo = addon.modulos.medir_conjunto(conj)
    addon.gavetas.definir_abertura(addon.gavetas.gavetas_do_grupo(grupo)[0], 0.4)
    yield
    yield
    for letra, lado in (('L', 'min'), ('A', 'max'), ('P', 'max')):
        for pixels in (-20, 10):
            alvo, inicio, direcao = _linha_editavel_gavetas(janela, grupo, letra, lado)
            fixa = alvo['pontos'][0].copy()
            antes = addon.gavetas.valor(grupo, (letra,))
            m.mover(*inicio)
            yield
            yield
            m.apertar()
            yield
            assert addon.hud._edicao_hud[0] is not None, ('the drag did not start',
                letra, lado, tuple(inicio), bpy.context.object,
                addon.hud._hover_hud, [o.bl_idname for o in janela.modal_operators])
            for passo in range(1, 5):
                m.mover(*(inicio + direcao * pixels * passo / 4))
                yield
            m.soltar()
            yield
            depois = addon.gavetas.valor(grupo, (letra,))
            assert (depois - antes) * pixels > 0, (letra, antes, depois)
            cantos = addon.gavetas.cantos_hud(grupo)
            assert min((c - fixa).length for c in cantos) < 1e-4, 'the fixed corner moved'
            assert all(abs(a - b) < 0.1 for a, b in zip(modulo, addon.modulos.medir_conjunto(conj)))
            assert bpy.context.view_layer.objects.active == grupo
            assert len(addon.gavetas.gavetas_com_slider(bpy.context)) == 3
            assert abs(addon.gavetas.gavetas_do_grupo(grupo)[0][addon.gavetas.CHAVE_ABERTURA] - 0.4) < 0.001


def test_gavetas_arraste_esc_e_digitacao_na_hud(janela, m):
    conj, area, regiao, rv3d = _gavetas_de_frente(janela)
    conj.conj_profundidade_mm = 560.0
    grupo = _gavetas_prontas(janela, conj)
    with contexto(janela, area, regiao):
        addon.gavetas.selecionar(bpy.context, grupo, 'GRUPO')
    rv3d.view_rotation = Euler((math.radians(65), 0, math.radians(-30))).to_quaternion()
    yield
    yield
    for letra in ('A', 'P'):
        antes = addon.gavetas.medidas(grupo)
        origem = grupo.matrix_world.translation.copy()
        _alvo, inicio, direcao = _linha_editavel_gavetas(janela, grupo, letra, 'max')
        m.mover(*inicio)
        yield
        yield
        m.apertar()
        yield
        m.mover(*(inicio - direcao * 20))
        yield
        m.tecla('ESC')
        m.soltar()
        yield
        yield
        assert addon.hud._edicao_hud[0] is None
        assert all(abs(a - b) < 0.1 for a, b in zip(antes, addon.gavetas.medidas(grupo)))
        assert (grupo.matrix_world.translation - origem).length < 1e-4
    _alvo, inicio, _direcao = _linha_editavel_gavetas(janela, grupo, 'L', 'min')
    m.mover(*inicio)
    yield
    yield
    m.apertar()
    yield
    assert addon.hud._edicao_hud[0] is not None, ('click did not open text entry',
        tuple(inicio), bpy.context.object, addon.hud._hover_hud,
        [o.bl_idname for o in janela.modal_operators])
    m.soltar()
    yield
    assert (addon.hud._edicao_hud[0] or {}).get('texto') is not None, addon.hud._edicao_hud[0]
    m.clicar('A', ctrl=True)
    m.digitar('350mm')
    m.tecla('RET')
    yield
    assert abs(addon.gavetas.medidas(grupo)[0] - 350.0) < 0.1


def test_gavetas_esc_apos_modulo_renomeado_e_aumentado(janela, m):
    # Regression v222: a preset's saved name, furniture away from origin, +100 mm.
    # Entering edit and pressing Esc without dragging must not duplicate translation.
    conj, area, regiao, rv3d = _gavetas_de_frente(janela)
    grupo = _gavetas_prontas(janela, conj)
    conj.location += Vector((6.7, -1.25, 0.3))
    conj.name += ' 600x500x300'
    conj.conj_altura_mm += 100.0
    bpy.context.view_layer.update()
    with contexto(janela, area, regiao):
        addon.gavetas.selecionar(bpy.context, grupo, 'GRUPO')
    lo, hi = caixa_mundo(addon.modulos._chapas_do_conjunto(conj))
    rv3d.view_location = (lo + hi) / 2
    rv3d.view_rotation = Euler((math.radians(65), 0, math.radians(-30))).to_quaternion()
    yield
    yield
    origem = grupo.matrix_world.translation.copy()
    medidas = addon.gavetas.medidas(grupo)
    for _ in range(3):
        _alvo, inicio, _direcao = _linha_editavel_gavetas(janela, grupo, 'A', 'max')
        m.mover(*inicio)
        yield
        yield
        m.apertar()
        yield
        m.soltar()
        yield
        assert (addon.hud._edicao_hud[0] or {}).get('texto') is not None
        m.tecla('ESC')
        yield
        yield
        assert addon.hud._edicao_hud[0] is None
        assert (grupo.matrix_world.translation - origem).length < 1e-4
        assert all(abs(a - b) < 0.1 for a, b in zip(medidas, addon.gavetas.medidas(grupo)))
        assert addon.gavetas.modulo_do_grupo(grupo) == conj
        assert grupo[addon.gavetas.CHAVE_MODULO] == conj.name


def test_alt_arrasta_o_ponto_das_gavetas(janela, m):
    # User request: Alt shows three points: two opposite front corners and depth;
    # the upper-left point snaps to a vertex.
    conj, area, regiao, rv3d = _gavetas_de_frente(janela)
    grupo = _gavetas_prontas(janela, conj, n=2)
    with contexto(janela, area, regiao):
        addon.gavetas.selecionar(bpy.context, grupo, 'GRUPO')
        bpy.ops.ed.undo_push(message='Antes da ancora nativa')
    nome = grupo.name
    antes = addon.gavetas.medidas(grupo)
    cursor = bpy.context.scene.cursor.location.copy()
    bloqueados = {o.name: o.hide_select for o in bpy.context.scene.objects}
    overlay = area.spaces.active.overlay.show_cursor
    yield
    yield
    m.mover(*na_tela(regiao, rv3d, addon.gavetas.pontos_editaveis(grupo)[0]))
    yield
    m.janela.event_simulate('LEFT_ALT', 'PRESS', alt=True, x=m.x, y=m.y)
    yield
    yield
    m.apertar(alt=True)
    yield
    assert addon.gavetas._arraste_ponto[0] is not None, 'the point was not grabbed'
    m.mover(m.x + 15, m.y + 10)
    yield
    m.tecla('ESC')
    yield
    yield
    assert addon.gavetas._arraste_ponto[0] is None, 'Esc did not end native snapping'
    assert addon.gavetas.medidas(grupo) == antes
    assert (bpy.context.scene.cursor.location - cursor).length < 1e-6
    assert area.spaces.active.overlay.show_cursor == overlay
    assert bloqueados == {o.name: o.hide_select for o in bpy.context.scene.objects}
    m.mover(*na_tela(regiao, rv3d, addon.gavetas.pontos_editaveis(grupo)[0]))
    yield
    m.apertar(alt=True)
    yield
    assert addon.gavetas._arraste_ponto[0] is not None
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    # The top's lower corner becomes the side's upper corner: the opening rises by E.
    destino = na_tela(regiao, rv3d, _local(conj, -L / 2 + E, -P / 2, A))
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
    assert addon.gavetas._arraste_ponto[0] is None
    _l, altura, _p = addon.gavetas.medidas(grupo)
    assert abs(altura - (A - E)) < 1, altura
    assert (bpy.context.scene.cursor.location - cursor).length < 1e-6
    assert area.spaces.active.overlay.show_cursor == overlay
    assert all(bpy.data.objects[n].hide_select == v for n, v in bloqueados.items()
               if bpy.data.objects.get(n) is not None)
    with contexto(janela, area, regiao):
        bpy.ops.ed.undo()
    yield
    grupo = bpy.data.objects[nome]
    assert all(abs(a - b) < 0.01 for a, b in zip(addon.gavetas.medidas(grupo), antes))
    assert (bpy.context.scene.cursor.location - cursor).length < 1e-6
    with contexto(janela, area, regiao):
        bpy.ops.ed.redo()
    yield
    grupo = bpy.data.objects[nome]
    assert abs(addon.gavetas.medidas(grupo)[1] - (A - E)) < 1
    assert (bpy.context.scene.cursor.location - cursor).length < 1e-6


def test_faces_da_parede_usam_shift_e_menu_permanece_disponivel(janela, m):
    # 399: Shift adds native faces; Ctrl remains reserved for the path.
    import bmesh
    A=addon.ambientes;E=addon.paredes_edicao
    area,regiao,rv=viewport(janela)
    dados=bpy.data.meshes.new('Parede para selecao de faces')
    dados.from_pydata([(-1,1,.5),(0,1,.5),(1,1,.5),(-1,1,2.5),(0,1,2.5),(1,1,2.5)],[],[(0,1,4,3),(1,2,5,4)])
    parede=bpy.data.objects.new(dados.name,dados);bpy.context.scene.collection.objects.link(parede)
    parede[addon.paredes.CHAVE_ALVENARIA]=True
    teto=parede.copy();teto.data=dados.copy();bpy.context.scene.collection.objects.link(teto);teto.location.y=-2
    for obj in bpy.context.selected_objects:obj.select_set(False)
    parede.select_set(True);bpy.context.view_layer.objects.active=parede
    rv.view_rotation=Euler((math.pi/2,0,0)).to_quaternion();rv.view_perspective='ORTHO'
    rv.view_location=(0,1,1.5);rv.view_distance=5;bpy.context.view_layer.update()
    with contexto(janela,area,regiao):bpy.ops.object.cabinet_editar_parede('INVOKE_DEFAULT')
    yield
    try:
        assert bpy.context.mode=='EDIT_MESH' and A._edicao_faces[0] is not None
        m.apertar('LEFT_SHIFT')
        yield
        for x in (-.5,.5):
            m.mover(*na_tela(regiao,rv,Vector((x,1,1.5))))
            yield
            m.clicar('LEFTMOUSE',shift=True)
            yield
        m.soltar('LEFT_SHIFT')
        yield
        assert len([f for f in bmesh.from_edit_mesh(parede.data).faces if f.select])==2
        itens=[]
        with contexto(janela,area,regiao):E.widgets(bpy.context,itens,12,900,400)
        assert "Cancel 2D selection" in [v[4] for v in itens]
        assert not any(v[4] in ("Automatic","By points",'Confirmar area') for v in itens)
        m.tecla('RET')
        yield
        assert E.ativa() and A._edicao_faces[0] is None
    finally:
        A.encerrar_selecao();E.encerrar()


def test_criar_divisorias_e_prateleiras_no_mesmo_volume(janela, m):
    A = addon.areas_criacao
    conj = criar_modulo(janela)
    area, regiao, rv = viewport(janela)
    rv.view_rotation = Euler((math.radians(70), 0, 0)).to_quaternion()
    rv.view_location = (0, 0, .35); rv.view_distance = 2
    bpy.context.scene.cabinet_aba = 'PRATELEIRAS'
    yield
    try:
        m.mover(*widget(janela, lambda v: v[5] == ('operador', 'object.cabinet_definir_area')))
        m.clicar()
        yield
        assert A._internos[0]['etapa'] == 'TIPO'
        m.mover(*widget(janela, lambda v: v[5] == ('resposta',1)));m.clicar()
        yield
        assert A._estado[0] is not None
        m.mover(*na_tela(regiao, rv, conj.matrix_world @ Vector((-.15, -.18, .018))))
        m.clicar()
        yield
        assert len(A.cantos(A.objeto())) == 8
        m.tecla('TAB')
        yield
        assert bpy.context.mode == 'OBJECT'
        for chave, mm in (('L', 300), ('A', 350), ('P', 250)):
            m.mover(*widget(janela, lambda v: v[5][:3] == ('medida', 'area_criacao', chave)))
            m.clicar()
            yield
            m.clicar('A', ctrl=True)
            m.digitar(str(mm)); m.tecla('RET')
            yield
            assert A.objeto() is not None, 'Enter in the field applied the area'
            assert abs(A.valor(A.objeto(), (chave,)) - mm) < .01
        m.mover(*widget(janela, lambda v: v[5] == ('operador', 'object.cabinet_aplicar_area')))
        m.clicar()
        yield
        assert A._estado[0]['etapa'] == 'FRENTE'
        c = A.cantos(A.objeto())
        frente = sum((c[i] for i in (0, 1, 4, 5)), Vector()) / 4
        yield from _clicar_no_mundo(m, regiao, rv, frente)
        assert A._estado[0] is None
        w = addon.divisorias._assistente_divisorias[0]
        assert w and w['etapa'] == 'QUANTIDADE'
        assert len(w['pontos']) == 2 and abs(w['p']['profundidade_mm'] - 250) < .01
        m.mover(regiao.x+regiao.width*.8,regiao.y+regiao.height*.5);m.clicar()
        yield
        assert A._internos[0]['etapa'] == 'CONTINUAR'
        area_criada=dict(A._internos[0]['area'])
        m.mover(*widget(janela,lambda v:v[5]==('resposta',0)));m.clicar()
        yield
        w=addon.prateleiras._assistente_prateleiras[0]
        assert w and w['etapa']=='QUANTIDADE'
        assert A._internos[0]['area']==area_criada
        m.mover(regiao.x+regiao.width*.8,regiao.y+regiao.height*.5);m.clicar()
        yield
        assert sum(len(addon.prateleiras.prateleiras_do_grupo(g)) for g in addon.prateleiras.grupos_do_modulo(conj))==2
        m.mover(*widget(janela,lambda v:v[5]==('resposta',0)));m.clicar()
        yield
        assert A._internos[0] is None
    finally:
        m.tecla('ESC'); m.tecla('ESC')
        A.esquecer()


def test_barra_do_painel_compartilhado_arrasta_sem_rolar_biblioteca(janela, m):
    criar_modulo(janela)
    g = addon.gaveta
    tela = janela.screen
    anterior = tela.get(g._CHAVE_DIVISA, g.DIVISA_PADRAO)
    try:
        tela[g._CHAVE_DIVISA] = .99
        tela[g._CHAVE_ROLAGEM] = 0
        tela[g._CHAVE_ROLAGEM_BIB] = 0
        bpy.context.scene.cabinet_aba = 'MODULOS'
        yield
        area, regiao = gaveta(janela)
        with contexto(janela, area, regiao):
            barras = g._widgets_interativos(bpy.context)
        barra = next(v for v in barras if v[5] and v[5][:2] == ('rolagem', g._CHAVE_ROLAGEM))
        base, h = g._alca_rolagem(barra[1], barra[3], barra[5][2], 0)
        x, y = regiao.x + barra[0] + barra[2] / 2, regiao.y + base + h / 2
        m.mover(x, y); m.apertar()
        yield
        m.mover(x, regiao.y + barra[1])
        yield
        assert tela[g._CHAVE_ROLAGEM] > 0
        assert tela[g._CHAVE_ROLAGEM_BIB] == 0
        m.tecla('ESC')
        yield
        m.soltar()
        assert tela[g._CHAVE_ROLAGEM] == 0
    finally:
        tela[g._CHAVE_DIVISA] = anterior
        tela[g._CHAVE_ROLAGEM] = 0
        tela[g._CHAVE_ROLAGEM_BIB] = 0


rodar([test_scroll_na_cota_subdivide_so_vao_e_esc_descarta_previa,
       test_walk_entre_pontos_preserva_criacao_do_volume,
       test_barra_do_painel_compartilhado_arrasta_sem_rolar_biblioteca,
       test_criar_divisorias_e_prateleiras_no_mesmo_volume,
       test_pontos_da_parede_usam_snap_nativo_e_menu_permanece_disponivel,
       test_gaveta_abre_na_largura_com_medidas_em_linha,
       test_clique_no_puxador_da_gaveta_abre_puxadores,
       test_botao_direito_no_material_pinta_o_comodo,
       test_criar_gavetas_pelo_assistente,
       test_criar_prateleiras_pelo_assistente,
       test_clique_nas_prateleiras_todas_duplo_uma,
       test_escape_na_marcacao_nativa_do_vao,
       test_slider_abre_a_gaveta_e_clique_seleciona,
       test_arrastar_gavetas_redimensiona_sem_mexer_no_armario,
       test_gavetas_arraste_esc_e_digitacao_na_hud,
       test_gavetas_esc_apos_modulo_renomeado_e_aumentado,
       test_altura_de_uma_gaveta_com_previa_esc_e_digitacao,
       test_alt_arrasta_o_ponto_das_gavetas,
       test_arrastar_modulo_com_o_direito_ate_a_parede,
       test_materiais_pela_gaveta,
       test_clique_na_aba_troca_a_aba,
       test_redimensiona_altura_da_biblioteca,
       test_roda_rola_so_a_biblioteca,
       test_duplo_clique_na_foto_insere_no_cursor,
       test_clique_na_foto_e_depois_na_viewport_posiciona,
       test_clique_na_viewport_seleciona_o_modulo,
       test_arrastar_a_seta_da_hud_estica_com_a_quina_parada,
       test_circulo_da_face_translate_b_esc_e_undo,
       test_snap_b_depois_de_arrastar_face_nao_soma_deslocamento_anterior,
       test_snap_b_gavetas_em_corpo_dobrado_e_girado_alinha_vertice_real,
       test_clicar_na_seta_e_digitar_a_medida,
       test_digitar_no_campo_da_gaveta,
       test_arrastar_o_campo_muda_o_valor,
       test_comodo_e_gerar_orcamento_pelas_opcoes,
       test_criar_puxador_no_topo_da_aba,
       test_usar_como_puxador_pela_gaveta,
       test_digitar_com_operador_e_cursor_no_meio,
       test_wizard_dois_cliques_meia_chapa_vira_curva,
       test_wizard_correr_metade_metade_pergunta_moldura,
       test_wizard_basculante_com_pistoes,
       test_wizard_diagonal_invalida_e_voltar_preservam_primeiro_canto,
       test_alt_arrasta_o_canto_da_porta,
       test_slider_abre_a_folha,
       test_resetar_pela_gaveta_move_a_chapa_ativa,
       test_regua_da_viewport_com_o_modulo_ativo_adapta_o_modulo,
       test_regua_que_muda_a_medida_pergunta_e_espera,
       test_arrastar_a_bolinha_troca_a_ancora,
       test_clique_dentro_do_campo_da_gaveta_move_o_cursor,
       test_selecao_da_porta_e_da_folha,
       test_correr_duplo_clique_na_folha_e_clique_no_trilho,
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
