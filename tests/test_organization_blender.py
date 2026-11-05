"""Contratos de importacao e recarga dos setores, sem tocar na biblioteca."""
import importlib
import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

SETORES = {'chapas':'panels', 'modulos':'cabinets', 'portas':'doors',
           'gavetas':'drawers', 'prateleiras':'shelves', 'divisorias':'partitions'}
PASTA_ADDON_ORIGINAL = addon.opcoes._pasta_addon


class TestOrganizacao(unittest.TestCase):
    def modulo_de_teste(self, internos=False):
        conjunto = addon.modulos.criar_armario(bpy.context, 'Teste coordenacao', 800, 700, 560,
                                               fundo=False)
        self.addCleanup(self.apagar_modulo, conjunto.name)
        if internos:
            addon.gavetas.criar_gavetas(bpy.context, conjunto, (18,18,18,350,0),
                                        dict(quantidade=2, profundidade_mm=400))
            addon.prateleiras.criar_prateleiras(bpy.context, conjunto, (18,18,350,18,0),
                                                dict(quantidade=2, profundidade_mm=400))
        bpy.context.view_layer.update()
        return conjunto

    def apagar_modulo(self, nome):
        conjunto = bpy.data.objects.get(nome)
        if conjunto is not None:
            for obj in list(reversed(conjunto.children_recursive)):
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.objects.remove(conjunto, do_unlink=True)

    def assinatura(self, conjunto):
        return (tuple(addon.modulos.medir_conjunto(conjunto)),
                {o.name: (tuple(v for linha in o.matrix_world for v in linha),
                          [tuple(v.co) for v in o.data.vertices] if o.type == 'MESH' else None)
                 for o in conjunto.children_recursive},
                [addon.gavetas.parametros(g) for g in addon.gavetas.grupos_do_modulo(conjunto)],
                [addon.prateleiras.parametros(g) for g in addon.prateleiras.grupos_do_modulo(conjunto)])

    def test_coordenador_atualiza_portas_gavetas_prateleiras_uma_vez_nesta_ordem(self):
        conjunto = self.modulo_de_teste()
        chamadas = []
        with patch.object(addon.portas, 'atualizar_do_conjunto',
                          side_effect=lambda c: chamadas.append(('portas', c))), \
             patch.object(addon.gavetas, 'atualizar_gavetas_do_conjunto',
                          side_effect=lambda c: chamadas.append(('gavetas', c))), \
             patch.object(addon.prateleiras, 'atualizar_do_conjunto',
                          side_effect=lambda c: chamadas.append(('prateleiras', c))):
            addon.modulos.atualizar_sistemas_do_conjunto(conjunto)
        self.assertEqual(chamadas, [(nome, conjunto) for nome in ('portas','gavetas','prateleiras')])

    def test_atualizar_apenas_portas_preserva_internos_reais(self):
        conjunto = self.modulo_de_teste(internos=True)
        antes = self.assinatura(conjunto)
        with patch.object(addon.gavetas, 'atualizar_gavetas_do_conjunto',
                          side_effect=AssertionError('Atualizou gavetas fora do escopo')), \
             patch.object(addon.prateleiras, 'atualizar_do_conjunto',
                          side_effect=AssertionError('Atualizou prateleiras fora do escopo')):
            addon.modulos.atualizar_sistemas_do_conjunto(conjunto, internos=False)
            addon.portas.atualizar_portas_do_conjunto(conjunto, sistemas=False)
        self.assertEqual(self.assinatura(conjunto), antes)

    def test_api_legada_delega_ao_mesmo_coordenador_sem_duplicar(self):
        conjunto = self.modulo_de_teste()
        chamadas = []
        with patch.object(addon.portas, 'atualizar_do_conjunto',
                          side_effect=lambda c: chamadas.append('portas')), \
             patch.object(addon.gavetas, 'atualizar_gavetas_do_conjunto',
                          side_effect=lambda c: chamadas.append('gavetas')), \
             patch.object(addon.prateleiras, 'atualizar_do_conjunto',
                          side_effect=lambda c: chamadas.append('prateleiras')):
            addon.portas.atualizar_portas_do_conjunto(conjunto)
        self.assertEqual(chamadas, ['portas','gavetas','prateleiras'])

    def test_coordenador_ignora_alvo_ausente_ou_sem_marca(self):
        comum = bpy.data.objects.new('Alvo comum de teste', None)
        try:
            with patch.object(addon.portas, 'atualizar_do_conjunto',
                              side_effect=AssertionError('Aceitou objeto que nao e modulo')):
                addon.modulos.atualizar_sistemas_do_conjunto(None)
                addon.modulos.atualizar_sistemas_do_conjunto(comum)
                addon.portas.atualizar_portas_do_conjunto(None)
        finally:
            bpy.data.objects.remove(comum)

    def test_resize_sem_porta_usa_coordenador_e_preserva_malhas_modeladas(self):
        conjunto = self.modulo_de_teste(internos=True)
        grupo = addon.prateleiras.grupos_do_modulo(conjunto)[0]
        fonte = addon.prateleiras.prateleiras_do_grupo(grupo)[0]
        fonte.data.vertices[0].co.x += .025
        fonte.data.update()
        antes = [(o, o.data, [tuple(v.co) for v in o.data.vertices])
                 for o in grupo.children if o.type == 'MESH']
        with patch.object(addon.portas, 'atualizar_portas_do_conjunto',
                          side_effect=AssertionError('Resize entrou pela API legada de portas')), \
             patch.object(addon.gavetas, 'atualizar_gavetas_do_conjunto',
                          wraps=addon.gavetas.atualizar_gavetas_do_conjunto) as gavetas, \
             patch.object(addon.prateleiras, 'atualizar_do_conjunto',
                          wraps=addon.prateleiras.atualizar_do_conjunto) as prateleiras:
            conjunto.conj_largura_mm = 1000
            bpy.context.view_layer.update()
            gavetas.assert_called_once_with(conjunto)
            prateleiras.assert_called_once_with(conjunto)
        self.assertAlmostEqual(addon.modulos.medir_conjunto(conjunto)[0], 1000, places=2)
        for obj, malha, vertices in antes:
            self.assertEqual(obj.data, malha)
            self.assertEqual([tuple(v.co) for v in obj.data.vertices], vertices)

    def test_producao_nao_coordena_sistemas_pela_api_legada_de_portas(self):
        raiz = Path(addon.__file__).parent
        antigos = []
        for arquivo in raiz.rglob('*.py'):
            arvore = ast.parse(arquivo.read_text(encoding='utf-8-sig'))
            for no in ast.walk(arvore):
                if not isinstance(no, ast.Call):
                    continue
                nome = no.func.attr if isinstance(no.func, ast.Attribute) else (
                    no.func.id if isinstance(no.func, ast.Name) else '')
                if nome == 'atualizar_portas_do_conjunto':
                    antigos.append((str(arquivo.relative_to(raiz)), no.lineno))
        self.assertEqual(antigos, [], 'Chamador interno ainda depende da fachada legada')

    def test_undo_redo_do_resize_coordenado_restaura_corpo_e_internos(self):
        addon.eventos._fim_do_desfazer()
        self.addCleanup(addon.eventos._fim_do_desfazer)
        conjunto = self.modulo_de_teste(internos=True)
        nome = conjunto.name
        antes = self.assinatura(conjunto)
        bpy.ops.ed.undo_push(message='Antes de resize coordenado')
        conjunto.conj_largura_mm = 1000
        bpy.context.view_layer.update()
        depois = self.assinatura(conjunto)
        bpy.ops.ed.undo_push(message='Resize coordenado concluido')
        bpy.ops.ed.undo()
        addon.eventos._fim_do_desfazer()
        conjunto = bpy.data.objects[nome]
        self.assertEqual(self.assinatura(conjunto), antes)
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        conjunto = bpy.data.objects[nome]
        self.assertEqual(self.assinatura(conjunto), depois)
        addon.eventos.verificar_periodicamente()
        self.assertEqual(self.assinatura(conjunto), depois)

    def test_pacotes_preservam_identidade_publica_sem_fonte_concorrente(self):
        raiz = Path(addon.__file__).parent
        for nome in SETORES:
            with self.subTest(setor=nome):
                modulo = importlib.import_module('cabinet_creator.' + nome)
                self.assertIs(modulo, getattr(addon, nome))
                self.assertIn(modulo, addon._MODULOS)
                self.assertEqual(Path(modulo.__file__).resolve(),
                                 (raiz / 'cabinetry' / SETORES[nome] / '__init__.py').resolve())
                self.assertFalse((raiz / (nome + '.py')).exists())
                self.assertIs(modulo, importlib.import_module(
                    'cabinet_creator.cabinetry.' + SETORES[nome]))
                for valor in vars(modulo).values():
                    if isinstance(valor, type) and valor.__module__.startswith('cabinet_creator.'):
                        self.assertEqual(valor.__module__, modulo.__name__)

    def test_todos_os_aliases_tem_uma_unica_implementacao_inglesa(self):
        for nome, modulo in addon._MODULE_ALIASES.items():
            with self.subTest(alias=nome):
                self.assertIs(importlib.import_module('cabinet_creator.' + nome), modulo)
                self.assertIs(importlib.import_module(modulo.__name__), modulo)
                self.assertIs(getattr(addon, nome), modulo)
                self.assertEqual(modulo.__name__.split('.')[1],
                                 Path(modulo.__file__).relative_to(Path(addon.__file__).parent).parts[0])

    def test_recursos_e_preferencias_continuam_na_raiz_instalavel(self):
        raiz = Path(addon.__file__).resolve().parent
        # Moving a source file must not create another library or preference key.
        self.assertEqual(addon.opcoes.CabinetCreatorPreferences.bl_idname, addon.__name__)
        self.assertEqual(Path(addon.ferragens.PASTA_FERRAGENS).resolve(), raiz/'ferragens')
        self.assertEqual(Path(addon.biblioteca.PASTA_FOTOS_PADRAO).resolve(), raiz/'fotos')
        # Capture before the fixture redirects the default to a temporary library.
        self.assertEqual(Path(PASTA_ADDON_ORIGINAL()).resolve(), raiz/'biblioteca')

    def test_recarga_religa_setores_e_preserva_objetos_da_cena(self):
        global addon
        conjunto = addon.modulos.criar_armario(bpy.context, 'Teste recarga setores', 600, 700, 400)
        nomes = [conjunto.name, *(o.name for o in conjunto.children_recursive)]
        vertices = {o.name: [tuple(v.co) for v in o.data.vertices]
                    for o in conjunto.children_recursive if o.type == 'MESH'}
        antigos = {nome: getattr(addon, nome) for nome in SETORES}
        pasta_teste = addon.biblioteca.pasta_biblioteca()
        addon.unregister()
        addon = importlib.reload(addon)
        # Reload tambem recarrega biblioteca/opcoes e remove os mocks;
        # reaplica o isolamento ANTES de registrar qualquer timer.
        # start() sem stop: no fim do teste o patch devolveria a funcao REAL
        # (a do reload) aos testes seguintes; o patch de fora restaura no fim.
        patch.object(addon.biblioteca, 'pasta_biblioteca', return_value=pasta_teste).start()
        patch.object(addon.opcoes, '_pasta_addon', return_value=pasta_teste).start()
        addon.register()
        try:
            for nome in nomes:
                self.assertIsNotNone(bpy.data.objects.get(nome))
            for nome, coordenadas in vertices.items():
                self.assertEqual(coordenadas, [tuple(v.co) for v in bpy.data.objects[nome].data.vertices])
            for nome, modulo in antigos.items():
                self.assertIs(getattr(addon, nome), modulo)
            self.assertIs(addon.assistente._portas, addon.portas)
            self.assertIs(addon.prateleiras._gavetas, addon.gavetas)
            self.assertIs(addon.divisorias._gavetas, addon.gavetas)
            self.assertIs(addon.modulos._portas, addon.portas)
            self.assertIs(addon.modulos._gavetas, addon.gavetas)
            self.assertIs(addon.modulos._prateleiras, addon.prateleiras)
            with patch.object(addon.portas, 'atualizar_do_conjunto') as atualizar:
                addon.modulos.atualizar_sistemas_do_conjunto(conjunto, internos=False)
                atualizar.assert_called_once_with(conjunto)
            self.assertTrue(issubclass(addon.prateleiras.OBJECT_OT_criar_prateleiras,
                                      addon.gavetas.AssistenteDoVao))
            self.assertTrue(issubclass(addon.divisorias.OBJECT_OT_criar_divisorias,
                                      addon.gavetas.AssistenteDoVao))
            self.assertEqual(bpy.ops.object.cabinet_selecionar.get_rna_type().identifier,
                             'OBJECT_OT_cabinet_selecionar')
        finally:
            for nome in reversed(nomes):
                obj = bpy.data.objects.get(nome)
                if obj is not None:
                    bpy.data.objects.remove(obj, do_unlink=True)


with tempfile.TemporaryDirectory(prefix='cabinet_organizacao_') as pasta:
    with patch.object(addon.biblioteca, 'pasta_biblioteca', return_value=pasta), \
         patch.object(addon.opcoes, '_pasta_addon', return_value=pasta):
        addon.register()
        try:
            resultado = unittest.TextTestRunner(verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(TestOrganizacao))
        finally:
            addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos contratos dos setores')
