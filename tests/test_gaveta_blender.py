"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_gaveta_blender.py"""
import os
import sys
import unittest
from types import SimpleNamespace

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon


class TestGaveta(unittest.TestCase):
    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        self.cena = bpy.context.scene
        self.cena.cabinet_aba = 'MODULOS'
        self.cena.chapa_bib_aberta = True
        self.cena.chapa_n1 = 'Armarios'
        self.cena.chapa_n2 = 'Sala'
        self.cena.chapa_n3 = 'Inferiores'

    def widgets(self):
        return addon._widgets_gaveta(bpy.context, 320, 1200)

    def test_medidas_e_wireframe_da_selecao(self):
        tipos = [a[0] for *_, a in self.widgets() if a]
        self.assertEqual(tipos.count('medida'), 3)
        self.assertIn('wireframe', tipos)
        self.assertNotIn('divisor_medidas', tipos)
        largo = addon._widgets_gaveta(bpy.context, 480, 1200)
        medidas = [v for v in largo if v[5] and v[5][0] == 'medida']
        self.assertEqual(len({v[1] for v in medidas}), 1)
        divisores = [v for v in largo if v[5]
                     and v[5][0] == 'divisor_medidas']
        self.assertEqual(len(divisores), 0)
        medio = [v for v in self.widgets() if v[5] and v[5][0] == 'medida']
        self.assertEqual(len({v[1] for v in medio}), 2)

    def test_objeto_livre_editavel(self):
        objeto = bpy.context.object
        resultado = bpy.ops.object.cabinet_editar_medida_gaveta(
            dono='livre', objeto=objeto.name,
            propriedade='dimensions_2', valor=1.25)
        self.assertEqual(resultado, {'FINISHED'})
        self.assertAlmostEqual(objeto.dimensions.z, 1.25)

    def test_edicao_inline_confirma_unidades_e_cancela(self):
        classe = addon.OBJECT_OT_editar_medida_gaveta
        objeto = bpy.context.object
        op = SimpleNamespace(valor=2.0, propriedade='dimensions_2',
                             dono='livre', objeto=objeto.name)
        op._encerrar = lambda: classe._encerrar(op)
        op.execute = lambda ctx: classe.execute(op, ctx)
        op.report = lambda *_: None
        area = SimpleNamespace(as_pointer=lambda: 123, tag_redraw=lambda: None)
        ctx = SimpleNamespace(area=area, scene=self.cena,
            window_manager=SimpleNamespace(modal_handler_add=lambda _: None))
        evento = lambda tipo, texto='': SimpleNamespace(
            type=tipo, value='PRESS', ctrl=False, unicode=texto)
        for texto, esperado in (('1250', 1.25), ('80 cm', 0.8), ('1,5 m', 1.5)):
            self.assertEqual(classe.invoke(op, ctx, None), {'RUNNING_MODAL'})
            classe.modal(op, ctx, evento('TEXTINPUT', texto))
            self.assertEqual(classe.modal(op, ctx, evento('RET')), {'FINISHED'})
            bpy.context.view_layer.update()
            self.assertAlmostEqual(objeto.dimensions.z, esperado, places=6)
            self.assertIsNone(addon._edicao_gaveta[0])
        classe.invoke(op, ctx, None)
        classe.modal(op, ctx, evento('TEXTINPUT', '900'))
        self.assertEqual(classe.modal(op, ctx, evento('ESC')), {'CANCELLED'})
        self.assertAlmostEqual(objeto.dimensions.z, 1.5)

    def test_carrossel_arraste_nao_seleciona_categoria(self):
        widgets = self.widgets()
        acao = next(v[5] for v in widgets if v[5] and v[5][0] == 'navegar')
        original = self.cena.chapa_n1
        op = SimpleNamespace(_carrossel=acao, _mouse_inicio=200,
                             _indice_inicio=0, _arrastou=False)
        ctx = SimpleNamespace(screen=bpy.context.screen,
                              area=SimpleNamespace(tag_redraw=lambda: None))
        evento = SimpleNamespace(type='MOUSEMOVE', mouse_region_x=50)
        addon.OBJECT_OT_interagir_gaveta.modal(op, ctx, evento)
        self.assertGreater(ctx.screen[acao[3]], 0)
        evento = SimpleNamespace(type='LEFTMOUSE', value='RELEASE')
        addon.OBJECT_OT_interagir_gaveta.modal(op, ctx, evento)
        self.assertEqual(original, self.cena.chapa_n1)
        ctx.screen[acao[3]] = 0

    def test_medidas_parametricas_da_chapa(self):
        bpy.ops.object.cabinet_marcar()
        tipos = [a[0] for *_, a in self.widgets() if a]
        self.assertEqual(tipos.count('medida'), 3)
        self.assertIn('auto', tipos)
        self.assertIn('wireframe', tipos)
        resultado = bpy.ops.object.cabinet_editar_medida_gaveta(
            dono='objeto', objeto=bpy.context.object.name,
            propriedade='ui_chapa_largura', valor=1.5)
        self.assertEqual(resultado, {'FINISHED'})
        self.assertAlmostEqual(bpy.context.object.chapa_largura_mm, 1500.0)

    def test_cascata_e_presets_com_acoes(self):
        widgets = self.widgets()
        tipos = [a[0] for *_, a in widgets if a]
        self.assertIn('navegar', tipos)
        self.assertEqual(tipos.count('separador'), 2)
        self.assertTrue(all(v[3] == 1 for v in widgets
                            if v[5] and v[5][0] == 'separador'))
        self.assertIn('preset', tipos)
        self.assertIn('item', tipos)
        self.assertIn('slider', tipos)
        self.assertIn('rolar_nivel', tipos)
        for nivel in (1, 2, 3):
            linhas = {v[1] for v in widgets if v[5] and
                      v[5][0] == 'navegar' and v[5][1] == nivel}
            self.assertEqual(len(linhas), 1)

    def test_desmarcar_preserva_malha_e_limpa_vinculos(self):
        bpy.ops.object.cabinet_marcar()
        obj = bpy.context.object
        malha = [tuple(v.co) for v in obj.data.vertices]
        vizinho = obj.copy()
        bpy.context.collection.objects.link(vizinho)
        vizinho['adj_x_pos'] = obj.name
        vizinho['adj_x_pos_uid'] = addon._garantir_uid(obj)
        bpy.ops.object.cabinet_marcar(alternar=True)
        self.assertNotIn(addon.MARCA_CHAPA, obj)
        self.assertFalse(obj.chapa_auto)
        self.assertEqual(malha, [tuple(v.co) for v in obj.data.vertices])
        self.assertNotIn('adj_x_pos_uid', vizinho)

    def test_aba_portas(self):
        self.cena.cabinet_aba = 'PORTAS'
        tipos = [a[0] for *_, a in self.widgets() if a]
        self.assertIn('portas', tipos)

    def test_responsividade_das_miniaturas(self):
        for largura in (190, 320, 620, 2056):
            widgets = addon._widgets_gaveta(bpy.context, largura, 1200)
            self.assertTrue(all(v[0] + v[2] <= min(largura - 12, 552)
                                for v in widgets))
            fotos = [v for v in widgets if v[5] and v[5][0] == 'preset']
            self.assertTrue(fotos)
            for x, _y, w, h, _rotulo, _acao in fotos:
                self.assertLessEqual(x + w, largura - 12 + 0.01)
                self.assertAlmostEqual(w - 10, h - 27)
                self.assertLessEqual(x + w, 552)

    def test_medidas_estreitas_e_limite_da_rolagem(self):
        largura, altura = 190, 400
        inicio = addon._widgets_gaveta(bpy.context, largura, altura,
                                       _rolagem=0)
        medidas = [v for v in inicio if v[5] and v[5][0] == 'medida']
        self.assertEqual(len({v[0] for v in medidas}), 1)
        self.assertTrue(all(v[0] + v[2] <= largura - 12 for v in medidas))
        limite = addon._limite_rolagem_gaveta(bpy.context, largura, altura)
        self.assertGreater(limite, 0)
        bpy.context.screen['cabinet_gaveta_rolagem'] = 9999
        fim = addon._widgets_gaveta(bpy.context, largura, altura)
        self.assertEqual(fim[2][1] - inicio[2][1], limite)
        bpy.context.screen['cabinet_gaveta_rolagem'] = 0


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestGaveta)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes da gaveta')
