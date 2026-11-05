"""Audit cabinet internal clearances and intersections without changing the library.

--destino must be outside the library. Contacts up to 0.25 mm are tolerated;
cut shelf envelopes can overlap without a corresponding physical collision."""
import argparse
from collections import Counter
import itertools
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
import tools.migrations.adjust_fits as _base

TOLERANCIA_MM = .25
FACES_CAIXA = ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4),
               (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5))


def geometria(pontos, faces, eixos=None):
    pontos = [Vector(v) for v in pontos]
    chaves = [tuple(round(c, 4) for c in v) for v in pontos]
    arestas = Counter(tuple(sorted((chaves[i], chaves[j]))) for face in faces
                      for i, j in zip(face, face[1:] + face[:1]))
    indices = Counter(tuple(sorted((i,j))) for face in faces
                      for i,j in zip(face,face[1:]+face[:1]))
    return dict(pontos=pontos, faces=faces,
                eixos=eixos or list(Matrix.Identity(3).col),
                arvore=BVHTree.FromPolygons(pontos, faces),
                fechada=all(n == 2 for n in indices.values()) or all(n == 2 for n in arestas.values()),
                centro=sum(pontos, Vector()) / len(pontos))


def caixa(matriz, dimensoes):
    return geometria([matriz @ Vector(v) for v in itertools.product(
        (0., dimensoes[0]), (0., dimensoes[1]), (0., dimensoes[2]))],
        FACES_CAIXA, [v.normalized() for v in matriz.to_3x3().col])


def intersecao_de_envelopes(a, b, tolerancia=TOLERANCIA_MM):
    """SAT: eixos das duas caixas e seus produtos cruzados, inclusive giradas."""
    eixos = a['eixos'] + b['eixos'] + [x.cross(y) for x in a['eixos'] for y in b['eixos']]
    menor = float('inf')
    for eixo in eixos:
        if eixo.length_squared < 1e-12:
            continue
        eixo = eixo.normalized()
        pa, pb = [[v.dot(eixo) for v in g['pontos']] for g in (a, b)]
        comum = min(max(pa), max(pb)) - max(min(pa), min(pb))
        if comum <= tolerancia:
            return None
        menor = min(menor, comum)
    return menor


def dentro(ponto, dados, tolerancia=TOLERANCIA_MM / 4):
    """Paridade do ray cast nativo independe da orientacao das normais do DXF."""
    arvore = dados['arvore']
    proximo = arvore.find_nearest(ponto)
    if proximo[0] is None or proximo[3] <= tolerancia:
        return False
    direcao = Vector((1., .37139, .19317)).normalized()
    origem, cruzamentos = ponto.copy(), 0
    for _ in range(256):
        local, _normal, _indice, _distancia = arvore.ray_cast(origem, direcao)
        if local is None:
            return bool(cruzamentos % 2)
        cruzamentos += 1
        origem = local + direcao * .001
    raise RuntimeError('Malha exige mais de 256 cruzamentos para testar interior')


def ponto_de_colisao(a, b):
    """Exige um ponto estritamente dentro dos dois solidos; tocar nao basta."""
    if not a['fechada'] or not b['fechada']:
        return None
    if intersecao_de_envelopes(a, b) is None:
        return None
    candidatos = [a['centro'], b['centro'], (a['centro'] + b['centro']) / 2]
    candidatos.append(Vector(tuple((max(min(v[k] for v in a['pontos']),
        min(v[k] for v in b['pontos'])) + min(max(v[k] for v in a['pontos']),
        max(v[k] for v in b['pontos']))) / 2 for k in range(3))))
    candidatos.extend(a['pontos'])
    candidatos.extend(b['pontos'])
    for p in candidatos:
        if dentro(p, a) and dentro(p, b):
            return list(p)
    # Cruzar placas pode nao deixar vertices dentro da outra. As arestas
    # que atravessam sua superficie fornecem uma amostra no volume comum.
    for origem, destino in ((a, b), (b, a)):
        pares = origem['arvore'].overlap(destino['arvore'])
        faces = {i for i, _j in pares}
        for indice in faces:
            vertices = origem['faces'][indice]
            vs = [origem['pontos'][i] for i in vertices]
            normal = (vs[1]-vs[0]).cross(vs[2]-vs[0]).normalized()
            centro_face = sum(vs, Vector()) / len(vs)
            for i, j in zip(vertices, vertices[1:] + vertices[:1]):
                inicio, fim = origem['pontos'][i], origem['pontos'][j]
                direcao = fim - inicio
                comprimento = direcao.length
                if comprimento <= TOLERANCIA_MM:
                    continue
                direcao.normalize()
                interior = (centro_face - (inicio+fim)/2).normalized()
                # O raio exatamente na aresta pode ser coplanar a' outra
                # placa. Desloca-lo antes do ray cast evita perder a cruz.
                for lado in (-1, 1):
                    desloc = (interior + normal * lado) * TOLERANCIA_MM / 2
                    local, _n, _f, _d = destino['arvore'].ray_cast(
                        inicio + desloc, direcao, comprimento)
                    if local is None:
                        continue
                    for sinal in (-1, 1):
                        q = local + direcao * sinal * TOLERANCIA_MM / 2
                        if dentro(q, a) and dentro(q, b):
                            return list(q)
    return None


def malha(obj, depsgraph):
    avaliado = obj.evaluated_get(depsgraph)
    mesh = avaliado.to_mesh()
    try:
        return geometria([obj.matrix_world @ v.co * 1000 for v in mesh.vertices],
                         [list(f.vertices) for f in mesh.polygons],
                         [v.normalized() for v in obj.matrix_world.to_3x3().col])
    finally:
        avaliado.to_mesh_clear()


def excessos(pontos, matriz_mm, dimensoes):
    inversa = matriz_mm.inverted()
    locais = [inversa @ v for v in pontos]
    return [max(0., -min(v[k] for v in locais),
                max(v[k] for v in locais)-dimensoes[k]) for k in range(3)]


def auditar_modulo(objetos):
    addon = _base.addon
    grupos = [o for o in objetos if o.get('eh_grupo_gavetas') or o.get('eh_grupo_prateleiras')]
    for o in objetos:
        if o.get('eh_gaveta'):
            addon.gavetas.definir_abertura(o, 0)
        elif o.get('eh_folha_porta'):
            addon.ferragens._definir_abertura(bpy.context, o, 0)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    pecas = {o.name: malha(o, depsgraph) for o in objetos
             if o.type == 'MESH' and addon.chapas.MARCA_CHAPA in o}
    donos = {o.name: g.name for g in grupos for o in g.children_recursive if o.name in pecas}
    registros, envelopes, colisoes = [], {}, []
    for grupo in grupos:
        dono = addon.gavetas if grupo.get('eh_grupo_gavetas') else addon.prateleiras
        largura, altura, matriz = dono.vao(grupo)
        conj = dono.modulo_do_grupo(grupo)
        mundo = conj.matrix_world @ matriz if conj else grupo.matrix_world
        milimetros = mundo.copy()
        milimetros.translation *= 1000
        profundidade = float(dono.parametros(grupo)['profundidade_mm'])
        envelope = caixa(milimetros, (largura, profundidade, altura))
        envelopes[grupo.name] = envelope
        intrusos = []
        for nome, dados in pecas.items():
            if donos.get(nome) == grupo.name:
                continue
            ponto = ponto_de_colisao(envelope, dados)
            if ponto is not None:
                intrusos.append(dict(peca=nome, grupo=donos.get(nome), ponto_mm=ponto))
        fora = []
        for obj in grupo.children_recursive:
            if obj.name not in pecas or obj.get('gaveta_peca') in ('FRENTE', 'TRILHO'):
                continue
            e = excessos(pecas[obj.name]['pontos'], milimetros, (largura, profundidade, altura))
            if max(e) > TOLERANCIA_MM:
                fora.append(dict(peca=obj.name, excesso_xyz_mm=e))
        cantos = [Vector(v)/1000 for v in itertools.product((0, largura),
                                                           (0, profundidade), (0, altura))]
        desvio = max(((mundo @ v)-(grupo.matrix_world @ v)).length*1000 for v in cantos)
        registros.append(dict(nome=grupo.name, tipo='gavetas' if dono is addon.gavetas else 'prateleiras',
            largura_mm=largura, altura_mm=altura, profundidade_mm=profundidade,
            desvio_origem_mm=(mundo.translation-grupo.matrix_world.translation).length*1000,
            desvio_referencial_mm=desvio, pecas_fora_do_vao=fora, intrusos_no_envelope=intrusos,
            quantidade=len(dono.gavetas_do_grupo(grupo) if dono is addon.gavetas
                           else dono.prateleiras_do_grupo(grupo))))
    sobreposicoes = []
    for a, b in itertools.combinations(grupos, 2):
        penetracao = intersecao_de_envelopes(envelopes[a.name], envelopes[b.name])
        if penetracao is not None:
            sobreposicoes.append(dict(grupos=[a.name, b.name], penetracao_minima_mm=penetracao))
    for (na, a), (nb, b) in itertools.combinations(pecas.items(), 2):
        if na not in donos and nb not in donos:
            continue
        oa, ob = bpy.data.objects[na], bpy.data.objects[nb]
        # Encaixes da propria caixa nao sao interferencia entre sistemas.
        if (donos.get(na) == donos.get(nb) and oa.parent == ob.parent
                and oa.parent is not None and oa.parent.get('eh_gaveta')):
            continue
        if not a['fechada'] or not b['fechada']:
            continue
        ponto = ponto_de_colisao(a, b)
        if ponto is not None:
            colisoes.append(dict(pecas=[na, nb], grupos=[donos.get(na), donos.get(nb)],
                penetracao_minima_envelopes_mm=intersecao_de_envelopes(a, b), ponto_mm=ponto))
    return dict(grupos=registros, sobreposicoes_de_envelopes=sobreposicoes,
                colisoes_de_pecas=colisoes,
                malhas_nao_fechadas=[n for n, dados in pecas.items() if not dados['fechada']])


def auditar(biblioteca, destino):
    _base.validar_destino(str(biblioteca), str(destino))
    biblioteca, destino = Path(biblioteca), Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    antes = {p.name: _base.digital(p) for p in biblioteca.iterdir() if p.is_file()}
    addon = _base.addon
    addon.opcoes._pasta_addon = lambda: str(destino / 'guarda')
    addon.biblioteca.pasta_biblioteca = lambda: str(destino / 'guarda')
    addon.register()
    addon.chapas._ocupado[0] = True
    resultados = []
    try:
        indice = json.loads((biblioteca / 'indice.json').read_text(encoding='utf-8'))
        itens = [it for it in indice if it.get('tipo') == 'modulo']
        for i, item in enumerate(itens, 1):
            _cols, objetos = _base.carregar(_base.caminho_da_peca(str(biblioteca), item['arquivo']))
            resultado = auditar_modulo(objetos)
            resultado.update(arquivo=item['arquivo'], niveis=list(addon.biblioteca.caminho_de(item)))
            resultados.append(resultado)
            if i % 25 == 0 or i == len(itens):
                print('[auditoria internos]', i, '/', len(itens), flush=True)
        depois = {p.name: _base.digital(p) for p in biblioteca.iterdir() if p.is_file()}
        if antes != depois:
            raise RuntimeError('A biblioteca mudou durante a auditoria')
        tipos = Counter(g['tipo'] for r in resultados for g in r['grupos'])
        resumo = dict(modulos=len(resultados), grupos=dict(tipos),
            modulos_com_sobreposicao=sum(bool(r['sobreposicoes_de_envelopes']) for r in resultados),
            modulos_com_colisao=sum(bool(r['colisoes_de_pecas']) for r in resultados),
            modulos_com_malhas_abertas=sum(bool(r['malhas_nao_fechadas']) for r in resultados),
            modulos_com_pecas_fora_do_vao=sum(any(g['pecas_fora_do_vao'] for g in r['grupos']) for r in resultados),
            modulos_com_referencial_desalinhado=sum(any(g['desvio_referencial_mm'] > TOLERANCIA_MM
                for g in r['grupos']) for r in resultados),
            biblioteca_preservada=True, tolerancia_mm=TOLERANCIA_MM)
        relatorio = dict(resumo=resumo, modulos=resultados)
        (destino / 'auditoria.json').write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(resumo, ensure_ascii=False), flush=True)
        return relatorio
    finally:
        _base.limpar()
        addon.chapas._ocupado[0] = False
        addon.unregister()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--biblioteca', default=str(RAIZ / 'archy_builder/biblioteca'))
    parser.add_argument('--destino', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    auditar(args.biblioteca, args.destino)


if __name__ == '__main__':
    main()
