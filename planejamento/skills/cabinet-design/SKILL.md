---
name: cabinet-design
description: Desenha e valida controles, miniaturas, cotas e alertas no editor Archy Builder. Use ao mudar layout, interacao ou feedback visual do add-on.
---

# Design do Archy Builder

Leia primeiro o guia de interface e as secoes aplicaveis de [DESIGN.md](../../../DESIGN.md).
Use o editor Archy Builder. Layout produz a tupla de seis campos; desenho e
hit-test leem a mesma tupla, e eventos chamam o dono da acao pela ponte do editor.
Prefira o verbo, campo, botao, barra e gizmo que ja' representam a operacao.
Use cores do tema e o realce semantico existente; icones sao gizmos nativos.

Exemplo de instalacao: miniatura e nome no cartao, previa na viewport, cotas
em colunas alinhadas e tamanho em campos separados. Um aviso de colisao
aparece perto da acao e conserva a confirmacao disponivel. Medir rotulos
com BLF, inclusive nas linhas estreitas; nao cortar a acao principal.

Conferir em 190, 320 e 564 px, temas claro e escuro, clique e arraste.
Registrar o que foi verificado e executar GUI so' com o PC liberado agora.
