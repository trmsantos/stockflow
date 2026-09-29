# ADR 0007 — Bootstrap de identidade sob RLS

**Contexto.** Depois da ADR 0006 a ligação que serve pedidos é o `stockflow_app` — `NOSUPERUSER`,
`NOBYPASSRLS`, dono de nenhuma tabela — e a RLS alcança-a de facto: sem âmbito de tenant, um `SELECT`
na outbox devolve zero linhas e um `INSERT` leva `new row violates row-level security policy`. A ADR
0005 diz que o `TenantMiddleware` "resolve o tenant" e só depois abre o `tenant_scope`. Mas resolver o
tenant é ler o `Membership` do utilizador autenticado, o `Membership` tem `tenant_id`, logo tem
política (CLAUDE.md: toda a tabela com `tenant_id` tem política na migração que a cria), logo a
leitura antes de o âmbito existir devolve zero linhas — e o âmbito não pode abrir antes de se saber o
tenant. O login é o mesmo problema sem disfarce: corre sem âmbito por definição e tem de encontrar um
utilizador por email. Isto não se resolve com ordem de middleware nem com disciplina, porque é
circular. O que o parte é reconhecer que o bootstrap precisa de exatamente **um** bit de informação
legível fora de âmbito — *que âmbitos é que este utilizador pode tentar* — e que tudo o resto é
verificado **dentro** do âmbito, pela política. A decisão é onde vive esse bit, quão pouco pode dizer
e o que é que ele não concede.

**Decisão.** Três tabelas, três respostas diferentes, e nenhuma delas é "confia no código".

O `accounts_tenant` **tem** política, sobre `id`:
`USING (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)`, com `ENABLE` e `FORCE`, no
`RunSQL` da migração que o cria. Sem ela, qualquer ligação autenticada lê a lista completa de clientes
com nomes e NIFs, que é a ameaça "acesso a dados de outro tenant" do SECURITY.md §1 na sua forma mais
literal. A regra do CLAUDE.md reformula-se sem se esvaziar, passando de "coluna" para "papel": *toda a
tabela de dados de um tenant tem política na migração que a cria, e o predicado compara a coluna que
identifica o tenant contra `NULLIF(current_setting('app.tenant_id', true), '')::uuid`; essa coluna é
`tenant_id` em toda a parte exceto no `accounts_tenant`, onde é `id`, porque a tabela é o tenant. As
únicas famílias sem política são os dados de referência partilhados (ADR 0005) e a identidade que tem
de ser lida antes de existir âmbito (abaixo), e ambas vivem numa lista fechada num teste.* Duas
mecânicas fazem esta política funcionar sem exceção nenhuma, e a segunda é o que torna o registo de um
tenant possível: as verificações de integridade referencial ignoram a RLS por decisão documentada do
Postgres, logo o FK `tenant_id → accounts_tenant.id` de todas as tabelas de domínio continua a validar
de dentro de um âmbito (é do tipo de afirmação que esta casa mede, e entra como asserção do teste da
migração, não como citação); e criar um tenant é gerar o UUID em Python, abrir `tenant_scope(esse
uuid)` e inserir — como não há `WITH CHECK` separado, o Postgres usa o `USING` também na escrita e
`id = app.tenant_id` é verdade.

O `accounts_user` **não** tem política, e a razão não é "não tem `tenant_id`": é que qualquer política
que lhe puséssemos precisava de uma porta para a única query que tem de correr antes de haver
identidade nenhuma, o `WHERE email = %s` do login, e uma política com uma porta para o login não é uma
política. Um utilizador pertence a vários tenants — a contabilista, o consultor, o dono que também é
gerente noutra sociedade — pelo que a tabela é global por desenho. A consequência é que o email e o
hash de qualquer utilizador são legíveis por qualquer ligação da app, e a resposta é **encolher a
tabela** em vez de fingir que está protegida: `accounts_user` tem `email` (que é o `USERNAME_FIELD`),
password, `is_active`, `last_login`, segredo TOTP e `is_staff`, e mais nada. O nome exibido, o
telefone e o papel vivem no `accounts_membership`, que tem política — e isso é também o desenho certo,
porque a mesma pessoa é "Ana Silva (contabilidade)" num tenant e outra coisa noutro. O que fica
legível sem âmbito passa a ser um email, não um perfil. O resto fecha-se na API, que é onde tem de se
fechar: o `accounts/api.py` não expõe pesquisa de utilizadores, e o convite e o reset de password
respondem exatamente o mesmo para um email que existe e para um que não existe — sem isso, uma tabela
global com `email` único é um oráculo de enumeração de contas. O risco residual fica nomeado no
SECURITY.md §3, e o controlo que o §1 promete é entregue, para identidade, pelas políticas do
`accounts_tenant` e do `accounts_membership`: saber um email não compra nada sem um `Membership`.

O `accounts_membership` tem `tenant_id` e tem a política normal, sem disjuntos. O bit legível fora de
âmbito é `accounts_user.tenant_ids`, um `ArrayField(UUIDField)` escrito na mesma transação que
qualquer `Membership` e que espelha as pertenças **ativas**. É um índice, não uma fonte de
autorização: só propõe âmbitos. É coluna e não tabela de propósito — uma tabela de índice teria
`tenant_id` sem política, que é a forma que o gate nunca pode deixar passar; uma coluna numa tabela
que já não tem política não introduz forma nova. Não tem integridade referencial com o
`accounts_tenant`, logo um tenant apagado deixa lá um uuid morto, que se resolve num 403 ou numa
ausência no login — benigno, precisamente porque o array não concede nada.

No caminho do pedido, o `TenantMiddleware` (em `apps/accounts/`, o último do `MIDDLEWARE`, a envolver
o `get_response()`) lê o `request.user` e o `request.session["tenant_id"]` — `django_session` e
`accounts_user` não têm política, logo isto funciona sem âmbito — e abre `tenant_scope(esse id)`. A
primeira instrução dentro do âmbito, e a única antes de entregar o pedido, é **uma** query: o
`Membership` de (utilizador autenticado, âmbito), com `select_related` do `Tenant`, por um único
indexado `UniqueConstraint(user, tenant)`. Dentro do âmbito as duas políticas casam e a linha aparece;
se a sessão nomear um tenant onde o utilizador não tem `Membership` ativo, a política devolve zero
linhas e a resposta é 403 com `transaction.set_rollback(True)`. É esta inversão que resolve a
circularidade: **a sessão escolhe o âmbito, a política concede-o.** O valor que vem da sessão não é
uma credencial, é um argumento — forjá-lo escolhe um âmbito onde a query do middleware, que leva
`user_id = <o meu>` no `WHERE`, não devolve nada, e nenhuma linha do tenant alheio é lida no caminho.
E porque a verificação é por pedido e não por sessão, revogar um `Membership` deixa de funcionar no
pedido seguinte sem ninguém tocar em sessões: a sessão guarda um UUID que o utilizador já conhece, e
zero autorização. O middleware publica `request.tenant` como dataclass congelado do `accounts/api.py`
(`id`, `name`, `role`) e não como instância do modelo, para que nenhum módulo seja tentado a atravessar
relações a partir dele; é o que o `obj.tenant_id == request.tenant.id` do SECURITY.md §5 precisa, e as
classes de permissão que fazem essa comparação vivem em `accounts/permissions.py` reexportadas pelo
`accounts/api.py` — escrever a comparação à mão em nove módulos é como um deles a escreve mal.

A dispensa de âmbito é declarada na **view** (`tenant_scope_exempt`, à imagem do atributo homónimo do
`TenantTask` da ADR 0005) e não numa lista de paths nas settings: o middleware resolve o path uma vez
para o ler, e o default é ter âmbito. Uma view que não declare nada é servida com âmbito; uma que não
o consiga obter leva 403 antes de o `get_response()` correr, com um `code` estável no corpo
(`sem_sessao`, `tenant_desconhecido`) porque o `SessionAuthentication` do DRF já responde 403 a
anónimos e o frontend tem de ramificar pelo código e não pelo status. O esquecimento falha fechado, e
a lista de dispensas de hoje está fechada num teste: admin, healthcheck, login, logout, registo,
listagem de tenants e troca de tenant.

O login corre `authenticate()` (com o `AxesStandaloneBackend` à frente), depois `login()`, e só depois
o tenant. A ordem é obrigatória: o `login()` do Django roda a chave de sessão — `cycle_key()`, ou
`flush()` se a sessão anterior era de outro utilizador (SECURITY.md §5) — e escrever o `tenant_id`
antes dele perdia-o em silêncio no caminho do `flush`, deixando uma sessão autenticada sem tenant. A
seguir, o `tenant_ids` do próprio utilizador dá os candidatos e cada um é confirmado no **seu**
`tenant_scope`, uma transação curta fechada antes de abrir a seguinte (o `tenant_scope` não é
reentrante para outro tenant), e é lá que o nome do tenant é lido, porque o `accounts_tenant` tem
política. São N transações, e N é 1 para quase todos. Um candidato confirmado escreve-se na sessão;
zero candidatos é 200 com lista vazia e sessão sem tenant, e o frontend diz que a conta não está
associada a nenhum estabelecimento; vários é 200 com a lista e sem tenant ativo até haver escolha. Se
a descoberta falhar, a view faz `flush()` — nunca fica uma sessão autenticada com um tenant que não
se confirmou. Nada deste caminho lê uma tabela com política fora de âmbito, e é essa a propriedade que
fecha o caminho de leitura cross-tenant: as únicas leituras sem âmbito são `accounts_user` por `email`
(antes de haver identidade) e por `pk` (a do próprio), e nenhuma aceita um parâmetro que a possa
apontar para outro tenant.

Troca de tenant dentro da sessão: sim, há, num `POST` dispensado de âmbito que abre o `tenant_scope`
do destino, confirma o `Membership`, reescreve `session["tenant_id"]` e deixa a troca registada no
log. O `TenantScopeConflict` da ADR 0005 não é tocado — o conflito é *dentro* de um pedido e trocar de
tenant acontece **entre** pedidos; se este endpoint não fosse dispensado, o middleware teria aberto o
âmbito antigo e a chamada levantaria, que é exatamente porque a dispensa se declara na view e não se
infere. A chave de sessão não roda na troca: a rotação é um controlo de fixação ligado à autenticação
e a mesma sessão já tinha acesso à mesma conta; o que a troca precisa é de registo, não de chave nova.
O que se paga é o multi-tab — um cookie por sessão significa que a contabilista não tem o tenant A e o
B abertos em dois separadores, e trocar num muda o outro no fetch seguinte. A correção mais barata é a
que entra: o cliente manda em cada pedido o tenant que acha ativo no header `X-Tenant-ID`, o
middleware compara-o com a sessão e responde 409 se divergirem. O header **nunca** escolhe âmbito, só
pode causar 409, e é essa assimetria que o torna inofensivo.

No admin registam-se só modelos sem política — o `User` e os do Django. `Tenant` e `Membership` não
são registados, e não é "registados e vazios": uma changelist vazia é uma armadilha operacional, onde
alguém conclui que o cliente não tem dados. A não-inscrição diz a verdade. `is_staff` é para
operadores do StockFlow e nunca para clientes — um `Membership` com papel `owner` não tem relação
nenhuma com ele — e continua a exigir MFA. Acesso operacional a dados de um tenant é por comando
`manage.py` com `--tenant`, que abre `tenant_scope` explicitamente e cujo `tenant_id` sai nos logs
pelo `ContextVar`. A impersonation de suporte — com motivo, expiração e registo — é uma feature com
ADR própria, e o gatilho é o primeiro pedido de suporte que exija ver dados de um cliente; dar um
seletor de tenant ao admin seria impersonation sem registo, que é o oposto do que se quer.

**Alternativas.** Disjunto de sistema na política do `Membership` e do `Tenant`, com o login a abrir
`system_scope()` — é a alternativa mais forte, porque dispensa por completo a denormalização e usa um
primitivo que já existe. Rejeitada pelo modo de falha: põe um privilégio de leitura cross-tenant no
caminho do login, onde um `filter(user=...)` esquecido despeja a tabela de pertenças inteira, e é
dentro do `system_scope` que a rede que a RLS é deixa de estar lá; o array não tem privilégio nenhum
que se possa esquecer, e a sua falha é a oposta — propõe um âmbito que a política depois recusa. E o
`app.scope = 'system'` deixaria de ser "só a outbox" (ADR 0005), que é o argumento que a tabela
seguinte vai usar. Disjunto por utilizador (`app.user_id`) na política do `Membership`: o GUC tem de
ser definido fora do `tenant_scope`, logo ou é de sessão — e reabre exatamente a porta que a ADR 0005
fechou, um GUC que sobrevive à resposta numa ligação com `CONN_MAX_AGE = 60` — ou é uma segunda
transação por pedido, com um segundo primitivo em `apps/shared/db.py` e uma matriz de conflitos que
passa de 2×2 a 3×3; e não resolve o problema, porque com o utilizador em três tenants continua a ser
preciso alguém dizer qual, e esse alguém é a sessão. `Membership` sem política, isolado só por
`has_object_permission`: a tabela que mapeia quem trabalha onde, e que **é** a autorização, ficaria
legível entre tenants, com o controlo de base de dados retirado precisamente à tabela que decide as
outras — a inversão do "permissões por objeto **e** RLS" do SECURITY.md §1. Função `SECURITY DEFINER`
que devolva os tenants de um utilizador: é a resposta de manual, mas o `FORCE` da ADR 0006 sujeita o
`stockflow_owner` à política, pelo que a função só veria linhas se pertencesse a um role com
`BYPASSRLS` — um quarto role com o privilégio que a ADR 0006 passou uma ADR inteira a retirar, e uma
porta de bypass no esquema que a próxima pessoa alarga com um parâmetro. Chave do tenant derivada do
NIF (`uuid5`), que faria o login calcular o âmbito sem ler nada: amarra a chave primária a um valor de
negócio mutável, dá um oráculo público de "este NIF é cliente?" e obriga os 98% de utilizadores de um
só tenant a escrever o NIF no login para servir os outros 2%. NIF no formulário de login resolvido por
uma tabela NIF→id sem política: põe a lista de NIFs dos clientes de volta em aberto, que é o que a
primeira decisão fecha. Subdomínio por tenant, com o âmbito a vir do `Host`: certificado wildcard,
`ALLOWED_HOSTS` wildcard, cookie de sessão num domínio-pai (isolamento pior, não melhor) e a
contabilista autenticada em N hostnames. Tenant num header do cliente em vez da sessão: a verificação
seria a mesma, mas o âmbito de **todos** os pedidos passava a ser escolhido por quem chama, e o raio
de um defeito na verificação passa de "o login" para "tudo".

**Consequências.** O `accounts_membership` não guarda localizações: a tabela delas vive em `inventory`
e um FK de `accounts` para lá invertia o grafo de dependências (ARCHITECTURE.md §6b). O `accounts`
sabe o papel, o `inventory` sabe as localizações, numa tabela sua com `tenant_id` e política — o que
confirma a decisão de domínio já registada, localização é autorização e não política de RLS. Custo
fixo de uma query por pedido, sem cache: não há sinal da secção 7 do ARCHITECTURE.md, e a query é por
índice único. `django.contrib.postgres` entra no `INSTALLED_APPS` pelo `ArrayField`, e
`AXES_USERNAME_FORM_FIELD = "email"` entra no `base.py` ao lado do `AUTH_USER_MODEL` — sem ele o
contador por conta do axes fica com a chave a `None` e o eixo por utilizador desaparece em silêncio,
que é a mesma classe de defeito do `django-ipware` do SECURITY.md §5. Qualquer tabela de junção que
venha a carregar `tenant_id` precisa de política, e a varredura do `pg_class` apanha-a porque olha
para relações e não para modelos. **Prova, em quatro peças.** O `tests/test_rls_isolation.py` que a
ADR 0005 prometeu para este passo, agora com a forma completa: dois tenants com uma linha cada, um
utilizador de A autenticado num endpoint de *lista* nunca vê a linha de B; a sessão desse utilizador
adulterada para o uuid de B dá 403 e a query do middleware devolve zero linhas, logo nenhuma linha de
B é lida nem pelo caminho do próprio middleware; um `Membership` desativado sob uma sessão viva dá 403
no pedido seguinte; e dentro de `tenant_scope(A)` o `Tenant.objects.count()` é 1 havendo dois tenants,
e é 0 fora de qualquer âmbito. Um guarda autouse no `conftest.py`, por `connection.execute_wrapper`,
que levanta quando o SQL menciona uma relação com política e não há âmbito que a cubra — `current_tenant()` a `None` **e** sem `in_system_scope()`, ou em âmbito de sistema sobre uma relação cuja política não tem o disjunto `app.scope` (só a `outbox` o tem, ADR 0005), que é o caso em que um âmbito aberto dá aparência de legitimidade a uma leitura que devolve zero linhas: a lista vem
do `pg_policy` no arranque da sessão de testes, logo uma tabela nova entra no guarda sozinha, e é ele
que faz falhar quem puser uma leitura de tabela tenant-scoped antes do âmbito — no login, no admin ou
em qualquer view que se esqueça de declarar o que precisa. Tem um teste próprio que faz a leitura
proibida de propósito e afirma que o guarda levanta, senão um guarda quebrado ficava verde e calado. A
varredura do `test_db_roles.py` muda de "toda a tabela com coluna `tenant_id` tem `ENABLE` + `FORCE` +
política" para uma igualdade de conjuntos nos dois sentidos: as tabelas com política são exatamente as
que têm `tenant_id` mais o `accounts_tenant`, e as que não têm política são exatamente uma lista
fechada e comentada entrada por entrada (`accounts_user`, `django_*`, `auth_permission`, `axes_*` e,
mais tarde, os dados de referência partilhados) — assim uma tabela de domínio nova sem política falha,
e uma que chame à sua coluna de tenant outra coisa também falha, porque cai no complemento e não está
na lista. E um teste que afirma que o convite e o reset respondem igual para um email que existe e um
que não existe. **Dependência nomeada: consultar `domain-expert`.** O que não decido aqui é o que
acontece quando um registo apresenta um NIF que já existe (juntar-se ao tenant existente ou recusar —
e recusar diz ao candidato que aquele NIF é cliente) e a validação do NIF em si: dígito de controlo,
prefixos de pessoa coletiva, NIFs estrangeiros e o `999999990` das faturas a consumidor final. É a
conversa das faturas PT e não é minha. Já está decidido e registado que tenant = NIF (o dono de três
pastelarias é um tenant com três localizações) e que localização é autorização, não política.
