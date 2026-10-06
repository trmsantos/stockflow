import type {
  BaseDaReceita,
  BaseDosSalarios,
  CategoriaDeOutroCusto,
  ExclusaoDoResultado,
  Granularidade,
  IdDeCusto,
  IdDeParteDeSalarios,
  IdDeSerie,
  MotivoDeQuebra,
  OrigemDaReceita,
  OrigemDosSalarios,
  Periodo,
} from "./schemas";
import { eNegativo, eZero } from "./schemas";

/**
 * O vocabulário do painel — **as palavras vivem aqui, e só aqui**.
 *
 * É a decisão 5 da ADR 0013 a ser cumprida: nenhum rótulo viaja no arame. O
 * servidor manda ids de uniões fechadas e cada um tem a sua palavra num
 * `Record` sobre a união, que é o que faz o `pnpm typecheck` falhar nos **dois**
 * sentidos — um id novo sem palavra não compila, e uma palavra para um id que
 * já não existe também não. A primeira versão da ADR mandava `label` nas séries
 * e era uma segunda fonte para a mesma palavra: a que diverge é sempre a que
 * está no sítio onde ninguém a relê.
 *
 * Dois pares `Record`/`Map` por tabela, como em toda a casa: o `Record` é a
 * garantia e o `Map` é por onde se lê, porque o
 * `security/detect-object-injection` do `eslint.config.js` recusa — e bem — um
 * `OBJETO[chave]` com chave dinâmica. O `?? id` de cada função é inalcançável
 * por construção (o `Map` nasce do `Record` exaustivo) e existe porque
 * `Map.get` devolve `undefined` no tipo.
 *
 * **A palavra "lucro" não aparece neste ficheiro nem em sítio nenhum do ecrã**
 * (ADR 0013, decisão 6). O campo chama-se `result_eur` e lê-se "resultado", com
 * o que fica de fora impresso ao lado a partir do `result_excludes` — porque um
 * resultado que não inclui amortizações nem a remuneração do dono, lido como
 * lucro, é cerca do dobro do lucro real.
 */

/* ---------------------------------------------------------------------------
 * Os períodos. Duas formas da mesma palavra, e as duas são precisas: a curta é
 * um controlo de 40px de altura numa barra onde cinco deles têm de caber, e a
 * longa é a frase que o cabeçalho do bloco escreve ("Mercadoria consumida nos
 * últimos 7 dias").
 * ------------------------------------------------------------------------- */

const ROTULO_CURTO_DO_PERIODO: Record<Periodo, string> = {
  today: "Hoje",
  "7d": "7 dias",
  "30d": "30 dias",
  month: "Este mês",
  prev_month: "Mês anterior",
};

const ROTULOS_CURTOS = new Map<string, string>(Object.entries(ROTULO_CURTO_DO_PERIODO));

export function rotuloCurtoDoPeriodo(periodo: Periodo): string {
  return ROTULOS_CURTOS.get(periodo) ?? periodo;
}

const ROTULO_DO_PERIODO: Record<Periodo, string> = {
  today: "hoje",
  "7d": "nos últimos 7 dias",
  "30d": "nos últimos 30 dias",
  month: "neste mês",
  prev_month: "no mês anterior",
};

const ROTULOS = new Map<string, string>(Object.entries(ROTULO_DO_PERIODO));

export function rotuloDoPeriodo(periodo: Periodo): string {
  return ROTULOS.get(periodo) ?? periodo;
}

/** A ordem em que o seletor os mostra: do mais curto para o mais longo. */
export const PERIODOS: readonly Periodo[] = ["today", "7d", "30d", "month", "prev_month"];

/* ---------------------------------------------------------------------------
 * As quatro linhas do dinheiro, as parcelas de custo e as séries.
 * ------------------------------------------------------------------------- */

const ROTULO_DE_CUSTO: Record<IdDeCusto, string> = {
  purchases: "Compras a fornecedores",
  goods_consumed: "Mercadoria consumida",
  waste: "Desperdício",
  unknown_shrinkage: "Quebra desconhecida",
  payroll: "Pessoal",
  other: "Custos fixos",
};

const ROTULOS_DE_CUSTO = new Map<string, string>(Object.entries(ROTULO_DE_CUSTO));

export function rotuloDeCusto(id: IdDeCusto): string {
  return ROTULOS_DE_CUSTO.get(id) ?? id;
}

/**
 * A anotação de cada linha — o `← dinheiro que saiu` do bloco da ADR 0013
 * decisão 4, que é o que impede o mês do stock-up de ser lido como prejuízo.
 *
 * É uma coluna da tabela e não uma sub-linha dentro da célula, e isso é uma
 * lição paga: uma sub-linha de 13px numa célula de 44px cresce a linha e desfaz
 * o ritmo da tabela (DESIGN.md §4).
 */
const NOTA_DE_CUSTO: Record<IdDeCusto, string> = {
  purchases: "dinheiro que saiu para fornecedores",
  goods_consumed: "o que saiu do stock, ao custo gravado no movimento",
  waste: "já está dentro da mercadoria consumida",
  unknown_shrinkage: "o líquido das contagens",
  payroll: "custo-empresa do mês, nunca rateado por dias",
  other: "renda, energia, água, gás, TPA, licenças, contabilista",
};

const NOTAS_DE_CUSTO = new Map<string, string>(Object.entries(NOTA_DE_CUSTO));

export function notaDeCusto(id: IdDeCusto): string {
  return NOTAS_DE_CUSTO.get(id) ?? "";
}

const ROTULO_DE_SERIE: Record<IdDeSerie, string> = {
  revenue: "Vendas",
  purchases: "Compras",
};

const ROTULOS_DE_SERIE = new Map<string, string>(Object.entries(ROTULO_DE_SERIE));

export function rotuloDeSerie(id: IdDeSerie): string {
  return ROTULOS_DE_SERIE.get(id) ?? id;
}

const ROTULO_DA_GRANULARIDADE: Record<Granularidade, string> = {
  day: "dia a dia",
  week: "semana a semana",
};

const ROTULOS_DA_GRANULARIDADE = new Map<string, string>(
  Object.entries(ROTULO_DA_GRANULARIDADE),
);

export function rotuloDaGranularidade(granularidade: Granularidade): string {
  return ROTULOS_DA_GRANULARIDADE.get(granularidade) ?? granularidade;
}

/* ---------------------------------------------------------------------------
 * As perdas — **duas linhas e não uma** (ADR 0013, decisão 7).
 * ------------------------------------------------------------------------- */

/**
 * Os cinco motivos de quebra, com as **mesmas** palavras do
 * `features/inventory/vocabulario.ts`.
 *
 * A duplicação é da fronteira entre features e não de descuido (ADR 0008,
 * decisão 2: de outra feature importa-se só o `api.ts`), e está no relatório.
 * Se as duas listas divergirem, o mesmo motivo passa a ter duas palavras em
 * dois ecrãs — e o sítio onde isso se nota é aqui, porque o painel e o ecrã de
 * desperdício mostram a mesma quebra.
 */
const ROTULO_DE_MOTIVO: Record<MotivoDeQuebra, string> = {
  expired: "expirado",
  spoiled: "estragado",
  breakage: "quebra",
  prep_loss: "perda de preparação",
  other: "outro",
};

const ROTULOS_DE_MOTIVO = new Map<string, string>(Object.entries(ROTULO_DE_MOTIVO));

export function rotuloDeMotivo(motivo: MotivoDeQuebra): string {
  return ROTULOS_DE_MOTIVO.get(motivo) ?? motivo;
}

/**
 * O rótulo da quebra desconhecida **depende do sinal**, e é uma regra do
 * domínio e não uma formatação: "quando o líquido dos ajustes for positivo o
 * rótulo é **excedente de contagem** e não desperdício negativo" (ADR 0013,
 * decisão 7).
 *
 * O sinal lê-se da string que o servidor mandou (`eNegativo`), sem converter
 * para `number`: ler um sinal não é fazer uma conta.
 */
export function rotuloDaQuebraDesconhecida(valor: string): string {
  return eNegativo(valor) ? "Excedente de contagem" : "Quebra desconhecida";
}

/* ---------------------------------------------------------------------------
 * A variação de stock — a afirmação mais visível do ecrã.
 * ------------------------------------------------------------------------- */

/**
 * O que a variação de stock **quer dizer**, em palavras.
 *
 * É isto que resolve o maior risco do painel: o mês do stock-up natalício
 * deixa de poder ser lido como prejuízo porque aparece **nomeado** — o dono vê
 * o seu próprio gesto em vez de um resultado estranho (ADR 0013, decisão 4).
 *
 * Nenhuma das três tem cor. Um `+1 150 €` não é "bom" nem "mau": é despensa
 * cheia, e a palavra é que o diz. A cor nesta identidade é sinal, não ênfase.
 */
export function notaDaVariacaoDeStock(valor: string): string {
  if (eZero(valor)) return "entrou tanto quanto saiu";
  return eNegativo(valor)
    ? "gastou-se a despensa: saiu mais stock do que entrou"
    : "encheu-se a despensa: entrou mais stock do que saiu";
}

/* ---------------------------------------------------------------------------
 * A receita: os dois valores, e qual deles é o registado.
 * ------------------------------------------------------------------------- */

const NOTA_DA_BASE_DA_RECEITA: Record<BaseDaReceita, string> = {
  gross: "registado com IVA, como no fecho de caixa",
  net: "registado sem IVA",
};

const NOTAS_DA_BASE = new Map<string, string>(Object.entries(NOTA_DA_BASE_DA_RECEITA));

export function notaDaBaseDaReceita(base: BaseDaReceita): string {
  return NOTAS_DA_BASE.get(base) ?? "";
}

const ROTULO_DA_ORIGEM_DA_RECEITA: Record<OrigemDaReceita, string> = {
  none: "as vendas ainda não estão registadas",
  manual: "vendas registadas à mão",
  pos: "vendas vindas do POS",
};

const ROTULOS_DA_ORIGEM = new Map<string, string>(Object.entries(ROTULO_DA_ORIGEM_DA_RECEITA));

export function rotuloDaOrigemDaReceita(origem: OrigemDaReceita): string {
  return ROTULOS_DA_ORIGEM.get(origem) ?? origem;
}

/* ---------------------------------------------------------------------------
 * O mês: salários, cargos, custos fixos e o que o resultado não inclui.
 * ------------------------------------------------------------------------- */

const ROTULO_DE_PARTE_DE_SALARIOS: Record<IdDeParteDeSalarios, string> = {
  base: "Bruto base",
  social_security: "Segurança Social (TSU)",
  subsidies: "Subsídios, em duodécimos",
  meal_allowance: "Subsídio de alimentação",
  insurance: "Seguro de acidentes de trabalho",
};

const ROTULOS_DE_PARTE = new Map<string, string>(Object.entries(ROTULO_DE_PARTE_DE_SALARIOS));

export function rotuloDeParteDeSalarios(id: IdDeParteDeSalarios): string {
  return ROTULOS_DE_PARTE.get(id) ?? id;
}

/**
 * As duas formas de cada palavra do pessoal, e as duas são precisas pela mesma
 * razão medida que as do período: **a nota de um contador da régua não é uma
 * frase**.
 *
 * Medido no banco de ensaio a 1280px: com a frase inteira ("custo-empresa: o
 * bruto mais o que a empresa paga por cima · do contrato, sem trabalho
 * suplementar") o campo cresceu para 660px e a régua de quatro contadores passou
 * a 1287px numa área de 1024 — deslizava na horizontal e punha o rácio de prime
 * cost fora do ecrã. Os campos da régua empacotam à esquerda e **não esticam**,
 * logo quem decide a largura é o texto mais comprido que lá se põe.
 *
 * A forma curta vai ao contador; a longa fica na frase que explica a
 * decomposição, onde há largura para ela.
 */
const ROTULO_DA_BASE_DOS_SALARIOS: Record<BaseDosSalarios, string> = {
  employer_cost: "custo-empresa",
  gross: "bruto",
};

const ROTULOS_DA_BASE_DOS_SALARIOS = new Map<string, string>(
  Object.entries(ROTULO_DA_BASE_DOS_SALARIOS),
);

export function rotuloDaBaseDosSalarios(base: BaseDosSalarios): string {
  return ROTULOS_DA_BASE_DOS_SALARIOS.get(base) ?? base;
}

const ROTULO_DA_ORIGEM_DOS_SALARIOS: Record<OrigemDosSalarios, string> = {
  contractual: "do contrato",
  actual: "do processamento",
};

const ROTULOS_DA_ORIGEM_DOS_SALARIOS = new Map<string, string>(
  Object.entries(ROTULO_DA_ORIGEM_DOS_SALARIOS),
);

export function rotuloDaOrigemDosSalarios(origem: OrigemDosSalarios): string {
  return ROTULOS_DA_ORIGEM_DOS_SALARIOS.get(origem) ?? origem;
}

const NOTA_DA_BASE_DOS_SALARIOS: Record<BaseDosSalarios, string> = {
  employer_cost: "custo-empresa: o bruto mais o que a empresa paga por cima",
  gross: "bruto: o que o trabalhador recebe antes de descontos",
};

const NOTAS_DOS_SALARIOS = new Map<string, string>(Object.entries(NOTA_DA_BASE_DOS_SALARIOS));

export function notaDaBaseDosSalarios(base: BaseDosSalarios): string {
  return NOTAS_DOS_SALARIOS.get(base) ?? "";
}

const NOTA_DA_ORIGEM_DOS_SALARIOS: Record<OrigemDosSalarios, string> = {
  contractual: "do contrato, sem trabalho suplementar",
  actual: "do processamento do mês",
};

const NOTAS_DA_ORIGEM_DOS_SALARIOS = new Map<string, string>(
  Object.entries(NOTA_DA_ORIGEM_DOS_SALARIOS),
);

export function notaDaOrigemDosSalarios(origem: OrigemDosSalarios): string {
  return NOTAS_DA_ORIGEM_DOS_SALARIOS.get(origem) ?? "";
}

const ROTULO_DE_OUTRO_CUSTO: Record<CategoriaDeOutroCusto, string> = {
  rent: "Renda",
  energy: "Energia",
  water: "Água",
  gas: "Gás",
  card_fees: "TPA e cartões",
  licences: "Licenças",
  accounting: "Contabilista",
  other: "Outros",
};

const ROTULOS_DE_OUTRO_CUSTO = new Map<string, string>(Object.entries(ROTULO_DE_OUTRO_CUSTO));

export function rotuloDeOutroCusto(categoria: CategoriaDeOutroCusto): string {
  return ROTULOS_DE_OUTRO_CUSTO.get(categoria) ?? categoria;
}

const ROTULO_DE_EXCLUSAO: Record<ExclusaoDoResultado, string> = {
  depreciation: "amortizações",
  financing: "financiamento",
  income_tax: "IRC",
  owner_compensation: "remuneração do dono",
};

const ROTULOS_DE_EXCLUSAO = new Map<string, string>(Object.entries(ROTULO_DE_EXCLUSAO));

/**
 * Não é exportada, e isso é a regra e não uma omissão: quem fala para fora é a
 * `fraseDasExclusoes`. Uma palavra sozinha ("amortizações") não diz nada no
 * ecrã; a frase inteira ("Não inclui amortizações, financiamento, IRC e
 * remuneração do dono.") é a unidade de sentido, e exportar a peça convidava
 * alguém a montar a frase outra vez noutro sítio.
 */
function rotuloDeExclusao(exclusao: ExclusaoDoResultado): string {
  return ROTULOS_DE_EXCLUSAO.get(exclusao) ?? exclusao;
}

/**
 * A frase que acompanha o resultado — **ao lado do número e não num rodapé**.
 *
 * O `result_eur` ficaria a faltar o que o `result_excludes` enumera, e a ADR
 * 0013 é explícita: a palavra "lucro" não aparece, e o que continua de fora
 * viaja no contrato e imprime-se junto do número. Uma lista vazia devolve
 * `null` e o ecrã não escreve nada — uma frase "não exclui nada" seria uma
 * afirmação que ninguém pediu.
 */
export function fraseDasExclusoes(exclusoes: readonly ExclusaoDoResultado[]): string | null {
  if (exclusoes.length === 0) return null;
  const palavras = exclusoes.map(rotuloDeExclusao);
  const ultima = palavras.at(-1) ?? "";
  const frase =
    palavras.length === 1 ? ultima : `${palavras.slice(0, -1).join(", ")} e ${ultima}`;
  return `Não inclui ${frase}.`;
}

/**
 * A consequência que **tem** de ficar visível quando a remuneração do dono não
 * entra nos custos.
 *
 * É decisão do dono do produto, confirmada contra a prática do sector: o que o
 * dono tira é distribuição de lucro e não despesa, e metê-lo na mão-de-obra
 * inflaciona o custo de pessoal em 4 a 5 pontos. O preço de a decisão estar
 * certa é que o rácio **deixa de ser comparável** com os benchmarks que o dono
 * encontra escritos — e dizê-lo ao lado do rácio é a diferença entre um número
 * honesto e um número que engana sem mentir.
 *
 * Devolve `null` quando a remuneração do dono **está** nos custos: aí o rácio é
 * comparável e a frase seria ruído.
 */
export function avisoDoRacioDePessoal(
  exclusoes: readonly ExclusaoDoResultado[],
): string | null {
  if (!exclusoes.includes("owner_compensation")) return null;
  // **A palavra "lucro" não entra nesta frase**, e isso é a regra do ecrã levada
  // ao sítio onde era mais tentador quebrá-la: a explicação de contabilidade é
  // "o que o dono tira é distribuição de lucro, não despesa", e bastava
  // escrevê-la assim para pôr a palavra ao lado de um número. Uma negação não
  // protege ninguém — quem passa os olhos lê o substantivo, não o "não" —, e é
  // por isso que a frase diz a mesma coisa por outras palavras.
  return (
    "Este rácio não é comparável com os do sector: a remuneração do dono não entra nos " +
    "custos de pessoal, porque o que o dono tira é uma distribuição do que o negócio rende " +
    "e não uma despesa. Quando o dono trabalha no negócio sem se pagar, o custo de pessoal " +
    "real é 4 a 5 pontos mais alto do que este número."
  );
}
