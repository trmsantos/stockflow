# ADR 0005 — A fronteira transacional da RLS multi-tenant

**Contexto.** Três documentos descrevem o âmbito da RLS de três maneiras, e as três falham.
`ARCHITECTURE.md` §4 põe um `SET app.tenant_id` na *ligação*: com `CONN_MAX_AGE = 60` a ligação é
persistente e o GUC sobrevive à resposta, pelo que o pedido seguinte servido por ela que não passe
pelo middleware — anónimo, 404 antes da view, exceção num middleware acima — herda o tenant do
anterior, com a RLS convencida de que está a isolar. `SECURITY.md` §3 diz `SET LOCAL` "no início de
cada transação", mas com `ATOMIC_REQUESTS = False` cada `execute` é a sua própria transação
implícita, e `SET LOCAL` fora de um bloco de transação não tem efeito (o Postgres avisa e segue):
todas as queries correriam sem `app.tenant_id`. E `config/settings/base.py:46-48` põe o âmbito nos
`services.py`, que são só as escritas: as leituras vivem em `selectors.py` e as querysets são
avaliadas durante a serialização, já na view, logo todos os endpoints de lista ficavam de fora.
Acresce que o valor não é interpolável — `SET` não aceita parâmetro e formatar o UUID é injeção de
SQL num valor que vem da sessão — e que o Celery não tem middleware nenhum.

**Decisão.** A fronteira é a **transação**, e a transação é o pedido. O âmbito vive em
`apps/shared/db.py`, que é camada de base, não importa nada (ADR 0003) e já é importável por todos
sem contrato novo no import-linter. A forma primitiva é o context manager `tenant_scope(tenant_id)`:
abre `transaction.atomic()`, corre `SELECT set_config('app.tenant_id', %s, true)` — parametrizado, e
o `true` é o que lhe dá âmbito de transação sem passar por `SET` — e publica o tenant num
`ContextVar` que `current_tenant()` lê (é também a origem do campo `tenant_id` dos logs). É
reentrante para o mesmo tenant e levanta `TenantScopeConflict` para um tenant diferente: um
`set_config` local dentro de um savepoint vive até ao fim da transação de topo e não se restaura à
saída do bloco interior, pelo que trocar de tenant a meio contaminaria o resto da transação. Quem
entra é o `TenantMiddleware` do `accounts`, a envolver `get_response()`, e passa a ser o **último**
da lista: precisa do `request.user`, e tudo o que tem de ser escrito seja qual for o destino do
pedido — a sessão do `SESSION_SAVE_EVERY_REQUEST` e o `AccessAttempt` do axes — fica assim fora da
transação, em autocommit, que é onde deve estar. Numa resposta 5xx o middleware marca
`transaction.set_rollback(True)` antes de fechar o bloco: o DRF apanha a exceção dentro da view e
sem isso um 500 commitava o que já tinha escrito. `ATOMIC_REQUESTS` fica `False` — não por economia,
mas porque abre a transação em volta da *view*, dentro da cadeia de middleware, onde nenhum
middleware lhe pode pôr o `set_config`. O `@transaction.atomic` dos services mantém-se e passa a ser
um savepoint: um service que falha desfaz o que escreveu sem derrubar o pedido. `CONN_MAX_AGE = 60`
mantém-se, e é esse o ganho: com o GUC preso à transação, nada sobrevive à resposta (e um pooler em
modo transação passa a ser possível). No Celery, `TenantTask` é o `task_cls` do app — todo o
`@app.task` o herda, logo não há outra forma de declarar uma tarefa —, `tenant_id` é argumento
obrigatório recusado no `apply_async` quando falta, e o corpo já corre dentro de `tenant_scope`. A
dispensa é um atributo de classe visível e greppable (`tenant_scope_exempt`), hoje só para o cron
que itera tenants a enfileirar uma tarefa por cada e para o consumidor da outbox, que lê a linha sob
`system_scope()` (`app.scope = 'system'`, disjunto que só a tabela `outbox` tem na sua política) e
reentra em `tenant_scope(row.tenant_id)` antes de tocar em mais nada. Pedidos sem tenant — login,
healthcheck, admin, anónimos — não abrem âmbito nem transação: `current_setting('app.tenant_id',
true)` é NULL, a comparação da política é NULL, zero linhas, sem erro.

**Alternativas.** GUC de sessão com `CONN_MAX_AGE = 0` — resolve a travessia ao preço de um
handshake TCP+TLS+auth por pedido, e não resolve o Celery. `ATOMIC_REQUESTS = True` — a transação
abre onde o middleware já não chega, e liga transação a todos os GETs anónimos. Filtro por
`tenant_id` num manager por omissão, sem RLS — um `objects.all()` esquecido é travessia de tenant, e
perde-se o segundo controlo de `SECURITY.md` §1: a RLS é a rede, não a regra. Um schema por tenant —
isolamento mais forte, migrações × N e o mesmo problema de ligação persistente, agora no
`search_path`. Decorador em cada service e selector — depende de disciplina, e o que é avaliado na
serialização escapa-lhe.

**Consequências.** `FORCE ROW LEVEL SECURITY` entra em todas as migrações de tabelas com `tenant_id`
desde a primeira: sem ele o dono da tabela — que é o role único do `.env.example` — ignora a
política. A separação de roles (app sem `ALTER TABLE`, migrações com role próprio) fica para a **ADR
0006**, porque muda o provisionamento e não a fronteira: `DATABASE_URL` + `MIGRATION_DATABASE_URL`
no `.env.example`, script de init e GRANTs no serviço `db` do compose. O risco residual é nomeável e
aceito-o até lá: hoje o role da app pode `DISABLE ROW LEVEL SECURITY`. No admin, as tabelas de
tenant aparecem vazias — não há âmbito —, e é deliberado: acesso operacional a dados de tenant é
pela app ou por um script que abra `tenant_scope`. Respostas em streaming são geradas depois de o
bloco fechar: nada lazy sobre tabelas de tenant pode viajar nelas. E `transaction.atomic(durable=True)`
num service passa a levantar dentro de um pedido, o que é útil — sinaliza um service mal
especificado: o que tiver de sobreviver ao rollback do pedido não pertence ao pedido, vai para uma
tarefa. **Prova, em dois testes com o Postgres do compose em 5442 (ADR 0002).** No passo 3,
`tests/test_tenant_scope.py` prova o mecanismo sem precisar de tabela de tenant nenhuma: dentro do
âmbito o `current_setting` devolve o UUID; à saída devolve NULL **na mesma ligação** (é a assertion
que a versão com GUC de sessão falha); um segundo tenant no mesmo bloco levanta; uma tarefa sem
`tenant_id` recusa ao enfileirar. Precisa de `django_db(transaction=True)`: com a transação do
pytest-django por fora, o `set_config` local só reverte no fim dela e a assertion do NULL não
significa nada. No passo 4, `tests/test_rls_isolation.py` prova o isolamento — dois tenants com uma
linha cada, pedido autenticado como utilizador de A nunca vê a linha de B, num endpoint de *lista*,
para a queryset ser avaliada na serialização — com uma guarda a afirmar que o role da ligação não é
`SUPERUSER` nem tem `BYPASSRLS`, senão passa por motivo errado. **Dependência nomeada: consultar
`domain-expert`.** Esta ADR fixa a fronteira exterior; o que o negócio exige que seja atómico dentro
de uma receção (lotes + movimentos + CMP + `SupplierPrice`, §6b) entra como savepoints dentro dela e
não altera a decisão.

**Restrições que vêm do domínio.** O `domain-expert` validou a fronteira e confirmou que nada tem de
commitar independentemente do resto do pedido, mas acrescentou cinco coisas que a transação-por-pedido
torna vinculativas. **Endpoints de sincronização são por linha**, ou devolvem resultado por linha com
um savepoint por linha, e nunca falham o lote inteiro por causa de uma linha: um funcionário conta 40
artigos dentro de uma câmara frigorífica, que não tem rede, e o telemóvel sincroniza em fila quando
sai — se as 40 linhas forem um bloco atómico, um produto entretanto desativado rejeita as 39 boas e
manda-o contar outra vez. **Leituras longas seguram um snapshot**: uma transação só de leitura não
consome XID nem slot de escrita, mas o relatório que varre 80 mil movimentos mantém-no aberto enquanto
durar, pelo que relatórios pesados leem da projeção e de agregados por período em vez de varrerem o
ledger; aos 4 segundos é tolerável, ao minuto não é. **Esta fronteira sobe o preço de I/O síncrono
numa view de "lento" para "segura locks"**: o FEFO tranca as linhas de `StockLevel` com `FOR UPDATE`
antes de escolher o lote — escolher e depois trancar é o bug, porque a escolha foi feita sobre dados
velhos — em ordem determinística `(product_id, lot_id)`, logo uma chamada a LLM ou HTTP dentro do
pedido segura os locks de todos os produtos da fatura até ao commit; a proibição de efeitos
secundários síncronos do `CLAUDE.md` deixa de ser higiene e passa a ser correção. **O predicado da
política é `tenant_id`, e só**: tenant é o NIF, o dono de três pastelarias é um tenant com três
localizações (recebe uma fatura de fornecedor que cobre entregas em duas lojas e transfere stock entre
elas todos os dias), e a localização é autorização por `Membership`, nunca política — `location_id` no
predicado tornaria impossíveis a transferência entre lojas e a vista consolidada do dono. E **dados de
referência partilhados não têm `tenant_id`, logo não têm política**: o catálogo global EAN→descrição e
os fornecedores que todos os clientes usam vivem em tabelas próprias sem `tenant_id` e sem RLS,
read-only para a app, com o tenant a copiar-para-uso no seu `Product` — uma linha de `tenant_id` NULL
avaliaria a falso e desaparecia, e esta saída mantém a regra do `CLAUDE.md` ("toda a tabela com
`tenant_id` tem política RLS") literalmente verdadeira, sem exceção.
