# CLAUDE.md -- tests/ (harness de seguranca)

> Mesmo limite do raiz: maximo 200 linhas. Inventario de funcionalidades
> e o teste de cada uma: `FUNCIONALIDADES.md` (nesta pasta).

## Rodar

```
blender --background --factory-startup --python tests/rodar_testes.py
blender ... --python tests/rodar_testes.py -- --gui        # + interface
blender ... --python tests/rodar_testes.py -- --versoes 5.2 --suites hud
blender ... --python tests/rodar_testes.py -- --atualizar  # regrava snapshots
```

Unico requisito: o Blender (o Python dele roda o executor; o `python`
do Windows nao existe nesta maquina). O executor acha todas as versoes
em `C:\Program Files\Blender Foundation`, roda cada suite num Blender
SEPARADO (`--factory-startup`, em paralelo; GUI uma por vez) e sai com
codigo 1 se algo falhar. Sem GUI ~1 min (versoes em paralelo; as mais lentas: biblioteca
e portas); durante o trabalho rode so' a suite da area.

**Antes de entregar: o executor inteiro, com `--gui` se a pessoa
liberou janela (memoria `nao-abrir-janelas`).** Suite isolada nao basta.

## Camadas (piramide de testes)

| Camada | Arquivo | Pega |
|---|---|---|
| Unidade/integracao headless | `test_*_blender.py` | logica, dados, layout por tuplas |
| Caracterizacao (golden master) | `test_snapshot_blender.py` + `snapshots/*.json` | QUALQUER mudanca de comportamento nao intencional |
| Interface com eventos reais | `gui_*.py` (+ `harness_gui.py`) | keymap, gizmo/hover, modais, sequencia real de eventos |
| Trava de cobertura | `test_cobertura_blender.py` | classe nova sem teste, teste apagado, snapshot orfao |
| Piso por suite | `PISO` em `rodar_testes.py` | suite que roda MENOS testes que antes |

## Regras

1. **Funcionalidade nova = teste novo no mesmo commit.** A trava falha
   se uma classe registrada nao e' citada por nenhum teste. Excecao so'
   em `SEM_TESTE_ACEITO` (com motivo); a lista so' encolhe.
2. **Piso so' sobe.** Suite cresceu: suba o numero em `PISO`. Baixar
   exige motivo no commit (teste removido de proposito).
3. **Snapshot mudou:** se foi de proposito, `--atualizar` e REVISE o
   diff do json no git antes do commit. Se nao foi, achou uma quebra.
   O snapshot ignora a biblioteca (depende dos presets, nao do codigo).
4. **Bug achado por teste:** escreva o teste, marque
   `@unittest.expectedFailure` com `# BUG:` em cima. Consertado, tire o
   marcador e deixe um comentario "Regressao (era BUG, corrigido na N)".
5. **Biblioteca real e' intocavel.** `test_biblioteca_blender.py` copia
   uma AMOSTRA (`copiar_amostra`: 2 presets por categoria) para um
   temporario e redireciona `pasta_biblioteca`/`_pasta_addon` ANTES do
   register; no fim confere por sha1 que nenhum byte da real mudou. A
   integridade de TODOS os presets reais e' lida direto da pasta real (so'
   leitura). Copiar a biblioteca inteira (~190 presets) estourava 300 s.
6. **Blender 4.2 nao le os .blend da biblioteca** (gravados pelo 5.x).
   Teste que abre preset real: `skipTest` em `bpy.app.version < (5,)`.
   GUI: `raise Pular(motivo)`. Nunca deixe falhar "por versao".
7. Testes ASCII, em portugues, unittest; no fim do arquivo
   `addon.register()` / roda / `addon.unregister()` / `raise RuntimeError`.

## Harness de interface (`harness_gui.py`)

Padrao oficial do Blender (`tests/python/ui_simulate`, `easy_keys`):
`--enable-event-simulate` (ignora mouse/teclado REAIS), cada teste e'
um GERADOR rodado por timer; cada `yield` = 4 tiques do loop (eventos
processados + redesenho); `yield esperar(s)` espera relogio.
`Mouse.mover/clicar/apertar/soltar/tecla/digitar`, coordenadas da
JANELA (`regiao.x + x`). Widgets da gaveta: pegue o retangulo de
`_widgets_interativos` (nunca coordenada fixa). Pontos 3D: `na_tela`.

Limites confirmados no fonte do Blender (4.2 e 5.2):
- O simulador NAO gera DOUBLE_CLICK (`check_double_click = false`).
- Operador MODAL nunca recebe DOUBLE_CLICK nem do mouse real
  (`wm_event_modalkeymap_begin` converte em PRESS). Por isso o duplo
  clique na foto e' medido pelo relogio (`_duplo_clique_na_foto`).
- DOUBLE_CLICK de KEYMAP (selecao em 3 camadas): o teste chama o
  operador com as props da entrada de `_ENTRADAS_KEYMAP`, no contexto
  real. A entrega do evento pelo Windows so' com mouse fisico.
- `popup_menu` em `--background` DERRUBA o Blender (access violation):
  o add-on so' abre pop-up com janela (`_abrir_pergunta`) e grava a
  resposta pendente; o teste responde chamando o operador da resposta.
  Na GUI, feche o pop-up com `m.tecla('ESC')` -- mover o mouse nao
  fecha, e o pop-up que sobra come o 1o clique do proximo teste.
- Erro em CALLBACK (desenho, gizmo, timer) o Blender so' IMPRIME: o
  harness troca o sys.stderr (`ErrosDeCallback`) e reprova o teste em
  que um traceback aparecer, mesmo com os asserts passando.
- Excecao num timer so' e' impressa: o harness captura tudo e sai com
  `os._exit(codigo)`; o executor tem tempo-limite por suite.

## Achados do harness (historico)

- v120: 2o clique do duplo na foto chega como PRESS (modal) -> insercao
  cancelava. Corrigido pelo relogio; coberto em `gui_interacao`.
- v126: adjacencia em dois eixos relia matrix_world defasado; S no
  Empty do modulo nao surtia efeito; timers sem remocao no unregister.
- v132: botao da gaveta que abre pop-up disparava no PRESS (gizmo
  incluso) e o RELEASE do mesmo clique respondia "Sim" sozinho.
- v141: a gaveta sumia (abas, icones, fundo) e os 26 testes de interface
  passavam: `acao[:2] in {set}` com o dict de um preset da biblioteca
  quebrava o desenho. Nasceu o `ErrosDeCallback`.
- v140: `bpy.ops` chamado de dentro de outro operador recebe o estado
  da janela, que no clique simulado ja' traz o RELEASE: quem chama de um
  PRESS avisa por prop (`esperar_soltar`), nao pelo `event`.
- v139: modal aberto pelo GIZMO de um icone da gaveta prendia os cliques
  dela (o "Confirmar" do pe' nao chegava). Botao que abre modal ou
  pop-up entra em `OPERADORES_NO_SOLTAR`.
- Abertos (expectedFailure em `test_biblioteca_blender.py`): .blend
  orfao quando a foto falha; asset salvo/refiliado vira `.001`;
  `editar_modelo` nao move o catalogo dentro do .blend.
