"""Estimates in .txt (Options button) and rooms (Outliner folders)."""

import os
import re

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper

# Used only at RUNTIME (circular imports): __init__ wires these
# aliases after loading all modules (`_ligar_modulos`).
_chapas = _modulos = _eventos = _portas = _solda = _perguntas = None
_prateleiras = _gavetas = _materiais = None

# ======================================================== ESTIMATES
# This is a commercial add-on: do not show "ERP" onscreen. The "Generate Estimate"
# button (gear panel) asks where to save and writes a .txt file in the user's
# company format, already read by its ERP: Markdown following a dictation
# prompt format, with a ```markdown block and outstanding items outside it.
# This module exports ONLY
# cabinetry; the rest follows the prompt's defaults for unspecified content:
# general cleaning, empty Values and Payment sections, and investor profile.
# Invent nothing: the cabinet line is the group NAME, and its details
# (doors, shelves, partitions, handles) come from the 3D model.
# A ROOM is a FOLDER in the Outliner, as requested by the user: a marked
# Collection at the scene root containing the cabinet Collections. It
# is the only source: dragging a cabinet to another Outliner folder
# also changes its room in the estimate.
MARCA_COLECAO_COMODO = "eh_colecao_comodo"
ALVO_COMODO = '@comodo'                  # Target of the 'choice' that assigns the room.
SUSPENSO_COMODO = 'comodo'               # Expandable list in the Cabinets tab.
COMODO_NENHUM = ''                       # Return the cabinet to the root.
COMODO_OUTRO = '@outro'                  # Open the typed-name field.
OP_EXPORTAR_ORCAMENTO = 'object.cabinet_exportar_orcamento'
# Prompt rooms in estimate ORDER (user-entered rooms follow
# alphabetically). Varanda maps to Sacada per the prompt. Keep accents:
# these are folder names and text read by the ERP.
COMODOS = (
    "Kitchen", "Dining Room", "Living Room", "Bedroom", "Suite", "En-suite Bedroom",
    "Bathroom", "En-suite Bathroom", "Powder Room", "Laundry Room",
    "Utility Area", "Balcony", "Office", 'Closet',
)
SINONIMOS_COMODO = {'varanda': "Balcony"}
# After saving, the button shows the result and outstanding items remain
# visible until the next save, a room change, or this timeout.
SEGUNDOS_ORCAMENTO_GERADO = 30.0
_orcamento_gerado = [None]       # {'modulos': n, 'pendencias': [...], 'arquivo'}
ARQUIVO_ORCAMENTO = "Estimate"     # Suggested name in "Save As".
# Name assigned automatically by the add-on: the user has not identified the cabinet.
NOME_AUTOMATICO_MODULO = re.compile(r'^((?:Cabinet|Armario) \d+x\d+x\d+|Assembly|Conjunto)$')
# (singular, plural) by door and handle model.
PALAVRAS_PORTA = {
    'CORRER': ("sliding door", "sliding doors"),
    'BASCULANTE': ("lift-up door", "lift-up doors"),
    'EMBUTIDA': ("inset door", "inset doors"),
    'GIRO': ('hinged door', 'hinged doors'),
}
PALAVRAS_PUXADOR = {'PERFIL': 'profile', 'ALCA': "pull", 'BORDA': 'edge'}
NOMES_DOBRADICA = {'RETA': 'full overlay', 'CURVA': 'half crank',
                  'SUPER_CURVA': "full inset", 'ARTICULADA': 'articulated'}


def _modulo_do_objeto(obj):
    """Cabinet for any of our components: itself, one of its panels, a door
    linked to it (leaf or group), or a handle on one of those doors."""
    if obj is None:
        return None
    if _chapas.MARCA_CONJUNTO in obj:
        return obj
    if _chapas.MARCA_PUXADOR in obj:
        obj = obj.parent
    grupo = _portas._grupo_portas(obj)
    if grupo is not None:
        # Hierarchy first, like `_portas_do_conjunto`: the stored name
        # does not gain .001 when the same preset is inserted twice.
        pai = grupo.parent
        while pai is not None and _chapas.MARCA_CONJUNTO not in pai:
            pai = pai.parent
        if pai is not None:
            return pai
        modulo = bpy.data.objects.get(grupo.get(_portas.CHAVE_MODULO_PORTA, ''))
        return modulo if modulo is not None and _chapas.MARCA_CONJUNTO in modulo else None
    return _portas._modulo_da_chapa(obj)


def _modulos_da_selecao(context):
    modulos = []
    for obj in [context.object, *(getattr(context, 'selected_objects', ())
                                   or ())]:
        modulo = _modulo_do_objeto(obj)
        if modulo is not None and modulo not in modulos:
            modulos.append(modulo)
    return modulos


def _nome_comodo(colecao):
    return _portas._sem_sufixo(colecao.name) if colecao is not None else ''


def _limpar_nome_comodo(nome):
    nome = ' '.join((nome or '').split())
    return SINONIMOS_COMODO.get(nome.casefold(), nome)


def _pais_da_colecao(colecao, cena):
    return [c for c in (cena.collection, *bpy.data.collections)
            if colecao.name in c.children]


def _comodo_do_modulo(conj):
    """Room folder containing the cabinet Collection, or None."""
    colecao = _modulos._colecao_do_modulo(conj)
    if colecao is None:
        return None
    return next((c for c in bpy.data.collections
                 if c.get(MARCA_COLECAO_COMODO)
                 and colecao.name in c.children), None)


def _comodos_da_cena(cena):
    """Room folders present in the scene (by name without .001)."""
    pastas = {}
    for c in cena.collection.children_recursive:
        if c.get(MARCA_COLECAO_COMODO):
            pastas.setdefault(_nome_comodo(c), c)
    return pastas


def _comodos_da_lista(cena):
    """List choices: prompt rooms and names already entered in the scene."""
    digitados = sorted((n for n in _comodos_da_cena(cena) if n not in COMODOS),
                       key=str.casefold)
    return [*COMODOS, *digitados]


def _ordem_comodo(nome):
    return ((0, COMODOS.index(nome), '') if nome in COMODOS
            else (1, 0, nome.casefold()))


def _colecao_do_comodo(cena, nome):
    pasta = _comodos_da_cena(cena).get(nome)
    if pasta is None:
        pasta = bpy.data.collections.new(nome)
        pasta[MARCA_COLECAO_COMODO] = 1
        cena.collection.children.link(pasta)
    return pasta


def _limpar_comodos_vazios():
    for pasta in [c for c in bpy.data.collections
                  if c.get(MARCA_COLECAO_COMODO)
                  and not c.all_objects and not c.children]:
        bpy.data.collections.remove(pasta)


def definir_comodo(cena, modulos, nome):
    """Put each cabinet Collection in folder `nome` (empty = scene root).
    Return the number of cabinets moved or already there."""
    nome = _limpar_nome_comodo(nome)
    feitos = 0
    for conj in modulos:
        if conj is None or _chapas.MARCA_CONJUNTO not in conj:
            continue
        colecao = _modulos._garantir_colecao_modulo(cena, conj)
        destino = (_colecao_do_comodo(cena, nome) if nome
                   else cena.collection)
        # Link before unlinking: the Collection must always have an owner.
        if colecao.name not in destino.children:
            destino.children.link(colecao)
        for pai in _pais_da_colecao(colecao, cena):
            if pai != destino:
                pai.children.unlink(colecao)
        feitos += 1
    _limpar_comodos_vazios()
    _orcamento_gerado[0] = None
    return feitos


def _abrir_caixa_comodo(context):
    """"Other Name...": the same field as the group name box, directly below
    the room row. Store the cabinets: clicking elsewhere may change
    selection before Enter."""
    nomes = [m.name for m in _modulos_da_selecao(context)]
    _solda._nome_grupo_gaveta[0] = {'comodo': nomes, 'grupo': '', 'texto': '',
                             'cursor': 0, 'selecionado': False}
    op = 'object.cabinet_definir_comodo'
    _perguntas._pergunta_atual[0] = {
        'texto': "Room name", 'campo': True, 'na_gaveta': True,
        'comodo': True,
        'opcoes': [('OK', 'CHECKMARK', op, {'digitado': True}),
                   ("Cancel", 'X', op, {'manter': True})]}


def _confirmar_campo_gaveta(estado):
    """Enter/OK in the black box field: group or room name."""
    if estado.get('comodo') is not None:
        modulos = [bpy.data.objects.get(n) for n in estado['comodo']]
        nome = _limpar_nome_comodo(estado['texto'])
        return bool(nome) and bool(definir_comodo(
            bpy.context.scene, modulos, nome))
    return _modulos.nomear_grupo(bpy.data.objects.get(estado['grupo']), estado['texto'])


class OBJECT_OT_definir_comodo(Operator):
    """Put selected cabinets in the room folder (Outliner)."""
    bl_idname = 'object.cabinet_definir_comodo'
    bl_label = "Cabinet Room"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    nome: StringProperty(name="Room", options={'SKIP_SAVE'})
    # OK / Cancel for the "Other Name..." box.
    digitado: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})
    manter: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        estado = _solda._nome_grupo_gaveta[0]
        _eventos._redesenhar_viewports(context)
        if self.digitado or self.manter:
            _solda._nome_grupo_gaveta[0] = _perguntas._pergunta_atual[0] = None
            if self.manter or estado is None:
                return {'CANCELLED'}
            return ({'FINISHED'} if _confirmar_campo_gaveta(estado)
                    else {'CANCELLED'})
        if not definir_comodo(context.scene, _modulos_da_selecao(context),
                              self.nome):
            self.report({'WARNING'}, "Select a cabinet")
            return {'CANCELLED'}
        return {'FINISHED'}


def _quantos(n, palavras):
    singular, plural = palavras
    return '%d %s' % (n, singular if n == 1 else plural)


def _pecas_internas(conj):
    """(shelves, partitions) in the CABINET frame, including rotated cabinets:
    a horizontal panel between bottom and top, and an upright panel between
    left and right. Outer panels are the base, top, and sides."""
    inversa = conj.matrix_world.to_3x3().normalized().inverted()
    posicoes = {0: [], 2: []}
    for chapa in _modulos._chapas_do_conjunto(conj):
        normal = inversa @ _chapas._eixos(chapa)[2]
        eixo = max(range(3), key=lambda i: abs(normal[i]))
        if eixo in posicoes:
            posicoes[eixo].append((inversa @ _chapas._centro(chapa))[eixo])

    def entre(valores):
        if len(valores) < 3:
            return 0
        baixo, alto = min(valores), max(valores)
        return sum(1 for v in valores
                   if baixo + _modulos.TOL_BORDA < v < alto - _modulos.TOL_BORDA)
    # Plus those from the Shelves tab (children of their group, not the cabinet).
    return (entre(posicoes[2]) + _prateleiras.quantas_no_modulo(conj),
            entre(posicoes[0]))


def cadastro_do_modulo(conj):
    """Current 3D record without persisting counts that become stale in presets."""
    bpy.context.view_layer.update()
    dep = bpy.context.evaluated_depsgraph_get()
    inversa = conj.matrix_world.to_quaternion().inverted().to_matrix()
    origem = conj.matrix_world.translation
    # The frame removes only rotation: actual scale and mesh edits
    # contribute to measurements, excluding open doors/drawers and hardware.
    pontos = []
    for peca in _modulos.pecas_do_envelope(conj):
        avaliada = peca.evaluated_get(dep)
        matriz = avaliada.matrix_world
        pontos.extend(inversa @ (matriz @ v.co - origem)
                      for v in avaliada.data.vertices)
    medidas = (tuple((max(p[i] for p in pontos) - min(p[i] for p in pontos))
                     * 1000.0 for i in (0, 2, 1)) if pontos else None)
    portas, dobradicas = {}, set()
    dobradicas_pendentes = False
    grupos = _portas._portas_do_conjunto(conj)
    for grupo in grupos:
        folhas = _portas._folhas_portas(grupo)
        if not folhas:
            continue
        p = grupo.get('porta_parametros') or {}
        abertura = p.get('abertura', 'GIRO')
        tipo = ('EMBUTIDA' if abertura == 'GIRO'
                and p.get('dobradica') == 'SUPER_CURVA' else abertura)
        portas[tipo] = portas.get(tipo, 0) + len(folhas)
        if abertura != 'CORRER':
            dobradica = p.get('dobradica')
            if dobradica in NOMES_DOBRADICA:
                dobradicas.add(dobradica)
            else:
                dobradicas_pendentes = True
            if p.get('dobradica_articulada') or (abertura == 'ZIGZAG' and len(folhas) > 1):
                dobradicas.add('ARTICULADA')
    gavetas = sum(1 for grupo in _gavetas.grupos_do_modulo(conj)
                  for gaveta in _gavetas.gavetas_do_grupo(grupo)
                  if any(_chapas.MARCA_CHAPA in o for o in gaveta.children_recursive))
    materiais, sem_material = set(), 0
    for peca in _materiais.pecas_dos_alvos([conj, *grupos]):
        # Stored slots with no faces do not represent material in use.
        indices = {p.material_index for p in peca.data.polygons}
        faltando = not indices
        for i in indices:
            mat = peca.material_slots[i].material if i < len(peca.material_slots) else None
            if mat is None:
                faltando = True
                continue
            chave = mat.get(_materiais.CHAVE_MATERIAL, '')
            partes = chave.split('/') if isinstance(chave, str) else []
            nome = ('%s %s' % (partes[0], partes[-1])
                    if len(partes) >= 2 and partes[0] and partes[-1] else mat.name)
            materiais.add(nome)
        sem_material += int(faltando)
    prateleiras, divisorias = _pecas_internas(conj)
    return dict(medidas_mm=medidas, portas=portas,
                dobradicas=sorted(dobradicas), dobradicas_pendentes=dobradicas_pendentes,
                gavetas=gavetas, materiais=sorted(materiais, key=str.casefold),
                pecas_sem_material=sem_material,
                prateleiras=prateleiras, divisorias=divisorias)


def _detalhes_do_modulo(conj, puxadores, cadastro=None):
    """Third estimate level: only what the 3D model HAS."""
    cadastro = cadastro if cadastro is not None else cadastro_do_modulo(conj)
    medidas = cadastro['medidas_mm']
    detalhes = [("Overall dimensions (width x height x depth): %s mm"
                 % ' x '.join(format(round(v, 2), '.2f').rstrip('0').rstrip('.')
                              for v in medidas)) if medidas else "Overall dimensions not identified"]
    for tipo, n in cadastro['portas'].items():
        if n:
            detalhes.append(_quantos(n, PALAVRAS_PORTA.get(
                tipo, PALAVRAS_PORTA['GIRO'])))
    if not cadastro['portas']:
        detalhes.append("No doors")
    dobradicas = [NOMES_DOBRADICA[t] for t in cadastro['dobradicas']]
    if cadastro['dobradicas_pendentes']:
        dobradicas.append("not identified")
    detalhes.append("Hinges: " + ', '.join(dobradicas) if dobradicas else "No hinges")
    n = cadastro['gavetas']
    detalhes.append(_quantos(n, ("internal drawer", "internal drawers"))
                    if n else "No internal drawers")
    prateleiras, divisorias = cadastro['prateleiras'], cadastro['divisorias']
    detalhes.append(_quantos(prateleiras, ("internal shelf",
                                           "internal shelves"))
                    if prateleiras else "No internal shelves")
    if divisorias:
        detalhes.append(_quantos(divisorias, ("internal partition",
                                              "internal partitions")))
    for tipo, n in puxadores.items():
        palavra = PALAVRAS_PUXADOR.get(tipo, '')
        detalhes.append(_quantos(n, ((palavra + ' handle').strip(),
                                     (palavra + ' handles').strip())))
    materiais = cadastro['materiais']
    detalhes.append("Materials: " + ', '.join(materiais) if materiais else "Material not identified")
    if materiais and cadastro['pecas_sem_material']:
        detalhes.append(_quantos(cadastro['pecas_sem_material'],
                                 ("part without material", "parts without material")))
    return detalhes


def _puxadores_por_modulo(objetos):
    """{cabinet: {type: count}}; imported items without a type count as ''."""
    contas = {}
    for pux in objetos:
        if _chapas.MARCA_PUXADOR not in pux:
            continue
        modulo = _modulo_do_objeto(pux)
        if modulo is not None:
            tipos = contas.setdefault(modulo.name, {})
            tipo = pux.get('puxador_tipo', '')
            tipos[tipo] = tipos.get(tipo, 0) + 1
    return contas


def orcamento_da_cena(cena):
    """(text, exported cabinets, outstanding items) in the company format."""
    objetos = list(cena.objects)
    puxadores = _puxadores_por_modulo(objetos)
    por_comodo = {}
    pendencias = []
    modulos = sorted((o for o in objetos if _chapas.MARCA_CONJUNTO in o
                      and _modulos._chapas_do_conjunto(o)),
                     key=lambda o: o.name.casefold())
    for conj in modulos:
        nome = _portas._sem_sufixo(conj.name)
        comodo = _nome_comodo(_comodo_do_modulo(conj)) or None
        if NOME_AUTOMATICO_MODULO.match(nome):
            pendencias.append("- %s%s: the cabinet type was not specified (the group still has its automatic name)."
                              % (comodo + ', ' if comodo else '', nome))
        if comodo is None:
            pendencias.append("- %s: the room was not specified; the cabinet was excluded from the estimate."
                              % nome)
            continue
        cadastro = cadastro_do_modulo(conj)
        if cadastro['pecas_sem_material']:
            pendencias.append("- %s, %s: material not identified on %s." % (
                comodo, nome, _quantos(cadastro['pecas_sem_material'], ('part', 'parts'))))
        if cadastro['dobradicas_pendentes']:
            pendencias.append("- %s, %s: hinge type not identified." % (comodo, nome))
        por_comodo.setdefault(comodo, []).append(
            (nome, _detalhes_do_modulo(conj, puxadores.get(conj.name, {}), cadastro)))
    soltas = [o for o in objetos if _chapas.MARCA_CHAPA in o and _chapas.MARCA_FOLHA not in o
              and _portas._modulo_da_chapa(o) is None]
    if soltas:
        pendencias.append('- %s, outside a cabinet: the cabinet was not specified; '
                          'excluded from the estimate.' %
                          _quantos(len(soltas), ('loose panel', 'loose panels')))

    linhas = ["# Estimate", "client:", "address:",
              "profile: investor", '']
    exportados = sum(len(v) for v in por_comodo.values())
    if exportados:
        # A block without content has no heading (prompt rule).
        linhas += ["## Furniture", '']
        for comodo in sorted(por_comodo, key=_ordem_comodo):
            itens = por_comodo[comodo]
            linhas.append('### ' + comodo)
            for nome, detalhes in itens:
                linhas.append('- ' + nome)
                linhas += ['  - ' + d for d in detalhes]
            linhas.append('')
    # Cleaning is the only unsolicited item; without construction work, use general cleaning.
    linhas += ["## Other", '', "### General", "- General cleaning.", '',
               "## Costs", "- furniture:", "- construction:", "- appliances:",
               "- other:", '',
               "## Payment", "- method: down payment+installments",
               "- down payment:", "- installments:"]
    texto = '```markdown\n' + '\n'.join(linhas) + '\n```\n\n'
    if pendencias:
        texto += ("Pending items\n" + '\n'.join(pendencias)
                  + "\n\nWould you like to update any of these before I rebuild the estimate?\n")
    else:
        texto += "No pending items.\n"
    return texto, exportados, pendencias


def _apagar_orcamento_gerado():
    _orcamento_gerado[0] = None
    for janela in bpy.context.window_manager.windows:
        for area in janela.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
    return None


def _arquivo_sugerido():
    """Beside the .blend with the same name; if unsaved, use the user's folder
    (Blender's "Save As" would open in the executable's folder)."""
    if bpy.data.filepath:
        pasta, nome = os.path.split(bpy.data.filepath)
        return os.path.join(pasta, '%s - %s.txt' % (
            ARQUIVO_ORCAMENTO, os.path.splitext(nome)[0]))
    return os.path.join(os.path.expanduser('~'), ARQUIVO_ORCAMENTO + '.txt')


class OBJECT_OT_exportar_orcamento(Operator, ExportHelper):
    """Save an estimate for the scene's furniture to a text file (.txt)."""
    bl_idname = OP_EXPORTAR_ORCAMENTO
    bl_label = "Generate estimate"

    filename_ext = '.txt'
    filter_glob: StringProperty(default='*.txt', options={'HIDDEN'})

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = _arquivo_sugerido()
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        texto, exportados, pendencias = orcamento_da_cena(context.scene)
        caminho = bpy.path.ensure_ext(bpy.path.abspath(self.filepath), '.txt')
        try:
            # UTF-8 for accented room names and system line endings let
            # Notepad open the file directly.
            with open(caminho, 'w', encoding='utf-8') as arquivo:
                arquivo.write(texto)
        except OSError as e:
            self.report({'ERROR'}, "Could not save the estimate: %s" % e)
            return {'CANCELLED'}
        # The sidebar shows what happened; a status-bar report alone
        # went unnoticed ("copy and nothing happens").
        _orcamento_gerado[0] = {'modulos': exportados,
                                'pendencias': list(pendencias),
                                'arquivo': os.path.basename(caminho)}
        if bpy.app.timers.is_registered(_apagar_orcamento_gerado):
            bpy.app.timers.unregister(_apagar_orcamento_gerado)
        bpy.app.timers.register(_apagar_orcamento_gerado,
                                first_interval=SEGUNDOS_ORCAMENTO_GERADO)
        _eventos._redesenhar_viewports(context)
        self.report({'WARNING'} if pendencias else {'INFO'},
                    "Estimate saved to %s: %d cabinet(s)%s" % (
                        caminho, exportados, ", %d pending item(s)"
                        % len(pendencias) if pendencias else ""))
        return {'FINISHED'}
