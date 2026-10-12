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
  type LinhaDeRececao,
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
 * Uma receção, escolhida pelo `id`.
 *
 * Não há `GET /receipts/<id>`: o cabeçalho do documento é uma **seleção** da
 * mesma entrada de cache que a lista já tem, pelo que abrir uma receção e voltar
 * atrás não refaz pedido nenhum. É a mesma decisão que o `useArtigoEmStock` do
 * módulo `inventory`, e por isso lê a lista **sem filtro** — o documento aberto
 * pode não estar no filtro que estava aplicado quando se tocou nele.
 *
 * `null` e não `undefined` quando não existe: o ecrã tem de distinguir "esta
 * receção não existe" (que tem uma saída) de "ainda a carregar" (que tem um
 * skeleton).
 */
export function useRececao(rececao: string): UseQueryResult<Rececao | null> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_RECECOES, { estado: undefined }),
    queryFn: ({ signal }) => apiRequest(CAMINHO_RECECOES, paginated(rececaoSchema), { signal }),
    select: (pagina) => pagina.results.find((linha) => linha.id === rececao) ?? null,
  });
}

/** As linhas do documento, na ordem em que estão impressas nele. */
export function useLinhasDaRececao(
  rececao: string,
): UseQueryResult<Paginated<LinhaDeRececao>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_LINHAS, { rececao }),
    queryFn: ({ signal }) =>
      apiRequest(`${CAMINHO_RECECOES}/${rececao}/lines`, paginated(linhaDeRececaoSchema), {
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
