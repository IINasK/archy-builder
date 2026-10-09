"""Execute no Blender: --background --factory-startup --python-exit-code 1 --python tests/test_hud_blender.py."""
import inspect
import os
import sys
import unittest
from types import SimpleNamespace

import bpy
import bmesh
import math

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon


class _ContextoRegiao:
    """bpy.context com uma regiao fixa (o clique guarda estado por ela)."""
    region = SimpleNamespace(as_pointer=lambda: 4242)

    def __getattr__(self, nome):
        return getattr(bpy.context, nome)


class TestHUD(unittest.TestCase):
    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        addon._clique_chapa_hud.clear()
        addon._hover_hud.clear()

    def modulo(self):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar()
        modulo = bpy.context.object
        bpy.context.view_layer.update()
        return modulo

    def test_clique_seleciona_todo_modulo_e_duplo_isola_chapa(self):
        modulo = self.modulo()
        chapa = addon._chapas_do_conjunto(modulo)[0]
        addon._selecionar_chapa_hud(bpy.context, chapa)
        self.assertEqual(set(bpy.context.selected_objects),
                         {modulo, *modulo.children_recursive})
        self.assertEqual(bpy.context.object, modulo)
        addon._selecionar_chapa_hud(bpy.context, chapa, individual=True)
        self.assertEqual(list(bpy.context.selected_objects), [chapa])
        self.assertEqual(bpy.context.object, chapa)
        self.assertEqual(chapa.chapa_modo, 'INDIVIDUAL')

    def test_hud_nao_aceita_modo_edicao(self):
        self.assertFalse(addon._contexto_hud(SimpleNamespace(mode='EDIT_MESH')))

    def test_contorno_grupo_tem_quatro_arestas_por_eixo_e_sem_E(self):
        modulo = self.modulo()
        geometria = addon._geometria_hud(bpy.context)
        self.assertEqual(geometria['objeto'], modulo)
        self.assertEqual(len(geometria['cantos']), 8)
        self.assertEqual(len(geometria['linhas']), 12)
        self.assertEqual({l['letra'] for l in geometria['linhas']}, {'L', 'A', 'P'})
        for eixo in range(3):
            self.assertEqual(sum(l['eixo'] == eixo for l in geometria['linhas']), 4)

    def test_individual_usa_espessura_local_mesmo_girada(self):
        modulo = self.modulo()
        chapa = next(o for o in addon._chapas_do_conjunto(modulo)
                     if abs(o.rotation_euler.y) > 1)
        addon._selecionar_chapa_hud(bpy.context, chapa, individual=True)
        geometria = addon._geometria_hud(bpy.context)
        arestas = [l for l in geometria['linhas'] if l['letra'] == 'E']
        self.assertEqual(len(arestas), 4)
        for linha in arestas:
            a, b = linha['pontos']
            self.assertAlmostEqual((b-a).length, chapa.chapa_espessura_mm/1000, places=5)

    def test_hit_test_em_tela_reconhece_canto_e_aresta(self):
        self.modulo()
        geometria = addon._geometria_hud(bpy.context)
        for profundidade in (-180, 80, 230):
            projetar = lambda p: Vector((300+p.x*500+p.y*profundidade,
                                        200+p.z*500+p.y*100))
            canto = addon._acertar_linhas_hud(
                geometria, projetar(geometria['cantos'][0]), projetar)
            self.assertEqual(canto['tipo'], 'ancora')
            linha = geometria['linhas'][0]
            ponto = sum(linha['pontos'], Vector())/2
            atingida = addon._acertar_linhas_hud(geometria, projetar(ponto), projetar)
            self.assertEqual(atingida['tipo'], 'medida')
            self.assertEqual(atingida['eixo'], linha['eixo'])

    def test_contorno_porta_e_gap_sao_distintos_do_modulo(self):
        modulo = self.modulo()
        bpy.ops.object.cabinet_portas(
            capturado=True, ponto_a=(-0.3, -0.15, 0), ponto_b=(0.3, -0.15, 0.4),
            pai_nome=modulo.name, modulo_nome=modulo.name,
            frente='NEG_Y', folhas=2)
        geometria = addon._geometria_hud(bpy.context)
        self.assertEqual(sum(l['tipo'] == 'medida' for l in geometria['linhas']), 12)
        self.assertEqual(sum(l['tipo'] == 'contorno_porta' for l in geometria['linhas']), 12)
        gaps = [l for l in geometria['linhas'] if l['tipo'] == 'gap']
        self.assertEqual(len(gaps), 1)
        self.assertIn(addon.MARCA_PORTAS, gaps[0]['objeto'])
        projetar = lambda p: Vector((300+p.x*500+p.y*100, 100+p.z*500))
        meio = sum(gaps[0]['pontos'], Vector())/2
        atingido = addon._acertar_linhas_hud(geometria, projetar(meio), projetar)
        self.assertEqual(atingido['tipo'], 'gap')
        folha = addon._folhas_portas(gaps[0]['objeto'])[0]
        addon._selecionar_chapa_hud(bpy.context, folha)
        self.assertEqual(bpy.context.object, modulo)
        self.assertEqual(set(bpy.context.selected_objects),
                         {modulo, *modulo.children_recursive})

    def test_hover_acende_as_quatro_arestas_do_eixo(self):
        self.modulo()
        geometria = addon._geometria_hud(bpy.context)
        for eixo in range(3):
            alvo = next(l for l in geometria['linhas'] if l['eixo'] == eixo)
            normais, acesos = addon._segmentos_hud(geometria, alvo)
            self.assertEqual(len(acesos), 8)
            self.assertEqual(len(normais), 16)

    def test_arraste_dimensao_atualiza_a_mesma_propriedade_do_menu(self):
        modulo = self.modulo()
        geometria = addon._geometria_hud(bpy.context)
        for letra, prop, valor in (('L', 'conj_largura_mm', 900),
                                   ('A', 'conj_altura_mm', 1300),
                                   ('P', 'conj_profundidade_mm', 450)):
            alvo = next(l for l in geometria['linhas'] if l['letra'] == letra)
            addon._aplicar_valor_hud(bpy.context, alvo, valor)
            self.assertAlmostEqual(getattr(modulo, prop), valor)
            campos = addon._medidas_gaveta(bpy.context)[1]
            self.assertIn(valor, [v for _, v, _ in campos])

    def test_linha_perto_da_quina_ancora_e_estica_para_o_outro_lado(self):
        projetar = lambda p: Vector((300+p.x*500+p.y*150, 200+p.z*500+p.y*90))
        for eixo, prop in ((0, 'conj_largura_mm'), (1, 'conj_profundidade_mm'),
                           (2, 'conj_altura_mm')):
            for lado in ('min', 'max'):
                with self.subTest(eixo=eixo, lado=lado):
                    self.setUp()
                    modulo = self.modulo()
                    chapas = addon._chapas_do_conjunto(modulo)
                    lo, hi = (list(v) for v in addon._caixa_de(chapas))
                    geometria = addon._geometria_hud(bpy.context)
                    linha = next(l for l in geometria['linhas']
                                 if l['eixo'] == eixo)
                    a, b = linha['pontos']
                    # mouse a 1/5 da aresta, do lado pedido, fora do
                    # raio da quina
                    perto, longe = (a, b) if lado == 'min' else (b, a)
                    mouse = projetar(perto + (longe - perto) * 0.2)
                    alvo = addon._acertar_linhas_hud(geometria, mouse, projetar)
                    self.assertEqual(alvo['tipo'], 'medida')
                    self.assertEqual(alvo['lado'], lado)
                    self.assertEqual(alvo['pontos'][0], perto)
                    # a linha compartilhada nao foi alterada
                    self.assertNotIn('lado', linha)
                    novo = getattr(modulo, prop) + 100
                    addon._aplicar_valor_hud(bpy.context, alvo, novo)
                    lo2, hi2 = addon._caixa_de(chapas)
                    if lado == 'min':
                        self.assertAlmostEqual(lo2[eixo], lo[eixo], places=5)
                        self.assertAlmostEqual(hi2[eixo], hi[eixo] + 0.1, places=5)
                    else:
                        self.assertAlmostEqual(hi2[eixo], hi[eixo], places=5)
                        self.assertAlmostEqual(lo2[eixo], lo[eixo] - 0.1, places=5)
                    self.assertAlmostEqual(getattr(modulo, prop), novo, places=3)

    def test_tres_eixos_de_uma_vez_respeitam_a_ancora(self):
        # REGRESSAO: o segundo eixo lia matrix_world defasado e gravava
        # de volta o centro antigo -- a peca crescia pelo meio.
        modulo = self.modulo()
        chapas = addon._chapas_do_conjunto(modulo)
        lo, hi = (list(v) for v in addon._caixa_de(chapas))
        addon.redimensionar_grupo(
            chapas, (modulo.conj_largura_mm + 100, modulo.conj_altura_mm + 50,
                     modulo.conj_profundidade_mm + 30), ('max', 'max', 'min'))
        lo2, hi2 = addon._caixa_de(chapas)
        self.assertAlmostEqual(hi2[0], hi[0], places=5)
        self.assertAlmostEqual(lo2[0], lo[0] - 0.1, places=5)
        self.assertAlmostEqual(hi2[1], hi[1], places=5)
        self.assertAlmostEqual(lo2[2], lo[2], places=5)
        self.assertAlmostEqual(hi2[2], hi[2] + 0.05, places=5)

    def test_chapa_solta_cresce_pela_ancora_mesmo_com_cena_defasada(self):
        bpy.ops.object.cabinet_criar()
        chapa = bpy.context.object
        chapa.chapa_modo = 'GRUPO'
        cena = bpy.context.scene
        cena.grupo_profundidade_mm = 123.0      # valor velho de outro grupo
        lo, hi = (list(v) for v in addon._caixa_de([chapa]))
        geometria = addon._geometria_hud(bpy.context)
        projetar = lambda p: Vector((300+p.x*500+p.y*150, 200+p.z*500+p.y*90))
        linha = next(l for l in geometria['linhas'] if l['eixo'] == 0)
        a, b = linha['pontos']
        alvo = addon._acertar_linhas_hud(geometria, projetar(a + (b - a) * 0.2),
                                         projetar)
        self.assertEqual(alvo['lado'], 'min')
        addon._aplicar_valor_hud(bpy.context, alvo, (hi[0] - lo[0]) * 1000 + 100)
        lo2, hi2 = addon._caixa_de([chapa])
        self.assertAlmostEqual(lo2[0], lo[0], places=5)
        self.assertAlmostEqual(hi2[0], hi[0] + 0.1, places=5)
        # o eixo que ninguem tocou continua igual
        self.assertAlmostEqual(hi2[1] - lo2[1], hi[1] - lo[1], places=5)

    def test_chapa_individual_tambem_cresce_pela_ancora(self):
        modulo = self.modulo()
        chapa = addon._chapas_do_conjunto(modulo)[0]
        addon._selecionar_chapa_hud(bpy.context, chapa, individual=True)
        geometria = addon._geometria_hud(bpy.context)
        self.assertEqual(geometria['modo'], 'INDIVIDUAL')
        projetar = lambda p: Vector((300+p.x*500+p.y*150, 200+p.z*500+p.y*90))
        for eixo, lado in ((0, 'max'), (1, 'min')):
            linha = next(l for l in geometria['linhas'] if l['eixo'] == eixo)
            a, b = linha['pontos']
            perto, longe = (a, b) if lado == 'min' else (b, a)
            alvo = addon._acertar_linhas_hud(
                geometria, projetar(perto + (longe - perto) * 0.2), projetar)
            self.assertEqual(alvo['lado'], lado)
            fixa = perto.copy()
            antes = addon._valor_hud(alvo)
            addon._aplicar_valor_hud(bpy.context, alvo, antes + 80)
            self.assertAlmostEqual(addon._valor_hud(alvo), antes + 80, places=3)
            nova = addon._geometria_hud(bpy.context)
            i, j = alvo['cantos']
            agora = nova['cantos'][i] if lado == 'min' else nova['cantos'][j]
            self.assertLess((agora - fixa).length, 1e-5)
            geometria = nova
        # E (espessura) tambem tem seta nas quinas (pedido do usuario):
        # a face da quina perto do mouse fica parada, engrossa para o
        # outro lado -- nos dois sentidos.
        for lado, soma in (('min', 12.0), ('max', -10.0)):
            linha = next(l for l in geometria['linhas'] if l['eixo'] == 2)
            a, b = linha['pontos']
            perto, longe = (a, b) if lado == 'min' else (b, a)
            alvo = addon._acertar_linhas_hud(
                geometria, projetar(perto + (longe - perto) * 0.2), projetar)
            self.assertEqual((alvo['tipo'], alvo['eixo'], alvo['lado']),
                             ('medida', 2, lado))
            self.assertEqual(addon._letra_do_alvo(alvo), 'E')
            fixa = perto.copy()
            antes = addon._valor_hud(alvo)
            addon._aplicar_valor_hud(bpy.context, alvo, antes + soma)
            self.assertAlmostEqual(chapa.chapa_espessura_mm, antes + soma,
                                   places=3)
            self.assertAlmostEqual(chapa.dimensions.z,
                                   (antes + soma) / 1000, places=5)
            nova = addon._geometria_hud(bpy.context)
            i, j = alvo['cantos']
            agora = nova['cantos'][i] if lado == 'min' else nova['cantos'][j]
            self.assertLess((agora - fixa).length, 1e-5)
            geometria = nova

    def dois_modulos(self):
        modulos = []
        for x in (-2.0, 2.0):
            antes = set(bpy.data.objects)
            bpy.ops.object.cabinet_criar_nicho()
            bpy.ops.object.select_all(action='DESELECT')
            for o in set(bpy.data.objects) - antes:
                o.select_set(True)
            bpy.ops.object.cabinet_agrupar()
            modulo = bpy.context.object
            modulo.location.x = x
            bpy.context.view_layer.update()
            modulos.append(modulo)
        primeiro, segundo = modulos
        for m in (primeiro, segundo):
            for o in [m, *m.children_recursive]:
                o.select_set(True)
        bpy.context.view_layer.objects.active = primeiro
        return primeiro, segundo

    def test_clique_num_de_varios_selecionados_deixa_so_ele_ao_soltar(self):
        primeiro, segundo = self.dois_modulos()
        chapa = addon._chapas_do_conjunto(segundo)[0]
        self.addCleanup(addon._clique_pendente.clear)
        original = addon._raio_hud
        addon._raio_hud = lambda _c, _l: (chapa, None)
        self.addCleanup(setattr, addon, '_raio_hud', original)
        contexto = _ContextoRegiao()
        evento = SimpleNamespace(mouse_region_x=10, mouse_region_y=10)
        classe = addon.OBJECT_OT_selecionar

        def clicar(valor):
            op = SimpleNamespace(
                modo='INDIVIDUAL' if valor == 'DOUBLE_CLICK' else 'GRUPO',
                extend=False, deselect=False, toggle=False,
                deselect_all=True, location=(0, 0),
                select_passthrough=valor == 'PRESS', clique=valor == 'CLICK')
            op._soltou = lambda c, p: classe._soltou(op, c, p)
            op._invoke = lambda c, e: classe._invoke(op, c, e)
            op.execute = lambda c: {'CANCELLED'}
            return classe.invoke(op, contexto, evento)

        dois = {primeiro, *primeiro.children_recursive,
                segundo, *segundo.children_recursive}
        # PRESS: nada muda -- arrastar ainda leva os dois modulos
        self.assertIn('PASS_THROUGH', clicar('PRESS'))
        self.assertEqual(set(bpy.context.selected_objects), dois)
        # soltou sem arrastar: so' o modulo clicado
        self.assertEqual(clicar('CLICK'), {'FINISHED'})
        self.assertEqual(set(bpy.context.selected_objects),
                         {segundo, *segundo.children_recursive})
        self.assertEqual(bpy.context.object, segundo)
        # sozinho: o PRESS seleciona direto e o CLICK nao se mete
        self.assertEqual(clicar('PRESS'), {'FINISHED'})
        self.assertEqual(clicar('CLICK'), {'PASS_THROUGH'})
        self.assertEqual(set(bpy.context.selected_objects),
                         {segundo, *segundo.children_recursive})
        # duplo clique partindo de varios selecionados ainda isola a chapa
        for o in dois:
            o.select_set(True)
        for valor in ('PRESS', 'CLICK', 'DOUBLE_CLICK'):
            clicar(valor)
        self.assertEqual(bpy.context.selected_objects, [chapa])

    def clicar_pelo_keymap(self, chapa, valor, shift=False):
        """Roda cabinet_selecionar com as props da entrada do keymap
        (valor, shift), com o raio acertando `chapa`."""
        entrada = next(e for e in addon._ENTRADAS_KEYMAP
                       if e[0] == valor and e[1] == shift)
        original = addon._raio_hud
        addon._raio_hud = lambda _c, _l: (chapa, None)
        classe = addon.OBJECT_OT_selecionar
        props = dict(extend=False, deselect=False, toggle=False,
                     deselect_all=False, select_passthrough=False,
                     clique=False)
        props.update(entrada[3])
        op = SimpleNamespace(modo=entrada[2], location=(0, 0), **props)
        op._soltou = lambda c, p: classe._soltou(op, c, p)
        op._invoke = lambda c, e: classe._invoke(op, c, e)
        op.execute = lambda c: {'CANCELLED'}
        try:
            return classe.invoke(op, _ContextoRegiao(), SimpleNamespace(
                mouse_region_x=10, mouse_region_y=10))
        finally:
            addon._raio_hud = original

    def duplo(self, chapa, shift=False):
        """O que o Blender entrega num duplo clique: PRESS e DOUBLE_CLICK."""
        self.clicar_pelo_keymap(chapa, 'PRESS', shift)
        self.clicar_pelo_keymap(chapa, 'DOUBLE_CLICK', shift)

    def test_shift_soma_chapas_individuais_do_mesmo_grupo(self):
        # Pedido do usuario: clique = grupo; duplo = uma chapa dele;
        # Shift+clique em outra chapa do MESMO grupo soma so' ela
        self.addCleanup(addon._clique_chapa_hud.clear)
        primeiro, _segundo = self.dois_modulos()
        a1, a2, a3 = addon._chapas_do_conjunto(primeiro)[:3]
        bpy.ops.object.select_all(action='DESELECT')
        self.clicar_pelo_keymap(a1, 'PRESS')
        self.assertTrue(primeiro.select_get())
        self.duplo(a1)
        self.assertEqual(set(bpy.context.selected_objects), {a1})
        self.clicar_pelo_keymap(a2, 'PRESS', shift=True)
        self.assertEqual(set(bpy.context.selected_objects), {a1, a2})
        self.assertEqual(bpy.context.object, a2)
        self.assertEqual(a2.chapa_modo, 'INDIVIDUAL')
        self.clicar_pelo_keymap(a3, 'PRESS', shift=True)
        self.assertEqual(set(bpy.context.selected_objects), {a1, a2, a3})
        # Shift+clique na chapa ATIVA tira ela, como o Shift nativo
        self.clicar_pelo_keymap(a3, 'PRESS', shift=True)
        self.assertEqual(set(bpy.context.selected_objects), {a1, a2})

    def test_shift_com_varios_grupos_e_duplo_isola_dentro_da_selecao(self):
        self.addCleanup(addon._clique_chapa_hud.clear)
        primeiro, segundo = self.dois_modulos()
        grupo_a = {primeiro, *primeiro.children_recursive}
        grupo_b = {segundo, *segundo.children_recursive}
        a1 = addon._chapas_do_conjunto(primeiro)[0]
        b1 = addon._chapas_do_conjunto(segundo)[1]
        bpy.ops.object.select_all(action='DESELECT')
        # clique no grupo A, Shift+clique no grupo B: os dois grupos
        self.clicar_pelo_keymap(a1, 'PRESS')
        self.clicar_pelo_keymap(b1, 'PRESS', shift=True)
        self.assertEqual(set(bpy.context.selected_objects), grupo_a | grupo_b)
        # Shift+duplo numa chapa de A: so' ela de A; B continua inteiro
        self.duplo(a1, shift=True)
        self.assertEqual(set(bpy.context.selected_objects), {a1} | grupo_b)
        self.assertEqual(bpy.context.object, a1)
        # Shift+duplo numa chapa de B: a1 continua, b1 entra sozinha
        self.duplo(b1, shift=True)
        self.assertEqual(set(bpy.context.selected_objects), {a1, b1})
        # mais um Shift+duplo em A: soma, sem perder ninguem
        a2 = addon._chapas_do_conjunto(primeiro)[1]
        self.duplo(a2, shift=True)
        self.assertEqual(set(bpy.context.selected_objects), {a1, a2, b1})
        # clique simples sem Shift volta ao grupo inteiro
        self.clicar_pelo_keymap(b1, 'PRESS')
        self.clicar_pelo_keymap(b1, 'CLICK')
        self.assertEqual(set(bpy.context.selected_objects), grupo_b)

    def test_props_do_clique_nao_herdam_o_ultimo_uso(self):
        # o keymap so' preenche o que cita: sem SKIP_SAVE, o toggle de um
        # Shift+clique vazava para o clique simples seguinte
        props = addon.OBJECT_OT_selecionar.__annotations__
        for nome in ('extend', 'deselect', 'toggle', 'deselect_all',
                     'select_passthrough', 'clique'):
            self.assertIn('SKIP_SAVE', props[nome].keywords.get('options', ()),
                          nome)
        valores = [e[0] for e in addon._ENTRADAS_KEYMAP]
        self.assertIn('CLICK', valores)

    def test_varios_itens_da_selecao_e_mesmo_valor_para_todos(self):
        primeiro, segundo = self.dois_modulos()
        itens = addon._itens_da_selecao(bpy.context)
        self.assertEqual([i[0] for i in itens], [primeiro, segundo]
                         if itens[0][0] == primeiro else [segundo, primeiro])
        self.assertEqual(len(itens), 2)
        self.assertEqual(addon._modo_chapa(bpy.context, primeiro), 'GRUPO')
        projetar = lambda p: Vector((300+p.x*500+p.y*150, 200+p.z*500+p.y*90))
        alvos = []
        caixas = []
        for objeto, modo, chapas in itens:
            geometria = addon._geometria_do_item(objeto, modo, chapas)
            linha = next(l for l in geometria['linhas'] if l['eixo'] == 0)
            a, b = linha['pontos']
            alvo = addon._acertar_linhas_hud(geometria, projetar(a + (b-a)*0.2),
                                             projetar, cantos=False)
            self.assertEqual(alvo['lado'], 'min')
            alvos.append(alvo)
            caixas.append(list(addon._caixa_de(chapas)[0]))
        self.assertNotEqual(addon._chave_do_alvo(alvos[0]),
                            addon._chave_do_alvo(alvos[1]))
        for alvo in alvos:
            addon._aplicar_valor_hud(bpy.context, alvo, 900.0)
        for (objeto, _m, chapas), lo_antes in zip(itens, caixas):
            self.assertAlmostEqual(objeto.conj_largura_mm, 900.0, places=3)
            lo, hi = addon._caixa_de(chapas)
            self.assertAlmostEqual(lo[0], lo_antes[0], places=5)

    def test_desenho_da_edicao_multipla_esconde_o_ja_escolhido(self):
        primeiro, segundo = self.dois_modulos()
        itens = addon._itens_da_selecao(bpy.context)
        geometria = addon._geometria_do_item(*itens[0])
        escolhido = dict(next(l for l in geometria['linhas'] if l['eixo'] == 0),
                         lado='min')
        regiao = SimpleNamespace(as_pointer=lambda: 77)
        contexto = SimpleNamespace(region=regiao, object=bpy.context.object,
                                   selected_objects=bpy.context.selected_objects)
        addon._edicao_hud[0] = {'regiao': 77, 'alvo': escolhido,
                                'fase': 'coletar', 'itens': [escolhido],
                                'todos': itens, 'hover': None, 'botoes': []}
        try:
            desenhos = addon._desenhos_hud(contexto)
            self.assertEqual(len(desenhos), 2)
            ja, outro = desenhos
            # o escolhido so' mostra a medida escolhida (as 4 arestas do eixo)
            self.assertEqual(len(ja[0]['linhas']), 4)
            self.assertEqual(ja[1], escolhido)
            self.assertGreater(len(outro[0]['linhas']), 4)
            self.assertIsNone(outro[1])
            # o que ainda precisa de seta e' o que pisca
            self.assertFalse(ja[0].get('pendente'))
            self.assertTrue(outro[0].get('pendente'))
        finally:
            addon._edicao_hud[0] = None

    def test_sem_pergunta_editar_como_e_os_pendentes_piscam(self):
        # Pedido do usuario: a SELECAO diz o que se edita; o pop-up
        # "Editar como? Individual | Grupo" saiu
        for nome in ('_botoes_popup_hud', '_botao_sob_mouse',
                     '_desenhar_popup_hud'):
            self.assertFalse(hasattr(addon, nome), nome)
        fonte = inspect.getsource(addon.OBJECT_OT_arrastar_hud)
        self.assertNotIn("'pergunta'", fonte)    # a fase do pop-up
        self.assertNotIn("'mais'", fonte)
        # piscada: duas, curtas, e apaga
        inicio = addon._piscada_hud[0]
        try:
            addon._piscada_hud[0] = 100.0
            d = addon.DURACAO_PISCADA_HUD
            self.assertEqual(addon._brilho_piscada(100.0), 0.0)
            self.assertAlmostEqual(addon._brilho_piscada(100.0 + d / 4), 1.0)
            self.assertAlmostEqual(addon._brilho_piscada(100.0 + d / 2), 0.0,
                                   places=6)
            self.assertAlmostEqual(addon._brilho_piscada(100.0 + 3 * d / 4), 1.0)
            self.assertEqual(addon._brilho_piscada(100.0 + d + 0.01), 0.0)
            self.assertLessEqual(d, 1.5)
        finally:
            addon._piscada_hud[0] = inicio

    def test_hud_some_durante_mover_girar_escalar(self):
        modulo = self.modulo()
        contexto = SimpleNamespace(
            mode='OBJECT', area=SimpleNamespace(type='VIEW_3D'),
            region=SimpleNamespace(type='WINDOW'), region_data=object())
        addon._hover_hud[1] = {'tipo': 'medida'}
        original = addon._transformando
        addon._transformando = lambda: True
        try:
            self.assertFalse(addon._contexto_hud(contexto))
            self.assertFalse(addon._hover_hud)
        finally:
            addon._transformando = original
        self.assertFalse(addon._transformando())   # nada rodando aqui
        # a seta sai da geometria atual, nao dos pontos do hover
        geometria = addon._geometria_hud(bpy.context)
        self.assertTrue(all('cantos' in l for l in geometria['linhas']
                            if l['tipo'] == 'medida'))
        self.assertEqual(geometria['objeto'], modulo)

    def test_contorno_nativo_some_no_modulo_e_volta_como_estava(self):
        desligados = addon._contornos_desligados
        usuario = addon._contornos_do_usuario
        self.addCleanup(desligados.clear)
        self.addCleanup(usuario.clear)
        novo, a, b = addon._novo_contorno, frozenset({'A'}), frozenset({'B'})
        # ligado: desliga na edicao e religa ao terminar
        self.assertIs(novo(1, True, a), False)
        self.assertIsNone(novo(1, False, a))
        self.assertIsNone(novo(1, False, b))       # outro modulo: segue
        self.assertIs(novo(1, False, frozenset()), True)
        self.assertIsNone(novo(1, True, frozenset()))
        # quem trabalha sem contorno: nada muda, nem ao terminar
        self.assertIsNone(novo(2, False, a))
        self.assertIsNone(novo(2, True, a))        # religou na mao: fica
        self.assertIsNone(novo(2, True, frozenset()))
        # religado na mao durante a edicao: respeitado ate' trocar
        self.assertIs(novo(3, True, a), False)
        self.assertIsNone(novo(3, True, a))
        self.assertIsNone(novo(3, True, a))
        self.assertIsNone(novo(3, True, frozenset()))
        # os ganchos de verdade tambem rodam aqui: so' as falsas contam
        self.assertFalse({1, 2, 3} & (desligados | set(usuario)))
        # so' modulo/porta escondem; chapa solta continua com o contorno
        modulo = self.modulo()
        camada = bpy.context.view_layer
        for o in camada.objects:
            o.select_set(False)
        self.assertFalse(addon._grupos_selecionados(camada))
        for o in addon.familia_de(modulo):
            o.select_set(True)
        self.assertEqual(addon._grupos_selecionados(camada),
                         frozenset({modulo.name}))
        espacos = [e for j in bpy.context.window_manager.windows
                   for e in addon._viewports_da_janela(j)]
        if not espacos:
            return
        overlay = espacos[0].overlay
        antes = overlay.show_outline_selected
        self.addCleanup(setattr, overlay, 'show_outline_selected', antes)
        for inicial in (True, False):
            desligados.clear()
            usuario.clear()
            overlay.show_outline_selected = inicial
            addon.sincronizar_contornos()
            self.assertFalse(overlay.show_outline_selected)
            addon._devolver_contornos()          # salvar: volta como era
            self.assertEqual(overlay.show_outline_selected, inicial)
            addon._retomar_contornos()
            self.assertFalse(overlay.show_outline_selected)
            for o in camada.objects:
                o.select_set(False)
            addon.sincronizar_contornos()
            self.assertEqual(overlay.show_outline_selected, inicial)
            for o in addon.familia_de(modulo):
                o.select_set(True)

    def test_letras_somem_de_longe_e_seta_tem_tamanho_fixo(self):
        self.modulo()
        geometria = addon._geometria_hud(bpy.context)
        original = addon._projetar_hud
        self.addCleanup(setattr, addon, '_projetar_hud', original)
        contexto = SimpleNamespace(preferences=bpy.context.preferences)

        def vista(pixels_por_metro):
            addon._projetar_hud = lambda _c, p: Vector(
                (p.x * pixels_por_metro + p.y * 0.3 * pixels_por_metro,
                 p.z * pixels_por_metro + p.y * 0.2 * pixels_por_metro))

        vista(500)          # perto: o modulo ocupa centenas de pixels
        self.assertEqual({r[0] for r in addon._rotulos_hud(
            contexto, geometria, None)}, {'L', 'A', 'P'})
        vista(40)           # longe: poucos pixels, as letras empilhavam
        self.assertLess(addon._tamanho_na_tela(contexto, geometria),
                        addon.FATOR_ROTULO_HUD * addon._opcao('hud_tamanho_rotulo'))
        self.assertEqual(addon._rotulos_hud(contexto, geometria, None), [])
        alvo = next(l for l in geometria['linhas'] if l.get('letra') == 'A')
        self.assertEqual([r[0] for r in addon._rotulos_hud(
            contexto, geometria, alvo)], ['A'])      # a acesa fica
        # O tamanho de hoje e' o TETO; aresta mais curta que a seta
        # (a E de 18 mm, print do usuario) leva a seta so' ate' a ponta
        # dela -- inteira: ponto e haste nunca passam da aresta.
        cheia = addon.COMPRIMENTO_SETA_HUD
        for comprimento in (6, 10, 40, cheia, 800):
            pontos = addon._triangulos_seta_hud(
                Vector((0, 0)), Vector((comprimento, 0)), 1.0)
            esperado = min(cheia, comprimento)
            self.assertAlmostEqual(max(p.x for p in pontos), esperado,
                                   msg=comprimento)
            self.assertGreaterEqual(min(p.x for p in pontos), -esperado)
        # no tamanho cheio a seta e' a de antes (ponta 12, haste 2.5)
        pontos = addon._triangulos_seta_hud(Vector((0, 0)), Vector((800, 0)),
                                            1.0)
        self.assertAlmostEqual(max(p.y for p in pontos), addon.ASA_SETA_HUD)

    def test_letras_ficam_fora_da_peca_e_nao_se_encostam(self):
        modulo = self.modulo()
        chapa = addon._chapas_do_conjunto(modulo)[0]
        original = addon._projetar_hud
        self.addCleanup(setattr, addon, '_projetar_hud', original)
        # vista obliqua de cima, como a da chapa deitada na referencia
        addon._projetar_hud = lambda _c, p: Vector(
            (300 + p.x * 400 - p.y * 250, 200 + p.z * 400 + p.y * 120 + p.x * 60))
        contexto = SimpleNamespace(preferences=bpy.context.preferences)
        tamanho = addon._opcao('hud_tamanho_rotulo')

        def casco(pontos):
            pontos = sorted(set((round(p.x, 4), round(p.y, 4)) for p in pontos))
            def volta(seq):
                h = []
                for p in seq:
                    while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (p[1] - h[-2][1])
                                           - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0])) <= 0:
                        h.pop()
                    h.append(p)
                return h
            return volta(pontos)[:-1] + volta(pontos[::-1])[:-1]

        def dentro(p, h):
            return all((b[0] - a[0]) * (p.y - a[1]) - (b[1] - a[1]) * (p.x - a[0]) > 0
                       for a, b in zip(h, h[1:] + h[:1]))

        for geometria in (addon._geometria_hud(bpy.context),
                          addon._geometria_do_item(chapa, 'INDIVIDUAL', [chapa])):
            rotulos = addon._rotulos_hud(contexto, geometria, None)
            self.assertGreaterEqual(len(rotulos), 3)
            h = casco([addon._projetar_hud(None, c) for c in geometria['cantos']])
            centro = sum((Vector(p) for p in h), Vector((0, 0))) / len(h)
            for letra, ponto, _aceso in rotulos:
                # nem o desenho da letra (meio tamanho para dentro) encosta
                borda = ponto + (centro - ponto).normalized() * tamanho * 0.4
                self.assertFalse(dentro(borda, h), '%s caiu sobre a peca' % letra)
            for i, (_l, a, _x) in enumerate(rotulos):
                for _m, b, _y in rotulos[:i]:
                    self.assertGreaterEqual((a - b).length, tamanho * 1.3 - 1e-6)

    # ------------------------------------------- correntes de adjacencia
    def piso_e_lateral(self, folga_mm=10.0):
        """A cena da 1a print do usuario: piso deitado e lateral em pe' a
        `folga_mm` da ponta dele, com a adjacencia memorizada."""
        piso = addon.nova_chapa('Piso', 600.0, 400.0, 18.0, (0, 0, 9.0),
                                (0, 0, 0), bpy.context)
        lateral = addon.nova_chapa('Lateral', 720.0, 400.0, 18.0,
                                   (300.0 + folga_mm + 9.0, 0, 360.0),
                                   (0, 90.0, 0), bpy.context)
        bpy.context.view_layer.update()
        self.assertGreater(addon.detectar_adjacencia([piso, lateral]), 0)
        return piso, lateral

    def caixote_aberto(self, recuo_mm=250.0):
        """A cena da 3a print: tampo e base encurtados, longe da lateral
        direita -- 4 pontas separadas (tampo e base, frente e tras)."""
        modulo = self.modulo()
        chapas = addon._chapas_do_conjunto(modulo)
        ordem = sorted(chapas, key=lambda o: o.matrix_world.translation.z)
        base, tampo = ordem[0], ordem[-1]
        for chapa in (base, tampo):
            addon._redimensionar_chapa_ancorada(
                chapa, 0, chapa.chapa_largura_mm - recuo_mm, 'min')
        bpy.context.view_layer.update()
        direita = max((c for c in chapas if c not in (base, tampo)),
                      key=lambda o: o.matrix_world.translation.x)
        return modulo, base, tampo, direita

    @staticmethod
    def vista_de_frente():
        """Matriz de vista olhando de -Y para +Y: no espaco da vista a
        camera olha para -Z, entao a frente (-Y) tem o MAIOR z."""
        return Matrix.Rotation(math.radians(-90), 4, 'X')

    def afastar(self, peca, metros, eixo=0):
        peca.location[eixo] += metros
        bpy.context.view_layer.update()

    def test_corrente_liga_os_dois_vertices_da_junta(self):
        # Soldados com 10 mm de folga: ESSA e' a origem da solda. A lateral
        # anda mais 10 mm -> desvio de 10 mm, a corrente aparece
        piso, lateral = self.piso_e_lateral(10.0)
        self.assertEqual(addon._ligacoes_adjacencia([piso, lateral]), [])
        self.afastar(lateral, 0.010)
        ligacoes = addon._ligacoes_adjacencia([piso, lateral])
        self.assertEqual(len(ligacoes), 1)
        ligacao = ligacoes[0]
        self.assertEqual((ligacao['a'], ligacao['b']), (piso, lateral))
        self.assertAlmostEqual(ligacao['desvio'], 0.010, places=5)
        # os 2 vertices associados: os de BAIXO da ponta do piso, frente
        # e tras, cada um com o canto mais perto da lateral (20 mm)
        self.assertEqual(len(ligacao['pares']), 2)
        for p, q, _assinatura in ligacao['pares']:
            self.assertAlmostEqual(p.x, 0.300, places=5)
            self.assertAlmostEqual(p.z, 0.0, places=5)
            self.assertAlmostEqual((q - p).length, 0.020, places=5)
        self.assertEqual({round(p.y, 3) for p, _q, _s in ligacao['pares']},
                         {-0.2, 0.2})
        # vale para qualquer das duas pecas como item da HUD
        self.assertEqual(len(addon._ligacoes_adjacencia([lateral])), 1)

    def test_corrente_so_aparece_com_desvio_maior_que_5mm(self):
        # Pedido do usuario: o que conta e' o DESVIO da origem da solda;
        # na viewport a corrente so' aparece acima de 5 mm, mas o botao
        # da gaveta ja' acende com qualquer desvio
        piso, lateral = self.piso_e_lateral(0.0)
        self.assertAlmostEqual(addon.LIMIAR_CORRENTE_VIEWPORT, 0.005)
        self.afastar(lateral, 0.003)
        self.assertEqual(addon._ligacoes_adjacencia([piso, lateral]), [])
        self.assertEqual(len(addon._pontas_fora_do_lugar([piso, lateral])), 1)
        self.afastar(lateral, 0.003)          # 6 mm
        self.assertEqual(len(addon._ligacoes_adjacencia([piso, lateral])), 1)
        # sem teto: longe continua corrente
        self.afastar(lateral, 0.3)
        self.assertEqual(len(addon._ligacoes_adjacencia([piso, lateral])), 1)

    def test_alt_mostra_todas_as_quinas_soldadas_com_corrente_e_regua(self):
        # Pedido do usuario: acabou o "so' a mais perto da camera" -- o
        # Alt mostra TODAS as quinas soldadas fora da origem, cada uma com
        # a corrente e, a direita, a regua
        modulo, base, tampo, direita = self.caixote_aberto()
        self.selecionar(modulo, *addon._chapas_do_conjunto(modulo), ativo=modulo)
        originais = {n: getattr(addon, n) for n in (
            '_correntes_visiveis', '_contexto_hud', '_eh_area_gaveta',
            '_projetar_hud')}
        for n, f in originais.items():
            self.addCleanup(setattr, addon, n, f)
        addon._correntes_visiveis = lambda: True
        addon._contexto_hud = lambda _c: True
        addon._eh_area_gaveta = lambda _c: False
        addon._projetar_hud = lambda _c, p: Vector((p.x * 1000, p.z * 1000))
        contexto = _ContextoRegiao()
        contexto.region_data = object()
        correntes = addon._correntes_hud(contexto)
        self.assertEqual(len(correntes), 4)          # tampo e base x 2 quinas
        self.assertEqual({c['a'] for c in correntes}, {base, tampo})
        # a regua move a que se afastou... aqui quem encolheu foram tampo e
        # base; a lateral tem as duas soldas fora, entao e' ela
        self.assertTrue(all(c['movel'] == direita for c in correntes))
        botoes = addon._botoes_da_corrente(contexto, correntes[0])
        self.assertLess(botoes['corrente'].x, botoes['regua'].x)
        self.assertEqual(addon._botao_corrente_sob_mouse(
            contexto, botoes['regua'])[1], 'regua')
        self.assertEqual(addon._botao_corrente_sob_mouse(
            contexto, botoes['corrente'])[1], 'corrente')
        self.assertFalse(hasattr(addon, '_corrente_da_vista'))

    def prateleira_solta(self, x_mm=800.0, z_mm=300.0):
        """Prateleira fora do modulo, longe de tudo (nada ao alcance)."""
        prateleira = addon.nova_chapa('Prateleira', 400.0, 300.0, 18.0,
                                      (x_mm, 0, z_mm), (0, 0, 0), bpy.context)
        bpy.context.view_layer.update()      # matrix_world defasado
        return prateleira

    def test_desagregar_solta_todas_as_quinas_de_uma_vez(self):
        # Regra nova: a corrente clicada vale pelo OBJETO inteiro
        modulo, base, tampo, direita = self.caixote_aberto()
        corrente = addon._ligacoes_adjacencia(
            addon._chapas_do_conjunto(modulo))[0]
        peca = corrente['a']
        self.assertIn(peca, (base, tampo))
        mundo = peca.matrix_world.copy()
        self.assertTrue(addon.agregado(peca))
        self.assertEqual(bpy.ops.object.cabinet_desassociar(chapa=peca.name),
                         {'FINISHED'})
        # nenhuma quina dela segue ligada, em nenhum sentido
        self.assertFalse(addon.agregado(peca))
        self.assertEqual(addon._ligados_a(peca), set())
        # saiu do modulo sem sair do lugar; as outras seguem la'
        self.assertIsNone(peca.parent)
        for a, b in zip(peca.matrix_world, mundo):
            self.assertLess((a - b).length, 1e-6)
        outra = tampo if peca is base else base
        self.assertEqual(outra.parent, modulo)
        self.assertTrue(addon.agregado(outra))
        # de novo: nada a fazer
        self.assertEqual(bpy.ops.object.cabinet_desassociar(chapa=peca.name),
                         {'CANCELLED'})

    def selecionar(self, *objs, ativo=None):
        bpy.ops.object.select_all(action='DESELECT')
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = ativo

    def test_resetar_com_a_chapa_ativa_move_a_chapa(self):
        # Print do usuario: a lateral afastada do nicho e SELECIONADA
        # sozinha -> ela volta a origem da solda; o resto nao se mexe
        modulo = self.modulo()
        chapas = addon._chapas_do_conjunto(modulo)
        direita = max(chapas, key=lambda o: o.matrix_world.translation.x)
        antes = direita.matrix_world.copy()
        fixos = {o.name: o.matrix_world.copy() for o in chapas if o != direita}
        self.selecionar(direita, ativo=direita)
        self.assertIsNone(addon._estado_resetar(bpy.context))   # na origem
        self.afastar(direita, 0.2)
        self.assertIs(addon._estado_resetar(bpy.context), True)  # azul
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(),
                         {'FINISHED'})
        for a, b in zip(direita.matrix_world, antes):
            self.assertLess((a - b).length, 1e-5)
        for o in chapas:
            if o != direita:
                for a, b in zip(o.matrix_world, fixos[o.name]):
                    self.assertLess((a - b).length, 1e-6, o.name)
        self.assertIsNone(addon._estado_resetar(bpy.context))

    def test_resetar_que_muda_a_medida_pergunta_antes(self):
        # Caso extremo do usuario: o modulo mudou e a chapa so' volta as
        # soldas mudando de medida -> pergunta; "Sim" estica, "Nao" nada
        modulo, base, tampo, direita = self.caixote_aberto()
        # o tampo vai a solda da esquerda (onde ja' esta') e da direita
        # (250 mm adiante): so' esticando
        self.selecionar(tampo, ativo=tampo)
        largura = tampo.chapa_largura_mm
        plano = addon._plano_reset_chapa(tampo)
        self.assertTrue(plano['muda_medida'])
        self.assertIn('Mover mesmo assim', addon.PERGUNTA_RESET)
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(),
                         {'CANCELLED'})
        self.assertEqual(addon._pergunta_reset[0], tampo.name)
        self.assertAlmostEqual(tampo.chapa_largura_mm, largura)
        # "Nao"
        bpy.ops.object.cabinet_resetar_distancia(cancelar=True)
        self.assertEqual(addon._pergunta_reset[0], '')
        self.assertAlmostEqual(tampo.chapa_largura_mm, largura)
        # "Sim, mover"
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(
            chapa=tampo.name, forcar=True), {'FINISHED'})
        self.assertAlmostEqual(tampo.chapa_largura_mm, largura + 250.0, places=2)
        self.assertEqual(addon._pontas_fora_do_lugar([tampo]), [])

    def test_resetar_com_o_modulo_ativo_o_modulo_se_adapta(self):
        # Modulo ativo: o GRUPO se adapta a chapa afastada -- as pontas
        # soldadas esticam ate' ela e o modulo cresce; a chapa fica
        modulo = self.modulo()
        chapas = addon._chapas_do_conjunto(modulo)
        direita = max(chapas, key=lambda o: o.matrix_world.translation.x)
        largura = modulo.conj_largura_mm
        self.afastar(direita, 0.2)
        lateral = direita.matrix_world.copy()
        self.selecionar(modulo, *chapas, ativo=modulo)
        self.assertIs(addon._estado_resetar(bpy.context), True)
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(),
                         {'FINISHED'})
        for a, b in zip(direita.matrix_world, lateral):
            self.assertLess((a - b).length, 1e-5)
        self.assertEqual(addon._pontas_fora_do_lugar(chapas), [])
        self.assertAlmostEqual(modulo.conj_largura_mm, largura + 200.0, places=1)
        # a regua de uma linha (viewport) vale pela peca da linha
        self.afastar(direita, 0.05)
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(
            chapa=direita.name), {'FINISHED'})
        self.assertEqual(addon._pontas_fora_do_lugar(chapas), [])

    def solda_do_tampo(self):
        """Nicho agrupado: (modulo, tampo, lateral direita, ponta do tampo
        soldada na lateral)."""
        modulo = self.modulo()
        chapas = addon._chapas_do_conjunto(modulo)
        tampo = max(chapas, key=lambda o: o.matrix_world.translation.z)
        direita = max((c for c in chapas if c is not tampo),
                      key=lambda o: o.matrix_world.translation.x)
        ponta = next(p for p in addon.PONTAS
                     if addon._vizinho_da_ponta(tampo, p) == direita)
        return modulo, tampo, direita, ponta

    def vertice_do_outro_lado(self, N, assinatura, sentido, espessura):
        """O vertice de N do outro lado da espessura dele."""
        alvo = addon._vertice_da_assinatura(N, assinatura) + sentido * espessura
        return min((a + b + c for a in '+-' for b in '+-' for c in '+-'),
                   key=lambda s: (addon._vertice_da_assinatura(N, s) - alvo).length)

    def test_ancoras_de_fabrica_trocar_e_apagar(self):
        modulo, tampo, direita, ponta = self.solda_do_tampo()
        self.assertIsNone(addon._ancoras_gravadas(tampo, ponta))
        ancoras = addon._ancoras_da_ligacao(tampo, ponta, direita)
        self.assertEqual(len(ancoras), 2)
        for sc, sn in ancoras:                    # de fabrica: encostados
            self.assertLess((addon._vertice_da_assinatura(tampo, sc)
                             - addon._vertice_da_assinatura(direita, sn)).length,
                            1e-5)
        # arrastar a bolinha do lado do vizinho ('b') para outro vertice
        _f, u, _e = addon._folga_com_sinal(tampo, ponta, direita)
        sentido = u if ponta.endswith('pos') else -u
        fora = self.vertice_do_outro_lado(direita, ancoras[0][1], sentido,
                                          direita.chapa_espessura_mm / 1000.0)
        op = SimpleNamespace(chapa=tampo.name, ponta=ponta, indice=0, lado='b',
                             report=lambda *a: None)
        self.assertEqual(addon.OBJECT_OT_arrastar_ancora._gravar(op, fora),
                         {'FINISHED'})
        self.assertEqual(addon._ancoras_gravadas(tampo, ponta),
                         [(ancoras[0][0], fora), ancoras[1]])
        # mesma ancora de novo: nada a gravar
        self.assertEqual(addon.OBJECT_OT_arrastar_ancora._gravar(op, fora),
                         {'CANCELLED'})
        # so' troca a ancora: a geometria nao mexeu, mas a solda saiu da
        # origem (a regua acende)
        self.assertTrue(addon._pontas_fora_do_lugar([tampo]))
        # soldar de novo (ou desassociar) volta as ancoras de fabrica
        addon.detectar_adjacencia(addon._chapas_do_conjunto(modulo))
        self.assertIsNone(addon._ancoras_gravadas(tampo, ponta))
        addon._gravar_ancoras(tampo, ponta, [(ancoras[0][0], fora), ancoras[1]])
        addon.desassociar(tampo, direita)
        self.assertNotIn('adj_%s_ancoras' % ponta, tampo)

    def test_regua_leva_aos_vertices_ancorados_mesmo_torta(self):
        # Print 1 do usuario: uma ancora na quina de FORA da lateral e a
        # outra na de dentro -> a ponta do tampo fica torta, na diagonal,
        # com a espessura intacta; a lateral nao se mexe
        modulo, tampo, direita, ponta = self.solda_do_tampo()
        ancoras = addon._ancoras_da_ligacao(tampo, ponta, direita)
        _f, u, _e = addon._folga_com_sinal(tampo, ponta, direita)
        sentido = u if ponta.endswith('pos') else -u
        fora = self.vertice_do_outro_lado(direita, ancoras[0][1], sentido,
                                          direita.chapa_espessura_mm / 1000.0)
        novas = [(ancoras[0][0], fora), ancoras[1]]
        addon._gravar_ancoras(tampo, ponta, novas)
        lateral = direita.matrix_world.copy()
        sc0, sc1 = ancoras[0][0], ancoras[1][0]
        parceiro = sc0[:2] + ('-' if sc0[2] == '+' else '+')
        espessura = (addon._vertice_da_assinatura(tampo, sc0)
                     - addon._vertice_da_assinatura(tampo, parceiro)).length
        self.selecionar(modulo, *addon._chapas_do_conjunto(modulo), ativo=modulo)
        self.assertIs(addon._estado_resetar(bpy.context), True)
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(),
                         {'FINISHED'})
        for sc, sn in novas:
            self.assertLess((addon._vertice_da_assinatura(tampo, sc)
                             - addon._vertice_da_assinatura(direita, sn)).length,
                            1e-4, sc)
        # torta: os dois cantos da ponta nao estao mais na mesma reta
        a = addon._vertice_da_assinatura(tampo, sc0)
        b = addon._vertice_da_assinatura(tampo, sc1)
        self.assertGreater(abs((a - b).dot(sentido)), 0.005)
        # o outro lado da espessura veio junto
        self.assertAlmostEqual((a - addon._vertice_da_assinatura(
            tampo, parceiro)).length, espessura, places=5)
        for x, y in zip(direita.matrix_world, lateral):
            self.assertLess((x - y).length, 1e-6)
        self.assertEqual(addon._pontas_fora_do_lugar([tampo]), [])

    def ancora_na_quina_de_fora(self):
        """Solda do tampo com o par 0 ancorado na quina de FORA da lateral
        (print do usuario). Devolve (modulo, tampo, direita, ponta, novas,
        sentido)."""
        modulo, tampo, direita, ponta = self.solda_do_tampo()
        ancoras = addon._ancoras_da_ligacao(tampo, ponta, direita)
        _f, u, _e = addon._folga_com_sinal(tampo, ponta, direita)
        sentido = u if ponta.endswith('pos') else -u
        fora = self.vertice_do_outro_lado(direita, ancoras[0][1], sentido,
                                          direita.chapa_espessura_mm / 1000.0)
        novas = [(ancoras[0][0], fora), ancoras[1]]
        addon._gravar_ancoras(tampo, ponta, novas)
        return modulo, tampo, direita, ponta, novas, sentido

    def test_lateral_ativa_e_ela_que_entorta_ate_as_ancoras(self):
        # Print do usuario: a LATERAL selecionada nao se deformava -- so'
        # andava ate' a media e as ancoras ficavam sem encostar
        modulo, tampo, direita, ponta, novas, sentido = self.ancora_na_quina_de_fora()
        tampo_antes = [tuple(tampo.matrix_world @ v.co) for v in tampo.data.vertices]
        sn0 = novas[0][1]
        parceiro = sn0[:2] + ('-' if sn0[2] == '+' else '+')
        espessura = (addon._vertice_da_assinatura(direita, sn0)
                     - addon._vertice_da_assinatura(direita, parceiro)).length
        self.selecionar(direita, ativo=direita)
        self.assertIs(addon._estado_resetar(bpy.context), True)
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(),
                         {'FINISHED'})
        for sc, sn in novas:
            self.assertLess((addon._vertice_da_assinatura(tampo, sc)
                             - addon._vertice_da_assinatura(direita, sn)).length,
                            1e-4, sn)
        # a lateral (a ativa) entortou, com a espessura intacta; o tampo nao
        self.assertAlmostEqual((addon._vertice_da_assinatura(direita, sn0)
                                - addon._vertice_da_assinatura(direita, parceiro)
                                ).length, espessura, places=5)
        tampo_depois = [tuple(tampo.matrix_world @ v.co) for v in tampo.data.vertices]
        for x, y in zip(tampo_antes, tampo_depois):
            self.assertLess((Vector(x) - Vector(y)).length, 1e-6)
        self.assertEqual(addon._pontas_fora_do_lugar([direita]), [])

    def test_lateral_afastada_com_ancora_volta_e_entorta(self):
        # A cena das prints: lateral 200 mm longe, uma ancora na quina de
        # fora. Lateral ativa: volta inteira pelas soldas normais (a base)
        # e entorta so' o que a ancora pede; tudo encostado, nada aparece.
        modulo, tampo, direita, ponta, novas, sentido = self.ancora_na_quina_de_fora()
        self.afastar(direita, 0.2)
        self.selecionar(direita, ativo=direita)
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(),
                         {'FINISHED'})
        for sc, sn in novas:
            self.assertLess((addon._vertice_da_assinatura(tampo, sc)
                             - addon._vertice_da_assinatura(direita, sn)).length,
                            1e-4, sn)
        self.assertEqual(addon._pontas_fora_do_lugar(
            addon._chapas_do_conjunto(modulo)), [])

    def test_ancora_em_vertice_de_chanfro(self):
        # Print do usuario (caso extremo): lateral com um chanfro curvo.
        # A bolinha tem que poder cair em QUALQUER vertice da malha, nao
        # so' nos 8 cantos da caixa; a regua leva a ponta ate' ele.
        modulo, tampo, direita, ponta = self.solda_do_tampo()
        malha = bmesh.new()
        malha.from_mesh(direita.data)
        malha.edges.ensure_lookup_table()
        topo = max(malha.edges, key=lambda e: sum(v.co.y for v in e.verts))
        bmesh.ops.bevel(malha, geom=[topo], offset=0.05, segments=5,
                        affect='EDGES')
        malha.to_mesh(direita.data)
        malha.free()
        direita.data.update()
        bpy.context.view_layer.update()
        candidatos = addon._ancoras_da_malha(direita)
        self.assertGreater(len(candidatos), 8)
        self.assertTrue(all(a.startswith('v') for a, _p in candidatos))
        ancoras = addon._ancoras_da_ligacao(tampo, ponta, direita)
        # um vertice do MEIO do chanfro (nao e' canto da caixa)
        cantos = [addon._vertice_da_assinatura(direita, a + b + c)
                  for a in '+-' for b in '+-' for c in '+-']
        alvo, ponto = max(candidatos, key=lambda c: min(
            (c[1] - k).length for k in cantos))
        op = SimpleNamespace(chapa=tampo.name, ponta=ponta, indice=0, lado='b',
                             report=lambda *a: None)
        self.assertEqual(addon.OBJECT_OT_arrastar_ancora._gravar(op, alvo),
                         {'FINISHED'})
        self.assertLess((addon._vertice_da_assinatura(direita, alvo) - ponto)
                        .length, 1e-6)
        # o outro lado da espessura de um vertice qualquer existe e e' outro
        parceiro = addon._parceiro_espessura(direita, alvo)
        self.assertNotEqual(parceiro, alvo)
        self.selecionar(tampo, ativo=tampo)
        bpy.ops.object.cabinet_resetar_distancia(forcar=True)
        self.assertLess((addon._vertice_da_assinatura(tampo, ancoras[0][0])
                         - addon._vertice_da_assinatura(direita, alvo)).length,
                        1e-4)

    def test_par_que_ja_encostou_some_da_viewport(self):
        # Print do usuario: o par que ja' chegou continuava desenhado em
        # cima do vertice (linha, bolinhas e botoes sobrepostos)
        modulo, tampo, direita, ponta, novas, sentido = self.ancora_na_quina_de_fora()
        ligacao = next(l for l in addon._ligacoes_adjacencia([tampo])
                       if l['a'] == tampo and l['b'] == direita)
        self.assertEqual(ligacao['soltos'], [True, False])
        self.selecionar(tampo, ativo=tampo)
        originais = {n: getattr(addon, n) for n in (
            '_correntes_visiveis', '_contexto_hud', '_eh_area_gaveta',
            '_projetar_hud')}
        for n, f in originais.items():
            self.addCleanup(setattr, addon, n, f)
        addon._correntes_visiveis = lambda: True
        addon._contexto_hud = lambda _c: True
        addon._eh_area_gaveta = lambda _c: False
        addon._projetar_hud = lambda _c, p: Vector((p.x * 1000, p.z * 1000))
        contexto = _ContextoRegiao()
        contexto.region_data = object()
        correntes = [c for c in addon._correntes_hud(contexto)
                     if c['a'] == tampo and c['b'] == direita]
        self.assertEqual([c['indice'] for c in correntes], [0])

    def test_estado_do_botao_corrente(self):
        piso, lateral = self.piso_e_lateral(10.0)
        self.selecionar(piso, ativo=piso)
        self.assertIs(addon._estado_corrente_objeto(bpy.context), True)
        # as duas pecas ligadas = o grupo: azul, o clique desagrega todas
        self.selecionar(piso, lateral, ativo=lateral)
        self.assertIs(addon._estado_corrente_objeto(bpy.context), True)
        self.assertEqual(addon._acao_corrente(bpy.context)[0], 'grupo')
        addon.desagregar(piso)
        self.selecionar(piso, ativo=piso)
        self.assertIs(addon._estado_corrente_objeto(bpy.context), False)
        # o botao da gaveta leva o estado (azul = agregado)
        widgets = addon._widgets_gaveta(bpy.context, 478, 900)
        botao = next(v for v in widgets if v[5] and v[5][:2] == (
            'operador', addon.OP_CORRENTE_OBJETO))
        self.assertEqual(botao[5][2], False)
        self.assertEqual(addon._icone_acao_gaveta(botao[5]), 'LINKED')

    def test_uma_peca_solta_vai_direto_ao_selecionar_vertice(self):
        piso, lateral = self.piso_e_lateral(3.0)
        addon.desagregar(piso)
        # mesmo com vizinha a 3 mm: sozinha, nada de conectar por distancia
        self.selecionar(piso, ativo=piso)
        self.assertEqual(addon._acao_corrente(bpy.context),
                         ('vertices', piso, []))

    def test_alvos_primeiro_e_a_peca_de_fora_por_ultimo(self):
        # Pedido do usuario: seleciona o(s) alvo(s) e, por ULTIMO (o ativo
        # do Blender), a peca de fora. Ate' 5 mm conecta sozinho; so' com
        # os alvos selecionados, nunca com uma vizinha que nao foi.
        piso, lateral = self.piso_e_lateral(3.0)
        addon.desagregar(piso)
        intrusa = addon.nova_chapa('Intrusa', 720.0, 400.0, 18.0,
                                   (-300.0 - 3.0 - 9.0, 0, 360.0),
                                   (0, 90.0, 0), bpy.context)
        bpy.context.view_layer.update()
        self.assertIn(intrusa, addon._vizinhos_por_distancia(piso))
        self.selecionar(lateral, piso, ativo=piso)
        self.assertEqual(addon._acao_corrente(bpy.context),
                         ('conectar', piso, [lateral]))
        self.assertIs(addon._estado_corrente_objeto(bpy.context), False)
        self.assertEqual(bpy.ops.object.cabinet_corrente_objeto(),
                         {'FINISHED'})
        self.assertEqual(addon._vizinho_da_ponta(piso, 'x_pos'), lateral)
        self.assertIsNone(addon._vizinho_da_ponta(piso, 'x_neg'))
        # a 10 mm a automatica falha: selecionar vertice, so' nos alvos
        addon.desagregar(piso)
        lateral.location.x += 0.007
        bpy.context.view_layer.update()
        self.assertEqual(addon._acao_corrente(bpy.context),
                         ('vertices', piso, [lateral]))
        estado = {'origem': piso.name, 'fase': 'destino',
                  'destinos': addon._nomes([lateral])}
        self.assertEqual({o for o, _s, _p in addon._candidatos_conexao(estado)},
                         {lateral})

    def test_modulo_como_ativo_nao_e_puxado_ate_o_alvo(self):
        # quem vai ate' o alvo e' UMA peca; um modulo por ultimo nao vale
        modulo = self.modulo()
        solta = self.prateleira_solta()
        self.selecionar(solta, modulo, *addon._chapas_do_conjunto(modulo),
                        ativo=modulo)
        self.assertIsNone(addon._acao_corrente(bpy.context))
        self.assertIsNone(addon._estado_corrente_objeto(bpy.context))

    def test_desagregar_o_grupo_pergunta_antes(self):
        modulo = self.modulo()
        chapas = addon._chapas_do_conjunto(modulo)
        mundo = {o.name: o.matrix_world.copy() for o in chapas}
        addon._selecionar_chapa_hud(bpy.context, chapas[0])   # clique: modulo
        self.assertEqual(addon._acao_corrente(bpy.context),
                         ('grupo', None, chapas))
        self.assertIn('todos os itens deste grupo',
                      addon.PERGUNTA_DESAGREGAR_GRUPO)
        self.assertEqual(bpy.ops.object.cabinet_corrente_objeto(),
                         {'FINISHED'})
        self.assertEqual(addon._desagregar_pendente[0],
                         sorted(o.name for o in chapas))
        # "Nao": nada muda
        self.assertEqual(bpy.ops.object.cabinet_desagregar_selecao(
            desagregar=False), {'CANCELLED'})
        self.assertIsNone(addon._desagregar_pendente[0])
        self.assertTrue(all(o.parent == modulo for o in chapas))
        # "Sim": todas soltas, no lugar, e o modulo vazio some
        nome_modulo = modulo.name
        bpy.ops.object.cabinet_corrente_objeto()
        self.assertEqual(bpy.ops.object.cabinet_desagregar_selecao(),
                         {'FINISHED'})
        self.assertNotIn(nome_modulo, bpy.data.objects)
        for o in chapas:
            self.assertIsNone(o.parent)
            self.assertFalse(addon.agregado(o), o.name)
            for a, b in zip(o.matrix_world, mundo[o.name]):
                self.assertLess((a - b).length, 1e-6, o.name)

    def test_pergunta_vai_para_a_gaveta_ou_para_o_popup(self):
        # Botao da gaveta (_na_gaveta) -> caixa na gaveta; viewport -> pop-up.
        # A resposta e' a mesma nos dois: cabinet_responder_pergunta.
        modulo = self.modulo()
        chapas = addon._chapas_do_conjunto(modulo)
        addon._selecionar_chapa_hud(bpy.context, chapas[0])
        try:
            addon._na_gaveta[0] = True
            bpy.ops.object.cabinet_corrente_objeto()
        finally:
            addon._na_gaveta[0] = False
        self.assertTrue(addon._pergunta_atual[0]['na_gaveta'])
        bpy.ops.object.cabinet_corrente_objeto()            # sem gaveta
        self.assertFalse(addon._pergunta_atual[0]['na_gaveta'])
        # "Nao": nada muda e a pergunta some
        self.assertEqual(bpy.ops.object.cabinet_responder_pergunta(opcao=1),
                         {'CANCELLED'})
        self.assertIsNone(addon._pergunta_atual[0])
        self.assertTrue(all(o.parent == modulo for o in chapas))
        # "Sim": desagrega
        bpy.ops.object.cabinet_corrente_objeto()
        self.assertEqual(bpy.ops.object.cabinet_responder_pergunta(opcao=0),
                         {'FINISHED'})
        self.assertTrue(all(o.parent is None for o in chapas))
        # sem pergunta pendente: nada a responder
        self.assertEqual(bpy.ops.object.cabinet_responder_pergunta(opcao=0),
                         {'CANCELLED'})

    def test_desagregar_um_objeto_do_grupo_pergunta_antes(self):
        modulo = self.modulo()
        chapas = addon._chapas_do_conjunto(modulo)
        peca = chapas[0]
        addon._selecionar_chapa_hud(bpy.context, peca, individual=True)
        self.assertEqual(addon._acao_corrente(bpy.context),
                         ('desagregar', peca, [peca]))
        self.assertIn('desagregar esse objeto do grupo',
                      addon.PERGUNTA_DESAGREGAR_OBJETO)
        bpy.ops.object.cabinet_corrente_objeto()
        self.assertEqual(addon._desagregar_pendente[0], [peca.name])
        self.assertEqual(bpy.ops.object.cabinet_desagregar_selecao(),
                         {'FINISHED'})
        self.assertIsNone(peca.parent)
        self.assertFalse(addon.agregado(peca))
        self.assertTrue(all(o.parent == modulo for o in chapas[1:]))
        self.assertIn(modulo.name, bpy.data.objects)
        # sem pergunta pendente: nada a fazer
        self.assertEqual(bpy.ops.object.cabinet_desagregar_selecao(),
                         {'CANCELLED'})

    def test_conexao_automatica_so_ate_5mm(self):
        # Pedido do usuario: juntar sozinho so' ate' 5 mm; mais longe ja'
        # e' "selecionar vertice" (nenhum vizinho "ao alcance").
        self.assertAlmostEqual(addon.ALCANCE_CONEXAO_AUTOMATICA, 0.005)
        for folga, alcanca in ((5.0, True), (6.0, False), (20.0, False)):
            for o in list(bpy.data.objects):
                bpy.data.objects.remove(o, do_unlink=True)
            piso, lateral = self.piso_e_lateral(folga)
            addon.desagregar(piso)
            self.assertEqual(addon._vizinhos_por_distancia(piso),
                             {lateral} if alcanca else set(), folga)
            resultado = bpy.ops.object.cabinet_conectar_distancia(
                origem=piso.name)
            self.assertEqual(resultado,
                             {'FINISHED'} if alcanca else {'CANCELLED'}, folga)
            self.assertEqual(addon._vizinho_da_ponta(piso, 'x_pos'),
                             lateral if alcanca else None, folga)
        # o agrupar do modulo (detectar_adjacencia) segue com o alcance dele
        piso, lateral = self.piso_e_lateral(20.0)
        self.assertEqual(addon._vizinho_da_ponta(piso, 'x_pos'), lateral)

    def test_associar_uma_peca_nao_apaga_as_ligacoes_das_outras(self):
        # detectar_adjacencia zera quem recebe; associar_por_distancia nao
        piso, lateral = self.piso_e_lateral(10.0)
        fora = addon.nova_chapa('Fora', 400.0, 400.0, 18.0,
                                (319.0 + 9.0 + 200.0 + 5.0, 0, 300.0),
                                (0, 0, 0), bpy.context)
        bpy.context.view_layer.update()
        addon.associar_por_distancia(fora, [lateral])
        self.assertEqual(addon._vizinho_da_ponta(fora, 'x_neg'), lateral)
        self.assertEqual(addon._vizinho_da_ponta(piso, 'x_pos'), lateral)

    def test_juntar_puxa_a_peca_e_o_alvo_fica_parado(self):
        modulo = self.modulo()
        chapas = addon._chapas_do_conjunto(modulo)
        direita = max(chapas, key=lambda o: o.matrix_world.translation.x)
        fixos = {o.name: o.matrix_world.copy() for o in chapas}
        prateleira = self.prateleira_solta(x_mm=900.0, z_mm=300.0)
        bpy.context.view_layer.update()
        # cantos da ponta ESQUERDA da prateleira (-x) nos cantos de fora
        # da lateral direita, embaixo (frente e tras)
        fora_x = max(p.x for p in addon._cantos(direita))
        alvos_lateral = sorted((p for p in addon._cantos(direita)
                                if abs(p.x - fora_x) < 1e-6 and p.z < 0.01),
                               key=lambda p: p.y)
        cantos = sorted((p for p in addon._cantos(prateleira)
                         if addon._assinatura_canto(prateleira, p)[0] == '-'
                         and addon._assinatura_canto(prateleira, p)[2] == '-'),
                        key=lambda p: p.y)
        direita_prat = max(p.x for p in addon._cantos(prateleira))
        pares = [(addon._assinatura_canto(prateleira, p), direita.name,
                  addon._assinatura_canto(direita, q))
                 for p, q in zip(cantos, alvos_lateral)]
        addon._conexao_pendente[0] = {
            'origem': prateleira.name,
            'alvos': [(s, tuple(addon._canto_da_assinatura(direita, sn)))
                      for s, _n, sn in pares],
            'pecas': [direita.name]}
        self.assertEqual(bpy.ops.object.cabinet_juntar_modulo(juntar=True),
                         {'FINISHED'})
        bpy.context.view_layer.update()
        # a ponta puxada foi ATE' a lateral; a outra ponta ficou
        lo = min(p.x for p in addon._cantos(prateleira))
        self.assertAlmostEqual(lo, fora_x, places=5)
        self.assertAlmostEqual(max(p.x for p in addon._cantos(prateleira)),
                               direita_prat, places=5)
        self.assertAlmostEqual(min(p.z for p in addon._cantos(prateleira)),
                               0.0, places=5)          # desceu ao alvo
        # entrou no modulo, associada; o modulo NAO foi puxado
        self.assertEqual(prateleira.parent, modulo)
        self.assertTrue(addon.agregado(prateleira))
        for o in chapas:
            for a, b in zip(o.matrix_world, fixos[o.name]):
                self.assertLess((a - b).length, 1e-6, o.name)
        self.assertIsNone(addon._conexao_pendente[0])

    def test_nao_juntar_nao_move_nada(self):
        modulo = self.modulo()
        direita = max(addon._chapas_do_conjunto(modulo),
                      key=lambda o: o.matrix_world.translation.x)
        prateleira = self.prateleira_solta(x_mm=900.0)
        antes = prateleira.matrix_world.copy()
        canto = addon._cantos(prateleira)[0]
        addon._conexao_pendente[0] = {
            'origem': prateleira.name,
            'alvos': [(addon._assinatura_canto(prateleira, canto),
                       tuple(addon._cantos(direita)[0]))],
            'pecas': [direita.name]}
        self.assertEqual(bpy.ops.object.cabinet_juntar_modulo(juntar=False),
                         {'FINISHED'})
        self.assertIsNone(prateleira.parent)
        for a, b in zip(prateleira.matrix_world, antes):
            self.assertLess((a - b).length, 1e-9)
        # sem pergunta pendente: nada a fazer
        self.assertEqual(bpy.ops.object.cabinet_juntar_modulo(),
                         {'CANCELLED'})

    def test_tecla_das_opcoes_mostra_as_correntes(self):
        op = addon.OBJECT_OT_tecla_corrente
        ctx = SimpleNamespace(screen=None)
        evento = SimpleNamespace(type='LEFT_ALT')
        original = addon._opcao('tecla_corrente')
        try:
            addon._definir_opcao('tecla_corrente', 'ALT')
            self.assertFalse(addon._correntes_visiveis())
            for tecla, apertou, visivel in (
                    ('LEFT_CTRL', True, False),     # outra tecla: nada
                    ('LEFT_ALT', True, True),
                    ('RIGHT_ALT', False, False)):
                fake = SimpleNamespace(tecla=tecla, apertou=apertou)
                # o evento segue adiante: Alt continua valendo no Blender
                self.assertEqual(op.invoke(fake, ctx, evento),
                                 {'PASS_THROUGH'})
                self.assertEqual(addon._correntes_visiveis(), visivel, tecla)
            addon._definir_opcao('tecla_corrente', 'SEMPRE')
            self.assertTrue(addon._correntes_visiveis())
            self.assertIn('tecla_corrente', addon.SUSPENSOS_OPCOES)
        finally:
            addon._tecla_corrente_segurada[0] = False
            addon._definir_opcao('tecla_corrente', original)

    def test_corrente_entre_modulo_e_peca_de_fora(self):
        modulo = self.modulo()
        chapas = addon._chapas_do_conjunto(modulo)
        lo = min(min(p.x for p in addon._cantos(c)) for c in chapas)
        # A adjacencia liga a PONTA de uma chapa a FACE de outra (duas
        # laterais face com face nao se ligam): prateleira de fora com a
        # ponta a 5 mm da lateral do modulo
        de_fora = addon.nova_chapa('Vizinha', 400.0, 300.0, 18.0,
                                   (lo * 1000.0 - 5.0 - 200.0, 0, 300.0),
                                   (0, 0, 0), bpy.context)
        bpy.context.view_layer.update()
        addon.detectar_adjacencia(chapas + [de_fora])
        self.assertEqual(addon._ligacoes_adjacencia(chapas), [])   # na origem
        self.afastar(de_fora, -0.010)
        ligacoes = addon._ligacoes_adjacencia(chapas)
        self.assertTrue(ligacoes)
        for ligacao in ligacoes:
            self.assertIn(de_fora, (ligacao['a'], ligacao['b']))

    def modos_dos_itens(self):
        return sorted((o.name, modo) for o, modo, _c in
                      addon._itens_da_selecao(bpy.context))

    def test_hud_mostra_todos_os_itens_sem_ordem(self):
        # Pedido do usuario: com dois modulos selecionados o contorno so'
        # aparecia no ultimo. Cada item tem o seu, em QUALQUER ordem:
        # dois grupos, grupo + chapa, chapa + grupo, duas chapas.
        primeiro, segundo = self.dois_modulos()
        a1 = addon._chapas_do_conjunto(primeiro)[0]
        b1 = addon._chapas_do_conjunto(segundo)[0]
        grupo_a = [primeiro, *primeiro.children_recursive]
        grupo_b = [segundo, *segundo.children_recursive]
        casos = (
            (grupo_a + grupo_b, segundo,
             [(primeiro.name, 'GRUPO'), (segundo.name, 'GRUPO')]),
            (grupo_a + [b1], b1,
             [(primeiro.name, 'GRUPO'), (b1.name, 'INDIVIDUAL')]),
            ([a1] + grupo_b, a1,
             [(a1.name, 'INDIVIDUAL'), (segundo.name, 'GRUPO')]),
            ([a1, b1], b1,
             [(a1.name, 'INDIVIDUAL'), (b1.name, 'INDIVIDUAL')]),
            ([a1, addon._chapas_do_conjunto(primeiro)[1]], a1,
             sorted([(a1.name, 'INDIVIDUAL'), (addon._chapas_do_conjunto(
                 primeiro)[1].name, 'INDIVIDUAL')])),
        )
        for selecao, ativo, esperado in casos:
            self.selecionar(*selecao, ativo=ativo)
            self.assertEqual(self.modos_dos_itens(), sorted(esperado),
                             [o.name for o in selecao])
            desenhos = addon._desenhos_hud(_ContextoRegiao())
            self.assertEqual(len(desenhos), len(esperado))
            # o item do ativo vem primeiro (gaveta e correntes leem ele)
            self.assertIn(ativo, (addon._alvo_hud(bpy.context)[0],
                                  *addon._alvo_hud(bpy.context)[2]))
        # chapa individual mostra L/A/E; modulo mostra L/P/A
        self.selecionar(*grupo_a, b1, ativo=b1)
        letras = {g['objeto'].name: {l['letra'] for l in g['linhas']
                                     if l['tipo'] == 'medida'}
                  for g, _a in addon._desenhos_hud(_ContextoRegiao())}
        self.assertEqual(letras[b1.name], {'L', 'A', 'E'})
        self.assertEqual(letras[primeiro.name], {'L', 'P', 'A'})

    def test_linhas_e_quinas_valem_em_qualquer_item_selecionado(self):
        # Setas e quinas tambem no item que NAO e' o ativo
        primeiro, segundo = self.dois_modulos()
        b1 = addon._chapas_do_conjunto(segundo)[0]
        self.selecionar(primeiro, *primeiro.children_recursive, b1, ativo=b1)
        projetar = lambda p: Vector((300 + p.x * 100 + p.y * 30,
                                     200 + p.z * 100 + p.y * 18))
        originais = (addon._contexto_hud, addon._projetar_hud)
        addon._contexto_hud = lambda _c: True
        addon._projetar_hud = lambda _c, p: projetar(p)
        self.addCleanup(setattr, addon, '_contexto_hud', originais[0])
        self.addCleanup(setattr, addon, '_projetar_hud', originais[1])
        geometria = addon._geometria_do_item(
            primeiro, 'GRUPO', addon._chapas_do_conjunto(primeiro))
        # quina do modulo nao ativo: mover
        alvo = addon._acertar_hud(bpy.context, projetar(geometria['cantos'][5]))
        self.assertEqual((alvo['tipo'], alvo['objeto']), ('ancora', primeiro))
        # linha L do modulo nao ativo: a seta e' dele
        linha = next(l for l in geometria['linhas']
                     if l['tipo'] == 'medida' and l['eixo'] == 0)
        a, b = (projetar(q) for q in linha['pontos'])
        alvo = addon._acertar_hud(bpy.context, a + (b - a) * 0.25)
        self.assertEqual((alvo['tipo'], alvo['objeto'], alvo['eixo']),
                         ('medida', primeiro, 0))
        self.assertEqual(alvo['lado'], 'min')
        largura = segundo.conj_largura_mm
        addon._aplicar_valor_hud(bpy.context, alvo, 900.0)
        self.assertAlmostEqual(primeiro.conj_largura_mm, 900.0, places=3)
        self.assertAlmostEqual(segundo.conj_largura_mm, largura, places=3)
        # so' o item do alvo acende; o outro desenha normal
        addon._hover_hud[4242] = alvo
        acesos = [g['objeto'] for g, aceso in
                  addon._desenhos_hud(_ContextoRegiao()) if aceso]
        self.assertEqual(acesos, [primeiro])

    def test_quina_continua_movendo_o_modulo(self):
        self.modulo()
        geometria = addon._geometria_hud(bpy.context)
        projetar = lambda p: Vector((300+p.x*500+p.y*150, 200+p.z*500+p.y*90))
        alvo = addon._acertar_linhas_hud(
            geometria, projetar(geometria['cantos'][5]), projetar)
        self.assertEqual(alvo['tipo'], 'ancora')
        self.assertNotIn('lado', alvo)

    def teclar(self, estado, texto):
        for c in texto:
            addon._tecla_no_texto(estado, 'X', c)

    def test_operador_continua_a_conta_em_vez_de_apagar(self):
        # Pedido do usuario: caixa aberta com "600" (todo selecionado);
        # '+' nao apaga -- fica "600 + "
        estado = {'texto': '600', 'cursor': 3, 'selecionado': True}
        addon._tecla_no_texto(estado, 'NUMPAD_PLUS', '+')
        self.assertEqual(estado['texto'], '600 + ')
        self.assertEqual(estado['cursor'], len('600 + '))
        self.teclar(estado, '100')
        self.assertEqual(addon._ler_medida_digitada(estado['texto']), 0.7)
        for operador in '-*/':
            estado = {'texto': '600', 'cursor': 3, 'selecionado': True}
            addon._tecla_no_texto(estado, 'X', operador)
            self.assertEqual(estado['texto'], '600 %s ' % operador)
        # print do usuario: "664 - 100+25" -- todo operador digitado sai
        # com um espaco de cada lado, em qualquer ponto da conta
        estado = {'texto': '664', 'cursor': 3, 'selecionado': True}
        self.teclar(estado, '-100+25*2/4')
        self.assertEqual(estado['texto'], '664 - 100 + 25 * 2 / 4')
        # sem espaco dobrado se ja' havia um; no meio tambem
        estado = {'texto': '664 ', 'cursor': 4, 'selecionado': False}
        self.teclar(estado, '+')
        self.assertEqual(estado['texto'], '664 + ')
        estado = {'texto': '600100', 'cursor': 3, 'selecionado': False}
        self.teclar(estado, '+')
        self.assertEqual(addon._com_cursor(estado['texto'], estado['cursor']),
                         '600 + |100')
        # colado entra como veio
        estado = {'texto': '', 'cursor': 0, 'selecionado': False}
        addon._tecla_no_texto(estado, 'V', '1+2')
        self.assertEqual(estado['texto'], '1+2')
        # numero com tudo selecionado continua trocando o texto
        estado = {'texto': '600', 'cursor': 3, 'selecionado': True}
        self.teclar(estado, '75')
        self.assertEqual(estado['texto'], '75')
        estado = {'texto': '600', 'cursor': 3, 'selecionado': True}
        addon._tecla_no_texto(estado, 'BACK_SPACE')
        self.assertEqual((estado['texto'], estado['cursor']), ('', 0))

    def test_unidade_solta_ou_no_meio_vale_para_o_numero(self):
        try:
            addon._definir_opcao('unidade_padrao', 'MM')
            # "500 + cm" -> 500 cm; "500 +" -> 500
            self.assertEqual(addon._arrumar_texto_medida('500 + cm'), '500cm')
            self.assertEqual(addon._ler_medida_digitada('500 + cm'), 5.0)
            self.assertEqual(addon._ler_medida_digitada('500 +'), 0.5)
            # "51cm00" (cm digitado no meio) -> 5100 cm
            self.assertEqual(addon._arrumar_texto_medida('51cm00'), '5100cm')
            self.assertEqual(addon._ler_medida_digitada('51cm00'), 51.0)
            # o que ja' funcionava nao muda
            for texto, metros in (('1m - 20mm', 0.98), ('600cm + 500mm', 6.5),
                                  ('2*300', 0.6), ('600 + 500', 1.1)):
                self.assertEqual(addon._ler_medida_digitada(texto), metros, texto)
        finally:
            addon._definir_opcao('unidade_padrao', 'MM')

    def test_cursor_anda_e_escreve_no_meio(self):
        # 500| -> clique ao lado do 5 -> 5|00 -> '1' -> 51|00 -> 'cm'
        largura = lambda t: 10 * len(t)            # 10 px por caractere
        estado = {'texto': '500', 'cursor': 3, 'selecionado': True}
        estado['cursor'] = addon._cursor_no_x('500', 3, 0, 12, largura)
        estado['selecionado'] = False
        self.assertEqual(estado['cursor'], 1)
        self.teclar(estado, '1')
        self.assertEqual(addon._com_cursor(estado['texto'], estado['cursor']),
                         '51|00')
        self.teclar(estado, 'cm')
        self.assertEqual(estado['texto'], '51cm00')
        self.assertEqual(addon._ler_medida_digitada(estado['texto']), 51.0)
        # depois da barra as posicoes andam a largura dela: "5|00", clique
        # em x=25 cai entre os dois zeros (posicao 2, x=30 na tela)
        self.assertEqual(addon._cursor_no_x('500', 1, 0, 25, largura), 2)
        # setas, Home/End, Del e Backspace no cursor
        estado = {'texto': '1234', 'cursor': 4, 'selecionado': False}
        for tecla in ('LEFT_ARROW', 'LEFT_ARROW'):
            addon._tecla_no_texto(estado, tecla)
        addon._tecla_no_texto(estado, 'BACK_SPACE')
        self.assertEqual((estado['texto'], estado['cursor']), ('134', 1))
        addon._tecla_no_texto(estado, 'DEL')
        self.assertEqual(estado['texto'], '14')
        addon._tecla_no_texto(estado, 'HOME')
        self.teclar(estado, '9')
        self.assertEqual(estado['texto'], '914')
        self.assertFalse(addon._tecla_no_texto(estado, 'F5'))

    def test_medida_digitada_aceita_conta_e_unidades_misturadas(self):
        for texto, metros in (('600 + 500', 1.1), ('600CM + 500MM', 6.5),
                              ('600cm + 500mm', 6.5), ('1m - 20mm', 0.98),
                              ('(600+500)/2', 0.55), ('2*300', 0.6)):
            # exato: o ruido do parser (1100.0001) e' arredondado
            self.assertEqual(addon._ler_medida_digitada(texto), metros, texto)
        try:
            addon._definir_opcao('unidade_padrao', 'CM')
            self.assertEqual(addon._ler_medida_digitada('60'), 0.6)
            # sem unidade = a padrao, mesmo ao lado de outra unidade
            self.assertEqual(addon._ler_medida_digitada('60 + 5mm'), 0.605)
            # o 2 multiplica, nao e' medida
            self.assertEqual(addon._ler_medida_digitada('2*30cm + 5'), 0.65)
            self.assertEqual(addon._texto_medida(600.0), '60.00 cm')
            self.assertEqual(addon._numero_na_unidade(600.0), '60')
        finally:
            addon._definir_opcao('unidade_padrao', 'MM')
        self.assertEqual(addon._texto_medida(600.0), '600.0 mm')

    def test_medida_digitada(self):
        for texto, metros in (('750', 0.75), ('75cm', 0.75), ('0,75 m', 0.75),
                              (' 18 ', 0.018)):
            self.assertAlmostEqual(addon._ler_medida_digitada(texto), metros)
        for texto in ('abc', '0', '-5'):
            with self.assertRaises(ValueError):
                addon._ler_medida_digitada(texto)

    def test_espessura_individual_livre_sem_alterar_outras_chapas(self):
        # A espessura nao arredonda mais para 15/18/20/30 (usuario).
        modulo = self.modulo()
        chapa = addon._chapas_do_conjunto(modulo)[0]
        outras = {o: o.chapa_espessura_mm for o in addon._chapas_do_conjunto(modulo)
                  if o != chapa}
        addon._selecionar_chapa_hud(bpy.context, chapa, individual=True)
        addon._aplicar_valor_hud(bpy.context, {'tipo': 'espessura', 'objeto': chapa}, 27)
        self.assertEqual(chapa.chapa_espessura_mm, 27)
        for o, espessura in outras.items():
            self.assertEqual(o.chapa_espessura_mm, espessura)
        self.assertEqual(addon._medidas_gaveta(bpy.context)[1][-1][1], 27)

    def test_gap_altera_somente_entre_folhas_e_sincroniza_menu(self):
        modulo = self.modulo()
        bpy.ops.object.cabinet_portas(
            capturado=True, ponto_a=(-0.3, -0.15, 0), ponto_b=(0.3, -0.15, 0.4),
            pai_nome=modulo.name, modulo_nome=modulo.name, frente='NEG_Y', folhas=2)
        grupo = addon._portas_do_conjunto(modulo)[0]
        antes = dict(grupo['porta_parametros'])
        alvo = {'tipo': 'gap', 'objeto': grupo}
        addon._aplicar_valor_hud(bpy.context, alvo, 8)
        self.assertEqual(grupo['porta_parametros']['entre_folhas_mm'], 8)
        self.assertEqual(bpy.context.scene.porta_entre_folhas_mm, 8)
        for chave in antes:
            if chave != 'entre_folhas_mm':
                self.assertEqual(antes[chave], grupo['porta_parametros'][chave])
        folhas = addon._folhas_portas(grupo)
        self.assertAlmostEqual((folhas[1].location.x-folhas[0].location.x)*1000
                               - folhas[0].chapa_largura_mm, 8, places=4)

    def test_cancelamento_restaura_geometria_e_parametros(self):
        modulo = self.modulo()
        alvo = addon._geometria_hud(bpy.context)['linhas'][0]
        estado = addon._estado_arraste_hud(bpy.context, alvo)
        addon._aplicar_valor_hud(bpy.context, alvo, 950)
        addon._restaurar_arraste_hud(bpy.context, estado)
        for obj, matriz, inversa, props, porta, vertices in estado[0]:
            for atual, esperado in zip(obj.matrix_world, matriz):
                self.assertLess((atual-esperado).length, 1e-6)
            for nome, valor in props.items():
                self.assertEqual(getattr(obj, nome), valor)
            if vertices is not None:
                for atual, esperado in zip(obj.data.vertices, vertices):
                    self.assertLess((atual.co-Vector(esperado)).length, 1e-6)

    def test_gaveta_nao_gera_mais_wireframe(self):
        self.modulo()
        for aba in ('MODULOS', 'PORTAS'):
            bpy.context.scene.cabinet_aba = aba
            for largura in (190, 320, 564):
                widgets = addon._widgets_gaveta(bpy.context, largura, 1400)
                self.assertFalse(any(w[5] and w[5][0] == 'wireframe' for w in widgets))

    def test_hover_esquece_objeto_liberado(self):
        # Crash do usuario no Ctrl+Z: o hover guardava o OBJETO e a HUD o
        # desenhava depois que o undo o liberou (memoria liberada).
        modulo = self.modulo()
        chapas = addon._chapas_do_conjunto(modulo)
        alvo = {'tipo': 'medida', 'objeto': modulo, 'chapas': chapas}
        self.assertTrue(addon._alvo_vivo(alvo))
        for evento, funcao in addon.HANDLERS_REFERENCIAS:
            self.assertIn(funcao, getattr(bpy.app.handlers, evento), evento)
        addon._hover_hud[1] = alvo
        addon._antes_de_desfazer()
        self.assertTrue(addon._desfazendo[0])
        addon._desfazendo[0] = False
        self.assertEqual(addon._hover_hud, {})
        bpy.data.objects.remove(chapas[0], do_unlink=True)
        self.assertFalse(addon._alvo_vivo(alvo))

    def test_handler_do_depsgraph_espera_o_undo_assentar(self):
        # Crash do usuario (2x): Ctrl+Z logo apos criar a porta; o 1o
        # recalculo depois do undo chamava o handler, que lia a selecao.
        modulo = self.modulo()
        chamadas = []
        original = addon.sincronizar_contornos
        addon.sincronizar_contornos = lambda *a, **k: chamadas.append(1)
        try:
            addon._depois_de_desfazer()
            self.assertTrue(addon._desfazendo[0])
            self.assertTrue(bpy.app.timers.is_registered(addon._fim_do_desfazer))
            addon.ao_atualizar_depsgraph(bpy.context.scene, None)
            self.assertEqual(chamadas, [])          # nada durante o undo
            addon._fim_do_desfazer()                 # o proximo tique
            self.assertFalse(addon._desfazendo[0])
            self.assertEqual(chamadas, [1])          # o contorno volta
        finally:
            addon.sincronizar_contornos = original
            addon._desfazendo[0] = False
            if bpy.app.timers.is_registered(addon._fim_do_desfazer):
                bpy.app.timers.unregister(addon._fim_do_desfazer)
        # a selecao dos grupos sai por select_get, sem a colecao
        bpy.ops.object.select_all(action='DESELECT')
        modulo.select_set(True)
        self.assertEqual(addon._grupos_selecionados(bpy.context.view_layer),
                         frozenset({modulo.name}))

    def test_handlers_e_gizmos_registrados(self):
        self.assertIsNotNone(addon._handler_hud_texto[0])
        self.assertIsNotNone(addon._handler_grid[0])
        self.assertIn(addon.VIEW3D_GT_hud_cabinet, addon.CLASSES)
        self.assertIn(addon.VIEW3D_GGT_hud_cabinet, addon.CLASSES)
        self.assertIn(addon.OBJECT_OT_arrastar_hud, addon.CLASSES)


addon.register()
resultado = unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(TestHUD))
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes da HUD')
