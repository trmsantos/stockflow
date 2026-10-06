import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { useCallback } from "react";

import { apiRequest } from "@/lib/api/http";
import { paginated, type Paginated } from "@/lib/api/pagination";
import { queryKeys } from "@/lib/api/query-keys";
import { tenantDaCache } from "@/lib/api/tenant";

import {
  alertaSchema,
  contagemDeLinhaSchema,
  contagemParaIniciarSchema,
  contagemSchema,
  desperdicioSchema,
  fechoDeContagemSchema,
  fechoParaRegistarSchema,
  linhaDeContagemSchema,
  movimentoSchema,
  nivelDeStockSchema,
  quebraParaRegistarSchema,
  resumoDeAlertasSchema,
  resumoDeStockSchema,
  type Alerta,
  type Contagem,
  type ContagemDeLinha,
  type ContagemParaIniciar,
  type Desperdicio,
  type FechoDeContagem,
  type FechoParaRegistar,
  type LinhaDeContagem,
  type Movimento,
  type NivelDeStock,
  type QuebraParaRegistar,
  type ResumoDeAlertas,
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
const CAMINHO_CONTAGENS = "/stock/counts";
const CAMINHO_ALERTAS = "/stock/alerts";
const CAMINHO_RESUMO_DE_ALERTAS = "/stock/alerts/summary";
const CAMINHO_DESPERDICIO = "/stock/alerts/waste";

/**
 * Os recursos deste módulo na cache. São sete porque são sete endpoints com
 * ritmos diferentes de mudança, e nomeá-los separadamente é o que permite a uma
 * mutação invalidar exactamente o que ficou errado.
 */
const RECURSOS = [
  "stock-levels",
  "stock-summary",
  "stock-movements",
  "stock-counts",
  "stock-count-lines",
  "stock-alerts",
  "stock-waste",
] as const;

const [
  RECURSO_NIVEIS,
  RECURSO_RESUMO,
  RECURSO_MOVIMENTOS,
  RECURSO_CONTAGENS,
  RECURSO_LINHAS,
  RECURSO_ALERTAS,
  RECURSO_DESPERDICIO,
] = RECURSOS;

/**
 * Os recursos que mudam quando o **ledger** muda, que são todos: um movimento
 * novo muda o nível, os três números do topo, o histórico, o esperado de uma
 * contagem a meio e a lista de alertas. É uma lista só porque a alternativa —
 * cada mutação a escolher as suas chaves — é como um ecrã passa a mostrar um
 * número que já não é verdade, e aqui o número errado mandava deitar comida
 * fora.
 */
const RECURSOS_DO_LEDGER = RECURSOS;

function invalidarRecursos(
  queryClient: ReturnType<typeof useQueryClient>,
  tenant: string,
  recursos: readonly string[],
): Promise<unknown> {
  return Promise.all(
    recursos.map((recurso) =>
      queryClient.invalidateQueries({ queryKey: queryKeys.resource(tenant, recurso) }),
    ),
  );
}

/**
 * Invalidar **tudo o que depende do ledger**, para quem muda o ledger de fora
 * deste módulo.
 *
 * Existe porque o ledger não é só do `inventory`: uma receção confirmada em
 * `purchasing` cria movimentos de entrada, e a partir desse instante o nível do
 * artigo, os três números do topo, o histórico, o esperado de uma contagem a
 * meio e a lista de alertas estão todos errados na cache. A alternativa era o
 * outro módulo conhecer os nomes dos sete recursos deste — e no dia em que
 * aparecesse o oitavo, ficava um ecrã a mostrar um número que já não é verdade.
 * Aqui o número errado mandava comprar o que já tinha chegado.
 *
 * É a única coisa que este `api.ts` exporta para ser usada por outra feature, e
 * é a porta que as fronteiras do ADR 0008 (decisão 2) deixam aberta: de outro
 * módulo importa-se `@/features/inventory/api`, nunca os seus schemas nem os
 * seus componentes.
 */
export function useInvalidarLedger(): () => Promise<void> {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useCallback(async () => {
    await invalidarRecursos(queryClient, tenant, RECURSOS_DO_LEDGER);
  }, [queryClient, tenant]);
}

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
      // Todas as chaves do ledger, e todas mudam de facto: o movimento novo
      // entra no histórico, o nível do artigo passa a ser outro, os números do
      // topo contam-no, o alerta daquele lote desaparece e o esperado de uma
      // contagem a meio passa a ser outro. Invalidar o recurso inteiro (e não a
      // lista exacta) apanha a consolidada e a de cada loja de uma só vez.
      await invalidarRecursos(queryClient, tenant, RECURSOS_DO_LEDGER);
    },
  });
}

/* ---------------------------------------------------------------------------
 * Contagem física — o ecrã Contar.
 * ------------------------------------------------------------------------ */

/**
 * As contagens deste estabelecimento, da mais recente para a mais antiga.
 *
 * Não há `GET /stock/counts/aberta`: "a contagem aberta" é uma **seleção** da
 * lista, não um endpoint, e assim o ecrã que mostra a aberta e o que mostra o
 * resultado da última leem a mesma entrada de cache.
 */
export function useContagens(): UseQueryResult<Paginated<Contagem>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_CONTAGENS, {}),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_CONTAGENS, paginated(contagemSchema), { signal }),
  });
}

/**
 * A contagem aberta, ou `null` quando não há nenhuma — e `null` e não
 * `undefined`, para o ecrã distinguir "não há contagem a decorrer" (que tem uma
 * ação: começar uma) de "ainda a carregar" (que tem um skeleton).
 */
export function useContagemAberta(): UseQueryResult<Contagem | null> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_CONTAGENS, {}),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_CONTAGENS, paginated(contagemSchema), { signal }),
    select: (pagina) => pagina.results.find((contagem) => contagem.status === "open") ?? null,
  });
}

/** A última contagem fechada, para o ecrã mostrar o resultado de quem fechou. */
export function useUltimaContagemFechada(): UseQueryResult<Contagem | null> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_CONTAGENS, {}),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_CONTAGENS, paginated(contagemSchema), { signal }),
    select: (pagina) => pagina.results.find((contagem) => contagem.status === "closed") ?? null,
  });
}

/**
 * As linhas de uma contagem, **já na ordem do percurso físico** (Balcão →
 * Frigorífico → Arca → Armazém). O cliente não reordena: a ordem é a regra do
 * guião §1, e uma segunda noção dela aqui seria uma segunda regra.
 *
 * A zona entra como filtro porque está no URL: contar uma zona de cada vez é o
 * que se faz em pé, e um recarregamento tem de devolver a mesma zona.
 */
export function useLinhasDeContagem(
  contagem: string | undefined,
  zona?: string,
): UseQueryResult<Paginated<LinhaDeContagem>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_LINHAS, { contagem, zona }),
    queryFn: ({ signal }) =>
      apiRequest(`${CAMINHO_CONTAGENS}/${String(contagem)}/lines`, paginated(linhaDeContagemSchema), {
        query: { zona },
        signal,
      }),
    // Sem contagem aberta não há nada para pedir — e um pedido a
    // `/counts/undefined/lines` era um 404 a aparecer como erro de rede.
    enabled: contagem !== undefined,
  });
}

/** O fecho, antes de o ser: as diferenças em quantidade e em euros, e o limiar. */
export function useFechoDeContagem(
  contagem: string | undefined,
): UseQueryResult<FechoDeContagem> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.detail(tenant, RECURSO_CONTAGENS, `${String(contagem)}:fecho`),
    queryFn: ({ signal }) =>
      apiRequest(`${CAMINHO_CONTAGENS}/${String(contagem)}/closing`, fechoDeContagemSchema, {
        signal,
      }),
    enabled: contagem !== undefined,
  });
}

/** Começar a contar uma localização. É a ação do estado vazio do ecrã. */
export function useIniciarContagem() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (pedido: ContagemParaIniciar) =>
      apiRequest(CAMINHO_CONTAGENS, contagemSchema, {
        method: "POST",
        body: contagemParaIniciarSchema.parse(pedido),
      }),
    onSuccess: async () => {
      await invalidarRecursos(queryClient, tenant, [RECURSO_CONTAGENS, RECURSO_LINHAS]);
    },
  });
}

/**
 * A contagem vai nas **variáveis** da mutação e não num argumento do hook.
 *
 * Não é estilo: um hook não se chama condicionalmente, e quando não há contagem
 * aberta o ecrã mostra o estado vazio — com a contagem no argumento, a
 * alternativa era chamar o hook com uma string vazia e construir um caminho
 * `/counts//lines` que nunca é pedido mas existe no código.
 */
export interface LinhaParaContar extends ContagemDeLinha {
  readonly contagem: string;
}

export interface FechoPedido extends FechoParaRegistar {
  readonly contagem: string;
}

/**
 * Registar a quantidade contada de uma linha.
 *
 * **Sem update optimista, e aqui a razão é outra que no desperdício:** a
 * conversão da unidade de contagem para a unidade base é do servidor
 * (`inventory-domain` §2), logo o cliente não sabe exactamente o que vai voltar
 * no campo — adivinhá-lo era refazer no frontend a conversão que o domínio lá
 * proíbe. O que o ecrã faz é não mexer no que está escrito enquanto o pedido
 * sai, para o número não piscar.
 */
export function useRegistarContagemDeLinha() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: ({ contagem, ...linha }: LinhaParaContar) =>
      apiRequest(`${CAMINHO_CONTAGENS}/${contagem}/lines`, linhaDeContagemSchema, {
        method: "POST",
        body: contagemDeLinhaSchema.parse(linha),
      }),
    onSuccess: async (_linha, variaveis) => {
      // Contar não mexe no ledger: só o fecho o faz. O que muda é a linha, o
      // progresso do topo e as diferenças do fecho — e mais nada. Invalidar o
      // stock aqui era prometer ao ecrã de Stock uma mudança que não houve.
      await Promise.all([
        invalidarRecursos(queryClient, tenant, [RECURSO_LINHAS, RECURSO_CONTAGENS]),
        queryClient.invalidateQueries({
          queryKey: queryKeys.detail(tenant, RECURSO_CONTAGENS, `${variaveis.contagem}:fecho`),
        }),
      ]);
    },
  });
}

/**
 * Fechar a contagem: é **aqui** que o ledger muda, com um `adjustment` por
 * diferença. Invalida tudo, porque muda tudo — níveis, números do topo,
 * histórico e alertas.
 */
export function useFecharContagem() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: ({ contagem, ...fecho }: FechoPedido) =>
      apiRequest(`${CAMINHO_CONTAGENS}/${contagem}/closing`, fechoDeContagemSchema, {
        method: "POST",
        body: fechoParaRegistarSchema.parse(fecho),
      }),
    onSuccess: async (_fecho, variaveis) => {
      await Promise.all([
        invalidarRecursos(queryClient, tenant, RECURSOS_DO_LEDGER),
        queryClient.invalidateQueries({
          queryKey: queryKeys.detail(tenant, RECURSO_CONTAGENS, `${variaveis.contagem}:fecho`),
        }),
      ]);
    },
  });
}

/* ---------------------------------------------------------------------------
 * Alertas — o que expira, o que falta, quanto se deitou fora.
 * ------------------------------------------------------------------------ */

/**
 * Os três contadores do topo. Trazem o limiar de dias e a **hora a que o dia de
 * negócio começa** (a sonda da Q6), as duas coisas para o ecrã as poder mostrar
 * em vez de as esconder num painel de configurações (guião §4, nº 7).
 */
export function useResumoDeAlertas(): UseQueryResult<ResumoDeAlertas> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_ALERTAS, { resumo: true }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_RESUMO_DE_ALERTAS, resumoDeAlertasSchema, { signal }),
  });
}

/** O que está em risco: validades e faltas, **uma** lista, ordenada no servidor. */
export function useAlertas(risco?: "expira" | "falta"): UseQueryResult<Paginated<Alerta>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_ALERTAS, { risco }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_ALERTAS, paginated(alertaSchema), { query: { risco }, signal }),
  });
}

/**
 * O que foi deitado fora, desde o início do dia de negócio ou na semana. É a
 * terceira pergunta do ecrã, e a lista onde a Q6 se lê: "05:10 — Pastéis de
 * ontem, 12 un".
 */
export function useDesperdicio(
  periodo: "hoje" | "semana",
  /**
   * `false` quando a lista não está à vista. Um hook não se chama
   * condicionalmente, e sem isto a lista do desperdício era pedida em **todas**
   * as visitas ao ecrã, incluindo as em que ele só olha para os contadores —
   * numa cozinha com Wi-Fi mau, um pedido a mais é a lista que interessa a
   * chegar mais tarde.
   */
  ativo: boolean,
): UseQueryResult<Paginated<Desperdicio>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_DESPERDICIO, { periodo }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_DESPERDICIO, paginated(desperdicioSchema), {
        query: { periodo },
        signal,
      }),
    enabled: ativo,
  });
}

/* ---------------------------------------------------------------------------
 * A leitura de uma linha, para quem a desenha de fora deste módulo.
 *
 * ## Porque é que isto atravessa a fronteira, e o que **não** atravessa
 *
 * A porta do ADR 0008 (decisão 2) é este ficheiro, e até 2026-10-06 só saía por
 * ela um hook (`useInvalidarLedger`) — "o que viaja entre módulos são hooks, não
 * a forma do payload". Continua a sair só isso: o que se acrescenta aqui são
 * **funções puras de leitura**, não schemas, não componentes e não tipos de
 * payload. Quem as chama recebe o tipo por inferência dos hooks acima, logo
 * nenhum ecrã de outro módulo passa a importar a forma do `Alerta`.
 *
 * A razão é o ecrã Início, que desde 2026-10-06 é uma **grelha de miniaturas**
 * dos ecrãs: as três piores linhas de validade, as três piores faltas, as três
 * piores linhas de stock. São linhas a sério — nome, quantidade, a frase da
 * validade e o trilho de 4px — e cada uma dessas quatro coisas tem exactamente
 * **uma** definição nesta casa:
 *
 *  - `textoDeQuantidade` decide as casas decimais pela unidade (o menor dígito
 *    visível é a unidade base). Uma segunda cópia escrevia "1500,000 g";
 *  - `leituraDaValidade` é a distinção `use_by`/`best_before` — "expira hoje"
 *    contra "perde qualidade em 2 dias" — e o tecto de cor do `best_before`. É a
 *    regra que o guião da sessão 0 §2 nomeia como condição para o dono confiar
 *    nos alertas, e a última coisa nesta casa que pode ter duas versões;
 *  - os dois `tintaDoTrilho*` são a cor do sinal, e a miniatura tem de dar
 *    exactamente a mesma que a tabela que ela previsualiza. Uma linha marcada no
 *    Início e apagada nos Alertas é pior do que uma linha sem marca nenhuma.
 *
 * A alternativa era copiar as quatro para o `reporting` — foi o que o
 * `purchasing/vocabulario.ts` fez com o `textoDeQuantidade`, e lá o argumento
 * era outro: aquele módulo tem **as suas** quantidades, vindas do seu contrato.
 * Aqui não: o Início desenha as linhas **deste** módulo.
 * ------------------------------------------------------------------------- */
export { leituraDe as leituraDaValidade } from "./leitura-da-validade";
export { tintaDoTrilhoDoNivel } from "./leitura-da-validade";
export { tintaDoTrilhoDeGravidade } from "./tinta-do-estado";
export { textoDeQuantidade } from "./vocabulario";
