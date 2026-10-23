"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_gavetas_blender.py

Gavetas do movel (pedido do usuario): grupo de gavetas num vao do modulo
-- frente, caixa e trilho (blocagem em tamanho real, telescopico de
padrao) --, a aba propria, a selecao como a da porta (clique = todas,
duplo = uma; so' elas com linha na HUD), o slider de abertura, os 3
pontos com Alt e a quantidade/profundidade/trilho editaveis.

O assistente (cliques, scroll, Alt) e o arraste do slider, com eventos de
verdade, estao em `gui_interacao.py`.
"""
import os
import math
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix, Vector
from bpy_extras import view3d_utils

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

G = addon.gavetas


class TestGavetas(unittest.TestCase):
    def test_segundo_clique_modal_recupera_modulo_do_estado(self):
        w=G.AssistenteDoVao()
        w._w=dict(modulo=self.conj.name,pontos=[Vector((-.382,-.280,.682))],nomes=['Tampo'],
            limites=G._limites(self.conj),p=dict(G.PARAMETROS_PADRAO),etapa='CANTO2',
            ponto_confirmado=(Vector((.382,-.280,.018)),'Base'))
        w._ir=lambda e:w._w.__setitem__('etapa',e)
        self.assertEqual(w.modal(bpy.context,SimpleNamespace(type='TIMER')),{'RUNNING_MODAL'})
        self.assertEqual(w._w['etapa'],'QUANTIDADE')
        self.assertAlmostEqual(w._w['vao'][0],764,places=2)

    def test_confirmacao_da_macro_nativa_restaura_cursor_e_bloqueios(self):
        cursor=bpy.context.scene.cursor;original=cursor.location.copy()
        obj=addon.modulos._chapas_do_conjunto(self.conj)[0]
        w={'etapa':'CANTO2'};G._assistente_gavetas[0]=w
        antes={o.name for o in bpy.data.objects};obj.hide_select=True
        G._snap_criacao[0]=dict(cena=bpy.context.scene.name,cursor=tuple(original),area=0,
                              mostrar_cursor=False,bloqueados=[(obj.name,False)])
        ponto=Vector((.382,-.280,.018));cursor.location=ponto
        try:
            with patch.object(G,'_objeto_do_ponto_criacao',return_value=obj.name):
                self.assertEqual(G.OBJECT_OT_confirmar_ponto_vao.execute(None,bpy.context),{'FINISHED'})
            self.assertLess((w['ponto_confirmado'][0]-ponto).length,1e-6)
            self.assertEqual(w['ponto_confirmado'][1],obj.name)
            self.assertFalse(obj.hide_select)
            self.assertLess((cursor.location-original).length,1e-6)
            self.assertIsNone(G._snap_criacao[0])
            self.assertEqual(antes,{o.name for o in bpy.data.objects})
            self.assertIn(G.OBJECT_OT_marcar_ponto_vao,addon.CLASSES)
        finally:
            G._assistente_gavetas[0]=None;cursor.location=original

    def test_erro_modal_libera_assistente_e_cursor(self):
        w=G.AssistenteDoVao()
        w._w=dict(modulo=self.conj.name,pontos=[Vector((-.382,-.280,.682))],nomes=['Tampo'],
            p=dict(G.PARAMETROS_PADRAO),etapa='CANTO2',ponto_confirmado=(Vector((.382,-.280,.018)),'Base'))
        w._handler=None;w._handler_2d=None;w._timer=None
        w._area=SimpleNamespace(header_text_set=lambda t:None,tag_redraw=lambda:None)
        liberados=[];contexto=SimpleNamespace(window=SimpleNamespace(cursor_modal_restore=lambda:liberados.append(True)))
        G._assistente_gavetas[0]=w._w
        with patch.object(w,'_definir_vao',side_effect=ValueError('Falha de teste')), \
             patch.object(G._eventos,'_redesenhar_viewports',return_value=None):
            with self.assertRaises(ValueError):w.modal(contexto,SimpleNamespace(type='TIMER'))
        self.assertIsNone(G._assistente_gavetas[0])
        self.assertEqual(liberados,[True])

    def test_snap_pendente_nao_projeta_vertices_da_cena(self):
        w=G.AssistenteDoVao();w._w=dict(etapa='CANTO2',snap_pendente=True)
        with patch.object(addon.portas,'_alvos_do_ima',side_effect=AssertionError('Avaliou malhas')), \
             patch.object(view3d_utils,'location_3d_to_region_2d',side_effect=AssertionError('Projetou vertices')):
            for _ in range(100):
                self.assertEqual(w.modal(bpy.context,SimpleNamespace(type='MOUSEMOVE')),{'PASS_THROUGH'})
    def assistente(self, a, b, nomes=('', '')):
        w=G.AssistenteDoVao()
        w._w=dict(modulo=self.conj.name,pontos=[Vector(a),Vector(b)],nomes=list(nomes),
                  limites=G._limites(self.conj),p=dict(G.PARAMETROS_PADRAO),etapa='PROFUNDIDADE')
        w._definir_vao(self.conj)
        return w

    def test_assistente_deduz_frente_lateral_e_a_preserva_ao_editar(self):
        # Simula preset com eixos do Empty diferentes da abertura real.
        rot=Matrix.Rotation(1.57079632679,4,'Z')
        for o in self.conj.children:o.matrix_world=rot@o.matrix_world
        bpy.context.view_layer.update()
        w=self.assistente((.280,-.382,.682),(.280,.382,.018))
        dados,matriz=w._dados()
        self.assertGreater(matriz.to_3x3().col[1].dot(Vector((-1,0,0))),.999)
        self.assertAlmostEqual(w._w['vao'][0],764,places=2)
        margens=G.margens_do_vao(self.conj,*w._w['pontos'],referencial=w._w['referencia'])
        grupo=w._criar_grupo(bpy.context,self.conj,margens,w._w['p'])
        gaveta=G.gavetas_do_grupo(grupo)[0]
        frente=G.frente_da_gaveta(gaveta);antes=frente.matrix_world.translation.copy()
        G.definir_abertura(gaveta,1);bpy.context.view_layer.update()
        self.assertGreater((frente.matrix_world.translation-antes).normalized().dot(Vector((1,0,0))),.999)
        G.definir_abertura(gaveta,0)
        self.assertIsNone(G.editar(bpy.context,grupo,'entre_gavetas_mm',5))
        self.assertGreater(grupo.matrix_world.to_3x3().col[1].dot(Vector((-1,0,0))),.999)

    def test_assistente_deduz_face_oposta_e_modulo_girado(self):
        self.conj.rotation_euler.z=.73;self.conj.location=(1,2,3)
        bpy.context.view_layer.update()
        mundo=self.conj.matrix_world
        w=self.assistente(mundo@Vector((.382,.280,.682)),mundo@Vector((-.382,.280,.018)))
        _,matriz=w._dados()
        self.assertGreater(matriz.to_3x3().col[1].dot(-mundo.to_3x3().col[1]),.999)
        self.assertGreater(matriz.to_3x3().determinant(),.999)

    def test_assistente_gap_usa_frente_interna_e_profundidade_mais_curta(self):
        fundo=addon.modulos.adicionar_fundo(self.conj,bpy.context)
        pr=addon.prateleiras.criar_prateleiras(bpy.context,self.conj,(18,18,18,18,0),
                       dict(quantidade=1,profundidade_mm=540,recuo_mm=30))
        chapa=addon.prateleiras.prateleiras_do_grupo(pr)[0]
        verts=[chapa.matrix_world@v.co for v in chapa.data.vertices]
        alto=Vector((-.382,-.250,max(v.z for v in verts)))
        baixo=Vector((.382,-.280,.018))
        base=next(o for o in addon.modulos._chapas_do_conjunto(self.conj) if 'Base' in o.name)
        w=self.assistente(alto,baixo,(chapa.name,base.name))
        _,matriz=w._dados()
        self.assertAlmostEqual(matriz.translation.y,-.250,places=4)
        self.assertEqual(w._w['p']['cobertura'],'EMBUTIDA')
        self.assertAlmostEqual(w._w['vao'][1],min(v.z for v in verts)*1000-18,places=2)
        limite=min((fundo.matrix_world@v.co).y for v in fundo.data.vertices)
        self.assertAlmostEqual(w._w['maxprof'],(limite+.250)*1000,places=2)
        dimensoes=w._w['vao'];rotacao=matriz.to_3x3().copy()
        w._receber_profundidade(Vector((.400,.280,.900)))
        self.assertAlmostEqual(w._w['p']['profundidade_mm'],w._w['maxprof'],places=2)
        _,depois=w._dados()
        self.assertEqual(w._w['vao'],dimensoes)
        self.assertLess((depois.translation-matriz.translation).length,1e-6)
        for i in range(3):self.assertLess((depois.to_3x3().col[i]-rotacao.col[i]).length,1e-6)

    def test_assistente_frente_diagonal_nao_usa_caixa_inflada_do_modulo(self):
        rot=Matrix.Rotation(.78539816339,4,'Z')
        for o in self.conj.children:o.matrix_world=rot@o.matrix_world
        bpy.context.view_layer.update()
        w=self.assistente(rot@Vector((-.382,-.280,.682)),rot@Vector((.382,-.280,.018)))
        _,matriz=w._dados()
        self.assertGreater(matriz.to_3x3().col[1].dot(rot.to_3x3().col[1]),.999)
        self.assertAlmostEqual(w._w['maxprof'],560,places=2)
        self.assertAlmostEqual(w._w['vao'][0],764,places=2)

    def test_assistente_previa_nao_reconsulta_malhas_nem_raios(self):
        w=self.assistente((-.382,-.280,.682),(.382,-.280,.018))
        with patch.object(G,'_limites',side_effect=AssertionError('Malha na previa')), \
             patch.object(G,'limites_na_referencia',side_effect=AssertionError('Caixa na previa')), \
             patch.object(G,'profundidade_disponivel',side_effect=AssertionError('Ray cast na previa')):
            for n in (1,2,3):
                w._w['p']['quantidade']=n
                self.assertIsNotNone(w._dados()[0])

    def test_ancora_de_profundidade_lateral_projeta_so_no_eixo_e_para_no_fundo(self):
        grupo=self.gavetas(quantidade=1)
        dimensoes=G.medidas(grupo)[:2];antes=grupo.matrix_world.copy()
        p=grupo.matrix_world@Vector((10,2,9))
        self.assertIsNone(G._aplicar_ponto(grupo,2,p))
        self.assertEqual(G.medidas(grupo)[:2],dimensoes)
        self.assertLess((grupo.matrix_world.translation-antes.translation).length,1e-6)
        self.assertLessEqual(G.medidas(grupo)[2],560+.01)

    def test_translate_nativo_usa_eixo_real_da_ancora_girada(self):
        grupo=self.gavetas(quantidade=1)
        self.conj.rotation_euler.z=.73;bpy.context.view_layer.update()
        cursor=bpy.context.scene.cursor;antes=cursor.location.copy()
        contexto=SimpleNamespace(scene=bpy.context.scene,visible_objects=bpy.context.visible_objects,region=SimpleNamespace(as_pointer=lambda:1),
                    area=SimpleNamespace(as_pointer=lambda:2),space_data=SimpleNamespace(overlay=SimpleNamespace(show_cursor=True)))
        try:
            params=G._preparar_ancora_nativa(contexto,grupo,2)
            params.pop('release_confirm',None);params.pop('snap',None)
            params.pop('snap_elements',None);params.pop('snap_target',None)
            params.pop('snap_align',None);params.pop('use_snap_selectable',None)
            base=cursor.location.copy()
            bpy.ops.transform.translate(value=(0,.1,0),**params)
            esperado=grupo.matrix_world.to_3x3().col[1].normalized()*.1
            self.assertLess((cursor.location-base-esperado).length,1e-6)
        finally:
            G._terminar_ancora_nativa();cursor.location=antes
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for colecao in list(bpy.data.collections):
            bpy.data.collections.remove(colecao)
        camada = bpy.context.view_layer
        camada.active_layer_collection = camada.layer_collection
        G.esquecer()
        # balcao 800 x 700 x 560, chapa 18: o vao de dentro e' 764 x 664
        self.conj = addon.modulos.criar_armario(bpy.context, 'Balcao', 800, 700, 560,
                                                fundo=False)
        bpy.context.view_layer.update()

    def gavetas(self, **p):
        padrao = dict(quantidade=3, lateral_mm=18.0, espessura_frente_mm=18.0,
                      profundidade_mm=560.0)
        padrao.update(p)
        return G.criar_gavetas(bpy.context, self.conj, (18, 18, 18, 18, 0), padrao)

    def pecas(self, gaveta, peca):
        return [o for o in gaveta.children if o.get(G.MARCA_PECA) == peca]

    def test_calculo_telescopico_e_oculto(self):
        p = dict(G.PARAMETROS_PADRAO, quantidade=3, profundidade_mm=560.0)
        dados = G.calcular(764.0, 664.0, p)
        self.assertEqual(dados['trilho_mm'], 550)       # 560 - 10 de folga
        alturas = [f['frente'][5] - f['frente'][4] for f in dados['gavetas']]
        self.assertAlmostEqual(max(alturas) - min(alturas), 0.0, places=6)
        # sobreposta cobre a lateral menos a folga frontal: 18 - 2
        self.assertAlmostEqual(dados['gavetas'][0]['frente'][0], -16.0)
        fundo = dados['gavetas'][0]['caixa'][0][2]
        self.assertAlmostEqual(fundo[1] - fundo[0], 764.0 - 2 * 12.7, places=3)
        p['trilho'] = 'OCULTO'
        fundo = G.calcular(764.0, 664.0, p)['gavetas'][0]['caixa'][0][2]
        self.assertAlmostEqual(fundo[1] - fundo[0], 764.0 - 10.0, places=3)
        with self.assertRaises(ValueError):
            G.calcular(764.0, 664.0, dict(p, quantidade=10, entre_gavetas_mm=40))
        with self.assertRaisesRegex(ValueError, 'menor trilho'):
            G.calcular(764.0, 664.0, dict(p, profundidade_mm=200.0))
        limite = dict(p,quantidade=1,trilho='TELESCOPICO',coberturas_mm=[10,10,10,5])
        self.assertEqual(len(G.calcular(764,79.99994,limite)['gavetas']),1)
        with self.assertRaisesRegex(ValueError,'altura para a caixa'):
            G.calcular(764,79.9,limite)

    def test_sistemas_em_montagem_antiga_sobrevivem_a_reinsercao(self):
        colecao = addon.modulos._colecao_do_modulo(self.conj)
        del colecao[addon.modulos.MARCA_COLECAO_MODULO]
        grupo = self.gavetas()
        prateleiras = addon.prateleiras.criar_prateleiras(
            bpy.context, self.conj, (18,18,18,18,0),
            dict(quantidade=1, profundidade_mm=500))
        self.assertIn(grupo, list(colecao.objects))
        self.assertIn(prateleiras, list(colecao.objects))
        bpy.context.view_layer.update()
        antes = {o.name:[o.matrix_world @ v.co for v in o.data.vertices]
                 for o in colecao.objects if o.type == 'MESH'}
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, 'Montagem.blend')
            bpy.data.libraries.write(caminho, {colecao})
            for obj in list(bpy.data.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(colecao)
            with bpy.data.libraries.load(caminho) as (de, para):
                para.collections = list(de.collections)
            bpy.context.scene.collection.children.link(para.collections[0])
            bpy.context.view_layer.update()
            for obj in para.collections[0].objects:
                if obj.name in antes:
                    self.assertTrue(all((obj.matrix_world @ v.co-co).length < 1e-5
                                        for v,co in zip(obj.data.vertices,antes[obj.name])))
            frentes = [o for o in para.collections[0].objects if o.get(G.MARCA_PECA)=='FRENTE']
            self.assertEqual(len(frentes), 3)
            self.assertTrue(G.selecionar(bpy.context,frentes[0],'GRUPO'))
            self.assertEqual(len(G.gavetas_com_slider(bpy.context)), 3)

    def test_cria_frente_caixa_trilho_e_puxador_sem_mexer_no_modulo(self):
        antes = addon.modulos.medir_conjunto(self.conj)
        chapas = len(addon.modulos._chapas_do_conjunto(self.conj))
        grupo = self.gavetas()
        gavetas = G.gavetas_do_grupo(grupo)
        self.assertEqual(len(gavetas), 3)
        for g in gavetas:
            self.assertEqual(len(self.pecas(g, 'FRENTE')), 1)
            self.assertEqual(len(self.pecas(g, 'LATERAL')), 2)
            self.assertEqual(len(self.pecas(g, 'TRILHO')), 2)        # os moveis
            frente = self.pecas(g, 'FRENTE')[0]
            self.assertTrue(any(addon.chapas.MARCA_PUXADOR in f for f in frente.children))
        self.assertEqual(len([o for o in grupo.children if o.get(G.MARCA_PECA) == 'TRILHO']), 6)
        self.assertEqual(len(addon.modulos._chapas_do_conjunto(self.conj)), chapas)
        for a, b in zip(antes, addon.modulos.medir_conjunto(self.conj)):
            self.assertAlmostEqual(a, b, places=3)
        self.assertAlmostEqual(G.medidas(grupo)[0], 764.0, places=3)
        self.assertAlmostEqual(G.medidas(grupo)[1], 664.0, places=3)
        self.assertEqual(grupo[G.CHAVE_TRILHO_MM], 550.0)

    def test_abertura_leva_a_gaveta_para_fora_pelo_trilho(self):
        grupo = self.gavetas()
        gaveta = G.gavetas_do_grupo(grupo)[1]
        frente = self.pecas(gaveta, 'FRENTE')[0]
        y0 = frente.matrix_world.translation.y
        G.definir_abertura(gaveta, 1.0)
        bpy.context.view_layer.update()
        self.assertAlmostEqual(frente.matrix_world.translation.y - y0, -0.55, places=5)
        fixo = next(o for o in grupo.children if o.get(G.MARCA_PECA) == 'TRILHO')
        self.assertEqual(fixo.parent, grupo)        # o fixo nao sai com ela

    def test_editar_refaz_e_guarda_abertura_e_puxador(self):
        grupo = self.gavetas()
        G.definir_abertura(G.gavetas_do_grupo(grupo)[0], 0.4)
        G.colocar_puxador(G.gavetas_do_grupo(grupo)[0], 'ALCA')
        self.assertIsNone(G.editar(bpy.context, grupo, 'gavetas_quantidade', 2))
        gavetas = G.gavetas_do_grupo(grupo)
        self.assertEqual(len(gavetas), 2)
        self.assertAlmostEqual(gavetas[0][G.CHAVE_ABERTURA], 0.4)
        self.assertEqual(gavetas[0][G.CHAVE_PUXADOR], 'ALCA')
        self.assertIsNone(G.editar(bpy.context, grupo, 'trilho', 'OCULTO'))
        fundo = self.pecas(G.gavetas_do_grupo(grupo)[0], 'FUNDO')[0]
        self.assertAlmostEqual(fundo.chapa_largura_mm, 764.0 - 10.0, places=2)
        # nao cabe: devolve o erro e fica como estava
        erro = G.editar(bpy.context, grupo, 'profundidade_mm', 150.0)
        self.assertIn('menor trilho', erro)
        self.assertEqual(G.parametros(grupo)['profundidade_mm'], 560.0)
        self.assertEqual(len(G.gavetas_do_grupo(grupo)), 2)

    def test_modulo_que_muda_de_medida_preserva_as_gavetas(self):
        # Regressao (era BUG, corrigido na 219): a caixa esticava as gavetas.
        grupo = self.gavetas()
        gaveta = G.gavetas_do_grupo(grupo)[0]
        G.definir_abertura(gaveta, 0.4)
        antes = G.medidas(grupo)
        backup = addon.hud._estado_arraste_hud(
            bpy.context, {'objeto': self.conj, 'tipo': 'medida'})
        objetos = list(grupo.children_recursive)
        self.conj.conj_largura_mm = 1000.0
        self.conj.conj_altura_mm = 1200.0
        bpy.context.view_layer.update()
        for a, b in zip(antes, G.medidas(grupo)):
            self.assertAlmostEqual(a, b, places=2)
        self.assertEqual(objetos, list(grupo.children_recursive))
        self.assertAlmostEqual(gaveta[G.CHAVE_ABERTURA], 0.4)
        addon.hud._restaurar_arraste_hud(bpy.context, backup)
        for a, b in zip(antes, G.medidas(grupo)):
            self.assertAlmostEqual(a, b, places=2)
        self.conj.conj_altura_mm = 1200.0
        bpy.context.view_layer.update()
        origem = grupo.matrix_world.translation.copy()
        self.assertIsNone(G.aplicar(bpy.context, grupo, ('A',), 800.0))
        bpy.context.view_layer.update()
        self.assertLess((grupo.matrix_world.translation - origem).length, 1e-5)
        self.assertAlmostEqual(G.medidas(grupo)[1], 800.0, places=2)

    def test_reducao_com_folga_preserva_gavetas_ate_faltar_espaco(self):
        grupo = G.criar_gavetas(bpy.context, self.conj, (18,382,18,382,0),
                                dict(quantidade=1, profundidade_mm=400))
        antes = G.medidas(grupo)
        for largura in (1000,900,700,600):
            self.conj.conj_largura_mm = largura
            bpy.context.view_layer.update()
            self.assertAlmostEqual(G.medidas(grupo)[0], antes[0], delta=.05)
        self.conj.conj_altura_mm = 600
        self.assertAlmostEqual(G.medidas(grupo)[1], antes[1], delta=.05)
        self.conj.conj_profundidade_mm = 500
        self.assertAlmostEqual(G.medidas(grupo)[2], antes[2], delta=.05)
        self.conj.conj_largura_mm = 400
        self.assertAlmostEqual(G.medidas(grupo)[0], 364, delta=.05)
        self.conj.conj_largura_mm = 800
        self.assertAlmostEqual(G.medidas(grupo)[0], antes[0], delta=.05)

    def test_escala_nativa_conserva_internos_ate_faltar_espaco(self):
        grupo = G.criar_gavetas(bpy.context,self.conj,(18,382,18,382,0),
                                dict(quantidade=1,profundidade_mm=400))
        p = addon.prateleiras
        prateleiras = p.criar_prateleiras(bpy.context,self.conj,(18,382,350,18,0),
                                         dict(quantidade=1,profundidade_mm=400))
        for alvo,esperado in [(1000,400),(900,400),(450,400),(400,364),(800,400)]:
            atual=addon.modulos.medir_conjunto(self.conj)[0]
            self.conj.scale.x=alvo/atual
            bpy.context.view_layer.update()
            addon.eventos.verificar_periodicamente()
            bpy.context.view_layer.update()
            self.assertAlmostEqual(G.medidas(grupo)[0],esperado,delta=.1)
            self.assertAlmostEqual(p.medidas(prateleiras)[0],esperado,delta=.1)
            chapa=p.prateleiras_do_grupo(prateleiras)[0]
            xs=[(chapa.matrix_world@v.co).x for v in chapa.data.vertices]
            self.assertAlmostEqual((max(xs)-min(xs))*1000,esperado,delta=.1)

    def test_gaveta_individual_menor_nao_encolhe_junto_com_o_vao(self):
        grupo=G.criar_gavetas(bpy.context,self.conj,(18,382,18,382,0),
                              dict(quantidade=1,profundidade_mm=400))
        self.assertIsNone(G.editar_individual(bpy.context,grupo,0,'largura',250))
        for alvo in (400,350,800):
            self.conj.conj_largura_mm=alvo
            self.assertAlmostEqual(float(G.parametros_da_unidade(G.parametros(grupo),0)['largura_mm']),250,delta=.05)

    def test_encolher_modulo_adapta_gavetas_e_retorno_restaura_escolhas(self):
        grupo=self.gavetas()
        gaveta=G.gavetas_do_grupo(grupo)[0];G.definir_abertura(gaveta,.4)
        antes=G.medidas(grupo);objetos=list(grupo.children_recursive)
        self.conj.conj_largura_mm=200
        self.assertAlmostEqual(G.medidas(grupo)[0],164,delta=.05)
        self.conj.conj_profundidade_mm=100
        self.assertAlmostEqual(self.conj.conj_profundidade_mm,260,delta=.05)
        self.assertAlmostEqual(G.parametros(grupo)['profundidade_mm'],260,delta=.05)
        self.assertEqual(grupo[G.CHAVE_TRILHO_MM],250)
        self.assertEqual(objetos,list(grupo.children_recursive))
        self.assertAlmostEqual(gaveta[G.CHAVE_ABERTURA],.4,places=4)
        self.conj.conj_largura_mm=800
        self.conj.conj_profundidade_mm=560
        for a,b in zip(antes,G.medidas(grupo)):self.assertAlmostEqual(a,b,delta=.05)
        self.assertEqual(grupo[G.CHAVE_TRILHO_MM],550)

    def test_esc_apos_reducao_do_modulo_restaura_sistema_inteiro(self):
        grupo=self.gavetas();antes=G.parametros(grupo)
        medidas=G.medidas(grupo);objetos=list(grupo.children_recursive)
        alvo=dict(objeto=self.conj,tipo='medida',modo='GRUPO',eixo=1,lado='min')
        backup=addon.hud._estado_arraste_hud(bpy.context,alvo)
        addon.hud._aplicar_valor_hud(bpy.context,alvo,100)
        addon.hud._restaurar_arraste_hud(bpy.context,backup)
        self.assertEqual(antes,G.parametros(grupo))
        for a,b in zip(medidas,G.medidas(grupo)):self.assertAlmostEqual(a,b,delta=.01)
        self.assertEqual(objetos,list(grupo.children_recursive))
        self.assertNotIn(G.CHAVE_ENCAIXE,grupo)

    def test_reducao_rotacionada_preserva_eixos_das_gavetas(self):
        grupo=self.gavetas()
        self.conj.rotation_euler.z=math.pi/2
        bpy.context.view_layer.update();addon.modulos.sincronizar_medidas_conjunto(self.conj)
        self.conj.conj_largura_mm=100
        self.assertAlmostEqual(G.parametros(grupo)['profundidade_mm'],260,delta=.05)
        self.assertAlmostEqual(self.conj.conj_largura_mm,260,delta=.05)
        self.conj.conj_largura_mm=560
        self.assertAlmostEqual(G.parametros(grupo)['profundidade_mm'],560,delta=.05)

    def test_esticar_para_baixo_leva_gavetas_sem_deformar_e_esc_devolve(self):
        # Regressao (era BUG, corrigido na 220): a base descia sozinha.
        grupo = G.criar_gavetas(bpy.context, self.conj, (18, 18, 18, 382, 0),
                               dict(quantidade=3, profundidade_mm=560.0))
        gaveta = G.gavetas_do_grupo(grupo)[0]
        G.definir_abertura(gaveta, 0.4)
        bpy.context.view_layer.update()
        medidas = G.medidas(grupo)
        objetos = [grupo, *grupo.children_recursive]
        matrizes = {o.name: o.matrix_world.copy() for o in objetos}
        malhas = {o.name: [tuple(v.co) for v in o.data.vertices]
                  for o in objetos if o.type == 'MESH'}
        margens = tuple(grupo[G.CHAVE_MARGENS])
        alvo = dict(objeto=self.conj, tipo='medida', modo='GRUPO', eixo=2, lado='max')
        backup = addon.hud._estado_arraste_hud(bpy.context, alvo)
        teto = addon.modulos._caixa_de(addon.modulos._chapas_do_conjunto(self.conj))[1][2]
        for altura in (1000.0, 1200.0):
            addon.hud._aplicar_valor_hud(bpy.context, alvo, altura)
            bpy.context.view_layer.update()
            delta = Vector((0, 0, -(altura - 700.0) / 1000.0))
            for o in objetos:
                self.assertLess((o.matrix_world.translation -
                                 matrizes[o.name].translation - delta).length, 1e-5)
            for a, b in zip(medidas, G.medidas(grupo)):
                self.assertAlmostEqual(a, b, places=2)
            self.assertAlmostEqual(addon.modulos._caixa_de(
                addon.modulos._chapas_do_conjunto(self.conj))[1][2], teto, places=5)
        self.assertEqual(malhas, {o.name: [tuple(v.co) for v in o.data.vertices]
                                 for o in objetos if o.type == 'MESH'})
        self.assertAlmostEqual(gaveta[G.CHAVE_ABERTURA], 0.4)
        addon.hud._restaurar_arraste_hud(bpy.context, backup)
        bpy.context.view_layer.update()
        for o in objetos:
            self.assertLess((o.matrix_world.translation - matrizes[o.name].translation).length, 1e-5)
        self.assertEqual(tuple(grupo[G.CHAVE_MARGENS]), margens)
        for a, b in zip(medidas, G.medidas(grupo)):
            self.assertAlmostEqual(a, b, places=2)

    def test_gavetas_proximas_do_topo_acompanham_topo_sem_esticar(self):
        grupo = G.criar_gavetas(bpy.context, self.conj, (18, 18, 382, 18, 0),
                               dict(quantidade=3, profundidade_mm=560.0))
        bpy.context.view_layer.update()
        origem = grupo.matrix_world.translation.copy()
        medidas = G.medidas(grupo)
        alvo = dict(objeto=self.conj, tipo='medida', modo='GRUPO', eixo=2, lado='min')
        addon.hud._aplicar_valor_hud(bpy.context, alvo, 1000.0)
        bpy.context.view_layer.update()
        self.assertLess((grupo.matrix_world.translation - origem - Vector((0, 0, 0.3))).length, 1e-5)
        for a, b in zip(medidas, G.medidas(grupo)):
            self.assertAlmostEqual(a, b, places=2)

    def test_modulo_selecionado_absorve_gavetas_sem_segunda_ancora(self):
        # Regressao (era BUG, corrigido na 219): filhos viravam multiselecao.
        grupo = self.gavetas()
        for o in [self.conj, *self.conj.children_recursive]:
            o.select_set(True)
        bpy.context.view_layer.objects.active = self.conj
        itens = addon.hud._itens_da_selecao(bpy.context)
        self.assertEqual([(o, modo) for o, modo, _ in itens], [(self.conj, 'GRUPO')])
        self.assertEqual(G.selecionados(bpy.context), [])
        self.assertEqual(G.gavetas_com_slider(bpy.context), [])
        outro = addon.modulos.criar_armario(bpy.context, 'Outro', 600, 700, 560)
        for o in [self.conj, *self.conj.children_recursive]:
            o.select_set(True)
        outro.select_set(True)
        itens = addon.hud._itens_da_selecao(bpy.context)
        self.assertEqual({o for o, modo, _ in itens}, {self.conj, outro})
        self.assertTrue(all(modo == 'GRUPO' for _, modo, _ in itens))

    def test_selecao_como_a_da_porta_e_so_elas_na_hud(self):
        grupo = self.gavetas()
        gaveta = G.gavetas_do_grupo(grupo)[2]
        frente = self.pecas(gaveta, 'FRENTE')[0]
        self.assertEqual(addon.selecao._aba_da_selecao(frente), 'GAVETAS')
        G.selecionar(bpy.context, frente, 'GRUPO')
        self.assertEqual(bpy.context.view_layer.objects.active, grupo)
        self.assertFalse(self.conj.select_get())
        itens = addon.hud._itens_da_selecao(bpy.context)
        self.assertEqual([(o.name, modo) for o, modo, _c in itens], [(grupo.name, 'GAVETAS')])
        geometria = addon.hud._geometria_do_item(*itens[0])
        self.assertEqual({l['tipo'] for l in geometria['linhas']}, {'gavetas'})
        self.assertEqual(len(G.gavetas_com_slider(bpy.context)), 3)
        G.selecionar(bpy.context, frente, 'GAVETA')
        self.assertEqual(bpy.context.view_layer.objects.active, gaveta)
        self.assertEqual(G.gavetas_com_slider(bpy.context), [gaveta])
        self.assertEqual(len(addon.hud._itens_da_selecao(bpy.context)), 1)

    def test_hud_edita_largura_com_a_quina_parada_e_profundidade(self):
        grupo = self.gavetas()
        G.selecionar(bpy.context, grupo, 'GRUPO')
        geometria = addon.hud._geometria_do_item(grupo, 'GAVETAS', [])
        inversa = grupo.matrix_world.inverted()
        projetar = lambda p: Vector(((inversa @ p).x, (inversa @ p).z)) * 1000.0
        linha = next(l for l in geometria['linhas'] if l['letra'] == 'L')
        perto_do_min = projetar(linha['pontos'][0]) + Vector((5.0, 0.0))
        alvo = addon.hud._acertar_linhas_hud(geometria, perto_do_min, projetar, cantos=False)
        self.assertEqual((alvo['tipo'], alvo['lado']), ('gavetas', 'min'))
        esquerda = self.pecas(G.gavetas_do_grupo(grupo)[0], 'FRENTE')[0].matrix_world.translation.x \
            - self.pecas(G.gavetas_do_grupo(grupo)[0], 'FRENTE')[0].chapa_largura_mm / 2000.0
        addon.hud._aplicar_valor_hud(bpy.context, alvo, 700.0)
        self.assertAlmostEqual(addon.hud._valor_hud(alvo), 700.0, places=3)
        frente = self.pecas(G.gavetas_do_grupo(grupo)[0], 'FRENTE')[0]
        self.assertAlmostEqual(frente.matrix_world.translation.x
                               - frente.chapa_largura_mm / 2000.0, esquerda, places=5)
        self.assertIsNone(G.aplicar(bpy.context, grupo, ('P',), 400.0))
        self.assertEqual(grupo[G.CHAVE_TRILHO_MM], 350.0)

    def test_cancelar_redimensionamento_direto_devolve_medidas_e_selecao(self):
        # Regressao (era BUG, corrigido na 221): Esc nao devolvia as medidas.
        grupo = self.gavetas()
        G.selecionar(bpy.context, grupo, 'GRUPO')
        G.definir_abertura(G.gavetas_do_grupo(grupo)[0], 0.4)
        for letra in ('L', 'A', 'P'):
            for lado in ('min', 'max'):
                alvo = dict(objeto=grupo, tipo='gavetas', face=(letra,), lado=lado)
                antes = G.medidas(grupo)
                modulo = addon.modulos.medir_conjunto(self.conj)
                origem = grupo.matrix_world.translation.copy()
                backup = addon.hud._estado_arraste_hud(bpy.context, alvo)
                addon.hud._aplicar_valor_hud(bpy.context, alvo, G.valor(grupo, (letra,)) - 50)
                addon.hud._restaurar_arraste_hud(bpy.context, backup)
                bpy.context.view_layer.update()
                for a, b in zip(antes, G.medidas(grupo)):
                    self.assertAlmostEqual(a, b, places=2)
                for a, b in zip(modulo, addon.modulos.medir_conjunto(self.conj)):
                    self.assertAlmostEqual(a, b, places=2)
                self.assertLess((grupo.matrix_world.translation - origem).length, 1e-5)
                self.assertEqual(bpy.context.view_layer.objects.active, grupo)
                self.assertAlmostEqual(G.gavetas_do_grupo(grupo)[0][G.CHAVE_ABERTURA], 0.4)

    def test_profundidade_editada_pelas_costas_mantem_costas_paradas(self):
        # Regressao (era BUG, corrigido na 221): P ignorava a quina escolhida.
        grupo = self.gavetas()
        bpy.context.view_layer.update()
        costas = G.pontos_editaveis(grupo)[2].copy()
        self.assertIsNone(G.aplicar(bpy.context, grupo, ('P',), 460.0, 'max'))
        bpy.context.view_layer.update()
        self.assertLess((G.pontos_editaveis(grupo)[2] - costas).length, 1e-5)
        self.assertAlmostEqual(G.medidas(grupo)[2], 460.0)

    def test_redimensionar_preserva_selecao_individual_da_gaveta(self):
        # Regressao (era BUG, corrigido na 221): a gaveta ativa era apagada.
        grupo = self.gavetas()
        G.selecionar(bpy.context, G.gavetas_do_grupo(grupo)[1], 'GAVETA')
        self.assertIsNone(G.aplicar(bpy.context, grupo, ('A',), 600.0, 'min'))
        self.assertEqual(bpy.context.view_layer.objects.active, G.gavetas_do_grupo(grupo)[1])
        self.assertEqual(G.gavetas_com_slider(bpy.context), [G.gavetas_do_grupo(grupo)[1]])

    def test_parametros_copiados_e_profundidade_invalida_nao_corrompem_proporcoes(self):
        # Regressao (era BUG, corrigido na 221): array RNA liberado no rollback.
        grupo = self.gavetas(proporcoes=[2.0, 1.0, 1.0])
        p = G.parametros(grupo)
        self.assertIsInstance(p['proporcoes'], list)
        for prof in (200.0, 500.0, 150.0, 400.0):
            erro = G.editar(bpy.context, grupo, 'profundidade_mm', prof)
            self.assertEqual(erro is not None, prof < 260.0)
            self.assertEqual(G.parametros(grupo)['proporcoes'], [2.0, 1.0, 1.0])
        self.assertEqual(p['profundidade_mm'], 560.0)
        self.assertEqual(p['proporcoes'], [2.0, 1.0, 1.0])

    def test_esc_apos_renomear_mover_e_crescer_modulo_nao_desloca_gavetas(self):
        # Regressao (era BUG, corrigido na 222): Esc duplicava a translacao.
        grupo = self.gavetas()
        self.conj.location = (6.7, -1.25, 0.3)
        addon.modulos.nomear_grupo(self.conj, 'Balcao 800x800x560')
        self.conj.conj_altura_mm += 100.0
        bpy.context.view_layer.update()
        G.selecionar(bpy.context, grupo, 'GRUPO')
        antes = grupo.matrix_world.copy()
        medidas = G.medidas(grupo)
        alvo = dict(objeto=grupo, tipo='gavetas', face=('A',), lado='max')
        backup = addon.hud._estado_arraste_hud(bpy.context, alvo)
        # Entrar e Esc SEM mover, como no relato.
        addon.hud._restaurar_arraste_hud(bpy.context, backup)
        bpy.context.view_layer.update()
        self.assertLess((grupo.matrix_world.translation - antes.translation).length, 1e-5)
        for a, b in zip(medidas, G.medidas(grupo)):
            self.assertAlmostEqual(a, b, places=2)
        self.assertIs(G.modulo_do_grupo(grupo), self.conj)
        self.assertEqual(grupo[G.CHAVE_MODULO], self.conj.name)

    def test_pai_real_prevalece_sobre_nome_antigo_de_outro_modulo(self):
        # Regressao (era BUG, corrigido na 222): preset resolvia o modulo errado.
        grupo = self.gavetas()
        self.conj.name = 'Balcao renomeado no Outliner'
        addon.modulos.criar_armario(bpy.context, 'Balcao', 500, 600, 400)
        self.assertIs(G.modulo_do_grupo(grupo), self.conj)

    def test_indice_snap_preserva_ponto_mais_perto_raio_e_empates(self):
        contexto = SimpleNamespace(region=SimpleNamespace(width=800, height=600),
            region_data=SimpleNamespace(perspective_matrix=Matrix((
                (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0.5, 1)))))
        pontos = [Vector((x / 10, y / 10, z)) for x in range(-12, 13)
                  for y in range(-8, 9) for z in (-3.0, 0.0, 0.5)]
        pontos += [Vector((0, 0, 0)), Vector((0, 0, 0.2))]
        indice = G.IndiceSnapGavetas([('Teste', pontos)])
        for x in range(0, 801, 40):
            for y in range(0, 601, 40):
                mouse = Vector((x, y))
                candidatos = []
                for i, p in enumerate(pontos):
                    tela = view3d_utils.location_3d_to_region_2d(
                        contexto.region, contexto.region_data, p)
                    if tela is not None:
                        d = (tela - mouse).length
                        if d <= addon.portas.RAIO_IMA_PX:
                            candidatos.append((d, i, p))
                esperado = min(candidatos, key=lambda v: (v[0], v[1]))[2] if candidatos else None
                encontrado = indice.buscar(contexto, mouse)
                if esperado is None:
                    self.assertIsNone(encontrado)
                else:
                    # Pequeno erro da projecao em lote nao pode mudar o snap.
                    self.assertLess((encontrado - esperado).length, 1e-5)

    def test_indice_snap_nao_reprojeta_no_mouse_e_atualiza_ao_navegar(self):
        contexto = SimpleNamespace(region=SimpleNamespace(width=800, height=600),
            region_data=SimpleNamespace(perspective_matrix=Matrix.Identity(4)))
        ponto = Vector((0.0, 0.0, 0.0))
        indice = G.IndiceSnapGavetas([('Teste', [ponto] * 10000)])
        with patch.object(indice, '_reconstruir', wraps=indice._reconstruir) as refazer:
            for i in range(500):
                self.assertEqual(indice.buscar(contexto, (400 + i % 10, 300)), ponto)
            self.assertEqual(refazer.call_count, 1)
            contexto.region_data.perspective_matrix[0][3] = 0.5
            self.assertIsNone(indice.buscar(contexto, (400, 300)))
            self.assertEqual(indice.buscar(contexto, (600, 300)), ponto)
            contexto.region.width = 1000
            self.assertEqual(indice.buscar(contexto, (750, 300)), ponto)
            self.assertEqual(refazer.call_count, 3)

    def test_snap_ignora_pecas_da_gaveta_sem_excluir_modulo(self):
        grupo = self.gavetas()
        ignorados = {o.name for o in [grupo, *grupo.children_recursive]}
        nomes = {o.name for o, _vs in addon.portas._alvos_do_ima(bpy.context, ignorar=ignorados)}
        self.assertFalse(nomes & ignorados)
        self.assertTrue({o.name for o in addon.modulos._chapas_do_conjunto(self.conj)} <= nomes)

    def test_tres_pontos_com_alt_refazem_o_vao(self):
        grupo = self.gavetas()
        cima_esq, baixo_dir, fundo = G.pontos_editaveis(grupo)
        eixos = grupo.matrix_world.to_3x3()
        novo = cima_esq + eixos.col[0] * 0.05 - eixos.col[2] * 0.1
        self.assertIsNone(G._aplicar_ponto(grupo, 0, novo))
        largura, altura, _p = G.medidas(grupo)
        self.assertAlmostEqual(largura, 714.0, places=3)
        self.assertAlmostEqual(altura, 564.0, places=3)
        self.assertIsNone(G._aplicar_ponto(grupo, 2, G.pontos_editaveis(grupo)[2]
                                           - eixos.col[1] * 0.1))
        self.assertAlmostEqual(G.medidas(grupo)[2], 460.0, places=3)

    def test_puxador_de_uma_gaveta_ou_de_todas(self):
        grupo = self.gavetas()
        gavetas = G.gavetas_do_grupo(grupo)
        G.selecionar(bpy.context, self.pecas(gavetas[1], 'FRENTE')[0], 'GAVETA')
        self.assertIsNone(G.trocar_puxador(bpy.context, 'ALCA'))
        tipos = [G.gavetas_do_grupo(grupo)[i].get(G.CHAVE_PUXADOR) for i in range(3)]
        self.assertEqual(tipos, ['PERFIL', 'ALCA', 'PERFIL'])
        G.selecionar(bpy.context, grupo, 'GRUPO')
        self.assertIsNone(G.trocar_puxador(bpy.context, 'BORDA'))
        tipos = {g.get(G.CHAVE_PUXADOR) for g in G.gavetas_do_grupo(grupo)}
        self.assertEqual(tipos, {'BORDA'})
        # o material das frentes: a pintura pega frentes e caixas
        pecas = addon.materiais.pecas_dos_alvos([grupo])
        self.assertEqual(len(pecas), 3 * 6)

    def test_aba_gavetas_e_campos_editaveis(self):
        cena = bpy.context.scene
        cena.cabinet_aba = 'GAVETAS'
        widgets = addon.gaveta._widgets_gaveta(bpy.context, 480, 1400)
        self.assertTrue(any(v[5] and v[5][0] == 'gavetas' for v in widgets))
        self.assertIn(('aba', 'GAVETAS'), [v[5] for v in widgets if v[5]])
        grupo = self.gavetas()
        G.selecionar(bpy.context, grupo, 'GRUPO')
        widgets = addon.gaveta._widgets_gaveta(bpy.context, 480, 1400)
        acoes = [v[5] for v in widgets if v[5]]
        self.assertTrue(any(a[0] == 'contador' and a[1] == 'gavetas_quantidade' for a in acoes))
        self.assertTrue(any(a[0] == 'escolha' and a[1] == 'gavetas_trilho' for a in acoes))
        self.assertTrue(any(a[0] == 'escolha' and a[5] == addon.gaveta.ALVO_PUXADOR_GAVETAS
                            for a in acoes if len(a) > 5))
        medidas = {a[2] for a in acoes if a[0] == 'medida' and a[1] == 'gavetas'}
        self.assertTrue({'largura', 'altura', 'profundidade_mm', 'folga_frontal_mm',
                         'entre_gavetas_mm', 'recuo_mm'} <= medidas, medidas)
        # os campos chegam nas gavetas pelos mesmos caminhos da porta
        ev = addon.gaveta_eventos
        self.assertIsNone(ev.aplicar_medida(bpy.context, 'gavetas', grupo.name,
                                            'recuo_mm', 0.02))
        self.assertEqual(G.parametros(grupo)['recuo_mm'], 20.0)
        self.assertIsNone(ev._aplicar_contador(
            bpy.context, ('contador', 'gavetas_quantidade', 3, 1, 10, grupo.name), 4))
        self.assertEqual(len(G.gavetas_do_grupo(grupo)), 4)
        # os operadores registrados (eventos de verdade no gui_interacao)
        for nome in ('OBJECT_OT_criar_gavetas', 'OBJECT_OT_abrir_gaveta',
                     'OBJECT_OT_arrastar_ponto_gaveta', 'VIEW3D_GT_slider_gaveta',
                     'VIEW3D_GGT_slider_gaveta'):
            self.assertIn(nome, [c.__name__ for c in addon.CLASSES])


    def test_ancora_nativa_nao_varre_malhas_e_restaura_cursor(self):
        grupo = self.gavetas()
        overlay = SimpleNamespace(show_cursor=True)
        area = SimpleNamespace(as_pointer=lambda: 123, type='VIEW_3D',
                               spaces=SimpleNamespace(active=SimpleNamespace(overlay=overlay)),
                               tag_redraw=lambda: None)
        contexto = SimpleNamespace(region=SimpleNamespace(as_pointer=lambda: 456),
            area=area, scene=bpy.context.scene, visible_objects=list(bpy.context.scene.objects),
            space_data=SimpleNamespace(overlay=overlay))
        cursor = tuple(bpy.context.scene.cursor.location)
        selecao = {o.name for o in bpy.context.selected_objects}
        bloqueados = {o.name: o.hide_select for o in bpy.context.scene.objects}
        with patch.object(addon.portas, '_alvos_do_ima', side_effect=AssertionError('varredura')):
            parametros = G._preparar_ancora_nativa(contexto, grupo, 0)
        self.assertTrue(parametros['cursor_transform'])
        self.assertTrue(parametros['use_snap_selectable'])
        self.assertFalse(overlay.show_cursor)
        self.assertTrue(all(o.hide_select for o in grupo.children_recursive if o.type == 'MESH'))
        self.assertEqual(selecao, {o.name for o in bpy.context.selected_objects})
        with patch.object(bpy, 'context', SimpleNamespace(window_manager=SimpleNamespace(
                windows=[SimpleNamespace(screen=SimpleNamespace(areas=[area]))]))):
            G._terminar_ancora_nativa()
        self.assertEqual(tuple(bpy.context.scene.cursor.location), cursor)
        self.assertTrue(overlay.show_cursor)
        self.assertEqual(bloqueados, {o.name: o.hide_select for o in bpy.context.scene.objects})

    def test_clique_no_puxador_isola_acessorio_e_abre_suas_funcoes(self):
        grupo = self.gavetas()
        gavetas = G.gavetas_do_grupo(grupo)
        puxadores = [next(o for o in G.frente_da_gaveta(g).children
                         if addon.chapas.MARCA_PUXADOR in o) for g in gavetas]
        G.selecionar(bpy.context, grupo, 'GRUPO')
        S = addon.selecao
        op = SimpleNamespace(clique=False, modo='GRUPO', toggle=False, extend=False)
        evento = SimpleNamespace(mouse_region_x=50, mouse_region_y=60)

        def clicar(obj, somar=False):
            op.toggle = somar
            ctx = SimpleNamespace(region=SimpleNamespace(as_pointer=lambda: 1),
                view_layer=bpy.context.view_layer, selected_objects=list(bpy.context.selected_objects),
                area=None)
            with patch.object(addon.hud, '_raio_hud', return_value=(obj, None)), \
                 patch.object(addon.hud, '_ferragem_sob_mouse', return_value=None), \
                 patch.object(addon.portas_viewport, '_slider_sob_mouse', return_value=None), \
                 patch.object(G, 'slider_sob_mouse', return_value=None):
                return S.OBJECT_OT_selecionar._invoke(op, ctx, evento)

        self.assertEqual(clicar(puxadores[0]), {'FINISHED'})
        self.assertEqual(set(bpy.context.selected_objects), {puxadores[0]})
        self.assertFalse(S.familia_de(puxadores[0]))
        S._seguir_selecao_na_gaveta(bpy.context)
        self.assertEqual(bpy.context.scene.cabinet_aba, 'PUXADORES')
        acoes = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 480, 1400) if v[5]]
        self.assertTrue(any(a[0] == 'escolha' and addon.gaveta.ALVO_PUXADOR in a for a in acoes))
        clicar(puxadores[1], somar=True)
        self.assertEqual(set(bpy.context.selected_objects), set(puxadores[:2]))
        clicar(puxadores[1], somar=True)
        self.assertEqual(set(bpy.context.selected_objects), {puxadores[0]})
        self.assertEqual(bpy.context.view_layer.objects.active, puxadores[0])
        trilho = next(o for o in grupo.children if o.get(G.MARCA_PECA) == 'TRILHO')
        clicar(trilho)
        self.assertEqual(bpy.context.view_layer.objects.active, grupo)
        self.assertFalse(any(p.select_get() for p in puxadores))

    def test_edicao_individual_puxador_sobrevive_ao_redimensionamento(self):
        grupo = self.gavetas()
        gavetas = G.gavetas_do_grupo(grupo)
        pux = next(o for o in G.frente_da_gaveta(gavetas[1]).children
                   if addon.chapas.MARCA_PUXADOR in o)
        addon.puxadores._trocar_modelo_puxador(pux, 'ALCA')
        pux['puxador_comprimento_mm'] = 180.0
        pux['puxador_recuo_mm'] = 35.0
        pux['puxador_fracao'] = 0.3
        addon.puxadores.posicionar_puxador(pux)
        self.assertEqual(gavetas[1][G.CHAVE_PUXADOR], 'ALCA')
        self.assertIsNone(G.editar(bpy.context, grupo, 'entre_gavetas_mm', 6.0))
        gavetas = G.gavetas_do_grupo(grupo)
        self.assertEqual([g[G.CHAVE_PUXADOR] for g in gavetas], ['PERFIL', 'ALCA', 'PERFIL'])
        novo = next(o for o in G.frente_da_gaveta(gavetas[1]).children
                    if addon.chapas.MARCA_PUXADOR in o)
        for chave, valor in (('puxador_comprimento_mm', 180.0), ('puxador_recuo_mm', 35.0),
                             ('puxador_fracao', 0.3)):
            self.assertAlmostEqual(novo[chave], valor)

    def test_macro_nativa_registrada_e_confirmacao_sem_estado(self):
        self.assertIn(G.OBJECT_OT_mover_ancora_gaveta, addon.CLASSES)
        self.assertIn(G.OBJECT_OT_confirmar_ancora_gaveta, addon.CLASSES)
        self.assertEqual(bpy.ops.object.cabinet_confirmar_ancora_gaveta(), {'CANCELLED'})

    def test_frente_curva_e_alturas_em_proporcao(self):
        # Promob: o gaveteiro de canto tem frente em ARCO e frentes de
        # alturas diferentes -- as nossas gavetas ganham as duas coisas
        grupo = self.gavetas(frente_curva_mm=60.0, proporcoes=[2.0, 1.0, 1.0],
                             puxador='NENHUM')
        frentes = [G.frente_da_gaveta(g) for g in G.gavetas_do_grupo(grupo)]
        alturas = [f.chapa_comprimento_mm for f in frentes]
        self.assertAlmostEqual(alturas[0] / alturas[1], 2.0, places=3)
        self.assertAlmostEqual(alturas[1], alturas[2], places=3)
        frente = frentes[0]
        # a malha do arco (`_chapas._malha_arco`): a corda e' a largura da
        # frente reta e a flecha vai para FORA (Z+ local = -Y do modulo)
        self.assertGreater(len(frente.data.vertices), 8)
        zs = [v.co.z * 1000.0 for v in frente.data.vertices]
        xs = [v.co.x * 1000.0 for v in frente.data.vertices]
        self.assertAlmostEqual(max(zs), 18.0 / 2 + 60.0, places=2)
        self.assertAlmostEqual(max(xs) - min(xs), frente.chapa_largura_mm, places=2)
        # outra quantidade: as proporcoes saem (alturas iguais)
        self.assertIsNone(G.editar(bpy.context, grupo, 'quantidade', 2))
        self.assertNotIn('proporcoes', grupo[G.CHAVE_PARAMETROS])
        a, b = [G.frente_da_gaveta(g).chapa_comprimento_mm for g in G.gavetas_do_grupo(grupo)]
        self.assertAlmostEqual(a, b, places=3)
        # curva 0 = reta de novo (a caixa padrao)
        self.assertIsNone(G.editar(bpy.context, grupo, 'frente_curva_mm', 0.0))
        self.assertEqual(len(G.frente_da_gaveta(G.gavetas_do_grupo(grupo)[0]).data.vertices), 8)
        # o campo "Curva" esta' na secao Frente da aba
        G.selecionar(bpy.context, grupo, 'GRUPO')
        bpy.context.scene.cabinet_aba = 'GAVETAS'
        acoes = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 480, 1400) if v[5]]
        self.assertTrue(any(a[0] == 'medida' and a[2] == 'frente_curva_mm' for a in acoes))

    def test_altura_individual_reencaixa_vizinha_sem_mudar_conjunto(self):
        grupo=self.gavetas(proporcoes=[1,2,1])
        G.selecionar(bpy.context,grupo,'GRUPO')
        largura,altura,_=G.medidas(grupo)
        antes=G.frentes(largura,altura,G.parametros(grupo))
        self.assertIsNone(G.aplicar(bpy.context,grupo,('A',1),antes[1][3]-antes[1][2]+40,'min'))
        depois=G.frentes(largura,altura,G.parametros(grupo))
        self.assertEqual(antes[0],depois[0])
        self.assertAlmostEqual(depois[1][2],antes[1][2])
        self.assertAlmostEqual(depois[1][3],antes[1][3]+40)
        self.assertAlmostEqual(depois[2][3],antes[2][3])
        self.assertEqual(G.medidas(grupo),(largura,altura,560))
        atual=G.valor(grupo,('A',1))
        topo=depois[1][3]
        self.assertIsNone(G.aplicar(bpy.context,grupo,('A',1),atual-25,'max'))
        depois=G.frentes(largura,altura,G.parametros(grupo))
        self.assertAlmostEqual(depois[1][3],topo)
        estado=G.copia(grupo)
        self.assertIsNotNone(G.aplicar(bpy.context,grupo,('A',1),900,'min'))
        self.assertEqual(G.copia(grupo),estado)
        self.assertEqual(bpy.context.object,grupo)

    def test_unidade_tem_profundidade_trilho_largura_e_espacamentos_proprios(self):
        grupo=self.gavetas()
        tamanho=G.medidas(grupo)
        self.assertIsNone(G.editar_individual(bpy.context,grupo,1,'profundidade_mm',450))
        self.assertIsNone(G.editar_individual(bpy.context,grupo,1,'trilho','OCULTO'))
        self.assertIsNone(G.editar_individual(bpy.context,grupo,1,'largura',700))
        self.assertIsNone(G.editar_individual(bpy.context,grupo,1,'recuo_mm',20))
        self.assertIsNone(G.editar_individual(bpy.context,grupo,1,'acima_mm',10))
        dados=G.calcular(*G.vao(grupo)[:2],G.parametros(grupo))
        self.assertEqual([d['trilho_mm'] for d in dados['gavetas']],[550,400,550])
        self.assertEqual(G.valor(grupo,('L',1)),700)
        self.assertEqual(G.folgas(G.parametros(grupo)),[3,10])
        self.assertEqual(G.medidas(grupo),tamanho)
        gaveta=G.gavetas_do_grupo(grupo)[1]
        G.definir_abertura(gaveta,1)
        self.assertAlmostEqual(gaveta.location.y,-.4)
        self.assertIsNone(G.editar(bpy.context,grupo,'trilho','TELESCOPICO'))
        self.assertEqual(G.parametros_da_unidade(G.parametros(grupo),1)['trilho'],'TELESCOPICO')

    def test_hud_segmentos_individuais_hover_e_selecao_isolada(self):
        grupo=self.gavetas()
        G.selecionar(bpy.context,grupo,'GRUPO')
        geometria=addon.hud._geometria_do_item(grupo,'GAVETAS',[])
        self.assertEqual({l['face'][1] for l in geometria['linhas'] if len(l['face'])>1},{0,1,2})
        linha=next(l for l in geometria['linhas'] if l['face']==('A',1))
        inv=grupo.matrix_world.inverted()
        projetar=lambda p:Vector(((inv@p).x,(inv@p).z))*1000
        alvo=addon.hud._acertar_linhas_hud(geometria,projetar(linha['pontos'][0])+Vector((1,10)),projetar,cantos=False)
        self.assertEqual(alvo['face'],('A',1))
        self.assertEqual(alvo['lado'],'min')
        gaveta=G.gavetas_do_grupo(grupo)[1]
        G.selecionar(bpy.context,gaveta,'GAVETA')
        geometria=addon.hud._geometria_do_item(grupo,'GAVETAS',[])
        self.assertEqual({l['face'][1] for l in geometria['linhas']},{1})
        self.assertEqual(len(geometria['linhas']),12)

    def test_previa_individual_nao_reconstroi_e_esc_restaura(self):
        grupo=self.gavetas()
        G.selecionar(bpy.context,G.gavetas_do_grupo(grupo)[1],'GAVETA')
        backup=G.copia(grupo)
        objetos=list(grupo.children_recursive)
        h=G.valor(grupo,('A',1))
        with patch.object(G,'montar',side_effect=AssertionError('Previa reconstruiu')):
            for delta in (10,20,30):
                self.assertIsNone(G.aplicar(bpy.context,grupo,('A',1),h+delta,'min',previa=True))
                G.linhas_hud(grupo,[])
        self.assertEqual(objetos,list(grupo.children_recursive))
        G.restaurar(backup)
        self.assertEqual(G.copia(grupo),backup)
        self.assertAlmostEqual(G.valor(grupo,('A',1)),h)
        self.assertEqual(bpy.context.object.get(G.CHAVE_INDICE),1)
        unica=self.gavetas(quantidade=1)
        backup=G.copia(unica)
        self.assertIsNone(G.aplicar(bpy.context,unica,('A',0),400,'max',previa=True))
        self.assertAlmostEqual(G.valor(unica,('A',0)),400)
        G.restaurar(backup)
        self.assertEqual(G.copia(unica),backup)

    def test_menu_da_unidade_mostra_medidas_e_escolhas_somente_dela(self):
        grupo=self.gavetas(proporcoes=[1,2,1])
        gaveta=G.gavetas_do_grupo(grupo)[1]
        G.selecionar(bpy.context,gaveta,'GAVETA')
        bpy.context.scene.cabinet_aba='GAVETAS'
        acoes=[v[5] for v in addon.gaveta._widgets_gaveta(bpy.context,480,1600) if v[5]]
        medidas={a[2]:a[4] for a in acoes if a[0]=='medida' and a[1]=='gavetas'}
        self.assertAlmostEqual(medidas['individual_1_altura'],G.valor(grupo,('A',1)))
        self.assertIn('individual_1_abaixo_mm',medidas)
        self.assertIn('individual_1_acima_mm',medidas)
        self.assertFalse(any(a[0]=='contador' and a[1]=='gavetas_quantidade' for a in acoes))
        self.assertTrue(any(a[0]=='escolha' and a[1]=='individual_1_trilho' for a in acoes))
        self.assertIsNone(addon.gaveta_eventos.aplicar_medida(bpy.context,'gavetas',grupo.name,'individual_1_altura',.300))
        self.assertAlmostEqual(G.valor(grupo,('A',1)),300)

    def test_edicao_preserva_madeira_abertura_e_puxador_individuais(self):
        grupo=self.gavetas()
        gaveta=G.gavetas_do_grupo(grupo)[1]
        G.colocar_puxador(gaveta,'ALCA')
        G.definir_abertura(gaveta,.4)
        material=bpy.data.materials.new('Madeira so desta gaveta')
        frente=G.frente_da_gaveta(gaveta)
        frente.data.materials.clear();frente.data.materials.append(material)
        frente.material_slots[0].link='OBJECT';frente.material_slots[0].material=material
        self.assertIsNone(G.editar_individual(bpy.context,grupo,1,'altura',260))
        gaveta=G.gavetas_do_grupo(grupo)[1]
        self.assertEqual(gaveta[G.CHAVE_PUXADOR],'ALCA')
        self.assertAlmostEqual(gaveta[G.CHAVE_ABERTURA],.4)
        self.assertEqual(G.frente_da_gaveta(gaveta).material_slots[0].material,material)
        self.assertEqual(G.frente_da_gaveta(gaveta).material_slots[0].link,'OBJECT')
        self.assertIsNone(G.editar_individual(bpy.context,grupo,1,'puxador','PERFIL'))
        self.assertEqual(G.gavetas_do_grupo(grupo)[1][G.CHAVE_PUXADOR],'PERFIL')

    def test_botao_normaliza_alturas_preservando_total_folgas_e_ajustes(self):
        grupo = self.gavetas(proporcoes=[1,2,1])
        self.assertIsNone(G.editar_individual(bpy.context,grupo,1,'profundidade_mm',450))
        self.assertIsNone(G.editar_individual(bpy.context,grupo,1,'trilho','OCULTO'))
        self.assertIsNone(G.editar_individual(bpy.context,grupo,1,'recuo_mm',15))
        self.assertIsNone(G.editar_individual(bpy.context,grupo,1,'acima_mm',7))
        self.assertIsNone(G.editar_individual(bpy.context,grupo,1,'puxador','ALCA'))
        gaveta = G.gavetas_do_grupo(grupo)[1]
        G.definir_abertura(gaveta,.4)
        material = bpy.data.materials.new('Madeira individual normalizada')
        frente = G.frente_da_gaveta(gaveta)
        frente.data.materials.append(material)
        frente.material_slots[-1].link='OBJECT'
        frente.material_slots[-1].material=material
        G.selecionar(bpy.context,gaveta,'GAVETA')
        bpy.context.scene.cabinet_aba='GAVETAS'
        for largura in (180,320,540):
            widgets=addon.gaveta._widgets_gaveta(bpy.context,largura,1600)
            botao,=[v for v in widgets if v[5]==('operador','object.cabinet_normalizar_gavetas')]
            self.assertEqual(botao[4],'Normalizar alturas')
            for campo in [v for v in widgets if v[5] and v[5][0]=='medida']:
                sobrepoe=(botao[0]<campo[0]+campo[2] and campo[0]<botao[0]+botao[2]
                          and botao[1]<campo[1]+campo[3] and campo[1]<botao[1]+botao[3])
                self.assertFalse(sobrepoe)
        medidas=G.medidas(grupo)
        parametros=G.parametros(grupo)
        frentes=G.frentes(*G.vao(grupo)[:2],parametros)
        self.assertIn(G.OBJECT_OT_normalizar_gavetas,addon.CLASSES)
        self.assertEqual(bpy.ops.object.cabinet_normalizar_gavetas(),{'FINISHED'})
        novos=G.frentes(*G.vao(grupo)[:2],G.parametros(grupo))
        alturas=[f[3]-f[2] for f in novos]
        self.assertLess(max(alturas)-min(alturas),1e-4)
        self.assertEqual(G.medidas(grupo),medidas)
        self.assertAlmostEqual(novos[0][2],frentes[0][2])
        self.assertAlmostEqual(novos[-1][3],frentes[-1][3])
        self.assertEqual(G.parametros(grupo)['individuais'],parametros['individuais'])
        self.assertEqual(G.folgas(G.parametros(grupo)),G.folgas(parametros))
        gaveta=G.gavetas_do_grupo(grupo)[1]
        self.assertEqual(bpy.context.object,gaveta)
        self.assertAlmostEqual(gaveta[G.CHAVE_ABERTURA],.4)
        self.assertEqual(gaveta[G.CHAVE_PUXADOR],'ALCA')
        self.assertEqual(G.frente_da_gaveta(gaveta).material_slots[-1].material,material)
        G.selecionar(bpy.context,grupo,'GRUPO')
        self.assertTrue(any(v[5]==('operador','object.cabinet_normalizar_gavetas')
                            for v in addon.gaveta._widgets_gaveta(bpy.context,320,1400)))

    def test_normalizar_que_nao_cabe_preserva_estado_e_uma_so_nao_tem_botao(self):
        grupo = G.criar_gavetas(bpy.context,self.conj,(18,18,18,432,0),
                               dict(quantidade=3,profundidade_mm=560,proporcoes=[1.2,1,1.2]))
        estado=G.copia(grupo)
        objetos=list(grupo.children_recursive)
        self.assertIsNotNone(G.normalizar_alturas(grupo))
        self.assertEqual(G.copia(grupo),estado)
        self.assertEqual(list(grupo.children_recursive),objetos)
        unica=self.gavetas(quantidade=1)
        G.selecionar(bpy.context,unica,'GRUPO')
        bpy.context.scene.cabinet_aba='GAVETAS'
        self.assertFalse(G.OBJECT_OT_normalizar_gavetas.poll(bpy.context))
        self.assertFalse(any(v[5]==('operador','object.cabinet_normalizar_gavetas')
                             for v in addon.gaveta._widgets_gaveta(bpy.context,320,1400)))

addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestGavetas)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de gavetas')
