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
`Armarios (3)` vira `arm (3)`, nunca `Armarios (`. A CASCATA da biblioteca
nao tem contagem (pedido do usuario: ocupava espaco) nem limite de niveis:
um carrossel por nivel do caminho escolhido; ramo sem preset nao aparece.

HUD da forma: na diagonal (inclusive a que toma o lado inteiro), um ARCO
em cada ponta com o angulo de DENTRO da planta em graus (esboco do
usuario); hover acende, clicar digita, arrastar de lado gira. Ponta que
acaba na ESPESSURA de uma chapa (prateleira da cantoneira na lateral): a
linha para onde a peca para e o arco mede com a face da lateral. O arco e'
PEQUENO e colado na quina (pedido do usuario: a 70 mm atravessava a peca):
raio fixo na TELA (~26 px, como o gizmo de angulo), nunca mais que 1/4 do
lado mais curto da quina; o numero fica logo fora dele, na bissetriz.

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
Quina: arrastar move o modulo; com Ctrl (a qualquer momento do arraste)
a quina gruda na de OUTRO armario (caixa da HUD) ou chapa ao alcance de
`RAIO_SNAP_QUINA_HUD` px -- snap especial, so' quinas (nada de vertice,
aresta ou grade); grudada, ganha bolinha cheia no circulo laranja.
Linha L/A/P (e a E da chapa individual):
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
Modulo que nao e' caixa (canto em L, diagonal, curvo -- os do Promob): a
linha branca segue a PLANTA em baixo e em cima, nunca a caixa envolvente
(pedido do usuario: no L a quina vazia tinha linha). L e P nos lados
inteiros; P1/P2 nos lados que chegam no canto = profundidade de CADA braco
(o outro nao mexe); R na diagonal e no arco (arrasta para dentro = maior);
A nas quinas. Recorte < 100 mm (quina de tras aberta) nao muda o desenho.
Na aba Modulos o mesmo modulo ganha a secao FORMATO (P1, P2, Raio e o
Angulo da diagonal, que deixa a frente do canto parada).

**Gavetas (aba propria, pedido do usuario).** Cabecalho com 5 abas
(Modulos | Portas | Gavetas | Prateleiras | Puxadores; estreita: Mod. |
Portas | Gav. | Prat. | Pux.). "Criar Gavetas" laranja no topo;
o assistente pede 2 cantos na DIAGONAL do vao (de cima a' esquerda a baixo
a' direita, ima nos vertices; o 2o pode ser livre no plano da frente),
scroll = quantas, o mouse a profundidade (Alt gruda num vertice) e a caixa
do trilho (Telescopico | Oculto). Modulo selecionado absorve gavetas e prateleiras na HUD (sem segunda seta); as gavetas acompanham a face proxima (base/topo) SEM mudar as medidas ao redimensionar a caixa. Selecionadas (clique na frente = todas
do vao, duplo = uma): so' elas tem linha branca; L/A/P da HUD mudam o vao
(a quina perto do mouse fica) e a profundidade; Alt mostra 3 bolinhas --
as quinas de cima a' esquerda e de baixo a' direita da frente e a da
profundidade. O arraste usa o snap nativo do Blender (vertice/meio de aresta), sem varrer malhas em Python; a propria gaveta e ferragens nao sao alvos, e Esc restaura o cursor e a selecao. O slider fica NA frente (um pouco a' frente dela, no meio da
altura) e anda com ela: a gaveta aberta nunca o cobre. Na aba: Gavetas
(L/A/P + contador), Frente (Sobreposta | Embutida, Espacamento frontal,
Entre gavetas, Recuo, Espessura, Curva), Trilho e o carrossel do Puxador -- de
UMA gaveta (duplo clique) ou de todas. Curva = flecha do arco da frente
(0 = reta), a do gaveteiro de canto do Promob; as alturas desiguais que a
importacao traz somem ao mudar a quantidade.

**Prateleiras (aba propria, pedido do usuario).** O assistente das
gavetas com SO' 2 pontos ("Criar Prateleiras": canto de cima a' esquerda e
de baixo a' direita, scroll = quantas, e o clique cria). Sem etapa de
profundidade nem trilho: a prateleira vai ate' o fundo do modulo e a folga
da frente e' o Recuo da aba. Selecionadas (clique = todas do vao, duplo = uma): a HUD tem o
L/A/P do vao e uma linha por VAO entre as prateleiras, no meio da largura,
com o VALOR ao lado (sao varios; uma letra so' nao diria qual). Arrastar ou
clicar e digitar um vao anda SO' a prateleira de cima dele. Na aba:
Prateleiras (L/A/P + contador), Chapa (Espessura, Recuo, Folga lateral) e
Espacamento: Igual | Livre, "Entre prateleiras" (o mesmo em todas) e
Vao 1..n+1 de baixo para cima; com UMA selecionada, so' Abaixo e Acima dela
(os dois andam so' ela).

**Porta de correr: a folha.** Na porta de correr selecionada, uma fila
Chapa | Quadro de aluminio (depois do trilho, com ou sem moldura). Quadro =
o perfil de aluminio do despenseiro do Promob em volta de um painel fino,
que tem material proprio (o vidro/espelho); o trilho continua o nosso.

**Snap que diz o que pegou (pedido do usuario: detector de angulo).** O
ima dos assistentes (porta, gaveta) mostra, ao lado da bolinha, o que o
ponto e': "Quina reta", "Angulo 135", "Fim da curva", "Centro do arco". O
meio de uma borda redonda nao e' mais oferecido (eram dezenas de pontos
colados); as pontas e o centro sim. Com Ctrl, o modulo arrastado gruda
tambem nas quinas e pontas de curva de pecas modeladas/curvas.
Posicionar puxador (`OBJECT_OT_posicionar_puxador`): 1o a linha (borda da
face sob o mouse), depois o ponto; scroll = n snaps (k/(n+1)); botao
direito volta a linha. Linhas grossas em triangulos (`_quad_2d`).
Puxador PERFIL = o modelo de aluminio do usuario (arquivo dele, extraido
por `extrair_puxador.py`: malha, material e texturas como sao), na borda
inteira, SEM deformar chanfro nem arredondado (pedido do usuario): na
largura as PONTAS andam inteiras; na espessura, a escala antiga esticava
os cantos das costas -- agora a secao se divide no maior vao sem vertice
(`_corte_do_perfil`, o trecho reto): as costas andam inteiras e so' o
reto acomoda. Porta tao fina que o reto sumiria: volta a' escala. A
frente, o labio e a cava sao os dele.
Tira 34,81 mm da madeira (o J de caixas, sem o asset, tira 30).
Nomes de objeto em portugues e sem sublinhado (pedido do usuario):
"Folha 01", "Puxador Perfil", "Pistao Corpo", "Dobradica Copo"...; o rig
importado tambem (objetos, malhas, ossos, modificadores, material).
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
**Gaveta por CONTEXTO** (conceito do usuario, TODAS as abas): sem nada
selecionado a aba mostra SO' o botao laranja de criar ("Criar Portas" /
"Criar Puxador"; a Modulos, cuja criacao e' a biblioteca, nao mostra
nada -- o orcamento, da cena inteira, mora nas Opcoes). Criando, os campos nascem etapa a
etapa. Selecionado, so' o que vale para AQUELE item (`_selecionado`:
ativo sem selecao nao conta): o bloco de medidas e' da aba dona do item
(modulo/chapa/objeto de fora = Modulos, porta = Portas, puxador =
Puxadores), nao fixo nas tres; porta sem dobradica; ferragens
selecionadas = so' a quantidade e o afastamento delas.
"Criar Portas" fica no TOPO da aba Portas, logo abaixo das abas, largura
inteira e texto centralizado (backlog do usuario, Epico 2.3); o bloco de
medidas desce 38 px nessa aba. Sem porta selecionada a aba nao mostra
folga/afastamento/vaos (Epico 2.1/2.4): os campos vem com a porta.
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
release respondia) que NUNCA saem cortadas (`_botoes_assistente` mede a
regiao: perto da borda a caixa vai para o outro lado do mouse ou
sobe/desce; o recado que segue o mouse idem), na ordem: Folhas (1 | 2) -> abertura so' com o que
nao se deduz (Giro | Basculante, ou Giro | Correr na embutida; 2 folhas
por cima = giro direto) -> clique na borda das dobradicas (verde; 2
folhas de giro = as duas; basculante = sempre CIMA, sem perguntar) ->
scroll = quantidade (padrao pela altura: 2/3/4/5) -> mouse em Y = margem
das quinas (padrao 100 mm) -> basculante: scroll = quantidade de pistoes
e a posicao nasce AUTOMATICA (modelo real do catalogo; aberta = pistao no
dobro do fechado); o mouse em Y so' SOBE o pistao (descer passaria do
curso). Esc cancela, botao direito volta uma etapa.
Previa de dobradica, pistao e puxador = o WIREFRAME da peca de verdade
(pedido do usuario; antes caixas de volume e, no puxador, so' o ponto da
ancora), na cor de realce e na espessura das linhas da HUD, raio-X
(`_desenhar_arame`, POLYLINE em 3D). O wizard planeja pelas MESMAS
ferragens que a porta monta (`_ferragens_da_porta`): a Reta e' o rig do
usuario, desenhado pelo CONTORNO (vincos > 30 graus, sem a subdivisao:
~4 mil segmentos em vez de 190 mil) gravado no .json do asset por
`extrair_arame_dobradica.py`, em lote na GPU peca a peca; caixas,
canecos e pistoes pela forma deles. O pistao aberto ganha um fio branco.
O posicionador do puxador mostra o puxador na linha sob o mouse.
Aba Portas criando (blocagem do usuario): marcada a area, as medidas da
porta (so' leitura: saem dos cliques); depois a COPIA da caixa -- cada
pergunta APARECE quando o wizard chega nela (Medidas corretas?, Folhas,
Abertura), clicavel como a da viewport: o MODAL atende o clique na gaveta
(`_responder_pela_gaveta`); responder de novo uma fila refaz dali. Depois,
Dobradicas e Pistoes EDITAVEIS (`_secao_ferragens_gaveta`): quantidade em
segmentos e afastamento/distancia do topo em campo; digitado na etapa do
mouse em Y, o 1o movimento parte do valor. A mesma secao, com as
ferragens SELECIONADAS, edita todas as portas do modulo (o clique numa
ferragem leva a gaveta a' aba Portas). Porta pronta selecionada: em cima,
Reposicionar no vao e Definir como frente (icone a' esquerda do texto,
`_icone_ao_lado`); depois CATEGORIAS com o titulo de Montagem
(`_titulo_secao`, auditoria do usuario: campos compactos, claros, rotulo
inteiro): **Porta** (L/A/E), **Folhas** (Entre folhas/planos e o campo
COMPACTO das folhas na ponta -- contador com rotulo: arrasta e digita; os
segmentos 1 2 3 4 sairam), **Posicao** (Afastamento ou Recuo), **Trilhos**
(Recuo, correr embutido) ou **Moldura** (Espessura, Rodape, Testeira) e
**Abertura** (slider dos retratos no titulo). Rotulo curto dentro da
categoria ("Recuo", nao "Recuo para trilhos"): o titulo ja' diz de que e'.
Dobradica (automatica) e Converter
em porta/dupla sairam da aba (pedido do usuario; F3 segue).
Correr: 1-2 e 3-4 no mesmo canto de DENTRO = embutido; de fora para
dentro = COM MOLDURA -- folhas de 18 na frente do modulo, cobrindo a
frente inteira, num trilho de aluminio do usuario (dois canais, a 1a na
frente), e a moldura de chapas de 15 refeita com a porta (revestimento das
laterais, base do trilho + testeira em cima, base + rodape embaixo; soma
acima e abaixo do modulo). Metade-metade (um par no mesmo ponto, o outro
nao) PERGUNTA "Porta embutida ou com moldura?" -- moldura usa o modulo
inteiro, embutida a medida de dentro da chapa.
Com moldura vem mais uma caixa: "A porta tem base?" -- sem rodape a
moldura vai direto no chao (rodape 0). A moldura passa a SER a caixa do
armario: L/A/P do modulo e a caixa da HUD contam com ela (envelope).
Depois da base, "Qual trilho?": PESADO (perfis de aluminio) ou LEVE
(canais fresados nas bases + U de embutir, folha de 15, SEM testeira: a
folha corre a' vista ate' a base de cima); na porta pronta,
os dois segmentos ficam no fim da categoria Moldura.
Porta pronta: o clique simples (a porta inteira) mostra, em raio-X, o
contorno BRANCO de cada folha, as linhas internas do vao em AMARELO e
os mesmos fios dos 4 cantos (as dobradicas nao: ver Ferragens); segurando Alt aparecem as 4 bolinhas brancas e arrastar
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
folga no meio. CORRER: o slider vai do centro da folha fechada ao da
aberta (a bolinha anda embaixo dela), um degrau de 40 mm acima por
trilho -- os de uma porta de varias folhas nao se sobrepoem. So' a
BOLINHA pega o clique (gizmo do tamanho dela, que
acende sob o mouse); o trilho nao. Pegar fora do centro nao a faz pular. Arrastar para a DIREITA abre, para a esquerda fecha, seja qual
for o lado da dobradica (pedido do usuario). Esc/botao direito volta.
A folha NUNCA fica rente a' borda do armario (prints do usuario), em
nenhum cenario: toda cobertura padrao deixa 2 mm de respiro -- Reta cobre
a espessura menos 2, Curva a metade menos 2 (duas portas na mesma chapa
do meio nao se encostam), embutida e correr ficam 2 mm para dentro do
vao. Nao ha' "Folga no perimetro" (pedido do usuario: sempre zero; so'
a porta importada guarda uma, por dentro). Cobertura fora do padrao,
marcada e confirmada pelo usuario, vale como marcada. Correr: sem campo
de sobreposicao -- com a largura da folha editavel ela e' consequencia
(o usuario nao via a diferenca entre as duas).
Dobradica RETA = o modelo e o rig do usuario (arquivo dele, extraido por
`extrair_dobradica.py`), importados tal e qual -- nada refeito: a folha
abre como a dele (gira E anda, 91,7 graus no fim) e o copo fura a folha
(Boolean -- o cortador e' a unica peca refeita: o do modelo era um
octogono menor que o copo e fora do centro, sobravam lascas da porta
dentro do copo; agora e' um cilindro medido no copo, com 0,2 mm de folga).
A folha fica no minimo a 1,86 mm do modulo, a folga do modelo
dele: encostada, o canto da folha aberta entrava no tampo (print do
usuario). Curva e embutida seguem com o volume em caixa e eixo fixo.
Ferragens (dobradica, caneco, pistao, trilho) sao malhas de verdade, e
NADA fica fora da edicao nativa (pedido do usuario): duplo clique numa
peca seleciona so' ela, como objeto do Blender (Tab, G/R/S, X,
modificadores). Elas so' nao acendem junto com a porta nem com o modulo.
A malha de uma peca do rig e' dividida entre as copias (editar uma muda
todas); a das caixas e' refeita quando a porta muda. Dobradicas e pistoes so'
APARECEM criando a porta ou SELECIONADOS (pedido do usuario): clique numa
dobradica = todas as dobradicas do modulo, num pistao = todos os pistoes,
Shift soma (ou tira) o outro tipo. Nesse modo so' elas ficam acesas
(o arame delas, raio-X): porta sem contorno branco, modulo e puxadores
apagados. Segurando Alt, um controlador (bolinha branca) por porta e
tipo: o da dobradica corre na BORDA (margem; passar do meio conta da
outra ponta, espelhada), o do pistao na LATERAL (distancia do topo, trava
no curso; voltar ao ponto automatico grava 0). Arrastando, aparece o
trilho; Esc/botao direito devolve. Trilho do correr: o clique vale pela
folha.
Varios itens selecionados: o ATIVO (a selecao principal, que manda nas
funcoes) tem as linhas da HUD levemente mais grossas (+40%, min. 1 px;
`_principal_hud`). Com um item so', nada muda.
Modulo selecionado (clique nas CHAPAS, que leva a porta junto):
nada do desenho da porta aparece -- vao amarelo,
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

Nome do grupo (pedido do usuario): ao agrupar, F3 (viewport) abre o
dialogo do Blender com "Armario LxAxP" ja' escrito; a Corrente juntando
pecas soltas pela gaveta mostra a MESMA caixa preta das perguntas, com o
campo "Nome do grupo: ...|" (digita direto, Enter/OK confirma, Esc/Manter
fica a sugestao). Outliner: cada armario e' uma Collection com o nome dele;
dentro, o Empty, as chapas e a porta ("Porta Dupla", "Porta de Correr"...).

Comodo do orcamento, no fim da aba Modulos (so' com armario
selecionado): titulo "Orcamento" como o de Montagem (sem separador: os da aba sao da cascata). Com armario
selecionado, o COMODO e' UMA linha "Comodo: Cozinha" com a seta da lista
suspensa (a grade fixa de 14 segmentos ocupava a aba -- RECUSADA pelo
usuario). O clique EXPANDE a lista dentro da aba, empurrando o resto
(nao flutua: sem conflito com o recorte do painel): os comodos do
prompt, os ja' digitados na cena, "Sem comodo" (se ha' um) e "Outro
nome...", que abre o campo da caixa preta logo abaixo (Enter/OK,
Esc/Cancelar). Escolher fecha a lista e vale para todos os armarios
selecionados. O comodo e' uma PASTA no Outliner (Collection na raiz com
as dos armarios dentro).

"Gerar orcamento (.txt)": ULTIMA linha do painel de Opcoes (engrenagem),
largura inteira -- e' da cena inteira e o add-on e' vendido, entao nada
de "ERP" nem de copiar para a area de transferencia (RECUSADO: o
usuario quer o arquivo). Dispara no SOLTAR e abre o "Salvar como" do
Blender (sugere "Orcamento - <nome do .blend>.txt" ao lado do .blend).
Salvo, o botao ACENDE com o que fez ("Salvo: N modulo(s)") e as
pendencias aparecem numa caixa preta logo abaixo, dentro do painel, por
30 s -- so' o relatorio da barra de status passava despercebido.

"Criar Puxador": mesmo padrao do "Criar Portas" -- LARANJA, no topo da
aba Puxadores, largura inteira, texto centralizado, mais forte enquanto
posiciona ("Posicionando o puxador... (Esc cancela)"). Saiu do pe' fixo.
Posicionando, aparece o MODELO num carrossel de RETRATOS (pedido do
usuario: a foto a 45 graus, como na biblioteca, no lugar dos nomes; setas
quando nao cabem): os de fabrica e os do usuario (categoria Puxadores da
biblioteca). O posicionador atende o clique e troca a previa na hora. Reposicionar (pedido do usuario): com Alt, a ancora de
cada puxador da selecao vira bolinha branca; arrastar leva-o a outra
borda SO' das chapas do grupo dele (folhas da porta, ou chapas do
modulo), snap de LINHA na face virada para quem olha, e ele sai virado
conforme a borda; o perfil devolve a madeira e corta a nova (um por
borda). Esc devolve. Clique no puxador (tambem de gaveta) seleciona SOMENTE ele e abre Puxadores; trilhos das gavetas permanecem com elas. Puxador do add-on selecionado: medidas e o modelo
(`_trocar_modelo_puxador` refaz AQUELE); objeto de fora: "Usar como
puxador" -- encostado numa chapa vira o puxador dela no mesmo lugar;
solto, a gaveta pede o clique na face que encosta na porta e o criador
abre com o modelo novo. "Converter em puxador" (so' marcar) ficou no F3.

TODO retrato (puxador, abertura, dobradica) tem o MESMO quadrado
(`_lado_retrato`, pedido do usuario): o do slider pequeno ao lado do
titulo da fila (`cabinet_tam_retrato`, 40-128 px); so' encolhe para
caber tres lado a lado.
Retratos em toda escolha de MODELO: abertura (Giro/Basculante/Correr)
criando e com a porta selecionada; a dobradica, que e' AUTOMATICA, so'
mostra o retrato do tipo detectado, pequeno e sem clique (tres retratos
empurravam os campos para baixo da divisoria) -- na etapa da borda, o da
borda sob o mouse. O retrato e' SO' a dobradica, sem o modulo (pedido do
usuario); Curva e Super Curva usam o da Reta ate' terem modelo proprio
(`FOTOS_PENDENTES`). Layout do usuario (mockup): na linha "Abertura" ficam o
retrato da abertura ESCOLHIDA (clicar volta a' escolha das tres), o da
dobradica e, ao lado, "Dobradicas:" com o CONTADOR (< 2 >: arrastar ou
clicar na metade direita/esquerda) -- nao mais cinco segmentos; embaixo,
o afastamento. O "aceitar" da etapa e' um quadrado VERDE com visto, colado
a' direita do campo que ela edita (o mesmo do clique na viewport; a etapa
seguinte parte do mouse quando ele volta). Gaveta estreita (< 260 px):
empilha. Qualquer campo de valor ARRASTA: direita aumenta, esquerda
diminui (1 mm/px; Shift fino, Ctrl grosso; Esc devolve; um undo so');
clicar sem arrastar continua digitando. A cada etapa nova do
wizard a aba rola ate' o fim, onde a etapa nasce (`_rolar_ate_o_fim`).
Na biblioteca, Puxadores e Dobradicas mostram tambem os de fabrica,
TRAVADOS (moram no add-on, fora do indice); clicar num puxador dela (foto
ou "Ins.") abre o "Criar Puxador" com ele -- o arrasto nativo do Asset
Browser traz so' o 3D.

**Modulos | Materiais** (pedido do usuario): dois segmentos AO LADO do
titulo "Biblioteca" (verbo `biblioteca`, nao `escolha`: a fila e' do
cabecalho, nao da aba), com a contagem dentro; sem espaco (< 2 x
`PX_MIN_NIVEL` depois dos icones) descem para a linha de baixo. Os icones
seguem a biblioteca aberta (Materiais: pasta e "+"). Materiais usam a
MESMA cascata e a MESMA grade (slider "Tamanho das miniaturas"); no lugar
da foto, a esfera da cor (`esfera_rgba`: difusa + brilho, sem render); a
esfera do material da selecao acende. UM clique na esfera NAO faz nada
(pedido do usuario: o clique errado pintava o que nao devia); o DUPLO
pinta a selecao e ARRASTAR (pincel no cursor) pinta, ao soltar, o que
esta' sob o mouse -- recusado: clique simples aplicando. Botao DIREITO
na esfera = PINTURA RAPIDA (pedido do usuario): a caixa preta abre sob o
material (nao pop-up: regra da gaveta) com "quais modulos?" -- um botao por
COMODO que tem armario, "Sem comodo", "Todos" e "Cancelar" -- e depois
"pintar o que?": Tudo, So' a caixa (corpo + fundo), So' as portas
(folhas + moldura). Muitas respostas quebram em filas
(`LARGURA_MIN_RESPOSTA`); a 1a resposta nao gera passo de desfazer. Embaixo:
Editar e Apagar; o
"Apagar?" abre sob a fila e a biblioteca rola ate' ele
(`_rolar_biblioteca_ate_pergunta`).

**Paredes (como no Promob, pedido do usuario).** Botao DIREITO segurado
num modulo o arrasta; solto numa superficie VERTICAL que nao seja movel
do add-on, as COSTAS (+Y do modulo) encostam nela e ele fica ASSOCIADO
A' FACE, nao ao objeto (pedido do usuario: a sala inteira e' um objeto
so'): parede = a face sob o mouse mais as vizinhas no MESMO plano ligadas
por aresta (`regiao_da_parede`). Durante o arraste essa face ACENDE (veu
e contorno grosso na cor de realce); fora de parede, a barra de status
diz por que (movel, nao vertical). Gravado: UID no objeto, indice da face,
ponto das costas e normal no referencial dele. O raio, achado o objeto,
e' refeito so' contra ele (`raio_ate_parede`): as costas ficam NO plano
da parede e pular o modulo atravessava a face (o modulo piscava). O cursor fica no meio das costas; pontas, piso e teto grudam a
`SNAP_PX`. Clique sem arrastar = o menu de contexto de sempre (no
SOLTAR). Parede = QUALQUER superficie (escolha do usuario: nada de
ferramenta "Criar parede" nem marcar a malha); os limites sao as faces
da face. Associado de verdade: a parede que anda leva o modulo; G/R
no modulo o devolvem ao plano (so' desliza) -- pelo timer de seguranca,
nunca no handler do depsgraph. Selecionado: contorno da parede e 4 guias
(esquerda, direita, piso, teto, esq./dir. de quem olha a parede) na cor
de realce; o NUMERO e' gizmo (ganha da selecao): clique digita, arrastar
ao longo da guia muda. Solta: F3 "Desassociar da Parede".

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
