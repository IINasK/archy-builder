"""Refina somente soldas existentes, em preparo externo reaberto e reversivel.

Blender --background --factory-startup --python este_arquivo --
  --destino PASTA [--biblioteca PASTA] [--auditar | --aplicar | --reverter]
Sem opcao: prepara; --auditar apenas mede, sem chamar a normalizacao.
Publicar exige revisao previa do manifesto e --aplicar explicito.
"""
import argparse
from array import array
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ajustar_encaixes_promob as base

ATRIBUTOS_SOLDAS = {'cabinet_canto', 'cabinet_solda_vertice'}
TOLERANCIA_MINIMO_MM = .001


def _ler(caminho):
    return json.loads(Path(caminho).read_text(encoding='utf-8'))


def _gravar(caminho, dados):
    caminho = Path(caminho)
    temporario = caminho.with_name(caminho.name + '.tmp')
    temporario.write_text(json.dumps(dados, ensure_ascii=True, indent=1) + '\n', encoding='utf-8')
    os.replace(temporario, caminho)


def _digital(dados):
    return hashlib.sha256(repr(dados).encode('utf-8')).hexdigest()


def _conferir_protegido(antes, depois):
    base.conferir(antes, depois)
    if _digital(antes) != _digital(depois):
        raise AssertionError('Assinatura protegida mudou, mesmo abaixo da tolerancia numerica')


def _caminho(pasta, nome):
    caminho = Path(base.caminho_da_peca(str(pasta), nome))
    if caminho.resolve().parent != Path(pasta).resolve() or ':' in nome:
        raise ValueError('Arquivo fora da pasta: ' + nome)
    return caminho


def _arquivos(pasta):
    return {p.name: base.digital(_caminho(pasta, p.name)) for p in Path(pasta).iterdir()
            if p.is_file() and p.suffix in ('.blend', '.png', '.json', '.txt')}


@contextmanager
def _sessao(guarda):
    if not bpy.app.background:
        raise RuntimeError('Use Blender externo com --background --factory-startup')
    addon = base.addon
    anteriores = addon.opcoes._pasta_addon, addon.biblioteca.pasta_biblioteca
    ocupado = addon.chapas._ocupado[0]
    addon.opcoes._pasta_addon = lambda: str(guarda)
    addon.biblioteca.pasta_biblioteca = lambda: str(guarda)
    try:
        addon.register()
        addon.chapas._ocupado[0] = True
        try:
            yield
        finally:
            base.limpar()
            addon.unregister()
    finally:
        addon.chapas._ocupado[0] = ocupado
        addon.opcoes._pasta_addon, addon.biblioteca.pasta_biblioteca = anteriores


def _rna(dado):
    valores = {}
    for prop in dado.bl_rna.properties:
        nome = prop.identifier
        if nome == 'rna_type' or prop.type == 'COLLECTION' or (prop.is_readonly and nome != 'type'):
            continue
        valor = getattr(dado, nome)
        if prop.type == 'POINTER' and valor is not None and not isinstance(valor, bpy.types.ID):
            continue
        if getattr(prop, 'is_array', False):
            valor = list(valor)
        valores[nome] = base.valor_json(valor)
    return valores


def _atributo(atributo):
    campos = {}
    if len(atributo.data):
        for prop in atributo.data[0].bl_rna.properties:
            if prop.identifier == 'rna_type':
                continue
            dados = array('f' if prop.type == 'FLOAT' else 'i', [0]) * (
                len(atributo.data) * (prop.array_length if prop.is_array else 1))
            atributo.data.foreach_get(prop.identifier, dados)
            campos[prop.identifier] = _digital(dados.tobytes())
    return atributo.data_type, atributo.domain, campos


def _preview(dado):
    preview = dado.preview
    return (list(preview.image_size), _digital(list(preview.image_pixels))) if preview else None


def _props(dado):
    try:
        return base.valor_json(dict(dado.items()))
    except TypeError:
        return {}


def _restricoes_axiais(objetos):
    solda = base.addon.solda
    restricoes = set()
    for o in objetos:
        for ponta in base.addon.chapas.PONTAS:
            n = solda._vizinho_da_ponta(o, ponta)
            if n is not None:
                restricoes.update((a.name, p, b.name, face, folga)
                    for a, p, b, face, folga in solda._restricoes_da_ligacao(o, ponta, n))
    return sorted(restricoes)


def estado_protegido(colecoes, objetos):
    """Assina dados que a migracao nao tem permissao para alterar."""
    estado = base.estado(colecoes, objetos)
    estado['restricoes_axiais'] = _restricoes_axiais(objetos)
    estado['colecoes'] = {c.name: dict(props=base.valor_json(dict(c.items())),
        filhos=sorted(x.name for x in c.children), objetos=sorted(o.name for o in c.objects),
        asset=_rna(c.asset_data) if c.asset_data else None, preview=_preview(c)) for c in colecoes}
    for o in objetos:
        estado['objetos'][o.name].update(
            pai=o.parent.name if o.parent else None, tipo=o.type,
            dados=o.data.name if o.data else None,
            matriz_local=[list(linha) for linha in o.matrix_basis],
            matriz_pai=[list(linha) for linha in o.matrix_parent_inverse],
            modificadores=[(_rna(m), _props(m)) for m in o.modifiers],
            restricoes=[_rna(c) for c in o.constraints],
            asset=_rna(o.asset_data) if o.asset_data else None, preview=_preview(o))
    estado['malhas'] = {}
    for malha in bpy.data.meshes:
        estado['malhas'][malha.name] = dict(
            props=base.valor_json(dict(malha.items())),
            arestas=_digital([tuple(e.vertices) for e in malha.edges]),
            faces=_digital([(tuple(p.vertices), p.material_index, p.use_smooth) for p in malha.polygons]),
            materiais=[m.name if m else None for m in malha.materials],
            atributos={a.name: _atributo(a) for a in malha.attributes if a.name not in ATRIBUTOS_SOLDAS})
        for a in malha.attributes:
            if a.name in ATRIBUTOS_SOLDAS and (a.data_type, a.domain) != ('INT', 'POINT'):
                raise RuntimeError('Atributo de solda com tipo incorreto: ' + malha.name + '/' + a.name)
    estado['materiais'] = {m.name: dict(rna=_rna(m), props=base.valor_json(dict(m.items())))
                           for m in bpy.data.materials}
    # Arvores embutidas de materiais diferentes compartilham o nome Shader Nodetree.
    arvores = {'grupo:' + t.name: t for t in bpy.data.node_groups}
    arvores.update({'material:' + m.name: m.node_tree for m in bpy.data.materials if m.node_tree})
    estado['nos'] = {nome: dict(nos=[dict(rna=_rna(n), props=_props(n),
        entradas=[(s.identifier, base.valor_json(list(s.default_value)
            if hasattr(s.default_value, '__len__') and not isinstance(s.default_value, str)
            else s.default_value)) for s in n.inputs if hasattr(s, 'default_value')])
        for n in t.nodes], ligacoes=[(l.from_node.name, l.from_socket.identifier,
        l.to_node.name, l.to_socket.identifier) for l in t.links]) for nome, t in arvores.items()}
    return estado


def _estado_soldas(objetos):
    return dict(props={o.name: {k: base.valor_json(v) for k, v in o.items() if k.startswith('adj_')}
                       for o in objetos}, atributos={m.name: {a.name: _atributo(a)
                       for a in m.attributes if a.name in ATRIBUTOS_SOLDAS} for m in bpy.data.meshes})


def auditar_objetos(objetos):
    """Conta registros e pares REAIS; nao propoe nem grava novas ancoras."""
    solda = base.addon.solda
    pares, invalidas, distancias = {}, [], []
    registros = ancoras = sem_ancoras = 0
    nomes = {o.name for o in objetos}
    for o in objetos:
        for ponta in base.addon.chapas.PONTAS:
            if not (o.get('adj_' + ponta) or o.get('adj_' + ponta + '_uid')):
                continue
            registros += 1
            n = solda._vizinho_da_ponta(o, ponta)
            if n is None or n.name not in nomes:
                invalidas.append(dict(origem=o.name, ponta=ponta, motivo='Vizinho ausente'))
                continue
            par = tuple(sorted((o.name, n.name)))
            dados = pares.setdefault(par, dict(registros=0, ancoras=0))
            dados['registros'] += 1
            gravadas = solda._ancoras_gravadas(o, ponta)
            if not gravadas:
                sem_ancoras += 1
                continue
            dados['ancoras'] += len(gravadas)
            ancoras += len(gravadas)
            for a, b in gravadas:
                try:
                    p, q = solda._vertice_da_assinatura(o, a), solda._vertice_da_assinatura(n, b)
                    distancias.append((p - q).length * 1000)
                except (ValueError, IndexError):
                    invalidas.append(dict(origem=o.name, ponta=ponta, motivo='Vertice invalido'))
    return dict(objetos=len(objetos), registros=registros, pares=len(pares), ancoras=ancoras,
        sem_ancoras_gravadas=sem_ancoras,
        pares_repetidos=sum(d['registros'] > 1 for d in pares.values()),
        pares_com_varias_ancoras=sum(d['ancoras'] > 1 for d in pares.values()),
        pares_objetos=[list(par) for par in sorted(pares)], invalidas=invalidas,
        distancia_maxima_mm=max(distancias, default=0),
        ancoras_em_contato=sum(d <= .01 for d in distancias))


def _conferir_soldas(antes, depois):
    if (depois['invalidas'] or depois['sem_ancoras_gravadas'] or depois['pares_repetidos'] or depois['pares_com_varias_ancoras']
            or depois['registros'] != depois['ancoras']
            or antes['pares_objetos'] != depois['pares_objetos']):
        raise RuntimeError('Soldas invalidas ou pares de objetos alterados: ' + json.dumps(depois))


def _distancia_minima_real(a, b):
    """Produto cartesiano em blocos, independente do KDTree usado pela API."""
    minimo = math.inf
    for i in range(0, len(a), 256):
        for j in range(0, len(b), 256):
            deltas = a[i:i+256, None, :] - b[None, j:j+256, :]
            minimo = min(minimo, float(np.einsum('ijk,ijk->ij', deltas, deltas).min()))
            if minimo == 0:
                return 0.
    return math.sqrt(minimo)


def validar_minimos_reais(objetos):
    """Somente leitura: cada ancora deve realizar o menor gap global em mundo."""
    solda = base.addon.solda
    pontos, registros = {}, []
    for o in objetos:
        for ponta in base.addon.chapas.PONTAS:
            n = solda._vizinho_da_ponta(o, ponta)
            if n is None:
                continue
            ancoras = solda._ancoras_gravadas(o, ponta)
            if not ancoras or len(ancoras) != 1:
                raise RuntimeError('Auditoria minima exige uma ancora: ' + o.name + '/' + ponta)
            for peca in (o, n):
                if peca.name not in pontos:
                    vertices = [tuple(peca.matrix_world @ v.co) for v in peca.data.vertices]
                    if not vertices or not np.isfinite(vertices).all():
                        raise RuntimeError('Peca sem vertices reais finitos: ' + peca.name)
                    pontos[peca.name] = np.array(vertices, dtype=np.float64)
            minimo = _distancia_minima_real(pontos[o.name], pontos[n.name]) * 1000
            a, b = ancoras[0]
            distancia = math.dist(solda._vertice_da_assinatura(o, a),
                                 solda._vertice_da_assinatura(n, b)) * 1000
            excesso = max(0., distancia - minimo)
            if not math.isfinite(distancia) or excesso > TOLERANCIA_MINIMO_MM:
                raise RuntimeError('Ancora nao realiza o minimo real global: %s/%s -> %s (%g > %g mm)'
                                   % (o.name, ponta, n.name, distancia, minimo))
            registros.append(dict(origem=o.name, ponta=ponta, destino=n.name, ancoras=ancoras[0],
                distancia_mm=distancia, minimo_mm=minimo, excesso_mm=excesso))
    return registros


def _resumo(registros):
    chaves = ('objetos', 'registros', 'pares', 'ancoras', 'sem_ancoras_gravadas',
              'pares_repetidos', 'pares_com_varias_ancoras', 'ancoras_em_contato')
    return dict(arquivos=len(registros), **{c: sum(r[c] for r in registros) for c in chaves},
        invalidas=sum(len(r['invalidas']) for r in registros))


def _indice(biblioteca):
    itens = _ler(biblioteca / 'indice.json')
    nomes = [i['arquivo'] for i in itens]
    if len({n.casefold() for n in nomes}) != len(nomes):
        raise ValueError('Indice tem nomes repetidos')
    for nome in nomes:
        if _caminho(biblioteca, nome).suffix != '.blend':
            raise ValueError('Preset sem extensao blend: ' + nome)
    return nomes


def auditar(biblioteca, destino):
    base.validar_destino(str(biblioteca), str(destino))
    biblioteca, destino = Path(biblioteca).resolve(), Path(destino).resolve()
    if destino.exists():
        raise ValueError('Destino ja existe; use outra pasta externa')
    nomes, hashes = _indice(biblioteca), _arquivos(biblioteca)
    destino.mkdir(parents=True)
    registros = []
    with _sessao(destino / 'guarda'):
        for nome in nomes:
            _cols, objetos = base.carregar(str(_caminho(biblioteca, nome)))
            registros.append(dict(arquivo=nome, **auditar_objetos(objetos)))
            if len(registros) % 25 == 0:
                print('[soldas auditadas]', len(registros), '/', len(nomes), flush=True)
    if _arquivos(biblioteca) != hashes:
        raise RuntimeError('Biblioteca mudou durante a auditoria')
    resultado = dict(biblioteca=str(biblioteca), hashes=hashes, arquivos=registros, resumo=_resumo(registros))
    _gravar(destino / 'auditoria.json', resultado)
    return resultado


def preparar(biblioteca, destino):
    base.validar_destino(str(biblioteca), str(destino))
    biblioteca, destino = Path(biblioteca).resolve(), Path(destino).resolve()
    if destino.exists():
        raise ValueError('Destino ja existe; use outra pasta externa')
    if not callable(getattr(base.addon.solda, 'normalizar_ligacoes', None)):
        raise RuntimeError('API solda.normalizar_ligacoes ainda indisponivel')
    nomes, hashes = _indice(biblioteca), _arquivos(biblioteca)
    for pasta in ('originais', 'novos'):
        (destino / pasta).mkdir(parents=True)
    # Copiar tudo permite revisar o staging como biblioteca, sem refazer fotos.
    for nome, digital in hashes.items():
        for pasta in ('originais', 'novos'):
            shutil.copy2(_caminho(biblioteca, nome), destino / pasta / nome)
            if base.digital(destino / pasta / nome) != digital:
                raise RuntimeError('Fonte mudou durante backup: ' + nome)
    fontes = {str(Path(f).resolve()): base.digital(f) for f in (
        __file__, base.addon.__file__, base.addon.solda.__file__, base.addon.chapas.__file__)}
    m = dict(biblioteca=str(biblioteca), versao=base.addon.bl_info['version'], fontes=fontes, hashes=hashes,
             arquivos=[], auditados=[], verificado=False, publicado=False)
    _gravar(destino / 'manifesto.json', m)
    with _sessao(destino / 'guarda'):
        for nome in nomes:
            cols, objetos = base.carregar(str(destino / 'originais' / nome))
            antes = estado_protegido(cols, objetos)
            soldas = _estado_soldas(objetos)
            auditoria = auditar_objetos(objetos)
            pecas = [o for o in objetos if base.addon.chapas.MARCA_CHAPA in o]
            resultado = base.addon.solda.normalizar_ligacoes(pecas, recalcular_ancoras=True)
            if resultado['invalidas']:
                raise RuntimeError('Normalizacao exige revisao: ' + nome + ' ' + repr(resultado['invalidas']))
            _conferir_protegido(antes, estado_protegido(cols, objetos))
            depois = auditar_objetos(objetos)
            _conferir_soldas(auditoria, depois)
            esperado = _estado_soldas(objetos)
            alterado = soldas != esperado
            if alterado:
                blend = destino / 'novos' / nome
                bpy.data.libraries.write(str(blend), set(cols) | set(objetos), fake_user=True, compress=True)
                cols, objetos = base.carregar(str(blend))
                _conferir_protegido(antes, estado_protegido(cols, objetos))
                base.conferir(esperado, _estado_soldas(objetos))
                _conferir_soldas(auditoria, auditar_objetos(objetos))
                pecas = [o for o in objetos if base.addon.chapas.MARCA_CHAPA in o]
                base.addon.solda.normalizar_ligacoes(pecas, recalcular_ancoras=True)
                base.conferir(esperado, _estado_soldas(objetos))
                _conferir_protegido(antes, estado_protegido(cols, objetos))
                m['arquivos'].append(dict(nome=nome, original=hashes[nome], novo=base.digital(blend)))
            m['auditados'].append(dict(arquivo=nome, alterado=alterado, antes=auditoria,
                depois=depois, resultado=base.valor_json(resultado), protegido=_digital(antes),
                minimos_reais=validar_minimos_reais(objetos)))
            _gravar(destino / 'manifesto.json', m)
            print('[soldas preparadas]', len(m['auditados']), '/', len(nomes), nome, flush=True)
    if _arquivos(biblioteca) != hashes or _arquivos(destino / 'originais') != hashes:
        raise RuntimeError('Biblioteca ou backup mudou durante o preparo')
    esperados = dict(hashes, **{a['nome']: a['novo'] for a in m['arquivos']})
    if _arquivos(destino / 'novos') != esperados:
        raise RuntimeError('Staging mudou fora dos blends verificados')
    if any(base.digital(f) != digital for f, digital in fontes.items()):
        raise RuntimeError('Fonte mudou durante o preparo; repita com fonte estabilizada')
    minimos = [p for a in m['auditados'] for p in a['minimos_reais']]
    if len(minimos) != sum(a['depois']['pares'] for a in m['auditados']):
        raise RuntimeError('Auditoria minima nao cobriu todos os pares de objetos')
    m.update(verificado=True, resumo_antes=_resumo([a['antes'] for a in m['auditados']]),
             resumo_depois=_resumo([a['depois'] for a in m['auditados']]),
             auditoria_minimos=dict(metodo='produto_cartesiano_numpy_em_blocos', pares=len(minimos),
                 tolerancia_mm=TOLERANCIA_MINIMO_MM,
                 excesso_maximo_mm=max((p['excesso_mm'] for p in minimos), default=0.)))
    _gravar(destino / 'manifesto.json', m)
    return m


def publicar(destino, reverter=False):
    destino = Path(destino).resolve()
    m = _ler(destino / 'manifesto.json')
    if not m.get('verificado') or bool(m.get('publicado')) != reverter:
        raise RuntimeError('Preparo incompleto ou estado de publicacao incompativel')
    if not reverter and (not m.get('fontes') or any(
            not Path(f).is_file() or base.digital(f) != digital for f, digital in m['fontes'].items())):
        raise RuntimeError('Fonte mudou desde o preparo; repita com fonte estabilizada')
    biblioteca = Path(m['biblioteca']).resolve()
    for pasta in (destino, destino / 'originais', destino / 'novos'):
        base.validar_destino(str(biblioteca), str(pasta))
    nomes = [a['nome'] for a in m['arquivos']]
    if len(set(nomes)) != len(nomes):
        raise ValueError('Manifesto com arquivos repetidos')
    for a in m['arquivos']:
        for pasta in (biblioteca, destino / 'originais', destino / 'novos'):
            _caminho(pasta, a['nome'])
        if Path(a['nome']).suffix != '.blend' or m['hashes'].get(a['nome']) != a['original']:
            raise ValueError('Manifesto altera arquivo nao permitido: ' + a['nome'])
    novos = dict(m['hashes'], **{a['nome']: a['novo'] for a in m['arquivos']})
    if (_arquivos(biblioteca) != (novos if reverter else m['hashes'])
            or _arquivos(destino / 'originais') != m['hashes']
            or _arquivos(destino / 'novos') != novos):
        raise RuntimeError('Biblioteca, staging ou backup mudou desde o preparo')
    fonte = destino / ('originais' if reverter else 'novos')
    retorno = destino / ('novos' if reverter else 'originais')
    for nome in nomes:
        if (biblioteca / (nome + '.solda-nova')).exists():
            raise RuntimeError('Temporario ja existe: ' + nome)
    aplicados, temporario = [], None
    try:
        for nome in nomes:
            alvo = _caminho(biblioteca, nome)
            temporario = alvo.with_name(alvo.name + '.solda-nova')
            shutil.copyfile(fonte / nome, temporario)
            os.replace(temporario, alvo)
            aplicados.append(nome)
            temporario = None
        if _arquivos(biblioteca) != (m['hashes'] if reverter else novos):
            raise RuntimeError('Conferencia final diverge')
        m['publicado'] = not reverter
        _gravar(destino / 'manifesto.json', m)
    except BaseException:
        for nome in aplicados:
            shutil.copy2(retorno / nome, biblioteca / nome)
        if temporario is not None:
            temporario.unlink(missing_ok=True)
        raise
    return m


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--biblioteca', default=base.addon.biblioteca.pasta_biblioteca())
    parser.add_argument('--destino', required=True)
    modos = parser.add_mutually_exclusive_group()
    for nome in ('auditar', 'aplicar', 'reverter'):
        modos.add_argument('--' + nome, action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:])
    if args.aplicar or args.reverter:
        resultado = publicar(args.destino, reverter=args.reverter)
    elif args.auditar:
        resultado = auditar(args.biblioteca, args.destino)
    else:
        resultado = preparar(args.biblioteca, args.destino)
    print(json.dumps(resultado.get('resumo_depois', resultado.get('resumo', {})), indent=1), flush=True)


if __name__ == '__main__':
    main()
