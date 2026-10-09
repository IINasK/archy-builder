"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_operadores_blender.py

Rede de seguranca dos operadores e orquestradores que nao tinham teste:
adjacencia depois da escala, absorcao da escala do Empty, espessura de
modulo/grupo/chapa, handler e timer, puxadores, poll da selecao e a
limpeza do unregister.

Bug achado por esta suite vira teste marcado `expectedFailure` com um
`# BUG:` em cima; consertado, o marcador sai e o teste fica de
regressao (os tres primeiros foram consertados na versao 126).
"""
import contextlib
import os
import sys
import unittest
from types import SimpleNamespace

import bpy
import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))


def caixa(nome, dims, centro):
    """Malha de caixa sem marcador, como viria de um arquivo de fora."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= dims[0]
        v.co.y *= dims[1]
        v.co.z *= dims[2]
    malha = bpy.data.meshes.new(nome)
    bm.to_mesh(malha)
    bm.free()
    obj = bpy.data.objects.new(nome, malha)
    bpy.context.collection.objects.link(obj)
    obj.location = centro
    bpy.context.view_layer.update()
    return obj


def selecionar(*objs):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0] if objs else None


def limites(objs):
    pontos = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    return ([min(p[i] for p in pontos) for i in range(3)],
            [max(p[i] for p in pontos) for i in range(3)])


@contextlib.contextmanager
def ocupado():
    """Simula o add-on no meio de uma escrita (guarda de reentrancia)."""
    antes = addon._ocupado[0]
    addon._ocupado[0] = True
    try:
        yield
    finally:
        addon._ocupado[0] = antes


class TestOperadores(unittest.TestCase):
    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.context.scene.cabinet_aba = 'MODULOS'
        addon._ocupado[0] = False
        addon._havia_modal[0] = False
        # O handler de depsgraph tambem normaliza a cada view_layer.update():
        # fora daqui os testes chamam os orquestradores na mao, um de cada
        # vez, para saber QUEM fez o trabalho.
        lista = bpy.app.handlers.depsgraph_update_post
        self._tinha_handler = addon.ao_atualizar_depsgraph in lista
        if self._tinha_handler:
            lista.remove(addon.ao_atualizar_depsgraph)

    def tearDown(self):
        lista = bpy.app.handlers.depsgraph_update_post
        if self._tinha_handler and addon.ao_atualizar_depsgraph not in lista:
            lista.append(addon.ao_atualizar_depsgraph)
        addon._ocupado[0] = False

    def assertPerto(self, a, b, casas=5):
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=casas)

    # ------------------------------------------------------------ cenas
    def nicho_solto(self, L=600.0, A=400.0, P=300.0, E=18.0):
        """Duas laterais, base e tampo, SEM Empty, com adjacencia."""
        li = L - 2 * E
        C = bpy.context
        pecas = {
            'Lat_E': addon.nova_chapa('Lat_E', A, P, E, (-(L / 2 - E / 2), 0, A / 2),
                                      (0, 90, 0), C),
            'Lat_D': addon.nova_chapa('Lat_D', A, P, E, (L / 2 - E / 2, 0, A / 2),
                                      (0, 90, 0), C),
            'Base': addon.nova_chapa('Base', li, P, E, (0, 0, E / 2), (0, 0, 0), C),
            'Tampo': addon.nova_chapa('Tampo', li, P, E, (0, 0, A - E / 2),
                                      (0, 0, 0), C),
        }
        C.view_layer.update()
        addon.detectar_adjacencia(list(pecas.values()))
        return pecas

    def modulo(self):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar()
        conj = next(o for o in bpy.data.objects if addon.MARCA_CONJUNTO in o)
        bpy.context.view_layer.update()
        return conj

    def peca(self, conj, prefixo):
        return next(o for o in addon._chapas_do_conjunto(conj)
                    if o.name.startswith(prefixo))

    def porta_importada(self, x=0.0, largura=0.4, altura=0.7, z=0.35, y=-0.2):
        placa = caixa('Placa', (largura, 0.018, altura), (x, y - 0.009, z))
        selecionar(placa)
        self.assertEqual(bpy.ops.object.cabinet_folha_de_objetos(), {'FINISHED'})
        return addon._grupo_portas(placa), placa

    # ================================================= 1. ADJACENCIA
    def test_adjacencia_fecha_o_vao_aberto_pela_escala(self):
        # Escalar o movel por F multiplica a POSICAO das laterais mas nao a
        # espessura delas: sobra (E/2)*(F-1) por lado entre base e lateral.
        L, E, F = 600.0, 18.0, 1.5
        C = bpy.context
        lat_e = addon.nova_chapa('Lat_E', 400, 300, E, (-(L / 2 - E / 2), 0, 200),
                                 (0, 90, 0), C)
        lat_d = addon.nova_chapa('Lat_D', 400, 300, E, (L / 2 - E / 2, 0, 200),
                                 (0, 90, 0), C)
        base = addon.nova_chapa('Base', L - 2 * E, 300, E, (0, 0, E / 2),
                                (0, 0, 0), C)
        C.view_layer.update()
        addon.detectar_adjacencia([lat_e, lat_d, base])
        self.assertEqual(base['adj_x_pos_uid'], lat_d['chapa_uid'])
        self.assertEqual(base['adj_x_neg_uid'], lat_e['chapa_uid'])
        # o que o S faria no grupo inteiro, em torno da origem
        for lat in (lat_e, lat_d):
            lat.location.x *= F
        C.view_layer.update()
        for lat in (lat_e, lat_d):
            lat.scale = (1.0, 1.0, F)      # local Z = X do mundo: espessura
        base.scale = (F, 1.0, 1.0)
        ajustadas = addon.normalizar_chapas()
        C.view_layer.update()
        self.assertEqual(set(ajustadas), {lat_e, lat_d, base})
        for obj in (lat_e, lat_d, base):
            self.assertPerto(obj.scale, (1, 1, 1))
        # espessura imune a escala (invariante 1)
        self.assertAlmostEqual(lat_d.chapa_espessura_mm, E, places=4)
        self.assertAlmostEqual(lat_d.chapa_largura_mm, 400, places=3)
        # a base levou o vao a mais: (L-2E)*F + 2*(E/2)*(F-1)
        so_escala = (L - 2 * E) * F
        self.assertAlmostEqual(base.chapa_largura_mm - so_escala,
                               2 * (E / 2) * (F - 1), places=2)
        self.assertAlmostEqual(base.chapa_largura_mm, (L - E) * F - E, places=2)
        # e encosta exatamente na face interna de cada lateral
        b_lo, b_hi = addon._faixa(base, X)
        self.assertAlmostEqual(b_hi, addon._faixa(lat_d, X)[0], places=5)
        self.assertAlmostEqual(b_lo, addon._faixa(lat_e, X)[1], places=5)

    # Regressao (era BUG, corrigido na 126): o eixo Y relia o centro de
    # um matrix_world defasado e desfazia o deslocamento do eixo X.
    def test_adjacencia_fecha_dois_eixos_ao_mesmo_tempo(self):
        C = bpy.context
        prat = addon.nova_chapa('Prat', 400, 300, 18, (0, 0, 0), (0, 0, 0), C)
        # lateral encostada em X+ (X 200..218), fundo encostado em Y+
        # (Y 150..168); estreitos o bastante para nao encostar nas quinas
        lat = addon.nova_chapa('Lat', 300, 100, 18, (209, 0, 0), (0, 90, 0), C)
        fundo = addon.nova_chapa('Fundo', 200, 300, 18, (0, 159, 0),
                                 (90, 0, 0), C)
        C.view_layer.update()
        addon.detectar_adjacencia([prat, lat, fundo])
        self.assertEqual(prat['adj_x_pos'], lat.name)
        self.assertEqual(prat['adj_y_pos'], fundo.name)
        prat.scale = (1.5, 1.5, 1.0)
        addon.normalizar_chapas()
        C.view_layer.update()
        self.assertAlmostEqual(prat.chapa_largura_mm, 500.0, places=2)
        self.assertAlmostEqual(prat.chapa_comprimento_mm, 375.0, places=2)
        # X: -300 (lado livre cresceu) .. 200 (face da lateral)
        self.assertPerto(addon._faixa(prat, X), (-0.3, 0.2), 4)
        # Y: -225 .. 150 (face do fundo)
        self.assertPerto(addon._faixa(prat, Y), (-0.225, 0.15), 4)

    def test_resolver_vizinho_prefere_uid_do_irmao_na_copia(self):
        conj = self.modulo()
        selecionar(conj, *conj.children)
        self.assertEqual(bpy.ops.object.duplicate(), {'FINISHED'})
        copia = next(o for o in bpy.context.selected_objects
                     if addon.MARCA_CONJUNTO in o)
        self.assertIsNot(copia, conj)
        copia.location.x += 2.0
        bpy.context.view_layer.update()
        base2 = self.peca(copia, 'Base')
        lat_d1 = self.peca(conj, 'Lateral_Dir')
        lat_d2 = self.peca(copia, 'Lateral_Dir')
        # a copia herda NOME e UID do original: so' o UID + irmaos distingue
        self.assertEqual(base2['adj_x_pos'], lat_d1.name)
        self.assertEqual(lat_d2['chapa_uid'], lat_d1['chapa_uid'])
        self.assertIs(addon._resolver_vizinho(
            base2, base2['adj_x_pos_uid'], base2['adj_x_pos']), lat_d2)
        # sem UID, cai no nome (e acha o original)
        self.assertIs(addon._resolver_vizinho(base2, '', base2['adj_x_pos']),
                      lat_d1)
        # o UID repetido entre modulos resolve dentro do proprio modulo
        self.assertIs(addon._resolver_vizinho(
            lat_d2, lat_d2['chapa_uid'], ''), lat_d2)
        # efeito: a base da copia fecha nas laterais DELA, nao do original
        base2.scale = (1.3, 1.0, 1.0)
        addon.normalizar_chapas()
        bpy.context.view_layer.update()
        self.assertAlmostEqual(base2.chapa_largura_mm, 564.0, places=2)
        self.assertPerto(addon._faixa(base2, X), (2 - 0.282, 2 + 0.282), 4)
        self.assertAlmostEqual(self.peca(conj, 'Base').chapa_largura_mm, 564.0,
                               places=2)

    # ============================== 2. OPERADOR DETECTAR ADJACENCIA
    def test_operador_detectar_adjacencia(self):
        C = bpy.context
        lat = addon.nova_chapa('Lat', 400, 300, 18, (291, 0, 200), (0, 90, 0), C)
        base = addon.nova_chapa('Base', 564, 300, 18, (0, 0, 9), (0, 0, 0), C)
        C.view_layer.update()
        selecionar(base)
        self.assertEqual(bpy.ops.object.cabinet_detectar_adjacencia(),
                         {'CANCELLED'})
        self.assertNotIn('adj_x_pos', base)
        self.assertNotIn('chapa_uid', base)
        # um nao-chapa na selecao nao conta como segunda chapa
        intruso = caixa('Intruso', (0.1, 0.1, 0.1), (2, 0, 0))
        selecionar(base, intruso)
        self.assertEqual(bpy.ops.object.cabinet_detectar_adjacencia(),
                         {'CANCELLED'})
        selecionar(base, lat)
        self.assertEqual(bpy.ops.object.cabinet_detectar_adjacencia(),
                         {'FINISHED'})
        self.assertEqual(base['adj_x_pos'], lat.name)
        self.assertEqual(base['adj_x_pos_uid'], lat['chapa_uid'])
        self.assertAlmostEqual(base['adj_x_pos_folga'], 0.0, places=6)
        self.assertEqual(base['adj_x_pos_face'], 0)     # face mais proxima
        self.assertEqual(base['adj_x_neg'], '')         # nada a esquerda
        for ponta in addon.PONTAS:
            self.assertIn('adj_' + ponta, lat)
        self.assertNotIn(addon.MARCA_CHAPA, intruso)

    # ===================================== 3. ABSORVER CONJUNTOS
    def test_absorver_conjuntos_sem_escala_nao_mexe(self):
        conj = self.modulo()
        antes = {o.name: o.matrix_world.copy() for o in conj.children}
        medidas = (conj.conj_largura_mm, conj.conj_altura_mm,
                   conj.conj_profundidade_mm)
        addon.absorver_conjuntos()
        bpy.context.view_layer.update()
        for o in conj.children:
            for a, b in zip(o.matrix_world, antes[o.name]):
                self.assertLess((a - b).length, 1e-6)
        self.assertPerto((conj.conj_largura_mm, conj.conj_altura_mm,
                          conj.conj_profundidade_mm), medidas, 3)

    # Regressao (era BUG, corrigido na 126): S no Empty do modulo nao
    # surtia efeito -- os filhos voltavam pelo pai ainda escalado.
    def test_absorver_conjuntos_passa_escala_do_empty_para_as_chapas(self):
        F = 1.5
        conj = self.modulo()
        lat_d = self.peca(conj, 'Lateral_Dir')
        base = self.peca(conj, 'Base')
        conj.scale = (F, 1.0, 1.0)
        bpy.context.view_layer.update()
        # pre-condicao: o S no Empty de fato levou a lateral para fora
        self.assertAlmostEqual(lat_d.matrix_world.translation.x, 0.291 * F,
                               places=5)
        addon.absorver_conjuntos()
        bpy.context.view_layer.update()
        self.assertPerto(conj.scale, (1, 1, 1))
        # as chapas ficam onde o S as deixou...
        self.assertAlmostEqual(lat_d.matrix_world.translation.x, 0.291 * F,
                               places=5)
        addon.normalizar_chapas()
        bpy.context.view_layer.update()
        # ...e, normalizadas, o modulo tem a medida nova: laterais com a
        # mesma espessura e a base fechando o vao (E/2)*(F-1)
        for o in addon._chapas_do_conjunto(conj):
            self.assertPerto(o.scale, (1, 1, 1))
            self.assertAlmostEqual(o.chapa_espessura_mm, 18.0, places=4)
        self.assertAlmostEqual(base.chapa_largura_mm, 582 * F - 18, places=2)
        self.assertAlmostEqual(conj.conj_largura_mm, 582 * F + 18, places=2)
        self.assertAlmostEqual(addon.medir_conjunto(conj)[0], 582 * F + 18,
                               places=2)
        self.assertAlmostEqual(conj.conj_altura_mm, 400.0, places=2)

    # ============================================= 4. ESPESSURA
    def test_espessura_do_modulo_engrossa_para_dentro(self):
        conj = self.modulo()
        caixa_antes = addon.medir_conjunto(conj)
        lo_antes, hi_antes = limites(addon._chapas_do_conjunto(conj))
        conj.conj_espessura_mm = 30.0
        bpy.context.view_layer.update()
        chapas = addon._chapas_do_conjunto(conj)
        for o in chapas:
            self.assertAlmostEqual(o.chapa_espessura_mm, 30.0, places=4)
        # contorno externo parado (medidas e caixa real de malha)
        self.assertPerto(addon.medir_conjunto(conj), caixa_antes, 2)
        lo, hi = limites(chapas)
        self.assertPerto(lo, lo_antes, 4)
        self.assertPerto(hi, hi_antes, 4)
        # base e tampo encolhem para caber entre as laterais mais grossas
        for nome in ('Base', 'Tampo'):
            self.assertAlmostEqual(self.peca(conj, nome).chapa_largura_mm,
                                   600 - 2 * 30, places=2)
        self.assertAlmostEqual(addon._faixa(self.peca(conj, 'Lateral_Dir'), X)[0],
                               0.3 - 0.030, places=5)
        self.assertAlmostEqual(addon._faixa(self.peca(conj, 'Base'), Z)[1],
                               0.030, places=5)
        self.assertAlmostEqual(addon._faixa(self.peca(conj, 'Tampo'), Z)[0],
                               0.4 - 0.030, places=5)

    def test_espessura_de_uma_chapa_ancora_na_face_externa(self):
        conj = self.modulo()
        lat_d = self.peca(conj, 'Lateral_Dir')
        base = self.peca(conj, 'Base')
        lado_externo = addon._faixa(lat_d, X)[1]
        self.assertAlmostEqual(lado_externo, 0.3, places=5)
        largura_base = base.chapa_largura_mm
        lat_d.chapa_espessura_mm = 30.0
        bpy.context.view_layer.update()
        self.assertAlmostEqual(lat_d.chapa_espessura_mm, 30.0, places=4)
        # a face no limite do modulo fica; a nova espessura vai para dentro
        lo, hi = addon._faixa(lat_d, X)
        self.assertAlmostEqual(hi, lado_externo, places=5)
        self.assertAlmostEqual(hi - lo, 0.030, places=5)
        # Pedido do usuario: a base NAO se mexe (nada "gruda" na solda);
        # a solda dela com a lateral sai da origem e fica para a regua
        self.assertAlmostEqual(base.chapa_largura_mm, largura_base, places=4)
        self.assertAlmostEqual(addon._faixa(base, X)[1], 0.3 - 0.018, places=5)
        self.assertIn(base, {l['a'] for l in addon._pontas_fora_do_lugar([lat_d])}
                      | {l['b'] for l in addon._pontas_fora_do_lugar([lat_d])})
        # a malha acompanha as props, e as outras chapas nao mudaram
        self.assertAlmostEqual(limites([lat_d])[1][0], 0.3, places=5)
        self.assertAlmostEqual(self.peca(conj, 'Lateral_Esq').chapa_espessura_mm,
                               18.0, places=4)
        self.assertAlmostEqual(addon.medir_conjunto(conj)[0], 600.0, places=2)

    def test_espessura_de_uma_chapa_nao_puxa_peca_afastada(self):
        # Bug do usuario: mudar o E de UMA chapa reaplicava TODAS as soldas
        # da cena e puxava de volta a lateral afastada de proposito
        conj = self.modulo()
        lat_d = self.peca(conj, 'Lateral_Dir')
        tampo = self.peca(conj, 'Tampo')
        lat_d.location.x += 0.2
        bpy.context.view_layer.update()
        longe = lat_d.matrix_world.translation.copy()
        largura_tampo = tampo.chapa_largura_mm
        self.peca(conj, 'Lateral_Esq').chapa_espessura_mm = 25.0
        bpy.context.view_layer.update()
        self.assertLess((lat_d.matrix_world.translation - longe).length, 1e-6)
        self.assertAlmostEqual(tampo.chapa_largura_mm, largura_tampo, places=4)

    def test_espessura_do_grupo_solto_pela_cena(self):
        pecas = self.nicho_solto()
        selecionar(pecas['Base'], *pecas.values())
        self.assertEqual(addon._modo_chapa(bpy.context, pecas['Base']), 'GRUPO')
        self.assertEqual(set(addon._grupo_ativo(bpy.context)),
                         set(pecas.values()))
        addon.sincronizar_grupo(bpy.context)
        s = bpy.context.scene
        self.assertAlmostEqual(s.grupo_largura_mm, 600.0, places=2)
        self.assertAlmostEqual(s.grupo_espessura_mm, 18.0, places=4)
        lo_antes, hi_antes = limites(list(pecas.values()))
        s.grupo_espessura_mm = 30.0
        bpy.context.view_layer.update()
        for o in pecas.values():
            self.assertIsNone(o.parent)
            self.assertAlmostEqual(o.chapa_espessura_mm, 30.0, places=4)
        lo, hi = limites(list(pecas.values()))
        self.assertPerto(lo, lo_antes, 4)
        self.assertPerto(hi, hi_antes, 4)
        self.assertAlmostEqual(pecas['Base'].chapa_largura_mm, 540.0, places=2)
        self.assertAlmostEqual(addon._faixa(pecas['Tampo'], Z)[0], 0.37, places=5)

    # ======================================= 5. HANDLER E TIMER
    def chapa_escalada(self):
        chapa = addon.nova_chapa('Solta', 600, 400, 18, (0, 0, 0), (0, 0, 0),
                                 bpy.context)
        bpy.context.view_layer.update()
        chapa.scale = (2.0, 0.5, 3.0)
        return chapa

    def test_handler_de_depsgraph_normaliza_quando_nao_ha_modal(self):
        chapa = self.chapa_escalada()
        with ocupado():
            addon.ao_atualizar_depsgraph(bpy.context.scene, None)
        self.assertPerto(chapa.scale, (2.0, 0.5, 3.0))
        self.assertAlmostEqual(chapa.chapa_largura_mm, 600.0, places=3)
        addon.ao_atualizar_depsgraph(bpy.context.scene, None)
        self.assertPerto(chapa.scale, (1, 1, 1))
        self.assertAlmostEqual(chapa.chapa_largura_mm, 1200.0, places=3)
        self.assertAlmostEqual(chapa.chapa_comprimento_mm, 200.0, places=3)
        self.assertAlmostEqual(chapa.chapa_espessura_mm, 18.0, places=4)
        self.assertFalse(addon._havia_modal[0])
        # a malha foi refeita com a medida nova
        bpy.context.view_layer.update()
        lo, hi = limites([chapa])
        self.assertPerto((hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]),
                         (1.2, 0.2, 0.018), 5)

    def test_handler_termina_o_modal_que_havia(self):
        # transicao "o modal acabou": recalcula e esquece o modal
        chapa = self.chapa_escalada()
        addon._havia_modal[0] = True
        addon.ao_atualizar_depsgraph(bpy.context.scene, None)
        self.assertFalse(addon._havia_modal[0])
        self.assertAlmostEqual(chapa.chapa_largura_mm, 1200.0, places=3)

    def test_timer_normaliza_e_continua_vivo(self):
        chapa = self.chapa_escalada()
        with ocupado():
            self.assertEqual(addon.verificar_periodicamente(),
                             addon.INTERVALO_TIMER)
        self.assertPerto(chapa.scale, (2.0, 0.5, 3.0))
        self.assertAlmostEqual(chapa.chapa_largura_mm, 600.0, places=3)
        self.assertEqual(addon.verificar_periodicamente(), addon.INTERVALO_TIMER)
        self.assertPerto(chapa.scale, (1, 1, 1))
        self.assertAlmostEqual(chapa.chapa_largura_mm, 1200.0, places=3)
        self.assertAlmostEqual(chapa.chapa_espessura_mm, 18.0, places=4)

    # ============================================== 6. PUXADORES
    def test_converter_puxador_marca_so_o_que_nao_e_chapa(self):
        chapa = addon.nova_chapa('Chapa', 600, 400, 18, (0, 0, 0), (0, 0, 0),
                                 bpy.context)
        pux = caixa('Pux', (0.02, 0.03, 0.15), (1, 0, 0))
        selecionar(chapa)
        self.assertFalse(addon.OBJECT_OT_converter_puxador.poll(bpy.context))
        antes = limites([pux])
        selecionar(pux, chapa)
        self.assertTrue(addon.OBJECT_OT_converter_puxador.poll(bpy.context))
        self.assertEqual(bpy.ops.object.cabinet_converter_puxador(),
                         {'FINISHED'})
        self.assertIn(addon.MARCA_PUXADOR, pux)
        self.assertEqual(list(pux[addon.CHAVE_TRAVAS_PUXADOR]), [1, 1, 1])
        self.assertNotIn(addon.MARCA_PUXADOR, chapa)     # chapa nao vira puxador
        self.assertIn(addon.MARCA_CHAPA, chapa)
        self.assertIsNone(pux.parent)
        self.assertEqual(limites([pux]), antes)          # medidas preservadas
        # ja' puxador: nao aparece mais como malha solta
        selecionar(pux)
        self.assertFalse(addon.OBJECT_OT_converter_puxador.poll(bpy.context))

    def test_puxadores_e_folhas_da_selecao(self):
        grupo, placa = self.porta_importada()
        pux = caixa('Pux', (0.02, 0.03, 0.15), (0.17, -0.233, 0.35))
        pux[addon.MARCA_PUXADOR] = 1
        selecionar(pux, grupo, placa)
        puxadores, folhas = addon._puxadores_e_folhas_da_selecao(bpy.context)
        self.assertEqual(puxadores, [pux])
        self.assertEqual(folhas, [placa])                # sem repetir
        selecionar(pux)
        self.assertEqual(addon._puxadores_e_folhas_da_selecao(bpy.context),
                         ([pux], []))
        self.assertFalse(addon.OBJECT_OT_vincular_puxador.poll(bpy.context))

    def test_vincular_puxador_pendura_na_folha_mais_proxima_sem_mover(self):
        g1, placa1 = self.porta_importada(x=-0.5)
        g2, placa2 = self.porta_importada(x=0.5)
        pux = caixa('Pux', (0.02, 0.03, 0.15), (0.67, -0.233, 0.35))
        selecionar(pux)
        bpy.ops.object.cabinet_converter_puxador()
        mundo = pux.matrix_world.copy()
        selecionar(pux, g1, g2)
        self.assertTrue(addon.OBJECT_OT_vincular_puxador.poll(bpy.context))
        self.assertEqual(bpy.ops.object.cabinet_vincular_puxador(), {'FINISHED'})
        self.assertIs(pux.parent, placa2)
        bpy.context.view_layer.update()
        for a, b in zip(pux.matrix_world, mundo):
            self.assertLess((a - b).length, 1e-6)
        # inversa identidade: matrix_basis E' o referencial da folha
        for a, b in zip(pux.matrix_parent_inverse, Matrix.Identity(4)):
            self.assertLess((a - b).length, 1e-6)
        # pendurado, acompanha a folha
        placa2.matrix_world = (Matrix.Translation((0, 0, 0.1))
                               @ placa2.matrix_world)
        bpy.context.view_layer.update()
        self.assertAlmostEqual(pux.matrix_world.translation.z,
                               mundo.translation.z + 0.1, places=6)

    # ======================================== 7. POLL DA SELECAO
    def contexto_viewport(self):
        janela = bpy.context.window_manager.windows[0]
        area = next(a for a in janela.screen.areas if a.type == 'VIEW_3D')
        regiao = next(r for r in area.regions if r.type == 'WINDOW')
        return janela, area, regiao

    def test_poll_da_selecao_por_grupo(self):
        janela, area, regiao = self.contexto_viewport()
        outra = next(a for a in janela.screen.areas if a.type != 'VIEW_3D')
        chapa = addon.nova_chapa('Chapa', 600, 400, 18, (0, 0, 0), (0, 0, 0),
                                 bpy.context)
        selecionar(chapa)
        poll = addon.OBJECT_OT_selecionar.poll
        prefs_original = addon._prefs
        try:
            with bpy.context.temp_override(window=janela, area=area,
                                           region=regiao):
                # sem preferencias (add-on por script): opcao ligada
                self.assertIsNone(addon._prefs())
                self.assertTrue(poll(bpy.context))
                addon._prefs = lambda: SimpleNamespace(selecao_por_grupo=False)
                self.assertFalse(poll(bpy.context))
                addon._prefs = lambda: SimpleNamespace(selecao_por_grupo=True)
                self.assertTrue(poll(bpy.context))
                addon._prefs = prefs_original
                bpy.ops.object.mode_set(mode='EDIT')
                try:
                    self.assertEqual(bpy.context.mode, 'EDIT_MESH')
                    self.assertFalse(poll(bpy.context))
                finally:
                    bpy.ops.object.mode_set(mode='OBJECT')
                self.assertTrue(poll(bpy.context))
            with bpy.context.temp_override(window=janela, area=outra):
                self.assertFalse(poll(bpy.context))     # fora da viewport
        finally:
            addon._prefs = prefs_original

    # ===================================== 9. MEDIDAS DO GRUPO SOLTO
    def test_largura_do_grupo_solto_pela_cena(self):
        pecas = self.nicho_solto()
        selecionar(pecas['Base'], *pecas.values())
        addon.sincronizar_grupo(bpy.context)
        s = bpy.context.scene
        self.assertAlmostEqual(s.grupo_altura_mm, 400.0, places=2)
        self.assertAlmostEqual(s.grupo_profundidade_mm, 300.0, places=2)
        lo_antes, hi_antes = limites(list(pecas.values()))
        s.grupo_largura_mm = 800.0
        bpy.context.view_layer.update()
        lo, hi = limites(list(pecas.values()))
        # ancora 'min' em X: a esquerda fica, a direita anda 200 mm
        self.assertAlmostEqual(lo[0], lo_antes[0], places=5)
        self.assertAlmostEqual(hi[0], hi_antes[0] + 0.2, places=5)
        self.assertPerto(lo[1:], lo_antes[1:], 5)
        self.assertPerto(hi[1:], hi_antes[1:], 5)
        for o in pecas.values():
            self.assertAlmostEqual(o.chapa_espessura_mm, 18.0, places=4)
            self.assertPerto(o.scale, (1, 1, 1))
        for nome in ('Base', 'Tampo'):
            self.assertAlmostEqual(pecas[nome].chapa_largura_mm, 764.0, places=2)
        self.assertAlmostEqual(pecas['Lat_D'].chapa_largura_mm, 400.0, places=2)
        self.assertAlmostEqual(addon._faixa(pecas['Base'], X)[1],
                               addon._faixa(pecas['Lat_D'], X)[0], places=5)

    def test_redimensionar_grupo_da_cena_sem_grupo_nao_faz_nada(self):
        selecionar()
        addon.redimensionar_grupo_da_cena(bpy.context.scene, bpy.context)
        avulsa = caixa('Avulsa', (0.1, 0.1, 0.1), (0, 0, 0))
        selecionar(avulsa)
        self.assertEqual(addon._grupo_ativo(bpy.context), [])
        addon.redimensionar_grupo_da_cena(bpy.context.scene, bpy.context)
        self.assertPerto(avulsa.dimensions, (0.1, 0.1, 0.1))

    # ================================== 10. FUNCOES DE APOIO
    def test_sem_modal_em_background(self):
        self.assertGreater(len(bpy.context.window_manager.windows), 0)
        self.assertFalse(addon._ha_modal_ativo())

    def test_marcar_apanhando_acende_o_botao(self):
        antes = addon._apanhando_vao[0]
        try:
            addon._marcar_apanhando(True)
            self.assertTrue(addon._apanhando_vao[0])
            addon._marcar_apanhando(True)                # idempotente
            self.assertTrue(addon._apanhando_vao[0])
            rotulo, acao = addon._botao_criar_portas(bpy.context)
            self.assertEqual(rotulo, 'Marcando o vao... (Esc cancela)')
            self.assertTrue(acao[2])
            addon._marcar_apanhando(False)
            self.assertFalse(addon._apanhando_vao[0])
            rotulo, acao = addon._botao_criar_portas(bpy.context)
            self.assertEqual(rotulo, 'Criar Portas')
            self.assertFalse(acao[2])
        finally:
            addon._apanhando_vao[0] = antes

    def test_modal_terminado_larga_os_objetos_da_cena(self):
        # Crash do usuario (repetivel): Ctrl+Z enquanto a porta nascia. O
        # wizard terminado seguia vivo (REGISTER) segurando os objetos do
        # ima, e o undo os liberava com o Python ainda segurando.
        modais = [c for c in addon.CLASSES if isinstance(c, type)
                  and issubclass(c, bpy.types.Operator) and 'modal' in c.__dict__]
        self.assertIn(addon.OBJECT_OT_apanhar_vao_portas, modais)
        for classe in modais:
            self.assertTrue(getattr(classe.modal, 'larga_dados', False),
                            classe.__name__)
        bpy.ops.mesh.primitive_cube_add()
        cubo = bpy.context.object

        class Falso:
            def modal(self, context, event):
                self._alvos = [(cubo, [cubo.location.copy()])]
                self._mapa = {'a': cubo}
                self._base = {cubo: cubo.location.copy()}
                self._numero = 3
                self._pronto = context
                return event

        modal = addon._envolver_evento(Falso.modal)
        op = Falso()
        self.assertEqual(modal(op, 'ctx', {'RUNNING_MODAL'}), {'RUNNING_MODAL'})
        self.assertIsNotNone(op._alvos)          # rodando: nada muda
        modal(op, 'ctx', {'FINISHED'})
        self.assertIsNone(op._alvos)
        self.assertIsNone(op._mapa)
        self.assertIsNone(op._base)
        self.assertEqual((op._numero, op._pronto), (3, 'ctx'))

    # ========================================= 11. UNREGISTER
    def test_unregister_remove_handlers_timers_keymaps_e_classes(self):
        lista = bpy.app.handlers.depsgraph_update_post
        if self._tinha_handler:
            lista.append(addon.ao_atualizar_depsgraph)
        self.assertIsNotNone(addon._handler_grid[0])
        self.assertIsNotNone(addon._handler_hud_texto[0])
        addon.unregister()
        try:
            self.assertIsNone(addon._handler_grid[0])
            self.assertIsNone(addon._handler_hud_texto[0])
            self.assertIsNone(addon._handler_gaveta[0])
            self.assertIsNone(addon._handler_posicionador[0])
            self.assertNotIn(addon.ao_atualizar_depsgraph, lista)
            for evento, funcao in (addon.HANDLERS_CONTORNO
                                   + addon.HANDLERS_REFERENCIAS):
                self.assertNotIn(funcao, getattr(bpy.app.handlers, evento),
                                 evento)
            for timer in (addon.verificar_periodicamente,
                          addon._limitar_largura_gaveta,
                          addon._reconectar_gavetas,
                          addon._configurar_gavetas,
                          addon._animar_realces,
                          addon._fim_do_desfazer):
                self.assertFalse(bpy.app.timers.is_registered(timer),
                                 timer.__name__)
            self.assertEqual(addon._keymaps, [])
            kc = bpy.context.window_manager.keyconfigs.addon
            km = kc.keymaps.get('3D View') if kc else None
            if km is not None:
                self.assertFalse([k for k in km.keymap_items
                                  if k.idname.startswith('object.cabinet')])
            for classe in addon.CLASSES:
                # gizmo nao tem `is_registered`; o bl_rna sai no unregister
                self.assertNotIn('bl_rna', classe.__dict__, classe.__name__)
            self.assertFalse(hasattr(bpy.types.Scene, 'cabinet_aba'))
        finally:
            addon.register()
        # e volta inteiro
        self.assertIsNotNone(addon._handler_grid[0])
        self.assertIsNotNone(addon._handler_hud_texto[0])
        self.assertIn(addon.ao_atualizar_depsgraph, lista)
        for classe in addon.CLASSES:
            self.assertIn('bl_rna', classe.__dict__, classe.__name__)
        self.assertTrue(hasattr(bpy.types.Scene, 'cabinet_aba'))
        if not self._tinha_handler:
            lista.remove(addon.ao_atualizar_depsgraph)

    # Regressao (era BUG, corrigido na 126): timers do register() sem
    # remocao no unregister (invariante 13), inclusive um lambda.
    def test_unregister_remove_timer_de_diagnostico(self):
        self.assertTrue(bpy.app.timers.is_registered(addon._log_keymaps))
        addon.unregister()
        try:
            for timer in (addon._log_keymaps,
                          addon._registrar_bibliotecas_adiado):
                self.assertFalse(bpy.app.timers.is_registered(timer),
                                 timer.__name__)
        finally:
            addon.register()


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestOperadores)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de operadores')
