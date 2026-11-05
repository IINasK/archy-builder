"""Partitions: opening segmentation, native wood and independent systems."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from mathutils import Matrix, Vector
import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon
D, G, P = addon.divisorias, addon.gavetas, addon.prateleiras


class TestDivisorias(unittest.TestCase):
    def test_segmentos_mantem_blocagem_unica_e_hud_mostra_cotas_dos_dois_lados(self):
        original=self.estante(2)
        uid=original[D.CHAVE_BLOCAGEM]
        div=self.criar()
        grupos=sorted(P.grupos_do_modulo(self.conj),key=lambda g:g.matrix_world.translation.x)
        self.assertEqual(len(grupos),2)
        self.assertTrue(all(g[D.CHAVE_BLOCAGEM]==uid for g in grupos))
        P.selecionar(bpy.context,grupos[0],'GRUPO')
        self.assertTrue(grupos[1].select_get())
        itens=addon.hud._itens_hud(bpy.context)
        self.assertEqual(len(itens),1)
        geometria=addon.hud._geometria_do_item(*itens[0])
        vaos=[l for l in geometria['linhas'] if l.get('vao')]
        self.assertEqual(len(vaos),6)
        self.assertEqual({l['objeto'] for l in vaos},set(grupos))
        largura=(geometria['cantos'][1]-geometria['cantos'][0]).length*1000
        self.assertAlmostEqual(largura,964,places=2)
        self.assertFalse(any(l['tipo']=='divisorias' for l in geometria['linhas']))
        D.selecionar(bpy.context,div)
        itens=addon.hud._itens_hud(bpy.context)
        self.assertEqual([i[1] for i in itens],['DIVISORIAS'])
        self.assertEqual(len([l for l in D.linhas_hud(div,[])[1] if l.get('vao')]),2)

    def test_orientacao_ativa_filtra_cotas_mesmo_com_selecao_mista(self):
        pr=self.estante(2);div=self.criar()
        P.selecionar(bpy.context,pr,'GRUPO')
        div.select_set(True)
        self.assertTrue(all(i[1]!='DIVISORIAS' for i in addon.hud._itens_hud(bpy.context)))
        bpy.context.view_layer.objects.active=div
        self.assertTrue(all(i[1]!='PRATELEIRAS' for i in addon.hud._itens_hud(bpy.context)))

    def test_migracao_legada_reune_so_segmentos_que_compartilham_apoio_real(self):
        self.estante(2);self.criar()
        grupos=P.grupos_do_modulo(self.conj)
        for g in grupos:del g[D.CHAVE_BLOCAGEM]
        separado=P.criar_prateleiras(bpy.context,self.conj,(18,18,18,18,0),dict(quantidade=0,profundidade_mm=500))
        del separado[D.CHAVE_BLOCAGEM]
        uid=D.garantir_blocagem(grupos[0])
        self.assertEqual(grupos[1][D.CHAVE_BLOCAGEM],uid)
        self.assertNotIn(D.CHAVE_BLOCAGEM,separado)
        self.assertEqual(set(D.grupos_da_blocagem(grupos[0])),set(grupos))

    def test_blocagens_independentes_no_mesmo_modulo_nao_sao_reunidas(self):
        original=self.estante(2);self.criar()
        uid=original[D.CHAVE_BLOCAGEM]
        outro=self.estante(2)
        self.assertNotEqual(outro[D.CHAVE_BLOCAGEM],uid)
        P.selecionar(bpy.context,original,'GRUPO')
        self.assertFalse(outro.select_get())
        self.assertEqual(len(D.grupos_da_blocagem(original)),2)

    def test_timer_recupera_blocagem_legada_sem_usuario_reselecionar(self):
        self.estante(2);self.criar()
        grupos=P.grupos_do_modulo(self.conj)
        for grupo in grupos:del grupo[D.CHAVE_BLOCAGEM]
        P.sincronizar_exclusoes_da_cena()
        self.assertTrue(grupos[0][D.CHAVE_BLOCAGEM])
        self.assertEqual(grupos[0][D.CHAVE_BLOCAGEM],grupos[1][D.CHAVE_BLOCAGEM])

    def test_inserir_em_vao_da_esquerda_preserva_prateleiras_e_gavetas_da_direita(self):
        original=self.estante(2);self.criar()
        grupos=sorted(P.grupos_do_modulo(self.conj),key=lambda g:g.matrix_world.translation.x)
        gavetas=G.criar_gavetas(bpy.context,self.conj,(509,18,18,600,0),
            dict(quantidade=3,profundidade_mm=500,cobertura='EMBUTIDA',puxador='SEM'))
        alvos=[*grupos[1].children_recursive,*gavetas.children_recursive]
        antes={o.name:(o.matrix_world.copy(),o.data.as_pointer() if o.type=='MESH' else 0) for o in alvos}
        estado=P.preparar_subdivisao_vao(grupos[0],0)
        P.subdividir_vao(bpy.context,grupos[0],estado,2)
        for obj in alvos:
            self.assertEqual((obj.matrix_world,obj.data.as_pointer() if obj.type=='MESH' else 0),antes[obj.name])
        self.assertTrue(all(bpy.data.objects[n].matrix_world.translation.x<0 for n in estado['novas']))
        self.assertEqual(len(P.prateleiras_do_grupo(grupos[1])),2)

    def setUp(self):
        addon.eventos._desfazendo[0] = False
        addon.chapas._ocupado[0] = False
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for c in list(bpy.data.collections):
            bpy.data.collections.remove(c)
        bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection
        bpy.context.view_layer.update()
        self.conj = addon.modulos.criar_armario(bpy.context, 'Caixa teste', 1000, 1200, 550)
        bpy.context.view_layer.update()
        self.lo, self.hi = G._limites(self.conj)

    def sistemas(self):
        # Upper storage compartment, three drawers below; full carcass opening.
        g = G.criar_gavetas(bpy.context, self.conj, (18, 18, 18, 582, 0),
            dict(quantidade=3, profundidade_mm=500, cobertura='EMBUTIDA', puxador='SEM'))
        p = P.criar_prateleiras(bpy.context, self.conj, (18, 18, 18, 18, 0),
            dict(quantidade=1, profundidade_mm=500, espacamento='LIVRE', vaos_mm=[950]))
        return g, p

    def criar(self, n=1, **p):
        return D.criar_divisorias(bpy.context, self.conj, (18, 18, 18, 18, 0),
            dict(quantidade=n, profundidade_mm=500, **p))

    def estante(self, quantidade=1):
        return P.criar_prateleiras(bpy.context, self.conj, (18,18,18,18,0),
                                  dict(quantidade=quantidade, profundidade_mm=500))

    def volume(self, obj):
        bpy.context.view_layer.update()
        avaliado = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        bm = bmesh.new()
        try:
            bm.from_mesh(avaliado.data)
            self.assertTrue(all(e.is_manifold for e in bm.edges))
            return abs(bm.calc_volume()) * 1e9
        finally:
            bm.free()

    def soma_prateleiras(self):
        return sum(self.volume(o) for g in P.grupos_do_modulo(self.conj) for o in P.prateleiras_do_grupo(g))

    def test_divisoria_rasa_deixa_vao_sem_exigir_profundidade_igual(self):
        grupo=self.estante(); original=P.prateleiras_do_grupo(grupo)[0]
        malha=original.data.as_pointer(); volume=self.volume(original)
        D.criar_divisorias(bpy.context,self.conj,(18,18,18,18,0),dict(profundidade_mm=300))
        self.assertEqual(len(P.grupos_do_modulo(self.conj)),2)
        self.assertEqual(original.data.as_pointer(),malha)
        self.assertAlmostEqual(self.soma_prateleiras(),volume-18*500*18,delta=5)

    def verificar_preenchimento(self, lado):
        grupo=self.estante(); original=P.prateleiras_do_grupo(grupo)[0]
        malha=original.data.as_pointer(); volume=self.volume(original)
        d=D.criar_divisorias(bpy.context,self.conj,(18,18,18,18,0),dict(profundidade_mm=300,preenchimento=lado))
        self.assertEqual(original.data.as_pointer(),malha)
        self.assertAlmostEqual(self.soma_prateleiras(),volume-18*300*18,delta=5)
        grupos=sorted(P.grupos_do_modulo(self.conj),key=lambda g:g.matrix_basis.translation.x)
        escolhido=grupos[0 if lado=='ESQUERDA' else 1]
        obj=P.prateleiras_do_grupo(escolhido)[0]
        modificador=next(m for m in obj.modifiers if m.type=='BOOLEAN')
        self.assertIs(modificador.object,D.pecas(d)[0])
        self.assertEqual(modificador.solver,'EXACT')
        return d,volume

    def test_prateleira_esquerda_preenche_so_a_lacuna_fora_da_divisoria(self):
        self.verificar_preenchimento('ESQUERDA')

    def test_prateleira_direita_preenche_so_a_lacuna_fora_da_divisoria(self):
        self.verificar_preenchimento('DIREITA')

    def test_boolean_nativo_acompanha_profundidade_editada(self):
        d,volume=self.verificar_preenchimento('ESQUERDA')
        self.assertIsNone(D.editar(bpy.context,d,'profundidade_mm',350))
        self.assertAlmostEqual(self.soma_prateleiras(),volume-18*350*18,delta=5)

    def test_preenchimento_com_modulo_rotacionado(self):
        import math
        self.conj.rotation_euler.z=math.radians(31)
        bpy.context.view_layer.update()
        self.verificar_preenchimento('ESQUERDA')

    def test_preenchimento_com_modulo_espelhado(self):
        self.conj.scale.x=-1
        bpy.context.view_layer.update()
        self.verificar_preenchimento('DIREITA')

    def test_prateleira_criada_depois_da_divisoria_rasa_preenche_lacuna(self):
        D.criar_divisorias(bpy.context,self.conj,(18,18,18,18,0),dict(profundidade_mm=300,preenchimento='DIREITA'))
        self.estante()
        self.assertAlmostEqual(self.soma_prateleiras(),964*500*18-18*300*18,delta=5)

    def test_encontro_coplanar_no_topo_da_prateleira_nao_corta_nem_recusa(self):
        grupo=self.estante(); obj=P.prateleiras_do_grupo(grupo)[0]
        _,alto=D._limites_malha(obj,self.conj.matrix_world)
        coordenadas=[tuple(v.co) for v in obj.data.vertices]
        D.criar_divisorias(bpy.context,self.conj,(18,18,alto.z-self.lo.z,18,0),dict(profundidade_mm=300))
        self.assertEqual(len(P.grupos_do_modulo(self.conj)),1)
        self.assertEqual([tuple(v.co) for v in obj.data.vertices],coordenadas)

    def test_divisoria_parcial_na_espessura_usa_recorte_real(self):
        grupo=self.estante(); obj=P.prateleiras_do_grupo(grupo)[0]
        baixo,alto=D._limites_malha(obj,self.conj.matrix_world)
        meio=(baixo.z+alto.z)/2
        volume=self.volume(obj)
        D.criar_divisorias(bpy.context,self.conj,(18,18,18,self.hi.z-meio,0),
            dict(profundidade_mm=300,preenchimento='ESQUERDA'))
        self.assertAlmostEqual(self.soma_prateleiras(),volume-18*300*9,delta=5)

    def test_divisorias_em_alturas_diferentes_nao_exigem_vao_comum(self):
        self.estante(3)
        D.criar_divisorias(bpy.context,self.conj,(18,18,18,800,0),dict(profundidade_mm=300))
        D.criar_divisorias(bpy.context,self.conj,(18,18,500,18,0),dict(profundidade_mm=300))
        self.assertEqual(sum(len(P.prateleiras_do_grupo(g)) for g in P.grupos_do_modulo(self.conj)),6)

    def test_gavetas_continuam_validando_travessia_antes_de_mutar(self):
        self.sistemas(); nomes=set(bpy.data.objects.keys())
        with self.assertRaisesRegex(ValueError,'depth'):
            D.criar_divisorias(bpy.context,self.conj,(18,18,18,18,0),dict(profundidade_mm=300))
        self.assertEqual(set(bpy.data.objects.keys()),nomes)

    def test_undo_redo_conserva_boolean_e_referencia_nativos(self):
        self.estante(); nome_modulo=self.conj.name
        bpy.ops.ed.undo_push(message='Antes do recorte parcial')
        d=D.criar_divisorias(bpy.context,self.conj,(18,18,18,18,0),dict(profundidade_mm=300,preenchimento='ESQUERDA'))
        bpy.ops.ed.undo_push(message='Encaixe com preenchimento')
        d=self.conj=None
        bpy.ops.ed.undo();addon.eventos._fim_do_desfazer()
        self.conj=bpy.data.objects[nome_modulo]
        self.assertEqual(len(P.grupos_do_modulo(self.conj)),1)
        self.conj=None
        bpy.ops.ed.redo();addon.eventos._fim_do_desfazer()
        self.conj=bpy.data.objects[nome_modulo]
        self.assertAlmostEqual(self.soma_prateleiras(),964*500*18-18*300*18,delta=5)

    def test_criar_divisorias_usa_assistente_e_snap_nativos(self):
        self.assertTrue(issubclass(D.OBJECT_OT_criar_divisorias, G.AssistenteDoVao))
        self.assertIn(D.OBJECT_OT_criar_divisorias, addon.CLASSES)
        estado = {'etapa': 'CANTO1'}
        D._assistente_divisorias[0] = estado
        try:
            self.assertIs(G._estado_criacao(), estado)
        finally:
            D.esquecer()
        grupo = self.criar()
        chapa, = D.pecas(grupo)
        self.assertAlmostEqual(chapa.chapa_espessura_mm, 18, places=3)
        self.assertTrue(all(abs(s - 1) < 1e-6 for s in chapa.scale))

    def test_tres_gavetas_viram_seis_e_maleiro_duas_prateleiras(self):
        g, p = self.sistemas()
        malha = P.prateleiras_do_grupo(p)[0].data.as_pointer()
        self.criar()
        gs, ps = G.grupos_do_modulo(self.conj), P.grupos_do_modulo(self.conj)
        self.assertEqual(len(gs), 2)
        self.assertEqual(sum(len(G.gavetas_do_grupo(o)) for o in gs), 6)
        self.assertEqual(sum(len(P.prateleiras_do_grupo(o)) for o in ps), 2)
        for o in gs + ps:
            dono = G if G.MARCA_GRUPO in o else P
            self.assertAlmostEqual(dono.vao(o)[0], 473, delta=.01)
        self.assertEqual(P.prateleiras_do_grupo(p)[0].data.as_pointer(), malha)
        f0 = G.frente_da_gaveta(G.gavetas_do_grupo(gs[0])[0])
        f1 = G.frente_da_gaveta(G.gavetas_do_grupo(gs[1])[0])
        self.assertIsNot(f0.data, f1.data)

    def test_varias_divisorias_repartem_a_espessura_correta(self):
        self.sistemas()
        grupo = self.criar(2)
        self.assertEqual(len(D.pecas(grupo)), 2)
        self.assertEqual(sum(len(G.gavetas_do_grupo(g)) for g in G.grupos_do_modulo(self.conj)), 9)
        for g in G.grupos_do_modulo(self.conj):
            self.assertAlmostEqual(G.vao(g)[0], (964 - 36) / 3, delta=.01)

    def test_sistemas_criados_depois_respeitam_a_divisoria(self):
        self.criar()
        self.sistemas()
        self.assertEqual(sum(len(G.gavetas_do_grupo(g)) for g in G.grupos_do_modulo(self.conj)), 6)
        self.assertEqual(sum(len(P.prateleiras_do_grupo(g)) for g in P.grupos_do_modulo(self.conj)), 2)

    def test_sistemas_novos_respeitam_divisorias_criadas_separadamente(self):
        self.criar(vaos_mm=[300, 646])
        self.criar(vaos_mm=[646, 300])
        self.sistemas()
        self.assertEqual(sum(len(G.gavetas_do_grupo(g)) for g in G.grupos_do_modulo(self.conj)), 9)
        self.assertEqual(sum(len(P.prateleiras_do_grupo(g)) for g in P.grupos_do_modulo(self.conj)), 3)

    def test_falha_de_espaco_nao_modifica_cena(self):
        self.sistemas()
        nomes = set(bpy.data.objects.keys())
        geometrias = {o.name: [tuple(v.co) for v in o.data.vertices]
                      for o in bpy.data.objects if o.type == 'MESH'}
        with self.assertRaises(ValueError):
            self.criar(10)
        self.assertEqual(set(bpy.data.objects.keys()), nomes)
        for nome, coords in geometrias.items():
            self.assertEqual([tuple(v.co) for v in bpy.data.objects[nome].data.vertices], coords)

    # Regression, fixed in v302: with two partitions, the first had already split
    # when the second was rejected, leaving an orphan copy in the scene.
    def test_segunda_divisoria_recusada_nao_deixa_copia(self):
        self.criar()
        D.criar_divisorias(bpy.context, self.conj, (18, 18, 18, 650, 0),
                           dict(quantidade=1, profundidade_mm=500, vaos_mm=[300, 646]))
        nomes = set(bpy.data.objects.keys())
        with self.assertRaises(ValueError):
            G.criar_gavetas(bpy.context, self.conj, (18, 18, 18, 18, 0),
                dict(quantidade=3, profundidade_mm=500, cobertura='EMBUTIDA', puxador='SEM'))
        self.assertEqual(set(bpy.data.objects.keys()), nomes)

    def test_material_espessura_topologia_e_altura_da_prateleira_preservados(self):
        _g, p = self.sistemas()
        prateleira, = P.prateleiras_do_grupo(p)
        mat = bpy.data.materials.new('Madeira teste')
        prateleira.data.materials.append(mat)
        z = prateleira.matrix_world.translation.z
        self.criar()
        for grupo in P.grupos_do_modulo(self.conj):
            obj, = P.prateleiras_do_grupo(grupo)
            self.assertIs(obj.material_slots[0].material, mat)
            self.assertAlmostEqual(obj.chapa_espessura_mm, 18, delta=.01)
            self.assertAlmostEqual(obj.matrix_world.translation.z, z, delta=1e-6)
            bm = bmesh.new()
            try:
                bm.from_mesh(obj.data)
                self.assertTrue(all(e.is_manifold for e in bm.edges))
                self.assertGreater(bm.calc_volume(), 0)
            finally:
                bm.free()

    def test_configuracoes_individuais_e_abertura_sao_copiadas(self):
        g, _p = self.sistemas()
        p = G.parametros(g)
        p['proporcoes'] = [1, 2, 1]
        p['individuais'] = {'1': {'recuo_mm': 5}}
        g[G.CHAVE_PARAMETROS] = p
        G.montar(g)
        G.definir_abertura(G.gavetas_do_grupo(g)[1], .5)
        self.criar()
        for grupo in G.grupos_do_modulo(self.conj):
            q = G.parametros(grupo)
            self.assertEqual(q['proporcoes'], [1, 2, 1])
            self.assertEqual(q['individuais']['1']['recuo_mm'], 5)
            self.assertAlmostEqual(G.gavetas_do_grupo(grupo)[1][G.CHAVE_ABERTURA], .5)

    def test_divisoria_parcial_separa_so_prateleiras_atingidas(self):
        p = P.criar_prateleiras(bpy.context, self.conj, (18, 18, 18, 18, 0),
            dict(quantidade=3, profundidade_mm=500))
        antes = [(o.name, o.matrix_world.copy(), o.data.as_pointer())
                 for o in P.prateleiras_do_grupo(p)]
        D.criar_divisorias(bpy.context, self.conj, (18, 18, 18, 650, 0),
                          dict(quantidade=1, profundidade_mm=500))
        grupos = P.grupos_do_modulo(self.conj)
        self.assertEqual(sum(len(P.prateleiras_do_grupo(g)) for g in grupos), 4)
        for nome, matriz, mesh in antes[1:]:
            obj = bpy.data.objects[nome]
            self.assertEqual(obj.matrix_world, matriz)
            self.assertEqual(obj.data.as_pointer(), mesh)

    def test_resize_do_modulo_mantem_divisoria_e_sistemas_encostados(self):
        self.sistemas()
        grupo = self.criar()
        self.conj.conj_largura_mm = 1200
        addon.modulos.absorver_conjuntos()
        D.atualizar_dependentes()
        for g in G.grupos_do_modulo(self.conj):
            self.assertAlmostEqual(G.vao(g)[0], 573, delta=.02)
        self.assertAlmostEqual(D.pecas(grupo)[0].chapa_espessura_mm, 18, delta=.01)

    def test_outro_modulo_e_sistemas_fora_do_corte_nao_mudam(self):
        outro = addon.modulos.criar_armario(bpy.context, 'Vizinho teste', 600, 800, 400)
        grupo = P.criar_prateleiras(bpy.context, outro, (18, 18, 18, 18, 0),
                                    dict(quantidade=1, profundidade_mm=350))
        objeto = P.prateleiras_do_grupo(grupo)[0]
        antes = (objeto.data.as_pointer(), objeto.matrix_world.copy())
        self.criar()
        self.assertEqual(len(P.grupos_do_modulo(outro)), 1)
        self.assertEqual((objeto.data.as_pointer(), objeto.matrix_world), antes)

    def test_puxadores_seguem_as_seis_frentes_sem_compartilhar_malhas(self):
        g, _p = self.sistemas()
        p = G.parametros(g)
        p['puxador'] = 'PERFIL'
        g[G.CHAVE_PARAMETROS] = p
        for gaveta in G.gavetas_do_grupo(g):
            G.colocar_puxador(gaveta, 'PERFIL')
        self.criar()
        puxadores = [o for grupo in G.grupos_do_modulo(self.conj)
                     for o in grupo.children_recursive if addon.puxadores._eh_puxador_parametrico(o)]
        self.assertEqual(len(puxadores), 6)
        self.assertEqual(len({o.data.as_pointer() for o in puxadores}), 6)
        for pux in puxadores:
            self.assertIsNotNone(G.gaveta_de(pux))
            addon.puxadores.posicionar_puxador(pux)

    def test_invalidar_um_campo_nao_deixa_sistemas_parcialmente_redimensionados(self):
        self.sistemas()
        grupo = self.criar()
        antes = [(o.name, G.vao(o)[0], o.matrix_basis.copy()) for o in G.grupos_do_modulo(self.conj)]
        self.assertIsNotNone(D.editar(bpy.context, grupo, 'vao_0', 80))
        for nome, largura, pose in antes:
            o = bpy.data.objects[nome]
            self.assertAlmostEqual(G.vao(o)[0], largura, delta=.01)
            self.assertEqual(o.matrix_basis, pose)

    def test_modulo_girado_divide_no_seu_referencial(self):
        self.conj.rotation_euler.z = .7
        self.conj.location = (2, 3, 1)
        bpy.context.view_layer.update()
        self.sistemas()
        self.criar()
        for grupo in G.grupos_do_modulo(self.conj):
            self.assertAlmostEqual(G.vao(grupo)[0], 473, delta=.01)

    def test_copia_nativa_conserva_inversa_de_parentesco_de_presets(self):
        _g, p = self.sistemas()
        chapa = P.prateleiras_do_grupo(p)[0]
        matriz = chapa.matrix_basis.copy()
        chapa.matrix_parent_inverse = Matrix.Translation((.1, -.2, .05))
        chapa.matrix_basis = chapa.matrix_parent_inverse.inverted() @ matriz
        bpy.context.view_layer.update()
        antes = chapa.matrix_world.copy()
        copia = D._duplicar(p)
        bpy.context.view_layer.update()
        obj = P.prateleiras_do_grupo(copia)[0]
        for r, s in zip(obj.matrix_world, antes):
            for x, y in zip(r, s):
                self.assertAlmostEqual(x, y, delta=1e-6)
        for o in [*copia.children_recursive, copia]:
            G._remover(o)
        self.criar()
        for grupo in P.grupos_do_modulo(self.conj):
            self.assertAlmostEqual(P.prateleiras_do_grupo(grupo)[0].matrix_world.translation.z,
                                   antes.translation.z, delta=1e-6)

    def test_gap_e_espessura_atualizam_os_apoios(self):
        self.sistemas()
        grupo = self.criar()
        self.assertIsNone(D.editar(bpy.context, grupo, 'vao_0', 400))
        self.assertEqual(sorted(round(G.vao(g)[0]) for g in G.grupos_do_modulo(self.conj)), [400, 546])
        self.assertIsNone(D.editar(bpy.context, grupo, 'espessura_mm', 22))
        self.assertEqual(sorted(round(G.vao(g)[0]) for g in G.grupos_do_modulo(self.conj)), [471, 471])

    def test_restaurar_campo_devolve_divisoria_e_sistemas(self):
        self.sistemas()
        grupo = self.criar()
        estado = D.copia(grupo)
        D.editar(bpy.context, grupo, 'vao_0', 400)
        D.restaurar(estado)
        for g in G.grupos_do_modulo(self.conj):
            self.assertAlmostEqual(G.vao(g)[0], 473, delta=.01)

    def test_aba_campos_selecao_e_limites_do_menu(self):
        grupo = self.criar()
        D.selecionar(bpy.context, D.pecas(grupo)[0])
        self.assertEqual(addon.selecao._aba_da_selecao(bpy.context.object), 'DIVISORIAS')
        for largura in (190, 320, 482, 564):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1600)
            self.assertTrue(any(w[5] == ('operador', 'object.cabinet_internos') for w in widgets))
            campos = [w for w in widgets if w[5] and w[5][:2] == ('medida', 'divisorias')]
            self.assertGreaterEqual(len(campos), 7)
            self.assertTrue(all(w[0] + w[2] <= min(largura - 12, 552) + .01 for w in campos))

    def test_clique_simples_isola_grupo_e_duplo_isola_divisoria(self):
        # Regression v282: clicking and HUD must retain the same scope.
        grupo = self.criar(2)
        chapa = D.pecas(grupo)[1]
        addon.hud._selecionar_chapa_hud(bpy.context, chapa)
        op = SimpleNamespace(clique=False, modo='GRUPO', toggle=False, extend=False)
        evento = SimpleNamespace(mouse_region_x=50, mouse_region_y=60)
        class Contexto:
            region = SimpleNamespace(as_pointer=lambda: 4242)
            def __getattr__(self, nome):
                return getattr(bpy.context, nome)
        with patch.object(addon.hud, '_raio_hud', return_value=(chapa, None)), \
             patch.object(addon.hud, '_ferragem_sob_mouse', return_value=None), \
             patch.object(addon.portas_viewport, '_slider_sob_mouse', return_value=None), \
             patch.object(G, 'slider_sob_mouse', return_value=None):
            self.assertEqual(addon.selecao.OBJECT_OT_selecionar._invoke(op, Contexto(), evento), {'FINISHED'})
            self.assertEqual(set(bpy.context.selected_objects), {grupo, *D.pecas(grupo)})
            self.assertIs(bpy.context.object, grupo)
            self.assertEqual(bpy.context.scene.cabinet_aba, 'DIVISORIAS')
            self.assertEqual(addon.hud._itens_da_selecao(bpy.context), [(grupo, 'DIVISORIAS', [])])
            self.assertEqual(set(addon.selecao.malhas_para_editar(bpy.context)), set(D.pecas(grupo)))
            op.modo = 'INDIVIDUAL'
            addon.selecao.OBJECT_OT_selecionar._invoke(op, Contexto(), evento)
            self.assertEqual(bpy.context.selected_objects, [chapa])
            self.assertEqual(addon.selecao.malhas_para_editar(bpy.context), [])

    def test_hud_exibe_vaos_laterais_reais_sem_somar_espessura(self):
        grupo = self.criar(2, vaos_mm=[200, 300, 428])
        D.selecionar(bpy.context, grupo)
        geo = addon.hud._geometria_do_item(*addon.hud._itens_da_selecao(bpy.context)[0])
        linhas = geo['linhas']
        vaos = [l for l in linhas if l.get('vao')]
        self.assertEqual([l['face'] for l in vaos], [('V', k) for k in range(3)])
        self.assertEqual({l['rotulo'] for l in linhas if l.get('letra')}, {'A1', 'A2', 'A3'})
        for linha, valor in zip(vaos, (200, 300, 428)):
            self.assertAlmostEqual(addon.hud._valor_hud(linha), valor, delta=.01)
            self.assertAlmostEqual((linha['pontos'][1] - linha['pontos'][0]).length * 1000, valor, delta=.01)
        inversa = grupo.matrix_world.inverted()
        def projetar(p):
            local = inversa @ p * 1000
            return Vector((local.x, local.z))
        alvo = addon.hud._acertar_linhas_hud(geo, (100, 582), projetar)
        self.assertEqual(alvo['face'], ('V', 0))
        self.assertEqual(alvo['tipo'], 'divisorias')
        with patch.object(addon.hud, '_projetar_hud', side_effect=lambda c, p: projetar(p)):
            rotulos = addon.hud._rotulos_hud(bpy.context, geo, None)
        self.assertEqual(len(rotulos), 6)

    def test_hud_edita_vao_e_esc_restaura_tambem_dependentes(self):
        self.sistemas()
        grupo = self.criar()
        D.selecionar(bpy.context, grupo)
        geo = addon.hud._geometria_do_item(grupo, 'DIVISORIAS', [])
        alvo = next(l for l in geo['linhas'] if l.get('vao'))
        estado = addon.hud._estado_arraste_hud(bpy.context, alvo)
        addon.hud._aplicar_valor_hud(bpy.context, alvo, 400)
        self.assertEqual(sorted(round(G.vao(g)[0]) for g in G.grupos_do_modulo(self.conj)), [400, 546])
        addon.hud._restaurar_arraste_hud(bpy.context, estado)
        self.assertEqual([round(addon.hud._valor_hud(l)) for l in D.linhas_hud(grupo, [])[1] if l.get('vao')], [473, 473])
        for g in G.grupos_do_modulo(self.conj):
            self.assertAlmostEqual(G.vao(g)[0], 473, delta=.01)

    def test_modulo_selecionado_absorve_hud_da_divisoria(self):
        grupo = self.criar()
        addon.hud._selecionar_chapa_hud(bpy.context, D.pecas(grupo)[0])
        itens = addon.hud._itens_da_selecao(bpy.context)
        self.assertEqual([(o, modo) for o, modo, _c in itens], [(self.conj, 'GRUPO')])

    def test_undo_redo_restaura_quantidades_e_malhas_nativas(self):
        self.sistemas()
        nomes = set(bpy.data.objects.keys())
        bpy.ops.ed.undo_push(message='Antes de dividir')
        self.criar()
        bpy.ops.ed.undo_push(message='Vao dividido')
        self.conj = None
        bpy.ops.ed.undo()
        addon.eventos._fim_do_desfazer()
        self.assertEqual(set(bpy.data.objects.keys()), nomes)
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        self.conj = next(o for o in bpy.data.objects if addon.chapas.MARCA_CONJUNTO in o)
        self.assertEqual(sum(len(G.gavetas_do_grupo(g)) for g in G.grupos_do_modulo(self.conj)), 6)


with tempfile.TemporaryDirectory(prefix='cabinet_divisorias_') as pasta:
    with patch.object(addon.biblioteca, 'pasta_biblioteca', return_value=pasta), \
         patch.object(addon.opcoes, '_pasta_addon', return_value=pasta):
        addon.register()
        try:
            resultado = unittest.TextTestRunner(verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(TestDivisorias))
        finally:
            addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError("Partition tests failed")
