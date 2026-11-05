"""Opening placeholders and clearance volumes for passage and swing."""
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector, geometry

_alvenaria = _paredes = _paredes_edicao = _instalacoes = None

MODELOS = {
    'PORTA': ("Hinged door", (.90, 2.10, .12)),
    'JANELA': ("Sliding window", (1.20, 1., .10)),
    'SACADA': ("Balcony door", (1.60, 2.10, .12)),
}
PERFIL = .045
FOLGA = .003
FOLHA = .035
GIRO = math.radians(110)
AVISO = "The cabinet obstructs the passage or the door opening"
CHAVE_LADO = 'cabinet_esquadria_lado'
CHAVE_FACE = 'cabinet_esquadria_sentido'
CHAVE_ABERTURAS = 'cabinet_esquadria_aberturas'
_varreduras = [{}]


def _retangulo(x0, x1, y0, y1):
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _sobrepoe(a, b):
    for poligono in (a, b):
        for p, q in zip(poligono, (*poligono[1:], poligono[0])):
            normal = (p[1] - q[1], q[0] - p[0])
            norma = math.hypot(*normal)
            if norma < 1e-10:
                continue
            aa = [x * normal[0] + y * normal[1] for x, y in a]
            bb = [x * normal[0] + y * normal[1] for x, y in b]
            if min(max(aa), max(bb)) - max(min(aa), min(bb)) <= 1e-5 * norma:
                return False
    return True


def _eixo(obj):
    largura, _, fundo = obj[_alvenaria.MEDIDAS]
    lado = obj.get(CHAVE_LADO, 1)
    sentido = obj.get(CHAVE_FACE, 1)
    x = lado * (-largura / 2 + PERFIL + FOLGA)
    z = 0. if sentido == 1 else -fundo
    return x, z, lado, sentido


def _folha_no_angulo(obj, angulo):
    largura = obj[_alvenaria.MEDIDAS][0] - 2 * (PERFIL + FOLGA)
    x0, z0, lado, sentido = _eixo(obj)
    c, s = math.cos(angulo), math.sin(angulo)
    return tuple((x0 + lado * (x*c + z*s), z0 + sentido * (x*s - z*c))
                 for x, z in _retangulo(0, largura, 0, FOLHA))


def _toca_batente(obj, angulo):
    largura, _, fundo = obj[_alvenaria.MEDIDAS]
    folha = _folha_no_angulo(obj, angulo)
    return any(_sobrepoe(folha, _retangulo(x, x + PERFIL, -fundo, 0))
               for x in (-largura / 2, largura / 2 - PERFIL))


def _limite(obj):
    anterior = 0.
    for i in range(1, 111):
        teste = GIRO * i / 110
        if _toca_batente(obj, teste):
            for _ in range(13):
                meio = (anterior + teste) / 2
                if _toca_batente(obj, meio):
                    teste = meio
                else:
                    anterior = meio
            return anterior
        anterior = teste
    return GIRO


def _ficha(obj):
    largura, altura, fundo = obj[_alvenaria.MEDIDAS]
    chave = (largura, altura, fundo, obj.get(CHAVE_LADO, 1), obj.get(CHAVE_FACE, 1))
    if chave in _varreduras[0]:
        return _varreduras[0][chave]
    limite = _limite(obj)
    passos = max(1, math.ceil(limite / math.radians(2)))
    poses = [_folha_no_angulo(obj, limite * i / passos) for i in range(passos + 1)]
    volumes = [(_retangulo(-largura / 2, largura / 2, -fundo, .002), -altura / 2, altura / 2)]
    sagita = largura * (1 - math.cos(limite / (2 * passos))) + 1e-5
    for antes, depois in zip(poses, poses[1:]):
        pontos = [Vector((x + dx, z + dz)) for x, z in (*antes, *depois)
                  for dx, dz in _retangulo(-sagita, sagita, -sagita, sagita)]
        envoltoria = tuple(pontos[i] for i in geometry.convex_hull_2d(pontos))
        volumes.append((envoltoria, -altura / 2 + FOLGA, altura / 2 - PERFIL - FOLGA))
    if len(_varreduras[0]) >= 64:
        _varreduras[0].clear()
    _varreduras[0][chave] = limite, volumes
    return limite, volumes


def _caixa(a, b, obj, nome):
    return _instalacoes.caixa(obj, nome, tuple((p + q) / 2 for p, q in zip(a, b)),
                           tuple(q - p for p, q in zip(a, b)))


def _vidro():
    material = next((m for m in bpy.data.materials if m.get('cabinet_vidro_blocagem')), None)
    if material is None:
        material = bpy.data.materials.new("Door/window glass")
        material['cabinet_vidro_blocagem'] = True
        material.diffuse_color = (.31, .58, .67, .36)
        material.use_nodes = True
        bsdf = next(n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        bsdf.inputs['Base Color'].default_value = (.31, .58, .67, 1)
        bsdf.inputs['Alpha'].default_value = .36
        bsdf.inputs['Roughness'].default_value = .2
    return material


def montar(obj):
    largura, altura, fundo = obj[_alvenaria.MEDIDAS]
    x, y = largura / 2, altura / 2
    porta = obj[_alvenaria.MARCA] == 'PORTA'
    _caixa((-x, -y, -fundo), (-x + PERFIL, y, 0), obj, "Left jamb")
    _caixa((x - PERFIL, -y, -fundo), (x, y, 0), obj, "Right jamb")
    _caixa((-x + PERFIL, y - PERFIL, -fundo), (x - PERFIL, y, 0), obj, "Head jamb")
    if porta:
        _instalacoes.caixa(obj, "Leaf 1", (0, 0, 0),
                        (largura - 2*(PERFIL+FOLGA), altura - PERFIL - 2*FOLGA, FOLHA))
        for i in range(2):
            _instalacoes.cilindro(obj, "Hinge %d" % (i + 1), .008, .075)
    else:
        _caixa((-x + PERFIL, -y, -fundo), (x - PERFIL, -y + PERFIL, 0), obj, "Lower tracks")
        for i in range(2):
            folha = _instalacoes.caixa(obj, "Leaf %d" % (i + 1), (0, 0, 0),
                                    ((largura - 2*PERFIL) / 2, altura - 2*PERFIL, .018))
            folha.color = (.31, .58, .67, .65)
            if not folha.data.materials:
                folha.data.materials.append(_vidro())
    obj[CHAVE_ABERTURAS] = obj.get(CHAVE_ABERTURAS, [0., 0.])
    posar(obj)


def posar(obj):
    largura, altura, fundo = obj[_alvenaria.MEDIDAS]
    pecas = {_instalacoes.nome_peca(p): p for p in obj.children}
    fracoes = obj[CHAVE_ABERTURAS]
    if obj[_alvenaria.MARCA] == 'PORTA':
        x, z, lado, sentido = _eixo(obj)
        angulo = _ficha(obj)[0] * fracoes[0]
        giro = Matrix.Rotation(-lado * sentido * angulo, 4, 'Y')
        meio = Vector((lado*(largura - 2*(PERFIL+FOLGA))/2, -PERFIL/2, -sentido*FOLHA/2))
        folha = pecas["Leaf 1"]
        folha.matrix_basis = Matrix.Translation((x, 0, z)) @ giro @ Matrix.Translation(meio) @ Matrix.Diagonal((*folha.scale, 1.))
        for i in range(2):
            peca = pecas.get("Hinge %d" % (i + 1))
            if peca:
                peca.matrix_basis = (Matrix.Translation((x, (.5-i)*altura*.65, z))
                                     @ Matrix.Rotation(math.pi/2, 4, 'X') @ Matrix.Diagonal((*peca.scale, 1.)))
    else:
        curso = (largura - 2*PERFIL) / 2
        for i, fracao in enumerate(fracoes):
            pecas["Leaf %d" % (i + 1)].location = ((2*i - 1)*curso*(.5-fracao), 0, -fundo*(i+1)/3)


def abrir(obj, folha, fracao):
    fracoes = list(obj[CHAVE_ABERTURAS])
    fracoes[folha] = min(1., max(0., fracao))
    obj[CHAVE_ABERTURAS] = fracoes
    posar(obj)


def colisao(context, modulo, matriz=None, caixa=None):
    portas = [o for o in getattr(context.scene, 'objects', ()) if o.get(_alvenaria.MARCA) == 'PORTA'
              and not o.get(_alvenaria.CHAVE_SEM_APOIO)]
    if not portas:
        return None
    caixa = caixa or _paredes.caixa_do_modulo(modulo)
    if caixa is None:
        return None
    lo, hi = caixa
    matriz = matriz if matriz is not None else _paredes.referencial(modulo)
    cantos = [matriz @ Vector((x, y, z)) for x in (lo.x, hi.x)
              for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    for porta in portas:
        inv = porta.matrix_world.inverted_safe()
        locais = [inv @ p for p in cantos]
        base, topo = min(p.y for p in locais), max(p.y for p in locais)
        pontos = [Vector((p.x, p.z)) for p in locais]
        contorno = tuple(pontos[i] for i in geometry.convex_hull_2d(pontos))
        for volume, ymin, ymax in _ficha(porta)[1]:
            if min(topo, ymax) - max(base, ymin) > 1e-5 and _sobrepoe(contorno, volume):
                return porta
    return None


def avisar(context, modulo):
    porta = colisao(context, modulo)
    if porta is None:
        return False
    regiao = _paredes_edicao.viewport(context)
    janela = next((r for r in regiao.regions if r.type == 'WINDOW'), None) if regiao else None
    if janela is None:
        return False
    l, a, _ = porta[_alvenaria.MEDIDAS]
    ps = [porta.matrix_world @ Vector((x, y, .002))
          for x, y in _retangulo(-l/2, l/2, -a/2, a/2)]
    _paredes.sinalizar_erro(dict(contorno=list(zip(ps, ps[1:]+ps[:1])),
                               triangulos=np.array([ps[i] for i in (0,1,2,0,2,3)])),
                           janela.as_pointer())
    return True
