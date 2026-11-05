"""Run: blender --background --factory-startup --python-exit-code 1 --python tests/test_walls_blender.py

Promob-style walls, as requested: a cabinet dropped on a wall places its back against it and becomes associated. Guides measure to endpoints, floor and ceiling; typing a guide moves the cabinet. Any vertical surface outside the add-on's furniture can be a wall.

Real modal events for right-button dragging and clicking guide numbers are covered in gui_interaction.py."""
import math
import os
import sys
import unittest
import tempfile
from unittest.mock import patch
from types import SimpleNamespace

import bpy
import bmesh
from mathutils import Euler, Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon

P = addon.paredes


def caixa(nome, dims, centro):
    """Create an unmarked box mesh representing a user-modeled wall."""
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
    bpy.context.scene.collection.objects.link(obj)
    obj.location = centro
    bpy.context.view_layer.update()
    return obj


class TestParedes(unittest.TestCase):
    def test_definir_parede_no_menu_e_retirar_definicao_preservam_geometria(self):
        conj=self.modulo();self.encostar(conj)
        bpy.ops.object.select_all(action='DESELECT');self.parede.select_set(True)
        bpy.context.view_layer.objects.active=self.parede
        self.assertTrue(P.OBJECT_OT_definir_alvenaria.poll(bpy.context))
        antes=conj.matrix_world.copy()
        self.assertFalse(P.alvenaria_definida(self.parede))
        self.assertEqual(bpy.ops.object.cabinet_definir_alvenaria(),{'FINISHED'})
        self.assertTrue(P.alvenaria_definida(self.parede))
        itens=[];addon.paredes_edicao.widgets(bpy.context,itens,0,500,300)
        self.assertTrue(any(i[5] == ('operador','object.cabinet_editar_parede') for i in itens))
        self.assertEqual(bpy.ops.object.cabinet_definir_alvenaria(),{'FINISHED'})
        self.assertFalse(P.alvenaria_definida(self.parede))
        self.assertNotIn(P.CHAVE_PAREDE,conj)
        self.assertEqual(conj.matrix_world,antes)
        itens=[];addon.alvenaria.widgets_classificar(bpy.context,itens,0,500,300)
        self.assertTrue(any(i[4] == "Create Masonry" for i in itens))
        self.assertFalse(any(i[5] == ('operador','object.cabinet_editar_parede') for i in itens))

    def test_snap_nativo_ignora_malhas_nao_definidas_mesmo_na_frente_da_parede(self):
        caixa('Obstaculo nao definido',(3,.1,2.7),(0,0,1.35))
        self.assertIsNone(P.raio_ate_parede(bpy.context,(0,-2,1),(0,1,0),set()))
        self.parede[P.CHAVE_ALVENARIA]=True
        acerto=P.raio_ate_parede(bpy.context,(0,-2,1),(0,1,0),set())
        self.assertIs(acerto[0],self.parede)
        self.assertAlmostEqual(acerto[1].y,1,places=5)
        del self.parede[P.CHAVE_ALVENARIA]
        self.assertIsNone(P.raio_ate_parede(bpy.context,(0,-2,1),(0,1,0),set()))

    def test_um_bloco_definido_libera_suas_duas_faces_e_piso(self):
        piso=caixa('Piso para unir',(4,4,.1),(0,0,-.05))
        inv=self.parede.matrix_world.inverted_safe();vertices=[];faces=[]
        for o in (self.parede,piso):
            offset=len(vertices)
            vertices.extend(tuple(inv@o.matrix_world@v.co) for v in o.data.vertices)
            faces.extend(tuple(offset+i for i in f.vertices) for f in o.data.polygons)
        m=bpy.data.meshes.new('Casa unica');m.from_pydata(vertices,[],faces)
        self.parede.data=m;bpy.data.objects.remove(piso,do_unlink=True)
        self.parede[P.CHAVE_ALVENARIA]=True;bpy.context.view_layer.update()
        for origem,direcao in (((0,0,1),(0,1,0)),((0,2,1),(0,-1,0)),((0,0,2),(0,0,-1))):
            acerto=P.raio_ate_parede(bpy.context,origem,direcao,set())
            self.assertIs(acerto[0],self.parede)
        self.assertTrue(P.eh_piso(acerto[2]))

    def test_alvenaria_definida_na_biblioteca_tambem_nao_impoe_largura_da_face(self):
        conj=self.modulo();pequena=caixa('Parede estreita',(.1,.1,1),(0,4,.5))
        pequena[P.CHAVE_ALVENARIA]=True;p=Vector((0,3.95,.5));n=Vector((0,-1,0))
        s=dict(parede=pequena.name,ponto=tuple(p),normal=tuple(n),u=(1,0,0),
               regiao=P.regiao_da_parede(pequena,p,n))
        antes=tuple((v.copy() for v in P.caixa_do_modulo(conj)))
        alvo,erro=addon.paredes_edicao.encaixar_na_face(bpy.context,conj,p,s)
        self.assertIsNone(erro);self.assertIsNotNone(alvo)
        depois=P.caixa_do_modulo(conj)
        self.assertVetor(antes[0],depois[0],6);self.assertVetor(antes[1],depois[1],6)

    def arrastador(self,conj):
        classe=P.OBJECT_OT_arrastar_na_parede
        ctx=SimpleNamespace(scene=bpy.context.scene,view_layer=bpy.context.view_layer,
            evaluated_depsgraph_get=bpy.context.evaluated_depsgraph_get,
            window=SimpleNamespace(cursor_modal_restore=lambda:None),
            workspace=SimpleNamespace(status_text_set=lambda _:None),
            area=SimpleNamespace(tag_redraw=lambda:None))
        regiao=SimpleNamespace(as_pointer=lambda:123)
        op=SimpleNamespace(_modulo=conj.name,_ignorar=set(),_regiao=regiao,_rv3d=None,
            _caixa=P.caixa_do_modulo(conj),_matriz=conj.matrix_world.copy(),_parede=None,
            _arrastou=True,_limbo=False,_associacao={k:getattr(conj[k],'to_list',lambda:conj[k])()
                for k in P.CHAVES_ASSOCIACAO if k in conj},report=lambda *_:None)
        op._restaurar=lambda c:classe._restaurar(op,c)
        op._encerrar=lambda c:classe._encerrar(op,c)
        op._status=lambda *_:None
        op._mover=lambda c,e:classe._mover(op,c,e)
        evento=SimpleNamespace(type='RIGHTMOUSE',value='RELEASE',mouse_region_x=0,mouse_region_y=0)
        return classe,op,ctx,evento

    def test_arraste_em_parede_pequena_permite_sobrar_sem_piscar(self):
        conj=self.modulo();self.encostar(conj)
        pequena=caixa('Parede pequena',(.1,.1,.1),(0,4,.05))
        pequena[P.CHAVE_ALVENARIA]=True
        classe,op,ctx,evento=self.arrastador(conj)
        matriz=conj.matrix_world.copy();props=dict(op._associacao)
        with patch.object(P,'_raio_ignorando',return_value=(pequena,Vector((0,3.95,.05)),Vector((0,-1,0)),None)), \
             patch.object(P,'_px_por_metro',return_value=100):
            op._mover(ctx,evento)
            self.assertTrue(P._arraste_parede[0]['valido'])
            self.assertTrue(P._arraste_parede[0]['contorno'])
            self.assertEqual(classe.modal(op,ctx,evento),{'FINISHED'})
        self.assertIsNone(P.erro_visivel())
        self.assertIs(P.parede_do_modulo(conj),pequena)

    def test_soltar_revalida_definicao_removida_depois_da_previa(self):
        conj=self.modulo();classe,op,ctx,evento=self.arrastador(conj)
        self.parede[P.CHAVE_ALVENARIA]=True
        acerto=(self.parede,Vector((0,1,1)),Vector((0,-1,0)),None)
        with patch.object(P,'_raio_ignorando',return_value=acerto),patch.object(P,'_px_por_metro',return_value=100):
            op._mover(ctx,evento)
            self.assertTrue(P._arraste_parede[0]['valido'])
            del self.parede[P.CHAVE_ALVENARIA]
            self.assertEqual(classe.modal(op,ctx,evento),{'CANCELLED'})
        self.assertNotIn(P.CHAVE_PAREDE,conj)

    def test_piso_pequeno_permite_sobrar_teto_e_esc_nao_disparam_erro(self):
        conj=self.modulo();pequeno=caixa('Piso pequeno',(.1,.1,.1),(0,0,-.05))
        pequeno[P.CHAVE_ALVENARIA]=True
        classe,op,ctx,e=self.arrastador(conj)
        with patch.object(P,'_raio_ignorando',return_value=(pequeno,Vector((0,0,0)),Vector((0,0,1)),None)), \
             patch.object(P,'_px_por_metro',return_value=100):
            self.assertEqual(classe.modal(op,ctx,e),{'FINISHED'})
        self.assertIs(P.parede_do_modulo(conj),pequeno)
        self.assertIsNone(P.regiao_do_piso(pequeno,Vector((0,0,-.1)),Vector((0,0,-1))))
        self.assertFalse(P.eh_piso(Vector((0,.02,1))))
        classe,op,ctx,e=self.arrastador(conj);e.type='ESC';e.value='PRESS'
        self.assertEqual(classe.modal(op,ctx,e),{'CANCELLED'})
        self.assertIsNone(P._erro_apoio[0])

    def test_piso_conserva_contorno_com_buraco_sem_impor_limites_ao_modulo(self):
        conj=self.modulo()
        malha=bpy.data.meshes.new('Piso vazado')
        ps=[(x,y,0) for x,y in ((-1.5,-1.5),(1.5,-1.5),(1.5,1.5),(-1.5,1.5),
                                (-.2,-.2),(.2,-.2),(.2,.2),(-.2,.2))]
        malha.from_pydata(ps,[],[(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
        piso=bpy.data.objects.new('Piso vazado',malha);bpy.context.scene.collection.objects.link(piso)
        bpy.context.view_layer.update()
        r=P.regiao_do_piso(piso,Vector((0,-1,0)),Vector((0,0,1)))
        self.assertEqual(len(r['contorno']),8)
        self.assertEqual(len(r['faces']),4)

    def test_arraste_no_piso_confirma_sem_bloquear_por_outro_modulo(self):
        conj=self.modulo();piso=caixa("Floor",(4,4,.1),(0,0,-.05))
        piso[P.CHAVE_ALVENARIA]=True
        # A second cabinet copies only the carcass through the existing operator.
        outro=addon.modulos.criar_armario(bpy.context,'Vizinho',800,700,600)
        outro.location=(0,0,0);bpy.context.view_layer.update()
        classe,op,ctx,e=self.arrastador(conj)
        with patch.object(P,'_raio_ignorando',return_value=(piso,Vector((0,0,0)),Vector((0,0,1)),None)), \
             patch.object(P,'_px_por_metro',return_value=100):
            self.assertEqual(classe.modal(op,ctx,e),{'FINISHED'})
        bpy.context.view_layer.update()
        a=self.cantos_do_envelope(conj)
        b=[o.matrix_world@Vector(c) for o in addon.modulos.pecas_do_envelope(outro) for c in o.bound_box]
        self.assertGreater(min(max(p.x for p in a),max(p.x for p in b))-max(min(p.x for p in a),min(p.x for p in b)),0)
        self.assertGreater(min(max(p.y for p in a),max(p.y for p in b))-max(min(p.y for p in a),min(p.y for p in b)),0)
        self.assertIs(P.parede_do_modulo(conj),piso)
        self.assertIsNone(P._arraste_parede[0]);self.assertIsNone(P._erro_apoio[0])

    def test_piso_afastamento_g_zero_guias_e_movimento_do_apoio(self):
        conj=self.modulo();piso=caixa("Floor",(4,4,.1),(0,0,-.05))
        P.associar(conj,piso,Vector((.3,.2,0)),Vector((0,0,1)))
        P.colocar_na_parede(conj,piso,Vector((.3,.2,0)),Vector((0,0,1)))
        bpy.context.view_layer.update();P.manter_nas_paredes()
        self.assertNotIn('afastamento',P.calcular_guias(conj)['valores'])
        conj.location.z+=.25;bpy.context.view_layer.update();P.manter_nas_paredes()
        self.assertAlmostEqual(P.afastamento(conj),.25,places=6)
        self.assertAlmostEqual(P.calcular_guias(conj)['valores']['afastamento'],250,places=3)
        piso.location.x+=1;piso.location.z+=.3;piso.rotation_euler.z=math.pi/2
        bpy.context.view_layer.update();P.manter_nas_paredes()
        self.assertVetor(P._ponto_da_base(conj),(.8,.3,.55),5)
        self.assertVetor(conj.matrix_world.to_3x3().col[2],(0,0,1),5)
        P.aplicar_guia(conj,'afastamento',0)
        bpy.context.view_layer.update();P.manter_nas_paredes()
        self.assertAlmostEqual(P._ponto_da_base(conj).z,.3,places=5)
        self.assertNotIn('afastamento',P.calcular_guias(conj)['valores'])
        P.desassociar(conj);self.assertNotIn(P.CHAVE_EIXO_PISO,conj)

    def test_piso_cache_nao_rele_malha_parada_e_erro_limpa_no_timer(self):
        piso=caixa("Floor",(4,4,.1),(0,0,-.05))
        r=P.regiao_do_piso(piso,Vector((0,0,0)),Vector((0,0,1)))
        with patch.object(P,'_calcular_regiao',side_effect=AssertionError('Releu malha')):
            for _ in range(20):self.assertIs(P.regiao_do_piso(piso,Vector((.1,.1,0)),Vector((0,0,1))),r)
        with patch.object(P.time,'monotonic',return_value=10):P.sinalizar_erro(r,123)
        with patch.object(P.time,'monotonic',return_value=11):
            self.assertIsNone(P._tique_erro_apoio())
        self.assertIsNone(P._erro_apoio[0])

    def test_roda_no_piso_gira_em_pe_e_esc_devolve_pose_e_associacao(self):
        conj=self.modulo();piso=caixa("Floor",(4,4,.1),(0,0,-.05))
        piso[P.CHAVE_ALVENARIA]=True
        classe,op,ctx,e=self.arrastador(conj);antes=conj.matrix_world.copy()
        with patch.object(P,'_raio_ignorando',return_value=(piso,Vector((0,0,0)),Vector((0,0,1)),None)), \
             patch.object(P,'_px_por_metro',return_value=100):
            op._mover(ctx,e)
            u=conj.matrix_world.to_3x3().col[0].normalized()
            e.type='WHEELUPMOUSE';e.value='PRESS'
            self.assertEqual(classe.modal(op,ctx,e),{'RUNNING_MODAL'})
            self.assertAlmostEqual(u.dot(conj.matrix_world.to_3x3().col[0].normalized()),0,places=5)
            self.assertVetor(conj.matrix_world.to_3x3().col[2].normalized(),(0,0,1),5)
            e.type='ESC'
            self.assertEqual(classe.modal(op,ctx,e),{'CANCELLED'})
        self.assertEqual(conj.matrix_world,antes)
        self.assertNotIn(P.CHAVE_EIXO_PISO,conj)

    def test_piso_e_gap_sobrevivem_salvar_reabrir_sem_reconstruir_geometria(self):
        conj=self.modulo();nome=conj.name;piso=caixa("Floor",(4,4,.1),(0,0,-.05))
        conj.rotation_euler.z=.4;bpy.context.view_layer.update()
        P.associar(conj,piso,Vector((.2,.3,0)),Vector((0,0,1)))
        P.definir_afastamento(conj,.12)
        P.colocar_na_parede(conj,piso,Vector((.2,.3,0)),Vector((0,0,1)))
        bpy.context.view_layer.update();P.manter_nas_paredes()
        uid=conj[P.CHAVE_PAREDE];conj=None;piso=None
        with tempfile.TemporaryDirectory(prefix='apoio_piso_') as pasta:
            caminho=os.path.join(pasta,'apoio.blend')
            bpy.ops.wm.save_as_mainfile(filepath=caminho)
            bpy.ops.wm.open_mainfile(filepath=caminho)
            addon.eventos._fim_do_desfazer();P.manter_nas_paredes()
            rec=bpy.data.objects[nome]
            self.assertEqual(rec[P.CHAVE_PAREDE],uid)
            self.assertAlmostEqual(rec.rotation_euler.z,.4,places=5)
            self.assertAlmostEqual(P.afastamento(rec),.12,places=5)
            self.assertAlmostEqual(P._ponto_da_base(rec).z,.12,places=5)
            self.assertIsNotNone(P.calcular_guias(rec))

    def test_g_nativo_afasta_da_parede_e_publica_cota_sem_perder_vinculo(self):
        # Regression v393: the timer undid the offset confirmed through G.
        conj=self.modulo();self.encostar(conj)
        bpy.ops.object.select_all(action='DESELECT');conj.select_set(True)
        bpy.context.view_layer.objects.active=conj
        bpy.ops.transform.translate(value=(.1,-.25,.05))
        bpy.context.view_layer.update()
        antes=conj.matrix_world.copy()
        P.manter_nas_paredes()
        self.assertVetor(conj.matrix_world.translation,antes.translation,6)
        self.assertAlmostEqual(P.afastamento(conj),.25,places=6)
        self.assertAlmostEqual(P.calcular_guias(conj)['valores']['afastamento'],250,places=3)
        self.assertIs(P.parede_do_modulo(conj),self.parede)

    def test_afastamento_digitado_zero_e_negativo_nao_alteram_malha(self):
        conj=self.modulo();self.encostar(conj)
        malhas={o.name:(o.data.as_pointer(),[tuple(v.co) for v in o.data.vertices])
                for o in addon.modulos.pecas_do_envelope(conj)}
        conj.location.y-=.2;bpy.context.view_layer.update();P.manter_nas_paredes()
        self.assertAlmostEqual(P.afastamento(conj),.2,places=6)
        P.aplicar_guia(conj,'afastamento',0);bpy.context.view_layer.update();P.manter_nas_paredes()
        self.assertAlmostEqual(P.ponto_das_costas(conj).y,1,places=6)
        self.assertNotIn('afastamento',P.calcular_guias(conj)['linhas'])
        conj.location.y+=.15;bpy.context.view_layer.update();P.manter_nas_paredes()
        self.assertAlmostEqual(P.ponto_das_costas(conj).y,1,places=6)
        self.assertEqual({o.name:(o.data.as_pointer(),[tuple(v.co) for v in o.data.vertices])
                for o in addon.modulos.pecas_do_envelope(conj)},malhas)

    def test_afastamento_nativo_undo_redo_reconstroi_vinculo_fora_da_guarda(self):
        conj=self.modulo();nome=conj.name;self.encostar(conj)
        bpy.context.preferences.edit.use_global_undo=True
        bpy.ops.object.select_all(action='DESELECT');conj.select_set(True)
        bpy.context.view_layer.objects.active=conj
        bpy.ops.ed.undo_push(message='Antes do afastamento')
        bpy.ops.transform.translate(value=(0,-.2,0))
        bpy.context.view_layer.update();P.manter_nas_paredes()
        bpy.ops.ed.undo_push(message='Afastamento confirmado')
        conj=None
        bpy.ops.ed.undo();addon.eventos._fim_do_desfazer();P.manter_nas_paredes()
        self.assertAlmostEqual(P.afastamento(bpy.data.objects[nome]),0,places=6)
        bpy.ops.ed.redo();addon.eventos._fim_do_desfazer();P.manter_nas_paredes()
        self.assertAlmostEqual(P.afastamento(bpy.data.objects[nome]),.2,places=6)
        self.assertIsNotNone(P.parede_do_modulo(bpy.data.objects[nome]))

    def test_piso_encaixa_base_sem_deitar_e_conserva_giro(self):
        conj=self.modulo();conj.rotation_euler.z=.63
        piso=caixa("Floor",(4,4,.1),(0,0,-.05))
        bpy.context.view_layer.update()
        regiao=P.regiao_do_piso(piso,Vector((0,0,0)),Vector((0,0,1)))
        ponto=Vector((0,0,0))
        P.associar(conj,piso,ponto,Vector((0,0,1)),regiao['face'])
        self.assertTrue(P.colocar_na_parede(conj,piso,ponto,Vector((0,0,1))))
        bpy.context.view_layer.update();P.manter_nas_paredes()
        self.assertAlmostEqual(min(p.z for p in self.cantos_do_envelope(conj)),0,places=6)
        self.assertVetor(conj.matrix_world.to_3x3().col[2].normalized(),(0,0,1),6)
        self.assertAlmostEqual(conj.rotation_euler.z,.63,places=5)
        self.assertIs(P.parede_do_modulo(conj),piso)

    def test_erro_de_encaixe_guarda_face_para_tres_piscadas_sem_guardar_objeto(self):
        import numpy as np
        visual=dict(contorno=[(Vector((0,0,0)),Vector((1,0,0)))],triangulos=np.zeros((3,3)))
        with patch.object(P.time,'monotonic',return_value=10):
            P.sinalizar_erro(visual,123)
        for i in range(6):
            self.assertEqual(P.erro_visivel(10+(i+.25)*P.PISCA_ERRO_S) is not None,i%2==0)
        self.assertIsNone(P.erro_visivel(10+6*P.PISCA_ERRO_S+.001))
        P.esquecer()
        self.assertIsNone(P._erro_apoio[0])
        self.assertFalse(bpy.app.timers.is_registered(P._tique_erro_apoio))
        ctx=SimpleNamespace(region=SimpleNamespace(as_pointer=lambda:123),region_data=None)
        P._arraste_parede[0]=dict(visual,valido=False,modulo='fixture')
        with patch.object(P,'_desenhar_face_alvo') as desenho:
            P.desenhar_guias(ctx)
        self.assertEqual(desenho.call_args.args[2],P.COR_ALVO_APOIO)
        self.assertFalse(desenho.call_args.args[0]['valido'])

    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for colecao in list(bpy.data.collections):
            bpy.data.collections.remove(colecao)
        camada = bpy.context.view_layer
        camada.active_layer_collection = camada.layer_collection
        P.esquecer()
        # 3000 x 2700 wall, front face at y = 1 m looking toward -Y.
        self.parede = caixa("Wall", (3.0, 0.15, 2.7), (0.0, 1.075, 1.35))

    def modulo(self):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        self.parede.select_set(False)
        bpy.ops.object.cabinet_agrupar()
        conj = next(o for o in bpy.data.objects
                    if addon.chapas.MARCA_CONJUNTO in o)
        bpy.context.view_layer.update()
        return conj

    def medidas(self, conj):
        lo, hi = P.caixa_do_modulo(conj)
        return (hi.x - lo.x) * 1000, (hi.z - lo.z) * 1000

    def encostar(self, conj, s=0.0, base=0.5):
        """Perform the drag-release behavior without using the mouse."""
        normal = Vector((0.0, -1.0, 0.0))
        costas = Vector((s, 1.0, base))
        self.assertTrue(P.colocar_na_parede(conj, self.parede, costas, normal))
        P.associar(conj, self.parede, costas, normal)
        bpy.context.view_layer.update()
        P.manter_nas_paredes()
        return costas

    def assertVetor(self, a, b, casas=4):
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=casas)

    def moldura_pesada(self, conj):
        return addon.portas.porta_no_modulo(conj,folhas=2,abertura='CORRER',
            moldura_mm=15,rodape_mm=100,testeira_mm=80)

    def cantos_do_envelope(self, conj):
        # Independent oracle: native part boxes, including supports.
        bpy.context.view_layer.update()
        return [o.matrix_world@Vector(c) for o in addon.modulos.pecas_do_envelope(conj)
                for c in o.bound_box]

    def test_caixa_de_parede_inclui_apoios_da_porta_pesada_como_o_grupo(self):
        # Regression v390: the HUD included the frame, but fitting measured only the carcass.
        conj=self.modulo()
        corpo=tuple(v.copy() for v in P.caixa_local_do_modulo(conj))
        grupo=self.moldura_pesada(conj)
        pontos=[conj.matrix_world.inverted()@p for p in self.cantos_do_envelope(conj)]
        lo,hi=P.caixa_local_do_modulo(conj)
        self.assertVetor(lo,tuple(min(p[i] for p in pontos) for i in range(3)),6)
        self.assertVetor(hi,tuple(max(p[i] for p in pontos) for i in range(3)),6)
        self.assertLess(lo.x,corpo[0].x)
        self.assertGreater(hi.x,corpo[1].x)
        self.assertLess(lo.z,corpo[0].z)
        self.assertEqual(P.frente_do_modulo(conj),'NEG_Y')
        # The door opening retains its structural reference without feeding the frame back in.
        interno=addon.portas._limites_locais_modulo(conj)
        self.assertVetor(interno[0]/1000,corpo[0],6)
        self.assertVetor(interno[1]/1000,corpo[1],6)

    def test_encostar_costas_diferentes_usa_envelope_em_modulo_girado(self):
        conj=self.modulo();self.moldura_pesada(conj)
        conj.location=(2,3,.4);conj.rotation_euler.z=.73
        bpy.context.view_layer.update()
        n=Vector((0,-1,0));alvo=Vector((.1,1,.35))
        for lado in P.LADOS_COSTAS:
            with self.subTest(lado=lado):
                conj[P.CHAVE_COSTAS]=lado
                self.assertTrue(P.colocar_na_parede(conj,self.parede,alvo,n))
                pontos=self.cantos_do_envelope(conj)
                self.assertAlmostEqual(max(p.y for p in pontos),1,places=6)
                self.assertAlmostEqual(min(p.z for p in pontos),.35,places=6)
                self.assertAlmostEqual((min(p.x for p in pontos)+max(p.x for p in pontos))/2,.1,places=6)

    def test_envelope_ignora_abertura_puxador_e_chapa_desvinculada(self):
        conj=self.modulo();grupo=self.moldura_pesada(conj)
        antes=[v.copy() for v in P.caixa_local_do_modulo(conj)]
        folhas=addon.portas._folhas_portas(grupo)
        folhas[0].location.x+=5
        pux=addon.puxadores.criar_puxador(bpy.context,folhas[1],'ALCA','X+',1)
        pux.location.x+=8
        solta=addon.modulos._chapas_do_conjunto(conj)[0]
        # A copy outside the group does not enlarge the assembly reference.
        copia=solta.copy();copia.data=solta.data.copy();copia.parent=None
        bpy.context.scene.collection.objects.link(copia);copia.location.x=20
        bpy.context.view_layer.update()
        depois=P.caixa_local_do_modulo(conj)
        self.assertVetor(depois[0],antes[0],6)
        self.assertVetor(depois[1],antes[1],6)

    def sessao_da_face(self):
        ponto=Vector((0,1,1));normal=Vector((0,-1,0))
        return dict(parede=self.parede.name,ponto=tuple(ponto),normal=tuple(normal),
            u=(1,0,0),regiao=P.regiao_da_parede(self.parede,ponto,normal))

    def test_snap_e_cotas_respeitam_os_apoios_nos_limites_da_parede(self):
        conj=self.modulo();self.moldura_pesada(conj);s=self.sessao_da_face()
        for alvo in ((-1.5,1,0),(1.5,1,2.7)):
            with self.subTest(alvo=alvo):
                costas,erro=addon.paredes_edicao.encaixar_na_face(bpy.context,conj,Vector(alvo),s)
                self.assertIsNone(erro)
                P.colocar_na_parede(conj,self.parede,costas,Vector(s['normal']))
                pontos=self.cantos_do_envelope(conj)
                xmin,xmax=min(p.x for p in pontos),max(p.x for p in pontos)
                zmin,zmax=min(p.z for p in pontos),max(p.z for p in pontos)
                self.assertGreaterEqual(xmin,-1.500001);self.assertLessEqual(xmax,1.500001)
                self.assertGreaterEqual(zmin,-.000001);self.assertLessEqual(zmax,2.700001)
                ficha=addon.paredes_composicao.ficha(conj,s)
                self.assertAlmostEqual(ficha['inicio'],xmin,places=6)
                self.assertAlmostEqual(ficha['base'],zmin,places=6)
                self.assertAlmostEqual(ficha['largura'],xmax-xmin,places=6)

    def test_snap_entre_modulos_nao_atravessa_a_moldura_do_vizinho(self):
        primeiro=self.modulo();self.moldura_pesada(primeiro)
        self.encostar(primeiro,base=0)
        segundo=addon.modulos.criar_armario(bpy.context,'Vizinho',600,700,550)
        self.moldura_pesada(segundo);s=self.sessao_da_face()
        bpy.context.view_layer.update()
        costas,erro=addon.paredes_edicao.encaixar_na_face(bpy.context,segundo,Vector((.31,1,.4)),s)
        self.assertIsNone(erro)
        P.colocar_na_parede(segundo,self.parede,costas,Vector(s['normal']))
        pontos_a=self.cantos_do_envelope(primeiro);pontos_b=self.cantos_do_envelope(segundo)
        self.assertAlmostEqual(min(p.x for p in pontos_b),max(p.x for p in pontos_a),places=6)

    def test_parede_e_superficie_vertical_que_nao_e_movel(self):
        n, u = P.eixos_da_parede(Vector((0.0, -1.0, 0.0)))
        self.assertVetor(n, (0, -1, 0))
        self.assertVetor(u, (1, 0, 0))        # To the viewer's right when looking at the wall.
        self.assertIsNone(P.eixos_da_parede(Vector((0.0, 0.0, 1.0))))    # Floor.
        self.assertIsNone(P.eixos_da_parede(Vector((0.0, -0.4, -0.9))))  # Ceiling.
        # The cabinet back (+Y) points into the wall.
        self.assertVetor(P.rotacao_na_parede(n, u) @ Vector((0, 1, 0)), (0, 1, 0))
        conj = self.modulo()
        self.assertTrue(P.eh_movel(conj))
        self.assertTrue(P.eh_movel(addon.modulos._chapas_do_conjunto(conj)[0]))
        self.assertFalse(P.eh_movel(self.parede))

    def test_limites_da_parede_sao_as_faces_do_mesmo_plano(self):
        retangulo = P.retangulo_da_parede(
            self.parede, Vector((0.4, 1.0, 1.0)), Vector((0.0, -1.0, 0.0)))
        self.assertVetor(retangulo, (-1.5, 1.5, 0.0, 2.7))
        # The rear face is a different wall with opposite normal and mirrored endpoints.
        retangulo = P.retangulo_da_parede(
            self.parede, Vector((0.4, 1.15, 1.0)), Vector((0.0, 1.0, 0.0)))
        self.assertVetor(retangulo, (-1.5, 1.5, 0.0, 2.7))

    def test_regiao_de_malha_pesada_em_lote_e_uma_vez_por_parede(self):
        # User's real scene: a house with hundreds of thousands of faces froze on every
        # mouse move. Compute the region in a batch for all its faces;
        # moving along the wall must not recalculate it.
        import time
        from unittest.mock import patch
        casa = caixa('Casa', (3.0, 0.15, 2.7), (0.0, 5.075, 1.35))
        bm = bmesh.new()
        bm.from_mesh(casa.data)
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=120, use_grid_fill=True)
        bm.to_mesh(casa.data)
        bm.free()
        bpy.context.view_layer.update()
        self.assertGreater(len(casa.data.polygons), 80000)
        normal = Vector((0, -1, 0))
        dep = bpy.context.evaluated_depsgraph_get()
        inicio = time.perf_counter()
        a = P.regiao_da_parede(casa, Vector((-1.0, 5.0, .5)), normal, dep)
        self.assertLess(time.perf_counter() - inicio, 2.0)
        s0, s1, z0, z1 = a['retangulo']
        self.assertAlmostEqual(s1 - s0, 3.0, places=4)
        self.assertAlmostEqual(z1 - z0, 2.7, places=4)
        self.assertEqual(len(a['faces']), 121 * 121)
        # Outline = only the face boundary, four sides of 121 edges.
        self.assertEqual(len(a['contorno']), 4 * 121)
        self.assertEqual(len(a['triangulos']), 3 * 2 * 121 * 121)
        outra = next(f for f in a['faces'] if f != a['face'])
        with patch.object(P, '_calcular_regiao', side_effect=AssertionError('recalculou')):
            b = P.regiao_da_parede(casa, Vector((1.0, 5.0, 2.0)), normal, dep, outra)
            # Legacy association without an index: the plane rectangle suffices.
            c = P.regiao_da_parede(casa, Vector((0.0, 5.0, 1.0)), normal, dep)
        self.assertEqual(b['face'], outra)
        self.assertEqual(b['retangulo'], a['retangulo'])
        self.assertEqual(c['faces'], a['faces'])

    def test_soltar_encosta_as_costas_e_mede_as_guias(self):
        conj = self.modulo()
        conj.rotation_euler = Euler((0, 0, math.radians(70)))  # Initially tilted.
        bpy.context.view_layer.update()
        largura, altura = self.medidas(conj)
        self.encostar(conj, s=0.2, base=0.5)
        # Facing away from the wall, with its back in the y = 1 m plane.
        self.assertVetor(conj.matrix_world.to_3x3() @ Vector((0, 1, 0)), (0, 1, 0))
        self.assertAlmostEqual(P.ponto_das_costas(conj).y, 1.0, places=5)
        guias = P.calcular_guias(conj)
        valores = guias['valores']
        self.assertAlmostEqual(valores['piso'], 500.0, places=2)
        self.assertAlmostEqual(valores['teto'], 2700.0 - 500.0 - altura, places=2)
        self.assertAlmostEqual(valores['esquerda'], 1700.0 - largura / 2, places=2)
        self.assertAlmostEqual(valores['direita'], 1300.0 - largura / 2, places=2)
        # Each line runs from wall to cabinet, 1 mm in front of the wall.
        a, b = guias['linhas']['piso']
        self.assertAlmostEqual(a.z, 0.0, places=5)
        self.assertAlmostEqual(b.z, 0.5, places=5)
        self.assertAlmostEqual(a.y, 1.0 - P.DESLOCAMENTO_GUIA_M, places=6)
        # UID stored on the wall; wall reference stored on the cabinet.
        self.assertEqual(conj[P.CHAVE_PAREDE], self.parede[P.CHAVE_UID_PAREDE])
        self.assertIs(P.parede_do_modulo(conj), self.parede)

    def test_digitar_a_guia_leva_o_modulo(self):
        # User drawing: 1000 from the left, 1200 from the floor.
        conj = self.modulo()
        largura, altura = self.medidas(conj)
        self.encostar(conj)
        self.assertTrue(P.aplicar_guia(conj, 'esquerda', 1000.0))
        self.assertTrue(P.aplicar_guia(conj, 'piso', 1200.0))
        valores = P.calcular_guias(conj)['valores']
        self.assertAlmostEqual(valores['esquerda'], 1000.0, places=2)
        self.assertAlmostEqual(valores['piso'], 1200.0, places=2)
        self.assertAlmostEqual(valores['direita'], 3000.0 - 1000.0 - largura, places=2)
        self.assertAlmostEqual(valores['teto'], 2700.0 - 1200.0 - altura, places=2)
        # Also through right and ceiling guides; the back stays on the wall.
        P.aplicar_guia(conj, 'direita', 350.0)
        P.aplicar_guia(conj, 'teto', 200.0)
        valores = P.calcular_guias(conj)['valores']
        self.assertAlmostEqual(valores['direita'], 350.0, places=2)
        self.assertAlmostEqual(valores['teto'], 200.0, places=2)
        self.assertAlmostEqual(P.ponto_das_costas(conj).y, 1.0, places=5)

    def test_zero_digitado_nas_guias_da_parede_encosta_o_modulo(self):
        conj = self.modulo()
        for lado in P.LADOS:
            with self.subTest(lado=lado):
                self.encostar(conj, s=.2, base=.4)
                avisos = []
                op = SimpleNamespace(_aplicar=lambda contexto, valor: P.aplicar_guia(conj, lado, valor),
                    report=lambda categoria, mensagem: avisos.append(mensagem))
                P._edicao_guia[0] = dict(texto='0', cursor=1, selecionado=False)
                evento = SimpleNamespace(value='PRESS', type='RET', ctrl=False, unicode='')
                self.assertEqual(P.OBJECT_OT_guia_parede._digitar(op, bpy.context, evento),
                                 {'FINISHED'}, avisos)
                self.assertAlmostEqual(P.calcular_guias(conj)['valores'][lado], 0, places=2)
                self.assertIsNone(P._edicao_guia[0])

    def test_parede_que_anda_e_gira_leva_o_modulo(self):
        conj = self.modulo()
        self.encostar(conj, s=0.3, base=0.4)
        antes = P.calcular_guias(conj)['valores']
        self.parede.location.x += 0.5
        self.parede.rotation_euler.z = math.radians(90)
        bpy.context.view_layer.update()
        self.assertTrue(P.manter_nas_paredes())
        depois = P.calcular_guias(conj)['valores']
        for lado in P.LADOS:
            self.assertAlmostEqual(depois[lado], antes[lado], places=2, msg=lado)
        # Rotated together: the back now points toward +X, into the wall.
        normal = P._normal_no_mundo(self.parede, conj[P.CHAVE_PAREDE_NORMAL])
        self.assertVetor(conj.matrix_world.to_3x3() @ Vector((0, 1, 0)), -normal)
        # Stationary: nothing else changes.
        self.assertFalse(P.manter_nas_paredes())

    def test_modulo_movido_so_desliza_na_parede(self):
        conj = self.modulo()
        self.encostar(conj, s=0.0, base=0.5)
        # G away from the wall and R to tilt: restore the plane while keeping other changes.
        conj.location += Vector((0.25, -0.4, 0.1))
        conj.rotation_euler.z += math.radians(30)
        bpy.context.view_layer.update()
        self.assertTrue(P.manter_nas_paredes())
        self.assertAlmostEqual(P.ponto_das_costas(conj).y, 1.0, places=5)
        self.assertVetor(conj.matrix_world.to_3x3() @ Vector((0, 1, 0)), (0, 1, 0))
        self.assertAlmostEqual(P.calcular_guias(conj)['valores']['piso'], 600.0, places=2)

    def test_desassociar_solta_o_modulo(self):
        conj = self.modulo()
        self.encostar(conj)
        for o in bpy.context.selected_objects:
            o.select_set(False)
        conj.select_set(True)
        bpy.context.view_layer.objects.active = conj
        self.assertEqual(bpy.ops.object.cabinet_desassociar_parede(), {'FINISHED'})
        self.assertNotIn(P.CHAVE_PAREDE, conj)
        conj.location.y -= 0.5
        bpy.context.view_layer.update()
        self.assertFalse(P.manter_nas_paredes())      # No longer returns.
        self.assertEqual(bpy.ops.object.cabinet_desassociar_parede(), {'CANCELLED'})

    def test_parede_duplicada_desempata_pelo_nome(self):
        conj = self.modulo()
        self.encostar(conj)
        copia = self.parede.copy()          # Shift+D copies the UID.
        bpy.context.scene.collection.objects.link(copia)
        self.assertIs(P.parede_do_modulo(conj), self.parede)
        self.parede.name = 'Parede Renomeada'   # Renaming does not unlink.
        self.assertIn(P.parede_do_modulo(conj), {self.parede, copia})

    def test_arraste_gruda_nas_pontas_no_piso_e_no_teto(self):
        retangulo = (-1.5, 1.5, 0.0, 2.7)
        # 1 cm from left endpoint and floor: snap within the 2 cm tolerance.
        s, base = P.posicao_no_arraste(retangulo, -1.5 + 0.3 + 0.01, 0.01,
                                       0.6, 0.7, 0.02)
        self.assertAlmostEqual(s, -1.2)
        self.assertAlmostEqual(base, 0.0)
        # Near right and ceiling.
        s, base = P.posicao_no_arraste(retangulo, 1.5 - 0.3 - 0.015, 2.0 - 0.01,
                                       0.6, 0.7, 0.02)
        self.assertAlmostEqual(s, 1.2)
        self.assertAlmostEqual(base, 2.0)
        # Far away: stay in place.
        self.assertEqual(P.posicao_no_arraste(retangulo, 0.0, 1.0, 0.6, 0.7, 0.02),
                         (0.0, 1.0))

    def test_guias_so_do_modulo_ativo_selecionado_e_associado(self):
        conj = self.modulo()
        for o in bpy.context.selected_objects:
            o.select_set(False)
        conj.select_set(True)
        bpy.context.view_layer.objects.active = conj
        P.atualizar_guias()
        self.assertIsNone(P._guias[0])               # Still unassociated.
        self.encostar(conj)
        P.atualizar_guias()
        self.assertEqual(P._guias[0]['modulo'], conj.name)
        conj.select_set(False)
        P.atualizar_guias()
        self.assertIsNone(P._guias[0])
        # Without guides, the number gizmo VIEW3D_GGT_guias_parede does not appear,
        # and the guide operator cabinet_guia_parede does not run.
        self.assertFalse(P.OBJECT_OT_guia_parede.poll(bpy.context))

    def test_raio_atravessa_o_modulo_encostado_e_acha_a_face_da_parede(self):
        self.parede[P.CHAVE_ALVENARIA]=True
        # User-reported regression v202: with the cabinet back already on the wall plane,
        # skipping the cabinet by advancing 0.1 mm crossed the wall face, so dragging
        # hit the wall's other side or nothing and rejected it as a wall.
        conj = self.modulo()
        self.encostar(conj, s=0.0, base=0.5)
        lateral = min(addon.modulos._chapas_do_conjunto(conj),
                      key=lambda c: c.matrix_world.translation.x)
        x = lateral.matrix_world.translation.x
        ignorar = {conj.name, *(o.name for o in conj.children_recursive)}
        # Through the side-panel thickness: exit exactly at the wall face.
        acerto = P.raio_ate_parede(bpy.context, Vector((x, -3.0, 0.7)),
                                   Vector((0.0, 1.0, 0.0)), ignorar)
        self.assertIsNotNone(acerto)
        parede, ponto, normal, face = acerto
        self.assertIs(parede, self.parede)
        self.assertAlmostEqual(ponto.y, 1.0, places=5)        # The front face.
        self.assertVetor(normal, (0, -1, 0))
        self.assertVetor(self.parede.matrix_world.to_3x3()
                         @ self.parede.data.polygons[face].normal, (0, -1, 0))

    def sala(self):
        """Create one object like the user's Geometry Nodes room. At y = 1, wall A has two connected quads (-1.5..-0.5 and -0.5..0), wall B follows after a gap (0.5..1.5), and perpendicular wall C joins A at its corner."""
        h = 2.7
        vs = [(-1.5, 1, 0), (-0.5, 1, 0), (-0.5, 1, h), (-1.5, 1, h),   # A1
              (0.0, 1, 0), (0.0, 1, h),                                # A2
              (0.5, 1, 0), (1.5, 1, 0), (1.5, 1, h), (0.5, 1, h),       # B
              (-1.5, -1, 0), (-1.5, -1, h)]                            # C
        faces = [(0, 1, 2, 3), (1, 4, 5, 2), (6, 7, 8, 9), (10, 0, 3, 11)]
        malha = bpy.data.meshes.new("Living Room")
        malha.from_pydata(vs, [], faces)
        malha.update()
        obj = bpy.data.objects.new("Living Room", malha)
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.update()
        return obj

    def test_associa_a_face_e_nao_ao_objeto(self):
        # User request: a wall is the face plus connected coplanar neighbors,
        # not the entire object or infinite plane.
        sala = self.sala()
        frente = Vector((0.0, -1.0, 0.0))
        regiao = P.regiao_da_parede(sala, Vector((-1.0, 1.0, 1.0)), frente, face=0)
        self.assertEqual(regiao['face'], 0)
        self.assertVetor(regiao['retangulo'], (-1.5, 0.0, 0.0, 2.7))   # A1 + A2
        self.assertEqual(len(regiao['contorno']), 6)    # Without the edge between A1 and A2.
        self.assertEqual(len(regiao['triangulos']), 2 * 2 * 3)
        b = P.regiao_da_parede(sala, Vector((1.0, 1.0, 1.0)), frente, face=2)
        self.assertVetor(b['retangulo'], (0.5, 1.5, 0.0, 2.7))         # Only B.
        # Cabinet on B: its left guide measures from B's endpoint, not A's.
        conj = self.modulo()
        largura, _altura = self.medidas(conj)
        costas = Vector((1.0, 1.0, 0.0))
        P.colocar_na_parede(conj, sala, costas, frente)
        P.associar(conj, sala, costas, frente, face=2)
        self.assertEqual(conj[P.CHAVE_PAREDE_FACE], 2)
        valores = P.calcular_guias(conj)['valores']
        self.assertAlmostEqual(valores['esquerda'], 500.0 - largura / 2, places=2)
        self.assertAlmostEqual(valores['direita'], 500.0 - largura / 2, places=2)
        # Rebuilt mesh with mismatched index: use the nearest face in the plane.
        conj[P.CHAVE_PAREDE_FACE] = 999
        P._retangulos.clear()
        self.assertAlmostEqual(P.calcular_guias(conj)['valores']['esquerda'],
                               500.0 - largura / 2, places=2)
        P.desassociar(conj)
        self.assertNotIn(P.CHAVE_PAREDE_FACE, conj)

    def modulo_com_porta_em_x(self):
        """Create a cabinet with its door on face +X, representing an internally rotated preset."""
        conj = self.modulo()
        grupo = addon.portas.porta_no_modulo(conj)
        bpy.context.view_layer.update()
        self.assertEqual(P.frente_do_modulo(conj), 'NEG_Y')
        # Rotate the door 90 degrees around the Empty, from -Y to +X.
        giro = (conj.matrix_world @ Matrix.Rotation(math.radians(90), 4, 'Z')
                @ conj.matrix_world.inverted())
        grupo.matrix_world = giro @ grupo.matrix_world
        bpy.context.view_layer.update()
        return conj

    def test_costas_sao_o_lado_oposto_a_porta(self):
        # User report: a preset with its door on X placed its side against the wall.
        # The back is always opposite the door.
        conj = self.modulo_com_porta_em_x()
        self.assertEqual(P.frente_do_modulo(conj), 'POS_X')
        self.assertEqual(P.lado_das_costas(conj), 'NEG_X')
        lo, hi = P.caixa_local_do_modulo(conj)
        self.encostar(conj, s=0.2, base=0.5)
        self.assertEqual(conj[P.CHAVE_COSTAS], 'NEG_X')      # Stored upon association.
        # The door (cabinet +X) faces away from the wall (world -Y).
        self.assertVetor(conj.matrix_world.to_3x3() @ Vector((1, 0, 0)), (0, -1, 0))
        pontos = [conj.matrix_world @ Vector((x, y, z)) for x in (lo.x, hi.x)
                  for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
        self.assertAlmostEqual(max(p.y for p in pontos), 1.0, places=5)   # Back on the plane.
        self.assertAlmostEqual((min(p.x for p in pontos) + max(p.x for p in pontos)) / 2,
                               0.2, places=5)
        self.assertAlmostEqual(min(p.z for p in pontos), 0.5, places=5)
        # Cabinet depth determines its span along the wall.
        largura, _altura = self.medidas(conj)
        self.assertAlmostEqual(largura, (hi.y - lo.y) * 1000, places=3)
        guias = P.calcular_guias(conj)['valores']
        self.assertAlmostEqual(guias['esquerda'], 1700.0 - largura / 2, places=2)
        # The timer must not undo rotation.
        self.assertFalse(P.manter_nas_paredes())

    def test_roda_do_mouse_troca_a_face_contra_a_parede(self):
        conj = self.modulo()
        self.encostar(conj)
        self.assertEqual(conj[P.CHAVE_COSTAS], 'POS_Y')
        dentro = {'POS_X': (1, 0, 0), 'NEG_Y': (0, -1, 0), 'NEG_X': (-1, 0, 0),
                  'POS_Y': (0, 1, 0)}
        vistos = []
        for _ in range(4):
            vistos.append(P.girar_costas(conj, P.passos_da_roda(
                SimpleNamespace(type='WHEELUPMOUSE'))))
            P.colocar_na_parede(conj, self.parede, Vector((0.0, 1.0, 0.5)), Vector((0, -1, 0)))
            bpy.context.view_layer.update()
            # The chosen side points into the wall, world +Y.
            self.assertVetor(conj.matrix_world.to_3x3() @ Vector(dentro[vistos[-1]]), (0, 1, 0))
            self.assertAlmostEqual(P.ponto_das_costas(conj).y, 1.0, places=5)
        self.assertEqual(vistos, ['POS_X', 'NEG_Y', 'NEG_X', 'POS_Y'])   # Returns in full.
        self.assertEqual(P.girar_costas(conj, P.passos_da_roda(
            SimpleNamespace(type='WHEELDOWNMOUSE'))), 'NEG_X')
        self.assertEqual(P.passos_da_roda(SimpleNamespace(type='MOUSEMOVE')), 0)
        P.desassociar(conj)
        self.assertNotIn(P.CHAVE_COSTAS, conj)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestParedes)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError("Wall tests failed")
