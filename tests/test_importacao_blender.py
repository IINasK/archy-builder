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


def _faces_da_caixa(lo, hi):
    """12 triangulos de uma caixa (como o Promob exporta), em mm."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    quads = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2),
             (2, 6, 7, 3), (3, 7, 4, 0)]
    return [[v[a], v[b], v[c]] for q in quads for a, b, c in ((q[0], q[1], q[2]),
                                                             (q[0], q[2], q[3]))]


def dxf_promob(caminho, caixas, polyfaces=(), cores=None):
    """DXF no formato do Promob: uma CAMADA por peca; 3DFACE para as
    caixas e POLYLINE polyface (70 = 64) para as recortadas. `cores` =
    {camada: cor} vai na tabela de camadas (7 chapa, 253 ferragem, 254
    aluminio), como o Promob grava."""
    out = []
    if cores:
        out += ['0', 'SECTION', '2', 'TABLES', '0', 'TABLE', '2', 'LAYER', '70', str(len(cores))]
        for camada, cor in cores.items():
            out += ['0', 'LAYER', '2', camada, '70', '0', '62', str(cor), '6', 'CONTINUOUS']
        out += ['0', 'ENDTAB', '0', 'ENDSEC']
    out += ['0', 'SECTION', '2', 'ENTITIES']
    for camada, faces in caixas:
        for face in faces:
            pts = list(face) + [face[-1]] * (4 - len(face))
            out += ['0', '3DFACE', '8', camada]
            for n, p in enumerate(pts):
                out += ['1%d' % n, str(p[0]), '2%d' % n, str(p[1]), '3%d' % n, str(p[2])]
    for camada, vertices, faces in polyfaces:
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
    with open(caminho, 'w', encoding='latin1') as f:
        f.write('\n'.join(out) + '\n')


def base_em_l(lado=600.0, recorte=300.0, e=15.0, z=0.0):
    """Prisma em L (a base de um canto do Promob): 12 vertices."""
    contorno = [(0, 0), (lado, 0), (lado, recorte), (recorte, recorte),
                (recorte, lado), (0, lado)]
    vs = [(x, y, z) for x, y in contorno] + [(x, y, z + e) for x, y in contorno]
    n = len(contorno)
    faces = [(0, 3, 2, 1), (0, 5, 4, 3), (6, 7, 8, 9), (6, 9, 10, 11)]
    faces += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    return vs, faces


class TestImportacao(unittest.TestCase):
    def test_transporte_curvo_preserva_residuos_e_identidade_do_perfil(self):
        conj=self._bancada_curva_real()
        g=max(addon.portas._portas_do_conjunto(conj),key=lambda g:addon.portas._folhas_portas(g)[0].chapa_comprimento_mm)
        f,=addon.portas._folhas_portas(g)
        perfil,ref=addon.promob._perfil_curvo_positivo(f)
        m=addon.ferragens._matriz_fechada(f)
        frente=[p.xy for p in perfil[0]];tras=[(m@Vector(p)).xy for p in ref['tras']]
        pontos=[m@v.co for v in f.data.vertices]
        centro=perfil[0][len(perfil[0])//2]
        n=(m.to_3x3()@Vector(ref['normais_frente'][len(ref['normais_frente'])//2])).normalized()
        pontos += [centro+n*.0015,centro-n*.0015]
        antes=(len(bpy.data.objects),len(bpy.data.meshes))
        delta=Vector((.017,-.023));rot=Matrix.Rotation(.3,2)
        for transformar in (lambda p:p+delta,lambda p:rot@p):
            novos=addon.promob._transportar_madeira_curva(f,pontos,[transformar(p) for p in frente],[transformar(p) for p in tras])
            self.assertIsNotNone(novos)
            for p,q in zip(pontos,novos):
                self.assertLess((q-Vector((*transformar(p.xy),p.z))).length,.000002)
        self.assertEqual(antes,(len(bpy.data.objects),len(bpy.data.meshes)))

    def test_limite_de_abertura_recalcula_uma_vez_apos_mudar_geometria(self):
        from unittest.mock import patch
        conj=self._bancada_curva_real()
        g=max(addon.portas._portas_do_conjunto(conj),key=lambda g:addon.portas._folhas_portas(g)[0].chapa_comprimento_mm)
        self.assertTrue(addon.promob.alinhar_frente_ao_corpo(g))
        f,=addon.portas._folhas_portas(g)
        pontos=[addon.ferragens._matriz_fechada(f)@v.co for v in f.data.vertices]
        addon.portas.adotar_contorno_modelado(bpy.context,g,pontos)
        self.assertTrue(g.get('porta_limite_pendente'))
        assinatura=addon.formas._digital_edicao(conj)
        with patch.object(addon.promob,'_limite_curvo_no_corpo',return_value=72.) as medir:
            addon.ferragens._definir_abertura(bpy.context,f,0.)
            self.assertEqual(medir.call_count,0)
            addon.ferragens._definir_abertura(bpy.context,f,.25)
            addon.ferragens._definir_abertura(bpy.context,f,.5)
            self.assertEqual(medir.call_count,1)
        self.assertEqual(g['porta_parametros']['abertura_limite_graus'],72.)
        self.assertFalse(g.get('porta_limite_pendente'))
        self.assertTrue(g.get('porta_limite_validado'))
        self.assertTrue(addon.portas_viewport._texto_abertura(f).startswith('36'))
        self.assertEqual(assinatura,addon.formas._digital_edicao(conj))

    def _bancada_curva_real(self):
        if bpy.app.version < (5,):self.skipTest('Preset gravado no Blender 5.x')
        caminho=os.path.join(os.path.dirname(__file__),'fixtures','bancada_curva_legada.blend')
        with bpy.data.libraries.load(caminho,link=False) as (de,para):
            para.collections=list(de.collections);para.objects=list(de.objects)
        for co in para.collections:
            if co.asset_data:bpy.context.scene.collection.children.link(co)
        bpy.context.view_layer.update()
        return next(o for o in para.objects if addon.chapas.MARCA_CONJUNTO in o)

    def _volume_intersecao_nativa(self,folha,corpo,matriz):
        # Oraculo independente: Boolean EXACT do Blender em copias.
        def copiar(o,m):
            me=o.data.copy();me.transform(m)
            bm=bmesh.new();bm.from_mesh(me)
            bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(me);bm.free()
            obj=bpy.data.objects.new('Volume de teste',me)
            bpy.context.scene.collection.objects.link(obj)
            return obj
        a,b=copiar(folha,matriz),copiar(corpo,corpo.matrix_world)
        try:
            mod=a.modifiers.new('Intersecao exata','BOOLEAN');mod.operation='INTERSECT';mod.solver='EXACT';mod.object=b
            bpy.context.view_layer.update()
            avaliado=a.evaluated_get(bpy.context.evaluated_depsgraph_get());me=avaliado.to_mesh()
            bm=bmesh.new()
            try:
                bm.from_mesh(me);return abs(bm.calc_volume())*1e9
            finally:bm.free();avaliado.to_mesh_clear()
        finally:
            for o in (a,b):
                me=o.data;bpy.data.objects.remove(o,do_unlink=True);bpy.data.meshes.remove(me)

    def test_curva_bancada_encaixa_sem_apagar_modelagem_e_abre_fora_do_corpo(self):
        from unittest.mock import patch
        conj=self._bancada_curva_real()
        folhas=[f for g in addon.portas._portas_do_conjunto(conj) for f in addon.portas._folhas_portas(g)]
        f=max(folhas,key=lambda o:o.chapa_comprimento_mm);rodape=min(folhas,key=lambda o:o.chapa_comprimento_mm)
        me=f.data;mr=rodape.data
        antes_rodape=[addon.ferragens._matriz_fechada(rodape)@v.co for v in mr.vertices]
        faces=[frozenset(p.vertices) for p in me.polygons]
        uv=me.uv_layers.new(name='UV da madeira')
        for i,d in enumerate(uv.data):d.uv=(i%7/7,i%11/11)
        uvs=[{me.loops[i].vertex_index:tuple(uv.data[i].uv) for i in p.loop_indices} for p in me.polygons]
        addon.ferragens._definir_abertura(bpy.context,f,.216251716)
        self.assertEqual(addon.promob.corrigir_curvas_legadas(conj,paineis_fixos=(rodape.parent.name,)),2)
        self.assertEqual(f.data,me);self.assertEqual(rodape.data,mr)
        self.assertEqual(faces,[frozenset(p.vertices) for p in me.polygons])
        atual=me.uv_layers['UV da madeira']
        self.assertEqual(uvs,[{me.loops[i].vertex_index:tuple(atual.data[i].uv) for i in p.loop_indices} for p in me.polygons])
        bm=bmesh.new();bm.from_mesh(me)
        try:self.assertGreater(bm.calc_volume(signed=True),0.)
        finally:bm.free()
        self.assertEqual(rodape.parent,conj);self.assertNotIn(addon.chapas.MARCA_FOLHA,rodape)
        self.assertTrue(rodape.get('eh_peca_curva'))
        for v,p in zip(mr.vertices,antes_rodape):self.assertLess((rodape.matrix_world@v.co-p).length,.000001)
        self.assertEqual(len(addon.portas._portas_do_conjunto(conj)),1)
        self.assertGreater(f.parent['porta_parametros'].get('abertura_limite_graus',0),45.)
        self.assertLess(f.parent['porta_parametros']['abertura_limite_graus'],110.)
        corpo=[o for o in addon.formas._pecas(conj) if o!=f]
        with patch.object(addon.promob,'_limite_curvo_no_corpo',side_effect=AssertionError('Recalculo no slider')):
            for fracao in (0.,.216251716,.5,1.):
                addon.ferragens._definir_abertura(bpy.context,f,fracao)
                for o in corpo:self.assertLess(self._volume_intersecao_nativa(f,o,f.matrix_world),1.,o.name)
        self.assertEqual(addon.promob.corrigir_curvas_legadas(conj),0)
        base=[addon.ferragens._matriz_fechada(f)@v.co for v in f.data.vertices]
        for propriedade in ('conj_largura_mm','conj_profundidade_mm'):
            original=getattr(conj,propriedade)
            setattr(conj,propriedade,100.)
            addon.ferragens._definir_abertura(bpy.context,f,.35)
            setattr(conj,propriedade,original)
            bpy.context.view_layer.update()
            for v,p in zip(f.data.vertices,base):self.assertLess((addon.ferragens._matriz_fechada(f)@v.co-p).length,.00005)

    def test_curva_sem_referencia_recusa_encaixe_sem_refazer_a_madeira(self):
        from unittest.mock import patch
        conj=self._bancada_curva_real()
        g=max(addon.portas._portas_do_conjunto(conj),key=lambda g:addon.portas._folhas_portas(g)[0].chapa_comprimento_mm)
        f,=addon.portas._folhas_portas(g);me=f.data
        antes=[v.co.copy() for v in me.vertices];faces=[tuple(p.vertices) for p in me.polygons]
        with patch.object(addon.promob,'_transportar_madeira_curva',return_value=None),patch.object(addon.portas,'_aplicar_portas',side_effect=AssertionError('Montou antes de validar')):
            self.assertFalse(addon.promob.alinhar_frente_ao_corpo(g))
        self.assertEqual(f.data,me);self.assertEqual(antes,[v.co for v in me.vertices])
        self.assertEqual(faces,[tuple(p.vertices) for p in me.polygons])

    def test_refs_clampadas_nao_apagam_sistema_ou_puxador_sem_confirmacao_da_migracao(self):
        conj=self._bancada_curva_real()
        g=min(addon.portas._portas_do_conjunto(conj),key=lambda g:addon.portas._folhas_portas(g)[0].chapa_comprimento_mm)
        f,=addon.portas._folhas_portas(g)
        puxadores=[o for o in f.children if addon.chapas.MARCA_PUXADOR in o]
        self.assertTrue(puxadores)
        nomes=[o.name for o in puxadores];meshes=[o.data for o in puxadores]
        addon.promob.corrigir_curvas_legadas(conj)
        self.assertEqual(f.parent,g)
        addon.promob.corrigir_curvas_legadas(conj,paineis_fixos=(g.name,))
        self.assertEqual(f.parent,conj)
        for nome,me in zip(nomes,meshes):
            o=bpy.data.objects.get(nome);self.assertIsNotNone(o);self.assertEqual(o.data,me)

    def test_inserir_curva_legada_migra_copia_sem_alterar_arquivo_e_sem_rna_morto(self):
        if bpy.app.version < (5,):self.skipTest('Preset gravado no Blender 5.x')
        import hashlib
        # o preset saiu da biblioteca (porta curva, pedido do usuario); a
        # copia dele em fixtures segue testando a migracao da curva legada
        pasta=os.path.join(os.path.dirname(__file__),'fixtures');arquivo='Bancada_Quarto_02_300x720x556.blend'
        with open(os.path.join(pasta,arquivo),'rb') as arq:antes=hashlib.sha256(arq.read()).digest()
        novos,raizes,erro=addon.biblioteca.inserir_preset(bpy.context,pasta,arquivo,'modulo',destino=Vector((2,3,0)))
        self.assertFalse(erro);self.assertTrue(novos);self.assertTrue(raizes)
        for o in novos:self.assertIsNotNone(bpy.data.objects.get(o.name));self.assertTrue(o.as_pointer())
        conj=next(o for o in novos if addon.chapas.MARCA_CONJUNTO in o)
        grupo=max(addon.portas._portas_do_conjunto(conj),key=lambda g:addon.portas._folhas_portas(g)[0].chapa_comprimento_mm)
        self.assertTrue(grupo.get('porta_perfil_corpo'))
        with open(os.path.join(pasta,arquivo),'rb') as arq:self.assertEqual(antes,hashlib.sha256(arq.read()).digest())

    def test_placa_acima_de_um_rodape_curvo_nao_cria_segunda_porta(self):
        import tempfile
        contorno=[(595-r*math.cos(i*math.pi/32),r*math.sin(i*math.pi/32))
                  for r,ids in ((245,range(17)),(230,range(16,-1,-1))) for i in ids]
        n=len(contorno)
        fs=[(i,i+1,n-2-i,n-1-i) for i in range(16)]
        fs += [(n+i,2*n-1-i,2*n-2-i,n+i+1) for i in range(16)]
        fs += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
        caixas=[('L',(0,-15,0),(350,0,700)),('D',(585,245,0),(600,600,700)),
                ('B',(0,0,0),(585,600,15)),('T',(0,0,685),(585,600,700)),
                ('H1',(558,245,80),(589,247,100)),('H2',(558,245,550),(589,247,592))]
        caminho=os.path.join(tempfile.mkdtemp(),'CurvaRodape.dxf')
        poly=[(nome,[(x,y,z) for z in alturas for x,y in contorno],fs) for nome,alturas in (('F',(5,695)),('Rodape',(0,75)))]
        dxf_promob(caminho,[(c,_faces_da_caixa(lo,hi)) for c,lo,hi in caixas],poly,
                   cores={**{c:253 if c.startswith('H') else 7 for c,lo,hi in caixas},'F':7,'Rodape':7})
        (conj,),info=addon.importacao.importar_dxf_promob(bpy.context,caminho,'Curva')
        self.assertEqual(info['portas'],1)
        self.assertEqual(len(addon.portas._portas_do_conjunto(conj)),1)

    def _diagonal_modelada(self):
        cs=[caixa('Lateral L',(.015,.350,.700),(.0075,.175,.350)),
            caixa('Lateral R',(.015,.250,.700),(.2925,.225,.350))]
        contorno=[(.015,0),(.150,0),(.285,.100),(.285,.350),(.015,.350)]
        n=len(contorno)
        for z in (0,.685):
            vs=[(x,y,h) for h in (z,z+.015) for x,y in contorno]
            fs=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
            malha=bpy.data.meshes.new('Tampo');malha.from_pydata(vs,[],fs)
            o=bpy.data.objects.new('Tampo',malha);bpy.context.collection.objects.link(o);cs.append(o)
        bpy.context.view_layer.update()
        for o in cs:addon.importacao.converter_em_chapa(o)
        conj=addon.modulos.agrupar_chapas(bpy.context,cs,'Diagonal modelada')
        p=addon.portas._parametros_portas_da_cena(bpy.context.scene,numerico=True)
        p.update(abertura='GIRO',folhas=1,dobradica='CURVA',dobradica_lado='DIREITA',
                 espessura_mm=15,lateral_mm=15,folga_mm=0,dobradicas_qtd=2)
        m=Matrix(((1,0,0),(0,0,1),(0,-1,0))).transposed().to_4x4();m.translation=Vector((0,-.025,.005))
        g=addon.portas._aplicar_portas(bpy.context,None,m,conj,300,690,p,frente='NEG_Y',largura_em='X')
        f=addon.portas._folhas_portas(g)[0]
        secao=[(.015,-.025),(.150,-.025),(.295,.087),(.295,.072),(.150,-.040),(.015,-.040)]
        vs=[f.matrix_world.inverted()@Vector((x,y,z)) for z in (.005,.695) for x,y in secao]
        n=len(secao);fs=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
        f.data.clear_geometry();f.data.from_pydata(vs,[],fs);f.data.update();f['porta_curva_modelada']=1
        addon.puxadores.criar_puxador(bpy.context,f,'ALCA','X-',1)
        bpy.context.view_layer.update()
        return conj,g,f

    # Regressao (era BUG, corrigido na 305): o perfil na borda X da folha
    # curva (linha da frente) ia pela caixa e caia na corda, fora da madeira.
    def test_perfil_na_borda_reta_da_folha_curva_senta_na_madeira(self):
        from unittest.mock import patch
        conj,g,f=self._diagonal_modelada()
        self.assertTrue(addon.promob.alinhar_frente_ao_corpo(g))
        pux,=[o for o in f.children if addon.chapas.MARCA_PUXADOR in o]
        # como as folhas curvas da biblioteca: sem a referencia nova das frentes
        with patch.object(addon.frentes,'referencia',return_value=None):
            addon.puxadores._trocar_modelo_puxador(pux,'PERFIL')
        bpy.context.view_layer.update()
        local=f.matrix_world.inverted()@pux.matrix_world.translation
        _hit,co,_n,_i=f.closest_point_on_mesh(local)
        self.assertLess((co-local).length,.002)
        self.assertAlmostEqual(max(pux.dimensions),f.chapa_comprimento_mm/1000,delta=.002)

    # Mesmo BUG, folha curva SEM linha: o raio de recuo 0 passava rente a'
    # ponta e o perfil ficava no lugar da caixa, solto no ar.
    def test_perfil_na_folha_curva_sem_linha_senta_na_madeira(self):
        from unittest.mock import patch
        conj,g,f=self._diagonal_modelada()
        self.assertNotIn('porta_linha_frente',f)
        pux,=[o for o in f.children if addon.chapas.MARCA_PUXADOR in o]
        pux['puxador_curvo']=True
        with patch.object(addon.frentes,'referencia',return_value=None):
            addon.puxadores._trocar_modelo_puxador(pux,'PERFIL')
        bpy.context.view_layer.update()
        local=f.matrix_world.inverted()@pux.matrix_world.translation
        _hit,co,_n,_i=f.closest_point_on_mesh(local)
        self.assertLess((co-local).length,.002)

    # Regressao (era BUG, corrigido na 307): "Definir como Frente" numa
    # porta curva tirava o vao da caixa da folha e a deslocava 10-76 cm.
    # Agora a madeira fica; lado, coberturas e o abrir trocam de sentido.
    def test_virar_frente_da_porta_curva_nao_mexe_na_madeira(self):
        from unittest.mock import patch
        conj,g,f=self._diagonal_modelada()
        F=addon.ferragens
        pux,=[o for o in f.children if addon.chapas.MARCA_PUXADOR in o]
        pux['puxador_curvo']=True
        p=dict(g['porta_parametros']);p.update(cobertura_esq_e=1.0,cobertura_dir_e=.5)
        g['porta_parametros']=p
        lado={'ESQUERDA':'DIREITA','DIREITA':'ESQUERDA'}[p['dobradica_lado']]
        def centro(fracao):
            F._definir_abertura(bpy.context,f,fracao);bpy.context.view_layer.update()
            vs=[f.matrix_world@v.co for v in f.data.vertices];return sum(vs,Vector())/len(vs)
        passo=centro(.5)-centro(0)
        antes=[f.matrix_world@v.co for v in f.data.vertices]
        z=g.matrix_world.to_3x3().col[2].copy()
        with patch.object(addon.frentes,'referencia',return_value=None):
            addon.puxadores.posicionar_puxador(pux);bpy.context.view_layer.update()
            pux_antes=pux.matrix_world.translation.copy()
            self.assertTrue(addon.importacao._definir_frente_porta(bpy.context,g,-z))
            addon.puxadores.posicionar_puxador(pux);bpy.context.view_layer.update()
            self.assertLess((pux.matrix_world.translation-pux_antes).length,.001)
        bpy.context.view_layer.update()
        self.assertLess(max((f.matrix_world@v.co-a).length for v,a in zip(f.data.vertices,antes)),1e-5)
        self.assertLess(g.matrix_world.to_3x3().col[2].dot(z),-.999)
        q=g['porta_parametros']
        self.assertEqual(q['dobradica_lado'],lado)
        self.assertEqual((q['cobertura_esq_e'],q['cobertura_dir_e']),(.5,1.0))
        self.assertLess((centro(.5)-centro(0)).dot(passo),0)    # abre para o outro lado

    def test_diagonal_modelada_alinha_perfil_normal_abertura_e_apoios(self):
        conj,g,f=self._diagonal_modelada()
        self.assertTrue(addon.promob.alinhar_frente_ao_corpo(g))
        self.assertEqual(g['porta_parametros']['dobradica_lado'],'ESQUERDA')
        self.assertGreater(g.matrix_world.to_3x3().col[2].dot(Vector((0,-1,0))),.999)
        linha=[addon.ferragens._matriz_fechada(f)@Vector(v) for v in f['porta_linha_frente']]
        self.assertAlmostEqual(linha[0].y,-.017,delta=.00005)
        self.assertAlmostEqual((linha[-1]-linha[-2]).normalized().dot(Vector((135,100,0)).normalized()),1,places=5)
        bases=[o for o in g.children if o.name.startswith('Dobradica Base')]
        self.assertEqual(len(bases),2)
        for base in bases:
            erros=[]
            for chapa in addon.modulos._estruturais(addon.modulos._chapas_do_conjunto(conj)):
                for v in base.data.vertices:
                    pt=base.matrix_world@v.co;hit,co,_n,_i=chapa.closest_point_on_mesh(chapa.matrix_world.inverted()@pt)
                    if hit:erros.append((chapa.matrix_world@co-pt).length)
            self.assertLess(min(erros),.00005)
        fechada=addon.ferragens._matriz_fechada(f)
        livre=linha[-1]
        addon.ferragens._definir_abertura(bpy.context,f,.5);bpy.context.view_layer.update()
        aberto=f.matrix_world@(fechada.inverted()@livre)
        self.assertLess(aberto.y,livre.y-.03)

    def test_diagonal_sem_placa_reconhecida_adota_frente_com_funcoes_nativas(self):
        conj,g,f=self._diagonal_modelada()
        obj=f.copy();obj.data=f.data.copy();bpy.context.collection.objects.link(obj)
        mundo=addon.ferragens._matriz_fechada(f)
        obj.parent=conj;obj.matrix_parent_inverse=Matrix.Identity(4);obj.matrix_world=mundo
        for chave in list(obj.keys()):del obj[chave]
        obj['eh_peca_curva']=1;obj[addon.chapas.MARCA_ACESSORIO]=1
        nome=obj.name
        for o in list(g.children_recursive):bpy.data.objects.remove(o,do_unlink=True)
        bpy.data.objects.remove(g,do_unlink=True);bpy.context.view_layer.update()
        self.assertFalse(addon.portas._portas_do_conjunto(conj))
        novos=addon.promob.integrar_frentes_diagonais(conj)
        self.assertEqual(len(novos),1)
        self.assertNotIn(nome,bpy.data.objects)
        novo=novos[0]
        self.assertTrue(novo.get('porta_perfil_corpo'))
        self.assertEqual(novo[addon.portas.CHAVE_MODULO_PORTA],conj.name)
        self.assertEqual(len(addon.portas._folhas_portas(novo)),1)
        self.assertTrue(any(addon.chapas.MARCA_PUXADOR in o for o in addon.portas._folhas_portas(novo)[0].children))

    def test_puxador_no_segmento_real_da_frente_e_da_borda_superior(self):
        conj,g,f=self._diagonal_modelada();addon.promob.alinhar_frente_ao_corpo(g)
        pux=next(o for o in f.children if addon.chapas.MARCA_PUXADOR in o)
        bordas=addon.puxadores._bordas_da_face(f,1)
        superiores=[ab for chave,ab in bordas.items() if chave.startswith('Y+|')]
        self.assertEqual(len(superiores),2)
        self.assertLess(abs((superiores[0][1]-superiores[0][0]).normalized().dot(
            (superiores[1][1]-superiores[1][0]).normalized())),.9)
        for borda,fracao in (('X+',.5),('Y+',.8)):
            pux['puxador_borda']=borda;pux['puxador_fracao']=fracao
            addon.puxadores.posicionar_puxador(pux);bpy.context.view_layer.update()
            esperado=Vector((100,-135,0)).normalized()
            self.assertGreater(pux.matrix_world.to_3x3().col[2].dot(esperado),.999)
            pt=pux.matrix_basis.translation
            hit,co,_n,_i=f.closest_point_on_mesh(pt)
            self.assertTrue(hit);self.assertLess((pt-co).length,.00001)

    def test_diagonal_quarto_append_sem_cache_resize_preserva_apoios_e_geometria(self):
        if bpy.app.version < (5,):
            self.skipTest('Preset gravado no Blender 5.x')
        from mathutils.kdtree import KDTree
        # Modelo descontinuado na biblioteca; a fixture conserva a regressao.
        caminho = os.path.join(os.path.dirname(__file__), 'fixtures',
                               'Diagonal_Quarto_Armario_06_350x2503x550.blend')
        # Append nativo evita o preparo do posicionador e o tique do timer:
        # a referencia tem de nascer ANTES de a primeira deformacao ocorrer.
        with bpy.data.libraries.load(caminho, link=False) as (origem, destino):
            destino.collections = list(origem.collections)
            destino.objects = list(origem.objects)
        for colecao in destino.collections:
            if colecao.asset_data:
                bpy.context.scene.collection.children.link(colecao)
        bpy.context.view_layer.update()
        conj = next(o for o in destino.objects if addon.chapas.MARCA_CONJUNTO in o)
        grupo, = addon.portas._portas_do_conjunto(conj)
        folha, = addon.portas._folhas_portas(grupo)
        self.assertIsNone(addon.frentes.referencia(folha))
        linha_antes = list(folha['porta_linha_frente'])
        self.assertEqual(len(linha_antes), 3)
        estruturais = addon.modulos._estruturais(addon.modulos._chapas_do_conjunto(conj))
        chapas = list(dict.fromkeys(list(estruturais)+[folha]))
        antes = {}
        for obj in chapas:
            matriz = addon.ferragens._matriz_fechada(obj) if obj == folha else obj.matrix_world
            antes[obj.name] = [matriz@v.co for v in obj.data.vertices]

        def conferir_apoios():
            bpy.context.view_layer.update()
            bases = [o for o in grupo.children if o.name.startswith('Dobradica Base')]
            self.assertEqual(len(bases), 3)
            for base in bases:
                erros = []
                for chapa in estruturais:
                    inversa = chapa.matrix_world.inverted()
                    for vertice in base.data.vertices:
                        ponto = base.matrix_world@vertice.co
                        hit, perto, _normal, _face = chapa.closest_point_on_mesh(inversa@ponto)
                        if hit:
                            erros.append((chapa.matrix_world@perto-ponto).length)
                self.assertTrue(erros, base.name)
                self.assertLess(min(erros), .00005, base.name)

        def conferir_retorno():
            for obj in chapas:
                pontos = antes[obj.name]
                matriz = addon.ferragens._matriz_fechada(obj) if obj == folha else obj.matrix_world
                atuais = [matriz@v.co for v in obj.data.vertices]
                self.assertEqual(len(atuais), len(pontos), obj.name)
                for alvos, consultas in ((pontos, atuais), (atuais, pontos)):
                    arvore = KDTree(len(alvos))
                    for indice, ponto in enumerate(alvos):
                        arvore.insert(ponto, indice)
                    arvore.balance()
                    self.assertLess(max(arvore.find(p)[2] for p in consultas), .00005, obj.name)

        conferir_apoios()
        addon.ferragens._definir_abertura(bpy.context, folha, .35)
        bpy.context.view_layer.update()
        self.assertIsNone(addon.frentes.referencia(folha))
        for propriedade, valor in (('conj_largura_mm', conj.conj_largura_mm+60),
                                    ('conj_profundidade_mm', 100)):
            original = getattr(conj, propriedade)
            for medida in (valor, original):
                setattr(conj, propriedade, medida)
                bpy.context.view_layer.update()
                self.assertAlmostEqual(folha[addon.ferragens.CHAVE_ABERTURA], .35, places=4)
                ref = addon.frentes.referencia(folha)
                self.assertIsNotNone(ref)
                self.assertEqual(len(ref['frente']), len(linha_antes))
                conferir_apoios()
            conferir_retorno()

    def test_diagonal_redimensiona_sem_perder_recorte_manual_ou_abertura(self):
        conj,g,f=self._diagonal_modelada();addon.promob.alinhar_frente_ao_corpo(g)
        f.data.vertices[1].co.y+=.003;f.data.update()
        faces=[tuple(p.vertices) for p in f.data.polygons]
        antes=[addon.ferragens._matriz_fechada(f)@v.co for v in f.data.vertices]
        largura=conj.conj_largura_mm
        addon.ferragens._definir_abertura(bpy.context,f,.35)
        conj.conj_largura_mm=largura+60
        self.assertAlmostEqual(f[addon.ferragens.CHAVE_ABERTURA],.35,places=4)
        self.assertEqual(faces,[tuple(p.vertices) for p in f.data.polygons])
        conj.conj_largura_mm=largura
        atual=[addon.ferragens._matriz_fechada(f)@v.co for v in f.data.vertices]
        self.assertLess(max((a-b).length for a,b in zip(antes,atual)),.00001)

    def test_contorno_da_porta_modelada_segue_vertices_sem_corda_ou_diagonal(self):
        conj,g,f=self._diagonal_modelada();addon.promob.alinhar_frente_ao_corpo(g)
        desenho=addon.portas_viewport._desenho_da_porta(g)
        self.assertTrue(desenho['perfil'])
        self.assertEqual(len(desenho['vao']),6)
        pontos,arestas=addon.portas_viewport._contorno_da_folha(f)
        for i,j in arestas:
            self.assertFalse(abs(i-j)==2, 'Corda atravessando as duas faces')
        for p in pontos:
            self.assertLess(min((f.matrix_world@v.co-p).length for v in f.data.vertices),1e-7)
        antes=[p.copy() for p in pontos]
        addon.ferragens._definir_abertura(bpy.context,f,.5);bpy.context.view_layer.update()
        depois,_=addon.portas_viewport._contorno_da_folha(f)
        self.assertGreater(max((a-b).length for a,b in zip(antes,depois)),.03)
        for a,b in zip(desenho['vao'],addon.portas_viewport._desenho_da_porta(g)['vao']):
            self.assertLess((a-b).length,1e-7)

    def test_previa_do_puxador_no_segmento_superior_coincide_com_objeto(self):
        conj,g,f=self._diagonal_modelada();addon.promob.alinhar_frente_ao_corpo(g)
        chave='Y+|1';fracao=.6
        addon.puxadores._posicionador_puxador[0]=dict(fase='LINHA',chapa=f.name,
            tipo='ALCA',borda=chave,face=1,fracao=fracao,arquivo='')
        try:
            previa=addon.arame._arame_do_posicionador()
            pux=addon.puxadores.criar_puxador(bpy.context,f,'ALCA',chave,1,fracao)
            bpy.context.view_layer.update()
            atual=addon.arame._arame_do_objeto_puxador(pux)
            self.assertTrue(previa)
            self.assertLess(max((a-b).length for a,b in zip(previa,atual)),1e-7)
            self.assertGreater(min(p.z for p in previa),.5)
            self.assertEqual(pux['puxador_borda'],'Y+')
        finally:
            addon.puxadores._posicionador_puxador[0]=None

    def test_pontas_da_folha_liberam_laterais_em_ambas_as_faces(self):
        conj,g,f=self._diagonal_modelada()
        self.assertTrue(addon.promob.alinhar_frente_ao_corpo(g))
        from mathutils.bvhtree import BVHTree
        m=addon.ferragens._matriz_fechada(f)
        vs=[m@v.co for v in f.data.vertices]
        arvore=BVHTree.FromPolygons(vs,[list(p.vertices) for p in f.data.polygons])
        for c in addon.modulos._estruturais(addon.modulos._chapas_do_conjunto(conj)):
            cv=[c.matrix_world@v.co for v in c.data.vertices]
            outra=BVHTree.FromPolygons(cv,[list(p.vertices) for p in c.data.polygons])
            self.assertFalse(arvore.overlap(outra),c.name)
            if abs(addon.chapas._eixos(c)[2].z)>.1:continue
            for i in (0,len(f['porta_linha_indices'])-1):
                for indice in (i,int(f['porta_linha_indices'][i])):
                    pt=vs[indice].copy();pt.z=.350
                    inv=c.matrix_world.inverted();hit,co,no,_=c.closest_point_on_mesh(inv@pt)
                    self.assertTrue(hit)
                    self.assertGreaterEqual(((inv@pt)-co).length,.00199)

    def test_diagonal_curva_real_nao_atravessa_lateral_ou_tampo(self):
        if bpy.app.version < (5,):
            self.skipTest('Preset gravado no Blender 5.x')
        # copia do preset que saiu da biblioteca (porta curva)
        path=os.path.join(os.path.dirname(__file__),'fixtures',
                          'Diagonal_Sup_Alto_02_300x1056x350.blend')
        with bpy.data.libraries.load(path,link=False) as (de,para):
            para.collections=list(de.collections);para.objects=list(de.objects)
        for c in para.collections:
            if c.asset_data:bpy.context.scene.collection.children.link(c)
        bpy.context.view_layer.update()
        conj=next(o for o in para.objects if addon.chapas.MARCA_CONJUNTO in o)
        g,=addon.portas._portas_do_conjunto(conj)
        self.assertTrue(addon.promob.alinhar_frente_ao_corpo(g))
        from mathutils.bvhtree import BVHTree
        f,=addon.portas._folhas_portas(g);m=addon.ferragens._matriz_fechada(f)
        arvore=BVHTree.FromPolygons([m@v.co for v in f.data.vertices],
                                   [list(p.vertices) for p in f.data.polygons])
        for c in addon.modulos._estruturais(addon.modulos._chapas_do_conjunto(conj)):
            outra=BVHTree.FromPolygons([c.matrix_world@v.co for v in c.data.vertices],
                                       [list(p.vertices) for p in c.data.polygons])
            self.assertFalse(arvore.overlap(outra),c.name)

    def test_caixas_cruzadas_no_vazio_do_l_nao_unem_modulos(self):
        vs,fs=base_em_l()
        l=addon.importacao._objeto_da_peca(bpy.context,'L',vs,fs,bpy.context.scene.collection)
        dentro=caixa('Outro modulo no vazio',(.1,.1,.015),(.45,.45,.0075))
        grupos=addon.importacao._modulos_por_contato([l,dentro])
        self.assertEqual(len(grupos),2)

    def test_destinos_das_novas_bibliotecas_nao_colidem_com_cozinha(self):
        raiz=os.path.join('D:',os.sep,'Promob')
        def destino(*p):return addon.importacao.destino_categoria_promob(os.path.join(raiz,*p),raiz)
        q,n=destino('Quartos','Armarios','Cantos','Cantos.dxf')
        self.assertEqual(q,('Armarios','Quartos','Armarios','Cantos'))
        self.assertNotEqual(n,destino('Cozinha','Cantos','Cantos.dxf')[1])
        self.assertEqual(destino('Cozinha','Portas','Madeira.dxf')[0],('Armarios','Cozinha','Portas','Madeira'))

    def test_mostruario_de_portas_vira_folha_nativa_sem_caixa_inventada(self):
        import tempfile
        path=os.path.join(tempfile.mkdtemp(),'Portas.dxf')
        dados=[('F',_faces_da_caixa((0,0,0),(400,15,680))),
               ('Q',_faces_da_caixa((1000,0,0),(1400,20,680))),
               ('V',_faces_da_caixa((1010,5,10),(1390,10,670))),
               ('H',_faces_da_caixa((10,15,100),(40,17,142)))]
        dxf_promob(path,dados,cores={'F':7,'Q':254,'V':254,'H':253})
        grupos,info=addon.importacao.importar_portas_avulsas(bpy.context,path,'Porta')
        self.assertEqual(len(grupos),2)
        self.assertTrue(all(addon.chapas.MARCA_PORTAS in g for g in grupos))
        self.assertFalse(any(addon.chapas.MARCA_CONJUNTO in g for g in grupos))
        quadro=next(g for g in grupos if g['porta_parametros']['folha']=='QUADRO')
        folha,=addon.portas._folhas_portas(quadro)
        self.assertAlmostEqual(folha['chapa_quadro_mm'],10,places=2)
        madeira=next(g for g in grupos if g!=quadro)
        f,=addon.portas._folhas_portas(madeira)
        self.assertAlmostEqual(f.chapa_largura_mm,400,places=2)
        self.assertEqual(len(f.data.vertices),8)

    def test_modulos_do_promob_so_com_as_chapas(self):
        # pedido do usuario: os modulos prontos do Promob, exportados em
        # DXF (uma camada por peca); dobradica, plaquinha de 2 mm e piso
        # ficam de fora, a base em L continua em L
        import tempfile
        caminho = os.path.join(tempfile.mkdtemp(), 'Cantos.dxf')
        vs_l, fs_l = base_em_l()
        dxf_promob(caminho, [
            ('LAYER0', _faces_da_caixa((-100, -100, -5), (3000, 900, 0))),      # piso
            ('LAYER1', _faces_da_caixa((0, 0, 15), (15, 600, 700))),           # lateral
            ('LAYER2', _faces_da_caixa((15, 585, 15), (600, 600, 700))),       # lateral
            ('LAYER3', _faces_da_caixa((15, 200, 300), (38, 243, 352))),       # dobradica
            ('LAYER4', _faces_da_caixa((15, 300, 500), (17, 331, 542))),       # placa 2 mm
            ('LAYER10', _faces_da_caixa((2000, 0, 0), (2015, 400, 700))),      # outro modulo
            ('LAYER11', _faces_da_caixa((2015, 0, 0), (2500, 400, 15))),
        ], [('LAYER5', vs_l, fs_l)])
        modulos, info = addon.importacao.importar_dxf_promob(
            bpy.context, caminho, addon.importacao.prefixo_da_categoria('Cantos'))
        self.assertEqual(info, {'pecas': 8, 'chapas': 5, 'curvas': 0, 'descartadas': 2,
                                'piso': 1, 'portas': 0, 'gavetas': 0, 'correr': 0, 'prateleiras': 0})
        self.assertEqual(len(modulos), 2)
        canto, outro = modulos
        self.assertTrue(canto.name.startswith('Canto 01 '), canto.name)
        self.assertEqual(len(addon.modulos._chapas_do_conjunto(canto)), 3)
        self.assertEqual(len(addon.modulos._chapas_do_conjunto(outro)), 2)
        # a base em L e' chapa de 15 mm com a malha PRESERVADA, no mesmo lugar
        base = next(c for c in addon.modulos._chapas_do_conjunto(canto)
                    if not addon.chapas._malha_e_caixa(c.data))
        self.assertAlmostEqual(base.chapa_espessura_mm, 15.0, places=3)
        self.assertEqual(len(base.data.vertices), 12)
        pts = [base.matrix_world @ v.co * 1000.0 for v in base.data.vertices]
        self.assertPerto([min(p[k] for p in pts) for k in range(3)], (0, 0, 0), 3)
        self.assertPerto([max(p[k] for p in pts) for k in range(3)], (600, 600, 15), 3)
        # as retangulares viram a caixa parametrica
        lateral = next(c for c in addon.modulos._chapas_do_conjunto(canto)
                       if addon.chapas._malha_e_caixa(c.data))
        self.assertEqual(sorted(round(v) for v in (lateral.chapa_largura_mm,
                                                   lateral.chapa_comprimento_mm,
                                                   lateral.chapa_espessura_mm)),
                         [15, 585, 685] if lateral.chapa_comprimento_mm < 600 else [15, 600, 685])
        # o operador (cabinet_importar_promob) faz o mesmo na cena
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        self.assertEqual(bpy.ops.object.cabinet_importar_promob(
            'EXEC_DEFAULT', filepath=caminho), {'FINISHED'})
        self.assertEqual(len([o for o in bpy.data.objects
                              if addon.chapas.MARCA_CONJUNTO in o]), 2)
        self.assertEqual(addon.importacao.prefixo_da_categoria('Inferiores'), 'Inferior')

    def test_promob_traz_a_porta_curva_e_a_prateleira_redonda(self):
        # pedido do usuario: o raio das cantoneiras/diagonais e' editavel,
        # entao a porta CURVA vem junto (acessorio que deforma) e a
        # prateleira de quina redonda e' chapa (contorno preservado). O
        # micro-ondas (caixa com moldura) nao e' peca curva.
        import tempfile
        caminho = os.path.join(tempfile.mkdtemp(), 'Diagonais.dxf')
        arco = lambda r: [(150 + r * math.cos(math.radians(180 + 7.5 * i)),
                           150 + r * math.sin(math.radians(180 + 7.5 * i)))
                          for i in range(13)]
        contorno = arco(150) + [(300, 0), (300, 550), (0, 550)]
        n = len(contorno)
        prateleira = ([(x, y, 0) for x, y in contorno] + [(x, y, 15) for x, y in contorno],
                      [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
                      + [(0, i + 1, i) for i in range(1, n - 1)]
                      + [(n, n + i, n + i + 1) for i in range(1, n - 1)])
        fora, dentro = arco(150), arco(135)
        faixa = fora + dentro[::-1]
        m = len(faixa)
        porta = ([(x, y, 15) for x, y in faixa] + [(x, y, 685) for x, y in faixa],
                 [(i, (i + 1) % m, m + (i + 1) % m, m + i) for i in range(m)]
                 + [(i, i + 1, m - 2 - i, m - 1 - i) for i in range(12)]
                 + [(m + i, m + m - 1 - i, m + m - 2 - i, m + i + 1) for i in range(12)])
        # micro-ondas: caixa de 450 x 300 x 15 com um vao (moldura)
        moldura = [(2000, 0), (2450, 0), (2450, 300), (2000, 300)]
        dxf_promob(caminho, [
            ('LAYER0', _faces_da_caixa((-500, -500, -5), (3000, 2000, 0))),     # piso
            ('LAYER1', _faces_da_caixa((300, 0, 0), (315, 565, 700))),
            ('LAYER2', _faces_da_caixa((0, 550, 0), (300, 565, 700))),
            ('LAYER9', _faces_da_caixa((2000, 0, 0), (2015, 400, 700))),
            ('LAYER10', _faces_da_caixa((2015, 0, 0), (2450, 400, 15))),
            ('LAYER11', _faces_da_caixa((2015, 0, 100), (2450, 20, 400))),     # micro-ondas
        ], [('LAYER3', *prateleira), ('LAYER4', *porta)])
        modulos, info = addon.importacao.importar_dxf_promob(bpy.context, caminho, 'Diagonal')
        self.assertEqual((info['chapas'], info['curvas']), (6, 1))
        diagonal = modulos[0]
        curvas = [o for o in diagonal.children if addon.formas.MARCA_CURVA in o]
        self.assertEqual(len(curvas), 1)
        self.assertIn(addon.chapas.MARCA_ACESSORIO, curvas[0])
        redonda = next(c for c in addon.modulos._chapas_do_conjunto(diagonal)
                       if not addon.chapas._malha_e_caixa(c.data))
        self.assertAlmostEqual(redonda.chapa_espessura_mm, 15.0, places=2)
        self.assertIsNone(addon.formas.forma_do_modulo(diagonal))
        geo=addon.hud._geometria_do_item(diagonal,'GRUPO',addon.formas._pecas(diagonal))
        self.assertFalse(any(l.get('letra')=='R' for l in geo['linhas']))

    def test_categorias_do_promob_pela_pasta_e_pelo_arquivo(self):
        # pedido do usuario: a PASTA e' a aba do Promob, o ARQUIVO a
        # categoria; as primeiras exportacoes (Cantos/, Bifond/) sao Inferiores
        cat = addon.importacao.categoria_promob
        raiz = os.path.join('Promob', 'Cozinha')
        self.assertEqual(cat(os.path.join(raiz, 'Bifond', 'Balcões.dxf')),
                         ('Inferiores', 'Balcoes', 'Balcao'))
        self.assertEqual(cat(os.path.join(raiz, 'Bifond', 'Bifond.dxf')),
                         ('Inferiores', 'Cantos Bifold', 'Bifold'))
        self.assertEqual(cat(os.path.join(raiz, 'Bifond', 'PEletros.dxf')),
                         ('Inferiores', 'Para Eletros', 'Eletro'))
        self.assertEqual(cat(os.path.join(raiz, 'Cantos', 'Cantos.dxf')),
                         ('Inferiores', 'Cantos', 'Canto'))
        # fora de Inferiores o nome leva a aba: nao grava por cima
        self.assertEqual(cat(os.path.join(raiz, 'Sup Baixos', 'Cantos.dxf')),
                         ('Sup Baixos', 'Cantos', 'Canto Sup Baixo'))
        self.assertEqual(cat(os.path.join(raiz, 'Altos', 'Torres.dxf')),
                         ('Altos', 'Torres', 'Torre Alto'))
        self.assertEqual(cat(os.path.join(raiz, 'Ilhas', 'Inferiores.dxf')),
                         ('Ilhas', 'Inferiores', 'Inferior Ilha'))
        self.assertEqual(addon.importacao.prefixo_da_categoria('Diagonais'), 'Diagonal')

    def test_piso_fino_sai_mesmo_com_modulos_fora_dele(self):
        # Especiais do Promob: os modulos passam da borda do piso (72% em
        # cima); fino assim (5 mm) e grande, e' piso -- senao ele juntava
        # todos os modulos num so'
        import tempfile
        caminho = os.path.join(tempfile.mkdtemp(), 'Especiais.dxf')
        caixas = [('LAYER0', _faces_da_caixa((0, 0, -5), (2000, 1000, 0)))]
        for n, x in enumerate((100, 1800, 2600)):
            caixas += [('LAYER%d' % (10 * n + 1), _faces_da_caixa((x, 100, 0), (x + 15, 600, 700))),
                       ('LAYER%d' % (10 * n + 2), _faces_da_caixa((x + 15, 100, 0), (x + 400, 600, 15)))]
        dxf_promob(caminho, caixas)
        modulos, info = addon.importacao.importar_dxf_promob(bpy.context, caminho, 'Especial')
        self.assertEqual(info['piso'], 1)
        self.assertEqual(len(modulos), 3)

    def test_peca_girada_e_recortada_fica_no_lugar_ao_virar_chapa(self):
        # Regressao: `converter_em_chapa` trocava a matriz sem levar os
        # vertices -- a peca recortada ia para outro lugar, e a caixa a 45
        # graus (porta de canto do Promob) nao era reconhecida como caixa
        malha = bpy.data.meshes.new('Diagonal')
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Rotation(math.radians(45), 4, 'Z')
                              @ Matrix.Diagonal((0.4, 0.015, 0.7, 1.0)))
        bm.to_mesh(malha)
        bm.free()
        obj = bpy.data.objects.new('Diagonal', malha)
        bpy.context.collection.objects.link(obj)
        obj.location = (1.0, 2.0, 0.35)
        bpy.context.view_layer.update()
        antes = sorted(tuple(round(c, 5) for c in obj.matrix_world @ v.co)
                       for v in obj.data.vertices)
        addon.importacao.converter_em_chapa(obj)
        bpy.context.view_layer.update()
        self.assertTrue(addon.chapas._malha_e_caixa(obj.data))
        self.assertAlmostEqual(obj.chapa_espessura_mm, 15.0, places=3)
        depois = sorted(tuple(round(c, 5) for c in obj.matrix_world @ v.co)
                        for v in obj.data.vertices)
        for a, b in zip(antes, depois):
            self.assertPerto(a, b, 4)

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
        self.assertTrue(addon.importacao._analisar_peca(placa)['chapa'])
        for obj in (cubo, pe, cilindro):
            self.assertFalse(addon.importacao._analisar_peca(obj)['chapa'], obj.name)

    def test_lateral_em_pe_girada_vira_chapa_sem_sair_do_lugar(self):
        # REGRESSAO: a conversao lia obj.dimensions em eixos de mundo e
        # tomava Z como espessura -- esta lateral virava chapa de 30 mm.
        lateral = caixa('Lateral', (0.018, 0.4, 0.7), (1, 2, 3),
                        rot_z=math.radians(30))
        antes = limites([lateral])
        selecionar(lateral)
        self.assertEqual(bpy.ops.object.cabinet_marcar(), {'FINISHED'})
        self.assertIn(addon.chapas.MARCA_CHAPA, lateral)
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
        self.assertIn(addon.chapas.MARCA_CONJUNTO, conj)
        self.assertEqual(set(addon.modulos._chapas_do_conjunto(conj)), set(pecas))
        self.assertIn(addon.chapas.MARCA_ACESSORIO, pe)
        self.assertNotIn(addon.chapas.MARCA_CHAPA, pe)
        self.assertEqual(pe.parent, conj)
        for peca in pecas:
            self.assertEqual(peca.chapa_espessura_mm, 18.0)

    def test_acessorio_segue_a_face_mais_proxima(self):
        pecas, pe = self.armario()
        selecionar(*pecas, pe)
        bpy.ops.object.cabinet_converter_modulo()
        conj = bpy.context.object
        antes = addon.portas._centro_mundo(pe)
        conj.conj_largura_mm += 100     # cresce a partir da esquerda
        bpy.context.view_layer.update()
        depois = addon.portas._centro_mundo(pe)
        # o pe' esta' perto da DIREITA: anda junto com ela
        self.assertAlmostEqual(depois.x - antes.x, 0.1, places=4)
        self.assertAlmostEqual(depois.z, antes.z, places=4)
        conj.conj_altura_mm += 200      # base parada: o pe' tambem
        bpy.context.view_layer.update()
        self.assertAlmostEqual(addon.portas._centro_mundo(pe).z, antes.z, places=4)

    def test_sem_nenhuma_chapa_tudo_vira_chapa(self):
        a = caixa('A', (0.3, 0.3, 0.3), (0, 0, 0))
        b = caixa('B', (0.3, 0.3, 0.3), (0.3, 0, 0))
        selecionar(a, b)
        bpy.ops.object.cabinet_converter_modulo()
        self.assertIn(addon.chapas.MARCA_CHAPA, a)
        self.assertIn(addon.chapas.MARCA_CHAPA, b)

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
        return addon.portas._grupo_portas(bpy.context.object), placa, objs[1:]

    def test_folha_de_objetos_fica_no_lugar_com_o_puxador(self):
        placa = caixa('Placa', (0.4, 0.018, 0.7), (0, -0.209, 0.35))
        pux = caixa('Puxador', (0.02, 0.03, 0.15), (0.17, -0.233, 0.35))
        antes = limites([placa]), limites([pux])
        selecionar(placa, pux)
        bpy.ops.object.cabinet_folha_de_objetos()
        grupo = addon.portas._grupo_portas(placa)
        self.assertIsNotNone(grupo)
        self.assertIn(addon.chapas.MARCA_FOLHA, placa)
        self.assertEqual(addon.portas._folhas_portas(grupo), [placa])
        self.assertEqual(pux.parent, placa)
        self.assertIn(addon.chapas.MARCA_PUXADOR, pux)
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
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'folga_mm', 3.0), '')
        self.assertAlmostEqual(limites([pux])[1][0] - limites([pux])[0][0],
                               largura, places=5)
        self.assertAlmostEqual(limites([placa])[1][0] - limites([pux])[1][0],
                               borda, places=5)

    def test_puxador_destravado_estica_com_a_folha(self):
        grupo, placa, (pux,) = self.porta_importada()
        pux[addon.chapas.CHAVE_TRAVAS_PUXADOR] = [0, 1, 1]
        largura = limites([pux])[1][0] - limites([pux])[0][0]
        folha_antes = placa.chapa_largura_mm
        addon.portas._editar_parametro_porta(bpy.context, grupo, 'folga_mm', 20.0)
        razao = placa.chapa_largura_mm / folha_antes
        self.assertLess(razao, 1.0)
        self.assertAlmostEqual(limites([pux])[1][0] - limites([pux])[0][0],
                               largura * razao, places=5)

    def test_vao_inverso_ida_e_volta(self):
        base = dict(abertura='GIRO', folhas=1, dobradica='RETA',
                    espessura_mm=18.0, lateral_mm=18.0, folga_mm=2.0,
                    entre_folhas_mm=3.0, afastamento_mm=4.0,
                    recuo_embutida_mm=5.0, recuo_correr_mm=30.0,
                    entre_planos_mm=2.0)
        for dobradica in ('RETA', 'CURVA', 'SUPER_CURVA'):
            for folhas in (1, 2):
                with self.subTest(dobradica=dobradica, folhas=folhas):
                    p = dict(base, dobradica=dobradica, folhas=folhas)
                    calculadas = addon.portas._calcular_folhas_portas(600, 800, p)
                    pontos = [Vector(c) + Vector((sx * l, sy * a, sz * e)) / 2
                              for l, a, e, c in calculadas
                              for sx in (-1, 1) for sy in (-1, 1)
                              for sz in (-1, 1)]
                    lo = Vector(tuple(min(q[i] for q in pontos) for i in range(3)))
                    hi = Vector(tuple(max(q[i] for q in pontos) for i in range(3)))
                    largura, altura, origem = addon.importacao._vao_inverso((lo, hi), p)
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
        self.assertEqual(len(addon.portas._folhas_portas(g1)), 2)
        self.assertAlmostEqual(g1['porta_parametros']['entre_folhas_mm'], 3.0,
                               places=3)
        lo, hi = limites(addon.portas._folhas_portas(g1))
        self.assertPerto(lo, externo[0], 4)
        self.assertPerto(hi, externo[1], 4)

    def test_porta_dupla_recusa_alturas_diferentes(self):
        g1, _p1, _ = self.porta_importada(x=-0.2015)
        g2, _p2, _ = self.porta_importada(x=0.2015, altura=0.6)
        selecionar(g1, g2)
        self.assertEqual(bpy.ops.object.cabinet_porta_dupla(), {'CANCELLED'})
        self.assertIn(g2.name, bpy.data.objects)
        self.assertEqual(len(addon.portas._folhas_portas(g1)), 1)

    def test_definir_frente_vira_a_porta_sem_mover(self):
        grupo, placa, (pux,) = self.porta_importada()
        antes = limites([placa]), limites([pux])
        normal = grupo.matrix_world.to_3x3().col[2].normalized()
        self.assertFalse(addon.importacao._definir_frente_porta(bpy.context, grupo, normal))
        self.assertTrue(addon.importacao._definir_frente_porta(bpy.context, grupo, -normal))
        nova = grupo.matrix_world.to_3x3().col[2].normalized()
        self.assertAlmostEqual(nova.dot(normal), -1.0, places=5)
        for obj, (lo, hi) in ((placa, antes[0]), (pux, antes[1])):
            lo2, hi2 = limites([obj])
            self.assertPerto(lo, lo2, 4)
            self.assertPerto(hi, hi2, 4)
        with self.assertRaises(ValueError):
            addon.importacao._definir_frente_porta(bpy.context, grupo, Vector((0, 0, 1)))

    # ---------------------------------------------- vincular porta + modulo
    def nicho(self):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar()
        conj = next(o for o in bpy.data.objects if addon.chapas.MARCA_CONJUNTO in o)
        bpy.context.view_layer.update()
        return conj

    def porta_no_modulo(self, conj, embutida=False):
        lo, hi = addon.portas._limites_locais_modulo(conj)
        E = addon.portas._caixa_do_modulo(conj)[3]
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
        grupo = addon.portas._grupo_portas(placa)
        selecionar(grupo, conj)
        self.assertTrue(addon.importacao.OBJECT_OT_vincular_porta.poll(bpy.context))
        self.assertEqual(bpy.ops.object.cabinet_vincular_porta(), {'FINISHED'})
        return grupo, placa, pux

    def test_vincular_deduz_reta_e_acompanha_o_modulo(self):
        conj = self.nicho()
        grupo, placa, pux = self.porta_no_modulo(conj)
        p = grupo['porta_parametros']
        self.assertEqual(p['dobradica'], 'RETA')
        self.assertAlmostEqual(p['folga_mm'], 0.0, places=3)
        self.assertAlmostEqual(p['afastamento_mm'], 0.0, places=3)
        self.assertEqual(grupo[addon.portas.CHAVE_MODULO_PORTA], conj.name)
        self.assertEqual(grupo.parent, conj)
        L = addon.portas._caixa_do_modulo(conj)[0]
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
        lo, hi = addon.portas._limites_locais_modulo(conj)
        E = addon.portas._caixa_do_modulo(conj)[3]
        meio = (lo.z + hi.z) / 2
        a = conj.matrix_world @ (Vector((lo.x, lo.y, meio)) / 1000)
        b = conj.matrix_world @ (Vector((hi.x, lo.y, hi.z)) / 1000)
        chapa = addon.modulos._chapas_do_conjunto(conj)[0]
        ref = conj.matrix_world.to_quaternion().to_matrix()
        quantos = len([o for o in bpy.data.objects if addon.chapas.MARCA_PORTAS in o])
        self.assertEqual(bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            referencia=tuple(v for linha in ref for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name,
            objeto_a_nome=chapa.name, objeto_b_nome=chapa.name,
            centro=addon.portas._centro_do_movel(chapa, chapa),
            grupo_alvo=grupo.name), {'FINISHED'})
        self.assertEqual(len([o for o in bpy.data.objects
                              if addon.chapas.MARCA_PORTAS in o]), quantos)
        self.assertAlmostEqual(grupo['porta_vao_altura_mm'],
                               hi.z - E - meio, places=2)
        self.assertEqual(grupo[addon.portas.CHAVE_MODULO_PORTA], conj.name)
        self.assertEqual(addon.portas._folhas_portas(grupo), [placa])

    # ------------------------------------------------------------ gaveta
    def test_cabecalho_tem_sete_abas_com_alvenaria_e_internos_juntos(self):
        # As correntes entre as abas foram descontinuadas (pedido do
        # usuario): nenhum widget de operador no cabecalho. A aba Gavetas
        # e as Prateleiras/Divisorias vem antes de Puxadores.
        for largura in (190, 320, 564):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1200)
            cabecalho = addon.gaveta._partes_gaveta(widgets)[0]
            if largura < 400:
                self.assertEqual(len(cabecalho), 1)
                self.assertEqual(cabecalho[0][5][:2], ('suspenso', addon.gaveta.CHAVE_ABAS))
                self.assertEqual(cabecalho[0][5][4], tuple(a[0] for a in addon.gaveta.ABAS_GAVETA))
            else:
                self.assertEqual([w[5][0] for w in cabecalho], ['aba'] * 7)
                self.assertEqual([w[5][1] for w in cabecalho],
                                 ['MODULOS', 'PORTAS', 'FUNDOS', 'GAVETAS', 'PRATELEIRAS', 'PUXADORES', 'ALVENARIA'])
            self.assertFalse(any(w[5] and w[5][0] == 'operador'
                                 and w[1] > 1200 - 48 for w in widgets))
            fim = cabecalho[-1]
            self.assertAlmostEqual(fim[0] + fim[2], 12 + min(540, largura - 24))
        # sem selecao, as correntes nao tem o que ligar
        selecionar(caixa('X', (0.1, 0.1, 0.1), (0, 0, 0)))
        self.assertFalse(addon.gaveta_eventos._poll_operador('object.cabinet_vincular_porta'))
        self.assertFalse(addon.gaveta_eventos._poll_operador('object.cabinet_vincular_puxador'))

    def test_bloco_do_puxador_tem_cadeados_e_e_igual_nas_tres_abas(self):
        _grupo, _placa, (pux,) = self.porta_importada()
        selecionar(pux)
        modo, campos, dono = addon.gaveta._medidas_gaveta(bpy.context)
        self.assertEqual((modo, dono), ('PUXADOR', 'puxador'))
        alvo = {'medida', 'cadeado'}

        def bloco(aba):
            bpy.context.scene.cabinet_aba = aba
            widgets = addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)
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
                      addon.gaveta._widgets_gaveta(bpy.context, largura, 1400)]
            for i, (ax, ay, aw, ah) in enumerate(caixas):
                for bx, by, bw, bh in caixas[i + 1:]:
                    sobrepoe = (ax < bx + bw - 0.01 and bx < ax + aw - 0.01
                                and ay < by + bh - 0.01 and by < ay + ah - 0.01)
                    self.assertFalse(sobrepoe, 'largura %d' % largura)

    # ------------------------------------------- Promob -> sistemas nossos
    # Pedido do usuario: "integracao, nao importacao bruta". A frente com
    # dobradica vira PORTA nativa, a com caixa atras GAVETAS nativas, o
    # quadro de aluminio porta de CORRER (folha Quadro); trilho, dobradica
    # e quadro do Promob nunca viram chapa. Caixas em mm, frente em -Y.
    def importar(self, nome, caixas, cores):
        import tempfile
        caminho = os.path.join(tempfile.mkdtemp(), nome)
        dxf_promob(caminho, [(c, _faces_da_caixa(lo, hi)) for c, lo, hi in caixas],
                   cores=cores)
        return addon.importacao.importar_dxf_promob(bpy.context, caminho, 'Teste')

    CORPO_400 = [   # 400 x 700, corpo de 15 de y 15 a 565 (a porta na frente)
        ('LAYER1', (0, 15, 0), (15, 565, 700)),
        ('LAYER2', (385, 15, 0), (400, 565, 700)),
        ('LAYER3', (15, 15, 0), (385, 565, 15)),
        ('LAYER4', (15, 15, 685), (385, 565, 700)),
    ]

    def test_promob_ilha_duas_frentes_fica_com_porta_e_fundo_nativos(self):
        caixas=self.CORPO_400+[
            ('F',(5,0,5),(395,15,695)),('R',(5,565,5),(395,580,695)),
            ('HE',(10,14,100),(33,57,152)),('HD',(10,523,100),(33,566,152))]
        cores={c:253 if c.startswith('H') else 7 for c,lo,hi in caixas}
        (conj,),info=self.importar('IlhaPassante.dxf',caixas,cores)
        self.assertEqual(info['portas'],1)
        grupo,=addon.portas._portas_do_conjunto(conj)
        folha,=addon.portas._folhas_portas(grupo)
        fora=addon.ferragens._matriz_fechada(folha).to_3x3().col[2].normalized()
        self.assertLess(fora.y,-.99)
        fundo=addon.modulos.fundo_do_modulo(conj)
        self.assertIsNotNone(fundo)
        self.assertAlmostEqual(fundo.chapa_espessura_mm,5,places=2)
        self.assertAlmostEqual(conj[addon.modulos.CHAVE_RECUO_FUNDO],15,places=2)
        self.assertNotIn('Peca R',bpy.data.objects)

    def test_promob_fundo_rente_na_fonte_importa_recuado_sem_atravessar_prateleira(self):
        caixas=self.CORPO_400+[
            ('Fundo',(10,559,10),(390,565,690)),
            ('Prateleira',(15,20,300),(385,559,315))]
        (conj,),info=self.importar('FundoRente.dxf',caixas,{c:7 for c,lo,hi in caixas})
        fundo=addon.modulos.fundo_do_modulo(conj)
        self.assertAlmostEqual(fundo.chapa_espessura_mm,6,places=2)
        inv=conj.matrix_world.inverted()
        def ys(obj):return [(inv @ (obj.matrix_world @ v.co)).y*1000 for v in obj.data.vertices]
        hi=addon.modulos._caixa_local_estrutural(conj)[1].y
        self.assertAlmostEqual(hi-max(ys(fundo)),15,places=2)
        grupo,=addon.prateleiras.grupos_do_modulo(conj)
        prateleira,=addon.prateleiras.prateleiras_do_grupo(grupo)
        self.assertLessEqual(max(ys(prateleira)),min(ys(fundo))+.01)

    def test_promob_frentes_perpendiculares_de_canto_sao_preservadas(self):
        def face(fora):
            fora=Vector(fora);up=Vector((0,0,1))
            return dict(referencia=Matrix((up.cross(fora),-fora,up)).transposed(),
                        folhas=[addon.promob.peca(None,(0,0,0),(400,15,700))])
        frente=face((0,-1,0));lateral=face((1,0,0));costas=face((0,1,0))
        self.assertEqual(addon.promob.portas_sem_faces_opostas([frente,lateral]),[frente,lateral])
        self.assertEqual(addon.promob.portas_sem_faces_opostas([costas,lateral,frente]),[lateral,frente])

    def test_promob_frente_com_dobradica_vira_porta_nativa(self):
        caixas = self.CORPO_400 + [
            ('LAYER5', (10, 541, 10), (390, 547, 690)),       # fundo de 6
            ('LAYER6', (5, 0, 5), (395, 15, 695)),            # a frente
            ('LAYER7', (367, 14, 100), (390, 57, 152)),       # dobradicas
            ('LAYER8', (367, 14, 550), (390, 57, 602)),
            ('LAYER9', (354, 15, 105), (385, 17, 147)),       # placa 2 mm
        ]
        cores = {c: 7 for c, _lo, _hi in caixas}
        cores.update(LAYER7=253, LAYER8=253, LAYER9=253)
        modulos, info = self.importar('Balcoes.dxf', caixas, cores)
        self.assertEqual((len(modulos), info['portas']), (1, 1), info)
        conj = modulos[0]
        # a frente saiu do corpo: P = 550, e o E e' o da caixa (nao o fundo de 6)
        self.assertAlmostEqual(conj.conj_profundidade_mm, 550.0, places=1)
        self.assertAlmostEqual(conj.conj_espessura_mm, 15.0, places=3)
        grupo, = addon.portas._portas_do_conjunto(conj)
        p = dict(grupo['porta_parametros'])
        # dobradicas a' direita; cobre 10 de 15 (o Promob deixa 5) = RETA nossa
        self.assertEqual((p['abertura'], p['folhas'], p['dobradica_lado'], p['dobradica']),
                         ('GIRO', 1, 'ESQUERDA', 'RETA'))
        # o fundo fino e' o FUNDO dependente (refeito pela caixa, em canal)
        fundo = addon.modulos.fundo_do_modulo(conj)
        self.assertIsNotNone(fundo)
        self.assertAlmostEqual(fundo.chapa_espessura_mm, 6.0, places=1)
        self.assertAlmostEqual(fundo.chapa_largura_mm, 400 - 30 + 14, places=1)
        # nenhuma ferragem do Promob virou peca
        self.assertFalse([o for o in bpy.data.objects if o.name in ('Peca LAYER7', 'Peca LAYER9')])

    def test_promob_dupla_articula_nas_bordas_externas_e_preserva_alturas(self):
        corpo = [(c, (lo[0] * 2 if c == 'LAYER2' else lo[0], lo[1], lo[2]),
                  (hi[0] * 2 if c in ('LAYER2', 'LAYER3', 'LAYER4') else hi[0], hi[1], hi[2]))
                 for c, lo, hi in self.CORPO_400]
        corpo[1] = ('LAYER2', (785, 15, 0), (800, 565, 700))
        corpo[2] = ('LAYER3', (15, 15, 0), (785, 565, 15))
        corpo[3] = ('LAYER4', (15, 15, 685), (785, 565, 700))
        caixas = corpo + [('F1', (5, 0, 5), (399, 15, 695)),
                          ('F2', (401, 0, 5), (795, 15, 695))]
        # Placa e braco sao UMA dobradica. As duas folhas tem margens
        # assimetricas diferentes; nao substituir pelo padrao de 100 mm.
        for lado, x, zs in [('E', 10, (120, 530)), ('D', 767, (140, 580))]:
            for i, z in enumerate(zs):
                caixas += [(lado + str(i), (x, 14, z - 26), (x + 23, 57, z + 26)),
                           (lado + str(i) + 'P', (x, 15, z - 21), (x + 31, 17, z + 21))]
        cores = {c: 7 if c.startswith(('LAYER', 'F')) else 253 for c, _, _ in caixas}
        (conj,), info = self.importar('Dupla.dxf', caixas, cores)
        self.assertEqual(info['portas'], 1)
        grupo, = addon.portas._portas_do_conjunto(conj)
        self.assertEqual(grupo['porta_parametros']['folhas'], 2)
        folhas = addon.portas._folhas_portas(grupo)
        raizes = [o for o in grupo.children if o.get('cabinet_peca') == 'raiz']
        self.assertEqual(len(raizes), 4)
        for indice, zs in [(0, (120, 530)), (1, (140, 580))]:
            roots = [r for r in raizes if r['porta_ferragem_folha'] == indice]
            self.assertEqual(sorted(round(r.matrix_world.translation.z * 1000) for r in roots), list(zs))
            for r in roots:
                self.assertLess(abs(r.matrix_world.translation.x * 1000 - (15 if indice == 0 else 785)), 3)
            fechado = folhas[indice].matrix_world.copy()
            addon.ferragens._definir_abertura(bpy.context, folhas[indice], .7)
            # A borda articulada fica junto ao apoio; a borda livre avanca.
            l = folhas[indice].chapa_largura_mm / 2000
            articulada = Vector((-l if indice == 0 else l, 0, 0))
            livre = -articulada
            desloc_apoio = (folhas[indice].matrix_world @ articulada - fechado @ articulada).length
            desloc_livre = (folhas[indice].matrix_world @ livre - fechado @ livre).length
            self.assertLess(desloc_apoio, desloc_livre / 5)
        self.assertEqual(addon.portas._editar_parametro_porta(bpy.context, grupo, 'dobradicas_qtd', 3), '')
        self.assertNotIn('dobradicas_referencia', grupo['porta_parametros'])

    def _porta_promob_girada(self, angulo):
        import tempfile
        caixas = self.CORPO_400 + [('F', (5, 0, 5), (395, 15, 695)),
                                  ('D1', (10, 14, 94), (33, 57, 146)),
                                  ('P1', (10, 15, 99), (41, 17, 141)),
                                  ('D2', (10, 14, 524), (33, 57, 576)),
                                  ('P2', (10, 15, 529), (41, 17, 571))]
        giro = Matrix.Rotation(math.radians(angulo), 3, 'Z')
        faces = [(c, [[tuple(giro @ Vector(v)) for v in face] for face in _faces_da_caixa(lo, hi)])
                 for c, lo, hi in caixas]
        cores = {c: 253 if c[0] in ('D', 'P') else 7 for c, _, _ in caixas}
        caminho = os.path.join(tempfile.mkdtemp(), 'Girada.dxf')
        dxf_promob(caminho, faces, cores=cores)
        (conj,), info = addon.importacao.importar_dxf_promob(bpy.context, caminho, 'Girada')
        self.assertEqual(info['portas'], 1)
        grupo, = addon.portas._portas_do_conjunto(conj)
        esperado = giro @ Vector((0, -1, 0))
        self.assertGreater(grupo.matrix_world.to_3x3().col[2].normalized().dot(esperado), .999)
        self.assertEqual(grupo['porta_parametros']['dobradica_lado'], 'ESQUERDA')
        return conj, grupo

    def test_promob_porta_diagonal_e_apoio_nao_viram_duas_portas(self):
        conj, grupo = self._porta_promob_girada(45)
        self.assertIn(addon.portas.CHAVE_VAO_ORIENTADO, grupo)
        normal = grupo.matrix_world.to_3x3().col[2].copy()
        matriz = grupo.matrix_world.copy()
        # Refazer uma caixa pode trocar os indices; a ancora e' a QUINA.
        for obj in set(grupo.get('porta_vao_apoio_%d' % i) for i in range(3)):
            if obj is None or len(obj.data.vertices) != 8:
                continue
            vs = [tuple(v.co) for v in reversed(obj.data.vertices)]
            fs = [[7 - i for i in p.vertices] for p in obj.data.polygons]
            attr = obj.data.attributes.get(addon.solda.ATRIBUTO_CANTO)
            codigos = [d.value for d in reversed(attr.data)] if attr else None
            obj.data.clear_geometry()
            obj.data.from_pydata(vs, [], fs)
            if codigos is not None:
                attr = (obj.data.attributes.get(addon.solda.ATRIBUTO_CANTO)
                        or obj.data.attributes.new(addon.solda.ATRIBUTO_CANTO, 'INT', 'POINT'))
                for d, codigo in zip(attr.data, codigos):
                    d.value = codigo
        bpy.context.view_layer.update()
        addon.portas.atualizar_portas_do_conjunto(conj)
        self.assertLess((grupo.matrix_world.translation - matriz.translation).length, 1e-6)
        addon.modulos.redimensionar_grupo(addon.modulos._chapas_do_conjunto(conj),
            (conj.conj_largura_mm, conj.conj_altura_mm + 100, conj.conj_profundidade_mm))
        addon.portas.atualizar_portas_do_conjunto(conj)
        bpy.context.view_layer.update()
        self.assertGreater(grupo.matrix_world.to_3x3().col[2].normalized().dot(normal), .999)
        self.assertGreater(grupo['porta_vao_altura_mm'], 700)

    def test_promob_porta_perpendicular_nao_depende_do_ymin(self):
        self._porta_promob_girada(90)

    def test_promob_dobradica_lateral_perto_do_topo_nao_vira_basculante(self):
        caixas = self.CORPO_400 + [('F', (5, 0, 500), (395, 15, 695)),
                                  ('D', (10, 14, 634), (33, 57, 686)),
                                  ('P', (10, 15, 639), (41, 17, 681))]
        cores = {c: 253 if c in ('D', 'P') else 7 for c, _, _ in caixas}
        (conj,), info = self.importar('Curta.dxf', caixas, cores)
        self.assertEqual(info['portas'], 1)
        grupo, = addon.portas._portas_do_conjunto(conj)
        self.assertEqual(grupo['porta_parametros']['abertura'], 'GIRO')
        self.assertEqual(grupo['porta_parametros']['dobradica_lado'], 'ESQUERDA')

    def test_promob_junta_sem_apoio_usa_a_lateral_externa(self):
        caixas = [p for p in self.CORPO_400 if p[0] != 'LAYER1'] + [
            ('F', (5, 0, 5), (395, 15, 695)),
            ('D1', (10, 14, 94), (33, 57, 146)),
            ('P1', (10, 15, 99), (41, 17, 141)),
            ('D2', (10, 14, 524), (33, 57, 576)),
            ('P2', (10, 15, 529), (41, 17, 571))]
        cores = {c: 253 if c[0] in ('D', 'P') else 7 for c, _, _ in caixas}
        (conj,), info = self.importar('Apoio.dxf', caixas, cores)
        self.assertEqual(info['portas'], 1)
        grupo, = addon.portas._portas_do_conjunto(conj)
        self.assertEqual(grupo['porta_parametros']['dobradica_lado'], 'DIREITA')
        self.assertTrue(all(r.matrix_world.translation.x * 1000 > 380
                            for r in grupo.children if r.get('cabinet_peca') == 'raiz'))

    def test_folha_de_canto_acompanha_apoio_e_conserva_referencia_fechada(self):
        conj, primeira = self._porta_promob_girada(0)
        folha, = addon.portas._folhas_portas(primeira)
        segunda = addon.portas.porta_no_modulo(conj, folhas=1)
        addon.portas.vincular_folha_de_apoio(segunda, folha, conj)
        filha, = addon.portas._folhas_portas(segunda)
        fechada = addon.ferragens._matriz_fechada(filha)
        addon.ferragens._definir_abertura(bpy.context, folha, .5)
        self.assertGreater((filha.matrix_world.translation - fechada.translation).length, .1)
        self.assertLess((addon.ferragens._matriz_fechada(filha).translation - fechada.translation).length, 1e-6)
        addon.portas.atualizar_portas_do_conjunto(conj)
        self.assertGreater((filha.matrix_world.translation - fechada.translation).length, .1)
        addon.ferragens._definir_abertura(bpy.context, folha, 0)
        self.assertLess((filha.matrix_world.translation - fechada.translation).length, 1e-6)

    def _canto_cego(self):
        # Regressao: 40/15 < 3 era descartado como ferragem e 49,9998 < 50
        # apagava o arremate. Sem apoio o painel fixo virava articulacao.
        caixas = [('L',(0,15,0),(15,365,706)),('R',(785,15,0),(800,365,706)),
                  ('B',(15,15,3),(785,365,18)),('T',(15,15,688),(785,365,703)),
                  ('A',( -3,0,0),(433,15,706)),
                  ('Rip',(415,15,18),(430,55,688)),
                  ('Arr',(335,-49.9998,3),(350,0,703)),
                  ('F',(432,0,13),(795,15,693))]
        for i,z in enumerate((113,593)):
            caixas += [('H%d'%i,(437,14,z-26),(460,57,z+26)),
                       ('HP%d'%i,(442,15,z-21),(473,17,z+21))]
        cores={n:253 if n.startswith('H') else 7 for n,_,_ in caixas}
        (conj,),info=self.importar('CantoCego.dxf',caixas,cores)
        return conj, info

    def test_canto_cego_preserva_ripas_e_arremate_com_dobradica_de_movel(self):
        conj, info = self._canto_cego()
        self.assertEqual(info['portas'],1)
        chapas=addon.modulos._chapas_do_conjunto(conj)
        nomes={o.name for o in chapas}
        self.assertIn('Peca Rip',nomes)
        self.assertIn('Peca Arr',nomes)
        self.assertIn('Peca A',nomes)
        grupo,=addon.portas._portas_do_conjunto(conj)
        self.assertFalse(grupo['porta_parametros'].get('dobradica_articulada'))
        self.assertFalse(grupo.get('porta_apoio_folha'))
        folha,=addon.portas._folhas_portas(grupo)
        self.assertFalse(any('Articulada' in o.name for o in grupo.children_recursive))
        self.assertTrue(any(o.get('cabinet_peca')=='cabeca'
                            for o in grupo.children_recursive))
        arremate=next(o for o in chapas if o.name=='Peca A')
        ripa=next(o for o in chapas if o.name=='Peca Rip')
        self.assertAlmostEqual((limites([folha])[0][0]-limites([arremate])[1][0])*1000,2,delta=.02)
        self.assertAlmostEqual((limites([ripa])[0][1]-limites([folha])[1][1])*1000,2,delta=.02)
        a=folha.matrix_world.copy()
        addon.ferragens._definir_abertura(bpy.context,folha,.7)
        bpy.context.view_layer.update()
        self.assertGreater((folha.matrix_world.translation-a.translation).length,.05)
        addon.ferragens._definir_abertura(bpy.context,folha,0)
        bpy.context.view_layer.update()
        self.assertLess((folha.matrix_world.translation-a.translation).length,1e-6)

    def test_porta_parcial_segue_ripa_e_lateral_ao_reduzir_largura(self):
        conj, _ = self._canto_cego()
        grupo, = addon.portas._portas_do_conjunto(conj)
        folha, = addon.portas._folhas_portas(grupo)
        ripa = next(o for o in conj.children if o.name == 'Peca Rip')
        inicio = conj.conj_largura_mm
        matriz = folha.matrix_world.copy()
        largura = folha.chapa_largura_mm
        gap = (limites([folha])[0][0]-limites([ripa])[1][0])*1000
        # Preset antigo sem referencia: a migracao acontece ANTES de mover
        # a ripa e so' uma vez, nao durante desenho/abertura.
        for k in list(grupo.keys()):
            if k.startswith('porta_vao_') and k not in ('porta_vao_largura_mm','porta_vao_altura_mm'):
                del grupo[k]
        for medida in (inicio-160, inicio-250, inicio):
            conj.conj_largura_mm = medida
            bpy.context.view_layer.update()
            self.assertAlmostEqual((limites([folha])[0][0]-limites([ripa])[1][0])*1000,gap,delta=.05)
        self.assertAlmostEqual(folha.chapa_largura_mm,largura,delta=.05)
        self.assertLess((folha.matrix_world.translation-matriz.translation).length,.00005)
        addon.ferragens._definir_abertura(bpy.context,folha,.5)
        addon.ferragens._definir_abertura(bpy.context,folha,0)
        self.assertLess((folha.matrix_world.translation-matriz.translation).length,.00005)

    def test_ancora_da_porta_no_meio_da_face_usa_interpolacao_nativa(self):
        conj, _ = self._canto_cego()
        grupo, = addon.portas._portas_do_conjunto(conj)
        # Vao parcial em altura, longe dos vertices da lateral.
        grupo.matrix_world.translation.z += .2
        grupo['porta_vao_altura_mm'] = 300
        bpy.context.view_layer.update()
        addon.portas.gravar_vao_orientado(grupo,conj)
        self.assertTrue(grupo.get('porta_vao_face_0'))
        ripa=grupo['porta_vao_apoio_0']
        self.assertEqual(ripa.name,'Peca Rip')
        inicio=addon.portas._vao_orientado(grupo,conj)[2].translation
        m=ripa.matrix_world.copy();m.translation.x+=.03;ripa.matrix_world=m
        bpy.context.view_layer.update()
        depois=addon.portas._vao_orientado(grupo,conj)[2].translation
        self.assertAlmostEqual(depois.x-inicio.x,.03,places=5)
        self.assertAlmostEqual(depois.z,inicio.z,places=5)

    def test_dobradica_reta_real_na_porta_parcial_cabe_na_folha(self):
        conj, _ = self._canto_cego()
        grupo, = addon.portas._portas_do_conjunto(conj)
        folha, = addon.portas._folhas_portas(grupo)
        inv = folha.matrix_world.inverted()
        lo = Vector(tuple(min(v.co[k] for v in folha.data.vertices) for k in range(3)))
        hi = Vector(tuple(max(v.co[k] for v in folha.data.vertices) for k in range(3)))
        grafo = bpy.context.evaluated_depsgraph_get()
        copos = [o for o in grupo.children_recursive if o.type=='MESH' and o.name.startswith('Dobradica Copo')]
        self.assertEqual(len(copos),2)
        for obj in copos:
            avaliado = obj.evaluated_get(grafo)
            malha = avaliado.to_mesh()
            try:
                for v in malha.vertices:
                    p = inv @ (obj.matrix_world @ v.co)
                    self.assertTrue(all(lo[k]-.0001 <= p[k] <= hi[k]+.0001 for k in (0,1)))
                    self.assertLessEqual(p.z,hi.z+.0001)
            finally:
                avaliado.to_mesh_clear()

    def test_canto_real_reduz_largura_em_etapas_sem_perder_referencia(self):
        if bpy.app.version < (5,):
            self.skipTest('Preset gravado no Blender 5.x')
        lib=os.path.join(os.path.dirname(os.path.dirname(__file__)),'cabinet_creator','biblioteca')
        ns,_,erro=addon.biblioteca.inserir_preset(bpy.context,lib,
            'Canto_Sup_Medio_01_800x706x800.blend','modulo')
        self.assertFalse(erro)
        conj=next(o for o in ns if addon.chapas.MARCA_CONJUNTO in o)
        pontos={o:[o.matrix_world@v.co for v in o.data.vertices]
                for o in addon.modulos._chapas_do_conjunto(conj)}
        largura=conj.conj_largura_mm
        for valor in (largura-100,largura-200,largura):
            conj.conj_largura_mm=valor
            bpy.context.view_layer.update()
        for obj,vs in pontos.items():
            self.assertLess(max((obj.matrix_world@v.co-p).length for v,p in zip(obj.data.vertices,vs)),.00005)

    def test_promob_folhas_articuladas_seguem_o_apoio_sem_ferragem_flutuante(self):
        caixas = [('LAYER1', (0, 15, 0), (15, 565, 700)),
                  ('LAYER2', (785, 15, 0), (800, 565, 700)),
                  ('LAYER3', (15, 15, 0), (785, 565, 15)),
                  ('LAYER4', (15, 15, 685), (785, 565, 700)),
                  ('F1', (5, 0, 5), (399, 15, 695)),
                  ('F2', (401, 0, 5), (795, 15, 695))]
        for lado, x in [('E', 10), ('M', 406)]:
            for i, z in enumerate((120, 550)):
                caixas += [(lado + str(i), (x, 14, z - 26), (x + 23, 57, z + 26)),
                           (lado + str(i) + 'P', (x, 15, z - 21), (x + 31, 17, z + 21))]
        cores = {c: 7 if c.startswith(('LAYER', 'F')) else 253 for c, _, _ in caixas}
        (conj,), info = self.importar('Articulada.dxf', caixas, cores)
        self.assertEqual(info['portas'], 2)
        grupos = addon.portas._portas_do_conjunto(conj)
        secundaria, = [g for g in grupos if g.get('porta_apoio_folha')]
        apoio = secundaria['porta_apoio_folha']
        self.assertTrue(secundaria['porta_parametros']['dobradica_articulada'])
        corpos = [o for o in secundaria.children if o.get(addon.ferragens.CHAVE_FERRAGEM) == 'DOBRADICA' and 'Placa Apoio' in o.name]
        self.assertEqual(len(corpos), 2)
        # Pelo menos uma face da placa nativa toca a folha de apoio.
        inversa = apoio.matrix_world.inverted()
        for corpo in corpos:
            distancias = [apoio.closest_point_on_mesh(inversa @ (corpo.matrix_world @ v.co))
                          for v in corpo.data.vertices]
            self.assertTrue(any(hit and (inversa @ (corpo.matrix_world @ v.co) - p).length < .003
                                for v, (hit, p, n, face) in zip(corpo.data.vertices, distancias)))
        folha, = addon.portas._folhas_portas(secundaria)
        antes = folha.matrix_world.translation.copy()
        addon.ferragens._definir_abertura(bpy.context, apoio, .5)
        self.assertGreater((folha.matrix_world.translation - antes).length, .1)
        nomes = {o.name for o in addon.ferragens._ferragens_portas(secundaria)}
        self.assertTrue(nomes.isdisjoint(o.name for o in addon.ferragens._ferragens_portas(apoio.parent)))
        addon.portas.atualizar_portas_do_conjunto(conj)
        self.assertEqual(nomes, {o.name for o in addon.ferragens._ferragens_portas(secundaria)})

    def test_promob_cadeia_da_direita_inverte_apoio_para_esquerda(self):
        caixas=[('LAYER1',(0,15,0),(15,565,700)),('LAYER2',(785,15,0),(800,565,700)),
                ('LAYER3',(15,15,0),(785,565,15)),('LAYER4',(15,15,685),(785,565,700)),
                ('F1',(5,0,5),(399,15,695)),('F2',(401,0,5),(795,15,695))]
        for lado,x in [('D',767),('M',367)]:
            for i,z in enumerate((120,550)):
                caixas += [(lado+str(i),(x,14,z-26),(x+23,57,z+26)),
                           (lado+str(i)+'P',(x,15,z-21),(x+31,17,z+21))]
        cores={c:7 if c.startswith(('LAYER','F')) else 253 for c,lo,hi in caixas}
        (conj,),info=self.importar('CadeiaDireita.dxf',caixas,cores)
        grupos=addon.portas._portas_do_conjunto(conj)
        raiz,=[g for g in grupos if not g.get('porta_apoio_folha')]
        secundaria,=[g for g in grupos if g.get('porta_apoio_folha')]
        self.assertEqual(raiz['porta_parametros']['dobradica_lado'],'ESQUERDA')
        folha=addon.portas._folhas_portas(raiz)[0]
        outra=addon.portas._folhas_portas(secundaria)[0]
        self.assertLess(folha.matrix_world.translation.x,outra.matrix_world.translation.x)
        self.assertEqual(secundaria['porta_apoio_folha'],folha)
        inversa=folha.matrix_world.inverted()
        corpos=[o for o in secundaria.children if 'Placa Apoio' in o.name]
        self.assertTrue(corpos)
        for corpo in corpos:
            self.assertLess(min((inversa@(corpo.matrix_world@v.co)-folha.closest_point_on_mesh(inversa@(corpo.matrix_world@v.co))[1]).length
                                for v in corpo.data.vertices),.003)
        antes=outra.matrix_world.translation.copy()
        addon.ferragens._definir_abertura(bpy.context,folha,.5)
        self.assertGreater((outra.matrix_world.translation-antes).length,.1)
        addon.ferragens._definir_abertura(bpy.context,folha,0)
        addon.portas.atualizar_portas_do_conjunto(conj)
        self.assertEqual(secundaria['porta_apoio_folha'],folha)
        self.assertFalse(addon.portas.preferir_esquerda_no_modulo(bpy.context,conj))

    def test_promob_dois_apoios_na_junta_nao_criam_ciclo(self):
        caixas = [('LAYER1', (0, 15, 0), (15, 565, 700)),
                  ('LAYER2', (785, 15, 0), (800, 565, 700)),
                  ('LAYER3', (15, 15, 0), (785, 565, 15)),
                  ('LAYER4', (15, 15, 685), (785, 565, 700)),
                  ('F1', (5, 0, 5), (399, 15, 695)),
                  ('F2', (401, 0, 5), (795, 15, 695))]
        for lado, x in [('E', 367), ('D', 406)]:
            for i, z in enumerate((120, 550)):
                caixas += [(lado + str(i), (x, 14, z - 26), (x + 23, 57, z + 26)),
                           (lado + str(i) + 'P', (x, 15, z - 21), (x + 31, 17, z + 21))]
        cores = {c: 7 if c.startswith(('LAYER', 'F')) else 253 for c, _, _ in caixas}
        (conj,), info = self.importar('SemCiclo.dxf', caixas, cores)
        self.assertEqual(info['portas'], 1)
        grupo, = addon.portas._portas_do_conjunto(conj)
        self.assertEqual(grupo['porta_parametros']['folhas'], 2)
        self.assertNotIn('porta_apoio_folha', grupo)

    def test_promob_pilha_com_caixa_vira_gavetas_nativas(self):
        caixas = list(self.CORPO_400)
        frentes = ((5, 230), (235, 460), (465, 695))
        for i, (z0, z1) in enumerate(frentes):
            caixas.append(('LAYER1%d' % i, (5, 0, z0), (395, 15, z1)))
            # a caixa do Promob nasce DENTRO da frente (y 12): encosta nela
            caixas += [('LAYER2%d' % i, (28, 12, z0 + 20), (43, 500, z0 + 150)),
                       ('LAYER3%d' % i, (357, 12, z0 + 20), (372, 500, z0 + 150)),
                       ('LAYER4%d' % i, (43, 15, z0 + 20), (357, 30, z0 + 150)),
                       ('LAYER5%d' % i, (28, 12, z0 + 14), (372, 500, z0 + 20))]
        modulos, info = self.importar('Gaveteiros.dxf', caixas, {c: 7 for c, _l, _h in caixas})
        conj, = modulos
        self.assertEqual(info['gavetas'], 1, info)
        # a caixa do Promob saiu: o modulo e' so' o corpo
        self.assertEqual(len(addon.modulos._chapas_do_conjunto(conj)), 4)
        grupo, = addon.gavetas.grupos_do_modulo(conj)
        p = addon.gavetas.parametros(grupo)
        self.assertEqual((p['quantidade'], p['cobertura'], p['trilho']),
                         (3, 'SOBREPOSTA', 'TELESCOPICO'))
        # as alturas DESIGUAIS do Promob ficam (proporcao), e as frentes
        # nascem onde estavam
        alturas = [addon.gavetas.frente_da_gaveta(g).chapa_comprimento_mm
                   for g in addon.gavetas.gavetas_do_grupo(grupo)]
        self.assertAlmostEqual(alturas[2] / alturas[0], 230.0 / 225.0, places=2)
        frente = addon.gavetas.frente_da_gaveta(addon.gavetas.gavetas_do_grupo(grupo)[0])
        self.assertAlmostEqual(frente.chapa_largura_mm, 390.0, delta=1.0)

    def test_promob_quadro_de_aluminio_vira_correr_com_trilho_nosso(self):
        caixas = [
            ('LAYER1', (0, 0, 0), (15, 550, 1356)), ('LAYER2', (1185, 0, 0), (1200, 550, 1356)),
            ('LAYER3', (15, 0, 3), (1185, 550, 18)), ('LAYER4', (15, 0, 1338), (1185, 550, 1353)),
            ('LAYER5', (15, 0, 18), (1185, 60, 24)),           # trilho de baixo (6 mm)
            ('LAYER6', (15, 0, 1298), (1185, 80, 1338)),       # trilho de cima
            ('LAYER7', (16, 7, 26), (616, 30, 1320)),          # quadros de 23
            ('LAYER8', (599, 37, 26), (1184, 60, 1320)),
            ('LAYER9', (21, 13, 32), (609, 18, 1314)),         # vidro de 5
        ]
        cores = {c: 7 for c, _l, _h in caixas}
        cores.update(LAYER5=253, LAYER6=253, LAYER7=254, LAYER8=254, LAYER9=254)
        modulos, info = self.importar('Despenseiros.dxf', caixas, cores)
        conj, = modulos
        self.assertEqual(info['correr'], 1, info)
        # o trilho de 6 mm passava como chapa: agora e' ferragem e sai
        self.assertEqual(sorted(round(c.chapa_espessura_mm) for c in
                                addon.modulos._chapas_do_conjunto(conj)), [15, 15, 15, 15])
        grupo, = addon.portas._portas_do_conjunto(conj)
        p = dict(grupo['porta_parametros'])
        self.assertEqual((p['abertura'], p['folhas'], p['folha']), ('CORRER', 2, 'QUADRO'))
        for folha in addon.portas._folhas_portas(grupo):
            self.assertAlmostEqual(folha.chapa_espessura_mm, 23.0, places=3)
            self.assertIn('chapa_quadro_mm', folha)

    def test_promob_travessas_do_topo_viram_dependentes(self):
        caixas = self.CORPO_400[:3] + [
            ('LAYER4', (15, 15, 685), (385, 85, 700)),          # travessa da frente
            ('LAYER5', (15, 495, 685), (385, 565, 700)),        # e a de tras
        ]
        modulos, _info = self.importar('Balcoes.dxf', caixas, {c: 7 for c, _l, _h in caixas})
        conj, = modulos
        lados = sorted(t[addon.modulos.CHAVE_LADO_TRAVESSA]
                       for t in addon.modulos.travessas_do_modulo(conj))
        self.assertEqual(lados, ['FRENTE', 'TRAS'])
        # a travessa refeita pela caixa: entre as laterais, E do modulo
        for t in addon.modulos.travessas_do_modulo(conj):
            self.assertAlmostEqual(t.chapa_largura_mm, 370.0, places=1)
            self.assertAlmostEqual(t.chapa_espessura_mm, 15.0, places=1)
        # o modulo continua 400 x 700 (sem crescer pela travessa)
        self.assertAlmostEqual(conj.conj_largura_mm, 400.0, places=1)
        self.assertAlmostEqual(conj.conj_altura_mm, 700.0, places=1)

    def test_promob_vao_sem_chapa_entre_gavetas_e_porta(self):
        # gavetas embaixo de uma basculante, sem travessa entre elas: o
        # vao das gavetas para na frente delas (menos a cobertura dos
        # lados), nao sobe ate' o tampo (`promob.vao_atras`)
        P = addon.promob
        corpo = [P.peca(None, (0, 15, 0), (15, 565, 1356), 0),
                 P.peca(None, (785, 15, 0), (800, 565, 1356), 0),
                 P.peca(None, (15, 15, 3), (785, 565, 18), 2),
                 P.peca(None, (15, 15, 1338), (785, 565, 1353), 2)]
        pilha = {'lo': [5, 0, 13], 'hi': [795, 15, 1007]}
        x0, x1, z0, z1 = P.vao_atras(corpo, pilha, 15.0, 565.0)
        self.assertEqual((x0, x1, z0), (15, 785, 18))
        self.assertAlmostEqual(z1, 1007 - 10.0, places=3)

    def test_promob_base_e_tampo_encostam_na_quina_sem_alterar_sistemas(self):
        caixas = [
            ('LAYER1', (0, 15, 0), (15, 565, 700)),
            ('LAYER2', (385, 15, 0), (400, 565, 700)),
            ('LAYER3', (15, 15, 3), (385, 565, 18)),
            ('LAYER4', (15, 15, 682), (385, 565, 697)),
            ('LAYER5', (15, 15, 350), (385, 565, 365)),
            ('LAYER6', (5, 0, 5), (395, 15, 695)),
            ('LAYER7', (367, 14, 100), (390, 57, 152)),
        ]
        cores = {c: 7 for c, _l, _h in caixas}
        cores['LAYER7'] = 253
        (conj,), info = self.importar('Encaixes.dxf', caixas, cores)
        self.assertEqual(info['portas'], 1)
        placas = addon.modulos._chapas_do_conjunto(conj)
        placas += [o for g in addon.prateleiras.grupos_do_modulo(conj) for o in addon.prateleiras.prateleiras_do_grupo(g)]
        horizontais = [c for c in placas if abs(c.matrix_world.to_3x3().col[2].normalized().z) > .999]
        alturas = sorted(tuple(round(v * 1000, 2) for v in (limites([c])[0][2], limites([c])[1][2]))
                          for c in horizontais)
        self.assertEqual(alturas, [(0, 15), (350, 365), (685, 700)])
        self.assertEqual(tuple(round(v) for v in (conj.conj_largura_mm, conj.conj_altura_mm,
                                                 conj.conj_profundidade_mm)), (400, 700, 550))
        self.assertEqual(addon.promob.ajustar_encaixes(conj), [])

    def test_encaixe_preserva_recortes_uid_portas_e_recuos_maiores(self):
        import tempfile
        caminho = os.path.join(tempfile.mkdtemp(), 'Curva.dxf')
        vs, fs = base_em_l(z=3)
        dxf_promob(caminho, [('LAYER1', _faces_da_caixa((0, 0, 0), (15, 600, 700))),
                            ('LAYER2', _faces_da_caixa((15, 0, 670), (600, 600, 685)))],
                   [('LAYER3', vs, fs)])
        (conj,), _ = addon.importacao.importar_dxf_promob(bpy.context, caminho, 'Teste')
        base = next(c for c in addon.modulos._chapas_do_conjunto(conj)
                    if not addon.chapas._malha_e_caixa(c.data))
        self.assertEqual(len(base.data.vertices), 12)
        self.assertAlmostEqual(limites([base])[0][2], 0, places=5)
        self.assertAlmostEqual(base.chapa_espessura_mm, 15, places=3)
        conj.rotation_euler = (.2, .3, .7)
        bpy.context.view_layer.update()
        uid = base['chapa_uid']
        # Recriar so' o recuo de 3 no eixo Z do modulo girado.
        m = base.matrix_world.copy()
        m.translation += conj.matrix_world.to_3x3() @ Vector((0, 0, .003))
        base.matrix_world = m
        bpy.context.view_layer.update()
        antes = [v.co.copy() for v in base.data.vertices]
        ajustes = addon.promob.ajustar_encaixes(conj)
        self.assertEqual(len(ajustes), 1)
        self.assertEqual(base['chapa_uid'], uid)
        self.assertTrue(all((v.co - co).length < 1e-7 for v, co in zip(base.data.vertices, antes)))
        inv = conj.matrix_world.inverted()
        self.assertAlmostEqual(min((inv @ (base.matrix_world @ v.co)).z for v in base.data.vertices), 0, places=5)


    def test_promob_gavetas_na_face_lateral_tem_selecao_abertura_e_edicao(self):
        import tempfile
        caixas = list(self.CORPO_400)
        for i, (z0, z1) in enumerate(((5, 230), (235, 460), (465, 695))):
            caixas += [('F%d' % i, (5, 0, z0), (395, 15, z1)),
                ('E%d' % i, (28, 15, z0+20), (43, 330, z0+150)),
                ('D%d' % i, (357, 15, z0+20), (372, 330, z0+150)),
                ('T%d' % i, (28, 320, z0+20), (372, 335, z0+150)),
                ('B%d' % i, (28, 15, z0+14), (372, 330, z0+20))]
        r = Matrix.Rotation(math.pi/2, 3, 'Z')
        path = os.path.join(tempfile.mkdtemp(), 'Ilha.dxf')
        dxf_promob(path, [(nome, [[tuple(r @ Vector(v)) for v in f] for f in _faces_da_caixa(lo, hi)]) for nome, lo, hi in caixas],
                    cores={nome:7 for nome, lo, hi in caixas})
        (conj,), info = addon.importacao.importar_dxf_promob(bpy.context, path, 'Ilha')
        self.assertEqual(info['gavetas'], 1)
        grupo, = addon.gavetas.grupos_do_modulo(conj)
        gs = addon.gavetas.gavetas_do_grupo(grupo)
        self.assertEqual(len(gs), 3)
        self.assertEqual([round(addon.gavetas.frente_da_gaveta(g).chapa_comprimento_mm)
                          for g in gs], [225, 225, 230])
        self.assertEqual(len(addon.modulos._chapas_do_conjunto(conj)), 4)
        for g in gs:
            frente = addon.gavetas.frente_da_gaveta(g)
            self.assertTrue(addon.gavetas.selecionar(bpy.context, frente, 'GRUPO'))
            self.assertEqual(bpy.context.object, grupo)
            antes = frente.matrix_world.translation.copy()
            addon.gavetas.definir_abertura(g, 1)
            bpy.context.view_layer.update()
            self.assertGreater((frente.matrix_world.translation - antes).dot(r @ Vector((0,-1,0))), .2)
            self.assertEqual(len([o for o in g.children if addon.chapas.MARCA_PUXADOR in o or any(addon.chapas.MARCA_PUXADOR in c for c in o.children)]), 1)
        a = addon.gavetas.medidas(grupo)[1]
        conj.name += ' renomeada'
        addon.gavetas.atualizar_gavetas_do_conjunto(conj)
        self.assertIsNone(addon.gavetas.editar(bpy.context, grupo, 'entre_gavetas_mm', 5))
        self.assertAlmostEqual(addon.gavetas.medidas(grupo)[1], a, places=3)
        self.assertEqual(len(addon.gavetas.parametros(grupo)['coberturas_mm']), 4)
        self.assertIsNone(addon.gavetas.editar(bpy.context, grupo, 'folga_frontal_mm', 2))
        self.assertFalse(addon.gavetas.parametros(grupo)['coberturas_mm'])

    def test_promob_lateral_inteira_nao_vira_gaveta_e_metais_so_referenciam(self):
        caixas = list(self.CORPO_400) + [('F', (5,0,500),(395,15,695)),
            ('E', (28,15,520),(43,330,670)), ('D', (357,15,520),(372,330,670)),
            ('B', (28,15,514),(372,330,520)), ('T', (28,320,520),(372,335,670))]
        # Caixa metalica tambem informa gaveta; trilhos gerados sao nossos.
        cores = {n: (254 if n in ('E','D') else 7) for n,lo,hi in caixas}
        (conj,), info = self.importar('Mista.dxf', caixas, cores)
        grupo, = addon.gavetas.grupos_do_modulo(conj)
        self.assertEqual(addon.gavetas.parametros(grupo)['quantidade'], 1)
        self.assertAlmostEqual(addon.gavetas.frente_da_gaveta(addon.gavetas.gavetas_do_grupo(grupo)[0]).chapa_comprimento_mm,195,delta=1)
        self.assertTrue(all(o.name not in ('Peca E','Peca D') for o in conj.children_recursive))

    def test_promob_prateleiras_adotam_uid_material_forma_e_funcoes(self):
        # As prateleiras avancam 5 mm alem do corpo: adotar nao pode
        # trocar o referencial do vao e desloca-las para tras.
        caixas = list(self.CORPO_400) + [('P1',(15,10,200),(385,540,215)), ('P2',(15,10,450),(385,540,465))]
        (conj,), info = self.importar('Prateleiras.dxf', caixas, {n:7 for n,lo,hi in caixas})
        self.assertEqual(info['prateleiras'], 1)
        grupo, = addon.prateleiras.grupos_do_modulo(conj)
        pecas = addon.prateleiras.prateleiras_do_grupo(grupo)
        uids = [p.get('chapa_uid') for p in pecas]
        self.assertTrue(all(uids))
        self.assertEqual([round(p.matrix_world.translation.z*1000) for p in pecas], [208,458])
        conj.name += ' novo'
        self.assertEqual(addon.prateleiras.modulo_do_grupo(grupo), conj)
        addon.prateleiras.selecionar(bpy.context, pecas[0], 'GRUPO')
        self.assertEqual(bpy.context.object, grupo)
        self.assertIsNone(addon.prateleiras.editar(bpy.context, grupo, 'vao_0', 230))
        self.assertEqual([p.get('chapa_uid') for p in addon.prateleiras.prateleiras_do_grupo(grupo)], uids)
        self.assertAlmostEqual(pecas[0].matrix_world.translation.z, .2525, places=3)
        self.assertAlmostEqual(limites(pecas)[0][1], .010, places=4)
        self.assertAlmostEqual(limites(pecas)[1][1], .540, places=4)

    def test_promob_prateleira_recortada_preserva_malha_material_e_edicao(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), 'Recortada.dxf')
        vs, fs = base_em_l(z=300)
        dxf_promob(path, [('L', _faces_da_caixa((0,0,0),(15,600,700))),
                         ('B', _faces_da_caixa((15,0,0),(600,600,15))),
                         ('T', _faces_da_caixa((15,0,685),(600,600,700)))],
                   [('P', vs, fs)])
        (conj,), info = addon.importacao.importar_dxf_promob(bpy.context, path, 'Recorte')
        grupo, = addon.prateleiras.grupos_do_modulo(conj)
        obj, = addon.prateleiras.prateleiras_do_grupo(grupo)
        self.assertFalse(addon.chapas._malha_e_caixa(obj.data))
        self.assertEqual(len(obj.data.vertices), 12)
        material = bpy.data.materials.new('Madeira recortada')
        obj.data.materials.append(material)
        obj.material_slots[0].link = 'OBJECT'
        obj.material_slots[0].material = material
        uid = obj['chapa_uid']
        antes = [v.co.copy() for v in obj.data.vertices]
        self.assertIsNone(addon.prateleiras.editar(bpy.context, grupo, 'vao_0', 330))
        self.assertEqual(obj['chapa_uid'], uid)
        self.assertEqual(obj.material_slots[0].material, material)
        self.assertTrue(all((v.co-co).length < 1e-6 for v,co in zip(obj.data.vertices,antes)))
        self.assertAlmostEqual(limites([obj])[0][2], .345, places=4)

    def test_promob_frente_alta_estreita_com_caixas_em_dois_niveis(self):
        caixas = [('L',(0,15,0),(15,565,700)),('D',(185,15,0),(200,565,700)),
                  ('B',(15,15,0),(185,565,15)),('T',(15,15,685),(185,565,700)),
                  ('F',(5,0,5),(195,15,695))]
        for i,z in enumerate((40,390)):
            caixas += [('E%d'%i,(28,15,z),(43,515,z+150)),
                       ('D%d'%i,(157,15,z),(172,515,z+200)),
                       ('B%d'%i,(38,25,z+10),(162,505,z+25)),
                       ('T%d'%i,(43,500,z),(157,515,z+200))]
        (conj,), info = self.importar('PortaTemperos.dxf',caixas,{n:7 for n,l,h in caixas})
        grupo, = addon.gavetas.grupos_do_modulo(conj)
        self.assertEqual(addon.gavetas.parametros(grupo)['quantidade'],1)
        self.assertFalse(addon.prateleiras.grupos_do_modulo(conj))
        self.assertEqual(len(addon.modulos._chapas_do_conjunto(conj)),4)

    def test_promob_caixa_curva_inclui_fundo_que_avanca_das_laterais(self):
        P = addon.promob
        frente = P.peca(None,(5,0,5),(395,80,230),curva=True,espessura=15)
        corpo = [P.peca(None,(0,80,0),(15,600,700),0),
                 P.peca(None,(385,80,0),(400,600,700),0),
                 P.peca(None,(15,80,0),(385,600,15),2),
                 P.peca(None,(28,70,25),(43,550,200),0),
                 P.peca(None,(357,70,25),(372,550,200),0),
                 P.peca(None,(38,30,35),(362,540,50),2),
                 P.peca(None,(43,25,25),(357,85,200),curva=True,espessura=15)]
        caixa = P._caixa_de_gaveta(frente,corpo,600)
        self.assertIn(corpo[-2],caixa)
        self.assertIn(corpo[-1],caixa)
        self.assertNotIn(corpo[2],caixa)


    def test_canto_preserva_os_dois_fundos_e_prateleira_sem_alargamento(self):
        caixas=[('L1',(0,0,0),(15,600,700)),('L2',(585,0,0),(600,600,700)),
                ('B',(15,0,0),(585,600,15)),('T',(15,0,685),(585,600,700)),
                ('FX',(18,10,10),(24,510,690)),('FY',(83,576,10),(590,582,690)),
                ('P',(24,20,350),(580,570,365))]
        (conj,),_=self.importar('FundosEmL.dxf',caixas,{n:7 for n,l,h in caixas})
        fundos=addon.modulos.fundos_do_modulo(conj)
        self.assertEqual(len(fundos),2)
        inv=conj.matrix_world.inverted()
        antes={o.name:[inv @ (o.matrix_world@v.co) for v in o.data.vertices] for o in fundos}
        addon.modulos.ajustar_fundo(conj);bpy.context.view_layer.update()
        for o in fundos:
            self.assertIn('fundo_margens_mm',o)
            self.assertLess(max(((inv@(o.matrix_world@v.co))-p).length for p,v in zip(antes[o.name],o.data.vertices)),1e-6)
        grupo,=addon.prateleiras.grupos_do_modulo(conj)
        self.assertGreater(addon.prateleiras.parametros(grupo)['profundidade_mm'],500)

    def test_encaixe_da_base_reconecta_as_divisorias_internas(self):
        caixas=[('L',(0,0,0),(15,550,700)),('D',(585,0,0),(600,550,700)),
                ('B',(15,0,3),(585,550,18)),('T',(15,0,682),(585,550,697)),
                ('Div',(290,0,18),(305,550,682))]
        (conj,),_=self.importar('Divisoria.dxf',caixas,{n:7 for n,l,h in caixas})
        obj=next(o for o in addon.modulos._chapas_do_conjunto(conj) if o.name.startswith('Peca Div'))
        self.assertAlmostEqual(limites([obj])[0][2],.015,places=5)
        self.assertAlmostEqual(limites([obj])[1][2],.685,places=5)
        self.assertAlmostEqual(obj.chapa_espessura_mm,15,places=3)
        self.assertFalse(addon.promob.ajustar_encaixes(conj))

    def test_curva_com_placas_vira_porta_nativa_preservando_a_malha(self):
        import tempfile
        contorno=[(595-r*math.cos(i*math.pi/32),r*math.sin(i*math.pi/32))
                  for r,indices in ((245,range(17)),(230,range(16,-1,-1))) for i in indices]
        vs=[(x,y,z) for z in (5,695) for x,y in contorno];n=len(contorno)
        # Polyface DXF admite so' quatro indices por face.
        fs=[(i,i+1,n-2-i,n-1-i) for i in range(16)]
        fs += [(n+i,2*n-1-i,2*n-2-i,n+i+1) for i in range(16)]
        fs += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
        caixas=[('L',(0,-15,0),(350,0,700)),('D',(585,245,0),(600,600,700)),
                ('B',(0,0,0),(585,600,15)),('T',(0,0,685),(585,600,700)),
                ('H1',(558,245,100),(589,247,142)),('H2',(558,245,550),(589,247,592))]
        caminho=os.path.join(tempfile.mkdtemp(),'CurvaFuncional.dxf')
        dxf_promob(caminho,[(c,_faces_da_caixa(lo,hi)) for c,lo,hi in caixas],
                   [('F',vs,fs)],cores={**{c:253 if c.startswith('H') else 7 for c,lo,hi in caixas},'F':7})
        (conj,),info=addon.importacao.importar_dxf_promob(bpy.context,caminho,'Curva')
        self.assertEqual(info['portas'],1)
        grupo,=addon.portas._portas_do_conjunto(conj);folha,=addon.portas._folhas_portas(grupo)
        self.assertTrue(folha.get('porta_curva_modelada'))
        self.assertAlmostEqual(folha.chapa_espessura_mm,15,places=2)
        pontos=[folha.matrix_world@v.co for v in folha.data.vertices]
        for v in vs:self.assertLess(min((p-Vector(v)/1000).length for p in pontos),1e-5)
        pux,=[o for o in folha.children if addon.chapas.MARCA_PUXADOR in o]
        self.assertEqual(pux['puxador_tipo'],'ALCA')
        self.assertTrue(pux.get('puxador_curvo'))
        antes=folha.matrix_world.copy()
        addon.ferragens._definir_abertura(bpy.context,folha,.5);bpy.context.view_layer.update()
        self.assertGreater((folha.matrix_world.translation-antes.translation).length,.05)
        addon.ferragens._definir_abertura(bpy.context,folha,0);bpy.context.view_layer.update()
        addon.portas._reaplicar_portas(bpy.context,grupo,dict(grupo['porta_parametros']))
        bpy.context.view_layer.update()
        for p in pontos:self.assertLess(min((folha.matrix_world@v.co-p).length for v in folha.data.vertices),1e-5)
        addon.ferragens._definir_abertura(bpy.context,folha,.35)
        addon.formas._deformar(conj,lambda p:Vector((20,0,0)))
        novos=[p+Vector((.02,0,0)) for p in pontos]
        addon.portas.adotar_contorno_modelado(bpy.context,grupo,novos)
        self.assertAlmostEqual(folha[addon.ferragens.CHAVE_ABERTURA],.35,places=4)
        copos=[o for o in folha.children if o.get(addon.ferragens.CHAVE_FERRAGEM)=='CANECO']
        self.assertTrue(copos)
        zmax=max(v.co.z for v in folha.data.vertices)+.1
        for copo in copos:
            for v in copo.data.vertices:
                p=copo.matrix_basis @ v.co
                hit,frente,_n,_face=folha.ray_cast(Vector((p.x,p.y,zmax)),Vector((0,0,-1)))
                if hit:self.assertLess(p.z,frente.z+.0001)
        addon.ferragens._definir_abertura(bpy.context,folha,0)
        for p in novos:self.assertLess(min((folha.matrix_world@v.co-p).length for v in folha.data.vertices),1e-5)
        self.assertIsNone(addon.formas.forma_do_modulo(conj))
        addon.ferragens._definir_abertura(bpy.context,folha,.35)
        malha=folha.data
        vertices=[tuple(v.co) for v in malha.vertices]
        addon.formas.aplicar(bpy.context,conj,('R',0),250.)
        self.assertIs(folha.data,malha)
        self.assertEqual(vertices,[tuple(v.co) for v in malha.vertices])
        self.assertAlmostEqual(folha[addon.ferragens.CHAVE_ABERTURA],.35,places=4)

addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestImportacao)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de importacao')
