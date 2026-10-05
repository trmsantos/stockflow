import {
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { apiRequest } from "@/lib/api/http";
import { queryKeys } from "@/lib/api/query-keys";
import { setActiveTenantId } from "@/lib/api/tenant";

import { codigoDaRecusa, CODIGO_TENANT_DESCONHECIDO } from "./erros";
import {
  ativacaoSchema,
  credenciaisSchema,
  escolhaDeEstabelecimentoSchema,
  sessaoSchema,
  type Ativacao,
  type Credenciais,
  type EscolhaDeEstabelecimento,
  type Sessao,
} from "./schemas";

/**
 * A camada de dados do módulo `accounts` — o `api.py` do frontend.
 *
 * Quatro chamadas e **uma** forma de resposta (`SessaoOut`), o que torna isto o
 * `api.ts` mais simples do repositório e ao mesmo tempo o único de que a
 * navegação depende: é dele que o `beforeLoad` da ADR 0008 lê a sessão.
 *
 * ## Sem barra final, e a razão está no `urls.py` do backend
 *
 * `auth/login` e **não** `auth/login/`. Com a barra na rota do Django, um POST
 * para o caminho sem barra levava um 301 do `APPEND_SLASH` do
 * `CommonMiddleware` e o browser repetia o pedido em **GET, sem corpo** — o
 * login "falhava" com um 405 e sem nada no log que explicasse porquê. É a mesma
 * razão pela qual o `/healthz` não tem barra, e é a convenção de toda a API.
 *
 * ## `GET /auth/sessao` é também o que põe o cookie de CSRF
 *
 * A view leva `ensure_csrf_cookie`, e é isso que dispensa a ADR 0010 de ter um
 * endpoint de CSRF próprio: a SPA chama a sessão no arranque de qualquer
 * maneira. Sem esse cookie o `http.ts` **recusa-se** a enviar qualquer escrita,
 * de propósito, com um `csrf_ausente` e uma instrução — em vez de deixar sair um
 * pedido que o Django recusa com um 403 que ninguém sabe ler.
 *
 * Depois do login o cookie **muda**: o `login()` do Django faz `rotate_token`.
 * Isso é transparente para o cliente porque o `http.ts` lê o cookie a cada
 * pedido e nunca o guarda — e foi **medido** nesta sessão, com `curl`, não
 * deduzido do docstring: o valor de `csrftoken` antes e depois do
 * `POST /auth/login` é diferente, e o pedido seguinte assina com o novo.
 *
 * ## Sem update optimista em nenhuma das quatro
 *
 * A regra da casa é "optimista só em ações reversíveis", e nenhuma destas o é:
 * entrar, sair, trocar de estabelecimento e activar um convite mudam **quem** e
 * **onde** se está, e o servidor é a única autoridade sobre as duas coisas.
 * Mostrar o resultado antes de ele existir era montar o `AppShell` para uma
 * sessão que pode não ter acontecido.
 */

const CAMINHO_SESSAO = "/auth/sessao";
const CAMINHO_LOGIN = "/auth/login";
const CAMINHO_LOGOUT = "/auth/logout";
const CAMINHO_TENANT_ATIVO = "/auth/tenant-ativo";
const CAMINHO_ATIVAR = "/auth/ativar";

/**
 * Alinhar o `X-Tenant-ID` com o que a sessão diz, a cada resposta de sessão.
 *
 * Isto não é higiene: é o que faz existir, na prática, o 409
 * `tenant_divergente` que o backend implementa. Sem ela o header nunca é
 * enviado (`getActiveTenantId()` fica `null`), e o caso que ele existe para
 * apanhar — dois separadores abertos, um deles em outro estabelecimento, o
 * primeiro a mostrar dados que já não são os da sessão — passa **sem erro
 * nenhum**, com o ecrã antigo a servir dados do estabelecimento novo. Medido:
 * `GET /api/v1/convites` com um `X-Tenant-ID` de outro estabelecimento responde
 * 409 `tenant_divergente`; sem o header, responde 200 com os dados do
 * estabelecimento da sessão.
 *
 * Nota medida que vale guardar: os cinco endpoints de `/auth/` são
 * `tenant_scope_exempt`, logo **não** dão 409 nem com um header divergente — o
 * `GET /auth/sessao` com o uuid errado responde 200. O 409 é dos endpoints com
 * âmbito, que são os que mostram dados. É por isso que o header tem de estar
 * certo antes do primeiro pedido de dados, e não só antes do próximo login.
 *
 * O valor vive **em memória** e só em memória (`lib/api/tenant.ts`): guardá-lo
 * em `localStorage` é proibido pelo `SECURITY.md` §7 e criava uma segunda fonte
 * de verdade que só sabe ficar desatualizada.
 */
export function sincronizarEstabelecimentoAtivo(sessao: Sessao): Sessao {
  setActiveTenantId(sessao.tenant_ativo?.id ?? null);
  return sessao;
}

/**
 * Uma resposta de sessão, validada e **já aplicada** ao `X-Tenant-ID`.
 *
 * Único ponto de passagem das quatro chamadas, de propósito: com a
 * sincronização em cada `onSuccess` em vez de aqui, a quinta chamada que
 * aparecer esquece-a — e o sintoma (nenhum `X-Tenant-ID`, nenhum 409, dados do
 * estabelecimento errado num separador antigo) não é visível em nenhum ecrã.
 */
async function pedirSessao(
  caminho: string,
  init?: Parameters<typeof apiRequest>[2],
): Promise<Sessao> {
  return sincronizarEstabelecimentoAtivo(await apiRequest(caminho, sessaoSchema, init));
}

/**
 * A sessão: `queryOptions` e não um hook, porque tem **dois** consumidores com
 * formas diferentes de chamar.
 *
 * O `beforeLoad` da rota do shell precisa de a ler **antes** de montar qualquer
 * componente, com `queryClient.query({ ...opcoesDaSessao(), staleTime: "static" })`
 * (o `ensureQueryData` que a ADR 0010 nomeia, pelo nome que ele tem desde que
 * foi deprecado — ver `routes/app.tsx`); os ecrãs leem-na com `useSessao()`. Os
 * dois têm de usar a **mesma** chave e a mesma `queryFn`, senão são duas
 * entradas de cache e dois pedidos — e o `beforeLoad` passava a perguntar ao
 * servidor em cada navegação.
 *
 * É esta a razão pela qual a ADR 0008 pôde manter o selector do
 * `no-restricted-syntax` contra `loader`/`loaderDeps`/`useLoaderData`: o que
 * ela recusou foi a **segunda** cache do router, não ler a única que existe.
 *
 * `staleTime` é o default de 30s do `query-client.ts` e não um valor próprio: a
 * navegação dentro da app não volta a perguntar, e o `refetchOnWindowFocus`
 * (também default) relê a sessão quando alguém volta ao separador, que é o
 * momento em que ela mais provavelmente mudou noutro sítio.
 */
export function opcoesDaSessao() {
  return queryOptions({
    queryKey: queryKeys.sessao(),
    queryFn: ({ signal }) => pedirSessao(CAMINHO_SESSAO, { signal }),
  });
}

/** A sessão, para quem está dentro de um componente. */
export function useSessao(): UseQueryResult<Sessao> {
  return useQuery(opcoesDaSessao());
}

/**
 * Escrever a sessão nova na cache, depois de apagar **todos os dados de
 * estabelecimento** que lá estavam.
 *
 * **Qualquer resposta que mude quem ou onde se está apaga os dados de tenant.**
 * É uma regra e não quatro decisões, e é a forma de não ter de responder "o que
 * é que isto invalida?" em cada uma das quatro chamadas:
 *
 *  - entrar e activar um convite: a cache podia ter dados de outra conta no
 *    mesmo browser (quem sai e entra com outra conta no balcão), e a chave de
 *    query não leva o utilizador — leva o estabelecimento;
 *  - sair: nada da sessão anterior deve ficar em memória à espera do `gcTime`;
 *  - trocar de estabelecimento: as chaves do novo tenant são outras, logo não
 *    *mostraria* dados errados — mas as do anterior ficavam lá, e a regra única
 *    custa um refetch e poupa a excepção que alguém teria de justificar.
 *
 * ## `removeQueries({ queryKey: ["t"] })` e não `clear()`
 *
 * O `clear()` apagaria **também** a entrada da sessão, e isso tem um efeito
 * visível: o observador que o ecrã de entrada tem montado (`useSessao`) perde o
 * `data`, volta a `isPending` — um piscar de skeleton no instante em que a
 * pessoa acabou de entrar — e dispara um `GET /auth/sessao` a mais, por cima do
 * valor que a resposta do login acabou de trazer.
 *
 * O prefixo `["t"]` apanha **tudo** o que é dados de estabelecimento, e isso é
 * garantido por construção e não por convenção: o `query-keys.ts` só sabe
 * construir chaves `["t", tenantId, ...]`, e a única chave sem esse prefixo é a
 * da própria sessão — com a razão escrita lá.
 *
 * A ordem é apagar e depois escrever, na mesma passagem síncrona.
 */
function fixarSessao(queryClient: QueryClient, sessao: Sessao): void {
  queryClient.removeQueries({ queryKey: PREFIXO_DE_TENANT });
  queryClient.setQueryData(queryKeys.sessao(), sessao);
}

/**
 * O prefixo de toda a chave de dados de estabelecimento (`query-keys.ts`).
 *
 * Escrito aqui como uma constante e não inline para que o acoplamento seja
 * visível: se o `query-keys.ts` mudar de prefixo, é esta linha que tem de mudar
 * com ele, e o nome diz porquê.
 */
const PREFIXO_DE_TENANT = ["t"] as const;

/**
 * `POST /auth/login`.
 *
 * O corpo é validado **à saída** com o mesmo schema que descreve a entrada do
 * servidor: um corpo mal formado falha aqui, com o campo nomeado, em vez de
 * voltar como um 400 que o ecrã tem de interpretar.
 *
 * Os ramos de recusa não são tratados aqui: são do ecrã, porque é lá que a
 * frase aparece. O que este hook garante é que um sucesso deixa a cache num
 * estado em que o `beforeLoad` seguinte passa sem ir ao servidor.
 */
export function useEntrar(): UseMutationResult<Sessao, Error, Credenciais> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (credenciais: Credenciais) =>
      pedirSessao(CAMINHO_LOGIN, {
        method: "POST",
        body: credenciaisSchema.parse(credenciais),
      }),
    onSuccess: (sessao) => {
      fixarSessao(queryClient, sessao);
    },
  });
}

/**
 * `POST /auth/logout`.
 *
 * `POST` e não `GET` apesar de não levar corpo: um `GET` que fecha a sessão é
 * disparável por um `<img>` numa página qualquer, e a protecção de CSRF não se
 * aplica a métodos seguros.
 *
 * Devolve `SessaoOut` com `estado: "anonimo"` em vez de 204, o que fecha a
 * sessão com **um** pedido em vez de um POST seguido de um GET.
 */
export function useSair(): UseMutationResult<Sessao, Error, void> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => pedirSessao(CAMINHO_LOGOUT, { method: "POST" }),
    onSuccess: (sessao) => {
      fixarSessao(queryClient, sessao);
    },
  });
}

/**
 * `POST /auth/tenant-ativo` — escolher o estabelecimento da sessão.
 *
 * O `tenant_id` é **argumento e não credencial**: quem verifica a pertença é a
 * política de RLS, dentro do `tenant_scope` que o service abre. O cliente não o
 * compara com nada antes de enviar — se comparasse, haveria duas verificações e
 * uma delas acabaria por ser a única.
 *
 * O 403 `tenant_desconhecido` é um ramo normal deste caminho e não um defeito:
 * acontece a quem tinha a lista aberta quando a sua pertença foi revogada. Quem
 * o trata é o seletor, e o que faz é limpar o estabelecimento ativo e reler a
 * lista.
 */
export function useEscolherEstabelecimento(): UseMutationResult<
  Sessao,
  Error,
  EscolhaDeEstabelecimento
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (escolha: EscolhaDeEstabelecimento) =>
      pedirSessao(CAMINHO_TENANT_ATIVO, {
        method: "POST",
        body: escolhaDeEstabelecimentoSchema.parse(escolha),
      }),
    onSuccess: (sessao) => {
      fixarSessao(queryClient, sessao);
    },
    onError: (erro) => {
      // Uma escolha recusada deixa o cliente a achar que o estabelecimento é
      // um que a política não concede. Limpar o header é o que impede o pedido
      // seguinte de levar um 409 em cima do 403 que acabou de acontecer — dois
      // erros para a mesma causa, e o segundo a esconder o primeiro.
      setActiveTenantId(null);

      // E o 403 `tenant_desconhecido` quer dizer uma coisa concreta: a lista
      // que está no ecrã **já não é verdade** (uma pertença foi revogada com a
      // página aberta). Reler a sessão é o que faz o estabelecimento
      // desaparecer da lista em vez de ficar lá a dar o mesmo erro a cada
      // clique. É a única invalidação selectiva deste ficheiro, e é selectiva
      // porque não houve mudança de âmbito nenhuma a justificar esvaziar tudo.
      if (codigoDaRecusa(erro) === CODIGO_TENANT_DESCONHECIDO) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.sessao() });
      }
    },
  });
}

/**
 * `POST /auth/ativar` — aceitar um convite.
 *
 * O `fragmento` vem do `location.hash` e viaja **inteiro e opaco**: quem o
 * divide é o service. O fragmento não chega ao servidor por acidente nenhum —
 * não entra no log de acesso do proxy, não viaja em `Referer`, e um pre-fetch
 * do cliente de email não consegue queimar um token de uso único (ADR 0010). É
 * este POST que o traz.
 *
 * A activação faz `login()` no servidor e devolve `SessaoOut`, pelo que o
 * sucesso aqui é indistinguível de um login — e por isso esvazia a cache pela
 * mesma regra.
 */
export function useAtivarConvite(): UseMutationResult<Sessao, Error, Ativacao> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ativacao: Ativacao) =>
      pedirSessao(CAMINHO_ATIVAR, {
        method: "POST",
        body: ativacaoSchema.parse(ativacao),
      }),
    onSuccess: (sessao) => {
      fixarSessao(queryClient, sessao);
    },
  });
}
