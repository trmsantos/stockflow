import type {
  BaseDaReceita,
  BaseDosSalarios,
  CategoriaDeOutroCusto,
  ExclusaoDoResultado,
  Granularidade,
  IdDeCusto,
  IdDeParteDeSalarios,
  IdDeSerie,
  Indisponibilidade,
  MotivoDeQuebra,
  OrigemDaReceita,
  OrigemDosSalarios,
  Periodo,
} from "./schemas";
import { eNegativo, eZero } from "./schemas";
import { textos } from "./textos";

/**
 * O vocabulário do painel — **os ids vivem aqui, as palavras no catálogo**.
 *
 * As palavras passaram para o `textos.pt.ts` a 2026-10-07 (ADR 0019, decisão 3)
 * e os `Record` ficaram, porque são coisas diferentes: o catálogo guarda a
 * palavra em cada língua, e é o `Record` que amarra a palavra ao contrato. Cada
 * folha é **nomeada individualmente** aqui, e não entregue em bloco — é o que
 * mantém o `check-textos.mjs` a poder podar uma chave que ninguém lê.
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
  today: textos.periodos.hojeCurto,
  "7d": textos.periodos.seteDiasCurto,
  "30d": textos.periodos.trintaDiasCurto,
  month: textos.periodos.esteMesCurto,
  prev_month: textos.periodos.mesAnteriorCurto,
};

const ROTULOS_CURTOS = new Map<string, string>(Object.entries(ROTULO_CURTO_DO_PERIODO));

export function rotuloCurtoDoPeriodo(periodo: Periodo): string {
  return ROTULOS_CURTOS.get(periodo) ?? periodo;
}

const ROTULO_DO_PERIODO: Record<Periodo, string> = {
  today: textos.periodos.hoje,
  "7d": textos.periodos.seteDias,
  "30d": textos.periodos.trintaDias,
  month: textos.periodos.esteMes,
  prev_month: textos.periodos.mesAnterior,
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
  purchases: textos.custos.comprasRotulo,
  goods_consumed: textos.custos.consumoRotulo,
  waste: textos.custos.desperdicioRotulo,
  unknown_shrinkage: textos.custos.quebraRotulo,
  payroll: textos.custos.pessoalRotulo,
  other: textos.custos.fixosRotulo,
};

const ROTULOS_DE_CUSTO = new Map<string, string>(Object.entries(ROTULO_DE_CUSTO));

export function rotuloDeCusto(id: IdDeCusto): string {
  return ROTULOS_DE_CUSTO.get(id) ?? id;
}

/**
 * A anotação de cada linha — o `← dinheiro que saiu` do bloco da ADR 0013
 * decisão 4, que é o que impede o mês do stock-up de ser lido como prejuízo.
 *
 * **Era uma coluna da tabela ("O QUE É") e desde 2026-10-06 é uma camada.** A
 * coluna era a maior massa de texto do painel — cerca de trinta frases num ecrã
 * de 3630px —, e o dono do produto leu-a como um manual de instruções. Cada nota
 * está agora no `title` da rubrica a que pertence e aparece como **sub-linha**
 * com o `?explicar=1` (ver `components/explicar.tsx`). Uma linha própria e nunca
 * uma segunda linha dentro da célula: uma sub-linha de 13px numa célula de 44px
 * cresce a linha e desfaz o ritmo da tabela (DESIGN.md §4, lição 3).
 */
const NOTA_DE_CUSTO: Record<IdDeCusto, string> = {
  purchases: textos.custos.comprasNota,
  goods_consumed: textos.custos.consumoNota,
  waste: textos.custos.desperdicioNota,
  unknown_shrinkage: textos.custos.quebraNota,
  payroll: textos.custos.pessoalNota,
  other: textos.custos.fixosNota,
};

const NOTAS_DE_CUSTO = new Map<string, string>(Object.entries(NOTA_DE_CUSTO));

export function notaDeCusto(id: IdDeCusto): string {
  return NOTAS_DE_CUSTO.get(id) ?? "";
}

const ROTULO_DE_SERIE: Record<IdDeSerie, string> = {
  revenue: textos.grafico.serieVendas,
  purchases: textos.grafico.serieCompras,
};

const ROTULOS_DE_SERIE = new Map<string, string>(Object.entries(ROTULO_DE_SERIE));

export function rotuloDeSerie(id: IdDeSerie): string {
  return ROTULOS_DE_SERIE.get(id) ?? id;
}

/**
 * De que família de dados depende cada série do gráfico — `null` quando ela não
 * depende de nada que possa faltar.
 *
 * Existe para a legenda poder dizer **porquê** quando uma série não vem: a
 * resposta do `/reporting/series` não traz `data_quality`, logo o id da série
 * tem de saber para que declaração olhar. O `Record` sobre a união falha nos
 * dois sentidos, como o resto deste ficheiro: uma série nova sem família
 * declarada não compila.
 */
const FAMILIA_DA_SERIE: Record<IdDeSerie, Indisponibilidade | null> = {
  revenue: "revenue",
  purchases: null,
};

const FAMILIAS_DAS_SERIES = new Map<string, Indisponibilidade | null>(
  Object.entries(FAMILIA_DA_SERIE),
);

export function razaoDaSerieEmFalta(
  id: IdDeSerie,
  declaradas: readonly Indisponibilidade[],
): string {
  const familia = FAMILIAS_DAS_SERIES.get(id) ?? null;
  return familia === null ? textos.falta.semRazao : ausenciaDe(familia, declaradas);
}

const ROTULO_DA_GRANULARIDADE: Record<Granularidade, string> = {
  day: textos.grafico.diaADia,
  week: textos.grafico.semanaASemana,
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
  expired: textos.motivos.expirado,
  spoiled: textos.motivos.estragado,
  breakage: textos.motivos.quebra,
  prep_loss: textos.motivos.perdaDePreparacao,
  other: textos.motivos.outro,
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
  return eNegativo(valor) ? textos.perdas.excedenteDeContagem : textos.custos.quebraRotulo;
}

/**
 * A nota da mesma linha, e muda pela mesma razão: sob "Excedente de contagem" a
 * frase "o líquido das contagens" não diz o que aconteceu. O que aconteceu é
 * que se encontrou mais do que o sistema dizia.
 */
export function notaDaQuebraDesconhecida(valor: string): string {
  return eNegativo(valor) ? textos.perdas.excedenteNota : textos.custos.quebraNota;
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
  if (eZero(valor)) return textos.dinheiro.variacaoIgual;
  return eNegativo(valor) ? textos.dinheiro.variacaoGastou : textos.dinheiro.variacaoEncheu;
}

/* ---------------------------------------------------------------------------
 * A receita: os dois valores, e qual deles é o registado.
 * ------------------------------------------------------------------------- */

const NOTA_DA_BASE_DA_RECEITA: Record<BaseDaReceita, string> = {
  gross: textos.receita.brutoNota,
  net: textos.receita.liquidoNota,
};

const NOTAS_DA_BASE = new Map<string, string>(Object.entries(NOTA_DA_BASE_DA_RECEITA));

export function notaDaBaseDaReceita(base: BaseDaReceita): string {
  return NOTAS_DA_BASE.get(base) ?? "";
}

/* ---------------------------------------------------------------------------
 * O que o painel **ainda não sabe** — os três ids do `unavailable` e as
 * palavras com que o ecrã os diz (ADR 0029, decisão 1).
 *
 * Os ids nunca chegam ao ecrã. Um `revenue` impresso cru seria um rótulo técnico
 * vindo do arame, que é exactamente o que a decisão 5 da ADR 0013 proíbe — e,
 * pior, seria a palavra errada: o dono não perguntou por um campo, perguntou
 * quanto vendeu.
 * ------------------------------------------------------------------------- */

const NOME_DO_QUE_FALTA: Record<Indisponibilidade, string> = {
  revenue: textos.falta.vendasCampo,
  payroll: textos.falta.pessoalCampo,
  other_costs: textos.falta.fixosCampo,
};

const NOMES_DO_QUE_FALTA = new Map<string, string>(Object.entries(NOME_DO_QUE_FALTA));

export function nomeDoQueFalta(id: Indisponibilidade): string {
  return NOMES_DO_QUE_FALTA.get(id) ?? id;
}

/** A frase inteira: vai ao `title` e à camada do `?explicar=1`. */
const FRASE_DO_QUE_FALTA: Record<Indisponibilidade, string> = {
  revenue: textos.falta.vendasFrase,
  payroll: textos.falta.pessoalFrase,
  other_costs: textos.falta.fixosFrase,
};

const FRASES_DO_QUE_FALTA = new Map<string, string>(Object.entries(FRASE_DO_QUE_FALTA));

export function fraseDoQueFalta(id: Indisponibilidade): string {
  return FRASES_DO_QUE_FALTA.get(id) ?? "";
}

/** A forma curta, para o sítio exacto onde o número estaria. */
const AUSENCIA_CURTA: Record<Indisponibilidade, string> = {
  revenue: textos.falta.vendasCurto,
  payroll: textos.falta.pessoalCurto,
  other_costs: textos.falta.fixosCurto,
};

const AUSENCIAS_CURTAS = new Map<string, string>(Object.entries(AUSENCIA_CURTA));

/**
 * **A frase que substitui um número ausente**, e a razão vem da lista do
 * servidor — não de um `if` escrito aqui.
 *
 * Um campo a `null` e a família **não** declarada é um estado possível e não é
 * um erro do ecrã: o servidor pode vir a ter uma razão que este catálogo ainda
 * não sabe dizer. Aí escreve-se que não se sabe, sem inventar o porquê. Entre
 * um traço e uma meia-verdade, isto é a terceira hipótese.
 */
export function ausenciaDe(
  id: Indisponibilidade,
  declaradas: readonly Indisponibilidade[],
): string {
  if (!declaradas.includes(id)) return textos.falta.semRazao;
  return AUSENCIAS_CURTAS.get(id) ?? textos.falta.semRazao;
}

const ROTULO_DA_ORIGEM_DA_RECEITA: Record<OrigemDaReceita, string> = {
  none: textos.receita.origemNenhuma,
  manual: textos.receita.origemManual,
  pos: textos.receita.origemPos,
};

const ROTULOS_DA_ORIGEM = new Map<string, string>(Object.entries(ROTULO_DA_ORIGEM_DA_RECEITA));

export function rotuloDaOrigemDaReceita(origem: OrigemDaReceita): string {
  return ROTULOS_DA_ORIGEM.get(origem) ?? origem;
}

/* ---------------------------------------------------------------------------
 * O mês: salários, cargos, custos fixos e o que o resultado não inclui.
 * ------------------------------------------------------------------------- */

const ROTULO_DE_PARTE_DE_SALARIOS: Record<IdDeParteDeSalarios, string> = {
  base: textos.salarios.base,
  social_security: textos.salarios.tsu,
  subsidies: textos.salarios.subsidios,
  meal_allowance: textos.salarios.alimentacao,
  insurance: textos.salarios.seguro,
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
 * A forma curta vai ao contador; a longa fica na **nota da linha "Pessoal"** da
 * tabela do resultado, com a decomposição do custo-empresa, onde há largura para
 * ela e onde o interruptor de explicação a revela a quem a pedir.
 */
const ROTULO_DA_BASE_DOS_SALARIOS: Record<BaseDosSalarios, string> = {
  employer_cost: textos.salarios.custoEmpresa,
  gross: textos.salarios.bruto,
};

const ROTULOS_DA_BASE_DOS_SALARIOS = new Map<string, string>(
  Object.entries(ROTULO_DA_BASE_DOS_SALARIOS),
);

export function rotuloDaBaseDosSalarios(base: BaseDosSalarios): string {
  return ROTULOS_DA_BASE_DOS_SALARIOS.get(base) ?? base;
}

const ROTULO_DA_ORIGEM_DOS_SALARIOS: Record<OrigemDosSalarios, string> = {
  contractual: textos.salarios.origemContrato,
  actual: textos.salarios.origemProcessamento,
};

const ROTULOS_DA_ORIGEM_DOS_SALARIOS = new Map<string, string>(
  Object.entries(ROTULO_DA_ORIGEM_DOS_SALARIOS),
);

export function rotuloDaOrigemDosSalarios(origem: OrigemDosSalarios): string {
  return ROTULOS_DA_ORIGEM_DOS_SALARIOS.get(origem) ?? origem;
}

const NOTA_DA_BASE_DOS_SALARIOS: Record<BaseDosSalarios, string> = {
  employer_cost: textos.salarios.custoEmpresaNota,
  gross: textos.salarios.brutoNota,
};

const NOTAS_DOS_SALARIOS = new Map<string, string>(Object.entries(NOTA_DA_BASE_DOS_SALARIOS));

export function notaDaBaseDosSalarios(base: BaseDosSalarios): string {
  return NOTAS_DOS_SALARIOS.get(base) ?? "";
}

const NOTA_DA_ORIGEM_DOS_SALARIOS: Record<OrigemDosSalarios, string> = {
  contractual: textos.salarios.origemContratoNota,
  actual: textos.salarios.origemProcessamentoNota,
};

const NOTAS_DA_ORIGEM_DOS_SALARIOS = new Map<string, string>(
  Object.entries(NOTA_DA_ORIGEM_DOS_SALARIOS),
);

export function notaDaOrigemDosSalarios(origem: OrigemDosSalarios): string {
  return NOTAS_DA_ORIGEM_DOS_SALARIOS.get(origem) ?? "";
}

const ROTULO_DE_OUTRO_CUSTO: Record<CategoriaDeOutroCusto, string> = {
  rent: textos.outrosCustos.renda,
  energy: textos.outrosCustos.energia,
  water: textos.outrosCustos.agua,
  gas: textos.outrosCustos.gas,
  card_fees: textos.outrosCustos.cartoes,
  licences: textos.outrosCustos.licencas,
  accounting: textos.outrosCustos.contabilista,
  other: textos.outrosCustos.outros,
};

const ROTULOS_DE_OUTRO_CUSTO = new Map<string, string>(Object.entries(ROTULO_DE_OUTRO_CUSTO));

export function rotuloDeOutroCusto(categoria: CategoriaDeOutroCusto): string {
  return ROTULOS_DE_OUTRO_CUSTO.get(categoria) ?? categoria;
}

const ROTULO_DE_EXCLUSAO: Record<ExclusaoDoResultado, string> = {
  depreciation: textos.exclusoes.amortizacoes,
  financing: textos.exclusoes.financiamento,
  income_tax: textos.exclusoes.irc,
  owner_compensation: textos.exclusoes.remuneracaoDoDono,
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
  // A junção — vírgulas e o remate — é regra da língua e por isso vive na
  // função do catálogo: o inglês remata com "and" e não com "e".
  return textos.exclusoes.naoInclui(exclusoes.map(rotuloDeExclusao));
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
 *
 * **Encurtou a 2026-10-06 e não saiu.** Eram quatro afirmações: não é
 * comparável, porque a remuneração do dono não entra, porque é distribuição e
 * não despesa, e quanto isso vale em pontos. As duas do meio explicam uma
 * decisão de contabilidade a quem já a tomou; as outras duas são as que mudam o
 * que o dono faz com o número — e são as que ficaram. A explicação inteira está
 * na linha "Pessoal" da tabela do resultado, atrás do interruptor de explicação,
 * que é a camada onde o painel passou a guardar o que não é accionável de
 * relance.
 */
export function avisoDoRacioDePessoal(
  exclusoes: readonly ExclusaoDoResultado[],
): string | null {
  if (!exclusoes.includes("owner_compensation")) return null;
  // A frase **não** usa a palavra "lucro", e a razão está escrita ao lado dela
  // no catálogo: é lá que ela se escreve em cada língua, e é lá que alguém a
  // poderia quebrar sem passar por aqui.
  return textos.pessoal.avisoDoRacio;
}
