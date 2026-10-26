"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_prateleiras_blender.py

Prateleiras internas (pedido do usuario): grupo de prateleiras num vao do
modulo, criado como as gavetas (2 cliques na diagonal, scroll = quantas,
mouse = profundidade), com aba propria: quantidade, espessura, o
espacamento entre elas e o de CADA uma (na aba e na HUD).

O assistente com eventos de verdade esta' em `gui_interacao.py`.
"""
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

P = addon.prateleiras


class TestPrateleiras(unittest.TestCase):
    def test_vestir_mesma_caixa_nao_reescreve_pose_medidas_ou_malha(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Montagem mantida', 600, 800, 550)
        grupo = addon.prateleiras.criar_prateleiras(bpy.context, conj, (18, 18, 18, 18, 0), dict(quantidade=2))
        obj = addon.prateleiras.prateleiras_do_grupo(grupo)[0]
        largura, altura, _matriz = addon.prateleiras.vao(grupo)
        caixa = addon.prateleiras.calcular(largura, altura, addon.prateleiras.parametros(grupo))['prateleiras'][0]
        matriz, malha = obj.matrix_basis.copy(), obj.data
        self.assertFalse(addon.prateleiras._vestir(obj, caixa))
        self.assertEqual(obj.matrix_basis, matriz)
        self.assertIs(obj.data, malha)

    def test_vestir_detecta_pose_alterada_sem_reconstruir_malha(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Pose alterada', 600, 800, 550)
        grupo = addon.prateleiras.criar_prateleiras(bpy.context, conj, (18, 18, 18, 18, 0), dict(quantidade=2))
        obj = addon.prateleiras.prateleiras_do_grupo(grupo)[0]
        largura, altura, _matriz = addon.prateleiras.vao(grupo)
        caixa = addon.prateleiras.calcular(largura, altura, addon.prateleiras.parametros(grupo))['prateleiras'][0]
        matriz, malha = obj.matrix_basis.copy(), obj.data
        obj.location.z += .01
        self.assertTrue(addon.prateleiras._vestir(obj, caixa))
        self.assertEqual(obj.matrix_basis, matriz)
        self.assertIs(obj.data, malha)

    def test_quantidade_local_subdivide_so_entre_os_apoios_e_reutiliza_a_familia(self):
        grupo = self.prateleiras()
        baixo, alvo, cima = P.prateleiras_do_grupo(grupo)
        antes = [(o.matrix_world.copy(), self.geometria(o), o.data) for o in (baixo, cima)]
        P.selecionar(bpy.context, alvo, 'PRATELEIRA')
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 2))
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 4)
        for obj, (matriz, geometria, malha) in zip((baixo, cima), antes):
            self.assertEqual(obj.matrix_world, matriz)
            self.assertEqual(self.geometria(obj), geometria)
            self.assertEqual(obj.data, malha)
        detalhe = P.detalhamento(grupo, alvo)
        self.assertEqual(detalhe['quantidade'], 2)
        self.assertAlmostEqual(detalhe['baixo'], 170.5, places=3)
        self.assertAlmostEqual(detalhe['cima'], 493.5, places=3)
        for g in detalhe['vaos']:
            self.assertAlmostEqual(g, (323 - 36) / 3, places=3)
        copia = detalhe['unidades'][1]
        P.selecionar(bpy.context, copia, 'PRATELEIRA')
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 3))
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 5)
        self.assertEqual(P.detalhamento(grupo, copia)['quantidade'], 3)
        self.assertEqual(P.individual_ativo(bpy.context, grupo), copia)
        detalhe = P.detalhamento(grupo, copia)
        apoio = cima.matrix_world.copy()
        self.assertIsNone(P.editar(bpy.context, grupo, 'vao_%d' % (detalhe['ultimo'] + 1), 40))
        self.assertEqual(cima.matrix_world, apoio)
        self.assertEqual(bpy.ops.object.cabinet_alinhar_prateleiras(), {'FINISHED'})
        for g in P.detalhamento(grupo, copia)['vaos']:
            self.assertAlmostEqual(g, (323 - 54) / 4, places=3)
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 1))
        self.assertEqual(P.detalhamento(grupo, copia)['unidades'], [copia])
        self.assertAlmostEqual(self.alturas(grupo)[1], 323, places=3)
        self.assertEqual(bpy.context.object, copia)

    def test_selecao_local_tem_contador_e_caixa_limitados_e_grupo_tem_total(self):
        grupo = self.prateleiras()
        alvo = P.prateleiras_do_grupo(grupo)[1]
        bpy.context.scene.cabinet_aba = 'PRATELEIRAS'
        for nivel, quantidade, limites, nomes in (
                ('PRATELEIRA', 1, (170.5, 493.5), ['E2', 'E3']),
                ('GRUPO', 3, (0., 664.), ['E1', 'E2', 'E3', 'E4'])):
            P.selecionar(bpy.context, alvo, nivel)
            widgets = addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)
            contador, = [w[5] for w in widgets if w[5] and w[5][:2] ==
                          ('contador', 'prateleiras_quantidade')]
            self.assertEqual(contador[2], quantidade)
            campos = [w[5] for w in widgets if w[5] and w[5][0] == 'medida'
                      and w[5][1] == 'prateleiras' and w[5][2].startswith('vao_')]
            self.assertEqual([c[3] for c in campos], nomes)
            cantos, _linhas = P.linhas_hud(grupo, [])
            zs = [(grupo.matrix_world.inverted() @ c).z * 1000 for c in cantos]
            self.assertAlmostEqual(min(zs), limites[0], places=2)
            self.assertAlmostEqual(max(zs), limites[1], places=2)

    def test_detalhamento_preserva_quatro_gavetas_e_herda_madeira_em_modulo_girado(self):
        self.conj.rotation_euler = (.2, -.3, .6)
        bpy.context.view_layer.update()
        gavetas = addon.gavetas.criar_gavetas(bpy.context, self.conj, (18,18,18,300,0),
                                             dict(quantidade=4, profundidade_mm=400))
        grupo = self.prateleiras(quantidade=2, espacamento='LIVRE', vaos_mm=[400., 100.])
        apoio, alvo = P.prateleiras_do_grupo(grupo)
        P.selecionar(bpy.context, alvo, 'PRATELEIRA')
        self.recortar(alvo)
        P.editar(bpy.context, grupo, 'profundidade_mm', 420)
        alvo.modifiers.new('Acabamento local', 'BEVEL').width = .002
        mat = bpy.data.materials.new('Madeira do detalhe')
        alvo.data.materials.append(mat)
        geometria = self.geometria(alvo)
        malha = alvo.data
        preservados = [apoio, *gavetas.children_recursive]
        antes = [(o, o.matrix_world.copy(), o.data, self.geometria(o) if o.type == 'MESH' else None)
                 for o in preservados]
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 2))
        for o, mundo, dados, forma in antes:
            self.assertEqual(o.matrix_world, mundo)
            self.assertEqual(o.data, dados)
            if forma is not None:
                self.assertEqual(self.geometria(o), forma)
        detalhe = P.detalhamento(grupo, alvo)
        self.assertAlmostEqual(detalhe['baixo'], 418, places=3)
        self.assertEqual(alvo.data, malha)
        self.assertEqual(len({o['chapa_uid'] for o in detalhe['unidades']}), 2)
        for o in detalhe['unidades']:
            self.assertEqual(self.geometria(o), geometria)
            self.assertEqual(o.data.materials[0], mat)
            self.assertAlmostEqual(o.modifiers[0].width, .002)
        self.assertIsNone(P.editar(bpy.context, grupo, 'espessura_mm', 25))
        for o in detalhe['unidades']:
            self.assertAlmostEqual(o.chapa_espessura_mm, 25)
        self.assertAlmostEqual(apoio.chapa_espessura_mm, 18)

    def test_contador_local_digitado_arrastado_e_esc_mantem_escopo(self):
        grupo = self.prateleiras()
        alvo = P.prateleiras_do_grupo(grupo)[1]
        P.selecionar(bpy.context, alvo, 'PRATELEIRA')
        bpy.context.scene.cabinet_aba = 'PRATELEIRAS'
        acao, = [w[5] for w in addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)
                  if w[5] and w[5][:2] == ('contador', 'prateleiras_quantidade')]
        self.assertEqual(acao[2], 1)
        self.assertEqual(acao[5], alvo.name)
        ctx = SimpleNamespace(mode='OBJECT', screen=bpy.context.screen,
                              area=SimpleNamespace(tag_redraw=lambda: None))
        ev = addon.gaveta_eventos
        for cancelar in (True, False):
            op = SimpleNamespace(_campo=dict(acao=acao, x0=0, arrastou=False, valor=1, meio=20))
            self.assertEqual(ev.OBJECT_OT_interagir_gaveta._modal_campo(op, ctx,
                SimpleNamespace(type='MOUSEMOVE', mouse_region_x=24)), {'RUNNING_MODAL'})
            self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 3)
            widgets = addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)
            self.assertTrue(any(w[4] == '2' and w[5] == acao for w in widgets))
            evento = SimpleNamespace(type='ESC' if cancelar else 'LEFTMOUSE',
                                     value='PRESS' if cancelar else 'RELEASE')
            ev.OBJECT_OT_interagir_gaveta._modal_campo(op, ctx, evento)
            self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 3 if cancelar else 4)
        self.assertIsNone(ev.aplicar_medida(bpy.context, 'contador', alvo.name,
                                           'prateleiras_quantidade', 1))
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 3)

    def test_detalhamento_inviavel_nao_altera_cena_e_zero_remove_so_o_trecho(self):
        grupo = self.prateleiras()
        baixo, alvo, cima = P.prateleiras_do_grupo(grupo)
        P.selecionar(bpy.context, alvo, 'PRATELEIRA')
        P.editar(bpy.context, grupo, 'espessura_mm', 100)
        antes = P.copia(grupo)
        mundos = [o.matrix_world.copy() for o in (baixo, alvo, cima)]
        self.assertIsNotNone(P.editar(bpy.context, grupo, 'quantidade', 10))
        self.assertEqual(P.copia(grupo), antes)
        self.assertEqual([o.matrix_world for o in (baixo, alvo, cima)], mundos)
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 3)
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 0))
        self.assertEqual(P.prateleiras_do_grupo(grupo), [baixo, cima])
        self.assertEqual([o.matrix_world for o in (baixo, cima)], [mundos[0], mundos[2]])

    def test_undo_redo_de_detalhar_preserva_vinculo_e_apoios(self):
        addon.eventos._fim_do_desfazer()
        self.addCleanup(addon.eventos._fim_do_desfazer)
        grupo = self.prateleiras()
        alvo = P.prateleiras_do_grupo(grupo)[1]
        nome, nome_alvo = grupo.name, alvo.name
        P.selecionar(bpy.context, alvo, 'PRATELEIRA')
        bpy.ops.ed.undo_push(message='Antes de subdividir')
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 2))
        depois = self.alturas(grupo)
        bpy.ops.ed.undo_push(message='Trecho subdividido')
        bpy.ops.ed.undo()
        grupo, alvo = bpy.data.objects[nome], bpy.data.objects[nome_alvo]
        self.assertEqual(self.alturas(grupo), [152.5, 323., 493.5])
        self.assertNotIn(P.CHAVE_DETALHAMENTO, alvo)
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        grupo, alvo = bpy.data.objects[nome], bpy.data.objects[nome_alvo]
        self.assertEqual(self.alturas(grupo), depois)
        self.assertEqual(P.detalhamento(grupo, alvo)['quantidade'], 2)
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 3))
        self.assertEqual(P.detalhamento(grupo, alvo)['quantidade'], 3)

    def test_detalhamento_gravado_em_blend_reabre_com_escopo_local(self):
        grupo = self.prateleiras()
        alvo = P.prateleiras_do_grupo(grupo)[1]
        P.selecionar(bpy.context, alvo, 'PRATELEIRA')
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 2))
        uid = alvo[P.CHAVE_DETALHAMENTO]
        with tempfile.TemporaryDirectory(prefix='cabinet_detalhamento_') as pasta:
            caminho = os.path.join(pasta, 'detalhamento.blend')
            bpy.data.libraries.write(caminho, {self.conj, *self.conj.children_recursive})
            with bpy.data.libraries.load(caminho, link=False) as (origem, destino):
                destino.objects = list(origem.objects)
            for obj in destino.objects:
                if obj is not None:
                    bpy.context.scene.collection.objects.link(obj)
            bpy.context.view_layer.update()
            novo = next(o for o in destino.objects if o is not None and P.MARCA_GRUPO in o)
            folha = next(o for o in P.prateleiras_do_grupo(novo) if o.get(P.CHAVE_DETALHAMENTO) == uid)
            P.selecionar(bpy.context, folha, 'PRATELEIRA')
            self.assertEqual(P.detalhamento(novo, folha)['quantidade'], 2)
            self.assertIsNone(P.editar(bpy.context, novo, 'quantidade', 3))
            self.assertEqual(P.detalhamento(novo, folha)['quantidade'], 3)
            self.assertEqual(P.detalhamento(grupo, alvo)['quantidade'], 2)

    def test_excluir_qualquer_unidade_preserva_posicoes_e_recalcula_hud_e_menu(self):
        for apagada in (2, 1, 0):
            with self.subTest(apagada=apagada):
                grupo = self.prateleiras()
                atuais = P.prateleiras_do_grupo(grupo)
                restantes = [o for i, o in enumerate(atuais) if i != apagada]
                antes = [(o.matrix_world.copy(), self.geometria(o), o.data)
                         for o in restantes]
                bpy.data.objects.remove(atuais[apagada], do_unlink=True)
                P.selecionar(bpy.context, grupo, 'GRUPO')
                addon.eventos.verificar_periodicamente()
                self.assertEqual(P.parametros(grupo)['quantidade'], 2)
                self.assertEqual([o[P.CHAVE_INDICE] for o in restantes], [0, 1])
                for obj, (matriz, geometria, malha) in zip(restantes, antes):
                    self.assertEqual(obj.matrix_world, matriz)
                    self.assertEqual(self.geometria(obj), geometria)
                    self.assertEqual(obj.data, malha)
                _, altura, _ = P.vao(grupo)
                esperado = [152.5, 152.5, 323.0] if apagada == 2 else (
                    [152.5, 323.0, 152.5] if apagada == 1 else [323.0, 152.5, 152.5])
                for a, b in zip(P.vaos(altura, P.parametros(grupo)), esperado):
                    self.assertAlmostEqual(a, b, places=3)
                _cantos, linhas = P.linhas_hud(grupo, restantes)
                vaos = [l for l in linhas if l.get('vao')]
                self.assertEqual(len(vaos), 3)
                for linha, mm in zip(vaos, esperado):
                    self.assertAlmostEqual((linha['pontos'][1] - linha['pontos'][0]).length * 1000,
                                           mm, places=3)
                bpy.context.scene.cabinet_aba = 'PRATELEIRAS'
                widgets = addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)
                contador, = [w for w in widgets if w[5] and w[5][:2] ==
                             ('contador', 'prateleiras_quantidade')]
                self.assertEqual(contador[5][2], 2)
                with patch.object(P, 'montar', side_effect=AssertionError('Recriou na sincronizacao')):
                    addon.eventos.verificar_periodicamente()
                self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 2)

    def test_exclusao_remapeia_ajustes_individuais_e_descarta_encaixe_antigo(self):
        grupo = self.prateleiras()
        self.assertIsNone(P.editar_individual(bpy.context, grupo, 2, 'recuo_mm', 35))
        self.assertIsNone(P.editar_individual(bpy.context, grupo, 2, 'espessura_mm', 25))
        P.atualizar_do_conjunto(self.conj)
        self.assertIn(P.CHAVE_ENCAIXE, grupo)
        primeira, meio, ultima = P.prateleiras_do_grupo(grupo)
        z = ultima.matrix_world.translation.z
        bpy.data.objects.remove(meio, do_unlink=True)
        # O resize pode chegar antes do tique de seguranca.
        P.atualizar_do_conjunto(self.conj)
        self.assertEqual(P.parametros(grupo)['quantidade'], 2)
        modelo = P.parametros_individuais(P.parametros(grupo), 1)
        self.assertEqual(modelo['recuo_mm'], 35)
        self.assertEqual(modelo['espessura_mm'], 25)
        self.assertAlmostEqual(ultima.matrix_world.translation.z, z, places=6)
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 2)
        self.assertIsNone(P.editar(bpy.context, grupo, 'vao_1', 200))
        self.assertEqual(ultima.chapa_espessura_mm, 25)
        self.assertEqual(primeira[P.CHAVE_INDICE], 0)

    def test_exclusao_usa_referencial_do_vao_em_modulo_girado(self):
        grupo = self.prateleiras()
        self.conj.rotation_euler = (.3, .2, .6)
        self.conj.location = (2, -1, 3)
        bpy.context.view_layer.update()
        atuais = P.prateleiras_do_grupo(grupo)
        bpy.data.objects.remove(atuais[2], do_unlink=True)
        P.sincronizar_exclusoes_da_cena()
        vaos = P.vaos(P.vao(grupo)[1], P.parametros(grupo))
        for a, b in zip(vaos, (152.5, 152.5, 323)):
            self.assertAlmostEqual(a, b, places=2)

    def test_excluir_todas_mantem_zero_sem_recriar_e_permite_nova_quantidade(self):
        grupo = self.prateleiras()
        for obj in P.prateleiras_do_grupo(grupo):
            bpy.data.objects.remove(obj, do_unlink=True)
        P.selecionar(bpy.context, grupo, 'GRUPO')
        P.sincronizar_exclusoes_da_cena()
        self.assertEqual(P.parametros(grupo)['quantidade'], 0)
        self.assertEqual(P.vaos(664, P.parametros(grupo)), [664])
        self.assertEqual(P.entre(grupo), 0)
        self.assertFalse(P.OBJECT_OT_alinhar_prateleiras.poll(bpy.context))
        self.conj.conj_largura_mm = 900
        self.assertEqual(P.prateleiras_do_grupo(grupo), [])
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 2))
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 2)

    def test_icone_iguala_todos_os_vaos_preservando_malhas_e_ajustes(self):
        grupo = self.prateleiras()
        fonte = P.prateleiras_do_grupo(grupo)[1]
        self.recortar(fonte)
        self.assertIsNone(P.editar_individual(bpy.context, grupo, 1, 'espessura_mm', 25))
        bpy.data.objects.remove(P.prateleiras_do_grupo(grupo)[2], do_unlink=True)
        # O clique tambem precisa absorver exclusao ainda nao vista pelo timer.
        P.selecionar(bpy.context, grupo, 'GRUPO')
        restantes = P.prateleiras_do_grupo(grupo)
        antes = [(o.data, self.geometria(o)) for o in restantes]
        self.assertIn(P.OBJECT_OT_alinhar_prateleiras, addon.CLASSES)
        self.assertEqual(bpy.ops.object.cabinet_alinhar_prateleiras(), {'FINISHED'})
        for o, (malha, geometria) in zip(restantes, antes):
            self.assertEqual(o.data, malha)
            self.assertEqual(self.geometria(o), geometria)
        p = P.parametros(grupo)
        self.assertEqual(p['quantidade'], 2)
        self.assertEqual(p['espacamento'], 'IGUAL')
        self.assertEqual(P.parametros_individuais(p, 1)['espessura_mm'], 25)
        esperado = (664 - 18 - 25) / 3
        for g in P.vaos(664, p):
            self.assertAlmostEqual(g, esperado, places=4)
        self.assertAlmostEqual(self.alturas(grupo)[1], 2 * esperado + 18, places=2)

    def test_centralizar_individual_iguala_so_vaos_vizinhos_e_preserva_madeira(self):
        for quantidade, indice in ((3, 0), (3, 1), (3, 2), (1, 0)):
            with self.subTest(quantidade=quantidade, indice=indice):
                grupo = self.prateleiras(quantidade=quantidade, espacamento='LIVRE',
                                         vaos_mm=[40., 160., 110.][:quantidade])
                unidades = P.prateleiras_do_grupo(grupo)
                alvo = unidades[indice]
                self.recortar(alvo)
                self.assertIsNone(P.editar_individual(
                    bpy.context, grupo, indice, 'espessura_mm', 25))
                P.selecionar(bpy.context, alvo, 'PRATELEIRA')
                antes = [(o.data, self.geometria(o), o.matrix_world.copy()) for o in unidades]
                alturas = self.alturas(grupo)
                altura = P.vao(grupo)[1]
                # Limites sao as faces das vizinhas, ou o limite do vao.
                apoio_baixo = alturas[indice - 1] + 18 if indice else 0
                apoio_cima = alturas[indice + 1] if indice + 1 < quantidade else altura
                esperado = (apoio_baixo + apoio_cima - 25) / 2
                self.assertEqual(bpy.ops.object.cabinet_alinhar_prateleiras(), {'FINISHED'})
                self.assertAlmostEqual(self.alturas(grupo)[indice], esperado, places=3)
                for i, (o, (malha, geometria, matriz)) in enumerate(zip(unidades, antes)):
                    self.assertEqual(o.data, malha)
                    self.assertEqual(self.geometria(o), geometria)
                    if i != indice:
                        self.assertEqual(o.matrix_world, matriz)
                g = P.vaos(altura, P.parametros(grupo))
                self.assertAlmostEqual(g[indice], g[indice + 1], places=5)
                self.assertEqual(bpy.context.object, alvo)
                self.assertEqual(list(bpy.context.selected_objects), [alvo])

    def test_centralizar_individual_absorve_exclusao_e_remapeia_indice(self):
        grupo = self.prateleiras()
        unidades = P.prateleiras_do_grupo(grupo)
        alvo = unidades[2]
        P.selecionar(bpy.context, alvo, 'PRATELEIRA')
        apoio = self.alturas(grupo)[1] + 18
        vizinha = unidades[1]
        antes = vizinha.matrix_world.copy()
        bpy.data.objects.remove(unidades[0], do_unlink=True)
        self.assertEqual(bpy.ops.object.cabinet_alinhar_prateleiras(), {'FINISHED'})
        self.assertEqual(P.parametros(grupo)['quantidade'], 2)
        self.assertEqual(alvo[P.CHAVE_INDICE], 1)
        self.assertEqual(vizinha.matrix_world, antes)
        self.assertAlmostEqual(self.alturas(grupo)[1], (apoio + 664 - 18) / 2, places=3)

    def test_centralizar_individual_undo_redo_restaura_posicao_e_selecao(self):
        # Em background o loop nao executa o timer que libera a guarda.
        self.addCleanup(addon.eventos._fim_do_desfazer)
        grupo = self.prateleiras(espacamento='LIVRE', vaos_mm=[40., 160., 110.])
        alvo = P.prateleiras_do_grupo(grupo)[1]
        nome_grupo, nome_alvo = grupo.name, alvo.name
        P.selecionar(bpy.context, alvo, 'PRATELEIRA')
        antes = self.alturas(grupo)
        bpy.ops.ed.undo_push(message='Prateleira individual antes de centralizar')
        self.assertEqual(bpy.ops.object.cabinet_alinhar_prateleiras(), {'FINISHED'})
        depois = self.alturas(grupo)
        self.assertNotEqual(antes[1], depois[1])
        bpy.ops.ed.undo_push(message='Prateleira individual centralizada')
        bpy.ops.ed.undo()
        self.assertEqual(self.alturas(bpy.data.objects[nome_grupo]), antes)
        self.assertEqual(bpy.context.object.name, nome_alvo)
        bpy.ops.ed.redo()
        self.assertEqual(self.alturas(bpy.data.objects[nome_grupo]), depois)
        self.assertEqual(bpy.context.object.name, nome_alvo)

    def test_secao_espacamento_tem_campos_E_e_botao_sem_sobreposicao_em_tres_larguras(self):
        grupo = self.prateleiras()
        bpy.context.scene.cabinet_aba = 'PRATELEIRAS'
        acao = ('operador', 'object.cabinet_alinhar_prateleiras')
        # Simbolo proprio: o hit-test ocupa o botao inteiro, sem disco
        # nativo por cima que possa conservar uma corrente do pool.
        self.assertIsNone(addon.gaveta_eventos._icone_acao_gaveta(acao))
        for nivel in ('GRUPO', 'PRATELEIRA'):
            P.selecionar(bpy.context, P.prateleiras_do_grupo(grupo)[0], nivel)
            for largura in (190, 320, 480, 482, 564):
                with self.subTest(nivel=nivel, largura=largura):
                    widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1400)
                    icone, = [w for w in widgets if w[5] == acao]
                    contador, = [w for w in widgets if w[5] and w[5][:2] ==
                                  ('contador', 'prateleiras_quantidade')]
                    basicas = [w for w in widgets if w[5] and w[5][0] == 'medida'
                               and w[5][3] in {'Largura', 'Altura', 'Profundidade'}]
                    self.assertEqual(len(basicas), 3 if nivel == 'GRUPO' else 2)
                    for campo in basicas:
                        self.assertAlmostEqual(campo[2], basicas[0][2])
                        self.assertGreater(campo[2], 0)
                    if largura >= 480:
                        self.assertTrue(all(w[1] == contador[1] for w in basicas))
                    self.assertEqual(icone[3], contador[3])
                    self.assertEqual(icone[4], 'Centralizar espacamento')
                    self.assertEqual(icone[0], 12)
                    self.assertEqual(icone[2], largura - 24)
                    self.assertLess(icone[1] + icone[3], contador[1])
                    campos_E = [w for w in widgets if w[5] and w[5][0] == 'medida'
                                and w[5][2].startswith('vao_')]
                    esperado = ['E1', 'E2', 'E3', 'E4'] if nivel == 'GRUPO' else ['E1', 'E2']
                    self.assertEqual([w[5][3] for w in campos_E], esperado)
                    self.assertTrue(all(w[1] + w[3] <= icone[1] for w in campos_E))
                    self.assertFalse(any(w[5] and w[5][:2] == ('escolha', 'prateleiras_espacamento')
                                         for w in widgets))
                    self.assertLessEqual(icone[0] + icone[2], largura - 12)
                    for outro in widgets:
                        if not outro[5] or outro == icone:
                            continue
                        sobrepoe = (min(icone[0] + icone[2], outro[0] + outro[2]) > max(icone[0], outro[0])
                            and min(icone[1] + icone[3], outro[1] + outro[3]) > max(icone[1], outro[1]))
                        self.assertFalse(sobrepoe, outro)

    def test_sincronizacao_nao_escreve_durante_undo_ou_edit_mode(self):
        grupo = self.prateleiras()
        fonte = P.prateleiras_do_grupo(grupo)[-1]
        bpy.data.objects.remove(fonte, do_unlink=True)
        with patch.object(addon.eventos, '_desfazendo', [True]):
            P.sincronizar_exclusoes_da_cena()
        self.assertEqual(P.parametros(grupo)['quantidade'], 3)
        P.selecionar(bpy.context, P.prateleiras_do_grupo(grupo)[0], 'PRATELEIRA')
        bpy.ops.object.mode_set(mode='EDIT')
        P.sincronizar_exclusoes_da_cena()
        self.assertEqual(P.parametros(grupo)['quantidade'], 3)
        bpy.ops.object.mode_set(mode='OBJECT')
        P.sincronizar_exclusoes_da_cena()
        self.assertEqual(P.parametros(grupo)['quantidade'], 2)

    def test_undo_redo_de_excluir_e_alinhar_restaura_quantidade_e_posicoes(self):
        grupo = self.prateleiras()
        nome = grupo.name
        P.selecionar(bpy.context, grupo, 'GRUPO')
        bpy.ops.ed.undo_push(message='Tres prateleiras')
        P.selecionar(bpy.context, P.prateleiras_do_grupo(grupo)[-1], 'PRATELEIRA')
        self.assertEqual(bpy.ops.object.delete(), {'FINISHED'})
        P.selecionar(bpy.context, grupo, 'GRUPO')
        P.sincronizar_exclusoes_da_cena()
        alturas = self.alturas(grupo)
        bpy.ops.ed.undo_push(message='Apagou a de cima')
        bpy.ops.object.cabinet_alinhar_prateleiras()
        bpy.ops.ed.undo_push(message='Igualou vaos')
        bpy.ops.ed.undo()
        grupo = bpy.data.objects[nome]
        self.assertEqual(self.alturas(grupo), alturas)
        self.assertEqual(P.parametros(grupo)['quantidade'], 2)
        bpy.ops.ed.undo()
        grupo = bpy.data.objects[nome]
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 3)
        self.assertEqual(P.parametros(grupo)['quantidade'], 3)
        bpy.ops.ed.redo()
        grupo = bpy.data.objects[nome]
        self.assertEqual(self.alturas(grupo), alturas)
        self.assertEqual(P.parametros(grupo)['quantidade'], 2)

    def test_aviso_de_referencia_segue_mouse_e_troca_de_viewport(self):
        primeira = SimpleNamespace(type='WINDOW', x=300, y=100, width=600, height=500,
                                  as_pointer=lambda: 123)
        segunda = SimpleNamespace(type='WINDOW', x=900, y=100, width=400, height=500,
                                 as_pointer=lambda: 456)
        ctx = SimpleNamespace(screen=SimpleNamespace(areas=[
            SimpleNamespace(type='VIEW_3D', regions=[primeira]),
            SimpleNamespace(type='VIEW_3D', regions=[segunda])]))
        P._referencia_pendente[0] = dict(grupo='Grupo', quantidade=5, regiao=None, mouse=None)
        with patch.object(addon.gaveta_eventos, '_gaveta_sob_evento', return_value=None), \
             patch.object(addon.eventos, '_redesenhar_viewports') as redesenhar:
            for x, y, regiao, esperado in ((410, 290, 123, (110, 190)),
                                           (470, 330, 123, (170, 230)),
                                           (1000, 400, 456, (100, 300))):
                evento = SimpleNamespace(type='MOUSEMOVE', mouse_x=x, mouse_y=y)
                resultado = P.OBJECT_OT_referencia_prateleira.modal(None, ctx, evento)
                self.assertEqual(resultado, {'PASS_THROUGH'})
                pedido = P._referencia_pendente[0]
                self.assertEqual(tuple(pedido['mouse']), esperado)
                self.assertEqual(pedido['regiao'], regiao)
                self.assertEqual(pedido['recado'], 'Selecione a prateleira de referencia')
                self.assertEqual(pedido['quantidade'], 5)
            self.assertEqual(redesenhar.call_count, 3)

    def test_aviso_de_referencia_some_fora_da_viewport_e_sobre_o_menu(self):
        regiao = SimpleNamespace(type='WINDOW', x=300, y=100, width=600, height=500,
                                 as_pointer=lambda: 123)
        ctx = SimpleNamespace(screen=SimpleNamespace(areas=[
            SimpleNamespace(type='VIEW_3D', regions=[regiao])]))
        P._referencia_pendente[0] = dict(grupo='Grupo', quantidade=5, regiao=123,
                                         mouse=Vector((50, 60)))
        with patch.object(addon.eventos, '_redesenhar_viewports'), \
             patch.object(addon.gaveta_eventos, '_gaveta_sob_evento', return_value=None):
            P.atualizar_aviso_referencia(ctx, SimpleNamespace(mouse_x=50, mouse_y=50))
            self.assertIsNone(P._referencia_pendente[0]['regiao'])
            self.assertIsNone(P._referencia_pendente[0]['mouse'])
            P.atualizar_aviso_referencia(ctx, SimpleNamespace(mouse_x=450, mouse_y=350))
            self.assertEqual(tuple(P._referencia_pendente[0]['mouse']), (150, 250))
        with patch.object(addon.eventos, '_redesenhar_viewports'), \
             patch.object(addon.gaveta_eventos, '_gaveta_sob_evento', return_value=('menu', 'regiao')):
            P.atualizar_aviso_referencia(ctx, SimpleNamespace(mouse_x=450, mouse_y=350))
            self.assertIsNone(P._referencia_pendente[0]['mouse'])
            self.assertIsNone(P._referencia_pendente[0]['regiao'])

    def test_aumento_reparte_vaos_pela_espessura_real_da_matriz(self):
        grupo = self.prateleiras()
        atuais = P.prateleiras_do_grupo(grupo)
        for obj in atuais:
            P.selecionar(bpy.context, obj, 'PRATELEIRA')
            self.assertIsNone(P.editar(bpy.context, grupo, 'espessura_mm', 80))
        P.selecionar(bpy.context, grupo, 'GRUPO')
        self.assertIsNone(P.editar(bpy.context, grupo, 'entre_mm', 80))
        P.selecionar(bpy.context, atuais[1], 'PRATELEIRA')
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 5, referencia=atuais[1]))
        self.assertEqual(P.parametros(grupo)['espacamento'], 'IGUAL')
        self.assertTrue(all(abs(o.chapa_espessura_mm - 80) < .001
                            for o in P.prateleiras_do_grupo(grupo)))
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 5)

    def test_arrastar_quantidade_exibe_previa_sem_montar_e_esc_cancela(self):
        grupo = self.prateleiras()
        P.selecionar(bpy.context, grupo, 'GRUPO')
        ev = addon.gaveta_eventos
        acao = ('contador', 'prateleiras_quantidade', 3, 1, 20, grupo.name, 'Prateleiras')
        op = SimpleNamespace(_campo=dict(acao=acao, x0=0, arrastou=False, valor=3, meio=20))
        ctx = SimpleNamespace(area=SimpleNamespace(tag_redraw=lambda: None))
        mover = SimpleNamespace(type='MOUSEMOVE', mouse_region_x=48)
        with patch.object(P, 'montar', wraps=P.montar) as montar:
            self.assertEqual(ev.OBJECT_OT_interagir_gaveta._modal_campo(op, ctx, mover), {'RUNNING_MODAL'})
            self.assertEqual(P._quantidade_previa[0], (grupo.name, 5))
            widgets = addon.gaveta._widgets_gaveta(bpy.context, 480, 1400)
            self.assertTrue(any(w[4] == '5' and w[5] and w[5][:2] == acao[:2] for w in widgets))
            self.assertEqual(P.parametros(grupo)['quantidade'], 3)
            cancelar = SimpleNamespace(type='ESC', value='PRESS')
            self.assertEqual(ev.OBJECT_OT_interagir_gaveta._modal_campo(op, ctx, cancelar), {'CANCELLED'})
            self.assertFalse(montar.called)
        self.assertIsNone(P._quantidade_previa[0])

    def test_undo_retorna_ao_edit_mode_com_escopo_global_e_redo_o_conserva(self):
        grupo = self.prateleiras()
        nome = grupo.name
        atuais = P.prateleiras_do_grupo(grupo)
        self.recortar(atuais[1])
        P.selecionar(bpy.context, grupo, 'GRUPO')
        bpy.ops.ed.undo_push(message='Antes de editar prateleiras')
        bpy.ops.object.cabinet_editar_grupo()
        self.editar_vertice_nativo(atuais[1])
        bpy.ops.ed.undo_push(message='Recorte global')
        bpy.ops.object.cabinet_editar_grupo()
        bpy.ops.ed.undo_push(message='Concluiu recorte')
        bpy.ops.ed.undo()
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        self.assertTrue(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
        self.assertIn(nome, P.edicao_atual(bpy.context)['globais'])
        bpy.ops.ed.redo()
        self.assertEqual(bpy.context.mode, 'OBJECT')
        P.concluir_edicao()
        grupo = bpy.data.objects[nome]
        self.assertIsNone(P._edicao[0])
        atuais = P.prateleiras_do_grupo(grupo)
        self.assertTrue(all(self.geometria(o) == self.geometria(atuais[0]) for o in atuais))
        bpy.ops.ed.undo()
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        self.assertTrue(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
        self.editar_vertice_nativo(bpy.context.object)
        bpy.ops.object.cabinet_editar_grupo()
        atuais = P.prateleiras_do_grupo(bpy.data.objects[nome])
        self.assertTrue(all(self.geometria(o) == self.geometria(atuais[0]) for o in atuais))

    def test_referencia_modal_clique_rejeita_corpo_e_retoma_no_mesmo_evento(self):
        grupo = self.prateleiras()
        fonte = P.prateleiras_do_grupo(grupo)[1]
        self.recortar(fonte)
        P.selecionar(bpy.context, grupo, 'GRUPO')
        P.editar(bpy.context, grupo, 'quantidade', 4)
        avisos = []
        op = SimpleNamespace(cancel=lambda ctx: P.OBJECT_OT_referencia_prateleira.cancel(None, ctx),
                             report=lambda tipo, texto: avisos.append(texto))
        evento = SimpleNamespace(type='LEFTMOUSE', value='PRESS')
        with patch.object(addon.gaveta_eventos, '_objeto_sob_mouse', return_value=self.conj.name):
            self.assertEqual(P.OBJECT_OT_referencia_prateleira.modal(op, bpy.context, evento), {'RUNNING_MODAL'})
        self.assertTrue(avisos)
        with patch.object(addon.gaveta_eventos, '_objeto_sob_mouse', return_value=fonte.name):
            self.assertEqual(P.OBJECT_OT_referencia_prateleira.modal(op, bpy.context, evento), {'FINISHED'})
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 4)
        self.assertEqual(self.geometria(P.prateleiras_do_grupo(grupo)[-1]), self.geometria(fonte))

    def test_matriz_unica_recortada_dispensa_escolha_sem_selecao_individual(self):
        grupo = self.prateleiras()
        atuais = P.prateleiras_do_grupo(grupo)
        for obj in atuais:
            self.recortar(obj)
        P.selecionar(bpy.context, grupo, 'GRUPO')
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 4))
        self.assertIsNone(P._referencia_pendente[0])
        self.assertEqual(self.geometria(P.prateleiras_do_grupo(grupo)[-1]), self.geometria(atuais[0]))

    def test_parametro_durante_tab_global_conclui_edicao_e_aplica_a_todas(self):
        grupo = self.prateleiras()
        P.selecionar(bpy.context, grupo, 'GRUPO')
        bpy.ops.object.cabinet_editar_grupo()
        self.assertIsNone(P.editar(bpy.context, grupo, 'profundidade_mm', 420))
        self.assertEqual(bpy.context.mode, 'OBJECT')
        self.assertTrue(all(abs(o.chapa_comprimento_mm - 420) < .001
                            for o in P.prateleiras_do_grupo(grupo)))

    def test_matrizes_individuais_reencaixam_na_profundidade_e_voltam_sem_perder_recorte(self):
        grupo = self.prateleiras()
        fonte = P.prateleiras_do_grupo(grupo)[1]
        self.recortar(fonte)
        P.selecionar(bpy.context, fonte, 'PRATELEIRA')
        P.editar(bpy.context, grupo, 'profundidade_mm', 420)
        P.editar(bpy.context, grupo, 'quantidade', 4)
        antes = [self.geometria(o) for o in P.prateleiras_do_grupo(grupo)]
        self.conj.conj_profundidade_mm = 100
        self.assertTrue(all(o.chapa_comprimento_mm <= 100.01
                            for o in P.prateleiras_do_grupo(grupo)))
        self.conj.conj_profundidade_mm = 560
        self.assertEqual([self.geometria(o) for o in P.prateleiras_do_grupo(grupo)], antes)

    def recortar(self, obj):
        # Um chanfro assimetrico distingue a geometria sem mudar a caixa.
        obj.data.vertices[0].co.x += .035
        obj.data.vertices[0].co.y += .025
        obj.data.update()

    def geometria(self, obj):
        return ([tuple(round(c, 7) for c in v.co) for v in obj.data.vertices],
                [tuple(f.vertices) for f in obj.data.polygons])

    def editar_vertice_nativo(self, obj):
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.verts[0].co.x += .037
        bm.verts[0].co.y += .021
        bmesh.update_edit_mesh(obj.data)

    def conferir_cotas_de_posicao(self, grupo, esperado):
        for atual, valor in zip(P.vaos(P.vao(grupo)[1], P.parametros(grupo)), esperado):
            self.assertAlmostEqual(atual, valor, places=2)
        _cantos, linhas = P.linhas_hud(grupo, P.prateleiras_do_grupo(grupo))
        linhas = [l for l in linhas if l.get('vao')]
        fonte = P.individual_ativo(bpy.context, grupo)
        indices = ([int(fonte[P.CHAVE_INDICE]), int(fonte[P.CHAVE_INDICE]) + 1]
                   if fonte else list(range(len(esperado))))
        visiveis = [esperado[i] for i in indices]
        self.assertEqual(len(linhas), len(visiveis))
        for linha, valor in zip(linhas, visiveis):
            self.assertAlmostEqual((linha['pontos'][1] - linha['pontos'][0]).length * 1000,
                                   valor, places=2)
        bpy.context.scene.cabinet_aba = 'PRATELEIRAS'
        widgets = addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)
        campos = [w[5] for w in widgets if w[5] and w[5][0] == 'medida'
                  and w[5][1] == 'prateleiras' and w[5][2].startswith('vao_')]
        self.assertEqual(len(campos), len(visiveis))
        for campo, valor in zip(campos, visiveis):
            self.assertAlmostEqual(campo[4], valor, places=2)

    def test_g_nativo_em_tab_individual_e_global_atualiza_cotas_sem_mover_vizinhas(self):
        self.conj.rotation_euler = (.2, -.3, .7)
        bpy.context.view_layer.update()
        for nivel, deslocamento in (('PRATELEIRA', 40.), ('GRUPO', -40.)):
            with self.subTest(nivel=nivel):
                grupo = self.prateleiras()
                pecas = P.prateleiras_do_grupo(grupo)
                alvo = pecas[1]
                P.selecionar(bpy.context, alvo, nivel)
                antes = [o.matrix_world.copy() for o in pecas]
                malhas = [o.data for o in pecas]
                bpy.ops.object.cabinet_editar_grupo()
                for obj in bpy.context.objects_in_mode:
                    bm = bmesh.from_edit_mesh(obj.data)
                    for v in bm.verts:
                        v.select_set(obj == alvo)
                    bmesh.update_edit_mesh(obj.data)
                delta = grupo.matrix_world.to_3x3() @ Vector((0, 0, deslocamento / 1000))
                self.assertEqual(bpy.ops.transform.translate(value=delta), {'FINISHED'})
                P.sincronizar_exclusoes_da_cena()
                self.assertEqual(P.vaos(664, P.parametros(grupo)), [152.5] * 4)
                bpy.ops.object.mode_set(mode='OBJECT')
                addon.eventos.verificar_periodicamente()
                self.conferir_cotas_de_posicao(grupo,
                    [152.5, 152.5 + deslocamento, 152.5 - deslocamento, 152.5])
                self.assertEqual([o.data for o in pecas], malhas)
                for i in (0, 2):
                    self.assertEqual(pecas[i].matrix_world, antes[i])
                alturas = self.alturas(grupo)
                P.montar(grupo)
                self.assertEqual(self.alturas(grupo), alturas)

    def test_g_nativo_em_objeto_sincroniza_so_apos_confirmar_e_conserva_encaixe(self):
        grupo = self.prateleiras()
        P.atualizar_do_conjunto(self.conj)
        pecas = P.prateleiras_do_grupo(grupo)
        alvo = pecas[1]
        P.selecionar(bpy.context, alvo, 'PRATELEIRA')
        self.assertEqual(bpy.ops.transform.translate(value=(0, 0, .04)), {'FINISHED'})
        with patch.object(addon.eventos, '_ha_modal_ativo', return_value=True):
            addon.eventos.verificar_periodicamente()
        self.assertAlmostEqual(P.vaos(664, P.parametros(grupo))[1], 152.5)
        addon.eventos.verificar_periodicamente()
        self.conferir_cotas_de_posicao(grupo, [152.5, 192.5, 112.5, 152.5])
        antes = self.alturas(grupo)
        P.atualizar_do_conjunto(self.conj)
        self.assertEqual(self.alturas(grupo), antes)
        with patch.object(P, 'montar', side_effect=AssertionError('Remontou no timer')):
            addon.eventos.verificar_periodicamente()
        self.assertEqual(P.prateleiras_do_grupo(grupo), pecas)

    def test_g_cruzando_prateleira_reordena_cotas_e_conserva_parametros_individuais(self):
        grupo = self.prateleiras()
        self.assertIsNone(P.editar_individual(bpy.context, grupo, 1, 'recuo_mm', 35))
        a, b, c = P.prateleiras_do_grupo(grupo)
        P.selecionar(bpy.context, b, 'PRATELEIRA')
        self.assertEqual(bpy.ops.transform.translate(value=(0, 0, .2)), {'FINISHED'})
        addon.eventos.verificar_periodicamente()
        self.assertEqual(P.prateleiras_do_grupo(grupo), [a, c, b])
        self.conferir_cotas_de_posicao(grupo, [152.5, 323., 11.5, 123.])
        self.assertEqual(P.parametros_individuais(P.parametros(grupo), 2)['recuo_mm'], 35)
        self.assertEqual(bpy.context.object, b)

    def test_undo_redo_do_g_nativo_restaura_malha_posicao_e_cotas(self):
        # O teste de undo anterior nao entrega o loop ao timer em background.
        addon.eventos._fim_do_desfazer()
        self.addCleanup(addon.eventos._fim_do_desfazer)
        grupo = self.prateleiras()
        nome = grupo.name
        alvo = P.prateleiras_do_grupo(grupo)[1]
        P.selecionar(bpy.context, alvo, 'PRATELEIRA')
        bpy.ops.ed.undo_push(message='Antes de G na prateleira')
        bpy.ops.object.cabinet_editar_grupo()
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.transform.translate(value=(0, 0, .04))
        bpy.ops.object.mode_set(mode='OBJECT')
        addon.eventos.verificar_periodicamente()
        bpy.ops.ed.undo_push(message='G confirmado e cotas atualizadas')
        bpy.ops.ed.undo()
        grupo = bpy.data.objects[nome]
        self.conferir_cotas_de_posicao(grupo, [152.5] * 4)
        self.assertEqual(self.alturas(grupo), [152.5, 323., 493.5])
        bpy.ops.ed.redo()
        grupo = bpy.data.objects[nome]
        self.conferir_cotas_de_posicao(grupo, [152.5, 192.5, 112.5, 152.5])
        self.assertEqual(self.alturas(grupo), [152.5, 363., 493.5])
        antes = P.copia(grupo)
        addon.eventos.verificar_periodicamente()
        self.assertEqual(P.copia(grupo), antes)
        addon.eventos._fim_do_desfazer()
        addon.eventos.verificar_periodicamente()
        self.conferir_cotas_de_posicao(grupo, [152.5, 192.5, 112.5, 152.5])

    def test_tab_individual_isola_malha_compartilhada_e_preserva_vizinhas(self):
        grupo = self.prateleiras()
        a, b, c = P.prateleiras_do_grupo(grupo)
        b.data = a.data
        antes = [self.geometria(o) for o in (a, c)]
        P.selecionar(bpy.context, b, 'PRATELEIRA')
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual(list(bpy.context.objects_in_mode), [b])
        self.editar_vertice_nativo(b)
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual([self.geometria(o) for o in (a, c)], antes)
        self.assertNotEqual(self.geometria(a), self.geometria(b))
        P.montar(grupo)
        self.assertNotEqual(self.geometria(a), self.geometria(b))

    def test_tab_modulo_propaga_recorte_sem_alterar_outro_modulo(self):
        grupo = self.prateleiras()
        fora = self.prateleiras()
        antes = [self.geometria(o) for o in P.prateleiras_do_grupo(fora)]
        # O segundo vao fica em outro modulo, mesmo que use o mesmo Mesh.
        outro = bpy.data.objects.new('Outro modulo', None)
        bpy.context.scene.collection.objects.link(outro)
        fora.parent = outro
        for o in bpy.context.selected_objects:
            o.select_set(False)
        self.conj.select_set(True)
        bpy.context.view_layer.objects.active = self.conj
        bpy.ops.object.cabinet_editar_grupo()
        atuais = P.prateleiras_do_grupo(grupo)
        ids_malha = [o.data.as_pointer() for o in atuais]
        self.editar_vertice_nativo(atuais[0])
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual([o.data.as_pointer() for o in atuais], ids_malha)
        self.assertTrue(all(self.geometria(o) == self.geometria(atuais[0]) for o in atuais))
        self.assertEqual([self.geometria(o) for o in P.prateleiras_do_grupo(fora)], antes)
        self.assertEqual(len({o.data.as_pointer() for o in atuais}), 3)

    def test_tab_global_com_tipos_diferentes_so_propaga_se_houver_edicao(self):
        grupo = self.prateleiras()
        atuais = P.prateleiras_do_grupo(grupo)
        self.recortar(atuais[1])
        antes = [self.geometria(o) for o in atuais]
        P.selecionar(bpy.context, grupo, 'GRUPO')
        bpy.ops.object.cabinet_editar_grupo()
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual([self.geometria(o) for o in atuais], antes)
        P.selecionar(bpy.context, grupo, 'GRUPO')
        bpy.ops.object.cabinet_editar_grupo()
        self.editar_vertice_nativo(atuais[1])
        # Saida pelo seletor nativo de modo tambem conclui no timer existente.
        bpy.ops.object.mode_set(mode='OBJECT')
        P.concluir_edicao()
        self.assertTrue(all(self.geometria(o) == self.geometria(atuais[1]) for o in atuais))

    def test_quantidade_herda_selecao_geometria_material_modificador_e_parametros(self):
        grupo = self.prateleiras()
        fonte = P.prateleiras_do_grupo(grupo)[1]
        self.recortar(fonte)
        P.selecionar(bpy.context, fonte, 'PRATELEIRA')
        P.editar(bpy.context, grupo, 'profundidade_mm', 425)
        fonte.modifiers.new('Arredondar', 'BEVEL').width = .002
        mat = bpy.data.materials.new('Madeira da matriz')
        fonte.data.materials.append(mat)
        esperado = self.geometria(fonte)
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 5, referencia=fonte))
        self.assertIsNone(P._referencia_pendente[0])
        atuais = P.prateleiras_do_grupo(grupo)
        for obj in atuais[3:]:
            self.assertEqual(self.geometria(obj), esperado)
            self.assertEqual(obj.modifiers[0].width, fonte.modifiers[0].width)
            self.assertEqual(obj.data.materials[0], mat)
            self.assertAlmostEqual(obj.chapa_comprimento_mm, 425)
            self.assertNotEqual(obj['chapa_uid'], fonte.get('chapa_uid'))
            self.assertNotEqual(obj.data, fonte.data)
        self.assertEqual(bpy.context.object, fonte)
        self.assertAlmostEqual(atuais[0].chapa_comprimento_mm, 540)

    def test_tipos_diferentes_pedem_referencia_e_so_adicionam_apos_clique_valido(self):
        grupo = self.prateleiras()
        fonte = P.prateleiras_do_grupo(grupo)[1]
        self.recortar(fonte)
        P.selecionar(bpy.context, grupo, 'GRUPO')
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 4))
        self.assertEqual(P.parametros(grupo)['quantidade'], 3)
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 3)
        self.assertIsNotNone(P._referencia_pendente[0])
        self.assertIsNotNone(P.resolver_referencia(bpy.context, self.conj))
        outro = self.prateleiras()
        self.assertIsNotNone(P.resolver_referencia(bpy.context, P.prateleiras_do_grupo(outro)[0]))
        self.assertIsNone(P.resolver_referencia(bpy.context, fonte))
        self.assertEqual(self.geometria(P.prateleiras_do_grupo(grupo)[-1]), self.geometria(fonte))
        self.assertIsNone(P._referencia_pendente[0])

    def test_referencia_modal_esc_nao_altera_quantidade_nem_geometria(self):
        grupo = self.prateleiras()
        self.recortar(P.prateleiras_do_grupo(grupo)[0])
        P.selecionar(bpy.context, grupo, 'GRUPO')
        antes = [self.geometria(o) for o in P.prateleiras_do_grupo(grupo)]
        P.editar(bpy.context, grupo, 'quantidade', 6)
        op = SimpleNamespace(cancel=lambda ctx: P.OBJECT_OT_referencia_prateleira.cancel(None, ctx))
        evento = SimpleNamespace(type='ESC', value='PRESS')
        self.assertEqual(P.OBJECT_OT_referencia_prateleira.modal(op, bpy.context, evento), {'CANCELLED'})
        self.assertIsNone(P._referencia_pendente[0])
        self.assertEqual(P.parametros(grupo)['quantidade'], 3)
        self.assertEqual([self.geometria(o) for o in P.prateleiras_do_grupo(grupo)], antes)
        self.assertIn(P.OBJECT_OT_referencia_prateleira, addon.CLASSES)

    def test_parametros_individuais_nao_movem_nem_redimensionam_as_vizinhas(self):
        grupo = self.prateleiras()
        a, b, c = P.prateleiras_do_grupo(grupo)
        P.selecionar(bpy.context, b, 'PRATELEIRA')
        antes = [(self.geometria(o), o.matrix_basis.copy()) for o in (a, c)]
        for campo, valor in (('espessura_mm', 30), ('profundidade_mm', 420),
                             ('recuo_mm', 15), ('largura_mm', 700)):
            self.assertIsNone(P.editar(bpy.context, grupo, campo, valor))
        self.assertEqual([(self.geometria(o), o.matrix_basis) for o in (a, c)], antes)
        self.assertAlmostEqual(b.chapa_espessura_mm, 30)
        self.assertAlmostEqual(b.chapa_largura_mm, 700)
        self.assertAlmostEqual(b.chapa_comprimento_mm, 405)
        P.selecionar(bpy.context, grupo, 'GRUPO')
        self.assertIsNone(P.editar(bpy.context, grupo, 'espessura_mm', 25))
        self.assertTrue(all(abs(o.chapa_espessura_mm - 25) < .001 for o in (a, b, c)))

    def test_reducao_dispensa_referencia_e_adicao_inviavel_nao_muda_o_grupo(self):
        grupo = self.prateleiras()
        fonte = P.prateleiras_do_grupo(grupo)[0]
        self.recortar(fonte)
        P.selecionar(bpy.context, grupo, 'GRUPO')
        self.assertIsNone(P.editar(bpy.context, grupo, 'quantidade', 2))
        self.assertIsNone(P._referencia_pendente[0])
        self.assertIsNone(P.editar(bpy.context, grupo, 'espessura_mm', 200))
        P.selecionar(bpy.context, fonte, 'PRATELEIRA')
        antes = P.parametros(grupo)
        self.assertIsNotNone(P.editar(bpy.context, grupo, 'quantidade', 5))
        self.assertEqual(P.parametros(grupo), antes)
        self.assertEqual(len(P.prateleiras_do_grupo(grupo)), 2)

    def test_reduzir_modulo_reencaixa_vaos_livres_e_devolve_originais(self):
        grupo=self.prateleiras(espacamento='LIVRE',vaos_mm=[100,200,50])
        antes=self.alturas(grupo)
        self.conj.conj_altura_mm=100
        l,a,m=P.vao(grupo)
        self.assertGreaterEqual(min(P.vaos(a,P.parametros(grupo))),-.01)
        self.assertLess(self.alturas(grupo)[-1]+18,a+.01)
        self.conj.conj_altura_mm=700
        self.assertEqual(antes,self.alturas(grupo))

    def test_prateleiras_do_assistente_conservam_referencia_da_face_lateral(self):
        ref=Matrix.Rotation(1.57079632679,3,'Z')
        pontos=[Vector((-.4,-.262,.682)),Vector((-.4,.262,.018))]
        ref=addon.gavetas.referencia_do_vao(self.conj,*pontos)
        margens=addon.gavetas.margens_do_vao(self.conj,*pontos,referencial=ref)
        grupo=P.criar_prateleiras(bpy.context,self.conj,margens,
                  dict(quantidade=2,profundidade_mm=700),referencial=ref)
        self.assertGreater(grupo.matrix_world.to_3x3().col[1].dot(Vector((1,0,0))),.999)
        self.assertIsNone(P.editar(bpy.context,grupo,'espessura_mm',15))
        self.assertGreater(grupo.matrix_world.to_3x3().col[1].dot(Vector((1,0,0))),.999)
        self.assertAlmostEqual(P.medidas(grupo)[0],524,places=2)
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

    def test_reducao_com_folga_preserva_prateleiras_e_so_adapta_ao_encostar(self):
        grupo = P.criar_prateleiras(bpy.context,self.conj,(18,382,18,382,0),
                                    dict(quantidade=2, profundidade_mm=400))
        pecas = P.prateleiras_do_grupo(grupo)
        antes = P.medidas(grupo)
        for largura in (1000,900,700,600):
            self.conj.conj_largura_mm = largura
            bpy.context.view_layer.update()
            self.assertAlmostEqual(P.medidas(grupo)[0],antes[0],delta=.05)
        self.conj.conj_altura_mm=600
        self.assertAlmostEqual(P.medidas(grupo)[1],antes[1],delta=.05)
        self.conj.conj_profundidade_mm=500
        self.assertAlmostEqual(P.medidas(grupo)[2],antes[2],delta=.05)
        self.conj.conj_largura_mm=400
        self.assertAlmostEqual(P.medidas(grupo)[0],364,delta=.05)
        self.conj.conj_largura_mm=800
        self.assertAlmostEqual(P.medidas(grupo)[0],antes[0],delta=.05)
        self.assertEqual(P.prateleiras_do_grupo(grupo),pecas)

    def test_cancelar_resize_do_modulo_restaura_vao_parametros_e_geometria(self):
        grupo=self.prateleiras()
        antes=P.copia(grupo)
        objetos=P.prateleiras_do_grupo(grupo)
        vertices={o.name:[tuple(v.co) for v in o.data.vertices] for o in objetos}
        alvo=dict(objeto=self.conj,tipo='medida',modo='GRUPO',eixo=0,lado='min')
        backup=addon.hud._estado_arraste_hud(bpy.context,alvo)
        addon.hud._aplicar_valor_hud(bpy.context,alvo,500)
        self.assertAlmostEqual(P.medidas(grupo)[0],464,delta=.05)
        addon.hud._restaurar_arraste_hud(bpy.context,backup)
        self.assertEqual(P.copia(grupo),antes)
        self.assertAlmostEqual(P.medidas(grupo)[0],764,delta=.05)
        self.assertNotIn(P.CHAVE_ENCAIXE,grupo)
        for o in objetos:self.assertEqual([tuple(v.co) for v in o.data.vertices],vertices[o.name])

    def test_modulo_que_muda_de_medida_leva_as_prateleiras(self):
        grupo = self.prateleiras()
        self.conj.conj_largura_mm = 1000.0          # dispara o redimensionar
        bpy.context.view_layer.update()
        # v288: aumentar a caixa deixa folga; o bloco conserva a escolha.
        self.assertAlmostEqual(P.medidas(grupo)[0], 764.0, places=2)
        self.assertAlmostEqual(P.prateleiras_do_grupo(grupo)[0].chapa_largura_mm, 764.0, places=2)

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
        self.assertIn(('aba', 'PRATELEIRAS'), [v[5] for v in widgets if v[5]])
        grupo = self.prateleiras()
        P.selecionar(bpy.context, grupo, 'GRUPO')
        acoes = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 480, 1400) if v[5]]
        self.assertTrue(any(a[0] == 'contador' and a[1] == 'prateleiras_quantidade'
                            for a in acoes))
        self.assertFalse(any(a[0] == 'escolha' and a[1] == 'prateleiras_espacamento'
                             for a in acoes))
        self.assertIn(('operador', 'object.cabinet_alinhar_prateleiras'), acoes)
        medidas = {a[2] for a in acoes if a[0] == 'medida' and a[1] == 'prateleiras'}
        self.assertTrue({'largura', 'altura', 'profundidade_mm', 'espessura_mm', 'recuo_mm',
                         'folga_lateral_mm', 'vao_0', 'vao_3'} <= medidas, medidas)
        self.assertNotIn('entre_mm', medidas)
        # Uma so' (duplo) mostra apenas os vaos do trecho local.
        segunda = P.prateleiras_do_grupo(grupo)[1]
        P.selecionar(bpy.context, segunda, 'PRATELEIRA')
        acoes = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 480, 1400) if v[5]]
        rotulos = {a[3]: a[2] for a in acoes if a[0] == 'medida' and a[1] == 'prateleiras'}
        self.assertEqual([rotulos['E%d' % i] for i in (2, 3)], ['vao_1', 'vao_2'])
        self.assertNotIn('E1', rotulos)
        self.assertNotIn('E4', rotulos)
        self.assertNotIn('Abaixo', rotulos)
        self.assertNotIn('Acima', rotulos)
        self.assertNotIn('Entre prateleiras', rotulos)
        self.assertEqual(rotulos['Largura'], 'individual_1_largura_mm')
        for largura in (190, 320, 564):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1400)
            self.assertTrue(any(w[5] and w[5][:2] == ('contador', 'prateleiras_quantidade')
                                for w in widgets))
        # os campos chegam pelos mesmos caminhos da porta/gavetas
        ev = addon.gaveta_eventos
        self.assertIsNone(ev.aplicar_medida(bpy.context, 'prateleiras', segunda.name,
                                            'vao_1', 0.1))
        self.assertEqual(self.alturas(grupo), [152.5, 270.5, 493.5])
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
