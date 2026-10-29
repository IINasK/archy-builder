"""Execute no Blender: --background --factory-startup --python-exit-code 1 --python tests/test_hud_blender.py."""
import inspect
import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import bmesh
import math

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon


class _ContextoRegiao:
    """bpy.context com uma regiao fixa (o clique guarda estado por ela)."""
    region = SimpleNamespace(as_pointer=lambda: 4242)

    def __getattr__(self, nome):
        return getattr(bpy.context, nome)


class TestHUD(unittest.TestCase):
    def editor_do_vao(self, espessura=18):
        addon.eventos._fim_do_desfazer()
        h=addon.hud;p=addon.prateleiras
        modulo=addon.modulos.criar_armario(bpy.context,'Vao editavel',800,700,560)
        grupo=p.criar_prateleiras(bpy.context,modulo,(18,18,18,18,0),dict(quantidade=2,espessura_mm=espessura))
        p.selecionar(bpy.context,grupo,'GRUPO')
        alvo=next(l for l in p.linhas_hud(grupo,[])[1] if l.get('face')==('V',1))
        backup=h._estado_arraste_hud(bpy.context,alvo)
        op=SimpleNamespace(_alvo=alvo,_area=SimpleNamespace(tag_redraw=lambda:None),
            _backup=backup,_backups=[backup],_arrastou=False,report=lambda *a:None)
        classe=h.OBJECT_OT_arrastar_hud
        op._rolar_prateleiras=lambda c,e:classe._rolar_prateleiras(op,c,e)
        op._digitar=lambda c,e:classe._digitar(op,c,e)
        op._encerrar=lambda:classe._encerrar(op)
        op.cancel=lambda c:classe.cancel(op,c)
        h._edicao_hud[0]=dict(regiao=4242,alvo=alvo,texto='200',cursor=3,selecionado=True)
        self.addCleanup(h._edicao_hud.__setitem__,0,None)
        return grupo,op

    def test_scroll_da_cota_altera_quantidade_local_e_enter_confirma_sem_mudar_distancia(self):
        p=addon.prateleiras;h=addon.hud;grupo,op=self.editor_do_vao()
        evento=SimpleNamespace(type='WHEELUPMOUSE',value='PRESS')
        for n in (1,2):
            self.assertEqual(h.OBJECT_OT_arrastar_hud.modal(op,bpy.context,evento),{'RUNNING_MODAL'})
            self.assertEqual(len(p.prateleiras_do_grupo(grupo)),2+n)
            self.assertEqual(h._edicao_hud[0]['texto'],str(n))
        evento.type='RET'
        with patch.object(h,'_aplicar_valor_hud',side_effect=AssertionError('Tratou quantidade como distancia')):
            self.assertEqual(h.OBJECT_OT_arrastar_hud.modal(op,bpy.context,evento),{'FINISHED'})
        self.assertIsNone(h._edicao_hud[0])
        self.assertEqual(p.parametros(grupo)['quantidade'],4)

    def test_esc_da_cota_remove_previa_e_restaura_mesmas_prateleiras(self):
        p=addon.prateleiras;h=addon.hud;grupo,op=self.editor_do_vao()
        antes=p.copia(grupo)
        originais={o.name:(o.matrix_world.copy(),o.data.as_pointer()) for o in p.prateleiras_do_grupo(grupo)}
        evento=SimpleNamespace(type='WHEELUPMOUSE',value='PRESS')
        h.OBJECT_OT_arrastar_hud.modal(op,bpy.context,evento)
        evento.type='ESC'
        self.assertEqual(h.OBJECT_OT_arrastar_hud.modal(op,bpy.context,evento),{'CANCELLED'})
        self.assertEqual(p.copia(grupo),antes)
        self.assertEqual({o.name:(o.matrix_world,o.data.as_pointer()) for o in p.prateleiras_do_grupo(grupo)},originais)

    def test_scroll_sem_espaco_nao_muda_digitacao_de_distancia_para_quantidade(self):
        h=addon.hud;p=addon.prateleiras;grupo,op=self.editor_do_vao(180)
        antes=p.copia(grupo)
        evento=SimpleNamespace(type='WHEELUPMOUSE',value='PRESS')
        h.OBJECT_OT_arrastar_hud.modal(op,bpy.context,evento)
        self.assertFalse(getattr(op,'_subdivisao_vao',None))
        self.assertEqual(h._edicao_hud[0]['texto'],'200')
        self.assertEqual(p.copia(grupo),antes)

    def test_edicao_solda_bloqueia_hud_geometria_e_restaura_ao_terminar(self):
        s=addon.solda;o,n,w=self._nova_solda_manual()
        contexto=_ContextoRegiao();contexto.region=SimpleNamespace(type='WINDOW',as_pointer=lambda:4242)
        contexto.area=SimpleNamespace(type='VIEW_3D');contexto.region_data=object();w['regiao']=4242
        with patch.object(addon.eventos,'_transformando',return_value=False), \
             patch.object(addon.gaveta,'_eh_area_gaveta',return_value=False), \
             patch.object(addon.hud,'_projetar_hud',return_value=Vector((100,100))):
            s._conexao_manual[0]=None
            self.assertTrue(addon.hud._contexto_hud(contexto))
            s._conexao_manual[0]=w
            addon.hud._hover_hud[4242]={'tipo':'medida'}
            self.assertFalse(addon.hud._contexto_hud(contexto))
            self.assertFalse(addon.hud._hover_hud)
            self.assertFalse(addon.hud.OBJECT_OT_arrastar_hud.poll(contexto))
            self.assertFalse(addon.hud.VIEW3D_GGT_hud_cabinet.poll(contexto))
            self.assertFalse(addon.portas_viewport.VIEW3D_GGT_slider_porta.poll(contexto))
            self.assertFalse(addon.portas_viewport.OBJECT_OT_abrir_porta.poll(contexto))
            self.assertTrue(addon.hud.VIEW3D_GGT_correntes_cabinet.poll(contexto))
            self.assertTrue(s.OBJECT_OT_clique_corrente.poll(contexto))
            self.assertEqual(len(s._correntes_hud(contexto)),1)
            with patch.object(s,'_campo_distancia_corrente',return_value=None), \
                 patch.object(s,'_bolinha_sob_mouse',return_value=(None,None)), \
                 patch.object(s,'_botao_corrente_sob_mouse',return_value=(None,None)), \
                 patch.object(addon.portas_viewport,'_canto_porta_sob_mouse',side_effect=AssertionError('Controle de geometria durante solda')):
                self.assertIsNone(s._alvo_da_corrente(contexto,(0,0)))
            s._conexao_manual[0]=None
            self.assertTrue(addon.hud._contexto_hud(contexto))
            with patch.object(s,'_arraste_ancora',[{'origem':o.name}]):
                self.assertFalse(addon.hud._contexto_hud(contexto))
            self.assertTrue(addon.hud._contexto_hud(contexto))

    def test_criacao_solda_controladores_sem_selecao_e_operadores_reutilizados(self):
        s=addon.solda;o,n,w=self._nova_solda_manual()
        contexto=_ContextoRegiao();contexto.region_data=object();w['regiao']=4242
        for obj in bpy.context.selected_objects:obj.select_set(False)
        with patch.object(addon.gaveta,'_eh_area_gaveta',return_value=False), \
             patch.object(addon.hud,'_projetar_hud',return_value=Vector((100,100))):
            correntes=s._correntes_hud(contexto)
            self.assertTrue(addon.hud.VIEW3D_GGT_correntes_cabinet.poll(contexto))
        self.assertEqual(len(correntes),1)
        feitos=[]
        def criar(tipo):
            op=SimpleNamespace();feitos.append((tipo,op))
            return SimpleNamespace(matrix_basis=Matrix.Identity(4),as_pointer=lambda:123457,
                target_set_operator=lambda nome:(setattr(op,'nome',nome) or op))
        grupo=SimpleNamespace(botoes=[],gizmos=SimpleNamespace(new=criar))
        with patch.object(s,'_correntes_hud',return_value=correntes):
            for _ in range(3):addon.hud.VIEW3D_GGT_correntes_cabinet.draw_prepare(grupo,contexto)
        self.assertEqual(len(feitos),3)
        self.assertEqual([op.acao for _,op in feitos[:2]],['REMOVER|0','RESETAR|0'])
        self.assertTrue(all(op.nome=='object.cabinet_acao_criacao_solda' for _,op in feitos[:2]))
        self.assertEqual((feitos[-1][1].dono,feitos[-1][1].propriedade),('solda_criacao','0'))
        addon.hud._campos_gaveta.pop(123457,None)
        op=SimpleNamespace(_na_viewport=lambda e:True,_area=SimpleNamespace(tag_redraw=lambda:None))
        evento=SimpleNamespace(type='MOUSEMOVE',value='NOTHING')
        self.assertEqual(s.OBJECT_OT_conectar_vertices._modal(op,bpy.context,evento),{'PASS_THROUGH'})

    def test_regua_criacao_por_indice_zera_no_destino_e_cancelar_restaura(self):
        s=addon.solda;o,n,w=self._nova_solda_manual();antes=o.matrix_world.copy();fixo=n.matrix_world.copy()
        self.assertEqual(bpy.ops.object.cabinet_acao_criacao_solda(acao='RESETAR|0'),{'FINISHED'})
        sc,_,sn=w['pares'][0]
        self.assertAlmostEqual((s._vertice_da_assinatura(o,sc)-s._vertice_da_assinatura(n,sn)).length,0,places=6)
        self.assertEqual(w['distancias'],[0]);self.assertEqual(w['zeradas'],[True])
        self.assertEqual(n.matrix_world,fixo)
        s.encerrar_conexao_nativa();self.assertEqual(o.matrix_world,antes)

    def test_corrente_criacao_remove_so_par_pendente_sem_desagregar(self):
        s=addon.solda;o,n,w=self._nova_solda_manual();pai=o.parent
        s.editar_criacao_solda(zerar=True)
        self.assertEqual(bpy.ops.object.cabinet_acao_criacao_solda(acao='REMOVER|0'),{'FINISHED'})
        self.assertEqual(w['pares'],[]);self.assertEqual(w['distancias'],[])
        self.assertEqual(w['fase'],'origem');self.assertEqual(o.parent,pai)
        self.assertFalse(any(k.startswith('adj_') for k in o.keys()))

    def test_feedback_criacao_usa_cursor_nativo_e_distancia_sem_consultar_malhas(self):
        s=addon.solda
        w=dict(snap_pendente=True,cursor=Vector((.3,.4,0)),escolhido=('---',Vector((0,0,0))))
        with patch.object(s,'_vertice_do_snap',side_effect=AssertionError('Segundo motor de snap')):
            ponto,inicio=s._feedback_snap_criacao(w)
        self.assertAlmostEqual((ponto-inicio).length,.5)
        w['snap_pendente']=False;self.assertIsNone(s._feedback_snap_criacao(w))

    def test_qualidade_ancoras_piloto_prioriza_zero_rejeita_vertices_e_quinas_repetidas(self):
        def par(origem,alvo,p,q):
            return dict(origem='Lateral',destino='Corpo',assinatura=origem,alvo=alvo,
                ponto=p,final=q,distancia=(Vector(p)-Vector(q)).length,raio=.01805)
        bons=[par(str(k),str(k),p,p) for k,p in enumerate(((0,0,0),(0,0,1),(0,1,0),(0,1,1)))]
        ruins=[par('0','extra',(0,0,0),(.1,0,0)),par('perto','perto',(0,0,.018),(0,0,.018))]
        r=addon.solda._refinar_candidatos_ancoras(ruins+list(reversed(bons)))
        self.assertEqual(len(r['aceitas']),1);self.assertEqual(len(r['ligacoes']),1)
        self.assertEqual(len(r['rejeitadas']),len(ruins+bons)-1)
        self.assertTrue(all(c['distancia']==0 for c in r['aceitas']))
        inversos=[dict(c,origem=c['destino'],destino=c['origem'],assinatura=c['alvo'],alvo=c['assinatura'],ponto=c['final'],final=c['ponto']) for c in bons]
        self.assertEqual(len(addon.solda._refinar_candidatos_ancoras(bons+inversos)['aceitas']),1)
        # O limite e' por par de objetos; a mesma quina pode atender outro destino.
        outro=dict(bons[0],destino='Outra peca')
        self.assertEqual(len(addon.solda._refinar_candidatos_ancoras([bons[0],outro])['aceitas']),2)

    def test_piloto_limita_um_par_entre_modulos_mesmo_com_chapas_diferentes(self):
        s=addon.solda
        candidatos=[dict(origem='Chapa A'+str(k),destino='Chapa B'+str(k),par=('Chapa A'+str(k),'Chapa B'+str(k)),
            assinatura='---',alvo='---',ponto=(k,0,0),final=(k+d,0,0),distancia=d,raio=.01805)
            for k,d in enumerate((.1,0.,.02))]
        r=s._refinar_candidatos_ancoras(candidatos)
        self.assertEqual(len(r['aceitas']),3)
        self.assertEqual(r['aceitas'][0]['origem'],'Chapa A1')
        self.assertEqual(r['rejeitadas'],[])
        self.assertEqual(r,s._refinar_candidatos_ancoras(list(reversed(candidatos))))

    def test_par_da_auditoria_respeita_modulos_e_preserva_juntas_internas(self):
        s=addon.solda;a=self.modulo()
        b=bpy.data.objects.new('Outro modulo',None);bpy.context.collection.objects.link(b)
        b[addon.chapas.MARCA_CONJUNTO]=True
        ca=addon.modulos._chapas_do_conjunto(a)
        cb=[addon.chapas.nova_chapa('Outra chapa',400,300,18,(800,0,0),(0,0,0),bpy.context) for _ in range(2)]
        for o in cb:o.parent=b
        self.assertEqual(s._par_qualidade_ancoras(ca[0],cb[0]),tuple(sorted((ca[0].name,cb[0].name))))
        self.assertEqual(s._par_qualidade_ancoras(ca[-1],cb[-1]),tuple(sorted((ca[-1].name,cb[-1].name))))
        self.assertNotEqual(s._par_qualidade_ancoras(ca[0],cb[0]),s._par_qualidade_ancoras(ca[-1],cb[-1]))
        self.assertEqual(s._par_qualidade_ancoras(ca[0],ca[1]),tuple(sorted((ca[0].name,ca[1].name))))
        solta=addon.chapas.nova_chapa('Chapa solta',400,300,18,(0,0,0),(0,0,0),bpy.context)
        self.assertEqual(s._par_qualidade_ancoras(solta,cb[0]),tuple(sorted((solta.name,cb[0].name))))

    def test_auditoria_modulo_e_somente_leitura_e_deterministica(self):
        modulo=self.modulo();pecas=addon.modulos._chapas_do_conjunto(modulo)
        antes=[(o.name,o.matrix_world.copy(),dict(o.items()),o.data.as_pointer()) for o in pecas]
        r=addon.solda.auditar_ancoras(pecas)
        self.assertGreater(r['candidatas'],0)
        self.assertEqual(r,addon.solda.auditar_ancoras(list(reversed(pecas))))
        self.assertEqual(antes,[(o.name,o.matrix_world.copy(),dict(o.items()),o.data.as_pointer()) for o in pecas])

    def test_piloto_busca_quinas_zero_em_vez_de_apenas_deduplicar_ancora_errada(self):
        s=addon.solda;o,n,w=self._nova_solda_manual()
        s.encerrar_conexao_nativa();n.location=(.4,0,0);bpy.context.view_layer.update()
        s._registrar_pares_reais(o,{('x_pos',n.name):[('---','+++')]})
        antes={k:str(v) for k,v in o.items()}
        self.assertGreater(s.auditar_ancoras([o,n])['aceitas'][0]['distancia'],.1)
        r=s.propor_ancoras_piloto([o,n])
        self.assertEqual(len(r['aceitas']),1);self.assertFalse(r['sem_contato'])
        self.assertTrue(all(c['distancia']<=1e-5 for c in r['aceitas']))
        self.assertTrue(all(c['assinatura']!='---' for c in r['aceitas']))
        self.assertEqual(antes,{k:str(v) for k,v in o.items()})
        self.assertEqual(r,s.propor_ancoras_piloto([n,o]))

    def test_piloto_nao_inventa_solda_entre_pecas_sem_contato(self):
        s=addon.solda;o,n,w=self._nova_solda_manual();s.encerrar_conexao_nativa()
        s._registrar_pares_reais(o,{('x_pos',n.name):[('---','---')]})
        r=s.propor_ancoras_piloto([o,n])
        self.assertEqual(r['aceitas'],[]);self.assertEqual(len(r['sem_contato']),1)

    def _nova_solda_manual(self,modelada=False):
        s=addon.solda
        o=addon.chapas.nova_chapa('Origem solda',400,300,18,(0,0,0),(0,0,0),bpy.context)
        if modelada:
            bpy.data.objects.remove(o,do_unlink=True);o=self._chapa_com_deslocamento()
        n=addon.chapas.nova_chapa('Destino solda',400,300,18,(800,200,50),(0,0,0),bpy.context)
        bpy.context.view_layer.update()
        sc=s._ancora_estavel(o,'v0');sn=s._ancora_estavel(n,'v0')
        d=s._vertice_da_assinatura(o,sc)-s._vertice_da_assinatura(n,sn)
        estado=dict(origem=o.name,origens=[o.name],destinos='',fase='confirmar',escolhido=None,
            pares=[(sc,n.name,sn)],moderna=True,distancias=[d.length],direcoes=[tuple(d.normalized())],
            zeradas=[False],snap_nativo=True,pela_gaveta=True,regiao=0)
        s._conexao_manual[0]=estado
        self.addCleanup(s.encerrar_conexao_nativa)
        return o,n,estado

    def _confirmar_solda_manual(self,estado):
        s=addon.solda
        op=SimpleNamespace(_encerrar=lambda ctx:s.encerrar_conexao_nativa(ctx))
        with patch.object(addon.perguntas,'_perguntar'):
            self.assertEqual(s.OBJECT_OT_conectar_vertices._terminar(op,bpy.context),{'FINISHED'})
        self.assertEqual(bpy.ops.object.cabinet_juntar_modulo(juntar=False),{'FINISHED'})
        o=bpy.data.objects[estado['origem']]
        return next(p for p in addon.chapas.PONTAS if o.get('adj_%s_manual'%p))

    def test_solda_previa_distancia_reset_zero_final_fixo_e_cancelamento_integral(self):
        s=addon.solda;o,n,w=self._nova_solda_manual();me=o.data
        filho=bpy.data.objects.new('Filho com restricao',None);bpy.context.collection.objects.link(filho)
        filho.parent=o;filho.location=(.1,.2,.3)
        restricao=filho.constraints.new('COPY_ROTATION');restricao.target=n;restricao.mix_mode='ADD'
        n.rotation_euler.z=.37;bpy.context.view_layer.update();mundo_filho=filho.matrix_world.copy()
        antes=[o.matrix_world@v.co for v in me.vertices];fixo=n.matrix_world.copy()
        self.assertIsNone(s.editar_criacao_solda(.025))
        sc,_nome,sn=w['pares'][0]
        self.assertAlmostEqual((s._vertice_da_assinatura(o,sc)-s._vertice_da_assinatura(n,sn)).length,.025,places=6)
        self.assertIsNone(s.editar_criacao_solda(zerar=True))
        self.assertLess((s._vertice_da_assinatura(o,sc)-s._vertice_da_assinatura(n,sn)).length,1e-6)
        self.assertEqual(w['zeradas'],[True]);self.assertEqual(n.matrix_world,fixo)
        s.encerrar_conexao_nativa();self.assertIs(o.data,me)
        for p,v in zip(antes,me.vertices):self.assertLess((o.matrix_world@v.co-p).length,1e-6)
        self.assertFalse(any(k.startswith('adj_') and o[k] for k in o.keys()))
        bpy.context.view_layer.update()
        for a,b in zip(mundo_filho,filho.matrix_world):self.assertLess((a-b).length,1e-6)

    def test_solda_criacao_voltar_por_backspace_ctrl_z_e_cancelar_por_direito_esc(self):
        s=addon.solda;o,n,w=self._nova_solda_manual()
        area=SimpleNamespace(tag_redraw=lambda:None)
        op=SimpleNamespace(_area=area,_encerrar=lambda ctx:s.encerrar_conexao_nativa(ctx),_na_viewport=lambda e:True)
        for tipo,ctrl in (('BACK_SPACE',False),('Z',True)):
            w.update(fase='confirmar',pares=[(s._ancora_estavel(o,'v0'),n.name,s._ancora_estavel(n,'v0'))],
                distancias=[.2],direcoes=[(1,0,0)],zeradas=[False])
            self.assertEqual(s.OBJECT_OT_conectar_vertices._modal(op,bpy.context,
                SimpleNamespace(type=tipo,value='PRESS',ctrl=ctrl)),{'RUNNING_MODAL'})
            self.assertEqual(w['fase'],'destino');self.assertFalse(w['pares'])
        for tipo in ('RIGHTMOUSE','ESC'):
            s._conexao_manual[0]=w
            self.assertEqual(s.OBJECT_OT_conectar_vertices._modal(op,bpy.context,
                SimpleNamespace(type=tipo,value='PRESS',ctrl=False)),{'CANCELLED'})
            self.assertIsNone(s._conexao_manual[0])

    def test_solda_comandos_da_criacao_nao_criam_vinculos_antes_do_aceite(self):
        s=addon.solda;o,n,w=self._nova_solda_manual()
        self.assertEqual(bpy.ops.object.cabinet_acao_criacao_solda(acao='RESETAR'),{'FINISHED'})
        self.assertEqual(w['distancias'],[0.])
        self.assertEqual(bpy.ops.object.cabinet_acao_criacao_solda(acao='VOLTAR'),{'FINISHED'})
        self.assertTrue(w.pop('voltar'))
        self.assertEqual(bpy.ops.object.cabinet_acao_criacao_solda(acao='CANCELAR'),{'FINISHED'})
        self.assertTrue(w.pop('cancelar'))
        self.assertFalse(any(s._ancoras_gravadas(o,p) for p in addon.chapas.PONTAS))

    def test_solda_confirmada_conserva_zero_e_edita_distancia_apos_giro_espelho(self):
        s=addon.solda;o,n,w=self._nova_solda_manual()
        s.editar_criacao_solda(zerar=True);s.editar_criacao_solda(.04)
        ponta=self._confirmar_solda_manual(w)
        self.assertLess(s._origens_ancoras(o,ponta)[0].length,1e-6)
        raiz=bpy.data.objects.new('Grupo girado',None);bpy.context.collection.objects.link(raiz)
        o.parent=n.parent=raiz;raiz.rotation_euler.z=.63;raiz.scale.x=-1
        bpy.context.view_layer.update();fixo=n.matrix_world.copy()
        self.assertIsNone(s.editar_distancia_solda(o.name,ponta+'|0',.1))
        sc,sn=s._ancoras_gravadas(o,ponta)[0]
        self.assertAlmostEqual((s._vertice_da_assinatura(o,sc)-s._vertice_da_assinatura(n,sn)).length,.1,places=6)
        self.assertEqual(n.matrix_world,fixo)
        self.assertTrue(s.resetar_ponta(o,ponta))
        self.assertLess((s._vertice_da_assinatura(o,sc)-s._vertice_da_assinatura(n,sn)).length,1e-5)
        self.assertTrue(s._ligacoes_adjacencia([o],somente_manuais=True))
        s.desassociar(o,n)
        self.assertNotIn('adj_%s_manual'%ponta,o);self.assertNotIn('adj_%s_direcoes'%ponta,o)

    def test_solda_nova_undo_redo_preserva_metadados_e_posicao_original(self):
        s=addon.solda;o,n,w=self._nova_solda_manual();nome=o.name
        antes=[o.matrix_world@v.co for v in o.data.vertices]
        bpy.ops.ed.undo_push(message='Antes da solda')
        s.editar_criacao_solda(zerar=True);ponta=self._confirmar_solda_manual(w)
        bpy.ops.ed.undo_push(message='Solda criada');o=None;n=None;w=None
        bpy.ops.ed.undo();bpy.context.view_layer.update();addon.eventos._fim_do_desfazer()
        o=bpy.data.objects[nome]
        self.assertNotIn('adj_%s_manual'%ponta,o)
        for p,v in zip(antes,o.data.vertices):self.assertLess((o.matrix_world@v.co-p).length,1e-5)
        o=None
        bpy.ops.ed.redo();bpy.context.view_layer.update();addon.eventos._fim_do_desfazer()
        o=bpy.data.objects[nome]
        self.assertTrue(o['adj_%s_manual'%ponta]);self.assertLess(s._origens_ancoras(o,ponta)[0].length,1e-6)

    def test_ancora_estavel_sobrevive_reordenacao_e_recusa_vertice_apagado(self):
        s=addon.solda;o=self._chapa_com_deslocamento()
        assinatura=s._ancora_estavel(o,'v0');self.assertTrue(assinatura.startswith('u'))
        antes=s._vertice_da_assinatura(o,assinatura)
        bm=bmesh.new()
        try:
            bm.from_mesh(o.data);bm.verts.ensure_lookup_table()
            bm.verts.sort(key=lambda v:-v.index);bm.verts.index_update();bm.to_mesh(o.data)
        finally:bm.free()
        self.assertLess((s._vertice_da_assinatura(o,assinatura)-antes).length,1e-6)
        indice=s._indices_da_assinatura(o,assinatura)[0]
        bm=bmesh.new()
        try:
            bm.from_mesh(o.data);bm.verts.ensure_lookup_table();bm.verts.remove(bm.verts[indice]);bm.to_mesh(o.data)
        finally:bm.free()
        self.assertFalse(s._indices_da_assinatura(o,assinatura))
        with self.assertRaises(ValueError):s._vertice_da_assinatura(o,assinatura)

    def test_solda_criacao_alt_reancora_pelo_snap_nativo_com_destino_restrito(self):
        s=addon.solda;o,n,w=self._nova_solda_manual();fixo=n.matrix_world.copy()
        op=SimpleNamespace(_area=SimpleNamespace(tag_redraw=lambda:None),
            _regiao=SimpleNamespace(x=0,y=0),_w=w,_na_viewport=lambda e:True)
        evento=SimpleNamespace(type='LEFTMOUSE',value='PRESS',ctrl=False,alt=True,mouse_x=10,mouse_y=10)
        with patch.object(s,'_bolinha_sob_mouse',return_value=({'indice':0},'b')):
            # O override usa a VIEW_3D real; nao abre janela nem simula gestos.
            op._area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
            op._regiao=next(r for r in op._area.regions if r.type=='WINDOW')
            with patch.object(addon.gavetas.AssistenteDoVao,'_iniciar_snap_nativo') as nativo:
                self.assertEqual(s.OBJECT_OT_conectar_vertices._modal(op,bpy.context,evento),{'RUNNING_MODAL'})
                nativo.assert_called_once();self.assertEqual(w['alvos_snap'],[n.name])
        self.assertEqual(w['editar_ancora'],(0,'b'));self.assertEqual(n.matrix_world,fixo)

    def test_solda_manual_salvar_anexar_e_renomear_preserva_dados(self):
        import tempfile
        s=addon.solda;o,n,w=self._nova_solda_manual(modelada=True)
        s.editar_criacao_solda(zerar=True);ponta=self._confirmar_solda_manual(w)
        nome=o.name;n.name='Destino renomeado'
        dados={k:str(v) for k,v in o.items() if k.startswith('adj_')}
        with tempfile.TemporaryDirectory() as tmp:
            arquivo=os.path.join(tmp,'solda.blend')
            bpy.data.libraries.write(arquivo,{o,n})
            bpy.data.objects.remove(o,do_unlink=True);bpy.data.objects.remove(n,do_unlink=True);o=None;n=None
            with bpy.data.libraries.load(arquivo,link=False) as (fonte,destino):destino.objects=list(fonte.objects)
            for obj in destino.objects:bpy.context.scene.collection.objects.link(obj)
            bpy.context.view_layer.update();o=bpy.data.objects[nome]
            self.assertEqual(dados,{k:str(v) for k,v in o.items() if k.startswith('adj_')})
            n=s._vizinho_da_ponta(o,ponta);self.assertEqual(n.name,'Destino renomeado')
            self.assertIsNone(s.editar_distancia_solda(o.name,ponta+'|0',.03))
            sc,sn=s._ancoras_gravadas(o,ponta)[0]
            self.assertAlmostEqual((s._vertice_da_assinatura(o,sc)-s._vertice_da_assinatura(n,sn)).length,.03,places=6)

    def test_solda_vertice_apagado_avisa_sem_apagar_ou_reinterpretar_metadados(self):
        s=addon.solda;o,n,w=self._nova_solda_manual(modelada=True)
        ponta=self._confirmar_solda_manual(w);sc,_sn=s._ancoras_gravadas(o,ponta)[0]
        antes={k:str(v) for k,v in o.items() if k.startswith('adj_')}
        indice=s._indices_da_assinatura(o,sc)[0]
        bm=bmesh.new()
        try:
            bm.from_mesh(o.data);bm.verts.ensure_lookup_table();bm.verts.remove(bm.verts[indice]);bm.to_mesh(o.data)
        finally:bm.free()
        self.assertTrue(s.diagnostico_soldas(o))
        self.assertEqual(antes,{k:str(v) for k,v in o.items() if k.startswith('adj_')})
        self.assertTrue(s.editar_distancia_solda(o.name,ponta+'|0',.05))

    def test_solda_manual_controles_em_zero_e_campo_nativo_editavel_sem_alt(self):
        s=addon.solda;o,n,w=self._nova_solda_manual()
        s.editar_criacao_solda(zerar=True)
        for obj in bpy.context.selected_objects:obj.select_set(False)
        ponta=self._confirmar_solda_manual(w)
        self.assertTrue(o.select_get());self.assertEqual(bpy.context.object,o)
        contexto=_ContextoRegiao();contexto.region_data=object()
        with patch.object(s,'_correntes_visiveis',return_value=False), \
             patch.object(addon.hud,'_contexto_hud',return_value=True), \
             patch.object(addon.gaveta,'_eh_area_gaveta',return_value=False), \
             patch.object(addon.hud,'_itens_hud',return_value=[(o,'INDIVIDUAL',[o])]), \
             patch.object(addon.hud,'_projetar_hud',side_effect=lambda _c,p:Vector((p.x*100,p.y*100))):
            correntes=s._correntes_hud(contexto)
        self.assertEqual(len(correntes),1);c=correntes[0];self.assertTrue(c['manual'])
        self.assertEqual(set(s._botoes_da_corrente(contexto,c)),{'corrente','regua'})
        feitos=[]
        def criar(tipo):
            op=SimpleNamespace();feitos.append((tipo,op))
            return SimpleNamespace(matrix_basis=Matrix.Identity(4),as_pointer=lambda:123456,
                target_set_operator=lambda _nome:op)
        grupo=SimpleNamespace(botoes=[],gizmos=SimpleNamespace(new=criar))
        with patch.object(s,'_correntes_hud',return_value=correntes):
            addon.hud.VIEW3D_GGT_correntes_cabinet.draw_prepare(grupo,contexto)
            addon.hud.VIEW3D_GGT_correntes_cabinet.draw_prepare(grupo,contexto)
        self.assertEqual(len(feitos),3)
        campo=feitos[-1][1]
        self.assertEqual((campo.dono,campo.objeto,campo.propriedade),('solda',o.name,ponta+'|0'))
        self.assertAlmostEqual(campo.valor,0,places=6)
        self.assertIn(123456,addon.hud._campos_gaveta)
        addon.hud._campos_gaveta.pop(123456,None)

    def test_solda_snap_sem_cache_consulta_face_nativa_sem_varrer_malha(self):
        s=addon.solda;o,n,w=self._nova_solda_manual()
        s._cache_ancoras[0].clear()
        with patch.object(s,'preparar_ancoras',side_effect=AssertionError('Leitura de toda a malha no clique')):
            ponto=o.matrix_world@o.data.vertices[0].co
            alvo=s._vertice_do_snap(dict(alvos_snap=[o.name]),ponto)
        self.assertEqual(alvo[:2],(o,'v0'))

    def test_raio_da_vista_local_ignora_objeto_oculto_diante_do_modulo(self):
        # Regressao v343: o raio via a parede externa e o clique nativo
        # acabava isolando a chapa que aparecia na vista local do usuario.
        modulo = self.modulo()
        topo = max(addon.modulos._chapas_do_conjunto(modulo),
                   key=lambda o: o.matrix_world.translation.z)
        centro = topo.matrix_world.translation.copy()
        oculto = addon.chapas.nova_chapa('Fora da vista local', 3000, 3000, 18,
            tuple((centro + Vector((0, 0, .5))) * 1000), (0, 0, 0), bpy.context)
        area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        regiao = next(r for r in area.regions if r.type == 'WINDOW')
        self.selecionar(modulo, *modulo.children_recursive, ativo=modulo)
        with bpy.context.temp_override(area=area, region=regiao):
            bpy.ops.view3d.localview(frame_selected=False)
            try:
                bpy.context.view_layer.update()
                self.assertFalse(oculto.visible_get(viewport=area.spaces.active))
                origem = centro + Vector((0, 0, 2))
                direcao = Vector((0, 0, -1))
                primeiro = bpy.context.scene.ray_cast(bpy.context.evaluated_depsgraph_get(), origem, direcao)
                self.assertEqual(primeiro[4].original, oculto)
                with patch.object(addon.hud.view3d_utils, 'region_2d_to_origin_3d', return_value=origem), \
                     patch.object(addon.hud.view3d_utils, 'region_2d_to_vector_3d', return_value=direcao):
                    atingido = addon.hud._raio_hud(bpy.context, (100, 100))
                self.assertEqual(atingido[0], topo)
                for _ in range(2):
                    addon.hud._selecionar_chapa_hud(bpy.context, atingido[0])
                    self.assertEqual(bpy.context.object, modulo)
                    bpy.ops.object.cabinet_editar_grupo()
                    bpy.ops.object.cabinet_editar_grupo()
                    self.assertEqual(bpy.context.object, modulo)
                    self.assertTrue(modulo.select_get())
            finally:
                if bpy.context.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
                bpy.ops.view3d.localview(frame_selected=False)

    def _nova_solda_legada(self, parcial=False):
        modulo=self.modulo();colecao=addon.modulos._colecao_do_modulo(modulo)
        del colecao[addon.modulos.MARCA_COLECAO_MODULO]
        c=max(addon.modulos._chapas_do_conjunto(modulo),key=lambda o:o.matrix_world.translation.x)
        c.location.x+=.4;bpy.context.view_layer.update();addon.solda.desagregar(c)
        n=addon.modulos._chapas_do_conjunto(modulo)[0]
        if parcial:
            mundo=c.matrix_world.copy();c.parent=modulo
            c.matrix_parent_inverse=modulo.matrix_world.inverted();c.matrix_world=mundo
            bpy.context.view_layer.update()
        return modulo,colecao,c,n

    def _confirmar_nova_solda(self,c,n):
        q=addon.solda._vertice_da_assinatura(n,'v1')
        addon.solda._conexao_pendente[0]=dict(origem=c.name,alvos=[('v0',tuple(q))],
            pecas=[n.name],pares=[('v0',n.name,'v1')])
        addon.perguntas._pergunta_atual[0]=dict(texto='Juntar ao modulo?',na_gaveta=True,
            opcoes=[('Sim','CHECKMARK','object.cabinet_juntar_modulo',dict(juntar=True))])
        self.assertEqual(bpy.ops.object.cabinet_responder_pergunta(opcao=0),{'FINISHED'})

    def test_soldar_novamente_reconhece_colecao_importada_sem_marca(self):
        # Regressao v271: o preset tem Collection, mas sem eh_colecao_modulo.
        modulo,colecao,c,n=self._nova_solda_legada()
        nome=modulo.name;antes=[c.matrix_world@v.co for v in c.data.vertices]
        locais=[tuple(v.co) for v in c.data.vertices];me=c.data
        self._confirmar_nova_solda(c,n)
        self.assertIs(addon.modulos._colecao_do_modulo(modulo),colecao)
        self.assertEqual(modulo.name,nome);self.assertEqual(colecao.name,nome)
        self.assertEqual(list(c.users_collection),[colecao]);self.assertIs(c.parent,modulo)
        for p,v in zip(antes,c.data.vertices):self.assertLess((c.matrix_world@v.co-p).length,1e-6)
        self.assertIs(c.data,me);self.assertEqual(locais,[tuple(v.co) for v in me.vertices])
        self.assertFalse(addon.solda._pontas_fora_do_lugar([c]))
        addon.solda.desagregar(c);self._confirmar_nova_solda(c,n)
        self.assertIs(addon.modulos._colecao_do_modulo(modulo),colecao)

    def test_nova_solda_recupera_parentesco_parcial_de_tentativa_que_falhou(self):
        # Regressao v271: o erro ja' tinha religado o pai, deixando a peca na raiz.
        modulo,colecao,c,n=self._nova_solda_legada(parcial=True)
        mundo=c.matrix_world.copy();self._confirmar_nova_solda(c,n)
        self.assertIs(addon.modulos._colecao_do_modulo(modulo),colecao)
        self.assertEqual(list(c.users_collection),[colecao]);self.assertIs(c.parent,modulo)
        for a,b in zip(mundo,c.matrix_world):self.assertLess((a-b).length,1e-6)

    def test_solda_sem_colecao_propria_cria_montagem_sem_tomar_itens_alheios(self):
        # Regressao v271: Empty antigo pode estar numa pasta compartilhada.
        modulo,compartilhada,c,n=self._nova_solda_legada()
        extra=bpy.data.objects.new('Item alheio',None);compartilhada.objects.link(extra)
        nome_antigo=compartilhada.name
        fixos={o.name:o.matrix_world.copy() for o in modulo.children_recursive}
        self._confirmar_nova_solda(c,n)
        propria=addon.modulos._colecao_do_modulo(modulo)
        self.assertIsNotNone(propria);self.assertIsNot(propria,compartilhada)
        self.assertEqual(propria.name,modulo.name)
        self.assertEqual(compartilhada.name,nome_antigo);self.assertEqual(list(extra.users_collection),[compartilhada])
        for o in [modulo,*modulo.children_recursive]:self.assertEqual(list(o.users_collection),[propria])
        for nome,mundo in fixos.items():
            for a,b in zip(mundo,bpy.data.objects[nome].matrix_world):self.assertLess((a-b).length,1e-6)

    def test_soldar_modulo_antigo_na_raiz_cria_colecao_propria(self):
        modulo,antiga,c,n=self._nova_solda_legada()
        addon.modulos._mover_para_colecao(modulo,bpy.context.scene.collection)
        self.assertEqual(list(modulo.users_collection),[bpy.context.scene.collection])
        self._confirmar_nova_solda(c,n)
        propria=addon.modulos._colecao_do_modulo(modulo)
        self.assertIsNotNone(propria);self.assertIsNot(propria,bpy.context.scene.collection)
        self.assertEqual(propria.name,modulo.name);self.assertIsNot(propria,antiga)
        for o in [modulo,*modulo.children_recursive]:self.assertEqual(list(o.users_collection),[propria])
        self.assertFalse(bpy.context.scene.collection.get(addon.modulos.MARCA_COLECAO_MODULO))

    def test_undo_redo_de_nova_solda_restaura_marca_colecao_e_parentesco(self):
        modulo,colecao,c,n=self._nova_solda_legada()
        nome=c.name;grupo=modulo.name;pasta=colecao.name;mundo=c.matrix_world.copy()
        bpy.ops.ed.undo_push(message='Antes de soldar no preset legado')
        self._confirmar_nova_solda(c,n)
        bpy.ops.ed.undo_push(message='Solda no preset com colecao recuperada')
        modulo=None;colecao=None;c=None;n=None
        for funcao,junto in ((bpy.ops.ed.undo,False),(bpy.ops.ed.redo,True)):
            funcao();bpy.context.view_layer.update();addon.eventos._fim_do_desfazer()
            c=bpy.data.objects[nome];colecao=bpy.data.collections[pasta]
            self.assertEqual(bool(colecao.get(addon.modulos.MARCA_COLECAO_MODULO)),junto)
            self.assertEqual(c.parent==bpy.data.objects[grupo],junto)
            self.assertEqual(colecao in c.users_collection,junto)
            for a,b in zip(mundo,c.matrix_world):self.assertLess((a-b).length,1e-6)
            c=None;colecao=None

    def test_alt_corrente_desvincula_lateral_ativa_e_nao_a_base(self):
        # Regressao v270: a base guardava a solda, mas a selecionada era a lateral.
        from unittest.mock import patch
        modulo=self.modulo();chapas=addon.modulos._chapas_do_conjunto(modulo)
        lateral=max(chapas,key=lambda o:o.matrix_world.translation.x)
        addon.hud._selecionar_chapa_hud(bpy.context,lateral,individual=True)
        lateral.location.x+=.5;bpy.context.view_layer.update()
        corrente=next(l for l in addon.solda._ligacoes_adjacencia(chapas) if l['b']==lateral)
        corrente['movel']=addon.solda._peca_da_regua(bpy.context,corrente['a'],corrente['b'])
        self.assertIs(corrente['movel'],lateral);base=corrente['a']
        antes={o.name:o.matrix_world.copy() for o in chapas}
        with patch.object(addon.solda,'_alvo_da_corrente',return_value=('botao',corrente,'corrente')):
            evento=SimpleNamespace(mouse_region_x=0,mouse_region_y=0)
            self.assertEqual(addon.solda.OBJECT_OT_clique_corrente.invoke(None,bpy.context,evento),{'FINISHED'})
        self.assertIsNone(lateral.parent);self.assertIs(base.parent,modulo)
        self.assertFalse(addon.solda._ligados_a(lateral))
        for o in chapas:
            for a,b in zip(antes[o.name],o.matrix_world):self.assertLess((a-b).length,1e-6)
        addon.hud._selecionar_chapa_hud(bpy.context,base)
        item=addon.hud._alvo_hud(bpy.context)
        self.assertNotIn(lateral,item[2])
        self.assertLess(addon.modulos.medir_conjunto(modulo)[0],601)

    def test_gizmo_corrente_desvincula_o_mesmo_alvo_que_a_regua(self):
        # Regressao v270: o gizmo usava o dono do registro em vez da peca ativa.
        from unittest.mock import patch
        modulo,base,tampo,lateral=self.caixote_aberto()
        addon.hud._selecionar_chapa_hud(bpy.context,lateral,individual=True)
        corrente=dict(a=base,b=lateral,movel=lateral,meio=Vector((100,100)))
        operadores=[]
        def operador(nome):
            op=SimpleNamespace(nome=nome);operadores.append(op);return op
        def novo(_nome):return SimpleNamespace(matrix_basis=Matrix.Identity(4),target_set_operator=operador)
        grupo=SimpleNamespace(botoes=[],gizmos=SimpleNamespace(new=novo))
        with patch.object(addon.solda,'_correntes_hud',return_value=[corrente]):
            addon.hud.VIEW3D_GGT_correntes_cabinet.draw_prepare(grupo,bpy.context)
        self.assertEqual(len(operadores),2)
        self.assertTrue(all(op.chapa==lateral.name for op in operadores))

    def test_gizmo_da_solda_reutiliza_operadores_ao_redesenhar_e_trocar_chapa(self):
        # Regressao (era BUG, corrigido na 348): redraw religava o operador
        # sob o mouse e invalidava os dados do tooltip do gizmo nativo.
        modulo, base, tampo, lateral = self.caixote_aberto()
        corrente = dict(a=base, b=lateral, movel=lateral, meio=Vector((100,100)))
        ligados = []
        def ligar(nome):
            op = SimpleNamespace(nome=nome); ligados.append(op); return op
        grupo = SimpleNamespace(botoes=[], gizmos=SimpleNamespace(new=lambda _n:
            SimpleNamespace(matrix_basis=Matrix.Identity(4), target_set_operator=ligar)))
        with patch.object(addon.solda, '_correntes_hud', return_value=[corrente]) as dados:
            for alvo in (lateral, tampo):
                corrente['movel'] = alvo
                addon.hud.VIEW3D_GGT_correntes_cabinet.draw_prepare(grupo, bpy.context)
                self.assertEqual(len(ligados), 2)
                self.assertTrue(all(op.chapa == alvo.name for op in ligados))
            dados.return_value = []
            addon.hud.VIEW3D_GGT_correntes_cabinet.draw_prepare(grupo, bpy.context)
            self.assertTrue(all(b.hide for b in grupo.botoes))
        self.assertEqual(len(ligados), 2)

    def test_clique_da_regua_cancelada_nao_cria_undo_externo(self):
        self.assertNotIn('UNDO', addon.solda.OBJECT_OT_clique_corrente.bl_options)
        alvo = SimpleNamespace(name='Chapa da regua')
        evento = SimpleNamespace(mouse_region_x=0, mouse_region_y=0)
        with patch.object(addon.solda, '_alvo_da_corrente',
                          return_value=('botao', {'movel':alvo}, 'regua')), \
             patch('bpy.ops.object.cabinet_resetar_distancia', return_value={'CANCELLED'}):
            self.assertEqual(addon.solda.OBJECT_OT_clique_corrente.invoke(
                None, bpy.context, evento), {'CANCELLED'})

    def test_detectar_controle_da_solda_calcula_correntes_uma_vez_por_evento(self):
        modulo, base, tampo, lateral = self.caixote_aberto()
        corrente = dict(a=base, b=lateral, movel=lateral, meio=Vector((100,100)),
                       pontos=[Vector((.1,0,0)), Vector((.3,0,0))])
        contexto = _ContextoRegiao()
        with patch.object(addon.solda, '_correntes_hud', return_value=[corrente]) as calcular, \
             patch.object(addon.hud, '_projetar_hud', side_effect=lambda _c,p: Vector((p.x*1000,0))):
            ponto = addon.solda._botoes_da_corrente(contexto, corrente)['regua']
            resultado = addon.solda._alvo_da_corrente(contexto, ponto)
        self.assertEqual(resultado, ('botao', corrente, 'regua'))
        self.assertEqual(calcular.call_count, 1)

    def _modulo_com_lateral_desvinculada(self, grupo_ativo=False):
        from unittest.mock import patch
        modulo=self.modulo()
        prateleiras=addon.prateleiras.criar_prateleiras(bpy.context,modulo,(18,18,18,18,0),
            dict(quantidade=2,espessura_mm=18,profundidade_mm=280))
        # Exercita tambem uma referencia de resize criada ANTES da separacao.
        modulo.conj_largura_mm=650;bpy.context.view_layer.update()
        chapas=addon.modulos._chapas_do_conjunto(modulo)
        lateral=max(chapas,key=lambda o:o.matrix_world.translation.x)
        addon.hud._selecionar_chapa_hud(bpy.context,lateral,individual=True)
        lateral.location.x+=.5;bpy.context.view_layer.update()
        if grupo_ativo:addon.hud._selecionar_chapa_hud(bpy.context,modulo)
        corrente=next(l for l in addon.solda._ligacoes_adjacencia(chapas) if l['b']==lateral)
        corrente['movel']=addon.solda._peca_da_regua(bpy.context,corrente['a'],corrente['b'])
        self.assertIs(corrente['movel'],lateral)
        with patch.object(addon.solda,'_alvo_da_corrente',return_value=('botao',corrente,'corrente')):
            addon.solda.OBJECT_OT_clique_corrente.invoke(None,bpy.context,
                SimpleNamespace(mouse_region_x=0,mouse_region_y=0))
        self.assertIsNone(lateral.parent)
        addon.hud._selecionar_chapa_hud(bpy.context,modulo)
        return modulo,lateral,prateleiras

    def test_corrente_no_grupo_remove_a_lateral_afastada_mesmo_sendo_destino(self):
        modulo,lateral,prateleiras=self._modulo_com_lateral_desvinculada(grupo_ativo=True)
        self.assertIs(addon.prateleiras.modulo_do_grupo(prateleiras),modulo)
        self.assertNotIn(lateral,addon.modulos.pecas_do_envelope(modulo))
        self.assertLess(addon.modulos.medir_conjunto(modulo)[0],651)

    def test_hud_e_menu_redimensionam_so_o_modulo_apos_desvincular(self):
        modulo,lateral,prateleiras=self._modulo_com_lateral_desvinculada()
        # Escolha original do nicho 600x400, antes de ampliar/desvincular.
        limite_internos=(564.,364.)
        mundo=lateral.matrix_world.copy();me=lateral.data;vertices=[tuple(v.co) for v in me.vertices]
        for caminho in ('hud','menu'):
            for eixo in (0,1,2):
                campos=addon.hud.campos_cotas(modulo,'GRUPO',addon.modulos.pecas_do_envelope(modulo))
                campo=next(c for c in campos if addon.hud.alvo_cota(modulo,c[2])['eixo']==eixo)
                for valor in (campo[1]+120,campo[1]):
                    with self.subTest(caminho=caminho,eixo=eixo,valor=valor):
                        if caminho=='hud':
                            alvo=addon.hud.alvo_cota(modulo,campo[2]);alvo['lado']='max'
                            addon.hud._aplicar_valor_hud(bpy.context,alvo,valor)
                        else:
                            self.assertEqual(bpy.ops.object.cabinet_editar_medida_gaveta('EXEC_DEFAULT',
                                dono='cota',objeto=modulo.name,propriedade=campo[2],valor=valor/1000),{'FINISHED'})
                        bpy.context.view_layer.update()
                        atual=addon.hud.alvo_cota(modulo,campo[2])
                        self.assertAlmostEqual(addon.hud._valor_hud(atual),valor,places=2)
                        self.assertNotIn(lateral,atual['chapas'])
                        self.assertEqual(vertices,[tuple(v.co) for v in me.vertices]);self.assertIs(lateral.data,me)
                        for a,b in zip(mundo,lateral.matrix_world):self.assertLess((a-b).length,1e-6)
                        largura,altura,_matriz=addon.prateleiras.vao(prateleiras)
                        esperado=addon.modulos.medir_conjunto(modulo)
                        # v288: o vao conserva a escolha, nao cresce com a caixa.
                        self.assertLessEqual(largura,min(limite_internos[0],esperado[0])+.05)
                        self.assertLessEqual(altura,min(limite_internos[1],esperado[1])+.05)
        # Mover a peca ja' solta de novo nao muda nem o vao nem a HUD do grupo.
        antes=addon.modulos.medir_conjunto(modulo)
        lateral.location.x+=2;bpy.context.view_layer.update()
        for a,b in zip(antes,addon.modulos.medir_conjunto(modulo)):self.assertAlmostEqual(a,b,places=3)

    def test_undo_redo_da_corrente_conserva_o_escopo_real_do_modulo(self):
        from unittest.mock import patch
        modulo=self.modulo();chapas=addon.modulos._chapas_do_conjunto(modulo)
        lateral=max(chapas,key=lambda o:o.matrix_world.translation.x)
        nome=lateral.name;grupo=modulo.name
        addon.hud._selecionar_chapa_hud(bpy.context,lateral,individual=True)
        lateral.location.x+=.5;bpy.context.view_layer.update()
        corrente=next(l for l in addon.solda._ligacoes_adjacencia(chapas) if l['b']==lateral)
        corrente['movel']=lateral
        bpy.ops.ed.undo_push(message='Lateral afastada e vinculada')
        with patch.object(addon.solda,'_alvo_da_corrente',return_value=('botao',corrente,'corrente')):
            addon.solda.OBJECT_OT_clique_corrente.invoke(None,bpy.context,SimpleNamespace(mouse_region_x=0,mouse_region_y=0))
        bpy.ops.ed.undo_push(message='Lateral desvinculada');corrente=None;modulo=None;lateral=None;chapas=None
        for funcao,vinculada in ((bpy.ops.ed.undo,True),(bpy.ops.ed.redo,False)):
            funcao();bpy.context.view_layer.update();addon.eventos._fim_do_desfazer()
            modulo=bpy.data.objects[grupo];lateral=bpy.data.objects[nome]
            self.assertEqual(lateral.parent==modulo,vinculada)
            self.assertEqual(lateral in addon.modulos.pecas_do_envelope(modulo),vinculada)
            modulo=None;lateral=None

    def _cadastrar_gap(self, varios=False):
        o=self._chapa_com_deslocamento();n=self._chapa_com_deslocamento()
        n.location+=Vector((.43,.17,.08));bpy.context.view_layer.update()
        ancoras=[('v0','v3'),('v2','v5')] if varios else [('v0','v3')]
        # O legado precisa continuar legivel, embora o cadastro novo aceite um so par.
        s=addon.solda
        addon.chapas._gravar_ligacao(o,'x','pos',n,0.,0)
        o['adj_x_pos_folga']=s._folga_com_sinal(o,'x_pos',n)[0]
        s._gravar_ancoras(o,'x_pos',ancoras)
        inversa=n.matrix_world.inverted().to_3x3()
        o['adj_x_pos_origens']=json.dumps([tuple(inversa@(
            s._vertice_da_assinatura(o,sc)-s._vertice_da_assinatura(n,sn))) for sc,sn in ancoras])
        self.assertEqual(len(s._ancoras_gravadas(o,'x_pos')),2 if varios else 1)
        return o,n,'x_pos'

    def test_gap_cadastrado_nao_move_nem_acende_reset(self):
        o,n,ponta=self._cadastrar_gap(True)
        self.assertIsNone(addon.solda._plano_reset_chapa(o))
        self.assertFalse(addon.solda._pontas_fora_do_lugar([o,n]))
        self.assertFalse(addon.solda.resetar_ponta(o,ponta))
        origens=addon.solda._origens_ancoras(o,ponta)
        self.assertGreater((origens[0]-origens[1]).length,.01)

    def test_reset_restaura_gap_3D_sem_mudar_forma_E_Mesh_ou_alvo(self):
        o,n,ponta=self._cadastrar_gap(True);me=o.data
        antes=[o.matrix_world@v.co for v in me.vertices];fixo=n.matrix_world.copy()
        locais=[tuple(v.co) for v in me.vertices];registro=o['adj_'+ponta+'_origens']
        o.location+=Vector((.11,-.07,.05));bpy.context.view_layer.update()
        addon.hud._selecionar_chapa_hud(bpy.context,o,individual=True)
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(),{'FINISHED'})
        self.assertIs(o.data,me);self.assertEqual(locais,[tuple(v.co) for v in me.vertices])
        self.assertEqual(registro,o['adj_'+ponta+'_origens'])
        for p,v in zip(antes,me.vertices):self.assertLess((o.matrix_world@v.co-p).length,1e-6)
        for a,b in zip(fixo,n.matrix_world):self.assertLess((a-b).length,1e-6)
        self.assertFalse(addon.solda._pontas_fora_do_lugar([o,n]))

    def test_reset_do_destino_tambem_restaura_gap_cadastrado(self):
        o,n,ponta=self._cadastrar_gap();antes=n.matrix_world.copy();fixo=o.matrix_world.copy()
        n.location+=Vector((-.04,.09,-.06));bpy.context.view_layer.update()
        plano=addon.solda._plano_reset_chapa(n)
        self.assertFalse(plano['muda_medida']);addon.solda._aplicar_reset_chapa(n,plano)
        for a,b in zip(antes,n.matrix_world):self.assertLess((a-b).length,1e-6)
        for a,b in zip(fixo,o.matrix_world):self.assertLess((a-b).length,1e-6)

    def test_gap_acompanha_rotacao_e_translacao_do_modulo(self):
        o,n,ponta=self._cadastrar_gap(True)
        pai=bpy.data.objects.new('Modulo de teste',None);bpy.context.scene.collection.objects.link(pai)
        for p in (o,n):
            mundo=p.matrix_world.copy();p.parent=pai;p.matrix_world=mundo
        pai.rotation_euler=(.3,-.4,.7);pai.location=(3,2,1);bpy.context.view_layer.update()
        self.assertFalse(addon.solda._pontas_fora_do_lugar([o,n]))
        antes=[o.matrix_world@v.co for v in o.data.vertices]
        mundo=o.matrix_world.copy();mundo.translation+=Vector((.06,-.03,.02));o.matrix_world=mundo
        bpy.context.view_layer.update();self.assertTrue(addon.solda.resetar_ponta(o,ponta))
        for p,v in zip(antes,o.data.vertices):self.assertLess((o.matrix_world@v.co-p).length,1e-6)

    def test_origens_da_ancora_saem_ao_desligar_ou_substituir_junta(self):
        for operacao in ('limpar','substituir','desassociar','converter_destino'):
            with self.subTest(operacao=operacao):
                o,n,ponta=self._cadastrar_gap()
                if operacao=='limpar':addon.chapas._limpar_ponta(o,ponta)
                elif operacao=='substituir':addon.chapas._gravar_ligacao(o,'x','pos',n,.02,0)
                elif operacao=='desassociar':addon.solda.desassociar(o,n)
                else:
                    addon.hud._selecionar_chapa_hud(bpy.context,n,individual=True)
                    self.assertEqual(bpy.ops.object.cabinet_marcar(alternar=True),{'FINISHED'})
                self.assertNotIn('adj_'+ponta+'_origens',o)

    def test_reset_de_gaps_distintos_recupera_vertices_sem_media(self):
        o,n,ponta=self._cadastrar_gap(True)
        ancoras=addon.solda._ancoras_gravadas(o,ponta)
        antes={s:addon.solda._vertice_da_assinatura(o,s) for s,_ in ancoras}
        for k,(s,_sn) in enumerate(ancoras):
            d=Vector((.03*(k+1),-.02*k,.01))
            for t in {s,addon.solda._parceiro_espessura(o,s)}:
                for i in addon.solda._indices_da_assinatura(o,t):o.data.vertices[i].co+=d
        o.data.update();bpy.context.view_layer.update()
        self.assertTrue(addon.solda.resetar_ponta(o,ponta))
        for s,p in antes.items():self.assertLess((addon.solda._vertice_da_assinatura(o,s)-p).length,1e-6)
        self.assertFalse(addon.solda._pontas_fora_do_lugar([o,n]))

    def test_undo_redo_do_reset_preserva_origem_cadastrada(self):
        o,n,ponta=self._cadastrar_gap();nome=o.name;registro=o['adj_'+ponta+'_origens']
        origem=[o.matrix_world@v.co for v in o.data.vertices]
        d=Vector((.06,-.03,.02));o.location+=d;bpy.context.view_layer.update()
        addon.hud._selecionar_chapa_hud(bpy.context,o,individual=True)
        bpy.ops.ed.undo_push(message='Gap afastado')
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(),{'FINISHED'})
        bpy.ops.ed.undo_push(message='Gap restaurado');o=None;n=None
        for funcao,deslocamento in ((bpy.ops.ed.undo,d),(bpy.ops.ed.redo,Vector())):
            funcao();bpy.context.view_layer.update();addon.eventos._fim_do_desfazer()
            o=bpy.data.objects[nome];self.assertEqual(o['adj_'+ponta+'_origens'],registro)
            for p,v in zip(origem,o.data.vertices):self.assertLess((o.matrix_world@v.co-p-deslocamento).length,1e-6)
            o=None

    def test_criar_solda_do_modulo_escolhe_origem_no_primeiro_snap_e_confirma_no_menu(self):
        S = addon.solda
        modulo = self.modulo()
        chapas = addon.modulos._chapas_do_conjunto(modulo)
        origem = chapas[0]
        origem.location.z += 5
        destino = self._chapa_com_deslocamento()
        destino.location = (3,3,3)
        bpy.context.view_layer.update()
        p = origem.matrix_world @ origem.data.vertices[0].co
        q = destino.matrix_world @ destino.data.vertices[0].co
        area = SimpleNamespace(tag_redraw=lambda:None, header_text_set=lambda _s:None)
        regiao = SimpleNamespace(as_pointer=lambda:333)
        contexto = _ContextoRegiao()
        contexto.object = modulo
        contexto.window_manager = SimpleNamespace(windows=[], modal_handler_add=lambda _o:None,
            event_timer_add=lambda *_a,**_k:object(), event_timer_remove=lambda _t:None)
        op = SimpleNamespace(origem='', destinos='', report=lambda *_a:None)
        op._encerrar = lambda ctx:S.encerrar_conexao_nativa(ctx)
        self.addCleanup(S.encerrar_conexao_nativa, contexto)
        with patch.object(addon.importacao, '_viewport_alvo', return_value=(area,regiao,object())), \
             patch.object(addon.perguntas, '_na_gaveta', [True]):
            self.assertEqual(S.OBJECT_OT_conectar_vertices.invoke(op,contexto,None), {'RUNNING_MODAL'})
        estado = S._conexao_manual[0]
        self.assertEqual(estado['origem'], '')
        self.assertEqual(set(estado['alvos_snap']), {o.name for o in chapas})
        self.assertNotIn(destino.name, estado['alvos_snap'])
        estado['ponto_confirmado'] = (p,None)
        self.assertEqual(S.OBJECT_OT_conectar_vertices._modal(op,contexto,None), {'RUNNING_MODAL'})
        self.assertEqual(estado['origem'], origem.name)
        self.assertEqual(estado['fase'], 'destino')
        self.assertIn(destino.name, estado['alvos_snap'])
        estado['ponto_confirmado'] = (q,None)
        S.OBJECT_OT_conectar_vertices._modal(op,contexto,None)
        self.assertEqual(estado['pares'], [(S._ancora_estavel(origem,'v0'),destino.name,S._ancora_estavel(destino,'v0'))])
        with patch.object(S, '_perguntar_juntar') as perguntar:
            self.assertEqual(S.OBJECT_OT_conectar_vertices._terminar(op,contexto), {'FINISHED'})
        self.assertTrue(perguntar.call_args.args[4])
        self.assertIsNone(S._conexao_manual[0])
        self.assertIsNone(S._timer_conexao[0])
        self.assertIsNone(S._handler_conexao[0])

    def test_selecao_de_solda_usa_todos_os_vertices_nativos_sem_caixa(self):
        from unittest.mock import patch
        o=self._chapa_com_deslocamento()
        estado=dict(origem=o.name,fase='origem')
        with patch.object(addon.chapas,'_cantos',side_effect=AssertionError('Recriou cantos nominais')):
            addon.solda._preparar_candidatos_conexao(estado)
        candidatos=addon.solda._candidatos_conexao(estado)
        self.assertEqual(len(candidatos),len(o.data.vertices))
        for obj,s,p in candidatos:
            self.assertIs(obj,o);self.assertTrue(s.startswith('v'))
            self.assertLess((p-o.matrix_world@o.data.vertices[int(s[1:])].co).length,1e-6)
            alvo=addon.solda._vertice_do_snap(estado,p)
            self.assertEqual(alvo[:2],(o,s))
        self.assertIsNone(addon.solda._vertice_do_snap(estado,o.matrix_world.translation+Vector((3,3,3))))

    def test_snap_de_solda_reutiliza_translate_nativo_sem_projecao_de_vertices(self):
        inicio=inspect.getsource(addon.gavetas.AssistenteDoVao._iniciar_snap_nativo)
        self.assertIn('cabinet_marcar_ponto_vao',inicio)
        self.assertIn('cursor_transform=True',inicio)
        self.assertIn('alvos_snap',inicio)
        modal=inspect.getsource(addon.solda.OBJECT_OT_conectar_vertices._modal)
        self.assertIn('AssistenteDoVao._iniciar_snap_nativo',modal)
        self.assertNotIn('location_3d_to_region_2d',inspect.getsource(addon.solda.OBJECT_OT_conectar_vertices._sob_mouse))

    def test_snap_compartilhado_da_solda_devolve_cursor_e_alvos_ao_confirmar(self):
        o=self._chapa_com_deslocamento();cursor=bpy.context.scene.cursor.location.copy()
        estado=dict(snap_nativo=True,etapa='SOLDA')
        addon.solda._conexao_manual[0]=estado
        self.addCleanup(lambda:addon.solda._conexao_manual.__setitem__(0,None))
        addon.gavetas._snap_criacao[0]=dict(cena=bpy.context.scene.name,cursor=tuple(cursor),
            bloqueados=[(o.name,o.hide_select)],area=0,mostrar_cursor=False)
        o.hide_select=True;novo=Vector((.22,.33,.44));bpy.context.scene.cursor.location=novo
        self.assertIs(addon.gavetas._estado_criacao(),estado)
        self.assertEqual(bpy.ops.object.cabinet_confirmar_ponto_vao(),{'FINISHED'})
        self.assertLess((estado['ponto_confirmado'][0]-novo).length,1e-6)
        self.assertIsNone(estado['ponto_confirmado'][1])
        self.assertLess((bpy.context.scene.cursor.location-cursor).length,1e-6)
        self.assertFalse(o.hide_select);self.assertIsNone(addon.gavetas._snap_criacao[0])

    def test_fim_da_escolha_resolve_destino_na_malha_real(self):
        from unittest.mock import patch
        o=self._chapa_com_deslocamento();n=self._chapa_com_deslocamento()
        estado=dict(origem=o.name,pares=[('v0',n.name,'v3')])
        operador=SimpleNamespace(_encerrar=lambda contexto:estado)
        chamadas=[]
        with patch.object(addon.solda,'_perguntar_juntar',side_effect=lambda *args:chamadas.append(args)):
            self.assertEqual(addon.solda.OBJECT_OT_conectar_vertices._terminar(operador,bpy.context),{'FINISHED'})
        self.assertLess((chamadas[0][2][0][1]-n.matrix_world@n.data.vertices[3].co).length,1e-6)
        self.assertEqual(chamadas[0][-1],estado['pares'])

    def test_juntar_chapa_torcida_preserva_forma_e_cadastra_afastamento(self):
        modulo=self.modulo();alvo=addon.modulos._chapas_do_conjunto(modulo)[0]
        o=self._chapa_com_deslocamento();me=o.data
        mundo=[o.matrix_world@v.co for v in me.vertices];locais=[tuple(v.co) for v in me.vertices]
        q=alvo.matrix_world@alvo.data.vertices[0].co;delta=q-mundo[0]
        fixos={p.name:[p.matrix_world@v.co for v in p.data.vertices] for p in addon.modulos._chapas_do_conjunto(modulo)}
        addon.solda.juntar_conexao(o,[('v0',q)],{alvo},True,[('v0',alvo.name,'v0')])
        self.assertIs(o.data,me);self.assertIs(o.parent,modulo)
        self.assertEqual(locais,[tuple(v.co) for v in me.vertices])
        for p,v in zip(mundo,me.vertices):self.assertLess((o.matrix_world@v.co-p).length,1e-6)
        self.assertGreater((o.matrix_world@me.vertices[0].co-q).length,.01)
        self.assertFalse(addon.solda._pontas_fora_do_lugar([o]))
        juntas=[p for p in addon.chapas.PONTAS if addon.solda._ancoras_gravadas(o,p)]
        self.assertEqual(len(juntas),1);self.assertIsNotNone(addon.solda._origens_ancoras(o,juntas[0]))
        for nome,ps in fixos.items():
            p=bpy.data.objects[nome]
            for a,v in zip(ps,p.data.vertices):self.assertLess((p.matrix_world@v.co-a).length,1e-6)

    def test_juntar_varias_ancoras_reais_chega_a_zero_sem_media(self):
        o=self._chapa_com_deslocamento();me=o.data
        secao=addon.chapas._secao_espessura(me)
        a=0;b=next(i for i,g in enumerate(secao['grupos']) if g!=secao['grupos'][a])
        alvos=[('v%d'%i,o.matrix_world@me.vertices[i].co+Vector(d)) for i,d in ((a,(.04,.03,.01)),(b,(-.02,.06,.01)))]
        addon.solda._puxar_por_pares(o,alvos)
        for s,q in alvos:self.assertLess((addon.solda._vertice_da_assinatura(o,s)-q).length,1e-6)
        self.assertIs(o.data,me)
        self.assertAlmostEqual(addon.chapas._secao_espessura(me)['espessura_mm'],18,places=3)

    def test_ancoras_incompativeis_nao_deformam_espessura(self):
        o=self._chapa_com_deslocamento();antes=[tuple(v.co) for v in o.data.vertices]
        a='v0';b=addon.solda._parceiro_espessura(o,a)
        alvos=[(a,addon.solda._vertice_da_assinatura(o,a)+Vector((.1,0,0))),
               (b,addon.solda._vertice_da_assinatura(o,b)+Vector((.2,0,0)))]
        with self.assertRaisesRegex(ValueError,'espessura'):addon.solda._puxar_por_pares(o,alvos)
        self.assertEqual(antes,[tuple(v.co) for v in o.data.vertices])

    def test_parceiro_de_espessura_nao_depende_do_sinal_do_Z(self):
        o=self._chapa_com_deslocamento();secao=addon.chapas._secao_espessura(o.data)
        for i,g in enumerate(secao['grupos']):
            parceiro=addon.solda._parceiro_espessura(o,'v%d'%i)
            j=int(parceiro[1:]);self.assertNotEqual(i,j)
            self.assertEqual(secao['grupos'][j],g)
            self.assertAlmostEqual((o.data.vertices[i].co-o.data.vertices[j].co).length,.018,places=6)

    def test_solda_automatica_tambem_aponta_vertices_reais_da_chapa_torcida(self):
        from unittest.mock import patch
        o=self._chapa_com_deslocamento();n=self._chapa_com_deslocamento()
        n.location.x+=.4;bpy.context.view_layer.update()
        addon.frentes.preparar(o,forcar=True);addon.frentes.preparar(n,forcar=True)
        addon.chapas._gravar_ligacao(o,'x','pos',n,0,0)
        with patch.object(addon.chapas,'_cantos',side_effect=AssertionError('Caixa nominal')),\
             patch.object(addon.solda,'KDTree',side_effect=AssertionError('Reconstruiu KD no redraw')):
            pares=addon.solda._ancoras_da_ligacao(o,'x_pos',n)
        self.assertEqual(len(pares),1)
        for sc,sn in pares:
            for obj,s in ((o,sc),(n,sn)):
                p=addon.solda._vertice_da_assinatura(obj,s)
                self.assertLess(min((p-obj.matrix_world@v.co).length for v in obj.data.vertices),1e-6)

    def test_undo_redo_de_juntar_preserva_vertices_e_ancora(self):
        modulo=self.modulo();n=addon.modulos._chapas_do_conjunto(modulo)[0]
        o=self._chapa_com_deslocamento();nome=o.name
        antes=[o.matrix_world@v.co for v in o.data.vertices]
        q=n.matrix_world@n.data.vertices[0].co
        bpy.ops.ed.undo_push(message='Antes da solda nativa')
        addon.solda._conexao_pendente[0]=dict(origem=nome,alvos=[('v0',tuple(q))],pecas=[n.name],pares=[('v0',n.name,'v0')])
        self.assertEqual(bpy.ops.object.cabinet_juntar_modulo(juntar=True),{'FINISHED'})
        bpy.ops.ed.undo_push(message='Depois da solda nativa');o=None;n=None;modulo=None
        for funcao,junto in ((bpy.ops.ed.undo,False),(bpy.ops.ed.redo,True)):
            funcao();bpy.context.view_layer.update();addon.eventos._fim_do_desfazer()
            o=bpy.data.objects[nome]
            for p,v in zip(antes,o.data.vertices):self.assertLess((o.matrix_world@v.co-p).length,1e-6)
            juntas=[p for p in addon.chapas.PONTAS if addon.solda._origens_ancoras(o,p) is not None]
            self.assertEqual(bool(juntas),junto)
            o=None

    def test_juntar_duas_soltas_conserva_ancoras_ao_criar_modulo(self):
        from unittest.mock import patch
        o=self._chapa_com_deslocamento();n=self._chapa_com_deslocamento()
        n.location.x+=.4;bpy.context.view_layer.update()
        q=n.matrix_world@n.data.vertices[0].co;antes=o.matrix_world@o.data.vertices[0].co
        addon.solda._conexao_pendente[0]=dict(origem=o.name,alvos=[('v0',tuple(q))],
            pecas=[n.name],pares=[('v0',n.name,'v0')])
        with patch.object(addon.solda,'_pedir_nome_grupo'):
            self.assertEqual(bpy.ops.object.cabinet_juntar_modulo(juntar=True),{'FINISHED'})
        self.assertIsNotNone(o.parent);self.assertIs(o.parent,n.parent)
        juntas=[p for p in addon.chapas.PONTAS if addon.solda._ancoras_gravadas(o,p)]
        self.assertEqual(len(juntas),1)
        self.assertEqual(addon.solda._ancoras_gravadas(o,juntas[0]),[('v0','v0')])
        self.assertIsNotNone(addon.solda._origens_ancoras(o,juntas[0]))
        self.assertLess((o.matrix_world@o.data.vertices[0].co-antes).length,1e-6)
        self.assertFalse(addon.solda._pontas_fora_do_lugar([o,n]))

    def test_escolha_de_solda_pausa_apos_par_para_concluir_com_enter(self):
        from unittest.mock import patch
        o=self._chapa_com_deslocamento();n=self._chapa_com_deslocamento()
        estado=dict(origem=o.name,fase='destino',escolhido=('v0',o.matrix_world@o.data.vertices[0].co),
            destinos=addon.solda._nomes([n]),pares=[],snap_nativo=True,snap_pendente=True)
        addon.solda._preparar_candidatos_conexao(estado)
        estado['ponto_confirmado']=(n.matrix_world@n.data.vertices[0].co,None)
        addon.solda._conexao_manual[0]=estado
        self.addCleanup(lambda:addon.solda._conexao_manual.__setitem__(0,None))
        operador=SimpleNamespace(_area=SimpleNamespace(tag_redraw=lambda:None),_terminar=lambda ctx:{'FINISHED'})
        evento=SimpleNamespace(type='TIMER',value='NOTHING')
        self.assertEqual(addon.solda.OBJECT_OT_conectar_vertices._modal(operador,bpy.context,evento),{'RUNNING_MODAL'})
        self.assertEqual(len(estado['pares']),1);self.assertFalse(estado['iniciar_snap'])
        evento=SimpleNamespace(type='RET',value='PRESS')
        self.assertEqual(addon.solda.OBJECT_OT_conectar_vertices._modal(operador,bpy.context,evento),{'FINISHED'})

    def _conferir_bordas_reais(self,o,quantidade):
        geo=addon.hud._geometria_do_item(o,'INDIVIDUAL',[o])
        bordas=[l for l in geo['linhas'] if l['tipo']=='aresta']
        self.assertEqual(len(bordas),quantidade*2)
        reais=[o.matrix_world@v.co for v in o.data.vertices]
        segmentos=[(reais[e.vertices[0]],reais[e.vertices[1]]) for e in o.data.edges]
        for linha in [l for l in geo['linhas'] if not l.get('angulo') and l['tipo']!='deslocamento']:
            a,b=linha['pontos']
            erro=min(min((a-p).length+(b-q).length,(a-q).length+(b-p).length) for p,q in segmentos)
            self.assertLess(erro,1e-6,'Contorno fora da madeira: '+str(linha))
        for linha in bordas:
            self.assertAlmostEqual(addon.hud._valor_hud(linha),(linha['pontos'][1]-linha['pontos'][0]).length*1000,places=3)
        return geo

    def test_chapa_quadrada_torcida_nao_usa_caixa_plana(self):
        # Regressao v267: a HUD flutuava fora da lateral real de oito vertices.
        o=addon.chapas.nova_chapa('Lateral torcida',550,720,15,(0,0,0),(90,0,90),bpy.context)
        for v in o.data.vertices:
            if v.co.x<0 and v.co.y<0:v.co.z-=.194569
        o.data.update();addon.chapas.absorver_malha_editada(o);addon.frentes.preparar(o)
        self.assertIsNone(addon.formas.forma_do_modulo(o))
        geo=self._conferir_bordas_reais(o,4)
        self.assertEqual(len({l['rotulo'] for l in geo['linhas'] if l.get('rotulo')}),6)

    def _chapa_com_pele_editada_por_tab(self):
        o=addon.chapas.nova_chapa('Lateral com topo editado',600,2000,18,
            (0,0,0),(90,0,0),bpy.context)
        for outro in bpy.context.selected_objects:outro.select_set(False)
        o.select_set(True);bpy.context.view_layer.objects.active=o
        addon.frentes.preparar(o)
        addon.hud._geometria_do_item(o,'INDIVIDUAL',[o])
        malha=o.data
        bpy.ops.object.mode_set(mode='EDIT')
        addon.chapas.absorver_edicoes_de_malha()
        bm=bmesh.from_edit_mesh(malha)
        for v in bm.verts:
            if v.co.x<0 and v.co.y>0 and v.co.z>0:v.co.y+=.08
        bmesh.update_edit_mesh(malha)
        bpy.ops.object.mode_set(mode='OBJECT')
        addon.chapas.absorver_edicoes_de_malha()
        bpy.context.view_layer.update()
        self.assertIs(o.data,malha)
        self.assertAlmostEqual(o.chapa_espessura_mm,18,places=3)
        return o

    def _conferir_cotas_na_malha(self,o):
        malha=o.data
        geo=addon.hud._geometria_do_item(o,'INDIVIDUAL',[o])
        reais=[o.matrix_world@v.co for v in malha.vertices]
        arestas=[(reais[e.vertices[0]],reais[e.vertices[1]]) for e in malha.edges]
        for linha in geo['linhas']:
            if linha.get('angulo') or linha['tipo']=='deslocamento':continue
            a,b=linha['pontos']
            erro=min(min((a-p).length+(b-q).length,(a-q).length+(b-p).length) for p,q in arestas)
            self.assertLess(erro,1e-6,'Cota fora da chapa apos Tab: '+str(linha))
            if linha['tipo']=='aresta':
                self.assertAlmostEqual(addon.hud._valor_hud(linha),(b-a).length*1000,places=3)
        return geo

    # Regressao (era BUG, corrigido na 380): Tab de uma pele projetava a outra.
    def test_tab_em_canto_da_chapa_plana_mantem_cotas_nas_arestas_reais(self):
        self._conferir_cotas_na_malha(self._chapa_com_pele_editada_por_tab())

    def _moldura_afinada_para_fechamento(self,registrar_tab=True,fator=.1,guardar_undo=False):
        grupo=bpy.data.objects.new('Porta com moldura',None)
        bpy.context.scene.collection.objects.link(grupo)
        grupo[addon.chapas.MARCA_PORTAS]=1
        grupo['porta_parametros']=dict(moldura_mm=15.,largura_mm=649.,altura_mm=2531.)
        o=addon.chapas.nova_chapa('Moldura para fechamento',649,2531,15,
            (0,0,0),(0,0,0),bpy.context)
        o[addon.chapas.MARCA_MOLDURA]=1;o.parent=grupo
        for outro in bpy.context.selected_objects:outro.select_set(False)
        o.select_set(True);bpy.context.view_layer.objects.active=o
        addon.hud._geometria_do_item(o,'INDIVIDUAL',[o])
        if guardar_undo:bpy.ops.ed.undo_push(message='Moldura antes do fechamento')
        bpy.ops.object.mode_set(mode='EDIT')
        if registrar_tab:addon.chapas.absorver_edicoes_de_malha()
        bm=bmesh.from_edit_mesh(o.data)
        for v in bm.verts:v.co.x=v.co.x*fator-.15
        bmesh.update_edit_mesh(o.data)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.transform.rotate(value=math.pi/2,orient_axis='X',orient_type='GLOBAL')
        bpy.context.view_layer.update()
        return o,grupo

    # Regressao (era BUG, corrigido na 381): moldura conservava caixa de 649 mm.
    def test_tab_afina_moldura_gira_vertical_e_hud_acompanha_malha(self):
        o,grupo=self._moldura_afinada_para_fechamento()
        malha=o.data;mundo=[o.matrix_world@v.co for v in malha.vertices]
        parametros=grupo['porta_parametros'].to_dict()
        addon.chapas.absorver_edicoes_de_malha();bpy.context.view_layer.update()
        self.assertAlmostEqual(o.chapa_largura_mm,64.9,places=3)
        self.assertAlmostEqual(o.chapa_comprimento_mm,2531,places=3)
        self.assertAlmostEqual(o.chapa_espessura_mm,15,places=3)
        self._conferir_cotas_na_malha(o)
        self.assertEqual(grupo['porta_parametros'].to_dict(),parametros)
        self.assertIs(o.data,malha)
        for p,v in zip(mundo,malha.vertices):self.assertLess((p-o.matrix_world@v.co).length,1e-6)

    # Regressao (era BUG, corrigido na 381): cena antiga nao tinha transicao Tab.
    def test_moldura_ja_editada_corrige_limites_no_timer_sem_novo_tab(self):
        o,grupo=self._moldura_afinada_para_fechamento(registrar_tab=False)
        addon.chapas._chapas_em_edicao.clear()
        addon.frentes.preparar(o)
        addon.chapas.absorver_edicoes_de_malha()
        self.assertAlmostEqual(o.chapa_largura_mm,64.9,places=3)
        self._conferir_cotas_na_malha(o)

    def test_fechamento_mais_estreito_que_E_mantem_contorno_e_espessura(self):
        o,grupo=self._moldura_afinada_para_fechamento(fator=3/649)
        addon.chapas.absorver_edicoes_de_malha()
        self.assertAlmostEqual(o.chapa_largura_mm,3,places=3)
        self.assertAlmostEqual(o.chapa_espessura_mm,15,places=3)
        self._conferir_cotas_na_malha(o)

    def test_moldura_sincronizada_nao_reextrai_malha_a_cada_timer(self):
        o,grupo=self._moldura_afinada_para_fechamento()
        addon.chapas.absorver_edicoes_de_malha()
        with patch.object(addon.chapas,'absorver_malha_editada',side_effect=AssertionError('Absorveu sem mudanca')), \
             patch.object(addon.frentes,'preparar',side_effect=AssertionError('Reextraiu sem mudanca')):
            for _ in range(3):addon.chapas.absorver_edicoes_de_malha()

    def test_undo_redo_do_fechamento_vertical_conserva_cotas_e_geometria(self):
        o,grupo=self._moldura_afinada_para_fechamento(guardar_undo=True);nome=o.name
        addon.chapas.absorver_edicoes_de_malha()
        bpy.ops.ed.undo_push(message='Fechamento vertical confirmado')
        o=grupo=None
        for _ in range(3):
            for operacao,largura in ((bpy.ops.ed.undo,649),(bpy.ops.ed.redo,64.9)):
                operacao();addon.eventos._fim_do_desfazer();bpy.context.view_layer.update()
                addon.chapas.absorver_edicoes_de_malha();addon.frentes.processar_pendentes()
                o=bpy.data.objects[nome]
                self.assertAlmostEqual(o.chapa_largura_mm,largura,places=3)
                self.assertAlmostEqual(o.chapa_espessura_mm,15,places=3)
                self._conferir_cotas_na_malha(o);o=None

    def test_seta_do_topo_editado_segue_a_aresta_clicada(self):
        o=self._chapa_com_pele_editada_por_tab();h=addon.hud
        geo=self._conferir_cotas_na_malha(o)
        contexto=SimpleNamespace(preferences=SimpleNamespace(system=SimpleNamespace(ui_scale=1)))
        projetar=lambda _c,p:Vector((p.x*1000,p.z*1000))
        for linha in geo['linhas']:
            if linha['tipo']!='aresta':continue
            with patch.object(h,'gpu'),patch.object(h,'batch_for_shader'), \
                 patch.object(h,'_projetar_hud',side_effect=projetar), \
                 patch.object(h,'_triangulos_seta_hud',return_value=[]) as seta:
                h._desenhar_seta_hud(contexto,dict(linha,lado='min'),geo)
                if (projetar(None,linha['pontos'][1])-projetar(None,linha['pontos'][0])).length<1:continue
                seta.assert_called_once()
                a,b=seta.call_args.args[:2]
                self.assertEqual(a,projetar(None,linha['pontos'][0]))
                self.assertEqual(b,projetar(None,linha['pontos'][1]))

    def test_contorno_com_peles_diferentes_e_cache_sem_extracao_no_redraw(self):
        o=self._chapa_com_pele_editada_por_tab()
        malha=o.data;uv=malha.uv_layers.new(name='UV preservada')
        material=bpy.data.materials.new('Material preservado');malha.materials.append(material)
        antes=([tuple(v.co) for v in malha.vertices], [tuple(f.vertices) for f in malha.polygons],
            [tuple(v.uv) for v in uv.data],o.matrix_world.copy())
        with patch.object(addon.chapas.bmesh,'new',side_effect=AssertionError('BMesh no redraw')), \
             patch.object(addon.formas,'forma_do_modulo',side_effect=AssertionError('Perfil no redraw')):
            for _ in range(3):geo=self._conferir_cotas_na_malha(o)
        self.assertIs(o.data,malha)
        self.assertEqual(antes,([tuple(v.co) for v in malha.vertices], [tuple(f.vertices) for f in malha.polygons],
            [tuple(v.uv) for v in uv.data],o.matrix_world))
        self.assertIs(malha.materials[0],material)
        campos=addon.hud.campos_cotas(o,'INDIVIDUAL',[o])
        self.assertEqual(len(campos),len({l['rotulo'] for l in geo['linhas']}))

    def test_segundo_tab_sem_mudar_envelope_atualiza_as_cotas_reais(self):
        o=self._chapa_com_pele_editada_por_tab()
        antes=addon.chapas._secao_espessura(o.data)
        self.assertIsNone(antes)
        digital=o.data[addon.chapas.CHAVE_ESPESSURA]['digital']
        medidas=(o.chapa_largura_mm,o.chapa_comprimento_mm,o.chapa_espessura_mm)
        bpy.ops.object.mode_set(mode='EDIT');addon.chapas.absorver_edicoes_de_malha()
        bm=bmesh.from_edit_mesh(o.data)
        max(bm.verts,key=lambda v:v.co.y).co.x+=.02
        bmesh.update_edit_mesh(o.data)
        bpy.ops.object.mode_set(mode='OBJECT');addon.chapas.absorver_edicoes_de_malha()
        self.assertEqual(medidas,(o.chapa_largura_mm,o.chapa_comprimento_mm,o.chapa_espessura_mm))
        self.assertNotEqual(digital,o.data[addon.chapas.CHAVE_ESPESSURA]['digital'])
        self._conferir_cotas_na_malha(o)

    def test_cota_real_de_pele_editada_preserva_mesh_e_undo_redo(self):
        o=self._chapa_com_pele_editada_por_tab();nome=o.name;malha=o.data
        geo=self._conferir_cotas_na_malha(o)
        alvo=next(l for l in geo['linhas'] if l['tipo']=='aresta'
            and abs((l['pontos'][1]-l['pontos'][0]).z)>.05
            and abs((l['pontos'][1]-l['pontos'][0]).x)>.5)
        chave=addon.hud.chave_cota(alvo);valor=addon.hud._valor_hud(alvo)
        antes=[o.matrix_world@v.co for v in malha.vertices]
        bpy.ops.ed.undo_push(message='Antes da cota de pele editada')
        addon.hud._aplicar_valor_hud(bpy.context,alvo,valor+20)
        self.assertIs(o.data,malha)
        self.assertAlmostEqual(addon.hud._valor_hud(addon.hud.alvo_cota(o,chave)),valor+20,places=3)
        self.assertEqual(sum((o.matrix_world@v.co-p).length>1e-6 for v,p in zip(malha.vertices,antes)),2)
        self._conferir_cotas_na_malha(o)
        bpy.ops.ed.undo_push(message='Depois da cota de pele editada')
        o=None;malha=None;alvo=None;geo=None
        for operacao,esperado in ((bpy.ops.ed.undo,valor),(bpy.ops.ed.redo,valor+20)):
            operacao();addon.eventos._fim_do_desfazer();bpy.context.view_layer.update()
            addon.frentes.processar_pendentes()
            o=bpy.data.objects[nome]
            self.assertAlmostEqual(addon.hud._valor_hud(addon.hud.alvo_cota(o,chave)),esperado,places=3)
            self.assertAlmostEqual(o.chapa_espessura_mm,18,places=3)
            self._conferir_cotas_na_malha(o);o=None

    def test_cota_de_pele_editada_isola_mesh_compartilhada_so_apos_validar(self):
        o=self._chapa_com_pele_editada_por_tab();malha=o.data
        copia=o.copy();bpy.context.scene.collection.objects.link(copia)
        antes=[tuple(v.co) for v in malha.vertices]
        with self.assertRaises(ValueError):addon.chapas.definir_aresta(o,999999,700)
        self.assertIs(o.data,malha)
        alvo=next(l for l in self._conferir_cotas_na_malha(o)['linhas'] if l['tipo']=='aresta')
        addon.hud._aplicar_valor_hud(bpy.context,alvo,addon.hud._valor_hud(alvo)+20)
        self.assertIsNot(o.data,malha);self.assertIs(copia.data,malha)
        self.assertEqual(antes,[tuple(v.co) for v in copia.data.vertices])
        self._conferir_cotas_na_malha(o)

    def test_chanfro_com_desvio_usa_as_duas_peles_reais(self):
        o=self._chapa_com_deslocamento()
        self._conferir_bordas_reais(o,5)

    def test_triangulacao_interna_nao_cria_cota_ou_diagonal(self):
        o=self._chapa_com_deslocamento()
        antes={chave:valor for nome,valor,chave in addon.hud.campos_cotas(o,'INDIVIDUAL',[o])}
        bm=bmesh.new()
        try:
            bm.from_mesh(o.data)
            bmesh.ops.triangulate(bm,faces=[f for f in bm.faces if len(f.verts)>4])
            bm.to_mesh(o.data)
        finally:bm.free()
        o.data.update();addon.frentes.preparar(o,forcar=True)
        self._conferir_bordas_reais(o,5)
        depois={chave:valor for nome,valor,chave in addon.hud.campos_cotas(o,'INDIVIDUAL',[o])}
        self.assertEqual(antes.keys(),depois.keys())
        for chave in antes:self.assertAlmostEqual(antes[chave],depois[chave],places=3)

    def test_contorno_3D_nao_consulta_mesh_ou_forma_no_redraw(self):
        from unittest.mock import patch
        o=self._chapa_com_deslocamento()
        with patch.object(addon.chapas,'_secao_espessura',side_effect=AssertionError('Mesh no redraw')),\
             patch.object(addon.formas,'forma_do_modulo',side_effect=AssertionError('Planta no redraw')):
            self._conferir_bordas_reais(o,5)

    def test_editar_aresta_3D_move_so_um_par_e_preserva_ID_E_UV(self):
        o=self._chapa_com_deslocamento();me=o.data
        uv=me.uv_layers.new(name='UV preservada')
        for i,v in enumerate(uv.data):v.uv=(i*.013,i*.017)
        uvs=[tuple(v.uv) for v in uv.data];faces=[tuple(f.vertices) for f in me.polygons]
        geo=self._conferir_bordas_reais(o,5)
        alvo=next(l for l in geo['linhas'] if l['tipo']=='aresta')
        antes=[o.matrix_world@v.co for v in me.vertices];novo=addon.hud._valor_hud(alvo)+25
        addon.hud._aplicar_valor_hud(bpy.context,dict(alvo,lado='min'),novo)
        self.assertAlmostEqual(addon.hud._valor_hud(alvo),novo,places=3)
        self.assertEqual(sum((o.matrix_world@v.co-p).length>1e-6 for v,p in zip(me.vertices,antes)),2)
        self.assertIs(o.data,me);self.assertEqual(faces,[tuple(f.vertices) for f in me.polygons])
        self.assertEqual(uvs,[tuple(v.uv) for v in me.uv_layers['UV preservada'].data])
        self.assertAlmostEqual(addon.chapas._secao_espessura(me)['espessura_mm'],18,places=3)
        self._conferir_bordas_reais(o,5)

    def test_angulo_3D_aceita_90_exatos_sem_mudar_E_ou_Mesh(self):
        o=self._chapa_com_deslocamento();me=o.data
        geo=self._conferir_bordas_reais(o,5)
        alvo=next(l for l in geo['linhas'] if l.get('angulo') and abs(addon.hud._valor_hud(l)-90)>1)
        antes=[o.matrix_world@v.co for v in me.vertices]
        addon.hud._aplicar_valor_hud(bpy.context,alvo,90)
        self.assertAlmostEqual(addon.hud._valor_hud(alvo),90,places=3)
        self.assertAlmostEqual(addon.chapas._secao_espessura(me)['espessura_mm'],18,places=3)
        self.assertEqual(sum((o.matrix_world@v.co-p).length>1e-6 for v,p in zip(me.vertices,antes)),2)
        self.assertIs(o.data,me);self._conferir_bordas_reais(o,5)

    def test_aresta_real_editada_pelo_menu_aceita_undo_redo(self):
        o=self._chapa_com_deslocamento();nome=o.name
        campo=next(c for c in addon.hud.campos_cotas(o,'INDIVIDUAL',[o]) if c[0]=='A1')
        addon.hud._selecionar_chapa_hud(bpy.context,o,individual=True)
        bpy.ops.ed.undo_push(message='Antes da aresta 3D')
        novo=campo[1]+25
        self.assertEqual(bpy.ops.object.cabinet_editar_medida_gaveta(
            'EXEC_DEFAULT',dono='cota',objeto=nome,propriedade=campo[2],valor=novo/1000),{'FINISHED'})
        bpy.ops.ed.undo_push(message='Depois da aresta 3D');o=None
        for funcao,valor in ((bpy.ops.ed.undo,campo[1]),(bpy.ops.ed.redo,novo)):
            funcao();bpy.context.view_layer.update();addon.eventos._fim_do_desfazer()
            o=bpy.data.objects[nome]
            self.assertAlmostEqual(addon.hud._valor_hud(addon.hud.alvo_cota(o,campo[2])),valor,places=3)
            self._conferir_bordas_reais(o,5);o=None

    def test_guia_de_deslocamento_fica_na_borda_baixa_sem_exceder_envelope(self):
        o=self._chapa_com_deslocamento()
        geo=self._conferir_bordas_reais(o,5)
        linha=next(l for l in geo['linhas'] if l['tipo']=='deslocamento')
        inv=o.matrix_world.inverted();a,b=[inv@p for p in linha['pontos']]
        self.assertAlmostEqual(a.x,b.x,places=6);self.assertAlmostEqual(a.y,b.y,places=6)
        baixo=min((o.matrix_world@v.co).z for v in o.data.vertices)
        self.assertAlmostEqual(min(p.z for p in linha['pontos']),baixo,places=6)
        lo=min(v.co.z for v in o.data.vertices);hi=max(v.co.z for v in o.data.vertices)
        for p in (a,b):self.assertTrue(lo-1e-6<=p.z<=hi+1e-6)

    def test_arco_3D_converte_mm_em_metros_e_fica_colado_na_quina(self):
        from unittest.mock import patch
        o=self._chapa_com_deslocamento()
        with patch.object(addon.hud,'_mm_por_pixel',return_value=1.):
            geo=addon.hud._geometria_do_item(o,'INDIVIDUAL',[o])
        escala=max(1.,bpy.context.preferences.system.ui_scale)
        for l in geo['linhas']:
            if not l.get('angulo'):continue
            for p in l['pontos']:
                self.assertAlmostEqual((p-l['vertice']).length,26*escala/1000,places=6)

    def test_cancelar_angulo_3D_restaura_contorno_cotas_e_mesma_Mesh(self):
        o=self._chapa_com_deslocamento();me=o.data
        alvo=next(l for l in addon.hud._geometria_do_item(o,'INDIVIDUAL',[o])['linhas'] if l.get('angulo'))
        backup=addon.hud._estado_arraste_hud(bpy.context,alvo)
        antes=[o.matrix_world@v.co for v in me.vertices]
        campos=addon.hud.campos_cotas(o,'INDIVIDUAL',[o])
        addon.hud._aplicar_valor_hud(bpy.context,alvo,75)
        addon.hud.restaurar_cota(bpy.context,backup,o.name)
        self.assertIs(o.data,me)
        self.assertLess(max((o.matrix_world@v.co-p).length for v,p in zip(me.vertices,antes)),1e-6)
        depois=addon.hud.campos_cotas(o,'INDIVIDUAL',[o])
        self.assertEqual([(c[0],c[2]) for c in campos],[(c[0],c[2]) for c in depois])
        for a,b in zip(campos,depois):self.assertAlmostEqual(a[1],b[1],places=3)
        self._conferir_bordas_reais(o,5)

    def _chapa_com_deslocamento(self):
        o=addon.chapas.nova_chapa('Chapa com deslocamento',400,300,18,(0,0,0),(0,90,0),bpy.context)
        bm=bmesh.new()
        try:
            bm.from_mesh(o.data)
            e=max((e for e in bm.edges if abs((e.verts[1].co-e.verts[0].co).normalized().z)>.99),key=lambda e:sum(v.co.x+v.co.y for v in e.verts))
            bmesh.ops.bevel(bm,geom=[e],offset=.08,segments=1,affect='EDGES')
            for v in bm.verts:
                if v.co.x>.1 and v.co.y>.05:v.co.z+=.12
            bm.to_mesh(o.data)
        finally:bm.free()
        o.data.update();addon.chapas.absorver_malha_editada(o);addon.frentes.preparar(o)
        return o

    def test_deslocamento_transversal_ganha_A6_com_E_independente(self):
        o=self._chapa_com_deslocamento()
        geo=addon.hud._geometria_do_item(o,'INDIVIDUAL',[o])
        campo=next(l for l in geo['linhas'] if l['tipo']=='deslocamento')
        self.assertEqual(campo['rotulo'],'A6')
        self.assertAlmostEqual(addon.hud._valor_hud(campo),120,places=3)
        self.assertAlmostEqual((campo['pontos'][1]-campo['pontos'][0]).length,.12,places=6)
        me=o.data;original=[v.co.copy() for v in me.vertices]
        secao=addon.chapas._secao_espessura(me)
        for valor in (240,60,120):
            addon.hud._aplicar_valor_hud(bpy.context,campo,valor)
            atual=next(l for l in addon.hud._geometria_do_item(o,'INDIVIDUAL',[o])['linhas'] if l['tipo']=='deslocamento')
            self.assertAlmostEqual(addon.hud._valor_hud(atual),valor,places=3)
            self.assertAlmostEqual(o.chapa_espessura_mm,18,places=3)
            self.assertAlmostEqual(addon.chapas._secao_espessura(me)['espessura_mm'],18,places=3)
        self.assertIs(o.data,me)
        self.assertLess(max((v.co-p).length for v,p in zip(me.vertices,original)),1e-6)
        addon.hud._aplicar_valor_hud(bpy.context,campo,10)
        self.assertFalse(any(l['tipo']=='deslocamento' for l in addon.hud._geometria_do_item(o,'INDIVIDUAL',[o])['linhas']))
        self.assertAlmostEqual(o.chapa_espessura_mm,18,places=3)

    def test_dois_chanfros_tem_cotas_independentes_no_menu(self):
        o=addon.chapas.nova_chapa('Dois chanfros',400,300,18,(0,0,0),(0,0,0),bpy.context)
        pol=[(-.2,-.07),(-.12,-.15),(.12,-.15),(.2,-.07),(.2,.15),(-.2,.15)]
        n=len(pol);vs=[(x,y,z) for z in (-.009,.009) for x,y in pol]
        fs=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
        o.data.clear_geometry();o.data.from_pydata(vs,[],fs);o.data.update()
        addon.frentes.preparar(o,forcar=True)
        geo=addon.hud._geometria_do_item(o,'INDIVIDUAL',[o])
        diagonais=[l for l in geo['linhas'] if l['tipo']=='forma' and l['face'][0]=='R' and not l.get('angulo')]
        self.assertEqual(len({tuple(l['face']) for l in diagonais}),2)
        self.assertEqual(len({l['rotulo'] for l in diagonais}),2)
        campos=addon.hud.campos_cotas(o,'INDIVIDUAL',[o])
        for l in diagonais:
            campo=next(c for c in campos if c[0]==l['rotulo'])
            self.assertEqual(campo[2],addon.hud.chave_cota(l))

    def test_todas_as_cotas_da_viewport_sao_editaveis_pelo_menu(self):
        o=self._chapa_com_deslocamento()
        campos=addon.hud.campos_cotas(o,'INDIVIDUAL',[o])
        self.assertEqual([c[0] for c in campos],['A1','A2','A3','A4','A5','A6','E'])
        backup=addon.hud._estado_arraste_hud(bpy.context,addon.hud.alvo_cota(o,campos[0][2]))
        for nome,valor,chave in campos:
            addon.hud.restaurar_cota(bpy.context,backup,o.name)
            novo=22 if nome=='E' else valor*1.05
            erro=addon.gaveta_eventos.aplicar_medida(bpy.context,'cota',o.name,chave,novo/1000)
            self.assertIsNone(erro,(nome,erro))
            self.assertAlmostEqual(addon.hud._valor_hud(addon.hud.alvo_cota(o,chave)),novo,delta=.02,msg=nome)
            self.assertAlmostEqual(o.chapa_espessura_mm,22 if nome=='E' else 18,places=3)

    def test_escape_do_campo_deslocamento_restaura_malha_e_cache(self):
        o=self._chapa_com_deslocamento();nome=o.name
        campo=next(c for c in addon.hud.campos_cotas(o,'INDIVIDUAL',[o]) if c[0]=='A6')
        alvo=addon.hud.alvo_cota(o,campo[2]);me=o.data
        backup=addon.hud._estado_arraste_hud(bpy.context,alvo)
        antes=[o.matrix_world@v.co for v in me.vertices]
        addon.hud._aplicar_valor_hud(bpy.context,alvo,10)
        operador=SimpleNamespace(_campo=dict(acao=('medida','cota',campo[2],'A6',120),
            objeto=nome,arrastou=True,backup_cota=backup))
        contexto=SimpleNamespace(area=SimpleNamespace(tag_redraw=lambda:None),scene=bpy.context.scene,view_layer=bpy.context.view_layer)
        resultado=addon.gaveta_eventos.OBJECT_OT_interagir_gaveta._modal_campo(operador,contexto,SimpleNamespace(type='ESC',value='PRESS'))
        self.assertEqual(resultado,{'CANCELLED'});self.assertIs(o.data,me)
        self.assertLess(max((p-o.matrix_world@v.co).length for p,v in zip(antes,me.vertices)),1e-6)
        self.assertAlmostEqual(addon.hud._valor_hud(addon.hud.alvo_cota(o,campo[2])),120,places=3)

    def test_realce_do_menu_acende_a_mesma_cota_na_viewport(self):
        o=self._chapa_com_deslocamento()
        addon.hud._selecionar_chapa_hud(bpy.context,o,individual=True)
        antigo=addon.hud._realce_medida[0]
        self.addCleanup(lambda:addon.hud._realce_medida.__setitem__(0,antigo))
        for nome,valor,chave in addon.hud.campos_cotas(o,'INDIVIDUAL',[o]):
            addon.hud._realce_medida[0]=nome
            alvo=addon.hud._realce_hud(_ContextoRegiao())
            self.assertEqual(addon.hud.chave_cota(alvo),chave)

    def test_edicao_de_A6_pelo_operador_aceita_undo_redo_nativo(self):
        o=self._chapa_com_deslocamento();nome=o.name
        campo=next(c for c in addon.hud.campos_cotas(o,'INDIVIDUAL',[o]) if c[0]=='A6')
        addon.hud._selecionar_chapa_hud(bpy.context,o,individual=True)
        bpy.ops.ed.undo_push(message='Antes da cota transversal')
        self.assertEqual(bpy.ops.object.cabinet_editar_medida_gaveta(
            'EXEC_DEFAULT',dono='cota',objeto=nome,propriedade=campo[2],valor=.18),{'FINISHED'})
        bpy.ops.ed.undo_push(message='Editou cota transversal');o=None
        for funcao,esperado in ((bpy.ops.ed.undo,120),(bpy.ops.ed.redo,180)):
            funcao();bpy.context.view_layer.update();addon.eventos._fim_do_desfazer()
            o=bpy.data.objects[nome]
            self.assertAlmostEqual(addon.hud._valor_hud(addon.hud.alvo_cota(o,campo[2])),esperado,places=3)
            self.assertAlmostEqual(o.chapa_espessura_mm,18,places=3)
            o=None

    def test_cotas_numeradas_preservam_alvos_e_edicao_dos_eixos(self):
        modulo=self.modulo()
        geo=addon.hud._geometria_hud(bpy.context)
        self.assertEqual({l['rotulo'] for l in geo['linhas']},{'A1','A2','A3'})
        for linha in geo['linhas']:
            self.assertEqual(linha['rotulo'],{'L':'A1','A':'A2','P':'A3'}[linha['letra']])
            self.assertEqual(addon.hud._propriedade_hud(linha),('conj_largura_mm','conj_profundidade_mm','conj_altura_mm')[linha['eixo']])

    def test_chapa_dobrada_oferece_E_nas_arestas_reais_sem_medir_no_redraw(self):
        from unittest.mock import patch
        o=addon.chapas.nova_chapa('Chapa dobrada HUD',400,300,18,(0,0,0),(0,90,0),bpy.context)
        bm=bmesh.new()
        try:
            bm.from_mesh(o.data)
            e=max((e for e in bm.edges if abs((e.verts[1].co-e.verts[0].co).normalized().z)>.99),key=lambda e:sum(v.co.x+v.co.y for v in e.verts))
            bmesh.ops.bevel(bm,geom=[e],offset=.08,segments=1,affect='EDGES')
            for v in bm.verts:
                if v.co.x>.1 and v.co.y>.05:v.co.z+=.12
            bm.to_mesh(o.data)
        finally:bm.free()
        o.data.update();addon.chapas.absorver_malha_editada(o);addon.frentes.preparar(o)
        addon.formas.forma_do_modulo(o)
        with patch.object(addon.chapas,'_secao_espessura',side_effect=AssertionError('Mediu Mesh no redraw')):
            geo=addon.hud._geometria_do_item(o,'INDIVIDUAL',[o])
        linhas=[l for l in geo['linhas'] if l.get('letra')]
        numeros={l['rotulo'] for l in linhas if l['letra']!='E'}
        self.assertEqual(numeros,{'A%d'%i for i in range(1,len(numeros)+1)})
        self.assertFalse(any(l['rotulo'] in ('L','A','P','R','L1') for l in linhas))
        es=[l for l in linhas if l['rotulo']=='E'];self.assertEqual(len(es),5)
        reais=[o.matrix_world@v.co for v in o.data.vertices]
        for l in es:
            self.assertAlmostEqual((l['pontos'][1]-l['pontos'][0]).length,.018,places=6)
            self.assertAlmostEqual(addon.hud._valor_hud(l),18,places=4)
            for p in l['pontos']:self.assertLess(min((p-v).length for v in reais),1e-6)

    def test_correntes_proximas_da_mesma_junta_tem_um_so_controle(self):
        a=addon.chapas.nova_chapa('A',600,400,18,(0,0,0),(0,0,0),bpy.context)
        b=addon.chapas.nova_chapa('B',600,400,18,(0,0,0),(0,0,0),bpy.context)
        itens=[dict(a=a,b=b,pontos=[Vector((0,0,z)),Vector((.1,0,z))],indice=i)
               for i,z in enumerate((0,.018,.1))]
        inversa=dict(a=b,b=a,pontos=list(reversed(itens[0]['pontos'])),indice=9)
        resultado=addon.solda._correntes_sem_repeticao(itens+[inversa])
        self.assertEqual([v['indice'] for v in resultado],[0])
        self.assertEqual(len(itens),3)

    def test_otimizacao_de_adjacencia_tira_quinas_falsas_e_preserva_ancoras_manuais(self):
        c=addon.modulos.criar_armario(bpy.context,'Conexoes',600,700,550,fundo=False)
        cs=addon.modulos._chapas_do_conjunto(c)
        base=next(o for o in cs if o.name.startswith('Base'))
        lateral=min((o for o in cs if o.name.startswith('Lateral')),key=lambda o:o.matrix_world.translation.x)
        addon.chapas._gravar_ligacao(base,'y','neg',lateral,0,0)
        self.assertIsNone(addon.chapas._melhor_vizinho(base,'y','neg',[lateral]))
        addon.solda._gravar_ancoras(base,'x_neg',[('---','+++')])
        antes=[tuple(v.co) for v in base.data.vertices]
        addon.chapas.otimizar_adjacencia(cs)
        self.assertIsNone(addon.solda._vizinho_da_ponta(base,'y_neg'))
        self.assertNotIn('adj_y_neg_uid',base)
        self.assertEqual(addon.solda._ancoras_gravadas(base,'x_neg'),[('---','+++')])
        self.assertEqual([tuple(v.co) for v in base.data.vertices],antes)
        self.assertFalse(addon.chapas.otimizar_adjacencia(cs))

    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        addon.hud._clique_chapa_hud.clear()
        addon.hud._hover_hud.clear()

    def modulo(self):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar()
        modulo = bpy.context.object
        bpy.context.view_layer.update()
        return modulo

    def test_delete_com_referencia_id_nao_poem_orfao_na_selecao_ou_tab(self):
        # Regressao (era BUG, corrigido na 369): children_recursive inclui ID sem cena.
        modulo = self.modulo()
        peca, outra = addon.modulos._chapas_do_conjunto(modulo)[:2]
        nome = peca.name
        referencia = bpy.data.objects.new('Referencia preservada', None)
        bpy.context.scene.collection.objects.link(referencia)
        referencia['peca'] = peca
        bpy.ops.object.select_all(action='DESELECT')
        peca.select_set(True)
        bpy.context.view_layer.objects.active = peca
        bpy.ops.object.delete()
        self.assertIn(nome, bpy.data.objects)
        self.assertNotIn(nome, bpy.context.view_layer.objects)
        self.assertIn(peca, modulo.children_recursive)
        addon.hud._selecionar_chapa_hud(bpy.context, outra)
        self.assertIs(bpy.context.object, modulo)
        self.assertTrue(outra.select_get())
        self.assertNotIn(peca, addon.hud._familia_do_clique(outra))
        self.assertNotIn(peca, addon.selecao.malhas_para_editar(bpy.context))
        addon.hud._somar_peca(bpy.context, outra, duplo=True)
        self.assertIs(bpy.context.object, outra)
        self.assertIs(referencia['peca'], bpy.data.objects[nome])

    def test_grupo_nao_seleciona_colecao_excluida_da_camada(self):
        modulo = self.modulo()
        peca, outra = addon.modulos._chapas_do_conjunto(modulo)[:2]
        colecao = bpy.data.collections.new('Peca em camada excluida')
        bpy.context.scene.collection.children.link(colecao)
        self.addCleanup(bpy.data.collections.remove, colecao)
        colecao.objects.link(peca)
        for c in list(peca.users_collection):
            if c != colecao:
                c.objects.unlink(peca)
        bpy.context.view_layer.layer_collection.children[colecao.name].exclude = True
        bpy.context.view_layer.update()
        self.assertIn(peca.name, bpy.context.scene.objects)
        self.assertNotIn(peca.name, bpy.context.view_layer.objects)
        addon.hud._selecionar_chapa_hud(bpy.context, outra)
        self.assertIs(bpy.context.object, modulo)
        self.assertNotIn(peca, addon.hud._familia_do_clique(outra))
        self.assertTrue(bpy.context.view_layer.layer_collection.children[colecao.name].exclude)

    def test_pai_fora_da_camada_conserva_a_peca_clicada_como_ativa(self):
        modulo = self.modulo()
        peca = addon.modulos._chapas_do_conjunto(modulo)[0]
        for c in list(modulo.users_collection):
            c.objects.unlink(modulo)
        bpy.context.view_layer.update()
        addon.hud._selecionar_chapa_hud(bpy.context, peca)
        self.assertIs(bpy.context.object, peca)
        self.assertTrue(peca.select_get())
        self.assertNotIn(modulo.name, bpy.context.view_layer.objects)

    def _volume_contexto(self):
        contexto = _ContextoRegiao()
        contexto.area = SimpleNamespace(as_pointer=lambda: 987654, tag_redraw=lambda: None)
        contexto.space_data = SimpleNamespace(overlay=SimpleNamespace(show_cursor=True))
        return contexto

    def _volume_preparar(self, obj, modo, eixo, lado):
        obj.select_set(True)
        geo = addon.hud._geometria_do_item(obj, modo, []) if modo != 'GRUPO' else (
            addon.hud._geometria_do_item(obj, modo, addon.modulos._chapas_do_conjunto(obj)))
        controle = next(c for c in addon.hud_volume.controles(geo)
                        if c['eixo'] == eixo and c['lado'] == lado)
        contexto = self._volume_contexto()
        backup = addon.hud._estado_arraste_hud(contexto, controle)
        props = addon.hud_volume.preparar(contexto, controle, backup)
        return contexto, controle, props

    def test_volume_seis_centros_reais_e_hit_test_em_caixa_girada(self):
        modulo = self.modulo()
        modulo.rotation_euler = (.1, .2, .7)
        bpy.context.view_layer.update()
        geo = addon.hud._geometria_do_item(modulo, 'GRUPO',
                                         addon.modulos._chapas_do_conjunto(modulo))
        controles = addon.hud_volume.controles(geo)
        self.assertEqual(len(controles), 6)
        for controle in controles:
            eixo = controle['eixo']
            face = 1 if controle['lado'] == 'min' else 0
            esperado = sum((p for i, p in enumerate(geo['cantos'])
                           if bool(i & (1 << eixo)) == bool(face)), Vector()) / 4
            self.assertLess((controle['pontos'][1] - esperado).length, 1e-7)
        # Projecao obliqua separa os seis centros, incluindo frente/costas.
        projetar = lambda p: Vector((p.x * 500 + p.y * 180, p.z * 500 + p.y * 90))
        for c in controles:
            alvo = addon.hud._acertar_linhas_hud(geo, projetar(c['pontos'][1]), projetar)
            self.assertTrue(alvo.get('controle_face'))
            self.assertEqual((alvo['eixo'], alvo['lado']), (c['eixo'], c['lado']))

    def test_opcoes_independentes_escondem_bolinhas_e_guias_sem_alvo_fantasma(self):
        from unittest.mock import patch
        modulo=self.modulo()
        geo=addon.hud._geometria_do_item(modulo,'GRUPO',addon.modulos._chapas_do_conjunto(modulo))
        originais={n:addon.opcoes._opcao(n) for n in ('hud_pontos_apoio','hud_setas_quinas')}
        ctx=_ContextoRegiao()
        realce=addon.hud._realce_medida[0]
        addon.hud._realce_medida[0]=None
        try:
            addon.opcoes._definir_opcao('hud_pontos_apoio',True)
            controle=addon.hud_volume.controles(geo)[0]
            addon.opcoes._definir_opcao('hud_pontos_apoio',False)
            self.assertFalse(addon.hud_volume.controles(geo))
            addon.hud._hover_hud[4242]=controle
            self.assertIsNone(addon.hud._realce_hud(ctx))
            addon.opcoes._definir_opcao('hud_pontos_apoio',True)
            self.assertIs(addon.hud._realce_hud(ctx),controle)
            addon.opcoes._definir_opcao('hud_setas_quinas',False)
            self.assertEqual(len(addon.hud_volume.controles(geo)),6)
            addon.hud._hover_hud[4242]=dict(geo['linhas'][0],lado='min')
            self.assertIsNone(addon.hud._realce_hud(ctx))
            with patch.object(addon.hud,'_projetar_hud',side_effect=AssertionError('Desenhou guia desligada')):
                addon.hud._desenhar_seta_hud(ctx,{},geo)
            addon.opcoes._definir_opcao('hud_setas_quinas',True)
            self.assertIsNotNone(addon.hud._realce_hud(ctx))
        finally:
            addon.hud._hover_hud.pop(4242,None)
            addon.hud._realce_medida[0]=realce
            for n,v in originais.items():addon.opcoes._definir_opcao(n,v)

    def test_menu_tem_controles_ligado_desligado_para_bolinhas_e_guias(self):
        for nome in ('hud_pontos_apoio','hud_setas_quinas'):
            self.assertEqual(addon.gaveta.SUSPENSOS_OPCOES[nome],((True,'Ligado'),(False,'Desligado')))
            self.assertIn(nome,[linha[2] for linha in addon.gaveta.LINHAS_OPCOES])
            self.assertTrue(addon.opcoes.CabinetCreatorPreferences.bl_rna.properties[nome].default)

    def test_volume_translate_nativo_vertice_base_b_e_estado_sem_ids(self):
        modulo = self.modulo()
        cursor = tuple(bpy.context.scene.cursor.location)
        ctx, c, props = self._volume_preparar(modulo, 'GRUPO', 0, 'min')
        try:
            self.assertTrue(props['cursor_transform'])
            self.assertFalse(props['snap'])
            self.assertEqual(props['snap_elements'], {'VERTEX'})
            self.assertTrue(props['use_snap_selectable'])
            self.assertEqual(props['constraint_axis'], (True, False, False))
            eixo = (c['pontos'][1] - c['pontos'][0]).normalized()
            self.assertGreater(Vector(props['orient_matrix'][0]).dot(eixo), .99999)
            self.assertFalse(addon._segura_dado(addon.hud_volume._estado[0]))
            self.assertIn('TRANSFORM_OT_translate',
                          bpy.ops.object.cabinet_transformar_volume.get_rna_type().properties.keys())
        finally:
            addon.hud_volume.terminar(ctx, cancelar=True)
        self.assertEqual(tuple(bpy.context.scene.cursor.location), cursor)
        self.assertFalse(modulo.hide_select)
        self.assertIsNone(addon.hud_volume._estado[0])
        chapa = addon.modulos._chapas_do_conjunto(modulo)[0]
        addon.hud._selecionar_chapa_hud(bpy.context, chapa, individual=True)
        alvo = dict(tipo='medida', objeto=chapa, modo='INDIVIDUAL', eixo=0,
                    lado='min', pontos=[chapa.matrix_world @ Vector(p)
                                       for p in [(-.1,0,0),(.1,0,0)]])
        backup = addon.hud._estado_arraste_hud(ctx, alvo)
        addon.hud_volume.preparar(ctx, alvo, backup)
        try:
            self.assertFalse(chapa.select_get())
            self.assertEqual(addon.hud._itens_hud(ctx), [(chapa, 'INDIVIDUAL', [chapa])])
        finally:
            addon.hud_volume.terminar(ctx, cancelar=True)
        self.assertTrue(chapa.select_get())

    def test_volume_base_snap_apos_arraste_preserva_geometria_atual_em_todos_os_eixos(self):
        # Regressao v290: a base pertence a' posicao em que B foi apertado.
        # O cursor nativo volta ao inicio, mas a madeira nao pode voltar.
        modulo=self.modulo()
        originais={o.name:[o.matrix_world@v.co for v in o.data.vertices]
                   for o in modulo.children_recursive if o.type=='MESH'}
        for eixo in range(3):
            for lado in ('min','max'):
                with self.subTest(eixo=eixo,lado=lado):
                    ctx,c,props=self._volume_preparar(modulo,'GRUPO',eixo,lado)
                    estado=addon.hud_volume._estado[0]
                    inicio=Vector(estado['inicio']);direcao=Vector(estado['eixo'])
                    original=estado['valor']
                    try:
                        bpy.context.scene.cursor.location=inicio+direcao*.04
                        addon.hud_volume.atualizar(ctx)
                        self.assertAlmostEqual(addon.hud._valor_hud(c,ctx),original+40,delta=.01)
                        atuais={o.name:[o.matrix_world@v.co for v in o.data.vertices]
                                for o in modulo.children_recursive if o.type=='MESH'}
                        cursor=bpy.context.scene.cursor.location.copy()
                        addon.hud_volume.preparar_base_snap(ctx)
                        self.assertLess((bpy.context.scene.cursor.location-cursor).length,1e-7)
                        for nome,pontos in atuais.items():
                            obj=bpy.data.objects[nome]
                            for v,p in zip(obj.data.vertices,pontos):
                                self.assertLess((obj.matrix_world@v.co-p).length,1e-6)
                        # O Blender restaura o cursor e aplica destino-base.
                        # Aqui o deslocamento e' conhecido; o translate real
                        # verifica a referencia sem simular picking por Python.
                        bpy.context.scene.cursor.location=inicio
                        addon.hud_volume.atualizar(ctx)
                        self.assertAlmostEqual(addon.hud._valor_hud(c,ctx),original+40,delta=.01)
                        base=max((p for pontos in atuais.values() for p in pontos),key=lambda p:p.dot(direcao))
                        destino=base+direcao*.075
                        props.update(snap=False,value=((destino-base).dot(direcao),0,0))
                        self.assertEqual(bpy.ops.transform.translate('EXEC_DEFAULT',**props),{'FINISHED'})
                        addon.hud_volume.atualizar(ctx)
                        self.assertAlmostEqual(addon.hud._valor_hud(c,ctx),original+115,delta=.02)
                        ponta=max((o.matrix_world@v.co for o in modulo.children_recursive
                                   if o.type=='MESH' for v in o.data.vertices),key=lambda p:p.dot(direcao))
                        self.assertAlmostEqual(ponta.dot(direcao),destino.dot(direcao),delta=.00002)
                    finally:
                        addon.hud_volume.terminar(ctx,cancelar=True)
                    for nome,pontos in originais.items():
                        obj=bpy.data.objects[nome]
                        for v,p in zip(obj.data.vertices,pontos):
                            self.assertLess((obj.matrix_world@v.co-p).length,1e-6)

    def test_volume_observador_repassa_base_nativa_e_termina_sem_consumir_undo(self):
        from unittest.mock import Mock,patch
        modulo=self.modulo()
        ctx,c,_=self._volume_preparar(modulo,'GRUPO',0,'min')
        obs=addon.hud_volume.OBJECT_OT_observar_volume
        operador=SimpleNamespace(_sessao=id(addon.hud_volume._estado[0]))
        evento=SimpleNamespace(type='B',value='PRESS')
        try:
            bpy.context.scene.cursor.location+=Vector((.03,0,0))
            addon.hud_volume.atualizar(ctx)
            with patch.object(addon.hud_volume,'_evento_base_snap',return_value=True):
                self.assertEqual(obs.modal(operador,ctx,evento),{'PASS_THROUGH'})
            self.assertAlmostEqual(modulo.conj_largura_mm,630,delta=.01)
            addon.hud_volume.terminar(ctx,cancelar=True)
            with patch.object(addon.hud_volume,'_remover_observador') as limpar:
                self.assertEqual(obs.modal(operador,ctx,evento),{'FINISHED','PASS_THROUGH'})
                limpar.assert_called_once()
            # Usa o matcher NATIVO, inclusive com o atalho remapeado.
            matcher=Mock(return_value=object())
            mapa=SimpleNamespace(keymap_items=SimpleNamespace(match_event=matcher))
            with patch.object(addon.hud_volume,'_mapa_eventos_snap',return_value=mapa):
                self.assertTrue(addon.hud_volume._evento_base_snap(ctx,evento))
            matcher.assert_called_once_with(evento)
            matcher.return_value=None
            with patch.object(addon.hud_volume,'_mapa_eventos_snap',return_value=mapa):
                self.assertFalse(addon.hud_volume._evento_base_snap(ctx,evento))
        finally:
            addon.hud_volume.terminar(ctx,cancelar=True)

    def test_volume_observador_abre_depois_do_translate_e_libera_timer(self):
        from unittest.mock import Mock,patch
        modulo=self.modulo()
        ctx,c,_=self._volume_preparar(modulo,'GRUPO',0,'min')
        backup=addon.hud_volume._recuperar(addon.hud_volume._estado[0]['backup'])
        addon.hud_volume.terminar(ctx,cancelar=True)
        ordem=[]
        def traduzir(*a,**k):ordem.append('translate');return {'RUNNING_MODAL'}
        def observar(*a,**k):ordem.append('observador');return {'RUNNING_MODAL'}
        try:
            api=SimpleNamespace(ops=SimpleNamespace(object=SimpleNamespace(
                cabinet_transformar_volume=traduzir,cabinet_observar_volume=observar)),
                app=SimpleNamespace(timers=SimpleNamespace(register=Mock())),
                types=bpy.types,data=bpy.data,context=bpy.context)
            with patch.object(addon.hud_volume,'bpy',api):
                self.assertTrue(addon.hud_volume.iniciar(ctx,c,backup))
            self.assertEqual(ordem,['translate','observador'])
            timer=object();adicionar=Mock(return_value=timer)
            wm=SimpleNamespace(event_timer_add=adicionar,modal_handler_add=Mock())
            contexto=SimpleNamespace(window_manager=wm,window=None)
            op=SimpleNamespace()
            classe=addon.hud_volume.OBJECT_OT_observar_volume
            with patch.object(addon.hud_volume,'_remover_observador'):
                self.assertEqual(classe.invoke(op,contexto,None),{'RUNNING_MODAL'})
            self.assertIs(addon.hud_volume._timer_observador[0],timer)
            wm.modal_handler_add.assert_called_once_with(op)
            # O operador guarda so' o identificador da sessao, nunca IDs.
            self.assertFalse(addon._segura_dado(op.__dict__))
            remover=Mock()
            api=SimpleNamespace(context=SimpleNamespace(window_manager=SimpleNamespace(
                event_timer_remove=remover,keyconfigs=SimpleNamespace(addon=None))))
            with patch.object(addon.hud_volume,'bpy',api):
                addon.hud_volume._remover_observador()
                remover.assert_called_once_with(timer)
            self.assertIsNone(addon.hud_volume._timer_observador[0])
        finally:
            addon.hud_volume._timer_observador[0]=None
            addon.hud_volume.terminar(ctx,cancelar=True)

    def test_volume_mapa_snap_nativo_tem_operador_valido_e_copia_atalhos_modais(self):
        v=addon.hud_volume
        origem=bpy.context.window_manager.keyconfigs.user.keymaps['Transform Modal Map']
        itens=[i for i in origem.keymap_items if i.active and i.propvalue in {
            'EDIT_SNAP_SOURCE_ON','EDIT_SNAP_SOURCE_OFF'}]
        criados=[]
        if not itens:
            # --background cria o mapa modal nativo, mas nao carrega o
            # preset Python dos atalhos. Completar somente esta fixture.
            criados=[origem.keymap_items.new_modal(p,'B','PRESS') for p in
                     ('EDIT_SNAP_SOURCE_ON','EDIT_SNAP_SOURCE_OFF')]
            itens=criados
        self.assertTrue(itens)
        self.assertTrue(all(i.idname=='' for i in itens))
        antes=[tuple(getattr(i,p,None) for p in v._CAMPOS_EVENTO) for i in itens]
        tipo=itens[0].type
        try:
            mapa=v._mapa_eventos_snap(bpy.context)
            self.assertFalse(mapa.is_modal)
            self.assertEqual(len(mapa.keymap_items),len(itens))
            self.assertTrue(all(i.idname==v.OBJECT_OT_observar_volume.bl_idname for i in mapa.keymap_items))
            self.assertEqual([tuple(getattr(i,p,None) for p in v._CAMPOS_EVENTO)
                              for i in mapa.keymap_items],antes)
            self.assertFalse(addon._segura_dado(v._assinatura_mapa_snap[0]))
            # Remapeamento durante a sessao atualiza o espelho sem editar
            # o mapa original. A fixture e' o factory-startup do harness.
            itens[0].type='V' if tipo!='V' else 'B'
            atualizado=v._mapa_eventos_snap(bpy.context)
            self.assertEqual(atualizado.keymap_items[0].type,itens[0].type)
        finally:
            itens[0].type=tipo
            v._remover_observador()
            for item in criados:origem.keymap_items.remove(item)
        self.assertIsNone(bpy.context.window_manager.keyconfigs.addon.keymaps.get(v.NOME_MAPA_SNAP))
        self.assertIsNone(v._assinatura_mapa_snap[0])

    def test_volume_gavetas_em_corpo_dobrado_e_girado_preservam_previa_ao_ancorar(self):
        g=addon.gavetas
        modulo=self.modulo()
        grupo=g.criar_gavetas(bpy.context,modulo,(18,18,18,18,0),dict(quantidade=4,profundidade_mm=280))
        largura=g.medidas(grupo)[0]
        modulo.conj_largura_mm*=2
        self.assertAlmostEqual(g.medidas(grupo)[0],largura,delta=.01)
        modulo.rotation_euler.z=math.pi/2
        bpy.context.view_layer.update()
        ctx,c,props=self._volume_preparar(grupo,'GAVETAS',0,'min')
        s=addon.hud_volume._estado[0]
        inicio=Vector(s['inicio']);eixo=Vector(s['eixo'])
        try:
            self.assertGreater(abs(eixo.y),.999)
            bpy.context.scene.cursor.location=inicio+eixo*.04
            addon.hud_volume.atualizar(ctx)
            self.assertAlmostEqual(g.medidas(grupo)[0],largura+40,delta=.02)
            addon.hud_volume.preparar_base_snap(ctx)
            bpy.context.scene.cursor.location=inicio
            addon.hud_volume.atualizar(ctx)
            self.assertAlmostEqual(g.medidas(grupo)[0],largura+40,delta=.02)
            props.update(snap=False,value=(.075,0,0))
            bpy.ops.transform.translate('EXEC_DEFAULT',**props)
            addon.hud_volume.atualizar(ctx)
            self.assertAlmostEqual(g.medidas(grupo)[0],largura+115,delta=.02)
            self.assertNotIn('erro',s)
        finally:
            addon.hud_volume.terminar(ctx,cancelar=True)
        self.assertAlmostEqual(g.medidas(grupo)[0],largura,delta=.01)

    def test_volume_base_snap_repetida_acumula_so_arrastes_e_esc_restaura_origem(self):
        modulo=self.modulo()
        ctx,c,_=self._volume_preparar(modulo,'GRUPO',0,'min')
        s=addon.hud_volume._estado[0]
        inicio=Vector(s['inicio']);eixo=Vector(s['eixo']);original=s['valor']
        antes={o.name:[tuple(v.co) for v in o.data.vertices]
               for o in modulo.children_recursive if o.type=='MESH'}
        try:
            for delta,total in ((.04,40),(.02,60),(-.01,50)):
                # B deve absorver o cursor mesmo antes do tique de previa.
                bpy.context.scene.cursor.location=inicio+eixo*delta
                addon.hud_volume.preparar_base_snap(ctx)
                self.assertAlmostEqual(addon.hud._valor_hud(c,ctx),original+total,delta=.02)
                bpy.context.scene.cursor.location=inicio
                addon.hud_volume.atualizar(ctx)
                self.assertAlmostEqual(addon.hud._valor_hud(c,ctx),original+total,delta=.02)
                # O segundo B confirma a mesma base, sem duplicar o gap.
                addon.hud_volume.preparar_base_snap(ctx)
                addon.hud_volume.atualizar(ctx)
                self.assertAlmostEqual(addon.hud._valor_hud(c,ctx),original+total,delta=.02)
            self.assertFalse(addon._segura_dado(s))
        finally:
            addon.hud_volume.terminar(ctx,cancelar=True)
        self.assertAlmostEqual(modulo.conj_largura_mm,original,delta=.01)
        for nome,pontos in antes.items():
            self.assertEqual([tuple(v.co) for v in bpy.data.objects[nome].data.vertices],pontos)

    def test_volume_previa_reparte_da_origem_e_esc_restaura_malha(self):
        modulo = self.modulo()
        antes = {o.name: (o.matrix_world.copy(), [tuple(v.co) for v in o.data.vertices])
                 for o in modulo.children_recursive if o.type == 'MESH'}
        original = modulo.conj_largura_mm
        ctx, c, _ = self._volume_preparar(modulo, 'GRUPO', 0, 'max')
        inicio = Vector(addon.hud_volume._estado[0]['inicio'])
        eixo = Vector(addon.hud_volume._estado[0]['eixo'])
        try:
            for delta in (.04, .01, .04):
                bpy.context.scene.cursor.location = inicio + eixo * delta
                addon.hud_volume.atualizar(ctx)
                self.assertAlmostEqual(modulo.conj_largura_mm, original + delta*1000, places=2)
            self.assertTrue(addon.hud._edicao_hud[0]['nativo'])
        finally:
            addon.hud_volume.terminar(ctx, cancelar=True)
        self.assertAlmostEqual(modulo.conj_largura_mm, original, places=3)
        for nome, (m, vertices) in antes.items():
            obj = bpy.data.objects[nome]
            for a, b in zip(m, obj.matrix_world):
                self.assertLess((a-b).length, 1e-6)
            self.assertEqual(vertices, [tuple(v.co) for v in obj.data.vertices])

    def test_volume_prateleiras_corrige_topo_e_base_sem_mover_corpo(self):
        modulo = self.modulo()
        p = addon.prateleiras
        grupo = p.criar_prateleiras(bpy.context, modulo, (18,18,0,0,0),
                                    dict(quantidade=2, profundidade_mm=300))
        corpo = {o.name: o.matrix_world.copy() for o in addon.modulos._chapas_do_conjunto(modulo)}
        altura = p.medidas(grupo)[1]
        for lado, deslocamento in [('min', -.018), ('max', -.2)]:
            ctx, c, _ = self._volume_preparar(grupo, 'PRATELEIRAS', 2, lado)
            s = addon.hud_volume._estado[0]
            bpy.context.scene.cursor.location = Vector(s['inicio']) + Vector(s['eixo']) * deslocamento
            # Confirmacao da macro aplica o ultimo movimento mesmo sem tique de timer.
            self.assertEqual(bpy.ops.object.cabinet_confirmar_volume(), {'FINISHED'})
        self.assertAlmostEqual(p.medidas(grupo)[1], altura - 218, places=2)
        self.assertAlmostEqual(grupo[p.CHAVE_MARGENS][2], 200, places=2)
        self.assertAlmostEqual(grupo[p.CHAVE_MARGENS][3], 18, places=2)
        for nome, matriz in corpo.items():
            self.assertEqual(bpy.data.objects[nome].matrix_world, matriz)

    def test_volume_prateleiras_frente_movel_preserva_costas(self):
        modulo = self.modulo()
        p = addon.prateleiras
        grupo = p.criar_prateleiras(bpy.context, modulo, (18,18,18,18,20),
                                    dict(quantidade=2, profundidade_mm=300))
        ctx, c, _ = self._volume_preparar(grupo, 'PRATELEIRAS', 1, 'max')
        costas = c['pontos'][0].copy()
        try:
            s = addon.hud_volume._estado[0]
            bpy.context.scene.cursor.location = Vector(s['inicio']) + Vector(s['eixo']) * -.05
            addon.hud_volume.atualizar(ctx)
            self.assertAlmostEqual(p.medidas(grupo)[2], 250, places=2)
            geo = addon.hud._geometria_do_item(grupo, 'PRATELEIRAS', [])
            atual = next(c for c in addon.hud_volume.controles(geo)
                         if c['eixo'] == 1 and c['lado'] == 'max')
            self.assertLess((atual['pontos'][0] - costas).length, 1e-6)
        finally:
            addon.hud_volume.terminar(ctx, cancelar=True)

    def test_volume_nao_intercepta_angulo_e_cota_de_unidade(self):
        modulo = self.modulo()
        for alvo in [dict(tipo='angulo_aresta', lado='min'),
                     dict(tipo='gavetas', face=('A', 0), lado='min'),
                     dict(tipo='prateleiras', face=('V', 0), lado='min')]:
            self.assertFalse(addon.hud_volume.elegivel(alvo))
        chapa = addon.modulos._chapas_do_conjunto(modulo)[0]
        geo = addon.hud._geometria_do_item(chapa, 'INDIVIDUAL', [chapa])
        self.assertFalse(addon.hud_volume.controles(geo))

    def test_volume_macro_executa_translate_real_e_confirma(self):
        modulo = self.modulo()
        largura = modulo.conj_largura_mm
        ctx, c, props = self._volume_preparar(modulo, 'GRUPO', 0, 'min')
        try:
            eixo = Vector(addon.hud_volume._estado[0]['eixo'])
            props['value'] = tuple(eixo * .05)
            props['snap'] = False
            self.assertEqual(bpy.ops.object.cabinet_transformar_volume(
                'EXEC_DEFAULT', TRANSFORM_OT_translate=props), {'FINISHED'})
            self.assertAlmostEqual(modulo.conj_largura_mm, largura + 50, places=2)
            self.assertIsNone(addon.hud_volume._estado[0])
        finally:
            addon.hud_volume.terminar(ctx, cancelar=True)

    def test_volume_gavetas_e_divisorias_previa_repetida_com_filhos_refeitos(self):
        for dono, modo, criar in [
                (addon.gavetas, 'GAVETAS', addon.gavetas.criar_gavetas),
                (addon.divisorias, 'DIVISORIAS', addon.divisorias.criar_divisorias)]:
            with self.subTest(modo=modo):
                modulo = self.modulo()
                grupo = criar(bpy.context, modulo, (18,18,18,18,20),
                              dict(quantidade=1, profundidade_mm=400))
                ctx, c, _ = self._volume_preparar(grupo, modo, 1, 'max')
                costas = c['pontos'][0].copy()
                inicio = Vector(addon.hud_volume._estado[0]['inicio'])
                eixo = Vector(addon.hud_volume._estado[0]['eixo'])
                try:
                    for delta in (-.03, -.05, -.02):
                        bpy.context.scene.cursor.location = inicio + eixo * delta
                        addon.hud_volume.atualizar(ctx)
                        self.assertAlmostEqual(dono.medidas(grupo)[2], 400+delta*1000, places=2)
                        geo = addon.hud._geometria_do_item(grupo, modo, [])
                        atual = next(c for c in addon.hud_volume.controles(geo)
                                     if c['eixo']==1 and c['lado']=='max')
                        self.assertLess((atual['pontos'][0]-costas).length, 1e-6)
                finally:
                    addon.hud_volume.terminar(ctx, cancelar=True)
                self.assertAlmostEqual(dono.medidas(grupo)[2], 400, places=2)

    def test_volume_medida_invalida_nao_abandona_translate_e_pode_recuperar(self):
        modulo = self.modulo()
        grupo = addon.gavetas.criar_gavetas(bpy.context, modulo, (18,18,18,18,0),
                                          dict(quantidade=1, profundidade_mm=400))
        ctx, c, _ = self._volume_preparar(grupo, 'GAVETAS', 1, 'min')
        s = addon.hud_volume._estado[0]
        inicio, eixo = Vector(s['inicio']), Vector(s['eixo'])
        try:
            bpy.context.scene.cursor.location = inicio - eixo * .3
            addon.hud_volume.atualizar(ctx)
            self.assertIs(addon.hud_volume._estado[0], s)
            self.assertTrue(s.get('erro'))
            self.assertAlmostEqual(addon.gavetas.medidas(grupo)[2], 400, places=2)
            bpy.context.scene.cursor.location = inicio - eixo * .02
            addon.hud_volume.atualizar(ctx)
            self.assertNotIn('erro', s)
            self.assertAlmostEqual(addon.gavetas.medidas(grupo)[2], 380, places=2)
        finally:
            addon.hud_volume.terminar(ctx, cancelar=True)

    def test_clique_seleciona_todo_modulo_e_duplo_isola_chapa(self):
        modulo = self.modulo()
        chapa = addon.modulos._chapas_do_conjunto(modulo)[0]
        addon.hud._selecionar_chapa_hud(bpy.context, chapa)
        self.assertEqual(set(bpy.context.selected_objects),
                         {modulo, *modulo.children_recursive})
        self.assertEqual(bpy.context.object, modulo)
        addon.hud._selecionar_chapa_hud(bpy.context, chapa, individual=True)
        self.assertEqual(list(bpy.context.selected_objects), [chapa])
        self.assertEqual(bpy.context.object, chapa)
        self.assertEqual(chapa.chapa_modo, 'INDIVIDUAL')

    def test_hud_nao_aceita_modo_edicao(self):
        self.assertFalse(addon.hud._contexto_hud(SimpleNamespace(mode='EDIT_MESH')))

    def test_familia_selecionada_mede_envelope_so_uma_vez(self):
        from unittest.mock import patch
        modulo=self.modulo()
        for o in [modulo,*modulo.children_recursive]:o.select_set(True)
        with patch.object(addon.modulos,'pecas_do_envelope',wraps=addon.modulos.pecas_do_envelope) as medir:
            itens=addon.hud._itens_da_selecao(bpy.context)
        self.assertEqual(len(itens),1)
        self.assertEqual(medir.call_count,1)

    def test_contorno_grupo_tem_quatro_arestas_por_eixo_e_sem_E(self):
        modulo = self.modulo()
        geometria = addon.hud._geometria_hud(bpy.context)
        self.assertEqual(geometria['objeto'], modulo)
        self.assertEqual(len(geometria['cantos']), 8)
        self.assertEqual(len(geometria['linhas']), 12)
        self.assertEqual({l['letra'] for l in geometria['linhas']}, {'L', 'A', 'P'})
        for eixo in range(3):
            self.assertEqual(sum(l['eixo'] == eixo for l in geometria['linhas']), 4)

    def test_individual_usa_espessura_local_mesmo_girada(self):
        modulo = self.modulo()
        chapa = next(o for o in addon.modulos._chapas_do_conjunto(modulo)
                     if abs(o.rotation_euler.y) > 1)
        addon.hud._selecionar_chapa_hud(bpy.context, chapa, individual=True)
        geometria = addon.hud._geometria_hud(bpy.context)
        arestas = [l for l in geometria['linhas'] if l['letra'] == 'E']
        self.assertEqual(len(arestas), 4)
        for linha in arestas:
            a, b = linha['pontos']
            self.assertAlmostEqual((b-a).length, chapa.chapa_espessura_mm/1000, places=5)

    def test_hit_test_em_tela_reconhece_canto_e_aresta(self):
        self.modulo()
        geometria = addon.hud._geometria_hud(bpy.context)
        for profundidade in (-180, 80, 230):
            projetar = lambda p: Vector((300+p.x*500+p.y*profundidade,
                                        200+p.z*500+p.y*100))
            canto = addon.hud._acertar_linhas_hud(
                geometria, projetar(geometria['cantos'][0]), projetar)
            self.assertEqual(canto['tipo'], 'ancora')
            linha = geometria['linhas'][0]
            ponto = sum(linha['pontos'], Vector())/2
            atingida = addon.hud._acertar_linhas_hud(geometria, projetar(ponto), projetar)
            self.assertEqual(atingida['tipo'], 'medida')
            self.assertEqual(atingida['eixo'], linha['eixo'])

    def _conferir_contorno_modelado_no_modulo(self, tipo):
        from unittest.mock import patch
        modulo = self.modulo()
        bpy.ops.object.cabinet_portas(
            capturado=True, ponto_a=(-.3, -.15, 0), ponto_b=(.3, -.15, .4),
            pai_nome=modulo.name, modulo_nome=modulo.name,
            frente='NEG_Y', folhas=1)
        grupo, = addon.portas._portas_do_conjunto(modulo)
        folha, = addon.portas._folhas_portas(grupo)
        if tipo == 'FACETADA':
            hx, hy, hz = addon.chapas._meias(folha)
            frente = [Vector((x, -hy, z)) for x,z in ((-hx,hz),(0,hz+.08),(hx,hz))]
            tras = [p-Vector((0,0,2*hz)) for p in frente]
            vertices = frente+tras+[p+Vector((0,2*hy,0)) for p in frente+tras]
            faces = []
            for i in range(2):
                faces.extend(((i,i+1,7+i,6+i),(3+i,9+i,10+i,4+i),
                              (i,3+i,4+i,i+1),(6+i,7+i,10+i,9+i)))
            faces.extend(((0,6,9,3),(2,5,11,8)))
            folha.data.clear_geometry()
            folha.data.from_pydata(vertices, [], faces)
            folha.data.update()
        else:
            if tipo == 'CURVA':
                folha['chapa_arco_mm'] = 60.
            else:
                addon.portas._vestir_folha(folha, {'folha':'QUADRO'})
            addon.chapas.gerar_malha_chapa(folha)
        # A nova fixture tem outra topologia; o primeiro preparo deve
        # reconhecer sua superficie sem herdar os rotulos da caixa inicial.
        for nome in (addon.frentes.ATR_FACE, addon.frentes.ATR_BORDA):
            atributo = folha.data.attributes.get(nome)
            if atributo is not None:
                folha.data.attributes.remove(atributo)
        addon.frentes.preparar(folha, forcar=True)
        bpy.context.view_layer.update()
        addon.hud._selecionar_chapa_hud(bpy.context, addon.modulos._chapas_do_conjunto(modulo)[0])
        with patch.object(bmesh,'new',side_effect=AssertionError('BMesh no redraw')),patch.object(addon.frentes,'preparar',side_effect=AssertionError('Preparo no redraw')):
            geometria=addon.hud._geometria_hud(bpy.context)
        self.assertEqual(sum(l['tipo']=='medida' for l in geometria['linhas']),12)
        self.assertFalse(any(l['tipo'] in ('contorno_porta','gap') for l in geometria['linhas']))
        self.assertTrue(all(len(l['pontos'])==2 for l in geometria['linhas']))
        # A abertura da folha nao muda a blocagem da carcaca.
        antes=[l['pontos'] for l in geometria['linhas']]
        addon.ferragens._definir_abertura(bpy.context,folha,.35)
        bpy.context.view_layer.update()
        with patch.object(bmesh,'new',side_effect=AssertionError('BMesh no redraw aberto')):
            aberta=addon.hud._geometria_hud(bpy.context)
        self.assertEqual(antes,[l['pontos'] for l in aberta['linhas']])

    def test_contorno_hud_modulo_segue_dobra_da_folha_sem_bmesh_no_redraw(self):
        self._conferir_contorno_modelado_no_modulo('FACETADA')

    def test_contorno_hud_modulo_segue_curva_nativa_sem_corda(self):
        self._conferir_contorno_modelado_no_modulo('CURVA')

    def test_contorno_hud_modulo_segue_quadro_e_painel_nativos(self):
        self._conferir_contorno_modelado_no_modulo('QUADRO')

    def test_contorno_porta_e_gap_sao_distintos_do_modulo(self):
        modulo=self.modulo()
        bpy.ops.object.cabinet_portas(capturado=True,ponto_a=(-.3,-.15,0),ponto_b=(.3,-.15,.4),
            pai_nome=modulo.name,modulo_nome=modulo.name,frente='NEG_Y',folhas=2)
        grupo,=addon.portas._portas_do_conjunto(modulo)
        addon.hud._selecionar_chapa_hud(bpy.context,addon.modulos._chapas_do_conjunto(modulo)[0])
        geometria=addon.hud._geometria_hud(bpy.context)
        self.assertEqual(sum(l['tipo']=='medida' for l in geometria['linhas']),12)
        self.assertFalse(any(l['tipo'] in ('contorno_porta','gap') for l in geometria['linhas']))
        for folha in addon.portas._folhas_portas(grupo):
            pontos,arestas=addon.portas_viewport._contorno_da_folha(folha)
            self.assertTrue(pontos);self.assertTrue(arestas)
        addon.ferragens._definir_abertura(bpy.context,addon.portas._folhas_portas(grupo)[0],.5)
        self.assertEqual([l['pontos'] for l in geometria['linhas']],
                         [l['pontos'] for l in addon.hud._geometria_hud(bpy.context)['linhas']])

    def test_clique_leva_a_gaveta_para_a_aba_do_item(self):
        # Pedido do usuario: clicou na porta -> aba Portas; no modulo ->
        # Modulos; no puxador -> Puxadores. So' o CLIQUE troca a aba.
        modulo = self.modulo()
        bpy.ops.object.cabinet_portas(
            capturado=True, ponto_a=(-0.3, -0.15, 0), ponto_b=(0.3, -0.15, 0.4),
            pai_nome=modulo.name, modulo_nome=modulo.name,
            frente='NEG_Y', folhas=2)
        cena = bpy.context.scene
        self.addCleanup(setattr, cena, 'cabinet_aba', 'MODULOS')
        grupo = addon.portas._portas_do_conjunto(modulo)[0]
        folha = addon.portas._folhas_portas(grupo)[0]
        chapa = addon.modulos._chapas_do_conjunto(modulo)[0]
        cena.cabinet_aba = 'MODULOS'
        bpy.ops.object.select_all(action='DESELECT')
        self.clicar_pelo_keymap(folha, 'PRESS')
        self.assertEqual(cena.cabinet_aba, 'PORTAS')
        self.clicar_pelo_keymap(chapa, 'PRESS')
        self.assertEqual(bpy.context.object, modulo)
        self.assertEqual(cena.cabinet_aba, 'MODULOS')
        # puxador: o clique nativo o deixa ativo
        pux = bpy.data.objects.new('Puxador', None)
        bpy.context.collection.objects.link(pux)
        pux[addon.chapas.MARCA_PUXADOR] = 1
        bpy.ops.object.select_all(action='DESELECT')
        pux.select_set(True)
        bpy.context.view_layer.objects.active = pux
        addon.selecao._seguir_selecao_na_gaveta(bpy.context)
        self.assertEqual(cena.cabinet_aba, 'PUXADORES')
        # o ADD-ON trocar o ativo (criar porta deixa o modulo) nao mexe
        bpy.context.view_layer.objects.active = modulo
        modulo.select_set(True)
        self.assertEqual(cena.cabinet_aba, 'PUXADORES')
        # objeto de fora nao e' de aba nenhuma
        self.assertIsNone(addon.selecao._aba_da_selecao(bpy.data.objects.new('X', None)))

    def test_hover_acende_as_quatro_arestas_do_eixo(self):
        self.modulo()
        geometria = addon.hud._geometria_hud(bpy.context)
        for eixo in range(3):
            alvo = next(l for l in geometria['linhas'] if l['eixo'] == eixo)
            normais, acesos = addon.hud._segmentos_hud(geometria, alvo)
            self.assertEqual(len(acesos), 8)
            self.assertEqual(len(normais), 16)

    def test_arraste_dimensao_atualiza_a_mesma_propriedade_do_menu(self):
        modulo = self.modulo()
        geometria = addon.hud._geometria_hud(bpy.context)
        for letra, prop, valor in (('L', 'conj_largura_mm', 900),
                                   ('A', 'conj_altura_mm', 1300),
                                   ('P', 'conj_profundidade_mm', 450)):
            alvo = next(l for l in geometria['linhas'] if l['letra'] == letra)
            addon.hud._aplicar_valor_hud(bpy.context, alvo, valor)
            self.assertAlmostEqual(getattr(modulo, prop), valor)
            campos = addon.gaveta._medidas_gaveta(bpy.context)[1]
            self.assertIn(valor, [v for _, v, _ in campos])

    def test_linha_perto_da_quina_ancora_e_estica_para_o_outro_lado(self):
        projetar = lambda p: Vector((300+p.x*500+p.y*150, 200+p.z*500+p.y*90))
        for eixo, prop in ((0, 'conj_largura_mm'), (1, 'conj_profundidade_mm'),
                           (2, 'conj_altura_mm')):
            for lado in ('min', 'max'):
                with self.subTest(eixo=eixo, lado=lado):
                    self.setUp()
                    modulo = self.modulo()
                    chapas = addon.modulos._chapas_do_conjunto(modulo)
                    lo, hi = (list(v) for v in addon.modulos._caixa_de(chapas))
                    geometria = addon.hud._geometria_hud(bpy.context)
                    linha = next(l for l in geometria['linhas']
                                 if l['eixo'] == eixo)
                    a, b = linha['pontos']
                    # mouse a 1/5 da aresta, do lado pedido, fora do
                    # raio da quina
                    perto, longe = (a, b) if lado == 'min' else (b, a)
                    mouse = projetar(perto + (longe - perto) * 0.2)
                    alvo = addon.hud._acertar_linhas_hud(geometria, mouse, projetar)
                    self.assertEqual(alvo['tipo'], 'medida')
                    self.assertEqual(alvo['lado'], lado)
                    self.assertEqual(alvo['pontos'][0], perto)
                    # a linha compartilhada nao foi alterada
                    self.assertNotIn('lado', linha)
                    novo = getattr(modulo, prop) + 100
                    addon.hud._aplicar_valor_hud(bpy.context, alvo, novo)
                    lo2, hi2 = addon.modulos._caixa_de(chapas)
                    if lado == 'min':
                        self.assertAlmostEqual(lo2[eixo], lo[eixo], places=5)
                        self.assertAlmostEqual(hi2[eixo], hi[eixo] + 0.1, places=5)
                    else:
                        self.assertAlmostEqual(hi2[eixo], hi[eixo], places=5)
                        self.assertAlmostEqual(lo2[eixo], lo[eixo] - 0.1, places=5)
                    self.assertAlmostEqual(getattr(modulo, prop), novo, places=3)

    def test_tres_eixos_de_uma_vez_respeitam_a_ancora(self):
        # REGRESSAO: o segundo eixo lia matrix_world defasado e gravava
        # de volta o centro antigo -- a peca crescia pelo meio.
        modulo = self.modulo()
        chapas = addon.modulos._chapas_do_conjunto(modulo)
        lo, hi = (list(v) for v in addon.modulos._caixa_de(chapas))
        addon.modulos.redimensionar_grupo(
            chapas, (modulo.conj_largura_mm + 100, modulo.conj_altura_mm + 50,
                     modulo.conj_profundidade_mm + 30), ('max', 'max', 'min'))
        lo2, hi2 = addon.modulos._caixa_de(chapas)
        self.assertAlmostEqual(hi2[0], hi[0], places=5)
        self.assertAlmostEqual(lo2[0], lo[0] - 0.1, places=5)
        self.assertAlmostEqual(hi2[1], hi[1], places=5)
        self.assertAlmostEqual(lo2[2], lo[2], places=5)
        self.assertAlmostEqual(hi2[2], hi[2] + 0.05, places=5)

    def test_chapa_solta_cresce_pela_ancora_mesmo_com_cena_defasada(self):
        bpy.ops.object.cabinet_criar()
        chapa = bpy.context.object
        chapa.chapa_modo = 'GRUPO'
        cena = bpy.context.scene
        cena.grupo_profundidade_mm = 123.0      # valor velho de outro grupo
        lo, hi = (list(v) for v in addon.modulos._caixa_de([chapa]))
        geometria = addon.hud._geometria_hud(bpy.context)
        projetar = lambda p: Vector((300+p.x*500+p.y*150, 200+p.z*500+p.y*90))
        linha = next(l for l in geometria['linhas'] if l['eixo'] == 0)
        a, b = linha['pontos']
        alvo = addon.hud._acertar_linhas_hud(geometria, projetar(a + (b - a) * 0.2),
                                         projetar)
        self.assertEqual(alvo['lado'], 'min')
        addon.hud._aplicar_valor_hud(bpy.context, alvo, (hi[0] - lo[0]) * 1000 + 100)
        lo2, hi2 = addon.modulos._caixa_de([chapa])
        self.assertAlmostEqual(lo2[0], lo[0], places=5)
        self.assertAlmostEqual(hi2[0], hi[0] + 0.1, places=5)
        # o eixo que ninguem tocou continua igual
        self.assertAlmostEqual(hi2[1] - lo2[1], hi[1] - lo[1], places=5)

    def test_chapa_individual_tambem_cresce_pela_ancora(self):
        modulo = self.modulo()
        chapa = addon.modulos._chapas_do_conjunto(modulo)[0]
        addon.hud._selecionar_chapa_hud(bpy.context, chapa, individual=True)
        geometria = addon.hud._geometria_hud(bpy.context)
        self.assertEqual(geometria['modo'], 'INDIVIDUAL')
        projetar = lambda p: Vector((300+p.x*500+p.y*150, 200+p.z*500+p.y*90))
        for eixo, lado in ((0, 'max'), (1, 'min')):
            linha = next(l for l in geometria['linhas'] if l['eixo'] == eixo)
            a, b = linha['pontos']
            perto, longe = (a, b) if lado == 'min' else (b, a)
            alvo = addon.hud._acertar_linhas_hud(
                geometria, projetar(perto + (longe - perto) * 0.2), projetar)
            self.assertEqual(alvo['lado'], lado)
            fixa = perto.copy()
            antes = addon.hud._valor_hud(alvo)
            addon.hud._aplicar_valor_hud(bpy.context, alvo, antes + 80)
            self.assertAlmostEqual(addon.hud._valor_hud(alvo), antes + 80, places=3)
            nova = addon.hud._geometria_hud(bpy.context)
            i, j = alvo['cantos']
            agora = nova['cantos'][i] if lado == 'min' else nova['cantos'][j]
            self.assertLess((agora - fixa).length, 1e-5)
            geometria = nova
        # E (espessura) tambem tem seta nas quinas (pedido do usuario):
        # a face da quina perto do mouse fica parada, engrossa para o
        # outro lado -- nos dois sentidos.
        for lado, soma in (('min', 12.0), ('max', -10.0)):
            linha = next(l for l in geometria['linhas'] if l['eixo'] == 2)
            a, b = linha['pontos']
            perto, longe = (a, b) if lado == 'min' else (b, a)
            alvo = addon.hud._acertar_linhas_hud(
                geometria, projetar(perto + (longe - perto) * 0.2), projetar)
            self.assertEqual((alvo['tipo'], alvo['eixo'], alvo['lado']),
                             ('medida', 2, lado))
            self.assertEqual(addon.hud._letra_do_alvo(alvo), 'E')
            fixa = perto.copy()
            antes = addon.hud._valor_hud(alvo)
            addon.hud._aplicar_valor_hud(bpy.context, alvo, antes + soma)
            self.assertAlmostEqual(chapa.chapa_espessura_mm, antes + soma,
                                   places=3)
            self.assertAlmostEqual(chapa.dimensions.z,
                                   (antes + soma) / 1000, places=5)
            nova = addon.hud._geometria_hud(bpy.context)
            i, j = alvo['cantos']
            agora = nova['cantos'][i] if lado == 'min' else nova['cantos'][j]
            self.assertLess((agora - fixa).length, 1e-5)
            geometria = nova

    def dois_modulos(self):
        modulos = []
        for x in (-2.0, 2.0):
            antes = set(bpy.data.objects)
            bpy.ops.object.cabinet_criar_nicho()
            bpy.ops.object.select_all(action='DESELECT')
            for o in set(bpy.data.objects) - antes:
                o.select_set(True)
            bpy.ops.object.cabinet_agrupar()
            modulo = bpy.context.object
            modulo.location.x = x
            bpy.context.view_layer.update()
            modulos.append(modulo)
        primeiro, segundo = modulos
        for m in (primeiro, segundo):
            for o in [m, *m.children_recursive]:
                o.select_set(True)
        bpy.context.view_layer.objects.active = primeiro
        return primeiro, segundo

    def test_selecao_principal_tem_a_linha_mais_grossa(self):
        # Pedido do usuario: com 2+ itens selecionados, o ATIVO (que manda
        # nas funcoes) sai levemente mais grosso; com 1 so', nada muda.
        primeiro, segundo = self.dois_modulos()
        contexto = _ContextoRegiao()
        desenhos = addon.hud._desenhos_hud(contexto)
        self.assertEqual(len(desenhos), 2)
        principal = addon.hud._principal_hud(contexto, desenhos)
        self.assertIs(desenhos[principal][0]['objeto'], primeiro)
        bpy.context.view_layer.objects.active = segundo
        desenhos = addon.hud._desenhos_hud(contexto)
        principal = addon.hud._principal_hud(contexto, desenhos)
        self.assertIs(desenhos[principal][0]['objeto'], segundo)
        for o in [primeiro, *primeiro.children_recursive]:
            o.select_set(False)
        self.assertIsNone(addon.hud._principal_hud(
            contexto, addon.hud._desenhos_hud(contexto)))
        # levemente: +40%, nunca menos de 1 px
        self.assertEqual(addon.hud._espessura_principal_hud(1.5), 2.5)
        self.assertEqual(addon.hud._espessura_principal_hud(10.0), 14.0)

    def test_clique_num_de_varios_selecionados_deixa_so_ele_ao_soltar(self):
        primeiro, segundo = self.dois_modulos()
        chapa = addon.modulos._chapas_do_conjunto(segundo)[0]
        self.addCleanup(addon.hud._clique_pendente.clear)
        original = addon.hud._raio_hud
        addon.hud._raio_hud = lambda _c, _l: (chapa, None)
        self.addCleanup(setattr, addon.hud, '_raio_hud', original)
        contexto = _ContextoRegiao()
        evento = SimpleNamespace(mouse_region_x=10, mouse_region_y=10)
        classe = addon.selecao.OBJECT_OT_selecionar

        def clicar(valor):
            op = SimpleNamespace(
                modo='INDIVIDUAL' if valor == 'DOUBLE_CLICK' else 'GRUPO',
                extend=False, deselect=False, toggle=False,
                deselect_all=True, location=(0, 0),
                select_passthrough=valor == 'PRESS', clique=valor == 'CLICK')
            op._soltou = lambda c, p: classe._soltou(op, c, p)
            op._invoke = lambda c, e: classe._invoke(op, c, e)
            op.execute = lambda c: {'CANCELLED'}
            return classe.invoke(op, contexto, evento)

        dois = {primeiro, *primeiro.children_recursive,
                segundo, *segundo.children_recursive}
        # PRESS: nada muda -- arrastar ainda leva os dois modulos
        self.assertIn('PASS_THROUGH', clicar('PRESS'))
        self.assertEqual(set(bpy.context.selected_objects), dois)
        # soltou sem arrastar: so' o modulo clicado
        self.assertEqual(clicar('CLICK'), {'FINISHED'})
        self.assertEqual(set(bpy.context.selected_objects),
                         {segundo, *segundo.children_recursive})
        self.assertEqual(bpy.context.object, segundo)
        # sozinho: o PRESS seleciona direto e o CLICK nao se mete
        self.assertEqual(clicar('PRESS'), {'FINISHED'})
        self.assertEqual(clicar('CLICK'), {'PASS_THROUGH'})
        self.assertEqual(set(bpy.context.selected_objects),
                         {segundo, *segundo.children_recursive})
        # duplo clique partindo de varios selecionados ainda isola a chapa
        for o in dois:
            o.select_set(True)
        for valor in ('PRESS', 'CLICK', 'DOUBLE_CLICK'):
            clicar(valor)
        self.assertEqual(bpy.context.selected_objects, [chapa])

    def clicar_pelo_keymap(self, chapa, valor, shift=False):
        """Roda cabinet_selecionar com as props da entrada do keymap
        (valor, shift), com o raio acertando `chapa`."""
        entrada = next(e for e in addon.selecao._ENTRADAS_KEYMAP
                       if e[0] == valor and e[1] == shift)
        original = addon.hud._raio_hud
        addon.hud._raio_hud = lambda _c, _l: (chapa, None) if chapa is not None else None
        classe = addon.selecao.OBJECT_OT_selecionar
        props = dict(extend=False, deselect=False, toggle=False,
                     deselect_all=False, select_passthrough=False,
                     clique=False)
        props.update(entrada[3])
        op = SimpleNamespace(modo=entrada[2], location=(0, 0), **props)
        op._soltou = lambda c, p: classe._soltou(op, c, p)
        op._invoke = lambda c, e: classe._invoke(op, c, e)
        def selecionar_nativo(c):
            # Fora do modulo, o Blender limpa/escolhe o objeto comum.
            if not shift:
                bpy.ops.object.select_all(action='DESELECT')
            if chapa is not None:
                chapa.select_set(True)
                bpy.context.view_layer.objects.active = chapa
            return {'FINISHED'}
        op.execute = selecionar_nativo
        try:
            return classe.invoke(op, _ContextoRegiao(), SimpleNamespace(
                mouse_region_x=10, mouse_region_y=10))
        finally:
            addon.hud._raio_hud = original

    def duplo(self, chapa, shift=False):
        """O que o Blender entrega num duplo clique: PRESS e DOUBLE_CLICK."""
        self.clicar_pelo_keymap(chapa, 'PRESS', shift)
        self.clicar_pelo_keymap(chapa, 'DOUBLE_CLICK', shift)

    def _gavetas_para_clique(self):
        self.addCleanup(setattr,bpy.context.scene,'cabinet_aba',bpy.context.scene.cabinet_aba)
        modulo=self.modulo()
        grupo=addon.gavetas.criar_gavetas(bpy.context,modulo,(18,18,18,18,0),
                                         dict(quantidade=3,profundidade_mm=300))
        unidades=addon.gavetas.gavetas_do_grupo(grupo)
        return grupo,unidades,[addon.gavetas.frente_da_gaveta(g) for g in unidades]

    # Regressao (era BUG, corrigido na 384): Shift voltava ao vao inteiro.
    def test_shift_apos_duplo_na_gaveta_soma_unidade_sem_expandir_conjunto(self):
        grupo,unidades,frentes=self._gavetas_para_clique()
        self.duplo(frentes[0])
        self.clicar_pelo_keymap(frentes[2],'PRESS',shift=True)
        self.assertFalse(grupo.select_get())
        self.assertTrue(unidades[0].select_get());self.assertTrue(unidades[2].select_get())
        self.assertFalse(any(o.select_get() for o in [unidades[1],*unidades[1].children_recursive]))
        self.assertIs(bpy.context.object,unidades[2])
        esperados={o for g in (unidades[0],unidades[2]) for o in g.children_recursive if o.type=='MESH'}
        self.assertEqual(set(addon.selecao.malhas_para_editar(bpy.context)),esperados)
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual(set(bpy.context.objects_in_mode),esperados)
        bpy.ops.object.cabinet_editar_grupo()
        self.assertFalse(grupo.select_get())

    def test_shift_duplo_encolhe_so_o_grupo_da_gaveta_e_conserva_objeto_externo(self):
        grupo,unidades,frentes=self._gavetas_para_clique()
        bpy.ops.mesh.primitive_cube_add(location=(3,0,0))
        externo=bpy.context.object
        self.duplo(frentes[0],shift=True)
        self.assertFalse(grupo.select_get())
        self.assertTrue(unidades[0].select_get())
        self.assertFalse(any(g.select_get() for g in unidades[1:]))
        self.assertTrue(externo.select_get())
        self.duplo(frentes[2],shift=True)
        self.assertTrue(unidades[0].select_get());self.assertTrue(unidades[2].select_get())
        self.assertFalse(unidades[1].select_get())
        self.assertTrue(externo.select_get())
        self.assertIs(bpy.context.object,unidades[2])

    def test_clique_simples_da_gaveta_ainda_seleciona_todo_o_conjunto(self):
        grupo,unidades,frentes=self._gavetas_para_clique()
        self.duplo(frentes[0])
        self.clicar_pelo_keymap(frentes[2],'PRESS',shift=True)
        self.clicar_pelo_keymap(frentes[1],'PRESS')
        self.assertTrue(grupo.select_get())
        self.assertTrue(all(g.select_get() for g in unidades))
        self.assertIs(bpy.context.object,grupo)

    # Regressao (era BUG, corrigido na 385): puxador voltava ao conjunto inteiro.
    def test_clique_no_puxador_da_gaveta_isolada_edita_so_ele(self):
        grupo,unidades,frentes=self._gavetas_para_clique()
        puxador=next(o for o in frentes[1].children if addon.chapas.MARCA_PUXADOR in o)
        corpo=next(o for o in unidades[1].children if o.get(addon.gavetas.MARCA_PECA)=='FUNDO')
        for obj in (frentes[1],corpo):
            with self.subTest(peca=obj.name):
                self.duplo(obj)
                self.assertTrue(unidades[1].select_get());self.assertFalse(grupo.select_get())
                self.clicar_pelo_keymap(puxador,'PRESS')
                self.assertEqual(set(bpy.context.selected_objects),{puxador})
                self.assertIs(bpy.context.object,puxador)
                self.assertEqual(bpy.context.scene.cabinet_aba,'PUXADORES')
                self.assertFalse(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))

    def test_duplo_direto_no_puxador_independe_de_selecionar_gaveta_antes(self):
        grupo,unidades,frentes=self._gavetas_para_clique()
        puxador=next(o for o in frentes[2].children if addon.chapas.MARCA_PUXADOR in o)
        self.duplo(puxador)
        self.assertEqual(set(bpy.context.selected_objects),{puxador})
        self.assertIs(bpy.context.object,puxador)
        self.assertEqual(bpy.context.scene.cabinet_aba,'PUXADORES')

    def test_clique_no_puxador_ja_isolado_conserva_somente_o_acessorio(self):
        grupo,unidades,frentes=self._gavetas_para_clique()
        puxador=next(o for o in frentes[0].children if addon.chapas.MARCA_PUXADOR in o)
        self.duplo(puxador)
        self.clicar_pelo_keymap(puxador,'PRESS')
        self.assertEqual(set(bpy.context.selected_objects),{puxador})
        self.assertIs(bpy.context.object,puxador)

    def test_gaveta_isolada_na_parede_libera_clique_no_proprio_puxador(self):
        grupo,unidades,frentes=self._gavetas_para_clique()
        modulo=addon.gavetas.modulo_do_grupo(grupo)
        puxador=next(o for o in frentes[1].children if addon.chapas.MARCA_PUXADOR in o)
        with patch.object(addon.paredes_edicao,'modulo_da_peca',return_value=modulo):
            self.duplo(frentes[1])
            self.assertTrue(unidades[1].select_get());self.assertFalse(modulo.select_get())
            self.clicar_pelo_keymap(puxador,'PRESS')
            self.assertEqual(set(bpy.context.selected_objects),{puxador})
            self.assertIs(bpy.context.object,puxador)

    def test_gaveta_isolada_nao_libera_puxador_de_outra_gaveta(self):
        grupo,unidades,frentes=self._gavetas_para_clique()
        outro=next(o for o in frentes[2].children if addon.chapas.MARCA_PUXADOR in o)
        self.duplo(frentes[0])
        self.clicar_pelo_keymap(outro,'PRESS')
        self.assertTrue(grupo.select_get())
        self.assertIs(bpy.context.object,grupo)
        self.assertFalse(outro.select_get())

    def test_objeto_comum_e_parede_continuam_selecionados_em_um_clique(self):
        grupo,unidades,frentes=self._gavetas_para_clique()
        for nome in ('Objeto comum','Parede generica'):
            with self.subTest(objeto=nome):
                bpy.ops.mesh.primitive_cube_add(location=(3,0,0))
                comum=bpy.context.object;comum.name=nome
                self.duplo(frentes[0])
                self.clicar_pelo_keymap(comum,'PRESS')
                self.assertEqual(set(bpy.context.selected_objects),{comum})
                self.assertIs(bpy.context.object,comum)
                self.assertEqual(self.clicar_pelo_keymap(comum,'CLICK'),{'PASS_THROUGH'})

    def test_material_nativo_usa_chapa_mestre_sem_perder_modulos_selecionados(self):
        destino, outro = self.dois_modulos()
        origem = addon.modulos._chapas_do_conjunto(outro)[0]
        material = bpy.data.materials.new('Material da mestre')
        addon.materiais.aplicar([origem], material)
        self.clicar_pelo_keymap(addon.modulos._chapas_do_conjunto(destino)[0], 'PRESS')
        self.clicar_pelo_keymap(origem, 'PRESS', shift=True)
        self.assertEqual(bpy.context.object, origem)

        self.assertTrue(destino.select_get())
        self.assertTrue(outro.select_get())
        selecionados = set(bpy.context.selected_objects)
        malhas = {o.name:(o.data.as_pointer(),tuple(tuple(v.co) for v in o.data.vertices))
                  for o in selecionados if o.type == 'MESH'}
        self.assertEqual(bpy.ops.object.make_links_data(type='MATERIAL'), {'FINISHED'})
        for o in selecionados:
            if o.type == 'MESH':
                self.assertIs(o.active_material, material)
                self.assertEqual(malhas[o.name],
                    (o.data.as_pointer(),tuple(tuple(v.co) for v in o.data.vertices)))
        self.assertEqual(set(bpy.context.selected_objects), selecionados)
        self.assertEqual(bpy.context.object, origem)

    def _grupo_para_pintar_com_ferragens(self):
        modulo=self.modulo();pecas=addon.modulos._chapas_do_conjunto(modulo)
        metal=bpy.data.materials.new('Metal preservado')
        ferragens=[]
        for nome,marca in (('Puxador protegido',addon.chapas.MARCA_PUXADOR),
                           ('Dobradica protegida',addon.ferragens.CHAVE_FERRAGEM),
                           ('Acessorio protegido',addon.chapas.MARCA_ACESSORIO)):
            obj=bpy.data.objects.new(nome,pecas[0].data.copy())
            bpy.context.scene.collection.objects.link(obj);obj.parent=pecas[0];obj[marca]=1
            obj.data.materials.clear();obj.data.materials.append(metal);ferragens.append(obj)
        trilho=bpy.data.objects.new('Trilho protegido',pecas[0].data.copy())
        bpy.context.scene.collection.objects.link(trilho);trilho.parent=modulo
        trilho[addon.gavetas.MARCA_PECA]='TRILHO'
        trilho.data.materials.clear();trilho.data.materials.append(metal);ferragens.append(trilho)
        origem=bpy.data.objects.new('Origem da madeira',pecas[0].data.copy())
        bpy.context.scene.collection.objects.link(origem)
        madeira=bpy.data.materials.new('Madeira para o grupo')
        origem.data.materials.clear();origem.data.materials.append(madeira)
        addon.hud._selecionar_chapa_hud(bpy.context,pecas[0])
        origem.select_set(True);bpy.context.view_layer.objects.active=origem
        return modulo,pecas,ferragens,origem,madeira,metal

    # Regressao (era BUG, corrigido na 382): grupo pintava o puxador selecionado.
    def test_vincular_material_do_grupo_preserva_ferragens_sem_mudar_selecao(self):
        modulo,pecas,ferragens,origem,madeira,metal=self._grupo_para_pintar_com_ferragens()
        for obj in ferragens:obj.select_set(True)
        selecionados=set(bpy.context.selected_objects)
        self.assertEqual(bpy.ops.object.cabinet_vincular_materiais(),{'FINISHED'})
        for obj in ferragens:self.assertIs(obj.active_material,metal)
        for obj in pecas:self.assertIs(obj.active_material,madeira)
        self.assertEqual(set(bpy.context.selected_objects),selecionados)
        self.assertIs(bpy.context.object,origem)

    # Regressao (era BUG, corrigido na 382): filho sem marca passava pelo filtro.
    def test_pintura_do_catalogo_reconhece_ferragem_pela_hierarquia(self):
        modulo,pecas,ferragens,origem,madeira,metal=self._grupo_para_pintar_com_ferragens()
        obj=bpy.data.objects.new('Filho sem marca do puxador',pecas[0].data.copy())
        bpy.context.scene.collection.objects.link(obj);obj.parent=ferragens[0]
        obj[addon.chapas.MARCA_CHAPA]=1
        obj.data.materials.clear();obj.data.materials.append(metal)
        alvos=addon.materiais.pecas_dos_alvos([modulo,obj])
        self.assertNotIn(obj,alvos)
        addon.materiais.aplicar(alvos,madeira)
        self.assertIs(obj.active_material,metal)
        self.assertTrue(all(o.active_material==metal for o in ferragens))

    def test_vincular_material_individual_permite_pintar_puxador(self):
        modulo,pecas,ferragens,origem,madeira,metal=self._grupo_para_pintar_com_ferragens()
        bpy.ops.object.select_all(action='DESELECT')
        ferragens[0].select_set(True);origem.select_set(True)
        bpy.context.view_layer.objects.active=origem
        self.assertEqual(bpy.ops.object.cabinet_vincular_materiais(),{'FINISHED'})
        self.assertIs(ferragens[0].active_material,madeira)
        self.assertTrue(all(o.active_material==metal for o in ferragens[1:]))

    def test_ferragem_mestre_pode_fornecer_material_sem_pintar_outras_ferragens(self):
        modulo,pecas,ferragens,origem,madeira,metal=self._grupo_para_pintar_com_ferragens()
        cromo=bpy.data.materials.new('Cromo da mestre')
        ferragens[0].material_slots[0].material=cromo
        for obj in ferragens:obj.select_set(True)
        bpy.context.view_layer.objects.active=ferragens[0]
        self.assertEqual(bpy.ops.object.cabinet_vincular_materiais(),{'FINISHED'})
        self.assertTrue(all(o.active_material==cromo for o in pecas))
        self.assertTrue(all(o.active_material==metal for o in ferragens[1:]))

    def _desenhar_menu_vinculos(self):
        class Layout:
            operator_context='INVOKE_REGION_WIN'
            def __init__(self):self.itens=[]
            def operator(self,identificador,**props):
                op=SimpleNamespace();self.itens.append(('operador',identificador,props,op,self.operator_context));return op
            def operator_enum(self,identificador,propriedade,**props):
                self.itens.append(('enum',identificador,propriedade))
            def operator_menu_enum(self,identificador,propriedade,**props):
                self.itens.append(('submenu',identificador,propriedade))
            def separator(self):pass
        layout=Layout()
        addon.materiais.VIEW3D_MT_vinculos.draw(SimpleNamespace(layout=layout),bpy.context)
        return layout

    def test_ctrl_l_reutiliza_menu_nativo_e_protege_so_a_acao_material(self):
        self._grupo_para_pintar_com_ferragens()
        layout=self._desenhar_menu_vinculos()
        operadores=[i for i in layout.itens if i[0]=='operador']
        self.assertEqual(sum(i[1]=='object.cabinet_vincular_materiais' for i in operadores),1)
        tipos={i[3].type for i in operadores if i[1]=='object.make_links_data'}
        originais={i.identifier for i in bpy.ops.object.make_links_data.get_rna_type().properties['type'].enum_items if i.identifier}
        self.assertEqual(tipos,originais-{'MATERIAL'})
        self.assertTrue(any(i[1]=='object.data_transfer' for i in operadores))
        self.assertTrue(any(i[1]=='object.join_uvs' for i in operadores))
        self.assertTrue(any(k.idname=='wm.call_menu' and k.type=='L' and k.ctrl
            and k.properties.name=='VIEW3D_MT_cabinet_vinculos' for _m,k in addon.selecao._keymaps))

    def test_ctrl_l_sem_grupo_preserva_enum_nativo_completo(self):
        bpy.ops.object.select_all(action='DESELECT')
        layout=self._desenhar_menu_vinculos()
        self.assertIn(('enum','object.make_links_data','type'),layout.itens)
        self.assertFalse(any(i[0]=='operador' and i[1]=='object.cabinet_vincular_materiais' for i in layout.itens))

    def test_protecao_de_material_atende_portas_gavetas_prateleiras_e_divisorias(self):
        modulo,pecas,ferragens,origem,madeira,metal=self._grupo_para_pintar_com_ferragens()
        marcas=(addon.chapas.MARCA_PORTAS,addon.gavetas.MARCA_GRUPO,addon.gavetas.MARCA_GAVETA,
                addon.prateleiras.MARCA_GRUPO,addon.divisorias.MARCA_GRUPO)
        for marca in marcas:
            with self.subTest(marca=marca):
                bpy.ops.object.select_all(action='DESELECT')
                grupo=bpy.data.objects.new('Grupo para pintar',None)
                bpy.context.scene.collection.objects.link(grupo);grupo[marca]=1;grupo.select_set(True)
                for o in [*pecas,*ferragens,origem]:o.select_set(True)
                bpy.context.view_layer.objects.active=origem
                self.assertEqual(bpy.ops.object.cabinet_vincular_materiais(),{'FINISHED'})
                self.assertTrue(all(o.active_material==madeira for o in pecas))
                self.assertTrue(all(o.active_material==metal for o in ferragens))

    def test_undo_redo_da_pintura_protegida_mantem_metal_e_selecao(self):
        modulo,pecas,ferragens,origem,madeira,metal=self._grupo_para_pintar_com_ferragens()
        for o in ferragens:o.select_set(True)
        nomes=[o.name for o in pecas];metais=[o.name for o in ferragens]
        selecionados={o.name for o in bpy.context.selected_objects};ativo=origem.name
        nome_metal=metal.name;nome_madeira=madeira.name
        bpy.ops.ed.undo_push(message='Antes da pintura protegida')
        self.assertEqual(bpy.ops.object.cabinet_vincular_materiais(),{'FINISHED'})
        bpy.ops.ed.undo_push(message='Pintura protegida concluida')
        modulo=pecas=ferragens=origem=madeira=metal=None;o=None
        for operacao,pintado in ((bpy.ops.ed.undo,False),(bpy.ops.ed.redo,True)):
            operacao();addon.eventos._fim_do_desfazer();bpy.context.view_layer.update()
            for nome in nomes:
                material=bpy.data.objects[nome].active_material
                self.assertEqual(material.name if material else None,nome_madeira if pintado else None)
            self.assertTrue(all(bpy.data.objects[n].active_material.name==nome_metal for n in metais))
            self.assertEqual({o.name for o in bpy.context.selected_objects},selecionados)
            self.assertEqual(bpy.context.object.name,ativo)

    def test_material_nativo_de_chapa_isolada_preserva_as_outras_pecas_da_origem(self):
        destino, outro = self.dois_modulos()
        pecas = addon.modulos._chapas_do_conjunto(outro)
        antiga = bpy.data.materials.new('Material preservado')
        nova = bpy.data.materials.new('Material da chapa isolada')
        addon.materiais.aplicar(pecas, antiga)
        origem = pecas[0]
        addon.materiais.aplicar([origem], nova)
        self.clicar_pelo_keymap(addon.modulos._chapas_do_conjunto(destino)[0], 'PRESS')
        self.duplo(origem, shift=True)
        self.assertEqual(bpy.context.object, origem)
        self.assertFalse(outro.select_get())
        self.assertEqual(bpy.ops.object.make_links_data(type='MATERIAL'), {'FINISHED'})
        for o in addon.modulos._chapas_do_conjunto(destino):
            self.assertIs(o.active_material, nova)
        for o in pecas[1:]:
            self.assertIs(o.active_material, antiga)

    def test_material_nativo_de_chapa_solta_copia_todos_os_slots(self):
        destino = self.modulo()
        origem = addon.chapas.nova_chapa('Chapa solta',400,300,18,(2000,0,0),(0,0,0),bpy.context)
        materiais = [bpy.data.materials.new('Slot origem %d' % i) for i in range(2)]
        for mat in materiais:
            origem.data.materials.append(mat)
        for i, slot in enumerate(origem.material_slots):
            slot.link = 'OBJECT'
            slot.material = materiais[i]
        for i, face in enumerate(origem.data.polygons):
            face.material_index = i % 2
        self.clicar_pelo_keymap(addon.modulos._chapas_do_conjunto(destino)[0], 'PRESS')
        self.clicar_pelo_keymap(origem, 'PRESS', shift=True)
        self.assertEqual(bpy.context.object, origem)
        self.assertEqual(bpy.ops.object.make_links_data(type='MATERIAL'), {'FINISHED'})
        for o in addon.modulos._chapas_do_conjunto(destino):
            self.assertEqual([s.material for s in o.material_slots], materiais)

    def test_shift_na_porta_preserva_grupo_e_folha_mestre_para_material_nativo(self):
        destino = self.modulo()
        bpy.ops.object.cabinet_portas(capturado=True,
            ponto_a=(-.3,-.15,0),ponto_b=(.3,-.15,.4),
            pai_nome=destino.name,modulo_nome=destino.name,
            frente='NEG_Y',dobradica='RETA',folhas=2)
        grupo = addon.portas._portas_do_conjunto(destino)[0]
        folha = addon.portas._folhas_portas(grupo)[0]
        origem = addon.chapas.nova_chapa('Outra chapa',400,300,18,(2000,0,0),(0,0,0),bpy.context)
        material = bpy.data.materials.new('Material da folha')
        addon.materiais.aplicar([folha], material)
        self.clicar_pelo_keymap(origem, 'PRESS')
        self.clicar_pelo_keymap(folha, 'PRESS', shift=True)
        self.assertEqual(bpy.context.object, folha)
        self.assertTrue(grupo.select_get())
        self.assertEqual(addon.hud._nivel_da_selecao(bpy.context, folha), 'PORTA')
        self.assertTrue(origem.select_get())
        self.assertEqual(bpy.ops.object.make_links_data(type='MATERIAL'), {'FINISHED'})
        self.assertIs(origem.active_material, material)

    def test_clique_no_vazio_reseta_individual_e_exige_novo_duplo(self):
        # Regressao v346: o nome do ultimo clique sobrevivia ao vazio,
        # mantendo o contexto individual depois de limpar a selecao.
        modulo = self.modulo()
        chapa = addon.modulos._chapas_do_conjunto(modulo)[0]
        self.duplo(chapa)
        self.assertEqual(bpy.context.selected_objects, [chapa])
        self.assertEqual(chapa.chapa_modo, 'INDIVIDUAL')
        addon.hud._hover_hud[4242] = {'objeto': chapa}
        self.clicar_pelo_keymap(None, 'PRESS')
        self.assertFalse(bpy.context.selected_objects)
        self.assertFalse(addon.hud._clique_chapa_hud)
        self.assertFalse(addon.hud._hover_hud)
        self.assertEqual(chapa.chapa_modo, 'GRUPO')
        # Nem um DOUBLE_CLICK sem o primeiro clique pode reutilizar a memoria.
        self.clicar_pelo_keymap(chapa, 'DOUBLE_CLICK')
        self.assertTrue(modulo.select_get())
        self.assertEqual(bpy.context.object, modulo)
        self.duplo(chapa)
        self.assertEqual(bpy.context.selected_objects, [chapa])
        self.clicar_pelo_keymap(None, 'PRESS')
        self.clicar_pelo_keymap(chapa, 'PRESS')
        self.assertTrue(modulo.select_get())
        self.assertEqual(bpy.context.object, modulo)

    def test_clique_em_objeto_comum_encerra_individual_do_modulo(self):
        modulo = self.modulo()
        chapa = addon.modulos._chapas_do_conjunto(modulo)[0]
        comum = bpy.data.objects.new('Objeto comum', bpy.data.meshes.new('Malha comum'))
        bpy.context.scene.collection.objects.link(comum)
        self.duplo(chapa)
        self.clicar_pelo_keymap(comum, 'PRESS')
        self.assertEqual(bpy.context.selected_objects, [comum])
        self.assertEqual(chapa.chapa_modo, 'GRUPO')
        self.assertFalse(addon.hud._clique_chapa_hud)
        self.clicar_pelo_keymap(chapa, 'PRESS')
        self.assertEqual(bpy.context.object, modulo)
        self.assertTrue(modulo.select_get())

    def test_shift_no_vazio_preserva_contexto_individual(self):
        modulo = self.modulo()
        chapa = addon.modulos._chapas_do_conjunto(modulo)[0]
        self.duplo(chapa)
        memoria = dict(addon.hud._clique_chapa_hud)
        self.clicar_pelo_keymap(None, 'PRESS', shift=True)
        self.assertEqual(bpy.context.selected_objects, [chapa])
        self.assertEqual(chapa.chapa_modo, 'INDIVIDUAL')
        self.assertEqual(addon.hud._clique_chapa_hud, memoria)

    def test_shift_soma_chapas_individuais_do_mesmo_grupo(self):
        # Pedido do usuario: clique = grupo; duplo = uma chapa dele;
        # Shift+clique em outra chapa do MESMO grupo soma so' ela
        self.addCleanup(addon.hud._clique_chapa_hud.clear)
        primeiro, _segundo = self.dois_modulos()
        a1, a2, a3 = addon.modulos._chapas_do_conjunto(primeiro)[:3]
        bpy.ops.object.select_all(action='DESELECT')
        self.clicar_pelo_keymap(a1, 'PRESS')
        self.assertTrue(primeiro.select_get())
        self.duplo(a1)
        self.assertEqual(set(bpy.context.selected_objects), {a1})
        self.clicar_pelo_keymap(a2, 'PRESS', shift=True)
        self.assertEqual(set(bpy.context.selected_objects), {a1, a2})
        self.assertEqual(bpy.context.object, a2)
        self.assertEqual(a2.chapa_modo, 'INDIVIDUAL')
        self.clicar_pelo_keymap(a3, 'PRESS', shift=True)
        self.assertEqual(set(bpy.context.selected_objects), {a1, a2, a3})
        # Shift+clique na chapa ATIVA tira ela, como o Shift nativo
        self.clicar_pelo_keymap(a3, 'PRESS', shift=True)
        self.assertEqual(set(bpy.context.selected_objects), {a1, a2})

    def test_shift_com_varios_grupos_e_duplo_isola_dentro_da_selecao(self):
        self.addCleanup(addon.hud._clique_chapa_hud.clear)
        primeiro, segundo = self.dois_modulos()
        grupo_a = {primeiro, *primeiro.children_recursive}
        grupo_b = {segundo, *segundo.children_recursive}
        a1 = addon.modulos._chapas_do_conjunto(primeiro)[0]
        b1 = addon.modulos._chapas_do_conjunto(segundo)[1]
        bpy.ops.object.select_all(action='DESELECT')
        # clique no grupo A, Shift+clique no grupo B: os dois grupos
        self.clicar_pelo_keymap(a1, 'PRESS')
        self.clicar_pelo_keymap(b1, 'PRESS', shift=True)
        self.assertEqual(set(bpy.context.selected_objects), grupo_a | grupo_b)
        # Shift+duplo numa chapa de A: so' ela de A; B continua inteiro
        self.duplo(a1, shift=True)
        self.assertEqual(set(bpy.context.selected_objects), {a1} | grupo_b)
        self.assertEqual(bpy.context.object, a1)
        # Shift+duplo numa chapa de B: a1 continua, b1 entra sozinha
        self.duplo(b1, shift=True)
        self.assertEqual(set(bpy.context.selected_objects), {a1, b1})
        # mais um Shift+duplo em A: soma, sem perder ninguem
        a2 = addon.modulos._chapas_do_conjunto(primeiro)[1]
        self.duplo(a2, shift=True)
        self.assertEqual(set(bpy.context.selected_objects), {a1, a2, b1})
        # clique simples sem Shift volta ao grupo inteiro
        self.clicar_pelo_keymap(b1, 'PRESS')
        self.clicar_pelo_keymap(b1, 'CLICK')
        self.assertEqual(set(bpy.context.selected_objects), grupo_b)

    def test_props_do_clique_nao_herdam_o_ultimo_uso(self):
        # o keymap so' preenche o que cita: sem SKIP_SAVE, o toggle de um
        # Shift+clique vazava para o clique simples seguinte
        props = addon.selecao.OBJECT_OT_selecionar.__annotations__
        for nome in ('extend', 'deselect', 'toggle', 'deselect_all',
                     'select_passthrough', 'clique'):
            self.assertIn('SKIP_SAVE', props[nome].keywords.get('options', ()),
                          nome)
        valores = [e[0] for e in addon.selecao._ENTRADAS_KEYMAP]
        self.assertIn('CLICK', valores)

    def test_varios_itens_da_selecao_e_mesmo_valor_para_todos(self):
        primeiro, segundo = self.dois_modulos()
        itens = addon.hud._itens_da_selecao(bpy.context)
        self.assertEqual([i[0] for i in itens], [primeiro, segundo]
                         if itens[0][0] == primeiro else [segundo, primeiro])
        self.assertEqual(len(itens), 2)
        self.assertEqual(addon.gaveta._modo_chapa(bpy.context, primeiro), 'GRUPO')
        projetar = lambda p: Vector((300+p.x*500+p.y*150, 200+p.z*500+p.y*90))
        alvos = []
        caixas = []
        for objeto, modo, chapas in itens:
            geometria = addon.hud._geometria_do_item(objeto, modo, chapas)
            linha = next(l for l in geometria['linhas'] if l['eixo'] == 0)
            a, b = linha['pontos']
            alvo = addon.hud._acertar_linhas_hud(geometria, projetar(a + (b-a)*0.2),
                                             projetar, cantos=False)
            self.assertEqual(alvo['lado'], 'min')
            alvos.append(alvo)
            caixas.append(list(addon.modulos._caixa_de(chapas)[0]))
        self.assertNotEqual(addon.hud._chave_do_alvo(alvos[0]),
                            addon.hud._chave_do_alvo(alvos[1]))
        for alvo in alvos:
            addon.hud._aplicar_valor_hud(bpy.context, alvo, 900.0)
        for (objeto, _m, chapas), lo_antes in zip(itens, caixas):
            self.assertAlmostEqual(objeto.conj_largura_mm, 900.0, places=3)
            lo, hi = addon.modulos._caixa_de(chapas)
            self.assertAlmostEqual(lo[0], lo_antes[0], places=5)

    def test_desenho_da_edicao_multipla_esconde_o_ja_escolhido(self):
        primeiro, segundo = self.dois_modulos()
        itens = addon.hud._itens_da_selecao(bpy.context)
        geometria = addon.hud._geometria_do_item(*itens[0])
        escolhido = dict(next(l for l in geometria['linhas'] if l['eixo'] == 0),
                         lado='min')
        regiao = SimpleNamespace(as_pointer=lambda: 77)
        contexto = SimpleNamespace(region=regiao, object=bpy.context.object,
                                   selected_objects=bpy.context.selected_objects)
        addon.hud._edicao_hud[0] = {'regiao': 77, 'alvo': escolhido,
                                'fase': 'coletar', 'itens': [escolhido],
                                'todos': itens, 'hover': None, 'botoes': []}
        try:
            desenhos = addon.hud._desenhos_hud(contexto)
            self.assertEqual(len(desenhos), 2)
            ja, outro = desenhos
            # o escolhido so' mostra a medida escolhida (as 4 arestas do eixo)
            self.assertEqual(len(ja[0]['linhas']), 4)
            self.assertEqual(ja[1], escolhido)
            self.assertGreater(len(outro[0]['linhas']), 4)
            self.assertIsNone(outro[1])
            # o que ainda precisa de seta e' o que pisca
            self.assertFalse(ja[0].get('pendente'))
            self.assertTrue(outro[0].get('pendente'))
        finally:
            addon.hud._edicao_hud[0] = None

    def test_sem_pergunta_editar_como_e_os_pendentes_piscam(self):
        # Pedido do usuario: a SELECAO diz o que se edita; o pop-up
        # "Editar como? Individual | Grupo" saiu
        for nome in ('_botoes_popup_hud', '_botao_sob_mouse',
                     '_desenhar_popup_hud'):
            self.assertFalse(hasattr(addon, nome), nome)
        fonte = inspect.getsource(addon.hud.OBJECT_OT_arrastar_hud)
        self.assertNotIn("'pergunta'", fonte)    # a fase do pop-up
        self.assertNotIn("'mais'", fonte)
        # piscada: duas, curtas, e apaga
        inicio = addon.hud._piscada_hud[0]
        try:
            addon.hud._piscada_hud[0] = 100.0
            d = addon.hud.DURACAO_PISCADA_HUD
            self.assertEqual(addon.hud._brilho_piscada(100.0), 0.0)
            self.assertAlmostEqual(addon.hud._brilho_piscada(100.0 + d / 4), 1.0)
            self.assertAlmostEqual(addon.hud._brilho_piscada(100.0 + d / 2), 0.0,
                                   places=6)
            self.assertAlmostEqual(addon.hud._brilho_piscada(100.0 + 3 * d / 4), 1.0)
            self.assertEqual(addon.hud._brilho_piscada(100.0 + d + 0.01), 0.0)
            self.assertLessEqual(d, 1.5)
        finally:
            addon.hud._piscada_hud[0] = inicio

    def test_hud_some_durante_mover_girar_escalar(self):
        modulo = self.modulo()
        contexto = SimpleNamespace(
            mode='OBJECT', area=SimpleNamespace(type='VIEW_3D'),
            region=SimpleNamespace(type='WINDOW'), region_data=object())
        addon.hud._hover_hud[1] = {'tipo': 'medida'}
        original = addon.eventos._transformando
        addon.eventos._transformando = lambda: True
        try:
            self.assertFalse(addon.hud._contexto_hud(contexto))
            self.assertFalse(addon.hud._hover_hud)
        finally:
            addon.eventos._transformando = original
        self.assertFalse(addon.eventos._transformando())   # nada rodando aqui
        # a seta sai da geometria atual, nao dos pontos do hover
        geometria = addon.hud._geometria_hud(bpy.context)
        self.assertTrue(all('cantos' in l for l in geometria['linhas']
                            if l['tipo'] == 'medida'))
        self.assertEqual(geometria['objeto'], modulo)

    def test_contorno_nativo_some_no_modulo_e_volta_como_estava(self):
        desligados = addon.eventos._contornos_desligados
        usuario = addon.eventos._contornos_do_usuario
        self.addCleanup(desligados.clear)
        self.addCleanup(usuario.clear)
        novo, a, b = addon.eventos._novo_contorno, frozenset({'A'}), frozenset({'B'})
        # ligado: desliga na edicao e religa ao terminar
        self.assertIs(novo(1, True, a), False)
        self.assertIsNone(novo(1, False, a))
        self.assertIsNone(novo(1, False, b))       # outro modulo: segue
        self.assertIs(novo(1, False, frozenset()), True)
        self.assertIsNone(novo(1, True, frozenset()))
        # quem trabalha sem contorno: nada muda, nem ao terminar
        self.assertIsNone(novo(2, False, a))
        self.assertIsNone(novo(2, True, a))        # religou na mao: fica
        self.assertIsNone(novo(2, True, frozenset()))
        # religado na mao durante a edicao: respeitado ate' trocar
        self.assertIs(novo(3, True, a), False)
        self.assertIsNone(novo(3, True, a))
        self.assertIsNone(novo(3, True, a))
        self.assertIsNone(novo(3, True, frozenset()))
        # os ganchos de verdade tambem rodam aqui: so' as falsas contam
        self.assertFalse({1, 2, 3} & (desligados | set(usuario)))
        # so' modulo/porta escondem; chapa solta continua com o contorno
        modulo = self.modulo()
        camada = bpy.context.view_layer
        for o in camada.objects:
            o.select_set(False)
        self.assertFalse(addon.eventos._grupos_selecionados(camada))
        for o in addon.selecao.familia_de(modulo):
            o.select_set(True)
        self.assertEqual(addon.eventos._grupos_selecionados(camada),
                         frozenset({modulo.name}))
        espacos = [e for j in bpy.context.window_manager.windows
                   for e in addon.eventos._viewports_da_janela(j)]
        if not espacos:
            return
        overlay = espacos[0].overlay
        antes = overlay.show_outline_selected
        self.addCleanup(setattr, overlay, 'show_outline_selected', antes)
        for inicial in (True, False):
            desligados.clear()
            usuario.clear()
            overlay.show_outline_selected = inicial
            addon.eventos.sincronizar_contornos()
            self.assertFalse(overlay.show_outline_selected)
            addon.eventos._devolver_contornos()          # salvar: volta como era
            self.assertEqual(overlay.show_outline_selected, inicial)
            addon.eventos._retomar_contornos()
            self.assertFalse(overlay.show_outline_selected)
            for o in camada.objects:
                o.select_set(False)
            addon.eventos.sincronizar_contornos()
            self.assertEqual(overlay.show_outline_selected, inicial)
            for o in addon.selecao.familia_de(modulo):
                o.select_set(True)

    def test_selecao_mista_devolve_contorno_e_vincula_material_do_objeto_comum(self):
        # Regressao 358: o modulo ocultava tambem o feedback do mestre nativo.
        e = addon.eventos
        modulo = self.modulo()
        pecas = addon.modulos._chapas_do_conjunto(modulo)
        comum = bpy.data.objects.new('Origem comum do material', pecas[0].data.copy())
        bpy.context.scene.collection.objects.link(comum)
        material = bpy.data.materials.new('Material de objeto comum')
        comum.data.materials.clear()
        comum.data.materials.append(material)
        addon.hud._selecionar_chapa_hud(bpy.context, pecas[0])
        overlay = next(e._viewports_da_janela(bpy.context.window)).overlay
        e.sincronizar_contornos(devolver=True)
        antes = overlay.show_outline_selected
        opcao = addon.opcoes._opcao('ocultar_contorno_grupo')
        try:
            addon.opcoes._definir_opcao('ocultar_contorno_grupo', True)
            e._contornos_do_usuario.clear()
            overlay.show_outline_selected = True
            e.sincronizar_contornos()
            self.assertFalse(overlay.show_outline_selected)
            comum.select_set(True)
            # Deve bastar ESTAR selecionado; o objeto comum nao precisa ser ativo.
            e.sincronizar_contornos()
            self.assertTrue(overlay.show_outline_selected)
            bpy.context.view_layer.objects.active = comum
            selecionados = {o.name for o in bpy.context.selected_objects}
            e.sincronizar_contornos()
            self.assertTrue(overlay.show_outline_selected)
            self.assertEqual({o.name for o in bpy.context.selected_objects}, selecionados)
            self.assertEqual(bpy.ops.object.make_links_data(type='MATERIAL'), {'FINISHED'})
            self.assertTrue(all(o.data.materials[0] == material for o in pecas))
            comum.select_set(False)
            bpy.context.view_layer.objects.active = modulo
            e.sincronizar_contornos()
            self.assertFalse(overlay.show_outline_selected)
            for o in bpy.context.selected_objects:
                o.select_set(False)
            comum.select_set(True)
            bpy.context.view_layer.objects.active = comum
            e.sincronizar_contornos()
            self.assertTrue(overlay.show_outline_selected)
        finally:
            for o in bpy.context.selected_objects:
                o.select_set(False)
            e.sincronizar_contornos(devolver=True)
            e._contornos_do_usuario.clear()
            addon.opcoes._definir_opcao('ocultar_contorno_grupo', opcao)
            overlay.show_outline_selected = antes

    def test_contorno_misto_respeita_usuario_e_componentes_do_modulo(self):
        e = addon.eventos
        modulo = self.modulo()
        componente = bpy.data.objects.new('Componente sem marca', None)
        bpy.context.scene.collection.objects.link(componente)
        componente.parent = modulo
        componente.select_set(True)
        curva = bpy.data.objects.new('Curva comum', bpy.data.curves.new('Curva comum', 'CURVE'))
        bpy.context.scene.collection.objects.link(curva)
        overlay = next(e._viewports_da_janela(bpy.context.window)).overlay
        e.sincronizar_contornos(devolver=True)
        antes = overlay.show_outline_selected
        opcao = addon.opcoes._opcao('ocultar_contorno_grupo')
        try:
            addon.opcoes._definir_opcao('ocultar_contorno_grupo', True)
            for inicial in (True, False):
                e.sincronizar_contornos(devolver=True)
                e._contornos_do_usuario.clear()
                overlay.show_outline_selected = inicial
                e.sincronizar_contornos()
                self.assertFalse(overlay.show_outline_selected)
                curva.select_set(True)
                e.sincronizar_contornos()
                self.assertEqual(overlay.show_outline_selected, inicial)
                curva.select_set(False)
                e.sincronizar_contornos()
                self.assertFalse(overlay.show_outline_selected)
        finally:
            for o in bpy.context.selected_objects:
                o.select_set(False)
            e.sincronizar_contornos(devolver=True)
            e._contornos_do_usuario.clear()
            addon.opcoes._definir_opcao('ocultar_contorno_grupo', opcao)
            overlay.show_outline_selected = antes

    def test_origens_grupo_restaura_flags_nativas_e_opcao_muda_na_hora(self):
        e = addon.eventos
        modulo = self.modulo()
        espacos = [s for j in bpy.context.window_manager.windows for s in e._viewports_da_janela(j)]
        self.assertTrue(espacos)
        overlay = espacos[0].overlay
        nomes = ('show_object_origins', 'show_object_origins_all')
        antes = [getattr(overlay, n) for n in nomes]
        opcao = addon.opcoes._opcao('ocultar_origens_grupo')
        try:
            for inicial in [(True, False), (True, True), (False, False), (False, True)]:
                e._origens_ocultas.clear(); e._origens_do_usuario.clear()
                for n, v in zip(nomes, inicial): setattr(overlay, n, v)
                addon.opcoes._definir_opcao('ocultar_origens_grupo', True)
                self.assertEqual([getattr(overlay, n) for n in nomes], [False, False])
                e._devolver_contornos()   # salvar/desligar devolve o estado nativo
                self.assertEqual([getattr(overlay, n) for n in nomes], list(inicial))
                e._retomar_contornos()
                self.assertFalse(overlay.show_object_origins)
                addon.opcoes._definir_opcao('ocultar_origens_grupo', False)
                self.assertEqual([getattr(overlay, n) for n in nomes], list(inicial))
                addon.opcoes._definir_opcao('ocultar_origens_grupo', True)
                chapa = addon.modulos._chapas_do_conjunto(modulo)[0]
                addon.hud._selecionar_chapa_hud(bpy.context, chapa, individual=True)
                e.sincronizar_contornos()
                self.assertEqual([getattr(overlay, n) for n in nomes], list(inicial))
                addon.hud._selecionar_chapa_hud(bpy.context, chapa)
        finally:
            for o in bpy.context.view_layer.objects: o.select_set(False)
            e.sincronizar_contornos(devolver=True)
            e._origens_ocultas.clear(); e._origens_do_usuario.clear()
            for n, v in zip(nomes, antes): setattr(overlay, n, v)
            addon.opcoes._definir_opcao('ocultar_origens_grupo', opcao)

    def test_origens_respeita_viewport_e_intervencao_manual(self):
        e = addon.eventos
        a = SimpleNamespace(as_pointer=lambda: -777, overlay=SimpleNamespace(
            show_object_origins=True, show_object_origins_all=True))
        b = SimpleNamespace(as_pointer=lambda: -778, overlay=SimpleNamespace(
            show_object_origins=False, show_object_origins_all=False))
        try:
            grupo = frozenset({'Modulo A'})
            e._sincronizar_origens(a, grupo); e._sincronizar_origens(b, grupo)
            self.assertFalse(a.overlay.show_object_origins)
            a.overlay.show_object_origins = True
            e._sincronizar_origens(a, grupo)
            self.assertTrue(a.overlay.show_object_origins)  # usuario manda nesta selecao
            e._sincronizar_origens(a, grupo, devolver=True)
            e._sincronizar_origens(a, grupo)
            self.assertTrue(a.overlay.show_object_origins)  # salvar nao perde a escolha
            e._sincronizar_origens(a, frozenset({'Modulo B'}))
            self.assertFalse(a.overlay.show_object_origins)
            e._sincronizar_origens(a, frozenset()); e._sincronizar_origens(b, frozenset())
            self.assertTrue(a.overlay.show_object_origins)
            self.assertTrue(a.overlay.show_object_origins_all)
            self.assertFalse(b.overlay.show_object_origins)
            self.assertFalse(b.overlay.show_object_origins_all)  # nunca ligar o que nao era nosso
        finally:
            for ptr in (-777, -778):
                for n in ('show_object_origins', 'show_object_origins_all'):
                    e._origens_ocultas.discard((ptr,n)); e._origens_do_usuario.pop((ptr,n),None)

    def test_origens_somem_em_todos_os_grupos_mas_nao_na_folha_individual(self):
        marcas = (addon.chapas.MARCA_CONJUNTO, addon.chapas.MARCA_PORTAS,
                  addon.gavetas.MARCA_GRUPO, addon.prateleiras.MARCA_GRUPO,
                  addon.divisorias.MARCA_GRUPO)
        for marca in (*marcas, addon.chapas.MARCA_FOLHA):
            obj = bpy.data.objects.new('Grupo para origens', None)
            bpy.context.scene.collection.objects.link(obj)
            obj[marca] = 1
            bpy.context.view_layer.update()
            obj.select_set(True)
            grupos = addon.eventos._grupos_selecionados(bpy.context.view_layer, marcas)
            self.assertEqual(grupos, frozenset({obj.name}) if marca in marcas else frozenset())
            obj.select_set(False)

    def test_menu_oferece_ocultar_e_mostrar_origens_no_grupo(self):
        g = addon.gaveta
        tela = bpy.context.screen
        antes = {n:tela.get(n) for n in (g._CHAVE_OPCOES, g._CHAVE_SUSPENSO)}
        try:
            tela[g._CHAVE_OPCOES] = 1
            tela[g._CHAVE_SUSPENSO] = 'ocultar_origens_grupo'
            widgets = g._rodape_gaveta(bpy.context, 12, 400)
            self.assertTrue(any(w[4] == 'Origens no grupo' for w in widgets))
            escolhas = [w for w in widgets if w[5] and w[5][:2] == ('escolha','ocultar_origens_grupo')]
            self.assertEqual({(w[4],w[5][2]) for w in escolhas}, {('Ocultar',True),('Mostrar',False)})
            prop = addon.opcoes.CabinetCreatorPreferences.bl_rna.properties['ocultar_origens_grupo']
            self.assertTrue(prop.default)
        finally:
            for n, v in antes.items():
                if v is None:
                    if n in tela: del tela[n]
                else: tela[n] = v

    def test_letras_somem_de_longe_e_seta_tem_tamanho_fixo(self):
        self.modulo()
        geometria = addon.hud._geometria_hud(bpy.context)
        original = addon.hud._projetar_hud
        self.addCleanup(setattr, addon.hud, '_projetar_hud', original)
        contexto = SimpleNamespace(preferences=bpy.context.preferences)

        def vista(pixels_por_metro):
            addon.hud._projetar_hud = lambda _c, p: Vector(
                (p.x * pixels_por_metro + p.y * 0.3 * pixels_por_metro,
                 p.z * pixels_por_metro + p.y * 0.2 * pixels_por_metro))

        vista(500)          # perto: o modulo ocupa centenas de pixels
        self.assertEqual({r[0] for r in addon.hud._rotulos_hud(
            contexto, geometria, None)}, {'A1', 'A2', 'A3'})
        vista(40)           # longe: poucos pixels, as letras empilhavam
        self.assertLess(addon.hud._tamanho_na_tela(contexto, geometria),
                        addon.hud.FATOR_ROTULO_HUD * addon.opcoes._opcao('hud_tamanho_rotulo'))
        self.assertEqual(addon.hud._rotulos_hud(contexto, geometria, None), [])
        alvo = next(l for l in geometria['linhas'] if l.get('letra') == 'A')
        self.assertEqual([r[0] for r in addon.hud._rotulos_hud(
            contexto, geometria, alvo)], ['A2'])      # a acesa fica
        # O tamanho de hoje e' o TETO; aresta mais curta que a seta
        # (a E de 18 mm, print do usuario) leva a seta so' ate' a ponta
        # dela -- inteira: ponto e haste nunca passam da aresta.
        cheia = addon.hud.COMPRIMENTO_SETA_HUD
        for comprimento in (6, 10, 40, cheia, 800):
            pontos = addon.hud._triangulos_seta_hud(
                Vector((0, 0)), Vector((comprimento, 0)), 1.0)
            esperado = min(cheia, comprimento)
            self.assertAlmostEqual(max(p.x for p in pontos), esperado,
                                   msg=comprimento)
            self.assertGreaterEqual(min(p.x for p in pontos), -esperado)
        # no tamanho cheio a seta e' a de antes (ponta 12, haste 2.5)
        pontos = addon.hud._triangulos_seta_hud(Vector((0, 0)), Vector((800, 0)),
                                            1.0)
        self.assertAlmostEqual(max(p.y for p in pontos), addon.hud.ASA_SETA_HUD)

    def test_letras_ficam_fora_da_peca_e_nao_se_encostam(self):
        modulo = self.modulo()
        chapa = addon.modulos._chapas_do_conjunto(modulo)[0]
        original = addon.hud._projetar_hud
        self.addCleanup(setattr, addon.hud, '_projetar_hud', original)
        # vista obliqua de cima, como a da chapa deitada na referencia
        addon.hud._projetar_hud = lambda _c, p: Vector(
            (300 + p.x * 400 - p.y * 250, 200 + p.z * 400 + p.y * 120 + p.x * 60))
        contexto = SimpleNamespace(preferences=bpy.context.preferences)
        tamanho = addon.opcoes._opcao('hud_tamanho_rotulo')

        def casco(pontos):
            pontos = sorted(set((round(p.x, 4), round(p.y, 4)) for p in pontos))
            def volta(seq):
                h = []
                for p in seq:
                    while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (p[1] - h[-2][1])
                                           - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0])) <= 0:
                        h.pop()
                    h.append(p)
                return h
            return volta(pontos)[:-1] + volta(pontos[::-1])[:-1]

        def dentro(p, h):
            return all((b[0] - a[0]) * (p.y - a[1]) - (b[1] - a[1]) * (p.x - a[0]) > 0
                       for a, b in zip(h, h[1:] + h[:1]))

        for geometria in (addon.hud._geometria_hud(bpy.context),
                          addon.hud._geometria_do_item(chapa, 'INDIVIDUAL', [chapa])):
            rotulos = addon.hud._rotulos_hud(contexto, geometria, None)
            self.assertGreaterEqual(len(rotulos), 3)
            h = casco([addon.hud._projetar_hud(None, c) for c in geometria['cantos']])
            centro = sum((Vector(p) for p in h), Vector((0, 0))) / len(h)
            for letra, ponto, _aceso in rotulos:
                # nem o desenho da letra (meio tamanho para dentro) encosta
                borda = ponto + (centro - ponto).normalized() * tamanho * 0.4
                self.assertFalse(dentro(borda, h), '%s caiu sobre a peca' % letra)
            for i, (_l, a, _x) in enumerate(rotulos):
                for _m, b, _y in rotulos[:i]:
                    self.assertGreaterEqual((a - b).length, tamanho * 1.3 - 1e-6)

    # ------------------------------------------- correntes de adjacencia
    def piso_e_lateral(self, folga_mm=10.0):
        """A cena da 1a print do usuario: piso deitado e lateral em pe' a
        `folga_mm` da ponta dele, com a adjacencia memorizada."""
        piso = addon.chapas.nova_chapa('Piso', 600.0, 400.0, 18.0, (0, 0, 9.0),
                                (0, 0, 0), bpy.context)
        lateral = addon.chapas.nova_chapa('Lateral', 720.0, 400.0, 18.0,
                                   (300.0 + folga_mm + 9.0, 0, 360.0),
                                   (0, 90.0, 0), bpy.context)
        bpy.context.view_layer.update()
        self.assertGreater(addon.chapas.detectar_adjacencia([piso, lateral]), 0)
        return piso, lateral

    def caixote_aberto(self, recuo_mm=250.0):
        """A cena da 3a print: tampo e base encurtados, longe da lateral
        direita -- 4 pontas separadas (tampo e base, frente e tras)."""
        modulo = self.modulo()
        chapas = addon.modulos._chapas_do_conjunto(modulo)
        ordem = sorted(chapas, key=lambda o: o.matrix_world.translation.z)
        base, tampo = ordem[0], ordem[-1]
        for chapa in (base, tampo):
            addon.hud._redimensionar_chapa_ancorada(
                chapa, 0, chapa.chapa_largura_mm - recuo_mm, 'min')
        bpy.context.view_layer.update()
        direita = max((c for c in chapas if c not in (base, tampo)),
                      key=lambda o: o.matrix_world.translation.x)
        return modulo, base, tampo, direita

    def afastar(self, peca, metros, eixo=0):
        peca.location[eixo] += metros
        bpy.context.view_layer.update()

    def test_corrente_liga_os_dois_vertices_da_junta(self):
        # Soldados com 10 mm de folga: ESSA e' a origem da solda. A lateral
        # anda mais 10 mm -> desvio de 10 mm, a corrente aparece
        piso, lateral = self.piso_e_lateral(10.0)
        self.assertEqual(addon.solda._ligacoes_adjacencia([piso, lateral]), [])
        self.afastar(lateral, 0.010)
        ligacoes = addon.solda._ligacoes_adjacencia([piso, lateral])
        self.assertEqual(len(ligacoes), 1)
        ligacao = ligacoes[0]
        self.assertEqual((ligacao['a'], ligacao['b']), (piso, lateral))
        self.assertAlmostEqual(ligacao['desvio'], 0.010, places=5)
        # Uma junta conserva somente um par real, mesmo com outras quinas proximas.
        self.assertEqual(len(ligacao['pares']), 1)
        for p, q, _assinatura in ligacao['pares']:
            self.assertAlmostEqual(p.x, 0.300, places=5)
            self.assertAlmostEqual(p.z, 0.0, places=5)
            self.assertAlmostEqual((q - p).length, 0.020, places=5)
        self.assertIn(round(ligacao['pares'][0][0].y,3),(-0.2,0.2))
        # vale para qualquer das duas pecas como item da HUD
        self.assertEqual(len(addon.solda._ligacoes_adjacencia([lateral])), 1)

    def test_corrente_so_aparece_com_desvio_maior_que_5mm(self):
        # Pedido do usuario: o que conta e' o DESVIO da origem da solda;
        # na viewport a corrente so' aparece acima de 5 mm, mas o botao
        # da gaveta ja' acende com qualquer desvio
        piso, lateral = self.piso_e_lateral(0.0)
        self.assertAlmostEqual(addon.solda.LIMIAR_CORRENTE_VIEWPORT, 0.005)
        self.afastar(lateral, 0.003)
        self.assertEqual(addon.solda._ligacoes_adjacencia([piso, lateral]), [])
        self.assertEqual(len(addon.solda._pontas_fora_do_lugar([piso, lateral])), 1)
        self.afastar(lateral, 0.003)          # 6 mm
        self.assertEqual(len(addon.solda._ligacoes_adjacencia([piso, lateral])), 1)
        # sem teto: longe continua corrente
        self.afastar(lateral, 0.3)
        self.assertEqual(len(addon.solda._ligacoes_adjacencia([piso, lateral])), 1)

    def test_alt_mostra_todas_as_quinas_soldadas_com_corrente_e_regua(self):
        # Alt mostra todos os pares de objetos fora da origem, uma corrente por par.
        modulo, base, tampo, direita = self.caixote_aberto()
        self.selecionar(modulo, *addon.modulos._chapas_do_conjunto(modulo), ativo=modulo)
        # cada funcao no modulo dela (o add-on e' um pacote)
        for m, n in ((addon.solda, '_correntes_visiveis'),
                     (addon.hud, '_contexto_hud'),
                     (addon.gaveta, '_eh_area_gaveta'),
                     (addon.hud, '_projetar_hud')):
            self.addCleanup(setattr, m, n, getattr(m, n))
        addon.solda._correntes_visiveis = lambda: True
        addon.hud._contexto_hud = lambda _c: True
        addon.gaveta._eh_area_gaveta = lambda _c: False
        addon.hud._projetar_hud = lambda _c, p: Vector((p.x * 1000, p.z * 1000))
        contexto = _ContextoRegiao()
        contexto.region_data = object()
        correntes = addon.solda._correntes_hud(contexto)
        self.assertEqual(len(correntes), 2)          # tampo-direita e base-direita
        self.assertEqual(len({frozenset((c['a'],c['b'])) for c in correntes}),2)
        self.assertEqual({c['a'] for c in correntes}, {base, tampo})
        # a regua move a que se afastou... aqui quem encolheu foram tampo e
        # base; a lateral tem as duas soldas fora, entao e' ela
        self.assertTrue(all(c['movel'] == direita for c in correntes))
        botoes = addon.solda._botoes_da_corrente(contexto, correntes[0])
        self.assertLess(botoes['corrente'].x, botoes['regua'].x)
        self.assertEqual(addon.solda._botao_corrente_sob_mouse(
            contexto, botoes['regua'])[1], 'regua')
        self.assertEqual(addon.solda._botao_corrente_sob_mouse(
            contexto, botoes['corrente'])[1], 'corrente')
        self.assertFalse(any(hasattr(m, '_corrente_da_vista')
                             for m in addon._MODULOS))

    def prateleira_solta(self, x_mm=800.0, z_mm=300.0):
        """Prateleira fora do modulo, longe de tudo (nada ao alcance)."""
        prateleira = addon.chapas.nova_chapa('Prateleira', 400.0, 300.0, 18.0,
                                      (x_mm, 0, z_mm), (0, 0, 0), bpy.context)
        bpy.context.view_layer.update()      # matrix_world defasado
        return prateleira

    def test_desagregar_solta_todas_as_quinas_de_uma_vez(self):
        # Regra nova: a corrente clicada vale pelo OBJETO inteiro
        modulo, base, tampo, direita = self.caixote_aberto()
        corrente = addon.solda._ligacoes_adjacencia(
            addon.modulos._chapas_do_conjunto(modulo))[0]
        peca = corrente['a']
        self.assertIn(peca, (base, tampo))
        mundo = peca.matrix_world.copy()
        self.assertTrue(addon.solda.agregado(peca))
        self.assertEqual(bpy.ops.object.cabinet_desassociar(chapa=peca.name),
                         {'FINISHED'})
        # nenhuma quina dela segue ligada, em nenhum sentido
        self.assertFalse(addon.solda.agregado(peca))
        self.assertEqual(addon.solda._ligados_a(peca), set())
        # saiu do modulo sem sair do lugar; as outras seguem la'
        self.assertIsNone(peca.parent)
        for a, b in zip(peca.matrix_world, mundo):
            self.assertLess((a - b).length, 1e-6)
        outra = tampo if peca is base else base
        self.assertEqual(outra.parent, modulo)
        self.assertTrue(addon.solda.agregado(outra))
        # de novo: nada a fazer
        self.assertEqual(bpy.ops.object.cabinet_desassociar(chapa=peca.name),
                         {'CANCELLED'})

    def selecionar(self, *objs, ativo=None):
        bpy.ops.object.select_all(action='DESELECT')
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = ativo

    def test_resetar_com_a_chapa_ativa_move_a_chapa(self):
        # Print do usuario: a lateral afastada do nicho e SELECIONADA
        # sozinha -> ela volta a origem da solda; o resto nao se mexe
        modulo = self.modulo()
        chapas = addon.modulos._chapas_do_conjunto(modulo)
        direita = max(chapas, key=lambda o: o.matrix_world.translation.x)
        antes = direita.matrix_world.copy()
        fixos = {o.name: o.matrix_world.copy() for o in chapas if o != direita}
        self.selecionar(direita, ativo=direita)
        self.assertIsNone(addon.solda._estado_resetar(bpy.context))   # na origem
        self.afastar(direita, 0.2)
        self.assertIs(addon.solda._estado_resetar(bpy.context), True)  # azul
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(),
                         {'FINISHED'})
        for a, b in zip(direita.matrix_world, antes):
            self.assertLess((a - b).length, 1e-5)
        for o in chapas:
            if o != direita:
                for a, b in zip(o.matrix_world, fixos[o.name]):
                    self.assertLess((a - b).length, 1e-6, o.name)
        self.assertIsNone(addon.solda._estado_resetar(bpy.context))

    def test_resetar_que_muda_a_medida_pergunta_antes(self):
        # Caso extremo do usuario: o modulo mudou e a chapa so' volta as
        # soldas mudando de medida -> pergunta; "Sim" estica, "Nao" nada
        modulo, base, tampo, direita = self.caixote_aberto()
        # o tampo vai a solda da esquerda (onde ja' esta') e da direita
        # (250 mm adiante): so' esticando
        self.selecionar(tampo, ativo=tampo)
        largura = tampo.chapa_largura_mm
        plano = addon.solda._plano_reset_chapa(tampo)
        self.assertTrue(plano['muda_medida'])
        self.assertIn('Mover mesmo assim', addon.solda.PERGUNTA_RESET)
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(),
                         {'CANCELLED'})
        self.assertEqual(addon.solda._pergunta_reset[0], tampo.name)
        self.assertAlmostEqual(tampo.chapa_largura_mm, largura)
        # "Nao"
        bpy.ops.object.cabinet_resetar_distancia(cancelar=True)
        self.assertEqual(addon.solda._pergunta_reset[0], '')
        self.assertAlmostEqual(tampo.chapa_largura_mm, largura)
        # "Sim, mover"
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(
            chapa=tampo.name, forcar=True), {'FINISHED'})
        self.assertAlmostEqual(tampo.chapa_largura_mm, largura + 250.0, places=2)
        self.assertEqual(addon.solda._pontas_fora_do_lugar([tampo]), [])

    def test_resetar_com_o_modulo_ativo_o_modulo_se_adapta(self):
        # Modulo ativo: o GRUPO se adapta a chapa afastada -- as pontas
        # soldadas esticam ate' ela e o modulo cresce; a chapa fica
        modulo = self.modulo()
        chapas = addon.modulos._chapas_do_conjunto(modulo)
        direita = max(chapas, key=lambda o: o.matrix_world.translation.x)
        largura = modulo.conj_largura_mm
        self.afastar(direita, 0.2)
        lateral = direita.matrix_world.copy()
        self.selecionar(modulo, *chapas, ativo=modulo)
        self.assertIs(addon.solda._estado_resetar(bpy.context), True)
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(),
                         {'FINISHED'})
        for a, b in zip(direita.matrix_world, lateral):
            self.assertLess((a - b).length, 1e-5)
        self.assertEqual(addon.solda._pontas_fora_do_lugar(chapas), [])
        self.assertAlmostEqual(modulo.conj_largura_mm, largura + 200.0, places=1)
        # a regua de uma linha (viewport) vale pela peca da linha
        self.afastar(direita, 0.05)
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(
            chapa=direita.name), {'FINISHED'})
        self.assertEqual(addon.solda._pontas_fora_do_lugar(chapas), [])

    def solda_do_tampo(self):
        """Nicho agrupado: (modulo, tampo, lateral direita, ponta do tampo
        soldada na lateral)."""
        modulo = self.modulo()
        chapas = addon.modulos._chapas_do_conjunto(modulo)
        tampo = max(chapas, key=lambda o: o.matrix_world.translation.z)
        direita = max((c for c in chapas if c is not tampo),
                      key=lambda o: o.matrix_world.translation.x)
        ponta = next(p for p in addon.chapas.PONTAS
                     if addon.solda._vizinho_da_ponta(tampo, p) == direita)
        return modulo, tampo, direita, ponta

    def _ancoras_legadas_da_ligacao(self, C, ponta, N):
        # Reproduz as duas quinas antigas sem depender do limite novo de cadastro.
        s=addon.solda;eixo=0 if ponta.startswith('x') else 1
        inversa=C.matrix_world.inverted()
        extremo=(max if ponta.endswith('pos') else min)(v.co[eixo] for v in C.data.vertices)
        candidatos=[]
        for sc,p in s._ancoras_da_malha(C):
            local=inversa@p
            if abs(local[eixo]-extremo)>1e-5:continue
            sn,q=min(s._ancoras_da_malha(N),key=lambda a:(a[1]-p).length_squared)
            candidatos.append(((q-p).length_squared,sc,sn,local))
        escolhidas=[];locais=[]
        for _d,sc,sn,local in sorted(candidatos,key=lambda a:a[0]):
            if any((local.xy-p.xy).length<1e-5 for p in locais):continue
            escolhidas.append((sc,sn));locais.append(local)
            if len(escolhidas)==2:break
        self.assertEqual(len(escolhidas),2)
        return escolhidas

    def vertice_do_outro_lado(self, N, assinatura, sentido, espessura):
        """O vertice de N do outro lado da espessura dele."""
        alvo = addon.solda._vertice_da_assinatura(N, assinatura) + sentido * espessura
        return min((a + b + c for a in '+-' for b in '+-' for c in '+-'),
                   key=lambda s: (addon.solda._vertice_da_assinatura(N, s) - alvo).length)

    # Regressao (era BUG, corrigido na 304): a bolinha projetava em Python os
    # vertices da peca a cada movimento; agora e' o cursor + snap nativo.
    def test_ancora_arrastada_pelo_snap_nativo(self):
        S = addon.solda
        self.assertIn(S.OBJECT_OT_mover_ancora_solda, addon.CLASSES)
        self.assertIn(S.OBJECT_OT_confirmar_ancora_solda, addon.CLASSES)
        self.assertEqual(bpy.ops.object.cabinet_confirmar_ancora_solda(), {'CANCELLED'})
        self.assertEqual(S.OBJECT_OT_arrastar_ancora.invoke(
            SimpleNamespace(chapa='sem chapa', ponta='x_pos', indice=0, lado='b'),
            bpy.context, None), {'CANCELLED'})
        modulo, tampo, direita, ponta = self.solda_do_tampo()
        ancoras = S._ancoras_da_ligacao(tampo, ponta, direita)
        _f, u, _e = S._folga_com_sinal(tampo, ponta, direita)
        sentido = u if ponta.endswith('pos') else -u
        fora = self.vertice_do_outro_lado(direita, ancoras[0][1], sentido,
                                          direita.chapa_espessura_mm / 1000.0)
        cena = bpy.context.scene
        cursor = cena.cursor.location.copy()
        contexto = SimpleNamespace(
            visible_objects=bpy.context.visible_objects, scene=cena,
            region=SimpleNamespace(as_pointer=lambda: 1),
            area=SimpleNamespace(as_pointer=lambda: 2),
            space_data=SimpleNamespace(overlay=SimpleNamespace(show_cursor=True)))
        self.addCleanup(S._terminar_ancora_solda)
        parametros = S._preparar_ancora_solda(contexto, tampo, ponta, direita, 0, 'b')
        self.assertEqual(parametros['snap_elements'], {'VERTEX'})
        self.assertTrue(parametros['cursor_transform'])
        self.assertTrue(tampo.hide_select)          # so' o lado 'b' e' alvo
        self.assertFalse(direita.hide_select)
        cena.cursor.location = S._vertice_da_assinatura(direita, fora)
        self.assertEqual(bpy.ops.object.cabinet_confirmar_ancora_solda(), {'FINISHED'})
        self.assertIsNone(S._arraste_ancora[0])
        self.assertFalse(tampo.hide_select)
        self.assertLess((cena.cursor.location - cursor).length, 1e-6)
        self.assertEqual(S._ancoras_gravadas(tampo, ponta), [(ancoras[0][0], fora)])

    def test_ancoras_de_fabrica_trocar_e_apagar(self):
        modulo, tampo, direita, ponta = self.solda_do_tampo()
        self.assertIsNone(addon.solda._ancoras_gravadas(tampo, ponta))
        ancoras = addon.solda._ancoras_da_ligacao(tampo, ponta, direita)
        self.assertEqual(len(ancoras), 1)
        for sc, sn in ancoras:                    # de fabrica: encostados
            self.assertLess((addon.solda._vertice_da_assinatura(tampo, sc)
                             - addon.solda._vertice_da_assinatura(direita, sn)).length,
                            1e-5)
        # arrastar a bolinha do lado do vizinho ('b') para outro vertice
        _f, u, _e = addon.solda._folga_com_sinal(tampo, ponta, direita)
        sentido = u if ponta.endswith('pos') else -u
        fora = self.vertice_do_outro_lado(direita, ancoras[0][1], sentido,
                                          direita.chapa_espessura_mm / 1000.0)
        op = SimpleNamespace(chapa=tampo.name, ponta=ponta, indice=0, lado='b',
                             report=lambda *a: None)
        self.assertEqual(addon.solda.OBJECT_OT_arrastar_ancora._gravar(op, fora),
                         {'FINISHED'})
        self.assertEqual(addon.solda._ancoras_gravadas(tampo, ponta),
                         [(ancoras[0][0], fora)])
        # mesma ancora de novo: nada a gravar
        self.assertEqual(addon.solda.OBJECT_OT_arrastar_ancora._gravar(op, fora),
                         {'CANCELLED'})
        # so' troca a ancora: a geometria nao mexeu, mas a solda saiu da
        # origem (a regua acende)
        self.assertTrue(addon.solda._pontas_fora_do_lugar([tampo]))
        # soldar de novo (ou desassociar) volta as ancoras de fabrica
        addon.chapas.detectar_adjacencia(addon.modulos._chapas_do_conjunto(modulo))
        self.assertIsNone(addon.solda._ancoras_gravadas(tampo, ponta))
        addon.solda._gravar_ancoras(tampo, ponta, [(ancoras[0][0], fora)])
        addon.solda.desassociar(tampo, direita)
        self.assertNotIn('adj_%s_ancoras' % ponta, tampo)

    def test_regua_rejeita_destinos_contraditorios_sem_alterar_modulo(self):
        # Regressao (era BUG, corrigido na 347): a regua aceitava a mesma
        # quina em dois destinos e ainda remontava portas e dobradicas.
        modulo, tampo, direita, ponta = self.solda_do_tampo()
        pares = addon.solda._ancoras_da_ligacao(tampo, ponta, direita)
        sc, sn = pares[0]
        oposto = addon.solda._parceiro_espessura(direita, sn)
        addon.solda._gravar_ancoras(tampo, ponta, [(sc, sn), (sc, oposto)])
        antes = {o.name: (o.matrix_world.copy(), [tuple(v.co) for v in o.data.vertices])
                 for o in addon.modulos._chapas_do_conjunto(modulo)}
        for alvo in (tampo, direita):
            self.selecionar(alvo, ativo=alvo)
            with patch.object(addon.solda, '_atualizar_modulo',
                              side_effect=AssertionError('Atualizou junta inviavel')):
                self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(
                    chapa=alvo.name, forcar=True), {'CANCELLED'})
            for nome, (matriz, pontos) in antes.items():
                self.assertEqual(bpy.data.objects[nome].matrix_world, matriz)
                self.assertEqual([tuple(v.co) for v in bpy.data.objects[nome].data.vertices], pontos)

    def test_regua_do_grupo_valida_todas_as_juntas_antes_da_primeira_escrita(self):
        modulo, base, tampo, direita = self.caixote_aberto()
        ponta = next(p for p in addon.chapas.PONTAS
                     if addon.solda._vizinho_da_ponta(tampo, p) == direita)
        sc, sn = addon.solda._ancoras_da_ligacao(tampo, ponta, direita)[0]
        addon.solda._gravar_ancoras(tampo, ponta, [
            (sc, sn), (sc, addon.solda._parceiro_espessura(direita, sn))])
        antes = [tuple(v.co) for v in base.data.vertices]
        matriz = base.matrix_world.copy()
        with self.assertRaisesRegex(ValueError, 'destinos diferentes'):
            addon.solda.resetar_pontas([(base, ponta), (tampo, ponta)])
        self.assertEqual(base.matrix_world, matriz)
        self.assertEqual([tuple(v.co) for v in base.data.vertices], antes)

    def test_regua_leva_aos_vertices_ancorados_mesmo_torta(self):
        # Print 1 do usuario: uma ancora na quina de FORA da lateral e a
        # outra na de dentro -> a ponta do tampo fica torta, na diagonal,
        # com a espessura intacta; a lateral nao se mexe
        modulo, tampo, direita, ponta = self.solda_do_tampo()
        ancoras = self._ancoras_legadas_da_ligacao(tampo, ponta, direita)
        _f, u, _e = addon.solda._folga_com_sinal(tampo, ponta, direita)
        sentido = u if ponta.endswith('pos') else -u
        fora = self.vertice_do_outro_lado(direita, ancoras[0][1], sentido,
                                          direita.chapa_espessura_mm / 1000.0)
        novas = [(ancoras[0][0], fora), ancoras[1]]
        addon.solda._gravar_ancoras(tampo, ponta, novas)
        lateral = direita.matrix_world.copy()
        sc0, sc1 = ancoras[0][0], ancoras[1][0]
        parceiro = sc0[:2] + ('-' if sc0[2] == '+' else '+')
        espessura = (addon.solda._vertice_da_assinatura(tampo, sc0)
                     - addon.solda._vertice_da_assinatura(tampo, parceiro)).length
        self.selecionar(modulo, *addon.modulos._chapas_do_conjunto(modulo), ativo=modulo)
        self.assertIs(addon.solda._estado_resetar(bpy.context), True)
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(),
                         {'FINISHED'})
        for sc, sn in novas:
            self.assertLess((addon.solda._vertice_da_assinatura(tampo, sc)
                             - addon.solda._vertice_da_assinatura(direita, sn)).length,
                            1e-4, sc)
        # torta: os dois cantos da ponta nao estao mais na mesma reta
        a = addon.solda._vertice_da_assinatura(tampo, sc0)
        b = addon.solda._vertice_da_assinatura(tampo, sc1)
        self.assertGreater(abs((a - b).dot(sentido)), 0.005)
        # o outro lado da espessura veio junto
        self.assertAlmostEqual((a - addon.solda._vertice_da_assinatura(
            tampo, parceiro)).length, espessura, places=5)
        for x, y in zip(direita.matrix_world, lateral):
            self.assertLess((x - y).length, 1e-6)
        self.assertEqual(addon.solda._pontas_fora_do_lugar([tampo]), [])

    def ancora_na_quina_de_fora(self):
        """Solda do tampo com o par 0 ancorado na quina de FORA da lateral
        (print do usuario). Devolve (modulo, tampo, direita, ponta, novas,
        sentido)."""
        modulo, tampo, direita, ponta = self.solda_do_tampo()
        ancoras = self._ancoras_legadas_da_ligacao(tampo, ponta, direita)
        _f, u, _e = addon.solda._folga_com_sinal(tampo, ponta, direita)
        sentido = u if ponta.endswith('pos') else -u
        fora = self.vertice_do_outro_lado(direita, ancoras[0][1], sentido,
                                          direita.chapa_espessura_mm / 1000.0)
        novas = [(ancoras[0][0], fora), ancoras[1]]
        addon.solda._gravar_ancoras(tampo, ponta, novas)
        return modulo, tampo, direita, ponta, novas, sentido

    def test_lateral_ativa_e_ela_que_entorta_ate_as_ancoras(self):
        # Print do usuario: a LATERAL selecionada nao se deformava -- so'
        # andava ate' a media e as ancoras ficavam sem encostar
        modulo, tampo, direita, ponta, novas, sentido = self.ancora_na_quina_de_fora()
        tampo_antes = [tuple(tampo.matrix_world @ v.co) for v in tampo.data.vertices]
        sn0 = novas[0][1]
        parceiro = sn0[:2] + ('-' if sn0[2] == '+' else '+')
        espessura = (addon.solda._vertice_da_assinatura(direita, sn0)
                     - addon.solda._vertice_da_assinatura(direita, parceiro)).length
        self.selecionar(direita, ativo=direita)
        self.assertIs(addon.solda._estado_resetar(bpy.context), True)
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(),
                         {'FINISHED'})
        for sc, sn in novas:
            self.assertLess((addon.solda._vertice_da_assinatura(tampo, sc)
                             - addon.solda._vertice_da_assinatura(direita, sn)).length,
                            1e-4, sn)
        # a lateral (a ativa) entortou, com a espessura intacta; o tampo nao
        self.assertAlmostEqual((addon.solda._vertice_da_assinatura(direita, sn0)
                                - addon.solda._vertice_da_assinatura(direita, parceiro)
                                ).length, espessura, places=5)
        tampo_depois = [tuple(tampo.matrix_world @ v.co) for v in tampo.data.vertices]
        for x, y in zip(tampo_antes, tampo_depois):
            self.assertLess((Vector(x) - Vector(y)).length, 1e-6)
        self.assertEqual(addon.solda._pontas_fora_do_lugar([direita]), [])

    def test_lateral_afastada_com_ancora_volta_e_entorta(self):
        # A cena das prints: lateral 200 mm longe, uma ancora na quina de
        # fora. Lateral ativa: volta inteira pelas soldas normais (a base)
        # e entorta so' o que a ancora pede; tudo encostado, nada aparece.
        modulo, tampo, direita, ponta, novas, sentido = self.ancora_na_quina_de_fora()
        self.afastar(direita, 0.2)
        self.selecionar(direita, ativo=direita)
        self.assertEqual(bpy.ops.object.cabinet_resetar_distancia(),
                         {'FINISHED'})
        for sc, sn in novas:
            self.assertLess((addon.solda._vertice_da_assinatura(tampo, sc)
                             - addon.solda._vertice_da_assinatura(direita, sn)).length,
                            1e-4, sn)
        self.assertEqual(addon.solda._pontas_fora_do_lugar(
            addon.modulos._chapas_do_conjunto(modulo)), [])

    def test_ancora_em_vertice_de_chanfro(self):
        # Print do usuario (caso extremo): lateral com um chanfro curvo.
        # A bolinha tem que poder cair em QUALQUER vertice da malha, nao
        # so' nos 8 cantos da caixa; a regua leva a ponta ate' ele.
        modulo, tampo, direita, ponta = self.solda_do_tampo()
        malha = bmesh.new()
        malha.from_mesh(direita.data)
        malha.edges.ensure_lookup_table()
        topo = max(malha.edges, key=lambda e: sum(v.co.y for v in e.verts))
        bmesh.ops.bevel(malha, geom=[topo], offset=0.05, segments=5,
                        affect='EDGES')
        malha.to_mesh(direita.data)
        malha.free()
        direita.data.update()
        bpy.context.view_layer.update()
        candidatos = addon.solda._ancoras_da_malha(direita)
        self.assertGreater(len(candidatos), 8)
        self.assertTrue(all(a.startswith('v') for a, _p in candidatos))
        ancoras = addon.solda._ancoras_da_ligacao(tampo, ponta, direita)
        # um vertice do MEIO do chanfro (nao e' canto da caixa)
        cantos = [addon.solda._vertice_da_assinatura(direita, a + b + c)
                  for a in '+-' for b in '+-' for c in '+-']
        alvo, ponto = max(candidatos, key=lambda c: min(
            (c[1] - k).length for k in cantos))
        op = SimpleNamespace(chapa=tampo.name, ponta=ponta, indice=0, lado='b',
                             report=lambda *a: None)
        self.assertEqual(addon.solda.OBJECT_OT_arrastar_ancora._gravar(op, alvo),
                         {'FINISHED'})
        self.assertLess((addon.solda._vertice_da_assinatura(direita, alvo) - ponto)
                        .length, 1e-6)
        # o outro lado da espessura de um vertice qualquer existe e e' outro
        parceiro = addon.solda._parceiro_espessura(direita, alvo)
        self.assertNotEqual(parceiro, alvo)
        self.selecionar(tampo, ativo=tampo)
        bpy.ops.object.cabinet_resetar_distancia(forcar=True)
        self.assertLess((addon.solda._vertice_da_assinatura(tampo, ancoras[0][0])
                         - addon.solda._vertice_da_assinatura(direita, alvo)).length,
                        1e-4)

    def test_par_que_ja_encostou_some_da_viewport(self):
        # Print do usuario: o par que ja' chegou continuava desenhado em
        # cima do vertice (linha, bolinhas e botoes sobrepostos)
        modulo, tampo, direita, ponta, novas, sentido = self.ancora_na_quina_de_fora()
        ligacao = next(l for l in addon.solda._ligacoes_adjacencia([tampo])
                       if l['a'] == tampo and l['b'] == direita)
        self.assertEqual(ligacao['soltos'], [True, False])
        self.selecionar(tampo, ativo=tampo)
        # cada funcao no modulo dela (o add-on e' um pacote)
        for m, n in ((addon.solda, '_correntes_visiveis'),
                     (addon.hud, '_contexto_hud'),
                     (addon.gaveta, '_eh_area_gaveta'),
                     (addon.hud, '_projetar_hud')):
            self.addCleanup(setattr, m, n, getattr(m, n))
        addon.solda._correntes_visiveis = lambda: True
        addon.hud._contexto_hud = lambda _c: True
        addon.gaveta._eh_area_gaveta = lambda _c: False
        addon.hud._projetar_hud = lambda _c, p: Vector((p.x * 1000, p.z * 1000))
        contexto = _ContextoRegiao()
        contexto.region_data = object()
        correntes = [c for c in addon.solda._correntes_hud(contexto)
                     if c['a'] == tampo and c['b'] == direita]
        self.assertEqual([c['indice'] for c in correntes], [0])

    def test_estado_do_botao_corrente(self):
        piso, lateral = self.piso_e_lateral(10.0)
        self.selecionar(piso, ativo=piso)
        self.assertIs(addon.solda._estado_corrente_objeto(bpy.context), True)
        # as duas pecas ligadas = o grupo: azul, o clique desagrega todas
        self.selecionar(piso, lateral, ativo=lateral)
        self.assertIs(addon.solda._estado_corrente_objeto(bpy.context), True)
        self.assertEqual(addon.solda._acao_corrente(bpy.context)[0], 'grupo')
        addon.solda.desagregar(piso)
        self.selecionar(piso, ativo=piso)
        self.assertIs(addon.solda._estado_corrente_objeto(bpy.context), False)
        # o botao da gaveta leva o estado (azul = agregado)
        widgets = addon.gaveta._widgets_gaveta(bpy.context, 478, 900)
        botao = next(v for v in widgets if v[5] and v[5][:2] == (
            'operador', addon.solda.OP_CORRENTE_OBJETO))
        self.assertEqual(botao[5][2], False)
        self.assertEqual(addon.gaveta_eventos._icone_acao_gaveta(botao[5]), 'LINKED')

    def test_uma_peca_solta_vai_direto_ao_selecionar_vertice(self):
        piso, lateral = self.piso_e_lateral(3.0)
        addon.solda.desagregar(piso)
        # mesmo com vizinha a 3 mm: sozinha, nada de conectar por distancia
        self.selecionar(piso, ativo=piso)
        self.assertEqual(addon.solda._acao_corrente(bpy.context),
                         ('vertices', piso, []))

    def test_alvos_primeiro_e_a_peca_de_fora_por_ultimo(self):
        # Pedido do usuario: seleciona o(s) alvo(s) e, por ULTIMO (o ativo
        # do Blender), a peca de fora. Ate' 5 mm conecta sozinho; so' com
        # os alvos selecionados, nunca com uma vizinha que nao foi.
        piso, lateral = self.piso_e_lateral(3.0)
        addon.solda.desagregar(piso)
        intrusa = addon.chapas.nova_chapa('Intrusa', 720.0, 400.0, 18.0,
                                   (-300.0 - 3.0 - 9.0, 0, 360.0),
                                   (0, 90.0, 0), bpy.context)
        bpy.context.view_layer.update()
        self.assertIn(intrusa, addon.chapas._vizinhos_por_distancia(piso))
        self.selecionar(lateral, piso, ativo=piso)
        self.assertEqual(addon.solda._acao_corrente(bpy.context),
                         ('conectar', piso, [lateral]))
        self.assertIs(addon.solda._estado_corrente_objeto(bpy.context), False)
        self.assertEqual(bpy.ops.object.cabinet_corrente_objeto(),
                         {'FINISHED'})
        self.assertEqual(addon.solda._vizinho_da_ponta(piso, 'x_pos'), lateral)
        self.assertIsNone(addon.solda._vizinho_da_ponta(piso, 'x_neg'))
        # as duas estavam soltas: a Corrente as junta num GRUPO com nome
        # (pedido do usuario); a intrusa fica de fora
        grupo = addon.portas._modulo_da_chapa(piso)
        self.assertIsNotNone(grupo)
        self.assertIs(addon.portas._modulo_da_chapa(lateral), grupo)
        self.assertIsNone(addon.portas._modulo_da_chapa(intrusa))
        self.assertTrue(grupo.name.startswith('Armario '))
        # a 10 mm a automatica falha: selecionar vertice, so' nos alvos
        addon.solda.desagregar_grupo([piso, lateral])
        lateral.location.x += 0.007
        bpy.context.view_layer.update()
        self.selecionar(lateral, piso, ativo=piso)
        self.assertEqual(addon.solda._acao_corrente(bpy.context),
                         ('vertices', piso, [lateral]))
        estado = {'origem': piso.name, 'fase': 'destino',
                  'destinos': addon.solda._nomes([lateral])}
        self.assertEqual({o for o, _s, _p in addon.solda._candidatos_conexao(estado)},
                         {lateral})

    def test_modulo_como_ativo_nao_e_puxado_ate_o_alvo(self):
        # quem vai ate' o alvo e' UMA peca; um modulo por ultimo nao vale
        modulo = self.modulo()
        solta = self.prateleira_solta()
        self.selecionar(solta, modulo, *addon.modulos._chapas_do_conjunto(modulo),
                        ativo=modulo)
        self.assertIsNone(addon.solda._acao_corrente(bpy.context))
        self.assertIsNone(addon.solda._estado_corrente_objeto(bpy.context))

    def test_desagregar_o_grupo_pergunta_antes(self):
        modulo = self.modulo()
        chapas = addon.modulos._chapas_do_conjunto(modulo)
        mundo = {o.name: o.matrix_world.copy() for o in chapas}
        addon.hud._selecionar_chapa_hud(bpy.context, chapas[0])   # clique: modulo
        self.assertEqual(addon.solda._acao_corrente(bpy.context),
                         ('grupo', None, chapas))
        self.assertIn('todos os itens deste grupo',
                      addon.solda.PERGUNTA_DESAGREGAR_GRUPO)
        self.assertEqual(bpy.ops.object.cabinet_corrente_objeto(),
                         {'FINISHED'})
        self.assertEqual(addon.solda._desagregar_pendente[0],
                         sorted(o.name for o in chapas))
        # "Nao": nada muda
        self.assertEqual(bpy.ops.object.cabinet_desagregar_selecao(
            desagregar=False), {'CANCELLED'})
        self.assertIsNone(addon.solda._desagregar_pendente[0])
        self.assertTrue(all(o.parent == modulo for o in chapas))
        # "Sim": todas soltas, no lugar, e o modulo vazio some
        nome_modulo = modulo.name
        bpy.ops.object.cabinet_corrente_objeto()
        self.assertEqual(bpy.ops.object.cabinet_desagregar_selecao(),
                         {'FINISHED'})
        self.assertNotIn(nome_modulo, bpy.data.objects)
        for o in chapas:
            self.assertIsNone(o.parent)
            self.assertFalse(addon.solda.agregado(o), o.name)
            for a, b in zip(o.matrix_world, mundo[o.name]):
                self.assertLess((a - b).length, 1e-6, o.name)

    def test_pergunta_vai_para_a_gaveta_ou_para_o_popup(self):
        # Botao da gaveta (_na_gaveta) -> caixa na gaveta; viewport -> pop-up.
        # A resposta e' a mesma nos dois: cabinet_responder_pergunta.
        modulo = self.modulo()
        chapas = addon.modulos._chapas_do_conjunto(modulo)
        addon.hud._selecionar_chapa_hud(bpy.context, chapas[0])
        try:
            addon.perguntas._na_gaveta[0] = True
            bpy.ops.object.cabinet_corrente_objeto()
        finally:
            addon.perguntas._na_gaveta[0] = False
        self.assertTrue(addon.perguntas._pergunta_atual[0]['na_gaveta'])
        bpy.ops.object.cabinet_corrente_objeto()            # sem gaveta
        self.assertFalse(addon.perguntas._pergunta_atual[0]['na_gaveta'])
        # "Nao": nada muda e a pergunta some
        self.assertEqual(bpy.ops.object.cabinet_responder_pergunta(opcao=1),
                         {'CANCELLED'})
        self.assertIsNone(addon.perguntas._pergunta_atual[0])
        self.assertTrue(all(o.parent == modulo for o in chapas))
        # "Sim": desagrega
        bpy.ops.object.cabinet_corrente_objeto()
        self.assertEqual(bpy.ops.object.cabinet_responder_pergunta(opcao=0),
                         {'FINISHED'})
        self.assertTrue(all(o.parent is None for o in chapas))
        # sem pergunta pendente: nada a responder
        self.assertEqual(bpy.ops.object.cabinet_responder_pergunta(opcao=0),
                         {'CANCELLED'})

    def test_desagregar_um_objeto_do_grupo_pergunta_antes(self):
        modulo = self.modulo()
        chapas = addon.modulos._chapas_do_conjunto(modulo)
        peca = chapas[0]
        addon.hud._selecionar_chapa_hud(bpy.context, peca, individual=True)
        self.assertEqual(addon.solda._acao_corrente(bpy.context),
                         ('desagregar', peca, [peca]))
        self.assertIn('desagregar esse objeto do grupo',
                      addon.solda.PERGUNTA_DESAGREGAR_OBJETO)
        bpy.ops.object.cabinet_corrente_objeto()
        self.assertEqual(addon.solda._desagregar_pendente[0], [peca.name])
        self.assertEqual(bpy.ops.object.cabinet_desagregar_selecao(),
                         {'FINISHED'})
        self.assertIsNone(peca.parent)
        self.assertFalse(addon.solda.agregado(peca))
        self.assertTrue(all(o.parent == modulo for o in chapas[1:]))
        self.assertIn(modulo.name, bpy.data.objects)
        # sem pergunta pendente: nada a fazer
        self.assertEqual(bpy.ops.object.cabinet_desagregar_selecao(),
                         {'CANCELLED'})

    def test_conexao_automatica_so_ate_5mm(self):
        # Pedido do usuario: juntar sozinho so' ate' 5 mm; mais longe ja'
        # e' "selecionar vertice" (nenhum vizinho "ao alcance").
        self.assertAlmostEqual(addon.chapas.ALCANCE_CONEXAO_AUTOMATICA, 0.005)
        for folga, alcanca in ((5.0, True), (6.0, False), (20.0, False)):
            for o in list(bpy.data.objects):
                bpy.data.objects.remove(o, do_unlink=True)
            piso, lateral = self.piso_e_lateral(folga)
            addon.solda.desagregar(piso)
            self.assertEqual(addon.chapas._vizinhos_por_distancia(piso),
                             {lateral} if alcanca else set(), folga)
            resultado = bpy.ops.object.cabinet_conectar_distancia(
                origem=piso.name)
            self.assertEqual(resultado,
                             {'FINISHED'} if alcanca else {'CANCELLED'}, folga)
            self.assertEqual(addon.solda._vizinho_da_ponta(piso, 'x_pos'),
                             lateral if alcanca else None, folga)
        # o agrupar do modulo (detectar_adjacencia) segue com o alcance dele
        piso, lateral = self.piso_e_lateral(20.0)
        self.assertEqual(addon.solda._vizinho_da_ponta(piso, 'x_pos'), lateral)

    def test_associar_uma_peca_nao_apaga_as_ligacoes_das_outras(self):
        # detectar_adjacencia zera quem recebe; associar_por_distancia nao
        piso, lateral = self.piso_e_lateral(10.0)
        fora = addon.chapas.nova_chapa('Fora', 400.0, 400.0, 18.0,
                                (319.0 + 9.0 + 200.0 + 5.0, 0, 300.0),
                                (0, 0, 0), bpy.context)
        bpy.context.view_layer.update()
        addon.chapas.associar_por_distancia(fora, [lateral])
        self.assertEqual(addon.solda._vizinho_da_ponta(fora, 'x_neg'), lateral)
        self.assertEqual(addon.solda._vizinho_da_ponta(piso, 'x_pos'), lateral)

    def test_juntar_cadastra_a_posicao_da_peca_e_o_alvo_fica_parado(self):
        modulo = self.modulo()
        chapas = addon.modulos._chapas_do_conjunto(modulo)
        direita = max(chapas, key=lambda o: o.matrix_world.translation.x)
        fixos = {o.name: o.matrix_world.copy() for o in chapas}
        prateleira = self.prateleira_solta(x_mm=900.0, z_mm=300.0)
        bpy.context.view_layer.update()
        # Um canto da ponta ESQUERDA da prateleira no vertice real da lateral.
        fora_x = max(p.x for p in addon.chapas._cantos(direita))
        alvos_lateral = sorted((p for p in addon.chapas._cantos(direita)
                                if abs(p.x - fora_x) < 1e-6 and p.z < 0.01),
                               key=lambda p: p.y)
        cantos = sorted((p for p in addon.chapas._cantos(prateleira)
                         if addon.solda._assinatura_canto(prateleira, p)[0] == '-'
                         and addon.solda._assinatura_canto(prateleira, p)[2] == '-'),
                        key=lambda p: p.y)
        direita_prat = max(p.x for p in addon.chapas._cantos(prateleira))
        antes=[prateleira.matrix_world@v.co for v in prateleira.data.vertices]
        pares = [(addon.solda._assinatura_canto(prateleira, p), direita.name,
                  addon.solda._assinatura_canto(direita, q))
                 for p, q in zip(cantos[:1], alvos_lateral[:1])]
        self.assertEqual(len(pares),1)
        addon.solda._conexao_pendente[0] = {
            'origem': prateleira.name,
            'alvos': [(s, tuple(addon.solda._canto_da_assinatura(direita, sn)))
                      for s, _n, sn in pares],
            'pecas': [direita.name], 'pares': pares}
        self.assertEqual(bpy.ops.object.cabinet_juntar_modulo(juntar=True),
                         {'FINISHED'})
        bpy.context.view_layer.update()
        for p,v in zip(antes,prateleira.data.vertices):
            self.assertLess((prateleira.matrix_world@v.co-p).length,1e-6)
        self.assertFalse(addon.solda._pontas_fora_do_lugar([prateleira]))
        # entrou no modulo, associada; o modulo NAO foi puxado
        self.assertEqual(prateleira.parent, modulo)
        self.assertTrue(addon.solda.agregado(prateleira))
        for o in chapas:
            for a, b in zip(o.matrix_world, fixos[o.name]):
                self.assertLess((a - b).length, 1e-6, o.name)
        self.assertIsNone(addon.solda._conexao_pendente[0])

    def test_nao_juntar_nao_move_nada(self):
        modulo = self.modulo()
        direita = max(addon.modulos._chapas_do_conjunto(modulo),
                      key=lambda o: o.matrix_world.translation.x)
        prateleira = self.prateleira_solta(x_mm=900.0)
        antes = prateleira.matrix_world.copy()
        canto = addon.chapas._cantos(prateleira)[0]
        addon.solda._conexao_pendente[0] = {
            'origem': prateleira.name,
            'alvos': [(addon.solda._assinatura_canto(prateleira, canto),
                       tuple(addon.chapas._cantos(direita)[0]))],
            'pecas': [direita.name]}
        self.assertEqual(bpy.ops.object.cabinet_juntar_modulo(juntar=False),
                         {'FINISHED'})
        self.assertIsNone(prateleira.parent)
        for a, b in zip(prateleira.matrix_world, antes):
            self.assertLess((a - b).length, 1e-9)
        # sem pergunta pendente: nada a fazer
        self.assertEqual(bpy.ops.object.cabinet_juntar_modulo(),
                         {'CANCELLED'})

    def test_tecla_das_opcoes_mostra_as_correntes(self):
        op = addon.solda.OBJECT_OT_tecla_corrente
        ctx = SimpleNamespace(screen=None)
        evento = SimpleNamespace(type='LEFT_ALT')
        original = addon.opcoes._opcao('tecla_corrente')
        try:
            addon.opcoes._definir_opcao('tecla_corrente', 'ALT')
            self.assertFalse(addon.solda._correntes_visiveis())
            for tecla, apertou, visivel in (
                    ('LEFT_CTRL', True, False),     # outra tecla: nada
                    ('LEFT_ALT', True, True),
                    ('RIGHT_ALT', False, False)):
                fake = SimpleNamespace(tecla=tecla, apertou=apertou)
                # o evento segue adiante: Alt continua valendo no Blender
                self.assertEqual(op.invoke(fake, ctx, evento),
                                 {'PASS_THROUGH'})
                self.assertEqual(addon.solda._correntes_visiveis(), visivel, tecla)
            addon.opcoes._definir_opcao('tecla_corrente', 'SEMPRE')
            self.assertTrue(addon.solda._correntes_visiveis())
            self.assertIn('tecla_corrente', addon.gaveta.SUSPENSOS_OPCOES)
        finally:
            addon.solda._tecla_corrente_segurada[0] = False
            addon.opcoes._definir_opcao('tecla_corrente', original)

    def test_corrente_entre_modulo_e_peca_de_fora(self):
        modulo = self.modulo()
        chapas = addon.modulos._chapas_do_conjunto(modulo)
        lo = min(min(p.x for p in addon.chapas._cantos(c)) for c in chapas)
        # A adjacencia liga a PONTA de uma chapa a FACE de outra (duas
        # laterais face com face nao se ligam): prateleira de fora com a
        # ponta a 5 mm da lateral do modulo
        de_fora = addon.chapas.nova_chapa('Vizinha', 400.0, 300.0, 18.0,
                                   (lo * 1000.0 - 5.0 - 200.0, 0, 300.0),
                                   (0, 0, 0), bpy.context)
        bpy.context.view_layer.update()
        addon.chapas.detectar_adjacencia(chapas + [de_fora])
        self.assertEqual(addon.solda._ligacoes_adjacencia(chapas), [])   # na origem
        self.afastar(de_fora, -0.010)
        ligacoes = addon.solda._ligacoes_adjacencia(chapas)
        self.assertTrue(ligacoes)
        for ligacao in ligacoes:
            self.assertIn(de_fora, (ligacao['a'], ligacao['b']))

    def modos_dos_itens(self):
        return sorted((o.name, modo) for o, modo, _c in
                      addon.hud._itens_da_selecao(bpy.context))

    def test_hud_mostra_todos_os_itens_sem_ordem(self):
        # Pedido do usuario: com dois modulos selecionados o contorno so'
        # aparecia no ultimo. Cada item tem o seu, em QUALQUER ordem:
        # dois grupos, grupo + chapa, chapa + grupo, duas chapas.
        primeiro, segundo = self.dois_modulos()
        a1 = addon.modulos._chapas_do_conjunto(primeiro)[0]
        b1 = addon.modulos._chapas_do_conjunto(segundo)[0]
        grupo_a = [primeiro, *primeiro.children_recursive]
        grupo_b = [segundo, *segundo.children_recursive]
        casos = (
            (grupo_a + grupo_b, segundo,
             [(primeiro.name, 'GRUPO'), (segundo.name, 'GRUPO')]),
            (grupo_a + [b1], b1,
             [(primeiro.name, 'GRUPO'), (b1.name, 'INDIVIDUAL')]),
            ([a1] + grupo_b, a1,
             [(a1.name, 'INDIVIDUAL'), (segundo.name, 'GRUPO')]),
            ([a1, b1], b1,
             [(a1.name, 'INDIVIDUAL'), (b1.name, 'INDIVIDUAL')]),
            ([a1, addon.modulos._chapas_do_conjunto(primeiro)[1]], a1,
             sorted([(a1.name, 'INDIVIDUAL'), (addon.modulos._chapas_do_conjunto(
                 primeiro)[1].name, 'INDIVIDUAL')])),
        )
        for selecao, ativo, esperado in casos:
            self.selecionar(*selecao, ativo=ativo)
            self.assertEqual(self.modos_dos_itens(), sorted(esperado),
                             [o.name for o in selecao])
            desenhos = addon.hud._desenhos_hud(_ContextoRegiao())
            self.assertEqual(len(desenhos), len(esperado))
            # o item do ativo vem primeiro (gaveta e correntes leem ele)
            self.assertIn(ativo, (addon.hud._alvo_hud(bpy.context)[0],
                                  *addon.hud._alvo_hud(bpy.context)[2]))
        # chapa individual mostra L/A/E; modulo mostra L/P/A
        self.selecionar(*grupo_a, b1, ativo=b1)
        letras = {g['objeto'].name: {l['letra'] for l in g['linhas']
                                     if l['tipo'] == 'medida'}
                  for g, _a in addon.hud._desenhos_hud(_ContextoRegiao())}
        self.assertEqual(letras[b1.name], {'L', 'A', 'E'})
        self.assertEqual(letras[primeiro.name], {'L', 'P', 'A'})

    def test_linhas_e_quinas_valem_em_qualquer_item_selecionado(self):
        # Setas e quinas tambem no item que NAO e' o ativo
        primeiro, segundo = self.dois_modulos()
        b1 = addon.modulos._chapas_do_conjunto(segundo)[0]
        self.selecionar(primeiro, *primeiro.children_recursive, b1, ativo=b1)
        projetar = lambda p: Vector((300 + p.x * 100 + p.y * 30,
                                     200 + p.z * 100 + p.y * 18))
        originais = (addon.hud._contexto_hud, addon.hud._projetar_hud)
        addon.hud._contexto_hud = lambda _c: True
        addon.hud._projetar_hud = lambda _c, p: projetar(p)
        self.addCleanup(setattr, addon.hud, '_contexto_hud', originais[0])
        self.addCleanup(setattr, addon.hud, '_projetar_hud', originais[1])
        geometria = addon.hud._geometria_do_item(
            primeiro, 'GRUPO', addon.modulos._chapas_do_conjunto(primeiro))
        # quina do modulo nao ativo: mover
        alvo = addon.hud._acertar_hud(bpy.context, projetar(geometria['cantos'][5]))
        self.assertEqual((alvo['tipo'], alvo['objeto']), ('ancora', primeiro))
        # linha L do modulo nao ativo: a seta e' dele
        linha = next(l for l in geometria['linhas']
                     if l['tipo'] == 'medida' and l['eixo'] == 0)
        a, b = (projetar(q) for q in linha['pontos'])
        alvo = addon.hud._acertar_hud(bpy.context, a + (b - a) * 0.25)
        self.assertEqual((alvo['tipo'], alvo['objeto'], alvo['eixo']),
                         ('medida', primeiro, 0))
        self.assertEqual(alvo['lado'], 'min')
        largura = segundo.conj_largura_mm
        addon.hud._aplicar_valor_hud(bpy.context, alvo, 900.0)
        self.assertAlmostEqual(primeiro.conj_largura_mm, 900.0, places=3)
        self.assertAlmostEqual(segundo.conj_largura_mm, largura, places=3)
        # so' o item do alvo acende; o outro desenha normal
        addon.hud._hover_hud[4242] = alvo
        acesos = [g['objeto'] for g, aceso in
                  addon.hud._desenhos_hud(_ContextoRegiao()) if aceso]
        self.assertEqual(acesos, [primeiro])

    def test_quina_continua_movendo_o_modulo(self):
        self.modulo()
        geometria = addon.hud._geometria_hud(bpy.context)
        projetar = lambda p: Vector((300+p.x*500+p.y*150, 200+p.z*500+p.y*90))
        alvo = addon.hud._acertar_linhas_hud(
            geometria, projetar(geometria['cantos'][5]), projetar)
        self.assertEqual(alvo['tipo'], 'ancora')
        self.assertNotIn('lado', alvo)

    # Regressao (era BUG, corrigido na 304): com Ctrl as quinas da cena eram
    # juntadas e projetadas em Python a cada movimento. Agora o cursor anda
    # pelo translate NATIVO (o Ctrl dele liga o snap) e o modulo o segue.
    def test_quina_move_o_modulo_pelo_snap_nativo(self):
        H = addon.hud
        self.assertIn(H.OBJECT_OT_mover_quina_hud, addon.CLASSES)
        self.assertIn(H.OBJECT_OT_confirmar_quina_hud, addon.CLASSES)
        self.assertEqual(bpy.ops.object.cabinet_confirmar_quina_hud(), {'CANCELLED'})
        primeiro, segundo = self.dois_modulos()
        chapas = addon.modulos._chapas_do_conjunto
        caixa = lambda m: H._caixa_hud_objetos(chapas(m))
        origem = caixa(primeiro)[3].copy()
        cena = bpy.context.scene
        cursor = cena.cursor.location.copy()
        contexto = SimpleNamespace(
            visible_objects=bpy.context.visible_objects, scene=bpy.context.scene,
            region=SimpleNamespace(as_pointer=lambda: 1),
            area=SimpleNamespace(as_pointer=lambda: 2),
            space_data=SimpleNamespace(overlay=SimpleNamespace(show_cursor=True)))
        self.addCleanup(H._terminar_quina_nativa)
        parametros = H._preparar_quina_nativa(contexto, primeiro, origem,
                                              primeiro.matrix_world.copy())
        self.assertFalse(parametros['snap'])          # o Ctrl do translate liga
        self.assertEqual(parametros['snap_elements'], {'VERTEX'})
        self.assertTrue(all(o.hide_select for o in chapas(primeiro)))
        self.assertFalse(any(o.hide_select for o in chapas(segundo)))
        destino = caixa(segundo)[3].copy()
        cena.cursor.location = destino
        self.assertEqual(bpy.ops.object.cabinet_confirmar_quina_hud(), {'FINISHED'})
        self.assertIsNone(H._arraste_quina[0])
        self.assertLess((caixa(primeiro)[3] - destino).length, 1e-5)
        self.assertFalse(any(o.hide_select for o in chapas(primeiro)))
        self.assertLess((cena.cursor.location - cursor).length, 1e-6)

    def teclar(self, estado, texto):
        for c in texto:
            addon.gaveta_desenho._tecla_no_texto(estado, 'X', c)

    def test_operador_continua_a_conta_em_vez_de_apagar(self):
        # Pedido do usuario: caixa aberta com "600" (todo selecionado);
        # '+' nao apaga -- fica "600 + "
        estado = {'texto': '600', 'cursor': 3, 'selecionado': True}
        addon.gaveta_desenho._tecla_no_texto(estado, 'NUMPAD_PLUS', '+')
        self.assertEqual(estado['texto'], '600 + ')
        self.assertEqual(estado['cursor'], len('600 + '))
        self.teclar(estado, '100')
        self.assertEqual(addon.gaveta_desenho._ler_medida_digitada(estado['texto']), 0.7)
        for operador in '-*/':
            estado = {'texto': '600', 'cursor': 3, 'selecionado': True}
            addon.gaveta_desenho._tecla_no_texto(estado, 'X', operador)
            self.assertEqual(estado['texto'], '600 %s ' % operador)
        # print do usuario: "664 - 100+25" -- todo operador digitado sai
        # com um espaco de cada lado, em qualquer ponto da conta
        estado = {'texto': '664', 'cursor': 3, 'selecionado': True}
        self.teclar(estado, '-100+25*2/4')
        self.assertEqual(estado['texto'], '664 - 100 + 25 * 2 / 4')
        # sem espaco dobrado se ja' havia um; no meio tambem
        estado = {'texto': '664 ', 'cursor': 4, 'selecionado': False}
        self.teclar(estado, '+')
        self.assertEqual(estado['texto'], '664 + ')
        estado = {'texto': '600100', 'cursor': 3, 'selecionado': False}
        self.teclar(estado, '+')
        self.assertEqual(addon.gaveta_desenho._com_cursor(estado['texto'], estado['cursor']),
                         '600 + |100')
        # colado entra como veio
        estado = {'texto': '', 'cursor': 0, 'selecionado': False}
        addon.gaveta_desenho._tecla_no_texto(estado, 'V', '1+2')
        self.assertEqual(estado['texto'], '1+2')
        # numero com tudo selecionado continua trocando o texto
        estado = {'texto': '600', 'cursor': 3, 'selecionado': True}
        self.teclar(estado, '75')
        self.assertEqual(estado['texto'], '75')
        estado = {'texto': '600', 'cursor': 3, 'selecionado': True}
        addon.gaveta_desenho._tecla_no_texto(estado, 'BACK_SPACE')
        self.assertEqual((estado['texto'], estado['cursor']), ('', 0))

    def test_unidade_solta_ou_no_meio_vale_para_o_numero(self):
        try:
            addon.opcoes._definir_opcao('unidade_padrao', 'MM')
            # "500 + cm" -> 500 cm; "500 +" -> 500
            self.assertEqual(addon.gaveta_desenho._arrumar_texto_medida('500 + cm'), '500cm')
            self.assertEqual(addon.gaveta_desenho._ler_medida_digitada('500 + cm'), 5.0)
            self.assertEqual(addon.gaveta_desenho._ler_medida_digitada('500 +'), 0.5)
            # "51cm00" (cm digitado no meio) -> 5100 cm
            self.assertEqual(addon.gaveta_desenho._arrumar_texto_medida('51cm00'), '5100cm')
            self.assertEqual(addon.gaveta_desenho._ler_medida_digitada('51cm00'), 51.0)
            # o que ja' funcionava nao muda
            for texto, metros in (('1m - 20mm', 0.98), ('600cm + 500mm', 6.5),
                                  ('2*300', 0.6), ('600 + 500', 1.1)):
                self.assertEqual(addon.gaveta_desenho._ler_medida_digitada(texto), metros, texto)
        finally:
            addon.opcoes._definir_opcao('unidade_padrao', 'MM')

    def test_cursor_anda_e_escreve_no_meio(self):
        # 500| -> clique ao lado do 5 -> 5|00 -> '1' -> 51|00 -> 'cm'
        largura = lambda t: 10 * len(t)            # 10 px por caractere
        estado = {'texto': '500', 'cursor': 3, 'selecionado': True}
        estado['cursor'] = addon.gaveta_desenho._cursor_no_x('500', 3, 0, 12, largura)
        estado['selecionado'] = False
        self.assertEqual(estado['cursor'], 1)
        self.teclar(estado, '1')
        self.assertEqual(addon.gaveta_desenho._com_cursor(estado['texto'], estado['cursor']),
                         '51|00')
        self.teclar(estado, 'cm')
        self.assertEqual(estado['texto'], '51cm00')
        self.assertEqual(addon.gaveta_desenho._ler_medida_digitada(estado['texto']), 51.0)
        # depois da barra as posicoes andam a largura dela: "5|00", clique
        # em x=25 cai entre os dois zeros (posicao 2, x=30 na tela)
        self.assertEqual(addon.gaveta_desenho._cursor_no_x('500', 1, 0, 25, largura), 2)
        # setas, Home/End, Del e Backspace no cursor
        estado = {'texto': '1234', 'cursor': 4, 'selecionado': False}
        for tecla in ('LEFT_ARROW', 'LEFT_ARROW'):
            addon.gaveta_desenho._tecla_no_texto(estado, tecla)
        addon.gaveta_desenho._tecla_no_texto(estado, 'BACK_SPACE')
        self.assertEqual((estado['texto'], estado['cursor']), ('134', 1))
        addon.gaveta_desenho._tecla_no_texto(estado, 'DEL')
        self.assertEqual(estado['texto'], '14')
        addon.gaveta_desenho._tecla_no_texto(estado, 'HOME')
        self.teclar(estado, '9')
        self.assertEqual(estado['texto'], '914')
        self.assertFalse(addon.gaveta_desenho._tecla_no_texto(estado, 'F5'))

    def test_medida_digitada_aceita_conta_e_unidades_misturadas(self):
        for texto, metros in (('600 + 500', 1.1), ('600CM + 500MM', 6.5),
                              ('600cm + 500mm', 6.5), ('1m - 20mm', 0.98),
                              ('(600+500)/2', 0.55), ('2*300', 0.6)):
            # exato: o ruido do parser (1100.0001) e' arredondado
            self.assertEqual(addon.gaveta_desenho._ler_medida_digitada(texto), metros, texto)
        try:
            addon.opcoes._definir_opcao('unidade_padrao', 'CM')
            self.assertEqual(addon.gaveta_desenho._ler_medida_digitada('60'), 0.6)
            # sem unidade = a padrao, mesmo ao lado de outra unidade
            self.assertEqual(addon.gaveta_desenho._ler_medida_digitada('60 + 5mm'), 0.605)
            # o 2 multiplica, nao e' medida
            self.assertEqual(addon.gaveta_desenho._ler_medida_digitada('2*30cm + 5'), 0.65)
            self.assertEqual(addon.opcoes._texto_medida(600.0), '60.00 cm')
            self.assertEqual(addon.opcoes._numero_na_unidade(600.0), '60')
        finally:
            addon.opcoes._definir_opcao('unidade_padrao', 'MM')
        self.assertEqual(addon.opcoes._texto_medida(600.0), '600.0 mm')

    def test_medida_digitada(self):
        for texto, metros in (('750', 0.75), ('75cm', 0.75), ('0,75 m', 0.75),
                              (' 18 ', 0.018)):
            self.assertAlmostEqual(addon.gaveta_desenho._ler_medida_digitada(texto), metros)
        for texto in ('abc', '0', '-5'):
            with self.assertRaises(ValueError):
                addon.gaveta_desenho._ler_medida_digitada(texto)
        # Regressao (era BUG, corrigido na 302): folga/curva digitada como 0
        # era recusada, embora o arraste aceite 0 nesses campos.
        self.assertEqual(addon.gaveta_desenho._ler_medida_digitada('0', 0.0), 0.0)
        with self.assertRaises(ValueError):
            addon.gaveta_desenho._ler_medida_digitada('-5', 0.0)

    def test_espessura_individual_livre_sem_alterar_outras_chapas(self):
        # A espessura nao arredonda mais para 15/18/20/30 (usuario).
        modulo = self.modulo()
        chapa = addon.modulos._chapas_do_conjunto(modulo)[0]
        outras = {o: o.chapa_espessura_mm for o in addon.modulos._chapas_do_conjunto(modulo)
                  if o != chapa}
        addon.hud._selecionar_chapa_hud(bpy.context, chapa, individual=True)
        addon.hud._aplicar_valor_hud(bpy.context, {'tipo': 'espessura', 'objeto': chapa}, 27)
        self.assertEqual(chapa.chapa_espessura_mm, 27)
        for o, espessura in outras.items():
            self.assertEqual(o.chapa_espessura_mm, espessura)
        self.assertEqual(addon.gaveta._medidas_gaveta(bpy.context)[1][-1][1], 27)

    def test_gap_altera_somente_entre_folhas_e_sincroniza_menu(self):
        modulo = self.modulo()
        bpy.ops.object.cabinet_portas(
            capturado=True, ponto_a=(-0.3, -0.15, 0), ponto_b=(0.3, -0.15, 0.4),
            pai_nome=modulo.name, modulo_nome=modulo.name, frente='NEG_Y', folhas=2)
        grupo = addon.portas._portas_do_conjunto(modulo)[0]
        antes = dict(grupo['porta_parametros'])
        alvo = {'tipo': 'gap', 'objeto': grupo}
        addon.hud._aplicar_valor_hud(bpy.context, alvo, 8)
        self.assertEqual(grupo['porta_parametros']['entre_folhas_mm'], 8)
        self.assertEqual(bpy.context.scene.porta_entre_folhas_mm, 8)
        for chave in antes:
            if chave != 'entre_folhas_mm':
                self.assertEqual(antes[chave], grupo['porta_parametros'][chave])
        folhas = addon.portas._folhas_portas(grupo)
        self.assertAlmostEqual((folhas[1].location.x-folhas[0].location.x)*1000
                               - folhas[0].chapa_largura_mm, 8, places=4)

    def test_cancelamento_restaura_geometria_e_parametros(self):
        modulo = self.modulo()
        alvo = addon.hud._geometria_hud(bpy.context)['linhas'][0]
        estado = addon.hud._estado_arraste_hud(bpy.context, alvo)
        addon.hud._aplicar_valor_hud(bpy.context, alvo, 950)
        addon.hud._restaurar_arraste_hud(bpy.context, estado)
        for obj, matriz, inversa, props, porta, vertices in estado[0]:
            for atual, esperado in zip(obj.matrix_world, matriz):
                self.assertLess((atual-esperado).length, 1e-6)
            for nome, valor in props.items():
                self.assertEqual(getattr(obj, nome), valor)
            if vertices is not None:
                for atual, esperado in zip(obj.data.vertices, vertices):
                    self.assertLess((atual.co-Vector(esperado)).length, 1e-6)

    def test_gaveta_nao_gera_mais_wireframe(self):
        self.modulo()
        for aba in ('MODULOS', 'PORTAS'):
            bpy.context.scene.cabinet_aba = aba
            for largura in (190, 320, 564):
                widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1400)
                self.assertFalse(any(w[5] and w[5][0] == 'wireframe' for w in widgets))

    def test_hover_esquece_objeto_liberado(self):
        # Crash do usuario no Ctrl+Z: o hover guardava o OBJETO e a HUD o
        # desenhava depois que o undo o liberou (memoria liberada).
        modulo = self.modulo()
        chapas = addon.modulos._chapas_do_conjunto(modulo)
        alvo = {'tipo': 'medida', 'objeto': modulo, 'chapas': chapas}
        self.assertTrue(addon.hud._alvo_vivo(alvo))
        for evento, funcao in addon.eventos.HANDLERS_REFERENCIAS:
            self.assertIn(funcao, getattr(bpy.app.handlers, evento), evento)
        addon.hud._hover_hud[1] = alvo
        addon.eventos._antes_de_desfazer()
        self.assertTrue(addon.eventos._desfazendo[0])
        addon.eventos._desfazendo[0] = False
        self.assertEqual(addon.hud._hover_hud, {})
        bpy.data.objects.remove(chapas[0], do_unlink=True)
        self.assertFalse(addon.hud._alvo_vivo(alvo))

    def test_handler_do_depsgraph_espera_o_undo_assentar(self):
        # Crash do usuario (2x): Ctrl+Z logo apos criar a porta; o 1o
        # recalculo depois do undo chamava o handler, que lia a selecao.
        modulo = self.modulo()
        chamadas = []
        original = addon.eventos.sincronizar_contornos
        addon.eventos.sincronizar_contornos = lambda *a, **k: chamadas.append(1)
        try:
            addon.eventos._depois_de_desfazer()
            self.assertTrue(addon.eventos._desfazendo[0])
            self.assertTrue(bpy.app.timers.is_registered(addon.eventos._fim_do_desfazer))
            addon.chapas.ao_atualizar_depsgraph(bpy.context.scene, None)
            self.assertEqual(chamadas, [])          # nada durante o undo
            addon.eventos._fim_do_desfazer()                 # o proximo tique
            self.assertFalse(addon.eventos._desfazendo[0])
            self.assertEqual(chamadas, [1])          # o contorno volta
        finally:
            addon.eventos.sincronizar_contornos = original
            addon.eventos._desfazendo[0] = False
            if bpy.app.timers.is_registered(addon.eventos._fim_do_desfazer):
                bpy.app.timers.unregister(addon.eventos._fim_do_desfazer)
        # a selecao dos grupos sai por select_get, sem a colecao
        bpy.ops.object.select_all(action='DESELECT')
        modulo.select_set(True)
        self.assertEqual(addon.eventos._grupos_selecionados(bpy.context.view_layer),
                         frozenset({modulo.name}))

    def test_handlers_e_gizmos_registrados(self):
        self.assertIsNotNone(addon.hud._handler_hud_texto[0])
        self.assertIsNotNone(addon.hud._handler_grid[0])
        self.assertIn(addon.hud.VIEW3D_GT_hud_cabinet, addon.CLASSES)
        self.assertIn(addon.hud.VIEW3D_GGT_hud_cabinet, addon.CLASSES)
        self.assertIn(addon.hud.OBJECT_OT_arrastar_hud, addon.CLASSES)


addon.register()
resultado = unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(TestHUD))
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes da HUD')
