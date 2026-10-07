# ADR 0008 — O shell navegável: router, fronteiras do frontend e a fronteira dos dados falsos

**Contexto.** O frontend tem canalização e zero ecrãs de produto: sete primitivos shadcn, o cliente
HTTP (cookie de sessão, `X-CSRFToken`, `X-Tenant-ID`), as chaves de query com o tenant à cabeça, os
tokens e a `/dev/tokens`. Do outro lado não há um único `views.py` em `backend/apps/`: a API serve
`schema`, `docs`, `healthz`, `readyz` e o admin, não tem endpoint de domínio nenhum e não tem
autenticação. O `src/routes/router.tsx` é um `if` sobre `window.location.pathname` com um comentário
a dizer que a escolha da biblioteca é uma ADR — é esta. O que vem a seguir não é a app final nem um
protótipo descartável: é um **shell navegável com dados falsos**, e existe como instrumento para
responder às onze perguntas de domínio por confirmar com um dono de restaurante real
(`SESSION-CONTEXT.md`, parágrafo da "Sessão 0") — mostrar um ecrã em vez de perguntar no abstracto.
O layout, a navegação, os tokens e os estados são a sério; os dados por cima são mentira temporária.
Três coisas têm de estar decididas antes do primeiro ecrã, porque as três são caras de mudar depois
de haver dez: com que biblioteca se navega, onde vivem os ecrãs, e por onde entram — e sobretudo por
onde saem — os dados falsos.

**Decisão 1 — TanStack Router, com a árvore de rotas escrita em código.** A razão decisiva são os
**search params tipados e validados**. Os ecrãs que respondem às perguntas da manhã — "o que falta?",
"o que expira?" — são a mesma lista com filtros diferentes: horizonte em dias, localização,
categoria, "só abaixo do mínimo". Esse estado pertence ao URL, senão um recarregamento, o botão de
voltar e um link mostrado ao dono não reproduzem o ecrã que se estava a ver. O TanStack Router põe os
search params no tipo da rota e valida-os à entrada (`validateSearch` com um schema Zod, que já está
na stack), pelo que um URL malformado degrada para o default em vez de explodir dentro de um ecrã; o
React Router entrega `URLSearchParams`, ou seja strings, e o parse e a validação dos filtros que
*definem* o ecrã ficariam repetidos ecrã a ecrã. Segunda razão: o investimento do React Router v7 foi
para o modo framework com SSR, que esta stack nunca vai usar (SPA de Vite servida por Caddy, API
Django à parte), logo ficávamos no seu caminho menos cuidado. A árvore é **em código**, em
`src/routes/`, sem o plugin de rotas por ficheiro: um artefacto gerado-e-commitado com gate de diff
já existe (`src/lib/api/types.ts`) e um é o que basta, a árvore tem uma dezena de rotas, e a convenção
de nomes do plugin ditaria a pasta da decisão 2. Code-splitting por `lazyRouteComponent`, rota a
rota. **O mobile/desktop do DESIGN.md §4 não é um problema de routing**: é uma árvore só, um layout
raiz só, com a sidebar e a tab bar ambas no DOM e uma escondida por breakpoint (`hidden md:flex`, que
também as tira da árvore de acessibilidade). Um `useMediaQuery` daria duas árvores de componentes,
remontagens ao redimensionar e o invólucro errado no primeiro paint. A `/dev/tokens` mantém a
propriedade que já tem: a rota só entra no array de filhos dentro do ramo `import.meta.env.DEV` e o
`import()` fica dentro desse ramo, logo o Rollup continua a eliminar o chunk. **O que se perde:**
muito menos prior art (os blocos de shadcn e os tutoriais assumem React Router); um bundle maior; e um
segundo caminho de dados na API do router — loaders, preload, `staleTime` próprio — que não vamos
usar, porque o TanStack Query continua a ser a única camada de dados. Para isso não apodrecer, o
`no-restricted-syntax` do `eslint.config.js` ganha um selector contra `loader`, `loaderDeps` e
`useLoaderData`; no dia em que uma rota precisar de `ensureQueryData`, tirar o selector é um diff
visível com uma razão. Perde-se também o code-splitting automático: esquecer o `lazyRouteComponent`
manda a rota para o chunk principal em silêncio, e isto fica **nomeado e sem mecanismo**.

**Decisão 2 — `routes/` é encaminhamento, `features/` é produto, `shell/` é o invólucro.** Uma rota
é o caminho, o `validateSearch`, o `lazyRouteComponent` e as suas fronteiras de erro e de pendente —
e renderiza **um** ecrã de uma feature. Não tem JSX de produto nem busca dados; se um ficheiro de
rota passa de umas vinte linhas, a lógica está no sítio errado. Uma feature é um **domínio**, e as
pastas chamam-se como os módulos do backend (`catalog`, `inventory`, `purchasing`, `recipes`,
`accounts`, `notifications`), não como ecrãs: um ecrã é uma rota, e partilhar o vocabulário com
`backend/apps/` poupa uma tradução em cada passagem entre agentes. Dentro: `screens/` (um componente
por rota), `components/` (composições de primitivos), `hooks/`, `api.ts` (hooks de query e mutação
sobre `lib/api/http` e `query-keys`), `schemas.ts` (Zod) — o que acrescenta `screens/` à anatomia do
ARCHITECTURE.md §2. Os URLs são em português (`/stock`, `/receber`, `/contar`, `/alertas`) porque são
copy de produto; as pastas são os nomes dos módulos porque são código. O shell vive em `src/shell/`
(`AppShell`, `SidebarNav`, `TabBar`, `AppHeader`, `nav-items.ts`): não é uma feature, porque não tem
domínio, e não é `src/components/`, cuja subpasta `ui/` é do CLI do shadcn e não se edita à mão. Os
itens de navegação são **um** array — a sidebar renderiza-o todo, a tab bar renderiza os marcados
para mobile, e esses são um tipo de tupla de quatro, para que os "4 itens" do DESIGN.md §4 sejam
verificados pelo `pnpm typecheck` e não por um comentário. O shell conhece caminhos de rota, nunca
domínios. **Precisa o frontend de um equivalente ao import-linter? Sim, e por outra razão que o
backend:** lá as fronteiras protegem a integridade transacional e a extração futura, aqui protegem a
**apagabilidade** — a decisão 3 só funciona se o conjunto de sítios que toca nos dados falsos for
finito e conhecido. Não se instala ferramenta nova: quem impõe é o `no-restricted-imports` do ESLint
core, que já corre, em quatro blocos `files` do `eslint.config.js` — `src/routes/**` só importa
`@/features/*/screens/*`; `src/features/**` só importa de outra feature `@/features/*/api` (o
`api.py` do frontend), e dentro da própria feature os imports são relativos (`./components/...`),
pelo que um `@/features/…` dentro de uma feature é cross-feature por construção; `src/shell/**` não
importa `@/features/*` nem `@/routes/*`; `src/lib/**` e `src/components/**` não importam nada de
cima, que é o papel do `apps/shared`. Como qualquer gate desta casa, quem o escrever confirma-o com
uma sonda — um import proibido posto de propósito, que tem de dar exit 1 — senão são quatro blocos
de configuração que ninguém mediu. O que **não** se decide: o que acontece quando duas features
quiserem o mesmo seletor de produto. A porta pré-aprovada é `@/features/catalog/api`; se o primeiro
caso real quiser um *componente* partilhado, desce-se uma camada, e decide-se com o caso à frente.

**Decisão 3 — os dados falsos não são um módulo da app: são um backend de fixtures do servidor de
desenvolvimento.** Vivem em `frontend/fixtures/`, **fora de `src/`**, servidos por um plugin do Vite
com `apply: "serve"` que responde aos caminhos `/api/v1/…` que o Django ainda não tem e faz `next()`
em tudo o resto, caindo no proxy para o `backend` (instalado na forma pré do `configureServer`, antes
do proxy interno — a confirmar com um `curl`, não por dedução). A consequência é que o `api.ts` se
escreve na forma **final** no primeiro dia: `apiRequest("/stock/levels", paginated(stockLevelSchema))`,
a chave de `query-keys`, os defaults do `query-client`. Um ecrã não sabe que os dados são falsos
porque não há nada que ele possa saber: mesmo `fetch`, mesmo cookie, mesmo `X-Tenant-ID`, mesmo
envelope de paginação, mesmo Zod, mesmos `retry` e `staleTime`. Não existe `if (fake)` em sítio
nenhum e não existe hook para ligar depois — já está ligado. A remoção é **por recurso**: apaga-se
`frontend/fixtures/<recurso>.ts` no dia em que o endpoint existir, o middleware deixa de conhecer
aquele caminho, o `next()` leva o pedido ao Django e o ecrã não muda uma linha; quando o último
ficheiro sair, sai a pasta e a linha do plugin. **O gate, em três peças, e a primeira não é um gate —
é uma impossibilidade:** (1) o `apply: "serve"` é do Vite e não nosso, o plugin não participa em
`vite build`, e porque nada em `src/` importa `fixtures/` os dados falsos não estão no grafo de
módulos: não há artefacto de produção que os contenha, não porque alguém se lembre de os apagar, mas
porque nunca entram. O preço, dito com clareza: **não existe build do shell com dados falsos** —
mostra-se ao dono com `pnpm dev --host` num telemóvel na mesma rede, e não há URL implantável de uma
app de mentira, que é a mesma propriedade vista do outro lado. (2) `scripts/check-fixtures.mjs`, ao
lado do `check-design-tokens.mjs` e no mesmo `pnpm lint`, falha se algum ficheiro de `src/` importar
de `fixtures/`, se o plugin for registado sem `apply: "serve"`, ou se um ficheiro de fixture não
contiver a sentinela `dados-falsos-stockflow`. (3) No job `frontend` do CI, depois do `pnpm build`
que já lá corre, um `grep -r` pela sentinela em `dist/` tem de dar zero — e ganha uma segunda linha
barata, porque o `dist/` também não pode conter o texto da `/dev/tokens`, afirmação que hoje só
existe num comentário do `router.tsx`. As peças (2) e (3) falham nos dois sentidos: uma garante que
toda a mentira carrega a sentinela, a outra que a sentinela não chega ao artefacto. Se alguém ligar
um fixture à app, a sentinela viaja com ele e o CI fica vermelho. **Mutações**: o servidor de
fixtures aceita POST/PATCH e guarda o estado em memória no processo do Vite, devolvendo 201 e o
objeto criado — é por isso que os fluxos se percorrem de ponta a ponta sem cirurgia na cache, porque
a invalidação do TanStack Query funciona a sério, já que o GET seguinte devolve de facto a lista
alterada. Reiniciar o `pnpm dev` volta ao estado inicial, e isso é honesto: o shell demonstra o
fluxo, não guarda dados. **Stock é um ledger, também na mentira**: o estado em memória guarda
`StockMovement`s e deriva os níveis, e não há campo de quantidade editável em sítio nenhum. Um shell
onde se corrige um número ensina o produto errado ao dono e ao próximo agente. **Estados**: o
middleware atrasa cada resposta (uns 250 ms por default, sobreponível por caminho) e sabe devolver
`results: []` e 500, porque os estados loading/empty/error do DESIGN.md §3 são metade do que se vai
mostrar — "o que aparece quando não há nada?" é uma das perguntas. **Validação**: cada resposta de
fixture é parseada, no servidor de dev, pelo **mesmo** schema Zod de `src/features/<m>/schemas.ts`
que o cliente usa à chegada, logo um fixture que não poderia sair do endpoint real falha alto e não
há duas noções do payload. O que isto não cobre é o schema estar errado quanto ao serializer que
ainda não existe; quem apanha isso é o `pnpm gen:api` com o gate de diff do CI (ARCHITECTURE.md §5) —
e é por isso que os fixtures e os `schemas.ts` são o **rascunho do contrato** que a sessão do backend
recebe, não o contrário. **Consultar `domain-expert`, e não é formalidade**: os valores de um fixture
são afirmações de domínio (unidades, validades, CMP, linhas de fatura, consumo por receita), e um
fixture **não resolve em silêncio** nenhuma das onze perguntas abertas — onde a resposta é
desconhecida (bloquear ou avisar sem stock, `yield_factor`, a hora a que começa o dia de negócio), o
ecrã mostra as duas variantes atrás de um interruptor em `/dev/`, porque mostrar duas opções a um
dono é como a pergunta se responde.

**Alternativas.** *Routing*: React Router v7 em modo biblioteca — o maior corpo de exemplos, e o que
os blocos de shadcn assumem; rejeitado porque o seu centro de gravidade é o modo framework com SSR
que não podemos usar, e porque filtros em `URLSearchParams` são strings sem tipo nem validação.
Manter o `if` sobre `window.location.pathname`: não sobrevive a layout aninhado, links, botão de
voltar e 404. `wouter` e afins: pequenos e sem tipagem de params/search, que é a única razão para
escolher alguma coisa aqui. *Fronteiras*: features nomeadas por ecrã (`dashboard`, `listagem`) — a
primeira pergunta do dono muda o nome da pasta; um `src/pages/` com o invólucro dentro de cada página
— é assim que a sidebar e a tab bar divergem; `eslint-plugin-boundaries` ou zones do `import-x` —
dependência nova para o que o `no-restricted-imports` do core faz em quatro blocos. *Dados falsos*:
fixture no `queryFn` (`queryFn: () => produtosFixture()` no `api.ts`) — é a opção óbvia e a que o
pedido já admitia ("apagar ficheiros e ligar hooks"), rejeitada porque põe a mentira **dentro** do
grafo de módulos, e a partir daí toda a proteção é deteção (varrer o bundle, ou um build de produção
que *tem* de falhar durante seis sessões, ou um modo de exceção que alguém acaba por usar) em vez de
impossibilidade. MSW no browser — padrão da indústria e com a semântica certa, mas pede uma
dependência, um `mockServiceWorker.js` em `public/` que o `pnpm build` copia para o `dist/` e a
imagem serve (o artefacto de mentira que esta decisão existe para impedir) e um `worker.start()` no
`main.tsx`, que é a aresta de import de volta. `json-server` ou um contentor de mock à parte — um
serviço novo sem sinal nenhum da secção 7 do ARCHITECTURE.md e mais uma porta no ADR 0002. Endpoints
Django a devolver dados falsos — mistura mentira com o único sítio onde a verdade tem de ser
verificável, e passaria por migrações e RLS para servir dados inventados.

**Consequências.** Entra `@tanstack/react-router` fixado por versão exacta, e mais nada — sem
devtools do router (nem os do Query estão instalados). O `src/routes/router.tsx` e o
`src/routes/home.tsx` de hoje desaparecem, e a `HomeRoute` passa a ser a rota `/` dentro do shell.
`frontend/fixtures/` entra no `include` do `tsconfig.json`: sem isso o ESLint com `projectService`
**crasha** nesses ficheiros (exit 2, o modo de falha que o próprio `eslint.config.js` documenta) e os
fixtures deixam de ser tipados, que é exactamente o que os torna inúteis como rascunho de contrato.
O `pnpm lint` ganha um segundo script e o `eslint.config.js` ganha cinco blocos (quatro de fronteiras
e o selector contra os loaders); o `pnpm build` não muda; o job `frontend` do CI ganha a varredura do
`dist/`. **Um defeito que estas rotas trazem à superfície, e que hoje ninguém veria:** o fallback de
SPA existe (`try_files {path} /index.html`) e o catch-all do proxy também, logo um deep link funciona
— mas a regra de cache do `docker/caddy/frontend.Caddyfile` é `@html path / /index.html`, e um pedido
a `/stock` serve o `index.html` **sem** `Cache-Control: no-cache`, pelo que um deploy novo pode servir
HTML antigo a quem tinha o marcador guardado. Corrige-se na sessão que acrescenta as rotas (o matcher
passa a ser "tudo o que não é `/assets/*`") e o gate é uma linha no job `stack` do CI: `curl -I` a
uma rota profunda tem de trazer `no-cache`. O shell não tem autenticação e portanto não tem rota
protegida: o `beforeLoad` que redirecciona para o login entra com a sessão da autenticação, e é lá
que se decide o ecrã de escolha de tenant que a ADR 0007 deixou em aberto no cliente — não se decide
aqui. Esta ADR não fica superada quando os endpoints chegarem: as decisões 1 e 2 são permanentes, e a
3 termina por apagamento — no dia em que `frontend/fixtures/` não existir, fica como registo de como
se atravessou o vazio.
