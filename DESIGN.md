# DESIGN.md — como desenhar UI no Cabinet Creator

> **REGRA DESTE ARQUIVO:** NAO pode passar de 200 linhas.
>
> **LEIA ANTES DE:** criar tela, botao, campo, secao, icone ou qualquer
> coisa visivel do add-on. Vale para humano e para IA.
>
> Travado por `tests/test_estrutura_blender.py`. Se um teste de la'
> falhar, a leitura correta e' "isto era de proposito, confirme antes
> de mudar" — nunca "conserte o teste".

## 1. A gaveta NAO e' um painel do Blender

A UI do add-on vive numa **area `VIEW_3D` propria**, criada com
`screen.area_split` a esquerda, com header, toolbar, regiao N e
overlays todos desligados. Dentro dela nao existe `UILayout`: cada
pixel e' desenhado por GPU num handler `POST_PIXEL`.

Consequencia direta: **nada de `layout.prop`, `layout.operator`,
`row()`, `column()`, `grid_flow`, `ui_units_x`, `scale_x`** — essas
APIs nao existem aqui. Quem vier do painel N legado
(`VIEW3D_PT_cabinet_creator`, no arquivo mas NAO registrado) vai
tentar usa-las por reflexo.

Em troca, some a limitacao mais irritante do painel N: aqui
`blf.dimensions()` **mede texto de verdade**. Nao estime largura de
string com constantes `PX_*` — isso era remendo do UILayout.

## 2. As tres camadas

Nesta ordem. Misturar duas na mesma funcao e' o erro mais comum.

| Camada | Funcao | Responsabilidade |
|---|---|---|
| Layout | `_widgets_gaveta` | decide ONDE cada coisa fica |
| Desenho | `_desenhar_gaveta` | pinta o que o layout decidiu |
| Evento | `OBJECT_OT_interagir_gaveta` | despacha o clique |

`_widgets_gaveta(context, largura, altura)` devolve tuplas de
**exatamente 6 elementos**: `(x, y, w, h, rotulo, acao)`. `x`/`y` em
pixels da regiao, origem embaixo a esquerda; `acao` e' `None`
(decorativo) ou uma tupla cujo `[0]` e' o **verbo**.

O layout e' **puro**: nao desenha, nao le evento, nao escreve em
`bpy.data`. Por isso da' para testa-lo sem abrir janela.

## 3. Receita para acrescentar um widget

1. Em `_widgets_gaveta`, faca `itens.append((x, y, w, h, rotulo, acao))`
   e desca `y` pela altura mais o respiro (ver secao 4).
2. Use um **verbo ja' existente** se couber. Verbo novo precisa entrar
   em `VERBOS` no teste de estrutura, que existe para te obrigar a
   confirmar que nao e' duplicata — e em `_chave_widget`, se acender.
3. Em `_desenhar_gaveta`, trate o verbo no laco. Sem tratamento ele
   cai no `_botao_gaveta` generico, que costuma bastar.
4. Em `OBJECT_OT_interagir_gaveta`, trate o clique. Verbo decorativo
   entra na lista que retorna `{'FINISHED'}` sem agir.
5. Precisa de icone? Secao 7.

## 4. Metricas

Nao invente numero novo: reaproveite a linha mais parecida.

| Elemento | Altura | Passo em `y` |
|---|---|---|
| Aba (Modulos/Portas) | 29 | topo em `altura - 40` |
| Aba de modo (Individual/Grupo) | 25 | 33 |
| Campo de medida | 37 | 43 |
| Botao de operador | 28 | 34 |
| Titulo de secao | 23 | 31 |
| Linha da cascata | 25 | 39 |
| Rodape (Chapa/Auto/nome) | 26 | 29 quebrando, 35 no fim |
| Separador | 1 | desenhado em `y + 31.5` |

Margem lateral `x = 12`, `w = max(24, min(540, largura - 24))`.
Respiro entre itens da mesma linha **6 px** (4 na cascata). Raio de
canto **4** no botao e **3** no preenchimento. Miniatura de preset:
`w - 10 == h - 27` (a faixa do nome e' 27).

## 5. Cor e tipografia sempre do tema

`_cores_gaveta()` devolve `(wcol_regular, fundo)` do tema do usuario.
Use `cores.inner`, `cores.inner_sel`, `cores.outline`, `cores.text`.

**Nunca escreva uma cor literal:** o add-on acompanha o tema claro e o
escuro. Cores cruas ja' foram removidas uma vez da alca.

Texto: `_texto_gaveta` para rotulo fixo, `_texto_cabivel_gaveta` para
qualquer texto que possa nao caber — ele reduz a fonte de 12 ate' 9 e
so' entao corta com reticencias.

Ao abreviar rotulo com contagem, use `_abreviar` **so' no nome**:
`Armarios (3)` vira `arm (3)`, nunca `Armarios (`.

## 6. Responsividade

A largura util e' dividida por `ui_scale` antes de decidir o layout.
Os cortes sao por **largura logica**:

| Largura logica | Campos de medida |
|---|---|
| >= 480 px | uma linha, todos lado a lado |
| >= 240 px | duas colunas |
| < 240 px | coluna unica |

Botoes de Montagem: `colunas = min(3, max(1, w // 36))`.

A gaveta **para de crescer em 564 px** (`_LARGURA_MAX_GAVETA`): texto
em coluna larga fica ilegivel e a miniatura vira faixa. Como
`Area.width` e' somente leitura, quem corrige e' o timer
`_limitar_largura_gaveta`, **depois** do resize — nunca um modal.

Regra de ouro, verificada por teste: nenhum widget pode terminar fora
de `min(largura - 12, 552)`.

## 7. Icones vem do GizmoGroup, nao da GPU

GPU desenha retangulo e texto. **Nao desenha icone do tema.** Para ter
um icone nativo, `VIEW3D_GGT_cabinet_gaveta.draw_prepare` cria um
`GIZMO_GT_button_2d` posicionado em cima do retangulo, e
`_icone_acao_gaveta(acao)` diz qual icone o verbo usa.

O retangulo vem do layout e o icone vem do gizmo: os dois precisam
concordar na posicao. Icone deslocado costuma ser `matrix_basis` em
`draw_prepare`, nao o layout.

## 8. Grid de medidas na cena

Passar o mouse num campo de medida (ou abri-lo para edicao) desenha a
caixa envolvente do alvo **na viewport vizinha** e acende as quatro
arestas do eixo daquele campo. Tres partes que precisam concordar:

1. `EIXOS_MEDIDA[modo][rotulo]` diz qual eixo o campo move. Rotulo sem
   entrada aqui nao acende nada.
2. `_caixa_da_medida` monta os 8 cantos. Em `INDIVIDUAL` a caixa e'
   **orientada pela chapa**: girada, a Espessura dela nao e' a vertical
   do mundo. Nos outros modos e' alinhada ao mundo.
3. `_desenhar_grid_medidas`, handler **`POST_VIEW`** — a caixa vive em
   coordenada de mundo, junto da cena.

O hover vem de `VIEW3D_GT_campo_gaveta`, um Gizmo invisivel por
widget, pelo mesmo motivo da alca (secao 9).

**O glow vale para QUALQUER botao**, nao so' os campos de medida.
`_chave_widget(acao)` da' a identidade de cada um (None = decoracao,
nao acende) e `_glow_gaveta` pinta o halo -- a mesma funcao da alca,
nunca uma copia. Duas regras aprendidas na marra:

- O halo vai **antes** do corpo do botao. Por cima, ele lava o texto.
- `_glow_gaveta` liga o **proprio** `blend_set('ALPHA')`, porque
  `blf.draw` deixa o estado alterado e o halo sai OPACO a partir do
  segundo widget. Vale para todo desenho seu com alfa apos um texto.

Widget com icone tem dois gizmos sobrepostos: o do icone (tooltip e
clique) e o retangular (hover). O retangular exclui o disco do icone,
para nao roubar o pick; o glow soma os dois `is_highlight`.

## 9. Nunca faca

- **Cor literal** no lugar do tema (secao 5).
- **Operador modal persistente** para capturar clique: roubaria evento
  de outros add-ons. Use Gizmo + `test_select` (a alca e' o modelo).
  Modal so' para interacao transitoria — arraste de slider, edicao de
  campo — que termina sozinha.
- **Deixar estado de GPU ligado**, ou supor o estado que veio de
  antes. Todo caminho de saida de `_desenhar_gaveta` fecha com
  `blend_set('NONE')`, e quem desenha com alfa liga o seu.
- **Desenhar a mesma coisa em dois lugares.** O Gizmo da alca tem
  `draw()` vazio de proposito: quem pinta e' o `POST_PIXEL`. Dois
  desenhos = alca dobrada.
- **Duplicar geometria entre desenho e hit-test** — ha' teste disso.
- **Estimar largura de texto.** Use `blf.dimensions()`.

## 10. Antes de entregar

1. Rodar as tres suites de `tests/` (ver CLAUDE.md).
2. Conferir em **tres larguras**: 190, 320 e 564. Bug de layout quase
   sempre so' aparece num extremo.
3. Conferir no tema claro e no escuro.
4. Incrementar `bl_info["version"]`.

Captura vale mais que leitura de codigo aqui:
`bpy.ops.screen.screenshot()` num Blender de verdade pega o que o
teste nao pega — halo opaco, texto cortado, icone fora do lugar.

## 11. Alternativas ja' avaliadas e RECUSADAS

Nao reabrir sem falar com o dono do projeto.

- **Overlay na viewport principal** (jeito do BlenderKit). Recusado:
  passaria a dividir pilha de evento, estado de GPU e o canto superior
  esquerdo com outros add-ons. A area propria e' imune aos tres. O
  ganho seria nao ocupar espaco de tela — insuficiente.
- **Pop-up / `invoke_props_dialog`**. Recusado: popup fecha quando o
  mouse sai, e clicar na viewport e' exatamente a acao seguinte do
  posicionador de preset. Nao existe popup fixo no bpy.
- **Voltar ao painel N com `UILayout`**. Recusado: o handler de UI come
  o evento antes de qualquer keymap, o icone de botao nao passa de
  16 px, e nao da' para fixar largura em pixels de elemento nenhum.
  Foi o que motivou a gaveta.
