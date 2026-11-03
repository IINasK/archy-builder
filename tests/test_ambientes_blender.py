"""Alvenaria, faces por ambiente, cores editoriais e filiacao nativa."""
import os,sys,math,tempfile,unittest
from contextlib import contextmanager
from unittest.mock import patch
from types import SimpleNamespace
import bpy,bmesh
from mathutils import Vector,Matrix
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon
A=addon.ambientes;P=addon.paredes


class TestAmbientes(unittest.TestCase):
    def test_realce_coplanar_corrige_so_profundidade_e_restaura_projecao(self):
        # Regressao 394: a cor disputava o mesmo depth da face nativa (listras).
        self.marcar([0]);self.selecionar([0]);A.atualizar()
        contexto=SimpleNamespace(mode='EDIT_MESH',edit_object=self.obj)
        for original in (Matrix.Identity(4),Matrix(((2,0,0,0),(0,2,0,0),(0,0,-1,-.2),(0,0,-1,0)))):
            class Pilha:
                p=original.copy()
                @contextmanager
                def push_pop_projection(self):
                    anterior=self.p.copy()
                    try: yield
                    finally:self.p=anterior
                def get_projection_matrix(self):return self.p.copy()
                def load_projection_matrix(self,p):self.p=p.copy()
            pilha=Pilha();durante=[]
            with patch.object(A,'bpy',SimpleNamespace(context=contexto)),patch.object(A,'gpu') as gpu, \
                 patch.object(A,'_rotulo'),patch.object(A,'batch_for_shader') as batch:
                gpu.matrix.push_pop_projection=pilha.push_pop_projection
                gpu.matrix.get_projection_matrix=pilha.get_projection_matrix
                gpu.matrix.load_projection_matrix=pilha.load_projection_matrix
                batch.return_value.draw.side_effect=lambda *_:durante.append(pilha.p.copy())
                A.desenhar()
            self.assertTrue(durante)
            for p in durante:
                self.assertEqual(p[0],original[0]);self.assertEqual(p[1],original[1]);self.assertEqual(p[3],original[3])
                self.assertGreater((original[2]-p[2]).length,0)
            self.assertEqual(pilha.p,original)
            with patch.object(A,'bpy',SimpleNamespace(context=contexto)),patch.object(A,'gpu') as gpu, \
                 patch.object(A,'batch_for_shader',side_effect=RuntimeError('Falha simulada')):
                gpu.matrix.push_pop_projection=pilha.push_pop_projection
                gpu.matrix.get_projection_matrix=pilha.get_projection_matrix
                gpu.matrix.load_projection_matrix=pilha.load_projection_matrix
                with self.assertRaises(RuntimeError):A.desenhar()
            self.assertEqual(pilha.p,original)

    def test_cubo_com_dois_ambientes_conserva_oito_vertices_seis_faces_e_sem_triangulo_duplicado(self):
        bpy.ops.object.select_all(action='DESELECT');bpy.ops.mesh.primitive_cube_add(size=2)
        self.obj=bpy.context.object;self.obj[P.CHAVE_ALVENARIA]=True
        dados=self.obj.data.as_pointer()
        self.marcar([0,1,2],'Copa');self.marcar([3,4,5],'Cozinha');A.atualizar()
        self.assertEqual((len(self.obj.data.vertices),len(self.obj.data.polygons)),(8,6))
        self.assertEqual(self.obj.data.as_pointer(),dados)
        triangulos=[]
        for _i,ps in A._cache[0][self.obj.name]['grupos']:
            for k in range(0,len(ps),3):triangulos.append(tuple(sorted(tuple(map(float,p)) for p in ps[k:k+3])))
        self.assertEqual(len(triangulos),12);self.assertEqual(len(set(triangulos)),12)

    def setUp(self):
        addon.eventos._fim_do_desfazer()
        addon.paredes_edicao.encerrar()
        if bpy.context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        for o in list(bpy.data.objects):bpy.data.objects.remove(o,do_unlink=True)
        for c in list(bpy.data.collections):bpy.data.collections.remove(c)
        bpy.context.view_layer.active_layer_collection=bpy.context.view_layer.layer_collection
        P.esquecer()
        m=bpy.data.meshes.new('Casa')
        ps=[(-2,1,0),(0,1,0),(2,1,0),(-2,1,2),(0,1,2),(2,1,2),
            (-2,-1,0),(2,-1,0),(-2,1,0),(2,1,0),
            (-2,-1,2),(2,-1,2),(2,1,2),(-2,1,2)]
        m.from_pydata(ps,[],[(0,1,4,3),(1,2,5,4),(6,7,9,8),(10,13,12,11)])
        self.obj=bpy.data.objects.new('Casa',m);bpy.context.scene.collection.objects.link(self.obj)
        self.obj[P.CHAVE_ALVENARIA]=True;self.obj.select_set(True)
        bpy.context.view_layer.objects.active=self.obj;bpy.context.view_layer.update()
        bpy.context.scene[A.CHAVE_NOME]='Cozinha'

    def tearDown(self):
        A.encerrar_selecao()
        if bpy.context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        addon.paredes_edicao.encerrar()

    def selecionar(self,indices):
        if bpy.context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT');self.obj.select_set(True)
        bpy.context.view_layer.objects.active=self.obj
        bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='DESELECT')
        bm=bmesh.from_edit_mesh(self.obj.data);bm.faces.ensure_lookup_table()
        for i in indices:bm.faces[i].select_set(True)
        bmesh.update_edit_mesh(self.obj.data,loop_triangles=False,destructive=False)

    def marcar(self,indices,nome='Cozinha'):
        self.selecionar(indices);A.definir(bpy.context,self.obj,nome)
        bpy.ops.object.mode_set(mode='OBJECT');bpy.context.view_layer.update()

    def modulo(self,ponto=(-1,1,.5),normal=(0,-1,0)):
        m=addon.modulos.criar_armario(bpy.context,'Modulo do ambiente',600,700,500)
        p,n=Vector(ponto),Vector(normal)
        P.associar(m,self.obj,p,n);P.colocar_na_parede(m,self.obj,p,n)
        bpy.context.view_layer.update();addon.paredes_edicao.registrar_posicionado(bpy.context,m)
        return m

    def test_classificacao_automatica_parede_piso_teto_e_inclinada(self):
        for n,tipo in (((0,-1,0),'PAREDE'),((1,0,0),'PAREDE'),((0,0,1),'PISO'),
                       ((0,0,-1),'TETO'),((0,.5,.9),'INCLINADA')):
            self.assertEqual(P.tipo_superficie(n),tipo)
        self.obj.rotation_euler.x=math.pi/2;bpy.context.view_layer.update()
        self.assertEqual(P.tipo_superficie(P._normal_no_mundo(self.obj,(0,0,1))),'PAREDE')

    def test_faces_nativas_recebem_ambiente_sem_alterar_geometria_ou_material(self):
        antes=([tuple(v.co) for v in self.obj.data.vertices],[tuple(f.vertices) for f in self.obj.data.polygons])
        dados=self.obj.data.as_pointer()
        self.selecionar([0,2,3]);self.assertTrue(A.OBJECT_OT_definir_ambiente.poll(bpy.context))
        self.assertEqual(bpy.ops.object.cabinet_definir_ambiente(),{'FINISHED'})
        bpy.ops.object.mode_set(mode='OBJECT')
        self.assertEqual(self.obj.data.as_pointer(),dados)
        self.assertEqual(([tuple(v.co) for v in self.obj.data.vertices],[tuple(f.vertices) for f in self.obj.data.polygons]),antes)
        self.assertEqual(len(self.obj.data.materials),0)
        vals=[v.value for v in self.obj.data.attributes[A.ATR_FACE].data]
        self.assertEqual(vals,[1,0,1,1])

    def test_ambientes_distintos_usam_ids_e_cores_distintas_sem_duplicar_preset(self):
        self.marcar([0,2,3]);self.marcar([1],'Quarto');self.marcar([0],'Cozinha')
        mapa=A._mapa(self.obj)
        self.assertEqual(len(mapa),2)
        self.assertNotEqual(mapa['1']['cor'],mapa['2']['cor'])
        self.assertEqual([v.value for v in self.obj.data.attributes[A.ATR_FACE].data],[1,2,1,1])

    def test_sem_faces_selecionadas_nao_cria_registro(self):
        self.selecionar([])
        with self.assertRaises(ValueError):A.definir(bpy.context,self.obj,'Cozinha')
        self.assertNotIn(A.CHAVE_MAPA,self.obj)

    def test_instancia_compartilhada_e_isolada_antes_de_marcar(self):
        copia=self.obj.copy();bpy.context.scene.collection.objects.link(copia)
        malha=copia.data;self.marcar([0])
        self.assertIsNot(self.obj.data,malha)
        self.assertIs(copia.data,malha)
        self.assertIsNone(copia.data.attributes.get(A.ATR_FACE))

    def test_modulos_da_parede_e_do_piso_entram_na_cozinha(self):
        self.marcar([0,2,3])
        for p,n in (((-1,1,.5),(0,-1,0)),((-1,0,0),(0,0,1))):
            m=self.modulo(p,n)
            self.assertEqual(addon.orcamento._nome_comodo(addon.orcamento._comodo_do_modulo(m)),'Cozinha')

    def test_g_entre_faces_atualiza_ambiente_sem_perder_associacao(self):
        self.marcar([0],'Cozinha');self.marcar([1],'Quarto')
        m=self.modulo();P.manter_nas_paredes()
        m.location.x+=2;bpy.context.view_layer.update();P.manter_nas_paredes()
        self.assertEqual(addon.orcamento._nome_comodo(addon.orcamento._comodo_do_modulo(m)),'Quarto')
        self.assertIs(P.parede_do_modulo(m),self.obj)

    def test_renomear_colecao_preserva_ambiente_por_uid(self):
        self.marcar([0]);a=self.modulo();col=addon.orcamento._comodo_do_modulo(a)
        col.name='Cozinha principal'
        b=self.modulo((-1.5,1,.3))
        self.assertIs(addon.orcamento._comodo_do_modulo(b),col)

    def test_lista_presets_tem_quadrado_e_nome_a_direita(self):
        self.selecionar([0]);itens=[]
        A.widgets(bpy.context,itens,self.obj,10,900,300)
        quadrados=[i for i in itens if i[5] and i[5][:2]==('escolha','ambiente_cor')]
        nomes=[i for i in itens if i[5] and i[5][:2]==('escolha','ambiente_nome')]
        self.assertEqual([i[4] for i in nomes],addon.orcamento._comodos_da_lista(bpy.context.scene))
        self.assertEqual(len(quadrados),len(nomes))
        for q,n in zip(quadrados,nomes):self.assertLess(q[0]+q[2],n[0])

    def test_editar_e_remover_lado_a_lado_definir_ocupa_linha_inteira(self):
        E=addon.paredes_edicao
        for largura in (166,296,540):
            itens=[];E.widgets(bpy.context,itens,12,900,largura)
            editar=next(v for v in itens if v[5]==('operador','object.cabinet_editar_parede'))
            remover=next(v for v in itens if v[5]==('operador','object.cabinet_definir_alvenaria'))
            self.assertEqual(editar[1],remover[1]);self.assertEqual(editar[2],remover[2])
            self.assertEqual(editar[0]+editar[2]+6,remover[0])
            self.assertAlmostEqual(remover[0]+remover[2],12+largura)
            self.assertIn('Editar ambientes',[v[4] for v in itens])
            del self.obj[P.CHAVE_ALVENARIA]
            itens=[];E.widgets(bpy.context,itens,12,900,largura)
            definir=next(v for v in itens if v[5]==('operador','object.cabinet_definir_alvenaria'))
            self.assertEqual(definir[2],largura)
            self.obj[P.CHAVE_ALVENARIA]=True

    def test_sair_e_definir_ambiente_lado_a_lado_laranja(self):
        # Regressao 395: sair/voltar e definir compartilham a linha laranja.
        self.selecionar([0])
        for retorno in (None,{'cena':bpy.context.scene.name}):
            with patch.object(A,'_retorno',[retorno]):
                for largura in (166,296,540):
                    itens=[];addon.paredes_edicao.widgets(bpy.context,itens,12,900,largura)
                    sair,definir=[v for v in itens if v[5] and v[5][0]=='operador'][:2]
                    self.assertEqual(sair[1],definir[1]);self.assertEqual(sair[2],definir[2])
                    self.assertEqual(sair[3],definir[3]);self.assertEqual(sair[0]+sair[2]+6,definir[0])
                    self.assertAlmostEqual(definir[0]+definir[2],12+largura)
                    self.assertEqual(definir[4],'Definir como Cozinha')
                    self.assertEqual(sair[5][1],'object.cabinet_editar_ambientes' if retorno else 'object.editmode_toggle')
                    for item in (sair,definir):self.assertIn(item[5][1],addon.gaveta.OPERADORES_DESTAQUE)

    def preparar_faces(self,parede_2d=False):
        area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
        regiao=next(r for r in area.regions if r.type=='WINDOW')
        with bpy.context.temp_override(area=area,region=regiao):
            token=A.preparar_selecao(bpy.context,self.obj,parede_2d)
        return area,regiao,token

    def faces_marcadas(self):
        return {f.index for f in bmesh.from_edit_mesh(self.obj.data).faces if f.select}

    def test_dois_caminhos_sem_seletor_de_metodo_nem_botoes_da_area(self):
        for largura in (166,296,540):
            itens=[];addon.paredes_edicao.widgets(bpy.context,itens,12,900,largura)
            nomes=[v[4] for v in itens]
            self.assertIn('Editar parede',nomes);self.assertIn('Editar ambientes',nomes)
            for nome in ('Automatico','Por pontos','Confirmar area','Remover ultimo ponto','Cancelar selecao'):
                self.assertNotIn(nome,nomes)

    def test_entrada_ambientes_executa_edit_mode_sem_alinhar_camera(self):
        area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
        anterior=area.spaces.active.region_3d.view_rotation.copy()
        self.assertEqual(bpy.ops.object.cabinet_editar_ambientes(),{'FINISHED'})
        self.assertEqual(bpy.context.mode,'EDIT_MESH');self.assertFalse(addon.paredes_edicao.ativa())
        self.assertEqual(anterior,area.spaces.active.region_3d.view_rotation)

    def test_previa_automatica_une_faces_e_ctrl_identifica_so_uma_sem_alterar_malha(self):
        self.preparar_faces();s=A._edicao_faces[0]
        inicio=Vector((-1,-2,1));direcao=Vector((0,1,0))
        auto=A.acerto_selecao(self.obj,inicio,direcao)
        manual=A.acerto_selecao(self.obj,inicio,direcao,True)
        ps=s['cache'][1][1][auto];pontos=s['cache'][0][1][manual]
        self.assertEqual((min(p[0] for p in ps),max(p[0] for p in ps)),(-2,2))
        self.assertEqual((min(p[0] for p in pontos),max(p[0] for p in pontos)),(-2,0))
        self.assertEqual(len(bmesh.from_edit_mesh(self.obj.data).faces),4)
        self.assertEqual(self.faces_marcadas(),set())
        with patch.object(A,'atualizar_selecao',side_effect=AssertionError('Reconstrucao no hover')):
            for _ in range(20):self.assertIsNotNone(A.acerto_selecao(self.obj,inicio,direcao))

    def test_clique_automatico_seleciona_regiao_ctrl_soma_e_retira_faces_nativas(self):
        area,regiao,_=self.preparar_faces();i=A.acerto_selecao(self.obj,Vector((-1,-2,1)),Vector((0,1,0)),True)
        with bpy.context.temp_override(area=area,region=regiao):
            A.selecionar_face(bpy.context,self.obj,i)
            self.assertEqual(self.faces_marcadas(),{0,1})
            A.selecionar_face(bpy.context,self.obj,i,True);self.assertEqual(self.faces_marcadas(),{1})
            A.selecionar_face(bpy.context,self.obj,i,True);self.assertEqual(self.faces_marcadas(),{0,1})

    def test_alvo_fixo_ignora_teto_e_objetos_externos_inclusive_faces_ocultas(self):
        bpy.ops.mesh.primitive_cube_add(size=20);oclusor=bpy.context.object
        oclusor.select_set(False);self.obj.select_set(True);bpy.context.view_layer.objects.active=self.obj
        self.preparar_faces()
        self.assertIsNotNone(A.acerto_selecao(self.obj,Vector((-1,-2,1)),Vector((0,1,0)),True))
        bm=bmesh.from_edit_mesh(self.obj.data);bm.faces.ensure_lookup_table();bm.faces[0].hide_set(True)
        A._edicao_faces[0]['sujo']=True;A.atualizar_selecao(self.obj)
        self.assertIsNone(A.acerto_selecao(self.obj,Vector((-1,-2,1)),Vector((0,1,0)),True))

    def test_hover_nao_troca_selecao_manual_e_navegacao_menu_passam(self):
        area,regiao,token=self.preparar_faces()
        evento=SimpleNamespace(type='MOUSEMOVE',value='NOTHING',mouse_x=regiao.x+regiao.width//2,
                               mouse_y=regiao.y+regiao.height//2,ctrl=False)
        with bpy.context.temp_override(area=area,region=regiao):
            A.selecionar_face(bpy.context,self.obj,0,True);antes=self.faces_marcadas()
            A.evento_selecao(bpy.context,evento,token)
            self.assertEqual(self.faces_marcadas(),antes)
            for tipo in ('MIDDLEMOUSE','WHEELUPMOUSE','NDOF_MOTION','TAB'):
                evento.type=tipo;self.assertEqual(A.evento_selecao(bpy.context,evento,token),{'PASS_THROUGH'})
            evento.type='LEFTMOUSE';evento.value='PRESS';evento.mouse_x=regiao.x-10
            self.assertEqual(A.evento_selecao(bpy.context,evento,token),{'PASS_THROUGH'})

    def test_tab_e_undo_limpam_cache_timer_handler_sem_trocar_malha(self):
        anterior=tuple(bpy.context.scene.tool_settings.mesh_select_mode)
        area,regiao,token=self.preparar_faces();dados=self.obj.data.as_pointer()
        bpy.ops.object.mode_set(mode='OBJECT')
        evento=SimpleNamespace(type='TIMER')
        self.assertEqual(A.evento_selecao(bpy.context,evento,token),{'CANCELLED'})
        self.assertIsNone(A._edicao_faces[0]);self.assertEqual(self.obj.data.as_pointer(),dados)
        self.assertEqual(tuple(bpy.context.scene.tool_settings.mesh_select_mode),anterior)
        self.preparar_faces();A.esquecer();self.assertIsNone(A._edicao_faces[0])

    def test_enter_no_caminho_2d_usa_faces_nativas_e_isolamento_existente(self):
        area,regiao,token=self.preparar_faces(True)
        evento=SimpleNamespace(type='RET',value='PRESS',mouse_x=regiao.x-10,mouse_y=regiao.y,ctrl=True)
        with bpy.context.temp_override(area=area,region=regiao):
            A.selecionar_face(bpy.context,self.obj,0)
            self.assertEqual(A.evento_selecao(bpy.context,evento,token),{'FINISHED'})
        self.assertTrue(addon.paredes_edicao.ativa());self.assertIsNone(A._edicao_faces[0])

    def test_invocar_as_duas_entradas_abre_edit_mode_sem_etapa_de_pontos(self):
        real=bpy.context;adicionados=[]
        class Gerenciador:
            def modal_handler_add(self,op):adicionados.append(op)
            def __getattr__(self,nome):return getattr(real.window_manager,nome)
        class Contexto:
            window_manager=Gerenciador()
            def __getattr__(self,nome):return getattr(real,nome)
        for classe in (addon.paredes_edicao.OBJECT_OT_editar_parede,A.OBJECT_OT_editar_ambientes):
            op=SimpleNamespace(objeto='',report=lambda *_:None)
            op.execute=lambda c:classe.execute(op,c)
            self.assertEqual(classe.invoke(op,Contexto(),None),{'RUNNING_MODAL'})
            self.assertEqual(bpy.context.mode,'EDIT_MESH')
            self.assertIsNone(addon.paredes_edicao._escolha_area[0])
            self.assertEqual(A._edicao_faces[0]['parede_2d'],classe!=A.OBJECT_OT_editar_ambientes)
            A.encerrar_selecao();bpy.ops.object.mode_set(mode='OBJECT')
        self.assertEqual(len(adicionados),2)

    def test_clique_automatico_2d_e_clique_ctrl_tem_destinos_distintos(self):
        for ctrl in (True,False):
            area,regiao,token=self.preparar_faces(True)
            ev=SimpleNamespace(type='LEFTMOUSE',value='PRESS',mouse_x=regiao.x+regiao.width//2,
                               mouse_y=regiao.y+regiao.height//2,ctrl=ctrl)
            with bpy.context.temp_override(area=area,region=regiao), \
                 patch.object(A.view3d_utils,'region_2d_to_origin_3d',return_value=Vector((-1,-2,1))), \
                 patch.object(A.view3d_utils,'region_2d_to_vector_3d',return_value=Vector((0,1,0))):
                self.assertEqual(A.evento_selecao(bpy.context,ev,token),{'RUNNING_MODAL'} if ctrl else {'FINISHED'})
            self.assertEqual(addon.paredes_edicao.ativa(),not ctrl)
            A.encerrar_selecao()
            if bpy.context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
            addon.paredes_edicao.encerrar()

    def test_cache_refaz_apos_tab_g_e_fica_limpo_ao_trocar_cena(self):
        self.preparar_faces();s=A._edicao_faces[0];cache=s['cache']
        bm=bmesh.from_edit_mesh(self.obj.data)
        for v in bm.verts:v.co.x+=3
        bmesh.update_edit_mesh(self.obj.data)
        A.invalidar(bpy.context.scene,SimpleNamespace(updates=[SimpleNamespace(id=self.obj.data,is_updated_geometry=True)]))
        self.assertTrue(s['sujo']);A.atualizar_selecao(self.obj);self.assertIsNot(s['cache'],cache)
        self.assertIsNotNone(A.acerto_selecao(self.obj,Vector((2,-2,1)),Vector((0,1,0))))
        origem=bpy.context.scene;outra=bpy.data.scenes.new('Outra cena de teste')
        try:
            bpy.context.window.scene=outra
            self.assertEqual(A.evento_selecao(bpy.context,SimpleNamespace(type='TIMER'),id(s)),{'CANCELLED'})
            self.assertIsNone(A._edicao_faces[0])
        finally:bpy.context.window.scene=origem;bpy.data.scenes.remove(outra)

    def test_undo_nativo_durante_selecao_descarta_todas_referencias_do_editor(self):
        bpy.context.preferences.edit.use_global_undo=True
        bpy.ops.ed.undo_push(message='Antes da selecao de ambientes')
        area,regiao,_=self.preparar_faces()
        with bpy.context.temp_override(area=area,region=regiao):
            A.selecionar_face(bpy.context,self.obj,0);A.definir(bpy.context,self.obj,'Cozinha')
            bpy.ops.ed.undo_push(message='Ambiente no editor');self.obj=None
            bpy.ops.ed.undo();addon.eventos._fim_do_desfazer()
        self.assertIsNone(A._edicao_faces[0]);self.obj=bpy.data.objects['Casa']

    def test_ctrl_nao_infere_uma_face_intermediaria_pelos_vertices_de_outras(self):
        self.preparar_faces()
        bm=bmesh.from_edit_mesh(self.obj.data);bm.faces.ensure_lookup_table()
        bm.faces[0].select_set(True);bm.faces[1].select_set(True)
        bm.faces[1].select=False
        # Vertices da face vizinha podem estar selecionados sem a face estar.
        for v in bm.faces[1].verts:v.select=True
        bmesh.update_edit_mesh(self.obj.data,loop_triangles=False,destructive=False)
        with self.assertRaisesRegex(ValueError,'vertices soltos'):
            addon.paredes_selecao.dos_vertices(bpy.context,self.obj,somente_faces=True)

    def test_previa_da_regiao_conectada_preserva_abertura_real_sem_perder_metade_da_area(self):
        # Regressao 396: faces conservadas pelo dissolve nao cortam a previa.
        self.obj.data.clear_geometry()
        vertices=[(x,0,z) for z in range(4) for x in range(4)]
        faces=[(z*4+x,z*4+x+1,(z+1)*4+x+1,(z+1)*4+x) for z in range(3) for x in range(3) if (x,z)!=(1,1)]
        self.obj.data.from_pydata(vertices,[],faces);self.preparar_faces()
        i=A.acerto_selecao(self.obj,Vector((.5,-2,.5)),Vector((0,1,0)))
        ps=A._edicao_faces[0]['cache'][1][1][i]
        area=sum((Vector(ps[k+1])-Vector(ps[k])).cross(Vector(ps[k+2])-Vector(ps[k])).length/2 for k in range(0,len(ps),3))
        self.assertAlmostEqual(area,8)
        self.assertIsNone(A.acerto_selecao(self.obj,Vector((1.5,-2,1.5)),Vector((0,1,0))))

    def test_editar_ambientes_e_submenu_da_parede_com_volta_ao_mesmo_recorte(self):
        E=addon.paredes_edicao
        area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
        regiao=next(r for r in area.regions if r.type=='WINDOW')
        p=Vector((-1,1,1));n=Vector((0,-1,0));r=P.regiao_da_parede(self.obj,p,n)
        with bpy.context.temp_override(area=area,region=regiao):
            self.assertIsNone(E.iniciar(bpy.context,self.obj,face=(p,n,r),recortar=True))
            limites=E._sessao[0]['regiao']['retangulo']
            itens=[];E.widgets(bpy.context,itens,12,900,296)
            self.assertIn(('operador','object.cabinet_editar_ambientes'),[v[5] for v in itens])
            self.assertTrue(A.OBJECT_OT_editar_ambientes.poll(bpy.context))
            self.assertEqual(bpy.ops.object.cabinet_editar_ambientes(),{'FINISHED'})
            self.assertEqual(bpy.context.mode,'EDIT_MESH');self.assertFalse(E.ativa())
            self.assertIs(bpy.context.edit_object,self.obj)
            itens=[];E.widgets(bpy.context,itens,12,900,296)
            self.assertIn('Voltar a edicao da parede',[v[4] for v in itens])
            self.assertIn('Definir como Cozinha',[v[4] for v in itens])
            self.assertEqual(bpy.ops.object.cabinet_editar_ambientes(),{'FINISHED'})
            self.assertTrue(E.ativa());self.assertEqual(bpy.context.mode,'OBJECT')
            self.assertEqual(E._sessao[0]['regiao']['retangulo'],limites)
            self.assertTrue(E._sessao[0]['recorte_explicito']);self.assertIsNone(A._retorno[0])

    def test_tab_nativo_na_edicao_de_ambientes_nao_perde_botao_de_retorno(self):
        E=addon.paredes_edicao
        area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
        regiao=next(r for r in area.regions if r.type=='WINDOW')
        p=Vector((-1,1,1));n=Vector((0,-1,0))
        with bpy.context.temp_override(area=area,region=regiao):
            self.assertIsNone(E.iniciar(bpy.context,self.obj,face=(p,n,P.regiao_da_parede(self.obj,p,n))))
            bpy.ops.object.cabinet_editar_ambientes()
            bpy.ops.object.mode_set(mode='OBJECT')
            itens=[];E.widgets(bpy.context,itens,12,900,296)
            editar=next(v for v in itens if v[4]=='Editar parede')
            self.assertEqual(editar[5],('operador','object.cabinet_editar_ambientes'))
            self.assertEqual(bpy.ops.object.cabinet_editar_ambientes(),{'FINISHED'})
            self.assertTrue(E.ativa())

    def test_falha_ao_entrar_em_edit_mode_restaura_a_parede(self):
        E=addon.paredes_edicao
        area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
        regiao=next(r for r in area.regions if r.type=='WINDOW')
        p=Vector((-1,1,1));n=Vector((0,-1,0))
        with bpy.context.temp_override(area=area,region=regiao):
            self.assertIsNone(E.iniciar(bpy.context,self.obj,face=(p,n,P.regiao_da_parede(self.obj,p,n))))
            op=SimpleNamespace(report=lambda *_:None)
            def modo_indisponivel(**_):raise RuntimeError('Modo indisponivel')
            class BpyProxy:
                ops=SimpleNamespace(object=SimpleNamespace(mode_set=modo_indisponivel))
                def __getattr__(self,nome):return getattr(bpy,nome)
            with patch.object(A,'bpy',BpyProxy()):
                self.assertEqual(A.OBJECT_OT_editar_ambientes.execute(op,bpy.context),{'CANCELLED'})
            self.assertTrue(E.ativa());self.assertIsNone(A._retorno[0])

    def test_cor_do_quadrado_altera_so_o_ambiente_escolhido(self):
        self.marcar([0]);self.marcar([1],'Quarto');antes=A._mapa(self.obj)['2']['cor']
        outra=self.obj.copy();outra.data=self.obj.data.copy();bpy.context.scene.collection.objects.link(outra)
        self.assertEqual(A.OBJECT_OT_cor_ambiente.bl_idname,'object.cabinet_cor_ambiente')
        self.assertEqual(bpy.ops.object.cabinet_cor_ambiente(objeto=self.obj.name,nome='Cozinha',cor=(1,0,0)),{'FINISHED'})
        self.assertEqual(A._mapa(self.obj)['1']['cor'],[1,0,0])
        self.assertEqual(A._mapa(self.obj)['2']['cor'],antes)
        self.assertEqual(A._mapa(outra)['1']['cor'],[1,0,0])

    def test_paleta_so_abre_ao_soltar_clique_do_quadrado(self):
        self.selecionar([0]);acao=('escolha','ambiente_cor','Cozinha',False,True,A.ALVO,(1,0,0))
        ctx=SimpleNamespace(screen={},scene=bpy.context.scene,
            area=SimpleNamespace(tag_redraw=lambda:None),
            window_manager=SimpleNamespace(modal_handler_add=lambda _:None))
        e=SimpleNamespace(type='LEFTMOUSE',value='PRESS',mouse_region_x=12,mouse_region_y=12)
        op=SimpleNamespace();classe=addon.gaveta_eventos.OBJECT_OT_interagir_gaveta
        with patch.object(addon.gaveta,'_widgets_interativos',return_value=[(0,0,24,24,'',acao)]), \
             patch.object(addon.gaveta,'_fechar_suspenso'), \
             patch.object(addon.editor,'executar') as executar:
            self.assertEqual(classe.invoke(op,ctx,e),{'RUNNING_MODAL'})
            executar.assert_not_called()
            e.value='RELEASE'
            self.assertEqual(classe.modal(op,ctx,e),{'FINISHED'})
            executar.assert_called_once_with(ctx,'object.cabinet_cor_ambiente',nome='Cozinha')

    def test_rotulo_so_cabe_se_retangulo_inteiro_couber_inclusive_concavidade(self):
        quad=[(-1,-1),(1,-1),(1,1),(-1,-1),(1,1),(-1,1)]
        self.assertTrue(A.rotulo_cabe(quad,1,.5))
        self.assertFalse(A.rotulo_cabe(quad,3,.5))
        # Dois bracos separados: os cantos do texto podem caber, mas o meio nao.
        lados=[(-1,-1),(-.5,-1),(-.5,1),(-1,-1),(-.5,1),(-1,1),
               (.5,-1),(1,-1),(1,1),(.5,-1),(1,1),(.5,1)]
        self.assertFalse(A.rotulo_cabe(lados,1.8,1))

    def test_cache_dissolve_so_copia_e_nao_rele_no_redesenho(self):
        self.marcar([0,1]);self.selecionar([0]);A.atualizar()
        self.assertEqual(len(bmesh.from_edit_mesh(self.obj.data).faces),4)
        with patch.object(A.bmesh,'from_edit_mesh',side_effect=AssertionError('Releu malha')):
            for _ in range(20):A.atualizar()
        self.assertTrue(A._cache[0][self.obj.name]['grupos'])

    def test_cores_e_nomes_nao_sao_desenhados_fora_da_definicao(self):
        self.marcar([0])
        with patch.object(A,'gpu') as gpu:A.desenhar()
        gpu.shader.from_builtin.assert_not_called()

    def test_invalidacao_ignora_transformacao_e_geometria_de_outros_objetos(self):
        self.marcar([0]);A.atualizar()
        outro=bpy.data.meshes.new('Mesh externa')
        for dado,geometria in ((self.obj,False),(outro,True)):
            A.invalidar(bpy.context.scene,SimpleNamespace(updates=[SimpleNamespace(id=dado,is_updated_geometry=geometria)]))
            self.assertFalse(A._sujo[0])
        A.invalidar(bpy.context.scene,SimpleNamespace(updates=[SimpleNamespace(id=self.obj.data,is_updated_geometry=True)]))
        self.assertTrue(A._sujo[0])

    def test_undo_redo_nativo_restaura_faces_metadata_e_cache(self):
        bpy.context.preferences.edit.use_global_undo=True
        bpy.ops.ed.undo_push(message='Antes de definir ambiente')
        self.marcar([0,2]);bpy.ops.ed.undo_push(message='Ambiente definido');self.obj=None
        bpy.ops.ed.undo();addon.eventos._fim_do_desfazer()
        self.obj=bpy.data.objects['Casa'];self.assertNotIn(A.CHAVE_MAPA,self.obj)
        self.assertFalse(A._cache[0])
        bpy.ops.ed.redo();addon.eventos._fim_do_desfazer()
        self.obj=bpy.data.objects['Casa'];A.atualizar()
        self.assertEqual(A._mapa(self.obj)['1']['nome'],'Cozinha')
        self.assertIn('Casa',A._cache[0])

    def test_metadata_e_uid_sobrevivem_salvar_reabrir(self):
        self.marcar([0,2,3]);antes=A._mapa(self.obj);self.obj=None
        with tempfile.TemporaryDirectory(prefix='ambientes_') as pasta:
            caminho=os.path.join(pasta,'casa.blend')
            bpy.ops.wm.save_as_mainfile(filepath=caminho);bpy.ops.wm.open_mainfile(filepath=caminho)
            self.obj=bpy.data.objects['Casa']
            self.assertEqual(A._mapa(self.obj),antes)
            self.assertTrue(P.alvenaria_definida(self.obj))
            m=self.modulo()
            self.assertEqual(addon.orcamento._nome_comodo(addon.orcamento._comodo_do_modulo(m)),'Cozinha')


with tempfile.TemporaryDirectory(prefix='ambientes_addon_') as pasta, \
     patch.object(addon.opcoes,'_pasta_addon',return_value=pasta), \
     patch.object(addon.biblioteca,'pasta_biblioteca',return_value=pasta):
    addon.register()
    try:resultado=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestAmbientes))
    finally:addon.unregister()
    if not resultado.wasSuccessful():raise RuntimeError('Falha nos ambientes da Alvenaria')
