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
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix, Vector
from bpy_extras import view3d_utils

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

    def test_modulo_que_muda_de_medida_preserva_as_gavetas(self):
        # Regressao (era BUG, corrigido na 219): a caixa esticava as gavetas.
        grupo = self.gavetas()
        gaveta = G.gavetas_do_grupo(grupo)[0]
        G.definir_abertura(gaveta, 0.4)
        antes = G.medidas(grupo)
        backup = addon.hud._estado_arraste_hud(
            bpy.context, {'objeto': self.conj, 'tipo': 'medida'})
        objetos = list(grupo.children_recursive)
        self.conj.conj_largura_mm = 1000.0
        self.conj.conj_altura_mm = 1200.0
        bpy.context.view_layer.update()
        for a, b in zip(antes, G.medidas(grupo)):
            self.assertAlmostEqual(a, b, places=2)
        self.assertEqual(objetos, list(grupo.children_recursive))
        self.assertAlmostEqual(gaveta[G.CHAVE_ABERTURA], 0.4)
        addon.hud._restaurar_arraste_hud(bpy.context, backup)
        for a, b in zip(antes, G.medidas(grupo)):
            self.assertAlmostEqual(a, b, places=2)
        self.conj.conj_altura_mm = 1200.0
        bpy.context.view_layer.update()
        origem = grupo.matrix_world.translation.copy()
        self.assertIsNone(G.aplicar(bpy.context, grupo, ('A',), 800.0))
        bpy.context.view_layer.update()
        self.assertLess((grupo.matrix_world.translation - origem).length, 1e-5)
        self.assertAlmostEqual(G.medidas(grupo)[1], 800.0, places=2)

    def test_esticar_para_baixo_leva_gavetas_sem_deformar_e_esc_devolve(self):
        # Regressao (era BUG, corrigido na 220): a base descia sozinha.
        grupo = G.criar_gavetas(bpy.context, self.conj, (18, 18, 18, 382, 0),
                               dict(quantidade=3, profundidade_mm=560.0))
        gaveta = G.gavetas_do_grupo(grupo)[0]
        G.definir_abertura(gaveta, 0.4)
        bpy.context.view_layer.update()
        medidas = G.medidas(grupo)
        objetos = [grupo, *grupo.children_recursive]
        matrizes = {o.name: o.matrix_world.copy() for o in objetos}
        malhas = {o.name: [tuple(v.co) for v in o.data.vertices]
                  for o in objetos if o.type == 'MESH'}
        margens = tuple(grupo[G.CHAVE_MARGENS])
        alvo = dict(objeto=self.conj, tipo='medida', modo='GRUPO', eixo=2, lado='max')
        backup = addon.hud._estado_arraste_hud(bpy.context, alvo)
        teto = addon.modulos._caixa_de(addon.modulos._chapas_do_conjunto(self.conj))[1][2]
        for altura in (1000.0, 1200.0):
            addon.hud._aplicar_valor_hud(bpy.context, alvo, altura)
            bpy.context.view_layer.update()
            delta = Vector((0, 0, -(altura - 700.0) / 1000.0))
            for o in objetos:
                self.assertLess((o.matrix_world.translation -
                                 matrizes[o.name].translation - delta).length, 1e-5)
            for a, b in zip(medidas, G.medidas(grupo)):
                self.assertAlmostEqual(a, b, places=2)
            self.assertAlmostEqual(addon.modulos._caixa_de(
                addon.modulos._chapas_do_conjunto(self.conj))[1][2], teto, places=5)
        self.assertEqual(malhas, {o.name: [tuple(v.co) for v in o.data.vertices]
                                 for o in objetos if o.type == 'MESH'})
        self.assertAlmostEqual(gaveta[G.CHAVE_ABERTURA], 0.4)
        addon.hud._restaurar_arraste_hud(bpy.context, backup)
        bpy.context.view_layer.update()
        for o in objetos:
            self.assertLess((o.matrix_world.translation - matrizes[o.name].translation).length, 1e-5)
        self.assertEqual(tuple(grupo[G.CHAVE_MARGENS]), margens)
        for a, b in zip(medidas, G.medidas(grupo)):
            self.assertAlmostEqual(a, b, places=2)

    def test_gavetas_proximas_do_topo_acompanham_topo_sem_esticar(self):
        grupo = G.criar_gavetas(bpy.context, self.conj, (18, 18, 382, 18, 0),
                               dict(quantidade=3, profundidade_mm=560.0))
        bpy.context.view_layer.update()
        origem = grupo.matrix_world.translation.copy()
        medidas = G.medidas(grupo)
        alvo = dict(objeto=self.conj, tipo='medida', modo='GRUPO', eixo=2, lado='min')
        addon.hud._aplicar_valor_hud(bpy.context, alvo, 1000.0)
        bpy.context.view_layer.update()
        self.assertLess((grupo.matrix_world.translation - origem - Vector((0, 0, 0.3))).length, 1e-5)
        for a, b in zip(medidas, G.medidas(grupo)):
            self.assertAlmostEqual(a, b, places=2)

    def test_modulo_selecionado_absorve_gavetas_sem_segunda_ancora(self):
        # Regressao (era BUG, corrigido na 219): filhos viravam multiselecao.
        grupo = self.gavetas()
        for o in [self.conj, *self.conj.children_recursive]:
            o.select_set(True)
        bpy.context.view_layer.objects.active = self.conj
        itens = addon.hud._itens_da_selecao(bpy.context)
        self.assertEqual([(o, modo) for o, modo, _ in itens], [(self.conj, 'GRUPO')])
        self.assertEqual(G.selecionados(bpy.context), [])
        self.assertEqual(G.gavetas_com_slider(bpy.context), [])
        outro = addon.modulos.criar_armario(bpy.context, 'Outro', 600, 700, 560)
        for o in [self.conj, *self.conj.children_recursive]:
            o.select_set(True)
        outro.select_set(True)
        itens = addon.hud._itens_da_selecao(bpy.context)
        self.assertEqual({o for o, modo, _ in itens}, {self.conj, outro})
        self.assertTrue(all(modo == 'GRUPO' for _, modo, _ in itens))

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

    def test_cancelar_redimensionamento_direto_devolve_medidas_e_selecao(self):
        # Regressao (era BUG, corrigido na 221): Esc nao devolvia as medidas.
        grupo = self.gavetas()
        G.selecionar(bpy.context, grupo, 'GRUPO')
        G.definir_abertura(G.gavetas_do_grupo(grupo)[0], 0.4)
        for letra in ('L', 'A', 'P'):
            for lado in ('min', 'max'):
                alvo = dict(objeto=grupo, tipo='gavetas', face=(letra,), lado=lado)
                antes = G.medidas(grupo)
                modulo = addon.modulos.medir_conjunto(self.conj)
                origem = grupo.matrix_world.translation.copy()
                backup = addon.hud._estado_arraste_hud(bpy.context, alvo)
                addon.hud._aplicar_valor_hud(bpy.context, alvo, G.valor(grupo, (letra,)) - 50)
                addon.hud._restaurar_arraste_hud(bpy.context, backup)
                bpy.context.view_layer.update()
                for a, b in zip(antes, G.medidas(grupo)):
                    self.assertAlmostEqual(a, b, places=2)
                for a, b in zip(modulo, addon.modulos.medir_conjunto(self.conj)):
                    self.assertAlmostEqual(a, b, places=2)
                self.assertLess((grupo.matrix_world.translation - origem).length, 1e-5)
                self.assertEqual(bpy.context.view_layer.objects.active, grupo)
                self.assertAlmostEqual(G.gavetas_do_grupo(grupo)[0][G.CHAVE_ABERTURA], 0.4)

    def test_profundidade_editada_pelas_costas_mantem_costas_paradas(self):
        # Regressao (era BUG, corrigido na 221): P ignorava a quina escolhida.
        grupo = self.gavetas()
        bpy.context.view_layer.update()
        costas = G.pontos_editaveis(grupo)[2].copy()
        self.assertIsNone(G.aplicar(bpy.context, grupo, ('P',), 460.0, 'max'))
        bpy.context.view_layer.update()
        self.assertLess((G.pontos_editaveis(grupo)[2] - costas).length, 1e-5)
        self.assertAlmostEqual(G.medidas(grupo)[2], 460.0)

    def test_redimensionar_preserva_selecao_individual_da_gaveta(self):
        # Regressao (era BUG, corrigido na 221): a gaveta ativa era apagada.
        grupo = self.gavetas()
        G.selecionar(bpy.context, G.gavetas_do_grupo(grupo)[1], 'GAVETA')
        self.assertIsNone(G.aplicar(bpy.context, grupo, ('A',), 600.0, 'min'))
        self.assertEqual(bpy.context.view_layer.objects.active, G.gavetas_do_grupo(grupo)[1])
        self.assertEqual(G.gavetas_com_slider(bpy.context), [G.gavetas_do_grupo(grupo)[1]])

    def test_parametros_copiados_e_profundidade_invalida_nao_corrompem_proporcoes(self):
        # Regressao (era BUG, corrigido na 221): array RNA liberado no rollback.
        grupo = self.gavetas(proporcoes=[2.0, 1.0, 1.0])
        p = G.parametros(grupo)
        self.assertIsInstance(p['proporcoes'], list)
        for prof in (200.0, 500.0, 150.0, 400.0):
            erro = G.editar(bpy.context, grupo, 'profundidade_mm', prof)
            self.assertEqual(erro is not None, prof < 260.0)
            self.assertEqual(G.parametros(grupo)['proporcoes'], [2.0, 1.0, 1.0])
        self.assertEqual(p['profundidade_mm'], 560.0)
        self.assertEqual(p['proporcoes'], [2.0, 1.0, 1.0])

    def test_esc_apos_renomear_mover_e_crescer_modulo_nao_desloca_gavetas(self):
        # Regressao (era BUG, corrigido na 222): Esc duplicava a translacao.
        grupo = self.gavetas()
        self.conj.location = (6.7, -1.25, 0.3)
        addon.modulos.nomear_grupo(self.conj, 'Balcao 800x800x560')
        self.conj.conj_altura_mm += 100.0
        bpy.context.view_layer.update()
        G.selecionar(bpy.context, grupo, 'GRUPO')
        antes = grupo.matrix_world.copy()
        medidas = G.medidas(grupo)
        alvo = dict(objeto=grupo, tipo='gavetas', face=('A',), lado='max')
        backup = addon.hud._estado_arraste_hud(bpy.context, alvo)
        # Entrar e Esc SEM mover, como no relato.
        addon.hud._restaurar_arraste_hud(bpy.context, backup)
        bpy.context.view_layer.update()
        self.assertLess((grupo.matrix_world.translation - antes.translation).length, 1e-5)
        for a, b in zip(medidas, G.medidas(grupo)):
            self.assertAlmostEqual(a, b, places=2)
        self.assertIs(G.modulo_do_grupo(grupo), self.conj)
        self.assertEqual(grupo[G.CHAVE_MODULO], self.conj.name)

    def test_pai_real_prevalece_sobre_nome_antigo_de_outro_modulo(self):
        # Regressao (era BUG, corrigido na 222): preset resolvia o modulo errado.
        grupo = self.gavetas()
        self.conj.name = 'Balcao renomeado no Outliner'
        addon.modulos.criar_armario(bpy.context, 'Balcao', 500, 600, 400)
        self.assertIs(G.modulo_do_grupo(grupo), self.conj)

    def test_indice_snap_preserva_ponto_mais_perto_raio_e_empates(self):
        contexto = SimpleNamespace(region=SimpleNamespace(width=800, height=600),
            region_data=SimpleNamespace(perspective_matrix=Matrix((
                (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0.5, 1)))))
        pontos = [Vector((x / 10, y / 10, z)) for x in range(-12, 13)
                  for y in range(-8, 9) for z in (-3.0, 0.0, 0.5)]
        pontos += [Vector((0, 0, 0)), Vector((0, 0, 0.2))]
        indice = G.IndiceSnapGavetas([('Teste', pontos)])
        for x in range(0, 801, 40):
            for y in range(0, 601, 40):
                mouse = Vector((x, y))
                candidatos = []
                for i, p in enumerate(pontos):
                    tela = view3d_utils.location_3d_to_region_2d(
                        contexto.region, contexto.region_data, p)
                    if tela is not None:
                        d = (tela - mouse).length
                        if d <= addon.portas.RAIO_IMA_PX:
                            candidatos.append((d, i, p))
                esperado = min(candidatos, key=lambda v: (v[0], v[1]))[2] if candidatos else None
                encontrado = indice.buscar(contexto, mouse)
                if esperado is None:
                    self.assertIsNone(encontrado)
                else:
                    # Pequeno erro da projecao em lote nao pode mudar o snap.
                    self.assertLess((encontrado - esperado).length, 1e-5)

    def test_indice_snap_nao_reprojeta_no_mouse_e_atualiza_ao_navegar(self):
        contexto = SimpleNamespace(region=SimpleNamespace(width=800, height=600),
            region_data=SimpleNamespace(perspective_matrix=Matrix.Identity(4)))
        ponto = Vector((0.0, 0.0, 0.0))
        indice = G.IndiceSnapGavetas([('Teste', [ponto] * 10000)])
        with patch.object(indice, '_reconstruir', wraps=indice._reconstruir) as refazer:
            for i in range(500):
                self.assertEqual(indice.buscar(contexto, (400 + i % 10, 300)), ponto)
            self.assertEqual(refazer.call_count, 1)
            contexto.region_data.perspective_matrix[0][3] = 0.5
            self.assertIsNone(indice.buscar(contexto, (400, 300)))
            self.assertEqual(indice.buscar(contexto, (600, 300)), ponto)
            contexto.region.width = 1000
            self.assertEqual(indice.buscar(contexto, (750, 300)), ponto)
            self.assertEqual(refazer.call_count, 3)

    def test_snap_ignora_pecas_da_gaveta_sem_excluir_modulo(self):
        grupo = self.gavetas()
        ignorados = {o.name for o in [grupo, *grupo.children_recursive]}
        nomes = {o.name for o, _vs in addon.portas._alvos_do_ima(bpy.context, ignorar=ignorados)}
        self.assertFalse(nomes & ignorados)
        self.assertTrue({o.name for o in addon.modulos._chapas_do_conjunto(self.conj)} <= nomes)

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


    def test_ancora_nativa_nao_varre_malhas_e_restaura_cursor(self):
        grupo = self.gavetas()
        overlay = SimpleNamespace(show_cursor=True)
        area = SimpleNamespace(as_pointer=lambda: 123, type='VIEW_3D',
                               spaces=SimpleNamespace(active=SimpleNamespace(overlay=overlay)),
                               tag_redraw=lambda: None)
        contexto = SimpleNamespace(region=SimpleNamespace(as_pointer=lambda: 456),
            area=area, scene=bpy.context.scene, visible_objects=list(bpy.context.scene.objects),
            space_data=SimpleNamespace(overlay=overlay))
        cursor = tuple(bpy.context.scene.cursor.location)
        selecao = {o.name for o in bpy.context.selected_objects}
        bloqueados = {o.name: o.hide_select for o in bpy.context.scene.objects}
        with patch.object(addon.portas, '_alvos_do_ima', side_effect=AssertionError('varredura')):
            parametros = G._preparar_ancora_nativa(contexto, grupo, 0)
        self.assertTrue(parametros['cursor_transform'])
        self.assertTrue(parametros['use_snap_selectable'])
        self.assertFalse(overlay.show_cursor)
        self.assertTrue(all(o.hide_select for o in grupo.children_recursive if o.type == 'MESH'))
        self.assertEqual(selecao, {o.name for o in bpy.context.selected_objects})
        with patch.object(bpy, 'context', SimpleNamespace(window_manager=SimpleNamespace(
                windows=[SimpleNamespace(screen=SimpleNamespace(areas=[area]))]))):
            G._terminar_ancora_nativa()
        self.assertEqual(tuple(bpy.context.scene.cursor.location), cursor)
        self.assertTrue(overlay.show_cursor)
        self.assertEqual(bloqueados, {o.name: o.hide_select for o in bpy.context.scene.objects})

    def test_clique_no_puxador_isola_acessorio_e_abre_suas_funcoes(self):
        grupo = self.gavetas()
        gavetas = G.gavetas_do_grupo(grupo)
        puxadores = [next(o for o in G.frente_da_gaveta(g).children
                         if addon.chapas.MARCA_PUXADOR in o) for g in gavetas]
        G.selecionar(bpy.context, grupo, 'GRUPO')
        S = addon.selecao
        op = SimpleNamespace(clique=False, modo='GRUPO', toggle=False, extend=False)
        evento = SimpleNamespace(mouse_region_x=50, mouse_region_y=60)

        def clicar(obj, somar=False):
            op.toggle = somar
            ctx = SimpleNamespace(region=SimpleNamespace(as_pointer=lambda: 1),
                view_layer=bpy.context.view_layer, selected_objects=list(bpy.context.selected_objects),
                area=None)
            with patch.object(addon.hud, '_raio_hud', return_value=(obj, None)), \
                 patch.object(addon.hud, '_ferragem_sob_mouse', return_value=None), \
                 patch.object(addon.portas_viewport, '_slider_sob_mouse', return_value=None), \
                 patch.object(G, 'slider_sob_mouse', return_value=None):
                return S.OBJECT_OT_selecionar._invoke(op, ctx, evento)

        self.assertEqual(clicar(puxadores[0]), {'FINISHED'})
        self.assertEqual(set(bpy.context.selected_objects), {puxadores[0]})
        self.assertFalse(S.familia_de(puxadores[0]))
        S._seguir_selecao_na_gaveta(bpy.context)
        self.assertEqual(bpy.context.scene.cabinet_aba, 'PUXADORES')
        acoes = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 480, 1400) if v[5]]
        self.assertTrue(any(a[0] == 'escolha' and addon.gaveta.ALVO_PUXADOR in a for a in acoes))
        clicar(puxadores[1], somar=True)
        self.assertEqual(set(bpy.context.selected_objects), set(puxadores[:2]))
        clicar(puxadores[1], somar=True)
        self.assertEqual(set(bpy.context.selected_objects), {puxadores[0]})
        self.assertEqual(bpy.context.view_layer.objects.active, puxadores[0])
        trilho = next(o for o in grupo.children if o.get(G.MARCA_PECA) == 'TRILHO')
        clicar(trilho)
        self.assertEqual(bpy.context.view_layer.objects.active, grupo)
        self.assertFalse(any(p.select_get() for p in puxadores))

    def test_edicao_individual_puxador_sobrevive_ao_redimensionamento(self):
        grupo = self.gavetas()
        gavetas = G.gavetas_do_grupo(grupo)
        pux = next(o for o in G.frente_da_gaveta(gavetas[1]).children
                   if addon.chapas.MARCA_PUXADOR in o)
        addon.puxadores._trocar_modelo_puxador(pux, 'ALCA')
        pux['puxador_comprimento_mm'] = 180.0
        pux['puxador_recuo_mm'] = 35.0
        pux['puxador_fracao'] = 0.3
        addon.puxadores.posicionar_puxador(pux)
        self.assertEqual(gavetas[1][G.CHAVE_PUXADOR], 'ALCA')
        self.assertIsNone(G.editar(bpy.context, grupo, 'entre_gavetas_mm', 6.0))
        gavetas = G.gavetas_do_grupo(grupo)
        self.assertEqual([g[G.CHAVE_PUXADOR] for g in gavetas], ['PERFIL', 'ALCA', 'PERFIL'])
        novo = next(o for o in G.frente_da_gaveta(gavetas[1]).children
                    if addon.chapas.MARCA_PUXADOR in o)
        for chave, valor in (('puxador_comprimento_mm', 180.0), ('puxador_recuo_mm', 35.0),
                             ('puxador_fracao', 0.3)):
            self.assertAlmostEqual(novo[chave], valor)

    def test_macro_nativa_registrada_e_confirmacao_sem_estado(self):
        self.assertIn(G.OBJECT_OT_mover_ancora_gaveta, addon.CLASSES)
        self.assertIn(G.OBJECT_OT_confirmar_ancora_gaveta, addon.CLASSES)
        self.assertEqual(bpy.ops.object.cabinet_confirmar_ancora_gaveta(), {'CANCELLED'})

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
