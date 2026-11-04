"""Classificacao, cotas e vinculos em cenas descartaveis."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

A = addon.alvenaria
P = addon.paredes


class TestAlvenaria(unittest.TestCase):
    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add(size=4)
        self.apoio = bpy.context.object
        A.esquecer()

    def test_classifica_tipos_independentes_sem_recriar_malha(self):
        dados = self.apoio.data
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(dados)
        for i, tipo in enumerate(A.TIPOS):
            for n, face in enumerate(bm.faces):
                face.select_set(n == i)
            self.assertEqual(bpy.ops.object.cabinet_classificar_alvenaria(tipo=tipo),
                             {'FINISHED'})
        bpy.ops.object.mode_set(mode='OBJECT')
        self.assertIs(self.apoio.data, dados)
        self.assertEqual([A.superficie(self.apoio, i, (0, 0, 1)) for i in range(4)],
                         ['PAREDE', 'PISO', 'TETO', None])

    def test_alvenaria_legada_usa_normal(self):
        self.apoio[P.CHAVE_ALVENARIA] = True
        self.assertEqual([A.superficie(self.apoio, 0, n) for n in
                          ((0, -1, 0), (0, 0, 1), (0, 0, -1))],
                         list(A.TIPOS))

    def test_cotas_e_vinculo_acompanham_transformacao_rigida(self):
        obj = self.vinculado()
        antes = A.cotas(obj)
        self.assertAlmostEqual(antes['esquerda'], 1.5)
        self.assertIsNone(A.editar_cota(obj, 'esquerda', .25))
        self.assertAlmostEqual(A.cotas(obj)['esquerda'], .25)
        posicao = obj.matrix_world.translation.copy()
        self.apoio.location.x += 3
        bpy.context.view_layer.update()
        A.verificar()
        self.assertAlmostEqual(obj.matrix_world.translation.x, posicao.x + 3)
        self.assertAlmostEqual(A.cotas(obj)['esquerda'], .25)

    def test_remover_face_preserva_ultima_pose(self):
        obj = self.vinculado()
        antes = obj.matrix_world.copy()
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(self.apoio.data)
        camada = bm.faces.layers.int[A.ATR_FACE]
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f[camada]], context='FACES')
        bmesh.update_edit_mesh(self.apoio.data)
        bpy.ops.object.mode_set(mode='OBJECT')
        A.esquecer()
        A.verificar()
        self.assertTrue(obj[A.CHAVE_SEM_APOIO])
        self.assertEqual(obj.matrix_world, antes)

    def test_menu_em_tres_larguras_conserva_tipos_na_mesma_linha(self):
        tela = bpy.context.screen
        tela[A.CHAVE_ABRIR] = True
        try:
            for largura in (190, 320, 564):
                itens = []
                A.widgets_classificar(bpy.context, itens, 12, 500, largura - 24)
                self.assertEqual([v[4] for v in itens], ['Criar Alvenaria', 'Parede', 'Piso', 'Teto'])
                self.assertEqual(len({v[1] for v in itens[1:]}), 1)
                self.assertAlmostEqual(itens[-1][0] + itens[-1][2], largura - 12)
        finally:
            del tela[A.CHAVE_ABRIR]

    def vinculado(self):
        self.apoio[P.CHAVE_ALVENARIA] = True
        face = next(f for f in self.apoio.data.polygons if f.normal.y < -.9)
        obj = bpy.data.objects.new('Instalacao de prova', None)
        bpy.context.collection.objects.link(obj)
        obj[A.MARCA] = 'PROVA'
        obj['cabinet_instalacao_medidas'] = (1., 1., .1)
        A.vincular(obj, self.apoio, face.index,
                   A.referencial(Vector((0, -2, 0)), face.normal), 'PAREDE')
        bpy.context.view_layer.update()
        return obj


with tempfile.TemporaryDirectory(prefix='alvenaria_') as pasta, \
     patch.object(addon.opcoes, '_pasta_addon', return_value=pasta), \
     patch.object(addon.biblioteca, 'pasta_biblioteca', return_value=pasta):
    addon.register()
    try:
        resultado = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(TestAlvenaria))
    finally:
        addon.unregister()
    if not resultado.wasSuccessful():
        raise RuntimeError('Falha nas provas de alvenaria')
