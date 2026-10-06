import {
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { useNavigate, useRouter } from "@tanstack/react-router";

import { apiRequest } from "@/lib/api/http";
import { paginated, type Paginated } from "@/lib/api/pagination";
import { queryKeys } from "@/lib/api/query-keys";
import { setActiveTenantId, tenantDaCache } from "@/lib/api/tenant";

import {
  codigoDaRecusa,
  CODIGO_CONVITE_NAO_PENDENTE,
  CODIGO_TENANT_DESCONHECIDO,
  mensagemDaRecusa,
} from "./erros";
import {
  ativacaoSchema,
  conviteCriadoSchema,
  conviteParaCriarSchema,
  conviteSchema,
  credenciaisSchema,
  escolhaDeEstabelecimentoSchema,
  nomeDoPapel,
  podeConvidar,
  sessaoSchema,
  type Ativacao,
  type Convite,
  type ConviteCriado,
  type ConviteParaCriar,
  type Credenciais,
  type EscolhaDeEstabelecimento,
  type Estabelecimento,
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
const CAMINHO_CONVITES = "/convites";

/**
 * O recurso dos convites na cache.
 *
 * **O primeiro deste módulo a levar o estabelecimento à cabeça da chave**, e é
 * a diferença que importa: os cinco endpoints de `/auth/` são
 * `tenant_scope_exempt` e a sessão vive numa chave sem tenant (com a razão
 * escrita no `query-keys.ts`); os convites são um recurso **com âmbito**, logo a
 * chave é `["t", <tenant>, "convites", ...]` como a de qualquer lista de dados.
 * Sem isso, trocar de estabelecimento no pé da sidebar mostrava os convites do
 * anterior até a revalidação chegar — e a lista de quem tem acesso a uma casa é
 * precisamente a que não se quer ver trocada.
 */
const RECURSO_CONVITES = "convites";

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

/**
 * Esquecer a sessão **e** os dados do estabelecimento — o que se faz quando a
 * sessão deixou de servir a meio (403 `sem_sessao`).
 *
 * É a regra do `fixarSessao` sem a parte de escrever: qualquer resposta que
 * mude quem ou onde se está apaga os dados de tenant. Aqui não há resposta
 * nenhuma para escrever, logo a entrada da sessão também sai.
 *
 * ## `removeQueries` e **não** `invalidateQueries`, e isto não é preferência
 *
 * Os dois portões (`routes/app.tsx` e `routes/entrar.tsx`) leem a sessão com
 * `query({ staleTime: "static" })`, que devolve o que está em cache **sempre que
 * exista** — é essa a semântica que substituiu o `ensureQueryData` deprecado.
 * Uma entrada invalidada continua a existir: com `invalidateQueries`, o
 * `/entrar` lia a sessão antiga, via `estado: "ativa"` e reencaminhava para o
 * ecrã protegido, que dava 403 outra vez — um ciclo que a pessoa experimenta
 * como "a aplicação pisca e não entra". Com `removeQueries` não há entrada, logo
 * o portão vai ao servidor e lê a verdade.
 *
 * O `setActiveTenantId(null)` é a terceira parte e não é higiene: sem ele o
 * pedido seguinte leva um `X-Tenant-ID` de uma sessão que já não existe e traz
 * um 409 por cima do 403 — dois erros para a mesma causa, e o segundo a esconder
 * o primeiro.
 */
export function esquecerSessao(queryClient: QueryClient): void {
  setActiveTenantId(null);
  queryClient.removeQueries({ queryKey: PREFIXO_DE_TENANT });
  queryClient.removeQueries({ queryKey: queryKeys.sessao() });
}

/* ---------------------------------------------------------------------------
 * Convites — os quatro endpoints com âmbito deste módulo.
 *
 * Tudo o que está abaixo desta linha é diferente do que está acima em três
 * coisas, e vale dizê-las juntas porque é o que explica a forma do código:
 *
 *  1. **têm âmbito.** São endpoints normais, com `tenant_id` na sessão e
 *     política de RLS por baixo (ADR 0010: "criar, listar e revogar convites são
 *     endpoints normais, com âmbito"). Logo levam o estabelecimento na chave de
 *     query, e um 403 `sem_sessao` aqui dispara o caminho de perda de sessão do
 *     `http.ts` — que os `/auth/` não disparam;
 *  2. **a resposta não é `SessaoOut`.** São três formas (`PaginatedConviteOutList`,
 *     `ConviteCriadoOut`, `ConviteOut`), logo não passam pelo `pedirSessao` e não
 *     sincronizam o `X-Tenant-ID`;
 *  3. **nenhuma é optimista, e a razão é a mesma para as três.** A regra da casa
 *     é "optimista só em ações reversíveis": criar emite um token que só existe
 *     nessa resposta, reenviar **roda** o token (o link anterior deixa de casar
 *     com nada) e revogar é final. Mostrar qualquer das três antes de o servidor
 *     a confirmar era mostrar um segredo que pode não existir, ou dizer que um
 *     acesso foi cortado quando não foi — que é a pior forma de falhar que uma
 *     operação de segurança tem.
 * ------------------------------------------------------------------------ */

/**
 * Quem está nesta sessão convida?
 *
 * A **mesma** verdade em dois sítios, de propósito, e nenhum deles é
 * autorização: o invólucro usa-a para esconder a entrada do menu (ADR 0009:
 * "esconder é apresentação, não autorização") e o ecrã usa-a para dizer a quem
 * chegou por deep link o que se passa, em vez de disparar um `GET /convites` que
 * já se sabe que vai dar 403. Quem autoriza é o servidor, em cada pedido.
 *
 * Medido: `GET` e `POST /api/v1/convites` com sessão de um `staff` respondem 403
 * com `detail` e **sem `code`** — logo quem lê o erro tem de ler o `code`
 * defensivamente e cair no ramo genérico, que é o que o `erros.ts` já faz.
 */
export function usePodeConvidar(): boolean {
  const sessao = useSessao();
  return podeConvidar(sessao.data?.tenant_ativo?.papel);
}

/**
 * A lista de convites do estabelecimento ativo, já ordenada **pelo servidor**
 * (mais recentes primeiro — medido).
 *
 * Devolve a **página inteira** com o `count`, e não só as linhas, pela razão que
 * o `inventory` já tinha: o servidor pagina a 50 e dizer "50 convites" como se
 * fossem todos é mentira. Aqui passar de 50 é improvável e por isso ainda mais
 * importante dizê-lo quando acontecer.
 *
 * O `ativo` existe porque um hook não se chama condicionalmente: quem não é
 * `owner` não pode listar (403 medido), e sem isto o ecrã disparava o pedido só
 * para mostrar a recusa que já sabia. Não é um controlo de acesso — é não bater
 * numa porta fechada.
 */
export function useConvites(ativo: boolean): UseQueryResult<Paginated<Convite>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_CONVITES, {}),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_CONVITES, paginated(conviteSchema), { signal }),
    enabled: ativo,
  });
}

/**
 * Invalidar a lista de convites — o recurso inteiro, não uma lista exacta.
 *
 * É sempre a mesma invalidação nas três mutações porque as três mudam a mesma
 * lista e nada mais: um convite novo entra, um reenviado muda de `expira_em`
 * (e, se estava `expirado`, de estado), um revogado muda de estado. Nada disto
 * toca no ledger, no catálogo ou na sessão — e invalidar a sessão aqui era
 * prometer uma mudança de pertenças que o convite ainda não fez (o `Membership`
 * nasce na **aceitação**, ADR 0010).
 */
function invalidarConvites(queryClient: QueryClient, tenant: string): Promise<void> {
  return queryClient.invalidateQueries({
    queryKey: queryKeys.resource(tenant, RECURSO_CONVITES),
  });
}

/**
 * Um 409 `convite_nao_pendente` não é só uma frase: é a lista a estar errada.
 *
 * O código existe para um caso concreto — o estado mudou debaixo dos pés de quem
 * tinha a página aberta (outro separador aceitou, outro dono revogou) —, logo a
 * reacção certa é **reler**, e o próprio `detail` do servidor diz-no
 * ("Recarregue a lista de convites"). Fazê-lo aqui é o que torna essa frase
 * verdadeira sem a pessoa ter de a executar: quando ela acaba de a ler, a linha
 * já mostra o estado novo e o botão que já não fazia sentido desapareceu.
 *
 * O `code` lê-se com o `codigoDaRecusa`, que devolve `null` para qualquer recusa
 * sem corpo JSON — e há-as: a recusa de **papel** é 403 sem `code` (medido). Uma
 * comparação directa com `erro.code` assumia um campo que nem sempre existe.
 */
function relerSeOEstadoMudou(queryClient: QueryClient, tenant: string, erro: unknown): void {
  if (codigoDaRecusa(erro) === CODIGO_CONVITE_NAO_PENDENTE) {
    void invalidarConvites(queryClient, tenant);
  }
}

/**
 * `POST /convites` — convidar alguém. **O token sai aqui, uma vez.**
 *
 * O corpo é validado à saída com o mesmo schema que valida o formulário: um
 * corpo mal formado falha aqui, com o campo nomeado, em vez de voltar como um
 * 400 que o ecrã tem de interpretar.
 *
 * Os ramos de recusa não são tratados aqui, e nesta mutação isso é mais do que
 * uma convenção: as recusas de criação são **erros de validação do campo
 * `email`** (ADR 0010, ponto 4) e o sítio onde elas aparecem é debaixo do input.
 * Medido: "Já existe um convite para este email neste estabelecimento. Reenvie-o
 * ou revogue-o." e "Esta pessoa já é membro deste estabelecimento." chegam as
 * duas em `{"email": [...]}` com status 400, sem `code`.
 *
 * O que sai daqui é o `ConviteCriadoOut` **inteiro**, com o `fragmento`: é o ecrã
 * que o guarda em estado de componente e compõe o link, e é a única vez que este
 * valor existe fora do servidor. Não vai para a cache de queries de propósito —
 * uma entrada de cache é uma cópia que sobrevive ao ecrã, e um segredo de uso
 * único não deve sobreviver a nada.
 */
export function useConvidar(): UseMutationResult<ConviteCriado, Error, ConviteParaCriar> {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (convite: ConviteParaCriar) =>
      apiRequest(CAMINHO_CONVITES, conviteCriadoSchema, {
        method: "POST",
        body: conviteParaCriarSchema.parse(convite),
      }),
    onSuccess: async () => {
      await invalidarConvites(queryClient, tenant);
    },
  });
}

/**
 * `POST /convites/<id>/reenviar` — **roda o token** e devolve o segredo novo.
 *
 * O nome engana e vale dizê-lo: não há email a ser enviado em sítio nenhum (ADR
 * 0010 — zero eventos, zero Celery, porque não há consumidor da outbox). O que
 * isto faz é substituir o `token_hash`, pelo que **o link anterior deixa de
 * casar com alguma coisa**. É a única operação deste ecrã que invalida algo que
 * já estava na mão de outra pessoa, e é por isso que o ecrã o diz antes.
 *
 * Aceite num convite `pendente` **ou `expirado`** — medido nos dois. Um convite
 * aceite ou revogado dá 409, e aí relê-se a lista.
 */
export function useReenviarConvite(): UseMutationResult<ConviteCriado, Error, string> {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (id: string) =>
      apiRequest(`${CAMINHO_CONVITES}/${id}/reenviar`, conviteCriadoSchema, { method: "POST" }),
    onSuccess: async () => {
      await invalidarConvites(queryClient, tenant);
    },
    onError: (erro) => {
      relerSeOEstadoMudou(queryClient, tenant, erro);
    },
  });
}

/**
 * `POST /convites/<id>/revogar` — cancelar um convite. **É final.**
 *
 * `POST` e não `DELETE`, e a linha do contrato não é cosmética: o convite não é
 * apagado, fica com `revoked_at` — "apagar um convite aceite apagaria o rasto da
 * concessão de acesso", e o `invited_by` é a única resposta persistida a "quem
 * deu acesso a esta pessoa" (ADR 0010, ponto 7). A resposta é o `ConviteOut`
 * actualizado, sem token nenhum, porque não há token novo a mostrar. Medido:
 * `DELETE /api/v1/convites/<id>` **não existe** (404).
 *
 * É **idempotente** no servidor (medido: revogar um já revogado devolve 200 e a
 * linha como está, sem escrita), o que é exactamente o que um duplo clique num
 * botão precisa. O 409 acontece só sobre um convite **aceite** — e aí a pertença
 * já existe, quem a retira é outro caminho, e revogar aqui daria a impressão de
 * ter cortado um acesso que continuava lá.
 */
export function useRevogarConvite(): UseMutationResult<Convite, Error, string> {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (id: string) =>
      apiRequest(`${CAMINHO_CONVITES}/${id}/revogar`, conviteSchema, { method: "POST" }),
    onSuccess: async () => {
      await invalidarConvites(queryClient, tenant);
    },
    onError: (erro) => {
      relerSeOEstadoMudou(queryClient, tenant, erro);
    },
  });
}

/** Um estabelecimento na forma que o invólucro mostra: o papel por extenso. */
function paraOInvolucro(estabelecimento: Estabelecimento) {
  return {
    id: estabelecimento.id,
    nome: estabelecimento.nome,
    papel: nomeDoPapel(estabelecimento.papel),
  };
}

/**
 * A sessão na forma de que o invólucro precisa: onde estou, onde mais posso
 * estar, como troco e como saio.
 *
 * ## Porque é que isto vive aqui e não no shell
 *
 * Porque o shell não conhece domínios (ADR 0008, decisão 2) e o seletor de
 * estabelecimento é do shell (DESIGN.md §4, ADR 0009). As duas coisas são
 * verdadeiras ao mesmo tempo com o shell a declarar a interface
 * (`shell/sessao-do-shell.ts`) e esta feature a satisfazê-la; quem as liga é a
 * rota, que é a única camada que pode importar as duas. Está no `api.ts` e não
 * num `hooks/` porque `api.ts` é a **porta** do módulo — o `api.py` do frontend
 * — e é a única coisa desta feature que uma rota pode importar.
 *
 * **Não leva tipo de retorno anotado**, e isso é deliberado: anotá-lo obrigava a
 * declarar aqui uma segunda cópia da interface do shell (que esta camada não
 * pode importar), e duas cópias divergem na primeira correcção. Quem verifica
 * que o que sai daqui serve o que o shell pede é o `pnpm typecheck` no sítio
 * onde os dois se encontram: `routes/app.tsx`.
 *
 * ## Duas coisas que acontecem depois de cada mutação, e porquê
 *
 * **Trocar** não navega — é o ponto todo de trocar no pé da sidebar: fica-se no
 * mesmo ecrã com os dados do outro estabelecimento. Mas chama
 * `router.invalidate()`, e isso não é zelo: as chaves de query dos ecrãs levam o
 * estabelecimento à cabeça e são calculadas **no render** (`tenantDaCache()`).
 * Sem forçar os ecrãs a renderizar outra vez, os observadores que já estão
 * montados refazem o pedido com a chave do estabelecimento **anterior** — os
 * dados que voltam são os certos (quem decide o âmbito é a sessão do servidor),
 * mas ficam guardados debaixo do nome errado, que é precisamente o que o
 * `query-keys.ts` existe para impedir.
 *
 * **Sair** navega, e tem de navegar: o `logout` devolve `SessaoOut` com
 * `estado: "anonimo"` e escreve-o na cache, mas o `beforeLoad` do shell não
 * volta a correr sozinho — sem o `navigate`, ficava-se dentro do invólucro de
 * uma sessão que já não existe, a ver dados que o pedido seguinte recusa.
 */
export function useSessaoDoShell() {
  const sessao = useSessao();
  const escolher = useEscolherEstabelecimento();
  const sair = useSair();
  const router = useRouter();
  const navegar = useNavigate();

  return {
    email: sessao.data?.utilizador?.email ?? null,
    ativo: sessao.data?.tenant_ativo === undefined || sessao.data.tenant_ativo === null
      ? null
      : paraOInvolucro(sessao.data.tenant_ativo),
    estabelecimentos: (sessao.data?.tenants ?? []).map(paraOInvolucro),
    aTrocar: escolher.isPending,
    erroDaTroca: escolher.isError ? mensagemDaRecusa(escolher.error) : null,
    trocar: (id: string) => {
      escolher.mutate(
        { tenant_id: id },
        {
          onSuccess: () => {
            void router.invalidate();
          },
        },
      );
    },
    aSair: sair.isPending,
    sair: () => {
      sair.mutate(undefined, {
        onSuccess: () => {
          void navegar({ to: "/entrar", replace: true });
        },
      });
    },
  };
}
