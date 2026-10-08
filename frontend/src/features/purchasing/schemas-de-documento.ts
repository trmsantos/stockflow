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
 * por construção (SECURITY.md §4). Os cinco DTO abaixo são os cinco da decisão 9
 * da ADR 0021 — `DocumentoOut`, `FicheiroOut`, `PaginaOut`, `ExtracaoOut`,
 * `LinhaLidaOut` —, campo a campo, na ordem em que o contrato os escreve.
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
 */
export const linhaLidaSchema = z.object({
  position: z.number().int().positive(),
  description: z.string(),
  quantity: decimal.nullable(),
  unit: z.string(),
  unit_price: decimal.nullable(),
  vat_rate: decimal.nullable(),
  line_total: decimal.nullable(),
  confidence: decimal.nullable(),
});

/**
 * O que o modelo leu, num painel só de leitura.
 *
 * `reason` é a razão legível de um `erro` e é a razão pela qual este ecrã não
 * tem de inventar uma frase: hoje a extração falha sempre com a mesma — não há
 * modelo configurado. O ecrã mostra-a sem a reescrever.
 */
export const extracaoSchema = z.object({
  state: estadoDaLeituraSchema,
  confidence: decimal.nullable(),
  read_at: z.iso.datetime({ offset: true }).nullable(),
  reason: z.string(),
  supplier_name: z.string(),
  supplier_nif: z.string(),
  doc_type: z.string(),
  doc_number: z.string(),
  issued_at: z.iso.date().nullable(),
  customer_nif: z.string(),
  total: decimal.nullable(),
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
export type Extracao = z.output<typeof extracaoSchema>;
export type Documento = z.output<typeof documentoSchema>;
