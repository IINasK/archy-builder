"""Stage left-opening door adjustments with backup, reopen checks and publication."""
from pathlib import Path
import argparse,json,os,shutil,sys
import bpy
RAIZ=str(Path(__file__).resolve().parents[2]);sys.path.insert(0,RAIZ)
from tools.migrations.adjust_fits import addon,carregar,limpar,estado,conferir,digital,publicar
from tools.migrations.adjust_fits import validar_destino
from tools.migrations.audit_and_repair_integration import verificar_funcoes


def preparar(biblioteca,destino):
    validar_destino(biblioteca, destino)
    novos,originais=[os.path.join(destino,p) for p in ('novos','originais')]
    os.makedirs(novos,exist_ok=False);os.makedirs(originais,exist_ok=False)
    addon.opcoes._pasta_addon=lambda:novos;addon.biblioteca.pasta_biblioteca=lambda:novos;addon.register()
    m=dict(biblioteca=biblioteca,versao=addon.bl_info['version'],arquivos=[],modulos=[],apoios_preservados=[],verificados=0,publicado=False)
    for it in json.load(open(os.path.join(biblioteca,'indice.json'),encoding='utf-8')):
        if it.get('tipo')!='modulo':continue
        nomes=[it['arquivo'],os.path.splitext(it['arquivo'])[0]+'.png']
        hashes={s:digital(os.path.join(biblioteca,s)) for s in nomes}
        cs,objs=carregar(os.path.join(biblioteca,nomes[0]))
        conj,=[o for o in objs if addon.chapas.MARCA_CONJUNTO in o]
        antes=estado(cs,objs)
        # Os descendentes sao copiados por NOME antes da reconfiguracao.
        sistemas={o.name for g in addon.portas._portas_do_conjunto(conj) for o in [g,*g.children_recursive]}
        alteradas=addon.portas.preferir_esquerda_no_modulo(bpy.context,conj)
        for g in addon.portas._portas_do_conjunto(conj):
            p=g['porta_parametros']
            if p.get('abertura') in ('GIRO','ZIGZAG') and p.get('dobradica_lado')=='DIREITA' and int(p.get('folhas',1))==1:
                m['apoios_preservados'].append(dict(arquivo=it['arquivo'],grupo=g.name))
        m['verificados']+=1
        if not alteradas:continue
        bpy.context.view_layer.update()
        depois=estado(list(bpy.data.collections),list(bpy.data.objects))
        for nome,dados in antes['objetos'].items():
            if nome not in sistemas:conferir(dados,depois['objetos'][nome],nome)
        conferir(antes['assets'],depois['assets'])
        for g in addon.portas._portas_do_conjunto(conj):
            for f in addon.portas._folhas_portas(g):
                dado=antes['objetos'][f.name];novo=depois['objetos'][f.name]
                for chave in ('medidas','materiais'):conferir(dado[chave],novo[chave],f.name+'/'+chave)
        for s in nomes:shutil.copy2(os.path.join(biblioteca,s),os.path.join(originais,s))
        blend,png=[os.path.join(novos,s) for s in nomes]
        bpy.data.libraries.write(blend,set(bpy.data.collections)|set(bpy.data.objects),fake_user=True)
        salvar=estado(list(bpy.data.collections),list(bpy.data.objects))
        addon.biblioteca.preparar_abertura_foto(bpy.context,conj)
        ok,msg=addon.biblioteca.fotografar_com_camera(png,list(bpy.data.objects))
        if not ok:raise RuntimeError(msg)
        limpar();ok,msg=addon.biblioteca.aplicar_preview_png(blend,png)
        if not ok:raise RuntimeError(msg)
        cs,objs=carregar(blend);conferir(salvar,estado(cs,objs))
        conj,=[o for o in objs if addon.chapas.MARCA_CONJUNTO in o]
        verificar_funcoes(conj)
        for s in nomes:
            assert digital(os.path.join(biblioteca,s))==hashes[s]
            m['arquivos'].append(dict(nome=s,original=hashes[s],novo=digital(os.path.join(novos,s))))
        m['modulos'].append(dict(arquivo=it['arquivo'],portas=alteradas))
        print('[esquerda]',it['arquivo'],alteradas,flush=True)
    limpar();addon.unregister()
    json.dump(m,open(os.path.join(destino,'manifesto.json'),'w',encoding='utf-8'),indent=1)
    print('VERIFICADOS',m['verificados'],'CORRIGIDOS',len(m['modulos']),'APOIOS PRESERVADOS',len(m['apoios_preservados']),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--destino',required=True)
    p.add_argument('--biblioteca',default=os.path.join(RAIZ,'cabinet_creator','biblioteca'));p.add_argument('--aplicar',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    validar_destino(a.biblioteca, a.destino)
    if a.aplicar:publicar(a.destino)
    else:preparar(a.biblioteca,a.destino)


if __name__=='__main__':main()
