"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_snapshot_blender.py

Testes de CARACTERIZACAO (golden master, M. Feathers): gravam o que o
add-on FAZ hoje -- layout da gaveta, malhas, calculo das portas,
redimensionamento do modulo, geometria da HUD, puxadores -- e acusam
qualquer diferenca. Nao dizem se o comportamento e' certo; dizem que
ele MUDOU. Quebra oculta vira diff com o caminho exato do valor.

Mudanca INTENCIONAL: regrave e revise o diff no git antes do commit:

    blender ... --python tests/run_tests.py -- --atualizar
    (ou CABINET_ATUALIZAR_SNAPSHOTS=1 ao rodar so' esta suite)
"""
import json
import math
import os
import sys
import unittest

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archy_builder as addon

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'snapshots')
ATUALIZAR = os.environ.get('CABINET_ATUALIZAR_SNAPSHOTS') == '1'
LARGURAS = (190, 320, 482, 564)


def _r(valor, casas=3):
    """Arredonda o que e' numero, recursivamente (ruido de float fora)."""
    if isinstance(valor, float):
        r = round(valor, casas)
        return 0.0 if r == 0 else r
    if isinstance(valor, (list, tuple)):
        return [_r(v, casas) for v in valor]
    if isinstance(valor, dict):
        return {k: _r(v, casas) for k, v in valor.items()}
    if isinstance(valor, Vector):
        return [_r(v, casas) for v in valor]
    return valor


def _primeira_diferenca(a, b, caminho='$'):
    if type(a) != type(b):
        return caminho, a, b
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return '%s.%s' % (caminho, k), a.get(k, '<falta>'), b.get(k, '<falta>')
            d = _primeira_diferenca(a[k], b[k], '%s.%s' % (caminho, k))
            if d:
                return d
        return None
    if isinstance(a, list):
        for i, (x, y) in enumerate(zip(a, b)):
            d = _primeira_diferenca(x, y, '%s[%d]' % (caminho, i))
            if d:
                return d
        if len(a) != len(b):
            return '%s(tamanho)' % caminho, len(a), len(b)
        return None
    return None if a == b else (caminho, a, b)


def _nome(obj):
    """Nome sem o sufixo .001 do Blender: estavel entre execucoes."""
    return obj.name.split('.')[0]


class TestCaracterizacao(unittest.TestCase):

    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        cena = bpy.context.scene
        for nome in addon.portas._PROPS_PORTAS_CENA:
            cena.property_unset(nome)
        cena.cursor.location = (0, 0, 0)
        cena.cabinet_aba = 'MODULOS'
        tela = bpy.context.screen
        for chave in (addon.gaveta._CHAVE_ROLAGEM, addon.gaveta._CHAVE_ROLAGEM_BIB,
                      addon.gaveta._CHAVE_DIVISA, addon.gaveta._CHAVE_OPCOES):
            tela.pop(chave, None)

    def conferir(self, nome, dados):
        dados = json.loads(json.dumps(_r(dados)))
        caminho = os.path.join(PASTA, nome + '.json')
        if ATUALIZAR or not os.path.exists(caminho):
            os.makedirs(PASTA, exist_ok=True)
            with open(caminho, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(dados, f, indent=1, ensure_ascii=True, sort_keys=True)
                f.write('\n')
            print('[snapshot] gravado:', nome)
            return
        with open(caminho, encoding='utf-8') as f:
            esperado = json.load(f)
        diferenca = _primeira_diferenca(esperado, dados)
        if diferenca:
            onde, antes, agora = diferenca
            self.fail('%s mudou em %s\n  gravado: %r\n  agora:   %r\n'
                      'Se foi de proposito, regrave (--atualizar) e revise '
                      'o diff.' % (nome, onde, antes, agora))

    # ------------------------------------------------------- cenas
    def modulo(self):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar()
        conj = next(o for o in bpy.data.objects if addon.chapas.MARCA_CONJUNTO in o)
        bpy.context.view_layer.update()
        return conj

    def porta(self, conj, **opcoes):
        L, A = conj.conj_largura_mm, conj.conj_altura_mm
        P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
        a = conj.matrix_world @ (Vector((-L / 2 + E, -P / 2, E)) / 1000.0)
        b = conj.matrix_world @ (Vector((L / 2 - E, -P / 2, A - E)) / 1000.0)
        parametros = dict(frente='NEG_Y', dobradica='RETA', folhas=2)
        parametros.update(opcoes)
        resultado = bpy.ops.object.cabinet_portas(
            'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
            referencia=tuple(v for linha in
                             conj.matrix_world.to_quaternion().to_matrix()
                             for v in linha),
            pai_nome=conj.name, modulo_nome=conj.name, **parametros)
        self.assertEqual(resultado, {'FINISHED'})
        return addon.portas._portas_do_conjunto(conj)[0]

    def chapas(self, objetos):
        return sorted(
            ({'nome': _nome(o), 'L': o.chapa_largura_mm,
              'C': o.chapa_comprimento_mm, 'E': o.chapa_espessura_mm,
              'centro': _r(o.matrix_world.translation, 5),
              'dims': _r(o.dimensions, 5)}
             for o in objetos if addon.chapas.MARCA_CHAPA in o),
            key=lambda d: (d['nome'], d['centro']))

    @staticmethod
    def widgets(largura, altura=900):
        """Painel da aba + divisoria + pe' fixo (a biblioteca fica de fora:
        o conteudo dela muda com os presets do usuario, nao com o codigo)."""
        cab, conteudo, rodape = addon.gaveta._partes_gaveta(
            addon.gaveta._widgets_gaveta(bpy.context, largura, altura))
        cima, divisa, _baixo = addon.gaveta._paineis_gaveta(conteudo)
        saida = []
        for x, y, w, h, rotulo, acao in cab + cima + ([divisa] if divisa else []) + rodape:
            verbo = acao[0] if acao else None
            extra = acao[1] if acao and len(acao) > 1 and isinstance(
                acao[1], (str, bool, int, float)) else None
            saida.append([x, y, w, h, rotulo, verbo, extra])
        return saida

    # ------------------------------------------------------ casos
    def test_layout_da_gaveta(self):
        conj = self.modulo()
        chapa = addon.modulos._chapas_do_conjunto(conj)[0]
        cenarios = {
            'nada': lambda: bpy.ops.object.select_all(action='DESELECT'),
            'modulo': lambda: addon.hud._selecionar_chapa_hud(bpy.context, chapa),
            'chapa': lambda: addon.hud._selecionar_chapa_hud(
                bpy.context, chapa, individual=True),
        }
        dados = {}
        for nome, selecionar in cenarios.items():
            selecionar()
            if nome == 'nada':
                bpy.context.view_layer.objects.active = None
            for aba in ('MODULOS', 'PORTAS', 'PUXADORES'):
                bpy.context.scene.cabinet_aba = aba
                for largura in LARGURAS:
                    dados['%s/%s/%d' % (nome, aba, largura)] = \
                        self.widgets(largura)
        self.conferir('gaveta_layout', dados)

    def test_malha_da_chapa(self):
        dados = {}
        for nome, (L, C, E, rot) in {
                'padrao': (600.0, 400.0, 18.0, (0, 0, 0)),
                'grossa': (1000.0, 300.0, 70.5, (0, 0, 0)),
                'em_pe': (720.0, 560.0, 15.0, (90.0, 0, 90.0))}.items():
            obj = addon.chapas.nova_chapa(nome, L, C, E, (100.0, 0, 0), rot,
                                   bpy.context)
            bpy.context.view_layer.update()
            dados[nome] = {
                'vertices': sorted(_r(tuple(v.co), 5) for v in obj.data.vertices),
                'faces': len(obj.data.polygons),
                'mundo': sorted(_r(tuple(p), 5) for p in addon.chapas._cantos(obj)),
            }
        self.conferir('chapa_malha', dados)

    def test_calculo_das_portas(self):
        dados = {}
        for abertura, maximo in sorted(addon.portas.LIMITES_FOLHAS.items()):
            dobradicas = (('RETA',) if abertura == 'CORRER'
                          else ('RETA', 'CURVA', 'SUPER_CURVA'))
            for folhas in range(1, maximo + 1):
                for dobradica in dobradicas:
                    p = addon.portas._parametros_portas_da_cena(bpy.context.scene,
                                                         numerico=True)
                    p.update(abertura=abertura, folhas=folhas,
                             dobradica=dobradica)
                    chave = '%s/%d/%s' % (abertura, folhas, dobradica)
                    try:
                        dados[chave] = _r(addon.portas._calcular_folhas_portas(
                            764.0, 664.0, p))
                    except ValueError as erro:
                        dados[chave] = 'ERRO: %s' % erro
        self.conferir('portas_calculo', dados)

    def test_modulo_redimensionado(self):
        conj = self.modulo()
        dados = {'inicio': self.chapas(addon.modulos._chapas_do_conjunto(conj))}
        conj.conj_largura_mm += 200
        conj.conj_altura_mm -= 100
        conj.conj_profundidade_mm += 50
        bpy.context.view_layer.update()
        dados['medidas'] = self.chapas(addon.modulos._chapas_do_conjunto(conj))
        conj.conj_espessura_mm = 25.0
        bpy.context.view_layer.update()
        dados['espessura'] = self.chapas(addon.modulos._chapas_do_conjunto(conj))
        dados['conj'] = [conj.conj_largura_mm, conj.conj_altura_mm,
                         conj.conj_profundidade_mm, conj.conj_espessura_mm,
                         _r(conj.matrix_world.translation, 5)]
        self.conferir('modulo_redimensionado', dados)

    def test_porta_no_modulo_acompanha_o_redimensionamento(self):
        conj = self.modulo()
        grupo = self.porta(conj)
        dados = {'parametros': dict(grupo['porta_parametros']),
                 'inicio': self.chapas(addon.portas._folhas_portas(grupo))}
        conj.conj_largura_mm += 300
        conj.conj_altura_mm += 100
        bpy.context.view_layer.update()
        dados['redimensionado'] = self.chapas(addon.portas._folhas_portas(grupo))
        self.conferir('porta_no_modulo', dados)

    def test_geometria_da_hud(self):
        conj = self.modulo()
        chapa = addon.modulos._chapas_do_conjunto(conj)[0]
        dados = {}
        for nome, individual in (('modulo', False), ('chapa', True)):
            addon.hud._selecionar_chapa_hud(bpy.context, chapa,
                                        individual=individual)
            g = addon.hud._geometria_hud(bpy.context)
            dados[nome] = {
                'modo': g['modo'],
                'cantos': [_r(p, 5) for p in g['cantos']],
                'linhas': sorted([l['tipo'], l.get('letra', ''),
                                  l.get('eixo', -1),
                                  list(l.get('cantos', ()))]
                                 for l in g['linhas']),
            }
        self.conferir('hud_geometria', dados)

    def test_puxadores_parametricos(self):
        dados = {}
        for tipo in sorted(addon.puxadores.MODELOS_PADRAO):
            for borda in ('X-', 'X+', 'Y-', 'Y+'):
                for o in list(bpy.data.objects):
                    bpy.data.objects.remove(o, do_unlink=True)
                chapa = addon.chapas.nova_chapa('Base', 600.0, 400.0, 18.0,
                                         (0, 0, 0), (0, 0, 0), bpy.context)
                pux = addon.puxadores.criar_puxador(bpy.context, chapa, tipo, borda, 1)
                bpy.context.view_layer.update()
                dados['%s/%s' % (tipo, borda)] = {
                    'centro': _r(pux.matrix_world.translation, 5),
                    'dims': _r(pux.dimensions, 5),
                    'chapa': _r(chapa.dimensions, 5),
                }
        self.conferir('puxadores', dados)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestCaracterizacao)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha nos testes de caracterizacao')
