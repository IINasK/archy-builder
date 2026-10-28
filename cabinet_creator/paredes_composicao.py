"""Composicao existente na parede: cotas, larguras fixas e redistribuicao.

O timer publica numeros para UI/desenho. Mutacoes pertencem aos operadores;
resize e cancelamento reutilizam os contratos do modulo e da HUD.
"""
import math
import time
import bpy
import bmesh
import blf
import gpu
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator
from mathutils import Vector
from mathutils.geometry import intersect_line_plane
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader

_paredes_edicao = _paredes = _modulos = _chapas = _hud = None
_gaveta = _gaveta_desenho = _opcoes = _biblioteca = None
_eventos = _orcamento = _hud_volume = None

CHAVE_FIXA = 'parede_largura_fixa'
_resumo = [None]
_rotulos = [()]
_edicao = [None]
_interiores = [{}]
_sujos = [set()]
_handler_interior = [None]
# Caixa LOCAL de cada modulo do resumo, por nome: no arraste so' a matriz
# muda, e as cotas seguem sem reler malhas.
_caixas = [{}]
# Modulos que o G/R/S nativo moveu na vista da parede: recebem o ima ao
# soltar (`encaixar_movidos`). So' nomes.
_movidos = [set()]
IMA_PX = 12     # como o SNAP_PX do arraste direito na parede
LADO_PX = 24    # G/arraste a ate' isto de uma lateral pega AQUELA lateral
QUINA_PX = 16   # mouse a ate' isto de uma quina-alvo: gruda nela, sem Alt
# Mover na parede em andamento, so' para o desenho: {'modulo', 'lado',
# 'quina' (x, z) ou None, 'linhas' [('x'|'z', valor)]}. So' nomes e numeros.
_movendo = [None]
# Quina de modulo sob o mouse na vista da parede (pedido do usuario: o
# circulo do snap de quina aparece so' de passar o mouse perto dela, como
# o do snap de vertice): (nome do modulo, (x, z)) ou None.
_quina_hover = [None]
RAIO_QUINA_PX = 7

# Guias de altura (pedido do usuario, como no Promob): linhas de referencia
# do piso da face, SO' na vista da parede. Padrao de cozinha planejada,
# editavel por projeto (ID props da cena).
CHAVE_GUIAS = 'parede_guias'
CHAVE_GUIAS_MODO = 'parede_guias_modo'
MODOS_GUIAS = (('OCULTAS', 'Ocultas'), ('VISIVEIS', 'Visiveis'), ('SNAP', 'Com snap'))
ALVO_GUIAS = 'paredes_guias'
MARCA_OBJETO_GUIAS = 'cabinet_parede_guias_2d'
GUIAS_PADRAO = (('Rodape', 150.0), ('Bancada', 900.0), ('Peitoril', 1100.0),
                ('Base do aereo', 1500.0), ('Altura maxima', 2150.0))
_rotulos_guias = [()]
ALTURA_ROTULO_GUIA_M = 0.07     # altura do texto na parede, em escala
TAMANHO_MINIMO_GUIA_PX = 7      # abaixo disso o rotulo some (ilegivel)
PISCA_CURSOR_S = 0.5            # meio periodo do cursor de digitacao
# Guias discretas (pedido do usuario): linha PONTILHADA -- tracos curtos da
# propria malha, entao o snap nativo de aresta continua pegando a altura --
# e rotulo em texto cinza; a caixa preta so' com o mouse em cima.
TRACO_GUIA_M = 0.01
PASSO_GUIA_M = 0.04
COR_TEXTO_GUIA = (0.5, 0.5, 0.5, 1.0)   # legivel na parede clara e na grade escura
_guia_hover = [None]            # 'guia_<i>' sob o mouse, ou None


def guias(cena):
    dados = cena.get(CHAVE_GUIAS)
    if not dados:
        return [dict(nome=nome, altura_mm=altura) for nome, altura in GUIAS_PADRAO]
    return [dict(nome=str(g['nome']), altura_mm=float(g['altura_mm'])) for g in dados]


def modo_guias(cena):
    modo = cena.get(CHAVE_GUIAS_MODO, 'SNAP')
    return modo if modo in dict(MODOS_GUIAS) else 'SNAP'


def editar_guia(context, indice, valor_mm):
    s = _paredes_edicao._sessao[0]
    lista = guias(context.scene)
    if s is None:
        return 'A edicao da parede terminou'
    if not 0 <= indice < len(lista):
        return 'Guia inexistente'
    s0, s1, z0, z1 = s['regiao']['retangulo']
    if not math.isfinite(valor_mm) or not 0 < valor_mm <= (z1 - z0) * 1000 + 1e-6:
        return 'A guia deve ficar dentro da altura da parede'
    lista[indice]['altura_mm'] = float(valor_mm)
    context.scene[CHAVE_GUIAS] = lista
    sincronizar_guias(context)
    return None


def definir_modo_guias(context, modo):
    if modo not in dict(MODOS_GUIAS):
        return 'Modo de guia desconhecido'
    context.scene[CHAVE_GUIAS_MODO] = modo
    sincronizar_guias(context)
    return None


def remover_objeto_guias():
    for obj in [o for o in bpy.data.objects if MARCA_OBJETO_GUIAS in o]:
        malha = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if malha is not None and malha.users == 0:
            bpy.data.meshes.remove(malha)


def sincronizar_guias(context):
    """Objeto temporario so' de ARESTAS na frente da parede: alvo do snap
    NATIVO de aresta. Sem snap nas guias, ele sai do snap pelo filtro
    nativo de nao-selecionaveis; ocultas, ele nem existe."""
    s = _paredes_edicao._sessao[0]
    cena = context.scene
    if s is None or modo_guias(cena) == 'OCULTAS':
        remover_objeto_guias()
    else:
        n, u, ponto = (Vector(s[k]) for k in ('normal', 'u', 'ponto'))
        s0, s1, z0, z1 = s['regiao']['retangulo']
        vertices, arestas = [], []
        # Tracos de s0 em diante e um ultimo rente a s1: a guia marca as
        # duas pontas da face.
        inicios = [s0 + k * PASSO_GUIA_M for k in range(int((s1 - s0) / PASSO_GUIA_M) + 1)
                   if s0 + k * PASSO_GUIA_M < s1 - 1e-9]
        if inicios and inicios[-1] + TRACO_GUIA_M < s1 - 1e-9:
            inicios.append(max(s0, s1 - TRACO_GUIA_M))
        for guia in guias(cena):
            for inicio in inicios:
                for x in (inicio, min(inicio + TRACO_GUIA_M, s1)):
                    p = ponto + u * (x - ponto.dot(u)) + n * .001
                    p.z = z0 + guia['altura_mm'] / 1000
                    vertices.append(p)
                arestas.append((len(vertices) - 2, len(vertices) - 1))
        obj = next((o for o in bpy.data.objects if MARCA_OBJETO_GUIAS in o), None)
        if obj is None:
            obj = bpy.data.objects.new('Guias da parede', bpy.data.meshes.new('Guias da parede'))
            obj[MARCA_OBJETO_GUIAS] = 1
            # Clique nativo pegaria a aresta solta; o snap continua vendo.
            obj.hide_select = True
            obj.hide_render = True
            cena.collection.objects.link(obj)
        obj.data.clear_geometry()
        obj.data.from_pydata(vertices, arestas, [])
        obj.data.update()
        _janela, area, _regiao = _paredes_edicao._janela_da_sessao()
        if area is not None and area.type == 'VIEW_3D' and area.spaces.active.local_view:
            obj.local_view_set(area.spaces.active, True)
    if s is not None:
        com_guias = modo_guias(cena) == 'SNAP'
        ajustes = cena.tool_settings
        ajustes.snap_elements = {'VERTEX', 'EDGE'} if com_guias else {'VERTEX'}
        ajustes.use_snap_selectable = not com_guias
    _paredes_edicao._redesenhar()


def desenhar_guias(context):
    """Rotulo "altura - nome" na ponta esquerda, sobre a linha; clicar
    digita. A linha e' a aresta nativa do objeto das guias."""
    s = _paredes_edicao._sessao[0]
    _rotulos_guias[0] = ()
    if modo_guias(context.scene) == 'OCULTAS':
        return
    n, u, ponto = (Vector(s[k]) for k in ('normal', 'u', 'ponto'))
    s0, s1, z0, z1 = s['regiao']['retangulo']
    tamanho_maximo = estilo_cotas(context)['tamanho'] * context.preferences.system.ui_scale
    # O rotulo tem tamanho FISICO na parede (pedido do usuario): diminui
    # com o zoom, nunca passa do da cota e some quando ficaria ilegivel.
    base = ponto + u * (s0 - ponto.dot(u)) + n * .002
    base.z = z0
    a, b = (view3d_utils.location_3d_to_region_2d(context.region, context.region_data, p)
            for p in (base, base + Vector((0, 0, 1))))
    tamanho = min(tamanho_maximo, ALTURA_ROTULO_GUIA_M * (b - a).length if a and b else 0)
    if tamanho < TAMANHO_MINIMO_GUIA_PX:
        return
    escala = context.preferences.system.ui_scale * tamanho / tamanho_maximo
    edicao = _edicao[0]
    rotulos = []
    try:
        for i, guia in enumerate(guias(context.scene)):
            p = base.copy()
            p.z = z0 + guia['altura_mm'] / 1000
            tela = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, p)
            if tela is None:
                continue
            prop = 'guia_%d' % i
            editando = edicao and edicao['objeto'] == '' and edicao['propriedade'] == prop
            numero = edicao['texto'] if editando else _opcoes._texto_medida(guia['altura_mm'])
            texto = '%s - %s' % (numero, guia['nome'])
            blf.size(0, tamanho)
            largura = blf.dimensions(0, texto)[0]
            x, y = tela.x + 8 * escala, tela.y + 4 * escala
            if editando or _guia_hover[0] == prop:
                caixa_editavel(x, y, texto, edicao if editando else None, tamanho, escala)
            else:
                texto_discreto(x, y, texto, tamanho)
            rotulos.append((x - 5, y - 4, largura + 10, tamanho + 8, '', prop, guia['altura_mm']))
    finally:
        gpu.state.blend_set('NONE')
        gpu.state.line_width_set(1.0)
    _rotulos_guias[0] = tuple(rotulos)


def texto_discreto(x, y, texto, tamanho):
    blf.size(0, tamanho)
    blf.position(0, x, y, 0)
    blf.color(0, *COR_TEXTO_GUIA)
    blf.draw(0, texto)


def atualizar_guia_hover(x, y):
    """Guia cujo rotulo esta' sob o mouse (x, y da regiao), ou None se
    fora; redesenha so' quando muda."""
    r = next((r for r in _rotulos_guias[0]
              if r[0] <= x <= r[0] + r[2] and r[1] <= y <= r[1] + r[3]), None) if x is not None else None
    prop = r[5] if r else None
    if prop != _guia_hover[0]:
        _guia_hover[0] = prop
        _paredes_edicao._redesenhar()


def cursor_aceso(agora=None):
    """Pisca como o cursor de texto: meio periodo aceso, meio apagado."""
    return int((time.monotonic() if agora is None else agora) / PISCA_CURSOR_S) % 2 == 0


def caixa_editavel(x, y, texto, edicao, tamanho, escala):
    """Caixa preta da HUD. Em edicao, o texto digitado (inicio de `texto`)
    ganha realce enquanto estiver todo selecionado, e uma barra PISCA na
    posicao do cursor: a referencia de onde a tecla entra."""
    _hud._caixa_texto_hud(x, y, texto, tamanho, escala)
    if edicao is None:
        return
    blf.size(0, tamanho)
    altura = blf.dimensions(0, '0')[1]
    digitado = edicao['texto']
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    shader.bind()
    if edicao.get('selecionado') and digitado:
        fim = x + blf.dimensions(0, digitado)[0]
        shader.uniform_float('color', (*_hud._cor_realce_hud()[:3], .45))
        batch_for_shader(shader, 'TRIS', {'pos': [
            (x - 1, y - 2), (fim + 1, y - 2), (fim + 1, y + altura + 2),
            (x - 1, y - 2), (fim + 1, y + altura + 2), (x - 1, y + altura + 2)]}).draw(shader)
    if cursor_aceso():
        cx = x + blf.dimensions(0, digitado[:min(edicao['cursor'], len(digitado))])[0]
        gpu.state.line_width_set(max(1.0, 1.5 * escala))
        shader.uniform_float('color', (1.0, 1.0, 1.0, 1.0))
        batch_for_shader(shader, 'LINES', {'pos': [(cx, y - 3), (cx, y + altura + 3)]}).draw(shader)
        gpu.state.line_width_set(1.0)


def parede(obj):
    """Parede assumida explicitamente ou que ja' tem modulos associados."""
    if obj is None:
        return False
    s = _paredes_edicao._sessao[0]
    ultima = _paredes_edicao._ultima_face[0]
    return (_paredes.CHAVE_UID_PAREDE in obj or
            bool(s and obj.name == s['parede']) or
            bool(ultima and ultima[0] == obj.name))


def ficha(obj, s, caixa=None):
    caixa = caixa or _paredes.caixa_do_modulo(obj)
    if caixa is None:
        return None
    lo, hi = caixa
    escala = _paredes.escala_no_referencial(obj)
    largura, altura, prof = ((hi[i] - lo[i]) * escala[i] for i in (0, 2, 1))
    costas = _paredes.ponto_das_costas(obj, caixa)
    inicio = costas.dot(Vector(s['u'])) - largura / 2
    afastamento = (costas - Vector(s['ponto'])).dot(Vector(s['normal']))
    return dict(nome=obj.name, inicio=inicio, fim=inicio + largura, base=costas.z,
                largura=largura, altura=altura, profundidade=prof,
                afastamento=max(0.0, afastamento),
                fixa=bool(obj.get(CHAVE_FIXA, False)))


def itens_da_face(context, caixas=None):
    """`caixas` (dict), se dado, recebe a caixa local de cada modulo."""
    s = _paredes_edicao._sessao[0]
    if not _paredes_edicao.ativa(context):
        return []
    obj = bpy.data.objects.get(s['parede'])
    if obj is None:
        return []
    encontrados = _paredes_edicao.associados(obj, Vector(s['ponto']), Vector(s['normal']),
                                             context.scene.objects, s['regiao'])
    if caixas is None:
        caixas = {}
    for o in encontrados:
        caixas[o.name] = _paredes.caixa_do_modulo(o)
    itens = sorted(filter(None, (ficha(o, s, caixas[o.name]) for o in encontrados)),
                   key=lambda f: f['inicio'])
    return _medir_vaos(itens, s)


def _medir_vaos(itens, s):
    """Cotas do Promob: Anterior/Posterior (`vao_esquerdo`/`vao_direito`)
    ate' o vizinho na mesma altura ou a ponta da face; Inferior/Superior
    ate' o modulo embaixo/em cima na mesma faixa, ou o piso/teto da face."""
    s0, s1, z0, z1 = s['regiao']['retangulo']
    for item in itens:
        topo = item['base'] + item['altura']
        vizinhos = [f for f in itens if f['nome'] != item['nome'] and
                    f['base'] < topo - 1e-6 and f['base'] + f['altura'] > item['base'] + 1e-6]
        item['vao_esquerdo'] = item['inicio'] - max([s0] + [f['fim'] for f in vizinhos if f['fim'] <= item['inicio'] + 1e-6])
        item['vao_direito'] = min([s1] + [f['inicio'] for f in vizinhos if f['inicio'] >= item['fim'] - 1e-6]) - item['fim']
        coluna = [f for f in itens if f['nome'] != item['nome'] and
                  f['inicio'] < item['fim'] - 1e-6 and f['fim'] > item['inicio'] + 1e-6]
        item['cota_inferior'] = item['base'] - max([z0] + [f['base'] + f['altura'] for f in coluna
                                                           if f['base'] + f['altura'] <= item['base'] + 1e-6])
        item['cota_superior'] = min([z1] + [f['base'] for f in coluna if f['base'] >= topo - 1e-6]) - topo
    return itens


def selecionado(context, itens=None):
    obj = context.object
    if obj is None or not obj.select_get():
        return None
    modulo = _paredes.modulo_de(obj)
    if not _paredes_edicao.modulo_editavel(modulo):
        return None
    return next((f for f in (itens if itens is not None else itens_da_face(context))
                 if modulo and f['nome'] == modulo.name), None)


def _intervalos_livres(context, s, base, altura, prof, excluir=()):
    return _paredes_edicao.faixas_livres(context, s, base, base + altura, prof, excluir)


def _validar_encaixe(context, s, item, excluir=()):
    if min(item[k] for k in ('largura', 'altura', 'profundidade')) < .02:
        return 'O modulo deve ter dimensoes de pelo menos 20 mm'
    # Afastado da parede, o modulo ocupa a profundidade a partir da folga.
    faixas = _intervalos_livres(context, s, item['base'], item['altura'],
                                item['profundidade'] + item.get('afastamento', 0.0), excluir)
    if not any(item['inicio'] >= a - .00005 and item['fim'] <= b + .00005 for a, b in faixas):
        return 'O modulo nao cabe neste vao sem ultrapassar o limite ou outro objeto'
    return None


def _aplicar(context, item, s):
    obj = bpy.data.objects[item['nome']]
    atuais = ficha(obj, s)
    alvo = _paredes.medidas_na_parede(obj, tuple(
        item[k] * 1000 for k in ('largura', 'altura', 'profundidade')))
    if any(abs(item[k] - atuais[k]) > 1e-6 for k in ('largura', 'altura', 'profundidade')):
        _modulos.redimensionar_orientado(obj, alvo)
    u, n, ponto = (Vector(s[k]) for k in ('u', 'normal', 'ponto'))
    costas = ponto + u * (item['inicio'] + item['largura'] / 2 - ponto.dot(u))
    costas.z = item['base']
    if 'afastamento' in item:
        _paredes.definir_afastamento(obj, item['afastamento'])
    _paredes.colocar_na_parede(obj, bpy.data.objects[s['parede']], costas, n)
    context.view_layer.update()
    real = ficha(obj, s)
    if any(abs(real[k] - item[k]) > .00005 for k in ('largura', 'altura', 'profundidade', 'inicio', 'base')
           + (('afastamento',) if 'afastamento' in item else ())):
        raise ValueError('As dimensoes pedidas nao sao compativeis com os encaixes do modelo')


def _transacao(context, itens):
    if any(not _paredes_edicao.modulo_editavel(bpy.data.objects.get(item['nome'])) for item in itens):
        return 'Selecione um modulo editavel'
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
                for k in _paredes.CHAVES_ASSOCIACAO:
                    if k in valores:
                        obj[k] = valores[k]
                    elif k in obj:
                        del obj[k]
        return str(erro)
    finally:
        # Medida pedida no campo nao recebe ima, mesmo vinda de um modal.
        _movidos[0] = set()
        _paredes._conferidos.clear()
        _paredes_edicao._plano[0] = None
        atualizar(context)
        _paredes_edicao._redesenhar()
    return None


def editar_modulo(context, nome, propriedade, valor_mm):
    if not _paredes_edicao.ativa(context):
        return 'Entre na edicao da parede'
    obj = _paredes.modulo_de(bpy.data.objects.get(nome))
    if not _paredes_edicao.modulo_editavel(obj):
        return 'Selecione um modulo editavel'
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
    elif propriedade == 'cota_inferior':
        item['base'] = item['base'] - item['cota_inferior'] + valor
    elif propriedade == 'cota_superior':
        item['base'] = item['base'] + item['cota_superior'] - valor
    elif propriedade == 'afastamento':
        item['afastamento'] = valor
    else:
        return 'Cota de modulo desconhecida'
    item['fim'] = item['inicio'] + item['largura']
    if (propriedade in ('cota_inferior', 'cota_superior') and
            (item['base'] < z0 - 1e-6 or item['base'] + item['altura'] > z1 + 1e-6)):
        return 'O modulo deve ficar entre o piso e o teto da parede'
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
    caixas = {}
    itens = itens_da_face(context, caixas)
    _caixas[0] = caixas
    _resumo[0] = dict(itens=itens, ativo=selecionado(context, itens))
    atualizar_interiores(context, itens)


@bpy.app.handlers.persistent
def acompanhar_arraste(cena, depsgraph):
    """G nativo: as cotas acompanham o movel a cada passo, nao so' no
    tique de 0,2 s. So' numeros (caixa guardada + matriz atual); o timer
    continua dono da lista de modulos, dos interiores e das caixas."""
    resumo, s = _resumo[0], _paredes_edicao._sessao[0]
    if _eventos._desfazendo[0] or s is None or not resumo:
        return
    nomes = {f['nome'] for f in resumo['itens']}
    movidos = {a.id.name for a in depsgraph.updates
               if a.is_updated_transform and isinstance(a.id, bpy.types.Object)
               and a.id.name in nomes}
    editado = modulo_em_edicao()
    if editado in nomes and depsgraph.updates:
        # Resize pela HUD muda a caixa, nao so' a matriz: a largura e a
        # altura em edicao acompanham o mouse.
        obj = bpy.data.objects.get(editado)
        caixa = _paredes.caixa_do_modulo(obj) if obj is not None else None
        if caixa is not None:
            _caixas[0][editado] = caixa
            movidos.add(editado)
    if not movidos:
        return
    if _eventos._transformando():
        # So' o gesto a' mao (G/R/S nativo) recebe o ima ao soltar; medida
        # digitada, distribuicao e insercao ficam exatamente como pedidas.
        # O ponto da face (translate do cursor) redimensiona: nada de ima.
        _movidos[0] |= movidos - {editado}
    itens = []
    for item in resumo['itens']:
        obj = bpy.data.objects.get(item['nome'])
        caixa = _caixas[0].get(item['nome'])
        novo = (ficha(obj, s, caixa) if item['nome'] in movidos
                and obj is not None and caixa is not None else None)
        itens.append(novo or item)
    resumo['itens'] = _medir_vaos(sorted(itens, key=lambda f: f['inicio']), s)
    _paredes_edicao._redesenhar()


def _alvos_do_ima(s, itens, nome, cena):
    """Bordas a que a caixa do modulo gruda, NO PLANO da parede: pontas,
    piso e teto da face, bordas dos vizinhos e as guias com snap."""
    s0, s1, z0, z1 = s['regiao']['retangulo']
    xs, zs = [s0, s1], [z0, z1]
    for f in itens:
        if f['nome'] != nome:
            xs += [f['inicio'], f['fim']]
            zs += [f['base'], f['base'] + f['altura']]
    # 'Visiveis' so' orientam; quem gruda e' o modo 'Com snap'.
    if modo_guias(cena) == 'SNAP':
        zs += [z0 + g['altura_mm'] / 1000 for g in guias(cena)]
    return xs, zs


def _quinas_do_ima(s, itens, nome):
    """Quinas (x, z) dos vizinhos e da face: alvos do Alt."""
    s0, s1, z0, z1 = s['regiao']['retangulo']
    caixas = [(s0, s1, z0, z1)] + [(f['inicio'], f['fim'], f['base'], f['base'] + f['altura'])
                                   for f in itens if f['nome'] != nome]
    return [(x, z) for a, b, c, d in caixas for x in (a, b) for z in (c, d)]


def _mais_perto(bordas, alvos, tolerancia):
    """(deslocamento, alvo) da borda ao alvo mais perto, ou (0, None)."""
    melhor = min(((c - p, c) for c in alvos for p in bordas),
                 key=lambda d: abs(d[0]), default=None)
    if melhor is None or abs(melhor[0]) > tolerancia:
        return 0.0, None
    return melhor


def _grudar(a, b, alvos, tolerancia):
    """Deslocamento que leva a borda `a` ou `b` ao alvo mais perto, ou 0."""
    return _mais_perto((a, b), alvos, tolerancia)[0]


def quinas_da_ficha(f):
    """{(i, j): (x, z)} das 4 quinas da caixa no plano: i 0/1 = esquerda/
    direita, j 0/1 = base/topo."""
    return {(i, j): (f['inicio'] + i * f['largura'], f['base'] + j * f['altura'])
            for i in (0, 1) for j in (0, 1)}


def quina_sob(f, x, z, tolerancia):
    """(i, j) da quina da caixa a ate' `tolerancia` de (x, z), ou None."""
    perto = min(quinas_da_ficha(f).items(), key=lambda q: math.dist(q[1], (x, z)))
    return perto[0] if math.dist(perto[1], (x, z)) <= tolerancia else None


def _no_plano_da_sessao(event, regiao, rv3d):
    """(x, z) do mouse no plano da parede, ou None."""
    s = _paredes_edicao._sessao[0]
    xy = (event.mouse_x - regiao.x, event.mouse_y - regiao.y)
    origem = view3d_utils.region_2d_to_origin_3d(regiao, rv3d, xy)
    direcao = view3d_utils.region_2d_to_vector_3d(regiao, rv3d, xy)
    p = intersect_line_plane(origem, origem + direcao, Vector(s['ponto']), Vector(s['normal']))
    return None if p is None else (p.dot(Vector(s['u'])), p.z)


def atualizar_quina_hover(event, regiao, rv3d):
    """O observador da parede chama no MOUSEMOVE: acende a quina de modulo
    perto do mouse (so' contas nas fichas do resumo, nada de malha)."""
    resumo, s = _resumo[0], _paredes_edicao._sessao[0]
    achada = None
    mouse = _no_plano_da_sessao(event, regiao, rv3d) if resumo and s else None
    px = _paredes._px_por_metro(regiao, rv3d, Vector(s['ponto']), Vector(s['u'])) if mouse else None
    if px:
        candidatas = [(math.dist(xz, mouse), f['nome'], xz) for f in resumo['itens']
                      if _paredes_edicao.modulo_editavel(bpy.data.objects.get(f['nome']))
                      for xz in quinas_da_ficha(f).values()]
        dist, nome, xz = min(candidatas, default=(math.inf, None, None))
        if dist <= QUINA_PX / px:
            achada = (nome, tuple(xz))
    if achada != _quina_hover[0]:
        _quina_hover[0] = achada
        _paredes_edicao._redesenhar()


def lado_sob(f, x, z, tolerancia):
    """A lateral da caixa (`ficha`) a ate' `tolerancia` de (x, z) no plano
    da parede, ou None. Frente e fundo nao contam: na vista de frente
    sobram esquerda, direita, base e topo."""
    topo = f['base'] + f['altura']
    candidatos = []
    if f['base'] - tolerancia <= z <= topo + tolerancia:
        candidatos += [(abs(x - f['inicio']), 'esquerda'), (abs(x - f['fim']), 'direita')]
    if f['inicio'] - tolerancia <= x <= f['fim'] + tolerancia:
        candidatos += [(abs(z - f['base']), 'base'), (abs(z - topo), 'topo')]
    distancia, lado = min(candidatos, default=(None, None))
    return lado if distancia is not None and distancia <= tolerancia else None


def posicao_com_ima(f, inicio, base, alvos, lado, tolerancia, quinas=(), mouse=None,
                    laterais=True, tolerancia_quina=None, quina=None):
    """(inicio, base, linhas) do modulo depois do ima 2D.

    A quina-alvo (`quinas`) a ate' `tolerancia_quina` do `mouse` recebe a
    quina mais perto da caixa, como o snap de vertice -- mas no plano,
    entao a quina da frente nunca cai na de tras de outro movel. Sem
    quina perto e com `laterais` (o Alt), `lado` gruda o LADO INTEIRO
    (pedido do usuario: nao a quina) e deixa o outro eixo livre; None
    gruda a borda mais perto de cada eixo. `linhas` sao os alvos usados,
    para o desenho."""
    largura, altura = f['largura'], f['altura']
    if tolerancia_quina is None:
        tolerancia_quina = tolerancia
    if quina is not None:
        # quina PEGA (o circulo aceso no G/arraste): e' ela que gruda, na
        # quina-alvo mais perto DELA, e as laterais dela com o Alt
        fonte = (inicio + quina[0] * largura, base + quina[1] * altura)
        alvo = min(quinas, key=lambda q: math.dist(q, fonte), default=None)
        if alvo is not None and math.dist(alvo, fonte) <= tolerancia_quina:
            return (inicio + alvo[0] - fonte[0], base + alvo[1] - fonte[1],
                    [('x', alvo[0]), ('z', alvo[1])])
    else:
        alvo = min(quinas, key=lambda q: math.dist(q, mouse), default=None)
        if alvo is not None and math.dist(alvo, mouse) <= tolerancia_quina:
            qx, qz = min(((x, z) for x in (inicio, inicio + largura) for z in (base, base + altura)),
                         key=lambda q: math.dist(q, alvo))
            return inicio + alvo[0] - qx, base + alvo[1] - qz, [('x', alvo[0]), ('z', alvo[1])]
    if not laterais:
        return inicio, base, []
    xs, zs = alvos
    linhas = []
    if quina is not None:
        lado = None
    if lado not in ('base', 'topo'):
        bordas = {'esquerda': (inicio,), 'direita': (inicio + largura,)}.get(
            lado, (inicio + quina[0] * largura,) if quina else (inicio, inicio + largura))
        dx, alvo = _mais_perto(bordas, xs, tolerancia)
        inicio += dx
        if alvo is not None:
            linhas.append(('x', alvo))
    if lado not in ('esquerda', 'direita'):
        bordas = {'base': (base,), 'topo': (base + altura,)}.get(
            lado, (base + quina[1] * altura,) if quina else (base, base + altura))
        dz, alvo = _mais_perto(bordas, zs, tolerancia)
        base += dz
        if alvo is not None:
            linhas.append(('z', alvo))
    return inicio, base, linhas


def encaixar_movidos(context):
    """Ao soltar o G (timer, sem modal): ima 2D e limite da face.

    So' no plano da parede: na vista de frente nao se ve profundidade, e
    o snap 3D grudava a quina da frente na de tras de outro movel (ou num
    vertice interno, como o do fundo recuado, deixando fresta). Aqui as
    bordas da CAIXA do modulo grudam nas dos vizinhos, da face e das
    guias a ate' IMA_PX, e o modulo volta para dentro da face."""
    s = _paredes_edicao._sessao[0]
    if s is None or not _movidos[0] or _eventos._ha_modal_ativo():
        return False
    nomes, _movidos[0] = _movidos[0], set()
    parede = bpy.data.objects.get(s['parede'])
    if parede is None:
        return False
    n, u, ponto = (Vector(s[k]) for k in ('normal', 'u', 'ponto'))
    s0, s1, z0, z1 = s['regiao']['retangulo']
    _janela, area, regiao = _paredes_edicao._janela_da_sessao()
    px = (_paredes._px_por_metro(regiao, area.spaces.active.region_3d, ponto, u)
          if regiao is not None else None)
    tolerancia = IMA_PX / px if px else 0.0
    itens = itens_da_face(context)
    mudou = False
    for nome in nomes:
        obj = bpy.data.objects.get(nome)
        if obj is None or not _paredes_edicao.associados(parede, ponto, n, [obj]):
            continue
        f = ficha(obj, s)
        if f is None:
            continue
        xs, zs = _alvos_do_ima(s, itens, nome, context.scene)
        inicio = f['inicio'] + _grudar(f['inicio'], f['fim'], xs, tolerancia)
        base = f['base'] + _grudar(f['base'], f['base'] + f['altura'], zs, tolerancia)
        # Associado, o modulo nao sai da face (pedido do usuario).
        inicio = max(s0, min(inicio, s1 - f['largura'])) if f['largura'] <= s1 - s0 else s0
        base = max(z0, min(base, z1 - f['altura'])) if f['altura'] <= z1 - z0 else z0
        if abs(inicio - f['inicio']) < 1e-7 and abs(base - f['base']) < 1e-7:
            continue
        costas = ponto + u * (inicio + f['largura'] / 2 - ponto.dot(u))
        costas.z = base
        _paredes.colocar_na_parede(obj, parede, costas, n)
        _paredes._conferidos.pop(nome, None)
        mudou = True
    if mudou:
        context.view_layer.update()
        atualizar(context)
        _paredes_edicao._redesenhar()
    return mudou


def modulo_em_edicao():
    """Nome do modulo cuja geometria a HUD edita agora (ponto da face ou
    seta da quina), ou None: a 2a etapa das cotas."""
    nativo = _hud_volume._estado[0]
    if nativo is not None:
        return nativo['objeto']
    edicao = _hud._edicao_hud[0]
    obj = edicao['alvo'].get('objeto') if edicao else None
    try:
        return obj.name if obj is not None else None
    except ReferenceError:
        return None


def digitacao_hud():
    """(propriedade, estado) da medida que se digita apos clicar na bolinha
    da borda, ou (None, None). O texto entra NO numero da cota verde dela:
    a caixa da HUD ao lado sobrepunha o rotulo (print do usuario)."""
    estado = _hud._edicao_hud[0]
    if not estado or estado.get('texto') is None:
        return None, None
    a, b = estado['alvo']['pontos'][:2]
    vertical = (b - a).length > 1e-9 and abs((b - a).normalized().z) > .5
    return ('altura' if vertical else 'largura'), estado


def esquecer():
    _resumo[0] = None
    _movidos[0] = set()
    _movendo[0] = None
    _quina_hover[0] = None
    _guia_hover[0] = None
    _caixas[0] = {}
    _rotulos[0] = ()
    _rotulos_guias[0] = ()
    _edicao[0] = None
    _interiores[0].clear()
    _sujos[0].clear()
    if _handler_interior[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler_interior[0], 'WINDOW')
        _handler_interior[0] = None


# (propriedade, rotulo, curto, coluna) das cotas do Promob, na CRUZ: cada
# uma do lado do modulo a que se refere; o afastamento (profundidade) no
# meio. Valores de ate' 5 digitos: a coluna nao cresce alem disso.
COTAS_EM_CRUZ = ((('cota_superior', 'Superior', 'Sup', 1),),
                 (('vao_esquerdo', 'Anterior', 'Ant', 0), ('afastamento', 'Afastamento', 'Afast', 1),
                  ('vao_direito', 'Posterior', 'Post', 2)),
                 (('cota_inferior', 'Inferior', 'Inf', 1),))
LARGURA_CAMPO_COTA = 84
LARGURA_ROTULO_INTEIRO = 76


def _campos_em_cruz(itens, x, topo, w, ativo):
    coluna = min(LARGURA_CAMPO_COTA, (w - 12) / 3)
    x0 = x + (w - (3 * coluna + 12)) / 2
    def campo(linha, indice, nome, rotulo, valor):
        itens.append((x0 + indice * (coluna + 6), topo - 37 - linha * 43, coluna, 37,
                      '%s: %s' % (rotulo, _opcoes._texto_medida(valor * 1000)),
                      ('medida', 'parede_modulo', nome, rotulo, valor * 1000)))
    for i, (nome, rotulo) in enumerate((('largura', 'A1'), ('altura', 'A2'), ('profundidade', 'A3'))):
        campo(0, i, nome, rotulo, ativo[nome])
    topo -= 43
    itens.append((x, topo - 22, w, 20, 'Cotas', None))
    topo -= 26
    for linha, cotas in enumerate(COTAS_EM_CRUZ):
        for nome, rotulo, curto, indice in cotas:
            campo(linha, indice, nome, rotulo if coluna >= LARGURA_ROTULO_INTEIRO else curto, ativo[nome])
    return topo - 3 * 43 - 6


def widgets(context, itens, x, topo, w):
    resumo = _resumo[0]
    if not resumo or not resumo['itens']:
        return topo
    ativo = selecionado(context, resumo['itens'])
    if not ativo:
        return topo
    # So' as medidas do selecionado (pedido do usuario): Livre/Fixa por
    # modulo e os botoes Redistribuir/Trocar/Desassociar sairam do menu.
    topo = _gaveta._titulo_secao(itens, x, topo, w, 'Composicao')
    return _campos_em_cruz(itens, x, topo, w, ativo) - 12


def estilo_cotas(context):
    """Linha do tema sobre halo opaco: legivel na parede e fora dela."""
    cores = context.preferences.themes[0].user_interface.wcol_regular
    return dict(linha=(*cores.text[:3], 1.0), halo=(*cores.inner[:3], 1.0),
                realce=_hud._cor_realce_hud(),
                tamanho=max(14, _opcoes._opcao('hud_tamanho_rotulo')))


def area_livre(context):
    """(x0, y0, x1, y1) da regiao fora das faixas sobrepostas (toolbar,
    cabecalho, sidebar, prateleira): ali a ponta de seta ficava escondida."""
    regiao = context.region
    x0, y0, x1, y1 = 0, 0, regiao.width, regiao.height
    for outra in (context.area.regions if context.area else ()):
        if outra.type == 'WINDOW' or outra.width <= 1 or outra.height <= 1:
            continue
        ox, oy = outra.x - regiao.x, outra.y - regiao.y
        if ox >= x1 or oy >= y1 or ox + outra.width <= x0 or oy + outra.height <= y0:
            continue        # sem sobreposicao: a regiao ja' a exclui
        if outra.alignment == 'LEFT':
            x0 = max(x0, ox + outra.width)
        elif outra.alignment == 'RIGHT':
            x1 = min(x1, ox)
        elif outra.alignment == 'BOTTOM':
            y0 = max(y0, oy + outra.height)
        elif outra.alignment == 'TOP':
            y1 = min(y1, oy)
    return x0, y0, x1, y1


def recortar_cota(a, b, livre, margem):
    """Pontas da cota trazidas para dentro de `livre` no eixo dela: a
    distancia ate' a parede fora da tela termina na borda, com a seta
    inteira a' vista (pedido do usuario). (None, None) se nada aparece."""
    x0, y0, x1, y1 = livre
    i, lo, hi = ((1, y0 + margem, y1 - margem) if abs(b.x - a.x) < abs(b.y - a.y)
                 else (0, x0 + margem, x1 - margem))
    if lo >= hi or max(a[i], b[i]) < lo or min(a[i], b[i]) > hi:
        return None, None
    a, b = a.copy(), b.copy()
    a[i], b[i] = min(max(a[i], lo), hi), min(max(b[i], lo), hi)
    return a, b


def desenhar(context):
    resumo = _resumo[0]
    if not resumo or not _paredes_edicao.ativa(context):
        return
    s = _paredes_edicao._sessao[0]
    n, u, ponto = (Vector(s[k]) for k in ('normal', 'u', 'ponto'))
    escala = context.preferences.system.ui_scale or 1.0
    estilo = estilo_cotas(context)
    tamanho = estilo['tamanho'] * escala
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    segmentos, realces, rotulos, textos = [], [], [], []
    ativo = selecionado(context, resumo['itens'])
    # A1/A2/A3 identificam o volume sempre; durante o resize as distancias
    # aos vizinhos somem para deixar o valor em edicao livre.
    editando = ativo is not None and modulo_em_edicao() == ativo['nome']
    digitada = digitacao_hud() if editando else (None, None)
    livre = area_livre(context)
    def tela(x, z):
        p = ponto + u * (x - ponto.dot(u)) + n * .002
        p.z = z
        return view3d_utils.location_3d_to_region_2d(context.region, context.region_data, p)
    def rotulo(centro, item, prop, valor, lado=0, prefixo=''):
        """Numero editavel em `centro`; `lado` -1/+1 encosta a' esquerda/
        direita de uma cota vertical, 0 centra."""
        edicao = _edicao[0]
        if not (edicao and edicao['objeto'] == item['nome'] and edicao['propriedade'] == prop):
            edicao = None
        if edicao is None and item is ativo and prop == digitada[0]:
            edicao = digitada[1]
        texto = edicao['texto'] if edicao else prefixo + _opcoes._texto_medida(valor * 1000)
        blf.size(0, tamanho)
        largura = blf.dimensions(0, texto)[0]
        x = (centro.x + 4 * escala if lado > 0 else
             centro.x - largura - 4 * escala if lado < 0 else centro.x - largura / 2)
        y = centro.y - tamanho / 2
        if prop in ('largura', 'altura', 'profundidade'):
            x = max(livre[0] + 5 * escala, min(x, livre[2] - largura - 5 * escala))
            y = max(livre[1] + 4 * escala, min(y, livre[3] - tamanho - 4 * escala))
            candidatos = [y]
            for r in rotulos:
                candidatos.extend((r[1] - tamanho - 8, r[1] + r[3] + 8))
            # Distancias conservam sua referencia; indicadores novos se
            # afastam dos numeros existentes, inclusive em modulo pequeno.
            for candidato in sorted(candidatos, key=lambda v: abs(v - y)):
                if not livre[1] + 4 <= candidato <= livre[3] - tamanho - 4:
                    continue
                if not any(x - 5 < r[0] + r[2] and x + largura + 5 > r[0]
                           and candidato - 4 < r[1] + r[3] and candidato + tamanho + 4 > r[1]
                           for r in rotulos):
                    y = candidato
                    break
        if edicao is not None and edicao is digitada[1]:
            # O clique DENTRO da caixa posiciona o cursor da HUD (`_clique_na_caixa`).
            edicao['caixas'] = [(x, y, tamanho, escala)]
        textos.append((x, y, texto, edicao))
        rotulos.append((x - 5, y - 4, largura + 10, tamanho + 8, item['nome'], prop, valor * 1000))
    def cota(a, b, item, prop, valor, numero, curto=False, lado=1, prefixo='', fracao=.5):
        if a is None or b is None or valor <= 1e-6:
            return
        a, b = recortar_cota(a, b, livre, 8 * escala)
        if a is None or ((b - a).length < 12 * escala and not curto):
            return
        linhas = realces if ativo == item else segmentos
        linhas.extend((a, b))
        direcao = (b - a).normalized()
        normal = Vector((-direcao.y, direcao.x))
        comprimento = min(7 * escala, (b - a).length / 3)
        for p, sinal in ((a, 1), (b, -1)):
            for lado_seta in (-1, 1):
                linhas.extend((p, p + direcao * sinal * comprimento + normal * lado_seta * 3 * escala))
        vertical = abs(b.x - a.x) < abs(b.y - a.y)
        rotulo(a.lerp(b, fracao), item, prop, valor, lado if vertical else 0, prefixo)
    gpu.state.blend_set('ALPHA')
    try:
        for i, item in enumerate(resumo['itens']):
            a, b = tela(item['inicio'], item['base']), tela(item['fim'], item['base'])
            if a is None or b is None or ativo != item:
                continue
            if not editando:
                # Guias de movimento (desenho do usuario): cada distancia
                # sai do MEIO da sua face e vai ate' o vizinho/ponta/piso/teto.
                meio_x = (item['inicio'] + item['fim']) / 2
                meio_z = item['base'] + item['altura'] / 2
                topo_modulo = item['base'] + item['altura']
                cota(tela(item['inicio'] - item['vao_esquerdo'], meio_z), tela(item['inicio'], meio_z),
                     item, 'vao_esquerdo', item['vao_esquerdo'], i, curto=True)
                cota(tela(item['fim'], meio_z), tela(item['fim'] + item['vao_direito'], meio_z),
                     item, 'vao_direito', item['vao_direito'], i, curto=True)
                cota(tela(meio_x, item['base'] - item['cota_inferior']), tela(meio_x, item['base']),
                     item, 'cota_inferior', item['cota_inferior'], i, curto=True)
                cota(tela(meio_x, topo_modulo), tela(meio_x, topo_modulo + item['cota_superior']),
                     item, 'cota_superior', item['cota_superior'], i, curto=True)
                # Profundidade nao tem linha de frente: o afastamento e' um
                # numero editavel no meio do modulo.
                meio = tela((item['inicio'] + item['fim']) / 2, item['base'] + item['altura'] / 2)
                if meio is not None:
                    rotulo(meio, item, 'afastamento', item['afastamento'], prefixo='Afast. ')
            # Mesmas propriedades e hit-tests do menu: nenhuma medida paralela.
            desloc = Vector((0, -14 * escala))
            cota(a + desloc, b + desloc, item, 'largura', item['largura'], i, prefixo='A1: ')
            topo = tela(item['fim'], item['base'] + item['altura'])
            cota(b + Vector((12 * escala, 0)), topo + Vector((12 * escala, 0)),
                 item, 'altura', item['altura'], i, prefixo='A2: ', fracao=.75)
            # Na vista frontal a profundidade nao se projeta. Uma chamada
            # na quina identifica A3 sem fingir uma aresta medida na tela.
            rotulo(b + Vector((26, 26)) * escala, item, 'profundidade',
                   item['profundidade'], lado=1, prefixo='A3 Prof.: ')
            r = rotulos[-1]
            ponta = Vector((max(r[0], min(b.x, r[0] + r[2])), r[1] + r[3] / 2))
            realces.extend((b, ponta))
        movendo = _movendo[0]
        item = next((f for f in resumo['itens'] if movendo and f['nome'] == movendo['modulo']), None)
        if item is not None:
            s0, s1, z0, z1 = s['regiao']['retangulo']
            fim, topo = item['fim'], item['base'] + item['altura']
            lados = {'esquerda': ((item['inicio'], item['base']), (item['inicio'], topo)),
                     'direita': ((fim, item['base']), (fim, topo)),
                     'base': ((item['inicio'], item['base']), (fim, item['base'])),
                     'topo': ((item['inicio'], topo), (fim, topo))}
            # A lateral pega e a linha-alvo de ponta a ponta da face.
            pares = [lados[movendo['lado']]] if movendo['lado'] else []
            pares += [((v, z0), (v, z1)) if eixo == 'x' else ((s0, v), (s1, v))
                      for eixo, v in movendo['linhas']]
            for a, b in pares:
                a, b = tela(*a), tela(*b)
                if a is not None and b is not None:
                    realces.extend((a, b))
        # O circulo do snap de quina (pedido do usuario): na quina sob o
        # mouse e, movendo, na quina pega (onde ela estiver, grudada ou nao).
        quina = (movendo or {}).get('quina') if movendo else (
            _quina_hover[0][1] if _quina_hover[0] else None)
        centro = tela(*quina) if quina else None
        if centro is not None:
            raio = RAIO_QUINA_PX * escala
            passos = 24
            volta = [centro + Vector((math.cos(k * math.tau / passos), math.sin(k * math.tau / passos))) * raio
                     for k in range(passos)]
            for a, b in zip(volta, volta[1:] + volta[:1]):
                realces.extend((a, b))
        for largura, cor, linhas in ((4 * escala, estilo['halo'], segmentos + realces),
                (2 * escala, estilo['linha'], segmentos), (2 * escala, estilo['realce'], realces)):
            if linhas:
                gpu.state.line_width_set(largura)
                shader.bind()
                shader.uniform_float('color', cor)
                batch_for_shader(shader, 'LINES', {'pos': linhas}).draw(shader)
        # O traco nunca passa sobre o numero nem sobre o cursor de edicao.
        for x, y, texto, edicao in textos:
            caixa_editavel(x, y, texto, edicao, tamanho, escala)
    finally:
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')
    _rotulos[0] = tuple(rotulos)


def cota_sob(x, y):
    return next((r for r in reversed(_rotulos[0] + _rotulos_guias[0])
                 if r[0] <= x <= r[0] + r[2] and r[1] <= y <= r[1] + r[3]), None)


def widgets_guias(context, itens, x, topo, w):
    cena = context.scene
    topo = _gaveta._titulo_secao(itens, x, topo, w, 'Guias')
    topo = _gaveta._linha_escolha_gaveta(itens, x, topo - 25, w, '', CHAVE_GUIAS_MODO,
                                         MODOS_GUIAS, modo_guias(cena),
                                         alvo=ALVO_GUIAS) + 23
    campos = [('%s: %s' % (g['nome'], _opcoes._texto_medida(g['altura_mm'])),
               ('medida', 'parede_guia', str(i), g['nome'], g['altura_mm']))
              for i, g in enumerate(guias(cena))]
    topo = _gaveta._campos_em_linhas(context, itens, x, topo, w, campos)
    itens.append((x, topo - 28, w, 28, 'Restaurar guias padrao',
                  ('operador', 'object.cabinet_restaurar_guias_parede')))
    return topo - 46


class OBJECT_OT_restaurar_guias_parede(Operator):
    bl_idname = 'object.cabinet_restaurar_guias_parede'
    bl_label = 'Restaurar guias padrao'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if CHAVE_GUIAS in context.scene:
            del context.scene[CHAVE_GUIAS]
        sincronizar_guias(context)
        return {'FINISHED'}


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


class OBJECT_OT_mover_na_parede(Operator):
    """Move o modulo no plano da parede: gruda na quina que o mouse passar
    perto; com Alt segurado, tambem a lateral mais perto do mouse"""
    bl_idname = 'object.cabinet_mover_na_parede'
    bl_label = 'Mover na Parede'
    bl_options = {'REGISTER', 'UNDO'}

    modulo: StringProperty(options={'SKIP_SAVE'})
    # Clique esquerdo num modulo: so' vira movimento depois do limiar de
    # arraste; antes disso tudo passa (o clique continua selecionando).
    arrastar: BoolProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and _paredes_edicao.ativa(context)

    def _vista(self):
        _janela, area, regiao = _paredes_edicao._janela_da_sessao()
        return (regiao, area.spaces.active.region_3d) if regiao is not None else (None, None)

    def _no_plano(self, event):
        s = _paredes_edicao._sessao[0]
        regiao, rv3d = self._vista()
        if regiao is None:
            return None
        xy = (event.mouse_x - regiao.x, event.mouse_y - regiao.y)
        origem = view3d_utils.region_2d_to_origin_3d(regiao, rv3d, xy)
        direcao = view3d_utils.region_2d_to_vector_3d(regiao, rv3d, xy)
        p = intersect_line_plane(origem, origem + direcao, Vector(s['ponto']), Vector(s['normal']))
        return None if p is None else (p.dot(Vector(s['u'])), p.z)

    def invoke(self, context, event):
        s = _paredes_edicao._sessao[0]
        obj = bpy.data.objects.get(self.modulo)
        caixa = _paredes.caixa_do_modulo(obj) if obj is not None else None
        f = ficha(obj, s, caixa) if caixa is not None else None
        mouse = self._no_plano(event)
        if f is None or mouse is None:
            return {'CANCELLED', 'PASS_THROUGH'}
        regiao, rv3d = self._vista()
        px = _paredes._px_por_metro(regiao, rv3d, Vector(s['ponto']), Vector(s['u']))
        self._tolerancia = IMA_PX / px if px else 0.0
        self._tolerancia_quina = QUINA_PX / px if px else 0.0
        # A quina perto do mouse (o circulo aceso) vale mais que a lateral.
        self._quina = quina_sob(f, *mouse, self._tolerancia_quina)
        self._lado = None if self._quina else lado_sob(f, *mouse, LADO_PX / px if px else 0.0)
        itens = itens_da_face(context)
        self._alvos = _alvos_do_ima(s, itens, obj.name, context.scene)
        self._quinas = _quinas_do_ima(s, itens, obj.name)
        self._ficha, self._caixa, self._mouse = f, caixa, mouse
        self._matriz = obj.matrix_world.copy()
        self._ponto = tuple(obj.get(_paredes.CHAVE_PAREDE_PONTO, ()))
        self._xy = (event.mouse_x, event.mouse_y)
        self._arrastou = not self.arrastar
        context.window_manager.modal_handler_add(self)
        if self._arrastou:
            self._comecar(context)
        return {'RUNNING_MODAL'}

    def _comecar(self, context):
        _movendo[0] = dict(modulo=self.modulo, lado=self._lado, linhas=[],
                           quina=quinas_da_ficha(self._ficha)[self._quina] if self._quina else None)
        _quina_hover[0] = None
        try:
            context.workspace.status_text_set(
                'Mover na parede | Mouse perto de uma quina: gruda nela | Segure Alt: laterais'
                ' | Esc/direito: cancelar')
        except Exception:
            pass
        _paredes_edicao._redesenhar()

    def _encerrar(self, context):
        _movendo[0] = None
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
        if _paredes_edicao.ativa(context):
            atualizar(context)
        _paredes_edicao._redesenhar()

    def _restaurar(self, context):
        obj = bpy.data.objects.get(self.modulo)
        if obj is not None:
            obj.matrix_world = self._matriz
            if self._ponto:
                obj[_paredes.CHAVE_PAREDE_PONTO] = self._ponto
            _paredes._conferidos.pop(obj.name, None)
            context.view_layer.update()

    def _mover(self, context, event):
        s = _paredes_edicao._sessao[0]
        obj = bpy.data.objects.get(self.modulo)
        parede = bpy.data.objects.get(s['parede'])
        mouse = self._no_plano(event)
        if obj is None or parede is None or mouse is None:
            return
        f = self._ficha
        inicio = f['inicio'] + mouse[0] - self._mouse[0]
        base = f['base'] + mouse[1] - self._mouse[1]
        # Pedido do usuario: a quina gruda so' de o mouse passar perto dela;
        # o Alt segurado liga tambem as laterais (solto, elas ficam livres).
        inicio, base, linhas = posicao_com_ima(
            f, inicio, base, self._alvos, self._lado, self._tolerancia,
            self._quinas, mouse, laterais=event.alt,
            tolerancia_quina=self._tolerancia_quina, quina=self._quina)
        n, u, ponto = (Vector(s[k]) for k in ('normal', 'u', 'ponto'))
        centro = ponto + u * (inicio + f['largura'] / 2 - ponto.dot(u))
        centro.z = base + f['altura'] / 2
        # As regras da insercao: dentro da face e sem sobrepor vizinho.
        costas, erro = _paredes_edicao.encaixar_na_face(context, obj, centro, s, self._caixa)
        if erro:
            try:
                context.workspace.status_text_set(erro + ' | Esc: cancelar')
            except Exception:
                pass
            return
        _paredes.colocar_na_parede(obj, parede, costas, n, self._caixa)
        _paredes._conferidos.pop(obj.name, None)
        context.view_layer.update()
        quina = None
        if self._quina:
            quina = (inicio + self._quina[0] * f['largura'], base + self._quina[1] * f['altura'])
        _movendo[0] = dict(modulo=self.modulo, lado=self._lado, linhas=linhas, quina=quina)
        _paredes_edicao._redesenhar()

    def modal(self, context, event):
        if not _paredes_edicao.ativa(context) or bpy.data.objects.get(self.modulo) is None:
            self._encerrar(context)
            return {'CANCELLED', 'PASS_THROUGH'}
        if not self._arrastou:
            if event.type == 'MOUSEMOVE':
                # O limiar do Blender: passado ele, o arraste e' daqui. Se
                # um G/gizmo nativo ja' comecou, ele e' o dono do gesto.
                limiar = context.preferences.inputs.drag_threshold_mouse
                if (max(abs(event.mouse_x - self._xy[0]), abs(event.mouse_y - self._xy[1])) < limiar
                        or _eventos._transformando()):
                    return {'PASS_THROUGH'}
                self._arrastou = True
                self._comecar(context)
                self._mover(context, event)
                return {'RUNNING_MODAL'}
            if event.type in {'LEFTMOUSE', 'ESC', 'RIGHTMOUSE'}:
                # soltou sem arrastar: era so' o clique de selecao
                return {'CANCELLED', 'PASS_THROUGH'}
            return {'PASS_THROUGH'}
        if event.type in {'MOUSEMOVE', 'LEFT_ALT', 'RIGHT_ALT'}:
            self._mover(context, event)
            return {'RUNNING_MODAL'}
        confirma = 'RELEASE' if self.arrastar else 'PRESS'
        if ((event.type == 'LEFTMOUSE' and event.value == confirma)
                or (event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS')):
            self._encerrar(context)
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._restaurar(context)
            self._encerrar(context)
            return {'CANCELLED'}
        if event.type.startswith(('WHEEL', 'TRACKPAD', 'NDOF')):
            return {'PASS_THROUGH'}      # zoom, como no G nativo
        # O resto (botao do meio etc.) nao chega ao observador, que sairia
        # da vista da parede ao girar.
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._restaurar(context)
        self._encerrar(context)


class OBJECT_OT_editar_cota_parede(Operator):
    bl_idname = 'object.cabinet_editar_cota_parede'
    bl_label = 'Editar cota do modulo'
    bl_options = {'REGISTER', 'UNDO'}
    objeto: StringProperty(options={'SKIP_SAVE'})
    propriedade: StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        guia = self._guia()
        if guia is not None:
            lista = guias(context.scene)
            if guia >= len(lista):
                return {'CANCELLED'}
            valor = lista[guia]['altura_mm'] / 1000
        else:
            item = next((f for f in itens_da_face(context) if f['nome'] == self.objeto), None)
            if item is None:
                return {'CANCELLED'}
            valor = (item['inicio'] - _paredes_edicao._sessao[0]['regiao']['retangulo'][0]
                     if self.propriedade == 'esquerda' else item[self.propriedade])
        texto = _opcoes._numero_na_unidade(valor * 1000)
        _edicao[0] = dict(objeto=self.objeto, propriedade=self.propriedade, texto=texto,
                          cursor=len(texto), selecionado=True)
        # Tique so' para o cursor piscar com o mouse parado; sai no cancel.
        self._tique = context.window_manager.event_timer_add(PISCA_CURSOR_S / 2, window=context.window)
        context.window_manager.modal_handler_add(self)
        _paredes_edicao._redesenhar()
        return {'RUNNING_MODAL'}

    def _guia(self):
        # Rotulo de guia: sem objeto, propriedade 'guia_<indice>'.
        if not self.objeto and self.propriedade.startswith('guia_'):
            return int(self.propriedade[len('guia_'):])
        return None

    def cancel(self, context):
        _edicao[0] = None
        tique = getattr(self, '_tique', None)
        if tique is not None:
            context.window_manager.event_timer_remove(tique)
            self._tique = None
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
        if event.type == 'TIMER':
            _paredes_edicao._redesenhar()
            return {'RUNNING_MODAL'}
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cancel(context)
            return {'CANCELLED'}
        if event.type in {'RET', 'NUMPAD_ENTER', 'LEFTMOUSE'}:
            try:
                # Distancia pode zerar; dimensoes e guias validam no dono.
                valor = _gaveta_desenho._ler_medida_digitada(estado['texto'], minimo=0) * 1000
                guia = self._guia()
                erro = (editar_guia(context, guia, valor) if guia is not None
                        else editar_modulo(context, self.objeto, self.propriedade, valor))
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
