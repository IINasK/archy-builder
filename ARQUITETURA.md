# Mapa de setores

Leia a raiz e apenas o guia da tarefa. Nao carregue todos os guias.
Os pares AGENTS.md/CLAUDE.md contem o mesmo texto para clientes diferentes.
Ao trabalhar da raiz, abra explicitamente o guia indicado: a descoberta
automatica do Codex segue o caminho ate' o diretorio de trabalho, nao links.

## Onde comecar

| Pedido ou sintoma | Dono / entrada | Guia | Suites |
|---|---|---|---|
| Criar prateleiras/divisorias no mesmo volume, lacunas e continuidade | `areas_criacao.py`: sessao/perguntas; `divisorias/`: plano e recorte nativo | [Interface](planejamento/setores/interface/AGENTS.md) + [Divisorias](cabinet_creator/divisorias/AGENTS.md) | areas_criacao, divisorias, prateleiras, gaveta |
| Definir area por tres pontos sem ordem/frente explicita ou caixa/plano livre | `areas_criacao.py`; HUD compartilhada e entrega aos assistentes atuais | [Interface](planejamento/setores/interface/AGENTS.md) + [Gavetas](cabinet_creator/gavetas/AGENTS.md) | areas_criacao, hud, gaveta, portas |
| Malha, E, Tab, cotas A1..An, angulo individual | `chapas/`; `formas.py`, `geometria.py`, `frentes.py` | [Chapas](cabinet_creator/chapas/AGENTS.md) | formas, geometria, frentes, hud |
| Caixa do armario, resize, pasta no Outliner, fundo/travessas | `modulos/`: `criar_armario`, `redimensionar_conjunto`, `ajustar_dependentes` | [Modulos](cabinet_creator/modulos/AGENTS.md) | armarios, operadores, hud |
| Folha, vao, cobertura, abertura, puxador ou dobradica | `portas/`; `assistente.py`, `ferragens.py`, `puxadores.py`, `portas_viewport.py` | [Portas](cabinet_creator/portas/AGENTS.md) | portas, puxadores, frentes |
| Fundos em canal/pregado/interno e vinculo de profundidade | `fundos.py`; legado em `modulos/` | [Modulos](cabinet_creator/modulos/AGENTS.md) + [Interface](planejamento/setores/interface/AGENTS.md) | fundos, armarios, gavetas, prateleiras, gaveta |
| Gaveta do MOVEL, trilho, frente, alturas individuais | `gavetas/`: `calcular`, `montar`, `editar_individual` | [Gavetas](cabinet_creator/gavetas/AGENTS.md) | gavetas |
| Quantidade, exclusao, vaos E1..En, redistribuir prateleiras | `prateleiras/`: `sincronizar_exclusoes`, `mover_vao`, `montar` | [Prateleiras](cabinet_creator/prateleiras/AGENTS.md) | prateleiras |
| Dividir sistemas por uma chapa vertical | `divisorias/`: `criar_divisorias`, `particionar_grupo`, `atualizar_dependentes` | [Divisorias](cabinet_creator/divisorias/AGENTS.md) | divisorias, gavetas, prateleiras |
| Menu esquerdo, clique/duplo/Alt, cotas e hover da viewport | `gaveta*.py`, `hud.py`, `selecao.py`, `eventos.py` | [Interface](planejamento/setores/interface/AGENTS.md) | gaveta, hud, estrutura, snapshot |
| Numeros, unidades, selecao e undo da escrita | `opcoes.py`: `_texto_medida`; `gaveta_desenho.py`: `_tecla_no_texto`, `_apresentacao_medida`, parser nativo | [Interface](planejamento/setores/interface/AGENTS.md) | medidas, gaveta, hud, paredes_composicao, snapshot |
| Esmaecer partes por aba, agregados e editar grupo visual | `visibilidade.py`: arame nativo, membros por UID, restauracao; `gaveta.py`: faixa fixa | [Interface](planejamento/setores/interface/AGENTS.md) | visibilidade, areas_criacao, gaveta, estrutura |
| Editor Cabinet Creator, persistencia da area e comandos na cena | `editor.py`; layout/eventos em `gaveta*.py` | [Interface](planejamento/setores/interface/AGENTS.md) | editor, gaveta, biblioteca_faixa, estrutura |
| Faixa de fotos, abas, rolagem, materiais e Ctrl+L | `biblioteca_faixa.py`, `materiais.py`; catalogo em `biblioteca.py` | [Interface](planejamento/setores/interface/AGENTS.md) + [Assets](cabinet_creator/biblioteca/AGENTS.md) | biblioteca_faixa, biblioteca, hud |
| Solda, ancora, gap, juntar/desvincular, comodo/orcamento | `solda.py`, `modulos/`, `paredes.py`, `orcamento.py` | [Montagem](planejamento/setores/montagem/AGENTS.md) | solda, hud, paredes, orcamento |
| Selecionar parede por vertices/area/hover, isolamento e composicao 2D | `paredes_selecao.py`, `paredes_edicao.py`, `paredes_composicao.py`; vinculo em `paredes.py`, resize em `modulos/` | [Montagem](planejamento/setores/montagem/AGENTS.md) + [Interface](planejamento/setores/interface/AGENTS.md) | paredes_selecao, paredes_composicao, paredes_edicao, paredes, gaveta |
| DXF/Promob, adocao, presets, migracoes | `promob.py`, `importacao.py`, scripts `integrar_*`/`ajustar_*` | [Integracao](planejamento/setores/integracao/AGENTS.md) | importacao, migracoes, biblioteca |
| Register, unregister, timers, ordem de carga, recarga | `__init__.py`, `eventos.py`, `opcoes.py` | [Raiz](AGENTS.md) | organizacao, estrutura, cobertura |
| Harness ou fixture | `tests/` | [Testes](tests/AGENTS.md) | cobertura + suite alterada |

Os caminhos Python da tabela sao relativos a `cabinet_creator/`.
Os guias em `planejamento/setores/` sao consulta explicita; nao mudam
automaticamente o escopo das instrucoes dos arquivos Python.

## Fronteiras e fluxo

Resize visual da caixa: `hud.py` desenha/seleciona; `hud_volume.py` entrega
o arraste ao translate nativo (B escolhe a base do snap). A geometria
continua no dono da cota, sem um segundo solver no controlador visual.

1. `__init__.py` importa na ordem declarada, liga `_nome` em `_ligar_modulos`
   e registra classes/propriedades/handlers. A lista `_MODULOS` e' explicita.
2. O operador recebe o gesto; o dominio calcula/valida e aplica; interface
   apenas apresenta e despacha. Calculos novos pertencem ao dominio.
3. HUD e menu chamam o mesmo contrato do dominio. `gaveta` e' o MENU;
   `gavetas` sao as caixas do movel. Nao misturar os dois.
4. `gavetas.AssistenteDoVao` fornece o gesto nativo compartilhado por
   prateleiras/divisorias/wizard de porta; `gavetas.iniciar_cursor_nativo`,
   o dos arrastes com Alt (canto da porta, ancora da solda, quina da HUD).
   Snap e' sempre o nativo. Corrigir o protocolo comum ali, nao copiar.
5. `modulos.atualizar_sistemas_do_conjunto` coordena portas -> gavetas ->
   prateleiras, uma chamada por dominio; `internos=False` conserva encaixes
   restaurados. Portas so' aplica suas folhas. A entrada antiga
   `portas.atualizar_portas_do_conjunto` permanece como compatibilidade,
   nunca como chamador interno de resize/solda/HUD/formas.
6. `divisorias` segmenta gavetas/prateleiras, que continuam donos dos grupos
   resultantes. `frentes.py` produz a referencia comum (ver [FRONTES.md](FRONTES.md)).

## Contrato desta organizacao

- Os seis setores sao pacotes Python homonimos; a implementacao existente
  fica em `__init__.py`. `cabinet_creator.portas` conserva nome e identidade.
- Os setores conservam suas APIs. A coordenacao de atualizacao pertence ao
  modulo, sem novo solver/registro de servicos; cada dominio escreve sua geometria.
  Nao dividir funcoes por tamanho nem afirmar que todo acoplamento desapareceu.
- `assistente.py`, UI e integracoes continuam na raiz do pacote. Seus guias
  indicam os arquivos exatos; nao ha' fachadas ou copias de implementacao.
- `biblioteca/`, `ferragens/` e `fotos/` sao RECURSOS. Nao adicionar
  `__init__.py` nessas pastas: homonimos `biblioteca.py`/`ferragens.py` existem.
- Para extrair uma responsabilidade futura: contrato e testes primeiro,
  mova uma unidade coesa, preserve patches no modulo dono e ajuste recarga
  explicita se criar submodulo. Nao adicionar carregador magico ou `import *`.
- Nao misture corrigir comportamento com mover codigo na mesma etapa de
  revisao. Mudancas pendentes anteriores continuam separadas no diff.

## Busca e manutencao

Comece com `rg -n '^def |^class ' cabinet_creator/portas` ou pelo nome de
funcao da tabela; leia o trecho, depois siga so' as dependencias usadas.
Use `rg --files cabinet_creator/portas` para inventario. Para o menu, busque
primeiro o verbo de acao em `gaveta.py` e seu despacho em `gaveta_eventos.py`.
Nao comece abrindo todos os arquivos nem toda a biblioteca binaria.

Ao mudar um contrato, atualize o guia dono e seu espelho; o indice so'
muda se a rota/responsabilidade mudou. Limites: raiz <=200 linhas, guias
novos <=120; mapas de funcoes nao substituem docstrings de implementacao.

Validacao: suite da area durante o trabalho; harness completo antes da
entrega. `organizacao` verifica imports/identidade/recarga; `estrutura`
confere todos os modulos E pacotes contra a ordem de carga.

## Referencias da decisao

- [Python: pacotes e imports relativos](https://docs.python.org/3/tutorial/modules.html#packages).
- [OpenAI Docs: instrucao global e por diretorio](https://developers.openai.com/codex/guides/agents-md).
- [Google Engineering: mudancas coesas e refatoracao separada](https://google.github.io/eng-practices/review/developer/small-cls.html).

Aplicacao local dessas referencias: dominio coeso, contexto sob demanda,
compatibilidade e revisao verificavel. Nao e' certificacao de arquitetura
nem medicao de economia de tokens.
