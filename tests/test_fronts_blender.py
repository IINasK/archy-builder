"""Invariantes independentes da referencia geometrica LOCAL das frentes.

Execute no Blender com --background --factory-startup --python-exit-code 1.
Fixtures proprias: nenhuma leitura ou escrita da biblioteca real.
"""
import math
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon


class ContagemSemVarredura:
    def __init__(self, colecao):
        self.colecao = colecao

    def __len__(self):
        return len(self.colecao)

    def __iter__(self):
        raise AssertionError('Redraw iterou geometria')

    def __getitem__(self, chave):
        raise AssertionError('Redraw leu geometria')

    def foreach_get(self, *args):
        raise AssertionError('Redraw copiou geometria')


class DadosSemVarredura:
    def __init__(self, malha):
        self.malha = malha

    def __getattr__(self, nome):
        if nome in ('vertices', 'edges', 'polygons', 'loops', 'loop_triangles'):
            return ContagemSemVarredura(getattr(self.malha, nome))
        if nome == 'calc_loop_triangles':
            raise AssertionError('Redraw triangulou malha')
        return getattr(self.malha, nome)

    def get(self, *args):
        return self.malha.get(*args)

    def __contains__(self, chave):
        return chave in self.malha

    def __getitem__(self, chave):
        return self.malha[chave]


class SemMalha:
    """Permite ID props e pose; qualquer consulta geometrica reprova o redraw."""
    def __init__(self, objeto):
        self.objeto = objeto

    def __getattr__(self, nome):
        if nome == 'data':
            return DadosSemVarredura(self.objeto.data)
        if nome in ('bound_box', 'evaluated_get', 'to_mesh',
                    'closest_point_on_mesh', 'ray_cast'):
            raise AssertionError('Redraw consultou malha: ' + nome)
        return getattr(self.objeto, nome)

    def get(self, *args):
        return self.objeto.get(*args)

    def __contains__(self, chave):
        return chave in self.objeto

    def __getitem__(self, chave):
        return self.objeto[chave]


class TestFrentes(unittest.TestCase):
    def test_instancia_fora_do_edit_mode_nao_escreve_mesh_em_edicao(self):
        obj=self.chapa();clone=obj.copy();clone.data=obj.data
        bpy.context.scene.collection.objects.link(clone);self.objetos.append(clone)
        for o in bpy.context.selected_objects:o.select_set(False)
        obj.select_set(True);bpy.context.view_layer.objects.active=obj
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            self.assertEqual(clone.mode,'OBJECT');self.assertTrue(clone.data.is_editmode)
            with patch.object(self.api.bmesh,'new',side_effect=AssertionError('Leu/escreveu Mesh de outra instancia em edicao')):
                self.assertIsNone(self.api.preparar(clone,forcar=True))
        finally:bpy.ops.object.mode_set(mode='OBJECT')

    def setUp(self):
        self.api = addon.frentes
        self.objetos = []
        self.malhas = []

    def tearDown(self):
        for obj in self.objetos:
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        for malha in self.malhas:
            if malha.users == 0:
                bpy.data.meshes.remove(malha)

    def vetor(self, atual, esperado, tolerancia=2e-6):
        self.assertLessEqual((Vector(atual) - Vector(esperado)).length,
                             tolerancia, (tuple(atual), tuple(esperado)))

    def linha(self, atual, esperado):
        self.assertEqual(len(atual), len(esperado))
        for a, b in zip(atual, esperado):
            self.vetor(a, b)

    def geometria(self, linha, altura=.8, espessura=.018):
        # Frente +Z; as quatro linhas tem a MESMA ordem de X crescente.
        frente = [Vector((x, -altura / 2, z)) for x, z in linha]
        tras = [p - Vector((0, 0, espessura)) for p in frente]
        cima = Vector((0, altura, 0))
        pontos = frente + tras + [p + cima for p in frente + tras]
        n = len(frente)
        faces = []
        for i in range(n - 1):
            faces.extend(((i, i+1, 2*n+i+1, 2*n+i),
                          (n+i, 3*n+i, 3*n+i+1, n+i+1),
                          (i, n+i, n+i+1, i+1),
                          (2*n+i, 2*n+i+1, 3*n+i+1, 3*n+i)))
        faces.extend(((0, 2*n, 3*n, n),
                      (n-1, 2*n-1, 4*n-1, 3*n-1)))
        return pontos, faces

    def chapa(self, linha=None):
        linha = linha or [(-.3, .009), (.3, .009)]
        pontos, faces = self.geometria(linha)
        malha = bpy.data.meshes.new('Frente teste')
        malha.from_pydata(pontos, [], faces)
        malha.update()
        obj = bpy.data.objects.new('Chapa teste frente', malha)
        bpy.context.scene.collection.objects.link(obj)
        obj[addon.chapas.MARCA_CHAPA] = True
        obj['eh_folha_porta'] = True
        addon.chapas._ocupado[0] = True
        try:
            obj.chapa_largura_mm = (linha[-1][0] - linha[0][0]) * 1000
            obj.chapa_comprimento_mm = 800
            obj.chapa_espessura_mm = 18
        finally:
            addon.chapas._ocupado[0] = False
        self.objetos.append(obj)
        self.malhas.append(malha)
        bpy.context.view_layer.update()
        return obj

    def conferir_referencia(self, obj, linha):
        self.api.preparar(obj, forcar=True)
        ref = self.api.referencia(obj)
        self.assertIsNotNone(ref)
        baixo = [Vector((x, -.4, z)) for x, z in linha]
        self.linha(ref['frente'], baixo)
        self.linha(ref['tras'], [p - Vector((0, 0, .018)) for p in baixo])
        self.linha(ref['cima_frente'], [p + Vector((0, .8, 0)) for p in baixo])
        self.linha(ref['cima_tras'], [p + Vector((0, .8, -.018)) for p in baixo])
        self.assertAlmostEqual(ref['altura'], .8, places=6)
        comprimento = sum((b-a).length for a, b in zip(baixo, baixo[1:]))
        self.assertAlmostEqual(ref['comprimento'], comprimento, places=6)
        return ref

    # Regressao corrigida (era BUG): A API combinada devolve dict; implementacao devolve IDPropertyGroup.
    def test_contrato_referencia_devolve_dict(self):
        obj = self.chapa()
        self.api.preparar(obj, forcar=True)
        self.assertIsInstance(self.api.referencia(obj), dict)

    def test_caixa_referencia_local_e_medidas_reais(self):
        obj = self.chapa()
        self.conferir_referencia(obj, [(-.3, .009), (.3, .009)])

    # Regressao corrigida (era BUG): Tampas estreitas entram no percurso da polilinha.
    def test_polilinha_dobrada_nao_vira_corda_ou_envelope(self):
        linha = [(-.3, .009), (-.1, .15), (.3, .009)]
        self.conferir_referencia(self.chapa(linha), linha)

    # Regressao corrigida (era BUG): Extracao inclui as tampas estreitas no percurso da frente.
    def test_arco_preserva_todas_as_quebras_e_comprimento(self):
        linha = [(.3 * math.sin(t), .009 + .3 * math.cos(t))
                 for t in [-1.0, -.6, -.2, .2, .6, 1.0]]
        self.conferir_referencia(self.chapa(linha), linha)

    def test_pose_abertura_e_troca_do_lado_nao_mudam_referencia_local(self):
        obj = self.chapa([(-.3, .009), (0, .13), (.3, .009)])
        self.api.preparar(obj, forcar=True)
        antes = [Vector(p) for p in self.api.referencia(obj)['frente']]
        bordas = self.api.bordas(obj)
        for angulo in (.7, -.7, 0):
            obj.matrix_world = (Matrix.Translation((1.2, -.8, .6))
                                @ Matrix.Rotation(angulo, 4, 'Y')
                                @ Matrix.Rotation(.4, 4, 'Z'))
            bpy.context.view_layer.update()
            self.linha(self.api.referencia(obj)['frente'], antes)
            depois = self.api.bordas(obj)
            self.assertEqual(set(depois), set(bordas))
            for chave, (a, b) in bordas.items():
                self.vetor(depois[chave][0], obj.matrix_world @ a)
                self.vetor(depois[chave][1], obj.matrix_world @ b)
        self.assertEqual(tuple(obj.scale), (1, 1, 1))

    # Regressao corrigida (era BUG): Segmentos extras das tampas alteram a fracao do percurso.
    def test_segmento_normaliza_por_comprimento_real(self):
        linha = [(-.3, .009), (-.1, .159), (.3, .159)]
        obj = self.chapa(linha)
        self.api.preparar(obj, forcar=True)
        ds = [math.hypot(b[0]-a[0], b[1]-a[1]) for a, b in zip(linha, linha[1:])]
        for borda in ('Y-', 'Y+'):
            for i in range(2):
                for fracao in (0, .25, 1):
                    nome, global_ = self.api.normalizar_borda(obj, borda+'|'+str(i), fracao)
                    self.assertEqual(nome, borda)
                    self.assertAlmostEqual(global_, (sum(ds[:i])+ds[i]*fracao)/sum(ds), places=6)

    def test_lugar_caixa_mm_recuo_e_normal_das_duas_faces(self):
        obj = self.chapa()
        self.api.preparar(obj, forcar=True)
        for face in (1, -1):
            for borda in ('X-', 'X+', 'Y-', 'Y+'):
                matriz, comprimento = self.api.lugar(obj, borda, face, .5, 148, 40)
                self.assertIsInstance(matriz, Matrix)
                self.assertAlmostEqual(comprimento, 148)
                eixo = 0 if borda[0] == 'X' else 1
                sinal = 1 if borda[1] == '+' else -1
                esperado = Vector((0, 0, face*.009))
                esperado[eixo] = sinal*((.3 if eixo == 0 else .4)-.04)
                self.vetor(matriz.translation, esperado)
                self.vetor(matriz.to_3x3().col[2], (0, 0, face))
                self.assertAlmostEqual(matriz.to_3x3().determinant(), 1, places=5)

    # Regressao corrigida (era BUG): Expansao da frente inclui tampas e diverge do verso.
    def test_verso_e_topo_seguem_superficies_distintas(self):
        obj = self.chapa([(-.3, .009), (0, .12), (.3, .009)])
        self.api.preparar(obj, forcar=True)
        frente, verso = self.api.bordas(obj, 1), self.api.bordas(obj, -1)
        self.assertEqual(set(frente), set(verso))
        for chave in frente:
            # O verso pode inverter a ordem da ancora sem mudar sua geometria.
            correspondentes = [b+Vector((0,0,.018)) for b in verso[chave]]
            for a in frente[chave]:
                self.vetor(a, min(correspondentes, key=lambda b:(a-b).length))
        baixo, cima = self.api.perfil(obj)
        self.assertEqual(len(baixo), 3)
        for a, b in zip(baixo, cima):
            self.vetor(b-a, (0, .8, 0))

    def test_resize_ida_volta_preserva_malha_pose_e_referencia(self):
        obj = self.chapa([(-.3, .009), (0, .12), (.3, .009)])
        self.api.preparar(obj, forcar=True)
        original = [v.co.copy() for v in obj.data.vertices]
        esperado = [Vector(p) for p in self.api.referencia(obj)['frente']]
        malha = obj.data
        obj.matrix_world = Matrix.Translation((2, 3, 4)) @ Matrix.Rotation(.8, 4, 'Z')
        pose = obj.matrix_world.copy()
        for fator in (.37, 1):
            bm = bmesh.new()
            try:
                bm.from_mesh(malha)
                for v, p in zip(bm.verts, original):
                    v.co = Vector((p.x*fator, p.y*fator, p.z))
                bm.to_mesh(malha)
            finally:
                bm.free()
            malha.update()
            self.api.preparar(obj, forcar=True)
        self.assertIs(obj.data, malha)
        self.linha(self.api.referencia(obj)['frente'], esperado)
        for a, b in zip(obj.matrix_world, pose):
            self.assertLess((a-b).length, 1e-6)

    # Regressao corrigida (era BUG): Reconhecimento apos recriar inclui tampas estreitas na frente.
    def test_edicao_topologica_reordena_vertices_e_acrescenta_quebra(self):
        obj = self.chapa()
        self.api.preparar(obj, forcar=True)
        linha = [(-.3, .009), (-.07, .16), (.3, .009)]
        pontos, faces = self.geometria(linha)
        # Recria na MESMA Mesh, com indices invertidos e numero diferente.
        n = len(pontos)
        obj.data.clear_geometry()
        obj.data.from_pydata(list(reversed(pontos)), [],
                             [tuple(n-1-i for i in face) for face in faces])
        obj.data.update()
        self.conferir_referencia(obj, linha)

    # Regressao corrigida (era BUG): Trecho horizontal no Y minimo descarta a ponta recortada.
    def test_recorte_inferior_preserva_ponta_e_nao_encurta_caminho(self):
        obj = self.chapa([(-.3, .009), (-.1, .009), (.3, .009)])
        self.api.preparar(obj, forcar=True)
        # Levanta apenas a quina esquerda inferior nas duas superficies.
        for v in obj.data.vertices:
            if v.co.x < -.29 and v.co.y < 0:
                v.co.y += .1
        obj.data.update()
        self.api.preparar(obj, forcar=True)
        ref = self.api.referencia(obj)
        self.linha(ref['frente'], [(-.3, -.3, .009), (-.1, -.4, .009), (.3, -.4, .009)])
        self.linha(ref['cima_frente'], [(-.3, .4, .009), (-.1, .4, .009), (.3, .4, .009)])

    def test_tag_semantica_sobrevive_triangulacao_nativa(self):
        obj = self.chapa([(-.3, .009), (-.08, .16), (.3, .009)])
        self.api.preparar(obj, forcar=True)
        esperado = [Vector(p) for p in self.api.referencia(obj)['frente']]
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            bmesh.ops.triangulate(bm, faces=list(bm.faces))
            bm.to_mesh(obj.data)
        finally:
            bm.free()
        obj.data.update()
        self.api.preparar(obj, forcar=True)
        self.linha(self.api.referencia(obj)['frente'], esperado)
        atributo = obj.data.attributes.get(self.api.ATR_FACE)
        self.assertIsNotNone(atributo)
        self.assertIn(1, [d.value for d in atributo.data])
        self.assertIn(-1, [d.value for d in atributo.data])

    def test_perfil_fechado_independe_da_pose_de_abertura(self):
        obj = self.chapa()
        grupo = bpy.data.objects.new('Grupo teste frente', None)
        bpy.context.scene.collection.objects.link(grupo)
        self.objetos.append(grupo)
        grupo.matrix_world = Matrix.Translation((2, 3, 4)) @ Matrix.Rotation(.3, 4, 'Z')
        obj.parent = grupo
        obj['porta_centro_mm'] = (100., 200., 300.)
        self.api.preparar(obj, forcar=True)
        ref = self.api.referencia(obj)
        fechada = grupo.matrix_world @ Matrix.Translation((.1, .2, .3))
        for angulo in (.7, -.7):
            obj.matrix_basis = Matrix.Translation((.1, .2, .3)) @ Matrix.Rotation(angulo, 4, 'Y')
            bpy.context.view_layer.update()
            baixo, cima = self.api.perfil(obj, fechada=True)
            self.linha(baixo, [fechada @ Vector(v) for v in ref['frente']])
            self.linha(cima, [fechada @ Vector(v) for v in ref['cima_frente']])
            atual, _ = self.api.perfil(obj)
            self.linha(atual, [obj.matrix_world @ Vector(v) for v in ref['frente']])

    def test_contorno_tem_indices_validos_e_nao_tem_diagonais_de_face(self):
        obj = self.chapa()
        self.api.preparar(obj, forcar=True)
        pontos, pares = self.api.contorno(obj)
        self.assertTrue(pontos)
        self.assertTrue(pares)
        for a, b in pares:
            self.assertTrue(0 <= a < len(pontos) and 0 <= b < len(pontos))
            diferenca = pontos[a]-pontos[b]
            self.assertEqual(sum(abs(c) > 1e-6 for c in diferenca), 1)

    def test_redraw_sem_referencia_nao_consulta_malha(self):
        obj = self.chapa()
        protegido = SemMalha(obj)
        with patch.object(self.api, 'preparar', side_effect=AssertionError('Redraw preparou referencia')):
            self.assertIsNone(self.api.referencia(protegido))
            self.assertIsNone(self.api.perfil(protegido))
            self.assertIsNone(self.api.contorno(protegido))
            self.assertFalse(self.api.bordas(protegido))

    # Regressao corrigida (era BUG): Renomear escapa da pendencia por nome.
    def test_invalidacao_sobrevive_renomear_objeto(self):
        obj = self.chapa()
        self.api.preparar(obj, forcar=True)
        self.api.invalidar(obj)
        obj.name = 'Chapa teste renomeada'
        self.assertIsNone(self.api.referencia(obj))

    # Regressao corrigida (era BUG): Cache da Mesh e invalidado somente pelo nome de um objeto.
    def test_invalidacao_cobre_usuarios_da_mesma_mesh(self):
        obj = self.chapa()
        copia = obj.copy()
        bpy.context.scene.collection.objects.link(copia)
        self.objetos.append(copia)
        self.api.preparar(obj, forcar=True)
        self.api.invalidar(obj)
        self.assertIsNone(self.api.referencia(copia))

    def test_redraw_invalidado_nao_consulta_malha(self):
        obj = self.chapa()
        self.api.preparar(obj, forcar=True)
        self.api.invalidar(obj)
        protegido = SemMalha(obj)
        with patch.object(self.api, 'preparar', side_effect=AssertionError('Redraw preparou referencia')):
            self.assertIsNone(self.api.referencia(protegido))
            self.assertIsNone(self.api.perfil(protegido))
            self.assertIsNone(self.api.contorno(protegido))
            self.assertFalse(self.api.bordas(protegido))

    # Regressao: bordas X conservam o centro Y real da geometria.
    def test_lugar_preserva_origem_local_nao_centrada(self):
        obj = self.chapa()
        deslocamento = Vector((.12, .23, .017))
        for v in obj.data.vertices:
            v.co += deslocamento
        obj.data.update()
        self.api.preparar(obj, forcar=True)
        for borda in ('X-', 'X+', 'Y-', 'Y+'):
            matriz, _ = self.api.lugar(obj, borda, 1, .5, 148, 40)
            eixo = 0 if borda[0] == 'X' else 1
            sinal = 1 if borda[1] == '+' else -1
            esperado = deslocamento + Vector((0, 0, .009))
            esperado[eixo] += sinal*((.3 if eixo == 0 else .4)-.04)
            self.vetor(matriz.translation, esperado)

    def test_fracao_legada_caixa_migra_uma_vez_sem_mover_ancora(self):
        obj = self.chapa()
        for borda in ('Y-', 'Y+'):
            for face in (1, -1):
                pux = bpy.data.objects.new('Puxador teste legado', None)
                bpy.context.scene.collection.objects.link(pux)
                self.objetos.append(pux)
                pux.parent = obj
                pux['eh_puxador'] = True
                pux['puxador_borda'] = borda
                pux['puxador_face'] = face
                pux['puxador_fracao'] = .25
        self.api.preparar(obj, forcar=True)
        for pux in obj.children:
            borda, face = pux['puxador_borda'], pux['puxador_face']
            sinal = 1 if borda == 'Y+' else -1
            matriz, _ = self.api.lugar(obj, borda, face,
                                      pux['puxador_fracao'], 148, 40)
            self.vetor(matriz.translation, (.15*sinal*face, sinal*.36, face*.009))
            fracao = pux['puxador_fracao']
            self.api.preparar(obj, forcar=True)
            self.assertEqual(pux['puxador_fracao'], fracao)
            self.assertEqual(pux['puxador_referencia_versao'], 1)

    def test_corte_perfil_separa_madeira_real_e_borda_de_montagem(self):
        obj = self.chapa()
        for v in obj.data.vertices:
            if v.co.y > 0:
                v.co.y -= .03
        obj.data.update()
        obj['chapa_rebaixos'] = 'Y+'
        self.api.preparar(obj, forcar=True)
        baixo, cima = self.api.perfil(obj)
        self.assertTrue(all(abs(p.y-.37)<1e-6 for p in cima))
        for chave, par in self.api.bordas(obj).items():
            if chave.startswith('Y+'):
                self.assertTrue(all(abs(p.y-.4)<1e-6 for p in par))
        pontos, _ = self.api.contorno(obj)
        self.assertLessEqual(max(p.y for p in pontos), .370001)
        matriz, comprimento = self.api.lugar(obj, 'Y+', 1, .5, 0, 0, inteiro=True)
        self.vetor(matriz.translation, (0, .4, .009))
        self.assertAlmostEqual(comprimento, 600, places=4)

    def test_invalidar_renomear_mesh_reprepara_fora_do_redraw(self):
        obj = self.chapa()
        self.api.preparar(obj, forcar=True)
        for v in obj.data.vertices:
            v.co.z += .01
        obj.data.update()
        self.api.invalidar(obj)
        obj.data.name = 'Malha teste renomeada'
        self.assertIsNone(self.api.referencia(obj))
        # Um tique descobre o nome antigo; o seguinte reexamina a cena.
        self.api.processar_pendentes()
        self.api.processar_pendentes()
        ref = self.api.referencia(obj)
        self.assertIsNotNone(ref)
        self.linha(ref['frente'], [(-.3, -.4, .019), (.3, -.4, .019)])

    def test_quadro_e_painel_desconectados_preservam_bordas_externas(self):
        obj = self.chapa()
        bm = bmesh.new()
        caixas = ((-.3, -.277, -.4, .4, -.005, .005),
                  (.277, .3, -.4, .4, -.005, .005),
                  (-.277, .277, -.4, -.377, -.005, .005),
                  (-.277, .277, .377, .4, -.005, .005),
                  (-.277, .277, -.377, .377, -.0025, .0025))
        try:
            for limites in caixas:
                cubo = bmesh.ops.create_cube(bm, size=1)
                for v in cubo['verts']:
                    v.co = Vector(tuple(limites[2*i+(1 if v.co[i]>0 else 0)]
                                        for i in range(3)))
            # Cinco solidos sem vertices soldados, incluindo o vidro maior.
            obj.data.clear_geometry()
            bm.to_mesh(obj.data)
        finally:
            bm.free()
        obj.data.update()
        self.api.preparar(obj, forcar=True)
        ref = self.api.referencia(obj)
        self.assertIsNotNone(ref)
        self.assertAlmostEqual(ref['comprimento'], .6, places=6)
        self.assertAlmostEqual(ref['altura'], .8, places=6)
        for nome, y, z in (('frente', -.4, .005), ('tras', -.4, -.005),
                           ('cima_frente', .4, .005), ('cima_tras', .4, -.005)):
            linha = ref[nome]
            self.vetor(linha[0], (-.3, y, z))
            self.vetor(linha[-1], (.3, y, z))
            self.assertTrue(all(abs(v[1]-y)<1e-6 and abs(v[2]-z)<1e-6 for v in linha))
        papeis = [d.value for d in obj.data.attributes[self.api.ATR_FACE].data]
        self.assertEqual(papeis.count(1), 5)
        self.assertEqual(papeis.count(-1), 5)
        for borda in ('Y-', 'Y+'):
            _, comprimento = self.api.lugar(obj, borda, 1, .5, 0, 0, inteiro=True)
            self.assertAlmostEqual(comprimento, 600, places=4)

    # Regressao corrigida: tampas radiais nao pertencem ao patch do verso.
    def test_curva_espessura_normal_nao_inclui_tampas_no_verso(self):
        angulos = (-.8, -.4, 0, .4, .8)
        raio, espessura = .6, .018
        frente = [Vector((raio*math.sin(t), -.4, raio*math.cos(t))) for t in angulos]
        # Intersecao dos planos deslocados: cada face tem 18 mm na normal.
        raio_interno = raio-espessura/math.cos((angulos[1]-angulos[0])/2)
        tras = [Vector((raio_interno*math.sin(t), -.4,
                        raio_interno*math.cos(t))) for t in angulos]
        _, faces = self.geometria([(p.x,p.z) for p in frente])
        pontos = frente+tras+[p+Vector((0,.8,0)) for p in frente+tras]
        obj = self.chapa()
        obj.data.clear_geometry()
        obj.data.from_pydata(pontos, [], faces)
        obj.data.update()
        self.api.preparar(obj, forcar=True)
        ref = self.api.referencia(obj)
        self.assertIsNotNone(ref)
        self.linha(ref['frente'], frente)
        self.linha(ref['tras'], tras)
        self.linha(ref['cima_frente'], [p+Vector((0,.8,0)) for p in frente])
        self.linha(ref['cima_tras'], [p+Vector((0,.8,0)) for p in tras])
        for i,(a,b) in enumerate(zip(angulos,angulos[1:])):
            normal = Vector((math.sin((a+b)/2),0,math.cos((a+b)/2)))
            self.assertAlmostEqual((Vector(ref['frente'][i])-Vector(ref['tras'][i])).dot(normal),
                                   espessura, places=6)
        papeis = [d.value for d in obj.data.attributes[self.api.ATR_FACE].data]
        # As duas tampas radiais fecham o solido; nao sao frente nem verso.
        self.assertEqual(papeis[-2:], [0,0])
        self.assertEqual(papeis.count(1), len(angulos)-1)
        self.assertEqual(papeis.count(-1), len(angulos)-1)

    def test_triangulacao_antes_do_primeiro_preparo_sem_tags(self):
        obj = self.chapa()
        self.assertIsNone(obj.data.attributes.get(self.api.ATR_FACE))
        self.assertIsNone(obj.data.get(self.api.CHAVE))
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            bmesh.ops.triangulate(bm, faces=list(bm.faces))
            bm.to_mesh(obj.data)
        finally:
            bm.free()
        obj.data.update()
        self.assertIsNone(obj.data.attributes.get(self.api.ATR_FACE))
        self.conferir_referencia(obj, [(-.3,.009),(.3,.009)])
        papeis = [d.value for d in obj.data.attributes[self.api.ATR_FACE].data]
        self.assertEqual(papeis.count(1), 2)
        self.assertEqual(papeis.count(-1), 2)

    def test_superficie_sem_frente_memoriza_falha_e_retenta_so_apos_edicao(self):
        obj = self.chapa()
        obj.data.clear_geometry()
        obj.data.from_pydata([(0,-.4,-.3),(0,.4,-.3),(0,.4,.3),(0,-.4,.3)],
                             [], [(0,1,2,3)])
        obj.data.update()
        self.api.invalidar(obj)
        with patch.object(self.api.bmesh, 'new', wraps=bmesh.new) as extracoes:
            self.api.processar_pendentes()
            self.assertIsNone(self.api.referencia(obj))
            self.assertFalse(obj.data[self.api.CHAVE]['valida'])
            self.assertNotIn(obj.data.name, self.api._pendentes)
            feitas = extracoes.call_count
            self.assertGreater(feitas, 0)
            for _ in range(3):
                self.api.processar_pendentes()
                self.assertIsNone(self.api.preparar(obj))
            self.assertEqual(extracoes.call_count, feitas)
            rotacao = Matrix.Rotation(-math.pi/2, 3, 'Y')
            for v in obj.data.vertices:
                v.co = rotacao @ v.co
            obj.data.update()
            self.api.invalidar(obj)
            self.api.processar_pendentes()
            self.assertGreater(extracoes.call_count, feitas)
            self.assertIsNotNone(self.api.referencia(obj))

    def test_puxador_maior_que_borda_centraliza_sem_encolher_modelo(self):
        obj = self.chapa()
        self.api.preparar(obj, forcar=True)
        for borda in ('Y-', 'Y+'):
            sinal = 1 if borda == 'Y+' else -1
            for face in (1, -1):
                for fracao in (0, .25, .5, .75, 1):
                    matriz, comprimento = self.api.lugar(
                        obj, borda, face, fracao, 900, 40)
                    self.vetor(matriz.translation, (0, sinal*.36, face*.009))
                    self.assertAlmostEqual(comprimento, 900, places=6)

    def test_redraw_com_cache_nao_consulta_malha(self):
        obj = self.chapa()
        self.api.preparar(obj, forcar=True)
        protegido = SemMalha(obj)
        with patch.object(self.api, 'preparar', side_effect=AssertionError('Redraw preparou referencia')):
            self.assertIsNotNone(self.api.referencia(protegido))
            self.assertTrue(self.api.bordas(protegido))
            self.assertIsNotNone(self.api.perfil(protegido))
            self.assertIsNotNone(self.api.contorno(protegido))


# Redireciona ANTES do register: nem timers podem tocar a biblioteca real.
with tempfile.TemporaryDirectory(prefix='cabinet_frentes_') as pasta:
    with patch.object(addon.biblioteca, 'pasta_biblioteca', return_value=pasta), \
         patch.object(addon.opcoes, '_pasta_addon', return_value=pasta):
        addon.register()
        try:
            resultado = unittest.TextTestRunner(verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(TestFrentes))
        finally:
            addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de frentes')
