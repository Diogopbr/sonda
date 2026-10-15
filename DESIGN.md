---
name: Sonda
description: Registro científico de observações HTTP e incidentes
colors:
  ink: "#183b4e"
  muted: "#526e7d"
  brand: "#0d4166"
  action: "#1264b2"
  action-hover: "#0a508f"
  ground: "#f3f8fa"
  surface: "#fff"
  line: "#c9dce5"
  blue-tint: "#e7f3f9"
  control-surface: "#e9f4fa"
  good: "#0c6b4d"
  bad: "#ad2546"
  warning: "#855400"
  recovery: "#6544a2"
  focus: "#e9ae3e"
  disabled-surface: "#e6edf0"
  disabled-text: "#637885"
  selected-row: "#e6f2f9"
typography:
  headline:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "2rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: "-0.015em"
  subheading:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 650
  body:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "1rem"
    lineHeight: 1.5
  label:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 600
  caption:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "0.875rem"
rounded:
  control: "6px"
  panel: "8px"
  dialog: "12px"
spacing:
  tight: "4px"
  compact: "8px"
  small: "12px"
  regular: "16px"
  record: "20px"
  section: "24px"
  wide: "28px"
  page: "32px"
  column: "36px"
  shell: "40px"
components:
  button-primary:
    backgroundColor: "{colors.action}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.action-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.brand}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "11px 12px"
  control-panel:
    backgroundColor: "{colors.control-surface}"
    rounded: "{rounded.panel}"
    padding: "26px 24px"
---

# Design System: Sonda

## Overview

**Creative North Star: "Registro científico de observações"**

Superfícies claras, alinhamentos precisos e registros comparáveis dão prioridade à evidência. O cabeçalho azul estabelece a identidade; o campo de leitura usa branco frio, texto de tinta e pouca ornamentação. Estado observado, idade da resposta e próxima ação orientam a leitura.

**Key Characteristics:**

- Registros alinhados com numerais tabulares.
- Estados escritos por extenso e acompanhados de sinal visual.
- Superfícies planas com separadores e agrupamentos tonais.
- Dados equivalentes em tabela para a sequência visual de amostras.

## Colors

Azul profundo identifica a aplicação; azul de ação marca controles e links. Tinta e cinza azulado sustentam leitura e contexto. Os valores normativos estão no frontmatter e correspondem a `frontend/src/app.css`.

- **Primary:** brand no cabeçalho e nas linhas superiores dos registros; action nos botões principais, links e seleção.
- **Neutral:** ground no fundo, surface nos registros, ink no texto, muted nos detalhes e line nos separadores.
- **Estados:** good para resposta saudável; bad para falha; warning para atenção; recovery para recuperação. O estado quiet usa muted. Blue-tint contextualiza o ambiente; control-surface agrupa a próxima observação.

**The Evidência Rule.** Toda cor de estado acompanha texto legível; ponto ou faixa colorida não substitui o registro.

## Typography

Source Sans 3 é a única família, com fallback sans-serif. A fonte variável local atende pesos de 400 a 800, com `font-display: swap`. O arquivo é `frontend/public/fonts/source-sans3-latin.woff2`; sua licença SIL Open Font License 1.1 acompanha a distribuição em `frontend/public/fonts/OFL.txt`.

A escala fixa preserva comparação entre páginas: título principal, título de seção, subtítulo, corpo, rótulo e legenda estão no frontmatter. Títulos de histórico usam 1.25rem; a leitura atual destacada usa 1.75rem. No celular, o título principal passa a 1.75rem. A entrada mantém entrelinha 1.3 no título. Parágrafos gerais têm limite de 70ch. Datas, durações e códigos HTTP usam numerais tabulares; não há família monoespaçada de exibição.

## Layout

O contêiner tem largura máxima de 1280px, margem automática e laterais de 32px. O conteúdo inicia com 40px de respiro. Detalhes usam uma coluna flexível de evidências e outra de controles com 330px, separadas por 36px. Até 1000px, controles passam a 290px e o intervalo a 24px.

Até 760px, o conteúdo usa laterais de 20px e respiro superior de 28px. Cabeçalho e ações de sessão quebram em linhas; detalhes e entrada passam a uma coluna. Tabelas recompõem cada registro em campos com rótulos explícitos. Seus cabeçalhos continuam disponíveis de forma visualmente oculta.

Nos detalhes de serviço e incidente, o link **Verificar ou alterar cenário** aparece após o cabeçalho de estado no celular. Ele leva a `#next-observation`, rola até a seção e transfere o foco. Existe uma única instância dos controles; a sequência de evidências continua antes deles na ordem do documento.

## Elevation & Depth

Registros e painéis são planos. Linhas, fundos tonais e espaçamento indicam agrupamento. A única sombra pertence ao diálogo de reinício: `0 18px 48px #112f4a33`, com backdrop `#0a2c48aa`. Não aplicar essa elevação aos registros comuns.

## Shapes

Controles e amostras têm cantos discretos; painéis têm curva um pouco maior e o diálogo concentra o raio mais amplo. Os registros tabulares permanecem retos. Pontos de estado são circulares, com 8px; marcas de amostra são barras retangulares de 22 × 6px. Bordas de 1px separam campos e registros; linhas superiores de 2px identificam o registro de serviços e o livro de evidências.

## Components

- **Botões:** altura mínima de 44px, peso 600, variante principal azul e secundária branca com borda. Hover escurece a ação principal e tonaliza a secundária. Botões indisponíveis usam fundo e texto específicos, cursor de indisponibilidade e a propriedade nativa disabled; operações em andamento alteram também o texto.
- **Campos:** fundo branco, borda azul acinzentada, rótulo persistente e ajuda contextual. Select tem mínimo de 46px; textarea permite expansão vertical e começa em 118px. Conteúdo somente leitura recebe fundo tonal. Erros aparecem em aviso textual com role alert; confirmação de ação usa role status.
- **Foco:** contorno de 3px em focus, afastado 3px. O atalho de conteúdo fica visível ao receber foco. Navegação interna transfere foco ao conteúdo ou ao destino de âncora. O diálogo nativo inicia no cancelamento e retorna ao acionador ao fechar.
- **Filtros e navegação:** filtros expõem aria-pressed e fundo selecionado; a navegação indica a página atual com aria-current e sublinhado. Hover mantém reconhecimento de links.
- **Registros e estados:** cada linha expõe resposta, momento, duração ou idade e ação pertinente. Ausência de medição possui mensagem própria. Carregamento, execução pendente, interrupção, expiração e conflito têm mensagens e ações específicas; não converter essas situações em falha HTTP.
- **Sequência de observações:** botões cronológicos mostram códigos reais, estado textual no nome acessível e aria-pressed. A seleção destaca a amostra e sua linha na tabela. A tabela equivalente apresenta momento, resposta, duração e origem da execução, em ordem mais recente primeiro. Quando uma amostra sustenta o incidente, o detalhe permite inspecionar esse vínculo.
- **Livro de evidências:** primeira falha, confirmação e recuperação têm registros próprios; evidência ainda ausente é informada em texto. Reconhecimento humano e recuperação mantêm tratamentos distintos.

A seleção de amostra usa uma confirmação de fundo de 200ms com ease-out. A preferência por movimento reduzido desativa animações e mantém rolagem automática. Marca e ícones são SVG no código; a geometria das amostras é CSS. Não há raster distribuído pela interface. Capturas de revisão são evidência de inspeção, não ativos do produto.

## Do's and Don'ts

### Do:

- **Do** mostrar resultado e momento antes de atribuir saúde ao serviço.
- **Do** manter texto junto a qualquer sinal semântico de cor.
- **Do** preservar rótulos dos registros no celular e acesso inicial à próxima observação.
- **Do** manter a tabela equivalente e o vínculo entre amostras e incidente.

### Don't:

- **Don't** inventar histórico, métricas de disponibilidade ou resultados ilustrativos.
- **Don't** substituir controles nativos por ícones sem nome acessível.
- **Don't** usar sombras em registros planos ou animações de entrada de página.
- **Don't** esconder informações operacionais essenciais em decoração ou cor isolada.
