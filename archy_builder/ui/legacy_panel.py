"""Legacy N-panel (deliberately excluded from CLASSES)."""

import bpy, os
from bpy.types import Panel

# Used only at RUNTIME (circular imports): __init__ binds these aliases after loading
# all modules (`_ligar_modulos`).
_chapas = _modulos = _biblioteca = _portas = _gaveta = None

class VIEW3D_PT_archy_builder(Panel):
    # The header is the tab bar; do not repeat a title beside it.
    bl_label = ""
    bl_idname = "VIEW3D_PT_archy_builder"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Archy Builder"
    bl_options = {'HEADER_LAYOUT_EXPAND'}

    @classmethod
    def poll(cls, context):
        return not _gaveta._eh_area_gaveta(context)

    def draw_header(self, context):
        linha = self.layout.row(align=True)
        linha.prop(context.scene, 'cabinet_aba', expand=True)

    def draw(self, context):
        layout = self.layout
        if context.scene.cabinet_aba == 'PORTAS':
            self.desenhar_portas(context, layout)
        else:
            self.desenhar_medidas(context, layout)
            layout.separator()
            self.desenhar_biblioteca(context, layout)

    def desenhar_portas(self, context, layout):
        caixa = layout.box()
        caixa.label(text="Parametric Doors")
        grupo = _portas._grupo_portas(context.object)
        if grupo is not None and context.mode == 'OBJECT':
            op = caixa.operator("object.cabinet_portas", text="Configure Doors",
                                icon='PREFERENCES')
            op.editar = True
        else:
            caixa.label(text="2 diagonal vertices of the internal opening")
            linha = caixa.row()
            linha.enabled = context.mode == 'EDIT_MESH'
            op = linha.operator("object.cabinet_portas", text="Create Doors",
                                icon='MESH_CUBE')
            op.editar = False
            if context.mode != 'EDIT_MESH':
                caixa.label(text="Select the panels and enter Edit Mode")

    # ------------------------------------------------------- DIMENSIONS
    def _abas_modo(self, layout, ativo):
        linha = layout.row(align=True)
        for modo, texto in (('INDIVIDUAL', "Individual"), ('GRUPO', "Group")):
            op = linha.operator(
                "object.cabinet_modo_medidas", text=texto,
                depress=(ativo == modo))
            op.modo = modo

    def _largura_logica(self, context):
        escala = max(0.5, float(context.preferences.system.ui_scale))
        return float(context.region.width) / escala

    def _painel_estreito(self, context):
        return self._largura_logica(context) < _biblioteca.WIREFRAME_LARGURA_EMPILHAR_PX

    def _painel_muito_estreito(self, context):
        return (self._largura_logica(context) <
                _biblioteca.MEDIDAS_LARGURA_COLUNA_UNICA_PX)

    def _escala_wireframe(self, context):
        """Responsive scale with limits so the preview neither disappears nor dominates
        the panel."""
        disponivel = max(0.0, self._largura_logica(context) - 24.0)
        escala = disponivel / 20.0
        maximo = (_biblioteca.WIREFRAME_ESCALA_ESTREITA_MAX_UI
                  if self._painel_estreito(context)
                  else _biblioteca.WIREFRAME_ESCALA_MAX_UI)
        return max(_biblioteca.WIREFRAME_ESCALA_MIN_UI,
                   min(maximo, escala))

    def _corpo_medidas(self, caixa, context, separador=0.4):
        """Return controls and visual area, side by side or stacked."""
        estreito = self._painel_estreito(context)
        corpo = (caixa.column(align=True) if estreito
                 else caixa.row(align=False))
        if not estreito:
            # Inset controls from the box corner without shifting the preview.
            corpo.separator(factor=0.35)
        campos = corpo.column(align=True)
        # In narrow mode the whole grid must use the box center. Keeping this container
        # LEFT-aligned makes Blender compact usable width to the widgets' natural size,
        # leaving more empty space on the right.
        campos.alignment = 'CENTER' if estreito else 'LEFT'
        if not estreito:
            # Reserve only the space labels and fields require. A wider column squeezes
            # the preview on the right before wrapping.
            campos.ui_units_x = _biblioteca.MEDIDAS_LARGURA_CONTROLES_UI
        campos.separator(factor=0.15 if estreito else separador)
        return campos, corpo, estreito

    def _grade_medidas(self, layout, estreito, coluna_unica, desenhadores):
        """Wrap the grid into two columns, or one below the narrow-width threshold."""
        if not estreito:
            for desenhar in desenhadores:
                desenhar(layout)
            return

        def desenhar_no_centro(desenhar, ocupacao=0.5):
            """Create a central strip with symmetric side margins."""
            margem = (1.0 - ocupacao) * 0.5
            externo = layout.split(factor=margem)
            externo.column()
            restante = externo.column()
            proporcao_no_restante = ocupacao / (1.0 - margem)
            centro_direita = restante.split(factor=proporcao_no_restante)
            celula = centro_direita.column(align=True)
            celula.alignment = 'CENTER'
            desenhar(celula)
            centro_direita.column()

        if coluna_unica:
            for desenhar in desenhadores:
                desenhar_no_centro(
                    desenhar, _biblioteca.MEDIDAS_OCUPACAO_COLUNA_UNICA)
            return

        for inicio in range(0, len(desenhadores), 2):
            par = desenhadores[inicio:inicio + 2]
            if len(par) == 2:
                # No fixed width: both cells share space equally and the center does not
                # drift left when compressed. `split` guarantees two actual halves of
                # the available space. Blender may compact two `column` layouts in a
                # `row` according to the fields' natural widths.
                linha = layout.split(factor=0.5, align=False)
                for desenhar in par:
                    celula = linha.column(align=True)
                    celula.alignment = 'CENTER'
                    desenhar(celula)
            else:
                desenhar_no_centro(par[0])

    def _visual_wireframe(self, layout, context, modo, medidas):
        """Draw a responsive preview within visually useful bounds."""
        coluna = layout.column(align=False)
        coluna.alignment = 'CENTER'
        icone = _biblioteca._icone_wireframe(context, modo, *medidas)
        if icone:
            linha = coluna.row(align=True)
            linha.alignment = 'CENTER'
            linha.template_icon(
                icon_value=icone, scale=self._escala_wireframe(context))
        else:
            coluna.label(text="", icon='MESH_CUBE')

    def _campo_medida(self, layout, dados, propriedade, texto):
        """Full label above, compact field immediately below."""
        alinhamento = ('CENTER' if layout.alignment == 'CENTER' else 'LEFT')
        bloco = layout.column(align=True)
        bloco.alignment = alinhamento
        rotulo = bloco.row(align=True)
        rotulo.alignment = alinhamento
        rotulo.label(text=texto)
        valor = bloco.row(align=True)
        valor.alignment = alinhamento
        valor.prop(dados, propriedade, text="")

    def _rotulo_medida(self, layout, texto, valor_mm):
        """Read-only field variant: an arbitrary selection has no property."""
        alinhamento = ('CENTER' if layout.alignment == 'CENTER' else 'LEFT')
        bloco = layout.column(align=True)
        bloco.alignment = alinhamento
        r = bloco.row(align=True)
        r.alignment = alinhamento
        r.label(text=texto)
        v = bloco.row(align=True)
        v.alignment = alinhamento
        v.label(text="%.1f mm" % valor_mm)

    def _campo_dimensao_objeto(self, layout, obj, indice, texto):
        """Editable native dimension; accepts mm, cm and m like Blender."""
        alinhamento = ('CENTER' if layout.alignment == 'CENTER' else 'LEFT')
        bloco = layout.column(align=True)
        bloco.alignment = alinhamento
        rotulo = bloco.row(align=True)
        rotulo.alignment = alinhamento
        rotulo.label(text=texto)
        valor = bloco.row(align=True)
        valor.alignment = alinhamento
        valor.prop(obj, "dimensions", index=indice, text="")

    def _medidas_da_selecao(self, context, layout):
        """Bounding box of ANY selection: cube, car, curves, anything."""
        m = _modulos.medir_selecao(context)
        if m is None:
            layout.label(text="Select a panel, cabinet, or any object", icon='INFO')
            return
        largura, altura, profundidade, quantos = m
        b = layout.box()
        b.label(text="Selection (%d object%s)"
                     % (quantos, "" if quantos == 1 else "s"),
                icon='SHADING_BBOX')
        # Three dimensions take less height than the maximum preview; a larger top
        # margin centers the block and moves it away from the box corner.
        campos, visual, estreito = self._corpo_medidas(
            b, context, separador=1.2)
        volumes = [o for o in context.selected_objects
                   if o.type in _modulos.TIPOS_COM_VOLUME]
        if quantos == 1 and len(volumes) == 1:
            obj = volumes[0]
            # Add-on convention: width=X, height=Z, depth=Y.
            self._grade_medidas(
                campos, estreito, self._painel_muito_estreito(context), [
                lambda lay: self._campo_dimensao_objeto(
                    lay, obj, 0, "Width"),
                lambda lay: self._campo_dimensao_objeto(
                    lay, obj, 2, "Height"),
                lambda lay: self._campo_dimensao_objeto(
                    lay, obj, 1, "Depth"),
            ])
            largura = obj.dimensions.x * 1000.0
            altura = obj.dimensions.z * 1000.0
            profundidade = obj.dimensions.y * 1000.0
        else:
            # The combined box of multiple objects has no single safe editable scale;
            # dimensions remain informational in that case.
            self._grade_medidas(
                campos, estreito, self._painel_muito_estreito(context), [
                lambda lay: self._rotulo_medida(lay, "Width", largura),
                lambda lay: self._rotulo_medida(lay, "Height", altura),
                lambda lay: self._rotulo_medida(
                    lay, "Depth", profundidade),
            ])
        self._visual_wireframe(visual, context, 'LIVRE',
                               (largura, altura, profundidade))

        # This block only appears when the object lacks the add-on signature; that is
        # why it shows Height instead of Thickness. Explain the reason and offer
        # conversion instead of leaving the user guessing.
        if (quantos == 1 and len(volumes) == 1
                and volumes[0].type == 'MESH'
                and _chapas.MARCA_CHAPA not in volumes[0]):
            aviso = b.column(align=True)
            aviso.label(text="Object has no panel signature",
                        icon='INFO')
            aviso.operator("object.cabinet_marcar", icon='MOD_SOLIDIFY')

    def _lista_espessuras(self, layout, centralizar=False):
        linha = layout.row(align=True)
        linha.alignment = 'CENTER' if centralizar else 'LEFT'
        linha.label(text="15/18/20/30")

    def desenhar_medidas(self, context, layout):
        obj = context.object

        portas = _portas._grupo_portas(obj)
        if portas is not None:
            caixa = layout.box()
            caixa.label(text="Opening: %.1f x %.1f mm" %
                        (portas['porta_vao_largura_mm'], portas['porta_vao_altura_mm']))
            caixa.label(text="%d door panel(s)" % len(_portas._folhas_portas(portas)))
            caixa.label(text="Use the Doors button at the top of the panel")
            return

        if obj is not None and _chapas.MARCA_CONJUNTO in obj:
            self._abas_modo(layout, 'GRUPO')
            b = layout.box()
            b.label(text="Cabinet (%d components)" % len(_modulos._chapas_do_conjunto(obj)), icon='MOD_BUILD')
            campos, visual, estreito = self._corpo_medidas(b, context)
            self._grade_medidas(
                campos, estreito, self._painel_muito_estreito(context), [
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_largura", "Width"),
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_altura", "Height"),
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_profundidade", "Depth"),
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_espessura", "Thickness"),
            ])
            self._lista_espessuras(campos, centralizar=estreito)
            self._visual_wireframe(
                visual, context, 'GRUPO',
                (obj.conj_largura_mm, obj.conj_altura_mm,
                 obj.conj_profundidade_mm))
            b.operator("object.cabinet_sincronizar", icon='FILE_REFRESH')
        elif obj is None or _chapas.MARCA_CHAPA not in obj:
            self._medidas_da_selecao(context, layout)
        else:
            self._abas_modo(layout, _gaveta._modo_chapa(context, obj))
            b = layout.box()
            if _gaveta._modo_chapa(context, obj) == 'INDIVIDUAL':
                campos, visual, estreito = self._corpo_medidas(
                    b, context, separador=1.0)
                self._grade_medidas(
                    campos, estreito, self._painel_muito_estreito(context), [
                    lambda lay: self._campo_medida(
                        lay, obj, "ui_chapa_largura", "Width"),
                    lambda lay: self._campo_medida(
                        lay, obj, "ui_chapa_comprimento", "Length"),
                    lambda lay: self._campo_medida(
                        lay, obj, "ui_chapa_espessura", "Thickness"),
                ])
                self._lista_espessuras(campos, centralizar=estreito)
                self._visual_wireframe(
                    visual, context, 'INDIVIDUAL',
                    (obj.chapa_largura_mm, obj.chapa_espessura_mm,
                     obj.chapa_comprimento_mm))
            else:
                b.label(text="Group: %d component(s)" % len(_modulos.grupo_de(obj)), icon='MOD_BUILD')
                sc = context.scene
                campos, visual, estreito = self._corpo_medidas(b, context)
                self._grade_medidas(
                    campos, estreito, self._painel_muito_estreito(context), [
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_largura", "Width"),
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_altura", "Height"),
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_profundidade", "Depth"),
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_espessura", "Thickness"),
                ])
                self._lista_espessuras(campos, centralizar=estreito)
                self._visual_wireframe(
                    visual, context, 'GRUPO',
                    (sc.grupo_largura_mm, sc.grupo_altura_mm,
                     sc.grupo_profundidade_mm))
                b.operator("object.cabinet_sincronizar_grupo", icon='FILE_REFRESH')

        layout.separator()
        c = layout.column(align=True)
        c.label(text="Assembly:")
        # (idname, full label, short label, icon). The short label is a CHOSEN name, not
        # a truncated full label; truncation would repeat the defect avoided by the
        # cascade above.
        botoes = (
            ("object.cabinet_agrupar", "Group Assembly", "Group",
             'OUTLINER_OB_EMPTY'),
            ("object.cabinet_detectar_adjacencia", "Detect Adjacency",
             "Adjacency", 'SNAP_ON'),
            ("object.cabinet_normalizar", "Recalculate Panels", "Recalculate",
             'FILE_REFRESH'),
        )
        largura = _gaveta._largura_painel(context)
        if sum(_gaveta._px_botao(b[2]) for b in botoes) <= largura:
            alvo, i_rotulo = c.row(align=True), 2      # Side by side.
        else:
            alvo, i_rotulo = c.column(align=True), 1   # Stacked.
        for botao in botoes:
            alvo.operator(botao[0], text=botao[i_rotulo], icon=botao[3])

    # ---------------------------------------------------- LIBRARY
    # HORIZONTAL cascade: each level is a row of buttons. The selected level turns blue
    # (depress=True, Blender's native highlight).
    def _linha_niveis(self, context, layout, nivel, valores, itens, sel,
                      pai=None):
        if not valores:
            return
        if nivel > 1:
            layout.separator(type='LINE')
        # bpy truncates labels on the RIGHT, removing the '(N)' count. Preserve the
        # count and shorten the NAME here.
        #
        # Try WRAPPING first: squeezing five buttons into a narrow sidebar left one
        # letter per label ('P (0)' for both Doors and Handles). The grid gives each
        # button more width before shortening the name.
        disponivel = _gaveta._largura_painel(context) - 16.0
        # Increase the column count only while the FULL name still fits. Dividing by the
        # number that fit made text shrink as the sidebar widened (more columns, each
        # narrower).
        maior = max(len(v) for v in valores) + 5      # Allowance for ' (NN)'.
        ideal = max(_gaveta.PX_MIN_NIVEL, maior * _gaveta.PX_CARACTERE + _gaveta.PX_FOLGA_BOTAO)
        colunas = max(1, min(len(valores), int(disponivel // ideal)))
        cabe = int((disponivel / colunas - _gaveta.PX_FOLGA_BOTAO) / _gaveta.PX_CARACTERE)
        linha = layout.grid_flow(row_major=True, columns=colunas,
                                 even_columns=True, align=True)
        for v in sorted(valores, key=str.casefold):
            if nivel == 1:
                n = _biblioteca._conta(itens, v)
            elif nivel == 2:
                n = _biblioteca._conta(itens, pai, v)
            else:
                n = _biblioteca._conta(itens, pai[0], pai[1], v)
            sufixo = " (%d)" % n
            nome = _gaveta._abreviar(v, cabe - len(sufixo))
            op = linha.operator("object.cabinet_navegar",
                                text=nome + sufixo,
                                depress=(sel == v))
            op.nivel = nivel
            op.valor = v

    def desenhar_biblioteca(self, context, layout):
        s = context.scene
        itens = _biblioteca.indice_completo()

        cab = layout.row(align=True)
        cab.prop(s, "chapa_bib_aberta",
                 icon='TRIA_DOWN' if s.chapa_bib_aberta else 'TRIA_RIGHT',
                 text="Library (%d)" % len(itens), toggle=True)
        cab.operator("object.cabinet_abrir_biblioteca", text="",
                     icon='FILE_FOLDER')
        # The '+' adds the current selection to the library.
        cab.operator("object.cabinet_salvar_biblioteca", text="", icon='ADD')
        if not s.chapa_bib_aberta:
            return

        menu = layout.box()
        self._linha_niveis(context, menu, 1, list(_biblioteca.ARVORE.keys()), itens,
                           s.chapa_n1)
        if s.chapa_n1:
            self._linha_niveis(context, menu, 2, _biblioteca._filhos_n2(s.chapa_n1),
                               itens, s.chapa_n2, pai=s.chapa_n1)
        if s.chapa_n1 and s.chapa_n2:
            self._linha_niveis(context, menu, 3,
                               _biblioteca._filhos_n3(s.chapa_n1, s.chapa_n2), itens,
                               s.chapa_n3, pai=(s.chapa_n1, s.chapa_n2))

        if not s.chapa_n1 or not s.chapa_n2:
            return
        filhos3 = _biblioteca._filhos_n3(s.chapa_n1, s.chapa_n2)
        if filhos3 and not s.chapa_n3:
            return

        daqui = []
        for it in itens:
            a, b, c = _biblioteca._niveis_de(it)
            if a == s.chapa_n1 and b == s.chapa_n2 and (not filhos3 or c == s.chapa_n3):
                daqui.append(it)
        daqui.sort(key=lambda i: (
            str(i.get("nome", "")).casefold(),
            str(i.get("arquivo", "")).casefold()))

        lista = layout.box()
        trilha = " > ".join(x for x in (s.chapa_n1, s.chapa_n2, s.chapa_n3) if x)
        # The breadcrumb ('Cabinets > Living Room > Base Units') was removed: the blue
        # cascade buttons already indicate the current location.
        self._barra_tamanho(context, lista, s)
        if not daqui:
            lista.label(text="no models here", icon='INFO')
            return

        # columns=0 lets grid_flow calculate how many columns fit the current panel
        # width: native responsive behavior. Fixed columns are only needed in mosaic
        # mode, where block width defines cell size. For a normal image, `columns=0`
        # lets bpy distribute space using its native responsive layout.
        if _biblioteca._foto_clicavel_ligada():
            colunas, _larg = _biblioteca._metrica_blocos(context, s.chapa_tam_bloco)
        else:
            colunas = 0
        grade = lista.grid_flow(row_major=True, columns=colunas,
                                even_columns=True, even_rows=True,
                                align=False)

        for it in daqui:
            icone = _biblioteca.icone_do_item(it)
            travado = _biblioteca.item_bloqueado(it)
            bloco = grade.column(align=True)

            # The image is a MOSAIC of buttons (see CLICKABLE IMAGE in `biblioteca`): it
            # scales with the selected size AND launches the placement tool from any
            # point, not only from the name.
            if icone and _biblioteca._foto_clicavel_ligada():
                self._foto_clicavel(context, bloco, it, icone)
            elif icone:
                bloco.template_icon(icon_value=icone,
                                    scale=float(s.chapa_tam_bloco))
            else:
                vazio = bloco.box()
                vazio.scale_y = float(s.chapa_tam_bloco) * 0.5
                vazio.label(text="", icon='IMAGE_DATA')

            # Two rows instead of one: putting everything together in a narrow block
            # clipped the lock, leaving no way to unlock a locked preset.
            acoes = bloco.column(align=True)

            # The name launches the PLACEMENT TOOL like the image: the preset follows
            # the cursor and the next viewport click confirms.
            op = acoes.operator("object.cabinet_arrastar_preset",
                                text=it["nome"])
            op.pasta = it["pasta"]
            op.arquivo = it["arquivo"]
            op.tipo = it.get("tipo", "modulo")

            botoes = acoes.row(align=True)
            # The arrow inserts directly at the 3D cursor without placement.
            oi = botoes.operator("object.cabinet_inserir_preset",
                                 text="", icon='IMPORT')
            oi.pasta = it["pasta"]
            oi.arquivo = it["arquivo"]
            oi.tipo = it.get("tipo", "modulo")

            # The pencil disappears when locked; the lock NEVER disappears.
            editar = botoes.row(align=True)
            editar.enabled = not travado
            oe = editar.operator(
                "object.cabinet_editar_modelo", text="", icon='GREASEPENCIL')
            oe.pasta = it["pasta"]
            oe.arquivo = it["arquivo"]
            self._cadeado(botoes, it, travado)

    def _foto_clicavel(self, context, layout, it, icone):
        """Button mosaic displaying the image: clicking anywhere launches placement,
        just like clicking the name."""
        s = context.scene
        png = os.path.splitext(it["arquivo"])[0] + ".png"
        # Tile size is FIXED; only the tile count varies.
        _col, largura_bloco = _biblioteca._metrica_blocos(context, s.chapa_tam_bloco)
        lado = max(2, int(round(
            (largura_bloco - _biblioteca.PADDING_BLOCO) / _biblioteca.PX_ALVO_CELULA)))
        tiles = _biblioteca._tiles_foto(it["pasta"], png, lado)
        if not tiles:
            # Without tiles, the image still appears but is not clickable.
            layout.template_icon(icon_value=icone,
                                 scale=float(s.chapa_tam_bloco))
            return

        # Cells larger than icons leave gaps, turning the mosaic into a checkerboard.
        # `ui_units_x` fixes row width in UI units (20 px each), giving every tile
        # exactly the icon size without needing the block grid's column count. scale_y
        # closes the top gap. Cell width is block width/side count. If it exceeds the 16
        # px icon, each column leaves a gap and the image becomes striped. scale_x
        # shrinks the cell to the icon; when the cell becomes SMALLER, the icon shrinks
        # with it, leaving no gap.
        grade = layout.column(align=True)
        grade.scale_y = _biblioteca.PX_TILE_FOTO / 20.0
        for linha_tiles in tiles:
            linha = grade.row(align=True)
            for icon_id in linha_tiles:
                op = linha.operator("object.cabinet_arrastar_preset",
                                    text="", emboss=False,
                                    icon_value=icon_id)
                op.pasta = it["pasta"]
                op.arquivo = it["arquivo"]
                op.tipo = it.get("tipo", "modulo")

    def _barra_tamanho(self, context, layout, s):
        """Compact bar of clickable slices (see SIZE BAR in `biblioteca`).

        RESERVE width with a split instead of relying on alignment: with
        `alignment='RIGHT'`, the button's natural width greatly exceeds the icon
        width and the track becomes dashed. Compressing enough to close the gaps
        blurred the drawing."""
        prop = bpy.types.Scene.bl_rna.properties["chapa_tam_bloco"]
        menor, maior = prop.hard_min, prop.hard_max
        ultimo = maior - menor
        ativo = max(0, min(ultimo, int(s.chapa_tam_bloco) - menor))

        fatias, _celula, _c = _biblioteca._metrica_barra(context)
        util = _biblioteca.PX_FATIA_BARRA * fatias
        largura = max(1.0, _gaveta._largura_painel(context))
        # The remaining space on the left is empty: push the bar into the corner.
        fracao = max(0.02, min(0.92, 1.0 - (util + _biblioteca.PX_BOTAO_BIBLIOTECA)
                               / largura))
        div = layout.split(factor=fracao)
        div.label(text="")
        direita = div.row(align=True)

        linha = direita.row(align=True)
        linha.scale_x = _biblioteca._metrica_barra(context, util)[2]
        for i in range(fatias):
            op = linha.operator(
                "object.cabinet_tamanho", text="", emboss=False,
                icon_value=_biblioteca._icone_fatia_barra(i, ativo, ultimo))
            op.valor = menor + i
        direita.operator("object.cabinet_asset_browser", text="",
                         icon='ASSET_MANAGER')

    def _cadeado(self, linha, it, travado):
        """Clickable lock toggling between the two sprites."""
        oc = linha.operator("object.cabinet_bloqueio", text="",
                            icon='LOCKED' if travado else 'UNLOCKED',
                            depress=travado)
        oc.pasta = it["pasta"]
        oc.arquivo = it["arquivo"]
