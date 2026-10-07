import { z } from "zod";

/**
 * O contrato do módulo-sumidouro `reporting`, em Zod — os três endpoints do
 * painel de gestão (ADR 0013, decisão 5).
 *
 * Como nos schemas de `inventory` e `purchasing`, este ficheiro é o **rascunho
 * do contrato** que a sessão do backend recebe (ADR 0008, decisão 3): o mesmo
 * ficheiro valida a resposta no cliente e valida o fixture no servidor de
 * desenvolvimento, logo não há duas noções do payload. Os nomes dos campos são
 * os da ADR, letra por letra, porque é esse o contrato que os serializers vão
 * ter de servir; os nomes dos *tipos* são portugueses, porque são nossos.
 *
 * Quatro convenções que vêm da ADR e não da UI:
 *
 *  - **dinheiro é `string`** (`Decimal` no Django). Nenhuma conta é feita em
 *    `number` no cliente, e é por isso que o `share` e o `scale_max_eur`
 *    existem: com eles a única aritmética de um gráfico é `share × píxeis`
 *    (decisão 5). Sem eles, o cliente procurava um máximo e dividia euros;
 *  - **nenhum rótulo viaja no arame**: o servidor manda ids de uniões fechadas
 *    e as palavras vivem no `vocabulario.ts` desta feature, onde o `Record`
 *    sobre a união falha nos dois sentidos. A primeira versão da ADR mandava
 *    `label` nas séries e era uma segunda fonte para a mesma palavra;
 *  - **o servidor decide o que soma** (`is_part_of_total`) e **quem contém
 *    quem** (`part_of`). O cliente indenta e escreve "dos quais";
 *  - **`z.iso.datetime({ offset: true })` e nunca a forma nua.** O Django corre
 *    com `TIME_ZONE = "Europe/Lisbon"` e o DRF serializa
 *    `2026-10-06T11:08:06.340331+01:00`; o `z.iso.datetime()` do Zod 4 só
 *    aceita `Z`. O `inventory/schemas.ts` tem a lição inteira escrita: um
 *    schema demasiado **estreito** não é apanhado pelo servidor de fixtures,
 *    porque o fixture usa `toISOString()` (que devolve sempre `Z`) e é escrito
 *    para satisfazer o schema. Esteve 11 dias a ser uma bomba invisível.
 */

/**
 * `"-2000.00"` — o que o DRF serializa a partir de um `DecimalField`.
 *
 * Duas alternativas e não `^-?\d+(?:\.\d+)?$`: a forma curta tem altura de
 * estrela 2 e o `security/detect-unsafe-regex` do `eslint.config.js` recusa-a.
 * Escrito outra vez aqui (e não importado do `inventory`) porque a fronteira do
 * ADR 0008 decisão 2 só deixa atravessar `@/features/<módulo>/api`: entre
 * features não se partilham schemas. No dia em que o `pnpm gen:api` conhecer
 * estes endpoints, o tipo único passa a ser o gerado.
 */
const decimal = z.string().regex(/^-?\d+$|^-?\d+\.\d+$/, "decimal inválido");

/** `"04:00"`, hora local do estabelecimento (ADR 0013, decisão 8). */
const horaDoDia = z.string().regex(/^\d\d:\d\d$/, "hora inválida");

/** `"2026-10"` — o mês de negócio, no parâmetro e na resposta. */
const mesIso = z.string().regex(/^\d{4}-(?:0[1-9]|1[0-2])$/, "mês inválido (YYYY-MM)");

/* ---------------------------------------------------------------------------
 * Os dois parâmetros, que são diferentes de propósito (ADR 0013, decisão 5):
 * um salário é um facto mensal, e ratear 30 dias por uma janela de 7 inventa
 * precisão que ninguém tem.
 * ------------------------------------------------------------------------- */

export const periodoSchema = z.enum(["today", "7d", "30d", "month", "prev_month"]);

export const mesSchema = mesIso;

/**
 * O período **resolvido**, ecoado pelo servidor: mostrar a fronteira, não
 * esconder (ADR 0013, decisão 5).
 *
 * O `key` é a união fechada e não `str` como a ADR o escreve, e a razão é a
 * própria decisão 5: é um id de que o cliente precisa de uma palavra
 * ("últimos 7 dias"), logo tem de ser exaustivo contra o `Record` do
 * `vocabulario.ts`. Está no relatório como desvio ao texto da ADR.
 */
export const periodoResolvidoSchema = z.object({
  key: periodoSchema,
  since: z.iso.datetime({ offset: true }),
  until: z.iso.datetime({ offset: true }),
  business_day_starts_at: horaDoDia,
});

/* ---------------------------------------------------------------------------
 * `GET /reporting/summary?period=…` — o bloco de período.
 * ------------------------------------------------------------------------- */

/**
 * Os ids de componente de custo (ADR 0013, decisão 5).
 *
 * `payroll` e `other` **só aparecem no `/month`**: o invariante da decisão 6 é
 * que nenhum campo fora de `/reporting/month` é função de `people`, e um total
 * de gastos com mercadoria discriminada revelaria a folha salarial por
 * subtracção. A união é uma só porque o componente é o mesmo; quem decide o que
 * entra em cada resposta é a permissão da view.
 */
export const idDeCustoSchema = z.enum([
  "purchases",
  "goods_consumed",
  "waste",
  "unknown_shrinkage",
  "payroll",
  "other",
]);

/**
 * Uma parcela de custo: **o cliente desenha, não compõe e não soma**.
 *
 * O `is_part_of_total`/`part_of` substituiu um `waste_inside_goods_cost`
 * booleano, e a razão está na ADR: sob consumo o desperdício **está dentro**
 * (senão o balanço de stock não fecha) e sob compras **não está dentro e
 * continua a não ser somável**, porque o que se deitou fora em outubro pode ter
 * sido comprado em setembro. Um booleano não sabe dizer "não está dentro e
 * ainda assim não somes".
 */
export const componenteDeCustoSchema = z.object({
  id: idDeCustoSchema,
  amount_eur: decimal,
  /**
   * 0 a 1. **O denominador é do servidor e a ADR não o fixa para esta lista**
   * (só o fixa para os pontos de série, `value/scale_max`). O fixture usa o
   * maior componente, porque o `summary` não tem total — e um `share` sobre um
   * total que não viaja seria uma divisão que o cliente não pode fazer nem
   * verificar. Está no relatório como lacuna do contrato.
   */
  share: decimal,
  /** O servidor decide o que soma. */
  is_part_of_total: z.boolean(),
  /** O id de quem o contém: "dos quais 420 € foram desperdício". */
  part_of: idDeCustoSchema.nullable(),
});

/**
 * Os cinco motivos de uma quebra.
 *
 * É a **mesma** união que o `motivoQuebraSchema` do `inventory`, escrita outra
 * vez por causa da fronteira entre features (ADR 0008, decisão 2: de outra
 * feature importa-se só o `api.ts`). No backend não há duplicação nenhuma — o
 * `reporting` importa o `inventory.api` —, e no dia em que o `pnpm gen:api`
 * gerar um `MotivoQuebraEnum` as duas passam a derivar dele. Até lá, duas
 * cópias de uma lista fechada de cinco valores é o preço da fronteira, e está
 * no relatório.
 */
export const motivoDeQuebraSchema = z.enum([
  "expired",
  "spoiled",
  "prep_loss",
  "breakage",
  "other",
]);

export const desperdicioPorMotivoSchema = z.object({
  reason: motivoDeQuebraSchema,
  amount_eur: decimal,
  /** Aqui o denominador **é** o total: é uma repartição verdadeira. */
  share: decimal,
  /** Quantos movimentos — "foram 3 vezes" é accionável de outra maneira. */
  movements: z.number().int().nonnegative(),
});

/** Como a receita foi registada: nenhuma, à mão, ou vinda de um POS. */
export const origemDaReceitaSchema = z.enum(["none", "manual", "pos"]);

/**
 * Qual dos dois valores de receita é o **registado** e qual é o derivado.
 *
 * O dono diz "fiz 1 800 € ontem" e esse número é **com** IVA, porque é o fecho
 * de caixa. Mostrar-lhe um líquido onde ele espera um bruto é perder a
 * confiança por 13% sem nenhum erro de cálculo (ADR 0013, decisão 5).
 */
export const baseDaReceitaSchema = z.enum(["gross", "net"]);

/**
 * O painel declara o que não sabe, e a declaração é **parte do contrato**
 * (ADR 0013, decisão 7).
 *
 * Nasce da decisão 1: como o `sales` v1 não escreve no ledger, pode não existir
 * consumo registado nenhum — e aí o painel mostraria 85% de margem. Um painel
 * optimista por omissão destrói a confiança mais depressa do que um prejuízo
 * falso, porque o prejuízo falso faz perguntar e o lucro falso faz acreditar.
 */
export const qualidadeDosDadosSchema = z.object({
  consumption_registered: z.boolean(),
  purchases_awaiting_invoice_eur: decimal,
  /** `null` = nunca houve contagem. Um zero sem contagem é mentira. */
  last_count_at: z.iso.datetime({ offset: true }).nullable(),
  revenue_source: origemDaReceitaSchema,
});

/**
 * `SummaryOut`. **Sem total de gastos e sem resultado**, de propósito: os dois
 * vivem só no `/month`, porque um total com mercadoria discriminada dá a folha
 * salarial por subtracção (ADR 0013, decisão 6).
 *
 * **A razão deste invariante mudou a 2026-10-06, e ele fica.** Era "impede a
 * exposição": o `/summary` era visto pelo encarregado e um total de gastos ao
 * lado da mercadoria dava-lhe a folha salarial por subtracção de rácios. Com o
 * painel inteiro fechado ao dono (os três endpoints passaram a `{owner}`), não
 * há hoje ninguém a quem isso exponha o que quer que seja. Passou a ser "impede
 * que uma abertura futura crie a exposição sem ninguém notar": no dia em que
 * alguém abrir um bloco deste painel ao encarregado — e é um pedido plausível,
 * porque o encarregado compra —, a folha salarial não vem atrás por descuido. O
 * `goods_cost_ratio_pct` fica como está e o `goods_margin_eur` continua fora,
 * pela mesma razão com que a ADR o revogou.
 */
export const resumoDoPeriodoSchema = z.object({
  period: periodoResolvidoSchema,
  revenue_net_eur: decimal,
  revenue_gross_eur: decimal,
  revenue_basis: baseDaReceitaSchema,
  /** Líquido de IVA dedutível e de notas de crédito. */
  purchases_eur: decimal,
  /** Contém o desperdício (ADR 0014). */
  goods_consumed_eur: decimal,
  /**
   * A identidade da decisão 4, afirmada ao cêntimo pelo servidor:
   * `stock_change_eur == purchases_eur − goods_consumed_eur − unknown_shrinkage_eur`.
   * O ecrã imprime-a com os três termos, porque uma identidade que o ecrã
   * mostra é a coisa mais próxima de uma prova que este produto consegue dar
   * sobre dinheiro.
   */
  stock_change_eur: decimal,
  /** Decomposição de `goods_consumed`, nunca parcela a somar. */
  waste_eur: decimal,
  /** O líquido dos `adjustment` de contagem. Positivo = quebra; negativo = excedente. */
  unknown_shrinkage_eur: decimal,
  /** Consumo sobre vendas, em pontos percentuais. `null` quando vendas == 0. */
  goods_cost_ratio_pct: decimal.nullable(),
  stock_value_eur: decimal,
  costs: z.array(componenteDeCustoSchema),
  /** Ordenada pelo servidor, a maior parcela primeiro. */
  waste_by_reason: z.array(desperdicioPorMotivoSchema),
  data_quality: qualidadeDosDadosSchema,
});

/* ---------------------------------------------------------------------------
 * `GET /reporting/series?period=…` — "como é que isto variou".
 * ------------------------------------------------------------------------- */

/** Derivada do período **pelo servidor**, nunca escolhida no cliente. */
export const granularidadeSchema = z.enum(["day", "week"]);

/** `{since, until}` — uma vez, não por série. */
export const intervaloSchema = z.object({
  since: z.iso.datetime({ offset: true }),
  until: z.iso.datetime({ offset: true }),
});

export const pontoDaSerieSchema = z.object({
  value_eur: decimal,
  /** `value / scale_max`. É este campo que torna o desenho uma multiplicação. */
  share: decimal,
});

/**
 * Os ids de série — **dois, e o tecto é da paleta e não da aritmética**.
 *
 * A ADR 0013 deduziu da paleta um limite de quatro séries; o
 * `components/barras-por-periodo.tsx` mediu-o e corrigiu-o para baixo: num
 * gráfico de dinheiro as cores de estado não estão livres (o verde diz "bom" e
 * um custo não é bom; o âmbar diz "aviso" e uma compra não é um aviso), logo há
 * **uma** tinta de acento e **uma** neutra. Duas séries.
 *
 * As duas escolhidas são os dois fluxos de dinheiro — o que entrou e o que saiu
 * para fornecedores. As outras duas linhas da identidade da decisão 4
 * (mercadoria consumida e variação de stock) ficam no bloco de números, e a
 * variação por uma segunda razão que é de desenho e não de cor: **pode ser
 * negativa**, e uma barra de altura negativa não existe neste componente.
 *
 * Um id novo que o servidor mande sem passar por aqui falha alto na validação,
 * e um id novo escrito aqui sem palavra e sem tinta **não compila**.
 */
export const idDeSerieSchema = z.enum(["revenue", "purchases"]);

export const serieSchema = z.object({
  id: idDeSerieSchema,
  unit: z.literal("eur"),
  total_eur: decimal,
  /** Um ponto por intervalo, na mesma ordem dos `buckets`. */
  points: z.array(pontoDaSerieSchema),
});

export const seriesDoPeriodoSchema = z.object({
  period: periodoResolvidoSchema,
  granularity: granularidadeSchema,
  buckets: z.array(intervaloSchema),
  /** O máximo do eixo vem do servidor. */
  scale_max_eur: decimal,
  series: z.array(serieSchema),
});

/* ---------------------------------------------------------------------------
 * `GET /reporting/month?month=YYYY-MM` — o fecho, com salários.
 * Permissão: `PertenceAoTenant + TemPapel.exige(OWNER)`. 403 a quem não é dono,
 * e o cliente não dispara o pedido (ADR 0013, decisão 6).
 * ------------------------------------------------------------------------- */

/** `employer_cost` (default) ou `gross`. O ecrã diz qual é. */
export const baseDosSalariosSchema = z.enum(["employer_cost", "gross"]);

/** `contractual` hoje; `actual` entra com trabalho suplementar (fora do v1). */
export const origemDosSalariosSchema = z.enum(["contractual", "actual"]);

/**
 * As cinco parcelas do custo-empresa.
 *
 * Existem porque um `payroll_eur` sozinho, 32% acima do bruto que o dono tem na
 * cabeça, parece erro — e a decomposição é o que transforma desconfiança em
 * verificação (ADR 0013, decisão 6). Os subsídios de férias e de Natal entram
 * **sempre em duodécimos**: senão junho e novembro parecem catástrofes e os
 * outros dez meses parecem bons.
 */
export const idDeParteDeSalariosSchema = z.enum([
  "base",
  "social_security",
  "subsidies",
  "meal_allowance",
  "insurance",
]);

export const parteDeSalariosSchema = z.object({
  id: idDeParteDeSalariosSchema,
  amount_eur: decimal,
});

/**
 * O custo por **cargo** — e o cargo de RH não é o papel de acesso (ADR 0013,
 * decisão 2). Um "pasteleiro" é uma função; `owner|manager|staff` é o que o
 * pedido pode fazer.
 *
 * O `headcount` viaja porque é ele que diz quando o agregado **não anonimiza
 * nada**: um cargo com uma pessoa é o salário dela com outro nome, e é a razão
 * pela qual este bloco é só do dono.
 */
export const custoPorCargoSchema = z.object({
  role_id: z.uuid(),
  name: z.string().min(1),
  headcount: z.number().int().nonnegative(),
  payroll_eur: decimal,
  share: decimal,
});

/**
 * As categorias de custo fixo mensal (`purchasing_othercost`).
 *
 * A lista é a que a ADR 0013 decisão 3 enumera — renda, energia, água, gás,
 * TPA, licenças, contabilista — mais `other`. **A ADR exige o `domain-expert`
 * para a fechar**, e está no relatório como tal: esta é a versão de trabalho,
 * não a decidida.
 */
export const categoriaDeOutroCustoSchema = z.enum([
  "rent",
  "energy",
  "water",
  "gas",
  "card_fees",
  "licences",
  "accounting",
  "other",
]);

export const outroCustoSchema = z.object({
  category: categoriaDeOutroCustoSchema,
  amount_eur: decimal,
  note: z.string().nullable(),
});

/**
 * O que o resultado **não** inclui, e viaja no contrato em vez de numa nota de
 * rodapé (ADR 0013, decisão 6).
 *
 * `owner_compensation` é o caso que o guião nomeia: em pastelaria o dono não se
 * paga ou paga-se o mínimo, e a margem fica excelente por omissão. Se não
 * houver remuneração de gerência registada, ela aparece aqui e o ecrã diz que a
 * não inclui — e diz, ao lado do rácio de pessoal, que esse rácio não é
 * comparável com benchmarks do sector.
 */
export const exclusaoDoResultadoSchema = z.enum([
  "depreciation",
  "financing",
  "income_tax",
  "owner_compensation",
]);

/** `MonthOut`. A palavra "lucro" não aparece: o campo é `result_eur`. */
export const fechoDoMesSchema = z.object({
  month: mesIso,
  since: z.iso.datetime({ offset: true }),
  until: z.iso.datetime({ offset: true }),
  business_day_starts_at: horaDoDia,
  closed: z.boolean(),
  /**
   * Um mês a correr ao dia 9 não se compara com um fechado, e o `closed`
   * sozinho não evita a leitura errada (ADR 0013, decisão 7).
   */
  days_elapsed: z.number().int().nonnegative(),
  days_in_month: z.number().int().positive(),

  // Os mesmos campos de mercadoria do `SummaryOut`, com o grão do mês de
  // negócio (ADR 0013, decisão 5).
  revenue_net_eur: decimal,
  revenue_gross_eur: decimal,
  revenue_basis: baseDaReceitaSchema,
  purchases_eur: decimal,
  goods_consumed_eur: decimal,
  stock_change_eur: decimal,
  waste_eur: decimal,
  unknown_shrinkage_eur: decimal,
  stock_value_eur: decimal,

  payroll_eur: decimal,
  payroll_basis: baseDosSalariosSchema,
  payroll_source: origemDosSalariosSchema,
  payroll_breakdown: z.array(parteDeSalariosSchema),
  roles: z.array(custoPorCargoSchema),
  other_costs: z.array(outroCustoSchema),
  /**
   * `costs` com as categorias de pessoal — é **outro gráfico** e não o do
   * período com uma barra escondida (ADR 0013, decisão 6).
   *
   * A ADR declara a lista no `SummaryOut` e não a repete aqui, mas os ids
   * `payroll` e `other` do `CostComponentOut` só podem aparecer nesta resposta:
   * é a leitura fiel, e está no relatório como inferência.
   */
  costs: z.array(componenteDeCustoSchema),
  /** Só aqui, porque só aqui há salários. */
  cost_total_eur: decimal,
  result_eur: decimal,
  result_excludes: z.array(exclusaoDoResultadoSchema),
  goods_cost_ratio_pct: decimal.nullable(),
  labour_cost_ratio_pct: decimal.nullable(),
  /** Mercadoria + pessoal sobre vendas. Vive só aqui, pela decisão 6. */
  prime_cost_pct: decimal.nullable(),
  data_quality: qualidadeDosDadosSchema,
});

/* ---------------------------------------------------------------------------
 * Dois predicados sobre a **string** decimal, e é de propósito que não há
 * nenhuma conta aqui.
 *
 * O ecrã precisa de saber o **sinal** de dois valores — a variação de stock
 * ("encheu-se" ou "gastou-se a despensa") e a quebra desconhecida ("quebra" ou
 * "excedente de contagem", ADR 0013 decisão 7) — e precisa de saber se um valor
 * é zero, para não escrever "1 240 € ainda sem fatura" quando não há nenhum.
 *
 * Nenhum dos dois converte para `number`: olham para a string que o servidor
 * mandou. É a diferença entre ler um valor e fazer uma conta com ele, e é a
 * regra da casa a ser cumprida no sítio onde era mais fácil quebrá-la.
 * ------------------------------------------------------------------------- */

export function eNegativo(valor: string): boolean {
  return valor.startsWith("-") && !eZero(valor);
}

export function eZero(valor: string): boolean {
  return /^-?0+$|^-?0+\.0+$/.test(valor);
}

export type Periodo = z.output<typeof periodoSchema>;
export type PeriodoResolvido = z.output<typeof periodoResolvidoSchema>;
export type IdDeCusto = z.output<typeof idDeCustoSchema>;
export type ComponenteDeCusto = z.output<typeof componenteDeCustoSchema>;
export type MotivoDeQuebra = z.output<typeof motivoDeQuebraSchema>;
export type DesperdicioPorMotivo = z.output<typeof desperdicioPorMotivoSchema>;
export type OrigemDaReceita = z.output<typeof origemDaReceitaSchema>;
export type BaseDaReceita = z.output<typeof baseDaReceitaSchema>;
export type QualidadeDosDados = z.output<typeof qualidadeDosDadosSchema>;
export type ResumoDoPeriodo = z.output<typeof resumoDoPeriodoSchema>;
export type Granularidade = z.output<typeof granularidadeSchema>;
export type Intervalo = z.output<typeof intervaloSchema>;
export type PontoDaSerie = z.output<typeof pontoDaSerieSchema>;
export type IdDeSerie = z.output<typeof idDeSerieSchema>;
export type Serie = z.output<typeof serieSchema>;
export type SeriesDoPeriodo = z.output<typeof seriesDoPeriodoSchema>;
export type BaseDosSalarios = z.output<typeof baseDosSalariosSchema>;
export type OrigemDosSalarios = z.output<typeof origemDosSalariosSchema>;
export type IdDeParteDeSalarios = z.output<typeof idDeParteDeSalariosSchema>;
export type ParteDeSalarios = z.output<typeof parteDeSalariosSchema>;
export type CustoPorCargo = z.output<typeof custoPorCargoSchema>;
export type CategoriaDeOutroCusto = z.output<typeof categoriaDeOutroCustoSchema>;
export type OutroCusto = z.output<typeof outroCustoSchema>;
export type ExclusaoDoResultado = z.output<typeof exclusaoDoResultadoSchema>;
export type FechoDoMes = z.output<typeof fechoDoMesSchema>;
