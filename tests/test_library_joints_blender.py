"""Soldas da biblioteca: fixtures sinteticas, staging e publicacao temporarios."""
from contextlib import ExitStack
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tools.migrations.refine_library_joints as migracao

addon = migracao.base.addon


class TestSoldasBiblioteca(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cabinet_soldas_teste_')
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.biblioteca = self.raiz / 'biblioteca'
        self.biblioteca.mkdir()
        self.destino = self.raiz / 'preparo'
        addon.chapas._ocupado[0] = True
        migracao.base.limpar()
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        # A suite ja registrou o addon com guarda temporaria antes de criar fixtures.
        self.patches.enter_context(patch.object(addon, 'register'))
        self.patches.enter_context(patch.object(addon, 'unregister'))

    def fixture(self):
        colecao = bpy.data.collections.new('Montagem')
        bpy.context.scene.collection.children.link(colecao)
        colecao.asset_mark()
        colecao.asset_data.catalog_id = 'af970f2e-98be-4137-a087-f93650e70041'
        preview = colecao.preview_ensure()
        preview.image_size = (2, 2)
        preview.image_pixels_float = [.2, .4, .6, 1.] * 4
        grupo = bpy.data.objects.new('Grupo', None)
        grupo['eh_conjunto_chapa'] = True
        colecao.objects.link(grupo)
        material = bpy.data.materials.new('Material conservado')
        material.use_nodes = True
        for nome in ('A', 'B'):
            malha = bpy.data.meshes.new(nome)
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=.018)
            bm.to_mesh(malha)
            bm.free()
            malha.materials.append(material)
            objeto = bpy.data.objects.new(nome, malha)
            objeto['eh_chapa'] = True
            objeto['chapa_uid'] = 'uid-' + nome
            objeto['sistema_conservado'] = {'parametros': [1., 2., 3.]}
            objeto.parent = grupo
            colecao.objects.link(objeto)
        a, b = bpy.data.objects['A'], bpy.data.objects['B']
        a['adj_x_pos'] = b.name
        a['adj_x_pos_uid'] = b['chapa_uid']
        a['adj_x_pos_ancoras'] = ['v0|v0', 'v1|v1']
        a['adj_x_pos_folga'] = 0.
        a['adj_x_pos_face'] = 0
        a['adj_y_pos'] = b.name
        a['adj_y_pos_uid'] = b['chapa_uid']
        a['adj_y_pos_ancoras'] = ['v2|v2']
        bpy.context.view_layer.update()
        bpy.data.libraries.write(str(self.biblioteca / 'Teste.blend'),
            {colecao, grupo, a, b}, fake_user=True, compress=True)
        (self.biblioteca / 'Teste.png').write_bytes(b'foto conservada byte por byte')
        (self.biblioteca / 'indice.json').write_text(json.dumps([
            dict(nome='Teste', arquivo='Teste.blend', tipo='modulo')]), encoding='utf-8')
        (self.biblioteca / 'blender_assets.cats.txt').write_text('VERSION 1\n', encoding='utf-8')
        return colecao, [grupo, a, b]

    def normalizar_fixture(self, pecas, recalcular_ancoras=False):
        self.assertTrue(recalcular_ancoras)
        a = next(o for o in pecas if o.name == 'A')
        for chave in list(a.keys()):
            if chave.startswith('adj_y_pos'):
                del a[chave]
        a['adj_x_pos_ancoras'] = ['v0|v0']
        a['adj_x_pos_origens'] = '[[0.0, 0.0, 0.0]]'
        a['adj_x_pos_restricoes'] = '[["a", "y_pos", 0, 0.0]]'
        return dict(ligacoes=1, removidas=1, ancoras=1, alteradas=['A'], invalidas=[])

    def preparar(self, normalizar=None):
        with patch.object(addon.solda, 'normalizar_ligacoes',
                side_effect=normalizar or self.normalizar_fixture, create=True):
            return migracao.preparar(self.biblioteca, self.destino)

    def test_recusa_destino_interno_inclusive_maiusculas(self):
        for destino in (self.biblioteca, self.biblioteca / 'preparo'):
            with self.assertRaises(ValueError):
                migracao.preparar(str(self.biblioteca).upper(), destino)
        self.assertFalse(list(self.biblioteca.iterdir()))

    def test_api_indisponivel_nao_cria_preparo(self):
        with patch.object(addon.solda, 'normalizar_ligacoes', None, create=True):
            with self.assertRaisesRegex(RuntimeError, 'indisponivel'):
                migracao.preparar(self.biblioteca, self.destino)
        self.assertFalse(self.destino.exists())

    def test_auditoria_e_somente_leitura_e_conta_pares_de_objetos(self):
        self.fixture()
        antes = migracao._arquivos(self.biblioteca)
        with patch.object(addon.solda, 'normalizar_ligacoes', create=True) as normalizar:
            resultado = migracao.auditar(self.biblioteca, self.destino)
        normalizar.assert_not_called()
        self.assertEqual(resultado['resumo']['registros'], 2)
        self.assertEqual(resultado['resumo']['pares'], 1)
        self.assertEqual(resultado['resumo']['ancoras'], 3)
        self.assertEqual(resultado['resumo']['pares_repetidos'], 1)
        self.assertEqual(migracao._arquivos(self.biblioteca), antes)

    def test_auditoria_separa_legado_sem_ancora_de_vizinho_invalido(self):
        _cols, objetos = self.fixture()
        a = bpy.data.objects['A']
        del a['adj_x_pos_ancoras']
        a['adj_y_pos_uid'] = 'uid-inexistente'
        a['adj_y_pos'] = 'Ausente'
        resultado = migracao.auditar_objetos(objetos)
        self.assertEqual(resultado['sem_ancoras_gravadas'], 1)
        self.assertEqual(len(resultado['invalidas']), 1)

    def test_pares_distintos_do_mesmo_modulo_podem_usar_mesmo_vertice(self):
        _cols, objetos = self.fixture()
        a, b = bpy.data.objects['A'], bpy.data.objects['B']
        c = bpy.data.objects.new('C', b.data.copy())
        c['eh_chapa'] = True
        c['chapa_uid'] = 'uid-C'
        c.parent = a.parent
        bpy.context.scene.collection.objects.link(c)
        a['adj_x_pos_ancoras'] = ['v0|v0']
        a['adj_y_pos'] = c.name
        a['adj_y_pos_uid'] = c['chapa_uid']
        a['adj_y_pos_ancoras'] = ['v0|v0']
        resultado = migracao.auditar_objetos(objetos + [c])
        self.assertEqual(resultado['pares'], 2)
        migracao._conferir_soldas(resultado, resultado)

    def test_preparo_reabre_conserva_fotos_catalogos_preview_e_backup(self):
        self.fixture()
        hashes = migracao._arquivos(self.biblioteca)
        m = self.preparar()
        self.assertTrue(m['verificado'])
        self.assertFalse(m['publicado'])
        self.assertEqual(len(m['arquivos']), 1)
        self.assertEqual(m['arquivos'][0]['nome'], 'Teste.blend')
        self.assertEqual(m['resumo_depois']['registros'], 1)
        self.assertEqual(m['auditoria_minimos']['pares'], 1)
        self.assertEqual(m['auditoria_minimos']['excesso_maximo_mm'], 0.)
        self.assertEqual(migracao._arquivos(self.biblioteca), hashes)
        self.assertEqual(migracao._arquivos(self.destino / 'originais'), hashes)
        for nome in ('Teste.png', 'indice.json', 'blender_assets.cats.txt'):
            self.assertEqual(migracao.base.digital(self.destino / 'novos' / nome), hashes[nome])
        cols, objetos = migracao.base.carregar(str(self.destino / 'novos/Teste.blend'))
        self.assertEqual(cols[0].asset_data.catalog_id, 'af970f2e-98be-4137-a087-f93650e70041')
        self.assertEqual(tuple(cols[0].preview.image_size), (2, 2))
        self.assertEqual(bpy.data.objects['A']['chapa_uid'], 'uid-A')

    def test_minimo_global_independente_em_mundo_recusa_ancora_mais_longa(self):
        _cols, objetos = self.fixture()
        a, b = bpy.data.objects['A'], bpy.data.objects['B']
        for chave in list(a.keys()):
            if chave.startswith('adj_y_pos'):
                del a[chave]
        a.rotation_euler = (.15, -.3, .7)
        a.scale = (2., .8, 1.4)
        b.rotation_euler = (-.2, .1, -.4)
        b.location = (.035, .012, .007)
        b.scale = (.7, 1.3, .9)
        bpy.context.view_layer.update()
        candidatos = sorted((math.dist(a.matrix_world @ v.co, b.matrix_world @ w.co), v.index, w.index)
                            for v in a.data.vertices for w in b.data.vertices)
        distancia, i, j = candidatos[0]
        a['adj_x_pos_ancoras'] = ['v%d|v%d' % (i, j)]
        antes = migracao._estado_soldas(objetos)
        with patch.object(addon.solda, '_vertices_mais_proximos', side_effect=AssertionError('Nao chamar o solver')):
            resultado = migracao.validar_minimos_reais(objetos)
        migracao.base.conferir(antes, migracao._estado_soldas(objetos))
        self.assertAlmostEqual(resultado[0]['minimo_mm'], distancia * 1000, places=8)
        self.assertLessEqual(resultado[0]['excesso_mm'], migracao.TOLERANCIA_MINIMO_MM)
        _distancia, i, j = candidatos[-1]
        a['adj_x_pos_ancoras'] = ['v%d|v%d' % (i, j)]
        with self.assertRaisesRegex(RuntimeError, 'minimo real global'):
            migracao.validar_minimos_reais(objetos)
        b.data.clear_geometry()
        with self.assertRaisesRegex(RuntimeError, 'sem vertices reais'):
            migracao.validar_minimos_reais(objetos)

    def test_api_real_refina_pares_e_conserva_restricoes_axiais(self):
        self.fixture()
        m = migracao.preparar(self.biblioteca, self.destino)
        self.assertTrue(m['verificado'])
        self.assertEqual(m['resumo_depois']['registros'], 1)
        self.assertEqual(m['resumo_depois']['ancoras'], 1)
        _cols, objetos = migracao.base.carregar(str(self.destino / 'novos/Teste.blend'))
        a = next(o for o in objetos if o.name == 'A')
        self.assertEqual(len(json.loads(a['adj_x_pos_restricoes'])), 1)
        self.assertEqual(len(migracao._restricoes_axiais(objetos)), 2)

    def test_preparo_recusa_movimento_de_vertice(self):
        self.fixture()
        def mover(pecas, **opcoes):
            resultado = self.normalizar_fixture(pecas, **opcoes)
            pecas[0].data.vertices[0].co.x += .001
            return resultado
        with self.assertRaises(AssertionError):
            self.preparar(mover)
        self.assertFalse(migracao._ler(self.destino / 'manifesto.json')['verificado'])

    def test_preparo_recusa_diagnosticos_da_api(self):
        self.fixture()
        def invalida(pecas, **opcoes):
            return dict(invalidas=['ancora apagada'])
        with self.assertRaisesRegex(RuntimeError, 'exige revisao'):
            self.preparar(invalida)

    def test_preparo_exige_idempotencia_depois_de_reabrir(self):
        self.fixture()
        def instavel(pecas, **opcoes):
            resultado = self.normalizar_fixture(pecas, **opcoes)
            a = next(o for o in pecas if o.name == 'A')
            a['adj_x_pos_folga'] = a.get('adj_x_pos_folga', 0.) + 1.
            return resultado
        with self.assertRaises(AssertionError):
            self.preparar(instavel)

    def test_estado_protege_material_modificador_atributo_e_uid(self):
        cols, objetos = self.fixture()
        a = bpy.data.objects['A']
        modificador = a.modifiers.new('Liso conservado', 'BEVEL')
        atributo = a.data.attributes.new('atributo_modelado', 'FLOAT', 'POINT')
        material = bpy.data.materials['Material conservado']
        outro = bpy.data.materials.new('Outro material')
        outro.use_nodes = True
        self.assertEqual(material.node_tree.name, outro.node_tree.name)
        antes = migracao.estado_protegido([cols], objetos)
        alteracoes = [(lambda: setattr(modificador, 'width', .04)),
            (lambda: setattr(atributo.data[0], 'value', 2.)),
            (lambda: a.__setitem__('chapa_uid', 'uid-trocado')),
            (lambda: setattr(material, 'diffuse_color', (1., 0., 0., 1.))),
            (lambda: setattr(material.node_tree.nodes.get('Principled BSDF').inputs['Roughness'], 'default_value', .123))]
        for alterar in alteracoes:
            alterar()
            with self.assertRaises(AssertionError):
                migracao.base.conferir(antes, migracao.estado_protegido([cols], objetos))
            antes = migracao.estado_protegido([cols], objetos)

    def test_estado_admite_somente_metadados_adj_e_atributos_de_solda(self):
        cols, objetos = self.fixture()
        a = bpy.data.objects['A']
        antes = migracao.estado_protegido([cols], objetos)
        a['adj_x_pos_manual'] = True
        a.data.attributes.new('cabinet_solda_vertice', 'INT', 'POINT')
        a.data.attributes.new('cabinet_canto', 'INT', 'POINT')
        migracao.base.conferir(antes, migracao.estado_protegido([cols], objetos))

    def test_preset_complexo_reabre_em_temporario_com_estado_protegido_identico(self):
        if bpy.app.version < (5,):
            self.skipTest('Biblioteca 5.x nao abre em Blender 4.2')
        fonte = Path(__file__).resolve().parents[1] / 'cabinet_creator/biblioteca/Armario_Quarto_08_600x2503x550.blend'
        digital = migracao.base.digital(fonte)
        copia = self.raiz / 'copia.blend'
        shutil.copy2(fonte, copia)
        cols, objetos = migracao.base.carregar(str(copia))
        antes = migracao.estado_protegido(cols, objetos)
        novo = self.raiz / 'regravado.blend'
        bpy.data.libraries.write(str(novo), set(cols) | set(objetos), fake_user=True, compress=True)
        cols, objetos = migracao.base.carregar(str(novo))
        migracao.base.conferir(antes, migracao.estado_protegido(cols, objetos))
        self.assertEqual(migracao.base.digital(fonte), digital)

    def test_publica_e_reverte_somente_blend(self):
        self.fixture()
        antes = migracao._arquivos(self.biblioteca)
        m = self.preparar()
        fonte = self.raiz / 'fonte.py'
        fonte.write_bytes(b'fonte anterior')
        m['fontes'][str(fonte)] = migracao.base.digital(fonte)
        migracao._gravar(self.destino / 'manifesto.json', m)
        self.assertTrue(migracao.publicar(self.destino)['publicado'])
        self.assertEqual(migracao._arquivos(self.biblioteca), migracao._arquivos(self.destino / 'novos'))
        fonte.write_bytes(b'fonte evoluiu depois de publicar')
        self.assertFalse(migracao.publicar(self.destino, reverter=True)['publicado'])
        self.assertEqual(migracao._arquivos(self.biblioteca), antes)

    def test_publicacao_recusa_fonte_alterada_ausente_ou_sem_hash_antes_de_escrever(self):
        self.fixture()
        m = self.preparar()
        fonte = self.raiz / 'fonte.py'
        fonte.write_bytes(b'fonte anterior')
        m['fontes'][str(fonte)] = migracao.base.digital(fonte)
        migracao._gravar(self.destino / 'manifesto.json', m)
        antes = migracao._arquivos(self.biblioteca)
        fonte.write_bytes(b'fonte modificada')
        for estado in ('alterada', 'ausente', 'sem_hashes'):
            if estado == 'ausente':
                fonte.unlink()
            elif estado == 'sem_hashes':
                m['fontes'] = {}
                migracao._gravar(self.destino / 'manifesto.json', m)
            manifesto_antes = (self.destino / 'manifesto.json').read_bytes()
            with self.subTest(estado=estado), patch.object(migracao.shutil, 'copyfile') as copiar:
                with self.assertRaisesRegex(RuntimeError, 'Fonte mudou'):
                    migracao.publicar(self.destino)
                copiar.assert_not_called()
            self.assertEqual(migracao._arquivos(self.biblioteca), antes)
            self.assertFalse(list(self.biblioteca.glob('*.solda-nova')))
            self.assertEqual((self.destino / 'manifesto.json').read_bytes(), manifesto_antes)

    def test_publicacao_recusa_foto_alterada_antes_de_escrever(self):
        self.fixture()
        self.preparar()
        (self.biblioteca / 'Teste.png').write_bytes(b'foto editada')
        antes = migracao._arquivos(self.biblioteca)
        with patch.object(migracao.shutil, 'copyfile') as copiar:
            with self.assertRaisesRegex(RuntimeError, 'mudou'):
                migracao.publicar(self.destino)
        copiar.assert_not_called()
        self.assertEqual(migracao._arquivos(self.biblioteca), antes)

    def test_publicacao_recusa_backup_ou_staging_adulterado(self):
        self.fixture()
        self.preparar()
        for pasta in ('originais', 'novos'):
            caminho = self.destino / pasta / 'Teste.blend'
            dados = caminho.read_bytes()
            caminho.write_bytes(b'arquivo adulterado')
            with self.assertRaisesRegex(RuntimeError, 'mudou'):
                migracao.publicar(self.destino)
            caminho.write_bytes(dados)

    def test_publicacao_nao_apaga_temporario_preexistente(self):
        self.fixture()
        self.preparar()
        temporario = self.biblioteca / 'Teste.blend.solda-nova'
        temporario.write_bytes(b'arquivo de outro processo')
        with self.assertRaisesRegex(RuntimeError, 'Temporario ja existe'):
            migracao.publicar(self.destino)
        self.assertEqual(temporario.read_bytes(), b'arquivo de outro processo')

    def test_publicacao_recusa_manifesto_incompleto_nome_inseguro_e_repetido(self):
        self.fixture()
        m = self.preparar()
        original = json.dumps(m)
        for campo, valor in (('verificado', False), ('publicado', True)):
            m = json.loads(original)
            m[campo] = valor
            migracao._gravar(self.destino / 'manifesto.json', m)
            with self.assertRaises(RuntimeError):
                migracao.publicar(self.destino)
        for nome in ('../fora.blend', 'Teste.png', 'C:fora.blend'):
            m = json.loads(original)
            m['arquivos'][0]['nome'] = nome
            migracao._gravar(self.destino / 'manifesto.json', m)
            with self.assertRaises(ValueError):
                migracao.publicar(self.destino)
        m = json.loads(original)
        m['arquivos'] *= 2
        migracao._gravar(self.destino / 'manifesto.json', m)
        with self.assertRaises(ValueError):
            migracao.publicar(self.destino)

    def test_falha_ao_gravar_manifesto_desfaz_toda_publicacao(self):
        self.fixture()
        self.preparar()
        antes = migracao._arquivos(self.biblioteca)
        with patch.object(migracao, '_gravar', side_effect=OSError('falha de disco')):
            with self.assertRaises(OSError):
                migracao.publicar(self.destino)
        self.assertEqual(migracao._arquivos(self.biblioteca), antes)
        self.assertFalse(migracao._ler(self.destino / 'manifesto.json')['publicado'])

    def test_falha_na_segunda_troca_restaura_primeiro_e_remove_temporario(self):
        self.fixture()
        shutil.copy2(self.biblioteca / 'Teste.blend', self.biblioteca / 'Segundo.blend')
        indice = migracao._ler(self.biblioteca / 'indice.json')
        indice.append(dict(nome='Segundo', arquivo='Segundo.blend', tipo='modulo'))
        migracao._gravar(self.biblioteca / 'indice.json', indice)
        self.preparar()
        antes = migracao._arquivos(self.biblioteca)
        substituir = migracao.os.replace
        def falhar(origem, alvo):
            if Path(alvo).name == 'Segundo.blend':
                raise OSError('segunda troca falhou')
            substituir(origem, alvo)
        with patch.object(migracao.os, 'replace', side_effect=falhar):
            with self.assertRaises(OSError):
                migracao.publicar(self.destino)
        self.assertEqual(migracao._arquivos(self.biblioteca), antes)
        self.assertFalse(list(self.biblioteca.glob('*.solda-nova')))


with tempfile.TemporaryDirectory(prefix='cabinet_soldas_guarda_') as guarda:
    with patch.object(addon.opcoes, '_pasta_addon', return_value=guarda), \
            patch.object(addon.biblioteca, 'pasta_biblioteca', return_value=guarda):
        addon.register()
        try:
            resultado = unittest.TextTestRunner(verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(TestSoldasBiblioteca))
        finally:
            migracao.base.limpar()
            addon.chapas._ocupado[0] = False
            addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Soldas da biblioteca reprovadas')
