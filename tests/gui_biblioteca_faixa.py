"""Biblioteca no topo: areas nativas, eventos reais e restauracao."""
import os
import sys
import tempfile
import json
import shutil
import bpy
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))
import cabinet_creator as addon
from harness_gui import rodar, esperar, viewport_principal, Pular

REAL = addon.opcoes._pasta_addon()
PASTA = tempfile.mkdtemp(prefix='cabinet_faixa_gui_')
with open(os.path.join(REAL, 'indice.json'), encoding='utf-8') as f:
    todos = json.load(f)
grupos = {}
for it in todos:
    grupos.setdefault(addon.biblioteca.caminho_de(it), []).append(it)
CAMINHO, AMOSTRA = max(grupos.items(), key=lambda par: len(par[1]))
AMOSTRA = AMOSTRA[:12]
for it in AMOSTRA:
    for nome in (it['arquivo'], os.path.splitext(it['arquivo'])[0] + '.png'):
        if os.path.isfile(os.path.join(REAL, nome)):
            shutil.copyfile(os.path.join(REAL, nome), os.path.join(PASTA, nome))
with open(os.path.join(PASTA, 'indice.json'), 'w', encoding='utf-8') as f:
    json.dump(AMOSTRA, f)
addon.biblioteca.pasta_biblioteca = lambda: PASTA
addon.opcoes._pasta_addon = lambda: PASTA
F = addon.biblioteca_faixa


def contexto(janela, area):
    regiao = next(r for r in area.regions if r.type == 'WINDOW')
    return bpy.context.temp_override(window=janela, area=area, region=regiao)


def preparar(janela):
    addon.register()


def clicar_widget(janela, m, filtro):
    area = F.area_da_faixa(janela.screen)
    regiao = next(r for r in area.regions if r.type == 'WINDOW')
    with contexto(janela, area):
        v = next(v for v in F.interativos(bpy.context) if v[5] and filtro(v))
    m.mover(regiao.x + v[0] + v[2] / 2, regiao.y + v[1] + v[3] / 2)
    yield
    m.clicar()
    yield


def test_abre_acima_das_duas_colunas_e_fecha_restaurando_vista(janela, m):
    principal, _, rv = viewport_principal(janela)
    antes = set(a.as_pointer() for a in janela.screen.areas)
    rv.view_distance = 7.0
    rv.view_location = (1.0, 2.0, 3.0)
    with contexto(janela, principal):
        bpy.ops.object.cabinet_alternar_gaveta()
    yield esperar(0.7)
    topo = F.area_da_faixa(janela.screen)
    menu = addon.gaveta._area_gaveta(janela.screen)
    cena = F.viewport(janela.screen)
    assert topo is not None and menu is not None, [(a.x,a.y,a.width,a.height) for a in janela.screen.areas]
    assert topo.y >= menu.y + menu.height - 5
    assert topo.x == menu.x and abs(topo.width - menu.width - cena.width) < 8
    janela.screen[F.CHAVE_AREA] = 0
    janela.screen[addon.gaveta._CHAVE_GAVETA] = 0
    F.reconectar(janela.screen)
    assert F.area_da_faixa(janela.screen) == topo
    assert addon.gaveta._area_gaveta(janela.screen) == menu
    assert abs(cena.spaces.active.region_3d.view_distance - 7.0) < 1e-5
    assert (cena.spaces.active.region_3d.view_location - rv.view_location).length < 1e-5
    with contexto(janela, topo):
        assert addon.gaveta_eventos.OBJECT_OT_interagir_gaveta.poll(bpy.context)
        assert not addon.selecao.OBJECT_OT_selecionar.poll(bpy.context)
        assert not addon.hud._contexto_hud(bpy.context)
    with contexto(janela, menu):
        widgets = addon.gaveta._widgets_gaveta(bpy.context, 480, 900)
        assert not any(v[5] and v[5][0] in ('preset','material','biblioteca','divisa') for v in widgets)
    with contexto(janela, cena):
        bpy.ops.object.cabinet_alternar_gaveta()
    yield
    assert F.area_da_faixa(janela.screen) is None
    assert addon.gaveta._area_gaveta(janela.screen) is None
    assert len(janela.screen.areas) == len(antes)
    cena = F.viewport(janela.screen)
    assert abs(cena.spaces.active.region_3d.view_distance - 7.0) < 1e-5


def test_recolhe_expande_e_clique_troca_modo_so_na_faixa(janela, m):
    cena = F.viewport(janela.screen)
    with contexto(janela, cena):
        bpy.ops.object.cabinet_alternar_gaveta()
    yield esperar(0.7)
    topo = F.area_da_faixa(janela.screen)
    altura = topo.height
    yield from clicar_widget(janela, m, lambda v: v[5] == ('operador','object.cabinet_recolher_biblioteca'))
    yield esperar(0.4)

    assert topo.height < altura / 2, (altura,topo.height,F._alturas[0],janela.screen.get(F.CHAVE_RECOLHIDA))
    yield from clicar_widget(janela, m, lambda v: v[5] == ('operador','object.cabinet_recolher_biblioteca'))
    yield esperar(0.4)
    assert abs(topo.height - altura) < 8
    with contexto(janela, topo):
        widgets = F.interativos(bpy.context)
    v = next(v for v in widgets if v[5] and v[5][:2] == ('biblioteca','MATERIAIS'))
    regiao = next(r for r in topo.regions if r.type == 'WINDOW')
    m.mover(regiao.x + v[0] + v[2]/2, regiao.y + v[1] + v[3]/2)
    yield
    m.clicar()
    yield
    assert bpy.context.scene.cabinet_bib_modo == 'MATERIAIS'
    with contexto(janela, F.viewport(janela.screen)):
        bpy.ops.object.cabinet_alternar_gaveta()
    yield


def test_miniaturas_rolam_na_faixa_e_preset_chega_na_cena(janela, m):
    cena = F.viewport(janela.screen)
    with contexto(janela, cena):
        bpy.ops.object.cabinet_alternar_gaveta()
        bpy.context.scene.cabinet_bib_modo = 'MODULOS'
        addon.biblioteca.definir_trilha(bpy.context.scene, CAMINHO)
    yield esperar(0.7)
    topo = F.area_da_faixa(janela.screen)
    with contexto(janela, topo):
        widgets = F.interativos(bpy.context)
    fotos = [v for v in widgets if v[5] and v[5][0] == 'preset']
    assert fotos, CAMINHO
    assert len(set(v[1] for v in fotos)) == 1
    assert not any(v[5] and v[5][0] == 'rolar_nivel' for v in widgets), 'seta numa fila que cabe inteira'
    assert addon.gaveta._fotos_gaveta, 'as fotos nao foram carregadas'
    with contexto(janela, topo):
        bpy.ops.screen.screenshot(filepath=os.path.join(PASTA, 'faixa-228.png'))
    print('FOTO_FAIXA', os.path.join(PASTA, 'faixa-228.png'))
    if bpy.app.version >= (5,):
        regiao = next(r for r in topo.regions if r.type == 'WINDOW')
        v = fotos[0]
        m.mover(regiao.x + v[0] + v[2]/2, regiao.y + v[1] + v[3]/2)
        yield
        m.apertar()
        yield
        assert any(o.bl_idname.endswith('cabinet_arrastar_preset') for o in janela.modal_operators)
        destino = next(r for r in F.viewport(janela.screen).regions if r.type == 'WINDOW')
        m.mover(destino.x + destino.width / 2, destino.y + destino.height / 2)
        yield
        m.soltar()
        yield
        assert any(addon.chapas.MARCA_CONJUNTO in o for o in bpy.context.scene.objects)
    with contexto(janela, F.viewport(janela.screen)):
        bpy.ops.object.cabinet_alternar_gaveta()
    yield


def test_material_clique_simples_nao_pinta_duplo_pinta(janela, m):
    with contexto(janela, F.viewport(janela.screen)):
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.object
        bpy.ops.object.cabinet_alternar_gaveta()
    yield esperar(0.7)
    cena = bpy.context.scene
    cena.cabinet_bib_modo = 'MATERIAIS'
    cena.cabinet_mat_n1, cena.cabinet_mat_n2, cena.cabinet_mat_n3 = 'MDF', 'Teste', ''
    addon.materiais.gravar_materiais([dict(nome='Vermelho', n1='MDF', n2='Teste', n3='', cor='#CC2222')])
    F.invalidar()
    yield
    yield from clicar_widget(janela, m, lambda v: v[5][0] == 'material')
    assert not obj.data.materials, 'um clique pintou'
    yield esperar(0.4)
    yield from clicar_widget(janela, m, lambda v: v[5][0] == 'material')
    yield from clicar_widget(janela, m, lambda v: v[5][0] == 'material')
    assert obj.data.materials, 'duplo clique nao pintou'
    with contexto(janela, F.viewport(janela.screen)):
        bpy.ops.object.cabinet_alternar_gaveta()
    yield


def test_migra_menu_antigo_sem_perder_vista(janela, m):
    principal = F.viewport(janela.screen)
    janela.screen[F.CHAVE_LAYOUT] = 0
    janela.screen[addon.gaveta._CHAVE_PENDENTE] = str(principal.as_pointer())
    with contexto(janela, principal):
        bpy.ops.screen.area_split(direction='VERTICAL', factor=0.3)
    bpy.app.timers.register(addon.gaveta._configurar_gavetas, first_interval=0.05)
    yield esperar(0.3)
    assert addon.gaveta._area_gaveta(janela.screen) is not None
    addon.gaveta._reconectar_gavetas()
    yield esperar(0.7)
    assert janela.screen[F.CHAVE_LAYOUT] == 2
    assert F.area_da_faixa(janela.screen) is not None
    with contexto(janela, F.viewport(janela.screen)):
        bpy.ops.object.cabinet_alternar_gaveta()
    yield


def test_direito_na_foto_e_no_nome_abre_menu_so_ao_soltar(janela, m):
    with contexto(janela, F.viewport(janela.screen)):
        bpy.ops.object.cabinet_alternar_gaveta()
        bpy.context.scene.cabinet_bib_modo = 'MODULOS'
        addon.biblioteca.definir_trilha(bpy.context.scene, CAMINHO)
    yield esperar(0.7)
    topo = F.area_da_faixa(janela.screen)
    regiao = next(r for r in topo.regions if r.type == 'WINDOW')
    with contexto(janela, topo):
        v = next(v for v in F.interativos(bpy.context) if v[5] and v[5][0] == 'preset')
    abrir = F.abrir_menu_item
    chamadas = []
    def observar(context, it):
        chamadas.append(it['arquivo'])
        return abrir(context, it)
    F.abrir_menu_item = observar
    try:
        antes = set(o.name for o in bpy.context.scene.objects)
        it = v[5][1]
        bloqueado_antes = addon.biblioteca.item_bloqueado(it)
        for y in (v[1] + v[3] - 25, v[1] + 10):
            m.mover(regiao.x + v[0] + v[2] / 2, regiao.y + y)
            yield
            n = len(chamadas)
            m.apertar('RIGHTMOUSE')
            yield
            assert len(chamadas) == n, 'menu abriu no PRESS'
            m.soltar('RIGHTMOUSE')
            yield
            assert len(chamadas) == n + 1, chamadas
            assert set(o.name for o in bpy.context.scene.objects) == antes, 'menu inseriu ao abrir'
            if len(chamadas) == 1:
                with contexto(janela, topo):
                    bpy.ops.screen.screenshot(filepath=os.path.join(PASTA, 'menu-227.png'))
                print('FOTO_MENU', os.path.join(PASTA, 'menu-227.png'))
            if len(chamadas) == 2:
                m.tecla('DOWN_ARROW')
                yield
                m.tecla('DOWN_ARROW')
                yield
                m.tecla('RET')
            else:
                m.tecla('ESC')
            yield
        # A UI nativa executa o operador depois de encerrar o popup.
        yield esperar(0.2)
        assert addon.biblioteca.item_bloqueado(addon.biblioteca._achar_item(
            it['pasta'], it['arquivo'])) != bloqueado_antes, 'menu nao acionou cadeado'
        # Restaurar a fixture usando a mesma acao do menu.
        with contexto(janela, topo):
            assert bpy.ops.object.cabinet_acao_item_biblioteca(
                pasta=it['pasta'], arquivo=it['arquivo'], indice=2) == {'FINISHED'}
            assert addon.biblioteca.item_bloqueado(addon.biblioteca._achar_item(
                it['pasta'], it['arquivo'])) == bloqueado_antes
    finally:
        F.abrir_menu_item = abrir
    with contexto(janela, F.viewport(janela.screen)):
        bpy.ops.object.cabinet_alternar_gaveta()
    yield


def test_arrastar_borda_para_cima_alinha_subcategorias(janela, m):
    with contexto(janela, F.viewport(janela.screen)):
        bpy.ops.object.cabinet_alternar_gaveta()
        bpy.context.scene.cabinet_bib_modo = 'MODULOS'
        addon.biblioteca.definir_trilha(bpy.context.scene, CAMINHO)
    yield esperar(0.7)
    topo = F.area_da_faixa(janela.screen)
    escala = max(1, bpy.context.preferences.system.ui_scale)
    x, y = topo.x + topo.width // 2, topo.y
    destino = y + topo.height - int(120 * escala)
    m.mover(x, y)
    yield
    m.apertar()
    yield
    m.mover(x, destino)
    yield
    m.soltar()
    yield esperar(0.2)
    assert topo.height < F.ALTURA_COMPACTA * escala, topo.height
    with contexto(janela, topo):
        widgets = F.interativos(bpy.context)
        grupos = [v for v in widgets if v[5] and v[5][0] == 'navegar' and v[5][1] > 1]
        assert {v[5][1] for v in grupos} == set(range(2, len(CAMINHO) + 1))
        assert len({v[1] for v in grupos}) == 1
        assert any(v[5] and v[5][0] == 'preset' for v in widgets), 'fotos fora da faixa'
        assert sum(v[5] == ('separador', 'biblioteca') for v in widgets) == len(CAMINHO)
        bpy.ops.screen.screenshot(filepath=os.path.join(PASTA, 'faixa-baixa-229.png'))
    print('FOTO_FAIXA_BAIXA', os.path.join(PASTA, 'faixa-baixa-229.png'))
    yield from clicar_widget(janela, m, lambda v: v[5][0] == 'navegar' and v[5][1] == len(CAMINHO))
    assert tuple(addon.biblioteca.trilha_da_cena(bpy.context.scene)) == tuple(CAMINHO[:-1])
    yield from clicar_widget(janela, m, lambda v: v[5][0] == 'navegar' and v[5][1] == len(CAMINHO))
    assert tuple(addon.biblioteca.trilha_da_cena(bpy.context.scene)) == tuple(CAMINHO)
    # Regressao: tooltip pendente ao trocar a quantidade de alvos e fechar.
    yield esperar(0.2)
    with contexto(janela, F.viewport(janela.screen)):
        bpy.ops.object.cabinet_alternar_gaveta()
    yield


rodar([test_abre_acima_das_duas_colunas_e_fecha_restaurando_vista,
       test_recolhe_expande_e_clique_troca_modo_so_na_faixa,
       test_miniaturas_rolam_na_faixa_e_preset_chega_na_cena,
       test_material_clique_simples_nao_pinta_duplo_pinta,
       test_direito_na_foto_e_no_nome_abre_menu_so_ao_soltar,
       test_arrastar_borda_para_cima_alinha_subcategorias,
       test_migra_menu_antigo_sem_perder_vista], preparar=preparar)
