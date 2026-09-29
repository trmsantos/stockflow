/**
 * Formatação para pt-PT, via `Intl`. Nenhum formato à mão.
 *
 * Quantidades e dinheiro vêm da API como strings (`Decimal` no Django, para
 * não perder precisão em JSON). Aqui só se formatam para mostrar — nenhuma
 * conta é feita em `number`.
 *
 * O espaço entre o número e a unidade é um espaço inquebrável: "12,5 kg" não
 * se parte no fim da linha.
 */
const LOCALE = "pt-PT";
const NBSP = " ";

const quantidade = new Intl.NumberFormat(LOCALE, {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});

const dinheiro = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: "EUR",
});

const inteiro = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });

const data = new Intl.DateTimeFormat(LOCALE, {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const relativo = new Intl.RelativeTimeFormat(LOCALE, { numeric: "auto" });

/** `12,500 kg` — três decimais, como o ledger guarda, e unidade sempre visível. */
export function formatQuantity(value: string | number, unit: string): string {
  return `${quantidade.format(Number(value))}${NBSP}${unit}`;
}

/** `78,40 €` */
export function formatMoney(value: string | number): string {
  return dinheiro.format(Number(value));
}

/** `360 un` — para unidades que não se contam em frações. */
export function formatCount(value: string | number, unit: string): string {
  return `${inteiro.format(Number(value))}${NBSP}${unit}`;
}

/** `29/09/2026` */
export function formatDate(value: Date | string): string {
  return data.format(typeof value === "string" ? new Date(value) : value);
}

/** `em 2 dias`, `ontem`, `hoje`. É o texto que acompanha o semáforo de validade. */
export function formatDaysAway(days: number): string {
  return relativo.format(days, "day");
}
