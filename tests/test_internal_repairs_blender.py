"""Internal-component repairs using only disposable scenes and directories."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tools.migrations.repair_library_internals as correcao

addon=correcao._base.addon


class TestCorrecaoInternos(unittest.TestCase):
    def setUp(self):
        addon.chapas._ocupado[0]=True
        correcao._base.limpar()
        colecao=bpy.data.collections.new('Teste')
        bpy.context.scene.collection.children.link(colecao)
        bpy.context.view_layer.update()
        bpy.context.view_layer.active_layer_collection=bpy.context.view_layer.layer_collection.children[colecao.name]

    def objeto(self,nome,pontos,faces):
        mesh=bpy.data.meshes.new(nome)
        mesh.from_pydata(pontos,[],faces)
        obj=bpy.data.objects.new(nome,mesh)
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.update()
        return obj

    def cubo(self,nome,origem=(0,0,0),dimensoes=(10,10,10)):
        dados=correcao._auditoria.caixa(Matrix.Translation(origem),dimensoes)
        return self.objeto(nome,[v/1000 for v in dados['pontos']],dados['faces'])

    def geometria(self,obj):
        return correcao._auditoria.geometria([obj.matrix_world@v.co*1000 for v in obj.data.vertices],
                                            [list(f.vertices) for f in obj.data.polygons])

    def test_preparo_recusa_destino_na_biblioteca_antes_de_criar_pastas(self):
        with tempfile.TemporaryDirectory() as pasta:
            biblioteca=Path(pasta)/"library";biblioteca.mkdir()
            with self.assertRaises(ValueError):
                correcao.preparar(biblioteca,Path(pasta)/'fontes',biblioteca/'novos')
            self.assertFalse(list(biblioteca.iterdir()))

    def test_publicacao_recusa_manifesto_sem_validacao(self):
        with tempfile.TemporaryDirectory() as pasta:
            (Path(pasta)/'manifesto.json').write_text(json.dumps(dict(verificado=False)))
            with self.assertRaises(RuntimeError):correcao.publicar(pasta)

    def test_costuras_internas_de_caixas_unidas_nao_mudam_o_envelope(self):
        obj=self.cubo('Primeira')
        bm=bmesh.new();bm.from_mesh(obj.data)
        novos=bmesh.ops.create_cube(bm,size=.01)['verts']
        bmesh.ops.translate(bm,verts=novos,vec=Vector((.015,.005,.005)))
        bm.to_mesh(obj.data);bm.free()
        antes=correcao.limites(obj)
        malha=obj.data
        self.assertTrue(correcao.reparar_topologia(obj))
        self.assertEqual(obj.data,malha)
        self.assertTrue(self.geometria(obj)['fechada'])
        for a,b in zip(antes,correcao.limites(obj)):self.assertLess((a-b).length,.001)

    def test_repara_peles_ausentes_quando_as_paredes_externas_existem(self):
        dados=correcao._auditoria.caixa(Matrix.Identity(4),(10,10,1))
        faces=[f for f in dados['faces'] if len({dados['pontos'][i].z for i in f})>1]
        obj=self.objeto('Sem peles',[v/1000 for v in dados['pontos']],faces)
        self.assertFalse(self.geometria(obj)['fechada'])
        correcao.reparar_topologia(obj)
        self.assertTrue(self.geometria(obj)['fechada'])

    def test_recorte_atravessando_a_chapa_continua_vazio_apos_repor_paredes(self):
        anel=[(0,0),(10,0),(10,10),(0,10),(3,3),(7,3),(7,7),(3,7)]
        pontos=[(x/1000,y/1000,z/1000) for z in (0,1) for x,y in anel]
        faces=[]
        for z in (0,8):
            for i in range(4):
                j=(i+1)%4;faces.append([z+i,z+j,z+j+4,z+i+4])
        faces += [[i,(i+1)%4,(i+1)%4+8,i+8] for i in range(4)]
        obj=self.objeto('Com recorte',pontos,faces)
        correcao.reparar_topologia(obj)
        dados=self.geometria(obj)
        self.assertTrue(dados['fechada'])
        self.assertFalse(correcao._auditoria.dentro(Vector((5,5,.5)),dados))

    def test_lacunas_triangularizadas_com_quinha_comum_ficam_fechadas(self):
        dados=correcao._auditoria.caixa(Matrix.Identity(4),(10,10,1))
        pontos=[v/1000 for v in dados['pontos']]+[Vector((.005,.005,.001))]
        faces=[f for f in dados['faces'] if not all(dados['pontos'][i].z==1 for i in f)]
        faces.extend(([1,5,8],[7,3,8]))
        obj=self.objeto('Lacunas na pele',pontos,faces)
        correcao.reparar_topologia(obj)
        self.assertTrue(self.geometria(obj)['fechada'])

    def test_recorte_local_preserva_id_da_mesh_e_retira_so_a_interferencia(self):
        obj=self.cubo('Prateleira',dimensoes=(20,20,2))
        obstaculo=self.cubo('Obstaculo',(15,15,-1),(10,10,4))
        malha=obj.data;obj['chapa_uid']='identidade-conservada'
        correcao.recortar(obj,obstaculo)
        self.assertEqual(obj.data,malha)
        self.assertEqual(obj['chapa_uid'],'identidade-conservada')
        self.assertTrue(self.geometria(obj)['fechada'])
        self.assertIsNone(correcao._auditoria.ponto_de_colisao(self.geometria(obj),self.geometria(obstaculo)))

    def test_corrigir_vao_de_modulo_girado_preserva_chapas_na_edicao(self):
        conj=addon.modulos.criar_armario(bpy.context,'Teste',600,800,550)
        grupo=addon.prateleiras.criar_prateleiras(bpy.context,conj,(18,18,18,18,0),
                  dict(quantidade=2,profundidade_mm=500,recuo_mm=30))
        conj.rotation_euler=(.2,-.3,.7);bpy.context.view_layer.update()
        antes={o.name:o.matrix_world.copy() for o in addon.prateleiras.prateleiras_do_grupo(grupo)}
        correcao.acertar_vao_prateleiras(grupo)
        correcao.conferir_edicao_prateleiras(conj)
        for o in addon.prateleiras.prateleiras_do_grupo(grupo):
            self.assertLess(max(abs(o.matrix_world[i][j]-antes[o.name][i][j]) for i in range(4) for j in range(4)),.00001)

    def test_familias_com_larguras_e_profundidades_distintas_podem_compartilhar_vao(self):
        conj=addon.modulos.criar_armario(bpy.context,'Teste',600,800,550)
        for n,(baixo,esq,prof) in enumerate(((18,18,500),(400,30,400))):
            addon.prateleiras.criar_prateleiras(bpy.context,conj,(esq,esq,baixo,18,0),
                dict(quantidade=1,profundidade_mm=prof,espacamento='LIVRE',vaos_mm=[100]))
        self.assertEqual(len(correcao.reunir_prateleiras(conj)),1)
        grupo,=addon.prateleiras.grupos_do_modulo(conj)
        correcao.acertar_vao_prateleiras(grupo)
        correcao.conferir_edicao_prateleiras(conj)
        self.assertEqual(len(addon.prateleiras.prateleiras_do_grupo(grupo)),2)

    def test_gaveteiro_conserva_vao_quando_a_estrutura_retorna(self):
        conj=addon.modulos.criar_armario(bpy.context,'Teste',600,800,550)
        grupo=addon.gavetas.criar_gavetas(bpy.context,conj,(18,18,18,18,0),dict(quantidade=2))
        largura,altura,_m=addon.gavetas.vao(grupo)
        matriz=grupo.matrix_world.copy()
        lateral=min(addon.modulos._chapas_do_conjunto(conj),key=lambda o:correcao.limites(o)[0].x)
        correcao.reparentear(lateral,None)
        correcao.acertar_vao_gavetas(conj)
        l,a,_m=addon.gavetas.vao(grupo)
        self.assertAlmostEqual(l,largura,places=3)
        self.assertAlmostEqual(a,altura,places=3)
        self.assertEqual(grupo.matrix_world,matriz)


with tempfile.TemporaryDirectory(prefix='cabinet_correcao_teste_') as guarda:
    with patch.object(addon.opcoes,'_pasta_addon',return_value=guarda),patch.object(addon.biblioteca,'pasta_biblioteca',return_value=guarda):
        addon.register()
        try:
            resultado=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestCorrecaoInternos))
        finally:
            correcao._base.limpar();addon.chapas._ocupado[0]=False;addon.unregister()
if not resultado.wasSuccessful():raise RuntimeError("Internal-component repair failed")
