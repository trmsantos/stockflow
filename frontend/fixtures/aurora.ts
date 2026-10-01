import type { UnidadeBase } from "../src/features/inventory/schemas.ts";

/**
 * dados-falsos-stockflow — o catálogo da **Pastelaria Aurora**.
 *
 * Nome fictício por regra (guião da sessão 0, §2): com o nome da pastelaria
 * dele, o dono trata os dados como sendo seus e passa a sessão a caçar erros
 * em vez de reagir ao fluxo.
 *
 * Cada artigo está aqui por uma razão nomeada no guião — compra ao saco e
 * consumo ao grama, duas embalagens para o mesmo artigo, validade após
 * abertura, peso variável na fatura, tara retornável, o artigo que ninguém vai
 * contar. Não é uma lista de exemplo: é o conjunto mínimo em que as onze
 * perguntas abertas têm onde acontecer. Mexer num valor é mexer numa afirmação
 * de domínio, e passa pelo `domain-expert`.
 *
 * Este ficheiro tem só o catálogo e as localizações, porque os fluxos Receber,
 * Contar e Alertas vão precisar dos mesmos artigos. O ledger vive no
 * `stock.ts`, e é lá que a mentira é apagável por recurso.
 */

/** Ids estáveis entre reinícios, para um deep link com `?artigo=` continuar a valer. */
function idDeArtigo(n: number): string {
  return `a17e0000-0000-4000-8000-${String(n).padStart(12, "0")}`;
}

function idDeLocalizacao(n: number): string {
  return `c0ca0000-0000-4000-8000-${String(n).padStart(12, "0")}`;
}

export interface LocalizacaoFalsa {
  readonly id: string;
  /** O que vai no search param `loja` do ecrã Stock. */
  readonly slug: "centro" | "mercado" | "cozinha";
  readonly nome: string;
}

/**
 * Duas lojas e produção. A Cozinha só interessa a quem tem produção separada
 * (guião §3, Q4), e é dela que sai a transferência em trânsito.
 */
export const LOCALIZACOES: readonly LocalizacaoFalsa[] = [
  { id: idDeLocalizacao(1), slug: "centro", nome: "Loja Centro" },
  { id: idDeLocalizacao(2), slug: "mercado", nome: "Loja Mercado" },
  { id: idDeLocalizacao(3), slug: "cozinha", nome: "Cozinha" },
];

export interface ArtigoFalso {
  readonly id: string;
  /** Como o staff lhe chama, não a descrição da fatura (guião §1). */
  readonly nomeCurto: string;
  readonly unidadeBase: UnidadeBase;
  /** Unidade de apresentação e o fator para a base. Ver `decimal.ts`. */
  readonly unidadeApresentacao: string;
  readonly fatorApresentacao: number;
  /** Mínimo na unidade base. */
  readonly minimo: string;
  /** Custo médio ponderado por unidade base, 4 casas (`inventory-domain` §6). */
  readonly custoUnitario: string;
}

function artigo(
  n: number,
  nomeCurto: string,
  unidadeBase: UnidadeBase,
  unidadeApresentacao: string,
  fatorApresentacao: number,
  minimo: string,
  custoUnitario: string,
): ArtigoFalso {
  return {
    id: idDeArtigo(n),
    nomeCurto,
    unidadeBase,
    unidadeApresentacao,
    fatorApresentacao,
    minimo,
    custoUnitario,
  };
}

export const ARTIGOS: readonly ArtigoFalso[] = [
  artigo(1, "Farinha T65", "g", "kg", 1000, "10000", "0.0007"),
  artigo(2, "Açúcar branco", "g", "kg", 1000, "10000", "0.0009"),
  artigo(3, "Ovo líquido", "g", "g", 1, "3000", "0.0032"),
  artigo(4, "Ovos M", "un", "un", 1, "60", "0.2100"),
  artigo(5, "Manteiga", "g", "kg", 1000, "2500", "0.0094"),
  artigo(6, "Nata 35%", "ml", "L", 1000, "6000", "0.0029"),
  artigo(7, "Leite UHT", "ml", "L", 1000, "12000", "0.0008"),
  artigo(8, "Café em grão", "g", "kg", 1000, "2000", "0.0180"),
  artigo(9, "Massa folhada", "g", "kg", 1000, "4000", "0.0041"),
  artigo(10, "Chocolate 54%", "g", "kg", 1000, "2000", "0.0094"),
  artigo(11, "Amêndoa laminada", "g", "g", 1, "1000", "0.0135"),
  artigo(12, "Morango", "g", "kg", 1000, "2000", "0.0055"),
  artigo(13, "Fermento fresco", "g", "g", 1, "500", "0.0043"),
  artigo(14, "Queijo flamengo", "g", "kg", 1000, "2000", "0.0079"),
  artigo(15, "Fiambre da perna", "g", "kg", 1000, "2000", "0.0092"),
  artigo(16, "Rissóis", "un", "un", 1, "100", "0.1800"),
  artigo(17, "Óleo de fritar", "ml", "L", 1000, "5000", "0.0019"),
  artigo(18, "Água 0,33 L", "un", "un", 1, "48", "0.2400"),
  artigo(19, "Caixas de bolo", "un", "un", 1, "100", "0.1600"),
  artigo(20, "Saquetas de açúcar", "un", "un", 1, "500", "0.0120"),
  artigo(21, "Bacalhau", "g", "kg", 1000, "3000", "0.0121"),
  artigo(22, "Pastéis de nata", "un", "un", 1, "0", "0.3500"),
];

/**
 * Quem registou. O autor em toda a linha de movimento é o probe da Q7 — sem
 * ele não há como perguntar "a Ana podia ter feito isto? e apagar?".
 */
export const AUTORES = {
  ana: "Ana (balcão)",
  rui: "Rui (produção)",
  dono: "Sofia (gerência)",
} as const;

/** Meia-noite de hoje, hora local. As validades são sempre relativas a isto. */
export function inicioDeHoje(): Date {
  const agora = new Date();
  return new Date(agora.getFullYear(), agora.getMonth(), agora.getDate());
}

/** `2026-10-02`, a `n` dias de hoje. Datas congeladas matam a credibilidade. */
export function dataEmDias(n: number): string {
  const dia = inicioDeHoje();
  dia.setDate(dia.getDate() + n);
  const mes = String(dia.getMonth() + 1).padStart(2, "0");
  const diaDoMes = String(dia.getDate()).padStart(2, "0");
  return `${String(dia.getFullYear())}-${mes}-${diaDoMes}`;
}

/** Hoje às `hora:minuto`, em ISO com fuso. */
export function horaDeHoje(hora: number, minuto: number): string {
  const dia = inicioDeHoje();
  dia.setHours(hora, minuto, 0, 0);
  return dia.toISOString();
}

/** Ontem às `hora:minuto`, para o histórico não começar todo à mesma hora. */
export function horaDeOntem(hora: number, minuto: number): string {
  const dia = inicioDeHoje();
  dia.setDate(dia.getDate() - 1);
  dia.setHours(hora, minuto, 0, 0);
  return dia.toISOString();
}

/** Dias entre hoje e uma data `YYYY-MM-DD`. Negativo se já passou. */
export function diasAte(data: string): number {
  const [ano, mes, dia] = data.split("-").map(Number);
  const alvo = new Date(ano ?? 0, (mes ?? 1) - 1, dia ?? 1);
  const milissegundosPorDia = 24 * 60 * 60 * 1000;
  return Math.round((alvo.getTime() - inicioDeHoje().getTime()) / milissegundosPorDia);
}
