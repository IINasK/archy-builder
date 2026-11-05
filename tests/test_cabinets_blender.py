"""Run: blender --background --factory-startup --python-exit-code 1 --python tests/test_cabinets_blender.py

Native cabinets and their backs, as requested: a 5 mm panel in a groove, recessed 15 mm from the rear edge, following cabinet dimensions while excluded from adjacency and cabinet thickness. This generator populates the library (biblioteca.ARMARIOS_NATIVOS).

Safety: generate into a temporary directory; verify the real library's SHA-1 hashes afterward, as in the library suite."""
import hashlib
import math
import os
import shutil
import sys
import tempfile
import unittest

import bpy
from mathutils import Euler, Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon

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
    def test_mirror_nativo_do_grupo_preserva_malhas_e_recalculo_dos_internos(self):
        # Regression v350: normalization treated a reflection as a negative dimension.
        for tipo in ('portas', 'gavetas'):
            with self.subTest(tipo=tipo):
                conj=M.criar_armario(bpy.context,'Espelho '+tipo,800,1800,550)
                if tipo=='portas':
                    g=addon.portas.porta_no_modulo(conj,folhas=2)
                    for f in addon.portas._folhas_portas(g):
                        addon.ferragens._definir_abertura(bpy.context,f,.4)
                    addon.prateleiras.criar_prateleiras(bpy.context,conj,(18,18,18,18,0),
                        dict(quantidade=2,espessura_mm=18,profundidade_mm=300))
                else:
                    addon.gavetas.criar_gavetas(bpy.context,conj,(18,18,18,18,0),dict(quantidade=3))
                conj.location=(1.2,-.8,.3);conj.rotation_euler.z=.61
                bpy.context.view_layer.update()
                addon.hud._selecionar_chapa_hud(bpy.context,conj)
                bpy.context.view_layer.objects.active=conj
                pivo=bpy.context.scene.tool_settings.transform_pivot_point
                bpy.context.scene.tool_settings.transform_pivot_point='ACTIVE_ELEMENT'
                pecas=[o for o in conj.children_recursive if o.type=='MESH']
                antes={o.name:[o.matrix_world@v.co for v in o.data.vertices] for o in pecas}
                malhas={o.name:o.data.as_pointer() for o in pecas}
                try:
                    for eixo in (0,1,1,0):
                        sinais=[1,1,1,1];sinais[eixo]=-1
                        espelho=conj.matrix_world@Matrix.Diagonal(sinais)@conj.matrix_world.inverted()
                        esperados={o.name:[espelho@(o.matrix_world@v.co) for v in o.data.vertices] for o in pecas}
                        self.assertEqual(bpy.ops.transform.mirror(orient_type='LOCAL',
                            constraint_axis=tuple(i==eixo for i in range(3))),{'FINISHED'})
                        bpy.context.view_layer.update()
                        M.absorver_conjuntos(no_timer=True);addon.chapas.normalizar_chapas()
                        M.atualizar_sistemas_do_conjunto(conj);bpy.context.view_layer.update()
                        for o in pecas:
                            self.assertEqual(o.data.as_pointer(),malhas[o.name])
                            self.assertLess(max((o.matrix_world@v.co-p).length
                                for v,p in zip(o.data.vertices,esperados[o.name])),1e-5,o.name)
                    for o in pecas:
                        self.assertLess(max((o.matrix_world@v.co-p).length
                            for v,p in zip(o.data.vertices,antes[o.name])),1e-5,o.name)
                finally:
                    bpy.context.scene.tool_settings.transform_pivot_point=pivo

    def test_redimensionar_e_recentrar_modulo_espelhado_girado(self):
        conj=M.criar_armario(bpy.context,'Espelho resize',800,1800,550)
        addon.portas.porta_no_modulo(conj,folhas=2)
        addon.prateleiras.criar_prateleiras(bpy.context,conj,(18,18,18,18,0),
            dict(quantidade=2,espessura_mm=18,profundidade_mm=300))
        conj.scale.x=-1;conj.rotation_euler.z=.61;bpy.context.view_layer.update()
        for largura in (900,800,1000):
            M.redimensionar_orientado(conj,(largura,1800,550))
            bpy.context.view_layer.update();addon.chapas.normalizar_chapas()
            caixa=addon.portas._caixa_do_modulo(conj)
            for real,esperado in zip(caixa[:3],(largura,1800,550)):
                self.assertAlmostEqual(real,esperado,places=2)
            self.assertLess(conj.matrix_world.determinant(),0)
        conj.scale.x*=1.2;bpy.context.view_layer.update()
        M.absorver_conjuntos(no_timer=True);addon.chapas.normalizar_chapas()
        bpy.context.view_layer.update()
        for real,esperado in zip(addon.portas._caixa_do_modulo(conj)[:3],(1200,1800,550)):
            self.assertAlmostEqual(real,esperado,places=2)
        self.assertTrue(all(abs(abs(s)-1)<1e-6 for s in conj.scale))

    def test_arremate_vertical_promob_chega_as_quinas_sem_alongar_divisoria(self):
        c=M.criar_armario(bpy.context,'Arremate',800,1056,350,fundo=False)
        r=addon.chapas.nova_chapa('Ripa',1050,50,15,(-60,-200,528),(0,90,0),bpy.context)
        r.parent=c
        d=addon.chapas.nova_chapa("Partition",1020,300,15,(0,0,528),(0,90,0),bpy.context)
        d.parent=c
        bpy.context.view_layer.update()
        e=r.chapa_espessura_mm
        self.assertEqual(addon.promob.alinhar_arremates(c),[r.name])
        self.assertAlmostEqual(r.chapa_largura_mm,1056,places=2)
        self.assertEqual(r.chapa_espessura_mm,e)
        self.assertAlmostEqual(d.chapa_largura_mm,1020,places=2)
        self.assertEqual(addon.promob.alinhar_arremates(c),[])

    def test_fundos_por_formato_preservam_planos_ao_redimensionar_e_remover(self):
        conj=M.criar_armario(bpy.context,'Fundo parcial',800,700,600)
        fundo=M.fundo_do_modulo(conj)
        addon.chapas._ocupado[0]=True
        try:fundo.chapa_largura_mm=650
        finally:addon.chapas._ocupado[0]=False
        addon.chapas.gerar_malha_chapa(fundo)
        bpy.context.view_layer.update()
        M.guardar_formato_fundo(conj,fundo);M.ajustar_fundo(conj)
        conj.conj_largura_mm=900
        self.assertAlmostEqual(fundo.chapa_largura_mm,750,places=2)
        conj.rotation_euler.z=.7;bpy.context.view_layer.update()
        M.ajustar_fundo(conj)
        self.assertAlmostEqual(fundo.chapa_largura_mm,750,places=2)
        anterior=self.caixa_local(conj,fundo)
        M.adicionar_fundo(conj,recuo=25,espessura=6)
        agora=self.caixa_local(conj,fundo)
        self.assertAlmostEqual(anterior[1].y-agora[1].y,10,places=2)
        self.assertAlmostEqual(fundo.chapa_espessura_mm,6,places=3)
        self.assertTrue(M.remover_fundo(conj))
        self.assertFalse(M.fundos_do_modulo(conj))

    def test_contorno_da_foto_ignora_diagonais_de_triangulacao(self):
        import bmesh
        conj=M.criar_armario(bpy.context,'Contorno',600,720,550)
        obj=M.fundo_do_modulo(conj)
        bm=bmesh.new();bm.from_mesh(obj.data)
        bmesh.ops.triangulate(bm,faces=list(bm.faces));bm.to_mesh(obj.data);bm.free()
        self.assertEqual(len(addon.biblioteca._arestas_da_foto(obj)),12)

    def test_foto_com_linhas_restaura_cor_render_e_nao_deixa_objetos(self):
        conj=M.criar_armario(bpy.context,'Foto limpa',600,720,550)
        objetos=[conj,*conj.children_recursive]
        for o in objetos:o.color=(.2,.4,.6,1)
        cores={o.name:tuple(o.color) for o in objetos}
        antes={o.name for o in bpy.data.objects};curvas=len(bpy.data.curves)
        cena=bpy.context.scene
        engine=cena.render.engine;sombra=cena.display.shading.color_type
        destino=os.path.join(_PASTA_GUARDA,'contorno.png')
        ok,msg=addon.biblioteca.fotografar_com_camera(destino,objetos,lado=128)
        self.assertTrue(ok,msg)
        self.assertEqual(antes,{o.name for o in bpy.data.objects})
        self.assertEqual(curvas,len(bpy.data.curves))
        self.assertEqual(cena.render.engine,engine)
        self.assertEqual(cena.display.shading.color_type,sombra)
        self.assertEqual(cores,{o.name:tuple(o.color) for o in objetos})
        imagem=bpy.data.images.load(destino)
        try:
            pixels=list(imagem.pixels)
            self.assertGreater(sum(1 for i in range(0,len(pixels),4) if pixels[i+3]>.5 and max(pixels[i:i+3])<.3),20)
            self.assertEqual(pixels[3],0)
        finally:bpy.data.images.remove(imagem)
    def test_promob_recuo_preserva_fundo_girado_espessura_material_e_uid(self):
        conj=M.criar_armario(bpy.context,"Inset",600,720,550)
        fundo=M.fundo_do_modulo(conj)
        addon.chapas._ocupado[0]=True
        try:fundo.chapa_espessura_mm=6
        finally:addon.chapas._ocupado[0]=False
        conj[M.CHAVE_RECUO_FUNDO]=0
        M.ajustar_fundo(conj)
        conj.rotation_euler.z=.7;conj.location=(1,2,3)
        bpy.context.view_layer.update()
        material=bpy.data.materials.new('Madeira fundo');fundo.data.materials.append(material)
        uid=fundo.get('chapa_uid');malha=[v.co.copy() for v in fundo.data.vertices]
        antes=self.caixa_local(conj,fundo)
        self.assertEqual(len(addon.promob.ajustar_recuo_fundos(conj)),1)
        depois=self.caixa_local(conj,fundo)
        self.assertAlmostEqual(antes[1].y-depois[1].y,15,places=2)
        self.assertAlmostEqual(fundo.chapa_espessura_mm,6,places=3)
        self.assertEqual(uid,fundo.get('chapa_uid'))
        self.assertEqual(fundo.material_slots[0].material,material)
        self.assertTrue(all((v.co-a).length<1e-6 for v,a in zip(fundo.data.vertices,malha)))
        self.assertFalse(addon.promob.ajustar_recuo_fundos(conj))
        conj[M.CHAVE_RECUO_FUNDO]=18;M.ajustar_fundo(conj)
        self.assertFalse(addon.promob.fundos_a_recuar(conj))

    def test_promob_fundo_parcial_recuado_nao_vira_fundo_da_torre(self):
        conj=M.criar_armario(bpy.context,'Compartimento',600,2200,550)
        fundo=M.fundo_do_modulo(conj)
        conj[M.CHAVE_RECUO_FUNDO]=0;M.ajustar_fundo(conj)
        del fundo[addon.chapas.MARCA_FUNDO]
        addon.chapas._ocupado[0]=True
        try:fundo.chapa_comprimento_mm=230
        finally:addon.chapas._ocupado[0]=False
        addon.chapas.gerar_malha_chapa(fundo)
        self.assertEqual(len(addon.promob.ajustar_recuo_fundos(conj)),1)
        self.assertNotIn(addon.chapas.MARCA_FUNDO,fundo)
        self.assertAlmostEqual(fundo.chapa_comprimento_mm,230,places=2)
        self.assertFalse(addon.promob.fundos_a_recuar(conj))
        fundo.location.y-=.1;bpy.context.view_layer.update()
        self.assertFalse(addon.promob.fundos_a_recuar(conj))

    def test_promob_fundo_recuado_reencaixa_prateleiras_e_trilhos(self):
        conj=M.criar_armario(bpy.context,'Internos',600,1000,550)
        conj[M.CHAVE_RECUO_FUNDO]=0;M.ajustar_fundo(conj)
        pr=addon.prateleiras.criar_prateleiras(bpy.context,conj,(18,18,18,18,18),
              dict(quantidade=1,profundidade_mm=525))
        gav=addon.gavetas.criar_gavetas(bpy.context,conj,(18,18,18,500,18),
              dict(quantidade=2,profundidade_mm=550,recuo_mm=13))
        pecas=addon.prateleiras.prateleiras_do_grupo(pr);uids=[o.get('chapa_uid') for o in pecas]
        antes=[self.caixa_local(conj,o) for o in pecas]
        frentes=[self.caixa_local(conj,addon.gavetas.frente_da_gaveta(g)) for g in addon.gavetas.gavetas_do_grupo(gav)]
        addon.promob.ajustar_recuo_fundos(conj)
        grupos=addon.promob.ajustar_internos_ao_fundo(conj)
        self.assertEqual(set(grupos),{pr.name,gav.name})
        limite=self.caixa_local(conj,M.fundo_do_modulo(conj))[0].y
        self.assertEqual(uids,[o.get('chapa_uid') for o in pecas])
        for o,a in zip(pecas,antes):
            lo,hi=self.caixa_local(conj,o)
            self.assertLessEqual(hi.y,limite+.01)
            self.assertAlmostEqual(lo.y,a[0].y,places=2)
            self.assertAlmostEqual(lo.z,a[0].z,places=2)
        for g,a in zip(addon.gavetas.gavetas_do_grupo(gav),frentes):
            b=self.caixa_local(conj,addon.gavetas.frente_da_gaveta(g))
            self.assertLess((b[0]-a[0]).length,.01)
            self.assertLess((b[1]-a[1]).length,.01)
        for o in gav.children_recursive:
            if o.type=='MESH' and addon.gavetas.MARCA_PECA in o:
                self.assertLessEqual(self.caixa_local(conj,o)[1].y,limite+.01)
        self.assertFalse(addon.promob.ajustar_internos_ao_fundo(conj))

    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for colecao in list(bpy.data.collections):
            bpy.data.collections.remove(colecao)
        camada = bpy.context.view_layer
        camada.active_layer_collection = camada.layer_collection

    def caixa_local(self, conj, obj):
        """Return (lo, hi) in mm for obj along the cabinet axes."""
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
        # Width and height: inner opening plus groove engagement.
        self.assertAlmostEqual(hi.x - lo.x, L - 2 * E + 2 * entra, places=2)
        self.assertAlmostEqual(hi.z - lo.z, A - 2 * E + 2 * entra, places=2)
        self.assertAlmostEqual(hi.y - lo.y, 5.0, places=2)
        # Place the back's rear face recuo from the cabinet's rear edge (+Y).
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
        # Cabinet E comes from the carcass, never the back ("Fundo" sorts before "Lateral").
        self.assertAlmostEqual(conj.conj_espessura_mm, 18.0, places=3)
        fundo = self.conferir_fundo(conj, 600, 720, 550)
        # Cut size = inner opening + 2 x 7 mm groove engagement.
        self.assertEqual(M.medidas_do_fundo(600, 720, 18), (578.0, 698.0, 15.0))
        # The back neither welds to other parts nor receives their welds.
        for chapa in M._chapas_do_conjunto(conj):
            for chave in [k for k in chapa.keys() if k.startswith('adj_')
                          and not k.endswith(('_folga', '_ancoras'))]:
                self.assertNotEqual(chapa[chave], fundo.name, chave)
        self.assertFalse([k for k in fundo.keys() if k.startswith('adj_')
                          and fundo[k]])

    def test_fundo_acompanha_as_medidas_e_fica_com_os_15_mm(self):
        conj = M.criar_armario(bpy.context, "Tall Cabinet", 600, 2200, 550)
        conj.conj_largura_mm = 900.0
        conj.conj_profundidade_mm = 330.0          # The recess does not scale.
        conj.conj_altura_mm = 700.0
        self.conferir_fundo(conj, 900, 700, 330)
        # Cabinet E: the carcass thickens; the back stays 5 mm and is rebuilt.
        conj.conj_espessura_mm = 15.0
        self.assertAlmostEqual(conj.conj_espessura_mm, 15.0, places=3)
        self.conferir_fundo(conj, 900, 700, 330, E=15.0)

    def test_fundo_segue_o_modulo_girado(self):
        conj = M.criar_armario(bpy.context, "Wall Cabinet", 800, 700, 330)
        conj.rotation_euler = Euler((0, 0, math.radians(90)))
        conj.location = (1.0, 2.0, 1.5)
        bpy.context.view_layer.update()
        M.ajustar_fundo(conj)
        self.conferir_fundo(conj, 800, 700, 330)

    def test_operador_do_fundo_muda_o_recuo_e_remove(self):
        conj = M.criar_armario(bpy.context, "Vanity Cabinet", 600, 600, 450, fundo=False)
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
        # User request: base and vanity cabinets have no top, only front and rear
        # stretchers that follow the carcass without welding to other parts.
        self.assertEqual(addon.biblioteca.TOPO_POR_TIPO,
                         {"Base Cabinet": 'TRAVESSAS', "Vanity Cabinet": 'TRAVESSAS'})
        conj = M.criar_armario(bpy.context, "Base Cabinet", 800, 720, 550, topo='TRAVESSAS')
        nomes = {c.name for c in M._chapas_do_conjunto(conj)}
        self.assertNotIn("Top", nomes)
        self.assertEqual({t[M.CHAVE_LADO_TRAVESSA] for t in M.travessas_do_modulo(conj)},
                         {'FRENTE', 'TRAS'})
        self.assertAlmostEqual(conj.conj_altura_mm, 720.0, places=2)
        self.assertAlmostEqual(conj.conj_espessura_mm, 18.0, places=3)

        def conferir(L, P, E):
            lo_c, hi_c = M._caixa_local_estrutural(conj)
            for tr in M.travessas_do_modulo(conj):
                lo, hi = self.caixa_local(conj, tr)
                self.assertAlmostEqual(hi.x - lo.x, L - 2 * E, places=2)     # Between the side panels.
                self.assertAlmostEqual(hi.y - lo.y, M.LARGURA_TRAVESSA_MM, places=2)
                self.assertAlmostEqual(hi.z, hi_c.z, places=2)               # At the top.
                self.assertAlmostEqual(hi.z - lo.z, E, places=2)
                if tr[M.CHAVE_LADO_TRAVESSA] == 'FRENTE':
                    self.assertAlmostEqual(lo.y, lo_c.y, places=2)           # Flush with the front.
                else:
                    self.assertAlmostEqual(hi.y, hi_c.y, places=2)           # Flush with the back.
                for chave in [k for k in tr.keys() if k.startswith('adj_')]:
                    self.assertFalse(tr[chave] and not chave.endswith('_folga'), chave)
            self.conferir_fundo(conj, L, 720, P, E)
        conferir(800, 550, 18)
        conj.conj_profundidade_mm = 330.0                # The 70 mm dimension does not scale.
        conj.conj_largura_mm = 1000.0
        conferir(1000, 330, 18)
        conj.conj_espessura_mm = 15.0
        conferir(1000, 330, 15)
        for chapa in M._chapas_do_conjunto(conj):         # No other parts weld to them.
            for chave in [k for k in chapa.keys() if k.startswith('adj_')
                          and not k.endswith(('_folga', '_ancoras', '_face'))]:
                self.assertNotIn(chapa[chave], ("Front Rail", "Rear Rail"))

    def test_parede_encosta_pelas_laterais_nao_pelo_fundo(self):
        # The 15 mm gap behind the back accommodates an uneven wall.
        conj = M.criar_armario(bpy.context, "Base Cabinet", 600, 720, 550)
        costas = addon.paredes.ponto_das_costas(conj)
        caixa = M._caixa_local_estrutural(conj)
        self.assertAlmostEqual((conj.matrix_world.inverted() @ costas).y * 1000.0,
                               caixa[1].y, places=2)

    def test_gerador_grava_preset_foto_e_indice(self):
        pasta = addon.biblioteca.pasta_biblioteca()
        tipo, L, A, P, niveis, portas = addon.biblioteca.ARMARIOS_NATIVOS[0]
        self.assertEqual(niveis, ("Cabinets", "Kitchen", "Base Cabinets"))
        self.assertEqual(portas, ('GIRO', 1))           # 300 mm: one leaf.
        arq = addon.biblioteca.gerar_armario_nativo(
            bpy.context, tipo, L, A, P, niveis, portas)
        nome = addon.biblioteca.nome_armario_nativo(tipo, L, A, P, portas)
        self.assertEqual(nome, "Base Cabinet 1 Door 300x720x550")
        self.assertEqual(os.path.dirname(arq), pasta)
        self.assertTrue(os.path.isfile(arq))
        png = os.path.splitext(arq)[0] + ".png"
        self.assertTrue(os.path.isfile(png), "no photo")
        imagem = bpy.data.images.load(png)
        try:
            self.assertEqual(tuple(imagem.size), (512, 512))
            alfa = list(imagem.pixels)[3::4]      # Blender 4.2 does not support stepped slicing here.
            self.assertEqual(alfa[0], 0.0)             # Transparent background.
            self.assertGreater(sum(1 for a in alfa if a > 0.5), 512 * 512 * 0.1)
        finally:
            bpy.data.images.remove(imagem)
        item = next(i for i in addon.biblioteca._ler_indice(pasta)
                    if i['arquivo'] == os.path.basename(arq))
        self.assertEqual((item['nome'], item['tipo'], item['n1'], item['n2'], item['n3']),
                         (nome, 'modulo', *niveis))
        # The scene remains clean: the preset exists only in the file.
        self.assertEqual(len(bpy.data.objects), 0)
        # The preset contains the back, door and clean carcass names without ".001";
        # only repeated hardware receives numeric suffixes.
        with bpy.data.libraries.load(arq) as (de, _para):
            nomes, colecoes = list(de.objects), list(de.collections)
        for peca in ('Base', "Back Panel", "Right Side", "Left Side",
                     "Front Rail", "Rear Rail", nome, 'Leaf 01',
                     'Handle Profile'):
            self.assertIn(peca, nomes)
        self.assertNotIn("Top", nomes)                 # Base cabinet: open top.
        self.assertEqual(colecoes, [nome])
        # Insertion restores the door linked to its cabinet.
        bpy.ops.object.cabinet_inserir_preset(pasta=pasta, arquivo=os.path.basename(arq),
                                              tipo='modulo')
        conj = next(o for o in bpy.data.objects if addon.chapas.MARCA_CONJUNTO in o)
        (grupo,) = addon.portas._portas_do_conjunto(conj)
        self.assertEqual(len(addon.portas._folhas_portas(grupo)), 1)
        self.assertIsNotNone(M.fundo_do_modulo(conj))
        # User-reported regression v205: the hinge controller arc was visible because
        # viewport visibility belongs to the layer and was not stored in the preset.
        # The slider opens the door while the rig remains hidden.
        F = addon.ferragens
        auxiliares = [o for o in bpy.data.objects
                      if o.get('cabinet_peca') in F.PECAS_OCULTAS_RIG]
        self.assertTrue(auxiliares)
        self.assertFalse([o.name for o in auxiliares if o.visible_get()])
        # The slider still rotates the hinge with the rig hidden.
        folha = addon.portas._folhas_portas(grupo)[0]
        copo = next(o for o in F._ferragens_portas(grupo)
                    if o.get(F.CHAVE_FERRAGEM) == 'CANECO')
        antes = copo.matrix_world.translation.copy()
        F._definir_abertura(bpy.context, folha, 1.0)
        bpy.context.view_layer.update()
        self.assertGreater((copo.matrix_world.translation - antes).length, 0.01)
        # The timer hides anything that reappears after append or a new layer.
        auxiliares[0].hide_set(False)
        self.assertEqual(F.ocultar_pecas_do_rig(), 1)
        self.assertFalse(auxiliares[0].visible_get())

    def test_lista_dos_nativos_tem_giro_e_basculante(self):
        nativos = addon.biblioteca.ARMARIOS_NATIVOS
        self.assertEqual(len(nativos), 39)
        nomes = [addon.biblioteca.nome_armario_nativo(t, L, A, P, pt)
                 for t, L, A, P, _n, pt in nativos]
        self.assertEqual(len(set(nomes)), len(nomes))       # One file each.
        self.assertIn("Base Cabinet 2 Doors 800x720x550", nomes)
        self.assertIn("Wall Cabinet Lift-up 600x700x330", nomes)
        self.assertIn("Wardrobe 1 Door 500x2400x550", nomes)
        for t, L, _A, _P, _n, (abertura, folhas) in nativos:
            if abertura == 'GIRO':
                self.assertEqual(folhas, 1 if L <= 500 else 2, (t, L))
            else:
                self.assertEqual((t, folhas), ("Wall Cabinet", 1))

    def test_porta_cobre_a_frente_do_modulo(self):
        conj = M.criar_armario(bpy.context, "Wall Cabinet", 900, 700, 330)
        grupo = addon.portas.porta_no_modulo(conj, 1, 'BASCULANTE')
        p = grupo['porta_parametros']
        self.assertEqual((p['abertura'], p['dobradica_lado'], p['folhas']),
                         ('BASCULANTE', 'CIMA', 1))
        # Full overlay: the leaf loses only the clearance on each side.
        (folha,) = addon.portas._folhas_portas(grupo)
        r = addon.portas.RESPIRO_PORTA_MM
        self.assertAlmostEqual(folha.chapa_largura_mm, 900 - 2 * r, places=2)
        self.assertAlmostEqual(folha.chapa_comprimento_mm, 700 - 2 * r, places=2)
        grupo = addon.portas.porta_no_modulo(
            M.criar_armario(bpy.context, "Base Cabinet", 800, 720, 550), 2)
        self.assertEqual(len(addon.portas._folhas_portas(grupo)), 2)

    def test_perfil_na_borda_de_cada_tipo(self):
        # User request: default handle type is PERFIL; top edge for base cabinets,
        # bottom for wall cabinets, vertical on the opening side for wardrobes.
        X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
        self.assertEqual(bpy.context.scene.cabinet_puxador_modelo, 'PERFIL')
        self.assertEqual(addon.biblioteca.PERFIL_POR_TIPO["Base Cabinet"], 'CIMA')
        self.assertEqual(addon.biblioteca.PERFIL_POR_TIPO["Wall Cabinet"], 'BAIXO')
        self.assertEqual(addon.biblioteca.PERFIL_POR_TIPO["Wardrobe"], 'LADO')

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
                # On the front face (-Y of the cabinet).
                self.assertGreater(rot.col[2].normalized().dot(-Y) * pux['puxador_face'], 0.9)
            return saida
        for d in direcoes(M.criar_armario(bpy.context, "B", 800, 720, 550), 2, 'GIRO', 'CIMA'):
            self.assertGreater(d.dot(Z), 0.99)
        for d in direcoes(M.criar_armario(bpy.context, "A", 800, 700, 330), 1, 'BASCULANTE', 'BAIXO'):
            self.assertGreater(d.dot(-Z), 0.99)
        esq, dir_ = direcoes(M.criar_armario(bpy.context, "R", 900, 2400, 550), 2, 'GIRO', 'LADO')
        self.assertGreater(esq.dot(X), 0.99)     # Left leaf: profile at the center.
        self.assertGreater(dir_.dot(-X), 0.99)

    def test_perfil_sempre_horizontal_salvo_guarda_roupa(self):
        # User request v308: tall units previously used vertical handles. Now only
        # wardrobes do; tall units use the horizontal edge nearest 1 m.
        Z = Vector((0, 0, 1))
        self.assertEqual(addon.biblioteca.PERFIL_POR_TIPO["Tall Cabinet"], 'ALTURA')
        regra = addon.importacao.posicao_do_perfil
        self.assertEqual([regra(a) for a in ("Base Cabinets", "Medium Wall Cabinets", "Wall Cabinets",
                                             "Tall Cabinets", "Cabinets", "Doors")],
                         ['CIMA', 'BAIXO', 'BAIXO', 'ALTURA', 'LADO', 'CIMA'])

        def sentido(grupo, posicao):
            pux, = addon.puxadores.perfis_na_porta(bpy.context, grupo, posicao)
            self.assertEqual(pux['puxador_borda'][0], 'Y')       # Horizontal.
            rot = pux.parent.matrix_world.to_3x3()
            return (rot.col[1] * (1 if pux['puxador_borda'][1] == '+' else -1)).normalized().dot(Z)
        conj = M.criar_armario(bpy.context, "T", 600, 600, 550)
        baixa = addon.portas.porta_no_modulo(conj, 1, 'GIRO')
        self.assertGreater(sentido(baixa, 'ALTURA'), .99)          # 0..600: at the top.
        alta = addon.portas.porta_no_modulo(conj, 1, 'GIRO')
        alta.matrix_world = Matrix.Translation((0, 0, 1.5)) @ alta.matrix_world
        bpy.context.view_layer.update()
        self.assertLess(sentido(alta, 'ALTURA'), -.99)             # 1500..2100: at the bottom.
        # Standalone door: its top is defined by its height, not its front (vertical fascia).
        solta = addon.portas.porta_no_modulo(M.criar_armario(bpy.context, "S", 600, 700, 550), 1, 'GIRO')
        solta.parent = None
        solta.pop(addon.portas.CHAVE_MODULO_PORTA, None)
        bpy.context.view_layer.update()
        self.assertGreater(sentido(solta, 'CIMA'), .99)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestArmarios)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
mudou = impressao_digital(PASTA_REAL) != DIGITAL_REAL
shutil.rmtree(_PASTA_GUARDA, ignore_errors=True)
if mudou:
    raise RuntimeError("THE REAL LIBRARY CHANGED during testing")
if not resultado.wasSuccessful():
    raise RuntimeError("Cabinet tests failed")
