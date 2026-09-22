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
| MODULO (CONJUNTO) | `redimensionar_grupo`, `aplicar_espessura_grupo`, `reposicionar_origem`, `absorver_conjuntos` |
| BIBLIOTECA / ASSETS | `registrar_bibliotecas`, `salvar_na_biblioteca`, `_garantir_catalogos` |
| ARVORE (3 niveis) | `ARVORE`, `_niveis_de`, `indice_completo`, `registrar_no_indice` |
| MINIATURAS | `icone_do_item`, `capturar_viewport` (render OpenGL 512x512) |
| BLOQUEIO/RENOMEAR/ORDEM | operadores de edicao dos blocos da grade |
| REDE DE SEGURANCA | `verificar_periodicamente` (timer 0.2 s) |
| CRIACAO | `nova_chapa`, criar chapa/nicho, modo Grupo (`_upd_grupo_*`) |
| UI | `CabinetCreatorPreferences`, `VIEW3D_PT_cabinet_creator` |
| registro | `CLASSES`, `register()` (props em Object/Scene), `unregister()` |

### Fluxo de recalculo

1. Usuario escala (`S`) chapa ou Empty. Durante o modal NADA e' tocado —
   o operador nativo reaplica a escala em cache a cada movimento.
2. Ao terminar o modal, o handler de depsgraph (ou, se nenhuma atualizacao
   chegar, o timer de 0.2 s) chama `absorver_conjuntos()` e depois
   `normalizar_chapas()`.
3. `normalizar_chapas` converte sx/sy em largura/comprimento, zera a
   escala, regenera a malha e chama `aplicar_adjacencia()` para fechar os
   vaos (vao por lado = (E/2)*(F-1)).
4. Medidas de modulo (props `conj_*` no Empty, ou `grupo_*` na Scene no modo
   Grupo) chamam `redimensionar_grupo` / `aplicar_espessura_grupo` e
   depois `reposicionar_origem` (Empty no centro X/Y e base Z).

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
11. **Pasta de fabrica e' somente leitura:** gravacoes vao SEMPRE para a
    pasta da equipe (`_pasta_equipe()`); presets de fabrica sao sempre
    bloqueados (`item_bloqueado`).
12. **Retrocompatibilidade do indice:** `_niveis_de` aceita o formato antigo
    `categoria/subcategoria`. Nao remova esse fallback.
13. Todo novo `Operator`/`Panel` entra na tupla `CLASSES`; toda nova prop em
    `register()` e todo handler/timer tem remocao em `unregister()`.

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
- A cada entrega relevante, incrementar `bl_info["version"]` (hoje 33.0.0).

## Git

- Mensagens de commit em portugues, verbo no presente, 3a pessoa
  ("Renomeia...", "Trata pasta somente-leitura...").
- `dist/`, `*.blend1`, `__pycache__` sao ignorados. `.blend` e `.png` sao
  binarios (nao tente editar/diffar como texto).

## Pendencias / residuos conhecidos

- Residuos do nome antigo "Chapa G3" ainda em uso: tag de asset
  `chapa-g3`, descricao `"Modulo G3 - ..."`, operador "Converte ... em chapa
  G3", e os caminhos de catalogo no `blender_assets.cats.txt` de fabrica
  (`Chapa G3/...`) diferem de `CAT_CHAPAS`/`CAT_MODULOS`
  (`Cabinet Creator/...`). Avaliar impacto nos presets antes de mudar.
- `_itens_de` usa o formato antigo do indice e nao tem chamadores.
- `unregister()` nao remove as props registradas em `Object`/`Scene`.

## Limitacoes da API (nao "consertar")

- Reordenar blocos so' por setas: bpy nao expoe arraste em paineis.
- Nao da' para sobrepor icone a imagem no layout do bpy.
- Largura da sidebar e' do usuario, nao do add-on.
- Corrigir escala durante o modal `S` nao funciona (ver HANDLER).
