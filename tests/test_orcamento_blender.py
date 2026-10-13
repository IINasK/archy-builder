"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_orcamento_blender.py

Orcamento para o ERP do usuario: o documento segue AO PE' DA LETRA o
padrao do prompt de ditado dele (bloco ```markdown + Pendencias), so'
com a marcenaria preenchida.
"""
import os
import shutil
import sys
import tempfile
import unittest

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

INFERIOR = 'Arm\u00e1rio inferior'


class TestOrcamento(unittest.TestCase):
    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for col in [c for c in bpy.data.collections
                    if c.get(addon.modulos.MARCA_COLECAO_MODULO)]:
            bpy.data.collections.remove(col)

    def nicho(self, nome='', extras=(), x=0.0):
        """Nicho 600x400x300 (+ chapas extras) agrupado com `nome`."""
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.object.cabinet_criar_nicho()
        pecas = list(bpy.context.selected_objects)
        for args in extras:
            pecas.append(addon.chapas.nova_chapa(*args, bpy.context))
        for o in pecas:
            o.location.x += x
            o.select_set(True)
        bpy.context.view_layer.update()
        bpy.ops.object.cabinet_agrupar(nome=nome)
        conj = bpy.context.object
        self.assertIn(addon.chapas.MARCA_CONJUNTO, conj)
        bpy.context.view_layer.update()
        return conj

    def porta(self, conj, **kwargs):
        L, A = conj.conj_largura_mm, conj.conj_altura_mm
        P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
        a = conj.matrix_world @ (Vector((-L / 2 + E, -P / 2, E)) / 1000.0)
        b = conj.matrix_world @ (Vector((L / 2 - E, -P / 2, A - E)) / 1000.0)
        opcoes = dict(frente='NEG_Y', dobradica='RETA', folhas=2)
        opcoes.update(kwargs)
        resultado = bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            referencia=tuple(v for linha in
                             conj.matrix_world.to_quaternion().to_matrix()
                             for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name, **opcoes)
        self.assertEqual(resultado, {'FINISHED'})
        return addon.portas._portas_do_conjunto(conj)[-1]

    def comodo(self, conj, nome):
        self.assertEqual(addon.orcamento.definir_comodo(bpy.context.scene, [conj], nome), 1)

    def bloco(self, texto):
        self.assertTrue(texto.startswith('```markdown\n'), texto)
        return texto.split('```markdown\n', 1)[1].split('\n```', 1)[0]

    def test_documento_completo_no_padrao_do_erp(self):
        # Prateleira no vao da esquerda, divisoria no meio, 2 folhas com
        # perfil: tudo sai do 3D, um detalhe por linha no 3o andar.
        conj = self.nicho(INFERIOR, extras=(
            ('Prateleira', 273.0, 280.0, 18.0, (-145.5, 0.0, 200.0),
             (0.0, 0.0, 0.0)),
            ('Divisoria', 364.0, 300.0, 18.0, (0.0, 0.0, 200.0),
             (0.0, 90.0, 0.0))))
        grupo = self.porta(conj)
        for folha in addon.portas._folhas_portas(grupo):
            addon.puxadores.criar_puxador(bpy.context, folha, 'PERFIL', 'Y-', 1)
        self.comodo(conj, 'Cozinha')
        texto, exportados, pendencias = addon.orcamento.orcamento_da_cena(bpy.context.scene)
        self.assertEqual((exportados, pendencias), (1, []))
        self.assertEqual(texto, '\n'.join((
            '```markdown',
            '# Or\u00e7amento',
            'cliente:',
            'endereco:',
            'perfil: investidor',
            '',
            '## M\u00f3veis',
            '',
            '### Cozinha',
            '- ' + INFERIOR,
            '  - 2 portas',
            '  - 1 prateleira interna',
            '  - 1 divis\u00f3ria interna',
            '  - 2 puxadores perfil',
            '',
            '## Outros',
            '',
            '### Geral',
            '- Limpeza geral.',
            '',
            '## Valores',
            '- moveis:',
            '- obras:',
            '- eletros:',
            '- outros:',
            '',
            '## Pagamento',
            '- modalidade: entrada+parcelas',
            '- entrada:',
            '- parcelas:',
            '```',
            '',
            'Sem pend\u00eancias.',
            '')))

    def test_modelos_de_porta_e_nicho_sem_nada(self):
        # Correr, basculante e embutida pelo nome do modelo; nicho sem
        # porta so' diz que nao tem prateleira (nada inventado).
        casos = (
            (dict(abertura='CORRER', folhas=2, dobradica='RETA'),
             '2 portas de correr'),
            (dict(abertura='BASCULANTE', folhas=1), '1 porta basculante'),
            (dict(dobradica='SUPER_CURVA', folhas=1), '1 porta embutida'),
        )
        for i, (opcoes, esperado) in enumerate(casos):
            with self.subTest(esperado=esperado):
                self.setUp()
                conj = self.nicho('Superior %d' % i)
                self.porta(conj, **opcoes)
                self.comodo(conj, 'Sala')
                bloco = self.bloco(addon.orcamento.orcamento_da_cena(bpy.context.scene)[0])
                self.assertIn('### Sala\n- Superior %d\n  - %s\n'
                              '  - Sem prateleiras internas\n' % (i, esperado),
                              bloco)
        self.setUp()
        conj = self.nicho('Nicho')
        self.comodo(conj, '\u00c1rea de servi\u00e7o')
        bloco = self.bloco(addon.orcamento.orcamento_da_cena(bpy.context.scene)[0])
        self.assertIn('### \u00c1rea de servi\u00e7o\n- Nicho\n'
                      '  - Sem prateleiras internas\n\n', bloco)

    def test_comodos_na_ordem_e_modulo_girado(self):
        # Cozinha antes da Sala (ordem fixa), e o modulo girado 90 graus
        # ainda acha a prateleira pelo referencial DELE.
        sala = self.nicho('Rack', x=2.0)
        self.comodo(sala, 'Sala')
        cozinha = self.nicho('Torre', extras=(
            ('Prateleira', 564.0, 300.0, 18.0, (0.0, 0.0, 200.0),
             (0.0, 0.0, 0.0)),))
        self.comodo(cozinha, 'Cozinha')
        cozinha.rotation_euler.z = 1.5707963
        bpy.context.view_layer.update()
        self.assertEqual(addon.orcamento._pecas_internas(cozinha), (1, 0))
        bloco = self.bloco(addon.orcamento.orcamento_da_cena(bpy.context.scene)[0])
        self.assertLess(bloco.index('### Cozinha'), bloco.index('### Sala'))
        self.assertIn('- Torre\n  - 1 prateleira interna\n', bloco)

    def test_pendencias_do_que_ficou_pela_metade(self):
        # Sem comodo o modulo fica fora (todo item mora num comodo); nome
        # automatico e chapa solta viram pendencia; sem marcenaria, o
        # bloco Moveis some (bloco vazio nao tem cabecalho).
        conj = self.nicho()
        self.assertTrue(addon.orcamento.NOME_AUTOMATICO_MODULO.match(conj.name))
        bpy.ops.object.select_all(action='DESELECT')
        addon.chapas.nova_chapa('Solta', 600.0, 400.0, 18.0, (3000.0, 0.0, 0.0),
                         (0.0, 0.0, 0.0), bpy.context)
        texto, exportados, pendencias = addon.orcamento.orcamento_da_cena(bpy.context.scene)
        self.assertEqual(exportados, 0)
        self.assertNotIn('## M\u00f3veis', texto)
        self.assertIn('## Outros\n\n### Geral\n- Limpeza geral.\n', texto)
        self.assertEqual(len(pendencias), 3)
        self.assertIn('- %s: n\u00e3o foi dito o c\u00f4modo; o m\u00f3dulo '
                      'ficou fora do or\u00e7amento.' % conj.name, pendencias)
        self.assertIn('- 1 chapa solta, fora de um arm\u00e1rio: n\u00e3o foi '
                      'dito a qual m\u00f3dulo pertence; ficou fora do '
                      'or\u00e7amento.', pendencias)
        self.assertTrue(texto.endswith(
            '\n```\n\nPend\u00eancias\n' + '\n'.join(pendencias)
            + '\n\nQuer atualizar algum destes antes de eu refazer o '
            'or\u00e7amento?\n'))
        # com o comodo, o nome automatico continua cobrado, pelo comodo
        self.comodo(conj, 'Quarto')
        pendencias = addon.orcamento.orcamento_da_cena(bpy.context.scene)[2]
        self.assertIn('- Quarto, %s: n\u00e3o foi dito que m\u00f3dulo \u00e9 '
                      '(o nome do grupo ainda \u00e9 o autom\u00e1tico).'
                      % conj.name, pendencias)

    def test_comodo_na_aba_modulos_e_uma_linha_que_expande(self):
        # Pedido do usuario: a grade fixa ocupava a aba. Fechada, UMA
        # linha; aberta, os comodos, os ja' digitados, "Sem comodo" (se ha'
        # um) e "Outro nome...". Vale para todos os modulos selecionados.
        a = self.nicho('A')
        b = self.nicho('B', x=2.0)
        tela = bpy.context.screen
        bpy.context.scene.cabinet_aba = 'MODULOS'
        self.addCleanup(tela.__setitem__, addon.gaveta._CHAVE_SUSPENSO, '')

        def widgets():
            return [v for v in addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)
                    if v[5]]

        def lista():
            return [v[5] for v in widgets() if v[5][0] == 'escolha'
                    and v[5][5] == addon.orcamento.ALVO_COMODO]

        def campo():
            return [v for v in widgets() if v[5][:2] == (
                'suspenso', addon.orcamento.SUSPENSO_COMODO)]
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = None
        self.assertEqual(campo(), [])               # sem modulo, sem comodo
        # chapa de A + folha da porta de B: os dois modulos
        chapa = addon.modulos._chapas_do_conjunto(a)[0]
        folha = addon.portas._folhas_portas(self.porta(b))[0]
        bpy.ops.object.select_all(action='DESELECT')
        chapa.select_set(True)
        folha.select_set(True)
        bpy.context.view_layer.objects.active = chapa
        (fechado,) = campo()
        self.assertEqual(fechado[4], 'Comodo: (nenhum)')
        self.assertEqual(lista(), [])               # fechada: uma linha so'
        tela[addon.gaveta._CHAVE_SUSPENSO] = addon.orcamento.SUSPENSO_COMODO
        self.assertEqual([e[2] for e in lista()],
                         [*addon.orcamento.COMODOS, addon.orcamento.COMODO_OUTRO])
        self.assertEqual(bpy.ops.object.cabinet_definir_comodo(nome='Sacada'),
                         {'FINISHED'})
        for conj in (a, b):
            self.assertEqual(addon.orcamento._nome_comodo(addon.orcamento._comodo_do_modulo(conj)),
                             'Sacada')
        self.assertEqual(campo()[0][4], 'Comodo: Sacada')
        self.assertEqual([e[2] for e in lista() if e[3]], ['Sacada'])
        self.assertIn(addon.orcamento.COMODO_NENHUM, [e[2] for e in lista()])
        # "Outro nome...": o campo da caixa preta, logo abaixo da linha
        addon.orcamento._abrir_caixa_comodo(bpy.context)
        self.addCleanup(addon.perguntas._pergunta_atual.__setitem__, 0, None)
        self.addCleanup(addon.solda._nome_grupo_gaveta.__setitem__, 0, None)
        caixa = [v for v in widgets() if v[5][0] == 'pergunta']
        self.assertEqual(len(caixa), 1)
        self.assertTrue(caixa[0][4].startswith('Nome do comodo: '))
        self.assertLess(caixa[0][1], campo()[0][1])
        addon.solda._nome_grupo_gaveta[0]['texto'] = 'Varanda'
        self.assertEqual(bpy.ops.object.cabinet_definir_comodo(digitado=True),
                         {'FINISHED'})
        self.assertIsNone(addon.perguntas._pergunta_atual[0])
        # Varanda e' Sacada (regra do prompt): a mesma pasta
        self.assertEqual([c.name for c in bpy.data.collections
                          if c.get(addon.orcamento.MARCA_COLECAO_COMODO)], ['Sacada'])
        addon.orcamento._abrir_caixa_comodo(bpy.context)
        addon.solda._nome_grupo_gaveta[0]['texto'] = 'Quarto do Joao'
        self.assertTrue(addon.orcamento._confirmar_campo_gaveta(
            addon.solda._nome_grupo_gaveta[0]))
        self.assertEqual([e[2] for e in lista()][-3:],
                         ['Quarto do Joao', addon.orcamento.COMODO_NENHUM,
                          addon.orcamento.COMODO_OUTRO])
        # Sem comodo: a Collection volta a' raiz e as pastas vazias somem
        bpy.ops.object.cabinet_definir_comodo(nome=addon.orcamento.COMODO_NENHUM)
        cena = bpy.context.scene
        for conj in (a, b):
            self.assertIn(addon.modulos._colecao_do_modulo(conj).name,
                          cena.collection.children)
        self.assertFalse([c for c in bpy.data.collections
                          if c.get(addon.orcamento.MARCA_COLECAO_COMODO)])

    def test_comodo_e_pasta_no_outliner(self):
        # Outliner: Cozinha > Armario > chapas e porta. A pasta e' a fonte:
        # arrastar o armario para outra pasta muda o orcamento.
        conj = self.nicho(INFERIOR)
        self.porta(conj)
        self.comodo(conj, 'Cozinha')
        cena = bpy.context.scene
        pasta = cena.collection.children['Cozinha']
        self.assertTrue(pasta.get(addon.orcamento.MARCA_COLECAO_COMODO))
        colecao = addon.modulos._colecao_do_modulo(conj)
        self.assertEqual(list(pasta.children), [colecao])
        self.assertNotIn(colecao.name, cena.collection.children)
        self.assertEqual(set(pasta.all_objects), set(colecao.all_objects))
        self.assertIn(addon.portas._portas_do_conjunto(conj)[0].name,
                      colecao.all_objects)
        # o usuario arrasta para uma pasta "Sala" do Outliner
        sala = bpy.data.collections.new('Sala')
        sala[addon.orcamento.MARCA_COLECAO_COMODO] = 1
        cena.collection.children.link(sala)
        sala.children.link(colecao)
        pasta.children.unlink(colecao)
        bloco = self.bloco(addon.orcamento.orcamento_da_cena(cena)[0])
        self.assertIn('### Sala\n- ' + INFERIOR, bloco)
        self.assertNotIn('### Cozinha', bloco)

    def test_armario_antigo_sem_collection_ganha_a_dele(self):
        # Antes do v168 o modulo nao tinha Collection: so' ela entra na
        # pasta, entao ela nasce aqui (com o mesmo nome do Empty).
        conj = self.nicho('Antigo')
        colecao = addon.modulos._colecao_do_modulo(conj)
        for o in [conj, *conj.children_recursive]:
            bpy.context.scene.collection.objects.link(o)
            colecao.objects.unlink(o)
        bpy.data.collections.remove(colecao)
        self.assertIsNone(addon.modulos._colecao_do_modulo(conj))
        self.comodo(conj, 'Copa')
        colecao = addon.modulos._colecao_do_modulo(conj)
        self.assertEqual(colecao.name, conj.name)
        self.assertIn(colecao.name,
                      bpy.context.scene.collection.children['Copa'].children)

    def arquivo(self, nome='Orcamento.txt'):
        pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, pasta, True)
        return os.path.join(pasta, nome)

    def test_gerar_mostra_o_resultado_nas_opcoes(self):
        # "Copiar e nada acontece": o relatorio so' ia para a barra de
        # status. O botao (no fim das Opcoes) acende e diz o que fez; as
        # pendencias ficam a' vista numa caixa preta logo abaixo.
        self.nicho()
        tela = bpy.context.screen
        bpy.ops.object.cabinet_opcoes_gaveta()
        self.addCleanup(addon.gaveta._fechar_opcoes, tela)
        self.addCleanup(addon.orcamento._orcamento_gerado.__setitem__, 0, None)
        self.assertEqual(bpy.ops.object.cabinet_exportar_orcamento(
            filepath=self.arquivo()), {'FINISHED'})
        _cab, _conteudo, rodape = addon.gaveta._partes_gaveta(
            addon.gaveta._widgets_gaveta(bpy.context, 320, 1400))
        rodape = [v for v in rodape if v[5]]
        (botao,) = [v for v in rodape
                    if v[5][:2] == ('operador', addon.orcamento.OP_EXPORTAR_ORCAMENTO)]
        self.assertTrue(botao[5][2])
        self.assertTrue(botao[4].startswith('Salvo: 0 modulo(s)'))
        caixa = [v for v in rodape if v[5][0] == 'pergunta']
        self.assertEqual(len(caixa), 1)
        self.assertTrue(caixa[0][4].startswith('Pendencias:\n'))
        self.assertLess(caixa[0][1], botao[1])
        # tudo dentro do painel, que sobe a partir da engrenagem
        painel = addon.gaveta._retangulo_painel_opcoes(rodape)
        self.assertGreaterEqual(caixa[0][1], painel[1])
        self.assertTrue(bpy.app.timers.is_registered(
            addon.orcamento._apagar_orcamento_gerado))
        addon.orcamento._apagar_orcamento_gerado()
        self.assertIsNone(addon.orcamento._orcamento_gerado[0])

    def test_operador_salva_o_txt(self):
        # Pedido do usuario: "Salvar como" e um .txt que o Bloco de Notas
        # abre, com o mesmo texto do padrao da empresa (acentos em UTF-8)
        conj = self.nicho('Gabinete')
        self.comodo(conj, 'Banheiro')
        self.addCleanup(addon.orcamento._orcamento_gerado.__setitem__, 0, None)
        caminho = self.arquivo('Obra da Ana')       # sem extensao: ganha .txt
        self.assertEqual(bpy.ops.object.cabinet_exportar_orcamento(
            filepath=caminho), {'FINISHED'})
        with open(caminho + '.txt', encoding='utf-8') as f:
            salvo = f.read()
        self.assertEqual(salvo, addon.orcamento.orcamento_da_cena(
            bpy.context.scene)[0])
        self.assertIn('### Banheiro\n- Gabinete\n', salvo)
        self.assertEqual(addon.orcamento._orcamento_gerado[0]['arquivo'],
                         'Obra da Ana.txt')
        # pasta que nao existe: avisa e nao finge que salvou
        addon.orcamento._orcamento_gerado[0] = None
        with self.assertRaises(RuntimeError):
            bpy.ops.object.cabinet_exportar_orcamento(
                filepath=os.path.join(caminho, 'nao', 'existe.txt'))
        self.assertIsNone(addon.orcamento._orcamento_gerado[0])

    def test_nome_sugerido_fica_ao_lado_do_blend(self):
        sugerido = addon.orcamento._arquivo_sugerido()
        self.assertTrue(sugerido.endswith('.txt'))
        if not bpy.data.filepath:
            self.assertEqual(os.path.dirname(sugerido),
                             os.path.expanduser('~'))


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestOrcamento)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de orcamento')
