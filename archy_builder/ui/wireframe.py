"""Wireframe preview of hardware and handles (user request)."""

import bpy, bmesh, math, gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

# Used only at RUNTIME (circular imports): __init__ binds these aliases after loading
# all modules (`_ligar_modulos`).
_opcoes = _portas = _ferragens = _puxadores = _hud = None

# ---- WIREFRAME: hardware and handle preview (user request)
# Hinges, gas struts and handles appear as WIREFRAMES of the actual parts, in the
# highlight color and HUD line width. Previously hinges were volume boxes and handles
# were only their anchor points. Draw above everything (X-ray), like the rest of the
# HUD. The straight hinge rig has ~190,000 evaluated edges: use only its OUTLINE,
# measured once in the asset (`extrair_arame_dobradica.py`) and batch-drawn part by
# part.
ANGULO_VINCO_ARAME = 30.0        # Same as the extractor (profile outline).
LADOS_CILINDRO_ARAME = 16
# Edge marker (INT 1) excluding the standard screw's shaft and thread from the outline:
# those lie inside the wood (`gerar_parafuso.py`). The marker follows when the screw is
# copied into the handle mesh.
ATRIBUTO_SEM_ARAME = 'cabinet_sem_arame'
MARCA_ARAME_TOPO = 'cabinet_arame_topo'     # On the mesh: only the marked top.
_contornos_ferragem = {}         # Mesh geometry -> outline (selection).
_arame_rig = [None]              # Asset wireframe, read once.
_arame_perfil = [None]           # Profile model outline.
_arame_borda = [None]            # Edge model outline.
_arame_parafuso = [None]         # Standard screw outline.
_lotes_arame = {}                # Rig mesh -> GPU batch.


def _dados_arame_rig():
    """{'malhas': {mesh: [paired points in meters, object space]}, 'pecas': [(mesh,
    root-relative pose in meters with door closed, mounting-plate part)]}, or None."""
    if _arame_rig[0] is None:
        bruto = (_ferragens._dados_dobradica_reta() or {}).get('arame')
        if not bruto:
            return None
        malhas = {chave: [Vector(v[i:i + 3]) / 1000.0
                          for i in range(0, len(v), 3)]
                  for chave, v in bruto['malhas'].items()}
        pecas = []
        for peca in bruto['pecas']:
            pose = Matrix([peca['pose'][i * 4:i * 4 + 4] for i in range(4)])
            pose.translation = pose.translation / 1000.0
            # Identify mounting-plate parts by PARENT in new JSON (the standard screw
            # uses the same mesh in the plate and cup); old JSON uses the mesh name.
            parte = peca.get('calco', _ferragens.MALHAS_CALCO.get(peca['malha'], ''))
            pecas.append((peca['malha'], pose, parte))
        _arame_rig[0] = {'malhas': malhas, 'pecas': pecas}
    return _arame_rig[0]


def _arame_caixa(cantos):
    """Paired points for the twelve edges (corners in ARESTAS_CAIXA order)."""
    return [Vector(cantos[k]) for i, j in _portas.ARESTAS_CAIXA for k in (i, j)]


def _arame_cilindro(base, eixo, raio, comprimento,
                    lados=LADOS_CILINDRO_ARAME):
    """Paired points: both caps and four longitudinal lines, from `base` along `eixo`."""
    eixo = (eixo.normalized() if eixo.length > 1e-9
            else Vector((0.0, 0.0, 1.0)))
    n1 = eixo.orthogonal().normalized()
    n2 = eixo.cross(n1)
    raios = [(n1 * math.cos(a) + n2 * math.sin(a)) * raio
             for a in (k * math.tau / lados for k in range(lados))]
    pontos = []
    for u in (0.0, comprimento):
        volta = [base + eixo * u + r for r in raios]
        for a, b in zip(volta, volta[1:] + volta[:1]):
            pontos += [a, b]
    for r in raios[::lados // 4]:
        pontos += [base + r, base + eixo * comprimento + r]
    return pontos


def _arame_dos_itens(itens):
    """(rig parts [(matrix in meters, mesh)], paired points in meters) for PLANNED
    hardware (`_ferragens_da_porta`: mm, group/opening frame): wizard preview before
    any object exists."""
    rig = _dados_arame_rig()
    por_id = {item['id']: item for item in itens}
    pecas, pontos = [], []
    for item in itens:
        forma = item['forma']
        if forma == 'RIG':
            if rig is None:
                continue
            raiz = item['matriz'].copy()
            raiz.translation = raiz.translation / 1000.0
            # Plate and support on the mounting plate (`_calco_rig`), as in the actual
            # part.
            calco = item.get('calco', {})
            pecas += [(raiz @ _ferragens._matriz_calco(calco.get(parte, 0.0))
                       @ pose, malha) for malha, pose, parte in rig['pecas']]
        elif forma in {'CAIXA', 'CAIXAS', 'PRISMA'}:
            for cantos in item.get('caixas') or [item['cantos']]:
                pontos += [p / 1000.0 for p in _arame_caixa(cantos)]
        elif forma == 'BRACO':
            origem = Vector(item['origem'])
            eixo = (item['destino'] - origem).normalized()
            x = Vector((0, 1, 0))
            z = x.cross(eixo)
            cantos = [origem + eixo * u + x * v + z * t
                      for u in (0, item['comprimento']) for v in (-6, 6) for t in (-3, 3)]
            pontos += [p / 1000 for p in _arame_caixa(cantos)]
        elif forma == 'PERFIL':         # Frame track: cross-sections at the ends.
            x0, x1 = item['x']
            for poligono in item['poligonos']:
                volta = poligono[1:] + ([] if item.get('aberto') else poligono[:1])
                for (za, ya), (zb, yb) in zip(poligono, volta):
                    for x in (x0, x1):
                        pontos += [Vector((x, ya, za)) / 1000.0,
                                   Vector((x, yb, zb)) / 1000.0]
                # A longitudinal edge at EVERY vertex: the last vertex of an open
                # profile starts no segment, but the actual mesh has that edge.
                for za, ya in poligono:
                    pontos += [Vector((x0, ya, za)) / 1000.0,
                               Vector((x1, ya, za)) / 1000.0]
        elif forma == 'CILINDRO':          # Cup: centered along Z.
            eixo = Vector((0, 1, 0) if item.get('eixo') == 'Y' else (0, 0, 1))
            meio = eixo * (item['comprimento'] / 2)
            pontos += [p / 1000.0 for p in _arame_cilindro(
                Vector(item['origem']) - meio, eixo,
                item['raio'], item['comprimento'])]
        elif forma == 'PARAFUSO':
            # Only the head's top circle, slightly above the plate (as in the part
            # wireframe: `marcar_arame_parafuso`).
            eixo = Vector((0, 0, 1 if item.get('sentido', 1) >= 0 else -1))
            topo = Vector(item['origem']) + eixo * _ferragens.SALIENCIA_PARAFUSO_MM
            pontos += [p / 1000.0 for p in _arame_cilindro(
                topo, eixo, _ferragens.RAIO_CABECA_PARAFUSO_MM, 0.0)[:2 * LADOS_CILINDRO_ARAME]]
        elif forma == 'HASTE' and item.get('mira') in por_id:
            origem = Vector(item['origem'])
            pontos += [p / 1000.0 for p in _arame_cilindro(
                origem, Vector(por_id[item['mira']]['origem']) - origem,
                item['raio'], item['comprimento'])]
    return pecas, pontos


def _arame_ferragens(grupo, tipos):
    """(parts, points) in WORLD space for door hardware `tipos`, in its current pose:
    rig parts use the asset outline; other parts (boxes, cups, gas struts) use their
    own small meshes."""
    rig = _dados_arame_rig()
    pecas, pontos = [], []
    for o in _ferragens._ferragens_portas(grupo):
        if (o.type != 'MESH' or not o.visible_get() or _ferragens.TIPOS_SELECAO_FERRAGEM
                .get(o.get(_ferragens.CHAVE_FERRAGEM)) not in tipos):
            continue
        chave = o.data.get('cabinet_origem')
        if rig is not None and 'cabinet_peca' in o and chave in rig['malhas']:
            pecas.append((o.matrix_world.copy(), chave))
            continue
        mundo, vertices = o.matrix_world, o.data.vertices
        if ATRIBUTO_SEM_ARAME in o.data.attributes:
            # Screw: all edges exposed the entire thread (user screenshot); the marked
            # outline contains only the head's top.
            pontos += [mundo @ p for p in _contorno_da_ferragem(o.data)]
            continue
        pontos += [mundo @ vertices[i].co for e in o.data.edges
                   for i in e.vertices]
    return pecas, pontos


def _modelo_perfil_carregado():
    """Profile model mesh if already present in the file; never load anything during
    drawing."""
    dados = _puxadores._dados_perfil()
    return next((m for m in bpy.data.meshes if dados is not None
                 and m.get('cabinet_origem') == dados['malha']
                 and not m.library), None)


def _modelo_borda_carregado():
    dados = _puxadores._dados_borda()
    return next((m for m in bpy.data.meshes if dados is not None
                 and m.get('cabinet_origem') == dados['malha']
                 and not m.library), None)


def preparar_modelos(tipo='PERFIL', arquivo=''):
    """Extract outlines during the event, before installing drawing."""
    if _arame_borda[0] is None:
        modelo = _modelo_borda_carregado()
        if modelo is not None:
            _arame_borda[0] = _contorno_malha(modelo)
    if _arame_parafuso[0] is None:
        parafuso = next((m for m in bpy.data.meshes if not m.library
                         and m.get('cabinet_origem') == _ferragens.NOME_PARAFUSO), None)
        if parafuso is not None:
            # Head only (`ATRIBUTO_SEM_ARAME` removes the thread).
            _arame_parafuso[0] = _contorno_malha(parafuso)
    if _arame_perfil[0] is None:
        modelo = _modelo_perfil_carregado()
        if modelo is not None:
            _arame_perfil[0] = _contorno_malha(modelo)
            _puxadores._corte_do_perfil(modelo)
    if tipo == 'MODELO' and arquivo not in _puxadores._contornos_modelo:
        malha = _puxadores._malha_modelo_usuario(arquivo, carregar=False)
        if malha is not None:
            _puxadores._contornos_modelo[arquivo] = _contorno_malha(malha)


def _contorno_perfil():
    """Prepared numeric data only; redraw never extracts meshes."""
    return _arame_perfil[0]


def _contorno_da_ferragem(malha):
    """Cached `_contorno_malha`: selection redraws every frame and the screw has
    hundreds of edges. The key contains geometry (name, counts and first vertex),
    never the object."""
    v = malha.vertices[0].co if len(malha.vertices) else Vector()
    chave = (malha.name, len(malha.vertices), len(malha.edges),
             tuple(round(c, 7) for c in v))
    if chave not in _contornos_ferragem:
        if len(_contornos_ferragem) > 256:
            _contornos_ferragem.clear()
        _contornos_ferragem[chave] = _contorno_malha(malha)
    return _contornos_ferragem[chave]


def marcar_arame_parafuso(malha):
    """Include only the TOP of the standard screw head (circle and cross, flush with
    the part) in the wireframe; mark the rest with `ATRIBUTO_SEM_ARAME`. Apply the
    `gerar_parafuso.py` rule ONCE to the scene's existing mesh, deduplicated by
    `cabinet_origem`, which takes precedence over the asset mesh. Marking down to
    the cone, or leaving it unmarked, cluttered the head."""
    if malha.get(MARCA_ARAME_TOPO):
        return
    camada = malha.attributes.get(ATRIBUTO_SEM_ARAME)
    if camada is None or camada.domain != 'EDGE' or camada.data_type != 'INT':
        if camada is not None:
            malha.attributes.remove(camada)
        camada = malha.attributes.new(ATRIBUTO_SEM_ARAME, 'INT', 'EDGE')
    vertices = malha.vertices
    topo = max((v.co.z for v in vertices), default=0.0) - 1e-6
    for e in malha.edges:
        camada.data[e.index].value = int(min(vertices[i].co.z for i in e.vertices) < topo)
    malha[MARCA_ARAME_TOPO] = True


def _contorno_malha(malha):
    """Outline edges (paired points in mesh space)."""
    bm = bmesh.new()
    bm.from_mesh(malha)
    pares = _contorno_bmesh(bm)
    bm.free()
    return pares


def _contorno_bmesh(bm):
    pares = []
    fora = bm.edges.layers.int.get(ATRIBUTO_SEM_ARAME)
    for e in bm.edges:
        if fora is not None and e[fora]:
            continue
        if (len(e.link_faces) != 2 or e.calc_face_angle(0.0)
                > math.radians(ANGULO_VINCO_ARAME)):
            pares += [v.co.copy() for v in e.verts]
    return _ordenar_contorno(pares)


def _ordenar_contorno(pontos):
    """Common geometric ordering: BMesh and boxes enumerate edges differently."""
    def chave(p):
        # Tolerance applies only to sorting; coordinates retain their precision.
        return tuple(round(c, 7) for c in p)
    pares = [sorted(pontos[i:i+2], key=chave) for i in range(0, len(pontos)-1, 2)]
    pares.sort(key=lambda par: (chave(par[0]), chave(par[1])))
    return [p for par in pares for p in par]


def _matriz_avaliada(matriz):
    local, rotacao, escala = matriz.decompose()
    rotacao.normalize()  # The depsgraph normalizes the object's quaternion.
    return Matrix.LocRotScale(local, rotacao, escala)


def _contorno_modelo(arquivo):
    """User model outline if the mesh is already loaded (placement loads it; drawing
    never opens .blend files)."""
    return _puxadores._contornos_modelo.get(arquivo)


def preparar_previa(chapa, tipo, borda, face, fracao=.5, arquivo='',
                     comprimento=None, recuo=None):
    """Event only: outline of the same geometry used to assemble the part."""
    preparar_modelos(tipo, arquivo)
    modelo = (_modelo_perfil_carregado() if tipo == 'PERFIL' else
              _puxadores._malha_modelo_usuario(arquivo, carregar=False)
              if tipo == 'MODELO' else None)
    if tipo == 'MODELO' and modelo is not None:
        if comprimento is None:
            comprimento = _puxadores._comprimento_do_modelo(modelo)
        if recuo is None and 'puxador_recuo_mm' in modelo:
            recuo = float(modelo['puxador_recuo_mm'])
    if tipo != 'PERFIL':
        # Dragging changes only the pose: the model uses its prepared numeric outline
        # and handles use the same box definitions as the actual part.
        return _arame_puxador_legado(chapa,tipo,borda,face,fracao,
                                     comprimento,recuo,arquivo)
    borda, fracao = _puxadores._borda_e_fracao(chapa, borda, fracao)
    matriz, comprimento = _puxadores._lugar_do_puxador(
        chapa, tipo, borda, face, fracao, comprimento, recuo)
    if modelo is not None:
        bm = _puxadores._bmesh_perfil(
            modelo, chapa.chapa_espessura_mm, comprimento, chapa, borda, face)
    else:
        bm = _puxadores._bmesh_caixas(
            tipo, chapa.chapa_espessura_mm, comprimento, chapa, borda, face)
    try:
        # The part stores location/quaternion/scale; the preview uses the same native
        # recomposition, including the precision of 90-degree rotations.
        mundo = chapa.matrix_world @ _matriz_avaliada(matriz)
        return [mundo @ p for p in _contorno_bmesh(bm)]
    finally:
        bm.free()


def _arame_puxador(chapa, tipo, borda, face, fracao, comprimento=None,
                   recuo=None, arquivo=''):
    """Preparation entry point for consumers outside the draw callback."""
    return preparar_previa(chapa, tipo, borda, face, fracao, arquivo,
                            comprimento, recuo)


def _arame_puxador_legado(chapa, tipo, borda, face, fracao, comprimento=None,
                   recuo=None, arquivo=''):
    """Handle points (WORLD space, paired) as positioned on that line: placement and
    Alt-drag preview."""
    if tipo == 'MODELO' and comprimento is None:
        pontos = _contorno_modelo(arquivo) or []
        xs = [p.x for p in pontos]
        comprimento = (max(xs)-min(xs))*1000 if xs else 0
    matriz, comprimento = _puxadores._lugar_do_puxador(chapa, tipo, borda, face, fracao,
                                            comprimento, recuo)
    mundo = chapa.matrix_world @ _matriz_avaliada(matriz)
    espessura = chapa.chapa_espessura_mm
    if tipo == 'MODELO':
        contorno = _contorno_modelo(arquivo)
        if contorno is not None:
            return [mundo @ p for p in contorno]
        tipo = 'ALCA'
    contorno = (_contorno_perfil() if tipo == 'PERFIL'
                and _puxadores._corte_perfil[0] is not None else None)
    if tipo == 'BORDA' and _arame_borda[0] is not None:
        # Same mesh deformation (`_malha_borda_do_modelo`).
        ajuste = _puxadores._ajuste_da_borda(espessura, comprimento)
        local = [_puxadores._deformar_borda(p, *ajuste) for p in _arame_borda[0]]
        # Flange screws, as in the actual part (`_parafusos_da_borda`).
        for lugar in (_puxadores.lugares_dos_parafusos_borda(espessura, comprimento)
                      if _arame_parafuso[0] is not None else ()):
            local += [_puxadores.ponta_do_parafuso(lugar @ p) for p in _arame_parafuso[0]]
    elif contorno is not None:
        # Same mesh deformation (`_malha_perfil_do_modelo`).
        ajuste = _puxadores._ajuste_do_perfil(None, espessura,
                                   comprimento)
        local = [_puxadores._deformar_perfil(p, *ajuste) for p in contorno]
    else:
        local = [p / 1000.0 for x0, x1, y0, y1, z0, z1
                 in _puxadores._caixas_puxador(tipo, espessura, comprimento)
                 for p in _arame_caixa([Vector((x, y, z)) for x in (x0, x1)
                                        for y in (y0, y1) for z in (z0, z1)])]
    return [mundo @ p for p in _ordenar_contorno(local)]


def _arame_do_objeto_puxador(pux):
    if not _puxadores._eh_puxador_parametrico(pux) or pux.parent is None:
        return []
    pontos = pux.get('puxador_contorno')
    if pontos is not None:
        return [pux.matrix_world @ Vector(pontos[i:i+3])
                for i in range(0, len(pontos)-2, 3)]
    return _arame_puxador_legado(pux.parent, pux['puxador_tipo'],
                          pux.get('puxador_borda', 'Y+'),
                          int(pux.get('puxador_face', 1)),
                          float(pux.get('puxador_fracao', 0.5)),
                          pux.get('puxador_comprimento_mm'),
                          pux.get('puxador_recuo_mm'),
                          pux.get('puxador_modelo', ''))


def _lote_arame(shader, malha):
    lote = _lotes_arame.get(malha)
    if lote is None:
        rig = _dados_arame_rig()
        if rig is None or malha not in rig['malhas']:
            return None
        lote = _lotes_arame[malha] = batch_for_shader(
            shader, 'LINES', {'pos': rig['malhas'][malha]})
    return lote


def _desenhar_arame(context, pecas, pontos, matriz=None, cor=None):
    """Wireframe in highlight color and HUD line width, above everything. `pecas` =
    [(matrix, rig mesh)], GPU-batched; `pontos` are paired; `matriz` transforms both
    to world space."""
    if not pecas and not pontos:
        return
    matriz = matriz if matriz is not None else Matrix.Identity(4)
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('NONE')
    try:
        shader.bind()
        shader.uniform_float('viewportSize', (context.region.width,
                                              context.region.height))
        shader.uniform_float('lineWidth', float(_opcoes._opcao('hud_espessura_linha')))
        shader.uniform_float('color', cor or _hud._cor_realce_hud())
        for m, malha in pecas:
            lote = _lote_arame(shader, malha)
            if lote is not None:
                with gpu.matrix.push_pop():
                    gpu.matrix.multiply_matrix(matriz @ m)
                    lote.draw(shader)
        if pontos:
            batch_for_shader(shader, 'LINES', {
                'pos': [matriz @ p for p in pontos]}).draw(shader)
    finally:
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('NONE')


def _arame_do_posicionador():
    """Handle to be created by placement: on the line under the mouse (previously only
    a point appeared) and, once the point is chosen, the preview handle."""
    estado = _puxadores._posicionador_puxador[0]
    if estado is None:
        return []
    if estado['fase'] == 'POSICAO':
        return _arame_do_objeto_puxador(
            bpy.data.objects.get(estado.get('pux') or ''))
    if 'arame' in estado:
        return estado['arame']
    # Legacy states not yet prepared: numeric calculations only.
    chapa = bpy.data.objects.get(estado.get('chapa') or '')
    if chapa is None or estado.get('borda') is None:
        return []
    return _arame_puxador_legado(chapa, estado['tipo'], estado['borda'],
                          estado['face'], estado.get('fracao', .5),
                          arquivo=estado.get('arquivo', ''))


def _desenhar_aramados(context):
    """Wireframe of selected hardware, the handle being placed and the Alt-dragged
    handle (the wizard draws its own hardware)."""
    if not _hud._contexto_hud(context):
        return
    pecas, pontos = [], []
    for grupo, tipos in _ferragens._ferragens_em_edicao(context):
        mais_pecas, mais_pontos = _arame_ferragens(grupo, tipos)
        pecas += mais_pecas
        pontos += mais_pontos
    pontos += _arame_do_posicionador()
    arraste = _puxadores._arraste_puxador[0]
    if arraste is not None:
        pontos += _arame_do_objeto_puxador(
            bpy.data.objects.get(arraste['puxador']))
    _desenhar_arame(context, pecas, pontos)
