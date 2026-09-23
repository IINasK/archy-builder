# Drag-and-drop da biblioteca com preview espacial

## Estado

Implementado na versao 56.0.0. Este documento descreve o contrato de
comportamento e as decisoes que precisam ser preservadas em manutencoes.

## Objetivo

Permitir que um preset da biblioteca seja levado do painel N para a viewport
com feedback espacial antes de criar a instancia definitiva. Durante a
operacao, o usuario ve uma mira no ponto de ancoragem e uma caixa wireframe
com o volume fisico do preset.

## Entradas de interface

1. O botao com o nome do preset chama o posicionador:
   - clique simples: ativa o preview; o clique seguinte na viewport insere;
   - pressionar e arrastar: tenta iniciar o preview e soltar na viewport.
   - a seta separada preserva a insercao imediata no cursor 3D.
2. O disparo usa `LEFTMOUSE` + `PRESS` no keymap `User Interface`. O modal
   aplica internamente um limiar de 6 px para separar clique de arraste.
   Registrar o item com `head=True`, evitando bloqueio por outro item.
3. O operador identifica o botao sob o cursor por
   `context.button_operator` e aceita somente
   `object.cabinet_inserir_preset`.
4. Arrastes sobre controles, lapis, cadeado e outros botoes retornam
   `PASS_THROUGH`. Isso preserva sliders e demais interacoes do Blender.
5. A imagem do painel usa `UILayout.template_icon`, unico widget que exibe
   o preview realmente ampliado. Ele nao expoe operador nem evento de drag
   na API Python; o drag verdadeiro pela imagem pertence a Asset Shelf.

## Ciclo de vida do operador

### 1. Captura do estado

- Guardar objetos selecionados e objeto ativo.
- Guardar o conjunto de colecoes existentes antes da importacao.
- Localizar a regiao `WINDOW` e `region_3d` da mesma area `VIEW_3D`.
- Guardar o ponteiro da regiao para impedir desenho em outra viewport.

### 2. Staging

- Importar o preset na origem por `inserir_preset(..., destino=(0, 0, 0))`.
- Identificar objetos novos, raizes e colecoes novas.
- Medir antes de ocultar, depois de atualizar o dependency graph.
- Salvar o estado anterior de `hide_viewport` e `hide_get()`.
- Ocultar todos os objetos importados. Nenhuma geometria definitiva deve
  aparecer enquanto o usuario ainda decide a posicao.

### 3. Caixa de dimensoes

- Considerar todos os objetos de `TIPOS_COM_VOLUME`.
- Usar `_cantos_avaliados` para incluir transformacoes e modificadores.
- Calcular minimo e maximo em espaco de mundo.
- Construir oito cantos e doze arestas da caixa.
- Usar como ancora o centro da face inferior:
  `((min_x + max_x) / 2, (min_y + max_y) / 2, min_z)`.
- A caixa nunca e' normalizada visualmente: seus lados correspondem ao
  tamanho fisico real do preset em unidades do Blender.

### 4. Posicao sob o cursor

- Converter coordenadas globais do evento em coordenadas da regiao.
- Produzir origem e direcao com `view3d_utils`.
- Tentar primeiro `scene.ray_cast` com o dependency graph avaliado.
- Ignorar qualquer objeto pertencente ao staging.
- Se houver acerto, usar ponto e normal retornados pelo raycast.
- Se nao houver acerto, intersectar o raio com um plano XY na altura Z do
  cursor 3D. Esse fallback permite soltar em area vazia da viewport.
- Transladar somente os objetos raiz. Filhos acompanham a hierarquia.
- Aplicar o mesmo deslocamento aos oito cantos usados pelo desenho GPU.

### 5. Desenho GPU

- Registrar um `SpaceView3D.draw_handler_add` em `POST_VIEW`.
- Desenhar a caixa verde com primitiva `LINES` e shader `UNIFORM_COLOR`.
- Desenhar a mira com tres eixos centrados no alvo.
- Orientar dois eixos no plano tangente da superficie e o terceiro na
  normal do acerto.
- Usar amarelo quando existe superficie e branco no plano de fallback.
- Desenhar somente na regiao `WINDOW` que iniciou o operador.
- Remover o draw handler em toda saida: confirmar, cancelar ou erro.

## Resolucao

### Confirmacao

- Ocorre no `RELEASE` do botao esquerdo para um drag real.
- Para chamada explicita do operador, aceita o proximo `PRESS`.
- Exige cursor dentro da regiao da viewport e alvo valido.
- Remove o handler, restaura a visibilidade original do preset, seleciona
  os objetos importados e define uma raiz como objeto ativo.
- O resultado fica coberto pelo Undo do operador.

### Cancelamento

- Gatilhos: botao direito, Esc, desativacao da janela, alvo invalido ou
  soltura fora da viewport.
- Remove handler e texto de status.
- Remove todos os objetos importados com `do_unlink=True`.
- Remove as colecoes criadas pela importacao.
- Restaura selecao e objeto ativo anteriores.
- Nao deixa objeto, caixa, mira ou colecao residual.

## Falhas e limpeza

- Inicializar listas de objetos e colecoes antes de importar. Assim uma
  excecao parcial ainda pode ser limpa.
- Se o preset nao trouxer geometria com volume, aceitar posicoes das raizes
  como ultimo recurso; se nem isso existir, cancelar.
- Falhas do raycast nao encerram o modal: registrar no console e usar o
  plano do cursor.
- Falha de desenho GPU nao pode derrubar o operador modal.
- Nunca remover colecoes que existiam antes do inicio do drag.

## Criterios de aceite

1. Arrastar o nome para uma face mostra mira amarela exatamente sob o cursor.
2. A caixa verde acompanha o cursor e preserva as dimensoes do preset.
3. Mover para area sem geometria usa o plano horizontal do cursor 3D.
4. Soltar dentro da viewport revela e seleciona a instancia final.
5. Soltar fora da viewport nao cria nada.
6. Botao direito e Esc removem imediatamente preview e staging.
7. Nenhum handler ou texto de status permanece apos terminar.
8. Clique simples no nome ativa o posicionamento; a seta insere diretamente
   no cursor 3D.
9. Sliders, lapis e cadeado continuam operando normalmente.
10. O add-on registra e remove sem erro no Blender 4.2 e 5.2.

## Validacoes executadas

- Registro e `unregister` no Blender 4.2.1 LTS.
- Registro e `unregister` no Blender 5.2.1 LTS.
- Preset de teste de 600 x 400 x 300 mm produz bbox de
  0.6 x 0.4 x 0.3 m nas duas versoes.
- Ocultacao e restauracao do staging verificadas nas duas versoes.
- Remocao do staging no cancelamento verificada nas duas versoes.
- Shader `UNIFORM_COLOR` verificado na sessao grafica do Blender 5.2.1.
