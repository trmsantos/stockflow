import { formatCount, formatQuantity } from "@/lib/format";

import type {
  Conservacao,
  EspecieDeLinha,
  EstadoDeLinha,
  EstadoDeRececao,
  LinhaDeRececao,
  Quantidade,
  TipoDeDocumento,
  TipoValidade,
} from "./schemas";

/**
 * O vocabulário do módulo `purchasing`: os enums do contrato em português
 * europeu, e as duas frases que uma linha de fatura precisa de dizer.
 *
 * Vive num ficheiro só pela mesma razão que o do `inventory`: é a mesma palavra
 * em todos os sítios — a lista, o detalhe e o badge têm de chamar `FS` "fatura
 * simplificada" sem divergirem. Mapas e não objetos indexados por variável: o
 * `security/detect-object-injection` recusa — e bem — um `OBJETO[chave]` com
 * chave dinâmica.
 */

/**
 * A sigla, como vem impressa no documento. É o que a linha da lista mostra,
 * porque é o que está no papel que ele tem na mão — e `guia` em vez de `GR`
 * porque é assim que se diz em voz alta (guião §1).
 */
const SIGLA = new Map<TipoDeDocumento, string>([
  ["FT", "FT"],
  ["FR", "FR"],
  ["FS", "FS"],
  ["NC", "NC"],
  ["GR", "guia"],
]);

export function siglaDeDocumento(tipo: TipoDeDocumento): string {
  return SIGLA.get(tipo) ?? tipo;
}

/** O nome por extenso, para o `title` e para quem lê o ecrã por áudio. */
const NOME_DO_DOCUMENTO = new Map<TipoDeDocumento, string>([
  ["FT", "Fatura"],
  ["FR", "Fatura-recibo"],
  ["FS", "Fatura simplificada"],
  ["NC", "Nota de crédito"],
  ["GR", "Guia de remessa"],
]);

export function nomeDoDocumento(tipo: TipoDeDocumento): string {
  return NOME_DO_DOCUMENTO.get(tipo) ?? tipo;
}

/**
 * O estado de um documento, **em palavra** — que é como o DESIGN.md §3 manda
 * mostrar um estado numa tabela densa, e não num chip.
 *
 * As duas palavras vêm dos badges que a lista usava antes de ser tabela
 * ("precisa de revisão", "no stock"), encurtadas para caberem numa célula de
 * 44px sem truncar. Dizem o que o documento é para o **stock**, que é a pergunta
 * do ecrã: "por rever" é mercadoria cujo stock ainda não existe.
 */
const ESTADO_DE_RECECAO = new Map<EstadoDeRececao, string>([
  ["needs_review", "por rever"],
  ["confirmed", "no stock"],
]);

export function rotuloDeEstadoDeRececao(estado: EstadoDeRececao): string {
  return ESTADO_DE_RECECAO.get(estado) ?? estado;
}

/**
 * O estado de uma linha. Três, e o terceiro é uma decisão e não um problema:
 * `skipped` é a linha que alguém deixou **de fora** desta entrada.
 *
 * "revista" e não "confirmada": o que a linha ganhou foi revisão humana. O
 * movimento no ledger só existe quando o documento inteiro é confirmado, e é a
 * coluna do stock que o diz.
 */
const ESTADO_DE_LINHA = new Map<EstadoDeLinha, string>([
  ["needs_review", "por rever"],
  ["confirmed", "revista"],
  ["skipped", "de fora"],
]);

export function rotuloDeEstadoDeLinha(estado: EstadoDeLinha): string {
  return ESTADO_DE_LINHA.get(estado) ?? estado;
}

const CONSERVACAO = new Map<Conservacao, string>([
  ["frozen", "congelado"],
  ["chilled", "refrigerado"],
  ["ambient", "ambiente"],
]);

export function rotuloDeConservacao(conservacao: Conservacao): string {
  return CONSERVACAO.get(conservacao) ?? conservacao;
}

/**
 * O que a linha é para o stock. "Vasilhame" é a palavra que está na fatura; é a
 * que o dono reconhece, e é a que diz porque é que aquela linha tem valor e não
 * tem quantidade.
 */
const ESPECIE = new Map<EspecieDeLinha, string>([
  ["goods", "mercadoria"],
  ["deposit", "vasilhame"],
  ["charge", "encargo"],
]);

export function rotuloDeEspecie(especie: EspecieDeLinha): string {
  return ESPECIE.get(especie) ?? especie;
}

/**
 * Os dois rótulos que a lei distingue, escritos como na embalagem. Tratar os
 * dois igual perde a credibilidade dos alertas de imediato (guião §2) — e é por
 * isso que a palavra entra aqui, onde a validade é **escrita**, e não só no ecrã
 * onde é lida.
 */
const VALIDADE = new Map<TipoValidade, string>([
  ["use_by", "consumir até"],
  ["best_before", "consumir de preferência antes de"],
]);

export function rotuloDeValidade(tipo: TipoValidade): string {
  return VALIDADE.get(tipo) ?? tipo;
}

/**
 * A forma curta, para caber numa célula de tabela.
 *
 * **"melhor antes" e não "durabilidade mínima", desde 2026-10-06**, por duas
 * razões que se somam. A primeira é de vocabulário: o módulo de inventário já diz
 * "melhor antes de 03/03" nos ecrãs de Stock e de Alertas, e dois módulos com
 * duas palavras para o mesmo conceito é exactamente o que estes ficheiros existem
 * para impedir. A forma legal ("data de durabilidade mínima") continua no
 * `rotuloDeValidade`, que é onde a validade é **escrita** e onde a precisão paga.
 *
 * A segunda é medida: com 19 caracteres, esta sub-linha forçava o `min-content`
 * da coluna da validade a 152px apesar de ela declarar `w-32` (128) — e os 24px
 * a mais saíam da coluna flexível do artigo, que já estava a truncar. Uma coluna
 * de largura fixa **não é** largura fixa se o conteúdo dela pedir mais, e isto
 * só se vê a medir.
 */
const VALIDADE_CURTA = new Map<TipoValidade, string>([
  ["use_by", "consumir até"],
  ["best_before", "melhor antes"],
]);

export function rotuloCurtoDeValidade(tipo: TipoValidade): string {
  return VALIDADE_CURTA.get(tipo) ?? tipo;
}

/**
 * O plural do substantivo da unidade de compra, para a frase da conversão não
 * ler "2 bloco 2,5 kg".
 *
 * É um **conjunto fechado** e com fallback: as unidades que o catálogo conhece
 * estão aqui, e uma unidade nova aparece no singular em vez de ganhar um "s"
 * adivinhado — "2 garrafãos" é pior do que "2 garrafão". Só o primeiro termo do
 * rótulo é pluralizado, porque o resto é o descritivo da embalagem ("caixa
 * 12×1 L" → "caixas 12×1 L").
 */
const PLURAL = new Map<string, string>([
  ["caixa", "caixas"],
  ["bloco", "blocos"],
  ["saco", "sacos"],
  ["pacote", "pacotes"],
  ["rolo", "rolos"],
  ["grade", "grades"],
  ["garrafão", "garrafões"],
  ["plateau", "plateaus"],
  ["peça", "peças"],
  ["lata", "latas"],
  ["embalagem", "embalagens"],
  ["bola", "bolas"],
]);

function pluralizar(rotulo: string, quantidade: number): string {
  if (quantidade === 1) return rotulo;
  const [primeiro, ...resto] = rotulo.split(" ");
  if (primeiro === undefined) return rotulo;
  const plural = PLURAL.get(primeiro);
  if (plural === undefined) return rotulo;
  return [plural, ...resto].join(" ");
}

/**
 * Uma quantidade de fatura: três casas decimais quando a fatura as traz (o
 * queijo pesado a 3,480 kg), nenhuma quando é um número de embalagens.
 *
 * A escolha é pela própria fração do número e não por um limiar de valor: "2
 * caixas" e "3,480 kg" estão os dois certos na mesma coluna, e "2,000 caixas"
 * está errado em qualquer coluna. Nenhuma conta é feita aqui — só se escolhe o
 * formatador.
 */
export function textoDeQuantidadeDaFatura(valor: string, unidade: string): string {
  const numero = Number(valor);
  const rotulo = pluralizar(unidade, numero);
  return Number.isInteger(numero)
    ? formatCount(valor, rotulo)
    : formatQuantity(valor, rotulo);
}

/**
 * Uma quantidade de stock como o ecrã de Stock a escreve: na unidade de
 * apresentação do artigo, com as casas decimais que correspondem ao passo do
 * ledger. É a mesma regra do `inventory` — o menor dígito visível é a unidade
 * base — e está repetida aqui porque as fronteiras do ADR 0008 só deixam
 * importar de outra feature o seu `api.ts`.
 */
export function textoDeQuantidade(quantidade: Quantidade): string {
  return quantidade.display_unit === quantidade.base_unit
    ? formatCount(quantidade.display, quantidade.display_unit)
    : formatQuantity(quantidade.display, quantidade.display_unit);
}

/**
 * A quantidade **na unidade base**, que é a unidade do ledger: "12 000 ml",
 * "5 000 g", "100 un".
 *
 * É esta a metade direita da conversão que o guião §1 manda ter à vista. A
 * esquerda fala a língua do fornecedor ("1 caixa 12×1 L") e esta fala a do
 * stock — e é por isso que não se mostra em kg nem em L aqui: o que o ecrã está
 * a afirmar é exactamente o número que vai entrar no ledger.
 */
export function textoNaUnidadeBase(quantidade: Quantidade): string {
  return formatCount(quantidade.base, quantidade.base_unit);
}

/**
 * `true` quando há de facto uma conversão para mostrar.
 *
 * Uma linha faturada em `un` de um artigo cuja unidade base é `un` não converte
 * nada, e "60 un → 60 un" é ruído numa linha onde cada carácter paga pixéis.
 */
export function temConversao(linha: LinhaDeRececao): boolean {
  const stock = linha.stock_quantity;
  if (stock === null) return false;
  if (linha.packaging !== null) return true;
  if (linha.invoice_unit.toLowerCase() !== stock.base_unit) return true;
  return Number(linha.quantity_received) !== Number(stock.base);
}

/** A metade esquerda da conversão: o que a fatura diz que chegou. */
export function textoDaUnidadeDeCompra(linha: LinhaDeRececao): string {
  return textoDeQuantidadeDaFatura(
    linha.quantity_received,
    linha.packaging?.label ?? linha.invoice_unit,
  );
}

/**
 * `234 567 891` — um NIF em grupos de três, como está impresso e como se lê em
 * voz alta. Nove dígitos seguidos não se conferem a olho.
 */
export function textoDeNif(nif: string): string {
  const grupos = nif.match(/\d{1,3}/g);
  return grupos === null ? nif : grupos.join(" ");
}
