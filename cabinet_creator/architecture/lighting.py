"""Blocagens eletricas, luzes e forro rebaixado sobre a Alvenaria."""
import math

import bmesh
import blf
import bpy
import numpy as np
from bpy.types import Operator
from mathutils import Matrix, Vector

_alvenaria = _instalacoes = _paredes = _opcoes = _hud = None

MODELOS = {
    'TOMADA': ('Tomada', (.080, .120, .018)),
    'INTERRUPTOR': ('Interruptor', (.080, .120, .018)),
    'SPOT_EMBUTIDO': ('Spot embutido', (.078, .078, .055)),
    'SPOT_SOBREPOSTO': ('Spot de sobrepor', (.090, .090, .065)),
    'PENDENTE': ('Pendente', (.130, .130, .450)),
    'REBAIXO': ('Rebaixar teto', (1., 1., .120)),
}
LUZES = {'SPOT_EMBUTIDO', 'SPOT_SOBREPOSTO', 'PENDENTE'}
FORRO = 'cabinet_superficie_do_forro'
REGIAO = 'cabinet_regiao_do_forro'
TABICAS = 'cabinet_tabicas'
LADOS = 'cabinet_lados_de_tabica'
LADOS_LUZ = 'cabinet_lados_com_luz'
LARGURA = 'cabinet_largura_tabica'
PROFUNDIDADE = 'cabinet_rebaixo'
FONTE = 'cabinet_apoio_original_da_luz'
# O nome identifica modificadores de forros salvos antes da troca da marca.
CORTE_TABICA = 'Cabinet Creator - Tabica '
GESSO = .015


def tipos_de_apoio(modelo):
    if modelo == 'REBAIXO':
        return ('TETO',)
    return _alvenaria.TIPOS


def _luz(obj, nome, tipo, energia):
    peca = next((o for o in obj.children if o.get(_alvenaria.PECA) == nome), None)
    if peca is None:
        peca = bpy.data.objects.new(nome, bpy.data.lights.new(nome, tipo))
        obj.users_collection[0].objects.link(peca)
        peca.parent = obj
        peca[_alvenaria.PECA] = nome
        peca[_instalacoes.DONO] = obj[_instalacoes.IDENTIDADE]
    peca.data.energy = energia
    return peca


def montar(obj):
    modelo = obj[_alvenaria.MARCA]
    l, a, p = obj[_alvenaria.MEDIDAS]
    if modelo in {'TOMADA', 'INTERRUPTOR'}:
        _instalacoes.caixa(obj, 'Espelho', (0, 0, .004), (l, a, .008))
        _instalacoes.caixa(obj, 'Tecla' if modelo == 'INTERRUPTOR' else 'Tomada central',
                          (0, 0, .009), (l*.52, a*.41, .010))
        return
    if modelo == 'REBAIXO':
        atualizar_forro(obj)
        return
    if modelo == 'PENDENTE':
        _instalacoes.cilindro(obj, 'Canopla', l*.38, .018, (0, 0, .009))
        _instalacoes.cilindro(obj, 'Haste', .004, p)
        _instalacoes.cilindro(obj, 'Difusor', l/2, .085)
        _luz(obj, 'Luz', 'POINT', 18).data.shadow_soft_size = .04
        posar_pendente(obj, obj.matrix_world)
        return
    embutido = modelo == 'SPOT_EMBUTIDO'
    _instalacoes.anel(obj, 'Corpo', l*.48, p, (0, 0, -p/2 if embutido else p/2))
    _instalacoes.anel(obj, 'Aro', l*.57, .008, (0, 0, .004 if embutido else p))
    luz = _luz(obj, 'Luz', 'SPOT', 18)
    luz.matrix_basis = (Matrix.Translation((0, 0, -.002 if embutido else p+.004))
                        @ Matrix.Rotation(math.pi, 4, 'X'))
    luz.data.spot_size = math.radians(46)
    luz.data.spot_blend = .25


def posar_pendente(obj, matriz):
    if obj.get(_alvenaria.MARCA) != 'PENDENTE':
        return
    queda = obj[_alvenaria.MEDIDAS][2]
    vertical = matriz.to_3x3().inverted_safe() @ Vector((0, 0, -1))
    giro = Vector((0, 0, 1)).rotation_difference(vertical).to_matrix().to_4x4()
    for peca in obj.children:
        nome = peca.get(_alvenaria.PECA)
        if nome == 'Canopla':
            continue
        posicao = queda/2 if nome == 'Haste' else queda + (.045 if nome == 'Luz' else 0)
        peca.matrix_basis = (Matrix.Translation(vertical*posicao) @ giro
                             @ Matrix.Diagonal((*peca.scale, 1.)))


def preparar_regiao(limites, matriz):
    """Malha numerica do forro com bordas orientadas pelo interior."""
    inversa = matriz.inverted_safe()
    vertices, indices, trios, bordas = [], {}, [], {}
    for tri in np.asarray(limites['triangulos']).reshape(-1, 3, 3):
        plano = [tuple((inversa @ Vector(p))[:2]) for p in tri]
        a, b, c = map(Vector, plano)
        cruz = (b-a).cross(c-a)
        if abs(cruz) < 1e-9:
            continue
        if cruz < 0:
            plano.reverse()
        ids = []
        for p in plano:
            chave = tuple(round(v, 6) for v in p)
            if chave not in indices:
                indices[chave] = len(vertices)
                vertices.append(chave)
            ids.append(indices[chave])
        trios.append(ids)
        for p, q in zip(ids, ids[1:]+ids[:1]):
            if (q, p) in bordas:
                del bordas[q, p]
            else:
                bordas[p, q] = True
    if not trios or not bordas:
        raise ValueError('Selecione uma regiao plana continua do teto')
    # Une apenas segmentos consecutivos que pertencem ao mesmo lado reto.
    lados = list(bordas)
    mudou = True
    while mudou:
        mudou = False
        for i, (p, q) in enumerate(lados):
            j = next((k for k, (a, b) in enumerate(lados) if a == q and b != p), None)
            if j is None:
                continue
            r = lados[j][1]
            a, b = Vector(vertices[q])-Vector(vertices[p]), Vector(vertices[r])-Vector(vertices[q])
            if abs(a.normalized().cross(b.normalized())) < 1e-5 and a.dot(b) > 0:
                lados[i] = (p, r)
                del lados[j]
                mudou = True
                break
    return dict(vertices=vertices, trios=trios, bordas=list(bordas), lados=lados)


def montar_forro(obj, limites, matriz):
    regiao = preparar_regiao(limites, matriz)
    obj[REGIAO] = regiao
    obj[PROFUNDIDADE] = obj[_alvenaria.MEDIDAS][2]
    obj[LARGURA] = .025
    obj[TABICAS] = False
    obj[LADOS] = [True]*len(regiao['lados'])
    obj[LADOS_LUZ] = [False]*len(regiao['lados'])
    vertices = [(x,y,z) for z in (0., -GESSO) for x,y in regiao['vertices']]
    quantidade = len(regiao['vertices'])
    faces = [tuple(t) for t in regiao['trios']]
    faces.extend(tuple(i+quantidade for i in reversed(t)) for t in regiao['trios'])
    faces.extend((b,a,a+quantidade,b+quantidade) for a,b in regiao['bordas'])
    malha = bpy.data.meshes.new('Superficie do forro')
    malha.from_pydata(vertices, [], faces)
    malha.update()
    tipo = malha.attributes.new(_alvenaria.ATR_TIPO, 'INT', 'FACE')
    for i in range(len(regiao['trios'])):
        tipo.data[i].value = 3
    placa = bpy.data.objects.new('Superficie do forro', malha)
    obj.users_collection[0].objects.link(placa)
    placa.parent = obj
    placa[FORRO] = True
    placa[_instalacoes.DONO] = obj[_instalacoes.IDENTIDADE]
    placa[_paredes.CHAVE_ALVENARIA] = True
    placa[_alvenaria.CHAVE_TIPADA] = True
    atualizar_forro(obj, matriz)
    return placa


def atualizar_forro(obj, matriz=None):
    placa = next((o for o in obj.children if o.get(FORRO)), None)
    if placa is None:
        return
    matriz = matriz if matriz is not None else obj.matrix_world
    queda = matriz.to_3x3().inverted_safe() @ Vector((0, 0, -obj[PROFUNDIDADE]))
    if (placa.location - queda).length > 1e-7:
        placa.location = queda
    regiao = obj[REGIAO]
    largura = obj[LARGURA]
    for i, (a,b) in enumerate(regiao['lados']):
        p, q = (Vector((*regiao['vertices'][j], 0.)) for j in (a,b))
        direcao = (q-p).normalized()
        interior = Vector((-direcao.y, direcao.x, 0))
        rotacao = Matrix.Rotation(math.atan2(direcao.y, direcao.x), 4, 'Z')
        centro = (p+q)/2 + queda + interior*(largura/2)
        comprimento = (q-p).length
        nome = CORTE_TABICA + str(i+1)
        mod = placa.modifiers.get(nome)
        if obj[TABICAS] and obj[LADOS][i]:
            caixa = _instalacoes.caixa(obj, nome, (0,0,0), (comprimento+2*largura, largura+.002, .1))
            caixa.matrix_basis = (Matrix.Translation(centro) @ rotacao
                                  @ Matrix.Diagonal((*caixa.scale, 1.)))
            caixa.hide_select = caixa.hide_render = True
            caixa.hide_set(True)
            if mod is None:
                mod = placa.modifiers.new(nome, 'BOOLEAN')
                mod.operation = 'DIFFERENCE'
                mod.solver = 'EXACT'
            mod.object = caixa
        elif mod is not None:
            cortador = mod.object
            placa.modifiers.remove(mod)
            if cortador is not None:
                _instalacoes.remover_peca(cortador)
        nome_luz = 'Luz da tabica %d' % (i+1)
        if obj[TABICAS] and obj[LADOS][i] and obj[LADOS_LUZ][i]:
            luz = _luz(obj, nome_luz, 'AREA', comprimento*12)
            luz.matrix_basis = Matrix.Translation(centro) @ rotacao @ Matrix.Rotation(math.pi, 4, 'X')
            luz.data.shape = 'RECTANGLE'
            luz.data.size = comprimento
            luz.data.size_y = min(largura, .018)
        else:
            luz = next((o for o in obj.children if o.get(_alvenaria.PECA) == nome_luz), None)
            if luz is not None:
                _instalacoes.remover_peca(luz)


def instalar_forro(context, apoio, indice, matriz, limites=None):
    limites = limites or _alvenaria.regiao(apoio, indice, matriz)
    if not limites:
        raise ValueError('Selecione uma regiao plana continua do teto')
    x0,x1,y0,y1 = limites['retangulo']
    medidas = (x1-x0, y1-y0, MODELOS['REBAIXO'][1][2])
    matriz = matriz.copy()
    u, v = (matriz.to_3x3().col[i] for i in (0, 1))
    matriz.translation += u*((x0+x1)/2-matriz.translation.dot(u))
    matriz.translation += v*((y0+y1)/2-matriz.translation.dot(v))
    obj = _instalacoes.nova(context, 'REBAIXO', 'Forro rebaixado', medidas, matriz)
    try:
        _alvenaria.vincular(obj, apoio, indice, matriz, 'TETO')
        montar_forro(obj, limites, matriz)
    except Exception:
        _instalacoes.remover(obj)
        raise
    return obj


def guardar_origem(obj, placa, matriz):
    if not placa.get(FORRO) or obj[_alvenaria.MARCA] not in LUZES:
        return
    forro = placa.parent
    resolvido = _alvenaria.resolver(forro)
    if resolvido is None:
        return
    origem, _, indice, _ = resolvido
    ancora = matriz.copy()
    ancora.translation.z += forro[PROFUNDIDADE]
    obj[FONTE] = dict(
        uid=origem[_paredes.CHAVE_UID_PAREDE], nome=origem.name,
        face=origem.data.attributes[_alvenaria.ATR_FACE].data[indice].value,
        tipo='TETO', matriz=[list(l) for l in _alvenaria._rigida(origem).inverted() @ ancora])


def devolver_luz(obj):
    anterior = obj.get(FONTE)
    if not anterior:
        return False
    apoio = _alvenaria.apoio_de(obj)
    copia = dict(obj[_alvenaria.CHAVE_VINCULO].to_dict())
    obj[_alvenaria.CHAVE_VINCULO] = anterior.to_dict()
    resolvido = _alvenaria.resolver(obj)
    if resolvido is None:
        obj[_alvenaria.CHAVE_VINCULO] = copia
        return False
    origem, matriz, indice, limites = resolvido
    if obj[_alvenaria.MARCA] == 'SPOT_EMBUTIDO':
        try:
            profundidade = _instalacoes._medir_corte(origem, matriz, indice, obj[_alvenaria.MEDIDAS], limites)
        except ValueError:
            obj[_alvenaria.CHAVE_VINCULO] = copia
            return False
        if apoio is not None:
            _instalacoes._recorte(obj, apoio, None)
        _instalacoes._recorte(obj, origem, profundidade)
    obj.matrix_world = matriz
    obj.pop(FONTE, None)
    return True


def devolver_luzes_do_forro(placa):
    luzes = [luz for luz in bpy.context.scene.objects
             if luz.get(FONTE) and _alvenaria.apoio_de(luz) == placa]
    for luz in luzes:
        devolver_luz(luz)


def editar_forro(obj, propriedade, valor):
    if propriedade not in {PROFUNDIDADE, LARGURA} or not .005 <= valor <= (3. if propriedade == PROFUNDIDADE else .20):
        return 'Valor invalido para o rebaixo'
    obj[propriedade] = valor
    atualizar_forro(obj)
    return None


def acao_forro(obj, acao):
    if obj[_alvenaria.MARCA] != 'REBAIXO':
        return False
    if acao in {'completo', 'tabica'}:
        obj[TABICAS] = acao == 'tabica'
    elif acao.startswith(('lado_', 'luz_')):
        chave = LADOS if acao.startswith('lado_') else LADOS_LUZ
        indice = int(acao.split('_')[1])
        valores = list(obj[chave])
        if not 0 <= indice < len(valores):
            return False
        valores[indice] = not valores[indice]
        obj[chave] = valores
    else:
        return False
    atualizar_forro(obj)
    return True


def widgets(context, itens, x, y, w, obj):
    modelo = obj[_alvenaria.MARCA]
    if modelo == 'REBAIXO':
        campos = [(PROFUNDIDADE, 'Altura do rebaixo', obj[PROFUNDIDADE])]
        if obj[TABICAS]:
            campos.append((LARGURA, 'Largura da tabica', obj[LARGURA]))
    elif modelo == 'PENDENTE':
        campos = [('2', 'Queda do pendente', obj[_alvenaria.MEDIDAS][2])]
    else:
        return y
    for chave, rotulo, valor in campos:
        mm = valor*1000
        itens.append((x, y-37, w, 37, rotulo + ': ' + _opcoes._texto_medida(mm),
                      ('medida', 'forro' if modelo == 'REBAIXO' else 'instalacao_tamanho', chave, rotulo, mm)))
        y -= 43
    if modelo != 'REBAIXO':
        return y
    metade = (w-6)/2
    y -= 29
    completo = 'Rebaixo completo' if metade >= 100 else 'Completo'
    for i, (acao, rotulo) in enumerate((('completo', completo), ('tabica', 'Com tabica'))):
        itens.append((x+i*(metade+6), y, metade, 25, rotulo,
                      ('escolha', 'acao_instalacao', acao, obj[TABICAS] == bool(i), True, _instalacoes.ALVO)))
    if obj[TABICAS]:
        for i, lado in enumerate(obj[LADOS]):
            y -= 29
            itens.append((x, y, metade, 25, 'Lado %d' % (i+1),
                          ('escolha', 'acao_instalacao', 'lado_%d'%i, lado, True, _instalacoes.ALVO)))
            itens.append((x+metade+6, y, metade, 25, 'Luz %d' % (i+1),
                          ('escolha', 'acao_instalacao', 'luz_%d'%i, obj[LADOS_LUZ][i], True, _instalacoes.ALVO)))
    return _instalacoes.widgets_modelos(context, itens, x, y-8, w, 'TETO', excluir={'REBAIXO'})


def desenhar_lados(context, tela):
    obj = _alvenaria.grupo_de(getattr(context, 'object', None))
    if obj is None or not obj.get(TABICAS):
        return
    regiao = obj[REGIAO]
    escala = context.preferences.system.ui_scale
    tamanho = 11 * escala
    for i, (a, b) in enumerate(regiao['lados']):
        p, q = (Vector((*regiao['vertices'][j], 0.)) for j in (a, b))
        centro = obj.matrix_world @ ((p+q)/2) - Vector((0, 0, obj[PROFUNDIDADE]))
        posicao = tela(centro)
        if posicao is not None:
            texto = 'Lado %d' % (i+1)
            blf.size(0, tamanho)
            largura, _ = blf.dimensions(0, texto)
            _hud._caixa_texto_hud(posicao.x-largura/2, posicao.y, texto, tamanho, escala)


class OBJECT_OT_rebaixar_faces(Operator):
    bl_idname = 'object.cabinet_rebaixar_faces'
    bl_label = 'Rebaixar faces do teto'
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and _paredes.alvenaria_definida(context.edit_object)

    def execute(self, context):
        apoio = context.edit_object
        bm = bmesh.from_edit_mesh(apoio.data)
        bm.faces.index_update()
        faces = {f for f in bm.faces if f.select and not f.hide}
        if not faces:
            self.report({'WARNING'}, 'Selecione faces do teto')
            return {'CANCELLED'}
        frente = min(faces, key=lambda f: f.index)
        indice = frente.index
        normal = _paredes._normal_no_mundo(apoio, frente.normal)
        camada = bm.faces.layers.int.get(_alvenaria.ATR_TIPO)
        ponto = apoio.matrix_world @ frente.calc_center_median()
        visitadas = {frente}
        pendentes = [frente]
        while pendentes:
            for aresta in pendentes.pop().edges:
                for vizinha in aresta.link_faces:
                    if vizinha in faces and vizinha not in visitadas:
                        visitadas.add(vizinha)
                        pendentes.append(vizinha)
        for f in faces:
            n = _paredes._normal_no_mundo(apoio, f.normal)
            explicito = f[camada] if camada is not None else 0
            teto = explicito == 3 or (not explicito and not apoio.get(_alvenaria.CHAVE_TIPADA)
                                      and _paredes.tipo_superficie(n) == 'TETO')
            if (not teto or f not in visitadas or n.dot(normal) < .99985
                    or any(abs((apoio.matrix_world @ v.co-ponto).dot(normal)) > .002 for v in f.verts)):
                self.report({'WARNING'}, 'Selecione uma regiao plana continua do teto')
                return {'CANCELLED'}
        matriz = _alvenaria.referencial(ponto, normal)
        vertices = [apoio.matrix_world @ l.vert.co for tri in bm.calc_loop_triangles()
                    if tri[0].face in faces for l in tri]
        u, v = (matriz.to_3x3().col[i] for i in (0, 1))
        limites = {'triangulos': [tuple(p) for p in vertices],
                   'retangulo': (min(p.dot(u) for p in vertices), max(p.dot(u) for p in vertices),
                                 min(p.dot(v) for p in vertices), max(p.dot(v) for p in vertices))}
        try:
            preparar_regiao(limites, matriz)
        except ValueError as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        bpy.ops.object.mode_set(mode='OBJECT')
        obj = instalar_forro(context, apoio, indice, matriz, limites)
        apoio.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {'FINISHED'}
