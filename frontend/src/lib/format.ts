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

const dinheiroRedondo = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

const inteiro = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });

const data = new Intl.DateTimeFormat(LOCALE, {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const diaEMes = new Intl.DateTimeFormat(LOCALE, { day: "2-digit", month: "2-digit" });

const hora = new Intl.DateTimeFormat(LOCALE, { hour: "2-digit", minute: "2-digit" });

/**
 * `2026-10-02` é uma **data civil**, não um instante: o `new Date` lê-a como
 * meia-noite UTC e num fuso a oeste de Greenwich mostra o dia anterior. Uma
 * validade que aparece um dia mais cedo é um alerta falso, por isso as datas sem
 * hora levam uma hora local antes de se formatarem.
 */
function paraData(valor: Date | string): Date {
  if (valor instanceof Date) return valor;
  return new Date(valor.length === 10 ? `${valor}T00:00:00` : valor);
}

const relativo = new Intl.RelativeTimeFormat(LOCALE, { numeric: "auto" });

/** `12,500 kg` — três decimais, como o ledger guarda, e unidade sempre visível. */
export function formatQuantity(value: string | number, unit: string): string {
  return `${quantidade.format(Number(value))}${NBSP}${unit}`;
}

/** `78,40 €` */
export function formatMoney(value: string | number): string {
  return dinheiro.format(Number(value));
}

/**
 * `1240 €` — euros sem cêntimos.
 *
 * Para totais de leitura (valor de stock, desperdício da semana), onde o cêntimo
 * é precisão falsa: o número vem de custos médios ponderados e de quantidades
 * estimadas, e mostrá-lo ao cêntimo convida a discutir o cêntimo em vez da
 * ordem de grandeza. Onde o valor é exacto — um total de fatura — usa-se o
 * `formatMoney`.
 */
export function formatMoneyRounded(value: string | number): string {
  return dinheiroRedondo.format(Number(value));
}

/** `360 un` — para unidades que não se contam em frações. */
export function formatCount(value: string | number, unit: string): string {
  return `${inteiro.format(Number(value))}${NBSP}${unit}`;
}

/** `29/09/2026` */
export function formatDate(value: Date | string): string {
  return data.format(paraData(value));
}

/** `29/09` — numa linha de 56px a validade não tem espaço para o ano. */
export function formatDayMonth(value: Date | string): string {
  return diaEMes.format(paraData(value));
}

/** `06:40` — a hora a que um movimento aconteceu. */
export function formatTime(value: Date | string): string {
  return hora.format(paraData(value));
}

/** `em 2 dias`, `ontem`, `hoje`. É o texto que acompanha o semáforo de validade. */
export function formatDaysAway(days: number): string {
  return relativo.format(days, "day");
}
