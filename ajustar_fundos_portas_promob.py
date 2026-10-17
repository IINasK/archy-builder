"""Prepara fundos recuados e ilhas de frente unica, com backup verificavel.
Blender --background --factory-startup --python este_arquivo --
    --destino PASTA_BACKUP [--aplicar]
"""
import argparse, json, os, shutil, sys
import bpy
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree
RAIZ=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,RAIZ)
from ajustar_encaixes_promob import addon,carregar,limpar,estado,conferir,digital,publicar
from ajustar_encaixes_promob import validar_destino


def faces_das_portas(conj):
    saida=[]
    for grupo in addon.portas._portas_do_conjunto(conj):
        folhas=addon.portas._folhas_portas(grupo)
        if not folhas or grupo['porta_parametros']['abertura']=='CORRER':continue
        fora=addon.ferragens._matriz_fechada(folhas[0]).to_3x3().col[2].normalized()
        direita=Vector((0,0,1)).cross(fora).normalized()
        ref=Matrix((direita,-fora,Vector((0,0,1)))).transposed()
        saida.append(dict(grupo=grupo,referencia=ref,
            folhas=[dict(lo=[0,0,0],hi=[f.chapa_largura_mm,0,f.chapa_comprimento_mm]) for f in folhas]))
    return saida


def retirar_portas_opostas(conj):
    faces=faces_das_portas(conj)
    mantidas=addon.promob.portas_sem_faces_opostas(faces)
    retirar=[p for p in faces if p not in mantidas]
    if not retirar:return []
    nomes=[]
    material=None
    for p in retirar:
        grupo=p['grupo'];nomes.append(grupo.name)
        folha=addon.portas._folhas_portas(grupo)[0]
        material=next((s.material for s in folha.material_slots if s.material),material)
        objetos=[o.name for o in [grupo,*grupo.children_recursive]]
        for nome in reversed(objetos):
            obj=bpy.data.objects.get(nome)
            if obj is not None:addon.ferragens._remover_ferragem(obj)
    # Os sistemas ja' existentes conservam sua geometria mundial.
    prateleiras=[(g,list(addon.prateleiras.prateleiras_do_grupo(g)))
                 for g in addon.prateleiras.grupos_do_modulo(conj)]
    addon.promob.orientar_modulo(conj,dict(portas=mantidas,gavetas=[]))
    for antigo,pecas in prateleiras:
        nome=antigo.name
        novo=addon.promob._prateleiras_do_plano(bpy.context,conj,[dict(obj=o) for o in pecas])
        bpy.data.objects.remove(antigo,do_unlink=True)
        novo.name=nome
    for grupo in addon.gavetas.grupos_do_modulo(conj):
        ref=conj.matrix_world.to_3x3().inverted() @ grupo.matrix_world.to_3x3().normalized()
        grupo[addon.gavetas.CHAVE_REFERENCIA]=[v for linha in ref for v in linha]
    addon.gavetas.atualizar_gavetas_do_conjunto(conj)
    fundo=addon.modulos.adicionar_fundo(conj,bpy.context)
    if material is not None:
        fundo.data.materials.clear();fundo.data.materials.append(material)
        fundo.material_slots[0].link='OBJECT';fundo.material_slots[0].material=material
    bpy.context.view_layer.update()
    for p in mantidas:addon.portas.gravar_vao_orientado(p['grupo'],conj)
    addon.chapas.detectar_adjacencia(addon.modulos._chapas_do_conjunto(conj))
    addon.modulos.sincronizar_medidas_conjunto(conj)
    return nomes


def preparar(biblioteca,destino):
    validar_destino(biblioteca, destino)
    novos,originais=[os.path.join(destino,p) for p in ('novos','originais')]
    os.makedirs(novos,exist_ok=False);os.makedirs(originais,exist_ok=False)
    addon.opcoes._pasta_addon=lambda:novos
    addon.biblioteca.pasta_biblioteca=lambda:novos
    addon.register()
    manifesto=dict(biblioteca=biblioteca,versao=addon.bl_info['version'],arquivos=[],modulos=[],verificados=0,publicado=False)
    for it in json.load(open(os.path.join(biblioteca,'indice.json'),encoding='utf-8')):
        if it.get('tipo')!='modulo':continue
        arquivos=[it['arquivo'],it['arquivo'].replace('.blend','.png')]
        hashes={s:digital(os.path.join(biblioteca,s)) for s in arquivos}
        cols,objs=carregar(os.path.join(biblioteca,arquivos[0]))
        conj,=[o for o in objs if addon.chapas.MARCA_CONJUNTO in o]
        antes=estado(cols,objs)
        malhas={o.name:[o.matrix_world @ v.co for v in o.data.vertices]
                for o in objs if o.type=='MESH' and addon.chapas.MARCA_CHAPA in o}
        portas=retirar_portas_opostas(conj)
        fundos=addon.promob.ajustar_recuo_fundos(conj)
        internos=addon.promob.ajustar_internos_ao_fundo(conj) if portas or fundos else []
        manifesto['verificados']+=1
        if not portas and not fundos:continue
        bpy.context.view_layer.update()
        depois=estado(list(bpy.data.collections),list(bpy.data.objects))
        deslocadas={n for n,_delta in fundos}
        ajustadas={o.name for g in bpy.data.objects if g.name in internos for o in g.children_recursive}
        for o in bpy.data.objects:
            if o.name not in malhas or o.name in deslocadas:continue
            if o.name in ajustadas:
                # Frentes, altura e largura nao mudam para caber o fundo.
                a=malhas[o.name];b=[o.matrix_world @ v.co for v in o.data.vertices]
                inv=conj.matrix_world.inverted();a=[inv@v for v in a];b=[inv@v for v in b]
                for k in (0,2):
                    assert abs(min(v[k] for v in a)-min(v[k] for v in b))<1e-5,o.name
                    assert abs(max(v[k] for v in a)-max(v[k] for v in b))<1e-5,o.name
                if o.get(addon.gavetas.MARCA_PECA)!='TRASEIRA':
                    assert abs(min(v.y for v in a)-min(v.y for v in b))<1e-5,o.name
                conferir(antes['objetos'][o.name]['materiais'],depois['objetos'][o.name]['materiais'],o.name+'/material')
                if addon.prateleiras.MARCA_PRATELEIRA in o:
                    assert antes['objetos'][o.name]['props'].get('chapa_uid')==o.get('chapa_uid')
                continue
            kd=KDTree(len(malhas[o.name]))
            for i,v in enumerate(malhas[o.name]):kd.insert(v,i)
            kd.balance()
            if len(o.data.vertices)!=len(malhas[o.name]) or any(kd.find(o.matrix_world @ v.co)[2]>1e-5 for v in o.data.vertices):
                raise AssertionError('Geometria mudou: '+o.name)
            conferir(antes['objetos'][o.name]['materiais'],depois['objetos'][o.name]['materiais'],o.name+'/material')
            assert antes['objetos'][o.name]['props'].get('chapa_uid')==o.get('chapa_uid')
        for nome,delta in fundos:
            conferir(antes['objetos'][nome]['malha'],depois['objetos'][nome]['malha'],nome+'/malha')
            conferir(antes['objetos'][nome]['medidas'],depois['objetos'][nome]['medidas'],nome+'/medidas')
        conferir(antes['assets'],depois['assets'],'Catalogos')
        assert not addon.promob.fundos_a_recuar(conj)
        faces=faces_das_portas(conj)
        assert len(addon.promob.portas_sem_faces_opostas(faces))==len(faces)
        for a in arquivos:shutil.copy2(os.path.join(biblioteca,a),os.path.join(originais,a))
        blend,png=[os.path.join(novos,s) for s in arquivos]
        bpy.data.libraries.write(blend,set(bpy.data.collections)|set(bpy.data.objects),fake_user=True)
        salvo=estado(list(bpy.data.collections),list(bpy.data.objects))
        addon.biblioteca.preparar_abertura_foto(bpy.context,conj)
        ok,msg=addon.biblioteca.fotografar_com_camera(png,list(bpy.data.objects))
        if not ok:raise RuntimeError(msg)
        limpar();ok,msg=addon.biblioteca.aplicar_preview_png(blend,png)
        if not ok:raise RuntimeError(msg)
        cs,os_=carregar(blend);conferir(salvo,estado(cs,os_))
        for s in arquivos:
            assert digital(os.path.join(biblioteca,s))==hashes[s]
            manifesto['arquivos'].append(dict(nome=s,original=hashes[s],novo=digital(os.path.join(novos,s))))
        manifesto['modulos'].append(dict(arquivo=it['arquivo'],fundos=fundos,portas_retiradas=portas,internos=internos))
        print('[fundos/portas]',it['nome'],fundos,portas,flush=True)
    limpar();addon.unregister()
    json.dump(manifesto,open(os.path.join(destino,'manifesto.json'),'w',encoding='utf-8'),indent=1)
    print('VERIFICADOS',manifesto['verificados'],'CORRIGIDOS',len(manifesto['modulos']),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--destino',required=True)
    p.add_argument('--biblioteca',default=os.path.join(RAIZ,'cabinet_creator','biblioteca'))
    p.add_argument('--aplicar',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    validar_destino(a.biblioteca, a.destino)
    if a.aplicar:publicar(a.destino)
    else:preparar(a.biblioteca,a.destino)


if __name__=='__main__':main()
