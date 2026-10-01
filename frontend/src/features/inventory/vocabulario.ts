import { formatCount, formatQuantity } from "@/lib/format";

import type { EstadoNivel, MotivoQuebra, Quantidade, TipoMovimento } from "./schemas";

/**
 * O vocabulário do módulo: os enums do contrato em português europeu, e a
 * decisão de quantas casas decimais uma quantidade mostra.
 *
 * Vive num ficheiro só porque é a mesma palavra em todos os sítios — a lista, o
 * detalhe e o histórico têm de chamar `waste` "desperdício" e `breakage`
 * "quebra" sem divergirem. Mapas e não objetos indexados por variável: o
 * `security/detect-object-injection` do `eslint.config.js` recusa — e bem — um
 * `OBJETO[chave]` com chave dinâmica.
 */

const ROTULO_DE_ESTADO = new Map<EstadoNivel, string>([
  ["negativo", "Negativo"],
  ["esgotado", "Esgotado"],
  ["baixo", "Baixo"],
  ["ok", "OK"],
]);

/** O estado da linha, decidido pelo servidor. Nunca só a cor: isto é o texto. */
export function rotuloDeEstado(estado: EstadoNivel): string {
  return ROTULO_DE_ESTADO.get(estado) ?? estado;
}

const ROTULO_DE_MOVIMENTO = new Map<TipoMovimento, string>([
  ["receipt", "Entrada"],
  ["consumption", "Consumo"],
  ["waste", "Desperdício"],
  ["adjustment", "Ajuste"],
  ["transfer_out", "Transferência (saída)"],
  ["transfer_in", "Transferência (entrada)"],
  ["return", "Devolução"],
]);

export function rotuloDeMovimento(tipo: TipoMovimento): string {
  return ROTULO_DE_MOVIMENTO.get(tipo) ?? tipo;
}

const ROTULO_DE_MOTIVO = new Map<MotivoQuebra, string>([
  ["expired", "expirado"],
  ["spoiled", "estragado"],
  ["breakage", "quebra"],
  ["prep_loss", "perda de preparação"],
  ["other", "outro"],
]);

export function rotuloDeMotivo(motivo: MotivoQuebra): string {
  return ROTULO_DE_MOTIVO.get(motivo) ?? motivo;
}

/**
 * Os motivos, na ordem em que o guião da sessão 0 §1 os lista — expirado,
 * estragado, quebra, perda de preparação — mais "outro". A ordem é a da
 * frequência com que acontecem numa pastelaria, não alfabética.
 */
export const MOTIVOS_DE_DESPERDICIO: readonly MotivoQuebra[] = [
  "expired",
  "spoiled",
  "breakage",
  "prep_loss",
  "other",
];

/**
 * Uma quantidade como se escreve: número, unidade visível, e as casas decimais
 * que correspondem ao passo do ledger.
 *
 * A regra é uma só: **o menor dígito visível é a unidade base**. Se a unidade de
 * apresentação é a própria unidade base (g, ml, un), o menor passo possível já é
 * o inteiro e três casas decimais seriam milésimos de grama — ruído, num ecrã
 * que se lê em pé. Se a apresentação é derivada (kg, L), as três casas são
 * exactamente os gramas e os mililitros que o ledger guarda.
 *
 * O que isto assume: uma unidade de apresentação diferente da base é múltipla de
 * 1000. É o que o catálogo tem (g→kg, ml→L) e o que o `format.ts` fixa em três
 * casas. No dia em que houver uma apresentação em caixas de 12, as casas
 * decimais passam a ser dado do servidor, ao lado do par `display`/`display_unit`
 * — não uma segunda conta aqui. Converter unidades no cliente é a fonte nº 1 de
 * bugs de stock (`inventory-domain` §2) e aqui não se converte nada: o par vem
 * pronto do servidor e isto só escolhe o formatador.
 */
export function textoDeQuantidade(quantidade: Quantidade): string {
  return quantidade.display_unit === quantidade.base_unit
    ? formatCount(quantidade.display, quantidade.display_unit)
    : formatQuantity(quantidade.display, quantidade.display_unit);
}
