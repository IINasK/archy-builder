"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_puxadores_blender.py"""
import os
import sys
import unittest
from types import SimpleNamespace

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon


def caixa_na_chapa(obj, chapa):
    """(lo, hi) em mm do objeto no referencial LOCAL da chapa."""
    bpy.context.view_layer.update()
    inversa = chapa.matrix_world.inverted()
    pontos = [inversa @ (obj.matrix_world @ Vector(c)) * 1000.0
              for c in obj.bound_box]
    return ([round(min(p[i] for p in pontos), 3) for i in range(3)],
            [round(max(p[i] for p in pontos), 3) for i in range(3)])


def malha_na_chapa(chapa):
    """(lo, hi) em mm da MALHA da chapa (com o corte do perfil)."""
    vs = [v.co * 1000.0 for v in chapa.data.vertices]
    return ([round(min(v[i] for v in vs), 3) for i in range(3)],
            [round(max(v[i] for v in vs), 3) for i in range(3)])


class TestPuxadores(unittest.TestCase):
    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def chapa(self):
        bpy.ops.object.cabinet_criar()          # 600 x 400 x 18
        return bpy.context.object

    def nicho_com_porta(self):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar()
        conj = next(o for o in bpy.data.objects if addon.chapas.MARCA_CONJUNTO in o)
        bpy.context.view_layer.update()
        L, A = conj.conj_largura_mm, conj.conj_altura_mm
        P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
        a = conj.matrix_world @ (Vector((-L / 2 + E, -P / 2, E)) / 1000.0)
        b = conj.matrix_world @ (Vector((L / 2 - E, -P / 2, A - E)) / 1000.0)
        resultado = bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            referencia=tuple(v for linha in
                             conj.matrix_world.to_quaternion().to_matrix()
                             for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name,
            frente='NEG_Y', dobradica='RETA', folhas=2)
        self.assertEqual(resultado, {'FINISHED'})
        return conj, addon.portas._portas_do_conjunto(conj)[0]

    def test_modelos_geram_as_medidas_de_exemplo(self):
        for tipo, esperado in (('ALCA', (148, 10, 30)), ('BORDA', (60, 20, 26)),
                               ('PERFIL', (500, 30, 18))):
            caixas = addon.puxadores._caixas_puxador(tipo, 18.0, 500.0 if tipo == 'PERFIL'
                                           else addon.puxadores.MODELOS_PUXADOR[tipo][1])
            medidas = tuple(round(max(c[2 * i + 1] for c in caixas)
                                  - min(c[2 * i] for c in caixas), 3)
                            for i in range(3))
            self.assertEqual(medidas, esperado, tipo)

    def test_posiciona_nas_quatro_bordas_e_nas_duas_faces(self):
        chapa = self.chapa()
        meias = {'X': 300.0, 'Y': 200.0}
        for borda in addon.puxadores.BORDAS_CHAPA:
            for face in (1, -1):
                pux = addon.puxadores.criar_puxador(bpy.context, chapa, 'ALCA', borda, face)
                lo, hi = caixa_na_chapa(pux, chapa)
                eixo = 0 if borda[0] == 'X' else 1
                sinal = 1 if borda[1] == '+' else -1
                centro = [(a + b) / 2 for a, b in zip(lo, hi)]
                # a 40 mm da linha, para dentro, centrado ao longo dela
                self.assertAlmostEqual(centro[eixo],
                                       sinal * (meias[borda[0]] - 40.0), places=3)
                self.assertAlmostEqual(centro[1 - eixo], 0.0, places=3)
                self.assertAlmostEqual(hi[1 - eixo] - lo[1 - eixo], 148.0, places=3)
                # de pe' na face escolhida: 30 mm para fora dela
                if face > 0:
                    self.assertEqual((lo[2], hi[2]), (9.0, 39.0))
                else:
                    self.assertEqual((lo[2], hi[2]), (-39.0, -9.0))
                bpy.data.objects.remove(pux, do_unlink=True)

    def test_acompanha_a_chapa_redimensionada(self):
        chapa = self.chapa()
        alca = addon.puxadores.criar_puxador(bpy.context, chapa, 'ALCA', 'X+', 1, 0.5)
        borda = addon.puxadores.criar_puxador(bpy.context, chapa, 'BORDA', 'Y+', 1, 0.25)
        x_antes = (lambda c: (c[0][0] + c[1][0]) / 2)(caixa_na_chapa(borda, chapa))
        chapa.chapa_largura_mm = 800.0
        chapa.chapa_comprimento_mm = 700.0
        lo, hi = caixa_na_chapa(alca, chapa)
        self.assertAlmostEqual((lo[0] + hi[0]) / 2, 360.0, places=3)   # 40 da borda
        self.assertAlmostEqual((lo[1] + hi[1]) / 2, 0.0, places=3)     # no meio
        self.assertAlmostEqual(hi[1] - lo[1], 148.0, places=3)         # mesmo tamanho
        lo, hi = caixa_na_chapa(borda, chapa)
        self.assertAlmostEqual(hi[1], 355.0, places=3)                 # na borda nova
        # 1/4 da borda continua 1/4: x de 150 (de 600) vira 200 (de 800)
        self.assertAlmostEqual(abs((lo[0] + hi[0]) / 2), 200.0, places=3)
        self.assertAlmostEqual(abs(x_antes), 150.0, places=3)
        # perto da ponta, a alca nunca passa da borda
        alca['puxador_fracao'] = 0.0
        addon.puxadores.posicionar_puxador(alca)
        lo, hi = caixa_na_chapa(alca, chapa)
        self.assertGreaterEqual(lo[1], -350.0 - 1e-6)

    def test_perfil_corta_a_madeira_e_a_medida_continua_nominal(self):
        # O perfil e' o modelo de aluminio do usuario (extrair_puxador.py):
        # a borda inteira, da borda nominal ate' o corte da madeira, costas
        # rentes as da folha e a frente um pouco saliente, como no modelo.
        chapa = self.chapa()
        perfil = addon.puxadores.criar_puxador(bpy.context, chapa, 'PERFIL', 'Y-', 1)
        self.assertEqual(perfil.name, 'Puxador Perfil')
        dados = addon.puxadores._dados_perfil()
        corte = dados['altura_mm']
        self.assertAlmostEqual(corte, addon.puxadores._altura_perfil_mm())
        lo, hi = caixa_na_chapa(perfil, chapa)
        self.assertEqual((lo[0], hi[0], lo[1]), (-300.0, 300.0, -200.0))
        self.assertAlmostEqual(lo[2], -9.0, delta=0.2)       # costas rentes
        self.assertTrue(9.0 < hi[2] < 11.0, hi[2])            # frente saliente
        self.assertTrue(-200.0 + corte < hi[1] < -200.0 + corte + 3.0, hi[1])
        self.assertEqual([m.name for m in perfil.data.materials],
                         ['Aluminio Escovado'])
        self.assertTrue(perfil.data.uv_layers)
        modelo = addon.puxadores._malha_modelo_perfil()
        self.assertEqual(len(perfil.data.vertices), len(modelo.vertices))
        # a malha do modelo nao se repete a cada perfil
        addon.puxadores.criar_puxador(bpy.context, chapa, 'PERFIL', 'Y+', 1)
        self.assertEqual(len([m for m in bpy.data.meshes
                              if m.get('cabinet_origem') == dados['malha']]), 1)
        self.assertEqual(len([m for m in bpy.data.materials
                              if m.get('cabinet_origem') == 'Aluminio Escovado']), 1)
        for f in [f for f in chapa.children
                  if f.get('puxador_borda') == 'Y+']:
            bpy.data.objects.remove(f, do_unlink=True)
        addon.puxadores._conferir_rebaixos()
        self.assertEqual(malha_na_chapa(chapa),
                         ([-300.0, round(-200.0 + corte, 3), -9.0],
                          [300.0, 200.0, 9.0]))
        self.assertEqual(chapa.chapa_comprimento_mm, 400.0)
        cantos = addon.hud._caixa_hud_objetos([chapa])
        alturas = [c.y * 1000 for c in cantos]
        self.assertAlmostEqual(max(alturas) - min(alturas), 400.0, places=3)
        # borda inteira tambem depois de redimensionar
        chapa.chapa_largura_mm = 900.0
        lo, hi = caixa_na_chapa(perfil, chapa)
        self.assertEqual((lo[0], hi[0]), (-450.0, 450.0))
        # outro perfil na mesma borda substitui; o corte nao dobra
        novo = addon.puxadores.criar_puxador(bpy.context, chapa, 'PERFIL', 'Y-', 1)
        self.assertEqual([f for f in chapa.children
                          if f.get('puxador_tipo') == 'PERFIL'], [novo])
        self.assertEqual(malha_na_chapa(chapa)[0][1], round(-200.0 + corte, 3))
        # apagado com X: a madeira volta
        bpy.data.objects.remove(novo, do_unlink=True)
        addon.puxadores._conferir_rebaixos()
        self.assertEqual(malha_na_chapa(chapa)[0][1], -200.0)
        self.assertNotIn('chapa_rebaixos', chapa)

    def test_porta_do_modulo_leva_os_puxadores(self):
        conj, grupo = self.nicho_com_porta()
        esquerda, direita = addon.portas._folhas_portas(grupo)
        alca = addon.puxadores.criar_puxador(bpy.context, esquerda, 'ALCA', 'X+', 1)
        perfil = addon.puxadores.criar_puxador(bpy.context, direita, 'PERFIL', 'Y+', 1)
        conj.conj_largura_mm += 400.0
        conj.conj_altura_mm += 300.0
        bpy.context.view_layer.update()
        esquerda, direita = addon.portas._folhas_portas(grupo)
        self.assertEqual(alca.parent, esquerda)
        lo, hi = caixa_na_chapa(alca, esquerda)
        self.assertAlmostEqual((lo[0] + hi[0]) / 2,
                               esquerda.chapa_largura_mm / 2 - 40.0, places=3)
        self.assertAlmostEqual((lo[1] + hi[1]) / 2, 0.0, places=3)
        lo, hi = caixa_na_chapa(perfil, direita)
        self.assertAlmostEqual(hi[0] - lo[0], direita.chapa_largura_mm, places=3)
        # porta dupla vira simples: o que sobra vai para a folha que fica
        erro = addon.portas._editar_parametro_porta(bpy.context, grupo, 'folhas', 1)
        self.assertFalse(erro)
        (unica,) = addon.portas._folhas_portas(grupo)
        self.assertEqual(alca.parent, unica)
        self.assertEqual(perfil.parent, unica)
        lo, hi = caixa_na_chapa(perfil, unica)
        self.assertAlmostEqual(hi[0] - lo[0], unica.chapa_largura_mm, places=3)
        self.assertEqual(unica.get('chapa_rebaixos'), 'Y+')

    def test_linha_snaps_e_fracao(self):
        self.assertEqual(addon.puxadores._snaps(0), [])
        self.assertEqual(addon.puxadores._snaps(1), [0.5])
        self.assertEqual(addon.puxadores._snaps(2), [1 / 3, 2 / 3])
        a, b = Vector((0, 0)), Vector((300, 0))
        self.assertAlmostEqual(addon.puxadores._fracao_na_linha(a, b, Vector((60, 40))), 0.2)
        self.assertEqual(addon.puxadores._fracao_na_linha(a, b, Vector((-50, 0))), 0.0)
        self.assertEqual(addon.puxadores._fracao_na_linha(a, b, Vector((60, 0)), 1), 0.5)
        self.assertAlmostEqual(addon.puxadores._fracao_na_linha(a, b, Vector((60, 0)), 2), 1 / 3)
        self.assertEqual(addon.puxadores._texto_fracao(0.5, 3), '1/2')
        self.assertEqual(addon.puxadores._texto_fracao(2 / 3, 2), '2/3')
        self.assertEqual(addon.puxadores._texto_fracao(0.2, 0), '20%')
        segmentos = {'Y+': (Vector((0, 100)), Vector((300, 100))),
                     'X+': (Vector((300, 0)), Vector((300, 100)))}
        self.assertEqual(addon.puxadores._borda_mais_proxima(segmentos, Vector((150, 90))), 'Y+')
        self.assertEqual(addon.puxadores._borda_mais_proxima(segmentos, Vector((290, 40))), 'X+')
        self.assertIsNone(addon.puxadores._borda_mais_proxima({}, Vector()))

    def test_face_e_bordas_da_chapa(self):
        chapa = self.chapa()
        olhar_de_frente = Vector((0, 0, -1))
        self.assertEqual(addon.puxadores._face_da_chapa(chapa, Vector((0, 0, 1)), olhar_de_frente), 1)
        self.assertEqual(addon.puxadores._face_da_chapa(chapa, Vector((0, 0, -1)), olhar_de_frente), -1)
        # face estreita: vale a grande virada para quem olha
        self.assertEqual(addon.puxadores._face_da_chapa(chapa, Vector((1, 0, 0)), olhar_de_frente), 1)
        self.assertEqual(addon.puxadores._face_da_chapa(chapa, Vector((1, 0, 0)), Vector((0, 0, 1))), -1)
        bordas = addon.puxadores._bordas_da_face(chapa, 1)
        self.assertEqual(set(bordas), set(addon.puxadores.BORDAS_CHAPA))
        a, b = bordas['Y+']
        self.assertAlmostEqual((b - a).length, 0.6, places=6)
        self.assertAlmostEqual(a.y, 0.2, places=6)
        self.assertAlmostEqual(a.z, 0.009, places=6)

    def test_bloco_de_medidas_do_puxador_parametrico(self):
        chapa = self.chapa()
        alca = addon.puxadores.criar_puxador(bpy.context, chapa, 'ALCA', 'X+', 1)
        perfil = addon.puxadores.criar_puxador(bpy.context, chapa, 'PERFIL', 'Y+', 1)
        nomes = [c[0] for c in addon.puxadores._medidas_puxador_parametrico(alca)]
        self.assertEqual(nomes, ['Comprimento', 'Recuo'])
        self.assertTrue(all(len(c) == 3 for c in       # sem cadeado
                            addon.puxadores._medidas_puxador_parametrico(alca)))
        self.assertEqual(addon.puxadores._medidas_puxador_parametrico(perfil)[0][2], '')
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        alca.select_set(True)
        bpy.context.view_layer.objects.active = alca
        for prop, valor, esperado in (('puxp_comprimento', 0.2, 200.0),
                                      ('puxp_recuo', 0.06, 60.0)):
            self.assertEqual(bpy.ops.object.cabinet_editar_medida_gaveta(
                dono='puxador', objeto=alca.name, propriedade=prop,
                valor=valor), {'FINISHED'})
        lo, hi = caixa_na_chapa(alca, chapa)
        self.assertAlmostEqual(hi[1] - lo[1], 200.0, places=3)
        self.assertAlmostEqual((lo[0] + hi[0]) / 2, 300.0 - 60.0, places=3)

    def test_aba_puxadores_modelo_e_posicionar(self):
        # Pedido do usuario: sem selecao, so' o "Criar Puxador"; o MODELO
        # aparece criando (o posicionador troca na hora) ou com o puxador
        # do add-on selecionado (troca aquele).
        cena = bpy.context.scene
        cena.cabinet_aba = 'PUXADORES'
        self.addCleanup(setattr, cena, 'cabinet_aba', 'MODULOS')
        bpy.ops.object.select_all(action='DESELECT')
        modelos = lambda ws: [v[5] for v in ws if v[5] and v[5][0] == 'escolha'
                              and v[5][1] == 'cabinet_puxador_modelo']
        self.assertEqual(modelos(addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)),
                         [])
        addon.puxadores._posicionador_puxador[0] = {'tipo': 'ALCA'}
        self.addCleanup(addon.puxadores._posicionador_puxador.__setitem__, 0, None)
        for largura in (190, 320, 564):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1400)
            escolhas = modelos(widgets)
            self.assertEqual([e[2] for e in escolhas], list(addon.puxadores.MODELOS_PUXADOR))
            self.assertEqual([e[2] for e in escolhas if e[3]], ['ALCA'])
            self.assertTrue(all(e[5] == addon.portas.ALVO_ASSISTENTE for e in escolhas))
            # no TOPO da aba, laranja, como o "Criar Portas" (aceso: criando)
            criar = [v for v in widgets if v[5] and v[5][0] == 'criar_puxador']
            self.assertEqual([v[4] for v in criar],
                             ['Posicionando o puxador... (Esc cancela)'])
            self.assertGreater(criar[0][1], max(
                v[1] for v in widgets if v[5] and v[5][0] == 'escolha'))
            caixas = [v[:4] for v in widgets]
            for i, (ax, ay, aw, ah) in enumerate(caixas):
                for bx, by, bw, bh in caixas[i + 1:]:
                    self.assertFalse(ax < bx + bw - 0.01 and bx < ax + aw - 0.01
                                     and ay < by + bh - 0.01 and by < ay + ah - 0.01,
                                     'largura %d' % largura)
        self.assertIn(addon.puxadores.OBJECT_OT_posicionar_puxador, addon.CLASSES)

    def test_trocar_o_modelo_do_puxador_selecionado(self):
        chapa = self.chapa()
        pux = addon.puxadores.criar_puxador(bpy.context, chapa, 'ALCA', 'Y-', 1)
        bpy.ops.object.select_all(action='DESELECT')
        pux.select_set(True)
        bpy.context.view_layer.objects.active = pux
        bpy.context.scene.cabinet_aba = 'PUXADORES'
        self.addCleanup(setattr, bpy.context.scene, 'cabinet_aba', 'MODULOS')
        escolhas = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)
                    if v[5] and v[5][0] == 'escolha']
        self.assertEqual([e[2] for e in escolhas if e[3]], ['ALCA'])
        self.assertTrue(all(e[5] == addon.gaveta.ALVO_PUXADOR for e in escolhas))
        addon.puxadores._trocar_modelo_puxador(pux, 'BORDA')
        self.assertEqual((pux['puxador_tipo'], pux.name),
                         ('BORDA', 'Puxador Borda'))
        self.assertEqual(malha_na_chapa(chapa)[0][1], -200.0)
        # perfil corta a madeira; voltar devolve
        addon.puxadores._trocar_modelo_puxador(pux, 'PERFIL')
        corte = addon.puxadores._altura_perfil_mm()
        self.assertEqual(malha_na_chapa(chapa)[0][1], round(-200.0 + corte, 3))
        addon.puxadores._trocar_modelo_puxador(pux, 'ALCA')
        self.assertEqual(malha_na_chapa(chapa)[0][1], -200.0)
        self.assertNotIn('Aluminio Escovado',
                         [m.name for m in pux.data.materials if m])

    def test_perfil_se_ajusta_sem_deformar_os_chanfros(self):
        # Pedido do usuario: o perfil acompanha a largura e a espessura da
        # porta, mas o chanfro/arredondado dele nao pode deformar. Cada
        # vertice do modelo so' ANDA: a ponta inteira no comprimento; na
        # secao, as costas inteiras (o trecho reto do meio acomoda).
        modelo = addon.puxadores._malha_modelo_perfil()
        dados = addon.puxadores._dados_perfil()
        corte, vao = addon.puxadores._corte_do_perfil(modelo)
        self.assertGreater(vao, 0.002)          # o trecho reto da secao
        for largura, espessura in ((600.0, 18.0), (250.0, 25.0),
                                   (900.0, 15.0)):
            chapa = addon.chapas.nova_chapa('Chapa', largura, 400.0, espessura,
                                     (0, 0, 0), (0, 0, 0), bpy.context)
            pux = addon.puxadores.criar_puxador(bpy.context, chapa, 'PERFIL', 'Y-', 1)
            self.assertEqual(len(pux.data.vertices), len(modelo.vertices))
            recua = -(espessura - dados['espessura_porta_mm']) / 1000.0
            estica = (largura - dados['comprimento_mm']) / 2000.0
            for v, m in zip(pux.data.vertices, modelo.vertices):
                d = v.co - m.co
                self.assertAlmostEqual(abs(d.x), abs(estica), places=6)
                self.assertAlmostEqual(d.y, 0.0, places=6)
                self.assertAlmostEqual(d.z, recua if m.co.z < corte else 0.0,
                                       places=6)
            # as costas do perfil continuam rentes as da porta
            self.assertAlmostEqual(min(v.co.z for v in pux.data.vertices),
                                   min(v.co.z for v in modelo.vertices) + recua,
                                   places=6)
        # porta muito mais fina que o modelo: sem vao que caiba, escala
        self.assertIsNone(addon.puxadores._ajuste_do_perfil(modelo, 10.0, 400.0)[2])

    def caixa_dos_pontos(self, pontos):
        return ([min(p[i] for p in pontos) for i in range(3)],
                [max(p[i] for p in pontos) for i in range(3)])

    def test_previa_do_puxador_e_o_arame_da_peca(self):
        # Pedido do usuario: a previa do puxador e' o wireframe dele (antes
        # so' o ponto da ancora), igual a' peca que vai nascer ali.
        chapa = self.chapa()
        addon.puxadores._malha_modelo_perfil()
        for tipo, borda in (('ALCA', 'X+'), ('BORDA', 'Y-'), ('PERFIL', 'Y+')):
            previa = addon.arame._arame_puxador(chapa, tipo, borda, 1, 0.3)
            self.assertEqual(len(previa) % 2, 0)
            pux = addon.puxadores.criar_puxador(bpy.context, chapa, tipo, borda, 1, 0.3)
            bpy.context.view_layer.update()
            cantos = [pux.matrix_world @ Vector(c) for c in pux.bound_box]
            lo, hi = self.caixa_dos_pontos(previa)
            plo, phi = self.caixa_dos_pontos(cantos)
            for a, b in zip(lo + hi, plo + phi):
                self.assertAlmostEqual(a, b, places=4, msg=tipo)
            self.assertEqual(addon.arame._arame_do_objeto_puxador(pux), previa)

    def test_alt_leva_o_puxador_a_outra_borda_do_grupo(self):
        # Pedido do usuario: Alt + arrastar a ancora leva o puxador a outra
        # linha, SO' nas chapas do grupo dele (as folhas da porta), virado
        # conforme a borda; o perfil devolve a madeira e corta a nova.
        _conj, grupo = self.nicho_com_porta()
        f0, f1 = addon.portas._folhas_portas(grupo)
        self.assertEqual(addon.puxadores._chapas_do_grupo_do_puxador(f0), [f0, f1])
        pux = addon.puxadores.criar_puxador(bpy.context, f0, 'ALCA', 'X+', 1, 0.5)
        bpy.ops.object.select_all(action='DESELECT')
        f0.select_set(True)
        self.assertEqual(addon.puxadores._puxadores_com_ancora(bpy.context), [pux])
        # a ancora e' o ponto dele NA borda
        a, b = addon.puxadores._bordas_da_face(f0, 1)['X+']
        self.assertLess((addon.puxadores._ancora_do_puxador(pux) - a.lerp(b, 0.5)).length,
                        1e-6)
        op = SimpleNamespace(puxador=pux.name)
        arrastar = addon.puxadores.OBJECT_OT_arrastar_puxador
        self.assertIn(arrastar, addon.CLASSES)
        arrastar._aplicar(op, bpy.context, f1.name, 'Y-', 1, 0.5)
        self.assertEqual((pux.parent, pux['puxador_borda']), (f1, 'Y-'))
        lo, hi = caixa_na_chapa(pux, f1)
        meia_y = f1.chapa_comprimento_mm / 2.0
        # virado para a borda nova: deitado ao longo de X, encostado em -Y
        self.assertGreater(hi[0] - lo[0], hi[1] - lo[1])
        self.assertLess(abs(lo[1] + meia_y), 50.0)
        # perfil: a madeira volta na folha velha e sai na nova
        perfil = addon.puxadores.criar_puxador(bpy.context, f0, 'PERFIL', 'Y+', 1)
        inteira = f1.chapa_comprimento_mm / 2.0
        corte = addon.puxadores._altura_perfil_mm()
        self.assertEqual(malha_na_chapa(f0)[1][1], round(inteira - corte, 3))
        arrastar._aplicar(SimpleNamespace(puxador=perfil.name), bpy.context,
                          f1.name, 'Y+', 1, 0.5)
        self.assertEqual(malha_na_chapa(f0)[1][1], round(inteira, 3))
        self.assertEqual(malha_na_chapa(f1)[1][1], round(inteira - corte, 3))


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestPuxadores)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de puxadores')
