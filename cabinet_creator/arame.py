"""Previa em wireframe das ferragens e dos puxadores (pedido do usuario)."""

import bpy, bmesh, math, gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_opcoes = _portas = _ferragens = _puxadores = _hud = None

# ---- ARAME: a previa das ferragens e dos puxadores (pedido do usuario)
# Dobradica, pistao e puxador aparecem como WIREFRAME da peca de verdade,
# na cor de realce e na espessura das linhas da HUD -- antes a dobradica
# era uma caixa de volume e o puxador so' o ponto onde ia ancorar. Por
# cima de tudo (raio-X), como o resto da HUD. O rig da Reta tem ~190 mil
# arestas avaliadas: o arame dele e' so' o CONTORNO, medido uma vez no
# asset (`extrair_arame_dobradica.py`) e desenhado em lote, peca a peca.
ANGULO_VINCO_ARAME = 30.0        # o mesmo do extrator (contorno do perfil)
LADOS_CILINDRO_ARAME = 16
_arame_rig = [None]              # o arame do asset, lido uma vez
_arame_perfil = [None]           # contorno do modelo do perfil
_lotes_arame = {}                # malha do rig -> lote na GPU


def _dados_arame_rig():
    """{'malhas': {malha: [pontos aos pares, m, espaco do objeto]},
    'pecas': [(malha, pose em m na raiz, porta fechada)]} ou None."""
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
            pecas.append((peca['malha'], pose))
        _arame_rig[0] = {'malhas': malhas, 'pecas': pecas}
    return _arame_rig[0]


def _arame_caixa(cantos):
    """Pontos aos pares das 12 arestas (cantos na ordem de ARESTAS_CAIXA)."""
    return [Vector(cantos[k]) for i, j in _portas.ARESTAS_CAIXA for k in (i, j)]


def _arame_cilindro(base, eixo, raio, comprimento,
                    lados=LADOS_CILINDRO_ARAME):
    """Pontos aos pares: as duas tampas e 4 geratrizes, de `base` rumo a
    `eixo`."""
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
    """(pecas do rig [(matriz m, malha)], pontos aos pares em m) das
    ferragens PLANEJADAS (`_ferragens_da_porta`: mm, referencial do
    grupo/vao) -- a previa do wizard, antes de existir objeto."""
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
            # a placa e o suporte no calco (`_calco_rig`), como na peca
            calco = item.get('calco', {})
            pecas += [(raiz @ _ferragens._matriz_calco(calco.get(
                _ferragens.MALHAS_CALCO.get(malha), 0.0)) @ pose, malha)
                for malha, pose in rig['pecas']]
        elif forma in {'CAIXA', 'CAIXAS'}:
            for cantos in item.get('caixas') or [item['cantos']]:
                pontos += [p / 1000.0 for p in _arame_caixa(cantos)]
        elif forma == 'PERFIL':         # trilho da moldura: a secao nas pontas
            x0, x1 = item['x']
            fecho = [] if item.get('aberto') else None
            for poligono in item['poligonos']:
                volta = poligono[1:] + (poligono[:1] if fecho is None else [])
                for (za, ya), (zb, yb) in zip(poligono, volta):
                    for x in (x0, x1):
                        pontos += [Vector((x, ya, za)) / 1000.0,
                                   Vector((x, yb, zb)) / 1000.0]
                    pontos += [Vector((x0, ya, za)) / 1000.0,
                               Vector((x1, ya, za)) / 1000.0]
        elif forma == 'CILINDRO':          # caneco: em Z, centrado
            meio = Vector((0.0, 0.0, item['comprimento'] / 2.0))
            pontos += [p / 1000.0 for p in _arame_cilindro(
                Vector(item['origem']) - meio, Vector((0.0, 0.0, 1.0)),
                item['raio'], item['comprimento'])]
        elif forma == 'HASTE' and item.get('mira') in por_id:
            origem = Vector(item['origem'])
            pontos += [p / 1000.0 for p in _arame_cilindro(
                origem, Vector(por_id[item['mira']]['origem']) - origem,
                item['raio'], item['comprimento'])]
    return pecas, pontos


def _arame_ferragens(grupo, tipos):
    """(pecas, pontos) em MUNDO das ferragens `tipos` da porta, na pose de
    agora: as pecas do rig pelo contorno do asset, o resto (caixas,
    canecos, pistoes) pela propria malha, que e' pouca."""
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
        pontos += [mundo @ vertices[i].co for e in o.data.edges
                   for i in e.vertices]
    return pecas, pontos


def _modelo_perfil_carregado():
    """A malha do modelo do perfil, se ja' esta' no arquivo (no desenho
    nao se carrega nada)."""
    dados = _puxadores._dados_perfil()
    return next((m for m in bpy.data.meshes if dados is not None
                 and m.get('cabinet_origem') == dados['malha']
                 and not m.library), None)


def _contorno_perfil():
    """Contorno (pontos aos pares, espaco do modelo) do perfil do usuario,
    se o modelo ja' foi carregado."""
    if _arame_perfil[0] is None:
        modelo = _modelo_perfil_carregado()
        if modelo is None:
            return None
        bm = bmesh.new()
        bm.from_mesh(modelo)
        pares = []
        for e in bm.edges:
            if (len(e.link_faces) != 2 or e.calc_face_angle(0.0)
                    > math.radians(ANGULO_VINCO_ARAME)):
                pares += [v.co.copy() for v in e.verts]
        bm.free()
        _arame_perfil[0] = pares
    return _arame_perfil[0]


def _contorno_malha(malha):
    """Arestas de contorno (pontos aos pares, espaco da malha)."""
    bm = bmesh.new()
    bm.from_mesh(malha)
    pares = []
    for e in bm.edges:
        if (len(e.link_faces) != 2 or e.calc_face_angle(0.0)
                > math.radians(ANGULO_VINCO_ARAME)):
            pares += [v.co.copy() for v in e.verts]
    bm.free()
    return pares


def _contorno_modelo(arquivo):
    """Contorno do modelo do usuario, se a malha ja' foi carregada (o
    posicionador carrega; no desenho nao se abre .blend)."""
    if arquivo not in _puxadores._contornos_modelo:
        malha = _puxadores._malha_modelo_usuario(arquivo, carregar=False)
        if malha is None:
            return None
        _puxadores._contornos_modelo[arquivo] = _contorno_malha(malha)
    return _puxadores._contornos_modelo[arquivo]


def _arame_puxador(chapa, tipo, borda, face, fracao, comprimento=None,
                   recuo=None, arquivo=''):
    """Pontos (MUNDO, aos pares) do puxador como ele fica naquela linha:
    a previa do posicionador e do arraste com Alt."""
    if tipo == 'MODELO' and comprimento is None:
        malha = _puxadores._malha_modelo_usuario(arquivo, carregar=False)
        comprimento = _puxadores._comprimento_do_modelo(malha)
        if recuo is None and malha is not None and 'puxador_recuo_mm' in malha:
            recuo = float(malha['puxador_recuo_mm'])
    matriz, comprimento = _puxadores._lugar_do_puxador(chapa, tipo, borda, face, fracao,
                                            comprimento, recuo)
    mundo = chapa.matrix_world @ matriz
    espessura = chapa.chapa_espessura_mm
    if tipo == 'MODELO':
        contorno = _contorno_modelo(arquivo)
        if contorno is not None:
            return [mundo @ p for p in contorno]
        tipo = 'ALCA'
    contorno = _contorno_perfil() if tipo == 'PERFIL' else None
    if contorno is not None:
        # a mesma deformacao da malha (`_malha_perfil_do_modelo`)
        ajuste = _puxadores._ajuste_do_perfil(_modelo_perfil_carregado(), espessura,
                                   comprimento)
        local = [_puxadores._deformar_perfil(p, *ajuste) for p in contorno]
    else:
        local = [p / 1000.0 for x0, x1, y0, y1, z0, z1
                 in _puxadores._caixas_puxador(tipo, espessura, comprimento)
                 for p in _arame_caixa([Vector((x, y, z)) for x in (x0, x1)
                                        for y in (y0, y1) for z in (z0, z1)])]
    return [mundo @ p for p in local]


def _arame_do_objeto_puxador(pux):
    if not _puxadores._eh_puxador_parametrico(pux) or pux.parent is None:
        return []
    return _arame_puxador(pux.parent, pux['puxador_tipo'],
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
    """Wireframe na cor de realce e na espessura das linhas da HUD,
    por cima de tudo. `pecas` = [(matriz, malha do rig)], em lote na GPU;
    `pontos` aos pares; `matriz` leva os dois ao mundo."""
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
    """O puxador que o posicionador vai criar: na linha sob o mouse (antes
    so' aparecia o ponto) e, escolhendo o ponto, o puxador de previa."""
    estado = _puxadores._posicionador_puxador[0]
    if estado is None:
        return []
    if estado['fase'] == 'POSICAO':
        return _arame_do_objeto_puxador(
            bpy.data.objects.get(estado.get('pux') or ''))
    chapa = bpy.data.objects.get(estado.get('chapa') or '')
    if chapa is None or estado.get('borda') is None:
        return []
    return _arame_puxador(chapa, estado['tipo'], estado['borda'],
                          estado['face'], estado.get('fracao', 0.5),
                          arquivo=estado.get('arquivo', ''))


def _desenhar_aramados(context):
    """Arame das ferragens selecionadas, do puxador sendo posicionado e
    do arrastado com Alt (o wizard desenha o das ferragens dele)."""
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
