import { z } from "zod";

/**
 * O contrato do módulo `inventory`, em Zod.
 *
 * Estes schemas são **escritos à mão** e não se geram do `types.ts` (CLAUDE.md).
 * Desde que o Django serve estes sete recursos (ADR 0034) deixou de haver um
 * servidor de dados falsos a validar-se com o mesmo ficheiro, e com ele saiu a
 * última rede: **nenhum gate atravessa esta fronteira**. Um campo que passe a
 * opcional no contrato tem de ganhar `.optional()` aqui — um `.nullable()`
 * sozinho continua a exigir a chave presente, e o ecrã **rebenta** no `parse`
 * com o `pnpm typecheck` verde. O que apanha isso é fotografar o ecrã
 * autenticado **com cada papel**, porque é por papel que as chaves desaparecem.
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
 * A gravidade, **decidida no servidor** desde a ADR 0034 (decisão 9), e com um
 * tecto que é legal e não de paleta: um `best_before` nunca sai `danger`, porque
 * um DDM passado ainda é mercadoria vendável (DL 26/2016).
 *
 * Vive aqui, acima da validade, e não na secção dos alertas onde nasceu: desde
 * que o `nearest_expiry` traz `severity`, ela é um campo **da validade** e o
 * alerta herda-a. Um `const` lê-se por ordem — declará-la depois punha o
 * `validadeProximaSchema` a ler uma variável ainda na zona morta.
 */
export const gravidadeSchema = z.enum(["danger", "warning", "info"]);

/**
 * O que se sabe sobre o custo de uma linha, nas três palavras da ADR 0032:
 * `conhecido` (há preço), `estimado` (há um palpite) e `desconhecido` (não há).
 *
 * É **qualidade de dados e não um euro**, logo chega aos três papéis — é a
 * palavra que impede um `unit_cost` ausente de se ler como "custou zero".
 */
export const estadoDoCustoSchema = z.enum(["conhecido", "estimado", "desconhecido"]);

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

/**
 * A validade mais próxima do artigo, com o lote que a traz.
 *
 * ## Três campos que mudaram com a ADR 0034, e dois deles rebentavam a página
 *
 * `lot_id` entrou porque o `POST` de quebra passou a aceitar **a chave** do lote
 * e não o código: um código não é chave e obrigava o servidor a resolvê-lo.
 *
 * `severity` entrou porque era a **quarta** definição de gravidade da casa — e a
 * única que o utilizador via, porque decidia a cor do trilho. O cliente mantém a
 * palavra (é i18n e é dele) e tira daqui a cor e a urgência; a tabela da decisão
 * 9 vive no servidor, numa função só, chamada pelas duas portas.
 *
 * `lot_code` e `kind` passaram a **nuláveis**, e cada um tem um caso real: um
 * lote sintético (o que a produção de uma receita cria) não tem código, e o
 * `expiry_kind` do catálogo é `""` por omissão — o serializer traduz `""` para
 * `null`, porque o `tipoValidadeSchema` não aceita a string vazia. Sem estes
 * dois `.nullable()` a primeira produção de receita rebentava o ecrã de Alertas
 * com o `pnpm typecheck` verde.
 */
export const validadeProximaSchema = z.object({
  /** A chave do lote. É ela que viaja no corpo da quebra, nunca o código. */
  lot_id: z.uuid(),
  /** `null` num lote sintético — quem o mostra diz "sem lote". */
  lot_code: z.string().nullable(),
  expires_at: z.iso.date(),
  /** Dias até à validade; negativo se já passou. Contado pelo servidor. */
  days_away: z.number().int(),
  /** `null` num artigo sem rótulo de validade (o `""` do catálogo). */
  kind: tipoValidadeSchema.nullable(),
  /** A gravidade desta validade. A **cor** do ecrã sai daqui, não de uma conta. */
  severity: gravidadeSchema,
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
  /**
   * **Do artigo, logo do estabelecimento inteiro — também com `?loja=`.** O
   * mínimo é por artigo (ADR 0024) e compará-lo contra o saldo de uma loja
   * inventava faltas, pelo que o `?loja=` escopa só `quantity`, `by_location`,
   * `nearest_expiry` e o valor. O ecrã **tem** de o dizer: "0,4 kg · ok" ao lado
   * de "mínimo 3 kg" lê-se como erro de cálculo quando não se sabe que o mínimo
   * é das três lojas somadas (ADR 0034, adenda).
   */
  min_quantity: quantidadeSchema,
  status: estadoNivelSchema,
  nearest_expiry: validadeProximaSchema.nullable(),
  by_location: z.array(nivelPorLocalizacaoSchema),
  /**
   * Quanta desta quantidade está em níveis **sem preço registado**. Zero é
   * cobertura total; igual ao `quantity` é não haver preço nenhum.
   *
   * É quantidade e não euro, logo chega aos três papéis: é o que diz se o valor
   * está subestimado em 5 % ou em 95 % (a régua da ADR 0032).
   */
  quantity_without_cost: quantidadeSchema,
  /**
   * ## Dois `.optional()` que não são opcionais
   *
   * `unit_cost` e `total_value` só vão a `owner|manager`, e vão **os dois
   * juntos** — um reconstrói o outro com a quantidade que já está no payload,
   * logo esconder um só era teatro. A chave fica **ausente** para o `staff`
   * (ADR 0032, decisão 1): nunca `0`, que é uma afirmação falsa sobre o preço,
   * nunca `null`, que o ecrã imprime como "—".
   *
   * O `.optional()` está aqui porque sem ele o Zod exigia a chave e o ecrã de
   * Stock **rebentava** no `parse` para quem não vê euros — com o `pnpm
   * typecheck` verde, porque nenhum gate atravessa esta fronteira.
   *
   * O `.nullable()` do `unit_cost` é outro facto e por isso fica: `null` é
   * "nenhuma parte desta quantidade tem preço", e vale para quem vê euros.
   */
  unit_cost: decimal.nullable().optional(),
  total_value: decimal.optional(),
});

/**
 * Os três números do topo. Vêm do servidor porque são a mesma verdade que
 * alimenta os alertas — e o `expiring_within_days` viaja com o número para o
 * ecrã poder mostrar o limiar em vez de o esconder num painel de
 * configurações (guião §4, proibição 7).
 */
export const resumoDeStockSchema = z.object({
  below_min_count: z.number().int().nonnegative(),
  /** Conta **artigos**. O do `/stock/alerts/summary` conta linhas da lista. */
  expiring_count: z.number().int().nonnegative(),
  expiring_within_days: z.number().int().positive(),
  /**
   * Σ do valor dos artigos com saldo positivo — um saldo negativo não baixa o
   * valor do stock. **Ausente** para quem não vê euros, e daí o `.optional()`:
   * sem ele o ecrã de Stock rebentava para o `staff`. Com a chave ausente
   * desaparece o **campo inteiro** da régua, que é a leitura certa de "não te
   * compete" — um traço no lugar seria uma afirmação sobre o stock.
   */
  stock_value_eur: decimal.optional(),
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
  /**
   * O `display_name` da pertença, **nunca o email**, e `null` quando quem agiu
   * já não tem nome aqui (a conta saiu do estabelecimento). Era `.min(1)` e uma
   * linha dessas rebentava a tabela do artigo inteira.
   */
  created_by: z.string().nullable(),
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
  /**
   * A referência **crua**, e o ecrã não a imprime.
   *
   * Num ajuste de fecho de contagem ela é o `id` da contagem em texto, e o ecrã
   * dizia "texto curto, para mostrar" — imprimia um uuid. Não se muda o que se
   * grava (há um índice parcial e dois lookups por esta string), logo o
   * servidor serve o par abaixo e o cliente imprime **o rótulo**.
   */
  reference: z.string().nullable(),
  /** `"contagem"`, ou `null` no que vem de fora deste módulo. */
  reference_kind: z.string().nullable(),
  /** `"Contagem de 24/10, Armazém"`. `null` = o ecrã não escreve nada. */
  reference_label: z.string().nullable(),
  /** Qualidade de dados, não euro: chega aos três papéis. */
  cost_status: estadoDoCustoSchema,
  /**
   * O custo unitário desta linha. **Ausente** para quem não vê euros (daí o
   * `.optional()`), e `null` quando é desconhecido — zero não é um preço de
   * zero euros, e é a `cost_status` que diz qual dos dois casos é.
   */
  unit_cost: decimal.nullable().optional(),
});

/**
 * O corpo de um `POST /stock/movements/waste`. Só cria; não há schema para
 * editar nem para apagar, e é de propósito (ADR 0006:
 * `inventory_stockmovement` é append-only na própria base de dados).
 *
 * A quantidade é o **valor absoluto** e o sinal vem do tipo — quem escreve "2"
 * numa quebra não tem de saber que o ledger guarda "-2000".
 */
export const quebraParaRegistarSchema = z.object({
  product: z.uuid(),
  location: z.uuid(),
  quantity: decimal,
  /**
   * A unidade em que o número acima está escrito, e é **obrigatória**.
   *
   * Tem de ser o `base_unit` ou o `display_unit` **daquele artigo**; qualquer
   * outra é 400, porque não existe motor genérico de conversão (ADR 0011). A
   * conversão é do servidor, nunca do cliente (`inventory-domain` §2).
   *
   * Entrou com a ADR 0034 (decisão 11) e fechou um buraco medido: o corpo dizia
   * "unidade BASE" contra um formulário que mostra a unidade de apresentação ao
   * lado do campo. Entre `g` e `kg` há um factor de 1000, às 6 da manhã quem
   * deita fora dois pães escreve `2`, e o destino é um ledger sem desfazer.
   */
  unit: z.string().min(1),
  reason: motivoQuebraSchema,
  /**
   * O lote de onde sai, **pela chave**, quando quem regista já o sabe — é o
   * caso do ecrã Alertas, onde o alerta **é** sobre um lote e deitar fora outro
   * seria deitar fora o lote errado. Era `lot_code` e passou a `lot`: um código
   * não é chave e obrigava o servidor a resolvê-lo.
   *
   * Omitido, o servidor escolhe por FEFO **na localização pedida** e reparte
   * por quantos lotes forem precisos — que é o que o ecrã do artigo faz, porque
   * lá a acção parte do artigo e não de um lote.
   */
  lot: z.uuid().optional(),
});

/**
 * O 201 da quebra: **sempre uma lista**, mesmo com um lote só.
 *
 * Uma quebra de 2 kg com o lote FEFO a 0,4 kg reparte-se por vários lotes (ADR
 * 0034, decisão 8), e uma resposta que fosse objecto no caso normal e lista no
 * caso raro era um cliente que funciona até ao dia em que o lote acaba a meio.
 * É a forma que o 201 da transferência já tem.
 */
export const respostaDeQuebraSchema = z.object({
  movements: z.array(movimentoSchema),
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
 * Uma zona da contagem — e **nesta fatia a zona é a localização** (ADR 0030,
 * decisão 3, confirmada pelo dono: "contei a câmara fria" é uma contagem da
 * câmara fria).
 *
 * O schema não muda de forma e passa a ter uma fonte: o `slug` é o do nome da
 * localização, o `name` é o nome dela e a `position` é `0`, porque **há uma
 * zona por contagem**. Zonas como entidade própria — tabela, ordem do percurso,
 * atribuição artigo→zona — ficaram fora de âmbito por extenso, e até lá o que
 * organiza o stock são as localizações que já existem.
 *
 * O `blind` chega sempre a `false` e isso é **facto e não marcador de lugar**:
 * a contagem cega não existe nesta fatia, logo o `expected` viaja sempre. Fica
 * no contrato porque é o servidor que o afirma — no dia em que o dono a
 * escolher, muda lá e o `expected` deixa de viajar.
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
  /**
   * A mesma diferença em euros, com sinal, arredondada ao cêntimo pelo CMP — e
   * **ausente para quem não vê euros** (ADR 0032, decisão 5).
   *
   * ## Um `.optional()` que não é opcional
   *
   * A chave só falta por **papel**, nunca por acaso: para `owner|manager` vem
   * sempre. O `.optional()` está aqui porque sem ele o Zod exigia a chave e o
   * ecrã de contagens não degradava para o colaborador — **rebentava** no
   * `parse`, que é o defeito exacto que a adenda da ADR 0031 descreve.
   *
   * O `.nullable()` fica, e não é redundante: `null` continua a querer dizer
   * "ainda não contado", que é o seu único significado desde que a ausência
   * passou a dizer o outro. A ADR 0030 tinha nomeado o preço de os juntar.
   *
   * Quem lê isto trata os dois casos como um só — não há número — e **nunca
   * desenha um traço** no lugar do dinheiro: para quem não o vê, a coluna não
   * existe.
   */
  difference_eur: decimal.nullable().optional(),
  /**
   * Quem contou e quando — uma **cópia do nome** da pertença, como no ledger,
   * para sobreviver à conta ser apagada.
   *
   * Não é cromado: nada impede duas pessoas de contarem a mesma localização ao
   * mesmo tempo em dois telemóveis, e **a última a escrever ganha** (o
   * `POST` é um upsert por artigo). Quem recontar tem de ver que já ali esteve
   * alguém, e a resposta a "o João já contou isto?" é esta linha e não uma soma
   * — somar duas observações da mesma prateleira é contar a mesma farinha duas
   * vezes.
   */
  counted_by: z.string().nullable(),
  counted_at: z.iso.datetime({ offset: true }).nullable(),
});

/**
 * O corpo de `POST /stock/counts/<id>/lines`: a quantidade contada de um
 * artigo, **na unidade de contagem da linha** (o `count_unit`, que é o rótulo
 * que está ao lado do campo). Quem conta escreve o que lê no rótulo; a
 * conversão para a unidade do ledger é do servidor, que é onde o
 * `inventory-domain` §2 a põe.
 *
 * É um POST na coleção e não um PATCH na linha porque contar é registar uma
 * observação nova — a última substitui a anterior, e não há id de linha para
 * quem está a andar pela cozinha com o telemóvel a saber. O upsert por
 * `(contagem, artigo)` dá **idempotência de graça**: repetir o mesmo pedido
 * depois de um timeout não conta duas vezes, que é o modo de falha real de
 * contar em pé com rede fraca.
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
 * As linhas que ficam **por contar**: quantas e quais.
 *
 * Existe para o botão poder dizer "Fechar com 3 por contar" em vez de se
 * desligar: fechar uma contagem imperfeita tem de ser possível, senão quem
 * conta inventa números para o botão acender (guião §4, proibição 3). E os
 * nomes vêm com o número porque "3 por contar" não diz se faltou a farinha ou
 * as saquetas de açúcar — e só uma dessas duas faz alguém voltar ao armazém.
 *
 * Uma linha nunca contada **não gera movimento**: ausência de observação não é
 * diferença de zero, e o stock dela fica exactamente como está.
 */
export const porContarSchema = z.object({
  count: z.number().int().nonnegative(),
  names: z.array(z.string()),
});

/**
 * O fecho da contagem: as diferenças em quantidade **e em euros**, o que fica
 * por contar, e a justificação.
 *
 * **A justificação é sempre obrigatória, sem limiar** (ADR 0030, segunda ronda
 * de respostas do dono, nº 5): o limiar de 50 € era uma hipótese por calibrar e
 * o dono preferiu a disciplina de uma frase em todas as contagens. O
 * `reason_required_above_eur` continua a viajar — vale zero — porque é o número
 * que se muda se ele voltar atrás; o ecrã não o mostra, porque "obrigatório
 * acima de 0 €" é uma frase que não informa ninguém.
 *
 * Este corpo é o **mesmo** no `GET` (pré-visualização, que não escreve nada) e
 * no `POST` (que escreve), com o `status` a dizer qual dos dois se está a ler.
 * O `GET` é de `owner|manager` e responde **403** a quem conta.
 */
export const fechoDeContagemSchema = z.object({
  count: z.uuid(),
  status: estadoDeContagemSchema,
  counted_lines: z.number().int().nonnegative(),
  total_lines: z.number().int().nonnegative(),
  /** Só as linhas com diferença, a maior em euros primeiro. */
  differences: z.array(linhaDeContagemSchema),
  /** O que fica de fora do ajuste, com nome. */
  uncounted_lines: porContarSchema,
  /** Perda e ganho separados, os dois positivos. */
  loss_eur: decimal,
  gain_eur: decimal,
  /** `gain − loss`. Com sinal. */
  net_eur: decimal,
  /** Zero desde a segunda ronda da ADR 0030. Fica por ser onde se volta atrás. */
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
 * **Obrigatória, e já não opcional.** Era `.optional()` enquanto o contrato
 * tinha um limiar em euros; a segunda ronda da ADR 0030 tirou o limiar e
 * deixou a regra sem excepção, e o servidor responde 400 por campo a um corpo
 * sem ela. Um `.optional()` aqui era o cliente a deixar sair um pedido que já
 * se sabe recusado — o ecrã pede a frase antes.
 *
 * O que isto **não** é: uma forma de impedir o fecho. Fechar com diferenças e
 * fechar sem ter contado tudo continuam os dois a ser possíveis (guião §4,
 * proibição 3). O que se exige é que alguém escreva porquê.
 */
export const fechoParaRegistarSchema = z.object({
  reason: z.string().trim().min(1).max(200),
});

/* ---------------------------------------------------------------------------
 * Alertas — "o que expira? o que falta? quanto deitei fora?"
 * ------------------------------------------------------------------------- */

/** Porque é que esta linha está na lista. Três perguntas, uma lista. */
export const motivoDeAlertaSchema = z.enum(["expiry", "missing"]);

/* A `gravidadeSchema` vive lá em cima, ao lado da validade: desde que o
 * `nearest_expiry` traz `severity`, ela é um campo da validade e o alerta
 * herda-a — num alerta de validade, o `severity` do alerta e o do lote são o
 * mesmo número pela mesma função do servidor. */

export const alertaSchema = z.object({
  /**
   * **Não é um uuid**: é `"expiry:<lot_id>:<location_id>"` ou
   * `"missing:<product_id>"`.
   *
   * A localização entra na chave porque um lote transferido tem saldo em duas
   * prateleiras, e `"expiry:<lot_id>"` produzia **dois ids iguais** — o painel
   * de motivos expandia a linha errada.
   */
  id: z.string().min(1),
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
  /**
   * Num alerta de validade é o valor em risco; num de falta é o que custa
   * voltar ao mínimo. **Ausente** para quem não vê euros — daí o `.optional()`,
   * sem o qual o ecrã de Alertas rebentava para o `staff` —, e com a chave
   * ausente desaparece a **coluna inteira**.
   */
  value_eur: decimal.optional(),
  /** Qualidade de dados, não euro: chega aos três papéis. */
  cost_status: estadoDoCustoSchema,
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
  /** Conta **linhas da lista** de validade. O do Stock conta artigos. */
  expiring_count: z.number().int().nonnegative(),
  expiring_within_days: z.number().int().positive(),
  missing_count: z.number().int().nonnegative(),
  /**
   * Desde o início do dia de negócio. **Ausente** para quem não vê euros.
   */
  wasted_today_eur: decimal.optional(),
  /** Os últimos sete dias de negócio. **Ausente** para quem não vê euros. */
  wasted_week_eur: decimal.optional(),
  /**
   * ## Quatro números **sem** `.optional()`, e é aqui que um a mais fazia mal
   *
   * As duas contagens de linhas e as duas de cobertura estão **presentes para
   * os três papéis** (ADR 0034, decisão 10). Um `COUNT(id)` não tem euros em
   * ponta nenhuma — não há numerador nem denominador —, logo nenhuma sequência
   * de observações reconstrói o custo unitário a partir delas.
   *
   * A razão de existirem é de **navegação**: os dois números em euros eram as
   * duas únicas portas para a lista de desperdício, e a decisão 4 diz que essa
   * lista tem de chegar ao `staff`. Sem contador, a rota existia sem ter quem
   * lá entrasse.
   *
   * E **sem `.optional()` de propósito**: aqui um `.optional()` a mais não
   * degradava nada — escondia um campo em falta, e o terceiro contador do
   * `staff` desaparecia em silêncio no dia em que o servidor o deixasse de
   * mandar.
   */
  wasted_today_count: z.number().int().nonnegative(),
  wasted_week_count: z.number().int().nonnegative(),
  /**
   * Quantas dessas linhas não têm preço conhecido. Linhas e não euros, como o
   * `quantity_without_cost` dos níveis: "7 quebras hoje" e "7 quebras hoje, 4
   * sem preço conhecido" não são a mesma frase.
   */
  wasted_today_lines_without_cost: z.number().int().nonnegative(),
  wasted_week_lines_without_cost: z.number().int().nonnegative(),
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
  /** `null` num lote sintético — quem o mostra não escreve nada. */
  lot_code: z.string().nullable(),
  /** Positiva: o que saiu. O sinal do ledger já foi lido pelo servidor. */
  quantity: quantidadeSchema,
  /** **Ausente** para quem não vê euros: com a chave fora, sai a coluna. */
  value_eur: decimal.optional(),
  /** Qualidade de dados, não euro: chega aos três papéis. */
  cost_status: estadoDoCustoSchema,
  /* O `""` é o "sem motivo" do servidor (as colunas de texto do ledger não
   * aceitam `NULL`), e um `z.enum()` recusa-o. Chega aqui como `null`, que é o
   * que a tabela já sabe desenhar — o mesmo tratamento do `movimentoSchema`. */
  reason: motivoQuebraSchema
    .or(z.literal(""))
    .nullable()
    .transform((valor) => (valor === "" ? null : valor)),
  location: localizacaoSchema,
  /** O `display_name` da pertença, `null` quando quem agiu já não tem nome. */
  created_by: z.string().nullable(),
  occurred_at: z.iso.datetime({ offset: true }),
});

export type UnidadeBase = z.output<typeof unidadeBaseSchema>;
export type Quantidade = z.output<typeof quantidadeSchema>;
export type TipoValidade = z.output<typeof tipoValidadeSchema>;
export type EstadoDoCusto = z.output<typeof estadoDoCustoSchema>;
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
export type RespostaDeQuebra = z.output<typeof respostaDeQuebraSchema>;
export type Zona = z.output<typeof zonaSchema>;
export type ProgressoDeZona = z.output<typeof progressoDeZonaSchema>;
export type EstadoDeContagem = z.output<typeof estadoDeContagemSchema>;
export type Contagem = z.output<typeof contagemSchema>;
export type LinhaDeContagem = z.output<typeof linhaDeContagemSchema>;
export type ContagemDeLinha = z.output<typeof contagemDeLinhaSchema>;
export type ContagemParaIniciar = z.output<typeof contagemParaIniciarSchema>;
export type PorContar = z.output<typeof porContarSchema>;
export type FechoDeContagem = z.output<typeof fechoDeContagemSchema>;
export type FechoParaRegistar = z.output<typeof fechoParaRegistarSchema>;
export type MotivoDeAlerta = z.output<typeof motivoDeAlertaSchema>;
export type Gravidade = z.output<typeof gravidadeSchema>;
export type Alerta = z.output<typeof alertaSchema>;
export type ResumoDeAlertas = z.output<typeof resumoDeAlertasSchema>;
export type Desperdicio = z.output<typeof desperdicioSchema>;
