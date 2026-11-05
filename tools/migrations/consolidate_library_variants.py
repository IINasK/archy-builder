"""Remove audited library variants with external originals and reversible publication."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import tools.migrations.adjust_fits as base


def _ler(caminho):
    return json.loads(Path(caminho).read_text(encoding='utf-8'))


def _gravar(caminho, dados):
    Path(caminho).write_text(json.dumps(dados, ensure_ascii=False, indent=1)+'\n', encoding='utf-8')


def _arquivos(biblioteca):
    return {p.name:base.digital(p) for p in Path(biblioteca).iterdir()
            if p.is_file() and p.suffix in ('.blend','.png','.json','.txt')}


def _indice_novo(indice, retiradas):
    por_nome={i['arquivo']:i for i in indice}
    nomes=[r['arquivo'] for r in retiradas]
    if len(set(nomes))!=len(nomes) or not nomes:
        raise ValueError('Plano vazio ou com retiradas repetidas')
    for r in retiradas:
        item=por_nome.get(r['arquivo'])
        if item is None or item.get('tipo')!='modulo' or not r.get('motivo'):
            raise ValueError('Retirada sem modulo ou motivo: '+r['arquivo'])
        mantido=r.get('mantido')
        if mantido:
            outro=por_nome.get(mantido)
            if (outro is None or mantido in nomes
                    or base.addon.biblioteca.caminho_de(item)!=base.addon.biblioteca.caminho_de(outro)):
                raise ValueError('Variante conservada invalida: '+mantido)
    return [i for i in indice if i['arquivo'] not in nomes]


def preparar(biblioteca, destino, retiradas):
    base.validar_destino(str(biblioteca),str(destino))
    biblioteca=Path(biblioteca).resolve();destino=Path(destino)
    if destino.exists():
        raise ValueError('Destino ja existe; use outra pasta externa')
    indice=_ler(biblioteca/'indice.json')
    novo=_indice_novo(indice,retiradas)
    hashes=_arquivos(biblioteca)
    nomes={'indice.json','blender_assets.cats.txt'}
    for r in retiradas:
        blend=base.caminho_da_peca(str(biblioteca),r['arquivo'])
        nomes.update((Path(blend).name,Path(blend).with_suffix('.png').name))
    for nome in nomes:
        if nome not in hashes:
            raise ValueError('Arquivo ausente: '+nome)
    (destino/'originais').mkdir(parents=True)
    for nome in sorted(nomes):
        shutil.copy2(biblioteca/nome,destino/'originais'/nome)
        if base.digital(destino/'originais'/nome)!=hashes[nome]:
            raise RuntimeError('Backup diverge: '+nome)
    _gravar(destino/'indice_novo.json',novo)
    manifesto=dict(biblioteca=str(biblioteca),retiradas=retiradas,hashes=hashes,
                   originais=sorted(nomes),publicado=False)
    _gravar(destino/'manifesto.json',manifesto)
    return manifesto


def publicar(destino):
    destino=Path(destino);m=_ler(destino/'manifesto.json')
    biblioteca=Path(m['biblioteca'])
    base.validar_destino(str(biblioteca),str(destino))
    if m['publicado'] or _arquivos(biblioteca)!=m['hashes']:
        raise RuntimeError('Biblioteca mudou depois do preparo')
    for nome in m['originais']:
        original=base.caminho_da_peca(str(destino/'originais'),nome)
        if base.digital(original)!=m['hashes'][nome]:
            raise RuntimeError('Backup diverge: '+nome)
    novo=_indice_novo(_ler(destino/'originais/indice.json'),m['retiradas'])
    if novo!=_ler(destino/'indice_novo.json'):
        raise RuntimeError('Indice preparado diverge do plano')
    retirados=[base.caminho_da_peca(str(biblioteca),nome) for nome in m['originais']
               if Path(nome).suffix in ('.blend','.png')]
    temporario=biblioteca/'indice.json.tmp'
    try:
        shutil.copyfile(destino/'indice_novo.json',temporario)
        os.replace(temporario,biblioteca/'indice.json')
        for caminho in retirados:
            Path(caminho).unlink()
        esperados={n:h for n,h in m['hashes'].items() if n not in {Path(p).name for p in retirados}}
        esperados['indice.json']=base.digital(destino/'indice_novo.json')
        if _arquivos(biblioteca)!=esperados:
            raise RuntimeError('Conferencia final da biblioteca diverge')
        m['publicado']=True
        _gravar(destino/'manifesto.json',m)
    except BaseException:
        for nome in m['originais']:
            shutil.copy2(destino/'originais'/nome,biblioteca/nome)
        temporario.unlink(missing_ok=True)
        raise
    return m


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--biblioteca',default=base.addon.biblioteca.pasta_biblioteca())
    p.add_argument('--destino',required=True)
    p.add_argument('--plano',help='JSON com lista de retiradas auditadas')
    p.add_argument('--aplicar',action='store_true')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:])
    if args.aplicar:
        m=publicar(args.destino)
    else:
        if not args.plano:p.error('--plano e obrigatorio no preparo')
        m=preparar(args.biblioteca,args.destino,_ler(args.plano))
    print(json.dumps(dict(retirados=len(m['retiradas']),publicado=m['publicado']),indent=1))


if __name__=='__main__':main()
