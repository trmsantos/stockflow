import { formatDate } from "@/lib/format";

import type { NomesDoCatalogo } from "./hooks/use-nomes-do-catalogo";
import type { CodigoDeErro, RotuloDeAcao, ToolCall } from "./schemas";
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
  // As doze da leitura total (ADR 0028, decisão 1). Sem elas o rodapé mostrava
  // `rececoes` e `historico_de_precos` ao lado de «Lotes a vencer» — nomes de
  // função do servidor numa linha que é copy.
  ["rececoes", textos.tools.rececoes],
  ["rececao", textos.tools.rececao],
  ["historico_de_precos", textos.tools.historicoDePrecos],
  ["contagens", textos.tools.contagens],
  ["contagem", textos.tools.contagem],
  ["alertas", textos.tools.alertas],
  ["artigo", textos.tools.artigo],
  ["receitas", textos.tools.receitas],
  ["receita", textos.tools.receita],
  ["producoes_recentes", textos.tools.producoesRecentes],
  ["equipa", textos.tools.equipa],
  ["estabelecimento", textos.tools.estabelecimento],
  // A única tool que não lê dados (ADR 0028, decisão 3). No rodapé lê-se
  // «Ajuda · Perdas e ajustes» e não o nome do ficheiro do manual.
  ["ajuda_sobre", textos.tools.ajudaSobre],
]);

/** O nome legível de uma tool, ou o técnico se o registo crescer antes disto. */
export function rotuloDaTool(nome: string): string {
  return ROTULO_DA_TOOL.get(nome) ?? nome;
}

/**
 * Uma tool que **conta linhas**? A ajuda não: devolve um texto do manual, e
 * `0 linhas` ao lado de «Ajuda» é uma contagem de uma coisa que não existe.
 */
export function toolContaLinhas(nome: string): boolean {
  return nome !== "ajuda_sobre";
}

/**
 * Os doze temas do manual, do slug para a palavra de produto (ADR 0028,
 * decisão 3). Um slug que este cliente não conheça **não se mostra**: o nome do
 * ficheiro do servidor não é copy.
 */
const NOME_DO_TEMA = new Map<string, string>([
  ["receber", textos.temas.receber],
  ["rever-linhas", textos.temas.reverLinhas],
  ["perdas-ajustes-transferencias", textos.temas.perdasAjustesTransferencias],
  ["contar", textos.temas.contar],
  ["alertas-e-minimos", textos.temas.alertasEMinimos],
  ["painel", textos.temas.painel],
  ["artigos-sku-embalagens", textos.temas.artigosSkuEmbalagens],
  ["fornecedores", textos.temas.fornecedores],
  ["receitas-e-producao", textos.temas.receitasEProducao],
  ["equipa-e-convites", textos.temas.equipaEConvites],
  ["definicoes", textos.temas.definicoes],
  ["assistente", textos.temas.assistente],
]);

/**
 * A palavra de cada `rotulo_id`, exaustiva sobre o enum gerado: um id novo no
 * backend (depois do `pnpm gen:api`) deixa de compilar aqui em vez de aparecer
 * num botão sem palavra. Lido por `Map`, como o resto do ficheiro
 * (`detect-object-injection`).
 */
const ROTULO_DA_ACAO: Record<RotuloDeAcao, string> = {
  ver_artigo: textos.acoes.verArtigo,
  ver_falta: textos.acoes.verFalta,
  ver_validade: textos.acoes.verValidade,
  ver_desperdicio: textos.acoes.verDesperdicio,
  ver_alertas: textos.acoes.verAlertas,
  rever_rececoes: textos.acoes.reverRececoes,
  ver_rececoes_de_hoje: textos.acoes.verRececoesDeHoje,
  ver_rececoes: textos.acoes.verRececoes,
  ver_rececao: textos.acoes.verRececao,
  ver_contagens: textos.acoes.verContagens,
  ver_painel: textos.acoes.verPainel,
  ver_stock: textos.acoes.verStock,
  ver_equipa: textos.acoes.verEquipa,
  ver_estabelecimento: textos.acoes.verEstabelecimento,
  ver_inicio: textos.acoes.verInicio,
};

const ROTULOS_POR_ID = new Map<string, string>(Object.entries(ROTULO_DA_ACAO));

/**
 * A palavra de uma acção, ou `undefined` se este cliente não conhecer o id.
 *
 * O `undefined` não é defensivismo decorativo: é a segunda metade da regra do
 * `schemas.ts` — uma acção sem palavra **não se mostra**, porque o id técnico
 * (`rever_rececoes`) não é copy e nunca deve chegar a um botão.
 */
export function rotuloDaAcao(id: string): string | undefined {
  return ROTULOS_POR_ID.get(id);
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
  modelo_ocupado: textos.errosDaMensagem.modeloOcupado,
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

  // Primeiro, porque é o assunto da chamada: «Ajuda · Perdas e ajustes».
  const tema = texto(args.tema);
  if (tema !== null) {
    const palavra = NOME_DO_TEMA.get(tema);
    if (palavra !== undefined) saida.push(palavra);
  }

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
