"""Areas livres retangulares: forma fixa, HUD nativa e entrega aos dominios."""
import os
import sys
import math
import tempfile
from itertools import permutations
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon
A = addon.areas_criacao


class TestAreasCriacao(unittest.TestCase):
    def setUp(self):
        addon.eventos._fim_do_desfazer()
        A.esquecer()
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        self.modulo = addon.modulos.criar_armario(bpy.context, 'Armario de teste', 1000, 1400, 600)
        self.area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        self.regiao = next(r for r in self.area.regions if r.type == 'WINDOW')

    def tearDown(self):
        addon.hud_volume.terminar()
        A.esquecer()

    def referencia(self, destino='GAVETAS'):
        ponto = self.modulo.matrix_world @ Vector((-.3, -.28, .2))
        obj = A.criar_referencia(bpy.context, destino, ponto, self.modulo)
        A._estado[0] = dict(objeto=obj.name, destino=destino, modulo=self.modulo.name,
            cena=bpy.context.scene.name, area=self.area.as_pointer(), handler=None, timer=None,
            selecao=[self.modulo.name], ativo=self.modulo.name, frente='Y-')
        A.aplicar(bpy.context, obj, ('L',), 400)
        A.aplicar(bpy.context, obj, ('A',), 600)
        if not obj['area_plana']:
            A.aplicar(bpy.context, obj, ('P',), 400)
        return obj

    def portas(self):
        grupo=addon.portas.porta_no_modulo(self.modulo,folhas=2)
        addon.puxadores.perfis_na_porta(bpy.context,grupo,'CIMA')
        for obj in bpy.context.selected_objects:obj.select_set(False)
        self.modulo.select_set(True);bpy.context.view_layer.objects.active=self.modulo
        self.addCleanup(lambda valor=bpy.context.scene.cabinet_aba:
                        setattr(bpy.context.scene,'cabinet_aba',valor))
        self.addCleanup(addon.perguntas._pergunta_atual.__setitem__,0,None)
        return grupo

    def test_criar_internos_pergunta_sim_nao_antes_da_captura(self):
        grupo=self.portas()
        comandos=('object.cabinet_criar_gavetas','object.cabinet_criar_prateleiras',
                  'object.cabinet_criar_divisorias','object.cabinet_internos')
        for comando in comandos:
            with self.subTest(comando=comando):
                if comando=='object.cabinet_internos':
                    resultado=bpy.ops.object.cabinet_internos()
                else:
                    tipo=next(t for t,c in A.DESTINOS.items() if c==comando)
                    resultado=addon.gavetas.AssistenteDoVao.invoke(SimpleNamespace(ABA=tipo),bpy.context,None)
                    self.assertIn('portas_verificadas',getattr(bpy.ops.object,comando.split('.')[1]).get_rna_type().properties)
                self.assertEqual(resultado,{'FINISHED'})
                pergunta=addon.perguntas._pergunta_atual[0]
                self.assertEqual(pergunta['texto'],'Esconder portas?')
                self.assertEqual([o[0] for o in pergunta['opcoes']],['Sim','Nao'])
                self.assertTrue(all(o[2]=='object.cabinet_portas_internos' for o in pergunta['opcoes']))
                self.assertIsNone(addon.gavetas._assistente_gavetas[0])
                self.assertIsNone(addon.prateleiras._assistente_prateleiras[0])
                self.assertIsNone(addon.divisorias._assistente_divisorias[0])
                self.assertTrue(A.portas_visiveis(bpy.context,A.portas_do_interno(bpy.context)))

    def test_sim_oculta_so_portas_e_agregados_do_modulo_e_continua(self):
        grupo=self.portas()
        outro=addon.modulos.criar_armario(bpy.context,'Outro armario',600,700,550)
        portas_outro=addon.portas.porta_no_modulo(outro)
        for obj in bpy.context.selected_objects:obj.select_set(False)
        self.modulo.select_set(True);bpy.context.view_layer.objects.active=self.modulo
        objetos=A.portas_do_interno(bpy.context)
        self.assertTrue(A.perguntar_portas(bpy.context,'object.cabinet_criar_gavetas'))
        with patch.object(addon.editor,'executar',return_value={'RUNNING_MODAL'}) as executar:
            # O respondedor existente chama a continuacao pelo editor.
            props=addon.perguntas._pergunta_atual[0]['opcoes'][0][3]
            self.assertEqual(bpy.ops.object.cabinet_portas_internos(**props),{'FINISHED'})
            executar.assert_called_once_with(bpy.context,'object.cabinet_criar_gavetas',portas_verificadas=True)
        self.assertTrue(all(addon.visibilidade.esmaecido(o) for o in objetos
            if o.type == 'MESH' and o.get('cabinet_peca') not in addon.ferragens.PECAS_OCULTAS_RIG))
        self.assertTrue(any(o.visible_get() for o in portas_outro.children_recursive if o.type=='MESH'))
        self.assertTrue(all(not o.hide_get() for o in addon.modulos._chapas_do_conjunto(self.modulo)))

    def test_nao_preserva_ocultacao_nativa_e_continua_sem_nova_pergunta(self):
        self.portas()
        objetos=A.portas_do_interno(bpy.context)
        uma=next(o for o in objetos if addon.chapas.MARCA_FOLHA in o)
        uma.hide_set(True)
        antes={o.name:o.hide_get() for o in objetos}
        self.assertTrue(A.perguntar_portas(bpy.context,'object.cabinet_criar_gavetas'))
        props=addon.perguntas._pergunta_atual[0]['opcoes'][1][3]
        with patch.object(addon.editor,'executar',return_value={'RUNNING_MODAL'}) as executar:
            bpy.ops.object.cabinet_portas_internos(**props)
            self.assertTrue(executar.call_args.kwargs['portas_verificadas'])
        self.assertEqual({o.name:o.hide_get() for o in objetos},antes)

    def test_olho_alterna_visibilidade_real_e_nao_mostra_controles_do_rig(self):
        self.portas()
        objetos=A.portas_do_interno(bpy.context)
        controles=[o for o in objetos if o.get('cabinet_peca') in addon.ferragens.PECAS_OCULTAS_RIG]
        self.assertTrue(controles)
        bpy.ops.object.cabinet_portas_internos()
        self.assertFalse(A.portas_visiveis(bpy.context,objetos))
        bpy.ops.object.cabinet_portas_internos()
        self.assertTrue(A.portas_visiveis(bpy.context,objetos))
        self.assertTrue(all(o.hide_get() for o in controles))
        folha=next(o for o in objetos if addon.chapas.MARCA_FOLHA in o)
        folha.hide_set(True)
        A.verificar()
        self.assertTrue(folha.hide_get())
        for obj in objetos:
            if obj not in controles:obj.hide_set(False)
        A.verificar()
        self.assertTrue(all(not o.hide_get() for o in objetos if o not in controles))

    def test_olho_fixo_reserva_linha_propria_e_muda_icone(self):
        self.portas()
        for aba in ('GAVETAS','PRATELEIRAS','DIVISORIAS'):
            for largura in (220,480):
                with self.subTest(aba=aba,largura=largura):
                    bpy.context.scene.cabinet_aba=aba
                    widgets=addon.gaveta._widgets_gaveta(bpy.context,largura,900,0,0)
                    olho=next(v for v in widgets if v[5] and v[5][:2]==('operador',addon.visibilidade.ALTERNAR))
                    editar=next(v for v in widgets if v[5] and v[5][:2]==('operador',addon.visibilidade.EDITAR))
                    self.assertEqual(editar[1],olho[1])
                    self.assertEqual(olho[3],30)
                    self.assertEqual(addon.gaveta_eventos._icone_acao_gaveta(olho[5]),'HIDE_OFF')
        bpy.ops.object.cabinet_portas_internos()
        bpy.context.scene.cabinet_aba='PORTAS'
        itens=addon.visibilidade.widgets(bpy.context,12,300,900)
        self.assertEqual(addon.gaveta_eventos._icone_acao_gaveta(itens[0][5]),'HIDE_ON')

    def test_area_livre_mantem_olho_no_modulo_original_apos_mudar_selecao(self):
        self.portas()
        obj=self.referencia()
        self.assertIs(A.modulo_das_portas(bpy.context),self.modulo)
        bpy.ops.object.cabinet_portas_internos()
        self.assertFalse(A.portas_visiveis(bpy.context,A.portas_do_interno(bpy.context)))
        self.assertFalse(obj.hide_get())
        self.assertIs(bpy.context.object,obj)

    def test_sem_portas_pula_pergunta_e_conserva_faixa_fixa(self):
        self.assertFalse(A.perguntar_portas(bpy.context,'object.cabinet_criar_gavetas'))
        itens=addon.visibilidade.widgets(bpy.context,12,300,900)
        self.assertEqual(len([v for v in itens if addon.visibilidade.eh_acao(v[5])]),2)

    def test_limpar_criacao_descarta_pergunta_de_portas_sem_apagar_outras_perguntas(self):
        self.portas()
        A.perguntar_portas(bpy.context,'object.cabinet_criar_gavetas')
        A.esquecer()
        self.assertIsNone(addon.perguntas._pergunta_atual[0])
        addon.perguntas._perguntar(bpy.context,'Outra pergunta',[])
        pergunta=addon.perguntas._pergunta_atual[0]
        A.esquecer()
        self.assertIs(addon.perguntas._pergunta_atual[0],pergunta)

    def test_resposta_antiga_nao_afeta_outra_cena_ou_outro_modulo(self):
        self.portas()
        A.perguntar_portas(bpy.context,'object.cabinet_criar_gavetas')
        props=addon.perguntas._pergunta_atual[0]['opcoes'][0][3]
        outro=addon.modulos.criar_armario(bpy.context,'Alvo diferente',600,700,550)
        for obj in bpy.context.selected_objects:obj.select_set(False)
        outro.select_set(True);bpy.context.view_layer.objects.active=outro
        self.assertEqual(bpy.ops.object.cabinet_portas_internos(**props),{'CANCELLED'})
        self.assertTrue(A.portas_visiveis(bpy.context,A.portas_do_interno(bpy.context,self.modulo)))

    def test_volume_e_internos_perguntam_antes_de_criar_referencia(self):
        self.portas()
        for aba in ('GAVETAS','PRATELEIRAS'):
            bpy.context.scene.cabinet_aba=aba
            op=SimpleNamespace(destino='',portas_verificadas=False)
            self.assertEqual(A.OBJECT_OT_definir_area.invoke(op,bpy.context,None),{'FINISHED'})
            self.assertIsNone(A._estado[0])
            pergunta=addon.perguntas._pergunta_atual[0]
            self.assertEqual(pergunta['texto'],'Esconder portas?')
            if aba=='PRATELEIRAS':self.assertEqual(pergunta['opcoes'][0][3]['metodo'],'VOLUME')

    def test_pergunta_do_menu_fica_na_gaveta_com_as_duas_respostas(self):
        self.portas()
        addon.perguntas._na_gaveta[0]=True
        try:A.perguntar_portas(bpy.context,'object.cabinet_criar_gavetas')
        finally:addon.perguntas._na_gaveta[0]=False
        bpy.context.scene.cabinet_aba='GAVETAS'
        widgets=addon.gaveta._widgets_aba_gaveta(bpy.context,320,900,0)
        self.assertEqual([v[4] for v in widgets if v[5] and v[5][0]=='resposta'],['Sim','Nao'])
        self.assertIsNone(addon.gavetas._assistente_gavetas[0])

    def test_responder_no_menu_preserva_pergunta_de_tipo_no_mesmo_menu(self):
        self.portas()
        addon.perguntas._na_gaveta[0]=True
        try:A.iniciar_internos(bpy.context)
        finally:addon.perguntas._na_gaveta[0]=False
        self.assertEqual(bpy.ops.object.cabinet_responder_pergunta(opcao=1),{'FINISHED'})
        pergunta=addon.perguntas._pergunta_atual[0]
        self.assertEqual(pergunta['texto'],'Criar prateleiras ou divisorias?')
        self.assertTrue(pergunta['na_gaveta'])
        self.assertFalse(addon.perguntas._na_gaveta[0])

    def test_esconder_portas_com_folha_ativa_preserva_o_modulo_para_criar(self):
        self.portas()
        folha=next(o for o in A.portas_do_interno(bpy.context) if addon.chapas.MARCA_FOLHA in o)
        self.modulo.select_set(False);folha.select_set(True);bpy.context.view_layer.objects.active=folha
        bpy.ops.object.cabinet_portas_internos()
        self.assertTrue(addon.visibilidade.esmaecido(folha))
        self.assertFalse(folha.hide_get())
        self.assertIs(A.modulo_das_portas(bpy.context),self.modulo)

    def test_h_e_alt_h_nativos_nao_sao_desfeitos_pelo_criador(self):
        self.portas()
        objetos=A.portas_do_interno(bpy.context)
        folha=next(o for o in objetos if addon.chapas.MARCA_FOLHA in o)
        self.modulo.select_set(False);folha.select_set(True);bpy.context.view_layer.objects.active=folha
        with bpy.context.temp_override(area=self.area,region=self.regiao):
            bpy.ops.object.hide_view_set(unselected=False)
            A.verificar()
            self.assertTrue(folha.hide_get())
            bpy.ops.object.hide_view_clear(select=False)
        addon.ferragens.ocultar_pecas_do_rig()
        A.verificar()
        self.assertFalse(folha.hide_get())

    def test_olho_respeita_undo_redo_nativo_sem_referencias_globais(self):
        self.portas()
        nome=self.modulo.name
        folhas=[o.name for o in A.portas_do_interno(bpy.context) if addon.chapas.MARCA_FOLHA in o]
        bpy.ops.ed.undo_push(message='Portas visiveis')
        bpy.ops.object.cabinet_portas_internos()
        bpy.ops.ed.undo_push(message='Portas escondidas')
        self.modulo=None
        bpy.ops.ed.undo();addon.eventos._fim_do_desfazer()
        addon.visibilidade.verificar()
        self.assertTrue(all(not addon.visibilidade.esmaecido(bpy.data.objects[n]) for n in folhas))
        bpy.ops.ed.redo();addon.eventos._fim_do_desfazer()
        addon.visibilidade.verificar()
        self.assertTrue(all(addon.visibilidade.esmaecido(bpy.data.objects[n]) for n in folhas))
        self.modulo=bpy.data.objects[nome]

    # Regressao (era BUG, corrigido na 386): modal consumia H/Alt+H entre cliques.
    def test_captura_de_pontos_repassa_ocultacao_do_keymap_nativo(self):
        g=addon.gavetas
        self.assertFalse(g.evento_de_ocultacao(SimpleNamespace(),SimpleNamespace(type='TIMER')))
        evento=SimpleNamespace(type='H',value='PRESS',mouse_x=self.regiao.x+20,mouse_y=self.regiao.y+20)
        op=self.assistente_tres_pontos()
        for identificador in ('object.hide_view_set','object.hide_view_clear'):
            item=SimpleNamespace(idname=identificador)
            mapa=SimpleNamespace(keymap_items=SimpleNamespace(match_event=lambda e:item))
            contexto=SimpleNamespace(window_manager=SimpleNamespace(keyconfigs=SimpleNamespace(
                user=SimpleNamespace(keymaps={'Object Mode':mapa}))))
            self.assertTrue(g.evento_de_ocultacao(contexto,evento))
            with patch.object(g,'evento_de_ocultacao',return_value=True), \
                 patch.object(g,'evento_de_navegacao',return_value=False):
                self.assertEqual(op._modal(bpy.context,evento),{'PASS_THROUGH'})
            self.assertEqual(op._w['etapa'],'CANTO1')
            self.assertEqual(op._w['pontos'],[])

    def pontos_livres(self):
        return [self.modulo.matrix_world @ Vector(p) for p in
                ((-.25, -.2, .6), (.25, .05, .8), (.08, .15, .1))]

    def assistente_tres_pontos(self):
        op = addon.gavetas.AssistenteDoVao()
        op._area = self.area; op._regiao = self.regiao
        op._rv3d = self.area.spaces.active.region_3d
        op._w = dict(etapa='CANTO1', volume_3d=True, pontos=[], nomes=[],
            p=dict(addon.gavetas.PARAMETROS_PADRAO), modulo='', mouse=None)
        self.addCleanup(op.cancel, bpy.context)
        return op

    def test_tres_pontos_arbitrarios_em_todas_as_ordens_produzem_mesma_caixa(self):
        self.modulo.rotation_euler = (.08, -.15, .61)
        self.modulo.location = (1.2, -2, .3)
        bpy.context.view_layer.update()
        pontos = self.pontos_livres()
        caixas = [A.caixa_de_pontos(self.modulo, ordem) for ordem in permutations(pontos)]
        esperado = caixas[0]
        for caixa in caixas:
            for a, b in zip(caixa['medidas'], (500, 350, 700)):
                self.assertAlmostEqual(a, b, places=3)
            for a, b in zip(A.cantos_dados(caixa), A.cantos_dados(esperado)):
                self.assertLess((a - b).length, 1e-6)
            m = A._matriz(caixa['matriz']).to_3x3()
            self.assertAlmostEqual(m.determinant(), 1, places=5)
            for i, j in ((0,1),(0,2),(1,2)):
                self.assertAlmostEqual(m.col[i].dot(m.col[j]), 0, places=5)

    def test_escala_e_espelho_do_modulo_nao_cisalham_caixa(self):
        self.modulo.rotation_euler.z = .4
        self.modulo.scale = (-2, .5, 1.2)
        bpy.context.view_layer.update()
        pontos = self.pontos_livres()
        caixa = A.caixa_de_pontos(self.modulo, pontos)
        m = A._matriz(caixa['matriz']); inv = m.inverted()
        medidas = Vector(caixa['medidas']) / 1000
        for p in pontos:
            local = inv @ p
            for i in range(3):
                self.assertGreaterEqual(local[i], -1e-6)
                self.assertLessEqual(local[i], medidas[i] + 1e-6)
        for i, j in ((0,1),(0,2),(1,2)):
            self.assertAlmostEqual(m.col[i].to_3d().dot(m.col[j].to_3d()), 0, places=5)

    def test_pontos_sem_volume_ou_nao_finitos_sao_recusados(self):
        for pontos in ([Vector((0,0,0))] * 3,
                       [Vector(p) for p in ((0,0,0), (1,0,1), (.2,0,.5))],
                       [Vector((float('nan'),0,0))]):
            with self.assertRaises(ValueError):
                A.caixa_de_pontos(self.modulo, pontos)

    def test_seis_frentes_preservam_volume_cantos_e_normal_escolhida(self):
        d = A.caixa_de_pontos(self.modulo, self.pontos_livres())
        cantos = A.cantos_dados(d)
        for face in A.FACES:
            novo = A.orientar_frente(d, face)
            for p in A.cantos_dados(novo):
                self.assertLess(min((p - outro).length for outro in cantos), 1e-6)
            self.assertAlmostEqual(math.prod(novo['medidas']), math.prod(d['medidas']), delta=200)
            m = A._matriz(d['matriz']).to_3x3()
            normal = m.col['XYZ'.index(face[0])] * (-1 if face[1] == '-' else 1)
            frente = -A._matriz(novo['matriz']).to_3x3().col[1]
            self.assertGreater(frente.dot(normal), .99999)

    def test_raio_escolhe_face_da_propria_caixa_sem_objetos_da_cena(self):
        d = A.caixa_de_pontos(self.modulo, self.pontos_livres())
        c = A.cantos_dados(d); m = A._matriz(d['matriz']).to_3x3()
        for face, indices in A.FACES.items():
            meio = sum((c[i] for i in indices), Vector()) / 4
            normal = m.col['XYZ'.index(face[0])] * (-1 if face[1] == '-' else 1)
            self.assertEqual(A.face_no_raio(d, meio + normal * 2, -normal), face)
        self.assertIsNone(A.face_no_raio(d, Vector((9,9,9)), Vector((0,0,1))))

    def test_assistente_exige_tres_pontos_e_frente_sem_inferir_diagonal(self):
        for ordem in permutations(self.pontos_livres()):
            op = self.assistente_tres_pontos()
            chapa = next(o for o in self.modulo.children_recursive if addon.chapas.MARCA_CHAPA in o)
            with patch.object(addon.gavetas, 'referencia_do_vao', side_effect=AssertionError('Inferiu diagonal')):
                for ponto, etapa in zip(ordem, ('CANTO2', 'CANTO3', 'FRENTE')):
                    op._aceitar_canto(bpy.context, ponto, chapa.name)
                    self.assertEqual(op._w['etapa'], etapa)
                self.assertNotIn('area_livre', op._w)
                op._receber_frente('X+')
                self.assertEqual(op._w['etapa'], 'QUANTIDADE')
                calculo, matriz = op._dados()
                self.assertIsNotNone(calculo)
                self.assertAlmostEqual(op._w['p']['profundidade_mm'], 500, places=3)
                self.assertAlmostEqual(matriz.to_3x3().determinant(), 1, places=4)

    def test_terceiro_ponto_invalido_pode_ser_corrigido_sem_perder_primeiros(self):
        op = self.assistente_tres_pontos()
        chapa = next(o for o in self.modulo.children_recursive if addon.chapas.MARCA_CHAPA in o)
        p = [self.modulo.matrix_world @ Vector(v) for v in ((-.2,0,.1),(.2,0,.8),(.1,0,.4))]
        for ponto in p:
            op._aceitar_canto(bpy.context, ponto, chapa.name)
        self.assertEqual(op._w['etapa'], 'CANTO3')
        self.assertEqual(op._w['pontos'], p[:2])
        op._aceitar_canto(bpy.context, p[2] + Vector((0,.3,0)), chapa.name)
        self.assertEqual(op._w['etapa'], 'FRENTE')

    def test_aplicar_volume_pede_frente_e_suspende_alcas_sem_criar(self):
        self.referencia()
        A._estado[0].pop('frente')
        with self.assertRaisesRegex(ValueError, 'frente'):
            A.preparar_entrega(bpy.context)
        with patch.object(addon.editor, 'executar') as executar:
            self.assertEqual(bpy.ops.object.cabinet_aplicar_area(), {'FINISHED'})
            self.assertTrue(A.escolhendo_frente())
            self.assertEqual(addon.hud._itens_hud(bpy.context), [])
            self.assertIsNone(addon.hud._alvo_hud(bpy.context))
            executar.assert_not_called()
        itens = A.widgets(bpy.context, [], 12, 600, 200)
        self.assertTrue(any('frente' in i[4] for i in itens))

    def test_clique_na_frente_entrega_e_encerra_modal_pai(self):
        self.referencia(); A.solicitar_frente(bpy.context)
        op = SimpleNamespace(report=lambda *_args: None)
        evento = SimpleNamespace(type='LEFTMOUSE', value='PRESS',
            mouse_x=self.regiao.x+50, mouse_y=self.regiao.y+50)
        with patch.object(A, 'face_no_raio', return_value='X+'), \
             patch.object(addon.editor, 'executar', return_value={'RUNNING_MODAL'}) as executar:
            self.assertEqual(A.OBJECT_OT_definir_area.modal(op,bpy.context,evento), {'FINISHED'})
            executar.assert_called_once()
            self.assertIsNone(A._estado[0])
            self.assertIsNone(A.objeto())

    def test_gavetas_prateleiras_divisorias_recebem_frente_escolhida_na_criacao_real(self):
        donos = ((addon.gavetas, addon.gavetas.OBJECT_OT_criar_gavetas),
                 (addon.prateleiras, addon.prateleiras.OBJECT_OT_criar_prateleiras),
                 (addon.divisorias, addon.divisorias.OBJECT_OT_criar_divisorias))
        pontos = self.pontos_livres()
        for indice, (dono, classe) in enumerate(donos):
            conj = addon.modulos.criar_armario(bpy.context, 'Frente teste %d' % indice, 1400, 1400, 1000)
            conj.location.x = 3 * (indice + 1)
            conj.rotation_euler.z = .35
            bpy.context.view_layer.update()
            locais = [conj.matrix_world @ (self.modulo.matrix_world.inverted() @ p) for p in pontos]
            caixa = A.caixa_de_pontos(conj, locais)
            for face in ('Y-', 'X+'):
                d = A.orientar_frente(caixa, face)
                op = self.assistente(classe, d)
                calculo, matriz = addon.gavetas.AssistenteDoVao._dados(op)
                self.assertIsNotNone(calculo)
                margens = addon.gavetas.margens_do_vao(conj, *op._w['pontos'],
                    referencial=op._w['referencia'], limites_referencia=op._w['limites_ref'])
                grupo = classe._criar_grupo(op, bpy.context, conj, margens, op._w['p'])
                for real, esperado in zip(dono.medidas(grupo), (d['medidas'][0], d['medidas'][2], d['medidas'][1])):
                    self.assertAlmostEqual(real, esperado, places=2)
                self.assertGreater(grupo.matrix_world.to_3x3().col[1].normalized().dot(matriz.to_3x3().col[1]), .9999)
                for peca in list(grupo.children_recursive) + [grupo]:
                    bpy.data.objects.remove(peca, do_unlink=True)

    def test_backspace_reabre_frente_e_refaz_terceiro_ponto(self):
        op = self.assistente_tres_pontos()
        chapa = next(o for o in self.modulo.children_recursive if addon.chapas.MARCA_CHAPA in o)
        for ponto in self.pontos_livres():
            op._aceitar_canto(bpy.context, ponto, chapa.name)
        op._w['iniciar_snap'] = False
        op._receber_frente('Y-')
        evento = SimpleNamespace(type='BACK_SPACE', value='PRESS')
        self.assertEqual(op._modal(bpy.context, evento), {'RUNNING_MODAL'})
        self.assertEqual(op._w['etapa'], 'FRENTE')
        op._modal(bpy.context, evento)
        self.assertEqual(op._w['etapa'], 'CANTO3')
        self.assertEqual(len(op._w['pontos']), 2)
        self.assertFalse(op._w['iniciar_snap'])

    def test_cancelar_escolha_da_frente_remove_apenas_referencia_temporaria(self):
        self.referencia(); A.solicitar_frente(bpy.context)
        nomes = {o.name for o in self.modulo.children_recursive}
        evento = SimpleNamespace(type='ESC', value='PRESS',
            mouse_x=self.regiao.x+50, mouse_y=self.regiao.y+50)
        self.assertEqual(A.OBJECT_OT_definir_area.modal(SimpleNamespace(),bpy.context,evento), {'CANCELLED'})
        self.assertFalse(A.escolhendo_frente())
        self.assertIsNone(A.objeto())
        self.assertEqual({o.name for o in self.modulo.children_recursive}, nomes)

    def test_volume_livre_repassa_navegacao_antes_e_durante_escolha_da_frente(self):
        obj=self.referencia();antes=A.copia(obj)
        evento=SimpleNamespace(type='ACCENT_GRAVE',value='PRESS',shift=True,
            mouse_x=self.regiao.x+80,mouse_y=self.regiao.y+80)
        for frente in (False,True):
            if frente:A.solicitar_frente(bpy.context)
            for tecla in ('ACCENT_GRAVE','MIDDLEMOUSE','TRACKPADPAN','TIMER'):
                evento.type=tecla
                self.assertEqual(A.OBJECT_OT_definir_area.modal(SimpleNamespace(),bpy.context,evento),{'PASS_THROUGH'})
            self.assertEqual(A.copia(obj),antes)

    def test_caixa_tem_oito_pontas_e_permanece_retangular_apos_grs(self):
        obj = self.referencia()
        self.assertEqual(obj.type, 'EMPTY')
        self.assertEqual(len(A.cantos(obj)), 8)
        obj.rotation_euler.z = math.radians(31)
        obj.scale = (1.5, .8, 2)
        obj.location += Vector((1, 2, 3))
        bpy.context.view_layer.update()
        d = A.dados(obj)
        for real, esperado in zip(d['medidas'], (600, 320, 1200)):
            self.assertAlmostEqual(real, esperado, places=3)
        c = A.cantos(obj)
        for i, j in ((1, 2), (1, 4), (2, 4)):
            self.assertAlmostEqual((c[i] - c[0]).normalized().dot((c[j] - c[0]).normalized()), 0, places=5)
        self.assertEqual(len(c), 8)

    def test_porta_e_fundo_tem_so_quatro_pontas_coplanares(self):
        for destino in ('PORTAS', 'FUNDOS'):
            obj = self.referencia(destino)
            self.assertEqual(len(A.cantos(obj)), 4)
            self.assertEqual(A.valor(obj, ('P',)), 0)
            self.assertTrue(A.aplicar(bpy.context, obj, ('P',), 500))
            self.assertEqual(len(A.cantos(obj)), 4)
            A.encerrar()

    def test_faces_opostas_mantem_o_lado_ancorado(self):
        obj = self.referencia()
        antes = A.cantos(obj)
        A.aplicar(bpy.context, obj, ('L',), 600, 'max')
        depois = A.cantos(obj)
        self.assertLess((antes[1] - depois[1]).length, 1e-6)
        self.assertAlmostEqual((antes[0] - depois[0]).length, .2, places=5)
        A.aplicar(bpy.context, obj, ('A',), 800, 'min')
        self.assertLess((A.cantos(obj)[0] - depois[0]).length, 1e-6)

    def test_rejeita_medida_invalida_e_cisalhamento(self):
        obj = self.referencia()
        antes = A.copia(obj)
        for mm in (0, -1, float('nan'), float('inf')):
            self.assertTrue(A.aplicar(bpy.context, obj, ('L',), mm))
            self.assertEqual(A.copia(obj), antes)
        m = obj.matrix_world.copy(); m[0][1] = .3
        class Referencia(dict):
            pass
        referencia = Referencia(area_medidas_mm=(200, 200, 200), area_plana=False)
        referencia.matrix_world = m
        with self.assertRaises(ValueError):
            A.dados(referencia)

    def test_hud_reutiliza_seis_faces_da_caixa_e_quatro_bordas_do_plano(self):
        for destino, esperado in (('GAVETAS', 6), ('PORTAS', 4)):
            obj = self.referencia(destino)
            geometria = addon.hud._geometria_hud(bpy.context)
            self.assertEqual(geometria['modo'], 'AREA_CRIACAO')
            self.assertIs(addon.hud._sistema_hud('area_criacao'), A)
            with patch.object(addon.opcoes, '_opcao', return_value=True):
                controles = addon.hud_volume.controles(geometria)
            self.assertEqual(len(controles), esperado)
            self.assertTrue(all(addon.hud_volume.elegivel(l) for l in controles))
            self.assertTrue(all(l['objeto'] == obj for l in controles))
            A.encerrar()

    def test_snap_b_muda_face_da_area_sem_acumular_deslocamento_anterior(self):
        obj = self.referencia()
        alvo = A.linhas_hud(obj, [])[1][0]
        alvo = dict(alvo, lado='min')
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            backup = addon.hud._estado_arraste_hud(bpy.context, alvo)
            params = addon.hud_volume.preparar(bpy.context, alvo, backup)
            self.assertFalse(params['snap'])
            inicio = Vector(bpy.context.scene.cursor.location)
            bpy.context.scene.cursor.location = inicio + Vector((.1, 0, 0))
            addon.hud_volume.atualizar(bpy.context)
            self.assertAlmostEqual(A.valor(obj, ('L',)), 500, places=3)
            addon.hud_volume.preparar_base_snap(bpy.context)
            # Ao escolher a base, o translate nativo zera seu delta original.
            bpy.context.scene.cursor.location = inicio + Vector((.05, 0, 0))
            addon.hud_volume.atualizar(bpy.context)
            self.assertAlmostEqual(A.valor(obj, ('L',)), 550, places=3)

    def test_snap_b_da_area_criada_em_modulo_bloqueia_externos_e_restaura_esc(self):
        bpy.ops.mesh.primitive_cube_add(location=(0,-1,.5))
        teto = bpy.context.object
        outro = addon.modulos.criar_armario(bpy.context,'Vizinho',1000,1400,600)
        obj = self.referencia()
        antes = {o.name: (o.hide_select, o.hide_get()) for o in bpy.context.scene.objects}
        alvo = dict(A.linhas_hud(obj,[])[1][0], lado='min')
        with bpy.context.temp_override(area=self.area,region=self.regiao):
            backup = addon.hud._estado_arraste_hud(bpy.context,alvo)
            addon.hud_volume.preparar(bpy.context,alvo,backup)
            self.assertTrue(teto.hide_select)
            self.assertTrue(all(o.hide_select for o in outro.children_recursive))
            self.assertFalse(any(o.hide_select for o in self.modulo.children_recursive))
            addon.hud_volume.terminar(bpy.context,cancelar=True)
        self.assertEqual({o.name:(o.hide_select,o.hide_get()) for o in bpy.context.scene.objects},antes)

    def assistente(self, classe, d):
        op = SimpleNamespace(_w={'p': classe._parametros_padrao(SimpleNamespace()), 'pontos': []})
        op._comecar_no_modulo = lambda c, p: classe._comecar_no_modulo(op, c, p)
        op._calcular = lambda l, a, p: classe._calcular(op, l, a, p)
        op._ir = lambda etapa: op._w.update(etapa=etapa)
        A.receber_internos(op, d)
        return op

    def assistente_internos(self, destino):
        obj=self.referencia(destino)
        d=A.preparar_entrega(bpy.context)
        A.encerrar()
        classe=(addon.prateleiras.OBJECT_OT_criar_prateleiras if destino=='PRATELEIRAS'
                else addon.divisorias.OBJECT_OT_criar_divisorias)
        op=self.assistente(classe,d)
        op.ABA=destino
        op._dados=lambda: addon.gavetas.AssistenteDoVao._dados(op)
        op._encerrar=lambda contexto: None
        return op

    def test_pergunta_inicial_escolhe_tipo_antes_da_blocagem(self):
        self.assertEqual(bpy.ops.object.cabinet_internos(acao='INICIAR'),{'FINISHED'})
        self.assertEqual(A._internos[0]['etapa'],'TIPO')
        pergunta=addon.perguntas._pergunta_atual[0]
        self.assertEqual([o[0] for o in pergunta['opcoes']],['Prateleiras','Divisorias','Sair'])
        with patch.object(addon.editor,'executar',return_value={'RUNNING_MODAL'}) as executar:
            self.assertEqual(bpy.ops.object.cabinet_internos(acao='TIPO',valor='DIVISORIAS'),{'FINISHED'})
        self.assertEqual(executar.call_args.args[1],'object.cabinet_criar_divisorias')
        self.assertEqual(A._internos[0]['tipo'],'DIVISORIAS')
        self.assertIn(A.OBJECT_OT_internos,addon.CLASSES)

    def test_volume_pergunta_tipo_e_so_depois_abre_referencia(self):
        A.iniciar_internos(bpy.context,'VOLUME')
        with patch.object(addon.editor,'executar',return_value={'RUNNING_MODAL'}) as executar:
            bpy.ops.object.cabinet_internos(acao='TIPO',valor='PRATELEIRAS')
        self.assertEqual(executar.call_args.args[1],'object.cabinet_definir_area')
        self.assertEqual(executar.call_args.kwargs,{'destino':'PRATELEIRAS','portas_verificadas':True})

    def test_divisorias_depois_prateleiras_reutilizam_volume_sem_novos_cliques(self):
        op=self.assistente_internos('DIVISORIAS')
        A.criar_internos(bpy.context,op,{})
        area=dict(A._internos[0]['area'])
        self.assertEqual(A._internos[0]['etapa'],'CONTINUAR')
        recebidos=[]
        def continuar(context,idname,*args,**kwargs):
            d=A.consumir('PRATELEIRAS');recebidos.append(d)
            novo=self.assistente(addon.prateleiras.OBJECT_OT_criar_prateleiras,d)
            novo.ABA='PRATELEIRAS';novo._encerrar=lambda contexto:None
            novo._dados=lambda: addon.gavetas.AssistenteDoVao._dados(novo)
            return A.criar_internos(context,novo,{})
        with patch.object(addon.editor,'executar',side_effect=continuar):
            bpy.ops.object.cabinet_internos(acao='CONTINUAR',valor='PRATELEIRAS')
        self.assertEqual(recebidos[0]['matriz'],area['matriz'])
        self.assertEqual(recebidos[0]['medidas'],area['medidas'])
        self.assertEqual(A._internos[0]['area'],area)
        divisorias=next(o for o in self.modulo.children if addon.divisorias.MARCA_GRUPO in o)
        self.assertTrue(all(g[addon.divisorias.CHAVE_BLOCAGEM]==divisorias[addon.divisorias.CHAVE_BLOCAGEM]
            for g in addon.prateleiras.grupos_do_modulo(self.modulo)))
        self.assertEqual(len(addon.divisorias.pecas(divisorias)),1)
        self.assertEqual(sum(len(addon.prateleiras.prateleiras_do_grupo(g)) for g in addon.prateleiras.grupos_do_modulo(self.modulo)),2)
        nomes=set(bpy.data.objects.keys())
        self.assertEqual([o[0] for o in addon.perguntas._pergunta_atual[0]['opcoes']],['Sair'])
        self.assertEqual(bpy.ops.object.cabinet_internos(acao='CONTINUAR',valor='DIVISORIAS'),{'CANCELLED'})
        bpy.ops.object.cabinet_internos(acao='SAIR')
        self.assertIsNone(A._internos[0]);self.assertEqual(set(bpy.data.objects.keys()),nomes)

    def test_lacuna_pergunta_antes_de_mutar_e_cancelar_conserva_prateleiras(self):
        op=self.assistente_internos('PRATELEIRAS');A.criar_internos(bpy.context,op,{})
        A.cancelar_internos()
        op=self.assistente_internos('DIVISORIAS');op._w['p']['profundidade_mm']=200
        nomes=set(bpy.data.objects.keys())
        A.criar_internos(bpy.context,op,{})
        self.assertEqual(A._internos[0]['etapa'],'LACUNA')
        self.assertEqual(set(bpy.data.objects.keys()),nomes)
        self.assertEqual(len(addon.perguntas._pergunta_atual[0]['opcoes']),4)
        addon.perguntas._pergunta_atual[0]['na_gaveta']=True
        for largura in (190,320,564):
            widgets=addon.gaveta._widgets_gaveta(bpy.context,largura,900)
            respostas=[v for v in widgets if v[5] and v[5][0]=='resposta']
            self.assertEqual([v[5][1] for v in respostas],[0,1,2,3])
            self.assertTrue(all(v[0]+v[2]<=min(largura-12,552) for v in respostas))
            import blf
            blf.size(0,9)
            self.assertTrue(all(blf.dimensions(0,v[4])[0]<=v[2]-14 for v in respostas))
        bpy.ops.object.cabinet_internos(acao='SAIR')
        self.assertEqual(set(bpy.data.objects.keys()),nomes)

    def test_prateleiras_criadas_depois_tambem_perguntam_sobre_lacuna(self):
        op=self.assistente_internos('DIVISORIAS');op._w['p']['profundidade_mm']=200
        A.criar_internos(bpy.context,op,{})
        A.cancelar_internos()
        op=self.assistente_internos('PRATELEIRAS')
        A.criar_internos(bpy.context,op,{})
        self.assertEqual(A._internos[0]['etapa'],'LACUNA')
        self.assertEqual(bpy.ops.object.cabinet_internos(acao='LACUNA',valor='ESQUERDA'),{'FINISHED'})
        grupos=addon.prateleiras.grupos_do_modulo(self.modulo)
        self.assertEqual(len(grupos),2)
        self.assertTrue(any(m.type=='BOOLEAN' for g in grupos for o in g.children for m in o.modifiers))

    def test_comando_fora_da_etapa_e_troca_de_cena_nao_criam_dados(self):
        A.iniciar_internos(bpy.context)
        nomes=set(bpy.data.objects.keys())
        self.assertEqual(bpy.ops.object.cabinet_internos(acao='CONTINUAR',valor='PRATELEIRAS'),{'CANCELLED'})
        self.assertEqual(set(bpy.data.objects.keys()),nomes)
        A.preparar_assistente_internos('DIVISORIAS')
        self.assertIsNone(A._internos[0])
        self.assertIsNone(addon.perguntas._pergunta_atual[0])
        A.iniciar_internos(bpy.context)
        A._internos[0].update(etapa='CRIANDO',tipo='PRATELEIRAS')
        atual=A._internos[0]
        A.preparar_assistente_internos('PRATELEIRAS')
        self.assertIs(A._internos[0],atual)
        A._internos[0]['cena']='Outra cena'
        A.verificar();self.assertIsNone(A._internos[0])

    def test_as_duas_selecoes_usam_a_mesma_aba_e_controles_do_tipo(self):
        g=addon.gaveta
        self.assertEqual(sum(aba[2]=='PRATELEIRAS' for aba in g.ABAS_GAVETA),1)
        self.assertFalse(any(aba[2]=='DIVISORIAS' for aba in g.ABAS_GAVETA))
        for tipo in ('PRATELEIRAS','DIVISORIAS'):
            bpy.context.scene.cabinet_aba=tipo
            self.assertEqual(g._aba_no_menu(bpy.context.scene),'PRATELEIRAS')
            cab=g._cabecalho_gaveta(bpy.context,12,860,166)
            self.assertEqual(cab[0][4],'Prateleiras / Divisorias')

    def test_area_cria_gavetas_sem_pontos_de_malha_nem_recalcular_profundidade(self):
        obj = self.referencia()
        d = A.preparar_entrega(bpy.context)
        classe = addon.gavetas.OBJECT_OT_criar_gavetas
        op = self.assistente(classe, d)
        calculo, matriz = addon.gavetas.AssistenteDoVao._dados(op)
        self.assertIsNotNone(calculo)
        self.assertEqual(op._w['etapa'], 'QUANTIDADE')
        self.assertEqual(op._w['p']['profundidade_mm'], 400)
        margens = addon.gavetas.margens_do_vao(self.modulo, *op._w['pontos'],
            referencial=op._w['referencia'], limites_referencia=op._w['limites_ref'])
        grupo = classe._criar_grupo(op, bpy.context, self.modulo, margens, op._w['p'])
        self.assertIs(grupo.parent, self.modulo)
        self.assertEqual(len(addon.gavetas.gavetas_do_grupo(grupo)), 1)
        op._depois_da_profundidade = lambda contexto: {'FIM_TESTE'}
        self.assertEqual(addon.gavetas.AssistenteDoVao._depois_da_quantidade(op, bpy.context), {'FIM_TESTE'})

    def test_mesma_area_cria_prateleiras_e_divisorias(self):
        for destino, dono, classe in (
            ('PRATELEIRAS', addon.prateleiras, addon.prateleiras.OBJECT_OT_criar_prateleiras),
            ('DIVISORIAS', addon.divisorias, addon.divisorias.OBJECT_OT_criar_divisorias)):
            obj = self.referencia(destino)
            d = A.preparar_entrega(bpy.context)
            op = self.assistente(classe, d)
            margens = addon.gavetas.margens_do_vao(self.modulo, *op._w['pontos'],
                referencial=op._w['referencia'], limites_referencia=op._w['limites_ref'])
            grupo = classe._criar_grupo(op, bpy.context, self.modulo, margens, op._w['p'])
            self.assertIs(grupo.parent, self.modulo)
            self.assertTrue(grupo.children_recursive)
            A.encerrar()

    def test_area_invalida_nao_perde_referencia_ao_aplicar(self):
        obj = self.referencia()
        A.aplicar(bpy.context, obj, ('L',), 1)
        with self.assertRaises(ValueError):
            A.preparar_entrega(bpy.context)
        self.assertIs(A.objeto(), obj)

    def test_porta_criada_no_plano_manual_conserva_vao_e_matriz(self):
        obj = self.referencia('PORTAS')
        d = A.preparar_entrega(bpy.context)
        l, a, m = A.vao_porta(d)
        c = A.cantos(obj)
        parametros = addon.portas._parametros_portas_da_cena(bpy.context.scene)
        resultado = bpy.ops.object.cabinet_portas('EXEC_DEFAULT', capturado=True,
            area_definida=True, matriz_area=tuple(v for linha in m for v in linha),
            medidas_area=(l, a), ponto_a=c[2], ponto_b=c[1],
            modulo_nome=self.modulo.name, quatro_pontos=True, **parametros)
        self.assertEqual(resultado, {'FINISHED'})
        grupo = next(o for o in self.modulo.children if addon.chapas.MARCA_PORTAS in o)
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], l, places=3)
        self.assertAlmostEqual(grupo['porta_vao_altura_mm'], a, places=3)
        self.assertLess(max(abs(x - y) for linha, outra in zip(grupo.matrix_world, m) for x, y in zip(linha, outra)), 1e-5)
        self.assertEqual(len(A.cantos(obj)), 4)

    def test_previa_da_porta_usa_plano_manual_sem_solver_de_vertices(self):
        obj = self.referencia('PORTAS'); d = A.preparar_entrega(bpy.context)
        c = A.cantos(obj)
        op = SimpleNamespace(_pontos=[(c[2], self.modulo), (c[1], self.modulo)],
            _w={'etapa': 'FOLHAS', 'area_livre': d, 'escolhas': {}}, _grupo_alvo='',
            _imantado=None, _objeto_imantado=None)
        with patch.object(addon.portas, '_preparar_vao_portas', side_effect=AssertionError('Procurou vertices')):
            caixas = addon.assistente.OBJECT_OT_apanhar_vao_portas._previa(op)
        self.assertTrue(caixas)
        self.assertAlmostEqual(op._w['largura'], 400, places=3)
        self.assertAlmostEqual(op._w['altura'], 600, places=3)
        op._ir = lambda etapa: op._w.update(etapa=etapa)
        addon.assistente.OBJECT_OT_apanhar_vao_portas._voltar(op)
        self.assertEqual(op._w['etapa'], 'FOLHAS')
        self.assertEqual(len(op._pontos), 2)

    def test_fundo_recebe_plano_sem_etapa_de_profundidade(self):
        obj = self.referencia('FUNDOS'); d = A.preparar_entrega(bpy.context)
        classe = addon.fundos.OBJECT_OT_criar_fundo
        op = SimpleNamespace(_w={'p': classe._parametros_padrao(SimpleNamespace()), 'pontos': []})
        op._comecar_no_modulo = lambda c, p: classe._comecar_no_modulo(op, c, p)
        op._ir = lambda etapa: op._w.update(etapa=etapa)
        A.receber_internos(op, d)
        grupo = classe._criar_grupo(op, bpy.context, self.modulo, [], op._w['p'])
        self.assertIn(addon.chapas.MARCA_FUNDO, grupo)
        self.assertEqual(len(A.cantos(obj)), 4)

    def test_primeiro_clique_em_face_sem_vertice_cria_area_e_tab_nao_modela(self):
        obj = self.modulo
        for o in bpy.context.selected_objects:
            o.select_set(False)
        obj.select_set(True); bpy.context.view_layer.objects.active = obj
        wm = SimpleNamespace(modal_handler_add=lambda op: None,
                             event_timer_add=lambda *args, **kwargs: None)
        class Contexto:
            window_manager = wm
            def __getattr__(self, nome):
                return getattr(bpy.context, nome)
        contexto = Contexto()
        op = SimpleNamespace(destino='GAVETAS', report=lambda *_args: None)
        with bpy.context.temp_override(area=self.area, region=self.regiao):
            self.assertEqual(A.OBJECT_OT_definir_area.invoke(op, contexto, None), {'RUNNING_MODAL'})
            ponto = Vector((-.2, -.25, .4))
            chapa = next(o for o in obj.children_recursive if o.type == 'MESH')
            evento = SimpleNamespace(type='LEFTMOUSE', value='PRESS',
                mouse_x=self.regiao.x + 60, mouse_y=self.regiao.y + 60)
            with patch.object(addon.gavetas, 'raio_no_modulo', return_value=(chapa, ponto, Vector((0,0,1)), 0, Matrix.Identity(4))), \
                 patch.object(addon.hud, '_raio_cru', side_effect=AssertionError('Consultou a cena inteira')):
                self.assertEqual(A.OBJECT_OT_definir_area.modal(op, contexto, evento), {'RUNNING_MODAL'})
            self.assertLess((A.objeto().matrix_world.translation-ponto).length,1e-6)
            self.assertEqual(len(A.cantos(A.objeto())), 8)
            evento.type = 'TAB'
            self.assertEqual(A.OBJECT_OT_definir_area.modal(op, contexto, evento), {'RUNNING_MODAL'})
            self.assertEqual(bpy.context.mode, 'OBJECT')

    def test_escala_zero_nao_quebra_callback_e_restaura_ultimo_volume_valido(self):
        obj = self.referencia()
        antes = A.cantos(obj)
        obj.scale.x = 0
        bpy.context.view_layer.update()
        self.assertEqual(A.cantos(obj), antes)
        self.assertAlmostEqual(A.valor(obj, ('L',)), 400, places=3)
        A.verificar()
        self.assertAlmostEqual(A.dados(obj)['medidas'][0], 400, places=3)
        self.assertTrue(A.aplicar(bpy.context, None, ('L',), 500))

    def test_enter_que_confirma_campo_ou_g_nao_aplica_area_no_release(self):
        self.referencia()
        op = SimpleNamespace(report=lambda *_args: None)
        evento = SimpleNamespace(type='RET', value='RELEASE',
            mouse_x=self.regiao.x + 50, mouse_y=self.regiao.y + 50)
        with patch.object(A, 'entregar', return_value={'FINISHED'}) as entregar:
            self.assertEqual(A.OBJECT_OT_definir_area.modal(op,bpy.context,evento), {'PASS_THROUGH'})
            entregar.assert_not_called()
            evento.value = 'PRESS'
            self.assertEqual(A.OBJECT_OT_definir_area.modal(op,bpy.context,evento), {'RUNNING_MODAL'})
            evento.value = 'RELEASE'
            self.assertEqual(A.OBJECT_OT_definir_area.modal(op,bpy.context,evento), {'RUNNING_MODAL'})
            self.assertEqual(A._estado[0]['etapa'], 'FRENTE')
            entregar.assert_not_called()

    def test_plano_externo_invalido_nao_cria_porta(self):
        obj = self.referencia('PORTAS')
        l, a, m = A.vao_porta(A.preparar_entrega(bpy.context))
        antes = set(bpy.data.objects.keys())
        m[0][1] += .3
        parametros = addon.portas._parametros_portas_da_cena(bpy.context.scene)
        resultado = bpy.ops.object.cabinet_portas('EXEC_DEFAULT', capturado=True, area_definida=True,
            matriz_area=tuple(v for linha in m for v in linha), medidas_area=(l,a), **parametros)
        self.assertEqual(resultado, {'CANCELLED'})
        self.assertEqual(set(bpy.data.objects.keys()), antes)

    def test_undo_redo_da_criacao_nao_deixa_area_provisoria(self):
        obj = self.referencia('PRATELEIRAS')
        d = A.preparar_entrega(bpy.context)
        op = self.assistente(addon.prateleiras.OBJECT_OT_criar_prateleiras, d)
        nome_modulo = self.modulo.name
        bpy.ops.ed.undo_push(message='Area definida antes de aplicar')
        A.encerrar(restaurar_selecao=False)
        margens = addon.gavetas.margens_do_vao(self.modulo, *op._w['pontos'],
            referencial=op._w['referencia'], limites_referencia=op._w['limites_ref'])
        grupo = addon.prateleiras.OBJECT_OT_criar_prateleiras._criar_grupo(op,bpy.context,self.modulo,margens,op._w['p'])
        nome_grupo = grupo.name
        bpy.ops.ed.undo_push(message='Prateleira criada pela area')
        self.modulo = obj = grupo = op = None
        bpy.ops.ed.undo(); addon.eventos._fim_do_desfazer(); A.verificar()
        self.assertNotIn(nome_grupo, bpy.data.objects)
        self.assertFalse(any(A.MARCA in o for o in bpy.data.objects))
        bpy.ops.ed.redo(); addon.eventos._fim_do_desfazer(); A.verificar()
        self.assertIn(nome_grupo, bpy.data.objects)
        self.assertIs(bpy.data.objects[nome_grupo].parent, bpy.data.objects[nome_modulo])
        self.assertFalse(any(A.MARCA in o for o in bpy.data.objects))

    def test_salvar_reabrir_nao_grava_referencia_provisoria(self):
        obj = self.referencia()
        nome = self.modulo.name
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, 'sem_area_temporaria.blend')
            bpy.ops.wm.save_as_mainfile(filepath=caminho)
            self.assertIsNone(A._estado[0])
            self.assertFalse(any(A.MARCA in o for o in bpy.data.objects))
            self.modulo = obj = None
            bpy.ops.wm.open_mainfile(filepath=caminho, load_ui=False)
        self.assertIn(nome, bpy.data.objects)
        self.assertFalse(any(A.MARCA in o for o in bpy.data.objects))

    def test_ponte_para_assistente_consumida_uma_vez_sem_rna_global(self):
        obj = self.referencia()
        def executar(contexto, idname, **props):
            self.assertEqual(idname, 'object.cabinet_criar_gavetas')
            self.assertEqual(props,dict(portas_verificadas=True))
            self.assertIsNone(A.objeto())
            dados = A.consumir('GAVETAS')
            self.assertTrue(dados)
            self.assertIsNone(A.consumir('GAVETAS'))
            self.assertTrue(all(not isinstance(v, bpy.types.Object) for v in dados.values()))
            return {'RUNNING_MODAL'}
        with patch.object(addon.editor, 'executar', side_effect=executar):
            self.assertEqual(A.entregar(bpy.context), {'FINISHED'})
        self.assertIsNone(A._entrega[0])

    def test_cancelar_e_undo_removem_so_referencia_temporaria(self):
        obj = self.referencia()
        nome = self.modulo.name
        nome_area = obj.name
        antes = {o.name: o.data.as_pointer() for o in self.modulo.children_recursive if o.type == 'MESH'}
        self.assertEqual(bpy.ops.object.cabinet_cancelar_area(), {'FINISHED'})
        self.assertNotIn(nome_area, bpy.data.objects)
        self.assertEqual(bpy.context.object.name, nome)
        self.assertEqual({n: bpy.data.objects[n].data.as_pointer() for n in antes}, antes)
        obj = self.referencia()
        bpy.ops.ed.undo_push(message='Referencia provisoria')
        A.encerrar()
        bpy.ops.ed.undo_push(message='Referencia cancelada')
        self.modulo = obj = None
        bpy.ops.ed.undo(); addon.eventos._fim_do_desfazer()
        A.verificar()
        self.assertFalse(any(A.MARCA in o for o in bpy.data.objects))

    def test_menu_oferece_volume_e_plano_e_campos_usam_mesmas_cotas(self):
        for aba, rotulo in (('GAVETAS', 'Definir por volume'), ('PRATELEIRAS', 'Definir por volume'), ('PORTAS', 'Definir por plano')):
            bpy.context.scene.cabinet_aba = aba
            itens = addon.gaveta._widgets_aba_gaveta(bpy.context, 320, 1000, 0)
            self.assertTrue(any(i[4] == rotulo for i in itens))
        obj = self.referencia()
        itens = addon.gaveta._widgets_aba_gaveta(bpy.context, 320, 1000, 0)
        campos = [i for i in itens if i[5] and i[5][0] == 'medida']
        self.assertEqual({i[5][2] for i in campos}, {'L', 'A', 'P'})
        self.assertTrue(any(i[4] == 'Aplicar area' for i in itens))
        self.assertEqual(bpy.ops.object.cabinet_editar_medida_gaveta('EXEC_DEFAULT',
            dono='area_criacao', propriedade='L', valor=.55), {'FINISHED'})
        self.assertAlmostEqual(A.valor(obj, ('L',)), 550, places=3)
        self.assertIn(A.OBJECT_OT_aplicar_area, addon.CLASSES)
        self.assertIn(A.OBJECT_OT_definir_area, addon.CLASSES)
        self.assertIn(A.OBJECT_OT_cancelar_area, addon.CLASSES)


with tempfile.TemporaryDirectory(prefix='areas_criacao_') as pasta, \
     patch.object(addon.opcoes, '_pasta_addon', return_value=pasta), \
     patch.object(addon.biblioteca, 'pasta_biblioteca', return_value=pasta):
    addon.register()
    try:
        resultado = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestAreasCriacao))
    finally:
        addon.unregister()
    if not resultado.wasSuccessful():
        raise RuntimeError('Falha nas areas de criacao')
