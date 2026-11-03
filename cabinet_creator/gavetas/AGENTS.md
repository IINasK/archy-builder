# Setor gavetas

## Papel e fronteiras

Gavetas do MOVEL: frente, caixa, trilhos, vao, curso e edicao por unidade.
O menu GPU e' `../gaveta.py`, nao este setor.
`AssistenteDoVao` tambem atende [prateleiras](../prateleiras/AGENTS.md) e
[divisorias](../divisorias/AGENTS.md); corrigir o gesto comum aqui, sem copiar.
Puxadores e referencia da frente: [portas](../portas/AGENTS.md), `../frentes.py`.

## Localizar tarefas

| Tarefa | Funcao / arquivo |
|---|---|
| Calculo e montagem | `calcular`, `montar`, `criar_gavetas` em `__init__.py` |
| Frente, referencia e profundidade | `referencia_do_vao`, `pontos_internos_do_vao`, `profundidade_disponivel` em `__init__.py` |
| Editar grupo/unidade/altura | `editar`, `editar_individual`, `normalizar_alturas` em `__init__.py` |
| Adaptar ao corpo | `acompanhar_redimensionamento`, `limitar_medidas`, `_adaptar_espaco` em `__init__.py` |
| Gesto comum e snap | `AssistenteDoVao`, `OBJECT_OT_marcar_ponto_vao` em `__init__.py` |
| Curso/slider/Alt | `definir_abertura`, `OBJECT_OT_abrir_gaveta`, `OBJECT_OT_arrastar_ponto_gaveta` em `__init__.py` |

## Decisoes e armadilhas

- Area livre (372): areas_criacao recebe um clique e conserva caixa retangular; HUD/snap/B compartilhados. Aplicar entrega referencial/diagonal/profundidade numericos ao AssistenteDoVao em QUANTIDADE; gavetas seguem direto ao trilho. Pontos usam o fluxo 3D descrito abaixo. Prateleiras/divisorias/fundos usam a mesma ponte, sem normalizar apoios imaginarios. Internos (375): finalizar prateleiras/divisorias entrega numeros a areas_criacao para lacuna/continuacao, encerra snap/modal antes da pergunta; gavetas/fundos conservam fluxo atual.
- Criacao 3D (376): tres pontos em qualquer ordem -> caixa min/max nos eixos do modulo -> clique explicito na face da frente -> quantidade -> trilho. 378: hover usa raio nativo; translate/snap apenas no PRESS do ponto, RELEASE confirma. Entre pontos, sem gesto ativo: navegar por MMB/trackpad/keymap nativo (view3d.navigate/walk/fly), mantendo etapa/pontos; Shift+scroll navega mesmo em quantidade. Contrato continuo antigo de portas/solda permanece. Snap nativo VERTEX/EDGE_MIDPOINT/FACE; sem inferir orientacao da diagonal. areas_criacao concentra caixa/raio/frente. Backspace reabre frente/terceiro ponto. Contratos de edicao por dois apoios e planos 2D permanecem.
- Aplicar area de volume tambem pede frente. A frente permuta eixos e conserva os oito cantos/medidas; assistente recebe referencial numerico e vai direto a QUANTIDADE. Continuacao prateleiras/divisorias reutiliza a area ja orientada. Profundidade deixa de ser um gesto separado na criacao 3D; Alt/edicao legada mantem seus contratos.
- Snap 380: B nos tres pontos abre translate nativo de vertice/meio de aresta; soltar a tecla nao confirma, clique confirma. Entre pontos a camera continua livre; clique/arraste existente conserva release_confirm.
- Fundo associado (360): o ponto final de profundidade identifica fundo
  por UID no mesmo modulo. O limite e' a face interna, nao o centro;
  fundos.py coordena a hitbox e o dominio conserva calculo/trilho/montagem.
  Desassociar usa UNPINNED, sem corrente/regua.
- Trilho e' BLOCAGEM em tamanho real; o modelo definitivo nao esta' pronto.
- Clique = todas, duplo = uma; SO' elas com linha na HUD. Slider ANDA com
  a frente e nunca fica coberto. Modulo selecionado absorve os filhos.
- Selecao 384: depois de isolar unidade, Shift+clique soma outra do mesmo vao. Shift+duplo reduz so' o vao clicado, preservando selecoes externas. Clique sem Shift continua grupo; Tab edita somente as unidades escolhidas.
- Puxador (385): gaveta isolada por duplo na frente/corpo libera clique simples so' no puxador dela; duplo direto no puxador tambem isola. Acessorio ja' ativo conserva selecao. Outra gaveta/grupo nao herda esse escopo; objetos comuns e paredes continuam nativos.
- Internos (387): perguntar Esconder portas? Sim/Nao antes da captura; Sim usa visibilidade.definir(PORTAS), arame nativo com snap. Faixa olho/lapis fixa em gaveta.py segue aba, incluindo caixas/trilhos/puxadores. H/Alt+H independentes. Flag SKIP_SAVE portas_verificadas evita repetir pergunta nas continuacoes pontos/volume/tipo. Raio superficial atravessa esmaecidos; alvos_snap conserva sua geometria e extras do grupo visual.
- Alt edita 3 pontos: duas quinas da frente + profundidade. Snap NATIVO pelo
  translate do cursor; Esc restaura cursor E alvos.
- Redimensionar move pela face proxima sem crescer. Consumir a folga real
  entre as faces de apoio antes de diminuir; `espaco_disponivel` usa caixas
  nativas fora da HUD. Adaptar so' quando nao couber, ate' o minimo fisico;
  devolver escolhas ao aumentar. Largura individual menor tambem se conserva.
  `sincronizar_margens` atende gavetas E prateleiras apos o transporte.
- Referenciais conservam reflexao do Mirror do grupo: normalizar colunas, nao converter em quaternion.
- Edicao direta preserva selecao; Esc restaura medidas. Vinculo e' PAI real:
  nome antigo gravado no preset nao manda.
- Frente CURVA e alturas em PROPORCAO. Borda de CADA gaveta cede/recebe altura
  da vizinha, total fixo; externa ancora limite. Gaveta unica usa seu vao.
- Duplo abre campos individuais L/A/P, Abaixo/Acima, frente/trilho/recuo/puxador;
  grupo edita todas. Curso e material sao por unidade.
- Previa SO' parametros/contorno; montar UMA vez no confirmar.
- Criar gavetas depois de divisorias tambem chama `particionar_grupo`;
  rejeicao de vao nao deve deixar conjunto parcialmente criado.
- Snap de criacao (377): fixar_modulo_criacao captura modulo SELECIONADO e nomes dos descendentes antes do primeiro translate; sem selecao, primeiro ponto valido fixa o alvo. alvos_snap limita todos os pontos e a identificacao por closest_point_on_mesh nativo, sem ray cast global. Rejeitar nome externo; nunca trocar o alvo pelo contexto atual. raio_no_modulo atende o primeiro clique do volume livre por BVHs nativos so' dos membros visiveis. Restaurar hide_select/cursor em confirmar/Esc/erro; nao revelar ocultos. HUD/B de area_criacao tambem bloqueia externos, mantendo o resto da HUD sem essa restricao.
- Protocolo compartilhado: `cabinet_marcar_ponto_vao` usa snap nativo,
  sem varredura Python de malhas no clique/arraste. Restaurar cursor no
  confirmar/Esc, undo unico. `translate.orient_matrix` recebe eixos em LINHAS:
  transpor a Matrix do grupo (colunas), senao arrasta girado ao contrario.

## Suites

Em `../../tests/`: `test_gavetas_blender.py`; gesto compartilhado/particao:
`test_prateleiras_blender.py`, `test_divisorias_blender.py`.
Selecao, slider e filhos: suites hud, operadores e portas.
Harness e eventos reais: [tests](../../tests/AGENTS.md).
