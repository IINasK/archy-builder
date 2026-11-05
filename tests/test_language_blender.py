"""English UI and documentation acceptance scenarios, using disposable data."""
import ast
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import archy_builder as addon


class TestEnglishInterface(unittest.TestCase):
    def test_support_dimension_labels_keep_direction_actions(self):
        masonry = addon.alvenaria
        assembly = bpy.data.objects.new('English support dimensions', None)
        bpy.context.collection.objects.link(assembly)
        self.addCleanup(lambda: bpy.data.objects.remove(assembly, do_unlink=True))
        self.addCleanup(masonry.esquecer)
        assembly[masonry.MARCA] = 'TEST'
        bpy.context.view_layer.objects.active = assembly
        masonry._cotas_menu[0][assembly.name] = dict(
            esquerda=.1, direita=.2, acima=.3, abaixo=.4)
        rows = []
        masonry.widgets(bpy.context, rows, 12, 600, 540)
        dimensions = [row for row in rows if row[5] and row[5][:2] == ('medida', 'instalacao')]
        self.assertEqual([row[5][3] for row in dimensions], ['Left', 'Right', 'Above', 'Below'])
        self.assertEqual([row[5][2] for row in dimensions], ['esquerda', 'direita', 'acima', 'abaixo'])

    def test_main_tabs_have_english_names(self):
        items = bpy.types.Scene.bl_rna.properties['cabinet_aba'].enum_items
        self.assertEqual([item.name for item in items],
                         ['Modules', 'Doors', 'Back Panels', 'Drawers', 'Shelves',
                          'Partitions', 'Handles', 'Masonry'])

    def test_native_dimension_properties_use_english_labels(self):
        properties = bpy.types.Object.bl_rna.properties
        for identifier, word in (('chapa_largura_mm', 'Width'),
                                 ('chapa_comprimento_mm', 'Length'),
                                 ('chapa_espessura_mm', 'Thickness'),
                                 ('conj_altura_mm', 'Height'),
                                 ('conj_profundidade_mm', 'Depth')):
            with self.subTest(property=identifier):
                self.assertIn(word, properties[identifier].name)

    def test_registered_operator_labels_are_english(self):
        portuguese = re.compile(r'\b(?:Criar|Editar|Selecionar|Remover|Definir|Mostrar|Esconder|Aplicar|Cancelar|Confirmar|Rebaixar|Arrastar|Medidas|Prateleiras|Dobradicas|Puxadores|Gavetas|Divisorias|Alvenaria)\b', re.I)
        for cls in addon.CLASSES:
            with self.subTest(operator=cls.__name__):
                self.assertIsNone(portuguese.search(getattr(cls, 'bl_label', '')))

    def test_bundled_catalog_uses_english_labels_and_keeps_file_identity(self):
        import json
        root = Path(addon.__file__).parent/"assets/library"
        items = json.loads((root/'indice.json').read_text(encoding='utf-8'))
        forbidden = {'Armarios','Cozinha','Quartos','Inferiores','Superiores',
                     'Portas','Gaveteiros','Despenseiros','Chapas'}
        for item in items:
            self.assertFalse(forbidden.intersection(item.get('niveis',
                [item.get('n1',''),item.get('n2',''),item.get('n3','')])))
            self.assertTrue((root/item['arquivo']).is_file())

    def test_catalog_translation_preserves_unique_uuid_paths(self):
        root = Path(addon.__file__).parent/"assets/library"
        entries = [line.split(':', 2) for line in
                   (root/'blender_assets.cats.txt').read_text(encoding='utf-8').splitlines()
                   if line.count(':') >= 2]
        self.assertEqual(len({entry[0] for entry in entries}), len(entries))
        self.assertEqual(len({entry[1] for entry in entries}), len(entries))
        self.assertTrue(any('/Tall Cabinets' in entry[1] for entry in entries))
        self.assertTrue(any('/Tower Cabinets' in entry[1] for entry in entries))

    def test_english_mode_labels_keep_native_identifiers(self):
        panel = addon.chapas.nova_chapa('Language test panel', 500, 400, 18,
                                       (0,0,0), (0,0,0), bpy.context)
        self.addCleanup(lambda: bpy.data.objects.remove(panel, do_unlink=True))
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        panel.select_set(True)
        bpy.data.objects['Cube'].select_set(True)
        bpy.context.view_layer.objects.active = panel
        bpy.context.scene.cabinet_aba = 'MODULOS'
        rows = [row for row in addon.gaveta._widgets_gaveta(bpy.context, 564, 1200)
                if row[5] and row[5][0] == 'modo']
        self.assertEqual([row[4] for row in rows], ['Individual', 'Group'])
        self.assertEqual([row[5][1] for row in rows], ['INDIVIDUAL', 'GRUPO'])
        self.assertEqual([row[5][2] for row in rows], [False, True])

    def test_source_folder_labels_produce_english_catalog_paths(self):
        # Foreign input labels are format data, not untranslated interface text.
        root = os.path.join(tempfile.gettempdir(), 'archy_source')
        path = os.path.join(root, 'Cozinha', 'Sup Medios', 'Cantos.dxf')
        levels, _ = addon.importacao.destino_categoria_promob(path, root)
        self.assertEqual(levels, ('Cabinets', 'Kitchen', 'Medium Wall Cabinets', 'Corners'))
        self.assertEqual(addon.importacao.posicao_do_perfil('Sup Medios'), 'BAIXO')


with tempfile.TemporaryDirectory(prefix='archy_english_') as directory:
    with patch.object(addon.biblioteca, 'pasta_biblioteca', return_value=directory), \
         patch.object(addon.opcoes, '_pasta_addon', return_value=directory):
        addon.register()
        try:
            result = unittest.TextTestRunner(verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(TestEnglishInterface))
        finally:
            addon.unregister()
if not result.wasSuccessful():
    raise RuntimeError('English interface regression')
