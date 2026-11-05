"""Architectural library and reversible associations in disposable scenes."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import bpy
import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon
A, I, P = addon.alvenaria, addon.instalacoes, addon.paredes


class Contexto:
    def __init__(self, **valores):
        self.__dict__.update(valores)

    def __getattr__(self, nome):
        return getattr(bpy.context, nome)


class TestInstalacoes(unittest.TestCase):
    def setUp(self):
        addon.eventos._fim_do_desfazer()
        addon.ambientes.encerrar_selecao()
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete()
        bpy.context.scene.pop(A.CHAVE_VISUAL, None)
        bpy.context.screen.pop(I.CHAVE_CATEGORIA, None)
        bpy.context.screen.pop(addon.gaveta._CHAVE_SUSPENSO, None)
        bpy.context.scene.cabinet_aba = 'ALVENARIA'
        A.esquecer();I.esquecer()
        self.area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        self.regiao = next(r for r in self.area.regions if r.type == 'WINDOW')

    def tearDown(self):
        addon.ambientes.encerrar_selecao()
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        A.esquecer();I.esquecer()

    def apoio(self, tipo='PAREDE', centro=(0,0,0), tamanho=8):
        normal = {'PAREDE': (0,-1,0), 'PISO': (0,0,1), 'TETO': (0,0,-1)}[tipo]
        bpy.ops.mesh.primitive_plane_add(size=tamanho, location=centro)
        obj = bpy.context.object
        obj.rotation_mode = 'QUATERNION'
        obj.rotation_quaternion = Vector((0,0,1)).rotation_difference(Vector(normal))
        obj[P.CHAVE_ALVENARIA] = True
        obj[A.CHAVE_TIPADA] = True
        obj.data.attributes.new(A.ATR_TIPO, 'INT', 'FACE').data[0].value = A.TIPOS.index(tipo)+1
        bpy.context.view_layer.update()
        return obj, A.referencial(centro, normal)

    def instalar(self, modelo='PORTA', tipo='PAREDE'):
        apoio, matriz = self.apoio(tipo)
        return I.instalar(bpy.context, modelo, apoio, 0, matriz), apoio

    def test_english_door_buttons_keep_stable_actions(self):
        door, _ = self.instalar()
        rows = []
        I.widgets(bpy.context, rows, 12, 900, 540, door)
        buttons = [row for row in rows if row[5] and row[5][:2] == ('escolha', 'acao_instalacao')
                   and row[4] in ('Reverse', 'Mirror')]
        self.assertEqual([row[4] for row in buttons], ['Reverse', 'Mirror'])
        self.assertEqual([row[5][2] for row in buttons], ['inverter', 'espelhar'])
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        door.select_set(True)
        bpy.context.view_layer.objects.active = door
        for row, key in zip(buttons, (addon.esquadrias.CHAVE_FACE, addon.esquadrias.CHAVE_LADO)):
            before = door.get(key, 1)
            self.assertEqual(bpy.ops.object.cabinet_acao_instalacao(acao=row[5][2]), {'FINISHED'})
            self.assertEqual(door[key], -before)

    def operador(self, modelo='SPOT_SOBREPOSTO', origem='', direito=False):
        op = SimpleNamespace(modelo=modelo, arrastar=True, origem=origem, direito=direito, report=Mock())
        op._mover = lambda *a: I.OBJECT_OT_instalar._mover(op, *a)
        op.cancel = lambda *a: I.OBJECT_OT_instalar.cancel(op, *a)
        ctx = Contexto(window_manager=SimpleNamespace(modal_handler_add=Mock()))
        evento = SimpleNamespace(mouse_x=0, mouse_y=0)
        self.assertEqual(I.OBJECT_OT_instalar.invoke(op, ctx, evento), {'RUNNING_MODAL'})
        return op

    def test_editar_primeiro_e_olho_ao_lado_de_teto_em_tres_larguras(self):
        self.apoio()
        for largura in (190,320,564):
            itens = addon.gaveta._widgets_aba_gaveta(bpy.context, largura, 1200, 0)
            topo = addon.gaveta._tamanho_cabecalho(itens)
            self.assertEqual(itens[topo][4], "Edit")
            teto = next(v for v in itens if v[4] == "Ceiling")
            olho = next(v for v in itens if v[5] and v[5][:2] == ('escolha','alvenaria_visual'))
            self.assertAlmostEqual(olho[0], teto[0]+teto[2]+6)
            self.assertEqual(olho[1], teto[1])
            self.assertEqual(addon.gaveta_eventos._icone_acao_gaveta(olho[5]), 'HIDE_ON')

    def test_olho_mostra_tres_tipos_e_remove_cache_ao_desligar(self):
        for tipo in A.TIPOS:
            self.apoio(tipo)
        self.assertEqual(bpy.ops.object.cabinet_visualizar_alvenaria(), {'FINISHED'})
        self.assertEqual(len(A._visuais[0]), 3)
        faces = [f for visual in A._visuais[0].values() for f in visual['faces']]
        self.assertEqual({f['tipo'] for f in faces}, set(A.TIPOS))
        self.assertTrue(all(v['bordas'] for v in A._visuais[0].values()))
        bpy.ops.object.cabinet_visualizar_alvenaria()
        self.assertFalse(bpy.context.scene[A.CHAVE_VISUAL])
        self.assertEqual(A._visuais[0], {})

    def test_editar_forca_visual_mesmo_com_olho_desligado(self):
        apoio,_ = self.apoio()
        A.iniciar_edicao(bpy.context, 'PAREDE', editar=True)
        self.assertFalse(bpy.context.scene.get(A.CHAVE_VISUAL, False))
        with patch.object(A, 'gpu'), patch.object(A, 'batch_for_shader'), patch.object(addon.ambientes,'_rotulo') as rotulo:
            A.desenhar_visual(bpy.context, apoio)
            self.assertEqual(rotulo.call_args.args[3], "Walls")

    def test_catalogo_reutiliza_cascata_grade_e_tem_fotos_reais(self):
        for it in I.catalogo():
            self.assertTrue((Path(it['pasta'])/it['foto']).is_file())
            self.assertEqual(len(it['niveis']), 2)
        I.definir_categoria(bpy.context, 1, "Lighting")
        I.definir_categoria(bpy.context, 2, 'Spots')
        for largura in (190,320,564):
            itens = []
            with patch.object(addon.gaveta, '_linha_cascata_gaveta', wraps=addon.gaveta._linha_cascata_gaveta) as cascata, \
                 patch.object(addon.gaveta, '_grade_biblioteca', wraps=addon.gaveta._grade_biblioteca) as grade:
                I.widgets_modelos(bpy.context, itens, 12, 700, largura-24, 'PAREDE')
                self.assertEqual(cascata.call_count, 2);grade.assert_called_once()
            modelos = [v[5][2] for v in itens if v[5] and v[5][:2] == ('escolha','modelo_instalacao')]
            # Regression, fixed in v404: the cascade covered the title.
            titulo = next(v for v in itens if v[4] == "Installations")
            campo = next(v for v in itens if v[5] and v[5][0] == 'suspenso')
            self.assertLessEqual(campo[1]+campo[3], titulo[1]-8)
            self.assertEqual(set(modelos), {'SPOT_EMBUTIDO','SPOT_SOBREPOSTO'})
            self.assertTrue(all(v[0]+v[2] <= largura-12+.001 for v in itens))
        I.definir_categoria(bpy.context, 1, "Doors and Windows")
        self.assertEqual(bpy.context.screen[I.CHAVE_CATEGORIA], "Doors and Windows")

    def test_cascata_superior_abre_sem_navegar_biblioteca_inferior(self):
        self.apoio()
        bpy.context.screen[addon.gaveta._CHAVE_SUSPENSO] = 'cabinet_instalacoes_1'
        itens = addon.gaveta._widgets_gaveta(bpy.context, 320, 1100)
        linhas = [v for v in itens if v[5] and v[5][0] == 'nivel']
        self.assertEqual({v[4] for v in linhas}, {"All","Electrical","Doors and Windows","Lighting","Ceilings"})
        self.assertTrue(all(v[5][1] == (I.ALVO,1) for v in linhas))
        self.assertTrue(all(v[1]+v[3] < 1100-48 for v in linhas))

    def test_modelos_nao_sao_filtrados_pelo_tipo_de_superficie(self):
        for tipo in A.TIPOS:
            itens=[];I.widgets_modelos(bpy.context,itens,12,900,540,tipo)
            modelos={v[5][2] for v in itens if v[5] and v[5][:2]==('escolha','modelo_instalacao')}
            self.assertEqual(modelos,set(I.modelos()))

    def test_porta_no_piso_fica_como_alcapao(self):
        obj, apoio = self.instalar(tipo='PISO')
        self.assertEqual(obj[A.CHAVE_VINCULO]['tipo'],'PISO')
        self.assertGreater(obj.matrix_world.to_3x3().col[2].dot(Vector((0,0,1))), .999)
        self.assertIs(A.apoio_de(obj),apoio)
        self.assertEqual(apoio.modifiers[0].solver,'EXACT')

    def test_luminarias_aceitam_faces_dos_tres_tipos(self):
        for modelo in ('SPOT_EMBUTIDO','SPOT_SOBREPOSTO','PENDENTE'):
            for tipo in A.TIPOS:
                obj, apoio = self.instalar(modelo, tipo)
                self.assertEqual(obj[A.CHAVE_VINCULO]['tipo'],tipo)
                self.assertIs(A.resolver(obj)[0],apoio)

    def test_arraste_consulta_motor_nativo_e_realca_face_inteira(self):
        apoio,_ = self.apoio()
        op = self.operador()
        evento = SimpleNamespace(mouse_x=self.regiao.x+100, mouse_y=self.regiao.y+100)
        with patch.object(P,'raio_ate_parede',return_value=(apoio,Vector(),Vector((0,-1,0)),0)) as raio, \
             patch.object(I.view3d_utils,'region_2d_to_origin_3d',return_value=Vector((0,-4,0))), \
             patch.object(I.view3d_utils,'region_2d_to_vector_3d',return_value=Vector((0,1,0))):
            op._mover(bpy.context,self.area,self.regiao,evento)
            raio.assert_called_once()
        self.assertEqual(I._previa[0]['tipo'],'PAREDE')
        self.assertGreater(len(I._previa[0]['face_visual']['contorno']),0)
        self.assertEqual(op.alvo[0],apoio.name)
        self.assertEqual(len(bpy.context.scene.objects),1)

    def test_preview_de_reassociacao_ignora_a_montagem_de_origem(self):
        obj, apoio = self.instalar('SPOT_SOBREPOSTO')
        op = self.operador('SPOT_SOBREPOSTO',obj.name,True)
        self.assertEqual(op.ignorados,{obj.name,*(o.name for o in obj.children_recursive)})
        evento = SimpleNamespace(type='ESC')
        antes = obj.matrix_world.copy()
        self.assertEqual(I.OBJECT_OT_instalar.modal(op,bpy.context,evento),{'CANCELLED'})
        self.assertEqual(obj.matrix_world,antes);self.assertIs(A.apoio_de(obj),apoio)

    def test_reassociar_transfere_so_o_proprio_corte_e_preserva_identidade(self):
        obj, anterior = self.instalar()
        outro,_ = self.apoio('PISO',(7,0,0))
        matriz = A.referencial((7,0,0),(0,0,1))
        nomes = {o.name for o in obj.children}
        uid = obj[I.IDENTIDADE]
        I.reassociar(bpy.context,obj,outro,0,matriz)
        self.assertEqual(obj[I.IDENTIDADE],uid)
        self.assertEqual({o.name for o in obj.children},nomes)
        self.assertFalse(anterior.modifiers)
        self.assertEqual(len(outro.modifiers),2)
        self.assertEqual(A.resolver(obj)[0],outro)
        self.assertEqual(obj[A.CHAVE_VINCULO]['tipo'],'PISO')

    def test_destino_pequeno_recusa_antes_de_mudar_origem(self):
        obj, anterior = self.instalar()
        outro,matriz = self.apoio('PISO',(7,0,0),.1)
        antes = obj.matrix_world.copy()
        with self.assertRaises(ValueError):I.reassociar(bpy.context,obj,outro,0,matriz)
        self.assertEqual(obj.matrix_world,antes)
        self.assertIs(A.apoio_de(obj),anterior)
        self.assertEqual(len(anterior.modifiers),2);self.assertFalse(outro.modifiers)
        self.assertEqual(bpy.ops.object.cabinet_instalar(origem='Origem apagada',apoio_destino=outro.name),{'CANCELLED'})
        self.assertEqual(bpy.ops.object.cabinet_instalar(modelo='PORTA',apoio_destino=outro.name,face_destino=999),{'CANCELLED'})

    def test_excecao_no_corte_devolve_pose_vinculo_e_componentes(self):
        obj, anterior = self.instalar()
        outro,matriz = self.apoio('PISO',(7,0,0))
        antes = obj.matrix_world.copy()
        bases = {o.name:o.matrix_basis.copy() for o in obj.children}
        propriedades = dict(outro.items())
        with patch.object(I,'_recorte',side_effect=ValueError('Falha de prova')), self.assertRaises(ValueError):
            I.reassociar(bpy.context,obj,outro,0,matriz)
        self.assertEqual(obj.matrix_world,antes)
        self.assertIs(A.apoio_de(obj),anterior)
        self.assertEqual({o.name:o.matrix_basis for o in obj.children},bases)
        self.assertEqual(len(anterior.modifiers),2);self.assertFalse(outro.modifiers)
        self.assertEqual(dict(outro.items()),propriedades)
        self.assertNotIn(A.ATR_FACE,outro.data.attributes)

    def test_reassociacao_preserva_modelagem_e_energia_da_luz(self):
        obj,_=self.instalar('SPOT_SOBREPOSTO')
        luz=next(o for o in obj.children if o.type=='LIGHT')
        luz.data.energy=37
        malha=next(o.data for o in obj.children if o.type=='MESH')
        malha.vertices[0].co.x += .003
        antes=[tuple(v.co) for v in malha.vertices]
        apoio,matriz=self.apoio('PISO',(7,0,0))
        I.reassociar(bpy.context,obj,apoio,0,matriz)
        self.assertEqual(luz.data.energy,37)
        self.assertEqual([tuple(v.co) for v in malha.vertices],antes)

    def test_soltar_esquerdo_cria_e_soltar_direito_reassocia_sem_duplicar(self):
        parede,matriz=self.apoio()
        piso,outra=self.apoio('PISO',(7,0,0))
        def soltar(op,apoio,quadro,botao):
            evento=SimpleNamespace(type=botao,value='RELEASE',mouse_x=self.regiao.x+100,mouse_y=self.regiao.y+100)
            normal=quadro.to_3x3().col[2];ponto=quadro.translation
            with bpy.context.temp_override(area=self.area,region=self.regiao), \
                 patch.object(P,'raio_ate_parede',return_value=(apoio,ponto,normal,0)), \
                 patch.object(I.view3d_utils,'region_2d_to_origin_3d',return_value=ponto+normal*4), \
                 patch.object(I.view3d_utils,'region_2d_to_vector_3d',return_value=-normal):
                self.assertEqual(I.OBJECT_OT_instalar.modal(op,bpy.context,evento),{'FINISHED'})
        soltar(self.operador(),parede,matriz,'LEFTMOUSE')
        obj=next(o for o in bpy.context.scene.objects if A.MARCA in o)
        nome=obj.name;uid=obj[I.IDENTIDADE]
        soltar(self.operador('SPOT_SOBREPOSTO',nome,True),piso,outra,'RIGHTMOUSE')
        self.assertEqual([o.name for o in bpy.context.scene.objects if A.MARCA in o],[nome])
        self.assertEqual(bpy.data.objects[nome][I.IDENTIDADE],uid)
        self.assertIs(A.apoio_de(bpy.data.objects[nome]),piso)
        self.assertIsNone(I._previa[0])

    def test_clique_direito_na_peca_usa_mesmo_posicionador(self):
        obj,_ = self.instalar('SPOT_SOBREPOSTO')
        peca = next(o for o in obj.children if o.type=='MESH')
        evento = SimpleNamespace(mouse_region_x=100,mouse_region_y=100)
        instalar = Mock(return_value={'RUNNING_MODAL'})
        with patch.object(addon.paredes_edicao,'lembrar_face'), \
             patch.object(addon.hud,'_raio_cru',return_value=(peca,None,None,None,None)), \
             patch.object(P,'bpy',SimpleNamespace(ops=SimpleNamespace(object=SimpleNamespace(cabinet_instalar=instalar)))):
            resultado = P.OBJECT_OT_arrastar_na_parede.invoke(SimpleNamespace(),bpy.context,evento)
        self.assertEqual(resultado,{'CANCELLED'})
        instalar.assert_called_once_with('INVOKE_DEFAULT',modelo='SPOT_SOBREPOSTO',origem=obj.name,arrastar=True,direito=True)

    def test_cartao_inicia_arraste_na_origem_sem_ponte_de_comando(self):
        acao = ('escolha','modelo_instalacao','PENDENTE',False,True,I.ALVO)
        evento = SimpleNamespace(type='LEFTMOUSE',mouse_region_x=30,mouse_region_y=30)
        instalar = Mock(return_value={'RUNNING_MODAL'})
        E = addon.gaveta_eventos
        with patch.object(addon.gaveta,'_widgets_interativos',return_value=[(0,0,100,100,"Pendant light",acao)]), \
             patch.object(E,'bpy',SimpleNamespace(data=bpy.data,ops=SimpleNamespace(object=SimpleNamespace(cabinet_instalar=instalar)))), \
             patch.object(E._editor,'executar') as ponte:
            with bpy.context.temp_override(area=self.area,region=self.regiao):
                self.assertEqual(E.OBJECT_OT_interagir_gaveta.invoke(SimpleNamespace(),bpy.context,evento),{'FINISHED'})
        instalar.assert_called_once_with('INVOKE_DEFAULT',modelo='PENDENTE',arrastar=True)
        ponte.assert_not_called()

    def test_reassocia_entre_faces_do_mesmo_objeto(self):
        bpy.ops.mesh.primitive_cube_add(size=8)
        apoio=bpy.context.object;apoio[P.CHAVE_ALVENARIA]=True
        indice=next(f.index for f in apoio.data.polygons if f.normal.y < -.99)
        obj=I.instalar(bpy.context,'PORTA',apoio,indice,A.referencial((0,-4,0),(0,-1,0)))
        destino=next(f.index for f in apoio.data.polygons if f.normal.z > .99)
        I.reassociar(bpy.context,obj,apoio,destino,A.referencial((0,0,4),(0,0,1)))
        resolvido=A.resolver(obj)
        self.assertEqual(resolvido[2],destino)
        self.assertEqual(obj[A.CHAVE_VINCULO]['tipo'],'PISO')
        self.assertEqual(len(apoio.modifiers),1)

    def test_olho_tambem_respeita_desfazer_refazer(self):
        apoio,_=self.apoio();nome=apoio.name
        bpy.context.preferences.edit.use_global_undo=True
        with bpy.context.temp_override(area=self.area,region=self.regiao):
            bpy.ops.ed.undo_push(message='Tipos ocultos')
            bpy.ops.object.cabinet_visualizar_alvenaria()
            bpy.ops.ed.undo_push(message='Tipos visiveis')
            bpy.ops.ed.undo();addon.eventos._fim_do_desfazer();A.verificar()
            self.assertFalse(bpy.context.scene.get(A.CHAVE_VISUAL,False))
            self.assertFalse(A._visuais[0])
            bpy.ops.ed.redo();addon.eventos._fim_do_desfazer();A.verificar()
            self.assertTrue(bpy.context.scene.get(A.CHAVE_VISUAL))
            self.assertIn(nome,A._visuais[0])

    def test_salvar_reabrir_preserva_apoio_tipo_e_visualizacao(self):
        obj,apoio=self.instalar('SPOT_SOBREPOSTO','PISO')
        nome,base=obj.name,apoio.name
        bpy.context.scene[A.CHAVE_VISUAL]=True
        with tempfile.TemporaryDirectory() as pasta:
            arquivo=os.path.join(pasta,'Instalacoes.blend')
            bpy.ops.wm.save_as_mainfile(filepath=arquivo)
            bpy.ops.wm.open_mainfile(filepath=arquivo)
        addon.eventos._fim_do_desfazer();A.verificar()
        self.assertEqual(A.apoio_de(bpy.data.objects[nome]).name,base)
        self.assertEqual(bpy.data.objects[nome][A.CHAVE_VINCULO]['tipo'],'PISO')
        self.assertTrue(bpy.context.scene[A.CHAVE_VISUAL])
        self.assertIn(base,A._visuais[0])

    def test_undo_redo_da_insercao_e_troca_de_face_restauram_cortes(self):
        origem,_ = self.apoio()
        destino,_ = self.apoio('PISO',(7,0,0))
        nomes = origem.name,destino.name
        bpy.context.preferences.edit.use_global_undo=True
        with bpy.context.temp_override(area=self.area,region=self.regiao):
            bpy.ops.ed.undo_push(message='Antes da instalacao')
            self.assertEqual(bpy.ops.object.cabinet_instalar('EXEC_DEFAULT',modelo='PORTA',apoio_destino=nomes[0],
                face_destino=0,ponto_destino=(0,0,0),normal_destino=(0,-1,0)),{'FINISHED'})
            obj=next(o for o in bpy.context.scene.objects if o.get(A.MARCA)=='PORTA');nome=obj.name
            uid=obj[I.IDENTIDADE]
            bpy.ops.ed.undo_push(message='Instalacao na parede')
            self.assertEqual(bpy.ops.object.cabinet_instalar('EXEC_DEFAULT',origem=nome,apoio_destino=nomes[1],
                face_destino=0,ponto_destino=(7,0,0),normal_destino=(0,0,1)),{'FINISHED'})
            bpy.ops.ed.undo_push(message='Instalacao no piso')
            bpy.ops.ed.undo();addon.eventos._fim_do_desfazer()
            A.verificar();I.verificar()
            self.assertEqual(A.apoio_de(bpy.data.objects[nome]).name,nomes[0])
            self.assertEqual(len(bpy.data.objects[nomes[0]].modifiers),2)
            self.assertFalse(bpy.data.objects[nomes[1]].modifiers)
            bpy.ops.ed.redo();addon.eventos._fim_do_desfazer()
            A.verificar();I.verificar()
            self.assertEqual(A.apoio_de(bpy.data.objects[nome]).name,nomes[1])
            self.assertEqual(bpy.data.objects[nome][I.IDENTIDADE],uid)
            bpy.ops.ed.undo();addon.eventos._fim_do_desfazer()
            bpy.ops.ed.undo();addon.eventos._fim_do_desfazer()
            self.assertNotIn(nome,bpy.data.objects)
            self.assertFalse(bpy.data.objects[nomes[0]].modifiers)
            bpy.ops.ed.redo();addon.eventos._fim_do_desfazer()
            self.assertIn(nome,bpy.data.objects)


with tempfile.TemporaryDirectory(prefix='instalacoes_') as pasta, \
     patch.object(addon.opcoes,'_pasta_addon',return_value=pasta), \
     patch.object(addon.biblioteca,'pasta_biblioteca',return_value=pasta):
    addon.register()
    try:
        resultado=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestInstalacoes))
    finally:addon.unregister()
    if not resultado.wasSuccessful():raise RuntimeError("Installation tests failed")
