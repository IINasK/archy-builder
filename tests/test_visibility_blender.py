"""Visibilidade por categoria sem retirar a geometria do snap nativo."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon
V = addon.visibilidade


class TestVisibilidade(unittest.TestCase):
    def setUp(self):
        V.suspender()
        addon.eventos._fim_do_desfazer()
        addon.areas_criacao.esquecer()
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        self.modulo = addon.modulos.criar_armario(bpy.context, 'Teste visual', 900, 1400, 550)

    def tearDown(self):
        V.suspender()

    def selecionar(self, obj):
        for o in bpy.context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

    def portas(self):
        grupo = addon.portas.porta_no_modulo(self.modulo, folhas=2)
        addon.puxadores.perfis_na_porta(bpy.context, grupo, 'CIMA')
        self.selecionar(self.modulo)
        return grupo

    def extra(self, nome='Extra'):
        obj = bpy.data.objects.new(nome, bpy.data.meshes.new(nome))
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.update()
        return obj

    def contexto_edicao(self):
        area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        regiao = next(r for r in area.regions if r.type == 'WINDOW')
        return bpy.context.temp_override(area=area, region=regiao)

    def iniciar_edicao(self):
        bpy.context.scene.cabinet_aba = 'PORTAS'
        self.selecionar(self.modulo)
        class Contexto:
            window_manager = SimpleNamespace(modal_handler_add=lambda op: None)
            def __getattr__(self, nome):
                return getattr(bpy.context, nome)
        return V.OBJECT_OT_editar_grupo_visual.invoke(SimpleNamespace(), Contexto(), None)

    def evento(self, tipo, valor='PRESS', dentro=True):
        r = bpy.context.region
        return SimpleNamespace(type=tipo, value=valor, mouse_x=r.x+20 if dentro else -10, mouse_y=r.y+20)

    def test_categorias_isoladas_internos_unificados_e_ferragens_sem_acao(self):
        self.portas()
        gav = addon.gavetas.criar_gavetas(bpy.context,self.modulo,(18,18,18,700,0),dict(quantidade=2,profundidade_mm=500))
        pr = addon.prateleiras.criar_prateleiras(bpy.context,self.modulo,(18,18,700,18,0),dict(quantidade=1,profundidade_mm=500))
        div = addon.divisorias.criar_divisorias(bpy.context,self.modulo,(18,18,700,18,0),dict(quantidade=1,profundidade_mm=500))
        internos = V.membros(bpy.context,self.modulo,'INTERNOS')
        self.assertTrue(any(o in pr.children_recursive for o in internos))
        self.assertTrue(any(o in div.children_recursive for o in internos))
        self.assertFalse(set(internos) & set(V.membros(bpy.context,self.modulo,'GAVETAS')))
        V.definir(bpy.context,self.modulo,'GAVETAS',True)
        self.assertTrue(all(V.esmaecido(o) for o in V._fisicas(gav.children_recursive)))
        self.assertTrue(all(not V.esmaecido(o) for o in internos))
        for aba in ('PRATELEIRAS','DIVISORIAS'):
            bpy.context.scene.cabinet_aba=aba
            self.assertEqual(V.categoria(bpy.context),'INTERNOS')
        bpy.context.scene.cabinet_aba='PUXADORES'
        self.assertFalse(V.OBJECT_OT_alternar_partes.poll(bpy.context))

    def test_portas_agregados_esmaecem_sem_modificar_malha_material_ou_snap(self):
        grupo = self.portas()
        obj = next(o for o in grupo.children_recursive if addon.chapas.MARCA_FOLHA in o)
        obj.color=(.2,.3,.4,1)
        cor=tuple(obj.color); malha=obj.data; matriz=obj.matrix_world.copy()
        vertices=[tuple(v.co) for v in obj.data.vertices]
        materiais=list(obj.material_slots)
        V.definir(bpy.context,self.modulo,'PORTAS',True)
        esperados=V._fisicas(grupo.children_recursive)
        self.assertTrue(any(o.get('eh_puxador') for o in esperados))
        self.assertTrue(all(V.esmaecido(o) for o in esperados))
        self.assertTrue(all(o.visible_get() and not o.hide_select for o in esperados))
        estado={};addon.gavetas.fixar_modulo_criacao(estado,self.modulo)
        self.assertTrue(all(o.name in estado['alvos_snap'] for o in esperados))
        self.assertIs(obj.data,malha);self.assertEqual(obj.matrix_world,matriz)
        self.assertEqual([tuple(v.co) for v in obj.data.vertices],vertices)
        self.assertEqual(list(obj.material_slots),materiais)
        self.assertEqual(tuple(obj.color),(1,1,1,1))
        V.definir(bpy.context,self.modulo,'PORTAS',False)
        self.assertEqual(tuple(obj.color),cor)
        self.assertFalse(any(V.ORIGINAL in o for o in esperados))

    def test_ocultacao_nativa_independente_e_rig_preservado(self):
        grupo=self.portas()
        obj=next(o for o in grupo.children_recursive if addon.chapas.MARCA_FOLHA in o)
        obj.hide_set(True)
        antes={o.name:(o.hide_get(),o.hide_viewport,o.hide_render,o.hide_select) for o in grupo.children_recursive}
        for esconder in (True,False):
            V.definir(bpy.context,self.modulo,'PORTAS',esconder)
            self.assertEqual(antes,{o.name:(o.hide_get(),o.hide_viewport,o.hide_render,o.hide_select) for o in grupo.children_recursive})
        V.definir(bpy.context,self.modulo,'PORTAS',True)
        obj.hide_set(False);V.verificar()
        self.assertTrue(obj.visible_get())
        obj.hide_set(True);V.verificar()
        self.assertTrue(obj.hide_get())

    def test_estrutura_e_fundo_tem_grupos_distintos(self):
        corpo=set(V.membros(bpy.context,self.modulo,'MODULOS'))
        fundos=set(V.membros(bpy.context,self.modulo,'FUNDOS'))
        self.assertTrue(corpo);self.assertTrue(fundos);self.assertFalse(corpo&fundos)
        V.definir(bpy.context,self.modulo,'FUNDOS',True)
        self.assertTrue(all(V.esmaecido(o) for o in fundos))
        self.assertTrue(all(not V.esmaecido(o) for o in corpo))

    def test_configuracao_por_uid_inclui_filhos_retira_padrao_e_conserva_parentesco(self):
        grupo=self.portas();extra=self.extra();filho=self.extra('Filho');filho.parent=extra
        V.configurar(bpy.context,self.modulo,'PORTAS',extra,True)
        extra.name='Extra renomeado'
        V.definir(bpy.context,self.modulo,'PORTAS',True)
        self.assertTrue(V.esmaecido(extra));self.assertTrue(V.esmaecido(filho))
        self.assertIsNone(extra.parent);self.assertIs(filho.parent,extra)
        folha=next(o for o in grupo.children_recursive if addon.chapas.MARCA_FOLHA in o)
        V.configurar(bpy.context,self.modulo,'PORTAS',folha,False)
        self.assertFalse(V.esmaecido(folha));self.assertIsNotNone(folha.parent)
        V.configurar(bpy.context,self.modulo,'PORTAS',extra,False)
        self.assertFalse(V.esmaecido(extra));self.assertFalse(V.esmaecido(filho))

    def test_grupos_sobrepostos_so_restauram_no_ultimo(self):
        extra=self.extra()
        for tipo in ('PORTAS','GAVETAS'):
            V.configurar(bpy.context,self.modulo,tipo,extra,True)
            V.definir(bpy.context,self.modulo,tipo,True)
        V.definir(bpy.context,self.modulo,'PORTAS',False)
        self.assertTrue(V.esmaecido(extra))
        V.definir(bpy.context,self.modulo,'GAVETAS',False)
        self.assertFalse(V.esmaecido(extra))

    def test_preferencias_nativas_de_arame_sao_restauradas(self):
        self.portas()
        with self.contexto_edicao():
            s=bpy.context.space_data
            anterior=(s.shading.wireframe_color_type,s.overlay.wireframe_opacity)
            V.definir(bpy.context,self.modulo,'PORTAS',True)
            self.assertEqual(s.shading.wireframe_color_type,'OBJECT')
            self.assertAlmostEqual(s.overlay.wireframe_opacity,.22)
            V.definir(bpy.context,self.modulo,'PORTAS',False)
            self.assertEqual((s.shading.wireframe_color_type,s.overlay.wireframe_opacity),anterior)

    def test_alteracoes_manuais_de_exibicao_nao_sao_sobrescritas_na_saida(self):
        self.portas()
        with self.contexto_edicao():
            s=bpy.context.space_data
            V.definir(bpy.context,self.modulo,'PORTAS',True)
            obj=V.membros(bpy.context,self.modulo,'PORTAS')[0]
            obj.display_type='SOLID';obj.color=(.5,.5,.5,1)
            s.shading.wireframe_color_type='THEME';s.overlay.wireframe_opacity=.6
            V.definir(bpy.context,self.modulo,'PORTAS',False)
            self.assertEqual(obj.display_type,'SOLID');self.assertEqual(tuple(obj.color),(.5,.5,.5,1))
            self.assertEqual(s.shading.wireframe_color_type,'THEME')
            self.assertAlmostEqual(s.overlay.wireframe_opacity,.6)

    def test_verificador_respeita_guarda_undo_e_aceita_peca_removida(self):
        self.portas();V.definir(bpy.context,self.modulo,'PORTAS',True)
        obj=V.membros(bpy.context,self.modulo,'PORTAS')[0]
        bpy.data.objects.remove(obj,do_unlink=True)
        with patch.object(addon.eventos,'_desfazendo',[True]),patch.object(V,'membros',side_effect=AssertionError('Leu dados no undo')):
            V.verificar()
        V.verificar()

    def test_salvar_suspende_visual_e_retomar_reaplica_sem_perder_configuracao(self):
        self.portas();V.definir(bpy.context,self.modulo,'PORTAS',True)
        objetos=V.membros(bpy.context,self.modulo,'PORTAS')
        V.suspender()
        self.assertTrue(V.ativo(self.modulo,'PORTAS'))
        self.assertTrue(all(not V.esmaecido(o) for o in objetos))
        V.retomar()
        self.assertTrue(all(V.esmaecido(o) for o in objetos))
        self.assertIn(V.OBJECT_OT_alternar_partes,addon.CLASSES)
        self.assertIn(V.OBJECT_OT_editar_grupo_visual,addon.CLASSES)
        self.assertTrue(all(f in getattr(bpy.app.handlers,e) for e,f in V.HANDLERS))

    def test_editor_usa_selecao_nativa_esquerdo_inclui_direito_retira(self):
        extra=self.extra()
        with self.contexto_edicao():
            self.assertEqual(self.iniciar_edicao(),{'RUNNING_MODAL'})
            self.assertFalse(addon.selecao.OBJECT_OT_selecionar.poll(bpy.context))
            self.assertFalse(addon.hud._contexto_hud(bpy.context))
            with patch.object(V,'_selecionar_nativo',return_value=extra) as nativo:
                self.selecionar(extra)
                for tipo,incluir in (('LEFTMOUSE',True),('RIGHTMOUSE',False)):
                    self.assertEqual(V.OBJECT_OT_editar_grupo_visual.modal(None,bpy.context,self.evento(tipo)),{'RUNNING_MODAL'})
                    self.assertEqual(extra in V.membros(bpy.context,self.modulo,'PORTAS'),incluir)
                self.assertEqual(nativo.call_count,2)
            self.assertEqual(V.OBJECT_OT_editar_grupo_visual.modal(None,bpy.context,self.evento('RET')),{'FINISHED'})
            self.assertIsNone(V._edicao[0]);self.assertIs(bpy.context.object,self.modulo)

    def test_editor_esc_restaura_e_menu_nao_rouba_cliques(self):
        extra=self.extra()
        with self.contexto_edicao():
            self.iniciar_edicao()
            V.configurar(bpy.context,self.modulo,'PORTAS',extra,True)
            with patch.object(V,'_selecionar_nativo',side_effect=AssertionError('Selecionou fora da viewport')):
                self.assertEqual(V.OBJECT_OT_editar_grupo_visual.modal(None,bpy.context,self.evento('LEFTMOUSE',dentro=False)),{'PASS_THROUGH'})
            self.assertEqual(V.OBJECT_OT_editar_grupo_visual.modal(None,bpy.context,self.evento('ESC')),{'CANCELLED'})
            self.assertNotIn(extra,V.membros(bpy.context,self.modulo,'PORTAS'))

    def test_faixa_desabilita_ferragens_e_nao_e_painel_opcoes(self):
        bpy.context.scene.cabinet_aba='MODULOS'
        for largura in (220,320,540):
            itens=addon.gaveta._widgets_gaveta(bpy.context,largura,900,0,0)
            rodape=addon.gaveta._partes_gaveta(itens)[2]
            self.assertIsNone(addon.gaveta._retangulo_painel_opcoes(rodape))
            self.assertEqual(len([v for v in rodape if V.eh_acao(v[5])]),2)
        bpy.context.scene.cabinet_aba='PUXADORES'
        self.assertFalse(V.OBJECT_OT_editar_grupo_visual.poll(bpy.context))

    def test_faixa_segue_referencia_com_rotulo_e_dois_icones_compactos_a_direita(self):
        bpy.context.scene.cabinet_aba='MODULOS'
        for largura in (196,296,456):
            itens=V.widgets(bpy.context,12,largura,900)
            botoes=[v for v in itens if V.eh_acao(v[5])]
            rotulo=next(v for v in itens if v[5]==('rotulo',))
            self.assertEqual(rotulo[4],'Visibilidade de objetos' if largura>=260 else 'Visibilidade')
            self.assertLessEqual(rotulo[0]+rotulo[2]+6,botoes[0][0])
            self.assertTrue(all(v[2:4]==(36,30) and not v[4] for v in botoes))
            self.assertEqual(botoes[-1][0]+botoes[-1][2],12+largura)
            self.assertTrue(all(addon.gaveta_eventos._centro_icone(*v[:4],v[5])==(v[0]+18,v[1]+15) for v in botoes))

    def test_moldura_com_bases_e_trilhos_da_porta_pesada_pertence_ao_grupo(self):
        grupo=addon.portas.porta_no_modulo(self.modulo,folhas=2,abertura='CORRER',
            moldura_mm=15,rodape_mm=100,testeira_mm=80)
        pecas=V._fisicas(grupo.children_recursive)
        self.assertTrue(any(addon.chapas.MARCA_MOLDURA in o for o in pecas))
        V.definir(bpy.context,self.modulo,'PORTAS',True)
        self.assertTrue(all(V.esmaecido(o) for o in pecas))
        estado={};addon.gavetas.fixar_modulo_criacao(estado,self.modulo)
        self.assertTrue(all(o.name in estado['alvos_snap'] for o in pecas))

    def test_alvo_extra_esmaecido_tambem_participa_do_snap_do_modulo(self):
        extra=self.extra()
        V.configurar(bpy.context,self.modulo,'PORTAS',extra,True)
        V.definir(bpy.context,self.modulo,'PORTAS',True)
        estado={};addon.gavetas.fixar_modulo_criacao(estado,self.modulo)
        self.assertIn(extra.name,estado['alvos_snap'])
        self.assertIsNone(extra.parent)

    def test_raio_superficial_atravessa_porta_mas_malha_continua_no_motor_nativo(self):
        self.portas()
        origem=Vector((.1,-2,.7));direcao=Vector((0,1,0))
        bpy.context.view_layer.update()
        antes=addon.gavetas.raio_no_modulo(bpy.context,self.modulo,origem,direcao)
        self.assertIn(addon.chapas.MARCA_FOLHA,antes[0])
        V.definir(bpy.context,self.modulo,'PORTAS',True)
        depois=addon.gavetas.raio_no_modulo(bpy.context,self.modulo,origem,direcao)
        self.assertNotIn(addon.chapas.MARCA_FOLHA,depois[0])
        obj=antes[0];inv=obj.matrix_world.inverted_safe()
        hit,*_=obj.ray_cast(inv@origem,(inv.to_3x3()@direcao).normalized())
        self.assertTrue(hit)
        with self.contexto_edicao(),patch.object(addon.hud.view3d_utils,'region_2d_to_origin_3d',return_value=origem), \
             patch.object(addon.hud.view3d_utils,'region_2d_to_vector_3d',return_value=direcao):
            acerto=addon.hud._raio_cru(bpy.context,(20,20))
            self.assertNotIn(addon.chapas.MARCA_FOLHA,acerto[0])

    def test_faixa_com_biblioteca_em_cima_some_sem_selecao_e_volta_no_modulo(self):
        bpy.context.scene.cabinet_aba='MODULOS'
        chave=addon.biblioteca_faixa.CHAVE_LAYOUT
        antes=bpy.context.screen.get(chave)
        self.addCleanup(lambda:bpy.context.screen.pop(chave,None) if antes is None else bpy.context.screen.__setitem__(chave,antes))
        bpy.context.screen[chave]=2
        for obj in bpy.context.selected_objects:obj.select_set(False)
        bpy.context.view_layer.objects.active=None
        for altura in (240,900):
            itens=addon.gaveta._widgets_gaveta(bpy.context,220,altura,0,0)
            faixa=[v for v in itens if V.eh_acao(v[5])]
            self.assertFalse(faixa)
            self.assertFalse(V.OBJECT_OT_alternar_partes.poll(bpy.context))
        self.selecionar(self.modulo)
        faixa=V.widgets(bpy.context,12,196,900)
        self.assertEqual(faixa[0][1],addon.gaveta.ALTURA_RODAPE_GAVETA+4)

    def test_editor_cancela_captura_e_visibilidade_sobrevive_ao_cancelamento(self):
        self.portas();V.definir(bpy.context,self.modulo,'PORTAS',True)
        estados=(addon.gavetas._assistente_gavetas,addon.prateleiras._assistente_prateleiras,
                 addon.divisorias._assistente_divisorias,addon.fundos._assistente_fundo,addon.portas._assistente_porta)
        for estado in estados:
            estado[0]={'modulo':self.modulo.name}
            self.addCleanup(estado.__setitem__,0,None)
        with self.contexto_edicao():
            self.iniciar_edicao()
            self.assertTrue(all(estado[0]['cancelar'] for estado in estados))
            V.OBJECT_OT_editar_grupo_visual.cancel(None,bpy.context)
            addon.areas_criacao.esquecer()
            self.assertTrue(V.ativo(self.modulo,'PORTAS'))
            self.assertTrue(all(V.esmaecido(o) for o in V.membros(bpy.context,self.modulo,'PORTAS')))

    def test_editor_repassa_navegacao_e_segundo_clique_no_lapis_conclui(self):
        with self.contexto_edicao():
            self.iniciar_edicao()
            for evento in ('MIDDLEMOUSE','WHEELUPMOUSE','WHEELDOWNMOUSE','NDOF_MOTION','ACCENT_GRAVE'):
                self.assertEqual(V.OBJECT_OT_editar_grupo_visual.modal(None,bpy.context,self.evento(evento)),{'PASS_THROUGH'})
            self.assertEqual(V.OBJECT_OT_editar_grupo_visual.invoke(None,bpy.context,None),{'FINISHED'})
            self.assertEqual(V.OBJECT_OT_editar_grupo_visual.modal(None,bpy.context,self.evento('MOUSEMOVE')),{'FINISHED'})

    def test_faixa_coberta_por_opcoes_nao_recebe_clique_e_barra_curta_tem_curso(self):
        g=addon.gaveta;chave=g._CHAVE_OPCOES;antes=bpy.context.screen.get(chave)
        self.addCleanup(lambda:bpy.context.screen.pop(chave,None) if antes is None else bpy.context.screen.__setitem__(chave,antes))
        bpy.context.screen[chave]=1
        class Contexto:
            region=SimpleNamespace(width=220,height=500)
            def __getattr__(self,nome):return getattr(bpy.context,nome)
        contexto=Contexto()
        rodape=g._partes_gaveta(g._widgets_gaveta(contexto,220,500,0,0))[2]
        px,py,pw,ph=g._retangulo_painel_opcoes(rodape)
        interativos=g._widgets_interativos(contexto)
        for v in rodape:
            if V.eh_acao(v[5]) and v[1]<py+ph and py<v[1]+v[3]:
                self.assertNotIn(v,interativos)
        base,tamanho=g._alca_rolagem(0,25,300,0)
        self.assertGreater(base,1);self.assertLess(tamanho,25)

    def test_editor_com_erro_restaura_selecao_e_libera_hud(self):
        with self.contexto_edicao():
            self.iniciar_edicao()
            with patch.object(V,'_selecionar_nativo',side_effect=RuntimeError('Objeto indisponivel')):
                with self.assertRaises(RuntimeError):
                    V.OBJECT_OT_editar_grupo_visual.modal(None,bpy.context,self.evento('LEFTMOUSE'))
            self.assertIsNone(V._edicao[0]);self.assertIs(bpy.context.object,self.modulo)
            self.assertTrue(addon.selecao.OBJECT_OT_selecionar.poll(bpy.context))

    def test_arame_ativa_overlays_temporariamente_quando_antes_estavam_desligados(self):
        self.portas()
        with self.contexto_edicao():
            overlay=bpy.context.space_data.overlay;antes=overlay.show_overlays
            self.addCleanup(setattr,overlay,'show_overlays',antes)
            overlay.show_overlays=False
            V.definir(bpy.context,self.modulo,'PORTAS',True)
            self.assertTrue(overlay.show_overlays)
            V.definir(bpy.context,self.modulo,'PORTAS',False)
            self.assertFalse(overlay.show_overlays)

    def test_arquivo_salvo_conserva_configuracao_sem_gravar_aparencia_temporaria(self):
        self.portas();V.definir(bpy.context,self.modulo,'PORTAS',True)
        nome=self.modulo.name
        with tempfile.TemporaryDirectory(prefix='visual_blend_') as pasta:
            caminho=os.path.join(pasta,'teste.blend')
            # Copia mantem o arquivo atual distinto; o 4.2 cai ao relinka-lo em si.
            bpy.ops.wm.save_as_mainfile(filepath=caminho,copy=True,relative_remap=False)
            self.assertTrue(all(V.esmaecido(o) for o in V.membros(bpy.context,self.modulo,'PORTAS')))
            # Ler como biblioteca nao executa o timer do add-on na copia.
            with bpy.data.libraries.load(caminho,link=False) as (origem,destino):
                destino.objects=list(origem.objects)
            copia=next(o for o in destino.objects if o and V.ATIVOS in o)
            self.assertTrue(V.ativo(copia,'PORTAS'))
            self.assertFalse(any(V.ORIGINAL in o for o in destino.objects if o))
            for obj in destino.objects:
                if obj:bpy.data.objects.remove(obj,do_unlink=True)
        self.assertEqual(self.modulo.name,nome)

    def test_faixa_fixa_nao_desaparece_sem_portas_ou_apos_cancelar_criacao(self):
        # Regressao 387: o olho 386 dependia de portas e da captura em andamento.
        addon.areas_criacao.esquecer()
        posicoes = []
        for aba in ('MODULOS', 'PORTAS', 'FUNDOS', 'GAVETAS', 'PRATELEIRAS', 'PUXADORES'):
            bpy.context.scene.cabinet_aba = aba
            for rolagem in (0, 300):
                itens = addon.gaveta._widgets_gaveta(bpy.context, 320, 900, rolagem, 0)
                faixa = [v for v in itens if v[5] and v[5][:2] in (
                    ('operador', 'object.cabinet_alternar_partes'),
                    ('operador', 'object.cabinet_editar_grupo_visual'))]
                if aba=='PUXADORES':
                    self.assertFalse(faixa)
                    continue
                self.assertEqual(len(faixa), 2)
                self.assertEqual(faixa[0][1], faixa[1][1])
                self.assertLess(faixa[0][0] + faixa[0][2], faixa[1][0])
                self.assertEqual(faixa[-1][0] + faixa[-1][2], 308)
                posicoes.append(faixa[0][1])
        self.assertEqual(len(set(posicoes)), 1)

    def test_faixa_nao_aparece_para_objeto_comum_ferragem_ou_sem_selecao(self):
        bpy.context.scene.cabinet_aba='PORTAS'
        comum=self.extra()
        self.selecionar(comum)
        self.assertFalse(V.widgets(bpy.context,12,296,900))
        self.assertEqual(V.altura(bpy.context),0)
        grupo=self.portas()
        puxador=next(o for o in grupo.children_recursive if addon.chapas.MARCA_PUXADOR in o)
        self.selecionar(puxador)
        self.assertFalse(V.widgets(bpy.context,12,296,900))
        folha=next(o for o in grupo.children_recursive if addon.chapas.MARCA_FOLHA in o)
        self.selecionar(folha)
        self.assertTrue(V.widgets(bpy.context,12,296,900))
        folha.select_set(False)
        self.assertFalse(V.widgets(bpy.context,12,296,900))


with tempfile.TemporaryDirectory(prefix='visibilidade_') as pasta, \
     patch.object(addon.opcoes, '_pasta_addon', return_value=pasta), \
     patch.object(addon.biblioteca, 'pasta_biblioteca', return_value=pasta):
    addon.register()
    try:
        resultado = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(TestVisibilidade))
    finally:
        addon.unregister()
    if not resultado.wasSuccessful():
        raise RuntimeError('Falha na visibilidade por categoria')
