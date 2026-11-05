"""Run: blender --background --factory-startup --python-exit-code 1 --python tests/test_sidebar_blender.py"""
import os
import sys
import inspect
import unittest
from types import SimpleNamespace

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon



def relativo(bloco):
    """Return the block with y relative to its first widget. In the Doors tab it moves down to accommodate Create Doors at the top (Epic 2.3); content and relative field positions remain identical."""
    if not bloco:
        return bloco
    y0 = bloco[0][1]
    return [(b[0], b[1] - y0) + tuple(b[2:]) for b in bloco]


class _Contexto:
    """Provide bpy.context with a chosen-size region for hit testing."""

    def __init__(self, largura, altura):
        self.region = SimpleNamespace(width=largura, height=altura)

    def __getattr__(self, nome):
        return getattr(bpy.context, nome)


class TestGaveta(unittest.TestCase):
    def contexto_abas(self, largura=190, altura=900):
        g = addon.gaveta
        tela = bpy.context.screen
        for chave, valor in ((g._CHAVE_SUSPENSO, ''), (g._CHAVE_OPCOES, 0),
                             (g._CHAVE_ROLAGEM, 0), (g._CHAVE_ROLAGEM_BIB, 0)):
            anterior = tela.get(chave)
            def restaurar(chave=chave, anterior=anterior):
                if anterior is None:
                    tela.pop(chave, None)
                else:
                    tela[chave] = anterior
            self.addCleanup(restaurar)
            tela[chave] = valor
        ctx = _Contexto(largura, altura)
        ctx.area = SimpleNamespace(tag_redraw=lambda: None, as_pointer=lambda: 0)
        return ctx

    def clicar_aba(self, ctx, widget):
        evento = SimpleNamespace(type='LEFTMOUSE', value='PRESS',
                                 mouse_region_x=widget[0] + widget[2] / 2,
                                 mouse_region_y=widget[1] + widget[3] / 2)
        return addon.gaveta_eventos.OBJECT_OT_interagir_gaveta.invoke(
            SimpleNamespace(report=lambda *_a: None), ctx, evento)

    def test_abas_mudam_para_lista_no_limite_real_da_fonte(self):
        import blf
        import math
        g = addon.gaveta
        self.contexto_abas()
        blf.size(0, 12)
        minimo = max(blf.dimensions(0, curto)[0] + 18 for _, curto, _ in g.ABAS_GAVETA)
        limite = math.ceil(minimo * len(g.ABAS_GAVETA) + 4 * (len(g.ABAS_GAVETA) - 1) + 24)
        # Reproduction: seven cells at 190 px clipped even abbreviations.
        self.assertLess((190 - 24 - 24) / 7, minimo)
        for largura in (190, 320, limite - 1, limite, 564):
            cab = g._partes_gaveta(g._widgets_gaveta(bpy.context, largura, 900))[0]
            self.assertEqual(len(cab), 1 if largura < limite else len(g.ABAS_GAVETA))
            for v in cab:
                self.assertGreaterEqual(v[0], 12)
                self.assertLessEqual(v[0] + v[2], largura - 12 + .01)
                blf.size(0, 12)
                self.assertLessEqual(blf.dimensions(0, v[4])[0] + (30 if len(cab) == 1 else 18), v[2])

    def test_lista_das_abas_abre_e_seleciona_as_sete_categorias(self):
        g = addon.gaveta
        ctx = self.contexto_abas()
        for rotulo, _, aba in g.ABAS_GAVETA:
            cab = g._partes_gaveta(g._widgets_gaveta(ctx, 190, 900))[0]
            self.assertEqual(self.clicar_aba(ctx, cab[0]), {'FINISHED'})
            itens = g._widgets_gaveta(ctx, 190, 900)
            flutuante = g._separar_flutuante(g._partes_gaveta(itens)[2])[1]
            self.assertEqual([v[4] for v in flutuante[1:]], [a[0] for a in g.ABAS_GAVETA])
            # Switching uses the same dispatch and resets scrolling.
            ctx.screen[g._CHAVE_ROLAGEM] = 80
            alvo = next(v for v in flutuante if v[5] == ('aba', aba))
            self.assertEqual(self.clicar_aba(ctx, alvo), {'FINISHED'})
            self.assertEqual(ctx.scene.cabinet_aba, aba)
            self.assertEqual(ctx.screen[g._CHAVE_SUSPENSO], '')
            self.assertEqual(ctx.screen[g._CHAVE_ROLAGEM], 0)
            self.assertEqual(g._widgets_gaveta(ctx, 190, 900)[0][4], rotulo)

    def test_lista_das_abas_tem_prioridade_e_nao_vaza_na_biblioteca(self):
        g = addon.gaveta
        ctx = self.contexto_abas()
        ctx.screen[g._CHAVE_SUSPENSO] = g.CHAVE_ABAS
        cab, conteudo, rodape = g._partes_gaveta(g._widgets_gaveta(ctx, 190, 900))
        flutuante = g._separar_flutuante(rodape)[1]
        self.assertEqual(g._widgets_interativos(ctx)[:len(g.ABAS_GAVETA)], flutuante[1:])
        self.assertLess(flutuante[0][1] + flutuante[0][3], cab[0][1])
        fx, fy, fw, fh = flutuante[0][:4]
        for v in conteudo:
            if v[5] and v[5][0] == 'divisa':
                continue
            self.assertFalse(v[0] < fx + fw and fx < v[0] + v[2]
                             and v[1] < fy + fh and fy < v[1] + v[3])
        self.assertFalse(any(v[5] and v[5][0] == 'nivel' for v in flutuante))

    def test_abas_ficam_fixas_sem_perder_primeiros_campos_na_rolagem(self):
        g = addon.gaveta
        ctx = self.contexto_abas()
        for largura in (190, 564):
            a = g._partes_gaveta(g._widgets_conteudo_gaveta(ctx, largura, 900, 0, 0))
            b = g._partes_gaveta(g._widgets_conteudo_gaveta(ctx, largura, 900, 90, 0))
            self.assertEqual(a[0], b[0])
            cima_a = g._paineis_gaveta(a[1])[0]
            cima_b = g._paineis_gaveta(b[1])[0]
            self.assertTrue(cima_a)
            self.assertEqual(cima_a[0][5][:2], ('escolha', 'criar_alvenaria'))
            self.assertEqual(len([v for v in cima_a if v[5] and v[5][0] == 'medida']), 3)
            self.assertEqual([v[5] for v in cima_a], [v[5] for v in cima_b])
            self.assertEqual([v[1] + 90 for v in cima_a], [v[1] for v in cima_b])

    def test_expandir_abas_preserva_selecao_e_descarta_lista_flutuante(self):
        g = addon.gaveta
        ctx = self.contexto_abas()
        self.cena.cabinet_aba = 'DIVISORIAS'
        objeto = bpy.context.object
        malha = [tuple(v.co) for v in objeto.data.vertices]
        selecionados = [o.name for o in bpy.context.selected_objects]
        ctx.screen[g._CHAVE_SUSPENSO] = g.CHAVE_ABAS
        for largura in (190, 564, 190):
            cab, _, rodape = g._partes_gaveta(g._widgets_gaveta(ctx, largura, 900))
            if largura == 564:
                self.assertEqual(len(cab), len(g.ABAS_GAVETA))
                self.assertFalse(g._separar_flutuante(rodape)[1])
            else:
                self.assertEqual(cab[0][4], "Shelves / Partitions")
            self.assertEqual(self.cena.cabinet_aba, 'DIVISORIAS')
            self.assertEqual([tuple(v.co) for v in objeto.data.vertices], malha)
            self.assertEqual([o.name for o in bpy.context.selected_objects], selecionados)

    def test_lista_das_abas_fecha_no_campo_e_no_vazio(self):
        g = addon.gaveta
        ctx = self.contexto_abas()
        campo = g._widgets_gaveta(ctx, 190, 900)[0]
        self.clicar_aba(ctx, campo)
        self.clicar_aba(ctx, g._widgets_gaveta(ctx, 190, 900)[0])
        self.assertEqual(ctx.screen[g._CHAVE_SUSPENSO], '')
        self.clicar_aba(ctx, campo)
        self.clicar_aba(ctx, (-20, 450, 2, 2, '', None))
        self.assertEqual(ctx.screen[g._CHAVE_SUSPENSO], '')
        self.assertEqual(self.cena.cabinet_aba, 'MODULOS')

    def test_lista_das_abas_e_cascata_compartilham_abertura_exclusiva(self):
        g = addon.gaveta
        ctx = self.contexto_abas()
        conteudo = g._partes_gaveta(g._widgets_gaveta(ctx, 190, 900))[1]
        campo = next(v for v in conteudo if v[5] and v[5][0] == 'suspenso' and len(v[5]) > 3)
        ctx.screen[g._CHAVE_SUSPENSO] = campo[5][1]
        self.clicar_aba(ctx, g._widgets_gaveta(ctx, 190, 900)[0])
        self.assertEqual(ctx.screen[g._CHAVE_SUSPENSO], g.CHAVE_ABAS)
        flutuante = g._separar_flutuante(g._partes_gaveta(g._widgets_gaveta(ctx, 190, 900))[2])[1]
        self.assertEqual([v[5][0] for v in flutuante[1:]], ['aba'] * len(g.ABAS_GAVETA))

    def test_desenho_restaura_campo_suspenso_apos_fundo_e_destaca_aba_atual(self):
        from unittest.mock import patch, Mock
        from contextlib import ExitStack
        g, d = addon.gaveta, addon.gaveta_desenho
        ctx = self.contexto_abas()
        ctx.region.type = 'WINDOW'
        ctx.screen[g._CHAVE_SUSPENSO] = g.CHAVE_ABAS
        cab, _, rodape = g._partes_gaveta(g._widgets_gaveta(ctx, 190, 900))
        linhas = g._separar_flutuante(rodape)[1][1:]
        chamadas = []
        def botao(x, y, w, h, **opcoes):
            chamadas.append(('botao', (x, y, w, h), opcoes.get('ativo', False)))
        def fundo(x, y, w, h, *_a):
            chamadas.append(('fundo', (x, y, w, h), False))
        with ExitStack() as pilha:
            pilha.enter_context(patch.object(d, 'bpy', SimpleNamespace(context=ctx)))
            pilha.enter_context(patch.object(d, 'gpu', SimpleNamespace(state=Mock())))
            pilha.enter_context(patch.object(g, '_eh_area_gaveta', return_value=True))
            pilha.enter_context(patch.object(g, '_widgets_gaveta', return_value=cab + rodape))
            pilha.enter_context(patch.object(g, '_botao_gaveta', side_effect=botao))
            pilha.enter_context(patch.object(g, '_retangulo_gaveta', side_effect=fundo))
            for nome in ('_retangulo_arredondado_gaveta', '_glow_gaveta', '_texto_cabivel_gaveta'):
                pilha.enter_context(patch.object(g, nome))
            pilha.enter_context(patch.object(d, '_seta_suspensa_gaveta'))
            d._desenhar_gaveta(tela=True)
        limpeza = chamadas.index(('fundo', (0, 852, 190, 48), False))
        self.assertIn(('botao', cab[0][:4], True), chamadas[limpeza + 1:])
        for v in linhas:
            self.assertIn(('botao', v[:4], v[5][1] == self.cena.cabinet_aba), chamadas)

    def test_botoes_criar_e_confirmar_solda_usam_destaque_laranja_existente(self):
        self.assertIn('object.cabinet_conectar_vertices',addon.gaveta.OPERADORES_DESTAQUE)
        self.assertIn('object.cabinet_confirmar_conexao',addon.gaveta.OPERADORES_DESTAQUE)
        estado=dict(fase='confirmar',pares=[('---','Destino','+++')],distancias=[.025])
        itens=addon.gaveta._painel_criacao_solda(bpy.context,[],8,1000,300,estado)
        criar=next(w for w in itens if w[4]=="Create Weld" and w[5])
        self.assertEqual(criar[5],('operador','object.cabinet_confirmar_conexao'))
        self.assertIn(criar[5][1],addon.gaveta.OPERADORES_DESTAQUE)

    def test_volume_livre_tem_destaque_e_mesmo_tamanho_do_criar(self):
        self.cena.cabinet_aba='GAVETAS'
        for obj in bpy.context.selected_objects:obj.select_set(False)
        for largura in (190,320,564):
            itens=addon.gaveta._widgets_gaveta(bpy.context,largura,1400)
            livre=next(i for i in itens if i[5]==('operador','object.cabinet_definir_area'))
            criar=next(i for i in itens if i[5] and i[5][0]=='gavetas')
            self.assertEqual(livre[4],"Define by Volume")
            self.assertEqual((livre[0],livre[2],livre[3]),(criar[0],criar[2],criar[3]))
            self.assertIn(livre[5][1],addon.gaveta.OPERADORES_DESTAQUE)

    def test_porta_selecionada_oferece_esconder_porta_e_agregados_no_menu(self):
        conj=addon.modulos.criar_armario(bpy.context,'Porta do menu',600,1200,550)
        grupo=addon.portas.porta_no_modulo(conj)
        folha=addon.portas._folhas_portas(grupo)[0]
        for obj in bpy.context.selected_objects:obj.select_set(False)
        folha.select_set(True);bpy.context.view_layer.objects.active=folha
        self.cena.cabinet_aba='PORTAS'
        for largura in (190,320,564):
            itens=addon.gaveta._widgets_gaveta(bpy.context,largura,1400)
            esconder=next(i for i in itens if i[5]==('operador','object.cabinet_esconder_porta'))
            self.assertEqual(esconder[4],"Hide Door and Attached Components")
            self.assertEqual(esconder[3],28)
            self.assertTrue(addon.selecao.OBJECT_OT_esconder_porta.poll(bpy.context))

    def test_criar_solda_tem_painel_proprio_sem_orcamento_e_distancia_editavel(self):
        estado=dict(moderna=True,fase='confirmar',pares=[('---','Destino','+++')],distancias=[.025])
        addon.solda._conexao_manual[0]=estado
        self.addCleanup(lambda:addon.solda._conexao_manual.__setitem__(0,None))
        for largura in (190,320,564):
            widgets=addon.gaveta._widgets_gaveta(bpy.context,largura,1200)
            rotulos=[w[4] for w in widgets]
            self.assertNotIn("Estimate",rotulos)
            self.assertFalse(any(w[5] and w[5][:2] == ('suspenso', addon.orcamento.SUSPENSO_COMODO)
                                 for w in widgets))
            self.assertIn("Create this weld?",rotulos)
            for rotulo in ("Create Weld","Cancel Weld","Previous Step","Reset Distance"):
                self.assertIn(rotulo,rotulos)
            medida=next(w for w in widgets if w[5] and w[5][:2]==('medida','solda_criacao'))
            self.assertEqual(medida[5][-1],25.)
            self.assertTrue(all(w[0]>=0 and w[0]+w[2]<=min(largura-12,552)+.01 for w in widgets))
        estado.update(fase='origem',pares=[],distancias=[])
        self.assertIsNone(addon.gaveta_eventos.aplicar_medida(bpy.context,'solda_criacao','','distancia',.012))
        widgets=addon.gaveta._widgets_gaveta(bpy.context,320,1200)
        campo=next(w for w in widgets if w[5] and w[5][:2]==('medida','solda_criacao'))
        self.assertEqual(campo[5][-1],12.)

    def test_icones_nativos_nao_migram_da_biblioteca_para_montagem(self):
        from unittest.mock import patch, Mock
        from contextlib import ExitStack
        from mathutils import Matrix
        e=addon.gaveta_eventos
        grupo=SimpleNamespace(botoes=[],campos=[],alca=SimpleNamespace(hide=False),
            gizmos=SimpleNamespace(new=lambda _tipo:SimpleNamespace(is_highlight=False,
                matrix_basis=Matrix.Identity(4),target_set_operator=lambda _op:None)),
            _preparar_hover=lambda *_a:None)
        pasta=('operador','object.cabinet_abrir_biblioteca')
        salvar=('operador','object.cabinet_salvar_biblioteca')
        corrente=('operador',addon.solda.OP_CORRENTE_OBJETO,True)
        reset=('operador',addon.solda.OP_RESETAR_DISTANCIA,True)
        abrir=Mock(return_value={'FINISHED'})
        externo=SimpleNamespace(ops=SimpleNamespace(wm=SimpleNamespace(path_open=abrir)))
        with patch.object(addon.biblioteca,'bpy',externo):
            self.assertEqual(addon.biblioteca.OBJECT_OT_abrir_pasta_biblioteca.execute(
                SimpleNamespace(report=lambda *_a:None),bpy.context),{'FINISHED'})
        abrir.assert_called_once_with(filepath=addon.biblioteca.pasta_biblioteca())
        with ExitStack() as pilha:
            pilha.enter_context(patch.object(addon.gaveta,'_eh_area_gaveta',return_value=True))
            widgets=pilha.enter_context(patch.object(addon.gaveta,'_widgets_interativos'))
            pilha.enter_context(patch.object(addon.biblioteca_faixa,'eh_faixa',return_value=False))
            pilha.enter_context(patch.object(addon.gaveta_desenho,'_desenhar_gaveta'))
            for acoes in ((pasta,salvar),(corrente,reset),(salvar,pasta),(reset,corrente),
                          (corrente,corrente),(pasta,salvar),(corrente,reset)):
                widgets.return_value=[(10+100*i,100,90,28,'',a) for i,a in enumerate(acoes)]
                e.VIEW3D_GGT_cabinet_gaveta.draw_prepare(grupo,bpy.context)
                visiveis=sorted((b for b in grupo.botoes if not b.hide),key=lambda b:b.matrix_basis[0][3])
                self.assertEqual(len(visiveis),len(acoes))
                for botao,acao in zip(visiveis,acoes):
                    # Native Button2D fixes its symbol on the first draw.
                    if not hasattr(botao,'icone_desenhado'):botao.icone_desenhado=botao.icon
                    self.assertEqual(botao.icone_desenhado,e._icone_acao_gaveta(acao))
                self.assertTrue(all(e._icone_ao_lado(a) for a in (corrente,reset)))
            self.assertEqual(len(grupo.botoes),5)

    def test_menu_chapa_chanfrada_exibe_cotas_da_viewport_com_campos_proprios(self):
        import bmesh
        o=addon.chapas.nova_chapa('Cotas dinamicas no menu',400,300,18,(0,0,0),(0,90,0),bpy.context)
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
        addon.hud._selecionar_chapa_hud(bpy.context,o,individual=True)
        for largura in (220,320,540):
            itens=addon.gaveta._widgets_gaveta(bpy.context,largura,1200)
            campos=[v for v in itens if v[5] and v[5][0]=='medida']
            self.assertEqual([v[5][3] for v in campos],['A1','A2','A3','A4','A5','A6','E'])
            self.assertTrue(all(v[5][1]=='cota' and v[5][2] for v in campos))
            self.assertEqual(len({v[5][2] for v in campos}),7)
            self.assertTrue(all(v[0]>=0 and v[0]+v[2]<=largura for v in campos))
            self.assertTrue(all(v[2]>=128 for v in campos))
            if largura==540:self.assertEqual(len({v[1] for v in campos}),3)

    def test_medidas_exibem_A1_A2_A3_sem_renomear_props_salvas(self):
        for largura in (220,320,540):
            itens=addon.gaveta._widgets_gaveta(bpy.context,largura,1200)
            campos=[v for v in itens if v[5] and v[5][0]=='medida']
            self.assertEqual({v[4].split(':')[0] for v in campos},{'A1','A2','A3'})
            self.assertEqual({v[5][3] for v in campos},{"Width","Height","Depth"})
        self.assertEqual(addon.hud.rotulo_medida("Thickness"),"Thickness")

    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        self.cena = bpy.context.scene
        self.cena.cabinet_aba = 'MODULOS'
        self.cena.chapa_bib_aberta = True
        self.cena.chapa_n1 = "Cabinets"
        self.cena.chapa_n2 = "Living Room"
        self.cena.chapa_n3 = "Base Cabinets"
        # Door parameters live in Scene and survive between tests. Without this reset,
        # one test's hinge adjustment makes the next fail for a reason
        # unrelated to that test.
        for nome in addon.portas._PROPS_PORTAS_CENA:
            self.cena.property_unset(nome)

    def widgets(self):
        return addon.gaveta._widgets_gaveta(bpy.context, 320, 1200)

    def test_medidas_da_selecao_sem_wireframe(self):
        tipos = [a[0] for *_, a in self.widgets() if a]
        self.assertEqual(tipos.count('medida'), 3)
        self.assertNotIn('wireframe', tipos)
        self.assertNotIn('divisor_medidas', tipos)
        largo = addon.gaveta._widgets_gaveta(bpy.context, 480, 1200)
        medidas = [v for v in largo if v[5] and v[5][0] == 'medida']
        self.assertEqual(len({v[1] for v in medidas}), 1)
        divisores = [v for v in largo if v[5]
                     and v[5][0] == 'divisor_medidas']
        self.assertEqual(len(divisores), 0)
        medio = [v for v in self.widgets() if v[5] and v[5][0] == 'medida']
        self.assertEqual(len({v[1] for v in medio}), 2)

    def test_objeto_livre_editavel(self):
        objeto = bpy.context.object
        resultado = bpy.ops.object.cabinet_editar_medida_gaveta(
            dono='livre', objeto=objeto.name,
            propriedade='dimensions_2', valor=1.25)
        self.assertEqual(resultado, {'FINISHED'})
        self.assertAlmostEqual(objeto.dimensions.z, 1.25)

    def test_rodape_abas_e_divisorias(self):
        bpy.ops.object.cabinet_marcar()
        bpy.context.object.chapa_modo = 'INDIVIDUAL'
        widgets = addon.gaveta._widgets_gaveta(bpy.context, 564, 1200)
        por_tipo = lambda tipo: [v for v in widgets if v[5] and v[5][0] == tipo]
        for tipo in ('aba', 'modo'):
            abas = por_tipo(tipo)
            self.assertAlmostEqual(abas[-1][0] + abas[-1][2], 552)
        # No footer: name, panel label and auto-regeneration were removed as requested.
        self.assertFalse(por_tipo('auto') or por_tipo('chapa')
                         or por_tipo('nome_objeto'))
        niveis = {v[5][3]: v[1] for v in por_tipo('suspenso') if len(v[5]) > 3}
        for divisor, nivel in zip(por_tipo('separador'), (1, 2)):
            centro = divisor[1] + divisor[3] / 2
            self.assertEqual(centro, (niveis[nivel] + niveis[nivel + 1] + 25) / 2)

    def test_alca_hit_test_retangular(self):
        ctx = SimpleNamespace(region=SimpleNamespace(height=1000))
        teste = addon.gaveta_eventos.VIEW3D_GT_alca_gaveta.test_select
        self.assertEqual(teste(None, ctx, (1, 86)), 0)
        self.assertEqual(teste(None, ctx, (25, 154)), 0)
        self.assertEqual(teste(None, ctx, (27, 120)), -1)
        self.assertEqual(teste(None, ctx, (10, 160)), -1)

    def test_quatro_medidas_responsivas_sem_sobrepor_abas(self):
        bpy.ops.object.empty_add()
        bpy.context.object[addon.chapas.MARCA_CONJUNTO] = 1
        for largura, linhas in ((564, 1), (320, 2), (190, 4)):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1200)
            medidas = [v for v in widgets if v[5] and v[5][0] == 'medida']
            abas = [v for v in widgets if v[5] and v[5][0] == 'modo']
            self.assertEqual(len(medidas), 4)
            self.assertEqual(len({v[1] for v in medidas}), linhas)
            self.assertLess(max(v[1] + v[3] for v in medidas), abas[0][1])

    def test_edicao_inline_confirma_unidades_e_cancela(self):
        classe = addon.gaveta_eventos.OBJECT_OT_editar_medida_gaveta
        objeto = bpy.context.object
        op = SimpleNamespace(valor=2.0, propriedade='dimensions_2',
                             dono='livre', objeto=objeto.name)
        op._encerrar = lambda: classe._encerrar(op)
        op.execute = lambda ctx: classe.execute(op, ctx)
        op.report = lambda *_: None
        area = SimpleNamespace(as_pointer=lambda: 123, tag_redraw=lambda: None)
        ctx = SimpleNamespace(area=area, scene=self.cena,
            window_manager=SimpleNamespace(modal_handler_add=lambda _: None))
        evento = lambda tipo, texto='', ctrl=False: SimpleNamespace(
            type=tipo, value='PRESS', ctrl=ctrl, unicode=texto)
        for texto, esperado in (('1250', 1.25), ('80 cm', 0.8), ('1,5 m', 1.5)):
            self.assertEqual(classe.invoke(op, ctx, None), {'RUNNING_MODAL'})
            classe.modal(op, ctx, evento('A', ctrl=True))
            classe.modal(op, ctx, evento('TEXTINPUT', texto))
            self.assertEqual(classe.modal(op, ctx, evento('RET')), {'FINISHED'})
            bpy.context.view_layer.update()
            self.assertAlmostEqual(objeto.dimensions.z, esperado, places=6)
            self.assertIsNone(addon.gaveta._edicao_gaveta[0])
        classe.invoke(op, ctx, None)
        classe.modal(op, ctx, evento('A', ctrl=True))
        classe.modal(op, ctx, evento('TEXTINPUT', '900'))
        self.assertEqual(classe.modal(op, ctx, evento('ESC')), {'CANCELLED'})
        self.assertAlmostEqual(objeto.dimensions.z, 1.5)

    def test_duplo_clique_na_foto_insere_no_cursor(self):
        from mathutils import Vector
        raiz = bpy.context.object
        raiz.location = (5.0, 5.0, 5.0)
        cursor = self.cena.cursor
        antes = cursor.location.copy()
        self.addCleanup(setattr, cursor, 'location', antes)
        cursor.location = (1.0, 2.0, 0.5)
        import time
        classe = addon.biblioteca.OBJECT_OT_arrastar_preset
        confirmados, cancelados = [], []
        base = raiz.location.copy()

        def posicionador():
            op = SimpleNamespace(
                _raizes=[raiz], _base={raiz: base.copy()},
                # Preset base center, where it attaches to the cursor.
                _ancora_base=Vector((5.0, 5.0, 4.0)), _valido=False,
                # The first click that opened the positioner was on the photo.
                _arrastando=True, _moveu=False, _mouse_inicio=(100, 100),
                _instante_inicio=time.monotonic(),
                _confirmar=lambda c: confirmados.append(1) or {'FINISHED'},
                _cancelar=lambda c: cancelados.append(1) or {'CANCELLED'})
            op._no_cursor = lambda c: classe._no_cursor(op, c)
            op._duplo_clique_na_foto = (
                lambda c, e: classe._duplo_clique_na_foto(op, c, e))
            return op

        def evento(valor, x=101):
            return SimpleNamespace(type='LEFTMOUSE', value=valor,
                                   mouse_x=x, mouse_y=100)

        # A double click inside the viewport is not on the photo: change nothing.
        op = posicionador()
        op._na_viewport = lambda _e: True
        op._arrastando = False
        self.assertEqual(classe.modal(op, bpy.context, evento('DOUBLE_CLICK')),
                         {'RUNNING_MODAL'})
        self.assertFalse(confirmados)
        # User-log sequence: RELEASE followed 67 ms later by PRESS in the same place;
        # Blender does not mark that event as DOUBLE_CLICK.
        for segundo in ('PRESS', 'DOUBLE_CLICK'):
            raiz.location = base
            op = posicionador()
            op._na_viewport = lambda _e: False
            self.assertEqual(classe.modal(op, bpy.context, evento('RELEASE')),
                             {'RUNNING_MODAL'})
            self.assertEqual(classe.modal(op, bpy.context, evento(segundo)),
                             {'FINISHED'}, segundo)
            self.assertEqual(tuple(raiz.location), (1.0, 2.0, 1.5))
        self.assertEqual(len(confirmados), 2)
        # A slow click, or one far from the photo, outside the viewport still cancels.
        for atraso, x in ((1.0, 101), (0.0, 160)):
            op = posicionador()
            op._na_viewport = lambda _e: False
            op._instante_inicio -= atraso
            classe.modal(op, bpy.context, evento('RELEASE'))
            self.assertEqual(classe.modal(op, bpy.context, evento('PRESS', x)),
                             {'CANCELLED'})
        self.assertEqual(len(confirmados), 2)
        self.assertEqual(len(cancelados), 2)

    def test_carrossel_arraste_nao_seleciona_categoria(self):
        # The draggable carousel belongs to the top strip; the menu uses a list.
        acao = ('navegar', 1, "Cabinets", 'cabinet_carrossel_1_None', 5, False)
        original = self.cena.chapa_n1
        op = SimpleNamespace(_carrossel=acao, _mouse_inicio=200,
                             _indice_inicio=0, _arrastou=False)
        ctx = SimpleNamespace(screen=bpy.context.screen,
                              area=SimpleNamespace(tag_redraw=lambda: None))
        evento = SimpleNamespace(type='MOUSEMOVE', mouse_region_x=50)
        addon.gaveta_eventos.OBJECT_OT_interagir_gaveta.modal(op, ctx, evento)
        self.assertGreater(ctx.screen[acao[3]], 0)
        evento = SimpleNamespace(type='LEFTMOUSE', value='RELEASE')
        addon.gaveta_eventos.OBJECT_OT_interagir_gaveta.modal(op, ctx, evento)
        self.assertEqual(original, self.cena.chapa_n1)
        ctx.screen[acao[3]] = 0

    def test_medidas_parametricas_da_chapa(self):
        bpy.ops.object.cabinet_marcar()
        tipos = [a[0] for *_, a in self.widgets() if a]
        self.assertEqual(tipos.count('medida'), 3)
        # Auto-regeneration was removed: panels always preserve modeled geometry.
        self.assertNotIn('auto', tipos)
        self.assertNotIn("Auto-regenerate", [v[4] for v in self.widgets()])
        self.assertNotIn('wireframe', tipos)
        resultado = bpy.ops.object.cabinet_editar_medida_gaveta(
            dono='objeto', objeto=bpy.context.object.name,
            propriedade='ui_chapa_largura', valor=1.5)
        self.assertEqual(resultado, {'FINISHED'})
        self.assertAlmostEqual(bpy.context.object.chapa_largura_mm, 1500.0)

    def test_cascata_e_presets_com_acoes(self):
        widgets = self.widgets()
        tipos = [a[0] for *_, a in widgets if a]
        self.assertIn('suspenso', tipos)
        self.assertNotIn('navegar', tipos)
        self.assertEqual(tipos.count('separador'), 2)
        self.assertTrue(all(v[3] == 1 for v in widgets
                            if v[5] and v[5][0] == 'separador'))
        self.assertIn('preset', tipos)
        # Insert/Edit/Lock use right-click, as in the strip.
        self.assertNotIn('item', tipos)
        self.assertIn('slider', tipos)
        self.assertNotIn('rolar_nivel', tipos)
        for nivel in (1, 2, 3):
            campos = [v for v in widgets if v[5] and v[5][0] == 'suspenso'
                      and len(v[5]) > 3 and v[5][3] == nivel]
            self.assertEqual(len(campos), 1)

    def test_preset_no_menu_usa_clique_direito_como_na_faixa(self):
        from unittest.mock import patch
        presets = [v for v in self.widgets() if v[5] and v[5][0] == 'preset']
        self.assertTrue(presets)
        # Without the button row, grid rows retain only the 8 px gap.
        alturas = sorted({v[1] for v in presets}, reverse=True)
        for cima, baixo in zip(alturas, alturas[1:]):
            self.assertAlmostEqual(cima - baixo, presets[0][3] + 8)
        alvo = presets[0]
        ctx = SimpleNamespace(window_manager=SimpleNamespace(modal_handler_add=lambda op: None))
        evento = SimpleNamespace(mouse_region_x=alvo[0] + 2, mouse_region_y=alvo[1] + 2)
        op = SimpleNamespace()
        with patch.object(addon.gaveta, '_widgets_interativos', return_value=[alvo]):
            r = addon.gaveta_eventos.OBJECT_OT_interagir_gaveta._botao_direito(op, ctx, evento)
        self.assertEqual(r, {'RUNNING_MODAL'})
        self.assertEqual(op._menu_item['arquivo'], alvo[5][1]['arquivo'])

    def test_desmarcar_preserva_malha_e_limpa_vinculos(self):
        bpy.ops.object.cabinet_marcar()
        obj = bpy.context.object
        malha = [tuple(v.co) for v in obj.data.vertices]
        vizinho = obj.copy()
        bpy.context.collection.objects.link(vizinho)
        vizinho['adj_x_pos'] = obj.name
        vizinho['adj_x_pos_uid'] = addon.chapas._garantir_uid(obj)
        bpy.ops.object.cabinet_marcar(alternar=True)
        self.assertNotIn(addon.chapas.MARCA_CHAPA, obj)
        self.assertFalse(obj.chapa_auto)
        self.assertEqual(malha, [tuple(v.co) for v in obj.data.vertices])
        self.assertNotIn('adj_x_pos_uid', vizinho)

    def test_engrenagem_no_rodape_abre_painel_para_cima(self):
        for aba in ('MODULOS', 'PORTAS', 'PUXADORES'):
            self.cena.cabinet_aba = aba
            _cab, _conteudo, rodape = addon.gaveta._partes_gaveta(
                addon.gaveta._widgets_gaveta(bpy.context, 320, 1400))
            # Collapsed: the footer contains only the gear at the sidebar bottom,
            # plus the move-to-strip button when the library is inside the menu.
            # Create Doors moved to the tab top (Epic 2.3), and its
            # Create Handle followed the same pattern, as requested.
            self.assertEqual([v[5] for v in rodape[1:] if not addon.visibilidade.eh_acao(v[5]) and v[5]!=('rotulo',)],
                             [('operador', addon.biblioteca_faixa.OP_LUGAR)], aba)
            if aba in {'PORTAS', 'PUXADORES'}:
                verbo = 'portas' if aba == 'PORTAS' else 'criar_puxador'
                botao = next(v for v in _conteudo if v[5] and v[5][0] == verbo)
                outros = [v for v in _conteudo if v != botao]
                # Immediately below the tabs, full width, above all other content.
                self.assertGreater(botao[1], max(v[1] + v[3] for v in outros))
                self.assertAlmostEqual(botao[2], min(540, 320 - 24))
            self.assertEqual(rodape[0][5], ('operador', addon.gaveta.OP_OPCOES))
            for v in rodape:
                if addon.visibilidade.eh_acao(v[5]) or v[5]==('rotulo',):
                    self.assertEqual(v[3],30)
                    continue
                self.assertLess(v[1] + v[3], addon.gaveta.ALTURA_RODAPE_GAVETA)
            if aba != 'MODULOS':
                # Item name and panel label stay outside both tabs.
                widgets = addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)
                self.assertFalse({v[5][0] for v in widgets if v[5]}
                                 & {'chapa', 'nome_objeto'}, aba)
            self.assertIsNone(addon.gaveta._retangulo_painel_opcoes(rodape))
            self.assertEqual(addon.gaveta_eventos._icone_acao_gaveta(rodape[0][5]), 'PREFERENCES')
        self.cena.cabinet_aba = 'MODULOS'
        tela = bpy.context.screen
        bpy.ops.object.cabinet_opcoes_gaveta()
        try:
            self.assertTrue(tela.get(addon.gaveta._CHAVE_OPCOES))
            for largura in (190, 320, 564):
                widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1400)
                caixas = [v[:4] for v in widgets]
                for i, (ax, ay, aw, ah) in enumerate(caixas):
                    for bx, by, bw, bh in caixas[i + 1:]:
                        self.assertFalse(ax < bx + bw - 0.01 and bx < ax + aw - 0.01
                                         and ay < by + bh - 0.01 and by < ay + ah - 0.01,
                                         "Width %d" % largura)
                _cab, _conteudo, rodape = addon.gaveta._partes_gaveta(widgets)
                # The panel expands upward from the gear.
                painel = addon.gaveta._retangulo_painel_opcoes(rodape)
                self.assertIsNotNone(painel)
                self.assertGreaterEqual(painel[1], addon.gaveta.ALTURA_RODAPE_GAVETA)
            # One control per option; theme settings live inside line color.
            controles = [v[5][1] for v in rodape if v[5] and (
                v[5][0] in {'suspenso', 'faixa'}
                or v[5][0] == 'cor' and v[5][2] == 'amostra')]
            self.assertEqual(sorted(controles), sorted(
                set(addon.opcoes.OPCOES_PADRAO) - {'hud_linha_tema', 'hud_realce_gizmo'}))
            # Estimate generation applies to the entire scene, so it belongs at the bottom
            # of Options rather than tab content, as requested.
            self.assertEqual([v[5][1] for v in rodape
                              if v[5] and v[5][0] == 'operador'],
                             [addon.gaveta.OP_OPCOES,
                              addon.biblioteca_faixa.OP_LUGAR,
                              addon.orcamento.OP_EXPORTAR_ORCAMENTO])
            self.assertNotIn(addon.orcamento.OP_EXPORTAR_ORCAMENTO,
                             [v[5][1] for v in _conteudo
                              if v[5] and v[5][0] == 'operador'])
            addon.opcoes._definir_opcao('hud_tamanho_rotulo', 22)
            self.assertEqual(addon.opcoes._opcao('hud_tamanho_rotulo'), 22)
        finally:
            addon.opcoes._definir_opcao('hud_tamanho_rotulo', 14)
            bpy.ops.object.cabinet_opcoes_gaveta()
        self.assertFalse(tela.get(addon.gaveta._CHAVE_OPCOES))

    def abrir_opcoes(self):
        tela = bpy.context.screen
        addon.gaveta._fechar_opcoes(tela)
        tela[addon.gaveta._CHAVE_OPCOES] = 1
        guardadas = {n: addon.opcoes._opcao(n) for n in addon.opcoes.OPCOES_PADRAO}
        self.addCleanup(addon.gaveta._fechar_opcoes, tela)
        self.addCleanup(lambda: [addon.opcoes._definir_opcao(n, v)
                                 for n, v in guardadas.items()])
        return tela

    def rodape(self, largura=320):
        return addon.gaveta._partes_gaveta(
            addon.gaveta._widgets_gaveta(bpy.context, largura, 1400))[2]

    def test_opcoes_compactas_em_uma_linha_por_opcao(self):
        self.abrir_opcoes()
        for largura in (190, 320, 564):
            rodape = self.rodape(largura)
            altura = addon.gaveta._retangulo_painel_opcoes(rodape)[3]
            # Label beside control; stack only in a narrow sidebar.
            # Estimate generation at the bottom, 34 px high.
            linhas = len(addon.gaveta.LINHAS_OPCOES)
            self.assertLessEqual(altura, 20 + linhas * (55 if largura < 300
                                                        else 29) + 30 + 34)
            for v in rodape:
                self.assertLessEqual(v[0] + v[2], min(largura - 12, 552) + 0.01)

    def test_lista_suspensa_flutua_por_cima_e_fecha_ao_escolher(self):
        tela = self.abrir_opcoes()
        for nome in addon.gaveta.SUSPENSOS_OPCOES:
            tela[addon.gaveta._CHAVE_SUSPENSO] = nome
            rodape = self.rodape()
            campo = next(v for v in rodape if v[5] and v[5][:2] == ('suspenso', nome))
            self.assertTrue(campo[5][2])
            _painel, flutuante = addon.gaveta._separar_flutuante(rodape)
            self.assertEqual(flutuante[0][5], ('fundo',))
            itens = flutuante[1:]
            self.assertEqual(len(itens), len(addon.gaveta.SUSPENSOS_OPCOES[nome]))
            self.assertEqual(sum(v[5][3] for v in itens), 1)
            for v in itens:
                self.assertEqual(v[5][5], addon.gaveta.ALVO_PREFERENCIAS)
                self.assertLess(v[1], campo[1])        # Opens downward.
            # Fits within the panel and receives input first; covered content is excluded.
            px, py, pw, ph = addon.gaveta._retangulo_painel_opcoes(rodape)
            fx, fy, fw, fh = flutuante[0][:4]
            self.assertGreaterEqual(fy, py)
            interativos = addon.gaveta._widgets_interativos(_Contexto(320, 1400))
            self.assertEqual(interativos[:len(itens)], itens)
            cobertos = [v for v in rodape[1:] if v not in flutuante
                        and v[0] < fx + fw and fx < v[0] + v[2]
                        and v[1] < fy + fh and fy < v[1] + v[3]]
            self.assertTrue(cobertos)
            for v in cobertos:
                self.assertNotIn(v, interativos)
        addon.opcoes._definir_opcao('unidade_padrao', 'CM')
        self.assertEqual(addon.opcoes._texto_medida(600), '60 cm')

    def test_faixas_de_1_a_50_arrastam_e_digitam(self):
        self.abrir_opcoes()
        for nome in ('hud_espessura_linha', 'hud_tamanho_rotulo'):
            minimo, maximo, _passo = addon.opcoes.FAIXAS_OPCOES[nome]
            self.assertEqual((minimo, maximo), (1, 50))
            self.assertEqual(addon.gaveta._valor_da_faixa(nome, -1), minimo)
            self.assertEqual(addon.gaveta._valor_da_faixa(nome, 2), maximo)
            for digitado, esperado in ((80, maximo), (0.2, minimo), (20, 20)):
                bpy.ops.object.cabinet_editar_medida_gaveta(
                    dono='opcao', propriedade=nome, valor=digitado)
                self.assertEqual(addon.opcoes._opcao(nome), esperado)
        self.assertIsInstance(addon.gaveta._valor_da_faixa('hud_tamanho_rotulo', 0.5), int)
        self.assertEqual(addon.gaveta._valor_da_faixa('hud_espessura_linha', 0.01), 1.5)
        for texto, valor in (('14', 14), ('1,5', 1.5), ('10 + 4', 14),
                             ('18px', 18)):
            self.assertAlmostEqual(addon.gaveta_desenho._ler_numero_digitado(texto), valor)
        faixa = next(v for v in self.rodape()
                     if v[5] and v[5][:2] == ('faixa', 'hud_tamanho_rotulo'))
        self.assertEqual(faixa[4], '20 px')

    def test_seletor_de_cor_abre_na_linha_e_sai_do_tema(self):
        tela = self.abrir_opcoes()
        self.assertTrue(addon.opcoes._opcao('hud_linha_tema'))
        tela[addon.gaveta._CHAVE_COR] = 'hud_rgb_linha'
        for largura in (190, 320, 564):
            # The open panel covers the fixed strip like dropdown lists.
            caixas = [v[:4] for v in self.rodape(largura) if not addon.visibilidade.eh_acao(v[5]) and v[5]!=('rotulo',)]
            for i, (ax, ay, aw, ah) in enumerate(caixas):
                for bx, by, bw, bh in caixas[i + 1:]:
                    self.assertFalse(ax < bx + bw - 0.01 and bx < ax + aw - 0.01
                                     and ay < by + bh - 0.01 and by < ay + ah - 0.01,
                                     "Width %d" % largura)
        partes = {v[5][2] for v in self.rodape()
                  if v[5] and v[5][0] == 'cor' and v[5][1] == 'hud_rgb_linha'}
        self.assertEqual(partes, {'amostra', 'atalho', 'quadro', 'matiz'})
        atalhos = [v for v in self.rodape() if v[5] and v[5][0] == 'cor'
                   and v[5][2] == 'atalho']
        self.assertEqual([v[5][5] for v in atalhos if v[5][4]], ['TEMA'])
        # Upper-right corner of the square = pure hue.
        addon.gaveta._matiz_cor['hud_rgb_linha'] = 0.0
        rgb = addon.gaveta._cor_do_seletor('hud_rgb_linha', 'quadro',
                                    addon.hud._cor_opcao('hud_rgb_linha'), 1, 1)
        addon.gaveta._aplicar_cor_opcao('hud_rgb_linha', rgb)
        self.assertFalse(addon.opcoes._opcao('hud_linha_tema'))
        self.assertEqual(addon.hud._cor_linhas_hud(bpy.context), (1.0, 0.0, 0.0, 1.0))
        # Retain hue when the color has no saturation.
        addon.gaveta._aplicar_cor_opcao('hud_rgb_realce', (1.0, 1.0, 1.0))
        addon.gaveta._cor_do_seletor('hud_rgb_realce', 'matiz', (1, 1, 1), 0.5, 0)
        h, _s, _v = addon.gaveta._hsv_opcao('hud_rgb_realce', (1.0, 1.0, 1.0))
        self.assertAlmostEqual(h, 0.5)
        amostra = next(v for v in self.rodape()
                       if v[5] and v[5][:3] == ('cor', 'hud_rgb_linha', 'amostra'))
        self.assertEqual(amostra[4], '#FF0000')

    def test_arraste_da_faixa_e_da_cor_e_esc_desfaz(self):
        self.abrir_opcoes()
        classe = addon.gaveta_eventos.OBJECT_OT_interagir_gaveta
        ctx = SimpleNamespace(screen=bpy.context.screen,
                              area=SimpleNamespace(tag_redraw=lambda: None))
        mover = lambda x, y=0: SimpleNamespace(
            type='MOUSEMOVE', value='NOTHING', mouse_region_x=x,
            mouse_region_y=y)
        esc = SimpleNamespace(type='ESC', value='PRESS')
        # Strip: 100 px track starting at x = 0; its endpoint is the maximum.
        acao = ('faixa', 'hud_tamanho_rotulo', 14, 1, 50)
        op = SimpleNamespace(_faixa={'acao': acao, 'x': 0, 'w': 100,
                                     'inicio': 30, 'arrastou': False})
        classe._modal_opcao(op, ctx, mover(32))           # Jitter: do not move.
        self.assertEqual(addon.opcoes._opcao('hud_tamanho_rotulo'), 14)
        classe._modal_opcao(op, ctx, mover(100))
        self.assertEqual(addon.opcoes._opcao('hud_tamanho_rotulo'), 50)
        self.assertEqual(classe._modal_opcao(op, ctx, esc), {'CANCELLED'})
        self.assertEqual(addon.opcoes._opcao('hud_tamanho_rotulo'), 14)
        # Color: 100 x 100 square; lower corner is black.
        acao = ('cor', 'hud_rgb_realce', 'quadro', addon.hud._cor_opcao('hud_rgb_realce'))
        op = SimpleNamespace(_cor={'acao': acao, 'ret': (0, 0, 100, 100),
                                   'original': (addon.opcoes._opcao('hud_rgb_realce'),
                                                {'hud_linha_tema': True,
                                                 'hud_realce_gizmo': False})})
        op._arrastar_cor = lambda c, x, y: classe._arrastar_cor(op, c, x, y)
        classe._modal_opcao(op, ctx, mover(50, -20))
        self.assertEqual(addon.opcoes._opcao('hud_rgb_realce'), (0.0, 0.0, 0.0))
        classe._modal_opcao(op, ctx, esc)
        self.assertEqual(addon.opcoes._opcao('hud_rgb_realce'), addon.opcoes.COR_REALCE_PADRAO)

    def test_realce_nas_cores_do_gizmo(self):
        tela = self.abrir_opcoes()
        self.assertFalse(addon.opcoes._opcao('hud_realce_gizmo'))
        tela[addon.gaveta._CHAVE_COR] = 'hud_rgb_realce'
        atalhos = [v[5] for v in self.rodape() if v[5] and v[5][0] == 'cor'
                   and v[5][2] == 'atalho']
        self.assertEqual(atalhos[0][5], 'GIZMO')
        self.assertFalse(atalhos[0][4])
        addon.opcoes._definir_opcao('hud_realce_gizmo', True)
        tema = bpy.context.preferences.themes[0].user_interface
        # Width = X, depth = Y, height = Z; thickness is orange.
        for letra, eixo in (('L', 'axis_x'), ('P', 'axis_y'), ('A', 'axis_z')):
            self.assertEqual(addon.hud._cor_realce_hud(letra)[:3],
                             tuple(getattr(tema, eixo))[:3], letra)
        for letra in ('E', ''):
            self.assertEqual(addon.hud._cor_realce_hud(letra)[:3],
                             addon.opcoes.COR_REALCE_PADRAO)
        self.assertEqual(addon.hud._letra_do_alvo({'tipo': 'espessura'}), 'E')
        self.assertEqual(addon.hud._letra_do_alvo({'tipo': 'medida', 'letra': 'A'}), 'A')
        amostra = next(v for v in self.rodape() if v[5]
                       and v[5][:3] == ('cor', 'hud_rgb_realce', 'amostra'))
        self.assertEqual((amostra[4], amostra[5][5]), ('Gizmo', 'GIZMO'))
        # Choosing a fixed color disables the gizmo; line color does not affect it.
        addon.gaveta._aplicar_cor_opcao('hud_rgb_linha', (1.0, 0.0, 0.0))
        self.assertTrue(addon.opcoes._opcao('hud_realce_gizmo'))
        addon.gaveta._aplicar_cor_opcao('hud_rgb_realce', (0.0, 1.0, 0.0))
        self.assertFalse(addon.opcoes._opcao('hud_realce_gizmo'))
        self.assertEqual(addon.hud._cor_realce_hud('L')[:3], (0.0, 1.0, 0.0))

    def test_modo_individual_ou_grupo_sai_da_selecao(self):
        bpy.ops.object.cabinet_marcar()
        chapa = bpy.context.object
        for o in bpy.context.selected_objects:
            o.select_set(False)
        chapa.select_set(True)
        self.assertEqual(addon.gaveta._modo_chapa(bpy.context, chapa), 'INDIVIDUAL')
        self.assertEqual(addon.gaveta._medidas_gaveta(bpy.context)[0], 'INDIVIDUAL')
        bpy.ops.mesh.primitive_cube_add(location=(5, 0, 0))
        outro = bpy.context.object
        chapa.select_set(True)
        bpy.context.view_layer.objects.active = chapa
        self.assertEqual(addon.gaveta._modo_chapa(bpy.context, chapa), 'GRUPO')
        # Buttons are indicators only: clicking neither highlights nor changes anything.
        modos = [v for v in self.widgets() if v[5] and v[5][0] == 'modo']
        self.assertEqual([v[5][2] for v in modos], [False, True])
        self.assertIsNone(addon.gaveta_desenho._chave_widget(modos[0][5]))
        outro.select_set(False)

    def test_aba_portas(self):
        self.cena.cabinet_aba = 'PORTAS'
        tipos = [a[0] for *_, a in self.widgets() if a]
        self.assertIn('portas', tipos)

    def portas(self, largura=320):
        self.cena.cabinet_aba = 'PORTAS'
        return addon.gaveta._widgets_gaveta(bpy.context, largura, 1400)

    def revelar(self, **escolhas):
        """The wizard answered these questions; the tab reveals their rows."""
        addon.portas._assistente_porta[0] = {'escolhas': escolhas}
        self.addCleanup(addon.portas._assistente_porta.__setitem__, 0, None)

    def escolhas(self, largura=320):
        alvo = {}
        for *_, acao in self.portas(largura):
            if acao and acao[0] == 'escolha':
                alvo.setdefault(acao[1], []).append(acao[2])
        return alvo

    def test_aba_portas_sem_porta_so_tem_criar_portas(self):
        # User request: remove door/split-door conversion and hinge choices from the tab;
        # without a door or wizard, show only the orange Create Doors action.
        widgets = self.portas()
        rotulos = [v[4] for v in widgets]
        self.assertFalse([r for r in rotulos if 'Converter' in r])
        self.assertNotIn("Hinge", rotulos)
        self.assertFalse([v for v in widgets if v[5] and v[5][0] == 'escolha'])
        self.assertEqual(len(addon.gaveta.COR_CRIAR_PORTAS), 4)
        self.assertGreater(addon.gaveta.COR_CRIAR_PORTAS[0], addon.gaveta.COR_CRIAR_PORTAS[2])
        # Icon buttons bypass the disabled-color rule because the gizmo already fades them.
        self.assertFalse(addon.gaveta_eventos._operador_apagado(
            ('operador', 'object.cabinet_vincular_puxador')))

    def test_pergunta_de_botao_da_gaveta_aparece_dentro_dela(self):
        # User design rule: popups only in the viewport; a sidebar button asks inside
        # the sidebar in a black box below Assembly.
        bpy.context.scene.cabinet_aba = 'MODULOS'
        op = 'object.cabinet_desagregar_selecao'
        try:
            addon.perguntas._perguntar(bpy.context, addon.solda.PERGUNTA_DESAGREGAR_OBJETO,
                             [("Yes, detach", 'CHECKMARK', op,
                               {'desagregar': True}),
                              ("No", 'X', op, {'desagregar': False})],
                             na_gaveta=True)
            for largura in (190, 320, 564):
                widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1200)
                caixa = next(v for v in widgets if v[5] == ('pergunta',))
                botoes = [v for v in widgets if v[5] and v[5][0] == 'operador'
                          and v[5][1] in (addon.solda.OP_CORRENTE_OBJETO,
                                          addon.solda.OP_RESETAR_DISTANCIA)]
                # Immediately below Assembly without covering buttons.
                self.assertLessEqual(caixa[1] + caixa[3],
                                     min(v[1] for v in botoes))
                respostas = [v for v in widgets if v[5] and v[5][0] == 'resposta']
                self.assertEqual([v[4] for v in respostas],
                                 ["Yes, detach", "No"])
                for v in respostas:          # Inside the box.
                    self.assertGreaterEqual(v[1], caixa[1])
                    self.assertLessEqual(v[0] + v[2], caixa[0] + caixa[2])
                # Text wraps to fit the box.
                self.assertEqual(' '.join(caixa[4].split('\n')),
                                 addon.solda.PERGUNTA_DESAGREGAR_OBJETO)
                self.assertTrue(all(len(l) * addon.gaveta.PX_CARACTERE_PERGUNTA
                                    <= caixa[2] - 20 + 1e-6
                                    for l in caixa[4].split('\n')))
            # The same question from the viewport does not enter the sidebar.
            addon.perguntas._pergunta_atual[0]['na_gaveta'] = False
            widgets = addon.gaveta._widgets_gaveta(bpy.context, 320, 1200)
            self.assertFalse(any(v[5] == ('pergunta',) for v in widgets))
        finally:
            addon.perguntas._pergunta_atual[0] = None
        self.assertIsNone(addon.gaveta_desenho._chave_widget(('pergunta',)))
        self.assertEqual(addon.gaveta_desenho._chave_widget(('resposta', 1)), 'resp:1')

    def test_montagem_tem_criar_solda_corrente_e_resetar_distancia(self):
        # User request v349: creating a weld must be explicit, even for a panel already
        # in the cabinet whose chain would otherwise detach it.
        bpy.context.scene.cabinet_aba = 'MODULOS'
        chapa = addon.chapas.nova_chapa("Panel", 600.0, 400.0, 18.0, (0, 0, 0),
                                 (0, 0, 0), bpy.context)
        bpy.ops.object.select_all(action='DESELECT')
        chapa.select_set(True)
        bpy.context.view_layer.objects.active = chapa
        for largura in (190, 320, 564):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1200)
            i = next(n for n, v in enumerate(widgets) if v[4] == "Assembly")
            botoes = [v[5][1] for v in widgets[i + 1:i + 4]]
            self.assertEqual(botoes, ['object.cabinet_conectar_vertices', addon.solda.OP_CORRENTE_OBJETO,
                                      addon.solda.OP_RESETAR_DISTANCIA])
            criar = widgets[i + 1]
            self.assertEqual(criar[4], "Create Weld")
            if largura >= 264:self.assertGreater(criar[2], widgets[i + 2][2])
            else:self.assertEqual(criar[2],widgets[i+2][2])
            self.assertGreater(criar[1], widgets[i + 2][1])
            for v in widgets[i+2:i+4]:
                self.assertTrue(addon.gaveta_eventos._icone_ao_lado(v[5]))
                self.assertIn(v[4],("Link","Reset Distance"))
            operadores = [v[5][1] for v in widgets if v[5] and v[5][0] == 'operador']
            for fora in ('object.cabinet_agrupar',
                         'object.cabinet_converter_modulo'):
                self.assertNotIn(fora, operadores)
        self.assertEqual(addon.gaveta_eventos._icone_acao_gaveta(
            ('operador', addon.solda.OP_RESETAR_DISTANCIA)), 'DRIVER_DISTANCE')

    def test_criar_solda_fica_no_menu_do_modulo_e_dispara_ao_soltar(self):
        bpy.context.scene.cabinet_aba = 'MODULOS'
        modulo = addon.modulos.criar_armario(bpy.context, 'Solda no menu', 600, 800, 550)
        addon.hud._selecionar_chapa_hud(bpy.context, modulo)
        self.assertIn('object.cabinet_conectar_vertices', addon.solda.OPERADORES_NO_SOLTAR)
        for largura in (190, 320, 564):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1200)
            criar = next(v for v in widgets if v[4] == "Create Weld")
            self.assertEqual(criar[5], ('operador', 'object.cabinet_conectar_vertices'))
            self.assertGreaterEqual(criar[0], 0)
            self.assertLessEqual(criar[0] + criar[2], largura - 12)
            self.assertFalse(addon.gaveta_eventos._operador_apagado(criar[5]))
        bpy.ops.object.select_all(action='DESELECT')
        self.assertFalse(any(v[4] == "Create Weld"
            for v in addon.gaveta._widgets_gaveta(bpy.context, 320, 1200)))

    def test_layout_da_aba_portas_do_usuario(self):
        # Each category appears when the wizard reaches it, as requested,
        # in the same order: Leaves then Opening. Rows mirror the viewport dialog,
        # are clickable and are answered by the modal operator.
        for largura in (190, 320, 564):
            fila = lambda ws, prop: [v for v in ws if v[5]
                                     and v[5][0] == 'escolha' and v[5][1] == prop]
            self.revelar(folhas=2)
            widgets = self.portas(largura)
            self.assertTrue(fila(widgets, 'porta_folhas'), largura)
            self.assertFalse(fila(widgets, 'porta_abertura'), largura)
            self.revelar(folhas=2, abertura='GIRO')
            widgets = self.portas(largura)
            abertura = fila(widgets, 'porta_abertura')
            folhas = fila(widgets, 'porta_folhas')
            self.assertLess(max(v[1] + v[3] for v in abertura),
                            min(v[1] for v in folhas))
            self.assertTrue(all(v[5][4] and v[5][5] == addon.portas.ALVO_ASSISTENTE
                                for v in abertura + folhas))
            self.assertEqual([v[5][2] for v in folhas if v[5][3]], [2])
            self.assertFalse(fila(widgets, 'porta_dobradica'))
            rotulos = [v[4] for v in widgets if v[5] is None]
            self.assertIn("Leaves", rotulos)
            self.assertNotIn("Hinge", rotulos)
            # Without a selected door, show no clearance/offset fields (Epics 2.1/2.4),
            # only the fixed dimensions block.
            campos = [v for v in widgets if v[5] and v[5][0] == 'medida']
            self.assertFalse([v for v in campos
                              if v[5][2].startswith('ui_porta_')], largura)

    def test_aba_portas_traz_o_que_estava_no_popup(self):
        # The popup was removed; all its options must be visible in the tab.
        self.revelar(folhas=2, abertura='GIRO')
        alvo = self.escolhas()
        for prop in ('porta_abertura', 'porta_folhas'):
            self.assertIn(prop, alvo, prop)
        # Hinge buttons were removed; four picked points determine the type automatically.
        self.assertNotIn('porta_dobradica', alvo)
        # Opening-axis controls were removed; the chain link determines them.
        self.assertNotIn('porta_orientacao', alvo)
        self.assertFalse(hasattr(self.cena, 'porta_orientacao'))
        # Individual/Group does not appear here: edit the leaf assembly,
        # never an isolated part.
        self.assertNotIn('modo', {v[5][0] for v in self.portas() if v[5]})

    def test_frente_e_espessuras_nao_sao_escolha(self):
        # The corner span defines the front; door thickness is leaf E and side-panel
        # thickness is cabinet E. None of these controls returns to the tab.
        for abertura in ('GIRO', 'BASCULANTE', 'CORRER'):
            for dobradica in ('RETA', 'CURVA', 'SUPER_CURVA'):
                self.cena.porta_abertura = abertura
                self.cena.porta_dobradica = dobradica
                alvo = self.escolhas()
                for prop in ('porta_frente', 'porta_espessura',
                             'porta_lateral'):
                    self.assertNotIn(prop, alvo)
                widgets = self.portas()
                # Only content after the separator: the fixed dimensions block retains
                # the selection's E field.
                corte = max(v[1] for v in widgets
                            if v[5] and v[5][0] == 'separador')
                rotulos = ' '.join(v[4] for v in widgets if v[1] < corte)
                self.assertNotIn("Thickness", rotulos)
                self.assertNotIn("Front", rotulos)
        for prop in ('porta_frente', 'porta_espessura', 'porta_lateral'):
            self.assertFalse(hasattr(bpy.types.Scene, prop), prop)

    def test_fila_do_wizard_nao_escreve_na_cena(self):
        # The wizard row answers its dialog through _responder_pela_gaveta
        # on its modal operator; the sidebar writes nothing to the scene.
        self.revelar(folhas=2, abertura='GIRO')
        acao = next(v[5] for v in self.portas()
                    if v[5] and v[5][0] == 'escolha'
                    and v[5][1] == 'porta_abertura' and v[5][2] == 'CORRER')
        self.assertEqual(addon.gaveta_eventos.OBJECT_OT_interagir_gaveta.poll(bpy.context),
                         addon.gaveta._eh_area_gaveta(bpy.context))
        self.assertEqual(acao[5], addon.portas.ALVO_ASSISTENTE)
        self.assertIn('ALVO_ASSISTENTE', inspect.getsource(
            addon.gaveta_eventos.OBJECT_OT_interagir_gaveta))

    def test_sem_porta_nao_ha_campos_de_folga(self):
        # Epics 2.1/2.4: clearance, offset and openings are not defined before drawing
        # the door; fields appear when the door is selected
        # (test_portas: campos_da_porta_seguem_a_abertura).
        for abertura in ('GIRO', 'BASCULANTE', 'CORRER'):
            self.cena.porta_abertura = abertura
            props = {v[5][2] for v in self.portas()
                     if v[5] and v[5][0] == 'medida'}
            self.assertFalse({p for p in props if p.startswith('ui_porta_')},
                             abertura)
        # Choices remain editable afterward; sliding doors use no hinge.
        self.cena.porta_abertura = 'CORRER'
        self.assertNotIn('porta_dobradica', self.escolhas())

    def test_folhas_limitadas_pela_abertura(self):
        self.cena.porta_folhas = 4
        self.cena.porta_abertura = 'BASCULANTE'
        self.assertEqual(self.cena.porta_folhas, 1)
        # The wizard row mirrors the dialog: 1 through 8; the opening type filters
        # later in _escolher.
        self.revelar(folhas=1, abertura='BASCULANTE')
        self.assertEqual(self.escolhas()['porta_folhas'], list(range(1, 9)))

    def test_wizard_aparece_na_aba_etapa_a_etapa(self):
        # User request: the viewport dialog is mirrored in the Doors tab;
        # each question appears when the wizard reaches it.
        def filas(**estado):
            addon.portas._assistente_porta[0] = estado
            self.addCleanup(addon.portas._assistente_porta.__setitem__, 0, None)
            ws = self.portas()
            return ([v[5][1] for v in ws if v[5] and v[5][0] == 'escolha'
                     and v[5][2] in (1, 'SIM', 'GIRO')],
                    [v[4] for v in ws if v[5] is None])
        self.assertEqual(filas(etapa='DIAGONAL', escolhas={})[0], [])
        props, rotulos = filas(etapa='CONFIRMAR', escolhas={})
        self.assertEqual(props, ['porta_confirmar'])
        self.assertIn("Are the dimensions correct?", rotulos)
        props, rotulos = filas(etapa='FOLHAS', escolhas={})
        self.assertEqual(props, ['porta_folhas'])
        self.assertIn("How many leaves?", rotulos)
        props, rotulos = filas(etapa='TIPO', escolhas={'folhas': 1},
                               tipos=addon.portas.TIPOS_SOBREPOSTA)
        self.assertEqual(props, ['porta_folhas', 'porta_abertura'])
        self.assertIn("Choose the opening type", rotulos)
        # After selecting the area, read-only door dimensions come first.
        addon.portas._assistente_porta[0] = dict(etapa='FOLHAS', escolhas={},
                                          medidas_porta=(600.0, 400.0, 18.0))
        medidas = [v[5] for v in self.portas() if v[5] and v[5][0] == 'medida']
        self.assertEqual([(m[3], m[4], m[2]) for m in medidas],
                         [("Width", 600.0, ''), ("Height", 400.0, ''),
                          ("Thickness", 18.0, '')])
        # At the edge: no count yet, only the message.
        props, rotulos = filas(etapa='EIXO', escolhas={
            'folhas': 1, 'abertura': 'GIRO'})
        self.assertNotIn('dobradicas_qtd', props)
        self.assertIn('Hinges: click their edge', rotulos)
        # Editable hinges and struts, as requested: segmented count,
        # with spacing/top distance in a field.
        aresta = {'lado': 'CIMA'}
        addon.portas._assistente_porta[0] = dict(
            etapa='PISTOES_OFFSET', aresta=aresta, qtd=3, margem=100.0,
            pqtd=2, poffset=120.0, escolhas={
                'folhas': 1, 'abertura': 'BASCULANTE', 'dobradica': 'RETA'})
        ws = self.portas()
        contadores = {v[5][1]: v[5][2] for v in ws if v[5]
                      and v[5][0] == 'contador'}
        self.assertEqual(contadores, {'dobradicas_qtd': 3, 'pistoes_qtd': 2})
        campos = {v[5][2]: (v[5][1], v[5][4]) for v in ws if v[5]
                  and v[5][0] == 'medida'}
        self.assertEqual(campos['dobradicas_margem_mm'], ('assistente', 100.0))
        self.assertEqual(campos['pistoes_offset_mm'], ('assistente', 120.0))
        rotulos = [v[4] for v in ws if v[5] is None]
        self.assertIn('Hinges: top edge', rotulos)
        # Automatic type is the highlighted thumbnail; opening also uses thumbnails.
        acesos = {v[5][1]: v[5][2] for v in ws if v[5] and v[5][0] == 'escolha'
                  and v[5][3] and len(v[5]) > 6}
        self.assertEqual(acesos, {'dobradica': 'RETA',
                                  'porta_abertura': 'BASCULANTE'})
        self.assertIn("Gas Stays", rotulos)
        # The hinge thumbnail is informational, with no target or click action.
        self.assertTrue(all(v[5][5] == addon.portas.ALVO_ASSISTENTE for v in ws
                            if v[5] and v[5][0] == 'escolha'
                            and v[5][1] != 'dobradica'))
        # User mockup: opening, hinge and hinge-count counter on one row;
        # the step acceptance action is a green square immediately beside
        # the edited field's right edge.
        def aceite(ws):
            return [v for v in ws if v[5] and v[5][0] == 'escolha'
                    and v[5][1] == addon.portas.CONFIRMAR_ETAPA]

        def campo(ws, prop):
            (v,) = [v for v in ws if v[5] and v[5][0] in {'contador', 'medida'}
                    and v[5][1 if v[5][0] == 'contador' else 2] == prop]
            return v
        for etapa, prop in (('QUANTIDADE', 'dobradicas_qtd'),
                            ('MARGEM', 'dobradicas_margem_mm'),
                            ('PISTOES_QTD', 'pistoes_qtd'),
                            ('PISTOES_OFFSET', 'pistoes_offset_mm')):
            addon.portas._assistente_porta[0] = dict(
                etapa=etapa, aresta=aresta, qtd=3, margem=100.0, pqtd=2,
                poffset=120.0, escolhas={'folhas': 1, 'abertura': 'BASCULANTE',
                                         'dobradica': 'RETA'})
            for largura in (190, 320):
                ws = self.portas(largura)
                (botao,) = aceite(ws)
                editado = campo(ws, prop)
                self.assertEqual(botao[5][2], etapa)
                self.assertEqual((botao[1], botao[3]), (editado[1], editado[3]))
                self.assertAlmostEqual(botao[0], editado[0] + editado[2] + 4)
            ws = self.portas(320)
            if etapa == 'QUANTIDADE':
                # Chosen opening and hinge on the same row as the counter.
                abertura, dobradica = sorted(
                    (v for v in ws if v[5] and v[5][0] == 'escolha'
                     and v[5][1] in {'porta_abertura', 'dobradica'}),
                    key=lambda v: v[0])
                self.assertEqual((abertura[5][2], dobradica[5][2]),
                                 ('BASCULANTE', 'RETA'))
                cont = campo(ws, prop)
                self.assertGreater(cont[0], dobradica[0] + dobradica[2])
                self.assertTrue(abertura[1] <= cont[1] <= abertura[1] + abertura[3])
        # At an edge, derive the type from coverage of the edge under the mouse.
        addon.portas._assistente_porta[0] = dict(
            etapa='EIXO', escolhas={'folhas': 1, 'abertura': 'GIRO'},
            coberturas={'cobertura_esq_e': 0.5}, embutida=False,
            snap=({'lado': 'ESQUERDA'}, None))
        acesos = [v[5][2] for v in self.portas() if v[5]
                  and v[5][0] == 'escolha' and v[5][1] == 'dobradica']
        self.assertEqual(acesos, ['CURVA'])

    def test_sem_selecao_cada_aba_so_tem_o_botao_de_criar(self):
        # User concept for all tabs: nothing selected means only Create Doors or
        # Create Handle; other controls appear during creation or selection.
        # Cabinets has no creation button because the library creates cabinets,
        # so it stays empty; estimate generation belongs in Options.
        bpy.ops.object.select_all(action='DESELECT')
        # Area creation (v372) adds only an alternative to picking points.
        for aba, esperado in (('PORTAS', {'portas', 'operador'}),
                              ('PUXADORES', {'criar_puxador'}),
                              ('MODULOS', set())):
            self.cena.cabinet_aba = aba
            _cab, conteudo, _rod = addon.gaveta._partes_gaveta(
                addon.gaveta._widgets_gaveta(bpy.context, 320, 1400))
            painel = addon.gaveta._paineis_gaveta(conteudo)[0]
            self.assertEqual({v[5][0] for v in painel if v[5]}, esperado, aba)
            if aba == 'PORTAS':
                self.assertEqual([v[5][1] for v in painel if v[5] and v[5][0] == 'operador'],
                                 ['object.cabinet_definir_area'])
        # An active but unselected object does not count either.
        self.assertIsNone(addon.gaveta._selecionado(bpy.context))

    def test_caixa_do_wizard_nunca_sai_da_viewport(self):
        # User screenshot: the door ended near the lower screen edge and the leaf-count
        # question was clipped.
        tamanho = (800, 500)
        for ancora in ((790, 5), (5, 5), (790, 495), (400, 250), (5, 495)):
            botoes = addon.assistente._botoes_assistente(
                Vector(ancora), addon.portas.OPCOES_CONFIRMAR, 1.0, tamanho,
                "Are the dimensions correct?")
            for (x, y, w, h), _c, _t in botoes:
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + w, tamanho[0])
            (x, y, w, h), _c, _t = botoes[0]
            self.assertLessEqual(y + h + 24, tamanho[1])     # The question.
        # Away from screen edges: beside the mouse as usual.
        (x, y, _w, _h), _c, _t = addon.assistente._botoes_assistente(
            Vector((400, 250)), addon.portas.OPCOES_FOLHAS, 1.0, tamanho, 'x')[0]
        self.assertEqual((x, y), (418, 236))

    def test_segmento_escolhido_acende(self):
        # Otherwise the user cannot tell which option is active.
        self.revelar(folhas=2, abertura='CORRER')
        acesos = [v[5] for v in self.portas()
                  if v[5] and v[5][0] == 'escolha'
                  and v[5][1] == 'porta_abertura' and v[5][3]]
        self.assertEqual([a[2] for a in acesos], ['CORRER'])
        fonte = inspect.getsource(addon.gaveta_desenho._desenhar_gaveta)
        self.assertIn("acao[0] == 'escolha' and acao[3]", fonte)

    def test_nenhum_widget_da_aba_portas_se_sobrepoe(self):
        # The dimension field is 37 px high while segmented rows leave 29 px;
        # without spacing, it covered the row above.
        wizard = dict(etapa='PISTOES_OFFSET', aresta={'lado': 'CIMA'}, qtd=3,
                      margem=100.0, pqtd=2, poffset=120.0, escolhas={
                          'folhas': 1, 'abertura': 'BASCULANTE',
                          'dobradica': 'RETA'})
        self.addCleanup(addon.portas._assistente_porta.__setitem__, 0, None)
        for largura, estado in ((l, e) for l in (190, 320, 564) for e in (
                {'escolhas': {'folhas': 2, 'abertura': 'GIRO'}}, wizard)):
            addon.portas._assistente_porta[0] = estado
            self.portas(largura)
            caixas = [v[:4] for v in addon.gaveta._widgets_interativos(_Contexto(largura,1400))]
            for i, (ax, ay, aw, ah) in enumerate(caixas):
                for bx, by, bw, bh in caixas[i + 1:]:
                    sobrepoe = (ax < bx + bw - 0.01 and bx < ax + aw - 0.01
                                and ay < by + bh - 0.01
                                and by < ay + ah - 0.01)
                    self.assertFalse(sobrepoe,
                                     "Width %d: %s covers %s"
                                     % (largura, (ax, ay, aw, ah),
                                        (bx, by, bw, bh)))

    def test_aba_portas_cabe_na_gaveta(self):
        for largura in (190, 320, 564):
            for x, _y, w, _h, _r, _a in self.portas(largura):
                self.assertGreaterEqual(x, 0)
                self.assertLessEqual(x + w, min(largura - 12, 552) + 0.01)

    def test_caixas_das_folhas_ficam_dentro_do_box(self):
        caixas = addon.biblioteca._caixas_das_folhas(600.0, 800.0, 400.0, 2)
        self.assertEqual(len(caixas), 2)
        for caixa in caixas:
            self.assertEqual(len(caixa), 8)
            for x, y, z in caixa:
                self.assertGreaterEqual(x, 0.0)
                self.assertLessEqual(x, 600.0)
                self.assertGreaterEqual(z, 0.0)
                self.assertLessEqual(z, 800.0)
                # Leaves belong at the front, not the back.
                self.assertLessEqual(y, 400.0 * 0.5)
        self.assertEqual(addon.biblioteca._caixas_das_folhas(600.0, 800.0, 400.0, 0), [])

    def test_folhas_nao_mudam_a_escala_do_box(self):
        # Scale comes from the box's eight corners; including leaves would make
        # the cabinet appear smaller than its actual size.
        sem = addon.biblioteca._pontos_wireframe(600.0, 800.0, 400.0)
        extras = [v for c in addon.biblioteca._caixas_das_folhas(600.0, 800.0, 400.0, 3)
                  for v in c]
        com = addon.biblioteca._pontos_wireframe(600.0, 800.0, 400.0, extras)
        self.assertEqual(sem, com[:8])
        self.assertEqual(len(com), 8 + len(extras))

    def test_folhas_para_wireframe_encontra_pelas_duas_pontas(self):
        bpy.ops.object.empty_add()
        conj = bpy.context.object
        conj[addon.chapas.MARCA_CONJUNTO] = 1
        bpy.ops.object.empty_add()
        grupo = bpy.context.object
        grupo[addon.chapas.MARCA_PORTAS] = 1
        grupo[addon.portas.CHAVE_MODULO_PORTA] = conj.name
        grupo.parent = conj
        for i in range(2):
            malha = bpy.data.meshes.new("Leaf")
            folha = bpy.data.objects.new('Folha_%d' % i, malha)
            bpy.context.collection.objects.link(folha)
            folha[addon.chapas.MARCA_CHAPA] = 1
            folha[addon.chapas.MARCA_FOLHA] = 1
            folha.parent = grupo
        # Through both the cabinet and the door itself.
        self.assertEqual(addon.gaveta._folhas_para_wireframe(conj, 'GRUPO'), 2)
        self.assertEqual(addon.gaveta._folhas_para_wireframe(grupo, 'GRUPO'), 2)
        # Regression: individual mode draws one panel; leaves appeared inside it
        # and broke the visualization.
        self.assertEqual(addon.gaveta._folhas_para_wireframe(conj, 'INDIVIDUAL'), 0)
        bpy.ops.mesh.primitive_cube_add()
        self.assertEqual(
            addon.gaveta._folhas_para_wireframe(bpy.context.object, 'GRUPO'), 0)

    def test_porta_para_wireframe_traz_o_vao_e_a_espessura(self):
        bpy.ops.object.empty_add()
        grupo = bpy.context.object
        grupo[addon.chapas.MARCA_PORTAS] = 1
        grupo['porta_vao_largura_mm'] = 600.0
        grupo['porta_vao_altura_mm'] = 800.0
        for i in range(2):
            malha = bpy.data.meshes.new("Leaf")
            folha = bpy.data.objects.new('Folha_%d' % i, malha)
            bpy.context.collection.objects.link(folha)
            folha[addon.chapas.MARCA_CHAPA] = 1
            folha[addon.chapas.MARCA_FOLHA] = 1
            folha.parent = grupo
            folha.chapa_espessura_mm = 20.0
        self.assertEqual(addon.gaveta._porta_para_wireframe(grupo),
                         (600.0, 800.0, 20.0, 2))
        bpy.ops.mesh.primitive_cube_add()
        self.assertIsNone(addon.gaveta._porta_para_wireframe(bpy.context.object))

    def test_bloco_de_medidas_so_na_aba_do_item(self):
        # User request: the menu shows settings relevant to selection. External-object
        # and cabinet dimensions belong in Cabinets; Doors and Handles show
        # only their creation button when no corresponding door or handle
        # is selected.
        alvo = {'medida', 'wireframe', 'modo'}

        def bloco(aba):
            self.cena.cabinet_aba = aba
            widgets = addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)
            _cab, conteudo, _rod = addon.gaveta._partes_gaveta(widgets)
            return [v[:4] + (v[5][0],) for v in addon.gaveta._paineis_gaveta(
                conteudo)[0] if v[5] and v[5][0] in alvo]

        modulos = bloco('MODULOS')
        self.assertTrue(modulos)
        self.assertNotIn('wireframe', [b[4] for b in modulos])
        self.assertEqual(bloco('PORTAS'), [])
        self.assertEqual(bloco('PUXADORES'), [])
        # Neither the item name nor panel label appears anywhere in the Doors tab.
        for selecionar in (True, False):
            for o in bpy.context.view_layer.objects:
                o.select_set(selecionar and o.type == 'MESH')
            self.cena.cabinet_aba = 'PORTAS'
            widgets = addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)
            verbos = {v[5][0] for v in widgets if v[5]}
            self.assertFalse(verbos & {'chapa', 'nome_objeto'})
            nomes = {o.name for o in bpy.data.objects}
            # Only inspect the tab panel: the library below shows preset names
            # that may happen to match, such as "Cube".
            _cab, conteudo, _rod = addon.gaveta._partes_gaveta(widgets)
            aba = addon.gaveta._paineis_gaveta(conteudo)[0]
            self.assertFalse(nomes & {v[4] for v in aba})
        self.cena.cabinet_aba = 'MODULOS'
        self.assertNotIn('nome_objeto', {v[5][0] for v in addon.gaveta._widgets_gaveta(
            bpy.context, 320, 1400) if v[5]})

    def test_sem_botoes_de_sincronizar_nem_recalcular(self):
        # Redundant, as reported by the user: the timer rereads dimensions and
        # the handler normalizes panels automatically.
        manuais = {'object.cabinet_sincronizar',
                   'object.cabinet_sincronizar_grupo',
                   'object.cabinet_normalizar'}
        a = addon.chapas.nova_chapa('A', 600.0, 400.0, 18.0, (0.0, 0.0, 0.0),
                             (0.0, 0.0, 0.0), bpy.context)
        b = addon.chapas.nova_chapa('B', 600.0, 400.0, 18.0, (0.0, 0.0, 0.3),
                             (0.0, 0.0, 0.0), bpy.context)
        bpy.ops.object.select_all(action='DESELECT')
        a.select_set(True)
        b.select_set(True)
        bpy.context.view_layer.objects.active = a
        for aba in ('MODULOS', 'PORTAS', 'PUXADORES'):
            self.cena.cabinet_aba = aba
            operadores = {v[5][1] for v in addon.gaveta._widgets_gaveta(
                bpy.context, 320, 1400) if v[5] and v[5][0] == 'operador'}
            self.assertFalse(operadores & manuais, aba)
        self.cena.cabinet_aba = 'MODULOS'

    def test_medidas_do_grupo_e_do_modulo_se_releem_sozinhas(self):
        a = addon.chapas.nova_chapa('A', 600.0, 400.0, 18.0, (0.0, 0.0, 0.0),
                             (0.0, 0.0, 0.0), bpy.context)
        b = addon.chapas.nova_chapa('B', 600.0, 400.0, 18.0, (0.0, 0.0, 0.3),
                             (0.0, 0.0, 0.0), bpy.context)
        bpy.ops.object.select_all(action='DESELECT')
        a.select_set(True)
        b.select_set(True)
        bpy.context.view_layer.objects.active = a
        # Loose group: scene fields follow the actual box.
        addon.chapas._ocupado[0] = True     # Old value, without resizing.
        try:
            self.cena.grupo_largura_mm = 1.0
        finally:
            addon.chapas._ocupado[0] = False
        addon.modulos._sincronizar_medidas_ativas()
        self.assertAlmostEqual(self.cena.grupo_largura_mm, 600.0, 1)
        # Cabinet: the same applies to Empty fields.
        conj = addon.modulos.agrupar_chapas(bpy.context, [a, b])
        a.chapa_largura_mm = 800.0
        addon.chapas.gerar_malha_chapa(a)
        addon.modulos._sincronizar_medidas_ativas()
        self.assertAlmostEqual(conj.conj_largura_mm, 800.0, 1)

    def test_nenhum_widget_da_aba_modulos_se_sobrepoe(self):
        # The same pairwise checks as the Doors tab caught the wireframe
        # overlapping the panel label's upper strip.
        self.cena.cabinet_aba = 'MODULOS'
        for largura in (190, 320, 564):
            caixas = [(v[0], v[1], v[2], v[3]) for v in
                      addon.gaveta._widgets_gaveta(bpy.context, largura, 1400)]
            for i, (ax, ay, aw, ah) in enumerate(caixas):
                for bx, by, bw, bh in caixas[i + 1:]:
                    sobrepoe = (ax < bx + bw - 0.01 and bx < ax + aw - 0.01
                                and ay < by + bh - 0.01
                                and by < ay + ah - 0.01)
                    self.assertFalse(sobrepoe, "Width %d: %s covers %s"
                                     % (largura, (ax, ay, aw, ah),
                                        (bx, by, bw, bh)))

    def botao_portas(self):
        return next((v[4], v[5]) for v in self.portas()
                    if v[5] and v[5][0] == 'portas')

    def test_botao_diz_o_que_falta_em_vez_de_nao_fazer_nada(self):
        # Regression: when an operator rejected an action, its warning did not reach
        # the sidebar, making clicking appear inert. The button conveys
        # the reason.
        rotulo, acao = self.botao_portas()
        self.assertEqual(acao[3], '')
        self.assertEqual(rotulo, "Create Doors")

        self.cena.porta_entre_folhas_mm = 5000.0
        rotulo, acao = self.botao_portas()
        self.assertTrue(acao[3])
        self.assertEqual(rotulo, acao[3])

    def test_dobradica_nasce_escolhida(self):
        # The mandatory enabled-field rule incorrectly left the creation button
        # disabled because no field could be active.
        self.assertEqual(self.cena.porta_dobradica, 'RETA')
        self.assertEqual(addon.portas._motivo_portas(self.cena), '')

    def test_toda_fila_de_segmentos_tem_um_aceso(self):
        for aberturas in ('GIRO', 'BASCULANTE', 'CORRER'):
            self.revelar(folhas=1, abertura=aberturas)
            por_prop = {}
            for *_, acao in self.portas():
                if acao and acao[0] == 'escolha':
                    por_prop.setdefault(acao[1], []).append(acao[3])
            for prop, acesos in por_prop.items():
                self.assertEqual(sum(1 for a in acesos if a), 1,
                                 "%s in %s" % (prop, aberturas))

    def test_botao_acende_enquanto_marca_o_vao(self):
        _, acao = self.botao_portas()
        self.assertFalse(acao[2])
        addon.portas._apanhando_vao[0] = True
        try:
            rotulo, acao = self.botao_portas()
            self.assertTrue(acao[2])
            self.assertIn('Marking', rotulo)
        finally:
            addon.portas._apanhando_vao[0] = False
        fonte = inspect.getsource(addon.gaveta_desenho._desenhar_gaveta)
        self.assertIn("acao[0] in _gaveta.BOTOES_CRIAR and acao[2]", fonte)
        self.assertEqual(addon.gaveta.BOTOES_CRIAR,
                         ('portas', 'gavetas', 'prateleiras', 'divisorias', 'criar_puxador'))

    def test_motivo_portas_reflete_a_aba(self):
        self.assertEqual(addon.portas._motivo_portas(self.cena), '')
        self.cena.porta_entre_folhas_mm = 5000.0
        self.assertTrue(addon.portas._motivo_portas(self.cena))

    def test_padrao_e_porta_dupla(self):
        self.assertEqual(self.cena.porta_folhas, 2)
        self.assertEqual(self.cena.porta_abertura, 'GIRO')

    def test_espessuras_saem_numericas_para_o_calculo(self):
        # Regression: thickness values are Enum strings. The operator needs a string,
        # but calculations fail on text, causing TypeError
        # in the preview and tab.
        p = addon.portas._parametros_portas_da_cena(self.cena)
        self.assertIsInstance(p['espessura_mm'], str)
        n = addon.portas._parametros_portas_da_cena(self.cena, numerico=True)
        self.assertIsInstance(n['espessura_mm'], float)
        self.assertIsInstance(n['lateral_mm'], float)
        n['dobradica'] = 'RETA'
        self.assertTrue(addon.portas._calcular_folhas_portas(600.0, 800.0, n))

    def test_aba_portas_com_grupo_selecionado_nao_quebra(self):
        # The tab shows group-leaf previews; a TypeError there would break drawing
        # of the entire sidebar rather than just that row.
        bpy.ops.object.empty_add()
        grupo = bpy.context.object
        grupo[addon.chapas.MARCA_PORTAS] = 1
        grupo['porta_vao_largura_mm'] = 600.0
        grupo['porta_vao_altura_mm'] = 800.0
        grupo['porta_parametros'] = {'abertura': 'GIRO', 'folhas': 2,
                                     'dobradica': 'RETA'}
        self.cena.porta_dobradica = 'RETA'
        widgets = self.portas()
        rotulos = [v[4] for v in widgets]
        # Avoid repeated dimensions: the per-leaf preview was removed.
        self.assertFalse(any('Cada folha' in r for r in rotulos), rotulos)
        # The tab reads the door directly without a read-parameters action;
        # creation of another door is disabled while this one remains selected.
        self.assertFalse(any('Ler parametros' in r for r in rotulos))
        botao = next(v[5] for v in widgets if v[5] and v[5][0] == 'portas')
        self.assertTrue(botao[4])

    def test_parametros_da_cena_cobrem_o_operador(self):
        # A missing name makes the operator use a default, exposing a value
        # the tab does not show.
        p = addon.portas._parametros_portas_da_cena(self.cena)
        self.assertEqual(set(p), set(addon.portas._PARAMETROS_PORTAS))

    def test_ler_do_grupo_traz_os_parametros(self):
        guardado = {'abertura': 'CORRER', 'folhas': 3, 'dobradica': 'RETA',
                    'espessura_mm': 20.0, 'lateral_mm': 15.0,
                    'folga_mm': 4.0, 'entre_folhas_mm': 2.0,
                    'afastamento_mm': 0.0, 'recuo_embutida_mm': 0.0,
                    'recuo_correr_mm': 25.0,
                    'entre_planos_mm': 2.0}
        bpy.ops.object.empty_add()
        falso = bpy.context.object
        falso['porta_parametros'] = guardado
        addon.portas._carregar_portas_na_cena(self.cena, falso)
        self.assertEqual(self.cena.porta_abertura, 'CORRER')
        self.assertEqual(self.cena.porta_folhas, 3)
        self.assertAlmostEqual(self.cena.porta_recuo_correr_mm, 25.0)

    def test_criar_portas_nao_abre_popup(self):
        # INVOKE would open a dialog; parameters already come from the tab.
        fonte = inspect.getsource(addon.assistente.OBJECT_OT_apanhar_vao_portas._concluir)
        self.assertIn("'EXEC_DEFAULT'", fonte)
        self.assertNotIn("'INVOKE_DEFAULT'", fonte)

    def test_responsividade_das_miniaturas(self):
        for largura in (190, 320, 620, 2056):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1200)
            self.assertTrue(all(v[0] + v[2] <= min(largura - 12, 552)
                                for v in widgets))
            fotos = [v for v in widgets if v[5] and v[5][0] == 'preset']
            self.assertTrue(fotos)
            for x, _y, w, h, _rotulo, _acao in fotos:
                self.assertLessEqual(x + w, largura - 12 + 0.01)
                self.assertAlmostEqual(w - 10, h - 27)
                self.assertLessEqual(x + w, 552)

    def test_slider_compacto_mantem_extremos_do_arraste(self):
        for largura in (190, 320, 564):
            slider = next(v for v in addon.gaveta._widgets_gaveta(
                bpy.context, largura, 1200) if v[5] and v[5][0] == 'slider')
            x, y, w, h = slider[:4]
            inicio, _, trilho = addon.gaveta._trilho_miniaturas_gaveta(x, y, w, h)
            self.assertLessEqual(w, 290)
            self.assertGreater(inicio, x)
            self.assertLessEqual(inicio + trilho + 6, x + w)
            op = SimpleNamespace(_inicio=inicio, _largura=trilho)
            ctx = SimpleNamespace(scene=self.cena,
                                  area=SimpleNamespace(tag_redraw=lambda: None))
            for posicao, esperado in ((inicio, 2), (inicio + trilho, 8)):
                addon.gaveta_eventos.OBJECT_OT_interagir_gaveta._atualizar(op, ctx, posicao)
                self.assertEqual(self.cena.chapa_tam_bloco, esperado)

    def test_retratos_tem_o_mesmo_quadrado_e_slider_no_titulo(self):
        # User request: handle, opening and hinge thumbnails use the same square size,
        # with one slider beside the title adjusting them all.
        g = addon.gaveta
        antes = self.cena.cabinet_tam_retrato
        self.addCleanup(setattr, self.cena, 'cabinet_tam_retrato', antes)
        opcoes = lambda n: tuple(('V%d' % i, 'T%d' % i, {}) for i in range(n))
        for tamanho in (g.LARGURA_RETRATO_MIN, 64, g.LARGURA_RETRATO_MAX):
            self.cena.cabinet_tam_retrato = tamanho
            for w in (166, 296, 540):
                itens = []
                g._carrossel_gaveta(itens, 12, 500, w, "Opening", 'p3', opcoes(3), 'V0')
                g._carrossel_gaveta(itens, 12, 300, w, "Handle Model",
                                    'p9', opcoes(9), 'V0')
                g._secao_ferragens_gaveta(
                    itens, 12, 100, w, {'DOBRADICA': {'qtd': 2, 'modelo': 'RETA'}},
                    g.ALVO_FERRAGENS, 'ferragens', separar=False)
                retratos = [v for v in itens if v[5] and v[5][0] == 'escolha'
                            and len(v[5]) > 6]
                self.assertEqual({v[2] for v in retratos}, {g._lado_retrato(w)}, w)
                self.assertEqual(g._lado_retrato(w), min(tamanho, (w - 8) / 3))
                sliders = [v for v in itens if v[5] == ('slider', 'retratos')]
                self.assertEqual(len(sliders), 3, w)
                for s in sliders:
                    titulo = next(v for v in itens if v[5] is None and v[1] == s[1])
                    self.assertLessEqual(titulo[0] + titulo[2], s[0])
                for v in itens:
                    self.assertLessEqual(v[0] + v[2], 12 + w + 0.01, (w, v))
        # Drag from minimum to maximum.
        x, y, w, h = 400, 0, g.LARGURA_SLIDER_RETRATO, 20
        inicio, _, trilho = g._trilho_slider_gaveta(('slider', 'retratos'), x, y, w, h)
        op = SimpleNamespace(_inicio=inicio, _largura=trilho, _slider='retratos')
        ctx = SimpleNamespace(scene=self.cena,
                              area=SimpleNamespace(tag_redraw=lambda: None))
        for posicao, esperado in ((inicio, g.LARGURA_RETRATO_MIN),
                                  (inicio + trilho, g.LARGURA_RETRATO_MAX)):
            addon.gaveta_eventos.OBJECT_OT_interagir_gaveta._atualizar(op, ctx, posicao)
            self.assertEqual(self.cena.cabinet_tam_retrato, esperado)

    def paineis(self, largura=478, altura=900):
        _cab, conteudo, _rod = addon.gaveta._partes_gaveta(
            addon.gaveta._widgets_gaveta(bpy.context, largura, altura))
        return addon.gaveta._paineis_gaveta(conteudo)

    def test_biblioteca_fica_fixa_na_metade_de_baixo_nas_tres_abas(self):
        tela = bpy.context.screen
        tela.pop(addon.gaveta._CHAVE_DIVISA, None)
        altura = 900
        meio = addon.gaveta._divisa_gaveta(bpy.context, altura)
        self.assertEqual(meio, round((addon.gaveta.ALTURA_RODAPE_GAVETA
                                      + altura - 48) / 2))
        for aba in ('MODULOS', 'PORTAS', 'PUXADORES'):
            self.cena.cabinet_aba = aba
            cima, divisa, baixo = self.paineis(altura=altura)
            self.assertEqual(divisa[5], ('divisa', True), aba)
            titulo = baixo[0]
            self.assertTrue(titulo[4].startswith("Library"), aba)
            # Always expanded: the title no longer toggles collapse.
            self.assertIsNone(titulo[5])
            self.assertTrue(any(v[5] and v[5][0] == 'suspenso' for v in baixo))
            self.assertLess(titulo[1] + titulo[3], meio)
            self.assertFalse([v for v in cima if v[4].startswith("Library")])
        self.cena.cabinet_aba = 'MODULOS'

    def test_divisoria_respeita_o_minimo_dos_dois_paineis(self):
        tela = bpy.context.screen
        altura = 900
        try:
            for fracao, esperado in (
                    (0.0, addon.gaveta.ALTURA_RODAPE_GAVETA
                     + addon.gaveta.ALTURA_MIN_PAINEL_GAVETA),
                    (1.0, altura - 48 - addon.gaveta.ALTURA_MIN_PAINEL_GAVETA)):
                tela[addon.gaveta._CHAVE_DIVISA] = fracao
                self.assertEqual(addon.gaveta._divisa_gaveta(bpy.context, altura),
                                 esperado)
            tela[addon.gaveta._CHAVE_DIVISA] = 0.25
            y = addon.gaveta._divisa_gaveta(bpy.context, altura)
            self.assertAlmostEqual(addon.gaveta._fracao_divisa(altura, y), 0.25, 2)
        finally:
            tela.pop(addon.gaveta._CHAVE_DIVISA, None)

    def test_cada_painel_rola_sozinho(self):
        tela = bpy.context.screen
        # Short enough that the cube dimensions do not fit within the panel.
        largura, altura = 320, 240
        tela.pop(addon.gaveta._CHAVE_DIVISA, None)
        limite, limite_bib = addon.gaveta._limites_rolagem_gaveta(
            bpy.context, largura, altura)
        self.assertGreater(limite, 0)
        self.assertGreater(limite_bib, 0)
        try:
            antes = self.paineis(largura, altura)
            tela[addon.gaveta._CHAVE_ROLAGEM_BIB] = 85
            depois = self.paineis(largura, altura)
            self.assertEqual([v[1] for v in antes[0]],
                             [v[1] for v in depois[0]])
            self.assertEqual(depois[2][0][1] - antes[2][0][1], min(85, limite_bib))
            tela[addon.gaveta._CHAVE_ROLAGEM_BIB] = 0
            tela[addon.gaveta._CHAVE_ROLAGEM] = 85
            depois = self.paineis(largura, altura)
            self.assertEqual([v[1] for v in antes[2]],
                             [v[1] for v in depois[2]])
            self.assertEqual(depois[0][0][1] - antes[0][0][1], min(85, limite))
        finally:
            tela[addon.gaveta._CHAVE_ROLAGEM] = 0
            tela[addon.gaveta._CHAVE_ROLAGEM_BIB] = 0

    def contexto_rolagem(self, altura=320):
        ctx = self.contexto_abas(320, altura)
        chave = addon.biblioteca_faixa.CHAVE_LAYOUT
        anterior = ctx.screen.get(chave)
        self.addCleanup(lambda: ctx.screen.pop(chave, None) if anterior is None
                        else ctx.screen.__setitem__(chave, anterior))
        ctx.screen[chave] = 0
        ctx.window_manager = SimpleNamespace(modal_handler_add=lambda *_: None)
        return ctx

    def test_barras_so_aparecem_com_excesso_e_respeitam_cada_painel(self):
        # Regression v373: clipped fields and photos had no visible scrollbar.
        g = addon.gaveta
        ctx = self.contexto_rolagem()
        for aba in g.ABAS_GAVETA:
            ctx.scene.cabinet_aba = aba[2]
            limites = g._limites_rolagem_gaveta(ctx, 320, 320)
            barras = [v for v in g._widgets_gaveta(ctx, 320, 320)
                      if v[5] and v[5][0] == 'rolagem']
            self.assertEqual(len(barras), sum(l > 0 for l in limites), aba)
            for v in barras:
                self.assertLessEqual(v[0] + v[2], 308)
                self.assertGreaterEqual(v[1], g.ALTURA_RODAPE_GAVETA)
                self.assertLessEqual(v[1] + v[3], 320 - 48)
                self.assertIn(v, g._widgets_interativos(ctx))
                conteudo = g._partes_gaveta(g._widgets_gaveta(ctx, 320, 320))[1]
                paineis = g._paineis_gaveta(conteudo)
                painel = paineis[0 if v[5][1] == g._CHAVE_ROLAGEM else 2]
                self.assertTrue(all(item[0] + item[2] <= v[0] - 4 for item in painel))
        self.assertEqual(g._barras_rolagem_gaveta(ctx, 320, 320, (0, 0), (0, 0)), [])

    def test_arraste_barra_limites_cancelamento_e_independencia(self):
        g = addon.gaveta
        ctx = self.contexto_rolagem(240)
        barras = [v for v in g._widgets_gaveta(ctx, 320, 240)
                  if v[5] and v[5][0] == 'rolagem']
        self.assertEqual(len(barras), 2)
        for v in barras:
            chave, limite = v[5][1:3]
            outra = g._CHAVE_ROLAGEM_BIB if chave == g._CHAVE_ROLAGEM else g._CHAVE_ROLAGEM
            base, h = g._alca_rolagem(v[1], v[3], limite, 0)
            op = SimpleNamespace()
            evento = SimpleNamespace(type='LEFTMOUSE', value='PRESS',
                mouse_region_x=v[0] + v[2] / 2, mouse_region_y=base + h / 2)
            classe = addon.gaveta_eventos.OBJECT_OT_interagir_gaveta
            self.assertEqual(classe.invoke(op, ctx, evento), {'RUNNING_MODAL'})
            for y, esperado in ((-10000, limite), (10000, 0)):
                classe._modal_rolagem(op, ctx, SimpleNamespace(type='MOUSEMOVE',
                    value='NOTHING', mouse_region_y=y))
                self.assertEqual(ctx.screen[chave], esperado)
                self.assertEqual(ctx.screen[outra], 0)
            classe._modal_rolagem(op, ctx, SimpleNamespace(type='MOUSEMOVE',
                value='NOTHING', mouse_region_y=-10000))
            self.assertEqual(classe._modal_rolagem(op, ctx,
                SimpleNamespace(type='ESC', value='PRESS')), {'CANCELLED'})
            self.assertEqual(ctx.screen[chave], 0)
            # Clicking the track near its bottom scrolls to the end; release preserves it.
            evento.mouse_region_y = v[1] + 1
            self.assertEqual(classe.invoke(op, ctx, evento), {'RUNNING_MODAL'})
            self.assertEqual(ctx.screen[chave], limite)
            self.assertEqual(classe._modal_rolagem(op, ctx,
                SimpleNamespace(type='LEFTMOUSE', value='RELEASE')), {'FINISHED'})
            self.assertEqual(ctx.screen[chave], limite)
            self.assertEqual(ctx.screen[outra], 0)
            ctx.screen[chave] = 0

    def test_roda_e_touchpad_rolam_so_painel_apontado_sem_mover_abas(self):
        g = addon.gaveta
        vinculos = {item.type: item.value for _, item in addon.editor._keymaps[0]}
        self.assertEqual(vinculos['TRACKPADPAN'], 'ANY')
        self.assertEqual(vinculos['WHEELDOWNMOUSE'], 'PRESS')
        ctx = self.contexto_rolagem(240)
        antes = g._widgets_gaveta(ctx, 320, 240)
        cab = g._partes_gaveta(antes)[0]
        for y, chave in ((150, g._CHAVE_ROLAGEM), (60, g._CHAVE_ROLAGEM_BIB)):
            for tipo, delta in (('WHEELDOWNMOUSE', 85), ('TRACKPADPAN', 27)):
                ctx.screen[chave] = 0
                evento = SimpleNamespace(type=tipo, value='NOTHING' if tipo == 'TRACKPADPAN' else 'PRESS', mouse_region_x=5,
                    mouse_region_y=y, mouse_y=100 + delta, mouse_prev_y=100)
                addon.gaveta_eventos.OBJECT_OT_interagir_gaveta.invoke(SimpleNamespace(), ctx, evento)
                limites = g._limites_rolagem_gaveta(ctx, 320, 240)
                limite = limites[0 if chave == g._CHAVE_ROLAGEM else 1]
                self.assertEqual(ctx.screen[chave], min(delta, limite))
                self.assertEqual(g._partes_gaveta(g._widgets_gaveta(ctx, 320, 240))[0], cab)
        valores = (ctx.screen[g._CHAVE_ROLAGEM], ctx.screen[g._CHAVE_ROLAGEM_BIB])
        for y in (10, 230):
            addon.gaveta_eventos.OBJECT_OT_interagir_gaveta.invoke(SimpleNamespace(), ctx,
                SimpleNamespace(type='WHEELDOWNMOUSE', mouse_region_x=5, mouse_region_y=y))
        self.assertEqual(valores, (ctx.screen[g._CHAVE_ROLAGEM], ctx.screen[g._CHAVE_ROLAGEM_BIB]))

    def test_barra_nao_vira_painel_de_opcoes_e_some_com_opcoes_abertas(self):
        g = addon.gaveta
        ctx = self.contexto_rolagem(240)
        rodape = g._partes_gaveta(g._widgets_gaveta(ctx, 320, 240))[2]
        self.assertIsNone(g._retangulo_painel_opcoes(rodape))
        ctx.screen[g._CHAVE_OPCOES] = 1
        self.assertFalse(any(v[5] and v[5][0] == 'rolagem'
                             for v in g._widgets_gaveta(ctx, 320, 240)))

    def test_alca_proporcional_no_topo_fundo_e_apos_redimensionar(self):
        g = addon.gaveta
        y, h = g._alca_rolagem(50, 100, 100, 0)
        self.assertEqual((y, h), (100, 50))
        self.assertEqual(g._alca_rolagem(50, 100, 100, 100), (50, 50))
        self.assertEqual(g._alca_rolagem(50, 100, 100, 9999), (50, 50))
        self.assertEqual(g._alca_rolagem(50, 10, 10000, 200), (50, 10))
        ctx = self.contexto_rolagem(240)
        ctx.screen[g._CHAVE_ROLAGEM] = 99999
        ctx.screen[g._CHAVE_ROLAGEM_BIB] = 99999
        barras = [v for v in g._widgets_gaveta(ctx, 320, 400)
                  if v[5] and v[5][0] == 'rolagem']
        for v in barras:
            self.assertEqual(v[5][3], v[5][2])
        # A photo fitting after column shrinkage must not toggle the scrollbar.
        from unittest.mock import patch
        def conteudo(context, largura, altura, *_):
            meio = g._divisa_gaveta(context, altura)
            piso = g.ALTURA_RODAPE_GAVETA + 18
            return [(12, meio - 5, largura - 24, 10, '', ('divisa', True)),
                    (12, piso - 1 if largura == 320 else piso + 1,
                     largura - 24, 100, 'Foto da fixture', None)]
        with patch.object(g, '_widgets_conteudo_gaveta', side_effect=conteudo):
            self.assertEqual(g._limites_rolagem_gaveta(ctx, 320, 400), (0, 1))

    def test_widget_cortado_recebe_clique_so_na_parte_visivel(self):
        largura, altura = 320, 500
        bpy.context.screen.pop(addon.gaveta._CHAVE_DIVISA, None)
        ctx = _Contexto(largura, altura)
        meio = addon.gaveta._divisa_gaveta(bpy.context, altura)
        cima, divisa, baixo = self.paineis(largura, altura)
        interativos = addon.gaveta._widgets_interativos(ctx)
        self.assertIn(divisa, interativos)
        folga = addon.gaveta.FOLGA_DIVISA_GAVETA
        for v in interativos:
            if addon.visibilidade.eh_acao(v[5]):
                self.assertGreaterEqual(v[1],meio+folga)
                continue
            if ((v[5] and v[5][0] == 'divisa') or v[1] >= altura - 48
                    or v[1] + v[3] <= addon.gaveta.ALTURA_RODAPE_GAVETA):
                continue        # Divider, header and fixed footer.
            # No clickable target crosses the divider or enters the fixed footer.
            self.assertFalse(v[1] - folga < meio < v[1] + v[3] + folga, v)
            if v[1] < meio:
                self.assertGreaterEqual(v[1], addon.gaveta.ALTURA_RODAPE_GAVETA, v)
            if addon.gaveta_eventos._icone_acao_gaveta(v[5]) and not addon.gaveta._no_cabecalho(v[5]):
                # Gizmo icons cannot be clipped; show only complete ones.
                self.assertTrue(any(v == c for c in cima + baixo), v)

    def test_foto_cortada_pelo_rodape_aceita_clique(self):
        # User screenshot's 633 px sidebar: the panel photo was half under the footer,
        # preventing clicks and double clicks from reaching it.
        largura, altura = 478, 633
        bpy.context.screen.pop(addon.gaveta._CHAVE_DIVISA, None)
        self.cena.chapa_n1 = "Panels"
        self.cena.chapa_n2 = addon.biblioteca._filhos_n2("Panels")[0]
        self.cena.chapa_n3 = ''
        try:
            foto = [v for v in addon.gaveta._widgets_gaveta(bpy.context, largura,
                                                     altura)
                    if v[5] and v[5][0] == 'preset'][0]
            self.assertLess(foto[1], addon.gaveta.ALTURA_RODAPE_GAVETA)
            clicavel = [v for v in addon.gaveta._widgets_interativos(
                _Contexto(largura, altura))
                if v[5] and v[5][0] == 'preset']
            self.assertEqual(len(clicavel), 1)
            x, y, w, h = clicavel[0][:4]
            self.assertEqual(y, addon.gaveta.ALTURA_RODAPE_GAVETA)
            self.assertEqual(y + h, foto[1] + foto[3])
        finally:
            self.cena.chapa_n1 = "Cabinets"
            self.cena.chapa_n2 = "Living Room"
            self.cena.chapa_n3 = "Base Cabinets"

    def test_arrastar_a_divisoria_e_esc_desfaz(self):
        tela = bpy.context.screen
        tela[addon.gaveta._CHAVE_DIVISA] = 0.5
        janela = SimpleNamespace(cursor_modal_restore=lambda: None)
        ctx = SimpleNamespace(
            screen=tela, window=janela,
            region=SimpleNamespace(height=900),
            area=SimpleNamespace(tag_redraw=lambda: None))
        op = SimpleNamespace(_divisa=0.5)
        modal = addon.gaveta_eventos.OBJECT_OT_interagir_gaveta._modal_divisa
        try:
            evento = SimpleNamespace(type='MOUSEMOVE', value='NOTHING',
                                     mouse_region_y=300)
            self.assertEqual(modal(op, ctx, evento), {'RUNNING_MODAL'})
            self.assertAlmostEqual(tela[addon.gaveta._CHAVE_DIVISA],
                                   addon.gaveta._fracao_divisa(900, 300))
            esc = SimpleNamespace(type='ESC', value='PRESS',
                                  mouse_region_y=300)
            self.assertEqual(modal(op, ctx, esc), {'CANCELLED'})
            self.assertEqual(tela[addon.gaveta._CHAVE_DIVISA], 0.5)
        finally:
            tela.pop(addon.gaveta._CHAVE_DIVISA, None)

    def test_medidas_estreitas_e_limite_da_rolagem(self):
        largura, altura = 190, 300
        inicio = addon.gaveta._widgets_gaveta(bpy.context, largura, altura,
                                       _rolagem=0)
        medidas = [v for v in inicio if v[5] and v[5][0] == 'medida']
        self.assertEqual(len({v[0] for v in medidas}), 1)
        self.assertTrue(all(v[0] + v[2] <= largura - 12 for v in medidas))
        limite = addon.gaveta._limite_rolagem_gaveta(bpy.context, largura, altura)
        self.assertGreater(limite, 0)
        bpy.context.screen['cabinet_gaveta_rolagem'] = 9999
        fim = addon.gaveta._widgets_gaveta(bpy.context, largura, altura)
        # The first widget after the header's tabs and chains scrolls.
        n = len(addon.gaveta._partes_gaveta(inicio)[0])
        self.assertEqual(fim[n][1] - inicio[n][1], limite)
        bpy.context.screen['cabinet_gaveta_rolagem'] = 0


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestGaveta)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError("Sidebar tests failed")
