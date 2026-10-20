import { z } from "zod";

/**
 * O contrato do **documento de fornecedor**, em Zod — a fatia 1 da ADR 0021.
 *
 * ## Porque é um ficheiro ao lado do `schemas.ts` e não mais uma secção dele
 *
 * São dois contratos com **estatutos diferentes**, e misturá-los apagava a
 * diferença. O `schemas.ts` é o *rascunho* que a sessão do backend recebeu (ADR
 * 0008, decisão 3): escrito primeiro no cliente, servido por fixtures, ainda sem
 * tabela do outro lado. Isto é o oposto — os endpoints existem, o
 * `openapi/schema.yaml` é a fonte e os tipos estão gerados em
 * `src/lib/api/types.ts`. Quem lê um `schemas.ts` com as duas coisas lá dentro
 * não tem como saber qual metade é promessa e qual é facto.
 *
 * ## Porque Zod, se os tipos já estão gerados
 *
 * Porque **um tipo não valida nada**. O `types.ts` descreve o que o servidor
 * promete; em runtime o que chega é `unknown`, e o `apiRequest` exige um schema
 * por construção (SECURITY.md §4). Os DTO abaixo são os cinco da decisão 9 da
 * ADR 0021 — `DocumentoOut`, `FicheiroOut`, `PaginaOut`, `ExtracaoOut`,
 * `LinhaLidaOut` — mais os **dois** que a ADR 0031 acrescentou ao `ExtracaoOut`
 * (`DivergenciaOut` e `ConferenciaDeIvaOut`), campo a campo.
 *
 * **A ordem é a semântica e não a alfabética do gerador.** O `types.ts` sai do
 * `openapi-typescript` com os campos por ordem alfabética, que é a ordem certa
 * para uma máquina e a errada para quem compara isto com o serializer: aqui os
 * campos ficam agrupados como se lêem — primeiro o estado da leitura, depois o
 * cabeçalho, depois o que veio do QR, por fim as linhas.
 *
 * ## O que a forma do contrato **afirma**, e que não é um comentário de UI
 *
 *  1. **O estado é derivado e são oito.** Não há um `default` possível no ecrã:
 *     um valor novo no enum deixa de compilar nos mapas do `vocabulario.ts`, que
 *     é onde um estado sem palavra tem de doer;
 *  2. **`image_url` é sempre uma string e `normalized` é quem decide**. É a
 *     escolha que o DTO explica: um `image_url` nulo dava dois campos para a
 *     mesma pergunta. Logo o ecrã nunca pede os bytes sem olhar primeiro para o
 *     booleano — e hoje o booleano é sempre `false`, porque não há rasterizador
 *     neste projecto;
 *  3. **`extraction` é anulável e o cabeçalho vem vazio quando o estado não é
 *     `lido`**. As strings do `ExtracaoOut` são `z.string()` e não
 *     `z.string().min(1)` exactamente por isso: um `supplier_name` vazio é o
 *     caso normal de um documento que ainda não foi lido, não um contrato
 *     partido;
 *  4. **`receipt` é sempre nulo nesta fatia.** Está no contrato para o
 *     `types.ts` não mudar de forma na fatia 2. O ecrã não o lê — e a razão
 *     fica escrita aqui em vez de ser descoberta por quem o tentar usar.
 *
 * Os números são `string` e não `number`: são `Decimal` do lado do Django e um
 * `float` do JavaScript perde cêntimos. A conversão para mostrar é do
 * `src/lib/format.ts`.
 */

/** `"-2000.000"` — o que o DRF serializa a partir de um `DecimalField`. */
const decimal = z.string().regex(/^-?\d+$|^-?\d+\.\d+$/, "decimal inválido");

/**
 * De onde vieram os bytes. **Derivada pelo servidor** e não declarada pelo
 * cliente: um pedido com ficheiro é `upload`, um pedido vazio é o slot que
 * espera páginas (`services.criar_documento`).
 */
export const origemDoDocumentoSchema = z.enum(["upload", "capture"]);

/**
 * Os oito estados do documento, derivados e nunca guardados (ADR 0021, decisão
 * 9; ADR 0020, decisão 2).
 *
 * Três são relógios e não colunas, e é isso que os torna impossíveis de guardar:
 * `aguarda_captura` passa a `expirado` quinze minutos depois do `created_at` sem
 * que ninguém escreva nada, e `a_extrair` passa a `erro` dez minutos depois de
 * uma extração que não acabou. Um estado em coluna estaria errado no minuto
 * seguinte.
 */
export const estadoDoDocumentoSchema = z.enum([
  "aguarda_captura",
  "expirado",
  "a_normalizar",
  "a_extrair",
  "lido",
  "ilegivel",
  "erro",
  "descartado",
]);

/**
 * O estado da **leitura**, que é outra coisa que o estado do documento: um
 * documento pode estar `lido` com uma extração `ilegivel`? Não — mas os dois
 * enums existem porque a extração é uma linha por tentativa e o documento é um
 * só (cada reabertura acrescenta uma linha em vez de sobrepor a anterior).
 */
export const estadoDaLeituraSchema = z.enum(["pendente", "lido", "ilegivel", "erro"]);

/**
 * Uma página: a ordem, a imagem e a geometria.
 *
 * `width`/`height` são anuláveis porque só existem depois da normalização, e a
 * normalização é a tarefa que hoje não corre. É a segunda metade do mesmo facto
 * que o `normalized` diz.
 */
export const paginaDeDocumentoSchema = z.object({
  position: z.number().int().positive(),
  image_url: z.string().min(1),
  width: z.number().int().positive().nullable(),
  height: z.number().int().positive().nullable(),
  normalized: z.boolean(),
});

/**
 * Um ficheiro: o que entrou, quando, e o que os bytes diziam.
 *
 * `content_type` é o **real** (bytes mágicos) e não o que o cliente declarou —
 * o `Content-Type` do pedido é ignorado e não validado (ADR 0020, decisão 4).
 * `original_filename` é um rótulo e nunca um caminho, e pode vir vazio.
 */
export const ficheiroDeDocumentoSchema = z.object({
  position: z.number().int().positive(),
  original_filename: z.string(),
  content_type: z.string().min(1),
  byte_size: z.number().int().nonnegative(),
  pages_detected: z.number().int().nonnegative(),
  received_at: z.iso.datetime({ offset: true }),
});

/**
 * Uma linha que o modelo leu. **Nada aqui é verdade sobre o estabelecimento** —
 * é uma afirmação não confiável de um LLM, e o que a torna verdade é a revisão
 * humana da fatia 2 (CLAUDE.md).
 *
 * Todos os números são anuláveis: um modelo que não conseguiu ler a quantidade
 * devolve a descrição e mais nada, e inventar um zero era pior.
 *
 * ## Os três campos de dinheiro, e **a ausência não é o `null`**
 *
 * Desde 2026-10-19 só `owner|manager` veem euros numa receção (ADR 0031, adenda
 * dos euros), e esta é a **mesma fatura pela porta do lado**: o painel da
 * extração servia os preços lidos a qualquer papel, pela rota do documento. O
 * servidor fechou-a da única forma que não mente — tira a chave do JSON
 * (`SemEurosParaQuemNaoVe`) — e aqui são **três** estados e não dois:
 *
 *  - `undefined` (chave ausente) — *"não te compete"*. É sobre **quem** olha, e
 *    o painel tira a coluna inteira;
 *  - `null` — *"o modelo não leu este número"*. É sobre o **documento**, e a
 *    célula diz "—" dentro de uma coluna que existe;
 *  - uma string decimal — o número lido.
 *
 * `.nullable().optional()` e não `.nullish()`: são dois factos e escrevem-se os
 * dois. **Isto é o defeito que o `schemas.ts` já pagou**, repetido no ecrã do
 * lado: em Zod o `.nullable()` sozinho aceita `null` e continua a **exigir a
 * chave presente**, logo para um `staff` o painel do documento não degradava —
 * rebentava, com o `pnpm typecheck` verde, porque estes schemas são escritos à
 * mão e a validação é em runtime.
 */
export const linhaLidaSchema = z.object({
  position: z.number().int().positive(),
  description: z.string(),
  quantity: decimal.nullable(),
  unit: z.string(),
  unit_price: decimal.nullable().optional(),
  /**
   * O desconto **de linha**, em percentagem. Sem ele o custo derivava do preço
   * bruto, que é o bug clássico desta família (ADR 0031, decisão 5) — e é por
   * isso que ele é dinheiro e sai com os outros dois: é a condição comercial, o
   * preço por outro caminho.
   */
  discount_pct: decimal.nullable().optional(),
  /**
   * A taxa fica **de fora** e continua obrigatória: 6, 13 ou 23 está impressa
   * em qualquer talão e não diz quanto custou nada. O mesmo vale para a
   * `quantity`, a `unit`, a `description`, o `supplier_code`, o `ean` e a
   * `confidence`, que continuam a sair para toda a gente.
   */
  vat_rate: decimal.nullable(),
  line_total: decimal.nullable().optional(),
  /**
   * A referência do artigo **no catálogo do fornecedor** e o código de barras.
   *
   * São strings e não anuláveis: o serializer serve `""` para o que o modelo
   * não leu, como faz em todo o cabeçalho. São os dois campos de que a memória
   * do match vive — sem eles cada fatura é a primeira (ADR 0031, decisão 5) —, e
   * **nenhum dos dois é um artigo**: quem escolhe o artigo é o catálogo, por
   * chave exacta, e nunca o modelo.
   */
  supplier_code: z.string(),
  ean: z.string(),
  confidence: decimal.nullable(),
});

/**
 * Um campo em que o **papel** e o **QR** não dizem o mesmo.
 *
 * Três strings, porque isto é para ler: um `Decimal` e uma data já vêm
 * formatados de quem os comparou. O `field` é o identificador do campo do
 * cabeçalho (`supplier_nif`, `doc_number`, `total`, …) e tem palavra no
 * `vocabulario-de-documento`.
 *
 * **O valor servido no cabeçalho é sempre o do QR** — ele é gerado por software
 * certificado e o papel é a leitura de uma fotografia. Isto é a prova de que ele
 * ganhou, e nunca a lista do que falta decidir.
 *
 * **Os três campos continuam obrigatórios e a lista é que encolhe.** Uma
 * divergência cujo `field` é dinheiro serve o `paper` e o `qr` como texto — a do
 * `total` diz o total do documento duas vezes —, logo quem não vê euros não
 * recebe a **linha inteira**: um `{"field": "total"}` sem valores era um aviso
 * sobre nada. Quem filtra é o servidor, e o ecrã não tem aqui nada a decidir. As
 * outras — NIF, tipo, número, data — continuam a sair, e são as mais úteis: um
 * número de documento mal lido é o que diz a quem recebe que a fotografia tem
 * dois papéis.
 */
export const divergenciaDeCabecalhoSchema = z.object({
  field: z.string(),
  paper: z.string(),
  qr: z.string(),
});

/**
 * A soma das linhas lidas numa taxa de IVA, contra a base dessa taxa no QR.
 *
 * `matches` falso é **o sinal mais forte que esta feature produz sobre a
 * qualidade de uma leitura** — mais forte do que a `confidence`, que o modelo
 * reporta de si próprio e que não está calibrada contra nada.
 *
 * `qr_base` e `difference` são anuláveis porque o QR pode não trazer base
 * nenhuma naquela taxa; aí não há nada a comparar e o `matches` não é uma
 * acusação.
 *
 * ## As três bases são dinheiro; a `rate` e o `matches` **não**
 *
 * E é essa divisão que faz esta tabela continuar a servir quem não vê euros. As
 * bases saem por ausência — a soma delas *é* o total da fatura, e `lines_base` é
 * literalmente a Σ dos `line_total` que a linha acima esconde, logo deixá-las
 * visíveis reconstruía por adição o que se tira por ausência. Ficam a taxa e o
 * veredicto, que é a **marcação qualitativa** desta leitura e exactamente o
 * trabalho de quem recebe: um `matches: false` é *"o sinal mais forte que esta
 * feature produz sobre a qualidade de uma leitura"* (ADR 0031), e o colaborador
 * continua a ver que as contas não batem sem ver um único euro.
 *
 * `lines_base` é `.optional()` **sem** `.nullable()`: uma soma de linhas é
 * sempre um número para quem a pode ver — zero quando o QR traz uma taxa que as
 * linhas não têm, que é o caso que diz "faltam linhas".
 */
export const conferenciaDeIvaSchema = z.object({
  rate: decimal,
  lines_base: decimal.optional(),
  qr_base: decimal.nullable().optional(),
  difference: decimal.nullable().optional(),
  matches: z.boolean(),
});

/**
 * O que o modelo leu, num painel só de leitura.
 *
 * `reason` é a razão legível de um `erro`, e é por isso que o ecrã não tem de
 * inventar uma frase — mostra-a sem a reescrever. Desde a ADR 0031 ela deixou de
 * ser sempre a mesma (*"não há modelo configurado"*): a extração corre a sério,
 * logo a razão pode ser um teto de tentativas, um orçamento diário gasto, ou um
 * documento com páginas a mais.
 *
 * ## Os sete campos que a ADR 0031 acrescentou, e o que cada um traz
 *
 *  - `attempt` — a que tentativa esta leitura corresponde. É o que diz ao ecrã
 *    se ainda há *tentar outra vez* para oferecer: oferecer um botão que o
 *    servidor vai recusar com 409 é mentir a quem o carrega;
 *  - `atcud` e `fiscal_space` — o que o QR traz e o papel raramente dá;
 *  - `qr_read` — **se houve QR legível**. É como o ecrã sabe se o cabeçalho é
 *    certificado ou leitura de uma fotografia, e as duas coisas valem o mesmo no
 *    tipo mas não valem o mesmo para quem revê;
 *  - `cancelled` — o `E=A` do QR. Um documento anulado pelo emissor não dá
 *    entrada a nada, e o servidor recusa a receção com esse código;
 *  - `divergences` e `vat_checks` — a prova de que o QR ganhou, e a aritmética
 *    das linhas contra a base certificada.
 */
export const extracaoSchema = z.object({
  state: estadoDaLeituraSchema,
  confidence: decimal.nullable(),
  read_at: z.iso.datetime({ offset: true }).nullable(),
  reason: z.string(),
  /**
   * A tentativa desta leitura. Inteiro e não `Decimal`: é uma contagem, não um
   * número de domínio, logo `z.number()` é o tipo certo e não há cêntimos a
   * perder.
   */
  attempt: z.number().int().nonnegative(),
  supplier_name: z.string(),
  supplier_nif: z.string(),
  doc_type: z.string(),
  doc_number: z.string(),
  issued_at: z.iso.date().nullable(),
  customer_nif: z.string(),
  /**
   * O total impresso. É o **mesmo número** que o `document_total` de uma
   * receção, logo sai pela mesma regra e com a mesma forma: ausente para quem
   * não vê euros, `null` quando o modelo não o leu.
   */
  total: decimal.nullable().optional(),
  atcud: z.string(),
  fiscal_space: z.string(),
  qr_read: z.boolean(),
  cancelled: z.boolean(),
  divergences: z.array(divergenciaDeCabecalhoSchema),
  vat_checks: z.array(conferenciaDeIvaSchema),
  lines: z.array(linhaLidaSchema),
});

/**
 * O documento inteiro — a resposta das **cinco** operações que devolvem um
 * documento (criar, anexar, fechar, ler um, listar).
 *
 * É isso que faz o polling da ADR 0020 (decisão 3) ser só um `GET`: quem
 * escreve recebe o estado completo e não precisa de uma segunda leitura para o
 * descobrir.
 */
export const documentoSchema = z.object({
  id: z.uuid(),
  source: origemDoDocumentoSchema,
  state: estadoDoDocumentoSchema,
  created_at: z.iso.datetime({ offset: true }),
  created_by: z.string(),
  closed_at: z.iso.datetime({ offset: true }).nullable(),
  expires_at: z.iso.datetime({ offset: true }),
  page_count: z.number().int().nonnegative(),
  page_limit: z.number().int().positive(),
  files: z.array(ficheiroDeDocumentoSchema),
  pages: z.array(paginaDeDocumentoSchema),
  extraction: extracaoSchema.nullable(),
  receipt: z.uuid().nullable(),
});

export type OrigemDoDocumento = z.output<typeof origemDoDocumentoSchema>;
export type EstadoDoDocumento = z.output<typeof estadoDoDocumentoSchema>;
export type EstadoDaLeitura = z.output<typeof estadoDaLeituraSchema>;
export type PaginaDeDocumento = z.output<typeof paginaDeDocumentoSchema>;
export type FicheiroDeDocumento = z.output<typeof ficheiroDeDocumentoSchema>;
export type LinhaLida = z.output<typeof linhaLidaSchema>;
export type DivergenciaDeCabecalho = z.output<typeof divergenciaDeCabecalhoSchema>;
export type ConferenciaDeIva = z.output<typeof conferenciaDeIvaSchema>;
export type Extracao = z.output<typeof extracaoSchema>;
export type Documento = z.output<typeof documentoSchema>;
