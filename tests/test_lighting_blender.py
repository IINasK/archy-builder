"""Electrical installations, ceilings and lights in disposable scenes."""
import math
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon

A, I, L, P = addon.alvenaria, addon.instalacoes, addon.iluminacao, addon.paredes


class TestIluminacao(unittest.TestCase):
    def test_saved_pendant_roles_keep_canopy_and_vertical_drop(self):
        ceiling = self.plano('TETO', (math.pi+.35, 0, 0), z=3)
        frame = self.quadro(ceiling)
        obj = I.instalar(bpy.context, 'PENDENTE', ceiling, 0, frame)
        aliases = {'Canopy':'Canopla', 'Stem':'Haste', 'Light':'Luz', 'Diffuser':'Difusor'}
        positions = {part.name: part.matrix_basis.copy() for part in obj.children}
        for part in obj.children:
            part[A.PECA] = aliases[part[A.PECA]]
        L.posar_pendente(obj, frame)
        for part in obj.children:
            self.assertLess((part.matrix_basis.translation-positions[part.name].translation).length, 1e-7)

    def test_saved_shadow_gap_cleanup_removes_cuts_and_lights(self):
        ceiling = self.plano('TETO', (math.pi, 0, 0), z=3)
        obj = I.instalar(bpy.context, 'REBAIXO', ceiling, 0, self.quadro(ceiling))
        obj[L.LADOS] = [True, False, False, False]
        obj[L.LADOS_LUZ] = [True, False, False, False]
        L.acao_forro(obj, 'tabica')
        panel = next(part for part in obj.children if part.get(L.FORRO))
        panel.modifiers[0].name = 'Archy Builder - Tabica 1'
        for part in obj.children:
            if part.type == 'LIGHT':part[A.PECA] = 'Luz da tabica 1'
        L.acao_forro(obj, 'completo')
        self.assertEqual(len(panel.modifiers), 0)
        self.assertFalse(any(part.type=='LIGHT' for part in obj.children))

    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        A.esquecer()

    def plano(self, tipo, rotacao, z=0.):
        bpy.ops.mesh.primitive_plane_add(size=4, rotation=rotacao, location=(0, 0, z))
        obj = bpy.context.object
        obj[P.CHAVE_ALVENARIA] = True
        obj[A.CHAVE_TIPADA] = True
        camada = obj.data.attributes.new(A.ATR_TIPO, 'INT', 'FACE')
        camada.data[0].value = A.TIPOS.index(tipo) + 1
        bpy.context.view_layer.update()
        return obj

    def quadro(self, obj):
        normal = P._normal_no_mundo(obj, obj.data.polygons[0].normal)
        return A.referencial(obj.matrix_world.translation, normal)

    def test_tomada_e_interruptor_com_espelho_e_cotas(self):
        parede = self.plano('PAREDE', (math.pi/2, 0, 0))
        for modelo in ('TOMADA', 'INTERRUPTOR'):
            obj = I.instalar(bpy.context, modelo, parede, 0, self.quadro(parede))
            self.assertIn("Faceplate", [o.get(A.PECA) for o in obj.children])
            self.assertEqual(len(A.cotas(obj)), 4)
            self.assertEqual(len(parede.modifiers), 0)

    def test_spot_fura_piso_parede_e_teto_inclinado_e_orienta_luz(self):
        for tipo, rotacao in (('PISO', (0, 0, 0)), ('PAREDE', (math.pi/2, 0, 0)),
                              ('TETO', (math.pi+.24, 0, 0))):
            apoio = self.plano(tipo, rotacao)
            matriz = self.quadro(apoio)
            obj = I.instalar(bpy.context, 'SPOT_EMBUTIDO', apoio, 0, matriz)
            bpy.context.view_layer.update()
            inv = apoio.matrix_world.inverted_safe()
            avaliacao = apoio.evaluated_get(bpy.context.evaluated_depsgraph_get())
            self.assertFalse(avaliacao.ray_cast(inv @ (matriz.translation + matriz.to_3x3().col[2]),
                                                inv.to_3x3() @ -matriz.to_3x3().col[2])[0])
            luz = next(o for o in obj.children if o.type == 'LIGHT')
            direcao = luz.matrix_world.to_3x3() @ Vector((0, 0, -1))
            self.assertGreater(direcao.dot(matriz.to_3x3().col[2]), .999)

    def test_pendente_vertical_em_teto_inclinado_e_spot_sem_furo(self):
        teto = self.plano('TETO', (math.pi+.35, 0, 0), z=3)
        quadro = self.quadro(teto)
        obj = I.instalar(bpy.context, 'PENDENTE', teto, 0, quadro)
        bpy.context.view_layer.update()
        luz = next(o for o in obj.children if o.type == 'LIGHT')
        deslocamento = luz.matrix_world.translation - obj.matrix_world.translation
        self.assertAlmostEqual(deslocamento.x, 0., places=5)
        self.assertAlmostEqual(deslocamento.y, 0., places=5)
        self.assertLess(deslocamento.z, -.4)
        I.instalar(bpy.context, 'SPOT_SOBREPOSTO', teto, 0, quadro)
        self.assertEqual(len(teto.modifiers), 0)

    def test_tabica_parcial_e_luz_acompanham_rebaixo_inclinado(self):
        teto = self.plano('TETO', (math.pi+.23, 0, 0), z=3)
        obj = I.instalar(bpy.context, 'REBAIXO', teto, 0, self.quadro(teto))
        placa = next(o for o in obj.children if o.get(L.FORRO))
        self.assertEqual(len(placa.modifiers), 0)
        obj[L.LADOS] = [True, False, False, False]
        obj[L.LADOS_LUZ] = [True, False, False, False]
        self.assertTrue(L.acao_forro(obj, 'tabica'))
        self.assertEqual(len(placa.modifiers), 1)
        luz = next(o for o in obj.children if o.type == 'LIGHT')
        bpy.context.view_layer.update()
        antes = luz.matrix_world.translation.copy()
        self.assertIsNone(L.editar_forro(obj, L.PROFUNDIDADE, .40))
        bpy.context.view_layer.update()
        self.assertAlmostEqual(luz.matrix_world.translation.z - antes.z, -.28, places=5)
        self.assertTrue(L.acao_forro(obj, 'completo'))
        self.assertEqual(len(placa.modifiers), 0)
        self.assertFalse(any(o.type == 'LIGHT' for o in obj.children))

    def test_spot_do_forro_acompanha_altura_e_volta_para_teto(self):
        teto = self.plano('TETO', (math.pi, 0, 0), z=3)
        forro = I.instalar(bpy.context, 'REBAIXO', teto, 0, self.quadro(teto))
        placa = next(o for o in forro.children if o.get(L.FORRO))
        bpy.context.view_layer.update()
        spot = I.instalar(bpy.context, 'SPOT_EMBUTIDO', placa, 0, self.quadro(placa))
        bpy.context.view_layer.update()
        antes = spot.matrix_world.translation.z
        self.assertIsNone(L.editar_forro(forro, L.PROFUNDIDADE, .37))
        bpy.context.view_layer.update()
        A.verificar()
        bpy.context.view_layer.update()
        self.assertAlmostEqual(spot.matrix_world.translation.z-antes, -.25, places=5)
        self.assertEqual(len(placa.modifiers), 1)
        I.remover(forro)
        bpy.context.view_layer.update()
        self.assertIs(A.apoio_de(spot), teto)
        self.assertAlmostEqual(spot.matrix_world.translation.z, 3., places=5)
        self.assertTrue(any(m.type == 'BOOLEAN' for m in teto.modifiers))

    def test_reabrir_preserva_apoio_e_luminaria(self):
        teto = self.plano('TETO', (math.pi, 0, 0), z=3)
        obj = I.instalar(bpy.context, 'SPOT_EMBUTIDO', teto, 0, self.quadro(teto))
        nome, apoio = obj.name, teto.name
        with tempfile.TemporaryDirectory(prefix='prova_instalacao_') as pasta:
            caminho = os.path.join(pasta, 'instalacao.blend')
            bpy.ops.wm.save_as_mainfile(filepath=caminho, copy=True)
            bpy.ops.wm.open_mainfile(filepath=caminho, load_ui=False)
        addon.eventos._fim_do_desfazer()
        obj = bpy.data.objects[nome]
        teto = bpy.data.objects[apoio]
        A.verificar()
        self.assertIs(A.apoio_de(obj), teto)
        self.assertTrue(any(m.type == 'BOOLEAN' for m in teto.modifiers))

    def test_rebaixa_faces_selecionadas_com_undo_redo(self):
        self.plano('TETO', (math.pi+.2, 0, 0), z=3)
        bpy.context.preferences.edit.use_global_undo = True
        bpy.ops.ed.undo_push(message='Teto antes do rebaixo')
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        self.assertEqual(bpy.ops.object.cabinet_rebaixar_faces(), {'FINISHED'})
        self.assertEqual(bpy.context.object[A.MARCA], 'REBAIXO')
        bpy.ops.ed.undo_push(message='Forro criado')
        bpy.ops.ed.undo()
        addon.eventos._fim_do_desfazer()
        self.assertFalse(any(o.get(A.MARCA) == 'REBAIXO' for o in bpy.context.scene.objects))
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        self.assertTrue(any(o.get(A.MARCA) == 'REBAIXO' for o in bpy.context.scene.objects))

    def test_menu_separa_modelos_por_superficie_e_preserva_colunas(self):
        apoio = self.plano('TETO', (math.pi, 0, 0), z=3)
        bpy.context.scene.cabinet_aba = 'ALVENARIA'
        modelos = {tipo: set(L.MODELOS) for tipo in A.TIPOS}
        for largura in (190, 320, 564):
            for tipo, esperado in modelos.items():
                bpy.context.screen[I.CHAVE_TIPO_MENU] = tipo
                itens = addon.gaveta._widgets_aba_gaveta(bpy.context, largura, 1400, 0)
                cartoes = [v for v in itens if v[5] and v[5][:2] == ('escolha', 'modelo_instalacao')
                           and v[5][2] in L.MODELOS]
                seletores = [v for v in itens if v[5] and v[5][:2] == ('escolha', 'tipo_instalacao')]
                titulo = next(v for v in itens if v[4]=="Installations")
                self.assertLessEqual(titulo[1]+titulo[3], min(v[1] for v in seletores))
                self.assertEqual({v[5][2] for v in cartoes}, esperado)
                for x, y, w, h, _, _ in cartoes:
                    self.assertGreaterEqual(x, 12)
                    self.assertLessEqual(x+w, largura-12+.001)
        spot = I.instalar(bpy.context, 'PENDENTE', apoio, 0, self.quadro(apoio))
        bpy.context.view_layer.objects.active = spot
        A.verificar()
        for largura in (190, 320, 564):
            itens = addon.gaveta._widgets_aba_gaveta(bpy.context, largura, 1400, 0)
            cotas = [v for v in itens if v[5] and v[5][:2] == ('medida', 'instalacao')]
            self.assertEqual(len(cotas), 4)
            self.assertIn("Pendant drop", [v[5][3] for v in itens if v[5] and v[5][0] == 'medida'])


with tempfile.TemporaryDirectory(prefix='iluminacao_') as pasta, \
     patch.object(addon.opcoes, '_pasta_addon', return_value=pasta), \
     patch.object(addon.biblioteca, 'pasta_biblioteca', return_value=pasta):
    addon.register()
    try:
        resultado = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(TestIluminacao))
    finally:
        addon.unregister()
    if not resultado.wasSuccessful():
        raise RuntimeError("Lighting tests failed")
