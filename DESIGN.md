# DESIGN.md — como desenhar UI no Cabinet Creator

> **REGRA DESTE ARQUIVO:** NAO pode passar de 200 linhas.
>
> **LEIA ANTES DE:** criar tela, botao, campo, secao, icone ou
> qualquer coisa visivel. Vale para humano e para IA. Travado por
> `tests/test_estrutura_blender.py`: teste de la' que falha quer dizer
> "isto era de proposito, confirme antes de mudar", nunca "conserte o
> teste".

## 1. A gaveta NAO e' um painel do Blender

A UI vive numa **area `VIEW_3D` propria** (`screen.area_split` a
esquerda), com header, toolbar, regiao N e overlays desligados. Nao
existe `UILayout` la' dentro: cada pixel e' desenhado por GPU num
handler `POST_PIXEL`.

Consequencia direta: **nada de `layout.prop`, `layout.operator`,
`row()`, `column()`, `grid_flow`, `ui_units_x`, `scale_x`** — essas
APIs nao existem aqui. Quem vier do painel N legado
(`VIEW3D_PT_cabinet_creator`, no arquivo mas NAO registrado) vai
tentar usa-las por reflexo.

Em troca, aqui `blf.dimensions()` **mede texto de verdade**: nao
estime largura com constantes `PX_*`, isso era remendo do UILayout.

## 2. As tres camadas

| Camada | Funcao | Responsabilidade |
|---|---|---|
| Layout | `_widgets_gaveta` | decide ONDE cada coisa fica |
| Desenho | `_desenhar_gaveta` | pinta o que o layout decidiu |
| Evento | `OBJECT_OT_interagir_gaveta` | despacha o clique |

`_widgets_gaveta(context, largura, altura)` devolve tuplas de
**exatamente 6 elementos**: `(x, y, w, h, rotulo, acao)`. `x`/`y` em
pixels da regiao, origem embaixo a esquerda; `acao` e' `None`
(decorativo) ou uma tupla cujo `[0]` e' o **verbo**. O layout nao
desenha nem le evento — da' para testa-lo sem abrir janela. Misturar
duas camadas na mesma funcao e' o erro mais comum aqui.

## 3. Receita para acrescentar um widget

1. Em `_widgets_gaveta`, `itens.append(...)` e desca `y` pela altura
   mais o respiro (secao 4).
2. Use um **verbo ja' existente** se couber. Verbo novo entra em
   `VERBOS` no teste de estrutura — que existe para te obrigar a
   confirmar que nao e' duplicata — e em `_chave_widget`, se acender.
3. Em `_desenhar_gaveta`, trate o verbo no laco; sem tratamento ele
   cai no `_botao_gaveta` generico, que costuma bastar.
4. Em `OBJECT_OT_interagir_gaveta`, trate o clique. Verbo decorativo
   entra na lista que retorna `{'FINISHED'}` sem agir.

## 4. Metricas

| Elemento | Altura | Passo em `y` |
|---|---|---|
| Aba (Modulos/Portas) | 29 | topo em `altura - 40` |
| Aba de modo / segmento | 25 | 33 / 29 |
| Campo de medida | 37 | 43 |
| Botao de operador | 28 | 34 |
| Titulo de secao / rotulo | 23 / 20 | 31 / 26 |
| Linha da cascata | 25 | 39 |

Margem lateral `x = 12`, `w = max(24, min(540, largura - 24))`; 6 px
entre itens da mesma linha (4 na cascata); raio 4 no botao e 3 no
preenchimento; miniatura de preset `w - 10 == h - 27`; separador de
1 px em `y + 31.5`. Nao invente numero novo: reaproveite a linha mais
parecida.

## 5. Cor e tipografia sempre do tema

`_cores_gaveta()` devolve `(wcol_regular, fundo)` do tema do usuario:
`cores.inner`, `cores.inner_sel`, `cores.outline`, `cores.text`.
**Nunca escreva uma cor literal** — o add-on acompanha o tema claro e
o escuro, e cores cruas ja' foram removidas uma vez da alca.

Texto: `_texto_gaveta` para rotulo fixo, `_texto_cabivel_gaveta` para
o que possa nao caber (reduz a fonte de 12 a 9 antes de cortar).

Ao abreviar rotulo com contagem, use `_abreviar` **so' no nome**:
`Armarios (3)` vira `arm (3)`, nunca `Armarios (`.

## 6. Responsividade

Largura util dividida por `ui_scale`; os cortes sao por **largura
logica**:

| Largura logica | Campos de medida |
|---|---|
| >= 480 px | uma linha, todos lado a lado |
| >= 240 px | duas colunas |
| < 240 px | coluna unica |

Botoes de Montagem: `colunas = min(3, max(1, w // 36))`. A gaveta
**abre na menor largura com L/A/P na mesma linha**
(`LARGURA_MEDIDAS_EM_LINHA` x escala + 2, `_largura_inicial_gaveta`;
teto de metade da viewport) e **para de crescer em 564 px**
(`_LARGURA_MAX_GAVETA`, nunca abaixo da inicial): texto
em coluna larga fica ilegivel e a miniatura vira faixa. Como
`Area.width` e' somente leitura, quem corrige e' o timer
`_limitar_largura_gaveta`, **depois** do resize — nunca um modal.
Regra de ouro, com teste: widget nenhum termina fora de
`min(largura - 12, 552)`.

**Dois paineis** (pedido do usuario, como Outliner | Properties): a aba
em cima, a **biblioteca fixa embaixo** nas tres abas, sempre aberta.
Entre eles o widget `divisa` (`_paineis_gaveta` corta o conteudo nele):
nasce na metade (`DIVISA_PADRAO`), guarda FRACAO em
`screen['cabinet_gaveta_divisa']` e deixa `ALTURA_MIN_PAINEL_GAVETA` a
cada lado. Perto dela: halo, pega e cursor MOVE_Y; arrastar = modal
transitorio (Esc desfaz). Cada painel tem rolagem propria (a roda rola
o que esta' sob o mouse) e e' recortado por `scissor`; o carrossel
recorta na INTERSECAO com o painel. Widget cortado recebe clique so'
na parte visivel (`_recortar_ao_painel`); icone e slider so' inteiros.
Exigir o widget inteiro deixou a foto do preset morta a 633 px.

## 7. Icones vem do GizmoGroup, nao da GPU

GPU desenha retangulo e texto, **nao icone do tema**. Para um icone
nativo, `draw_prepare` cria um `GIZMO_GT_button_2d` em cima do
retangulo e `_icone_acao_gaveta(acao)` diz qual usar; icone deslocado
costuma ser `matrix_basis`, nao o layout.

## 8. HUD parametrica na viewport

A representacao do armario agora vive na viewport principal: `gpu`
em `POST_VIEW` desenha os contornos e `blf` em `POST_PIXEL` as letras.
O mini-wireframe da gaveta foi descontinuado; os campos continuam nela.
A HUD e seus eventos so' funcionam em Object Mode. Clique seleciona o
modulo; duplo clique na mesma chapa isola essa chapa. Shift soma, como
no Blender (`_somar_peca`): Shift+clique soma o grupo inteiro, ou so' a
chapa se o grupo dela ja' esta' em selecao individual (Shift+clique na
chapa ativa a tira); Shift+duplo isola a chapa DENTRO da selecao -- o
resto do grupo dela sai, os outros grupos/chapas ficam. A HUD mostra
TODOS os itens da selecao, sem ordem de hierarquia (`_itens_da_selecao`:
modulo com o Empty selecionado = grupo; outra chapa = individual), e
setas e quinas valem em qualquer um deles (`_acertar_hud` pega o mais
perto do mouse; so' o item do alvo acende). Grupo mostra
L/A/P; E aparece SOMENTE na chapa individual, inclusive ao passar nas
faces estreitas. Espessura do modulo fica no menu lateral.
`_geometria_hud` alimenta desenho e hit-test: hover em uma aresta acende
as quatro do eixo; o contorno da porta e o gap sao alvos separados.
Quina: arrastar move o modulo. Linha L/A/P (e a E da chapa individual):
seta sai da quina mais perto (`lado`), que fica PARADA; arrastar estica,
clicar digita (Enter/Esc). Caixa de digitar (HUD e gaveta, um nucleo so':
`_tecla_no_texto`): abre com tudo selecionado, mas um OPERADOR continua
a conta ("600" e '+' -> "600 + "); clicar DENTRO da caixa so' move o
cursor (`_cursor_no_x`), fora confirma; "500 + cm" = 500 cm e "51cm00"
= 5100 cm (`_arrumar_texto_medida`). Na E a face da quina fica e a chapa engrossa
para o outro lado (`_redimensionar_chapa_ancorada`, eixo 2).
Seta com teto fixo na tela (`COMPRIMENTO_SETA_HUD`), nunca maior que a aresta; letras somem se o
item fica menor que `FATOR_ROTULO_HUD` x o rotulo (so' a acesa fica).
Letra = aresta do eixo mais FORA na tela, empurrada para longe do centro
da peca (nunca sobre a face); letras que se encostam afastam-se mais.
Posicionar puxador (`OBJECT_OT_posicionar_puxador`): 1o a linha (borda da
face sob o mouse), depois o ponto; scroll = n snaps (k/(n+1)); botao
direito volta a linha. Linhas grossas em triangulos (`_quad_2d`).
Correntes (soldas): cada ligacao de adjacencia associa 2 quinas e grava
a folga do momento -- a ORIGEM da solda. Com a tecla das opcoes
segurada (`tecla_corrente`) aparecem TODAS as quinas soldadas do item
cujo DESVIO da origem passa de `LIMIAR_CORRENTE_VIEWPORT` (5 mm); o
"so' a mais perto da camera" foi descontinuado. Cada linha tem a
corrente (clique DESAGREGA a peca inteira, `desagregar`) e, a direita,
a regua (`cabinet_resetar_distancia`). O Alt+clique e' de
`cabinet_clique_corrente` (o gizmo nativo nao aceita modificador).
PERGUNTAS (regra do usuario para todo o design): pop-up SO' quando a
acao veio da VIEWPORT (atalho, Alt+corrente/regua, Enter no modo de
vertices). Veio de um botao da GAVETA: a pergunta aparece DENTRO dela,
logo abaixo do botao, numa caixa preta com as respostas lado a lado
(`_pergunta_na_gaveta`, verbos `pergunta`/`resposta`). Tudo passa por
`_perguntar` (`_na_gaveta` diz a origem) e se responde por
`cabinet_responder_pergunta`; nunca `popup_menu` direto.
Montagem tem SO dois botoes: Corrente e Resetar distancia (regua;
Agrupar e Converter sairam da gaveta, seguem no F3). A regua fica AZUL
com qualquer solda fora da origem; quem se mexe sai da selecao:
chapa unica ativa = ELA se move ate' todas as soldas voltarem
(`_plano_reset_chapa`); se so' voltar mudando de medida, pergunta
"Mover mesmo assim?" (pop-up so' depois do SOLTAR: `esperar_soltar`).
Modulo ativo = o MODULO se adapta a chapa: as pontas soldadas esticam
ate' ela (`resetar_ponta`) e o modulo se redimensiona. Na viewport a
regua passa a peca da linha (a ativa, ou a que se afastou:
`_peca_afastada`) e volta todas as soldas dela.
Bolinhas brancas nas pontas das linhas (Alt) sao as ANCORAS: arrastar
uma ate' outro vertice das duas pecas (ima por tela; na malha modelada,
qualquer vertice dela -- o chanfro --, gravado como `v<indice>`) so' grava qual
vertice esta' soldado em qual (`OBJECT_OT_arrastar_ancora`); a regua
leva ate' la' a peca que se move (a ativa, de qualquer lado da solda):
ela anda pelas soldas normais e o que sobra DEFORMA a ponta ou a face
dela (`_deformar_ancoras`), mesmo torta. Par que ja' encostou some da
viewport (nao sobrepoe linha, bolinha e botoes). Bolinha e botao disputam o clique
pelo mais perto do mouse (`_alvo_da_corrente`).
Botao Corrente da gaveta (no lugar do ima), pela SELECAO
(`_acao_corrente`): azul = o clique desagrega, cinza = associa.
UMA peca (individual) agregada -> "Voce realmente deseja desagregar
esse objeto do grupo?"; o GRUPO (clique no modulo) -> "Voce tem
certeza que deseja desagregar todos os itens deste grupo?" (o modulo
que esvazia e' apagado, `desagregar_grupo`). Peca solta sozinha -> modo
"selecionar vertice" direto. Alvo(s) primeiro e a peca de fora POR
ULTIMO (o ativo): conecta por distancia ate' 5 mm
(`ALCANCE_CONEXAO_AUTOMATICA`), so' com os alvos; mais longe, o mesmo
"selecionar vertice", so' nos cantos dos alvos -- canto da peca,
depois o canto alvo, repetindo; Enter ou "Confirmar" no pe' -> "Juntar
ao modulo?". Sim puxa a peca ate' os alvos (`_puxar_por_pares`: a
ponta puxada estica, o alvo fica PARADO), entra no modulo e associa
sem zerar as ligacoes dos outros (`associar_por_distancia`). Pop-ups
aqui sao pedido explicito. O botao dispara no SOLTAR
(`OPERADORES_NO_SOLTAR`): no PRESS o pop-up nascia sob o mouse e o
proprio RELEASE escolhia "Sim".
Esc restaura. Durante G/R/S a HUD some inteira (`_transformando`). Cores, espessura
(`POLYLINE_UNIFORM_COLOR`, ate' 50 px) e rotulos vem da engrenagem; o
realce "Gizmo" pinta L/P/A com os eixos X/Y/Z do tema e E de laranja.
A gaveta segue as cores do tema.
Varios itens selecionados (`_itens_da_selecao`, Shift soma): a SELECAO
diz o que se edita -- grupo inteiro, uma chapa, ou so' os selecionados.
NAO ha' "Editar como? Individual | Grupo" nem "Adicionar | Finalizar"
(recusado pelo usuario). Clicada a seta de um item, os que ainda nao
tem seta dao duas piscadas de luz nas linhas (`_piscar_pendentes`,
`DURACAO_PISCADA_HUD`); cada clique numa linha deles escolhe a quina
parada (o escolhido some da escolha) e o ultimo leva a digitar: o valor
vale para todos, cada um ancorado na sua quina. Esc desfaz tudo.
Individual/Grupo da gaveta so' indica.
Modulo/porta selecionado desliga `show_outline_selected` (nao ha' contorno
por objeto) e o devolve como era: so' religa o que o add-on desligou
(`sincronizar_contornos`; salvar/abrir/desligar devolvem antes).

O hover vem de `VIEW3D_GT_campo_gaveta`, Gizmo invisivel por widget
(secao 11). Widget com icone tem dois gizmos: o do icone (tooltip e
clique) e o retangular (hover), que exclui o disco do icone para nao
roubar o pick; o glow soma os dois `is_highlight`.

**O glow vale para QUALQUER botao.** `_chave_widget(acao)` da' a
identidade (None = decoracao) e `_glow_gaveta` pinta o halo -- a mesma
funcao da alca, nunca uma copia. Botao de texto cujo operador recusa a
selecao (`_operador_apagado`) sai cinza, sem halo e sem clique. Nada de
nome do item nem medida repetida em rotulo, e nada de botao que so'
repete o que o add-on ja' faz sozinho (Sincronizar, Recalcular): a
gaveta mostra o estado, o timer o mantem. Duas regras caras:

- O halo vai **antes** do corpo do botao. Por cima, lava o texto.
- `_glow_gaveta` liga o **proprio** `blend_set('ALPHA')`: `blf.draw`
  altera o estado e o halo sai OPACO do segundo widget em diante.
  Vale para todo desenho com alfa depois de um texto.

## 9. Enum sem dropdown

Nao ha' menu suspenso aqui, e popup e' o que sai da frente do
usuario. Enum vira **fila de segmentos** (`_linha_escolha_gaveta`):
rotulo em cima, uma opcao por botao, a escolhida acesa com
`inner_sel` -- mostra tudo sem clique nenhum. Cuidado com a altura:
segmento tem 25 px e passo 29, campo de medida tem 37; emendar sem
respiro faz o campo cobrir a fila de cima (ha' teste par a par).
Pe' fixo: engrenagem e, ao lado dela, "Criar Puxador" (aba Puxadores).
"Criar Portas" fica no TOPO da aba Portas, logo abaixo das abas, largura
inteira e texto centralizado (backlog do usuario, Epico 2.3); por isso o
bloco de medidas desce 38 px SO' nessa aba -- conteudo e posicoes entre
os campos continuam identicos (testes comparam relativo). Sem porta
selecionada a aba nao mostra folga/afastamento/vaos (Epico 2.1/2.4):
a criacao usa os valores da cena; os campos vem com a porta.
Wizard de criacao (Epico 1), desenho do usuario: QUATRO cliques -- canto
da porta, canto do vao, canto oposto do vao, canto oposto da porta. Os
fios 1-2 e 3-4 (laranja) mostram quanto a folha cobre de cada lado; o
2-3 (branco), o vao. Dai' sai tudo: medida da folha, vao, espessura e a
dobradica, que e' AUTOMATICA (borda no limite do modulo = Reta, na
metade da chapa = Curva, dentro do vao = Super Curva) e nao aparece
como escolha nem na aba. Clique 1 e 2 no mesmo ponto: a margem do par
3-4 vale para ele, contada para dentro. Cobertura que nao bate com
nenhuma das tres pergunta "As medidas estao corretas?" (Nao = marcar de
novo). Depois, caixas desenhadas ao lado do clique (popup nativo nao, o
release respondia), na ordem: Folhas (1 | 2) -> abertura so' com o que
nao se deduz (Giro | Basculante, ou Giro | Correr na embutida; 2 folhas
por cima = giro direto) -> clique na borda das dobradicas (verde; 2
folhas de giro = as duas) -> scroll = quantidade (padrao pela altura:
2/3/4/5) -> mouse em Y = margem das quinas (padrao 100 mm) ->
basculante: pistoes com o mesmo sistema, offset do TOPO para baixo
(padrao 1/3 da altura). Esc cancela, botao direito volta uma etapa.
As dobradicas aparecem como VOLUME (caixas laranja, raio-X), nao
pontos: o corpo na FACE INTERNA da chapa, para dentro do movel atras
da folha, e o caneco de 35 mm nas costas da folha (print do usuario:
os pontos ficavam na borda de fora da folha).
Aba Portas: "Criar Portas" LARANJA desde o inicio e nada mais; cada
categoria APARECE quando o wizard a responde (Folhas, depois Abertura),
na mesma ordem, so' mostrando -- quem decide e' a caixa da viewport.
Porta pronta selecionada revela tudo, editavel. Dobradica (automatica)
e Converter em porta/dupla sairam da aba (pedido do usuario; F3 segue).
Porta pronta: o clique simples (a porta inteira) mostra, em raio-X, o
contorno BRANCO de cada folha, as linhas internas do vao em AMARELO, o
volume das dobradicas onde o wizard as pos e os mesmos fios dos 4
cantos; segurando Alt aparecem as 4 bolinhas brancas e arrastar
uma ate' outro vertice refaz a porta como se o clique tivesse sido
dado ali (cobertura e dobradica automaticas; fora do padrao pergunta).
Abertura (Epico 4): um SLIDER por folha, so' com a porta ou a folha
selecionada, na base da folha FECHADA e 30 mm a' frente (parado enquanto
ela abre, nao foge do mouse), por cima de tudo. GROSSO (pedido do
usuario): trilho de 13 mm com pontas redondas e borda clara, parte
aberta na cor de realce, bolinha branca de 12 mm de raio e o valor numa
caixa preta acima dela (graus; mm no correr). Medidas em MM do mundo,
nao pixels (pedido do usuario): afastar o zoom encolhe tudo na mesma
proporcao da porta; perto para no teto de 2 px/mm; o valor some abaixo
de 7 px (ilegivel). Recuado das pontas da folha
(40 mm ou 12% dela): numa porta dupla os dois NUNCA se encostam, sobra
folga no meio. So' a BOLINHA pega o clique (gizmo do tamanho dela, que
acende sob o mouse); o trilho nao. Pegar fora do centro nao a faz pular. Arrastar para a DIREITA abre, para a esquerda fecha, seja qual
for o lado da dobradica (pedido do usuario). Esc/botao direito volta.
Ferragens (dobradica, caneco, pistao, trilho) sao malhas de verdade,
nunca selecionaveis; o clique numa delas vale pela folha.
Modulo selecionado (clique nas CHAPAS, que leva a porta junto):
nada do desenho da porta aparece -- dobradicas, vao amarelo,
diagonal, cantos e sliders; fica so' a HUD do modulo (pedido do
usuario: visao mais limpa).
Selecao de porta (Epico 3): clique = a porta inteira, nunca o modulo;
duplo = uma folha. Folha sozinha tambem desliga o contorno nativo.
Opcoes: engrenagem FIXA no pe' da gaveta (`_rodape_gaveta`), painel que
sobe dela por cima do conteudo, uma linha por opcao (`LINHAS_OPCOES`,
rotulo | controle; empilha < 250 px). EXCECAO pedida pelo usuario, so'
ali: lista suspensa (`suspenso`, itens apos o widget `fundo`, desenhados
por ultimo e atendidos primeiro), `faixa` 1-50 (arrasta; clique digita)
e `cor` (atalhos + quadro S/V + matiz, aberto na propria linha).

## 10. Animacao

Glow e carrossel correm no MESMO timer (`_animar_realces`, 60 fps),
que se desregistra sozinho. Nao crie um segundo. O carrossel desliza
como roleta: o indice INTEIRO em `screen['cabinet_carrossel_*']` e' a verdade,
`_deslizes` guarda so' a intermediaria. Tres regras:

- Em repouso `_deslizar` devolve o proprio alvo: o layout parado fica
  identico ao de antes e o teste ve posicoes inteiras.
- As posicoes saem de `_widgets_gaveta`, nunca do desenho — o
  retangulo de clique anda junto com a peca, senao o usuario erra o
  alvo em movimento e o glow acende a peca errada.
- O trilho e' recortado com `scissor_set`, senao a peca que entra
  aparece por cima das setas; todo scissor ligado tem que ser
  desligado no mesmo laco.

## 11. Nunca faca

- **Cor literal** na gaveta no lugar do tema (secao 5).
- **Operador modal persistente** para capturar clique: roubaria evento
  de outros add-ons. Use Gizmo + `test_select` (a alca e' o modelo).
  Modal so' para interacao transitoria — arraste de slider, edicao de
  campo — que termina sozinha.
- **Deixar estado de GPU ligado**, ou supor o estado que veio de
  antes. Todo caminho de saida de `_desenhar_gaveta` fecha com
  `blend_set('NONE')`, e quem desenha com alfa liga o seu.
- **Desenhar a mesma coisa em dois lugares** (o Gizmo da alca tem
  `draw()` vazio de proposito) ou **duplicar geometria entre desenho
  e hit-test** — ha' teste disso.
- **Estimar largura de texto.** Use `blf.dimensions()`.

## 12. Antes de entregar
1. Rodar o harness inteiro: `tests/rodar_testes.py` (com `--gui` quando
   puder abrir janela). Mudou o layout de proposito? `--atualizar` e
   revise o diff dos snapshots (`tests/CLAUDE.md`).
2. Conferir em **tres larguras** (190, 320, 564) e nos dois temas:
   bug de layout quase sempre so' aparece num extremo (o snapshot da
   gaveta ja' grava 190/320/482/564).
3. Incrementar `bl_info["version"]`.

Captura vale mais que leitura de codigo aqui:
`bpy.ops.screen.screenshot()` num Blender de verdade pega o que o
teste nao pega — halo opaco, texto cortado, icone fora do lugar.

## 13. Alternativas ja' avaliadas e RECUSADAS
A antiga restricao contra overlay foi substituida pela HUD da secao 8,
por solicitacao explicita do usuario. A biblioteca continua na gaveta.

- **Pop-up / `invoke_props_dialog`**: fecha quando o mouse sai, e
  clicar na viewport e' a acao seguinte do posicionador. Nao existe
  popup fixo no bpy. O dialogo das Portas virou a aba (secao 9).
- **Voltar ao painel N com `UILayout`**: o handler de UI come o evento
  antes de qualquer keymap, o icone nao passa de 16 px e nao da' para
  fixar largura em pixels. Foi o que motivou a gaveta.
