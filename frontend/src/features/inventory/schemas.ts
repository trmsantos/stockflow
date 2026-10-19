import { z } from "zod";

/**
 * O contrato do módulo `inventory`, em Zod.
 *
 * Estes schemas são o **rascunho do contrato** que a sessão do backend recebe
 * (ADR 0008, decisão 3): o mesmo ficheiro valida a resposta no cliente e
 * valida o fixture no servidor de desenvolvimento, logo não há duas noções do
 * payload. Quando os serializers existirem, é o `pnpm gen:api` com o gate de
 * diff do CI que apanha uma divergência — não este ficheiro.
 *
 * Convenções que vêm do domínio e não da UI:
 *  - quantidades e dinheiro são **strings** (`Decimal` no Django, para não
 *    perder precisão em JSON). Nenhuma conta é feita em `number` no cliente;
 *  - o ledger guarda sempre a **unidade base** do artigo (g, ml, un), e o
 *    servidor manda também a forma de mostrar. Converter g para kg no cliente
 *    é a fonte nº 1 de bugs de stock (`inventory-domain` §2);
 *  - um movimento é append-only: há schema para o criar e nenhum para o
 *    alterar ou apagar, o que espelha o `REVOKE UPDATE, DELETE` do ADR 0006.
 */

/**
 * `"-2000.000"` — o que o DRF serializa a partir de um `DecimalField`.
 *
 * Escrito como duas alternativas e não como `^-?\d+(?:\.\d+)?$`: a forma curta
 * tem altura de estrela 2 (um `+` dentro de um grupo opcional) e o
 * `security/detect-unsafe-regex` recusa-a. Aqui cada alternativa tem um só
 * quantificador, diz exactamente o mesmo, e a casa não suprime lint.
 */
const decimal = z.string().regex(/^-?\d+$|^-?\d+\.\d+$/, "decimal inválido");

/** A unidade base de stock do artigo. É nesta unidade que o ledger guarda. */
export const unidadeBaseSchema = z.enum(["g", "ml", "un"]);

/**
 * Uma quantidade, nas duas formas: a do ledger e a de mostrar.
 *
 * O `display` existe porque o staff diz "3,4 kg" e o ledger guarda
 * "3400.000 g". A conversão é do servidor (o artigo sabe a sua unidade de
 * apresentação); o cliente só escolhe o formatador. Sem este campo, ou o ecrã
 * mostra `3400,000 g` — ilegível em pé, com pressa — ou o cliente divide por
 * 1000, que é exactamente a conversão que o domínio proíbe no frontend.
 */
export const quantidadeSchema = z.object({
  base: decimal,
  base_unit: unidadeBaseSchema,
  display: decimal,
  display_unit: z.string().min(1),
});

/**
 * Os dois rótulos que a lei distingue, e que o guião da sessão 0 nomeia como
 * condição para o dono confiar nos alertas: `use_by` é limite legal
 * ("consumir até"), `best_before` é qualidade ("consumir de preferência antes
 * de"). Tratar os dois igual é perder a credibilidade na primeira amêndoa
 * laminada marcada a vermelho.
 */
export const tipoValidadeSchema = z.enum(["use_by", "best_before"]);

/**
 * O estado da linha, **decidido no servidor**. O cliente não recalcula: se o
 * limiar de "baixo" mudar, muda num sítio, e a UI não ganha uma segunda
 * definição de "em falta" que divirja da dos alertas.
 */
export const estadoNivelSchema = z.enum(["ok", "baixo", "esgotado", "negativo"]);

/** Tipos de movimento do ledger (`inventory-domain` §1). */
/**
 * Os nove tipos de movimento do ledger (ADR 0014).
 *
 * `production_out` e `production_in` entraram a 2026-10-06 e o argumento foi de
 * **oportunidade**: hoje são dois valores num `z.enum` e duas linhas de
 * vocabulário, porque o `inventory_stockmovement` ainda não existe. Depois de
 * haver migração aplicada — que o CLAUDE.md proíbe editar — são uma migração
 * nova *e* o reetiquetar de linhas mal classificadas num ledger append-only,
 * onde uma linha errada não se corrige: corrige-se com outra linha.
 *
 * O que elas resolvem é uma **dupla contagem que já existia**: fazer pastéis sai
 * como `consumption` dos ingredientes e entrava como `receipt` — o tipo das
 * compras a fornecedores — e vender o pastel é outro `consumption`. Somar as
 * saídas de stock contava o custo dos ingredientes **e** o do produto acabado.
 * Numa pastelaria isso não é caso limite: é o fluxo de todos os dias.
 *
 * A forma é a do par `transfer_*` que já existia, e a simetria não é estética:
 * numa transferência o valor não sai do negócio e muda de **sítio**; numa
 * produção não sai e muda de **forma**. Os dois são pares de pernas que se
 * anulam no total do tenant e **não são eventos económicos** — a ADR 0014 tem a
 * tabela de nove linhas que diz, por tipo, o que entra em "mercadoria consumida"
 * e o que entra em "compras", e é essa tabela que impede cada agregação futura de
 * inventar a sua própria lista de exclusões.
 *
 * Um tipo e não uma `reference` excluída pela agregação: um `reference` é filtro
 * por convenção, e esquecê-lo devolve um número errado em silêncio. Uma união
 * fechada chega ao `Record` do frontend e um ramo esquecido **não compila**.
 */
export const tipoMovimentoSchema = z.enum([
  "receipt",
  "consumption",
  "waste",
  "adjustment",
  "transfer_out",
  "transfer_in",
  "return",
  "production_out",
  "production_in",
]);

/** Motivo obrigatório de um `waste` (`inventory-domain` §8). */
export const motivoQuebraSchema = z.enum(["expired", "spoiled", "prep_loss", "breakage", "other"]);

export const localizacaoSchema = z.object({
  id: z.uuid(),
  name: z.string().min(1),
});

/** A validade mais próxima do artigo, com o lote que a traz. */
export const validadeProximaSchema = z.object({
  lot_code: z.string().min(1),
  expires_at: z.iso.date(),
  /** Dias até à validade; negativo se já passou. Contado pelo servidor. */
  days_away: z.number().int(),
  kind: tipoValidadeSchema,
});

/** Quanto deste artigo está em cada localização — o probe da Q2 do guião. */
export const nivelPorLocalizacaoSchema = z.object({
  location: localizacaoSchema,
  quantity: quantidadeSchema,
});

/**
 * Uma linha do ecrã Stock: um artigo, agregado sobre as localizações.
 *
 * Nota para quem escrever o serializer: a projeção `StockLevel` do domínio é
 * produto × localização × lote. Esta é a **leitura agregada por artigo** que o
 * ecrã pede, com as linhas cruas em `by_location`. É um selector, não a
 * tabela — e a ordem vem do servidor ("o que está pior primeiro", guião §1),
 * porque uma segunda definição de "pior" no cliente divergiria da dos alertas.
 */
export const nivelDeStockSchema = z.object({
  product: z.uuid(),
  short_name: z.string().min(1),
  quantity: quantidadeSchema,
  min_quantity: quantidadeSchema,
  status: estadoNivelSchema,
  nearest_expiry: validadeProximaSchema.nullable(),
  by_location: z.array(nivelPorLocalizacaoSchema),
});

/**
 * Os três números do topo. Vêm do servidor porque são a mesma verdade que
 * alimenta os alertas — e o `expiring_within_days` viaja com o número para o
 * ecrã poder mostrar o limiar em vez de o esconder num painel de
 * configurações (guião §4, proibição 7).
 */
export const resumoDeStockSchema = z.object({
  below_min_count: z.number().int().nonnegative(),
  expiring_count: z.number().int().nonnegative(),
  expiring_within_days: z.number().int().positive(),
  stock_value_eur: decimal,
});

/** Uma linha do ledger. Tem autor sempre — o probe da Q7 do guião. */
export const movimentoSchema = z.object({
  id: z.uuid(),
  movement_type: tipoMovimentoSchema,
  /** Sinal pelo tipo: entradas positivas, saídas negativas. */
  quantity: quantidadeSchema,
  location: localizacaoSchema,
  lot_code: z.string().nullable(),
  /* O vazio é o "sem motivo" do servidor desde 2026-10-19: as colunas de texto
   * do ledger deixaram de aceitar `NULL` (convenção do Django — um valor só
   * para "nada"), e um `z.enum()` recusa `""`. O `null` fica aceite porque as
   * linhas antigas e os fixtures ainda o usam; ambos chegam aqui como `null`,
   * que é o que o ecrã já sabe desenhar. */
  reason: motivoQuebraSchema
    .or(z.literal(""))
    .nullable()
    .transform((valor) => (valor === "" ? null : valor)),
  created_by: z.string().min(1),
/* `{ offset: true }` e não `z.iso.datetime()` nu, e isto esteve 11 dias a ser uma
 * bomba de relógio invisível. O Django corre com `TIME_ZONE = "Europe/Lisbon"` e
 * o DRF serializa `2026-10-13T11:08:06.340331+01:00`; o `z.iso.datetime()` do
 * Zod 4 **só aceita `Z`**. Medido: o formato real falha, o dos fixtures passa.
 *
 * Porque não se notou, e é a lição que importa: o servidor de fixtures usa
 * `toISOString()`, que devolve sempre `Z`. E ele valida as respostas com **este
 * mesmo schema** — o que a ADR 0008 decisão 3 celebra como "um fixture que não
 * poderia sair do endpoint real falha alto". Esse mecanismo apanha um schema
 * **demasiado largo**; não pode apanhar um schema **demasiado estreito**, porque
 * o fixture é escrito para o satisfazer. Os dados falsos eram mais complacentes
 * do que a realidade, e no dia em que estes endpoints existissem cada resposta
 * virava um erro de forma com uma mensagem que não aponta para o fuso horário. */
  occurred_at: z.iso.datetime({ offset: true }),
  /** Referência: fatura, contagem, transferência. Texto curto, para mostrar. */
  /** Referência: fatura, contagem, transferência. Texto curto, para mostrar.
   * `z.string()` já aceita o `""` que o servidor passou a enviar em vez de
   * `NULL` (2026-10-19); o `null` fica para as linhas antigas e os fixtures. */
  reference: z.string().nullable(),
});

/**
 * O corpo de um `POST /stock/movements`. Só cria; não há schema para editar
 * nem para apagar, e é de propósito (ADR 0006: `inventory_stockmovement` é
 * append-only na própria base de dados).
 *
 * A quantidade é o **valor absoluto**, na unidade base, e o sinal vem do tipo
 * — quem escreve "2000" numa quebra não tem de saber que o ledger guarda
 * "-2000".
 */
export const quebraParaRegistarSchema = z.object({
  product: z.uuid(),
  location: z.uuid(),
  quantity: decimal,
  reason: motivoQuebraSchema,
  /**
   * O lote de onde sai, quando quem regista já o sabe — é o caso do ecrã
   * Alertas, onde o alerta **é** sobre um lote ("L. 240928 · amanhã") e deitar
   * fora outro seria deitar fora o lote errado. Omitido, o servidor escolhe por
   * FEFO (`inventory-domain` §4), que é o que o ecrã de Stock faz: lá a ação
   * parte do artigo e não de um lote.
   */
  lot_code: z.string().min(1).optional(),
});

/* ---------------------------------------------------------------------------
 * Contagem física — o ecrã Contar.
 *
 * Uma contagem **não reescreve um nível**: ao fechar, cada diferença entra no
 * ledger como um `adjustment` com justificação. É por isso que há aqui um
 * campo numérico (o `counted` da linha) sem contradizer o "nenhum campo de
 * quantidade editável": o que se escreve é o que está na prateleira, e o que o
 * sistema diz continua a mudar só por movimento (ADR 0006, append-only).
 * ------------------------------------------------------------------------- */

/**
 * Uma zona física **dentro** de uma localização: Balcão, Frigorífico, Arca,
 * Armazém. Não é a loja (`localizacaoSchema`) — é a prateleira por onde se
 * anda, e a `position` é a ordem do percurso. "Ordem por localização física …
 * é regra, não preferência" (guião da sessão 0, §1): quem conta atravessa a
 * cozinha, não o alfabeto.
 *
 * O `blind` é a sonda da contagem cega. Numa zona cega o `expected` da linha
 * **não viaja na resposta**: esconder no cliente um número que o servidor
 * mandou não é contagem cega, é um número à distância de um devtools — e a
 * ancoragem que se queria evitar continuava a acontecer, só que no código.
 */
export const zonaSchema = z.object({
  slug: z.string().min(1),
  name: z.string().min(1),
  position: z.number().int().nonnegative(),
  blind: z.boolean(),
});

/** A mesma zona com o progresso. Vive na contagem, não repetida em cada linha. */
export const progressoDeZonaSchema = zonaSchema.extend({
  counted_lines: z.number().int().nonnegative(),
  total_lines: z.number().int().nonnegative(),
});

export const estadoDeContagemSchema = z.enum(["open", "closed"]);

export const contagemSchema = z.object({
  id: z.uuid(),
  location: localizacaoSchema,
  status: estadoDeContagemSchema,
  started_at: z.iso.datetime({ offset: true }),
  closed_at: z.iso.datetime({ offset: true }).nullable(),
  /** O "12 de 34" do topo. Contado pelo servidor, como todo o resto. */
  counted_lines: z.number().int().nonnegative(),
  total_lines: z.number().int().nonnegative(),
  /**
   * A zona onde a contagem está: a primeira, na ordem do percurso, que ainda
   * tem linhas por contar. `null` quando está tudo contado.
   */
  current_zone: progressoDeZonaSchema.nullable(),
  zones: z.array(progressoDeZonaSchema),
  /**
   * Quem pode fechar, em texto — a sonda da Q7 ("uma ação visivelmente
   * restrita"). É um **rótulo**, não uma permissão: o shell não bloqueia nada
   * (guião §4, proibição 3), mostra a quem a ação pertence e observa-se se o
   * dono acha que a Ana a podia fazer.
   */
  closing_role: z.string().min(1),
  /** A justificação com que foi fechada, quando já foi. */
  closing_reason: z.string().nullable(),
});

/**
 * Uma linha de contagem: um artigo numa zona.
 *
 * `count_unit` é a unidade em que **ele** conta (kg na balança, un à mão), e é
 * nessa unidade que o campo aceita o número e que o `counted` volta. A
 * conversão para a unidade base é do servidor — converter unidades no cliente é
 * a fonte nº 1 de bugs de stock (`inventory-domain` §2).
 */
export const linhaDeContagemSchema = z.object({
  id: z.uuid(),
  product: z.uuid(),
  short_name: z.string().min(1),
  zone: zonaSchema,
  /** A ordem do percurso dentro da zona. Nunca alfabética. */
  position: z.number().int().nonnegative(),
  count_unit: z.string().min(1),
  /** O que o sistema diz. `null` numa zona cega, e aí é ausência real. */
  expected: quantidadeSchema.nullable(),
  /** O que foi contado. `null` = por contar. */
  counted: quantidadeSchema.nullable(),
  /** `counted − expected`. `null` enquanto faltar um dos dois. */
  difference: quantidadeSchema.nullable(),
  /** A mesma diferença em euros, com sinal. Arredondada ao cêntimo pelo CMP. */
  difference_eur: decimal.nullable(),
  counted_by: z.string().nullable(),
  counted_at: z.iso.datetime({ offset: true }).nullable(),
});

/**
 * O corpo de `POST /stock/counts/<id>/lines`: a quantidade contada de um
 * artigo, **na unidade de contagem da linha**.
 *
 * É um POST na coleção e não um PATCH na linha porque contar é registar uma
 * observação nova — a última substitui a anterior, e não há id de linha para
 * quem está a andar pela cozinha com o telemóvel a saber.
 */
export const contagemDeLinhaSchema = z.object({
  product: z.uuid(),
  quantity: decimal,
});

/** O corpo de `POST /stock/counts`: contar é sempre contar **uma** localização. */
export const contagemParaIniciarSchema = z.object({
  location: z.uuid(),
});

/**
 * O fecho da contagem: as diferenças em quantidade **e em euros**, e o limiar
 * acima do qual a justificação é obrigatória.
 *
 * O limiar vem no payload para o ecrã o poder **mostrar** ("diferenças de 15 €
 * — motivo obrigatório acima de 5 €"), que é a alternativa ao painel de
 * configurações que o guião §4 nº 7 proíbe.
 */
export const fechoDeContagemSchema = z.object({
  count: z.uuid(),
  status: estadoDeContagemSchema,
  counted_lines: z.number().int().nonnegative(),
  total_lines: z.number().int().nonnegative(),
  /** Só as linhas com diferença, a maior em euros primeiro. */
  differences: z.array(linhaDeContagemSchema),
  /** Perda e ganho separados, os dois positivos. */
  loss_eur: decimal,
  gain_eur: decimal,
  /** `gain − loss`. Com sinal. */
  net_eur: decimal,
  /** `loss + gain` comparado com este valor decide se o motivo é obrigatório. */
  reason_required_above_eur: decimal,
  reason_required: z.boolean(),
  closing_role: z.string().min(1),
  closing_reason: z.string().nullable(),
});

/**
 * O corpo de `POST /stock/counts/<id>/closing`. A justificação é texto livre —
 * uma contagem não cai nos cinco motivos de um desperdício, e a razão de uma
 * diferença é quase sempre uma frase ("faltou lançar a transferência").
 *
 * Opcional no contrato, obrigatório acima do limiar: é o servidor que recusa,
 * não o botão que se desativa. Fechar uma contagem com diferenças tem de ser
 * possível (guião §4, proibição 3).
 */
export const fechoParaRegistarSchema = z.object({
  reason: z.string().trim().min(1).max(200).optional(),
});

/* ---------------------------------------------------------------------------
 * Alertas — "o que expira? o que falta? quanto deitei fora?"
 * ------------------------------------------------------------------------- */

/** Porque é que esta linha está na lista. Três perguntas, uma lista. */
export const motivoDeAlertaSchema = z.enum(["expiry", "missing"]);

/**
 * A gravidade, **decidida no servidor**, e com um tecto: um `best_before`
 * nunca sai `danger`. É a regra que o ecrã de Stock já estabeleceu ("expira"
 * contra "perde qualidade") levada ao contrato, para a amêndoa laminada não
 * poder aparecer a vermelho por distração de um ecrã.
 */
export const gravidadeSchema = z.enum(["danger", "warning", "info"]);

export const alertaSchema = z.object({
  id: z.uuid(),
  product: z.uuid(),
  short_name: z.string().min(1),
  reason: motivoDeAlertaSchema,
  severity: gravidadeSchema,
  /**
   * Onde está. `null` num alerta de falta: o mínimo é do artigo e vale sobre o
   * consolidado, logo não há uma localização a apontar.
   */
  location: localizacaoSchema.nullable(),
  /** O que está em risco (o lote) ou o que resta (a falta). */
  quantity: quantidadeSchema,
  value_eur: decimal,
  /** O lote em risco, com a distinção `use_by`/`best_before`. */
  lot: validadeProximaSchema.nullable(),
  /** O limiar de dias que fez este alerta aparecer. `null` numa falta. */
  threshold_days: z.number().int().positive().nullable(),
  /** O mínimo que fez este alerta aparecer. `null` numa validade. */
  min_quantity: quantidadeSchema.nullable(),
});

/**
 * Os três contadores do topo.
 *
 * O `business_day_starts_at` e o `wasted_since` são a sonda da Q6: o rótulo lê
 * "Deitado fora — hoje (desde as 04:00)" e a fronteira do dia é **dado do
 * servidor**, por estabelecimento. Na pastelaria o dia começa no início da
 * produção (~4h) e não no fim do serviço (~2h) de um restaurante — e a resposta
 * pode ser diferente por tipo de negócio, o que é em si um achado.
 */
export const resumoDeAlertasSchema = z.object({
  expiring_count: z.number().int().nonnegative(),
  expiring_within_days: z.number().int().positive(),
  missing_count: z.number().int().nonnegative(),
  /** Desde o início do dia de negócio. */
  wasted_today_eur: decimal,
  /** Os últimos sete dias de negócio. */
  wasted_week_eur: decimal,
  /** `"04:00"`, hora local do estabelecimento. */
  business_day_starts_at: z.string().regex(/^\d\d:\d\d$/, "hora inválida"),
  wasted_since: z.iso.datetime({ offset: true }),
});

/**
 * Uma linha de desperdício — a vista do ledger que responde à terceira
 * pergunta. É só leitura: um movimento não se edita nem se apaga (ADR 0006),
 * e aqui não há ação nenhuma na linha de propósito.
 */
export const desperdicioSchema = z.object({
  id: z.uuid(),
  product: z.uuid(),
  short_name: z.string().min(1),
  lot_code: z.string().nullable(),
  /** Positiva: o que saiu. O sinal do ledger já foi lido pelo servidor. */
  quantity: quantidadeSchema,
  value_eur: decimal,
  reason: motivoQuebraSchema,
  location: localizacaoSchema,
  created_by: z.string().min(1),
  occurred_at: z.iso.datetime({ offset: true }),
});

export type UnidadeBase = z.output<typeof unidadeBaseSchema>;
export type Quantidade = z.output<typeof quantidadeSchema>;
export type TipoValidade = z.output<typeof tipoValidadeSchema>;
export type EstadoNivel = z.output<typeof estadoNivelSchema>;
export type TipoMovimento = z.output<typeof tipoMovimentoSchema>;
export type MotivoQuebra = z.output<typeof motivoQuebraSchema>;
export type Localizacao = z.output<typeof localizacaoSchema>;
export type ValidadeProxima = z.output<typeof validadeProximaSchema>;
export type NivelPorLocalizacao = z.output<typeof nivelPorLocalizacaoSchema>;
export type NivelDeStock = z.output<typeof nivelDeStockSchema>;
export type ResumoDeStock = z.output<typeof resumoDeStockSchema>;
export type Movimento = z.output<typeof movimentoSchema>;
export type QuebraParaRegistar = z.output<typeof quebraParaRegistarSchema>;
export type Zona = z.output<typeof zonaSchema>;
export type ProgressoDeZona = z.output<typeof progressoDeZonaSchema>;
export type EstadoDeContagem = z.output<typeof estadoDeContagemSchema>;
export type Contagem = z.output<typeof contagemSchema>;
export type LinhaDeContagem = z.output<typeof linhaDeContagemSchema>;
export type ContagemDeLinha = z.output<typeof contagemDeLinhaSchema>;
export type ContagemParaIniciar = z.output<typeof contagemParaIniciarSchema>;
export type FechoDeContagem = z.output<typeof fechoDeContagemSchema>;
export type FechoParaRegistar = z.output<typeof fechoParaRegistarSchema>;
export type MotivoDeAlerta = z.output<typeof motivoDeAlertaSchema>;
export type Gravidade = z.output<typeof gravidadeSchema>;
export type Alerta = z.output<typeof alertaSchema>;
export type ResumoDeAlertas = z.output<typeof resumoDeAlertasSchema>;
export type Desperdicio = z.output<typeof desperdicioSchema>;
