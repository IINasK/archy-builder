"""Reproducoes: planta monolitica, recorte por pontos e selecao nativa."""
import math
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector, Quaternion

sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon
E=addon.paredes_edicao
P=addon.paredes
S=addon.paredes_selecao


def malha(nome,poligonos):
    bm=bmesh.new();vertices={}
    for pontos in poligonos:
        face=[]
        for co in pontos:
            co=tuple(co)
            if co not in vertices:vertices[co]=bm.verts.new(co)
            face.append(vertices[co])
        bm.faces.new(face)
    bm.normal_update()
    dados=bpy.data.meshes.new(nome);bm.to_mesh(dados);bm.free()
    obj=bpy.data.objects.new(nome,dados);bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return obj


def quad(x0,x1,z0,z1,y=1):
    return [(x0,y,z0),(x1,y,z0),(x1,y,z1),(x0,y,z1)]


class TestSelecaoParedes(unittest.TestCase):
    def setUp(self):
        addon.eventos._fim_do_desfazer()
        E.encerrar()
        if bpy.context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
        S.esquecer();E._ultima_face[0]=None
        self.area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
        self.regiao=next(r for r in self.area.regions if r.type=='WINDOW')
        self.area.spaces.active.region_3d.view_rotation=Quaternion((1,0,0),math.pi/2)
        # Frente e fundo no MESMO objeto: o caso que bloqueava a camera.
        self.parede=malha('Planta monolitica',[quad(-2,2,0,3),list(reversed(quad(-2,2,0,3,-1))),
                       [(-2,-1,0),(-2,1,0),(-2,1,3),(-2,-1,3)]])
        self.extra=malha('Outra parede',[quad(5,6,0,3)])
        self.selecionar(self.parede)
        bpy.context.scene['parede_metodo_selecao']='AUTO'

    def tearDown(self):
        E.encerrar()
        if bpy.context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        if self.area.spaces.active.local_view is not None:
            with bpy.context.temp_override(area=self.area,region=self.regiao):
                bpy.ops.view3d.localview(frame_selected=False)

    def selecionar(self,obj):
        for o in bpy.context.selected_objects:o.select_set(False)
        obj.select_set(True);bpy.context.view_layer.objects.active=obj

    def automatica(self,obj=None):
        return S.automatica(bpy.context,obj or self.parede,Vector((0,1,1.5)),Vector((0,-1,0)),0)

    def vertices(self,predicado):
        self.selecionar(self.parede)
        bpy.ops.object.mode_set(mode='EDIT')
        bm=bmesh.from_edit_mesh(self.parede.data)
        for f in bm.faces:f.select_set(False)
        for e in bm.edges:e.select_set(False)
        for v in bm.verts:v.select_set(bool(predicado(v.co)))
        bm.select_flush_mode();bmesh.update_edit_mesh(self.parede.data,loop_triangles=False,destructive=False)

    def recorte(self,pontos=None):
        p,n,r=self.automatica()
        if pontos is not None:r=S.recortar(r,pontos,n)
        return p,n,r

    def iniciar(self,face=None):
        with bpy.context.temp_override(area=self.area,region=self.regiao):
            erro=E.iniciar(bpy.context,self.parede,face=face or self.recorte(),recortar=True)
        self.assertIsNone(erro)
        return bpy.data.objects[E._sessao[0]['exibicao']]

    def escolha(self,metodo='PONTOS'):
        bpy.context.scene['parede_metodo_selecao']=metodo
        with bpy.context.temp_override(area=self.area,region=self.regiao):
            self.assertIsNone(E.preparar_escolha(bpy.context,self.parede))
        p,n,r=self.automatica()
        E._escolha_area[0]['candidata']=dict(objeto=self.parede.name,ponto=tuple(p),normal=tuple(n),regiao=r)
        return E._escolha_area[0]

    def test_auto_identifica_apenas_regiao_conectada_e_orientada(self):
        p,n,r=self.automatica()
        self.assertEqual(r['faces'],frozenset({0}))
        self.assertGreater(n.dot(Vector((0,-1,0))),.99999)
        self.assertAlmostEqual(np.max(np.abs(r['triangulos'][:,1]-1)),0)

    def test_auto_reusa_cache_sem_reler_malha_no_hover(self):
        self.automatica()
        with patch.object(P,'_calcular_regiao',side_effect=AssertionError('Recalculou o mesmo hover')):
            self.automatica()

    def test_vertices_nativos_validos_conservam_malha(self):
        antes=[tuple(v.co) for v in self.parede.data.vertices]
        self.vertices(lambda v:abs(v.y-1)<1e-6)
        p,n,r=S.dos_vertices(bpy.context,self.parede)
        self.assertEqual(r['faces'],frozenset({0}))
        bpy.ops.object.mode_set(mode='OBJECT')
        self.assertEqual([tuple(v.co) for v in self.parede.data.vertices],antes)

    def test_vertices_com_orientacoes_distintas_sao_recusados(self):
        self.vertices(lambda v:True)
        with self.assertRaisesRegex(ValueError,'orientacao'):
            S.dos_vertices(bpy.context,self.parede)
        self.assertEqual(bpy.context.mode,'EDIT_MESH')

    def test_vertices_desconectados_sao_recusados(self):
        self.parede=malha('Desconectadas',[quad(-2,-1,0,3),quad(1,2,0,3)])
        self.vertices(lambda v:True)
        with self.assertRaisesRegex(ValueError,'conectados'):
            S.dos_vertices(bpy.context,self.parede)

    def test_tolerancia_pequena_de_plano_e_aceita(self):
        self.parede=malha('Quase plana',[quad(-2,0,0,3),[(0,1,0),(2,1.001,0),(2,1.001,3),(0,1,3)]])
        self.vertices(lambda v:True)
        self.assertIsNotNone(S.dos_vertices(bpy.context,self.parede))

    def test_desvio_maior_que_dois_mm_e_recusado(self):
        self.parede=malha('Fora do plano',[quad(-2,0,0,3),[(0,1,0),(2,1.01,0),(2,1.01,3),(0,1,3)]])
        self.vertices(lambda v:True)
        with self.assertRaisesRegex(ValueError,'plano'):
            S.dos_vertices(bpy.context,self.parede)

    def test_entrar_por_vertices_sai_do_edit_e_isola(self):
        self.vertices(lambda v:abs(v.y-1)<1e-6)
        with bpy.context.temp_override(area=self.area,region=self.regiao):
            self.assertEqual(bpy.ops.object.cabinet_editar_parede(),{'FINISHED'})
        self.assertEqual(bpy.context.mode,'OBJECT')
        self.assertTrue(E.ativa())
        self.assertFalse(self.parede.visible_get(viewport=self.area.spaces.active))

    def test_poligono_com_tres_pontas_e_aceito(self):
        p,n,r=self.recorte([(-1,1,.5),(1,1,.5),(0,1,2.5)])
        self.assertEqual(r['retangulo'],(-1,1,.5,2.5))

    def test_poligono_concavo_preserva_reentrancia(self):
        p,n,r=self.recorte([(-1,1,.5),(1,1,.5),(1,1,1),(0,1,1),(0,1,2.5),(-1,1,2.5)])
        faixas=E.faixas_da_face(r,Vector((1,0,0)),2,2.1)
        self.assertEqual(len(faixas),1)
        self.assertAlmostEqual(faixas[0][0],-1)
        self.assertAlmostEqual(faixas[0][1],0)

    def test_poligono_cruzado_ou_sem_tres_pontas_e_recusado(self):
        for pontos in ([(-1,1,0),(1,1,2),(-1,1,2),(1,1,0)],[(-1,1,0),(1,1,2)],[]):
            with self.assertRaises(ValueError):self.recorte(pontos)

    def test_poligono_externo_nao_inventa_superficie(self):
        with self.assertRaises(ValueError):self.recorte([(5,1,0),(6,1,0),(6,1,2)])

    def test_bordas_coincidentes_nao_duplicam_cotas(self):
        p,n,r=self.recorte([(-2,1,0),(2,1,0),(2,1,3),(-2,1,3)])
        self.assertEqual(E.faixas_da_face(r,Vector((1,0,0)),.5,2.5),[(-2,2)])

    def test_abertura_real_permanece_fora_da_area_util(self):
        xs=(-2,-.5,.5,2);zs=(0,1,2,3)
        self.parede=malha('Parede com janela',[quad(xs[i],xs[i+1],zs[j],zs[j+1]) for i in range(3) for j in range(3) if (i,j)!=(1,1)])
        self.selecionar(self.parede)
        p,n,r=S.automatica(bpy.context,self.parede,Vector((-1,1,.5)),Vector((0,-1,0)),0)
        r=S.recortar(r,[(-2,1,0),(2,1,0),(2,1,3),(-2,1,3)],n)
        self.assertEqual(E.faixas_da_face(r,Vector((1,0,0)),1.2,1.8),[(-2,-.5),(.5,2)])

    def test_planta_monolitica_nao_bloqueia_camera(self):
        malha_original=self.parede.data
        antes=[tuple(v.co) for v in malha_original.vertices]
        # Reproduz o bloqueio antigo: o mesmo objeto intercepta o raio
        # na parede da frente antes da parede desejada, que fica em y=1.
        atingiu,ponto,_normal,_face=self.parede.ray_cast(Vector((0,-3,1.5)),Vector((0,1,0)))
        self.assertTrue(atingiu)
        self.assertAlmostEqual(ponto.y,-1)
        exibicao=self.iniciar()
        self.assertTrue(exibicao.visible_get(viewport=self.area.spaces.active))
        self.assertFalse(self.parede.visible_get(viewport=self.area.spaces.active))
        self.assertFalse(self.extra.visible_get(viewport=self.area.spaces.active))
        self.assertEqual(self.parede.data,malha_original)
        self.assertEqual([tuple(v.co) for v in malha_original.vertices],antes)
        self.assertTrue(all(abs(v.co.y-1)<1e-6 for v in exibicao.data.vertices))

    def test_saida_restaura_ocultacao_local_view_e_remove_temporarios(self):
        self.extra.hide_set(True)
        nome=self.iniciar().name
        E.encerrar()
        self.assertTrue(self.parede.visible_get(viewport=self.area.spaces.active))
        self.assertTrue(self.extra.hide_get())
        self.assertIsNone(bpy.data.objects.get(nome))
        self.assertIsNone(self.area.spaces.active.local_view)

    def test_moveis_da_regiao_visiveis_e_face_oposta_oculta(self):
        a=addon.modulos.criar_armario(bpy.context,'Na parede',600,700,500,fundo=False)
        b=addon.modulos.criar_armario(bpy.context,'Na oposta',600,700,500,fundo=False)
        for g,co,n in ((a,(0,1,0),(0,-1,0)),(b,(0,-1,0),(0,1,0))):
            P.colocar_na_parede(g,self.parede,Vector(co),Vector(n))
            P.associar(g,self.parede,Vector(co),Vector(n),face=0 if g==a else 1)
        self.selecionar(self.parede)
        self.iniciar()
        self.assertTrue(all(o.visible_get(viewport=self.area.spaces.active) for o in a.children))
        self.assertFalse(b.visible_get(viewport=self.area.spaces.active))

    def test_pontos_backspace_cancelar_e_menu_lateral(self):
        e=self.escolha()
        for p in ((-1,1,.5),(1,1,.5),(1,1,2.5)):
            e['cursor']=p;self.assertEqual(E.acao_escolha(bpy.context,'PONTO'),'RUNNING_MODAL')
        self.assertEqual(len(e['pontos']),3)
        bpy.ops.object.cabinet_area_parede_voltar()
        self.assertEqual(e['acao'],'VOLTAR')
        E.acao_escolha(bpy.context,e.pop('acao'))
        self.assertEqual(len(e['pontos']),2)
        bpy.ops.object.cabinet_area_parede_cancelar()
        self.assertEqual(E.acao_escolha(bpy.context,e.pop('acao')),'CANCELLED')
        self.assertIsNone(E._escolha_area[0])
        self.assertFalse(E.ativa())

    def test_enter_confirma_area_e_menu_tambem(self):
        e=self.escolha()
        for p in ((-1,1,.5),(1,1,.5),(0,1,2.5)):
            e['cursor']=p;E.acao_escolha(bpy.context,'PONTO')
        bpy.ops.object.cabinet_area_parede_confirmar()
        self.assertEqual(E.acao_escolha(bpy.context,e.pop('acao')),'FINISHED')
        self.assertTrue(E.ativa())
        self.assertTrue(E._sessao[0]['recorte_explicito'])

    def test_auto_confirma_por_clique_sem_pontos(self):
        self.escolha('AUTO')
        self.assertEqual(E.acao_escolha(bpy.context,'PONTO'),'FINISHED')
        self.assertTrue(E.ativa())

    def test_mudar_metodo_limpa_pontos_e_conserva_duas_interfaces(self):
        e=self.escolha()
        e['cursor']=(-1,1,.5);E.acao_escolha(bpy.context,'PONTO')
        E.definir_metodo(bpy.context,'AUTO')
        self.assertEqual(e['pontos'],[])
        self.assertEqual(e['metodo'],'AUTO')
        for largura in (190,320,564):
            itens=[];E.widgets(bpy.context,itens,12,900,min(540,largura-24))
            self.assertFalse([v for v in itens if v[0]+v[2]>largura-12+.01])
            self.assertIn('Cancelar selecao',[v[4] for v in itens])

    def test_desfazer_adia_limpeza_de_objetos_e_timer_remove_orfaos(self):
        nome=self.iniciar().name
        addon.eventos._desfazendo[0]=True
        E.encerrar()
        self.assertIsNotNone(bpy.data.objects.get(nome))
        addon.eventos._fim_do_desfazer()
        S.esquecer();E.verificar()
        self.assertIsNone(bpy.data.objects.get(nome))

    def test_realce_reutiliza_desenho_do_atach(self):
        import inspect
        self.assertIn('_paredes._desenhar_face_alvo',inspect.getsource(E._desenhar_escolha))

    def test_raycast_no_recorte_ignora_parede_que_bloqueava_camera(self):
        self.iniciar()
        with bpy.context.temp_override(area=self.area,region=self.regiao):
            acerto=P.raio_ate_parede(bpy.context,Vector((0,-3,1.5)),Vector((0,1,0)),set())
        self.assertIsNotNone(acerto)
        self.assertEqual(acerto[0],self.parede)
        self.assertAlmostEqual(acerto[1].y,1)
        self.assertNotIn(S.MARCA_EXIBICAO,acerto[0])

    def test_local_view_anterior_e_conservado_no_recorte(self):
        self.extra.select_set(True)
        with bpy.context.temp_override(area=self.area,region=self.regiao):
            bpy.ops.view3d.localview(frame_selected=False)
        antes={o.name for o in bpy.context.scene.objects if E.esta_na_vista(o,self.area.spaces.active,bpy.context)}
        self.iniciar()
        E.encerrar()
        depois={o.name for o in bpy.context.scene.objects if E.esta_na_vista(o,self.area.spaces.active,bpy.context)}
        self.assertEqual(antes,depois)
        with bpy.context.temp_override(area=self.area,region=self.regiao):
            bpy.ops.view3d.localview(frame_selected=False)

    def test_modulo_fora_do_recorte_preserva_vinculo_mas_fica_oculto(self):
        modulo=addon.modulos.criar_armario(bpy.context,'Fora da area',600,700,500,fundo=False)
        P.colocar_na_parede(modulo,self.parede,Vector((1.5,1,0)),Vector((0,-1,0)))
        P.associar(modulo,self.parede,Vector((1.5,1,0)),Vector((0,-1,0)),face=0)
        self.selecionar(self.parede)
        self.iniciar(self.recorte([(-2,1,0),(0,1,0),(0,1,3),(-2,1,3)]))
        self.assertFalse(modulo.visible_get(viewport=self.area.spaces.active))
        P.manter_nas_paredes()
        self.assertEqual(P.parede_do_modulo(modulo),self.parede)

    def test_enter_backspace_esc_e_direito_no_operador_modal(self):
        for tipo in ('ESC','RIGHTMOUSE'):
            self.escolha()
            evento=SimpleNamespace(type=tipo,value='PRESS',mouse_x=self.regiao.x+20,mouse_y=self.regiao.y+20)
            saida=E.OBJECT_OT_editar_parede.modal(SimpleNamespace(),bpy.context,evento)
            self.assertEqual(saida,{'CANCELLED'})
            self.assertIsNone(E._escolha_area[0])
        e=self.escolha()
        e['pontos']=[(-1,1,0),(1,1,0)]
        evento=SimpleNamespace(type='BACK_SPACE',value='PRESS',mouse_x=0,mouse_y=0)
        self.assertEqual(E.OBJECT_OT_editar_parede.modal(SimpleNamespace(),bpy.context,evento),{'RUNNING_MODAL'})
        self.assertEqual(len(e['pontos']),1)

    def test_confirmacao_no_menu_funciona_com_mouse_fora_da_viewport(self):
        e=self.escolha('AUTO')
        bpy.ops.object.cabinet_area_parede_confirmar()
        evento=SimpleNamespace(type='TIMER',value='NOTHING',mouse_x=-100,mouse_y=-100)
        self.assertEqual(E.OBJECT_OT_editar_parede.modal(SimpleNamespace(),bpy.context,evento),{'FINISHED'})
        self.assertTrue(E.ativa())

    def test_undo_redo_nao_restaura_exibicao_temporaria_orfa(self):
        nomes=self.parede.name,self.extra.name
        bpy.ops.ed.undo_push(message='Antes do recorte')
        self.iniciar()
        bpy.ops.ed.undo_push(message='Recorte da parede')
        self.parede=self.extra=None
        bpy.ops.ed.undo();addon.eventos._fim_do_desfazer();E.verificar()
        self.assertFalse(E.ativa())
        self.assertFalse([o for o in bpy.data.objects if o.get(S.MARCA_EXIBICAO)])

        bpy.ops.ed.redo();addon.eventos._fim_do_desfazer();E.verificar()
        self.assertFalse([o for o in bpy.data.objects if o.get(S.MARCA_EXIBICAO)])
        self.parede,self.extra=(bpy.data.objects.get(n) for n in nomes)
        self.assertTrue(self.parede.visible_get(viewport=self.area.spaces.active))

    def test_face_horizontal_e_menos_de_tres_vertices_sao_recusados(self):
        self.parede=malha('Piso',[[(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)]])
        self.vertices(lambda v:True)
        with self.assertRaisesRegex(ValueError,'vertical'):
            S.dos_vertices(bpy.context,self.parede)
        bpy.ops.object.mode_set(mode='OBJECT')
        self.vertices(lambda v:v.x<0)
        with self.assertRaisesRegex(ValueError,'tres vertices'):
            S.dos_vertices(bpy.context,self.parede)

    def test_hover_automatico_usa_raio_nativo_e_muda_feedback_por_face(self):
        e=self.escolha('AUTO')
        with patch.object(E,'raio_da_escolha',return_value=(self.parede,Vector((0,-1,1.5)),Vector((0,1,0)),1)) as raio:
            E.atualizar_escolha(bpy.context,(self.regiao.width/2,self.regiao.height/2))
        self.assertEqual(raio.call_count,1)
        self.assertGreater(e['candidata']['normal'][1],.999)
        self.assertEqual(e['candidata']['regiao']['faces'],frozenset({1}))
        self.assertIn('triangulos',e['candidata']['regiao'])
        self.assertIn('contorno',e['candidata']['regiao'])

    # Regressao (era BUG, corrigido na 371): teto invisivel bloqueava a parede escolhida.
    def test_escolha_absoluta_ignora_teto_e_objetos_a_frente(self):
        teto = malha('Teto com backface invisivel', [quad(-3,3,0,4,-3)])
        self.parede = malha('Parede alvo unica', [quad(-2,2,0,3,1)])
        self.selecionar(self.parede)
        self.escolha('AUTO')
        origem, direcao = Vector((0,-5,1.5)), Vector((0,1,0))
        self.assertIs(bpy.context.scene.ray_cast(bpy.context.evaluated_depsgraph_get(),origem,direcao)[4].original,teto)
        with patch.object(E.view3d_utils,'region_2d_to_origin_3d',return_value=origem), \
             patch.object(E.view3d_utils,'region_2d_to_vector_3d',return_value=direcao):
            E.atualizar_escolha(bpy.context,(30,30))
        self.assertEqual(E._escolha_area[0]['candidata']['objeto'],self.parede.name)
        self.assertEqual(E._escolha_area[0]['cursor'],(0,1,1.5))
        with patch.object(E.view3d_utils,'region_2d_to_origin_3d',return_value=Vector((8,-5,1.5))), \
             patch.object(E.view3d_utils,'region_2d_to_vector_3d',return_value=direcao):
            E.atualizar_escolha(bpy.context,(30,30))
        self.assertIsNone(E._escolha_area[0]['candidata'])

    def test_pontos_usam_snap_nativo_so_de_vertices_do_objeto_e_restauram_estado(self):
        e=self.escolha('PONTOS');e['cursor']=(0,1,1)
        dados=bpy.data.curves.new('Curva que nao participa do snap','CURVE')
        curva=bpy.data.objects.new(dados.name,dados)
        bpy.context.scene.collection.objects.link(curva)
        bpy.context.view_layer.update()
        ts=bpy.context.scene.tool_settings
        for nome in ('use_snap','snap_elements','snap_target'):
            self.addCleanup(setattr,ts,nome,getattr(ts,nome))
        ts.use_snap=False;ts.snap_elements={'EDGE'};ts.snap_target='ACTIVE'
        antes=tuple(bpy.context.scene.cursor.location)
        bloqueios={o.name:o.hide_select for o in bpy.context.scene.objects}
        with bpy.context.temp_override(area=self.area,region=self.regiao):
            parametros=E.preparar_snap_area(bpy.context)
            self.assertTrue(parametros['snap'])
            self.assertEqual(parametros['snap_elements'],{'VERTEX'})
            self.assertTrue(parametros['use_snap_selectable'])
            self.assertTrue(parametros['release_confirm'])
            self.assertEqual(parametros['constraint_axis'],(True,True,False))
            self.assertFalse(self.parede.hide_select)
            self.assertTrue(self.extra.hide_select)
            self.assertTrue(curva.hide_select)
            props=bpy.ops.object.cabinet_marcar_ponto_parede.get_rna_type().properties
            self.assertIn('TRANSFORM_OT_translate',props)
            self.assertIn('OBJECT_OT_cabinet_confirmar_ponto_parede',props)
            self.assertEqual(E.OBJECT_OT_marcar_ponto_parede.bl_idname,'object.cabinet_marcar_ponto_parede')
            bpy.context.scene.cursor.location=(-2,1,0)
            self.assertEqual(E.OBJECT_OT_confirmar_ponto_parede.execute(SimpleNamespace(),bpy.context),{'FINISHED'})
        self.assertEqual(e['pontos'],[(-2,1,0)])
        self.assertEqual(tuple(bpy.context.scene.cursor.location),antes)
        self.assertEqual({o.name:o.hide_select for o in bpy.context.scene.objects},bloqueios)
        self.assertIsNone(E._snap_area[0])
        self.assertEqual((ts.use_snap,set(ts.snap_elements),ts.snap_target),(False,{'EDGE'},'ACTIVE'))

    def test_teto_na_mesma_malha_e_backface_oculta_nao_bloqueiam_face_vertical(self):
        teto=[(-3,-3,3),(3,-3,3),(3,3,3),(-3,3,3)]
        self.parede=malha('Planta com teto',[teto,quad(-2,2,0,3,1),list(reversed(quad(-2,2,0,3,-1)))])
        self.selecionar(self.parede)
        self.escolha('AUTO')
        material=bpy.data.materials.new('Backface invisivel')
        material.use_backface_culling=True
        self.parede.data.materials.append(material)
        with bpy.context.temp_override(area=self.area,region=self.regiao), \
             patch.object(E.view3d_utils,'region_2d_to_origin_3d',return_value=Vector((0,-3,4))), \
             patch.object(E.view3d_utils,'region_2d_to_vector_3d',return_value=Vector((0,1,-.5)).normalized()):
            acerto=E.raio_da_escolha(bpy.context,self.regiao,self.area.spaces.active.region_3d,(30,30))
        self.assertIsNotNone(acerto)
        self.assertAlmostEqual(acerto[1].y,1,places=5)
        self.assertEqual(acerto[3],1)

    def test_cancelar_pontos_restaura_cursor_bloqueios_e_snap_anterior(self):
        e=self.escolha();e['cursor']=(0,1,1)
        cursor=tuple(bpy.context.scene.cursor.location)
        self.extra.hide_select=True
        with bpy.context.temp_override(area=self.area,region=self.regiao):
            E.preparar_snap_area(bpy.context)
            bpy.context.scene.cursor.location=(-2,1,0)
            E.encerrar_escolha()
        self.assertEqual(tuple(bpy.context.scene.cursor.location),cursor)
        self.assertTrue(self.extra.hide_select)
        self.assertFalse(self.parede.hide_select)
        self.assertIsNone(E._snap_area[0])

    def test_cancelamento_nativo_e_erro_na_confirmacao_nao_deixam_cursor_ou_bloqueios(self):
        e=self.escolha();e['cursor']=(0,1,1)
        cursor=tuple(bpy.context.scene.cursor.location)
        with bpy.context.temp_override(area=self.area,region=self.regiao):
            E.preparar_snap_area(bpy.context)
            with patch.object(E,'acao_escolha',side_effect=ValueError('Falha de teste')):
                with self.assertRaises(ValueError):
                    E.OBJECT_OT_confirmar_ponto_parede.execute(SimpleNamespace(),bpy.context)
            self.assertIsNone(E._snap_area[0])
            self.assertFalse(self.extra.hide_select)
            self.assertEqual(tuple(bpy.context.scene.cursor.location),cursor)
            E.preparar_snap_area(bpy.context)
            # Sem macro nativa viva, o timer deve interpretar Esc/cancelamento.
            E.acompanhar_snap_area(bpy.context)
            self.assertEqual(e['acao'],'CANCELAR')
            evento=SimpleNamespace(type='TIMER',value='NOTHING')
            self.assertEqual(E.OBJECT_OT_editar_parede.modal(SimpleNamespace(),bpy.context,evento),{'CANCELLED'})
        self.assertIsNone(E._escolha_area[0])
        self.assertIsNone(E._snap_area[0])
        self.assertFalse(self.extra.hide_select)
        self.assertEqual(tuple(bpy.context.scene.cursor.location),cursor)

    def modulo_da_face(self):
        modulo=addon.modulos.criar_armario(bpy.context,'Modulo do recorte',1000,2000,550,fundo=False)
        P.colocar_na_parede(modulo,self.parede,Vector((0,1,0)),Vector((0,-1,0)))
        P.associar(modulo,self.parede,Vector((0,1,0)),Vector((0,-1,0)),face=0)
        bpy.context.view_layer.update()
        self.selecionar(self.parede)
        return modulo

    def test_visibilidade_mede_area_e_limite_de_noventa_porcento(self):
        modulo=self.modulo_da_face()
        for fim,esperado in ((0,.5),(.4,.9),(.399,.899),(.5,1.0)):
            with self.subTest(fim=fim):
                p,n,r=self.recorte([(-2,1,0),(fim,1,0),(fim,1,3),(-2,1,3)])
                self.assertAlmostEqual(S.fracao_visivel(modulo,r,n),esperado,places=5)
        p,n,r=self.recorte([(-.5,1,0),(.5,1,0),(-.5,1,2)])
        self.assertAlmostEqual(S.fracao_visivel(modulo,r,n),.5,places=5)

    def test_modulo_cortado_fica_cinza_bloqueado_e_malha_original_intacta(self):
        modulo=self.modulo_da_face()
        antes={o.name:(o.data.as_pointer(),[tuple(v.co) for v in o.data.vertices])
               for o in modulo.children_recursive if o.type=='MESH'}
        self.iniciar(self.recorte([(-2,1,0),(0,1,0),(0,1,3),(-2,1,3)]))
        self.assertIn(modulo.name,E._sessao[0]['restritos'])
        self.assertTrue(modulo.hide_select)
        self.assertFalse(modulo.visible_get(viewport=self.area.spaces.active))
        proxy=next(o for o in bpy.context.scene.objects if o.get(S.MARCA_MODULO_RECORTADO) and not o.hide_get())
        self.assertTrue(proxy.hide_select)
        self.assertTrue(proxy.visible_get(viewport=self.area.spaces.active))
        self.assertAlmostEqual(proxy.color[0],proxy.color[1])
        self.assertAlmostEqual(proxy.color[1],proxy.color[2])
        malha=proxy.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
        try:
            self.assertGreater(len(malha.vertices),0)
            self.assertLessEqual(max(v.co.x for v in malha.vertices),1e-5)
        finally:
            proxy.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
        self.assertTrue(addon.paredes_composicao.editar_modulo(bpy.context,modulo.name,'largura',900))
        E.encerrar()
        self.assertFalse(modulo.hide_select)
        self.assertFalse(any(o.get(S.MARCA_MODULO_RECORTADO) for o in bpy.data.objects))
        for nome,(ponteiro,vertices) in antes.items():
            self.assertEqual(bpy.data.objects[nome].data.as_pointer(),ponteiro)
            self.assertEqual([tuple(v.co) for v in bpy.data.objects[nome].data.vertices],vertices)

    def test_modulo_editavel_na_entrada_nao_perde_edicao_ao_sair_do_recorte(self):
        modulo=self.modulo_da_face()
        self.iniciar(self.recorte([(-2,1,0),(.4,1,0),(.4,1,3),(-2,1,3)]))
        self.assertIn(modulo.name,E._sessao[0]['editaveis'])
        modulo.location.x+=4
        bpy.context.view_layer.update()
        self.assertEqual(S.fracao_visivel(modulo,E._sessao[0]['regiao'],Vector((0,-1,0))),0)
        addon.paredes_composicao.atualizar(bpy.context)
        self.assertTrue(E.modulo_editavel(modulo))
        self.assertTrue(any(f['nome']==modulo.name for f in addon.paredes_composicao.itens_da_face(bpy.context)))
        with bpy.context.temp_override(area=self.area,region=self.regiao):
            peca=next(o for o in modulo.children_recursive if o.type=='MESH')
            self.assertIs(E.modulo_da_peca(bpy.context,peca),modulo)

    def test_recorte_inativo_em_parede_rotacionada_conserva_vertices_e_plano(self):
        self.parede.matrix_world=Matrix.Rotation(math.radians(37),4,'Z')
        bpy.context.view_layer.update()
        n=P._normal_no_mundo(self.parede,Vector((0,-1,0)))
        p=self.parede.matrix_world@Vector((0,1,1))
        p,n,r=S.automatica(bpy.context,self.parede,p,n,0)
        modulo=addon.modulos.criar_armario(bpy.context,'Modulo rotacionado',1000,2000,550,fundo=False)
        P.colocar_na_parede(modulo,self.parede,self.parede.matrix_world@Vector((0,1,0)),n)
        P.associar(modulo,self.parede,self.parede.matrix_world@Vector((0,1,0)),n,face=0)
        bpy.context.view_layer.update()
        pontos=[self.parede.matrix_world@Vector(co) for co in ((-2,1,0),(0,1,0),(0,1,3),(-2,1,3))]
        r=S.recortar(r,pontos,n)
        self.assertAlmostEqual(S.fracao_visivel(modulo,r,n),.5,places=5)
        self.assertIn(modulo,E.associados(self.parede,p,n,[modulo],r),
                      (tuple(p),tuple(n),P.plano_do_modulo(modulo,self.parede),r['retangulo'],
                       S.modulo_na_regiao(modulo,r,n),P.parede_do_modulo(modulo)==self.parede))
        self.selecionar(self.parede)
        self.iniciar((p,n,r))
        proxy=next(o for o in bpy.context.scene.objects if o.get(S.MARCA_MODULO_RECORTADO) and not o.hide_get())
        avaliado=proxy.evaluated_get(bpy.context.evaluated_depsgraph_get())
        malha=avaliado.to_mesh()
        try:
            self.assertTrue(malha.vertices)
            u=P.eixos_da_parede(n)[1]
            self.assertLessEqual(max(v.co.dot(u) for v in malha.vertices),1e-5)
        finally:
            avaliado.to_mesh_clear()

    def test_saida_e_undo_limpam_recortes_e_restauram_bloqueio_do_usuario(self):
        modulo=self.modulo_da_face()
        nome=modulo.name
        peca=next(o for o in modulo.children_recursive if o.type=='MESH')
        nome_peca=peca.name
        peca.hide_select=True
        bpy.ops.ed.undo_push(message='Antes do recorte com selecao bloqueada')
        self.iniciar(self.recorte([(-2,1,0),(0,1,0),(0,1,3),(-2,1,3)]))
        bpy.ops.ed.undo_push(message='Recorte temporario')
        E.encerrar()
        self.assertTrue(peca.hide_select)
        self.assertFalse(modulo.hide_select)
        modulo=peca=None
        bpy.ops.ed.undo()
        addon.eventos._fim_do_desfazer()
        E.verificar()
        self.assertFalse(bpy.data.objects[nome].hide_select)
        self.assertTrue(bpy.data.objects[nome_peca].hide_select)
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        E.verificar()
        self.assertFalse(any(S.MARCA_BLOQUEIO in o or o.get(S.MARCA_MODULO_RECORTADO) for o in bpy.data.objects))
        self.assertFalse(bpy.data.objects[nome].hide_select)
        self.assertTrue(bpy.data.objects[nome_peca].hide_select)

    def test_falha_no_recorte_remove_so_exibicoes_e_restabelece_selecao(self):
        modulo=self.modulo_da_face()
        nomes=set(bpy.data.objects.keys())
        p,n,r=self.recorte([(-2,1,0),(0,1,0),(0,1,3),(-2,1,3)])
        with patch.object(E,'_aplicar_isolamento',side_effect=ValueError('Falha de teste')):
            with bpy.context.temp_override(area=self.area,region=self.regiao):
                self.assertEqual(E.iniciar(bpy.context,self.parede,face=(p,n,r),recortar=True),'Falha de teste')
        self.assertEqual(set(bpy.data.objects.keys()),nomes)
        self.assertFalse(modulo.hide_select)
        self.assertFalse(any(S.MARCA_BLOQUEIO in o for o in bpy.data.objects))

    def test_alterar_fonte_ou_apagar_exibicao_encerra_sem_dados_pendentes(self):
        exibicao=self.iniciar()
        bpy.data.objects.remove(exibicao,do_unlink=True)
        E.verificar()
        self.assertFalse(E.ativa())
        self.iniciar()
        self.parede.location.x+=.3
        bpy.context.view_layer.update();E.verificar()
        self.assertFalse(E.ativa())
        self.assertFalse([o for o in bpy.data.objects if o.get(S.MARCA_EXIBICAO)])
        p,n,r=self.recorte()
        with patch.object(P,'_uid_da_parede',side_effect=ValueError('Fonte nao editavel')):
            with self.assertRaises(ValueError):S.criar_exibicao(bpy.context,self.parede,r)
        self.assertFalse([o for o in bpy.data.objects if o.get(S.MARCA_EXIBICAO)])

    def test_selecionar_moveis_nao_deixa_parede_oculta_selecionada(self):
        modulo=addon.modulos.criar_armario(bpy.context,'Movel real',600,700,500,fundo=False)
        P.colocar_na_parede(modulo,self.parede,Vector((0,1,0)),Vector((0,-1,0)))
        P.associar(modulo,self.parede,Vector((0,1,0)),Vector((0,-1,0)),face=0)
        self.selecionar(self.parede)
        self.iniciar()
        modulo.select_set(True);bpy.context.view_layer.objects.active=modulo
        E.verificar()
        self.assertFalse(self.parede.select_get())
        E.encerrar()
        self.assertTrue(modulo.select_get())

    def test_regiao_rotacionada_conserva_orientacao_e_recorte(self):
        self.parede.rotation_euler.z=.7
        bpy.context.view_layer.update()
        ponto=self.parede.matrix_world@Vector((0,1,1.5))
        normal=self.parede.matrix_world.to_3x3()@Vector((0,-1,0))
        p,n,r=S.automatica(bpy.context,self.parede,ponto,normal,0)
        pontos=[self.parede.matrix_world@Vector(co) for co in ((-1,1,.5),(1,1,.5),(1,1,2.5),(-1,1,2.5))]
        r=S.recortar(r,pontos,n)
        exibicao=self.iniciar((p,n,r))
        self.assertAlmostEqual(r['retangulo'][1]-r['retangulo'][0],2,places=5)
        self.assertTrue(all(abs((v.co-p).dot(n))<1e-5 for v in exibicao.data.vertices))


with tempfile.TemporaryDirectory(prefix='parede_selecao_') as pasta:
    addon.opcoes._pasta_addon=lambda:pasta
    addon.biblioteca.pasta_biblioteca=lambda:pasta
    addon.register()
    resultado=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestSelecaoParedes))
    addon.unregister()
    if not resultado.wasSuccessful():raise RuntimeError('Falha na selecao de paredes')
