"""Painel N legado (fora de CLASSES de proposito)."""

import bpy, os
from bpy.types import Panel

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _modulos = _biblioteca = _portas = _gaveta = None

class VIEW3D_PT_cabinet_creator(Panel):
    # O cabecalho e' a barra de abas; nao repetir um titulo ao lado dela.
    bl_label = ""
    bl_idname = "VIEW3D_PT_cabinet_creator"
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
        caixa.label(text="Portas parametricas")
        grupo = _portas._grupo_portas(context.object)
        if grupo is not None and context.mode == 'OBJECT':
            op = caixa.operator("object.cabinet_portas", text="Configurar Portas",
                                icon='PREFERENCES')
            op.editar = True
        else:
            caixa.label(text="2 vertices diagonais do vao interno")
            linha = caixa.row()
            linha.enabled = context.mode == 'EDIT_MESH'
            op = linha.operator("object.cabinet_portas", text="Criar Portas",
                                icon='MESH_CUBE')
            op.editar = False
            if context.mode != 'EDIT_MESH':
                caixa.label(text="Selecione as chapas e entre em Edicao")

    # ------------------------------------------------------- MEDIDAS
    def _abas_modo(self, layout, ativo):
        linha = layout.row(align=True)
        for modo, texto in (('INDIVIDUAL', "Individual"), ('GRUPO', "Grupo")):
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
        """Escala responsiva com limites para nao sumir nem dominar o painel."""
        disponivel = max(0.0, self._largura_logica(context) - 24.0)
        escala = disponivel / 20.0
        maximo = (_biblioteca.WIREFRAME_ESCALA_ESTREITA_MAX_UI
                  if self._painel_estreito(context)
                  else _biblioteca.WIREFRAME_ESCALA_MAX_UI)
        return max(_biblioteca.WIREFRAME_ESCALA_MIN_UI,
                   min(maximo, escala))

    def _corpo_medidas(self, caixa, context, separador=0.4):
        """Retorna controles e area visual, em linha ou empilhados."""
        estreito = self._painel_estreito(context)
        corpo = (caixa.column(align=True) if estreito
                 else caixa.row(align=False))
        if not estreito:
            # Afasta os controles da quina do box sem deslocar o preview.
            corpo.separator(factor=0.35)
        campos = corpo.column(align=True)
        # No modo estreito, toda a grade precisa usar o centro do box. Manter
        # este contêiner em LEFT faz o Blender compactar a largura útil pelo
        # tamanho natural dos widgets, deixando uma sobra maior à direita.
        campos.alignment = 'CENTER' if estreito else 'LEFT'
        if not estreito:
            # Reserva somente o necessario para rotulos e caixas. Uma coluna
            # maior comprime o preview na area direita antes da quebra.
            campos.ui_units_x = _biblioteca.MEDIDAS_LARGURA_CONTROLES_UI
        campos.separator(factor=0.15 if estreito else separador)
        return campos, corpo, estreito

    def _grade_medidas(self, layout, estreito, coluna_unica, desenhadores):
        """Quebra a grade em duas colunas ou uma coluna no limite estreito."""
        if not estreito:
            for desenhar in desenhadores:
                desenhar(layout)
            return

        def desenhar_no_centro(desenhar, ocupacao=0.5):
            """Cria uma faixa central com margens laterais simetricas."""
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
                # Sem largura fixa: as duas celulas dividem o espaco por
                # igual e o centro nao deriva para a esquerda ao comprimir.
                # `split` garante duas metades reais do espaco disponivel.
                # Duas `column` dentro de uma `row` podem ser compactadas pelo
                # Blender conforme a largura natural dos campos.
                linha = layout.split(factor=0.5, align=False)
                for desenhar in par:
                    celula = linha.column(align=True)
                    celula.alignment = 'CENTER'
                    desenhar(celula)
            else:
                desenhar_no_centro(par[0])

    def _visual_wireframe(self, layout, context, modo, medidas):
        """Desenha o preview responsivo entre os limites visualmente uteis."""
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
        """Rotulo completo acima e campo compacto logo abaixo."""
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
        """Versao so'-leitura do campo: selecao livre nao tem prop."""
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
        """Dimensao nativa editavel; aceita mm, cm e m como o Blender."""
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
        """Caixa de QUALQUER selecao -- cubo, carro, curvas, o que for."""
        m = _modulos.medir_selecao(context)
        if m is None:
            layout.label(text="Selecione uma chapa, um modulo ou "
                              "qualquer objeto", icon='INFO')
            return
        largura, altura, profundidade, quantos = m
        b = layout.box()
        b.label(text="Selecao (%d objeto%s)"
                     % (quantos, "" if quantos == 1 else "s"),
                icon='SHADING_BBOX')
        # Tres medidas ocupam menos altura que o preview maximo; a margem
        # superior maior centraliza o bloco e o afasta da quina do box.
        campos, visual, estreito = self._corpo_medidas(
            b, context, separador=1.2)
        volumes = [o for o in context.selected_objects
                   if o.type in _modulos.TIPOS_COM_VOLUME]
        if quantos == 1 and len(volumes) == 1:
            obj = volumes[0]
            # Convencao do add-on: largura=X, altura=Z, profundidade=Y.
            self._grade_medidas(
                campos, estreito, self._painel_muito_estreito(context), [
                lambda lay: self._campo_dimensao_objeto(
                    lay, obj, 0, "Largura"),
                lambda lay: self._campo_dimensao_objeto(
                    lay, obj, 2, "Altura"),
                lambda lay: self._campo_dimensao_objeto(
                    lay, obj, 1, "Profundidade"),
            ])
            largura = obj.dimensions.x * 1000.0
            altura = obj.dimensions.z * 1000.0
            profundidade = obj.dimensions.y * 1000.0
        else:
            # A caixa conjunta de varios objetos nao tem uma unica escala
            # segura para editar; nesse caso as medidas continuam informativas.
            self._grade_medidas(
                campos, estreito, self._painel_muito_estreito(context), [
                lambda lay: self._rotulo_medida(lay, "Largura", largura),
                lambda lay: self._rotulo_medida(lay, "Altura", altura),
                lambda lay: self._rotulo_medida(
                    lay, "Profundidade", profundidade),
            ])
        self._visual_wireframe(visual, context, 'LIVRE',
                               (largura, altura, profundidade))

        # Este bloco so' aparece quando o objeto NAO tem a assinatura do
        # add-on -- e' por isso que ele mostra Altura no lugar de
        # Espessura. Em vez de deixar o usuario adivinhando, diz o
        # motivo e oferece a conversao.
        if (quantos == 1 and len(volumes) == 1
                and volumes[0].type == 'MESH'
                and _chapas.MARCA_CHAPA not in volumes[0]):
            aviso = b.column(align=True)
            aviso.label(text="Objeto sem assinatura de chapa",
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
            caixa.label(text="Vao: %.1f x %.1f mm" %
                        (portas['porta_vao_largura_mm'], portas['porta_vao_altura_mm']))
            caixa.label(text="%d folha(s)" % len(_portas._folhas_portas(portas)))
            caixa.label(text="Use o botao Portas no topo do painel")
            return

        if obj is not None and _chapas.MARCA_CONJUNTO in obj:
            self._abas_modo(layout, 'GRUPO')
            b = layout.box()
            b.label(text="Modulo (%d pecas)" % len(_modulos._chapas_do_conjunto(obj)), icon='MOD_BUILD')
            campos, visual, estreito = self._corpo_medidas(b, context)
            self._grade_medidas(
                campos, estreito, self._painel_muito_estreito(context), [
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_largura", "Largura"),
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_altura", "Altura"),
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_profundidade", "Profundidade"),
                lambda lay: self._campo_medida(
                    lay, obj, "ui_conj_espessura", "Espessura"),
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
                        lay, obj, "ui_chapa_largura", "Largura"),
                    lambda lay: self._campo_medida(
                        lay, obj, "ui_chapa_comprimento", "Comprimento"),
                    lambda lay: self._campo_medida(
                        lay, obj, "ui_chapa_espessura", "Espessura"),
                ])
                self._lista_espessuras(campos, centralizar=estreito)
                self._visual_wireframe(
                    visual, context, 'INDIVIDUAL',
                    (obj.chapa_largura_mm, obj.chapa_espessura_mm,
                     obj.chapa_comprimento_mm))
            else:
                b.label(text="Grupo: %d peca(s)" % len(_modulos.grupo_de(obj)), icon='MOD_BUILD')
                sc = context.scene
                campos, visual, estreito = self._corpo_medidas(b, context)
                self._grade_medidas(
                    campos, estreito, self._painel_muito_estreito(context), [
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_largura", "Largura"),
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_altura", "Altura"),
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_profundidade", "Profundidade"),
                    lambda lay: self._campo_medida(
                        lay, sc, "ui_grupo_espessura", "Espessura"),
                ])
                self._lista_espessuras(campos, centralizar=estreito)
                self._visual_wireframe(
                    visual, context, 'GRUPO',
                    (sc.grupo_largura_mm, sc.grupo_altura_mm,
                     sc.grupo_profundidade_mm))
                b.operator("object.cabinet_sincronizar_grupo", icon='FILE_REFRESH')

        layout.separator()
        c = layout.column(align=True)
        c.label(text="Montagem:")
        # (idname, rotulo inteiro, rotulo curto, icone). O curto e' um
        # nome ESCOLHIDO, nao o inteiro truncado -- cortar seria o mesmo
        # defeito que a cascata acima evita.
        botoes = (
            ("object.cabinet_agrupar", "Agrupar Conjunto", "Agrupar",
             'OUTLINER_OB_EMPTY'),
            ("object.cabinet_detectar_adjacencia", "Detectar Adjacencia",
             "Adjacencia", 'SNAP_ON'),
            ("object.cabinet_normalizar", "Recalcular Chapas", "Recalcular",
             'FILE_REFRESH'),
        )
        largura = _gaveta._largura_painel(context)
        if sum(_gaveta._px_botao(b[2]) for b in botoes) <= largura:
            alvo, i_rotulo = c.row(align=True), 2      # lado a lado
        else:
            alvo, i_rotulo = c.column(align=True), 1   # empilhado
        for botao in botoes:
            alvo.operator(botao[0], text=botao[i_rotulo], icon=botao[3])

    # ---------------------------------------------------- BIBLIOTECA
    # Cascata HORIZONTAL: cada nivel e' uma linha de botoes. O nivel
    # selecionado fica azul (depress=True, o destaque nativo do Blender).
    def _linha_niveis(self, context, layout, nivel, valores, itens, sel,
                      pai=None):
        if not valores:
            return
        if nivel > 1:
            layout.separator(type='LINE')
        # O bpy corta o rotulo pela DIREITA, comendo justamente o "(N)".
        # Por isso a conta e' preservada e o NOME e' encurtado aqui.
        #
        # Antes de encurtar, porem, vale QUEBRAR A LINHA: espremer cinco
        # botoes numa sidebar estreita sobrava uma letra para cada um
        # ("P (0)" para Portas e Puxadores). A grade da mais largura a
        # cada botao e so' entao o nome e' resumido.
        disponivel = _gaveta._largura_painel(context) - 16.0
        # O numero de colunas so' cresce enquanto o nome INTEIRO ainda
        # couber. Repartir por quantos cabem deixava o texto encolher ao
        # alargar a sidebar (mais colunas, cada uma mais estreita).
        maior = max(len(v) for v in valores) + 5      # folga do " (NN)"
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
                 text="Biblioteca (%d)" % len(itens), toggle=True)
        cab.operator("object.cabinet_abrir_biblioteca", text="",
                     icon='FILE_FOLDER')
        # o "+" adiciona a selecao atual a biblioteca
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
        # a trilha ("Armarios > Sala > Inferiores") saiu: os proprios
        # botoes da cascata, em azul, ja' dizem onde se esta'
        self._barra_tamanho(context, lista, s)
        if not daqui:
            lista.label(text="nenhum modelo aqui", icon='INFO')
            return

        # columns=0 faz o grid_flow calcular sozinho quantas colunas cabem
        # na largura atual do painel -- e' o mecanismo responsivo nativo.
        # As colunas so' precisam ser fixas no modo mosaico, onde a
        # largura do bloco define o tamanho da celula. Na foto normal
        # `columns=0` deixa o bpy distribuir, que e' o comportamento
        # responsivo nativo.
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

            # A foto e' um MOSAICO de botoes (ver FOTO CLICAVEL em
            # `biblioteca`): assim
            # ela cresce com o tamanho escolhido E aciona o posicionador
            # em qualquer ponto, nao so' pelo nome.
            if icone and _biblioteca._foto_clicavel_ligada():
                self._foto_clicavel(context, bloco, it, icone)
            elif icone:
                bloco.template_icon(icon_value=icone,
                                    scale=float(s.chapa_tam_bloco))
            else:
                vazio = bloco.box()
                vazio.scale_y = float(s.chapa_tam_bloco) * 0.5
                vazio.label(text="", icon='IMAGE_DATA')

            # Duas linhas em vez de uma: no bloco estreito tudo junto
            # cortava o cadeado, e sem ele um preset travado nao teria
            # como ser destravado.
            acoes = bloco.column(align=True)

            # O nome chama o POSICIONADOR, igual a foto: o preset gruda
            # no cursor e o proximo clique na viewport confirma.
            op = acoes.operator("object.cabinet_arrastar_preset",
                                text=it["nome"])
            op.pasta = it["pasta"]
            op.arquivo = it["arquivo"]
            op.tipo = it.get("tipo", "modulo")

            botoes = acoes.row(align=True)
            # a seta insere direto no cursor 3D, sem posicionar
            oi = botoes.operator("object.cabinet_inserir_preset",
                                 text="", icon='IMPORT')
            oi.pasta = it["pasta"]
            oi.arquivo = it["arquivo"]
            oi.tipo = it.get("tipo", "modulo")

            # o lapis some com o cadeado fechado, o cadeado NUNCA some
            editar = botoes.row(align=True)
            editar.enabled = not travado
            oe = editar.operator(
                "object.cabinet_editar_modelo", text="", icon='GREASEPENCIL')
            oe.pasta = it["pasta"]
            oe.arquivo = it["arquivo"]
            self._cadeado(botoes, it, travado)

    def _foto_clicavel(self, context, layout, it, icone):
        """Mosaico de botoes com a foto: clicar em qualquer ponto
        aciona o posicionador, igual ao nome."""
        s = context.scene
        png = os.path.splitext(it["arquivo"])[0] + ".png"
        # o ladrilho tem tamanho FIXO: quem varia e' a quantidade deles
        _col, largura_bloco = _biblioteca._metrica_blocos(context, s.chapa_tam_bloco)
        lado = max(2, int(round(
            (largura_bloco - _biblioteca.PADDING_BLOCO) / _biblioteca.PX_ALVO_CELULA)))
        tiles = _biblioteca._tiles_foto(it["pasta"], png, lado)
        if not tiles:
            # sem os ladrilhos a foto ainda aparece, so' que nao clicavel
            layout.template_icon(icon_value=icone,
                                 scale=float(s.chapa_tam_bloco))
            return

        # Celula maior que o icone deixa fresta e o mosaico vira
        # xadrez. `ui_units_x` fixa a largura da linha em unidades de
        # UI (20 px cada), entao cada ladrilho recebe exatamente o
        # tamanho do icone -- sem precisar saber quantas colunas a
        # grade de blocos resolveu usar. scale_y fecha a fresta de cima.
        # A celula vale largura_do_bloco/lado. Se ela sobrar sobre o
        # icone de 16 px, fica uma fresta por coluna e a foto ganha
        # listras. scale_x encolhe a celula ate' o icone -- e quando a
        # celula fica MENOR que ele, o icone acompanha, sem fresta.
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
        """Barra compacta de fatias clicaveis (ver BARRA DE TAMANHO em
        `biblioteca`).

        A largura e' RESERVADA por um split em vez de deixada ao
        alinhamento: com `alignment='RIGHT'` o botao assume uma largura
        natural bem maior que o icone e o trilho sai tracejado, e
        comprimir o bastante para fechar os vaos borrava o desenho.
        """
        prop = bpy.types.Scene.bl_rna.properties["chapa_tam_bloco"]
        menor, maior = prop.hard_min, prop.hard_max
        ultimo = maior - menor
        ativo = max(0, min(ultimo, int(s.chapa_tam_bloco) - menor))

        fatias, _celula, _c = _biblioteca._metrica_barra(context)
        util = _biblioteca.PX_FATIA_BARRA * fatias
        largura = max(1.0, _gaveta._largura_painel(context))
        # o que sobra a esquerda e' so' vao: joga a barra no canto
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
        """Cadeado clicavel, alternando entre os dois sprites."""
        oc = linha.operator("object.cabinet_bloqueio", text="",
                            icon='LOCKED' if travado else 'UNLOCKED',
                            depress=travado)
        oc.pasta = it["pasta"]
        oc.arquivo = it["arquivo"]
