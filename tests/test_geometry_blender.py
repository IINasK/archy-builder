"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_geometry_blender.py

A AREA da chapa para o orcamento (`geometria`). O detector de angulos saiu
na v309 (o snap e' o nativo do Blender); o snap da peca curva segue aqui.
"""
import math
import os
import sys
import unittest

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon

GE = addon.geometria


def prisma(nome, contorno, espessura=0.018, chapa=True):
    """Peca extrudada em Z a partir de um contorno (m), como a do Promob."""
    bm = bmesh.new()
    baixo = [bm.verts.new((x, y, 0.0)) for x, y in contorno]
    cima = [bm.verts.new((x, y, espessura)) for x, y in contorno]
    bm.faces.new(baixo[::-1])
    bm.faces.new(cima)
    n = len(contorno)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((baixo[i], baixo[j], cima[j], cima[i]))
    malha = bpy.data.meshes.new(nome)
    bm.to_mesh(malha)
    bm.free()
    obj = bpy.data.objects.new(nome, malha)
    bpy.context.collection.objects.link(obj)
    if chapa:
        obj[addon.chapas.MARCA_CHAPA] = 1
        addon.chapas._ocupado[0] = True
        try:
            obj.chapa_espessura_mm = espessura * 1000.0
        finally:
            addon.chapas._ocupado[0] = False
    return obj


def retangulo_arredondado(L, C, r, passos=8):
    """Contorno (m) de um retangulo com as 4 quinas arredondadas de raio r."""
    pontos = []
    for cx, cy, inicio in ((L - r, r, -90), (L - r, C - r, 0), (r, C - r, 90), (r, r, 180)):
        for k in range(passos + 1):
            a = math.radians(inicio + 90.0 * k / passos)
            pontos.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pontos


class TestGeometria(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def test_caixa_area_e_borda(self):
        ch = addon.chapas.nova_chapa('Caixa', 600, 400, 18, (0, 0, 0), (0, 0, 0), bpy.context)
        area, borda = GE.medidas_da_chapa(ch)
        self.assertAlmostEqual(area, 0.24, places=6)
        self.assertAlmostEqual(borda, 2.0, places=5)          # 2 x (0,6 + 0,4)

    def test_recorte_em_l_area(self):
        obj = prisma('L', [(0, 0), (0.6, 0), (0.6, 0.3), (0.3, 0.3), (0.3, 0.6), (0, 0.6)])
        area, _b = GE.medidas_da_chapa(obj)
        self.assertAlmostEqual(area, 0.36 - 0.09, places=6)

    def test_frente_em_arco_area_desenvolvida(self):
        ch = addon.chapas.nova_chapa('Arco', 400, 160, 15, (0, 0, 0), (0, 0, 0), bpy.context)
        ch['chapa_arco_mm'] = 65.0
        addon.chapas.gerar_malha_chapa(ch)
        # area = o arco do MEIO da espessura x o comprimento
        raio = (200.0 ** 2 + 65.0 ** 2) / (2 * 65.0)
        arco = 2 * math.asin(200.0 / raio) * (raio - 7.5)
        area, _b = GE.medidas_da_chapa(ch)
        self.assertAlmostEqual(area, arco * 160.0 / 1e6, delta=0.0005)

    def test_snap_do_modulo_pega_a_ponta_da_curva_de_outro(self):
        # Mover o modulo pela quina: o snap NATIVO enxerga a peca curva/
        # modelada do outro (as pontas da curva sao vertices dela) e nao as
        # pecas do proprio modulo.
        from types import SimpleNamespace
        a = addon.modulos.criar_armario(bpy.context, 'A', 400, 700, 500, fundo=False)
        b = addon.modulos.criar_armario(bpy.context, 'B', 400, 700, 500, fundo=False)
        b.location.x = 2.0
        curva = prisma('Frente curva', retangulo_arredondado(0.4, 0.1, 0.04), chapa=False)
        curva[addon.chapas.MARCA_ACESSORIO] = 1
        curva.parent = b
        bpy.context.view_layer.update()
        contexto = SimpleNamespace(
            visible_objects=bpy.context.visible_objects, scene=bpy.context.scene,
            region=SimpleNamespace(as_pointer=lambda: 1),
            area=SimpleNamespace(as_pointer=lambda: 2),
            space_data=SimpleNamespace(overlay=SimpleNamespace(show_cursor=True)))
        self.addCleanup(addon.hud._terminar_quina_nativa)
        addon.hud._preparar_quina_nativa(contexto, a, a.matrix_world.translation.copy(),
                                         a.matrix_world.copy())
        self.assertFalse(curva.hide_select)
        self.assertTrue(all(o.hide_select for o in addon.modulos._chapas_do_conjunto(a)))

    def test_area_do_modulo_e_operador(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Balcao', 800, 700, 560, fundo=True)
        r = GE.areas([conj])
        nomes = {p[0] for p in r['pecas']}
        self.assertEqual(len(nomes), len(addon.modulos._chapas_do_conjunto(conj)))
        esperado = sum(c.chapa_largura_mm * c.chapa_comprimento_mm / 1e6
                       for c in addon.modulos._chapas_do_conjunto(conj))
        self.assertAlmostEqual(r['total_m2'], esperado, places=5)
        self.assertEqual(sum(r['por_material'].values()), r['total_m2'])
        for o in bpy.context.selected_objects:
            o.select_set(False)
        conj.select_set(True)
        bpy.context.view_layer.objects.active = conj
        self.assertEqual(bpy.ops.object.cabinet_calcular_areas(), {'FINISHED'})


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestGeometria)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de geometria')
