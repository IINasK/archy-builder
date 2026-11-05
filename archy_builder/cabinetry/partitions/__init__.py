"""Vertical partitions and supports for the internal systems they cross.

The system owns its opening; the actual panel owns the internal limit.
Splitting neither replaces surviving Mesh IDs nor reconstructs shelves.
"""
import bpy
import bmesh
from mathutils import Matrix, Vector
from bpy.types import Operator
from ... import gavetas as _gavetas

_chapas = _modulos = _portas = _prateleiras = _eventos = _hud = _formas = None
MARCA_GRUPO = 'eh_grupo_divisorias'
MARCA_DIVISORIA = 'eh_divisoria'
CHAVE_PARAMETROS = 'divisorias_parametros'
CHAVE_APOIOS = 'divisorias_apoios'
CHAVE_BLOCAGEM = 'cabinet_blocagem_uid'
# Shared opening reference; the group marker determines its editor.
CHAVE_MARGENS = _gavetas.CHAVE_MARGENS
CHAVE_REFERENCIA = _gavetas.CHAVE_REFERENCIA
CHAVE_VAO = _gavetas.CHAVE_VAO
PARAMETROS_PADRAO = dict(quantidade=1, espessura_mm=18.0,
                        profundidade_mm=500.0, recuo_mm=0.0, vaos_mm=[])
MAXIMO_DIVISORIAS = 20
TOL = .01
_assistente_divisorias = [None]


def grupo_de(obj):
    while obj is not None:
        if MARCA_GRUPO in obj:
            return obj
        obj = obj.parent
    return None


def pecas(grupo):
    return sorted((o for o in grupo.children if MARCA_DIVISORIA in o),
                  key=lambda o: int(o.get('divisoria_indice', 0)))


def parametros(grupo):
    return dict(PARAMETROS_PADRAO, **_portas._copiar_parametros(
        grupo.get(CHAVE_PARAMETROS, {})))


def garantir_blocagem(grupo):
    uid = grupo.get(CHAVE_BLOCAGEM)
    if uid:
        return uid
    membros = [grupo]
    if _prateleiras.MARCA_GRUPO in grupo and grupo.parent is not None:
        # Legacy: only coplanar segments linked to the same actual support.
        pendentes = [g for g in grupo.parent.children
                     if _prateleiras.MARCA_GRUPO in g and not g.get(CHAVE_BLOCAGEM) and g != grupo]
        inv = grupo.matrix_world.inverted_safe()
        _l, altura, prof = _prateleiras.medidas(grupo)
        ligacoes = lambda g: {a['uid'] for a in g.get(CHAVE_APOIOS, {}).values() if a.get('uid')}
        apoios = ligacoes(grupo)
        while apoios:
            novas = []
            for outro in pendentes:
                r = inv @ outro.matrix_world
                _l, a, p = _prateleiras.medidas(outro)
                if (apoios & ligacoes(outro) and abs(a-altura) < TOL and abs(p-prof) < TOL
                        and abs(r.translation.y) < 1e-5 and abs(r.translation.z) < 1e-5
                        and all(abs(r[i][j] - float(i == j)) < 1e-5 for i in range(3) for j in range(3))):
                    novas.append(outro)
            if not novas:
                break
            for outro in novas:
                membros.append(outro); pendentes.remove(outro); apoios |= ligacoes(outro)
    uid = _chapas._garantir_uid(grupo)
    for membro in membros:
        membro[CHAVE_BLOCAGEM] = uid
    return uid


def grupos_da_blocagem(grupo):
    uid = grupo.get(CHAVE_BLOCAGEM)
    marca = _prateleiras.MARCA_GRUPO if _prateleiras.MARCA_GRUPO in grupo else MARCA_GRUPO
    if not uid or grupo.parent is None:
        return [grupo]
    return [grupo] + [g for g in grupo.parent.children
        if g != grupo and marca in g and g.get(CHAVE_BLOCAGEM) == uid]


def linhas_da_blocagem(grupo, chapas, linhas_do_grupo):
    cantos, linhas = linhas_do_grupo(grupo, chapas)
    grupos = [g for g in grupos_da_blocagem(grupo) if g.visible_get()]
    if len(grupos) <= 1:
        return cantos, linhas
    geometrias = [(cantos, linhas)] + [linhas_do_grupo(g, []) for g in grupos if g != grupo]
    inv = grupo.matrix_world.inverted_safe()
    pontos = [inv @ p for c, _l in geometrias for p in c]
    lo = Vector(tuple(min(p[i] for p in pontos) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in pontos) for i in range(3)))
    cantos = [grupo.matrix_world @ Vector((x,y,z)) for z in (lo.z,hi.z)
              for y in (lo.y,hi.y) for x in (lo.x,hi.x)]
    moldura = [dict(l, tipo='contorno_forma', editavel=False,
                    pontos=[cantos[i] for i in l['cantos']])
               for l in linhas if l.get('cantos')]
    return cantos, moldura + [l for _c, ls in geometrias for l in ls if l.get('vao')]


def calcular(largura, altura, p):
    n, e = int(p['quantidade']), float(p['espessura_mm'])
    if not 1 <= n <= MAXIMO_DIVISORIAS or e <= 0 or altura < 50:
        raise ValueError("Invalid partition count, thickness, or height")
    livre = largura - n * e
    g = list(p.get('vaos_mm') or ())
    if len(g) != n + 1:
        g = [livre / (n + 1)] * (n + 1)
    if min(g) < 50 - TOL or abs(sum(g) - livre) > TOL:
        raise ValueError("Partitions leave openings smaller than 50 mm")
    recuo, prof = float(p['recuo_mm']), float(p['profundidade_mm'])
    if prof - recuo < 50:
        raise ValueError("The partition needs at least 50 mm of depth")
    caixas, x = [], 0.0
    for i in range(n):
        x += g[i]
        caixas.append((x, x + e, recuo, prof, 0.0, altura))
        x += e
    return dict(divisorias=caixas, vaos=g)


def vao(grupo):
    return _gavetas.vao(grupo)


def medidas(grupo):
    l, a, _m = vao(grupo)
    return l, a, float(parametros(grupo)['profundidade_mm'])


def linhas_hud(grupo, chapas):
    return linhas_da_blocagem(grupo, chapas, _linhas_hud_grupo)


def _linhas_hud_grupo(grupo, chapas):
    """System opening and clear distances to partition faces."""
    largura, altura, prof = medidas(grupo)
    m = grupo.matrix_world
    cantos = [m @ (Vector((i * largura, j * prof, k * altura)) / 1000)
              for k in (0, 1) for j in (0, 1) for i in (0, 1)]
    letras = ('L', 'P', 'A')
    comum = dict(tipo='divisorias', objeto=grupo, modo='DIVISORIAS', chapas=chapas)
    linhas = [dict(comum, eixo=eixo, letra=letras[eixo], face=(letras[eixo],),
                   cantos=(i, j), pontos=[cantos[i], cantos[j]])
              for eixo, arestas in enumerate(_hud.ARESTAS_EIXO) for i, j in arestas]
    p = parametros(grupo)
    try:
        dados = calcular(largura, altura, p)
    except ValueError:      # Draw callback: opening dimensions only.
        return cantos, linhas
    caixas = dados['divisorias']
    for k in range(len(dados['vaos'])):
        x0 = caixas[k - 1][1] if k else 0.0
        x1 = caixas[k][0] if k < len(caixas) else largura
        linhas.append(dict(comum, letra=None, face=('V', k), vao=True,
            pontos=[m @ (Vector((x, p['recuo_mm'], altura / 2)) / 1000) for x in (x0, x1)]))
    return cantos, linhas


def valor(grupo, chave):
    if chave[0] == 'V':
        l, a, _m = vao(grupo)
        return calcular(l, a, parametros(grupo))['vaos'][chave[1]]
    return dict(zip(('L', 'A', 'P'), medidas(grupo)))[chave[0]]


def _limites_malha(obj, mundo):
    matriz = mundo.inverted_safe() @ obj.matrix_world
    pontos = [matriz @ Vector(c) * 1000 for c in obj.bound_box]
    return (Vector(tuple(min(p[k] for p in pontos) for k in range(3))),
            Vector(tuple(max(p[k] for p in pontos) for k in range(3))))


def limitar_vao(grupo, largura, altura, matriz):
    """Supports by UID in opening coordinates; absence keeps the last limit."""
    apoios = grupo.get(CHAVE_APOIOS)
    if not apoios:
        return largura, altura, matriz
    modulo = _gavetas.modulo_do_grupo(grupo)
    if modulo is None:
        return largura, altura, matriz
    mundo = modulo.matrix_world @ matriz
    por_uid = {o.get('chapa_uid'): o for o in modulo.children_recursive
               if MARCA_DIVISORIA in o}
    extremos = [0.0, largura]
    for k, lado in enumerate(('min', 'max')):
        apoio = apoios.get(lado)
        if not apoio:
            continue
        chapa = por_uid.get(apoio['uid'])
        if chapa is not None:
            lo, hi = _limites_malha(chapa, mundo)
            extremos[k] = (hi.x if apoio.get('face') == 'max' else lo.x
                           if apoio.get('face') == 'min' else hi.x if k == 0 else lo.x)
        else:
            # Deleting a partition must not merge systems the user may have
            # edited independently after splitting.
            origem = matriz.translation
            eixo = matriz.to_3x3().col[0]
            extremos[k] = (Vector(apoio['ponto']) - origem).dot(eixo) * 1000
    nova = matriz @ Matrix.Translation((extremos[0] / 1000, 0, 0))
    return extremos[1] - extremos[0], altura, nova


def _parametros_largura(dono, grupo, largura, antiga, indice, total, e):
    p = dono.parametros(grupo)
    if dono is _gavetas:
        for q in p.get('individuais', {}).values():
            for chave in ('largura_mm', 'x_mm'):
                if chave in q:
                    q[chave] *= largura / antiga
        cob = list(_gavetas.coberturas(p))
        cobertura = max(0, (e - float(p['entre_gavetas_mm'])) / 2)
        if indice:
            cob[0] = cobertura
        if indice + 1 < total:
            cob[1] = cobertura
        p['coberturas_mm'] = cob
    else:
        for q in p.get('individuais') or ():
            q.pop('largura_mm', None)
            q.pop('x_mm', None)
    return p


def _duplicar(grupo):
    """Native copies: remap parents, modifiers and the rig's own targets."""
    mapa = {}
    for obj in [grupo, *grupo.children_recursive]:
        novo = obj.copy()
        if obj.data is not None:
            novo.data = obj.data.copy()
        _gavetas._colecao(grupo).objects.link(novo)
        for chave in list(novo.keys()):
            if chave.startswith('adj_') or chave in ('chapa_uid', 'chapa_edicao', 'forma_edicao'):
                del novo[chave]
        if _chapas.MARCA_CHAPA in novo:
            _chapas._garantir_uid(novo)
        mapa[obj] = novo
    for obj, novo in mapa.items():
        novo.parent = mapa.get(obj.parent, obj.parent)
        # Native parent assignment resets the inverse; imported presets
        # retain nonidentity assembly compensation.
        novo.matrix_parent_inverse = obj.matrix_parent_inverse.copy()
        novo.matrix_basis = obj.matrix_basis.copy()
        for bloco in [*novo.modifiers, *novo.constraints]:
            for prop in bloco.bl_rna.properties:
                if prop.type == 'POINTER' and not prop.is_readonly:
                    alvo = getattr(bloco, prop.identifier)
                    if isinstance(alvo, bpy.types.Object) and alvo in mapa:
                        setattr(bloco, prop.identifier, mapa[alvo])
        if novo.animation_data:
            for driver in novo.animation_data.drivers:
                for variavel in driver.driver.variables:
                    for alvo in variavel.targets:
                        if isinstance(alvo.id, bpy.types.Object) and alvo.id in mapa:
                            alvo.id = mapa[alvo.id]
    return mapa[grupo]


def _cortar_chapa(obj, mundo, inicio, fim):
    """Native bisect/cap preserves thickness, cutouts, materials and UVs."""
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        inversa = obj.matrix_world.inverted_safe()
        for x, sinal in ((inicio, -1), (fim, 1)):
            normal = mundo.to_3x3().col[0].normalized() * sinal
            normal = (obj.matrix_world.to_3x3().transposed() @ normal).normalized()
            ponto = inversa @ (mundo @ Vector((x / 1000, 0, 0)))
            corte = bmesh.ops.bisect_plane(bm, geom=[*bm.verts, *bm.edges, *bm.faces],
                plane_co=ponto, plane_no=normal, dist=1e-7, clear_outer=True)
            bordas = [v for v in corte['geom_cut']
                      if isinstance(v, bmesh.types.BMEdge) and v.is_boundary]
            if bordas:
                bmesh.ops.holes_fill(bm, edges=bordas, sides=0)
            eixo = max(range(3), key=lambda k: abs(normal[k]))
            if abs(normal[eixo]) > 1 - 1e-6:
                # Bisect retains vertices nearly on the plane; align the cap to remove
                # single-precision wedges before native Boolean.
                tampa = [v for v in bm.verts if abs(v.co[eixo] - ponto[eixo]) < 1e-6]
                projecao = Matrix.Identity(4)
                projecao[eixo][eixo] = 0; projecao[eixo][3] = ponto[eixo]
                bmesh.ops.transform(bm, matrix=projecao, verts=tampa)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(obj.data)
        obj.data.update()
    finally:
        bm.free()


def _plano(conj, matriz, caixas, alvo=None):
    """Plan ALL systems before writing any part."""
    planos = []
    mundo = conj.matrix_world @ matriz
    for dono in (_gavetas, _prateleiras):
        for grupo in dono.grupos_do_modulo(conj):
            if alvo is not None and grupo != alvo:
                continue
            l, a, m = dono.vao(grupo)
            p = dono.parametros(grupo)
            transformacao = (conj.matrix_world @ m).inverted_safe() @ mundo
            prateleiras = (_prateleiras.prateleiras_do_grupo(grupo)
                          if dono is _prateleiras else [])
            locais = [_limites_malha(obj, conj.matrix_world @ m) for obj in prateleiras]
            por_peca = {k: [] for k in range(len(prateleiras))} if prateleiras else {None: []}
            parciais = set()
            for i, caixa in enumerate(caixas):
                pts = [transformacao @ Vector((x / 1000, y / 1000, z / 1000)) * 1000
                       for x in caixa[:2] for y in caixa[2:4] for z in caixa[4:6]]
                lo = [min(v[k] for v in pts) for k in range(3)]
                hi = [max(v[k] for v in pts) for k in range(3)]
                if (lo[0] <= TOL or hi[0] >= l - TOL or hi[1] <= TOL
                        or lo[1] >= float(p['profundidade_mm']) - TOL
                        or hi[2] <= TOL or lo[2] >= a - TOL):
                    continue
                obliqua = abs(abs(transformacao.to_3x3().col[0].normalized().x) - 1) > 1e-5
                if obliqua and dono is _gavetas:
                    raise ValueError("The partition must follow the orientation of the systems it crosses")
                if dono is _prateleiras:
                    indices = {k for k, (baixo, cima) in enumerate(locais)
                               if baixo.x < lo[0] - TOL and cima.x > hi[0] + TOL
                               and cima.z > lo[2] + TOL and baixo.z < hi[2] - TOL
                               and cima.y > lo[1] + TOL and baixo.y < hi[1] - TOL}
                    if not indices:
                        continue
                    if obliqua or any(lo[1] > locais[k][0].y + TOL or hi[1] < locais[k][1].y - TOL
                            or lo[2] > locais[k][0].z + TOL or hi[2] < locais[k][1].z - TOL for k in indices):
                        parciais.add(i)
                else:
                    if lo[2] > TOL or hi[2] < a - TOL:
                        raise ValueError("Mark the full opening height of %s" % grupo.name)
                    if lo[1] > TOL or hi[1] < float(p['profundidade_mm']) - TOL:
                        raise ValueError("The partition must cover the depth of %s" % grupo.name)
                    indices = {None}
                for k in indices:
                    por_peca[k].append((lo[0], hi[0], i))
            conjuntos = {}
            for k, cortes in por_peca.items():
                if cortes:
                    conjuntos.setdefault(tuple(sorted(cortes)), set()).add(k)
            for cortes, atingidos in conjuntos.items():
                segmentos, inicio, anterior = [], 0.0, None
                for esquerda, direita, indice in cortes:
                    segmentos.append((inicio, esquerda, anterior, indice))
                    inicio, anterior = direita, indice
                segmentos.append((inicio, l, anterior, None))
                for k, (x0, x1, _min, _max) in enumerate(segmentos):
                    novo = _parametros_largura(dono, grupo, x1 - x0, l, k, len(segmentos),
                                              caixas[0][1] - caixas[0][0])
                    dono.calcular(x1 - x0, a, novo)
                # Panel identity avoids shifting indices when splitting another subset.
                nomes = {prateleiras[k].name for k in atingidos} if prateleiras else set()
                planos.append((dono, grupo, l, a, m, segmentos, nomes, parciais))
    return planos


def _apoios(grupo, m, x0, x1, minimo, maximo, chapas, faces=None):
    valores = _portas._copiar_parametros(grupo.get(CHAVE_APOIOS, {}))
    for lado, indice, x in (('min', minimo, x0), ('max', maximo, x1)):
        if indice is not None:
            ponto = m @ Vector((x / 1000, 0, 0))
            valores[lado] = dict(uid=chapas[indice]['chapa_uid'], ponto=list(ponto))
            if faces and lado in faces:
                valores[lado]['face'] = faces[lado]
    grupo[CHAVE_APOIOS] = valores


def _separar_prateleiras(fonte, indices):
    """A partial selection creates another opening without moving other units."""
    antigas = _prateleiras.prateleiras_do_grupo(fonte)
    if len(indices) == len(antigas):
        return fonte
    p = _prateleiras.parametros(fonte)
    nova = fonte.copy()
    _gavetas._colecao(fonte).objects.link(nova)
    for k in indices:
        antigas[k].parent = nova
    bpy.context.view_layer.update()
    for grupo in (fonte, nova):
        atuais = _prateleiras.prateleiras_do_grupo(grupo)
        novo = _portas._copiar_parametros(p)
        topo, g, individuais = 0.0, [], []
        for indice, obj in enumerate(atuais):
            lo, hi = _limites_malha(obj, grupo.matrix_world)
            g.append(lo.z - topo)
            topo = hi.z
            anterior = int(obj[_prateleiras.CHAVE_INDICE])
            individuais.append(_portas._copiar_parametros(
                (p.get('individuais') or [])[anterior])
                if anterior < len(p.get('individuais') or []) else {})
            obj[_prateleiras.CHAVE_INDICE] = indice
        novo.update(quantidade=len(atuais), vaos_mm=g, espacamento='LIVRE', individuais=individuais)
        grupo[_prateleiras.CHAVE_PARAMETROS] = novo
    return nova


def _partir(conj, planos, chapas, preenchimento='MANTER'):
    for dono, fonte, largura, altura, m, segmentos, nomes, parciais in planos:
        if dono is _prateleiras:
            garantir_blocagem(fonte)
        if dono is _prateleiras:
            indices = {i for i, o in enumerate(_prateleiras.prateleiras_do_grupo(fonte)) if o.name in nomes}
            fonte = _separar_prateleiras(fonte, indices)
        grupos = [fonte] + [_duplicar(fonte) for _ in segmentos[1:]]
        bpy.context.view_layer.update()
        mundo = conj.matrix_world @ m
        for k, (grupo, (x0, x1, minimo, maximo)) in enumerate(zip(grupos, segmentos)):
            faces, recortes = {}, []
            if dono is _prateleiras:
                for lado, indice in (('min', minimo), ('max', maximo)):
                    if indice in parciais and ((lado == 'max' and preenchimento == 'ESQUERDA')
                            or (lado == 'min' and preenchimento == 'DIREITA')):
                        baixo, cima = _limites_malha(chapas[indice], mundo)
                        if lado == 'max':
                            x1 = cima.x; faces[lado] = 'max'
                        else:
                            x0 = baixo.x; faces[lado] = 'min'
                        recortes.append(chapas[indice])
            poses = {o.name: o.matrix_world.copy() for o in _prateleiras.prateleiras_do_grupo(grupo)} if dono is _prateleiras else {}
            p = _parametros_largura(dono, grupo, x1 - x0, largura, k, len(segmentos),
                                    chapas[0].chapa_espessura_mm)
            _apoios(grupo, m, x0, x1, minimo, maximo, chapas, faces)
            nova = m @ Matrix.Translation((x0 / 1000, 0, 0))
            grupo.matrix_parent_inverse = Matrix.Identity(4)
            grupo.matrix_basis = nova
            valores = grupo.get(dono.CHAVE_REFERENCIA)
            ref = Matrix([valores[i:i + 3] for i in (0, 3, 6)]) if valores else Matrix.Identity(3)
            lo, hi = _gavetas.limites_na_referencia(conj, ref)
            origem = ref.transposed() @ (nova.translation * 1000)
            margens = list(grupo[dono.CHAVE_MARGENS])
            margens[0], margens[1] = origem.x - lo.x, hi.x - origem.x - (x1 - x0)
            grupo[dono.CHAVE_MARGENS] = margens
            grupo[dono.CHAVE_PARAMETROS] = p
            if dono.CHAVE_ENCAIXE in grupo:
                del grupo[dono.CHAVE_ENCAIXE]
            if dono is _gavetas:
                _gavetas._reencaixar_existentes(grupo, x1 - x0, altura, p)
                for gaveta in _gavetas.gavetas_do_grupo(grupo):
                    for obj in gaveta.children_recursive:
                        if _chapas.MARCA_PUXADOR in obj:
                            _gavetas._puxadores.posicionar_puxador(obj)
            else:
                # The group moves its origin: first preserve panels in the PREVIOUS
                # frame, then bisect.
                bpy.context.view_layer.update()
                for obj in _prateleiras.prateleiras_do_grupo(grupo):
                    obj.matrix_world = poses[obj.name]
                bpy.context.view_layer.update()
                individuais = []
                for obj in _prateleiras.prateleiras_do_grupo(grupo):
                    _cortar_chapa(obj, mundo, x0, x1)
                    _chapas.absorver_malha_editada(obj, reorientar=False)
                    for apoio in recortes:
                        # Native Boolean follows movement/resize without reconstructing wood.
                        corte = obj.modifiers.new("Partition Joint", 'BOOLEAN')
                        corte.operation = 'DIFFERENCE'; corte.solver = 'EXACT'; corte.object = apoio
                    lo_obj, hi_obj = _limites_malha(obj, conj.matrix_world @ nova)
                    q = dict(_prateleiras.parametros_individuais(p, int(obj[_prateleiras.CHAVE_INDICE])))
                    individuais.append({chave: q[chave] for chave in _prateleiras.CAMPOS_INDIVIDUAIS if chave in q})
                    individuais[-1].update(largura_mm=hi_obj.x - lo_obj.x, x_mm=lo_obj.x)
                p['individuais'] = individuais
                grupo[dono.CHAVE_PARAMETROS] = p
                grupo[dono.CHAVE_VAO] = (x1 - x0, altura)
        bpy.context.view_layer.update()


def montar(grupo):
    l, a, m = vao(grupo)
    p = parametros(grupo)
    anterior = grupo.get(CHAVE_VAO)
    if anterior and abs(l - anterior[0]) > TOL and p.get('vaos_mm'):
        livre = l - float(p['espessura_mm']) * int(p['quantidade'])
        total = sum(p['vaos_mm'])
        if total > TOL:
            p['vaos_mm'] = [v * livre / total for v in p['vaos_mm']]
            grupo[CHAVE_PARAMETROS] = p
    dados = calcular(l, a, p)
    grupo.matrix_parent_inverse = Matrix.Identity(4)
    grupo.matrix_basis = m
    atuais = pecas(grupo)
    for i, caixa in enumerate(dados['divisorias']):
        obj = atuais[i] if i < len(atuais) else bpy.data.objects.new(
            "Partition %d" % (i + 1), bpy.data.meshes.new("Partition"))
        if i >= len(atuais):
            _gavetas._colecao(grupo).objects.link(obj)
            obj.parent = grupo
            obj[_chapas.MARCA_CHAPA] = 1
            obj[MARCA_DIVISORIA] = 1
            _chapas._garantir_uid(obj)
            mat = _prateleiras._material_do_modulo(grupo.parent)
            if mat is not None:
                _gavetas._pintar([obj], mat)
        obj['divisoria_indice'] = i
        pose, dims = _gavetas._matriz_da_caixa(caixa, 0)
        obj.matrix_basis = pose
        ocupado = _chapas._ocupado[0]
        _chapas._ocupado[0] = True
        try:
            obj.chapa_largura_mm, obj.chapa_comprimento_mm, obj.chapa_espessura_mm = dims
        finally:
            _chapas._ocupado[0] = ocupado
        _chapas.gerar_malha_chapa(obj)
    grupo[CHAVE_VAO] = (l, a)
    bpy.context.view_layer.update()


def planejar(conj, margens, p, referencial=None):
    p = dict(PARAMETROS_PADRAO, **p)
    ref = referencial if referencial is not None else Matrix.Identity(3)
    lo, hi = _gavetas.limites_na_referencia(conj, ref)
    esq, direita, baixo, cima, frente = margens
    l, a = hi.x - lo.x - esq - direita, hi.z - lo.z - baixo - cima
    matriz = ref.to_4x4() @ Matrix.Translation(
        Vector((lo.x + esq, lo.y + frente, lo.z + baixo)) / 1000)
    dados = calcular(l, a, p)
    planos = _plano(conj, matriz, dados['divisorias'])
    return p, planos


def criar_divisorias(context, conj, margens, p, referencial=None, blocagem_uid=None):
    p, planos = planejar(conj, margens, p, referencial)
    ref = referencial if referencial is not None else Matrix.Identity(3)
    grupo = bpy.data.objects.new("Partitions %s" % conj.name, None)
    (_modulos._colecao_do_modulo(conj) or conj.users_collection[0]).objects.link(grupo)
    grupo[MARCA_GRUPO] = 1
    grupo[CHAVE_PARAMETROS] = p
    grupo[CHAVE_MARGENS] = list(margens)
    grupo[CHAVE_REFERENCIA] = [v for linha in ref for v in linha]
    grupo.parent = conj
    grupo[CHAVE_BLOCAGEM] = blocagem_uid or _chapas._garantir_uid(grupo)
    _chapas._ocultar_empty(grupo)
    ocupado = _chapas._ocupado[0]
    _chapas._ocupado[0] = True
    try:
        montar(grupo)
        _partir(conj, planos, pecas(grupo), p.get('preenchimento', 'MANTER'))
        _formas.esquecer()
    finally:
        _chapas._ocupado[0] = ocupado
    return grupo


def prever_lacunas_prateleiras(conj, margens, p, referencial=None):
    ref = referencial if referencial is not None else Matrix.Identity(3)
    lo, hi = _gavetas.limites_na_referencia(conj, ref)
    esq, direita, baixo, cima, frente = margens
    l, a = hi.x-lo.x-esq-direita, hi.z-lo.z-baixo-cima
    m = ref.to_4x4() @ Matrix.Translation(Vector((lo.x+esq,lo.y+frente,lo.z+baixo))/1000)
    caixas = _prateleiras.calcular(l,a,dict(_prateleiras.PARAMETROS_PADRAO,**p))['prateleiras']
    for div in (g for g in conj.children if MARCA_GRUPO in g):
        for chapa in pecas(div):
            minimo, maximo = _limites_malha(chapa, conj.matrix_world @ m)
            for x0,x1,y0,y1,z0,z1 in caixas:
                if (x0 < minimo.x-TOL and x1 > maximo.x+TOL and y1 > minimo.y+TOL
                        and y0 < maximo.y-TOL and z1 > minimo.z+TOL and z0 < maximo.z-TOL):
                    if minimo.y > y0+TOL or maximo.y < y1-TOL or minimo.z > z0+TOL or maximo.z < z1-TOL:
                        return True
    return False


def particionar_grupo(grupo):
    """Systems created later also respect existing partitions."""
    conj = _gavetas.modulo_do_grupo(grupo)
    if conj is None:
        return
    alvos = [grupo]
    for div in [o for o in conj.children if MARCA_GRUPO in o]:
        chapas = pecas(div)
        if not chapas:
            continue
        caixas = []
        for chapa in chapas:
            lo, hi = _limites_malha(chapa, div.matrix_world)
            caixas.append((lo.x, hi.x, lo.y, hi.y, lo.z, hi.z))
        # Preflight is independent of mutation: a narrow opening must not leave
        # one completed half when the other half failed.
        try:
            for alvo in list(alvos):
                anteriores = {o.name for o in conj.children}
                planos = _plano(conj, div.matrix_basis, caixas, alvo=alvo)
                preenchimento = (_prateleiras.parametros(grupo).get('preenchimento_divisorias')
                    if _prateleiras.MARCA_GRUPO in grupo else None)
                _partir(conj, planos, chapas, preenchimento or parametros(div).get('preenchimento', 'MANTER'))
                alvos.extend(o for o in conj.children if o.name not in anteriores
                             and (_gavetas.MARCA_GRUPO in o or _prateleiras.MARCA_GRUPO in o))
        except ValueError:
            # With 2+ partitions, the first may split before the second rejects:
            # the caller removes only `grupo`, which would orphan copies.
            for copia in alvos[1:]:
                for o in list(reversed(copia.children_recursive)):
                    _gavetas._remover(o)
                _gavetas._remover(copia)
            raise


def atualizar_dependentes():
    if (_chapas._ocupado[0] or _eventos._desfazendo[0] or bpy.context.mode != 'OBJECT'):
        return
    for grupo in [o for o in bpy.data.objects if MARCA_GRUPO in o]:
        l, a, m = vao(grupo)
        antes = grupo.get(CHAVE_VAO)
        if antes and (max(abs(l - antes[0]), abs(a - antes[1])) > TOL or any(
                abs(x - y) > 1e-7 for r, s in zip(m, grupo.matrix_basis) for x, y in zip(r, s))):
            try:
                montar(grupo)
            except ValueError as erro:
                # Opening no longer fits: otherwise the timer failed every cycle
                # and stopped all remaining maintenance.
                print("[Archy Builder] partitions:", erro)
    pendentes = []
    for grupo in list(bpy.data.objects):
        dono = (_gavetas if _gavetas.MARCA_GRUPO in grupo else
                _prateleiras if _prateleiras.MARCA_GRUPO in grupo else None)
        if dono is None or CHAVE_APOIOS not in grupo:
            continue
        l, a, m = dono.vao(grupo)
        antigo_l, antigo_a = grupo[dono.CHAVE_VAO]
        if max(abs(l - antigo_l), abs(a - antigo_a)) < TOL and all(
                abs(x - y) < 1e-7 for r, s in zip(m, grupo.matrix_basis) for x, y in zip(r, s)):
            continue
        p = dono.parametros(grupo)
        if antigo_l > TOL:
            individuais = p.get('individuais') or ({} if dono is _gavetas else [])
            for q in (individuais.values() if dono is _gavetas else individuais):
                for chave in ('largura_mm', 'x_mm'):
                    if chave in q:
                        q[chave] *= l / antigo_l
        dono.calcular(l, a, p)
        pendentes.append((dono, grupo, l, a, m, p))
    for dono, grupo, l, a, m, p in pendentes:
        grupo[dono.CHAVE_PARAMETROS] = p
        grupo.matrix_basis = m
        if dono is _gavetas:
            _gavetas._reencaixar_existentes(grupo, l, a, p)
            for obj in grupo.children_recursive:
                if _gavetas._puxadores._eh_puxador_parametrico(obj):
                    _gavetas._puxadores.posicionar_puxador(obj)
        else:
            _prateleiras.montar(grupo)


def editar(context, grupo, nome, valor):
    p = parametros(grupo)
    antes = _portas._copiar_parametros(p)
    nome = nome.removeprefix('divisorias_')
    if nome.startswith('vao_'):
        l, a, _m = vao(grupo)
        g = calcular(l, a, p)['vaos']
        k = int(nome.split('_')[1])
        vizinho = k + 1 if k + 1 < len(g) else k - 1
        g[vizinho] -= float(valor) - g[k]
        g[k] = float(valor)
        p['vaos_mm'] = g
    elif nome not in ('espessura_mm', 'profundidade_mm', 'recuo_mm'):
        return "Unknown partition field"
    else:
        p[nome] = float(valor)
        if nome == 'espessura_mm':
            p['vaos_mm'] = []
    l, a, _m = vao(grupo)
    try:
        calcular(l, a, p)
    except ValueError as erro:
        return str(erro)
    grupo[CHAVE_PARAMETROS] = p
    montar(grupo)
    try:
        atualizar_dependentes()
    except ValueError as erro:
        grupo[CHAVE_PARAMETROS] = antes
        montar(grupo)
        atualizar_dependentes()
        return str(erro)
    return None


def selecionar(context, obj, nivel='GRUPO', somar=False):
    grupo = grupo_de(obj)
    if grupo is None:
        return False
    garantir_blocagem(grupo)
    if not somar:
        for o in context.selected_objects:
            o.select_set(False)
    alvos = ([obj] if nivel == 'INDIVIDUAL' and obj != grupo else
             [o for g in grupos_da_blocagem(grupo) for o in [g, *pecas(g)]])
    for o in alvos:
        if o.visible_get():
            o.select_set(True)
    context.view_layer.objects.active = alvos[0]
    context.scene.cabinet_aba = 'DIVISORIAS'
    if context.area:
        context.area.tag_redraw()
    return True


def aplicar(context, grupo, chave, novo, lado=None):
    letra = chave[0]
    if letra == 'V':
        return editar(context, grupo, 'vao_%d' % chave[1], novo)
    if letra == 'P':
        antes = list(grupo[CHAVE_MARGENS])
        if lado == 'max':
            margens = list(antes)
            margens[4] -= float(novo) - valor(grupo, ('P',))
            grupo[CHAVE_MARGENS] = margens
        erro = editar(context, grupo, 'profundidade_mm', novo)
        if erro:
            grupo[CHAVE_MARGENS] = antes
            montar(grupo)
        return erro
    antes = list(grupo[CHAVE_MARGENS])
    margens = list(antes)
    l, a, _m = vao(grupo)
    k = (0 if lado == 'max' else 1) if letra == 'L' else (2 if lado == 'max' else 3)
    # As with drawers/shelves: a negative margin would put everything outside the cabinet.
    margens[k] = max(0.0, margens[k] - (float(novo) - (l if letra == 'L' else a)))
    grupo[CHAVE_MARGENS] = margens
    try:
        l, a, _m = vao(grupo)
        calcular(l, a, parametros(grupo))
        montar(grupo)
        atualizar_dependentes()
    except ValueError as erro:
        grupo[CHAVE_MARGENS] = antes
        montar(grupo)
        atualizar_dependentes()
        return str(erro)


def copia(grupo):
    return grupo.name, parametros(grupo), list(grupo[CHAVE_MARGENS])


def restaurar(estado):
    nome, p, margens = estado
    grupo = bpy.data.objects.get(nome)
    if grupo is not None:
        grupo[CHAVE_PARAMETROS] = p
        grupo[CHAVE_MARGENS] = margens
        montar(grupo)
        atualizar_dependentes()


def _criando():
    return _assistente_divisorias[0] is not None


class OBJECT_OT_criar_divisorias(_gavetas.AssistenteDoVao, Operator):
    """Create partitions and segment systems crossing the opening."""
    bl_idname = 'object.cabinet_criar_divisorias'
    bl_label = "Create Partitions"
    bl_options = {'REGISTER', 'UNDO'}
    _estado = _assistente_divisorias
    RECADOS = {
        'CANTO1': "Mark the top left corner of the opening",
        'CANTO2': "Mark the bottom right corner of the opening",
        'QUANTIDADE': "Scroll: partition count | Click: create"}
    MAXIMO = MAXIMO_DIVISORIAS
    ITEM = ('divisoria', 'divisorias')
    ABA = 'DIVISORIAS'
    FIM_QUANTIDADE = "Click to create"

    def _parametros_padrao(self):
        return dict(PARAMETROS_PADRAO, vaos_mm=[])

    def _calcular(self, largura, altura, p):
        return calcular(largura, altura, p)

    def _caixas_da_previa(self, dados):
        return dados['divisorias']

    def _comecar_no_modulo(self, conj, ponto):
        # Depth comes from `_definir_vao` at the second corner, up to the back.
        self._w['p']['espessura_mm'] = float(_portas._espessura_do_vao(conj))

    def _depois_da_quantidade(self, context):
        return self._criar(context)

    def _criar_grupo(self, context, conj, margens, p):
        return criar_divisorias(context, conj, margens, p, self._w.get('referencia'))

    def _selecionar_grupo(self, context, grupo):
        selecionar(context, grupo)


def esquecer():
    _assistente_divisorias[0] = None
