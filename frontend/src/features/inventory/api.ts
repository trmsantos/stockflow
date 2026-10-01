import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";

import { apiRequest } from "@/lib/api/http";
import { paginated, type Paginated } from "@/lib/api/pagination";
import { queryKeys } from "@/lib/api/query-keys";
import { tenantDaCache } from "@/lib/api/tenant";

import {
  movimentoSchema,
  nivelDeStockSchema,
  quebraParaRegistarSchema,
  resumoDeStockSchema,
  type Movimento,
  type NivelDeStock,
  type QuebraParaRegistar,
  type ResumoDeStock,
} from "./schemas";

/**
 * A camada de dados do módulo `inventory` — o `api.py` do frontend.
 *
 * Está escrita na **forma final** (ADR 0008, decisão 3). Não há `if (fake)`,
 * não há hook para ligar depois e não há um segundo caminho para dados reais:
 * em desenvolvimento quem responde a estes caminhos é o servidor de fixtures do
 * Vite, e no dia em que o Django os servir não muda uma linha aqui nem nos
 * ecrãs. Mesmo `fetch`, mesmo cookie de sessão, mesmo `X-Tenant-ID`, mesmo
 * envelope de paginação, mesmo Zod, mesmos `retry` e `staleTime`.
 *
 * Os ecrãs não chamam `apiRequest` nem conhecem caminhos: usam os hooks daqui.
 */

const CAMINHO_NIVEIS = "/stock/levels";
const CAMINHO_RESUMO = "/stock/summary";
const CAMINHO_MOVIMENTOS = "/stock/movements";

/**
 * Os recursos deste módulo na cache. São três porque são três endpoints com
 * ritmos diferentes de mudança, e nomeá-los separadamente é o que permite a uma
 * mutação invalidar exactamente o que ficou errado.
 */
const RECURSOS = ["stock-levels", "stock-summary", "stock-movements"] as const;

const [RECURSO_NIVEIS, RECURSO_RESUMO, RECURSO_MOVIMENTOS] = RECURSOS;

/** O que a lista e o resumo partilham: o âmbito de localização. */
export interface AmbitoDeStock {
  /** `id` da localização. Ausente = consolidado, todas as localizações. */
  readonly loja?: string | undefined;
}

/**
 * A lista do ecrã Stock, já ordenada **pelo servidor** ("o que está pior
 * primeiro", nunca alfabética). O cliente não reordena: uma segunda definição
 * de "pior" divergiria da dos alertas na primeira vez que o limiar mudasse.
 *
 * Devolve a **página inteira**, com o `count`, e não só as linhas: o servidor
 * pagina a 50 (`PAGE_SIZE`) e um catálogo real passa disso. Sem o total, o ecrã
 * mostrava as 50 piores e calava as outras — e porque a ordem é "o que está
 * pior primeiro", calava-as exactamente onde ninguém ia notar.
 */
export function useNiveisDeStock(
  ambito: AmbitoDeStock = {},
): UseQueryResult<Paginated<NivelDeStock>> {
  const tenant = tenantDaCache();
  const { loja } = ambito;

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_NIVEIS, { loja }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_NIVEIS, paginated(nivelDeStockSchema), { query: { loja }, signal }),
  });
}

/**
 * Um artigo da lista, escolhido pelo `id` do produto.
 *
 * Não há `GET /stock/levels/<id>`: a projeção por artigo é a lista, e o detalhe
 * seleciona-a da **mesma** entrada de cache que o ecrã de Stock consolidado já
 * tem — logo voltar atrás e abrir outro artigo não refaz pedido nenhum. Sem
 * `?loja=`, de propósito: o detalhe mostra o artigo em todas as localizações,
 * porque é de uma delas que se vai registar o desperdício.
 */
export function useArtigoEmStock(produto: string): UseQueryResult<NivelDeStock | null> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_NIVEIS, { loja: undefined }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_NIVEIS, paginated(nivelDeStockSchema), { signal }),
    // `null` e não `undefined`: um `select` que devolve `undefined` deixa o
    // `data` indistinguível de "ainda a carregar", e o ecrã perdia a diferença
    // entre "o artigo não existe" e "espera".
    select: (pagina) => pagina.results.find((linha) => linha.product === produto) ?? null,
  });
}

/**
 * Os três números do topo. Vêm do servidor — incluindo o limiar de dias, que
 * viaja com o número para o ecrã o poder **mostrar** em vez de o esconder num
 * painel de configurações (guião da sessão 0, §4).
 */
export function useResumoDeStock(ambito: AmbitoDeStock = {}): UseQueryResult<ResumoDeStock> {
  const tenant = tenantDaCache();
  const { loja } = ambito;

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_RESUMO, { loja }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_RESUMO, resumoDeStockSchema, { query: { loja }, signal }),
  });
}

/** O ledger de um artigo, do mais recente para o mais antigo. */
export function useMovimentosDoArtigo(produto: string): UseQueryResult<Paginated<Movimento>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_MOVIMENTOS, { artigo: produto }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_MOVIMENTOS, paginated(movimentoSchema), {
        query: { artigo: produto },
        signal,
      }),
  });
}

/**
 * Registar um desperdício: **um POST que cria um movimento**, e nada mais.
 *
 * Não há update optimista, e não é por descuido. Um movimento é append-only na
 * própria base de dados (ADR 0006: `REVOKE UPDATE, DELETE` em
 * `inventory_stockmovement`), logo esta ação não é reversível e não há nada que
 * se possa desfazer se o servidor recusar — mostrar o resultado antes de ele
 * existir seria mostrar um ledger que pode nunca ter acontecido. O que se faz é
 * invalidar e deixar o servidor dizer o novo nível: é também ele que decide se
 * o resultado ficou `negativo`, e é esse veredicto que o ecrã mostra.
 */
export function useRegistarDesperdicio() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (quebra: QuebraParaRegistar) =>
      apiRequest(CAMINHO_MOVIMENTOS, movimentoSchema, {
        method: "POST",
        // Validado à saída com o mesmo schema que o servidor usa à entrada: um
        // corpo mal formado falha aqui, com o campo errado nomeado, em vez de
        // voltar como um 400 genérico.
        body: quebraParaRegistarSchema.parse(quebra),
      }),
    onSuccess: async () => {
      // As três chaves, e as três mudam de facto: o movimento novo entra no
      // histórico, o nível do artigo passa a ser outro e os três números do
      // topo contam-no. Invalidar o recurso inteiro (e não a lista exacta)
      // apanha a lista consolidada e a de cada loja de uma só vez.
      await Promise.all(
        RECURSOS.map((recurso) =>
          queryClient.invalidateQueries({ queryKey: queryKeys.resource(tenant, recurso) }),
        ),
      );
    },
  });
}
