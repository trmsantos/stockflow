# DESIGN.md — Sistema visual

O agente lê este ficheiro antes de qualquer trabalho de UI. O objetivo é que a aplicação
tenha uma identidade própria e não pareça gerada por IA. Isso consegue-se com decisões
concretas (abaixo), não com adjetivos.

> Preenche a secção "Identidade" para cada projeto. Tudo o resto é regra transversal.

---

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

```css
@theme {
  /* Superfícies */
  --color-background: oklch(0.985 0.002 250);
  --color-surface:    oklch(1 0 0);
  --color-surface-2:  oklch(0.965 0.003 250);
  --color-border:     oklch(0.90 0.004 250);

  /* Texto */
  --color-foreground:       oklch(0.20 0.01 250);
  --color-muted-foreground: oklch(0.50 0.01 250);

  /* Marca — UMA cor de acento, usada com parcimónia */
  --color-primary:            oklch(0.52 0.14 165);   /* verde-azulado escuro; único acento */
  --color-primary-foreground: oklch(0.99 0 0);

  /* Estado */
  --color-success: oklch(0.62 0.15 150);
  --color-warning: oklch(0.75 0.15 80);
  --color-danger:  oklch(0.58 0.20 25);
}

@media (prefers-color-scheme: dark) { /* redefinir todos os tokens acima */ }
```

Regras:
- Uma cor de acento. Gradientes só se a identidade os pedir explicitamente; nunca como default.
- Cinzentos com um ligeiro tom (o `0.002–0.01` de chroma acima), nunca `#888` puro.
- Contraste mínimo WCAG AA (4.5:1 texto, 3:1 UI). Verificar com o plugin de a11y.

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
- [ ] Contraste AA verificado.
- [ ] Funciona a 360px.
- [ ] `prefers-reduced-motion` respeitado.
- [ ] Nenhum item da secção 5 presente.
- [ ] Skill `web-design-guidelines` corrida sobre os ficheiros alterados (se instalada).
