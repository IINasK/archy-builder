# Referencia das frentes

`cabinet_creator/cabinetry/fronts.py` fornece a geometria compartilhada por portas,
puxadores, contorno, previa e transporte durante redimensionamento.
O reconhecimento usa a propria Mesh local, independente do nome/categoria
do armario. A pose fechada vem do rig existente; abrir ou mover nao muda
a referencia local.

A HUD do modulo consome o mesmo contorno de cada folha da porta isolada.
Nao agrega folhas numa caixa nominal: ela atravessaria curvas e dobras.

- `preparar`: extrai a referencia durante montagem, importacao ou edicao.
- `referencia`: le dados numericos; nao extrai nem consulta geometria.
- `perfil`, `contorno`: superficie fisica e limites reais da madeira.
- `bordas`, `lugar`: encaixe sobre as bordas de montagem; seguem a curva.
- `normalizar_borda`, `fracao_do_ponto`: coordenada comum do segmento.
- `transportar`: consulta uma copia nativa da geometria deformada antes
  de reancorar o rig; conserva a Mesh, vertices e faces modelados.

## Persistencia e edicao

`cabinet_frente_face` (INT/FACE) distingue frente, verso e tampas.
`cabinet_frente_borda` (INT/EDGE) distingue bordas superior/inferior nas
duas superficies. Sao atributos nativos, transportados pela edicao do
Blender. Nao se gravam numeros de vertices como identidade de uma borda.

O preparo precede a captura de referencia e a deformacao. Copias nativas
antigas recebem os atributos apenas se a topologia coincide, sem trocar
a geometria original de resize. Frente/verso curvos sao distinguidos de
tampas pela consulta nativa da superficie oposta na espessura.

`cabinet_frente_referencia` e' um cache numerico na Mesh, com versao,
assinatura geometrica, caminhos e normais. Mudanca geometrica invalida
essa Mesh, incluindo todos os seus usuarios. A fila guarda nomes de
meshes e nao objetos RNA; renomeacao/undo/abrir arquivo sao recuperados
fora do desenho. O handler distingue geometria de pose. Redraw/hover
leem o cache; reconhecimento e BMesh ficam fora desses callbacks.

Uma montagem parametrica com perfil pode retirar uma faixa da madeira.
O contorno usa a madeira cortada; a borda nominal conservada pelo corte
continua sendo a referencia de montagem do puxador. Essa distincao evita
deslocar o perfil novamente ao refazer a chapa.

## Compatibilidade

`porta_linha_frente` serve como guia de migracao de presets antigos.
`porta_linha_indices` nao governa os consumidores novos. Puxadores antigos
traduzem a coordenada uma unica vez (`puxador_referencia_versao`); nunca
somam deslocamentos ao redimensionar. Sem cache, o desenho legado continua
numerico ate' o preparo pelo evento/timer.

A reconstrucao historica de diagonais do DXF continua no adaptador
de importacao. Ela remodela exportacoes antigas reconhecidas e exige
backup ao publicar assets. Nao e' usada para reconhecer a frente durante
redraw, edicao ou posicionamento: ampliar essa reconstrucao para uma
porta parcial substituiria sua geometria pela caixa inteira do armario.

## Verificacao

`tests/test_fronts_blender.py` cobre caixas, curvas/facetas, espessura
normal, verso, recortes, topologia, pose, bordas de montagem, migracao,
malhas compartilhadas, renomeacao e ausencia de varredura no redraw.
As suites portas/puxadores/importacao verificam os consumidores. A
auditoria de integracao le assets reais sem regravar a biblioteca.

A edicao angular usa a aresta nativa marcada em `cabinet_forma_angulo`
(INT/EDGE), inclusive quando chega a um canto ortogonal. A vizinha real
define o angulo interno; os limites de P1/P2 nao limitam esse angulo.
Fundos ficam fora do envelope, mas seguem o apoio com recuo normal e
espessura preservados. Chapas planas inclinadas por Tab sao reexpressas
no plano real, conservando Mesh, coordenadas mundiais, UV e usuarios.

Na 256 o solver da forma usa uma base ortonormal por secao: XY, XZ e
YZ, sem girar a cena para calcular. Arestas angulares nativas distinguem
os planos; referencia/undo conservam a base original do modulo. Sistemas
recebem o deslocamento convertido ao referencial do pai. A HUD combina
e recorta secoes numericas em cache, sem varrer malhas no redesenho.
Na chapa isolada o solver usa seu plano local e separa usuarios da Mesh;
ao sair de Tab o cache das tres secoes e' invalidado conjuntamente.

Na 380, editar apenas uma pele pode deixar frente e verso com perimetros
diferentes. Nesse caso a HUD individual usa as arestas estruturais reais,
com UID EDGE e coordenadas no cache de secao; nao extruda o perfil de
uma pele sobre a outra. A medida nominal de E nao usa o envelope ambiguo.
Redraw e hover continuam apenas numericos, sem extracao de BMesh/CDT.

Na 257, formatos obliquos livres sem classificacao parametrica usam a
uniao nativa `delaunay_2d_cdt` para encontrar os limites reais. Somente
arestas estruturais da malha, sem diagonais coplanares de triangulacao,
entram na HUD. A identidade da borda usa UID e fracoes locais, nunca
indices persistidos. Cache nao conserva RNA e nao refaz CDT/BMesh no
redesenho. O desenho continua oferecendo L/A/P, ancoragem, seta e Esc.
