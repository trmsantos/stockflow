/**
 * dados-falsos-stockflow — aritmética de quantidades e de euros.
 *
 * Isto não é um utilitário de conveniência: é a razão de o servidor de
 * fixtures poder somar movimentos sem mentir. As quantidades do domínio são
 * `Decimal` com 3 casas e os custos unitários com 4 (`inventory-domain` §2);
 * somar `0.1 + 0.2` em `number` daria `0.30000000000000004` e o ledger falso
 * deixaria de fechar. Tudo aqui é aritmética de inteiros — milésimos para
 * quantidades, décimos de milésimo para custos, cêntimos para euros — e só se
 * formata para string no fim.
 *
 * Os inteiros cabem com folga no `Number.MAX_SAFE_INTEGER`: o maior produto
 * possível neste dataset (32 kg de açúcar × 0,35 €/un) é ~1e11.
 */

const MILESIMO = 1000;
const DECIMILESIMO = 10_000;
const CENTIMO = 100;

function paraInteiro(valor: string, escala: number): number {
  const negativo = valor.startsWith("-");
  const absoluto = negativo ? valor.slice(1) : valor;
  const [inteiro, fracao] = absoluto.split(".");
  const casas = String(escala).length - 1;
  const digitos = (fracao ?? "").padEnd(casas, "0").slice(0, casas);
  const total = Number(inteiro ?? "0") * escala + Number(digitos === "" ? "0" : digitos);
  return negativo ? -total : total;
}

function paraString(inteiro: number, escala: number): string {
  const negativo = inteiro < 0;
  const absoluto = Math.abs(inteiro);
  const casas = String(escala).length - 1;
  const parteInteira = Math.trunc(absoluto / escala);
  const parteFracionaria = String(absoluto % escala).padStart(casas, "0");
  const sinal = negativo ? "-" : "";
  return casas === 0
    ? `${sinal}${String(parteInteira)}`
    : `${sinal}${String(parteInteira)}.${parteFracionaria}`;
}

/** `"2.5"` → `2500`. */
export function milesimosDe(valor: string): number {
  return paraInteiro(valor, MILESIMO);
}

/** `2500` → `"2.500"`. */
export function stringDeMilesimos(milesimos: number): string {
  return paraString(milesimos, MILESIMO);
}

/** `"0.0079"` → `79`. Custo unitário, 4 casas. */
export function decimilesimosDe(valor: string): number {
  return paraInteiro(valor, DECIMILESIMO);
}

/**
 * Valor em cêntimos de uma quantidade em milésimos a um custo em décimos de
 * milésimo: `q/1e3 × c/1e4` euros = `q×c/1e7` euros = `q×c/1e5` cêntimos.
 */
export function centimosDe(milesimos: number, decimilesimos: number): number {
  return Math.round((milesimos * decimilesimos) / 100_000);
}

/** `124000` → `"1240.00"`. */
export function stringDeCentimos(centimos: number): string {
  return paraString(centimos, CENTIMO);
}

/**
 * Converte a quantidade base para a unidade de apresentação do artigo. O
 * fator é do artigo (1 para `un` e para quem se mostra na unidade base, 1000
 * para quem se mostra em kg ou L) — nunca um limiar decidido por valor, senão
 * a mesma coluna mostrava `kg` numa linha e `g` na seguinte.
 */
export function milesimosParaApresentacao(milesimos: number, fator: number): number {
  return Math.round(milesimos / fator);
}
