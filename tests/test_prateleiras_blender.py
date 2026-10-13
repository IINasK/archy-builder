"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_prateleiras_blender.py

Prateleiras internas (pedido do usuario): grupo de prateleiras num vao do
modulo, criado como as gavetas (2 cliques na diagonal, scroll = quantas,
mouse = profundidade), com aba propria: quantidade, espessura, o
espacamento entre elas e o de CADA uma (na aba e na HUD).

O assistente com eventos de verdade esta' em `gui_interacao.py`.
"""
import os
import sys
import unittest

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

P = addon.prateleiras


class TestPrateleiras(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for colecao in list(bpy.data.collections):
            bpy.data.collections.remove(colecao)
        camada = bpy.context.view_layer
        camada.active_layer_collection = camada.layer_collection
        P.esquecer()
        # balcao 800 x 700 x 560, chapa 18: o vao de dentro e' 764 x 664
        self.conj = addon.modulos.criar_armario(bpy.context, 'Balcao', 800, 700, 560,
                                                fundo=False)
        bpy.context.view_layer.update()

    def prateleiras(self, **p):
        padrao = dict(quantidade=3, espessura_mm=18.0, profundidade_mm=540.0)
        padrao.update(p)
        return P.criar_prateleiras(bpy.context, self.conj, (18, 18, 18, 18, 0), padrao)

    def alturas(self, grupo):
        """z de baixo de cada prateleira, em mm, no grupo."""
        inversa = grupo.matrix_world.inverted()
        return [round((inversa @ o.matrix_world.translation).z * 1000.0
                      - o.chapa_espessura_mm / 2.0, 3) for o in P.prateleiras_do_grupo(grupo)]

    def test_calculo_igual_e_livre(self):
        p = dict(P.PARAMETROS_PADRAO, quantidade=3, espessura_mm=18.0, profundidade_mm=500.0)
        dados = P.calcular(764.0, 664.0, p)
        # 664 - 3 x 18 = 610 em 4 vaos iguais
        self.assertEqual([round(v, 3) for v in dados['vaos']], [152.5] * 4)
        self.assertAlmostEqual(dados['prateleiras'][1][4], 152.5 * 2 + 18.0)
        # LIVRE: o de cima e' o que sobra
        livre = dict(p, espacamento='LIVRE', vaos_mm=[100.0, 200.0, 50.0])
        self.assertAlmostEqual(P.vaos(664.0, livre)[-1], 610.0 - 350.0)
        with self.assertRaisesRegex(ValueError, 'passam do topo'):
            P.vaos(664.0, dict(livre, vaos_mm=[300.0, 300.0, 100.0]))
        with self.assertRaisesRegex(ValueError, 'nao cabem'):
            P.calcular(764.0, 664.0, dict(p, quantidade=20, espessura_mm=40.0))
        with self.assertRaisesRegex(ValueError, 'rasa'):
            P.calcular(764.0, 664.0, dict(p, recuo_mm=480.0))

    def test_mover_um_vao_anda_so_uma_prateleira(self):
        p = dict(P.PARAMETROS_PADRAO, quantidade=3, espessura_mm=18.0)
        # vao 2 (entre a 1a e a 2a) em 100: so' a 2a desce; o 3o cede
        self.assertEqual([round(v, 3) for v in P.mover_vao(664.0, p, 1, 100.0)],
                         [152.5, 100.0, 205.0])
        # o do topo em 100: a mais alta sobe (o vao de baixo dela cresce)
        self.assertEqual([round(v, 3) for v in P.mover_vao(664.0, p, 3, 100.0)],
                         [152.5, 152.5, 205.0])
        # o "Acima" da 2a: anda ELA (o vao de baixo dela cede)
        self.assertEqual([round(v, 3) for v in P.mover_vao(664.0, p, 2, 100.0, de_baixo=True)],
                         [152.5, 205.0, 100.0])
        with self.assertRaisesRegex(ValueError, 'Nao cabe'):
            P.mover_vao(664.0, p, 1, 400.0)

    def test_cria_chapas_no_vao_sem_mexer_no_modulo(self):
        antes = addon.modulos.medir_conjunto(self.conj)
        chapas = len(addon.modulos._chapas_do_conjunto(self.conj))
        grupo = self.prateleiras(folga_lateral_mm=1.0, recuo_mm=20.0)
        prateleiras = P.prateleiras_do_grupo(grupo)
        self.assertEqual(len(prateleiras), 3)
        self.assertEqual(grupo.parent, self.conj)
        for o in prateleiras:
            self.assertIn(addon.chapas.MARCA_CHAPA, o)
            self.assertAlmostEqual(o.chapa_largura_mm, 764.0 - 2.0, places=3)
            self.assertAlmostEqual(o.chapa_comprimento_mm, 540.0 - 20.0, places=3)
            self.assertAlmostEqual(o.chapa_espessura_mm, 18.0, places=3)
        self.assertEqual(self.alturas(grupo), [152.5, 323.0, 493.5])
        # o modulo nao ganha chapa nem muda de medida
        self.assertEqual(len(addon.modulos._chapas_do_conjunto(self.conj)), chapas)
        for a, b in zip(antes, addon.modulos.medir_conjunto(self.conj)):
            self.assertAlmostEqual(a, b, places=3)
        # o orcamento conta as prateleiras; a pintura pega todas
        self.assertEqual(addon.orcamento._pecas_internas(self.conj)[0], 3)
        self.assertEqual(len(addon.materiais.pecas_dos_alvos([grupo])), 3)

    def test_editar_na_mesma_chapa_e_desfaz_o_que_nao_cabe(self):
        grupo = self.prateleiras()
        segunda = P.prateleiras_do_grupo(grupo)[1]
        nome = segunda.name
        self.assertIsNone(P.editar(bpy.context, grupo, 'espessura_mm', 25.0))
        self.assertEqual(P.prateleiras_do_grupo(grupo)[1].name, nome)   # a mesma
        self.assertAlmostEqual(segunda.chapa_espessura_mm, 25.0, places=3)
        # entre todas: LIVRE com o mesmo vao; mais uma continua com ele
        self.assertIsNone(P.editar(bpy.context, grupo, 'entre_mm', 120.0))
        self.assertEqual(self.alturas(grupo), [120.0, 265.0, 410.0])
        self.assertIsNone(P.editar(bpy.context, grupo, 'prateleiras_quantidade', 4))
        self.assertEqual(self.alturas(grupo), [120.0, 265.0, 410.0, 555.0])
        # 5 a 120 nao cabem: volta a dividir igual
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 5))
        self.assertEqual(P.parametros(grupo)['espacamento'], 'IGUAL')
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 5)
        # nao cabe: devolve o erro e fica como estava
        erro = P.editar(bpy.context, grupo, 'espessura_mm', 200.0)
        self.assertIn('nao cabem', erro)
        self.assertEqual(P.parametros(grupo)['espessura_mm'], 25.0)
        # LIVRE parte dos vaos de hoje; IGUAL divide de novo
        antes = self.alturas(grupo)
        self.assertIsNone(P.editar(bpy.context, grupo, 'espacamento', 'LIVRE'))
        self.assertEqual(self.alturas(grupo), antes)
        self.assertIsNone(P.editar(bpy.context, grupo, 'vao_0', 50.0))
        self.assertEqual(self.alturas(grupo)[0], 50.0)
        self.assertEqual(self.alturas(grupo)[1:], antes[1:])
        self.assertIsNone(P.editar(bpy.context, grupo, 'espacamento', 'IGUAL'))
        self.assertEqual(self.alturas(grupo), antes)

    def test_modulo_que_muda_de_medida_leva_as_prateleiras(self):
        grupo = self.prateleiras()
        self.conj.conj_largura_mm = 1000.0          # dispara o redimensionar
        bpy.context.view_layer.update()
        self.assertAlmostEqual(P.medidas(grupo)[0], 964.0, places=2)
        self.assertAlmostEqual(P.prateleiras_do_grupo(grupo)[0].chapa_largura_mm, 964.0, places=2)

    def test_profundidade_para_no_fundo(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Alto', 600, 900, 400)
        bpy.context.view_layer.update()
        fundo = next(c for c in addon.modulos._chapas_do_conjunto(conj)
                     if addon.chapas.MARCA_FUNDO in c)
        inversa = conj.matrix_world.inverted()
        frente_do_fundo = min((inversa @ (fundo.matrix_world @ v.co)).y * 1000.0
                              for v in fundo.data.vertices)
        lo, _hi = addon.gavetas._limites(conj)
        ponto = conj.matrix_world @ (Vector((0.0, lo.y, 300.0)) / 1000.0)
        self.assertAlmostEqual(P.profundidade_ate_o_fundo(conj, ponto),
                               frente_do_fundo - lo.y, places=2)
        self.assertLess(P.profundidade_ate_o_fundo(conj, ponto), 400.0 - 15.0)

    def test_selecao_hud_e_vaos_editaveis(self):
        grupo = self.prateleiras()
        segunda = P.prateleiras_do_grupo(grupo)[1]
        self.assertEqual(addon.selecao._aba_da_selecao(segunda), 'PRATELEIRAS')
        P.selecionar(bpy.context, segunda, 'GRUPO')
        self.assertEqual(bpy.context.view_layer.objects.active, grupo)
        self.assertFalse(self.conj.select_get())
        itens = addon.hud._itens_da_selecao(bpy.context)
        self.assertEqual([(o.name, modo) for o, modo, _c in itens],
                         [(grupo.name, 'PRATELEIRAS')])
        geometria = addon.hud._geometria_do_item(*itens[0])
        vaos = [l for l in geometria['linhas'] if l.get('vao')]
        self.assertEqual([l['face'] for l in vaos], [('V', k) for k in range(4)])
        self.assertEqual({l['letra'] for l in geometria['linhas'] if not l.get('vao')},
                         {'L', 'A', 'P'})
        # a linha do 2o vao: arrastar/digitar anda so' a 2a prateleira
        self.assertAlmostEqual(addon.hud._valor_hud(vaos[1]), 152.5, places=3)
        addon.hud._aplicar_valor_hud(bpy.context, vaos[1], 100.0)
        self.assertEqual(self.alturas(grupo), [152.5, 270.5, 493.5])
        # o Esc do arraste devolve os parametros
        estado = addon.hud._estado_arraste_hud(bpy.context, vaos[1])
        addon.hud._aplicar_valor_hud(bpy.context, vaos[1], 60.0)
        addon.hud._restaurar_arraste_hud(bpy.context, estado)
        self.assertEqual(self.alturas(grupo), [152.5, 270.5, 493.5])
        # duplo clique: so' ela
        P.selecionar(bpy.context, segunda, 'PRATELEIRA')
        self.assertEqual(bpy.context.view_layer.objects.active, segunda)
        self.assertEqual(len(addon.hud._itens_da_selecao(bpy.context)), 1)

    def test_aba_prateleiras_e_campos_editaveis(self):
        cena = bpy.context.scene
        cena.cabinet_aba = 'PRATELEIRAS'
        widgets = addon.gaveta._widgets_gaveta(bpy.context, 480, 1400)
        self.assertTrue(any(v[5] and v[5][0] == 'prateleiras' for v in widgets))
        self.assertIn('Prateleiras', [v[4] for v in widgets if v[5] and v[5][0] == 'aba'])
        grupo = self.prateleiras()
        P.selecionar(bpy.context, grupo, 'GRUPO')
        acoes = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 480, 1400) if v[5]]
        self.assertTrue(any(a[0] == 'contador' and a[1] == 'prateleiras_quantidade'
                            for a in acoes))
        self.assertTrue(any(a[0] == 'escolha' and a[1] == 'prateleiras_espacamento'
                            for a in acoes))
        medidas = {a[2] for a in acoes if a[0] == 'medida' and a[1] == 'prateleiras'}
        self.assertTrue({'largura', 'altura', 'profundidade_mm', 'espessura_mm', 'recuo_mm',
                         'folga_lateral_mm', 'entre_mm', 'vao_0', 'vao_3'} <= medidas, medidas)
        # uma so' (duplo): os dois vaos dela
        segunda = P.prateleiras_do_grupo(grupo)[1]
        P.selecionar(bpy.context, segunda, 'PRATELEIRA')
        acoes = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 480, 1400) if v[5]]
        rotulos = {a[3]: a[2] for a in acoes if a[0] == 'medida' and a[1] == 'prateleiras'}
        self.assertEqual((rotulos.get('Abaixo'), rotulos.get('Acima')), ('vao_1', 'acima_1'))
        self.assertNotIn('Entre prateleiras', rotulos)
        # os campos chegam pelos mesmos caminhos da porta/gavetas
        ev = addon.gaveta_eventos
        self.assertIsNone(ev.aplicar_medida(bpy.context, 'prateleiras', segunda.name,
                                            'acima_1', 0.1))
        self.assertEqual(self.alturas(grupo), [152.5, 375.5, 493.5])
        self.assertIsNone(ev._aplicar_contador(
            bpy.context, ('contador', 'prateleiras_quantidade', 3, 1, 20, grupo.name), 2))
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 2)
        self.assertIn('OBJECT_OT_criar_prateleiras', [c.__name__ for c in addon.CLASSES])
        # so' 2 pontos (pedido do usuario): o clique da quantidade ja' cria,
        # sem a etapa de profundidade das gavetas
        self.assertNotIn('PROFUNDIDADE', P.OBJECT_OT_criar_prateleiras.RECADOS)
        self.assertIsNot(P.OBJECT_OT_criar_prateleiras._depois_da_quantidade,
                         addon.gavetas.AssistenteDoVao._depois_da_quantidade)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestPrateleiras)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de prateleiras')
