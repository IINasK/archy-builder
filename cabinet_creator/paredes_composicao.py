"""Composicao existente na parede: cotas, larguras fixas e redistribuicao.

O timer publica numeros para UI/desenho. Mutacoes pertencem aos operadores;
resize e cancelamento reutilizam os contratos do modulo e da HUD.
"""
import math
import bpy
import bmesh
import blf
import gpu
from bpy.props import StringProperty
from bpy.types import Operator
from mathutils import Vector
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader

_paredes_edicao = _paredes = _modulos = _chapas = _hud = None
_gaveta = _gaveta_desenho = _opcoes = _biblioteca = None
_eventos = _orcamento = None

CHAVE_FIXA = 'parede_largura_fixa'
_resumo = [None]
_rotulos = [()]
_edicao = [None]
_interiores = [{}]
_sujos = [set()]
_handler_interior = [None]


def parede(obj):
    """Parede assumida explicitamente ou que ja' tem modulos associados."""
    if obj is None:
        return False
    s = _paredes_edicao._sessao[0]
    ultima = _paredes_edicao._ultima_face[0]
    return (_paredes.CHAVE_UID_PAREDE in obj or
            bool(s and obj.name == s['parede']) or
            bool(ultima and ultima[0] == obj.name))


def ficha(obj, s):
    caixa = _paredes.caixa_do_modulo(obj)
    if caixa is None:
        return None
    lo, hi = caixa
    escala = obj.matrix_world.to_scale()
    largura, altura, prof = ((hi[i] - lo[i]) * escala[i] for i in (0, 2, 1))
    costas = _paredes.ponto_das_costas(obj, caixa)
    inicio = costas.dot(Vector(s['u'])) - largura / 2
    return dict(nome=obj.name, inicio=inicio, fim=inicio + largura, base=costas.z,
                largura=largura, altura=altura, profundidade=prof,
                fixa=bool(obj.get(CHAVE_FIXA, False)))


def itens_da_face(context):
    s = _paredes_edicao._sessao[0]
    if not _paredes_edicao.ativa(context):
        return []
    obj = bpy.data.objects.get(s['parede'])
    if obj is None:
        return []
    encontrados = _paredes_edicao.associados(obj, Vector(s['ponto']), Vector(s['normal']),
                                             context.scene.objects, s['regiao'])
    itens = sorted(filter(None, (ficha(o, s) for o in encontrados)), key=lambda f: f['inicio'])
    s0, s1 = s['regiao']['retangulo'][:2]
    for item in itens:
        vizinhos = [f for f in itens if f['nome'] != item['nome'] and
                    f['base'] < item['base'] + item['altura'] - 1e-6 and
                    f['base'] + f['altura'] > item['base'] + 1e-6]
        item['vao_esquerdo'] = item['inicio'] - max([s0] + [f['fim'] for f in vizinhos if f['fim'] <= item['inicio'] + 1e-6])
        item['vao_direito'] = min([s1] + [f['inicio'] for f in vizinhos if f['inicio'] >= item['fim'] - 1e-6]) - item['fim']
    return itens


def selecionado(context, itens=None):
    obj = context.object
    if obj is None or not obj.select_get():
        return None
    modulo = _paredes.modulo_de(obj)
    return next((f for f in (itens if itens is not None else itens_da_face(context))
                 if modulo and f['nome'] == modulo.name), None)


def _intervalos_livres(context, s, base, altura, prof, excluir=()):
    return _paredes_edicao.faixas_livres(context, s, base, base + altura, prof, excluir)


def _validar_encaixe(context, s, item, excluir=()):
    if min(item[k] for k in ('largura', 'altura', 'profundidade')) < .02:
        return 'O modulo deve ter dimensoes de pelo menos 20 mm'
    faixas = _intervalos_livres(context, s, item['base'], item['altura'], item['profundidade'], excluir)
    if not any(item['inicio'] >= a - .00005 and item['fim'] <= b + .00005 for a, b in faixas):
        return 'O modulo nao cabe neste vao sem ultrapassar o limite ou outro objeto'
    return None


def _aplicar(context, item, s):
    obj = bpy.data.objects[item['nome']]
    atuais = ficha(obj, s)
    alvo = tuple(item[k] * 1000 for k in ('largura', 'altura', 'profundidade'))
    if any(abs(item[k] - atuais[k]) > 1e-6 for k in ('largura', 'altura', 'profundidade')):
        _modulos.redimensionar_orientado(obj, alvo)
    u, n, ponto = (Vector(s[k]) for k in ('u', 'normal', 'ponto'))
    costas = ponto + u * (item['inicio'] + item['largura'] / 2 - ponto.dot(u))
    costas.z = item['base']
    _paredes.colocar_na_parede(obj, bpy.data.objects[s['parede']], costas, n)
    context.view_layer.update()
    real = ficha(obj, s)
    if any(abs(real[k] - item[k]) > .00005 for k in ('largura', 'altura', 'profundidade', 'inicio', 'base')):
        raise ValueError('As dimensoes pedidas nao sao compativeis com os encaixes do modelo')


def _transacao(context, itens):
    backups, vinculos = [], []
    for item in itens:
        obj = bpy.data.objects[item['nome']]
        backups.append(_hud._estado_arraste_hud(context, dict(objeto=obj, tipo='modulo')))
        vinculos.append((obj.name, {k: tuple(obj[k]) if hasattr(obj[k], 'to_list') else obj[k]
                                    for k in _paredes.CHAVES_ASSOCIACAO if k in obj}))
    try:
        for item in itens:
            _aplicar(context, item, _paredes_edicao._sessao[0])
    except Exception as erro:
        for backup in backups:
            _hud._restaurar_arraste_hud(context, backup)
        for nome, valores in vinculos:
            obj = bpy.data.objects.get(nome)
            if obj:
                for k, v in valores.items():
                    obj[k] = v
        return str(erro)
    finally:
        _paredes._conferidos.clear()
        _paredes_edicao._plano[0] = None
        atualizar(context)
        _paredes_edicao._redesenhar()
    return None


def editar_modulo(context, nome, propriedade, valor_mm):
    if not _paredes_edicao.ativa(context):
        return 'Entre na edicao da parede'
    obj = _paredes.modulo_de(bpy.data.objects.get(nome))
    s = _paredes_edicao._sessao[0]
    item = next((f for f in itens_da_face(context) if obj and f['nome'] == obj.name), None)
    if item is None:
        return 'O modulo nao esta associado a esta face'
    if not math.isfinite(valor_mm) or valor_mm < 0:
        return 'Informe uma medida positiva ou zero'
    item = dict(item)
    valor = valor_mm / 1000
    s0, s1, z0, z1 = s['regiao']['retangulo']
    if propriedade in ('largura', 'altura', 'profundidade'):
        item[propriedade] = valor
    elif propriedade == 'esquerda':
        item['inicio'] = s0 + valor
    elif propriedade == 'direita':
        item['inicio'] = s1 - valor - item['largura']
    elif propriedade == 'instalacao':
        item['base'] = z0 + valor
    elif propriedade == 'vao_esquerdo':
        item['inicio'] = item['inicio'] - item['vao_esquerdo'] + valor
    elif propriedade == 'vao_direito':
        item['inicio'] = item['fim'] + item['vao_direito'] - valor - item['largura']
    else:
        return 'Cota de modulo desconhecida'
    item['fim'] = item['inicio'] + item['largura']
    erro = _validar_encaixe(context, s, item, (item['nome'],))
    return erro or _transacao(context, [item])


def fixar(context, nome, fixa):
    obj = bpy.data.objects.get(nome)
    if not obj or not any(f['nome'] == nome for f in itens_da_face(context)):
        return 'Modulo nao encontrado nesta parede'
    obj[CHAVE_FIXA] = bool(fixa)
    atualizar(context)
    _paredes_edicao._redesenhar()
    return None


def planejar_troca(context, s):
    obj = bpy.data.objects.get(s.get('substituir', ''))
    item = next((f for f in itens_da_face(context) if obj and f['nome'] == obj.name), None)
    if item is None:
        return {'erro': 'O modulo a substituir nao pertence mais a esta parede'}
    erro = _validar_encaixe(context, s, item, (item['nome'],))
    if erro:
        return {'erro': erro}
    return dict(largura=item['largura'], altura=item['altura'], profundidade=item['profundidade'],
                base=item['base'], inicios=[item['inicio']], alvo=item)


def substituir(context):
    s = _paredes_edicao._sessao[0]
    plano = planejar_troca(context, s)
    if plano.get('erro'):
        return plano['erro']
    if not s.get('modelo'):
        return 'Escolha o novo modelo na biblioteca'
    item = plano['alvo']
    antigo = bpy.data.objects[item['nome']]
    velhos = [antigo] + list(antigo.children_recursive)
    nomes_velhos = {o.name for o in velhos}
    colecoes = [c.name for c in antigo.users_collection if c.get('eh_colecao_modulo')
                 and all(o.name in nomes_velhos for o in c.all_objects)]
    antes = _paredes_edicao._dados_antes()
    selecao = [o.name for o in context.selected_objects]
    ativo = context.object.name if context.object else ''
    # o preset entra na raiz da cena; o substituto volta para o comodo do
    # original, senao sai do orcamento
    comodo = _orcamento._nome_comodo(_orcamento._comodo_do_modulo(antigo))
    try:
        m = s['modelo']
        novos, raizes, erro = _biblioteca.inserir_preset(context, m['pasta'], m['arquivo'], m['tipo'], Vector((0, 0, 0)))
        if erro:
            raise ValueError(erro)
        modulos = [o for o in novos if _chapas.MARCA_CONJUNTO in o]
        if len(modulos) != 1 or raizes != modulos:
            raise ValueError('O modelo deve conter um unico modulo completo')
        novo = modulos[0]
        alvo = dict(item, nome=novo.name)
        _aplicar(context, alvo, s)
        costas = _paredes.ponto_das_costas(novo)
        _paredes.associar(novo, bpy.data.objects[s['parede']], costas, Vector(s['normal']), s['face'])
        novo[CHAVE_FIXA] = item['fixa']
        if antigo.parent is not None:
            matriz = novo.matrix_world.copy()
            novo.parent = antigo.parent
            novo.matrix_world = matriz
        janela, area, regiao = _paredes_edicao._janela_da_sessao()
        if area and area.spaces.active.local_view:
            for obj in novos:
                obj.local_view_set(area.spaces.active, True)
        context.view_layer.update()
        for obj in context.selected_objects:
            obj.select_set(False)
        novo.select_set(True)
        context.view_layer.objects.active = novo
    except Exception as erro:
        _paredes_edicao._limpar_tentativa(antes)
        for nome in selecao:
            obj = context.view_layer.objects.get(nome)
            if obj:
                obj.select_set(True)
        context.view_layer.objects.active = context.view_layer.objects.get(ativo)
        return str(erro)
    # O original so' sai depois de o substituto estar validado e associado.
    for obj in reversed(velhos):
        bpy.data.objects.remove(obj, do_unlink=True)
    for nome in colecoes:
        col = bpy.data.collections.get(nome)
        if col is not None:
            bpy.data.collections.remove(col)
    if comodo:
        _orcamento.definir_comodo(context.scene, [novo], comodo)
    if s['local_anterior']:
        s['membros_anteriores'] = [n for n in s['membros_anteriores'] if n not in nomes_velhos]
        s['membros_anteriores'].extend(o.name for o in novos)
    s.update(modelo=None, substituir='', escolhendo=False)
    _paredes_edicao._plano[0] = None
    atualizar(context)
    _paredes_edicao._redesenhar()
    return None


def planejar_redistribuicao(context):
    s = _paredes_edicao._sessao[0]
    itens = itens_da_face(context)
    ativo = selecionado(context, itens)
    escolhidos = [f for f in itens if bpy.data.objects[f['nome']].select_get()]
    if len(escolhidos) < 2:
        if ativo is None:
            return {'erro': 'Selecione um modulo da composicao'}
        escolhidos = [f for f in itens if abs(f['base'] - ativo['base']) < .002]
    if not escolhidos:
        return {'erro': 'Nenhum modulo para distribuir'}
    base = min(f['base'] for f in escolhidos)
    topo = max(f['base'] + f['altura'] for f in escolhidos)
    profundidade = max(f['profundidade'] for f in escolhidos)
    faixas = _intervalos_livres(context, s, base, topo - base, profundidade,
                               [f['nome'] for f in escolhidos])
    inicio, fim = min(f['inicio'] for f in escolhidos), max(f['fim'] for f in escolhidos)
    faixa = next(((a, b) for a, b in faixas if a <= inicio + .00005 and b >= fim - .00005), None)
    if faixa is None:
        return {'erro': 'Os modulos selecionados nao compartilham um vao livre'}
    esquerda, direita, espaco = (s[k] / 1000 for k in ('esquerda', 'direita', 'espacamento'))
    disponivel = faixa[1] - faixa[0] - esquerda - direita - espaco * (len(escolhidos) - 1)
    fixas = sum(f['largura'] for f in escolhidos if f['fixa'])
    livres = sum(not f['fixa'] for f in escolhidos)
    if not livres:
        return {'erro': 'Libere a largura de pelo menos um modulo'}
    largura = (disponivel - fixas) / livres
    if largura < .02:
        return {'erro': 'As larguras fixas e as folgas nao cabem no vao'}
    posicao, resultado = faixa[0] + esquerda, []
    for item in escolhidos:
        novo = dict(item, largura=item['largura'] if item['fixa'] else largura, inicio=posicao)
        novo['fim'] = posicao + novo['largura']
        resultado.append(novo)
        posicao = novo['fim'] + espaco
    return {'itens': resultado, 'faixa': faixa}


@bpy.app.handlers.persistent
def invalidar_interiores(cena, depsgraph):
    if _eventos._desfazendo[0] or _paredes_edicao._sessao[0] is None:
        return
    # Apenas nomes; extrair geometria no depsgraph ou no redraw torna undo inseguro.
    for atualizacao in depsgraph.updates:
        if atualizacao.is_updated_geometry:
            dado = atualizacao.id
            if isinstance(dado, bpy.types.Object):
                _sujos[0].add(('objeto', dado.name))
            elif isinstance(dado, bpy.types.Mesh):
                _sujos[0].add(('malha', dado.name))


def _arestas_avaliadas(obj, depsgraph):
    avaliado = obj.evaluated_get(depsgraph)
    malha = avaliado.to_mesh()
    bm = bmesh.new()
    try:
        bm.from_mesh(malha)
        bm.normal_update()
        mundo = avaliado.matrix_world
        # O BMesh nativo distingue quinas de triangulos coplanares; a copia
        # nunca e' escrita na Mesh do usuario.
        return tuple(tuple(mundo @ v.co) for e in bm.edges
                     if len(e.link_faces) != 2 or e.calc_face_angle(0) > .001
                     for v in e.verts)
    finally:
        bm.free()
        avaliado.to_mesh_clear()


def atualizar_interiores(context, itens):
    if (_eventos._desfazendo[0] or context.mode != 'OBJECT'
            or _eventos._ha_modal_ativo()):
        return
    janela, area, regiao = _paredes_edicao._janela_da_sessao()
    if area is None:
        return
    dep = context.evaluated_depsgraph_get()
    vivos = set()
    for item in itens:
        modulo = bpy.data.objects.get(item['nome'])
        if modulo is None:
            continue
        for obj in modulo.children_recursive:
            if (obj.type != 'MESH' or _chapas.MARCA_CHAPA not in obj
                    or _chapas.MARCA_FOLHA in obj or obj.get('eh_fundo_modulo')
                    or obj.get('eh_acessorio') or obj.get('eh_puxador')
                    or not obj.visible_get(viewport=area.spaces.active)
                    or obj.data.is_editmode):
                continue
            vivos.add(obj.name)
            assinatura = (obj.data.name, len(obj.data.vertices), len(obj.data.edges),
                          tuple(tuple(r) for r in obj.matrix_world))
            antigo = _interiores[0].get(obj.name)
            if (antigo is None or antigo['assinatura'] != assinatura
                    or ('objeto', obj.name) in _sujos[0] or ('malha', obj.data.name) in _sujos[0]):
                _interiores[0][obj.name] = dict(assinatura=assinatura, linhas=_arestas_avaliadas(obj, dep))
    _interiores[0] = {n: v for n, v in _interiores[0].items() if n in vivos}
    _sujos[0].clear()
    if _handler_interior[0] is None:
        _handler_interior[0] = bpy.types.SpaceView3D.draw_handler_add(desenhar_interiores, (), 'WINDOW', 'POST_VIEW')


def desenhar_interiores():
    context = bpy.context
    if (not _paredes_edicao.ativa(context) or context.mode != 'OBJECT' or context.area is None
            or context.area.as_pointer() != _paredes_edicao._sessao[0]['area']
            or _eventos._desfazendo[0] or _eventos._ha_modal_ativo()):
        return
    linhas = [p for dado in _interiores[0].values() for p in dado['linhas']]
    if not linhas:
        return
    tema = context.preferences.themes[0].view_3d
    cinza = (sum(tema.wire[:3]) + sum(tema.space.text[:3])) / 6
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    teste_anterior = gpu.state.depth_test_get()
    mascara_anterior = gpu.state.depth_mask_get()
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('GREATER')
    gpu.state.depth_mask_set(False)
    try:
        shader.bind()
        shader.uniform_float('color', (cinza, cinza, cinza, .4))
        batch_for_shader(shader, 'LINES', {'pos': linhas}).draw(shader)
    finally:
        gpu.state.depth_test_set(teste_anterior)
        gpu.state.depth_mask_set(mascara_anterior)
        gpu.state.blend_set('NONE')


def atualizar(context):
    if not _paredes_edicao.ativa(context):
        esquecer()
        return
    itens = itens_da_face(context)
    _resumo[0] = dict(itens=itens, ativo=selecionado(context, itens))
    atualizar_interiores(context, itens)


def esquecer():
    _resumo[0] = None
    _rotulos[0] = ()
    _edicao[0] = None
    _interiores[0].clear()
    _sujos[0].clear()
    if _handler_interior[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler_interior[0], 'WINDOW')
        _handler_interior[0] = None


def widgets(context, itens, x, topo, w):
    resumo = _resumo[0]
    if not resumo or not resumo['itens']:
        return topo
    ativo = selecionado(context, resumo['itens'])
    topo = _gaveta._titulo_secao(itens, x, topo, w, 'Composicao')
    if ativo:
        s0, s1, z0, z1 = _paredes_edicao._sessao[0]['regiao']['retangulo']
        valores = [('largura', 'A1', ativo['largura']), ('altura', 'A2', ativo['altura']),
                   ('profundidade', 'A3', ativo['profundidade']),
                   ('esquerda', 'Esquerda', ativo['inicio'] - s0),
                   ('direita', 'Direita', s1 - ativo['fim']),
                   ('instalacao', 'Instalacao', ativo['base'] - z0),
                   ('vao_esquerdo', 'E1', ativo['vao_esquerdo']),
                   ('vao_direito', 'E2', ativo['vao_direito'])]
        campos = [('%s: %s' % (rotulo, _opcoes._texto_medida(valor * 1000)),
                   ('medida', 'parede_modulo', nome, rotulo, valor * 1000))
                  for nome, rotulo, valor in valores]
        topo = _gaveta._campos_em_linhas(context, itens, x, topo, w, campos)
    for i, item in enumerate(resumo['itens']):
        titulo = 'M%d - %s' % (i + 1, _opcoes._texto_medida(item['largura'] * 1000))
        itens.append((x, topo - 20, w, 20, titulo, None))
        topo -= 24
        for j, (rotulo, valor) in enumerate((('Livre', False), ('Fixa', True))):
            itens.append((x + j * (w + 6) / 2, topo - 25, (w - 6) / 2, 25, rotulo,
                          ('escolha', CHAVE_FIXA, valor, item['fixa'] == valor, True, item['nome'])))
        topo -= 33
    for rotulo, op in (('Redistribuir composicao', 'object.cabinet_redistribuir_parede'),
                       ('Trocar modelo do modulo', 'object.cabinet_trocar_modelo_parede')):
        itens.append((x, topo - 28, w, 28, rotulo, ('operador', op)))
        topo -= 34
    return topo - 12


def estilo_cotas(context):
    """Linha do tema sobre halo opaco: legivel na parede e fora dela."""
    cores = context.preferences.themes[0].user_interface.wcol_regular
    return dict(linha=(*cores.text[:3], 1.0), halo=(*cores.inner[:3], 1.0),
                realce=_hud._cor_realce_hud(),
                tamanho=max(14, _opcoes._opcao('hud_tamanho_rotulo')))


def desenhar(context):
    resumo = _resumo[0]
    if not resumo or not _paredes_edicao.ativa(context):
        return
    s = _paredes_edicao._sessao[0]
    n, u, ponto = (Vector(s[k]) for k in ('normal', 'u', 'ponto'))
    escala = context.preferences.system.ui_scale
    estilo = estilo_cotas(context)
    tamanho = estilo['tamanho'] * escala
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    segmentos, realces, rotulos, textos = [], [], [], []
    ativo = selecionado(context, resumo['itens'])
    def tela(x, z):
        p = ponto + u * (x - ponto.dot(u)) + n * .002
        p.z = z
        return view3d_utils.location_3d_to_region_2d(context.region, context.region_data, p)
    def cota(a, b, item, prop, valor, numero, curto=False):
        if a is None or b is None or valor <= 1e-6 or ((b - a).length < 12 * escala and not curto):
            return
        linhas = realces if ativo == item else segmentos
        linhas.extend((a, b))
        direcao = (b - a).normalized()
        normal = Vector((-direcao.y, direcao.x))
        comprimento = min(7 * escala, (b - a).length / 3)
        for p, sinal in ((a, 1), (b, -1)):
            for lado in (-1, 1):
                linhas.extend((p, p + direcao * sinal * comprimento + normal * lado * 3 * escala))
        centro = (a + b) / 2
        edicao = _edicao[0]
        texto = (_gaveta_desenho._com_cursor(edicao['texto'], edicao['cursor'])
                 if edicao and edicao['objeto'] == item['nome'] and edicao['propriedade'] == prop
                 else _opcoes._texto_medida(valor * 1000))
        blf.size(0, tamanho)
        largura = blf.dimensions(0, texto)[0]
        x, y = centro.x - largura / 2, centro.y - tamanho / 2
        if abs(b.x - a.x) < abs(b.y - a.y):
            x = centro.x + 4 * escala
        textos.append((x, y, texto))
        rotulos.append((x - 5, y - 4, largura + 10, tamanho + 8, item['nome'], prop, valor * 1000))
    gpu.state.blend_set('ALPHA')
    try:
        for i, item in enumerate(resumo['itens']):
            a, b = tela(item['inicio'], item['base']), tela(item['fim'], item['base'])
            if a is None or b is None:
                continue
            # Cota real de largura, fora da caixa, como uma elevacao.
            desloc = Vector((0, -14 * escala))
            cota(a + desloc, b + desloc, item, 'largura', item['largura'], i)
            if ativo == item:
                topo = tela(item['fim'], item['base'] + item['altura'])
                base = tela(item['fim'], item['base'])
                cota(base + Vector((12 * escala, 0)), topo + Vector((12 * escala, 0)),
                     item, 'altura', item['altura'], i)
                inicio = tela(item['inicio'] - item['vao_esquerdo'], item['base'])
                cota(inicio + Vector((0, -34 * escala)), a + Vector((0, -34 * escala)),
                     item, 'vao_esquerdo', item['vao_esquerdo'], i, curto=True)
                fim = tela(item['fim'] + item['vao_direito'], item['base'])
                cota(b + Vector((0, -34 * escala)), fim + Vector((0, -34 * escala)),
                     item, 'vao_direito', item['vao_direito'], i, curto=True)
        for largura, cor, linhas in ((4 * escala, estilo['halo'], segmentos + realces),
                (2 * escala, estilo['linha'], segmentos), (2 * escala, estilo['realce'], realces)):
            if linhas:
                gpu.state.line_width_set(largura)
                shader.bind()
                shader.uniform_float('color', cor)
                batch_for_shader(shader, 'LINES', {'pos': linhas}).draw(shader)
        # O traco nunca passa sobre o numero nem sobre o cursor de edicao.
        for x, y, texto in textos:
            _hud._caixa_texto_hud(x, y, texto, tamanho, escala)
    finally:
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')
    _rotulos[0] = tuple(rotulos)


def cota_sob(x, y):
    return next((r for r in reversed(_rotulos[0]) if r[0] <= x <= r[0] + r[2]
                 and r[1] <= y <= r[1] + r[3]), None)


class OBJECT_OT_redistribuir_parede(Operator):
    bl_idname = 'object.cabinet_redistribuir_parede'
    bl_label = 'Redistribuir composicao'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _paredes_edicao.ativa(context):
            return {'CANCELLED'}
        plano = planejar_redistribuicao(context)
        erro = plano.get('erro') or _transacao(context, plano['itens'])
        if erro:
            self.report({'WARNING'}, erro)
        return {'CANCELLED'} if erro else {'FINISHED'}


class OBJECT_OT_trocar_modelo_parede(Operator):
    bl_idname = 'object.cabinet_trocar_modelo_parede'
    bl_label = 'Trocar modelo do modulo'

    def execute(self, context):
        item = selecionado(context)
        if item is None:
            self.report({'WARNING'}, 'Selecione um modulo associado a esta parede')
            return {'CANCELLED'}
        s = _paredes_edicao._sessao[0]
        s['substituir'] = item['nome']
        s['modelo'] = None
        _paredes_edicao._redesenhar()
        return {'FINISHED'}


class OBJECT_OT_editar_cota_parede(Operator):
    bl_idname = 'object.cabinet_editar_cota_parede'
    bl_label = 'Editar cota do modulo'
    bl_options = {'REGISTER', 'UNDO'}
    objeto: StringProperty(options={'SKIP_SAVE'})
    propriedade: StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        item = next((f for f in itens_da_face(context) if f['nome'] == self.objeto), None)
        if item is None:
            return {'CANCELLED'}
        valor = (item['inicio'] - _paredes_edicao._sessao[0]['regiao']['retangulo'][0]
                 if self.propriedade == 'esquerda' else item[self.propriedade])
        texto = _opcoes._numero_na_unidade(valor * 1000)
        _edicao[0] = dict(objeto=self.objeto, propriedade=self.propriedade, texto=texto,
                          cursor=len(texto), selecionado=True)
        context.window_manager.modal_handler_add(self)
        _paredes_edicao._redesenhar()
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        _edicao[0] = None
        _paredes_edicao._redesenhar()

    def modal(self, context, event):
        try:
            return self._modal(context, event)
        except Exception:
            self.cancel(context)
            raise

    def _modal(self, context, event):
        estado = _edicao[0]
        if not _paredes_edicao.ativa(context) or estado is None:
            self.cancel(context)
            return {'CANCELLED'}
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cancel(context)
            return {'CANCELLED'}
        if event.type in {'RET', 'NUMPAD_ENTER', 'LEFTMOUSE'}:
            try:
                valor = _gaveta_desenho._ler_medida_digitada(estado['texto']) * 1000
                erro = editar_modulo(context, self.objeto, self.propriedade, valor)
            except (ValueError, TypeError) as exc:
                erro = str(exc)
            if erro:
                self.report({'WARNING'}, erro)
                return {'RUNNING_MODAL'}
            self.cancel(context)
            return {'FINISHED'}
        entrada = context.window_manager.clipboard if event.ctrl and event.type == 'V' else event.unicode or ''
        _gaveta_desenho._tecla_no_texto(estado, event.type, entrada, event.ctrl)
        _paredes_edicao._redesenhar()
        return {'RUNNING_MODAL'}
