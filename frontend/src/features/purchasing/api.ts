import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";

import { useInvalidarLedger } from "@/features/inventory/api";
import { apiRequest } from "@/lib/api/http";
import { paginated, type Paginated } from "@/lib/api/pagination";
import { queryKeys } from "@/lib/api/query-keys";
import { tenantDaCache } from "@/lib/api/tenant";

import {
  cabecalhoParaReverSchema,
  linhaDeRececaoSchema,
  linhaParaCriarSchema,
  rececaoParaCriarSchema,
  rececaoSchema,
  resumoDeRececoesSchema,
  revisaoDeLinhaSchema,
  temperaturaSchema,
  type CabecalhoParaRever,
  type LinhaParaCriar,
  type Rececao,
  type RececaoParaCriar,
  type ResumoDeRececoes,
  type RevisaoDeLinha,
} from "./schemas";

/**
 * A camada de dados do módulo `purchasing` — o `api.py` do frontend.
 *
 * Escrita na forma final (ADR 0008, decisão 3): mesmo `fetch`, mesmo cookie de
 * sessão, mesmo `X-Tenant-ID`, mesmo envelope de paginação, mesmo Zod. Em
 * desenvolvimento quem responde é o servidor de fixtures do Vite; no dia em que
 * o Django servir estes caminhos não muda uma linha aqui nem nos ecrãs.
 *
 * **A regra que este módulo tem de encarnar está na forma das mutações.** São
 * três escritas e só **uma** toca no ledger:
 *
 *  - `useRevisarLinha` grava a revisão humana de uma linha (artigo, lote,
 *    validade, ou "fica de fora"). Invalida este módulo e mais nada — rever
 *    não cria stock;
 *  - `useRegistarTemperatura` grava um número que é um registo de receção, não
 *    um movimento;
 *  - `useConfirmarRececao` é a única que cria movimentos, e por isso é a única
 *    que invalida o ledger inteiro, através do `useInvalidarLedger` do módulo
 *    `inventory`. Antes dela, o nível do artigo no ecrã de Stock não muda;
 *    depois dela, muda. É o que separa este produto de um que inventa stock a
 *    partir de um OCR.
 */

const CAMINHO_RECECOES = "/receipts";
const CAMINHO_RESUMO = "/receipts/summary";

/**
 * Dois recursos na cache: os documentos e as suas linhas. São dois porque
 * mudam em ritmos diferentes — confirmar uma linha muda a linha e o contador de
 * "linhas por rever" do documento, e não mexe nas outras receções.
 */
const RECURSO_RECECOES = "receipts";
const RECURSO_LINHAS = "receipt-lines";

function invalidarRececoes(
  queryClient: ReturnType<typeof useQueryClient>,
  tenant: string,
): Promise<unknown> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.resource(tenant, RECURSO_RECECOES) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.resource(tenant, RECURSO_LINHAS) }),
  ]);
}

/**
 * O filtro da lista, que é o que os dois números do topo põem no URL.
 *
 * `hoje` e não `confirmadas`: o segundo número conta as confirmadas **no dia de
 * negócio corrente**, e o filtro tem de dar exactamente essas linhas. Um
 * contador no topo que não dá a lista de baixo é a primeira coisa que faz o
 * dono desconfiar do ecrã inteiro.
 */
export type EstadoPedido = "revisao" | "hoje";

/**
 * Os dois números do topo. O limiar que aqui viaja é a **hora a que o dia de
 * negócio começa**: "confirmadas hoje" conta desde essa hora e não desde a
 * meia-noite, e o ecrã mostra-a em vez de a esconder (guião §4, nº 7).
 */
export function useResumoDeRececoes(): UseQueryResult<ResumoDeRececoes> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_RECECOES, { resumo: true }),
    queryFn: ({ signal }) => apiRequest(CAMINHO_RESUMO, resumoDeRececoesSchema, { signal }),
  });
}

/**
 * A lista de receções, **já ordenada pelo servidor**: o que precisa de revisão
 * primeiro, depois o mais recente. O cliente não reordena, como em todos os
 * outros ecrãs — uma segunda definição de "primeiro" divergiria desta.
 *
 * Devolve a página inteira, com o `count`, e não só as linhas: o servidor
 * pagina a 50 e um mês de faturas passa disso.
 */
export function useRececoes(estado?: EstadoPedido): UseQueryResult<Paginated<Rececao>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_RECECOES, { estado }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_RECECOES, paginated(rececaoSchema), { query: { estado }, signal }),
  });
}

/**
 * Uma receção, pelo `id` — **o recurso, e não uma linha escolhida da lista**
 * (ADR 0034, adenda de 29, decisão 17).
 *
 * `GET /receipts/<id>`, que **existe desde a fatia 2** e é o `retrieve` desta
 * mesma classe no servidor. O que aqui estava escrito — *"não há
 * `GET /receipts/<id>`"* — era falso, e era o defeito: este hook pedia a lista
 * **sem filtro** e escolhia o documento com um `find()`, logo com a página a 50
 * a 51.ª receção abria a dizer que não existe. Como a lista vem por
 * `-received_at`, a que não se alcançava era a **mais antiga** — precisamente a
 * que ficou por rever, e a que o contador de "por rever" do topo conta.
 *
 * O docstring anterior citava a decisão do `useArtigoEmStock` como precedente;
 * essa decisão foi revogada pela mesma adenda, e foi essa citação que trouxe
 * este caminho para dentro do âmbito: corrigir um e deixar o outro não era meia
 * correcção — era deixar um comentário a invocar uma decisão morta sobre o
 * mesmo defeito.
 *
 * **Dois estados e não três**: a receção é legível neste estabelecimento
 * (`200`), ou não é — nunca existiu, era rascunho e foi apagada, ou é de outra
 * casa (`404`). Não há aqui o vazio do `never_stocked` do `inventory`, e não é
 * por simetria que se escolhe: ali quem sabia que o artigo existia era o
 * `catalog`, aqui a linha **é** a receção e não há segundo dono a quem
 * perguntar. O ecrã trata o `404` **antes** do erro genérico, senão o `detail`
 * do DRF é o que aparece a quem está ao lado de uma palete.
 */
export function useRececao(rececao: string): UseQueryResult<Rececao> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.detail(tenant, RECURSO_RECECOES, rececao),
    queryFn: ({ signal }) =>
      apiRequest(`${CAMINHO_RECECOES}/${rececao}`, rececaoSchema, { signal }),
  });
}

/**
 * O corpo do `GET /receipts/<id>/lines`: a contagem e as linhas, e **mais
 * nada**.
 *
 * Não é um envelope de paginação, e a diferença não é cosmética: as linhas de
 * um documento são um todo — confirmar metade de uma fatura não quer dizer nada
 * —, logo o `LinhasOutSerializer` não serve páginas e não há `next` nem
 * `previous` para onde ir. O `paginated()` exigia os dois, o servidor nunca os
 * mandou, e a tabela de linhas **não carregava em nenhum dos três papéis** —
 * medido a 2026-10-20, com a recusa a dizer "a resposta de
 * /receipts/<id>/lines não tem a forma esperada". É a mesma falha de fundo que
 * os euros opcionais: um validador escrito à mão que não acompanhou o contrato
 * gerado (`LinhasOut` no `types.ts` tem duas chaves).
 */
const linhasDaRececaoSchema = z.object({
  count: z.number().int().nonnegative(),
  results: z.array(linhaDeRececaoSchema),
});

export type LinhasDaRececao = z.output<typeof linhasDaRececaoSchema>;

/** As linhas do documento, na ordem em que estão impressas nele. */
export function useLinhasDaRececao(rececao: string): UseQueryResult<LinhasDaRececao> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_LINHAS, { rececao }),
    queryFn: ({ signal }) =>
      apiRequest(`${CAMINHO_RECECOES}/${rececao}/lines`, linhasDaRececaoSchema, {
        signal,
      }),
  });
}

export interface LinhaParaRevisar extends RevisaoDeLinha {
  readonly rececao: string;
  readonly linha: string;
}

/**
 * A revisão humana de uma linha: o artigo, o lote, a validade, ou a decisão de
 * a deixar fora desta entrada.
 *
 * **Sem update optimista, e a razão é a mesma do `inventory`:** quem decide o
 * estado da linha é o servidor — se o lote preenchido fecha a linha, se o
 * artigo escolhido ainda exige validade, qual é o rótulo de validade daquele
 * artigo. Adivinhá-lo aqui era refazer no cliente as regras que o servidor
 * aplica, e mostrar por um instante uma linha confirmada que podia voltar atrás.
 *
 * Invalida as receções **e** as linhas, e não o ledger: rever uma linha não
 * cria movimento nenhum. Prometer ao ecrã de Stock uma mudança que não houve é
 * exactamente o que este ecrã existe para não fazer.
 */
export function useRevisarLinha() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: ({ rececao, linha, ...revisao }: LinhaParaRevisar) =>
      apiRequest(
        `${CAMINHO_RECECOES}/${rececao}/lines/${linha}/confirmation`,
        linhaDeRececaoSchema,
        {
          method: "POST",
          // Validado à saída com o mesmo schema que o servidor usa à entrada:
          // um corpo mal formado falha aqui, com o campo nomeado, em vez de
          // voltar como um 400 genérico.
          body: revisaoDeLinhaSchema.parse(revisao),
        },
      ),
    onSuccess: async () => {
      await invalidarRececoes(queryClient, tenant);
    },
  });
}

export interface TemperaturaPedida {
  readonly rececao: string;
  readonly conservation: "chilled" | "frozen";
  readonly celsius: string;
}

/** A temperatura à entrega. Um registo da receção; não é um movimento. */
export function useRegistarTemperatura() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: ({ rececao, conservation, celsius }: TemperaturaPedida) =>
      apiRequest(`${CAMINHO_RECECOES}/${rececao}/temperature`, rececaoSchema, {
        method: "POST",
        body: temperaturaSchema.parse({ conservation, celsius }),
      }),
    onSuccess: async () => {
      await invalidarRececoes(queryClient, tenant);
    },
  });
}

/**
 * Confirmar a receção: é **aqui**, e só aqui, que a mercadoria entra no stock.
 *
 * Cada linha confirmada gera um movimento de entrada no ledger com o lote e a
 * validade que alguém escreveu; as linhas que ficaram por rever ou de fora não
 * geram nada. Não há update optimista e não há forma de desfazer: um movimento
 * é append-only na própria base de dados (ADR 0006, `REVOKE UPDATE, DELETE` em
 * `inventory_stockmovement`), e mostrar o resultado antes de ele existir seria
 * mostrar um stock que pode nunca ter acontecido.
 *
 * Invalida as receções e, pelo `useInvalidarLedger`, tudo o que depende do
 * ledger. Sem a segunda metade, o ecrã de Stock continuava a mostrar o nível de
 * antes da entrega — e é precisamente essa mudança que prova que a confirmação
 * humana é o que cria stock.
 */
export function useConfirmarRececao() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();
  const invalidarLedger = useInvalidarLedger();

  return useMutation({
    // Sem corpo: confirmar é um ato, não um formulário. O que havia para
    // escrever foi escrito linha a linha, e é isso que está a ser confirmado.
    mutationFn: (rececao: string) =>
      apiRequest(`${CAMINHO_RECECOES}/${rececao}/confirmation`, rececaoSchema, {
        method: "POST",
      }),
    onSuccess: async () => {
      await Promise.all([invalidarRececoes(queryClient, tenant), invalidarLedger()]);
    },
  });
}

/** Criar uma receção a partir de um documento ou à mão. */
export function useCriarRececao() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (pedido: RececaoParaCriar) =>
      apiRequest(CAMINHO_RECECOES, rececaoSchema, {
        method: "POST",
        body: rececaoParaCriarSchema.parse(pedido),
      }),
    onSuccess: async () => {
      await invalidarRececoes(queryClient, tenant);
    },
  });
}

/** Rever o cabeçalho de uma receção (zona da pessoa). */
export function useReverCabecalho() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: ({ id, ...revisao }: CabecalhoParaRever & { id: string }) =>
      apiRequest(`${CAMINHO_RECECOES}/${id}`, rececaoSchema, {
        method: "PATCH",
        body: cabecalhoParaReverSchema.parse(revisao),
      }),
    onSuccess: async () => {
      await invalidarRececoes(queryClient, tenant);
    },
  });
}

/** Apagar uma receção em rascunho. */
export function useApagarRascunho() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (id: string) =>
      apiRequest(`${CAMINHO_RECECOES}/${id}`, z.void(), {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await invalidarRececoes(queryClient, tenant);
    },
  });
}

/** Adicionar uma linha à mão numa receção. */
export function useAdicionarLinha() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: ({ id, ...linha }: LinhaParaCriar & { id: string }) =>
      apiRequest(`${CAMINHO_RECECOES}/${id}/lines`, linhaDeRececaoSchema, {
        method: "POST",
        body: linhaParaCriarSchema.parse(linha),
      }),
    onSuccess: async () => {
      await invalidarRececoes(queryClient, tenant);
    },
  });
}

/* ---------------------------------------------------------------------------
 * A tinta de um documento, para quem o desenha de fora deste módulo.
 *
 * Mesma razão, e mesmo limite, que o bloco equivalente do
 * `features/inventory/api.ts`: o ecrã Início é desde 2026-10-06 uma grelha de
 * miniaturas, e uma delas é o documento por rever. O trilho de 4px dessa linha
 * tem de ser **o mesmo** que a tabela do Receber lhe dá — um documento marcado
 * num ecrã e apagado no outro é pior do que não marcar nenhum.
 *
 * Sai uma função pura de leitura, e mais nada: nem schemas, nem componentes,
 * nem o tipo `Rececao`. Quem a chama recebe o `status` por inferência dos hooks
 * acima.
 *
 * A alternativa era o Início escrever `bg-warning` à mão, que foi o que a fila
 * de linhas fazia até aqui. Era uma segunda afirmação sobre o domínio ("um
 * documento por rever é um aviso") escrita num ecrã que não é desta feature, e
 * sobreviveria intacta ao dia em que esta decidisse outra coisa.
 * ------------------------------------------------------------------------- */
export { tintaDoTrilhoDoEstado } from "./tinta-do-estado";
