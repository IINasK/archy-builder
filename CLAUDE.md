# CLAUDE.md — Cabinet Creator

> **REGRA DESTE ARQUIVO:** este CLAUDE.md NAO pode passar de 200 linhas.
> Subpastas da ferramenta podem ter seus proprios CLAUDE.md especificos,
> sujeitos ao MESMO limite de 200 linhas. Ao atualizar, enxugue antes de
> acrescentar; detalhe de uma subpasta vai no CLAUDE.md dela.
>
> CLAUDE.md existentes:
> - `CLAUDE.md` (este) — visao geral, invariantes, convencoes
> - `cabinet_creator/biblioteca/CLAUDE.md` — presets, indice.json, catalogos

## O que e'

Add-on de Blender (bl_info `blender: (4, 0, 0)`, testado ate' 5.x) para
modelar armarios de moveis planejados. Unidade basica: a **chapa** (painel
de madeira) com espessura discreta 15/18/20/30 mm, imune a escala, e malha
real gerada por bmesh (editavel em Edit Mode). Chapas se agrupam em
**modulos/conjuntos** (Empty pai com medidas externas parametricas) e podem
ser salvas numa **biblioteca** de presets com foto.

Idioma do projeto: portugues (codigo, comentarios, UI, commits).

## Comandos

```
python vincular_blender.py [versao]   # junction cabinet_creator/ -> addons do Blender
python build.py                        # gera dist/cabinet_creator.zip
python -m py_compile cabinet_creator/__init__.py   # checagem rapida de sintaxe
```

- Nao ha testes automatizados nem lint configurado. `bpy` so' existe dentro
  do Blender: a validacao real e' recarregar o add-on (desabilitar/habilitar
  em Preferences ou reiniciar o Blender) e exercitar no painel `N > Cabinet
  Creator`.
- `vincular_blender.py` usa `mklink /J` (Windows, sem admin). Sem argumento,
  pega a maior versao em `%APPDATA%/Blender Foundation/Blender`.
- `build.py` empacota TUDO dentro de `cabinet_creator/` (menos pycache),
  incluindo `biblioteca/` e qualquer `.md` que estiver la'.

## Estrutura

```
cabinet_creator/__init__.py   # o add-on inteiro (arquivo unico, por decisao)
cabinet_creator/biblioteca/   # presets de fabrica: .blend + indice.json + cats
build.py                      # empacotador
vincular_blender.py           # junction para desenvolvimento
.vscode/                      # settings (LF, utf8, 4 espacos, regua 79)
```

## Mapa do `__init__.py` (secoes marcadas por banners `# ====`)

| Secao | Funcoes-chave |
|---|---|
| topo | `gerar_malha_chapa`, `_upd_chapa`, `_upd_espessura` |
| NORMALIZACAO | `normalizar_chapas` — escala -> mm, descarta Z |
| HANDLER | `ao_atualizar_depsgraph` — age so' quando o modal termina |
| ADJACENCIA | `detectar_adjacencia`, `aplicar_adjacencia`, `_resolver_vizinho` |
| MODULO (CONJUNTO) | `redimensionar_grupo`, `aplicar_espessura_grupo`, `aplicar_espessura_chapa`, `reposicionar_origem`, `absorver_conjuntos` |
| BIBLIOTECA / ASSETS | `registrar_bibliotecas`, `salvar_na_biblioteca`, `_garantir_catalogos`, `caminhos_catalogo`, `refiliar_preset` |
| ARVORE (3 niveis) | `ARVORE`, `_niveis_de`, `indice_completo`, `registrar_no_indice` |
| MINIATURAS | `icone_do_item`, `capturar_viewport` (render OpenGL 512x512) |
| BLOQUEIO/RENOMEAR | nome, lapis e cadeado na mesma linha; ordem alfabetica |
| SELECAO | `familia_de`, `OBJECT_OT_selecionar`, `registrar_keymaps` |
| PRATELEIRA DE ASSETS | `VIEW3D_AST_cabinet_creator`, `OBJECT_OT_prateleira` |
| ARRASTE DA BIBLIOTECA | `inserir_preset`, `OBJECT_OT_arrastar_preset` |
| REDE DE SEGURANCA | `verificar_periodicamente` (timer 0.2 s) |
| CRIACAO | `nova_chapa`, criar chapa/nicho, modo Grupo (`_upd_grupo_*`) |
| UI | `VIEW3D_PT_cabinet_creator`, `medir_selecao`, `_largura_painel` (responsividade) |
| registro | `CLASSES`, `register()` (props em Object/Scene), `unregister()` |

### Fluxo de recalculo

1. Usuario escala (`S`) chapa ou Empty. Durante o modal NADA e' tocado —
   o operador nativo reaplica a escala em cache a cada movimento.
2. Ao terminar o modal, o handler de depsgraph (ou, se nenhuma atualizacao
   chegar, o timer de 0.2 s) chama `absorver_conjuntos()` e depois
   `normalizar_chapas()`.
3. `normalizar_chapas` converte sx/sy em medida, zera a escala, regenera
   a malha e chama `aplicar_adjacencia()` (vao por lado = (E/2)*(F-1)).
4. Medidas de modulo (props `conj_*` no Empty, ou `grupo_*` na Scene no modo
   Grupo) chamam `redimensionar_grupo` / `aplicar_espessura_grupo` e
   depois `reposicionar_origem` (Empty no centro X/Y e base Z).
5. Espessura de UMA chapa chama `aplicar_espessura_chapa`: ancora a face
   no limite externo do grupo e engrossa para DENTRO; a espessura antiga
   vem da malha (a prop ja' mudou quando o callback roda).

### Arraste da biblioteca (painel N)

1. O nome do preset chama diretamente o operador de posicionamento; a
   seta separada insere imediatamente no cursor 3D. A foto usa
   `template_icon`, unico widget que amplia previews, e o drag verdadeiro
   pela imagem fica na Asset Shelf nativa. Pressionar e arrastar o nome
   dispara `LEFTMOUSE/PRESS` no keymap
   "User Interface". O `PRESS` e' necessario porque o botao do Blender
   consome `CLICK_DRAG`; registrar com `head=True` impede outro item do
   keymap de bloquear o gatilho. `template_icon` apenas desenha e nao
   recebe eventos; nao prometer drag customizado pela foto do painel N.
2. `OBJECT_OT_arrastar_preset` le o preset em `context.button_operator`
   e so' aceita o botao de inserir (cadeado e lapis tambem tem
   `arquivo`). Outro arraste devolve `{'PASS_THROUGH'}`, senao sliders
   parariam de andar.
3. O preset e' carregado como staging oculto. A caixa GPU usa os cantos
   avaliados reais de todos os objetos com volume e ancora pelo centro
   inferior; a geometria definitiva so' aparece depois da confirmacao.
4. O modal faz `scene.ray_cast` sob o cursor. Quando existe superficie,
   a mira segue o ponto e a normal; sem acerto, usa o plano horizontal na
   altura do cursor 3D. A caixa verde preserva dimensoes e orientacao.
5. Movimento minimo de 6 px distingue arraste de clique simples. Quando
   o Blender retem o drag do botao, o clique simples deixa o posicionador
   ativo: mover para a viewport e clicar confirma. No drag normal, soltar
   o botao esquerdo dentro da viewport confirma. Botao direito,
   Esc, desativar a janela ou soltar fora cancela, remove objetos e
   colecoes importadas e restaura a selecao anterior.
6. Miniaturas sao PNG RGBA com fundo transparente. `capturar_viewport`
   isola e enquadra automaticamente o alvo em projecao ortografica; uma
   segunda passagem mede o alfa e ajusta o zoom para 82% da imagem. Ao
   terminar restaura vista, selecao, visibilidade e render settings.
   O botao do nome mantem `emboss=True` para o highlight no hover.
7. Salvar preset SEMPRE gera o PNG inicial; nao existe opcao `com_foto`.
   Falha na captura cancela o cadastro no indice e reporta erro.

### Medidas responsivas

1. Qualquer selecao unica com volume expoe `Object.dimensions` editavel na
   convencao L=X, A=Z, P=Y. Selecao multipla mostra a caixa conjunta apenas
   para leitura, pois nao existe uma unica escala segura para todos.
2. Abaixo de 310 px logicos, controles e wireframe ficam empilhados. Acima
   disso ficam lado a lado. Nao voltar a fixar `ui_units_x` no modo estreito.
3. No modo estreito, medidas formam grade de duas colunas: L/A na primeira
   linha e P/E na segunda. Sem E, P fica sozinha e centralizada. Abaixo de
   210 px logicos, todas as medidas formam uma unica coluna centralizada para
   preservar os rotulos completos. Os campos dessa coluna ocupam 80% da area
   util, inclusive Espessura quando existir. No modo largo os campos ficam em
   coluna, com margem esquerda e centro vertical.
4. O preview permanece com 9 unidades tanto no modo largo quanto no primeiro
   estagio empilhado. Ele so reduz progressivamente, ate o minimo de 5, quando
   a largura fisica ja nao comporta o tamanho completo.
   No layout lado a lado, a coluna de controles usa somente 4.5 unidades de UI;
   nao ampliar essa reserva, pois ela retira espaco do preview antes da quebra.
5. A rasterizacao e' recentralizada pelo bounding box alfa depois de incluir
   L/A/P/C. Sem isso, as letras laterais fazem o desenho parecer deslocado.
   Na grade impar, usar divisao 25/50/25. Cada rotulo e campo deve receber
   `alignment='CENTER'` dentro da propria celula; centralizar apenas a celula
   deixa os controles deslocados para a esquerda.

## Invariantes — NAO quebrar

1. **Eixos locais da chapa:** X = largura, Y = comprimento, Z = espessura.
   Orientacao se faz por rotacao, nunca por escala. `sz` e' sempre descartado.
2. **Nomes gravados nos .blend:** `eh_chapa`, `eh_conjunto_chapa`,
   `chapa_*`, `conj_*`, `adj_*`, `chapa_uid` estao salvos dentro dos presets.
   Renomear invalida a biblioteca. Manter mesmo sendo nomes do add-on antigo
   ("Chapa G3").
3. **Marcadores sao ID props** (`obj["eh_chapa"] = 1`) e sao testados com
   `MARCA_CHAPA in obj`. Props criadas via `bpy.props` sao RNA e NAO
   aparecem em `"x" in obj` — nao troque um pelo outro.
4. **Guarda de reentrancia `_ocupado[0]`:** toda escrita em prop com
   `update=` feita por codigo deve ficar em `_ocupado[0] = True; try: ...
   finally: _ocupado[0] = False`. Todo callback `_upd_*` e o handler
   retornam cedo se `_ocupado[0]`. Regenere malhas DEPOIS do `finally`.
5. **Espaco de mundo:** geometria via `matrix_world` (`_eixos`, `_centro`,
   `_cantos`); para gravar posicao use `_definir_centro` (respeita pai e
   `matrix_parent_inverse`). `location`/`rotation_euler` locais quebram
   quando o Empty sai da origem.
6. **Depsgraph defasado:** chame `bpy.context.view_layer.update()` antes de
   ler `matrix_world` depois de mudar medidas/posicoes.
7. **Vizinhos por UID, nao por nome:** presets inseridos ganham sufixo
   `.001`. `_resolver_vizinho` busca UID entre irmaos (mesmo pai) primeiro.
8. **Espessuras permitidas:** `ESPESSURAS_PERMITIDAS`; todo campo de
   espessura arredonda para o valor mais proximo.
9. **Malha por bmesh, nao Geometry Nodes:** Blender 5.2 nao deixa escrever
   inputs de modificador GN via Python (issue #160038).
10. **`bpy.ops` nao roda dentro de `register()`:** adie com
    `bpy.app.timers.register(..., first_interval=...)`.
11. **Uma biblioteca so'** (`pasta_biblioteca()`, default = a pasta do
    add-on): e' a da empresa. Nao ha' mais fabrica/equipe nem bloqueio
    por origem. Ao registrar, a limpeza das entradas antigas vem ANTES
    do add — invertendo, o usuario fica sem biblioteca.
12. **Retrocompatibilidade do indice:** `_niveis_de` aceita o formato antigo
    `categoria/subcategoria`. Nao remova esse fallback.
13. Todo novo `Operator`/`Panel` entra na tupla `CLASSES`; toda nova prop em
    `register()` e todo handler/timer tem remocao em `unregister()`. O mesmo
    vale para keymaps: `registrar_keymaps()` / `remover_keymaps()`.
14. **Clique esquerdo na viewport e' do addon:** as entradas ficam no
    keyconfig do ADDON (avaliado antes do padrao). O `poll` de
    `OBJECT_OT_selecionar` devolve False fora do Object Mode ou com a
    preferencia `selecao_por_grupo` desligada -- e' assim que o clique
    nativo volta. Nao troque esse poll por um `return True`.
15. **Catalogo mora dentro do `.blend`** (`asset_data.catalog_id`); o
    `indice.json` nao manda nele e `catalog_simple_name` e' somente
    leitura. Mover de categoria exige regravar (`refiliar_preset`).
16. **Raiz de catalogo unica (`CAT_RAIZ`).** Renomear o CAMINHO de um
    catalogo preserva os assets; trocar o UUID os orfana. Raizes velhas
    entram em `RAIZES_ANTIGAS` e sao migradas com o UUID intacto.

## Convencoes de codigo

- Nomes em portugues: funcoes/variaveis `snake_case`, privadas com `_`.
  Classes no padrao Blender `OBJECT_OT_<acao>`, `VIEW3D_PT_<nome>`.
- `bl_idname` de operadores: `object.cabinet_<acao>`.
- Textos e comentarios SEM acentos (ASCII); `e'` / `so'` / `ja'` no lugar
  de acento agudo. Docstring de operador = tooltip, curta.
- Comentarios explicam o PORQUE (bug encontrado, limitacao da API) — manter
  esse estilo ao alterar logica sutil.
- Estado global mutavel em listas de 1 elemento (`_ocupado = [False]`).
- Log: `print("[Cabinet Creator] contexto:", e)`; falha nao-critica e'
  capturada e logada, nunca derruba handler/timer.
- Operadores reportam via `self.report({'INFO'|'WARNING'|'ERROR'}, ...)`
  e retornam `{'CANCELLED'}` quando a selecao e' invalida.
- Unidades: props em mm, Blender em metros (`/ 1000.0`; meia medida
  `/ 2000.0`). Medidas de modulo: (Largura, Altura, Profundidade) =
  eixos de mundo (X, Z, Y).
- Formatacao: 4 espacos, LF, UTF-8 (`.gitattributes` forca `eol=lf`).
- A cada entrega relevante, incrementar `bl_info["version"]` (hoje 67.0.0).

## Git

- Mensagens de commit em portugues, verbo no presente, 3a pessoa
  ("Renomeia...", "Trata pasta somente-leitura...").
- `dist/`, `*.blend1`, `__pycache__` sao ignorados. `.blend` e `.png` sao
  binarios (nao tente editar/diffar como texto).

## Pendencias / residuos conhecidos

- Residuos do nome antigo "Chapa G3": tag `chapa-g3`, descricao
  `"Modulo G3 - ..."`, operador "Converte ... em chapa G3". A raiz de
  catalogo ja' migrou. `_itens_de` nao tem chamadores; `unregister()`
  nao remove as props de `Object`/`Scene`.
- Asset Browser ja' e' a biblioteca principal; a grade do painel N
  ainda convive com ela.

## Limitacoes da API (nao "consertar")

- Blocos e categorias usam ordem alfabetica; nao sobrepoe icone a imagem; escala
  durante o modal `S` nao da' (HANDLER).
- **O bpy nao mede texto nem avisa quanto cabe num botao** — so' corta
  pela direita. Layout responsivo e nomes resumidos saem de
  `_largura_painel()` + as estimativas `PX_*`; ajuste-as, nao procure
  uma API de medicao.
- `UILayout` nao expoe drag-and-drop e o `template_asset_view` foi
  REMOVIDO no 5.x: painel nao DESENHA item arrastavel. O arraste vem de
  fora — `CLICK_DRAG` + `context.button_operator` (ver ARRASTE).
- Arraste 100% nativo so' na `AssetShelf`: quem DESLIGA pede
  `NO_ASSET_DRAG`. `bound_box` de curva/texto/meta descreve os PONTOS DE
  CONTROLE; em `TIPOS_BBOX_INFIEL` a medida fiel sai de `to_mesh()`.
- `show_region_asset_shelf` e' "read-only" conforme o contexto; use
  `bpy.ops.screen.region_toggle(region_type='ASSET_SHELF')`.
