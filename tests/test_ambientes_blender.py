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
            self.assertNotIn('Editar ambientes',[v[4] for v in itens])
            del self.obj[P.CHAVE_ALVENARIA]
            itens=[];E.widgets(bpy.context,itens,12,900,largura)
            definir=next(v for v in itens if v[5]==('operador','object.cabinet_definir_alvenaria'))
            self.assertEqual(definir[2],largura)
            self.obj[P.CHAVE_ALVENARIA]=True

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
