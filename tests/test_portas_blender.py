"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_portas_blender.py"""
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
import cabinet_creator as addon


def folga_reta():
    """Folga minima (mm) da porta Reta ate' o modulo: a do rig do usuario."""
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
    """O bloco com y relativo ao 1o widget: na aba Portas ele desce para
    caber o "Criar Portas" no topo (Epico 2.3); o CONTEUDO e as posicoes
    entre os campos continuam identicos."""
    if not bloco:
        return bloco
    y0 = bloco[0][1]
    return [(b[0], b[1] - y0) + tuple(b[2:]) for b in bloco]


class TestPortas(unittest.TestCase):
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
        # Uma pequena torcao deixa o centro medio do quad fora dos seus
        # triangulos, como a folha real exportada pelo Promob.
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

    # Regressao (era BUG): o raio acertava o proprio quad torcido.
    def test_curva_torcida_reconhece_superficies_inteiras(self):
        g, f, n = self._porta_curva_torcida()
        ref = addon.frentes.referencia(f)
        for chave, inicio in (('frente', 0), ('tras', n),
                              ('cima_frente', 2*n), ('cima_tras', 3*n)):
            self.assertEqual(len(ref[chave]), n, chave)
            for atual, v in zip(ref[chave], list(f.data.vertices)[inicio:inicio+n]):
                self.assertLess((Vector(atual) - v.co).length, 1e-6)

    # Regressao (era BUG): rotulos e cache truncados sobreviviam ao preparo.
    def test_curva_recupera_cache_antigo_truncado_sem_recriar_mesh(self):
        g, f, n = self._porta_curva_torcida()
        malha = f.data
        for i, valor in enumerate(malha.attributes[addon.frentes.ATR_FACE].data):
            valor.value = 1 if i == 0 else -1 if i == 1 else 0
        rotulos = {frozenset((0, 1)): 1, frozenset((2*n, 2*n+1)): 2,
                   frozenset((n, n+1)): 3, frozenset((3*n, 3*n+1)): 4}
        for aresta, valor in zip(malha.edges, malha.attributes[addon.frentes.ATR_BORDA].data):
            valor.value = rotulos.get(frozenset(aresta.vertices), 0)
        # Simula a referencia antiga valida pelo hash, mas incompleta.
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

    # Regressao (era BUG): transporte aberto herdava o contorno truncado.
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
        # Deformacao radial conhecida, independente do solver de formas.
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
        # O caneco fica atras da face fisica, tambem com a folha aberta.
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
        c=addon.modulos.criar_armario(bpy.context,'Espelhar',600,700,550,fundo=False)
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

    def test_espelhar_grupo_e_folha_tem_icone_e_menu_contextual(self):
        c=addon.modulos.criar_armario(bpy.context,'Menu',600,700,550,fundo=False)
        g=addon.portas.porta_no_modulo(c)
        for o in bpy.context.selected_objects:o.select_set(False)
        g.select_set(True);bpy.context.view_layer.objects.active=g
        bpy.context.scene.cabinet_aba='PORTAS'
        for largura in (190,320,564):
            acoes=[w[5] for w in addon.gaveta._widgets_gaveta(bpy.context,largura,1400)]
            self.assertIn(('operador','object.cabinet_espelhar_porta'),acoes)
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
        # Como no append: o Blender renomeia o pai, mas nao uma string.
        g[addon.portas.CHAVE_MODULO_PORTA]=outro.name
        self.assertEqual(addon.portas._portas_do_conjunto(c),[g])
        self.assertEqual(addon.portas._portas_do_conjunto(outro),[])
        antes=float(g['porta_vao_largura_mm'])
        c.conj_largura_mm=800
        self.assertAlmostEqual(float(g['porta_vao_largura_mm'])-antes,200,delta=.05)

    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        # Este script usa somente a cena descartavel de --factory-startup.
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        # cada armario tem a sua Collection (nome e' do grupo)
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
        # Curva: metade da lateral MENOS o respiro (pedido do usuario).
        # Reta: a folga minima do rig do usuario ate' o modulo.
        # Nunca rente a' borda (pedido do usuario): Reta = espessura menos
        # o respiro, embutida = o respiro para dentro do vao.
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
        # Print do usuario: duas portas Curva dividindo a chapa do meio se
        # encostavam. Cada uma cobre metade MENOS 2 mm: sobram 4 mm.
        E = 18.0
        meia = dict(cobertura_esq_e=1.0, cobertura_dir_e=0.5,
                    cobertura_baixo_e=1.0, cobertura_cima_e=1.0)
        l, _a, _e, c = addon.portas._calcular_folhas_portas(
            300, 800, parametros(dobradica='CURVA', **meia))[0]
        direita_a = c[0] + l / 2                     # vao A: 0..300
        espelho = dict(meia, cobertura_esq_e=0.5, cobertura_dir_e=1.0)
        l, _a, _e, c = addon.portas._calcular_folhas_portas(
            300, 800, parametros(dobradica='CURVA', **espelho))[0]
        esquerda_b = 300 + E + c[0] - l / 2          # vao B: depois da chapa
        self.assertAlmostEqual(direita_a, 300 + E / 2 - 2, places=6)
        self.assertAlmostEqual(esquerda_b - direita_a,
                               2 * addon.portas.RESPIRO_PORTA_MM, places=6)
        self.assertEqual(addon.portas._cobertura_mm(0.5, E), 7.0)
        self.assertEqual(addon.portas._cobertura_mm(1.0, E), E - addon.portas.RESPIRO_PORTA_MM)
        self.assertEqual(addon.portas._cobertura_mm(0.0, E), -addon.portas.RESPIRO_PORTA_MM)
        self.assertEqual(addon.portas._cobertura_mm(0.8, E), 0.8 * E)   # marcada

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
        # pedido do usuario: cada folha no SEU trilho (plano proprio), a 1a
        # na frente; o recuo mede a face mais externa
        r = addon.portas.RESPIRO_PORTA_MM
        util = 600 - 2 * r
        for n in range(1, 5):
            folhas = addon.portas._calcular_folhas_portas(
                600, 800, parametros(abertura='CORRER', folhas=n))
            # o respiro de cada lado: nem a de correr encosta na lateral
            self.assertAlmostEqual(folhas[0][3][0] - folhas[0][0] / 2, r)
            if n == 1:
                # a unica tem METADE do vao: sobra para onde correr
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
            # espalhadas no vao: 1a a' esquerda, ultima a' direita
            self.assertAlmostEqual(folhas[0][3][0] - 175, r)
            if n > 1:
                self.assertAlmostEqual(folhas[-1][3][0] + 175, 600 - r)
        # maior que o vao: fica do vao (o modulo encolheu)
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
        cobre = 18 - addon.portas.RESPIRO_PORTA_MM - 2          # menos a folga
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
        # vao, grupo, 4 solidos e os trilhos de cima e de baixo
        self.assertEqual(len(bpy.data.objects), 8)
        trilhos = addon.ferragens._ferragens_portas(grupo)
        self.assertEqual(sorted(o.name for o in trilhos),
                         ['Trilho Inferior', 'Trilho Superior'])
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
        pai = bpy.data.objects.new('Modulo', None)
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
        # Caminho do apanhador (`cabinet_apanhar_vao`): os pontos
        # chegam prontos e o Modo Edicao nao entra na historia.
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
        # 600 x 800 de vao, dobradica reta: cobre a lateral dos dois
        # lados. Nos eixos LOCAIS da folha, X=largura, Y=altura e
        # Z=espessura -- a altura nao e' o Z.
        cobre = (18 - addon.portas.RESPIRO_PORTA_MM) / 1000.0
        self.assertAlmostEqual(folha.dimensions.x, 0.6 + 2 * cobre, places=4)
        self.assertAlmostEqual(folha.dimensions.y, 0.8 + 2 * cobre, places=4)
        self.assertAlmostEqual(folha.dimensions.z, 0.018, places=4)

    def test_referencia_do_par_usa_o_ancestral_comum(self):
        # A mesma regra serve ao Modo Edicao e ao apanhador; se as duas
        # divergirem, o vao sai girado num dos caminhos.
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
        """Sem o asset da dobradica reta: caixas e eixo fixo -- o caminho
        das portas Curva/embutida (e de quem nao tem o asset)."""
        original = addon.ferragens._dados_dobradica_reta
        addon.ferragens._dados_dobradica_reta = lambda: None
        self.addCleanup(setattr, addon.ferragens, '_dados_dobradica_reta', original)

    def nicho(self):
        """Modulo de verdade, com laterais, base e tampo."""
        bpy.ops.object.cabinet_criar_nicho()
        # O nicho cria as chapas soltas; o Empty do conjunto, com as
        # medidas parametricas, vem do agrupar.
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar()
        conj = next(o for o in bpy.data.objects
                    if addon.chapas.MARCA_CONJUNTO in o)
        bpy.context.view_layer.update()
        return conj

    def porta_no_nicho(self, conj):
        """Cria a porta pelo vao interno do modulo (cenario 2)."""
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
        # Com o vinculo, quem fica ativo e' o MODULO (etapa 3), entao o
        # grupo vem pela lista de portas dele.
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
        # o vao encosta nas quatro chapas: uma espessura por lado
        for folga in grupo[addon.portas.CHAVE_FOLGAS_PORTA]:
            self.assertAlmostEqual(folga, 1.0, places=4)

    def corrente(self):
        """Estado da corrente porta/modulo (o operador saiu da gaveta,
        segue no F3)."""
        return 'LINKED' if addon.importacao._corrente_porta_ligada(bpy.context) else 'UNLINKED'

    def test_corrente_decide_porta_no_modulo_ou_no_mundo(self):
        s = bpy.context.scene
        self.addCleanup(s.property_unset, 'porta_associar')
        # sem porta ativa: a corrente e' a escolha para a proxima porta
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
        # porta ATIVA: a corrente mostra e troca o estado dela
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
        self.assertTrue(s.porta_associar)          # a da cena nao mexeu
        # solta, nao acompanha o modulo
        largura = addon.portas._folhas_portas(grupo)[0].chapa_largura_mm
        conj.conj_largura_mm += 200.0
        bpy.context.view_layer.update()
        self.assertEqual(addon.portas._folhas_portas(grupo)[0].chapa_largura_mm, largura)
        # religar volta para o mesmo modulo, mesmo sem ele selecionado
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
        # Folga guardada em espessuras: chapa mais grossa aperta o vao.
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
        # Cenario 1: objeto generico, nenhum vinculo a manter.
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
        # Porta que cobre METADE de uma chapa (pedido do usuario): ja' na
        # diagonal o snap NATIVO pega o meio das arestas (EDGE_MIDPOINT);
        # o wizard nao troca os elementos padrao do protocolo comum.
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
        # esquerda: no MEIO da lateral, menos o respiro (2 portas na mesma
        # chapa nao se encostam); o resto cobre a chapa inteira (Reta)
        meia = E / 2 - addon.portas.RESPIRO_PORTA_MM
        r = addon.portas.RESPIRO_PORTA_MM          # a Reta tambem nao fica rente
        self.assertAlmostEqual(lo[0] * 1000, -L / 2 + E - meia, places=3)
        self.assertAlmostEqual(hi[0] * 1000, L / 2 - r, places=3)
        self.assertAlmostEqual(lo[2] * 1000, r, places=3)
        self.assertAlmostEqual(hi[2] * 1000, A - r, places=3)
        # redimensionar o modulo mantem a borda no meio da lateral
        conj.conj_largura_mm = L + 100
        bpy.context.view_layer.update()
        lo, hi = self.limites_folhas(conj, grupo)
        self.assertAlmostEqual(lo[0] * 1000, -(L + 100) / 2 + E - meia, places=3)
        self.assertAlmostEqual(hi[0] * 1000, (L + 100) / 2 - r, places=3)
        # meia cobertura e' fixa: a Curva ja' cobre meia, nada muda nela
        p = dict(grupo['porta_parametros'], dobradica='CURVA')
        self.assertEqual(addon.portas._inicios_porta(p), [-meia] * 4)
        # a meia e' do VAO: fica mesmo se a dobradica mudar (o resto,
        # embutido, fica o respiro para dentro do vao)
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

    # Regressao (era BUG, corrigido na 303): o Alt-arraste do canto lia toda
    # malha visivel no clique e projetava cada vertice a cada movimento --
    # segundos de travamento. Agora o cursor anda pelo snap nativo.
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
        self.assertTrue(folha.hide_select)      # a porta nao e' ima de si
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
        # esq/cima/baixo: chapa inteira; dir: metade da lateral
        grupo = self.porta_por_quatro_cliques(
            conj, (-L / 2, y, A), (-L / 2 + E, y, A - E), (L / 2 - E, y, E),
            (L / 2 - E / 2, y, 0), dobradica='RETA', folhas=1)
        p = grupo['porta_parametros']
        self.assertEqual([p[k] for k in addon.portas.COBERTURAS_LADOS],
                         [1.0, 0.5, 1.0, 1.0])
        lo, hi = self.limites_folhas(conj, grupo)
        meia = E / 2 - addon.portas.RESPIRO_PORTA_MM     # respiro na meia
        r = addon.portas.RESPIRO_PORTA_MM                # e nas retas
        self.assertAlmostEqual(lo[0] * 1000, -L / 2 + r, places=3)
        self.assertAlmostEqual(hi[0] * 1000, L / 2 - E + meia, places=3)
        self.assertAlmostEqual(lo[2] * 1000, r, places=3)
        self.assertAlmostEqual(hi[2] * 1000, A - r, places=3)
        # acompanha o modulo
        conj.conj_largura_mm = L + 100
        bpy.context.view_layer.update()
        lo, hi = self.limites_folhas(conj, grupo)
        self.assertAlmostEqual(hi[0] * 1000, (L + 100) / 2 - E + meia, places=3)

    def test_quatro_cliques_com_porta_e_vao_no_mesmo_ponto(self):
        conj = self.nicho()
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        y = -P / 2
        # 1 e 2 no MESMO ponto (quina de fora): vale a margem do par 3-4
        grupo = self.porta_por_quatro_cliques(
            conj, (-L / 2, y, A), (-L / 2, y, A), (L / 2 - E, y, E),
            (L / 2, y, 0), dobradica='RETA', folhas=1)
        p = grupo['porta_parametros']
        self.assertEqual([p[k] for k in addon.portas.COBERTURAS_LADOS], [1.0] * 4)
        self.assertAlmostEqual(grupo['porta_vao_largura_mm'], L - 2 * E,
                               places=3)
        # os 4 no canto do vao: porta embutida, sem cobrir nada
        bpy.data.objects.remove(grupo, do_unlink=True)
        grupo = self.porta_por_quatro_cliques(
            conj, (-L / 2 + E, y, A - E), (-L / 2 + E, y, A - E),
            (L / 2 - E, y, E), (L / 2 - E, y, E),
            dobradica='SUPER_CURVA', folhas=1)
        p = grupo['porta_parametros']
        self.assertEqual([p[k] for k in addon.portas.COBERTURAS_LADOS], [0.0] * 4)

    def test_cantos_da_porta_sao_os_cliques_e_refazem_a_porta(self):
        # Pedido do usuario: porta selecionada mostra os pontos do wizard;
        # com Alt so' os 2 cliques (v309: eram 4) se arrastam e refazem a
        # porta como a criacao, pela chapa de cada clique.
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
        # canto de baixo na quina de fora: a direita passa a cobrir a chapa toda
        fora = conj.matrix_world @ (Vector((L / 2, y, 0)) / 1000.0)
        self.assertEqual(V._mover_cantos_porta(bpy.context, grupo, [mundo[0], fora]),
                         {'FINISHED'})
        p = grupo['porta_parametros']
        self.assertEqual([p[k] for k in addon.portas.COBERTURAS_LADOS], [1.0] * 4)
        self.assertEqual(grupo[addon.portas.CHAVE_MODULO_PORTA], conj.name)
        # a porta continua selecionada para seguir ajustando
        self.assertIn(grupo, addon.portas_viewport._portas_com_cantos(bpy.context))
        # canto de cima no meio da lateral das dobradicas: a chapa do clique
        # diz que e' a metade dela, e a dobradica vira Curva
        meio = conj.matrix_world @ (Vector((-L / 2 + E / 2, y, A)) / 1000.0)
        V._mover_cantos_porta(bpy.context, grupo, [meio, fora], [lateral, None])
        self.assertEqual(grupo['porta_parametros']['cobertura_esq_e'], 0.5)
        self.assertEqual(grupo['porta_parametros']['dobradica'], 'CURVA')
        antes = [V._cantos_da_porta(grupo)[i] for i in V.CANTOS_DO_GESTO]
        self.assertLess((antes[0] - meio).length, 1e-6)
        # padrao: refaz sem perguntar
        addon.perguntas._pergunta_atual[0] = None
        quina = conj.matrix_world @ (Vector((-L / 2, y, A)) / 1000.0)
        V._aplicar_cantos_porta(bpy.context, grupo, [quina, fora], [lateral, None],
                                antes, [lateral, None])
        self.assertIsNone(addon.perguntas._pergunta_atual[0])
        self.assertEqual(grupo['porta_parametros']['cobertura_esq_e'], 1.0)
        # o "Nao" da pergunta volta os 2 cliques, com a chapa de cada um
        self.assertEqual(bpy.ops.object.cabinet_cantos_porta(
            grupo=grupo.name, pontos=tuple(v for p in antes for v in p),
            objeto_a=lateral.name), {'FINISHED'})
        self.assertEqual(grupo['porta_parametros']['cobertura_esq_e'], 0.5)
        # "Sim" nao mexe em nada
        antes = addon.portas_viewport._cantos_da_porta(grupo)
        self.assertEqual(bpy.ops.object.cabinet_cantos_porta(
            grupo=grupo.name, manter=True), {'FINISHED'})
        for a, b in zip(antes, addon.portas_viewport._cantos_da_porta(grupo)):
            self.assertLess((a - b).length, 1e-9)
        self.assertFalse(addon.portas._lados_fora_do_padrao(
            addon.portas_viewport._coberturas_da_porta(grupo)))

    def test_porta_selecionada_desenha_folhas_vao_e_dobradicas(self):
        # Print do usuario: com a porta selecionada, contorno das folhas e
        # linhas internas do vao (amarelo). O VOLUME das dobradicas onde o
        # wizard as pos so' aparece com elas selecionadas.
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
        # o vao: as faces internas das chapas
        xs = sorted(round(local(v).x, 3) for v in desenho['vao'])
        self.assertAlmostEqual(xs[0], -L / 2 + E, places=3)
        self.assertAlmostEqual(xs[-1], L / 2 - E, places=3)
        # 2 dobradicas (padrao pela altura) x (corpo + caneco), na esquerda;
        # o corpo encosta na face interna da lateral e entra no movel
        self.assertEqual(len(addon.ferragens._caixas_ferragens(grupo, {'DOBRADICA'})), 4)
        corpo = addon.ferragens._caixas_ferragens(grupo, {'DOBRADICA'})[0]
        x = sorted(local(v).x for v in corpo)
        self.assertAlmostEqual(x[0], -L / 2 + E, places=3)
        self.assertAlmostEqual(x[-1], -L / 2 + E + addon.portas.DOBRADICA_AVANCO_MM, places=3)
        # atras da folha: da frente (y = -P/2) para DENTRO do movel
        ys = sorted(local(v).y for v in corpo)
        self.assertAlmostEqual(ys[0], y, places=3)
        self.assertAlmostEqual(ys[-1], y + addon.portas.DOBRADICA_FUNDO_MM, places=3)
        # 2 folhas de giro: dobradicas nas duas laterais
        bpy.data.objects.remove(grupo, do_unlink=True)
        grupo = self.porta_no_nicho(conj)
        desenho = addon.portas_viewport._desenho_da_porta(grupo)
        self.assertEqual(len(desenho['folhas']), 2)
        self.assertEqual(len(addon.ferragens._caixas_ferragens(grupo, {'DOBRADICA'})), 8)
        # correr nao tem dobradica
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'abertura', 'CORRER'), '')
        self.assertEqual(addon.ferragens._caixas_ferragens(grupo, {'DOBRADICA'}), [])

    # ---- Fase 3: ferragens de verdade, pivo e abertura
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
        # Corpo da dobradica no MODULO, caneco furado nas costas da FOLHA;
        # malhas que o clique nao pega mas que andam com a porta.
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
            # selecionavel e editavel como qualquer objeto (pedido do usuario)
            self.assertFalse(o.hide_select)
            self.assertNotIn(addon.chapas.MARCA_CHAPA, o)
            self.assertEqual(o.parent, folha if o in canecos else grupo)
        local = lambda v: (conj.matrix_world.inverted() @ v) * 1000.0
        caneco = [local(canecos[0].matrix_world @ Vector(c))
                  for c in canecos[0].bound_box]
        # 12 mm para dentro da folha, a partir das costas (frente = -Y), e
        # a aba saindo das costas: senao o copo sumia dentro da porta
        self.assertAlmostEqual(max(v.y for v in caneco),
                               y + addon.portas.CANECO_ABA_MM, places=3)
        self.assertAlmostEqual(min(v.y for v in caneco),
                               y - addon.portas.CANECO_FUNDO_MM, places=3)
        # furo a 5 mm da borda da folha (a folha cobre a lateral menos o
        # respiro)
        self.assertAlmostEqual(min(v.x for v in caneco), -L / 2
                               + addon.portas.RESPIRO_PORTA_MM + addon.portas.CANECO_BORDA_MM,
                               places=3)
        # o desenho da porta selecionada e' o volume dessas malhas
        desenho = addon.portas_viewport._desenho_da_porta(grupo)
        corpo = sorted(local(v).x for v in addon.ferragens._caixas_ferragens(grupo, {'DOBRADICA'})[0])
        self.assertAlmostEqual(corpo[0], -L / 2 + E, places=3)
        self.assertAlmostEqual(corpo[-1], -L / 2 + E + addon.portas.DOBRADICA_AVANCO_MM,
                               places=3)
        # o Blender nao seleciona hide_select: a porta vai sem elas
        addon.hud._selecionar_porta_hud(bpy.context, folha, 'PORTA')
        self.assertFalse(any(o.select_get() for o in corpos + canecos))
        self.assertFalse(any(addon.ferragens.CHAVE_FERRAGEM in item[0]
                             for item in addon.hud._itens_da_selecao(bpy.context)))
        # 2 folhas: dobradicas dos dois lados; voltar a 1 nao deixa sobra
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
        # Por isso o handler confere (num timer) quando a contagem de
        # objetos muda: porta sem ferragem ganha; ferragem sem porta sai.
        self.sem_rig()
        conj = self.nicho()
        grupo = self.porta_de_giro(conj)
        for o in addon.ferragens._ferragens_portas(grupo):
            addon.ferragens._remover_ferragem(o)        # porta duplicada / antiga
        addon.ferragens._conferir_ferragens()
        self.assertEqual(len(addon.ferragens._ferragens_portas(grupo)), 4)
        for o in [grupo, *addon.portas._folhas_portas(grupo)]:
            bpy.data.objects.remove(o, do_unlink=True)    # apagou a porta
        self.assertTrue(any(addon.ferragens.CHAVE_FERRAGEM in o for o in bpy.data.objects))
        addon.ferragens._conferir_ferragens()
        self.assertFalse(any(addon.ferragens.CHAVE_FERRAGEM in o for o in bpy.data.objects))

    def _apagar_malhas_modulo(self, conj):
        bpy.ops.object.select_all(action='DESELECT')
        for o in conj.children_recursive:
            if o.type == 'MESH' and not o.hide_get():
                o.select_set(True)
        bpy.ops.object.delete()

    # Regressao (era BUG, corrigido na 279): Empty e rig ocultos
    # sobreviviam ao Delete e impediam a limpeza da pasta do modulo.
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

    # Regressao (era BUG, corrigido na 280): a embalagem do asset
    # tinha a tag nativa, mas nao a marca da Collection do modulo.
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
        # Renomear a pasta nao pode inutilizar a identificacao do asset.
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
        # No background o event loop nao chama o tique que libera undo.
        addon.eventos._fim_do_desfazer()
        addon.ferragens._conferir_ferragens()
        self.assertEqual(set(bpy.data.objects.keys()), nomes)
        bpy.ops.ed.redo()
        addon.eventos._fim_do_desfazer()
        addon.ferragens._conferir_ferragens()
        self.assertNotIn(nome, bpy.data.objects)
        self.assertNotIn(nome, bpy.data.collections)

    def test_placa_da_reta_fica_na_face_interna(self):
        # print do usuario: a placa base da Reta entrava ~3 mm na lateral
        # (o modelo cobre 12,75 mm, a Reta de 18 cobre 16). Como o
        # parafuso de cobertura de verdade, placa e suporte andam ate' a
        # face; o copo continua na folha (nada muda na abertura)
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
            # mm para DENTRO da chapa (face interna: x = 0 ou x = L)
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
        # a previa do wizard (arame) tambem
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
        # Pedido do usuario: a Reta IMPORTA o modelo e o rig dele (asset
        # de extrair_dobradica.py), sem recriar malha nem rig; a folha faz
        # o movimento medido no rig e o copo fura a folha (Boolean).
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

        # cada copia traz o rig inteiro, e o driver e o IK sao DELA
        for arm in por_peca('armacao'):
            alvo = arm.animation_data.drivers[0].driver.variables[0].targets[0].id
            self.assertIs(raiz_de(alvo), raiz_de(arm))
        for ik in por_peca('armacao_ik'):
            alvos = [c.target for pb in ik.pose.bones for c in pb.constraints
                     if c.type == 'IK']
            self.assertEqual(len(alvos), 1)
            self.assertIs(raiz_de(alvos[0]), raiz_de(ik))
        self.assertEqual(len(por_peca('armacao_ik')), n)
        # nada restrito: toda peca se seleciona e edita no Blender
        self.assertFalse(any(o.hide_select for o in pecas))
        # mas nao acende junto com a porta nem com o modulo
        addon.hud._selecionar_chapa_hud(bpy.context, folha)
        self.assertFalse(any(o.select_get() for o in pecas))
        # duplo clique = UMA peca, selecao nativa (Tab entra na malha dela)
        cabeca = por_peca('cabeca')[0]
        addon.ferragens._selecionar_peca(bpy.context, cabeca)
        self.assertEqual(bpy.context.selected_objects, [cabeca])
        self.assertIs(bpy.context.view_layer.objects.active, cabeca)
        self.assertEqual(bpy.ops.object.mode_set(mode='EDIT'), {'FINISHED'})
        bpy.ops.object.mode_set(mode='OBJECT')
        # a folha guarda a folga do modelo ate' o modulo (1,86 mm): sem
        # ela o canto da folha aberta entrava no modulo (print do usuario)
        dados = addon.ferragens._dados_dobradica_reta()
        costas = addon.ferragens._dados_da_folha(folha)[3][2] - folha.chapa_espessura_mm / 2
        self.assertAlmostEqual(costas, dados['folga_modulo_mm'], places=3)
        # e em NENHUM ponto do giro a folha passa da frente do modulo
        P = addon.portas._caixa_do_modulo(conj)[2]
        local = lambda v: (conj.matrix_world.inverted() @ v) * 1000.0
        for passo in range(41):
            addon.ferragens._definir_abertura(bpy.context, folha, passo / 40.0)
            fundo = max(local(folha.matrix_world @ Vector(c)).y
                        for c in folha.bound_box)
            self.assertLessEqual(fundo, -P / 2.0 + 1e-3, passo)
        addon.ferragens._definir_abertura(bpy.context, folha, 0.0)
        # a malha e' dividida entre as copias: o arquivo nao incha
        cabecas = por_peca('cabeca')
        self.assertEqual(len({o.data.name for o in cabecas}), 1)
        # o copo fura a folha: um Boolean por dobradica, com o cortador dela
        furos = [m for m in folha.modifiers
                 if m.name.startswith(addon.ferragens.PREFIXO_FURO)]
        self.assertEqual(len(furos), n)
        self.assertTrue(all(m.operation == 'DIFFERENCE'
                            and m.object.get('cabinet_peca') == 'furo'
                            for m in furos))
        # a cabeca anda COLADA na folha (tabela da folha = rig de verdade)
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
        # copia de asset antigo (nomes em ingles, furo velho) e' trocada
        # pela atual quando a porta se refaz
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
        # Curva: o rig sai inteiro, com o furo; voltam as caixas
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
        # o eixo: a quina das COSTAS do lado da dobradica fica parada (como
        # a dobradica de caneco: aberta, sem vao entre a folha e o modulo)
        eixo = Vector((-l, 0.0, -e)) / 2000.0
        self.assertLess((folha.matrix_world @ eixo - fechada @ eixo).length, 1e-6)
        frente = Vector((-l, 0.0, e)) / 2000.0
        self.assertGreater((folha.matrix_world @ frente
                            - fechada @ frente).length, 0.01)
        # o outro lado vem para fora do movel (frente = -Y)
        ponta = Vector((l, 0.0, e)) / 2000.0
        self.assertLess(local(folha.matrix_world @ ponta).y,
                        local(fechada @ ponta).y - 100)
        x_folha = folha.matrix_world.to_3x3() @ Vector((1, 0, 0))
        x_vao = grupo.matrix_world.to_3x3() @ Vector((1, 0, 0))
        self.assertAlmostEqual(math.degrees(x_folha.angle(x_vao)), 110.0, places=3)
        self.assertEqual(addon.portas_viewport._texto_abertura(folha), '110' + addon.portas_viewport.SIMBOLO_GRAU)
        # o caneco gira junto; o corpo fica no modulo
        self.assertGreater((caneco.matrix_world.translation - caneco_antes).length,
                           0.01)
        self.assertLess((corpo.matrix_world.translation - corpo_antes).length, 1e-9)
        # o contorno da porta selecionada acompanha a folha aberta
        contorno = addon.portas_viewport._desenho_da_porta(grupo)['folhas'][0]
        self.assertLess(min(local(v).y for v in contorno),
                        min(local(fechada @ Vector(c)).y
                            for c in folha.bound_box) - 100)
        # a abertura sobrevive a redimensionar o modulo
        addon.ferragens._definir_abertura(bpy.context, folha, 0.5)
        conj.conj_largura_mm = L + 100
        bpy.context.view_layer.update()
        folha = addon.portas._folhas_portas(grupo)[0]
        self.assertAlmostEqual(folha[addon.ferragens.CHAVE_ABERTURA], 0.5)
        x_folha = folha.matrix_world.to_3x3() @ Vector((1, 0, 0))
        self.assertAlmostEqual(math.degrees(x_folha.angle(x_vao)), 55.0, places=3)
        self.assertAlmostEqual(folha.chapa_largura_mm,
                               L + 100 - 2 * addon.portas.RESPIRO_PORTA_MM, places=3)
        # fechar volta exatamente ao lugar
        addon.ferragens._definir_abertura(bpy.context, folha, 0.0)
        self.assertLess((folha.matrix_world.translation
                         - addon.ferragens._matriz_fechada(folha).translation).length, 1e-9)

    def test_basculante_tem_pistoes_com_mira(self):
        # Pistao = rigging: cada metade mira a outra ponta (Damped Track),
        # entao estica junto com a abertura; a haste fica embaixo.
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
            # haste para BAIXO: a fixacao da lateral e' a ponta de baixo
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
                # nem sobra fora da ponta (fechado) nem abre buraco (aberto)
                if fracao == 0.0:
                    self.assertLessEqual(comprimento(corpo), distancia + 1e-3)
                else:
                    self.assertGreaterEqual(comprimento(corpo) + comprimento(haste),
                                            distancia - 1e-3)
                # automatico: fechado = metade do pistao, aberto = ele todo
                self.assertAlmostEqual(distancia, 2 * comprimento(corpo)
                                       if fracao else comprimento(corpo),
                                       places=2)
        # Reta: abre o que o rig do usuario abre (91,7 graus)
        self.assertEqual(addon.portas_viewport._texto_abertura(folha), '%d%s' % (
            round(addon.ferragens._giro_maximo_rig()), addon.portas_viewport.SIMBOLO_GRAU))
        # aberta como a de verdade (print do usuario): a borda fica junto
        # da frente do modulo -- nada do vao da espessura entre a porta e
        # o modulo -- e, como a dobradica de caneco real a 90 graus, a
        # folha avanca um pouco sobre o vao (nao fica no nivel do topo)
        cantos = lambda m: [local(m @ Vector(c)) for c in folha.bound_box]
        fechada = cantos(addon.ferragens._matriz_fechada(folha))
        aberta = cantos(folha.matrix_world)
        vao = max(v.y for v in fechada) - max(v.y for v in aberta)
        altura = min(v.z for v in aberta) - max(v.z for v in fechada)
        self.assertLess(abs(vao), 3.0, (vao, altura))
        self.assertTrue(-30.0 < altura < 0.0, (vao, altura))
        # volume de pistao de verdade: corpo mais grosso que a haste, e
        # um suporte na lateral (fica) e outro na folha (gira com ela)
        raio = lambda o: max(v.co.x for v in o.data.vertices) * 1000.0
        self.assertGreater(raio(corpos[0]), raio(hastes[0]))
        suportes = self.ferragens(grupo, 'PISTAO_SUPORTE')
        self.assertEqual(sorted(s.parent.name for s in suportes),
                         sorted([grupo.name] * 2 + [folha.name] * 2))

    def test_previa_das_dobradicas_e_o_arame_da_peca(self):
        # Pedido do usuario: a previa da dobradica e' o wireframe da peca de
        # verdade (antes, uma caixa de volume). O wizard planeja pelas
        # MESMAS ferragens que a porta monta: o arame cai em cima do rig.
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
        # selecionadas: o arame vem das copias, na pose de agora
        pecas_sel, pontos_sel = addon.arame._arame_ferragens(grupo, {'DOBRADICA'})
        self.assertEqual(len(pecas_sel), len(pecas))
        self.assertEqual(pontos_sel, [])
        # so' o contorno: leve (a malha avaliada tem ~190 mil arestas)
        segmentos = sum(len(v) for v in rig['malhas'].values()) // 2
        self.assertTrue(1000 < segmentos < 6000, segmentos)

    def test_previa_de_caixas_e_pistoes_e_arame(self):
        # Curva/embutida (caixas) e pistoes: o arame da forma de cada um
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
        # Pedido do usuario: com as ferragens selecionadas a aba Portas
        # mostra SO' elas -- quantidade e afastamento das dobradicas,
        # quantidade e distancia do topo dos pistoes --, editaveis; nada
        # das medidas da porta. Editar vale para a porta e a selecao fica.
        self.addCleanup(addon.ferragens._ferragens_selecionadas.__setitem__, 0, None)
        cena = bpy.context.scene
        self.addCleanup(setattr, cena, 'cabinet_aba', 'MODULOS')
        cena.cabinet_aba = 'MODULOS'
        conj = self.nicho()
        grupo = self.porta_de_giro(conj, abertura='BASCULANTE',
                                   dobradica_lado='CIMA', pistoes_qtd=2)
        caneco = self.ferragens(grupo, 'CANECO')[0]
        addon.ferragens._selecionar_ferragem(bpy.context, caneco)
        self.assertEqual(cena.cabinet_aba, 'PORTAS')      # foi a' aba dela

        def painel():
            _c, conteudo, _r = addon.gaveta._partes_gaveta(
                addon.gaveta._widgets_gaveta(bpy.context, 320, 1400))
            return [v[5] for v in addon.gaveta._paineis_gaveta(conteudo)[0] if v[5]]

        acoes = painel()
        campos = {a[2]: a for a in acoes if a[0] == 'medida'}
        self.assertEqual(set(campos), {'dobradicas_margem_mm'})
        self.assertEqual(campos['dobradicas_margem_mm'][1], 'ferragens')
        # o tipo da dobradica e' automatico: retratos so' para ver (sem
        # clique), o detectado aceso
        retratos = [a for a in acoes if a[0] == 'escolha' and a[1] == 'dobradica']
        self.assertEqual([a[2] for a in retratos if a[3]],
                         [grupo['porta_parametros']['dobradica']])
        self.assertFalse(any(a[4] for a in retratos))
        # quantidade = CONTADOR (mockup do usuario), sem "aceitar": a
        # selecao edita na hora
        self.assertFalse([a for a in acoes if a[0] == 'escolha'
                          and a[1] == addon.portas.CONFIRMAR_ETAPA])
        (qtd,) = [a for a in acoes if a[0] == 'contador']
        n = len(addon.ferragens._dobradicas_da_porta(
            *addon.ferragens._porta_calculada(grupo))[0][1])
        self.assertEqual(qtd, ('contador', 'dobradicas_qtd', n,
                               *addon.portas.LIMITES_DOBRADICAS,
                               addon.gaveta.ALVO_FERRAGENS))
        # editar: a porta muda e as ferragens continuam selecionadas
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
        # Shift no pistao: os dois tipos, cada um com a sua secao
        addon.ferragens._selecionar_ferragem(bpy.context,
                                   self.ferragens(grupo, 'PISTAO_SUPORTE')[0],
                                   somar=True)
        campos = {a[2] for a in painel() if a[0] == 'medida'}
        self.assertEqual(campos, {'dobradicas_margem_mm', 'pistoes_offset_mm'})
        # o pistao trava no curso: descer demais fica no limite (que e' o
        # ponto automatico: grava 0); subir grava o que foi digitado
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
        # Pedido do usuario: clique numa dobradica = TODAS as dobradicas
        # do modulo; num pistao = todos os pistoes; Shift soma o outro
        # tipo. Nada mais fica selecionado (porta/modulo sem contorno).
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
        self.assertEqual(bpy.context.selected_objects, [])
        (achado, tipos), = addon.ferragens._ferragens_em_edicao(bpy.context)
        self.assertEqual((achado, tipos), (grupo, {'DOBRADICA'}))
        # na Reta, o volume das pecas grandes do rig (base, suporte, copo)
        n = len([o for o in addon.ferragens._ferragens_portas(grupo)
                 if o.get('cabinet_peca') in addon.ferragens.PECAS_REALCE_RIG])
        self.assertEqual(len(addon.ferragens._caixas_ferragens(grupo, tipos)), n)
        # Shift no pistao: os dois tipos; de novo no pistao: so' as dobradicas
        addon.ferragens._selecionar_ferragem(bpy.context, pistao, somar=True)
        self.assertEqual(addon.ferragens._ferragens_em_edicao(bpy.context)[0][1],
                         {'DOBRADICA', 'PISTAO'})
        caixas = addon.ferragens._caixas_ferragens(grupo, {'DOBRADICA', 'PISTAO'})
        self.assertEqual(len(caixas), n + 4 * 2)    # corpo, haste e 2 suportes
        addon.ferragens._selecionar_ferragem(bpy.context, pistao, somar=True)
        self.assertEqual(addon.ferragens._ferragens_em_edicao(bpy.context)[0][1],
                         {'DOBRADICA'})
        # sem Shift: troca
        addon.ferragens._selecionar_ferragem(bpy.context, pistao)
        self.assertEqual(addon.ferragens._ferragens_em_edicao(bpy.context)[0][1],
                         {'PISTAO'})
        # o volume do pistao e' o da malha de verdade: corpo entre as pontas
        corpo = self.ferragens(grupo, 'PISTAO_CORPO')[0]
        caixa = addon.ferragens._caixas_ferragens(grupo, {'PISTAO'})[0]
        self.assertLess((sum(caixa, Vector()) / 8 - corpo.matrix_world
                         @ Vector((0, corpo.dimensions.y / 2, 0))).length, 1e-4)
        # selecionar qualquer outra coisa encerra o modo
        addon.hud._selecionar_porta_hud(bpy.context, folha, 'PORTA')
        self.assertEqual(addon.ferragens._ferragens_em_edicao(bpy.context), [])
        self.assertIsNone(addon.ferragens._ferragens_selecionadas[0])

    def test_controladores_das_ferragens(self):
        # Alt: um controlador por tipo. O da dobradica corre na borda
        # (margem, espelhada); o do pistao, na lateral (so' ate' o curso).
        conj = self.nicho()
        grupo = self.porta_de_giro(conj, abertura='BASCULANTE',
                                   dobradica_lado='CIMA', pistoes_qtd=2)
        controles = addon.ferragens._controles_ferragens(grupo, {'DOBRADICA', 'PISTAO'})
        self.assertEqual([c[0] for c in controles], ['DOBRADICA', 'PISTAO'])
        (_t, ponto_d, a_d, b_d), (_t2, ponto_p, a_p, b_p) = controles
        # na Reta, na raiz do rig da 1a dobradica
        raiz = next(o for o in self.ferragens(grupo, 'DOBRADICA_RIG')
                    if o[addon.ferragens.CHAVE_ID_FERRAGEM].endswith('_0'))
        self.assertLess((ponto_d - raiz.matrix_world.translation).length, 1e-6)
        haste = self.ferragens(grupo, 'PISTAO_HASTE')[-1]          # a da ESQUERDA
        self.assertLess((ponto_p - haste.matrix_world.translation).length, 1e-6)
        # margem espelhada: 10% e 90% do trilho dao a mesma
        comprimento = (b_d - a_d).length * 1000.0
        nome, perto = addon.ferragens._valor_do_controle(grupo, 'DOBRADICA', 0.1)
        self.assertEqual(nome, 'dobradicas_margem_mm')
        self.assertAlmostEqual(perto, 0.1 * comprimento, places=3)
        self.assertAlmostEqual(
            addon.ferragens._valor_do_controle(grupo, 'DOBRADICA', 0.9)[1], perto, places=3)
        # pistao: la' embaixo trava no curso (= automatico, grava 0)
        self.assertEqual(addon.ferragens._valor_do_controle(grupo, 'PISTAO', 1.0),
                         ('pistoes_offset_mm', 0.0))
        nome, offset = addon.ferragens._valor_do_controle(grupo, 'PISTAO', 0.15)
        self.assertGreater(offset, 0.0)
        antes = haste.matrix_world.translation.copy()
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, nome, offset), '')
        bpy.context.view_layer.update()
        haste = self.ferragens(grupo, 'PISTAO_HASTE')[-1]          # a da ESQUERDA
        cima = grupo.matrix_world.to_3x3() @ Vector((0, 1, 0))
        self.assertGreater((haste.matrix_world.translation - antes).dot(cima), 0.01)
        ponto_novo = addon.ferragens._controles_ferragens(grupo, {'PISTAO'})[0][1]
        self.assertLess((ponto_novo - haste.matrix_world.translation).length, 1e-6)
        # e a margem nova move a 1a dobradica ao longo da borda
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'dobradicas_margem_mm', 150.0), '')
        ponto_d = addon.ferragens._controles_ferragens(grupo, {'DOBRADICA'})[0][1]
        a_d = addon.ferragens._controles_ferragens(grupo, {'DOBRADICA'})[0][2]
        self.assertAlmostEqual((ponto_d - a_d).length * 1000.0, 150.0, places=3)
        # O arraste (cabinet_arrastar_ferragem) refaz a porta e as
        # ferragens continuam selecionadas; Esc devolve o valor de antes.
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
        # giro: sem pistao, so' o controlador da dobradica
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
        # cada uma no seu trilho: corre o vao INTEIRO, ate' a outra ponta
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
        # pedido do usuario: a unica nasce com METADE do vao, a' esquerda,
        # e o slider a leva ate' a direita; a largura se edita na gaveta
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
        # o slider vai do centro fechado ao aberto: a bolinha fica sob ela
        a, b = addon.portas_viewport._slider_no_mundo(folha)
        self.assertAlmostEqual(((b - a) * 1000.0).length, util / 2, places=2)
        meio = (folha.matrix_world.translation - b) * 1000.0
        self.assertAlmostEqual(meio.dot(grupo.matrix_world.to_3x3().col[0]
                                        .normalized()), 0.0, places=2)
        # a largura e' o campo L da gaveta, editavel (digitar ou arrastar)
        grupo.select_set(True)
        bpy.context.view_layer.objects.active = grupo
        campos = addon.gaveta._medidas_da_porta(grupo, grupo)
        self.assertEqual(campos[0][::2], ('Largura', 'ui_porta_largura_folha'))
        self.assertIsNone(addon.gaveta_eventos.aplicar_medida(
            bpy.context, 'porta', grupo.name, 'ui_porta_largura_folha', 0.4))
        (folha,) = addon.portas._folhas_portas(grupo)
        self.assertAlmostEqual(folha.chapa_largura_mm, 400.0, places=3)
        self.assertAlmostEqual(bordas()[1], L - r, places=2)    # segue aberta
        # outra tipologia: a largura volta a' do padrao
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'folhas', 2), '')
        self.assertNotIn(addon.portas.CHAVE_LARGURA_CORRER,
                         grupo['porta_parametros'])

    def test_correr_com_moldura_cobre_o_modulo_e_traz_a_moldura(self):
        # Pedido do usuario: o correr que cobre a chapa (cliques de fora para
        # dentro) avanca na frente do modulo dentro de uma MOLDURA --
        # revestimento nas laterais, base + testeira em cima, base + rodape
        # embaixo, tudo de 15 -- e as folhas cobrem a frente INTEIRA dele.
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
        for _l, a, _e, c in folhas:   # do trilho (sobre a base) ao topo do modulo
            self.assertAlmostEqual(c[1] - a / 2, -18.0 + trilho_baixo, places=5)
            self.assertAlmostEqual(c[1] + a / 2, 818.0)
        # uma folha em cada canal do trilho do usuario, a 1a na frente
        costas, frente = f.CANAIS_TRILHO_MOLDURA_MM
        self.assertAlmostEqual(folhas[0][3][2], pt.TRILHO_MOLDURA_COSTAS_MM + frente)
        self.assertAlmostEqual(folhas[1][3][2], pt.TRILHO_MOLDURA_COSTAS_MM + costas)
        # trilhos = os perfis do usuario, entre os revestimentos
        itens = f._ferragens_da_porta(p, 600, 800, folhas)
        trilhos = {i['id']: i for i in itens if i['tipo'] == 'TRILHO'}
        self.assertEqual({t['forma'] for t in trilhos.values()}, {'PERFIL'})
        for item in trilhos.values():
            self.assertEqual(tuple(item['x']), (-18.0, 618.0))
        lo_c, hi_c = f._limites_perfil(trilhos['TRILHO_CIMA'])
        lo_b, hi_b = f._limites_perfil(trilhos['TRILHO_BAIXO'])
        self.assertAlmostEqual(lo_c.y, 818.0 - pt.INSERCAO_CANAL_MM, places=3)  # no canal
        self.assertAlmostEqual(hi_b.y, -18.0 + trilho_baixo, places=3)  # o pe' dela
        malha = bpy.data.meshes.new('perfil')
        f._malha_da_ferragem(malha, trilhos['TRILHO_CIMA'])
        self.assertEqual(len(malha.polygons),
                         sum(len(pol) + 2 for pol in trilhos['TRILHO_CIMA']['poligonos']))
        bpy.data.meshes.remove(malha)
        _pecas, pontos = addon.arame._arame_dos_itens(list(trilhos.values()))
        self.assertTrue(pontos)                                        # previa do wizard
        # a moldura
        pecas = {k: caixa for k, _n, caixa, _e in pt._pecas_moldura(p, 600, 800, 300.0)}
        self.assertEqual(set(pecas), {'LATERAL_ESQ', 'LATERAL_DIR', 'BASE_CIMA',
                                      'TESTEIRA', 'BASE_BAIXO', 'RODAPE'})
        avanco = pt._avanco_moldura(p)
        esq, dir_ = pecas['LATERAL_ESQ'], pecas['LATERAL_DIR']
        self.assertEqual(esq[:2], (-33.0, -18.0))        # por fora da lateral
        self.assertEqual(dir_[:2], (618.0, 633.0))
        self.assertEqual(esq[4:], (-300.0, avanco))      # das costas a' frente
        testeira, rodape = pecas['TESTEIRA'], pecas['RODAPE']
        self.assertAlmostEqual(testeira[5] - testeira[4], 15.0)
        self.assertAlmostEqual(testeira[3] - testeira[2], 80.0)
        self.assertGreater(testeira[4], max(c[2] + e / 2 for _l, _a, e, c in folhas))
        self.assertAlmostEqual(rodape[3] - rodape[2], 100.0)
        self.assertAlmostEqual(pecas['BASE_CIMA'][2], hi_c.y, places=3)   # sobre o trilho
        self.assertAlmostEqual(pecas['BASE_BAIXO'][3], lo_b.y, places=3)  # sob o trilho
        self.assertAlmostEqual(esq[2], rodape[2])               # do piso
        self.assertAlmostEqual(esq[3], pecas['BASE_CIMA'][3])   # ao teto
        # a base de baixo encosta no fundo do modulo (y = -18): sem fresta
        # entre ela e o modulo (print do usuario)
        self.assertAlmostEqual(pecas['BASE_BAIXO'][3], -18.0)
        self.assertEqual(pecas['BASE_BAIXO'][4], 0.0)          # da frente dele
        # rodape e testeira zerados: as pecas somem; embutida: sem moldura
        sem = {k: caixa for k, _n, caixa, _e in pt._pecas_moldura(
            dict(p, rodape_mm=0.0, testeira_mm=0.0), 600, 800)}
        self.assertEqual(set(sem), {'LATERAL_ESQ', 'LATERAL_DIR', 'BASE_CIMA',
                                    'BASE_BAIXO'})
        # SEM BASE: tudo no chao, no nivel do fundo do modulo -- nada abaixo
        # dele; o trilho na base e a folha no trilho
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
        # Pedido do usuario: trilho LEVE = o do "Trilho exemplo" -- dois
        # canais fresados nas bases da moldura com o U de embutir dentro; o
        # PESADO e' o de aluminio. Trocar na porta pronta refaz tudo.
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
        for folha in folhas:            # os canais ficam a 17,3 mm: folha de 15
            self.assertAlmostEqual(folha.chapa_espessura_mm, 15.0)
        # uma folha no meio de cada canal, a 1a na frente
        calculadas = pt._calcular_folhas_portas(
            grupo['porta_vao_largura_mm'], grupo['porta_vao_altura_mm'], p)
        costas, frente = leve['canais_mm']
        self.assertAlmostEqual(calculadas[0][3][2], pt.TRILHO_MOLDURA_COSTAS_MM + frente)
        self.assertAlmostEqual(calculadas[1][3][2], pt.TRILHO_MOLDURA_COSTAS_MM + costas)
        # pe' da folha na aba do U, rente a' base; topo com folga ate' a de cima
        _t, base_cima, base_baixo, _fundo = pt._alturas_moldura(p, grupo['porta_vao_altura_mm'])
        for _l, a, _e, c in calculadas:
            self.assertAlmostEqual(c[1] - a / 2, base_baixo + leve['aba_mm'], places=5)
            self.assertAlmostEqual(base_cima - (c[1] + a / 2),
                                   pt.FOLGA_TOPO_TRILHO_LEVE_MM, places=5)
        # as duas bases com os canais na malha (em cima da de baixo, embaixo
        # da de cima), o U dentro deles
        bases = {o['porta_moldura_peca']: o for o in pt._moldura_da_porta(grupo)
                 if o['porta_moldura_peca'] in {'BASE_BAIXO', 'BASE_CIMA'}}
        self.assertEqual(set(bases), {'BASE_BAIXO', 'BASE_CIMA'})
        for chave, lado in (('BASE_BAIXO', 1), ('BASE_CIMA', -1)):
            base = bases[chave]
            self.assertEqual(base['chapa_canal_lado'], lado)
            self.assertEqual(len(base['chapa_canais']), 2)
            self.assertEqual(len(base.data.vertices), 2 * (4 + 4 * 2))
            zs = sorted({round(v.co.z * 1000, 3) for v in base.data.vertices})
            self.assertEqual(len(zs), 3)        # face, fundo do canal e a outra face
        trilhos = {i['id']: i for i in f._ferragens_da_porta(
            p, grupo['porta_vao_largura_mm'], grupo['porta_vao_altura_mm'], calculadas)
            if i['tipo'] == 'TRILHO'}
        lo, hi = f._limites_perfil(trilhos['TRILHO_BAIXO'])
        self.assertAlmostEqual(hi.y, base_baixo + leve['aba_mm'], places=3)
        self.assertAlmostEqual(lo.y, base_baixo + min(v for pol in leve['poligonos']
                                                      for _u, v in pol), places=3)
        self.assertLess(lo.y, base_baixo)                   # o U dentro do canal
        self.assertTrue(trilhos['TRILHO_BAIXO']['aberto'])
        malha = bpy.data.meshes.new('u')
        f._malha_da_ferragem(malha, trilhos['TRILHO_BAIXO'])
        self.assertEqual(len(malha.polygons),
                         sum(len(pol) - 1 for pol in leve['poligonos']))   # sem tampas
        bpy.data.meshes.remove(malha)
        # a moldura do leve e' mais rasa (o trilho tem 27 mm, o pesado 64)
        self.assertLess(pt._avanco_moldura(p), pt._avanco_moldura(dict(p, trilho='PESADO')))
        # e nao tem fechamento frontal em cima (print do usuario): sem testeira,
        # nem o campo dela na aba
        pecas = {o['porta_moldura_peca'] for o in pt._moldura_da_porta(grupo)}
        self.assertNotIn('TESTEIRA', pecas)
        self.assertIn('RODAPE', pecas)
        addon.hud._selecionar_porta_hud(bpy.context, folhas[0], 'PORTA')
        bpy.context.scene.cabinet_aba = 'PORTAS'
        campos = {v[5][2] for v in addon.gaveta._widgets_gaveta(bpy.context, 564, 1600)
                  if v[5] and v[5][0] == 'medida'}
        self.assertNotIn('ui_porta_testeira', campos)
        self.assertIn('ui_porta_rodape', campos)
        # trocar para o pesado na porta pronta: folha de 18, bases sem canais
        nomes = {k: o.name for k, o in bases.items()}
        self.assertEqual(pt._editar_parametro_porta(bpy.context, grupo, 'trilho', 'PESADO'), '')
        for folha in pt._folhas_portas(grupo):
            self.assertAlmostEqual(folha.chapa_espessura_mm, 18.0)
        for nome in nomes.values():
            base = bpy.data.objects[nome]
            self.assertNotIn('chapa_canais', base)
            self.assertEqual(len(base.data.vertices), 8)       # caixa de novo
        # o pesado tem a testeira de volta
        self.assertIn('TESTEIRA', {o['porta_moldura_peca']
                                   for o in pt._moldura_da_porta(grupo)})

    def test_porta_com_moldura_no_modulo(self):
        # Metade-metade (1-2 no mesmo canto de dentro, 3-4 de dentro para
        # fora) respondido "com moldura": vale o modulo inteiro e as seis
        # pecas nascem como chapas de 15, as folhas de 18 (pedido do usuario)
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
        # ja' ao criar, o modulo mede com a moldura (sem esperar o timer)
        self.assertAlmostEqual(conj.conj_largura_mm, L + 2 * 15.0, places=2)
        for o in moldura.values():
            self.assertIn(addon.chapas.MARCA_CHAPA, o)
            self.assertEqual(o.parent, grupo)
            self.assertAlmostEqual(o.chapa_espessura_mm, 15.0)
        for folha in pt._folhas_portas(grupo):
            self.assertAlmostEqual(folha.chapa_espessura_mm, 18.0)
        # nao entram nas operacoes do modulo (como as folhas)
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
        self.assertAlmostEqual(hi[0], -L / 2, places=3)       # encosta por fora
        self.assertAlmostEqual(lo[0], -L / 2 - 15.0, places=3)
        self.assertAlmostEqual(hi[1], P / 2, places=3)         # das costas
        self.assertAlmostEqual(lo[1], -P / 2 - pt._avanco_moldura(p), places=3)
        # o E de uma peca vale para a moldura inteira
        nomes = {k: o.name for k, o in moldura.items()}
        moldura['TESTEIRA'].chapa_espessura_mm = 20.0
        self.assertAlmostEqual(grupo['porta_parametros']['moldura_mm'], 20.0)
        for nome in nomes.values():
            self.assertAlmostEqual(bpy.data.objects[nome].chapa_espessura_mm, 20.0)
        # a moldura conta como o armario (pedido do usuario): L/A/P do modulo
        # sao do ENVELOPE, e mudar a largura leva a moldura ate' ela
        bpy.context.view_layer.update()
        self.assertAlmostEqual(conj.conj_largura_mm, L + 2 * 20.0, places=2)
        envelope = addon.modulos.medir_conjunto(conj)
        self.assertGreater(envelope[1], A + 100.0)            # rodape + topo
        self.assertAlmostEqual(envelope[2], P + pt._avanco_moldura(
            dict(grupo['porta_parametros'])), places=2)
        conj.conj_largura_mm = L + 100
        bpy.context.view_layer.update()
        lo, hi = caixa_local(nomes['LATERAL_DIR'])
        self.assertAlmostEqual(hi[0], (L + 100) / 2, places=3)   # a borda de fora
        self.assertAlmostEqual(conj.conj_largura_mm, L + 100, places=2)
        self.assertAlmostEqual(pt._caixa_do_modulo(conj)[0], L + 60, places=2)  # o corpo
        # a caixa da HUD do modulo e' a do envelope
        bpy.ops.object.select_all(action='DESELECT')
        conj.select_set(True)
        bpy.context.view_layer.objects.active = conj
        (_obj, _modo, pecas), = addon.hud._itens_da_selecao(bpy.context)
        self.assertTrue(set(addon.portas._moldura_da_porta(grupo)) <= set(pecas))

    def test_metade_metade_embutida_usa_o_vao_de_dentro(self):
        # O mesmo gesto, respondido "embutida": a medida de DENTRO da chapa,
        # mesmo com o 4o clique no canto de fora; nada de moldura
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
        # correr escolhido no metade-metade: a caixa pergunta; a resposta cria
        w = {'etapa': 'TIPO', 'escolhas': {'folhas': 2}, 'embutida': False}
        op = SimpleNamespace(_w=w, _metade_metade=lambda: True,
                             _ir=lambda etapa, mouse=None: w.update(etapa=etapa),
                             _criar=lambda ctx: 'CRIADA')
        self.assertIsNone(tipo._escolher_abertura(op, None, 'CORRER'))
        self.assertEqual(w['etapa'], 'MOLDURA')
        # com moldura, mais uma pergunta: tem base (rodape)? (pedido do usuario)
        self.assertIsNone(tipo._escolher(op, None, 'MOLDURA'))
        self.assertEqual(w['escolhas']['tipo_correr'], 'MOLDURA')
        self.assertEqual(w['etapa'], 'BASE')
        self.assertIsNone(tipo._escolher(op, None, 'SEM'))
        self.assertEqual(w['escolhas']['rodape_mm'], 0.0)
        # e o trilho (pedido do usuario): pesado ou leve -- a resposta cria
        self.assertEqual(w['etapa'], 'TRILHO')
        self.assertEqual(tipo._escolher(op, None, 'LEVE'), 'CRIADA')
        self.assertEqual(w['escolhas']['trilho'], 'LEVE')
        # embutida: nada de base, cria direto
        w.update(etapa='MOLDURA', escolhas={'folhas': 2})
        self.assertEqual(tipo._escolher(op, None, 'EMBUTIDA'), 'CRIADA')
        self.assertNotIn('rodape_mm', w['escolhas'])
        # gesto de fora para dentro (com moldura, sem duvida): so' a base
        op._metade_metade = lambda: False
        w.update(etapa='TIPO', escolhas={'folhas': 2}, embutida=False)
        self.assertIsNone(tipo._escolher_abertura(op, None, 'CORRER'))
        self.assertEqual(w['etapa'], 'BASE')
        self.assertIsNone(tipo._escolher(op, None, 'COM'))
        self.assertEqual(w['escolhas']['rodape_mm'],
                         addon.portas.PADRAO_MEDIDAS_PORTAS['porta_rodape_mm'])
        self.assertEqual(tipo._escolher(op, None, 'PESADO'), 'CRIADA')
        # embutido pelos cliques: cria direto
        w.update(etapa='TIPO', escolhas={'folhas': 2}, embutida=True)
        self.assertEqual(tipo._escolher_abertura(op, None, 'CORRER'), 'CRIADA')
        # por cima, 2 folhas: Giro ou Correr (com moldura), nao mais giro direto
        self.assertIn('CORRER', dict(addon.portas.TIPOS_SOBREPOSTA))

    def test_correr_trilhos_como_os_de_verdade(self):
        # a foto do usuario: em CIMA um U alto, um canal fundo por folha
        # (ela entra e sobra folga para levantar); em BAIXO uma chapa baixa
        # com uma guia sob cada folha, que fica em pe' nela
        f = addon.ferragens
        p = parametros(abertura='CORRER', folhas=3)
        folhas = addon.portas._calcular_folhas_portas(600, 800, p)
        itens = f._ferragens_da_porta(p, 600, 800, folhas)
        trilhos = {i['id']: i for i in itens if i['tipo'] == 'TRILHO'}
        self.assertEqual(set(trilhos), {'TRILHO_CIMA', 'TRILHO_BAIXO'})
        cima, baixo = trilhos['TRILHO_CIMA'], trilhos['TRILHO_BAIXO']
        # chapa do topo, 2 paredes de fora e 2 entre os 3 canais
        self.assertEqual(len(cima['caixas']), 1 + 2 + 2)
        # chapa de baixo e uma guia por folha
        self.assertEqual(len(baixo['caixas']), 1 + 3)
        for l, a, e, c in folhas:
            frente, costas = c[2] + e / 2, c[2] - e / 2
            paredes = [cx for cx in cima['caixas'][1:]
                       if min(v.z for v in cx) < frente - 1e-6
                       and max(v.z for v in cx) > costas + 1e-6]
            self.assertFalse(paredes, 'parede dentro do canal da folha')
            pe, topo = c[1] - a / 2, c[1] + a / 2
            # em pe' na guia; o topo dentro do canal, longe da chapa
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

    # ---- nomes e organizacao dos grupos (pedido do usuario, com print)
    def test_grupo_tem_nome_colecao_e_porta_pelo_modelo(self):
        conj = self.nicho()
        L, A, P, _E = addon.portas._caixa_do_modulo(conj)
        cena = bpy.context.scene
        # sem nome digitado vale a sugestao "Armario LxAxP"
        self.assertEqual(conj.name, 'Armario %dx%dx%d' % (round(L), round(A),
                                                          round(P)))
        colecao = conj.users_collection[0]
        self.assertEqual(colecao.name, conj.name)
        self.assertTrue(colecao.get(addon.modulos.MARCA_COLECAO_MODULO))
        self.assertIn(colecao, list(cena.collection.children))
        for chapa in addon.modulos._chapas_do_conjunto(conj):
            self.assertEqual(list(chapa.users_collection), [colecao])
        # a porta mora no grupo, com o nome do modelo; folhas = Folha NN
        # (nomes em portugues, sem sublinhado: pedido do usuario)
        grupo = self.porta_no_nicho(conj)
        self.assertEqual(grupo.name, 'Porta Dupla')
        self.assertEqual(list(grupo.users_collection), [colecao])
        self.assertEqual([f.name for f in addon.portas._folhas_portas(grupo)],
                         ['Folha 01', 'Folha 02'])
        nomes = [o.name for o in addon.ferragens._ferragens_portas(grupo)]
        self.assertFalse([n for n in nomes if '_' in n or 'Hinge' in n
                          or 'Screw' in n or 'Armature' in n], nomes)
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'abertura', 'CORRER'), '')
        self.assertEqual(grupo.name, 'Porta de Correr')
        for p, nome in ((dict(abertura='BASCULANTE'), 'Porta Basculante'),
                        (dict(folhas=1), 'Porta Unica'),
                        (dict(folhas=2, dobradica='SUPER_CURVA'),
                         'Porta Embutida Dupla'),
                        (dict(folhas=1, dobradica='SUPER_CURVA'),
                         'Porta Embutida Unica')):
            self.assertEqual(addon.portas._nome_da_porta(parametros(**p)), nome)
        # nome trocado pelo usuario fica
        grupo.name = 'Porta da pia'
        addon.portas._editar_parametro_porta(bpy.context, grupo, 'abertura', 'GIRO')
        self.assertEqual(grupo.name, 'Porta da pia')
        # renomear o grupo leva a Collection e o vinculo da porta junto
        self.assertTrue(addon.modulos.nomear_grupo(conj, '  Cozinha  '))
        self.assertEqual((conj.name, colecao.name), ('Cozinha', 'Cozinha'))
        self.assertEqual(grupo[addon.portas.CHAVE_MODULO_PORTA], 'Cozinha')
        self.assertEqual(addon.portas._portas_do_conjunto(conj), [grupo])
        self.assertFalse(addon.modulos.nomear_grupo(conj, '   '))
        # desagrupar: a chapa sai para a RAIZ da cena
        chapa = addon.modulos._chapas_do_conjunto(conj)[0]
        addon.solda.desagregar(chapa)
        self.assertIsNone(chapa.parent)
        self.assertEqual(list(chapa.users_collection), [cena.collection])

    def test_agrupar_com_nome_e_grupo_vazio_some_com_a_colecao(self):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        # F3 abre o dialogo; por script o nome vem pronto
        self.assertEqual(bpy.ops.object.cabinet_agrupar(nome='Banheiro'),
                         {'FINISHED'})
        conj = bpy.context.object
        colecao = conj.users_collection[0]
        self.assertEqual((conj.name, colecao.name), ('Banheiro', 'Banheiro'))
        addon.solda.desagregar_grupo(addon.modulos._chapas_do_conjunto(conj))
        self.assertNotIn('Banheiro', bpy.data.objects)
        self.assertNotIn('Banheiro', bpy.data.collections)
        # armario apagado com X: a conferencia tira a Collection vazia
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar(nome='Sala')
        for o in list(bpy.data.collections['Sala'].all_objects):
            bpy.data.objects.remove(o, do_unlink=True)
        addon.ferragens._conferir_ferragens()
        self.assertNotIn('Sala', bpy.data.collections)

    def test_corrente_junta_soltas_e_pergunta_o_nome_na_gaveta(self):
        # Pela gaveta (sem pop-up): o grupo nasce com a sugestao e a caixa
        # preta traz o campo; o que se digita vira o nome.
        piso = addon.chapas.nova_chapa('Piso', 600.0, 400.0, 18.0, (0, 0, 9.0),
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
        for letra in 'Lavanderia':      # o texto vem todo selecionado
            addon.gaveta_desenho._tecla_no_texto(estado, letra.upper(), letra)
        self.assertEqual(estado['texto'], 'Lavanderia')
        # Enter no modal de digitar (cabinet_digitar_nome_grupo)
        op = SimpleNamespace(_redesenhar=lambda c: None)
        evento = SimpleNamespace(type='RET', value='PRESS', ctrl=False,
                                 unicode='')
        self.assertEqual(addon.solda.OBJECT_OT_digitar_nome_grupo.modal(
            op, bpy.context, evento), {'FINISHED'})
        self.assertEqual(grupo.name, 'Lavanderia')
        self.assertIsNone(addon.perguntas._pergunta_atual[0])
        # o OK da caixa (cabinet_nomear_grupo) faz o mesmo; Manter fica
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
        # Pedido do usuario: os Empties (modulo, grupo de portas, ponta do
        # pistao) poluiam a vista. Continuam (o parentesco move tudo), mas
        # no tamanho minimo; os de arquivo antigo encolhem na conferencia.
        conj = self.nicho()
        grupo = self.porta_de_giro(conj, abertura='BASCULANTE',
                                   dobradica_lado='CIMA', pistoes_qtd=1)
        pontos = self.ferragens(grupo, 'PISTAO_PONTO')
        self.assertTrue(pontos)
        for o in [conj, grupo, *pontos]:
            self.assertEqual(o.type, 'EMPTY')
            self.assertAlmostEqual(o.empty_display_size,
                                   addon.chapas.TAMANHO_EMPTY_OCULTO, places=6)
        conj.empty_display_size = 0.15        # arquivo de antes
        grupo.empty_display_type = 'ARROWS'
        grupo.empty_display_size = 0.05
        addon.ferragens._conferir_ferragens()
        for o in (conj, grupo):
            self.assertAlmostEqual(o.empty_display_size,
                                   addon.chapas.TAMANHO_EMPTY_OCULTO, places=6)
        self.assertEqual(grupo.empty_display_type, 'PLAIN_AXES')
        # Empty do usuario (sem marca) ninguem mexe
        livre = bpy.data.objects.new('Livre', None)
        bpy.context.collection.objects.link(livre)
        livre.empty_display_size = 0.5
        addon.ferragens._conferir_ferragens()
        self.assertEqual(livre.empty_display_size, 0.5)

    def test_modulo_selecionado_nao_desenha_a_porta(self):
        # Pedido do usuario: clicar nas CHAPAS seleciona o modulo (e a porta
        # junto), mas dobradicas, linhas do vao, diagonal, cantos e sliders
        # so' aparecem com a porta selecionada por si.
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
        # Pedido do usuario: os dois sliders nao se encostam; sobra folga
        # entre eles e das pontas da porta. E nao andam quando a folha abre.
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        esquerda, direita = addon.portas._folhas_portas(grupo)
        local = lambda v: (conj.matrix_world.inverted() @ v) * 1000.0
        a = sorted(local(p).x for p in addon.portas_viewport._slider_no_mundo(esquerda))
        b = sorted(local(p).x for p in addon.portas_viewport._slider_no_mundo(direita))
        self.assertGreaterEqual(b[0] - a[1], 2 * addon.portas_viewport.SLIDER_RECUO_MM)
        borda = min(local(esquerda.matrix_world @ v.co).x
                    for v in esquerda.data.vertices)
        # malha em float32: 1e-3 mm de tolerancia
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
        r = addon.portas.RESPIRO_PORTA_MM / 1000        # nunca rente a' borda
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
        # Forca a ordem alfabetica contraria a ordem das dependencias.
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
        # O eixo que nao varia na diagonal e' a normal; o lado sai do
        # centro do movel. Diagonal sem mudar Z = porta deitada.
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
        # Deitada, a largura corre pelo lado MAIOR da diagonal
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
        # reta: cobre o tampo inteiro e fica por cima dele (com a folga)
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
        # REGRESSAO: a lateral ficava com a espessura de quando a porta
        # nasceu; ao trocar a do modulo, a porta reta sobrava para fora.
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
        # espessura livre (nao arredonda mais para 15/18/20/30)
        folhas[0].chapa_espessura_mm = 21.0
        for folha in addon.portas._folhas_portas(grupo):
            self.assertEqual(folha.chapa_espessura_mm, 21.0)
            self.assertAlmostEqual(folha.dimensions.z, 0.021, places=5)
        self.assertEqual(grupo['porta_parametros']['espessura_mm'], 21.0)
        # a face de tras continua no plano do vao (mais a folga da Reta)
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

    # ------------------------------------------- edicao da porta colocada
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
        # Shift soma a porta a' selecao em vez de troca-la
        addon.hud._selecionar_chapa_hud(bpy.context, folha)          # o modulo
        addon.hud._selecionar_porta_hud(bpy.context, folha, 'PORTA', somar=True)
        self.assertIn(conj, bpy.context.selected_objects)
        self.assertEqual(bpy.context.object, grupo)
        # folha sozinha tambem desliga o contorno nativo (conta como porta)
        addon.hud._selecionar_porta_hud(bpy.context, folha, 'FOLHA')
        self.assertIn(folha.name, addon.eventos._grupos_selecionados(bpy.context.view_layer))

    def test_aba_mostra_a_porta_selecionada_e_nao_a_cena(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)       # reta, 2 folhas
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
        # a dobradica e' automatica: nem aparece na aba (pedido do usuario)
        self.assertNotIn('Dobradica', [v[4] for v in widgets])
        folhas = next(v[5] for v in widgets
                      if v[5] and v[5][:2] == ('contador', 'porta_folhas'))
        self.assertEqual(folhas[2], 2)
        self.assertEqual(folhas[5], grupo.name)
        self.assertNotIn('porta_folhas', acesos)       # nada de segmentos
        # "Folga no perimetro" nao existe (pedido do usuario)
        self.assertFalse([v for v in widgets if v[5] and v[5][0] == 'medida'
                          and v[5][2] == 'ui_porta_folga'])
        rotulos = [v[4] for v in widgets]
        # sem cabecalho "Porta N de M - vao L x A" (nome/medida repetidos)
        self.assertFalse(any(r.startswith('Porta ') and 'vao' in r
                             for r in rotulos))
        botao = next(v[5] for v in widgets if v[5] and v[5][0] == 'portas')
        self.assertTrue(botao[4])

    def test_aba_da_porta_com_moldura_em_categorias(self):
        # Auditoria do usuario: campos compactos, organizados por categoria
        # (Porta, Folhas, Moldura, Abertura), que nao cortam texto e nao se
        # sobrepoem; a moldura e' editavel ali
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
        titulos = ['Porta', 'Folhas', 'Moldura', 'Abertura']
        for largura in (190, 320, 564):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1600)
            ys = {v[4]: v[1] for v in widgets if v[5] is None and v[4] in titulos}
            self.assertEqual(sorted(ys, key=lambda t: -ys[t]), titulos, largura)
            campos = {v[5][2]: v for v in widgets if v[5] and v[5][0] == 'medida'}
            for prop in ('ui_porta_moldura', 'ui_porta_rodape', 'ui_porta_testeira'):
                self.assertIn(prop, campos)
                self.assertLess(campos[prop][1], ys['Moldura'])
                self.assertGreater(campos[prop][1], ys['Abertura'])
            self.assertNotIn('ui_porta_recuo_correr', campos)     # com moldura, sem recuo
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
            # rotulo inteiro, nem que seja no menor tamanho da fonte (9)
            blf.size(0, 9)
            for v in campos.values():
                self.assertLessEqual(blf.dimensions(0, v[5][3])[0], v[2] - 14,
                                     (largura, v[5][3]))
        # o rodape zerado na aba some da moldura
        self.assertIsNone(addon.gaveta_eventos.aplicar_medida(
            bpy.context, 'porta', grupo.name, 'ui_porta_rodape', 0.0))
        self.assertEqual({o['porta_moldura_peca']
                          for o in addon.portas._moldura_da_porta(grupo)},
                         {'LATERAL_ESQ', 'LATERAL_DIR', 'BASE_CIMA',
                          'TESTEIRA', 'BASE_BAIXO'})

    def test_folhas_e_campo_compacto_e_botoes_com_icone_em_cima(self):
        # Pedido do usuario: Folhas deixa de ser 1 2 3 4 e vira um campo
        # compacto AO LADO do ultimo campo da porta (Entre folhas/planos),
        # que arrasta e digita; Reposicionar e Frente vao para CIMA das
        # medidas, com icone.
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)       # reta, 2 folhas
        addon.hud._selecionar_porta_hud(
            bpy.context, addon.portas._folhas_portas(grupo)[0], 'PORTA')
        bpy.context.scene.cabinet_aba = 'PORTAS'
        ops = ('object.cabinet_apanhar_vao', 'object.cabinet_definir_frente')
        for largura in (190, 320, 564):
            widgets = addon.gaveta._widgets_gaveta(bpy.context, largura, 1400)
            campo = next(v for v in widgets
                         if v[5] and v[5][:2] == ('contador', 'porta_folhas'))
            self.assertEqual(campo[2], addon.gaveta.LARGURA_CAMPO_FOLHAS)
            self.assertTrue(addon.gaveta_desenho._eh_campo_contador(campo[5]))
            vizinho = next(v for v in widgets if v[5] and v[5][0] == 'medida'
                           and v[5][2] == 'ui_porta_entre_folhas')
            self.assertEqual(vizinho[1], campo[1], largura)    # mesma linha
            self.assertLessEqual(vizinho[0] + vizinho[2], campo[0])
            self.assertLessEqual(campo[0] + campo[2], min(largura - 12, 552) + 0.01)
            botoes = [v for v in widgets if v[5] and v[5][0] == 'operador'
                      and v[5][1] in ops]
            self.assertEqual(len(botoes), 2)
            medidas = [v for v in widgets if v[5] and v[5][0] == 'medida']
            self.assertGreater(min(b[1] for b in botoes),
                               max(m[1] + m[3] for m in medidas), largura)
            for b in botoes:
                self.assertTrue(addon.gaveta_eventos._icone_ao_lado(b[5]))
                self.assertTrue(addon.gaveta_eventos._icone_acao_gaveta(b[5]))
                cx, _cy = addon.gaveta_eventos._centro_icone(*b[:4], b[5])
                self.assertLess(cx, b[0] + b[3])       # na ponta esquerda
        # digitar qualquer numero: o que a abertura aceita grava; o resto
        # avisa e nao mexe na porta
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
        # embutida: as folhas ficam DENTRO do modulo
        L, A, P, E = addon.portas._caixa_do_modulo(conj)
        lo, hi = self.limites_folhas(conj, grupo)
        self.assertGreater(lo[0], -L / 2000)
        self.assertLess(hi[0], L / 2000)
        # e ela continua acompanhando o modulo
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
            self.assertEqual(folha.chapa_espessura_mm, 21.0)   # livre

    def test_porta_selecionada_so_na_aba_portas_e_sem_dobradicas(self):
        # Pedido do usuario: o menu mostra o que vale para a selecao. A
        # porta e' da aba Portas (a Modulos nao a mostra) e, nela, nada
        # de dobradica: isso e' da selecao das ferragens.
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
                         ['Largura', 'Altura', 'Espessura'])
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
        # o ponto chega da macro NATIVA (cursor + snap do Blender): nada de
        # ler malhas; o timer acorda o modal com o ponto confirmado
        evento = SimpleNamespace(type='TIMER', value='NOTHING')
        with patch.object(addon.assistente.view3d_utils, 'location_3d_to_region_2d',
                          side_effect=AssertionError('projetou vertices')):
            self.assertEqual(tipo.modal(falso, bpy.context, evento), {'RUNNING_MODAL'})
            self.assertEqual(len(iniciados), 0)     # sem pedido, nao reinicia
            for ponto, obj in (pontos[0], pontos[0], pontos[1]):
                falso._w['ponto_confirmado'] = (ponto, obj.name)
                self.assertEqual(tipo.modal(falso, bpy.context, evento), {'RUNNING_MODAL'})
                if falso._w['etapa'] == 'DIAGONAL':
                    # entre um canto e outro o snap nativo recomeca
                    self.assertEqual(tipo.modal(falso, bpy.context, evento), {'RUNNING_MODAL'})
            self.assertEqual(len(falso._pontos), 2)
            self.assertEqual(falso._w['etapa'], 'FOLHAS')
            self.assertEqual(len(iniciados), 2)
        tipo._voltar(falso)
        self.assertEqual(falso._w['etapa'], 'DIAGONAL')
        self.assertEqual(len(falso._pontos), 1)
        self.assertTrue(falso._w['iniciar_snap'])

    # Regressao (era BUG, corrigido na 305): o snap nativo devolve so' o
    # ponto; a chapa saia do ray cast, que passa rente a' quina do vao, ou
    # do modulo ATIVO. Sem modulo selecionado nao vinha peca e o 2o clique
    # derrubava o wizard (handlers e HUD presos): porta nova nao nascia.
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
            # ponto solto (snap sem vertice): sem peca
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

    # ------------------------------------------------ wizard (API legada)
    def test_quatro_cliques_coberturas_e_dobradica(self):
        # Desenho do usuario: 1 = canto da porta, 2 = do vao, 3 = vao
        # oposto, 4 = porta oposta. Cobertura de cada lado em espessuras.
        E = 18.0
        bordas = [Vector((-18, 382, 0)), Vector((573, -18, 0))]
        vaos = [Vector((0, 364, 0)), Vector((564, 0, 0))]
        cob = addon.portas._coberturas_dos_cantos(bordas, vaos, E)
        self.assertEqual([cob[k] for k in addon.portas.COBERTURAS_LADOS],
                         [1.0, 0.5, 1.0, 1.0])
        self.assertEqual(addon.portas._lados_fora_do_padrao(cob), [])
        # +-2 mm ainda e' reta; 40 mm a mais, nao
        self.assertEqual(addon.portas._encaixar_cobertura(19.5, E), 1.0)
        self.assertEqual(addon.portas._lados_fora_do_padrao(addon.portas._coberturas_dos_cantos(
            [Vector((-58, 382, 0)), bordas[1]], vaos, E)), ['cobertura_esq_e'])
        # clique 1 e 2 no mesmo ponto: a margem do par 3-4 vale para ele,
        # contada para DENTRO a partir do clique
        novos, espelhados = addon.portas._espelhar_margem(
            [Vector((-18, 382, 0)), Vector((582, -18, 0))],
            [Vector((-18, 382, 0)), Vector((564, 0, 0))])
        self.assertEqual(espelhados, [True, False])
        self.assertEqual(novos[0].to_tuple(), (0.0, 364.0, 0.0))
        # os dois pares no mesmo ponto: nada se espelha
        self.assertEqual(addon.portas._espelhar_margem(vaos, vaos)[1], [False, False])
        # dobradica automatica pela cobertura do lado dela
        self.assertEqual([addon.portas._dobradica_da_cobertura(f) for f in (1.0, 0.5)],
                         ['RETA', 'CURVA'])
        self.assertEqual(addon.portas._dobradica_da_cobertura(0.0, embutida=True),
                         'SUPER_CURVA')
        self.assertTrue(addon.portas._porta_embutida(dict.fromkeys(
            addon.portas.COBERTURAS_LADOS, 0.0)))
        self.assertFalse(addon.portas._porta_embutida(cob))
        # linha das dobradicas: na FACE INTERNA da chapa (borda do vao),
        # com o comprimento da folha (print do usuario: ficavam na borda
        # de fora da folha)
        arestas = addon.portas._arestas_da_porta(564.0, 364.0, cob, E, 'GIRO')
        self.assertEqual([a['lado'] for a in arestas], ['ESQUERDA', 'DIREITA'])
        esq, dir_ = arestas
        cobre = E - addon.portas.RESPIRO_PORTA_MM      # a Reta tambem tem respiro
        self.assertEqual((esq['a'].x, esq['a'].y, esq['b'].y),
                         (0.0, -cobre, 364.0 + cobre))
        self.assertEqual(dir_['a'].x, 564.0)
        # meia = metade menos o respiro de 2 mm
        self.assertEqual((esq['cobertura'], dir_['cobertura']), (cobre, 7.0))
        cima, = addon.portas._arestas_da_porta(564.0, 364.0, cob, E, 'BASCULANTE')
        self.assertEqual((cima['lado'], cima['a'].y, cima['a'].x, cima['b'].x),
                         ('CIMA', 364.0, -cobre, 571.0))

    def test_volume_da_dobradica_na_face_interna(self):
        cob = dict.fromkeys(addon.portas.COBERTURAS_LADOS, 1.0)
        esq, dir_ = addon.portas._arestas_da_porta(564.0, 364.0, cob, 18.0, 'GIRO')
        (corpo, caneco), = addon.portas._caixas_dobradicas(esq, [100.0], 0.0)
        faixa = lambda caixa, i: (min(p[i] for p in caixa), max(p[i] for p in caixa))
        # corpo: da face interna (x=0) para DENTRO do movel, atras da folha
        self.assertEqual(faixa(corpo, 0), (0.0, addon.portas.DOBRADICA_AVANCO_MM))
        cobre = 18.0 - addon.portas.RESPIRO_PORTA_MM    # a folha comeca ai'
        self.assertEqual(faixa(corpo, 1), (100.0 - cobre - 25.0,
                                           100.0 - cobre + 25.0))
        self.assertEqual(faixa(corpo, 2), (-addon.portas.DOBRADICA_FUNDO_MM, 0.0))
        # caneco: na folha, a 5 mm da borda dela (x = -cobre), 12 de fundo
        self.assertEqual(faixa(caneco, 0), (-cobre + 5.0, -cobre + 40.0))
        self.assertEqual(faixa(caneco, 2), (-addon.portas.CANECO_ABA_MM,
                                            addon.portas.CANECO_FUNDO_MM))
        # do outro lado o volume aponta para o outro sentido
        (corpo, _caneco), = addon.portas._caixas_dobradicas(dir_, [100.0], 0.0)
        self.assertEqual(faixa(corpo, 0), (564.0 - addon.portas.DOBRADICA_AVANCO_MM, 564.0))

    def test_ferragens_em_segmentos_iguais_com_margem(self):
        self.assertEqual(addon.portas._posicoes_ferragens(700.0, 3, 100.0),
                         [100.0, 350.0, 600.0])
        self.assertEqual(addon.portas._posicoes_ferragens(700.0, 1, 100.0), [350.0])
        self.assertEqual(addon.portas._posicoes_ferragens(100.0, 2, 80.0), [50.0, 50.0])
        self.assertEqual(addon.portas._posicoes_ferragens(500.0, 0, 100.0), [])
        # padroes de marcenaria (editaveis no wizard)
        self.assertEqual([addon.portas._qtd_dobradicas_padrao(a)
                          for a in (700, 900, 1200, 1800, 2200)],
                         [2, 2, 3, 4, 5])
        self.assertEqual(addon.portas._qtd_pistoes_padrao(560), 1)
        self.assertEqual(addon.portas._qtd_pistoes_padrao(800), 2)
        self.assertEqual(addon.portas.MARGEM_DOBRADICAS_PADRAO, 100.0)

    def test_dobradicas_nunca_se_sobrepoem(self):
        # relato do usuario: no posicionamento (mouse Y) a margem ia ate' o
        # meio da borda e as dobradicas ficavam umas sobre as outras
        ajustar = addon.portas._ajustar_dobradicas
        passo = addon.portas.PASSO_MIN_DOBRADICAS_MM
        meia = addon.portas.DOBRADICA_ALTURA_MM / 2.0
        self.assertEqual(ajustar(700.0, 3, 100.0), (3, 100.0))     # padrao intacto
        self.assertEqual(ajustar(700.0, 3, 350.0), (3, (700.0 - 2 * passo) / 2))
        self.assertEqual(ajustar(700.0, 3, 0.0), (3, meia))        # inteira na folha
        self.assertEqual(ajustar(200.0, 6, 100.0)[0], 3)           # so' as que cabem
        # no wizard: o valor digitado (e o mouse Y, pela mesma funcao)
        w = {'aresta': {'a': Vector((0.0, 0.0)), 'b': Vector((0.0, 700.0))},
             'qtd': 3, 'margem': 100.0}
        addon.portas._assistente_porta[0] = w
        try:
            addon.assistente._editar_assistente('dobradicas_margem_mm', 5000.0)
            self.assertEqual((w['qtd'], w['margem']), (3, 290.0))
            # mais dobradicas: a margem encolhe para caberem
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
        # porta ja' criada: a margem gravada passa pelo mesmo limite, e a
        # gravada antes dele nao empilha as dobradicas
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
        # Regra do usuario: aberta 90 graus = pistao no DOBRO do fechado.
        # Modelo real do catalogo, o maior que cabe nos 2/3 de cima do vao.
        e = 18.0

        def folha(altura):          # Reta: a folha passa 18 mm em cima
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
            # a fixacao da lateral fica atras da folha, abaixo do suporte
            lateral, na_folha, _a = addon.portas._pontas_pistao(g, 25.0, f)
            self.assertLess(lateral.y, na_folha.y)
            self.assertLess(lateral.z, na_folha.z)
            escolhidos.append(g['aberto'])
        self.assertEqual(escolhidos, sorted(escolhidos))
        self.assertLess(escolhidos[0], escolhidos[-1])
        # a aberta e' a extensao maxima: a folha no lugar certo, girada
        p = {'abertura': 'BASCULANTE'}
        f = folha(350.0)
        g = addon.portas._pistao_do_vao(350.0, f)
        _l, _f, aberta = addon.portas._pontas_pistao(g, 25.0, f)
        _l, fechada, _a = addon.portas._pontas_pistao(g, 25.0, f)
        giro = addon.ferragens._matriz_abertura(p, 600.0, 1, 0, f, 1.0)
        c = Vector(f[3])
        girada = giro @ ((fechada - c) / 1000.0) * 1000.0
        self.assertLess((girada - aberta).length, 1e-3)

        # Manual: so' sobe. Descer alem do automatico trava no curso
        # maximo; subir encurta o aberto e mantem o fechado.
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
        # o wizard realca o VOLUME do pistao fechado (como as dobradicas):
        # corpo e haste de ponta a ponta, mais os 2 suportes
        itens = addon.ferragens._pistoes_da_porta({'pistoes_qtd': 1}, 600.0, 350.0, [f])
        caixas = addon.ferragens._caixas_dos_itens_pistao(itens)
        self.assertEqual(len(caixas), 4)
        lateral, fechada, _a = addon.portas._pontas_pistao(g, 25.0, f)
        self.assertAlmostEqual((sum(caixas[0], Vector()) / 8
                                - (lateral + fechada) / 2).length, 0.0, places=3)
        # e nem o suporte da folha sobe ate' a dobradica
        topo = addon.portas._pistao_do_vao(350.0, f, 1.0)
        self.assertAlmostEqual(topo['offset'], topo['offset_min'], places=3)
        self.assertAlmostEqual(topo['d'], addon.portas.PISTAO_DA_DOBRADICA_MIN_MM)

    def test_porta_guarda_as_ferragens_do_wizard(self):
        conj = self.nicho()
        grupo = self.porta_no_nicho(conj)
        # sem wizard: 0 = automatico, lado esquerdo
        p = grupo['porta_parametros']
        self.assertEqual((p['dobradicas_qtd'], p['dobradica_lado']), (0, 'ESQUERDA'))
        # a aba continua lendo a porta sem tropecar nos campos novos
        valores = addon.gaveta._valores_portas(bpy.context.scene, grupo)
        self.assertEqual(valores['dobradica_lado'], 'ESQUERDA')
        addon.portas._carregar_portas_na_cena(bpy.context.scene, grupo)

    def test_campos_da_porta_seguem_a_abertura(self):
        # Com a porta selecionada os campos aparecem e seguem o tipo dela
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
        # a sobreposicao e' consequencia da largura da folha: sem campo
        self.assertNotIn('ui_porta_sobreposicao', props())

    def test_previa_e_execucao_usam_o_mesmo_vao(self):
        from types import SimpleNamespace
        conj, cima, baixo = self.duas_fileiras()
        folha = addon.portas._folhas_portas(cima)[-1]
        a = conj.matrix_world @ Vector((-0.3, -0.15, 0))
        # a base da porta de cima (onde a de baixo foi apoiada)
        z = self.limites_folhas(conj, cima)[0][2]
        b = conj.matrix_world @ Vector((0.3, -0.168, z))
        chapa = addon.modulos._chapas_do_conjunto(conj)[0]
        tipo = addon.assistente.OBJECT_OT_apanhar_vao_portas
        # 4 cliques: porta e vao no mesmo ponto nos dois cantos
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
        # pedido do usuario: a correr "diferenciada" do Promob vira estilo
        # NOSSO -- perfil de aluminio (23 de fundo, 10 de face) em volta de
        # um painel de 5; o trilho continua o do add-on
        conj = self.nicho()
        grupo = addon.portas.porta_no_modulo(conj, folhas=2, abertura='CORRER')
        self.assertEqual(addon.portas._editar_parametro_porta(
            bpy.context, grupo, 'folha', 'QUADRO'), '')
        grupo = addon.portas._portas_do_conjunto(conj)[-1]
        for folha in addon.portas._folhas_portas(grupo):
            self.assertAlmostEqual(folha.chapa_espessura_mm, 23.0, places=3)
            # 4 barras do perfil + o painel = 5 caixas de 8 vertices
            self.assertEqual(len(folha.data.vertices), 40)
            self.assertEqual([m.name for m in folha.data.materials],
                             [addon.portas.NOME_MATERIAL_QUADRO,
                              addon.portas.NOME_MATERIAL_PAINEL])
            # o painel (material 1) fica a 6 mm da face de fora
            painel = [folha.data.vertices[i].co.z * 1000.0
                      for p in folha.data.polygons if p.material_index == 1
                      for i in p.vertices]
            self.assertAlmostEqual(max(painel), 23.0 / 2 - 6.0, places=3)
        # a aba mostra a escolha da folha so' na porta de correr
        addon.hud._selecionar_porta_hud(
            bpy.context, addon.portas._folhas_portas(grupo)[0], 'PORTA')
        bpy.context.scene.cabinet_aba = 'PORTAS'
        acoes = [v[5] for v in addon.gaveta._widgets_gaveta(bpy.context, 480, 1600) if v[5]]
        self.assertTrue(any(a[0] == 'escolha' and a[1] == 'porta_folha' for a in acoes))
        # de volta a' chapa: a caixa de 18 e um material so'
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
        self.assertEqual(grupo.name, 'Porta Zig-zag')
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

    def test_zigzag_volumes_presos_as_duas_folhas(self):
        conj = self.nicho()
        grupo = addon.portas.porta_no_modulo(conj, folhas=3, abertura='ZIGZAG')
        folhas = addon.portas._folhas_portas(grupo)
        ferragens = addon.ferragens._ferragens_portas(grupo)
        self.assertTrue(any(o.get('cabinet_peca') == 'base' for o in ferragens))
        for i in (1, 2):
            itens = [o for o in ferragens if o.get('porta_ferragem_id', '').startswith('ART_%d_' % i)]
            self.assertTrue(any('Eixo' in o.name for o in itens))
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
                addon.portas.OPCOES_FOLHAS, 1, tamanho, 'Quantas folhas?')
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

    # Regressao (era BUG, corrigido na 302): Esc no arraste da dobradica so'
    # devolvia a margem e perdia o arranjo medido do Promob.
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
        # Regressao v232: minimo de distancia aprovava uma quina so'.
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
                # Quatro vertices cobrem uma area, nao um segmento.
                self.assertGreater((contatos[1] - contatos[0]).cross(contatos[2] - contatos[0]).length, .001)

    def test_braco_angular_segue_o_copo_sem_refazer_malhas(self):
        conj, grupo, suporte = self._canto_135('DIREITA')
        folha, = addon.portas._folhas_portas(grupo)
        bracos = [o for o in addon.ferragens._ferragens_portas(grupo) if 'Braco Angular' in o.name]
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
        # Inclinar ainda mais o apoio refaz o encaixe pela geometria atual.
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
    raise RuntimeError('Falha nos testes de portas')
