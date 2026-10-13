"""Biblioteca de presets: pastas, catalogos, indice, inserir/arrastar
preset, miniaturas, foto clicavel, barra de tamanho, bloquear e salvar,
Asset Browser e prateleira. Mora aqui tambem o wireframe das medidas
(usado pela gaveta e pelo painel N)."""

import bpy, math, os, uuid, json, gpu, time
import bpy.utils.previews
from gpu_extras.batch import batch_for_shader
from mathutils import Euler, Matrix, Vector
from mathutils.geometry import intersect_line_plane
from bpy_extras import view3d_utils
from bpy.types import Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _modulos = _opcoes = _selecao = _gaveta = None
_portas = _puxadores = _ferragens = None

# ================================================== BIBLIOTECA / ASSETS
# Salva chapas e modulos na biblioteca de assets do Blender, para
# reaproveitar via Asset Browser (arrastar para a cena).
#
# Cada preset vira um .blend proprio dentro da pasta da biblioteca.
# Um arquivo por preset evita ter que reabrir e mesclar um .blend
# compartilhado a cada gravacao.
SUBPASTA_BIB = "Cabinet Creator"
# Raiz UNICA dos catalogos do Asset Browser. Trocar o CAMINHO de um
# catalogo e' seguro desde que o UUID nao mude: o .blend guarda o UUID,
# e e' por ele que o Blender reencontra o asset. Por isso as raizes
# antigas sao RENOMEADAS (mesmo UUID), nunca recriadas.
CAT_RAIZ = "Cabinet Creator"
RAIZES_ANTIGAS = ("Chapa G3",)

# Uma unica biblioteca de assets. Os nomes abaixo sao os que o addon ja'
# registrou em versoes anteriores e agora precisa recolher.
NOME_BIBLIOTECA = "Cabinet Creator"
BIBLIOTECAS_ANTIGAS = (
    "Chapa G3 (fabrica)", "Chapa G3 (equipe)",
    "Cabinet Creator (fabrica)", "Cabinet Creator (equipe)",
)
CAT_CHAPAS = CAT_RAIZ + "/Chapas"
CAT_MODULOS = CAT_RAIZ + "/Modulos"


def pasta_biblioteca():
    """A UNICA biblioteca: a da empresa, que mora dentro do addon.

    Nao ha' mais separacao fabrica/equipe -- era ela que produzia duas
    entradas no seletor do Asset Browser. Quem quiser a biblioteca numa
    pasta de rede aponta `pasta_biblioteca` nas Preferencias.

    ATENCAO: gravar dentro do addon so' e' seguro porque a pasta e' o
    repositorio da empresa (junction feita por vincular_blender.py).
    Numa instalacao por .zip, uma atualizacao sobrescreve a pasta --
    nesse caso configure a pasta de rede nas Preferencias.
    """
    p = _opcoes._prefs()
    if p and getattr(p, "pasta_biblioteca", ""):
        destino = bpy.path.abspath(p.pasta_biblioteca)
    else:
        destino = _opcoes._pasta_addon()
    try:
        os.makedirs(destino, exist_ok=True)
    except Exception as e:
        print("[Cabinet Creator] biblioteca:", e)
    return destino


def registrar_bibliotecas(silencioso=True):
    """Registra as duas pastas como bibliotecas de assets do Blender,
    sem duplicar caso ja' estejam registradas."""
    registradas = []
    libs = bpy.context.preferences.filepaths.asset_libraries
    caminho = pasta_biblioteca()
    alvo = os.path.normcase(os.path.normpath(caminho))

    # A limpeza vem ANTES do registro. Uma entrada antiga podia apontar
    # para ESTA mesma pasta: removendo depois, o registro era pulado por
    # "ja' existe" e em seguida a entrada sumia -- o usuario ficava sem
    # biblioteca nenhuma ate' a proxima execucao.
    for i in range(len(libs) - 1, -1, -1):
        if libs[i].name in BIBLIOTECAS_ANTIGAS:
            try:
                libs.remove(libs[i])
            except Exception as e:
                if not silencioso:
                    print("[Cabinet Creator] remover biblioteca antiga:", e)

    ja = any(os.path.normcase(os.path.normpath(bpy.path.abspath(l.path))) == alvo
             for l in libs if l.path)
    if not ja:
        try:
            bpy.ops.preferences.asset_library_add(directory=caminho)
            libs[-1].name = NOME_BIBLIOTECA
            registradas.append(NOME_BIBLIOTECA)
        except Exception as e:
            if not silencioso:
                print("[Cabinet Creator] registro falhou:", e)

    # a cascata tem de existir ANTES do primeiro save, senao o Asset
    # Browser abre sem nenhuma pasta
    try:
        _garantir_catalogos(caminho)
    except Exception as e:
        if not silencioso:
            print("[Cabinet Creator] catalogos:", e)
    return registradas




def caminhos_catalogo():
    """Toda a ARVORE como caminhos de catalogo, em cascata.

    Cada nivel ganha a SUA propria linha: o Blender ate' desenha os pais
    implicitos, mas so' da' para ARQUIVAR um asset num nivel que exista
    como catalogo de verdade -- e a ideia e' poder arquivar em qualquer
    altura da cascata.
    """
    caminhos = [CAT_RAIZ]
    arvores = [ARVORE]
    try:
        arvores.append(_niveis_do_indice())
    except Exception as e:
        print("[Cabinet Creator] niveis do indice:", e)
    for arv in arvores:
        for n1, filhos in arv.items():
            caminhos.append("%s/%s" % (CAT_RAIZ, n1))
            for n2, netos in filhos.items():
                caminhos.append("%s/%s/%s" % (CAT_RAIZ, n1, n2))
                for n3 in netos:
                    caminhos.append("%s/%s/%s/%s" % (CAT_RAIZ, n1, n2, n3))
    return list(dict.fromkeys(caminhos))


def catalogo_de(n1, n2="", n3=""):
    """Caminho de catalogo mais fundo para os niveis escolhidos."""
    partes = [x for x in (n1, n2, n3) if x]
    if not partes:
        return ""
    return CAT_RAIZ + "/" + "/".join(partes)


def _migrar_raiz(caminho):
    """Troca uma raiz antiga pela atual, preservando o resto do caminho."""
    for velha in RAIZES_ANTIGAS:
        if caminho == velha:
            return CAT_RAIZ
        if caminho.startswith(velha + "/"):
            return CAT_RAIZ + caminho[len(velha):]
    return caminho


def _garantir_catalogos(raiz, extras=()):
    """Cria/atualiza o blender_assets.cats.txt com a cascata do addon.

    Linhas ja' existentes sao PRESERVADAS com o mesmo UUID: os presets
    guardam o UUID do catalogo dentro do .blend, entao gerar um novo
    faria o asset sumir da arvore do Asset Browser.
    """
    arq = os.path.join(raiz, "blender_assets.cats.txt")
    existentes = {}
    if os.path.exists(arq):
        for linha in open(arq, encoding="utf-8"):
            linha = linha.strip()
            if not linha or linha.startswith("#") or linha.startswith("VERSION"):
                continue
            partes = linha.split(":")
            if len(partes) >= 2:
                # raiz antiga vira a nova MANTENDO o UUID: assim o asset
                # continua achando o catalogo e nao sobra arvore dupla
                existentes.setdefault(_migrar_raiz(partes[1]), partes[0])
    for cam in list(caminhos_catalogo()) + [x for x in extras if x]:
        existentes.setdefault(cam, str(uuid.uuid4()))
    # nome simples = caminho com tracos, convencao do Blender
    texto = "VERSION 1\n\n" + "".join(
        "%s:%s:%s\n" % (existentes[cam], cam, cam.replace("/", "-"))
        for cam in sorted(existentes))
    _gravar_se_mudou(arq, texto)
    return existentes


def _gravar_se_mudou(arq, texto):
    """Grava `texto` em `arq` so' se mudou, e de forma ATOMICA.

    Todo registro do add-on passa por aqui. Antes o arquivo era reaberto
    com "w" (zera e regrava) a cada vez: com dois Blenders registrando
    juntos (o harness roda suites em paralelo; o usuario pode abrir dois),
    um lia o arquivo ja' zerado pelo outro e gerava UUID NOVO para todos
    os catalogos -- os presets perdiam a categoria (visto em 2026-10-09).
    Temporario + os.replace nunca mostra o arquivo pela metade. newline
    explicito: o .gitattributes forca LF (sem ele o Windows grava CRLF).
    """
    try:
        with open(arq, encoding="utf-8", newline="") as f:
            if f.read() == texto:
                return False
    except FileNotFoundError:
        pass
    temporario = "%s.%d.tmp" % (arq, os.getpid())
    with open(temporario, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
    for _tentativa in range(20):
        try:
            os.replace(temporario, arq)
            return True
        except PermissionError:
            # o Windows recusa a troca enquanto outro processo le
            time.sleep(0.05)
    try:
        os.remove(temporario)
    except OSError:
        pass
    return False


def refiliar_preset(caminho, niveis):
    """Reassina o catalogo de um preset JA' gravado no disco.

    O catalogo mora dentro do .blend (`asset_data.catalog_id`), nao no
    indice.json -- entao a unica forma de mover um preset de categoria
    e' carregar o datablock do asset, trocar o id e regravar o arquivo.

    Devolve (ok, mensagem).
    """
    cam = catalogo_de(*niveis)
    if not cam:
        return False, "item sem categoria no indice"
    if not os.path.exists(caminho):
        return False, "arquivo nao encontrado"
    ids = _garantir_catalogos(os.path.dirname(caminho), extras=(cam,))

    antes_col = set(bpy.data.collections)
    antes_obj = set(bpy.data.objects)
    with bpy.data.libraries.load(caminho) as (de, para):
        para.collections = list(de.collections)
        para.objects = list(de.objects)
    novas_col = [c for c in bpy.data.collections if c not in antes_col]
    novos_obj = [o for o in bpy.data.objects if o not in antes_obj]

    def limpar():
        for c in novas_col:
            try:
                bpy.data.collections.remove(c)
            except Exception:
                pass
        for o in novos_obj:
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass

    alvos = [d for d in list(novas_col) + list(novos_obj) if d.asset_data]
    if not alvos:
        limpar()
        return False, "nenhum asset dentro do arquivo"

    # so' o catalog_id e' gravavel: o Blender deriva o nome simples
    for d in alvos:
        d.asset_data.catalog_id = ids[cam]

    blocos = set(novas_col)
    for o in novos_obj:
        blocos.add(o)
        if o.data:
            blocos.add(o.data)
    try:
        bpy.data.libraries.write(caminho, blocos, fake_user=True,
                                 compress=True)
    except Exception as e:
        limpar()
        return False, str(e)
    limpar()
    return True, cam


LADO_PREVIEW = 128


def _pixels_png(caminho, lado=LADO_PREVIEW):
    """Le um PNG e devolve os pixels prontos para uma ImagePreview."""
    img = None
    try:
        img = bpy.data.images.load(caminho)
        # 'Raw' evita a conversao de espaco de cor: a preview guarda os
        # mesmos valores que o PNG, sem ganhar nem perder gama
        try:
            img.colorspace_settings.name = 'Raw'
        except Exception:
            pass
        if tuple(img.size) != (lado, lado):
            img.scale(lado, lado)
        return list(img.pixels)
    except Exception as e:
        print("[Cabinet Creator] preview:", e)
        return None
    finally:
        if img is not None:
            try:
                bpy.data.images.remove(img)
            except Exception:
                pass


def aplicar_preview_png(caminho_blend, caminho_png):
    """Grava a foto do preset DENTRO do .blend, como preview do asset.

    `asset_generate_preview()` NAO serve: ele so' enfileira um job
    assincrono de render, e o arquivo e' gravado antes de o job
    terminar -- por isso os presets chegavam ao Asset Browser com a
    preview vazia (128x128 zerada) e apareciam com o icone generico.
    Escrever os pixels a mao e' sincrono e sobrevive a gravacao.
    """
    if not os.path.exists(caminho_blend):
        return False, "blend nao encontrado"
    if not os.path.exists(caminho_png):
        return False, "sem foto (.png) ao lado do preset"
    pixels = _pixels_png(caminho_png)
    if not pixels:
        return False, "nao consegui ler a foto"

    antes_col = set(bpy.data.collections)
    antes_obj = set(bpy.data.objects)
    with bpy.data.libraries.load(caminho_blend) as (de, para):
        para.collections = list(de.collections)
        para.objects = list(de.objects)
    novas_col = [c for c in bpy.data.collections if c not in antes_col]
    novos_obj = [o for o in bpy.data.objects if o not in antes_obj]

    def limpar():
        for c in novas_col:
            try:
                bpy.data.collections.remove(c)
            except Exception:
                pass
        for o in novos_obj:
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass

    alvos = [d for d in list(novas_col) + list(novos_obj) if d.asset_data]
    if not alvos:
        limpar()
        return False, "nenhum asset dentro do arquivo"

    lado = (LADO_PREVIEW, LADO_PREVIEW)
    for d in alvos:
        try:
            d.preview_ensure()
        except Exception:
            pass
        pv = d.preview
        if pv is None:
            continue
        pv.image_size = lado
        pv.image_pixels_float = pixels
        # sem o nivel de icone o Asset Browser cai no icone generico
        pv.icon_size = lado
        pv.icon_pixels_float = pixels

    blocos = set(novas_col)
    for o in novos_obj:
        blocos.add(o)
        if o.data:
            blocos.add(o.data)
    try:
        bpy.data.libraries.write(caminho_blend, blocos, fake_user=True,
                                 compress=True)
    except Exception as e:
        limpar()
        return False, str(e)
    limpar()
    return True, "%d asset(s)" % len(alvos)


class OBJECT_OT_regerar_previews(Operator):
    """Regrava as fotos dos presets dentro dos .blend, para o Asset
    Browser deixar de mostrar o icone generico"""
    bl_idname = "object.cabinet_regerar_previews"
    bl_label = "Regerar Previews da Biblioteca"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        feitos, falhas = 0, []
        for it in indice_completo():
            blend = os.path.join(it["pasta"], it["arquivo"])
            png = os.path.join(
                it["pasta"], os.path.splitext(it["arquivo"])[0] + ".png")
            ok, msg = aplicar_preview_png(blend, png)
            if ok:
                feitos += 1
            else:
                falhas.append("%s: %s" % (it.get("nome", "?"), msg))
        for f in falhas:
            print("[Cabinet Creator] preview:", f)
        if falhas:
            self.report({'WARNING'},
                        "%d preview(s) gravada(s), %d sem foto -- salve o "
                        "preset de novo" % (feitos, len(falhas)))
        else:
            self.report({'INFO'}, "%d preview(s) gravada(s)" % feitos)
        return {'FINISHED'}


class OBJECT_OT_refiliar_catalogos(Operator):
    """Arquiva os presets da equipe nos catalogos da cascata, conforme a
    categoria de cada um no indice"""
    bl_idname = "object.cabinet_refiliar"
    bl_label = "Reorganizar Catalogos"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        feitos, falhas = 0, []
        for it in indice_completo():
            ok, msg = refiliar_preset(
                os.path.join(it["pasta"], it["arquivo"]), _niveis_de(it))
            if ok:
                feitos += 1
            else:
                falhas.append("%s: %s" % (it.get("nome", "?"), msg))
        for f in falhas:
            print("[Cabinet Creator] refiliar:", f)
        if falhas:
            self.report({'WARNING'},
                        "%d movido(s), %d falha(s) -- ver console"
                        % (feitos, len(falhas)))
        else:
            self.report({'INFO'}, "%d preset(s) reorganizado(s)" % feitos)
        return {'FINISHED'}


def _nome_arquivo_seguro(nome):
    limpo = "".join(ch if (ch.isalnum() or ch in " -_") else "_" for ch in nome).strip()
    return (limpo or "sem_nome").replace(" ", "_")


def salvar_na_biblioteca(objs, nome, como_colecao, niveis=None):
    """Grava os objetos num .blend da biblioteca.

    como_colecao=True agrupa tudo numa Collection e marca a COLLECTION
    como asset -- necessario para modulos, porque arrastar um objeto
    traz so' aquele objeto, enquanto arrastar uma colecao traz o
    conjunto inteiro.

    `niveis` = (n1, n2, n3): arquiva o asset no catalogo da CATEGORIA,
    que e' o que o Asset Browser mostra na cascata a esquerda. Sem
    niveis cai no catalogo por tipo (Chapas/Modulos), como antes.
    """
    raiz = destino = pasta_biblioteca()
    # sem niveis cai no catalogo por tipo; ele entra como extra para
    # existir no .cats.txt sem sujar o nivel 1 da cascata
    cam_cat = (catalogo_de(*niveis) if niveis else "") or (
        CAT_MODULOS if como_colecao else CAT_CHAPAS)
    ids_cat = _garantir_catalogos(raiz, extras=(cam_cat,))

    blocos = set()
    if como_colecao:
        col = bpy.data.collections.new(nome)
        for o in objs:
            col.objects.link(o)
        col.asset_mark()
        if col.asset_data:
            col.asset_data.catalog_id = ids_cat[cam_cat]
            col.asset_data.description = "Modulo G3 - %d peca(s)" % len(objs)
            col.asset_data.tags.new("chapa-g3")
        blocos.add(col)
    else:
        for o in objs:
            o.asset_mark()
            if o.asset_data:
                o.asset_data.catalog_id = ids_cat[cam_cat]
                o.asset_data.tags.new("chapa-g3")
    for o in objs:
        blocos.add(o)
        if o.data:
            blocos.add(o.data)

    # A preview do Asset Browser NAO e' gerada aqui: `asset_generate_preview`
    # e' assincrono e nunca chega a tempo da gravacao. Quem a grava e'
    # `aplicar_preview_png`, depois que a foto do preset existe.

    arquivo = os.path.join(destino, _nome_arquivo_seguro(nome) + ".blend")
    bpy.data.libraries.write(arquivo, blocos, fake_user=True, compress=True)

    if como_colecao:
        # a colecao foi criada so' para empacotar o asset
        bpy.data.collections.remove(col)
    return arquivo


# ======================================= ARVORE DA BIBLIOTECA (3 niveis)
# Cascata horizontal: nivel 1 no topo, nivel 2 abaixo ao clicar, nivel 3
# abaixo do 2. Ramos com lista vazia no nivel 3 terminam no nivel 2.
AMBIENTES = ["Sala", "Cozinha", "Varanda", "Quarto", "Banheiro", "Externo"]

ARVORE = {
    "Armarios": {
        "Sala":     ["Inferiores", "Superiores", "Cantos", "Estantes"],
        "Cozinha":  ["Inferiores", "Superiores", "Cantos", "Torres"],
        "Varanda":  ["Inferiores", "Superiores", "Bancadas"],
        "Quarto":   ["Inferiores", "Superiores", "Closets", "Gaveteiros"],
        "Banheiro": ["Gabinetes", "Espelheiras", "Nichos"],
        "Externo":  ["Inferiores", "Superiores", "Bancadas"],
    },
    "Chapas":     {"Avulsas": []},
    "Portas":     {"Abrir": [], "Correr": [], "Basculante": []},
    "Puxadores":  {"Perfil": [], "Alca": [], "Borda": [], "Cava": []},
    "Dobradicas": {"Comuns": [], "Amortecidas": [], "Especiais": []},
}


def _niveis_de(it):
    """Le os 3 niveis de um item do indice, aceitando o formato antigo
    (categoria/subcategoria) para nao invalidar indices ja' gravados."""
    n1 = it.get("n1")
    if n1:
        return n1, it.get("n2", ""), it.get("n3", "")
    cat, sub = it.get("categoria", ""), it.get("subcategoria", "")
    if cat in AMBIENTES:
        return "Armarios", cat, sub
    return cat, sub, ""


def _niveis_do_indice():
    """Categorias que EXISTEM nos presets salvos, alem das da ARVORE.

    E' o que integra as duas pontas: uma subcategoria digitada no "+"
    do painel N passa a aparecer na cascata e tambem vira catalogo.
    """
    extra = {}
    for it in indice_completo():
        a, b, c = _niveis_de(it)
        if not a:
            continue
        ramo = extra.setdefault(a, {})
        if b:
            filhos = ramo.setdefault(b, [])
            if c and c not in filhos:
                filhos.append(c)
    return extra


def _filhos_n2(n1):
    vistos = list(ARVORE.get(n1, {}).keys())
    for k in _niveis_do_indice().get(n1, {}):
        if k not in vistos:
            vistos.append(k)
    return vistos


def _filhos_n3(n1, n2):
    vistos = list(ARVORE.get(n1, {}).get(n2, []))
    for k in _niveis_do_indice().get(n1, {}).get(n2, []):
        if k not in vistos:
            vistos.append(k)
    return vistos


def _conta(itens, n1, n2=None, n3=None):
    n = 0
    for it in itens:
        a, b, c = _niveis_de(it)
        if a != n1:
            continue
        if n2 is not None and b != n2:
            continue
        if n3 is not None and c != n3:
            continue
        n += 1
    return n


NOME_INDICE = "indice.json"


def _ler_indice(pasta):
    """Indice em JSON ao lado dos .blend. Existe para o painel listar os
    presets sem precisar abrir cada arquivo -- abrir .blend so' para
    montar a lista deixaria a interface travada."""
    arq = os.path.join(pasta, NOME_INDICE)
    if not os.path.exists(arq):
        return []
    try:
        with open(arq, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("[Cabinet Creator] indice ilegivel:", e)
        return []


def _gravar_indice(pasta, itens):
    try:
        # newline explicito: o .gitattributes do projeto forca LF
        with open(os.path.join(pasta, NOME_INDICE), "w",
                  encoding="utf-8", newline="\n") as f:
            json.dump(itens, f, ensure_ascii=False, indent=1)
            f.write("\n")
    except Exception as e:
        print("[Cabinet Creator] nao gravei o indice:", e)


def indice_completo():
    """Le o indice da biblioteca da empresa."""
    pasta = pasta_biblioteca()
    itens = []
    for it in _ler_indice(pasta):
        it = dict(it)
        it["origem"] = "biblioteca"
        it["pasta"] = pasta
        itens.append(it)
    return itens


def registrar_no_indice(pasta, nome, arquivo, n1, n2, n3, tipo):
    itens = [i for i in _ler_indice(pasta)
             if not (i.get("arquivo") == os.path.basename(arquivo))]
    itens.append({"nome": nome, "arquivo": os.path.basename(arquivo),
                  "n1": n1, "n2": n2, "n3": n3, "tipo": tipo})
    _gravar_indice(pasta, itens)
def itens_de_fabrica():
    """Os modelos de FABRICA do criador de puxadores e das dobradicas, na
    cascata da biblioteca (pedido do usuario): TRAVADOS -- moram no add-on,
    fora do indice, entao nem o "Edit." nem o cadeado os alcancam. O
    usuario edita os DELE (categoria Puxadores) e o criador acompanha."""
    itens = []
    for tipo in _puxadores.MODELOS_PADRAO:
        nome = _puxadores.MODELOS_PUXADOR[tipo][0]
        it = foto_padrao('puxador_' + tipo)
        it.update(nome=nome, n1=_puxadores.CATEGORIA_PUXADORES, n2=nome,
                  n3='', tipo='objeto', bloqueado=True,
                  fabrica='puxador', valor=tipo)
        itens.append(it)
    for tipo, nome in _portas.NOME_DOBRADICA.items():
        it = foto_padrao('dobradica_' + tipo)
        it.update(nome=nome, n1='Dobradicas', n2='Comuns', n3='',
                  tipo='objeto', bloqueado=True, fabrica='dobradica',
                  valor=tipo)
        itens.append(it)
    return itens


def _itens_de(categoria, subcategoria):
    return [i for i in indice_completo()
            if i.get("categoria") == categoria and i.get("subcategoria") == subcategoria]


def inserir_preset(context, pasta, arquivo, tipo, destino=None):
    """Carrega o .blend do preset na cena e seleciona o que veio.

    Devolve (novos, raizes, erro). `destino` e' o deslocamento aplicado
    as raizes; sem ele o preset vai para o cursor 3D em vez de ser
    despejado na origem.
    """
    caminho = os.path.join(pasta, arquivo)
    if not os.path.exists(caminho):
        return [], [], "Arquivo nao encontrado: " + caminho
    antes = set(bpy.data.objects)
    with bpy.data.libraries.load(caminho) as (de, para):
        if tipo == "modulo" and de.collections:
            para.collections = list(de.collections)
        else:
            para.objects = list(de.objects)
    novas_cols = [c for c in bpy.data.collections
                  if c.library is None and c.name not in
                  [x.name for x in context.scene.collection.children]]
    for c in novas_cols:
        if any(o not in antes for o in c.objects):
            context.scene.collection.children.link(c)
    for o in bpy.data.objects:
        if o not in antes and o.name not in [x.name for c in novas_cols for x in c.objects]:
            if o.name not in context.scene.collection.objects:
                try:
                    context.scene.collection.objects.link(o)
                except Exception:
                    pass
    novos = [o for o in bpy.data.objects if o not in antes]

    raizes = [o for o in novos if o.parent is None or o.parent not in novos]
    desloc = context.scene.cursor.location.copy() if destino is None else destino
    for o in raizes:
        o.location = o.location + desloc

    for o in context.selected_objects:
        o.select_set(False)
    for o in novos:
        try:
            o.select_set(True)
        except Exception:
            pass
    # o "olho" das pecas auxiliares do rig e' da camada de visualizacao,
    # nao do objeto: no .blend do preset ele nao vem
    _ferragens.ocultar_pecas_do_rig(novos)
    return novos, raizes, ""


class OBJECT_OT_inserir_preset(Operator):
    """Traz o preset da biblioteca para o cursor 3D"""
    bl_idname = "object.cabinet_inserir_preset"
    bl_label = "Inserir"
    bl_options = {'REGISTER', 'UNDO'}

    pasta: bpy.props.StringProperty()
    arquivo: bpy.props.StringProperty()
    tipo: bpy.props.StringProperty(default="modulo")

    def execute(self, context):
        novos, _raizes, erro = inserir_preset(
            context, self.pasta, self.arquivo, self.tipo)
        if erro:
            self.report({'ERROR'}, erro)
            return {'CANCELLED'}
        self.report({'INFO'}, "%d objeto(s) inserido(s)" % len(novos))
        return {'FINISHED'}


# O segundo clique do duplo na foto pode tremer um pouco
RAIO_DUPLO_CLIQUE_PX = 8


class OBJECT_OT_arrastar_preset(Operator):
    """Arrasta com mira e caixa exata antes de inserir na cena"""
    bl_idname = "object.cabinet_arrastar_preset"
    bl_label = "Arrastar para a Cena"
    bl_options = {'REGISTER', 'UNDO'}

    # SKIP_SAVE: as props do operador persistem entre execucoes no
    # Blender, e o arraste precisa descobri-las de novo a cada vez
    pasta: bpy.props.StringProperty(options={'SKIP_SAVE'})
    arquivo: bpy.props.StringProperty(options={'SKIP_SAVE'})
    tipo: bpy.props.StringProperty(default="modulo", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        # Sem preset nas props, o arraste comecou sobre a grade: o bloco
        # sob o cursor e' lido em context.button_operator, que entrega as
        # propriedades do botao apontado (o mesmo recurso que o Blender
        # usa para "Atribuir Atalho" no menu de contexto de um botao).
        if not self.arquivo:
            alvo = getattr(context, "button_operator", None)
            # O botao de importacao, o cadeado e o lapis tambem carregam
            # `arquivo`: so' miniatura e nome (este proprio operador)
            # valem como pega do arraste.
            origem = getattr(getattr(alvo, "bl_rna", None), "identifier", "")
            arquivo = (getattr(alvo, "arquivo", "")
                       if origem.endswith("cabinet_arrastar_preset") else "")
            if not arquivo:
                # arraste em qualquer outro lugar da sidebar: devolve o
                # evento para o Blender, senao sliders parariam de andar
                return {'PASS_THROUGH'}
            self.pasta = getattr(alvo, "pasta", "")
            self.arquivo = arquivo
            self.tipo = getattr(alvo, "tipo", "modulo") or "modulo"
            self._arrastando = True
            self._mouse_inicio = (event.mouse_x, event.mouse_y)
            self._moveu = False
        else:
            self._arrastando = _gaveta._eh_area_gaveta(context)
            self._mouse_inicio = (event.mouse_x, event.mouse_y)
            self._moveu = not self._arrastando

        # relogio do 1o clique: o duplo na foto e' medido a partir dele
        self._instante_inicio = time.monotonic()
        # a grade vive na sidebar, entao a regiao do evento NAO e' a
        # viewport: a janela de desenho tem de ser procurada na area
        self._area_preview = context.area
        if _gaveta._eh_area_gaveta(context):
            self._area_preview = next(
                (a for a in context.screen.areas
                 if a.type == 'VIEW_3D' and a != context.area
                 and a.x > context.area.x
                 and a.y == context.area.y), None)
        self._regiao = next(
            (r for r in self._area_preview.regions if r.type == 'WINDOW'), None
        ) if self._area_preview else None
        self._rv3d = getattr(self._area_preview.spaces.active, "region_3d", None
                             ) if self._area_preview else None
        if self._regiao is None or self._rv3d is None:
            self.report({'ERROR'}, "Sem viewport 3D para posicionar")
            return {'CANCELLED'}
        # O draw handler pode ser chamado no primeiro redraw logo depois de
        # registrado; deixe o filtro de regiao pronto antes desse momento.
        self._regiao_ptr = self._regiao.as_pointer()

        self._selecionados_antes = list(context.selected_objects)
        self._ativo_antes = context.view_layer.objects.active
        colecoes_antes = set(bpy.data.collections)
        self._novos = []
        self._raizes = []
        self._colecoes_novas = []

        # O preset entra oculto como staging. So' se torna visivel quando
        # o usuario solta dentro da viewport; cancelar apaga tudo.
        novos, raizes, erro = inserir_preset(
            context, self.pasta, self.arquivo, self.tipo,
            destino=Vector((0.0, 0.0, 0.0)))
        self._novos = list(novos or [])
        self._raizes = list(raizes or [])
        self._colecoes_novas = [c for c in bpy.data.collections
                                if c not in colecoes_antes]
        if erro:
            self._apagar()
            self._restaurar_selecao(context)
            self.report({'ERROR'}, erro)
            return {'CANCELLED'}
        if not self._novos:
            self._apagar()
            self._restaurar_selecao(context)
            self.report({'WARNING'}, "O preset nao trouxe nenhum objeto")
            return {'CANCELLED'}

        self._base = {o: o.location.copy() for o in self._raizes}
        self._altura = context.scene.cursor.location.z
        self._alvo = None
        self._normal = Vector((0.0, 0.0, 1.0))
        self._bbox_atual = []
        self._valido = False
        self._em_superficie = False
        self._handler_preview = None

        try:
            self._preparar_bbox(context)
            self._ocultar_staging(context)
            self._handler_preview = bpy.types.SpaceView3D.draw_handler_add(
                self._desenhar_preview, (), 'WINDOW', 'POST_VIEW')
        except Exception as e:
            print("[Cabinet Creator] preview do arraste:", e)
            self._apagar()
            self._restaurar_selecao(context)
            self.report({'ERROR'}, "Nao consegui preparar o preview")
            return {'CANCELLED'}

        try:
            item = _achar_item(self.pasta, self.arquivo)
            nome = item.get("nome", self.arquivo) if item else self.arquivo
            context.workspace.status_text_set(
                "Arrastando %s | Solte: inserir | Botao direito: cancelar"
                % nome)
        except Exception:
            pass
        self._mover(context, event)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _preparar_bbox(self, context):
        """Mede o staging avaliado e define a ancora no centro da base."""
        context.view_layer.update()
        try:
            dep = context.evaluated_depsgraph_get()
        except Exception:
            dep = None
        pontos = []
        for obj in self._novos:
            if obj.type in _modulos.TIPOS_COM_VOLUME:
                pontos.extend(_modulos._cantos_avaliados(obj, dep))
        if not pontos:
            pontos = [o.matrix_world.translation.copy() for o in self._raizes]
        if not pontos:
            raise RuntimeError("preset sem geometria")

        lo = Vector(tuple(min(p[i] for p in pontos) for i in range(3)))
        hi = Vector(tuple(max(p[i] for p in pontos) for i in range(3)))
        self._bbox_base = (
            Vector((lo.x, lo.y, lo.z)), Vector((hi.x, lo.y, lo.z)),
            Vector((hi.x, hi.y, lo.z)), Vector((lo.x, hi.y, lo.z)),
            Vector((lo.x, lo.y, hi.z)), Vector((hi.x, lo.y, hi.z)),
            Vector((hi.x, hi.y, hi.z)), Vector((lo.x, hi.y, hi.z)),
        )
        self._ancora_base = Vector((
            (lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, lo.z))
        diagonal = (hi - lo).length
        self._tamanho_mira = max(0.04, min(diagonal * 0.08, 0.35))

    def _ocultar_staging(self, context):
        """Esconde a geometria real para deixar somente o preview GPU."""
        self._visibilidade = []
        for obj in self._novos:
            self._visibilidade.append(
                (obj, bool(obj.hide_viewport), bool(obj.hide_get())))
            obj.hide_set(True)
            obj.hide_viewport = True
        context.view_layer.update()

    def _restaurar_staging(self):
        for obj, global_oculto, local_oculto in getattr(
                self, "_visibilidade", []):
            try:
                obj.hide_viewport = global_oculto
                obj.hide_set(local_oculto)
            except (ReferenceError, RuntimeError):
                pass

    def _restaurar_selecao(self, context):
        try:
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in self._selecionados_antes:
                if obj.name in bpy.data.objects:
                    obj.select_set(True)
            if (self._ativo_antes is not None and
                    self._ativo_antes.name in bpy.data.objects):
                context.view_layer.objects.active = self._ativo_antes
        except (ReferenceError, RuntimeError):
            pass

    def _encerrar_visual(self, context):
        if self._handler_preview is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(
                    self._handler_preview, 'WINDOW')
            except Exception:
                pass
            self._handler_preview = None
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
        if context.area is not None:
            context.area.tag_redraw()
        if getattr(self, '_area_preview', None) is not None:
            self._area_preview.tag_redraw()

    def _desenhar_preview(self):
        """Desenha box e mira sobre a viewport sem criar geometria."""
        if not self._valido or not self._bbox_atual:
            return
        regiao = getattr(bpy.context, "region", None)
        if regiao is None or regiao.as_pointer() != self._regiao_ptr:
            return

        arestas = (
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        )
        linhas_box = []
        for a, b in arestas:
            linhas_box.extend((self._bbox_atual[a], self._bbox_atual[b]))

        normal = self._normal.normalized()
        referencia = (Vector((0.0, 0.0, 1.0))
                      if abs(normal.z) < 0.9 else Vector((1.0, 0.0, 0.0)))
        tangente = normal.cross(referencia).normalized()
        bitangente = normal.cross(tangente).normalized()
        tamanho = self._tamanho_mira
        alvo = self._alvo
        linhas_mira = (
            alvo - tangente * tamanho, alvo + tangente * tamanho,
            alvo - bitangente * tamanho, alvo + bitangente * tamanho,
            alvo - normal * tamanho * 0.35,
            alvo + normal * tamanho * 0.35,
        )

        try:
            gpu.state.blend_set('ALPHA')
            gpu.state.depth_test_set('NONE')
            gpu.state.line_width_set(1.5)
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            shader.bind()
            shader.uniform_float("color", (0.1, 1.0, 0.2, 0.9))
            batch_for_shader(
                shader, 'LINES', {"pos": linhas_box}).draw(shader)
            shader.uniform_float(
                "color", (1.0, 0.85, 0.1, 1.0)
                if self._em_superficie else (0.9, 0.9, 0.9, 1.0))
            batch_for_shader(
                shader, 'LINES', {"pos": linhas_mira}).draw(shader)
        except Exception as e:
            print("[Cabinet Creator] desenho do preview:", e)
        finally:
            try:
                gpu.state.line_width_set(1.0)
                gpu.state.depth_test_set('NONE')
                gpu.state.blend_set('NONE')
            except Exception:
                pass

    def _na_viewport(self, event):
        """O solte so' vale dentro da viewport, como no arraste nativo."""
        dx = event.mouse_x - self._regiao.x
        dy = event.mouse_y - self._regiao.y
        return 0 <= dx < self._regiao.width and 0 <= dy < self._regiao.height

    def _mover(self, context, event):
        """Usa raycast na cena e plano do cursor como contingencia."""
        if not self._na_viewport(event):
            self._valido = False
            self._area_preview.tag_redraw()
            return
        coord = (event.mouse_x - self._regiao.x, event.mouse_y - self._regiao.y)
        try:
            origem = view3d_utils.region_2d_to_origin_3d(
                self._regiao, self._rv3d, coord)
            direcao = view3d_utils.region_2d_to_vector_3d(
                self._regiao, self._rv3d, coord)
        except Exception:
            return
        alvo = None
        normal = Vector((0.0, 0.0, 1.0))
        self._em_superficie = False
        try:
            dep = context.evaluated_depsgraph_get()
            acerto, local, normal_hit, _face, obj_hit, _matriz = (
                context.scene.ray_cast(
                    dep, origem, direcao, distance=1000000.0))
            if acerto and obj_hit not in self._novos:
                alvo = local.copy()
                normal = normal_hit.copy()
                self._em_superficie = True
        except Exception as e:
            print("[Cabinet Creator] raycast do arraste:", e)
        if alvo is None:
            alvo = intersect_line_plane(
                origem, origem + direcao * 1000.0,
                Vector((0.0, 0.0, self._altura)),
                Vector((0.0, 0.0, 1.0)))
        if alvo is None:        # raio paralelo ao plano: nada a fazer
            self._valido = False
            self._area_preview.tag_redraw()
            return
        deslocamento = alvo - self._ancora_base
        for o in self._raizes:
            base = self._base.get(o)
            if base is not None:
                o.location = base + deslocamento
        self._alvo = alvo
        self._normal = normal
        self._bbox_atual = [p + deslocamento for p in self._bbox_base]
        self._valido = True
        self._area_preview.tag_redraw()

    def _apagar(self):
        for o in list(self._novos):
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass
        for colecao in list(getattr(self, "_colecoes_novas", [])):
            try:
                if colecao.name in bpy.data.collections:
                    bpy.data.collections.remove(colecao)
            except (ReferenceError, RuntimeError):
                pass

    def _cancelar(self, context):
        self._encerrar_visual(context)
        self._apagar()
        self._restaurar_selecao(context)
        if context.area is not None:
            context.area.tag_redraw()
        return {'CANCELLED'}

    def _duplo_clique_na_foto(self, context, event):
        """Segundo clique, rapido e no mesmo lugar do que abriu o
        posicionador, fora da viewport.

        Medido AQUI, pelo relogio: o Blender entrega esse segundo clique
        como PRESS, nao DOUBLE_CLICK (confirmado no log do usuario --
        PRESS 67 ms depois do RELEASE), porque o primeiro foi consumido
        pela gaveta. Esperando so' DOUBLE_CLICK, o PRESS caia no "clique
        fora da viewport" e cancelava a insercao.
        """
        if (event.type != 'LEFTMOUSE'
                or event.value not in {'PRESS', 'DOUBLE_CLICK'}
                or self._na_viewport(event)):
            return False
        if event.value == 'DOUBLE_CLICK':
            return True
        try:
            limite = context.preferences.inputs.mouse_double_click_time
        except Exception:
            limite = 350
        dx = event.mouse_x - self._mouse_inicio[0]
        dy = event.mouse_y - self._mouse_inicio[1]
        return ((time.monotonic() - self._instante_inicio) * 1000.0 <= limite
                and dx * dx + dy * dy <= RAIO_DUPLO_CLIQUE_PX ** 2)

    def _no_cursor(self, context):
        """Centro da base do preset no cursor 3D, e confirma."""
        deslocamento = context.scene.cursor.location - self._ancora_base
        for o in self._raizes:
            base = self._base.get(o)
            if base is not None:
                o.location = base + deslocamento
        self._valido = True
        return self._confirmar(context)

    def _confirmar(self, context):
        self._encerrar_visual(context)
        self._restaurar_staging()
        try:
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in self._novos:
                obj.select_set(True)
            if self._raizes:
                context.view_layer.objects.active = self._raizes[0]
            elif self._novos:
                context.view_layer.objects.active = self._novos[0]
            context.view_layer.update()
        except (ReferenceError, RuntimeError):
            pass
        self.report({'INFO'}, "%d objeto(s) inserido(s)" % len(self._novos))
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            if self._arrastando and not self._moveu:
                dx = event.mouse_x - self._mouse_inicio[0]
                dy = event.mouse_y - self._mouse_inicio[1]
                # O limiar evita transformar um clique com pequena
                # oscilacao involuntaria em arraste.
                self._moveu = (dx * dx + dy * dy) >= 36
            self._mover(context, event)
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE':   # DIAGNOSTICO TEMPORARIO
            _selecao._log_clique('posicionador %s viewport=%s arrastando=%s moveu=%s'
                        % (event.value, self._na_viewport(event),
                           self._arrastando, self._moveu))
        if self._duplo_clique_na_foto(context, event):
            # Duplo clique na FOTO (o primeiro clique abriu este
            # posicionador): entra direto no cursor 3D, sem mirar.
            return self._no_cursor(context)
        if event.type == 'LEFTMOUSE':
            confirma = 'RELEASE' if self._arrastando else 'PRESS'
            if event.value == confirma:
                if self._arrastando and not self._moveu:
                    # O clique sem arraste ativa o mesmo posicionador. Esse
                    # fallback e' indispensavel porque algumas versoes/temas
                    # do Blender retêm o drag do botao da interface.
                    self._arrastando = False
                    try:
                        context.workspace.status_text_set(
                            "Posicionamento ativo | Clique na viewport: "
                            "inserir | Botao direito: cancelar")
                    except Exception:
                        pass
                    return {'RUNNING_MODAL'}
                if not self._na_viewport(event):
                    return self._cancelar(context)
                if not self._valido:
                    self.report({'WARNING'}, "Posicione dentro da viewport")
                    return self._cancelar(context)
                return self._confirmar(context)
        if (event.type in {'RET', 'NUMPAD_ENTER'} and
                event.value == 'PRESS'):
            if not self._valido:
                self.report({'WARNING'}, "Posicione dentro da viewport")
                return {'RUNNING_MODAL'}
            return self._confirmar(context)
        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            return self._cancelar(context)
        if event.type == 'WINDOW_DEACTIVATE':
            return self._cancelar(context)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._cancelar(context)


class OBJECT_OT_navegar(Operator):
    """Seleciona um nivel da cascata"""
    bl_idname = "object.cabinet_navegar"
    bl_label = "Navegar"

    nivel: bpy.props.IntProperty(default=1)
    valor: bpy.props.StringProperty()

    def execute(self, context):
        s = context.scene
        if self.nivel == 1:
            s.chapa_n1 = "" if s.chapa_n1 == self.valor else self.valor
            s.chapa_n2 = ""
            s.chapa_n3 = ""
        elif self.nivel == 2:
            s.chapa_n2 = "" if s.chapa_n2 == self.valor else self.valor
            s.chapa_n3 = ""
        else:
            s.chapa_n3 = "" if s.chapa_n3 == self.valor else self.valor
        return {'FINISHED'}


# ======================================= MINIATURAS E WIREFRAME DE MEDIDAS
_previews = [None]

# O canvas e o scale do template sao fixos de proposito: alargar a sidebar
# nao deve ampliar a representacao. Cada proporcao e' normalizada para ocupar
# a area util maxima sem deformar ou ultrapassar as margens internas.
WIREFRAME_LARGURA_PX = 160
WIREFRAME_ALTURA_PX = 160
WIREFRAME_MARGEM_ESQUERDA_PX = 14.0
WIREFRAME_MARGEM_DIREITA_PX = 2.0
WIREFRAME_MARGEM_Y_PX = 20.0
WIREFRAME_LINHA_PX = 0.45
WIREFRAME_ESCALA_MIN_UI = 5.0
WIREFRAME_ESCALA_MAX_UI = 9.0
WIREFRAME_ESCALA_ESTREITA_MAX_UI = WIREFRAME_ESCALA_MAX_UI
WIREFRAME_LARGURA_EMPILHAR_PX = 310.0
MEDIDAS_LARGURA_COLUNA_UNICA_PX = 210.0
MEDIDAS_OCUPACAO_COLUNA_UNICA = 0.80
MEDIDAS_LARGURA_CONTROLES_UI = 4.5
WIREFRAME_CACHE_MAX = 48
MINIMO_ESPESSURA_WIREFRAME = 0.07
WIREFRAME_PREFIXO = "wireframe:v15:"
_wireframe_ordem = []

# Vertices: frente (0, 1, 5, 4), fundo (2, 3, 7, 6) e ligacoes.
_ARESTAS_WIREFRAME = (
    (0, 1), (1, 5), (5, 4), (4, 0),
    (2, 3), (3, 7), (7, 6), (6, 2),
    (0, 2), (1, 3), (5, 7), (4, 6),
)

# Fonte minima 5x7. Os indicadores fazem parte do buffer procedural e nao
# dependem de fontes instaladas no sistema.
_FONTE_WIREFRAME = {
    'A': ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    'E': ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    'L': ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    'P': ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
}


def _colecao_previews():
    if _previews[0] is None:
        _previews[0] = bpy.utils.previews.new()
    return _previews[0]


def _cor_wireframe(context):
    """Cor de texto do tema, para contrastar em temas claros e escuros."""
    try:
        cor = context.preferences.themes[0].user_interface.wcol_regular.text
        return tuple(max(0.0, min(1.0, float(v))) for v in cor[:3])
    except Exception:
        return (0.9, 0.9, 0.9)


def _caixas_das_folhas(largura, altura, profundidade, folhas):
    """Vertices das folhas na face frontal, nos eixos da caixa.

    Proporcoes de DESENHO, nao medidas: o preview e' um esquema. A
    folha recua 4% das bordas e avanca 8% da profundidade, que e' o que
    deixa a blocagem legivel em 160 px.
    """
    if folhas <= 0:
        return []
    recuo = min(largura, altura) * 0.04
    fundo = max(profundidade * 0.08, 1e-6)
    vao = largura - 2.0 * recuo
    if vao <= 0.0 or altura - 2.0 * recuo <= 0.0:
        return []
    vaz = vao * 0.02
    passo = (vao + vaz) / folhas
    z0, z1 = recuo, altura - recuo
    caixas = []
    for i in range(folhas):
        x0 = recuo + i * passo
        x1 = x0 + passo - vaz
        caixas.append([(x0, 0.0, z0), (x1, 0.0, z0),
                       (x0, fundo, z0), (x1, fundo, z0),
                       (x0, 0.0, z1), (x1, 0.0, z1),
                       (x0, fundo, z1), (x1, fundo, z1)])
    return caixas


def _pontos_wireframe(largura, altura, profundidade, extras=()):
    """Projeta a 45 graus e ajusta a proporcao a area util do canvas.

    `extras` sao vertices nos MESMOS eixos da caixa (por exemplo as
    folhas); voltam projetados logo apos os 8 cantos, para que nada
    saia com escala diferente da caixa.
    """
    medidas = (float(largura), float(altura), float(profundidade))
    if not all(math.isfinite(v) and v > 0.0 for v in medidas):
        return None
    L, A, P = medidas
    vertices = (
        (0.0, 0.0, 0.0), (L, 0.0, 0.0),
        (0.0, P, 0.0), (L, P, 0.0),
        (0.0, 0.0, A),   (L, 0.0, A),
        (0.0, P, A),     (L, P, A),
    ) + tuple(extras)
    diagonal = math.sqrt(0.5)  # cos(45) == sin(45)
    projetados = [(x - y * diagonal, z + y * diagonal)
                  for x, y, z in vertices]
    # Os limites saem dos 8 cantos da CAIXA: incluir as folhas mudaria
    # a escala e o modulo apareceria menor do que e'.
    caixa = projetados[:8]
    min_x = min(p[0] for p in caixa)
    max_x = max(p[0] for p in caixa)
    min_y = min(p[1] for p in caixa)
    max_y = max(p[1] for p in caixa)
    largura_proj = max_x - min_x
    altura_proj = max_y - min_y
    util_l = (WIREFRAME_LARGURA_PX - WIREFRAME_MARGEM_ESQUERDA_PX -
              WIREFRAME_MARGEM_DIREITA_PX)
    util_a = WIREFRAME_ALTURA_PX - 2.0 * WIREFRAME_MARGEM_Y_PX
    if (largura_proj <= 0.0 or altura_proj <= 0.0 or
            util_l <= 0.0 or util_a <= 0.0):
        return None

    escala = min(util_l / largura_proj, util_a / altura_proj)
    desenho_l = largura_proj * escala
    desenho_a = altura_proj * escala
    dx = WIREFRAME_MARGEM_ESQUERDA_PX - min_x * escala
    dy = (WIREFRAME_ALTURA_PX - desenho_a) / 2.0 - min_y * escala
    return [(x * escala + dx, y * escala + dy) for x, y in projetados]


def _desenhar_segmento(buffer, p0, p1, cor):
    """Rasteriza um segmento antialias somente dentro de sua caixa local."""
    largura = WIREFRAME_LARGURA_PX
    altura = WIREFRAME_ALTURA_PX
    x0, y0 = p0
    x1, y1 = p1
    vx, vy = x1 - x0, y1 - y0
    comp2 = vx * vx + vy * vy
    if comp2 <= 1e-12:
        return
    raio = WIREFRAME_LINHA_PX / 2.0
    alcance = raio + 1.0
    xa = max(0, int(math.floor(min(x0, x1) - alcance)))
    xb = min(largura - 1, int(math.ceil(max(x0, x1) + alcance)))
    ya = max(0, int(math.floor(min(y0, y1) - alcance)))
    yb = min(altura - 1, int(math.ceil(max(y0, y1) + alcance)))
    cr, cg, cb = cor

    for y in range(ya, yb + 1):
        py = y + 0.5
        for x in range(xa, xb + 1):
            px = x + 0.5
            t = ((px - x0) * vx + (py - y0) * vy) / comp2
            t = max(0.0, min(1.0, t))
            perto_x = x0 + t * vx
            perto_y = y0 + t * vy
            distancia = math.hypot(px - perto_x, py - perto_y)
            cobertura = max(0.0, min(1.0, raio + 0.75 - distancia))
            if cobertura <= 0.0:
                continue
            # ImagePreview usa a origem embaixo; os pontos tambem usam Y para
            # cima, portanto nao e' preciso inverter a linha neste buffer.
            i = (y * largura + x) * 4
            if cobertura > buffer[i + 3]:
                buffer[i] = cr
                buffer[i + 1] = cg
                buffer[i + 2] = cb
                buffer[i + 3] = cobertura


def _desenhar_indicador(buffer, letra, x, y, cor, escala=2):
    """Desenha uma letra 5x7 centralizada em (x, y)."""
    glifo = _FONTE_WIREFRAME.get(letra)
    if glifo is None:
        return
    largura = len(glifo[0]) * escala
    altura = len(glifo) * escala
    inicio_x = int(round(x - largura / 2.0))
    inicio_y = int(round(y - altura / 2.0))
    cr, cg, cb = cor
    for linha, bits in enumerate(reversed(glifo)):
        for coluna, bit in enumerate(bits):
            if bit != '1':
                continue
            for sy in range(escala):
                py = inicio_y + linha * escala + sy
                if py < 0 or py >= WIREFRAME_ALTURA_PX:
                    continue
                for sx in range(escala):
                    px = inicio_x + coluna * escala + sx
                    if px < 0 or px >= WIREFRAME_LARGURA_PX:
                        continue
                    i = (py * WIREFRAME_LARGURA_PX + px) * 4
                    buffer[i] = cr
                    buffer[i + 1] = cg
                    buffer[i + 2] = cb
                    buffer[i + 3] = 1.0


def _meio_wireframe(p0, p1):
    return ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)


def _desenhar_indicadores(buffer, pontos, cor, modo, trocado=False):
    """Identifica as direcoes sem adicionar cotas ou linhas auxiliares.

    'INDIVIDUAL' (chapa): L, A e E. Na chapa a aresta VERTICAL do
        desenho e' a espessura -- `_visual_wireframe` (`painel_legado`)
        passa a espessura na posicao da altura -- e a aresta que recua
        e' a altura da peca.
    'GRUPO' (modulo de chapas): L, A, P e mais o E na quina inferior
        direita. A espessura nao tem aresta propria no modulo, mas e'
        medida dele e precisa aparecer.
    'LIVRE' (objeto sem assinatura do addon): so' L, A e P. Sem chapas
        no meio, nao existe espessura para anunciar.
    """
    topo = _meio_wireframe(pontos[6], pontos[7])
    fundo = _meio_wireframe(pontos[0], pontos[2])
    vertical = _meio_wireframe(pontos[2], pontos[6])
    _desenhar_indicador(buffer, 'P' if trocado else 'L',
                        topo[0], topo[1] + 10.0, cor)

    if modo == 'INDIVIDUAL':
        _desenhar_indicador(
            buffer, 'E', max(5.0, vertical[0] - 9.0), vertical[1], cor)
        _desenhar_indicador(
            buffer, 'A', fundo[0] - 9.0, fundo[1] - 8.0, cor)
        return

    if modo == 'PORTA':
        _desenhar_indicador(
            buffer, 'A', max(5.0, vertical[0] - 9.0), vertical[1], cor)
        _desenhar_indicador(
            buffer, 'E', fundo[0] - 9.0, fundo[1] - 8.0, cor)
        return

    _desenhar_indicador(
        buffer, 'A', max(5.0, vertical[0] - 9.0), vertical[1], cor)
    _desenhar_indicador(
        buffer, 'L' if trocado else 'P', fundo[0] - 9.0, fundo[1] - 8.0, cor)
    if modo == 'GRUPO':
        # Canto inferior direito da projecao. A letra desce para a
        # margem de baixo em vez de sair pela direita: a margem lateral
        # e' de poucos pixels e `_desenhar_indicador` corta calado.
        quina = pontos[1]
        _desenhar_indicador(
            buffer, 'E', quina[0] - 8.0, quina[1] - 9.0, cor)


def _rasterizar_wireframe(largura, altura, profundidade, cor, modo='GRUPO',
                         folhas=0, trocado=False):
    """Pixels RGBA das 12 arestas do box, mais as folhas na frente."""
    caixas = _caixas_das_folhas(largura, altura, profundidade, folhas)
    extras = [v for caixa in caixas for v in caixa]
    pontos = _pontos_wireframe(largura, altura, profundidade, extras)
    if pontos is None:
        return None
    n = WIREFRAME_LARGURA_PX * WIREFRAME_ALTURA_PX * 4
    buffer = [0.0] * n
    for a, b in _ARESTAS_WIREFRAME:
        _desenhar_segmento(buffer, pontos[a], pontos[b], cor)
    for i in range(len(caixas)):
        base = 8 + i * 8
        for a, b in _ARESTAS_WIREFRAME:
            _desenhar_segmento(buffer, pontos[base + a], pontos[base + b], cor)
    _desenhar_indicadores(buffer, pontos, cor, modo, trocado)
    return _centralizar_wireframe(buffer)


def _centralizar_wireframe(buffer):
    """Centraliza o conteudo VISIVEL, incluindo as letras L/A/P/E."""
    largura, altura = WIREFRAME_LARGURA_PX, WIREFRAME_ALTURA_PX
    ocupados = [i // 4 for i in range(0, len(buffer), 4)
                if buffer[i + 3] > 0.0]
    if not ocupados:
        return buffer
    xs = [p % largura for p in ocupados]
    ys = [p // largura for p in ocupados]
    dx = int(round(((largura - 1) - (min(xs) + max(xs))) / 2.0))
    dy = int(round(((altura - 1) - (min(ys) + max(ys))) / 2.0))
    if dx == 0 and dy == 0:
        return buffer
    centralizado = [0.0] * len(buffer)
    for p in ocupados:
        x, y = p % largura, p // largura
        nx, ny = x + dx, y + dy
        if 0 <= nx < largura and 0 <= ny < altura:
            origem = p * 4
            destino = (ny * largura + nx) * 4
            centralizado[destino:destino + 4] = buffer[origem:origem + 4]
    return centralizado


# ==================================== BARRA DE TAMANHO (estilo volume)
# O bpy nao tem slider de trilho fino com knob redondo: o `slider=True`
# nativo pinta a barra inteira e escreve o valor por cima. Esta aqui e'
# rasterizada -- mesma tecnica do wireframe -- e fica clicavel porque e'
# montada em FATIAS: cada fatia e' um botao de operador que grava o seu
# proprio valor, e o clique cai na fatia certa sem precisar adivinhar
# coordenada nenhuma (o bpy nao informa onde o botao foi desenhado).
BARRA_PREFIXO = "barra:v2:"
BARRA_PX = 40               # lado da fatia rasterizada, em pixels
PX_FATIA_BARRA = 18.0       # largura que o icone ocupa ao ser desenhado
PX_BOTAO_BIBLIOTECA = 34.0  # o botao do Asset Browser, ao lado da barra
BARRA_TRILHO = 0.14         # espessura do trilho, fracao do lado
BARRA_KNOB = 0.62           # diametro do knob, fracao do lado
AMOSTRAS_BARRA = 4          # supersampling por pixel (4x4)
COR_BARRA_VAZIA = (0.322, 0.298, 0.290)
COR_BARRA_CHEIA = (1.0, 1.0, 1.0)


def _cobertura_disco(x, y, cx, cy, raio, amostras=AMOSTRAS_BARRA):
    """Quanto do pixel (x, y) o disco cobre, de 0 a 1.

    Supersampling na marra: o icone e' reduzido pelo Blender na hora de
    desenhar, e um circulo cru vira losango depois dessa reducao.
    """
    dentro = 0
    passo = 1.0 / amostras
    for sy in range(amostras):
        py = y - 0.5 + (sy + 0.5) * passo
        for sx in range(amostras):
            px = x - 0.5 + (sx + 0.5) * passo
            if math.hypot(px - cx, py - cy) <= raio:
                dentro += 1
    return dentro / float(amostras * amostras)


def _fatia_barra(indice, ativo, ultimo):
    """Pixels RGBA de UMA fatia: trecho do trilho + knob se for a ativa.

    O trilho vem cheio ate' a fatia ativa e vazio depois dela, que e' a
    leitura imediata de "quanto esta' ligado".
    """
    lado = BARRA_PX
    buffer = [0.0] * (lado * lado * 4)
    meio = (lado - 1) / 2.0
    meia_esp = max(1.0, lado * BARRA_TRILHO / 2.0)
    raio = lado * BARRA_KNOB / 2.0
    cor = COR_BARRA_CHEIA if indice <= ativo else COR_BARRA_VAZIA

    for y in range(lado):
        dy = abs(y - meio)
        for x in range(lado):
            alfa, c = 0.0, cor
            # trilho: faixa horizontal, bordas suavizadas
            if dy <= meia_esp - 0.5:
                alfa = 1.0
            elif dy <= meia_esp + 0.5:
                alfa = meia_esp + 0.5 - dy
            # pontas arredondadas so' nas fatias das extremidades
            if indice == 0 and x < meia_esp:
                alfa = min(alfa, _cobertura_disco(x, y, meia_esp, meio,
                                                  meia_esp))
            if indice == ultimo and x > lado - 1 - meia_esp:
                alfa = min(alfa, _cobertura_disco(
                    x, y, lado - 1 - meia_esp, meio, meia_esp))
            # knob por cima, sempre branco
            if indice == ativo:
                cob = _cobertura_disco(x, y, meio, meio, raio)
                if cob > 0.0:
                    if cob >= alfa:
                        c = COR_BARRA_CHEIA
                    alfa = max(alfa, cob)
            if alfa <= 0.0:
                continue
            i = (y * lado + x) * 4
            buffer[i] = c[0]
            buffer[i + 1] = c[1]
            buffer[i + 2] = c[2]
            buffer[i + 3] = min(1.0, alfa)
    return buffer


def _icone_fatia_barra(indice, ativo, ultimo):
    """icon_id de uma fatia, reaproveitado pelo cache de previews."""
    chave = BARRA_PREFIXO + "%d:%d:%d" % (indice, ativo, ultimo)
    colecao = _colecao_previews()
    if chave not in colecao:
        try:
            preview = colecao.new(chave)
            tamanho = (BARRA_PX, BARRA_PX)
            pixels = _fatia_barra(indice, ativo, ultimo)
            preview.icon_size = tamanho
            preview.icon_pixels_float = pixels
            preview.image_size = tamanho
            preview.image_pixels_float = pixels
        except Exception as e:
            print("[Cabinet Creator] barra:", e)
            return 0
    try:
        return colecao[chave].icon_id
    except Exception:
        return 0


def _metrica_barra(context, disponivel=None):
    """(fatias, largura logica da celula, compressao) da barra.

    Um lugar so' porque o DESENHO e o ARRASTE precisam concordar: se a
    celula medir diferente dos dois lados, o knob anda fora do dedo.
    """
    prop = bpy.types.Scene.bl_rna.properties["chapa_tam_bloco"]
    fatias = prop.hard_max - prop.hard_min + 1
    if disponivel is None:
        disponivel = max(1.0, PX_FATIA_BARRA * fatias)
    disponivel = max(1.0, disponivel)
    # scale_x encolhe a celula ate' o tamanho do icone; acima de 1.0 nao
    # adianta (o icone nao estica), entao a celula fica menor que o alvo
    compressao = min(1.0, PX_FATIA_BARRA * fatias / disponivel)
    celula = min(PX_FATIA_BARRA, disponivel / fatias)
    return fatias, celula, compressao


# ====================================== FOTO CLICAVEL (fatiada)
# `template_icon` amplia a foto mas NAO recebe evento, e o icone de um
# botao de operador nao passa de ~16 px por mais que se aumente
# scale_x/scale_y (medido). Para a foto inteira ficar clicavel ela e'
# cortada em ladrilhos, cada um o icone de um botao: o mosaico parece
# uma imagem so' e qualquer ponto dela aciona o posicionador.
FOTO_PREFIXO = "foto:v2:"
# Rasterizar em 24 e desenhar em 16 obrigava o Blender a reamostrar
# cada ladrilho (1,5x) e aparecia bandeamento nas faces lisas. Os
# dois tamanhos precisam ser IGUAIS: assim o desenho e' 1:1.
FOTO_TILE_PX = 16
# 16 px e' a largura REAL com que o Blender desenha o icone de um
# botao; 18 deixava 2 px de fresta e o mosaico virava xadrez.
PX_TILE_FOTO = 16.0
# Alvo da CELULA, de proposito menor que o icone: mirar nos 16 px
# exige acertar a largura do bloco na mosca, e ela e' estimada --
# qualquer desvio abre fresta e a foto fica picotada. Com folga, a
# celula fica sempre abaixo do icone em qualquer largura.
PX_ALVO_CELULA = 16.0
# ui_units_x sozinho nao encosta as colunas: sobra folga lateral
# em cada celula. O valor abaixo foi achado por captura de tela.
COMPRESSAO_TILE_FOTO = 0.7


# Folgas medidas por captura: o box da lista come' um tanto da
# largura do painel, e cada bloco tem a sua propria margem interna.
PADDING_GRADE = 34.0
PADDING_BLOCO = 12.0


def _metrica_blocos(context, tamanho):
    """(colunas, largura de cada bloco) da grade de presets.

    As colunas precisam ser EXPLICITAS. Com `columns=0` quem decide a
    largura do bloco e' o bpy, e a foto clicavel -- um mosaico de
    icones de 16 px -- so' fica sem fresta quando essa largura e'
    conhecida: `ui_units_x` e' ignorado dentro do grid_flow (medido) e
    `scale_x` encolhe o proprio icone, deformando a imagem.
    """
    util = max(1.0, _gaveta._largura_painel(context) - PADDING_GRADE)
    # O mosaico da foto so' fica sem listras quando a celula
    # (largura_do_bloco / ladrilhos) cai perto dos 16 px do icone.
    # Blocos largos demais fazem a conta desviar e aparecem bandas;
    # 20 px por grau de tamanho mantem o bloco na faixa que fecha.
    alvo = max(64.0, float(tamanho) * 20.0)
    colunas = max(1, min(6, int(util // alvo)))
    return colunas, util / colunas


def _foto_clicavel_ligada():
    """Preferencia: foto clicavel (mosaico) ou foto perfeita."""
    p = _opcoes._prefs()
    return bool(p and getattr(p, "foto_clicavel", False))


def _tiles_foto(pasta, png, lado):
    """icon_id de cada ladrilho da foto, em grade `lado` x `lado`.

    Devolve as linhas de CIMA para BAIXO, que e' a ordem em que a UI
    desenha -- os pixels do Blender vem de baixo para cima.
    """
    colecao = _colecao_previews()
    base = FOTO_PREFIXO + "%s|%s:%d:" % (pasta, png, lado)
    if (base + "0:0") not in colecao:
        n = lado * FOTO_TILE_PX
        pixels = _pixels_png(os.path.join(pasta, png), n)
        if not pixels:
            return None
        for j in range(lado):
            for i in range(lado):
                buf = []
                for y in range(FOTO_TILE_PX):
                    ini = ((j * FOTO_TILE_PX + y) * n
                           + i * FOTO_TILE_PX) * 4
                    buf.extend(pixels[ini:ini + FOTO_TILE_PX * 4])
                try:
                    pv = colecao.new(base + "%d:%d" % (i, j))
                except Exception as e:
                    print("[Cabinet Creator] foto:", e)
                    return None
                tam = (FOTO_TILE_PX, FOTO_TILE_PX)
                pv.icon_size = tam
                pv.icon_pixels_float = buf
                pv.image_size = tam
                pv.image_pixels_float = buf
    try:
        return [[colecao[base + "%d:%d" % (i, j)].icon_id
                 for i in range(lado)]
                for j in range(lado - 1, -1, -1)]
    except Exception as e:
        print("[Cabinet Creator] foto:", e)
        return None


class OBJECT_OT_definir_tamanho(Operator):
    """Tamanho das miniaturas da biblioteca.

    A barra responde a CLIQUE, nao a arraste, e isso nao tem conserto
    pela API: o bpy nao permite criar um tipo de widget novo. Um botao
    de painel e' tratado pelo handler de UI, que consome o PRESS antes
    de qualquer keymap -- nem `head=True` no keymap "User Interface"
    passa na frente. O que se desenha (imagem, icone) nao recebe
    evento; o que recebe evento (botao) nao se desenha do nosso jeito.
    Ja' foi tentado: keymap PRESS e CLICK_DRAG + modal relativo.
    """
    bl_idname = "object.cabinet_tamanho"
    bl_label = "Tamanho dos Blocos"

    valor: bpy.props.IntProperty(default=5)

    def execute(self, context):
        context.scene.chapa_tam_bloco = self.valor
        return {'FINISHED'}


def _chave_wireframe(modo, largura, altura, profundidade, cor, folhas=0):
    medidas = tuple(round(float(v), 1)
                    for v in (largura, altura, profundidade))
    rgb = tuple(round(float(v) * 255.0) for v in cor)
    return WIREFRAME_PREFIXO + "%s:%.1f:%.1f:%.1f:%d:%d:%d:%d" % (
        modo, medidas[0], medidas[1], medidas[2], rgb[0], rgb[1], rgb[2],
        int(folhas))


def _registrar_uso_wireframe(chave, colecao):
    if chave in _wireframe_ordem:
        _wireframe_ordem.remove(chave)
    _wireframe_ordem.append(chave)
    while len(_wireframe_ordem) > WIREFRAME_CACHE_MAX:
        antiga = _wireframe_ordem.pop(0)
        if antiga in colecao:
            try:
                del colecao[antiga]
            except Exception:
                pass


def _icone_wireframe(context, modo, largura, altura, profundidade, folhas=0):
    """Cria ou reutiliza o icon_id horizontal para estas medidas."""
    cor = _cor_wireframe(context)
    chave = _chave_wireframe(modo, largura, altura, profundidade, cor, folhas)
    colecao = _colecao_previews()
    if chave not in colecao:
        pixels = _rasterizar_wireframe(
            largura, altura, profundidade, cor, modo=modo, folhas=folhas)
        if pixels is None:
            return 0
        try:
            preview = colecao.new(chave)
            tamanho = (WIREFRAME_LARGURA_PX, WIREFRAME_ALTURA_PX)
            # Preenche ambos porque a versao do Blender decide qual nivel
            # usar conforme a escala pedida por template_icon.
            preview.icon_size = tamanho
            preview.icon_pixels_float = pixels
            preview.image_size = tamanho
            preview.image_pixels_float = pixels
        except Exception as e:
            if chave in colecao:
                try:
                    del colecao[chave]
                except Exception:
                    pass
            print("[Cabinet Creator] wireframe:", e)
            return 0
    _registrar_uso_wireframe(chave, colecao)
    return colecao[chave].icon_id


def _chave_preview(pasta, arquivo):
    return os.path.join(pasta, arquivo)


def icone_do_item(it):
    """icon_value da foto do preset, ou 0 se nao houver."""
    png = it.get("foto") or (os.path.splitext(it["arquivo"])[0] + ".png")
    caminho = os.path.join(it["pasta"], png)
    if not os.path.exists(caminho):
        return 0
    col = _colecao_previews()
    chave = _chave_preview(it["pasta"], png)
    if chave not in col:
        try:
            col.load(chave, caminho, 'IMAGE')
        except Exception:
            return 0
    return col[chave].icon_id


def _ocupacao_alpha_png(caminho):
    """Maior fracao ocupada pelo alfa, em X ou Y, ou zero se vazio."""
    imagem = None
    try:
        imagem = bpy.data.images.load(caminho, check_existing=False)
        largura, altura = imagem.size
        if largura <= 0 or altura <= 0:
            return 0.0
        # Blender 4.2 nao aceita `step` diretamente no bpy_prop_array.
        alpha = list(imagem.pixels)[3::4]
        min_x, min_y = largura, altura
        max_x = max_y = -1
        for indice, valor in enumerate(alpha):
            if valor <= 0.01:
                continue
            x = indice % largura
            y = indice // largura
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
        if max_x < min_x or max_y < min_y:
            return 0.0
        return max((max_x - min_x + 1) / largura,
                   (max_y - min_y + 1) / altura)
    except Exception as e:
        print("[Cabinet Creator] leitura do alfa:", e)
        return 0.0
    finally:
        if imagem is not None:
            try:
                bpy.data.images.remove(imagem)
            except (ReferenceError, RuntimeError):
                pass


# Fotos dos modelos de FABRICA (puxadores, aberturas, dobradicas): PNGs
# que viajam com o add-on, feitos por `gerar_fotos_padrao.py` na mesma
# vista das fotos da biblioteca. Ficam fora dela: sao protegidos.
PASTA_FOTOS_PADRAO = os.path.join(os.path.dirname(__file__), 'fotos')


# Modelos ainda sem peca propria mostram a foto de outro (pedido do
# usuario): tire daqui quando o modelo da Curva/Super Curva existir.
FOTOS_PENDENTES = {'dobradica_CURVA': 'dobradica_RETA',
                   'dobradica_SUPER_CURVA': 'dobradica_RETA'}


def foto_padrao(nome):
    """Retrato de fabrica (`puxador_ALCA`, `abertura_GIRO`...) no formato
    de item que o desenho da gaveta le."""
    nome = FOTOS_PENDENTES.get(nome, nome)
    return {'pasta': PASTA_FOTOS_PADRAO, 'arquivo': nome + '.png',
            'foto': nome + '.png'}


# Foto "a 45 graus" (pedido do usuario): de frente-direita, um pouco de
# cima -- a mesma vista para todo modelo de puxador, porta e dobradica.
VISTA_FOTO = Euler((math.radians(60.0), 0.0, math.radians(45.0)),
                   'XYZ').to_quaternion()


def fotografar_com_camera(destino_png, objetos, rotacao=VISTA_FOTO, lado=512):
    """Foto do preset SEM janela: camera ortografica na vista da foto,
    render Workbench solido com fundo transparente (a viewport de
    `capturar_viewport` nao existe em --background; o gerador dos armarios
    nativos roda assim). So' `objetos` aparecem; o resto volta como era."""
    cena = bpy.context.scene
    sombreamento = cena.display.shading
    antes = (cena.render.engine, cena.render.filepath,
             cena.render.image_settings.file_format,
             cena.render.image_settings.color_mode, cena.render.resolution_x,
             cena.render.resolution_y, cena.render.resolution_percentage,
             cena.render.film_transparent, cena.camera, sombreamento.light,
             sombreamento.color_type, tuple(sombreamento.single_color),
             sombreamento.show_object_outline)
    manter = {o.name for o in objetos}
    escondidos = [o for o in cena.objects
                  if o.name not in manter and not o.hide_render]
    dados = bpy.data.cameras.new('Foto Preset')
    camera = bpy.data.objects.new('Foto Preset', dados)
    cena.collection.objects.link(camera)
    try:
        for o in escondidos:
            o.hide_render = True
        bpy.context.view_layer.update()
        pontos = [o.matrix_world @ Vector(c) for o in objetos
                  if o.type == 'MESH' for c in o.bound_box]
        if not pontos:
            return False, 'nada para fotografar'
        centro = sum(pontos, Vector()) / len(pontos)
        rot = rotacao.to_matrix()
        # enquadra pela caixa VISTA da camera (eixos x/y dela)
        locais = [rot.transposed() @ (p - centro) for p in pontos]
        largura = max(p.x for p in locais) - min(p.x for p in locais)
        altura = max(p.y for p in locais) - min(p.y for p in locais)
        meio = Vector(((max(p.x for p in locais) + min(p.x for p in locais)) / 2,
                       (max(p.y for p in locais) + min(p.y for p in locais)) / 2,
                       0.0))
        profundidade = max(p.z for p in locais) + 1.0
        dados.type = 'ORTHO'
        dados.ortho_scale = max(largura, altura) * 1.12
        dados.clip_end = profundidade * 4 + 10.0
        camera.matrix_world = (Matrix.Translation(
            centro + rot @ (meio + Vector((0, 0, profundidade))))
            @ rotacao.to_matrix().to_4x4())
        cena.camera = camera
        cena.render.engine = 'BLENDER_WORKBENCH'
        cena.render.filepath = destino_png
        cena.render.image_settings.file_format = 'PNG'
        cena.render.image_settings.color_mode = 'RGBA'
        cena.render.resolution_x = cena.render.resolution_y = lado
        cena.render.resolution_percentage = 100
        cena.render.film_transparent = True
        sombreamento.light = 'STUDIO'
        sombreamento.color_type = 'SINGLE'
        sombreamento.single_color = (0.55, 0.55, 0.55)  # o cinza das fotos
        sombreamento.show_object_outline = True
        bpy.ops.render.render(write_still=True)
        return os.path.isfile(destino_png), destino_png
    except Exception as e:
        return False, str(e)
    finally:
        for o in escondidos:
            try:
                o.hide_render = False
            except ReferenceError:
                pass
        (cena.render.engine, cena.render.filepath,
         cena.render.image_settings.file_format,
         cena.render.image_settings.color_mode, cena.render.resolution_x,
         cena.render.resolution_y, cena.render.resolution_percentage,
         cena.render.film_transparent, cena.camera, sombreamento.light,
         sombreamento.color_type, sombreamento.single_color,
         sombreamento.show_object_outline) = antes
        bpy.data.objects.remove(camera, do_unlink=True)
        bpy.data.cameras.remove(dados)


# Armarios NATIVOS de fabrica (pedido do usuario): so' chapas do add-on,
# caixa + fundo de 5 mm em canal, chapa de 18 mm, COM PORTA (Reta,
# cobrindo a frente). Medidas EXTERNAS da caixa (mm), as de mercado:
# balcao 720 de caixa (bancada a ~900 com rodape), aereo 330 de fundo,
# torre e roupeiro de altura inteira. Porta de giro: 1 folha ate' 500 mm
# de largura, 2 acima; o aereo tem tambem a versao basculante.
LARGURA_MAX_UMA_FOLHA_MM = 500
ABERTURA_FOTO = 0.3            # fracao do slider de abertura na foto
# Puxador padrao dos nativos = PERFIL (pedido do usuario), na borda da
# pratica de cozinha planejada: balcao/gabinete em cima, aereo embaixo,
# torre/roupeiro na vertical do lado da abertura
# Modulo de bancada (pedido do usuario): topo ABERTO, duas travessas
TOPO_POR_TIPO = {'Balcao': 'TRAVESSAS', 'Gabinete': 'TRAVESSAS'}
PERFIL_POR_TIPO = {'Balcao': 'CIMA', 'Gabinete': 'CIMA', 'Aereo': 'BAIXO',
                   'Torre': 'LADO', 'Roupeiro': 'LADO'}


def _giro(L):
    return ('GIRO', 1 if L <= LARGURA_MAX_UMA_FOLHA_MM else 2)


ARMARIOS_NATIVOS = (
    [("Balcao", L, 720, 550, ("Armarios", "Cozinha", "Inferiores"), _giro(L))
     for L in (300, 400, 450, 500, 600, 800, 900, 1000, 1200)]
    + [("Aereo", L, 700, 330, ("Armarios", "Cozinha", "Superiores"), _giro(L))
       for L in (300, 400, 450, 500, 600, 800, 900, 1000, 1200)]
    + [("Aereo", L, 700, 330, ("Armarios", "Cozinha", "Superiores"),
        ('BASCULANTE', 1)) for L in (400, 450, 500, 600, 800, 900, 1000, 1200)]
    + [("Torre", L, 2200, 550, ("Armarios", "Cozinha", "Torres"), _giro(L))
       for L in (600, 700)]
    + [("Roupeiro", L, 2400, 550, ("Armarios", "Quarto", "Closets"), _giro(L))
       for L in (450, 500, 600, 800, 900, 1000)]
    + [("Gabinete", L, 600, 450, ("Armarios", "Banheiro", "Gabinetes"), _giro(L))
       for L in (400, 500, 600, 800, 1000)]
)


def nome_armario_nativo(tipo, L, A, P, portas=None):
    """"Balcao 2 Portas 800x720x550", "Aereo Basculante 600x700x330"."""
    if portas is None:
        variante = ""
    elif portas[0] == 'BASCULANTE':
        variante = " Basculante"
    else:
        variante = " %d Porta%s" % (portas[1], "s" if portas[1] > 1 else "")
    return "%s%s %dx%dx%d" % (tipo, variante, L, A, P)


def gerar_armario_nativo(context, tipo, L, A, P, niveis, portas=None, E=18.0):
    """Monta o armario (com a porta de `portas`: ('GIRO', folhas) ou
    ('BASCULANTE', 1)), grava o .blend na biblioteca (`pasta_biblioteca`),
    tira a foto sem janela, poe a preview no asset e registra no indice.
    A cena volta a ficar sem ele. Devolve o caminho do .blend."""
    nome = nome_armario_nativo(tipo, L, A, P, portas)
    conj = _modulos.criar_armario(context, nome, L, A, P, E,
                                  topo=TOPO_POR_TIPO.get(tipo, 'TAMPO'))
    if portas is not None:
        grupo = _portas.porta_no_modulo(conj, folhas=portas[1], abertura=portas[0])
        _puxadores.perfis_na_porta(context, grupo, PERFIL_POR_TIPO.get(tipo, 'CIMA'))
    return gravar_modulo_na_biblioteca(context, conj, nome, niveis)


def gravar_modulo_na_biblioteca(context, conj, nome, niveis):
    """Grava o modulo da cena como preset (`pasta_biblioteca`): .blend,
    foto sem janela (porta entreaberta), preview do asset e indice. O
    modulo SAI da cena. Devolve o caminho do .blend."""
    pecas = [conj] + list(conj.children_recursive)
    colecao = _modulos._colecao_do_modulo(conj)
    if colecao is not None:
        # a Collection do ASSET leva o nome: a da montagem sai do caminho
        # (senao o asset gravado viraria "<nome>.001")
        colecao.name = nome + " (montagem)"
    removido = [False]

    def remover_da_cena():
        if removido[0]:
            return
        removido[0] = True
        for o in pecas:
            malha = o.data if o.type == 'MESH' else None
            bpy.data.objects.remove(o, do_unlink=True)
            if malha is not None and malha.users == 0:
                bpy.data.meshes.remove(malha)
        if colecao is not None and colecao.name in bpy.data.collections:
            bpy.data.collections.remove(colecao)
    try:
        arq = salvar_na_biblioteca(pecas, nome, True, niveis=niveis)
        png = os.path.join(pasta_biblioteca(),
                           os.path.splitext(os.path.basename(arq))[0] + ".png")
        # na FOTO a porta fica entreaberta: fechadas, giro de 1 folha e
        # basculante saiam iguais na grade (o .blend ja' foi gravado fechado)
        for grupo in _portas._portas_do_conjunto(conj):
            for folha in _portas._folhas_portas(grupo):
                _ferragens._definir_abertura(context, folha, ABERTURA_FOTO)
        context.view_layer.update()
        ok, msg = fotografar_com_camera(png, pecas)
        if not ok:
            raise RuntimeError("foto do preset: " + msg)
        # `aplicar_preview_png` recarrega e REGRAVA o .blend: com as pecas
        # ainda na cena, tudo voltava como ".001" (bug aberto da suite da
        # biblioteca); fora dela, os nomes do arquivo ficam limpos
        remover_da_cena()
        ok, msg = aplicar_preview_png(arq, png)
        if not ok:
            raise RuntimeError("preview do preset: " + msg)
        registrar_no_indice(pasta_biblioteca(), nome, arq, *niveis, "modulo")
        return arq
    finally:
        remover_da_cena()


def capturar_viewport(destino_png, camera=None, isolar=None, rotacao=None):
    """Foto do modelo a partir da viewport.

    NAO renderiza: usa render OpenGL, ou seja, as cores da propria
    viewport. Overlays desligados removem grade, eixos, gizmos e icones.
    O PNG sai em RGBA transparente e, sem camera explicita, o alvo e'
    enquadrado automaticamente para ocupar a miniatura.

    camera  -- se informada, usa a vista dela. Se nao, e a viewport ja'
               estiver em vista de camera, mantem essa vista; caso
               contrario usa o enquadramento atual da viewport.
    isolar  -- lista de objetos que devem aparecer. Todo o resto da cena
               e' ocultado durante a captura e restaurado depois, para
               que um modulo dentro de uma composicao maior saia sozinho
               na foto.
    rotacao -- vista fixa (quaternion, ex.: `VISTA_FOTO`) no lugar da
               orientacao atual da viewport.
    """
    cena = bpy.context.scene
    ant = (cena.render.filepath, cena.render.image_settings.file_format,
           cena.render.image_settings.color_mode,
           cena.render.resolution_x, cena.render.resolution_y,
           cena.render.resolution_percentage, cena.render.film_transparent)
    # a gaveta tambem e' VIEW_3D: a foto sai da viewport de verdade
    area = next((a for a in bpy.context.screen.areas if a.type == 'VIEW_3D'
                 and not _gaveta._eh_area_gaveta_bruto(a)), None)
    if area is None:
        return False, "Nenhuma viewport 3D visivel"

    espaco = area.spaces.active
    r3d = espaco.region_3d
    ov_ant = espaco.overlay.show_overlays
    vista_ant = (r3d.view_distance, r3d.view_location.copy(),
                 r3d.view_rotation.copy(), r3d.view_perspective,
                 r3d.view_camera_zoom, tuple(r3d.view_camera_offset))
    cam_ant = cena.camera
    selecionados_ant = list(bpy.context.selected_objects)
    ativo_ant = bpy.context.view_layer.objects.active
    escondidos = []
    enquadrar = []

    try:
        if isolar is not None:
            manter = set()
            for o in isolar:
                manter.add(o.name)
                for f in bpy.data.objects:
                    if f.parent is o:
                        manter.add(f.name)
            for o in bpy.context.view_layer.objects:
                if o.name not in manter and not o.hide_get():
                    o.hide_set(True)
                    escondidos.append(o)
                elif o.name in manter:
                    enquadrar.append(o)

        cena.render.image_settings.file_format = 'PNG'
        cena.render.image_settings.color_mode = 'RGBA'
        cena.render.resolution_x = 512
        cena.render.resolution_y = 512
        cena.render.resolution_percentage = 100
        cena.render.film_transparent = True
        cena.render.filepath = destino_png
        espaco.overlay.show_overlays = False

        if camera is not None:
            cena.camera = camera
            r3d.view_perspective = 'CAMERA'
        elif rotacao is not None:
            r3d.view_rotation = rotacao
        # Sem camera preserva a orientacao escolhida pelo usuario, mas
        # ajusta centro e distancia para o alvo ocupar a miniatura.

        regiao = next((r for r in area.regions if r.type == 'WINDOW'), None)
        with bpy.context.temp_override(area=area, region=regiao):
            if camera is None and enquadrar:
                # A captura quadrada nao tem a mesma proporcao da viewport
                # larga. ORTHO preserva o angulo, mantem o centro e evita
                # o deslocamento lateral que a perspectiva produziria.
                r3d.view_perspective = 'ORTHO'
                for o in bpy.context.selected_objects:
                    o.select_set(False)
                for o in enquadrar:
                    try:
                        o.select_set(True)
                    except (ReferenceError, RuntimeError):
                        pass
                bpy.context.view_layer.objects.active = enquadrar[0]
                bpy.ops.view3d.view_selected(use_all_regions=False)
                # Uma pequena folga evita cortar antialiasing e objetos
                # muito largos/altos junto ao limite do PNG.
                r3d.view_distance *= 1.12
            bpy.ops.render.opengl(write_still=True, view_context=True)
            if camera is None and enquadrar:
                # `view_selected` enquadra usando a proporcao da viewport,
                # mas o PNG e' quadrado. Mede o alfa real e faz uma segunda
                # passagem para ocupar o mesmo espaco em qualquer sidebar.
                ocupacao = _ocupacao_alpha_png(destino_png)
                if ocupacao > 0.01:
                    fator = max(0.25, min(2.0, ocupacao / 0.82))
                    if abs(fator - 1.0) > 0.03:
                        r3d.view_distance *= fator
                        bpy.ops.render.opengl(write_still=True,
                                              view_context=True)
        return True, destino_png
    except Exception as e:
        return False, str(e)
    finally:
        for o in escondidos:
            try:
                o.hide_set(False)
            except Exception:
                pass
        espaco.overlay.show_overlays = ov_ant
        (r3d.view_distance, r3d.view_location, r3d.view_rotation,
         r3d.view_perspective, r3d.view_camera_zoom,
         r3d.view_camera_offset) = vista_ant
        cena.camera = cam_ant
        for o in bpy.context.selected_objects:
            o.select_set(False)
        for o in selecionados_ant:
            try:
                o.select_set(True)
            except (ReferenceError, RuntimeError):
                pass
        if ativo_ant is not None and ativo_ant.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = ativo_ant
        (cena.render.filepath, cena.render.image_settings.file_format,
         cena.render.image_settings.color_mode,
         cena.render.resolution_x, cena.render.resolution_y,
         cena.render.resolution_percentage, cena.render.film_transparent) = ant


def viewport_em_camera():
    area = next((a for a in bpy.context.screen.areas if a.type == 'VIEW_3D'), None)
    if area is None:
        return False
    return area.spaces.active.region_3d.view_perspective == 'CAMERA'


def _achar_item(pasta, arquivo):
    for it in indice_completo():
        if it["pasta"] == pasta and it["arquivo"] == arquivo:
            return it
    return None


# ========================================== BLOQUEIO E RENOMEAR DOS BLOCOS
def _atualizar_item(pasta, arquivo, mudancas):
    itens = _ler_indice(pasta)
    for i in itens:
        if i.get("arquivo") == arquivo:
            i.update(mudancas)
    _gravar_indice(pasta, itens)


def item_bloqueado(it):
    """Com uma biblioteca so', o cadeado e' por item: nao ha' mais uma
    origem "de fabrica" que force o bloqueio."""
    return bool(it.get("bloqueado", False))


class OBJECT_OT_alternar_bloqueio(Operator):
    """Bloqueia ou desbloqueia a edicao deste bloco"""
    bl_idname = "object.cabinet_bloqueio"
    bl_label = "Bloquear/Desbloquear"

    pasta: bpy.props.StringProperty()
    arquivo: bpy.props.StringProperty()

    def execute(self, context):
        it = _achar_item(self.pasta, self.arquivo)
        if it is None:
            return {'CANCELLED'}
        _atualizar_item(self.pasta, self.arquivo,
                        {"bloqueado": not bool(it.get("bloqueado", False))})
        return {'FINISHED'}


class OBJECT_OT_editar_modelo(Operator):
    """Editar nome, categoria e foto do modelo"""
    bl_idname = "object.cabinet_editar_modelo"
    bl_label = "Editar Modelo"
    bl_options = {'REGISTER'}

    pasta: bpy.props.StringProperty()
    arquivo: bpy.props.StringProperty()
    nome: bpy.props.StringProperty(name="Nome")
    n1: bpy.props.EnumProperty(name="Categoria",
                               items=lambda s, c: [(k, k, "") for k in ARVORE.keys()])
    n2: bpy.props.StringProperty(name="Subcategoria")
    n3: bpy.props.StringProperty(name="Tipo")
    tirar_foto: bpy.props.BoolProperty(
        name="Capturar foto da viewport", default=False,
        description="Salva o enquadramento atual da viewport 3D como foto do modelo")

    def invoke(self, context, event):
        it = _achar_item(self.pasta, self.arquivo)
        if it:
            self.nome = it.get("nome", "")
            a, b, c = _niveis_de(it)
            try:
                self.n1 = a or "Armarios"
            except Exception:
                pass
            self.n2, self.n3 = b, c
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        lay = self.layout
        lay.prop(self, "nome")
        lay.prop(self, "n1")
        lay.prop(self, "n2")
        lay.prop(self, "n3")
        lay.separator()
        it = _achar_item(self.pasta, self.arquivo)
        icone = icone_do_item(it) if it else 0
        cx = lay.box()
        cx.label(text="Foto do modelo")
        if icone:
            cx.template_icon(icon_value=icone, scale=6.0)
        else:
            cx.label(text="sem foto", icon='IMAGE_DATA')
        cx.prop(self, "tirar_foto")

    def execute(self, context):
        it = _achar_item(self.pasta, self.arquivo)
        if it is None:
            self.report({'ERROR'}, "Preset nao encontrado no indice")
            return {'CANCELLED'}
        if item_bloqueado(it):
            self.report({'WARNING'}, "Bloco bloqueado: destrave o cadeado")
            return {'CANCELLED'}

        png = os.path.splitext(self.arquivo)[0] + ".png"
        if self.tirar_foto:
            cam = next((o for o in context.selected_objects if o.type == 'CAMERA'), None)
            alvo = [o for o in context.selected_objects if o.type != 'CAMERA']
            ok, msg = capturar_viewport(os.path.join(self.pasta, png), cam,
                                        isolar=alvo or None)
            if not ok:
                self.report({'WARNING'}, "Foto falhou: " + msg)
            else:
                chave = _chave_preview(self.pasta, png)
                col = _colecao_previews()
                if chave in col:
                    del col[chave]

        itens = _ler_indice(self.pasta)
        for i in itens:
            if i.get("arquivo") == self.arquivo:
                i["nome"] = self.nome
                i["n1"] = self.n1
                i["n2"] = self.n2
                i["n3"] = self.n3
                i.pop("categoria", None)
                i.pop("subcategoria", None)
                i["foto"] = png
        _gravar_indice(self.pasta, itens)
        self.report({'INFO'}, "Modelo atualizado")
        return {'FINISHED'}


class OBJECT_OT_salvar_biblioteca(Operator):
    """Salva a selecao na biblioteca de assets do Blender"""
    bl_idname = "object.cabinet_salvar_biblioteca"
    bl_label = "Salvar na Biblioteca"
    bl_options = {'REGISTER'}

    nome: bpy.props.StringProperty(name="Nome do preset", default="Preset")
    n1: bpy.props.EnumProperty(name="Categoria",
                               items=lambda s, c: [(k, k, "") for k in ARVORE.keys()])
    n2: bpy.props.StringProperty(name="Subcategoria", default="")
    n3: bpy.props.StringProperty(name="Tipo", default="")
    como_modulo: bpy.props.BoolProperty(
        name="Como modulo (varias pecas)", default=True,
        description="Ligado: salva como Collection (arrasta o conjunto inteiro). "
                    "Desligado: salva cada chapa como objeto separado")

    def invoke(self, context, event):
        sel = [o for o in context.selected_objects]
        if len(sel) == 1 and sel[0].type == 'MESH':
            self.como_modulo = False
            self.nome = sel[0].name
        elif sel:
            self.nome = "Modulo"
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        sel = [o for o in context.selected_objects]
        if not sel:
            self.report({'WARNING'}, "Nada selecionado")
            return {'CANCELLED'}
        # inclui filhos dos Empties de conjunto selecionados
        completos = list(sel)
        for o in sel:
            if _chapas.MARCA_CONJUNTO in o:
                completos += [f for f in bpy.data.objects if f.parent == o]
        completos = list(dict.fromkeys(completos))
        # os niveis sao resolvidos ANTES de gravar: e' deles que sai o
        # catalogo em que o asset vai ser arquivado
        n2 = self.n2 or (_filhos_n2(self.n1) or [""])[0]
        n3 = self.n3 or (_filhos_n3(self.n1, n2) or [""])[0]
        try:
            arq = salvar_na_biblioteca(completos, self.nome, self.como_modulo,
                                       niveis=(self.n1, n2, n3))
            png = os.path.splitext(os.path.basename(arq))[0] + ".png"
            # Todo preset precisa nascer com representacao visual. Nao e'
            # uma preferencia do usuario nem pode ser desativada no dialogo.
            cam = next((o for o in sel if o.type == 'CAMERA'), None)
            alvo = [o for o in completos if o.type != 'CAMERA']
            okf, msg = capturar_viewport(
                os.path.join(pasta_biblioteca(), png), cam,
                isolar=alvo or None)
            if not okf:
                self.report({'ERROR'}, "Foto obrigatoria falhou: " + msg)
                return {'CANCELLED'}
            # a mesma foto vira a preview do asset dentro do .blend
            okp, msgp = aplicar_preview_png(
                arq, os.path.join(pasta_biblioteca(), png))
            if not okp:
                print("[Cabinet Creator] preview do asset:", msgp)
            registrar_no_indice(pasta_biblioteca(), self.nome, arq,
                                self.n1, n2, n3,
                                "modulo" if self.como_modulo else "objeto")
        except Exception as e:
            self.report({'ERROR'}, "Falha ao salvar: %s" % e)
            return {'CANCELLED'}
        self.report({'INFO'}, "Salvo em %s" % arq)
        return {'FINISHED'}


# Fracao da altura da viewport que sobra para a viewport ao abrir a
# biblioteca embaixo dela.
FRACAO_ASSET_BROWSER = 0.35


def _apontar_asset_browser():
    """Aponta o Asset Browser recem-aberto para a biblioteca do addon.

    Roda adiado porque `params` do SpaceFileBrowser so' passa a existir
    depois que a area e' desenhada pela primeira vez. As areas sao
    relidas do window_manager a cada chamada -- guardar a referencia
    arriscaria usar um ponteiro morto se a area fosse fechada antes.
    """
    try:
        for janela in bpy.context.window_manager.windows:
            for area in janela.screen.areas:
                if area.type != 'FILE_BROWSER':
                    continue
                params = getattr(area.spaces.active, "params", None)
                if params is None:
                    continue
                # so' mexe em quem ainda esta' no padrao ("All
                # Libraries"): um browser que o usuario ja' apontou para
                # outra biblioteca nao pode ser sequestrado
                atual = getattr(params, "asset_library_reference", "")
                if atual in ("", "ALL"):
                    try:
                        params.asset_library_reference = NOME_BIBLIOTECA
                    except Exception as e:
                        print("[Cabinet Creator] biblioteca:", e)
                area.tag_redraw()
    except Exception as e:
        print("[Cabinet Creator] asset browser:", e)
    return None


def _area_asset_browser(tela):
    for area in tela.areas:
        if area.type == 'FILE_BROWSER' and area.ui_type == 'ASSETS':
            return area
    return None


class OBJECT_OT_abrir_asset_browser(Operator):
    """Abre a biblioteca do Blender embaixo da viewport; clique de novo
    para fechar"""
    bl_idname = "object.cabinet_asset_browser"
    bl_label = "Abrir no Asset Browser"

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        registrar_bibliotecas()
        tela = context.window.screen

        # ja' aberto: o mesmo botao fecha
        aberto = _area_asset_browser(tela)
        if aberto is not None:
            alvo = next((r for r in aberto.regions if r.type == 'WINDOW'),
                        None)
            try:
                with context.temp_override(area=aberto, region=alvo):
                    bpy.ops.screen.area_close()
                return {'FINISHED'}
            except Exception as e:
                print("[Cabinet Creator] fechar browser:", e)
                self.report({'WARNING'}, "Feche a area a mao")
                return {'CANCELLED'}

        # Uma JANELA nova nao serve: `Window.width/height` sao somente
        # leitura e nenhum operador aceita tamanho, entao ela nasceria
        # quase do tamanho da tela e esconderia o trabalho. Dividir a
        # viewport da uma area pequena, com o modelo sempre a' vista.
        area = context.area
        janela = next((r for r in area.regions if r.type == 'WINDOW'), None)
        antes = {a.as_pointer() for a in tela.areas}
        try:
            with context.temp_override(area=area, region=janela):
                bpy.ops.screen.area_split(direction='HORIZONTAL',
                                          factor=FRACAO_ASSET_BROWSER)
        except Exception as e:
            print("[Cabinet Creator] dividir area:", e)
            self.report({'WARNING'}, "Nao consegui abrir a biblioteca")
            return {'CANCELLED'}

        nova = next((a for a in tela.areas if a.as_pointer() not in antes),
                    None)
        if nova is None:
            self.report({'WARNING'}, "Nao consegui abrir a biblioteca")
            return {'CANCELLED'}
        try:
            nova.type = 'FILE_BROWSER'
            nova.ui_type = 'ASSETS'
        except Exception as e:
            print("[Cabinet Creator] asset browser:", e)
            self.report({'WARNING'}, "Troque o editor para Asset Browser")
            return {'CANCELLED'}
        # params so' nasce depois do primeiro desenho da area
        bpy.app.timers.register(_apontar_asset_browser, first_interval=0.2)
        return {'FINISHED'}


class OBJECT_OT_abrir_pasta_biblioteca(Operator):
    """Mostra o caminho da biblioteca no Explorer"""
    bl_idname = "object.cabinet_abrir_biblioteca"
    bl_label = "Abrir Pasta da Biblioteca"

    def execute(self, context):
        destino = pasta_biblioteca()
        bpy.ops.wm.path_open(filepath=destino)
        self.report({'INFO'}, destino)
        return {'FINISHED'}


# ========================================== PRATELEIRA DE ASSETS
# O arrastar-e-soltar de verdade -- o MESMO do Asset Browser do Blender
# -- so' existe em editores nativos. `UILayout` nao expoe nada que
# inicie um arraste, e o `template_asset_view`, que os paineis usavam
# para isso, foi removido (nao existe mais no 5.x, junto com
# `bpy.types.AssetHandle`). Ou seja: a grade da sidebar nao tem como
# iniciar um arraste, por construcao da API.
#
# A AssetShelf, porem, E' registravel em Python e fica dentro da propria
# viewport. O arraste nativo vem LIGADO de fabrica: os pinceis do
# Blender e' que pedem 'NO_ASSET_DRAG' para desliga-lo. Nao pedindo
# nada, o item e' arrastavel e o solte cai no dropbox nativo da
# viewport, identico ao do Asset Browser.


class VIEW3D_AST_cabinet_creator(bpy.types.AssetShelf):
    """Prateleira com os presets: arraste o modulo direto para a cena."""
    bl_idname = "VIEW3D_AST_cabinet_creator"
    bl_space_type = 'VIEW_3D'
    bl_options = {'STORE_ENABLED_CATALOGS_IN_PREFERENCES'}
    bl_default_preview_size = 96
    # allowlist: so' o que faz sentido soltar na cena
    filter_object = True
    filter_group = True

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and not _gaveta._eh_area_gaveta(context)

    @classmethod
    def asset_poll(cls, asset):
        return asset.id_type in {'OBJECT', 'COLLECTION'}


class OBJECT_OT_prateleira(Operator):
    """Mostra/esconde a prateleira de assets na viewport -- e' de la'
    que se ARRASTA o modulo para a cena"""
    bl_idname = "object.cabinet_prateleira"
    bl_label = "Prateleira de Assets"

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        registrar_bibliotecas()
        # Gravar show_region_asset_shelf direto falha com "read-only"
        # dependendo do contexto (o botao vive na sidebar, nao na
        # viewport). O operador de regiao do proprio Blender resolve
        # sempre -- e' o mesmo que o menu Ver usa.
        janela = next((r for r in context.area.regions
                       if r.type == 'WINDOW'), None)
        try:
            with context.temp_override(area=context.area, region=janela):
                bpy.ops.screen.region_toggle(region_type='ASSET_SHELF')
        except Exception as e:
            print("[Cabinet Creator] prateleira:", e)
            self.report({'WARNING'}, "Use Ver > Prateleira de Assets")
            return {'CANCELLED'}
        if getattr(context.space_data, "show_region_asset_shelf", False):
            self.report({'INFO'},
                        "Escolha a biblioteca 'Cabinet Creator' e arraste")
        return {'FINISHED'}


class OBJECT_OT_registrar_bibliotecas(Operator):
    """Registra as pastas do addon como bibliotecas de assets"""
    bl_idname = "object.cabinet_registrar_bibliotecas"
    bl_label = "Registrar Bibliotecas no Blender"

    def execute(self, context):
        novas = registrar_bibliotecas(silencioso=False)
        if novas:
            self.report({'INFO'}, "Registrada(s): " + ", ".join(novas))
        else:
            self.report({'INFO'}, "Bibliotecas ja estavam registradas")
        return {'FINISHED'}
