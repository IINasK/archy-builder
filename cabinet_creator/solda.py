"""Correntes da solda (adjacencia): desagregar, conectar, ancoras,
regua (resetar distancia) e o nome do grupo que a Corrente cria."""

import bpy, bmesh, math, json, gpu, blf
from array import array
from gpu_extras.batch import batch_for_shader
from bpy.props import BoolProperty, StringProperty, IntProperty
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree
from bpy_extras import view3d_utils
from bpy.types import Operator, Macro
from types import SimpleNamespace

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = None
_gavetas = None
_modulos = None
_opcoes = None
_eventos = None
_selecao = None
_portas = None
_ferragens = None
_importacao = None
_puxadores = None
_gaveta = None
_orcamento = None
_hud = None
_perguntas = None
_portas_viewport = None
_gaveta_desenho = None
_frentes = None
_formas = None
_cache_ancoras = [{}]  # nomes/numeros/KDTree nativa, nunca RNA
_timer_conexao = [None]
_handler_conexao = [None]
_normalizar_pendente = [True]


def encerrar_conexao_nativa(context=None):
    context=context or bpy.context
    estado=_conexao_manual[0]
    if estado and not _eventos._desfazendo[0]:_restaurar_previa_solda(estado)
    if estado and estado.get('snap_nativo'):_gavetas._terminar_snap_criacao()
    if _timer_conexao[0] is not None:
        context.window_manager.event_timer_remove(_timer_conexao[0]);_timer_conexao[0]=None
    if _handler_conexao[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler_conexao[0],'WINDOW');_handler_conexao[0]=None
    if estado:
        for janela in context.window_manager.windows:
            for area in janela.screen.areas:
                if any(r.as_pointer()==estado.get('regiao') for r in area.regions):area.header_text_set(None)
    _conexao_manual[0]=None
    return estado


def preparar_ancoras(P, digital=None):
    if P.type!='MESH' or P.data.is_editmode:return None
    digital=digital or _frentes._digital(P.data)
    antigo=_cache_ancoras[0].get(P.data.name)
    if antigo and antigo['digital']==digital:return antigo
    arvore=KDTree(len(P.data.vertices)) if P.data.vertices else None
    assinaturas={};caixa=_chapas._malha_e_caixa(P.data)
    for v in P.data.vertices:
        arvore.insert(v.co,v.index)
        assinaturas[v.index]=(_assinatura_canto(P,P.matrix_world@v.co) if caixa else 'v%d'%v.index)
    if arvore:arvore.balance()
    pontas={}
    for i in (0,1):
        for lado,funcao in (('neg',min),('pos',max)):
            extremo=funcao((v.co[i] for v in P.data.vertices),default=0.)
            pontas[str(i)+lado]=[v.index for v in P.data.vertices if abs(v.co[i]-extremo)<1e-5]
    dado=dict(digital=digital,n=len(P.data.vertices),arvore=arvore,pontas=pontas,assinaturas=assinaturas)
    _cache_ancoras[0][P.data.name]=dado
    return dado


def _dados_ancoras(P):
    dado=_cache_ancoras[0].get(P.data.name)
    return dado if dado and dado['n']==len(P.data.vertices) else preparar_ancoras(P)

# ------------------------------------------- correntes de adjacencia
# A adjacencia (a SOLDA) liga a PONTA de uma chapa a FACE de outra e
# grava a folga daquele momento -- a origem da solda. Cada ligacao associa
# um par de vertices reais; formatos antigos podiam repetir quinas.
# - so' com a tecla das opcoes segurada (Alt por padrao);
# - aparecem TODAS as quinas soldadas do item cuja folga saiu da origem
#   mais de LIMIAR_CORRENTE_VIEWPORT (antes: so' a mais perto da camera);
# - cada linha tem a corrente (desagrega o objeto inteiro, `desagregar`)
#   e, a direita, a regua (`cabinet_resetar_distancia`: volta a solda).
LIMIAR_CORRENTE_VIEWPORT = 0.005     # m de desvio da origem da solda
RAIO_CORRENTE_PX = 14.0
VAO_BOTOES_CORRENTE_PX = 13.0        # corrente a esquerda, regua a direita
TECLAS_CORRENTE = ('LEFT_ALT', 'RIGHT_ALT', 'LEFT_CTRL', 'RIGHT_CTRL',
                   'LEFT_SHIFT', 'RIGHT_SHIFT')
_tecla_corrente_segurada = [False]


def _correntes_visiveis():
    return (_opcoes._opcao('tecla_corrente') == 'SEMPRE'
            or _tecla_corrente_segurada[0])


def _assinatura_canto(C, p):
    """Qual canto de C e' o ponto p, pelo SINAL no referencial da chapa
    ('+-+'): estavel quando a chapa muda de medida ou de lugar."""
    local = C.matrix_world.inverted() @ p
    return ''.join('+' if v > 0 else '-' for v in local)


def _canto_da_assinatura(C, assinatura):
    """Inverso de `_assinatura_canto`: o canto de C em mundo."""
    meias = _chapas._meias(C)
    local = Vector([(1 if s == '+' else -1) * m
                    for s, m in zip(assinatura, meias)])
    return C.matrix_world @ local


def _pares_da_ligacao(C, u, extremo, N):
    """Um par real: o vertice da ponta mais proximo do vizinho."""
    dc,dn=_dados_ancoras(C),_dados_ancoras(N)
    if not dc or not dn or dn['arvore'] is None:return []
    local=C.matrix_world.to_3x3().transposed()@u
    eixo=max((0,1),key=lambda i:abs(local[i]));lado='pos' if extremo>C.matrix_world.translation.dot(u) else 'neg'
    inversa=N.matrix_world.inverted();pares=[]
    for i in dc['pontas'][str(eixo)+lado]:
        p=C.matrix_world@C.data.vertices[i].co
        _co,j,_d=dn['arvore'].find(inversa@p)
        q=N.matrix_world@N.data.vertices[j].co
        pares.append((p,q,dc['assinaturas'][i],dn['assinaturas'][j]))
    pares.sort(key=lambda par: (par[1] - par[0]).length)
    escolhidos=[];locais=[]
    for par in pares:
        p=C.matrix_world.inverted()@par[0]
        if any((p.xy-q.xy).length<1e-5 for q in locais):continue
        escolhidos.append(par);locais.append(p)
        if len(escolhidos)==1:break
    return escolhidos


def _vizinho_da_ponta(C, ponta):
    nome = C.get('adj_' + ponta, '')
    uid = C.get('adj_%s_uid' % ponta, '')
    if not nome and not uid:
        return None
    N = _chapas._resolver_vizinho(C, uid, nome)
    return None if N is C else N


def _ligados_a(C):
    """Pecas ligadas a C pela adjacencia, em qualquer sentido."""
    ligados = {N for N in (_vizinho_da_ponta(C, p) for p in _chapas.PONTAS) if N}
    for X in bpy.data.objects:
        if X is not C and _chapas.MARCA_CHAPA in X and any(
                _vizinho_da_ponta(X, p) == C for p in _chapas.PONTAS):
            ligados.add(X)
    return ligados


def _ligacao_entre(C, N):
    for dono, vizinho in ((C, N), (N, C)):
        for ponta in _chapas.PONTAS:
            if _vizinho_da_ponta(dono, ponta) == vizinho:
                return dono, ponta
    return None


def _restricoes_da_ligacao(C, ponta, N):
    """A unica aresta conserva os encaixes axiais legados de ambos extremos."""
    dados = [('a', ponta, int(C.get('adj_%s_face'%ponta, 0 if ponta.endswith('pos') else 1)),
              float(C.get('adj_%s_folga'%ponta, 0.)))]
    dados += json.loads(C.get('adj_%s_restricoes'%ponta, '[]'))
    return [(C if lado == 'a' else N, p, N if lado == 'a' else C, int(face), float(folga))
            for lado, p, face, folga in dados
            if lado in ('a', 'b') and p in _chapas.PONTAS and face in (0, 1) and math.isfinite(folga)]


def _gravar_restricoes(C, ponta, N, restricoes):
    extras = {}
    for origem, p, destino, face, folga in restricoes:
        lado = 'a' if origem == C else 'b'
        if (origem not in (C, N) or destino not in (C, N)
                or origem == destino or (lado == 'a' and p == ponta)):
            continue
        extras.setdefault((lado, p), (lado, p, face, folga))
    chave = 'adj_%s_restricoes'%ponta
    valor = json.dumps(sorted(extras.values()))
    if extras and C.get(chave) != valor:
        C[chave] = valor
    elif not extras and chave in C:
        del C[chave]


def restricoes_adjacencia(chapas):
    """Mapa calculado UMA vez por ajuste, sem buscar reciprocidade por chapa."""
    alvos = {c for c in chapas if c.type == 'MESH' and _chapas.MARCA_CHAPA in c}
    resultado = {c: {} for c in alvos}
    prioridades = {}
    for c in bpy.data.objects:
        if c.type != 'MESH' or _chapas.MARCA_CHAPA not in c:
            continue
        for ponta in _chapas.PONTAS:
            n = _vizinho_da_ponta(c, ponta)
            if n is None:
                continue
            for origem, p, destino, face, folga in _restricoes_da_ligacao(c, ponta, n):
                if origem in alvos:
                    # A ponta gravada no proprio objeto prevalece sobre um
                    # descritor reverso legado; nunca depende do Outliner.
                    prioridade = (not (origem is c and p == ponta),
                                  c.get('chapa_uid', ''), c.name, ponta)
                    chave = (origem, p)
                    if chave not in prioridades or prioridade < prioridades[chave]:
                        prioridades[chave] = prioridade
                        resultado[origem][p] = (destino, face, folga)
    return resultado


def agregado(C):
    """Ligada (agregada) a alguma peca? E' o azul do botao Corrente."""
    return bool(_ligados_a(C))


def _ligacoes_adjacencia(chapas_item, limiar=None, somente_manuais=False):
    """Ligacoes que tocam o item e cuja folga saiu da ORIGEM da solda (a
    gravada) `limiar` ou mais (m; padrao LIMIAR_CORRENTE_VIEWPORT).
    A adjacencia e' gravada so' na peca que encosta (ponta dela ->
    vizinho), entao varre a cena toda: o vizinho de fora pode ser quem
    guarda a ligacao."""
    limiar = LIMIAR_CORRENTE_VIEWPORT if limiar is None else limiar
    item = set(chapas_item)
    ligacoes = []
    restricoes = restricoes_adjacencia(bpy.data.objects)
    for C in bpy.data.objects:
        if C.type != 'MESH' or _chapas.MARCA_CHAPA not in C:
            continue
        for ponta in _chapas.PONTAS:
            manual=bool(C.get('adj_%s_manual'%ponta))
            if somente_manuais and not manual:continue
            N = _vizinho_da_ponta(C, ponta)
            if N is None or (C not in item and N not in item):
                continue
            folga, u, extremo = _folga_com_sinal(C, ponta, N)
            desvio, residuos = _medida_solda(C, ponta, N, restricoes)
            if not manual and _tamanho_desvio(desvio, residuos) < limiar:
                continue            # na origem da solda: sem corrente
            ancoras = _ancoras_da_ligacao(C, ponta, N, u, extremo)
            pares = [(_vertice_da_assinatura(C, sc),
                      _vertice_da_assinatura(N, sn), sc) for sc, sn in ancoras]
            # Com ancoras gravadas cada par tem o SEU desvio: o que ja'
            # encostou some (a print do usuario: ele ficava desenhado em
            # cima do vertice, sobrepondo bolinha e botoes)
            gravadas=_ancoras_gravadas(C,ponta)
            soltos = ([manual or _desvio_ancora(C,ponta,N,gravadas.index((sc,sn)),sc,sn).length >= limiar
                       for sc,sn in ancoras] if gravadas else [True] * len(pares))
            ligacoes.append({'a': C, 'b': N, 'ponta': ponta,
                             'folga': folga, 'desvio': desvio,
                             'ancoras': ancoras, 'pares': pares,
                             'soltos': soltos,'manual':manual})
    return ligacoes


def _correntes_hud(context):
    """[corrente] de TODAS as quinas soldadas e fora da origem dos itens
    da HUD: uma por par de vertices, com o 'meio' em pixels e a peca que
    a regua move ('movel')."""
    estado = _conexao_manual[0]
    if estado and estado.get('moderna'):
        return _correntes_criacao(context, estado)
    if (not _hud._contexto_hud(context)
            or _gaveta._eh_area_gaveta(context) or estado is not None):
        return []
    if getattr(context, 'region_data', None) is None:
        return []
    chapas = [c for _o, _m, pecas in _hud._itens_hud(context) for c in pecas]
    correntes = []
    for ligacao in _ligacoes_adjacencia(chapas,somente_manuais=not _correntes_visiveis()):
        movel = ligacao['a'] if ligacao['manual'] else _peca_da_regua(context, ligacao['a'], ligacao['b'])
        for k, ((p, q, assinatura), ancora) in enumerate(
                zip(ligacao['pares'], ligacao['ancoras'])):
            if not ligacao['soltos'][k]:
                continue            # esse par ja' encostou: some
            correntes.append({'a': ligacao['a'], 'b': ligacao['b'],
                              'ponta': ligacao['ponta'], 'movel': movel,
                              'assinatura': assinatura, 'pontos': [p, q],
                              'indice': k, 'ancora': ancora,'manual':ligacao['manual'],
                              'meio': _hud._projetar_hud(context, (p + q) / 2)})
    return _correntes_sem_repeticao(correntes)


def _correntes_criacao(context, estado):
    if (_gaveta._eh_area_gaveta(context) or context.region is None
            or context.region.as_pointer() != estado['regiao']
            or getattr(context, 'region_data', None) is None):
        return []
    origem = bpy.data.objects.get(estado['origem'])
    if origem is None:return []
    correntes = []
    for k, (sc, nome, sn) in enumerate(estado['pares']):
        destino = bpy.data.objects.get(nome)
        if destino is None:continue
        try:p, q = _vertice_da_assinatura(origem, sc), _vertice_da_assinatura(destino, sn)
        except ValueError:continue
        correntes.append(dict(a=origem, b=destino, movel=origem, ponta='', indice=k,
            ancora=(sc, sn), assinatura=sc, pontos=[p, q], manual=True, criacao=True,
            meio=_hud._projetar_hud(context, (p+q)/2)))
    return _correntes_sem_repeticao(correntes)


def _correntes_sem_repeticao(correntes):
    """Arquivos antigos tambem mostram somente uma solda por par de objetos."""
    por_par = {}
    for corrente in sorted(correntes, key=lambda c: (
            (c['pontos'][1]-c['pontos'][0]).length_squared,
            c['a'].name, c['b'].name, c.get('ponta', ''), c.get('indice', 0))):
        chave = tuple(sorted((corrente['a'].name, corrente['b'].name)))
        por_par.setdefault(chave, corrente)
    return list(por_par.values())


def _vertices_mais_proximos(C, N):
    """Consulta nativa em MUNDO, somente no cadastro/migracao, nunca no redraw."""
    if not C.data.vertices or not N.data.vertices:
        raise ValueError('A chapa nao possui vertices para a solda')
    arvore = KDTree(len(N.data.vertices))
    for v in N.data.vertices:
        arvore.insert(N.matrix_world @ v.co, v.index)
    arvore.balance()
    candidatos = []
    for v in C.data.vertices:
        p = C.matrix_world @ v.co
        q, indice, _distancia = arvore.find(p)
        candidatos.append(((p-q).length_squared, v.index, indice))
    _distancia, origem, destino = min(candidatos)
    return 'v%d' % origem, 'v%d' % destino


def normalizar_ligacoes(pecas, recalcular_ancoras=False):
    """Uma aresta por par nao ordenado, preservando a origem de cenas antigas.

    A migracao explicita da biblioteca pode cadastrar o menor gap atual.
    A compatibilidade de cena nunca transforma uma chapa afastada em origem.
    """
    pecas = {o for o in pecas if o.type == 'MESH' and _chapas.MARCA_CHAPA in o}
    if _eventos._desfazendo[0] or any(o.data.is_editmode for o in pecas):
        raise ValueError('Aguarde o fim da edicao ou do undo para atualizar as soldas')
    antes = {o.name: repr(sorted((k, str(v)) for k, v in o.items()
                                if k.startswith('adj_'))) for o in pecas}
    por_par = {}
    invalidas = []
    for c in sorted(pecas, key=lambda o: (o.get('chapa_uid', ''), o.name)):
        for ponta in _chapas.PONTAS:
            n = _vizinho_da_ponta(c, ponta)
            if n not in pecas:
                continue
            ancoras = _ancoras_gravadas(c, ponta) or []
            medidas = []
            for i, (sc, sn) in enumerate(ancoras):
                try:
                    distancia = (_vertice_da_assinatura(c, sc)-_vertice_da_assinatura(n, sn)).length
                except ValueError:
                    # Uma referencia apagada continua diagnosticavel; nao a
                    # substituir silenciosamente por outro vertice proximo.
                    distancia = -1.
                    invalidas.append(dict(origem=c.name, ponta=ponta, indice=i))
                medidas.append((distancia, i))
            distancia, indice = min(medidas) if medidas else (abs(float(c.get('adj_%s_folga'%ponta, 0.))), 0)
            registro = dict(c=c, n=n, ponta=ponta, ancoras=ancoras, indice=indice,
                origens=_origens_ancoras(c, ponta), distancia=distancia,
                restricoes=_restricoes_da_ligacao(c, ponta, n))
            por_par.setdefault(frozenset((c, n)), []).append(registro)
    planos = []
    for registros in por_par.values():
        vencedor = min(registros, key=lambda r: (
            not bool(r['c'].get('adj_%s_manual'%r['ponta'])), r['distancia'],
            r['c'].get('chapa_uid', ''), r['c'].name, r['ponta']))
        par = _vertices_mais_proximos(vencedor['c'], vencedor['n']) if recalcular_ancoras else None
        planos.append((vencedor, registros, par))
    removidas = ancoras_alteradas = 0
    for r, registros, par in planos:
        c, n, ponta, indice = r['c'], r['n'], r['ponta'], r['indice']
        _gravar_restricoes(c, ponta, n,
            [dado for registro in [r]+[outro for outro in registros if outro is not r]
             for dado in registro['restricoes']])
        if par is not None:
            par = (_ancora_estavel(c, par[0]), _ancora_estavel(n, par[1]))
            if r['ancoras'] != [par]:
                _gravar_ancoras(c, ponta, [par])
                ancoras_alteradas += 1
            origem = n.matrix_world.inverted_safe().to_3x3() @ (
                _vertice_da_assinatura(c, par[0])-_vertice_da_assinatura(n, par[1]))
            valor = json.dumps([tuple(origem)])
            if c.get('adj_%s_origens'%ponta) != valor:
                c['adj_%s_origens'%ponta] = valor
            if c.get('adj_%s_manual'%ponta):
                direcao = origem.normalized() if origem.length > 1e-8 else Vector((0, 0, 1))
                c['adj_%s_direcoes'%ponta] = json.dumps([tuple(direcao)])
        elif len(r['ancoras']) > 1:
            _gravar_ancoras(c, ponta, [r['ancoras'][indice]])
            if r['origens'] is not None:
                c['adj_%s_origens'%ponta] = json.dumps([tuple(r['origens'][indice])])
            direcoes = c.get('adj_%s_direcoes'%ponta)
            if direcoes:
                c['adj_%s_direcoes'%ponta] = json.dumps([json.loads(direcoes)[indice]])
            ancoras_alteradas += 1
        for outro in registros:
            if outro is not r:
                _chapas._limpar_ponta(outro['c'], outro['ponta'])
                removidas += 1
    alteradas = sorted(o.name for o in pecas if antes[o.name] != repr(sorted(
        (k, str(v)) for k, v in o.items() if k.startswith('adj_'))))
    return dict(ligacoes=len(planos), removidas=removidas, ancoras=ancoras_alteradas,
                alteradas=alteradas, invalidas=invalidas)


def normalizar_pendentes():
    if (_normalizar_pendente[0] and bpy.context.mode == 'OBJECT'
            and not _eventos._desfazendo[0] and not _chapas._ocupado[0]
            and not _eventos._ha_modal_ativo()):
        normalizar_ligacoes(bpy.data.objects)
        _normalizar_pendente[0] = False


def _par_qualidade_ancoras(c, n):
    return tuple(sorted((c.name, n.name)))


def auditar_ancoras(pecas):
    """Proposta para UM modulo; nao altera seus vinculos nem sua geometria."""
    candidatos=[];invalidas=[]
    for c in pecas:
        for ponta in _chapas.PONTAS:
            n=_vizinho_da_ponta(c,ponta)
            if n is None:continue
            for indice,(sc,sn) in enumerate(_ancoras_gravadas(c,ponta) or _ancoras_da_ligacao(c,ponta,n)):
                try:p,q=_vertice_da_assinatura(c,sc),_vertice_da_assinatura(n,sn)
                except ValueError:
                    invalidas.append(dict(origem=c.name,ponta=ponta,indice=indice,motivo='Ancora invalida'));continue
                candidatos.append(dict(origem=c.name,destino=n.name,ponta=ponta,indice=indice,
                    par=_par_qualidade_ancoras(c,n),
                    assinatura=sc,alvo=sn,ponto=tuple(p),final=tuple(q),distancia=(p-q).length,
                    raio=min(.025,max(c.chapa_espessura_mm,n.chapa_espessura_mm)/1000)+.00005))
    return _refinar_candidatos_ancoras(candidatos,invalidas)


def _refinar_candidatos_ancoras(candidatos, invalidas=()):
    aceitas=[];rejeitadas=list(invalidas);ligacoes={}
    # Menor distancia primeiro garante preferencia por contato real, independente da ordem do Outliner.
    for c in sorted(candidatos,key=lambda c:(c['distancia'],c['origem'],c['destino'],c['assinatura'],c['alvo'])):
        par=tuple(sorted(c.get('par',(c['origem'],c['destino']))))
        if par in ligacoes:
            rejeitadas.append(dict(c,motivo='Par de objetos ja soldado'));continue
        aceitas.append(c)
        ligacoes.setdefault(par,[]).append(len(aceitas)-1)
    return dict(candidatas=len(candidatos),aceitas=aceitas,rejeitadas=rejeitadas,
        ligacoes=[dict(pecas=par,ancoras=indices) for par,indices in sorted(ligacoes.items())])


def propor_ancoras_piloto(pecas):
    """Auditoria explicita fora do gesto: busca contato zero nas juntas existentes."""
    candidatos=[];pares=set();sem_contato=[]
    for c in sorted(pecas,key=lambda o:o.name):
        for ponta in _chapas.PONTAS:
            n=_vizinho_da_ponta(c,ponta)
            if n is None:continue
            par=tuple(sorted((c.name,n.name)))
            if par in pares:continue
            pares.add(par)
            # So' a auditoria percorre os vertices; cliques continuam no motor nativo.
            origem=_ancoras_da_malha(c);destino=_ancoras_da_malha(n)
            arvore=KDTree(len(destino))
            for k,(_s,p) in enumerate(destino):arvore.insert(p,k)
            arvore.balance();contatos=[]
            for sc,p in origem:
                for q,k,d in arvore.find_range(p,1e-5):
                    sn=destino[k][0]
                    contatos.append(dict(origem=c.name,destino=n.name,ponta=ponta,
                        par=_par_qualidade_ancoras(c,n),
                        assinatura=sc,alvo=sn,ponto=tuple(p),final=tuple(q),distancia=d,
                        raio=min(.025,max(c.chapa_espessura_mm,n.chapa_espessura_mm)/1000)+.00005))
            if not contatos:sem_contato.append(dict(pecas=par,motivo='Sem quinas coincidentes; revisar apoio antes de soldar'))
            candidatos.extend(contatos)
    resultado=_refinar_candidatos_ancoras(candidatos)
    resultado['sem_contato']=sem_contato
    return resultado


RAIO_BOLINHA_PX = 9.0
_bolinha_hover = [None]          # (chapa, ponta, indice, lado) sob o mouse


def _bolinhas_da_corrente(context, corrente):
    """{'a': ponto na tela do vertice da chapa, 'b': do vertice alvo}."""
    p, q = corrente['pontos']
    return {lado: ponto for lado, ponto in (
        ('a', _hud._projetar_hud(context, p)), ('b', _hud._projetar_hud(context, q)))
        if ponto is not None}


def _bolinha_sob_mouse(context, posicao, correntes=None):
    """(corrente, 'a' | 'b') da bolinha branca sob o mouse, ou (None, None).
    'a' = o vertice da chapa soldada, 'b' = onde ele encosta."""
    raio = RAIO_BOLINHA_PX * max(1.0, context.preferences.system.ui_scale)
    mouse = Vector(posicao)
    melhor = None
    for corrente in (_correntes_hud(context) if correntes is None else correntes):
        for lado, ponto in _bolinhas_da_corrente(context, corrente).items():
            d = (ponto - mouse).length
            if d <= raio and (melhor is None or d < melhor[0]):
                melhor = (d, corrente, lado)
    return (melhor[1], melhor[2]) if melhor else (None, None)


def _chave_bolinha(corrente, lado):
    return (corrente['a'].name, corrente['ponta'], corrente['indice'], lado)


def _botoes_da_corrente(context, corrente):
    """{'corrente': centro, 'regua': centro} em pixels (lado a lado)."""
    if corrente['meio'] is None:
        return {}
    vao = VAO_BOTOES_CORRENTE_PX * max(1.0, context.preferences.system.ui_scale)
    return {'corrente': corrente['meio'] - Vector((vao, 0)),
            'regua': corrente['meio'] + Vector((vao, 0))}


def _campo_distancia_corrente(context,corrente):
    if not corrente.get('manual') or corrente['meio'] is None:return None
    escala=max(1.,context.preferences.system.ui_scale)
    valor=(corrente['pontos'][0]-corrente['pontos'][1]).length
    texto=_opcoes._texto_medida(valor*1000)
    blf.size(0,round(12*escala));w,h=blf.dimensions(0,texto)
    return corrente['meio'].x-w/2,corrente['meio'].y+22*escala,w,h,texto,valor


def _botao_corrente_sob_mouse(context, posicao, correntes=None):
    """(corrente, 'corrente' | 'regua') sob o mouse, ou (None, None)."""
    raio = RAIO_CORRENTE_PX * max(1.0, context.preferences.system.ui_scale)
    mouse = Vector(posicao)
    melhor = None
    for corrente in (_correntes_hud(context) if correntes is None else correntes):
        for tipo, centro in _botoes_da_corrente(context, corrente).items():
            d = (centro - mouse).length
            if d <= raio and (melhor is None or d < melhor[0]):
                melhor = (d, corrente, tipo)
    return (melhor[1], melhor[2]) if melhor else (None, None)


def _alvo_da_corrente(context, posicao):
    """('bolinha', corrente, lado), ('botao', corrente, tipo) ou None: o
    MAIS PERTO do mouse. Numa linha curta na tela a bolinha da ponta fica
    sob o botao -- primeiro que achasse roubava o clique do outro."""
    mouse = Vector(posicao)
    escala = max(1.0, context.preferences.system.ui_scale)
    candidatos = []
    correntes = _correntes_hud(context)
    for c in correntes:
        campo=_campo_distancia_corrente(context,c)
        if campo:
            x,y,w,h,_texto,_valor=campo
            if x-4<=mouse.x<=x+w+4 and y-4<=mouse.y<=y+h+4:
                return 'distancia',c,None
    corrente, lado = _bolinha_sob_mouse(context, posicao, correntes)
    if corrente is not None:
        ponto = _bolinhas_da_corrente(context, corrente)[lado]
        candidatos.append(((ponto - mouse).length / (RAIO_BOLINHA_PX * escala),
                           'bolinha', corrente, lado))
    corrente, tipo = _botao_corrente_sob_mouse(context, posicao, correntes)
    if corrente is not None:
        centro = _botoes_da_corrente(context, corrente)[tipo]
        candidatos.append(((centro - mouse).length / (RAIO_CORRENTE_PX * escala),
                           'botao', corrente, tipo))
    if _conexao_manual[0] is not None:
        return min(candidatos,key=lambda c:c[0])[1:] if candidatos else None
    grupo, indice = _portas_viewport._canto_porta_sob_mouse(context, posicao)
    if grupo is not None:
        ponto = _hud._projetar_hud(context, _portas_viewport._cantos_da_porta(grupo)[indice])
        candidatos.append(((ponto - mouse).length / (RAIO_BOLINHA_PX * escala),
                           'canto_porta', grupo, indice))
    grupo, indice = _gavetas.ponto_sob_mouse(context, posicao)
    if grupo is not None:
        ponto = _hud._projetar_hud(context, _gavetas.pontos_editaveis(grupo)[indice])
        candidatos.append(((ponto - mouse).length / (RAIO_BOLINHA_PX * escala),
                           'ponto_gaveta', grupo, indice))
    grupo, tipo = _ferragens._controle_ferragem_sob_mouse(context, posicao)
    if grupo is not None:
        ponto = next(_hud._projetar_hud(context, c[1])
                     for c in _ferragens._controles_ferragens(grupo, {tipo}))
        candidatos.append(((ponto - mouse).length / (RAIO_BOLINHA_PX * escala),
                           'ferragem', grupo, tipo))
    pux = _puxadores._puxador_sob_mouse(context, posicao)
    if pux is not None:
        ponto = _hud._projetar_hud(context, _puxadores._ancora_do_puxador(pux))
        candidatos.append(((ponto - mouse).length / (RAIO_BOLINHA_PX * escala),
                           'puxador', pux, None))
    if not candidatos:
        return None
    return min(candidatos, key=lambda c: c[0])[1:]


def desassociar(a, b):
    """Apaga TODAS as ligacoes entre a e b, dos dois lados. Devolve
    quantas pontas foram desligadas."""
    n = 0
    for C, N in ((a, b), (b, a)):
        for ponta in _chapas.PONTAS:
            if _vizinho_da_ponta(C, ponta) != N:
                continue
            base = 'adj_' + ponta
            for sufixo in ('', '_uid', '_folga', '_face', '_ancoras', '_origens','_manual','_direcoes','_restricoes'):
                if base + sufixo in C:
                    del C[base + sufixo]
            n += 1
    return n


def _atualizar_modulo(modulo):
    try:
        bpy.context.view_layer.update()
        _modulos.reposicionar_origem(modulo)
        _modulos.sincronizar_medidas_conjunto(modulo)
        _modulos.atualizar_sistemas_do_conjunto(modulo)
    except Exception as e:
        print("[Cabinet Creator] atualizar modulo:", e)


def desagregar(C):
    """Desassocia TODAS as quinas de C de uma vez (pedido do usuario: a
    quina clicada vale pelo objeto inteiro) e, se C estava num modulo,
    tira C dele sem sair do lugar. Devolve quantas pecas soltou."""
    soltas, modulo = _soltar(C)
    if modulo is not None:
        _atualizar_modulo(modulo)
    return soltas


def _soltar(C):
    """Apaga as ligacoes de C e o tira do modulo sem sair do lugar.
    Devolve (pecas desligadas, modulo de onde saiu ou None)."""
    soltas = 0
    for N in _ligados_a(C):
        desassociar(C, N)
        soltas += 1
    modulo = _portas._modulo_da_chapa(C)
    if modulo is not None:
        mundo = C.matrix_world.copy()
        C.parent = None
        C.matrix_world = mundo
        # fora do armario, na RAIZ da cena (pedido do usuario)
        _modulos._mover_para_colecao(C, bpy.context.scene.collection)
    return soltas, modulo


def desagregar_grupo(pecas):
    """Desagrega TODAS as pecas de uma vez ("desagregar todos os itens
    deste grupo"). O modulo que fica sem filho nenhum e' apagado: um
    Empty vazio so' sobraria na cena com medidas de nada."""
    modulos = set()
    for C in pecas:
        _n, modulo = _soltar(C)
        if modulo is not None:
            modulos.add(modulo)
    for modulo in modulos:
        if modulo.children:
            _atualizar_modulo(modulo)
        else:
            colecao = _modulos._colecao_do_modulo(modulo)
            bpy.data.objects.remove(modulo, do_unlink=True)
            if colecao is not None and not colecao.all_objects:
                bpy.data.collections.remove(colecao)
    return len(pecas)


def _movimentos_por_pares(C, pares):
    """Valida todos os destinos e as duas peles antes de escrever na malha."""
    inversa=C.matrix_world.inverted().to_3x3();deltas={}
    for s,q in pares:
        ids=_indices_da_assinatura(C,s)
        if not ids:raise ValueError('O vertice de origem nao existe mais')
        i=ids[0];d=inversa@(Vector(q)-C.matrix_world@C.data.vertices[i].co)
        if i in deltas and (deltas[i]-d).length>1e-6:
            raise ValueError('O mesmo vertice recebeu destinos diferentes')
        deltas[i]=d
    movimentos={}
    for i,d in deltas.items():
        parceiro=_indices_da_assinatura(C,_parceiro_espessura(C,'v%d'%i))
        for j in {i,*parceiro}:
            if j in movimentos and (movimentos[j]-d).length>1e-6:
                raise ValueError('As ancoras exigem alterar a espessura da chapa')
            movimentos[j]=d
    return deltas,movimentos


def _puxar_por_pares(C, pares):
    """Uma ancora translada a peca inteira; varias impoem pontos exatos.

    A origem do Object nao participa do encaixe. A malha nativa conserva
    topologia/UV; cada vertice move junto com seu parceiro da espessura.
    """
    if not pares:return
    if C.mode=='EDIT' or C.data.is_editmode:raise ValueError('Saia do modo de edicao')
    deltas,movimentos=_movimentos_por_pares(C,pares)
    primeiro=next(iter(deltas.values()))
    if all((d-primeiro).length<1e-6 for d in deltas.values()):
        mundo=C.matrix_world.copy();mundo.translation+=C.matrix_world.to_3x3()@primeiro
        C.matrix_world=mundo
    else:
        # Deslocamento transversal comum move todas as peles, sem inclinar
        # a chapa por uma translacao igual pedida nas duas quinas.
        comum_z=primeiro.z if all(abs(d.z-primeiro.z)<1e-6 for d in deltas.values()) else 0.
        if C.data.users>1:C.data=C.data.copy()
        bm=bmesh.new()
        try:
            bm.from_mesh(C.data);bm.verts.ensure_lookup_table()
            bmesh.ops.translate(bm,verts=list(bm.verts),vec=Vector((0,0,comum_z)))
            for i,d in movimentos.items():
                bmesh.ops.translate(bm,verts=[bm.verts[i]],vec=d-Vector((0,0,comum_z)))
            bm.to_mesh(C.data)
        finally:bm.free()
        C.data.update();_chapas.absorver_malha_editada(C,reorientar=False)
    _frentes.preparar(C,forcar=True);_formas.esquecer()
    bpy.context.view_layer.update()


def juntar_conexao(C, alvos, pecas, juntar, pares_reais=None):
    """Associa na posicao atual; juntar apenas muda a filiacao ao modulo.
    A origem e' o afastamento cadastrado, nunca um encaixe forcado."""
    pecas = {N for N in pecas if N is not None and N is not C}
    plano=_plano_ancoras_reais(C,pares_reais) if pares_reais else None
    # `alvos` pode vir vazio quando so' a ponta do VIZINHO alcanca C: o
    # modulo sai das `pecas`, senao "Sim, juntar" faria o mesmo que "Nao".
    if juntar:
        modulo = next((m for m in (_portas._modulo_da_chapa(N) for N in pecas)
                       if m is not None), None)
        if modulo is not None:
            # Preparar antes de religar o pai: preset sem marca nao pode
            # falhar no meio, nem deixar uma nova tentativa presa na raiz.
            colecao = _modulos._garantir_colecao_modulo(bpy.context.scene,modulo)
            if _portas._modulo_da_chapa(C) != modulo:
                mundo = C.matrix_world.copy()
                C.parent = modulo
                C.matrix_parent_inverse = modulo.matrix_world.inverted()
                C.matrix_world = mundo
            pecas |= set(_modulos._chapas_do_conjunto(modulo))
            bpy.context.view_layer.update()
            _modulos._mover_para_colecao(C,colecao)
            if not plano:
                _chapas.associar_por_distancia(C, pecas)
            _modulos.reposicionar_origem(modulo)
            _modulos.sincronizar_medidas_conjunto(modulo)
        elif not plano:_chapas.associar_por_distancia(C, pecas)
        if plano:_registrar_pares_reais(C,plano)
        return
    if not plano:_chapas.associar_por_distancia(C, pecas)
    if plano:_registrar_pares_reais(C,plano)


def _plano_ancoras_reais(C, pares):
    """Valida todas as referencias antes de mover, sem sobrescrever vizinhos."""
    vizinhos={}
    for sc,nome,sn in pares:
        N=bpy.data.objects.get(nome)
        if N is None or N is C:raise ValueError('A chapa de destino nao existe mais')
        if nome in vizinhos:raise ValueError('Cada par de objetos permite somente uma solda')
        ids=_indices_da_assinatura(C,sc)
        if not ids or not _indices_da_assinatura(N,sn):raise ValueError('O vertice da ancora nao existe mais')
        vizinhos.setdefault(nome,[]).append((sc,sn))
    if len(vizinhos)>len(_chapas.PONTAS):raise ValueError('A chapa ja possui quatro destinos nesta conexao')
    limites=[(min(v.co[i] for v in C.data.vertices),max(v.co[i] for v in C.data.vertices)) for i in (0,1)]
    restricoes = restricoes_adjacencia([C])[C]
    grupos={};ocupadas={p for p,(n,_face,_folga) in restricoes.items() if n.name not in vizinhos}
    if len(vizinhos)>len(_chapas.PONTAS)-len(ocupadas):
        raise ValueError('A chapa nao possui uma ponta livre para outra conexao')
    for nome,ancoras in vizinhos.items():
        pontos=[C.data.vertices[_indices_da_assinatura(C,sc)[0]].co for sc,_sn in ancoras]
        _d,ponta=min((sum(abs(p[i]-b) for p in pontos),('x','y')[i]+'_'+lado)
                    for i in (0,1) for b,lado in zip(limites[i],('neg','pos'))
                    if ('x','y')[i]+'_'+lado not in ocupadas)
        ocupadas.add(ponta);grupos[ponta,nome]=ancoras
    return grupos


def _registrar_pares_reais(C, grupos):
    """Conserva o afastamento de C a N no referencial de N: gira com o modulo."""
    destinos=set()
    restricoes = restricoes_adjacencia([C])[C]
    for (ponta,nome),ancoras in grupos.items():
        N=bpy.data.objects.get(nome)
        if (N is None or N is C or nome in destinos or len(ancoras)!=1
                or any(not _indices_da_assinatura(C,sc) or not _indices_da_assinatura(N,sn) for sc,sn in ancoras)):
            raise ValueError('Cada par de objetos permite somente uma solda valida')
        atual=restricoes.get(ponta, (None, 0, 0.))[0]
        if atual is not None and atual is not N:
            raise ValueError('A ponta ja esta soldada a outra chapa')
        destinos.add(nome)
    for (ponta,nome),ancoras in grupos.items():
        N=bpy.data.objects[nome];eixo,lado=ponta.split('_')
        for dono,vizinho in ((C,N),(N,C)):
            for anterior in _chapas.PONTAS:
                if _vizinho_da_ponta(dono,anterior) is vizinho:
                    _chapas._limpar_ponta(dono,anterior)
        if not _chapas._gravar_ligacao(C,eixo,lado,N,0.,0 if lado=='pos' else 1):
            raise ValueError('O par de objetos ja esta soldado')
        C['adj_%s_folga'%ponta]=_folga_com_sinal(C,ponta,N)[0]
        _gravar_ancoras(C,ponta,ancoras)
        inversa=N.matrix_world.inverted().to_3x3()
        C['adj_%s_origens'%ponta]=json.dumps([tuple(inversa@(
            _vertice_da_assinatura(C,sc)-_vertice_da_assinatura(N,sn))) for sc,sn in ancoras])


def _alvos_por_distancia(C, candidatos=None):
    """(alvos, pecas) da conexao por distancia: cada ponta de C ao alcance
    de um vizinho vai so' ATE' a face dele (fecha a folga, nao desliza).
    `candidatos` limita os vizinhos aos alvos selecionados."""
    outras = _chapas._chapas_candidatas(C, candidatos)
    alvos, pecas = [], set()
    eixos = _chapas._eixos(C)
    for i, eixo in enumerate(("x", "y")):
        for lado in ("pos", "neg"):
            achado = _chapas._melhor_vizinho(C, eixo, lado, outras,
                                     _chapas.ALCANCE_CONEXAO_AUTOMATICA)
            if achado is None:
                continue
            N, folga, _face = achado
            pecas.add(N)
            u = eixos[i] * (1 if lado == "pos" else -1)
            dados=_dados_ancoras(C)
            for indice in dados['pontas'][str(i)+lado]:
                p=C.matrix_world@C.data.vertices[indice].co
                alvos.append((dados['assinaturas'][indice],p+u*folga))
    return alvos, pecas | _chapas._vizinhos_por_distancia(C, candidatos=candidatos)


class OBJECT_OT_desassociar(Operator):
    """Desagrega esta peca: todas as quinas dela se soltam e ela sai do modulo"""
    bl_idname = 'object.cabinet_desassociar'
    bl_label = 'Desagregar'
    bl_options = {'REGISTER', 'UNDO'}

    chapa: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        chapa = bpy.data.objects.get(self.chapa)
        if chapa is None or _chapas.MARCA_CHAPA not in chapa:
            self.report({'WARNING'}, 'Peca nao encontrada')
            return {'CANCELLED'}
        if not agregado(chapa) and _portas._modulo_da_chapa(chapa) is None:
            self.report({'INFO'}, "Esta peca ja' estava desagregada")
            return {'CANCELLED'}
        desagregar(chapa)
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


class OBJECT_OT_clique_corrente(Operator):
    """Clique na corrente (desagrega) ou na regua (resetar) com a tecla segurada"""
    bl_idname = 'object.cabinet_clique_corrente'
    bl_label = 'Desagregar pela Corrente'
    bl_options = {'INTERNAL'}

    # O botao nativo da corrente (GIZMO_GT_button_2d) so' aceita clique
    # SEM modificador -- e a corrente so' aparece com Alt/Ctrl/Shift
    # segurado. Este atalho (qualquer modificador, na frente da selecao)
    # pega o clique; fora de uma corrente o evento segue intacto.
    @classmethod
    def poll(cls, context):
        criacao=_conexao_manual[0]
        if criacao and criacao.get('moderna'):
            return (context.mode=='OBJECT' and context.region is not None
                    and context.region.as_pointer()==criacao['regiao']
                    and not _gaveta._eh_area_gaveta(context))
        return _hud._contexto_hud(context)

    def invoke(self, context, event):
        posicao = (event.mouse_region_x, event.mouse_region_y)
        alvo = _alvo_da_corrente(context, posicao)
        if alvo is None:
            return {'PASS_THROUGH'}
        tipo_alvo, corrente, tipo = alvo
        if isinstance(corrente,dict) and corrente.get('criacao'):
            if tipo_alvo=='distancia':
                bpy.ops.object.cabinet_editar_medida_gaveta('INVOKE_DEFAULT',
                    dono='solda_criacao',objeto=corrente['a'].name,propriedade=str(corrente['indice']),
                    valor=(corrente['pontos'][0]-corrente['pontos'][1]).length)
                return {'FINISHED'}
            if tipo_alvo=='botao':
                return bpy.ops.object.cabinet_acao_criacao_solda(
                    acao='%s|%d'%('RESETAR' if tipo=='regua' else 'REMOVER',corrente['indice']))
            return {'PASS_THROUGH'}
        if tipo_alvo=='distancia':
            bpy.ops.object.cabinet_editar_medida_gaveta('INVOKE_DEFAULT',
                dono='solda',objeto=corrente['a'].name,
                propriedade='%s|%d'%(corrente['ponta'],corrente['indice']),
                valor=(corrente['pontos'][0]-corrente['pontos'][1]).length)
            return {'FINISHED'}
        if tipo_alvo == 'puxador':
            # ancora do puxador: arrastar ate' outra borda do grupo
            bpy.ops.object.cabinet_arrastar_puxador(
                'INVOKE_DEFAULT', puxador=corrente.name)
            return {'FINISHED'}
        if tipo_alvo == 'ferragem':
            # controlador da dobradica (borda) ou do pistao (lateral)
            bpy.ops.object.cabinet_arrastar_ferragem(
                'INVOKE_DEFAULT', grupo=corrente.name, tipo=tipo)
            return {'FINISHED'}
        if tipo_alvo == 'ponto_gaveta':
            # quina da frente ou profundidade das gavetas (ima nos vertices)
            bpy.ops.object.cabinet_arrastar_ponto_gaveta(
                'INVOKE_DEFAULT', grupo=corrente.name, indice=tipo)
            return {'FINISHED'}
        if tipo_alvo == 'canto_porta':
            # canto da porta: arrastar ate' outro vertice refaz a porta
            bpy.ops.object.cabinet_arrastar_canto_porta(
                'INVOKE_DEFAULT', grupo=corrente.name, indice=tipo)
            return {'FINISHED'}
        if tipo_alvo == 'bolinha':
            # bolinha branca: arrastar a ancora ate' outro vertice
            bpy.ops.object.cabinet_arrastar_ancora(
                'INVOKE_DEFAULT', chapa=corrente['a'].name,
                ponta=corrente['ponta'], indice=corrente['indice'], lado=tipo)
            return {'FINISHED'}
        if tipo == 'regua':
            # a regua pode perguntar ("vai mudar de medida"): o operador
            # espera o SOLTAR deste clique para abrir o pop-up
            # (este operador nao tem modal: devolver o RUNNING_MODAL do
            # reset aqui o cancelava)
            resposta = bpy.ops.object.cabinet_resetar_distancia(
                'INVOKE_DEFAULT', chapa=corrente['movel'].name,
                esperar_soltar=True)
            _eventos._redesenhar_viewports(context)
            return {'CANCELLED'} if 'CANCELLED' in resposta else {'FINISHED'}
        # O registro e' direcional: a base pode guardar a solda da lateral.
        # A selecao decide a peca que sai, como ja' decide a peca da regua.
        return bpy.ops.object.cabinet_desassociar(
            chapa=(corrente['movel'] if corrente.get('manual') else
                   _peca_da_regua(context,corrente['a'],corrente['b'])).name)


class OBJECT_OT_tecla_corrente(Operator):
    """Segurar a tecla das opcoes mostra a corrente; soltar esconde"""
    bl_idname = 'object.cabinet_tecla_corrente'
    bl_label = 'Mostrar Correntes'
    bl_options = {'INTERNAL'}

    tecla: StringProperty(options={'SKIP_SAVE'})
    apertou: BoolProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        # o evento SEMPRE segue adiante: Alt/Ctrl/Shift continuam valendo
        # para o Blender e para os outros atalhos
        if self.tecla.split('_', 1)[-1] == _opcoes._opcao('tecla_corrente'):
            if _tecla_corrente_segurada[0] != self.apertou:
                _tecla_corrente_segurada[0] = self.apertou
                _eventos._redesenhar_viewports(context)
        return {'PASS_THROUGH'}


# ------------------------------------------ botao Corrente da gaveta
# Regras do usuario (a selecao diz o que o clique faz):
# - UMA peca (individual, nao o grupo): agregada -> "desagregar esse
#   objeto do grupo?"; solta -> "selecionar vertice" direto.
# - o GRUPO (clique no modulo, ou pecas ligadas) -> "desagregar todos
#   os itens deste grupo?".
# - alvo(s) primeiro e, por ULTIMO (o ativo do Blender), a peca de fora:
#   conecta por distancia ate' ALCANCE_CONEXAO_AUTOMATICA; mais longe,
#   "selecionar vertice" so' com os cantos dos alvos.
OP_CORRENTE_OBJETO = 'object.cabinet_corrente_objeto'
# Botoes da gaveta que abrem pop-up ou modal: disparam no SOLTAR, pela
# propria gaveta (interagir_gaveta). Pelo gizmo do icone, o pop-up nascia
# sob o mouse e o RELEASE ja' respondia; e o modal aberto pelo gizmo
# prendia os cliques da gaveta -- o "Confirmar" do pe' nao chegava.
# O "Gerar orcamento" (opcoes) abre o "Salvar como"; o "Usar como
# puxador", o modal do clique na face.
OPERADORES_NO_SOLTAR = {OP_CORRENTE_OBJETO,
                        'object.cabinet_editar_grupo_visual',
                        'object.cabinet_criar_fundo',
                        'object.cabinet_conectar_vertices',
                        'object.cabinet_editar_parede',
                        'object.cabinet_editar_ambientes',
                        'object.cabinet_resetar_distancia',
                        'object.cabinet_exportar_orcamento',
                          'object.cabinet_usar_como_puxador',
                          'object.cabinet_definir_area', 'object.cabinet_aplicar_area',
                          'object.cabinet_internos'}
_desagregar_pendente = [None]    # pecas esperando o "tem certeza?"
_conexao_pendente = [None]       # alvos esperando o "Juntar ao modulo?"
_conexao_manual = [None]         # estado do modo "selecionar vertice"


ATR_VERTICE_SOLDA = 'cabinet_solda_vertice'


def _ancora_estavel(obj, assinatura):
    ids=_indices_da_assinatura(obj,assinatura)
    if not ids:raise ValueError('Ancora apagada ou ambigua; escolha outro vertice')
    i=ids[0]
    if not assinatura.startswith('v'):return assinatura
    if _chapas._malha_e_caixa(obj.data):
        _gravar_cantos(obj)
        return _assinatura_canto(obj,obj.matrix_world@obj.data.vertices[i].co)
    atributo=obj.data.attributes.get(ATR_VERTICE_SOLDA)
    if atributo is None:atributo=obj.data.attributes.new(ATR_VERTICE_SOLDA,'INT','POINT')
    valores=array('i',[0])*len(obj.data.vertices);atributo.data.foreach_get('value',valores)
    proximo=max(valores,default=0)+1
    for j,v in enumerate(valores):
        if v==0:valores[j]=proximo;proximo+=1
    atributo.data.foreach_set('value',valores)
    return 'u%d'%valores[i]


def _guardar_previa_solda(estado):
    if estado.get('backup'):return
    obj=bpy.data.objects.get(estado['origem'])
    co=array('f',[0])*(len(obj.data.vertices)*3);obj.data.vertices.foreach_get('co',co)
    estado['backup']=dict(malha=obj.data.name,co=co,
        matriz=[list(l) for l in obj.matrix_world],
        medidas=[obj.chapa_largura_mm,obj.chapa_comprimento_mm,obj.chapa_espessura_mm],
        filhos_base={o.name:[list(l) for l in o.matrix_basis] for o in obj.children_recursive})


def _restaurar_previa_solda(estado):
    if estado.get('cena') not in (None,bpy.context.scene.as_pointer()):return
    b=estado.get('backup');obj=bpy.data.objects.get(estado.get('origem',''))
    if not b or obj is None:return
    if obj.mode=='EDIT' or obj.data.is_editmode:return
    malha=bpy.data.meshes.get(b['malha'])
    if malha is None or len(malha.vertices)*3!=len(b['co']):return
    ocupado=_chapas._ocupado[0];_chapas._ocupado[0]=True
    try:
        temporaria=obj.data;obj.data=malha
        malha.vertices.foreach_set('co',b['co']);malha.update()
        obj.matrix_world=Matrix(b['matriz'])
        obj.chapa_largura_mm,obj.chapa_comprimento_mm,obj.chapa_espessura_mm=b['medidas']
        bpy.context.view_layer.update()
        for nome,m in b.get('filhos_base',b.get('filhos',{})).items():
            filho=bpy.data.objects.get(nome)
            if filho is not None:
                if 'filhos_base' in b:filho.matrix_basis=Matrix(m)
                else:filho.matrix_world=Matrix(m)
        if temporaria is not malha and temporaria.users==0:bpy.data.meshes.remove(temporaria)
    finally:_chapas._ocupado[0]=ocupado
    _frentes.invalidar(obj);_formas.esquecer();bpy.context.view_layer.update()


def _alvos_previa_solda(estado):
    alvos=[]
    for k,(sc,nome,sn) in enumerate(estado['pares']):
        n=bpy.data.objects.get(nome)
        if n is None:raise ValueError('A chapa de destino nao existe mais')
        alvos.append((sc,_vertice_da_assinatura(n,sn)+Vector(estado['direcoes'][k])*estado['distancias'][k]))
    return alvos


def editar_criacao_solda(valor=None, zerar=False, indice=None):
    estado=_conexao_manual[0]
    if not estado:return 'Nenhuma solda em criacao'
    if valor is not None and (not math.isfinite(valor) or valor<0):return 'Distancia invalida'
    if not estado['pares']:
        estado['distancia_previa']=0. if zerar else valor
        estado['reset_pendente']=zerar
        return None
    anteriores=list(estado['distancias']);zeros=list(estado['zeradas'])
    if indice is not None and not 0 <= indice < len(anteriores):return 'Ancora inexistente'
    if zerar:
        indices=range(len(anteriores)) if indice is None else [indice]
        for k in indices:estado['distancias'][k]=0.;estado['zeradas'][k]=True
    elif valor is not None:
        if not math.isfinite(valor) or valor<0:return 'Distancia invalida'
        estado['distancias'][-1 if indice is None else indice]=valor
    _guardar_previa_solda(estado);_restaurar_previa_solda(estado)
    try:_puxar_por_pares(bpy.data.objects[estado['origem']],_alvos_previa_solda(estado))
    except ValueError as erro:
        estado['distancias']=anteriores;estado['zeradas']=zeros
        _restaurar_previa_solda(estado)
        try:_puxar_por_pares(bpy.data.objects[estado['origem']],_alvos_previa_solda(estado))
        except ValueError:pass    # destino apagado: conservar a geometria original
        return str(erro)
    _eventos._redesenhar_viewports(bpy.context)
    return None


def voltar_criacao_solda(estado):
    _restaurar_previa_solda(estado)
    if estado.get('editar_ancora'):
        estado.pop('editar_ancora');estado['fase']='confirmar'
    elif estado['fase']=='destino':
        estado.update(fase='origem',escolhido=None)
    elif estado['pares']:
        sc,nome,sn=estado['pares'].pop()
        for chave in ('distancias','direcoes','zeradas'):estado[chave].pop()
        origem=bpy.data.objects[estado['origem']]
        estado.update(fase='destino',escolhido=(sc,_vertice_da_assinatura(origem,sc)),aguardar_novo_par=False)
    _preparar_candidatos_conexao(estado)


class OBJECT_OT_acao_criacao_solda(Operator):
    """Controles da solda em criacao, sem gravar undo da previa"""
    bl_idname='object.cabinet_acao_criacao_solda'
    bl_label='Editar Criacao da Solda'
    bl_options={'INTERNAL'}
    acao:StringProperty(options={'SKIP_SAVE'})

    def execute(self,context):
        estado=_conexao_manual[0]
        if estado is None:return {'CANCELLED'}
        if self.acao=='CANCELAR':estado['cancelar']=True
        elif self.acao=='VOLTAR':estado['voltar']=True
        elif self.acao=='ADICIONAR':
            estado.update(fase='origem',escolhido=None,aguardar_novo_par=False)
            _preparar_candidatos_conexao(estado)
        elif self.acao=='RESETAR':
            erro=editar_criacao_solda(zerar=True)
            if erro:self.report({'WARNING'},erro);return {'CANCELLED'}
        elif self.acao.startswith(('RESETAR|','REMOVER|')):
            acao, texto = self.acao.split('|',1)
            k=int(texto)
            if not 0<=k<len(estado['pares']):return {'CANCELLED'}
            if acao=='RESETAR':
                erro=editar_criacao_solda(zerar=True,indice=k)
                if erro:self.report({'WARNING'},erro);return {'CANCELLED'}
            else:
                _restaurar_previa_solda(estado)
                for chave in ('pares','distancias','direcoes','zeradas'):estado[chave].pop(k)
                if estado['pares'] and estado.get('backup'):editar_criacao_solda()
                estado.update(fase='confirmar' if estado['pares'] else 'origem',escolhido=None)
                _preparar_candidatos_conexao(estado)
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}
PERGUNTA_DESAGREGAR_GRUPO = ('Voce tem certeza que deseja desagregar todos '
                             'os itens deste grupo?')
PERGUNTA_DESAGREGAR_OBJETO = ('Voce realmente deseja desagregar esse '
                              'objeto do grupo?')


def _chapas_selecionadas(context):
    return [o for o in getattr(context, 'selected_objects', ()) or ()
            if o.type == 'MESH' and _chapas.MARCA_CHAPA in o]


def _acao_corrente(context, medir=True):
    """(acao, peca, pecas) do botao Corrente pela selecao, ou None:
    ('grupo', None, pecas do grupo), ('desagregar', peca, [peca]),
    ('conectar', peca de fora, alvos ao alcance) ou ('vertices', peca,
    alvos -- vazio = qualquer chapa). Sem `medir` nao procura vizinhos
    (o desenho da gaveta so' precisa saber se e' azul ou cinza)."""
    selecionados = list(getattr(context, 'selected_objects', ()) or ())
    chapas = [o for o in selecionados if o.type == 'MESH' and _chapas.MARCA_CHAPA in o]
    ativo = getattr(context, 'active_object', None)
    if ativo is not None and ativo not in selecionados:
        ativo = None
    if ativo is None and len(chapas) == 1:
        ativo = chapas[0]
    if ativo is None or (_chapas.MARCA_CHAPA not in ativo and _chapas.MARCA_CONJUNTO not in ativo):
        return None
    modulo = ativo if _chapas.MARCA_CONJUNTO in ativo else _portas._modulo_da_chapa(ativo)
    grupo = set(_selecao.familia_de(ativo))
    if modulo is not None:
        grupo |= set(_modulos._chapas_do_conjunto(modulo))
    alvos = [c for c in chapas if c not in grupo]
    if alvos:
        if _chapas.MARCA_CHAPA not in ativo:
            return None          # quem vai ate' o alvo e' UMA peca, nao um modulo
        if not medir:
            return ('conectar', ativo, alvos)
        _pontos, perto = _alvos_por_distancia(ativo, alvos)
        if perto:
            return ('conectar', ativo, alvos)
        return ('vertices', ativo, alvos)
    if _chapas.MARCA_CHAPA in ativo and chapas == [ativo] and not any(
            _chapas.MARCA_CONJUNTO in o for o in selecionados):
        if agregado(ativo) or modulo is not None:
            return ('desagregar', ativo, [ativo])
        return ('vertices', ativo, [])
    pecas = (_modulos._chapas_do_conjunto(modulo) if modulo is not None
             else [c for c in chapas if c in grupo])
    if not pecas:
        return None
    return ('grupo', None, pecas)


def _estado_corrente_objeto(context):
    """True (azul: o clique desagrega) / False (cinza: o clique associa) /
    None (nada que a corrente faca com esta selecao)."""
    acao = _acao_corrente(context, medir=False)
    if acao is None:
        return None
    return acao[0] in ('grupo', 'desagregar')


def _perguntar_desagregar(context, pecas, todos):
    _desagregar_pendente[0] = sorted(o.name for o in pecas)
    op = 'object.cabinet_desagregar_selecao'
    _perguntas._perguntar(context, PERGUNTA_DESAGREGAR_GRUPO if todos
               else PERGUNTA_DESAGREGAR_OBJETO,
               [('Sim, desagregar', 'CHECKMARK', op, {'desagregar': True}),
                ('Nao', 'X', op, {'desagregar': False})])


def _agrupar_soltas(context, C, pecas):
    """A Corrente juntou pecas que nao estao em armario nenhum: viram um
    GRUPO (pedido do usuario). Com armario de um lado, quem manda e' o
    "Juntar ao modulo?" -- aqui nada acontece. Devolve o grupo ou None."""
    pecas = {N for N in pecas if N is not None and _chapas.MARCA_CHAPA in N}
    if (C is None or not pecas or _portas._modulo_da_chapa(C) is not None
            or any(_portas._modulo_da_chapa(N) is not None for N in pecas)):
        return None
    todas = {C} | pecas | set(_modulos.grupo_de(C, simetrico=True))
    return _modulos.agrupar_chapas(context, sorted(todas, key=lambda o: o.name))


# Caixa do nome na gaveta: o grupo ja' nasceu com a sugestao; o texto
# digitado aqui o renomeia (Enter/OK) ou fica a sugestao (Esc/Manter).
_nome_grupo_gaveta = [None]     # {'grupo', 'texto', 'cursor', 'selecionado'}


def _abrir_caixa_nome(conj):
    _nome_grupo_gaveta[0] = {'grupo': conj.name, 'texto': conj.name,
                             'cursor': len(conj.name), 'selecionado': True}
    _perguntas._pergunta_atual[0] = {
        'texto': 'Nome do grupo', 'campo': True, 'na_gaveta': True,
        'opcoes': [('OK', 'CHECKMARK', 'object.cabinet_nomear_grupo',
                    {'digitado': True}),
                   ('Manter', 'X', 'object.cabinet_nomear_grupo',
                    {'manter': True})]}


def _pedir_nome_grupo(context, conj, na_gaveta=None):
    """Pergunta o nome do grupo novo no lugar certo: caixa com campo
    DENTRO da gaveta se o clique veio dela, pop-up se veio da viewport."""
    na_gaveta = _perguntas._na_gaveta[0] if na_gaveta is None else na_gaveta
    if na_gaveta:
        _abrir_caixa_nome(conj)
        if _perguntas._abrir_pergunta(context):
            bpy.ops.object.cabinet_digitar_nome_grupo('INVOKE_DEFAULT')
        _eventos._redesenhar_viewports(context)
    elif _perguntas._abrir_pergunta(context):
        bpy.ops.object.cabinet_nomear_grupo('INVOKE_DEFAULT', grupo=conj.name,
                                            nome=conj.name)


class OBJECT_OT_nomear_grupo(Operator):
    """Da' nome ao grupo (armario): o Empty e a Collection dele"""
    bl_idname = 'object.cabinet_nomear_grupo'
    bl_label = 'Nome do Grupo'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    grupo: StringProperty(options={'SKIP_SAVE', 'HIDDEN'})
    nome: StringProperty(name='Nome', options={'SKIP_SAVE'})
    # OK da caixa da gaveta: vale o texto digitado nela
    digitado: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})
    # "Manter" da caixa: fica a sugestao, so' fecha
    manter: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def execute(self, context):
        estado = _nome_grupo_gaveta[0]
        if self.digitado or self.manter:
            _nome_grupo_gaveta[0] = None
            if estado is None:
                return {'CANCELLED'}
            self.grupo = estado['grupo']
            self.nome = estado['texto'] if self.digitado else ''
        _eventos._redesenhar_viewports(context)
        if self.manter:
            return {'FINISHED'}
        if not _modulos.nomear_grupo(bpy.data.objects.get(self.grupo), self.nome):
            return {'CANCELLED'}
        return {'FINISHED'}


class OBJECT_OT_digitar_nome_grupo(Operator):
    """Digita o nome do grupo na caixa da gaveta (Enter confirma, Esc mantem)"""
    bl_idname = 'object.cabinet_digitar_nome_grupo'
    bl_label = 'Digitar Nome do Grupo'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        if _nome_grupo_gaveta[0] is None:
            return {'CANCELLED'}
        self._area = context.area
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _redesenhar(self, context):
        _eventos._redesenhar_viewports(context)

    def modal(self, context, event):
        estado = _nome_grupo_gaveta[0]
        if estado is None:
            # respondida pelos botoes da caixa (cada um com o seu undo)
            self._redesenhar(context)
            return {'CANCELLED'}
        if event.value != 'PRESS' or event.type in {
                'LEFTMOUSE', 'MIDDLEMOUSE', 'RIGHTMOUSE', 'WHEELUPMOUSE',
                'WHEELDOWNMOUSE', 'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            # o clique vai para a gaveta (OK / Manter) e para a viewport
            return {'PASS_THROUGH'}
        if event.type == 'ESC':
            _nome_grupo_gaveta[0] = _perguntas._pergunta_atual[0] = None
            self._redesenhar(context)
            return {'CANCELLED'}
        if event.type in {'RET', 'NUMPAD_ENTER'}:
            _nome_grupo_gaveta[0] = _perguntas._pergunta_atual[0] = None
            _orcamento._confirmar_campo_gaveta(estado)
            self._redesenhar(context)
            return {'FINISHED'}
        entrada = (context.window_manager.clipboard
                   if event.ctrl and event.type == 'V'
                   else '' if event.ctrl else event.unicode or '')
        if _gaveta_desenho._tecla_no_texto(estado, event.type, entrada, event.ctrl):
            self._redesenhar(context)
        return {'RUNNING_MODAL'}


def _perguntar_juntar(context, origem, alvos, pecas, na_gaveta=None, pares=None, configuracao=None):
    _conexao_pendente[0] = {'origem': origem.name,
                            'alvos': [(s, tuple(q)) for s, q in alvos],
                            'pecas': sorted(o.name for o in pecas),
                            'pares':list(pares or ()), 'configuracao':configuracao}
    op = 'object.cabinet_juntar_modulo'
    _perguntas._perguntar(context, 'Juntar ao modulo?',
               [('Sim, juntar', 'CHECKMARK', op, {'juntar': True}),
                ('Nao', 'X', op, {'juntar': False})], na_gaveta)


def _nomes(objs):
    return json.dumps([o.name for o in objs])


def _objetos_dos_nomes(texto):
    """Lista de objetos de um JSON de nomes; None se vazio (= todos)."""
    if not texto:
        return None
    try:
        nomes = json.loads(texto)
    except ValueError:
        return None
    return [o for o in (bpy.data.objects.get(n) for n in nomes) if o is not None]


class OBJECT_OT_corrente_objeto(Operator):
    """Corrente: agrega ou desagrega pela selecao (azul = agregado). Alvos primeiro, peca de fora por ultimo"""
    bl_idname = OP_CORRENTE_OBJETO
    bl_label = 'Corrente'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.mode == 'OBJECT' and _conexao_manual[0] is None
                and _estado_corrente_objeto(context) is not None)

    def invoke(self, context, event):
        acao = _acao_corrente(context)
        if acao is None:
            self.report({'WARNING'}, 'Selecione a peca (ou os alvos e, por '
                        'ultimo, a peca de fora)')
            return {'CANCELLED'}
        tipo, peca, pecas = acao
        if tipo in ('grupo', 'desagregar'):
            _perguntar_desagregar(context, pecas, tipo == 'grupo')
            return {'FINISHED'}
        if tipo == 'conectar':
            return bpy.ops.object.cabinet_conectar_distancia(
                origem=peca.name, alvos=_nomes(pecas))
        return bpy.ops.object.cabinet_conectar_vertices(
            'INVOKE_DEFAULT', origem=peca.name,
            destinos=_nomes(pecas) if pecas else '')

    def execute(self, context):
        return self.invoke(context, None)


class OBJECT_OT_desagregar_selecao(Operator):
    """Resposta do "tem certeza?": desagrega a peca ou o grupo inteiro"""
    bl_idname = 'object.cabinet_desagregar_selecao'
    bl_label = 'Desagregar'
    bl_options = {'REGISTER', 'UNDO'}

    desagregar: BoolProperty(default=True, options={'SKIP_SAVE'})

    def execute(self, context):
        nomes, _desagregar_pendente[0] = _desagregar_pendente[0], None
        if not nomes or not self.desagregar:
            return {'CANCELLED'}
        pecas = [o for o in (bpy.data.objects.get(n) for n in nomes)
                 if o is not None and _chapas.MARCA_CHAPA in o]
        if not pecas:
            return {'CANCELLED'}
        n = desagregar_grupo(pecas)
        self.report({'INFO'}, '%d peca(s) desagregada(s)' % n)
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


class OBJECT_OT_conectar_distancia(Operator):
    """Liga a peca as vizinhas ao alcance (ate' 5 mm)"""
    bl_idname = 'object.cabinet_conectar_distancia'
    bl_label = 'Conectar por Distancia'
    bl_options = {'REGISTER', 'UNDO'}

    origem: StringProperty(options={'SKIP_SAVE'})
    # JSON com os nomes dos alvos selecionados; vazio = qualquer chapa
    alvos: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        chapa = bpy.data.objects.get(self.origem)
        if chapa is None:
            return {'CANCELLED'}
        alvos, pecas = _alvos_por_distancia(chapa,
                                            _objetos_dos_nomes(self.alvos))
        if not pecas:
            self.report({'WARNING'}, 'Nenhuma peca ao alcance')
            return {'CANCELLED'}
        modulo = next((m for m in (_portas._modulo_da_chapa(N) for N in pecas)
                       if m is not None), None)
        if modulo is not None and _portas._modulo_da_chapa(chapa) != modulo:
            _perguntar_juntar(context, chapa, alvos, pecas)
        else:
            _chapas.associar_por_distancia(chapa, pecas, _chapas.ALCANCE_CONEXAO_AUTOMATICA)
            conj = _agrupar_soltas(context, chapa, pecas)
            if conj is not None:
                _pedir_nome_grupo(context, conj)
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


class OBJECT_OT_recalcular_ancoragem(Operator):
    """Refaz as soldas das chapas selecionadas pelo lugar onde estao agora
(copias do Ctrl+D ganham identidade propria)"""
    bl_idname = 'object.cabinet_recalcular_ancoragem'
    bl_label = 'Recalcular Ancoragem'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(_chapas_selecionadas(context))

    def execute(self, context):
        chapas = _chapas_selecionadas(context)
        context.view_layer.update()         # posicoes de agora (invariante 6)
        n = _chapas.recalcular_ancoragem(chapas)
        _eventos._redesenhar_viewports(context)
        self.report({'INFO'}, "%d solda(s) refeita(s) em %d chapa(s)"
                    % (n, len(chapas)))
        return {'FINISHED'}


class OBJECT_OT_juntar_modulo(Operator):
    """Registra a ancoragem atual e, ao juntar, filia a peca sem move-la"""
    bl_idname = 'object.cabinet_juntar_modulo'
    bl_label = 'Juntar ao Modulo'
    bl_options = {'REGISTER', 'UNDO'}

    juntar: BoolProperty(default=True, options={'SKIP_SAVE'})

    def execute(self, context):
        pendente, _conexao_pendente[0] = _conexao_pendente[0], None
        if not pendente:
            return {'CANCELLED'}
        chapa = bpy.data.objects.get(pendente['origem'])
        if chapa is None:
            return {'CANCELLED'}
        pecas = {bpy.data.objects.get(n) for n in pendente['pecas']}
        try:
            pares=pendente.get('pares')
            configuracao=pendente.get('configuracao')
            if configuracao:
                _plano_ancoras_reais(chapa,pares)
                _puxar_por_pares(chapa,_alvos_previa_solda(configuracao))
            alvos=([(sc,_vertice_da_assinatura(bpy.data.objects.get(nome),sn)) for sc,nome,sn in pares]
                   if pares else [(s,Vector(q)) for s,q in pendente['alvos']])
            juntar_conexao(chapa,alvos,pecas,self.juntar,pares)
        except ValueError as erro:
            self.report({'WARNING'},str(erro));return {'CANCELLED'}
        if self.juntar:
            conj = _agrupar_soltas(context, chapa, pecas)
            if conj is not None:
                if pares:_registrar_pares_reais(chapa,_plano_ancoras_reais(chapa,pares))
                _pedir_nome_grupo(context, conj)
        if configuracao:
            plano=_plano_ancoras_reais(chapa,pares)
            _registrar_pares_reais(chapa,plano)
            for (ponta,nome),ancoras in plano.items():
                chapa['adj_%s_manual'%ponta]=True
                zeros=[];direcoes=[]
                for sc,sn in ancoras:
                    k=pares.index((sc,nome,sn));n=bpy.data.objects[nome]
                    zeros.append((0.,0.,0.) if configuracao['zeradas'][k] else
                        tuple(n.matrix_world.inverted().to_3x3()@(
                        _vertice_da_assinatura(chapa,sc)-_vertice_da_assinatura(n,sn))))
                    direcoes.append(tuple(n.matrix_world.to_3x3().normalized().inverted()@Vector(configuracao['direcoes'][k])))
                chapa['adj_%s_origens'%ponta]=json.dumps(zeros)
                chapa['adj_%s_direcoes'%ponta]=json.dumps(direcoes)
            modulo=_portas._modulo_da_chapa(chapa)
            if modulo is not None:_atualizar_modulo(modulo)
            if not context.selected_objects:
                _hud._selecionar_chapa_hud(context,chapa,individual=True)
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


class OBJECT_OT_confirmar_conexao(Operator):
    """Termina a escolha de vertices (o mesmo que Enter)"""
    bl_idname = 'object.cabinet_confirmar_conexao'
    bl_label = 'Confirmar Conexao'

    @classmethod
    def poll(cls, context):
        estado=_conexao_manual[0]
        return estado is not None and (not estado.get('moderna') or
            estado.get('fase')=='confirmar' and bool(estado.get('pares')))

    def execute(self, context):
        _conexao_manual[0]['confirmar'] = True
        # confirmado pelo botao da gaveta: "Juntar ao modulo?" vem nela
        _conexao_manual[0]['pela_gaveta'] = _perguntas._na_gaveta[0]
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


def _desenhar_conexao_manual():
    """Cantos clicaveis, o escolhido e as pontas ja' conectadas."""
    estado = _conexao_manual[0]
    regiao = getattr(bpy.context, 'region', None)
    if estado is None or regiao is None or regiao.as_pointer() != estado['regiao']:
        return
    rv3d = bpy.context.region_data
    realce = _hud._cor_realce_hud()
    cor = _hud._cor_linhas_hud(bpy.context)
    escala = max(1.0, bpy.context.preferences.system.ui_scale)

    def tela(ponto):
        return view3d_utils.location_3d_to_region_2d(regiao, rv3d, ponto)

    def bolinha(ponto, raio, rgba):
        p = tela(ponto)
        if p is None:
            return
        volta = [p + Vector((math.cos(i * math.tau / 16),
                             math.sin(i * math.tau / 16))) * raio
                 for i in range(17)]
        tris = []
        for a, b in zip(volta, volta[1:]):
            tris += [p, a, b]
        shader.uniform_float('color', rgba)
        batch_for_shader(shader, 'TRIS', {'pos': tris}).draw(shader)

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        # as bolinhas so' com poucas pecas (a origem ou os alvos escolhidos):
        # a cena inteira projetada a cada quadro travava o destino
        if not estado.get('moderna') and (estado['fase'] == 'origem' or estado.get('destinos')):
            for _obj, _s, ponto in _candidatos_conexao(estado):
                bolinha(ponto, 4 * escala, (*cor[:3], 0.8))
        for s, nome, sn in estado['pares']:
            origem = bpy.data.objects.get(estado['origem'])
            alvo = bpy.data.objects.get(nome)
            if origem is None or alvo is None:
                continue
            a = tela(_vertice_da_assinatura(origem, s))
            b = tela(_vertice_da_assinatura(alvo, sn))
            if a is not None and b is not None:
                shader.uniform_float('color', realce)
                batch_for_shader(shader, 'TRIS', {'pos': _puxadores._quad_2d(
                    a, b, 2.0 * escala)}).draw(shader)
                bolinha(_vertice_da_assinatura(origem, s), 6 * escala, realce)
                bolinha(_vertice_da_assinatura(alvo, sn), 6 * escala, realce)
        if estado.get('escolhido'):
            bolinha(estado['escolhido'][1], 7 * escala, realce)
        if estado.get('hover'):
            bolinha(estado['hover'][2], 7 * escala, (*realce[:3], 0.6))
        if estado.get('moderna'):
            _desenhar_bolinhas_correntes(bpy.context)
            feedback = _feedback_snap_criacao(estado)
            if feedback:
                ponto, inicio = feedback
                p = tela(ponto)
                if p is not None:
                    shader.bind()
                    _hud._bolinha_2d(shader,p,10*escala,(1.,1.,1.,.9))
                    _hud._bolinha_2d(shader,p,5*escala,realce)
                    texto='Snap nativo'
                    if inicio is not None:
                        a=tela(inicio)
                        if a is not None:
                            shader.uniform_float('color',realce)
                            batch_for_shader(shader,'TRIS',{'pos':_puxadores._quad_2d(a,p,2*escala)}).draw(shader)
                        texto += ' | '+_opcoes._texto_medida((ponto-inicio).length*1000)
                    _hud._caixa_texto_hud(p.x+14*escala,p.y+14*escala,texto,round(12*escala),escala)
    finally:
        gpu.state.blend_set('NONE')


def _feedback_snap_criacao(estado):
    # O cursor e' o resultado do translate nativo, sem outro motor de snap.
    if not estado.get('snap_pendente') or estado.get('cursor') is None:return None
    escolhido=estado.get('escolhido')
    return Vector(estado['cursor']), Vector(escolhido[1]) if escolhido else None


def _candidatos_conexao(estado):
    """[(objeto, assinatura, ponto)] clicaveis na fase atual. Le vertices:
    so' para DESENHAR poucas pecas; o clique e' do snap nativo."""
    if 'alvos_snap' not in estado:_preparar_candidatos_conexao(estado)
    objs=[bpy.data.objects.get(n) for n in estado.get('alvos_snap',())]
    return [(o,'v%d'%v.index,o.matrix_world@v.co) for o in objs if o is not None for v in o.data.vertices]


def _preparar_candidatos_conexao(estado):
    """As pecas que o snap nativo pode pegar na fase atual: a chapa de
    origem, ou as outras chapas (o destino). Nenhum vertice e' lido aqui."""
    origem = bpy.data.objects.get(estado['origem'])
    if estado['fase'] == 'origem':
        pecas = ([origem] if origem is not None else
                 [o for nome in estado.get('origens', ())
                  if (o := bpy.data.objects.get(nome)) is not None and o.visible_get()])
    else:
        # alvos selecionados antes da peca de fora: so' os cantos deles
        destinos = _objetos_dos_nomes(estado.get('destinos'))
        pecas = [o for o in (bpy.data.objects if destinos is None else destinos)
                 if o is not origem and o.type == 'MESH' and _chapas.MARCA_CHAPA in o
                 and o.visible_get()]
    if estado.get('editar_ancora') and estado['editar_ancora'][1]=='b':
        pecas=[bpy.data.objects.get(estado['pares'][estado['editar_ancora'][0]][1])]
    estado.update(alvos_snap=[o.name for o in pecas if o is not None],
                  iniciar_snap=not estado.get('moderna') and not estado.get('aguardar_novo_par',False))


def _vertice_do_snap(estado, ponto):
    """O Blender escolheu o ponto; o KDTree em cache SO' da peca atingida
    (caixa local descarta as outras) recupera seu MeshVertex."""
    if ponto is None:return None
    ponto=Vector(ponto)
    for nome in estado.get('alvos_snap',()):
        obj=bpy.data.objects.get(nome)
        if obj is None or obj.type!='MESH':continue
        local=obj.matrix_world.inverted()@ponto
        caixa=[Vector(c) for c in obj.bound_box]
        if any(local[k]<min(c[k] for c in caixa)-1e-4 or local[k]>max(c[k] for c in caixa)+1e-4
               for k in range(3)):continue
        dados=_cache_ancoras[0].get(obj.data.name)
        if dados and dados['n']==len(obj.data.vertices) and dados['arvore'] is not None:
            _co,i,_d=dados['arvore'].find(local)
        else:
            # Biblioteca recem-anexada: consulta nativa da face, sem montar
            # uma arvore Python de TODOS os vertices no clique.
            hit,_co,_n,face=obj.closest_point_on_mesh(local)
            if not hit or face<0:continue
            i=min(obj.data.polygons[face].vertices,key=lambda i:(obj.data.vertices[i].co-local).length_squared)
        p=obj.matrix_world@obj.data.vertices[i].co
        if (p-ponto).length<=1e-5:return obj,'v%d'%i,p
    return None


class OBJECT_OT_conectar_vertices(Operator):
    """Criar solda: escolha o canto da chapa de origem e o canto de destino. Enter confirma"""
    bl_idname = 'object.cabinet_conectar_vertices'
    bl_label = 'Criar Solda'
    bl_options = {'REGISTER'}

    origem: StringProperty(options={'SKIP_SAVE'})
    # JSON com os nomes dos alvos; vazio = cantos de qualquer chapa
    destinos: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and _conexao_manual[0] is None and _gavetas._estado_criacao() is None

    def invoke(self, context, event):
        chapa = (bpy.data.objects.get(self.origem) if self.origem
                 else context.object)
        if chapa is None or not any(m in chapa for m in
                                   (_chapas.MARCA_CHAPA, _chapas.MARCA_CONJUNTO)):
            self.report({'WARNING'}, 'Selecione uma chapa ou modulo para criar a solda')
            return {'CANCELLED'}
        modulo = chapa if _chapas.MARCA_CONJUNTO in chapa else None
        if not self.origem and getattr(chapa, 'chapa_modo', '') == 'GRUPO':
            modulo = modulo or _portas._modulo_da_chapa(chapa)
        origens = _modulos._chapas_do_conjunto(modulo) if modulo is not None else [chapa]
        if not origens:
            self.report({'WARNING'}, 'O modulo nao possui chapas para soldar')
            return {'CANCELLED'}
        alvo = _importacao._viewport_alvo(context)
        if alvo is None:
            self.report({'ERROR'}, 'Sem viewport 3D para clicar')
            return {'CANCELLED'}
        self._area, self._regiao, self._rv3d = alvo
        _conexao_manual[0] = {'origem': '' if modulo is not None else chapa.name,
                              'origens': [o.name for o in origens], 'pares': [],
                              'destinos': self.destinos,
                              'pela_gaveta': bool(_perguntas._na_gaveta[0]),
                              'fase': 'origem', 'escolhido': None,
                              'hover': None, 'confirmar': False,
                              'regiao': self._regiao.as_pointer(),'snap_nativo':True,
                              'etapa':'SOLDA','elementos_snap':('VERTEX',),
                              'moderna':True,'distancias':[],'direcoes':[],'zeradas':[],
                              'cena':context.scene.as_pointer()}
        self._w=_conexao_manual[0]
        _preparar_candidatos_conexao(self._w)
        _timer_conexao[0]=context.window_manager.event_timer_add(.03,window=context.window)
        _handler_conexao[0] = bpy.types.SpaceView3D.draw_handler_add(
            _desenhar_conexao_manual, (), 'WINDOW', 'POST_PIXEL')
        self._area.header_text_set(
            "Criar solda: canto da chapa de origem, depois canto de destino | "
            "Clique/arraste: snap nativo | Alt: ancora | Enter: confirmar | "
            "Direito/Esc: cancelar | Backspace/Ctrl+Z: voltar")
        context.window_manager.modal_handler_add(self)
        _eventos._redesenhar_viewports(context)
        return {'RUNNING_MODAL'}

    def _encerrar(self, context):
        estado=encerrar_conexao_nativa(context)
        _eventos._redesenhar_viewports(context)
        return estado

    def _na_viewport(self, event):
        dx, dy = event.mouse_x - self._regiao.x, event.mouse_y - self._regiao.y
        return 0 <= dx < self._regiao.width and 0 <= dy < self._regiao.height

    def _sob_mouse(self, event):
        estado=_conexao_manual[0]
        ponto=estado.get('cursor')
        return _vertice_do_snap(estado,ponto) if ponto is not None else None

    def _terminar(self, context):
        estado = self._encerrar(context)
        origem = bpy.data.objects.get(estado['origem'])
        if origem is None or not estado['pares']:
            return {'CANCELLED'}
        alvos = [(s, _vertice_da_assinatura(bpy.data.objects[nome], sn))
                 for s, nome, sn in estado['pares']
                 if nome in bpy.data.objects]
        # destino apagado pelo Outliner durante o modal: None quebrava a pergunta
        pecas = {bpy.data.objects[nome] for _s, nome, _sn in estado['pares']
                 if nome in bpy.data.objects}
        if estado.get('moderna'):
            configuracao={k:estado[k] for k in ('origem','pares','distancias','direcoes','zeradas')}
            _perguntar_juntar(context,origem,alvos,pecas,estado.get('pela_gaveta',False),estado['pares'],configuracao=configuracao)
        else:
            _perguntar_juntar(context, origem, alvos, pecas,
                              estado.get('pela_gaveta', False),estado['pares'])
        return {'FINISHED'}

    def modal(self, context, event):
        try:return self._modal(context,event)
        except Exception:
            self._encerrar(context);raise

    def _modal(self, context, event):
        estado = _conexao_manual[0]
        if estado is None:
            return {'CANCELLED'}
        if estado.get('cancelar') or context.mode!='OBJECT':
            self._encerrar(context);return {'CANCELLED'}
        if estado.pop('voltar',False):
            voltar_criacao_solda(estado);return {'RUNNING_MODAL'}
        confirmado=estado.pop('ponto_confirmado',None)
        if confirmado is not None:
            estado['snap_pendente']=False
            if estado.get('confirmar'):return self._terminar(context)
            alvo=_vertice_do_snap(estado,confirmado[0])
            if alvo is not None:
                obj,s,ponto=alvo
                if estado.get('moderna'):s=_ancora_estavel(obj,s)
                if estado.get('editar_ancora'):
                    k,lado=estado.pop('editar_ancora');sc,nome,sn=estado['pares'][k]
                    estado['pares'][k]=(s,nome,sn) if lado=='a' else (sc,obj.name,s)
                    estado['fase']='confirmar'
                    _restaurar_previa_solda(estado)
                    if estado.get('backup'):editar_criacao_solda()
                    else:
                        sc,nome,sn=estado['pares'][k]
                        d=_vertice_da_assinatura(bpy.data.objects[estado['origem']],sc)-_vertice_da_assinatura(bpy.data.objects[nome],sn)
                        estado['distancias'][k]=d.length
                        if d.length>1e-8:estado['direcoes'][k]=tuple(d.normalized())
                elif estado['fase']=='origem':estado.update(origem=obj.name,fase='destino',escolhido=(s,ponto),aguardar_novo_par=False,soltar_confirma=False)
                else:
                    if any(nome==obj.name for _sc,nome,_sn in estado['pares']):
                        self.report({'WARNING'},'Cada par de objetos permite somente uma solda')
                        estado['iniciar_snap']=True
                        return {'RUNNING_MODAL'}
                    estado['pares'].append((estado['escolhido'][0],obj.name,s))
                    if estado.get('moderna'):
                        p=Vector(estado['escolhido'][1]);d=p-ponto
                        estado['distancias'].append(d.length)
                        estado['direcoes'].append(tuple(d.normalized() if d.length>1e-8 else _chapas._eixos(obj)[2]))
                        estado['zeradas'].append(False)
                    estado.update(fase='confirmar' if estado.get('moderna') else 'origem',escolhido=None,aguardar_novo_par=True)
                    if estado.get('distancia_previa') is not None:
                        editar_criacao_solda(estado['distancia_previa'],zerar=estado.get('reset_pendente',False))
                _preparar_candidatos_conexao(estado)
            else:estado['iniciar_snap']=True
            self._area.tag_redraw();return {'RUNNING_MODAL'}
        if estado.get('confirmar') and not estado.get('snap_pendente'):
            return self._terminar(context)
        if estado.get('snap_pendente'):return {'PASS_THROUGH'}
        if _gaveta._edicao_gaveta[0] is not None:return {'PASS_THROUGH'}
        if event.type in {'ESC','RIGHTMOUSE'} and event.value=='PRESS':
            self._encerrar(context);return {'CANCELLED'}
        if event.value=='PRESS' and (event.type=='BACK_SPACE' or event.type=='Z' and event.ctrl):
            voltar_criacao_solda(estado);self._area.tag_redraw();return {'RUNNING_MODAL'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            if estado.get('moderna') and estado['fase']!='confirmar':return {'RUNNING_MODAL'}
            return self._terminar(context)
        if event.type == 'ESC' and event.value == 'PRESS':
            self._encerrar(context)
            return {'CANCELLED'}
        if not self._na_viewport(event):
            return {'PASS_THROUGH'}     # a gaveta (Confirmar) segue viva
        if event.type == 'MOUSEMOVE':
            if estado.pop('iniciar_snap',False):
                _gavetas.AssistenteDoVao._iniciar_snap_nativo(self,context)
            estado['hover'] = None
            self._area.tag_redraw()
            # O gizmo nativo precisa do movimento para reconhecer o hover antes do clique.
            return {'PASS_THROUGH'} if estado.get('moderna') else {'RUNNING_MODAL'}
        if estado.get('moderna') and event.type=='LEFTMOUSE' and event.value=='PRESS':
            if not event.alt:
                with context.temp_override(area=self._area,region=self._regiao):
                    controle=_alvo_da_corrente(bpy.context,(event.mouse_x-self._regiao.x,event.mouse_y-self._regiao.y))
                if controle and controle[0] in {'botao','distancia'}:return {'PASS_THROUGH'}
            if event.alt and estado['pares']:
                correntes=[]
                origem=bpy.data.objects[estado['origem']]
                for k,(sc,nome,sn) in enumerate(estado['pares']):
                    correntes.append(dict(indice=k,pontos=[_vertice_da_assinatura(origem,sc),_vertice_da_assinatura(bpy.data.objects[nome],sn)]))
                with context.temp_override(area=self._area,region=self._regiao):
                    corrente,lado=_bolinha_sob_mouse(bpy.context,
                        (event.mouse_x-self._regiao.x,event.mouse_y-self._regiao.y),correntes)
                if corrente is None:return {'RUNNING_MODAL'}
                estado['editar_ancora']=(corrente['indice'],lado)
                estado['fase']='origem' if lado=='a' else 'destino'
                _preparar_candidatos_conexao(estado)
            elif estado['fase']=='confirmar':return {'RUNNING_MODAL'}
            estado['soltar_confirma']=True
            _gavetas.AssistenteDoVao._iniciar_snap_nativo(self,context)
            return {'RUNNING_MODAL'}
        if event.type=='LEFTMOUSE' and event.value=='PRESS' and estado.get('aguardar_novo_par'):
            estado.update(aguardar_novo_par=False,soltar_confirma=True)
            _gavetas.AssistenteDoVao._iniciar_snap_nativo(self,context)
            return {'RUNNING_MODAL'}
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            if estado['fase'] == 'destino':
                estado.update(fase='origem', escolhido=None)
            elif estado['pares']:
                estado['pares'].pop()
            _preparar_candidatos_conexao(estado)
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._encerrar(context)


def _desenhar_bolinhas_correntes(context):
    """Bolinha branca em cada ponta das linhas das correntes (Alt): e' a
    ancora, arrastavel; a sob o mouse cresce e ganha o realce."""
    correntes = _correntes_hud(context)
    if not correntes or _arraste_ancora[0] is not None:
        return
    escala = max(1.0, context.preferences.system.ui_scale)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    shader.bind()
    realce = _hud._cor_realce_hud()
    for corrente in correntes:
        for lado, ponto in _bolinhas_da_corrente(context, corrente).items():
            acesa = _chave_bolinha(corrente, lado) == _bolinha_hover[0]
            if acesa:
                _hud._bolinha_2d(shader, ponto, 8 * escala, realce)
            _hud._bolinha_2d(shader, ponto, (6 if acesa else 5) * escala,
                        (1.0, 1.0, 1.0, 1.0))
    for corrente in correntes:
        campo=_campo_distancia_corrente(context,corrente)
        if campo:
            x,y,_w,_h,texto,_valor=campo
            _hud._caixa_texto_hud(x,y,texto,round(12*escala),escala)
    gpu.state.blend_set('NONE')


# ------------------------------------------------ arrastar a ancora
_arraste_ancora = [None]         # estado do arraste da bolinha


def _candidatos_ancora(estado):
    """[(assinatura, ponto)] dos vertices onde a bolinha pode cair: os da
    chapa (lado 'a', QUAL vertice e' soldado) ou os do vizinho (lado
    'b', ONDE ele encosta)."""
    C = bpy.data.objects.get(estado['chapa'])
    N = _vizinho_da_ponta(C, estado['ponta']) if C is not None else None
    if N is None:
        return []
    return _ancoras_da_malha(C if estado['lado'] == 'a' else N)


_handler_ancora = [None]         # desenho do arraste da bolinha


def _desenhar_arraste_ancora():
    estado = _arraste_ancora[0]
    regiao = getattr(bpy.context, 'region', None)
    if estado is None or regiao is None or regiao.as_pointer() != estado['regiao']:
        return
    rv3d = bpy.context.region_data
    escala = max(1.0, bpy.context.preferences.system.ui_scale)
    realce = _hud._cor_realce_hud()
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    tela = lambda p: view3d_utils.location_3d_to_region_2d(regiao, rv3d, p)
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        for _s, ponto in _candidatos_ancora(estado):
            p = tela(ponto)
            if p is not None:
                _hud._bolinha_2d(shader, p, 4 * escala, (0.75, 0.75, 0.75, 0.9))
        fixo = tela(estado['fixo'])
        solto = tela(estado['ponto'])      # o cursor do snap nativo
        if fixo is not None and solto is not None:
            shader.uniform_float('color', realce)
            batch_for_shader(shader, 'TRIS', {'pos': _puxadores._quad_2d(
                fixo, solto, 3.0 * escala)}).draw(shader)
        if fixo is not None:
            _hud._bolinha_2d(shader, fixo, 5 * escala, (1.0, 1.0, 1.0, 1.0))
        if solto is not None:
            _hud._bolinha_2d(shader, solto, 8 * escala, realce)
            _hud._bolinha_2d(shader, solto, 6 * escala, (1.0, 1.0, 1.0, 1.0))
    finally:
        gpu.state.blend_set('NONE')


def _terminar_ancora_solda(remover_timer=True):
    estado = _gavetas.terminar_cursor_nativo(_arraste_ancora)
    if _handler_ancora[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler_ancora[0], 'WINDOW')
        _handler_ancora[0] = None
    if remover_timer and bpy.app.timers.is_registered(_acompanhar_ancora_solda):
        bpy.app.timers.unregister(_acompanhar_ancora_solda)
    return estado


def _acompanhar_ancora_solda():
    if _gavetas.acompanhar_cursor_nativo(_arraste_ancora, 'OBJECT_OT_cabinet_mover_ancora_solda'):
        return 1.0 / 60.0
    _terminar_ancora_solda(remover_timer=False)     # Esc: tira o desenho
    return None


def _preparar_ancora_solda(context, C, ponta, N, indice, lado):
    """O cursor parte da bolinha e o snap NATIVO so' enxerga a peca onde
    ela pode cair (antes: os vertices projetados em Python a cada movimento)."""
    sc, sn = _ancoras_da_ligacao(C, ponta, N)[indice]
    alvo, movel, fixo = (C, (C, sc), (N, sn)) if lado == 'a' else (N, (N, sn), (C, sc))
    _gavetas.iniciar_cursor_nativo(
        context, _arraste_ancora,
        {'regiao': context.region.as_pointer(), 'chapa': C.name, 'ponta': ponta,
         'lado': lado, 'indice': indice, 'peca': alvo.name,
         'fixo': _vertice_da_assinatura(*fixo)},
        _vertice_da_assinatura(*movel), lambda o: o != alvo)
    return dict(_gavetas.PARAMETROS_CURSOR_NATIVO, snap_elements={'VERTEX'})


class OBJECT_OT_confirmar_ancora_solda(Operator):
    bl_idname = 'object.cabinet_confirmar_ancora_solda'
    bl_label = 'Confirmar Ancora da Solda'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        if not _arraste_ancora[0]:
            return {'CANCELLED'}
        ponto = context.scene.cursor.location.copy()
        estado = _terminar_ancora_solda()
        P = bpy.data.objects.get(estado['peca'])
        dados = _dados_ancoras(P) if P is not None else None
        if not dados or dados['arvore'] is None:
            return {'CANCELLED'}
        # o vertice que o snap nativo pegou: KDTree em cache da peca
        _co, i, _d = dados['arvore'].find(P.matrix_world.inverted() @ ponto)
        if (P.matrix_world @ P.data.vertices[i].co - ponto).length > 1e-5:
            return {'CANCELLED'}           # soltou longe de um vertice
        op = SimpleNamespace(chapa=estado['chapa'], ponta=estado['ponta'],
                             indice=estado['indice'], lado=estado['lado'],
                             report=self.report)
        return OBJECT_OT_arrastar_ancora._gravar(op, dados['assinaturas'][i])


class OBJECT_OT_mover_ancora_solda(Macro):
    bl_idname = 'object.cabinet_mover_ancora_solda'
    bl_label = 'Ajustar Ancora da Solda'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}


def registrar_macro_ancora():
    OBJECT_OT_mover_ancora_solda.define('TRANSFORM_OT_translate')
    OBJECT_OT_mover_ancora_solda.define('OBJECT_OT_cabinet_confirmar_ancora_solda')


class OBJECT_OT_arrastar_ancora(Operator):
    """Arraste a bolinha da corrente ate' outro vertice: troca a ancora da solda (a chapa vai la' pela regua)"""
    bl_idname = 'object.cabinet_arrastar_ancora'
    bl_label = 'Ajustar Ancora da Solda'
    bl_options = {'INTERNAL'}

    chapa: StringProperty(options={'SKIP_SAVE'})
    ponta: StringProperty(options={'SKIP_SAVE'})
    indice: IntProperty(options={'SKIP_SAVE'})
    lado: StringProperty(default='b', options={'SKIP_SAVE'})

    def invoke(self, context, event):
        C = bpy.data.objects.get(self.chapa)
        N = _vizinho_da_ponta(C, self.ponta) if C is not None else None
        if N is None or context.region is None:
            return {'CANCELLED'}
        if not 0 <= self.indice < len(_ancoras_da_ligacao(C, self.ponta, N)):
            return {'CANCELLED'}
        parametros = _preparar_ancora_solda(context, C, self.ponta, N,
                                            self.indice, self.lado)
        _handler_ancora[0] = bpy.types.SpaceView3D.draw_handler_add(
            _desenhar_arraste_ancora, (), 'WINDOW', 'POST_PIXEL')
        try:
            resultado = bpy.ops.object.cabinet_mover_ancora_solda(
                'INVOKE_DEFAULT', TRANSFORM_OT_translate=parametros)
        except Exception:
            _terminar_ancora_solda()
            raise
        if 'RUNNING_MODAL' not in resultado:
            _terminar_ancora_solda()
            return {'CANCELLED'}
        bpy.app.timers.register(_acompanhar_ancora_solda, first_interval=0.0)
        return {'FINISHED'}

    def _gravar(self, alvo):
        C = bpy.data.objects.get(self.chapa)
        N = _vizinho_da_ponta(C, self.ponta) if C is not None else None
        if N is None:
            return {'CANCELLED'}
        ancoras = list(_ancoras_da_ligacao(C, self.ponta, N))
        sc, sn = ancoras[self.indice]
        if C.get('adj_%s_manual'%self.ponta):alvo=_ancora_estavel(C if self.lado=='a' else N,alvo)
        novo = (alvo, sn) if self.lado == 'a' else (sc, alvo)
        if novo == ancoras[self.indice]:
            return {'CANCELLED'}
        ancoras[self.indice] = novo
        _gravar_ancoras(C, self.ponta, ancoras)
        if C.get('adj_%s_manual'%self.ponta):
            d=_vertice_da_assinatura(C,novo[0])-_vertice_da_assinatura(N,novo[1])
            if d.length>1e-8:
                direcoes=json.loads(C['adj_%s_direcoes'%self.ponta])
                direcoes[self.indice]=tuple(N.matrix_world.to_3x3().normalized().inverted()@d.normalized())
                C['adj_%s_direcoes'%self.ponta]=json.dumps(direcoes)
        self.report({'INFO'}, 'Ancora trocada; a regua leva a chapa ate' + "' la'")
        return {'FINISHED'}


# ------------------------------------------ resetar distancia
# Pedido do usuario: "volta para a origem da solda". O botao da gaveta
# (regua) fica AZUL quando a peca/modulo ativo tem solda fora da origem
# (folga diferente da gravada). Quem se mexe sai da SELECAO:
# - chapa unica ativa: ELA se move ate' todas as soldas dela voltarem; se
#   para isso precisar mudar de medida (o modulo mudou muito), pergunta;
# - modulo (grupo) ativo: o GRUPO se adapta a chapa -- as pontas soldadas
#   esticam ate' ela, e o modulo se redimensiona se preciso.
# Na viewport (Alt) a regua de cada quina faz o mesmo, pela peca da linha.
OP_RESETAR_DISTANCIA = 'object.cabinet_resetar_distancia'
TOL_RESET_DISTANCIA = 0.0005     # m: abaixo disto a solda esta' na origem
PERGUNTA_RESET = ('A chapa vai mudar de medida para voltar a solda. '
                  'Mover mesmo assim?')
_pergunta_reset = ['']           # chapa esperando a resposta


def _folga_com_sinal(C, ponta, N):
    """(folga em m, eixo u, extremo) como o `_chapas._melhor_vizinho` grava:
    positiva = afastada, negativa = invadindo o vizinho."""
    eixo, lado = ponta.split('_')
    ex, ey, _ez = _chapas._eixos(C)
    u = ex if eixo == 'x' else ey
    hx, hy, _hz = _chapas._meias(C)
    h = hx if eixo == 'x' else hy
    extremo = _chapas._centro(C).dot(u) + (h if lado == 'pos' else -h)
    face = int(C.get('adj_%s_face' % ponta, 0 if lado == 'pos' else 1))
    alvo = _chapas._faixa(N, u)[face]
    return (alvo - extremo if lado == 'pos' else extremo - alvo), u, extremo


def _pontas_fora_do_lugar(chapas):
    """Soldas que tocam `chapas` fora da origem (qualquer desvio)."""
    return _ligacoes_adjacencia(chapas, TOL_RESET_DISTANCIA)


# ---- ancoras da solda (pedido do usuario)
# Cada solda liga 2 vertices da chapa a 2 vertices do vizinho. De fabrica
# sao os cantos mais perto (`_pares_da_ligacao`); com Alt o usuario arrasta
# a bolinha de cada ponta para outro vertice das duas pecas e a escolha
# fica gravada em `adj_<ponta>_ancoras` ("+-+|-++", chapa|vizinho). So'
# troca a ancora: a chapa vai la' na regua. Vertices que nao cabem na
# mesma reta (um em cima, outro embaixo) DEFORMAM a ponta da chapa: o
# canto e o do outro lado da espessura vao juntos, a chapa fica torta.
def _ancoras_gravadas(C, ponta):
    lista = C.get('adj_%s_ancoras' % ponta)
    if not lista:
        return None
    try:
        ancoras = [tuple(str(x).split('|')) for x in lista]
    except Exception:
        return None
    return ancoras if all(len(a) == 2 for a in ancoras) else None


def _ancoras_da_ligacao(C, ponta, N, u=None, extremo=None):
    """[(assinatura em C, assinatura em N)]: as gravadas ou as de fabrica."""
    gravadas = _ancoras_gravadas(C, ponta)
    if gravadas:
        return [(sc,sn) for sc,sn in gravadas if _indices_da_assinatura(C,sc) and _indices_da_assinatura(N,sn)]
    if u is None:
        i=0 if ponta.startswith('x') else 1
        u=_chapas._eixos(C)[i]
        extremo=_chapas._centro(C).dot(u)+_chapas._meias(C)[i]*(1 if ponta.endswith('pos') else -1)
    return [(sc,sn) for _p,q,sc,sn in _pares_da_ligacao(C,u,extremo,N)]


def _parceiro_espessura(P, assinatura):
    """A ancora do OUTRO lado da espessura (Z local): no canto, o sinal de
    Z trocado; num vertice qualquer, o mais perto dele na face oposta."""
    if not assinatura.startswith(('v', 'u')):
        return assinatura[:2] + ('-' if assinatura[2] == '+' else '+')
    indices = _indices_da_assinatura(P, assinatura)
    if not indices:
        return assinatura
    co = P.data.vertices[indices[0]].co
    secao=_chapas._secao_espessura(P.data)
    if secao:
        grupo=secao['grupos'][indices[0]];lado=secao['lados'][indices[0]]
        parceiro=next((i for i,g in enumerate(secao['grupos']) if g==grupo and secao['lados'][i]!=lado),None)
        if parceiro is not None:return 'v%d'%parceiro
    opostos = [v for v in P.data.vertices if v.co.z * co.z < 0]
    if not opostos:
        return assinatura
    v = min(opostos, key=lambda v: (v.co.x - co.x) ** 2 + (v.co.y - co.y) ** 2)
    return 'v%d' % v.index


def _ancoras_da_malha(P):
    """[(ancora, ponto)] de TODOS os vertices de P onde a bolinha pode
    cair: os 8 cantos da caixa, ou cada vertice da malha modelada (o
    chanfro da print do usuario nao era alcancavel so' com os cantos)."""
    if P.type == 'MESH' and not _chapas._malha_e_caixa(P.data):
        mundo = P.matrix_world
        return [('v%d' % v.index, mundo @ v.co) for v in P.data.vertices]
    return [(s, _vertice_da_assinatura(P, s))
            for s in (a + b + c for a in '+-' for b in '+-' for c in '+-')]


def _gravar_ancoras(C, ponta, ancoras):
    C['adj_%s_ancoras' % ponta] = ['%s|%s' % a for a in ancoras]


def _origens_ancoras(C, ponta):
    """Dados numericos persistidos; juntas antigas conservam a folga escalar."""
    try:
        valores=json.loads(C.get('adj_%s_origens'%ponta,'null'))
        if valores is None or len(valores)!=len(_ancoras_gravadas(C,ponta) or []):return None
        if not all(len(v)==3 and all(math.isfinite(float(x)) for x in v) for v in valores):return None
        return [Vector(v) for v in valores]
    except (ValueError,TypeError):return None


def editar_distancia_solda(nome,propriedade,valor):
    """A ancora final permanece fixa; o afastamento vive nos eixos dela."""
    try:
        ponta,indice=propriedade.split('|');indice=int(indice)
        c=bpy.data.objects.get(nome);n=_vizinho_da_ponta(c,ponta) if c else None
        if n is None or not c.get('adj_%s_manual'%ponta):return 'Solda manual nao encontrada'
        if not math.isfinite(valor) or valor<0:return 'Distancia invalida'
        ancoras=_ancoras_gravadas(c,ponta) or []
        if not 0<=indice<len(ancoras):return 'Ancora da solda nao encontrada'
        direcoes=json.loads(c['adj_%s_direcoes'%ponta])
        direcao=(n.matrix_world.to_3x3().normalized()@Vector(direcoes[indice])).normalized()
        if not all(math.isfinite(v) for v in direcao) or direcao.length<.5:return 'Direcao da solda invalida; escolha outra ancora'
        alvos=[(sc,_vertice_da_assinatura(n,sn)+direcao*valor) if k==indice else
               (sc,_vertice_da_assinatura(c,sc)) for k,(sc,sn) in enumerate(ancoras)]
        _puxar_por_pares(c,alvos)
        modulo=_portas._modulo_da_chapa(c)
        if modulo is not None:_atualizar_modulo(modulo)
    except (ValueError,KeyError,IndexError,TypeError) as erro:return str(erro)
    return None


def diagnostico_soldas(obj):
    """Uma ancora invalida conserva os metadados e exige escolha explicita."""
    if obj is None:return ''
    chapas=_modulos._chapas_do_conjunto(obj) if _chapas.MARCA_CONJUNTO in obj else [obj]
    for c in chapas:
        for ponta in _chapas.PONTAS:
            if not c.get('adj_%s_manual'%ponta):continue
            n=_vizinho_da_ponta(c,ponta)
            if n is None:return 'Destino da solda removido'
            if any(not _indices_da_assinatura(c,sc) or not _indices_da_assinatura(n,sn)
                   for sc,sn in (_ancoras_gravadas(c,ponta) or [])):
                return 'Ancora da solda removida ou ambigua'
    return ''


def _desvio_ancora(C, ponta, N, indice, sc, sn):
    """Diferenca ate' a origem cadastrada, compartilhada pela HUD e pelo reset."""
    origens=_origens_ancoras(C,ponta)
    if origens is not None:
        afastamento=N.matrix_world.to_3x3()@origens[indice]
    else:
        u=_chapas._eixos(C)[0 if ponta.startswith('x') else 1]
        afastamento=u*(-1 if ponta.endswith('pos') else 1)*float(C.get('adj_%s_folga'%ponta,0.))
    return _vertice_da_assinatura(N,sn)+afastamento-_vertice_da_assinatura(C,sc)


# Cada vertice da caixa guarda o canto de ORIGEM num atributo: deformada
# pelas ancoras, um canto pode cruzar a origem da peca (a lateral entorta
# a espessura inteira) e o sinal da coordenada passava a apontar o vertice
# ERRADO (teste: ancora 13,5 mm fora). O atributo anda com o vertice.
ATRIBUTO_CANTO = 'cabinet_canto'


def _codigo_assinatura(assinatura):
    return sum(1 << i for i, c in enumerate(assinatura) if c == '+')


def _gravar_cantos(P):
    """Marca os 8 vertices da caixa com o canto de cada um (pelo lado em
    que estao do centro dela -- vale enquanto ela nao entortou)."""
    malha = getattr(P, 'data', None)
    if malha is None or len(malha.vertices) != 8:
        return
    centro = sum((v.co for v in malha.vertices), Vector()) / 8.0
    atributo = (malha.attributes.get(ATRIBUTO_CANTO)
                or malha.attributes.new(ATRIBUTO_CANTO, 'INT', 'POINT'))
    for v in malha.vertices:
        atributo.data[v.index].value = _codigo_assinatura(''.join(
            '+' if c > m else '-' for c, m in zip(v.co, centro)))


def _indices_da_assinatura(P, assinatura):
    """Indice do vertice da ancora: 'v12' = o vertice 12 da malha (malha
    modelada, ex. o chanfro); canto '+-+' = o do atributo de canto (so' na
    caixa de 8 vertices -- numa malha que ganhou vertices o atributo vem 0
    nos novos); sem ele, pelos sinais no referencial da peca."""
    if P is None or P.type != 'MESH':
        return []
    if assinatura.startswith('u'):
        atributo=P.data.attributes.get(ATR_VERTICE_SOLDA)
        if atributo is None:return []
        try:codigo=int(assinatura[1:])
        except ValueError:return []
        valores=array('i',[0])*len(atributo.data);atributo.data.foreach_get('value',valores)
        return [valores.index(codigo)] if valores.count(codigo)==1 else []
    if assinatura.startswith('v'):
        try:
            indice = int(assinatura[1:])
        except ValueError:
            return []
        return [indice] if 0 <= indice < len(P.data.vertices) else []
    atributo = P.data.attributes.get(ATRIBUTO_CANTO)
    if (atributo is not None and len(P.data.vertices) == 8
            and len(atributo.data) == 8):
        codigo = _codigo_assinatura(assinatura)
        achados = [i for i, d in enumerate(atributo.data) if d.value == codigo]
        if achados:
            return achados[:1]
    sinais = [1.0 if c == '+' else -1.0 for c in assinatura]
    candidatos = [v for v in P.data.vertices
                  if all(c * s > 0 for c, s in zip(v.co, sinais))]
    if not candidatos:
        return []
    return [max(candidatos, key=lambda v: sum(
        c * s for c, s in zip(v.co, sinais))).index]


def _vertice_da_assinatura(P, assinatura):
    """O vertice REAL (mundo) da ancora: a chapa deformada pelas ancoras
    sai do canto nominal das props."""
    indices = _indices_da_assinatura(P, assinatura)
    if not indices:raise ValueError('O vertice da ancora nao existe mais')
    return P.matrix_world @ P.data.vertices[indices[0]].co


def _medida_solda(C, ponta, N, restricoes=None):
    """(delta, residuos) da solda C->N: `delta` = quanto a ponta de C tem
    que andar PARA FORA para voltar a origem; `residuos` = [(assinatura,
    vetor)] do que sobra por vertice quando as ancoras nao cabem numa
    reta (vazio sem ancoras gravadas)."""
    folga, u, _extremo = _folga_com_sinal(C, ponta, N)
    memorizada = float(C.get('adj_%s_folga' % ponta, 0.0))
    ancoras = _ancoras_gravadas(C, ponta)
    if not ancoras:
        residuos = []
        extras = _restricoes_da_ligacao(C, ponta, N)[1:]
        if extras and restricoes is None:
            restricoes = restricoes_adjacencia([C, N])
        for origem, p, destino, face, gap in extras:
            if restricoes.get(origem, {}).get(p) != (destino, face, gap):
                continue
            eixo, d = _delta_restricao(origem, p, destino, face, gap)
            residuos.append(('', eixo*d))
        return folga - memorizada, residuos
    sentido = u if ponta.endswith('pos') else -u
    itens = [(sc, _desvio_ancora(C,ponta,N,k,sc,sn)) for k,(sc, sn) in enumerate(ancoras)
              if _indices_da_assinatura(C,sc) and _indices_da_assinatura(N,sn)]
    if not itens:return 0.,[]
    delta = sum(d.dot(sentido) for _s, d in itens) / len(itens)
    return delta, [(sc, d - sentido * delta) for sc, d in itens]


def _tamanho_desvio(delta, residuos):
    return max([abs(delta)] + [r.length for _s, r in residuos])


def _delta_restricao(C, ponta, N, face, folga):
    u = _chapas._eixos(C)[0 if ponta.startswith('x') else 1]
    extremo = _chapas._centro(C).dot(u) + _chapas._meias(C)[0 if ponta.startswith('x') else 1] * (
        1 if ponta.endswith('pos') else -1)
    atual = _chapas._faixa(N, u)[face] - extremo
    return u, (atual if ponta.endswith('pos') else -atual) - folga


def _pares_reset_ancoras(C, ponta, N, lado='a'):
    """Destinos calculados juntos: uma ancora nao altera o calculo da seguinte."""
    peca=C if lado=='a' else N
    pares=[]
    for k,(sc,sn) in enumerate(_ancoras_gravadas(C,ponta) or []):
        if not _indices_da_assinatura(C,sc) or not _indices_da_assinatura(N,sn):continue
        desvio=_desvio_ancora(C,ponta,N,k,sc,sn)
        assinatura,d=(sc,desvio) if lado=='a' else (sn,-desvio)
        pares.append((assinatura,_vertice_da_assinatura(peca,assinatura)+d))
    return pares


def _validar_reset_ancoras(M):
    pares=[]
    for C in bpy.data.objects:
        if C.type!='MESH' or _chapas.MARCA_CHAPA not in C:continue
        for ponta in _chapas.PONTAS:
            N=_vizinho_da_ponta(C,ponta)
            if N is not None and M in (C,N):
                pares.extend(_pares_reset_ancoras(C,ponta,N,'a' if M is C else 'b'))
    if pares:_movimentos_por_pares(M,pares)


def _deformar_ancoras(C, ponta, N, lado='a'):
    """Encosta os vertices ancorados: lado 'a' leva os de C (a ponta) ate'
    os do vizinho; lado 'b' leva os de N ate' os de C -- e' a peca que se
    move (a ativa) que entorta. Cada canto vai junto com o do outro lado
    da espessura dele: a espessura nao muda, a chapa fica torta."""
    ancoras = _ancoras_gravadas(C, ponta)
    if not ancoras:
        return False
    peca = C if lado == 'a' else N
    _deltas,movimentos=_movimentos_por_pares(peca,_pares_reset_ancoras(C,ponta,N,lado))
    movimentos={i:d for i,d in movimentos.items() if d.length>=TOL_RESET_DISTANCIA}
    mudou=bool(movimentos)
    if mudou:
        if peca.data.users>1:peca.data=peca.data.copy()
        if peca.data.attributes.get(ATRIBUTO_CANTO) is None:
            _gravar_cantos(peca)    # marca a referencia antes de deformar
        for i,d in movimentos.items():peca.data.vertices[i].co+=d
        peca.data.update()
        bpy.context.view_layer.update()
    return mudou


def resetar_ponta(C, ponta):
    """Leva a ponta `ponta` de C ate' a folga memorizada com o vizinho;
    a outra ponta fica parada e a chapa estica (ou encolhe). Com ancoras
    gravadas, estica pela media e deforma o resto (`_deformar_ancoras`)."""
    N = _vizinho_da_ponta(C, ponta)
    if N is None:
        return False
    if _origens_ancoras(C,ponta) is not None:
        alvos=[(sc,_vertice_da_assinatura(C,sc)+_desvio_ancora(C,ponta,N,k,sc,sn))
               for k,(sc,sn) in enumerate(_ancoras_gravadas(C,ponta))
               if _indices_da_assinatura(C,sc) and _indices_da_assinatura(N,sn)]
        if not alvos or all((p-_vertice_da_assinatura(C,s)).length<TOL_RESET_DISTANCIA for s,p in alvos):return False
        _puxar_por_pares(C,alvos)
        return True
    if C.get('adj_%s_restricoes'%ponta) and not _ancoras_gravadas(C, ponta):
        plano = _plano_reset_chapa(C, ligacao=(C, ponta))
        if plano is None:
            return False
        _aplicar_reset_chapa(C, plano, ligacao=(C, ponta))
        return True
    eixo, lado = ponta.split('_')
    _folga, u, extremo = _folga_com_sinal(C, ponta, N)
    delta, residuos = _medida_solda(C, ponta, N)
    hx, hy, _hz = _chapas._meias(C)
    h = hx if eixo == 'x' else hy
    fixo = extremo - 2 * h if lado == 'pos' else extremo + 2 * h
    novo = extremo + delta * (1 if lado == 'pos' else -1)
    comprimento = abs(novo - fixo)
    if comprimento < 0.001:
        return False
    if abs(delta) < TOL_RESET_DISTANCIA:
        return _deformar_ancoras(C, ponta, N) or bool(residuos)
    centro = _chapas._centro(C)
    _chapas._ocupado[0] = True
    try:
        if eixo == 'x':
            C.chapa_largura_mm = comprimento * 1000.0
        else:
            C.chapa_comprimento_mm = comprimento * 1000.0
    finally:
        _chapas._ocupado[0] = False
    _chapas._definir_centro(C, centro + u * ((novo + fixo) / 2 - centro.dot(u)))
    _chapas.gerar_malha_chapa(C)
    bpy.context.view_layer.update()
    _deformar_ancoras(C, ponta, N)
    return True


def resetar_pontas(escolhidas):
    """[(chapa, ponta)] -> quantas voltaram; os modulos se reacomodam."""
    escolhidas=list(escolhidas)
    # Nao deixar as primeiras juntas aplicadas se uma posterior for inviavel.
    for C,ponta in escolhidas:
        N=_vizinho_da_ponta(C,ponta)
        if N is not None:
            _movimentos_por_pares(C,_pares_reset_ancoras(C,ponta,N))
    n, modulos = 0, set()
    for C, ponta in escolhidas:
        if resetar_ponta(C, ponta):
            n += 1
            modulo = _portas._modulo_da_chapa(C)
            if modulo is not None:
                modulos.add(modulo)
    for modulo in modulos:
        _atualizar_modulo(modulo)
    return n


def _restricoes_reset(M, ligacao=None):
    """[(eixo de M, 'min'/'max', deslocamento em m)] que cada solda de M
    pede para voltar a origem -- as que ja' estao nela pedem 0 (ancoras).
    Devolve tambem se alguma esta' fora."""
    eixos = _chapas._eixos(M)
    restricoes, fora = [], False
    efetivas = restricoes_adjacencia(bpy.data.objects)
    for C in bpy.data.objects:
        if C.type != 'MESH' or _chapas.MARCA_CHAPA not in C:
            continue
        for ponta in _chapas.PONTAS:
            if ligacao is not None and (C, ponta) != ligacao:
                continue
            N = _vizinho_da_ponta(C, ponta)
            if N is None or M not in (C, N):
                continue
            ancorada = bool(_ancoras_gravadas(C, ponta))
            descricoes = _restricoes_da_ligacao(C, ponta, N)
            for origem, p, destino, face, gap in (descricoes[:1] if ancorada else descricoes):
                if efetivas.get(origem, {}).get(p) != (destino, face, gap):
                    continue
                if ancorada:
                    _folga, u, _extremo = _folga_com_sinal(C, ponta, N)
                    delta, residuos = _medida_solda(C, ponta, N, efetivas)
                else:
                    u, delta = _delta_restricao(origem, p, destino, face, gap)
                    residuos = []
                fora = fora or _tamanho_desvio(delta, residuos) >= TOL_RESET_DISTANCIA
                positiva = p.endswith('pos')
                sentido = u if positiva else -u
                if M is origem:
                    i = 0 if p[0] == 'x' else 1
                    lado = 'max' if positiva else 'min'
                    vetor = sentido * delta
                else:
                    i = max(range(3), key=lambda k: abs(eixos[k].dot(u)))
                    mesmo = eixos[i].dot(u) > 0
                    lado = (('min' if face == 0 else 'max') if mesmo
                            else ('max' if face == 0 else 'min'))
                    vetor = -sentido * delta
                restricoes.append((i, lado, vetor.dot(eixos[i]), ancorada))
    return restricoes, fora


def _plano_reset_chapa(M, ligacao=None):
    """{'lados': [(d_min, d_max)] por eixo de M, 'muda_medida'} para M
    voltar as soldas a origem, ou None se ja' estao todas nela. Lados
    opostos pedindo deslocamentos diferentes = esticar (muda a medida);
    a espessura nunca estica: ali vale a media."""
    # Afastamentos 3D iguais pedem uma translacao rigida, inclusive no eixo
    # tangente a solda. A folga escalar antiga nao representava esse movimento.
    restricoes, fora = _restricoes_reset(M, ligacao)
    if not fora:return None
    vetores=[]
    for C in bpy.data.objects:
        if C.type!='MESH' or _chapas.MARCA_CHAPA not in C:continue
        for ponta in _chapas.PONTAS:
            if ligacao is not None and (C, ponta) != ligacao:continue
            N=_vizinho_da_ponta(C,ponta)
            if N is None or M not in (C,N):continue
            if _origens_ancoras(C,ponta) is None:continue
            vetores.extend(_desvio_ancora(C,ponta,N,k,sc,sn)*(1 if M is C else -1)
                for k,(sc,sn) in enumerate(_ancoras_gravadas(C,ponta))
                if _indices_da_assinatura(C,sc) and _indices_da_assinatura(N,sn))
    if vetores and all((v-vetores[0]).length<1e-6 for v in vetores):
        d=sum(vetores,Vector())/len(vetores)
        eixos=_chapas._eixos(M)
        if all(ancorada or abs(d.dot(eixos[i])-valor)<TOL_RESET_DISTANCIA
               for i,_lado,valor,ancorada in restricoes):
            return {'lados':[(d.dot(u),d.dot(u)) for u in eixos],'muda_medida':False}
    lados, muda = [], False
    def do_lado(i, qual):
        # Num mesmo lado, as soldas NORMAIS mandam no movimento inteiro; as
        # ancoradas so' valem se forem as unicas -- o resto delas a
        # deformacao resolve. Media das duas tirava a base do lugar para
        # atender meio caminho do tampo ancorado.
        todas = [(d, ancorada) for k, lado, d, ancorada in restricoes
                 if k == i and lado == qual]
        normais = [d for d, ancorada in todas if not ancorada]
        return normais or [d for d, _a in todas]

    for i in range(3):
        mins = do_lado(i, 'min')
        maxs = do_lado(i, 'max')
        d_min = sum(mins) / len(mins) if mins else None
        d_max = sum(maxs) / len(maxs) if maxs else None
        if d_min is None and d_max is None:
            lados.append((0.0, 0.0))
            continue
        d_min = d_max if d_min is None else d_min
        d_max = d_min if d_max is None else d_max
        if abs(d_max - d_min) >= TOL_RESET_DISTANCIA:
            if i == 2:
                d_min = d_max = (d_min + d_max) / 2
            else:
                muda = True
        lados.append((d_min, d_max))
    return {'lados': lados, 'muda_medida': muda}


def _aplicar_reset_chapa(M, plano, ligacao=None):
    _validar_reset_ancoras(M)
    eixos = _chapas._eixos(M)
    centro = _chapas._centro(M)
    medidas = [M.chapa_largura_mm, M.chapa_comprimento_mm]
    for i, (d_min, d_max) in enumerate(plano['lados']):
        centro = centro + eixos[i] * ((d_min + d_max) / 2)
        if i < 2:
            medidas[i] += (d_max - d_min) * 1000.0
    _chapas._ocupado[0] = True
    try:
        M.chapa_largura_mm, M.chapa_comprimento_mm = medidas
    finally:
        _chapas._ocupado[0] = False
    _chapas._definir_centro(M, centro)
    if plano['muda_medida']:_chapas.gerar_malha_chapa(M)
    bpy.context.view_layer.update()
    # o que as ancoras pedem e a translacao nao resolve: DEFORMA a peca
    # que se move -- a ponta dela, ou a face dela se ela e' o vizinho
    for C in bpy.data.objects:
        if C.type != 'MESH' or _chapas.MARCA_CHAPA not in C:
            continue
        for ponta in _chapas.PONTAS:
            if ligacao is not None and (C, ponta) != ligacao:
                continue
            N = _vizinho_da_ponta(C, ponta)
            if N is not None and M in (C, N):
                _deformar_ancoras(C, ponta, N, 'a' if M is C else 'b')
    modulo = _portas._modulo_da_chapa(M)
    if modulo is not None:
        _atualizar_modulo(modulo)


def _soldas_de(P):
    """Quantas soldas P tem e quantas estao fora da origem."""
    total = fora = 0
    restricoes = restricoes_adjacencia(bpy.data.objects)
    for C in bpy.data.objects:
        if C.type != 'MESH' or _chapas.MARCA_CHAPA not in C:
            continue
        for ponta in _chapas.PONTAS:
            N = _vizinho_da_ponta(C, ponta)
            if N is None or P not in (C, N):
                continue
            total += 1
            if _tamanho_desvio(*_medida_solda(C, ponta, N, restricoes)) >= TOL_RESET_DISTANCIA:
                fora += 1
    return total, fora


def _peca_afastada(a, b):
    """Das duas pecas da solda, a que se AFASTOU: todas as soldas dela
    estao fora da origem (na print do usuario, a lateral)."""
    def razao(P):
        total, fora = _soldas_de(P)
        return fora / total if total else 0.0
    return a if razao(a) > razao(b) else b


def _peca_da_regua(context, a, b):
    """A peca que a regua da linha a-b passa ao reset: a chapa unica
    ativa, se for uma das duas; senao a que se afastou."""
    alvo = _hud._alvo_hud(context)
    if alvo is not None and alvo[1] == 'INDIVIDUAL' and alvo[0] in (a, b):
        return alvo[0]
    return _peca_afastada(a, b)


def _modo_reset(context, nome=''):
    """('CHAPA', M, None) ou ('GRUPO', pecas, foco) pela selecao ativa;
    `nome` = a peca da linha clicada na viewport. None sem item."""
    alvo = _hud._alvo_hud(context)
    foco = bpy.data.objects.get(nome) if nome else None
    if alvo is None:
        if foco is not None and _chapas.MARCA_CHAPA in foco:
            return ('CHAPA', foco, None)
        return None
    obj, modo, chapas = alvo
    if modo == 'INDIVIDUAL':
        return ('CHAPA', foco if foco is not None else obj, None)
    return ('GRUPO', chapas, foco)


def _soldas_do_grupo(pecas, foco=None):
    ligacoes = _pontas_fora_do_lugar(pecas)
    if foco is not None:
        ligacoes = [l for l in ligacoes if foco in (l['a'], l['b'])]
    return ligacoes


def _estado_resetar(context):
    """True (azul: ha' solda fora da origem) ou None (apagado)."""
    try:
        modo = _modo_reset(context)
    except (ReferenceError, AttributeError):
        return None
    if modo is None:
        return None
    if modo[0] == 'CHAPA':
        return True if _plano_reset_chapa(modo[1]) is not None else None
    return True if _soldas_do_grupo(modo[1]) else None


class OBJECT_OT_resetar_distancia(Operator):
    """Resetar distancia: volta as soldas para a origem. Chapa ativa: ela se move; modulo ativo: o modulo se adapta a chapa"""
    bl_idname = OP_RESETAR_DISTANCIA
    bl_label = 'Resetar Distancia'
    bl_options = {'REGISTER', 'UNDO'}

    chapa: StringProperty(options={'SKIP_SAVE'})
    forcar: BoolProperty(options={'SKIP_SAVE'})
    cancelar: BoolProperty(options={'SKIP_SAVE'})
    # Chamado de um PRESS (regua com Alt): o `event` do bpy.ops ja' pode
    # trazer o RELEASE do mesmo clique (visto no log), entao quem chama
    # avisa que o soltar ainda vem.
    esperar_soltar: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and _conexao_manual[0] is None

    def _vai_perguntar(self, context):
        modo = _modo_reset(context, self.chapa)
        if self.forcar or modo is None or modo[0] != 'CHAPA':
            return False
        plano = _plano_reset_chapa(modo[1])
        return bool(plano and plano['muda_medida'])

    def invoke(self, context, event):
        # Pop-up aberto no PRESS nasce sob o mouse e o RELEASE do mesmo
        # clique ja' responde (visto no botao Corrente): espera o soltar.
        apertando = self.esperar_soltar or (
            event is not None and event.type == 'LEFTMOUSE'
            and event.value == 'PRESS')
        if apertando and self._vai_perguntar(context):
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        return self.execute(context)

    def modal(self, context, event):
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return self.execute(context)
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            return {'CANCELLED'}
        return {'PASS_THROUGH'}

    def execute(self, context):
        if self.cancelar:
            _pergunta_reset[0] = ''
            return {'CANCELLED'}
        modo = _modo_reset(context, self.chapa)
        if modo is None:
            self.report({'WARNING'}, 'Selecione a chapa ou o modulo')
            return {'CANCELLED'}
        if modo[0] == 'CHAPA':
            M = modo[1]
            plano = _plano_reset_chapa(M)
            if plano is None:
                self.report({'INFO'}, "As soldas ja' estao na origem")
                return {'CANCELLED'}
            if plano['muda_medida'] and not self.forcar:
                _pergunta_reset[0] = M.name
                _perguntas._perguntar(context, PERGUNTA_RESET, [
                    ('Sim, mover', 'CHECKMARK', OP_RESETAR_DISTANCIA,
                     {'chapa': M.name, 'forcar': True}),
                    ('Nao', 'X', OP_RESETAR_DISTANCIA, {'cancelar': True})])
                return {'CANCELLED'}
            _pergunta_reset[0] = ''
            try:
                _aplicar_reset_chapa(M, plano)
            except ValueError as e:
                self.report({'WARNING'}, str(e))
                return {'CANCELLED'}
            self.report({'INFO'}, '%s voltou a origem da solda' % M.name)
        else:
            ligacoes = _soldas_do_grupo(modo[1], modo[2])
            if not ligacoes:
                self.report({'INFO'}, "As soldas ja' estao na origem")
                return {'CANCELLED'}
            try:
                n = resetar_pontas([(l['a'], l['ponta']) for l in ligacoes])
            except ValueError as e:     # ancoras manuais em conflito
                self.report({'WARNING'}, str(e))
                return {'CANCELLED'}
            self.report({'INFO'}, '%d ponta(s) voltaram a solda' % n)
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}
