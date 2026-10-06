import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { useSessao } from "@/features/accounts/api";
import { apiRequest } from "@/lib/api/http";
import { queryKeys } from "@/lib/api/query-keys";
import { tenantDaCache } from "@/lib/api/tenant";
import type { components } from "@/lib/api/types";

import {
  fechoDoMesSchema,
  resumoDoPeriodoSchema,
  seriesDoPeriodoSchema,
  type FechoDoMes,
  type Periodo,
  type ResumoDoPeriodo,
  type SeriesDoPeriodo,
} from "./schemas";

/**
 * A camada de dados do módulo `reporting` — o `api.py` do frontend.
 *
 * Três leituras e **zero escritas**, o que é a propriedade que sustenta a
 * decisão 3 da ADR 0013: o `reporting` é um módulo-sumidouro, importa os
 * `api.py` dos outros e não tem tabelas nem interface pública. Aqui isso
 * aparece como a ausência de `useMutation`: não há nada neste ficheiro que
 * possa deixar a cache de outra feature errada.
 *
 * Está escrita na **forma final** (ADR 0008, decisão 3). Em desenvolvimento
 * quem responde a estes caminhos é o servidor de fixtures do Vite; no dia em
 * que o Django os servir não muda uma linha aqui nem no ecrã.
 *
 * ## O que este ficheiro **não** faz, e quem tem de o fazer um dia
 *
 * Não observa o ledger. Um desperdício registado no ecrã Alertas muda
 * `waste_eur`, `goods_consumed_eur` e a identidade da variação de stock, e
 * nenhuma chave daqui é invalidada por isso — o que o painel tem é o
 * `staleTime` de 30s do `query-client.ts` e o `refetchOnWindowFocus`, que é
 * precisamente o momento em que alguém volta ao separador do painel depois de
 * registar uma quebra noutro.
 *
 * Fica escrito em vez de resolvido com um invalidador que ninguém chama: no dia
 * em que **este** módulo tiver uma mutação, ou em que se quiser que o Alertas
 * invalide o painel, o que entra é um `useInvalidarPainel()` exportado daqui e
 * chamado de lá — a mesma porta que o `useInvalidarLedger` do `inventory` já
 * abriu na direcção contrária, e pela mesma razão: o outro módulo não tem de
 * conhecer os nomes dos recursos deste.
 */

const CAMINHO_RESUMO = "/reporting/summary";
const CAMINHO_SERIES = "/reporting/series";
const CAMINHO_MES = "/reporting/month";

/**
 * Os três recursos deste módulo na cache, nomeados separadamente porque têm
 * ritmos diferentes: o resumo e as séries mudam com qualquer movimento do dia, o
 * mês muda quando entra um salário ou um custo fixo.
 */
const RECURSOS = ["reporting-summary", "reporting-series", "reporting-month"] as const;

const [RECURSO_RESUMO, RECURSO_SERIES, RECURSO_MES] = RECURSOS;

/**
 * O papel de quem vê, **do enum gerado** (`PapelEnum` do `types.ts`, que o
 * `pnpm gen:api` escreve a partir do `schema.yaml`).
 *
 * Não é uma união escrita à mão que por acaso coincide com a do backend, e não
 * é o `papelSchema` do `features/accounts` — esse não atravessa a fronteira do
 * ADR 0008 decisão 2 (de outra feature importa-se só o `api.ts`). O `types.ts`
 * é `@/lib/*`, o `apps/shared` do frontend, e é para ser usado de cima para
 * baixo: é o mesmo mecanismo com que o `shell/registo-de-rotas.ts` tipa o
 * `RotaId`. Se o backend ganhar um quarto papel, o `Record` abaixo não compila.
 */
export type PapelDoPainel = components["schemas"]["PapelEnum"];

/**
 * As **três projecções** do mesmo ecrã (ADR 0013, decisão 6).
 *
 * Não é "o painel do dono com uma barra escondida": são ecrãs diferentes, e é
 * por isso que isto é uma projecção e não um conjunto de booleanos. O `staff`
 * não vê painel nenhum — aterra no Início e vê a lista das perguntas da manhã,
 * que é o que ele já vê hoje; o `manager` vê o bloco de período e nada que seja
 * função de salários; o `owner` vê tudo.
 *
 * **Isto não é autorização**, e é a mesma distinção que o `podeConvidar()` do
 * `accounts` faz: quem autoriza é o servidor, com `permission_classes` na view,
 * e o `/month` responde 403 a quem não é dono. O que isto faz é não bater numa
 * porta fechada — e o 403 fica como rede para o deep link e para a pertença
 * revogada a meio da sessão, que é o caso que a ADR 0007 fez ser verificado por
 * pedido.
 */
export type Projeccao = "dono" | "encarregado" | "operacao";

/**
 * O `Record` é a **garantia** (exaustivo nos dois sentidos contra o enum
 * gerado); o `Map` é por onde se lê, porque o
 * `security/detect-object-injection` do `eslint.config.js` recusa — e bem — um
 * `OBJETO[chave]` com chave dinâmica. É o mesmo par do `NOME_DO_PAPEL` do
 * `accounts` e do `REGISTO_DE_ROTAS` do shell.
 */
const PROJECCAO_DO_PAPEL: Record<PapelDoPainel, Projeccao> = {
  owner: "dono",
  manager: "encarregado",
  staff: "operacao",
};

const PROJECCOES = new Map<string, Projeccao>(Object.entries(PROJECCAO_DO_PAPEL));

/**
 * A projecção desta sessão, ou `null` enquanto ela não chegou.
 *
 * `null` e não um default, porque os dois defaults possíveis estão errados:
 * `"dono"` dispara o `/month` de quem talvez não possa, e `"operacao"` fazia o
 * painel do dono aparecer depois de um piscar das perguntas da manhã. Na
 * prática é imediato — o `beforeLoad` da rota do shell já leu a sessão antes de
 * montar o invólucro —, e o ecrã trata o `null` como "a carregar".
 *
 * Lê a **única** cache que existe, pela porta que a ADR 0008 deixa aberta entre
 * features (`@/features/accounts/api`). Não faz pedido nenhum.
 */
export function useProjeccaoDoPainel(): Projeccao | null {
  const sessao = useSessao();
  const papel = sessao.data?.tenant_ativo?.papel;
  return papel === undefined ? null : (PROJECCOES.get(papel) ?? null);
}

/**
 * `GET /reporting/summary?period=…` — o bloco de período.
 *
 * O `ativo` existe porque um hook não se chama condicionalmente: um `staff` vê
 * as perguntas da manhã e **não** dispara este pedido, que o servidor recusaria
 * com 403 (a permissão é `OWNER, MANAGER`). Não é um controlo de acesso — é não
 * bater numa porta fechada.
 */
export function useResumoDoPeriodo(
  periodo: Periodo,
  ativo: boolean,
): UseQueryResult<ResumoDoPeriodo> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_RESUMO, { periodo }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_RESUMO, resumoDoPeriodoSchema, {
        query: { period: periodo },
        signal,
      }),
    enabled: ativo,
  });
}

/**
 * `GET /reporting/series?period=…` — a mesma janela, intervalo a intervalo.
 *
 * Chave separada da do resumo e não um campo dentro dele: são dois endpoints
 * porque o resumo carrega acima da dobra e a série é um desenho que pode
 * chegar depois. Com uma chave só, um erro na série apagava os números.
 */
export function useSeriesDoPeriodo(
  periodo: Periodo,
  ativo: boolean,
): UseQueryResult<SeriesDoPeriodo> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_SERIES, { periodo }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_SERIES, seriesDoPeriodoSchema, {
        query: { period: periodo },
        signal,
      }),
    enabled: ativo,
  });
}

/**
 * `GET /reporting/month?month=YYYY-MM` — o fecho, com salários. **Só do dono.**
 *
 * `detail(…, mes)` e não `list(…, {mes})`: um mês é um recurso identificado,
 * navegar para o mês anterior e voltar lê a mesma entrada de cache, e
 * invalidá-lo é invalidar um mês e não a família toda.
 *
 * O `ativo` é a decisão 6 da ADR 0013 a ser cumprida do lado do cliente: quem
 * não é dono **não dispara** este pedido. O 403 continua a existir e a ser a
 * autoridade — o ecrã mostra-o se ele chegar, porque pode chegar: basta a
 * pertença ser revogada com a página aberta.
 */
export function useFechoDoMes(mes: string, ativo: boolean): UseQueryResult<FechoDoMes> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.detail(tenant, RECURSO_MES, mes),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_MES, fechoDoMesSchema, { query: { month: mes }, signal }),
    enabled: ativo,
  });
}

/**
 * Os dois parâmetros do painel, re-exportados para a **rota** os validar.
 *
 * `src/routes/busca-do-painel.ts` precisa deles para o `validateSearch`, e a
 * fronteira do ADR 0008 decisão 2 só deixa uma rota importar
 * `@/features/<módulo>/screens/<ecrã>` e `@/features/<módulo>/api`. Re-exportar
 * aqui é o que evita a alternativa pior: uma segunda cópia da lista fechada dos
 * cinco períodos no ficheiro da rota, que divergiria da do contrato na primeira
 * vez que um período entrasse ou saísse.
 */
export { mesSchema, periodoSchema } from "./schemas";
export type { Periodo } from "./schemas";
