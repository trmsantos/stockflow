import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";

import { useSessao } from "@/features/accounts/api";
import { apiRequest } from "@/lib/api/http";
import { paginated, type Paginated } from "@/lib/api/pagination";
import { queryKeys } from "@/lib/api/query-keys";
import { tenantDaCache } from "@/lib/api/tenant";

import {
  receitaDetalheSchema,
  receitaParaAlterarSchema,
  receitaParaCriarSchema,
  receitaResumoSchema,
  type EstadoDaLista,
  type ReceitaDetalhe,
  type ReceitaParaAlterar,
  type ReceitaParaCriar,
  type ReceitaResumo,
} from "./schemas";

/**
 * A camada de dados do módulo `recipes` — o `api.py` do frontend.
 *
 * Quatro operações e **uma** coisa a saber sobre elas: a ficha é um documento e
 * não uma colecção (ADR 0035, decisão 4). As linhas viajam dentro do corpo, por
 * substituição total, logo não há `POST /recipes/<id>/lines` nem uma mutação por
 * linha — há `criar` e `actualizar`, cada uma com um botão de gravar.
 *
 * ## Os euros não estão aqui, e isso é a decisão
 *
 * Nenhuma função deste ficheiro sabe quem vê dinheiro. O servidor tira as cinco
 * chaves do JSON para quem não é `owner|manager` (`SemEurosParaQuemNaoVe`), os
 * schemas Zod declaram-nas `.optional().nullable()`, e quem decide **colunas** é
 * o `euros-da-ficha.ts`, a partir do payload. Um filtro por papel aqui seria uma
 * segunda definição da política, escrita onde ninguém a mantém.
 *
 * ## O que esta cache **não** sabe, e está nomeado em vez de disfarçado
 *
 * O custo de ingredientes é **derivado do stock na leitura** (decisões 2 e 3):
 * uma receção confirmada ou uma quebra registada mudam o `unit_cost` dos
 * artigos e portanto mudam o custo de todas as fichas que os usam. Essas
 * escritas vivem noutros módulos e invalidam os recursos do **ledger**
 * (`inventory.useInvalidarLedger`), que não conhece — nem deve conhecer — o
 * nome do recurso deste. O que repara a divergência é o `staleTime` de 30 s do
 * `query-client.ts`: a ficha revalida sozinha ao voltar ao ecrã.
 *
 * Fica dito porque a alternativa tem um custo real e a dívida é pequena: pôr o
 * `recipes` na lista do ledger obrigava o `inventory/api.ts` a nomear um recurso
 * de um módulo que não conhece, e a aresta certa (`recipes` a ouvir o ledger)
 * não existe no TanStack Query sem um barramento de eventos que esta casa não
 * tem. Trinta segundos num número de **gestão** — que ninguém lê a meio de um
 * turno — não é o mesmo risco que trinta segundos num saldo de stock.
 */

const CAMINHO = "/recipes";

/**
 * O recurso deste módulo na cache. **Um**, e não dois: a lista e a ficha são o
 * mesmo documento visto de duas distâncias — o `compor_ficha` do servidor é
 * literalmente o `compor_resumo` mais as linhas —, logo uma gravação invalida os
 * dois de uma vez e nunca deixa a lista a dizer "6 ingredientes" ao lado de uma
 * ficha com sete.
 */
const RECURSO = "recipes";

/** O âmbito da lista: a procura e o filtro de estado, os dois do contrato. */
export interface FiltrosDeReceitas {
  /** Casa no nome curto **ou no SKU** do acabado, por tokens, no servidor. */
  readonly q?: string | undefined;
  /** `activas` (omissão) ou `todas`. Um terceiro valor é 400, não uma lista. */
  readonly estado?: EstadoDaLista | undefined;
}

/**
 * A lista de fichas, já ordenada **e já filtrada** pelo servidor: por ordem
 * alfabética do acabado, com as arquivadas no fim.
 *
 * Os dois filtros entram na `queryKey` porque são duas perguntas diferentes ao
 * servidor — e é isso que faz voltar atrás num filtro ser instantâneo, com a
 * resposta anterior ainda em cache.
 *
 * Devolve a **página inteira**, com o `count`, e não só as linhas: o servidor
 * pagina a 50 e sem o total o ecrã mostrava 50 fichas como se fossem todas. A
 * procura é um `WHERE` e não um `filter()` sobre os `results` — é a lição que a
 * ADR 0034 cobrou no Stock, onde procurar dentro da página calava em silêncio
 * tudo o que estivesse fora dela.
 */
export function useReceitas(
  filtros: FiltrosDeReceitas = {},
): UseQueryResult<Paginated<ReceitaResumo>> {
  const tenant = tenantDaCache();
  const { q, estado } = filtros;

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO, { q, estado }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO, paginated(receitaResumoSchema), { query: { q, estado }, signal }),
  });
}

/**
 * Uma ficha, pelo `id` — **um recurso, e não uma linha escolhida da lista**.
 *
 * `GET /recipes/<id>`. Escolher a linha da lista com um `find()` era o defeito
 * que a ADR 0034 fechou no detalhe do artigo: com a página a 50, uma ficha que a
 * procura alcança e a primeira página não contém abria a dizer que não existe.
 *
 * Uma ficha **inactiva** responde 200 e nunca 404 (decisão 7): mercadoria que
 * existiu continua auditável, e é por isso que o ecrã distingue "arquivada" de
 * "não existe".
 */
export function useReceita(receita: string): UseQueryResult<ReceitaDetalhe> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.detail(tenant, RECURSO, receita),
    queryFn: ({ signal }) =>
      apiRequest(`${CAMINHO}/${receita}`, receitaDetalheSchema, { signal }),
  });
}

/**
 * Gravar uma ficha inteira, linhas incluídas. `201` com a ficha composta.
 *
 * **Sem update optimista**, e a regra da casa é "optimista só em acções
 * reversíveis". Esta não é insegura — uma ficha corrige-se, ao contrário de um
 * movimento do ledger —, mas o que o servidor devolve **não é o que foi
 * enviado**: a fornada volta convertida para a unidade base, as quantidades
 * voltam nas duas formas, e o **custo inteiro** é calculado na leitura, a partir
 * do stock de hoje. Uma ficha optimista teria de inventar os cinco euros e as
 * três palavras do `cost_status` — isto é, inventar precisamente o número que o
 * ecrã existe para mostrar.
 *
 * O `409 receita_ja_existe` não é tratado aqui: traz o `id` da ficha que já
 * existe e a reacção é **de ecrã** (um botão que leva lá), não de cache. Ver o
 * `recusas-de-receita.ts`.
 */
export function useCriarReceita() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (receita: ReceitaParaCriar) =>
      apiRequest(CAMINHO, receitaDetalheSchema, {
        method: "POST",
        // Validado à saída com o mesmo schema que o servidor usa à entrada: um
        // corpo mal formado falha aqui, com o campo nomeado, em vez de voltar
        // como um 400 genérico.
        body: receitaParaCriarSchema.parse(receita),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.resource(tenant, RECURSO) });
    },
  });
}

/** O corpo do `PATCH`, com o `id` da ficha a que ele se aplica. */
export interface AlteracaoDeFicha extends ReceitaParaAlterar {
  readonly receita: string;
}

/**
 * Alterar a ficha. `lines` **ausente** não toca nas linhas; `lines` **presente**
 * substitui-as todas.
 *
 * É a única parte do contrato que não se adivinha, e é por isso que está escrita
 * aqui, no schema e na ADR. O ecrã usa as duas formas: o formulário manda
 * sempre as linhas (é um documento, grava-se inteiro) e o botão de arquivar
 * manda **só** `{is_active}` — mandar as linhas para arquivar era reescrever o
 * documento para mudar um estado, e um `PATCH` que reescreve é last-write-wins
 * em silêncio sobre o que outra pessoa gravou entretanto.
 *
 * Invalida o **recurso inteiro** e não só o detalhe: o `line_count`, o
 * `is_active` e os três euros da linha da lista mudam com a mesma gravação.
 */
export function useActualizarReceita() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: ({ receita, ...alteracao }: AlteracaoDeFicha) =>
      apiRequest(`${CAMINHO}/${receita}`, receitaDetalheSchema, {
        method: "PATCH",
        body: receitaParaAlterarSchema.parse(alteracao),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.resource(tenant, RECURSO) });
    },
  });
}

/**
 * Quem está nesta sessão escreve fichas?
 *
 * **Ler a ficha é dos três papéis** e **escrevê-la é de `owner|manager`** — a
 * assimetria da ADR 0035 (decisão 5), que é o **espelho** da das contagens: ali
 * o campo abre e o gabinete fecha; aqui o gabinete escreve a ficha e o campo
 * produz a partir dela (fatia B). Quem está na cozinha precisa das quantidades,
 * e o que lhe falta são os euros — que são uma **coluna** e não o recurso.
 *
 * Isto **não é autorização**: quem autoriza é o `ReceitaViewSet`, com 403, em
 * cada pedido. É o mesmo uso que o `usePodeConvidar` do `accounts` faz da mesma
 * verdade — esconder um botão que acabaria em 403 é apresentação (ADR 0009), e
 * mostrá-lo a quem não o pode usar é uma promessa que o servidor desmente.
 *
 * Uma **igualdade sobre dois valores**, nunca um `>=` sobre uma hierarquia: não
 * existe ordem entre papéis neste projecto, e inventá-la era responder à Q7 sem
 * ninguém ter perguntado. Enquanto a sessão não chegou, o papel é `undefined` e
 * a resposta é `false` — falhar fechado é a direcção certa.
 */
export function usePodeEscreverFicha(): boolean {
  const papel = useSessao().data?.tenant_ativo?.papel;
  return papel === "owner" || papel === "manager";
}
