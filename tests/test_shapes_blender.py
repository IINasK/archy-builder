"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_shapes_blender.py

Formas de planta (pedido do usuario): o modulo do Promob que nao e' caixa
-- canto em L e diagonal (triangular) -- tem a linha branca da HUD
seguindo a planta; a profundidade de CADA lado (P1/P2) muda sozinha, o
R da diagonal e' editavel e L/P totais esticam sem deformar o
canto. Os modulos saem de DXFs no formato do Promob, como os de verdade.
"""
import math
import os
import sys
import tempfile
import unittest

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon

F = addon.formas


def prisma(contorno, z0, z1, convexo=True):
    """Peca em pe' de um contorno 2D (mm): tampas em leque (convexo) e
    laterais em quadrados -- polyface de ate' 4 vertices, como no DXF."""
    n = len(contorno)
    vs = [(x, y, z0) for x, y in contorno] + [(x, y, z1) for x, y in contorno]
    faces = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    if convexo:
        faces += [(0, i + 1, i) for i in range(1, n - 1)]
        faces += [(n, n + i, n + i + 1) for i in range(1, n - 1)]
    return vs, faces


def faixa(externo, interno, z0, z1):
    """Prisma de uma FAIXA (porta curva): tampas em quadrados entre o
    contorno de fora e o de dentro."""
    vs, faces = prisma(externo + interno[::-1], z0, z1, convexo=False)
    n, m = len(externo) + len(interno), len(externo)
    for i in range(m - 1):
        a, b = i, i + 1
        c, d = n - 1 - (i + 1), n - 1 - i
        faces += [(a, b, c, d), (n + a, n + d, n + c, n + b)]
    return vs, faces


def caixa(x0, y0, z0, x1, y1, z1):
    return prisma([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1)


def arco(cx, cy, raio, de, ate, passos=12):
    return [(cx + raio * math.cos(math.radians(de + (ate - de) * i / passos)),
             cy + raio * math.sin(math.radians(de + (ate - de) * i / passos)))
            for i in range(passos + 1)]


def dxf(pecas, piso=True):
    """[(vertices, faces)] -> caminho de um DXF do Promob (camada = peca)."""
    out = ['0', 'SECTION', '2', 'ENTITIES']
    if piso:
        pecas = [caixa(-2000, -2000, -5, 3000, 3000, 0)] + list(pecas)
    for n, (vertices, faces) in enumerate(pecas):
        camada = 'LAYER%d' % n
        out += ['0', 'POLYLINE', '8', camada, '66', '1', '70', '64']
        for p in vertices:
            out += ['0', 'VERTEX', '8', camada, '10', str(p[0]), '20', str(p[1]),
                    '30', str(p[2]), '70', '192']
        for face in faces:
            out += ['0', 'VERTEX', '8', camada, '10', '0', '20', '0', '30', '0', '70', '128']
            for k, indice in enumerate(face):
                out += ['7%d' % (k + 1), str(indice + 1)]
        out += ['0', 'SEQEND', '8', camada]
    out += ['0', 'ENDSEC', '0', 'EOF']
    caminho = os.path.join(tempfile.mkdtemp(), 'Teste.dxf')
    with open(caminho, 'w', encoding='latin1') as f:
        f.write('\n'.join(out) + '\n')
    return caminho


def importar(pecas):
    modulos, _info = addon.importacao.importar_dxf_promob(
        bpy.context, dxf(pecas), 'Teste', na_origem=True)
    return modulos[0]


def canto_em_l():
    """Canto 900 x 900, bracos de 500 (recorte de 400 na quina de tras
    a direita, x/y maximos), 15 mm, 700 de altura."""
    l_base = [(0, 0), (900, 0), (900, 500), (500, 500), (500, 900), (0, 900)]
    vs, faces = prisma(l_base, 0, 15, convexo=False)
    n = len(l_base)
    faces += [(0, 3, 2, 1), (0, 5, 4, 3), (n, n + 1, n + 2, n + 3), (n, n + 3, n + 4, n + 5)]
    return importar([
        (vs, faces),
        caixa(0, 0, 15, 15, 900, 700),            # lateral esquerda
        caixa(15, 0, 15, 885, 15, 700),           # costas
        caixa(885, 0, 15, 900, 500, 700),         # ponta do braco A
        caixa(0, 885, 15, 500, 900, 700),         # ponta do braco B
        caixa(500, 485, 15, 885, 500, 700),       # face interna do braco A
        caixa(485, 500, 15, 500, 885, 700),       # face interna do braco B
    ])


def canto_diagonal():
    """Canto 900 x 900 com a quina (900, 900) cortada por uma porta
    diagonal: pernas de 350."""
    contorno = [(0, 0), (900, 0), (900, 550), (550, 900), (0, 900)]
    d = Vector((-350, 350)).normalized()
    normal = Vector((d.y, -d.x)) * 15          # para fora
    a, b = Vector((900, 550)), Vector((550, 900))
    porta = [tuple(a), tuple(b), tuple(b - normal), tuple(a - normal)]
    return importar([
        prisma(contorno, 0, 15),
        caixa(0, 0, 15, 15, 900, 700),
        caixa(15, 0, 15, 885, 15, 700),
        caixa(885, 15, 15, 900, 550, 700),
        caixa(15, 885, 15, 550, 900, 700),
        prisma(porta, 15, 700),
    ])


def diagonal_inteira():
    """Modulo 900 x 600 cuja ESQUERDA e' uma diagonal inteira (o print do
    usuario): da quina de tras (0, 600) ate' a frente em x = 400."""
    contorno = [(400, 0), (900, 0), (900, 600), (0, 600)]
    d = Vector((-400, 600)).normalized()
    normal = Vector((-d.y, d.x)) * 15          # para fora (esquerda)
    a, b = Vector((400, 0)), Vector((0, 600))
    lateral = [tuple(a), tuple(b), tuple(b - normal), tuple(a - normal)]
    return importar([
        prisma(contorno, 0, 15),
        caixa(415, 0, 15, 885, 15, 700),          # frente reta
        caixa(885, 0, 15, 900, 600, 700),         # lateral direita
        caixa(30, 585, 15, 885, 600, 700),        # costas
        prisma(lateral, 15, 700),
    ])


def cantoneira_de_ponta():
    """A cantoneira do Promob (print do usuario): 300 x 550, prateleiras
    triangulares que acabam na FACE DE DENTRO da lateral direita de 15 --
    a ponta nao e' afiada, fica a espessura dela (285 a 300)."""
    prateleira = [(285, 0), (285, 535), (0, 535), (0, 299)]
    pecas = [prisma(prateleira, z, z + 15) for z in (3, 346, 688)]
    pecas += [caixa(285, 0, 0, 300, 550, 706),       # lateral direita
              caixa(0, 535, 0, 285, 550, 706)]       # costas
    return importar(pecas)


def cantoneira(com_porta=False):
    """Prateleiras de 300 x 550 com a quina (0, 0) redonda, raio 150;
    lateral e costas do lado oposto."""
    contorno = arco(150, 150, 150, 180, 270) + [(300, 0), (300, 550), (0, 550)]
    pecas = [prisma(contorno, z, z + 15) for z in (0, 340, 685)]
    pecas += [caixa(300, 0, 0, 315, 565, 700), caixa(0, 550, 0, 300, 565, 700)]
    if com_porta:
        pecas.append(faixa(arco(150, 150, 150, 180, 270), arco(150, 150, 135, 180, 270), 15, 685))
    return importar(pecas)


class TestFormas(unittest.TestCase):
    def test_angulo_so_aparece_com_selecao_individual_da_chapa(self):
        conj,pecas=self._perfil_vertical_pequeno('XZ');o=pecas[0]
        for p in bpy.context.selected_objects:p.select_set(False)
        conj.select_set(True)
        for p in pecas:p.select_set(True)
        bpy.context.view_layer.objects.active=conj
        geo=addon.hud._geometria_hud(bpy.context)
        self._conferir_caixa_do_modulo(geo,pecas)
        for p in bpy.context.selected_objects:p.select_set(False)
        o.select_set(True);bpy.context.view_layer.objects.active=o
        geo=addon.hud._geometria_hud(bpy.context)
        self.assertEqual(geo['modo'],'INDIVIDUAL')
        alvo=next(l for l in geo['linhas'] if l.get('angulo'))
        antes=[p.matrix_world@v.co for p in pecas[1:] for v in p.data.vertices]
        addon.hud._aplicar_valor_hud(bpy.context,alvo,90.)
        depois=[p.matrix_world@v.co for p in pecas[1:] for v in p.data.vertices]
        self.assertEqual(antes,depois)

    def test_evento_hud_antigo_nao_edita_angulo_do_modulo(self):
        conj=canto_diagonal();pecas=F._pecas_da_edicao(conj)
        antes={o:([tuple(v.co) for v in o.data.vertices],o.matrix_world.copy()) for o in pecas}
        for face in (('ANG',2,'A'),('JUNTA',0,1,0),('P1',2)):
            alvo=dict(tipo='forma',objeto=conj,modo='GRUPO',face=face)
            with self.assertRaises(ValueError):addon.hud._aplicar_valor_hud(bpy.context,alvo,90.)
        for o,(vs,m) in antes.items():
            self.assertEqual(vs,[tuple(v.co) for v in o.data.vertices]);self.assertEqual(m,o.matrix_world)

    def _geometria_solver_legado(self,conj,plano='XY'):
        pecas=addon.modulos._chapas_do_conjunto(conj)
        cantos,linhas=addon.hud._linhas_da_forma(conj,pecas,F.forma_do_modulo(conj,plano))
        return dict(objeto=conj,modo='GRUPO',chapas=pecas,cantos=cantos,linhas=linhas)

    def _aplicar_solver_legado(self,alvo,valor):
        return F.aplicar_angulo_interno(bpy.context,alvo['objeto'],alvo['face'][1],alvo['face'][2],valor,alvo.get('plano','XY'))

    def _modulo_com_inclinacoes_combinadas(self,trocar=False,inclinar_base=False):
        volumes=[caixa(-300,-150,0,-282,150,400),caixa(282,-150,0,300,360,300)]
        pol=[(-282,-150),(282,-150),(282,360),(-282,150)]
        volumes.append(prisma(pol,0,18))
        vs,fs=prisma(pol,0,18)
        n=Vector((100,0,564)).normalized()
        volumes.append(([(x,y,400-(x+282)*100/564-(18-z)/n.z) for x,y,z in vs],fs))
        pecas=[]
        for vs,fs in volumes:
            if inclinar_base:vs=[(x,y,z-.1*(y+150)) for x,y,z in vs]
            if trocar:vs=[(y,x,z) for x,y,z in vs]
            me=bpy.data.meshes.new('Malha da inclinacao composta')
            me.from_pydata([Vector(v)/1000 for v in vs],[],fs);me.update()
            o=bpy.data.objects.new('Chapa da inclinacao composta',me);bpy.context.scene.collection.objects.link(o)
            bpy.context.view_layer.update();addon.importacao.converter_em_chapa(o);pecas.append(o)
        conj=addon.modulos.agrupar_chapas(bpy.context,pecas,'Nicho com inclinacoes combinadas')
        bpy.context.view_layer.update();F.esquecer()
        return conj,pecas

    def test_inclinacoes_multiplas_usam_caixa_sem_angulo_no_modulo(self):
        from unittest.mock import patch
        for trocar,inclinar in ((False,False),(True,False),(False,True)):
            self.setUp();conj,pecas=self._modulo_com_inclinacoes_combinadas(trocar,inclinar)
            conj.rotation_euler=(.21,-.17,.37);bpy.context.view_layer.update()
            antes={o:([tuple(v.co) for v in o.data.vertices],o.matrix_world.copy()) for o in pecas}
            with patch.object(F,'forma_do_modulo',side_effect=AssertionError('Inferiu forma do grupo')):
                geo=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
            self._conferir_caixa_do_modulo(geo,pecas)
            for o,(vs,m) in antes.items():
                self.assertEqual(vs,[tuple(v.co) for v in o.data.vertices]);self.assertEqual(m,o.matrix_world)


    def test_juntas_com_inclinacao_composta_editam_o_angulo_real_sem_mudar_secao(self):
        for trocar,inclinar in ((False,False),(True,False),(False,True)):
            self.setUp();conj,pecas=self._modulo_com_inclinacoes_combinadas(trocar,inclinar)
            s=1 if trocar else 0;indice=6
            if trocar:indice=5
            antes={o:(o.data,o.chapa_espessura_mm,[o.matrix_world@v.co for v in o.data.vertices]) for o in pecas}
            for t,novo in ((1-s,100.),(2,90.)):
                chave=('JUNTA',s,t,indice);original=F.dados_junta(conj,chave)['angulo']
                for graus in (novo,original):
                    F.aplicar_angulo_junta(bpy.context,conj,chave,graus)
                    self.assertAlmostEqual(F.dados_junta(conj,chave)['angulo'],graus,delta=.02)
                    for o,(me,e,vs) in antes.items():
                        self.assertIs(o.data,me)
                        self.assertAlmostEqual((max(v.co.z for v in me.vertices)-min(v.co.z for v in me.vertices))*1000,e,delta=.002)
                for o,(me,e,vs) in antes.items():
                    self.assertLess(max((o.matrix_world@v.co-p).length for v,p in zip(me.vertices,vs)),.00005)

    def test_inclinacoes_compostas_cacheiam_o_corpo_e_preservam_topologia_em_l(self):
        from unittest.mock import patch
        conj,pecas=self._modulo_com_inclinacoes_combinadas()
        geo=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        with patch.object(F.bmesh,'new',side_effect=AssertionError('Hull no redraw')),patch.object(F,'_planta',side_effect=AssertionError('Mesh no redraw')):
            nova=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        self.assertEqual([l['pontos'] for l in geo['linhas']],[l['pontos'] for l in nova['linhas']])
        self.setUp();conj=canto_em_l();bloco=F.blocagem_do_modulo(conj)
        self.assertIsNotNone(bloco)
        self.assertFalse(F.blocagem_cobre_estrutura(conj,bloco))

    def _modulo_com_teto_inclinado(self,trocar_eixos=False):
        pecas=[]
        volumes=[caixa(0,0,0,15,550,700),caixa(585,0,0,600,550,550),
                 caixa(15,0,0,585,550,15)]
        vs,fs=caixa(15,0,0,585,550,15)
        normal=Vector((150,0,570)).normalized()
        vs=[(x,y,700-(x-15)*150/570-(15-z)/normal.z) for x,y,z in vs]
        volumes.append((vs,fs))
        for vs,fs in volumes:
            if trocar_eixos:vs=[(y,x,z) for x,y,z in vs]
            me=bpy.data.meshes.new('Secao angular preservada')
            me.from_pydata([Vector(v)/1000 for v in vs],[],fs);me.update()
            o=bpy.data.objects.new('Chapa da junta',me);bpy.context.scene.collection.objects.link(o)
            bpy.context.view_layer.update();addon.importacao.converter_em_chapa(o);pecas.append(o)
        conj=addon.modulos.agrupar_chapas(bpy.context,pecas,'Blocagem com laterais assimetricas')
        bpy.context.view_layer.update();F.esquecer()
        return conj,pecas,pecas[-1]

    def test_blocagem_assimetrica_tambem_e_cubo_convencional(self):
        conj,pecas,teto=self._modulo_com_teto_inclinado()
        self._conferir_caixa_do_modulo(addon.hud._geometria_do_item(conj,'GRUPO',pecas),pecas)


    def test_angulo_da_blocagem_preserva_secao_contato_uv_mesh_e_retorno(self):
        for trocar in (False,True):
            self.setUp()
            conj,pecas,teto=self._modulo_com_teto_inclinado(trocar)
            conj.rotation_euler=(.17,-.23,.37);bpy.context.view_layer.update();F.esquecer()
            s=1 if trocar else 0;chave=('JUNTA',s,2,4)
            angulo=F.dados_junta(conj,chave)['angulo']
            referencias={o:(o.data,[tuple(p.vertices) for p in o.data.polygons],
                           [o.matrix_world@v.co for v in o.data.vertices],o.chapa_espessura_mm) for o in pecas}
            uv=teto.data.uv_layers.new(name='UV da secao')
            for i,v in enumerate(uv.data):v.uv=(i/40,i/60)
            original_uv=[tuple(v.uv) for v in uv.data]
            for graus in (90.,angulo,105.,angulo):
                F.aplicar_angulo_junta(bpy.context,conj,chave,graus)
                self.assertAlmostEqual(F.dados_junta(conj,chave)['angulo'],graus,delta=.02)
                for o,(me,fs,ps,e) in referencias.items():
                    self.assertIs(o.data,me)
                    self.assertEqual(fs,[tuple(p.vertices) for p in me.polygons])
                    self.assertAlmostEqual(o.chapa_espessura_mm,e,delta=.001)
                    self.assertAlmostEqual((max(v.co.z for v in me.vertices)-min(v.co.z for v in me.vertices))*1000,e,delta=.001)
                    if graus==angulo:
                        self.assertLess(max((o.matrix_world@v.co-p).length for v,p in zip(me.vertices,ps)),.00005)
                self.assertEqual(original_uv,[tuple(v.uv) for v in teto.data.uv_layers['UV da secao'].data])
                bloco=F.blocagem_do_modulo(conj);inv=F.matriz_do_modulo(conj).inverted()
                for v in teto.data.vertices:
                    p=inv@teto.matrix_world@v.co*1000
                    self.assertLess(min(abs(Vector(n).dot(p)-d) for n,d in bloco['apoios']),.01)

    def test_blocagem_cache_numerico_e_sem_cdt_no_redraw(self):
        from unittest.mock import patch
        conj,pecas,teto=self._modulo_com_teto_inclinado()
        antes=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        with patch.object(F,'_planta',side_effect=AssertionError('Mesh no redraw')),patch.object(F,'_uniao_da_secao',side_effect=AssertionError('CDT no redraw')),patch.object(F.bmesh,'new',side_effect=AssertionError('BMesh no redraw')):
            depois=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        self.assertEqual([l['pontos'] for l in antes['linhas']],[l['pontos'] for l in depois['linhas']])

    def test_junta_em_lateral_inclinada_preserva_espessura_e_angulo_exato(self):
        conj,pecas,teto=self._modulo_com_teto_inclinado()
        for o in (pecas[0],teto):
            inv=o.matrix_world.inverted()
            for v in o.data.vertices:
                p=o.matrix_world@v.co
                if p.x<.1 and p.z>.6:p.x+=.05
                v.co=inv@p
            o.data.update();addon.chapas.absorver_malha_editada(o)
        bpy.context.view_layer.update();F.esquecer()
        chave=('JUNTA',0,2,4);original=F.dados_junta(conj,chave)['angulo']
        espessuras={o:o.chapa_espessura_mm for o in pecas}
        for graus in (90.,original):
            F.aplicar_angulo_junta(bpy.context,conj,chave,graus)
            self.assertAlmostEqual(F.dados_junta(conj,chave)['angulo'],graus,delta=.02)
            for o,e in espessuras.items():
                self.assertAlmostEqual((max(v.co.z for v in o.data.vertices)-min(v.co.z for v in o.data.vertices))*1000,e,delta=.002)

    def test_junta_impossivel_nao_inverte_chapa_nem_desfaz_ultimo_angulo(self):
        conj,pecas,teto=self._modulo_com_teto_inclinado()
        chave=('JUNTA',0,2,4)
        F.aplicar_angulo_junta(bpy.context,conj,chave,90.)
        antes={o:(o.data,[tuple(v.co) for v in o.data.vertices],o.matrix_world.copy()) for o in pecas}
        with self.assertRaises(ValueError):F.aplicar_angulo_junta(bpy.context,conj,chave,5.)
        self.assertAlmostEqual(F.dados_junta(conj,chave)['angulo'],90.,delta=.02)
        for o,(me,vs,m) in antes.items():
            self.assertIs(o.data,me);self.assertEqual(vs,[tuple(v.co) for v in me.vertices]);self.assertEqual(o.matrix_world,m)

    def _modulo_com_frente_curva(self):
        pol=[(0,0),(550,0)]+arco(250,0,300,0,90,16)[1:]+[(0,300)]
        return importar([caixa(0,-15,0,550,0,720),caixa(0,300,0,250,315,720),
                       caixa(-15,-15,0,0,315,720),prisma(pol,705,720),prisma(pol,0,15)])

    def test_blocagem_curva_retangular_sem_diagonal_falsa_nem_mudar_madeira(self):
        conj=self._modulo_com_frente_curva()
        conj.rotation_euler=(.2,-.15,.4);bpy.context.view_layer.update();F.esquecer()
        pecas=F._pecas(conj);antes={o:[tuple(v.co) for v in o.data.vertices] for o in pecas}
        bloco=F.blocagem_do_modulo(conj)
        self.assertEqual(bloco['eixo'],1)
        self.assertEqual(F.planos_curvos(conj),('XY',))
        geo=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        medidas=[l for l in geo['linhas'] if l['tipo']=='medida']
        self.assertEqual(len(medidas),12)
        self.assertFalse(any(l['tipo']=='contorno_porta' for l in geo['linhas']))
        self.assertFalse(any(l.get('angulo') for l in geo['linhas']))
        inv=F.matriz_do_modulo(conj).inverted()
        for l in medidas:
            a,b=l['pontos'];d=b-a
            self.assertEqual(sum(abs(v)>.00001 for v in d),1)
            self.assertTrue(all(abs(d[i])<.00001 for i in range(3) if i!=l['eixo']))
        for o,ps in antes.items():self.assertEqual(ps,[tuple(v.co) for v in o.data.vertices])

    def test_gatilho_curvo_ignora_subdivisoes_quina_l_e_arremate_pequeno(self):
        def detectar(ps):
            return addon.frentes.contorno_tem_curva([(Vector((*a,0)),Vector((*b,0)))
                     for a,b in zip(ps,ps[1:]+ps[:1])])
        diagonal=[(0,0),(600,0)]+[(600-i*20,300+i*20) for i in range(16)]+[(0,600)]
        self.assertFalse(detectar(diagonal))
        self.assertFalse(detectar([(0,0),(600,0),(600,300),(300,300),(300,600),(0,600)]))
        self.assertFalse(detectar(arco(10,10,10,180,270,16)+[(600,0),(600,600),(0,600)]))
        for n in (6,16,64):
            self.assertTrue(detectar(arco(150,150,150,180,270,n)+[(600,0),(600,600),(0,600)]))

    def test_frente_curva_com_teto_inclinado_continua_com_caixa_convencional(self):
        conj=self._modulo_com_frente_curva();pecas=F._pecas(conj)
        inv=F.matriz_do_modulo(conj).inverted()
        for o in pecas:
            m=inv@o.matrix_world;volta=m.inverted()
            for v in o.data.vertices:
                p=m@v.co
                if p.z>.1:p.z-=.2*(p.y+.165)
                v.co=volta@p
            o.data.update();addon.chapas.absorver_malha_editada(o)
        bpy.context.view_layer.update();F.esquecer()
        antes={o:[tuple(v.co) for v in o.data.vertices] for o in pecas}
        self._conferir_caixa_do_modulo(addon.hud._geometria_do_item(conj,'GRUPO',pecas),pecas)
        for o,vs in antes.items():self.assertEqual(vs,[tuple(v.co) for v in o.data.vertices])


    def test_curvatura_da_porta_isolada_nao_muda_referencia_da_carcaca(self):
        conj,pecas,teto=self._modulo_com_teto_inclinado()
        antes=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        vs,fs=faixa(arco(150,0,150,0,90),arco(150,0,135,0,90),15,680)
        me=bpy.data.meshes.new('Madeira da porta curva isolada');me.from_pydata([Vector(v)/1000 for v in vs],[],fs);me.update()
        o=bpy.data.objects.new('Porta curva sem mudar caixa',me);bpy.context.scene.collection.objects.link(o)
        bpy.context.view_layer.update();addon.importacao.converter_em_chapa(o)
        o[addon.chapas.MARCA_FOLHA]=1;o.parent=conj
        bpy.context.view_layer.update();F.esquecer()
        self.assertEqual(F.planos_curvos(conj),())
        depois=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        self.assertEqual([l['pontos'] for l in antes['linhas']],[l['pontos'] for l in depois['linhas']])

    def test_prateleira_curva_direta_no_modulo_nao_troca_o_tipo_da_caixa(self):
        conj,pecas,teto=self._modulo_com_teto_inclinado()
        vs,fs=prisma(arco(150,150,150,180,270)+[(300,0),(300,300),(0,300)],340,355)
        me=bpy.data.meshes.new('Malha da prateleira recortada');me.from_pydata([Vector(v)/1000 for v in vs],[],fs);me.update()
        o=bpy.data.objects.new('Prateleira com recorte arredondado',me);bpy.context.scene.collection.objects.link(o)
        bpy.context.view_layer.update();addon.importacao.converter_em_chapa(o)
        o[addon.prateleiras.MARCA_PRATELEIRA]=1;o.parent=conj
        bpy.context.view_layer.update();F.esquecer()
        self.assertEqual(F.planos_curvos(conj),())
        geo=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        self.assertFalse(any(l.get('angulo') for l in geo['linhas']))

    def test_classificacao_curva_cacheia_e_invalida_apos_tab_e_restauracao(self):
        from unittest.mock import patch
        import bmesh
        conj=self._modulo_com_frente_curva();pecas=F._pecas(conj)
        self.assertEqual(F.planos_curvos(conj),('XY',))
        with patch.object(F,'_detectar_planos_curvos',side_effect=AssertionError('Mesh no redraw')):
            addon.hud._geometria_do_item(conj,'GRUPO',pecas)
            addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        originais={o:([v.co.copy() for v in o.data.vertices],o.matrix_world.copy()) for o in pecas}
        # Trocar o arco pela corda sem mudar IDs/numero de vertices/L/A/P.
        for o in pecas:
            if len(o.data.vertices)<30:continue
            bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
            bpy.ops.object.mode_set(mode='EDIT');addon.chapas.absorver_edicoes_de_malha()
            bm=bmesh.from_edit_mesh(o.data);m=o.matrix_world
            ref=F.matriz_do_modulo(conj);inv=ref.inverted()
            ps=[inv@m@v.co*1000 for v in bm.verts]
            lo=Vector(tuple(min(p[i] for p in ps) for i in range(3)))
            hi=Vector(tuple(max(p[i] for p in ps) for i in range(3)))
            for v in bm.verts:
                local=inv@m@v.co*1000
                if local.x>lo.x+249 and lo.y+.01<local.y<hi.y-.01:
                    local.x=hi.x-(local.y-lo.y)
                    v.co=m.inverted()@(ref@(local/1000))
            bmesh.update_edit_mesh(o.data)
            bpy.ops.object.mode_set(mode='OBJECT');addon.chapas.absorver_edicoes_de_malha()
        self.assertEqual(F.planos_curvos(conj),())
        for o,(ps,m) in originais.items():
            for v,p in zip(o.data.vertices,ps):v.co=p
            o.matrix_world=m
            o.data.update()
        bpy.context.view_layer.update()
        addon.eventos._esquecer_referencias()
        self.assertEqual(F.planos_curvos(conj),('XY',))

    def test_contorno_curvo_modelado_nao_cria_parametro_radial(self):
        conj=cantoneira(com_porta=True)
        pecas=F._pecas(conj)
        antes={o:(o.data,[tuple(v.co) for v in o.data.vertices],o.matrix_world.copy()) for o in pecas}
        self.assertIsNone(F.forma_do_modulo(conj))
        geo=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        self.assertFalse(any(l.get('face')==('R',0) for l in geo['linhas']))
        self.assertEqual(len([l for l in geo['linhas'] if l['tipo']=='medida']),12)
        for o,(malha,vs,m) in antes.items():
            self.assertIs(o.data,malha)
            self.assertEqual(vs,[tuple(v.co) for v in o.data.vertices])
            self.assertEqual(m,o.matrix_world)

    def test_perfil_reto_valida_todos_os_cantos_da_caixa(self):
        forma=dict(lo=Vector((0,0,0)),hi=Vector((600,600,700)),cantos=[
            None,None,dict(tipo='CHANFRO',a=200,b=200),None])
        boa=[(0,0),(600,0),(600,400),(400,600),(0,600)]
        fora=[(0,0),(600,0),(600,600),(0,600)]
        self.assertTrue(F._perfil_contem_pecas(forma,[boa],15))
        self.assertFalse(F._perfil_contem_pecas(forma,[fora],15))

    def test_perfil_arredondado_nao_inventa_diagonal_entre_pontas(self):
        pol=arco(150,150,150,180,270,16)+[(300,0),(300,550),(0,550)]
        lo,hi=Vector((0,0,0)),Vector((300,550,700))
        self.assertIsNone(F._feicao([pol],lo,hi,0))
        pol[0]=(20,150);pol[16]=(150,20)
        self.assertIsNone(F._feicao([pol],lo,hi,0))

    def test_resize_pelo_campo_recupera_referencia_se_perfil_some_no_limite(self):
        from unittest.mock import patch
        conj=canto_diagonal()
        pecas=F._pecas_da_edicao(conj)
        antes={o:[o.matrix_world@v.co for v in o.data.vertices] for o in pecas}
        largura=conj.conj_largura_mm
        conj.conj_largura_mm=100
        bpy.context.view_layer.update()
        original=F.forma_do_modulo;chamadas=[]
        def detectar(*args,**kwargs):
            chamadas.append(1)
            return None if len(chamadas)==1 else original(*args,**kwargs)
        with patch.object(F,'forma_do_modulo',side_effect=detectar):
            conj.conj_largura_mm=largura
        bpy.context.view_layer.update()
        self.assertAlmostEqual(conj.conj_largura_mm,largura,delta=.01)
        for o,ps in antes.items():
            self.assertLess(max((o.matrix_world@v.co-p).length for v,p in zip(o.data.vertices,ps)),.00005,o.name)

    def _armario_inclinado_em_dois_planos(self):
        pecas=[]
        volumes=[caixa(-300,-275,0,-285,275,720),
                 caixa(285,-275,0,300,275,720),
                 caixa(-285,-275,83,285,275,98),
                 caixa(-285,-235,394,285,254,409),
                 caixa(-285,-275,705,285,-205,720),
                 caixa(-285,205,705,285,275,720)]
        for indice,(vs,fs) in enumerate(volumes):
            # Mesmo estado da cena: cantos superiores movidos em dois
            # planos; prateleiras internas ainda guardam a forma anterior.
            novos=[]
            for x,y,z in vs:
                if indice in (0,1,4,5) and z>700:
                    if x>0:x-=135.738
                    if y>0:y-=144.81
                novos.append((x,y,z))
            malha=bpy.data.meshes.new('Malha inclinada em dois planos')
            malha.from_pydata([Vector(v)/1000 for v in novos],[],fs);malha.update()
            o=bpy.data.objects.new('Chapa inclinada em dois planos',malha)
            bpy.context.scene.collection.objects.link(o)
            bpy.context.view_layer.update()
            addon.importacao.converter_em_chapa(o);pecas.append(o)
        conj=addon.modulos.agrupar_chapas(bpy.context,pecas,'Modulo inclinado em dois planos')
        bpy.context.view_layer.update()
        return conj,pecas

    # Regressao (era BUG, corrigido na 258): chapa reta nao vira arco.
    def test_inclinacao_composta_nao_inventa_curva_nem_diagonal_sem_apoio(self):
        conj,pecas=self._armario_inclinado_em_dois_planos()
        for plano in ('XY','XZ','YZ'):
            self.assertIsNone(F.forma_do_modulo(conj,plano),plano)
        geo=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        self.assertEqual(len([l for l in geo['linhas'] if l['tipo']=='medida']),12)
        self.assertFalse(any(l.get('face',('',))[0]=='ANG' for l in geo['linhas']))

    def test_curva_com_base_elevada_usa_arestas_nativas_sem_arco_aproximado(self):
        from unittest.mock import patch
        conj=cantoneira()
        pecas=F._pecas(conj)
        base=min(pecas,key=lambda o:o.matrix_world.translation.z)
        base.location.z+=.083
        bpy.context.view_layer.update();F.esquecer()
        antes={o:(o.data,[tuple(v.co) for v in o.data.vertices],o.matrix_world.copy()) for o in pecas}
        geo=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        self.assertEqual(len([l for l in geo['linhas'] if l['tipo']=='medida']),12)
        self.assertFalse(any(l['tipo']=='forma' for l in geo['linhas']))
        with patch.object(F,'_planta',side_effect=AssertionError('Leu malha no redraw')),patch.object(F,'_uniao_da_secao',side_effect=AssertionError('CDT no redraw')):
            nova=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
            self.assertEqual([l['pontos'] for l in geo['linhas']],[l['pontos'] for l in nova['linhas']])
        for o,(malha,vs,m) in antes.items():
            self.assertIs(o.data,malha)
            self.assertEqual(vs,[tuple(v.co) for v in o.data.vertices])
            self.assertEqual(m,o.matrix_world)

    def test_contorno_ignora_diagonais_coplanares_com_normais_invertidas(self):
        conj,pecas=self._armario_inclinado_em_dois_planos()
        o=pecas[2]
        vertices=[v.co.copy() for v in o.data.vertices]
        faces=[]
        for f in o.data.polygons:
            if len(f.vertices)==4:
                a,b,c,d=f.vertices
                faces.extend(((a,b,c),(a,d,c)))
            else:faces.append(tuple(f.vertices))
        o.data.clear_geometry();o.data.from_pydata(vertices,[],faces);o.data.update()
        F.esquecer()
        estrutura=F.estrutura_hud(conj)
        inv=o.matrix_world.inverted()@F.matriz_do_modulo(conj)
        contorno=[e for e in estrutura if e['referencia'][0]==o['chapa_uid']]
        self.assertTrue(contorno)
        for e in contorno:
            a,b=[inv@(Vector(e[k])/1000) for k in ('a','b')]
            # Caixa: cada aresta real varia em apenas um eixo. A diagonal
            # de triangulos opostos e' coplanar, apesar do sinal da normal.
            self.assertEqual(sum(abs(x)>.00001 for x in b-a),1)

    def _armario_livre_por_tab(self):
        import bmesh
        pecas=[]
        volumes=[caixa(0,65,0,15,615,703),caixa(1230,65,0,1245,615,703),
                 caixa(615,65,15,630,105,691),caixa(695,0,3,710,50,703),
                 caixa(612,50,0,1248,65,706),caixa(15,65,0,1230,615,15),
                 caixa(15,65,691,1230,135,706),caixa(15,545,691,1230,615,706),
                 caixa(15,105,345,1230,591,360)]
        for vs,faces in volumes:
            malha=bpy.data.meshes.new('Chapa para Tab livre')
            malha.from_pydata([Vector(v)/1000 for v in vs],[],faces);malha.update()
            o=bpy.data.objects.new('Chapa para Tab livre',malha)
            bpy.context.scene.collection.objects.link(o)
            bpy.context.view_layer.update()
            addon.importacao.converter_em_chapa(o);pecas.append(o)
        conj=addon.modulos.agrupar_chapas(bpy.context,pecas,'Canto livre editado')
        for o in bpy.context.selected_objects:o.select_set(False)
        conj.select_set(True);bpy.context.view_layer.objects.active=conj
        # A HUD ja' mediu o armario antes do Tab: reproduz cache existente.
        addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        self.assertIn('FINISHED',bpy.ops.object.cabinet_editar_grupo())
        addon.chapas.absorver_edicoes_de_malha()
        bpy.context.scene.tool_settings.mesh_select_mode=(True,False,False)
        bpy.ops.mesh.select_all(action='DESELECT')
        for o in bpy.context.objects_in_mode_unique_data:
            bm=bmesh.from_edit_mesh(o.data)
            for v in bm.verts:
                p=o.matrix_world@v.co
                v.select_set(p.x>1. and p.y>.2)
            bm.select_flush_mode();bmesh.update_edit_mesh(o.data)
        self.assertIn('FINISHED',bpy.ops.transform.translate(value=(0,-.3,0),orient_type='GLOBAL'))
        self.assertIn('FINISHED',bpy.ops.object.cabinet_editar_grupo())
        addon.chapas.absorver_edicoes_de_malha()
        bpy.context.view_layer.update()
        return conj,pecas

    def _conferir_caixa_do_modulo(self,geo,pecas):
        self.assertEqual(len(geo['cantos']),8)
        self.assertEqual(len(geo['linhas']),12)
        self.assertEqual({l['letra'] for l in geo['linhas']},{'L','P','A'})
        self.assertTrue(all(l['tipo']=='medida' and not l.get('angulo') for l in geo['linhas']))
        lo=Vector(tuple(min(p[i] for p in geo['cantos']) for i in range(3)))
        hi=Vector(tuple(max(p[i] for p in geo['cantos']) for i in range(3)))
        self.assertEqual(len({tuple(p) for p in geo['cantos']}),8)
        for linha in geo['linhas']:
            d=linha['pontos'][1]-linha['pontos'][0]
            self.assertTrue(all(abs(d[i])<1e-7 for i in range(3) if i!=linha['eixo']))
        for o in pecas:
            for v in o.data.vertices:
                ponto=o.matrix_world@v.co
                self.assertTrue(all(lo[i]-.00001<=ponto[i]<=hi[i]+.00001 for i in range(3)))


    # Regressao (era BUG, corrigido na 257): Tab/G deixava caixa no vazio.
    def test_tab_g_tab_formato_livre_grade_sobre_arestas_nativas(self):
        conj,pecas=self._armario_livre_por_tab()
        self.assertIsNone(F.forma_do_modulo(conj))
        self.assertEqual(bpy.context.mode,'OBJECT')
        self.assertEqual(bpy.context.object,conj)
        geo=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        self._conferir_caixa_do_modulo(geo,pecas)
        # Esquecer e recalcular deve produzir exatamente o mesmo contorno.
        F.esquecer()
        nova=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        self.assertEqual([l['pontos'] for l in geo['linhas']],[l['pontos'] for l in nova['linhas']])

    def test_grade_livre_e_leitura_sem_mesh_cdt_bmesh_no_redesenho(self):
        from unittest.mock import patch
        conj,pecas=self._armario_livre_por_tab()
        material=bpy.data.materials.new('Material do contorno livre')
        pecas[0].data.materials.append(material);pecas[0].data.uv_layers.new(name='UV preservada')
        antes={o:(o.data,[tuple(v.co) for v in o.data.vertices],[tuple(p.vertices) for p in o.data.polygons],o.matrix_world.copy()) for o in pecas}
        uvs={o:[(camada.name,[tuple(l.uv) for l in camada.data])
                for camada in o.data.uv_layers] for o in pecas}
        geo=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        with patch.object(F,'_planta',side_effect=AssertionError('Leu Mesh no redraw')),patch.object(F,'_uniao_da_secao',side_effect=AssertionError('CDT no redraw')),patch.object(F.bmesh,'new',side_effect=AssertionError('BMesh no redraw')):
            for _ in range(3):
                nova=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
                self.assertEqual(len(geo['linhas']),len(nova['linhas']))
        for o,(malha,vs,fs,m) in antes.items():
            self.assertIs(o.data,malha)
            self.assertEqual(vs,[tuple(v.co) for v in o.data.vertices])
            self.assertEqual(fs,[tuple(p.vertices) for p in o.data.polygons])
            self.assertEqual(m,o.matrix_world)
            self.assertEqual(uvs[o],[(camada.name,[tuple(l.uv) for l in camada.data])
                                    for camada in o.data.uv_layers])
        self.assertEqual(pecas[0].data.materials[0],material)
        # O Tab ja' criou o mapa metrico; o mapa do usuario pode ser o segundo.
        self.assertIn('UV preservada',pecas[0].data.uv_layers)

    def test_grade_livre_grupo_girado_segue_a_geometria(self):
        conj,pecas=self._armario_livre_por_tab()
        conj.rotation_euler=(.2,-.31,.43)
        bpy.context.view_layer.update()
        geo=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        self._conferir_caixa_do_modulo(geo,pecas)

    def test_uniao_nativa_preserva_concavidade_ilhas_furos_e_sobreposicao(self):
        l=[(0,0),(100,0),(100,40),(40,40),(40,100),(0,100)]
        quad=lambda x,y,w,h:[(x,y),(x+w,y),(x+w,y+h),(x,y+h)]
        casos=[([l],6400),([l[::-1]],6400),
               ([quad(0,0,100,100),quad(50,0,100,100)],15000),
               ([quad(0,0,100,100),quad(200,0,100,100)],20000),
               ([quad(0,0,100,20),quad(0,80,100,20),quad(0,20,20,60),quad(80,20,20,60)],6400)]
        for poligonos,esperada in casos:
            bordas,area=F._uniao_da_secao(poligonos)
            self.assertTrue(bordas)
            self.assertAlmostEqual(area,esperada,delta=.01)
        bordas,_area=F._uniao_da_secao(casos[-1][0])
        for a,b in bordas:
            m=(a+b)/2
            self.assertFalse(20.01<m.x<79.99 and 20.01<m.y<79.99)

    def test_grade_livre_medida_arraste_esc_e_seta_continuam_ativas(self):
        from unittest.mock import patch
        conj,pecas=self._armario_livre_por_tab()
        h=addon.hud;geo=h._geometria_do_item(conj,'GRUPO',pecas)
        alvo=next(dict(l,lado='min') for l in geo['linhas'] if l['tipo']=='medida' and l['eixo']==0)
        inicial=h._valor_hud(alvo)
        copia=h._estado_arraste_hud(bpy.context,alvo)
        h._aplicar_valor_hud(bpy.context,alvo,inicial+100)
        self.assertAlmostEqual(conj.conj_largura_mm,inicial+100,delta=.01)
        geo=h._geometria_do_item(conj,'GRUPO',pecas)
        self._conferir_caixa_do_modulo(geo,pecas)
        # A identidade geometrica da aresta deve sobreviver a L/A/P.
        self.assertTrue(any(h._identidade_hud(l)==h._identidade_hud(alvo) for l in geo['linhas']))
        with patch.object(h,'gpu'),patch.object(h,'batch_for_shader'),patch.object(h,'_projetar_hud',side_effect=lambda _c,p:p.xy*1000),patch.object(h,'_triangulos_seta_hud',return_value=[]) as seta:
            h._desenhar_seta_hud(bpy.context,alvo,geo)
            seta.assert_called_once()
        h._restaurar_arraste_hud(bpy.context,copia)
        self.assertAlmostEqual(h._valor_hud(alvo),inicial,delta=.01)
        self._conferir_caixa_do_modulo(h._geometria_do_item(conj,'GRUPO',pecas),pecas)

    def _diagonal_vertical(self,plano):
        conj,tampo,fundo,_alvo,pontos,angulo=self._diagonal_perna_35_com_fundo_dependente()
        m=conj.matrix_world.copy()
        transporte=m@F._base_do_plano(plano)@m.inverted()
        poses={o:transporte@o.matrix_world for o in conj.children_recursive}
        for o,pose in poses.items():
            o.matrix_world=pose
            bpy.context.view_layer.update()
        F.esquecer()
        geometria=self._geometria_solver_legado(conj,plano)
        alvo=next(l for l in geometria['linhas'] if l.get('plano')==plano and l.get('face')==('ANG',3,'B'))
        return conj,tampo,fundo,alvo,pontos,angulo

    # Regressao (era BUG, corrigido na 256): o solver nao se limita a XY.
    def test_solver_legado_inclinacao_vertical_xz_yz_90_exato_fundo_e_retorno(self):
        for plano in ('XZ','YZ'):
            with self.subTest(plano=plano):
                self.setUp()
                conj,tampo,fundo,alvo,_pontos,angulo=self._diagonal_vertical(plano)
                conj.rotation_euler=(.31,.2,-.42)
                bpy.context.view_layer.update()
                from mathutils import Matrix
                centro=fundo.matrix_world.translation.copy()
                eixo=F.matriz_do_modulo(conj,plano).to_3x3().col[2]
                fundo.matrix_world=(Matrix.Translation(centro)@Matrix.Rotation(.002,4,eixo)
                                    @Matrix.Translation(-centro)@fundo.matrix_world)
                bpy.context.view_layer.update()
                original=angulo()
                pecas=F._pecas_da_edicao(conj)
                antes={o:[o.matrix_world@v.co for v in o.data.vertices] for o in pecas}
                espessuras={o:o.chapa_espessura_mm for o in pecas}
                pintura=bpy.data.materials.new('Pintura vertical')
                fundo.data.materials.append(pintura)
                fundo.data.uv_layers.new(name='UV vertical')
                uv=[tuple(v.uv) for v in fundo.data.uv_layers.active.data]
                faces=[tuple(p.vertices) for p in fundo.data.polygons]
                for _ in range(2):
                    self._aplicar_solver_legado(alvo,90.)
                    self.assertAlmostEqual(angulo(),90.,delta=.01)
                    self.assertAlmostEqual(addon.hud._valor_hud(alvo),90.,delta=.01)
                    self.assertGreater(max((fundo.matrix_world@v.co-p).length for v,p in zip(fundo.data.vertices,antes[fundo])),.001)
                    for o in pecas:
                        self.assertAlmostEqual(o.chapa_espessura_mm,espessuras[o],delta=.001)
                        self.assertTrue(all(abs(s-1)<1e-6 for s in o.scale))
                    self.assertEqual(faces,[tuple(p.vertices) for p in fundo.data.polygons])
                    self.assertEqual(uv,[tuple(v.uv) for v in fundo.data.uv_layers.active.data])
                    self.assertEqual(fundo.data.materials[-1],pintura)
                    self._aplicar_solver_legado(alvo,original)
                    self.assertAlmostEqual(angulo(),original,delta=.01)
                    for o,ps in antes.items():
                        self.assertLess(max((o.matrix_world@v.co-p).length for v,p in zip(o.data.vertices,ps)),.00005,o.name)


    def test_inclinacoes_em_planos_diferentes_tem_referencias_independentes(self):
        conj,_tampo,_fundo,alvo,_pontos,angulo=self._diagonal_vertical('YZ')
        original=angulo()
        F.aplicar_angulo_interno(bpy.context,conj,3,'B',90.,'YZ')
        self.assertIsNotNone(F.forma_do_modulo(conj,'YZ'))
        self.assertTrue(any(o.data.attributes.get(F._atributo_angular('YZ')) for o in F._pecas(conj)))
        self.assertFalse(any(o.data.attributes.get(F.ATR_ANGULO) for o in F._pecas(conj)))
        self.assertEqual(alvo['plano'],'YZ')
        del conj[F.CHAVE_EDICAO]
        # Uma referencia nova pode partir da chapa retangular: nao
        # transformar o trapezio de volta em caixa depois da deformacao.
        F.aplicar_angulo_interno(bpy.context,conj,3,'B',original,'YZ')
        self.assertAlmostEqual(angulo(),original,delta=.01)

    def test_solver_legado_hud_vertical_reutiliza_cache_e_esc_restaura(self):
        from unittest.mock import patch
        conj,_tampo,_fundo,alvo,_pontos,angulo=self._diagonal_vertical('XZ')
        antes=angulo()
        copia=addon.hud._estado_arraste_hud(bpy.context,alvo)
        with patch.object(F,'_planta',side_effect=AssertionError('Malha varrida no redesenho')):
            for _ in range(3):
                addon.hud._geometria_do_item(conj,'GRUPO',addon.modulos._chapas_do_conjunto(conj))
                self.assertAlmostEqual(addon.hud._valor_hud(alvo),antes,delta=.01)
        self._aplicar_solver_legado(alvo,90.)
        addon.hud._restaurar_arraste_hud(bpy.context,copia)
        self.assertAlmostEqual(angulo(),antes,delta=.01)
        self.assertAlmostEqual(addon.hud._valor_hud(alvo),antes,delta=.01)


    def _perfil_vertical_pequeno(self,plano):
        from mathutils import Matrix
        pecas=[]
        for z in (0,300):
            vs,faces=prisma([(0,0),(400,0),(400,700),(3,700)],z,z+15)
            malha=bpy.data.meshes.new('Perfil vertical pequeno')
            malha.from_pydata([Vector(v)/1000 for v in vs],[],faces)
            malha.update()
            o=bpy.data.objects.new('Chapa inclinacao pequena',malha)
            bpy.context.scene.collection.objects.link(o)
            o.matrix_world=F._base_do_plano(plano)
            bpy.context.view_layer.update()
            addon.importacao.converter_em_chapa(o)
            pecas.append(o)
        conj=addon.modulos.agrupar_chapas(bpy.context,pecas,'Perfil vertical')
        bpy.context.view_layer.update()
        F.esquecer()
        return conj,pecas

    def test_vertical_detecta_inclinacao_menor_que_folga_da_planta(self):
        for plano in ('XZ','YZ'):
            with self.subTest(plano=plano):
                self.setUp()
                conj,_pecas=self._perfil_vertical_pequeno(plano)
                forma=F.forma_do_modulo(conj,plano)
                self.assertIsNotNone(forma)
                self.assertAlmostEqual(F.dados_angulo_da_ponta(forma,3,'B')[0],90-math.degrees(math.atan2(3,700)),delta=.001)
                if plano=='XZ':
                    geo=addon.hud._geometria_do_item(conj,'GRUPO',_pecas)
                    normais=[l for l in geo['linhas'] if l['tipo']=='medida' and l['eixo']==1]
                    eixo=F.matriz_do_modulo(conj).to_3x3().col[1]
                    self.assertTrue(normais)
                    for l in normais:self.assertGreater((l['pontos'][1]-l['pontos'][0]).dot(eixo),0)
                    antes=min((o.matrix_world@v.co).dot(eixo) for o in _pecas for v in o.data.vertices)
                    alvo=dict(normais[0],lado='min')
                    addon.hud._aplicar_valor_hud(bpy.context,alvo,conj.conj_profundidade_mm+20)
                    depois=min((o.matrix_world@v.co).dot(eixo) for o in _pecas for v in o.data.vertices)
                    self.assertAlmostEqual(antes,depois,delta=.00001)
                F.aplicar_angulo_interno(bpy.context,conj,3,'B',90.,plano)
                self.assertAlmostEqual(F.dados_angulo_da_ponta(F.forma_do_modulo(conj,plano),3,'B')[0],90.,delta=.01)

    def test_cotas_angulares_da_chapa_individual_usam_seu_plano_real(self):
        conj,pecas=self._perfil_vertical_pequeno('YZ');chapa=pecas[0]
        geo=addon.hud._geometria_do_item(chapa,'INDIVIDUAL',[chapa])
        self.assertTrue(any(l.get('angulo') for l in geo['linhas']))
        for linha in geo['linhas']:
            if linha.get('angulo'):continue
            for p in linha['pontos']:
                hit,q,_n,_i=chapa.closest_point_on_mesh(chapa.matrix_world.inverted()@p)
                self.assertTrue(hit);self.assertLess((chapa.matrix_world@q-p).length,.00003)


    def test_chapa_vertical_individual_isola_malha_compartilhada(self):
        conj,pecas=self._perfil_vertical_pequeno('XZ')
        o=pecas[0]
        copia=o.copy();copia.data=o.data
        bpy.context.scene.collection.objects.link(copia)
        copia.location+=Vector((2,0,0))
        bpy.context.view_layer.update()
        outras={p:[p.matrix_world@v.co for v in p.data.vertices] for p in (pecas[1],copia)}
        original=[o.matrix_world@v.co for v in o.data.vertices]
        geo=addon.hud._geometria_do_item(o,'INDIVIDUAL',[o])
        alvo=next(l for l in geo['linhas'] if l.get('angulo') and l['face'][2]=='B')
        valor=addon.hud._valor_hud(alvo)
        addon.hud._aplicar_valor_hud(bpy.context,alvo,90.)
        self.assertIsNot(o.data,copia.data)
        self.assertAlmostEqual(addon.hud._valor_hud(alvo),90.,delta=.01)
        for p,ps in outras.items():
            self.assertLess(max((p.matrix_world@v.co-q).length for v,q in zip(p.data.vertices,ps)),1e-6)
        addon.hud._aplicar_valor_hud(bpy.context,alvo,valor)
        self.assertLess(max((o.matrix_world@v.co-q).length for v,q in zip(o.data.vertices,original)),.00005)

    def test_tab_invalida_perfil_vertical_sem_mudar_caixa_ou_topologia(self):
        import bmesh
        conj,pecas=self._perfil_vertical_pequeno('YZ')
        forma=F.forma_do_modulo(conj,'YZ')
        antes=F.dados_angulo_da_ponta(forma,3,'B')[0]
        # Editar as duas laterais sem alterar seus extremos L/A/E.
        for o in pecas:
            for p in bpy.context.selected_objects:p.select_set(False)
            o.select_set(True);bpy.context.view_layer.objects.active=o
            bpy.ops.object.mode_set(mode='EDIT')
            addon.chapas.absorver_edicoes_de_malha()
            bm=bmesh.from_edit_mesh(o.data)
            inv=F.matriz_do_modulo(conj,'YZ').inverted()
            m=inv@o.matrix_world
            d=m.to_3x3().inverted()@Vector((.003,0,0))
            pts=[m@v.co*1000 for v in bm.verts]
            xmin=min(p.x for p in pts);ymax=max(p.y for p in pts)
            for v,p in zip(bm.verts,pts):
                if p.x<xmin+10 and p.y>ymax-1:v.co+=d
            bmesh.update_edit_mesh(o.data)
            bpy.ops.object.mode_set(mode='OBJECT')
            addon.chapas.absorver_edicoes_de_malha()
        nova=F.forma_do_modulo(conj,'YZ')
        self.assertIsNot(nova,forma)
        self.assertAlmostEqual(F.dados_angulo_da_ponta(nova,3,'B')[0],90-math.degrees(math.atan2(6,700)),delta=.001)
        self.assertGreater(abs(F.dados_angulo_da_ponta(nova,3,'B')[0]-antes),.2)

    def test_referencia_vertical_sobrevive_a_anexar_com_nomes_duplicados(self):
        conj,pecas=self._perfil_vertical_pequeno('YZ')
        original=F.dados_angulo_da_ponta(F.forma_do_modulo(conj,'YZ'),3,'B')[0]
        antes={o['chapa_uid']:[conj.matrix_world.inverted()@o.matrix_world@v.co for v in o.data.vertices] for o in pecas}
        F.aplicar_angulo_interno(bpy.context,conj,3,'B',90.,'YZ')
        with tempfile.TemporaryDirectory() as pasta:
            caminho=os.path.join(pasta,'Perfil vertical.blend')
            bpy.data.libraries.write(caminho,{conj,*conj.children_recursive})
            with bpy.data.libraries.load(caminho,link=False) as (de,para):
                para.objects=de.objects
            novos=[o for o in para.objects if o is not None]
            for o in novos:bpy.context.scene.collection.objects.link(o)
            copia=next(o for o in novos if addon.chapas.MARCA_CONJUNTO in o)
            bpy.context.view_layer.update()
            self.assertNotEqual(copia.name,conj.name)
            F.aplicar_angulo_interno(bpy.context,copia,3,'B',original,'YZ')
            self.assertAlmostEqual(F.dados_angulo_da_ponta(F.forma_do_modulo(copia,'YZ'),3,'B')[0],original,delta=.01)
            self.assertAlmostEqual(F.dados_angulo_da_ponta(F.forma_do_modulo(conj,'YZ'),3,'B')[0],90.,delta=.01)
            # A origem foi recentrada; comparar a peca em MUNDO remove
            # essa compensacao usando a pose inicial gravada no solver.
            inicio=F._matriz_gravada(copia[F.CHAVE_EDICAO]['inicio'])
            for o in F._pecas(copia):
                atuais=[inicio.inverted()@o.matrix_world@v.co for v in o.data.vertices]
                self.assertLess(max((a-b).length for a,b in zip(atuais,antes[o['chapa_uid']])),.00005)

    def test_seta_vertical_usa_aresta_atual_sem_indices_da_caixa(self):
        from unittest.mock import patch
        conj,pecas=self._perfil_vertical_pequeno('XZ')
        h=addon.hud
        geo=h._geometria_do_item(conj,'GRUPO',pecas)
        linha=next(l for l in geo['linhas'] if l['tipo']=='medida' and l['eixo']==1)
        alvo=dict(linha,lado='min')
        projetar=lambda _c,p:Vector((p.y*1000,p.z*1000))
        for _ in range(2):
            atual=next(l for l in geo['linhas'] if h._identidade_hud(l)==h._identidade_hud(alvo) and l.get('cantos')==alvo.get('cantos'))
            # Uma lista de quinas diferente nao muda a aresta da seta.
            # O alvo conserva os pontos anteriores durante o arraste.
            geo['cantos']=[Vector((99,99,99))]*20
            for lado in ('min','max'):
                alvo['lado']=lado
                with patch.object(h,'gpu'),patch.object(h,'batch_for_shader'),patch.object(h,'_projetar_hud',side_effect=projetar),patch.object(h,'_triangulos_seta_hud',return_value=[]) as seta:
                    h._desenhar_seta_hud(bpy.context,alvo,geo)
                    seta.assert_called_once()
                    esperado=atual['pontos'] if lado=='min' else atual['pontos'][::-1]
                    self.assertLess((seta.call_args.args[0]-projetar(None,esperado[0])).length,.001)
                    self.assertLess((seta.call_args.args[1]-projetar(None,esperado[1])).length,.001)
            h._aplicar_valor_hud(bpy.context,dict(alvo,lado='min'),conj.conj_profundidade_mm+20)
            geo=h._geometria_do_item(conj,'GRUPO',pecas)

    def _diagonal_perna_35_com_fundo_dependente(self):
        from mathutils import Matrix
        contorno = [(0,0),(500,0),(600,100),(600,600),(270,600),(0,565)]
        objetos = []
        def peca(nome, vertices_faces):
            vertices, faces = vertices_faces
            malha = bpy.data.meshes.new(nome)
            malha.from_pydata([Vector(v)/1000 for v in vertices], [], faces)
            malha.update()
            obj = bpy.data.objects.new(nome, malha)
            bpy.context.scene.collection.objects.link(obj)
            bpy.context.view_layer.update()
            addon.importacao.converter_em_chapa(obj)
            objetos.append(obj)
            return obj
        peca('Base dois chanfros', prisma(contorno,0,15))
        tampo = peca('Tampo dois chanfros', prisma(contorno,685,700))
        peca('Lateral esquerda', caixa(0,0,15,15,550,685))
        peca('Lateral direita', caixa(585,115,15,600,600,685))
        peca('Frente reta', caixa(15,0,15,485,15,685))
        peca('Costas retas', caixa(285,585,15,585,600,685))
        conj = addon.modulos.agrupar_chapas(bpy.context, objetos, 'Diagonal perna 35')
        # A chapa de 5 mm acompanha o apoio, mas nao define o envelope.
        a,b = Vector((0,565)),Vector((270,600))
        direcao = (b-a).normalized()
        normal = Vector((-direcao.y,direcao.x))
        a += direcao*20
        b -= direcao*20
        perfil = [tuple(a-normal*15),tuple(b-normal*15),
                  tuple(b-normal*20),tuple(a-normal*20)]
        fundo = peca('Fundo obliquo dependente', prisma(perfil,15,685))
        fundo[addon.chapas.MARCA_FUNDO] = True
        mundo = fundo.matrix_world.copy()
        fundo.parent = conj
        fundo.matrix_parent_inverse = Matrix.Identity(4)
        fundo.matrix_world = mundo
        bpy.context.view_layer.update()
        addon.modulos.guardar_formato_fundo(conj, fundo)
        F.esquecer()
        # Nomes de pontos apenas na fixture; nenhum indice persistido no asset.
        alvos = ((270,600,700),(0,565,700),(0,0,700))
        indices = [min(range(len(tampo.data.vertices)),
                       key=lambda i:(tampo.matrix_world@tampo.data.vertices[i].co-Vector(p)/1000).length)
                   for p in alvos]
        def pontos_topo():
            bpy.context.view_layer.update()
            return [tampo.matrix_world@tampo.data.vertices[i].co for i in indices]
        def angulo_nativo():
            pa,pb,vizinho = pontos_topo()
            u,v = pa-pb,vizinho-pb
            return math.degrees(math.atan2(u.cross(v).length,u.dot(v)))
        geometria = self._geometria_solver_legado(conj)
        alvo, = [l for l in geometria['linhas'] if l.get('face')==('ANG',3,'B')]
        self.assertAlmostEqual(angulo_nativo(),90+math.degrees(math.atan2(35,270)),delta=.001)
        self.assertAlmostEqual(addon.hud._valor_hud(alvo),angulo_nativo(),delta=.001)
        return conj,tampo,fundo,alvo,pontos_topo,angulo_nativo

    # Regressao (era BUG, corrigido na 255): 90 interno sem perna minima.
    def test_solver_legado_hud_angulo_interno_90_na_perna_35_retorna_sem_acumulo(self):
        conj,tampo,fundo,alvo,pontos_topo,angulo = self._diagonal_perna_35_com_fundo_dependente()
        original = angulo()
        pecas = addon.modulos._chapas_do_conjunto(conj)
        antes = {o:[o.matrix_world@v.co for v in o.data.vertices] for o in pecas}
        for _ in range(2):
            self._aplicar_solver_legado(alvo,90.)
            # Aos 90 o chanfro/arco pode desaparecer; a Mesh continua medivel.
            self.assertAlmostEqual(angulo(),90.,delta=.01)
            self._aplicar_solver_legado(alvo,original)
            self.assertAlmostEqual(angulo(),original,delta=.01)
            for obj,pontos in antes.items():
                self.assertEqual(len(obj.data.vertices),len(pontos))
                atuais = [obj.matrix_world@v.co for v in obj.data.vertices]
                self.assertLess(max((a-b).length for a,b in zip(pontos,atuais)),.00005,obj.name)


    # Regressao (era BUG, corrigido na 255): fundo segue o apoio sem perder E.
    def test_solver_legado_fundo_obliquo_acompanha_angulo_90_preserva_espessura_e_retorna(self):
        conj,tampo,fundo,alvo,pontos_topo,angulo = self._diagonal_perna_35_com_fundo_dependente()
        original = angulo()
        antes = [fundo.matrix_world@v.co for v in fundo.data.vertices]
        pose = fundo.matrix_world.copy()
        material_base = bpy.data.materials.new('Fundo base independente')
        pintura = bpy.data.materials.new('Pintura fundo independente')
        fundo.data.materials.clear()
        fundo.data.materials.append(material_base)
        fundo.material_slots[0].link = 'OBJECT'
        fundo.material_slots[0].material = pintura
        def conferir_fundo():
            self.assertNotIn(fundo,F._pecas(conj))
            self.assertNotIn(fundo,addon.modulos._estruturais(addon.modulos._chapas_do_conjunto(conj)))
            self.assertIn(fundo,F._pecas_da_edicao(conj))
            self.assertIs(fundo.data.materials[0],material_base)
            self.assertEqual(fundo.material_slots[0].link,'OBJECT')
            self.assertIs(fundo.material_slots[0].material,pintura)
            pa,pb,_ = pontos_topo()
            tangente = (pa-pb).normalized()
            cima = F.matriz_do_modulo(conj).to_3x3().col[2].normalized()
            normal = cima.cross(tangente).normalized()
            pontos = [fundo.matrix_world@v.co for v in fundo.data.vertices]
            distancias = [(p-pb).dot(normal) for p in pontos]
            self.assertAlmostEqual(max(distancias)-min(distancias),.005,delta=.00005)
            self.assertAlmostEqual(abs(sum(distancias)/len(distancias)),.0175,delta=.00005)
            self.assertAlmostEqual(fundo.chapa_espessura_mm,5.,delta=.001)
            self.assertGreater(abs(fundo.matrix_world.to_3x3().col[2].normalized().dot(normal)),.99999)
            for escala in fundo.scale:
                self.assertAlmostEqual(escala,1.,delta=1e-6)
            return pontos
        conferir_fundo()
        for _ in range(2):
            self._aplicar_solver_legado(alvo,90.)
            depois = conferir_fundo()
            self.assertGreater(max((a-b).length for a,b in zip(antes,depois)),.001)
            self._aplicar_solver_legado(alvo,original)
            pontos = conferir_fundo()
            self.assertLess(max((a-b).length for a,b in zip(antes,pontos)),.00005)
            for a,b in zip(pose,fundo.matrix_world):
                self.assertLess((a-b).length,1e-5)


    # Regressao (era BUG, corrigido na 255): fundo cabe no apoio e nos canais.
    def test_solver_legado_fundo_alongado_por_tab_cabe_no_apoio_mais_canais_sem_acumulo(self):
        import bmesh
        conj,tampo,fundo,alvo,pontos_topo,angulo = self._diagonal_perna_35_com_fundo_dependente()
        original = angulo()
        pa,pb,_ = pontos_topo()
        tangente = (pa-pb).normalized()
        pontos = [fundo.matrix_world@v.co for v in fundo.data.vertices]
        centro = sum(pontos,Vector())/len(pontos)
        medidas = [(p-centro).dot(tangente) for p in pontos]
        fator = (pa-pb).length*1.32/(max(medidas)-min(medidas))
        bm=bmesh.new()
        try:
            bm.from_mesh(fundo.data)
            bmesh.ops.subdivide_edges(bm,edges=list(bm.edges),cuts=1,use_grid_fill=True)
            bm.to_mesh(fundo.data)
        finally:bm.free()
        fundo.data.update()
        uv = fundo.data.uv_layers.new(name='UV fundo alongado')
        for i,dado in enumerate(uv.data):dado.uv=((i%4)/3.,(i//4)/6.)
        pintura = bpy.data.materials.new('Pintura fundo alongado')
        fundo.data.materials.clear();fundo.data.materials.append(pintura)
        fundo.material_slots[0].link='OBJECT';fundo.material_slots[0].material=pintura
        for o in bpy.context.selected_objects:o.select_set(False)
        fundo.select_set(True);bpy.context.view_layer.objects.active=fundo
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            bm=bmesh.from_edit_mesh(fundo.data)
            inversa=fundo.matrix_world.inverted()
            for v in bm.verts:
                p=fundo.matrix_world@v.co
                # Tambem descentra a chapa: limitar so' o comprimento nao basta.
                v.co=inversa@(p+tangente*((p-centro).dot(tangente)*(fator-1)+.025))
            bmesh.update_edit_mesh(fundo.data)
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        addon.chapas.absorver_malha_editada(fundo)
        F.esquecer()
        uvs=[tuple(d.uv) for d in fundo.data.uv_layers['UV fundo alongado'].data]
        faces=[tuple(f.vertices) for f in fundo.data.polygons]
        espessura=fundo.chapa_espessura_mm
        antes=[fundo.matrix_world@v.co for v in fundo.data.vertices]
        extensao=max(p.dot(tangente) for p in antes)-min(p.dot(tangente) for p in antes)
        self.assertGreater(extensao,(pa-pb).length+.014)
        estados={}
        for pedido in (95.,90.,original,95.,90.,original):
            self._aplicar_solver_legado(alvo,pedido)
            self.assertAlmostEqual(angulo(),pedido,delta=.01)
            pa,pb,_=pontos_topo();direcao=(pa-pb).normalized();apoio=(pa-pb).length
            cima=F.matriz_do_modulo(conj).to_3x3().col[2].normalized()
            normal=cima.cross(direcao).normalized()
            atuais=[fundo.matrix_world@v.co for v in fundo.data.vertices]
            limites=[(p-pb).dot(direcao) for p in atuais]
            # Planos reais das pontas: permite 7 mm no canal de cada lateral.
            self.assertGreaterEqual(min(limites),-.007-.00005)
            self.assertLessEqual(max(limites),apoio+.007+.00005)
            self.assertAlmostEqual(max(limites)-min(limites),apoio+.014,delta=.00005)
            distancias=[p.dot(normal) for p in atuais]
            self.assertAlmostEqual((max(distancias)-min(distancias))*1000,espessura,delta=.001)
            self.assertAlmostEqual(fundo.chapa_espessura_mm,espessura,delta=.001)
            self.assertEqual([tuple(d.uv) for d in fundo.data.uv_layers['UV fundo alongado'].data],uvs)
            self.assertEqual([tuple(f.vertices) for f in fundo.data.polygons],faces)
            self.assertEqual(fundo.material_slots[0].link,'OBJECT')
            self.assertIs(fundo.material_slots[0].material,pintura)
            if pedido in estados:
                self.assertLess(max((p-q).length for p,q in zip(estados[pedido],atuais)),.00005)
            else:estados[pedido]=atuais
        salvo=next(d['malha'] for d in conj[F.CHAVE_EDICAO]['pecas'].values() if d['objeto']==fundo)
        self.assertEqual([tuple(f.vertices) for f in salvo.polygons],faces)
        self.assertGreater(max(max(v.co[i] for v in salvo.vertices)-min(v.co[i] for v in salvo.vertices)
                               for i in (0,1)),.35)


    # Regressao (era BUG, corrigido na 255): EDGE conserva a medida real apos Tab.
    def test_solver_legado_hud_angulo_real_apos_tab_com_vizinho_obliquo(self):
        import bmesh
        conj,tampo,fundo,alvo,pontos_topo,angulo = self._diagonal_perna_35_com_fundo_dependente()
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        conj.select_set(True)
        bpy.context.view_layer.objects.active = conj
        bpy.ops.object.cabinet_editar_grupo()
        for obj in bpy.context.objects_in_mode_unique_data:
            bm = bmesh.from_edit_mesh(obj.data)
            inversa = obj.matrix_world.inverted()
            for vertice in bm.verts:
                mundo = obj.matrix_world@vertice.co
                if mundo.x < .020001 and mundo.y < .565:
                    mundo.x += .04*(1-mundo.y/.565)
                    vertice.co = inversa@mundo
            bmesh.update_edit_mesh(obj.data)
        bpy.ops.object.cabinet_editar_grupo()
        addon.eventos.verificar_periodicamente()
        original = angulo()
        # A aresta vizinha real gira, embora os limites X/Y continuem iguais.
        self.assertGreater(abs(original-(90+math.degrees(math.atan2(35,270)))),1.)
        geometria = self._geometria_solver_legado(conj)
        alvo, = [l for l in geometria['linhas'] if l.get('face')==('ANG',3,'B')]
        self.assertAlmostEqual(addon.hud._valor_hud(alvo),original,delta=.01)
        antes = [tampo.matrix_world@v.co for v in tampo.data.vertices]
        for pedido in (95.,90.,original,95.,original):
            try:
                self._aplicar_solver_legado(alvo,pedido)
            except ValueError as erro:
                self.fail('Pedido %.6f apos Tab (original %.6f): %s' % (pedido,original,erro))
            self.assertAlmostEqual(angulo(),pedido,delta=.01)
        atuais = [tampo.matrix_world@v.co for v in tampo.data.vertices]
        self.assertEqual(len(antes),len(atuais))
        self.assertLess(max((a-b).length for a,b in zip(antes,atuais)),.00005)


    # Regressao (era BUG, corrigido na 255): rebase conserva E real sem arredondar.
    def test_rebase_fundo_inclinado_preserva_mundo_mesh_uv_material_e_filho(self):
        import bmesh
        from mathutils import Matrix
        for girar_xy in (0.,.37):
            with self.subTest(rotacao_xy=girar_xy):
                bm = bmesh.new()
                try:
                    bmesh.ops.create_cube(bm,size=1.)
                    inclinacao = Matrix.Rotation(girar_xy,3,'Z')
                    for v in bm.verts:
                        x,y = v.co.x*.284,v.co.y*.687
                        z = -.17629/.284*x+v.co.z*.006
                        v.co = inclinacao@Vector((x,y,z))
                    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
                    malha = bpy.data.meshes.new('Fundo local obliquo teste')
                    bm.to_mesh(malha)
                finally:
                    bm.free()
                malha.update()
                uv = malha.uv_layers.new(name='UV preservada')
                for i,dado in enumerate(uv.data):
                    dado.uv = ((i%4)/3.,(i//4)/6.)
                obj = bpy.data.objects.new('Fundo real 182 de envelope',malha)
                bpy.context.scene.collection.objects.link(obj)
                obj[addon.chapas.MARCA_CHAPA] = True
                obj[addon.chapas.MARCA_FUNDO] = True
                obj.matrix_world = Matrix.Translation((1.1,-.7,.4))@Matrix.Rotation(.43,4,'Z')
                addon.chapas._ocupado[0] = True
                try:
                    obj.chapa_largura_mm = 284.
                    obj.chapa_comprimento_mm = 687.
                    obj.chapa_espessura_mm = 182.29
                finally:
                    addon.chapas._ocupado[0] = False
                material = bpy.data.materials.new('Pintura rebase fundo')
                malha.materials.append(material)
                obj.material_slots[0].link = 'OBJECT'
                obj.material_slots[0].material = material
                filho = bpy.data.objects.new('Parafuso referencia de mundo',None)
                bpy.context.scene.collection.objects.link(filho)
                filho.parent = obj
                filho.matrix_world = Matrix.Translation((1.2,-.65,.51))
                bpy.context.view_layer.update()
                mundo = [obj.matrix_world@v.co for v in malha.vertices]
                pose_filho = filho.matrix_world.copy()
                faces = [tuple(f.vertices) for f in malha.polygons]
                arestas = [tuple(e.vertices) for e in malha.edges]
                uvs = [tuple(d.uv) for d in uv.data]
                normal = max(malha.polygons,key=lambda f:f.area).normal.copy()
                planos = [v.co.dot(normal) for v in malha.vertices]
                espessura = max(planos)-min(planos)
                self.assertLess(espessura,.006)
                self.assertGreater(espessura,.005)
                addon.chapas.absorver_malha_editada(obj)
                bpy.context.view_layer.update()
                self.assertAlmostEqual(obj.chapa_espessura_mm,espessura*1000,delta=.001)
                self.assertIs(obj.data,malha)
                self.assertEqual([tuple(f.vertices) for f in malha.polygons],faces)
                self.assertEqual([tuple(e.vertices) for e in malha.edges],arestas)
                self.assertEqual([tuple(d.uv) for d in malha.uv_layers['UV preservada'].data],uvs)
                atuais = [obj.matrix_world@v.co for v in malha.vertices]
                self.assertLess(max((a-b).length for a,b in zip(mundo,atuais)),1e-6)
                for a,b in zip(pose_filho,filho.matrix_world):
                    self.assertLess((a-b).length,1e-6)
                self.assertEqual(obj.material_slots[0].link,'OBJECT')
                self.assertIs(obj.material_slots[0].material,material)
                zs = [v.co.z for v in malha.vertices]
                self.assertAlmostEqual(max(zs)-min(zs),espessura,delta=1e-6)
                for escala in obj.scale:
                    self.assertAlmostEqual(escala,1.,delta=1e-6)

    # Regressao (era BUG, corrigido na 255): rebase sincroniza todos os usuarios.
    def test_rebase_mesh_compartilhada_preserva_usuarios_pais_filhos_uv_e_materiais(self):
        import bmesh
        from mathutils import Matrix
        bm = bmesh.new()
        try:
            bmesh.ops.create_cube(bm,size=1.)
            for v in bm.verts:
                x,y = v.co.x*.284,v.co.y*.687
                v.co = Vector((x,y,-.17629/.284*x+v.co.z*.006)) + Vector((.031,-.047,.023))
            bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
            malha = bpy.data.meshes.new('Fundo obliquo compartilhado fora do centro')
            bm.to_mesh(malha)
        finally:
            bm.free()
        malha.update()
        uv = malha.uv_layers.new(name='UV compartilhada')
        for i,dado in enumerate(uv.data):
            dado.uv = ((i%4)/3.,(i//4)/6.)
        fornecedor = bpy.data.materials.new('Material DATA compartilhado')
        malha.materials.append(fornecedor)
        obj = bpy.data.objects.new('Instancia fundo A',malha)
        bpy.context.scene.collection.objects.link(obj)
        obj[addon.chapas.MARCA_CHAPA] = True
        obj[addon.chapas.MARCA_FUNDO] = True
        addon.chapas._ocupado[0] = True
        try:
            obj.chapa_largura_mm = 284.
            obj.chapa_comprimento_mm = 687.
            obj.chapa_espessura_mm = 182.29
        finally:
            addon.chapas._ocupado[0] = False
        clone = obj.copy()
        clone.name = 'Instancia fundo B'
        bpy.context.scene.collection.objects.link(clone)
        usuarios = [obj,clone]
        filhos,pais,pinturas = [],[],[]
        for i,o in enumerate(usuarios):
            pai = bpy.data.objects.new('Pai distinto fundo %d'%i,None)
            bpy.context.scene.collection.objects.link(pai)
            pai.matrix_world = Matrix.Translation((i*1.4,-i*.8,.2+i*.3))@Matrix.Rotation(.3+i*.7,4,'Z')
            o.parent = pai
            o.matrix_parent_inverse = Matrix.Identity(4)
            o.matrix_basis = Matrix.Translation((.2,-.1,.35))@Matrix.Rotation(.2+i*.4,4,'X')
            pintura = bpy.data.materials.new('Pintura individual fundo %d'%i)
            o.material_slots[0].link = 'OBJECT'
            o.material_slots[0].material = pintura
            filho = bpy.data.objects.new('Filho individual fundo %d'%i,None)
            bpy.context.scene.collection.objects.link(filho)
            filho.parent = o
            filho.matrix_basis = Matrix.Translation((.06,.08,.12))
            pais.append(pai);filhos.append(filho);pinturas.append(pintura)
        bpy.context.view_layer.update()
        mundos = [[o.matrix_world@v.co for v in malha.vertices] for o in usuarios]
        poses = {o:o.matrix_world.copy() for o in pais+filhos}
        uvs = [tuple(d.uv) for d in malha.uv_layers['UV compartilhada'].data]
        faces = [tuple(f.vertices) for f in malha.polygons]
        arestas = [tuple(e.vertices) for e in malha.edges]
        normal = max(malha.polygons,key=lambda f:f.area).normal.copy()
        planos = [v.co.dot(normal) for v in malha.vertices]
        espessura = (max(planos)-min(planos))*1000
        normais = [(o.matrix_world.to_3x3()@normal).normalized() for o in usuarios]
        self.assertTrue(addon.chapas.absorver_malha_editada(obj))
        bpy.context.view_layer.update()
        tamanho = Vector([max(v.co[i] for v in malha.vertices)-min(v.co[i] for v in malha.vertices)
                          for i in range(3)])*1000
        for i,o in enumerate(usuarios):
            self.assertIs(o.parent,pais[i])
            self.assertIs(o.data,malha)
            self.assertLess(max((a-o.matrix_world@v.co).length for a,v in zip(mundos[i],malha.vertices)),1e-6)
            self.assertAlmostEqual(o.chapa_largura_mm,tamanho.x,delta=.001)
            self.assertAlmostEqual(o.chapa_comprimento_mm,tamanho.y,delta=.001)
            self.assertAlmostEqual(o.chapa_espessura_mm,espessura,delta=.001)
            self.assertGreater(abs(o.matrix_world.to_3x3().col[2].normalized().dot(normais[i])),.999999)
            self.assertEqual(o.material_slots[0].link,'OBJECT')
            self.assertIs(o.material_slots[0].material,pinturas[i])
            self.assertLess((o.scale-Vector((1,1,1))).length,1e-6)
        for o,pose in poses.items():
            for a,b in zip(pose,o.matrix_world):self.assertLess((a-b).length,1e-6)
        self.assertEqual([tuple(d.uv) for d in malha.uv_layers['UV compartilhada'].data],uvs)
        self.assertEqual([tuple(f.vertices) for f in malha.polygons],faces)
        self.assertEqual([tuple(e.vertices) for e in malha.edges],arestas)
        self.assertIs(malha.materials[0],fornecedor)
        centro = Vector([(min(v.co[i] for v in malha.vertices)+max(v.co[i] for v in malha.vertices))/2
                         for i in range(3)])
        self.assertLess(centro.length,1e-7)
        self.assertFalse(addon.chapas.absorver_malha_editada(clone))

    def test_espessura_dos_apoios_nao_cria_angulos_no_grupo(self):
        pol=[(285,15),(285,535),(15,535),(15,299)]
        conj=importar([prisma(pol,z,z+15) for z in (0,340,685)]+[
            caixa(285,0,0,300,550,700),caixa(0,299,0,15,550,700),caixa(15,535,0,285,550,700)])
        pecas=addon.modulos._chapas_do_conjunto(conj)
        self._conferir_caixa_do_modulo(addon.hud._geometria_do_item(conj,'GRUPO',pecas),pecas)
        o=next(o for o in pecas if F.forma_do_modulo(o) is not None)
        self.assertTrue(any(l.get('angulo') for l in addon.hud._geometria_do_item(o,'INDIVIDUAL',[o])['linhas']))


    def test_tab_diagonal_sem_editar_preserva_planta_e_contorno_do_grupo(self):
        conj = cantoneira_de_ponta()
        for o in bpy.context.selected_objects:
            o.select_set(False)
        conj.select_set(True)
        bpy.context.view_layer.objects.active = conj
        antes = F.forma_do_modulo(conj)
        pontos = {o: [o.matrix_world @ v.co for v in o.data.vertices] for o in F._pecas(conj)}
        bpy.ops.object.cabinet_editar_grupo()
        addon.eventos.verificar_periodicamente()
        bpy.ops.object.cabinet_editar_grupo()
        addon.eventos.verificar_periodicamente()
        depois = F.forma_do_modulo(conj)
        self.assertEqual(F.contorno(antes), F.contorno(depois))
        self.assertEqual([(o, m) for o, m, _ in addon.hud._itens_da_selecao(bpy.context)], [(conj, 'GRUPO')])
        for o, ps in pontos.items():
            self.assertLess(max((p-o.matrix_world @ v.co).length for p, v in zip(ps, o.data.vertices)), 1e-6)

    def test_portas_e_gaveta_no_outro_braco_acompanham_a_quina_interna(self):
        from mathutils import Matrix
        conj=canto_em_l();P=addon.portas;G=addon.gavetas
        params=P._parametros_portas_da_cena(bpy.context.scene,numerico=True)
        params.update(abertura='GIRO',folhas=1,dobradica='RETA',folga_mm=0,
                      espessura_mm=15,lateral_mm=15)
        rotacoes=[Matrix(((-1,0,0),(0,0,1),(0,1,0))).transposed(),
                  Matrix(((0,1,0),(0,0,1),(1,0,0))).transposed()]
        origens=[Vector((435,50,15)),Vector((50,65,15))]
        portas=[]
        for r,o in zip(rotacoes,origens):
            m=r.to_4x4();m.translation=o/1000
            p=P._aplicar_portas(bpy.context,None,m,conj,370,670,params,frente='NEG_Y',largura_em='X')
            p[P.CHAVE_MODULO_PORTA]=conj.name;p[P.CHAVE_FOLGAS_PORTA]=(1,1,1,1)
            P.gravar_vao_orientado(p,conj)
            portas.append(p)
        # O problema real: uma face nao tem nenhuma ancora perto.
        for k in list(portas[0].keys()):
            if k.startswith('porta_vao_apoio_'):del portas[0][k]
        ref=Matrix(((0,1,0),(-1,0,0),(0,0,1))).transposed()
        margens=G.margens_do_vao(conj,Vector((50,65,685))/1000,Vector((50,435,15))/1000,ref)
        gavetas=G.criar_gavetas(bpy.context,conj,margens,dict(quantidade=3,profundidade_mm=500),ref)
        f=P._folhas_portas(portas[0])[0];addon.ferragens._definir_abertura(bpy.context,f,.4)
        F.aplicar(bpy.context,conj,('P1',2),400)
        self.assertAlmostEqual(portas[0].matrix_world.translation.y,-.05,delta=.001)
        self.assertAlmostEqual(portas[1]['porta_vao_largura_mm'],470,delta=.1)
        self.assertAlmostEqual(gavetas[G.CHAVE_VAO][0],470,delta=.1)
        self.assertAlmostEqual(gavetas.matrix_world.translation.y,-.035,delta=.001)
        self.assertAlmostEqual(f[addon.ferragens.CHAVE_ABERTURA],.4,places=4)
        F.aplicar(bpy.context,conj,('P1',2),500)
        self.assertAlmostEqual(portas[1]['porta_vao_largura_mm'],370,delta=.1)
        self.assertAlmostEqual(gavetas[G.CHAVE_VAO][0],370,delta=.1)

    def test_gaveta_diagonal_gira_pelo_par_de_extremidades(self):
        from mathutils import Matrix
        conj=canto_diagonal();G=addon.gavetas
        x=Vector((-1,1,0)).normalized();z=Vector((0,0,1));y=z.cross(x)
        ref=Matrix((x,y,z)).transposed()
        a=Vector((435,85,685))/1000;b=Vector((85,435,15))/1000
        margens=G.margens_do_vao(conj,a,b,ref)
        grupo=G.criar_gavetas(bpy.context,conj,margens,dict(quantidade=3,profundidade_mm=450),ref)
        antes=grupo.matrix_world.to_3x3().col[0].normalized()
        backup=addon.hud._estado_arraste_hud(bpy.context,dict(objeto=conj,tipo='forma',face=('P1',2)))
        F.aplicar(bpy.context,conj,('P1',2),450)
        depois=grupo.matrix_world.to_3x3().col[0].normalized()
        self.assertGreater(antes.angle(depois),math.radians(2))
        self.assertGreater(G.referencia(grupo).col[0].dot(conj.matrix_world.to_3x3().inverted() @ depois),.999)
        addon.hud._restaurar_arraste_hud(bpy.context,backup)
        self.assertGreater(G.referencia(grupo).col[0].dot(antes),.999)
        F.aplicar(bpy.context,conj,('P1',2),450)
        F.aplicar(bpy.context,conj,('P1',2),550)
        self.assertGreater(antes.dot(grupo.matrix_world.to_3x3().col[0].normalized()),.999)

    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        F.esquecer()

    def medidas(self, conj):
        forma = F.forma_do_modulo(conj)
        return {s['chave']: round(F.valor(conj, s['chave']), 1)
                for s in F.segmentos(forma) if s['chave']}

    def espessuras(self, conj):
        return sorted({round(c.chapa_espessura_mm, 2)
                       for c in addon.modulos._chapas_do_conjunto(conj)})

    def test_canto_em_l_e_reconhecido_pela_planta(self):
        conj = canto_em_l()
        forma = F.forma_do_modulo(conj)
        self.assertIsNotNone(forma)
        tipos = [f and f['tipo'] for f in forma['cantos']]
        self.assertEqual(tipos, [None, None, 'RECORTE', None])
        self.assertAlmostEqual(forma['cantos'][2]['a'], 400.0, delta=0.5)
        self.assertAlmostEqual(forma['cantos'][2]['b'], 400.0, delta=0.5)
        m = self.medidas(conj)
        self.assertEqual(m[('L',)], 900.0)
        self.assertEqual(m[('P',)], 900.0)
        self.assertEqual(m[('P1', 2)], 500.0)      # profundidade do braco A
        self.assertEqual(m[('P2', 2)], 500.0)      # do braco B

    def test_caixa_comum_nao_tem_forma(self):
        conj = importar([caixa(0, 0, 0, 15, 550, 700), caixa(585, 0, 0, 600, 550, 700),
                         caixa(15, 0, 0, 585, 550, 15), caixa(15, 535, 15, 585, 550, 700)])
        self.assertIsNone(F.forma_do_modulo(conj))
        geometria = addon.hud._geometria_do_item(conj, 'GRUPO',
                                                 addon.modulos._chapas_do_conjunto(conj))
        self.assertFalse(any(l['tipo'] in ('forma', 'contorno_forma')
                             for l in geometria['linhas']))

    def test_profundidade_de_cada_lado_muda_sozinha(self):
        conj = canto_em_l()
        F.aplicar(bpy.context, conj, ('P1', 2), 650.0)
        m = self.medidas(conj)
        self.assertEqual(m[('P1', 2)], 650.0)
        self.assertEqual(m[('P2', 2)], 500.0)      # o outro braco nao mexe
        self.assertEqual((m[('L',)], m[('P',)]), (900.0, 900.0))
        # a face interna do braco A so' andou (inteira); a do B encurtou
        medidas = sorted(sorted((round(c.chapa_largura_mm), round(c.chapa_comprimento_mm)))
                         for c in addon.modulos._chapas_do_conjunto(conj))
        self.assertIn([385, 685], medidas)
        self.assertIn([235, 685], medidas)
        F.aplicar(bpy.context, conj, ('P2', 2), 420.0)
        m = self.medidas(conj)
        self.assertEqual((m[('P1', 2)], m[('P2', 2)]), (650.0, 420.0))
        self.assertEqual(self.espessuras(conj), [15.0])

    def test_total_estica_sem_mudar_os_bracos(self):
        conj = canto_em_l()
        F.aplicar(bpy.context, conj, ('L',), 1100.0, 'min')
        m = self.medidas(conj)
        self.assertEqual(m[('L',)], 1100.0)
        self.assertEqual((m[('P1', 2)], m[('P2', 2)]), (500.0, 500.0))
        F.aplicar(bpy.context, conj, ('P',), 1000.0, 'max')
        m = self.medidas(conj)
        self.assertEqual(m[('P',)], 1000.0)
        self.assertEqual((m[('P1', 2)], m[('P2', 2)]), (500.0, 500.0))
        self.assertEqual(self.espessuras(conj), [15.0])

    def test_diagonal_gira_e_estica_com_o_lado(self):
        conj = canto_diagonal()
        forma = F.forma_do_modulo(conj)
        self.assertEqual(forma['cantos'][2]['tipo'], 'CHANFRO')
        self.assertAlmostEqual(F.valor(conj, ('R', 2)), 350.0, delta=2.0)
        def eixo(c):
            v = c.matrix_world.to_3x3().col[0].normalized()
            return Vector((v.x, v.y)).normalized() if v.xy.length > 1e-6 else Vector((1.0, 0.0))
        porta = max(addon.modulos._chapas_do_conjunto(conj),
                    key=lambda c: abs(eixo(c).x * eixo(c).y))
        antes = eixo(porta)
        F.aplicar(bpy.context, conj, ('P1', 2), 650.0)
        m = self.medidas(conj)
        self.assertAlmostEqual(m[('P1', 2)], 650.0, delta=1.0)
        self.assertAlmostEqual(m[('P2', 2)], 550.0, delta=1.0)
        # a porta GIROU (ponta foi junto com o lado) e continua 15 mm
        self.assertGreater(abs(eixo(porta).angle_signed(antes)), math.radians(5))
        self.assertEqual(self.espessuras(conj), [15.0])
        self.assertTrue(addon.chapas._malha_e_caixa(porta.data))
        # R deixa as duas pernas iguais
        F.aplicar(bpy.context, conj, ('R', 2), 300.0)
        f = F.forma_do_modulo(conj)['cantos'][2]
        self.assertAlmostEqual(f['a'], 300.0, delta=2.0)
        self.assertAlmostEqual(f['b'], 300.0, delta=2.0)

    def test_menu_modulo_nao_oferece_formato_nem_aceita_evento_angular_antigo(self):
        for criar in (canto_diagonal,canto_em_l):
            self.setUp();conj=criar()
            for o in bpy.context.selected_objects:o.select_set(False)
            conj.select_set(True);bpy.context.view_layer.objects.active=conj
            bpy.context.scene.cabinet_aba='MODULOS'
            acoes=[v[5] for v in addon.gaveta._widgets_gaveta(bpy.context,480,1400) if v[5]]
            self.assertFalse(any(a[0]=='medida' and a[1]=='forma' for a in acoes))
            self.assertFalse(any(a[0]=='contador' and a[1].startswith('forma_') for a in acoes))
            antes={o:[tuple(v.co) for v in o.data.vertices] for o in F._pecas(conj)}
            self.assertTrue(addon.gaveta_eventos.aplicar_medida(bpy.context,'forma',conj.name,'P1:2',.6))
            self.assertTrue(addon.gaveta_eventos._aplicar_contador(bpy.context,('contador','forma_angulo_2',40,5,85,conj.name),40))
            for o,vs in antes.items():self.assertEqual(vs,[tuple(v.co) for v in o.data.vertices])


    def test_comando_radial_antigo_nao_deforma_blocagem(self):
        conj=cantoneira(com_porta=True)
        pecas=F._pecas(conj)
        antes={o:(o.data,[tuple(v.co) for v in o.data.vertices],o.matrix_world.copy()) for o in pecas}
        for raio in (220.,2000.):
            F.aplicar(bpy.context,conj,('R',0),raio)
        for o,(malha,vs,m) in antes.items():
            self.assertIs(o.data,malha)
            self.assertEqual(vs,[tuple(v.co) for v in o.data.vertices])
            self.assertEqual(m,o.matrix_world)
        for o in bpy.context.selected_objects:o.select_set(False)
        conj.select_set(True);bpy.context.view_layer.objects.active=conj
        acoes=[v[5] for v in addon.gaveta._widgets_gaveta(bpy.context,480,1400) if v[5]]
        self.assertFalse(any(a[0]=='medida' and a[1]=='forma' for a in acoes))

    def test_hud_do_l_so_oferece_caixa_e_redimensionamento_convencional(self):
        from unittest.mock import patch
        conj=canto_em_l();pecas=addon.modulos._chapas_do_conjunto(conj)
        geo=addon.hud._geometria_do_item(conj,'GRUPO',pecas)
        self._conferir_caixa_do_modulo(geo,pecas)
        alvo=dict(next(l for l in geo['linhas'] if l['eixo']==0),lado='min')
        inicial=addon.hud._valor_hud(alvo)
        with patch.object(F,'aplicar',side_effect=AssertionError('Usou deformacao angular do grupo')):
            addon.hud._aplicar_valor_hud(bpy.context,alvo,inicial+100)
        self.assertAlmostEqual(addon.hud._valor_hud(alvo),inicial+100,delta=.01)
        self._conferir_caixa_do_modulo(addon.hud._geometria_do_item(conj,'GRUPO',pecas),pecas)


    def test_diagonal_inteira_so_mostra_angulos_na_chapa_individual(self):
        conj=diagonal_inteira();pecas=addon.modulos._chapas_do_conjunto(conj)
        self._conferir_caixa_do_modulo(addon.hud._geometria_do_item(conj,'GRUPO',pecas),pecas)
        chapa=next(o for o in pecas if F.forma_do_modulo(o) is not None)
        geo=addon.hud._geometria_do_item(chapa,'INDIVIDUAL',[chapa])
        self.assertTrue(any(l.get('angulo') for l in geo['linhas']))
        self.assertTrue(all(l['objeto']==chapa for l in geo['linhas']))


    def test_cantoneira_com_apoio_na_espessura_usa_caixa_no_grupo(self):
        conj=cantoneira_de_ponta();pecas=addon.modulos._chapas_do_conjunto(conj)
        forma=F.forma_do_modulo(conj);f=forma['cantos'][0]
        self.assertAlmostEqual(f['a'],285.,delta=1.5)
        self.assertAlmostEqual(f['b'],299.,delta=1.5)
        self._conferir_caixa_do_modulo(addon.hud._geometria_do_item(conj,'GRUPO',pecas),pecas)


    def test_rotulos_da_forma_aparecem(self):
        conj = cantoneira()
        geometria = addon.hud._geometria_do_item(conj, 'GRUPO',
                                                 addon.modulos._chapas_do_conjunto(conj))
        self.assertFalse(any(l.get('letra') == 'R' for l in geometria['linhas']))
        medidas=[l for l in geometria['linhas'] if l['tipo']=='medida']
        self.assertTrue({'L','P','A'} <= {l.get('letra') for l in medidas})
        self.assertTrue(all(len(l['pontos'])==2 for l in medidas))

    def test_cache_segue_a_geometria(self):
        conj = canto_em_l()
        primeira = F.forma_do_modulo(conj)
        self.assertIs(F.forma_do_modulo(conj), primeira)
        F.aplicar(bpy.context, conj, ('P1', 2), 600.0)
        self.assertIsNot(F.forma_do_modulo(conj), primeira)

    def test_encolher_a_100_e_devolver_nao_acumula_deformacao(self):
        # Regressao: a faixa da frente alcancava as costas e trocava os
        # vertices que se moviam no retorno. Verificar coordenadas reais.
        for criar in (canto_em_l, canto_diagonal):
            conj=criar()
            pecas=addon.modulos._chapas_do_conjunto(conj)
            antes={o:[o.matrix_world @ v.co for v in o.data.vertices] for o in pecas}
            for chave in (('P1',2),('P2',2)):
                original=F.valor(conj,chave)
                for _ in range(3):
                    F.aplicar(bpy.context,conj,chave,100)
                    self.assertAlmostEqual(F.valor(conj,chave),100,delta=1)
                    F.aplicar(bpy.context,conj,chave,original)
                    for o,vs in antes.items():
                        self.assertEqual(len(vs),len(o.data.vertices))
                        self.assertLess(max((o.matrix_world @ v.co-p).length for p,v in zip(vs,o.data.vertices)),.00001)

    def test_referencia_sobrevive_ao_append_e_nao_edita_o_original(self):
        conj=canto_em_l();chave=('P1',2)
        F.aplicar(bpy.context,conj,chave,100)
        col=addon.modulos._colecao_do_modulo(conj)
        caminho=os.path.join(tempfile.mkdtemp(),'Canto.blend')
        bpy.data.libraries.write(caminho,{col})
        with bpy.data.libraries.load(caminho) as (de,para):para.collections=[col.name]
        nova=para.collections[0];bpy.context.scene.collection.children.link(nova)
        copia=next(o for o in nova.objects if addon.chapas.MARCA_CONJUNTO in o)
        bpy.context.view_layer.update()
        F.aplicar(bpy.context,copia,chave,500)
        self.assertAlmostEqual(F.valor(copia,chave),500,delta=.1)
        self.assertAlmostEqual(F.valor(conj,chave),100,delta=.1)
        self.assertTrue(all(d['objeto'] in copia.children_recursive for d in copia[F.CHAVE_EDICAO]['pecas'].values()))

    def test_gavetas_acompanham_a_frente_do_braco_com_trilho_valido(self):
        from mathutils import Matrix
        conj=canto_em_l();G=addon.gavetas
        ref=Matrix.Diagonal(Vector((-1,-1,1)))
        # importar(..., na_origem=True) centraliza X/Y em torno de zero.
        margens=G.margens_do_vao(conj,Vector((435,50,15))/1000,Vector((65,50,685))/1000,ref)
        grupo=G.criar_gavetas(bpy.context,conj,margens,dict(quantidade=3,profundidade_mm=500),ref)
        bpy.context.view_layer.update()
        origem=grupo.matrix_world.translation.copy()
        pecas=list(grupo.children_recursive)
        F.aplicar(bpy.context,conj,('P1',2),100)
        # 100 nao comporta trilho de 250 + 10 mm: limita sem esmagar.
        self.assertGreaterEqual(F.valor(conj,('P1',2)),259.9)
        self.assertAlmostEqual(G.parametros(grupo)['profundidade_mm'],260,delta=.1)
        self.assertAlmostEqual(grupo.matrix_world.translation.y,-.190,delta=.001)
        self.assertEqual(pecas,list(grupo.children_recursive))
        F.aplicar(bpy.context,conj,('P1',2),500)
        self.assertAlmostEqual(G.parametros(grupo)['profundidade_mm'],500,delta=.1)
        self.assertLess((origem-grupo.matrix_world.translation).length,1e-5)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestFormas)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de formas')
