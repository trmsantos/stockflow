# DESIGN.md — Sistema visual

O agente lê este ficheiro antes de qualquer trabalho de UI. O objetivo é que a aplicação
tenha uma identidade própria e não pareça gerada por IA. Isso consegue-se com decisões
concretas (abaixo), não com adjetivos.

> Preenche a secção "Identidade" para cada projeto. Tudo o resto é regra transversal.

---

## 1. Identidade

**Aprovada a 2026-10-01**: identidade **"Cabine"**, escolhida pelo dono do produto entre duas
propostas construídas e vistas lado a lado. A proposta rejeitada ("Caderno de Caixa", clara, papel
morno e tinta azul) e as duas rotas de comparação foram apagadas no mesmo dia: uma candidata que
perdeu e fica no repositório volta por distração.

| Campo | Valor |
|---|---|
| Nome do produto | StockFlow |
| Público | Donos e encarregados **ao computador no escritório**; cozinha e armazém no telemóvel, só nos fluxos de campo (contar, receber). |
| Tom em três palavras | Direto, denso, sinalizado |
| Referência visual principal | **Bloomberg Terminal** (a densidade e o cromado contado de um painel de operação) e os **ecrãs de cozinha (KDS) do Toast e do Square** (a linha alta, o sinal que se lê de longe) |
| O que este produto NÃO é | Não é lúdico, não é "startup roxa", não é software de contabilidade cinzento, não é uma app de consumo com cartões arredondados |

Esta secção foi reescrita por **duas** razões de uma vez, e é por isso que mudaram ao mesmo tempo a
referência e o público:

1. **A referência estava errada para o produto.** Era o Linear — uma ferramenta de developers, feita
   para teclado. A paleta do §2 e a estrutura dos ecrãs derivam desta secção, e mudar o verde sem
   mudar a referência dava o mesmo produto noutra cor. A referência nova é um painel de operação: a
   pergunta da manhã não é "quanto tenho de tudo", é "o que está mal", e num painel escuro com
   colunas regueadas e algarismos mono uma linha em falta ou fora de prazo **vê-se sem se ler** — e
   vê-se de dois metros, que é a distância a que o dono olha para o monitor com a porta aberta para
   a copa. É também a identidade que aguenta um monitor barato e uma sala com a persiana meia
   fechada, onde um ecrã branco encandeia.
2. **A afirmação de público deixou de ser verdadeira.** A direcção de 2026-10-01 é um ERP
   desktop-primeiro (ADR 0009): menu lateral que cresce, tabelas densas com muitas colunas,
   configuração por empresa, e o telemóvel a servir **só** os fluxos de campo. O "de pé, numa
   cozinha, com pressa" continua verdadeiro para **duas** rotas — Contar e Receber — e é falso para
   as outras.

Princípio de UX: cada ecrã responde a uma pergunta de operação — "o que falta?", "o que expira?",
"quanto deitei fora?". A resposta é uma **tabela densa com a excepção em cima**, e não um número
grande: quem está ao computador quer a lista, e quem está no telemóvel está numa das duas rotas de
campo, que são desenhadas para 360px.

---

## 2. Tokens (fonte da verdade: `src/styles/tokens.css`)

Todos os tokens são variáveis CSS mapeadas para Tailwind v4 via `@theme`. O agente usa
**apenas** classes derivadas destes tokens. Cores hardcoded são proibidas.

### Cor — uma paleta, escura, e porque não há duas

**Uma paleta só, e é escura.** A identidade "Cabine" é um painel de operação; a decisão do dono do
produto é **escuro primário, claro depois**. O modo claro é **dívida nomeada**, aqui e não num
banner: entra quando estiver **completo e medido** — os 18 tokens redefinidos, gamut e contraste
medidos contra a pior superfície dele — e o gate falha se aparecer um bloco `prefers-color-scheme`
com uma paleta parcial. Um modo claro a meio é pior do que não ter modo claro: dá uma app com metade
das cores erradas a quem tem o sistema em claro.

Três papéis por cor de estado, porque um valor só não serve os três. Uma cor de estado usada
como **texto** sobre o fundo precisa de 4.5:1; a mesma cor como **preenchimento** de um banner
precisa de ter texto legível por cima; e a **borda** desse banner precisa de 3:1 para delimitar
um componente. Um token só para os três papéis é como se perde a acessibilidade sem ninguém dar
por isso — uma versão anterior deste ficheiro tinha `warning` a **2.17:1**, abaixo das duas barras
que esta própria secção exige.

```css
@theme static {
  /* Superfícies — três degraus de preto frio. O `surface-2` é o mais claro dos
   * três, logo o pior fundo para texto claro: é contra ele que tudo se mede. */
  --color-background:  oklch(0.145 0.008 240);
  --color-surface:     oklch(0.19 0.009 240);
  --color-surface-2:   oklch(0.245 0.01 240);

  /* Bordas — dois papéis distintos */
  --color-border:        oklch(0.305 0.011 240);  /* separador decorativo; isento dos 3:1 */
  --color-border-strong: oklch(0.55 0.013 240);   /* fronteira de componente (input): 3.3:1 */

  /* Texto */
  --color-foreground:       oklch(0.97 0.003 240);
  --color-muted-foreground: oklch(0.675 0.016 240);

  /* Marca — UMA cor de acento: ciano de lâmpada de painel */
  --color-primary:            oklch(0.76 0.13 225);
  --color-primary-foreground: oklch(0.19 0.02 240);

  /* Estado — texto / preenchimento suave / borda */
  --color-success:         oklch(0.76 0.17 148);
  --color-success-surface: oklch(0.3 0.05 148);
  --color-success-border:  oklch(0.6 0.15 148);

  --color-warning:         oklch(0.82 0.15 85);
  --color-warning-surface: oklch(0.32 0.05 85);
  --color-warning-border:  oklch(0.65 0.13 85);

  --color-danger:          oklch(0.7 0.185 25);
  --color-danger-surface:  oklch(0.3 0.06 25);
  --color-danger-border:   oklch(0.58 0.19 25);
}
```

O acento é ciano e não verde por eliminação, não por gosto: a gama de estado já gasta o verde, o
âmbar e o vermelho, e o §5 proíbe o roxo. Um acento que repita uma cor de estado faz o item activo
do menu parecer um alerta.

**`color-scheme: dark` no `:root`**, e não `light dark`. Sem isso as barras de scroll, o caret, o
autofill e os controlos nativos vêm do modo claro por cima de uma página preta — é o detalhe que
trai uma app escura feita a meio. E como há uma paleta só, o variant `dark:` do Tailwind (que por
default é `prefers-color-scheme`) está **neutralizado** no `tokens.css`: senão o aspecto dos inputs
passava a depender da configuração do sistema de quem olha, com a mesma paleta nos dois casos.

Como se usam os três papéis, e não há um quarto:
- `--color-<estado>` é **cor de texto e de ícone**, sobre qualquer das três superfícies. Serve
  também de preenchimento de botão sólido, com `--color-primary-foreground` por cima — medido a
  **8.863:1** sobre o `primary`, que é o único par em que a frente é escura e o fundo claro.
- `--color-<estado>-surface` é o preenchimento suave de um banner ou badge, e o texto por cima é
  `--color-foreground` — nunca a cor de estado, que sobre a própria tinta não tem contraste.
- `--color-<estado>-border` é a borda desse banner, e só isso.

Regras:
- Uma cor de acento. Gradientes só se a identidade os pedir explicitamente; nunca como default.
- Cinzentos com um ligeiro tom (o `0.003–0.016` de chroma acima, em hue 240), nunca `#888` puro.
- **Contraste mínimo WCAG AA: 4.5:1 texto, 3:1 UI, verificado contra a pior das três superfícies**
  — que é o `surface-2`, não o `background`. **Medido** (`pnpm lint`, não a olho): texto de
  **5.535:1** (`muted-foreground`) a **14.864:1** (`foreground`); fronteiras de componente de
  **3.349:1** (`border-strong`) a **4.960:1** (`warning-border`); `foreground` sobre as três tintas
  de estado de **11.670:1** a **12.814:1**; `primary-foreground` sobre `primary` a **8.863:1**. Os
  três valores mais apertados são os que se quer ver num diff: se um deles descer, desceu por uma
  razão que alguém tem de escrever.
- **Isto é um gate, não uma promessa.** O `frontend/scripts/check-design-tokens.mjs` recalcula o
  gamut e o contraste a cada `pnpm lint`, deriva os papéis do **nome** do token (um
  `--color-info-border` novo entra sozinho na regra dos 3:1) e compara esta secção com o
  `tokens.css` token a token. Até aqui as três afirmações desta secção eram prosa: verdadeiras
  quando escritas, e sem nada que as mantivesse verdadeiras. Foi assim que dois `warning` de uma
  paleta anterior estiveram fora do gamut sem ninguém dar por isso.
- **O gate mudou de alvo a 2026-10-01, e não foi relaxado.** Exigia paridade entre dois modos; com
  um modo só, essa paridade era uma afirmação sobre um conjunto vazio. Passou a exigir: uma paleta
  **completa** (os nove tokens de estrutura e os **três papéis** de cada cor de estado — o que esta
  secção prometia e nada media), todo o token literal legível como `oklch(L C h)`, e **falha se
  aparecer um bloco `prefers-color-scheme` com uma paleta parcial**. Relaxar um gate é afirmar menos
  sobre a mesma coisa; mudar o que ele afirma, porque a coisa mudou, é outra.
- **Todos os valores estão dentro do gamut sRGB**, verificado com tolerância de 1e-6 e não com uma
  margem de arredondamento: numa paleta anterior o `warning` escuro estava a `-0.0011` no canal azul
  e uma tolerância de `0.002` deixava-o passar como se estivesse dentro. Um `oklch()` fora do gamut
  é distorcido pelo browser em silêncio, e o contraste que se mede deixa de ser o contraste que se
  vê. É também por isso que as tintas de estado (`-surface`) têm croma baixa à luminosidade a que
  estão: é um limite do sRGB, não uma escolha estética.
- O `--color-border` a **1.21:1** contra o `surface-2` **não** é uma falha: um separador
  decorativo entre superfícies está fora da regra dos 3:1, que se aplica a fronteiras que
  identificam componentes. Para essas há o `--color-border-strong`. Um `input` delimitado com
  `--color-border` é um bug de acessibilidade. A isenção está no gate pelo nome do token, e é a
  única — qualquer outro token que não seja superfície é medido.

### Tipografia

| Papel | Fonte | Fallback |
|---|---|---|
| UI / corpo | **Archivo**, peso 500 (a família não tem 400) | `system-ui, sans-serif` |
| Títulos | Archivo, peso 600 | idem |
| Cromado (cabeçalho de coluna, microrótulo) | Archivo, peso 700, caixa alta, tracking `0.08em` | idem |
| Mono / dados (quantidades, preços, códigos) | **IBM Plex Mono** | `ui-monospace, monospace` |

**Proibido como default:** Inter, Roboto, Open Sans, Poppins. São o marcador mais óbvio de UI gerada.

Porque duas famílias e não uma: o algarismo mono é mais largo e mais escuro que a palavra ao lado, e
numa coluna de quantidades o que se compara são os números. Todo o dado numérico é mono; nada de
prosa é.

Escala (rem): `0.8125 · 0.9375 · 1 · 1.125 · 1.25 · 1.5 · 2 · 2.5 · 3.25` — um degrau acima da
escala anterior, porque o ecrã também é lido de dois metros: a célula da tabela (`text-sm`) é 15px e
o rótulo de coluna (`text-xs`) é 13px.
Line-height: 1.45–1.5 corpo, 1.05–1.2 títulos. Tracking negativo em títulos (`-0.01em` a `-0.02em`).
Números tabulares em tabelas e métricas (`font-variant-numeric: tabular-nums`).

### Espaçamento e forma

- Grelha de 4px. Escala: `1 2 3 4 6 8 12 16 24 32` (×4px).
- Radius: **base 8px** (`rounded-lg`), derivados `sm = 4px`, `md = 6px`, `xl = 12px`. Painéis com
  canto, como os cartões de um KDS. Não misturar `rounded-full` em botões com `rounded-md` em
  inputs.
- **Densidade, em tokens e não em números soltos** (`--spacing-*`, logo `h-linha`, `px-celula-x`,
  `gap-ritmo`): linha de tabela **44px**, célula `12px/16px`, ritmo entre painéis **24px**, controlo
  (input, botão) **40px**, chip **28px** mínimo, barra de topo **56px**, trilho de acento **4px**,
  sidebar **16rem**. A linha é alta de propósito: 44px é ao mesmo tempo o alvo de toque mínimo do §4
  e a altura que deixa a mesma tabela servir num tablet na copa sem um segundo desenho.
- Sombras: máximo dois níveis (`shadow-sm` para painéis, `shadow-lg` para popovers). Sem sombras
  coloridas. Num fundo preto a sombra não separa — o que separa é o fio de luz de 1px na aresta de
  cima, que é a primeira camada do `shadow-sm`.
- Bordas de 1px com `--color-border` são preferíveis a sombras para separar superfícies. O cromado
  desta identidade é **visível e contado**: cromado (sidebar e cabeçalho) no `surface` e a tela de
  conteúdo no `background` — **ao contrário do que esta linha dizia**, e a razão é medida: os quatro
  ecrãs desenham os seus painéis em `bg-surface`, logo com a sidebar em `background` e a tela em
  `surface` os painéis **desapareciam na própria tela**. Honrar a ordem original exige subir todos os
  ecrãs um degrau de superfície, que é obra própria e fica nomeada; até lá o documento descreve o que
  existe: cabeçalho de tabela no `surface-2`, réguas verticais de 1px entre colunas, e um trilho de
  4px em `--color-primary` na linha e no item de menu activos.

### Movimento

- Duração: 120ms (micro), 200ms (transições), 320ms (entrada de painéis).
- Easing: `cubic-bezier(0.2, 0, 0, 1)` para entradas; `ease-out` para saídas.
- Só anima `transform` e `opacity`. Nunca `width`, `height`, `top`.
- Respeitar `prefers-reduced-motion: reduce` — desligar tudo exceto opacidade.
- Sem animações decorativas em loop. Sem confetti. Sem "hover: scale(1.05)" em cards.

---

## 3. Componentes

Base: **shadcn/ui** em `src/components/ui/`. Instalados via CLI, nunca copiados à mão:

```
pnpm dlx shadcn@latest add <componente>
```

**`pnpm dlx` e não uma devDependency**, desde 2026-10-06. O `shadcn` é um CLI que
se corre de vez em quando, nada o importa e nenhum script o chamava — e enquanto
era dependência arrastava uma árvore transitiva (`ts-morph`, `fast-glob`,
`micromatch`, `braces`) que a auditoria do CI lia a cada corrida. O `braces` tem
um aviso `high` **sem versão corrigida a montante**, logo a única saída honesta era
não ter o caminho: suprimir um aviso que não se pode corrigir ensina a ignorar a
auditoria, e uma auditoria que se ignora não é um gate.
Personalizados uma vez através dos tokens acima — não por componente.

Regras de composição:
- Componentes de feature (`src/features/*/components`) compõem primitivos; não redefinem estilos.
- Um `<Button>` tem no máximo estas variantes: `default | secondary | outline | ghost | destructive`.
  Se precisas de uma sexta, provavelmente precisas de outro componente.
- Estados obrigatórios em tudo o que é interativo: hover, focus-visible, active, disabled, loading.
- Estados obrigatórios em tudo o que carrega dados: loading (skeleton, não spinner), empty, error.
- Tabelas: densas, alinhamento numérico à direita, sem zebra stripes por default. A moldura, as
  classes de célula e de linha, o cabeçalho e o esqueleto vivem **num** módulo
  (`src/components/tabela.tsx`), usado pelas duas features que têm tabelas: duas tabelas com a mesma
  intenção em dois ficheiros divergem na primeira correção feita só numa delas.
- **Larguras de coluna explícitas nas colunas de largura previsível** (quantidades, estado). O
  layout automático dá espaço a quem tem o conteúdo mais largo, e numa coluna numérica o conteúdo
  mais largo é o **cabeçalho**: "QUANTIDADE" em caixa alta com tracking de 0.08em é mais largo do que
  "24,400 kg". Medido: 246px para a quantidade e 140px para "Onde", que truncava nomes reais com
  espaço de sobra ao lado.
- **O trilho de sinal de 4px na aresta esquerda da linha, e uma linha saudável não o tem.** É onde a
  ousadia desta identidade está gasta, e é o que faz a leitura de dois metros do §1 funcionar: todos
  os trilhos estão na mesma vertical, logo o olho corre uma coluna de 4px em vez de quinze linhas. Um
  trilho em todas as linhas é uma coluna pintada que não distingue nada.
- **O estado é a palavra, não um chip.** Um badge de 28px com tinta e borda próprias dentro de uma
  célula de 44px é um cartão pequeno a competir com a régua de 1px que já delimita a célula. A cor
  vem do primeiro papel do §2 (cor de texto) e a palavra é quem cumpre a regra de não comunicar só
  por cor — nunca foi o ícone. Um estado saudável devolve a palavra **só para áudio**: silêncio
  visual, não silêncio total.
- **Números no topo: uma régua de campos, não uma grelha de cartões.** Sem radius, sem borda
  individual, sem sombra, sem `gap` — o que separa é a régua vertical de 1px, e o microrótulo do
  campo usa o mesmo tratamento do `<th>` da tabela que vem abaixo. É essa rima que faz o topo e a
  tabela lerem-se como um instrumento só. Os campos empacotam à esquerda e **não esticam**: três
  células a dividir 1024px dariam 340px cada para um número de dois dígitos.
- **O "cabeçalho sticky" saiu desta linha, e a razão é de CSS e não de preguiça.** Uma tabela de ERP
  a 360px desliza na horizontal (`overflow-x-auto`, que o §4 aceita e manda declarar), e esse
  invólucro torna-se o *scrollport* do `position: sticky`. Como ele não rola na **vertical**, um
  `thead` sticky ficaria colado ao topo de um contentor que nunca se move: a classe existiria e o
  efeito não. O que acompanha de facto o scroll é a **barra do ecrã** (`sticky top-cabecalho`), e é
  isso que está construído. Um cabeçalho de tabela a sério exige dar altura própria à região da
  tabela com scroll vertical interno — decisão de produto, não de estilo, e fica por decidir.
- Formulários: label acima do campo, erro abaixo em `--color-danger`, nunca só a cor a comunicar erro.

---

## 4. Layout

Desktop-primeiro, com o telemóvel a servir **só** os fluxos de campo (ADR 0009). Isto é o oposto do
que esta secção dizia até 2026-10-01, e a razão está no §1: o público mudou, não a moda.

- **Larguras de referência: desenho a 1440px, obrigatória a 1280px** (o portátil real). **360px
  continua a ser referência das rotas de campo** — Contar e Receber — e não de todas.
- Nenhuma rota é bloqueada em mobile: um deep link tem de funcionar. Mas só as de campo são
  desenhadas para 360; as outras a 360 têm scroll horizontal na tabela, e isso é **declarado** e não
  um defeito.
- Largura máxima: `72rem` para **formulários e leitura**, `42rem` para texto corrido. **Tabelas usam
  a largura toda da área de conteúdo** — um cap de 72rem numa tabela de ERP é espaço desperdiçado à
  direita.
- **Todos os ecrãs de lista cumprem a linha acima desde 2026-10-06** — Stock, Alertas, o
  desperdício, Receber, a receção e o histórico de movimentos de um artigo —, **e Contar e o Fecho de
  contagem nunca a vão cumprir, porque não são listas.** Este documento
  carregava a dívida por escrito — os quatro ecrãs com um cap de `42rem`, 672px numa área de 1024 —
  e a ordem de a pagar **depois** da sessão 0 (ADR 0009), porque refazer antes das respostas era
  refazer duas vezes.
  A ordem inverteu-se por decisão do dono do produto, e a razão não estava prevista: aquele desenho
  **lê-se como UI gerada por IA**, e um ecrã que o dono não quer mostrar não serve de instrumento
  para a sessão 0 que depende dele. A dívida estava a bloquear o que a havia de resolver. O que a
  sessão 0 ainda decide são as **colunas** (unidades, mínimo por artigo ou por artigo-e-loja), e
  trocar uma coluna numa tabela que existe é uma linha num array — logo o argumento de "duas vezes"
  caiu com a forma, não com as respostas.
  **Alargar o cap sem passar as linhas a tabela densa continua a ser pior do que não alargar.** A
  conversão foi por ecrã e cada um pagou a sua.
- **As larguras de coluna medem-se, não se somam.** A oito colunas numa área de 1024px todas as
  larguras ficam no mínimo, e três coisas que só aparecem a medir decidiram o desenho final:
  1. **uma coluna de largura fixa não é de largura fixa.** A sub-linha "durabilidade mínima" (19
     caracteres) forçava o `min-content` da coluna da validade a 152px apesar de ela declarar `w-32`
     (128), e os 24px a mais saíam da coluna flexível ao lado. O remédio foi encurtar a palavra — e
     encurtá-la melhorou o vocabulário, porque o inventário já dizia "melhor antes de" para o mesmo
     conceito;
  2. **o cabeçalho é, muitas vezes, o conteúdo mais largo de uma coluna numérica.** "QUANTIDADE" em
     caixa alta com tracking de 0.08em é mais largo do que "24,400 kg";
  3. **uma sub-linha de 13px numa célula de 44px cresce a linha.** "aviso a 3 dias" na coluna do lote
     punha metade das linhas dos Alertas a 62px numa tabela de 44, e o ritmo da tabela desfazia-se.
  O tecto honesto a 1280px é oito colunas de dados; a nona não cabe. A **1440px**, que é a largura de
  desenho deste documento, nenhuma das tabelas trunca. Um nome de artigo a cortar aos 1280 é aceite e
  tem o texto completo no `title` e no ecrã de detalhe a que o nome liga — um nome truncado lê-se
  mesmo assim, ao contrário da razão de um alerta ou de uma validade.
- **Contar e o Fecho de contagem continuam formulários, mas já não são estreitos.** O dono do
  produto apanhou o Contar a parecer de outro produto ao lado dos outros — continuava com o cap de
  `42rem` e o cromado antigo — e tinha razão. O que mudou foi a largura e o cromado; as linhas
  continuam a ser um formulário. A razão para o ter deixado de fora tinha um **pressuposto
  escondido**: assumiu-se que uma tabela obriga a uma largura mínima grande e que isso partia os
  360px. Com poucas colunas não obriga — o que de facto não cabe a 360px é a informação toda.
  A forma é por isso uma **grelha responsiva com um só `<input>` no DOM**: cinco colunas em desktop,
  com cabeçalho, e duas linhas empilhadas a 360, com os mesmos elementos. O `md:contents` promove os
  filhos da segunda linha a células em desktop, que é o que evita dois layouts — e dois layouts
  seriam dois campos, dois focos e dois `onBlur`. O cabeçalho usa a **mesma** constante de grelha da
  linha: medido, o rótulo "Artigo" e a célula dele ficam os dois em `x=272, w=384`.
  As duas continuam a não ser listas: são **formulários**. Uma linha de contagem é um campo numérico com salto de foco (`enterKeyHint="next"`)
  para o teclado ficar aberto do princípio ao fim da zona, e o `<label>` está ao lado do campo —
  contra o default do §3 — porque nove rótulos empilhados sobre nove campos são dezoito linhas. O
  fecho são três totais, uma justificação e um botão. As duas são rotas de campo, contam-se de pé no
  armazém com uma mão, e o §4 dá a 360px a prioridade do desenho ali: uma tabela de `<input>`s a
  360px desliza na horizontal e põe fora do ecrã o campo que se está a escrever.
  O que elas **partilham** com os outros ecrãs é a régua de contadores — a última grelha de três
  mosaicos do repositório era a dos totais do fecho, e passou a régua a 2026-10-06. A linguagem é a
  mesma; a forma do conteúdo é que é outra, por razões de uso e não de moda.
- Densidade: **compacta** em desktop; em mobile mantém-se compacta e os alvos de toque são ≥ 44px
  (a regra está no `base.css` por `pointer: coarse`, não por breakpoint — um tablet com rato mantém a
  densidade).
- Navegação: **sidebar persistente e colapsável** em desktop, e **a mesma** sidebar como drawer a
  partir do header em mobile. **Não há tab bar** e não há uma terceira superfície de navegação. O
  menu é uma projecção por tenant sobre as rotas que existem, com um nível de agrupamento (ADR
  0009); esconder é apresentação, não autorização.
- O **seletor de tenant** vive no pé da sidebar (é do shell); o **seletor de loja** fica na barra do
  ecrã (é do ecrã). Parecem a mesma coisa e não são.

---

## 5. Anti-padrões (o "look de IA") — proibidos

- Hero com gradiente roxo/azul e texto centrado com emoji.
- Cards com ícone colorido em círculo + título + duas linhas, repetidos em grelha de 3.
- Glassmorphism, blur em fundos, "glow" atrás de botões.
- Três colunas de "features" com ícones da Lucide todos da mesma cor.
- Frases como "Powered by AI", "Seamlessly", "Unlock", "Elevate" na UI.
- Sombras enormes e coloridas; bordas de 2px; `rounded-2xl` em tudo.
- Ilustrações genéricas de pessoas abstratas.
- Emojis como ícones.

Se o agente se apanhar a produzir qualquer um destes, apaga e recomeça a partir da secção 1.

---

## 6. Checklist antes de dar UI por terminada

- [ ] Só usei tokens (nenhum `#hex`, nenhum `bg-[...]`).
- [ ] Fontes são as do projeto (Archivo / IBM Plex Mono), não Inter/Roboto.
- [ ] Todos os estados (loading/empty/error/disabled/focus) existem.
- [ ] Navegação por teclado funciona; foco é visível.
- [ ] `pnpm lint` passou — é ele que mede o contraste AA contra o `surface-2` (a pior superfície),
      o gamut sRGB a 1e-6 e a paridade desta secção com o `tokens.css`. Não se presume nenhum dos três.
      Para os números token a token: `node scripts/check-design-tokens.mjs --detalhe`.
- [ ] Se acrescentei uma cor de estado, tem os **três** papéis (`-surface` e `-border` incluídos) e
      está escrita no §2 — o gate falha nos dois sentidos, e agora **mede** os três papéis.
- [ ] **Não comecei um segundo modo de cor.** Há uma paleta só, escura; o modo claro é dívida
      nomeada no §2 e entra completo e medido ou não entra. Um `prefers-color-scheme` com paleta
      parcial falha o `pnpm lint`.
- [ ] Nenhum `dark:` em código nosso: com uma paleta só, o variant não seleciona nada (está
      neutralizado no `tokens.css`) e o gate recusa-o fora dos ficheiros gerados.
- [ ] Nenhum `input` ou controlo delimitado com `--color-border` em vez de `--color-border-strong`.
- [ ] Densidade pelos tokens (`h-linha`, `px-celula-x`, `gap-ritmo`), não por números no JSX.
- [ ] Funciona a **1280px**; e a **360px** se for uma rota de campo (Contar, Receber). Fora dessas,
      scroll horizontal na tabela a 360 é aceite e declarado (§4).
- [ ] `prefers-reduced-motion` respeitado.
- [ ] Nenhum item da secção 5 presente.
- [ ] Skill `web-design-guidelines` corrida sobre os ficheiros alterados (se instalada).
