"""Weld/adjacency chains: detach, connect, anchors, ruler distance reset
and naming groups created by the Chain tool."""

import bpy, bmesh, math, json, gpu, blf
from array import array
from gpu_extras.batch import batch_for_shader
from bpy.props import BoolProperty, StringProperty, IntProperty
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree
from bpy_extras import view3d_utils
from bpy.types import Operator, Macro
from types import SimpleNamespace

# Used only at runtime (circular imports): __init__ binds these
# aliases after loading all modules (`_ligar_modulos`).
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
_cache_ancoras = [{}]  # Names/numbers/native KDTree, never RNA.
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

# ------------------------------------------- adjacency chains
# Adjacency/WELD links a panel END to another panel's FACE and stores
# the current gap as weld origin. Each link associates actual vertex
# pairs; older formats could repeat corners.
# - Show only while holding the options key, Alt by default.
# - Show ALL welded item corners displaced from origin by more than
# LIMIAR_CORRENTE_VIEWPORT, previously only the camera-nearest one.
# - Each line has a chain to detach the whole object (`desagregar`)
# and a ruler on its right to restore the weld (`cabinet_resetar_distancia`).
LIMIAR_CORRENTE_VIEWPORT = 0.005     # Deviation from weld origin in m.
RAIO_CORRENTE_PX = 14.0
VAO_BOTOES_CORRENTE_PX = 13.0        # Chain on left, ruler on right.
TECLAS_CORRENTE = ('LEFT_ALT', 'RIGHT_ALT', 'LEFT_CTRL', 'RIGHT_CTRL',
                   'LEFT_SHIFT', 'RIGHT_SHIFT')
_tecla_corrente_segurada = [False]


def _correntes_visiveis():
    return (_opcoes._opcao('tecla_corrente') == 'SEMPRE'
            or _tecla_corrente_segurada[0])


def _assinatura_canto(C, p):
    """Identify point p as C's corner by SIGN in panel coordinates ('+-+'),
    stable through panel resizing/movement."""
    local = C.matrix_world.inverted() @ p
    return ''.join('+' if v > 0 else '-' for v in local)


def _canto_da_assinatura(C, assinatura):
    """Inverse of `_assinatura_canto`: C's corner in world space."""
    meias = _chapas._meias(C)
    local = Vector([(1 if s == '+' else -1) * m
                    for s, m in zip(assinatura, meias)])
    return C.matrix_world @ local


def _pares_da_ligacao(C, u, extremo, N):
    """Actual pair: the endpoint vertex nearest the neighbor."""
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
    """Parts linked to C by adjacency in either direction."""
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
    """The single edge preserves legacy axial fittings at both ends."""
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
    """Compute the map ONCE per adjustment, without reverse-link searches per panel."""
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
                    # The endpoint stored on the object takes precedence over a legacy
                    # reverse descriptor; never depend on Outliner order.
                    prioridade = (not (origem is c and p == ponta),
                                  c.get('chapa_uid', ''), c.name, ponta)
                    chave = (origem, p)
                    if chave not in prioridades or prioridade < prioridades[chave]:
                        prioridades[chave] = prioridade
                        resultado[origem][p] = (destino, face, folga)
    return resultado


def agregado(C):
    """Is it attached to any part? Determines the Chain button's blue state."""
    return bool(_ligados_a(C))


def _ligacoes_adjacencia(chapas_item, limiar=None, somente_manuais=False):
    """Links touching the item whose gap differs from the stored weld ORIGIN
    by at least `limiar` m (default LIMIAR_CORRENTE_VIEWPORT). Adjacency
    is stored only on the touching part, endpoint -> neighbor, so scan
    the scene: an external neighbor may own the link."""
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
                continue            # At weld origin: no chain.
            ancoras = _ancoras_da_ligacao(C, ponta, N, u, extremo)
            pares = [(_vertice_da_assinatura(C, sc),
                      _vertice_da_assinatura(N, sn), sc) for sc, sn in ancoras]
            # With stored anchors, each pair has its OWN deviation: hide pairs
            # already touching. Otherwise the line remained on the vertex,
            # overlapping its dot and buttons in the user's screenshot.
            gravadas=_ancoras_gravadas(C,ponta)
            soltos = ([manual or _desvio_ancora(C,ponta,N,gravadas.index((sc,sn)),sc,sn).length >= limiar
                       for sc,sn in ancoras] if gravadas else [True] * len(pares))
            ligacoes.append({'a': C, 'b': N, 'ponta': ponta,
                             'folga': folga, 'desvio': desvio,
                             'ancoras': ancoras, 'pares': pares,
                             'soltos': soltos,'manual':manual})
    return ligacoes


def _correntes_hud(context):
    """Chains for ALL welded HUD-item corners away from origin: one per
    vertex pair, with midpoint in pixels and the part moved by the ruler
    in 'movel'."""
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
                continue            # This pair already touches: hide it.
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
    """Old files also show only one weld per object pair."""
    por_par = {}
    for corrente in sorted(correntes, key=lambda c: (
            (c['pontos'][1]-c['pontos'][0]).length_squared,
            c['a'].name, c['b'].name, c.get('ponta', ''), c.get('indice', 0))):
        chave = tuple(sorted((corrente['a'].name, corrente['b'].name)))
        por_par.setdefault(chave, corrente)
    return list(por_par.values())


def _vertices_mais_proximos(C, N):
    """Native WORLD query only during registration/migration, never redraw."""
    if not C.data.vertices or not N.data.vertices:
        raise ValueError("The panel has no vertices for the joint")
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
    """One edge per unordered pair, retaining old scenes' origins.

    Explicit library migration may record the smallest current gap.
    Scene compatibility must never redefine a displaced panel as origin.
    """
    pecas = {o for o in pecas if o.type == 'MESH' and _chapas.MARCA_CHAPA in o}
    if _eventos._desfazendo[0] or any(o.data.is_editmode for o in pecas):
        raise ValueError("Wait for editing or undo to finish before updating joints")
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
                    # A deleted reference remains diagnosable; never silently
                    # substitute a nearby vertex.
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
    """Proposal for ONE cabinet; changes neither its links nor geometry."""
    candidatos=[];invalidas=[]
    for c in pecas:
        for ponta in _chapas.PONTAS:
            n=_vizinho_da_ponta(c,ponta)
            if n is None:continue
            for indice,(sc,sn) in enumerate(_ancoras_gravadas(c,ponta) or _ancoras_da_ligacao(c,ponta,n)):
                try:p,q=_vertice_da_assinatura(c,sc),_vertice_da_assinatura(n,sn)
                except ValueError:
                    invalidas.append(dict(origem=c.name,ponta=ponta,indice=indice,motivo="Invalid anchor"));continue
                candidatos.append(dict(origem=c.name,destino=n.name,ponta=ponta,indice=indice,
                    par=_par_qualidade_ancoras(c,n),
                    assinatura=sc,alvo=sn,ponto=tuple(p),final=tuple(q),distancia=(p-q).length,
                    raio=min(.025,max(c.chapa_espessura_mm,n.chapa_espessura_mm)/1000)+.00005))
    return _refinar_candidatos_ancoras(candidatos,invalidas)


def _refinar_candidatos_ancoras(candidatos, invalidas=()):
    aceitas=[];rejeitadas=list(invalidas);ligacoes={}
    # Shortest distance first prefers actual contact independently of Outliner order.
    for c in sorted(candidatos,key=lambda c:(c['distancia'],c['origem'],c['destino'],c['assinatura'],c['alvo'])):
        par=tuple(sorted(c.get('par',(c['origem'],c['destino']))))
        if par in ligacoes:
            rejeitadas.append(dict(c,motivo="Pair of objects already joined"));continue
        aceitas.append(c)
        ligacoes.setdefault(par,[]).append(len(aceitas)-1)
    return dict(candidatas=len(candidatos),aceitas=aceitas,rejeitadas=rejeitadas,
        ligacoes=[dict(pecas=par,ancoras=indices) for par,indices in sorted(ligacoes.items())])


def propor_ancoras_piloto(pecas):
    """Explicit audit outside gestures: find zero contact on existing joints."""
    candidatos=[];pares=set();sem_contato=[]
    for c in sorted(pecas,key=lambda o:o.name):
        for ponta in _chapas.PONTAS:
            n=_vizinho_da_ponta(c,ponta)
            if n is None:continue
            par=tuple(sorted((c.name,n.name)))
            if par in pares:continue
            pares.add(par)
            # Only the audit traverses vertices; clicks still use the native engine.
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
            if not contatos:sem_contato.append(dict(pecas=par,motivo="No coincident corners; review the support before joining"))
            candidatos.extend(contatos)
    resultado=_refinar_candidatos_ancoras(candidatos)
    resultado['sem_contato']=sem_contato
    return resultado


RAIO_BOLINHA_PX = 9.0
_bolinha_hover = [None]          # (panel, endpoint, index, side) under the mouse.


def _bolinhas_da_corrente(context, corrente):
    """Return {'a': panel vertex screen point, 'b': target vertex screen point}."""
    p, q = corrente['pontos']
    return {lado: ponto for lado, ponto in (
        ('a', _hud._projetar_hud(context, p)), ('b', _hud._projetar_hud(context, q)))
        if ponto is not None}


def _bolinha_sob_mouse(context, posicao, correntes=None):
    """(chain, 'a' | 'b') for the white dot under the mouse, or (None, None).
    'a' is the welded panel vertex; 'b' is its contact target."""
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
    """Return {'corrente': center, 'regua': center} in pixels, side by side."""
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
    """(chain, 'corrente' | 'regua') under the mouse, or (None, None)."""
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
    """Return the NEAREST mouse target: ('bolinha', chain, side),
    ('botao', chain, type), or None. Short on-screen lines can put an
    endpoint dot under a button; first-match logic stole the other's click."""
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
    """Remove ALL links between a and b in both directions. Return the
    number of disconnected ends."""
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
        print("[Archy Builder] update cabinet:", e)


def desagregar(C):
    """Detach ALL C corners together: the clicked corner represents the whole
    object. If C belongs to a cabinet, remove it without movement.
    Return detached-part count."""
    soltas, modulo = _soltar(C)
    if modulo is not None:
        _atualizar_modulo(modulo)
    return soltas


def _soltar(C):
    """Remove C's links and detach it from its cabinet without movement.
    Return (detached parts, former cabinet or None)."""
    soltas = 0
    for N in _ligados_a(C):
        desassociar(C, N)
        soltas += 1
    modulo = _portas._modulo_da_chapa(C)
    if modulo is not None:
        mundo = C.matrix_world.copy()
        C.parent = None
        C.matrix_world = mundo
        # Outside the cabinet, at the scene ROOT, as requested.
        _modulos._mover_para_colecao(C, bpy.context.scene.collection)
    return soltas, modulo


def desagregar_grupo(pecas):
    """Detach ALL group parts together. Delete the cabinet if no children
    remain; an empty Empty would otherwise retain meaningless dimensions."""
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
    """Validate all destinations and both skins before writing the mesh."""
    inversa=C.matrix_world.inverted().to_3x3();deltas={}
    for s,q in pares:
        ids=_indices_da_assinatura(C,s)
        if not ids:raise ValueError("The source vertex no longer exists")
        i=ids[0];d=inversa@(Vector(q)-C.matrix_world@C.data.vertices[i].co)
        if i in deltas and (deltas[i]-d).length>1e-6:
            raise ValueError("The same vertex received different destinations")
        deltas[i]=d
    movimentos={}
    for i,d in deltas.items():
        parceiro=_indices_da_assinatura(C,_parceiro_espessura(C,'v%d'%i))
        for j in {i,*parceiro}:
            if j in movimentos and (movimentos[j]-d).length>1e-6:
                raise ValueError("The anchors require changing the panel thickness")
            movimentos[j]=d
    return deltas,movimentos


def _puxar_por_pares(C, pares):
    """One anchor translates the whole part; multiple anchors impose exact points.

    Object origin does not participate in fitting. Native mesh retains
    topology/UVs; each vertex follows its thickness partner.
    """
    if not pares:return
    if C.mode=='EDIT' or C.data.is_editmode:raise ValueError("Exit Edit Mode")
    deltas,movimentos=_movimentos_por_pares(C,pares)
    primeiro=next(iter(deltas.values()))
    if all((d-primeiro).length<1e-6 for d in deltas.values()):
        mundo=C.matrix_world.copy();mundo.translation+=C.matrix_world.to_3x3()@primeiro
        C.matrix_world=mundo
    else:
        # A common transverse displacement moves all skins without tilting
        # the panel for equal translation requested at both corners.
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
    """Associate at the current position; joining changes only cabinet membership.
    Origin is the recorded offset, never a forced fit."""
    pecas = {N for N in pecas if N is not None and N is not C}
    plano=_plano_ancoras_reais(C,pares_reais) if pares_reais else None
    # `alvos` may be empty when only the NEIGHBOR's end reaches C: derive
    # the cabinet from `pecas`, or Join would behave just like No.
    if juntar:
        modulo = next((m for m in (_portas._modulo_da_chapa(N) for N in pecas)
                       if m is not None), None)
        if modulo is not None:
            # Prepare before reparenting: an unmarked preset must not fail midway
            # or leave a retry stuck at the root.
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
    """Validate all references before moving without overwriting neighbors."""
    vizinhos={}
    for sc,nome,sn in pares:
        N=bpy.data.objects.get(nome)
        if N is None or N is C:raise ValueError("The destination panel no longer exists")
        if nome in vizinhos:raise ValueError("Each pair of objects allows only one joint")
        ids=_indices_da_assinatura(C,sc)
        if not ids or not _indices_da_assinatura(N,sn):raise ValueError("The anchor vertex no longer exists")
        vizinhos.setdefault(nome,[]).append((sc,sn))
    if len(vizinhos)>len(_chapas.PONTAS):raise ValueError("The panel already has four destinations in this connection")
    limites=[(min(v.co[i] for v in C.data.vertices),max(v.co[i] for v in C.data.vertices)) for i in (0,1)]
    restricoes = restricoes_adjacencia([C])[C]
    grupos={};ocupadas={p for p,(n,_face,_folga) in restricoes.items() if n.name not in vizinhos}
    if len(vizinhos)>len(_chapas.PONTAS)-len(ocupadas):
        raise ValueError("The panel has no free end for another connection")
    for nome,ancoras in vizinhos.items():
        pontos=[C.data.vertices[_indices_da_assinatura(C,sc)[0]].co for sc,_sn in ancoras]
        _d,ponta=min((sum(abs(p[i]-b) for p in pontos),('x','y')[i]+'_'+lado)
                    for i in (0,1) for b,lado in zip(limites[i],('neg','pos'))
                    if ('x','y')[i]+'_'+lado not in ocupadas)
        ocupadas.add(ponta);grupos[ponta,nome]=ancoras
    return grupos


def _registrar_pares_reais(C, grupos):
    """Keep C-to-N offset in N's frame so it rotates with the cabinet."""
    destinos=set()
    restricoes = restricoes_adjacencia([C])[C]
    for (ponta,nome),ancoras in grupos.items():
        N=bpy.data.objects.get(nome)
        if (N is None or N is C or nome in destinos or len(ancoras)!=1
                or any(not _indices_da_assinatura(C,sc) or not _indices_da_assinatura(N,sn) for sc,sn in ancoras)):
            raise ValueError("Each pair of objects allows only one valid joint")
        atual=restricoes.get(ponta, (None, 0, 0.))[0]
        if atual is not None and atual is not N:
            raise ValueError("The end is already joined to another panel")
        destinos.add(nome)
    for (ponta,nome),ancoras in grupos.items():
        N=bpy.data.objects[nome];eixo,lado=ponta.split('_')
        for dono,vizinho in ((C,N),(N,C)):
            for anterior in _chapas.PONTAS:
                if _vizinho_da_ponta(dono,anterior) is vizinho:
                    _chapas._limpar_ponta(dono,anterior)
        if not _chapas._gravar_ligacao(C,eixo,lado,N,0.,0 if lado=='pos' else 1):
            raise ValueError("The pair of objects is already joined")
        C['adj_%s_folga'%ponta]=_folga_com_sinal(C,ponta,N)[0]
        _gravar_ancoras(C,ponta,ancoras)
        inversa=N.matrix_world.inverted().to_3x3()
        C['adj_%s_origens'%ponta]=json.dumps([tuple(inversa@(
            _vertice_da_assinatura(C,sc)-_vertice_da_assinatura(N,sn))) for sc,sn in ancoras])


def _alvos_por_distancia(C, candidatos=None):
    """(targets, parts) for distance connection: move each reachable C end
    only TO a neighbor face, closing the gap without sliding.
    `candidatos` restricts neighbors to selected targets."""
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
    """Detach this part: release all its corners and remove it from the cabinet."""
    bl_idname = 'object.cabinet_desassociar'
    bl_label = "Detach"
    bl_options = {'REGISTER', 'UNDO'}

    chapa: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        chapa = bpy.data.objects.get(self.chapa)
        if chapa is None or _chapas.MARCA_CHAPA not in chapa:
            self.report({'WARNING'}, "Part not found")
            return {'CANCELLED'}
        if not agregado(chapa) and _portas._modulo_da_chapa(chapa) is None:
            self.report({'INFO'}, "This part was already detached")
            return {'CANCELLED'}
        desagregar(chapa)
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


class OBJECT_OT_clique_corrente(Operator):
    """Click the chain to detach or ruler to reset while holding the options key."""
    bl_idname = 'object.cabinet_clique_corrente'
    bl_label = "Detach via Link"
    bl_options = {'INTERNAL'}

    # The native chain button (GIZMO_GT_button_2d) accepts only UNMODIFIED
    # clicks, but chains appear only with Alt/Ctrl/Shift held.
    # This shortcut accepts any modifier before selection and captures
    # the click; outside chains the event passes through unchanged.
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
            # Handle anchor: drag to another edge of the group.
            bpy.ops.object.cabinet_arrastar_puxador(
                'INVOKE_DEFAULT', puxador=corrente.name)
            return {'FINISHED'}
        if tipo_alvo == 'ferragem':
            # Hinge controller on the edge or piston controller on the side.
            bpy.ops.object.cabinet_arrastar_ferragem(
                'INVOKE_DEFAULT', grupo=corrente.name, tipo=tipo)
            return {'FINISHED'}
        if tipo_alvo == 'ponto_gaveta':
            # Drawer front corner or depth with vertex snapping.
            bpy.ops.object.cabinet_arrastar_ponto_gaveta(
                'INVOKE_DEFAULT', grupo=corrente.name, indice=tipo)
            return {'FINISHED'}
        if tipo_alvo == 'canto_porta':
            # Door corner: dragging to another vertex rebuilds the door.
            bpy.ops.object.cabinet_arrastar_canto_porta(
                'INVOKE_DEFAULT', grupo=corrente.name, indice=tipo)
            return {'FINISHED'}
        if tipo_alvo == 'bolinha':
            # White dot: drag the anchor to another vertex.
            bpy.ops.object.cabinet_arrastar_ancora(
                'INVOKE_DEFAULT', chapa=corrente['a'].name,
                ponta=corrente['ponta'], indice=corrente['indice'], lado=tipo)
            return {'FINISHED'}
        if tipo == 'regua':
            # The ruler may ask about resizing; its operator waits for this click's
            # RELEASE before opening the popup.
            # This operator has no modal: returning reset's RUNNING_MODAL here
            # would cancel it.
            resposta = bpy.ops.object.cabinet_resetar_distancia(
                'INVOKE_DEFAULT', chapa=corrente['movel'].name,
                esperar_soltar=True)
            _eventos._redesenhar_viewports(context)
            return {'CANCELLED'} if 'CANCELLED' in resposta else {'FINISHED'}
        # Registration is directional: the base may store the side's weld.
        # Selection determines the detached part, as for the ruler's moving part.
        return bpy.ops.object.cabinet_desassociar(
            chapa=(corrente['movel'] if corrente.get('manual') else
                   _peca_da_regua(context,corrente['a'],corrente['b'])).name)


class OBJECT_OT_tecla_corrente(Operator):
    """Hold the options key to show chains; release to hide them."""
    bl_idname = 'object.cabinet_tecla_corrente'
    bl_label = "Show Links"
    bl_options = {'INTERNAL'}

    tecla: StringProperty(options={'SKIP_SAVE'})
    apertou: BoolProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        # ALWAYS pass the event through: Alt/Ctrl/Shift remain available
        # to Blender and other shortcuts.
        if self.tecla.split('_', 1)[-1] == _opcoes._opcao('tecla_corrente'):
            if _tecla_corrente_segurada[0] != self.apertou:
                _tecla_corrente_segurada[0] = self.apertou
                _eventos._redesenhar_viewports(context)
        return {'PASS_THROUGH'}


# ------------------------------------------ sidebar Chain button
# Selection determines the action, per user requirements:
# - ONE individual part: attached asks to detach it from the group;
# loose goes directly to vertex selection.
# - GROUP (cabinet or linked parts): ask to detach all
# items in the group.
# - Targets first, external part LAST/active: connect by distance within
# ALCANCE_CONEXAO_AUTOMATICA; beyond it, vertex selection
# offers only target corners.
OP_CORRENTE_OBJETO = 'object.cabinet_corrente_objeto'
# Sidebar buttons opening popups/modals trigger on RELEASE through
# interagir_gaveta. Icon gizmos opened popups under the mouse, where
# the same RELEASE answered them; gizmo-opened modals also captured
# sidebar clicks, preventing the bottom Confirm action.
# Generate Estimate opens Save As; Use as Handle opens
# the face-click modal.
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
_desagregar_pendente = [None]    # Parts awaiting confirmation.
_conexao_pendente = [None]       # Targets awaiting Join Cabinet.
_conexao_manual = [None]         # Vertex-selection mode state.


ATR_VERTICE_SOLDA = 'cabinet_solda_vertice'


def _ancora_estavel(obj, assinatura):
    ids=_indices_da_assinatura(obj,assinatura)
    if not ids:raise ValueError("Anchor deleted or ambiguous; choose another vertex")
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
        if n is None:raise ValueError("The destination panel no longer exists")
        alvos.append((sc,_vertice_da_assinatura(n,sn)+Vector(estado['direcoes'][k])*estado['distancias'][k]))
    return alvos


def editar_criacao_solda(valor=None, zerar=False, indice=None):
    estado=_conexao_manual[0]
    if not estado:return "No joint being created"
    if valor is not None and (not math.isfinite(valor) or valor<0):return "Invalid distance"
    if not estado['pares']:
        estado['distancia_previa']=0. if zerar else valor
        estado['reset_pendente']=zerar
        return None
    anteriores=list(estado['distancias']);zeros=list(estado['zeradas'])
    if indice is not None and not 0 <= indice < len(anteriores):return "Anchor does not exist"
    if zerar:
        indices=range(len(anteriores)) if indice is None else [indice]
        for k in indices:estado['distancias'][k]=0.;estado['zeradas'][k]=True
    elif valor is not None:
        if not math.isfinite(valor) or valor<0:return "Invalid distance"
        estado['distancias'][-1 if indice is None else indice]=valor
    _guardar_previa_solda(estado);_restaurar_previa_solda(estado)
    try:_puxar_por_pares(bpy.data.objects[estado['origem']],_alvos_previa_solda(estado))
    except ValueError as erro:
        estado['distancias']=anteriores;estado['zeradas']=zeros
        _restaurar_previa_solda(estado)
        try:_puxar_por_pares(bpy.data.objects[estado['origem']],_alvos_previa_solda(estado))
        except ValueError:pass    # Deleted target: retain original geometry.
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
    """Controls for a weld being created, without recording preview undo."""
    bl_idname='object.cabinet_acao_criacao_solda'
    bl_label="Edit Joint Creation"
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
PERGUNTA_DESAGREGAR_GRUPO = ("Are you sure you want to detach all items from this group?")
PERGUNTA_DESAGREGAR_OBJETO = ("Are you sure you want to detach this object from the group?")


def _chapas_selecionadas(context):
    return [o for o in getattr(context, 'selected_objects', ()) or ()
            if o.type == 'MESH' and _chapas.MARCA_CHAPA in o]


def _acao_corrente(context, medir=True):
    """Chain action from selection: (action, part, parts) or None.
    ('grupo', None, group parts), ('desagregar', part, [part]),
    ('conectar', external part, reachable targets), or ('vertices', part,
    targets; empty means any panel). Without `medir`, skip neighbor
    search: sidebar drawing needs only blue/gray state."""
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
            return None          # ONE part moves to the target, not an entire cabinet.
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
    """True = blue/detach; False = gray/attach; None = no Chain action
    for this selection."""
    acao = _acao_corrente(context, medir=False)
    if acao is None:
        return None
    return acao[0] in ('grupo', 'desagregar')


def _perguntar_desagregar(context, pecas, todos):
    _desagregar_pendente[0] = sorted(o.name for o in pecas)
    op = 'object.cabinet_desagregar_selecao'
    _perguntas._perguntar(context, PERGUNTA_DESAGREGAR_GRUPO if todos
               else PERGUNTA_DESAGREGAR_OBJETO,
               [("Yes, detach", 'CHECKMARK', op, {'desagregar': True}),
                ("No", 'X', op, {'desagregar': False})])


def _agrupar_soltas(context, C, pecas):
    """Chain-connected parts outside cabinets become a GROUP. If either side
    has a cabinet, the Join Cabinet question governs; do nothing here.
    Return the group or None."""
    pecas = {N for N in pecas if N is not None and _chapas.MARCA_CHAPA in N}
    if (C is None or not pecas or _portas._modulo_da_chapa(C) is not None
            or any(_portas._modulo_da_chapa(N) is not None for N in pecas)):
        return None
    todas = {C} | pecas | set(_modulos.grupo_de(C, simetrico=True))
    return _modulos.agrupar_chapas(context, sorted(todas, key=lambda o: o.name))


# Sidebar name box: the group already has a suggested name; typed text
# renames it on Enter/OK, while Esc/Keep retains the suggestion.
_nome_grupo_gaveta = [None]     # {'grupo', 'texto', 'cursor', 'selecionado'}.


def _abrir_caixa_nome(conj):
    _nome_grupo_gaveta[0] = {'grupo': conj.name, 'texto': conj.name,
                             'cursor': len(conj.name), 'selecionado': True}
    _perguntas._pergunta_atual[0] = {
        'texto': "Group name", 'campo': True, 'na_gaveta': True,
        'opcoes': [('OK', 'CHECKMARK', 'object.cabinet_nomear_grupo',
                    {'digitado': True}),
                   ("Keep", 'X', 'object.cabinet_nomear_grupo',
                    {'manter': True})]}


def _pedir_nome_grupo(context, conj, na_gaveta=None):
    """Ask for the new group name in context: a field box INSIDE the sidebar
    for sidebar clicks, a popup for viewport clicks."""
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
    """Name the cabinet group: its Empty and Collection."""
    bl_idname = 'object.cabinet_nomear_grupo'
    bl_label = "Group Name"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    grupo: StringProperty(options={'SKIP_SAVE', 'HIDDEN'})
    nome: StringProperty(name="Name", options={'SKIP_SAVE'})
    # Sidebar box OK: use its typed text.
    digitado: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})
    # Keep: retain the suggestion and just close.
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
    """Type the group name in the sidebar box; Enter confirms, Esc keeps it."""
    bl_idname = 'object.cabinet_digitar_nome_grupo'
    bl_label = "Enter Group Name"
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
            # Answered by box buttons, each with its own undo.
            self._redesenhar(context)
            return {'CANCELLED'}
        if event.value != 'PRESS' or event.type in {
                'LEFTMOUSE', 'MIDDLEMOUSE', 'RIGHTMOUSE', 'WHEELUPMOUSE',
                'WHEELDOWNMOUSE', 'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            # Pass clicks to sidebar OK/Keep and the viewport.
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
    _perguntas._perguntar(context, "Join the cabinet?",
               [("Yes, join", 'CHECKMARK', op, {'juntar': True}),
                ("No", 'X', op, {'juntar': False})], na_gaveta)


def _nomes(objs):
    return json.dumps([o.name for o in objs])


def _objetos_dos_nomes(texto):
    """Object list from JSON names; None if empty, meaning all."""
    if not texto:
        return None
    try:
        nomes = json.loads(texto)
    except ValueError:
        return None
    return [o for o in (bpy.data.objects.get(n) for n in nomes) if o is not None]


class OBJECT_OT_corrente_objeto(Operator):
    """Chain: attach/detach by selection; blue means attached. Targets first, external part last."""
    bl_idname = OP_CORRENTE_OBJETO
    bl_label = "Link"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.mode == 'OBJECT' and _conexao_manual[0] is None
                and _estado_corrente_objeto(context) is not None)

    def invoke(self, context, event):
        acao = _acao_corrente(context)
        if acao is None:
            self.report({'WARNING'}, "Select the part (or the targets and, last, the external part)")
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
    """Confirmation answer: detach the part or entire group."""
    bl_idname = 'object.cabinet_desagregar_selecao'
    bl_label = "Detach"
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
        self.report({'INFO'}, "%d part(s) detached" % n)
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


class OBJECT_OT_conectar_distancia(Operator):
    """Connect the part to reachable neighbors within 5 mm."""
    bl_idname = 'object.cabinet_conectar_distancia'
    bl_label = "Connect by Distance"
    bl_options = {'REGISTER', 'UNDO'}

    origem: StringProperty(options={'SKIP_SAVE'})
    # JSON of selected target names; empty means any panel.
    alvos: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        chapa = bpy.data.objects.get(self.origem)
        if chapa is None:
            return {'CANCELLED'}
        alvos, pecas = _alvos_por_distancia(chapa,
                                            _objetos_dos_nomes(self.alvos))
        if not pecas:
            self.report({'WARNING'}, "No part within reach")
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
    """Rebuild selected panels' welds at their current positions;
    Ctrl+D copies acquire their own identity."""
    bl_idname = 'object.cabinet_recalcular_ancoragem'
    bl_label = "Recalculate Anchoring"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(_chapas_selecionadas(context))

    def execute(self, context):
        chapas = _chapas_selecionadas(context)
        context.view_layer.update()         # Current positions (invariant 6).
        n = _chapas.recalcular_ancoragem(chapas)
        _eventos._redesenhar_viewports(context)
        self.report({'INFO'}, "%d joint(s) rebuilt on %d panel(s)"
                    % (n, len(chapas)))
        return {'FINISHED'}


class OBJECT_OT_juntar_modulo(Operator):
    """Record current anchors; joining changes membership without moving the part."""
    bl_idname = 'object.cabinet_juntar_modulo'
    bl_label = "Join Cabinet"
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
    """Finish vertex selection, equivalent to Enter."""
    bl_idname = 'object.cabinet_confirmar_conexao'
    bl_label = "Confirm Connection"

    @classmethod
    def poll(cls, context):
        estado=_conexao_manual[0]
        return estado is not None and (not estado.get('moderna') or
            estado.get('fase')=='confirmar' and bool(estado.get('pares')))

    def execute(self, context):
        _conexao_manual[0]['confirmar'] = True
        # Sidebar Confirm: show Join Cabinet there too.
        _conexao_manual[0]['pela_gaveta'] = _perguntas._na_gaveta[0]
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


def _desenhar_conexao_manual():
    """Clickable corners, the chosen one and already connected endpoints."""
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
        # Draw dots only for a few source/selected-target parts:
        # projecting the whole scene every frame froze destination selection.
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
                    texto="Native snap"
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
    # The cursor comes from native translate, without another snap engine.
    if not estado.get('snap_pendente') or estado.get('cursor') is None:return None
    escolhido=estado.get('escolhido')
    return Vector(estado['cursor']), Vector(escolhido[1]) if escolhido else None


def _candidatos_conexao(estado):
    """Clickable [(object, signature, point)] for the current phase. Read
    vertices only to DRAW a few parts; clicks use native snapping."""
    if 'alvos_snap' not in estado:_preparar_candidatos_conexao(estado)
    objs=[bpy.data.objects.get(n) for n in estado.get('alvos_snap',())]
    return [(o,'v%d'%v.index,o.matrix_world@v.co) for o in objs if o is not None for v in o.data.vertices]


def _preparar_candidatos_conexao(estado):
    """Parts eligible for native snapping in this phase: source panel or
    other destination panels. Read no vertices here."""
    origem = bpy.data.objects.get(estado['origem'])
    if estado['fase'] == 'origem':
        pecas = ([origem] if origem is not None else
                 [o for nome in estado.get('origens', ())
                  if (o := bpy.data.objects.get(nome)) is not None and o.visible_get()])
    else:
        # Targets selected before the external part: only their corners.
        destinos = _objetos_dos_nomes(estado.get('destinos'))
        pecas = [o for o in (bpy.data.objects if destinos is None else destinos)
                 if o is not origem and o.type == 'MESH' and _chapas.MARCA_CHAPA in o
                 and o.visible_get()]
    if estado.get('editar_ancora') and estado['editar_ancora'][1]=='b':
        pecas=[bpy.data.objects.get(estado['pares'][estado['editar_ancora'][0]][1])]
    estado.update(alvos_snap=[o.name for o in pecas if o is not None],
                  iniciar_snap=not estado.get('moderna') and not estado.get('aguardar_novo_par',False))


def _vertice_do_snap(estado, ponto):
    """Blender chose the point; use a cached KDTree ONLY for the hit part
    to recover its MeshVertex, rejecting other parts by local box."""
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
            # Newly appended library: native face query, without building a Python
            # tree of ALL vertices during the click.
            hit,_co,_n,face=obj.closest_point_on_mesh(local)
            if not hit or face<0:continue
            i=min(obj.data.polygons[face].vertices,key=lambda i:(obj.data.vertices[i].co-local).length_squared)
        p=obj.matrix_world@obj.data.vertices[i].co
        if (p-ponto).length<=1e-5:return obj,'v%d'%i,p
    return None


class OBJECT_OT_conectar_vertices(Operator):
    """Create a weld: choose source-panel and destination corners; Enter confirms."""
    bl_idname = 'object.cabinet_conectar_vertices'
    bl_label = "Create Joint"
    bl_options = {'REGISTER'}

    origem: StringProperty(options={'SKIP_SAVE'})
    # JSON target names; empty means corners of any panel.
    destinos: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and _conexao_manual[0] is None and _gavetas._estado_criacao() is None

    def invoke(self, context, event):
        chapa = (bpy.data.objects.get(self.origem) if self.origem
                 else context.object)
        if chapa is None or not any(m in chapa for m in
                                   (_chapas.MARCA_CHAPA, _chapas.MARCA_CONJUNTO)):
            self.report({'WARNING'}, "Select a panel or cabinet to create the joint")
            return {'CANCELLED'}
        modulo = chapa if _chapas.MARCA_CONJUNTO in chapa else None
        if not self.origem and getattr(chapa, 'chapa_modo', '') == 'GRUPO':
            modulo = modulo or _portas._modulo_da_chapa(chapa)
        origens = _modulos._chapas_do_conjunto(modulo) if modulo is not None else [chapa]
        if not origens:
            self.report({'WARNING'}, "The cabinet has no panels to join")
            return {'CANCELLED'}
        alvo = _importacao._viewport_alvo(context)
        if alvo is None:
            self.report({'ERROR'}, "No 3D viewport for clicking")
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
            "Create joint: source panel corner, then destination corner | Click/drag: native snap | Alt: anchor | Enter: confirm | Right-click/Esc: cancel | Backspace/Ctrl+Z: back")
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
        # Target deleted through Outliner during the modal: None broke the question.
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
                        self.report({'WARNING'},"Each pair of objects allows only one joint")
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
            return {'PASS_THROUGH'}     # Keep sidebar Confirm available.
        if event.type == 'MOUSEMOVE':
            if estado.pop('iniciar_snap',False):
                _gavetas.AssistenteDoVao._iniciar_snap_nativo(self,context)
            estado['hover'] = None
            self._area.tag_redraw()
            # The native gizmo needs mouse movement to recognize hover before a click.
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
    """White dot at each chain-line endpoint with Alt: draggable anchor;
    grow and highlight the dot under the mouse."""
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


# ------------------------------------------------ anchor dragging
_arraste_ancora = [None]         # Dot-drag state.


def _candidatos_ancora(estado):
    """Eligible [(signature, point)] for the dot: panel vertices on side 'a'
    (WHICH vertex is welded), neighbor vertices on side 'b'
    (WHERE it touches)."""
    C = bpy.data.objects.get(estado['chapa'])
    N = _vizinho_da_ponta(C, estado['ponta']) if C is not None else None
    if N is None:
        return []
    return _ancoras_da_malha(C if estado['lado'] == 'a' else N)


_handler_ancora = [None]         # Dot-drag drawing.


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
        solto = tela(estado['ponto'])      # Native snap cursor.
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
    _terminar_ancora_solda(remover_timer=False)     # Esc: remove drawing.
    return None


def _preparar_ancora_solda(context, C, ponta, N, indice, lado):
    """Start the cursor at the dot and restrict NATIVE snap to its eligible
    part, replacing per-movement Python vertex projection."""
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
    bl_label = "Confirm Joint Anchor"
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
        # Vertex selected by native snap: the part's cached KDTree.
        _co, i, _d = dados['arvore'].find(P.matrix_world.inverted() @ ponto)
        if (P.matrix_world @ P.data.vertices[i].co - ponto).length > 1e-5:
            return {'CANCELLED'}           # Released away from a vertex.
        op = SimpleNamespace(chapa=estado['chapa'], ponta=estado['ponta'],
                             indice=estado['indice'], lado=estado['lado'],
                             report=self.report)
        return OBJECT_OT_arrastar_ancora._gravar(op, dados['assinaturas'][i])


class OBJECT_OT_mover_ancora_solda(Macro):
    bl_idname = 'object.cabinet_mover_ancora_solda'
    bl_label = "Adjust Joint Anchor"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}


def registrar_macro_ancora():
    OBJECT_OT_mover_ancora_solda.define('TRANSFORM_OT_translate')
    OBJECT_OT_mover_ancora_solda.define('OBJECT_OT_cabinet_confirmar_ancora_solda')


class OBJECT_OT_arrastar_ancora(Operator):
    """Drag a chain dot to another vertex to change its anchor; use the ruler to move the panel there."""
    bl_idname = 'object.cabinet_arrastar_ancora'
    bl_label = "Adjust Joint Anchor"
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
        self.report({'INFO'}, 'Anchor changed; use the ruler to move the panel to it')
        return {'FINISHED'}


# ------------------------------------------ reset distance
# Restore weld origin: the sidebar ruler is BLUE when the active
# part/cabinet has a weld away from origin, with gap differing from
# its recorded value. SELECTION determines movement:
# - Single active panel: move IT to restore all its welds; ask first
# if changed cabinet dimensions require resizing.
# - Active cabinet/group: adapt the GROUP to the panel, stretching
# welded ends to it and resizing the cabinet if needed.
# Each viewport Alt ruler applies the same logic to its line's part.
OP_RESETAR_DISTANCIA = 'object.cabinet_resetar_distancia'
TOL_RESET_DISTANCIA = 0.0005     # m: below this deviation, the weld is at origin.
PERGUNTA_RESET = ("The panel will resize to return to the joint. Move anyway?")
_pergunta_reset = ['']           # Panel awaiting an answer.


def _folga_com_sinal(C, ponta, N):
    """(gap m, axis u, extreme), as stored by `_chapas._melhor_vizinho`:
    positive means separated, negative means penetrating the neighbor."""
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
    """Welds touching `chapas` away from origin, for any deviation."""
    return _ligacoes_adjacencia(chapas, TOL_RESET_DISTANCIA)


# ---- Weld anchors
# Each weld links two panel vertices to two neighbor vertices. Defaults
# use nearest corners (`_pares_da_ligacao`). Alt-drag endpoint dots to
# other vertices on either part; save the choice in `adj_<ponta>_ancoras`
# as "+-+|-++" (panel|neighbor). This changes only the anchor;
# the ruler moves the panel. Noncollinear vertices, such as one high
# and one low, DEFORM the panel end: each corner moves with its opposite
# thickness partner, tilting the panel.
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
    """Return [(C signature, N signature)], stored or default anchors."""
    gravadas = _ancoras_gravadas(C, ponta)
    if gravadas:
        return [(sc,sn) for sc,sn in gravadas if _indices_da_assinatura(C,sc) and _indices_da_assinatura(N,sn)]
    if u is None:
        i=0 if ponta.startswith('x') else 1
        u=_chapas._eixos(C)[i]
        extremo=_chapas._centro(C).dot(u)+_chapas._meias(C)[i]*(1 if ponta.endswith('pos') else -1)
    return [(sc,sn) for _p,q,sc,sn in _pares_da_ligacao(C,u,extremo,N)]


def _parceiro_espessura(P, assinatura):
    """Anchor across local-Z thickness: flip Z sign for corners; for arbitrary
    vertices, choose the nearest vertex on the opposite face."""
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
    """All eligible P vertices as [(anchor, point)]: eight box corners or
    every modeled-mesh vertex; corners alone could not reach the user's
    chamfer."""
    if P.type == 'MESH' and not _chapas._malha_e_caixa(P.data):
        mundo = P.matrix_world
        return [('v%d' % v.index, mundo @ v.co) for v in P.data.vertices]
    return [(s, _vertice_da_assinatura(P, s))
            for s in (a + b + c for a in '+-' for b in '+-' for c in '+-')]


def _gravar_ancoras(C, ponta, ancoras):
    C['adj_%s_ancoras' % ponta] = ['%s|%s' % a for a in ancoras]


def _origens_ancoras(C, ponta):
    """Persisted numeric data; old joints retain scalar clearance."""
    try:
        valores=json.loads(C.get('adj_%s_origens'%ponta,'null'))
        if valores is None or len(valores)!=len(_ancoras_gravadas(C,ponta) or []):return None
        if not all(len(v)==3 and all(math.isfinite(float(x)) for x in v) for v in valores):return None
        return [Vector(v) for v in valores]
    except (ValueError,TypeError):return None


def editar_distancia_solda(nome,propriedade,valor):
    """The destination anchor stays fixed; offset lives in its axes."""
    try:
        ponta,indice=propriedade.split('|');indice=int(indice)
        c=bpy.data.objects.get(nome);n=_vizinho_da_ponta(c,ponta) if c else None
        if n is None or not c.get('adj_%s_manual'%ponta):return "Manual joint not found"
        if not math.isfinite(valor) or valor<0:return "Invalid distance"
        ancoras=_ancoras_gravadas(c,ponta) or []
        if not 0<=indice<len(ancoras):return "Joint anchor not found"
        direcoes=json.loads(c['adj_%s_direcoes'%ponta])
        direcao=(n.matrix_world.to_3x3().normalized()@Vector(direcoes[indice])).normalized()
        if not all(math.isfinite(v) for v in direcao) or direcao.length<.5:return "Invalid joint direction; choose another anchor"
        alvos=[(sc,_vertice_da_assinatura(n,sn)+direcao*valor) if k==indice else
               (sc,_vertice_da_assinatura(c,sc)) for k,(sc,sn) in enumerate(ancoras)]
        _puxar_por_pares(c,alvos)
        modulo=_portas._modulo_da_chapa(c)
        if modulo is not None:_atualizar_modulo(modulo)
    except (ValueError,KeyError,IndexError,TypeError) as erro:return str(erro)
    return None


def diagnostico_soldas(obj):
    """Invalid anchors retain metadata and require an explicit choice."""
    if obj is None:return ''
    chapas=_modulos._chapas_do_conjunto(obj) if _chapas.MARCA_CONJUNTO in obj else [obj]
    for c in chapas:
        for ponta in _chapas.PONTAS:
            if not c.get('adj_%s_manual'%ponta):continue
            n=_vizinho_da_ponta(c,ponta)
            if n is None:return "Joint destination removed"
            if any(not _indices_da_assinatura(c,sc) or not _indices_da_assinatura(n,sn)
                   for sc,sn in (_ancoras_gravadas(c,ponta) or [])):
                return "Joint anchor removed or ambiguous"
    return ''


def _desvio_ancora(C, ponta, N, indice, sc, sn):
    """Difference from recorded origin, shared by HUD and reset."""
    origens=_origens_ancoras(C,ponta)
    if origens is not None:
        afastamento=N.matrix_world.to_3x3()@origens[indice]
    else:
        u=_chapas._eixos(C)[0 if ponta.startswith('x') else 1]
        afastamento=u*(-1 if ponta.endswith('pos') else 1)*float(C.get('adj_%s_folga'%ponta,0.))
    return _vertice_da_assinatura(N,sn)+afastamento-_vertice_da_assinatura(C,sc)


# Each box vertex stores its ORIGINAL corner attribute. Anchor deformation
# can move a corner across the part origin, tilting a side through its
# entire thickness; coordinate signs then selected the WRONG vertex
# (13.5 mm external-anchor regression). The attribute follows the vertex.
ATRIBUTO_CANTO = 'cabinet_canto'


def _codigo_assinatura(assinatura):
    return sum(1 << i for i, c in enumerate(assinatura) if c == '+')


def _gravar_cantos(P):
    """Mark eight box vertices by their side of the box center; valid
    before deformation."""
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
    """Anchor vertex index: 'v12' means modeled-mesh vertex 12, such as a
    chamfer. '+-+' means its corner attribute only for eight-vertex boxes;
    new vertices get attribute 0. Without attributes, use coordinate
    signs in the part frame."""
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
    """Anchor's ACTUAL world vertex: anchor-deformed panels depart from
    nominal property corners."""
    indices = _indices_da_assinatura(P, assinatura)
    if not indices:raise ValueError("The anchor vertex no longer exists")
    return P.matrix_world @ P.data.vertices[indices[0]].co


def _medida_solda(C, ponta, N, restricoes=None):
    """C->N weld (delta, residuals): delta is OUTWARD endpoint movement to
    restore origin; residuals = [(signature, vector)] per-vertex remainder
    for noncollinear anchors, empty without stored anchors."""
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
    """Compute destinations together so one anchor cannot affect the next."""
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
    """Fit anchored vertices: side 'a' moves C endpoints to neighbor vertices;
    side 'b' moves N vertices to C. Deform the active/moving part. Each
    corner follows its opposite thickness partner, retaining thickness
    while tilting the panel."""
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
            _gravar_cantos(peca)    # Mark the reference before deformation.
        for i,d in movimentos.items():peca.data.vertices[i].co+=d
        peca.data.update()
        bpy.context.view_layer.update()
    return mudou


def resetar_ponta(C, ponta):
    """Move C endpoint `ponta` to its stored neighbor gap, holding the other
    end fixed and stretching/shrinking the panel. Stored anchors stretch
    by the mean, then deform the remainder (`_deformar_ancoras`)."""
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
    """Given [(panel, endpoint)], return restored count; refit cabinets."""
    escolhidas=list(escolhidas)
    # Do not leave earlier joints applied if a later joint is impossible.
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
    """Return [(M axis, 'min'/'max', displacement m)] requested by M's welds
    to restore origin, including 0 for anchors already there.
    Also report whether any weld is displaced."""
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
    """Return {'lados': [(d_min, d_max)] per M axis, 'muda_medida'} to restore
    M's weld origins, or None if all already match. Different opposite-side
    displacements require resizing; thickness never stretches, using
    the mean instead."""
    # Equal 3D offsets require rigid translation, including the direction
    # tangent to the weld. Legacy scalar clearance could not represent it.
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
        # On a side, NORMAL welds govern overall movement; anchored welds govern
        # only when alone, with deformation handling their remainder.
        # Averaging both moved the base to meet only halfway
        # toward the anchored top.
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
    # Anchor requirements not resolved by translation DEFORM the moving
    # part's endpoint, or its face when it is the neighbor.
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
    """Count P's welds and how many are away from origin."""
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
    """Of two welded parts, find the one that MOVED AWAY: all its welds
    are away from origin, as with the user's side panel."""
    def razao(P):
        total, fora = _soldas_de(P)
        return fora / total if total else 0.0
    return a if razao(a) > razao(b) else b


def _peca_da_regua(context, a, b):
    """Part passed by line a-b's ruler to reset: the sole active panel
    if it is either participant, otherwise the displaced part."""
    alvo = _hud._alvo_hud(context)
    if alvo is not None and alvo[1] == 'INDIVIDUAL' and alvo[0] in (a, b):
        return alvo[0]
    return _peca_afastada(a, b)


def _modo_reset(context, nome=''):
    """From active selection, return ('CHAPA', M, None) or ('GRUPO', parts,
    focus). `nome` is the clicked viewport line's part; None without an item."""
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
    """True for blue, with a displaced weld; None for disabled."""
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
    """Reset weld distance to origin: move an active panel; adapt an active cabinet to the panel."""
    bl_idname = OP_RESETAR_DISTANCIA
    bl_label = "Reset Distance"
    bl_options = {'REGISTER', 'UNDO'}

    chapa: StringProperty(options={'SKIP_SAVE'})
    forcar: BoolProperty(options={'SKIP_SAVE'})
    cancelar: BoolProperty(options={'SKIP_SAVE'})
    # Called from PRESS (Alt ruler): bpy.ops `event` may already contain
    # the same click's RELEASE, as observed in logs, so the caller signals
    # that release is still pending.
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
        # A popup opened on PRESS appears under the mouse and the same click's
        # RELEASE answers it, as with Chain. Wait for release.
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
            self.report({'WARNING'}, "Select the panel or cabinet")
            return {'CANCELLED'}
        if modo[0] == 'CHAPA':
            M = modo[1]
            plano = _plano_reset_chapa(M)
            if plano is None:
                self.report({'INFO'}, "The joints are already at their origins")
                return {'CANCELLED'}
            if plano['muda_medida'] and not self.forcar:
                _pergunta_reset[0] = M.name
                _perguntas._perguntar(context, PERGUNTA_RESET, [
                    ("Yes, move", 'CHECKMARK', OP_RESETAR_DISTANCIA,
                     {'chapa': M.name, 'forcar': True}),
                    ("No", 'X', OP_RESETAR_DISTANCIA, {'cancelar': True})])
                return {'CANCELLED'}
            _pergunta_reset[0] = ''
            try:
                _aplicar_reset_chapa(M, plano)
            except ValueError as e:
                self.report({'WARNING'}, str(e))
                return {'CANCELLED'}
            self.report({'INFO'}, "%s returned to the joint origin" % M.name)
        else:
            ligacoes = _soldas_do_grupo(modo[1], modo[2])
            if not ligacoes:
                self.report({'INFO'}, "The joints are already at their origins")
                return {'CANCELLED'}
            try:
                n = resetar_pontas([(l['a'], l['ponta']) for l in ligacoes])
            except ValueError as e:     # Conflicting manual anchors.
                self.report({'WARNING'}, str(e))
                return {'CANCELLED'}
            self.report({'INFO'}, "%d end(s) returned to the joint" % n)
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}
