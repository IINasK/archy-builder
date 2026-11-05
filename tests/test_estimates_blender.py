"""Run: blender --background --factory-startup --python-exit-code 1 --python tests/test_estimates_blender.py

Estimate for the user's ERP: follow the dictated-prompt format exactly (markdown fenced block plus pending items), filling only the cabinetry content."""
import os
import shutil
import sys
import tempfile
import unittest

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon

INFERIOR = 'Base Cabinet'


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
        """Create a grouped 600x400x300 niche with extra panels and nome as its name."""
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
        addon.materiais.aplicar(addon.materiais.pecas_dos_alvos([conj]), self.material())
        return conj

    def material(self):
        mat = bpy.data.materials.get('MDF White TX') or bpy.data.materials.new('MDF White TX')
        mat[addon.materiais.CHAVE_MATERIAL] = "MDF/Solid Colors//White TX"
        return mat

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
        grupo = addon.portas._portas_do_conjunto(conj)[-1]
        addon.materiais.aplicar(addon.materiais.pecas_dos_alvos([grupo]), self.material())
        return grupo

    def comodo(self, conj, nome):
        self.assertEqual(addon.orcamento.definir_comodo(bpy.context.scene, [conj], nome), 1)

    def bloco(self, texto):
        self.assertTrue(texto.startswith('```markdown\n'), texto)
        return texto.split('```markdown\n', 1)[1].split('\n```', 1)[0]

    def test_documento_completo_no_padrao_do_erp(self):
        # Shelf in the left opening, center partition, two leaves with profile handles:
        # derive everything from 3D, one detail per line at the third level.
        conj = self.nicho(INFERIOR, extras=(
            ('Shelf', 273.0, 280.0, 18.0, (-145.5, 0.0, 200.0),
             (0.0, 0.0, 0.0)),
            ("Partition", 364.0, 300.0, 18.0, (0.0, 0.0, 200.0),
             (0.0, 90.0, 0.0))))
        grupo = self.porta(conj)
        for folha in addon.portas._folhas_portas(grupo):
            addon.puxadores.criar_puxador(bpy.context, folha, 'PERFIL', 'Y-', 1)
        self.comodo(conj, "Kitchen")
        texto, exportados, pendencias = addon.orcamento.orcamento_da_cena(bpy.context.scene)
        self.assertEqual((exportados, pendencias), (1, []))
        self.assertEqual(texto, '\n'.join((
            '```markdown',
            "# Estimate",
            "client:",
            "address:",
            "profile: investor",
            '',
            "## Furniture",
            '',
            '### Kitchen',
            '- ' + INFERIOR,
            '  - Overall dimensions (width x height x depth): 600 x 400 x 300 mm',
            '  - 2 hinged doors',
            '  - Hinges: full overlay',
            '  - No internal drawers',
            '  - 1 internal shelf',
            '  - 1 internal partition',
            '  - 2 profile handles',
            '  - Materials: MDF White TX',
            '',
            "## Other",
            '',
            "### General",
            "- General cleaning.",
            '',
            "## Costs",
            "- furniture:",
            "- construction:",
            "- appliances:",
            "- other:",
            '',
            "## Payment",
            "- method: down payment+installments",
            "- down payment:",
            "- installments:",
            '```',
            '',
            'No pending items.',
            '')))

    def test_modelos_de_porta_e_nicho_sem_nada(self):
        # Infer sliding, lift-up and inset from the model name; a doorless niche
        # only states that it has no shelf, without inventing details.
        casos = (
            (dict(abertura='CORRER', folhas=2, dobradica='RETA'),
             '2 sliding doors'),
            (dict(abertura='BASCULANTE', folhas=1), '1 lift-up door'),
            (dict(dobradica='SUPER_CURVA', folhas=1), '1 inset door'),
        )
        for i, (opcoes, esperado) in enumerate(casos):
            with self.subTest(esperado=esperado):
                self.setUp()
                conj = self.nicho('Wall Cabinet %d' % i)
                self.porta(conj, **opcoes)
                self.comodo(conj, "Living Room")
                bloco = self.bloco(addon.orcamento.orcamento_da_cena(bpy.context.scene)[0])
                self.assertIn('### Living Room\n- Wall Cabinet %d\n' % i, bloco)
                self.assertIn('  - %s\n' % esperado, bloco)
                self.assertIn('  - No internal shelves\n', bloco)
        self.setUp()
        conj = self.nicho('Niche')
        self.comodo(conj, "Utility Area")
        bloco = self.bloco(addon.orcamento.orcamento_da_cena(bpy.context.scene)[0])
        self.assertIn('### Utility Area\n- Niche\n', bloco)
        self.assertIn('  - No doors\n  - No hinges\n', bloco)
        self.assertIn('  - No internal shelves\n', bloco)

    # Regression, fixed in v302: the door's cabinet came from a saved name,
    # which does not gain .001 when the same preset is inserted twice.
    def test_porta_pertence_ao_modulo_pai_mesmo_com_nome_antigo(self):
        a = self.nicho("Cabinet")
        b = self.nicho('Cabinet Copy', x=1.0)
        self.porta(a)
        grupo = self.porta(b)
        grupo[addon.portas.CHAVE_MODULO_PORTA] = a.name
        folha = addon.portas._folhas_portas(grupo)[0]
        self.assertIs(addon.orcamento._modulo_do_objeto(folha), b)
        self.assertIs(addon.orcamento._modulo_do_objeto(grupo), b)

    def test_comodos_na_ordem_e_modulo_girado(self):
        # Kitchen before living room in fixed order; a cabinet rotated 90 degrees
        # still finds its shelf in its own reference frame.
        sala = self.nicho('Rack', x=2.0)
        self.comodo(sala, "Living Room")
        cozinha = self.nicho("Tall Cabinet", extras=(
            ('Shelf', 564.0, 300.0, 18.0, (0.0, 0.0, 200.0),
             (0.0, 0.0, 0.0)),))
        self.comodo(cozinha, "Kitchen")
        cozinha.rotation_euler.z = 1.5707963
        bpy.context.view_layer.update()
        self.assertEqual(addon.orcamento._pecas_internas(cozinha), (1, 0))
        bloco = self.bloco(addon.orcamento.orcamento_da_cena(bpy.context.scene)[0])
        self.assertLess(bloco.index('### Kitchen'), bloco.index('### Living Room'))
        self.assertIn('- Tall Cabinet\n', bloco)
        self.assertIn('  - 1 internal shelf\n', bloco)

    def test_cadastro_mede_geometria_girada_sem_mudar_cena(self):
        conj = self.nicho("Vanity Cabinet")
        porta = self.porta(conj)
        folha = addon.portas._folhas_portas(porta)[0]
        addon.ferragens._definir_abertura(bpy.context, folha, 0.7)
        conj.rotation_euler = (0.0, 0.0, 0.646)
        conj.location = (2.0, -3.0, 1.0)
        bpy.context.view_layer.update()
        antes = {o.name: (tuple(v for linha in o.matrix_world for v in linha),
                          tuple(tuple(v.co) for v in o.data.vertices) if o.type == 'MESH' else ())
                 for o in bpy.context.scene.objects}
        ficha = addon.orcamento.cadastro_do_modulo(conj)
        for obtido, esperado in zip(ficha['medidas_mm'], (600, 400, 300)):
            self.assertAlmostEqual(obtido, esperado, places=2)
        depois = {o.name: (tuple(v for linha in o.matrix_world for v in linha),
                           tuple(tuple(v.co) for v in o.data.vertices) if o.type == 'MESH' else ())
                  for o in bpy.context.scene.objects}
        self.assertEqual(antes, depois)

    def test_cadastro_mede_edicao_real_sem_confiar_no_campo_antigo(self):
        conj = self.nicho('Edited')
        direita = max(addon.modulos._chapas_do_conjunto(conj),
                      key=lambda o: o.matrix_world.translation.x)
        direita.location.x += .1234
        bpy.context.view_layer.update()
        antigo = conj.conj_largura_mm
        ficha = addon.orcamento.cadastro_do_modulo(conj)
        self.assertAlmostEqual(ficha['medidas_mm'][0], 723.4, places=2)
        self.assertAlmostEqual(conj.conj_largura_mm, antigo)

    def test_contagens_atuais_ignoram_parametros_e_pecas_excluidas(self):
        conj = addon.modulos.criar_armario(bpy.context, "Drawer Unit", 800, 700, 560, 18)
        grupo = addon.gavetas.criar_gavetas(bpy.context, conj, (18,18,18,18,0),
                                           dict(quantidade=3, profundidade_mm=400))
        portas = self.porta(conj)
        self.assertEqual(addon.orcamento.cadastro_do_modulo(conj)['gavetas'], 3)
        unidade = addon.gavetas.gavetas_do_grupo(grupo)[-1]
        for o in reversed(list(unidade.children_recursive)):
            bpy.data.objects.remove(o, do_unlink=True)
        folha = addon.portas._folhas_portas(portas)[-1]
        for o in reversed(list(folha.children_recursive)):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.objects.remove(folha, do_unlink=True)
        ficha = addon.orcamento.cadastro_do_modulo(conj)
        self.assertEqual(ficha['gavetas'], 2)
        self.assertEqual(ficha['portas'], {'GIRO': 1})
        self.assertEqual(grupo[addon.gavetas.CHAVE_PARAMETROS]['quantidade'], 3)
        detalhes = addon.orcamento._detalhes_do_modulo(conj, {}, ficha)
        self.assertIn('2 internal drawers', detalhes)

    def test_tipos_de_dobradica_e_correr_sem_dobradica(self):
        for tipo in ('RETA', 'CURVA', 'SUPER_CURVA'):
            with self.subTest(tipo=tipo):
                self.setUp()
                conj = self.nicho("Doors")
                self.porta(conj, dobradica=tipo)
                self.assertEqual(addon.orcamento.cadastro_do_modulo(conj)['dobradicas'], [tipo])
        self.setUp()
        conj = self.nicho("Sliding")
        self.porta(conj, abertura='CORRER')
        ficha = addon.orcamento.cadastro_do_modulo(conj)
        self.assertEqual(ficha['dobradicas'], [])
        self.assertFalse(ficha['dobradicas_pendentes'])

    def test_materiais_usados_incluem_portas_e_ignoram_slots_sem_faces(self):
        conj = self.nicho('Multicolor')
        grupo = self.porta(conj)
        mat = bpy.data.materials.new('Alias .001')
        mat[addon.materiais.CHAVE_MATERIAL] = "MDP/Woodgrains//Freijo"
        folhas = addon.portas._folhas_portas(grupo)
        addon.materiais.aplicar([folhas[0]], mat)
        folhas[0].data.materials.append(bpy.data.materials.new('Unused Slot'))
        nativo = bpy.data.materials.new('Custom Lacquer')
        addon.materiais.aplicar([folhas[1]], nativo)
        ficha = addon.orcamento.cadastro_do_modulo(conj)
        self.assertEqual(ficha['materiais'], ['Custom Lacquer', 'MDF White TX', 'MDP Freijo'])
        self.assertEqual(ficha['pecas_sem_material'], 0)

    def test_material_e_dobradica_ausentes_viram_pendencia(self):
        conj = self.nicho('Incomplete')
        grupo = self.porta(conj)
        p = dict(grupo['porta_parametros'])
        p.pop('dobradica')
        grupo['porta_parametros'] = p
        peca = addon.modulos._chapas_do_conjunto(conj)[0]
        peca.data.materials.clear()
        self.comodo(conj, "Kitchen")
        texto, n, pendencias = addon.orcamento.orcamento_da_cena(bpy.context.scene)
        self.assertEqual(n, 1)
        self.assertIn('  - 1 part without material\n', texto)
        self.assertIn('  - Hinges: not identified\n', texto)
        self.assertEqual(pendencias, [
            '- Kitchen, Incomplete: material not identified on 1 part.',
            '- Kitchen, Incomplete: hinge type not identified.'])

    def test_pendencias_do_que_ficou_pela_metade(self):
        # Cabinets without a room are excluded because every item belongs in a room.
        # Automatic names and loose panels become pending items; without cabinetry,
        # omit the furniture block because empty blocks have no heading.
        conj = self.nicho()
        self.assertTrue(addon.orcamento.NOME_AUTOMATICO_MODULO.match(conj.name))
        bpy.ops.object.select_all(action='DESELECT')
        addon.chapas.nova_chapa('Loose Panel', 600.0, 400.0, 18.0, (3000.0, 0.0, 0.0),
                         (0.0, 0.0, 0.0), bpy.context)
        texto, exportados, pendencias = addon.orcamento.orcamento_da_cena(bpy.context.scene)
        self.assertEqual(exportados, 0)
        self.assertNotIn("## Furniture", texto)
        self.assertIn('## Other\n\n### General\n- General cleaning.\n', texto)
        self.assertEqual(len(pendencias), 3)
        self.assertIn("- %s: the room was not specified; the cabinet was excluded from the estimate." % conj.name, pendencias)
        self.assertIn('- 1 loose panel, outside a cabinet: the cabinet was not specified; '
                      'excluded from the estimate.', pendencias)
        self.assertTrue(texto.endswith(
            '\n```\n\nPending items\n' + '\n'.join(pendencias)
            + "\n\nWould you like to update any of these before I rebuild the estimate?\n"))
        # Even with a room assigned, an automatic name remains pending under that room.
        self.comodo(conj, "Bedroom")
        pendencias = addon.orcamento.orcamento_da_cena(bpy.context.scene)[2]
        self.assertIn('- Bedroom, %s: the cabinet type was not specified '
                      '(the group still has its automatic name).'
                      % conj.name, pendencias)

    def test_comodo_na_aba_modulos_e_uma_linha_que_expande(self):
        # User request: the fixed grid occupied the tab. Collapsed, use one row;
        # expanded, list rooms, previously entered names, an unassigned entry if needed,
        # and a custom-name option. Apply to all selected cabinets.
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
        self.assertEqual(campo(), [])               # No cabinet means no room.
        # Panel from A plus door leaf from B: both cabinets.
        chapa = addon.modulos._chapas_do_conjunto(a)[0]
        folha = addon.portas._folhas_portas(self.porta(b))[0]
        bpy.ops.object.select_all(action='DESELECT')
        chapa.select_set(True)
        folha.select_set(True)
        bpy.context.view_layer.objects.active = chapa
        (fechado,) = campo()
        self.assertEqual(fechado[4], 'Room: (none)')
        self.assertEqual(lista(), [])               # Collapsed: a single row.
        tela[addon.gaveta._CHAVE_SUSPENSO] = addon.orcamento.SUSPENSO_COMODO
        self.assertEqual([e[2] for e in lista()],
                         [*addon.orcamento.COMODOS, addon.orcamento.COMODO_OUTRO])
        self.assertEqual(bpy.ops.object.cabinet_definir_comodo(nome="Balcony"),
                         {'FINISHED'})
        for conj in (a, b):
            self.assertEqual(addon.orcamento._nome_comodo(addon.orcamento._comodo_do_modulo(conj)),
                             "Balcony")
        self.assertEqual(campo()[0][4], 'Room: Balcony')
        self.assertEqual([e[2] for e in lista() if e[3]], ["Balcony"])
        self.assertIn(addon.orcamento.COMODO_NENHUM, [e[2] for e in lista()])
        # The custom-name choice opens a black-box field immediately below the row.
        addon.orcamento._abrir_caixa_comodo(bpy.context)
        self.addCleanup(addon.perguntas._pergunta_atual.__setitem__, 0, None)
        self.addCleanup(addon.solda._nome_grupo_gaveta.__setitem__, 0, None)
        caixa = [v for v in widgets() if v[5][0] == 'pergunta']
        self.assertEqual(len(caixa), 1)
        self.assertTrue(caixa[0][4].startswith('Room name: '))
        self.assertLess(caixa[0][1], campo()[0][1])
        # Keep the legacy synonym as input to preserve normalization coverage.
        addon.solda._nome_grupo_gaveta[0]['texto'] = 'Varanda'
        self.assertEqual(bpy.ops.object.cabinet_definir_comodo(digitado=True),
                         {'FINISHED'})
        self.assertIsNone(addon.perguntas._pergunta_atual[0])
        # The legacy synonym resolves to the same Balcony folder.
        self.assertEqual([c.name for c in bpy.data.collections
                          if c.get(addon.orcamento.MARCA_COLECAO_COMODO)], ["Balcony"])
        addon.orcamento._abrir_caixa_comodo(bpy.context)
        addon.solda._nome_grupo_gaveta[0]['texto'] = "John's Bedroom"
        self.assertTrue(addon.orcamento._confirmar_campo_gaveta(
            addon.solda._nome_grupo_gaveta[0]))
        self.assertEqual([e[2] for e in lista()][-3:],
                         ["John's Bedroom", addon.orcamento.COMODO_NENHUM,
                          addon.orcamento.COMODO_OUTRO])
        # Unassigned room: return the Collection to the root and remove empty folders.
        bpy.ops.object.cabinet_definir_comodo(nome=addon.orcamento.COMODO_NENHUM)
        cena = bpy.context.scene
        for conj in (a, b):
            self.assertIn(addon.modulos._colecao_do_modulo(conj).name,
                          cena.collection.children)
        self.assertFalse([c for c in bpy.data.collections
                          if c.get(addon.orcamento.MARCA_COLECAO_COMODO)])

    def test_comodo_e_pasta_no_outliner(self):
        # Outliner: Kitchen > Cabinet > panels and door. The folder is authoritative:
        # dragging the cabinet to another folder changes its estimate assignment.
        conj = self.nicho(INFERIOR)
        self.porta(conj)
        self.comodo(conj, "Kitchen")
        cena = bpy.context.scene
        pasta = cena.collection.children["Kitchen"]
        self.assertTrue(pasta.get(addon.orcamento.MARCA_COLECAO_COMODO))
        colecao = addon.modulos._colecao_do_modulo(conj)
        self.assertEqual(list(pasta.children), [colecao])
        self.assertNotIn(colecao.name, cena.collection.children)
        self.assertEqual(set(pasta.all_objects), set(colecao.all_objects))
        self.assertIn(addon.portas._portas_do_conjunto(conj)[0].name,
                      colecao.all_objects)
        # The user drags it into a living-room Outliner folder.
        sala = bpy.data.collections.new("Living Room")
        sala[addon.orcamento.MARCA_COLECAO_COMODO] = 1
        cena.collection.children.link(sala)
        sala.children.link(colecao)
        pasta.children.unlink(colecao)
        bloco = self.bloco(addon.orcamento.orcamento_da_cena(cena)[0])
        self.assertIn('### Living Room\n- ' + INFERIOR, bloco)
        self.assertNotIn('### Kitchen', bloco)

    def test_armario_antigo_sem_collection_ganha_a_dele(self):
        # Before v168, cabinets had no Collection. Since only Collections can enter
        # the folder, create one here with the Empty's name.
        conj = self.nicho('Legacy')
        colecao = addon.modulos._colecao_do_modulo(conj)
        for o in [conj, *conj.children_recursive]:
            bpy.context.scene.collection.objects.link(o)
            colecao.objects.unlink(o)
        bpy.data.collections.remove(colecao)
        self.assertIsNone(addon.modulos._colecao_do_modulo(conj))
        self.comodo(conj, "Dining Room")
        colecao = addon.modulos._colecao_do_modulo(conj)
        self.assertEqual(colecao.name, conj.name)
        self.assertIn(colecao.name,
                      bpy.context.scene.collection.children["Dining Room"].children)

    def arquivo(self, nome='Estimate.txt'):
        pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, pasta, True)
        return os.path.join(pasta, nome)

    def test_gerar_mostra_o_resultado_nas_opcoes(self):
        # User report: copying appeared to do nothing because feedback only reached
        # the status bar. The button at the bottom of Options now highlights and reports
        # its result; pending items remain visible in a black box immediately below.
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
        self.assertTrue(botao[4].startswith('Saved: 0 cabinet(s)'))
        caixa = [v for v in rodape if v[5][0] == 'pergunta']
        self.assertEqual(len(caixa), 1)
        self.assertTrue(caixa[0][4].startswith('Pending items:\n'))
        self.assertLess(caixa[0][1], botao[1])
        # Keep everything inside the panel, expanding upward from the gear icon.
        painel = addon.gaveta._retangulo_painel_opcoes(rodape)
        self.assertGreaterEqual(caixa[0][1], painel[1])
        self.assertTrue(bpy.app.timers.is_registered(
            addon.orcamento._apagar_orcamento_gerado))
        addon.orcamento._apagar_orcamento_gerado()
        self.assertIsNone(addon.orcamento._orcamento_gerado[0])

    def test_operador_salva_o_txt(self):
        # User request: Save As produces a .txt readable in Notepad, using the company's
        # exact text format with UTF-8 accents.
        conj = self.nicho("Vanity Cabinet")
        self.comodo(conj, "Bathroom")
        self.addCleanup(addon.orcamento._orcamento_gerado.__setitem__, 0, None)
        caminho = self.arquivo('Renovation - Zo\u00eb')  # Preserve UTF-8 filename coverage.
        self.assertEqual(bpy.ops.object.cabinet_exportar_orcamento(
            filepath=caminho), {'FINISHED'})
        with open(caminho + '.txt', encoding='utf-8') as f:
            salvo = f.read()
        self.assertEqual(salvo, addon.orcamento.orcamento_da_cena(
            bpy.context.scene)[0])
        self.assertIn('### Bathroom\n- Vanity Cabinet\n', salvo)
        self.assertEqual(addon.orcamento._orcamento_gerado[0]['arquivo'],
                         'Renovation - Zo\u00eb.txt')
        # For a nonexistent directory, warn rather than claiming success.
        addon.orcamento._orcamento_gerado[0] = None
        with self.assertRaises(RuntimeError):
            bpy.ops.object.cabinet_exportar_orcamento(
                filepath=os.path.join(caminho, 'not', 'found.txt'))
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
    raise RuntimeError("Estimate tests failed")
