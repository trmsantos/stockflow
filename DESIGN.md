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

### Cor — três paletas, cada uma completa e cada uma medida

**Três paletas: `escuro` (o default, e a identidade aprovada), `claro` e `meio_termo`; e a selecção é
o atributo `data-tema` no `<html>`, nunca `prefers-color-scheme` (ADR 0015).** A preferência é **da
pessoa** e vive no servidor (ADR 0016), não na configuração do sistema de quem olha; e uma media query
tem dois estados para três paletas. Por isso `prefers-color-scheme` deixou de selecionar o que quer que
seja e passa a ser proibido em `src/**` inteiro.

**E a paleta é aplicada antes da primeira pintura, não quando a sessão chega.** A preferência está no
servidor e o servidor só responde depois do primeiro pixel, pelo que o cliente guarda uma **cópia do
nome da paleta** e é ela que o módulo de entrada lê, antes de montar o React (`src/lib/tema.ts`). Sem
isso, quem prefere o claro via um relâmpago escuro em cada arranque — o mesmo defeito, na mesma
superfície, que o `color-scheme` desta secção existe para evitar. Numa máquina nova o primeiro arranque
pinta o default e troca quando a sessão chega: é um relâmpago **por máquina** e não um por arranque.
Medido no browser com a sessão bloqueada, que é o único estado em que só a cópia decide.

**As três existem desde 2026-10-07 e estão escritas abaixo**, com os 18 tokens de cor **mais os dois
de sombra** cada uma — uma paleta não é só `--color-*`. Nenhuma entrou a 17 de 18: o gate falha se
entrar. O que cada uma é, e a **pior superfície** de cada uma, que o gate *calcula* (a de menor
contraste contra o `foreground` dessa paleta) e imprime a cada corrida em vez de a nomear em código:

| Paleta | O que é | Pior superfície | Pior texto | Pior fronteira |
|---|---|---|---|---|
| `escuro` | A identidade "Cabine" aprovada: três degraus de preto frio, cromado contado, sinal que se lê de dois metros. É o default e vive na `:root` sem atributo. | `surface-2` (o **mais claro** dos três pretos) | 5.535:1 | 3.349:1 |
| `claro` | A mesma cabine com as luzes acesas: cinzento **frio** no mesmo hue 240, a tela em cima e o cromado a descer. Não é papel morno — o morno era a identidade rejeitada a 2026-10-01. | `surface-2` (o **mais escuro** dos três cinzentos) | 4.774:1 | 3.331:1 |
| `meio_termo` | Grafite com texto claro: a direcção do escuro com as superfícies, o separador e as tintas **+0.105 em L** e o texto a descer de 0.97 para 0.94, para matar a halation do texto claro sobre quase-preto num monitor barato. | `surface-2` | 5.082:1 | 3.298:1 |

Nos três casos a pior superfície dá o `surface-2`, e **pela mesma razão estrutural e não por
coincidência**: é o degrau mais afastado da tela em qualquer das três. No escuro por ser o mais claro,
no claro por ser o mais escuro — que é exactamente porque o gate a calcula. Nomeá-la numa paleta clara
seria medir contra o melhor fundo e chamar-lhe o pior.

**O meio termo é um terceiro conjunto de superfícies, não um `opacity` por cima do escuro**: um factor
multiplicativo não redefine token nenhum, e um token que caia a 4.4:1 não aparece em medição alguma
porque não existe como valor. E não é um claro esbatido — isso seria uma paleta clara com menos
contraste, pior do que o claro precisamente naquilo para que o claro serve.

Os **acentos e as cores de estado redefinem-se em cada paleta**, e isso não é uma proibição de
partilhar um valor: é o que a medição obriga. O mesmo `oklch` que dá 5.5:1 sobre quase-preto dá muito
menos sobre papel, logo um valor copiado falha na paleta onde não passa — e um que passe fica. No
`meio_termo` o acento e dois dos três sinais são **o mesmo valor** do escuro, sem uma linha de
diferença, porque medidos passam. O que mudou lá mudou por medição, e a contabilidade está no
`tokens.css`: quatro tokens do escuro **falham** sobre o grafite (`muted-foreground` 3.854:1,
`border-strong` 2.332:1, `danger` 3.888:1, `danger-border` 2.395:1), dois passam por uma margem que
esta casa recusa e sobem com ela (`success-border` a 0.048 da barra, `warning-border`), e só o
`foreground` desce por decisão e não por medição — é metade do remédio para a halation.

Três papéis por cor de estado, porque um valor só não serve os três. Uma cor de estado usada
como **texto** sobre o fundo precisa de 4.5:1; a mesma cor como **preenchimento** de um banner
precisa de ter texto legível por cima; e a **borda** desse banner precisa de 3:1 para delimitar
um componente. Um token só para os três papéis é como se perde a acessibilidade sem ninguém dar
por isso — uma versão anterior deste ficheiro tinha `warning` a **2.17:1**, abaixo das duas barras
que esta própria secção exige.

```css
/* `escuro` — o default e a identidade aprovada. Vive na `:root` sem atributo. */
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

  /* Sombras — parte da paleta. Num fundo preto a sombra não separa; o que
   * separa é o fio de luz de 1px na aresta de cima, a primeira camada do `sm`. */
  --shadow-sm: inset 0 1px 0 0 oklch(1 0 0 / 0.05), 0 10px 28px -16px oklch(0 0 0 / 0.75);
  --shadow-lg: 0 16px 40px -12px oklch(0 0 0 / 0.8);
}
```

```css
/* `claro` — a mesma cabine com as luzes acesas. Cinzento frio, hue 240, tela em
 * cima: o `surface-2` é a mais escura das três e a pior superfície. */
:root[data-tema="claro"] {
  color-scheme: light;

  --color-background:  oklch(0.985 0.004 240);
  --color-surface:     oklch(0.952 0.006 240);
  --color-surface-2:   oklch(0.92 0.008 240);

  --color-border:        oklch(0.855 0.01 240);   /* separador decorativo; isento dos 3:1 */
  --color-border-strong: oklch(0.58 0.014 240);   /* fronteira de componente: 3.375:1 */

  --color-foreground:       oklch(0.235 0.014 240);
  --color-muted-foreground: oklch(0.485 0.016 240);

  /* O mesmo matiz 225 do acento aprovado, à luminosidade e croma que o papel
   * deixa — ciano de painel profundo em vez de ciano de lâmpada. */
  --color-primary:            oklch(0.49 0.082 225);
  --color-primary-foreground: oklch(0.99 0.004 240);

  --color-success:         oklch(0.485 0.125 148);
  --color-success-surface: oklch(0.9 0.085 148);
  --color-success-border:  oklch(0.565 0.145 148);

  --color-warning:         oklch(0.5 0.09 85);
  --color-warning-surface: oklch(0.9 0.08 85);
  --color-warning-border:  oklch(0.585 0.105 85);

  --color-danger:          oklch(0.52 0.19 25);
  --color-danger-surface:  oklch(0.9 0.045 25);
  --color-danger-border:   oklch(0.61 0.215 25);

  /* Sem fio de luz: sobre papel um fio branco não existe, e a sombra volta a
   * ser o que separa. Continuam dois níveis e nenhuma é colorida. */
  --shadow-sm: 0 1px 2px 0 oklch(0 0 0 / 0.07), 0 8px 20px -14px oklch(0 0 0 / 0.22);
  --shadow-lg: 0 14px 36px -10px oklch(0 0 0 / 0.28);
}
```

```css
/* `meio_termo` — grafite com texto claro: o escuro com as superfícies, o
 * separador e as tintas +0.105 em L, e cinco tokens re-derivados porque a
 * medição recusou os do escuro (os valores recusados estão no `tokens.css`). */
:root[data-tema="meio_termo"] {
  color-scheme: dark;

  --color-background:  oklch(0.25 0.008 240);
  --color-surface:     oklch(0.295 0.009 240);
  --color-surface-2:   oklch(0.35 0.01 240);

  --color-border:        oklch(0.41 0.011 240);   /* separador decorativo; isento dos 3:1 */
  --color-border-strong: oklch(0.635 0.014 240);  /* fronteira de componente: 3.298:1 */

  --color-foreground:       oklch(0.94 0.005 240);
  --color-muted-foreground: oklch(0.755 0.016 240);

  /* O acento aprovado, sem uma alteração */
  --color-primary:            oklch(0.76 0.13 225);
  --color-primary-foreground: oklch(0.19 0.02 240);

  --color-success:         oklch(0.76 0.17 148);
  --color-success-surface: oklch(0.405 0.05 148);
  --color-success-border:  oklch(0.66 0.15 148);

  --color-warning:         oklch(0.82 0.15 85);
  --color-warning-surface: oklch(0.425 0.05 85);
  --color-warning-border:  oklch(0.7 0.125 85);

  /* Clareia para salmão por aritmética: o vermelho saturado do sRGB tem
   * luminância máxima de 0.213 e aqui são precisos 0.358 para 4.5:1. */
  --color-danger:          oklch(0.765 0.125 25);
  --color-danger-surface:  oklch(0.405 0.06 25);
  --color-danger-border:   oklch(0.67 0.18 25);

  /* O fio de luz fica, mais fraco: sobre grafite a sombra já funciona outra vez
   * e ganha o peso que o fio perde. */
  --shadow-sm: inset 0 1px 0 0 oklch(1 0 0 / 0.04), 0 10px 26px -16px oklch(0 0 0 / 0.6);
  --shadow-lg: 0 16px 40px -12px oklch(0 0 0 / 0.7);
}
```

O acento é ciano e não verde por eliminação, não por gosto: a gama de estado já gasta o verde, o
âmbar e o vermelho, e o §5 proíbe o roxo. Um acento que repita uma cor de estado faz o item activo
do menu parecer um alerta.

**E esse argumento é o que fixa o acento claro.** O ciano do escuro (L 0.76) mede **1.644:1** sobre o
`surface-2` da paleta clara — como texto não existe —, logo tinha de ser re-derivado; mas o que se
re-derivou foi a **luminosidade e a croma**, não o matiz: 225 nas três paletas. Mudar o matiz era
resolver um problema de contraste criando o problema que a frase acima descreve. O valor claro não é
uma preferência: a 4.5:1 sobre o `surface-2` o tecto é L 0.50, e a croma que o sRGB tem neste matiz é
0.095 a esse L — o acento é o que cabe nessas duas paredes, e dá **4.830:1** como texto. O custo, dito
por inteiro: sobre papel o acento é um ciano de painel **profundo**, não a lâmpada de painel do escuro.
Reconhece-se como a mesma cor; não tem o mesmo brilho, e não há como ter: o brilho vinha do fundo
preto.

**`color-scheme` é por paleta, e nunca `light dark`**: `dark` no escuro e no meio termo, `light` no
claro. Sem isso as barras de scroll, o caret, o autofill e os controlos nativos vêm do modo errado por
cima da página — é o detalhe que trai uma app feita a meio, e é a razão pela qual esta linha existe. O
variant `dark:` do Tailwind continua **neutralizado** no `tokens.css`, agora com duas razões: ele
selecciona dois estados e há três, e a paleta vive nos tokens, pelo que nenhum componente precisa de
saber qual está activa — um `dark:` escrito por nós é uma regra que não corre.

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
- **Contraste mínimo WCAG AA: 4.5:1 texto, 3:1 UI, verificado contra a pior das três superfícies de
  cada paleta** — que o gate calcula (a de menor contraste contra o `foreground` dessa paleta) em vez
  de a nomear; nas três dá o `surface-2`, e não o `background`. **Medido** (`pnpm lint`, não a olho),
  por paleta, contra o `surface-2` de cada uma:

  | | texto | fronteira de componente | `foreground` sobre as tintas | `primary-fg` sobre `primary` |
  |---|---|---|---|---|
  | `escuro` | 5.535 (`muted-foreground`) – 14.864 (`foreground`) | 3.349 (`border-strong`) – 4.960 (`warning-border`) | 11.670 – 12.814 | 8.863 |
  | `claro` | 4.774 (`warning`) – 13.152 (`foreground`) | 3.331 (`danger-border`) – 3.375 (`border-strong`) | 12.156 – 12.716 | 5.942 |
  | `meio_termo` | 5.082 (`danger`) – 9.470 (`foreground`) | 3.298 (`border-strong`) – 4.188 (`warning-border`) | 6.969 – 7.792 | 8.863 |

  Os valores mais apertados de cada linha são os que se quer ver num diff: se um deles descer, desceu
  por uma razão que alguém tem de escrever. **A paleta clara é a mais apertada das três no texto**, e é
  uma propriedade do papel e não um descuido: uma cor que seja ao mesmo tempo legível como texto e
  reconhecível como sinal tem menos espaço acima de uma tela clara do que acima de uma preta. Todas as
  cores de estado e o acento do `claro` ficam entre 4.77 e 4.83 — 0.3 acima da barra, que é margem para
  um arredondamento e não para uma mudança de valor à mão.
- **Isto é um gate, não uma promessa.** O `frontend/scripts/check-design-tokens.mjs` recalcula o
  gamut e o contraste a cada `pnpm lint`, deriva os papéis do **nome** do token (um
  `--color-info-border` novo entra sozinho na regra dos 3:1) e compara esta secção com o
  `tokens.css` token a token. Até aqui as três afirmações desta secção eram prosa: verdadeiras
  quando escritas, e sem nada que as mantivesse verdadeiras. Foi assim que dois `warning` de uma
  paleta anterior estiveram fora do gamut sem ninguém dar por isso.
- **O gate mudou de alvo duas vezes, e nunca foi relaxado.** A 2026-10-01 exigia paridade entre dois
  modos; com um modo só, essa paridade era uma afirmação sobre um conjunto vazio, e passou a exigir uma
  paleta **completa** (os nove tokens de estrutura e os **três papéis** de cada cor de estado — o que
  esta secção prometia e nada media) e todo o token literal legível como `oklch(L C h)`. A 2026-10-06,
  com o pedido das três paletas (ADR 0015), o alvo passa de "uma paleta completa e nenhuma
  alternativa" para **"N paletas, cada uma completa e cada uma medida"**: a completude passa a incluir
  os dois tokens de sombra, a pior superfície passa a ser calculada por paleta, e um bloco de paleta
  que não redefina o conjunto inteiro falha — como já falhava um `prefers-color-scheme` parcial.
  Relaxar um gate é afirmar menos sobre a mesma coisa; mudar o que ele afirma, porque a coisa mudou, é
  outra.
- **Todos os valores estão dentro do gamut sRGB**, verificado com tolerância de 1e-6 e não com uma
  margem de arredondamento: numa paleta anterior o `warning` escuro estava a `-0.0011` no canal azul
  e uma tolerância de `0.002` deixava-o passar como se estivesse dentro. Um `oklch()` fora do gamut
  é distorcido pelo browser em silêncio, e o contraste que se mede deixa de ser o contraste que se
  vê. É também por isso que as tintas de estado (`-surface`) têm croma baixa à luminosidade a que
  estão: é um limite do sRGB, não uma escolha estética. Os dois casos onde esse limite **decide** o
  valor estão nomeados: o acento do `claro` (a croma disponível a L 0.49 no matiz 225 é 0.093) e o
  `danger` do `meio_termo` (o vermelho saturado do sRGB tem luminância máxima de 0.213 e sobre o
  grafite são precisos 0.358, logo o alarme clareia para salmão por aritmética). Cada token dos três
  blocos tem **pelo menos 10% de folga** até à parede do gamut no seu matiz e luminosidade.
- O `--color-border` a **1.21:1** (escuro), **1.23:1** (claro) e **1.28:1** (meio termo) contra o
  `surface-2` **não** é uma falha: um separador
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
  cima, que é a primeira camada do `shadow-sm`. **Os dois tokens de sombra são parte da paleta e
  redefinem-se com ela** (ADR 0015): num fundo claro um fio de luz branco não existe e é a sombra que
  volta a separar. **E as duas utilities têm de ser apontadas ao token à mão**, em quatro linhas do
  `base.css`: medido no CSS compilado, o Tailwind v4 **interpreta** o valor do token em tempo de
  compilação e inlina-o (para suportar `shadow-<cor>`), logo redefinir `--shadow-sm` num bloco de tema
  não mudava nada e o fio de luz da paleta escura aparecia nas três. Perde-se a composição com
  `ring-*` — auditada, não está em uso nestas duas classes — e com `shadow-<cor>`, que esta secção
  proíbe.
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
se corre de vez em quando, nada o importa em TypeScript e nenhum script o chamava
— entrava por um `@import` de CSS, que é como ele me escapou à primeira
verificação. Enquanto era dependência arrastava uma árvore transitiva
(`ts-morph`, `fast-glob`, `micromatch`, `braces`) que a auditoria do CI lia a cada
corrida, e o `braces` tem um aviso `high` **sem versão corrigida a montante**: a
única saída honesta era não ter o caminho, porque suprimir um aviso que não se pode
corrigir ensina a ignorar a auditoria, e uma auditoria que se ignora não é um gate.

As três variantes `data-*` que vinham do CSS dele são nossas desde então
(`src/styles/variantes.css`), com o `scripts/check-variantes.mjs` a impedir a
cópia de divergir — e a lista fechada dele cobre o caso em que a variante nativa
do Tailwind não basta, que é quando o Radix escreve `data-state="open"` e o nativo
`[data-open]` nunca casa: a classe existe e o estilo não aparece.

Personalizados uma vez através dos tokens acima — não por componente.

Regras de composição:
- Componentes de feature (`src/features/*/components`) compõem primitivos; não redefinem estilos.
- Um `<Button>` tem no máximo estas variantes: `default | secondary | outline | ghost | destructive`.
  Se precisas de uma sexta, provavelmente precisas de outro componente.
- Estados obrigatórios em tudo o que é interativo: hover, focus-visible, active, disabled, loading.
- Estados obrigatórios em tudo o que carrega dados: loading, empty, error.
- **Esqueleto e indicador são dois trabalhos, não duas opções.** Esta linha dizia
  "skeleton, **não** spinner" e a razão continua verdadeira — um esqueleto com a
  forma do conteúdo impede o layout de saltar quando os dados chegam, e um
  indicador não reserva espaço nenhum. O que mudou a 2026-10-06, a pedido do dono
  do produto, é que a regra era exclusiva e passou a ser uma divisão:
  - o **esqueleto** diz *que forma vem* (tabela de sete colunas, régua de três
    campos) e vive onde o conteúdo vai aparecer;
  - o **indicador** (`components/indicador-de-carga.tsx`) diz *que alguma coisa
    está a acontecer* e vive onde não há forma a reservar: a barra de topo, um
    botão à espera da resposta, o ecrã de arranque do `index.html`. Era a parte
    que faltava — uma revalidação em segundo plano não tem esqueleto nenhum e,
    até aqui, não tinha sinal nenhum.
- **O indicador são três traços que acendem em sequência, e não um anel a rodar.**
  Um anel é o elemento mais genérico de qualquer interface; três traços são o
  trilho de sinal das tabelas a dizer que o produto está a trabalhar. O ecrã de
  arranque desenha **os mesmos** em CSS puro, antes de o React existir: um produto
  com dois indicadores de carga diferentes tem dois produtos lá dentro.
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
- **"A tabela desliza a 360px" é sobre a tabela, nunca sobre o ecrã — e até 2026-10-07 era o ecrã
  que deslizava.** A moldura tem `overflow-x-auto` desde que nasceu e não continha nada: um item de
  flex tem `min-width: auto`, logo crescia para caber as colunas, e o bloco da `<table>` contribuía
  para a área de scroll da **raiz** mesmo clipado. Medido a 360px com o `scripts/ver-ecra.py`, e foi
  a fotografia que o mostrou: 360px de aplicação e 587px de preto deslizável, num telemóvel, em
  quatro ecrãs. São duas classes na moldura (`min-w-0` para conter, `relative` para a sobreposição
  ficar local) e a razão está escrita no `components/tabela.tsx`, com os cinco candidatos medidos.
  O que se declara aqui é a **tabela** a deslizar por dentro da sua moldura; um ecrã que desliza para
  o lado leva a sidebar e a barra de topo com ele, e isso nunca foi aceite.
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
- **Eram dois sinais de "dados a fingir", e não se juntavam num badge só. Ficou um.** "O servidor de
  fixtures respondeu" era sobre o ambiente de desenvolvimento e não existia no bundle de produção;
  "estás no estabelecimento de demonstração" é sobre o **tenant** e tem de funcionar em produção,
  que é onde importa. Colapsá-los dava um sinal de produção testável só onde está sempre ligado — e
  o modo de falha é nunca aparecer onde interessa; por isso a regra de os não juntar continua
  escrita. **O primeiro saiu a 2026-10-27 com a pasta `fixtures/`** (ADR 0034, decisão 7): o Django
  serve os últimos sete recursos, e um badge a dizer que os dados são a fingir passou a ser a única
  coisa a mentir sobre a origem deles. O segundo fica.
  A faixa do tenant vive na barra de topo porque ela é `sticky`: é o que limita alguém a registar no
  demo uma quebra que era a sério (ADR 0018, decisão 8 — o demo é escrevível de propósito, e o que o
  protege é a sinalização). Usa os papéis de banner que já existem (`warning-surface`,
  `warning-border`): não se inventam cores, e o amarelo é o registo certo — é um aviso, não um erro.
  O estabelecimento fica marcado nos **dois** estados do seletor, com ícone **mais** texto `sr-only`:
  o botão em repouso responde "onde estou?" sem abrir a lista, o item responde "qual deles é?" com
  ela aberta, e a cor nunca comunica sozinha.
- O **seletor de tenant** vive no pé da sidebar (é do shell); o **seletor de loja** fica na barra do
  ecrã (é do ecrã). Parecem a mesma coisa e não são. É também no pé da sidebar que vive a **entrada
  para as Definições**, ao lado do email e da saída da conta — um `<Link>` para `/definicoes` e
  **não** um segundo controlo de tema: há um sítio onde a paleta se troca, e dois eram duas fontes
  para o mesmo gesto.
- **"Definições" e não "Configurações"**: é o termo pt-PT, e o outro é pt-BR. Vale para a copy e não
  para o código (`GET /inventory/configuracao` é um identificador, e renomeá-lo é churn sem leitor);
  o caminho da rota **é** copy e muda com a palavra (ADR 0008: "os URLs são em português porque são
  copy de produto").
- **Todas as definições num ecrã, em secções** (ADR 0019, que supersede a decisão 1 da ADR 0017 —
  dois ecrãs). Aparência · Estabelecimento · Navegação · Equipa, com a **pessoal primeiro** e uma
  **separação visível** antes das da empresa: é o que substitui a fronteira que a ADR 0017 punha no
  menu, onde uma família era um item restrito e a outra não. Cada secção da empresa nomeia o
  **estabelecimento** no seu `<h2>`, que é também a resposta a "qual destas casas é que eu estou a
  configurar?" para quem tem duas. Com **uma secção só não há régua** — uma régua de um segmento é um
  controlo que não escolhe —, logo um `staff` vê "Definições" com a Aparência e mais nada. A secção é
  um search param com queda para o default, e a queda vive no **render**: o papel é por tenant e
  trocar de estabelecimento muda-o sem mudar o URL.
- **Nenhum rótulo nosso viaja no arame.** O que atravessa a API é um id de união fechada ou texto que
  o **tenant** escreveu; o nome e o grupo por omissão de uma rota são copy do produto e vivem no
  registo do cliente, que os resolve. Antes de 2026-10-07 o `grupo` vinha resolvido, e como o
  `PUT /menu` é substituição total a primeira gravação **congelava** "Inventário" na linha do tenant
  — medido na base de dados, e nenhuma tradução a voltava a alcançar.
- **Um selector de opções fixas é uma régua de segmentos, não uma pilha de cartões.** O
  `/preferencias` escolhe a paleta numa moldura com três segmentos encostados, separados pela régua de
  1px das colunas da tabela, com o escolhido marcado pelo trilho de 4px. A primeira versão eram três
  `rounded-lg` com borda e descrição — o cartão repetido em grelha que o §5 proíbe, de volta pela
  porta do ecrã novo. Em coluna abaixo de `md`, com o trilho a passar de vertical a horizontal.

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
- [ ] `pnpm lint` passou — é ele que mede o contraste AA contra a pior superfície **de cada paleta**
      (calculada, não nomeada), o gamut sRGB a 1e-6 e a paridade desta secção com o `tokens.css`. Não
      se presume nenhum dos três.
      Para os números token a token: `node scripts/check-design-tokens.mjs --detalhe`.
- [ ] Se acrescentei uma cor de estado, tem os **três** papéis (`-surface` e `-border` incluídos) em
      **todas** as paletas e está escrita no §2 — o gate falha nos dois sentidos, e **mede** os três
      papéis.
- [ ] **Se acrescentei uma paleta, acrescentei-a completa.** São 18 tokens de cor mais os dois de
      sombra, medidos, com o bloco neste §2 e no `tokens.css` na mesma alteração (ADR 0015). Um tema a
      17 de 18 falha o `pnpm lint`, e um bloco de paleta parcial também.
- [ ] Nenhum `prefers-color-scheme` em código nosso: a paleta é escolhida pelo atributo `data-tema`,
      que vem da preferência da pessoa (ADR 0016), e não pela configuração do sistema de quem olha.
- [ ] Nenhum `dark:` em código nosso: o variant selecciona dois estados e há três paletas (está
      neutralizado no `tokens.css`), e o gate recusa-o fora dos ficheiros gerados.
- [ ] Nenhum `input` ou controlo delimitado com `--color-border` em vez de `--color-border-strong`.
- [ ] Densidade pelos tokens (`h-linha`, `px-celula-x`, `gap-ritmo`), não por números no JSX.
- [ ] Funciona a **1280px**; e a **360px** se for uma rota de campo (Contar, Receber). Fora dessas,
      scroll horizontal na tabela a 360 é aceite e declarado (§4).
- [ ] `prefers-reduced-motion` respeitado.
- [ ] Nenhum item da secção 5 presente.
- [ ] Skill `web-design-guidelines` corrida sobre os ficheiros alterados (se instalada).
