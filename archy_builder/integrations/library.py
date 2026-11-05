"""Preset library: folders, catalogs, index, preset insertion/dragging,
thumbnails, clickable photos, size bar, locking, saving, Asset Browser,
and shelf. Also owns the dimension wireframe used by the sidebar
and N-panel."""

import bpy, math, os, uuid, json, gpu, time, blf
_frentes = None
import bpy.utils.previews
from gpu_extras.batch import batch_for_shader
from mathutils import Euler, Matrix, Vector
from mathutils.geometry import intersect_line_plane
from bpy_extras import view3d_utils
from bpy.types import Operator

# Used only at RUNTIME (circular imports): __init__ wires these
# aliases after loading all modules (`_ligar_modulos`).
_chapas = _modulos = _opcoes = _selecao = _gaveta = None
_portas = _puxadores = _ferragens = _promob = None
_biblioteca_faixa = None
_formas = None
_paredes_edicao = None
_paredes = None
_esquadrias = None

# ================================================== LIBRARY / ASSETS
# Save panels and cabinets in Blender's asset library for
# reuse through the Asset Browser by dragging into the scene.
#
# Each preset gets its own .blend in the library folder.
# One file per preset avoids reopening and merging a shared .blend
# on every save.
# Auxiliary folder name for new library data.
SUBPASTA_BIB = "Archy Builder"
# SINGLE Asset Browser catalog root. Changing a catalog PATH is safe
# as long as its UUID stays unchanged: the .blend stores that UUID,
# which Blender uses to find the asset. Therefore old roots
# are RENAMED with the same UUID, never recreated.
CAT_RAIZ = "Archy Builder"
RAIZES_ANTIGAS = ("Cabinet Creator", "Chapa G3")

# One asset library. These names were registered by earlier add-on
# versions and must now be cleaned up.
NOME_BIBLIOTECA = "Archy Builder"
BIBLIOTECAS_ANTIGAS = (
    "Chapa G3 (fabrica)", "Chapa G3 (equipe)",
    "Cabinet Creator", "Cabinet Creator (fabrica)", "Cabinet Creator (equipe)",
)
CAT_CHAPAS = CAT_RAIZ + "/Panels"
CAT_MODULOS = CAT_RAIZ + "/Modules"


def pasta_biblioteca():
    """The ONLY library: the company library inside the add-on.

    The factory/team split no longer exists; it caused duplicate entries
    in the Asset Browser selector. To use a network folder, set
    `pasta_biblioteca` in Preferences.

    WARNING: writing inside the add-on is safe only because the folder
    is the company repository (junction created by vincular_blender.py).
    For ZIP installations, an update overwrites the folder; configure
    the network folder in Preferences in that case."""
    p = _opcoes._prefs()
    if p and getattr(p, "pasta_biblioteca", ""):
        destino = bpy.path.abspath(p.pasta_biblioteca)
    else:
        destino = _opcoes._pasta_addon()
    try:
        os.makedirs(destino, exist_ok=True)
    except Exception as e:
        print("[Archy Builder] library:", e)
    return destino


def registrar_bibliotecas(silencioso=True):
    """Register the library folder as a Blender asset library
    without duplicating an existing registration."""
    registradas = []
    libs = bpy.context.preferences.filepaths.asset_libraries
    caminho = pasta_biblioteca()
    alvo = os.path.normcase(os.path.normpath(caminho))

    # Cleanup comes BEFORE registration. An old entry could point to THIS
    # same folder: removing it afterward skipped registration because it
    # already existed, then removed the entry, leaving the user with no
    # library until the next run.
    for i in range(len(libs) - 1, -1, -1):
        if libs[i].name in BIBLIOTECAS_ANTIGAS:
            try:
                libs.remove(libs[i])
            except Exception as e:
                if not silencioso:
                    print("[Archy Builder] remove old library:", e)

    ja = any(os.path.normcase(os.path.normpath(bpy.path.abspath(l.path))) == alvo
             for l in libs if l.path)
    if not ja:
        try:
            bpy.ops.preferences.asset_library_add(directory=caminho)
            libs[-1].name = NOME_BIBLIOTECA
            registradas.append(NOME_BIBLIOTECA)
        except Exception as e:
            if not silencioso:
                print("[Archy Builder] registration failed:", e)

    # The hierarchy must exist BEFORE the first save, otherwise the Asset
    # Browser opens without folders.
    try:
        _garantir_catalogos(caminho)
    except Exception as e:
        if not silencioso:
            print("[Archy Builder] catalogs:", e)
    return registradas




def caminhos_catalogo():
    """The entire ARVORE as hierarchical catalog paths.

    Each level gets ITS OWN line: Blender displays implicit parents,
    but an asset can only be FILED at a level that exists as a real
    catalog. Assets must be fileable at any depth in the hierarchy."""
    caminhos = [CAT_RAIZ]
    arvores = [ARVORE]
    try:
        arvores.append(_niveis_do_indice())
    except Exception as e:
        print("[Archy Builder] index levels:", e)
    for arv in arvores:
        for n1, filhos in arv.items():
            caminhos.append("%s/%s" % (CAT_RAIZ, n1))
            for n2, netos in filhos.items():
                caminhos.append("%s/%s/%s" % (CAT_RAIZ, n1, n2))
                for n3 in netos:
                    caminhos.append("%s/%s/%s/%s" % (CAT_RAIZ, n1, n2, n3))
    # Include deeper preset levels too (the library has unlimited
    # depth: Armarios > Cozinha > Altos > Despenseiros).
    try:
        for it in indice_completo():
            trilha = caminho_de(it)
            for k in range(1, len(trilha) + 1):
                caminhos.append(catalogo_de(*trilha[:k]))
    except Exception as e:
        print("[Archy Builder] index levels:", e)
    return list(dict.fromkeys(caminhos))


def catalogo_de(*niveis):
    """Deepest catalog path for the chosen levels, of any depth."""
    partes = [x for x in niveis if x]
    if not partes:
        return ""
    return CAT_RAIZ + "/" + "/".join(partes)


def _migrar_raiz(caminho):
    """Replace an old root with the current one, preserving the remaining path."""
    for velha in RAIZES_ANTIGAS:
        if caminho == velha:
            return CAT_RAIZ
        if caminho.startswith(velha + "/"):
            return CAT_RAIZ + caminho[len(velha):]
    return caminho


def _garantir_catalogos(raiz, extras=()):
    """Create/update blender_assets.cats.txt with the add-on hierarchy.

    PRESERVE existing lines with the same UUID: presets store the catalog
    UUID inside the .blend, so generating a new one would make the asset
    disappear from the Asset Browser tree."""
    arq = os.path.join(raiz, "blender_assets.cats.txt")
    existentes = {}
    if os.path.exists(arq):
        for linha in open(arq, encoding="utf-8"):
            linha = linha.strip()
            if not linha or linha.startswith("#") or linha.startswith("VERSION"):
                continue
            partes = linha.split(":")
            if len(partes) >= 2:
                # Rename an old root to the new one WHILE KEEPING its UUID, so the asset
                # still finds its catalog and no duplicate tree remains.
                existentes.setdefault(_migrar_raiz(partes[1]), partes[0])
    for cam in list(caminhos_catalogo()) + [x for x in extras if x]:
        existentes.setdefault(cam, str(uuid.uuid4()))
    # Simple name = hyphenated path, following Blender's convention.
    texto = "VERSION 1\n\n" + "".join(
        "%s:%s:%s\n" % (existentes[cam], cam, cam.replace("/", "-"))
        for cam in sorted(existentes))
    _gravar_se_mudou(arq, texto)
    return existentes


def _gravar_se_mudou(arq, texto):
    """Write `texto` to `arq` ATOMICALLY, only if changed.

    Every add-on registration passes here. Previously the file was reopened
    with "w" (truncate and rewrite) each time. With two Blenders registering
    concurrently (parallel harness suites or two user instances), one could
    read the other's truncated file and generate NEW UUIDs for all catalogs,
    losing preset categories (observed 2026-10-09). A temporary file plus
    os.replace never exposes a partial file. Explicit newline: .gitattributes
    requires LF; otherwise Windows writes CRLF."""
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
            # Windows refuses replacement while another process is reading.
            time.sleep(0.05)
    try:
        os.remove(temporario)
    except OSError:
        pass
    # False already means "unchanged": silent failure let the caller use
    # a catalog UUID that was never written to disk.
    raise OSError("could not write " + arq)


def refiliar_preset(caminho, niveis):
    """Reassign the catalog of a preset ALREADY saved on disk.

    The catalog lives inside the .blend (`asset_data.catalog_id`), not in
    indice.json, so moving a preset between categories requires loading
    the asset datablock, changing its ID, and rewriting the file.

    Return (ok, message)."""
    cam = catalogo_de(*niveis)
    if not cam:
        return False, "item has no category in the index"
    if not os.path.exists(caminho):
        return False, "file not found"
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
        return False, "no assets in the file"

    # Only catalog_id is writable; Blender derives the simple name.
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
    """Read a PNG and return pixels ready for an ImagePreview."""
    img = None
    try:
        img = bpy.data.images.load(caminho)
        # 'Raw' avoids color-space conversion: the preview retains the
        # PNG's values without changing gamma.
        try:
            img.colorspace_settings.name = 'Raw'
        except Exception:
            pass
        if tuple(img.size) != (lado, lado):
            img.scale(lado, lado)
        return list(img.pixels)
    except Exception as e:
        print("[Archy Builder] preview:", e)
        return None
    finally:
        if img is not None:
            try:
                bpy.data.images.remove(img)
            except Exception:
                pass


def aplicar_preview_png(caminho_blend, caminho_png):
    """Write the preset photo INSIDE the .blend as the asset preview.

    `asset_generate_preview()` is unsuitable: it only queues an asynchronous
    render job, and the file is saved before the job finishes. Presets
    therefore reached the Asset Browser with an empty zeroed 128x128
    preview and appeared with a generic icon. Writing pixels directly
    is synchronous and survives saving."""
    if not os.path.exists(caminho_blend):
        return False, "blend file not found"
    if not os.path.exists(caminho_png):
        return False, "no photo (.png) next to the preset"
    pixels = _pixels_png(caminho_png)
    if not pixels:
        return False, "could not read the photo"

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
        return False, "no assets in the file"

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
        # Without the icon size, the Asset Browser falls back to a generic icon.
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
    """Rewrite preset photos inside .blend files so the Asset Browser
    no longer shows the generic icon."""
    bl_idname = "object.cabinet_regerar_previews"
    bl_label = "Regenerate Library Previews"
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
            print("[Archy Builder] preview:", f)
        if falhas:
            self.report({'WARNING'},
                        "%d preview(s) saved, %d without photos -- save the preset again" % (feitos, len(falhas)))
        else:
            self.report({'INFO'}, "%d preview(s) saved" % feitos)
        return {'FINISHED'}


class OBJECT_OT_refiliar_catalogos(Operator):
    """File team presets in hierarchical catalogs according to each
    preset's category in the index."""
    bl_idname = "object.cabinet_refiliar"
    bl_label = "Reorganize Catalogs"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        feitos, falhas = 0, []
        for it in indice_completo():
            ok, msg = refiliar_preset(
                os.path.join(it["pasta"], it["arquivo"]), caminho_de(it))
            if ok:
                feitos += 1
            else:
                falhas.append("%s: %s" % (it.get("nome", "?"), msg))
        for f in falhas:
            print("[Archy Builder] reassign catalog:", f)
        if falhas:
            self.report({'WARNING'},
                        "%d moved, %d failed -- see console"
                        % (feitos, len(falhas)))
        else:
            self.report({'INFO'}, "%d preset(s) reorganized" % feitos)
        return {'FINISHED'}


def _nome_arquivo_seguro(nome):
    limpo = "".join(ch if (ch.isalnum() or ch in " -_") else "_" for ch in nome).strip()
    return (limpo or "sem_nome").replace(" ", "_")


def salvar_na_biblioteca(objs, nome, como_colecao, niveis=None):
    """Write objects to a library .blend.

    como_colecao=True groups everything in a Collection and marks the
    COLLECTION as an asset. Cabinets require this: dragging an object
    imports only that object, while dragging a collection imports the
    whole assembly.

    `niveis` = (n1, n2, n3): file the asset in its CATEGORY catalog, shown
    in the left Asset Browser hierarchy. Without levels, use the type
    catalog (Chapas/Modulos), as before."""
    raiz = destino = pasta_biblioteca()
    # Without levels, fall back to the type catalog; include it as an extra
    # so it exists in .cats.txt without cluttering hierarchy level 1.
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
            col.asset_data.description = "Archy Builder Cabinet - %d component(s)" % len(objs)
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

    # The Asset Browser preview is NOT generated here: `asset_generate_preview`
    # is asynchronous and never finishes before saving. `aplicar_preview_png`
    # writes it after the preset photo exists.

    arquivo = os.path.join(destino, _nome_arquivo_seguro(nome) + ".blend")
    bpy.data.libraries.write(arquivo, blocos, fake_user=True, compress=True)

    if como_colecao:
        # The collection was created only to package the asset.
        bpy.data.collections.remove(col)
    return arquivo


# ======================================= LIBRARY TREE
# Horizontal hierarchy: level 1 at the top; each chosen level opens the next below.
# ARVORE is only the three-level saving TEMPLATE; presets may go
# deeper (unlimited levels requested by the user). The entire path
# is stored in `niveis` in the index (`caminho_de`).
AMBIENTES = ["Living Room", "Kitchen", "Veranda", "Bedroom", "Bathroom", "Outdoor"]

ARVORE = {
    "Cabinets": {
        "Living Room":     ["Base Cabinets", "Wall Cabinets", "Corners", "Bookcases"],
        "Kitchen":  ["Base Cabinets", "Wall Cabinets", "Corners", "Tower Cabinets"],
        "Veranda":  ["Base Cabinets", "Wall Cabinets", "Countertops"],
        "Bedroom":   ["Base Cabinets", "Wall Cabinets", "Closets", "Drawer Units"],
        "Bathroom": ["Vanity Cabinets", "Mirror Cabinets", "Niches"],
        "Outdoor":  ["Base Cabinets", "Wall Cabinets", "Countertops"],
    },
    "Panels":     {"Loose Panels": []},
    "Doors":     {"Hinged": [], "Sliding": [], "Lift-up": []},
    "Handles":  {"Profile": [], "Pull": [], "Edge": [], "Recessed": []},
    "Hinges": {"Standard": [], "Soft-Close": [], "Specials": []},
}


def _niveis_de(it):
    """Read the FIRST three levels of an index item, accepting the old
    format (categoria/subcategoria) to keep saved indices valid.
    The full path at any depth is `caminho_de`."""
    if it.get("niveis"):
        trilha = list(caminho_de(it)) + ["", "", ""]
        return trilha[0], trilha[1], trilha[2]
    n1 = it.get("n1")
    if n1:
        return n1, it.get("n2", ""), it.get("n3", "")
    cat, sub = it.get("categoria", ""), it.get("subcategoria", "")
    if cat in AMBIENTES:
        return "Cabinets", cat, sub
    return cat, sub, ""


def caminho_de(it):
    """ALL nonempty item levels: ('Armarios', 'Cozinha', 'Altos', 'Despenseiros').
    Without stored `niveis`, use the usual three."""
    if it.get("niveis"):
        return tuple(str(n) for n in it["niveis"] if n)
    n1 = it.get("n1")
    if n1:
        trilha = (n1, it.get("n2", ""), it.get("n3", ""))
    else:
        cat, sub = it.get("categoria", ""), it.get("subcategoria", "")
        trilha = ("Cabinets", cat, sub) if cat in AMBIENTES else (cat, sub)
    return tuple(n for n in trilha if n)


def filhos_de(itens, pai):
    """Names immediately below `pai` (tuple) that HAVE presets in `itens`.
    The hierarchy hides empty branches, which would otherwise be buttons
    leading nowhere. Order: ARVORE first, then index order."""
    pai = tuple(pai)
    modelo = []
    if len(pai) == 0:
        modelo = list(ARVORE.keys())
    elif len(pai) == 1:
        modelo = list(ARVORE.get(pai[0], {}).keys())
    elif len(pai) == 2:
        modelo = list(ARVORE.get(pai[0], {}).get(pai[1], []))
    n = len(pai)
    com_itens = []
    for it in itens:
        trilha = caminho_de(it)
        if len(trilha) > n and trilha[:n] == pai and trilha[n] not in com_itens:
            com_itens.append(trilha[n])
    return ([k for k in modelo if k in com_itens]
            + [k for k in com_itens if k not in modelo])


def itens_em(itens, trilha):
    """Presets located EXACTLY at this path."""
    trilha = tuple(trilha)
    return [it for it in itens if caminho_de(it) == trilha]


def trilha_da_cena(s, prefixo='chapa_n'):
    """Chosen hierarchy path: the scene's three levels and the remainder
    in `<prefixo>_mais`, separated by '/'."""
    trilha = [getattr(s, prefixo + str(i), '') for i in (1, 2, 3)]
    trilha += (getattr(s, prefixo + '_mais', '') or '').split('/')
    saida = []
    for n in trilha:
        if not n:
            break
        saida.append(n)
    return tuple(saida)


def definir_trilha(s, trilha, prefixo='chapa_n'):
    trilha = list(trilha)
    for i in (1, 2, 3):
        setattr(s, prefixo + str(i), trilha[i - 1] if len(trilha) >= i else "")
    if hasattr(s, prefixo + '_mais'):
        setattr(s, prefixo + '_mais', '/'.join(trilha[3:]))


def _niveis_do_indice():
    """Categories that EXIST in saved presets, in addition to ARVORE.

    This connects both interfaces: a subcategory typed through "+" in
    the N-panel appears in the hierarchy and also becomes a catalog."""
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


def _ler_indice(pasta, estrito=False):
    """JSON index beside the .blend files, allowing the panel to list presets
    without opening each file; doing that merely to build a list would
    freeze the interface.

    `estrito`: callers REWRITING the index must not treat unreadable files
    as empty, or they would overwrite all existing items with just the new one."""
    arq = os.path.join(pasta, NOME_INDICE)
    if not os.path.exists(arq):
        return []
    try:
        with open(arq, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        if estrito:
            raise
        print("[Archy Builder] unreadable index:", e)
        return []


def _gravar_indice(pasta, itens):
    try:
        _gravar_se_mudou(os.path.join(pasta, NOME_INDICE),
                         json.dumps(itens, ensure_ascii=False, indent=1) + "\n")
        _biblioteca_faixa.invalidar()
    except Exception as e:
        print("[Archy Builder] index not saved:", e)


def indice_completo():
    """Read the company library index."""
    pasta = pasta_biblioteca()
    itens = []
    for it in _ler_indice(pasta):
        it = dict(it)
        it["origem"] = "biblioteca"
        it["pasta"] = pasta
        itens.append(it)
    return itens


def registrar_no_indice(pasta, nome, arquivo, *niveis_e_tipo):
    """`niveis_e_tipo` = levels of ANY depth, followed by the type:
    (n1, n2, n3, tipo) as before, or (n1, n2, n3, n4, ..., tipo).
    For more than three levels, store the full path in `niveis`; retain
    n1/n2/n3 for the old index format."""
    *niveis, tipo = niveis_e_tipo
    niveis = [n for n in niveis if n]
    itens = [i for i in _ler_indice(pasta, estrito=True)
             if not (i.get("arquivo") == os.path.basename(arquivo))]
    tres = (niveis + ["", "", ""])[:3]
    item = {"nome": nome, "arquivo": os.path.basename(arquivo),
            "n1": tres[0], "n2": tres[1], "n3": tres[2], "tipo": tipo}
    if len(niveis) > 3:
        item["niveis"] = niveis
    itens.append(item)
    _gravar_indice(pasta, itens)


def itens_de_fabrica():
    """FACTORY handle-creator and hinge models in the library hierarchy,
    as requested by the user: LOCKED, stored in the add-on outside the
    index, so neither "Edit" nor the lock affects them. Users edit THEIR
    models in the Puxadores category, and the creator follows those changes."""
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
        it.update(nome=nome, n1="Hinges", n2="Standard", n3='',
                  tipo='objeto', bloqueado=True, fabrica='dobradica',
                  valor=tipo)
        itens.append(it)
    return itens


def inserir_preset(context, pasta, arquivo, tipo, destino=None):
    """Load the preset .blend into the scene and select the imported objects.

    Return (new objects, roots, error). `destino` is the offset applied
    to roots; without it, insert at the 3D cursor rather than the origin."""
    caminho = os.path.join(pasta, arquivo)
    if not os.path.exists(caminho):
        return [], [], "File not found: " + caminho
    antes = set(bpy.data.objects)
    colecoes_antes = set(bpy.data.collections)
    ocupado = _chapas._ocupado[0]
    _chapas._ocupado[0] = True
    try:
        with bpy.data.libraries.load(caminho) as (de, para):
            if tipo == "modulo" and de.collections:
                para.collections = list(de.collections)
            else:
                para.objects = list(de.objects)
        novos = set(bpy.data.objects) - antes
        novas_cols = set(bpy.data.collections) - colecoes_antes
        filhas = {f for c in novas_cols for f in c.children}
        # Native append already brought the relationships. Linking every
        # subcollection to the root too duplicates layer and depsgraph paths.
        for c in novas_cols - filhas:
            context.scene.collection.children.link(c)
        ligados = {o for c in novas_cols for o in c.all_objects}
        for o in novos - ligados:
            context.scene.collection.objects.link(o)
        raizes = [o for o in novos if o.parent not in novos]
        desloc = context.scene.cursor.location.copy() if destino is None else destino
        for o in raizes:
            o.location = o.location + desloc
        for o in context.selected_objects:
            o.select_set(False)
        for o in novos:
            try:o.select_set(True)
            except RuntimeError:pass
        # hide_set belongs to the layer and is not saved in the preset.
        _ferragens.ocultar_pecas_do_rig(novos)
    finally:
        _chapas._ocupado[0] = ocupado
    context.view_layer.update()
    conjuntos=[o for o in novos if _chapas.MARCA_CONJUNTO in o]
    for o in conjuntos:
        _promob.corrigir_curvas_legadas(o)
        _modulos.sincronizar_medidas_conjunto(o)
    novos=set(bpy.data.objects)-antes
    raizes=[o for o in novos if o.parent not in novos]
    _ferragens.ocultar_pecas_do_rig(novos)
    for o in novos:
        if o.type=='MESH' and _chapas.MARCA_CHAPA in o:
            _frentes.preparar(o)
    novos = sorted(novos, key=lambda o:o.name)
    return novos, raizes, ""


# Preset box in the index (user request, v321): dragging shows only the
# wireframe and loads the .blend on RELEASE, like BlenderKit. Loading
# at drag start froze the screen in real scenes. Without a cached box,
# the first drag loads as before and stores it for subsequent drags.
CHAVE_CAIXA = 'caixa'


def _arredondar(valores):
    return [round(float(v), 6) for v in valores]


def medir_caixa(context, novos, raizes):
    """Evaluated box (lo, hi) of the newly inserted preset, in world space."""
    context.view_layer.update()
    try:
        dep = context.evaluated_depsgraph_get()
    except Exception:
        dep = None
    pontos = []
    for obj in novos:
        if obj.type in _modulos.TIPOS_COM_VOLUME:
            pontos.extend(_modulos._cantos_avaliados(obj, dep))
    if not pontos:
        pontos = [o.matrix_world.translation.copy() for o in raizes]
    if not pontos:
        raise RuntimeError("preset has no geometry")
    return (Vector(tuple(min(p[i] for p in pontos) for i in range(3))),
            Vector(tuple(max(p[i] for p in pontos) for i in range(3))))


def registro_da_caixa(caminho, lo, hi, modulo=None):
    """Data read from a preset during dragging without loading it. `bytes`
    invalidates the record when the .blend changes (Git changes dates, not sizes)."""
    registro = {'bytes': os.path.getsize(caminho), 'lo': _arredondar(lo),
                'hi': _arredondar(hi)}
    caixa = _paredes.caixa_local_do_modulo(modulo) if modulo is not None else None
    if caixa is not None:
        registro['modulo'] = {'lo': _arredondar(caixa[0]), 'hi': _arredondar(caixa[1]),
                              'matriz': _arredondar(v for linha in modulo.matrix_world
                                                    for v in linha),
                              # Side placed against the wall (opposite the door).
                              'costas': _paredes.lado_das_costas(modulo, caixa)}
    return registro


def caixa_do_preset(pasta, arquivo):
    """Record stored in the index, if still valid for the file."""
    item = next((i for i in _ler_indice(pasta) if i.get('arquivo') == arquivo), None)
    registro = item.get(CHAVE_CAIXA) if item else None
    try:
        if registro and registro.get('modulo') and 'costas' not in registro['modulo']:
            return None         # Record predates `costas`: measure again.
        if registro and registro.get('bytes') == os.path.getsize(os.path.join(pasta, arquivo)):
            return registro
    except OSError:
        pass
    return None


def _matriz_do_registro(valores):
    return Matrix([valores[i:i + 4] for i in range(0, 16, 4)])


class _PresetPrevisto:
    """Preset NOT yet loaded: root data read by placement (matrix, location,
    empty name, specified ID properties). On release, the real root
    receives its matrix/offset and properties."""

    def __init__(self, matriz, props=None):
        self.name = ''
        self.matrix_world = matriz.copy()
        self.props = dict(props or {})

    @property
    def location(self):
        return self.matrix_world.translation.copy()

    @location.setter
    def location(self, valor):
        matriz = self.matrix_world.copy()
        matriz.translation = Vector(valor)
        self.matrix_world = matriz

    def get(self, chave, padrao=None):
        return self.props.get(chave, padrao)

    def __contains__(self, chave):
        return chave in self.props

    def __getitem__(self, chave):
        return self.props[chave]

    def __setitem__(self, chave, valor):
        self.props[chave] = valor


class OBJECT_OT_inserir_preset(Operator):
    """Insert the library preset at the 3D cursor."""
    bl_idname = "object.cabinet_inserir_preset"
    bl_label = "Insert"
    bl_options = {'REGISTER', 'UNDO'}

    pasta: bpy.props.StringProperty()
    arquivo: bpy.props.StringProperty()
    tipo: bpy.props.StringProperty(default="modulo")

    def execute(self, context):
        if _paredes_edicao.ativa(context):
            erro = _paredes_edicao.inserir_modelo(context, self.pasta, self.arquivo, self.tipo)
            if erro:
                self.report({'WARNING'}, erro)
            return {'CANCELLED'} if erro else {'FINISHED'}
        novos, _raizes, erro = inserir_preset(
            context, self.pasta, self.arquivo, self.tipo)
        if erro:
            self.report({'ERROR'}, erro)
            return {'CANCELLED'}
        self.report({'INFO'}, "%d object(s) inserted" % len(novos))
        return {'FINISHED'}


# The second photo double click may move slightly.
RAIO_DUPLO_CLIQUE_PX = 8


class OBJECT_OT_arrastar_preset(Operator):
    """Drag with a crosshair and exact box before inserting into the scene."""
    bl_idname = "object.cabinet_arrastar_preset"
    bl_label = "Drag into Scene"
    bl_options = {'REGISTER', 'UNDO'}

    # SKIP_SAVE: Blender persists operator properties between executions,
    # but dragging must discover them again each time.
    pasta: bpy.props.StringProperty(options={'SKIP_SAVE'})
    arquivo: bpy.props.StringProperty(options={'SKIP_SAVE'})
    tipo: bpy.props.StringProperty(default="modulo", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.area is not None and (context.area.type == 'VIEW_3D' or _gaveta._eh_area_gaveta(context))

    def invoke(self, context, event):
        if (self.arquivo and _paredes_edicao.ativa(context)
                and _paredes_edicao._sessao[0].get('substituir')):
            erro = _paredes_edicao.preparar_modelo(context, self.pasta, self.arquivo, self.tipo)
            if erro:
                self.report({'WARNING'}, erro)
            return {'CANCELLED'} if erro else {'FINISHED'}
        # Without a preset in the properties, dragging started over the grid:
        # read the tile under the cursor from context.button_operator, which
        # supplies the pointed button's properties, the same facility Blender
        # uses for "Assign Shortcut" in a button's context menu.
        if not self.arquivo:
            alvo = getattr(context, "button_operator", None)
            # Import, lock, and pencil buttons also carry `arquivo`:
            # only the thumbnail and name (this operator)
            # are valid drag handles.
            origem = getattr(getattr(alvo, "bl_rna", None), "identifier", "")
            arquivo = (getattr(alvo, "arquivo", "")
                       if origem.endswith("cabinet_arrastar_preset") else "")
            if not arquivo:
                # Dragging elsewhere in the sidebar: return the event
                # to Blender, otherwise sliders would stop moving.
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

        # First-click timestamp: measure the photo double click from it.
        self._instante_inicio = time.monotonic()
        # The grid lives in the sidebar, so the event region is NOT
        # the viewport: find the drawing window within the area.
        self._area_preview = context.area
        if _gaveta._eh_area_gaveta(context):
            self._area_preview = _biblioteca_faixa.viewport(context.screen)
        self._regiao = next(
            (r for r in self._area_preview.regions if r.type == 'WINDOW'), None
        ) if self._area_preview else None
        self._rv3d = getattr(self._area_preview.spaces.active, "region_3d", None
                             ) if self._area_preview else None
        if self._regiao is None or self._rv3d is None:
            self.report({'ERROR'}, "No 3D viewport for placement")
            return {'CANCELLED'}
        # The draw handler may run on the first redraw after registration;
        # prepare the region filter before that moment.
        self._regiao_ptr = self._regiao.as_pointer()

        self._selecionados_antes = list(context.selected_objects)
        self._ativo_antes = context.view_layer.objects.active
        colecoes_antes = set(bpy.data.collections)
        self._novos = []
        self._raizes = []
        self._colecoes_novas = []

        self._previa = caixa_do_preset(self.pasta, self.arquivo)
        self._carregando = False
        self._handler_aviso = self._tique = None
        if self._previa is not None:
            # Wireframe only; load the .blend on release (`_carregar`).
            modulo = self._previa.get('modulo')
            self._raizes = [_PresetPrevisto(_matriz_do_registro(modulo['matriz']),
                                            {_paredes.CHAVE_COSTAS: modulo['costas']})
                            if modulo else _PresetPrevisto(Matrix.Identity(4))]
        else:
            # Load the preset hidden as staging. It becomes visible only
            # when released inside the viewport; cancellation deletes it.
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
                self.report({'WARNING'}, "The preset contained no objects")
                return {'CANCELLED'}

        self._base = {o: o.location.copy() for o in self._raizes}
        self._sessao_parede = (_paredes_edicao._sessao[0]['id']
                                if _paredes_edicao.ativa(context) else 0)
        self._modulo_unico = self.tipo == 'modulo' and (
            bool(self._previa.get('modulo')) if self._previa is not None else
            len(self._raizes) == 1 and _chapas.MARCA_CONJUNTO in self._raizes[0])
        if self._sessao_parede and not self._modulo_unico:
            self._apagar()
            self._restaurar_selecao(context)
            self.report({'WARNING'}, "Choose a single complete cabinet")
            return {'CANCELLED'}
        self._na_parede = None
        self._caixa_parede_base = self._caixa_local = None
        if self._modulo_unico:
            self._matriz_parede_base = self._raizes[0].matrix_world.copy()
            if self._previa is not None:
                modulo = self._previa['modulo']
                self._caixa_local = (Vector(modulo['lo']), Vector(modulo['hi']))
            else:
                self._caixa_local = _paredes.caixa_local_do_modulo(self._raizes[0])
            self._girar_caixa()
        self._automatico_parede = False
        self._altura = context.scene.cursor.location.z
        self._alvo = None
        self._normal = Vector((0.0, 0.0, 1.0))
        self._bbox_atual = []
        self._erro_posicionamento = ''
        self._aviso_ajuste = ''
        self._cache_ajuste = {}
        self._caixa_prevista = None
        self._valido = False
        self._em_superficie = False
        self._handler_preview = None

        try:
            self._preparar_bbox(context)
            self._ocultar_staging(context)
            self._handler_preview = bpy.types.SpaceView3D.draw_handler_add(
                self._desenhar_preview, (), 'WINDOW', 'POST_VIEW')
            self._handler_aviso = bpy.types.SpaceView3D.draw_handler_add(
                self._desenhar_aviso, (), 'WINDOW', 'POST_PIXEL')
        except Exception as e:
            print("[Archy Builder] drag preview:", e)
            self._encerrar_visual(context)
            self._apagar()
            self._restaurar_selecao(context)
            self.report({'ERROR'}, "Could not prepare the preview")
            return {'CANCELLED'}

        item = next((i for i in _ler_indice(self.pasta) if i.get('arquivo') == self.arquivo), None)
        self._nome = item.get("nome", self.arquivo) if item else self.arquivo
        try:
            context.workspace.status_text_set(
                "Dragging %s | Release: insert | Right click: cancel"
                % self._nome)
        except Exception:
            pass
        self._mover(context, event)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _preparar_bbox(self, context):
        """Measure evaluated staging (or read the stored box) and anchor
        at the base center."""
        if getattr(self, '_previa', None) is not None:
            lo, hi = Vector(self._previa['lo']), Vector(self._previa['hi'])
        else:
            lo, hi = medir_caixa(context, self._novos, self._raizes)
            self._gravar_caixa(lo, hi)
        self._bbox_base = (
            Vector((lo.x, lo.y, lo.z)), Vector((hi.x, lo.y, lo.z)),
            Vector((hi.x, hi.y, lo.z)), Vector((lo.x, hi.y, lo.z)),
            Vector((lo.x, lo.y, hi.z)), Vector((hi.x, lo.y, hi.z)),
            Vector((hi.x, hi.y, hi.z)), Vector((lo.x, hi.y, hi.z)),
        )
        if getattr(self, '_sessao_parede', 0):
            # The whole staging box includes handles/open leaves and may be
            # rotated. The preview must use the validated envelope.
            lo, hi = self._caixa_local
            matriz = self._matriz_parede_base
            self._bbox_base = tuple(matriz @ Vector((x, y, z)) for z in (lo.z, hi.z)
                for x, y in ((lo.x, lo.y), (hi.x, lo.y), (hi.x, hi.y), (lo.x, hi.y)))
        self._ancora_base = Vector((
            (lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, lo.z))
        diagonal = (hi - lo).length
        self._tamanho_mira = max(0.04, min(diagonal * 0.08, 0.35))

    def _gravar_caixa(self, lo, hi):
        """First drag of a preset without an indexed box: store it so
        subsequent drags load only on release."""
        try:
            if not any(i.get('arquivo') == self.arquivo for i in _ler_indice(self.pasta)):
                return
            registro = registro_da_caixa(os.path.join(self.pasta, self.arquivo), lo, hi,
                                         self._raizes[0] if self._modulo_unico else None)
            _atualizar_item(self.pasta, self.arquivo, {CHAVE_CAIXA: registro})
        except Exception as e:
            print("[Archy Builder] preset box not saved:", e)

    def _esperar_carga(self, context):
        """On release, keep the wireframe still with "Loading..." and load the
        .blend on the next tick, AFTER the message appears onscreen
        (loading blocks the interface until it finishes)."""
        self._carregando = True
        try:
            context.workspace.status_text_set("Loading %s..." % self._nome)
        except Exception:
            pass
        if self._handler_aviso is None:
            self._handler_aviso = bpy.types.SpaceView3D.draw_handler_add(
                self._desenhar_aviso, (), 'WINDOW', 'POST_PIXEL')
        self._tique = context.window_manager.event_timer_add(0.05, window=context.window)
        self._area_preview.tag_redraw()
        return {'RUNNING_MODAL'}

    def _encerrar_carga(self, context):
        if self._tique is not None:
            context.window_manager.event_timer_remove(self._tique)
            self._tique = None
        if self._handler_aviso is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler_aviso, 'WINDOW')
            self._handler_aviso = None

    def _carregar(self, context):
        """Load the .blend and move the actual root to the wireframe position."""
        self._encerrar_carga(context)
        self._carregando = False
        previsto = self._raizes[0]
        colecoes_antes = set(bpy.data.collections)
        novos, raizes, erro = inserir_preset(context, self.pasta, self.arquivo, self.tipo,
                                             destino=Vector((0.0, 0.0, 0.0)))
        self._novos = list(novos or [])
        self._colecoes_novas = [c for c in bpy.data.collections if c not in colecoes_antes]
        modulo_ok = not self._modulo_unico or (
            len(raizes) == 1 and _chapas.MARCA_CONJUNTO in raizes[0])
        if erro or not self._novos or not modulo_ok:
            self.report({'ERROR'}, erro or "The preset changed; drag again")
            return self._cancelar(context)
        self._previa = None
        self._raizes = list(raizes)
        if self._modulo_unico and (self._na_parede is not None or self._sessao_parede):
            self._raizes[0].matrix_world = previsto.matrix_world
            # Face selected with the wheel (or stored in the index).
            if _paredes.CHAVE_COSTAS in previsto:
                self._raizes[0][_paredes.CHAVE_COSTAS] = previsto[_paredes.CHAVE_COSTAS]
        else:
            deslocamento = previsto.location - self._base[previsto]
            for o in self._raizes:
                o.location = o.location + deslocamento
        self._base = {o: o.location.copy() for o in self._raizes}
        context.view_layer.update()
        return self._confirmar(context)

    def _desenhar_aviso(self):
        """Show loading status or a constraint beside the preview, without a popup."""
        try:
            erro = getattr(self, '_erro_posicionamento', '') or getattr(self, '_aviso_ajuste', '')
            if not self._carregando and not erro:
                return
            regiao = bpy.context.region
            if (regiao is None or regiao.as_pointer() != self._regiao_ptr
                    or self._alvo is None):
                return
            xy = view3d_utils.location_3d_to_region_2d(regiao, bpy.context.region_data,
                                                       self._alvo)
            if xy is None:
                return
            escala = bpy.context.preferences.system.ui_scale
            texto = "Loading %s..." % self._nome if self._carregando else erro
            blf.size(0, 13 * escala)
            largura, altura = blf.dimensions(0, texto)
            folga = 6 * escala
            largura = min(largura, regiao.width - 2 * folga)
            x = max(folga, min(regiao.width - largura - folga, xy.x - largura / 2))
            y = max(folga, min(regiao.height - altura - folga, xy.y - altura / 2))
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            gpu.state.blend_set('ALPHA')
            shader.bind()
            shader.uniform_float('color', (0.0, 0.0, 0.0, 0.8))
            x0, y0, x1, y1 = x - folga, y - folga, x + largura + folga, y + altura + folga
            batch_for_shader(shader, 'TRIS', {'pos': ((x0, y0), (x1, y0), (x1, y1),
                                                      (x0, y0), (x1, y1), (x0, y1))}).draw(shader)
            _gaveta._texto_cabivel_gaveta(x, y, texto, largura,
                                         tamanho=13 * escala, cor=(1, 1, 1, 1))
        except Exception as e:
            print("[Archy Builder] placement warning:", e)
        finally:
            gpu.state.blend_set('NONE')

    def _ocultar_staging(self, context):
        """Hide actual geometry so only the GPU preview remains."""
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
        if getattr(self, '_tique', None) is not None or getattr(self, '_handler_aviso', None) is not None:
            self._encerrar_carga(context)
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
        """Draw a box and crosshair over the viewport without creating geometry."""
        if not self._bbox_atual:
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
            shader.uniform_float("color", (0.1, 1.0, 0.2, 0.9) if self._valido else (1.0, 0.15, 0.1, 0.9))
            batch_for_shader(
                shader, 'LINES', {"pos": linhas_box}).draw(shader)
            shader.uniform_float(
                "color", (1.0, 0.85, 0.1, 1.0)
                if self._em_superficie else (0.9, 0.9, 0.9, 1.0))
            batch_for_shader(
                shader, 'LINES', {"pos": linhas_mira}).draw(shader)
        except Exception as e:
            print("[Archy Builder] preview drawing:", e)
        finally:
            try:
                gpu.state.line_width_set(1.0)
                gpu.state.depth_test_set('NONE')
                gpu.state.blend_set('NONE')
            except Exception:
                pass

    def _na_viewport(self, event):
        """Release is valid only inside the viewport, like native dragging."""
        dx = event.mouse_x - self._regiao.x
        dy = event.mouse_y - self._regiao.y
        return 0 <= dx < self._regiao.width and 0 <= dy < self._regiao.height

    def _mover(self, context, event):
        """Raycast the scene, falling back to the cursor plane."""
        self._erro_posicionamento = ''
        self._aviso_ajuste = ''
        self._caixa_prevista = None
        self._bbox_atual = []
        if not self._na_viewport(event):
            self._valido = False
            self._area_preview.tag_redraw()
            return
        if getattr(self, '_sessao_parede', 0):
            self._mover_na_parede(context, event)
            return
        coord = (event.mouse_x - self._regiao.x, event.mouse_y - self._regiao.y)
        try:
            origem = view3d_utils.region_2d_to_origin_3d(
                self._regiao, self._rv3d, coord)
            direcao = view3d_utils.region_2d_to_vector_3d(
                self._regiao, self._rv3d, coord)
        except Exception:
            return
        self._largar_parede()
        if self._mover_contra_parede(context, origem, direcao):
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
            print("[Archy Builder] drag raycast:", e)
        if alvo is None:
            alvo = intersect_line_plane(
                origem, origem + direcao * 1000.0,
                Vector((0.0, 0.0, self._altura)),
                Vector((0.0, 0.0, 1.0)))
        if alvo is None:        # Ray parallel to the plane: nothing to do.
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

    def _girar_caixa(self):
        """Box in the wall frame, using the root's back side.
        Store that side on the root: inferring it from the door on every mouse
        movement would scan panels."""
        if self._caixa_local is None:
            self._caixa_parede_base = None
            return
        raiz = self._raizes[0]
        raiz[_paredes.CHAVE_COSTAS] = _paredes.lado_das_costas(raiz, self._caixa_local)
        self._caixa_parede_base = _paredes.girar_caixa(self._caixa_local,
                                                       raiz[_paredes.CHAVE_COSTAS])

    def _trocar_face(self, context, event):
        """Mouse wheel over the wall: place the next face against it."""
        _paredes.girar_costas(self._raizes[0], _paredes.passos_da_roda(event))
        self._girar_caixa()
        self._mover(context, event)
        return {'RUNNING_MODAL'}

    def _largar_parede(self):
        """Off the wall: restore the preset's cabinet rotation."""
        if getattr(self, '_na_parede', None) is not None:
            self._raizes[0].matrix_world = self._matriz_parede_base
            self._na_parede = None
            self._status(bpy.context, "Release: insert")

    def _mover_contra_parede(self, context, origem, direcao):
        """Cabinet released on a wall outside 2D editing: back against the wall,
        as with right dragging. Previously the BASE center went to the ray
        point without rotating, leaving the cabinet sideways (user report).
        The cursor is the cabinet center; ends, floor, and ceiling snap, and
        neighbors are not overlapped (`encaixar_na_face`)."""
        if not getattr(self, '_modulo_unico', False) or self._caixa_parede_base is None:
            return False
        acerto = _paredes.raio_ate_parede(context, origem, direcao,
                                          {o.name for o in self._novos})
        if acerto is None:
            return False
        parede, ponto, normal, face = acerto
        if (parede.type != 'MESH' or _paredes.eh_movel(parede)
                or _paredes.eixos_da_parede(normal) is None):
            return False
        regiao = _paredes.regiao_da_parede(parede, ponto, normal,
                                           context.evaluated_depsgraph_get(), face)
        if regiao is None:
            return False
        n, u = _paredes.eixos_da_parede(normal)
        sessao = dict(parede=parede.name, regiao=regiao, ponto=tuple(ponto),
                      normal=tuple(n), u=tuple(u))
        modulo = self._raizes[0]
        px = _paredes._px_por_metro(self._regiao, self._rv3d, ponto, u)
        costas, erro = _paredes_edicao.encaixar_na_face(
            context, modulo, ponto, sessao, self._caixa_parede_base,
            _paredes.SNAP_PX / px if px else 0)
        if erro:
            costas, self._caixa_prevista, erro = _paredes_edicao.ajustar_na_face(
                context, modulo, ponto, sessao, self._caixa_parede_base, self._cache_ajuste)
        if erro:
            self._na_parede = None
        else:
            self._na_parede = (parede.name, tuple(costas), tuple(n), regiao['face'])
        self._prever_na_parede(context, ponto, costas, n, u, erro)
        self._area_preview.tag_redraw()
        return True

    def _status(self, context, texto):
        try:
            context.workspace.status_text_set(texto + " | Wheel: change face | Right click: cancel")
        except Exception:
            pass

    def _prever_na_parede(self, context, ponto, costas, normal, u, erro):
        modulo = self._raizes[0]
        lo, hi = self._caixa_prevista or self._caixa_parede_base
        altura = abs((hi.z - lo.z) * _paredes.escala_no_referencial(modulo).z)
        if erro:
            # Keep the rejection visible without allowing insertion or stretching.
            costas = ponto - Vector((0, 0, altura / 2))
        modulo.matrix_world = _paredes.matriz_na_parede(modulo, costas, normal, u,
                                                       caixa=self._caixa_prevista or self._caixa_parede_base)
        context.view_layer.update()
        matriz = modulo.matrix_world @ self._matriz_parede_base.inverted_safe()
        self._bbox_atual = [matriz @ p for p in self._bbox_base]
        if self._caixa_prevista is not None:
            referencia = _paredes.referencial(modulo)
            self._bbox_atual = [referencia @ Vector((x, y, z)) for z in (lo.z, hi.z)
                for x, y in ((lo.x, lo.y), (hi.x, lo.y), (hi.x, hi.y), (lo.x, hi.y))]
        self._alvo = costas + Vector((0, 0, altura / 2))
        self._normal = normal.copy()
        self._em_superficie = True
        self._valido = not erro
        self._erro_posicionamento = ("H: %.1f mm | %s" % (altura * 1000, erro)) if erro else ''
        original = self._caixa_parede_base[1] - self._caixa_parede_base[0]
        if not erro and any(abs((hi - lo)[i] - original[i]) > 1e-7 for i in range(3)):
            escala = _paredes.escala_no_referencial(modulo)
            self._aviso_ajuste = "Adjusted: %.1f x %.1f mm | Release to insert" % (
                abs((hi.x - lo.x) * escala.x) * 1000, altura * 1000)
        interferencia = not erro and _esquadrias.colisao(context, modulo, caixa=(lo, hi))
        self._status(context, self._erro_posicionamento or (_esquadrias.AVISO if interferencia else
                     self._aviso_ajuste or "Release to insert on wall"))

    def _mover_na_parede(self, context, event):
        self._valido = False
        ponto = _paredes_edicao.ponto_no_evento(context, event)
        if ponto is not None:
            # Hidden objects do not update their children in the depsgraph. The preview
            # uses the box measured before hiding, never a stale box.
            costas, self._caixa_prevista, erro = _paredes_edicao.encaixe_do_modelo(
                context, self._raizes[0], ponto, self._caixa_parede_base, self._cache_ajuste)
            s = _paredes_edicao._sessao[0]
            self._prever_na_parede(context, ponto, costas, Vector(s['normal']), Vector(s['u']), erro)
            self._ponto_parede = tuple(ponto)
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
        """A quick second click at the same position that opened the placement
        tool, outside the viewport.

        Measure HERE by the clock: Blender delivers the second click as PRESS,
        not DOUBLE_CLICK (confirmed in the user's log: PRESS 67 ms after RELEASE),
        because the sidebar consumed the first click. Waiting only for
        DOUBLE_CLICK treated PRESS as a click outside the viewport and canceled
        insertion."""
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
        """Center the preset base on the 3D cursor and confirm."""
        if getattr(self, '_sessao_parede', 0):
            self._raizes[0].matrix_world = self._matriz_parede_base
            context.view_layer.update()
            self._automatico_parede = True
            return self._confirmar(context)
        if hasattr(self, '_largar_parede'):
            self._largar_parede()
        deslocamento = context.scene.cursor.location - self._ancora_base
        for o in self._raizes:
            base = self._base.get(o)
            if base is not None:
                o.location = base + deslocamento
        self._valido = True
        return self._confirmar(context)

    def _confirmar(self, context):
        if getattr(self, '_previa', None) is not None:
            return self._esperar_carga(context)
        if getattr(self, '_sessao_parede', 0):
            self._raizes[0].matrix_world = self._matriz_parede_base
            self._restaurar_staging()
            context.view_layer.update()
            ponto = None if self._automatico_parede else Vector(self._ponto_parede)
            erro = _paredes_edicao.posicionar_modelo(context, self._raizes[0], ponto, self._novos)
            if erro:
                self.report({'WARNING'}, erro)
                return self._cancelar(context)
        self._encerrar_visual(context)
        self._restaurar_staging()
        if getattr(self, '_na_parede', None) is not None:
            nome, costas, n, face = self._na_parede
            parede = bpy.data.objects.get(nome)
            if parede is not None:
                if self._caixa_prevista is not None:
                    erro = _paredes_edicao.aplicar_ajuste_do_modelo(self._raizes[0], self._caixa_prevista, self._novos)
                    if erro:
                        self.report({'WARNING'}, erro)
                        return self._cancelar(context)
                    _paredes.colocar_na_parede(self._raizes[0], parede, Vector(costas), Vector(n))
                _paredes.associar(self._raizes[0], parede, Vector(costas), Vector(n), face)
                _paredes_edicao.registrar_posicionado(context, self._raizes[0], self._novos)
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
        if self._raizes and _esquadrias.avisar(context, self._raizes[0]):
            self.report({'WARNING'}, _esquadrias.AVISO)
        else:
            self.report({'INFO'}, "%d object(s) inserted" % len(self._novos))
        return {'FINISHED'}

    def modal(self, context, event):
        if getattr(self, '_carregando', False):
            # Released: wait only for the tick that loads the .blend.
            return self._carregar(context) if event.type == 'TIMER' else {'RUNNING_MODAL'}
        if getattr(self, '_sessao_parede', 0) and (not _paredes_edicao.ativa(context)
                or _paredes_edicao._sessao[0]['id'] != self._sessao_parede):
            return self._cancelar(context)
        if event.type == 'MOUSEMOVE':
            if self._arrastando and not self._moveu:
                dx = event.mouse_x - self._mouse_inicio[0]
                dy = event.mouse_y - self._mouse_inicio[1]
                # The threshold prevents a click with slight involuntary
                # movement from becoming a drag.
                self._moveu = (dx * dx + dy * dy) >= 36
            self._mover(context, event)
            return {'RUNNING_MODAL'}
        if (_paredes.passos_da_roda(event) and self._caixa_local is not None
                and (self._na_parede is not None or getattr(self, '_sessao_parede', 0))):
            return self._trocar_face(context, event)

        if self._duplo_clique_na_foto(context, event):
            # Double click on the PHOTO (the first click opened this placement
            # tool): insert directly at the 3D cursor without aiming.
            return self._no_cursor(context)
        if event.type == 'LEFTMOUSE':
            confirma = 'RELEASE' if self._arrastando else 'PRESS'
            if event.value == confirma:
                if self._arrastando and not self._moveu:
                    # A click without dragging activates the same placement tool. This
                    # fallback is essential because some Blender versions/themes
                    # retain the UI button's drag event.
                    self._arrastando = False
                    try:
                        context.workspace.status_text_set(
                            "Placement active | Click in viewport: insert | Right click: cancel")
                    except Exception:
                        pass
                    return {'RUNNING_MODAL'}
                if not self._na_viewport(event):
                    return self._cancelar(context)
                # RELEASE can arrive without MOUSEMOVE at the final position.
                if getattr(self, '_sessao_parede', 0):
                    self._mover(context, event)
                if not self._valido:
                    self.report({'WARNING'}, self._erro_posicionamento or "Position inside the viewport")
                    return self._cancelar(context)
                return self._confirmar(context)
        if (event.type in {'RET', 'NUMPAD_ENTER'} and
                event.value == 'PRESS'):
            if not self._valido:
                self.report({'WARNING'}, self._erro_posicionamento or "Position inside the viewport")
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
    """Select a hierarchy level."""
    bl_idname = "object.cabinet_navegar"
    bl_label = "Browse"

    nivel: bpy.props.IntProperty(default=1, min=1)
    valor: bpy.props.StringProperty()

    def execute(self, context):
        s = context.scene
        # Use the hierarchy of the open library: presets or materials.
        prefixo = ('cabinet_mat_n' if getattr(s, 'cabinet_bib_modo', '') == 'MATERIAIS'
                   else 'chapa_n')
        atual = trilha_da_cena(s, prefixo)
        trilha = list(atual[:self.nivel - 1])
        if not (len(atual) >= self.nivel and atual[self.nivel - 1] == self.valor):
            trilha.append(self.valor)       # Same level again = close it.
        definir_trilha(s, trilha, prefixo)
        return {'FINISHED'}


# ======================================= THUMBNAILS AND DIMENSION WIREFRAME
_previews = [None]

# Canvas and template scale are deliberately fixed: widening the sidebar
# must not enlarge the representation. Normalize each proportion to fill
# the usable area without distortion or crossing the inner margins.
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

# Vertices: front (0, 1, 5, 4), back (2, 3, 7, 6), and connections.
_ARESTAS_WIREFRAME = (
    (0, 1), (1, 5), (5, 4), (4, 0),
    (2, 3), (3, 7), (7, 6), (6, 2),
    (0, 2), (1, 3), (5, 7), (4, 6),
)

# Minimal 5x7 font. Indicators are part of the procedural buffer
# and do not depend on installed system fonts.
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
    """Theme text color for contrast in light and dark themes."""
    try:
        cor = context.preferences.themes[0].user_interface.wcol_regular.text
        return tuple(max(0.0, min(1.0, float(v))) for v in cor[:3])
    except Exception:
        return (0.9, 0.9, 0.9)


def _caixas_das_folhas(largura, altura, profundidade, folhas):
    """Leaf vertices on the front face, along box axes.

    DRAWING proportions, not measurements: the preview is schematic. Leaves
    are inset 4% from the edges and project 8% of the depth, making
    the placeholder readable at 160 px."""
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
    """Project at 45 degrees and fit proportions to the usable canvas area.

    `extras` are vertices in the SAME box axes (for example, leaves);
    return them projected after the eight corners so everything uses
    the same scale as the box."""
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
    # Derive bounds from the eight BOX corners: including leaves would
    # change the scale and make the cabinet look smaller than it is.
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
    """Rasterize an antialiased segment only inside its local box."""
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
            # ImagePreview uses a bottom origin; points also use Y up,
            # so this buffer needs no row inversion.
            i = (y * largura + x) * 4
            if cobertura > buffer[i + 3]:
                buffer[i] = cr
                buffer[i + 1] = cg
                buffer[i + 2] = cb
                buffer[i + 3] = cobertura


def _desenhar_indicador(buffer, letra, x, y, cor, escala=2):
    """Draw a 5x7 letter centered at (x, y)."""
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
    """Identify directions without adding dimensions or auxiliary lines.

    'INDIVIDUAL' (panel): L, A, E. The drawing's VERTICAL panel edge
    represents thickness: `_visual_wireframe` (`painel_legado`) passes
    thickness in the height slot; the receding edge is the component height.
    'GRUPO' (panel cabinet): L, A, P, plus E at the lower-right corner.
    Thickness has no dedicated cabinet edge but is still a measurement
    that must be displayed.
    'LIVRE' (object without the add-on signature): only L, A, P.
    Without panels, there is no thickness to display."""
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
        # Lower-right projection corner. Move the letter down into
        # the bottom margin rather than right: the side margin is
        # only a few pixels and `_desenhar_indicador` silently clips it.
        quina = pontos[1]
        _desenhar_indicador(
            buffer, 'E', quina[0] - 8.0, quina[1] - 9.0, cor)


def _rasterizar_wireframe(largura, altura, profundidade, cor, modo='GRUPO',
                         folhas=0, trocado=False):
    """RGBA pixels of the box's 12 edges, plus front leaves."""
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
    """Center VISIBLE content, including the L/A/P/E letters."""
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


# ==================================== SIZE BAR (volume style)
# bpy has no thin-track slider with a round knob: native `slider=True`
# fills the entire bar and writes its value over it. This bar is
# rasterized with the wireframe technique and made clickable by
# assembling SLICES: each slice is an operator button writing its own
# value, so the click reaches the correct slice without guessing
# coordinates (bpy does not report where a button was drawn).
BARRA_PREFIXO = "barra:v2:"
BARRA_PX = 40               # Rasterized slice side length, in pixels.
PX_FATIA_BARRA = 18.0       # Width occupied by the icon when drawn.
PX_BOTAO_BIBLIOTECA = 34.0  # Asset Browser button beside the bar.
BARRA_TRILHO = 0.14         # Track thickness as a fraction of the side length.
BARRA_KNOB = 0.62           # Knob diameter as a fraction of the side length.
AMOSTRAS_BARRA = 4          # Supersampling per pixel (4x4).
COR_BARRA_VAZIA = (0.322, 0.298, 0.290)
COR_BARRA_CHEIA = (1.0, 1.0, 1.0)


def _cobertura_disco(x, y, cx, cy, raio, amostras=AMOSTRAS_BARRA):
    """Fraction of pixel (x, y) covered by the disk, from 0 to 1.

    Manual supersampling: Blender downsamples the icon when drawing,
    and a raw circle becomes a diamond after that reduction."""
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
    """RGBA pixels for ONE slice: track segment + knob if active.

    The track is filled through the active slice and empty afterward,
    giving an immediate indication of how much is enabled."""
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
            # Track: horizontal strip with smoothed edges.
            if dy <= meia_esp - 0.5:
                alfa = 1.0
            elif dy <= meia_esp + 0.5:
                alfa = meia_esp + 0.5 - dy
            # Rounded ends only on the outermost slices.
            if indice == 0 and x < meia_esp:
                alfa = min(alfa, _cobertura_disco(x, y, meia_esp, meio,
                                                  meia_esp))
            if indice == ultimo and x > lado - 1 - meia_esp:
                alfa = min(alfa, _cobertura_disco(
                    x, y, lado - 1 - meia_esp, meio, meia_esp))
            # Knob on top, always white.
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
    """Slice icon_id, reused through the preview cache."""
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
            print("[Archy Builder] bar:", e)
            return 0
    try:
        return colecao[chave].icon_id
    except Exception:
        return 0


def _metrica_barra(context, disponivel=None):
    """(slices, logical cell width, compression) for the bar.

    Keep this in one place because DRAWING and DRAGGING must agree:
    if their cell sizes differ, the knob drifts away from the pointer."""
    prop = bpy.types.Scene.bl_rna.properties["chapa_tam_bloco"]
    fatias = prop.hard_max - prop.hard_min + 1
    if disponivel is None:
        disponivel = max(1.0, PX_FATIA_BARRA * fatias)
    disponivel = max(1.0, disponivel)
    # scale_x shrinks the cell to icon size; above 1.0 it has no effect
    # (the icon does not stretch), so the cell becomes smaller than the target.
    compressao = min(1.0, PX_FATIA_BARRA * fatias / disponivel)
    celula = min(PX_FATIA_BARRA, disponivel / fatias)
    return fatias, celula, compressao


# ====================================== CLICKABLE PHOTO (sliced)
# `template_icon` enlarges the photo but receives NO events, and an operator
# button's icon never exceeds about 16 px regardless of increases to
# scale_x/scale_y (measured). To make the whole photo clickable, split it
# into tiles, each used as a button icon: the mosaic looks like one image
# and any point activates the placement tool.
FOTO_PREFIXO = "foto:v2:"
# Rasterizing at 24 and drawing at 16 forced Blender to resample every
# tile (1.5x), causing banding on smooth faces. Both sizes must
# be EQUAL so drawing is 1:1.
FOTO_TILE_PX = 16
# 16 px is the ACTUAL width at which Blender draws a button icon;
# 18 left a 2 px gap, turning the mosaic into a checkerboard.
PX_TILE_FOTO = 16.0
# CELL target deliberately smaller than the icon: targeting 16 px
# requires an exact tile width, but that width is estimated; any
# deviation opens gaps and fragments the photo. With clearance,
# the cell always remains smaller than the icon at any width.
PX_ALVO_CELULA = 16.0


# Gaps measured from captures: the list box consumes some panel
# width, and each tile has its own inner margin.
PADDING_GRADE = 34.0
PADDING_BLOCO = 12.0


def _metrica_blocos(context, tamanho):
    """(columns, width of each tile) for the preset grid.

    Columns must be EXPLICIT. With `columns=0`, bpy chooses tile width,
    and a clickable photo, made of 16 px icons, is gap-free only when
    that width is known. `ui_units_x` is ignored inside grid_flow
    (measured), while `scale_x` shrinks the icon itself, distorting the image."""
    util = max(1.0, _gaveta._largura_painel(context) - PADDING_GRADE)
    # The photo mosaic has no stripes only when the cell width
    # (tile width / tile count) is close to the icon's 16 px.
    # Overwide tiles make the calculation drift and produce bands;
    # 20 px per size increment keeps the tile in the gap-free range.
    alvo = max(64.0, float(tamanho) * 20.0)
    colunas = max(1, min(6, int(util // alvo)))
    return colunas, util / colunas


def _foto_clicavel_ligada():
    """Preference: clickable photo (mosaic) or perfect photo."""
    p = _opcoes._prefs()
    return bool(p and getattr(p, "foto_clicavel", False))


def _tiles_foto(pasta, png, lado):
    """icon_id for each photo tile in a `lado` x `lado` grid.

    Return rows from TOP to BOTTOM, the UI drawing order; Blender's
    pixels run bottom to top."""
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
                    print("[Archy Builder] photo:", e)
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
        print("[Archy Builder] photo:", e)
        return None


class OBJECT_OT_definir_tamanho(Operator):
    """Library thumbnail size.

    The bar responds to CLICKS, not dragging, and the API cannot fix this:
    bpy does not allow a new widget type. A panel button's UI handler
    consumes PRESS before any keymap, even `head=True` in the "User Interface"
    keymap. Drawn images/icons receive no events; buttons that receive events
    cannot use our custom drawing. Previously tried: PRESS and CLICK_DRAG
    keymaps with a relative modal."""
    bl_idname = "object.cabinet_tamanho"
    bl_label = "Block Size"

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
    """Create or reuse the horizontal icon_id for these dimensions."""
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
            # Populate both because Blender's version chooses the level
            # according to the scale requested by template_icon.
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
            print("[Archy Builder] wireframe:", e)
            return 0
    _registrar_uso_wireframe(chave, colecao)
    return colecao[chave].icon_id


def _chave_preview(pasta, arquivo):
    return os.path.join(pasta, arquivo)


def icone_do_item(it):
    """Preset photo icon_value, or 0 if unavailable."""
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
    """Largest alpha occupancy fraction along X or Y, or zero if empty."""
    imagem = None
    try:
        imagem = bpy.data.images.load(caminho, check_existing=False)
        largura, altura = imagem.size
        if largura <= 0 or altura <= 0:
            return 0.0
        # Blender 4.2 does not accept `step` directly on bpy_prop_array.
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
        print("[Archy Builder] alpha reading:", e)
        return 0.0
    finally:
        if imagem is not None:
            try:
                bpy.data.images.remove(imagem)
            except (ReferenceError, RuntimeError):
                pass


# FACTORY model photos (handles, opening mechanisms, hinges): PNGs bundled
# with the add-on, made by `gerar_fotos_padrao.py` using the same view
# as library photos. They stay outside the library and are protected.
PASTA_FOTOS_PADRAO = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets/previews")


# Models without their own component still show another model's photo,
# as requested by the user; remove these entries when Curva/Super Curva models exist.
FOTOS_PENDENTES = {'dobradica_CURVA': 'dobradica_RETA',
                   'dobradica_SUPER_CURVA': 'dobradica_RETA'}


def foto_padrao(nome):
    """Factory portrait (`puxador_ALCA`, `abertura_GIRO`, etc.) in the
    item format read by sidebar drawing."""
    nome = FOTOS_PENDENTES.get(nome, nome)
    return {'pasta': PASTA_FOTOS_PADRAO, 'arquivo': nome + '.png',
            'foto': nome + '.png'}


# "45-degree" photo, requested by the user: front-right, slightly from
# above; the same view for every handle, door, and hinge model.
VISTA_FOTO = Euler((math.radians(60.0), 0.0, math.radians(45.0)),
                   'XYZ').to_quaternion()


def _arestas_da_foto(obj):
    """Actual edges and corners: coplanar triangles must not become lines in the photo."""
    normais = {}
    for face in obj.data.polygons:
        for chave in face.edge_keys:
            normais.setdefault(tuple(sorted(chave)), []).append(face.normal)
    limite = math.cos(math.radians(20))
    return [e.vertices[:] for e in obj.data.edges
            if len(ns := normais.get(tuple(sorted(e.vertices)), [])) == 1
            or any(a.dot(b) < limite for i, a in enumerate(ns) for b in ns[i+1:])]


def _contornos_da_foto(objetos, raio):
    """Temporary render lines, thick enough to remain readable in thumbnails,
    occluded by the geometry itself rather than drawn through the furniture."""
    dados = bpy.data.curves.new("Preset Photo Outline", 'CURVE')
    dados.dimensions = '3D'
    dados.bevel_depth = raio
    dados.bevel_resolution = 0
    for obj in objetos:
        if obj.type != 'MESH' or obj.hide_render or _chapas.MARCA_CHAPA not in obj:
            continue
        for a, b in _arestas_da_foto(obj):
            linha = dados.splines.new('POLY')
            linha.points.add(1)
            for ponto, indice in zip(linha.points, (a, b)):
                co = obj.matrix_world @ obj.data.vertices[indice].co
                ponto.co = (*co, 1)
    contorno = bpy.data.objects.new("Preset Photo Outline", dados)
    bpy.context.scene.collection.objects.link(contorno)
    contorno.color = (.045, .045, .045, 1)
    return contorno


def fotografar_com_camera(destino_png, objetos, rotacao=VISTA_FOTO, lado=512):
    """Preset photo WITHOUT a window: orthographic camera in photo view,
    solid Workbench render on a transparent background (`capturar_viewport`
    has no viewport in --background; the native cabinet generator runs
    that way). Show only `objetos`; restore everything else afterward."""
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
    dados = bpy.data.cameras.new("Preset Photo")
    camera = bpy.data.objects.new("Preset Photo", dados)
    cena.collection.objects.link(camera)
    contorno = None
    cores = [(o, tuple(o.color)) for o in objetos]
    try:
        for o in escondidos:
            o.hide_render = True
        bpy.context.view_layer.update()
        pontos = [o.matrix_world @ Vector(c) for o in objetos
                  if o.type == 'MESH' and not o.hide_render for c in o.bound_box]
        if not pontos:
            return False, "nothing to photograph"
        centro = sum(pontos, Vector()) / len(pontos)
        rot = rotacao.to_matrix()
        # Frame using the box AS SEEN by the camera (its x/y axes).
        locais = [rot.transposed() @ (p - centro) for p in pontos]
        largura = max(p.x for p in locais) - min(p.x for p in locais)
        altura = max(p.y for p in locais) - min(p.y for p in locais)
        meio = Vector(((max(p.x for p in locais) + min(p.x for p in locais)) / 2,
                       (max(p.y for p in locais) + min(p.y for p in locais)) / 2,
                       0.0))
        profundidade = max(p.z for p in locais) + 1.0
        dados.type = 'ORTHO'
        dados.ortho_scale = max(largura, altura) * 1.12
        contorno = _contornos_da_foto(objetos, dados.ortho_scale * .003)
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
        sombreamento.color_type = 'OBJECT'
        for obj, _cor in cores:
            obj.color = (.55, .55, .55, 1)
        sombreamento.single_color = (0.55, 0.55, 0.55)  # Photo gray.
        sombreamento.show_object_outline = True
        bpy.ops.render.render(write_still=True)
        return os.path.isfile(destino_png), destino_png
    except Exception as e:
        return False, str(e)
    finally:
        if contorno is not None:
            curva = contorno.data
            bpy.data.objects.remove(contorno, do_unlink=True)
            bpy.data.curves.remove(curva)
        for obj, cor in cores:
            obj.color = cor
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


# Factory NATIVE cabinets, requested by the user: add-on panels only,
# box + 5 mm back in a groove, 18 mm panels, WITH A DOOR (straight,
# covering the front). Standard EXTERNAL box dimensions in mm:
# base cabinet with a 720 mm body (countertop about 900 mm with plinth),
# wall cabinet 330 mm deep, full-height tall cabinets and wardrobes. Hinged
# doors: one leaf up to 500 mm wide, two above; wall cabinets also have a lift-up version.
LARGURA_MAX_UMA_FOLHA_MM = 500
ABERTURA_FOTO = 0.0            # Library: all leaves closed.


def preparar_abertura_foto(context, conj):
    """Closed PHOTO pose without changing side, opening, or hardware."""
    for grupo in _portas._portas_do_conjunto(conj):
        for folha in _portas._folhas_portas(grupo):
            _ferragens._definir_abertura(context, folha, ABERTURA_FOTO)
    context.view_layer.update()
# Default native handle = PROFILE, as requested by the user, positioned
# according to fitted kitchen practice: top on base/sink cabinets, bottom
# on wall cabinets, horizontal at hand height on tall cabinets; only wardrobes use vertical.
# Countertop cabinet, requested by the user: OPEN top, two rails.
TOPO_POR_TIPO = {"Base Cabinet": 'TRAVESSAS', "Vanity Cabinet": 'TRAVESSAS'}
PERFIL_POR_TIPO = {"Base Cabinet": 'CIMA', "Vanity Cabinet": 'CIMA', "Wall Cabinet": 'BAIXO',
                   "Tall Cabinet": 'ALTURA', "Wardrobe": 'LADO'}


def _giro(L):
    return ('GIRO', 1 if L <= LARGURA_MAX_UMA_FOLHA_MM else 2)


ARMARIOS_NATIVOS = (
    [("Base Cabinet", L, 720, 550, ("Cabinets", "Kitchen", "Base Cabinets"), _giro(L))
     for L in (300, 400, 450, 500, 600, 800, 900, 1000, 1200)]
    + [("Wall Cabinet", L, 700, 330, ("Cabinets", "Kitchen", "Wall Cabinets"), _giro(L))
       for L in (300, 400, 450, 500, 600, 800, 900, 1000, 1200)]
    + [("Wall Cabinet", L, 700, 330, ("Cabinets", "Kitchen", "Wall Cabinets"),
        ('BASCULANTE', 1)) for L in (400, 450, 500, 600, 800, 900, 1000, 1200)]
    + [("Tall Cabinet", L, 2200, 550, ("Cabinets", "Kitchen", "Tower Cabinets"), _giro(L))
       for L in (600, 700)]
    + [("Wardrobe", L, 2400, 550, ("Cabinets", "Bedroom", "Closets"), _giro(L))
       for L in (450, 500, 600, 800, 900, 1000)]
    + [("Vanity Cabinet", L, 600, 450, ("Cabinets", "Bathroom", "Vanity Cabinets"), _giro(L))
       for L in (400, 500, 600, 800, 1000)]
)


def nome_armario_nativo(tipo, L, A, P, portas=None):
    """"Balcao 2 Portas 800x720x550", "Aereo Basculante 600x700x330" (preset names)."""
    if portas is None:
        variante = ""
    elif portas[0] == 'BASCULANTE':
        variante = " Lift-up"
    else:
        variante = " %d Door%s" % (portas[1], "s" if portas[1] > 1 else "")
    return "%s%s %dx%dx%d" % (tipo, variante, L, A, P)


def gerar_armario_nativo(context, tipo, L, A, P, niveis, portas=None, E=18.0):
    """Build the cabinet with `portas` = ('GIRO', leaf count) or
    ('BASCULANTE', 1), save its .blend to `pasta_biblioteca`, capture a
    headless photo, apply the asset preview, and register it in the index.
    Remove it from the scene again. Return the .blend path."""
    nome = nome_armario_nativo(tipo, L, A, P, portas)
    conj = _modulos.criar_armario(context, nome, L, A, P, E,
                                  topo=TOPO_POR_TIPO.get(tipo, 'TAMPO'))
    if portas is not None:
        grupo = _portas.porta_no_modulo(conj, folhas=portas[1], abertura=portas[0])
        _puxadores.perfis_na_porta(context, grupo, PERFIL_POR_TIPO.get(tipo, 'CIMA'))
    return gravar_modulo_na_biblioteca(context, conj, nome, niveis)


def gravar_modulo_na_biblioteca(context, conj, nome, niveis):
    """Save the scene cabinet as a preset in `pasta_biblioteca`: .blend,
    headless photo (door closed), asset preview, and index. REMOVE the
    cabinet from the scene. Return the .blend path."""
    pecas = [conj] + list(conj.children_recursive)
    colecao = _modulos._colecao_do_modulo(conj)
    if colecao is not None:
        # The ASSET Collection takes the name; move the assembly Collection aside
        # so the saved asset does not become "<name>.001".
        colecao.name = nome + " (assembly)"
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
        # The photo uses the closed pose required throughout the library.
        preparar_abertura_foto(context, conj)
        pecas = [conj, *conj.children_recursive]
        context.view_layer.update()
        ok, msg = fotografar_com_camera(png, pecas)
        if not ok:
            raise RuntimeError("preset photo: " + msg)
        # `aplicar_preview_png` reloads and REWRITES the .blend: with components
        # still in the scene, everything returned as ".001" (open library-suite
        # bug); removing them keeps the file's names clean.
        remover_da_cena()
        ok, msg = aplicar_preview_png(arq, png)
        if not ok:
            raise RuntimeError("preset preview: " + msg)
        registrar_no_indice(pasta_biblioteca(), nome, arq, *niveis, "modulo")
        return arq
    finally:
        remover_da_cena()


def capturar_viewport(destino_png, camera=None, isolar=None, rotacao=None):
    """Model photo from the viewport.

    Use OpenGL rendering, preserving viewport colors. Disable overlays
    to remove the grid, axes, gizmos, and icons. Output a transparent RGBA
    PNG; without an explicit camera, frame the target automatically
    to fill the thumbnail.

    camera -- use its view if supplied. Otherwise preserve an existing
    camera view, or use the current viewport framing.
    isolar -- objects to show. Hide the rest of the scene during capture
    and restore it afterward, so a cabinet in a larger layout appears alone.
    rotacao -- fixed view quaternion (e.g. `VISTA_FOTO`) instead of the
    current viewport orientation."""
    cena = bpy.context.scene
    ant = (cena.render.filepath, cena.render.image_settings.file_format,
           cena.render.image_settings.color_mode,
           cena.render.resolution_x, cena.render.resolution_y,
           cena.render.resolution_percentage, cena.render.film_transparent)
    # The sidebar is also VIEW_3D: capture the actual viewport.
    area = next((a for a in bpy.context.screen.areas if a.type == 'VIEW_3D'
                 and not _gaveta._eh_area_gaveta_bruto(a)), None)
    if area is None:
        return False, "No visible 3D viewport"

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
        # Without a camera, preserve the user's orientation but adjust
        # center and distance so the target fills the thumbnail.

        regiao = next((r for r in area.regions if r.type == 'WINDOW'), None)
        with bpy.context.temp_override(area=area, region=regiao):
            if camera is None and enquadrar:
                # The square capture has a different aspect ratio from the wide
                # viewport. ORTHO preserves the angle and center, avoiding the
                # sideways shift that perspective would produce.
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
                # A small margin avoids clipping antialiasing and very wide/tall
                # objects near the PNG boundary.
                r3d.view_distance *= 1.12
            bpy.ops.render.opengl(write_still=True, view_context=True)
            if camera is None and enquadrar:
                # `view_selected` frames using the viewport aspect ratio, but the PNG
                # is square. Measure actual alpha and make a second pass
                # to occupy the same space at any sidebar width.
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


def _achar_item(pasta, arquivo):
    for it in indice_completo():
        if it["pasta"] == pasta and it["arquivo"] == arquivo:
            return it
    return None


# ========================================== TILE LOCKING AND RENAMING
def _atualizar_item(pasta, arquivo, mudancas):
    itens = _ler_indice(pasta, estrito=True)
    for i in itens:
        if i.get("arquivo") == arquivo:
            i.update(mudancas)
    _gravar_indice(pasta, itens)


def item_bloqueado(it):
    """With one library, locking is per item: there is no longer a
    factory origin that forces locking."""
    return bool(it.get("bloqueado", False))


class OBJECT_OT_alternar_bloqueio(Operator):
    """Lock or unlock editing of this tile."""
    bl_idname = "object.cabinet_bloqueio"
    bl_label = "Lock/Unlock"

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
    """Edit model name, category, and photo."""
    bl_idname = "object.cabinet_editar_modelo"
    bl_label = "Edit Model"
    bl_options = {'REGISTER'}

    pasta: bpy.props.StringProperty()
    arquivo: bpy.props.StringProperty()
    nome: bpy.props.StringProperty(name="Name")
    n1: bpy.props.EnumProperty(name="Category",
                               items=lambda s, c: [(k, k, "") for k in ARVORE.keys()])
    n2: bpy.props.StringProperty(name="Subcategory")
    n3: bpy.props.StringProperty(name="Type")
    mais: bpy.props.StringProperty(
        name="More Levels", description="Levels below Type, separated by /")
    tirar_foto: bpy.props.BoolProperty(
        name="Capture Viewport Photo", default=False,
        description="Save the current 3D viewport framing as the model photo")

    def invoke(self, context, event):
        it = _achar_item(self.pasta, self.arquivo)
        if it:
            self.nome = it.get("nome", "")
            a, b, c = _niveis_de(it)
            try:
                self.n1 = a or "Cabinets"
            except Exception:
                pass
            self.n2, self.n3 = b, c
            self.mais = "/".join(caminho_de(it)[3:])
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        lay = self.layout
        lay.prop(self, "nome")
        lay.prop(self, "n1")
        lay.prop(self, "n2")
        lay.prop(self, "n3")
        lay.prop(self, "mais")
        lay.separator()
        it = _achar_item(self.pasta, self.arquivo)
        icone = icone_do_item(it) if it else 0
        cx = lay.box()
        cx.label(text="Model Photo")
        if icone:
            cx.template_icon(icon_value=icone, scale=6.0)
        else:
            cx.label(text="no photo", icon='IMAGE_DATA')
        cx.prop(self, "tirar_foto")

    def execute(self, context):
        it = _achar_item(self.pasta, self.arquivo)
        if it is None:
            self.report({'ERROR'}, "Preset not found in index")
            return {'CANCELLED'}
        if item_bloqueado(it):
            self.report({'WARNING'}, "Tile locked: unlock the padlock")
            return {'CANCELLED'}

        png = os.path.splitext(self.arquivo)[0] + ".png"
        if self.tirar_foto:
            cam = next((o for o in context.selected_objects if o.type == 'CAMERA'), None)
            alvo = [o for o in context.selected_objects if o.type != 'CAMERA']
            ok, msg = capturar_viewport(os.path.join(self.pasta, png), cam,
                                        isolar=alvo or None)
            if not ok:
                self.report({'WARNING'}, "Photo failed: " + msg)
            else:
                chave = _chave_preview(self.pasta, png)
                col = _colecao_previews()
                if chave in col:
                    del col[chave]

        itens = _ler_indice(self.pasta, estrito=True)
        for i in itens:
            if i.get("arquivo") == self.arquivo:
                i["nome"] = self.nome
                i["n1"] = self.n1
                i["n2"] = self.n2
                i["n3"] = self.n3
                trilha = [n for n in (self.n1, self.n2, self.n3) if n]
                trilha += [n for n in self.mais.split("/") if n.strip()]
                if len(trilha) > 3:
                    i["niveis"] = trilha
                else:
                    i.pop("niveis", None)
                i.pop("categoria", None)
                i.pop("subcategoria", None)
                i["foto"] = png
        _gravar_indice(self.pasta, itens)
        self.report({'INFO'}, "Model updated")
        return {'FINISHED'}


class OBJECT_OT_salvar_biblioteca(Operator):
    """Save selection to Blender's asset library."""
    bl_idname = "object.cabinet_salvar_biblioteca"
    bl_label = "Save to Library"
    bl_options = {'REGISTER'}

    nome: bpy.props.StringProperty(name="Preset Name", default="Preset")
    n1: bpy.props.EnumProperty(name="Category",
                               items=lambda s, c: [(k, k, "") for k in ARVORE.keys()])
    n2: bpy.props.StringProperty(name="Subcategory", default="")
    n3: bpy.props.StringProperty(name="Type", default="")
    mais: bpy.props.StringProperty(
        name="More Levels", default="",
        description="Levels below Type, separated by / (unlimited)")
    como_modulo: bpy.props.BoolProperty(
        name="As Cabinet (Multiple Components)", default=True,
        description="On: save as a Collection (drag the entire assembly). Off: save each panel as a separate object")

    def invoke(self, context, event):
        sel = [o for o in context.selected_objects]
        if len(sel) == 1 and sel[0].type == 'MESH':
            self.como_modulo = False
            self.nome = sel[0].name
        elif sel:
            self.nome = "Cabinet"
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        sel = [o for o in context.selected_objects]
        if not sel:
            self.report({'WARNING'}, "Nothing selected")
            return {'CANCELLED'}
        # Include children of selected assembly Empties.
        completos = list(sel)
        for o in sel:
            if _chapas.MARCA_CONJUNTO in o:
                completos += [f for f in bpy.data.objects if f.parent == o]
        completos = list(dict.fromkeys(completos))
        # Resolve levels BEFORE saving: they determine the catalog
        # in which the asset will be filed.
        n2 = self.n2 or (_filhos_n2(self.n1) or [""])[0]
        n3 = self.n3 or (_filhos_n3(self.n1, n2) or [""])[0]
        niveis = [self.n1, n2, n3] + [n for n in self.mais.split("/") if n.strip()]
        try:
            arq = salvar_na_biblioteca(completos, self.nome, self.como_modulo,
                                       niveis=niveis)
            png = os.path.splitext(os.path.basename(arq))[0] + ".png"
            # Every preset must have a visual representation from creation.
            # This is not a user preference and cannot be disabled in the dialog.
            cam = next((o for o in sel if o.type == 'CAMERA'), None)
            alvo = [o for o in completos if o.type != 'CAMERA']
            okf, msg = capturar_viewport(
                os.path.join(pasta_biblioteca(), png), cam,
                isolar=alvo or None)
            if not okf:
                self.report({'ERROR'}, "Required photo failed: " + msg)
                return {'CANCELLED'}
            # The same photo becomes the asset preview inside the .blend.
            okp, msgp = aplicar_preview_png(
                arq, os.path.join(pasta_biblioteca(), png))
            if not okp:
                print("[Archy Builder] asset preview:", msgp)
            registrar_no_indice(pasta_biblioteca(), self.nome, arq, *niveis,
                                "modulo" if self.como_modulo else "objeto")
        except Exception as e:
            self.report({'ERROR'}, "Failed to save: %s" % e)
            return {'CANCELLED'}
        self.report({'INFO'}, "Saved to %s" % arq)
        return {'FINISHED'}


# Fraction of viewport height left for the viewport when opening
# the library beneath it.
FRACAO_ASSET_BROWSER = 0.35


def _apontar_asset_browser():
    """Point the newly opened Asset Browser at the add-on library.

    Defer because SpaceFileBrowser `params` exists only after the area's
    first draw. Reread areas from window_manager on every call: retaining
    a reference risks a dead pointer if the area closes first."""
    try:
        for janela in bpy.context.window_manager.windows:
            for area in janela.screen.areas:
                if area.type != 'FILE_BROWSER':
                    continue
                params = getattr(area.spaces.active, "params", None)
                if params is None:
                    continue
                # Change only browsers still at the default "All
                # Libraries": do not hijack a browser the user has already
                # pointed at another library.
                atual = getattr(params, "asset_library_reference", "")
                if atual in ("", "ALL"):
                    try:
                        params.asset_library_reference = NOME_BIBLIOTECA
                    except Exception as e:
                        print("[Archy Builder] library:", e)
                area.tag_redraw()
    except Exception as e:
        print("[Archy Builder] asset browser:", e)
    return None


def _area_asset_browser(tela):
    for area in tela.areas:
        if area.type == 'FILE_BROWSER' and area.ui_type == 'ASSETS':
            return area
    return None


class OBJECT_OT_abrir_asset_browser(Operator):
    """Open Blender's library below the viewport; click again
    to close it."""
    bl_idname = "object.cabinet_asset_browser"
    bl_label = "Open in Asset Browser"

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        registrar_bibliotecas()
        tela = context.window.screen

        # Already open: the same button closes it.
        aberto = _area_asset_browser(tela)
        if aberto is not None:
            alvo = next((r for r in aberto.regions if r.type == 'WINDOW'),
                        None)
            try:
                with context.temp_override(area=aberto, region=alvo):
                    bpy.ops.screen.area_close()
                return {'FINISHED'}
            except Exception as e:
                print("[Archy Builder] close browser:", e)
                self.report({'WARNING'}, "Close the area manually")
                return {'CANCELLED'}

        # A new WINDOW is unsuitable: `Window.width/height` are read-only,
        # and no operator accepts a size, so it would open almost
        # fullscreen and hide the work. Splitting the viewport provides
        # a small area while keeping the model visible.
        area = context.area
        janela = next((r for r in area.regions if r.type == 'WINDOW'), None)
        antes = {a.as_pointer() for a in tela.areas}
        try:
            with context.temp_override(area=area, region=janela):
                bpy.ops.screen.area_split(direction='HORIZONTAL',
                                          factor=FRACAO_ASSET_BROWSER)
        except Exception as e:
            print("[Archy Builder] split area:", e)
            self.report({'WARNING'}, "Could not open the library")
            return {'CANCELLED'}

        nova = next((a for a in tela.areas if a.as_pointer() not in antes),
                    None)
        if nova is None:
            self.report({'WARNING'}, "Could not open the library")
            return {'CANCELLED'}
        try:
            nova.type = 'FILE_BROWSER'
            nova.ui_type = 'ASSETS'
        except Exception as e:
            print("[Archy Builder] asset browser:", e)
            self.report({'WARNING'}, "Switch the editor to Asset Browser")
            return {'CANCELLED'}
        # params exists only after the area's first draw.
        bpy.app.timers.register(_apontar_asset_browser, first_interval=0.2)
        return {'FINISHED'}


class OBJECT_OT_abrir_pasta_biblioteca(Operator):
    """Show the library path in Explorer."""
    bl_idname = "object.cabinet_abrir_biblioteca"
    bl_label = "Open Library Folder"

    def execute(self, context):
        destino = pasta_biblioteca()
        bpy.ops.wm.path_open(filepath=destino)
        self.report({'INFO'}, destino)
        return {'FINISHED'}


# ========================================== ASSET SHELF
# True drag-and-drop, the SAME behavior as Blender's Asset Browser,
# exists only in native editors. `UILayout` exposes nothing to
# initiate dragging, and `template_asset_view`, formerly used by panels
# for that purpose, was removed in 5.x along with
# `bpy.types.AssetHandle`. Thus the sidebar grid cannot initiate
# native dragging due to the API design.
#
# AssetShelf, however, CAN be registered in Python and lives inside
# the viewport. Native dragging is ENABLED by default: Blender's
# brushes request 'NO_ASSET_DRAG' to disable it. With no such request,
# the item is draggable and drops into the viewport's native dropbox,
# exactly like the Asset Browser. The "Assets" button that showed it
# was retired at the user's request in version 330; it remains
# available from Blender's View menu.


class VIEW3D_AST_archy_builder(bpy.types.AssetShelf):
    """Preset shelf: drag a cabinet directly into the scene."""
    bl_idname = "VIEW3D_AST_archy_builder"
    bl_space_type = 'VIEW_3D'
    bl_options = {'STORE_ENABLED_CATALOGS_IN_PREFERENCES'}
    bl_default_preview_size = 96
    # Allowlist: only items suitable for dropping into the scene.
    filter_object = True
    filter_group = True

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and not _gaveta._eh_area_gaveta(context)

    @classmethod
    def asset_poll(cls, asset):
        return asset.id_type in {'OBJECT', 'COLLECTION'}


class OBJECT_OT_registrar_bibliotecas(Operator):
    """Register the library folder as an asset library."""
    bl_idname = "object.cabinet_registrar_bibliotecas"
    bl_label = "Register Libraries in Blender"

    def execute(self, context):
        novas = registrar_bibliotecas(silencioso=False)
        if novas:
            self.report({'INFO'}, "Registered: " + ", ".join(novas))
        else:
            self.report({'INFO'}, "Libraries were already registered")
        return {'FINISHED'}
