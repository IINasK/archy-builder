# CLAUDE.md — biblioteca/ (presets de fabrica)

> **REGRA:** este CLAUDE.md NAO pode passar de 200 linhas (mesmo limite do
> CLAUDE.md da raiz). Visao geral e invariantes gerais estao em
> `../../CLAUDE.md`.

## Papel desta pasta

Presets que viajam DENTRO do add-on (`_pasta_fabrica()`). E' registrada no
Blender como biblioteca de assets "Cabinet Creator (fabrica)". Ao atualizar
o add-on a pasta e' sobrescrita, por isso:

- o codigo NUNCA grava aqui — gravacoes vao para a pasta da equipe
  (Preferences > `pasta_equipe`, padrao `~/Documents/Blender/Assets/Cabinet Creator`);
- itens daqui aparecem sempre bloqueados na UI (`item_bloqueado`).

Para adicionar um preset de fabrica: salve pela UI (vai para a pasta da
equipe) e copie `.blend` + `.png` + a entrada do `indice.json` para ca'.

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
- `n1/n2/n3`: niveis da arvore `ARVORE` em `__init__.py`. `n1` deve ser
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
- Aqui os caminhos ainda sao `Chapa G3/Chapas` e `Chapa G3/Modulos`
  (nome antigo), enquanto o codigo usa `Cabinet Creator/...` para a pasta
  da equipe. Divergencia conhecida; nao "corrigir" sem checar os presets.

## Cuidados

- `.blend`/`.png` sao binarios no `.gitattributes`; nunca edite como texto.
- Nao commitar `*.blend1`/`*.blend2` (backups do Blender, ja' ignorados).
- Os `.blend` contem as props `eh_chapa`, `chapa_*`, `adj_*`, `chapa_uid`:
  qualquer renomeacao dessas props no codigo quebra estes presets.
- `build.py` empacota esta pasta inteira no zip (inclusive este `.md`).
