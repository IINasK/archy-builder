# Setor modulos

## Papel e fronteiras

Corpo do armario, envelope, Empty/Collection e dependentes fundo/travessas.
Portas e internos conservam seus dominios; forma individual e' de
[chapas](../chapas/AGENTS.md). Solda, ancoras, comodo e orcamento:
[montagem](../../planejamento/setores/montagem/AGENTS.md).
Adocao Promob/migracoes: [integracao](../../planejamento/setores/integracao/AGENTS.md).

## Localizar tarefas

| Tarefa | Funcao / arquivo |
|---|---|
| Criar ou agrupar | `criar_armario`, `agrupar_chapas` em `__init__.py` |
| Nome/pasta do modulo | `_nome_livre`, `nomear_grupo`, `_garantir_colecao_modulo` em `__init__.py` |
| Envelope e resize | `medir_conjunto`, `redimensionar_conjunto`, `redimensionar_grupo` em `__init__.py` |
| Resize nos eixos de um modulo na parede girada | `redimensionar_orientado` em `__init__.py` |
| Fundos por dois pontos, canal/pregado/interno e hitbox | `../fundos.py`: `criar`, `atualizar_internos`, `verificar` |
| Fundo e margens | `adicionar_fundo`, `guardar_formato_fundo`, `ajustar_fundo` em `__init__.py` |
| Travessas e dependentes | `adicionar_travessas`, `ajustar_dependentes` em `__init__.py` |
| Sistemas apos resize/solda/HUD | `atualizar_sistemas_do_conjunto` em `__init__.py` |

## Decisoes e armadilhas

- Grupo = Empty + Collection de MESMO nome, escolhido por `_nome_livre`,
  na raiz, contendo chapas e porta. A porta guarda o NOME do modulo.
- Renomear por F3 abre dialogo; Corrente juntando SOLTAS usa campo.
  Solda/comodo garantem a Collection ANTES da filiacao.
- Preset sem marca reutiliza SOMENTE a pasta exclusiva de mesmo nome.
  Pasta compartilhada nunca vira modulo.
- Fundo legado: 5 mm, canal a 15 mm, entra 7 mm; fundo E travessas sao dependentes.
  Promob exige recuo MINIMO de 15 mm.
- Fundos 360: aba propria, dois pontos/snap nativo pelo AssistenteDoVao.
  Canal 6/9 mm com Boolean EXACT nao destrutivo; pregado por fora; interno
  rente (15 mm seleciona esse tipo). Legados nao migram automaticamente.
  Vao dos internos exclui fundos novos: mover o fundo nao amplia a estrutura.
  Vinculo por UID e pai real, somente com sobreposicao; snap a ate 5 mm, ou
  colisao de um fundo novo. Timer apos G/Tab adapta profundidade/trilho,
  preserva altura/frente; sem capacidade, devolve a pose valida e avisa.
  UNPINNED desassocia e preserva medidas; ignorado ate novo snap explicito.
  Novo sistema em fundos.py; legado permanece neste pacote por contrato.
- Fundos parciais/ortogonais guardam margens por PLANO; nunca expandir pela
  caixa inteira do armario.
- Base/tampo deslocados: alongar a divisoria que ENCOSTAVA na face real,
  fechando a nova fresta. Nao escolher apoio apenas pela caixa nominal.
- Ilhas: frente unica (+X/-Y da foto); a oposta vira fundo, cantos ficam.
- Migracoes de fundo/portas: `ajustar_fundos_portas_promob.py` e
  `refinar_cantos_promob.py`, na raiz, com backup e preparo validado.
- `atualizar_sistemas_do_conjunto`: corpo pronto -> portas -> gavetas ->
  prateleiras, cada uma UMA vez. `internos=False` so' portas: a volta a'
  referencia conserva os encaixes ja' restaurados, nao remontar internos ali.
  Resize, espessura, formas, HUD e solda entram por esse coordenador.
  Portas escreve folhas em `portas.atualizar_do_conjunto`; a antiga
  `portas.atualizar_portas_do_conjunto(..., sistemas=...)` so' traduz a API
  externa para este dono. Nao chamar a fachada legada dentro do add-on.
  Sem estado/cache, servico generico ou funcao capturada: patches e recarga
  resolvem cada dominio no modulo de origem. Referencias: guia de chapas.
- Solda unica (359): grupo solto/resize consultam o mapa de restricoes
  axiais em lote; a aresta pode estar no outro extremo, sem ampliar o
  escopo estrito a ligacoes reversas que nunca existiram.
- S nativo com internos: `absorver_conjuntos(no_timer=True)` mede a caixa
  nativa escalada e usa o resize comum no timer. O depsgraph apenas adia;
  nao absorver a escala herdada nas chapas antes disso, nem multiplicar
  os internos. Preservar o canto resultante do pivo da escala.
- Mirror do GRUPO conserva escala unitaria com sinal no Empty. Eixos de
  vao/forma conservam a paridade; quaternion descarta a reflexao. Recentrar
  modulo refletido move so' a translacao dos filhos, sem inverter chapas.
  S depois de R mede nos eixos locais e usa `redimensionar_orientado`.

## Suites

Em `../../tests/`: `test_armarios_blender.py`, `test_operadores_blender.py`,
`test_hud_blender.py`; dependentes/importados: `test_importacao_blender.py`,
`test_migracoes_blender.py` e suites portas/gavetas/prateleiras.
Harness e fixtures: [tests](../../tests/AGENTS.md).
