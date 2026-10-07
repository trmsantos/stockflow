import { formatCount, formatQuantity } from "@/lib/format";

import type { EstadoNivel, MotivoQuebra, Quantidade, TipoMovimento } from "./schemas";
import { textos } from "./textos";

/**
 * O vocabulário do módulo: os enums do contrato por extenso (as palavras vêm do
 * `textos.pt.ts`), e a decisão de quantas casas decimais uma quantidade mostra.
 *
 * Vive num ficheiro só porque é a mesma palavra em todos os sítios — a lista, o
 * detalhe e o histórico têm de chamar `waste` "desperdício" e `breakage`
 * "quebra" sem divergirem. Mapas e não objetos indexados por variável: o
 * `security/detect-object-injection` do `eslint.config.js` recusa — e bem — um
 * `OBJETO[chave]` com chave dinâmica.
 */

// As palavras vêm do catálogo; os `Map` ficam aqui, porque é neles que o
// contrato se amarra — um `EstadoNivel` novo tem de passar por esta lista.
// Cada folha é nomeada à parte de propósito: o `check-textos` conta uma chave
// como usada quando alguém a **nomeia**, e entregar o objecto do catálogo
// inteiro deixava as palavras sem uso visível.
const ROTULO_DE_ESTADO = new Map<EstadoNivel, string>([
  ["negativo", textos.vocabulario.estadoNegativo],
  ["esgotado", textos.vocabulario.estadoEsgotado],
  ["baixo", textos.vocabulario.estadoBaixo],
  ["ok", textos.vocabulario.estadoOk],
]);

/** O estado da linha, decidido pelo servidor. Nunca só a cor: isto é o texto. */
export function rotuloDeEstado(estado: EstadoNivel): string {
  return ROTULO_DE_ESTADO.get(estado) ?? estado;
}

const ROTULO_DE_MOVIMENTO = new Map<TipoMovimento, string>([
  ["receipt", textos.vocabulario.movimentoEntrada],
  ["consumption", textos.vocabulario.movimentoConsumo],
  ["waste", textos.vocabulario.movimentoDesperdicio],
  ["adjustment", textos.vocabulario.movimentoAjuste],
  ["transfer_out", textos.vocabulario.movimentoTransferenciaSaida],
  ["transfer_in", textos.vocabulario.movimentoTransferenciaEntrada],
  ["return", textos.vocabulario.movimentoDevolucao],
  // As duas pernas de uma fornada (ADR 0014).
  ["production_out", textos.vocabulario.movimentoProducaoConsumo],
  ["production_in", textos.vocabulario.movimentoProducaoEntrada],
]);

export function rotuloDeMovimento(tipo: TipoMovimento): string {
  return ROTULO_DE_MOVIMENTO.get(tipo) ?? tipo;
}

const ROTULO_DE_MOTIVO = new Map<MotivoQuebra, string>([
  ["expired", textos.vocabulario.motivoExpirado],
  ["spoiled", textos.vocabulario.motivoEstragado],
  ["breakage", textos.vocabulario.motivoQuebra],
  ["prep_loss", textos.vocabulario.motivoPerdaDePreparacao],
  ["other", textos.vocabulario.motivoOutro],
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

/**
 * Os tipos que **não são eventos económicos** (ADR 0014, decisão 2): pares de
 * pernas que se anulam no total do tenant. Um valor que muda de sítio
 * (transferência) ou de forma (produção) não é uma perda nem um ganho, e um
 * histórico que os mostre com o mesmo peso de uma quebra ensina o produto
 * errado — a lista de um artigo numa pastelaria é dominada por fornadas.
 *
 * Vive aqui e não no ecrã para a tabela de nove linhas da ADR 0014 ter **uma**
 * tradução em código. Se um tipo novo entrar sem passar por aqui, entra como
 * evento económico, que é o default seguro: um movimento a mais numa soma de
 * perdas faz perguntar, um a menos passa.
 */
const SEM_EVENTO_ECONOMICO: ReadonlySet<TipoMovimento> = new Set([
  "transfer_out",
  "transfer_in",
  "production_out",
  "production_in",
]);

export function eEventoEconomico(tipo: TipoMovimento): boolean {
  return !SEM_EVENTO_ECONOMICO.has(tipo);
}
