# Setor prateleiras

## Papel e fronteiras

Prateleiras internas, quantidade, vaos e edicao individual/coletiva.
Gesto e referencial compartilhados com [gavetas](../gavetas/AGENTS.md):
`AssistenteDoVao`; segmentacao pertence a [divisorias](../divisorias/AGENTS.md).
Menu/HUD despacham para este dominio; malha base pertence a [chapas](../chapas/AGENTS.md).

## Localizar tarefas

| Tarefa | Funcao / arquivo |
|---|---|
| Vaos e calculo | `vaos`, `calcular`, `mover_vao` em `__init__.py` |
| Criar/montar/resize | `criar_prateleiras`, `montar`, `atualizar_do_conjunto` em `__init__.py` |
| Exclusao e centralizacao | `sincronizar_exclusoes`, `OBJECT_OT_alinhar_prateleiras` em `__init__.py` |
| G nativo / cotas reais | `_sincronizar_disposicao`, `sincronizar_exclusoes_da_cena` em `__init__.py` |
| Parametros e quantidade | `editar`, `editar_individual`, `resolver_referencia` em `__init__.py` |
| Subdivisao local / copias | `detalhamento`, `editar_quantidade_local`, `CHAVE_DETALHAMENTO` em `__init__.py` |
| Tab e propagacao | `iniciar_edicao`, `edicao_atual`, `concluir_edicao` em `__init__.py` |
| Escolha de referencia/assistente | `OBJECT_OT_referencia_prateleira`, `OBJECT_OT_criar_prateleiras` em `__init__.py` |

## Decisoes e armadilhas

- Aba propria. Mesmo `AssistenteDoVao` das gavetas: SO' 2 cliques + scroll.
  Profundidade ate' o FUNDO; folga da frente e' RECUO. Usar/gravar a mesma
  referencia do vao das gavetas; seguir seu protocolo de snap nativo.
- Menu: campos E de BAIXO para CIMA, apenas os do escopo selecionado.
  Sem Igual/Livre, Entre prateleiras ou Abaixo/Acima.
- Quantidade: grupo = total/global; unidade = ela e suas copias, distribuidas
  SO' entre os apoios externos inferior/superior. UID `prateleira_detalhamento_uid`
  nas chapas, sem Empty/caixa extra; limites derivados dos vaos atuais. Selecionar
  qualquer copia reencontra o trecho. Fora dele, nada move/remonta (inclui gavetas).
  Reduzir conserva a ativa; zero apaga so' o trecho; capacidade valida ANTES de copiar.
  Parametros e Centralizar locais abrangem as copias. Tab individual continua nativo.
  Local mostra so' os campos E do trecho, contador local e moldura entre apoios;
  moldura nao redimensiona o bloco global. Ultimo E anda a ultima copia, nao o apoio.
  Contador guarda o NOME do alvo (unidade/grupo), inclusive digitacao/previa/Esc.
  Referencia explicita na API continua global; copia global nao herda UID do detalhe.
- "Centralizar espacamento" fica na secao Espacamento, simbolo
  seta esquerda/barra/seta direita, altura 37; nunca junto ao contador.
  Grupo selecionado: distribui todas. Unidade sem subdivisoes: iguala SO'
  os vaos acima/abaixo; com copias, redistribui SO' o trecho local.
- Excluir atualiza quantidade/vaos SEM mover sobreviventes; SO' o botao
  redistribui. Mudar UM vao anda SO' uma prateleira; o vizinho cede.
- G nativo (Objeto ou Tab individual/global): cotas seguem as caixas nativas
  no referencial do vao apos confirmar/sair; nao remontar nem mover vizinhas.
  Se cruzarem, reordenar E/indices de baixo para cima, levando ajustes com a
  chapa. Descartar encaixe antigo; sincronizar so' fora de modal/Edit/undo,
  depois de absorver Tab. Nao varrer vertices nem medir no redraw.
- Clique = todas, duplo = uma; HUD exibe L/A/P do vao E o VALOR de cada vao.
  Parametros individuais nao movem vizinhas.
- Sao as mesmas chapas: Tab no grupo propaga a todas ao concluir, em Edit
  Mode multiobjeto NATIVO; individual isola a malha.
- NUNCA trocar ID de Mesh ao concluir: `BMesh.to_mesh` na MESMA malha,
  pois undo nativo guarda o ID. Undo voltando ao Edit Mode recupera
  o escopo da selecao nativa.
- Quantidade herda geometria, parametros, material E modificadores da unidade
  selecionada. Tipos diferentes sem unidade ativa pedem
  "Selecione a prateleira de referencia" junto ao mouse na viewport;
  aviso acompanha cursor, respeita bordas e Esc cancela SEM adicionar.
- Arrastar quantidade so' exibe previa; montar ao SOLTAR.
- Montagem identica nao reescreve pose/medidas nem atualiza o depsgraph:
  isso invalidava os BVHs nativos ao usar a regua em outra chapa.
- Resize do modulo conserva o bloco enquanto couber: transporte/capacidade
  compartilhados com gavetas; `ajustar_ao_espaco` guarda a escolha e
  `atualizar_do_conjunto` remonta. Nao voltar a margens fixas que crescem
  com a caixa. Esc do modulo restaura tambem vao/margens/parametros/encaixe.
- Criar apos divisorias respeita `particionar_grupo`; cortes preservam
  altura/material/recortes. Regras de travessia e apoios estao no guia de divisorias.

## Suites

Em `../../tests/`: `test_prateleiras_blender.py`; gesto/particao:
`test_gavetas_blender.py`, `test_divisorias_blender.py`.
Tab/undo e apresentacao: suites operadores, formas, hud e gaveta.
Harness e fixtures: [tests](../../tests/AGENTS.md).
