# Cabinet Creator - instrucoes globais

AGENTS.md e CLAUDE.md sao espelhos: mude os dois juntos. Maximo 200 linhas.
Codigo, UI, commits e nomes em portugues ASCII. Comentario explica o porque.

## Leia somente o setor da tarefa

Comece em [ARQUITETURA.md](ARQUITETURA.md): tabela pedido -> dono -> guia -> testes.
Antes de editar, leia explicitamente o guia indicado, inclusive para arquivos
que continuam na raiz. Nao carregue todos os guias; instrucoes por pasta
so' entram automaticamente quando o cliente percorre aquele diretorio.
UI visivel exige tambem [DESIGN.md](DESIGN.md); frentes, [FRONTES.md](FRONTES.md).
Testes: [tests/AGENTS.md](tests/AGENTS.md). Assets: [biblioteca](cabinet_creator/biblioteca/AGENTS.md).

## Projeto e extensao

Add-on Blender (bl_info 4.0; testes 4.2 e 5.2). Chapas BMesh, modulo Empty +
Collection. Gaveta = menu GPU em VIEW_3D; gavetas = caixas do movel.
Seis dominios sao pacotes homonimos; UI/integracoes mantem arquivos atuais.
O __init__ raiz carrega, liga e registra. Entre modulos, SEMPRE `_modulo.nome`
(ligado por `_ligar_modulos`); `from . import`/`from .. import` so' ao carregar.
Nao importar funcao solta de outro dominio. Teste troca no modulo dono
(`addon.portas.x`), nunca no pacote raiz. Nomes publicos/ID props sao contratos.
Nao criar abstracoes ou mover funcoes apenas por quantidade de linhas.

## Comandos e verificacao

```
python vincular_blender.py [versao]
python build.py
blender --background --factory-startup --python tests/rodar_testes.py
```

Sem python no PATH: Blender 5.2/5.2/python/bin/python.exe.
Durante trabalho, harness com `-- --suites <area>`; antes de entregar, completo.
Nova funcionalidade exige teste e tests/FUNCIONALIDADES.md; piso so' sobe.
Cada bug corrigido exige cenario reproduzivel que demonstre a falha antiga.
Cada melhoria exige cenario com parametros e resultados esperados. Criar
cenas/fixtures temporarias; nao modificar o projeto aberto nem a biblioteca.
`--gui` ABRE Blender: so' com usuario liberando o PC AGORA.
Falha em test_estrutura_blender.py significa decisao intencional: confirme
antes de enfraquecer a regra. Mudanca arquitetural pedida preserva o contrato
no teste atualizado. Testes nunca escrevem na biblioteca real.
Cada entrega incrementa bl_info["version"] (atual 364).

## Preferencias globais

- Nao delegar automaticamente; somente com pedido explicito para a tarefa atual.
- SNAP: reutilizar SEMPRE o motor nativo do Blender quando aplicavel. Nao
  varrer malhas Python no clique/arraste, inclusive criando internos. Cursor
  temporario restaura ao confirmar/Esc; undo unico. `translate.orient_matrix`
  recebe eixos em LINHAS: transpor a Matrix do grupo, que armazena colunas.

## Invariantes — NAO quebrar
1. Chapa: X = largura, Y = comprimento, Z = espessura. Orientacao por
   rotacao, nunca escala; `sz` sempre descartado.
2. Nomes gravados nos .blend (renomear quebra a biblioteca): `eh_chapa`,
   `eh_conjunto_chapa`, `chapa_*`, `conj_*`, `adj_*`, `chapa_uid`,
   `eh_grupo_portas`, `eh_folha_porta`, `porta_*`, `eh_acessorio`,
   `eh_puxador`, `puxador_*`, `eh_colecao_modulo`, `eh_colecao_comodo`,
  `eh_moldura_porta`, `eh_fundo_modulo`, `fundo_recuo_mm`, `fundo_margens_mm`, `fundo_recuo_base_mm`, `eh_travessa_modulo`,
  `travessa_lado`, `parede_*`, `cabinet_parede_uid`, `cabinet_canto`, `cabinet_forma_angulo`, `cabinet_material`, `eh_peca_curva`,
  `eh_grupo_gavetas`, `eh_gaveta`, `gaveta_*`, `gavetas_*`, `eh_grupo_prateleiras`, `eh_prateleira`,
  `prateleira_*`, `prateleiras_*`, `forma_edicao`, `chapa_edicao`.
3. Marcadores sao ID props (`MARCA_CHAPA in obj`); props de `bpy.props`
   sao RNA e NAO aparecem em `"x" in obj`. Nao troque um pelo outro.
4. Escrita de prop com `update=` feita por codigo: dentro de `_ocupado[0] = True; try/finally`.
   Callbacks `_upd_*` e o handler voltam cedo com `_ocupado[0]`. Malha DEPOIS do `finally`.
5. Geometria em MUNDO (`_eixos`, `_centro`, `_cantos`); posicao por `_definir_centro` (pai).
6. `view_layer.update()` antes de ler `matrix_world` depois de mexer.
7. Vizinho por UID, nao por nome (preset inserido vira `.001`).
8. Espessura LIVRE (`_espessura_livre`, > 0; > 60 mm = campo vermelho): nada de arredondar.
9. Malha por bmesh: o 5.2 nao escreve input de Geometry Nodes (#160038).
10. Malha modelada nunca e' substituida (`_esticar_malha` estica). `chapa_auto` e' residuo.
11. `bpy.ops` nao roda em `register()`: adie com `bpy.app.timers`.
12. Tudo registrado sai no `unregister()`: classe em `CLASSES`, prop,
    handler, TIMER, keymap. Estado global em lista de 1 elemento, zerado ali.
13. Uma biblioteca so' (`pasta_biblioteca()`), entradas antigas limpas ANTES
    do add. Catalogo DENTRO do .blend (`catalog_id`; mover = `refiliar_preset`)
    e UUID que nunca muda (`RAIZES_ANTIGAS` migram). O .cats.txt e' atomico e
    so' se muda (`_gravar_se_mudou`): dois Blenders davam UUID novo a tudo.
14. `_niveis_de` aceita o indice antigo `categoria/subcategoria`: manter.
15. Clique esquerdo na viewport e' do add-on (keyconfig ADDON). O `poll` de `OBJECT_OT_selecionar`
    da' False fora do Object Mode ou com `selecao_por_grupo` desligada -- e' assim que o clique
    nativo volta. Props dele SKIP_SAVE. Objeto comum e' do CLICK nativo: nao recriar.
16. `sincronizar_contornos` so' religa o overlay que ELE desligou.

## Armadilhas da API (confirmadas; nao "consertar")
- `Mesh.unit_test_compare` cai no 4.2 com atributos incompativeis: conferir
  nomes/dominios/tipos ANTES de chamar o comparador nativo.
- Erro em callback de desenho/gizmo/timer o Blender so' IMPRIME (a UI some
  calada; o harness GUI reprova). Desenho: nunca hashear acao (dict). Biblioteca/menu: gizmos em pool (so' ocultar); campos conservam operador ligado, atualizam dica. Remover/religar no redraw caia em WM_gizmomap_tooltip_init.
- `popup_menu` em `--background` derruba o Blender: `_abrir_pergunta`.
- Objeto guardado em estado global (hover da HUD) vira memoria liberada
  no Ctrl+Z/abrir/apagar -- o release nao invalida -- e o crash sai em
  lugar aleatorio. Guarde NOME; o hover e' limpo em `undo_pre` e
  conferido por `_alvo_vivo` (so' `as_pointer()`, sem ler o objeto).
- Depsgraph E timer durante Ctrl+Z/Shift+Z (`_desfazendo`): nada de selecao/malhas. Fecho do undo SO' libera a guarda; reconstruir referencias no timer normal. Limpar transicoes antigas de Edit Mode/modal ao invalidar. Absorver Tab so' mede/recentra, NUNCA chama gerar_malha_chapa/BMesh.to_mesh; `Mesh.is_editmode` bloqueia escritas tambem por instancias fora de Edit Mode.
  Selecao dos grupos por `select_get`, nunca `view_layer.objects.selected`.
- Operador MODAL terminado segue vivo (REGISTER): objeto da cena em `self`
  no Ctrl+Z seguinte corrompia a memoria do Python. `_larga_dados_ao_terminar`
  envolve invoke/modal/cancel INCLUSIVE herdados de mixin e solta (inclusive chave de dict). Assistente com excecao encerra handlers/timer/snap antes de propagar.
- Pop-up aberto num PRESS nasce sob o mouse e o RELEASE do mesmo clique
  responde a 1a opcao. Botao da gaveta que abre pop-up/modal dispara no
  SOLTAR (`OPERADORES_NO_SOLTAR`); o gizmo de icone tambem dispara no
  PRESS e, se abrir modal, prende os cliques da gaveta.
- `bpy.ops` em operador: `esperar_soltar`. Modal sem DOUBLE_CLICK: `_duplo_clique_na_foto`.
- Keyconfig do USUARIO guarda a ordem dele (`head=True` nao adianta): clique
  que tem de ganhar da selecao e' GIZMO (antes do keymap), como o slider.
- `GIZMO_GT_button_2d` nao aceita clique com modificador: Alt+clique na
  corrente/regua e' do keymap `cabinet_clique_corrente`.
- UILayout: sem widget novo nem px (`ui_units_x`); `template_asset_view` saiu no 5.x.
  `asset_generate_preview()` e' assincrono (perde o `libraries.write`): `aplicar_preview_png`.
- `Window.width/height` read-only: Asset Browser = AREA (`area_split`); shelf: `region_toggle`.
  `bound_box` de curva/texto/meta: por `to_mesh()` (`TIPOS_BBOX_INFIEL`). Escala no modal `S`
  nao se intercepta: o handler age quando ele termina.

## Git e residuos

Commit em portugues, terceira pessoa, so' a pedido; push so' a pedido.
Fora do git: dist/, *.blend1, __pycache__. Nome antigo "Chapa G3"
(tag chapa-g3); props de Object/Scene ficam. Preserve mudancas pendentes.
