import { formatDate } from "@/lib/format";

import type { NomesDoCatalogo } from "./hooks/use-nomes-do-catalogo";
import type { CodigoDeErro, ToolCall } from "./schemas";
import { textos } from "./textos";

/**
 * As palavras do assistente: o nome legível de cada tool, a frase de cada
 * `error_code`, e os argumentos de uma chamada ditos em português.
 *
 * ## Os argumentos são texto não confiável
 *
 * Os `args` de uma tool são o JSON que o **modelo** escreveu (ADR 0027,
 * decisão 1), guardado verbatim mesmo quando não validou. Nada aqui os
 * interpreta sem um `typeof` antes, uma data só se formata se for uma data
 * válida (o `Intl` lança numa inválida), e um uuid só vira nome se o catálogo o
 * conhecer. O que não se reconhece **não se mostra** — e o `limite` também não,
 * porque não diz nada a quem lê.
 */

const ROTULO_DA_TOOL = new Map<string, string>([
  ["procurar_artigos", textos.tools.procurarArtigos],
  ["procurar_fornecedores", textos.tools.procurarFornecedores],
  ["saldo_de_artigo", textos.tools.saldoDeArtigo],
  ["artigos_abaixo_do_minimo", textos.tools.artigosAbaixoDoMinimo],
  ["lotes_a_vencer", textos.tools.lotesAVencer],
  ["movimentos_de_artigo", textos.tools.movimentosDeArtigo],
  ["compras_por_periodo", textos.tools.comprasPorPeriodo],
]);

/** O nome legível de uma tool, ou o técnico se o registo crescer antes disto. */
export function rotuloDaTool(nome: string): string {
  return ROTULO_DA_TOOL.get(nome) ?? nome;
}

/**
 * Exaustivo sobre o enum gerado: um `error_code` novo no backend deixa de
 * compilar aqui. Lido por `Map` e não por índice (`detect-object-injection`).
 */
const FRASE_DO_ERRO: Record<CodigoDeErro, string> = {
  teto_de_iteracoes: textos.errosDaMensagem.tetoDeIteracoes,
  teto_de_custo: textos.errosDaMensagem.tetoDeCusto,
  tempo_esgotado: textos.errosDaMensagem.tempoEsgotado,
  resposta_invalida: textos.errosDaMensagem.respostaInvalida,
  erro_do_modelo: textos.errosDaMensagem.erroDoModelo,
  pertenca_revogada: textos.errosDaMensagem.pertencaRevogada,
};

const FRASES_POR_CODIGO = new Map<string, string>(Object.entries(FRASE_DO_ERRO));

/** A frase de um turno que falhou. Sem código, a do modelo: é o caso genérico. */
export function fraseDoErroDaMensagem(codigo: CodigoDeErro | null): string {
  return (
    (codigo === null ? undefined : FRASES_POR_CODIGO.get(codigo)) ??
    textos.errosDaMensagem.erroDoModelo
  );
}

/** As palavras do produto para os tipos do ledger — as do ecrã de artigo. */
const ROTULO_DO_MOVIMENTO = new Map<string, string>([
  ["receipt", textos.tools.movimentoEntrada],
  ["return", textos.tools.movimentoDevolucao],
  ["consumption", textos.tools.movimentoConsumo],
  ["waste", textos.tools.movimentoDesperdicio],
  ["adjustment", textos.tools.movimentoAjuste],
  ["transfer_out", textos.tools.movimentoTransferenciaSaida],
  ["transfer_in", textos.tools.movimentoTransferenciaEntrada],
  ["production_out", textos.tools.movimentoProducaoSaida],
  ["production_in", textos.tools.movimentoProducaoEntrada],
]);

const DATA_CIVIL = /^\d{4}-\d{2}-\d{2}$/;

function texto(valor: unknown): string | null {
  return typeof valor === "string" && valor !== "" ? valor : null;
}

/** Uma data civil válida, formatada; `null` para tudo o que não o seja. */
function dataLegivel(valor: unknown): string | null {
  const bruta = texto(valor);
  if (bruta === null || !DATA_CIVIL.test(bruta)) return null;
  const data = new Date(`${bruta}T00:00:00`);
  return Number.isNaN(data.getTime()) ? null : formatDate(data);
}

function nome(valor: unknown, resolver: (id: string) => string | null): string | null {
  const id = texto(valor);
  return id === null ? null : resolver(id);
}

/**
 * Os argumentos principais de uma chamada, por ordem de leitura: o que se
 * procurou, de que artigo, em que loja, de que fornecedor, em que horizonte.
 */
export function argumentosLegiveis(tool: ToolCall, nomes: NomesDoCatalogo): readonly string[] {
  const { args } = tool;
  const saida: string[] = [];

  const q = texto(args.q);
  if (q !== null) saida.push(`«${q}»`);

  for (const candidato of [
    nome(args.product_id, nomes.artigo),
    nome(args.location_id, nomes.loja),
    nome(args.supplier_id, nomes.fornecedor),
  ]) {
    if (candidato !== null) saida.push(candidato);
  }

  if (typeof args.dias === "number" && Number.isInteger(args.dias)) {
    saida.push(textos.tools.dias(args.dias));
  }

  const desde = dataLegivel(args.desde);
  const ate = dataLegivel(args.ate);
  if (desde !== null && ate !== null) saida.push(textos.tools.periodo(desde, ate));
  else if (desde !== null) saida.push(textos.tools.desde(desde));
  else if (ate !== null) saida.push(textos.tools.ate(ate));

  if (Array.isArray(args.tipos)) {
    const palavras = args.tipos
      .filter((tipo): tipo is string => typeof tipo === "string")
      .map((tipo) => ROTULO_DO_MOVIMENTO.get(tipo) ?? tipo);
    if (palavras.length > 0) saida.push(palavras.join(", "));
  }

  return saida;
}
