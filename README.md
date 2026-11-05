<p align="center">
  <img src="docs/boas-vindas.svg" alt="Archy Builder - moveis planejados, arquitetura e interiores no Blender" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-em_desenvolvimento-f28c28" alt="Em desenvolvimento">
  <img src="https://img.shields.io/badge/preco-gratuito-26966f" alt="Gratuito">
  <a href="LICENSE"><img src="https://img.shields.io/badge/licenca-CC0_1.0-4269d0" alt="CC0 1.0 Universal"></a>
  <img src="https://img.shields.io/badge/Blender-testes_4.2_e_5.2-e87d0d" alt="Testado em Blender 4.2 e 5.2">
</p>

<p align="center">
  <a href="#comece-aqui">Comece aqui</a> &nbsp; | &nbsp;
  <a href="#o-que-voce-pode-criar">Recursos</a> &nbsp; | &nbsp;
  <a href="https://github.com/IINasK/archy-builder/issues">Relatar um problema</a> &nbsp; | &nbsp;
  <a href="CONTRIBUIR.md">Contribuir</a>
</p>

# Bem-vindo ao Archy Builder

Um add-on gratuito para **moveis planejados, marcenaria, arquitetura e
interiores no Blender**. Crie armarios, chapas, portas, gavetas e prateleiras,
organize ambientes e integre o mobiliario a paredes, pisos, tetos e instalacoes
em desenvolvimento.

**O projeto e' completamente gratuito e esta' em desenvolvimento ativo.**
Voce pode estudar, copiar, modificar, redistribuir e usar o conteudo autoral
do projeto, inclusive comercialmente, sem pagar licenca e sem pedir permissao.
A dedicacao [CC0 1.0 Universal](LICENSE) formaliza essa liberdade, no limite
permitido por lei. Veja o [escopo e os creditos](NOTICE).

> **Versao de desenvolvimento.** Recursos, interface e formatos internos
> podem mudar; ainda existem bugs. Experimente em uma copia do seu projeto
> e mantenha seus arquivos originais salvos.

## O que voce pode criar

| Area | O que oferece |
| --- | --- |
| **Armarios e chapas** | Modulos editaveis, malhas reais e controle de espessura das chapas. |
| **Portas e ferragens** | Folhas, tipos de abertura, puxadores e dobradicas associados. |
| **Gavetas e internos** | Gavetas, prateleiras, divisorias e fundos com medidas e espacamentos. |
| **Biblioteca** | Presets, materiais, categorias e insercao por arraste. |
| **Alvenaria** | Identificacao de paredes, piso e teto, ambientes e edicao em vista 2D. |
| **Instalacoes blocadas** | Portas, janelas, spots, pendente, eletrica e rebaixo de teto em desenvolvimento. |
| **Trabalho no Blender** | Selecao por conjunto ou peca, cotas editaveis e integracao com ferramentas nativas. |

As instalacoes arquitetonicas ainda sao representacoes simplificadas.
O add-on nao substitui a verificacao tecnica de um projeto executivo.

## Comece aqui

### 1. Obtenha o projeto

Use **Code -> Download ZIP** no GitHub e extraia o arquivo, ou clone:

```sh
git clone https://github.com/IINasK/archy-builder.git
cd archy-builder
```

### 2. Gere o arquivo instalavel

Com Python 3 disponivel, execute na pasta do projeto:

```sh
python build.py
```

O comando cria **`dist/archy_builder.zip`**, incluindo a biblioteca e a licenca.
Esse e' o ZIP instalavel; o ZIP de codigo-fonte do GitHub precisa ser extraido
e empacotado antes.

No Windows, se nao houver Python no PATH, pode usar o Python do Blender:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' build.py
```

### 3. Instale no Blender

Abra **Edit -> Preferences** e escolha **Install from Disk** nas opcoes
de complementos/extensoes da sua versao. Selecione `archy_builder.zip`
e habilite **Archy Builder**.

Os testes automatizados cobrem **Blender 4.2 e 5.2**. Os presets salvos
no Blender 5.x podem nao abrir no 4.2; a compatibilidade do codigo e da
biblioteca e' verificada separadamente.

### Compatibilidade com projetos anteriores

Archy Builder e' o novo nome do Cabinet Creator (antes Chapa G3).
A pasta tecnica `cabinet_creator`, preferencias, atalhos, propriedades e
tipos de editor foram preservados para continuar abrindo projetos antigos.
Instale a atualizacao sobre o add-on existente; nao e' necessario recriar
moveis ou converter seus arquivos. Catalogos conservam seus UUIDs.

### 4. Experimente

Abra o editor **Archy Builder** pelo seletor de editores do Blender.
Explore as abas de modulos, portas, fundos, gavetas, prateleiras/divisorias,
puxadores e alvenaria. A selecao determina os controles apresentados.

## Participe do desenvolvimento

Voce e' bem-vindo para testar, sugerir melhorias ou enviar alteracoes.

- **Encontrou um bug?** Abra uma [issue](https://github.com/IINasK/archy-builder/issues/new)
  com a versao do Blender, os passos para reproduzir e o resultado esperado.
- **Quer melhorar o codigo?** Leia [CONTRIBUIR.md](CONTRIBUIR.md) e o
  [mapa de arquitetura](ARQUITETURA.md), depois envie um pull request.
- **Vai corrigir um bug?** Inclua um teste de regressao e registre o cenario
  em [FUNCIONALIDADES.md](tests/FUNCIONALIDADES.md).

Os testes usam cenas descartaveis. Nunca execute uma suite sobre seu arquivo
de trabalho aberto. Instrucoes completas em [tests/AGENTS.md](tests/AGENTS.md).

## Documentacao do projeto

| Para quem | Onde comecar |
| --- | --- |
| Quer contribuir | [Guia de contribuicao](CONTRIBUIR.md) |
| Quer encontrar uma funcao | [Arquitetura e setores](ARQUITETURA.md) |
| Vai alterar a interface do add-on | [Padrao de design](DESIGN.md) |
| Quer conferir cenarios e testes | [Funcionalidades verificadas](tests/FUNCIONALIDADES.md) |
| Quer consultar etapas anteriores | [Historico preservado](docs/HISTORICO.md) |

## Liberdade de uso

**Sem cobranca e sem exclusividade sobre o conteudo autoral disponibilizado
sob CC0.** Faca seu fork, adapte o projeto e compartilhe suas melhorias.
Creditos sao bem-vindos, mas nao sao exigidos pela CC0.

A dedicacao nao altera licencas ou direitos de terceiros, nem direitos
sobre marcas e patentes. O Blender e' um projeto independente e mantem
sua propria licenca. O Archy Builder e' fornecido sem garantias.

[Texto integral CC0](LICENSE) &nbsp; | &nbsp; [Escopo e creditos](NOTICE)
