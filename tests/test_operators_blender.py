"""Run: blender --background --factory-startup --python-exit-code 1 --python tests/test_operators_blender.py

Safety net for previously untested operators and coordinators: post-scale adjacency, Empty scale absorption, cabinet/group/panel thickness, handlers and timers, handles, selection poll and unregister cleanup.

Bugs found here receive expectedFailure with a BUG comment. Once fixed, remove that marker and retain the regression test; the first three were fixed in v126."""
import contextlib
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import bpy
import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon

X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))


def caixa(nome, dims, centro):
    """Create an unmarked box mesh as it would arrive from an external file."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= dims[0]
        v.co.y *= dims[1]
        v.co.z *= dims[2]
    malha = bpy.data.meshes.new(nome)
    bm.to_mesh(malha)
    bm.free()
    obj = bpy.data.objects.new(nome, malha)
    bpy.context.collection.objects.link(obj)
    obj.location = centro
    bpy.context.view_layer.update()
    return obj


def selecionar(*objs):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0] if objs else None


def limites(objs):
    pontos = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    return ([min(p[i] for p in pontos) for i in range(3)],
            [max(p[i] for p in pontos) for i in range(3)])


@contextlib.contextmanager
def ocupado():
    """Simulate the add-on in the middle of a write under its reentrancy guard."""
    antes = addon.chapas._ocupado[0]
    addon.chapas._ocupado[0] = True
    try:
        yield
    finally:
        addon.chapas._ocupado[0] = antes


class TestOperadores(unittest.TestCase):
    def porta_com_agregados(self):
        conj=addon.modulos.criar_armario(bpy.context,'Porta para ocultar',600,1200,550)
        grupo=addon.portas.porta_no_modulo(conj,folhas=2)
        puxadores=addon.puxadores.perfis_na_porta(bpy.context,grupo,'CIMA')
        self.assertTrue(puxadores)
        self.assertTrue(addon.ferragens._ferragens_portas(grupo))
        return conj,grupo,puxadores

    def test_grupo_da_porta_pelo_shift_g_permite_h_nativo_com_todos_agregados(self):
        conj,grupo,puxadores=self.porta_com_agregados()
        selecionar(puxadores[0])
        esperados={o.name for o in [grupo,*grupo.children_recursive]
                   if o.visible_get() and not o.hide_select}
        self.assertEqual(bpy.ops.object.cabinet_selecionar_montagem_porta('EXEC_DEFAULT'),{'FINISHED'})
        self.assertEqual({o.name for o in bpy.context.selected_objects},esperados)
        area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
        regiao=next(r for r in area.regions if r.type=='WINDOW')
        with bpy.context.temp_override(area=area,region=regiao):
            self.assertEqual(bpy.ops.object.hide_view_set(unselected=False),{'FINISHED'})
        self.assertTrue(all(bpy.data.objects[n].hide_get() for n in esperados))
        self.assertFalse(any(o.hide_get() for o in addon.modulos._chapas_do_conjunto(conj)))

    def test_esconder_porta_oculta_rig_e_puxadores_sem_trocar_malhas_ou_afetar_modulo(self):
        conj,grupo,puxadores=self.porta_com_agregados()
        bpy.ops.mesh.primitive_cube_add(location=(3,0,0))
        externo=bpy.context.object
        objetos=[grupo,*grupo.children_recursive]
        malhas={o.name:o.data.as_pointer() for o in objetos if o.type=='MESH'}
        nomes={o.name for o in bpy.data.objects}
        selecionar(addon.portas._folhas_portas(grupo)[0],externo)
        self.assertEqual(bpy.ops.object.cabinet_esconder_porta(),{'FINISHED'})
        self.assertTrue(all(o.hide_get() for o in objetos))
        addon.ferragens._conferir_ferragens()
        self.assertTrue(all(o.hide_get() for o in objetos))
        self.assertEqual({o.name for o in bpy.data.objects},nomes)
        self.assertEqual({o.name:o.data.as_pointer() for o in objetos if o.type=='MESH'},malhas)
        self.assertFalse(externo.hide_get());self.assertTrue(externo.select_get())
        self.assertFalse(any(o.hide_get() for o in addon.modulos._chapas_do_conjunto(conj)))
        area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
        regiao=next(r for r in area.regions if r.type=='WINDOW')
        with bpy.context.temp_override(area=area,region=regiao):
            bpy.ops.object.hide_view_clear(select=False)
        addon.ferragens.ocultar_pecas_do_rig()
        self.assertTrue(all(not f.hide_get() for f in addon.portas._folhas_portas(grupo)))
        self.assertFalse(puxadores[0].hide_get())

    def test_ocultacao_da_porta_respeita_undo_redo_nativo(self):
        conj,grupo,puxadores=self.porta_com_agregados()
        folha=addon.portas._folhas_portas(grupo)[0]
        nome=folha.name;nome_puxador=puxadores[0].name
        selecionar(folha)
        bpy.ops.ed.undo_push(message='Antes de esconder porta')
        bpy.ops.object.cabinet_esconder_porta()
        bpy.ops.ed.undo_push(message='Porta escondida')
        conj=grupo=folha=puxadores=None
        bpy.ops.ed.undo();addon.eventos._fim_do_desfazer()
        self.assertFalse(bpy.data.objects[nome].hide_get())
        self.assertFalse(bpy.data.objects[nome_puxador].hide_get())
        bpy.ops.ed.redo();addon.eventos._fim_do_desfazer()
        self.assertTrue(bpy.data.objects[nome].hide_get())
        self.assertTrue(bpy.data.objects[nome_puxador].hide_get())

    def test_menu_shift_g_preserva_grupos_nativos_e_nao_intercepta_objeto_comum(self):
        conj,grupo,puxadores=self.porta_com_agregados()
        selecionar(puxadores[0])
        self.assertTrue(addon.selecao.OBJECT_OT_selecionar_montagem_porta.poll(bpy.context))
        layout=Mock()
        addon.selecao.VIEW3D_MT_grupo_porta.draw(SimpleNamespace(layout=layout),bpy.context)
        self.assertEqual(layout.operator_context,'EXEC_DEFAULT')
        layout.operator.assert_called_once_with('object.cabinet_selecionar_montagem_porta',icon='OUTLINER_OB_GROUP_INSTANCE')
        layout.operator_menu_enum.assert_called_once_with('object.select_grouped','type',text="Blender Groups")
        if bpy.context.window_manager.keyconfigs.addon is not None:
            self.assertTrue(any(k.idname=='object.cabinet_selecionar_montagem_porta' and k.type=='G' and k.shift
                for m,k in addon.selecao._keymaps))
        selecionar(conj)
        self.assertFalse(addon.selecao.OBJECT_OT_selecionar_montagem_porta.poll(bpy.context))
        self.assertFalse(addon.selecao.OBJECT_OT_esconder_porta.poll(bpy.context))

    def test_ocultar_ignora_descendente_fora_da_view_layer(self):
        conj,grupo,puxadores=self.porta_com_agregados()
        fora=bpy.data.objects.new('Agregado de outra camada',None);fora.parent=grupo
        selecionar(addon.portas._folhas_portas(grupo)[0])
        self.assertNotIn(fora,addon.selecao.montagem_da_porta(bpy.context))
        self.assertEqual(bpy.ops.object.cabinet_esconder_porta(),{'FINISHED'})

    def test_tab_reduz_altura_sem_refazer_puxadores_editados(self):
        # Regression v357: rebuilding the profile after G canceled native translation
        # and separated the handle from the cutout wood.
        conj = addon.modulos.criar_armario(bpy.context, 'Altura pelo Tab', 600, 2400, 550)
        grupo = addon.portas.porta_no_modulo(conj)
        puxadores = addon.puxadores.perfis_na_porta(bpy.context, grupo, 'CIMA')
        self.assertTrue(puxadores)
        selecionar(conj)
        bpy.ops.object.cabinet_editar_grupo()
        for obj in bpy.context.objects_in_mode_unique_data:
            bm = bmesh.from_edit_mesh(obj.data)
            for v in bm.verts:
                v.select_set((obj.matrix_world @ v.co).z > 1.2)
            bmesh.update_edit_mesh(obj.data)
        bpy.ops.transform.translate(value=(0, 0, -.3))
        bpy.ops.object.cabinet_editar_grupo()
        bpy.context.view_layer.update()
        confirmados = {p.name: (p.data, [p.matrix_world @ v.co for v in p.data.vertices],
                              [tuple(f.vertices) for f in p.data.polygons]) for p in puxadores}
        with patch.object(addon.puxadores, 'gerar_malha_puxador',
                          side_effect=AssertionError('Tab reconstroi puxador')) as gerar:
            for _ in range(2):
                addon.eventos.verificar_periodicamente()
            gerar.assert_not_called()
        bpy.context.view_layer.update()
        for pux in puxadores:
            malha, pontos, faces = confirmados[pux.name]
            self.assertIs(pux.data, malha)
            self.assertEqual([tuple(f.vertices) for f in malha.polygons], faces)
            for v, esperado in zip(malha.vertices, pontos):
                self.assertPerto(pux.matrix_world @ v.co, esperado)
            contorno = [float(c) for p in addon.arame._contorno_malha(malha) for c in p]
            self.assertEqual(list(pux['puxador_contorno']), contorno)
        self.assertAlmostEqual(addon.modulos.medir_conjunto(conj)[1], 2100, places=3)

    def test_tab_atualiza_ferragens_em_lote_sem_avaliar_por_dobradica(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Rigs em lote', 600, 2400, 550)
        grupo = addon.portas.porta_no_modulo(conj)
        raizes = [o for o in grupo.children_recursive if o.get('cabinet_peca') == 'raiz']
        self.assertGreater(len(raizes), 2)
        malhas = [o for r in raizes for o in r.children_recursive
                  if o.type == 'MESH' and not o.hide_render]
        for obj in malhas:
            if obj.data.users > 1:
                obj.data = obj.data.copy()
        bpy.context.view_layer.update()
        antes = {r.name: r.matrix_world.translation.copy() for r in raizes}
        registros = addon.ferragens.iniciar_edicao_rigs(malhas)
        delta = Vector((0, 0, -.05))
        for obj in malhas:
            local = obj.matrix_world.inverted_safe().to_3x3() @ delta
            obj.data.transform(Matrix.Translation(local))
            obj.data.update()
        atualizar = Mock(wraps=bpy.context.view_layer.update)
        contexto = SimpleNamespace(mode='OBJECT', view_layer=SimpleNamespace(update=atualizar))
        with patch.object(addon.ferragens, 'bpy', SimpleNamespace(context=contexto, data=bpy.data)):
            addon.ferragens.concluir_edicao_rigs(registros)
        self.assertLessEqual(atualizar.call_count, 2)
        for raiz in raizes:
            self.assertPerto(raiz.matrix_world.translation, antes[raiz.name] + delta)

    def test_tab_materializa_espelho_da_dobradica_antes_do_arraste_nativo(self):
        # Regression v344: Mirror/Clipping kept the virtual half at its old location.
        # This test moves using native transform while still in Edit Mode.
        conj = addon.modulos.criar_armario(bpy.context, 'Espelho editavel', 600, 800, 550)
        grupo = addon.portas.porta_no_modulo(conj)
        raiz = next(o for o in grupo.children_recursive if o.get('cabinet_peca') == 'raiz')
        base = next(o for o in raiz.children_recursive if o.get('cabinet_peca') == 'base')
        espelho = base.modifiers.new('Espelho antigo', 'MIRROR')
        espelho.use_axis = (False, False, True)
        espelho.use_clip = True
        outra = base.copy()
        bpy.context.scene.collection.objects.link(outra)
        outra.parent = None
        original = outra.data
        bpy.context.view_layer.update()
        avaliada = base.evaluated_get(bpy.context.evaluated_depsgraph_get())
        malha = avaliada.to_mesh()
        try:
            pontos = [v.co.copy() for v in malha.vertices]
        finally:
            avaliada.to_mesh_clear()
        selecionar(conj)
        bpy.ops.object.cabinet_editar_grupo()
        self.assertFalse([m for m in base.modifiers if m.type == 'MIRROR'])
        self.assertIs(outra.data, original)
        self.assertTrue([m for m in outra.modifiers if m.type == 'MIRROR'])
        base.update_from_editmode()
        bpy.context.view_layer.update()
        avaliada = base.evaluated_get(bpy.context.evaluated_depsgraph_get())
        malha = avaliada.to_mesh()
        try:
            self.assertEqual(len(malha.vertices), len(pontos))
            for atual, esperado in zip(malha.vertices, pontos):
                self.assertLess((atual.co - esperado).length, .000001)
        finally:
            avaliada.to_mesh_clear()
        bpy.ops.mesh.select_all(action='DESELECT')
        bm = bmesh.from_edit_mesh(base.data)
        antes = [v.co.copy() for v in bm.verts]
        for v in bm.verts:
            v.select_set(True)
        bmesh.update_edit_mesh(base.data)
        local = base.matrix_world.inverted_safe().to_3x3() @ Vector((0, 0, .035))
        bpy.ops.transform.translate(value=(0, 0, .035))
        for v, ponto in zip(bm.verts, antes):
            self.assertLess((v.co - ponto - local).length, .000001)
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual(bpy.context.object, conj)
        self.assertNotIn('cabinet_rig_edicao', base.data)

    def test_uv_metrica_acompanha_face_estendida_pelo_transformador_nativo(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Textura proporcional', 600, 800, 550)
        chapa = next(o for o in addon.modulos._chapas_do_conjunto(conj)
                     if all(abs(a) < .01 for a in o.rotation_euler))
        selecionar(conj)
        bpy.ops.object.cabinet_editar_grupo()
        self.assertTrue(bpy.context.scene.tool_settings.use_transform_correct_face_attributes)
        bm = bmesh.from_edit_mesh(chapa.data)
        uv = bm.loops.layers.uv.active
        self.assertIsNotNone(uv)
        bpy.ops.mesh.select_all(action='DESELECT')
        for v in bm.verts:
            v.select_set(v.co.x > 0)
        bmesh.update_edit_mesh(chapa.data)
        mundo = chapa.matrix_world.to_3x3() @ Vector((.1, 0, 0))
        bpy.ops.transform.translate(value=mundo)
        for face in bm.faces:
            for loop in face.loops:
                proximo = loop.link_loop_next
                real = (proximo.vert.co - loop.vert.co).length
                textura = (proximo[uv].uv - loop[uv].uv).length
                self.assertAlmostEqual(textura / real, 1, places=4)
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual(len(chapa.data.uv_layers), 1)

    def test_uv_personalizada_conserva_rotacao_e_densidade_ao_editar(self):
        conj = addon.modulos.criar_armario(bpy.context, 'UV personalizada', 600, 800, 550)
        chapa = next(o for o in addon.modulos._chapas_do_conjunto(conj)
                     if all(abs(a) < .01 for a in o.rotation_euler))
        addon.chapas.preparar_uvs_chapa(chapa)
        uv = chapa.data.uv_layers.active
        for loop in uv.data:
            u, v = loop.uv
            loop.uv = (2 - v * 3, 4 + u * 3)
        antes = [tuple(l.uv) for l in uv.data]
        self.assertFalse(addon.chapas.preparar_uvs_chapa(chapa))
        self.assertEqual(antes, [tuple(l.uv) for l in uv.data])
        selecionar(conj)
        bpy.ops.object.cabinet_editar_grupo()
        bpy.ops.mesh.select_all(action='DESELECT')
        bm = bmesh.from_edit_mesh(chapa.data)
        camada = bm.loops.layers.uv.active
        for v in bm.verts:
            v.select_set(v.co.x > 0)
        bmesh.update_edit_mesh(chapa.data)
        mundo = chapa.matrix_world.to_3x3() @ Vector((.1, 0, 0))
        bpy.ops.transform.translate(value=mundo)
        for face in bm.faces:
            for loop in face.loops:
                proximo = loop.link_loop_next
                real = (proximo.vert.co - loop.vert.co).length
                textura = (proximo[camada].uv - loop[camada].uv).length
                self.assertAlmostEqual(textura / real, 3, places=3)
        bpy.ops.object.cabinet_editar_grupo()

    def test_tab_move_dobradica_inteira_com_rig_furo_e_curva(self):
        # Regression v343: moving vertices left rigs, holes and springs at their old
        # positions, distorting the hinge when opening the door.
        conj = addon.modulos.criar_armario(bpy.context, 'Dobradicas editaveis', 600, 1800, 550)
        conj.rotation_euler.z = .7
        grupo = addon.portas.porta_no_modulo(conj)
        raiz = next(o for o in grupo.children_recursive if o.get('cabinet_peca') == 'raiz')
        fixa = next(o for o in grupo.children_recursive
                    if o.get('cabinet_peca') == 'raiz' and o != raiz)
        # Tab materializes Mirror: rigid transport compares the editable mesh without
        # depending on a prior test leaving an already-expanded copy in cache.
        addon.ferragens.preparar_malhas_para_editar(bpy.context,
            [o for o in grupo.children_recursive if o.type == 'MESH'])
        bpy.context.view_layer.update()
        partes = list(raiz.children_recursive)
        mundos = {o.name: o.matrix_world.copy() for o in [raiz, fixa, *partes]}
        malhas = {o.name: (o.data, [v.co.copy() for v in o.data.vertices])
                  for o in partes if o.type == 'MESH' and not o.hide_render}
        selecionar(conj)
        bpy.ops.object.cabinet_editar_grupo()
        self.assertFalse(addon._segura_dado(addon.selecao._edicao_grupo[0]))
        delta = Vector((0, 0, .035))
        for obj in bpy.context.objects_in_mode:
            bm = bmesh.from_edit_mesh(obj.data)
            mover = obj.name in malhas
            local = obj.matrix_world.inverted_safe().to_3x3() @ delta
            for v in bm.verts:
                v.select_set(mover)
                if mover:
                    v.co += local
            bmesh.update_edit_mesh(obj.data)
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual(bpy.context.object, conj)
        self.assertTrue(conj.select_get())
        for obj in [raiz, *partes]:
            self.assertPerto(obj.matrix_world.translation, mundos[obj.name].translation + delta)
        self.assertPerto(fixa.matrix_world.translation, mundos[fixa.name].translation)
        for nome, (_anterior, pontos) in malhas.items():
            obj = bpy.data.objects[nome]
            for v, ponto in zip(obj.data.vertices, pontos):
                self.assertLess((v.co - ponto).length, .000001)
        # Reapplying parameters and opening/closing preserves edits and holes.
        addon.ferragens._refazer_ferragens(grupo)
        folha = addon.portas._folhas_portas(grupo)[0]
        addon.ferragens._definir_abertura(bpy.context, folha, .5)
        addon.ferragens._definir_abertura(bpy.context, folha, 0)
        bpy.context.view_layer.update()
        for obj in [raiz, *partes]:
            self.assertPerto(obj.matrix_world.translation, mundos[obj.name].translation + delta)
        # Another Tab with no movement must not reapply the previous displacement.
        bpy.ops.object.cabinet_editar_grupo()
        bpy.ops.object.cabinet_editar_grupo()
        self.assertPerto(raiz.matrix_world.translation, mundos[raiz.name].translation + delta)

    def test_tab_de_peca_inteira_move_rig_mas_modelagem_parcial_fica_nativa(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Modelagem da ferragem', 600, 800, 550)
        grupo = addon.portas.porta_no_modulo(conj)
        raiz = next(o for o in grupo.children_recursive if o.get('cabinet_peca') == 'raiz')
        base = next(o for o in raiz.children_recursive if o.get('cabinet_peca') == 'base')
        if base.data.users > 1:
            base.data = base.data.copy()
        malha = base.data
        antes = raiz.matrix_world.copy()
        registros = addon.ferragens.iniciar_edicao_rigs([base])
        original = base.data.vertices[0].co.copy()
        base.data.vertices[0].co.z += .003
        base.data.update()
        addon.ferragens.concluir_edicao_rigs(registros)
        self.assertEqual(raiz.matrix_world, antes)
        self.assertAlmostEqual(base.data.vertices[0].co.z, original.z + .003, places=6)
        registros = addon.ferragens.iniciar_edicao_rigs([base])
        local = Vector((0, 0, .025))
        base.data.transform(Matrix.Translation(local))
        delta = base.matrix_world.to_3x3() @ local
        addon.ferragens.concluir_edicao_rigs(registros)
        self.assertPerto(raiz.matrix_world.translation, antes.translation + delta)
        self.assertIs(base.data, malha)
        self.assertAlmostEqual(base.data.vertices[0].co.z, original.z + .003, places=6)

    def test_tab_cancelado_e_ferragem_removida_nao_movem_rig(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Cancelar ferragem', 600, 800, 550)
        grupo = addon.portas.porta_no_modulo(conj)
        raiz = next(o for o in grupo.children_recursive if o.get('cabinet_peca') == 'raiz')
        base = next(o for o in raiz.children_recursive if o.get('cabinet_peca') == 'base')
        antes = raiz.matrix_world.copy()
        registros = addon.ferragens.iniciar_edicao_rigs([base])
        addon.ferragens.concluir_edicao_rigs(registros)
        self.assertEqual(raiz.matrix_world, antes)
        bpy.data.objects.remove(base, do_unlink=True)
        addon.ferragens.concluir_edicao_rigs(registros)
        self.assertEqual(raiz.matrix_world, antes)

    def test_trocar_versao_do_rig_preserva_deslocamento_manual(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Ferragem antiga editada', 600, 800, 550)
        grupo = addon.portas.porta_no_modulo(conj)
        raiz = next(o for o in grupo.children_recursive if o.get('cabinet_peca') == 'raiz')
        base = next(o for o in raiz.children_recursive if o.get('cabinet_peca') == 'base')
        if base.data.users > 1:
            base.data = base.data.copy()
        registros = addon.ferragens.iniciar_edicao_rigs([base])
        delta = Vector((0, .035, 0))
        local = base.matrix_world.inverted_safe().to_3x3() @ (grupo.matrix_world.to_3x3() @ delta)
        base.data.transform(Matrix.Translation(local))
        addon.ferragens.concluir_edicao_rigs(registros)
        identidade = raiz[addon.ferragens.CHAVE_ID_FERRAGEM]
        pose = raiz.matrix_basis.copy()
        raiz['cabinet_versao'] = int(addon.ferragens._dados_dobradica_reta()['versao']) - 1
        addon.ferragens._refazer_ferragens(grupo)
        atual = next(o for o in grupo.children_recursive
                     if o.get(addon.ferragens.CHAVE_ID_FERRAGEM) == identidade)
        self.assertPerto(atual.matrix_basis.translation, pose.translation)
        self.assertPerto(atual['porta_ferragem_deslocamento_mm'], delta * 1000)

    def test_undo_refaz_tab_da_dobradica_sem_perder_montagem_ou_grupo(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Undo da ferragem', 600, 800, 550)
        grupo = addon.portas.porta_no_modulo(conj)
        raiz = next(o for o in grupo.children_recursive if o.get('cabinet_peca') == 'raiz')
        base = next(o for o in raiz.children_recursive if o.get('cabinet_peca') == 'base')
        nome, nome_raiz, nome_base = conj.name, raiz.name, base.name
        origem = raiz.matrix_world.translation.copy()
        selecionar(conj)
        bpy.ops.ed.undo_push(message='Antes da ferragem')
        bpy.ops.object.cabinet_editar_grupo()
        local = base.matrix_world.inverted_safe().to_3x3() @ Vector((0, 0, .03))
        bm = bmesh.from_edit_mesh(base.data)
        for v in bm.verts:
            v.co += local
        bmesh.update_edit_mesh(base.data)
        bpy.ops.ed.undo_push(message='Moveu ferragem')
        bpy.ops.object.cabinet_editar_grupo()
        bpy.ops.ed.undo_push(message='Saiu da ferragem')
        bpy.ops.ed.undo()
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        self.assertTrue(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        addon.eventos.verificar_periodicamente()
        self.assertEqual(bpy.context.object.name, nome)
        self.assertPerto(bpy.data.objects[nome_raiz].matrix_world.translation, origem + Vector((0, 0, .03)))
        bpy.ops.ed.undo()
        self.assertTrue(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
        addon.eventos._fim_do_desfazer()
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual(bpy.context.object.name, nome)
        self.assertPerto(bpy.data.objects[nome_raiz].matrix_world.translation, origem + Vector((0, 0, .03)))
        base = bpy.data.objects[nome_base]
        self.assertNotIn('porta_ferragem_deslocamento_mm', base)

    def test_instancia_nao_altera_mesh_que_outra_instancia_esta_editando(self):
        from unittest.mock import patch
        o=addon.chapas.nova_chapa('Malha compartilhada em edicao',400,300,18,(0,0,0),(0,0,0),bpy.context)
        clone=o.copy();clone.data=o.data;bpy.context.scene.collection.objects.link(clone)
        selecionar(o);bpy.ops.object.mode_set(mode='EDIT')
        try:
            self.assertEqual(clone.mode,'OBJECT');self.assertTrue(clone.data.is_editmode)
            with patch.object(addon.chapas.bmesh,'new',side_effect=AssertionError('Substituiu Mesh em edicao')):
                addon.chapas.gerar_malha_chapa(clone)
                self.assertFalse(addon.chapas.absorver_malha_editada(clone))
                clone.scale.x=2.
                self.assertEqual(addon.chapas.normalizar_chapas([clone]),[])
                self.assertEqual(clone.scale.x,2.)
        finally:bpy.ops.object.mode_set(mode='OBJECT')

    def test_absorver_chanfro_modelado_nao_reconstroi_malha_do_undo(self):
        from unittest.mock import patch
        o=addon.chapas.nova_chapa('Chapa com chanfro nativo',400,300,18,(0,0,.2),(0,90,0),bpy.context)
        bm=bmesh.new()
        try:
            bm.from_mesh(o.data)
            e=max((e for e in bm.edges if abs((e.verts[1].co-e.verts[0].co).normalized().z)>.99),key=lambda e:sum(v.co.x+v.co.y for v in e.verts))
            bmesh.ops.bevel(bm,geom=[e],offset=.08,segments=1,affect='EDGES')
            for v in bm.verts:
                if v.co.x>.1 and v.co.y>.05:v.co.z+=.08
            bm.to_mesh(o.data)
        finally:bm.free()
        o.data.update();me=o.data
        uv=me.uv_layers.new(name='UV do chanfro')
        for i,v in enumerate(uv.data):v.uv=(i/50,i/70)
        pintura=bpy.data.materials.new('Pintura do chanfro');me.materials.append(pintura)
        antes=[o.matrix_world@v.co for v in me.vertices]
        faces=[tuple(f.vertices) for f in me.polygons];uvs=[tuple(v.uv) for v in uv.data]
        with patch.object(addon.chapas,'gerar_malha_chapa',side_effect=AssertionError('Reconstruiu malha manual')):
            self.assertTrue(addon.chapas.absorver_malha_editada(o))
        self.assertIs(o.data,me);self.assertNotIn('chapa_edicao',o)
        self.assertEqual(faces,[tuple(f.vertices) for f in me.polygons])
        self.assertEqual(uvs,[tuple(v.uv) for v in me.uv_layers['UV do chanfro'].data])
        self.assertIs(me.materials[0],pintura)
        self.assertLess(max((p-o.matrix_world@v.co).length for p,v in zip(antes,me.vertices)),1e-6)

    def test_timer_nao_consulta_cena_enquanto_undo_esta_restaurando(self):
        from unittest.mock import patch
        addon.eventos._desfazendo[0]=True
        try:
            with patch.object(addon.eventos,'sincronizar_contornos',side_effect=AssertionError('Leu selecao durante undo')):
                self.assertEqual(addon.eventos.verificar_periodicamente(),addon.eventos.INTERVALO_TIMER)
        finally:addon.eventos._desfazendo[0]=False

    def test_fecho_do_undo_nao_escreve_malhas_e_descarta_transicao_antiga(self):
        from unittest.mock import patch
        addon.chapas._chapas_em_edicao.add('Chapa anterior ao undo');addon.chapas._havia_modal[0]=True
        addon.eventos._antes_de_desfazer()
        self.assertFalse(addon.chapas._chapas_em_edicao);self.assertFalse(addon.chapas._havia_modal[0])
        with patch.object(addon.frentes,'preparar_cena',side_effect=AssertionError('Escreveu Mesh no fecho do undo')),patch.object(addon.eventos,'sincronizar_contornos'):
            addon.eventos._fim_do_desfazer()
        self.assertFalse(addon.eventos._desfazendo[0]);self.assertTrue(addon.frentes._cena_pendente[0])

    def test_chanfrar_mover_tab_undo_redo_conserva_topologia_e_copia_nativa(self):
        conj=addon.modulos.criar_armario(bpy.context,'Regressao do chanfro undo',600,400,300)
        o=next(o for o in conj.children if "Right" in o.name);nome=o.name
        selecionar(o);bpy.ops.ed.undo_push(message='Antes do chanfro')
        bpy.ops.object.mode_set(mode='EDIT');addon.chapas.absorver_edicoes_de_malha()
        bpy.ops.mesh.select_all(action='DESELECT');bpy.ops.mesh.select_mode(type='EDGE')
        bm=bmesh.from_edit_mesh(o.data)
        e=max((e for e in bm.edges if abs((e.verts[1].co-e.verts[0].co).normalized().z)>.99),key=lambda e:sum(v.co.x+v.co.y for v in e.verts))
        e.select_set(True);bmesh.update_edit_mesh(o.data)
        bpy.ops.mesh.bevel(offset=.08,segments=1,affect='EDGES')
        bpy.ops.ed.undo_push(message='Chanfrou')
        bpy.ops.transform.translate(value=(-.08,0,0));bpy.ops.ed.undo_push(message='Moveu a quina')
        bpy.ops.object.mode_set(mode='OBJECT');bpy.ops.ed.undo_push(message='Tab antes do timer')
        addon.chapas.absorver_edicoes_de_malha();addon.frentes.processar_pendentes()
        self.assertEqual(len(o.data.vertices),10)
        faces=[tuple(f.vertices) for f in o.data.polygons]
        bm=e=o=conj=None
        for _ in range(4):
            bpy.ops.ed.undo();bpy.context.view_layer.update()
            self.assertEqual(bpy.context.mode,'EDIT_MESH')
            addon.eventos._fim_do_desfazer();addon.eventos.verificar_periodicamente()
            bpy.ops.ed.redo();bpy.context.view_layer.update()
            self.assertEqual(bpy.context.mode,'OBJECT')
            addon.eventos._fim_do_desfazer();addon.eventos.verificar_periodicamente()
            self.assertEqual(faces,[tuple(f.vertices) for f in bpy.data.objects[nome].data.polygons])
            o=bpy.data.objects[nome]
            reais=[(max(v.co[i] for v in o.data.vertices)-min(v.co[i] for v in o.data.vertices))*1000 for i in range(2)]
            reais.append(addon.chapas._secao_espessura(o.data)['espessura_mm'])
            for real,prop in zip(reais,('chapa_largura_mm','chapa_comprimento_mm','chapa_espessura_mm')):
                self.assertAlmostEqual(real,getattr(o,prop),places=3)
            o=None
            copia=bpy.data.objects[nome].data.copy()
            self.assertEqual(len(copia.vertices),10);bpy.data.meshes.remove(copia)

    def test_dobra_chanfrada_mede_pele_e_resize_preserva_linha_media(self):
        o=addon.chapas.nova_chapa('Dobra com espessura fisica',400,300,18,(0,0,0),(0,90,0),bpy.context)
        bm=bmesh.new()
        try:
            bm.from_mesh(o.data)
            e=max((e for e in bm.edges if abs((e.verts[1].co-e.verts[0].co).normalized().z)>.99),key=lambda e:sum(v.co.x+v.co.y for v in e.verts))
            bmesh.ops.bevel(bm,geom=[e],offset=.08,segments=1,affect='EDGES')
            for v in bm.verts:
                if v.co.x>.1 and v.co.y>.05:v.co.z+=.12
            bm.to_mesh(o.data)
        finally:bm.free()
        o.data.update();me=o.data
        mundo=[o.matrix_world@v.co for v in me.vertices]
        addon.chapas.absorver_malha_editada(o)
        self.assertAlmostEqual(o.chapa_espessura_mm,18,places=4)
        self.assertGreater((max(v.co.z for v in me.vertices)-min(v.co.z for v in me.vertices))*1000,130)
        # Old file already recentered, with a property contaminated by the AABB.
        with ocupado():o.chapa_espessura_mm=(max(v.co.z for v in me.vertices)-min(v.co.z for v in me.vertices))*1000
        self.assertTrue(addon.chapas.absorver_malha_editada(o))
        self.assertAlmostEqual(o.chapa_espessura_mm,18,places=4)
        self.assertLess(max((p-o.matrix_world@v.co).length for p,v in zip(mundo,me.vertices)),1e-6)
        original=[v.co.copy() for v in me.vertices]
        o.chapa_largura_mm=500
        self.assertEqual([v.co.z for v in me.vertices],[p.z for p in original])
        o.chapa_largura_mm=400
        for v,p in zip(me.vertices,original):self.assertLess((v.co-p).length,1e-6)
        o.chapa_espessura_mm=25
        self.assertAlmostEqual(addon.chapas._espessura_da_malha(o),25,places=4)
        secao=addon.chapas._secao_espessura(me)
        for a,b in secao['pares']:
            par=[p for p in original if abs(p.x-a[0])<1e-6 and abs(p.y-a[1])<1e-6]
            self.assertEqual(len(par),2)
            self.assertAlmostEqual((a[2]+b[2])/2,sum(p.z for p in par)/2,places=6)
        self.assertIs(o.data,me)

    def test_secao_ambigua_nao_inventa_espessura_pelo_envelope(self):
        o=addon.chapas.nova_chapa('Secao irregular',400,300,18,(0,0,0),(0,0,0),bpy.context)
        o.data.vertices[0].co.z-=.12;o.data.update()
        addon.chapas.absorver_malha_editada(o)
        self.assertAlmostEqual(o.chapa_espessura_mm,18,places=4)

    def test_undo_do_tab_recupera_grupo_sem_referencias_a_objetos_antigos(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Tab desfazer', 600, 700, 550)
        nome = conj.name
        selecionar(conj)
        bpy.ops.ed.undo_push(message='Antes de Tab')
        bpy.ops.object.cabinet_editar_grupo()
        obj = bpy.context.object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.verts[0].co.x += .005
        bmesh.update_edit_mesh(obj.data)
        bpy.ops.ed.undo_push(message='Editou grupo')
        bpy.ops.object.cabinet_editar_grupo()
        bpy.ops.ed.undo_push(message='Saiu de Tab')
        bpy.ops.ed.undo()
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        self.assertTrue(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
        bpy.ops.ed.redo()
        self.assertEqual(bpy.context.mode, 'OBJECT')
        bpy.ops.ed.undo()
        self.assertTrue(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
        bpy.ops.object.cabinet_editar_grupo()
        conj = bpy.data.objects[nome]
        self.assertEqual(bpy.context.object, conj)
        self.assertEqual([(o, m) for o, m, _ in addon.hud._itens_da_selecao(bpy.context)], [(conj, 'GRUPO')])

    def test_tab_restaura_selecao_do_modulo_e_hud_unica(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Tab inteiro', 600, 700, 550)
        selecionar(conj)
        bpy.context.view_layer.objects.active = None
        antes = limites(addon.modulos._chapas_do_conjunto(conj))
        for _ in range(3):
            bpy.ops.object.cabinet_editar_grupo()
            self.assertEqual(bpy.context.mode, 'EDIT_MESH')
            self.assertTrue(conj.select_get())
            self.assertTrue(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
            bpy.ops.object.cabinet_editar_grupo()
            addon.eventos.verificar_periodicamente()
            self.assertEqual(set(bpy.context.selected_objects), {conj})
            self.assertEqual(bpy.context.object, conj)
            itens = addon.hud._itens_da_selecao(bpy.context)
            self.assertEqual([(o, modo) for o, modo, _ in itens], [(conj, 'GRUPO')])
        self.assertEqual(antes, limites(addon.modulos._chapas_do_conjunto(conj)))

    def test_saida_nativa_do_edit_mode_conserva_grupos_e_nova_selecao(self):
        a = addon.modulos.criar_armario(bpy.context, 'Tab A', 600, 700, 550)
        b = addon.modulos.criar_armario(bpy.context, 'Tab B', 600, 700, 550)
        selecionar(a, b)
        bpy.ops.object.cabinet_editar_grupo()
        bpy.ops.object.mode_set(mode='OBJECT')
        addon.eventos.verificar_periodicamente()
        self.assertEqual(set(bpy.context.selected_objects), {a, b})
        self.assertEqual(bpy.context.object, a)
        bpy.ops.object.cabinet_editar_grupo()
        bpy.ops.object.mode_set(mode='OBJECT')
        peca = addon.modulos._chapas_do_conjunto(b)[0]
        selecionar(peca)
        addon.eventos.verificar_periodicamente()
        self.assertEqual(set(bpy.context.selected_objects), {peca})
        self.assertEqual(bpy.context.object, peca)

    def _gavetas_para_tab(self):
        conj=addon.modulos.criar_armario(bpy.context,'Tab das gavetas',800,900,560)
        grupo=addon.gavetas.criar_gavetas(bpy.context,conj,(18,18,18,18,0),
                                        dict(quantidade=3,profundidade_mm=560))
        return conj,grupo,addon.gavetas.gavetas_do_grupo(grupo)

    # Regression, fixed in v383: the unit Empty was not an editable group.
    def test_tab_da_gaveta_individual_abre_caixa_e_puxador_sem_as_vizinhas(self):
        conj,grupo,gavetas=self._gavetas_para_tab()
        alvo=gavetas[1]
        addon.gavetas.selecionar(bpy.context,addon.gavetas.frente_da_gaveta(alvo),'GAVETA')
        selecionados=set(bpy.context.selected_objects)
        esperados={o for o in alvo.children_recursive if o.type=='MESH'}
        self.assertTrue(any(addon.chapas.MARCA_PUXADOR in o for o in esperados))
        malhas={o.name:o.data for o in esperados}
        for _ in range(3):
            self.assertTrue(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
            self.assertEqual(bpy.ops.object.cabinet_editar_grupo(),{'FINISHED'})
            self.assertEqual(bpy.context.mode,'EDIT_MESH')
            self.assertEqual(set(bpy.context.objects_in_mode),esperados)
            self.assertTrue(alvo.select_get())
            self.assertEqual(bpy.ops.object.cabinet_editar_grupo(),{'FINISHED'})
            self.assertEqual(set(bpy.context.selected_objects),selecionados)
            self.assertIs(bpy.context.object,alvo)
        self.assertTrue(all(o.data==malhas[o.name] for o in esperados))

    def test_tab_de_duas_gavetas_conserva_escopo_e_isola_malha_compartilhada(self):
        conj,grupo,gavetas=self._gavetas_para_tab()
        a,c=gavetas[0],gavetas[2]
        addon.gavetas.selecionar(bpy.context,a,'GAVETA')
        addon.gavetas.selecionar(bpy.context,c,'GAVETA',somar=True)
        selecionados=set(bpy.context.selected_objects)
        frente=addon.gavetas.frente_da_gaveta(a)
        externo=frente.copy();bpy.context.scene.collection.objects.link(externo)
        externo.parent=None;externo.select_set(False)
        originais=[v.co.copy() for v in externo.data.vertices]
        esperados={o for g in (a,c) for o in g.children_recursive if o.type=='MESH'}
        self.assertTrue(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual(set(bpy.context.objects_in_mode),esperados)
        bm=bmesh.from_edit_mesh(frente.data)
        for v in bm.verts:v.co.z+=.01
        bmesh.update_edit_mesh(frente.data)
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual(set(bpy.context.selected_objects),selecionados)
        self.assertIs(bpy.context.object,c)
        self.assertNotEqual(externo.data,frente.data)
        for v,co in zip(externo.data.vertices,originais):self.assertLess((v.co-co).length,1e-7)

    def test_undo_redo_do_tab_da_gaveta_restaura_escopo_individual(self):
        conj,grupo,gavetas=self._gavetas_para_tab()
        alvo=gavetas[1];nome=alvo.name
        addon.gavetas.selecionar(bpy.context,alvo,'GAVETA')
        selecionados={o.name for o in bpy.context.selected_objects}
        bpy.ops.ed.undo_push(message='Gaveta selecionada')
        self.assertTrue(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
        bpy.ops.object.cabinet_editar_grupo()
        bm=bmesh.from_edit_mesh(bpy.context.object.data)
        for v in bm.verts:v.co.x+=.002
        bmesh.update_edit_mesh(bpy.context.object.data)
        bpy.ops.ed.undo_push(message='Gaveta editada')
        bpy.ops.object.cabinet_editar_grupo()
        bpy.ops.ed.undo_push(message='Gaveta fora de edicao')
        conj=grupo=gavetas=alvo=bm=v=None
        bpy.ops.ed.undo()
        self.assertEqual(bpy.context.mode,'EDIT_MESH')
        self.assertTrue(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
        bpy.ops.ed.redo()
        self.assertEqual(bpy.context.mode,'OBJECT')
        bpy.ops.ed.undo()
        self.assertTrue(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
        bpy.ops.object.cabinet_editar_grupo()
        self.assertEqual({o.name for o in bpy.context.selected_objects},selecionados)
        self.assertEqual(bpy.context.object.name,nome)
        self.assertFalse(addon._segura_dado(addon.selecao._edicao_grupo[0]))

    def test_tab_do_grupo_entra_no_edit_mode_nativo_das_malhas(self):
        conj=addon.modulos.criar_armario(bpy.context,"Edit",600,700,550)
        addon.portas.porta_no_modulo(conj)
        for o in bpy.context.selected_objects:o.select_set(False)
        conj.select_set(True);bpy.context.view_layer.objects.active=conj
        alvos=addon.selecao.malhas_para_editar(bpy.context)
        self.assertTrue(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
        self.assertIn('FINISHED',bpy.ops.object.cabinet_editar_grupo())
        self.assertEqual(bpy.context.mode,'EDIT_MESH')
        self.assertEqual(set(bpy.context.objects_in_mode),set(alvos))
        bpy.ops.object.mode_set(mode='OBJECT')

    def test_tab_de_peca_fica_nativo_e_malhas_compartilhadas_ficam_isoladas(self):
        conj=addon.modulos.criar_armario(bpy.context,'Unico',600,700,550)
        obj=addon.modulos._chapas_do_conjunto(conj)[0]
        outro=obj.copy();bpy.context.scene.collection.objects.link(outro)
        selecionar(obj)
        self.assertFalse(addon.selecao.OBJECT_OT_editar_grupo.poll(bpy.context))
        selecionar(conj)
        bpy.ops.object.cabinet_editar_grupo()
        bpy.ops.object.mode_set(mode='OBJECT')
        self.assertNotEqual(outro.data,obj.data)

    def test_antiga_chapa_integrada_nao_puxa_carcaca_por_adjacencia(self):
        c=addon.chapas.nova_chapa('Lateral',600,400,18,(0,0,0),(0,0,0),bpy.context)
        n=addon.chapas.nova_chapa('Prateleira integrada',500,400,18,(1000,0,0),(0,0,0),bpy.context)
        pai=bpy.data.objects.new('Sistema',None);bpy.context.scene.collection.objects.link(pai)
        n.parent=pai;n['eh_prateleira']=1
        c['adj_x_pos']=n.name;c['adj_x_pos_uid']=addon.chapas._garantir_uid(n)
        antes=c.chapa_largura_mm
        addon.chapas.aplicar_adjacencia([c])
        self.assertEqual(c.chapa_largura_mm,antes)

    def test_malha_modelada_retorna_apos_vertices_cruzarem_o_meio(self):
        contorno=[(-.5,-.5),(.5,-.5),(.5,-.2),(.1,-.2),(.1,.5),(-.5,.5)]
        vs=[(x,y,z) for z in (-.009,.009) for x,y in contorno]
        fs=[tuple(range(5,-1,-1)),tuple(range(6,12))]+[(i,(i+1)%6,(i+1)%6+6,i+6) for i in range(6)]
        m=bpy.data.meshes.new("Cutout");m.from_pydata(vs,[],fs)
        o=bpy.data.objects.new("Cutout",m);bpy.context.scene.collection.objects.link(o)
        o[addon.chapas.MARCA_CHAPA]=1
        with ocupado():o.chapa_largura_mm=1000;o.chapa_comprimento_mm=1000;o.chapa_espessura_mm=18
        faces=[tuple(f.vertices) for f in m.polygons]
        for _ in range(3):
            o.chapa_largura_mm=100
            o.chapa_largura_mm=1000
            for v,co in zip(m.vertices,vs):self.assertLess((v.co-Vector(co)).length,1e-6)
            self.assertEqual([tuple(f.vertices) for f in m.polygons],faces)

    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.context.scene.cabinet_aba = 'MODULOS'
        addon.chapas._ocupado[0] = False
        addon.chapas._havia_modal[0] = False
        bpy.context.scene.tool_settings.use_transform_correct_face_attributes = False
        # The depsgraph handler also normalizes at every view_layer.update(). Outside this
        # fixture, tests call coordinators individually to identify which one
        # performed the work.
        lista = bpy.app.handlers.depsgraph_update_post
        self._tinha_handler = addon.chapas.ao_atualizar_depsgraph in lista
        if self._tinha_handler:
            lista.remove(addon.chapas.ao_atualizar_depsgraph)

    def tearDown(self):
        lista = bpy.app.handlers.depsgraph_update_post
        if self._tinha_handler and addon.chapas.ao_atualizar_depsgraph not in lista:
            lista.append(addon.chapas.ao_atualizar_depsgraph)
        addon.chapas._ocupado[0] = False

    def assertPerto(self, a, b, casas=5):
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=casas)

    # ------------------------------------------------------------ Scenes
    def nicho_solto(self, L=600.0, A=400.0, P=300.0, E=18.0):
        """Create two sides, base and top with adjacency but without an Empty."""
        li = L - 2 * E
        C = bpy.context
        pecas = {
            'Lat_E': addon.chapas.nova_chapa('Lat_E', A, P, E, (-(L / 2 - E / 2), 0, A / 2),
                                      (0, 90, 0), C),
            'Lat_D': addon.chapas.nova_chapa('Lat_D', A, P, E, (L / 2 - E / 2, 0, A / 2),
                                      (0, 90, 0), C),
            'Base': addon.chapas.nova_chapa('Base', li, P, E, (0, 0, E / 2), (0, 0, 0), C),
            "Top": addon.chapas.nova_chapa("Top", li, P, E, (0, 0, A - E / 2),
                                      (0, 0, 0), C),
        }
        C.view_layer.update()
        addon.chapas.detectar_adjacencia(list(pecas.values()))
        return pecas

    def modulo(self):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar()
        conj = next(o for o in bpy.data.objects if addon.chapas.MARCA_CONJUNTO in o)
        bpy.context.view_layer.update()
        return conj

    def peca(self, conj, prefixo):
        return next(o for o in addon.modulos._chapas_do_conjunto(conj)
                    if o.name.startswith(prefixo))

    def porta_importada(self, x=0.0, largura=0.4, altura=0.7, z=0.35, y=-0.2):
        placa = caixa('Placa', (largura, 0.018, altura), (x, y - 0.009, z))
        selecionar(placa)
        self.assertEqual(bpy.ops.object.cabinet_folha_de_objetos(), {'FINISHED'})
        return addon.portas._grupo_portas(placa), placa

    # ================================================= 1. ADJACENCY
    def test_adjacencia_fecha_o_vao_aberto_pela_escala(self):
        # Scaling furniture by F multiplies side-panel positions but not thickness,
        # leaving (E/2)*(F-1) per side between base and side panel.
        L, E, F = 600.0, 18.0, 1.5
        C = bpy.context
        lat_e = addon.chapas.nova_chapa('Lat_E', 400, 300, E, (-(L / 2 - E / 2), 0, 200),
                                 (0, 90, 0), C)
        lat_d = addon.chapas.nova_chapa('Lat_D', 400, 300, E, (L / 2 - E / 2, 0, 200),
                                 (0, 90, 0), C)
        base = addon.chapas.nova_chapa('Base', L - 2 * E, 300, E, (0, 0, E / 2),
                                (0, 0, 0), C)
        C.view_layer.update()
        addon.chapas.detectar_adjacencia([lat_e, lat_d, base])
        self.assertEqual(base['adj_x_pos_uid'], lat_d['chapa_uid'])
        self.assertEqual(base['adj_x_neg_uid'], lat_e['chapa_uid'])
        # What S would do to the entire group around the origin.
        for lat in (lat_e, lat_d):
            lat.location.x *= F
        C.view_layer.update()
        for lat in (lat_e, lat_d):
            lat.scale = (1.0, 1.0, F)      # Local Z = world X: thickness.
        base.scale = (F, 1.0, 1.0)
        ajustadas = addon.chapas.normalizar_chapas()
        C.view_layer.update()
        self.assertEqual(set(ajustadas), {lat_e, lat_d, base})
        for obj in (lat_e, lat_d, base):
            self.assertPerto(obj.scale, (1, 1, 1))
        # Thickness is unaffected by scale, invariant 1.
        self.assertAlmostEqual(lat_d.chapa_espessura_mm, E, places=4)
        self.assertAlmostEqual(lat_d.chapa_largura_mm, 400, places=3)
        # The base takes up the extra opening: (L-2E)*F + 2*(E/2)*(F-1).
        so_escala = (L - 2 * E) * F
        self.assertAlmostEqual(base.chapa_largura_mm - so_escala,
                               2 * (E / 2) * (F - 1), places=2)
        self.assertAlmostEqual(base.chapa_largura_mm, (L - E) * F - E, places=2)
        # And touches each side panel's inner face exactly.
        b_lo, b_hi = addon.chapas._faixa(base, X)
        self.assertAlmostEqual(b_hi, addon.chapas._faixa(lat_d, X)[0], places=5)
        self.assertAlmostEqual(b_lo, addon.chapas._faixa(lat_e, X)[1], places=5)

    # Regression, fixed in v126: Y reread the center from a stale matrix_world
    # and undid the displacement along X.
    def test_adjacencia_fecha_dois_eixos_ao_mesmo_tempo(self):
        C = bpy.context
        prat = addon.chapas.nova_chapa('Prat', 400, 300, 18, (0, 0, 0), (0, 0, 0), C)
        # Side touching X+ at X 200..218, back touching Y+ at Y 150..168;
        # both narrow enough not to touch the corners.
        lat = addon.chapas.nova_chapa('Lat', 300, 100, 18, (209, 0, 0), (0, 90, 0), C)
        fundo = addon.chapas.nova_chapa("Back Panel", 200, 300, 18, (0, 159, 0),
                                 (90, 0, 0), C)
        C.view_layer.update()
        addon.chapas.detectar_adjacencia([prat, lat, fundo])
        self.assertEqual(prat['adj_x_pos'], lat.name)
        self.assertEqual(prat['adj_y_pos'], fundo.name)
        prat.scale = (1.5, 1.5, 1.0)
        addon.chapas.normalizar_chapas()
        C.view_layer.update()
        self.assertAlmostEqual(prat.chapa_largura_mm, 500.0, places=2)
        self.assertAlmostEqual(prat.chapa_comprimento_mm, 375.0, places=2)
        # X: -300 at the extended free side .. 200 at the side-panel face.
        self.assertPerto(addon.chapas._faixa(prat, X), (-0.3, 0.2), 4)
        # Y: -225 .. 150 at the back face.
        self.assertPerto(addon.chapas._faixa(prat, Y), (-0.225, 0.15), 4)

    def test_resolver_vizinho_prefere_uid_do_irmao_na_copia(self):
        conj = self.modulo()
        selecionar(conj, *conj.children)
        self.assertEqual(bpy.ops.object.duplicate(), {'FINISHED'})
        copia = next(o for o in bpy.context.selected_objects
                     if addon.chapas.MARCA_CONJUNTO in o)
        self.assertIsNot(copia, conj)
        copia.location.x += 2.0
        bpy.context.view_layer.update()
        base2 = self.peca(copia, 'Base')
        lat_d1 = self.peca(conj, 'Lateral_Dir')
        lat_d2 = self.peca(copia, 'Lateral_Dir')
        # A copy inherits the original's name and UID; only UID plus siblings distinguishes it.
        self.assertEqual(base2['adj_x_pos'], lat_d1.name)
        self.assertEqual(lat_d2['chapa_uid'], lat_d1['chapa_uid'])
        self.assertIs(addon.chapas._resolver_vizinho(
            base2, base2['adj_x_pos_uid'], base2['adj_x_pos']), lat_d2)
        # Without UID, fall back to the name and find the original.
        self.assertIs(addon.chapas._resolver_vizinho(base2, '', base2['adj_x_pos']),
                      lat_d1)
        # A UID repeated across cabinets resolves within its own cabinet.
        self.assertIs(addon.chapas._resolver_vizinho(
            lat_d2, lat_d2['chapa_uid'], ''), lat_d2)
        # Effect: the copy's base meets its own sides rather than the original's.
        base2.scale = (1.3, 1.0, 1.0)
        addon.chapas.normalizar_chapas()
        bpy.context.view_layer.update()
        self.assertAlmostEqual(base2.chapa_largura_mm, 564.0, places=2)
        self.assertPerto(addon.chapas._faixa(base2, X), (2 - 0.282, 2 + 0.282), 4)
        self.assertAlmostEqual(self.peca(conj, 'Base').chapa_largura_mm, 564.0,
                               places=2)

    def test_vizinho_com_uid_duplicado_no_modulo_conserva_identidade_ao_mover(self):
        # Regression, fixed in v347: the weld switched sides when a same-UID copy
        # was closer.
        conj = self.modulo()
        base = self.peca(conj, 'Base')
        lateral = self.peca(conj, 'Lateral_Dir')
        copia = lateral.copy()
        bpy.context.collection.objects.link(copia)
        copia.location = base.location
        lateral.location.x += 2
        bpy.context.view_layer.update()
        self.assertIs(addon.chapas._resolver_vizinho(
            base, base['adj_x_pos_uid'], base['adj_x_pos']), lateral)
        # The name neither overrides UID nor references an object in another cabinet.
        self.assertIs(addon.chapas._resolver_vizinho(
            base, base['adj_x_pos_uid'], base.name), copia)

    def test_copia_de_chapa_no_mesmo_modulo_sai_sem_as_soldas(self):
        # User request: Ctrl+D on a panel copied its UID and welds, causing it
        # to stretch toward the original panel's neighbors.
        conj = self.modulo()
        lat, base = self.peca(conj, 'Lateral_Dir'), self.peca(conj, 'Base')
        selecionar(lat)
        self.assertEqual(bpy.ops.object.duplicate(), {'FINISHED'})
        copia = bpy.context.selected_objects[0]
        self.assertEqual(copia['chapa_uid'], lat['chapa_uid'])     # The residual record.
        # The handler schedules the timer; background mode does not run it automatically.
        addon.chapas._separar_copias_no_timer()
        self.assertNotEqual(copia['chapa_uid'], lat['chapa_uid'])
        self.assertFalse(any(copia.get('adj_' + k) for k in addon.chapas.PONTAS))
        self.assertIs(addon.solda._vizinho_da_ponta(base, 'x_pos'), lat)
        self.assertFalse(addon.chapas._copias_com_mesmo_uid())

    def test_recalcular_ancoragem_refaz_as_soldas_pelo_lugar(self):
        conj = self.modulo()
        lat, base = self.peca(conj, 'Lateral_Dir'), self.peca(conj, 'Base')
        selecionar(lat)
        bpy.ops.object.duplicate()
        copia = bpy.context.selected_objects[0]
        # Moved outside, like the cladding in the user's example.
        copia.location.x += 0.018
        bpy.context.view_layer.update()
        selecionar(copia)
        self.assertEqual(bpy.ops.object.cabinet_recalcular_ancoragem(), {'FINISHED'})
        self.assertNotEqual(copia['chapa_uid'], lat['chapa_uid'])
        # Only parts actually touching within 5 mm stay welded.
        for k in addon.chapas.PONTAS:
            vizinho = addon.solda._vizinho_da_ponta(copia, k)
            if vizinho is not None:
                self.assertLessEqual(abs(copia['adj_%s_folga' % k]),
                                     addon.chapas.ALCANCE_CONEXAO_AUTOMATICA + 1e-9)
                self.assertIsNot(vizinho, base)
        self.assertIs(addon.solda._vizinho_da_ponta(base, 'x_pos'), lat)
        selecionar()
        self.assertFalse(addon.solda.OBJECT_OT_recalcular_ancoragem.poll(bpy.context))

    # ============================== 2. DETECT ADJACENCY OPERATOR
    def test_operador_detectar_adjacencia(self):
        C = bpy.context
        lat = addon.chapas.nova_chapa('Lat', 400, 300, 18, (291, 0, 200), (0, 90, 0), C)
        base = addon.chapas.nova_chapa('Base', 564, 300, 18, (0, 0, 9), (0, 0, 0), C)
        C.view_layer.update()
        selecionar(base)
        self.assertEqual(bpy.ops.object.cabinet_detectar_adjacencia(),
                         {'CANCELLED'})
        self.assertNotIn('adj_x_pos', base)
        self.assertNotIn('chapa_uid', base)
        # A selected non-panel does not count as the second panel.
        intruso = caixa('Intruso', (0.1, 0.1, 0.1), (2, 0, 0))
        selecionar(base, intruso)
        self.assertEqual(bpy.ops.object.cabinet_detectar_adjacencia(),
                         {'CANCELLED'})
        selecionar(base, lat)
        self.assertEqual(bpy.ops.object.cabinet_detectar_adjacencia(),
                         {'FINISHED'})
        self.assertEqual(base['adj_x_pos'], lat.name)
        self.assertEqual(base['adj_x_pos_uid'], lat['chapa_uid'])
        self.assertAlmostEqual(base['adj_x_pos_folga'], 0.0, places=6)
        self.assertEqual(base['adj_x_pos_face'], 0)     # Nearest face.
        self.assertEqual(base['adj_x_neg'], '')         # Nothing to the left.
        for ponta in addon.chapas.PONTAS:
            self.assertIn('adj_' + ponta, lat)
        self.assertNotIn(addon.chapas.MARCA_CHAPA, intruso)

    # ===================================== 3. ABSORB ASSEMBLIES
    def test_absorver_conjuntos_sem_escala_nao_mexe(self):
        conj = self.modulo()
        antes = {o.name: o.matrix_world.copy() for o in conj.children}
        medidas = (conj.conj_largura_mm, conj.conj_altura_mm,
                   conj.conj_profundidade_mm)
        addon.modulos.absorver_conjuntos()
        bpy.context.view_layer.update()
        for o in conj.children:
            for a, b in zip(o.matrix_world, antes[o.name]):
                self.assertLess((a - b).length, 1e-6)
        self.assertPerto((conj.conj_largura_mm, conj.conj_altura_mm,
                          conj.conj_profundidade_mm), medidas, 3)

    # Regression, fixed in v126: S on the cabinet Empty had no effect;
    # children reverted through their still-scaled parent.
    def test_absorver_conjuntos_passa_escala_do_empty_para_as_chapas(self):
        F = 1.5
        conj = self.modulo()
        lat_d = self.peca(conj, 'Lateral_Dir')
        base = self.peca(conj, 'Base')
        conj.scale = (F, 1.0, 1.0)
        bpy.context.view_layer.update()
        # Precondition: S on the Empty actually moved the side outward.
        self.assertAlmostEqual(lat_d.matrix_world.translation.x, 0.291 * F,
                               places=5)
        addon.modulos.absorver_conjuntos()
        bpy.context.view_layer.update()
        self.assertPerto(conj.scale, (1, 1, 1))
        # Panels stay where S put them...
        self.assertAlmostEqual(lat_d.matrix_world.translation.x, 0.291 * F,
                               places=5)
        addon.chapas.normalizar_chapas()
        bpy.context.view_layer.update()
        # ...and after normalization, the cabinet has its new dimensions: unchanged
        # side thickness, with the base closing the (E/2)*(F-1) gap.
        for o in addon.modulos._chapas_do_conjunto(conj):
            self.assertPerto(o.scale, (1, 1, 1))
            self.assertAlmostEqual(o.chapa_espessura_mm, 18.0, places=4)
        self.assertAlmostEqual(base.chapa_largura_mm, 582 * F - 18, places=2)
        self.assertAlmostEqual(conj.conj_largura_mm, 582 * F + 18, places=2)
        self.assertAlmostEqual(addon.modulos.medir_conjunto(conj)[0], 582 * F + 18,
                               places=2)
        self.assertAlmostEqual(conj.conj_altura_mm, 400.0, places=2)

    # ============================================= 4. THICKNESS
    def test_espessura_do_modulo_engrossa_para_dentro(self):
        conj = self.modulo()
        caixa_antes = addon.modulos.medir_conjunto(conj)
        lo_antes, hi_antes = limites(addon.modulos._chapas_do_conjunto(conj))
        conj.conj_espessura_mm = 30.0
        bpy.context.view_layer.update()
        chapas = addon.modulos._chapas_do_conjunto(conj)
        for o in chapas:
            self.assertAlmostEqual(o.chapa_espessura_mm, 30.0, places=4)
        # Outer outline stays fixed, both dimension properties and actual mesh box.
        self.assertPerto(addon.modulos.medir_conjunto(conj), caixa_antes, 2)
        lo, hi = limites(chapas)
        self.assertPerto(lo, lo_antes, 4)
        self.assertPerto(hi, hi_antes, 4)
        # Base and top shrink to fit between thicker sides.
        for nome in ('Base', "Top"):
            self.assertAlmostEqual(self.peca(conj, nome).chapa_largura_mm,
                                   600 - 2 * 30, places=2)
        self.assertAlmostEqual(addon.chapas._faixa(self.peca(conj, 'Lateral_Dir'), X)[0],
                               0.3 - 0.030, places=5)
        self.assertAlmostEqual(addon.chapas._faixa(self.peca(conj, 'Base'), Z)[1],
                               0.030, places=5)
        self.assertAlmostEqual(addon.chapas._faixa(self.peca(conj, "Top"), Z)[0],
                               0.4 - 0.030, places=5)

    def test_espessura_de_uma_chapa_ancora_na_face_externa(self):
        conj = self.modulo()
        lat_d = self.peca(conj, 'Lateral_Dir')
        base = self.peca(conj, 'Base')
        lado_externo = addon.chapas._faixa(lat_d, X)[1]
        self.assertAlmostEqual(lado_externo, 0.3, places=5)
        largura_base = base.chapa_largura_mm
        lat_d.chapa_espessura_mm = 30.0
        bpy.context.view_layer.update()
        self.assertAlmostEqual(lat_d.chapa_espessura_mm, 30.0, places=4)
        # The face on the cabinet boundary stays fixed; added thickness extends inward.
        lo, hi = addon.chapas._faixa(lat_d, X)
        self.assertAlmostEqual(hi, lado_externo, places=5)
        self.assertAlmostEqual(hi - lo, 0.030, places=5)
        # User request: the base must not move or stick to the weld. Its side weld
        # deviates from the origin and is left for the ruler to resolve.
        self.assertAlmostEqual(base.chapa_largura_mm, largura_base, places=4)
        self.assertAlmostEqual(addon.chapas._faixa(base, X)[1], 0.3 - 0.018, places=5)
        self.assertIn(base, {l['a'] for l in addon.solda._pontas_fora_do_lugar([lat_d])}
                      | {l['b'] for l in addon.solda._pontas_fora_do_lugar([lat_d])})
        # The mesh follows the properties; other panels remain unchanged.
        self.assertAlmostEqual(limites([lat_d])[1][0], 0.3, places=5)
        self.assertAlmostEqual(self.peca(conj, 'Lateral_Esq').chapa_espessura_mm,
                               18.0, places=4)
        self.assertAlmostEqual(addon.modulos.medir_conjunto(conj)[0], 600.0, places=2)

    def test_espessura_de_uma_chapa_nao_puxa_peca_afastada(self):
        # User bug: changing one panel's E reapplied every scene weld,
        # pulling back a side panel intentionally moved away.
        conj = self.modulo()
        lat_d = self.peca(conj, 'Lateral_Dir')
        tampo = self.peca(conj, "Top")
        lat_d.location.x += 0.2
        bpy.context.view_layer.update()
        longe = lat_d.matrix_world.translation.copy()
        largura_tampo = tampo.chapa_largura_mm
        self.peca(conj, 'Lateral_Esq').chapa_espessura_mm = 25.0
        bpy.context.view_layer.update()
        self.assertLess((lat_d.matrix_world.translation - longe).length, 1e-6)
        self.assertAlmostEqual(tampo.chapa_largura_mm, largura_tampo, places=4)

    def test_espessura_do_grupo_solto_pela_cena(self):
        pecas = self.nicho_solto()
        selecionar(pecas['Base'], *pecas.values())
        self.assertEqual(addon.gaveta._modo_chapa(bpy.context, pecas['Base']), 'GRUPO')
        self.assertEqual(set(addon.modulos._grupo_ativo(bpy.context)),
                         set(pecas.values()))
        addon.modulos.sincronizar_grupo(bpy.context)
        s = bpy.context.scene
        self.assertAlmostEqual(s.grupo_largura_mm, 600.0, places=2)
        self.assertAlmostEqual(s.grupo_espessura_mm, 18.0, places=4)
        lo_antes, hi_antes = limites(list(pecas.values()))
        s.grupo_espessura_mm = 30.0
        bpy.context.view_layer.update()
        for o in pecas.values():
            self.assertIsNone(o.parent)
            self.assertAlmostEqual(o.chapa_espessura_mm, 30.0, places=4)
        lo, hi = limites(list(pecas.values()))
        self.assertPerto(lo, lo_antes, 4)
        self.assertPerto(hi, hi_antes, 4)
        self.assertAlmostEqual(pecas['Base'].chapa_largura_mm, 540.0, places=2)
        self.assertAlmostEqual(addon.chapas._faixa(pecas["Top"], Z)[0], 0.37, places=5)

    # ======================================= 5. HANDLER AND TIMER
    def chapa_escalada(self):
        chapa = addon.chapas.nova_chapa('Solta', 600, 400, 18, (0, 0, 0), (0, 0, 0),
                                 bpy.context)
        bpy.context.view_layer.update()
        chapa.scale = (2.0, 0.5, 3.0)
        return chapa

    def test_handler_de_depsgraph_normaliza_quando_nao_ha_modal(self):
        chapa = self.chapa_escalada()
        with ocupado():
            addon.chapas.ao_atualizar_depsgraph(bpy.context.scene, None)
        self.assertPerto(chapa.scale, (2.0, 0.5, 3.0))
        self.assertAlmostEqual(chapa.chapa_largura_mm, 600.0, places=3)
        addon.chapas.ao_atualizar_depsgraph(bpy.context.scene, None)
        self.assertPerto(chapa.scale, (1, 1, 1))
        self.assertAlmostEqual(chapa.chapa_largura_mm, 1200.0, places=3)
        self.assertAlmostEqual(chapa.chapa_comprimento_mm, 200.0, places=3)
        self.assertAlmostEqual(chapa.chapa_espessura_mm, 18.0, places=4)
        self.assertFalse(addon.chapas._havia_modal[0])
        # Mesh rebuilt with the new dimension.
        bpy.context.view_layer.update()
        lo, hi = limites([chapa])
        self.assertPerto((hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]),
                         (1.2, 0.2, 0.018), 5)

    def test_handler_termina_o_modal_que_havia(self):
        # Modal-finished transition: recalculate and forget the modal operator.
        chapa = self.chapa_escalada()
        addon.chapas._havia_modal[0] = True
        addon.chapas.ao_atualizar_depsgraph(bpy.context.scene, None)
        self.assertFalse(addon.chapas._havia_modal[0])
        self.assertAlmostEqual(chapa.chapa_largura_mm, 1200.0, places=3)

    def test_timer_normaliza_e_continua_vivo(self):
        chapa = self.chapa_escalada()
        with ocupado():
            self.assertEqual(addon.eventos.verificar_periodicamente(),
                             addon.eventos.INTERVALO_TIMER)
        self.assertPerto(chapa.scale, (2.0, 0.5, 3.0))
        self.assertAlmostEqual(chapa.chapa_largura_mm, 600.0, places=3)
        self.assertEqual(addon.eventos.verificar_periodicamente(), addon.eventos.INTERVALO_TIMER)
        self.assertPerto(chapa.scale, (1, 1, 1))
        self.assertAlmostEqual(chapa.chapa_largura_mm, 1200.0, places=3)
        self.assertAlmostEqual(chapa.chapa_espessura_mm, 18.0, places=4)

    # ============================================== 6. HANDLES
    def test_converter_puxador_marca_so_o_que_nao_e_chapa(self):
        chapa = addon.chapas.nova_chapa("Panel", 600, 400, 18, (0, 0, 0), (0, 0, 0),
                                 bpy.context)
        pux = caixa('Pux', (0.02, 0.03, 0.15), (1, 0, 0))
        selecionar(chapa)
        self.assertFalse(addon.importacao.OBJECT_OT_converter_puxador.poll(bpy.context))
        antes = limites([pux])
        selecionar(pux, chapa)
        self.assertTrue(addon.importacao.OBJECT_OT_converter_puxador.poll(bpy.context))
        self.assertEqual(bpy.ops.object.cabinet_converter_puxador(),
                         {'FINISHED'})
        self.assertIn(addon.chapas.MARCA_PUXADOR, pux)
        self.assertEqual(list(pux[addon.chapas.CHAVE_TRAVAS_PUXADOR]), [1, 1, 1])
        self.assertNotIn(addon.chapas.MARCA_PUXADOR, chapa)     # A panel must not become a handle.
        self.assertIn(addon.chapas.MARCA_CHAPA, chapa)
        self.assertIsNone(pux.parent)
        self.assertEqual(limites([pux]), antes)          # Dimensions preserved.
        # Already a handle: no longer appears as a loose mesh.
        selecionar(pux)
        self.assertFalse(addon.importacao.OBJECT_OT_converter_puxador.poll(bpy.context))

    def test_puxadores_e_folhas_da_selecao(self):
        grupo, placa = self.porta_importada()
        pux = caixa('Pux', (0.02, 0.03, 0.15), (0.17, -0.233, 0.35))
        pux[addon.chapas.MARCA_PUXADOR] = 1
        selecionar(pux, grupo, placa)
        puxadores, folhas = addon.importacao._puxadores_e_folhas_da_selecao(bpy.context)
        self.assertEqual(puxadores, [pux])
        self.assertEqual(folhas, [placa])                # Without repetition.
        selecionar(pux)
        self.assertEqual(addon.importacao._puxadores_e_folhas_da_selecao(bpy.context),
                         ([pux], []))
        self.assertFalse(addon.importacao.OBJECT_OT_vincular_puxador.poll(bpy.context))

    def test_vincular_puxador_pendura_na_folha_mais_proxima_sem_mover(self):
        g1, placa1 = self.porta_importada(x=-0.5)
        g2, placa2 = self.porta_importada(x=0.5)
        pux = caixa('Pux', (0.02, 0.03, 0.15), (0.67, -0.233, 0.35))
        selecionar(pux)
        bpy.ops.object.cabinet_converter_puxador()
        mundo = pux.matrix_world.copy()
        selecionar(pux, g1, g2)
        self.assertTrue(addon.importacao.OBJECT_OT_vincular_puxador.poll(bpy.context))
        self.assertEqual(bpy.ops.object.cabinet_vincular_puxador(), {'FINISHED'})
        self.assertIs(pux.parent, placa2)
        bpy.context.view_layer.update()
        for a, b in zip(pux.matrix_world, mundo):
            self.assertLess((a - b).length, 1e-6)
        # Identity inverse: matrix_basis is the leaf reference frame.
        for a, b in zip(pux.matrix_parent_inverse, Matrix.Identity(4)):
            self.assertLess((a - b).length, 1e-6)
        # Parented to and following the leaf.
        placa2.matrix_world = (Matrix.Translation((0, 0, 0.1))
                               @ placa2.matrix_world)
        bpy.context.view_layer.update()
        self.assertAlmostEqual(pux.matrix_world.translation.z,
                               mundo.translation.z + 0.1, places=6)

    # ======================================== 7. SELECTION POLL
    def contexto_viewport(self):
        janela = bpy.context.window_manager.windows[0]
        area = next(a for a in janela.screen.areas if a.type == 'VIEW_3D')
        regiao = next(r for r in area.regions if r.type == 'WINDOW')
        return janela, area, regiao

    def test_poll_da_selecao_por_grupo(self):
        janela, area, regiao = self.contexto_viewport()
        outra = next(a for a in janela.screen.areas if a.type != 'VIEW_3D')
        chapa = addon.chapas.nova_chapa("Panel", 600, 400, 18, (0, 0, 0), (0, 0, 0),
                                 bpy.context)
        selecionar(chapa)
        poll = addon.selecao.OBJECT_OT_selecionar.poll
        prefs_original = addon.opcoes._prefs
        try:
            with bpy.context.temp_override(window=janela, area=area,
                                           region=regiao):
                # Without preferences, as in scripted add-on loading, the option is enabled.
                self.assertIsNone(addon.opcoes._prefs())
                self.assertTrue(poll(bpy.context))
                addon.opcoes._prefs = lambda: SimpleNamespace(selecao_por_grupo=False)
                self.assertFalse(poll(bpy.context))
                addon.opcoes._prefs = lambda: SimpleNamespace(selecao_por_grupo=True)
                self.assertTrue(poll(bpy.context))
                addon.opcoes._prefs = prefs_original
                bpy.ops.object.mode_set(mode='EDIT')
                try:
                    self.assertEqual(bpy.context.mode, 'EDIT_MESH')
                    self.assertFalse(poll(bpy.context))
                finally:
                    bpy.ops.object.mode_set(mode='OBJECT')
                self.assertTrue(poll(bpy.context))
            with bpy.context.temp_override(window=janela, area=outra):
                self.assertFalse(poll(bpy.context))     # Outside the viewport.
        finally:
            addon.opcoes._prefs = prefs_original

    # ===================================== 9. LOOSE GROUP DIMENSIONS
    def test_largura_do_grupo_solto_pela_cena(self):
        pecas = self.nicho_solto()
        selecionar(pecas['Base'], *pecas.values())
        addon.modulos.sincronizar_grupo(bpy.context)
        s = bpy.context.scene
        self.assertAlmostEqual(s.grupo_altura_mm, 400.0, places=2)
        self.assertAlmostEqual(s.grupo_profundidade_mm, 300.0, places=2)
        lo_antes, hi_antes = limites(list(pecas.values()))
        s.grupo_largura_mm = 800.0
        bpy.context.view_layer.update()
        lo, hi = limites(list(pecas.values()))
        # X anchor 'min': left stays fixed, right moves 200 mm.
        self.assertAlmostEqual(lo[0], lo_antes[0], places=5)
        self.assertAlmostEqual(hi[0], hi_antes[0] + 0.2, places=5)
        self.assertPerto(lo[1:], lo_antes[1:], 5)
        self.assertPerto(hi[1:], hi_antes[1:], 5)
        for o in pecas.values():
            self.assertAlmostEqual(o.chapa_espessura_mm, 18.0, places=4)
            self.assertPerto(o.scale, (1, 1, 1))
        for nome in ('Base', "Top"):
            self.assertAlmostEqual(pecas[nome].chapa_largura_mm, 764.0, places=2)
        self.assertAlmostEqual(pecas['Lat_D'].chapa_largura_mm, 400.0, places=2)
        self.assertAlmostEqual(addon.chapas._faixa(pecas['Base'], X)[1],
                               addon.chapas._faixa(pecas['Lat_D'], X)[0], places=5)

    def test_redimensionar_grupo_da_cena_sem_grupo_nao_faz_nada(self):
        selecionar()
        addon.modulos.redimensionar_grupo_da_cena(bpy.context.scene, bpy.context)
        avulsa = caixa('Avulsa', (0.1, 0.1, 0.1), (0, 0, 0))
        selecionar(avulsa)
        self.assertEqual(addon.modulos._grupo_ativo(bpy.context), [])
        addon.modulos.redimensionar_grupo_da_cena(bpy.context.scene, bpy.context)
        self.assertPerto(avulsa.dimensions, (0.1, 0.1, 0.1))

    # ================================== 10. HELPERS
    def test_sem_modal_em_background(self):
        self.assertGreater(len(bpy.context.window_manager.windows), 0)
        self.assertFalse(addon.eventos._ha_modal_ativo())

    def test_marcar_apanhando_acende_o_botao(self):
        antes = addon.portas._apanhando_vao[0]
        try:
            addon.portas._marcar_apanhando(True)
            self.assertTrue(addon.portas._apanhando_vao[0])
            addon.portas._marcar_apanhando(True)                # Idempotent.
            self.assertTrue(addon.portas._apanhando_vao[0])
            rotulo, acao = addon.gaveta._botao_criar_portas(bpy.context)
            self.assertEqual(rotulo, "Marking the opening... (Esc cancels)")
            self.assertTrue(acao[2])
            addon.portas._marcar_apanhando(False)
            self.assertFalse(addon.portas._apanhando_vao[0])
            rotulo, acao = addon.gaveta._botao_criar_portas(bpy.context)
            self.assertEqual(rotulo, "Create Doors")
            self.assertFalse(acao[2])
        finally:
            addon.portas._apanhando_vao[0] = antes

    def test_modal_terminado_larga_os_objetos_da_cena(self):
        # Reproducible user crash: Ctrl+Z during door creation. The finished REGISTER
        # wizard remained alive holding snap-target objects; undo freed them while
        # Python still retained references.
        modais = [c for c in addon.CLASSES if isinstance(c, type)
                  and issubclass(c, bpy.types.Operator) and 'modal' in c.__dict__]
        self.assertIn(addon.assistente.OBJECT_OT_apanhar_vao_portas, modais)
        for classe in modais:
            self.assertTrue(getattr(classe.modal, 'larga_dados', False),
                            classe.__name__)
        bpy.ops.mesh.primitive_cube_add()
        cubo = bpy.context.object

        class Falso:
            def modal(self, context, event):
                self._alvos = [(cubo, [cubo.location.copy()])]
                self._mapa = {'a': cubo}
                self._base = {cubo: cubo.location.copy()}
                self._numero = 3
                self._pronto = context
                return event

        modal = addon._envolver_evento(Falso.modal)
        op = Falso()
        self.assertEqual(modal(op, 'ctx', {'RUNNING_MODAL'}), {'RUNNING_MODAL'})
        self.assertIsNotNone(op._alvos)          # While running, change nothing.
        modal(op, 'ctx', {'FINISHED'})
        self.assertIsNone(op._alvos)
        self.assertIsNone(op._mapa)
        self.assertIsNone(op._base)
        self.assertEqual((op._numero, op._pronto), (3, 'ctx'))

    # ========================================= 11. UNREGISTER
    def test_unregister_remove_handlers_timers_keymaps_e_classes(self):
        lista = bpy.app.handlers.depsgraph_update_post
        if self._tinha_handler:
            lista.append(addon.chapas.ao_atualizar_depsgraph)
        self.assertIsNotNone(addon.hud._handler_grid[0])
        self.assertIsNotNone(addon.hud._handler_hud_texto[0])
        addon.unregister()
        try:
            self.assertIsNone(addon.hud._handler_grid[0])
            self.assertIsNone(addon.hud._handler_hud_texto[0])
            self.assertIsNone(addon.gaveta._handler_gaveta[0])
            self.assertIsNone(addon.puxadores._handler_posicionador[0])
            self.assertNotIn(addon.chapas.ao_atualizar_depsgraph, lista)
            for evento, funcao in (addon.eventos.HANDLERS_CONTORNO
                                   + addon.eventos.HANDLERS_REFERENCIAS):
                self.assertNotIn(funcao, getattr(bpy.app.handlers, evento),
                                 evento)
            for timer in (addon.eventos.verificar_periodicamente,
                          addon.gaveta._limitar_largura_gaveta,
                          addon.gaveta._reconectar_gavetas,
                          addon.gaveta._configurar_gavetas,
                          addon.gaveta._animar_realces,
                          addon.eventos._fim_do_desfazer):
                self.assertFalse(bpy.app.timers.is_registered(timer),
                                 timer.__name__)
            self.assertEqual(addon.selecao._keymaps, [])
            kc = bpy.context.window_manager.keyconfigs.addon
            km = kc.keymaps.get('3D View') if kc else None
            if km is not None:
                self.assertFalse([k for k in km.keymap_items
                                  if k.idname.startswith('object.cabinet')])
            for classe in addon.CLASSES:
                # Gizmos have no is_registered; bl_rna disappears on unregister.
                self.assertNotIn('bl_rna', classe.__dict__, classe.__name__)
            self.assertFalse(hasattr(bpy.types.Scene, 'cabinet_aba'))
        finally:
            addon.register()
        # And returns intact.
        self.assertIsNotNone(addon.hud._handler_grid[0])
        self.assertIsNotNone(addon.hud._handler_hud_texto[0])
        self.assertIn(addon.chapas.ao_atualizar_depsgraph, lista)
        for classe in addon.CLASSES:
            self.assertIn('bl_rna', classe.__dict__, classe.__name__)
        self.assertTrue(hasattr(bpy.types.Scene, 'cabinet_aba'))
        if not self._tinha_handler:
            lista.remove(addon.chapas.ao_atualizar_depsgraph)

    # Regression, fixed in v126: register() timers, including a lambda, were not
    # removed on unregister, violating invariant 13.
    def test_unregister_remove_timer_adiado(self):
        self.assertTrue(bpy.app.timers.is_registered(addon._registrar_bibliotecas_adiado))
        addon.unregister()
        try:
            self.assertFalse(bpy.app.timers.is_registered(addon._registrar_bibliotecas_adiado))
        finally:
            addon.register()


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestOperadores)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError("Operator tests failed")
