"""Library materials (MDF/MDP): hierarchical SOLID COLOR catalog,
applied to panels as Blender Materials with color only, as requested
by the user: no textures yet; color appears in the Solid viewport.
The preview is a shaded sphere like Blender's material preview,
rasterized here without rendering or photo files."""

import bpy, json, os, time
from bpy.props import StringProperty, FloatVectorProperty, EnumProperty, BoolProperty
from bpy.types import Operator, Menu

# Used only at RUNTIME (circular imports): __init__ wires these
# aliases after loading all modules (`_ligar_modulos`).
_biblioteca = _chapas = _ferragens = _perguntas = _gaveta = _portas = None
_orcamento = None
_gavetas = None
_prateleiras = None
_divisorias = None

# First sphere click: (key, timestamp, mouse_x, mouse_y). A single click
# does NOT apply color, as requested by the user: a misplaced click could
# change unintended objects. Only a quick second click at the same position applies it.
_clique_esfera = [None]

NOME_ARQUIVO = "materiais.json"
# Blender Material ID property: catalog item key. Use it to find
# the material when reapplying or editing, never its name,
# which Blender may suffix with .001.
CHAVE_MATERIAL = "cabinet_material"

# Factory hierarchy: level 1 = MDF/MDP, as requested by the user;
# lower levels also derive from file items, like the library.
ARVORE_MATERIAIS = {
    "MDF": {"Solid Colors": [], "Woodgrains": []},
    "MDP": {"Solid Colors": [], "Woodgrains": []},
}

# Initial catalog, used until the library has `materiais.json`
# (created on the first edit). Color = hexadecimal sRGB, as read
# in a supplier catalog.
MATERIAIS_PADRAO = (
    ("MDF", "Solid Colors", "White TX", "#EDEDE8"),
    ("MDF", "Solid Colors", "Snow White", "#F7F7F4"),
    ("MDF", "Solid Colors", "Black TX", "#222222"),
    ("MDF", "Solid Colors", "Crystal Gray", "#B4B6B3"),
    ("MDF", "Solid Colors", "Graphite", "#4B4D50"),
    ("MDF", "Solid Colors", "Sand", "#D9CDB8"),
    ("MDF", "Solid Colors", "Fendi", "#C3B7A6"),
    ("MDF", "Woodgrains", "Freijo", "#A97C50"),
    ("MDF", "Woodgrains", "Oak", "#BC9567"),
    ("MDF", "Woodgrains", "Walnut", "#6F4C35"),
    ("MDF", "Woodgrains", "Louro Preto", "#5B4334"),
    ("MDF", "Woodgrains", "Cumaru", "#8E5B3D"),
    ("MDP", "Solid Colors", "White TX", "#EDEDE8"),
    ("MDP", "Solid Colors", "Black TX", "#222222"),
    ("MDP", "Solid Colors", "Crystal Gray", "#B4B6B3"),
    ("MDP", "Solid Colors", "Graphite", "#4B4D50"),
    ("MDP", "Woodgrains", "Freijo", "#A97C50"),
    ("MDP", "Woodgrains", "Oak", "#BC9567"),
    ("MDP", "Woodgrains", "Walnut", "#6F4C35"),
)

_cache = [None]          # (path, mtime, items): the sidebar reads on every redraw.
_texturas_esfera = {}    # Hex color -> sphere GPUTexture.
_apagar_pendente = [None]  # Key awaiting "Delete?" in the black box.


# ------------------------------------------------------------- catalog
def chave_de(it):
    return "/".join((it.get("n1", ""), it.get("n2", ""), it.get("n3", ""),
                     it.get("nome", "")))


def _completar(it):
    it = dict(it)
    for nivel in ("n1", "n2", "n3"):
        it.setdefault(nivel, "")
    it["cor"] = _hexa_valido(it.get("cor", "")) or "#808080"
    it["chave"] = chave_de(it)
    return it


def _padrao():
    return [_completar({"n1": a, "n2": b, "n3": "", "nome": nome, "cor": cor})
            for a, b, nome, cor in MATERIAIS_PADRAO]


def caminho_arquivo():
    return os.path.join(_biblioteca.pasta_biblioteca(), NOME_ARQUIVO)


def ler_materiais(estrito=False):
    """Catalog items (dicts with n1/n2/n3/nome/cor/chave). Without a library
    file, use the factory catalog. `estrito` (for rewriting): raise for
    an unreadable file instead of substituting the factory catalog."""
    caminho = caminho_arquivo()
    try:
        mtime = os.path.getmtime(caminho)
    except OSError:
        return _padrao()
    guardado = _cache[0]
    if guardado is not None and guardado[:2] == (caminho, mtime):
        return [dict(it) for it in guardado[2]]
    try:
        with open(caminho, encoding="utf-8") as f:
            itens = [_completar(it) for it in json.load(f)
                     if isinstance(it, dict) and it.get("nome") and it.get("n1")]
    except Exception as e:
        if estrito:
            raise
        print("[Archy Builder] unreadable materials:", e)
        return _padrao()
    _cache[0] = (caminho, mtime, itens)
    return [dict(it) for it in itens]


def _itens_para_gravar(op):
    """None with a warning if the file exists but is unreadable:
    overwriting it would replace the user's catalog with the factory catalog."""
    try:
        return ler_materiais(estrito=True)
    except Exception as e:
        op.report({'ERROR'}, "%s unreadable: %s" % (NOME_ARQUIVO, e))
        return None


def gravar_materiais(itens):
    """Write the entire catalog atomically, only if changed."""
    limpos = [{"nome": it["nome"], "n1": it["n1"], "n2": it.get("n2", ""),
               "n3": it.get("n3", ""), "cor": it["cor"]} for it in itens]
    texto = json.dumps(limpos, ensure_ascii=False, indent=1) + "\n"
    _biblioteca._gravar_se_mudou(caminho_arquivo(), texto)
    _cache[0] = None


def achar(chave, itens=None):
    return next((it for it in (itens if itens is not None else ler_materiais())
                 if it["chave"] == chave), None)


def _niveis_extra(itens):
    extra = {}
    for it in itens:
        ramo = extra.setdefault(it["n1"], {})
        if it["n2"]:
            filhos = ramo.setdefault(it["n2"], [])
            if it["n3"] and it["n3"] not in filhos:
                filhos.append(it["n3"])
    return extra


def filhos_n1(itens):
    return list(dict.fromkeys(list(ARVORE_MATERIAIS) + list(_niveis_extra(itens))))


def filhos_n2(itens, n1):
    return list(dict.fromkeys(list(ARVORE_MATERIAIS.get(n1, {}))
                              + list(_niveis_extra(itens).get(n1, {}))))


def filhos_n3(itens, n1, n2):
    return list(dict.fromkeys(list(ARVORE_MATERIAIS.get(n1, {}).get(n2, []))
                              + _niveis_extra(itens).get(n1, {}).get(n2, [])))


# ------------------------------------------------------------------ color
def _hexa_valido(texto):
    texto = (texto or "").strip().lstrip("#")
    if len(texto) != 6:
        return ""
    try:
        int(texto, 16)
    except ValueError:
        return ""
    return "#" + texto.upper()


def rgb_de(hexa):
    """sRGB 0..1 from '#RRGGBB'."""
    hexa = _hexa_valido(hexa) or "#808080"
    return tuple(int(hexa[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


def hexa_de(rgb):
    return "#" + "".join("%02X" % max(0, min(255, round(c * 255))) for c in rgb[:3])


def _linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_linear(hexa):
    """The Material stores LINEAR color; the catalog stores sRGB."""
    return tuple(_linear(c) for c in rgb_de(hexa))


# ------------------------------------------------------ scene material
def material_da_chave(chave):
    return next((m for m in bpy.data.materials
                 if m.get(CHAVE_MATERIAL) == chave), None)


def nome_do_material(it):
    return "%s %s" % (it["n1"], it["nome"])


def garantir_material(it):
    """The item's Blender Material: solid color only, both viewport Solid
    (`diffuse_color`) and Principled (Material Preview and rendering).
    If it exists, update only its name and color from the catalog."""
    mat = material_da_chave(it["chave"])
    nome = nome_do_material(it)
    if mat is None:
        mat = bpy.data.materials.new(nome)
        mat[CHAVE_MATERIAL] = it["chave"]
    elif mat.name != nome and not mat.name.startswith(nome + "."):
        # Only the .001 suffix is tolerated: "Branco TX" -> "Branco" renames it.
        mat.name = nome
    cor = (*rgb_linear(it["cor"]), 1.0)
    mat.diffuse_color = cor
    if mat.node_tree is None:
        try:
            mat.use_nodes = True        # 4.x; in 5.x it is created with nodes already enabled.
        except Exception:
            pass
    arvore = mat.node_tree
    if arvore is not None:
        for no in arvore.nodes:
            if no.type == 'BSDF_PRINCIPLED':
                no.inputs['Base Color'].default_value = cor
    return mat


def protegida_no_grupo(obj):
    """The marker may be on the accessory Empty, not its child mesh."""
    while obj is not None:
        if (any(m in obj for m in (_chapas.MARCA_PUXADOR,_chapas.MARCA_ACESSORIO,
                                  _ferragens.CHAVE_FERRAGEM))
                or obj.get(_gavetas.MARCA_PECA)=='TRILHO'):
            return True
        obj=obj.parent
    return False


def _eh_peca(obj):
    """Mesh eligible for material: panel, leaf, frame, or ordinary object;
    never a handle, accessory, or hardware, which have their own materials."""
    return obj.type=='MESH' and not protegida_no_grupo(obj)


def _pintando_grupo(context):
    marcas=(_chapas.MARCA_CONJUNTO,_chapas.MARCA_PORTAS,_gavetas.MARCA_GRUPO,
            _gavetas.MARCA_GAVETA,_prateleiras.MARCA_GRUPO,_divisorias.MARCA_GRUPO)
    return any(o.type=='EMPTY' and any(m in o for m in marcas) for o in context.selected_objects)


class _LayoutVinculos:
    """Reuse the native menu, replacing only the group's material action."""
    def __init__(self,layout):object.__setattr__(self,'_layout',layout)
    def __getattr__(self,nome):return getattr(self._layout,nome)
    def __setattr__(self,nome,valor):setattr(self._layout,nome,valor)

    def operator_enum(self,operador,propriedade,**opcoes):
        if (operador,propriedade)!=('object.make_links_data','type'):
            return self._layout.operator_enum(operador,propriedade,**opcoes)
        for item in bpy.ops.object.make_links_data.get_rna_type().properties['type'].enum_items:
            if not item.identifier:
                self._layout.separator();continue
            if item.identifier=='MATERIAL':
                self._layout.operator(OBJECT_OT_vincular_materiais.bl_idname,
                    text="Link Materials",icon_value=item.icon)
            else:
                self._layout.operator(operador,text=item.name,icon_value=item.icon).type=item.identifier


class _MenuVinculos:
    def __init__(self,menu):
        self._menu=menu;self.layout=_LayoutVinculos(menu.layout)
    def __getattr__(self,nome):return getattr(self._menu,nome)


class VIEW3D_MT_vinculos(Menu):
    bl_idname='VIEW3D_MT_cabinet_vinculos'
    bl_label="Link/Transfer Data"

    def draw(self,context):
        menu=_MenuVinculos(self) if _pintando_grupo(context) else self
        bpy.types.VIEW3D_MT_make_links.draw(menu,context)


class OBJECT_OT_vincular_materiais(Operator):
    bl_idname='object.cabinet_vincular_materiais'
    bl_label="Link Materials"
    bl_description="Link materials while preserving the group's handles and hardware"
    bl_options={'REGISTER','UNDO'}

    @classmethod
    def poll(cls,context):
        return context.mode=='OBJECT' and bpy.ops.object.make_links_data.poll()

    def execute(self,context):
        if not _pintando_grupo(context):
            return bpy.ops.object.make_links_data(type='MATERIAL')
        # Filtered context preserves selection for G, H, Delete, and duplication.
        alvos=[o for o in context.selected_editable_objects
               if o==context.active_object or not protegida_no_grupo(o)]
        with context.temp_override(selected_objects=alvos,selected_editable_objects=alvos):
            return bpy.ops.object.make_links_data(type='MATERIAL')


def pecas_dos_alvos(objs):
    """Components painted by a material, following selection rules: CABINET =
    its panels (the door is a separate item); DOOR = leaves and frame;
    separate component or leaf (double click) = only that component."""
    pecas = []
    for obj in objs:
        if (_gavetas.MARCA_GRUPO in obj or _gavetas.MARCA_GAVETA in obj
                or _prateleiras.MARCA_GRUPO in obj):
            # Drawers: fronts and boxes (rails have their own material).
            pecas += [f for f in obj.children_recursive
                      if _chapas.MARCA_CHAPA in f and _eh_peca(f)]
        elif _chapas.MARCA_CONJUNTO in obj:
            pecas += [f for f in obj.children_recursive
                      if _chapas.MARCA_CHAPA in f and _eh_peca(f)]
        elif _chapas.MARCA_PORTAS in obj:
            pecas += [f for f in obj.children
                      if (_chapas.MARCA_FOLHA in f or _chapas.MARCA_MOLDURA in f)
                      and _eh_peca(f)]
        elif _eh_peca(obj):
            pecas.append(obj)
    return list(dict.fromkeys(pecas))


def pecas_do_solte(obj, selecionados):
    """Components painted when the sphere is DROPPED onto `obj`. If `obj`
    is selected, use the selection (double clicking already isolated a
    component if needed); otherwise use what clicking `obj` would select:
    the cabinet, whole door, or separate component."""
    if obj.select_get():
        return pecas_dos_alvos(selecionados)
    dono = (_portas._grupo_portas(obj) or _portas._modulo_da_chapa(obj)
            or obj)
    return pecas_dos_alvos([dono])


def duplo_clique_na_esfera(chave, x, y, limite_ms, agora=None):
    """True if this PRESS completes a quick double click at the same position
    on sphere `chave`; otherwise store it as the first click. Use the clock,
    like photos: the sidebar receives the second click as PRESS, not DOUBLE_CLICK."""
    agora = time.monotonic() if agora is None else agora
    raio = _biblioteca.RAIO_DUPLO_CLIQUE_PX
    anterior = _clique_esfera[0]
    duplo = (anterior is not None and anterior[0] == chave
             and (agora - anterior[1]) * 1000.0 <= limite_ms
             and (x - anterior[2]) ** 2 + (y - anterior[3]) ** 2 <= raio ** 2)
    _clique_esfera[0] = None if duplo else (chave, agora, x, y)
    return duplo


def aplicar(pecas, mat):
    """Material in the OBJECT slot (`link='OBJECT'`): survives mesh rebuilding
    (door, frame) and does not paint objects sharing that mesh."""
    for obj in pecas:
        if not obj.material_slots:
            obj.data.materials.append(None)
        for slot in obj.material_slots:
            slot.link = 'OBJECT'
            slot.material = mat


def chave_aplicada(obj):
    """Catalog material key on the component, or the group's first item."""
    pecas = pecas_dos_alvos([obj]) if obj is not None else []
    for peca in pecas[:1]:
        for slot in peca.material_slots:
            if slot.material is not None:
                return slot.material.get(CHAVE_MATERIAL, "")
    return ""


# ------------------------------------------------------- sphere (preview)
LADO_ESFERA = 96
LUZ_ESFERA = (-0.45, 0.55, 0.70)    # From the upper left, like Blender's.


def esfera_rgba(rgb, lado=LADO_ESFERA):
    """RGBA pixels (float, row 0 at the bottom) for a sphere of color `rgb`
    (sRGB): diffuse + ambient + specular, smoothed edges. Transparent
    background to sit on the theme square."""
    import numpy as np
    eixo = (np.arange(lado, dtype=np.float32) + 0.5) / lado * 2.0 - 1.0
    x, y = np.meshgrid(eixo, eixo)
    raio = 0.94
    nx, ny = x / raio, y / raio
    r2 = nx * nx + ny * ny
    nz = np.sqrt(np.clip(1.0 - r2, 0.0, 1.0))
    luz = np.array(LUZ_ESFERA, dtype=np.float32)
    luz /= np.linalg.norm(luz)
    meio = luz + np.array((0.0, 0.0, 1.0), dtype=np.float32)
    meio /= np.linalg.norm(meio)
    difusa = np.clip(nx * luz[0] + ny * luz[1] + nz * luz[2], 0.0, 1.0)
    brilho = np.clip(nx * meio[0] + ny * meio[1] + nz * meio[2], 0.0, 1.0) ** 40
    tom = 0.30 + 0.70 * difusa
    saida = np.zeros((lado, lado, 4), dtype=np.float32)
    for i in range(3):
        saida[:, :, i] = np.clip(rgb[i] * tom + 0.30 * brilho, 0.0, 1.0)
    # Coverage from distance (px) to the outline: antialiased edge.
    borda = (1.0 - np.sqrt(r2)) * raio * lado / 2.0
    saida[:, :, 3] = np.clip(borda + 0.5, 0.0, 1.0)
    return saida.ravel()


def desenhar_esfera(hexa, x, y, w, h):
    """Material sphere in sidebar rectangle (x, y, w, h)."""
    import gpu
    from gpu_extras.batch import batch_for_shader
    textura = _texturas_esfera.get(hexa)
    if textura is None:
        pixels = esfera_rgba(rgb_de(hexa))
        dados = gpu.types.Buffer('FLOAT', len(pixels), pixels)
        textura = gpu.types.GPUTexture((LADO_ESFERA, LADO_ESFERA),
                                       format='RGBA32F', data=dados)
        _texturas_esfera[hexa] = textura
    lado = min(w, h) * 0.86
    x, y = x + (w - lado) / 2, y + (h - lado) / 2
    shader = gpu.shader.from_builtin('IMAGE')
    batch = batch_for_shader(shader, 'TRIS', {
        'pos': ((x, y), (x + lado, y), (x + lado, y + lado),
                (x, y), (x + lado, y + lado), (x, y + lado)),
        'texCoord': ((0, 0), (1, 0), (1, 1), (0, 0), (1, 1), (0, 1))})
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_sampler('image', textura)
    batch.draw(shader)


# ------------------------------------------------------------ operators
class OBJECT_OT_aplicar_material(Operator):
    """Apply the material to selection: cabinet = its panels, door =
    leaves and frame, component = only itself."""
    bl_idname = "object.cabinet_aplicar_material"
    bl_label = "Apply Material"
    bl_options = {'REGISTER', 'UNDO'}

    chave: StringProperty(options={'SKIP_SAVE'})
    # Name of the object onto which the sphere was DROPPED (empty = selection).
    alvo: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        it = achar(self.chave)
        if it is None:
            self.report({'ERROR'}, "Material not found: %s" % self.chave)
            return {'CANCELLED'}
        if self.alvo:
            obj = bpy.data.objects.get(self.alvo)
            pecas = (pecas_do_solte(obj, context.selected_objects)
                     if obj is not None else [])
            aviso = "Drop the material onto a cabinet, door, or component"
        else:
            pecas = pecas_dos_alvos(context.selected_objects)
            aviso = "Select a cabinet, door, or component to apply the material"
        if not pecas:
            self.report({'WARNING'}, aviso)
            return {'CANCELLED'}
        aplicar(pecas, garantir_material(it))
        self.report({'INFO'}, "%s on %d component(s)" % (nome_do_material(it), len(pecas)))
        return {'FINISHED'}


def _itens_n1(self, context):
    return [(k, k, "") for k in filhos_n1(ler_materiais())]


class _CamposMaterial:
    nome: StringProperty(name="Name", default="New Material")
    cor: FloatVectorProperty(name="Color", subtype='COLOR_GAMMA', size=3,
                             min=0.0, max=1.0, default=(0.8, 0.8, 0.8))
    n1: EnumProperty(name="Material", items=_itens_n1)
    n2: StringProperty(name="Category", default="Solid Colors")
    n3: StringProperty(name="Subcategory", default="")

    def draw(self, context):
        for campo in ("nome", "cor", "n1", "n2", "n3"):
            self.layout.prop(self, campo)

    def _item(self):
        return _completar({"nome": self.nome.strip(), "n1": self.n1,
                           "n2": self.n2.strip(), "n3": self.n3.strip(),
                           "cor": hexa_de(self.cor)})


class OBJECT_OT_novo_material(_CamposMaterial, Operator):
    """Add a material (solid color) to the library."""
    bl_idname = "object.cabinet_novo_material"
    bl_label = "New Material"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        s = context.scene
        # Start in the category currently open in the hierarchy.
        if s.cabinet_mat_n1 in filhos_n1(ler_materiais()):
            self.n1 = s.cabinet_mat_n1
        self.n2 = s.cabinet_mat_n2 or self.n2
        self.n3 = s.cabinet_mat_n3
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        novo = self._item()
        if not novo["nome"]:
            self.report({'ERROR'}, "Material has no name")
            return {'CANCELLED'}
        itens = _itens_para_gravar(self)
        if itens is None:
            return {'CANCELLED'}
        if achar(novo["chave"], itens) is not None:
            self.report({'ERROR'}, "%s already exists in this category" % novo["nome"])
            return {'CANCELLED'}
        gravar_materiais(itens + [novo])
        self.report({'INFO'}, "Material %s created" % nome_do_material(novo))
        return {'FINISHED'}


class OBJECT_OT_editar_material(_CamposMaterial, Operator):
    """Change a library material's name, color, or category; already
    applied Materials follow the changes."""
    bl_idname = "object.cabinet_editar_material"
    bl_label = "Edit Material"
    bl_options = {'REGISTER', 'UNDO'}

    chave: StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        it = achar(self.chave)
        if it is None:
            self.report({'ERROR'}, "Material not found")
            return {'CANCELLED'}
        self.nome, self.cor = it["nome"], rgb_de(it["cor"])
        self.n1, self.n2, self.n3 = it["n1"], it["n2"], it["n3"]
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        itens = _itens_para_gravar(self)
        if itens is None:
            return {'CANCELLED'}
        antigo = achar(self.chave, itens)
        novo = self._item()
        if antigo is None or not novo["nome"]:
            self.report({'ERROR'}, "Material not found")
            return {'CANCELLED'}
        if novo["chave"] != antigo["chave"] and achar(novo["chave"], itens):
            self.report({'ERROR'}, "%s already exists in this category" % novo["nome"])
            return {'CANCELLED'}
        gravar_materiais([novo if it["chave"] == antigo["chave"] else it
                          for it in itens])
        mat = material_da_chave(antigo["chave"])
        if mat is not None:
            mat[CHAVE_MATERIAL] = novo["chave"]
            garantir_material(novo)
        return {'FINISHED'}


class OBJECT_OT_apagar_material(Operator):
    """Remove a material from the library, preserving painted components."""
    bl_idname = "object.cabinet_apagar_material"
    bl_label = "Delete Material"
    bl_options = {'REGISTER', 'INTERNAL'}

    chave: StringProperty(options={'SKIP_SAVE'})
    apagar: BoolProperty(default=True, options={'SKIP_SAVE'})

    def execute(self, context):
        _apagar_pendente[0] = None
        if not self.apagar:
            return {'CANCELLED'}
        itens = _itens_para_gravar(self)
        if itens is None or achar(self.chave, itens) is None:
            return {'CANCELLED'}
        gravar_materiais([it for it in itens if it["chave"] != self.chave])
        return {'FINISHED'}


def perguntar_apagar(context, it):
    """"Delete?" in the black box directly below the material in the sidebar."""
    _apagar_pendente[0] = it["chave"]
    _pintar_pendente[0] = None
    op = OBJECT_OT_apagar_material.bl_idname
    _perguntas._perguntar(context, "Delete material %s?" % nome_do_material(it),
                          [("Yes, Delete", 'TRASH', op,
                            {"chave": it["chave"], "apagar": True}),
                           ("No", 'X', op, {"chave": it["chave"], "apagar": False})],
                          na_gaveta=True)
    # Create the box in the LIBRARY below the material, not the upper tab.
    _perguntas._pergunta_atual[0]['biblioteca'] = True
    _gaveta._rolar_biblioteca_ate_pergunta(context)


# ------------------------------------------------------ quick painting
# User request: hover over a library material and RIGHT click
# to paint WHOLE cabinets by their room (Kitchen, Bedroom, etc.);
# a second question chooses everything, box only, or doors only.
# Questions appear in the black box directly below the material:
# sidebar questions stay in the sidebar, never a popup.
_pintar_pendente = [None]   # Material key with "Paint?" open.
TODOS = '@todos'
CANCELAR = '@cancelar'
PARTES_PINTURA = (('TUDO', "Everything"), ('CAIXA', "Box Only"),
                  ('PORTAS', "Doors Only"))
SEM_COMODO = "No Room"


def chave_da_caixa():
    """Material under which the black box opens (delete or paint)."""
    return _apagar_pendente[0] or _pintar_pendente[0]


def modulos_por_comodo(cena):
    """{room name ('' = no room): [cabinets]} for the scene."""
    grupos = {}
    for conj in cena.objects:
        if _chapas.MARCA_CONJUNTO not in conj:
            continue
        pasta = _orcamento._comodo_do_modulo(conj)
        grupos.setdefault(_orcamento._nome_comodo(pasta) if pasta else '', []).append(conj)
    return grupos


def pecas_do_modulo(conj, parte):
    """Components painted by quick painting: 'CAIXA' = body panels
    (sides, base, top, back, shelves); 'PORTAS' = its door leaves
    and frames; 'TUDO' = both."""
    portas = _portas._portas_do_conjunto(conj)
    pecas = []
    if parte in ('TUDO', 'CAIXA'):
        dentro_de_porta = {o for g in portas for o in g.children_recursive}
        pecas += [o for o in conj.children_recursive
                  if _chapas.MARCA_CHAPA in o and o not in dentro_de_porta
                  and _eh_peca(o)]
    if parte in ('TUDO', 'PORTAS'):
        pecas += pecas_dos_alvos(portas)
    return list(dict.fromkeys(pecas))


def _rotulo_comodo(nome, n):
    return "%s (%d)" % (nome or SEM_COMODO, n)


def perguntar_pintar(context, it):
    """First question: which cabinets, by room."""
    grupos = modulos_por_comodo(context.scene)
    if not grupos:
        return False
    _pintar_pendente[0] = it["chave"]
    _apagar_pendente[0] = None
    op = OBJECT_OT_pintar_modulos.bl_idname
    ordem = sorted(grupos, key=lambda n: (n == '', _orcamento._ordem_comodo(n) if n else 0))
    opcoes = [(_rotulo_comodo(n, len(grupos[n])), 'HOME', op,
               {"chave": it["chave"], "comodo": n}) for n in ordem]
    if len(grupos) > 1:
        opcoes.append(("All (%d)" % sum(len(v) for v in grupos.values()),
                       'WORLD', op, {"chave": it["chave"], "comodo": TODOS}))
    opcoes.append(("Cancel", 'X', op, {"chave": it["chave"], "comodo": CANCELAR}))
    _perguntas._perguntar(context, "Which cabinets should use %s?" % nome_do_material(it),
                          opcoes, na_gaveta=True)
    _perguntas._pergunta_atual[0]['biblioteca'] = True
    _gaveta._rolar_biblioteca_ate_pergunta(context)
    return True


def _perguntar_parte(context, it, comodo, n):
    _pintar_pendente[0] = it["chave"]
    op = OBJECT_OT_pintar_modulos.bl_idname
    quem = ("All %d cabinets" % n if comodo == TODOS
            else _rotulo_comodo(comodo, n).replace(' (', ': ').rstrip(')') + " cabinet(s)")
    opcoes = [(rotulo, 'BRUSH_DATA', op,
               {"chave": it["chave"], "comodo": comodo, "parte": parte})
              for parte, rotulo in PARTES_PINTURA]
    opcoes.append(("Cancel", 'X', op, {"chave": it["chave"], "comodo": CANCELAR}))
    _perguntas._perguntar(context, "%s: what should use %s?" % (quem, nome_do_material(it)),
                          opcoes, na_gaveta=True)
    _perguntas._pergunta_atual[0]['biblioteca'] = True
    _gaveta._rolar_biblioteca_ate_pergunta(context)


class OBJECT_OT_pintar_modulos(Operator):
    """Apply material to an entire room's cabinets (right click on the sphere):
    everything, box only, or doors only."""
    bl_idname = "object.cabinet_pintar_modulos"
    bl_label = "Paint Cabinets"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    chave: StringProperty(options={'SKIP_SAVE'})
    # Room name ('' = no room), TODOS or CANCELAR.
    comodo: StringProperty(options={'SKIP_SAVE'})
    # Empty = ask the second question; TUDO, CAIXA or PORTAS.
    parte: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        it = achar(self.chave)
        if it is None or self.comodo == CANCELAR:
            _pintar_pendente[0] = None
            return {'CANCELLED'}
        grupos = modulos_por_comodo(context.scene)
        modulos = ([m for v in grupos.values() for m in v] if self.comodo == TODOS
                   else grupos.get(self.comodo, []))
        if not modulos:
            _pintar_pendente[0] = None
            self.report({'WARNING'}, "No cabinets in this room")
            return {'CANCELLED'}
        if not self.parte:
            # First answer only: ask the second question without an undo step.
            _perguntar_parte(context, it, self.comodo, len(modulos))
            return {'CANCELLED'}
        _pintar_pendente[0] = None
        pecas = [p for m in modulos for p in pecas_do_modulo(m, self.parte)]
        if not pecas:
            self.report({'WARNING'}, "Nothing to paint (no doors?)")
            return {'CANCELLED'}
        aplicar(list(dict.fromkeys(pecas)), garantir_material(it))
        self.report({'INFO'}, "%s on %d component(s) in %d cabinet(s)"
                    % (nome_do_material(it), len(pecas), len(modulos)))
        return {'FINISHED'}
