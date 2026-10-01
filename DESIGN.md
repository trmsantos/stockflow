# DESIGN.md — Sistema visual

O agente lê este ficheiro antes de qualquer trabalho de UI. O objetivo é que a aplicação
tenha uma identidade própria e não pareça gerada por IA. Isso consegue-se com decisões
concretas (abaixo), não com adjetivos.

> Preenche a secção "Identidade" para cada projeto. Tudo o resto é regra transversal.

---

> ## ⚠ O visual deste ficheiro NÃO está aprovado
>
> **2026-10-01.** O dono do produto viu o shell dos quatro ecrãs e rejeitou o visual nos **quatro**
> eixos que lhe apresentei: a paleta e o tom, a densidade e o tamanho, "parece genérico / shadcn por
> defeito", **e a estrutura dos ecrãs**. Não é um retoque de tokens — é um redesenho, e a decisão foi
> registá-lo como dívida e continuar a construir produto em cima dele, porque a estrutura e as sondas
> sobrevivem a uma mudança visual.
>
> **A raiz suspeita é a secção 1, não a 2.** A referência visual que lá está é o **Linear** —
> uma ferramenta de developers, densa, feita para teclado, usada sentado num ecrã grande. O público
> deste produto usa-o **de pé, numa cozinha, com pressa**. Os tokens do §2 derivam desta secção, e a
> estrutura dos ecrãs deriva do princípio de UX que ela fixa: logo o redesenho começa **aqui** e não
> na paleta. Mudar o verde sem mudar a referência dá o mesmo produto noutra cor.
>
> **O que sobrevive, e é deliberado:** a arquitectura dos tokens (uma fonte, um gate que falha se um
> ecrã tiver uma cor literal) e o gate que mede contraste, gamut e a paridade do §2 com o
> `tokens.css`. Um redesenho troca **valores**, não o mecanismo — foi exactamente para isto que o
> mecanismo existe.
>
> **Como alimentar o redesenho, porque "boas ideias de UI" não é accionável:** uma **app com nome**,
> um **ecrã concreto** e a **razão**. "O cartão de topo do X", "a forma como o Y mostra validades".
> A biblioteca de referência do dono do produto é o **mobbin.com** — está atrás de login e o valor
> dela são as imagens, que um agente não vê. O caminho é ele apontar e o agente traduzir em tokens e
> composição.
>
> **Quando:** depois da sessão 0. O que o dono de pastelaria fizer com estes ecrãs muda a estrutura
> **e** o visual, e redesenhar antes é redesenhar duas vezes. O risco aceite em troca está nomeado no
> `SESSION-CONTEXT.md`: um visual que desagrada pode contaminar a conversa, com o dono a reagir ao
> aspecto em vez do fluxo.

## 1. Identidade (preencher por projeto)

| Campo | Valor |
|---|---|
| Nome do produto | StockFlow |
| Público | Donos e chefes de cozinha de restaurantes, pastelarias e cafés; staff de armazém. Usam em telemóvel, em pé, com pressa. |
| Tom em três palavras | Direto, denso, calmo |
| Referência visual principal | Linear (densidade e tipografia) — com mais contraste e alvos de toque maiores |
| O que este produto NÃO é | Não é lúdico, não é "startup roxa", não é software de contabilidade cinzento |

Princípio de UX: cada ecrã responde a uma pergunta que o dono faz de manhã — "o que falta?",
"o que expira?", "quanto deitei fora?". Números grandes, ação principal a um toque.

---

## 2. Tokens (fonte da verdade: `src/styles/tokens.css`)

Todos os tokens são variáveis CSS mapeadas para Tailwind v4 via `@theme`. O agente usa
**apenas** classes derivadas destes tokens. Cores hardcoded são proibidas.

### Cor — semântica, não literal

Três papéis por cor de estado, porque um valor só não serve os três. Uma cor de estado usada
como **texto** sobre o fundo precisa de 4.5:1; a mesma cor como **preenchimento** de um banner
precisa de ter texto legível por cima; e a **borda** desse banner precisa de 3:1 para delimitar
um componente. Um token só para os três papéis é como se perde a acessibilidade sem ninguém dar
por isso — a versão anterior deste ficheiro tinha `warning` a **2.17:1**, abaixo das duas barras
que esta própria secção exige.

```css
@theme {
  /* Superfícies */
  --color-background:  oklch(0.985 0.002 250);
  --color-surface:     oklch(1 0 0);
  --color-surface-2:   oklch(0.965 0.003 250);

  /* Bordas — dois papéis distintos */
  --color-border:        oklch(0.90 0.004 250);   /* separador decorativo; isento dos 3:1 */
  --color-border-strong: oklch(0.626 0.008 250);  /* fronteira de componente (input): 3.2:1 */

  /* Texto */
  --color-foreground:       oklch(0.20 0.01 250);
  --color-muted-foreground: oklch(0.528 0.01 250);

  /* Marca — UMA cor de acento, usada com parcimónia */
  --color-primary:            oklch(0.514 0.105 165);  /* verde-azulado; único acento */
  --color-primary-foreground: oklch(0.99 0 0);

  /* Estado — texto / preenchimento suave / borda */
  --color-success:         oklch(0.512 0.14 150);
  --color-success-surface: oklch(0.95 0.035 150);
  --color-success-border:  oklch(0.610 0.15 150);

  --color-warning:         oklch(0.532 0.11 80);
  --color-warning-surface: oklch(0.95 0.038 80);
  --color-warning-border:  oklch(0.630 0.13 80);

  --color-danger:          oklch(0.552 0.20 25);
  --color-danger-surface:  oklch(0.95 0.020 25);
  --color-danger-border:   oklch(0.650 0.20 25);
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-background:  oklch(0.18 0.006 250);
    --color-surface:     oklch(0.21 0.006 250);
    --color-surface-2:   oklch(0.25 0.007 250);

    --color-border:        oklch(0.30 0.008 250);
    --color-border-strong: oklch(0.544 0.008 250);

    --color-foreground:       oklch(0.96 0.003 250);
    --color-muted-foreground: oklch(0.644 0.01 250);

    --color-primary:            oklch(0.628 0.13 165);
    --color-primary-foreground: oklch(0.16 0.01 250);

    --color-success:         oklch(0.628 0.15 150);
    --color-success-surface: oklch(0.26 0.030 150);
    --color-success-border:  oklch(0.528 0.145 150);

    --color-warning:         oklch(0.648 0.134 80);
    --color-warning-surface: oklch(0.26 0.032 80);
    --color-warning-border:  oklch(0.548 0.113 80);

    --color-danger:          oklch(0.668 0.20 25);
    --color-danger-surface:  oklch(0.26 0.035 25);
    --color-danger-border:   oklch(0.568 0.20 25);
  }
}
```

Como se usam os três papéis, e não há um quarto:
- `--color-<estado>` é **cor de texto e de ícone**, sobre qualquer das três superfícies. Serve
  também de preenchimento de botão sólido, com `--color-primary-foreground` por cima (≥ 5.1:1).
- `--color-<estado>-surface` é o preenchimento suave de um banner ou badge, e o texto por cima é
  `--color-foreground` — nunca a cor de estado, que sobre a própria tinta não tem contraste.
- `--color-<estado>-border` é a borda desse banner, e só isso.

Regras:
- Uma cor de acento. Gradientes só se a identidade os pedir explicitamente; nunca como default.
- Cinzentos com um ligeiro tom (o `0.002–0.01` de chroma acima), nunca `#888` puro.
- **Contraste mínimo WCAG AA: 4.5:1 texto, 3:1 UI, verificado contra a pior das três superfícies**
  — que é o `surface-2` nos dois modos, não o `background`. Medido: **4.800–4.835** para texto e
  **3.208–3.220** para elementos de UI, nos dois modos. A margem é deliberada e estreita, para um
  arredondamento não fazer falhar a barra — e é por isso que não se mede a olho.
- **Isto é um gate, não uma promessa.** O `frontend/scripts/check-design-tokens.mjs` recalcula o
  gamut e o contraste a cada `pnpm lint`, deriva os papéis do **nome** do token (um
  `--color-info-border` novo entra sozinho na regra dos 3:1) e compara esta secção com o
  `tokens.css` token a token. Até aqui as três afirmações desta secção eram prosa: verdadeiras
  quando escritas, e sem nada que as mantivesse verdadeiras. Foi assim que os dois `warning` do
  modo escuro estiveram fora do gamut sem ninguém dar por isso.
- **Todos os valores estão dentro do gamut sRGB**, verificado com tolerância de 1e-6 e não com uma
  margem de arredondamento: o `warning` do modo escuro estava a `-0.0011` no canal azul e uma
  tolerância de `0.002` deixava-o passar como se estivesse dentro. Um `oklch()` fora do gamut é
  distorcido pelo browser em silêncio, e o contraste que se mede deixa de ser o contraste que se vê.
  À luminosidade das tintas (0.95) o vermelho aceita muito menos croma que o verde — daí o
  `danger-surface` ser mais discreto que o `success-surface`. É um limite do sRGB, não uma escolha
  estética, e é também por isso que a croma do `warning` escuro é 0.134 e não 0.135.
- O `--color-border` a **1.22:1** no claro e **1.17:1** no escuro **não** é uma falha: um separador
  decorativo entre superfícies está fora da regra dos 3:1, que se aplica a fronteiras que
  identificam componentes. Para essas há o `--color-border-strong`. Um `input` delimitado com
  `--color-border` é um bug de acessibilidade. A isenção está no gate pelo nome do token, e é a
  única — qualquer outro token que não seja superfície é medido.

### Tipografia

| Papel | Fonte | Fallback |
|---|---|---|
| UI / corpo | IBM Plex Sans | `system-ui, sans-serif` |
| Títulos | IBM Plex Sans, peso 600, tracking -0.02em | idem |
| Mono / dados (quantidades, preços, códigos) | IBM Plex Mono | `ui-monospace, monospace` |

**Proibido como default:** Inter, Roboto, Open Sans, Poppins. São o marcador mais óbvio de UI gerada.

Escala (rem): `0.75 · 0.875 · 1 · 1.125 · 1.25 · 1.5 · 2 · 2.5 · 3.25`.
Line-height: 1.5 corpo, 1.2 títulos. Tracking ligeiramente negativo em títulos grandes (`-0.02em`).
Números tabulares em tabelas e métricas (`font-variant-numeric: tabular-nums`).

### Espaçamento e forma

- Grelha de 4px. Escala: `1 2 3 4 6 8 12 16 24 32` (×4px).
- Radius: **um valor base** por projeto (`--radius: 6px` ou `10px`), derivados `sm = base-2`, `lg = base+4`.
  Não misturar `rounded-full` em botões com `rounded-md` em inputs.
- Sombras: máximo dois níveis (`shadow-sm` para cards, `shadow-lg` para popovers). Sem sombras coloridas.
- Bordas de 1px com `--color-border` são preferíveis a sombras para separar superfícies.

### Movimento

- Duração: 120ms (micro), 200ms (transições), 320ms (entrada de painéis).
- Easing: `cubic-bezier(0.2, 0, 0, 1)` para entradas; `ease-out` para saídas.
- Só anima `transform` e `opacity`. Nunca `width`, `height`, `top`.
- Respeitar `prefers-reduced-motion: reduce` — desligar tudo exceto opacidade.
- Sem animações decorativas em loop. Sem confetti. Sem "hover: scale(1.05)" em cards.

---

## 3. Componentes

Base: **shadcn/ui** em `src/components/ui/`. Instalados via CLI, nunca copiados à mão.
Personalizados uma vez através dos tokens acima — não por componente.

Regras de composição:
- Componentes de feature (`src/features/*/components`) compõem primitivos; não redefinem estilos.
- Um `<Button>` tem no máximo estas variantes: `default | secondary | outline | ghost | destructive`.
  Se precisas de uma sexta, provavelmente precisas de outro componente.
- Estados obrigatórios em tudo o que é interativo: hover, focus-visible, active, disabled, loading.
- Estados obrigatórios em tudo o que carrega dados: loading (skeleton, não spinner), empty, error.
- Tabelas: densas, alinhamento numérico à direita, cabeçalho sticky, sem zebra stripes por default.
- Formulários: label acima do campo, erro abaixo em `--color-danger`, nunca só a cor a comunicar erro.

---

## 4. Layout

- Largura máxima de conteúdo: `72rem` para dashboards, `42rem` para leitura.
- Densidade: **compacta** em desktop; em mobile mantém compacta mas alvos de toque ≥ 44px.
- Navegação: **sidebar fixa** em desktop; **tab bar inferior** (4 itens: Stock · Receber · Contar · Alertas) em mobile.
- Mobile-first. Testar a 360px e 1440px. Os fluxos Receber (fatura) e Contar são desenhados primeiro para mobile.

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
- [ ] Fontes são as do projeto, não Inter/Roboto.
- [ ] Todos os estados (loading/empty/error/disabled/focus) existem.
- [ ] Navegação por teclado funciona; foco é visível.
- [ ] `pnpm lint` passou — é ele que mede o contraste AA contra o `surface-2` (a pior superfície),
      o gamut sRGB a 1e-6 e a paridade desta secção com o `tokens.css`. Não se presume nenhum dos três.
- [ ] Se acrescentei uma cor de estado, tem os **três** papéis (`-surface` e `-border` incluídos) e
      está escrita no §2 — o gate falha nos dois sentidos.
- [ ] Nenhum `input` ou controlo delimitado com `--color-border` em vez de `--color-border-strong`.
- [ ] Funciona a 360px.
- [ ] `prefers-reduced-motion` respeitado.
- [ ] Nenhum item da secção 5 presente.
- [ ] Skill `web-design-guidelines` corrida sobre os ficheiros alterados (se instalada).
