"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_gavetas_blender.py

Gavetas do movel (pedido do usuario): grupo de gavetas num vao do modulo
-- frente, caixa e trilho (blocagem em tamanho real, telescopico de
padrao) --, a aba propria, a selecao como a da porta (clique = todas,
duplo = uma; so' elas com linha na HUD), o slider de abertura, os 3
pontos com Alt e a quantidade/profundidade/trilho editaveis.

O assistente (cliques, scroll, Alt) e o arraste do slider, com eventos de
verdade, estao em `gui_interacao.py`.
"""
import os
import sys
import unittest

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

G = addon.gavetas


class TestGavetas(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for colecao in list(bpy.data.collections):
            bpy.data.collections.remove(colecao)
        camada = bpy.context.view_layer
        camada.active_layer_collection = camada.layer_collection
        G.esquecer()
        # balcao 800 x 700 x 560, chapa 18: o vao de dentro e' 764 x 664
        self.conj = addon.modulos.criar_armario(bpy.context, 'Balcao', 800, 700, 560,
                                                fundo=False)
        bpy.context.view_layer.update()

    def gavetas(self, **p):
        padrao = dict(quantidade=3, lateral_mm=18.0, espessura_frente_mm=18.0,
                      profundidade_mm=560.0)
        padrao.update(p)
        return G.criar_gavetas(bpy.context, self.conj, (18, 18, 18, 18, 0), padrao)

    def pecas(self, gaveta, peca):
        return [o for o in gaveta.children if o.get(G.MARCA_PECA) == peca]

    def test_calculo_telescopico_e_oculto(self):
        p = dict(G.PARAMETROS_PADRAO, quantidade=3, profundidade_mm=560.0)
        dados = G.calcular(764.0, 664.0, p)
        self.assertEqual(dados['trilho_mm'], 550)       # 560 - 10 de folga
        alturas = [f['frente'][5] - f['frente'][4] for f in dados['gavetas']]
        self.assertAlmostEqual(max(alturas) - min(alturas), 0.0, places=6)
        # sobreposta cobre a lateral menos a folga frontal: 18 - 2
        self.assertAlmostEqual(dados['gavetas'][0]['frente'][0], -16.0)
        fundo = dados['gavetas'][0]['caixa'][0][2]
        self.assertAlmostEqual(fundo[1] - fundo[0], 764.0 - 2 * 12.7, places=3)
        p['trilho'] = 'OCULTO'
        fundo = G.calcular(764.0, 664.0, p)['gavetas'][0]['caixa'][0][2]
        self.assertAlmostEqual(fundo[1] - fundo[0], 764.0 - 10.0, places=3)
        with self.assertRaises(ValueError):
            G.calcular(764.0, 664.0, dict(p, quantidade=10, entre_gavetas_mm=40))
        with self.assertRaisesRegex(ValueError, 'menor trilho'):
            G.calcular(764.0, 664.0, dict(p, profundidade_mm=200.0))

    def test_cria_frente_caixa_trilho_e_puxador_sem_mexer_no_modulo(self):
        antes = addon.modulos.medir_conjunto(self.conj)
        chapas = len(addon.modulos._chapas_do_conjunto(self.conj))
        grupo = self.gavetas()
        gavetas = G.gavetas_do_grupo(grupo)
        self.assertEqual(len(gavetas), 3)
        for g in gavetas:
            self.assertEqual(len(self.pecas(g, 'FRENTE')), 1)
            self.assertEqual(len(self.pecas(g, 'LATERAL')), 2)
            self.assertEqual(len(self.pecas(g, 'TRILHO')), 2)        # os moveis
            frente = self.pecas(g, 'FRENTE')[0]
            self.assertTrue(any(addon.chapas.MARCA_PUXADOR in f for f in frente.children))
        self.assertEqual(len([o for o in grupo.children if o.get(G.MARCA_PECA) == 'TRILHO']), 6)
        self.assertEqual(len(addon.modulos._chapas_do_conjunto(self.conj)), chapas)
        for a, b in zip(antes, addon.modulos.medir_conjunto(self.conj)):
            self.assertAlmostEqual(a, b, places=3)
        self.assertAlmostEqual(G.medidas(grupo)[0], 764.0, places=3)
        self.assertAlmostEqual(G.medidas(grupo)[1], 664.0, places=3)
        self.assertEqual(grupo[G.CHAVE_TRILHO_MM], 550.0)

    def test_abertura_leva_a_gaveta_para_fora_pelo_trilho(self):
        grupo = self.gavetas()
        gaveta = G.gavetas_do_grupo(grupo)[1]
        frente = self.pecas(gaveta, 'FRENTE')[0]
        y0 = frente.matrix_world.translation.y
        G.definir_abertura(gaveta, 1.0)
        bpy.context.view_layer.update()
        self.assertAlmostEqual(frente.matrix_world.translation.y - y0, -0.55, places=5)
        fixo = next(o for o in grupo.children if o.get(G.MARCA_PECA) == 'TRILHO')
        self.assertEqual(fixo.parent, grupo)        # o fixo nao sai com ela

    def test_editar_refaz_e_guarda_abertura_e_puxador(self):
        grupo = self.gavetas()
        G.definir_abertura(G.gavetas_do_grupo(grupo)[0], 0.4)
        G.colocar_puxador(G.gavetas_do_grupo(grupo)[0], 'ALCA')
        self.assertIsNone(G.editar(bpy.context, grupo, 'gavetas_quantidade', 2))
        gavetas = G.gavetas_do_grupo(grupo)
        self.assertEqual(len(gavetas), 2)
        self.assertAlmostEqual(gavetas[0][G.CHAVE_ABERTURA], 0.4)
        self.assertEqual(gavetas[0][G.CHAVE_PUXADOR], 'ALCA')
        self.assertIsNone(G.editar(bpy.context, grupo, 'trilho', 'OCULTO'))
        fundo = self.pecas(G.gavetas_do_grupo(grupo)[0], 'FUNDO')[0]
        self.assertAlmostEqual(fundo.chapa_largura_mm, 764.0 - 10.0, places=2)
        # nao cabe: devolve o erro e fica como estava
        erro = G.editar(bpy.context, grupo, 'profundidade_mm', 150.0)
        self.assertIn('menor trilho', erro)
        self.assertEqual(G.parametros(grupo)['profundidade_mm'], 560.0)
        self.assertEqual(len(G.gavetas_do_grupo(grupo)), 2)

    def test_modulo_que_muda_de_medida_leva_as_gavetas(self):
        grupo = self.gavetas()
        self.conj.conj_largura_mm = 1000.0          # dispara o redimensionar
        bpy.context.view_layer.update()
        self.assertAlmostEqual(G.medidas(grupo)[0], 964.0, places=2)
        frente = self.pecas(G.gavetas_do_grupo(grupo)[0], 'FRENTE')[0]
        self.assertAlmostEqual(frente.chapa_largura_mm, 964.0 + 32.0, places=2)

    def test_selecao_como_a_da_porta_e_so_elas_na_hud(self):
        grupo = self.gavetas()
        gaveta = G.gavetas_do_grupo(grupo)[2]
        frente = self.pecas(gaveta, 'FRENTE')[0]
        self.assertEqual(addon.selecao._aba_da_selecao(frente), 'GAVETAS')
        G.selecionar(bpy.context, frente, 'GRUPO')
        self.assertEqual(bpy.context.view_layer.objects.active, grupo)
        self.assertFalse(self.conj.select_get())
        itens = addon.hud._itens_da_selecao(bpy.context)
        self.assertEqual([(o.name, modo) for o, modo, _c in itens], [(grupo.name, 'GAVETAS')])
        geometria = addon.hud._geometria_do_item(*itens[0])
        self.assertEqual({l['tipo'] for l in geometria['linhas']}, {'gavetas'})
        self.assertEqual(len(G.gavetas_com_slider(bpy.context)), 3)
        G.selecionar(bpy.context, frente, 'GAVETA')
        self.assertEqual(bpy.context.view_layer.objects.active, gaveta)
        self.assertEqual(G.gavetas_com_slider(bpy.context), [gaveta])
        self.assertEqual(len(addon.hud._itens_da_selecao(bpy.context)), 1)

    def test_hud_edita_largura_com_a_quina_parada_e_profundidade(self):
        grupo = self.gavetas()
        G.selecionar(bpy.context, grupo, 'GRUPO')
        geometria = addon.hud._geometria_do_item(grupo, 'GAVETAS', [])
        inversa = grupo.matrix_world.inverted()
        projetar = lambda p: Vector(((inversa @ p).x, (inversa @ p).z)) * 1000.0
        linha = next(l for l in geometria['linhas'] if l['letra'] == 'L')
        perto_do_min = projetar(linha['pontos'][0]) + Vector((5.0, 0.0))
        alvo = addon.hud._acertar_linhas_hud(geometria, perto_do_min, projetar, cantos=False)
        self.assertEqual((alvo['tipo'], alvo['lado']), ('gavetas', 'min'))
        esquerda = self.pecas(G.gavetas_do_grupo(grupo)[0], 'FRENTE')[0].matrix_world.translation.x \
            - self.pecas(G.gavetas_do_grupo(grupo)[0], 'FRENTE')[0].chapa_largura_mm / 2000.0
        addon.hud._aplicar_valor_hud(bpy.context, alvo, 700.0)
        self.assertAlmostEqual(addon.hud._valor_hud(alvo), 700.0, places=3)
        frente = self.pecas(G.gavetas_do_grupo(grupo)[0], 'FRENTE')[0]
        self.assertAlmostEqual(frente.matrix_world.translation.x
                               - frente.chapa_largura_mm / 2000.0, esquerda, places=5)
        self.assertIsNone(G.aplicar(bpy.context, grupo, ('P',), 400.0))
        self.assertEqual(grupo[G.CHAVE_TRILHO_MM], 350.0)

    def test_tres_pontos_com_alt_refazem_o_vao(self):
        grupo = self.gavetas()
        cima_esq, baixo_dir, fundo = G.pontos_editaveis(grupo)
        eixos = grupo.matrix_world.to_3x3()
        novo = cima_esq + eixos.col[0] * 0.05 - eixos.col[2] * 0.1
        self.assertIsNone(G._aplicar_ponto(grupo, 0, novo))
        largura, altura, _p = G.medidas(grupo)
        self.assertAlmostEqual(largura, 714.0, places=3)
        self.assertAlmostEqual(altura, 564.0, places=3)
        self.assertIsNone(G._aplicar_ponto(grupo, 2, G.pontos_editaveis(grupo)[2]
                                           - eixos.col[1] * 0.1))
        self.assertAlmostEqual(G.medidas(grupo)[2], 460.0, places=3)

    def test_puxador_de_uma_gaveta_ou_de_todas(self):
        grupo = self.gavetas()
        gavetas = G.gavetas_do_grupo(grupo)
        G.selecionar(bpy.context, self.pecas(gavetas[1], 'FRENTE')[0], 'GAVETA')
        self.assertIsNone(G.trocar_puxador(bpy.context, 'ALCA'))
        tipos = [G.gavetas_do_grupo(grupo)[i].get(G.CHAVE_PUXADOR) for i in range(3)]
        self.assertEqual(tipos, ['PERFIL', 'ALCA', 'PERFIL'])
        G.selecionar(bpy.context, grupo, 'GRUPO')
        self.assertIsNone(G.trocar_puxador(bpy.context, 'BORDA'))
        tipos = {g.get(G.CHAVE_PUXADOR) for g in G.gavetas_do_grupo(grupo)}
        self.assertEqual(tipos, {'BORDA'})
        # o material das frentes: a pintura pega frentes e caixas
        pecas = addon.materiais.pecas_dos_alvos([grupo])
        self.assertEqual(len(pecas), 3 * 6)

    def test_aba_gavetas_e_campos_editaveis(self):
        cena = bpy.context.scene
        cena.cabinet_aba = 'GAVETAS'
        widgets = addon.gaveta._widgets_gaveta(bpy.context, 480, 1400)
        self.assertTrue(any(v[5] and v[5][0] == 'gavetas' for v in widgets))
        self.assertIn('Gavetas', [v[4] for v in widgets if v[5] and v[5][0] == 'aba'])
        grupo = self.gavetas()
        G.selecionar(bpy.context, grupo, 'GRUPO')
        widgets = addon.gaveta._widgets_gaveta(bpy.context, 480, 1400)
        acoes = [v[5] for v in widgets if v[5]]
        self.assertTrue(any(a[0] == 'contador' and a[1] == 'gavetas_quantidade' for a in acoes))
        self.assertTrue(any(a[0] == 'escolha' and a[1] == 'gavetas_trilho' for a in acoes))
        self.assertTrue(any(a[0] == 'escolha' and a[5] == addon.gaveta.ALVO_PUXADOR_GAVETAS
                            for a in acoes if len(a) > 5))
        medidas = {a[2] for a in acoes if a[0] == 'medida' and a[1] == 'gavetas'}
        self.assertTrue({'largura', 'altura', 'profundidade_mm', 'folga_frontal_mm',
                         'entre_gavetas_mm', 'recuo_mm'} <= medidas, medidas)
        # os campos chegam nas gavetas pelos mesmos caminhos da porta
        ev = addon.gaveta_eventos
        self.assertIsNone(ev.aplicar_medida(bpy.context, 'gavetas', grupo.name,
                                            'recuo_mm', 0.02))
        self.assertEqual(G.parametros(grupo)['recuo_mm'], 20.0)
        self.assertIsNone(ev._aplicar_contador(
            bpy.context, ('contador', 'gavetas_quantidade', 3, 1, 10, grupo.name), 4))
        self.assertEqual(len(G.gavetas_do_grupo(grupo)), 4)
        # os operadores registrados (eventos de verdade no gui_interacao)
        for nome in ('OBJECT_OT_criar_gavetas', 'OBJECT_OT_abrir_gaveta',
                     'OBJECT_OT_arrastar_ponto_gaveta', 'VIEW3D_GT_slider_gaveta',
                     'VIEW3D_GGT_slider_gaveta'):
            self.assertIn(nome, [c.__name__ for c in addon.CLASSES])


    def test_frente_curva_e_alturas_em_proporcao(self):
        # Promob: o gaveteiro de canto tem frente em ARCO e frentes de
        # alturas diferentes -- as nossas gavetas ganham as duas coisas
        grupo = self.gavetas(frente_curva_mm=60.0, proporcoes=[2.0, 1.0, 1.0],
                             puxador='NENHUM')
        frentes = [G.frente_da_gaveta(g) for g in G.gavetas_do_grupo(grupo)]
        alturas = [f.chapa_comprimento_mm for f in frentes]
        self.assertAlmostEqual(alturas[0] / alturas[1], 2.0, places=3)
        self.assertAlmostEqual(alturas[1], alturas[2], places=3)
        frente = frentes[0]
        # a malha do arco (`_chapas._malha_arco`): a corda e' a largura da
        # frente reta e a flecha vai para FORA (Z+ local = -Y do modulo)
        self.assertGreater(len(frente.data.vertices), 8)
        zs = [v.co.z * 1000.0 for v in frente.data.vertices]
        xs = [v.co.x * 1000.0 for v in frente.data.vertices]
        self.assertAlmostEqual(max(zs), 18.0 / 2 + 60.0, places=2)
        self.assertAlmostEqual(max(xs) - min(xs), frente.chapa_largura_mm, places=2)
        # outra quantidade: as proporcoes saem (alturas iguais)
        self.assertIsNone(G.editar(bpy.context, grupo, 'quantidade', 2))
        self.assertNotIn('proporcoes', grupo[G.CHAVE_PARAMETROS])
        a, b = [G.frente_da_gaveta(g).chapa_comprimento_mm for g in G.gavetas_do_grupo(grupo)]
        self.assertAlmostEqual(a, b, places=3)
        # curva 0 = reta de novo (a caixa padrao)
        self.assertIsNone(G.editar(bpy.context, grupo, 'frente_curva_mm', 0.0))
        self.assertEqual(len(G.frente_da_gaveta(G.gavetas_do_grupo(grupo)[0]).data.vertices), 8)
        # o campo "Curva" esta' na secao Frente da aba
        G.selecionar(bpy.context, grupo, 'GRUPO')
        bpy.context.scene.cabinet_aba = 'GAVETAS'
        acoes = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 480, 1400) if v[5]]
        self.assertTrue(any(a[0] == 'medida' and a[2] == 'frente_curva_mm' for a in acoes))

addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestGavetas)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de gavetas')
