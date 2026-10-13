# Plano de reformulacao da biblioteca

Status: planejamento; a interface atual ainda nao foi alterada.
Referencia: imagem enviada pelo usuario em 13/10/2026, com categorias
em abas horizontais e uma fila de miniaturas abaixo.

## Disposicao aprovada pelo pedido

A biblioteca ocupa uma faixa no topo de toda a regiao do Cabinet Creator:
acima TANTO do menu a esquerda QUANTO da viewport principal. O menu fica
dedicado a editar o item selecionado. A biblioteca continua acessivel
ao trocar entre Modulos, Portas, Gavetas, Prateleiras e Puxadores.

```text
+-------------------------------------------------------------------+
| Modulos / Materiais | categorias do nivel 1                        |
| categorias dos niveis seguintes: caminho atualmente aberto        |
| [foto + nome] [foto + nome] [foto + nome] ...              <     >  |
+---------------------+---------------------------------------------+
| Menu de edicao      |                                             |
| do item selecionado | Viewport principal                          |
|                     |                                             |
+---------------------+---------------------------------------------+
```

## Navegacao e aparencia

- Abas horizontais para categorias; a ativa fica realcada pelo tema.
  Cada nivel exibe os filhos da categoria escolhida no nivel anterior.
- Preservar `niveis`, UUIDs, catalogos e a biblioteca unica existentes.
  Este trabalho muda a apresentacao, sem reclassificar os presets.
- Profundidade de categorias sem limite. Ramos vazios desaparecem.
  Niveis que nao couberem tem rolagem, sem eliminar partes do caminho.
- Uma fila horizontal de miniaturas, como na referencia: foto acima,
  nome abaixo, tooltip com o nome completo. Rolagem e setas por fila.
  Nomes e fotos reutilizam o catalogo e os PNGs atuais.
- Proposta inicial: fotos de 64-88 px logicos; faixa de cerca de
  160-200 px com o caminho atual. Medidas finais dependem do prototipo
  em escalas 100/150/200%. Altura ajustavel e opcao de recolher a faixa.
- Material continua representado por esfera; categoria e item nao
  exibem contagem. Manter renomear, salvar, apagar e protecoes atuais.

## Interacoes preservadas

- Clique num modulo inicia seu posicionamento na viewport; Esc cancela.
- Material: clique simples nao pinta; duplo pinta a selecao; arrastar
  pinta o alvo ao soltar; direito abre pintura rapida por comodo/parte.
- Perguntas originadas na biblioteca aparecem dentro da propria faixa,
  com espaco e rolagem para respostas. Pop-up permanece so' da viewport.
- Mouse na biblioteca controla suas filas; mouse na cena controla a
  viewport. Camera, selecao, gizmos, HUD e snap nao recebem cliques da faixa.
- Clicar na caixa seleciona o modulo; portas/puxadores abrem suas funcoes;
  puxadores de gavetas sao individuais e seus trilhos ficam com as gavetas.

## Implementacao proposta

1. Prototipar uma area dedicada no topo: dividir horizontalmente a
   regiao de trabalho, depois dividir a parte inferior em menu e cena.
   Assim a faixa pode atravessar as duas colunas. Reutilizar desenho GPU,
   tema e eventos existentes. Nao usar uma janela flutuante.
2. Na migracao do layout atual, guardar vista, largura do menu e estado
   de navegacao; reorganizar apenas as areas pertencentes ao add-on e
   sua viewport. Validar abrir/fechar/restaurar em 4.2 e 5.2 antes de
   migrar automaticamente. Outros editores permanecem fora desse fluxo.
3. Separar a apresentacao da biblioteca do layout do menu. Catalogo,
   miniaturas e acoes permanecem compartilhados; um modulo de interface
   cuida da faixa. O menu deixa de renderizar a biblioteca inferior.
4. Adaptar os filtros de area dos operadores/gizmos, alvo do arraste,
   perguntas e rolagem. Reconectar areas por papel ao reabrir arquivos;
   ponteiros da area nao podem ser a unica identificacao persistente.
5. Carregar fotos somente dos itens visiveis e uma pequena margem;
   limitar o cache de imagens/texturas. Filtrar pelo indice, nunca abrir
   arquivos .blend para desenhar uma fila. Invalidar cache por mudanca
   de categoria/catalogo; nenhuma varredura de malhas no desenho.
6. Atualizar documentacao e snapshots quando o prototipo for integrado,
   removendo a divisoria e as dependencias da biblioteca inferior.

## Validacao e criterio de entrega

- Primeiro, validar a disposicao completa numa cena de teste e medir
  abertura, troca de categoria, rolagem e uso de memoria com a biblioteca
  atual e um catalogo sintetico maior. Nada escreve na biblioteca real.
- Depois, verificar eventos reais: modulo, materiais, pintura rapida,
  salvar/apagar, trocar aba de edicao e recolher/restaurar a faixa.
- Testar janela estreita, escalas de UI, caminhos profundos, duas janelas,
  troca de workspace, reabertura de arquivo e desativacao do add-on.
- Entrega: faixa acima das duas colunas; conteudo legivel; estado
  preservado; nenhuma interferencia nos controles da cena; testes nas
  duas versoes. Falhas anteriores de parede/material devem ser relatadas
  separadamente, sem apresentar a suite completa como aprovada.

## Ordem do trabalho

Layout completo -> catalogo e miniaturas -> eventos e perguntas ->
cache e desempenho -> migracao e testes de regressao.
