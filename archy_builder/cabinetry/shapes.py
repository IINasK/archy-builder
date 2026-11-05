"""PLAN shapes for nonbox cabinets: L corners (RECORTE), diagonals
(CHANFRO), recognized from actual geometry and edited through the HUD:
each side's depth (P1/P2), diagonal R and total L/P without distorting
the corner.

Shapes are derived on every change, not persisted, like L/A/P. Measure
each box corner inward to the first part: constant setback means a
notch, linear means a diagonal, rapidly decreasing means a free outline
of straight segments.
"""

import math
import hashlib
from array import array

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.geometry import convex_hull_2d, delaunay_2d_cdt

# Used only at runtime (circular imports): __init__ binds these
# aliases after loading all modules (`_ligar_modulos`).
_chapas = _modulos = _portas = _prateleiras = None
_gavetas = None
_frentes = None

# Smaller corner setbacks are door/edge-band gaps, not shape features.
TOL_FORMA_MM = 30.0
# Missing L-shaped arm: smaller notches are rear pipe openings,
# which do not change the outline or gain a dimension.
RECORTE_MINIMO_MM = 100.0
# Band around the moving inner face: the door, crosspiece
# and ends of parts meeting it move together.
FAIXA_MM = 100.0
# Parts thinner than this across the stretch plane move rigidly.
RIGIDA_MM = 60.0
# For diagonals, geometry this close to the side moves intact so the
# side cannot bend; displacement decreases toward the opposite end.
MARGEM_CHANFRO_MM = 30.0
MENOR_LADO_MM = 50.0      # No edit may make a side smaller than this.
# Full-side diagonal: a remainder within this threshold means a SHARP
# corner, reaching it; a larger remainder ends at panel THICKNESS
# (corner shelf touching the side's inner face). Up to ESPESSURA_PONTA_MM,
# the remaining panel tip is outline only, without a dimension.
PONTA_AFIADA_MM = 3.0
ESPESSURA_PONTA_MM = 40.0
# DXF curved part (arched door/panel): not a panel, but deforms
# with the shape; marker saved in .blend.
MARCA_CURVA = "eh_peca_curva"

# Box corners counterclockwise: (X sign, Y sign).
QUINAS = ((-1, -1), (1, -1), (1, 1), (-1, 1))

_cache = {}     # Cabinet/panel name -> (signature, {plane: shape}).
CHAVE_EDICAO = 'forma_edicao'
VERSAO_REFERENCIA = 7
ATR_ANGULO = 'cabinet_forma_angulo'


def _base_do_plano(plano):
    # Right-handed bases let the same 2D solver handle plan and elevations.
    eixos = {'XY': ((1,0,0),(0,1,0),(0,0,1)),
             'XZ': ((1,0,0),(0,0,1),(0,-1,0)),
             'YZ': ((0,1,0),(0,0,1),(1,0,0))}
    return Matrix(eixos[plano]).transposed().to_4x4()


def _atributo_angular(plano):
    return ATR_ANGULO if plano == 'XY' else ATR_ANGULO + '_' + plano.lower()


def _matriz_gravada(valores):
    return Matrix([valores[i:i+4] for i in (0, 4, 8, 12)])


def _gravar_matriz(matriz):
    return [v for linha in matriz for v in linha]


def _pecas_da_edicao(conj):
    return list(dict.fromkeys(_pecas(conj) + [o for o in conj.children
                     if o.type == 'MESH' and (_chapas.MARCA_CHAPA in o
                                             or _chapas.MARCA_ACESSORIO in o)]))


def _digital_edicao(conj):
    """Manual edits invalidate the reference; cabinet movement/opening does not.
    foreach_get copies the mesh natively without a separate RNA read per co.
    """
    registros=[]
    inv = matriz_do_modulo(conj).inverted()
    for o in _pecas_da_edicao(conj):
        h=hashlib.sha1()
        m = (_portas._ferragens._matriz_fechada(o) if o.get('porta_curva_modelada')
             else o.matrix_world)
        h.update(repr((o.get('chapa_uid',''), tuple(round(v, 5) for linha in inv @ m for v in linha),
                       len(o.data.polygons), o.chapa_largura_mm, o.chapa_comprimento_mm,
                       o.chapa_espessura_mm)).encode())
        co = array('f', [0]) * (3 * len(o.data.vertices))
        o.data.vertices.foreach_get('co', co)
        h.update(co.tobytes())
        registros.append(h.digest())
    for o in conj.children:
        for chave in ('gavetas_parametros','prateleiras_parametros','porta_parametros'):
            p=o.get(chave)
            if p is not None:
                h=hashlib.sha1()
                m=(tuple(round(v,5) for linha in inv @ o.matrix_world for v in linha)
                   if chave!='porta_parametros' else ())
                parametros=p.to_dict()
                # Measured travel is a motion cache, not geometry.
                # Recalculating it during opening must not discard the resize reference.
                if chave=='porta_parametros':parametros.pop('abertura_limite_graus',None)
                h.update(repr((chave,m,parametros)).encode())
                if chave=='porta_parametros':
                    vao=o.get(_portas.CHAVE_VAO_ORIENTADO)
                    h.update(repr(vao.to_dict() if vao else None).encode())
                registros.append(h.digest())
    # Append can reorder children without changing geometry. The signature
    # describes a set of parts/systems rather than Outliner order.
    return hashlib.sha1(b''.join(sorted(registros))).hexdigest()


def concluir_edicao(conj):
    estado=conj.get(CHAVE_EDICAO)
    if estado:
        estado['ultimo']=_digital_edicao(conj)
        estado['fim']=_gravar_matriz(conj.matrix_world)


def _preparar_edicao(conj, chave, lado, plano='XY'):
    """Every dimension edit starts from the SAME reference geometry. Native
    Mesh copies retain topology, attributes, UVs and cutouts; the reference
    follows undo, saving/appending and cabinet duplication.
    """
    # Establish semantic identity before deformation and reference copying;
    # afterwards, the legacy guide may already lie on another plane.
    for o in conj.children:
        if o.type=='MESH' and _chapas.MARCA_FUNDO in o:
            _chapas.absorver_malha_editada(o)
    if conj.type=='MESH':
        if conj.data.users>1:conj.data=conj.data.copy()
        _frentes.preparar(conj)
    else:
        _frentes.preparar_conjunto(conj)
    canal = repr((tuple(chave), lado, plano))
    estado = conj.get(CHAVE_EDICAO)
    if (estado and estado.get('versao') == VERSAO_REFERENCIA and estado['canal'] == canal
            and estado['ultimo'] == _digital_edicao(conj)
            and all(isinstance(d.get('objeto'), bpy.types.Object)
                    and isinstance(d.get('malha'), bpy.types.Mesh)
                    for d in estado['pecas'].values())):
        # Dimension changes move the origin; only EXTERNAL movement should
        # transform the original reference.
        delta = conj.matrix_world @ _matriz_gravada(estado['fim']).inverted()
        mundo = delta @ _matriz_gravada(estado['inicio'])
        ocupado=_chapas._ocupado[0]
        _chapas._ocupado[0] = True
        try:
            filhos = {o: o.matrix_world.copy() for o in conj.children}
            conj.matrix_world = mundo
            bpy.context.view_layer.update()
            for o, m in filhos.items():
                o.matrix_world = m
            for d in estado['pecas'].values():
                o = d['objeto']
                velha = o.data
                _frentes.copiar_rotulos(velha,d['malha'])
                if chave[0]=='JUNTA' and velha.users==1:
                    # Angle editing retains the ID used by undo.
                    bm=bmesh.new()
                    try:bm.from_mesh(d['malha']);bm.to_mesh(velha)
                    finally:bm.free()
                else:
                    o.data = d['malha'].copy()
                    if velha.users == 0:
                        bpy.data.meshes.remove(velha)
                o.matrix_world = mundo @ _matriz_gravada(d['matriz'])
                o.chapa_largura_mm, o.chapa_comprimento_mm, o.chapa_espessura_mm = d['medidas']
                if 'centro_folha' in d:
                    o[_portas._ferragens.CHAVE_CENTRO_FOLHA]=list(d['centro_folha'])
            for d in estado['grupos'].values():
                o = d.get('objeto')
                if isinstance(o, bpy.types.Object):
                    o.matrix_world = mundo @ _matriz_gravada(d['matriz'])
                    if _gavetas.MARCA_GRUPO in o and 'parametros' in d:
                        if d.get('referencia'):
                            o[_gavetas.CHAVE_REFERENCIA]=list(d['referencia'])
                        elif _gavetas.CHAVE_REFERENCIA in o:del o[_gavetas.CHAVE_REFERENCIA]
                        if _gavetas.CHAVE_ENCAIXE in o:del o[_gavetas.CHAVE_ENCAIXE]
                        o[_gavetas.CHAVE_MARGENS]=list(d['margens'])
                        p=d['parametros'].to_dict()
                        if (any(abs(a-b)>.01 for a,b in zip(o[_gavetas.CHAVE_VAO],d['vao']))
                                or _gavetas.parametros(o)!=p):
                            _gavetas._reencaixar_existentes(o,*d['vao'],p)
                    if _prateleiras.MARCA_GRUPO in o and 'prateleiras' in d:
                        dados=d['prateleiras'].to_dict()
                        if _prateleiras.CHAVE_ENCAIXE in o:del o[_prateleiras.CHAVE_ENCAIXE]
                        for chave,valor in dados.items():o[chave]=valor
                    if _chapas.MARCA_PORTAS in o and 'porta' in d:
                        for chave in list(o.keys()):
                            if chave.startswith('porta_vao_'):del o[chave]
                        for chave,valor in d['porta'].items():
                            o[chave]=_portas._copiar_parametros(valor)
            # Restore parents before children's world matrices.
            # Shelves previously received origin compensation TWICE.
            bpy.context.view_layer.update()
            for d in estado['pecas'].values():
                d['objeto'].matrix_world=mundo @ _matriz_gravada(d['matriz'])
        finally:
            _chapas._ocupado[0] = ocupado
        bpy.context.view_layer.update()
        _cache.pop(conj.name, None)
        return
    if chave[0]=='ANG':
        _marcar_aresta_angular(conj,chave[1],plano)
    # Discarded references must not accumulate orphan meshes.
    antigas = [d.get('malha') for d in estado['pecas'].values()] if estado else []
    inv = matriz_do_modulo(conj).inverted()
    pecas = {str(i): dict(objeto=o, malha=o.data.copy(),
                         matriz=_gravar_matriz(inv @ (_portas._ferragens._matriz_fechada(o)
                                  if o.get('porta_curva_modelada') else o.matrix_world)),
                         medidas=[o.chapa_largura_mm, o.chapa_comprimento_mm, o.chapa_espessura_mm])
             for i, o in enumerate(_pecas_da_edicao(conj))}
    for d in pecas.values():
        o=d['objeto']
        if o.get('porta_curva_modelada') and _portas._ferragens.CHAVE_CENTRO_FOLHA in o:
            d['centro_folha']=list(o[_portas._ferragens.CHAVE_CENTRO_FOLHA])
    grupos = {str(i): dict(objeto=o, matriz=_gravar_matriz(inv @ o.matrix_world))
              for i, o in enumerate(dict.fromkeys([o for o in conj.children if o.type=='EMPTY']
                                                  +_portas._portas_do_conjunto(conj)))}
    for d in grupos.values():
        o=d['objeto']
        if _gavetas.MARCA_GRUPO in o:
            d.update(parametros=_gavetas.parametros(o),vao=list(o[_gavetas.CHAVE_VAO]),
                     margens=list(o[_gavetas.CHAVE_MARGENS]),
                     referencia=list(o.get(_gavetas.CHAVE_REFERENCIA,())))
        if _chapas.MARCA_PORTAS in o:
            d['porta']={chave:_portas._copiar_parametros(o[chave]) for chave in o.keys()
                        if chave.startswith('porta_vao_')}
        if _prateleiras.MARCA_GRUPO in o:
            d['prateleiras']={chave:_portas._copiar_parametros(o[chave]) for chave in (
                _prateleiras.CHAVE_PARAMETROS,_prateleiras.CHAVE_MARGENS,_prateleiras.CHAVE_VAO,
                _prateleiras.CHAVE_ENCAIXE) if chave in o}
    conj[CHAVE_EDICAO] = dict(versao=VERSAO_REFERENCIA,canal=canal, inicio=_gravar_matriz(matriz_do_modulo(conj)),
                             fim=_gravar_matriz(conj.matrix_world), ultimo='',
                             pecas=pecas, grupos=grupos)
    for m in antigas:
        if isinstance(m, bpy.types.Mesh) and m.users == 0:
            bpy.data.meshes.remove(m)
    _cache.pop(conj.name,None)


def esquecer():
    _cache.clear()


def matriz_do_modulo(conj, plano='XY'):
    # Quaternion conversion loses reflection and restored references without Mirror.
    matriz=conj.matrix_world.to_3x3().normalized().to_4x4()
    matriz.translation=conj.matrix_world.translation
    return matriz @ _base_do_plano(plano)


def _pecas(conj):
    """Body panels and curved parts contributing to the plan outline."""
    if conj.type=='MESH' and _chapas.MARCA_CHAPA in conj:return [conj]
    return [o for o in conj.children_recursive if o.type == 'MESH' and (
        o.get('porta_curva_modelada') or _prateleiras.MARCA_PRATELEIRA in o or (o.parent == conj and (
        (_chapas.MARCA_CHAPA in o and not _chapas.eh_dependente(o))
        or MARCA_CURVA in o)))]


def _assinatura(conj, pecas):
    def matriz(m):
        return tuple(round(v, 6) for linha in m for v in linha)
    return (matriz(conj.matrix_world),) + tuple(
        (o.name, matriz(_portas._ferragens._matriz_fechada(o) if o.get('porta_curva_modelada') else o.matrix_world), len(o.data.vertices),
         round(getattr(o, 'chapa_largura_mm', 0.0), 3),
         round(getattr(o, 'chapa_comprimento_mm', 0.0), 3)) for o in pecas)


def _marcar_aresta_angular(conj,k,plano='XY'):
    """A native edge retains identity when a chamfer becomes straight.
    Store no index: subdivision/editing transports its EDGE attribute.
    """
    forma=forma_do_modulo(conj,plano)
    if forma is None or forma['cantos'][k] is None:return
    pa,pb=pontas_diagonal(forma,k);inv=matriz_do_modulo(conj,plano).inverted()
    for o in _pecas(conj):
        m=inv@o.matrix_world
        if abs(m.to_3x3().col[2].normalized().z)<.99:continue
        for e in o.data.edges:
            a,b=[(m@o.data.vertices[i].co*1000).xy for i in e.vertices]
            if min((a-pa).length+(b-pb).length,(a-pb).length+(b-pa).length)>.1:
                continue
            nome=_atributo_angular(plano)
            atributo=o.data.attributes.get(nome)
            if atributo is None:atributo=o.data.attributes.new(nome,'INT','EDGE')
            atributo.data[e.index].value=k+1
    _cache.pop(conj.name,None)


def _planta(conj, pecas, plano='XY'):
    """(2D polygons, lo, hi) in cabinet-space mm. Horizontal panels use
    their actual notched/curved outline; other parts use the convex
    hull of their projection."""
    inversa = matriz_do_modulo(conj,plano).inverted()
    poligonos, todos, deitadas, bordas, marcadas = [], [], [], [], []
    for o in pecas:
        # Integrated fronts follow the body. Their thickness and clearance
        # must not enlarge the plan used to measure the cabinet.
        if o.get('porta_curva_modelada') and o.parent and o.parent.get('porta_perfil_corpo'):
            continue
        fechado=_portas._ferragens._matriz_fechada(o) if o.get('porta_curva_modelada') else o.matrix_world
        mundo = inversa @ fechado
        pts = [mundo @ v.co * 1000.0 for v in o.data.vertices]
        if not pts:
            continue
        todos += pts
        eixo_z = (mundo.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
        faces = []
        if o.get('porta_curva_modelada'):
            faces=[[(pts[i].x,pts[i].y) for i in f.vertices] for f in o.data.polygons
                   if (mundo.to_3x3() @ f.normal).z>.99]
        if _chapas.MARCA_CHAPA in o and abs(eixo_z.z) > 0.99:
            faces = [[(pts[i].x, pts[i].y) for i in f.vertices]
                     for f in o.data.polygons if f.normal.z > 0.99]
            deitadas += faces
            # Identity only during extraction. The cache stores vectors, never
            # indices; coplanar triangles must not create false sides.
            contagens={}
            for face in o.data.polygons:
                if face.normal.z<=.99:continue
                for aresta in face.edge_keys:
                    chave=tuple(sorted(aresta))
                    contagens[chave]=contagens.get(chave,0)+1
            bordas.extend((pts[i].xy,pts[j].xy,o.name)
                          for (i,j),n in contagens.items() if n==1)
            atributo=o.data.attributes.get(_atributo_angular(plano))
            if atributo is not None:
                for e in o.data.edges:
                    k=atributo.data[e.index].value-1
                    if 0<=k<4:
                        i,j=e.vertices
                        marcadas.append((k,pts[i].xy,pts[j].xy,o.name))
        if not faces:
            planos = [(p.x, p.y) for p in pts]
            faces = [[planos[i] for i in convex_hull_2d(planos)]]
        poligonos += faces
    if not todos:
        return None
    lo = Vector([min(p[i] for p in todos) for i in range(3)])
    hi = Vector([max(p[i] for p in todos) for i in range(3)])
    return poligonos, lo, hi, deitadas, bordas, marcadas


def _cortes(poligonos, eixo, valor):
    """Where the line with coordinate `eixo` = value crosses edges:
    return the OTHER coordinate at each crossing."""
    outro = 1 - eixo
    saida = []
    for pol in poligonos:
        for i in range(len(pol)):
            a, b = pol[i - 1], pol[i]
            da, db = a[eixo] - valor, b[eixo] - valor
            if da == db:
                if da == 0:
                    saida += [a[outro], b[outro]]
                continue
            if da * db <= 0:
                f = da / (da - db)
                saida.append(a[outro] + f * (b[outro] - a[outro]))
    return saida


def _recuo(poligonos, lo, hi, k, eixo, t):
    """Distance in mm from corner k to the first part along `eixo`,
    on a line `t` mm from the box side."""
    sx, sy = QUINAS[k]
    if eixo == 0:
        y = hi.y - t if sy > 0 else lo.y + t
        xs = _cortes(poligonos, 1, y)
        if not xs:
            return hi.x - lo.x
        return max(0.0, hi.x - max(xs) if sx > 0 else min(xs) - lo.x)
    x = hi.x - t if sx > 0 else lo.x + t
    ys = _cortes(poligonos, 0, x)
    if not ys:
        return hi.y - lo.y
    return max(0.0, hi.y - max(ys) if sy > 0 else min(ys) - lo.y)


def _feicao(poligonos, lo, hi, k, tolerancia=TOL_FORMA_MM):
    """Missing corner k: None or {'tipo', 'a' (X leg), 'b' (Y leg)}.
    Halfway along b, setback is ~a for a notch, ~a/2 for a diagonal.
    Other profiles retain the mesh's free outline."""
    amostra=min(1.0,tolerancia/4)
    a = _recuo(poligonos, lo, hi, k, 0, amostra)
    b = _recuo(poligonos, lo, hi, k, 1, amostra)
    largura, fundo = hi.x - lo.x, hi.y - lo.y
    inteira_a, inteira_b = a > largura - TOL_FORMA_MM, b > fundo - TOL_FORMA_MM
    if a < tolerancia or b < tolerancia:
        return None
    meio = _recuo(poligonos, lo, hi, k, 0, b / 2.0)
    if inteira_a or inteira_b:
        # A DIAGONAL spanning a whole side (corner/end cabinet, where the white
        # line previously followed the box) or both sides (triangular cabinet):
        # chamfer only, with its full-side leg reaching the other corner
        # when that corner is sharp.
        if not 0.3 * a <= meio <= 0.75 * a:
            return None
        if inteira_a and largura - a <= PONTA_AFIADA_MM:
            a = largura
        if inteira_b and fundo - b <= PONTA_AFIADA_MM:
            b = fundo
        return {'tipo': 'CHANFRO', 'a': a, 'b': b}
    if meio > 0.75 * a:
        # Notch rear (door/crosspiece), not the other arm's tip.
        b = _recuo(poligonos, lo, hi, k, 1, a / 2.0)
        if min(meio, b) < RECORTE_MINIMO_MM:
            return None
        return {'tipo': 'RECORTE', 'a': meio, 'b': b}
    if meio >= 0.3 * a:
        return {'tipo': 'CHANFRO', 'a': a, 'b': b}
    # Rounded profiles retain modeled edges. Do not infer circles
    # or offer radial deformation from sampled points.
    return None


def _perfil_contem_pecas(forma,poligonos,margem):
    corpo=forma
    perfil=[Vector(p[:2]) for p in contorno(corpo)]
    trechos=[(a,b) for a,b in zip(perfil,perfil[1:]+perfil[:1]) if (b-a).length>.01]
    vistos=set()
    for p in (Vector(p) for pol in poligonos for p in pol):
        chave=tuple(round(c,2) for c in p)
        if chave in vistos:continue
        vistos.add(chave)
        if intervalos_no_perfil(corpo,p,p):continue
        apoiado=False
        for a,b in trechos:
            d=b-a;t=max(0.,min(1.,(p-a).dot(d)/d.length_squared))
            if (p-a-d*t).length<=margem:
                apoiado=True;break
        if not apoiado:return False
    return True


def _detectar_planos_curvos(conj,pecas):
    """Structural-face edges only: doors/shelves do not define the body.
    Counts eliminate triangulation diagonals without changing Mesh.
    Per-plane projection preserves actual tilt in the other elevation.
    """
    if conj.type=='MESH':return ()
    inv=matriz_do_modulo(conj).inverted();curvos=set()
    for o in pecas:
        if (o.parent!=conj or _chapas.MARCA_CHAPA not in o or
                _chapas.eh_dependente(o) or _chapas.MARCA_FOLHA in o or
                _prateleiras.MARCA_PRATELEIRA in o):continue
        contagens={}
        for face in o.data.polygons:
            if face.normal.z<.99:continue
            for par in face.edge_keys:
                chave=tuple(sorted(par));contagens[chave]=contagens.get(chave,0)+1
        bordas=[par for par,n in contagens.items() if n==1]
        if len(bordas)<5:continue
        m=inv@o.matrix_world
        pts={i:m@o.data.vertices[i].co*1000 for par in bordas for i in par}
        normal=m.to_3x3().col[2].normalized()
        principal=max(range(3),key=lambda e:abs(normal[e]))
        for plano,eixos,fora in (('XY',(0,1),2),('XZ',(0,2),1),('YZ',(1,2),0)):
            # An inclined cap remains a cap: its curved projections must not
            # make both elevations rounded too.
            if plano in curvos or fora!=principal:continue
            segmentos=[tuple(Vector((pts[i][eixos[0]],pts[i][eixos[1]],0)) for i in par) for par in bordas]
            extensao=max(max(p[e] for p in pts.values())-min(p[e] for p in pts.values()) for e in eixos)
            if _frentes.contorno_tem_curva(segmentos,extensao_minima=max(30.,extensao*.1)):curvos.add(plano)
    return tuple(sorted(curvos))


def planos_curvos(conj):
    forma_do_modulo(conj)
    memoria=_cache.get(conj.name)
    return memoria[1].get('planos_curvos',()) if memoria else ()


def forma_do_modulo(conj, plano='XY'):
    """Return {'lo', 'hi' (cabinet-space mm), 'cantos': [4 x feature]},
    or None for boxes/free outlines using native blockout edges."""
    if conj is None or not (_chapas.MARCA_CONJUNTO in conj or
            (conj.type=='MESH' and _chapas.MARCA_CHAPA in conj)):
        return None
    pecas = _pecas(conj)
    if len(pecas) < (1 if conj.type=='MESH' else 2):
        return None
    assinatura = _assinatura(conj, pecas)
    guardado = _cache.get(conj.name)
    if guardado is None or guardado[0] != assinatura:
        guardado=(assinatura,{'planos_curvos':_detectar_planos_curvos(conj,pecas)})
        _cache[conj.name]=guardado
    if plano in guardado[1]:
        return guardado[1][plano]
    forma = None
    planta = _planta(conj, pecas, plano)
    guardado[1][('planta',plano)]=planta
    if planta is not None and plano not in guardado[1]['planos_curvos']:
        poligonos, lo, hi, deitadas, bordas, marcadas = planta
        tolerancia=TOL_FORMA_MM if plano=='XY' and conj.type!='MESH' else .1
        cantos = [_feicao(poligonos, lo, hi, k,tolerancia) for k in range(4)]
        for k, f in enumerate(cantos):
            referencia=[(a,b,dono) for ki,a,b,dono in marcadas if ki==k]
            if referencia and f is None:
                f=cantos[k]=dict(tipo='CHANFRO')
            if f is not None and f['tipo'] == 'CHANFRO':
                _diagonal_real(deitadas or poligonos, lo, hi, k, f, bordas, referencia,tolerancia)
                if 'pontas' not in f:cantos[k]=None
        if any(cantos):
            forma = {'lo': lo, 'hi': hi, 'cantos': cantos, 'plano': plano}
            # One tilted edge is insufficient: other panels may lie outside
            # the profile after partial Tab editing.
            # Never trim wood to an idealized model of its neighbor.
            margem=max((getattr(o,'chapa_espessura_mm',0.) for o in pecas),default=0.)+.1
            if forma is not None and not _perfil_contem_pecas(forma,poligonos,margem):forma=None
    guardado[1][plano] = forma
    return forma


def _uniao_da_secao(poligonos):
    """Native CDT resolves overlaps, concavities and islands. Include only
    triangles covered by a panel; never fill voids with the group's
    convex hull or draw triangulation.
    """
    pts,faces=[],[]
    for pol in poligonos:
        area=sum(p[0]*q[1]-p[1]*q[0] for p,q in zip(pol,pol[1:]+pol[:1]))
        if abs(area)<.0001:continue
        face=list(range(len(pts),len(pts)+len(pol)))
        pts.extend(Vector(p) for p in pol)
        faces.append(face if area>0 else face[::-1])
    if not faces:return [],0.
    vs,_es,fs,_ov,_oe,orig=delaunay_2d_cdt(pts,[],faces,1,.01)
    contagens={};area=0.
    for face,ids in zip(fs,orig):
        if not ids:continue
        area+=abs(sum(vs[i].x*vs[j].y-vs[i].y*vs[j].x
                      for i,j in zip(face,face[1:]+face[:1])))/2
        for i,j in zip(face,face[1:]+face[:1]):
            par=tuple(sorted((i,j)))
            contagens[par]=contagens.get(par,0)+1
    bordas=[(vs[i],vs[j]) for (i,j),n in contagens.items()
            if n==1 and (vs[i]-vs[j]).length>.01]
    return bordas,area


def _na_borda_da_secao(p,bordas):
    for a,b in bordas:
        d=b-a;t=max(0.,min(1.,(p-a).dot(d)/d.length_squared))
        if (p-a-d*t).length<.02:return True
    return False


def blocagem_do_modulo(conj):
    """Two sides support the outline, not the front's tessellation.
    Outer faces trace wood; inner faces define joints. The cache retains
    only numbers/names, including after Tab and undo.
    """
    forma_do_modulo(conj)
    memoria=_cache.get(conj.name)
    if memoria is None:return None
    dados=memoria[1]
    if 'blocagem' in dados:return dados['blocagem']
    inv=matriz_do_modulo(conj).inverted();candidatos={0:[],1:[]}
    pecas=[o for o in _pecas(conj) if o.parent==conj and _chapas.MARCA_CHAPA in o
           and not _chapas.eh_dependente(o) and not o.get('porta_curva_modelada')]
    pontos={o:[inv@o.matrix_world@v.co*1000 for v in o.data.vertices] for o in pecas}
    altura=max((p.z for vs in pontos.values() for p in vs),default=0)-min(
               (p.z for vs in pontos.values() for p in vs),default=0)
    for o,vs in pontos.items():
        if not vs or max(p.z for p in vs)-min(p.z for p in vs)<altura*.45:continue
        m=inv@o.matrix_world;n=m.to_3x3().col[2].normalized()
        eixo=max((0,1),key=lambda i:abs(n[i]))
        if abs(n[eixo])<.35 or abs(n.z)>.94:continue
        candidatos[eixo].append((o,m,sum(vs,Vector())/len(vs),n))
    pares=[]
    for eixo,cs in candidatos.items():
        for i,a in enumerate(cs):
            for b in cs[i+1:]:
                distancia=abs(a[2][eixo]-b[2][eixo])
                if distancia<2*max(a[0].chapa_espessura_mm,b[0].chapa_espessura_mm):continue
                area=min(o.chapa_largura_mm*o.chapa_comprimento_mm for o in (a[0],b[0]))
                pares.append((distancia*area,eixo,sorted((a,b),key=lambda c:c[2][eixo])))
    dados['blocagem']=None
    if not pares:return None
    _peso,eixo,par=max(pares,key=lambda p:p[0]);outro=1-eixo
    externos=[None]*8;internos=[None]*8;planos=[];nomes=[]
    for lado,(o,m,centro,n) in enumerate(par):
        baixo=min(v.co.z for v in o.data.vertices);alto=max(v.co.z for v in o.data.vertices)
        fora=alto if n[eixo]*(1 if lado else -1)>0 else baixo
        dentro=baixo if fora==alto else alto
        for z,saida in ((fora,externos),(dentro,internos)):
            vs=[m@v.co*1000 for v in o.data.vertices if abs(v.co.z-z)<.00005]
            if len(vs)<4:return None
            # Sides may be trapezoidal. Four planar extrema preserve tilt
            # without multiplying outline vertices.
            h0,h1=min(p[outro] for p in vs),max(p[outro] for p in vs)
            z0,z1=min(p.z for p in vs),max(p.z for p in vs)
            usados=set()
            for h in (0,1):
                for v in (0,1):
                    ponto=max(vs,key=lambda p:(1 if h else -1)*(p[outro]-h0)/max(h1-h0,.01)
                              +(1 if v else -1)*(p.z-z0)/max(z1-z0,.01))
                    chave=tuple(round(x,4) for x in ponto)
                    if chave in usados:return None
                    usados.add(chave)
                    bits=[0,0,v];bits[eixo]=lado;bits[outro]=h
                    saida[bits[0]+2*bits[1]+4*bits[2]]=tuple(ponto)
        normal=n if dentro==alto else -n
        ponto=m@Vector((0,0,dentro))*1000
        planos.append((tuple(normal),normal.dot(ponto)))
        nomes.append(o.name)
    # Rectangularize only the rounded projection. Other components retain,
    # for example, an inclined ceiling above a curved front.
    envolvente=[list(p) for p in externos]
    for plano in dados['planos_curvos']:
        eixos={'XY':(0,1),'XZ':(0,2),'YZ':(1,2)}[plano]
        fora=next(i for i in range(3) if i not in eixos)
        for nivel in (0,1):
            indices=[i for i in range(8) if bool(i&(1<<fora))==bool(nivel)]
            for e in eixos:
                lo=min(externos[i][e] for i in indices);hi=max(externos[i][e] for i in indices)
                for i in indices:envolvente[i][e]=hi if i&(1<<e) else lo
    dados['blocagem']=dict(eixo=eixo,cantos=externos,internos=internos,apoios=planos,nomes=nomes,
                          planos_curvos=dados['planos_curvos'],cantos_hud=[tuple(p) for p in envolvente])
    return dados['blocagem']


def dados_junta(conj,chave,bloco=None):
    bloco=blocagem_do_modulo(conj) if bloco is None else bloco
    if bloco is None:raise ValueError("The side panels no longer define this joint")
    _tipo,s,t,indice=chave
    if s!=bloco['eixo']:raise ValueError("The joint support has changed")
    ps=[Vector(p) for p in bloco['internos']]
    a,b,c,d=(ps[i] for i in (indice,indice^(1<<s),indice^(1<<t),indice^(1<<s)^(1<<t)))
    u=c-a;v=b-a
    if min(u.length,v.length)<.01:raise ValueError("The joint has no free length")
    angulo=math.degrees(u.angle(v))
    return dict(a=a,b=b,c=c,d=d,s=s,t=t,angulo=angulo,bloco=bloco)


def blocagem_cobre_estrutura(conj,bloco):
    """Recognize a body between two sides without closing an L or extra
    corner with a chord. Native convex hull ONCE per signature; curved
    fronts/shelves do not define support topology.
    """
    if 'cobre_estrutura' in bloco:return bloco['cobre_estrutura']
    bm=bmesh.new()
    try:
        vs=[bm.verts.new(p) for p in bloco['cantos']]
        bmesh.ops.convex_hull(bm,input=vs);bm.normal_update()
        centro=sum((v.co for v in bm.verts),Vector())/len(bm.verts)
        planos=[]
        for face in bm.faces:
            n=face.normal.copy();p=face.verts[0].co
            if n.dot(p-centro)<0:n.negate()
            planos.append((n,n.dot(p)))
        if len(planos)<4:
            bloco['cobre_estrutura']=False;return False
        inv=matriz_do_modulo(conj).inverted()
        for o in _pecas(conj):
            if o.parent!=conj or _chapas.MARCA_CHAPA not in o or _chapas.eh_dependente(o):continue
            m=inv@o.matrix_world
            if abs(m.to_3x3().col[2].normalized().z)>.94:continue
            margem=o.chapa_espessura_mm*1.1+.1
            for v in o.data.vertices:
                p=m@v.co*1000
                if any(n.dot(p)-d>margem for n,d in planos):
                    bloco['cobre_estrutura']=False;return False
        bloco['cobre_estrutura']=True
        return True
    finally:bm.free()


def _delta_da_junta(j,graus):
    a,b,c,d,s,t=(j[k] for k in ('a','b','c','d','s','t'))
    u=(c-a).normalized();v=d-a;w=b-d
    # Intersect the support line with the angle cone. With additional
    # tilts, the line may lie outside the corner's Cartesian plane.
    # This is a scalar quadratic: no mesh queries or vertex iteration.
    def dot(x,y):return math.fsum(float(p)*float(q) for p,q in zip(x,y))
    cos=math.cos(math.radians(float(graus)));uv,uw=dot(u,v),dot(u,w)
    vv,vw,ww=dot(v,v),dot(v,w),dot(w,w)
    if ww<.0001:raise ValueError("The support has no free length")
    if abs(cos)<1e-8:
        raizes=[-uv/uw] if abs(uw)>1e-9 else ([1.] if abs(uv)<.001 else [])
    else:
        A=uw*uw-cos*cos*ww;B=2*(uv*uw-cos*cos*vw);C=uv*uv-cos*cos*vv
        if abs(A)<ww*1e-12:raizes=[-C/B] if abs(B)>1e-9 else []
        else:
            discriminante=B*B-4*A*C
            if discriminante<0:raizes=[]
            else:
                q=-.5*(B+math.copysign(math.sqrt(discriminante),B))
                raizes=[q/A,C/q] if abs(q)>1e-12 else [-B/(2*A)]
    validas=[]
    for t in raizes:
        if t*math.sqrt(ww)<20:continue
        ponto=v+w*t
        if ponto.length<.01:continue
        if abs(dot(u,ponto)/ponto.length-cos)>1e-5:continue
        validas.append(t)
    if not validas:raise ValueError("The angle does not fit between the supports")
    t=min(validas,key=lambda t:abs(t-1.))
    return d+w*t-b


def aplicar_angulo_junta(context,conj,chave,graus):
    """Rotate the reference about the INNER vertex and trim at the support
    face. A single deformation transports the assembly; reconstruct each
    panel section along its normal without thickening, shearing or welding.
    """
    if not 1<float(graus)<179:raise ValueError("The angle must be between 1 and 179 degrees")
    # Reject inverted supports before restoring the reference: impossible
    # input must not change the last confirmed angle.
    _delta_da_junta(dados_junta(conj,chave),graus)
    _preparar_edicao(conj,chave,None)
    j=dados_junta(conj,chave);a,b,c,d,s,t=(j[k] for k in ('a','b','c','d','s','t'))
    delta=_delta_da_junta(j,graus)
    def desloc(ponto):
        u=max(0.,min(1.,(ponto[s]-a[s])/(b[s]-a[s])))
        inicio=c[t]+u*(d[t]-c[t]);fim=a[t]+u*(b[t]-a[t])
        v=max(0.,min(1.,(ponto[t]-inicio)/(fim-inicio)))
        return delta*u*v
    _deformar(conj,desloc,conservar_espessura=True,apoios=dict(j['bloco'],ancora=tuple((a+b)/2)))
    _concluir_transformacao(context,conj)


def estrutura_hud(conj):
    """Free outline when no parametric shape is recognized. Prepare once per
    signature/Tab. Numeric cache only; BMesh/CDT read native geometry
    without changing Mesh, UVs, properties or selection.
    """
    for plano in ('XY','XZ','YZ'):forma_do_modulo(conj,plano)
    guardado=_cache.get(conj.name)
    if guardado is None:return None
    dados=guardado[1]
    if 'estrutura' in dados:return dados['estrutura']
    perfis=[];livre=False
    for plano in ('XY','XZ','YZ'):
        planta=dados.get(('planta',plano))
        if planta is None:continue
        pol,lo,hi=planta[:3]
        bordas,area=_uniao_da_secao(pol)
        perfis.append((_base_do_plano(plano).to_3x3().transposed(),bordas))
        l,p=hi.x-lo.x,hi.y-lo.y
        obliqua=any(min(abs(b.x-a.x),abs(b.y-a.y))>.05 for a,b in bordas)
        # Assembly gaps in an orthogonal box are not body deformation.
        # An unclassified oblique profile needs its actual outline even
        # with strips or other steps along the same perimeter.
        livre=livre or (obliqua and l*p-area>.02*(l+p))
    if not livre:
        dados['estrutura']=None
        return None
    inv=matriz_do_modulo(conj).inverted();arestas={}
    for o in sorted(_pecas(conj),key=lambda o:o.get('chapa_uid',o.name)):
        # An articulated leaf is not body geometry. Its closed outline appears
        # separately in door HUD, never as fixed cabinet wood.
        if o.get('porta_curva_modelada'):continue
        m=inv@(_portas._ferragens._matriz_fechada(o)
               if o.get('porta_curva_modelada') else o.matrix_world)
        bm=bmesh.new()
        try:
            bm.from_mesh(o.data);bm.normal_update()
            if not bm.verts:continue
            lo=Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
            hi=Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
            def referencia(v):
                # Local fractions identify the edge during drag;
                # retain no native indices or objects in the cache.
                return tuple(round((v.co[i]-lo[i])/max(hi[i]-lo[i],1e-9),4) for i in range(3))
            for e in bm.edges:
                if len(e.link_faces)==2 and abs(e.link_faces[0].normal.dot(e.link_faces[1].normal))>.99999:
                    continue
                a,b=[m@v.co*1000 for v in e.verts]
                if (b-a).length<.01:continue
                if not any(_na_borda_da_secao((base@((a+b)/2)).xy,bs) for base,bs in perfis):
                    continue
                chave=tuple(sorted((tuple(round(v,2) for v in a),tuple(round(v,2) for v in b))))
                ref=tuple(sorted(referencia(v) for v in e.verts))
                arestas.setdefault(chave,dict(a=tuple(a),b=tuple(b),
                         referencia=(o.get('chapa_uid',o.name),ref)))
        finally:bm.free()
    dados['estrutura']=list(arestas.values())
    return dados['estrutura']


# ------------------------------------------------------------ outline
def _diagonal_real(poligonos, lo, hi, k, f, bordas=(), referencia=(),tolerancia=TOL_FORMA_MM):
    """1 mm samples detect shape, not panel endpoints. Actual edges end
    at the side's inner face even when BOTH ends are inset by thickness.
    Measure once into the cache.
    """
    sx, sy = QUINAS[k]
    xc, yc = (hi.x if sx > 0 else lo.x), (hi.y if sy > 0 else lo.y)
    candidatos = []
    segmentos=(bordas or [(p,q,None) for pol in poligonos
                          for p,q in zip(pol,pol[1:]+pol[:1])])
    for p, q, dono in (referencia or segmentos):
            a, b = sorted((Vector(p), Vector(q)),
                          key=lambda v:(round(abs(v.y-yc),2),-abs(v.x-xc)))
            dx, dy = abs(a.x - b.x), abs(a.y - b.y)
            if not referencia and (min(dx, dy) < tolerancia or (a.x-b.x)*(a.y-b.y)*sx*sy >= 0):
                continue
            if not referencia and (abs(a.y-yc) > ESPESSURA_PONTA_MM or abs(b.x-xc) > ESPESSURA_PONTA_MM):
                continue
            if not referencia and (abs(abs(a.x-xc)-f['a']) > ESPESSURA_PONTA_MM or abs(abs(b.y-yc)-f['b']) > ESPESSURA_PONTA_MM):
                continue
            candidatos.append(((a-b).length, a, b, dono))
    if candidatos:
        _, a, b, dono = max(candidatos, key=lambda c: c[0])
        f.update(a=abs(a.x-xc), b=abs(b.y-yc), pontas=(tuple(a), tuple(b)))
        lados=[]
        for ponto,outra in ((a,b),(b,a)):
            anterior=outra;atual=ponto
            for _ in range(len(segmentos)):
                pares=[Vector(q) if (Vector(p)-atual).length<.05 else Vector(p)
                       for p,q,d in segmentos if d==dono and
                       ((Vector(p)-atual).length<.05 or (Vector(q)-atual).length<.05)]
                pares=[p for p in pares if (p-anterior).length>.05]
                if not pares:break
                proximo=pares[0];trecho=proximo-atual
                if trecho.length>ESPESSURA_PONTA_MM:
                    lados.append((tuple(trecho.normalized()),trecho.length));break
                anterior,atual=atual,proximo
        if len(lados)==2:f['lados']=lados


def pontas_diagonal(forma, k):
    f = forma['cantos'][k]
    if 'pontas' in f:
        return tuple(Vector(p) for p in f['pontas'])
    sx, sy = QUINAS[k]
    xc, yc = _quina(forma, k)
    return Vector((xc-sx*f['a'], yc)), Vector((xc, yc-sy*f['b']))


def angulo_diagonal(forma, k):
    a, b = pontas_diagonal(forma, k)
    return math.degrees(math.atan2(abs(b.y-a.y), abs(b.x-a.x)))


def lado_da_ponta(forma, k, ponta):
    """Actual neighboring-side direction beyond thickness segments.
    HUD and typed input share this numeric reference; no Mesh in redraw.
    """
    lados=forma['cantos'][k].get('lados')
    if lados:
        direcao,comprimento=lados[0 if ponta=='A' else 1]
        return Vector(direcao),comprimento
    pa, pb = pontas_diagonal(forma, k)
    vertice, outra = (pa, pb) if ponta == 'A' else (pb, pa)
    pontos = []
    for x, y, _ in contorno(forma):
        p = Vector((x, y))
        if not pontos or (p-pontos[-1]).length > 1.0:
            pontos.append(p)
    if len(pontos)>1 and (pontos[0]-pontos[-1]).length<=1.0:
        pontos.pop()
    n=len(pontos)
    i=min(range(n),key=lambda j:(pontos[j]-vertice).length)
    for passo in (-1,1):
        anterior=vertice
        for j in range(1,n):
            p=pontos[(i+j*passo)%n]
            if (p-outra).length<=1.0:break
            trecho=p-anterior
            if trecho.length>ESPESSURA_PONTA_MM:
                return trecho.normalized(),trecho.length
            anterior=p
    return None,0.0


def dados_angulo_da_ponta(forma, k, ponta):
    pa,pb=pontas_diagonal(forma,k)
    vertice,outra=(pa,pb) if ponta=='A' else (pb,pa)
    lado,_=lado_da_ponta(forma,k,ponta)
    if lado is None:raise ValueError("The corner has no supporting side")
    ate=(outra-vertice).normalized()
    giro=math.atan2(lado.x*ate.y-lado.y*ate.x,lado.dot(ate))
    sx,sy=QUINAS[k]
    sinal=(-sx*sy)*(1.0 if giro>=0 else -1.0)
    visto=math.degrees(abs(giro))
    return visto,visto-sinal*angulo_diagonal(forma,k),sinal


def aplicar_angulo_interno(context,conj,k,ponta,graus,plano='XY'):
    """Solve the angle between two edges, never a quantized basis.
    Each attempt restores the source Mesh through the existing ANG channel.
    """
    chave=('ANG',k)
    _preparar_edicao(conj,chave,None,plano)
    forma=forma_do_modulo(conj,plano)
    if forma is None or forma['cantos'][k] is None:
        raise ValueError("The corner no longer has a diagonal")
    anterior=angulo_diagonal(forma,k)
    _,base,sinal=dados_angulo_da_ponta(forma,k,ponta)
    alvo=(float(graus)-base)/sinal
    if not -.0001<=alvo<=90.0001:
        raise ValueError("This angle extends beyond the cabinet side")
    for _ in range(4):
        aplicar(context,conj,chave,max(0.,min(90.,alvo)),plano=plano)
        forma=forma_do_modulo(conj,plano)
        # At extremes the diagonal becomes an orthogonal corner and ceases
        # to be a CHANFRO feature; the native reference allows returning.
        visto=(dados_angulo_da_ponta(forma,k,ponta)[0]
               if forma and forma['cantos'][k] else 90.0)
        erro=float(graus)-visto
        if abs(erro)<=.01:return
        alvo+=erro/sinal
    aplicar(context,conj,chave,anterior,plano=plano)
    raise ValueError("The angle does not fit with the cabinet's current clearances")


def _quina(forma, k):
    sx, sy = QUINAS[k]
    lo, hi = forma['lo'], forma['hi']
    return (hi.x if sx > 0 else lo.x), (hi.y if sy > 0 else lo.y)


def _pontos_do_canto(forma, k):
    """Corner k points [(x, y, rises)] counterclockwise; rises means
    a vertical edge exists."""
    sx, sy = QUINAS[k]
    xc, yc = _quina(forma, k)
    f = forma['cantos'][k]
    if f is None:
        return [(xc, yc, True)]
    a, b = f['a'], f['b']
    px, py = (xc - sx * a, yc), (xc, yc - sy * b)
    x_antes = sx * sy < 0          # Arrive along the horizontal side.
    primeiro, segundo = (px, py) if x_antes else (py, px)
    if f['tipo'] == 'RECORTE':
        return [(*primeiro, True), (xc - sx * a, yc - sy * b, True),
                (*segundo, True)]
    if f['tipo'] == 'CHANFRO':
        pa, pb = pontas_diagonal(forma, k)
        reais = (pa, pb) if x_antes else (pb, pa)
        saida = [(*primeiro, True)]
        for p in (*reais, segundo):
            if (Vector(p) - Vector(saida[-1][:2])).length > .01:
                saida.append((*p, True))
        return saida
    raise ValueError("Shape cannot be edited parametrically using straight segments")


def contorno(forma):
    """Plan points [(x, y, rises)] counterclockwise."""
    return [p for k in range(4) for p in _pontos_do_canto(forma, k)]


def intervalos_no_perfil(forma,a,b):
    """Clip a line using prepared numeric sections without reading Mesh.
    Parametric intersections preserve the same line across all three
    planes, even when an inclined top cuts a plan edge.
    """
    pol=[Vector(p[:2]) for p in contorno(forma)]
    a,b=Vector(a),Vector(b);d=b-a
    def cruz(u,v):return u.x*v.y-u.y*v.x
    def dentro(p):
        impar=False
        for u,v in zip(pol,pol[1:]+pol[:1]):
            e=v-u
            if e.length_squared>1e-12:
                t=max(0.,min(1.,(p-u).dot(e)/e.length_squared))
                if (p-u-e*t).length<.01:return True
            if (u.y>p.y)!=(v.y>p.y) and p.x<(v.x-u.x)*(p.y-u.y)/(v.y-u.y)+u.x:
                impar=not impar
        return impar
    if d.length<1e-6:return [(0.,1.)] if dentro(a) else []
    cortes=[0.,1.]
    for u,v in zip(pol,pol[1:]+pol[:1]):
        e=v-u;den=cruz(d,e)
        if abs(den)<1e-9:continue
        t,s=cruz(u-a,e)/den,cruz(u-a,d)/den
        if 0<t<1 and -.00001<=s<=1.00001:cortes.append(t)
    cortes=sorted(set(cortes))
    return [(u,v) for u,v in zip(cortes,cortes[1:])
            if v-u>1e-7 and dentro(a+d*((u+v)/2))]


def segmentos(forma):
    """Plan edges: {'a', 'b', 'chave', 'letra', 'direcao', 'cantos'}.
    `chave` None means outline only. Whole sides use total L/P min-to-max
    with box corners. Sides meeting a notch/diagonal use P1 (vertical) or
    P2 (horizontal), from outer endpoint `a` to moving endpoint `b`.
    Diagonals use R."""
    pontos = [_pontos_do_canto(forma, k) for k in range(4)]
    saida = []
    for k in range(4):
        f = forma['cantos'][k]
        sx, sy = QUINAS[k]
        for p, q in zip(pontos[k], pontos[k][1:]):
            if (Vector(p[:2]) - Vector(q[:2])).length < 1.0:
                continue
            seg = {'a': p[:2], 'b': q[:2], 'chave': None, 'letra': None,
                   'direcao': None, 'cantos': None}
            if f['tipo'] == 'CHANFRO' and min(abs(p[0]-q[0]), abs(p[1]-q[1])) > .01:
                raiz = math.sqrt(0.5)
                seg.update(chave=('R', k), letra='R',
                           direcao=(-sx * raiz, -sy * raiz))
            saida.append(seg)
        j = (k + 1) % 4
        g = forma['cantos'][j]
        p, q = pontos[k][-1][:2], pontos[j][0][:2]
        if (Vector(p) - Vector(q)).length < 1.0:
            continue                # The diagonal spans the whole side.
        horizontal = k in (0, 2)
        seg = {'a': p, 'b': q, 'chave': None, 'letra': None,
               'direcao': None, 'cantos': None}
        if f is None and g is None:
            eixo = 0 if horizontal else 1
            a, b = sorted((p, q), key=lambda c: c[eixo])
            if horizontal:
                nivel = 0 if k == 0 else 2
                cantos = (nivel, nivel + 1)
            else:
                cantos = (1, 3) if k == 1 else (0, 2)
            seg.update(a=a, b=b, chave=('L',) if horizontal else ('P',),
                       letra='L' if horizontal else 'P', cantos=cantos)
        elif (f is None) != (g is None):
            com, kc = (f, k) if f is not None else (g, j)
            if (com['tipo'] in ('RECORTE', 'CHANFRO')
                    and (Vector(p) - Vector(q)).length > ESPESSURA_PONTA_MM):
                # A shorter remainder is the panel tip where the diagonal ends.
                fora, dentro = (q, p) if f is not None else (p, q)
                letra = 'P2' if horizontal else 'P1'
                seg.update(a=fora, b=dentro, chave=(letra, kc), letra=letra)
        saida.append(seg)
    return saida


def valor(conj, chave, plano='XY'):
    """Dimension in mm displayed by HUD line `chave`."""
    forma = forma_do_modulo(conj,plano)
    if forma is None:
        raise ValueError("The cabinet no longer has this shape")
    if chave[0] == 'L':
        return forma['hi'].x - forma['lo'].x
    if chave[0] == 'P':
        return forma['hi'].y - forma['lo'].y
    if chave[0] == 'R':
        f = forma['cantos'][chave[1]]
        if f is None:
            raise ValueError("The corner no longer has a diagonal")
        if (plano!='XY' or conj.type=='MESH') and f['tipo']=='CHANFRO':
            a,b=pontas_diagonal(forma,chave[1])
            return (b-a).length
        return (f['a'] + f['b']) / 2.0
    if chave[0] == 'ANG':
        # Diagonal angle to the FRONT side, corresponding to leg a.
        f = forma['cantos'][chave[1]]
        if f is None or f['tipo'] != 'CHANFRO':
            raise ValueError("The corner no longer has a diagonal")
        return angulo_diagonal(forma, chave[1])
    for seg in segmentos(forma):
        if seg['chave'] == tuple(chave):
            return (Vector(seg['a']) - Vector(seg['b'])).length
    raise ValueError("The cabinet no longer has this dimension")


# ------------------------------------------------------------- editing
def _no_canto(forma, k, p):
    """(X', Y'): coordinates measured inward from corner k."""
    sx, sy = QUINAS[k]
    xc, yc = _quina(forma, k)
    return sx * (xc - p.x), sy * (yc - p.y)


def _reajustar(o, era_caixa, cima):
    """Restore edited panels to convention: mesh centered at origin, L/C in
    properties. Rebuild distorted boxes, such as diagonal doors with one
    end moved, by rotating about vertical and stretching."""
    malha = o.data
    # A section-defining panel may stop being rectangular. Rebuilding its
    # box would erase tilt when starting from 90 degrees or after append.
    no_perfil=abs(o.matrix_world.to_3x3().col[2].normalized().dot(cima))>.99
    if era_caixa and not no_perfil and not _chapas._malha_e_caixa(malha):
        _refazer_caixa(o, cima)
        return
    vs = malha.vertices
    lo = Vector([min(v.co[i] for v in vs) for i in range(3)])
    hi = Vector([max(v.co[i] for v in vs) for i in range(3)])
    centro = (lo + hi) / 2.0
    if centro.length > 1e-9:
        malha.transform(Matrix.Translation(-centro))
        o.matrix_world = o.matrix_world @ Matrix.Translation(centro)
    _chapas._ocupado[0] = True
    try:
        o.chapa_largura_mm = (hi.x - lo.x) * 1000.0
        o.chapa_comprimento_mm = (hi.y - lo.y) * 1000.0
    finally:
        _chapas._ocupado[0] = False
    malha.update()


def _refazer_caixa(o, cima):
    rot = o.matrix_world.to_3x3().normalized()
    eixos = [rot.col[i].normalized() for i in range(3)]
    vertical = max(range(3), key=lambda i: abs(eixos[i].dot(cima)))
    medidas = (o.chapa_largura_mm, o.chapa_comprimento_mm, o.chapa_espessura_mm)
    longo = max((i for i in range(3) if i != vertical), key=lambda i: medidas[i])
    if longo == 2:
        return
    mundo = o.matrix_world
    mais = [mundo @ v.co for v in o.data.vertices if v.co[longo] > 0]
    menos = [mundo @ v.co for v in o.data.vertices if v.co[longo] < 0]
    if not mais or not menos:
        return
    d = sum(mais, Vector()) / len(mais) - sum(menos, Vector()) / len(menos)
    d -= cima * d.dot(cima)
    velho = eixos[longo] - cima * eixos[longo].dot(cima)
    if d.length < 1e-6 or velho.length < 1e-6:
        return
    angulo = math.atan2(cima.dot(velho.cross(d)), velho.dot(d))
    nova = Matrix.Rotation(angulo, 3, cima) @ rot
    centro = sum((mundo @ v.co for v in o.data.vertices), Vector()) / len(o.data.vertices)
    _chapas._ocupado[0] = True
    try:
        setattr(o, ('chapa_largura_mm', 'chapa_comprimento_mm')[longo],
                d.length * 1000.0)
    finally:
        _chapas._ocupado[0] = False
    o.matrix_world = Matrix.LocRotScale(centro, nova.to_quaternion(),
                                        Vector((1.0, 1.0, 1.0)))
    o.data.clear_geometry()
    _chapas.gerar_malha_chapa(o)       # An empty mesh starts as a box.


def _deformar_chapa_com_secao(o,matriz,desloc,ancora,apoios):
    """Transport one face while retaining the other's NORMAL distance.
    Trim endpoints by support intersections, not a rotated box, allowing
    a single contact corner even with oblique sides.
    """
    inv=matriz.inverted();m=inv@o.matrix_world
    normal=m.to_3x3().col[2].normalized()
    zs=[v.co.z for v in o.data.vertices]
    z0,z1=min(zs),max(zs)
    if (z1-z0)*1000>o.chapa_espessura_mm*1.2+.1:return False
    centro=sum((m@v.co*1000 for v in o.data.vertices),Vector())/len(zs)
    z=z1 if (ancora-centro).dot(normal)>=0 else z0
    def mover(p):return p+desloc(p)
    origem=m@Vector((0,0,z))*1000
    q=mover(origem)
    hx=max(1.,o.chapa_largura_mm/2);hy=max(1.,o.chapa_comprimento_mm/2)
    dx=m.to_3x3().col[0].normalized()*hx
    dy=m.to_3x3().col[1].normalized()*hy
    x=(mover(origem+dx)-mover(origem-dx))/(2*hx)
    y=(mover(origem+dy)-mover(origem-dy))/(2*hy)
    n=x.cross(y).normalized()
    if n.length<.9:raise ValueError("The tilt eliminates the panel's cross-section")
    x.normalize();y=n.cross(x).normalized()
    rot=Matrix((x,y,n)).transposed()
    nova=Matrix.LocRotScale((q-n*z*1000)/1000,rot.to_quaternion(),Vector((1,1,1)))
    volta=nova.inverted();coords=[]
    for v in o.data.vertices:
        p=m@Vector((v.co.x,v.co.y,z))*1000
        original=m@v.co*1000
        # Profiles may contain cutouts: retain each vertex's displacement field,
        # projecting only the normal component so the face remains planar.
        ponto=mover(p)
        ponto-=n*n.dot(ponto-q)
        ponto+=n*(v.co.z-z)*1000
        for nome,normal_antes,dist_antes,normal_depois,dist_depois in apoios:
            if nome==o.name or abs(normal_antes.dot(original)-dist_antes)>.15:continue
            tangente=normal_depois-n*normal_depois.dot(n)
            den=normal_depois.dot(tangente)
            if den>1e-8:ponto+=tangente*((dist_depois-normal_depois.dot(ponto))/den)
        coords.extend(volta@(ponto/1000))
    if o.data.users>1:o.data=o.data.copy()
    o.data.vertices.foreach_set('co',coords);o.data.update()
    o.matrix_world=matriz@nova
    _reajustar(o,False,matriz.to_3x3().col[2].normalized())
    _frentes.preparar(o,forcar=True)
    return True


def _deformar(conj, desloc, rigida=None, reencaixar_paineis=False, plano='XY',
              conservar_espessura=False,apoios=None):
    """Apply `desloc(p) -> Vector` in cabinet-space mm to each part vertex.
    `rigida(pts, deslocs)` may return ONE displacement for the whole part
    to move rigidly. Ordinary accessories follow their own center displacement."""
    matriz = matriz_do_modulo(conj,plano)
    inversa = matriz.inverted()
    giro = matriz.to_3x3()
    cima = giro.col[2].normalized()
    base=_base_do_plano(plano).to_3x3()
    def no_modulo(p):
        return base @ desloc(base.transposed() @ p)
    fator = _gavetas.acompanhar_forma(conj, no_modulo)
    if fator < 1.:
        original = desloc
        desloc = lambda p: original(p) * fator
    vaos=_portas.preparar_deformacao_vaos(conj,no_modulo)
    paineis=_apoios_dos_paineis(conj,matriz)
    contatos=[]
    if conservar_espessura and apoios:
        para_plano=_base_do_plano(plano).to_3x3().transposed()
        for lado,(nome,(n,dist)) in enumerate(zip(apoios['nomes'],apoios['apoios'])):
            ids=[i for i in range(8) if bool(i&(1<<apoios['eixo']))==bool(lado)]
            ps=[para_plano@Vector(apoios['internos'][i]) for i in ids]
            novos=[p+desloc(p) for p in ps]
            normal=(novos[1]-novos[0]).cross(novos[2]-novos[0]).normalized()
            n=para_plano@Vector(n)
            if normal.dot(n)<0:normal.negate()
            contatos.append((nome,n,dist,normal,normal.dot(novos[0])))
        ancora=sum((Vector(p) for p in apoios['internos']),Vector())/8
        # The panel's outer face is the one facing the edited joint.
        ancora=para_plano@Vector(apoios.get('ancora',ancora))
    # Backs/crosspieces do not define the envelope but participate in deformation.
    # Preserve actual cuts/thickness instead of rebuilding them from AABB.
    pecas = list(dict.fromkeys([o for o in _pecas(conj) if not o.get('porta_curva_modelada')]
             + [o for o in conj.children if o.type == 'MESH'
                and _chapas.MARCA_CHAPA in o and _chapas.eh_dependente(o)]))
    for o in pecas + [o for o in conj.children if o not in pecas
                      and _chapas.MARCA_ACESSORIO in o]:
        mundo = o.matrix_world.copy()
        if o.type != 'MESH' or o not in pecas:
            centro = sum((inversa @ (mundo @ Vector(c)) for c in o.bound_box),
                         Vector()) / 8.0 * 1000.0
            d = desloc(centro)
            if d.length > 1e-6:
                o.matrix_world = Matrix.Translation(giro @ d / 1000.0) @ mundo
            continue
        para_modulo = inversa @ mundo
        pts = [para_modulo @ v.co * 1000.0 for v in o.data.vertices]
        deslocs = [desloc(p) for p in pts]
        if conservar_espessura and apoios and not (reencaixar_paineis and _chapas.MARCA_FUNDO in o):
            if all(d.length<1e-6 for d in deslocs):continue
            if _deformar_chapa_com_secao(o,matriz,desloc,ancora,contatos):continue
        if _chapas.MARCA_FUNDO in o and o!=conj:
            if not reencaixar_paineis and all(d.length<.001 for d in deslocs):
                continue
            # A panel follows both planar endpoints while retaining its section.
            # Applying the field separately to front/rear shears thickness;
            # box rebuilding would lose the edited mesh.
            _transportar_painel(o,pts,deslocs,matriz,cima,desloc,paineis.get(o))
            continue
        inteira = rigida(pts, deslocs) if rigida is not None else None
        if inteira is not None:
            deslocs = [inteira] * len(pts)
        if all(d.length < 1e-6 for d in deslocs):
            continue
        if all((d - deslocs[0]).length < 1e-6 for d in deslocs):
            o.matrix_world = Matrix.Translation(giro @ deslocs[0] / 1000.0) @ mundo
            continue
        if o.data.users > 1:
            o.data = o.data.copy()
        era_caixa = _chapas._malha_e_caixa(o.data)
        volta = para_modulo.inverted()
        for v, p, d in zip(o.data.vertices, pts, deslocs):
            v.co = volta @ ((p + d) / 1000.0)
        o.data.update()
        if _chapas.MARCA_CHAPA in o:
            _reajustar(o, era_caixa, cima)
    # A curved leaf is a native system, but its outline participates in the
    # same linear deformation. Calculate CLOSED even when the slider is open.
    for o in [o for o in conj.children_recursive if o.get('porta_curva_modelada')]:
        fechado=_portas._ferragens._matriz_fechada(o)
        para_modulo=inversa @ fechado
        volta=para_modulo.inverted()
        for v in o.data.vertices:
            ponto=para_modulo @ v.co*1000
            v.co=volta @ ((ponto+desloc(ponto))/1000)
        o.data.update()
    bpy.context.view_layer.update()
    _portas.aplicar_deformacao_vaos(conj,vaos)


def _apoios_dos_paineis(conj,matriz):
    """Actual horizontal-panel edges, prepared outside drawing. Backs follow
    their supports with normal setback preserved; shearing their centers
    would reduce setback on rotation.
    """
    inversa=matriz.inverted();arestas=[]
    for o in _pecas(conj):
        if abs((inversa@o.matrix_world).to_3x3().col[2].normalized().z)<.99:
            continue
        contorno=_frentes.contorno(o)
        if contorno is None:continue
        ps,es=contorno
        for i,j in es:
            a,b=(inversa@ps[i]*1000).xy,(inversa@ps[j]*1000).xy
            if (b-a).length>ESPESSURA_PONTA_MM:arestas.append((a,b))
    resultado={}
    for o in conj.children:
        if o.type!='MESH' or _chapas.MARCA_FUNDO not in o:continue
        m=inversa@o.matrix_world
        eixos=[m.to_3x3().col[i].normalized() for i in range(2)]
        longo=min(range(2),key=lambda i:abs(eixos[i].z))
        direcao=eixos[longo].xy.normalized()
        centro=sum((m@v.co*1000 for v in o.data.vertices),Vector())/len(o.data.vertices)
        candidatos=[]
        for a,b in arestas:
            d=b-a
            if abs(d.normalized().dot(direcao))<.7:continue
            t=(centro.xy-a).dot(d)/d.length_squared
            if not -.1<=t<=1.1:continue
            candidatos.append(((centro.xy-(a+d*t)).length,a,b))
        if not candidatos:continue
        _,a,b=min(candidatos,key=lambda x:x[0])
        if (b-a).dot(direcao)<0:a,b=b,a
        d=(b-a).normalized();normal=Vector((-d.y,d.x))
        if normal.dot(m.to_3x3().col[2].xy)<0:normal.negate()
        resultado[o]=(a.copy(),b.copy(),normal,centro.copy())
    return resultado


def _transportar_painel(o,pts,deslocs,matriz,cima,desloc,apoio=None):
    mundo=o.matrix_world.copy()
    rot=mundo.to_3x3().normalized()
    eixos=[rot.col[i].normalized() for i in range(2)]
    longo=min(range(2),key=lambda i:abs(eixos[i].dot(cima)))
    lados=[[i for i,v in enumerate(o.data.vertices) if (v.co[longo]>=0)==sinal]
           for sinal in (False,True)]
    if any(not lado for lado in lados):return
    centros=[sum((pts[i] for i in lado),Vector())/len(lado) for lado in lados]
    novos=[sum((pts[i]+deslocs[i] for i in lado),Vector())/len(lado) for lado in lados]
    antigo=centros[1]-centros[0];novo=novos[1]-novos[0]
    if antigo.length<1e-6 or novo.length<1e-6:return
    giro=matriz.to_3x3()
    a,b=(giro@antigo).normalized(),(giro@novo).normalized()
    proporcao=novo.length/antigo.length
    meio=matriz@((novos[0]+novos[1])/2000)
    if apoio is not None:
        p,q,normal,centro_apoio=apoio
        origem,destino=Vector((*p,centro_apoio.z)),Vector((*q,centro_apoio.z))
        nova_origem,nova_ponta=origem+desloc(origem),destino+desloc(destino)
        d=(q-p);novo_d=(nova_ponta-nova_origem).xy
        if novo_d.length>1e-6:
            t=(centro_apoio.xy-p).dot(d)/d.length_squared
            recuo=(centro_apoio.xy-p).dot(normal)
            proporcao=novo_d.length/d.length
            comprimento=(max(v.co[longo] for v in o.data.vertices)-
                         min(v.co[longo] for v in o.data.vertices))*1000
            entra=max(0.,_modulos.CANAL_FUNDO_MM-_modulos.FOLGA_CANAL_FUNDO_MM)
            # A panel sheared by older edits may have grown when aligned.
            # Fit it to support plus actual groove penetration.
            corte=min(comprimento*proporcao,novo_d.length+2*entra)
            proporcao=corte/max(comprimento,1e-9)
            margem=(corte/2-entra)/novo_d.length
            t=max(margem,min(1-margem,t))
            n=Vector((-novo_d.y,novo_d.x)).normalized()
            if n.dot(normal)<0:n.negate()
            pos=nova_origem.xy+novo_d*t+n*recuo
            meio=matriz@(Vector((*pos,centro_apoio.z))/1000)
            # Transporting the SUPPORT rotation preserves the panel's modeled
            # section; aligning it to the new axis erased residual tilt
            # even when the operation had zero displacement.
            a=(giro@Vector((*d,0))).normalized()
            b=(giro@Vector((*novo_d,0))).normalized()
    angulo=math.atan2(cima.dot(a.cross(b)),a.dot(b))
    centro=sum((v.co.copy() for v in o.data.vertices),Vector())/len(o.data.vertices)
    escala=Matrix.Identity(4);escala[longo][longo]=proporcao
    o.data.transform(Matrix.Translation(centro)@escala@Matrix.Translation(-centro))
    nova=Matrix.Rotation(angulo,3,cima)@rot
    o.matrix_world=Matrix.LocRotScale(meio-nova@centro,nova.to_quaternion(),Vector((1,1,1)))
    _chapas._ocupado[0]=True
    try:
        nome=('chapa_largura_mm','chapa_comprimento_mm')[longo]
        setattr(o,nome,float(getattr(o,nome))*proporcao)
    finally:
        _chapas._ocupado[0]=False
    o.data.update()
    _frentes.preparar(o,forcar=True)


def _rigida_na_faixa(forma, k, eixo, centro, faixa=FAIXA_MM):
    """A WHOLE part within the moving face band (crosspiece, arm-front door)
    moves rigidly, including any portion entering the other arm."""
    def rigida(pts, deslocs):
        if not any(d.length > 1e-6 for d in deslocs):
            return None
        coords = [_no_canto(forma, k, p)[eixo] for p in pts]
        if min(coords) >= centro - faixa and max(coords) <= centro + faixa:
            return max(deslocs, key=lambda d: d.length)
        return None
    return rigida


def _mover_perna(conj, forma, k, perna, variacao, angular=False):
    """Increase corner k feature leg `perna` ('a' on X, 'b' on Y) by
    `variacao` mm: move the inner face/diagonal endpoint inward;
    keep the other arm fixed."""
    f = forma['cantos'][k]
    if f is None or f['tipo'] not in ('RECORTE', 'CHANFRO'):
        return
    sx, sy = QUINAS[k]
    largura, fundo = forma['hi'].x - forma['lo'].x, forma['hi'].y - forma['lo'].y
    eixo = 0 if perna == 'a' else 1
    lado = largura if eixo == 0 else fundo
    outra = 0.0
    vizinha = forma['cantos'][_vizinha(k, eixo)]
    if vizinha is not None:
        outra = vizinha['a' if eixo == 0 else 'b']
    atual = f[perna]
    novo = min(max(atual + variacao, 0.0 if angular else TOL_FORMA_MM + 5.0),
               lado if angular else lado - outra - MENOR_LADO_MM)
    variacao = novo - atual
    if abs(variacao) < 1e-6:
        if angular:
            # Returning to the reference value also refits an old back
            # already larger than its support.
            _deformar(conj,lambda p:Vector(),reencaixar_paineis=True,plano=forma.get('plano','XY'))
        return
    passo = Vector((-sx * variacao, 0.0, 0.0)) if eixo == 0 else \
        Vector((0.0, -sy * variacao, 0.0))
    ao_longo = f[perna]                         # Moving face position.
    largura_coluna = f['b' if eixo == 0 else 'a']
    # The fixed 100 mm band reached the REAR when shortening an arm:
    # on restoration, the same vertices then belonged to another side.
    # Splitting endpoints at the midpoint of remaining space preserves
    # thickness and endpoint identity, including on short arms.
    meio = (ao_longo + lado) / 2.0
    if f['tipo'] == 'RECORTE':
        def peso(p):
            c = _no_canto(forma, k, p)
            if (ao_longo / 2 < c[eixo] < meio
                    and c[1 - eixo] <= largura_coluna + TOL_FORMA_MM):
                return 1.0
            return 0.0
    else:
        def peso(p):
            c = _no_canto(forma, k, p)
            longe, junto = c[eixo], c[1 - eixo]
            if junto > largura_coluna or longe >= meio:
                return 0.0
            px = 1.0 if junto <= MARGEM_CHANFRO_MM else (
                (largura_coluna - junto) / max(largura_coluna - MARGEM_CHANFRO_MM, 1.0))
            return max(0.0, px)
    apoios=None
    if angular:
        apoios=blocagem_do_modulo(conj) or dict(nomes=[],apoios=[],internos=[])
        a,b=pontas_diagonal(forma,k)
        centro=Vector((*((a+b)/2),(forma['lo'].z+forma['hi'].z)/2))
        apoios=dict(apoios,ancora=tuple(_base_do_plano(forma.get('plano','XY')).to_3x3()@centro))
    _deformar(conj, lambda p: passo * peso(p),
              None if angular else _rigida_na_faixa(forma, k, eixo, ao_longo,
                               min(FAIXA_MM, (lado-ao_longo)/2-1)),
              reencaixar_paineis=angular,plano=forma.get('plano','XY'),
              conservar_espessura=angular,apoios=apoios)


def _vizinha(k, eixo):
    """Other corner on the same box side: horizontal for leg a, vertical
    for leg b."""
    sx, sy = QUINAS[k]
    alvo = (-sx, sy) if eixo == 0 else (sx, -sy)
    return QUINAS.index(alvo)


def _concluir_transformacao(context,conj,sistemas=True):
    # Both angle/dimension families transport the same closed reference.
    # Reanchor after the rig to avoid deforming the door twice.
    context.view_layer.update()
    curvas=[(o.parent,[_portas._ferragens._matriz_fechada(o)@v.co for v in o.data.vertices])
            for o in conj.children_recursive if o.get('porta_curva_modelada')]
    _modulos.reposicionar_origem(conj)
    _modulos.sincronizar_medidas_conjunto(conj)
    _modulos.atualizar_sistemas_do_conjunto(conj, internos=sistemas)
    for grupo,pontos in curvas:_portas.adotar_contorno_modelado(context,grupo,pontos)
    context.view_layer.update();_cache.pop(conj.name,None);concluir_edicao(conj)


def _corte(forma, eixo):
    """(total-stretch plane position, available shortening clearance).
    For notches/diagonals, place the plane in ITS column containing only
    one arm, so the other arm's depth stays unchanged."""
    lo, hi = forma['lo'][eixo], forma['hi'][eixo]
    colunas, ocupado = [], []
    for k, f in enumerate(forma['cantos']):
        if f is None:
            continue
        sx, sy = QUINAS[k]
        sinal = sx if eixo == 0 else sy
        perna = f['a'] if eixo == 0 else f['b']
        borda = hi if sinal > 0 else lo
        faixa = sorted((borda, borda - sinal * perna))
        ocupado.append(faixa)
        if f['tipo'] in ('RECORTE', 'CHANFRO'):
            colunas.append(faixa)
    if colunas:
        a, b = max(colunas, key=lambda c: c[1] - c[0])
        return (a + b) / 2.0, (b - a) / 2.0
    livres, inicio = [], lo
    for a, b in sorted(ocupado):
        if a > inicio:
            livres.append((inicio, a))
        inicio = max(inicio, b)
    if hi > inicio:
        livres.append((inicio, hi))
    if not livres:
        return (lo + hi) / 2.0, (hi - lo) / 4.0
    a, b = max(livres, key=lambda c: c[1] - c[0])
    return (a + b) / 2.0, (b - a) / 2.0


def _esticar_total(conj, forma, eixo, variacao, lado):
    """Total L (axis 0) or P (axis 1): cut the cabinet with a plane and move
    the side opposite fixed `lado` ('min'/'max') by `variacao`."""
    corte, folga = _corte(forma, eixo)
    variacao = max(variacao, -(folga - 10.0))
    if abs(variacao) < 1e-6:
        return
    anda_max = lado != 'max'
    passo = Vector((0.0, 0.0, 0.0))
    passo[eixo] = variacao if anda_max else -variacao

    def do_lado(c):
        return c > corte if anda_max else c < corte

    def rigida(pts, deslocs):
        coords = [p[eixo] for p in pts]
        if min(coords) < corte < max(coords) and max(coords) - min(coords) < RIGIDA_MM:
            return passo if do_lado((min(coords) + max(coords)) / 2.0) else Vector()
        return None
    _deformar(conj, lambda p: passo if do_lado(p[eixo]) else Vector(), rigida,plano=forma.get('plano','XY'))


def aplicar(context, conj, chave, novo, lado=None, _correcao=0., _tentativa=0, _eixo_corpo=None, plano='XY'):
    """Set shape dimension `chave` to `novo` mm through HUD drag/typing."""
    # A reduced boundary may hide a feature from detection. Restore before
    # looking up the dimension to allow return to the original shape.
    _preparar_edicao(conj, chave, lado, plano)
    forma = forma_do_modulo(conj,plano)
    if forma is None:return
    antes=(valor(conj,chave,plano) if _eixo_corpo is None
           else _modulos.medir_conjunto(conj)[_eixo_corpo])
    variacao = novo + _correcao - antes
    tipo = chave[0]
    if tipo in ('L', 'P'):
        _esticar_total(conj, forma, 0 if tipo == 'L' else 1, variacao, lado or 'min')
    elif tipo in ('P1', 'P2'):
        # Longer side = shorter leg.
        _mover_perna(conj, forma, chave[1], 'b' if tipo == 'P1' else 'a', -variacao)
    elif tipo == 'ANG':
        # User requirement: keep corner front P2/leg a fixed and move
        # the opposite P1 endpoint to achieve the angle.
        k = chave[1]
        f = forma['cantos'][k]
        # A right angle may eliminate the chamfer; P1/P2 minima must not
        # silently return 97 degrees when the user types 90.
        graus = max(0.0, min(90.0, float(novo) + _correcao))
        angulo = math.radians(graus)
        pa, pb = pontas_diagonal(forma, k)
        xc, yc = _quina(forma, k)
        recuo_x, recuo_y = abs(pb.x-xc), abs(pa.y-yc)
        if (graus >= 90.0 or (graus > 0.0 and
                f['b'] >= forma['hi'].y - forma['lo'].y - TOL_FORMA_MM
                and f['a'] < forma['hi'].x - forma['lo'].x - TOL_FORMA_MM)):
            # Diagonal spans the WHOLE side: hold it fixed and move the front.
            _mover_perna(conj, forma, k, 'a', recuo_x + (f['b']-recuo_y) / math.tan(angulo) - f['a'], angular=True)
        else:
            _mover_perna(conj, forma, k, 'b', recuo_y + (f['a']-recuo_x) * math.tan(angulo) - f['b'], angular=True)
    elif tipo == 'R':
        k = chave[1]
        f = forma['cantos'][k]
        if (plano!='XY' or conj.type=='MESH') and f['tipo']=='CHANFRO':
            pa,pb=pontas_diagonal(forma,k);xc,yc=_quina(forma,k)
            rx,ry=abs(pb.x-xc),abs(pa.y-yc)
            dx,dy=abs(pb.x-pa.x),abs(pb.y-pa.y)
            if f['b']>=forma['hi'].y-forma['lo'].y-TOL_FORMA_MM:
                if novo<dy:raise ValueError("The diagonal cannot be shorter than its height")
                _mover_perna(conj,forma,k,'a',rx+math.sqrt(max(0.,novo*novo-dy*dy))-f['a'],angular=True)
            elif f['a']>=forma['hi'].x-forma['lo'].x-TOL_FORMA_MM:
                if novo<dx:raise ValueError("The diagonal cannot be shorter than its width")
                _mover_perna(conj,forma,k,'b',ry+math.sqrt(max(0.,novo*novo-dx*dx))-f['b'],angular=True)
            else:
                fator=novo/max((pb-pa).length,1e-9)
                _mover_perna(conj,forma,k,'a',rx+dx*fator-f['a'],angular=True)
                _cache.pop(conj.name,None)
                atual=forma_do_modulo(conj,plano)
                # The first leg may eliminate the diagonal (R ~ 0), hiding the shape.
                if atual is not None and atual['cantos'][k] is not None:
                    _mover_perna(conj,atual,k,'b',ry+dy*fator-atual['cantos'][k]['b'],angular=True)
        else:
            # Diagonal: both legs receive the same dimension.
            _mover_perna(conj, forma, k, 'b', novo - f['b'])
            _cache.pop(conj.name, None)
            forma = forma_do_modulo(conj,plano)
            if forma is not None and forma['cantos'][k] is not None:
                _mover_perna(conj, forma, k, 'a', novo - forma['cantos'][k]['a'])
    _cache.pop(conj.name, None)
    if conj.type=='MESH':
        _chapas.absorver_malha_editada(conj)
        _frentes.preparar(conj,forcar=True)
        # An individual notch may change without changing L/A/E:
        # invalidate the parent's previous section too.
        esquecer()
        context.view_layer.update()
        concluir_edicao(conj)
        return
    _concluir_transformacao(context,conj,sistemas=abs(variacao)>.01)
    if tipo in ('P1','P2','ANG') and _tentativa<3 and _eixo_corpo is None:
        # Rotating an oblique panel also shifts projected thickness.
        # Correct that small error using the SAME reference, without accumulating
        # deformations. Do not iterate physical limits such as tracks/wood.
        try:erro=novo-valor(conj,chave,plano)
        except ValueError:return
        if .01<abs(erro)<5:
            aplicar(context,conj,chave,novo,lado,_correcao+erro,_tentativa+1,plano=plano)
