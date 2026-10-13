"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_formas_blender.py

Formas de planta (pedido do usuario): o modulo do Promob que nao e' caixa
-- canto em L, diagonal (triangular) e curvo -- tem a linha branca da HUD
seguindo a planta; a profundidade de CADA lado (P1/P2) muda sozinha, o
raio R da diagonal/curva e' editavel e L/P totais esticam sem deformar o
canto. Os modulos saem de DXFs no formato do Promob, como os de verdade.
"""
import math
import os
import sys
import tempfile
import unittest

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

F = addon.formas


def prisma(contorno, z0, z1, convexo=True):
    """Peca em pe' de um contorno 2D (mm): tampas em leque (convexo) e
    laterais em quadrados -- polyface de ate' 4 vertices, como no DXF."""
    n = len(contorno)
    vs = [(x, y, z0) for x, y in contorno] + [(x, y, z1) for x, y in contorno]
    faces = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    if convexo:
        faces += [(0, i + 1, i) for i in range(1, n - 1)]
        faces += [(n, n + i, n + i + 1) for i in range(1, n - 1)]
    return vs, faces


def faixa(externo, interno, z0, z1):
    """Prisma de uma FAIXA (porta curva): tampas em quadrados entre o
    contorno de fora e o de dentro."""
    vs, faces = prisma(externo + interno[::-1], z0, z1, convexo=False)
    n, m = len(externo) + len(interno), len(externo)
    for i in range(m - 1):
        a, b = i, i + 1
        c, d = n - 1 - (i + 1), n - 1 - i
        faces += [(a, b, c, d), (n + a, n + d, n + c, n + b)]
    return vs, faces


def caixa(x0, y0, z0, x1, y1, z1):
    return prisma([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1)


def arco(cx, cy, raio, de, ate, passos=12):
    return [(cx + raio * math.cos(math.radians(de + (ate - de) * i / passos)),
             cy + raio * math.sin(math.radians(de + (ate - de) * i / passos)))
            for i in range(passos + 1)]


def dxf(pecas, piso=True):
    """[(vertices, faces)] -> caminho de um DXF do Promob (camada = peca)."""
    out = ['0', 'SECTION', '2', 'ENTITIES']
    if piso:
        pecas = [caixa(-2000, -2000, -5, 3000, 3000, 0)] + list(pecas)
    for n, (vertices, faces) in enumerate(pecas):
        camada = 'LAYER%d' % n
        out += ['0', 'POLYLINE', '8', camada, '66', '1', '70', '64']
        for p in vertices:
            out += ['0', 'VERTEX', '8', camada, '10', str(p[0]), '20', str(p[1]),
                    '30', str(p[2]), '70', '192']
        for face in faces:
            out += ['0', 'VERTEX', '8', camada, '10', '0', '20', '0', '30', '0', '70', '128']
            for k, indice in enumerate(face):
                out += ['7%d' % (k + 1), str(indice + 1)]
        out += ['0', 'SEQEND', '8', camada]
    out += ['0', 'ENDSEC', '0', 'EOF']
    caminho = os.path.join(tempfile.mkdtemp(), 'Teste.dxf')
    with open(caminho, 'w', encoding='latin1') as f:
        f.write('\n'.join(out) + '\n')
    return caminho


def importar(pecas):
    modulos, _info = addon.importacao.importar_dxf_promob(
        bpy.context, dxf(pecas), 'Teste', na_origem=True)
    return modulos[0]


def canto_em_l():
    """Canto 900 x 900, bracos de 500 (recorte de 400 na quina de tras
    a direita, x/y maximos), 15 mm, 700 de altura."""
    l_base = [(0, 0), (900, 0), (900, 500), (500, 500), (500, 900), (0, 900)]
    vs, faces = prisma(l_base, 0, 15, convexo=False)
    n = len(l_base)
    faces += [(0, 3, 2, 1), (0, 5, 4, 3), (n, n + 1, n + 2, n + 3), (n, n + 3, n + 4, n + 5)]
    return importar([
        (vs, faces),
        caixa(0, 0, 15, 15, 900, 700),            # lateral esquerda
        caixa(15, 0, 15, 885, 15, 700),           # costas
        caixa(885, 0, 15, 900, 500, 700),         # ponta do braco A
        caixa(0, 885, 15, 500, 900, 700),         # ponta do braco B
        caixa(500, 485, 15, 885, 500, 700),       # face interna do braco A
        caixa(485, 500, 15, 500, 885, 700),       # face interna do braco B
    ])


def canto_diagonal():
    """Canto 900 x 900 com a quina (900, 900) cortada por uma porta
    diagonal: pernas de 350."""
    contorno = [(0, 0), (900, 0), (900, 550), (550, 900), (0, 900)]
    d = Vector((-350, 350)).normalized()
    normal = Vector((d.y, -d.x)) * 15          # para fora
    a, b = Vector((900, 550)), Vector((550, 900))
    porta = [tuple(a), tuple(b), tuple(b - normal), tuple(a - normal)]
    return importar([
        prisma(contorno, 0, 15),
        caixa(0, 0, 15, 15, 900, 700),
        caixa(15, 0, 15, 885, 15, 700),
        caixa(885, 15, 15, 900, 550, 700),
        caixa(15, 885, 15, 550, 900, 700),
        prisma(porta, 15, 700),
    ])


def diagonal_inteira():
    """Modulo 900 x 600 cuja ESQUERDA e' uma diagonal inteira (o print do
    usuario): da quina de tras (0, 600) ate' a frente em x = 400."""
    contorno = [(400, 0), (900, 0), (900, 600), (0, 600)]
    d = Vector((-400, 600)).normalized()
    normal = Vector((-d.y, d.x)) * 15          # para fora (esquerda)
    a, b = Vector((400, 0)), Vector((0, 600))
    lateral = [tuple(a), tuple(b), tuple(b - normal), tuple(a - normal)]
    return importar([
        prisma(contorno, 0, 15),
        caixa(415, 0, 15, 885, 15, 700),          # frente reta
        caixa(885, 0, 15, 900, 600, 700),         # lateral direita
        caixa(30, 585, 15, 885, 600, 700),        # costas
        prisma(lateral, 15, 700),
    ])


def cantoneira_de_ponta():
    """A cantoneira do Promob (print do usuario): 300 x 550, prateleiras
    triangulares que acabam na FACE DE DENTRO da lateral direita de 15 --
    a ponta nao e' afiada, fica a espessura dela (285 a 300)."""
    prateleira = [(285, 0), (285, 535), (0, 535), (0, 299)]
    pecas = [prisma(prateleira, z, z + 15) for z in (3, 346, 688)]
    pecas += [caixa(285, 0, 0, 300, 550, 706),       # lateral direita
              caixa(0, 535, 0, 285, 550, 706)]       # costas
    return importar(pecas)


def cantoneira(com_porta=False):
    """Prateleiras de 300 x 550 com a quina (0, 0) redonda, raio 150;
    lateral e costas do lado oposto."""
    contorno = arco(150, 150, 150, 180, 270) + [(300, 0), (300, 550), (0, 550)]
    pecas = [prisma(contorno, z, z + 15) for z in (0, 340, 685)]
    pecas += [caixa(300, 0, 0, 315, 565, 700), caixa(0, 550, 0, 300, 565, 700)]
    if com_porta:
        pecas.append(faixa(arco(150, 150, 150, 180, 270), arco(150, 150, 135, 180, 270), 15, 685))
    return importar(pecas)


class TestFormas(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        F.esquecer()

    def medidas(self, conj):
        forma = F.forma_do_modulo(conj)
        return {s['chave']: round(F.valor(conj, s['chave']), 1)
                for s in F.segmentos(forma) if s['chave']}

    def espessuras(self, conj):
        return sorted({round(c.chapa_espessura_mm, 2)
                       for c in addon.modulos._chapas_do_conjunto(conj)})

    def test_canto_em_l_e_reconhecido_pela_planta(self):
        conj = canto_em_l()
        forma = F.forma_do_modulo(conj)
        self.assertIsNotNone(forma)
        tipos = [f and f['tipo'] for f in forma['cantos']]
        self.assertEqual(tipos, [None, None, 'RECORTE', None])
        self.assertAlmostEqual(forma['cantos'][2]['a'], 400.0, delta=0.5)
        self.assertAlmostEqual(forma['cantos'][2]['b'], 400.0, delta=0.5)
        m = self.medidas(conj)
        self.assertEqual(m[('L',)], 900.0)
        self.assertEqual(m[('P',)], 900.0)
        self.assertEqual(m[('P1', 2)], 500.0)      # profundidade do braco A
        self.assertEqual(m[('P2', 2)], 500.0)      # do braco B

    def test_caixa_comum_nao_tem_forma(self):
        conj = importar([caixa(0, 0, 0, 15, 550, 700), caixa(585, 0, 0, 600, 550, 700),
                         caixa(15, 0, 0, 585, 550, 15), caixa(15, 535, 15, 585, 550, 700)])
        self.assertIsNone(F.forma_do_modulo(conj))
        geometria = addon.hud._geometria_do_item(conj, 'GRUPO',
                                                 addon.modulos._chapas_do_conjunto(conj))
        self.assertFalse(any(l['tipo'] in ('forma', 'contorno_forma')
                             for l in geometria['linhas']))

    def test_profundidade_de_cada_lado_muda_sozinha(self):
        conj = canto_em_l()
        F.aplicar(bpy.context, conj, ('P1', 2), 650.0)
        m = self.medidas(conj)
        self.assertEqual(m[('P1', 2)], 650.0)
        self.assertEqual(m[('P2', 2)], 500.0)      # o outro braco nao mexe
        self.assertEqual((m[('L',)], m[('P',)]), (900.0, 900.0))
        # a face interna do braco A so' andou (inteira); a do B encurtou
        medidas = sorted(sorted((round(c.chapa_largura_mm), round(c.chapa_comprimento_mm)))
                         for c in addon.modulos._chapas_do_conjunto(conj))
        self.assertIn([385, 685], medidas)
        self.assertIn([235, 685], medidas)
        F.aplicar(bpy.context, conj, ('P2', 2), 420.0)
        m = self.medidas(conj)
        self.assertEqual((m[('P1', 2)], m[('P2', 2)]), (650.0, 420.0))
        self.assertEqual(self.espessuras(conj), [15.0])

    def test_total_estica_sem_mudar_os_bracos(self):
        conj = canto_em_l()
        F.aplicar(bpy.context, conj, ('L',), 1100.0, 'min')
        m = self.medidas(conj)
        self.assertEqual(m[('L',)], 1100.0)
        self.assertEqual((m[('P1', 2)], m[('P2', 2)]), (500.0, 500.0))
        F.aplicar(bpy.context, conj, ('P',), 1000.0, 'max')
        m = self.medidas(conj)
        self.assertEqual(m[('P',)], 1000.0)
        self.assertEqual((m[('P1', 2)], m[('P2', 2)]), (500.0, 500.0))
        self.assertEqual(self.espessuras(conj), [15.0])

    def test_diagonal_gira_e_estica_com_o_lado(self):
        conj = canto_diagonal()
        forma = F.forma_do_modulo(conj)
        self.assertEqual(forma['cantos'][2]['tipo'], 'CHANFRO')
        self.assertAlmostEqual(F.valor(conj, ('R', 2)), 350.0, delta=2.0)
        def eixo(c):
            v = c.matrix_world.to_3x3().col[0].normalized()
            return Vector((v.x, v.y)).normalized() if v.xy.length > 1e-6 else Vector((1.0, 0.0))
        porta = max(addon.modulos._chapas_do_conjunto(conj),
                    key=lambda c: abs(eixo(c).x * eixo(c).y))
        antes = eixo(porta)
        F.aplicar(bpy.context, conj, ('P1', 2), 650.0)
        m = self.medidas(conj)
        self.assertAlmostEqual(m[('P1', 2)], 650.0, delta=1.0)
        self.assertAlmostEqual(m[('P2', 2)], 550.0, delta=1.0)
        # a porta GIROU (ponta foi junto com o lado) e continua 15 mm
        self.assertGreater(abs(eixo(porta).angle_signed(antes)), math.radians(5))
        self.assertEqual(self.espessuras(conj), [15.0])
        self.assertTrue(addon.chapas._malha_e_caixa(porta.data))
        # R deixa as duas pernas iguais
        F.aplicar(bpy.context, conj, ('R', 2), 300.0)
        f = F.forma_do_modulo(conj)['cantos'][2]
        self.assertAlmostEqual(f['a'], 300.0, delta=2.0)
        self.assertAlmostEqual(f['b'], 300.0, delta=2.0)

    def test_angulo_e_campos_do_formato_no_menu(self):
        # pedido do usuario: as medidas novas (P1, P2, raio e o ANGULO da
        # quina) no menu da esquerda; no angulo a frente do canto (P2) fica
        conj = canto_diagonal()
        self.assertAlmostEqual(F.valor(conj, ('ANG', 2)), 45.0, delta=0.5)
        F.aplicar(bpy.context, conj, ('ANG', 2), 30.0)
        self.assertAlmostEqual(F.valor(conj, ('ANG', 2)), 30.0, delta=1.0)
        self.assertAlmostEqual(F.valor(conj, ('P2', 2)), 550.0, delta=1.0)
        for o in bpy.context.selected_objects:
            o.select_set(False)
        conj.select_set(True)
        bpy.context.view_layer.objects.active = conj
        bpy.context.scene.cabinet_aba = 'MODULOS'
        acoes = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 480, 1400) if v[5]]
        props = {a[2] for a in acoes if a[0] == 'medida' and a[1] == 'forma'}
        self.assertEqual(props, {'P1:2', 'P2:2', 'R:2'})
        self.assertTrue(any(a[0] == 'contador' and a[1] == 'forma_angulo_2' for a in acoes))
        ev = addon.gaveta_eventos
        self.assertIsNone(ev.aplicar_medida(bpy.context, 'forma', conj.name, 'P1:2', 0.6))
        self.assertAlmostEqual(F.valor(conj, ('P1', 2)), 600.0, delta=1.0)
        self.assertIsNone(ev._aplicar_contador(
            bpy.context, ('contador', 'forma_angulo_2', 40, 5, 85, conj.name), 40))
        self.assertAlmostEqual(F.valor(conj, ('ANG', 2)), 40.0, delta=1.0)
        # canto em L: so' P1 e P2 (sem raio nem angulo)
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        conj = canto_em_l()
        conj.select_set(True)
        bpy.context.view_layer.objects.active = conj
        acoes = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 480, 1400) if v[5]]
        self.assertEqual({a[2] for a in acoes if a[0] == 'medida' and a[1] == 'forma'},
                         {'P1:2', 'P2:2'})
        self.assertFalse(any(a[0] == 'contador' and a[1].startswith('forma_') for a in acoes))

    def test_raio_da_curva_e_editavel(self):
        conj = cantoneira(com_porta=True)
        forma = F.forma_do_modulo(conj)
        self.assertEqual(forma['cantos'][0]['tipo'], 'CURVA')
        self.assertAlmostEqual(F.valor(conj, ('R', 0)), 150.0, delta=3.0)
        curva = next(o for o in conj.children if F.MARCA_CURVA in o)
        F.aplicar(bpy.context, conj, ('R', 0), 220.0)
        self.assertAlmostEqual(F.valor(conj, ('R', 0)), 220.0, delta=3.0)
        # a porta curva foi junto: o lado de fora no arco novo, a mesma
        # espessura (15 mm) ate' o de dentro
        lo = F.forma_do_modulo(conj)['lo']
        inversa = F.matriz_do_modulo(conj).inverted()
        centro = Vector((lo.x + 220.0, lo.y + 220.0))
        raios = [((inversa @ curva.matrix_world @ v.co * 1000.0).xy - centro).length
                 for v in curva.data.vertices]
        self.assertAlmostEqual(max(raios), 220.0, delta=1.0)
        self.assertAlmostEqual(min(raios), 205.0, delta=1.0)
        # o raio nao passa do primeiro vertice reto (a lateral)
        F.aplicar(bpy.context, conj, ('R', 0), 2000.0)
        self.assertLess(F.valor(conj, ('R', 0)), 300.0)

    def test_hud_desenha_a_planta_e_edita_cada_lado(self):
        conj = canto_em_l()
        chapas = addon.modulos._chapas_do_conjunto(conj)
        geometria = addon.hud._geometria_do_item(conj, 'GRUPO', chapas)
        letras = {l.get('letra') for l in geometria['linhas']
                  if l['tipo'] in ('forma', 'medida')}
        self.assertTrue({'L', 'P', 'A', 'P1', 'P2'} <= letras, letras)
        # nenhuma linha passa pela quina que falta (900, 900)
        inversa = F.matriz_do_modulo(conj).inverted()
        forma = F.forma_do_modulo(conj)
        vazia = Vector((forma['hi'].x, forma['hi'].y))
        for linha in geometria['linhas']:
            for p in linha['pontos']:
                self.assertGreater((((inversa @ p) * 1000.0).xy - vazia).length, 1.0)
        # clicar na linha do P1 (vista de cima) e digitar
        projetar = lambda p: (inversa @ p).xy * 1000.0
        p1 = next(l for l in geometria['linhas'] if l.get('letra') == 'P1')
        meio = (projetar(p1['pontos'][0]) + projetar(p1['pontos'][1])) / 2.0
        alvo = addon.hud._acertar_linhas_hud(geometria, meio, projetar, cantos=False)
        self.assertEqual(alvo['tipo'], 'forma')
        self.assertEqual(alvo['face'], ('P1', 2))
        self.assertAlmostEqual(addon.hud._valor_hud(alvo), 500.0, delta=0.5)
        addon.hud._aplicar_valor_hud(bpy.context, alvo, 600.0)
        self.assertAlmostEqual(addon.hud._valor_hud(alvo), 600.0, delta=0.5)
        # o L total tem lado (quina parada) como a caixa comum
        linha_l = next(l for l in geometria['linhas'] if l.get('letra') == 'L')
        perto_do_min = projetar(linha_l['pontos'][0]) + Vector((5.0, 0.0))
        alvo = addon.hud._acertar_linhas_hud(geometria, perto_do_min, projetar, cantos=False)
        self.assertEqual(alvo.get('lado'), 'min')

    def test_diagonal_do_lado_inteiro_segue_a_planta_com_os_angulos(self):
        # print do usuario: a diagonal tomava o lado INTEIRO e a linha
        # branca fechava a caixa; agora segue a diagonal e mostra o ARCO do
        # angulo nas duas pontas dela (editavel: clicar digita)
        conj = diagonal_inteira()
        forma = F.forma_do_modulo(conj)
        self.assertIsNotNone(forma)
        f = forma['cantos'][0]
        self.assertEqual(f['tipo'], 'CHANFRO')
        # a lateral passa uns mm da quina de tras: a diagonal para onde a
        # PECA para e o resto e' a ponta da chapa
        self.assertGreater(f['b'], forma['hi'].y - forma['lo'].y - F.TOL_FORMA_MM)
        self.assertEqual(sum(1 for c in forma['cantos'] if c), 1)
        # nenhum lado de comprimento zero na quina de tras
        for seg in F.segmentos(forma):
            self.assertGreater((Vector(seg['a']) - Vector(seg['b'])).length, 1.0)
        chapas = addon.modulos._chapas_do_conjunto(conj)
        geometria = addon.hud._geometria_do_item(conj, 'GRUPO', chapas)
        arcos = [l for l in geometria['linhas'] if l.get('angulo')]
        self.assertEqual(sorted(l['face'] for l in arcos), [('ANG', 0, 'A'), ('ANG', 0, 'B')])
        # angulos de DENTRO da planta: na frente 180 - t; na quina de tras
        # (o vizinho ali e' a costa) o proprio t -- somam 180
        t = math.degrees(math.atan2(f['b'], f['a']))
        frente = next(l for l in arcos if l['face'][2] == 'A')
        quina = next(l for l in arcos if l['face'][2] == 'B')
        self.assertAlmostEqual(addon.hud._valor_hud(frente), 180.0 - t, delta=0.5)
        self.assertAlmostEqual(addon.hud._valor_hud(quina), t, delta=0.5)
        # o arco de tras fica DENTRO da planta (nao sai pela quina)
        inversa = F.matriz_do_modulo(conj).inverted()
        for p in quina['pontos']:
            q = (inversa @ p) * 1000.0
            self.assertLessEqual(q.y, forma['hi'].y + 0.5)
            self.assertGreaterEqual(q.x, forma['lo'].x - 0.5)
        # o mouse sobre o arco pega o arco (linha de varios trechos)
        inversa = F.matriz_do_modulo(conj).inverted()
        projetar = lambda p: (inversa @ p).xy * 1000.0
        meio = projetar(frente['pontos'][len(frente['pontos']) // 2])
        alvo = addon.hud._acertar_linhas_hud(geometria, meio, projetar, cantos=False)
        self.assertEqual(alvo['face'], ('ANG', 0, 'A'))
        # digitar 135 na frente: o lado inteiro fica, a frente anda
        addon.hud._aplicar_valor_hud(bpy.context, alvo, 135.0)
        F.esquecer()
        novo = F.forma_do_modulo(conj)
        # (a espessura da lateral girada passa uns mm da caixa)
        self.assertAlmostEqual(novo['cantos'][0]['b'], f['b'], delta=3.0)
        self.assertAlmostEqual(addon.hud._valor_hud(alvo), 135.0, delta=1.0)

    def test_diagonal_que_acaba_na_espessura_da_chapa(self):
        # print do usuario: a diagonal nao fecha numa quina afiada, acaba na
        # espessura da lateral. Ela para ONDE A PECA PARA (285, nao 300), o
        # trecho da espessura e' so' contorno, e o arco mede com a LATERAL
        conj = cantoneira_de_ponta()
        forma = F.forma_do_modulo(conj)
        f = forma['cantos'][0]
        self.assertEqual(f['tipo'], 'CHANFRO')
        self.assertAlmostEqual(f['a'], 285.0, delta=1.5)
        self.assertAlmostEqual(f['b'], 299.0, delta=1.5)
        curtos = [seg for seg in F.segmentos(forma)
                  if (Vector(seg['a']) - Vector(seg['b'])).length < F.ESPESSURA_PONTA_MM]
        self.assertTrue(curtos)
        self.assertTrue(all(seg['chave'] is None for seg in curtos))
        geometria = addon.hud._geometria_do_item(
            conj, 'GRUPO', addon.modulos._chapas_do_conjunto(conj))
        arcos = {l['face'][2]: l for l in geometria['linhas'] if l.get('angulo')}
        ponta = math.degrees(math.atan2(f['a'], f['b']))      # ~44 graus
        self.assertAlmostEqual(addon.hud._valor_hud(arcos['A']), ponta, delta=0.5)
        self.assertAlmostEqual(addon.hud._valor_hud(arcos['B']), 180.0 - ponta, delta=0.5)
        # o arco e' PEQUENO e colado na quina (pedido do usuario: a 70 mm ele
        # atravessava a peca): sem viewport, RAIO_ARCO_ANGULO_MM em volta dela
        for arco in arcos.values():
            raios = [(p - arco['vertice']).length * 1000.0 for p in arco['pontos']]
            self.assertLessEqual(max(raios), addon.hud.RAIO_ARCO_ANGULO_MM + 0.01)
            self.assertAlmostEqual(max(raios), min(raios), places=3)
        # o arco da ponta fica DENTRO da prateleira (nao na quina de fora)
        inversa = F.matriz_do_modulo(conj).inverted()
        for p in arcos['A']['pontos']:
            q = (inversa @ p) * 1000.0
            self.assertLessEqual(q.x, forma['lo'].x + f['a'] + 0.5)
        # e a quina AFIADA (prateleira triangular, sem lateral) vai ate' a
        # quina: as duas pernas sao os lados inteiros
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        F.esquecer()
        triangulo = [(0, 0), (300, 0), (0, 550)]
        # uma chapa no canto de dentro une as prateleiras sem tocar a ponta
        conj = importar([prisma(triangulo, z, z + 15) for z in (3, 346, 688)]
                        + [caixa(0, 0, 0, 100, 15, 706)])
        forma = F.forma_do_modulo(conj)
        f = next(c for c in forma['cantos'] if c)
        self.assertEqual(f['tipo'], 'CHANFRO')
        self.assertAlmostEqual(f['a'], 300.0, delta=0.01)
        self.assertAlmostEqual(f['b'], 550.0, delta=0.01)
        geometria = addon.hud._geometria_do_item(
            conj, 'GRUPO', addon.modulos._chapas_do_conjunto(conj))
        angulos = sorted(round(addon.hud._valor_hud(l)) for l in geometria['linhas']
                         if l.get('angulo'))
        self.assertEqual(angulos, sorted([round(math.degrees(math.atan2(300, 550))),
                                          round(math.degrees(math.atan2(550, 300)))]))

    def test_rotulos_da_forma_aparecem(self):
        conj = cantoneira()
        geometria = addon.hud._geometria_do_item(conj, 'GRUPO',
                                                 addon.modulos._chapas_do_conjunto(conj))
        arco_r = [l for l in geometria['linhas'] if l.get('letra') == 'R']
        self.assertGreater(len(arco_r), 4)         # o arco em segmentos
        self.assertTrue(all(l['face'] == ('R', 0) for l in arco_r))
        self.assertTrue(all(l.get('direcao') is not None for l in arco_r))

    def test_cache_segue_a_geometria(self):
        conj = canto_em_l()
        primeira = F.forma_do_modulo(conj)
        self.assertIs(F.forma_do_modulo(conj), primeira)
        F.aplicar(bpy.context, conj, ('P1', 2), 600.0)
        self.assertIsNot(F.forma_do_modulo(conj), primeira)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestFormas)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de formas')
