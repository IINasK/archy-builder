"""Recortes e movimento de esquadrias arquitetonicas em cena temporaria."""
import math
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

A, E, I, P = addon.alvenaria, addon.esquadrias, addon.instalacoes, addon.paredes


class TestEsquadrias(unittest.TestCase):
    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        A.esquecer()

    def parede(self, volume=False):
        bpy.ops.mesh.primitive_plane_add(size=4, rotation=(math.pi/2, 0, 0))
        self.apoio = bpy.context.object
        if volume:
            solido = self.apoio.modifiers.new('Espessura de prova', 'SOLIDIFY')
            solido.thickness = .20
            bpy.ops.object.modifier_apply(modifier=solido.name)
        self.apoio[P.CHAVE_ALVENARIA] = True
        bpy.context.view_layer.update()
        self.indice = next(f.index for f in self.apoio.data.polygons if f.normal.z > .99)

    def instalar(self, modelo='PORTA', centro=(0, 0, 0), medidas=None):
        return I.instalar(bpy.context, modelo, self.apoio, self.indice,
                          A.referencial(centro, (0, -1, 0)), medidas)

    def raio(self, ponto=(0, -1, 0)):
        bpy.context.view_layer.update()
        dep = bpy.context.evaluated_depsgraph_get()
        inv = self.apoio.matrix_world.inverted()
        return self.apoio.ray_cast(inv @ Vector(ponto),
                                 inv.to_3x3() @ Vector((0, 1, 0)), depsgraph=dep)[0]

    def test_corta_face_plana_e_restaura_na_remocao(self):
        self.parede()
        obj = self.instalar()
        self.assertEqual(len(self.apoio.data.polygons), 1)
        self.assertFalse(self.raio())
        self.assertEqual(self.apoio.modifiers[0].solver, 'EXACT')
        bpy.context.view_layer.objects.active = obj
        self.assertEqual(bpy.ops.object.cabinet_acao_instalacao(acao='remover'), {'FINISHED'})
        self.assertTrue(self.raio())

    def test_corta_volume_e_reaproveita_um_vao_existente(self):
        self.parede(volume=True)
        self.instalar('JANELA')
        self.assertFalse(self.raio())
        bpy.context.view_layer.objects.active = self.apoio
        bpy.ops.object.modifier_apply(modifier=self.apoio.modifiers[-1].name)
        I.verificar()
        self.indice = next(f.index for f in self.apoio.data.polygons if f.normal.z > .99)
        self.instalar('JANELA')
        self.assertFalse(any(m.type == 'BOOLEAN' for m in self.apoio.modifiers))
        self.assertFalse(self.raio())

    def test_sacada_sobre_degrau_redimensiona_altura_sem_mudar_base(self):
        self.parede()
        obj = self.instalar('SACADA', centro=(0, 0, .45), medidas=(1.6, 1.6, .12))
        folha = next(o for o in obj.children if o.get(A.PECA) == 'Folha 1')
        malha = folha.data
        self.assertIsNone(I.editar_medida(obj, 1, 2.))
        bpy.context.view_layer.update()
        self.assertAlmostEqual(obj.matrix_world.translation.z - obj[A.MEDIDAS][1]/2, -.35, places=5)
        self.assertIs(folha.data, malha)
        E.abrir(obj, 0, 1.)
        self.assertGreater(folha.location.x, 0.)
        self.assertEqual(obj[E.CHAVE_ABERTURAS][1], 0.)

    def test_inverter_e_espelhar_mudam_a_folha_sem_mudar_vao(self):
        self.parede()
        obj = self.instalar()
        bpy.context.view_layer.objects.active = obj
        nome = self.apoio.modifiers[0].name
        E.abrir(obj, 0, 1.)
        self.assertFalse(E._toca_batente(obj, E._ficha(obj)[0]))
        folha = next(o for o in obj.children if o.get(A.PECA) == 'Folha 1')
        antes = folha.location.copy()
        self.assertEqual(bpy.ops.object.cabinet_acao_instalacao(acao='inverter'), {'FINISHED'})
        self.assertLess(folha.location.z, antes.z)
        self.assertEqual(bpy.ops.object.cabinet_acao_instalacao(acao='espelhar'), {'FINISHED'})
        self.assertEqual(obj[E.CHAVE_LADO], -1)
        self.assertEqual(self.apoio.modifiers[0].name, nome)

    def test_colisao_no_meio_do_giro_ignora_armario_alto_e_distante(self):
        self.parede()
        obj = self.instalar()
        bpy.context.view_layer.update()
        caixa = Vector((-.035, -.035, -.06)), Vector((.035, .035, .06))
        meio = obj.matrix_world @ Vector((.01, 0, .42))
        matriz = Matrix.Translation(meio)
        self.assertIs(E.colisao(bpy.context, None, matriz, caixa), obj)
        for delta in ((0, 0, 2), (4, 0, 0), (0, -3, 0)):
            self.assertIsNone(E.colisao(bpy.context, None, Matrix.Translation(meio+Vector(delta)), caixa))

    def test_cartoes_nao_se_sobrepoem_e_abrir_operador_tem_destino(self):
        self.parede()
        for largura in (190, 320, 564):
            itens = []
            I.widgets_modelos(bpy.context, itens, 12, 500, largura-24, 'PAREDE')
            cartoes = [v for v in itens if v[5]]
            self.assertEqual([v[5][2] for v in cartoes], list(E.MODELOS))
            self.assertTrue(all(x+w <= largura-12+.001 for x,y,w,h,_,_ in cartoes))
        self.assertTrue(hasattr(bpy.ops.object, 'cabinet_instalar'))

    def test_escala_nativa_altera_medidas_sem_esticar_o_batente(self):
        self.parede()
        obj = self.instalar()
        obj.select_set(True)
        bpy.context.view_layer.update()
        A.verificar()
        obj.scale.x = 1.3
        bpy.context.view_layer.update()
        A.verificar()
        self.assertAlmostEqual(obj[A.MEDIDAS][0], .90*1.3, places=5)
        batente = next(o for o in obj.children if o.get(A.PECA) == 'Batente esquerdo')
        self.assertAlmostEqual(batente.scale.x, E.PERFIL)


with tempfile.TemporaryDirectory(prefix='esquadrias_') as pasta, \
     patch.object(addon.opcoes, '_pasta_addon', return_value=pasta), \
     patch.object(addon.biblioteca, 'pasta_biblioteca', return_value=pasta):
    addon.register()
    try:
        resultado = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(TestEsquadrias))
    finally:
        addon.unregister()
    if not resultado.wasSuccessful():
        raise RuntimeError('Falha nas provas de esquadrias')
