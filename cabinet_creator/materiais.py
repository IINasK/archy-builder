"""Materiais da biblioteca (MDF/MDP): catalogo de CORES SOLIDAS em cascata,
aplicadas nas chapas como um Material do Blender so' com a cor (pedido do
usuario: sem textura por enquanto; a cor aparece no Solid da viewport).
A preview e' uma esfera sombreada (como a de material do Blender),
rasterizada aqui mesmo -- nenhum render, nenhum arquivo de foto."""

import bpy, json, os, time
from bpy.props import StringProperty, FloatVectorProperty, EnumProperty, BoolProperty
from bpy.types import Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_biblioteca = _chapas = _ferragens = _perguntas = _gaveta = _portas = None
_orcamento = None
_gavetas = None
_prateleiras = None

# 1o clique numa esfera: (chave, instante, mouse_x, mouse_y). Clique
# simples NAO pinta (pedido do usuario: um clique errado mudaria o que nao
# devia); so' o 2o, rapido e no mesmo lugar, aplica na selecao.
_clique_esfera = [None]

NOME_ARQUIVO = "materiais.json"
# ID prop do Material do Blender: a chave do item do catalogo. E' por ela
# (nunca pelo nome, que o Blender sufixa com .001) que o material e'
# reencontrado ao reaplicar ou editar.
CHAVE_MATERIAL = "cabinet_material"

# Cascata de fabrica: nivel 1 = MDF/MDP (pedido do usuario); os niveis
# de baixo tambem nascem dos itens do arquivo, como os da biblioteca.
ARVORE_MATERIAIS = {
    "MDF": {"Unicolores": [], "Madeirados": []},
    "MDP": {"Unicolores": [], "Madeirados": []},
}

# Catalogo inicial, usado enquanto a biblioteca nao tem `materiais.json`
# (o arquivo nasce na primeira edicao). Cor = sRGB em hexa, como se le
# num catalogo de fornecedor.
MATERIAIS_PADRAO = (
    ("MDF", "Unicolores", "Branco TX", "#EDEDE8"),
    ("MDF", "Unicolores", "Branco Neve", "#F7F7F4"),
    ("MDF", "Unicolores", "Preto TX", "#222222"),
    ("MDF", "Unicolores", "Cinza Cristal", "#B4B6B3"),
    ("MDF", "Unicolores", "Grafite", "#4B4D50"),
    ("MDF", "Unicolores", "Areia", "#D9CDB8"),
    ("MDF", "Unicolores", "Fendi", "#C3B7A6"),
    ("MDF", "Madeirados", "Freijo", "#A97C50"),
    ("MDF", "Madeirados", "Carvalho", "#BC9567"),
    ("MDF", "Madeirados", "Nogueira", "#6F4C35"),
    ("MDF", "Madeirados", "Louro Preto", "#5B4334"),
    ("MDF", "Madeirados", "Cumaru", "#8E5B3D"),
    ("MDP", "Unicolores", "Branco TX", "#EDEDE8"),
    ("MDP", "Unicolores", "Preto TX", "#222222"),
    ("MDP", "Unicolores", "Cinza Cristal", "#B4B6B3"),
    ("MDP", "Unicolores", "Grafite", "#4B4D50"),
    ("MDP", "Madeirados", "Freijo", "#A97C50"),
    ("MDP", "Madeirados", "Carvalho", "#BC9567"),
    ("MDP", "Madeirados", "Nogueira", "#6F4C35"),
)

_cache = [None]          # (caminho, mtime, itens): a gaveta le a cada redesenho
_texturas_esfera = {}    # cor hexa -> GPUTexture da esfera
_apagar_pendente = [None]  # chave esperando o "Apagar?" da caixa preta


# ------------------------------------------------------------- catalogo
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


def ler_materiais():
    """Itens do catalogo (dicts com n1/n2/n3/nome/cor/chave). Sem
    arquivo na biblioteca: o catalogo de fabrica."""
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
        print("[Cabinet Creator] materiais ilegiveis:", e)
        return _padrao()
    _cache[0] = (caminho, mtime, itens)
    return [dict(it) for it in itens]


def gravar_materiais(itens):
    """Grava o catalogo inteiro (atomico, so' se mudou)."""
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


# ------------------------------------------------------------------ cor
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
    """sRGB 0..1 de '#RRGGBB'."""
    hexa = _hexa_valido(hexa) or "#808080"
    return tuple(int(hexa[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


def hexa_de(rgb):
    return "#" + "".join("%02X" % max(0, min(255, round(c * 255))) for c in rgb[:3])


def _linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_linear(hexa):
    """O Material guarda cor LINEAR; o catalogo, sRGB."""
    return tuple(_linear(c) for c in rgb_de(hexa))


# ------------------------------------------------------ material na cena
def material_da_chave(chave):
    return next((m for m in bpy.data.materials
                 if m.get(CHAVE_MATERIAL) == chave), None)


def nome_do_material(it):
    return "%s %s" % (it["n1"], it["nome"])


def garantir_material(it):
    """O Material do Blender do item: so' a cor solida -- a do Solid da
    viewport (`diffuse_color`) e a do Principled (Material Preview e
    render). Existindo, so' acompanha nome e cor do catalogo."""
    mat = material_da_chave(it["chave"])
    if mat is None:
        mat = bpy.data.materials.new(nome_do_material(it))
        mat[CHAVE_MATERIAL] = it["chave"]
    elif not mat.name.startswith(nome_do_material(it)):
        mat.name = nome_do_material(it)
    cor = (*rgb_linear(it["cor"]), 1.0)
    mat.diffuse_color = cor
    if mat.node_tree is None:
        try:
            mat.use_nodes = True        # 4.x; no 5.x ja' nasce com nos
        except Exception:
            pass
    arvore = mat.node_tree
    if arvore is not None:
        for no in arvore.nodes:
            if no.type == 'BSDF_PRINCIPLED':
                no.inputs['Base Color'].default_value = cor
    return mat


def _eh_peca(obj):
    """Malha que leva material: chapa, folha, moldura ou objeto comum --
    nunca puxador, acessorio ou ferragem (essas tem o material delas)."""
    return (obj.type == 'MESH'
            and not any(m in obj for m in (_chapas.MARCA_PUXADOR,
                                           _chapas.MARCA_ACESSORIO,
                                           _ferragens.CHAVE_FERRAGEM)))


def pecas_dos_alvos(objs):
    """As pecas que um material pinta, pela regra da selecao: MODULO =
    as chapas dele (a porta e' outro item); PORTA = folhas e moldura;
    peca solta ou folha (duplo clique) = so' ela."""
    pecas = []
    for obj in objs:
        if (_gavetas.MARCA_GRUPO in obj or _gavetas.MARCA_GAVETA in obj
                or _prateleiras.MARCA_GRUPO in obj):
            # gavetas: frentes e caixas (trilho tem o material dele)
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
    """As pecas que a esfera SOLTA sobre `obj` pinta. `obj` na selecao: a
    selecao (o duplo clique ja' isolou a peca, se for o caso); fora dela:
    o que um clique em `obj` selecionaria -- o modulo, a porta inteira ou
    a peca solta."""
    if obj.select_get():
        return pecas_dos_alvos(selecionados)
    dono = (_portas._grupo_portas(obj) or _portas._modulo_da_chapa(obj)
            or obj)
    return pecas_dos_alvos([dono])


def duplo_clique_na_esfera(chave, x, y, limite_ms, agora=None):
    """True se este PRESS fecha um duplo clique na esfera `chave` (rapido e
    no mesmo lugar); senao, guarda-o como o 1o. Pelo relogio, como o da
    foto: o 2o clique chega a' gaveta como PRESS, nao DOUBLE_CLICK."""
    agora = time.monotonic() if agora is None else agora
    raio = _biblioteca.RAIO_DUPLO_CLIQUE_PX
    anterior = _clique_esfera[0]
    duplo = (anterior is not None and anterior[0] == chave
             and (agora - anterior[1]) * 1000.0 <= limite_ms
             and (x - anterior[2]) ** 2 + (y - anterior[3]) ** 2 <= raio ** 2)
    _clique_esfera[0] = None if duplo else (chave, agora, x, y)
    return duplo


def aplicar(pecas, mat):
    """Material no slot do OBJETO (`link='OBJECT'`): sobrevive a' malha
    refeita (porta, moldura) e nao pinta quem divide a malha."""
    for obj in pecas:
        if not obj.material_slots:
            obj.data.materials.append(None)
        for slot in obj.material_slots:
            slot.link = 'OBJECT'
            slot.material = mat


def chave_aplicada(obj):
    """Chave do material do catalogo na peca (ou no 1o item do grupo)."""
    pecas = pecas_dos_alvos([obj]) if obj is not None else []
    for peca in pecas[:1]:
        for slot in peca.material_slots:
            if slot.material is not None:
                return slot.material.get(CHAVE_MATERIAL, "")
    return ""


# ------------------------------------------------------- esfera (preview)
LADO_ESFERA = 96
LUZ_ESFERA = (-0.45, 0.55, 0.70)    # de cima a' esquerda, como a do Blender


def esfera_rgba(rgb, lado=LADO_ESFERA):
    """Pixels RGBA (float, linha 0 embaixo) de uma esfera da cor `rgb`
    (sRGB): difusa + ambiente + brilho, borda suavizada. Fundo
    transparente, para cair sobre o quadrado do tema."""
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
    # cobertura pela distancia (px) ate' o contorno: borda sem serrilhado
    borda = (1.0 - np.sqrt(r2)) * raio * lado / 2.0
    saida[:, :, 3] = np.clip(borda + 0.5, 0.0, 1.0)
    return saida.ravel()


def desenhar_esfera(hexa, x, y, w, h):
    """A esfera do material no quadrado (x, y, w, h) da gaveta."""
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


# ------------------------------------------------------------ operadores
class OBJECT_OT_aplicar_material(Operator):
    """Pinta a selecao com o material: modulo = as chapas dele, porta =
    folhas e moldura, peca = so' ela"""
    bl_idname = "object.cabinet_aplicar_material"
    bl_label = "Aplicar Material"
    bl_options = {'REGISTER', 'UNDO'}

    chave: StringProperty(options={'SKIP_SAVE'})
    # nome do objeto onde a esfera foi SOLTA (vazio = a selecao)
    alvo: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        it = achar(self.chave)
        if it is None:
            self.report({'ERROR'}, "Material nao encontrado: %s" % self.chave)
            return {'CANCELLED'}
        if self.alvo:
            obj = bpy.data.objects.get(self.alvo)
            pecas = (pecas_do_solte(obj, context.selected_objects)
                     if obj is not None else [])
            aviso = "Solte o material sobre um modulo, porta ou peca"
        else:
            pecas = pecas_dos_alvos(context.selected_objects)
            aviso = "Selecione um modulo, porta ou peca para aplicar"
        if not pecas:
            self.report({'WARNING'}, aviso)
            return {'CANCELLED'}
        aplicar(pecas, garantir_material(it))
        self.report({'INFO'}, "%s em %d peca(s)" % (nome_do_material(it), len(pecas)))
        return {'FINISHED'}


def _itens_n1(self, context):
    return [(k, k, "") for k in filhos_n1(ler_materiais())]


class _CamposMaterial:
    nome: StringProperty(name="Nome", default="Novo material")
    cor: FloatVectorProperty(name="Cor", subtype='COLOR_GAMMA', size=3,
                             min=0.0, max=1.0, default=(0.8, 0.8, 0.8))
    n1: EnumProperty(name="Material", items=_itens_n1)
    n2: StringProperty(name="Categoria", default="Unicolores")
    n3: StringProperty(name="Subcategoria", default="")

    def draw(self, context):
        for campo in ("nome", "cor", "n1", "n2", "n3"):
            self.layout.prop(self, campo)

    def _item(self):
        return _completar({"nome": self.nome.strip(), "n1": self.n1,
                           "n2": self.n2.strip(), "n3": self.n3.strip(),
                           "cor": hexa_de(self.cor)})


class OBJECT_OT_novo_material(_CamposMaterial, Operator):
    """Acrescenta um material (cor solida) a' biblioteca"""
    bl_idname = "object.cabinet_novo_material"
    bl_label = "Novo Material"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        s = context.scene
        # nasce na categoria que esta' aberta na cascata
        if s.cabinet_mat_n1 in filhos_n1(ler_materiais()):
            self.n1 = s.cabinet_mat_n1
        self.n2 = s.cabinet_mat_n2 or self.n2
        self.n3 = s.cabinet_mat_n3
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        novo = self._item()
        if not novo["nome"]:
            self.report({'ERROR'}, "Material sem nome")
            return {'CANCELLED'}
        itens = ler_materiais()
        if achar(novo["chave"], itens) is not None:
            self.report({'ERROR'}, "Ja' existe %s nessa categoria" % novo["nome"])
            return {'CANCELLED'}
        gravar_materiais(itens + [novo])
        self.report({'INFO'}, "Material %s criado" % nome_do_material(novo))
        return {'FINISHED'}


class OBJECT_OT_editar_material(_CamposMaterial, Operator):
    """Muda nome, cor ou categoria de um material da biblioteca (os
    Materiais ja' aplicados acompanham)"""
    bl_idname = "object.cabinet_editar_material"
    bl_label = "Editar Material"
    bl_options = {'REGISTER', 'UNDO'}

    chave: StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        it = achar(self.chave)
        if it is None:
            self.report({'ERROR'}, "Material nao encontrado")
            return {'CANCELLED'}
        self.nome, self.cor = it["nome"], rgb_de(it["cor"])
        self.n1, self.n2, self.n3 = it["n1"], it["n2"], it["n3"]
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        itens = ler_materiais()
        antigo = achar(self.chave, itens)
        novo = self._item()
        if antigo is None or not novo["nome"]:
            self.report({'ERROR'}, "Material nao encontrado")
            return {'CANCELLED'}
        if novo["chave"] != antigo["chave"] and achar(novo["chave"], itens):
            self.report({'ERROR'}, "Ja' existe %s nessa categoria" % novo["nome"])
            return {'CANCELLED'}
        gravar_materiais([novo if it["chave"] == antigo["chave"] else it
                          for it in itens])
        mat = material_da_chave(antigo["chave"])
        if mat is not None:
            mat[CHAVE_MATERIAL] = novo["chave"]
            garantir_material(novo)
        return {'FINISHED'}


class OBJECT_OT_apagar_material(Operator):
    """Tira um material da biblioteca (as pecas pintadas continuam)"""
    bl_idname = "object.cabinet_apagar_material"
    bl_label = "Apagar Material"
    bl_options = {'REGISTER', 'INTERNAL'}

    chave: StringProperty(options={'SKIP_SAVE'})
    apagar: BoolProperty(default=True, options={'SKIP_SAVE'})

    def execute(self, context):
        _apagar_pendente[0] = None
        if not self.apagar:
            return {'CANCELLED'}
        itens = ler_materiais()
        if achar(self.chave, itens) is None:
            return {'CANCELLED'}
        gravar_materiais([it for it in itens if it["chave"] != self.chave])
        return {'FINISHED'}


def perguntar_apagar(context, it):
    """"Apagar?" na caixa preta, logo abaixo do material, na gaveta."""
    _apagar_pendente[0] = it["chave"]
    _pintar_pendente[0] = None
    op = OBJECT_OT_apagar_material.bl_idname
    _perguntas._perguntar(context, "Apagar o material %s?" % nome_do_material(it),
                          [("Sim, apagar", 'TRASH', op,
                            {"chave": it["chave"], "apagar": True}),
                           ("Nao", 'X', op, {"chave": it["chave"], "apagar": False})],
                          na_gaveta=True)
    # a caixa nasce na BIBLIOTECA (sob o material), nao na aba de cima
    _perguntas._pergunta_atual[0]['biblioteca'] = True
    _gaveta._rolar_biblioteca_ate_pergunta(context)


# ------------------------------------------------------ pintura rapida
# Pedido do usuario: na biblioteca, mouse sobre o material + botao DIREITO
# = pintar modulos INTEIROS pelo comodo em que estao (Cozinha, Quarto...)
# e, numa 2a pergunta, o que deles: tudo, so' a caixa ou so' as portas.
# As perguntas sao a caixa preta logo abaixo do material (regra da gaveta:
# pergunta que vem dela fica nela, nunca pop-up).
_pintar_pendente = [None]   # chave do material com a "Pintar?" aberta
TODOS = '@todos'
CANCELAR = '@cancelar'
PARTES_PINTURA = (('TUDO', "Tudo"), ('CAIXA', "So' a caixa"),
                  ('PORTAS', "So' as portas"))
SEM_COMODO = "Sem comodo"


def chave_da_caixa():
    """O material sob o qual a caixa preta abre (apagar ou pintar)."""
    return _apagar_pendente[0] or _pintar_pendente[0]


def modulos_por_comodo(cena):
    """{nome do comodo ('' = sem comodo): [modulos]} da cena."""
    grupos = {}
    for conj in cena.objects:
        if _chapas.MARCA_CONJUNTO not in conj:
            continue
        pasta = _orcamento._comodo_do_modulo(conj)
        grupos.setdefault(_orcamento._nome_comodo(pasta) if pasta else '', []).append(conj)
    return grupos


def pecas_do_modulo(conj, parte):
    """As pecas que a pintura rapida pinta: 'CAIXA' = as chapas do corpo
    (laterais, base, tampo, fundo, prateleiras); 'PORTAS' = folhas e
    moldura das portas dele; 'TUDO' = as duas."""
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
    """1a pergunta: quais modulos (por comodo)."""
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
        opcoes.append(("Todos (%d)" % sum(len(v) for v in grupos.values()),
                       'WORLD', op, {"chave": it["chave"], "comodo": TODOS}))
    opcoes.append(("Cancelar", 'X', op, {"chave": it["chave"], "comodo": CANCELAR}))
    _perguntas._perguntar(context, "Pintar com %s quais modulos?" % nome_do_material(it),
                          opcoes, na_gaveta=True)
    _perguntas._pergunta_atual[0]['biblioteca'] = True
    _gaveta._rolar_biblioteca_ate_pergunta(context)
    return True


def _perguntar_parte(context, it, comodo, n):
    _pintar_pendente[0] = it["chave"]
    op = OBJECT_OT_pintar_modulos.bl_idname
    quem = ("Todos os %d modulos" % n if comodo == TODOS
            else _rotulo_comodo(comodo, n).replace(' (', ': ').rstrip(')') + " modulo(s)")
    opcoes = [(rotulo, 'BRUSH_DATA', op,
               {"chave": it["chave"], "comodo": comodo, "parte": parte})
              for parte, rotulo in PARTES_PINTURA]
    opcoes.append(("Cancelar", 'X', op, {"chave": it["chave"], "comodo": CANCELAR}))
    _perguntas._perguntar(context, "%s: pintar o que com %s?" % (quem, nome_do_material(it)),
                          opcoes, na_gaveta=True)
    _perguntas._pergunta_atual[0]['biblioteca'] = True
    _gaveta._rolar_biblioteca_ate_pergunta(context)


class OBJECT_OT_pintar_modulos(Operator):
    """Pinta os modulos de um comodo inteiro com o material (botao direito
    na esfera): tudo, so' a caixa ou so' as portas"""
    bl_idname = "object.cabinet_pintar_modulos"
    bl_label = "Pintar Modulos"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    chave: StringProperty(options={'SKIP_SAVE'})
    # nome do comodo ('' = sem comodo), TODOS ou CANCELAR
    comodo: StringProperty(options={'SKIP_SAVE'})
    # vazio = ainda pergunta (a 2a pergunta); TUDO, CAIXA ou PORTAS
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
            self.report({'WARNING'}, "Nenhum modulo nesse comodo")
            return {'CANCELLED'}
        if not self.parte:
            # so' a 1a resposta: a 2a pergunta, sem passo de desfazer
            _perguntar_parte(context, it, self.comodo, len(modulos))
            return {'CANCELLED'}
        _pintar_pendente[0] = None
        pecas = [p for m in modulos for p in pecas_do_modulo(m, self.parte)]
        if not pecas:
            self.report({'WARNING'}, "Nada para pintar (sem portas?)")
            return {'CANCELLED'}
        aplicar(list(dict.fromkeys(pecas)), garantir_material(it))
        self.report({'INFO'}, "%s em %d peca(s) de %d modulo(s)"
                    % (nome_do_material(it), len(pecas), len(modulos)))
        return {'FINISHED'}
