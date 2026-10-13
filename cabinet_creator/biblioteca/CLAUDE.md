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
- `niveis` (opcional): o caminho INTEIRO quando passa de 3 (pedido do
  usuario: sem limite) -- `["Armarios", "Cozinha", "Altos", "Despenseiros"]`;
  n1/n2/n3 continuam com os 3 primeiros. Leia sempre por `caminho_de`
  (`_niveis_de` so' devolve os 3 primeiros). O catalogo e' o caminho todo.
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

## Armarios nativos de fabrica

> Decisao do usuario: a biblioteca usa SO' os modulos do Promob. Os 39
> nativos foram APAGADOS; o gerador continua no add-on (e nos testes),
> mas nao rode na biblioteca real sem pedido.

`gerar_armarios_nativos.py` (raiz do repo, `--background`, Blender 5.x)
grava os 39 de `biblioteca.ARMARIOS_NATIVOS` (caixa 18 mm -- balcao e gabinete
com topo ABERTO, duas travessas (`TOPO_POR_TIPO`) -- + fundo 5 mm em
canal + porta Reta pelo `porta_no_modulo`: giro de 1 folha ate' 500 mm, 2
acima; aereos tambem basculantes) e o PERFIL de puxador (`PERFIL_POR_TIPO`:
balcao/gabinete em cima, aereo embaixo, torre/roupeiro na vertical do lado
da abertura). Foto por camera/Workbench
(`fotografar_com_camera`), sem janela, com a porta ENTREABERTA (fechadas,
giro e basculante saiam iguais); o .blend e' gravado com ela fechada.
Rodar de novo regrava os mesmos arquivos e linhas do indice. A preview vai
DEPOIS de tirar as pecas da cena: `aplicar_preview_png` recarrega e regrava
o .blend, e com elas na cena tudo virava `.001`.

## Modulos do Promob

> Decisao do usuario: a biblioteca usa SO' os modulos do Promob, com as
> abas dele: a PASTA e' a aba (Altos, Ilhas, Sup Baixos...), o ARQUIVO a
> categoria. Como a biblioteca tem 3 niveis, as duas vao juntas no 3o:
> Armarios > Cozinha > "Inferiores - Cantos". As pastas Cantos/ e Bifond/
> das primeiras exportacoes sao Inferiores (`importacao.categoria_promob`).

`importar_promob.py` (raiz, `--background`, Blender 5.x) le
`Documentos/Promob/<Ambiente>/<Aba>/<Categoria>.dxf`. Nome: "Canto 01
LxAxP" (P sem a porta: a frente vira porta nativa); fora de Inferiores
leva a aba ("Canto Sup Baixo 01") -- o mesmo "Canto 01" de duas abas
gravava um por cima do outro. Rodar de novo substitui pelo nome; se o
nome MUDAR (outra regra de importacao), tire antes os presets antigos do
indice (os de n3 "Aba - Categoria") e os .blend/.png deles. O DXF do
Promob tem uma CAMADA por peca (3DFACE/polyface, mm, Z para cima, frente
-Y) e a COR da camada diz o que e' (7 chapa, 253 ferragem, 254 aluminio
e vidro, 8 puxador, 28 acessorio, 250-252 eletro). Pedido do usuario:
INTEGRACAO, nao copia -- o modulo vira o NOSSO (`promob`):
- CHAPA (cor 7, >= 3 mm, lados >= 50 mm), inclusive a de contorno curvo;
- frente com DOBRADICA -> porta nativa (dobradica nossa; o lado dela vai
  para a cobertura Reta/Curva do add-on); com CAIXA de MDF ou CESTO
  aramado atras -> gavetas nativas (trilho nosso, alturas em proporcao,
  frente curva com flecha); QUADRO de aluminio (cor 254, 23 mm) -> porta
  de correr com a folha Quadro de aluminio (trilho nosso);
- fundo fino e travessas do topo -> as dependentes do modulo;
- PECA CURVA que nao e' gaveta (porta em arco) como acessorio
  `eh_peca_curva`, que deforma com o raio da HUD (`formas`).
Ferragem, puxador, cesto, eletro e decoracao NUNCA viram peca; o PISO
(chapa deitada > 1,5 m2 com <= 6 mm, ou por baixo de 80% das pecas) sai.
Ainda ficam chapa: frente na diagonal (a `formas` gira e estica) e a com
dobradica EMBAIXO (tombador: a basculante nossa so' abre para cima).
Os niveis: Armarios > Ambiente > ABA > CATEGORIA (4 niveis).
Pecas que se encostam viram UM modulo: na cena do Promob os modulos
precisam de espaco entre si. Os arquivos da biblioteca do Promob NAO
servem: o .entity e' receita do motor dele (formulas), sem as pecas; o
.model de fabricante e' criptografado.

## Cuidados

- `.blend`/`.png` sao binarios no `.gitattributes`; nunca edite como texto.
- Nao commitar `*.blend1`/`*.blend2` (backups do Blender, ja' ignorados).
- Os `.blend` contem as props `eh_chapa`, `chapa_*`, `adj_*`, `chapa_uid`:
  qualquer renomeacao dessas props no codigo quebra estes presets.
- `build.py` empacota esta pasta inteira no zip (inclusive este `.md`).
