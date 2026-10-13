"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_armarios_blender.py

Armarios NATIVOS e o FUNDO do modulo (pedido do usuario): chapa de 5 mm
em canal, recuada 15 mm da borda de tras, que acompanha as medidas do
modulo e fica fora da adjacencia e da espessura dele. E o gerador que
popula a biblioteca (`biblioteca.ARMARIOS_NATIVOS`).

SEGURANCA: o gerador grava numa pasta TEMPORARIA; a biblioteca real e'
conferida por sha1 no fim, como na suite da biblioteca.
"""
import hashlib
import math
import os
import shutil
import sys
import tempfile
import unittest

import bpy
from mathutils import Euler, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

PASTA_REAL = os.path.normpath(addon.opcoes._pasta_addon())
_PASTA_GUARDA = tempfile.mkdtemp(prefix="cabinet_armarios_")
addon.biblioteca.pasta_biblioteca = lambda: _PASTA_GUARDA
addon.opcoes._pasta_addon = lambda: _PASTA_GUARDA
M = addon.modulos


def impressao_digital(pasta):
    saida = {}
    for raiz, dirs, arqs in os.walk(pasta):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for a in arqs:
            with open(os.path.join(raiz, a), "rb") as f:
                saida[os.path.relpath(os.path.join(raiz, a), pasta)] = \
                    hashlib.sha1(f.read()).hexdigest()
    return saida


DIGITAL_REAL = impressao_digital(PASTA_REAL)


class TestArmarios(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for colecao in list(bpy.data.collections):
            bpy.data.collections.remove(colecao)
        camada = bpy.context.view_layer
        camada.active_layer_collection = camada.layer_collection

    def caixa_local(self, conj, obj):
        """(lo, hi) em mm de `obj` nos eixos do modulo."""
        inversa = conj.matrix_world.inverted()
        pts = [inversa @ (obj.matrix_world @ v.co) * 1000.0
               for v in obj.data.vertices]
        return (Vector([min(p[i] for p in pts) for i in range(3)]),
                Vector([max(p[i] for p in pts) for i in range(3)]))

    def conferir_fundo(self, conj, L, A, P, E=18.0, recuo=15.0):
        fundo = M.fundo_do_modulo(conj)
        self.assertIsNotNone(fundo)
        self.assertAlmostEqual(fundo.chapa_espessura_mm, 5.0, places=3)
        lo, hi = self.caixa_local(conj, fundo)
        entra = M.CANAL_FUNDO_MM - M.FOLGA_CANAL_FUNDO_MM
        # largura e altura: o vao interno mais o que entra no canal
        self.assertAlmostEqual(hi.x - lo.x, L - 2 * E + 2 * entra, places=2)
        self.assertAlmostEqual(hi.z - lo.z, A - 2 * E + 2 * entra, places=2)
        self.assertAlmostEqual(hi.y - lo.y, 5.0, places=2)
        # costas do fundo a `recuo` da borda de tras (+Y do modulo)
        caixa = M._caixa_local_estrutural(conj)
        self.assertAlmostEqual(caixa[1].y - hi.y, recuo, places=2)
        self.assertAlmostEqual((lo.x + hi.x) / 2, (caixa[0].x + caixa[1].x) / 2, places=2)
        return fundo

    def test_armario_nativo_nasce_com_fundo_em_canal(self):
        conj = M.criar_armario(bpy.context, "Balcao 600x720x550", 600, 720, 550)
        self.assertEqual(conj.name, "Balcao 600x720x550")
        self.assertEqual(len(M._chapas_do_conjunto(conj)), 5)
        self.assertAlmostEqual(conj.conj_largura_mm, 600.0, places=2)
        self.assertAlmostEqual(conj.conj_altura_mm, 720.0, places=2)
        self.assertAlmostEqual(conj.conj_profundidade_mm, 550.0, places=2)
        # o E do modulo e' o da caixa, nunca o do fundo ("Fundo" < "Lateral")
        self.assertAlmostEqual(conj.conj_espessura_mm, 18.0, places=3)
        fundo = self.conferir_fundo(conj, 600, 720, 550)
        # corte = vao interno + 2 x 7 mm de canal
        self.assertEqual(M.medidas_do_fundo(600, 720, 18), (578.0, 698.0, 15.0))
        # o fundo nao solda em ninguem nem e' soldado
        for chapa in M._chapas_do_conjunto(conj):
            for chave in [k for k in chapa.keys() if k.startswith('adj_')
                          and not k.endswith(('_folga', '_ancoras'))]:
                self.assertNotEqual(chapa[chave], fundo.name, chave)
        self.assertFalse([k for k in fundo.keys() if k.startswith('adj_')
                          and fundo[k]])

    def test_fundo_acompanha_as_medidas_e_fica_com_os_15_mm(self):
        conj = M.criar_armario(bpy.context, "Torre", 600, 2200, 550)
        conj.conj_largura_mm = 900.0
        conj.conj_profundidade_mm = 330.0          # recuo NAO escala
        conj.conj_altura_mm = 700.0
        self.conferir_fundo(conj, 900, 700, 330)
        # E do modulo: a caixa engrossa, o fundo fica com 5 mm e se refaz
        conj.conj_espessura_mm = 15.0
        self.assertAlmostEqual(conj.conj_espessura_mm, 15.0, places=3)
        self.conferir_fundo(conj, 900, 700, 330, E=15.0)

    def test_fundo_segue_o_modulo_girado(self):
        conj = M.criar_armario(bpy.context, "Aereo", 800, 700, 330)
        conj.rotation_euler = Euler((0, 0, math.radians(90)))
        conj.location = (1.0, 2.0, 1.5)
        bpy.context.view_layer.update()
        M.ajustar_fundo(conj)
        self.conferir_fundo(conj, 800, 700, 330)

    def test_operador_do_fundo_muda_o_recuo_e_remove(self):
        conj = M.criar_armario(bpy.context, "Gabinete", 600, 600, 450, fundo=False)
        self.assertIsNone(M.fundo_do_modulo(conj))
        r = bpy.ops.object.cabinet_fundo_modulo(recuo_mm=20.0, espessura_mm=5.0)
        self.assertEqual(r, {'FINISHED'})
        self.conferir_fundo(conj, 600, 600, 450, recuo=20.0)
        self.assertEqual(conj[M.CHAVE_RECUO_FUNDO], 20.0)
        r = bpy.ops.object.cabinet_fundo_modulo(remover=True)
        self.assertEqual(r, {'FINISHED'})
        self.assertIsNone(M.fundo_do_modulo(conj))
        self.assertNotIn(M.CHAVE_RECUO_FUNDO, conj)

    def test_modulo_de_bancada_tem_topo_aberto_com_travessas(self):
        # pedido do usuario: balcao e gabinete sem tampo, duas travessas
        # (frente e tras) que seguem a caixa e nao soldam em ninguem
        self.assertEqual(addon.biblioteca.TOPO_POR_TIPO,
                         {'Balcao': 'TRAVESSAS', 'Gabinete': 'TRAVESSAS'})
        conj = M.criar_armario(bpy.context, "Balcao", 800, 720, 550, topo='TRAVESSAS')
        nomes = {c.name for c in M._chapas_do_conjunto(conj)}
        self.assertNotIn('Tampo', nomes)
        self.assertEqual({t[M.CHAVE_LADO_TRAVESSA] for t in M.travessas_do_modulo(conj)},
                         {'FRENTE', 'TRAS'})
        self.assertAlmostEqual(conj.conj_altura_mm, 720.0, places=2)
        self.assertAlmostEqual(conj.conj_espessura_mm, 18.0, places=3)

        def conferir(L, P, E):
            lo_c, hi_c = M._caixa_local_estrutural(conj)
            for tr in M.travessas_do_modulo(conj):
                lo, hi = self.caixa_local(conj, tr)
                self.assertAlmostEqual(hi.x - lo.x, L - 2 * E, places=2)     # entre as laterais
                self.assertAlmostEqual(hi.y - lo.y, M.LARGURA_TRAVESSA_MM, places=2)
                self.assertAlmostEqual(hi.z, hi_c.z, places=2)               # no topo
                self.assertAlmostEqual(hi.z - lo.z, E, places=2)
                if tr[M.CHAVE_LADO_TRAVESSA] == 'FRENTE':
                    self.assertAlmostEqual(lo.y, lo_c.y, places=2)           # rente a' frente
                else:
                    self.assertAlmostEqual(hi.y, hi_c.y, places=2)           # rente ao fundo
                for chave in [k for k in tr.keys() if k.startswith('adj_')]:
                    self.assertFalse(tr[chave] and not chave.endswith('_folga'), chave)
            self.conferir_fundo(conj, L, 720, P, E)
        conferir(800, 550, 18)
        conj.conj_profundidade_mm = 330.0                # 70 mm nao escalam
        conj.conj_largura_mm = 1000.0
        conferir(1000, 330, 18)
        conj.conj_espessura_mm = 15.0
        conferir(1000, 330, 15)
        for chapa in M._chapas_do_conjunto(conj):         # ninguem solda nelas
            for chave in [k for k in chapa.keys() if k.startswith('adj_')
                          and not k.endswith(('_folga', '_ancoras', '_face'))]:
                self.assertNotIn(chapa[chave], ('Travessa Frontal', 'Travessa Traseira'))

    def test_parede_encosta_pelas_laterais_nao_pelo_fundo(self):
        # o vao de 15 mm atras do fundo e' o que absorve a parede torta
        conj = M.criar_armario(bpy.context, "Balcao", 600, 720, 550)
        costas = addon.paredes.ponto_das_costas(conj)
        caixa = M._caixa_local_estrutural(conj)
        self.assertAlmostEqual((conj.matrix_world.inverted() @ costas).y * 1000.0,
                               caixa[1].y, places=2)

    def test_gerador_grava_preset_foto_e_indice(self):
        pasta = addon.biblioteca.pasta_biblioteca()
        tipo, L, A, P, niveis, portas = addon.biblioteca.ARMARIOS_NATIVOS[0]
        self.assertEqual(niveis, ("Armarios", "Cozinha", "Inferiores"))
        self.assertEqual(portas, ('GIRO', 1))           # 300 mm: uma folha
        arq = addon.biblioteca.gerar_armario_nativo(
            bpy.context, tipo, L, A, P, niveis, portas)
        nome = addon.biblioteca.nome_armario_nativo(tipo, L, A, P, portas)
        self.assertEqual(nome, "Balcao 1 Porta 300x720x550")
        self.assertEqual(os.path.dirname(arq), pasta)
        self.assertTrue(os.path.isfile(arq))
        png = os.path.splitext(arq)[0] + ".png"
        self.assertTrue(os.path.isfile(png), 'sem foto')
        imagem = bpy.data.images.load(png)
        try:
            self.assertEqual(tuple(imagem.size), (512, 512))
            alfa = list(imagem.pixels)[3::4]      # o 4.2 nao fatia com passo
            self.assertEqual(alfa[0], 0.0)             # fundo transparente
            self.assertGreater(sum(1 for a in alfa if a > 0.5), 512 * 512 * 0.1)
        finally:
            bpy.data.images.remove(imagem)
        item = next(i for i in addon.biblioteca._ler_indice(pasta)
                    if i['arquivo'] == os.path.basename(arq))
        self.assertEqual((item['nome'], item['tipo'], item['n1'], item['n2'], item['n3']),
                         (nome, 'modulo', *niveis))
        # a cena fica limpa: o preset mora so' no arquivo
        self.assertEqual(len(bpy.data.objects), 0)
        # o preset tem o fundo, a porta e os nomes da caixa LIMPOS (sem
        # ".001"; as ferragens repetidas e' que se numeram)
        with bpy.data.libraries.load(arq) as (de, _para):
            nomes, colecoes = list(de.objects), list(de.collections)
        for peca in ('Base', 'Fundo', 'Lateral Direita', 'Lateral Esquerda',
                     'Travessa Frontal', 'Travessa Traseira', nome, 'Folha 01',
                     'Puxador Perfil'):
            self.assertIn(peca, nomes)
        self.assertNotIn('Tampo', nomes)                 # balcao: topo aberto
        self.assertEqual(colecoes, [nome])
        # inserido, volta com a porta vinculada ao modulo
        bpy.ops.object.cabinet_inserir_preset(pasta=pasta, arquivo=os.path.basename(arq),
                                              tipo='modulo')
        conj = next(o for o in bpy.data.objects if addon.chapas.MARCA_CONJUNTO in o)
        (grupo,) = addon.portas._portas_do_conjunto(conj)
        self.assertEqual(len(addon.portas._folhas_portas(grupo)), 1)
        self.assertIsNotNone(M.fundo_do_modulo(conj))
        # Regressao (relato do usuario, v205): o arco do controlador da
        # dobradica aparecia -- o "olho" e' da camada, nao vinha no preset.
        # A porta e' aberta pelo slider; o rig so' trabalha escondido.
        F = addon.ferragens
        auxiliares = [o for o in bpy.data.objects
                      if o.get('cabinet_peca') in F.PECAS_OCULTAS_RIG]
        self.assertTrue(auxiliares)
        self.assertFalse([o.name for o in auxiliares if o.visible_get()])
        # o slider continua girando a dobradica com o rig escondido
        folha = addon.portas._folhas_portas(grupo)[0]
        copo = next(o for o in F._ferragens_portas(grupo)
                    if o.get(F.CHAVE_FERRAGEM) == 'CANECO')
        antes = copo.matrix_world.translation.copy()
        F._definir_abertura(bpy.context, folha, 1.0)
        bpy.context.view_layer.update()
        self.assertGreater((copo.matrix_world.translation - antes).length, 0.01)
        # o timer reesconde o que reaparecer (anexado, camada nova...)
        auxiliares[0].hide_set(False)
        self.assertEqual(F.ocultar_pecas_do_rig(), 1)
        self.assertFalse(auxiliares[0].visible_get())

    def test_lista_dos_nativos_tem_giro_e_basculante(self):
        nativos = addon.biblioteca.ARMARIOS_NATIVOS
        self.assertEqual(len(nativos), 39)
        nomes = [addon.biblioteca.nome_armario_nativo(t, L, A, P, pt)
                 for t, L, A, P, _n, pt in nativos]
        self.assertEqual(len(set(nomes)), len(nomes))       # um arquivo cada
        self.assertIn("Balcao 2 Portas 800x720x550", nomes)
        self.assertIn("Aereo Basculante 600x700x330", nomes)
        self.assertIn("Roupeiro 1 Porta 500x2400x550", nomes)
        for t, L, _A, _P, _n, (abertura, folhas) in nativos:
            if abertura == 'GIRO':
                self.assertEqual(folhas, 1 if L <= 500 else 2, (t, L))
            else:
                self.assertEqual((t, folhas), ("Aereo", 1))

    def test_porta_cobre_a_frente_do_modulo(self):
        conj = M.criar_armario(bpy.context, "Aereo", 900, 700, 330)
        grupo = addon.portas.porta_no_modulo(conj, 1, 'BASCULANTE')
        p = grupo['porta_parametros']
        self.assertEqual((p['abertura'], p['dobradica_lado'], p['folhas']),
                         ('BASCULANTE', 'CIMA', 1))
        # Reta cobrindo tudo: a folha so' perde o respiro de cada lado
        (folha,) = addon.portas._folhas_portas(grupo)
        r = addon.portas.RESPIRO_PORTA_MM
        self.assertAlmostEqual(folha.chapa_largura_mm, 900 - 2 * r, places=2)
        self.assertAlmostEqual(folha.chapa_comprimento_mm, 700 - 2 * r, places=2)
        grupo = addon.portas.porta_no_modulo(
            M.criar_armario(bpy.context, "Balcao", 800, 720, 550), 2)
        self.assertEqual(len(addon.portas._folhas_portas(grupo)), 2)

    def test_perfil_na_borda_de_cada_tipo(self):
        # pedido do usuario: puxador padrao = PERFIL; balcao em cima,
        # aereo embaixo, roupeiro na vertical do lado da abertura
        X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
        self.assertEqual(bpy.context.scene.cabinet_puxador_modelo, 'PERFIL')
        self.assertEqual(addon.biblioteca.PERFIL_POR_TIPO['Balcao'], 'CIMA')
        self.assertEqual(addon.biblioteca.PERFIL_POR_TIPO['Aereo'], 'BAIXO')
        self.assertEqual(addon.biblioteca.PERFIL_POR_TIPO['Roupeiro'], 'LADO')

        def direcoes(conj, folhas, abertura, posicao):
            grupo = addon.portas.porta_no_modulo(conj, folhas, abertura)
            perfis = addon.puxadores.perfis_na_porta(bpy.context, grupo, posicao)
            bpy.context.view_layer.update()
            saida = []
            for pux in perfis:
                folha = pux.parent
                self.assertEqual(pux['puxador_tipo'], 'PERFIL')
                rot = folha.matrix_world.to_3x3()
                eixo = {'X': rot.col[0], 'Y': rot.col[1]}[pux['puxador_borda'][0]]
                sinal = 1 if pux['puxador_borda'][1] == '+' else -1
                saida.append((eixo * sinal).normalized())
                # na face da FRENTE (-Y do modulo)
                self.assertGreater(rot.col[2].normalized().dot(-Y) * pux['puxador_face'], 0.9)
            return saida
        for d in direcoes(M.criar_armario(bpy.context, "B", 800, 720, 550), 2, 'GIRO', 'CIMA'):
            self.assertGreater(d.dot(Z), 0.99)
        for d in direcoes(M.criar_armario(bpy.context, "A", 800, 700, 330), 1, 'BASCULANTE', 'BAIXO'):
            self.assertGreater(d.dot(-Z), 0.99)
        esq, dir_ = direcoes(M.criar_armario(bpy.context, "R", 900, 2400, 550), 2, 'GIRO', 'LADO')
        self.assertGreater(esq.dot(X), 0.99)     # folha da esquerda: perfil no meio
        self.assertGreater(dir_.dot(-X), 0.99)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestArmarios)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
mudou = impressao_digital(PASTA_REAL) != DIGITAL_REAL
shutil.rmtree(_PASTA_GUARDA, ignore_errors=True)
if mudou:
    raise RuntimeError('A BIBLIOTECA REAL MUDOU durante os testes')
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de armarios')
