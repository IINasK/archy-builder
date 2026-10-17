"""Revalida as conexoes de TODA a biblioteca, com preparo/backup/releitura.

Blender --background --factory-startup --python este_arquivo --
  --destino PASTA [--aplicar]
Somente o Canto Sup Alto 11 recebe a correcao geometrica de arremate.
"""
import argparse
import json
import os
import shutil
import sys
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ajustar_encaixes_promob import addon, carregar, limpar, estado, conferir, digital, publicar
from ajustar_encaixes_promob import validar_destino

RAIZ = os.path.dirname(os.path.abspath(__file__))
ALVO = 'Canto_Sup_Alto_11_803x1056x415.blend'


def preparar(biblioteca, destino):
    validar_destino(biblioteca, destino)
    novos, originais = [os.path.join(destino, n) for n in ('novos', 'originais')]
    for pasta in (novos, originais):
        os.makedirs(pasta, exist_ok=True)
    manifesto_path = os.path.join(destino, 'manifesto.json')
    indice_path = os.path.join(biblioteca, 'indice.json')
    if os.path.exists(manifesto_path):
        m = json.load(open(manifesto_path, encoding='utf-8'))
        if m['indice'] != digital(indice_path) or m['publicado']:
            raise RuntimeError('Preparo ja publicado ou indice alterado')
    else:
        m = dict(biblioteca=biblioteca, versao=addon.bl_info['version'],
                 indice=digital(indice_path), arquivos=[], modulos=[],
                 auditados=[], publicado=False)
    addon.opcoes._pasta_addon = lambda: novos
    addon.biblioteca.pasta_biblioteca = lambda: novos
    addon.register()
    itens = [it for it in json.load(open(indice_path, encoding='utf-8'))
             if it.get('tipo') == 'modulo']
    for it in itens:
        nome = it['arquivo']
        if any(a['arquivo'] == nome for a in m['auditados']):
            continue
        fonte = os.path.join(biblioteca, nome)
        hash_original = digital(fonte)
        cs, objs = carregar(fonte)
        antes = estado(cs, objs)
        grupos = [o for o in objs if addon.chapas.MARCA_CONJUNTO in o]
        ligacoes_antes = sum(bool(addon.solda._vizinho_da_ponta(o, p))
            for g in grupos for o in addon.modulos._chapas_do_conjunto(g) for p in addon.chapas.PONTAS)
        arremates, conexoes = [], []
        for g in grupos:
            if nome == ALVO:
                arremates += addon.promob.alinhar_arremates(g)
            conexoes += addon.chapas.otimizar_adjacencia(addon.modulos._chapas_do_conjunto(g))
        esperado = estado(cs, objs)
        uids_criados = []
        for chave, dados in esperado['objetos'].items():
            if 'chapa_uid' not in antes['objetos'][chave]['props'] and 'chapa_uid' in dados['props']:
                antes['objetos'][chave]['props']['chapa_uid'] = dados['props']['chapa_uid']
                uids_criados.append(chave)
        # Estado ignora adj_*: tudo o mais deve ser identico, salvo a ripa.
        for chave in arremates:
            antes['objetos'][chave] = esperado['objetos'][chave]
        conferir(antes, esperado)
        ligacoes_depois = sum(bool(addon.solda._vizinho_da_ponta(o, p))
            for g in grupos for o in addon.modulos._chapas_do_conjunto(g) for p in addon.chapas.PONTAS)
        registro = dict(arquivo=nome, antes=ligacoes_antes, depois=ligacoes_depois,
                        chapas_conexoes=len(conexoes), arremates=arremates, uids_criados=uids_criados)
        if conexoes or arremates:
            shutil.copy2(fonte, os.path.join(originais, nome))
            if digital(os.path.join(originais, nome)) != hash_original:
                raise RuntimeError('Fonte mudou durante o preparo: ' + nome)
            blend = os.path.join(novos, nome)
            bpy.data.libraries.write(blend, set(cs) | set(objs), fake_user=True, compress=True)
            if arremates:
                png_nome = os.path.splitext(nome)[0] + '.png'
                png_fonte = os.path.join(biblioteca, png_nome)
                hash_png = digital(png_fonte)
                shutil.copy2(png_fonte, os.path.join(originais, png_nome))
                png = os.path.join(novos, png_nome)
                ok, motivo = addon.biblioteca.fotografar_com_camera(png, objs)
                if not ok:
                    raise RuntimeError(motivo)
                limpar()
                ok, motivo = addon.biblioteca.aplicar_preview_png(blend, png)
                if not ok:
                    raise RuntimeError(motivo)
                m['arquivos'].append(dict(nome=png_nome, original=hash_png, novo=digital(png)))
            cs, objs = carregar(blend)
            conferir(esperado, estado(cs, objs))
            for g in (o for o in objs if addon.chapas.MARCA_CONJUNTO in o):
                if addon.chapas.otimizar_adjacencia(addon.modulos._chapas_do_conjunto(g)):
                    raise AssertionError('Conexoes nao estaveis ao reabrir: ' + nome)
                if nome == ALVO and addon.promob.alinhar_arremates(g):
                    raise AssertionError('Arremate ainda fora da quina')
            m['arquivos'].append(dict(nome=nome, original=hash_original, novo=digital(blend)))
            m['modulos'].append(registro)
        m['auditados'].append(registro)
        with open(manifesto_path, 'w', encoding='utf-8') as f:
            json.dump(m, f, ensure_ascii=True, indent=1)
        if len(m['auditados']) % 25 == 0 or nome == ALVO:
            print('[biblioteca249]', len(m['auditados']), '/', len(itens),
                  'alterados', len(m['modulos']), nome, flush=True)
    limpar()
    addon.unregister()
    print('[biblioteca249] PREPARO VALIDADO:', len(m['auditados']), 'modulos;',
          sum(a['antes'] for a in m['auditados']), '->', sum(a['depois'] for a in m['auditados']),
          'ligacoes', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--destino', required=True)
    parser.add_argument('--biblioteca', default=os.path.join(RAIZ, 'cabinet_creator', 'biblioteca'))
    parser.add_argument('--aplicar', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    destino, biblioteca = os.path.abspath(args.destino), os.path.abspath(args.biblioteca)
    validar_destino(biblioteca, destino)
    if args.aplicar:
        m = json.load(open(os.path.join(destino, 'manifesto.json'), encoding='utf-8'))
        indice = json.load(open(os.path.join(biblioteca, 'indice.json'), encoding='utf-8'))
        if m['indice'] != digital(os.path.join(biblioteca, 'indice.json')) or len(m['auditados']) != sum(i.get('tipo') == 'modulo' for i in indice):
            raise RuntimeError('Auditoria de toda a biblioteca nao foi concluida')
        publicar(destino)
    else:
        preparar(biblioteca, destino)
