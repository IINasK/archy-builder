"""Run: blender --background --factory-startup --python-exit-code 1 --python tests/test_doors_blender.py"""
import math
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon


def folga_reta():
    """Minimum clearance (mm) from a full-overlay door to the cabinet, taken from the user's rig."""
    return addon.ferragens._dados_dobradica_reta()['folga_modulo_mm']


def parametros(**alteracoes):
    p = dict(abertura='GIRO', folhas=1, dobradica='RETA',
             espessura_mm=18.0, lateral_mm=18.0, folga_mm=0.0,
             entre_folhas_mm=2.0, afastamento_mm=0.0,
             recuo_embutida_mm=0.0, recuo_correr_mm=30.0,
             entre_planos_mm=2.0)
    p.update(alteracoes)
    return p



def relativo(bloco):
    """Return the block with y relative to its first widget. In the Doors tab it moves down to accommodate Create Doors at the top (Epic 2.3); content and relative field positions remain identical."""
    if not bloco:
        return bloco
    y0 = bloco[0][1]
    return [(b[0], b[1] - y0) + tuple(b[2:]) for b in bloco]


class TestPortas(unittest.TestCase):
    def test_anexar_rig_com_atributo_extra_nao_compara_malhas_incompativeis(self):
        # Regression, fixed in v348: Blender 4.2's native comparator crashed when
        # given different sets of attributes.
        F = addon.ferragens
        a = F._instanciar_rig(bpy.context.scene.collection, 'RIG_COM_ATRIBUTO')
        cabeca = next(o for o in a.children_recursive if o.get('cabinet_peca') == 'cabeca')
        origem = cabeca.data.get('cabinet_origem')
        for malha in bpy.data.meshes:
            if malha.get('cabinet_origem') == origem:
                malha.attributes.new('edicao_manual', 'INT', 'POINT')
        b = F._instanciar_rig(bpy.context.scene.collection, 'RIG_SEM_ATRIBUTO')
        nova = next(o for o in b.children_recursive if o.get('cabinet_peca') == 'cabeca')
        self.assertIn('edicao_manual', cabeca.data.attributes)
        self.assertNotIn('edicao_manual', nova.data.attributes)

    def test_anexar_rig_nao_reutiliza_malha_modelada_com_a_mesma_marca_do_asset(self):
        F = addon.ferragens
        a = F._instanciar_rig(bpy.context.scene.collection, 'RIG_MODELADO')
        cabeca = next(o for o in a.children_recursive if o.get('cabinet_peca') == 'cabeca')
        original = [tuple(v.co) for v in cabeca.data.vertices]
        cabeca.data = cabeca.data.copy()
        cabeca.data.vertices[0].co.x += .005
        cabeca.data.update()
        alterada = cabeca.data
        b = F._instanciar_rig(bpy.context.scene.collection, 'RIG_ORIGINAL')
        nova = next(o for o in b.children_recursive if o.get('cabinet_peca') == 'cabeca')
        self.assertIsNot(nova.data, alterada)
        self.assertEqual([tuple(v.co) for v in nova.data.vertices], original)
        self.assertAlmostEqual(alterada.vertices[0].co.x, original[0][0] + .005)

    def test_montar_dez_rigs_carrega_asset_uma_vez_sem_cruzar_pais_ou_drivers(self):
        F = addon.ferragens
        conj = addon.modulos.criar_armario(bpy.context, 'Dez rigs', 600, 2500, 550)
        with patch.object(F, '_anexar_sem_repetir', wraps=F._anexar_sem_repetir) as anexar:
            grupo = addon.portas.porta_no_modulo(conj, folhas=2, dobradicas_qtd=5)
        self.assertEqual(sum(c.args[0] == F.ARQUIVO_DOBRADICA_RETA for c in anexar.call_args_list), 1)
        raizes = [o for o in grupo.children_recursive if o.get('cabinet_peca') == 'raiz']
        self.assertEqual(len(raizes), 10)
        for raiz in raizes:
            partes = {raiz, *raiz.children_recursive}
            outras = {o for r in raizes if r != raiz for o in [r,*r.children_recursive]}
            usuarios = bpy.data.user_map(subset=partes)
            self.assertFalse({u for us in usuarios.values() for u in us} & outras)
        folha = addon.portas._folhas_portas(grupo)[0]
        addon.ferragens._definir_abertura(bpy.context, folha, .5)
        bpy.context.view_layer.update()
        self.assertEqual(len(raizes), 10)

    def test_remover_rig_em_lote_conserva_malhas_usadas_pela_outra_dobradica(self):
        F = addon.ferragens
        a = F._instanciar_rig(bpy.context.scene.collection, 'RIG_A')
        b = F._instanciar_rig(bpy.context.scene.collection, 'RIG_B', modelo=a)
        pontos = {o.name:(o.data, [tuple(v.co) for v in o.data.vertices])
                  for o in b.children_recursive if o.type == 'MESH'}
        F._remover_ferragem(a)
        bpy.context.view_layer.update()
        for nome,(malha,coords) in pontos.items():
            self.assertIs(bpy.data.objects[nome].data, malha)
            self.assertEqual([tuple(v.co) for v in malha.vertices], coords)

    def test_atualizar_vao_reta_inalterado_nao_remonta_folhas_ou_ferragens(self):
        # Regression v345: a panel's ruler rebuilt the whole door, invalidating
        # BVHs and handles even though the opening had not changed.
        conj = addon.modulos.criar_armario(bpy.context, 'Reta mantida', 600, 800, 550)
        grupo = addon.portas.porta_no_modulo(conj)
        folha = addon.portas._folhas_portas(grupo)[0]
        addon.ferragens._definir_abertura(bpy.context, folha, .4)
        malha = folha.data
        folha.data.vertices[0].co.y += .003
        folha.data.update()
        pontos = [tuple(v.co) for v in malha.vertices]
        with patch.object(addon.portas, '_aplicar_portas', side_effect=AssertionError('Remontou vao igual')):
            addon.portas.atualizar_do_conjunto(conj)
        self.assertIs(folha.data, malha)
        self.assertEqual([tuple(v.co) for v in malha.vertices], pontos)
        self.assertAlmostEqual(folha[addon.ferragens.CHAVE_ABERTURA], .4)

    def test_atualizar_vao_reta_detecta_nova_margem_das_dobradicas(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Ferragem mudou', 600, 800, 550)
        grupo = addon.portas.porta_no_modulo(conj)
        p = addon.portas._copiar_parametros(grupo['porta_parametros'])
        p['dobradicas_margem_mm'] = 160
        grupo['porta_parametros'] = p
        with patch.object(addon.portas, '_aplicar_portas', wraps=addon.portas._aplicar_portas) as aplicar:
            addon.portas.atualizar_do_conjunto(conj)
        self.assertEqual(aplicar.call_count, 1)
        with patch.object(addon.portas, '_aplicar_portas', side_effect=AssertionError('Remontou outra vez')):
            addon.portas.atualizar_do_conjunto(conj)

    def test_atualizar_vao_reta_repoe_rig_apagado_e_atualiza_versao_antiga(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Rig incompleto', 600, 800, 550)
        grupo = addon.portas.porta_no_modulo(conj)
        raiz = next(o for o in grupo.children_recursive if o.get('cabinet_peca') == 'raiz')
        addon.ferragens._remover_ferragem(raiz)
        with patch.object(addon.portas, '_aplicar_portas', wraps=addon.portas._aplicar_portas) as aplicar:
            addon.portas.atualizar_do_conjunto(conj)
        self.assertEqual(aplicar.call_count, 1)
        raiz = next(o for o in grupo.children_recursive if o.get('cabinet_peca') == 'raiz')
        raiz['cabinet_versao'] = int(addon.ferragens._dados_dobradica_reta()['versao']) - 1
        with patch.object(addon.portas, '_aplicar_portas', wraps=addon.portas._aplicar_portas) as aplicar:
            addon.portas.atualizar_do_conjunto(conj)
        self.assertEqual(aplicar.call_count, 1)

    def test_atualizar_apoios_obliquos_conserva_remontagem_mesmo_com_vao_igual(self):
        conj = addon.modulos.criar_armario(bpy.context, 'Apoio real', 600, 800, 550)
        grupo = addon.portas.porta_no_modulo(conj)
        # The shortcut creates full coverage and resolves RETA automatically.
        p = addon.portas._copiar_parametros(grupo['porta_parametros'])
        p.update(dobradica='CURVA', dobradica_modelo_reta=False)
        grupo['porta_parametros'] = p
        with patch.object(addon.portas, '_aplicar_portas', wraps=addon.portas._aplicar_portas) as aplicar:
            addon.portas.atualizar_do_conjunto(conj)
        self.assertEqual(aplicar.call_count, 1)

    def _porta_curva_torcida(self):
        p = addon.portas._parametros_portas_da_cena(bpy.context.scene, numerico=True)
        p.update(abertura='GIRO', folhas=1, dobradica='CURVA',
                 dobradica_lado='ESQUERDA', espessura_mm=15, lateral_mm=15,
                 folga_mm=0, afastamento_mm=0, dobradicas_qtd=2,
                 cobertura_esq_e=0, cobertura_dir_e=0,
                 cobertura_baixo_e=0, cobertura_cima_e=0, respiro_original=True)
        g = addon.portas._aplicar_portas(bpy.context, None, Matrix.Identity(4),
                                        None, 320, 700, p)
        f, = addon.portas._folhas_portas(g)
        n = 17
        pontos = []
        # A slight twist puts the quad's average center outside its triangles,
        # as on the real leaf exported by Promob.
        for y in (-.35, .35):
            for raio in (.3, .315):
                for i in range(n):
                    t = i * math.pi / 32
                    x, z = -.16 + raio * math.sin(t), .3075 - raio * math.cos(t)
                    pontos.append((x + y * z * .001, y, z + y * x * .001))
        faces = []
        for i in range(n - 1):
            faces.extend(((i, i+1, 2*n+i+1, 2*n+i),
                          (n+i, 3*n+i, 3*n+i+1, n+i+1),
                          (i, n+i, n+i+1, i+1),
                          (2*n+i, 2*n+i+1, 3*n+i+1, 3*n+i)))
        faces.extend(((0, 2*n, 3*n, n), (n-1, 2*n-1, 4*n-1, 3*n-1)))
        f.data.clear_geometry()
        f.data.from_pydata(pontos, [], faces)
        f.data.update()
        f['porta_curva_modelada'] = 1
        for chave in (addon.frentes.ATR_FACE, addon.frentes.ATR_BORDA):
            atributo = f.data.attributes.get(chave)
            if atributo is not None:
                f.data.attributes.remove(atributo)
        addon.frentes.preparar(f, forcar=True)
        return g, f, n

    # Regression: the ray hit the twisted quad itself.
    def test_curva_torcida_reconhece_superficies_inteiras(self):
        g, f, n = self._porta_curva_torcida()
        ref = addon.frentes.referencia(f)
        for chave, inicio in (('frente', 0), ('tras', n),
                              ('cima_frente', 2*n), ('cima_tras', 3*n)):
            self.assertEqual(len(ref[chave]), n, chave)
            for atual, v in zip(ref[chave], list(f.data.vertices)[inicio:inicio+n]):
                self.assertLess((Vector(atual) - v.co).length, 1e-6)

    # Regression: truncated labels and caches survived preparation.
    def test_curva_recupera_cache_antigo_truncado_sem_recriar_mesh(self):
        g, f, n = self._porta_curva_torcida()
        malha = f.data
        for i, valor in enumerate(malha.attributes[addon.frentes.ATR_FACE].data):
            valor.value = 1 if i == 0 else -1 if i == 1 else 0
        rotulos = {frozenset((0, 1)): 1, frozenset((2*n, 2*n+1)): 2,
                   frozenset((n, n+1)): 3, frozenset((3*n, 3*n+1)): 4}
        for aresta, valor in zip(malha.edges, malha.attributes[addon.frentes.ATR_BORDA].data):
            valor.value = rotulos.get(frozenset(aresta.vertices), 0)
        # Simulate an old reference with a valid hash but incomplete data.
        antigo = addon.frentes.referencia(f)
        antigo.pop('amostragem_triangular', None)
        antigo['frente'] = antigo['frente'][:2]
        malha[addon.frentes.CHAVE] = antigo
        antes = [v.co.copy() for v in malha.vertices]
        ref = addon.frentes.preparar(f)
        self.assertEqual(len(ref['frente']), n)
        self.assertEqual(len(ref['tras']), n)
        self.assertEqual(f.data, malha)
        for v, esperado in zip(malha.vertices, antes):
            self.assertEqual(v.co, esperado)
        with patch.object(addon.frentes, '_faces_opostas', side_effect=AssertionError('Reextraiu cache valido')):
            self.assertEqual(addon.frentes.preparar(f), ref)

    # Regression: open-door transport inherited the truncated outline.
    def test_reancorar_curva_torcida_aberta_preserva_madeira_e_dados(self):
        g, f, n = self._porta_curva_torcida()
        malha = f.data
        uv = malha.uv_layers.new(name='UV modelada')
        for i, dado in enumerate(uv.data):
            dado.uv = (i % 7 / 7, i % 11 / 11)
        material = bpy.data.materials.new('Madeira curva teste')
        malha.materials.append(material)
        f.modifiers.new('Acabamento preservado', 'BEVEL').width = .0002
        topologia = [tuple(p.vertices) for p in malha.polygons]
        uvs = [tuple(dado.uv) for dado in uv.data]
        addon.ferragens._definir_abertura(bpy.context, f, .216251716)
        fechada = addon.ferragens._matriz_fechada(f)
        # Known radial deformation independent of the shape solver.
        centro = Vector((-.16, 0, .3075))
        pontos = []
        for v in malha.vertices:
            radial = v.co - centro
            radial.y = 0
            pontos.append(fechada @ (v.co + radial.normalized() * .02))
        addon.portas.adotar_contorno_modelado(bpy.context, g, pontos)
        nova = addon.ferragens._matriz_fechada(f)
        self.assertEqual(f.data, malha)
        self.assertEqual([tuple(p.vertices) for p in malha.polygons], topologia)
        self.assertEqual([tuple(dado.uv) for dado in malha.uv_layers['UV modelada'].data], uvs)
        self.assertEqual(list(malha.materials), [material])
        self.assertEqual(f.modifiers['Acabamento preservado'].type, 'BEVEL')
        self.assertAlmostEqual(f[addon.ferragens.CHAVE_ABERTURA], .216251716, places=6)
        for v, esperado in zip(malha.vertices, pontos):
            self.assertLess((nova @ v.co - esperado).length, 1e-6)
        frente = addon.frentes.perfil(f, fechada=True)[0]
        self.assertEqual(len(frente), n)
        for atual, esperado in zip(frente, pontos[:n]):
            self.assertLess((atual - esperado).length, 1e-6)
        # The hinge cup stays behind the physical face, including when the leaf is open.
        copos = [o for o in f.children if o.get(addon.ferragens.CHAVE_FERRAGEM) == 'CANECO']
        self.assertEqual(len(copos), 2)
        zmax = max(v.co.z for v in malha.vertices) + .1
        for copo in copos:
            contatos = 0
            for v in copo.data.vertices:
                p = copo.matrix_basis @ v.co
                hit, co, _normal, _face = f.ray_cast(Vector((p.x, p.y, zmax)), Vector((0, 0, -1)))
                if hit:
                    contatos += 1
                    self.assertLessEqual(p.z, co.z + .0001)
            self.assertGreater(contatos, 0)

    def test_espelhar_correr_inverte_curso_e_duas_vezes_devolve_posicao(self):
        c=addon.modulos.criar_armario(bpy.context,'Correr espelhada',1000,700,550,fundo=False)
        g=addon.portas.porta_no_modulo(c,abertura='CORRER')
        f=addon.portas._folhas_portas(g)[0]
        x=addon.ferragens._dados_da_folha(f)[3][0]
        addon.ferragens._definir_abertura(bpy.context,f,1)
        self.assertGreater(f.matrix_basis.translation.x*1000,x)
        self.assertEqual(addon.portas.espelhar_porta(bpy.context,g),'')
        novo=addon.ferragens._dados_da_folha(f)[3][0]
        self.assertGreater(novo,x)
        self.assertLess(f.matrix_basis.translation.x*1000,novo)
        self.assertEqual(addon.portas.espelhar_porta(bpy.context,g),'')
        self.assertAlmostEqual(addon.ferragens._dados_da_folha(f)[3][0],x,places=3)

    def test_espelhar_basculante_inverte_dobradicas_pistoes_e_puxador(self):
        c=addon.modulos.criar_armario(bpy.context,'Basculante espelhada',600,700,550,fundo=False)
        g=addon.portas.porta_no_modulo(c,abertura='BASCULANTE')
        f=addon.portas._folhas_portas(g)[0]
        pux=addon.puxadores.perfis_na_porta(bpy.context,g,'BAIXO')[0]
        p=addon.portas._copiar_parametros(g['porta_parametros'])
        calc=[addon.ferragens._dados_da_folha(f)]
        origens={i['id']:i['origem'].copy() for i in addon.ferragens._pistoes_da_porta(p,g['porta_vao_largura_mm'],g['porta_vao_altura_mm'],calc) if 'origem' in i}
        addon.ferragens._definir_abertura(bpy.context,f,.5)
        antes=f.matrix_basis[2][1]
        self.assertEqual(addon.portas.espelhar_porta(bpy.context,g),'')
        p=addon.portas._copiar_parametros(g['porta_parametros'])
        self.assertTrue(p['basculante_invertida'])
        self.assertLess(antes*f.matrix_basis[2][1],0)
        self.assertEqual(pux['puxador_borda'],'Y+')
        aresta=addon.ferragens._dobradicas_da_porta(p,g['porta_vao_largura_mm'],g['porta_vao_altura_mm'],calc)[0][0]
        self.assertEqual(aresta['lado'],'BAIXO')
        for item in addon.ferragens._pistoes_da_porta(p,g['porta_vao_largura_mm'],g['porta_vao_altura_mm'],calc):
            if 'origem' in item:self.assertAlmostEqual(item['origem'].y+origens[item['id']].y,2*calc[0][3][1],places=3)
        self.assertEqual(addon.portas.espelhar_porta(bpy.context,g),'')
        self.assertEqual(pux['puxador_borda'],'Y-')

    def test_espelhar_porta_preserva_vao_malha_e_fracao_de_abertura(self):
        c=addon.modulos.criar_armario(bpy.context,"Mirror",600,700,550,fundo=False)
        g=addon.portas.porta_no_modulo(c)
        f=addon.portas._folhas_portas(g)[0]
        f.data.vertices[0].co.y += .015
        antes=[tuple(v.co) for v in f.data.vertices]
        fechada=addon.ferragens._matriz_fechada(f).copy()
        lado=addon.ferragens._lado_da_folha(g['porta_parametros'],0,1)
        addon.ferragens._definir_abertura(bpy.context,f,.65)
        for o in bpy.context.selected_objects:o.select_set(False)
        g.select_set(True);bpy.context.view_layer.objects.active=g
        self.assertIn('FINISHED',bpy.ops.object.cabinet_espelhar_porta())
        self.assertNotEqual(addon.ferragens._lado_da_folha(g['porta_parametros'],0,1),lado)
        self.assertEqual(f[addon.ferragens.CHAVE_ABERTURA],.65)
        self.assertTrue(all((v.co-Vector(co)).length<1e-6 for v,co in zip(f.data.vertices,antes)))
        self.assertLess(max(abs(a-b) for la,lb in zip(fechada,addon.ferragens._matriz_fechada(f)) for a,b in zip(la,lb)),1e-6)
        self.assertIn('FINISHED',bpy.ops.object.cabinet_espelhar_porta())
        self.assertEqual(addon.ferragens._lado_da_folha(g['porta_parametros'],0,1),lado)
        self.assertEqual(bpy.context.object,g)

    def test_espelhar_folha_dupla_muda_so_ela_e_usa_a_sua_borda(self):
        c=addon.modulos.criar_armario(bpy.context,'Dupla espelhada',800,700,550,fundo=False)
        g=addon.portas.porta_no_modulo(c,folhas=2)
        f0,f1=addon.portas._folhas_portas(g)
        for o in bpy.context.selected_objects:o.select_set(False)
        f1.select_set(True);bpy.context.view_layer.objects.active=f1
        self.assertIn('FINISHED',bpy.ops.object.cabinet_espelhar_porta())
        p=addon.portas._copiar_parametros(g['porta_parametros'])
        self.assertEqual([addon.ferragens._lado_da_folha(p,i,2) for i in range(2)],['ESQUERDA','ESQUERDA'])
        calc=addon.portas._calcular_folhas_portas(g['porta_vao_largura_mm'],g['porta_vao_altura_mm'],p)
        aresta=addon.ferragens._dobradicas_da_porta(p,g['porta_vao_largura_mm'],g['porta_vao_altura_mm'],calc)[1][0]
        self.assertGreater(aresta['a'].x,200)
        self.assertLess(aresta['a'].x,g['porta_vao_largura_mm']-200)
        self.assertEqual(bpy.context.object,f1)
        self.assertEqual(addon.portas.alvos_para_espelhar(bpy.context),{g:{1}})
        raizes=[o for o in g.children_recursive if o.get('cabinet_peca')=='raiz']
        self.assertEqual({int(o['porta_ferragem_folha']) for o in raizes},{0,1})
        self.assertEqual(len({o[addon.ferragens.CHAVE_ID_FERRAGEM] for o in raizes}),len(raizes))
        self.assertFalse(addon.portas._editar_parametro_porta(bpy.context,g,'espessura_mm',20))
        c.conj_largura_mm=900
        c.conj_largura_mm=800
        self.assertEqual(g['porta_parametros']['dobradicas_lados_folhas']['1'],'ESQUERDA')

    def test_espelhar_grupo_e_folha_fica_no_menu_contextual(self):
        c=addon.modulos.criar_armario(bpy.context,'Menu',600,700,550,fundo=False)
        g=addon.portas.porta_no_modulo(c)
        for o in bpy.context.selected_objects:o.select_set(False)
        g.select_set(True);bpy.context.view_layer.objects.active=g
        bpy.context.scene.cabinet_aba='PORTAS'
        for largura in (190,320,564):
            acoes=[w[5] for w in addon.gaveta._widgets_gaveta(bpy.context,largura,1400)]
            self.assertNotIn(('operador','object.cabinet_espelhar_porta'),acoes)
        self.assertEqual(addon.gaveta_eventos._icone_acao_gaveta(('operador','object.cabinet_espelhar_porta')),'MOD_MIRROR')
        chamadas=[]
        menu=SimpleNamespace(layout=SimpleNamespace(separator=lambda:None,
            operator=lambda nome,**kw:chamadas.append((nome,kw))))
        addon.portas.menu_contexto_porta(menu,bpy.context)
        self.assertEqual(chamadas,[('object.cabinet_espelhar_porta',{'icon':'MOD_MIRROR'})])
        c.select_set(True)
        self.assertFalse(addon.portas.OBJECT_OT_espelhar_porta.poll(bpy.context))

    def test_espelhar_puxador_nativo_muda_lado_e_duas_vezes_restaura(self):
        c=addon.modulos.criar_armario(bpy.context,'Puxador espelhado',600,700,550,fundo=False)
        g=addon.portas.porta_no_modulo(c)
        pux=addon.puxadores.perfis_na_porta(bpy.context,g,'LADO')[0]
        borda=pux['puxador_borda']
        self.assertEqual(addon.portas.espelhar_porta(bpy.context,g),'')
        self.assertNotEqual(pux['puxador_borda'],borda)
        self.assertEqual(addon.portas.espelhar_porta(bpy.context,g),'')
        self.assertEqual(pux['puxador_borda'],borda)

    def test_espelhar_zigzag_mantem_folhas_fechadas_e_puxador_na_ultima(self):
        c=addon.modulos.criar_armario(bpy.context,'Zigzag espelhada',900,700,550,fundo=False)
        g=addon.portas.porta_no_modulo(c,folhas=3,abertura='ZIGZAG')
        fs=addon.portas._folhas_portas(g)
        antes={f:addon.ferragens._matriz_fechada(f).translation.copy() for f in fs}
        for _ in range(2):
            self.assertEqual(addon.portas.espelhar_porta(bpy.context,g),'')
            novas=addon.portas._folhas_portas(g)
            for f in novas:self.assertLess((addon.ferragens._matriz_fechada(f).translation-antes[f]).length,1e-6)
            pux=[p for f in novas for p in f.children if addon.chapas.MARCA_PUXADOR in p]
            self.assertEqual({p.parent for p in pux},{novas[-1]})

    def test_modulo_real_prevalece_sobre_nome_antigo_do_preset(self):
        c=addon.modulos.criar_armario(bpy.context,'Origem',600,700,550,fundo=False)
        g=addon.portas.porta_no_modulo(c)
        outro=addon.modulos.criar_armario(bpy.context,'Copia',600,700,550,fundo=False)
        # As with append, Blender renames the parent but not a stored string.
        g[addon.portas.CHAVE_MODULO_PORTA]=outro.name
        self.assertEqual(addon.portas._portas_do_conjunto(c),[g])
        self.assertEqual(addon.portas._portas_do_conjunto(outro),[])
        antes=float(g['porta_vao_largura_mm'])
        c.conj_largura_mm=800
        self.assertAlmostEqual(float(g['porta_vao_largura_mm'])-antes,200,delta=.05)

    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        # This script uses only the disposable --factory-startup scene.
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        # Each cabinet has its own Collection, named after the group.
        for col in [c for c in bpy.data.collections
                    if c.get(addon.modulos.MARCA_COLECAO_MODULO)]:
            bpy.data.collections.remove(col)

    def pontos(self, pontos=((0, -0.15, 0), (0.6, -0.15, 0.8)), separados=False,
               pai=None):
        objetos = []
        for coords in ([[p] for p in pontos] if separados else [pontos]):
            malha = bpy.data.meshes.new('VerticesTeste')
            malha.from_pydata(coords, [], [])
            obj = bpy.data.objects.new('VaoTeste', malha)
            bpy.context.collection.objects.link(obj)
            obj.parent = pai
            obj.select_set(True)
            objetos.append(obj)
        bpy.context.view_layer.objects.active = objetos[0]
        bpy.context.view_layer.update()
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        return objetos

    def criar(self, **kwargs):
        self.pontos()
        resultado = bpy.ops.object.cabinet_portas('EXEC_DEFAULT', **kwargs)
        self.assertEqual(resultado, {'FINISHED'})
        return bpy.context.object

    def test_coberturas_e_profundidades(self):
        # Half overlay: half the side thickness minus clearance, as requested.
        # Full overlay: the user's rig determines minimum cabinet clearance.
        # Never flush with the edge, as requested: full overlay = thickness minus
        # clearance; inset = clearance inside the opening.
        r = addon.portas.RESPIRO_PORTA_MM
        for dobradica, cobertura, z in [('RETA', 18 - r, 9 + folga_reta()),
                                      ('CURVA', 7, 9), ('SUPER_CURVA', -r, -9)]:
            for abertura in ('GIRO', 'BASCULANTE'):
                with self.subTest(dobradica=dobradica, abertura=abertura):
                    folha = addon.portas._calcular_folhas_portas(
                        600, 800, parametros(dobradica=dobradica, abertura=abertura))[0]
                    self.assertEqual(folha[:3], (600 + 2 * cobertura,
                                                800 + 2 * cobertura, 18))
                    self.assertEqual(folha[3][:2], (300, 400))
                    self.assertAlmostEqual(folha[3][2], z, places=6)

    def test_duas_portas_na_mesma_chapa_tem_respiro(self):
        # User screenshot: two half-overlay doors sharing the center panel touched.
        # Each covers half minus 2 mm, leaving a 4 mm gap.
        E = 18.0
        meia = dict(cobertura_esq_e=1.0, cobertura_dir_e=0.5,
                    cobertura_baixo_e=1.0, cobertura_cima_e=1.0)
        l, _a, _e, c = addon.portas._calcular_folhas_portas(
            300, 800, parametros(dobradica='CURVA', **meia))[0]
        direita_a = c[0] + l / 2                     # Opening A: 0..300.
        espelho = dict(meia, cobertura_esq_e=0.5, cobertura_dir_e=1.0)
        l, _a, _e, c = addon.portas._calcular_folhas_portas(
            300, 800, parametros(dobradica='CURVA', **espelho))[0]
        esquerda_b = 300 + E + c[0] - l / 2          # Opening B: beyond the panel.
        self.assertAlmostEqual(direita_a, 300 + E / 2 - 2, places=6)
        self.assertAlmostEqual(esquerda_b - direita_a,
                               2 * addon.portas.RESPIRO_PORTA_MM, places=6)
        self.assertEqual(addon.portas._cobertura_mm(0.5, E), 7.0)
        self.assertEqual(addon.portas._cobertura_mm(1.0, E), E - addon.portas.RESPIRO_PORTA_MM)
        self.assertEqual(addon.portas._cobertura_mm(0.0, E), -addon.portas.RESPIRO_PORTA_MM)
        self.assertEqual(addon.portas._cobertura_mm(0.8, E), 0.8 * E)   # Marked.

    def test_giro_duplo_fecha_perimetro(self):
        folhas = addon.portas._calcular_folhas_portas(600, 800, parametros(folhas=2))
        l = folhas[0][0]
        cobre = 18 - addon.portas.RESPIRO_PORTA_MM
        self.assertEqual(l, (600 + 2 * cobre - 2) / 2)
        self.assertEqual(folhas[0][3][0] - l / 2, -cobre)
        self.assertEqual(folhas[-1][3][0] + l / 2, 600 + cobre)
        self.assertEqual(folhas[1][3][0] - folhas[0][3][0] - l, 2)

    def test_limites_no_calculo(self):
        for abertura, limite in addon.portas.LIMITES_FOLHAS.items():
            for n in range(0, 6):
                with self.subTest(abertura=abertura, folhas=n):
                    if (2 if abertura == 'ZIGZAG' else 1) <= n <= limite:
                        self.assertEqual(len(addon.portas._calcular_folhas_portas(
                            600, 800, parametros(abertura=abertura, folhas=n))), n)
                    else:
                        with self.assertRaises(ValueError):
                            addon.portas._calcular_folhas_portas(
                                600, 800, parametros(abertura=abertura, folhas=n))

    def test_correr_um_trilho_por_folha_e_recuo(self):
        # User request: each leaf has its own track and plane, with the first in front;
        # the recess is measured to the outermost face.
        r = addon.portas.RESPIRO_PORTA_MM
        util = 600 - 2 * r
        for n in range(1, 5):
            folhas = addon.portas._calcular_folhas_portas(
                600, 800, parametros(abertura='CORRER', folhas=n))
            # Clearance on both sides: sliding doors must not touch the side panels either.
            self.assertAlmostEqual(folhas[0][3][0] - folhas[0][0] / 2, r)
            if n == 1:
                # A single leaf spans half the opening, leaving room to slide.
                self.assertAlmostEqual(folhas[0][0], util / 2)
            else:
                self.assertAlmostEqual(folhas[-1][3][0] + folhas[-1][0] / 2,
                                       600 - r)
            for i, (l, a, e, centro) in enumerate(folhas):
                self.assertEqual(centro[2] + e / 2, -30 - i * 20)
                if i:
                    anterior = folhas[i - 1]
                    self.assertAlmostEqual(anterior[3][0] + l / 2 -
                                           (centro[0] - l / 2), 20)

    def test_correr_largura_da_folha_digitada(self):
        r = addon.portas.RESPIRO_PORTA_MM
        util = 600 - 2 * r
        chave = addon.portas.CHAVE_LARGURA_CORRER
        for n in range(1, 5):
            folhas = addon.portas._calcular_folhas_portas(
                600, 800, parametros(abertura='CORRER', folhas=n,
                                     **{chave: 350.0}))
            self.assertEqual({f[0] for f in folhas}, {350.0})
            # Spread across the opening: first at left, last at right.
            self.assertAlmostEqual(folhas[0][3][0] - 175, r)
            if n > 1:
                self.assertAlmostEqual(folhas[-1][3][0] + 175, 600 - r)
        # If larger than the opening after cabinet shrinkage, clamp to the opening width.
        (folha,) = addon.portas._calcular_folhas_portas(
            600, 800, parametros(abertura='CORRER', **{chave: 900.0}))
        self.assertAlmostEqual(folha[0], util)

    def test_medidas_invalidas(self):
        for alteracao in [dict(folga_mm=500), dict(entre_folhas_mm=1000, folhas=2),
                          dict(dobradica='ESCOLHER'), dict(espessura_mm=0),
                          dict(folga_mm=float('nan')),
                          dict(abertura='CORRER', recuo_correr_mm=0)]:
            with self.subTest(alteracao=alteracao), self.assertRaises(ValueError):
                addon.portas._calcular_folhas_portas(600, 800, parametros(**alteracao))

    def test_folgas_e_afastamentos(self):
        l, a, e, centro = addon.portas._calcular_folhas_portas(
            600, 800, parametros(folga_mm=2, afastamento_mm=3))[0]
        cobre = 18 - addon.portas.RESPIRO_PORTA_MM - 2          # Minus clearance.
        self.assertEqual((l, a), (600 + 2 * cobre, 800 + 2 * cobre))
        self.assertAlmostEqual(centro[2] - e / 2, 3)
        folha = addon.portas._calcular_folhas_portas(
            600, 800, parametros(dobradica='SUPER_CURVA', recuo_embutida_mm=5))[0]
        self.assertEqual(folha[3][2] + folha[2] / 2, -5)

    def test_ordem_dos_vertices_e_faces(self):
        for frente in ('NEG_Y', 'POS_Y', 'NEG_X', 'POS_X'):
            a, b = ((1, 2, 3), (1.6, 2, 3.8)) if frente.endswith('Y') else (
                (1, 2, 3), (1, 2.6, 3.8))
            l, h, matriz = addon.portas._mapear_vao_portas(a, b, Matrix.Identity(3), frente)
            l2, h2, matriz2 = addon.portas._mapear_vao_portas(b, a, Matrix.Identity(3), frente)
            self.assertAlmostEqual(l, 600, places=3)
            self.assertAlmostEqual(h, 800, places=3)
            self.assertEqual((l, h, matriz), (l2, h2, matriz2))
            self.assertAlmostEqual(matriz.determinant(), 1)

    def test_vao_degenerado_ou_fora_do_plano(self):
        for ponto in [(0, 0, 0), (0, 0, 0.8), (0.6, 0, 0), (0.6, 0.1, 0.8)]:
            with self.assertRaises(ValueError):
                addon.portas._mapear_vao_portas((0, 0, 0), ponto, Matrix.Identity(3), 'NEG_Y')

    def test_captura_bmesh_de_duas_chapas(self):
        self.pontos(separados=True)
        a, b, ref, pai = addon.portas._capturar_vertices_portas(bpy.context)
        l, h, _ = addon.portas._mapear_vao_portas(a, b, ref, 'NEG_Y')
        self.assertAlmostEqual(l, 600, places=3)
        self.assertAlmostEqual(h, 800, places=3)
        self.assertIsNone(pai)

    def test_contagem_invalida_preserva_cena_e_modo(self):
        for n in (1, 3):
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            objetos = self.pontos(pontos=[(i, 0, i) for i in range(n)])
            antes = set(bpy.data.objects.keys())
            self.assertEqual(bpy.ops.object.cabinet_portas(dobradica='RETA'), {'CANCELLED'})
            self.assertEqual(set(bpy.data.objects.keys()), antes)
            self.assertEqual(bpy.context.mode, 'EDIT_MESH')
            self.assertEqual(sum(v.select for v in bmesh.from_edit_mesh(objetos[0].data).verts), n)

    def test_dobradica_obrigatoria(self):
        self.pontos()
        antes = len(bpy.data.objects)
        self.assertEqual(bpy.ops.object.cabinet_portas(dobradica='ESCOLHER'), {'CANCELLED'})
        self.assertEqual(len(bpy.data.objects), antes)
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')

    def test_malhas_fechadas_e_o_trilho_do_correr(self):
        grupo = self.criar(abertura='CORRER', folhas=4)
        folhas = addon.portas._folhas_portas(grupo)
        self.assertEqual(len(folhas), 4)
        # Opening, group, four solids, and upper/lower tracks.
        self.assertEqual(len(bpy.data.objects), 8)
        trilhos = addon.ferragens._ferragens_portas(grupo)
        self.assertEqual(sorted(o.name for o in trilhos),
                         ["Lower Track", "Upper Track"])
        self.assertEqual({o[addon.ferragens.CHAVE_FERRAGEM] for o in trilhos},
                         {'TRILHO'})
        for folha in folhas:
            self.assertEqual(len(folha.data.vertices), 8)
            self.assertEqual(len(folha.data.polygons), 6)
            self.assertFalse(folha.modifiers)
            bm = bmesh.new()
            bm.from_mesh(folha.data)
            self.assertTrue(all(e.is_manifold for e in bm.edges))
            self.assertGreater(bm.calc_volume(signed=True), 0)
            bm.free()
        addon.chapas.normalizar_chapas()
        addon.modulos.absorver_conjuntos()
        self.assertEqual(len(addon.portas._folhas_portas(grupo)), 4)
        self.assertEqual(len(grupo.children), 6)
        self.assertEqual(len(addon.selecao.familia_de(folhas[0])), 5)

    def test_posicao_em_mundo_e_origem(self):
        grupo = self.criar(dobradica='RETA')
        folha = addon.portas._folhas_portas(grupo)[0]
        vertices = [folha.matrix_world @ v.co for v in folha.data.vertices]
        cobre = (18 - addon.portas.RESPIRO_PORTA_MM) / 1000.0
        self.assertAlmostEqual(min(v.x for v in vertices), -cobre, places=6)
        self.assertAlmostEqual(max(v.x for v in vertices), 0.6 + cobre, places=6)
        self.assertAlmostEqual(min(v.z for v in vertices), -cobre, places=6)
        self.assertAlmostEqual(max(v.z for v in vertices), 0.8 + cobre, places=6)
        folga = folga_reta() / 1000.0
        self.assertAlmostEqual(min(v.y for v in vertices), -0.168 - folga, places=6)
        self.assertAlmostEqual(max(v.y for v in vertices), -0.15 - folga, places=6)
        self.assertLess((grupo.matrix_world.translation - Vector((0, -0.15, 0))).length, 1e-6)

    def test_pai_rotacionado_escalado_e_transladado(self):
        pai = bpy.data.objects.new("Cabinet", None)
        bpy.context.collection.objects.link(pai)
        pai.location = (1, 2, 3)
        pai.rotation_euler = (0.2, -0.1, math.radians(37))
        pai.scale = (2, 1, 1.5)
        bpy.context.view_layer.update()
        self.pontos(separados=True, pai=pai)
        a, b, ref, capturado = addon.portas._capturar_vertices_portas(bpy.context)
        self.assertEqual(capturado, pai)
        l, h, _ = addon.portas._mapear_vao_portas(a, b, ref, 'NEG_Y')
        self.assertAlmostEqual(l, 1200, places=2)
        self.assertAlmostEqual(h, 1200, places=2)
        self.assertEqual(bpy.ops.object.cabinet_portas(dobradica='SUPER_CURVA'), {'FINISHED'})
        grupo = bpy.context.object
        folha = addon.portas._folhas_portas(grupo)[0]
        self.assertEqual(grupo.parent, pai)
        self.assertAlmostEqual((folha.matrix_world.to_3x3().col[2]).length, 1, places=5)
        self.assertAlmostEqual(folha.chapa_espessura_mm, 18)
        antes = folha.matrix_world.translation.copy()
        pai.location.x += 1
        bpy.context.view_layer.update()
        self.assertAlmostEqual(folha.matrix_world.translation.x - antes.x, 1, places=5)

    def test_objeto_rotacionado_sem_pai(self):
        objetos = self.pontos()
        bpy.ops.object.mode_set(mode='OBJECT')
        objetos[0].rotation_euler.z = math.radians(45)
        objetos[0].location = (2, 3, 4)
        bpy.context.view_layer.update()
        bpy.ops.object.mode_set(mode='EDIT')
        self.assertEqual(bpy.ops.object.cabinet_portas(
            orientacao='ATIVO', dobradica='SUPER_CURVA'), {'FINISHED'})
        grupo = bpy.context.object
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], 600, places=2)
        self.assertAlmostEqual(grupo['porta_vao_altura_mm'], 800, places=2)

    def test_parametros_sobrevivem_arquivo_blend(self):
        grupo = self.criar(abertura='CORRER', folhas=3, recuo_correr_mm=45)
        params = dict(grupo['porta_parametros'])
        folhas = addon.portas._folhas_portas(grupo)
        with tempfile.TemporaryDirectory(prefix='cabinet_portas_teste_') as pasta:
            arquivo = os.path.join(pasta, 'portas.blend')
            bpy.data.libraries.write(arquivo, {grupo, *folhas})
            with bpy.data.libraries.load(arquivo, link=False) as (origem, destino):
                destino.objects = origem.objects
            copias = destino.objects
        novo = next(o for o in copias if addon.chapas.MARCA_PORTAS in o)
        self.assertEqual(dict(novo['porta_parametros']), params)
        self.assertEqual(len(addon.portas._folhas_portas(novo)), 3)
        self.assertAlmostEqual(novo['porta_vao_largura_mm'], 600, places=3)

    def test_malha_compartilhada_nao_altera_outra_porta(self):
        grupo = self.criar(dobradica='RETA')
        primeira = addon.portas._folhas_portas(grupo)[0]
        copia = primeira.copy()
        bpy.context.collection.objects.link(copia)
        copia.parent = None
        malha_original = copia.data
        vertices = [v.co.copy() for v in malha_original.vertices]
        self.assertEqual(bpy.ops.object.cabinet_portas(
            editar=True, grupo_nome=grupo.name, dobradica='SUPER_CURVA'), {'FINISHED'})
        self.assertNotEqual(primeira.data, malha_original)
        self.assertEqual([v.co for v in copia.data.vertices], vertices)

    def test_edicao_reutiliza_materiais_e_remove_somente_folhas(self):
        grupo = self.criar(abertura='CORRER', folhas=4)
        primeira = addon.portas._folhas_portas(grupo)[0]
        material = bpy.data.materials.new('MadeiraTeste')
        primeira.data.materials.append(material)
        extra = bpy.data.objects.new('FilhoDoUsuario', None)
        bpy.context.collection.objects.link(extra)
        extra.parent = grupo
        matriz = grupo.matrix_world.copy()
        resultado = bpy.ops.object.cabinet_portas(editar=True, grupo_nome=grupo.name,
                                                abertura='BASCULANTE', folhas=1,
                                                dobradica='CURVA')
        self.assertEqual(resultado, {'FINISHED'})
        self.assertEqual(addon.portas._folhas_portas(grupo), [primeira])
        self.assertEqual(primeira.data.materials[0], material)
        self.assertEqual(extra.parent, grupo)
        self.assertEqual(grupo.matrix_world, matriz)
        self.assertEqual(grupo['porta_parametros']['dobradica'], 'CURVA')

    def test_edicao_invalida_nao_altera_grupo(self):
        grupo = self.criar(dobradica='RETA')
        original = dict(grupo['porta_parametros'])
        primeira = addon.portas._folhas_portas(grupo)[0]
        coords = [v.co.copy() for v in primeira.data.vertices]
        self.assertEqual(bpy.ops.object.cabinet_portas(
            editar=True, grupo_nome=grupo.name, dobradica='RETA', folga_mm=1000), {'CANCELLED'})
        self.assertEqual(dict(grupo['porta_parametros']), original)
        self.assertEqual([v.co for v in primeira.data.vertices], coords)

    def test_vao_apanhado_em_modo_objeto_dispensa_edit_mode(self):
        # Picker path (cabinet_apanhar_vao): points arrive ready to use,
        # without involving Edit Mode.
        objetos = self.pontos(separados=True)
        bpy.ops.object.mode_set(mode='OBJECT')
        self.assertEqual(bpy.context.mode, 'OBJECT')

        a = objetos[0].matrix_world @ objetos[0].data.vertices[0].co
        b = objetos[1].matrix_world @ objetos[1].data.vertices[0].co
        referencia, pai = addon.portas._referencia_do_par(objetos[0], objetos[1])
        resultado = bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            referencia=tuple(v for linha in referencia for v in linha),
            pai_nome=pai.name if pai is not None else '',
            dobradica='RETA')
        self.assertEqual(resultado, {'FINISHED'})
        grupo = addon.portas._grupo_portas(bpy.context.object)
        self.assertIsNotNone(grupo)
        folha = addon.portas._folhas_portas(grupo)[0]
        # 600 x 800 opening, full-overlay hinge: cover both side panels.
        # In the leaf's local axes, X = width, Y = height and Z = thickness;
        # height is not Z.
        cobre = (18 - addon.portas.RESPIRO_PORTA_MM) / 1000.0
        self.assertAlmostEqual(folha.dimensions.x, 0.6 + 2 * cobre, places=4)
        self.assertAlmostEqual(folha.dimensions.y, 0.8 + 2 * cobre, places=4)
        self.assertAlmostEqual(folha.dimensions.z, 0.018, places=4)

    def test_referencia_do_par_usa_o_ancestral_comum(self):
        # Edit Mode and the picker must follow the same rule; divergence
        # would rotate the opening in one path.
        bpy.ops.object.empty_add()
        empty = bpy.context.object
        empty.rotation_euler = (0.0, 0.0, math.radians(30))
        objetos = self.pontos(separados=True, pai=empty)
        bpy.ops.object.mode_set(mode='OBJECT')
        referencia, pai = addon.portas._referencia_do_par(objetos[0], objetos[1])
        self.assertEqual(pai, empty)
        esperado = pai.matrix_world.to_quaternion().to_matrix()
        for linha_a, linha_b in zip(referencia, esperado):
            for va, vb in zip(linha_a, linha_b):
                self.assertAlmostEqual(va, vb, places=6)

    def test_apanhador_so_roda_em_modo_objeto(self):
        self.pontos()
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        self.assertFalse(addon.assistente.OBJECT_OT_apanhar_vao_portas.poll(bpy.context))
        bpy.ops.object.mode_set(mode='OBJECT')
        self.assertTrue(addon.assistente.OBJECT_OT_apanhar_vao_portas.poll(bpy.context))

    def sem_rig(self):
        """Without the full-overlay hinge asset, use boxes and a fixed pivot, as for half-overlay/inset doors and installations missing the asset."""
        original = addon.ferragens._dados_dobradica_reta
        addon.ferragens._dados_dobradica_reta = lambda: None
        self.addCleanup(setattr, addon.ferragens, '_dados_dobradica_reta', original)

    def nicho(self):
        """Create a real cabinet with side panels, base and top."""
        bpy.ops.object.cabinet_criar_nicho()
        # The niche creates loose panels; grouping supplies the assembly Empty
        # with its parametric dimensions.
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar()
        conj = next(o for o in bpy.data.objects
                    if addon.chapas.MARCA_CONJUNTO in o)
        bpy.context.view_layer.update()
        return conj

    def porta_no_nicho(self, conj):
        """Create the door from the cabinet's inner opening (scenario 2)."""
        L = conj.conj_largura_mm
        A = conj.conj_altura_mm
        P = conj.conj_profundidade_mm
        E = conj.conj_espessura_mm
        local_a = Vector((-L / 2 + E, -P / 2, E)) / 1000.0
        local_b = Vector((L / 2 - E, -P / 2, A - E)) / 1000.0
        a = conj.matrix_world @ local_a
        b = conj.matrix_world @ local_b
        chapa = next(o for o in addon.modulos._chapas_do_conjunto(conj))
        self.assertEqual(addon.portas._modulo_da_chapa(chapa), conj)
        resultado = bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            referencia=tuple(
                v for linha in conj.matrix_world.to_quaternion().to_matrix()
                for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name,
            frente='NEG_Y', dobradica='RETA', folhas=2)
        self.assertEqual(resultado, {'FINISHED'})
        # Linking makes the cabinet active (step 3), so retrieve the group
        # through its door list.
        self.assertEqual(bpy.context.object, conj)
        grupos = addon.portas._portas_do_conjunto(conj)
        self.assertEqual(len(grupos), 1)
        return grupos[0]

    def test_modulo_da_chapa_sobe_ate_o_conjunto(self):
        conj = self.nicho()
        for chapa in addon.modulos._chapas_do_conjunto(conj):
            self.assertEqual(addon.portas._modulo_da_chapa(chapa), conj)
        bpy.ops.mesh.primitive_cube_add()
        self.assertIsNone(addon.portas._modulo_da_chapa(bpy.context.object))

    def test_porta_vinculada_grava_folgas_em_espessuras(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        self.assertEqual(grupo[addon.portas.CHAVE_MODULO_PORTA], conj.name)
        # The opening touches all four panels: one thickness per side.
        for folga in grupo[addon.portas.CHAVE_FOLGAS_PORTA]:
            self.assertAlmostEqual(folga, 1.0, places=4)

    def corrente(self):
        """Door/cabinet chain state. The operator left the sidebar but remains available through F3."""
        return 'LINKED' if addon.importacao._corrente_porta_ligada(bpy.context) else 'UNLINKED'

    def test_corrente_decide_porta_no_modulo_ou_no_mundo(self):
        s = bpy.context.scene
        self.addCleanup(s.property_unset, 'porta_associar')
        # With no active door, the chain sets the next door's linking choice.
        bpy.ops.object.select_all(action='DESELECT')
        self.assertEqual(self.corrente(), 'LINKED')
        self.assertEqual(bpy.ops.object.cabinet_corrente_porta(), {'FINISHED'})
        self.assertFalse(s.porta_associar)
        self.assertEqual(self.corrente(), 'UNLINKED')
        apanhador = SimpleNamespace(_grupo_alvo='')
        classe = addon.assistente.OBJECT_OT_apanhar_vao_portas
        self.assertFalse(classe._associar(apanhador, bpy.context))
        s.porta_associar = True
        self.assertTrue(classe._associar(apanhador, bpy.context))
        # With an active door, the chain displays and changes that door's state.
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        bpy.context.view_layer.objects.active = grupo
        self.assertEqual(self.corrente(), 'LINKED')
        mundo = grupo.matrix_world.copy()
        self.assertEqual(bpy.ops.object.cabinet_corrente_porta(), {'FINISHED'})
        self.assertNotIn(addon.portas.CHAVE_MODULO_PORTA, grupo)
        self.assertIsNone(grupo.parent)
        self.assertTrue(all(abs(a - b) < 1e-6 for la, lb in
                            zip(mundo, grupo.matrix_world) for a, b in zip(la, lb)))
        self.assertEqual(self.corrente(), 'UNLINKED')
        self.assertTrue(s.porta_associar)          # The scene setting is unchanged.
        # Detached doors do not follow the cabinet.
        largura = addon.portas._folhas_portas(grupo)[0].chapa_largura_mm
        conj.conj_largura_mm += 200.0
        bpy.context.view_layer.update()
        self.assertEqual(addon.portas._folhas_portas(grupo)[0].chapa_largura_mm, largura)
        # Relinking returns to the same cabinet even when it is not selected.
        bpy.context.view_layer.objects.active = grupo
        self.assertEqual(bpy.ops.object.cabinet_corrente_porta(), {'FINISHED'})
        self.assertEqual(grupo[addon.portas.CHAVE_MODULO_PORTA], conj.name)
        self.assertEqual(grupo.parent, conj)
        self.assertEqual(self.corrente(), 'LINKED')

    def test_porta_acompanha_a_largura_do_modulo(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        antes = grupo['porta_vao_largura_mm']
        conj.conj_largura_mm = conj.conj_largura_mm + 400.0
        bpy.context.view_layer.update()
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], antes + 400.0,
                               places=3)
        folha = addon.portas._folhas_portas(grupo)[0]
        self.assertGreater(folha.chapa_largura_mm, 0.0)

    def test_porta_acompanha_a_altura_do_modulo(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        antes = grupo['porta_vao_altura_mm']
        conj.conj_altura_mm = conj.conj_altura_mm + 300.0
        bpy.context.view_layer.update()
        self.assertAlmostEqual(grupo['porta_vao_altura_mm'], antes + 300.0,
                               places=3)

    def test_porta_acompanha_a_espessura_das_chapas(self):
        # Clearance is stored in thickness units: thicker panels narrow the opening.
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        antes = grupo['porta_vao_largura_mm']
        e_antes = conj.conj_espessura_mm
        conj.conj_espessura_mm = 30.0
        bpy.context.view_layer.update()
        esperado = antes - 2.0 * (30.0 - e_antes)
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], esperado,
                               places=3)

    def test_porta_sem_modulo_nao_ganha_vinculo(self):
        # Scenario 1: generic object, with no link to preserve.
        objetos = self.pontos(separados=True)
        bpy.ops.object.mode_set(mode='OBJECT')
        a = objetos[0].matrix_world @ objetos[0].data.vertices[0].co
        b = objetos[1].matrix_world @ objetos[1].data.vertices[0].co
        bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            dobradica='RETA')
        grupo = addon.portas._grupo_portas(bpy.context.object)
        self.assertNotIn(addon.portas.CHAVE_MODULO_PORTA, grupo)

    def test_operador_limita_basculante_e_giro(self):
        grupo = self.criar(abertura='BASCULANTE', folhas=4, dobradica='RETA')
        self.assertEqual(len(addon.portas._folhas_portas(grupo)), 1)
        self.assertEqual(bpy.ops.object.cabinet_portas(
            editar=True, grupo_nome=grupo.name, abertura='GIRO', folhas=4,
            dobradica='RETA'), {'FINISHED'})
        self.assertEqual(len(addon.portas._folhas_portas(grupo)), 2)

    def criar_por_pontos(self, conj, a, b, objetos=(None, None), **opcoes):
        anteriores = set(addon.portas._portas_do_conjunto(conj))
        ref = conj.matrix_world.to_quaternion().to_matrix()
        p = dict(frente='NEG_Y', dobradica='RETA', folhas=2)
        p.update(opcoes)
        resultado = bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True,
            ponto_a=conj.matrix_world @ Vector(a),
            ponto_b=conj.matrix_world @ Vector(b),
            referencia=tuple(v for linha in ref for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name,
            objeto_a_nome=objetos[0].name if objetos[0] else '',
            objeto_b_nome=objetos[1].name if objetos[1] else '', **p)
        self.assertEqual(resultado, {'FINISHED'})
        return next(g for g in addon.portas._portas_do_conjunto(conj) if g not in anteriores)

    def limites_folhas(self, conj, grupo):
        inversa = conj.matrix_world.inverted()
        pontos = [inversa @ (f.matrix_world @ v.co)
                  for f in addon.portas._folhas_portas(grupo) for v in f.data.vertices]
        return ([min(v[i] for v in pontos) for i in range(3)],
                [max(v[i] for v in pontos) for i in range(3)])

    def lateral_esquerda(self, conj):
        return min((c for c in addon.modulos._chapas_do_conjunto(conj)
                    if abs(addon.chapas._eixos(c)[2].x) > 0.9),
                   key=lambda c: (conj.matrix_world.inverted()
                                  @ c.matrix_world.translation).x)

    def test_snap_nativo_oferece_o_meio_da_espessura(self):
        # User request: a door covering half a panel uses native EDGE_MIDPOINT
        # snapping while choosing opposite corners. The wizard does not replace
        # the common protocol's default snap elements.
        import inspect
        fonte = inspect.getsource(addon.gavetas.AssistenteDoVao._iniciar_snap_nativo)
        self.assertIn("('VERTEX','EDGE_MIDPOINT')", fonte)
        w = addon.assistente.OBJECT_OT_apanhar_vao_portas
        self.assertNotIn('elementos_snap', inspect.getsource(w.invoke))

    def test_porta_cobre_meia_chapa_marcada_no_meio(self):
        conj = self.nicho()
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        lateral = self.lateral_esquerda(conj)
        a = conj.matrix_world @ (Vector((-L / 2 + E / 2, -P / 2, A)) / 1000.0)
        b = conj.matrix_world @ (Vector((L / 2, -P / 2, 0)) / 1000.0)
        self.assertEqual(bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            referencia=tuple(v for linha in
                             conj.matrix_world.to_quaternion().to_matrix()
                             for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name,
            objeto_a_nome=lateral.name, frente='NEG_Y', dobradica='RETA',
            folhas=1, folga_mm=0), {'FINISHED'})
        grupo = addon.portas._portas_do_conjunto(conj)[0]
        p = grupo['porta_parametros']
        self.assertEqual(p['cobertura_esq_e'], 0.5)
        self.assertEqual([k for k in addon.portas.COBERTURAS_LADOS if k in p],
                         ['cobertura_esq_e'])
        lo, hi = self.limites_folhas(conj, grupo)
        # Left: half the side panel minus clearance, so two doors sharing one panel
        # do not touch; the other edges use full overlay.
        meia = E / 2 - addon.portas.RESPIRO_PORTA_MM
        r = addon.portas.RESPIRO_PORTA_MM          # Full overlay also leaves clearance from the edge.
        self.assertAlmostEqual(lo[0] * 1000, -L / 2 + E - meia, places=3)
        self.assertAlmostEqual(hi[0] * 1000, L / 2 - r, places=3)
        self.assertAlmostEqual(lo[2] * 1000, r, places=3)
        self.assertAlmostEqual(hi[2] * 1000, A - r, places=3)
        # Resizing the cabinet keeps the edge at the side panel's midpoint.
        conj.conj_largura_mm = L + 100
        bpy.context.view_layer.update()
        lo, hi = self.limites_folhas(conj, grupo)
        self.assertAlmostEqual(lo[0] * 1000, -(L + 100) / 2 + E - meia, places=3)
        self.assertAlmostEqual(hi[0] * 1000, (L + 100) / 2 - r, places=3)
        # Half coverage is fixed; a half-overlay hinge already covers half, so it is unchanged.
        p = dict(grupo['porta_parametros'], dobradica='CURVA')
        self.assertEqual(addon.portas._inicios_porta(p), [-meia] * 4)
        # Half coverage belongs to the opening and survives a hinge-type change;
        # the remaining inset edges stay one clearance inside the opening.
        p = dict(p, dobradica='SUPER_CURVA')
        r = addon.portas.RESPIRO_PORTA_MM
        self.assertEqual(addon.portas._inicios_porta(p), [-meia, r, r, r])

    def porta_por_quatro_cliques(self, conj, p1, p2, p3, p4, **extras):
        mundo = [conj.matrix_world @ (Vector(p) / 1000.0)
                 for p in (p1, p2, p3, p4)]
        chapa = self.lateral_esquerda(conj)
        self.assertEqual(bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=mundo[1],
            ponto_b=mundo[2], quatro_pontos=True, porta_a=mundo[0],
            porta_b=mundo[3],
            referencia=tuple(v for linha in
                             conj.matrix_world.to_quaternion().to_matrix()
                             for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name,
            objeto_a_nome=chapa.name, frente='NEG_Y', folga_mm=0,
            **extras), {'FINISHED'})
        return addon.portas._portas_do_conjunto(conj)[0]

    # Regression, fixed in v303: Alt-dragging a corner scanned every visible mesh
    # on click and projected every vertex on each move, causing seconds of freezing.
    # The cursor now uses native snapping.
    def test_canto_da_porta_pelo_snap_nativo(self):
        import inspect
        V = addon.portas_viewport
        self.assertIn(V.OBJECT_OT_mover_canto_porta, addon.CLASSES)
        self.assertIn(V.OBJECT_OT_confirmar_canto_porta, addon.CLASSES)
        self.assertNotIn('.vertices', inspect.getsource(V._preparar_canto_nativo))
        self.assertEqual(bpy.ops.object.cabinet_confirmar_canto_porta(), {'CANCELLED'})
        self.assertEqual(V.OBJECT_OT_arrastar_canto_porta.invoke(
            SimpleNamespace(grupo='sem porta', indice=0), bpy.context, None), {'CANCELLED'})
        self.assertIsNone(V._arraste_canto_porta[0])
        conj = self.nicho()
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        y = -P / 2
        grupo = self.porta_por_quatro_cliques(
            conj, (-L / 2, y, A), (-L / 2 + E, y, A - E), (L / 2 - E, y, E),
            (L / 2 - E / 2, y, 0), dobradica='RETA', folhas=1)
        self.assertEqual(grupo['porta_parametros']['cobertura_dir_e'], 0.5)
        folha = addon.portas._folhas_portas(grupo)[0]
        cena = bpy.context.scene
        cursor = cena.cursor.location.copy()
        contexto = SimpleNamespace(
            visible_objects=bpy.context.visible_objects, scene=cena,
            region=SimpleNamespace(as_pointer=lambda: 1),
            area=SimpleNamespace(as_pointer=lambda: 2),
            space_data=SimpleNamespace(overlay=SimpleNamespace(show_cursor=True)))
        self.addCleanup(V._terminar_canto_nativo)
        parametros = V._preparar_canto_nativo(contexto, grupo, 3)
        self.assertTrue(parametros['snap'] and parametros['cursor_transform'])
        self.assertTrue(folha.hide_select)      # The door must not snap to itself.
        self.assertLess((cena.cursor.location - V._cantos_da_porta(grupo)[3]).length, 1e-6)
        cena.cursor.location = conj.matrix_world @ (Vector((L / 2, y, 0)) / 1000.0)
        self.assertEqual(bpy.ops.object.cabinet_confirmar_canto_porta(), {'FINISHED'})
        self.assertIsNone(V._arraste_canto_porta[0])
        self.assertFalse(folha.hide_select)
        self.assertLess((cena.cursor.location - cursor).length, 1e-6)
        self.assertEqual(grupo['porta_parametros']['cobertura_dir_e'], 1.0)

    def test_quatro_cliques_definem_a_porta_lado_a_lado(self):
        conj = self.nicho()
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        y = -P / 2
        # Left/top/bottom: full panel coverage; right: half the side panel.
        grupo = self.porta_por_quatro_cliques(
            conj, (-L / 2, y, A), (-L / 2 + E, y, A - E), (L / 2 - E, y, E),
            (L / 2 - E / 2, y, 0), dobradica='RETA', folhas=1)
        p = grupo['porta_parametros']
        self.assertEqual([p[k] for k in addon.portas.COBERTURAS_LADOS],
                         [1.0, 0.5, 1.0, 1.0])
        lo, hi = self.limites_folhas(conj, grupo)
        meia = E / 2 - addon.portas.RESPIRO_PORTA_MM     # Clearance on the half-overlay edge.
        r = addon.portas.RESPIRO_PORTA_MM                # And on full-overlay edges.
        self.assertAlmostEqual(lo[0] * 1000, -L / 2 + r, places=3)
        self.assertAlmostEqual(hi[0] * 1000, L / 2 - E + meia, places=3)
        self.assertAlmostEqual(lo[2] * 1000, r, places=3)
        self.assertAlmostEqual(hi[2] * 1000, A - r, places=3)
        # Follow the cabinet.
        conj.conj_largura_mm = L + 100
        bpy.context.view_layer.update()
        lo, hi = self.limites_folhas(conj, grupo)
        self.assertAlmostEqual(hi[0] * 1000, (L + 100) / 2 - E + meia, places=3)

    def test_quatro_cliques_com_porta_e_vao_no_mesmo_ponto(self):
        conj = self.nicho()
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        y = -P / 2
        # Points 1 and 2 coincide at the outer corner: use the margin from pair 3-4.
        grupo = self.porta_por_quatro_cliques(
            conj, (-L / 2, y, A), (-L / 2, y, A), (L / 2 - E, y, E),
            (L / 2, y, 0), dobradica='RETA', folhas=1)
        p = grupo['porta_parametros']
        self.assertEqual([p[k] for k in addon.portas.COBERTURAS_LADOS], [1.0] * 4)
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], L - 2 * E,
                               places=3)
        # All four points at the opening corners: an inset door with no overlay.
        bpy.data.objects.remove(grupo, do_unlink=True)
        grupo = self.porta_por_quatro_cliques(
            conj, (-L / 2 + E, y, A - E), (-L / 2 + E, y, A - E),
            (L / 2 - E, y, E), (L / 2 - E, y, E),
            dobradica='SUPER_CURVA', folhas=1)
        p = grupo['porta_parametros']
        self.assertEqual([p[k] for k in addon.portas.COBERTURAS_LADOS], [0.0] * 4)

    def test_cantos_da_porta_sao_os_cliques_e_refazem_a_porta(self):
        # User request: selecting a door shows its wizard points. With Alt, only the
        # two picked points (four before v309) can be dragged to rebuild the door,
        # using each point's panel as during creation.
        conj = self.nicho()
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        y = -P / 2
        cliques = [(-L / 2, y, A), (-L / 2 + E, y, A - E), (L / 2 - E, y, E),
                   (L / 2 - E / 2, y, 0)]
        grupo = self.porta_por_quatro_cliques(conj, *cliques,
                                              dobradica='RETA', folhas=1)
        mundo = [conj.matrix_world @ (Vector(p) / 1000.0) for p in cliques]
        for a, b in zip(addon.portas_viewport._cantos_da_porta(grupo), mundo):
            self.assertLess((a - b).length, 1e-6)
        V = addon.portas_viewport
        self.assertEqual(V.CANTOS_DO_GESTO, (0, 3))
        self.assertEqual(V.OBJECT_OT_arrastar_canto_porta.invoke(
            SimpleNamespace(grupo=grupo.name, indice=1), bpy.context, None), {'CANCELLED'})
        lateral = self.lateral_esquerda(conj)
        # Moving the lower corner to the outer corner makes the right edge fully overlay.
        fora = conj.matrix_world @ (Vector((L / 2, y, 0)) / 1000.0)
        self.assertEqual(V._mover_cantos_porta(bpy.context, grupo, [mundo[0], fora]),
                         {'FINISHED'})
        p = grupo['porta_parametros']
        self.assertEqual([p[k] for k in addon.portas.COBERTURAS_LADOS], [1.0] * 4)
        self.assertEqual(grupo[addon.portas.CHAVE_MODULO_PORTA], conj.name)
        # The door stays selected for further adjustments.
        self.assertIn(grupo, addon.portas_viewport._portas_com_cantos(bpy.context))
        # At the hinge side's midpoint, the picked panel establishes half coverage
        # and changes the hinge to half overlay.
        meio = conj.matrix_world @ (Vector((-L / 2 + E / 2, y, A)) / 1000.0)
        V._mover_cantos_porta(bpy.context, grupo, [meio, fora], [lateral, None])
        self.assertEqual(grupo['porta_parametros']['cobertura_esq_e'], 0.5)
        self.assertEqual(grupo['porta_parametros']['dobradica'], 'CURVA')
        antes = [V._cantos_da_porta(grupo)[i] for i in V.CANTOS_DO_GESTO]
        self.assertLess((antes[0] - meio).length, 1e-6)
        # Default: rebuild without prompting.
        addon.perguntas._pergunta_atual[0] = None
        quina = conj.matrix_world @ (Vector((-L / 2, y, A)) / 1000.0)
        V._aplicar_cantos_porta(bpy.context, grupo, [quina, fora], [lateral, None],
                                antes, [lateral, None])
        self.assertIsNone(addon.perguntas._pergunta_atual[0])
        self.assertEqual(grupo['porta_parametros']['cobertura_esq_e'], 1.0)
        # Answering no restores both picked points and their associated panels.
        self.assertEqual(bpy.ops.object.cabinet_cantos_porta(
            grupo=grupo.name, pontos=tuple(v for p in antes for v in p),
            objeto_a=lateral.name), {'FINISHED'})
        self.assertEqual(grupo['porta_parametros']['cobertura_esq_e'], 0.5)
        # Answering yes changes nothing.
        antes = addon.portas_viewport._cantos_da_porta(grupo)
        self.assertEqual(bpy.ops.object.cabinet_cantos_porta(
            grupo=grupo.name, manter=True), {'FINISHED'})
        for a, b in zip(antes, addon.portas_viewport._cantos_da_porta(grupo)):
            self.assertLess((a - b).length, 1e-9)
        self.assertFalse(addon.portas._lados_fora_do_padrao(
            addon.portas_viewport._coberturas_da_porta(grupo)))

    def test_porta_selecionada_desenha_folhas_vao_e_dobradicas(self):
        # User screenshot: selected doors show leaf outlines and yellow internal
        # opening lines. Hinge volumes at the wizard's planned positions appear
        # only when the hinges themselves are selected.
        self.sem_rig()
        conj = self.nicho()
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        y = -P / 2
        grupo = self.porta_por_quatro_cliques(
            conj, (-L / 2, y, A), (-L / 2 + E, y, A - E), (L / 2 - E, y, E),
            (L / 2 - E / 2, y, 0), dobradica='RETA', folhas=1)
        desenho = addon.portas_viewport._desenho_da_porta(grupo)
        self.assertNotIn('dobradicas', desenho)
        local = lambda v: (conj.matrix_world.inverted() @ v) * 1000.0
        self.assertEqual(len(desenho['folhas']), 1)
        # Opening: the panels' inner faces.
        xs = sorted(round(local(v).x, 3) for v in desenho['vao'])
        self.assertAlmostEqual(xs[0], -L / 2 + E, places=3)
        self.assertAlmostEqual(xs[-1], L / 2 - E, places=3)
        # Two hinges by default for this height, each with body and cup, at the left;
        # the body touches the inner side-panel face and extends into the cabinet.
        self.assertEqual(len(addon.ferragens._caixas_ferragens(grupo, {'DOBRADICA'})), 4)
        corpo = addon.ferragens._caixas_ferragens(grupo, {'DOBRADICA'})[0]
        x = sorted(local(v).x for v in corpo)
        self.assertAlmostEqual(x[0], -L / 2 + E, places=3)
        self.assertAlmostEqual(x[-1], -L / 2 + E + addon.portas.DOBRADICA_AVANCO_MM, places=3)
        # Behind the leaf: from the front (y = -P/2) into the cabinet.
        ys = sorted(local(v).y for v in corpo)
        self.assertAlmostEqual(ys[0], y, places=3)
        self.assertAlmostEqual(ys[-1], y + addon.portas.DOBRADICA_FUNDO_MM, places=3)
        # Two hinged leaves: hinges on both sides.
        bpy.data.objects.remove(grupo, do_unlink=True)
        grupo = self.porta_no_nicho(conj)
        desenho = addon.portas_viewport._desenho_da_porta(grupo)
        self.assertEqual(len(desenho['folhas']), 2)
        self.assertEqual(len(addon.ferragens._caixas_ferragens(grupo, {'DOBRADICA'})), 8)
        # Sliding doors have no hinges.
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'abertura', 'CORRER'), '')
        self.assertEqual(addon.ferragens._caixas_ferragens(grupo, {'DOBRADICA'}), [])

    # ---- Phase 3: real hardware, pivot and opening
    def porta_de_giro(self, conj, **extras):
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        y = -P / 2
        opcoes = dict(dobradica='RETA', folhas=1)
        opcoes.update(extras)
        return self.porta_por_quatro_cliques(
            conj, (-L / 2, y, A), (-L / 2 + E, y, A - E), (L / 2 - E, y, E),
            (L / 2, y, 0), **opcoes)

    def ferragens(self, grupo, tipo):
        return sorted((o for o in addon.ferragens._ferragens_portas(grupo)
                       if o[addon.ferragens.CHAVE_FERRAGEM] == tipo),
                      key=lambda o: o[addon.ferragens.CHAVE_ID_FERRAGEM])

    def test_ferragens_de_verdade_seguem_a_porta(self):
        # Hinge body on the cabinet, cup cut into the back of the leaf;
        # meshes move with the door but are excluded from its click target.
        self.sem_rig()
        conj = self.nicho()
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        y = -P / 2
        grupo = self.porta_de_giro(conj)
        folha = addon.portas._folhas_portas(grupo)[0]
        corpos = self.ferragens(grupo, 'DOBRADICA')
        canecos = self.ferragens(grupo, 'CANECO')
        self.assertEqual((len(corpos), len(canecos)), (2, 2))
        for o in corpos + canecos:
            # Selectable and editable like any object, as requested.
            self.assertFalse(o.hide_select)
            self.assertNotIn(addon.chapas.MARCA_CHAPA, o)
            self.assertEqual(o.parent, folha if o in canecos else grupo)
        local = lambda v: (conj.matrix_world.inverted() @ v) * 1000.0
        caneco = [local(canecos[0].matrix_world @ Vector(c))
                  for c in canecos[0].bound_box]
        # 12 mm into the leaf from its back (front = -Y), with the flange protruding
        # from the back; otherwise the cup disappears inside the door.
        self.assertAlmostEqual(max(v.y for v in caneco),
                               y + addon.portas.CANECO_ABA_MM, places=3)
        self.assertAlmostEqual(min(v.y for v in caneco),
                               y - addon.portas.CANECO_FUNDO_MM, places=3)
        # Hole 5 mm from the leaf edge; the leaf covers the side panel minus
        # clearance.
        self.assertAlmostEqual(min(v.x for v in caneco), -L / 2
                               + addon.portas.RESPIRO_PORTA_MM + addon.portas.CANECO_BORDA_MM,
                               places=3)
        # The selected-door drawing uses these meshes' volumes.
        desenho = addon.portas_viewport._desenho_da_porta(grupo)
        corpo = sorted(local(v).x for v in addon.ferragens._caixas_ferragens(grupo, {'DOBRADICA'})[0])
        self.assertAlmostEqual(corpo[0], -L / 2 + E, places=3)
        self.assertAlmostEqual(corpo[-1], -L / 2 + E + addon.portas.DOBRADICA_AVANCO_MM,
                               places=3)
        # Blender does not select hide_select objects, so the door selection excludes them.
        addon.hud._selecionar_porta_hud(bpy.context, folha, 'PORTA')
        self.assertFalse(any(o.select_get() for o in corpos + canecos))
        self.assertFalse(any(addon.ferragens.CHAVE_FERRAGEM in item[0]
                             for item in addon.hud._itens_da_selecao(bpy.context)))
        # Two leaves create hinges on both sides; returning to one leaves no extras.
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'folhas', 2), '')
        folhas = addon.portas._folhas_portas(grupo)
        self.assertEqual(sorted(o.parent.name for o in self.ferragens(grupo, 'CANECO')),
                         sorted([folhas[0].name] * 2 + [folhas[1].name] * 2))
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'folhas', 1), '')
        soltas = [o for o in bpy.data.objects if addon.ferragens.CHAVE_FERRAGEM in o]
        self.assertEqual(len(soltas), 4)

    def test_ferragens_conferidas_ao_apagar_ou_duplicar(self):
        # The handler therefore checks object-count changes on a timer: add missing
        # hardware to doors and remove hardware whose door no longer exists.
        self.sem_rig()
        conj = self.nicho()
        grupo = self.porta_de_giro(conj)
        for o in addon.ferragens._ferragens_portas(grupo):
            addon.ferragens._remover_ferragem(o)        # Duplicated or old door.
        addon.ferragens._conferir_ferragens()
        self.assertEqual(len(addon.ferragens._ferragens_portas(grupo)), 4)
        for o in [grupo, *addon.portas._folhas_portas(grupo)]:
            bpy.data.objects.remove(o, do_unlink=True)    # Door deleted.
        self.assertTrue(any(addon.ferragens.CHAVE_FERRAGEM in o for o in bpy.data.objects))
        addon.ferragens._conferir_ferragens()
        self.assertFalse(any(addon.ferragens.CHAVE_FERRAGEM in o for o in bpy.data.objects))

    def _apagar_malhas_modulo(self, conj):
        bpy.ops.object.select_all(action='DESELECT')
        for o in conj.children_recursive:
            if o.type == 'MESH' and not o.hide_get():
                o.select_set(True)
        bpy.ops.object.delete()

    # Regression, fixed in v279: hidden Empty and rig survived Delete
    # and prevented cleanup of the cabinet folder.
    def test_delete_pecas_limpa_rig_empties_e_pasta(self):
        conj = self.nicho()
        grupo = self.porta_de_giro(conj)
        nome, pasta = conj.name, conj.users_collection[0].name
        self.assertTrue(any(o.type == 'ARMATURE' for o in grupo.children_recursive))
        self._apagar_malhas_modulo(conj)
        self.assertIn(nome, bpy.data.objects)
        addon.ferragens._conferir_ferragens()
        self.assertNotIn(nome, bpy.data.objects)
        self.assertNotIn(pasta, bpy.data.collections)
        self.assertEqual(len(bpy.data.objects), 0)

    def test_delete_so_folha_limpa_rig_e_preserva_carcaca(self):
        conj = self.nicho()
        grupo = self.porta_de_giro(conj)
        antes = {o.name: (o.data.as_pointer(), o.matrix_world.copy())
                 for o in addon.modulos._chapas_do_conjunto(conj)}
        for o in addon.portas._folhas_portas(grupo):
            bpy.data.objects.remove(o, do_unlink=True)
        addon.ferragens._conferir_ferragens()
        self.assertFalse(any(addon.ferragens.CHAVE_FERRAGEM in o
                             for o in bpy.data.objects))
        self.assertIn(conj.name, bpy.data.collections)
        for nome, (malha, pose) in antes.items():
            self.assertEqual(bpy.data.objects[nome].data.as_pointer(), malha)
            self.assertEqual(bpy.data.objects[nome].matrix_world, pose)

    def test_delete_pai_deixa_subgrupos_mas_limpeza_remove_pasta(self):
        conj = self.nicho()
        self.porta_de_giro(conj)
        pasta = conj.users_collection[0].name
        self._apagar_malhas_modulo(conj)
        bpy.data.objects.remove(conj, do_unlink=True)
        addon.ferragens._conferir_ferragens()
        self.assertNotIn(pasta, bpy.data.collections)
        self.assertEqual(len(bpy.data.objects), 0)

    def test_delete_nativo_com_folha_referenciada_limpa_dobradicas_e_grupo_vazio(self):
        conj = self.nicho()
        grupo = self.porta_de_giro(conj)
        folha = addon.portas._folhas_portas(grupo)[0]
        nome, nome_grupo = folha.name, grupo.name
        referencia = bpy.data.objects.new('Referencia do usuario', None)
        bpy.context.scene.collection.objects.link(referencia)
        referencia['folha'] = folha
        corpos = {o.name: o.data.as_pointer() for o in addon.modulos._chapas_do_conjunto(conj)}
        bpy.ops.object.select_all(action='DESELECT')
        folha.select_set(True)
        bpy.context.view_layer.objects.active = folha
        bpy.ops.object.delete()
        self.assertIn(nome, bpy.data.objects)
        self.assertNotIn(nome, bpy.context.scene.objects)
        addon.hud._hover_hud[4242] = {'objeto': grupo}
        addon.ferragens._conferir_ferragens()
        self.assertNotIn(nome_grupo, bpy.data.objects)
        self.assertFalse(addon.hud._hover_hud)
        self.assertFalse(any(addon.ferragens.CHAVE_FERRAGEM in o for o in bpy.data.objects))
        self.assertIs(referencia['folha'], bpy.data.objects[nome])
        self.assertEqual({o.name: o.data.as_pointer() for o in addon.modulos._chapas_do_conjunto(conj)}, corpos)
        addon.hud._selecionar_chapa_hud(bpy.context, bpy.data.objects[next(iter(corpos))])
        self.assertIs(bpy.context.object, conj)

    def test_delete_que_conserva_id_agenda_limpeza_pelo_vinculo_de_cena(self):
        conj = self.nicho()
        grupo = self.porta_de_giro(conj)
        folha = addon.portas._folhas_portas(grupo)[0]
        referencia = bpy.data.objects.new('Referencia que impede remover o ID', None)
        bpy.context.scene.collection.objects.link(referencia)
        referencia['folha'] = folha
        bpy.ops.object.select_all(action='DESELECT')
        folha.select_set(True)
        bpy.context.view_layer.objects.active = folha
        antes = len(bpy.data.objects)
        F = addon.ferragens
        if bpy.app.timers.is_registered(F._conferir_ferragens):
            bpy.app.timers.unregister(F._conferir_ferragens)
        F._contagem_objetos[0] = (antes, tuple((s.name, len(s.objects)) for s in bpy.data.scenes))
        bpy.ops.object.delete()
        bpy.context.view_layer.update()
        addon.chapas.ao_atualizar_depsgraph(bpy.context.scene, None)
        self.assertEqual(len(bpy.data.objects), antes)
        self.assertTrue(bpy.app.timers.is_registered(F._conferir_ferragens))
        self.assertFalse(folha.users_scene)
        F._conferir_ferragens()
        self.assertFalse(any(F.CHAVE_FERRAGEM in o for o in bpy.data.objects))

    # Regression, fixed in v370: opening removed the Delete observer.
    def test_reabrir_projeto_conserva_observador_e_delete_limpa_dobradicas(self):
        grupo = self.porta_de_giro(self.nicho())
        nome = grupo.name
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, 'portas.blend')
            bpy.ops.wm.save_as_mainfile(filepath=caminho)
            grupo = None
            bpy.ops.wm.open_mainfile(filepath=caminho, load_ui=False)
        self.assertIn(addon.chapas.ao_atualizar_depsgraph,
                      bpy.app.handlers.depsgraph_update_post)
        grupo = bpy.data.objects[nome]
        folhas = addon.portas._folhas_portas(grupo)
        corpos = {o.name: o.data.as_pointer()
                  for o in addon.modulos._chapas_do_conjunto(grupo.parent)}
        bpy.ops.object.select_all(action='DESELECT')
        # A single-click selection also deletes the door Empty, as in a real scene.
        for o in [grupo, *folhas]:
            o.select_set(True)
        bpy.context.view_layer.objects.active = grupo
        bpy.ops.object.delete()
        grupo = folhas = None
        bpy.context.view_layer.update()
        addon.chapas.ao_atualizar_depsgraph(bpy.context.scene, None)
        self.assertTrue(bpy.app.timers.is_registered(addon.ferragens._conferir_ferragens))
        addon.ferragens._conferir_ferragens()
        self.assertFalse(any(addon.ferragens.CHAVE_FERRAGEM in o for o in bpy.data.objects))
        self.assertEqual({n: bpy.data.objects[n].data.as_pointer() for n in corpos}, corpos)

    # Regression, fixed in v370: Delete missed the internal selection.
    def test_selecionar_dobradicas_orfas_permite_delete_nativo_e_undo(self):
        F = addon.ferragens
        self.addCleanup(F._ferragens_selecionadas.__setitem__, 0, None)
        grupo = self.porta_de_giro(self.nicho())
        corpos = {o.name for o in addon.modulos._chapas_do_conjunto(grupo.parent)}
        bpy.ops.object.select_all(action='DESELECT')
        for folha in addon.portas._folhas_portas(grupo):
            folha.select_set(True)
        bpy.ops.object.delete()
        # Do not call cleanup; reproduce the file containing leftover hinges.
        caneco = self.ferragens(grupo, 'CANECO')[0]
        self.assertTrue(F._selecionar_ferragem(bpy.context, caneco))
        self.assertIs(bpy.context.object, caneco)
        selecionadas = {o.name for o in bpy.context.selected_objects}
        self.assertTrue(selecionadas)
        self.assertFalse(corpos & selecionadas)
        self.assertTrue(all(F.CHAVE_FERRAGEM in o for o in bpy.context.selected_objects))
        bpy.ops.ed.undo_push(message='Ferragens orfas selecionadas')
        self.assertEqual(bpy.ops.object.delete(), {'FINISHED'})
        grupo = caneco = folha = None
        F._conferir_ferragens()
        self.assertFalse(any(F.CHAVE_FERRAGEM in o for o in bpy.data.objects))
        self.assertTrue(corpos <= set(bpy.context.scene.objects.keys()))
        bpy.ops.ed.undo_push(message='Delete nativo das ferragens')
        bpy.ops.ed.undo()
        addon.eventos._fim_do_desfazer()
        self.assertTrue(selecionadas <= set(bpy.context.scene.objects.keys()))
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        self.assertFalse(any(F.CHAVE_FERRAGEM in o for o in bpy.data.objects))

    def test_selecao_ferragens_respeita_ocultacao_camada_e_desmarcar_nativo(self):
        F = addon.ferragens
        self.addCleanup(F._ferragens_selecionadas.__setitem__, 0, None)
        grupo = self.porta_de_giro(self.nicho())
        canecos = self.ferragens(grupo, 'CANECO')
        oculto, clicado = canecos[:2]
        oculto.hide_set(True)
        fora = next(o for o in F._ferragens_portas(grupo)
                    if o.type == 'MESH' and o not in canecos and o.visible_get())
        colecao = bpy.data.collections.new('Ferragem fora da camada')
        bpy.context.scene.collection.children.link(colecao)
        self.addCleanup(bpy.data.collections.remove, colecao)
        colecao.objects.link(fora)
        for c in list(fora.users_collection):
            if c != colecao:
                c.objects.unlink(fora)
        bpy.context.view_layer.layer_collection.children[colecao.name].exclude = True
        bpy.context.view_layer.update()
        F._selecionar_ferragem(bpy.context, clicado)
        self.assertIs(bpy.context.object, clicado)
        self.assertTrue(F._ferragens_em_edicao(bpy.context))
        self.assertFalse(oculto.select_get())
        self.assertNotIn(fora.name, bpy.context.view_layer.objects)
        self.assertTrue(oculto.hide_get())
        bpy.ops.object.select_all(action='DESELECT')
        self.assertEqual(F._ferragens_em_edicao(bpy.context), [])
        self.assertIsNone(F._ferragens_selecionadas[0])

    def test_porta_com_folha_fora_da_camada_seleciona_so_as_vivas(self):
        conj = self.nicho()
        grupo = self.porta_de_giro(conj, folhas=2)
        apagada, viva = addon.portas._folhas_portas(grupo)
        for c in list(apagada.users_collection):
            c.objects.unlink(apagada)
        bpy.context.view_layer.update()
        addon.hud._selecionar_porta_hud(bpy.context, viva, 'PORTA')
        self.assertIs(bpy.context.object, grupo)
        self.assertEqual(addon.selecao._aba_da_selecao(bpy.context.object), 'PORTAS')
        self.assertTrue(viva.select_get())
        self.assertNotIn(apagada.name, bpy.context.view_layer.objects)
        addon.hud._selecionar_porta_hud(bpy.context, viva, 'FOLHA')
        self.assertIs(bpy.context.object, viva)
        self.assertEqual({o.name for o in bpy.context.selected_objects}, {viva.name})

    def _verificar_exclusao_de_uma_folha(self):
        F = addon.ferragens
        grupo = self.porta_de_giro(self.nicho(), folhas=2)
        apagada, viva = addon.portas._folhas_portas(grupo)
        indice = int(viva['porta_indice'])
        sobreviventes = {o.name: o.matrix_world.copy() for o in F._ferragens_portas(grupo)
                         if o.get('porta_ferragem_folha') == indice}
        removidas = {o.name for o in F._ferragens_portas(grupo)
                     if o.get('porta_ferragem_folha') == apagada['porta_indice']}
        self.assertTrue(sobreviventes)
        self.assertTrue(removidas)
        referencia = bpy.data.objects.new('Referencia da folha apagada', None)
        bpy.context.scene.collection.objects.link(referencia)
        referencia['folha'] = apagada
        bpy.ops.object.select_all(action='DESELECT')
        apagada.select_set(True)
        bpy.context.view_layer.objects.active = apagada
        bpy.ops.object.delete()
        with patch.object(F, '_refazer_ferragens', side_effect=AssertionError('Remontou a outra folha')):
            F._conferir_ferragens()
        self.assertFalse(removidas & set(bpy.data.objects.keys()))
        self.assertTrue(sobreviventes.keys() <= set(bpy.data.objects.keys()))
        for nome, matriz in sobreviventes.items():
            self.assertEqual(bpy.data.objects[nome].matrix_world, matriz)
        F._definir_abertura(bpy.context, viva, .5)
        controles = [o for o in F._ferragens_portas(grupo)
                     if o.get('cabinet_peca') == 'controle']
        for o in controles:
            self.assertAlmostEqual(o.rotation_euler.z,
                                   -math.radians(F._passo_rig(.5)[0]), places=5)

    def test_delete_uma_folha_remove_so_dobradicas_dela_e_preserva_abertura_da_outra(self):
        self._verificar_exclusao_de_uma_folha()

    def test_delete_uma_folha_sem_rig_remove_corpo_e_caneco_correspondentes(self):
        self.sem_rig()
        self._verificar_exclusao_de_uma_folha()

    def test_excluir_colecao_da_view_layer_preserva_porta_e_ferragens(self):
        conj = self.nicho()
        grupo = self.porta_de_giro(conj)
        folha = addon.portas._folhas_portas(grupo)[0]
        nomes = {o.name for o in grupo.children_recursive}
        colecao = bpy.data.collections.new('Folha excluida da View Layer')
        bpy.context.scene.collection.children.link(colecao)
        self.addCleanup(bpy.data.collections.remove, colecao)
        colecao.objects.link(folha)
        for c in list(folha.users_collection):
            if c != colecao:
                c.objects.unlink(folha)
        bpy.context.view_layer.layer_collection.children[colecao.name].exclude = True
        bpy.context.view_layer.update()
        self.assertNotIn(folha.name, bpy.context.view_layer.objects)
        addon.ferragens._conferir_ferragens()
        self.assertTrue(nomes <= set(bpy.data.objects.keys()))
        self.assertTrue(addon.ferragens._ferragens_portas(grupo))

    def test_delete_com_referencia_undo_redo_restaura_porta_e_selecao(self):
        conj = self.nicho()
        grupo = self.porta_de_giro(conj)
        folha = addon.portas._folhas_portas(grupo)[0]
        nome_conj, nome_grupo, nome_folha = conj.name, grupo.name, folha.name
        referencia = bpy.data.objects.new('Referencia que conserva a folha', None)
        bpy.context.scene.collection.objects.link(referencia)
        referencia['folha'] = folha
        nomes = set(bpy.data.objects.keys())
        bpy.ops.ed.undo_push(message='Porta com referencia antes de apagar')
        bpy.ops.object.select_all(action='DESELECT')
        folha.select_set(True)
        bpy.context.view_layer.objects.active = folha
        bpy.ops.object.delete()
        addon.ferragens._conferir_ferragens()
        bpy.ops.ed.undo_push(message='Folha apagada e ferragens removidas')
        conj = grupo = folha = referencia = None
        bpy.ops.ed.undo()
        addon.eventos._fim_do_desfazer()
        bpy.context.view_layer.update()
        addon.ferragens._conferir_ferragens()
        self.assertEqual(set(bpy.data.objects.keys()), nomes)
        addon.hud._selecionar_porta_hud(bpy.context, bpy.data.objects[nome_folha], 'PORTA')
        self.assertEqual(bpy.context.object.name, nome_grupo)
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        bpy.context.view_layer.update()
        addon.ferragens._conferir_ferragens()
        self.assertNotIn(nome_grupo, bpy.data.objects)
        self.assertFalse(any(addon.ferragens.CHAVE_FERRAGEM in o for o in bpy.data.objects))
        peca = addon.modulos._chapas_do_conjunto(bpy.data.objects[nome_conj])[0]
        addon.hud._selecionar_chapa_hud(bpy.context, peca)
        self.assertEqual(bpy.context.object.name, nome_conj)

    def test_folha_ligada_em_outra_cena_nao_e_tratada_como_excluida(self):
        conj = self.nicho()
        grupo = self.porta_de_giro(conj)
        folha = addon.portas._folhas_portas(grupo)[0]
        nomes = {grupo.name, *(o.name for o in grupo.children_recursive)}
        cena = bpy.data.scenes.new('Outra cena com folha viva')
        self.addCleanup(bpy.data.scenes.remove, cena)
        cena.collection.objects.link(folha)
        for c in list(folha.users_collection):
            if c != cena.collection:
                c.objects.unlink(folha)
        bpy.context.view_layer.update()
        self.assertNotIn(folha.name, bpy.context.scene.objects)
        self.assertIn(cena, folha.users_scene)
        addon.ferragens._conferir_ferragens()
        self.assertTrue(nomes <= set(bpy.data.objects.keys()))

    def test_delete_parcial_preserva_porta_e_dobradicas(self):
        conj = self.nicho()
        grupo = self.porta_de_giro(conj)
        nomes = {o.name for o in grupo.children_recursive}
        bpy.data.objects.remove(addon.modulos._chapas_do_conjunto(conj)[0],
                                do_unlink=True)
        addon.ferragens._conferir_ferragens()
        self.assertTrue(nomes <= set(bpy.data.objects.keys()))
        self.assertIn(conj.name, bpy.data.collections)

    def test_limpeza_preserva_objeto_comum_na_pasta_e_grupo(self):
        conj = self.nicho()
        pasta = conj.users_collection[0]
        livre = bpy.data.objects.new('Referencia do usuario', None)
        pasta.objects.link(livre)
        livre.parent = conj
        self._apagar_malhas_modulo(conj)
        addon.ferragens._conferir_ferragens()
        self.assertIs(livre.parent, conj)
        self.assertIn(pasta.name, bpy.data.collections)
        livre.parent = None
        addon.ferragens._conferir_ferragens()
        self.assertIn(livre.name, bpy.data.objects)
        self.assertIn(pasta.name, bpy.data.collections)

    def test_limpeza_rig_preserva_filho_comum_e_dados_compartilhados(self):
        conj = self.nicho()
        grupo = self.porta_de_giro(conj)
        rig = next(o for o in grupo.children_recursive
                   if o.get('cabinet_peca') == 'armacao')
        livre = bpy.data.objects.new('Referencia do rig', None)
        bpy.context.collection.objects.link(livre)
        livre.parent = rig
        malha = next(o.data for o in grupo.children_recursive if o.type == 'MESH')
        copia = bpy.data.objects.new('Copia independente', malha)
        bpy.context.collection.objects.link(copia)
        nome = rig.name
        for o in addon.portas._folhas_portas(grupo):
            bpy.data.objects.remove(o, do_unlink=True)
        addon.ferragens._conferir_ferragens()
        self.assertEqual(livre.parent.name, nome)
        self.assertIs(copia.data, malha)
        self.assertGreater(malha.users, 0)

    def test_limpeza_so_remove_pastas_marcadas_e_comodos_vazios(self):
        conj = self.nicho()
        nome = conj.name
        comodo = bpy.data.collections.new('Comodo de teste')
        comodo[addon.orcamento.MARCA_COLECAO_COMODO] = 1
        bpy.context.scene.collection.children.link(comodo)
        comodo.children.link(conj.users_collection[0])
        comum = bpy.data.collections.new('Pasta comum vazia')
        bpy.context.scene.collection.children.link(comum)
        self._apagar_malhas_modulo(conj)
        addon.ferragens._conferir_ferragens()
        self.assertNotIn(nome, bpy.data.collections)
        self.assertNotIn('Comodo de teste', bpy.data.collections)
        self.assertIn(comum.name, bpy.data.collections)
        bpy.data.collections.remove(comum)

    # Regression, fixed in v280: the asset container had the native tag
    # but lacked the cabinet Collection marker.
    def test_append_delete_limpa_embalagem_asset_legada_com_fake_user(self):
        conj = self.nicho()
        arquivo = addon.biblioteca.salvar_na_biblioteca(
            [conj, *conj.children_recursive], 'Embalagem legada teste', True)
        with open(arquivo, 'rb') as f:
            antes = f.read()
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        addon.ferragens._conferir_ferragens()
        novos, _raizes, erro = addon.biblioteca.inserir_preset(
            bpy.context, os.path.dirname(arquivo), os.path.basename(arquivo), 'modulo')
        self.assertFalse(erro)
        embalagem = next(c for c in bpy.data.collections if c.asset_data)
        self.assertNotIn(addon.modulos.MARCA_COLECAO_MODULO, embalagem)
        self.assertTrue(embalagem.use_fake_user)
        self.assertIsNotNone(embalagem.asset_data.tags.get('chapa-g3'))
        nome = embalagem.name
        # Renaming the folder must not break asset identification.
        embalagem.name = 'Pasta renomeada pelo usuario'
        nome = embalagem.name
        bpy.ops.object.select_all(action='DESELECT')
        for o in novos:
            o.select_set(True)
        bpy.ops.object.delete()
        addon.ferragens._conferir_ferragens()
        self.assertNotIn(nome, bpy.data.collections)
        with open(arquivo, 'rb') as f:
            self.assertEqual(f.read(), antes)

    def _embalagem_asset_teste(self, nome):
        c = bpy.data.collections.new(nome)
        bpy.context.scene.collection.children.link(c)
        c.asset_mark()
        c.asset_data.tags.new('chapa-g3')
        c.use_fake_user = True
        return c

    def test_embalagem_asset_nao_vazia_e_assets_alheios_sao_preservados(self):
        nossa = self._embalagem_asset_teste('Modulo da biblioteca')
        objeto = bpy.data.objects.new('Referencia independente', None)
        nossa.objects.link(objeto)
        comum = bpy.data.collections.new('Armario vazio do usuario')
        bpy.context.scene.collection.children.link(comum)
        alheia = self._embalagem_asset_teste('Asset de outro addon')
        alheia.asset_data.tags.remove(alheia.asset_data.tags.get('chapa-g3'))
        nomes = {c.name for c in (nossa, comum, alheia)}
        addon.ferragens._conferir_ferragens()
        self.assertTrue(nomes <= set(bpy.data.collections.keys()))
        self.assertIn(objeto.name, bpy.data.objects)
        for c in (nossa, comum, alheia):
            bpy.data.collections.remove(c)

    def test_embalagens_asset_aninhadas_limpam_de_dentro_para_fora(self):
        externa = self._embalagem_asset_teste('Embalagem externa')
        interna = self._embalagem_asset_teste('Embalagem interna')
        externa.children.link(interna)
        nomes = (externa.name, interna.name)
        addon.ferragens._conferir_ferragens()
        for nome in nomes:
            self.assertNotIn(nome, bpy.data.collections)
        externa = self._embalagem_asset_teste('Embalagem com pasta comum')
        comum = bpy.data.collections.new('Organizacao independente')
        externa.children.link(comum)
        addon.ferragens._conferir_ferragens()
        self.assertIn(externa.name, bpy.data.collections)
        self.assertIn(comum.name, externa.children)
        bpy.data.collections.remove(comum)
        bpy.data.collections.remove(externa)

    def test_undo_redo_restaura_embalagem_asset_e_sua_identificacao(self):
        conj = self.nicho()
        embalagem = self._embalagem_asset_teste('Embalagem undo teste')
        for o in [conj, *conj.children_recursive]:
            embalagem.objects.link(o)
        nome = embalagem.name
        bpy.ops.ed.undo_push(message='Antes do Delete com asset')
        self._apagar_malhas_modulo(conj)
        addon.ferragens._conferir_ferragens()
        self.assertNotIn(nome, bpy.data.collections)
        bpy.ops.ed.undo_push(message='Delete com limpeza do asset')
        conj = embalagem = None
        bpy.ops.ed.undo()
        addon.eventos._fim_do_desfazer()
        addon.ferragens._conferir_ferragens()
        c = bpy.data.collections[nome]
        self.assertTrue(c.use_fake_user)
        self.assertIsNotNone(c.asset_data.tags.get('chapa-g3'))
        self.assertGreater(len(c.all_objects), 0)
        c = None
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        addon.ferragens._conferir_ferragens()
        self.assertNotIn(nome, bpy.data.collections)

    def test_limpeza_adiada_em_undo_edicao_ocupado_e_modal(self):
        conj = self.nicho()
        nome = conj.name
        self._apagar_malhas_modulo(conj)
        for estado in (addon.eventos._desfazendo, addon.chapas._ocupado):
            with self.subTest(estado=id(estado)), patch.object(
                    addon.eventos, '_ha_modal_ativo', return_value=False):
                estado[0] = True
                try:
                    self.assertEqual(addon.ferragens._conferir_ferragens(), .2)
                    self.assertIn(nome, bpy.data.objects)
                finally:
                    estado[0] = False
        with patch.object(addon.eventos, '_ha_modal_ativo', return_value=True):
            self.assertEqual(addon.ferragens._conferir_ferragens(), .2)
        peca = addon.chapas.nova_chapa('Em edicao', 100, 100, 18,
                                      (0, 0, 0), (0, 0, 0), bpy.context)
        bpy.context.view_layer.objects.active = peca
        peca.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            self.assertEqual(addon.ferragens._conferir_ferragens(), .2)
            self.assertIn(nome, bpy.data.objects)
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        addon.ferragens._conferir_ferragens()
        self.assertNotIn(nome, bpy.data.objects)

    def test_delete_undo_redo_restauram_modulo_e_pasta(self):
        conj = self.nicho()
        self.porta_de_giro(conj)
        nome = conj.name
        nomes = set(bpy.data.objects.keys())
        bpy.ops.ed.undo_push(message='Modulo antes do Delete')
        self._apagar_malhas_modulo(conj)
        addon.ferragens._conferir_ferragens()
        bpy.ops.ed.undo_push(message='Delete e limpeza')
        bpy.ops.ed.undo()
        bpy.context.view_layer.update()
        self.assertEqual(set(bpy.data.objects.keys()), nomes)
        self.assertIn(nome, bpy.data.collections)
        # In background mode, the event loop does not call the tick that releases undo.
        addon.eventos._fim_do_desfazer()
        addon.ferragens._conferir_ferragens()
        self.assertEqual(set(bpy.data.objects.keys()), nomes)
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        addon.ferragens._conferir_ferragens()
        self.assertNotIn(nome, bpy.data.objects)
        self.assertNotIn(nome, bpy.data.collections)

    def test_placa_da_reta_fica_na_face_interna(self):
        # User screenshot: the full-overlay mounting plate penetrated the side by ~3 mm.
        # The model covers 12.75 mm, whereas full overlay on 18 mm covers 16 mm.
        # Like a real overlay adjustment screw, move the plate and support to the face;
        # the cup remains in the leaf and opening behavior stays unchanged.
        conj = self.nicho()
        grupo = self.porta_de_giro(conj)
        L = grupo['porta_vao_largura_mm']
        inversa = grupo.matrix_world.inverted()
        grafo = bpy.context.evaluated_depsgraph_get()

        def lado(o):
            while o.get('cabinet_peca') != 'raiz':
                o = o.parent
            return o[addon.ferragens.CHAVE_ID_FERRAGEM].split('_')[1]

        def passou(x, ld):
            # Millimeters into the panel; inner face is x = 0 or x = L.
            return -x if ld == 'ESQUERDA' else x - L
        vistas = 0
        for o in addon.ferragens._ferragens_portas(grupo):
            if o.get('cabinet_peca') not in ('base', 'suporte'):
                continue
            avaliado = o.evaluated_get(grafo)
            malha = avaliado.to_mesh()
            pior = max(passou((inversa @ (o.matrix_world @ v.co)).x * 1000.0,
                              lado(o)) for v in malha.vertices)
            avaliado.to_mesh_clear()
            self.assertLessEqual(pior, 1e-3, (o.name, lado(o)))
            vistas += 1
        self.assertGreaterEqual(vistas, 4)
        # The wizard's wire preview follows the same rule.
        medidas = addon.ferragens._porta_calculada(grupo)
        itens = [i for i in addon.ferragens._ferragens_da_porta(*medidas)
                 if i['forma'] == 'RIG']
        rig = addon.arame._dados_arame_rig()
        for item in itens:
            pecas, _pontos = addon.arame._arame_dos_itens([item])
            ld = item['id'].split('_')[1]
            for matriz, chave in pecas:
                if addon.ferragens.MALHAS_CALCO.get(chave) is None \
                        or 'Parafuso' in chave:
                    continue
                pior = max(passou((matriz @ v).x * 1000.0, ld)
                           for v in rig['malhas'][chave])
                self.assertLessEqual(pior, 1e-3, (chave, ld))

    def test_dobradica_reta_e_o_rig_do_usuario(self):
        # User request: full-overlay hinges import the model and rig asset from
        # tools/hardware/extract_hinge.py without recreating either; leaf motion follows
        # the measured rig, and the cup cuts the leaf with a Boolean.
        conj = self.nicho()
        grupo = self.porta_de_giro(conj)
        folha = addon.portas._folhas_portas(grupo)[0]
        raizes = self.ferragens(grupo, 'DOBRADICA_RIG')
        n = len(raizes)
        self.assertGreaterEqual(n, 2)
        pecas = addon.ferragens._ferragens_portas(grupo)
        por_peca = lambda nome: [o for o in pecas if o.get('cabinet_peca') == nome]

        def raiz_de(o):
            while o.get('cabinet_peca') != 'raiz':
                o = o.parent
            return o

        # Each copy includes its own complete rig, driver and IK.
        for arm in por_peca('armacao'):
            alvo = arm.animation_data.drivers[0].driver.variables[0].targets[0].id
            self.assertIs(raiz_de(alvo), raiz_de(arm))
        for ik in por_peca('armacao_ik'):
            alvos = [c.target for pb in ik.pose.bones for c in pb.constraints
                     if c.type == 'IK']
            self.assertEqual(len(alvos), 1)
            self.assertIs(raiz_de(alvos[0]), raiz_de(ik))
        self.assertEqual(len(por_peca('armacao_ik')), n)
        # No restrictions: every part remains selectable and editable in Blender.
        self.assertFalse(any(o.hide_select for o in pecas))
        # But it does not highlight with the door or cabinet.
        addon.hud._selecionar_chapa_hud(bpy.context, folha)
        self.assertFalse(any(o.select_get() for o in pecas))
        # Double click selects one part natively; Tab edits that part's mesh.
        cabeca = por_peca('cabeca')[0]
        addon.ferragens._selecionar_peca(bpy.context, cabeca)
        self.assertEqual(bpy.context.selected_objects, [cabeca])
        self.assertIs(bpy.context.view_layer.objects.active, cabeca)
        self.assertEqual(bpy.ops.object.mode_set(mode='EDIT'), {'FINISHED'})
        bpy.ops.object.mode_set(mode='OBJECT')
        # The leaf preserves the model's 1.86 mm cabinet clearance; without it,
        # the open leaf's corner entered the cabinet, as shown in the user's screenshot.
        dados = addon.ferragens._dados_dobradica_reta()
        costas = addon.ferragens._dados_da_folha(folha)[3][2] - folha.chapa_espessura_mm / 2
        self.assertAlmostEqual(costas, dados['folga_modulo_mm'], places=3)
        # At no point in its rotation may the leaf cross the cabinet front.
        P = addon.portas._caixa_do_modulo(conj)[2]
        local = lambda v: (conj.matrix_world.inverted() @ v) * 1000.0
        for passo in range(41):
            addon.ferragens._definir_abertura(bpy.context, folha, passo / 40.0)
            fundo = max(local(folha.matrix_world @ Vector(c)).y
                        for c in folha.bound_box)
            self.assertLessEqual(fundo, -P / 2.0 + 1e-3, passo)
        addon.ferragens._definir_abertura(bpy.context, folha, 0.0)
        # Copies share the mesh to avoid inflating file size.
        cabecas = por_peca('cabeca')
        self.assertEqual(len({o.data.name for o in cabecas}), 1)
        # The cup cuts the leaf: one Boolean per hinge, using that hinge's cutter.
        furos = [m for m in folha.modifiers
                 if m.name.startswith(addon.ferragens.PREFIXO_FURO)]
        self.assertEqual(len(furos), n)
        self.assertTrue(all(m.operation == 'DIFFERENCE'
                            and m.object.get('cabinet_peca') == 'furo'
                            for m in furos))
        # The head follows the leaf exactly; the leaf motion table reflects the real rig.
        bpy.context.view_layer.update()
        relativa = lambda c: folha.matrix_world.inverted() @ c.matrix_world
        fechadas = [relativa(c) for c in cabecas]
        pior = [0.0, 0.0]
        for passo in range(1, 21):
            addon.ferragens._definir_abertura(bpy.context, folha, passo / 20.0)
            for cabeca, antes in zip(cabecas, fechadas):
                agora = relativa(cabeca)
                giro = agora.to_quaternion().rotation_difference(
                    antes.to_quaternion()).angle
                pior[0] = max(pior[0], (agora.translation - antes.translation)
                              .length * 1000.0)
                pior[1] = max(pior[1], math.degrees(giro))
        print('[rig] folha x cabeca: pior %.4f mm, %.4f graus' % tuple(pior))
        self.assertLess(pior[0], 0.05)
        self.assertLess(pior[1], 0.05)
        self.assertEqual(addon.portas_viewport._texto_abertura(folha),
                         '%d%s' % (round(addon.ferragens._giro_maximo_rig()),
                                   addon.portas_viewport.SIMBOLO_GRAU))
        # An old asset copy with English names and an obsolete hole is replaced
        # with the current asset when the door is rebuilt.
        velha = raizes[0]
        raizes[0]['cabinet_versao'] = 1
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'dobradicas_margem_mm', 120.0), '')
        self.assertFalse(addon.ferragens._vivo(velha))
        versao = addon.ferragens._dados_dobradica_reta()['versao']
        self.assertTrue(all(o['cabinet_versao'] == versao
                            for o in self.ferragens(grupo, 'DOBRADICA_RIG')))
        self.assertEqual(len(self.ferragens(grupo, 'DOBRADICA_RIG')), n)
        folha = addon.portas._folhas_portas(grupo)[0]
        # Half overlay removes the entire rig and hole, restoring the boxes.
        addon.ferragens._definir_abertura(bpy.context, folha, 0.0)
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'dobradica', 'CURVA'), '')
        self.assertFalse([o for o in bpy.data.objects if o.get('cabinet_peca')])
        self.assertFalse([m for m in bpy.data.meshes
                          if m.get('cabinet_origem') and m.users])
        folha = addon.portas._folhas_portas(grupo)[0]
        self.assertFalse([m for m in folha.modifiers
                          if m.name.startswith(addon.ferragens.PREFIXO_FURO)])
        self.assertEqual(len(self.ferragens(grupo, 'DOBRADICA')), n)

    def test_abrir_a_folha_gira_na_borda_da_dobradica(self):
        self.sem_rig()
        conj = self.nicho()
        L = addon.portas._caixa_do_modulo(conj)[0]
        grupo = self.porta_de_giro(conj)
        folha = addon.portas._folhas_portas(grupo)[0]
        corpo = self.ferragens(grupo, 'DOBRADICA')[0]
        caneco = self.ferragens(grupo, 'CANECO')[0]
        fechada = folha.matrix_world.copy()
        corpo_antes = corpo.matrix_world.translation.copy()
        caneco_antes = caneco.matrix_world.translation.copy()
        local = lambda v: (conj.matrix_world.inverted() @ v) * 1000.0
        self.assertTrue(addon.ferragens._definir_abertura(bpy.context, folha, 1.0))
        l, a, e, _c = addon.ferragens._dados_da_folha(folha)
        # Pivot: the rear corner on the hinge side remains fixed, as with a cup hinge;
        # when open, no gap separates the leaf from the cabinet.
        eixo = Vector((-l, 0.0, -e)) / 2000.0
        self.assertLess((folha.matrix_world @ eixo - fechada @ eixo).length, 1e-6)
        frente = Vector((-l, 0.0, e)) / 2000.0
        self.assertGreater((folha.matrix_world @ frente
                            - fechada @ frente).length, 0.01)
        # The other side moves outward (front = -Y).
        ponta = Vector((l, 0.0, e)) / 2000.0
        self.assertLess(local(folha.matrix_world @ ponta).y,
                        local(fechada @ ponta).y - 100)
        x_folha = folha.matrix_world.to_3x3() @ Vector((1, 0, 0))
        x_vao = grupo.matrix_world.to_3x3() @ Vector((1, 0, 0))
        self.assertAlmostEqual(math.degrees(x_folha.angle(x_vao)), 110.0, places=3)
        self.assertEqual(addon.portas_viewport._texto_abertura(folha), '110' + addon.portas_viewport.SIMBOLO_GRAU)
        # The cup rotates with the leaf; the body stays on the cabinet.
        self.assertGreater((caneco.matrix_world.translation - caneco_antes).length,
                           0.01)
        self.assertLess((corpo.matrix_world.translation - corpo_antes).length, 1e-9)
        # The selected-door outline follows the open leaf.
        contorno = addon.portas_viewport._desenho_da_porta(grupo)['folhas'][0]
        self.assertLess(min(local(v).y for v in contorno),
                        min(local(fechada @ Vector(c)).y
                            for c in folha.bound_box) - 100)
        # Opening survives cabinet resizing.
        addon.ferragens._definir_abertura(bpy.context, folha, 0.5)
        conj.conj_largura_mm = L + 100
        bpy.context.view_layer.update()
        folha = addon.portas._folhas_portas(grupo)[0]
        self.assertAlmostEqual(folha[addon.ferragens.CHAVE_ABERTURA], 0.5)
        x_folha = folha.matrix_world.to_3x3() @ Vector((1, 0, 0))
        self.assertAlmostEqual(math.degrees(x_folha.angle(x_vao)), 55.0, places=3)
        self.assertAlmostEqual(folha.chapa_largura_mm,
                               L + 100 - 2 * addon.portas.RESPIRO_PORTA_MM, places=3)
        # Closing returns exactly to the original position.
        addon.ferragens._definir_abertura(bpy.context, folha, 0.0)
        self.assertLess((folha.matrix_world.translation
                         - addon.ferragens._matriz_fechada(folha).translation).length, 1e-9)

    def test_basculante_tem_pistoes_com_mira(self):
        # Gas-strut rigging: each half aims at the other endpoint using Damped Track,
        # extending with door opening; the rod stays below.
        conj = self.nicho()
        grupo = self.porta_de_giro(conj, abertura='BASCULANTE',
                                   dobradica_lado='CIMA', pistoes_qtd=2)
        folha = addon.portas._folhas_portas(grupo)[0]
        self.assertEqual(len(self.ferragens(grupo, 'DOBRADICA')), 2)
        corpos = self.ferragens(grupo, 'PISTAO_CORPO')
        hastes = self.ferragens(grupo, 'PISTAO_HASTE')
        pontos = self.ferragens(grupo, 'PISTAO_PONTO')
        self.assertEqual((len(corpos), len(hastes), len(pontos)), (2, 2, 2))
        local = lambda v: (conj.matrix_world.inverted() @ v) * 1000.0

        def comprimento(o):
            return max(v.co.y for v in o.data.vertices) * 1000.0

        for corpo, haste, ponto in zip(corpos, hastes, pontos):
            self.assertEqual((corpo.parent, haste.parent, ponto.parent),
                             (folha, grupo, folha))
            self.assertEqual(corpo.constraints[0].type, 'DAMPED_TRACK')
            self.assertEqual(corpo.constraints[0].target, haste)
            self.assertEqual(haste.constraints[0].target, ponto)
            # Rod downward: the side-panel attachment is the lower endpoint.
            self.assertLess(local(haste.matrix_world.translation).z,
                            local(ponto.matrix_world.translation).z)
        for fracao in (0.0, 1.0):
            addon.ferragens._definir_abertura(bpy.context, folha, fracao)
            for corpo, haste, ponto in zip(corpos, hastes, pontos):
                a = corpo.matrix_world.translation
                b = haste.matrix_world.translation
                y_corpo = (corpo.matrix_world.to_3x3() @ Vector((0, 1, 0))).normalized()
                y_haste = (haste.matrix_world.to_3x3() @ Vector((0, 1, 0))).normalized()
                self.assertAlmostEqual(y_corpo.dot((b - a).normalized()), 1.0, places=4)
                self.assertAlmostEqual(y_haste.dot((a - b).normalized()), 1.0, places=4)
                distancia = (b - a).length * 1000.0
                # No protrusion past the endpoint when closed, or gap when open.
                if fracao == 0.0:
                    self.assertLessEqual(comprimento(corpo), distancia + 1e-3)
                else:
                    self.assertGreaterEqual(comprimento(corpo) + comprimento(haste),
                                            distancia - 1e-3)
                # Automatic: half the strut length when closed, full length when open.
                self.assertAlmostEqual(distancia, 2 * comprimento(corpo)
                                       if fracao else comprimento(corpo),
                                       places=2)
        # Full overlay opens as far as the user's rig: 91.7 degrees.
        self.assertEqual(addon.portas_viewport._texto_abertura(folha), '%d%s' % (
            round(addon.ferragens._giro_maximo_rig()), addon.portas_viewport.SIMBOLO_GRAU))
        # Open like the real hardware in the user's screenshot: the edge stays by
        # the cabinet front without a thickness-sized gap. As with a real cup hinge
        # at 90 degrees, the leaf extends slightly into the opening rather than
        # remaining level with the top.
        cantos = lambda m: [local(m @ Vector(c)) for c in folha.bound_box]
        fechada = cantos(addon.ferragens._matriz_fechada(folha))
        aberta = cantos(folha.matrix_world)
        vao = max(v.y for v in fechada) - max(v.y for v in aberta)
        altura = min(v.z for v in aberta) - max(v.z for v in fechada)
        self.assertLess(abs(vao), 3.0, (vao, altura))
        self.assertTrue(-30.0 < altura < 0.0, (vao, altura))
        # Real gas-strut volume: the body is thicker than the rod; one mounting bracket
        # stays on the side panel and the other rotates with the leaf.
        raio = lambda o: max(v.co.x for v in o.data.vertices) * 1000.0
        self.assertGreater(raio(corpos[0]), raio(hastes[0]))
        suportes = self.ferragens(grupo, 'PISTAO_SUPORTE')
        self.assertEqual(sorted(s.parent.name for s in suportes),
                         sorted([grupo.name] * 2 + [folha.name] * 2))

    def test_previa_das_dobradicas_e_o_arame_da_peca(self):
        # User request: hinge preview uses the real part's wireframe rather than a box.
        # The wizard plans using the same hardware the door assembles,
        # so preview wires coincide with the rig.
        conj = self.nicho()
        grupo = self.porta_de_giro(conj)
        bpy.context.view_layer.update()
        p, L, A, folhas = addon.ferragens._porta_calculada(grupo)
        pecas, pontos = addon.arame._arame_dos_itens(
            addon.ferragens._ferragens_da_porta(p, L, A, folhas))
        rig = addon.arame._dados_arame_rig()
        raizes = [o for o in addon.ferragens._ferragens_portas(grupo)
                  if o.get('cabinet_peca') == 'raiz']
        self.assertEqual(len(pecas), len(raizes) * len(rig['pecas']))
        self.assertEqual(pontos, [])
        partes = [o for o in addon.ferragens._ferragens_portas(grupo) if o.type == 'MESH'
                  and o.get('cabinet_peca') not in ('furo', 'controle')]
        for m, malha in pecas:
            mundo = grupo.matrix_world @ m
            self.assertTrue(any(
                o.data.get('cabinet_origem') == malha
                and max(abs(a - b) for la, lb in zip(mundo, o.matrix_world)
                        for a, b in zip(la, lb)) < 1e-4
                for o in partes), malha)
        # When selected, the wireframe comes from the copies in their current pose.
        pecas_sel, pontos_sel = addon.arame._arame_ferragens(grupo, {'DOBRADICA'})
        self.assertEqual(len(pecas_sel), len(pecas))
        self.assertEqual(pontos_sel, [])
        # Outline only for performance; the evaluated mesh has about 190,000 edges.
        segmentos = sum(len(v) for v in rig['malhas'].values()) // 2
        self.assertTrue(1000 < segmentos < 6000, segmentos)

    def test_previa_de_caixas_e_pistoes_e_arame(self):
        # Half-overlay/inset boxes and gas struts use each part's own shape.
        self.sem_rig()
        conj = self.nicho()
        grupo = self.porta_de_giro(conj, abertura='BASCULANTE',
                                   dobradica_lado='CIMA', pistoes_qtd=2)
        p, L, A, folhas = addon.ferragens._porta_calculada(grupo)
        itens = addon.ferragens._ferragens_da_porta(p, L, A, folhas)
        pecas, pontos = addon.arame._arame_dos_itens(itens)
        self.assertEqual(pecas, [])
        caixas = sum(1 for i in itens if i['forma'] == 'CAIXA')
        cilindros = sum(1 for i in itens if i['forma'] in ('CILINDRO', 'HASTE'))
        lados = addon.arame.LADOS_CILINDRO_ARAME
        self.assertEqual(len(pontos), caixas * 24 + cilindros * (lados * 4 + 8))
        _pecas, pistoes = addon.arame._arame_ferragens(grupo, {'PISTAO'})
        self.assertTrue(pistoes)
        self.assertEqual(len(pistoes) % 2, 0)

    def test_ferragens_selecionadas_editam_na_aba_portas(self):
        # User request: when hardware is selected, the Doors tab shows only its
        # editable settings: hinge count and spacing, or gas-strut count and top offset,
        # without door dimensions. Editing updates the door while preserving
        # the hardware selection.
        self.addCleanup(addon.ferragens._ferragens_selecionadas.__setitem__, 0, None)
        cena = bpy.context.scene
        self.addCleanup(setattr, cena, 'cabinet_aba', 'MODULOS')
        cena.cabinet_aba = 'MODULOS'
        conj = self.nicho()
        grupo = self.porta_de_giro(conj, abertura='BASCULANTE',
                                   dobradica_lado='CIMA', pistoes_qtd=2)
        caneco = self.ferragens(grupo, 'CANECO')[0]
        addon.ferragens._selecionar_ferragem(bpy.context, caneco)
        self.assertEqual(cena.cabinet_aba, 'PORTAS')      # Switched to its tab.

        def painel():
            _c, conteudo, _r = addon.gaveta._partes_gaveta(
                addon.gaveta._widgets_gaveta(bpy.context, 320, 1400))
            return [v[5] for v in addon.gaveta._paineis_gaveta(conteudo)[0] if v[5]]

        acoes = painel()
        campos = {a[2]: a for a in acoes if a[0] == 'medida'}
        self.assertEqual(set(campos), {'dobradicas_margem_mm'})
        self.assertEqual(campos['dobradicas_margem_mm'][1], 'ferragens')
        # Hinge type is automatic: thumbnails are informational and non-clickable,
        # with the detected type highlighted.
        retratos = [a for a in acoes if a[0] == 'escolha' and a[1] == 'dobradica']
        self.assertEqual([a[2] for a in retratos if a[3]],
                         [grupo['porta_parametros']['dobradica']])
        self.assertFalse(any(a[4] for a in retratos))
        # Count uses a counter, per the user's mockup, without an acceptance step;
        # the selected hardware updates immediately.
        self.assertFalse([a for a in acoes if a[0] == 'escolha'
                          and a[1] == addon.portas.CONFIRMAR_ETAPA])
        (qtd,) = [a for a in acoes if a[0] == 'contador']
        n = len(addon.ferragens._dobradicas_da_porta(
            *addon.ferragens._porta_calculada(grupo))[0][1])
        self.assertEqual(qtd, ('contador', 'dobradicas_qtd', n,
                               *addon.portas.LIMITES_DOBRADICAS,
                               addon.gaveta.ALVO_FERRAGENS))
        # Editing changes the door while hardware remains selected.
        self.assertEqual(addon.ferragens._editar_ferragens_selecionadas(
            bpy.context, 'dobradicas_qtd', 4), '')
        self.assertEqual(grupo['porta_parametros']['dobradicas_qtd'], 4)
        self.assertEqual(len(self.ferragens(grupo, 'CANECO')), 4)
        self.assertEqual(addon.ferragens._ferragens_em_edicao(bpy.context)[0][1],
                         {'DOBRADICA'})
        self.assertEqual(bpy.ops.object.cabinet_editar_medida_gaveta(
            'EXEC_DEFAULT', dono='ferragens', propriedade='dobradicas_margem_mm',
            valor=0.06), {'FINISHED'})
        self.assertAlmostEqual(
            grupo['porta_parametros']['dobradicas_margem_mm'], 60.0, places=3)
        # Shift-select a gas strut: both types appear, each in its own section.
        addon.ferragens._selecionar_ferragem(bpy.context,
                                   self.ferragens(grupo, 'PISTAO_SUPORTE')[0],
                                   somar=True)
        campos = {a[2] for a in painel() if a[0] == 'medida'}
        self.assertEqual(campos, {'dobradicas_margem_mm', 'pistoes_offset_mm'})
        # The gas strut stops at its travel limit: too far down clamps to the automatic
        # position, stored as 0; moving up stores the entered value.
        addon.ferragens._editar_ferragens_selecionadas(bpy.context, 'pistoes_offset_mm',
                                             5000.0)
        p, _l, altura, folhas = addon.ferragens._porta_calculada(grupo)
        g = addon.portas._pistao_do_vao(altura, folhas[0], 5000.0, p)
        mostrado = addon.ferragens._dados_ferragens_selecionadas(bpy.context)
        self.assertAlmostEqual(mostrado['PISTAO']['mm'], g['offset_max'],
                               delta=0.5)
        acima = g['offset_max'] - 40.0
        addon.ferragens._editar_ferragens_selecionadas(bpy.context, 'pistoes_offset_mm',
                                             acima)
        p = grupo['porta_parametros']
        self.assertAlmostEqual(float(p['pistoes_offset_mm']), addon.portas._pistao_do_vao(
            altura, folhas[0], acima, dict(p))['offset'], delta=0.01)
        self.assertGreater(float(p['pistoes_offset_mm']), 0.0)
        self.assertTrue(addon.ferragens._ferragens_em_edicao(bpy.context))

    def test_clique_na_ferragem_seleciona_as_do_modulo(self):
        # User request: clicking a hinge selects all cabinet hinges; clicking a strut
        # selects all struts. Shift adds the other type. Nothing else stays selected,
        # so the door and cabinet have no selection outline.
        self.addCleanup(addon.ferragens._ferragens_selecionadas.__setitem__, 0, None)
        conj = self.nicho()
        grupo = self.porta_de_giro(conj, abertura='BASCULANTE',
                                   dobradica_lado='CIMA', pistoes_qtd=2)
        folha = addon.portas._folhas_portas(grupo)[0]
        addon.hud._selecionar_porta_hud(bpy.context, folha, 'PORTA')
        caneco = self.ferragens(grupo, 'CANECO')[1]
        pistao = self.ferragens(grupo, 'PISTAO_SUPORTE')[0]
        self.assertFalse(addon.ferragens._selecionar_ferragem(
            bpy.context, self.ferragens(grupo, 'PISTAO_PONTO')[0]))

        self.assertTrue(addon.ferragens._selecionar_ferragem(bpy.context, caneco))
        self.assertTrue(bpy.context.selected_objects)
        self.assertIs(bpy.context.object, caneco)
        self.assertTrue(all(addon.ferragens.CHAVE_FERRAGEM in o
                            for o in bpy.context.selected_objects))
        (achado, tipos), = addon.ferragens._ferragens_em_edicao(bpy.context)
        self.assertEqual((achado, tipos), (grupo, {'DOBRADICA'}))
        # Full overlay uses the volume of the rig's large parts: base, support and cup.
        n = len([o for o in addon.ferragens._ferragens_portas(grupo)
                 if o.get('cabinet_peca') in addon.ferragens.PECAS_REALCE_RIG])
        self.assertEqual(len(addon.ferragens._caixas_ferragens(grupo, tipos)), n)
        # Shift-click the strut to select both types; repeat to leave only hinges.
        addon.ferragens._selecionar_ferragem(bpy.context, pistao, somar=True)
        self.assertEqual(addon.ferragens._ferragens_em_edicao(bpy.context)[0][1],
                         {'DOBRADICA', 'PISTAO'})
        caixas = addon.ferragens._caixas_ferragens(grupo, {'DOBRADICA', 'PISTAO'})
        self.assertEqual(len(caixas), n + 4 * 2)    # Body, rod and two mounting brackets.
        addon.ferragens._selecionar_ferragem(bpy.context, pistao, somar=True)
        self.assertEqual(addon.ferragens._ferragens_em_edicao(bpy.context)[0][1],
                         {'DOBRADICA'})
        # Without Shift, replace the selection.
        addon.ferragens._selecionar_ferragem(bpy.context, pistao)
        self.assertEqual(addon.ferragens._ferragens_em_edicao(bpy.context)[0][1],
                         {'PISTAO'})
        # The strut volume comes from its real mesh, with the body between endpoints.
        corpo = self.ferragens(grupo, 'PISTAO_CORPO')[0]
        caixa = addon.ferragens._caixas_ferragens(grupo, {'PISTAO'})[0]
        self.assertLess((sum(caixa, Vector()) / 8 - corpo.matrix_world
                         @ Vector((0, corpo.dimensions.y / 2, 0))).length, 1e-4)
        # Selecting anything else ends the mode.
        addon.hud._selecionar_porta_hud(bpy.context, folha, 'PORTA')
        self.assertEqual(addon.ferragens._ferragens_em_edicao(bpy.context), [])
        self.assertIsNone(addon.ferragens._ferragens_selecionadas[0])

    def test_controladores_das_ferragens(self):
        # Alt: one controller per hardware type. The hinge controller follows the edge
        # with mirrored margin; the strut controller follows the side up to its travel limit.
        conj = self.nicho()
        grupo = self.porta_de_giro(conj, abertura='BASCULANTE',
                                   dobradica_lado='CIMA', pistoes_qtd=2)
        controles = addon.ferragens._controles_ferragens(grupo, {'DOBRADICA', 'PISTAO'})
        self.assertEqual([c[0] for c in controles], ['DOBRADICA', 'PISTAO'])
        (_t, ponto_d, a_d, b_d), (_t2, ponto_p, a_p, b_p) = controles
        # Full overlay: at the first hinge rig's root.
        raiz = next(o for o in self.ferragens(grupo, 'DOBRADICA_RIG')
                    if o[addon.ferragens.CHAVE_ID_FERRAGEM].endswith('_0'))
        self.assertLess((ponto_d - raiz.matrix_world.translation).length, 1e-6)
        haste = self.ferragens(grupo, 'PISTAO_HASTE')[-1]          # The left one.
        self.assertLess((ponto_p - haste.matrix_world.translation).length, 1e-6)
        # Mirrored margin: 10% and 90% of the track produce the same margin.
        comprimento = (b_d - a_d).length * 1000.0
        nome, perto = addon.ferragens._valor_do_controle(grupo, 'DOBRADICA', 0.1)
        self.assertEqual(nome, 'dobradicas_margem_mm')
        self.assertAlmostEqual(perto, 0.1 * comprimento, places=3)
        self.assertAlmostEqual(
            addon.ferragens._valor_do_controle(grupo, 'DOBRADICA', 0.9)[1], perto, places=3)
        # Gas strut: downward motion stops at the automatic travel limit, stored as 0.
        self.assertEqual(addon.ferragens._valor_do_controle(grupo, 'PISTAO', 1.0),
                         ('pistoes_offset_mm', 0.0))
        nome, offset = addon.ferragens._valor_do_controle(grupo, 'PISTAO', 0.15)
        self.assertGreater(offset, 0.0)
        antes = haste.matrix_world.translation.copy()
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, nome, offset), '')
        bpy.context.view_layer.update()
        haste = self.ferragens(grupo, 'PISTAO_HASTE')[-1]          # The left one.
        cima = grupo.matrix_world.to_3x3() @ Vector((0, 1, 0))
        self.assertGreater((haste.matrix_world.translation - antes).dot(cima), 0.01)
        ponto_novo = addon.ferragens._controles_ferragens(grupo, {'PISTAO'})[0][1]
        self.assertLess((ponto_novo - haste.matrix_world.translation).length, 1e-6)
        # The new margin moves the first hinge along the edge.
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'dobradicas_margem_mm', 150.0), '')
        ponto_d = addon.ferragens._controles_ferragens(grupo, {'DOBRADICA'})[0][1]
        a_d = addon.ferragens._controles_ferragens(grupo, {'DOBRADICA'})[0][2]
        self.assertAlmostEqual((ponto_d - a_d).length * 1000.0, 150.0, places=3)
        # Dragging through cabinet_arrastar_ferragem rebuilds the door and retains
        # hardware selection; Esc restores the previous value.
        self.addCleanup(addon.ferragens._ferragens_selecionadas.__setitem__, 0, None)
        self.addCleanup(addon.ferragens._arraste_ferragem.__setitem__, 0, None)
        addon.ferragens._selecionar_ferragem(bpy.context, haste)
        estado = addon.ferragens._ferragens_selecionadas[0]
        classe = addon.ferragens.OBJECT_OT_arrastar_ferragem
        op = SimpleNamespace(
            grupo=grupo.name, tipo='PISTAO', _nome='pistoes_offset_mm',
            _antes=addon.portas._copiar_parametros(grupo['porta_parametros']),
            _estado=estado, _trilho=(a_p, b_p),
            _area=SimpleNamespace(tag_redraw=lambda: None))
        op._aplicar = lambda c, v: classe._aplicar(op, c, v)
        op._restaurar = lambda c: classe._restaurar(op, c)
        op._refazer = lambda c, e: classe._refazer(op, c, e)
        op._encerrar = lambda: classe._encerrar(op)
        addon.ferragens._arraste_ferragem[0] = (grupo.name, 'PISTAO')
        op._aplicar(bpy.context, 0.0)
        self.assertEqual(grupo['porta_parametros']['pistoes_offset_mm'], 0.0)
        self.assertEqual(addon.ferragens._ferragens_em_edicao(bpy.context),
                         [(grupo, {'PISTAO'})])
        self.assertEqual(classe.modal(op, bpy.context, SimpleNamespace(
            type='ESC', value='PRESS')), {'CANCELLED'})
        self.assertAlmostEqual(grupo['porta_parametros']['pistoes_offset_mm'],
                               offset)
        self.assertIsNone(addon.ferragens._arraste_ferragem[0])
        addon.ferragens._arraste_ferragem[0] = (grupo.name, 'PISTAO')
        self.assertEqual(classe.modal(op, bpy.context, SimpleNamespace(
            type='LEFTMOUSE', value='RELEASE')), {'FINISHED'})
        # Hinged opening: no gas strut, only the hinge controller.
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'abertura', 'GIRO'), '')
        self.assertEqual([c[0] for c in addon.ferragens._controles_ferragens(
            grupo, {'DOBRADICA', 'PISTAO'})], ['DOBRADICA'])

    def test_correr_desliza_no_trilho(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'abertura', 'CORRER'), '')
        self.assertEqual([o[addon.ferragens.CHAVE_FERRAGEM]
                          for o in addon.ferragens._ferragens_portas(grupo)],
                         ['TRILHO', 'TRILHO'])
        esquerda, direita = addon.portas._folhas_portas(grupo)
        p = grupo['porta_parametros']
        util = (grupo['porta_vao_largura_mm']
                - 2 * addon.portas.RESPIRO_PORTA_MM - 2 * p['folga_mm'])
        x_vao = grupo.matrix_world.to_3x3() @ Vector((1, 0, 0))
        # Each leaf follows its own track across the entire opening to the far endpoint.
        for folha, sentido in ((esquerda, 1), (direita, -1)):
            antes = folha.matrix_world.translation.copy()
            addon.ferragens._definir_abertura(bpy.context, folha, 1.0)
            passo = (folha.matrix_world.translation - antes) * 1000.0
            self.assertAlmostEqual(passo.dot(x_vao.normalized()),
                                   sentido * (util - folha.chapa_largura_mm),
                                   places=3)
        self.assertEqual(addon.portas_viewport._texto_abertura(esquerda),
                         '%d mm' % round(util - esquerda.chapa_largura_mm))

    def test_correr_folha_unica_corre_de_um_lado_ao_outro(self):
        # User request: one leaf starts at the left spanning half the opening;
        # its slider moves it right, and its width is editable in the sidebar.
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'folhas', 1), '')
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'abertura', 'CORRER'), '')
        (folha,) = addon.portas._folhas_portas(grupo)
        p = grupo['porta_parametros']
        r = addon.portas.RESPIRO_PORTA_MM + p['folga_mm']
        L = grupo['porta_vao_largura_mm']
        util = L - 2 * r
        self.assertAlmostEqual(folha.chapa_largura_mm, util / 2, places=3)
        m = grupo.matrix_world.inverted()

        def bordas():
            bpy.context.view_layer.update()
            xs = [(m @ (folha.matrix_world @ v.co)).x * 1000.0
                  for v in folha.data.vertices]
            return min(xs), max(xs)
        self.assertAlmostEqual(bordas()[0], r, places=2)
        addon.ferragens._definir_abertura(bpy.context, folha, 1.0)
        self.assertAlmostEqual(bordas()[1], L - r, places=2)
        # The slider runs from closed to open center, keeping the dot beneath the leaf.
        a, b = addon.portas_viewport._slider_no_mundo(folha)
        self.assertAlmostEqual(((b - a) * 1000.0).length, util / 2, places=2)
        meio = (folha.matrix_world.translation - b) * 1000.0
        self.assertAlmostEqual(meio.dot(grupo.matrix_world.to_3x3().col[0]
                                        .normalized()), 0.0, places=2)
        # Width is the sidebar L field, editable by typing or dragging.
        grupo.select_set(True)
        bpy.context.view_layer.objects.active = grupo
        campos = addon.gaveta._medidas_da_porta(grupo, grupo)
        self.assertEqual(campos[0][::2], ("Width", 'ui_porta_largura_folha'))
        self.assertIsNone(addon.gaveta_eventos.aplicar_medida(
            bpy.context, 'porta', grupo.name, 'ui_porta_largura_folha', 0.4))
        (folha,) = addon.portas._folhas_portas(grupo)
        self.assertAlmostEqual(folha.chapa_largura_mm, 400.0, places=3)
        self.assertAlmostEqual(bordas()[1], L - r, places=2)    # Remains open.
        # Switching type restores the default width.
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'folhas', 2), '')
        self.assertNotIn(addon.portas.CHAVE_LARGURA_CORRER,
                         grupo['porta_parametros'])

    def test_correr_com_moldura_cobre_o_modulo_e_traz_a_moldura(self):
        # User request: overlay sliding doors, picked from outside inward, project
        # in front of the cabinet inside a frame: side cladding, upper base and fascia,
        # lower base and plinth, all 15 mm thick. The leaves cover the cabinet's
        # entire front.
        pt, f = addon.portas, addon.ferragens
        cobre = {k: 1.0 for k in pt.COBERTURAS_LADOS}
        p = parametros(abertura='CORRER', folhas=2, moldura_mm=15.0,
                       rodape_mm=100.0, testeira_mm=80.0, **cobre)
        self.assertTrue(pt._correr_sobreposta(p))
        self.assertFalse(pt._correr_sobreposta(parametros(abertura='CORRER', folhas=2)))
        folhas = pt._calcular_folhas_portas(600, 800, p)
        borda = 18 - pt.RESPIRO_PORTA_MM
        self.assertAlmostEqual(folhas[0][3][0] - folhas[0][0] / 2, -borda)
        self.assertAlmostEqual(folhas[1][3][0] + folhas[1][0] / 2, 600 + borda)
        trilho_baixo = f.perfil_trilho_moldura('BAIXO')['altura_mm']
        for _l, a, _e, c in folhas:   # From the track on the base to the cabinet top.
            self.assertAlmostEqual(c[1] - a / 2, -18.0 + trilho_baixo, places=5)
            self.assertAlmostEqual(c[1] + a / 2, 818.0)
        # One leaf in each channel of the user's track, first leaf in front.
        costas, frente = f.CANAIS_TRILHO_MOLDURA_MM
        self.assertAlmostEqual(folhas[0][3][2], pt.TRILHO_MOLDURA_COSTAS_MM + frente)
        self.assertAlmostEqual(folhas[1][3][2], pt.TRILHO_MOLDURA_COSTAS_MM + costas)
        # Tracks use the user's profiles, fitted between the side cladding.
        itens = f._ferragens_da_porta(p, 600, 800, folhas)
        trilhos = {i['id']: i for i in itens if i['tipo'] == 'TRILHO'}
        self.assertEqual({t['forma'] for t in trilhos.values()}, {'PERFIL'})
        for item in trilhos.values():
            self.assertEqual(tuple(item['x']), (-18.0, 618.0))
        lo_c, hi_c = f._limites_perfil(trilhos['TRILHO_CIMA'])
        lo_b, hi_b = f._limites_perfil(trilhos['TRILHO_BAIXO'])
        self.assertAlmostEqual(lo_c.y, 818.0 - pt.INSERCAO_CANAL_MM, places=3)  # Inside the channel.
        self.assertAlmostEqual(hi_b.y, -18.0 + trilho_baixo, places=3)  # Its foot.
        malha = bpy.data.meshes.new('perfil')
        f._malha_da_ferragem(malha, trilhos['TRILHO_CIMA'])
        self.assertEqual(len(malha.polygons),
                         sum(len(pol) + 2 for pol in trilhos['TRILHO_CIMA']['poligonos']))
        bpy.data.meshes.remove(malha)
        _pecas, pontos = addon.arame._arame_dos_itens(list(trilhos.values()))
        self.assertTrue(pontos)                                        # Wizard preview.
        # The frame.
        pecas = {k: caixa for k, _n, caixa, _e in pt._pecas_moldura(p, 600, 800, 300.0)}
        self.assertEqual(set(pecas), {'LATERAL_ESQ', 'LATERAL_DIR', 'BASE_CIMA',
                                      'TESTEIRA', 'BASE_BAIXO', 'RODAPE'})
        avanco = pt._avanco_moldura(p)
        esq, dir_ = pecas['LATERAL_ESQ'], pecas['LATERAL_DIR']
        self.assertEqual(esq[:2], (-33.0, -18.0))        # Outside the side panel.
        self.assertEqual(dir_[:2], (618.0, 633.0))
        self.assertEqual(esq[4:], (-300.0, avanco))      # From back to front.
        testeira, rodape = pecas['TESTEIRA'], pecas['RODAPE']
        self.assertAlmostEqual(testeira[5] - testeira[4], 15.0)
        self.assertAlmostEqual(testeira[3] - testeira[2], 80.0)
        self.assertGreater(testeira[4], max(c[2] + e / 2 for _l, _a, e, c in folhas))
        self.assertAlmostEqual(rodape[3] - rodape[2], 100.0)
        self.assertAlmostEqual(pecas['BASE_CIMA'][2], hi_c.y, places=3)   # Above the track.
        self.assertAlmostEqual(pecas['BASE_BAIXO'][3], lo_b.y, places=3)  # Below the track.
        self.assertAlmostEqual(esq[2], rodape[2])               # From the floor.
        self.assertAlmostEqual(esq[3], pecas['BASE_CIMA'][3])   # To the ceiling.
        # The lower base touches the cabinet back at y = -18, leaving no gap
        # between it and the cabinet, as in the user's screenshot.
        self.assertAlmostEqual(pecas['BASE_BAIXO'][3], -18.0)
        self.assertEqual(pecas['BASE_BAIXO'][4], 0.0)          # From its front.
        # Zero plinth/fascia removes those parts; inset doors have no frame.
        sem = {k: caixa for k, _n, caixa, _e in pt._pecas_moldura(
            dict(p, rodape_mm=0.0, testeira_mm=0.0), 600, 800)}
        self.assertEqual(set(sem), {'LATERAL_ESQ', 'LATERAL_DIR', 'BASE_CIMA',
                                    'BASE_BAIXO'})
        # Without a base, everything sits on the floor at the cabinet-bottom level,
        # with nothing below it: the track sits on the base and the leaf on the track.
        self.assertAlmostEqual(sem['BASE_BAIXO'][2], -18.0)
        self.assertAlmostEqual(sem['LATERAL_ESQ'][2], -18.0)
        sem_p = dict(p, rodape_mm=0.0)
        self.assertAlmostEqual(pt._pe_da_folha_moldura(sem_p),
                               -18.0 + 15.0 + trilho_baixo, places=5)
        folhas_sem = pt._calcular_folhas_portas(600, 800, sem_p)
        self.assertAlmostEqual(folhas_sem[0][3][1] - folhas_sem[0][1] / 2,
                               pt._pe_da_folha_moldura(sem_p), places=5)
        _lo, hi_sem = f._limites_perfil(next(
            i for i in f._ferragens_da_porta(sem_p, 600, 800, folhas_sem)
            if i['id'] == 'TRILHO_BAIXO'))
        self.assertAlmostEqual(_lo.y, sem['BASE_BAIXO'][3], places=3)
        self.assertEqual(pt._pecas_moldura(parametros(abertura='CORRER', folhas=2),
                                           600, 800), [])

    def test_trilho_leve_tem_canais_fresados_e_folha_de_15(self):
        # User request: light track uses the sample track model, with two routed channels
        # in the frame bases containing inset U profiles; heavy track uses aluminum.
        # Changing an existing door's track rebuilds everything.
        pt, f = addon.portas, addon.ferragens
        conj = self.nicho()
        L, A, P, E = pt._caixa_do_modulo(conj)
        y = -P / 2
        grupo = self.porta_por_quatro_cliques(
            conj, (-L / 2, y, A), (-L / 2 + E, y, A - E), (L / 2 - E, y, E),
            (L / 2, y, 0), abertura='CORRER', folhas=2, trilho='LEVE')
        p = dict(grupo['porta_parametros'])
        leve = f.perfil_trilho_moldura('LEVE')
        self.assertEqual(p['trilho'], 'LEVE')
        folhas = pt._folhas_portas(grupo)
        for folha in folhas:            # Channels are 17.3 mm wide for a 15 mm leaf.
            self.assertAlmostEqual(folha.chapa_espessura_mm, 15.0)
        # One leaf centered in each channel, first in front.
        calculadas = pt._calcular_folhas_portas(
            grupo['porta_vao_largura_mm'], grupo['porta_vao_altura_mm'], p)
        costas, frente = leve['canais_mm']
        self.assertAlmostEqual(calculadas[0][3][2], pt.TRILHO_MOLDURA_COSTAS_MM + frente)
        self.assertAlmostEqual(calculadas[1][3][2], pt.TRILHO_MOLDURA_COSTAS_MM + costas)
        # The leaf foot rests on the U flange flush with the base; its top clears the upper base.
        _t, base_cima, base_baixo, _fundo = pt._alturas_moldura(p, grupo['porta_vao_altura_mm'])
        for _l, a, _e, c in calculadas:
            self.assertAlmostEqual(c[1] - a / 2, base_baixo + leve['aba_mm'], places=5)
            self.assertAlmostEqual(base_cima - (c[1] + a / 2),
                                   pt.FOLGA_TOPO_TRILHO_LEVE_MM, places=5)
        # Both bases contain mesh channels, on top of the lower base and underneath
        # the upper base, with the U profiles inside.
        bases = {o['porta_moldura_peca']: o for o in pt._moldura_da_porta(grupo)
                 if o['porta_moldura_peca'] in {'BASE_BAIXO', 'BASE_CIMA'}}
        self.assertEqual(set(bases), {'BASE_BAIXO', 'BASE_CIMA'})
        for chave, lado in (('BASE_BAIXO', 1), ('BASE_CIMA', -1)):
            base = bases[chave]
            self.assertEqual(base['chapa_canal_lado'], lado)
            self.assertEqual(len(base['chapa_canais']), 2)
            self.assertEqual(len(base.data.vertices), 2 * (4 + 4 * 2))
            zs = sorted({round(v.co.z * 1000, 3) for v in base.data.vertices})
            self.assertEqual(len(zs), 3)        # Face, channel bottom and opposite face.
        trilhos = {i['id']: i for i in f._ferragens_da_porta(
            p, grupo['porta_vao_largura_mm'], grupo['porta_vao_altura_mm'], calculadas)
            if i['tipo'] == 'TRILHO'}
        lo, hi = f._limites_perfil(trilhos['TRILHO_BAIXO'])
        self.assertAlmostEqual(hi.y, base_baixo + leve['aba_mm'], places=3)
        self.assertAlmostEqual(lo.y, base_baixo + min(v for pol in leve['poligonos']
                                                      for _u, v in pol), places=3)
        self.assertLess(lo.y, base_baixo)                   # The U profile inside the channel.
        self.assertTrue(trilhos['TRILHO_BAIXO']['aberto'])
        malha = bpy.data.meshes.new('u')
        f._malha_da_ferragem(malha, trilhos['TRILHO_BAIXO'])
        self.assertEqual(len(malha.polygons),
                         sum(len(pol) - 1 for pol in leve['poligonos']))   # No caps.
        bpy.data.meshes.remove(malha)
        # The light-track frame is shallower: its track is 27 mm versus 64 mm for heavy.
        self.assertLess(pt._avanco_moldura(p), pt._avanco_moldura(dict(p, trilho='PESADO')))
        # It has no upper front closure, as in the user's screenshot: no fascia
        # and no fascia field in the tab.
        pecas = {o['porta_moldura_peca'] for o in pt._moldura_da_porta(grupo)}
        self.assertNotIn('TESTEIRA', pecas)
        self.assertIn('RODAPE', pecas)
        addon.hud._selecionar_porta_hud(bpy.context, folhas[0], 'PORTA')
        bpy.context.scene.cabinet_aba = 'PORTAS'
        campos = {v[5][2] for v in addon.gaveta._widgets_gaveta(bpy.context, 564, 1600)
                  if v[5] and v[5][0] == 'medida'}
        self.assertNotIn('ui_porta_testeira', campos)
        self.assertIn('ui_porta_rodape', campos)
        # Switch an existing door to heavy track: 18 mm leaves, bases without channels.
        nomes = {k: o.name for k, o in bases.items()}
        self.assertEqual(pt._editar_parametro_porta(bpy.context, grupo, 'trilho', 'PESADO'), '')
        for folha in pt._folhas_portas(grupo):
            self.assertAlmostEqual(folha.chapa_espessura_mm, 18.0)
        for nome in nomes.values():
            base = bpy.data.objects[nome]
            self.assertNotIn('chapa_canais', base)
            self.assertEqual(len(base.data.vertices), 8)       # A box again.
        # Heavy track restores the fascia.
        self.assertIn('TESTEIRA', {o['porta_moldura_peca']
                                   for o in pt._moldura_da_porta(grupo)})

    def test_porta_com_moldura_no_modulo(self):
        # Mixed coverage: 1-2 at the same inner corner, 3-4 from inside outward.
        # Choosing framed uses the entire cabinet and creates six 15 mm panels
        # with 18 mm leaves, as requested.
        pt = addon.portas
        conj = self.nicho()
        L, A, P, E = pt._caixa_do_modulo(conj)
        y = -P / 2
        grupo = self.porta_por_quatro_cliques(
            conj, (-L / 2 + E, y, A - E), (-L / 2 + E, y, A - E),
            (L / 2 - E, y, E), (L / 2, y, 0), abertura='CORRER', folhas=2,
            tipo_correr='MOLDURA')
        p = grupo['porta_parametros']
        self.assertEqual([p[k] for k in pt.COBERTURAS_LADOS], [1.0] * 4)
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], L - 2 * E, places=3)
        moldura = {o['porta_moldura_peca']: o for o in pt._moldura_da_porta(grupo)}
        self.assertEqual(len(moldura), 6)
        # Cabinet dimensions include the frame immediately, without waiting for the timer.
        self.assertAlmostEqual(conj.conj_largura_mm, L + 2 * 15.0, places=2)
        for o in moldura.values():
            self.assertIn(addon.chapas.MARCA_CHAPA, o)
            self.assertEqual(o.parent, grupo)
            self.assertAlmostEqual(o.chapa_espessura_mm, 15.0)
        for folha in pt._folhas_portas(grupo):
            self.assertAlmostEqual(folha.chapa_espessura_mm, 18.0)
        # Like leaves, these are excluded from cabinet operations.
        self.assertFalse(set(moldura.values())
                         & set(addon.modulos._chapas_do_conjunto(conj)))

        def caixa_local(nome):
            bpy.context.view_layer.update()
            o = bpy.data.objects[nome]
            inv = conj.matrix_world.inverted()
            vs = [inv @ (o.matrix_world @ v.co) * 1000.0 for v in o.data.vertices]
            return ([min(v[i] for v in vs) for i in range(3)],
                    [max(v[i] for v in vs) for i in range(3)])
        lo, hi = caixa_local(moldura['LATERAL_ESQ'].name)
        self.assertAlmostEqual(hi[0], -L / 2, places=3)       # Touches the outside.
        self.assertAlmostEqual(lo[0], -L / 2 - 15.0, places=3)
        self.assertAlmostEqual(hi[1], P / 2, places=3)         # From the back.
        self.assertAlmostEqual(lo[1], -P / 2 - pt._avanco_moldura(p), places=3)
        # Editing one part's E applies to the whole frame.
        nomes = {k: o.name for k, o in moldura.items()}
        moldura['TESTEIRA'].chapa_espessura_mm = 20.0
        self.assertAlmostEqual(grupo['porta_parametros']['moldura_mm'], 20.0)
        for nome in nomes.values():
            self.assertAlmostEqual(bpy.data.objects[nome].chapa_espessura_mm, 20.0)
        # The frame counts toward cabinet dimensions, as requested: cabinet L/A/P
        # describe the envelope, and width changes move the frame to that dimension.
        bpy.context.view_layer.update()
        self.assertAlmostEqual(conj.conj_largura_mm, L + 2 * 20.0, places=2)
        envelope = addon.modulos.medir_conjunto(conj)
        self.assertGreater(envelope[1], A + 100.0)            # Plinth plus top.
        self.assertAlmostEqual(envelope[2], P + pt._avanco_moldura(
            dict(grupo['porta_parametros'])), places=2)
        conj.conj_largura_mm = L + 100
        bpy.context.view_layer.update()
        lo, hi = caixa_local(nomes['LATERAL_DIR'])
        self.assertAlmostEqual(hi[0], (L + 100) / 2, places=3)   # The outer edge.
        self.assertAlmostEqual(conj.conj_largura_mm, L + 100, places=2)
        self.assertAlmostEqual(pt._caixa_do_modulo(conj)[0], L + 60, places=2)  # The carcass.
        # The cabinet HUD box uses the envelope.
        bpy.ops.object.select_all(action='DESELECT')
        conj.select_set(True)
        bpy.context.view_layer.objects.active = conj
        (_obj, _modo, pecas), = addon.hud._itens_da_selecao(bpy.context)
        self.assertTrue(set(addon.portas._moldura_da_porta(grupo)) <= set(pecas))

    def test_metade_metade_embutida_usa_o_vao_de_dentro(self):
        # The same gesture answered as inset uses the panel's inner dimension,
        # even with the fourth click at an outer corner; no frame.
        pt = addon.portas
        conj = self.nicho()
        L, A, P, E = pt._caixa_do_modulo(conj)
        y = -P / 2
        grupo = self.porta_por_quatro_cliques(
            conj, (-L / 2 + E, y, A - E), (-L / 2 + E, y, A - E),
            (L / 2, y, 0), (L / 2, y, 0), abertura='CORRER', folhas=2,
            tipo_correr='EMBUTIDA')
        p = grupo['porta_parametros']
        self.assertEqual([p[k] for k in pt.COBERTURAS_LADOS], [0.0] * 4)
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], L - 2 * E, places=3)
        self.assertAlmostEqual(grupo['porta_vao_altura_mm'], A - 2 * E, places=3)
        self.assertFalse(pt._moldura_da_porta(grupo))

    def test_wizard_pergunta_embutida_ou_moldura_so_no_metade_metade(self):
        tipo = addon.assistente.OBJECT_OT_apanhar_vao_portas
        dentro, fora = Vector((0.018, 0, 0.018)), Vector((0.6, 0, 0.4))
        perto = Vector((0.582, 0, 0.382))
        caso = lambda *pts: SimpleNamespace(_pontos=[(p, None) for p in pts])
        self.assertTrue(tipo._metade_metade(caso(dentro, dentro, perto, fora)))
        self.assertTrue(tipo._metade_metade(caso(Vector(), dentro, fora, fora)))
        self.assertFalse(tipo._metade_metade(caso(dentro, dentro, perto, perto)))
        self.assertFalse(tipo._metade_metade(caso(Vector(), dentro, perto, fora)))
        # Choosing sliding for mixed coverage prompts; answering creates it.
        w = {'etapa': 'TIPO', 'escolhas': {'folhas': 2}, 'embutida': False}
        op = SimpleNamespace(_w=w, _metade_metade=lambda: True,
                             _ir=lambda etapa, mouse=None: w.update(etapa=etapa),
                             _criar=lambda ctx: 'CRIADA')
        self.assertIsNone(tipo._escolher_abertura(op, None, 'CORRER'))
        self.assertEqual(w['etapa'], 'MOLDURA')
        # Framed adds a question about the base/plinth, as requested.
        self.assertIsNone(tipo._escolher(op, None, 'MOLDURA'))
        self.assertEqual(w['escolhas']['tipo_correr'], 'MOLDURA')
        self.assertEqual(w['etapa'], 'BASE')
        self.assertIsNone(tipo._escolher(op, None, 'SEM'))
        self.assertEqual(w['escolhas']['rodape_mm'], 0.0)
        # Then choose heavy or light track, as requested; the answer creates the door.
        self.assertEqual(w['etapa'], 'TRILHO')
        self.assertEqual(tipo._escolher(op, None, 'LEVE'), 'CRIADA')
        self.assertEqual(w['escolhas']['trilho'], 'LEVE')
        # Inset skips the base question and creates immediately.
        w.update(etapa='MOLDURA', escolhas={'folhas': 2})
        self.assertEqual(tipo._escolher(op, None, 'EMBUTIDA'), 'CRIADA')
        self.assertNotIn('rodape_mm', w['escolhas'])
        # Outside-to-inside gesture unambiguously means framed: ask only about the base.
        op._metade_metade = lambda: False
        w.update(etapa='TIPO', escolhas={'folhas': 2}, embutida=False)
        self.assertIsNone(tipo._escolher_abertura(op, None, 'CORRER'))
        self.assertEqual(w['etapa'], 'BASE')
        self.assertIsNone(tipo._escolher(op, None, 'COM'))
        self.assertEqual(w['escolhas']['rodape_mm'],
                         addon.portas.PADRAO_MEDIDAS_PORTAS['porta_rodape_mm'])
        self.assertEqual(tipo._escolher(op, None, 'PESADO'), 'CRIADA')
        # Inset determined by clicks: create immediately.
        w.update(etapa='TIPO', escolhas={'folhas': 2}, embutida=True)
        self.assertEqual(tipo._escolher_abertura(op, None, 'CORRER'), 'CRIADA')
        # Overlay with two leaves now offers hinged or framed sliding, rather than hinged directly.
        self.assertIn('CORRER', dict(addon.portas.TIPOS_SOBREPOSTA))

    def test_correr_trilhos_como_os_de_verdade(self):
        # User photo: a tall upper U profile provides a deep channel for each leaf,
        # with clearance to lift it; a low lower plate has one guide per leaf,
        # and the leaf stands on that guide.
        f = addon.ferragens
        p = parametros(abertura='CORRER', folhas=3)
        folhas = addon.portas._calcular_folhas_portas(600, 800, p)
        itens = f._ferragens_da_porta(p, 600, 800, folhas)
        trilhos = {i['id']: i for i in itens if i['tipo'] == 'TRILHO'}
        self.assertEqual(set(trilhos), {'TRILHO_CIMA', 'TRILHO_BAIXO'})
        cima, baixo = trilhos['TRILHO_CIMA'], trilhos['TRILHO_BAIXO']
        # Top plate, two outer walls and two walls between the three channels.
        self.assertEqual(len(cima['caixas']), 1 + 2 + 2)
        # Lower plate and one guide per leaf.
        self.assertEqual(len(baixo['caixas']), 1 + 3)
        for l, a, e, c in folhas:
            frente, costas = c[2] + e / 2, c[2] - e / 2
            paredes = [cx for cx in cima['caixas'][1:]
                       if min(v.z for v in cx) < frente - 1e-6
                       and max(v.z for v in cx) > costas + 1e-6]
            self.assertFalse(paredes, "Wall inside the leaf channel")
            pe, topo = c[1] - a / 2, c[1] + a / 2
            # Standing on the guide; the top sits inside the channel away from the plate.
            self.assertAlmostEqual(pe, f.altura_trilho_baixo())
            self.assertAlmostEqual(800 - f.TRILHO_CIMA_CHAPA_MM - topo,
                                   f.TRILHO_LEVANTAR_MM)
            self.assertGreater(topo, 800 - f.TRILHO_CIMA_ALTURA_MM)
            (guia,) = [cx for cx in baixo['caixas'][1:]
                       if min(v.z for v in cx) < c[2] < max(v.z for v in cx)]
            self.assertAlmostEqual(max(v.y for v in guia), pe)
        ys = [v.y for cx in baixo['caixas'] for v in cx]
        self.assertEqual((min(ys), max(ys)), (0.0, f.altura_trilho_baixo()))
        ys = [v.y for cx in cima['caixas'] for v in cx]
        self.assertEqual((min(ys), max(ys)),
                         (800 - f.TRILHO_CIMA_ALTURA_MM, 800.0))

    # ---- Group naming and organization, as requested with a screenshot
    def test_grupo_tem_nome_colecao_e_porta_pelo_modelo(self):
        conj = self.nicho()
        L, A, P, _E = addon.portas._caixa_do_modulo(conj)
        cena = bpy.context.scene
        # Without an entered name, use the suggested "Armario LxAxP".
        self.assertEqual(conj.name, "Cabinet %dx%dx%d" % (round(L), round(A),
                                                          round(P)))
        colecao = conj.users_collection[0]
        self.assertEqual(colecao.name, conj.name)
        self.assertTrue(colecao.get(addon.modulos.MARCA_COLECAO_MODULO))
        self.assertIn(colecao, list(cena.collection.children))
        for chapa in addon.modulos._chapas_do_conjunto(conj):
            self.assertEqual(list(chapa.users_collection), [colecao])
        # Generated assembly and part names follow the English interface.
        grupo = self.porta_no_nicho(conj)
        self.assertEqual(grupo.name, 'Double Door')
        self.assertEqual(list(grupo.users_collection), [colecao])
        self.assertEqual([f.name for f in addon.portas._folhas_portas(grupo)],
                         ['Leaf 01', 'Leaf 02'])
        nomes = [o.name for o in addon.ferragens._ferragens_portas(grupo)]
        self.assertFalse([n for n in nomes if '_' in n or 'Dobradica' in n
                          or 'Parafuso' in n or 'Armacao' in n], nomes)
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'abertura', 'CORRER'), '')
        self.assertEqual(grupo.name, "Sliding Door")
        for p, nome in ((dict(abertura='BASCULANTE'), "Lift-Up Door"),
                        (dict(folhas=1), 'Single Door'),
                        (dict(folhas=2, dobradica='SUPER_CURVA'),
                         'Double Inset Door'),
                        (dict(folhas=1, dobradica='SUPER_CURVA'),
                         'Single Inset Door')):
            self.assertEqual(addon.portas._nome_da_porta(parametros(**p)), nome)
        # Preserve a user-edited name.
        grupo.name = 'Porta da pia'
        addon.portas._editar_parametro_porta(bpy.context, grupo, 'abertura', 'GIRO')
        self.assertEqual(grupo.name, 'Porta da pia')
        # Renaming the group also renames the Collection and updates the door link.
        self.assertTrue(addon.modulos.nomear_grupo(conj, '  Kitchen  '))
        self.assertEqual((conj.name, colecao.name), ("Kitchen", "Kitchen"))
        self.assertEqual(grupo[addon.portas.CHAVE_MODULO_PORTA], "Kitchen")
        self.assertEqual(addon.portas._portas_do_conjunto(conj), [grupo])
        self.assertFalse(addon.modulos.nomear_grupo(conj, '   '))
        # Ungrouping moves the panel to the scene root.
        chapa = addon.modulos._chapas_do_conjunto(conj)[0]
        addon.solda.desagregar(chapa)
        self.assertIsNone(chapa.parent)
        self.assertEqual(list(chapa.users_collection), [cena.collection])

    def test_agrupar_com_nome_e_grupo_vazio_some_com_a_colecao(self):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        # F3 opens the dialog; scripts provide the name directly.
        self.assertEqual(bpy.ops.object.cabinet_agrupar(nome="Bathroom"),
                         {'FINISHED'})
        conj = bpy.context.object
        colecao = conj.users_collection[0]
        self.assertEqual((conj.name, colecao.name), ("Bathroom", "Bathroom"))
        addon.solda.desagregar_grupo(addon.modulos._chapas_do_conjunto(conj))
        self.assertNotIn("Bathroom", bpy.data.objects)
        self.assertNotIn("Bathroom", bpy.data.collections)
        # After deleting a cabinet with X, validation removes its empty Collection.
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar(nome="Living Room")
        for o in list(bpy.data.collections["Living Room"].all_objects):
            bpy.data.objects.remove(o, do_unlink=True)
        addon.ferragens._conferir_ferragens()
        self.assertNotIn("Living Room", bpy.data.collections)

    def test_corrente_junta_soltas_e_pergunta_o_nome_na_gaveta(self):
        # Through the sidebar without a popup: create the group with the suggested name,
        # then show the black-box text field; entered text becomes its name.
        piso = addon.chapas.nova_chapa("Floor", 600.0, 400.0, 18.0, (0, 0, 9.0),
                                (0, 0, 0), bpy.context)
        lateral = addon.chapas.nova_chapa('Lateral', 720.0, 400.0, 18.0,
                                   (300.0 + 3.0 + 9.0, 0, 360.0),
                                   (0, 90.0, 0), bpy.context)
        bpy.context.view_layer.update()
        addon.perguntas._na_gaveta[0] = True
        self.addCleanup(addon.perguntas._na_gaveta.__setitem__, 0, False)
        self.addCleanup(addon.perguntas._pergunta_atual.__setitem__, 0, None)
        self.assertEqual(bpy.ops.object.cabinet_conectar_distancia(
            origem=piso.name), {'FINISHED'})
        grupo = addon.portas._modulo_da_chapa(piso)
        self.assertIs(addon.portas._modulo_da_chapa(lateral), grupo)
        pergunta = addon.perguntas._pergunta_atual[0]
        self.assertTrue(pergunta['campo'] and pergunta['na_gaveta'])
        estado = addon.solda._nome_grupo_gaveta[0]
        self.assertEqual(estado['texto'], grupo.name)
        for letra in "Laundry Room":      # Initially select all text.
            addon.gaveta_desenho._tecla_no_texto(estado, letra.upper(), letra)
        self.assertEqual(estado['texto'], "Laundry Room")
        # Enter in the name-entry modal (cabinet_digitar_nome_grupo).
        op = SimpleNamespace(_redesenhar=lambda c: None)
        evento = SimpleNamespace(type='RET', value='PRESS', ctrl=False,
                                 unicode='')
        self.assertEqual(addon.solda.OBJECT_OT_digitar_nome_grupo.modal(
            op, bpy.context, evento), {'FINISHED'})
        self.assertEqual(grupo.name, "Laundry Room")
        self.assertIsNone(addon.perguntas._pergunta_atual[0])
        # The box's OK action (cabinet_nomear_grupo) does the same; Keep preserves it.
        addon.solda._abrir_caixa_nome(grupo)
        addon.solda._nome_grupo_gaveta[0]['texto'] = 'Area'
        self.assertEqual(bpy.ops.object.cabinet_responder_pergunta(opcao=0),
                         {'FINISHED'})
        self.assertEqual(grupo.name, 'Area')
        addon.solda._abrir_caixa_nome(grupo)
        addon.solda._nome_grupo_gaveta[0]['texto'] = 'Outro'
        bpy.ops.object.cabinet_responder_pergunta(opcao=1)
        self.assertEqual(grupo.name, 'Area')
        self.assertIsNone(addon.solda._nome_grupo_gaveta[0])

    def test_empties_de_amarracao_ficam_invisiveis(self):
        # User request: cabinet, door-group and strut-endpoint Empties cluttered the view.
        # Keep them for parent-driven movement at minimum display size;
        # validation shrinks those from older files too.
        conj = self.nicho()
        grupo = self.porta_de_giro(conj, abertura='BASCULANTE',
                                   dobradica_lado='CIMA', pistoes_qtd=1)
        pontos = self.ferragens(grupo, 'PISTAO_PONTO')
        self.assertTrue(pontos)
        for o in [conj, grupo, *pontos]:
            self.assertEqual(o.type, 'EMPTY')
            self.assertAlmostEqual(o.empty_display_size,
                                   addon.chapas.TAMANHO_EMPTY_OCULTO, places=6)
        conj.empty_display_size = 0.15        # An older file.
        grupo.empty_display_type = 'ARROWS'
        grupo.empty_display_size = 0.05
        addon.ferragens._conferir_ferragens()
        for o in (conj, grupo):
            self.assertAlmostEqual(o.empty_display_size,
                                   addon.chapas.TAMANHO_EMPTY_OCULTO, places=6)
        self.assertEqual(grupo.empty_display_type, 'PLAIN_AXES')
        # Leave unmarked user Empties untouched.
        livre = bpy.data.objects.new("Free", None)
        bpy.context.collection.objects.link(livre)
        livre.empty_display_size = 0.5
        addon.ferragens._conferir_ferragens()
        self.assertEqual(livre.empty_display_size, 0.5)

    def test_modulo_selecionado_nao_desenha_a_porta(self):
        # User request: clicking panels selects the cabinet and its door, but hinges,
        # opening lines, opposite-corner line, corners and sliders appear only when
        # the door itself is selected.
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        folhas = addon.portas._folhas_portas(grupo)
        addon.hud._selecionar_chapa_hud(bpy.context, self.lateral_esquerda(conj))
        self.assertTrue(grupo.select_get())
        self.assertEqual(addon.portas_viewport._portas_com_cantos(bpy.context), [])
        self.assertEqual(addon.portas_viewport._folhas_com_slider(bpy.context), [])
        addon.hud._selecionar_porta_hud(bpy.context, folhas[0], 'PORTA')
        self.assertEqual(addon.portas_viewport._portas_com_cantos(bpy.context), [grupo])
        self.assertEqual(addon.portas_viewport._folhas_com_slider(bpy.context), folhas)
        addon.hud._selecionar_porta_hud(bpy.context, folhas[1], 'FOLHA')
        self.assertEqual(addon.portas_viewport._folhas_com_slider(bpy.context), [folhas[1]])

    def test_sliders_da_porta_dupla_tem_folga_no_meio(self):
        # User request: leave space between the two sliders and at both door ends;
        # they must not move when the leaf opens.
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        esquerda, direita = addon.portas._folhas_portas(grupo)
        local = lambda v: (conj.matrix_world.inverted() @ v) * 1000.0
        a = sorted(local(p).x for p in addon.portas_viewport._slider_no_mundo(esquerda))
        b = sorted(local(p).x for p in addon.portas_viewport._slider_no_mundo(direita))
        self.assertGreaterEqual(b[0] - a[1], 2 * addon.portas_viewport.SLIDER_RECUO_MM)
        borda = min(local(esquerda.matrix_world @ v.co).x
                    for v in esquerda.data.vertices)
        # float32 mesh: tolerance of 1e-3 mm.
        self.assertGreaterEqual(a[0] - borda, addon.portas_viewport.SLIDER_RECUO_MM - 1e-3)
        antes = addon.portas_viewport._slider_no_mundo(esquerda)
        addon.ferragens._definir_abertura(bpy.context, esquerda, 0.8)
        for p, q in zip(antes, addon.portas_viewport._slider_no_mundo(esquerda)):
            self.assertLess((p - q).length, 1e-9)

    def test_porta_de_apoio_aberta_nao_muda_o_vao(self):
        conj, cima, baixo = self.duas_fileiras()
        antes = self.limites_folhas(conj, baixo)
        apoio = baixo['porta_ancora_3']
        addon.ferragens._definir_abertura(bpy.context, apoio, 1.0)
        addon.portas.atualizar_portas_do_conjunto(conj)
        bpy.context.view_layer.update()
        depois = self.limites_folhas(conj, baixo)
        for a, b in zip(antes[0] + antes[1], depois[0] + depois[1]):
            self.assertAlmostEqual(a, b, places=6)

    def test_cantos_externos_equivalem_aos_internos_nas_quatro_faces(self):
        conj = self.nicho()
        conj.location = (2, -3, 1)
        conj.rotation_euler = (0.1, -0.2, 0.4)
        bpy.context.view_layer.update()
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        for frente in ('NEG_Y', 'POS_Y', 'NEG_X', 'POS_X'):
            for dobradica in ('RETA', 'CURVA', 'SUPER_CURVA'):
                with self.subTest(frente=frente, dobradica=dobradica):
                    plano = (-1 if frente.startswith('NEG') else 1)
                    if frente.endswith('Y'):
                        a, b = (-L/2, plano*P/2, 0), (L/2, plano*P/2, A)
                    else:
                        a, b = (plano*L/2, -P/2, 0), (plano*L/2, P/2, A)
                    g = self.criar_por_pontos(conj, Vector(a)/1000, Vector(b)/1000,
                                             frente=frente, dobradica=dobradica)
                    self.assertAlmostEqual(g['porta_vao_largura_mm'],
                                           (L if frente.endswith('Y') else P) - 2*E, places=2)
                    self.assertAlmostEqual(g['porta_vao_altura_mm'], A-2*E, places=2)
                    for f in g[addon.portas.CHAVE_FOLGAS_PORTA]:
                        self.assertAlmostEqual(f, 1, places=3)

    def test_canto_misto_nao_desconta_duas_vezes_a_espessura(self):
        conj = self.nicho()
        L, A, P, E = (v/1000 for v in addon.portas._caixa_do_modulo(conj))
        g = self.criar_por_pontos(conj, (L/2-E, -P/2, A-E), (-L/2, -P/2, 0))
        lo, hi = self.limites_folhas(conj, g)
        r = addon.portas.RESPIRO_PORTA_MM / 1000        # Never flush with the edge.
        for atual, esperado in ((lo[0], -L/2 + r), (hi[0], L/2 - r),
                                (lo[2], r), (hi[2], A - r)):
            self.assertAlmostEqual(atual, esperado, places=5)

    def duas_fileiras(self, inverter=False):
        conj = self.nicho()
        conj.conj_altura_mm = 1800
        L, A, P, E = (v/1000 for v in addon.portas._caixa_do_modulo(conj))
        cima = self.criar_por_pontos(conj, (-L/2, -P/2, 0.7), (L/2, -P/2, A))
        folha = addon.portas._folhas_portas(cima)[-1]
        inferior = self.limites_folhas(conj, cima)[0][2]
        a, b = (-L/2, -P/2, 0), (L/2, -P/2-0.018, inferior)
        chapa = addon.modulos._chapas_do_conjunto(conj)[0]
        objetos = (chapa, folha)
        if inverter:
            a, b, objetos = b, a, tuple(reversed(objetos))
        baixo = self.criar_por_pontos(conj, a, b, objetos)
        return conj, cima, baixo

    def test_apoio_em_porta_respeita_folga_e_plano_nas_duas_ordens(self):
        for inverter in (False, True):
            self.setUp()
            conj, cima, baixo = self.duas_fileiras(inverter)
            lo_c, hi_c = self.limites_folhas(conj, cima)
            lo_b, hi_b = self.limites_folhas(conj, baixo)
            self.assertAlmostEqual(lo_c[2] - hi_b[2], 0.002, places=5)
            self.assertAlmostEqual(lo_c[1], lo_b[1], places=5)
            self.assertAlmostEqual(hi_c[1], hi_b[1], places=5)
            self.assertAlmostEqual(lo_c[0], lo_b[0], places=5)
            self.assertAlmostEqual(hi_c[0], hi_b[0], places=5)
            self.assertIn('porta_ancora_3', baixo)

    def test_apoio_e_origem_acompanham_redimensionamento(self):
        conj, cima, baixo = self.duas_fileiras()
        # Force alphabetical order opposite to dependency order.
        cima.name, baixo.name = 'Z_superiores', 'A_inferiores'
        for prop, valor in (('conj_altura_mm', 2200), ('conj_largura_mm', 1000),
                            ('conj_profundidade_mm', 550), ('conj_espessura_mm', 30)):
            setattr(conj, prop, valor)
            bpy.context.view_layer.update()
            lo_c, hi_c = self.limites_folhas(conj, cima)
            lo_b, hi_b = self.limites_folhas(conj, baixo)
            self.assertAlmostEqual(lo_c[2] - hi_b[2], 0.002, places=5)
            self.assertAlmostEqual(lo_c[1], lo_b[1], places=5)
            self.assertAlmostEqual(lo_c[0], lo_b[0], places=5)
            self.assertAlmostEqual(hi_c[0], hi_b[0], places=5)

    def test_preview_preserva_arestas_e_duas_fileiras_reais(self):
        conj, cima, baixo = self.duas_fileiras()
        for modo in ('GRUPO', 'PORTA'):
            dims, vertices, arestas = addon.gaveta._geometria_wireframe(conj, modo)
            alvos = addon.portas._folhas_portas(cima) + addon.portas._folhas_portas(baixo)
            if modo == 'GRUPO':
                alvos = addon.modulos._chapas_do_conjunto(conj) + alvos
            self.assertEqual(len(vertices), sum(len(o.data.vertices) for o in alvos))
            self.assertEqual(len(arestas), sum(len(o.data.edges) for o in alvos))
            alturas = sorted({round(v[2], 2) for v in vertices})
            self.assertGreaterEqual(len(alturas), 4)
            for i, j in arestas:
                self.assertGreater((Vector(vertices[i])-Vector(vertices[j])).length, 0)
        self.assertIsNone(addon.gaveta._geometria_wireframe(conj, 'INDIVIDUAL'))

    def test_medidas_da_cena_sincronizam_modulo_e_portas(self):
        conj, cima, baixo = self.duas_fileiras()
        chapa = addon.modulos._chapas_do_conjunto(conj)[0]
        bpy.context.view_layer.objects.active = chapa
        chapa.chapa_modo = 'GRUPO'
        addon.modulos.sincronizar_grupo(bpy.context)
        bpy.context.scene.grupo_altura_mm = 2200
        self.assertAlmostEqual(conj.conj_altura_mm, 2200, places=3)
        lo_c, hi_c = self.limites_folhas(conj, cima)
        lo_b, hi_b = self.limites_folhas(conj, baixo)
        self.assertAlmostEqual(hi_c[2], 2.2 - addon.portas.RESPIRO_PORTA_MM / 1000,
                               places=5)
        self.assertAlmostEqual(lo_c[2] - hi_b[2], 0.002, places=5)

    def test_cantos_externos_usam_a_malha_com_campo_antigo(self):
        conj = self.nicho()
        addon.modulos.redimensionar_grupo(addon.modulos._chapas_do_conjunto(conj), (600, 1200, 300))
        addon.modulos.reposicionar_origem(conj)
        self.assertAlmostEqual(conj.conj_altura_mm, 400)
        g = self.criar_por_pontos(conj, (-0.3, -0.15, 0), (0.3, -0.15, 1.2))
        self.assertAlmostEqual(g['porta_vao_altura_mm'], 1164, places=3)
        for folga in g[addon.portas.CHAVE_FOLGAS_PORTA]:
            self.assertAlmostEqual(folga, 1, places=4)

    def test_apoio_lateral_e_reedicao_mantem_folga(self):
        conj = self.nicho()
        primeira = self.criar_por_pontos(conj, (-0.3, -0.15, 0), (0, -0.15, 0.4),
                                         folhas=1)
        folha = addon.portas._folhas_portas(primeira)[0]
        borda = self.limites_folhas(conj, primeira)[1][0]
        segunda = self.criar_por_pontos(
            conj, (borda, -0.168, 0), (0.3, -0.15, 0.4),
            (folha, addon.modulos._chapas_do_conjunto(conj)[0]), folhas=1)
        self.assertAlmostEqual(self.limites_folhas(conj, segunda)[0][0] - borda,
                               0.002, places=5)
        for _ in range(2):
            bpy.ops.object.cabinet_portas(editar=True, grupo_nome=segunda.name,
                                          entre_folhas_mm=4)
            self.assertAlmostEqual(self.limites_folhas(conj, segunda)[0][0] - borda,
                                   0.004, places=5)

    def test_frente_automatica_nos_tres_eixos(self):
        # The constant axis between opposite corners is the normal; derive its side
        # from the cabinet center. Constant Z means a horizontal door.
        ref, centro = Matrix.Identity(3), (0, 0, 0.5)
        casos = [(((-0.3, -0.2, 0.1), (0.3, -0.2, 0.9)), 'NEG_Y'),
                 (((-0.3, 0.2, 0.1), (0.3, 0.2, 0.9)), 'POS_Y'),
                 (((0.3, -0.2, 0.1), (0.3, 0.2, 0.9)), 'POS_X'),
                 (((-0.3, -0.2, 1.0), (0.3, 0.2, 1.0)), 'POS_Z'),
                 (((-0.3, -0.2, 0.0), (0.3, 0.2, 0.0)), 'NEG_Z')]
        for (a, b), esperado in casos:
            with self.subTest(esperado=esperado):
                self.assertEqual(addon.portas._frente_automatica(ref, a, b, centro),
                                 esperado)
        # For a horizontal door, width follows the longer side of the corner span.
        self.assertEqual(addon.portas._largura_do_vao(ref, (0, 0, 1), (0.6, 0.4, 1)), 'X')
        self.assertEqual(addon.portas._largura_do_vao(ref, (0, 0, 1), (0.4, 0.6, 1)), 'Y')

    def test_mapear_porta_deitada(self):
        for a, b in (((0, 0, 1), (0.6, 0.4, 1)), ((0, 0, 1), (0.4, 0.6, 1))):
            for frente, sinal in (('POS_Z', 1), ('NEG_Z', -1)):
                with self.subTest(b=b, frente=frente):
                    l, h, matriz = addon.portas._mapear_vao_portas(
                        a, b, Matrix.Identity(3), frente)
                    self.assertAlmostEqual(l, 600, places=3)
                    self.assertAlmostEqual(h, 400, places=3)
                    self.assertAlmostEqual(matriz.determinant(), 1)
                    self.assertAlmostEqual(matriz.col[2].z, sinal)

    def porta_deitada(self, conj, z):
        L, A, P, E = (v / 1000 for v in addon.portas._caixa_do_modulo(conj))
        chapa = addon.modulos._chapas_do_conjunto(conj)[0]
        return self.criar_por_pontos(
            conj, (-L / 2, -P / 2, z), (L / 2, P / 2, z), (chapa, chapa),
            frente='AUTO', folhas=1,
            centro=addon.portas._centro_do_movel(chapa, chapa))

    def test_tampa_de_bau_nasce_em_cima_e_acompanha_o_modulo(self):
        conj = self.nicho()
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        grupo = self.porta_deitada(conj, A / 1000)
        self.assertEqual(grupo['porta_frente'], 'POS_Z')
        largura, altura = max(L, P), min(L, P)
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], largura - 2 * E, places=2)
        self.assertAlmostEqual(grupo['porta_vao_altura_mm'], altura - 2 * E, places=2)
        lo, hi = self.limites_folhas(conj, grupo)
        # Full overlay covers the entire top and sits above it with clearance.
        folga = folga_reta()
        self.assertAlmostEqual(lo[2], (A + folga) / 1000, places=5)
        self.assertAlmostEqual(hi[2], (A + E + folga) / 1000, places=5)
        r2 = 2 * addon.portas.RESPIRO_PORTA_MM
        self.assertAlmostEqual(hi[0] - lo[0], (L - r2) / 1000, places=5)
        self.assertAlmostEqual(hi[1] - lo[1], (P - r2) / 1000, places=5)
        conj.conj_largura_mm = L + 200
        conj.conj_altura_mm = A + 100
        bpy.context.view_layer.update()
        lo, hi = self.limites_folhas(conj, grupo)
        self.assertAlmostEqual(hi[0] - lo[0], (L + 200 - r2) / 1000, places=5)
        self.assertAlmostEqual(lo[2], (A + 100 + folga) / 1000, places=5)

    def test_porta_na_base_aponta_para_baixo(self):
        conj = self.nicho()
        grupo = self.porta_deitada(conj, 0.0)
        self.assertEqual(grupo['porta_frente'], 'NEG_Z')
        lo, hi = self.limites_folhas(conj, grupo)
        self.assertAlmostEqual(hi[2], -folga_reta() / 1000, places=5)
        self.assertLess(lo[2], 0.0)

    def test_lateral_e_porta_seguem_a_espessura_do_modulo(self):
        conj = self.nicho()
        conj.conj_espessura_mm = 15.0
        bpy.context.view_layer.update()
        grupo = self.porta_no_nicho(conj)
        self.assertEqual(grupo['porta_parametros']['lateral_mm'], 15.0)
        self.assertEqual(grupo['porta_parametros']['espessura_mm'], 15.0)
        # Regression: the side retained its creation-time thickness, so changing cabinet
        # thickness left the full-overlay door protruding.
        conj.conj_espessura_mm = 30.0
        bpy.context.view_layer.update()
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        lo, hi = self.limites_folhas(conj, grupo)
        r2 = 2 * addon.portas.RESPIRO_PORTA_MM
        self.assertAlmostEqual(hi[0] - lo[0], (L - r2) / 1000, places=5)
        self.assertAlmostEqual(hi[2] - lo[2], (A - r2) / 1000, places=5)
        self.assertEqual(grupo['porta_parametros']['lateral_mm'], 30.0)

    def test_espessura_de_uma_folha_vale_para_a_porta(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        folhas = addon.portas._folhas_portas(grupo)
        # Free thickness: no longer rounded to 15/18/20/30.
        folhas[0].chapa_espessura_mm = 21.0
        for folha in addon.portas._folhas_portas(grupo):
            self.assertEqual(folha.chapa_espessura_mm, 21.0)
            self.assertAlmostEqual(folha.dimensions.z, 0.021, places=5)
        self.assertEqual(grupo['porta_parametros']['espessura_mm'], 21.0)
        # The rear face remains in the opening plane plus full-overlay clearance.
        lo, _ = self.limites_folhas(conj, grupo)
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        self.assertAlmostEqual(lo[1], -(P / 2 + folga_reta()) / 1000 - 0.021,
                               places=5)
        conj.conj_largura_mm = L + 100
        bpy.context.view_layer.update()
        for folha in addon.portas._folhas_portas(grupo):
            self.assertEqual(folha.chapa_espessura_mm, 21.0)

    def test_reconfigurar_nao_volta_a_espessura(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        addon.portas._folhas_portas(grupo)[0].chapa_espessura_mm = 20.0
        self.assertEqual(bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', editar=True, grupo_nome=grupo.name,
            dobradica='RETA', folhas=2), {'FINISHED'})
        for folha in addon.portas._folhas_portas(grupo):
            self.assertEqual(folha.chapa_espessura_mm, 20.0)

    # ------------------------------------------- Editing a placed door
    def aba_portas(self):
        bpy.context.scene.cabinet_aba = 'PORTAS'
        return addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)

    def test_niveis_de_selecao_modulo_porta_folha(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        folha = addon.portas._folhas_portas(grupo)[1]
        addon.hud._selecionar_chapa_hud(bpy.context, folha)
        self.assertEqual(bpy.context.object, conj)
        self.assertEqual(addon.hud._nivel_da_selecao(bpy.context, folha), 'MODULO')
        addon.hud._selecionar_porta_hud(bpy.context, folha, 'PORTA')
        self.assertEqual(bpy.context.object, grupo)
        self.assertEqual(set(bpy.context.selected_objects),
                         {grupo, *addon.portas._folhas_portas(grupo)})
        self.assertEqual(addon.hud._nivel_da_selecao(bpy.context, folha), 'PORTA')
        self.assertIsNone(addon.hud._alvo_hud(bpy.context))
        addon.hud._selecionar_porta_hud(bpy.context, folha, 'FOLHA')
        self.assertEqual(list(bpy.context.selected_objects), [folha])
        self.assertEqual(addon.hud._nivel_da_selecao(bpy.context, folha), 'FOLHA')
        self.assertIsNone(addon.hud._alvo_hud(bpy.context))
        # Shift adds the door to selection instead of replacing it.
        addon.hud._selecionar_chapa_hud(bpy.context, folha)          # The cabinet.
        addon.hud._selecionar_porta_hud(bpy.context, folha, 'PORTA', somar=True)
        self.assertIn(conj, bpy.context.selected_objects)
        # The leaf is the native active object without switching to individual-door selection.
        self.assertEqual(bpy.context.object, folha)
        self.assertEqual(addon.hud._nivel_da_selecao(bpy.context, folha), 'PORTA')
        self.assertTrue(grupo.select_get())
        # Selecting only a leaf also disables the native outline because it counts as a door.
        addon.hud._selecionar_porta_hud(bpy.context, folha, 'FOLHA')
        self.assertIn(folha.name, addon.eventos._grupos_selecionados(bpy.context.view_layer))

    def test_aba_mostra_a_porta_selecionada_e_nao_a_cena(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)       # Full overlay, two leaves.
        cena = bpy.context.scene
        antes = {p: getattr(cena, p) for p in addon.portas._PROPS_PORTAS_CENA}
        self.addCleanup(lambda: [setattr(cena, p, v) for p, v in antes.items()])
        cena.porta_dobradica = 'CURVA'
        cena.porta_folhas = 1
        addon.hud._selecionar_porta_hud(bpy.context, addon.portas._folhas_portas(grupo)[0],
                                    'PORTA')
        widgets = self.aba_portas()
        acesos = {v[5][1]: v[5] for v in widgets
                  if v[5] and v[5][0] == 'escolha' and v[5][3]}
        # Hinge type is automatic and absent from the tab, as requested.
        self.assertNotIn("Hinge", [v[4] for v in widgets])
        folhas = next(v[5] for v in widgets
                      if v[5] and v[5][:2] == ('contador', 'porta_folhas'))
        self.assertEqual(folhas[2], 2)
        self.assertEqual(folhas[5], grupo.name)
        self.assertNotIn('porta_folhas', acesos)       # No segments.
        # No perimeter-clearance field, as requested.
        self.assertFalse([v for v in widgets if v[5] and v[5][0] == 'medida'
                          and v[5][2] == 'ui_porta_folga'])
        rotulos = [v[4] for v in widgets]
        # No redundant door-number/opening-dimensions header.
        self.assertFalse(any(r.startswith("Door ") and 'vao' in r
                             for r in rotulos))
        botao = next(v[5] for v in widgets if v[5] and v[5][0] == 'portas')
        self.assertTrue(botao[4])

    def test_aba_da_porta_com_moldura_em_categorias(self):
        # User audit: compact fields grouped by Door, Leaves, Frame and Opening,
        # without clipped text or overlap; the frame is editable
        # in that section.
        import blf
        conj = self.nicho()
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        y = -P / 2
        grupo = self.porta_por_quatro_cliques(
            conj, (-L / 2, y, A), (-L / 2 + E, y, A - E), (L / 2 - E, y, E),
            (L / 2, y, 0), abertura='CORRER', folhas=2)
        self.assertEqual(len(addon.portas._moldura_da_porta(grupo)), 6)
        addon.hud._selecionar_porta_hud(
            bpy.context, addon.portas._folhas_portas(grupo)[0], 'PORTA')
        bpy.context.scene.cabinet_aba = 'PORTAS'
        titulos = ["Door", "Leaves", "Frame", "Opening"]
        for largura in (190, 320, 564):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1600)
            ys = {v[4]: v[1] for v in widgets if v[5] is None and v[4] in titulos}
            self.assertEqual(sorted(ys, key=lambda t: -ys[t]), titulos, largura)
            campos = {v[5][2]: v for v in widgets if v[5] and v[5][0] == 'medida'}
            for prop in ('ui_porta_moldura', 'ui_porta_rodape', 'ui_porta_testeira'):
                self.assertIn(prop, campos)
                self.assertLess(campos[prop][1], ys["Frame"])
                self.assertGreater(campos[prop][1], ys["Opening"])
            self.assertNotIn('ui_porta_recuo_correr', campos)     # Framed, without recess.
            interativos = [v for v in widgets if v[5] and v[5][0] in {
                'medida', 'contador', 'operador', 'escolha', 'slider'}
                and v[1] > 0]
            for i, a in enumerate(interativos):
                self.assertLessEqual(a[0] + a[2], min(largura - 12, 552) + 0.01)
                for b in interativos[i + 1:]:
                    self.assertFalse(
                        a[0] < b[0] + b[2] - 0.01 and b[0] < a[0] + a[2] - 0.01
                        and a[1] < b[1] + b[3] - 0.01 and b[1] < a[1] + a[3] - 0.01,
                        (largura, a[4], b[4]))
            # Show the entire label, even at the minimum font size of 9.
            blf.size(0, 9)
            for v in campos.values():
                self.assertLessEqual(blf.dimensions(0, v[5][3])[0], v[2] - 14,
                                     (largura, v[5][3]))
        # Setting plinth height to zero in the tab removes it from the frame.
        self.assertIsNone(addon.gaveta_eventos.aplicar_medida(
            bpy.context, 'porta', grupo.name, 'ui_porta_rodape', 0.0))
        self.assertEqual({o['porta_moldura_peca']
                          for o in addon.portas._moldura_da_porta(grupo)},
                         {'LATERAL_ESQ', 'LATERAL_DIR', 'BASE_CIMA',
                          'TESTEIRA', 'BASE_BAIXO'})

    def test_folhas_e_campo_compacto_sem_linha_de_acoes_em_cima(self):
        # User request: replace the 1/2/3/4 leaf-count choices with a compact field
        # beside the last door field (between leaves/planes), supporting drag and typing.
        # The action row was removed at the user's request.
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)       # Full overlay, two leaves.
        addon.hud._selecionar_porta_hud(
            bpy.context, addon.portas._folhas_portas(grupo)[0], 'PORTA')
        bpy.context.scene.cabinet_aba = 'PORTAS'
        ops = ('object.cabinet_apanhar_vao', 'object.cabinet_definir_frente',
               'object.cabinet_espelhar_porta')
        for largura in (190, 320, 564):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1400)
            campo = next(v for v in widgets
                         if v[5] and v[5][:2] == ('contador', 'porta_folhas'))
            self.assertEqual(campo[2], addon.gaveta.LARGURA_CAMPO_FOLHAS)
            self.assertTrue(addon.gaveta_desenho._eh_campo_contador(campo[5]))
            vizinho = next(v for v in widgets if v[5] and v[5][0] == 'medida'
                           and v[5][2] == 'ui_porta_entre_folhas')
            self.assertEqual(vizinho[1], campo[1], largura)    # Same row.
            self.assertLessEqual(vizinho[0] + vizinho[2], campo[0])
            self.assertLessEqual(campo[0] + campo[2], min(largura - 12, 552) + 0.01)
            botoes = [v for v in widgets if v[5] and v[5][0] == 'operador'
                      and v[5][1] in ops]
            self.assertFalse(botoes)
        # Allow any typed number: store counts supported by the opening type;
        # otherwise warn without changing the door.
        self.assertIsNone(addon.gaveta_eventos.aplicar_medida(
            bpy.context, 'contador', grupo.name, 'porta_folhas', 1.0))
        self.assertEqual(int(grupo['porta_parametros']['folhas']), 1)
        self.assertEqual(len(addon.portas._folhas_portas(grupo)), 1)
        erro = addon.gaveta_eventos.aplicar_medida(
            bpy.context, 'contador', grupo.name, 'porta_folhas', 7.0)
        self.assertTrue(erro)
        self.assertEqual(int(grupo['porta_parametros']['folhas']), 1)

    def test_editar_parametro_muda_so_aquela_porta(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        cena_antes = bpy.context.scene.porta_dobradica
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'dobradica', 'SUPER_CURVA'), '')
        self.assertEqual(grupo['porta_parametros']['dobradica'], 'SUPER_CURVA')
        self.assertEqual(bpy.context.scene.porta_dobradica, cena_antes)
        # Inset leaves stay inside the cabinet.
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        lo, hi = self.limites_folhas(conj, grupo)
        self.assertGreater(lo[0], -L / 2000)
        self.assertLess(hi[0], L / 2000)
        # And continue following the cabinet.
        conj.conj_largura_mm = L + 100
        bpy.context.view_layer.update()
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], L + 100 - 2 * E,
                               places=2)
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'folhas', 1), '')
        self.assertEqual(len(addon.portas._folhas_portas(grupo)), 1)

    def test_valor_invalido_nao_muda_a_porta(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        antes = dict(grupo['porta_parametros'])
        coords = [tuple(f.matrix_world @ v.co) for f in addon.portas._folhas_portas(grupo)
                  for v in f.data.vertices]
        self.assertTrue(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'folga_mm', 5000.0))
        self.assertEqual(dict(grupo['porta_parametros']), antes)
        self.assertEqual(coords, [tuple(f.matrix_world @ v.co)
                                  for f in addon.portas._folhas_portas(grupo)
                                  for v in f.data.vertices])

    def test_campos_da_aba_e_espessura_editam_a_porta(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        addon.hud._selecionar_porta_hud(bpy.context, addon.portas._folhas_portas(grupo)[0],
                                    'FOLHA')
        self.assertEqual(bpy.ops.object.cabinet_editar_medida_gaveta(
            'EXEC_DEFAULT', dono='porta', objeto=bpy.context.object.name,
            propriedade='ui_porta_afastamento', valor=0.003), {'FINISHED'})
        self.assertAlmostEqual(grupo['porta_parametros']['afastamento_mm'], 3.0)
        modo, campos, dono = addon.gaveta._medidas_gaveta(bpy.context)
        self.assertEqual((modo, dono), ('PORTA', 'porta'))
        self.assertEqual([c[2] for c in campos], ['', '', 'ui_porta_espessura'])
        self.assertEqual(bpy.ops.object.cabinet_editar_medida_gaveta(
            'EXEC_DEFAULT', dono='porta', objeto=bpy.context.object.name,
            propriedade='ui_porta_espessura', valor=0.021), {'FINISHED'})
        for folha in addon.portas._folhas_portas(grupo):
            self.assertEqual(folha.chapa_espessura_mm, 21.0)   # Free.

    def test_porta_selecionada_so_na_aba_portas_e_sem_dobradicas(self):
        # User request: the menu reflects selection. Doors belong in the Doors tab,
        # not Cabinets. Hinge settings belong to hardware selection,
        # so they do not appear for a selected door.
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        addon.hud._selecionar_porta_hud(bpy.context, addon.portas._folhas_portas(grupo)[0],
                                    'PORTA')

        def painel(aba):
            bpy.context.scene.cabinet_aba = aba
            _c, conteudo, _r = addon.gaveta._partes_gaveta(
                addon.gaveta._widgets_gaveta(bpy.context, 320, 1400))
            return [v[5] for v in addon.gaveta._paineis_gaveta(conteudo)[0] if v[5]]

        portas = painel('PORTAS')
        self.assertEqual([a[3] for a in portas if a[0] == 'medida'][:3],
                         ["Width", "Height", "Thickness"])
        self.assertNotIn('modo', [a[0] for a in portas])
        props = {a[1] for a in portas if a[0] == 'escolha'}
        props |= {a[2] for a in portas if a[0] == 'medida'}
        self.assertFalse(props & {'dobradicas_qtd', 'dobradicas_margem_mm',
                                  'pistoes_qtd', 'pistoes_offset_mm'})
        self.assertFalse([a for a in painel('MODULOS') if a[0] == 'medida'])

    def apanhador_diagonal(self, conj, internos=False, meia=False, **escolhas):
        tipo = addon.assistente.OBJECT_OT_apanhar_vao_portas
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        dx = E / 2 if meia else E if internos else 0
        dz = E if internos else 0
        a, b = [conj.matrix_world @ (Vector(p) / 1000) for p in
                ((-L / 2 + dx, -P / 2, A - dz), (L / 2 - dx, -P / 2, dz))]
        chapas = addon.modulos._chapas_do_conjunto(conj)
        oa = min(chapas, key=lambda o: (conj.matrix_world.inverted() @ o.matrix_world.translation).x)
        ob = max(chapas, key=lambda o: (conj.matrix_world.inverted() @ o.matrix_world.translation).x)
        falso = SimpleNamespace(_grupo_alvo='', _pontos=[(a, oa), (b, ob)],
            _imantado=None, _objeto_imantado=None,
            _w=dict(etapa='DIAGONAL', escolhas=dict(folhas=1, abertura='GIRO', **escolhas)),
            _encerrar=lambda c: None)
        for nome in ('_referencia', '_centro', '_associar', '_cliques', '_instrucao', '_previa',
                     '_marcar_canto'):
            setattr(falso, nome, lambda *args, nome=nome: getattr(tipo, nome)(falso, *args))
        falso.PASSOS_CANTOS = tipo.PASSOS_CANTOS
        return falso

    def test_wizard_novo_e_reposicionar_usam_so_dois_cantos(self):
        tipo = addon.assistente.OBJECT_OT_apanhar_vao_portas
        for alvo in ('', 'Porta existente'):
            falso = SimpleNamespace(_grupo_alvo=alvo, _pontos=[], PASSOS_CANTOS=tipo.PASSOS_CANTOS)
            self.assertEqual(tipo._cliques(falso), 2)
            self.assertIn('1/2', tipo._instrucao(falso))
            falso._pontos = [(None, None)]
            self.assertIn('2/2', tipo._instrucao(falso))

    def test_wizard_diagonal_calcula_cobertura_e_execucao_igual_a_previa(self):
        tipo = addon.assistente.OBJECT_OT_apanhar_vao_portas
        for internos, meia, cob, dobradica in ((False, False, [1]*4, 'RETA'),
                (True, False, [0]*4, 'SUPER_CURVA'), (False, True, [.5, .5, 1, 1], 'CURVA')):
            with self.subTest(internos=internos, meia=meia):
                self.setUp()
                conj = self.nicho()
                falso = self.apanhador_diagonal(conj, internos, meia)
                pontos = list(falso._pontos)
                falso._pontos = pontos[:1]
                falso._imantado, falso._objeto_imantado = pontos[1]
                caixas = falso._previa()
                self.assertEqual(len(caixas), 1)
                self.assertEqual([falso._w['coberturas'][k] for k in addon.portas.COBERTURAS_LADOS], cob)
                falso._pontos = pontos
                self.assertEqual(tipo._concluir(falso, bpy.context, falso._w['escolhas']), {'FINISHED'})
                grupo, = addon.portas._portas_do_conjunto(conj)
                self.assertEqual(grupo['porta_parametros']['dobradica'], dobradica)
                for folha in addon.portas._folhas_portas(grupo):
                    for v in folha.data.vertices:
                        self.assertLess(min((folha.matrix_world @ v.co - p).length
                                            for caixa in caixas for p in caixa), 1e-5)

    def test_wizard_dois_cantos_modal_avanca_e_diagonal_invalida_pode_ser_refeita(self):
        conj = self.nicho()
        tipo = addon.assistente.OBJECT_OT_apanhar_vao_portas
        falso = self.apanhador_diagonal(conj)
        pontos, falso._pontos = falso._pontos, []
        falso._area = SimpleNamespace(tag_redraw=lambda: None, header_text_set=lambda t: None)
        falso._etapa_vista = 'DIAGONAL'
        falso._engolir_soltar = False
        falso._imantar = lambda e: tipo._imantar(falso, e)
        falso._mouse_na_regiao = lambda e: Vector((100, 100))
        falso.report = lambda *a: None
        falso._ir = lambda etapa, mouse=None: falso._w.update(etapa=etapa)
        iniciados = []
        falso._iniciar_snap = lambda c: iniciados.append(c)
        # The point arrives through the native cursor/snap macro without reading meshes;
        # the timer resumes the modal operator with the confirmed point.
        evento = SimpleNamespace(type='TIMER', value='NOTHING')
        with patch.object(addon.assistente.view3d_utils, 'location_3d_to_region_2d',
                          side_effect=AssertionError('projetou vertices')):
            self.assertEqual(tipo.modal(falso, bpy.context, evento), {'RUNNING_MODAL'})
            self.assertEqual(len(iniciados), 0)     # Without a request, do not restart.
            for ponto, obj in (pontos[0], pontos[0], pontos[1]):
                falso._w['ponto_confirmado'] = (ponto, obj.name)
                self.assertEqual(tipo.modal(falso, bpy.context, evento), {'RUNNING_MODAL'})
                if falso._w['etapa'] == 'DIAGONAL':
                    # Native snapping restarts between corners.
                    self.assertEqual(tipo.modal(falso, bpy.context, evento), {'RUNNING_MODAL'})
            self.assertEqual(len(falso._pontos), 2)
            self.assertEqual(falso._w['etapa'], 'FOLHAS')
            self.assertEqual(len(iniciados), 2)
        tipo._voltar(falso)
        self.assertEqual(falso._w['etapa'], 'DIAGONAL')
        self.assertEqual(len(falso._pontos), 1)
        self.assertTrue(falso._w['iniciar_snap'])

    # Regression, fixed in v305: native snap returns only a point. Its panel was
    # resolved by a ray cast grazing the opening corner, or from the active cabinet.
    # With no cabinet selected, no part was found; the second click crashed the wizard,
    # leaving handlers and HUD stuck and preventing door creation.
    def test_wizard_acha_a_chapa_do_ponto_sem_modulo_ativo(self):
        conj = self.nicho()
        G = addon.gavetas
        bpy.context.view_layer.objects.active = None
        falso = self.apanhador_diagonal(conj)
        contexto = SimpleNamespace(
            area=SimpleNamespace(spaces=SimpleNamespace(active=SimpleNamespace(region_3d=None))),
            region=None, object=None, visible_objects=bpy.context.visible_objects,
            scene=bpy.context.scene)
        with patch.object(G.view3d_utils, 'location_3d_to_region_2d', return_value=None):
            for ponto, obj in falso._pontos:
                nome = G._objeto_do_ponto_criacao(contexto, ponto)
                self.assertEqual(addon.portas._modulo_da_chapa(bpy.data.objects[nome]), conj)
            # A free point snapped without a vertex has no part.
            self.assertIsNone(G._objeto_do_ponto_criacao(contexto, Vector((9, 9, 9))))

    def test_wizard_ponto_sem_peca_pede_outro_clique(self):
        conj = self.nicho()
        tipo = addon.assistente.OBJECT_OT_apanhar_vao_portas
        falso = self.apanhador_diagonal(conj)
        primeiro, segundo = falso._pontos
        falso._pontos = [primeiro]
        falso._area = SimpleNamespace(tag_redraw=lambda: None, header_text_set=lambda t: None)
        falso._etapa_vista = 'DIAGONAL'
        falso._imantar = lambda e: tipo._imantar(falso, e)
        falso._mouse_na_regiao = lambda e: Vector((100, 100))
        avisos = []
        falso.report = lambda nivel, texto: avisos.append(texto)
        falso._w['ponto_confirmado'] = (segundo[0], None)
        evento = SimpleNamespace(type='TIMER', value='NOTHING')
        self.assertEqual(tipo.modal(falso, bpy.context, evento), {'RUNNING_MODAL'})
        self.assertEqual(len(falso._pontos), 1)
        self.assertEqual(falso._w['etapa'], 'DIAGONAL')
        self.assertTrue(falso._w['iniciar_snap'])
        self.assertTrue(avisos)

    def test_wizard_diagonal_girada_e_ordem_inversa_preservam_cobertura(self):
        conj = self.nicho()
        conj.rotation_euler = (.1, -.2, .4)
        conj.location = (2, -3, 1)
        bpy.context.view_layer.update()
        falso = self.apanhador_diagonal(conj)
        falso._pontos.reverse()
        self.assertTrue(falso._previa())
        self.assertEqual([falso._w['coberturas'][k] for k in addon.portas.COBERTURAS_LADOS], [1]*4)

    def test_wizard_diagonal_de_correr_resolve_embutida_e_moldura(self):
        tipo = addon.assistente.OBJECT_OT_apanhar_vao_portas
        conj = self.nicho()
        for internos in (False, True):
            falso = self.apanhador_diagonal(conj, internos)
            falso._w['escolhas']['abertura'] = 'CORRER'
            self.assertTrue(falso._previa())
            self.assertEqual(falso._w['embutida'], internos)
            self.assertEqual(tipo._metade_metade(falso), False)

    # ------------------------------------------------ Wizard (legacy API)
    def test_quatro_cliques_coberturas_e_dobradica(self):
        # User drawing: 1 = door corner, 2 = opening corner, 3 = opposite opening corner,
        # 4 = opposite door corner. Coverage on each side is measured in thickness units.
        E = 18.0
        bordas = [Vector((-18, 382, 0)), Vector((573, -18, 0))]
        vaos = [Vector((0, 364, 0)), Vector((564, 0, 0))]
        cob = addon.portas._coberturas_dos_cantos(bordas, vaos, E)
        self.assertEqual([cob[k] for k in addon.portas.COBERTURAS_LADOS],
                         [1.0, 0.5, 1.0, 1.0])
        self.assertEqual(addon.portas._lados_fora_do_padrao(cob), [])
        # Within +/-2 mm still counts as full overlay; 40 mm extra does not.
        self.assertEqual(addon.portas._encaixar_cobertura(19.5, E), 1.0)
        self.assertEqual(addon.portas._lados_fora_do_padrao(addon.portas._coberturas_dos_cantos(
            [Vector((-58, 382, 0)), bordas[1]], vaos, E)), ['cobertura_esq_e'])
        # When clicks 1 and 2 coincide, use pair 3-4's margin,
        # measured inward from the click.
        novos, espelhados = addon.portas._espelhar_margem(
            [Vector((-18, 382, 0)), Vector((582, -18, 0))],
            [Vector((-18, 382, 0)), Vector((564, 0, 0))])
        self.assertEqual(espelhados, [True, False])
        self.assertEqual(novos[0].to_tuple(), (0.0, 364.0, 0.0))
        # Both pairs coincide: do not mirror anything.
        self.assertEqual(addon.portas._espelhar_margem(vaos, vaos)[1], [False, False])
        # Determine hinge type automatically from coverage on its side.
        self.assertEqual([addon.portas._dobradica_da_cobertura(f) for f in (1.0, 0.5)],
                         ['RETA', 'CURVA'])
        self.assertEqual(addon.portas._dobradica_da_cobertura(0.0, embutida=True),
                         'SUPER_CURVA')
        self.assertTrue(addon.portas._porta_embutida(dict.fromkeys(
            addon.portas.COBERTURAS_LADOS, 0.0)))
        self.assertFalse(addon.portas._porta_embutida(cob))
        # Hinge line: on the panel's inner face at the opening edge, with the leaf's
        # length. The user's screenshot showed it incorrectly at the leaf's
        # outer edge.
        arestas = addon.portas._arestas_da_porta(564.0, 364.0, cob, E, 'GIRO')
        self.assertEqual([a['lado'] for a in arestas], ['ESQUERDA', 'DIREITA'])
        esq, dir_ = arestas
        cobre = E - addon.portas.RESPIRO_PORTA_MM      # Full overlay also has clearance.
        self.assertEqual((esq['a'].x, esq['a'].y, esq['b'].y),
                         (0.0, -cobre, 364.0 + cobre))
        self.assertEqual(dir_['a'].x, 564.0)
        # Half coverage = half the thickness minus 2 mm clearance.
        self.assertEqual((esq['cobertura'], dir_['cobertura']), (cobre, 7.0))
        cima, = addon.portas._arestas_da_porta(564.0, 364.0, cob, E, 'BASCULANTE')
        self.assertEqual((cima['lado'], cima['a'].y, cima['a'].x, cima['b'].x),
                         ('CIMA', 364.0, -cobre, 571.0))

    def test_volume_da_dobradica_na_face_interna(self):
        cob = dict.fromkeys(addon.portas.COBERTURAS_LADOS, 1.0)
        esq, dir_ = addon.portas._arestas_da_porta(564.0, 364.0, cob, 18.0, 'GIRO')
        (corpo, caneco), = addon.portas._caixas_dobradicas(esq, [100.0], 0.0)
        faixa = lambda caixa, i: (min(p[i] for p in caixa), max(p[i] for p in caixa))
        # Body: from the inner face (x = 0) into the cabinet, behind the leaf.
        self.assertEqual(faixa(corpo, 0), (0.0, addon.portas.DOBRADICA_AVANCO_MM))
        cobre = 18.0 - addon.portas.RESPIRO_PORTA_MM    # The leaf starts here.
        self.assertEqual(faixa(corpo, 1), (100.0 - cobre - 25.0,
                                           100.0 - cobre + 25.0))
        self.assertEqual(faixa(corpo, 2), (-addon.portas.DOBRADICA_FUNDO_MM, 0.0))
        # Cup: in the leaf, 5 mm from its edge (x = -cobre), 12 mm deep.
        self.assertEqual(faixa(caneco, 0), (-cobre + 5.0, -cobre + 40.0))
        self.assertEqual(faixa(caneco, 2), (-addon.portas.CANECO_ABA_MM,
                                            addon.portas.CANECO_FUNDO_MM))
        # On the other side, the volume points in the opposite direction.
        (corpo, _caneco), = addon.portas._caixas_dobradicas(dir_, [100.0], 0.0)
        self.assertEqual(faixa(corpo, 0), (564.0 - addon.portas.DOBRADICA_AVANCO_MM, 564.0))

    def test_ferragens_em_segmentos_iguais_com_margem(self):
        self.assertEqual(addon.portas._posicoes_ferragens(700.0, 3, 100.0),
                         [100.0, 350.0, 600.0])
        self.assertEqual(addon.portas._posicoes_ferragens(700.0, 1, 100.0), [350.0])
        self.assertEqual(addon.portas._posicoes_ferragens(100.0, 2, 80.0), [50.0, 50.0])
        self.assertEqual(addon.portas._posicoes_ferragens(500.0, 0, 100.0), [])
        # Woodworking defaults, editable in the wizard.
        self.assertEqual([addon.portas._qtd_dobradicas_padrao(a)
                          for a in (700, 900, 1200, 1800, 2200)],
                         [2, 2, 3, 4, 5])
        self.assertEqual(addon.portas._qtd_pistoes_padrao(560), 1)
        self.assertEqual(addon.portas._qtd_pistoes_padrao(800), 2)
        self.assertEqual(addon.portas.MARGEM_DOBRADICAS_PADRAO, 100.0)

    def test_dobradicas_nunca_se_sobrepoem(self):
        # User report: during mouse-Y placement the margin reached the edge midpoint,
        # making hinges overlap.
        ajustar = addon.portas._ajustar_dobradicas
        passo = addon.portas.PASSO_MIN_DOBRADICAS_MM
        meia = addon.portas.DOBRADICA_ALTURA_MM / 2.0
        self.assertEqual(ajustar(700.0, 3, 100.0), (3, 100.0))     # Default unchanged.
        self.assertEqual(ajustar(700.0, 3, 350.0), (3, (700.0 - 2 * passo) / 2))
        self.assertEqual(ajustar(700.0, 3, 0.0), (3, meia))        # Entirely inside the leaf.
        self.assertEqual(ajustar(200.0, 6, 100.0)[0], 3)           # Only as many as fit.
        # Wizard typed value and mouse Y use the same function.
        w = {'aresta': {'a': Vector((0.0, 0.0)), 'b': Vector((0.0, 700.0))},
             'qtd': 3, 'margem': 100.0}
        addon.portas._assistente_porta[0] = w
        try:
            addon.assistente._editar_assistente('dobradicas_margem_mm', 5000.0)
            self.assertEqual((w['qtd'], w['margem']), (3, 290.0))
            # More hinges require a smaller margin so they fit.
            addon.assistente._editar_assistente('dobradicas_qtd', 6)
            self.assertEqual((w['qtd'], w['margem']), (6, 200.0))
        finally:
            addon.portas._assistente_porta[0] = None
        for comprimento in (120.0, 200.0, 333.0, 700.0, 1500.0, 2400.0):
            for qtd in range(2, 7):
                for margem in (0.0, 50.0, 100.0, 400.0, comprimento):
                    n, m = ajustar(comprimento, qtd, margem)
                    pos = addon.portas._posicoes_ferragens(comprimento, n, m)
                    self.assertGreaterEqual(pos[0], meia - 1e-6)
                    self.assertLessEqual(pos[-1], comprimento - meia + 1e-6)
                    for a, b in zip(pos, pos[1:]):
                        self.assertGreaterEqual(b - a, passo - 1e-6,
                                                (comprimento, qtd, margem))
        # Existing door: the stored margin obeys the same limit; legacy stored margins
        # must not stack the hinges.
        conj = self.nicho()
        grupo = self.porta_de_giro(conj)
        margem = addon.ferragens._valor_ferragem(grupo, 'dobradicas_margem_mm', 5000.0)
        p, largura, altura, folhas = addon.ferragens._porta_calculada(grupo)
        aresta, pos, _i = addon.ferragens._dobradicas_da_porta(
            p, largura, altura, folhas)[0]
        comprimento = (aresta['b'] - aresta['a']).length
        self.assertAlmostEqual(margem, (comprimento - (len(pos) - 1) * passo) / 2)
        p['dobradicas_margem_mm'] = 5000.0
        _a, pos, _i = addon.ferragens._dobradicas_da_porta(
            p, largura, altura, folhas)[0]
        self.assertTrue(all(b - a >= passo - 1e-6 for a, b in zip(pos, pos[1:])), pos)

    def test_pistao_automatico_dobra_do_fechado_ao_aberto(self):
        # User rule: at 90 degrees open, strut length is twice its closed length.
        # Use the largest real catalog model fitting the opening's upper two thirds.
        e = 18.0

        def folha(altura):          # Full overlay: the leaf extends 18 mm above.
            return (600.0, altura + 2 * e, e, (300.0, altura / 2.0, e / 2.0))

        def medidas(g, f):
            lateral, fechada, aberta = addon.portas._pontas_pistao(g, 25.0, f)
            return (fechada - lateral).length, (aberta - lateral).length

        escolhidos = []
        for altura in (250.0, 350.0, 500.0, 800.0):
            f = folha(altura)
            g = addon.portas._pistao_do_vao(altura, f)
            self.assertIn(g['aberto'], [m[0] for m in addon.portas.PISTOES_CATALOGO])
            fechado, aberto = medidas(g, f)
            self.assertAlmostEqual(fechado, g['aberto'] / 2.0, places=3)
            self.assertAlmostEqual(aberto, g['aberto'], places=3)
            self.assertLessEqual(g['offset'], altura * 2.0 / 3.0)
            # The side attachment sits behind the leaf, below the bracket.
            lateral, na_folha, _a = addon.portas._pontas_pistao(g, 25.0, f)
            self.assertLess(lateral.y, na_folha.y)
            self.assertLess(lateral.z, na_folha.z)
            escolhidos.append(g['aberto'])
        self.assertEqual(escolhidos, sorted(escolhidos))
        self.assertLess(escolhidos[0], escolhidos[-1])
        # Open length is maximum extension, with the leaf correctly positioned and rotated.
        p = {'abertura': 'BASCULANTE'}
        f = folha(350.0)
        g = addon.portas._pistao_do_vao(350.0, f)
        _l, _f, aberta = addon.portas._pontas_pistao(g, 25.0, f)
        _l, fechada, _a = addon.portas._pontas_pistao(g, 25.0, f)
        giro = addon.ferragens._matriz_abertura(p, 600.0, 1, 0, f, 1.0)
        c = Vector(f[3])
        girada = giro @ ((fechada - c) / 1000.0) * 1000.0
        self.assertLess((girada - aberta).length, 1e-3)

        # Manual adjustment only raises it. Lowering beyond automatic stops at maximum
        # travel; raising reduces open length while preserving closed length.
        auto = g['offset']
        abaixo = addon.portas._pistao_do_vao(350.0, f, auto + 80.0)
        self.assertAlmostEqual(abaixo['offset'], auto, places=3)
        acima = addon.portas._pistao_do_vao(350.0, f, auto - 40.0)
        self.assertAlmostEqual(acima['offset'], auto - 40.0, places=3)
        self.assertEqual(acima['aberto'], g['aberto'])
        fechado, aberto = medidas(acima, f)
        self.assertAlmostEqual(fechado, g['aberto'] / 2.0, places=3)
        self.assertLess(aberto, g['aberto'])
        self.assertAlmostEqual(aberto, acima['alcance'], places=3)
        # The wizard highlights the closed strut's volume like the hinges:
        # body and rod from end to end, plus both mounting brackets.
        itens = addon.ferragens._pistoes_da_porta({'pistoes_qtd': 1}, 600.0, 350.0, [f])
        caixas = addon.ferragens._caixas_dos_itens_pistao(itens)
        self.assertEqual(len(caixas), 4)
        lateral, fechada, _a = addon.portas._pontas_pistao(g, 25.0, f)
        self.assertAlmostEqual((sum(caixas[0], Vector()) / 8
                                - (lateral + fechada) / 2).length, 0.0, places=3)
        # Even the leaf bracket must not rise as far as the hinge.
        topo = addon.portas._pistao_do_vao(350.0, f, 1.0)
        self.assertAlmostEqual(topo['offset'], topo['offset_min'], places=3)
        self.assertAlmostEqual(topo['d'], addon.portas.PISTAO_DA_DOBRADICA_MIN_MM)

    def test_porta_guarda_as_ferragens_do_wizard(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        # Without a wizard: 0 means automatic, left side.
        p = grupo['porta_parametros']
        self.assertEqual((p['dobradicas_qtd'], p['dobradica_lado']), (0, 'ESQUERDA'))
        # The tab must still read the door without failing on the new fields.
        valores = addon.gaveta._valores_portas(bpy.context.scene, grupo)
        self.assertEqual(valores['dobradica_lado'], 'ESQUERDA')
        addon.portas._carregar_portas_na_cena(bpy.context.scene, grupo)

    def test_campos_da_porta_seguem_a_abertura(self):
        # A selected door shows fields appropriate to its type.
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        addon.hud._selecionar_porta_hud(bpy.context, addon.portas._folhas_portas(grupo)[0],
                                    'PORTA')
        bpy.context.scene.cabinet_aba = 'PORTAS'

        def props():
            return {v[5][2] for v in addon.gaveta._widgets_gaveta(bpy.context, 320, 1400)
                    if v[5] and v[5][0] == 'medida'
                    and v[5][2].startswith('ui_porta_')}

        self.assertNotIn('ui_porta_folga', props())
        self.assertNotIn('ui_porta_recuo_correr', props())
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'abertura', 'CORRER'), '')
        self.assertIn('ui_porta_recuo_correr', props())
        self.assertNotIn('ui_porta_afastamento', props())
        # Overlap follows from leaf width, so it has no separate field.
        self.assertNotIn('ui_porta_sobreposicao', props())

    def test_previa_e_execucao_usam_o_mesmo_vao(self):
        from types import SimpleNamespace
        conj, cima, baixo = self.duas_fileiras()
        folha = addon.portas._folhas_portas(cima)[-1]
        a = conj.matrix_world @ Vector((-0.3, -0.15, 0))
        # The upper door's base, on which the lower door was supported.
        z = self.limites_folhas(conj, cima)[0][2]
        b = conj.matrix_world @ Vector((0.3, -0.168, z))
        chapa = addon.modulos._chapas_do_conjunto(conj)[0]
        tipo = addon.assistente.OBJECT_OT_apanhar_vao_portas
        # Four clicks: door and opening coincide at both corners.
        falso = SimpleNamespace(_pontos=[(a, chapa), (a, chapa), (b, folha), (b, folha)],
                                _imantado=b, _objeto_imantado=folha,
                                _frente='NEG_Y')
        falso._referencia = lambda a, b: tipo._referencia(falso, a, b)
        falso._centro = lambda a, b: tipo._centro(falso, a, b)
        caixas = tipo._previa(falso)
        self.assertEqual(len(caixas), 2)
        esperados = [p for caixa in caixas for p in caixa]
        reais = [f.matrix_world @ v.co for f in addon.portas._folhas_portas(baixo)
                 for v in f.data.vertices]
        for p in reais:
            self.assertLess(min((p - q).length for q in esperados), 1e-5)


    def test_folha_quadro_de_aluminio_na_porta_de_correr(self):
        # User request: Promob's distinctive sliding leaf becomes our own style:
        # an aluminum profile, 23 mm deep with a 10 mm face, around a 5 mm panel;
        # the track remains the add-on's.
        conj = self.nicho()
        grupo = addon.portas.porta_no_modulo(conj, folhas=2, abertura='CORRER')
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'folha', 'QUADRO'), '')
        grupo = addon.portas._portas_do_conjunto(conj)[-1]
        for folha in addon.portas._folhas_portas(grupo):
            self.assertAlmostEqual(folha.chapa_espessura_mm, 23.0, places=3)
            # Four profile bars plus the panel: five boxes of eight vertices.
            self.assertEqual(len(folha.data.vertices), 40)
            self.assertEqual([m.name for m in folha.data.materials],
                             [addon.portas.NOME_MATERIAL_QUADRO,
                              addon.portas.NOME_MATERIAL_PAINEL])
            # The panel (material 1) sits 6 mm from the outer face.
            painel = [folha.data.vertices[i].co.z * 1000.0
                      for p in folha.data.polygons if p.material_index == 1
                      for i in p.vertices]
            self.assertAlmostEqual(max(painel), 23.0 / 2 - 6.0, places=3)
        # The tab shows the leaf-style choice only for sliding doors.
        addon.hud._selecionar_porta_hud(
            bpy.context, addon.portas._folhas_portas(grupo)[0], 'PORTA')
        bpy.context.scene.cabinet_aba = 'PORTAS'
        acoes = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 480, 1600) if v[5]]
        self.assertTrue(any(a[0] == 'escolha' and a[1] == 'porta_folha' for a in acoes))
        # Back to a plain panel: an 18 mm box with one material.
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'folha', 'CHAPA'), '')
        for folha in addon.portas._folhas_portas(addon.portas._portas_do_conjunto(conj)[-1]):
            self.assertAlmostEqual(folha.chapa_espessura_mm, 18.0, places=3)
            self.assertEqual(len(folha.data.vertices), 8)
            self.assertNotIn('chapa_quadro_mm', folha)

    def test_zigzag_espelha_a_cadeia_e_mantem_eixos_coincidentes(self):
        f = addon.ferragens
        for lado in ('ESQUERDA', 'DIREITA'):
            for n in (3, 4, 8):
                p = parametros(abertura='ZIGZAG', folhas=n, dobradica_lado=lado)
                folhas = addon.portas._calcular_folhas_portas(1200, 800, p)
                for fracao in (0, .5, 1):
                    poses = f._matrizes_zigzag(p, 1200, folhas, fracao)
                    for i in range(1, n):
                        junta = f._junta_zigzag(p, folhas[i-1], folhas[i], i) / 1000
                        a = poses[i-1] @ Matrix.Translation(-Vector(folhas[i-1][3]) / 1000)
                        b = poses[i] @ Matrix.Translation(-Vector(folhas[i][3]) / 1000)
                        self.assertLess((a @ junta - b @ junta).length, 1e-6)
                        ang_a = math.atan2(a[0][2], a[0][0])
                        ang_b = math.atan2(b[0][2], b[0][0])
                        self.assertAlmostEqual(ang_a, -ang_b, places=5)

    def test_zigzag_puxador_ultima_folha_abertura_e_edicao(self):
        conj = self.nicho()
        grupo = addon.portas.porta_no_modulo(conj, folhas=3, abertura='ZIGZAG')
        self.assertEqual(grupo.name, "Folding Door")
        for quantidade in (3, 5, 2):
            self.assertEqual(addon.portas._editar_parametro_porta(bpy.context, grupo, 'folhas', quantidade), '')
            folhas = addon.portas._folhas_portas(grupo)
            puxadores = [c for folha in folhas for c in folha.children if addon.chapas.MARCA_PUXADOR in c]
            self.assertEqual(len(puxadores), 1)
            self.assertEqual(puxadores[0].parent, folhas[-1])
            addon.ferragens._definir_abertura(bpy.context, folhas[-1], .7)
            self.assertTrue(all(abs(f.get(addon.ferragens.CHAVE_ABERTURA) - .7) < 1e-6 for f in folhas))
            fechado = addon.ferragens._matriz_fechada(folhas[-1])
            self.assertGreater((folhas[-1].matrix_world.translation - fechado.translation).length, .01)
        addon.portas._editar_parametro_porta(bpy.context, grupo, 'dobradica_lado', 'DIREITA')
        self.assertEqual(puxadores[0]['puxador_borda'], 'X-')
        addon.hud._selecionar_porta_hud(bpy.context, folhas[0], 'PORTA')
        self.assertEqual(addon.portas_viewport._folhas_com_slider(bpy.context), folhas[-1:])

    def test_parafusos_padrao_nas_dobradicas(self):
        # User request: the same real-size screw on hinges and handles, matching
        # its photo: a 3.5 x 14 countersunk chipboard screw.
        conj = self.nicho()
        grupo = addon.portas.porta_no_modulo(conj, folhas=3, abertura='ZIGZAG')
        ferragens = addon.ferragens._ferragens_portas(grupo)
        parafuso = addon.ferragens.malha_parafuso()
        nome = addon.ferragens.NOME_PARAFUSO
        # Full-overlay rig: two screws in each hinge's plate and two in its cup.
        rig = [o for o in ferragens if o.type == 'MESH' and 'cabinet_peca' in o
               and o.data.get('cabinet_origem') == nome]
        raizes = [o for o in ferragens if o.get('cabinet_peca') == 'raiz']
        self.assertEqual(len(rig), 4 * len(raizes))
        for o in rig:
            for s in o.matrix_world.to_scale():
                self.assertAlmostEqual(s, 1.0, places=4)
        # Articulated hinge: replace the disks with the screw and its steel material.
        articulados = [o for o in ferragens if 'Parafuso' in o.get('porta_ferragem_id', '')]
        self.assertTrue(articulados)
        for o in articulados:
            self.assertEqual(len(o.data.vertices), len(parafuso.vertices))
            self.assertEqual([m.get('cabinet_origem') for m in o.data.materials], ['Aco Bicromatizado'])
            # Selection lines, per user screenshot: only the head's top circle and cross,
            # without threads or the bottom of the cross recess.
            contorno = addon.arame._contorno_da_ferragem(o.data)
            self.assertTrue(contorno)
            self.assertLess(len(contorno), len(o.data.edges) // 2)
            # The head protrudes outward by SALIENCIA; rotation reverses the sign.
            for p in contorno:
                self.assertAlmostEqual(abs(p.z), addon.ferragens.SALIENCIA_PARAFUSO_MM / 1000.0,
                                       places=6)
        # An existing scene mesh lacking the top marker is rebuilt once.
        velha = parafuso.copy()
        del velha[addon.arame.MARCA_ARAME_TOPO]
        velha.attributes.remove(velha.attributes[addon.arame.ATRIBUTO_SEM_ARAME])
        self.assertGreater(len(addon.arame._contorno_malha(velha)),
                           len(addon.arame._contorno_malha(parafuso)))
        addon.arame.marcar_arame_parafuso(velha)
        self.assertEqual(addon.arame._contorno_malha(velha), addon.arame._contorno_malha(parafuso))

    def test_dobradica_antiga_da_cena_troca_sozinha(self):
        # User report: a preset/scene with the original full-overlay hinge used the
        # adjustment screw on mounting plates; rebuilding the door was needed to update it.
        # The hardware timer now replaces the old copy.
        F = addon.ferragens
        conj = self.nicho()
        grupo = addon.portas.porta_no_modulo(conj)
        raizes = [o for o in F._ferragens_portas(grupo) if o.get('cabinet_peca') == 'raiz']
        self.assertTrue(raizes)
        self.assertFalse(F._ferragens_antigas(grupo))
        for raiz in raizes:
            raiz['cabinet_versao'] = 2              # The one used by library presets.
        self.assertTrue(F._ferragens_antigas(grupo))
        F._conferir_ferragens()
        self.assertFalse(F._ferragens_antigas(grupo))
        ferragens = F._ferragens_portas(grupo)
        raizes = [o for o in ferragens if o.get('cabinet_peca') == 'raiz']
        self.assertTrue(raizes)
        # Mounting plate and cup use the standard screw; the adjustment screw stays on the arm.
        malhas = [o for o in ferragens if o.type == 'MESH']
        padrao = [o for o in malhas if o.data.get('cabinet_origem') == F.NOME_PARAFUSO]
        self.assertEqual(len(padrao), 4 * len(raizes))
        regulagem = [o for o in malhas if o.data.get('cabinet_origem') == 'Dobradica Parafuso']
        self.assertEqual(len(regulagem), len(raizes))
        for o in regulagem:
            self.assertTrue(o.parent.name.startswith('Hinge Support'), o.parent.name)
        # Also update the flush 7 mm countersunk head (version 1), previously reused by name.
        rente = padrao[0].data.copy()
        rente['cabinet_versao'] = 1
        padrao[0].data = rente
        self.assertTrue(F._ferragens_antigas(grupo))
        self.assertTrue(F.parafuso_atual(F.malha_parafuso()))
        # A pan-head screw (v323) in hardware also counts as outdated.
        padrao[0].data = bpy.data.meshes.new('Panela')
        padrao[0].data['cabinet_origem'] = 'Parafuso Chipboard 3,5x14'
        self.assertTrue(F._ferragens_antigas(grupo))

    def test_zigzag_volumes_presos_as_duas_folhas(self):
        conj = self.nicho()
        grupo = addon.portas.porta_no_modulo(conj, folhas=3, abertura='ZIGZAG')
        folhas = addon.portas._folhas_portas(grupo)
        ferragens = addon.ferragens._ferragens_portas(grupo)
        self.assertTrue(any(o.get('cabinet_peca') == 'base' for o in ferragens))
        for i in (1, 2):
            itens = [o for o in ferragens if o.get('porta_ferragem_id', '').startswith('ART_%d_' % i)]
            self.assertTrue(any('Articulated Hinge Pin' in o.name for o in itens))
            self.assertTrue(any(o.parent == folhas[i-1] for o in itens))
            self.assertTrue(any(o.parent == folhas[i] for o in itens))
            for o in itens:
                self.assertGreater(len(o.data.vertices), 0)
        meshes = {o.name: o.data.as_pointer() for o in ferragens if o.type == 'MESH'}
        addon.ferragens._definir_abertura(bpy.context, folhas[-1], 1)
        self.assertEqual(meshes, {o.name: o.data.as_pointer() for o in ferragens if o.type == 'MESH'})

    def test_assistente_oferece_zigzag_tres_folhas(self):
        tipo = addon.assistente.OBJECT_OT_apanhar_vao_portas
        chamadas = []
        op = SimpleNamespace(_w=dict(etapa='FOLHAS', escolhas={}, embutida=False),
                             _ir=chamadas.append)
        tipo._escolher(op, bpy.context, '3')
        self.assertIn(('ZIGZAG', 'Zig-zag'), op._w['tipos'])
        self.assertEqual(chamadas, ['TIPO'])

    def test_oito_folhas_cabem_na_caixa_de_viewport_baixa(self):
        for tamanho in ((190, 180), (320, 200), (564, 800)):
            botoes = addon.assistente._botoes_assistente(Vector((185, 20)),
                addon.portas.OPCOES_FOLHAS, 1, tamanho, "How many leaves?")
            self.assertEqual(len(botoes), 8)
            for (x, y, w, h), chave, texto in botoes:
                self.assertGreaterEqual(x, 10)
                self.assertGreaterEqual(y, 10)
                self.assertLessEqual(x + w, tamanho[0] - 10 + 1e-6)
                self.assertLessEqual(y + h + 24, tamanho[1] - 10 + 1e-6)

    def test_foto_de_canto_fecha_todas_as_folhas(self):
        conj = self.nicho()
        grupo = addon.portas.porta_no_modulo(conj, folhas=2)
        original = addon.formas.forma_do_modulo
        try:
            addon.formas.forma_do_modulo = lambda c: {'cantos': [dict(tipo='RECORTE')]}
            for f in addon.portas._folhas_portas(grupo):addon.ferragens._definir_abertura(bpy.context,f,.7)
            addon.biblioteca.preparar_abertura_foto(bpy.context, conj)
            self.assertEqual([f[addon.ferragens.CHAVE_ABERTURA] for f in addon.portas._folhas_portas(grupo)], [0, 0])
            addon.formas.forma_do_modulo = lambda c: {'cantos': [None] * 4}
            addon.biblioteca.preparar_abertura_foto(bpy.context, conj)
            self.assertEqual([f[addon.ferragens.CHAVE_ABERTURA] for f in addon.portas._folhas_portas(grupo)], [0, 0])
        finally:
            addon.formas.forma_do_modulo = original

    def test_foto_fecha_tambem_correr_basculante_e_zigzag(self):
        for abertura in ('GIRO','CORRER','BASCULANTE','ZIGZAG'):
            conj=addon.modulos.criar_armario(bpy.context,'Foto',600,700,550,fundo=False)
            grupo=addon.portas.porta_no_modulo(conj,folhas=2,abertura=abertura)
            folhas=addon.portas._folhas_portas(grupo)
            for f in folhas:addon.ferragens._definir_abertura(bpy.context,f,.8)
            quantidade=len(bpy.data.objects)
            addon.biblioteca.preparar_abertura_foto(bpy.context,conj)
            self.assertEqual(len(bpy.data.objects),quantidade)
            self.assertTrue(all(f[addon.ferragens.CHAVE_ABERTURA]==0 for f in folhas))

    def test_foto_fecha_porta_sem_alterar_lado_nem_preset_original(self):
        import tempfile,os
        conj=self.nicho()
        grupo=self.porta_de_giro(conj,dobradica_lado='DIREITA')
        caminho=os.path.join(tempfile.mkdtemp(),'Foto.blend')
        bpy.data.libraries.write(caminho,{conj,*conj.children_recursive})
        addon.biblioteca.preparar_abertura_foto(bpy.context,conj)
        self.assertEqual(grupo['porta_parametros']['dobradica_lado'],'DIREITA')
        folha,=addon.portas._folhas_portas(grupo)
        self.assertEqual(folha[addon.ferragens.CHAVE_ABERTURA],0)
        with bpy.data.libraries.load(caminho) as (de,para):para.objects=list(de.objects)
        original,=[o for o in para.objects if addon.chapas.MARCA_PORTAS in o]
        self.assertEqual(original['porta_parametros']['dobradica_lado'],'DIREITA')
        self.assertTrue(all(f.get(addon.ferragens.CHAVE_ABERTURA,0)==0 for f in addon.portas._folhas_portas(original)))

    # Regression, fixed in v302: Esc during hinge dragging restored only the margin,
    # losing the arrangement measured from Promob.
    def test_esc_no_arraste_da_dobradica_preserva_a_referencia(self):
        conj=self.nicho();grupo=self.porta_de_giro(conj)
        p=addon.portas._copiar_parametros(grupo['porta_parametros'])
        p['dobradicas_referencia']={'0':[.16,.77]}
        addon.portas._reaplicar_portas(bpy.context,grupo,p)
        classe=addon.ferragens.OBJECT_OT_arrastar_ferragem
        self.addCleanup(addon.ferragens._arraste_ferragem.__setitem__,0,None)
        op=SimpleNamespace(grupo=grupo.name,tipo='DOBRADICA',_nome='dobradicas_margem_mm',
                           _antes=addon.portas._copiar_parametros(grupo['porta_parametros']),
                           _estado=None,_area=SimpleNamespace(tag_redraw=lambda:None))
        op._aplicar=lambda c,v:classe._aplicar(op,c,v)
        op._restaurar=lambda c:classe._restaurar(op,c)
        op._refazer=lambda c,e:classe._refazer(op,c,e)
        op._encerrar=lambda:classe._encerrar(op)
        addon.ferragens._arraste_ferragem[0]=(grupo.name,'DOBRADICA')
        op._aplicar(bpy.context,123.)
        self.assertNotIn('dobradicas_referencia',grupo['porta_parametros'])
        self.assertEqual(classe.modal(op,bpy.context,SimpleNamespace(type='ESC',value='PRESS')),{'CANCELLED'})
        self.assertEqual(list(grupo['porta_parametros']['dobradicas_referencia']['0']),[.16,.77])

    def test_padrao_esquerdo_preserva_alturas_material_uid_e_puxador(self):
        conj=self.nicho();grupo=self.porta_de_giro(conj,dobradica_lado='DIREITA')
        p=addon.portas._copiar_parametros(grupo['porta_parametros'])
        p['dobradicas_referencia']={'0':[.16,.77]}
        addon.portas._reaplicar_portas(bpy.context,grupo,p)
        folha,=addon.portas._folhas_portas(grupo)
        material=bpy.data.materials.new('Porta madeira');folha.data.materials.append(material)
        uid=folha.get('chapa_uid');fechada=addon.ferragens._matriz_fechada(folha)
        pux=addon.puxadores.criar_puxador(bpy.context,folha,'PERFIL','X-',1)
        self.assertTrue(addon.portas.preferir_abertura_esquerda(bpy.context,grupo))
        self.assertEqual(grupo['porta_parametros']['dobradica_lado'],'ESQUERDA')
        self.assertEqual(list(grupo['porta_parametros']['dobradicas_referencia']['0']),[.16,.77])
        self.assertEqual(folha.get('chapa_uid'),uid)
        self.assertEqual(folha.material_slots[0].material,material)
        self.assertEqual(pux.get('puxador_borda'),'X+')
        self.assertLess((addon.ferragens._matriz_fechada(folha).translation-fechada.translation).length,1e-6)
        self.assertFalse(addon.portas.preferir_abertura_esquerda(bpy.context,grupo))

    def test_padrao_esquerdo_nao_cria_dobradica_sem_lateral_de_apoio(self):
        conj=self.nicho();grupo=self.porta_de_giro(conj,dobradica_lado='DIREITA')
        laterais=[o for o in addon.modulos._chapas_do_conjunto(conj) if abs(addon.chapas._eixos(o)[2].x)>.9]
        esquerda=min(laterais,key=lambda o:o.matrix_world.translation.x)
        bpy.data.objects.remove(esquerda,do_unlink=True);bpy.context.view_layer.update()
        self.assertFalse(addon.portas.preferir_abertura_esquerda(bpy.context,grupo))
        self.assertEqual(grupo['porta_parametros']['dobradica_lado'],'DIREITA')

    def _canto_135(self, lado):
        conj = self.nicho()
        grupo = self.porta_de_giro(conj, dobradica='CURVA', dobradica_lado=lado)
        p = addon.portas._copiar_parametros(grupo['porta_parametros'])
        p['dobradica'] = 'CURVA'
        addon.portas._reaplicar_portas(bpy.context, grupo, p)
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        esquerda = lado == 'ESQUERDA'
        laterais = [o for o in addon.modulos._chapas_do_conjunto(conj) if abs(addon.chapas._eixos(o)[2].x) > .9]
        suporte = (min if esquerda else max)(laterais, key=lambda o: o.matrix_world.translation.x)
        q = conj.matrix_world @ (Vector((-L / 2 + E if esquerda else L / 2 - E, -P / 2, 0)) / 1000)
        suporte.matrix_world = (Matrix.Translation(q) @ Matrix.Rotation(math.radians(45 if esquerda else -45), 4, 'Z')
                                @ Matrix.Translation(-q) @ suporte.matrix_world)
        bpy.context.view_layer.update()
        addon.ferragens._refazer_ferragens(grupo)
        bpy.context.view_layer.update()
        return conj, grupo, suporte

    def test_dobradica_de_135_encosta_com_a_face_inteira_sem_penetrar(self):
        # Regression v232: minimum distance accepted a single corner.
        for lado in ('ESQUERDA', 'DIREITA'):
            self.setUp()
            conj, grupo, suporte = self._canto_135(lado)
            bases = [o for o in addon.ferragens._ferragens_portas(grupo) if 'porta_ferragem_apoio' in o]
            self.assertEqual(len(bases), 2)
            im = suporte.matrix_world.inverted()
            for base in bases:
                self.assertEqual(base['porta_ferragem_apoio'], suporte)
                contatos, distancias = [], []
                for v in base.data.vertices:
                    local = im @ (base.matrix_world @ v.co)
                    hit, ponto, normal, face = suporte.closest_point_on_mesh(local)
                    self.assertTrue(hit)
                    delta = suporte.matrix_world.to_3x3() @ (local - ponto)
                    distancias.append(delta.length)
                    if delta.length < .00005:
                        contatos.append(base.matrix_world @ v.co)
                    self.assertGreaterEqual((local - ponto).dot(normal), -.00005)
                self.assertEqual(len(contatos), 4)
                self.assertLess(max(distancias), .0031)
                # Four vertices cover an area rather than a segment.
                self.assertGreater((contatos[1] - contatos[0]).cross(contatos[2] - contatos[0]).length, .001)

    def test_braco_angular_segue_o_copo_sem_refazer_malhas(self):
        conj, grupo, suporte = self._canto_135('DIREITA')
        folha, = addon.portas._folhas_portas(grupo)
        bracos = [o for o in addon.ferragens._ferragens_portas(grupo) if 'Angled Hinge Arm' in o.name]
        self.assertEqual(len(bracos), 2)
        meshes = [o.data.as_pointer() for o in bracos]
        for fracao in (0, .5, 1):
            addon.ferragens._definir_abertura(bpy.context, folha, fracao)
            for braco in bracos:
                r, = [c for c in braco.constraints if c.type == 'STRETCH_TO']
                self.assertEqual(r.target.parent, folha)
                ponta = braco.matrix_world @ Vector((0, r.rest_length, 0))
                self.assertLess((ponta - r.target.matrix_world.translation).length, 1e-5)
        self.assertEqual(meshes, [o.data.as_pointer() for o in bracos])

    def test_braco_angular_espelhado_preserva_volume_e_migra_mira_antiga(self):
        conj,grupo,suporte=self._canto_135('DIREITA')
        bracos=[o for o in addon.ferragens._ferragens_portas(grupo) if 'Angled Hinge Arm' in o.name]
        self.assertEqual(len(bracos),2)
        for braco in bracos:
            r,=[c for c in braco.constraints if c.type=='STRETCH_TO']
            r.owner_space=r.target_space='WORLD';r.space_object=None
        addon.ferragens._conferir_ferragens();bpy.context.view_layer.update()
        for braco in bracos:
            r,=[c for c in braco.constraints if c.type=='STRETCH_TO']
            self.assertEqual((r.owner_space,r.target_space,r.space_object),('CUSTOM','CUSTOM',grupo))
        antes={o.name:[o.matrix_world@v.co for v in o.data.vertices] for o in bracos}
        espelho=conj.matrix_world@Matrix.Diagonal((-1,1,1,1))@conj.matrix_world.inverted()
        conj.scale.x=-1;bpy.context.view_layer.update()
        for o in bracos:
            self.assertLess(max((o.matrix_world@v.co-espelho@p).length
                for v,p in zip(o.data.vertices,antes[o.name])),1e-5)

    def test_prisma_angular_e_arame_preservam_o_plano_real(self):
        conj, grupo, suporte = self._canto_135('ESQUERDA')
        p, L, A, folhas = addon.ferragens._porta_calculada(grupo)
        apoios = addon.ferragens._apoios_obliquos(conj, grupo.matrix_world, p, L, A, folhas)
        itens = addon.ferragens._ferragens_da_porta(p, L, A, folhas, apoios)
        _, pontos = addon.arame._arame_dos_itens(itens)
        self.assertTrue(pontos)
        for item in [i for i in itens if i['forma'] == 'PRISMA']:
            obj = next(o for o in grupo.children if o.get('porta_ferragem_id') == item['id'])
            vs = [obj.matrix_world @ v.co for v in obj.data.vertices]
            for ponto in item['cantos']:
                mundo = grupo.matrix_world @ (ponto / 1000)
                self.assertLess(min((v - mundo).length for v in vs), 1e-6)
        # Further tilting the support rebuilds the fit from its current geometry.
        suporte.location.y += .01
        bpy.context.view_layer.update()
        addon.ferragens._refazer_ferragens(grupo)
        bpy.context.view_layer.update()
        self.assertEqual(len([o for o in grupo.children if 'porta_ferragem_apoio' in o]), 2)

    def test_atualiza_preset_antigo_sem_alterar_porta_puxador_ou_abertura(self):
        conj, grupo, suporte = self._canto_135('ESQUERDA')
        folha, = addon.portas._folhas_portas(grupo)
        puxador = addon.puxadores.criar_puxador(bpy.context, folha, 'PERFIL', 'X+', 1)
        addon.ferragens._definir_abertura(bpy.context, folha, .6)
        bpy.context.view_layer.update()
        antes = (folha.matrix_world.copy(), folha.data.as_pointer(), puxador.as_pointer(), folha[addon.ferragens.CHAVE_ABERTURA])
        del grupo['porta_ferragens_encaixe']
        addon.ferragens._conferir_ferragens()
        bpy.context.view_layer.update()
        self.assertEqual(grupo['porta_ferragens_encaixe'], 1)
        self.assertEqual((folha.data.as_pointer(), puxador.as_pointer(), folha[addon.ferragens.CHAVE_ABERTURA]), antes[1:])
        self.assertLess(max(abs(a - b) for r, s in zip(folha.matrix_world, antes[0]) for a, b in zip(r, s)), 1e-6)

with tempfile.TemporaryDirectory(prefix='cabinet_portas_') as pasta:
    with patch.object(addon.biblioteca, 'pasta_biblioteca', return_value=pasta), \
         patch.object(addon.opcoes, '_pasta_addon', return_value=pasta):
        addon.register()
        try:
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestPortas)
            resultado = unittest.TextTestRunner(verbosity=2).run(suite)
        finally:
            addon.unregister()
        addon.register()
        addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError("Door tests failed")
