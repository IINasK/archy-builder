"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_geometria_blender.py

Detector de geometria (pedido do usuario): quinas e ANGULOS detectados
para o snap, bordas arredondadas com as EXTREMIDADES (e o centro)
interagiveis, e a AREA da chapa para o orcamento (`geometria`).
"""
import math
import os
import sys
import unittest

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

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


def tipos(obj):
    r = GE.pontos_notaveis(obj.data)
    contagem = {}
    for p in r['pontos']:
        chave = (p['tipo'], p['angulo'])
        contagem[chave] = contagem.get(chave, 0) + 1
    return contagem, r


class TestGeometria(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        GE.esquecer()

    def test_caixa_tem_8_quinas_retas_e_area(self):
        ch = addon.chapas.nova_chapa('Caixa', 600, 400, 18, (0, 0, 0), (0, 0, 0), bpy.context)
        contagem, r = tipos(ch)
        self.assertEqual(contagem, {('QUINA', 90.0): 8})
        self.assertFalse(r['ruido'])
        area, borda = GE.medidas_da_chapa(ch)
        self.assertAlmostEqual(area, 0.24, places=6)
        self.assertAlmostEqual(borda, 2.0, places=5)          # 2 x (0,6 + 0,4)
        self.assertEqual(GE.rotulo('QUINA', 90.0), 'Quina reta')

    def test_recorte_em_l_tem_a_quina_de_dentro_reta(self):
        obj = prisma('L', [(0, 0), (0.6, 0), (0.6, 0.3), (0.3, 0.3), (0.3, 0.6), (0, 0.6)])
        contagem, _r = tipos(obj)
        # 5 cantos de fora (x2 faces) e o de DENTRO do recorte, 270 graus
        self.assertEqual(contagem, {('QUINA', 90.0): 10, ('QUINA', 270.0): 2})
        self.assertEqual(GE.rotulo('QUINA', 270.0), 'Quina reta')
        area, _b = GE.medidas_da_chapa(obj)
        self.assertAlmostEqual(area, 0.36 - 0.09, places=6)

    def test_chanfro_detecta_o_angulo(self):
        obj = prisma('Chanfro', [(0, 0), (0.6, 0), (0.6, 0.4), (0.4, 0.6), (0, 0.6)])
        contagem, _r = tipos(obj)
        self.assertEqual(contagem.get(('QUINA', 135.0)), 4)
        self.assertEqual(GE.rotulo('QUINA', 135.0), 'Angulo 135')

    def test_quina_arredondada_da_as_extremidades_e_o_centro(self):
        r = 0.05
        obj = prisma('Redonda', retangulo_arredondado(0.6, 0.4, r))
        contagem, res = tipos(obj)
        # nenhuma quina viva: so' as pontas das 4 curvas (x 2 faces) e os centros
        self.assertNotIn('QUINA', {t for t, _a in contagem})
        extremidades = [p['co'] for p in res['pontos'] if p['tipo'] == 'EXTREMIDADE']
        centros = [p['co'] for p in res['pontos'] if p['tipo'] == 'CENTRO']
        self.assertEqual(len(extremidades), 16)
        # a ponta da curva e' onde a reta comeca: (L - r, 0) e (L, r)
        for alvo in ((0.6 - r, 0.0), (0.6, r)):
            self.assertLess(min((Vector((p.x, p.y)) - Vector(alvo)).length
                                for p in extremidades), 1e-6, alvo)
        # o centro do arco de baixo a' direita e' (L - r, r), nas duas faces
        self.assertLess(min((Vector((c.x, c.y)) - Vector((0.6 - r, r))).length
                            for c in centros), 1e-6)
        # o MEIO dos arcos e' ruido (o ima nao oferece)
        self.assertEqual(len(res['ruido']), 4 * 7 * 2)
        self.assertEqual(GE.rotulo('EXTREMIDADE', None), 'Fim da curva')

    def test_frente_em_arco_area_desenvolvida(self):
        ch = addon.chapas.nova_chapa('Arco', 400, 160, 15, (0, 0, 0), (0, 0, 0), bpy.context)
        ch['chapa_arco_mm'] = 65.0
        addon.chapas.gerar_malha_chapa(ch)
        _contagem, res = tipos(ch)
        self.assertGreater(len(res['ruido']), 40)
        self.assertTrue(any(p['tipo'] == 'CENTRO' for p in res['pontos']))
        # area = o arco do MEIO da espessura x o comprimento
        raio = (200.0 ** 2 + 65.0 ** 2) / (2 * 65.0)
        arco = 2 * math.asin(200.0 / raio) * (raio - 7.5)
        area, _b = GE.medidas_da_chapa(ch)
        self.assertAlmostEqual(area, arco * 160.0 / 1e6, delta=0.0005)

    def test_ima_tira_o_meio_do_arco_e_poe_o_centro_com_rotulo(self):
        obj = prisma('Redonda', retangulo_arredondado(0.6, 0.4, 0.05))
        caixa = addon.chapas.nova_chapa('Caixa', 300, 300, 18, (2, 0, 0), (0, 0, 0), bpy.context)
        bpy.context.view_layer.update()
        alvos = dict((o.name, pts) for o, pts in addon.portas._alvos_do_ima(bpy.context))
        _contagem, res = tipos(obj)
        m = obj.matrix_world
        pontos = alvos['Redonda']
        perto = lambda alvo: min((p - alvo).length for p in pontos) < 1e-6
        # o meio dos arcos (e o meio das arestas de espessura deles) sai
        for i in res['ruido']:
            self.assertFalse(perto(m @ obj.data.vertices[i].co), i)
        # as pontas das curvas e os centros entram
        for p in res['pontos']:
            self.assertTrue(perto(m @ p['co']), p['tipo'])
        # o ponto que o ima pegar diz o que e'
        quina = caixa.matrix_world @ caixa.data.vertices[0].co
        self.assertEqual(GE.rotulo_do_ponto(quina), 'Quina reta')
        centro = next(obj.matrix_world @ p['co'] for p in res['pontos'] if p['tipo'] == 'CENTRO')
        self.assertEqual(GE.rotulo_do_ponto(centro), 'Centro do arco')
        estado = {}
        GE.marcar_rotulo(estado, quina)
        self.assertEqual(estado['rotulo_snap'], 'Quina reta')

    def test_snap_do_modulo_pega_a_ponta_da_curva_de_outro(self):
        # Ctrl ao arrastar o modulo: alem da caixa dos outros, as quinas e
        # as pontas das curvas da peca curva/modelada deles
        a = addon.modulos.criar_armario(bpy.context, 'A', 400, 700, 500, fundo=False)
        b = addon.modulos.criar_armario(bpy.context, 'B', 400, 700, 500, fundo=False)
        b.location.x = 2.0
        curva = prisma('Frente curva', retangulo_arredondado(0.4, 0.1, 0.04), chapa=False)
        curva[addon.chapas.MARCA_ACESSORIO] = 1
        curva.parent = b
        bpy.context.view_layer.update()
        quinas = addon.hud._quinas_de_snap(a)
        pontas = [co for co, tipo, _a in GE.pontos_no_mundo(curva) if tipo == 'EXTREMIDADE']
        self.assertTrue(pontas)
        for p in pontas:
            self.assertLess(min((p - q).length for q in quinas), 1e-6)

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

    def test_cache_refaz_quando_a_malha_muda(self):
        ch = addon.chapas.nova_chapa('Caixa', 600, 400, 18, (0, 0, 0), (0, 0, 0), bpy.context)
        primeiro = GE.pontos_notaveis(ch.data)
        self.assertIs(GE.pontos_notaveis(ch.data), primeiro)        # guardado
        addon.chapas._ocupado[0] = True
        try:
            ch.chapa_largura_mm = 700.0
        finally:
            addon.chapas._ocupado[0] = False
        addon.chapas.gerar_malha_chapa(ch)
        novo = GE.pontos_notaveis(ch.data)
        self.assertIsNot(novo, primeiro)
        xs = [p['co'].x for p in novo['pontos']]
        self.assertAlmostEqual(max(xs) - min(xs), 0.7, places=6)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestGeometria)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de geometria')
