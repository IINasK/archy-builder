"""Regera PNG/preview de modulos, conservando montagem/parametros do .blend.
Preparo fora da biblioteca com backup e hashes; --aplicar publica.
"""
import argparse,json,os,shutil,sys
import bpy
RAIZ=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,RAIZ)
from ajustar_encaixes_promob import addon,carregar,limpar,estado,conferir,digital,publicar
from ajustar_encaixes_promob import validar_destino


def preparar(biblioteca,destino):
    validar_destino(biblioteca, destino)
    novos,originais=[os.path.join(destino,p) for p in ('novos','originais')]
    os.makedirs(novos,exist_ok=False);os.makedirs(originais,exist_ok=False)
    addon.opcoes._pasta_addon=lambda:novos
    addon.biblioteca.pasta_biblioteca=lambda:novos
    addon.register()
    m=dict(biblioteca=biblioteca,versao=addon.bl_info['version'],arquivos=[],modulos=[],publicado=False)
    for it in json.load(open(os.path.join(biblioteca,'indice.json'),encoding='utf-8')):
        if it.get('tipo')!='modulo':continue
        nomes=[it['arquivo'],os.path.splitext(it['arquivo'])[0]+'.png']
        hashes={s:digital(os.path.join(biblioteca,s)) for s in nomes}
        for s in nomes:shutil.copy2(os.path.join(biblioteca,s),os.path.join(originais,s))
        blend,png=[os.path.join(novos,s) for s in nomes]
        shutil.copy2(os.path.join(biblioteca,nomes[0]),blend)
        cs,objs=carregar(blend)
        antes=estado(cs,objs)
        for conj in [o for o in objs if addon.chapas.MARCA_CONJUNTO in o]:
            addon.biblioteca.preparar_abertura_foto(bpy.context,conj)
        ok,msg=addon.biblioteca.fotografar_com_camera(png,list(bpy.data.objects))
        if not ok:raise RuntimeError(msg)
        limpar()
        ok,msg=addon.biblioteca.aplicar_preview_png(blend,png)
        if not ok:raise RuntimeError(msg)
        cs,objs=carregar(blend)
        conferir(antes,estado(cs,objs))
        for s in nomes:
            assert digital(os.path.join(biblioteca,s))==hashes[s]
            m['arquivos'].append(dict(nome=s,original=hashes[s],novo=digital(os.path.join(novos,s))))
        m['modulos'].append(dict(arquivo=it['arquivo']))
        print('[fotos]',len(m['modulos']),it['arquivo'],'montagem preservada',flush=True)
    limpar();addon.unregister()
    with open(os.path.join(destino,'manifesto.json'),'w',encoding='utf-8') as f:json.dump(m,f,indent=1)
    print('FOTOS VERIFICADAS',len(m['modulos']),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--destino',required=True)
    p.add_argument('--biblioteca',default=os.path.join(RAIZ,'cabinet_creator','biblioteca'))
    p.add_argument('--aplicar',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    validar_destino(a.biblioteca, a.destino)
    if a.aplicar:publicar(a.destino)
    else:preparar(a.biblioteca,a.destino)


if __name__=='__main__':main()
