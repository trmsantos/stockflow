import { z } from "zod";

/**
 * O contrato do módulo `purchasing`, em Zod.
 *
 * Como em `inventory`, estes schemas são o **rascunho do contrato** que a
 * sessão do backend recebe (ADR 0008, decisão 3): o mesmo ficheiro valida a
 * resposta no cliente e valida o fixture no servidor de desenvolvimento, logo
 * não há duas noções do payload.
 *
 * Três afirmações de domínio estão **na forma do contrato** e não num
 * comentário de UI, porque é aqui que o backend as vai ler:
 *
 *  1. **Uma receção não exige encomenda nem fatura.** Não há `purchase_order`
 *     em sítio nenhum, o `doc_number` é anulável (a fatura manuscrita da
 *     frutaria não tem número) e `awaiting_invoice` existe para a mercadoria
 *     que entra por guia de remessa e só é faturada a fim de mês. "Se o modelo
 *     de dados exigir uma `PurchaseOrder`, está errado para o mercado
 *     português" (guião da sessão 0, §5).
 *  2. **O IVA é dado da linha.** `vat_rate` vive em `linhaDeRececaoSchema` e
 *     não no artigo, porque a taxa muda entre o Continente e as Regiões
 *     Autónomas e porque o que vale é o que está impresso no documento. Um
 *     artigo não "tem" taxa.
 *  3. **A extração não gera movimentos; a confirmação humana gera.** Uma
 *     receção é um rascunho (`status: "needs_review"`) e cada linha tem o seu
 *     próprio estado. O campo `movement` de uma linha é `null` até alguém
 *     confirmar, e é o único sítio onde o ledger e este módulo se tocam
 *     (CLAUDE.md: "toda a extração de fatura passa por revisão humana antes de
 *     gerar movimentos").
 *
 * **Porque é que `quantidadeSchema` e `localizacaoSchema` estão aqui outra vez,
 * se já existem em `inventory`:** as fronteiras do frontend só deixam importar
 * de outra feature o seu `api.ts` (ADR 0008, decisão 2), e isso é deliberado —
 * o que viaja entre módulos são hooks, não a forma do payload. Em DRF seria o
 * mesmo: `apps/purchasing/serializers.py` declara os seus campos ainda que o
 * valor seja o mesmo value object. São vinte linhas repetidas com a alternativa
 * nomeada: no dia em que um **terceiro** módulo precisar destas formas, elas
 * descem para `src/lib/`, que é o `apps/shared` do frontend, e esse diff é uma
 * decisão com um caso à frente em vez de uma generalização a dois.
 */

/** `"-2000.000"` — o que o DRF serializa a partir de um `DecimalField`. */
const decimal = z.string().regex(/^-?\d+$|^-?\d+\.\d+$/, "decimal inválido");

/** A unidade base de stock do artigo. É nesta unidade que o ledger guarda. */
export const unidadeBaseSchema = z.enum(["g", "ml", "un"]);

/** Uma quantidade, nas duas formas: a do ledger e a de mostrar. */
export const quantidadeSchema = z.object({
  base: decimal,
  base_unit: unidadeBaseSchema,
  display: decimal,
  display_unit: z.string().min(1),
});

export const localizacaoSchema = z.object({
  id: z.uuid(),
  name: z.string().min(1),
});

/** "Consumir até" (limite legal) contra "consumir de preferência antes de". */
export const tipoValidadeSchema = z.enum(["use_by", "best_before"]);

/**
 * Os tipos de documento com que a mercadoria chega a uma cozinha portuguesa.
 *
 * `FT` fatura · `FR` fatura-recibo · `FS` fatura simplificada (o cash & carry,
 * sem encomenda) · `NC` nota de crédito (devolução, que referencia o documento
 * original) · `GR` guia de remessa (a mercadoria entra **antes** de existir
 * fatura, e a fatura de fim de mês reconcilia N entregas).
 *
 * Os cinco estão aqui porque os cinco aparecem no seed. Não há um sexto valor
 * "outro": um documento que não seja nenhum destes é uma conversa a ter, não um
 * caso a tratar em silêncio.
 */
export const tipoDeDocumentoSchema = z.enum(["FT", "FR", "FS", "NC", "GR"]);

/**
 * O estado da receção. **Dois**, e não três: ou está à espera de revisão, ou já
 * foi confirmada. Não há "parcialmente confirmada" — uma linha que ficou de
 * fora fica-o na linha (`skipped`), e o documento não ganha um estado
 * intermédio que ninguém saberia resolver.
 */
export const estadoDeRececaoSchema = z.enum(["needs_review", "confirmed"]);

/**
 * O estado de uma linha. `skipped` é a linha que o utilizador decidiu deixar
 * fora desta entrada — tipicamente um artigo que a fatura traz e o catálogo não
 * tem. Não gera movimento e **não** bloqueia a confirmação do documento.
 */
export const estadoDeLinhaSchema = z.enum(["needs_review", "confirmed", "skipped"]);

/**
 * O que a linha é, para o ledger.
 *
 * `goods` é mercadoria e é a única espécie que gera movimento. `deposit` é
 * tara/vasilhame retornável: linha de fatura **com valor** que não é stock
 * consumível (guião §2, prática 5). `charge` é portes, serviço ou desconto —
 * valor sem mercadoria. Tratar as três como iguais era inventar stock de
 * grades de plástico e de portes de envio.
 */
export const especieDeLinhaSchema = z.enum(["goods", "deposit", "charge"]);

/**
 * Como se conserva o que vem nesta linha. É o que decide se a receção pede
 * registo de temperatura à entrega.
 */
export const conservacaoSchema = z.enum(["ambient", "chilled", "frozen"]);

export const fornecedorSchema = z.object({
  name: z.string().min(1),
  /** NIF de nove dígitos. `null` quando o documento não o traz legível. */
  nif: z.string().regex(/^\d{9}$/, "NIF inválido").nullable(),
});

/**
 * A embalagem em que o fornecedor vende, e quanto ela vale na unidade base.
 *
 * É este objeto que torna a conversão mostrável — "1 caixa 12×1 L → 12 000 ml"
 * — sem que o cliente faça a conta: o `base_quantity` é **uma** embalagem, e a
 * quantidade que entra no ledger vem pronta em `stock_quantity`. Converter
 * unidades no cliente é a fonte nº 1 de bugs de stock (`inventory-domain` §2);
 * aqui o cliente só escreve a frase.
 */
export const embalagemSchema = z.object({
  /** Como o fornecedor lhe chama: "caixa 12×1 L", "bloco 2,5 kg", "kg". */
  label: z.string().min(1),
  base_quantity: decimal,
  base_unit: unidadeBaseSchema,
});

/**
 * O preço desta linha contra o das últimas compras do mesmo artigo.
 *
 * Existe porque "manteiga a 9,40 €/kg contra 7,80 €" é um dos eventos que o
 * guião §2 exige nos dados, e porque é o único número desta feature que o dono
 * reconhece de imediato. Dois cuidados:
 *
 *  - a comparação é de **preço de compra** (`SupplierPrice`,
 *    `inventory-domain` §6), não do custo médio ponderado: o CMP é uma média
 *    histórica e compará-lo com uma linha de fatura daria uma percentagem que
 *    não quer dizer nada;
 *  - a variação vem em **pontos percentuais inteiros** e o limiar que a fez
 *    aparecer viaja com ela, para o ecrã o poder mostrar ("aviso acima de
 *    10 %") em vez de o esconder num painel de configurações (guião §4, nº 7).
 */
export const historicoDePrecoSchema = z.object({
  last_price: decimal,
  /** A unidade a que os dois preços se referem ("kg", "bloco 2,5 kg"). */
  unit_label: z.string().min(1),
  /** `21` = 21 % acima. Negativo quando está mais barato. */
  change_pct: z.number().int(),
  /** De onde vem o preço anterior: o documento, para ele poder ir ver. */
  reference: z.string().min(1),
  threshold_pct: z.number().int().positive(),
});

/**
 * Uma linha de fatura, que é o objeto central desta feature.
 *
 * A ordem dos campos é a ordem em que a linha se lê no ecrã: o que a fatura
 * diz, o que isso é no catálogo, quanto entra no stock, quanto custou, e o lote
 * com a validade — que é a única parte que **ninguém** consegue extrair de um
 * documento, porque está na embalagem e não na fatura.
 */
export const linhaDeRececaoSchema = z.object({
  id: z.uuid(),
  /** A ordem em que as linhas estão impressas no documento. */
  position: z.number().int().nonnegative(),
  /**
   * A descrição **como vem na fatura** (`FARINHA T65 SACO 25KG`), que não é o
   * nome curto do artigo. As duas aparecem lado a lado no ecrã de propósito: é
   * a tradução que o utilizador está a confirmar.
   */
  description: z.string().min(1),
  /** O artigo do catálogo. `null` = a fatura traz algo que o catálogo não tem. */
  product: z.uuid().nullable(),
  product_name: z.string().min(1).nullable(),
  kind: especieDeLinhaSchema,
  status: estadoDeLinhaSchema,
  conservation: conservacaoSchema,
  /** Onde esta linha entra. Pode ser diferente de linha para linha. */
  location: localizacaoSchema,
  /** A unidade impressa na linha: "bloco", "caixa", "kg", "un". */
  invoice_unit: z.string().min(1),
  quantity_invoiced: decimal,
  /**
   * O que entrou de facto. Diferente do faturado numa **receção parcial** (5
   * rolos faturados, 3 entregues) — e é assim que a parcial se representa sem
   * uma encomenda: a divergência é entre o documento e a prateleira, não entre
   * a encomenda e a entrega.
   */
  quantity_received: decimal,
  packaging: embalagemSchema.nullable(),
  /**
   * O que entra (ou já entrou) no ledger, na unidade base e na de mostrar.
   * `null` quando a linha não é stock — tara, portes, ou um artigo que o
   * catálogo não tem.
   */
  stock_quantity: quantidadeSchema.nullable(),
  /** Peso irregular, pesado peça a peça na fatura: o queijo e o fiambre ao kg. */
  variable_weight: z.boolean(),
  /** Por `invoice_unit`. `null` numa guia de remessa, que não traz preços. */
  unit_price: decimal.nullable(),
  /** A taxa **como vem na linha**, em fração (`"0.230"`). Nunca do artigo. */
  vat_rate: decimal.nullable(),
  line_total: decimal.nullable(),
  price_history: historicoDePrecoSchema.nullable(),
  /** Se este artigo exige lote: perecível, ou de origem animal (HACCP). */
  requires_lot: z.boolean(),
  lot_code: z.string().min(1).nullable(),
  expires_at: z.iso.date().nullable(),
  /**
   * Qual dos dois rótulos a validade desta linha é. Vem do **artigo** e não é
   * escolha de quem recebe: é a distinção que o ecrã Alertas usa para não
   * marcar a amêndoa laminada a vermelho.
   */
  expiry_kind: tipoValidadeSchema.nullable(),
  reviewed_by: z.string().min(1).nullable(),
  reviewed_at: z.iso.datetime().nullable(),
  /**
   * O movimento que esta linha criou no ledger. `null` enquanto não houver
   * confirmação humana — e é este campo que prova que a extração, por si, não
   * mexe no stock.
   */
  movement: z.uuid().nullable(),
});

/** A base e o IVA por taxa, como vêm no rodapé do documento. */
export const totalDeIvaSchema = z.object({
  rate: decimal,
  base: decimal,
  vat: decimal,
});

export const rececaoSchema = z.object({
  id: z.uuid(),
  supplier: fornecedorSchema,
  doc_type: tipoDeDocumentoSchema,
  /** `null` numa fatura manuscrita sem número — e existem. */
  doc_number: z.string().min(1).nullable(),
  /** Quando a mercadoria chegou, segundo o documento. */
  received_at: z.iso.datetime(),
  /**
   * Quando foi revista e confirmada, que é quando os movimentos entraram no
   * ledger. `null` enquanto é rascunho. Não é o mesmo instante que o
   * `received_at`: a mercadoria entra de manhã e a fatura lança-se depois, e é
   * por isso que são dois campos e não um.
   */
  confirmed_at: z.iso.datetime().nullable(),
  confirmed_by: z.string().min(1).nullable(),
  status: estadoDeRececaoSchema,
  /** Quantas linhas faltam rever. É o número que o badge da lista mostra. */
  lines_to_review: z.number().int().nonnegative(),
  line_count: z.number().int().nonnegative(),
  /**
   * O adquirente **como vem no documento** — nome e NIF.
   *
   * Vem ao lado do nome e do NIF da empresa, e os quatro campos existem por
   * causa da Q10: a fatura simplificada do cash & carry foi emitida ao NIF
   * pessoal do sócio, e o ecrã extrai isso num badge discreto. O par da empresa
   * viaja no payload em vez de viver no cliente pela mesma razão que o
   * `?loja=` é um id: um NIF guardado no frontend seria uma segunda fonte de
   * verdade sobre o estabelecimento, e só sabe ficar desatualizada.
   */
  customer_name: z.string().nullable(),
  customer_nif: z.string().nullable(),
  company_name: z.string().min(1),
  company_nif: z.string(),
  /** Entrou por guia e a fatura ainda não existe. Não é um erro: é o normal. */
  awaiting_invoice: z.boolean(),
  /** O total **impresso**. `null` numa guia de remessa sem preços. */
  document_total: decimal.nullable(),
  /**
   * A soma das linhas. Pode não bater com o impresso — um desconto de rodapé,
   * portes, uma linha que não foi lida. O ecrã avisa e **não** bloqueia:
   * bloquear é a Q1 e o shell não responde por ela (guião §4, proibição 3).
   */
  lines_total: decimal.nullable(),
  vat_breakdown: z.array(totalDeIvaSchema),
  /** A temperatura à entrega, em °C. */
  temperature_c: decimal.nullable(),
  /** Esta receção traz frio: refrigerado ou congelado. */
  cold_chain: z.boolean(),
  /** Onde a mercadoria entrou. Mais do que uma numa ida ao cash & carry. */
  locations: z.array(localizacaoSchema),
  /** A referência com que os movimentos desta receção vivem no ledger. */
  reference: z.string().min(1),
});

/**
 * Os dois números do topo: "1 receção a precisar de revisão · 3 confirmadas
 * hoje" (guião §1).
 *
 * **Dois e não três.** O orçamento de 360×640 são três números *ou* uma linha a
 * mais na lista (guião §0), e o terceiro candidato — "1 sem fatura" — diz-se
 * melhor onde acontece: num badge na linha da guia de remessa.
 *
 * O `business_day_starts_at` é o mesmo dado do ecrã Alertas, e está aqui pela
 * mesma razão: "confirmadas hoje" tem de significar o dia de negócio (que numa
 * pastelaria começa ao início da produção) e não o dia civil, senão uma
 * entrega lançada às 05:30 aparece no dia errado.
 */
export const resumoDeRececoesSchema = z.object({
  needs_review_count: z.number().int().nonnegative(),
  /** O total de linhas por rever, somando as receções. */
  needs_review_lines: z.number().int().nonnegative(),
  confirmed_today_count: z.number().int().nonnegative(),
  business_day_starts_at: z.string().regex(/^\d\d:\d\d$/, "hora inválida"),
  confirmed_since: z.iso.datetime(),
});

/**
 * O corpo de `POST /receipts/<id>/lines/<linha>/confirmation` — a revisão
 * humana de **uma** linha, que é a segunda ação do ecrã.
 *
 * Todos os campos são opcionais porque uma linha chega ao utilizador em estados
 * diferentes: a que só precisa de lote manda o lote, a que não tem artigo manda
 * o artigo (ou `skip: true` para ficar de fora desta entrada), e a que já está
 * bem manda um corpo vazio e é só um "confirmo".
 *
 * Não há schema para **apagar** uma linha: um documento não se edita, e uma
 * linha que não devia entrar fica `skipped` com registo de quem o decidiu.
 *
 * **Não há `product`, e a ausência é uma decisão por tomar e não um
 * esquecimento.** Uma linha que o catálogo não tem resolve-se de duas maneiras
 * — criar o artigo, ou associar a um existente — e as duas precisam de saber
 * quantas unidades base vale a embalagem daquela linha ("pacote de 500 folhas"
 * não converte para nada). Dar aqui um seletor de artigo sem essa conversão era
 * prometer uma entrada de stock com um número inventado, que é exactamente o
 * que este ecrã existe para não fazer; e um formulário de criação de artigo
 * pré-decide o âmbito do catálogo v1, que é uma das perguntas da sessão. No
 * shell a linha sem artigo só se deixa de fora; o campo entra quando houver
 * resposta sobre o catálogo.
 */
export const revisaoDeLinhaSchema = z.object({
  lot_code: z.string().trim().min(1).max(40).optional(),
  expires_at: z.iso.date().optional(),
  /** Deixa a linha fora desta entrada. Reversível: volta a `needs_review`. */
  skip: z.boolean().optional(),
});

/**
 * O corpo de `POST /receipts/<id>/temperature`.
 *
 * Em °C, com uma casa decimal, e aceita negativos — um ultracongelado chega a
 * −18 °C e um valor positivo nessa linha é precisamente o que interessa
 * registar.
 */
export const temperaturaSchema = z.object({
  celsius: decimal,
});

export type UnidadeBase = z.output<typeof unidadeBaseSchema>;
export type Quantidade = z.output<typeof quantidadeSchema>;
export type Localizacao = z.output<typeof localizacaoSchema>;
export type TipoValidade = z.output<typeof tipoValidadeSchema>;
export type TipoDeDocumento = z.output<typeof tipoDeDocumentoSchema>;
export type EstadoDeRececao = z.output<typeof estadoDeRececaoSchema>;
export type EstadoDeLinha = z.output<typeof estadoDeLinhaSchema>;
export type EspecieDeLinha = z.output<typeof especieDeLinhaSchema>;
export type Conservacao = z.output<typeof conservacaoSchema>;
export type Fornecedor = z.output<typeof fornecedorSchema>;
export type Embalagem = z.output<typeof embalagemSchema>;
export type HistoricoDePreco = z.output<typeof historicoDePrecoSchema>;
export type LinhaDeRececao = z.output<typeof linhaDeRececaoSchema>;
export type TotalDeIva = z.output<typeof totalDeIvaSchema>;
export type Rececao = z.output<typeof rececaoSchema>;
export type ResumoDeRececoes = z.output<typeof resumoDeRececoesSchema>;
export type RevisaoDeLinha = z.output<typeof revisaoDeLinhaSchema>;
export type Temperatura = z.output<typeof temperaturaSchema>;
