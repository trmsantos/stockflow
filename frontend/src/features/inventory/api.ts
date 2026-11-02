import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { useCallback } from "react";

import { useSessao } from "@/features/accounts/api";
import { apiRequest } from "@/lib/api/http";
import type { components } from "@/lib/api/types";
import { paginated, type Paginated } from "@/lib/api/pagination";
import { queryKeys } from "@/lib/api/query-keys";
import { tenantDaCache } from "@/lib/api/tenant";

import {
  CODIGO_CONTAGEM_FECHADA,
  CODIGO_CONTAGEM_JA_ABERTA,
  codigoDaRecusaDeContagem,
} from "./recusas-de-contagem";
import {
  alertaSchema,
  contagemDeLinhaSchema,
  contagemParaIniciarSchema,
  contagemSchema,
  desperdicioSchema,
  fechoDeContagemSchema,
  fechoParaRegistarSchema,
  linhaDeContagemSchema,
  localizacaoSchema,
  movimentoSchema,
  nivelDeStockSchema,
  nivelDoArtigoSchema,
  quebraParaRegistarSchema,
  respostaDeQuebraSchema,
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
  type Localizacao,
  type Movimento,
  type NivelDeStock,
  type NivelDoArtigo,
  type QuebraParaRegistar,
  type ResumoDeAlertas,
  type ResumoDeStock,
} from "./schemas";

/**
 * A camada de dados do módulo `inventory` — o `api.py` do frontend.
 *
 * Estava escrita na **forma final** antes de o Django existir (ADR 0008,
 * decisão 3), e a ADR 0034 cobrou a promessa: os sete recursos passaram do
 * servidor de dados falsos para o Django e **nenhum ecrã mudou de forma por
 * causa disso**. O mesmo `fetch`, o mesmo cookie de sessão, o mesmo
 * `X-Tenant-ID`, o mesmo envelope de paginação, o mesmo Zod, os mesmos `retry`
 * e `staleTime`.
 *
 * O que mudou foi o **contrato**, e está nomeado onde mudou: os três filtros do
 * Stock passaram a `WHERE` no servidor, a quebra mudou de caminho e de corpo, e
 * sete chaves de dinheiro ficam ausentes para quem não as vê.
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

/** O âmbito do resumo: a localização, e mais nada. */
export interface AmbitoDeStock {
  /** `id` da localização. Ausente = consolidado, todas as localizações. */
  readonly loja?: string | undefined;
}

/**
 * O âmbito da **lista**, que é o do resumo mais os dois filtros do topo.
 *
 * Os três são `WHERE` no servidor desde a ADR 0034 (decisão 2), e isso corrigiu
 * um defeito a sério: o ecrã filtrava `?q=` e `?filtro=` em JavaScript sobre os
 * `results`, logo com paginação a 50 procurava **só nas 50 piores linhas** e
 * calava as outras em silêncio — e porque a ordem é "o pior primeiro",
 * calava-as exactamente onde ninguém nota.
 */
export interface FiltrosDeStock extends AmbitoDeStock {
  /**
   * Procura no nome curto.
   *
   * **Perdeu os acentos na mudança, e isso é uma dívida do servidor.** O
   * `filtrar()` que vivia no ecrã normalizava o termo *e* o nome (`NFD` +
   * remover diacríticos), com o caso de uso escrito por extenso: *"quem procura
   * «acucar» tem de encontrar «Açúcar»"*. O servidor faz `icontains`, que ignora
   * a caixa e **não** ignora os acentos — medido: `?q=manteiga` e `?q=MANTEIGA`
   * dão a linha, `?q=acucar` dá zero e `?q=açúcar` dá uma.
   *
   * Não se repõe aqui, e a razão é a mesma que mandou o filtro para o servidor:
   * uma normalização no cliente só alcança a página carregada, logo o artigo que
   * estivesse fora das 50 primeiras continuava invisível — a procurar com
   * acentos *e* sem eles. A correcção é no `WHERE` (o `unaccent` do Postgres, ou
   * uma coluna normalizada), e até lá quem procura numa cozinha com pressa tem
   * de escrever o cedilha.
   */
  readonly q?: string | undefined;
  /** `falta` é tudo o que não está `ok`; `validade` é o que entra no limiar. */
  readonly filtro?: "falta" | "validade" | undefined;
}

/**
 * A lista do ecrã Stock, já ordenada **e já filtrada** pelo servidor ("o que
 * está pior primeiro", nunca alfabética). O cliente não reordena nem filtra:
 * uma segunda definição de "pior" ou de "em falta" divergiria da dos alertas na
 * primeira vez que o limiar mudasse.
 *
 * Devolve a **página inteira**, com o `count`, e não só as linhas: o servidor
 * pagina a 50 (`PAGE_SIZE`) e um catálogo real passa disso. Sem o total, o ecrã
 * mostrava as 50 piores e calava as outras.
 *
 * Os três filtros entram na `queryKey` porque são três perguntas diferentes ao
 * servidor — e é isso que faz voltar atrás num filtro ser instantâneo, com a
 * resposta anterior ainda em cache.
 */
export function useNiveisDeStock(
  filtros: FiltrosDeStock = {},
): UseQueryResult<Paginated<NivelDeStock>> {
  const tenant = tenantDaCache();
  const { loja, q, filtro } = filtros;

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_NIVEIS, { loja, q, filtro }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_NIVEIS, paginated(nivelDeStockSchema), {
        query: { loja, q, filtro },
        signal,
      }),
  });
}

/**
 * Um artigo em stock, pelo `id` do produto — **um recurso, e não uma linha
 * escolhida da lista** (ADR 0034, adenda de 29, decisões 12 a 16).
 *
 * `GET /stock/levels/<product_id>`. Até aqui este hook pedia a lista **sem
 * filtros** e escolhia a linha com um `find()`; com a página a 50, um artigo
 * que a procura alcança e a primeira página não contém abria a dizer que não
 * estava no stock — uma frase falsa sobre mercadoria que existe, no ecrã a
 * partir do qual se regista a quebra. O argumento que construiu aquele
 * `select` — *"o detalhe não paga um pedido que a lista já pagou"* — só é
 * verdade para quem chegou à ficha a partir da lista **sem filtros**, que é
 * exactamente o caso em que o defeito não aparecia.
 *
 * **Três estados, e o do meio é um vazio e não um erro**: o artigo tem
 * `StockLevel` (`never_stocked: false`); existe no catálogo e nunca entrou
 * (`200` com `never_stocked: true` e saldo zero); não existe neste
 * estabelecimento (`404`). O ecrã distingue os três, e o ramo do 404 vem antes
 * do ramo de erro genérico — senão o `detail` do DRF ("Não encontrado.") é o
 * que aparece a quem está numa cozinha.
 *
 * **Sem `?loja=`, e agora porque o servidor também não o aceita** (decisão 16):
 * o detalhe é sempre do estabelecimento inteiro, porque é do `by_location` que
 * se escolhe onde registar a quebra — e porque um saldo escopado a uma loja ao
 * lado de um mínimo e de um estado que são de todas lê-se como erro de cálculo.
 * O número escreve-se com o âmbito ao lado, no ecrã.
 */
export function useArtigoEmStock(produto: string): UseQueryResult<NivelDoArtigo> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.detail(tenant, RECURSO_NIVEIS, produto),
    queryFn: ({ signal }) =>
      apiRequest(`${CAMINHO_NIVEIS}/${produto}`, nivelDoArtigoSchema, { signal }),
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
 * Registar um desperdício: **um POST que cria um ou mais movimentos**.
 *
 * ## Um gesto, N linhas, e por isso a resposta é uma lista
 *
 * Uma quebra de 2 kg com o lote FEFO a 0,4 kg **reparte-se** pelos lotes
 * seguintes, por ordem de validade, numa transação e com a mesma referência
 * (ADR 0034, decisão 8). O 201 é por isso `{movements: [...]}`, sempre lista,
 * mesmo com um lote só: uma resposta que fosse objecto no caso normal e lista
 * no caso raro era um cliente que funciona até ao dia em que o lote acaba a
 * meio. Quem a lê nomeia **os lotes**, no plural, em vez de "o lote X".
 *
 * O caminho é `/stock/movements/waste` e não `/stock/movements`: o `POST` na
 * colecção deixou de existir, e os três de escrita têm cada um o seu verbo.
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
      apiRequest(`${CAMINHO_MOVIMENTOS}/waste`, respostaDeQuebraSchema, {
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
 * **As** contagens a decorrer — plural, e perguntadas ao servidor.
 *
 * Isto era um `useContagemAberta` (singular) que fazia
 * `results.find(status === "open")` sobre a primeira página da lista toda.
 * Estava certo enquanto o servidor garantia **uma** aberta por estabelecimento
 * e ficou errado de duas maneiras com a ADR 0033: assume unicidade onde a
 * exclusividade passou a ser **por localização** (a arca e a despensa são duas
 * contagens legítimas em simultâneo), e depende da paginação — bastam 50
 * contagens fechadas à frente para a aberta não vir na primeira página e o ecrã
 * dizer que não há nenhuma a decorrer.
 *
 * O `?status=open` é a correcção das duas de uma vez, e é por isso que o
 * parâmetro existe no contrato (ADR 0033, decisão 4): "as que estão a decorrer"
 * é uma **pergunta ao servidor**, não uma suposição do ecrã. Devolve a página
 * inteira e não uma escolha: **qual** delas se está a contar é do URL
 * (`?contagem=`), e um `select` aqui voltava a pôr essa decisão nesta camada.
 */
export function useContagensAbertas(): UseQueryResult<Paginated<Contagem>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_CONTAGENS, { status: "open" }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_CONTAGENS, paginated(contagemSchema), {
        query: { status: "open" },
        signal,
      }),
  });
}

/**
 * A última contagem fechada, para o ecrã mostrar o resultado de quem fechou.
 *
 * Com `?status=closed` e `results[0]`, e não com um `find` sobre a lista toda:
 * a ordem é `-started_at` do servidor, logo a primeira fechada **é** a última a
 * ter começado. Pela mesma razão de paginação de cima — com várias abertas à
 * frente, a página 1 podia não ter fechada nenhuma e o ecrã calava o resultado
 * de quem acabou de fechar.
 *
 * `null` e não `undefined` quando não há nenhuma: o ecrã tem de distinguir
 * "ainda não houve nenhuma" (não se mostra nada) de "ainda a carregar".
 */
export function useUltimaContagemFechada(): UseQueryResult<Contagem | null> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_CONTAGENS, { status: "closed" }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_CONTAGENS, paginated(contagemSchema), {
        query: { status: "closed" },
        signal,
      }),
    select: (pagina) => pagina.results[0] ?? null,
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

/**
 * Quais os papéis que **fecham** uma contagem, tipado contra o enum gerado.
 *
 * **Abrir saiu desta lista com a ADR 0033 (decisão 2), e foi a ADR 0030 que o
 * mandou.** A razão escrita lá para abrir ser restrito não era o risco da
 * escrita — era *"ocupar a única contagem aberta do estabelecimento"*. Com uma
 * contagem aberta por **localização** a escassez acabou, e a razão acabou com
 * ela; manter a restrição era conservar a consequência de uma premissa
 * revogada. Quem conta às 6h abre a localização que quiser.
 *
 * **Fechar fica**, e a razão também não é o papel: o `GET /closing` **é** a
 * decisão (diferença por linha, `loss_eur`, `gain_eur`) e o `POST` é só a
 * assinatura. Dar a assinatura a quem não pode ver a decisão não é delegar
 * responsabilidade, é retirá-la — um carimbo é pior do que a espera.
 *
 * O `Record` é a garantia e é exaustivo nos dois sentidos: se o backend ganhar
 * um quarto papel, isto não compila e alguém tem de decidir se ele fecha. Uma
 * lista de strings que por acaso coincide com a do servidor ficava em silêncio
 * nesse dia — e o silêncio aqui é um botão a aparecer a quem vai levar 403, ou
 * a desaparecer a quem podia carregar nele.
 *
 * O `Map` é por onde se lê, porque o `security/detect-object-injection` recusa —
 * e bem — um `OBJETO[chave]` com chave dinâmica. É o mesmo par do
 * `PROJECCAO_DO_PAPEL` do `reporting` e do `NOME_DO_PAPEL` do `accounts`. E o
 * tipo vem do `types.ts` (que é `@/lib/*`, usado de cima para baixo) e não do
 * `papelSchema` do `accounts`, que não atravessa a fronteira da ADR 0008.
 */
const FECHA_CONTAGENS: Record<components["schemas"]["PapelEnum"], boolean> = {
  owner: true,
  manager: true,
  staff: false,
};

const QUEM_FECHA = new Map<string, boolean>(Object.entries(FECHA_CONTAGENS));

/**
 * Quem está nesta sessão **fecha** contagens?
 *
 * **Não é autorização, e é por isso que aceita a ausência de papel.** Quem
 * autoriza é o servidor: fechar é de `owner|manager`, imposto em
 * `permission_classes`, e o `GET /closing` responde **403** a quem conta. Isto é
 * a mesma verdade usada para duas coisas de apresentação — não desenhar um
 * botão que vai dar 403, e não disparar o pedido da pré-visualização que já se
 * sabe recusado. Esconder é apresentação, não autorização (ADR 0009).
 *
 * Chamava-se `usePodeGerirContagens` e "gerir" eram duas acções; desde a ADR
 * 0033 é uma só, e o nome diz qual. A assimetria não é de ecrã: contar e abrir
 * não tocam no ledger, e **fechar escreve N movimentos irreversíveis** a partir
 * de uma pré-visualização em euros.
 *
 * Lê a **única** cache que existe, pela porta que a ADR 0008 (decisão 2) deixa
 * aberta entre features. Não faz pedido nenhum. Enquanto a sessão não chegou o
 * papel é `undefined` e a resposta é `false`: na prática é imediato, porque o
 * `beforeLoad` da rota do shell já leu a sessão antes de montar o invólucro.
 */
export function usePodeFecharContagens(): boolean {
  const sessao = useSessao();
  const papel = sessao.data?.tenant_ativo?.papel;
  return papel !== undefined && (QUEM_FECHA.get(papel) ?? false);
}

/**
 * O fecho, antes de o ser: as diferenças em quantidade e em euros, e o que fica
 * por contar. O `GET` **não escreve nada**.
 *
 * O `ativo` existe porque um hook não se chama condicionalmente e porque este
 * endpoint é de `owner|manager`: sem ele, o ecrã de quem conta disparava um
 * pedido que já se sabe que responde 403, e o 403 chegava à barra de erro de um
 * ecrã onde não há nada a corrigir. Não é controlo de acesso — é não bater numa
 * porta fechada.
 */
export function useFechoDeContagem(
  contagem: string | undefined,
  ativo: boolean,
): UseQueryResult<FechoDeContagem> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.detail(tenant, RECURSO_CONTAGENS, `${String(contagem)}:fecho`),
    queryFn: ({ signal }) =>
      apiRequest(`${CAMINHO_CONTAGENS}/${String(contagem)}/closing`, fechoDeContagemSchema, {
        signal,
      }),
    enabled: contagem !== undefined && ativo,
  });
}

/**
 * Começar a contar uma localização. É a ação do ecrã, e desde a ADR 0033 é de
 * **toda a gente**.
 *
 * **O 409 não é tratado como erro, e é essa a decisão.** Só pode haver uma
 * contagem aberta **por localização** (ADR 0033, decisão 1), logo a segunda
 * tentativa sobre a mesma localização responde `contagem_ja_aberta` com o `id`
 * da que já está aberta. O que isso quer dizer, do lado de quem carregou no
 * botão, é que **a contagem que ela quer já existe** — e a reacção certa é
 * levá-la lá, não dizer "erro".
 *
 * Aqui a recusa releva a lista das abertas: o `onError` invalida as contagens e
 * a que já estava a decorrer aparece na lista do ecrã. O atalho é do ecrã, com
 * o `id` que o corpo do conflito traz (`contagemDoConflito`) — com várias
 * abertas, reler a lista deixou de bastar: ela traz três e nenhuma delas é "a"
 * contagem.
 *
 * As linhas entram na mesma invalidação porque o `POST` as materializa: uma por
 * artigo com nível não-zero naquela localização (ADR 0030, decisão 4).
 */
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
    onError: async (erro) => {
      // O conflito é informação: há uma contagem aberta que esta cache ainda não
      // viu (foi outra pessoa, noutro telemóvel). Reler é o que a faz aparecer.
      if (codigoDaRecusaDeContagem(erro) !== CODIGO_CONTAGEM_JA_ABERTA) return;
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
    onError: async (erro) => {
      // A contagem fechou debaixo dos pés de quem estava a contar — outra
      // pessoa, noutro telemóvel. O número **não entrou**, e o que o ecrã tem de
      // fazer é deixar de mostrar uma contagem a decorrer que já não decorre.
      if (codigoDaRecusaDeContagem(erro) !== CODIGO_CONTAGEM_FECHADA) return;
      await invalidarRecursos(queryClient, tenant, [RECURSO_CONTAGENS, RECURSO_LINHAS]);
    },
  });
}

/**
 * Fechar a contagem: é **aqui** que o ledger muda, com um `adjustment` por
 * diferença. Invalida tudo, porque muda tudo — níveis, números do topo,
 * histórico e alertas.
 *
 * Sem update optimista, e pela razão mais forte que existe nesta casa: os
 * movimentos são append-only na própria base de dados (ADR 0006), logo isto é
 * **irreversível** e não há nada que se desfaça se o servidor recusar. Mostrar
 * o resultado antes de ele existir era mostrar um ledger que pode nunca ter
 * acontecido.
 *
 * A `reason` vai sempre, porque o contrato a exige sempre (ADR 0030, segunda
 * ronda, nº 5) — e o `fechoParaRegistarSchema.parse` do corpo é o que faz um
 * pedido sem ela falhar **aqui**, com o campo nomeado, em vez de voltar do
 * servidor como um 400 por campo.
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
 * Localizações — o ecrã de receção precisa delas.
 * ------------------------------------------------------------------------ */

const CAMINHO_LOCALIZACOES = "/locations";
const RECURSO_LOCALIZACOES_INV = "inventory-locations";

/**
 * Lista de localizações do estabelecimento.
 */
export function useLocalizacoes(): UseQueryResult<Paginated<Localizacao>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_LOCALIZACOES_INV, {}),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_LOCALIZACOES, paginated(localizacaoSchema), { signal }),
  });
}

/**
 * Criar uma nova localização.
 */
export function useCriarLocalizacao() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (pedido: { name: string; position?: number }) =>
      apiRequest(CAMINHO_LOCALIZACOES, localizacaoSchema, {
        method: "POST",
        body: pedido,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.resource(tenant, RECURSO_LOCALIZACOES_INV),
      });
    },
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
 *    contra "perde qualidade em 2 dias". É a regra que o guião da sessão 0 §2
 *    nomeia como condição para o dono confiar nos alertas. **O tecto de cor do
 *    `best_before` deixou de ser daqui com a ADR 0034**: a gravidade vem no
 *    `severity` do lote e um DDM nunca chega a `danger` no servidor, por ser
 *    mercadoria vendável. O que fica deste lado é a palavra, porque i18n é do
 *    cliente;
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
