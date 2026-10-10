# CLAUDE.md — biblioteca/ (presets de fabrica)

> **REGRA:** este CLAUDE.md NAO pode passar de 200 linhas (mesmo limite do
> CLAUDE.md da raiz). Visao geral e invariantes gerais estao em
> `../../CLAUDE.md`.

## Papel desta pasta

E' a biblioteca DA EMPRESA -- a unica. `pasta_biblioteca()` aponta para
ca' e o Blender a registra como a unica biblioteca de assets do add-on,
chamada `Cabinet Creator`. Salvar pela UI grava aqui.

Nao existe mais o par fabrica/equipe: era ele que produzia duas entradas
no seletor do Asset Browser. O cadeado virou por item (`bloqueado` no
indice); nada e' bloqueado so' por estar nesta pasta.

> **Cuidado:** gravar dentro do add-on so' e' seguro porque esta pasta e'
> o repositorio da empresa (junction de `vincular_blender.py`). Numa
> instalacao por `.zip`, atualizar o add-on SOBRESCREVE a pasta — nesse
> caso configure Preferences > `pasta_biblioteca` para uma pasta de rede.

## Arquivos

| Arquivo | O que e' |
|---|---|
| `*.blend` | Um arquivo por preset (`bpy.data.libraries.write`, comprimido). Binario. |
| `*.png` | Foto opcional 512x512 com o mesmo nome base do `.blend`. |
| `indice.json` | Catalogo lido pelo painel (evita abrir cada `.blend`). |
| `blender_assets.cats.txt` | Catalogos do Asset Browser (`VERSION 1`). |

## Formato do `indice.json`

Lista JSON, `indent=1`, `ensure_ascii=False`. Cada item:

```json
{
 "nome": "Nicho 600x400x300",
 "arquivo": "Nicho_600x400x300.blend",
 "tipo": "modulo",
 "n1": "Armarios", "n2": "Cozinha", "n3": "Inferiores"
}
```

- `tipo`: `"modulo"` (Collection marcada como asset; insere o conjunto) ou
  `"objeto"` (objetos soltos).
- `n1/n2/n3`: niveis da arvore `ARVORE` em `biblioteca.py`. `n1` deve ser
  chave de `ARVORE`; ramos sem nivel 3 usam `"n3": ""`.
- Opcionais: `foto` (nome do png), `ordem` (int, posicao na grade),
  `bloqueado` (bool; ignorado aqui, fabrica e' sempre bloqueada).
- Formato legado `categoria`/`subcategoria` ainda e' aceito por
  `_niveis_de` — nao gere mais, mas nao quebre a leitura.
- `arquivo` e' a chave de identidade do item (sem caminho, so' o basename).
  `pasta` e `origem` sao adicionados em memoria por `indice_completo()`
  e NAO devem ser gravados no JSON.

## Catalogos (`blender_assets.cats.txt`)

- Linha: `UUID:caminho/do/catalogo:nome_simples`.
- Os `.blend` guardam o UUID do catalogo no `asset_data`. NAO troque os
  UUIDs existentes, senao os assets somem do catalogo no Asset Browser.
- O arquivo e' GERADO por `_garantir_catalogos()`: a cascata inteira da
  `ARVORE` sob a raiz UNICA `Cabinet Creator`. Nao edite a mao — rode a
  funcao apontando para esta pasta e commite o resultado.
- Raizes antigas (`RAIZES_ANTIGAS`, hoje `Chapa G3`) sao RENOMEADAS
  mantendo o UUID. Renomear o caminho e' seguro; trocar o UUID nao.
- O nivel 1 e' exatamente o do painel N (chaves da `ARVORE`). Os
  catalogos por TIPO (`Chapas`/`Modulos`) so' existem como fallback de
  quem salva sem categoria — nao entram na cascata.
- Cada preset e' arquivado no catalogo da sua CATEGORIA (`n1/n2/n3` do
  indice), nao mais por tipo. Para mover um preset de categoria use
  `refiliar_preset()`: o catalogo mora dentro do `.blend`, mudar so' o
  indice.json nao surte efeito no Asset Browser.

## Cuidados

- `.blend`/`.png` sao binarios no `.gitattributes`; nunca edite como texto.
- Nao commitar `*.blend1`/`*.blend2` (backups do Blender, ja' ignorados).
- Os `.blend` contem as props `eh_chapa`, `chapa_*`, `adj_*`, `chapa_uid`:
  qualquer renomeacao dessas props no codigo quebra estes presets.
- `build.py` empacota esta pasta inteira no zip (inclusive este `.md`).
