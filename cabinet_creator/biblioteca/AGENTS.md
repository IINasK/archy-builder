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
| `*.png` | Foto 512x512 com o mesmo nome base do `.blend`. |
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
- `n1/n2/n3`: primeiros niveis da arvore em `biblioteca.py`; o indice
  estende os ramos dinamicamente. Ramo sem nivel 3 usa `"n3": ""`.
- `niveis` (opcional): o caminho INTEIRO quando passa de 3 (pedido do
  usuario: sem limite) -- `["Armarios", "Cozinha", "Altos", "Despenseiros"]`;
  n1/n2/n3 continuam com os 3 primeiros. Leia sempre por `caminho_de`
  (`_niveis_de` so' devolve os 3 primeiros). O catalogo e' o caminho todo.
- Opcionais: `foto`, `ordem` (posicao na grade), `bloqueado` (cadeado por
  item), `caixa` (wireframe do arraste sem abrir o .blend; `bytes` invalida).
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

`gerar_armarios_nativos.py` e `ARMARIOS_NATIVOS` continuam para testes,
fora da biblioteca real. Preview so' DEPOIS de remover as pecas da cena:
`aplicar_preview_png` recarrega/regrava e nomes ainda presentes viravam `.001`.

## Modulos do Promob

> Decisao do usuario: a biblioteca usa SO' os modulos do Promob, com as
> abas dele: a PASTA e' a aba (Altos, Ilhas, Sup Baixos...), o ARQUIVO a
> categoria. O caminho atual tem 4 ou mais niveis, pelo campo `niveis`:
> Armarios > Cozinha > Inferiores > Cantos. As pastas Cantos/ e Bifond/
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
- PORTA curva adotada na importacao usa folha nativa e controle explicito
  do add-on; malha curvada pelo Tab nao ativa curva parametrica.
Ferragem, puxador, cesto, eletro e decoracao NUNCA viram peca; o PISO
(chapa deitada > 1,5 m2 com <= 6 mm, ou por baixo de 80% das pecas) sai.
Portas em L/diagonal: placa/braco do Promob revelam a face e as alturas;
vao orientado segue vertices reais (cabinet_canto/vN), inclusive R/angulo.
Folha articulada segue sua folha de apoio (placa/caneco nativos, nao Reta
de carcaca flutuando); ferragens pertencem so' ao grupo mais proximo.
Junta sem apoio/ciclo: usar a lateral externa que existe na caixa.
Ainda fica chapa a com dobradica EMBAIXO (tombador nao implementado).
Os niveis: Armarios > Ambiente > ABA > CATEGORIA (4 niveis).
Pecas que se encostam viram UM modulo: na cena do Promob os modulos
precisam de espaco entre si. Os arquivos da biblioteca do Promob NAO
servem: o .entity e' receita do motor dele (formulas), sem as pecas; o
.model de fabricante e' criptografado.

Encaixes (v230): o Promob deixa base/tampo 3 mm para dentro da extremidade
das laterais. `promob.ajustar_encaixes` leva essas chapas deitadas a' quina
externa (tolerancia ate' 3,1 mm); conserva E, contornos, UID, portas/gavetas
e dimensoes externas; refaz as ancoras da montagem. Prateleiras internas,
fundo em canal e recuos maiores nao entram. Aplicado tambem ao importar.
Presets existentes: `ajustar_encaixes_promob.py -- --destino PASTA_BACKUP`
prepara/reabre/verifica .blend + fotos/previews FORA da biblioteca e guarda
originais. Depois `--aplicar` publica os mesmos nomes, checando hashes;
indice, nomes e UUIDs de catalogo permanecem. NUNCA rode isso dentro de teste.
13/10/2026: auditados 182 presets Promob; corrigidos 172 (269 chapas,
deslocamentos de -3/+3 mm), com fotos e previews. Conferencia apos publicar:
zero folgas desse tipo, dimensoes externas preservadas em todos. Originais
em Documentos/Cabinet Creator Backups/encaixes-20261013 (manifesto + hashes).

## Cuidados

Portas (v231): `ajustar_portas_promob.py` prepara fora da biblioteca,
substitui so' portas usando os DXFs da categoria, restaura chapas que
viraram portas por engano e converte frentes de canto antes fixas.
Conserva chapas restantes (UID/geometria/encaixes), materiais, puxadores,
nomes de arquivo e UUIDs; reabre e verifica .blend/foto antes de --aplicar.
Alturas por folha sao referencias normalizadas, substituidas ao editar
qtd/margem manualmente; nao contar a plaquinha como outra dobradica.
Calco da Reta pode andar para fora tambem (meia cobertura); nao clamar
em zero e deixar a placa a 7 mm da divisoria. Editor conserva referencias
sem edicao de margem/qtd; slots OBJECT conservados na migracao.
14/10/2026: 96 presets corrigidos, 26 chapas antes confundidas com portas
restauradas e 68 frentes antes fixas integradas. 339 apoios de dobradicas
verificados em contato. Backup: Documentos/Cabinet Creator Backups/
portas-20261014-preparo5. Fotos de canto: 100%/50%; .blend fechado.
Zig-zag nativa: 2-8 folhas, articulacoes alternadas em cadeia, volumetria
propria (placas, nos, eixo, parafusos), puxador somente na ultima folha.
v232: `ajustar_dobradicas_promob.py` corrige somente ferragens dos apoios
obliquos, sem reconstruir portas/chapas. A placa inteira encosta na face
real: 4 vertices coplanares + espessura para fora; nao usar so' a menor
distancia de um canto. Arame e malha preservam o prisma inclinado.

v233: `auditar_integracao_promob.py` compara cada preset ao DXF e testa
selecao, sliders, abertura e editar/restaurar, inclusive depois de salvar.
182 presets auditados; 134 corrigidos: 113 gavetas nativas (antes 96) e
220 prateleiras com vaos LIVRES nas chapas originais. Ilhas por FACE real,
laterais antes confundidas com frente restauradas; proporcoes/coberturas
das frentes preservadas. Materiais, UID, geometria mundial do corpo e
catalogos verificados. Backup: Documentos/Cabinet Creator Backups/
integracao-20261014-preparo11 (manifesto esperado/antes/depois por preset).
Atualiza BIBLIOTECA; exemplares antigos na cena precisam ser reinseridos. Formato BLENDER17 de 5.x; 4.2.1 nao le (valida so' codigo).

v236: `ajustar_fundos_portas_promob.py`: 25 fundos recuados a 15 mm e
4 ilhas de frente unica (Inferior 02/03, Superior 01/05); 29 presets.
Frente oposta substituida por fundo nativo 5 mm, cantos preservados.
Prateleiras e caixas reencaixadas; fundos parciais conservam o perfil.
Backup: Documentos/Cabinet Creator Backups/fundos-portas-20261014-preparo3.
v237: primeira porta na foto a' esquerda, demais fechadas (canto 100%/50%); contorno das quinas, sem triangulacao. v238: abertura REAL esquerda com apoio; cadeias coplanares invertidas. ajustar_abertura_esquerda.py (backup esquerda-20261014-preparo2).
Montagem intacta; atualizar_fotos_biblioteca.py valida releitura/hashes. Backup: Documentos/Cabinet Creator Backups/fotos-20261014-preparo1.

v241: Sup Medios > Cantos (11): reconstruidos do DXF por
`refinar_cantos_promob.py`. Fundos em L guardam margens em CADA plano;
fundo parcial nao vira o retangulo da caixa (antes alargava 75 mm).
Base/tampo na quina: divisorias que encostavam acompanham a face interna.
Coberturas/gaps exatos, normal da chapa sem ruido da placa; apoio diagonal
usa ferragem angular nossa. Perfil embaixo; curva com perfil na borda reta (v306),
folha nativa que conserva malha/flecha e acompanha R c/ abertura preservada.
Historico v241: arquivo fechado e foto 100%/50%; releitura/abertura/contato auditados. v243: TODAS as portas fechadas nas fotos/previews, sem mudar lado/ferragens. Backup: Documentos/Cabinet Creator Backups/fotos-fechadas-20261015-v243 (183 modulos).
Indice, nomes, UUIDs e materiais conservados. Backup final: Documentos/Cabinet Creator Backups/cantos-20261015-preparo7; originais iniciais no preparo6.
v244: 33 cantos com portas reconstruidos dos DXF (Inferiores/Sup Baixos/Sup Medios): ripas estreitas e arremates conservados, painel fixo sem articulacao entre folhas, folga de 2 mm. Backup: cantos-apoios244-{supmedios,supbaixos,inferiores-validado}. Inferiores 07/12 ja' nao tinham folhas funcionais e foram preservados. v245: mesmos 33 com referencias de face e rig Reta nas folhas planas com apoio perpendicular; copos auditados dentro da folha. Backup cantos-reta245-{medios,baixos,inferiores}. v246: +220 modelos, 408 presets totais; 30 categorias preparadas (26 novas + 4 revistas). Cozinha inclui Sup Altos, restantes Sup Medios e Portas (32 madeira, 12 aluminio); Quartos inclui Armarios/Bancadas/Escritorios/Cabeceiras/Superiores. Canto 05 e 08 separados em A/B com medidas individuais, perfil na frente local. Auditoria: 259 assets, 246 folhas, 12 grupos de gavetas, 149 grupos de prateleiras. Backup: bibliotecas246-preparo (originais/novos/manifesto/auditoria). Atualizar preset nao substitui exemplares ja' inseridos. v252: mesmos 32 Diagonais com extremidades livres das chapas reais, contorno do perfil e previa superior corrigidos; BVH sem intersecoes, backup diagonais252-final; refinar_diagonais252.py. v251: 32 Diagonais corrigidos pelo perfil do tampo; 12 frentes antes modeladas integradas, puxador/Alt na tangente e apoios em contato. Resize 100 mm/retorno auditado; corpo/UID/materiais/catalogo conservados. Backup diagonais251-validado; refinar_diagonais251.py. v249: 405 modulos auditados; soldas automaticas por area positiva de apoio, UID residual limpo, ancoras manuais preservadas; 8557 -> 3129 ligacoes. Canto Sup Alto 11: ripa alinhada de 3..1053 para 0..1056 mm, nova foto fechada. Backup/releitura/hash: conexoes249-preparo; refinar_biblioteca249.py. v306: TODO puxador e' PERFIL (pedido do usuario), `padronizar_puxador_perfil.py`: 142 modulos; 37 alcas viraram perfil na MESMA borda (curvas: a vertical, reta), 147 folhas sem puxador ganharam perfil pela regra da importacao (curva na lateral), 8 gavetas NENHUM -> perfil. Releitura: 505 perfis, 0 porta sem puxador. Perfil gravado SEM o material do modelo, como os antigos (+1,6 MB). Backup puxador-perfil-20261024-preparo4. v307: Bancadas Quarto 01/02/05 tinham a FRENTE da porta curva invertida (dobradica por fora, abrindo para dentro): virada por `_virar_porta_modelada` com a madeira no lugar; dobradica na face real por dentro e, na 01/02 (ponta em linha com a lateral), 'Apoio Dobradica' 15 mm na altura da porta (escolha do usuario), cortada na base interna. Bancada 03: perfil saiu da borda das dobradicas. `corrigir_portas_curvas_invertidas.py`, backup portas-curvas-20261024-preparo2. v308: perfil SEMPRE horizontal salvo guarda-roupa (pedido do usuario): 95 modulos refeitos por `padronizar_puxador_perfil.py` (Altos pela altura da mao; folhas curvas ganharam referencia de frentes). Releitura: 51 verticais, todos em Quartos > Armarios. Backup puxador-horizontal-20261024-preparo1. v310: EXCLUIDOS 11 modulos com folha presa em OUTRA folha por dobradica (sanfona; pedido do usuario: nao e' modelo real): Despenseiro Alto 03/04, Balcao 11, Inferior Ilha 05/06, Armario Quarto 02/06, Bifold 01/02 (catalogo Cantos Bifold saiu) e Canto Quarto Armario 07/12. Nao reimportar folha articulada para a biblioteca. v333: EXCLUIDOS 21 modulos com folha de porta CURVA (pedido do usuario): Diagonal 01/02, Diagonal Sup Baixo 02/03, Sup Alto 01/02, Sup Medio 01/02, Diagonal Quarto Armario 01/02, Canto 08B, Canto Sup Alto 01, Sup Baixo 05, Sup Medio 03, Canto Quarto Armario 02, Canto Quarto Bancada 01, Canto Quarto Superior 02 e Bancada Quarto 01/02/03/05; diagonais de porta reta chanfrada ficam. Backup portas-curvas-remocao-20261025; 2 copias em tests/fixtures. v341: retirados tambem Balcao 09/15 (frentes curvas ainda como chapas comuns) e Gaveteiro 01/03 (frentes em arco); recepcoes curvas e diagonais chanfrados ficam por escolha do usuario. Backup frentes-curvas-remocao-20261025-v341. v342: internos preparados/reabertos com vaos sem sobreposicao, recortes locais e costuras reparadas; separadores fixos continuam na estrutura. Laterais do Gaveteiro 19/Mesa de Cabeceira 04 restauradas do DXF; Armario Quarto 08 tem quatro gavetas nativas. Fotos, previews e caixas do indice atualizados; backup internos342-preparo.

v350: retirados 10 diagonais restantes com `porta_curva_modelada` e 34 variantes repetidas/espelhadas; retas/chanfradas e recepcoes curvas continuam. Geometria, materiais e sistemas auditados nos 369 modulos; conservada orientacao mais visivel da foto frontal direita, empate conserva ordinal. Nomes/UUIDs/bytes dos mantidos intactos. `consolidar_variantes_biblioteca.py`: plano externo, backup/hashes, indice atomico e rollback. Originais: Documentos/Cabinet Creator Backups/variantes350-20261025; auditoria/escolhas no irmao variantes350-auditoria. Mirror e' transformacao NATIVA do GRUPO no Object Mode; nao aplicar modificador duplicador em cada chapa. Atualizacao nao remove exemplares ja' inseridos.

- `.blend`/`.png` sao binarios no `.gitattributes`; nunca edite como texto.
- Nao commitar `*.blend1`/`*.blend2` (backups do Blender, ja' ignorados).
- Os `.blend` contem as props `eh_chapa`, `chapa_*`, `adj_*`, `chapa_uid`:
  qualquer renomeacao dessas props no codigo quebra estes presets.
- `build.py` empacota esta pasta inteira no zip (inclusive este `.md`). Estado conferido: 328 assets (325 modulos e 3 objetos), com indice/arquivo/foto/catalogo consistentes. Scripts de preparo validam pasta externa por caminho real, inclusive junction/case no Windows; publicacao confere hashes/backup e tem rollback (suite migracoes).
