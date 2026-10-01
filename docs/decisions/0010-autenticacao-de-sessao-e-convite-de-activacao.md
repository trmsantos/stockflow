# ADR 0010 — Autenticação de sessão e o convite de activação antes de existir âmbito

**Contexto.** Não há nada: zero endpoints de autenticação, `accounts` com modelos, services, selectors,
permissões e middleware e **nenhum `views.py`**. A ADR 0007 já especificou a mecânica do login com
detalhe — `authenticate()` → `login()` → descoberta de tenants pelo `User.tenant_ids`, cada candidato
confirmado no **seu** `tenant_scope`, `flush()` se a descoberta falhar, `tenant_scope_exempt` declarado
na view, códigos estáveis no corpo, troca de tenant num POST dispensado, `X-Tenant-ID` que só pode
causar 409 — e deixou em aberto o registo, o convite e o primeiro utilizador. O dono do produto pede
agora uma tela de login e **uma criação ou link de activação** para entrar na app. O ponto difícil é
um: um token de activação corre **antes de existir âmbito**, como o login, e a ADR 0007 fechou as
tabelas sem política numa lista que o `tests/test_db_roles.py` verifica por igualdade de conjuntos nos
dois sentidos. A pergunta não é "qual é a razão que escrevo ao pôr os convites nessa lista" — é se eles
têm de lá entrar.

**Decisão.** **O token nomeia o tenant, logo a tabela dos convites mantém política normal e não entra
na lista.** O link é `/ativar#<uuid-do-tenant>.<token>`, o `accounts_invitation` tem `tenant_id`,
`ENABLE`, `FORCE` e o predicado de sempre, e a view de aceitação — dispensada de âmbito, como o login —
abre `tenant_scope(uuid que vem do link)` e lê o convite **lá dentro**. É a inversão da ADR 0007 na
letra, com o link no lugar da sessão: **o link escolhe o âmbito, a política concede-o.** O uuid é
argumento e não credencial, e forjá-lo escolhe um âmbito onde nenhum `token_hash` existe. A ordem das
leituras é parte da decisão: casa-se o convite **primeiro** e só depois se lê o nome do tenant, senão um
uuid adivinhado devolvia "foste convidado para a Pastelaria Aurora" sem token nenhum.

**A diferença em relação à sessão, que obriga ao resto.** O `tenant_id` da sessão não concede nada e é
um UUID que o utilizador já conhece (ADR 0007); **o token é uma credencial ao portador** — é a única
coisa entre um estranho e um `Membership`. Logo: 32 bytes de `secrets`, guardado **só** como SHA-256
(não Argon2: o segredo tem 256 bits de entropia, não é uma password), uso único, 7 dias, revogável, e
**no fragmento do URL** — o fragmento não chega ao servidor, não entra no log de acesso do proxy e não
viaja em `Referer`; a SPA lê-o do `location.hash` e põe-no no corpo do POST. Efeito lateral que é
benefício: um pre-fetch do cliente de email não consegue queimar um token de uso único.

**Quem cria o tenant: o operador, por `manage.py`, e não há registo self-service no v1.** Três razões,
nenhuma de conveniência: a ADR 0007 deixou ao `domain-expert` o que acontece quando um registo
apresenta um NIF que já existe (e recusar diz ao candidato que aquele NIF é cliente); o NIF do tenant é
PII de pessoa singular numas vezes e exige `nif_encrypted` + `nif_hmac` com pepper, que é sessão
própria (`SECURITY.md` §3); e o `billing` é fase 3, pelo que um formulário aberto cria tenants sem
limite. O comando cria o tenant, cria o `User` com `set_unusable_password()` — o `UserManager` já diz
no docstring que é a forma certa para uma conta por convite — cria o `Invitation` com papel `owner` e
imprime o URL. Gatilho para reabrir: billing a existir, NIF encriptado e a pergunta do NIF duplicado
respondida.

**O `Membership` nasce na aceitação, não no convite**, dentro de `tenant_scope` e pelo
`conceder_pertenca`, que já escreve o `tenant_ids` na mesma transação. Password, `Membership` e
`accepted_at` vão **numa** transação dentro do âmbito: escrever no `accounts_user` de dentro de um
âmbito é já o normal e está justificado no `_espelhar` do `services.py`. **E a aceitação nunca define
password numa conta que já tem uma** — a password é global e a pertença é por tenant, pelo que
"convite + definir password" dava a quem pode convidar a tomada de uma conta existente, com os outros
tenants dela lá dentro. Email já registado: a página de activação exige entrar primeiro. Sessão
autenticada noutra conta, ou `is_active = False`: recusa com código estável, nunca uma concessão à
conta errada.

**A reposição de password é outra tabela, e é essa que entra na lista.** `accounts_passwordreset` não
tem `tenant_id` — uma password é credencial global e uma reposição não tem tenant nenhum para nomear,
porque quem a pede pode pertencer a zero ou a três — logo não tem política e **entra em `SEM_POLITICA`
com essa razão escrita**, ao lado do `accounts_user`, que lá está pela mesma razão estrutural. Guarda
`user_id`, hash do token e timestamps; não guarda email. Uma tabela só com `purpose` e `tenant_id`
nullable é a armadilha que a ADR 0005 já nomeou: sob política, uma linha com NULL avalia a falso e
desaparece. TTL de 1 hora. A ADR 0007 já prometia este caminho e o teste de que convite e reposição
respondem igual para um email que existe e para um que não existe — isto é dívida owed, não âmbito novo.

**Resto do contrato.** Convidar é só do `owner` no v1 (o conjunto de papéis é a Q7 e o
`SESSION-CONTEXT.md` diz que bloqueia esta ADR); nenhum convite concede papel acima do de quem convida.
O token é mostrado **uma vez**, na resposta ao POST que o criou, como uma chave de API: não há
consumidor da outbox (dívida nomeada) e um token mostrável depois teria de ser guardado em claro. Logo
**nenhuma tarefa Celery e nenhum evento no v1** — o `accounts/services.py` já diz que um evento sem
subscritor é um contrato público escrito ao contrário. A superfície dispensada de âmbito fica mínima:
login, logout, sessão, troca de tenant, activação e as duas de reposição; **criar, listar e revogar
convites são endpoints normais, com âmbito**. O CSRF resolve-se sem endpoint novo — `GET /auth/sessao`
leva `ensure_csrf_cookie` e a SPA chama-o no arranque de qualquer forma. A resposta do login tem um
campo de **estado**, para que um segundo factor seja mais um estado no mesmo endpoint e não um endpoint
novo (MFA é dívida do `SECURITY.md` §5). E o 429 do lockout passa a ter corpo JSON com
`code: conta_bloqueada`, que fecha um item de dívida nomeado.

**Alternativas.** Convites sem política, na lista fechada — é a forma que o pedido assumia, e é a que
esta ADR recusa: punha email, papel e `tenant_id` de **todos** os convites pendentes de **todos** os
clientes legíveis por qualquer ligação da app, que é a ameaça "acesso a dados de outro tenant" do
`SECURITY.md` §1 na forma literal, ao preço evitável de não pôr um uuid no link. Token assinado e sem
estado (`PasswordResetTokenGenerator`, `itsdangerous`) — dispensa a tabela, mas não é revogável nem de
uso único, e um convite tem de poder ser cancelado. Token no path em vez do fragmento — é a forma comum
e funciona, mas entra no log de acesso do proxy e no `Referer`, e um pre-fetch queima um token de uso
único. Registo self-service com NIF — três coisas em aberto para entregar um formulário. `Membership`
criado no convite — uma concessão de acesso que ninguém reclamou, e o `tenant_ids` a propor um âmbito
sem pessoa atrás. Magic link em vez de password — menos credenciais para roubar, mas toda a entrada
passa a depender de entrega de email, que não tem consumidor, e numa caixa de correio partilhada de
cozinha é pior do que uma password. Criar tenants pelo admin — a ADR 0007 não registra `Tenant` nem
`Membership` de propósito, e uma changelist que os cria pediria um seletor de tenant, que é
impersonation sem registo. JWT — o `SECURITY.md` §2 fixa `SessionAuthentication` e nada aqui precisa de
outra coisa.

**Consequências.** Duas tabelas novas: `accounts_invitation` (`tenant_id`, política com `ENABLE` e
`FORCE`, índice em `token_hash`, unicidade do convite pendente por `(tenant, email)`) e
`accounts_passwordreset` (sem política). As duas igualdades de conjuntos do `test_db_roles.py` mexem em
sentidos opostos — a primeira ganha uma tabela por ter `tenant_id`, a segunda ganha uma entrada
comentada — e ambas aparecem no diff. `APPEND_ONLY` não muda: `accepted_at` é um `UPDATE`. O `accounts`
ganha o primeiro `views.py`, `urls.py` e `serializers.py` do repositório, e a API deixa de ter zero
endpoints de domínio. No frontend, a árvore de rotas ganha um ramo público (`/entrar`, `/ativar`,
`/password/...`) **fora** do `AppShell`, e a rota de layout do shell ganha o `beforeLoad` que a ADR 0008
deixou em aberto; ele lê a sessão da cache do TanStack Query (`ensureQueryData`), e o selector do
`no-restricted-syntax` não precisa de mudar — o que a ADR 0008 recusou foi a **segunda** cache do
router, não ler a única que existe. **O ciclo de desenvolvimento muda, e isto é o custo prático:** o
servidor de fixtures **não** finge a sessão, porque uma sessão falsa é a única mentira que muda
autorização em vez de forma de dados e nenhum dos três gates da decisão 3 a apanharia; a partir daqui,
ver o shell num telemóvel com `pnpm dev --host` exige o backend a correr, Postgres migrado e um tenant
semeado — e é o comando acima que torna isso um passo só. **Prova:** um uuid forjado no link dá recusa
genérica e zero linhas lidas; token expirado, usado e inexistente dão o **mesmo** código e o mesmo
corpo; a aceitação por um email com password utilizável não toca na password; o guarda de âmbito do
`conftest.py` fica calado porque o convite é lido dentro do âmbito. Risco residual nomeado: um email de
convite roubado **é** uma pertença, e o que o limita é o TTL, o uso único e a revogação, não mais nada.
**Consultar `domain-expert`:** o conjunto de papéis (Q7) e se um `manager` pode convidar.
