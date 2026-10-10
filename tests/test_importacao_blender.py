"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_importacao_blender.py"""
import math
import os
import sys
import unittest

import bpy
import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon


def caixa(nome, dims, centro, rot_z=0.0):
    """Malha de caixa como viria de um arquivo de fora: sem marcador."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= dims[0]
        v.co.y *= dims[1]
        v.co.z *= dims[2]
    malha = bpy.data.meshes.new(nome)
    bm.to_mesh(malha)
    bm.free()
    obj = bpy.data.objects.new(nome, malha)
    bpy.context.collection.objects.link(obj)
    obj.location = centro
    obj.rotation_euler.z = rot_z
    bpy.context.view_layer.update()
    return obj


def selecionar(*objs):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def limites(objs):
    pontos = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    return ([min(p[i] for p in pontos) for i in range(3)],
            [max(p[i] for p in pontos) for i in range(3)])



def relativo(bloco):
    """O bloco com y relativo ao 1o widget: na aba Portas ele desce para
    caber o "Criar Portas" no topo (Epico 2.3); o CONTEUDO e as posicoes
    entre os campos continuam identicos."""
    if not bloco:
        return bloco
    y0 = bloco[0][1]
    return [(b[0], b[1] - y0) + tuple(b[2:]) for b in bloco]


class TestImportacao(unittest.TestCase):
    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.context.scene.cabinet_aba = 'MODULOS'

    def assertPerto(self, a, b, casas=5):
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=casas)

    # ------------------------------------------------------ classificador
    def test_classifica_chapa_e_acessorio(self):
        placa = caixa('Placa', (0.6, 0.4, 0.018), (0, 0, 0))
        cubo = caixa('Cubo', (0.3, 0.3, 0.3), (1, 0, 0))
        pe = caixa('Pe', (0.05, 0.05, 0.1), (2, 0, 0))
        bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=0.3,
                                            location=(3, 0, 0))
        cilindro = bpy.context.object
        self.assertTrue(addon._analisar_peca(placa)['chapa'])
        for obj in (cubo, pe, cilindro):
            self.assertFalse(addon._analisar_peca(obj)['chapa'], obj.name)

    def test_lateral_em_pe_girada_vira_chapa_sem_sair_do_lugar(self):
        # REGRESSAO: a conversao lia obj.dimensions em eixos de mundo e
        # tomava Z como espessura -- esta lateral virava chapa de 30 mm.
        lateral = caixa('Lateral', (0.018, 0.4, 0.7), (1, 2, 3),
                        rot_z=math.radians(30))
        antes = limites([lateral])
        selecionar(lateral)
        self.assertEqual(bpy.ops.object.cabinet_marcar(), {'FINISHED'})
        self.assertIn(addon.MARCA_CHAPA, lateral)
        self.assertEqual(lateral.chapa_espessura_mm, 18.0)
        self.assertEqual(sorted((round(lateral.chapa_largura_mm),
                                 round(lateral.chapa_comprimento_mm))),
                         [400, 700])
        self.assertPerto(lateral.scale, (1, 1, 1))
        depois = limites([lateral])
        self.assertPerto(antes[0], depois[0])
        self.assertPerto(antes[1], depois[1])
        # local Z = espessura (invariante 1)
        z = lateral.matrix_world.to_3x3().col[2].normalized()
        self.assertAlmostEqual(abs(z.dot(Vector((math.cos(math.radians(30)),
                                                 math.sin(math.radians(30)),
                                                 0)))), 1.0, places=5)

    def test_escala_do_objeto_vira_medida(self):
        placa = caixa('Placa', (0.3, 0.4, 0.018), (0, 0, 0))
        placa.scale = (2.0, 1.0, 1.0)
        bpy.context.view_layer.update()
        selecionar(placa)
        bpy.ops.object.cabinet_marcar()
        self.assertPerto(placa.scale, (1, 1, 1))
        self.assertAlmostEqual(max(placa.chapa_largura_mm,
                                   placa.chapa_comprimento_mm), 600.0, places=2)

    def test_chapa_alinhada_continua_como_antes(self):
        placa = caixa('Placa', (0.6, 0.4, 0.018), (0, 0, 0))
        selecionar(placa)
        bpy.ops.object.cabinet_marcar()
        self.assertAlmostEqual(placa.chapa_largura_mm, 600.0, places=3)
        self.assertAlmostEqual(placa.chapa_comprimento_mm, 400.0, places=3)
        self.assertPerto(placa.rotation_euler, (0, 0, 0))

    # ------------------------------------------------------------- modulo
    def armario(self):
        """Laterais, base, tampo e um pe' cilindrico do lado direito."""
        pecas = [caixa('Lat_E', (0.018, 0.4, 0.7), (-0.291, 0, 0.35)),
                 caixa('Lat_D', (0.018, 0.4, 0.7), (0.291, 0, 0.35)),
                 caixa('Base', (0.564, 0.4, 0.018), (0, 0, 0.009)),
                 caixa('Tampo', (0.564, 0.4, 0.018), (0, 0, 0.691))]
        bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=0.08,
                                            location=(0.25, 0, 0.04))
        pe = bpy.context.object
        return pecas, pe

    def test_converter_em_modulo_separa_chapas_e_acessorios(self):
        pecas, pe = self.armario()
        selecionar(*pecas, pe)
        self.assertEqual(bpy.ops.object.cabinet_converter_modulo(), {'FINISHED'})
        conj = bpy.context.object
        self.assertIn(addon.MARCA_CONJUNTO, conj)
        self.assertEqual(set(addon._chapas_do_conjunto(conj)), set(pecas))
        self.assertIn(addon.MARCA_ACESSORIO, pe)
        self.assertNotIn(addon.MARCA_CHAPA, pe)
        self.assertEqual(pe.parent, conj)
        for peca in pecas:
            self.assertEqual(peca.chapa_espessura_mm, 18.0)

    def test_acessorio_segue_a_face_mais_proxima(self):
        pecas, pe = self.armario()
        selecionar(*pecas, pe)
        bpy.ops.object.cabinet_converter_modulo()
        conj = bpy.context.object
        antes = addon._centro_mundo(pe)
        conj.conj_largura_mm += 100     # cresce a partir da esquerda
        bpy.context.view_layer.update()
        depois = addon._centro_mundo(pe)
        # o pe' esta' perto da DIREITA: anda junto com ela
        self.assertAlmostEqual(depois.x - antes.x, 0.1, places=4)
        self.assertAlmostEqual(depois.z, antes.z, places=4)
        conj.conj_altura_mm += 200      # base parada: o pe' tambem
        bpy.context.view_layer.update()
        self.assertAlmostEqual(addon._centro_mundo(pe).z, antes.z, places=4)

    def test_sem_nenhuma_chapa_tudo_vira_chapa(self):
        a = caixa('A', (0.3, 0.3, 0.3), (0, 0, 0))
        b = caixa('B', (0.3, 0.3, 0.3), (0.3, 0, 0))
        selecionar(a, b)
        bpy.ops.object.cabinet_converter_modulo()
        self.assertIn(addon.MARCA_CHAPA, a)
        self.assertIn(addon.MARCA_CHAPA, b)

    # --------------------------------------------- porta a partir de objetos
    def porta_importada(self, x=0.0, largura=0.4, altura=0.7, z=0.35,
                        y=-0.2, puxador=True):
        placa = caixa('Placa', (largura, 0.018, altura), (x, y - 0.009, z))
        objs = [placa]
        if puxador:
            objs.append(caixa('Puxador', (0.02, 0.03, 0.15),
                              (x + largura / 2 - 0.03, y - 0.033, z)))
        selecionar(*objs)
        self.assertEqual(bpy.ops.object.cabinet_folha_de_objetos(), {'FINISHED'})
        return addon._grupo_portas(bpy.context.object), placa, objs[1:]

    def test_folha_de_objetos_fica_no_lugar_com_o_puxador(self):
        placa = caixa('Placa', (0.4, 0.018, 0.7), (0, -0.209, 0.35))
        pux = caixa('Puxador', (0.02, 0.03, 0.15), (0.17, -0.233, 0.35))
        antes = limites([placa]), limites([pux])
        selecionar(placa, pux)
        bpy.ops.object.cabinet_folha_de_objetos()
        grupo = addon._grupo_portas(placa)
        self.assertIsNotNone(grupo)
        self.assertIn(addon.MARCA_FOLHA, placa)
        self.assertEqual(addon._folhas_portas(grupo), [placa])
        self.assertEqual(pux.parent, placa)
        self.assertIn(addon.MARCA_PUXADOR, pux)
        for obj, (lo, hi) in ((placa, antes[0]), (pux, antes[1])):
            lo2, hi2 = limites([obj])
            self.assertPerto(lo, lo2, 4)
            self.assertPerto(hi, hi2, 4)
        # a frente vai para o lado do puxador (-Y)
        normal = grupo.matrix_world.to_3x3().col[2].normalized()
        self.assertAlmostEqual(normal.y, -1.0, places=5)

    def test_puxador_travado_mantem_medida_e_distancia_da_borda(self):
        grupo, placa, (pux,) = self.porta_importada()
        largura = limites([pux])[1][0] - limites([pux])[0][0]
        borda = limites([placa])[1][0] - limites([pux])[1][0]
        self.assertEqual(addon._editar_parametro_porta(
            bpy.context, grupo, 'folga_mm', 3.0), '')
        self.assertAlmostEqual(limites([pux])[1][0] - limites([pux])[0][0],
                               largura, places=5)
        self.assertAlmostEqual(limites([placa])[1][0] - limites([pux])[1][0],
                               borda, places=5)

    def test_puxador_destravado_estica_com_a_folha(self):
        grupo, placa, (pux,) = self.porta_importada()
        pux[addon.CHAVE_TRAVAS_PUXADOR] = [0, 1, 1]
        largura = limites([pux])[1][0] - limites([pux])[0][0]
        folha_antes = placa.chapa_largura_mm
        addon._editar_parametro_porta(bpy.context, grupo, 'folga_mm', 20.0)
        razao = placa.chapa_largura_mm / folha_antes
        self.assertLess(razao, 1.0)
        self.assertAlmostEqual(limites([pux])[1][0] - limites([pux])[0][0],
                               largura * razao, places=5)

    def test_vao_inverso_ida_e_volta(self):
        base = dict(abertura='GIRO', folhas=1, dobradica='RETA',
                    espessura_mm=18.0, lateral_mm=18.0, folga_mm=2.0,
                    entre_folhas_mm=3.0, afastamento_mm=4.0,
                    recuo_embutida_mm=5.0, recuo_correr_mm=30.0,
                    sobreposicao_mm=20.0, entre_planos_mm=2.0)
        for dobradica in ('RETA', 'CURVA', 'SUPER_CURVA'):
            for folhas in (1, 2):
                with self.subTest(dobradica=dobradica, folhas=folhas):
                    p = dict(base, dobradica=dobradica, folhas=folhas)
                    calculadas = addon._calcular_folhas_portas(600, 800, p)
                    pontos = [Vector(c) + Vector((sx * l, sy * a, sz * e)) / 2
                              for l, a, e, c in calculadas
                              for sx in (-1, 1) for sy in (-1, 1)
                              for sz in (-1, 1)]
                    lo = Vector(tuple(min(q[i] for q in pontos) for i in range(3)))
                    hi = Vector(tuple(max(q[i] for q in pontos) for i in range(3)))
                    largura, altura, origem = addon._vao_inverso((lo, hi), p)
                    self.assertAlmostEqual(largura, 600, places=6)
                    self.assertAlmostEqual(altura, 800, places=6)
                    self.assertPerto(origem, (0, 0, 0), 6)

    def test_porta_dupla_funde_duas_folhas(self):
        g1, p1, _ = self.porta_importada(x=-0.2015, largura=0.4)
        g2, p2, _ = self.porta_importada(x=0.2015, largura=0.4)
        externo = limites([p1, p2])
        nome_g2 = g2.name
        selecionar(g1, g2)
        self.assertEqual(bpy.ops.object.cabinet_porta_dupla(), {'FINISHED'})
        self.assertNotIn(nome_g2, bpy.data.objects)
        self.assertEqual(len(addon._folhas_portas(g1)), 2)
        self.assertAlmostEqual(g1['porta_parametros']['entre_folhas_mm'], 3.0,
                               places=3)
        lo, hi = limites(addon._folhas_portas(g1))
        self.assertPerto(lo, externo[0], 4)
        self.assertPerto(hi, externo[1], 4)

    def test_porta_dupla_recusa_alturas_diferentes(self):
        g1, _p1, _ = self.porta_importada(x=-0.2015)
        g2, _p2, _ = self.porta_importada(x=0.2015, altura=0.6)
        selecionar(g1, g2)
        self.assertEqual(bpy.ops.object.cabinet_porta_dupla(), {'CANCELLED'})
        self.assertIn(g2.name, bpy.data.objects)
        self.assertEqual(len(addon._folhas_portas(g1)), 1)

    def test_definir_frente_vira_a_porta_sem_mover(self):
        grupo, placa, (pux,) = self.porta_importada()
        antes = limites([placa]), limites([pux])
        normal = grupo.matrix_world.to_3x3().col[2].normalized()
        self.assertFalse(addon._definir_frente_porta(bpy.context, grupo, normal))
        self.assertTrue(addon._definir_frente_porta(bpy.context, grupo, -normal))
        nova = grupo.matrix_world.to_3x3().col[2].normalized()
        self.assertAlmostEqual(nova.dot(normal), -1.0, places=5)
        for obj, (lo, hi) in ((placa, antes[0]), (pux, antes[1])):
            lo2, hi2 = limites([obj])
            self.assertPerto(lo, lo2, 4)
            self.assertPerto(hi, hi2, 4)
        with self.assertRaises(ValueError):
            addon._definir_frente_porta(bpy.context, grupo, Vector((0, 0, 1)))

    # ---------------------------------------------- vincular porta + modulo
    def nicho(self):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar()
        conj = next(o for o in bpy.data.objects if addon.MARCA_CONJUNTO in o)
        bpy.context.view_layer.update()
        return conj

    def porta_no_modulo(self, conj, embutida=False):
        lo, hi = addon._limites_locais_modulo(conj)
        E = addon._caixa_do_modulo(conj)[3]
        if embutida:
            L, A = hi.x - lo.x - 2 * E, hi.z - lo.z - 2 * E
            y = lo.y + 9          # atras da face, dentro do vao
        else:
            L, A = hi.x - lo.x, hi.z - lo.z
            y = lo.y - 9          # na frente, cobrindo as laterais
        centro = conj.matrix_world @ (Vector(((lo.x + hi.x) / 2, y,
                                              (lo.z + hi.z) / 2)) / 1000)
        placa = caixa('Frente', (L / 1000, 0.018, A / 1000), centro)
        pux = caixa('Puxador', (0.02, 0.03, 0.15),
                    centro + Vector((L / 2000 - 0.04, -0.03, 0)))
        selecionar(placa, pux)
        bpy.ops.object.cabinet_folha_de_objetos()
        grupo = addon._grupo_portas(placa)
        selecionar(grupo, conj)
        self.assertTrue(addon.OBJECT_OT_vincular_porta.poll(bpy.context))
        self.assertEqual(bpy.ops.object.cabinet_vincular_porta(), {'FINISHED'})
        return grupo, placa, pux

    def test_vincular_deduz_reta_e_acompanha_o_modulo(self):
        conj = self.nicho()
        grupo, placa, pux = self.porta_no_modulo(conj)
        p = grupo['porta_parametros']
        self.assertEqual(p['dobradica'], 'RETA')
        self.assertAlmostEqual(p['folga_mm'], 0.0, places=3)
        self.assertAlmostEqual(p['afastamento_mm'], 0.0, places=3)
        self.assertEqual(grupo[addon.CHAVE_MODULO_PORTA], conj.name)
        self.assertEqual(grupo.parent, conj)
        L = addon._caixa_do_modulo(conj)[0]
        conj.conj_largura_mm = L + 200
        bpy.context.view_layer.update()
        lo, hi = limites([placa])
        self.assertAlmostEqual(hi[0] - lo[0], (L + 200) / 1000, places=4)
        # o puxador travado continua perto da borda direita
        self.assertAlmostEqual(hi[0] - limites([pux])[1][0], 0.03, places=4)

    def test_vincular_deduz_embutida(self):
        conj = self.nicho()
        grupo, _placa, _pux = self.porta_no_modulo(conj, embutida=True)
        self.assertEqual(grupo['porta_parametros']['dobradica'], 'SUPER_CURVA')

    def test_reposicionar_move_a_mesma_porta_para_o_vao_novo(self):
        conj = self.nicho()
        grupo, placa, _pux = self.porta_no_modulo(conj)
        lo, hi = addon._limites_locais_modulo(conj)
        E = addon._caixa_do_modulo(conj)[3]
        meio = (lo.z + hi.z) / 2
        a = conj.matrix_world @ (Vector((lo.x, lo.y, meio)) / 1000)
        b = conj.matrix_world @ (Vector((hi.x, lo.y, hi.z)) / 1000)
        chapa = addon._chapas_do_conjunto(conj)[0]
        ref = conj.matrix_world.to_quaternion().to_matrix()
        quantos = len([o for o in bpy.data.objects if addon.MARCA_PORTAS in o])
        self.assertEqual(bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            referencia=tuple(v for linha in ref for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name,
            objeto_a_nome=chapa.name, objeto_b_nome=chapa.name,
            centro=addon._centro_do_movel(chapa, chapa),
            grupo_alvo=grupo.name), {'FINISHED'})
        self.assertEqual(len([o for o in bpy.data.objects
                              if addon.MARCA_PORTAS in o]), quantos)
        self.assertAlmostEqual(grupo['porta_vao_altura_mm'],
                               hi.z - E - meio, places=2)
        self.assertEqual(grupo[addon.CHAVE_MODULO_PORTA], conj.name)
        self.assertEqual(addon._folhas_portas(grupo), [placa])

    # ------------------------------------------------------------ gaveta
    def test_cabecalho_tem_so_as_tres_abas(self):
        # As correntes entre as abas foram descontinuadas (pedido do
        # usuario): nenhum widget de operador no cabecalho
        for largura in (190, 320, 564):
            widgets = addon._widgets_gaveta(bpy.context, largura, 1200)
            cabecalho = widgets[:addon.WIDGETS_CABECALHO]
            self.assertEqual([w[5][0] for w in cabecalho], ['aba'] * 3)
            self.assertFalse(any(w[5] and w[5][0] == 'operador'
                                 and w[1] > 1200 - 48 for w in widgets))
            self.assertEqual([w[5][1] for w in cabecalho if w[5][0] == 'aba'],
                             ['MODULOS', 'PORTAS', 'PUXADORES'])
            fim = cabecalho[-1]
            self.assertAlmostEqual(fim[0] + fim[2], 12 + min(540, largura - 24))
        # sem selecao, as correntes nao tem o que ligar
        selecionar(caixa('X', (0.1, 0.1, 0.1), (0, 0, 0)))
        self.assertFalse(addon._poll_operador('object.cabinet_vincular_porta'))
        self.assertFalse(addon._poll_operador('object.cabinet_vincular_puxador'))

    def test_bloco_do_puxador_tem_cadeados_e_e_igual_nas_tres_abas(self):
        _grupo, _placa, (pux,) = self.porta_importada()
        selecionar(pux)
        modo, campos, dono = addon._medidas_gaveta(bpy.context)
        self.assertEqual((modo, dono), ('PUXADOR', 'puxador'))
        alvo = {'medida', 'cadeado'}

        def bloco(aba):
            bpy.context.scene.cabinet_aba = aba
            widgets = addon._widgets_gaveta(bpy.context, 320, 1400)
            return [v[:4] + (v[5][0],) for v in widgets
                    if v[5] and v[5][0] in alvo]

        # o puxador e' da aba Puxadores (pedido do usuario: cada menu
        # mostra o que vale para a selecao); nas outras, nada dele
        puxadores = bloco('PUXADORES')
        self.assertEqual(sum(1 for b in puxadores if b[4] == 'cadeado'), 3)
        self.assertEqual(bloco('PORTAS'), [])
        self.assertEqual(bloco('MODULOS'), [])
        # editar uma medida escala so' aquele eixo do puxador
        altura_antes = limites([pux])[1][2] - limites([pux])[0][2]
        self.assertEqual(bpy.ops.object.cabinet_editar_medida_gaveta(
            'EXEC_DEFAULT', dono='puxador', objeto=pux.name,
            propriedade='pux_0', valor=0.05), {'FINISHED'})
        self.assertAlmostEqual(limites([pux])[1][0] - limites([pux])[0][0],
                               0.05, places=5)
        self.assertAlmostEqual(limites([pux])[1][2] - limites([pux])[0][2],
                               altura_antes, places=5)

    def test_aba_puxadores_sem_sobreposicao(self):
        bpy.context.scene.cabinet_aba = 'PUXADORES'
        for largura in (190, 320, 564):
            caixas = [(v[0], v[1], v[2], v[3]) for v in
                      addon._widgets_gaveta(bpy.context, largura, 1400)]
            for i, (ax, ay, aw, ah) in enumerate(caixas):
                for bx, by, bw, bh in caixas[i + 1:]:
                    sobrepoe = (ax < bx + bw - 0.01 and bx < ax + aw - 0.01
                                and ay < by + bh - 0.01 and by < ay + ah - 0.01)
                    self.assertFalse(sobrepoe, 'largura %d' % largura)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestImportacao)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de importacao')
