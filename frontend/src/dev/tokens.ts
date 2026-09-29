/**
 * O inventário dos tokens de cor do DESIGN.md §2 e os pares que têm de passar
 * WCAG AA. Usado só pela página `/dev/tokens`.
 *
 * As classes de swatch estão escritas uma a uma de propósito: o Tailwind não
 * gera `bg-${nome}` dinâmico, e listá-las é ao mesmo tempo a prova de que os
 * 18 tokens produzem utilities que compilam.
 */

export const SURFACES = ["background", "surface", "surface-2"] as const;
export const STATES = ["success", "warning", "danger"] as const;

export type Surface = (typeof SURFACES)[number];
export type State = (typeof STATES)[number];

export type TokenName =
  | Surface
  | "border"
  | "border-strong"
  | "foreground"
  | "muted-foreground"
  | "primary"
  | "primary-foreground"
  | State
  | `${State}-surface`
  | `${State}-border`;

export interface TokenGroup {
  readonly title: string;
  readonly note: string;
  readonly tokens: readonly TokenName[];
}

export const TOKEN_GROUPS: readonly TokenGroup[] = [
  {
    title: "Superfícies",
    note: "Página, cartão e superfície elevada. Separadas por borda de 1px, não por sombra.",
    tokens: ["background", "surface", "surface-2"],
  },
  {
    title: "Bordas",
    note: "Dois papéis: separador decorativo (isento dos 3:1) e fronteira de componente (3:1).",
    tokens: ["border", "border-strong"],
  },
  {
    title: "Texto",
    note: "Sobre qualquer das três superfícies.",
    tokens: ["foreground", "muted-foreground"],
  },
  {
    title: "Marca",
    note: "Um único acento. Também é a cor do anel de foco.",
    tokens: ["primary", "primary-foreground"],
  },
  {
    title: "Estado",
    note: "Três papéis por estado: texto e ícone, preenchimento suave, borda desse preenchimento.",
    tokens: [
      "success",
      "success-surface",
      "success-border",
      "warning",
      "warning-surface",
      "warning-border",
      "danger",
      "danger-surface",
      "danger-border",
    ],
  },
];

export const SWATCH_CLASS: Readonly<Record<TokenName, string>> = {
  background: "bg-background",
  surface: "bg-surface",
  "surface-2": "bg-surface-2",
  border: "bg-border",
  "border-strong": "bg-border-strong",
  foreground: "bg-foreground",
  "muted-foreground": "bg-muted-foreground",
  primary: "bg-primary",
  "primary-foreground": "bg-primary-foreground",
  success: "bg-success",
  "success-surface": "bg-success-surface",
  "success-border": "bg-success-border",
  warning: "bg-warning",
  "warning-surface": "bg-warning-surface",
  "warning-border": "bg-warning-border",
  danger: "bg-danger",
  "danger-surface": "bg-danger-surface",
  "danger-border": "bg-danger-border",
};

export const ALL_TOKENS: readonly TokenName[] = TOKEN_GROUPS.flatMap((group) => group.tokens);

export type Requirement = "text" | "ui" | "exempt";

export interface ContrastCheck {
  readonly foreground: TokenName;
  readonly background: TokenName;
  readonly requirement: Requirement;
  readonly role: string;
}

export const MINIMUM: Readonly<Record<Requirement, number>> = {
  text: 4.5,
  ui: 3,
  exempt: 0,
};

const textOnSurfaces = (token: TokenName, role: string): ContrastCheck[] =>
  SURFACES.map((surface) => ({
    foreground: token,
    background: surface,
    requirement: "text" as const,
    role,
  }));

const borderOnSurfaces = (token: TokenName, role: string): ContrastCheck[] =>
  SURFACES.map((surface) => ({
    foreground: token,
    background: surface,
    requirement: "ui" as const,
    role,
  }));

export const CONTRAST_CHECKS: readonly ContrastCheck[] = [
  ...textOnSurfaces("foreground", "texto principal"),
  ...textOnSurfaces("muted-foreground", "texto secundário"),
  ...textOnSurfaces("primary", "texto e ícone de acento"),
  ...STATES.flatMap((state) => textOnSurfaces(state, `texto de ${state}`)),
  {
    foreground: "primary-foreground",
    background: "primary",
    requirement: "text",
    role: "texto sobre botão sólido",
  },
  ...STATES.map(
    (state): ContrastCheck => ({
      foreground: "primary-foreground",
      background: state,
      requirement: "text",
      role: "texto sobre botão sólido",
    }),
  ),
  ...STATES.map(
    (state): ContrastCheck => ({
      foreground: "foreground",
      background: `${state}-surface`,
      requirement: "text",
      role: "texto sobre banner",
    }),
  ),
  ...borderOnSurfaces("border-strong", "fronteira de input"),
  ...STATES.flatMap((state) => borderOnSurfaces(`${state}-border`, "borda de banner")),
  ...SURFACES.map(
    (surface): ContrastCheck => ({
      foreground: "border",
      background: surface,
      requirement: "exempt",
      role: "separador decorativo",
    }),
  ),
];
