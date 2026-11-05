"""Run: blender --background --factory-startup --python-exit-code 1 --python tests/test_handles_blender.py"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon


def caixa_na_chapa(obj, chapa):
    """Return object (lo, hi) in mm in the panel's local reference frame."""
    bpy.context.view_layer.update()
    inversa = chapa.matrix_world.inverted()
    pontos = [inversa @ (obj.matrix_world @ Vector(c)) * 1000.0
              for c in obj.bound_box]
    return ([round(min(p[i] for p in pontos), 3) for i in range(3)],
            [round(max(p[i] for p in pontos), 3) for i in range(3)])


def malha_na_chapa(chapa):
    """Return panel-mesh (lo, hi) in mm, including the profile cut."""
    vs = [v.co * 1000.0 for v in chapa.data.vertices]
    return ([round(min(v[i] for v in vs), 3) for i in range(3)],
            [round(max(v[i] for v in vs), 3) for i in range(3)])


class TestPuxadores(unittest.TestCase):
    def porta_de_correr(self):
        _, grupo = self.nicho_com_porta()
        p = addon.portas._copiar_parametros(grupo['porta_parametros'])
        p['abertura'] = 'CORRER'
        addon.portas._reaplicar_portas(bpy.context, grupo, p)
        return grupo, addon.portas._folhas_portas(grupo)

    def procurar(self, folha=None, acerto=None):
        area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        regiao = next(r for r in area.regions if r.type == 'WINDOW')
        estado = dict(alvo=folha.name if folha else '', tipo='ALCA', n=0, chapa=None)
        op = SimpleNamespace(_estado=estado, _area=area, _regiao=regiao,
            _rv3d=area.spaces.active.region_3d, _preparar_arame=lambda: None)
        op._projetados = lambda: {k:(Vector((0,0)),Vector((100,0))) for k in estado.get('segmentos',{})}
        if folha is not None:
            origem = folha.matrix_world @ Vector((0,0,1))
            direcao = -(folha.matrix_world.to_3x3().col[2].normalized())
        else:
            origem, direcao = Vector((0,0,1)), Vector((0,0,-1))
        with patch.object(addon.puxadores.view3d_utils,'region_2d_to_origin_3d',return_value=origem), \
             patch.object(addon.puxadores.view3d_utils,'region_2d_to_vector_3d',return_value=direcao), \
             patch.object(addon.hud,'_raio_cru',return_value=acerto) as raio:
            addon.puxadores.OBJECT_OT_posicionar_puxador._procurar_linha(op,bpy.context,Vector((10,0)))
        return estado, raio.call_count

    def test_trocar_giro_por_correr_adapta_lados_e_conserva_donos(self):
        _,grupo=self.nicho_com_porta()
        puxadores=addon.puxadores.perfis_na_porta(bpy.context,grupo,'LADO')
        nomes=[p.name for p in puxadores]
        donos=[p.parent.name for p in puxadores]
        self.assertEqual([p['puxador_borda'] for p in puxadores],['X+','X-'])
        p=addon.portas._copiar_parametros(grupo['porta_parametros'])
        for abertura,esperado in [('CORRER',['X-','X+']),('GIRO',['X+','X-'])]:
            p['abertura']=abertura
            addon.portas._reaplicar_portas(bpy.context,grupo,p)
            self.assertEqual([bpy.data.objects[n]['puxador_borda'] for n in nomes],esperado)
            self.assertEqual([bpy.data.objects[n].parent.name for n in nomes],donos)
            self.assertEqual(len([o for o in grupo.children_recursive if addon.chapas.MARCA_PUXADOR in o]),2)

    def test_perfis_novos_da_porta_de_correr_ficam_nas_bordas_externas(self):
        grupo,folhas=self.porta_de_correr()
        perfis=addon.puxadores.perfis_na_porta(bpy.context,grupo,'LADO')
        self.assertEqual([p.parent for p in perfis],folhas)
        self.assertEqual([p['puxador_borda'] for p in perfis],['X-','X+'])

    def test_lado_do_perfil_independe_da_abertura_atual_da_folha(self):
        _,grupo=self.nicho_com_porta()
        folhas=addon.portas._folhas_portas(grupo)
        p=addon.portas._copiar_parametros(grupo['porta_parametros'])
        for i,f in enumerate(folhas):
            f[addon.ferragens.CHAVE_ABERTURA]=1.0
        addon.portas._reaplicar_portas(bpy.context,grupo,p)
        perfis=addon.puxadores.perfis_na_porta(bpy.context,grupo,'LADO')
        self.assertEqual([p['puxador_borda'] for p in perfis],['X+','X-'])

    def test_folha_alvo_usa_raio_nativo_mesmo_com_outra_na_frente(self):
        _,folhas=self.porta_de_correr()
        alvo=folhas[0]
        # Overlapping the other leaf makes the scene's first hit ambiguous.
        folhas[1].matrix_world=alvo.matrix_world.copy()
        folhas[1].location.z += .03
        bpy.context.view_layer.update()
        estado,chamadas=self.procurar(alvo)
        self.assertEqual(estado['chapa'],alvo.name)
        self.assertTrue(estado['segmentos'])
        self.assertEqual(chamadas,0)

    def test_folha_alvo_oculta_ou_bloqueada_nao_recebe_puxador(self):
        _,folhas=self.porta_de_correr()
        alvo=folhas[0]
        for oculto,bloqueado in ((True,False),(False,True)):
            alvo.hide_set(oculto);alvo.hide_select=bloqueado
            estado,chamadas=self.procurar(alvo)
            self.assertIsNone(estado['chapa'])
            self.assertEqual(chamadas,0)

    def test_sem_folha_isolada_reutiliza_acerto_visivel_da_hud(self):
        _,folhas=self.porta_de_correr()
        alvo=folhas[1]
        acerto=(alvo,alvo.matrix_world.translation,alvo.matrix_world.to_3x3().col[2],0,alvo.matrix_world)
        estado,chamadas=self.procurar(acerto=acerto)
        self.assertEqual(estado['chapa'],alvo.name)
        self.assertEqual(chamadas,1)

    def test_apagar_e_recriar_so_puxador_da_segunda_folha(self):
        _,folhas=self.porta_de_correr()
        primeiro=addon.puxadores.criar_puxador(bpy.context,folhas[0],'ALCA','X-',1)
        nome=primeiro.name
        segundo=addon.puxadores.criar_puxador(bpy.context,folhas[1],'ALCA','X+',1)
        bpy.data.objects.remove(segundo,do_unlink=True)
        estado,_=self.procurar(folhas[1])
        alvo=bpy.data.objects[estado['chapa']]
        novo=addon.puxadores.criar_puxador(bpy.context,alvo,estado['tipo'],estado['borda'],estado['face'],estado['fracao'])
        self.assertEqual(novo.parent,folhas[1])
        self.assertEqual(bpy.data.objects[nome].parent,folhas[0])
        self.assertEqual([sum(addon.chapas.MARCA_PUXADOR in o for o in f.children) for f in folhas],[1,1])

    def test_tab_individual_preserva_modelagem_material_uv_e_undo_do_puxador(self):
        chapa = self.chapa()
        pux = addon.puxadores.criar_puxador(bpy.context, chapa, 'ALCA', 'Y+', 1)
        nome = pux.name
        uv = pux.data.uv_layers.new(name='UV do puxador editado')
        for i, dado in enumerate(uv.data):
            dado.uv = (i / 50, i / 70)
        uvs = [tuple(d.uv) for d in uv.data]
        material = pux.data.materials[0].name
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        pux.select_set(True)
        bpy.context.view_layer.objects.active = pux
        bpy.ops.ed.undo_push(message='Puxador antes do Tab')
        bpy.ops.object.mode_set(mode='EDIT')
        addon.chapas.absorver_edicoes_de_malha()
        bm = bmesh.from_edit_mesh(pux.data)
        bm.verts.ensure_lookup_table()
        bm.verts[0].co.z += .004
        bmesh.update_edit_mesh(pux.data)
        bpy.ops.ed.undo_push(message='Modelou o puxador')
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.ed.undo_push(message='Saiu do puxador')
        pontos = [tuple(v.co) for v in pux.data.vertices]
        addon.chapas.absorver_edicoes_de_malha()
        self.assertEqual([tuple(v.co) for v in pux.data.vertices], pontos)
        chapa = pux = uv = dado = obj = bm = None
        for _ in range(2):
            bpy.ops.ed.undo()
            self.assertEqual(bpy.context.mode, 'EDIT_MESH')
            addon.eventos._fim_do_desfazer()
            addon.eventos.verificar_periodicamente()
            bpy.ops.ed.redo()
            addon.eventos._fim_do_desfazer()
            addon.eventos.verificar_periodicamente()
            malha = bpy.data.objects[nome].data
            self.assertEqual([tuple(v.co) for v in malha.vertices], pontos)
            self.assertEqual([tuple(d.uv) for d in malha.uv_layers[0].data], uvs)
            self.assertEqual(malha.materials[0].name, material)
            self.assertIn('puxador_contorno', bpy.data.objects[nome])
            malha = None

    def test_perfil_da_folha_perpendicular_fica_na_frente_e_na_ponta_livre(self):
        from mathutils import Matrix
        import math
        conj,grupo=self.nicho_com_porta()
        grupo.matrix_world=Matrix.Rotation(math.pi/2,4,'Z') @ grupo.matrix_world
        bpy.context.view_layer.update()
        puxadores=addon.puxadores.perfis_na_porta(bpy.context,grupo,'LADO')
        for i,pux in enumerate(puxadores):
            self.assertEqual(pux['puxador_face'],1)
            self.assertEqual(pux['puxador_borda'],'X+' if i==0 else 'X-')

    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def chapa(self):
        bpy.ops.object.cabinet_criar()          # 600 x 400 x 18
        return bpy.context.object

    def nicho_com_porta(self):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar()
        conj = next(o for o in bpy.data.objects if addon.chapas.MARCA_CONJUNTO in o)
        bpy.context.view_layer.update()
        L, A = conj.conj_largura_mm, conj.conj_altura_mm
        P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
        a = conj.matrix_world @ (Vector((-L / 2 + E, -P / 2, E)) / 1000.0)
        b = conj.matrix_world @ (Vector((L / 2 - E, -P / 2, A - E)) / 1000.0)
        resultado = bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            referencia=tuple(v for linha in
                             conj.matrix_world.to_quaternion().to_matrix()
                             for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name,
            frente='NEG_Y', dobradica='RETA', folhas=2)
        self.assertEqual(resultado, {'FINISHED'})
        return conj, addon.portas._portas_do_conjunto(conj)[0]

    def test_modelos_geram_as_medidas_de_exemplo(self):
        # BORDA uses boxes only without the asset; 80 mm is the commercial default (v322).
        for tipo, esperado in (('ALCA', (148, 10, 30)), ('BORDA', (80, 20, 26)),
                               ('PERFIL', (500, 30, 18))):
            caixas = addon.puxadores._caixas_puxador(tipo, 18.0, 500.0 if tipo == 'PERFIL'
                                           else addon.puxadores.MODELOS_PUXADOR[tipo][1])
            medidas = tuple(round(max(c[2 * i + 1] for c in caixas)
                                  - min(c[2 * i] for c in caixas), 3)
                            for i in range(3))
            self.assertEqual(medidas, esperado, tipo)

    def test_posiciona_nas_quatro_bordas_e_nas_duas_faces(self):
        chapa = self.chapa()
        meias = {'X': 300.0, 'Y': 200.0}
        for borda in addon.puxadores.BORDAS_CHAPA:
            for face in (1, -1):
                pux = addon.puxadores.criar_puxador(bpy.context, chapa, 'ALCA', borda, face)
                lo, hi = caixa_na_chapa(pux, chapa)
                eixo = 0 if borda[0] == 'X' else 1
                sinal = 1 if borda[1] == '+' else -1
                centro = [(a + b) / 2 for a, b in zip(lo, hi)]
                # 40 mm inward from the line, centered along it.
                self.assertAlmostEqual(centro[eixo],
                                       sinal * (meias[borda[0]] - 40.0), places=3)
                self.assertAlmostEqual(centro[1 - eixo], 0.0, places=3)
                self.assertAlmostEqual(hi[1 - eixo] - lo[1 - eixo], 148.0, places=3)
                # Standing on the chosen face, extending 30 mm outward.
                if face > 0:
                    self.assertEqual((lo[2], hi[2]), (9.0, 39.0))
                else:
                    self.assertEqual((lo[2], hi[2]), (-39.0, -9.0))
                bpy.data.objects.remove(pux, do_unlink=True)

    def test_acompanha_a_chapa_redimensionada(self):
        chapa = self.chapa()
        alca = addon.puxadores.criar_puxador(bpy.context, chapa, 'ALCA', 'X+', 1, 0.5)
        borda = addon.puxadores.criar_puxador(bpy.context, chapa, 'BORDA', 'Y+', 1, 0.25)
        x_antes = (lambda c: (c[0][0] + c[1][0]) / 2)(caixa_na_chapa(borda, chapa))
        chapa.chapa_largura_mm = 800.0
        chapa.chapa_comprimento_mm = 700.0
        lo, hi = caixa_na_chapa(alca, chapa)
        self.assertAlmostEqual((lo[0] + hi[0]) / 2, 360.0, places=3)   # 40 mm from the edge.
        self.assertAlmostEqual((lo[1] + hi[1]) / 2, 0.0, places=3)     # At the midpoint.
        self.assertAlmostEqual(hi[1] - lo[1], 148.0, places=3)         # Same size.
        lo, hi = caixa_na_chapa(borda, chapa)
        # At the new edge: the slim handle's 1.1 mm top sits on it.
        self.assertAlmostEqual(hi[1], 350.0 + addon.puxadores._dados_borda()['tampo_mm'], places=2)
        # A quarter of the edge remains a quarter: x = 150 of 600 becomes 200 of 800.
        self.assertAlmostEqual(abs((lo[0] + hi[0]) / 2), 200.0, places=3)
        self.assertAlmostEqual(abs(x_antes), 150.0, places=3)
        # Near an endpoint, the pull never extends past the edge.
        alca['puxador_fracao'] = 0.0
        addon.puxadores.posicionar_puxador(alca)
        lo, hi = caixa_na_chapa(alca, chapa)
        self.assertGreaterEqual(lo[1], -350.0 - 1e-6)

    def furos_da_borda(self, pux, chapa):
        """Return hole spacing and diameter in mm from asset hole vertices; deformation preserves their indices."""
        modelo = addon.puxadores._malha_modelo_borda()
        dados = addon.puxadores._dados_borda()
        meio = dados['entre_furos_mm'] / 2000.0
        furo = [v.index for v in modelo.vertices
                if (Vector((abs(v.co.x), v.co.y)) - Vector((meio, .0062))).length < .0025]
        inversa = chapa.matrix_world.inverted()
        pontos = [inversa @ (pux.matrix_world @ pux.data.vertices[i].co) * 1000 for i in furo]
        direita = [p for p in pontos if p.x > 0]
        esquerda = [p for p in pontos if p.x < 0]
        centro = lambda ps: (min(p.x for p in ps) + max(p.x for p in ps)) / 2
        return (centro(direita) - centro(esquerda),
                max(p.x for p in direita) - min(p.x for p in direita))

    def test_borda_slim_em_tamanho_real_acompanha_a_porta(self):
        # User request: the slim flange handle becomes the BORDA default at real size:
        # 80 mm long, holes 64 mm apart, projecting 20 mm forward. Widen it sideways
        # and adapt to panel thickness without scaling holes, chamfers
        # or the rolled front.
        chapa = self.chapa()                                   # 600 x 400 x 18
        pux = addon.puxadores.criar_puxador(bpy.context, chapa, 'BORDA', 'Y+', 1, .5)
        # The model, followed by the flange's two standard screws.
        parafuso = addon.ferragens.malha_parafuso()
        self.assertEqual(len(pux.data.vertices),
                         len(addon.puxadores._malha_modelo_borda().vertices)
                         + 2 * len(parafuso.vertices))
        self.assertEqual([m.get('cabinet_origem') for m in pux.data.materials][1:], ['Aco Bicromatizado'])
        # Preview only the countersunk head's top; the thread is inside the wood.
        F = addon.ferragens
        addon.arame._arame_parafuso[0] = None
        addon.arame.preparar_modelos()
        cabeca = addon.arame._arame_parafuso[0]
        self.assertTrue(cabeca)
        for p in cabeca:
            self.assertAlmostEqual(p.z, F.SALIENCIA_PARAFUSO_MM / 1000.0, places=6)
        self.assertLess(len(cabeca), len(parafuso.edges) * 2)
        lo, hi = caixa_na_chapa(pux, chapa)
        self.assertAlmostEqual(hi[0] - lo[0], 80.0, places=2)
        self.assertAlmostEqual(hi[2], 9.0 + 20.0, places=2)          # 20 mm forward.
        # Rear flange at 0.94 mm; the screw head protrudes 0.876 mm from it,
        # following the user's refinement.
        saliencia = F.SALIENCIA_PARAFUSO_MM
        self.assertAlmostEqual(lo[2], -9.0 - 0.94 - saliencia, delta=.1)
        self.assertAlmostEqual(hi[1], 200.0 + 1.0956, places=2)      # Top sits on the edge.
        entre, furo = self.furos_da_borda(pux, chapa)
        self.assertAlmostEqual(entre, 64.0, places=2)
        # Screws, as requested: one per hole, 5.78 mm head on the flange's outer face,
        # with the shaft inside the door without reaching the front.
        inversa = chapa.matrix_world.inverted()
        n = len(addon.puxadores._malha_modelo_borda().vertices)
        pontos = [inversa @ (pux.matrix_world @ v.co) * 1000 for v in pux.data.vertices[n:]]
        for lado in (-1, 1):
            ps = [p for p in pontos if p.x * lado > 0]
            self.assertAlmostEqual((min(p.x for p in ps) + max(p.x for p in ps)) / 2, 32.0 * lado, places=2)
            self.assertAlmostEqual(max(p.x for p in ps) - min(p.x for p in ps),
                                   2 * F.RAIO_CABECA_PARAFUSO_MM, places=2)
            self.assertAlmostEqual(min(p.z for p in ps), -9.0 - 0.94 - saliencia, delta=.05)
            self.assertLess(max(p.z for p in ps), 9.0 - 3.0 + 1e-3)
        # Thicker door: only the flange moves back; front, top and holes stay unchanged.
        chapa.chapa_espessura_mm = 25.0
        lo, hi = caixa_na_chapa(pux, chapa)
        self.assertAlmostEqual(hi[2], 12.5 + 20.0, places=2)
        self.assertAlmostEqual(lo[2], -12.5 - 0.94 - saliencia, delta=.1)
        self.assertAlmostEqual(self.furos_da_borda(pux, chapa)[1], furo, places=3)
        # Longer handle: endpoints move with the holes (144 -> 128 commercial spacing).
        pux['puxador_comprimento_mm'] = 144.0
        addon.puxadores.posicionar_puxador(pux)
        lo, hi = caixa_na_chapa(pux, chapa)
        self.assertAlmostEqual(hi[0] - lo[0], 144.0, places=2)
        entre, largura = self.furos_da_borda(pux, chapa)
        self.assertAlmostEqual(entre, 128.0, places=2)
        self.assertAlmostEqual(largura, furo, places=3)
        # A thin 6 mm door still fits without scaling.
        chapa.chapa_espessura_mm = 6.0
        lo, hi = caixa_na_chapa(pux, chapa)
        self.assertAlmostEqual(lo[2], -3.0 - 0.94 - saliencia, delta=.1)
        self.assertAlmostEqual(self.furos_da_borda(pux, chapa)[1], furo, places=3)
        # Flat faces without gradients: rebuild the handle's Weighted Normal at each
        # dimension change; switching models removes it.
        self.assertIn(addon.puxadores.NOME_NORMAIS_BORDA, pux.modifiers)
        bpy.context.view_layer.update()
        avaliada = pux.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
        def lado_menor(p):
            vs = [avaliada.vertices[i].co for i in p.vertices]
            return min((a - b).length for a, b in zip(vs, vs[1:] + vs[:1]))
        # Truly flat faces: bands of 0.27 mm at corners and 1.3 mm before the roll
        # are intentional smooth transitions into the curve.
        planas = [p for p in avaliada.polygons if lado_menor(p) > .003
                  and max(abs(c) for c in p.normal) > .999]
        self.assertGreater(len(planas), 6)
        desvio = max(max(avaliada.corner_normals[li].vector.angle(p.normal)
                         for li in p.loop_indices) for p in planas)
        self.assertLess(desvio * 57.3, 1.0)
        addon.puxadores._trocar_modelo_puxador(pux, 'ALCA')
        self.assertNotIn(addon.puxadores.NOME_NORMAIS_BORDA, pux.modifiers)

    def test_previa_da_borda_e_o_arame_do_modelo(self):
        chapa = self.chapa()
        addon.puxadores._malha_modelo_borda()
        addon.arame.preparar_modelos('BORDA')
        pux = addon.puxadores.criar_puxador(bpy.context, chapa, 'BORDA', 'Y+', 1, .5)
        pontos = addon.arame.preparar_previa(chapa, 'BORDA', 'Y+', 1, .5)
        inversa = chapa.matrix_world.inverted()
        local = [inversa @ p * 1000 for p in pontos]
        lo, hi = caixa_na_chapa(pux, chapa)
        for i in range(3):
            self.assertAlmostEqual(min(p[i] for p in local), lo[i], places=1)
            self.assertAlmostEqual(max(p[i] for p in local), hi[i], places=1)

    def test_material_do_objeto_sobrevive_migracao_e_redimensionamento(self):
        chapa=self.chapa()
        pux=addon.puxadores.criar_puxador(bpy.context,chapa,'PERFIL','Y+',1)
        material=bpy.data.materials.new('Pintura desta instancia')
        pux.material_slots[0].link='OBJECT';pux.material_slots[0].material=material
        del pux['puxador_referencia_versao']
        addon.frentes.preparar(chapa,forcar=True)
        self.assertEqual(pux['puxador_referencia_versao'],1)
        self.assertEqual(pux.material_slots[0].link,'OBJECT')
        self.assertIs(pux.material_slots[0].material,material)
        chapa.chapa_largura_mm=800
        self.assertEqual(pux.material_slots[0].link,'OBJECT')
        self.assertIs(pux.material_slots[0].material,material)

    def test_previa_em_movimento_reutiliza_geometria_preparada(self):
        chapa=self.chapa()
        addon.arame.preparar_modelos('ALCA')
        with patch.object(addon.arame.bmesh,'new',side_effect=AssertionError('Recriou malha no hover')):
            for tipo in ('ALCA','BORDA'):
                for fracao in (.25,.5,.75):
                    self.assertTrue(addon.arame.preparar_previa(chapa,tipo,'Y+',1,fracao))

    # Regression, fixed in v302: frame/arc/channel mesh left gerar_malha_chapa
    # before profile placement, leaving the profile at the origin.
    def test_perfil_em_folha_quadro_acompanha_a_malha(self):
        chapa = self.chapa()
        chapa['chapa_quadro_mm'] = 40.0
        addon.chapas.gerar_malha_chapa(chapa)
        perfil = addon.puxadores.criar_puxador(bpy.context, chapa, 'PERFIL', 'Y-', 1)
        self.assertTrue(perfil.data.vertices)
        lo, hi = caixa_na_chapa(perfil, chapa)
        self.assertEqual((lo[0], hi[0], lo[1]), (-300.0, 300.0, -200.0))
        chapa.chapa_largura_mm = 800
        lo, hi = caixa_na_chapa(perfil, chapa)
        self.assertEqual((lo[0], hi[0]), (-400.0, 400.0))

    def test_perfil_corta_a_madeira_e_a_medida_continua_nominal(self):
        # The profile is the user's aluminum model (tools/hardware/extract_profile_handle.py):
        # span the entire edge from nominal edge to wood cut, with the back flush
        # to the leaf and the front slightly proud, matching the model.
        chapa = self.chapa()
        perfil = addon.puxadores.criar_puxador(bpy.context, chapa, 'PERFIL', 'Y-', 1)
        self.assertEqual(perfil.name, 'Handle Profile')
        dados = addon.puxadores._dados_perfil()
        corte = dados['altura_mm']
        self.assertAlmostEqual(corte, addon.puxadores._altura_perfil_mm())
        lo, hi = caixa_na_chapa(perfil, chapa)
        self.assertEqual((lo[0], hi[0], lo[1]), (-300.0, 300.0, -200.0))
        self.assertAlmostEqual(lo[2], -9.0, delta=0.2)       # Flush at the back.
        self.assertTrue(9.0 < hi[2] < 11.0, hi[2])            # Protruding at the front.
        self.assertTrue(-200.0 + corte < hi[1] < -200.0 + corte + 3.0, hi[1])
        self.assertEqual([m.name for m in perfil.data.materials],
                         ['Aluminio Escovado'])
        self.assertTrue(perfil.data.uv_layers)
        modelo = addon.puxadores._malha_modelo_perfil()
        self.assertEqual(len(perfil.data.vertices), len(modelo.vertices))
        # The model mesh is not duplicated for each profile.
        addon.puxadores.criar_puxador(bpy.context, chapa, 'PERFIL', 'Y+', 1)
        self.assertEqual(len([m for m in bpy.data.meshes
                              if m.get('cabinet_origem') == dados['malha']]), 1)
        self.assertEqual(len([m for m in bpy.data.materials
                              if m.get('cabinet_origem') == 'Aluminio Escovado']), 1)
        for f in [f for f in chapa.children
                  if f.get('puxador_borda') == 'Y+']:
            bpy.data.objects.remove(f, do_unlink=True)
        addon.puxadores._conferir_rebaixos()
        self.assertEqual(malha_na_chapa(chapa),
                         ([-300.0, round(-200.0 + corte, 3), -9.0],
                          [300.0, 200.0, 9.0]))
        self.assertEqual(chapa.chapa_comprimento_mm, 400.0)
        cantos = addon.hud._caixa_hud_objetos([chapa])
        alturas = [c.y * 1000 for c in cantos]
        self.assertAlmostEqual(max(alturas) - min(alturas), 400.0, places=3)
        # Still spans the entire edge after resizing.
        chapa.chapa_largura_mm = 900.0
        lo, hi = caixa_na_chapa(perfil, chapa)
        self.assertEqual((lo[0], hi[0]), (-450.0, 450.0))
        # Another profile on the same edge replaces it without doubling the cut.
        novo = addon.puxadores.criar_puxador(bpy.context, chapa, 'PERFIL', 'Y-', 1)
        self.assertEqual([f for f in chapa.children
                          if f.get('puxador_tipo') == 'PERFIL'], [novo])
        self.assertEqual(malha_na_chapa(chapa)[0][1], round(-200.0 + corte, 3))
        # Deleting with X restores the wood.
        bpy.data.objects.remove(novo, do_unlink=True)
        addon.puxadores._conferir_rebaixos()
        self.assertEqual(malha_na_chapa(chapa)[0][1], -200.0)
        self.assertNotIn('chapa_rebaixos', chapa)

    def test_porta_do_modulo_leva_os_puxadores(self):
        conj, grupo = self.nicho_com_porta()
        esquerda, direita = addon.portas._folhas_portas(grupo)
        alca = addon.puxadores.criar_puxador(bpy.context, esquerda, 'ALCA', 'X+', 1)
        perfil = addon.puxadores.criar_puxador(bpy.context, direita, 'PERFIL', 'Y+', 1)
        conj.conj_largura_mm += 400.0
        conj.conj_altura_mm += 300.0
        bpy.context.view_layer.update()
        esquerda, direita = addon.portas._folhas_portas(grupo)
        self.assertEqual(alca.parent, esquerda)
        lo, hi = caixa_na_chapa(alca, esquerda)
        self.assertAlmostEqual((lo[0] + hi[0]) / 2,
                               esquerda.chapa_largura_mm / 2 - 40.0, places=3)
        self.assertAlmostEqual((lo[1] + hi[1]) / 2, 0.0, places=3)
        lo, hi = caixa_na_chapa(perfil, direita)
        self.assertAlmostEqual(hi[0] - lo[0], direita.chapa_largura_mm, places=3)
        # Changing a double door to single transfers remaining hardware to the surviving leaf.
        erro = addon.portas._editar_parametro_porta(bpy.context, grupo, 'folhas', 1)
        self.assertFalse(erro)
        (unica,) = addon.portas._folhas_portas(grupo)
        self.assertEqual(alca.parent, unica)
        self.assertEqual(perfil.parent, unica)
        lo, hi = caixa_na_chapa(perfil, unica)
        self.assertAlmostEqual(hi[0] - lo[0], unica.chapa_largura_mm, places=3)
        self.assertEqual(unica.get('chapa_rebaixos'), 'Y+')

    def test_clique_simples_no_puxador_da_porta_seleciona_a_porta(self):
        # User request: only double-clicking enters handle editing;
        # a single click acts on its leaf and selects the entire door.
        conj, grupo = self.nicho_com_porta()
        esquerda = addon.portas._folhas_portas(grupo)[0]
        alca = addon.puxadores.criar_puxador(bpy.context, esquerda, 'ALCA', 'X+', 1)
        S = addon.selecao
        evento = SimpleNamespace(mouse_region_x=50, mouse_region_y=60)
        def clicar(duplo):
            op = SimpleNamespace(clique=False, modo='INDIVIDUAL' if duplo else 'GRUPO',
                                 toggle=False, extend=False, select_passthrough=False)
            ctx = SimpleNamespace(region=SimpleNamespace(as_pointer=lambda: 1),
                view_layer=bpy.context.view_layer, selected_objects=list(bpy.context.selected_objects),
                area=None)
            with patch.object(addon.hud, '_raio_hud', return_value=(alca, None)), \
                 patch.object(addon.hud, '_ferragem_sob_mouse', return_value=None), \
                 patch.object(addon.portas_viewport, '_slider_sob_mouse', return_value=None), \
                 patch.object(addon.gavetas, 'slider_sob_mouse', return_value=None):
                return S.OBJECT_OT_selecionar._invoke(op, ctx, evento)
        bpy.ops.object.select_all(action='DESELECT')
        self.assertEqual(clicar(False), {'FINISHED'})
        self.assertEqual(set(bpy.context.selected_objects),
                         {grupo, *addon.portas._folhas_portas(grupo)})
        self.assertFalse(alca.select_get())
        self.assertEqual(clicar(True), {'FINISHED'})
        self.assertEqual(set(bpy.context.selected_objects), {alca})
        self.assertEqual(bpy.context.view_layer.objects.active, alca)

    def test_linha_snaps_e_fracao(self):
        self.assertEqual(addon.puxadores._snaps(0), [])
        self.assertEqual(addon.puxadores._snaps(1), [0.5])
        self.assertEqual(addon.puxadores._snaps(2), [1 / 3, 2 / 3])
        a, b = Vector((0, 0)), Vector((300, 0))
        self.assertAlmostEqual(addon.puxadores._fracao_na_linha(a, b, Vector((60, 40))), 0.2)
        self.assertEqual(addon.puxadores._fracao_na_linha(a, b, Vector((-50, 0))), 0.0)
        self.assertEqual(addon.puxadores._fracao_na_linha(a, b, Vector((60, 0)), 1), 0.5)
        self.assertAlmostEqual(addon.puxadores._fracao_na_linha(a, b, Vector((60, 0)), 2), 1 / 3)
        self.assertEqual(addon.puxadores._texto_fracao(0.5, 3), '1/2')
        self.assertEqual(addon.puxadores._texto_fracao(2 / 3, 2), '2/3')
        self.assertEqual(addon.puxadores._texto_fracao(0.2, 0), '20%')
        segmentos = {'Y+': (Vector((0, 100)), Vector((300, 100))),
                     'X+': (Vector((300, 0)), Vector((300, 100)))}
        self.assertEqual(addon.puxadores._borda_mais_proxima(segmentos, Vector((150, 90))), 'Y+')
        self.assertEqual(addon.puxadores._borda_mais_proxima(segmentos, Vector((290, 40))), 'X+')
        self.assertIsNone(addon.puxadores._borda_mais_proxima({}, Vector()))

    def test_face_e_bordas_da_chapa(self):
        chapa = self.chapa()
        olhar_de_frente = Vector((0, 0, -1))
        self.assertEqual(addon.puxadores._face_da_chapa(chapa, Vector((0, 0, 1)), olhar_de_frente), 1)
        self.assertEqual(addon.puxadores._face_da_chapa(chapa, Vector((0, 0, -1)), olhar_de_frente), -1)
        # For a narrow face, use the large face pointing toward the viewer.
        self.assertEqual(addon.puxadores._face_da_chapa(chapa, Vector((1, 0, 0)), olhar_de_frente), 1)
        self.assertEqual(addon.puxadores._face_da_chapa(chapa, Vector((1, 0, 0)), Vector((0, 0, 1))), -1)
        bordas = addon.puxadores._bordas_da_face(chapa, 1)
        self.assertEqual(set(bordas), set(addon.puxadores.BORDAS_CHAPA))
        a, b = bordas['Y+']
        self.assertAlmostEqual((b - a).length, 0.6, places=6)
        self.assertAlmostEqual(a.y, 0.2, places=6)
        self.assertAlmostEqual(a.z, 0.009, places=6)

    def test_bloco_de_medidas_do_puxador_parametrico(self):
        chapa = self.chapa()
        alca = addon.puxadores.criar_puxador(bpy.context, chapa, 'ALCA', 'X+', 1)
        perfil = addon.puxadores.criar_puxador(bpy.context, chapa, 'PERFIL', 'Y+', 1)
        nomes = [c[0] for c in addon.puxadores._medidas_puxador_parametrico(alca)]
        self.assertEqual(nomes, ["Length", "Inset"])
        self.assertTrue(all(len(c) == 3 for c in       # No lock.
                            addon.puxadores._medidas_puxador_parametrico(alca)))
        self.assertEqual(addon.puxadores._medidas_puxador_parametrico(perfil)[0][2], '')
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        alca.select_set(True)
        bpy.context.view_layer.objects.active = alca
        for prop, valor, esperado in (('puxp_comprimento', 0.2, 200.0),
                                      ('puxp_recuo', 0.06, 60.0)):
            self.assertEqual(bpy.ops.object.cabinet_editar_medida_gaveta(
                dono='puxador', objeto=alca.name, propriedade=prop,
                valor=valor), {'FINISHED'})
        lo, hi = caixa_na_chapa(alca, chapa)
        self.assertAlmostEqual(hi[1] - lo[1], 200.0, places=3)
        self.assertAlmostEqual((lo[0] + hi[0]) / 2, 300.0 - 60.0, places=3)

    def test_aba_puxadores_modelo_e_posicionar(self):
        # User request: without selection, show only Create Handle. Show the model
        # during creation, updating the positioner immediately, or when an add-on handle
        # is selected, replacing that handle.
        cena = bpy.context.scene
        cena.cabinet_aba = 'PUXADORES'
        self.addCleanup(setattr, cena, 'cabinet_aba', 'MODULOS')
        bpy.ops.object.select_all(action='DESELECT')
        modelos = lambda ws: [v[5] for v in ws if v[5] and v[5][0] == 'escolha'
                              and v[5][1] == 'cabinet_puxador_modelo']
        self.assertEqual(modelos(addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)),
                         [])
        addon.puxadores._posicionador_puxador[0] = {'tipo': 'ALCA'}
        self.addCleanup(addon.puxadores._posicionador_puxador.__setitem__, 0, None)
        for largura in (190, 320, 564):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1400)
            escolhas = modelos(widgets)
            # Thumbnail carousel, as requested: factory models use their bundled photos
            # instead of names.
            self.assertEqual([e[2] for e in escolhas], list(addon.puxadores.MODELOS_PADRAO))
            self.assertEqual([e[6]['arquivo'] for e in escolhas],
                             ['puxador_%s.png' % t for t in addon.puxadores.MODELOS_PADRAO])
            self.assertEqual([e[2] for e in escolhas if e[3]], ['ALCA'])
            self.assertTrue(all(e[5] == addon.portas.ALVO_ASSISTENTE for e in escolhas))
            # At the top of the tab in orange, like Create Doors; highlighted during creation.
            criar = [v for v in widgets if v[5] and v[5][0] == 'criar_puxador']
            self.assertEqual([v[4] for v in criar],
                             ["Positioning the handle... (Esc cancels)"])
            self.assertGreater(criar[0][1], max(
                v[1] for v in widgets if v[5] and v[5][0] == 'escolha'))
            caixas = [v[:4] for v in widgets]
            for i, (ax, ay, aw, ah) in enumerate(caixas):
                for bx, by, bw, bh in caixas[i + 1:]:
                    self.assertFalse(ax < bx + bw - 0.01 and bx < ax + aw - 0.01
                                     and ay < by + bh - 0.01 and by < ay + ah - 0.01,
                                     "Width %d" % largura)
        self.assertIn(addon.puxadores.OBJECT_OT_posicionar_puxador, addon.CLASSES)

    def test_trocar_o_modelo_do_puxador_selecionado(self):
        chapa = self.chapa()
        pux = addon.puxadores.criar_puxador(bpy.context, chapa, 'ALCA', 'Y-', 1)
        bpy.ops.object.select_all(action='DESELECT')
        pux.select_set(True)
        bpy.context.view_layer.objects.active = pux
        bpy.context.scene.cabinet_aba = 'PUXADORES'
        self.addCleanup(setattr, bpy.context.scene, 'cabinet_aba', 'MODULOS')
        escolhas = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)
                    if v[5] and v[5][0] == 'escolha']
        self.assertEqual([e[2] for e in escolhas if e[3]], ['ALCA'])
        self.assertTrue(all(e[5] == addon.gaveta.ALVO_PUXADOR for e in escolhas))
        addon.puxadores._trocar_modelo_puxador(pux, 'BORDA')
        self.assertEqual((pux['puxador_tipo'], pux.name),
                         ('BORDA', 'Handle Edge'))
        self.assertEqual(malha_na_chapa(chapa)[0][1], -200.0)
        # A profile cuts the wood; switching back restores it.
        addon.puxadores._trocar_modelo_puxador(pux, 'PERFIL')
        corte = addon.puxadores._altura_perfil_mm()
        self.assertEqual(malha_na_chapa(chapa)[0][1], round(-200.0 + corte, 3))
        addon.puxadores._trocar_modelo_puxador(pux, 'ALCA')
        self.assertEqual(malha_na_chapa(chapa)[0][1], -200.0)
        self.assertNotIn('Aluminio Escovado',
                         [m.name for m in pux.data.materials if m])

    def test_perfil_se_ajusta_sem_deformar_os_chanfros(self):
        # User request: the profile follows door width and thickness without deforming
        # its chamfer or rounding. Model vertices only translate: move the whole endpoint
        # along the length and the whole back of the section, allowing the straight
        # middle section to accommodate the change.
        modelo = addon.puxadores._malha_modelo_perfil()
        dados = addon.puxadores._dados_perfil()
        corte, vao = addon.puxadores._corte_do_perfil(modelo)
        self.assertGreater(vao, 0.002)          # The straight part of the section.
        for largura, espessura in ((600.0, 18.0), (250.0, 25.0),
                                   (900.0, 15.0), (260.0, 18.0)):
            chapa = addon.chapas.nova_chapa("Panel", largura, 400.0, espessura,
                                     (0, 0, 0), (0, 0, 0), bpy.context)
            pux = addon.puxadores.criar_puxador(bpy.context, chapa, 'PERFIL', 'Y-', 1)
            self.assertEqual(len(pux.data.vertices), len(modelo.vertices))
            recua = -(espessura - dados['espessura_porta_mm']) / 1000.0
            estica = (largura - dados['comprimento_mm']) / 2000.0
            for v, m in zip(pux.data.vertices, modelo.vertices):
                d = v.co - m.co
                # For a door shorter than the model, the endpoint moves inward;
                # abs() here hid a 532 mm profile inside a 260 mm door.
                self.assertAlmostEqual(d.x, estica if m.co.x > 0 else -estica,
                                       places=6)
                self.assertAlmostEqual(d.y, 0.0, places=6)
                self.assertAlmostEqual(d.z, recua if m.co.z < corte else 0.0,
                                       places=6)
            xs = [v.co.x for v in pux.data.vertices]
            self.assertAlmostEqual(max(xs) - min(xs), largura / 1000.0, places=5)
            # The profile back remains flush with the door back.
            self.assertAlmostEqual(min(v.co.z for v in pux.data.vertices),
                                   min(v.co.z for v in modelo.vertices) + recua,
                                   places=6)
        # For a much thinner door, scale if no accommodating span fits.
        self.assertIsNone(addon.puxadores._ajuste_do_perfil(modelo, 10.0, 400.0)[2])

    def caixa_dos_pontos(self, pontos):
        return ([min(p[i] for p in pontos) for i in range(3)],
                [max(p[i] for p in pontos) for i in range(3)])

    def test_previa_do_puxador_e_o_arame_da_peca(self):
        # User request: handle preview uses its wireframe, formerly just the anchor point,
        # matching the part that will be created there.
        chapa = self.chapa()
        addon.puxadores._malha_modelo_perfil()
        for tipo, borda in (('ALCA', 'X+'), ('BORDA', 'Y-'), ('PERFIL', 'Y+')):
            previa = addon.arame._arame_puxador(chapa, tipo, borda, 1, 0.3)
            self.assertEqual(len(previa) % 2, 0)
            pux = addon.puxadores.criar_puxador(bpy.context, chapa, tipo, borda, 1, 0.3)
            bpy.context.view_layer.update()
            cantos = [pux.matrix_world @ Vector(c) for c in pux.bound_box]
            lo, hi = self.caixa_dos_pontos(previa)
            plo, phi = self.caixa_dos_pontos(cantos)
            for a, b in zip(lo + hi, plo + phi):
                self.assertAlmostEqual(a, b, places=4, msg=tipo)
            # Same points in the same order; the rotated screw is stored as float32
            # in the mesh, producing differences of about 1e-9 m.
            objeto = addon.arame._arame_do_objeto_puxador(pux)
            self.assertEqual(len(objeto), len(previa), tipo)
            for a, b in zip(objeto, previa):
                self.assertLess((a - b).length, 1e-7, tipo)

    def test_alt_leva_o_puxador_a_outra_borda_do_grupo(self):
        # User request: Alt-drag the anchor to another line only on its own group's
        # panels, namely the door leaves, oriented to that edge. A profile restores
        # the old wood and cuts the new location.
        _conj, grupo = self.nicho_com_porta()
        f0, f1 = addon.portas._folhas_portas(grupo)
        self.assertEqual(addon.puxadores._chapas_do_grupo_do_puxador(f0), [f0, f1])
        pux = addon.puxadores.criar_puxador(bpy.context, f0, 'ALCA', 'X+', 1, 0.5)
        bpy.ops.object.select_all(action='DESELECT')
        f0.select_set(True)
        self.assertEqual(addon.puxadores._puxadores_com_ancora(bpy.context), [pux])
        # The anchor is its point on the edge.
        a, b = addon.puxadores._bordas_da_face(f0, 1)['X+']
        self.assertLess((addon.puxadores._ancora_do_puxador(pux) - a.lerp(b, 0.5)).length,
                        1e-6)
        op = SimpleNamespace(puxador=pux.name)
        arrastar = addon.puxadores.OBJECT_OT_arrastar_puxador
        self.assertIn(arrastar, addon.CLASSES)
        arrastar._aplicar(op, bpy.context, f1.name, 'Y-', 1, 0.5)
        self.assertEqual((pux.parent, pux['puxador_borda']), (f1, 'Y-'))
        lo, hi = caixa_na_chapa(pux, f1)
        meia_y = f1.chapa_comprimento_mm / 2.0
        # Orient to the new edge: along X, resting against -Y.
        self.assertGreater(hi[0] - lo[0], hi[1] - lo[1])
        self.assertLess(abs(lo[1] + meia_y), 50.0)
        # Profile: restore wood on the old leaf and cut it on the new one.
        perfil = addon.puxadores.criar_puxador(bpy.context, f0, 'PERFIL', 'Y+', 1)
        inteira = f1.chapa_comprimento_mm / 2.0
        corte = addon.puxadores._altura_perfil_mm()
        self.assertEqual(malha_na_chapa(f0)[1][1], round(inteira - corte, 3))
        arrastar._aplicar(SimpleNamespace(puxador=perfil.name), bpy.context,
                          f1.name, 'Y+', 1, 0.5)
        self.assertEqual(malha_na_chapa(f0)[1][1], round(inteira, 3))
        self.assertEqual(malha_na_chapa(f1)[1][1], round(inteira - corte, 3))

    def test_arraste_recusa_destino_ocupado_sem_mover_ou_remover_os_puxadores(self):
        # Regression v389: two pulls ended up with the same matrix, at distance 0.
        p=addon.puxadores;c=self.chapa()
        movel=p.criar_puxador(bpy.context,c,'ALCA','Y+',1)
        outro=p.criar_puxador(bpy.context,c,'ALCA','X+',1)
        antes=movel.matrix_basis.copy();outro_antes=outro.matrix_basis.copy()
        self.assertFalse(p.OBJECT_OT_arrastar_puxador._aplicar(SimpleNamespace(puxador=movel.name),
            bpy.context,c.name,'X+',1,.5))
        self.assertEqual(movel['puxador_borda'],'Y+')
        self.assertEqual(movel.matrix_basis,antes)
        self.assertEqual(outro.matrix_basis,outro_antes)
        self.assertEqual(len([o for o in c.children if 'eh_puxador' in o]),2)

    def test_arraste_permite_duas_alcas_separadas_na_mesma_borda(self):
        p=addon.puxadores;c=self.chapa()
        primeiro=p.criar_puxador(bpy.context,c,'ALCA','X+',1,0)
        movel=p.criar_puxador(bpy.context,c,'ALCA','Y+',1)
        self.assertTrue(p.OBJECT_OT_arrastar_puxador._aplicar(SimpleNamespace(puxador=movel.name),
            bpy.context,c.name,'X+',1,1))
        self.assertEqual(movel['puxador_borda'],'X+')
        self.assertGreater((movel.matrix_basis.translation-primeiro.matrix_basis.translation).length,.148)

    def test_arraste_recusa_sobreposicao_proxima_e_fracoes_limitadas_na_mesma_ponta(self):
        p=addon.puxadores;c=self.chapa()
        outro=p.criar_puxador(bpy.context,c,'ALCA','X+',1,0)
        movel=p.criar_puxador(bpy.context,c,'ALCA','Y+',1)
        op=SimpleNamespace(puxador=movel.name)
        for fracao in (0,.1,.3):
            with self.subTest(fracao=fracao):
                self.assertFalse(p.OBJECT_OT_arrastar_puxador._aplicar(op,bpy.context,c.name,'X+',1,fracao))
                self.assertEqual(movel['puxador_borda'],'Y+')
        outro.hide_set(True)
        self.assertFalse(p.OBJECT_OT_arrastar_puxador._aplicar(op,bpy.context,c.name,'X+',1,.1))

    def test_arraste_permite_face_oposta_e_nao_confunde_outro_objeto(self):
        p=addon.puxadores;c=self.chapa()
        p.criar_puxador(bpy.context,c,'ALCA','X+',1)
        movel=p.criar_puxador(bpy.context,c,'ALCA','Y+',1)
        op=SimpleNamespace(puxador=movel.name)
        self.assertTrue(p.OBJECT_OT_arrastar_puxador._aplicar(op,bpy.context,c.name,'X+',-1,.5))
        outra=self.chapa()
        self.assertTrue(p.OBJECT_OT_arrastar_puxador._aplicar(op,bpy.context,outra.name,'X+',1,.5))
        self.assertIs(movel.parent,outra)

    def test_arraste_bloqueado_nao_reconstroi_madeira_ou_consulta_vertices(self):
        p=addon.puxadores;c=self.chapa()
        movel=p.criar_puxador(bpy.context,c,'ALCA','Y+',1)
        p.criar_puxador(bpy.context,c,'BORDA','X+',1)
        with patch.object(p,'posicionar_puxador',side_effect=AssertionError('Refaz puxador bloqueado')), \
             patch.object(p,'_atualizar_madeira',side_effect=AssertionError('Refaz chapa bloqueada')):
            self.assertFalse(p.OBJECT_OT_arrastar_puxador._aplicar(SimpleNamespace(puxador=movel.name),
                bpy.context,c.name,'X+',1,.5))

    def test_arraste_de_perfil_nao_apaga_perfil_que_ocupa_o_destino(self):
        p=addon.puxadores;c=self.chapa()
        movel=p.criar_puxador(bpy.context,c,'PERFIL','Y+',1)
        outro=p.criar_puxador(bpy.context,c,'PERFIL','X+',1)
        nomes=(movel.name,outro.name);madeira=malha_na_chapa(c)
        op=SimpleNamespace(puxador=movel.name,_encerrar=lambda:p._arraste_puxador.__setitem__(0,None))
        p._arraste_puxador[0]={'puxador':movel.name}
        self.addCleanup(p._arraste_puxador.__setitem__,0,None)
        p.OBJECT_OT_arrastar_puxador._aplicar(op,bpy.context,c.name,'X+',1,.5)
        self.assertEqual(p.OBJECT_OT_arrastar_puxador.modal(op,bpy.context,
            SimpleNamespace(type='LEFTMOUSE',value='RELEASE')),{'FINISHED'})
        self.assertTrue(all(bpy.data.objects.get(n) is not None for n in nomes))
        self.assertEqual(movel['puxador_borda'],'Y+')
        self.assertEqual(malha_na_chapa(c),madeira)

    def test_cancelar_arraste_restaura_inclusive_sobreposicao_legada(self):
        p=addon.puxadores;c=self.chapa()
        movel=p.criar_puxador(bpy.context,c,'ALCA','X+',1)
        p.criar_puxador(bpy.context,c,'ALCA','X+',1)
        antes=movel.matrix_basis.copy()
        op=SimpleNamespace(puxador=movel.name,_antes=(c.name,'X+',1,.5),_encerrar=lambda:None)
        op._aplicar=lambda *a,**kw:p.OBJECT_OT_arrastar_puxador._aplicar(op,*a,**kw)
        op._aplicar(bpy.context,c.name,'Y+',1,.5)
        p.OBJECT_OT_arrastar_puxador.cancel(op,bpy.context)
        self.assertEqual(movel.matrix_basis,antes)
        self.assertEqual(movel['puxador_borda'],'X+')

    def test_arraste_considera_ocupacao_na_chapa_girada_e_ignora_o_proprio_puxador(self):
        p=addon.puxadores;c=self.chapa()
        c.rotation_euler=(.4,.7,1.1);c.location=(2,3,4)
        bpy.context.view_layer.update()
        movel=p.criar_puxador(bpy.context,c,'ALCA','Y+',1)
        p.criar_puxador(bpy.context,c,'ALCA','X+',1)
        op=SimpleNamespace(puxador=movel.name)
        self.assertTrue(p.OBJECT_OT_arrastar_puxador._aplicar(op,bpy.context,c.name,'Y+',1,.5))
        self.assertFalse(p.OBJECT_OT_arrastar_puxador._aplicar(op,bpy.context,c.name,'X+',1,.5))


def barra(nome, tamanho_mm, matriz):
    """Create an external box mesh at world-space matriz."""
    import bmesh
    from mathutils import Matrix
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Diagonal(
        [t / 1000.0 for t in tamanho_mm] + [1.0]))
    malha = bpy.data.meshes.new(nome)
    bm.to_mesh(malha)
    bm.free()
    obj = bpy.data.objects.new(nome, malha)
    bpy.context.collection.objects.link(obj)
    obj.matrix_world = matriz
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.context.view_layer.update()
    return obj


def caixa_mundo(obj):
    bpy.context.view_layer.update()
    pontos = [obj.matrix_world @ v.co for v in obj.data.vertices]
    return ([min(p[i] for p in pontos) for i in range(3)],
            [max(p[i] for p in pontos) for i in range(3)])


class TestModeloDoUsuario(unittest.TestCase):
    """Use-as-handle, as requested: an external object becomes a library model in the handles category, which the creator then uses. Redirect the library to a temporary directory and use a dummy PNG: background mode has no viewport to photograph."""

    def setUp(self):
        import shutil
        import tempfile
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        self.pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.pasta, True)
        bib = addon.biblioteca
        for nome, troca in (('pasta_biblioteca', lambda: self.pasta),
                            ('capturar_viewport', self.foto)):
            self.addCleanup(setattr, bib, nome, getattr(bib, nome))
            setattr(bib, nome, troca)
        self.fotos = []
        cena = bpy.context.scene
        self.addCleanup(addon.puxadores.escolher_modelo, cena, 'ALCA')

    def foto(self, destino, camera=None, isolar=None, rotacao=None):
        self.fotos.append((isolar, rotacao))
        img = bpy.data.images.new('foto_teste', 4, 4, alpha=True)
        img.filepath_raw = destino
        img.file_format = 'PNG'
        img.save()
        bpy.data.images.remove(img)
        return True, destino

    def chapa(self):
        bpy.ops.object.cabinet_criar()          # 600 x 400 x 18
        return bpy.context.object

    def test_encostado_na_porta_vira_o_puxador_dela_no_mesmo_lugar(self):
        from mathutils import Matrix
        chapa = self.chapa()
        # 148 x 10 x 20 bar lying on face +Z, 40 mm from edge Y+ and
        # 50 mm to the right of center.
        local = Matrix.Translation((0.05, 0.16, 0.009 + 0.010))
        obj = barra('Barra Inox', (148, 10, 20), chapa.matrix_world @ local)
        antes = caixa_mundo(obj)
        self.assertEqual(bpy.ops.object.cabinet_usar_como_puxador(), {'FINISHED'})
        self.assertNotIn('Barra Inox', bpy.data.objects)
        (pux,) = [o for o in chapa.children if addon.chapas.MARCA_PUXADOR in o]
        self.assertEqual(pux['puxador_tipo'], 'MODELO')
        self.assertEqual((pux['puxador_borda'], pux['puxador_face']), ('Y+', 1))
        self.assertAlmostEqual(pux['puxador_recuo_mm'], 40.0, places=2)
        self.assertAlmostEqual(pux['puxador_comprimento_mm'], 148.0, places=2)
        for a, b in zip(caixa_mundo(pux), antes):
            for i in range(3):
                self.assertAlmostEqual(a[i], b[i], places=5)
        self.assertIs(bpy.context.object, pux)
        # Stored in the handles library category with a 45-degree photo;
        (it,) = addon.puxadores.modelos_do_usuario()
        self.assertEqual((it['nome'], it['arquivo'], pux['puxador_modelo']),
                         ('Barra Inox', 'Barra_Inox.blend', 'Barra_Inox.blend'))
        self.assertTrue(os.path.isfile(os.path.join(self.pasta, 'Barra_Inox.png')))
        self.assertEqual(self.fotos[0][1], addon.biblioteca.VISTA_FOTO)
        # the creator opens with that model selected.
        self.assertEqual(addon.puxadores.modelo_escolhido(bpy.context.scene),
                         ('MODELO', 'Barra_Inox.blend'))

    def test_solto_usa_a_face_clicada_e_o_lado_mais_comprido(self):
        from mathutils import Matrix
        # The bar stands far away; its bottom face (-Z) is the contact face,
        # so its 148 mm length runs along the edge.
        obj = barra('Alca Torta', (10, 148, 20),
                    Matrix.Translation((3.0, 0.0, 0.0)))
        self.assertEqual(bpy.ops.object.cabinet_usar_como_puxador(
            normal=(0.0, 0.0, -1.0)), {'FINISHED'})
        self.assertIn('Alca Torta', bpy.data.objects)     # The original stays.
        tipo, arquivo = addon.puxadores.modelo_escolhido(bpy.context.scene)
        self.assertEqual(tipo, 'MODELO')
        chapa = self.chapa()
        pux = addon.puxadores.criar_puxador(bpy.context, chapa, tipo, 'Y-', 1,
                                            0.5, arquivo)
        lo, hi = caixa_na_chapa(pux, chapa)
        self.assertAlmostEqual(hi[0] - lo[0], 148.0, places=2)   # Along the edge.
        self.assertAlmostEqual(hi[2] - lo[2], 20.0, places=2)    # Outward.
        self.assertAlmostEqual(lo[2], 9.0, places=2)             # On the face.
        self.assertEqual(pux.name, 'Handle Alca Torta')
        # No face and no touching panel: nothing to do.
        barra('Outra', (10, 10, 10), Matrix.Translation((5.0, 0.0, 0.0)))
        self.assertEqual(bpy.ops.object.cabinet_usar_como_puxador(),
                         {'CANCELLED'})

    def test_editar_o_modelo_na_biblioteca_muda_o_criador(self):
        from mathutils import Matrix
        barra('Puxador X', (100, 10, 20), Matrix.Translation((3.0, 0.0, 0.0)))
        bpy.ops.object.cabinet_usar_como_puxador(normal=(0.0, 0.0, -1.0))
        _tipo, arquivo = addon.puxadores.modelo_escolhido(bpy.context.scene)
        chapa = self.chapa()
        pux = addon.puxadores.criar_puxador(bpy.context, chapa, 'MODELO', 'Y-',
                                            1, 0.5, arquivo)
        self.assertAlmostEqual(pux['puxador_comprimento_mm'], 100.0, places=2)
        # The user opens the library .blend and lengthens the part.
        caminho = os.path.join(self.pasta, arquivo)
        with bpy.data.libraries.load(caminho) as (de, para):
            para.meshes = list(de.meshes)
        malha = para.meshes[0]
        malha.transform(Matrix.Diagonal((2.0, 1.0, 1.0, 1.0)))
        bpy.data.libraries.write(caminho, {malha}, fake_user=True)
        os.utime(caminho, (os.path.getatime(caminho),
                           os.path.getmtime(caminho) + 5))
        bpy.data.meshes.remove(malha)
        outro = addon.puxadores.criar_puxador(bpy.context, chapa, 'MODELO',
                                              'Y+', 1, 0.5, arquivo)
        self.assertAlmostEqual(outro['puxador_comprimento_mm'], 200.0, places=2)
        # The wire preview follows the new part's outline.
        pontos = addon.arame._arame_puxador(chapa, 'MODELO', 'X+', 1, 0.5,
                                            arquivo=arquivo)
        self.assertEqual(len(pontos), 24)          # The box's 12 edges.

    def test_modelos_de_fabrica_ficam_protegidos_na_biblioteca(self):
        fabrica = addon.biblioteca.itens_de_fabrica()
        self.assertEqual(
            [(it['n1'], it['valor']) for it in fabrica],
            [("Handles", t) for t in addon.puxadores.MODELOS_PADRAO]
            + [("Hinges", t) for t in addon.portas.NOME_DOBRADICA])
        self.assertTrue(all(addon.biblioteca.item_bloqueado(it) for it in fabrica))
        alca = next(it for it in fabrica if it['valor'] == 'ALCA')
        # Outside the index: neither the lock nor edit action can reach it.
        self.assertEqual(bpy.ops.object.cabinet_bloqueio(
            pasta=alca['pasta'], arquivo=alca['arquivo']), {'CANCELLED'})
        op = SimpleNamespace(report=lambda *a: None)
        for indice in (1, 2):
            self.assertIsNone(addon.gaveta_eventos._modelo_do_criador(
                op, bpy.context, alca, indice))
        # In the sidebar cascade under handles/pulls, using the factory photo.
        cena = bpy.context.scene
        antes = (cena.chapa_n1, cena.chapa_n2, cena.chapa_n3)
        self.addCleanup(setattr, cena, 'chapa_n3', antes[2])
        self.addCleanup(setattr, cena, 'chapa_n2', antes[1])
        self.addCleanup(setattr, cena, 'chapa_n1', antes[0])
        cena.chapa_n1, cena.chapa_n2, cena.chapa_n3 = "Handles", "Pull", ''
        presets = [v[5][1] for v in addon.gaveta._widgets_gaveta(
            bpy.context, 320, 1400) if v[5] and v[5][0] == 'preset']
        self.assertEqual([it['nome'] for it in presets], ["Pull"])
        self.assertTrue(os.path.isfile(os.path.join(
            presets[0]['pasta'], presets[0]['foto'])))
        # Clicking the photo or insert action opens the creator with that model.
        self.assertEqual(addon.gaveta_eventos._modelo_do_criador(
            op, bpy.context, alca, 0), 'CRIAR')
        self.assertEqual(addon.puxadores.modelo_escolhido(cena), ('ALCA', ''))
        reta = next(it for it in fabrica if it['valor'] == 'RETA')
        self.assertIsNone(addon.gaveta_eventos._modelo_do_criador(
            op, bpy.context, reta, 0))


addon.register()
suite = unittest.TestSuite(
    unittest.defaultTestLoader.loadTestsFromTestCase(caso)
    for caso in (TestPuxadores, TestModeloDoUsuario))
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError("Handle tests failed")
