"""Fundos por vao, canais nativos e acompanhamento dos internos."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon


class TestFundos(unittest.TestCase):
    def setUp(self):
        if bpy.context.mode!='OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj,do_unlink=True)
        self.handler=addon.chapas.ao_atualizar_depsgraph
        self.ativo=self.handler in bpy.app.handlers.depsgraph_update_post
        if self.ativo:
            bpy.app.handlers.depsgraph_update_post.remove(self.handler)
        self.f=addon.fundos
        self.f.esquecer()
        self.conj=addon.modulos.criar_armario(bpy.context,'Teste Fundo',800,800,560,18,fundo=False)
        bpy.context.view_layer.update()

    def tearDown(self):
        addon.eventos._desfazendo[0]=False
        addon.chapas._ocupado[0]=False
        if self.ativo:
            bpy.app.handlers.depsgraph_update_post.append(self.handler)

    def pontos(self):
        lo,hi=addon.gavetas._limites(self.conj)
        return [self.conj.matrix_world@(Vector((lo.x+18,hi.y,lo.z+18))/1000),
                self.conj.matrix_world@(Vector((hi.x-18,hi.y,hi.z-18))/1000)]

    def fundo(self,**p):
        return self.f.criar(bpy.context,self.conj,self.pontos(),p)

    def prateleiras(self,prof=520):
        return addon.prateleiras.criar_prateleiras(bpy.context,self.conj,(18,18,18,18,0),dict(quantidade=2,profundidade_mm=prof))

    def gavetas(self,prof=520):
        return addon.gavetas.criar_gavetas(bpy.context,self.conj,(18,18,18,18,0),dict(quantidade=2,profundidade_mm=prof,puxador='NENHUM'))

    def test_canal_6_mm_encaixa_e_corta_apoios_sem_trocar_malha(self):
        apoios=addon.modulos._chapas_do_conjunto(self.conj)
        malhas={o.name:o.data for o in apoios}
        fundo=self.fundo()
        self.assertAlmostEqual(fundo.chapa_espessura_mm,6)
        self.assertAlmostEqual(fundo.chapa_largura_mm,778,places=2)
        self.assertAlmostEqual(fundo.chapa_comprimento_mm,778,places=2)
        self.assertEqual(len([o for o in apoios if any(m.type=='BOOLEAN' for m in o.modifiers)]),4)
        for o in apoios:
            self.assertEqual(o.data,malhas[o.name])
            avaliado=o.evaluated_get(bpy.context.evaluated_depsgraph_get())
            self.assertGreater(len(avaliado.data.vertices),8)

    def test_pregado_cobre_costas_sem_recuo_nem_canal(self):
        fundo=self.fundo(tipo='PREGADO')
        self.assertAlmostEqual(fundo.chapa_largura_mm,800,places=2)
        self.assertAlmostEqual(fundo.chapa_comprimento_mm,800,places=2)
        self.assertFalse(fundo.children)
        self.assertAlmostEqual(self.f._caixa(fundo,self.conj.matrix_world.inverted())[0][1],280,places=2)

    def test_15_mm_vira_interno_rente_sem_canal(self):
        fundo=self.fundo(espessura_mm=15)
        self.assertEqual(fundo['fundo_tipo'],'APOIADO')
        self.assertAlmostEqual(fundo.chapa_largura_mm,764,places=2)
        self.assertFalse(fundo.children)
        self.assertAlmostEqual(self.f._caixa(fundo,self.conj.matrix_world.inverted())[1][1],280,places=2)

    def test_9_comercial_e_8_recusado_sem_criar_residuo(self):
        self.assertAlmostEqual(self.fundo(espessura_mm=9).chapa_espessura_mm,9)
        antes=set(bpy.data.objects)
        with self.assertRaises(ValueError):
            self.fundo(espessura_mm=8)
        self.assertEqual(set(bpy.data.objects),antes)

    def test_fundo_move_prateleiras_so_em_profundidade(self):
        grupo=self.prateleiras()
        fundo=self.fundo(tipo='APOIADO',espessura_mm=15)
        frente=grupo.matrix_world.copy()
        centros=[o.matrix_world.translation.z for o in addon.prateleiras.prateleiras_do_grupo(grupo)]
        fundo.location.y-=.08
        bpy.context.view_layer.update()
        self.f.verificar()
        self.assertEqual(grupo[self.f.VINCULO],fundo['chapa_uid'])
        self.assertAlmostEqual(addon.prateleiras.parametros(grupo)['profundidade_mm'],465,places=2)
        self.assertEqual(grupo.matrix_world,frente)
        self.assertEqual([o.matrix_world.translation.z for o in addon.prateleiras.prateleiras_do_grupo(grupo)],centros)

    def test_gavetas_encolhem_trilhos_para_caber(self):
        grupo=self.gavetas(550)
        fundo=self.fundo(tipo='APOIADO',espessura_mm=15)
        fundo.location.y-=.06
        bpy.context.view_layer.update()
        self.f.verificar()
        self.assertAlmostEqual(addon.gavetas.parametros(grupo)['profundidade_mm'],485,places=2)
        self.assertLessEqual(grupo[addon.gavetas.CHAVE_TRILHO_MM],450)
        self.assertEqual(grupo[self.f.VINCULO],fundo['chapa_uid'])

    def test_snap_no_fundo_cria_vinculo_so_no_mesmo_modulo(self):
        fundo=self.fundo(tipo='APOIADO',espessura_mm=15)
        grupo=self.prateleiras(400)
        ponto=grupo.matrix_world@Vector((.1,.545,.1))
        self.assertEqual(self.f.detectar_no_ponto(grupo,ponto),fundo)
        outro=addon.modulos.criar_armario(bpy.context,'Outro',800,800,560,fundo=False)
        g=addon.prateleiras.criar_prateleiras(bpy.context,outro,(18,18,18,18,0),dict(quantidade=1,profundidade_mm=400))
        self.assertFalse(self.f.associar(g,fundo))

    def test_sem_snap_perto_nao_cria_vinculo(self):
        self.fundo(tipo='APOIADO',espessura_mm=15)
        grupo=self.prateleiras(400)
        self.assertIsNone(self.f.detectar_no_ponto(grupo,grupo.matrix_world@Vector((.1,.4,.1))))
        self.assertNotIn(self.f.VINCULO,grupo)

    def test_desassociar_preserva_profundidade_e_nao_religa_no_timer(self):
        grupo=self.prateleiras(550)
        fundo=self.fundo(tipo='APOIADO',espessura_mm=15)
        self.f.selecionar(bpy.context,fundo)
        self.assertEqual(bpy.ops.object.cabinet_desassociar_fundo(),{'FINISHED'})
        antes=addon.prateleiras.parametros(grupo)['profundidade_mm']
        fundo.location.y-=.08
        bpy.context.view_layer.update()
        self.f.verificar()
        self.assertNotIn(self.f.VINCULO,grupo)
        self.assertAlmostEqual(addon.prateleiras.parametros(grupo)['profundidade_mm'],antes)

    def test_remover_fundo_limpa_recortes_nativos(self):
        self.fundo()
        self.assertTrue(addon.modulos.remover_fundo(self.conj))
        self.assertFalse([o for o in self.conj.children_recursive if o.get('fundo_canal_uid')])
        self.assertFalse([m for o in self.conj.children_recursive for m in o.modifiers if m.type=='BOOLEAN'])

    def test_undo_e_editmode_impedem_atualizacao(self):
        self.fundo()
        with patch.object(self.f,'atualizar_internos',side_effect=AssertionError('Escreveu no undo')):
            addon.eventos._desfazendo[0]=True
            self.f.verificar()
        addon.eventos._desfazendo[0]=False
        self.f.selecionar(bpy.context,addon.modulos.fundo_do_modulo(self.conj))
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            with patch.object(self.f,'atualizar_internos',side_effect=AssertionError('Escreveu em Edit Mode')):
                self.f.verificar()
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')

    def test_menu_fundos_e_icone_distinto(self):
        fundo=self.fundo()
        self.f.selecionar(bpy.context,fundo)
        self.assertEqual(addon.selecao._aba_da_selecao(fundo),'FUNDOS')
        for largura in (190,320,480,564):
            itens=addon.gaveta._widgets_aba_gaveta(bpy.context,largura,1400,0)
            self.assertTrue(any(i[5]==('operador','object.cabinet_criar_fundo') for i in itens))
            self.assertFalse([i for i in itens if i[0]+i[2]>min(largura-12,552)+.01])
        acao=('operador','object.cabinet_desassociar_fundo')
        self.assertEqual(addon.gaveta_eventos._icone_acao_gaveta(acao),'UNPINNED')
        self.assertIn('UNPINNED',bpy.types.UILayout.bl_rna.functions['operator'].parameters['icon'].enum_items.keys())

    def test_resize_do_modulo_preserva_tipo_espessura_e_recuo(self):
        fundo=self.fundo(tipo='APOIADO',espessura_mm=15)
        with patch.object(addon.portas,'atualizar_do_conjunto'):
            self.conj.conj_largura_mm=1000
        bpy.context.view_layer.update()
        self.assertEqual(fundo['fundo_tipo'],'APOIADO')
        self.assertAlmostEqual(fundo.chapa_espessura_mm,15)
        self.assertAlmostEqual(fundo.chapa_largura_mm,964,places=2)

    def test_modulo_girado_conserva_canal_e_normal(self):
        self.conj.rotation_euler.z=.73
        bpy.context.view_layer.update()
        fundo=self.fundo()
        self.assertAlmostEqual(fundo.chapa_largura_mm,778,places=2)
        self.assertAlmostEqual(abs(fundo.matrix_world.to_3x3().col[2].dot(self.conj.matrix_world.to_3x3().col[1])),1,places=5)

    def test_fundo_afastado_devolve_profundidade_do_vinculo(self):
        grupo=self.prateleiras(550)
        fundo=self.fundo(tipo='APOIADO',espessura_mm=15)
        fundo.location.y-=.08
        bpy.context.view_layer.update()
        self.f.verificar()
        fundo.location.y+=.08
        bpy.context.view_layer.update()
        self.f.verificar()
        self.assertAlmostEqual(addon.prateleiras.parametros(grupo)['profundidade_mm'],545,places=2)

    def test_ignora_fundo_sem_sobreposicao_vertical(self):
        grupo=self.prateleiras(400)
        fundo=self.fundo(tipo='APOIADO',espessura_mm=15)
        fundo.location.z+=2
        bpy.context.view_layer.update()
        self.assertFalse(self.f.associar(grupo,fundo))

    def test_exclusao_nativa_limpa_cortador_e_booleanos_orfaos(self):
        fundo=self.fundo()
        bpy.data.objects.remove(fundo,do_unlink=True)
        self.f.verificar()
        self.assertFalse([o for o in bpy.data.objects if o.get('fundo_canal_uid')])
        self.assertFalse([m for o in self.conj.children_recursive for m in o.modifiers if m.type=='BOOLEAN'])

    def test_copia_e_restauro_devolvem_tipo_canal_e_profundidades(self):
        grupo=self.prateleiras(550)
        fundo=self.fundo()
        estado=self.f.copia(bpy.context,fundo.name)
        self.f.editar(bpy.context,fundo,'espessura_mm',15)
        self.f.restaurar(bpy.context,estado)
        self.assertEqual(fundo['fundo_tipo'],'CANAL')
        self.assertAlmostEqual(fundo.chapa_espessura_mm,6)
        self.assertEqual(addon.prateleiras.parametros(grupo),estado['grupos'][0][2])

    def test_movimento_sem_espaco_restaura_fundo_sem_apagar_gavetas(self):
        grupo=self.gavetas(550)
        fundo=self.fundo(tipo='APOIADO',espessura_mm=15)
        antes=fundo.matrix_world.copy()
        pecas={o.name:o.data for o in grupo.children_recursive if o.type=='MESH'}
        fundo.location.y-=.45
        bpy.context.view_layer.update()
        self.f.verificar()
        self.assertLess((fundo.matrix_world.translation-antes.translation).length,.000001)
        self.assertIn('fundo_erro',fundo)
        self.assertEqual({o.name:o.data for o in grupo.children_recursive if o.type=='MESH'},pecas)

    def test_profundidade_individual_nao_atravessa_fundo(self):
        grupo=self.gavetas(550)
        p=addon.gavetas.parametros(grupo)
        p['individuais']={'0':dict(profundidade_mm=550)}
        grupo[addon.gavetas.CHAVE_PARAMETROS]=p
        fundo=self.fundo(tipo='APOIADO',espessura_mm=15)
        fundo.location.y-=.08
        bpy.context.view_layer.update()
        self.f.verificar()
        self.assertAlmostEqual(addon.gavetas.parametros(grupo)['individuais']['0']['profundidade_mm'],465,places=2)

    def test_trocar_para_canal_escolhe_6_mm_e_preserva_malha(self):
        fundo=self.fundo(tipo='APOIADO',espessura_mm=15)
        malha=fundo.data
        self.f.editar(bpy.context,fundo,'tipo','CANAL')
        self.assertEqual(fundo['fundo_tipo'],'CANAL')
        self.assertAlmostEqual(fundo.chapa_espessura_mm,6)
        self.assertEqual(fundo.data,malha)

    def test_undo_redo_recupera_vinculo_sem_reter_referencias(self):
        grupo=self.prateleiras(550)
        fundo=self.fundo(tipo='APOIADO',espessura_mm=15)
        nomes=grupo.name,fundo.name,self.conj.name
        bpy.ops.ed.undo_push(message='Fundo original')
        fundo.location.y-=.08
        bpy.context.view_layer.update()
        self.f.verificar()
        bpy.ops.ed.undo_push(message='Fundo movido')
        self.conj=None
        del grupo,fundo
        bpy.ops.ed.undo()
        addon.eventos._fim_do_desfazer()
        self.f.verificar()
        self.assertAlmostEqual(addon.prateleiras.parametros(bpy.data.objects[nomes[0]])['profundidade_mm'],545,places=2)
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        self.f.verificar()
        self.assertAlmostEqual(addon.prateleiras.parametros(bpy.data.objects[nomes[0]])['profundidade_mm'],465,places=2)
        self.conj=bpy.data.objects[nomes[2]]

    def test_recuo_invalido_nao_cria_dados_e_edicao_restaura_valor(self):
        antes=set(bpy.data.objects)
        with self.assertRaises(ValueError):
            self.fundo(recuo_mm=1000)
        self.assertEqual(set(bpy.data.objects),antes)
        fundo=self.fundo()
        with self.assertRaises(ValueError):
            self.f.editar(bpy.context,fundo,'recuo_mm',1000)
        self.assertAlmostEqual(fundo['fundo_recuo_mm'],15)

    def test_espessura_dos_apoios_reduz_fundo_interno_sem_alterar_sua_espessura(self):
        fundo=self.fundo(tipo='APOIADO',espessura_mm=15)
        self.conj.conj_espessura_mm=25
        bpy.context.view_layer.update()
        addon.modulos.ajustar_fundo(self.conj)
        self.assertAlmostEqual(fundo.chapa_largura_mm,750,places=2)
        self.assertAlmostEqual(fundo.chapa_espessura_mm,15)

    def test_canal_movido_atualiza_recuo_mostrado_no_menu(self):
        fundo=self.fundo()
        fundo.location.y-=.08
        bpy.context.view_layer.update()
        self.f.verificar()
        self.assertAlmostEqual(fundo['fundo_recuo_mm'],95,places=2)

    def test_dois_fundos_usam_limite_mais_proximo(self):
        grupo=self.prateleiras(550)
        self.fundo(tipo='APOIADO',espessura_mm=15)
        segundo=self.fundo(tipo='APOIADO',espessura_mm=15)
        segundo.location.y-=.08
        bpy.context.view_layer.update()
        self.f.verificar()
        self.assertEqual(grupo[self.f.VINCULO],segundo['chapa_uid'])
        self.assertAlmostEqual(addon.prateleiras.parametros(grupo)['profundidade_mm'],465,places=2)

    def test_legado_sem_vinculo_nao_recebe_metadados_ou_reencaixe(self):
        fundo=addon.modulos.adicionar_fundo(self.conj)
        grupo=self.prateleiras(400)
        antes=repr(list(fundo.items()))
        p=addon.prateleiras.parametros(grupo)
        self.f.verificar()
        self.assertEqual(repr(list(fundo.items())),antes)
        self.assertEqual(addon.prateleiras.parametros(grupo),p)
        self.assertNotIn(self.f.VINCULO,grupo)

    def test_criacao_sem_capacidade_nao_deixa_cortador_nem_vinculo_parcial(self):
        grupo=self.gavetas(400)
        nomes={o.name for o in bpy.data.objects}
        p=addon.gavetas.parametros(grupo)
        with self.assertRaises(ValueError):
            self.fundo(recuo_mm=435)
        self.assertEqual({o.name for o in bpy.data.objects},nomes)
        self.assertEqual(addon.gavetas.parametros(grupo),p)
        self.assertNotIn(self.f.VINCULO,grupo)
        self.assertFalse([m for o in self.conj.children_recursive for m in o.modifiers if m.type=='BOOLEAN'])

    def test_ajustar_ponto_existente_religa_apos_desassociar(self):
        grupo=self.gavetas(550)
        fundo=self.fundo(tipo='APOIADO',espessura_mm=15)
        self.f.selecionar(bpy.context,fundo)
        bpy.ops.object.cabinet_desassociar_fundo()
        ponto=grupo.matrix_world@Vector((.1,.545,.1))
        self.assertIsNone(addon.gavetas._aplicar_ponto(grupo,2,ponto))
        self.assertEqual(grupo[self.f.VINCULO],fundo['chapa_uid'])
        fundo.location.y-=.08
        bpy.context.view_layer.update()
        self.f.verificar()
        self.assertAlmostEqual(addon.gavetas.parametros(grupo)['profundidade_mm'],465,places=2)

    def test_novo_fundo_herda_parametros_exibidos_do_selecionado(self):
        fundo=self.fundo(tipo='APOIADO',espessura_mm=15)
        self.f.selecionar(bpy.context,fundo)
        p=self.f.OBJECT_OT_criar_fundo._parametros_padrao(None)
        self.assertEqual(p['tipo'],'APOIADO')
        self.assertAlmostEqual(p['espessura_mm'],15)


with tempfile.TemporaryDirectory(prefix='cabinet_fundos_') as pasta:
    addon.opcoes._pasta_addon=lambda:pasta
    addon.biblioteca.pasta_biblioteca=lambda:pasta
    addon.register()
    resultado=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestFundos))
    addon.unregister()
    if not resultado.wasSuccessful():
        raise RuntimeError('Falha nos fundos')
