/**
 * Matemática de cor para a página `/dev/tokens`. Só corre em desenvolvimento.
 *
 * Existe por uma razão: o DESIGN.md §2 exige contraste AA verificado, e
 * "verificado" não pode querer dizer "o documento diz que sim". Isto lê os
 * tokens tal como o browser os resolve — no modo em que a página está — e
 * calcula o contraste WCAG 2.1 real.
 *
 * Um `oklch()` fora do gamut sRGB é mapeado pelo browser em silêncio, e o
 * contraste do que aparece no ecrã deixa de ser o do valor escrito. Por isso o
 * cálculo reduz o croma até caber no gamut (aproximação do algoritmo de
 * gamut mapping do CSS Color 4) e assinala que o fez.
 */

export interface LinearRgb {
  r: number;
  g: number;
  b: number;
}

export interface ResolvedColor {
  /** O valor tal como está no token, ex. `oklch(0.512 0.14 150)`. */
  value: string;
  /** Projeção em sRGB, para mostrar ao lado do oklch. */
  hex: string;
  /** Luminância relativa WCAG. */
  luminance: number;
  /** O browser teve de reduzir o croma para caber em sRGB. */
  clamped: boolean;
}

const OKLCH = /^oklch\(\s*([\d.]+)%?\s+([\d.]+)\s+([\d.]+)(?:deg)?\s*\)$/i;

function oklchToLinearRgb(l: number, c: number, hDeg: number): LinearRgb {
  const h = (hDeg * Math.PI) / 180;
  const a = c * Math.cos(h);
  const b = c * Math.sin(h);

  const lp = l + 0.3963377774 * a + 0.2158037573 * b;
  const mp = l - 0.1055613458 * a - 0.0638541728 * b;
  const sp = l - 0.0894841775 * a - 1.291485548 * b;

  const lc = lp * lp * lp;
  const mc = mp * mp * mp;
  const sc = sp * sp * sp;

  return {
    r: 4.0767416621 * lc - 3.3077115913 * mc + 0.2309699292 * sc,
    g: -1.2684380046 * lc + 2.6097574011 * mc - 0.3413193965 * sc,
    b: -0.0041960863 * lc - 0.7034186147 * mc + 1.707614701 * sc,
  };
}

const EPSILON = 1e-5;

function inGamut({ r, g, b }: LinearRgb): boolean {
  return [r, g, b].every((channel) => channel >= -EPSILON && channel <= 1 + EPSILON);
}

/** Reduz o croma por bissecção até o valor caber em sRGB. */
function fitToGamut(l: number, c: number, h: number): { rgb: LinearRgb; clamped: boolean } {
  const direct = oklchToLinearRgb(l, c, h);
  if (inGamut(direct)) return { rgb: direct, clamped: false };

  let low = 0;
  let high = c;
  for (let i = 0; i < 24; i += 1) {
    const mid = (low + high) / 2;
    if (inGamut(oklchToLinearRgb(l, mid, h))) low = mid;
    else high = mid;
  }
  return { rgb: oklchToLinearRgb(l, low, h), clamped: true };
}

const clamp01 = (value: number): number => Math.min(1, Math.max(0, value));

function encode(channel: number): number {
  const c = clamp01(channel);
  return c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;
}

function toHex({ r, g, b }: LinearRgb): string {
  const byte = (channel: number): string =>
    Math.round(encode(channel) * 255)
      .toString(16)
      .padStart(2, "0");
  return `#${byte(r)}${byte(g)}${byte(b)}`;
}

/** Interpreta um valor de token. Devolve `null` se não for um `oklch()`. */
export function resolveColor(value: string): ResolvedColor | null {
  const match = OKLCH.exec(value.trim());
  if (!match) return null;

  const [, rawL, rawC, rawH] = match;
  if (rawL === undefined || rawC === undefined || rawH === undefined) return null;

  const l = Number(rawL) > 1 ? Number(rawL) / 100 : Number(rawL);
  const { rgb, clamped } = fitToGamut(l, Number(rawC), Number(rawH));

  return {
    value: value.trim(),
    hex: toHex(rgb),
    luminance: 0.2126 * clamp01(rgb.r) + 0.7152 * clamp01(rgb.g) + 0.0722 * clamp01(rgb.b),
    clamped,
  };
}

/** Contraste WCAG 2.1 entre duas luminâncias relativas. */
export function contrastRatio(a: number, b: number): number {
  const lighter = Math.max(a, b);
  const darker = Math.min(a, b);
  return (lighter + 0.05) / (darker + 0.05);
}

export function formatRatio(ratio: number): string {
  return `${ratio.toFixed(2)}:1`;
}
