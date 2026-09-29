# ADR 0006 — Separação de roles de base de dados

**Contexto.** O `docker/compose.yml` passa `POSTGRES_USER=stockflow` e a imagem oficial do Postgres
corre `initdb --username=stockflow`: o role com que a aplicação se liga **é** o superuser de
bootstrap do cluster. Medido no contentor a correr:

```
current_user | rolsuper | rolbypassrls | rolcreatedb
stockflow    | t        | t            | t
```

Um superuser não é sujeito a políticas de RLS e o `FORCE ROW LEVEL SECURITY` não o alcança, pelo que
a política do `shared_outboxevent` existe, está testada e **não é imposta em runtime**. Os testes de
isolamento do passo 3 só provam algo porque criam um role `stockflow_rls_probe NOLOGIN` e trocam para
ele com `set_config('role', ...)` antes de afirmar o que quer que seja: provam a política, não provam
o produto. O `SECURITY.md` §3 já exige o que falta — "utilizador da app sem `SUPERUSER`, sem
`CREATEDB`; migrações com um role separado" — e a ADR 0005 nomeou o risco residual com prazo, que é
esta ADR. O caminho óbvio não serve, e é aqui que está a decisão difícil: "faz o role da app dono das
tabelas e liga o `FORCE`" sujeita-o de facto à política, mas o dono de uma tabela pode `ALTER TABLE
... DISABLE ROW LEVEL SECURITY` e `DROP POLICY`, e um role que desliga o seu próprio isolamento não
tem isolamento nenhum — tem uma convenção. O dono tem de ser **outro** role.

**Decisão.** Três roles, nenhum com duas funções. O superuser de bootstrap (`POSTGRES_USER`, hoje
`stockflow`; em produção, o role de administração do fornecedor) passa a ser só provisionamento e não
aparece em `DATABASE_URL` nenhum. O `stockflow_owner` — `LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE
CREATEDB` — é dono da base de dados e, por consequência, de todas as tabelas: é a credencial do
`migrate`, e mais nada. O `stockflow_app` — `LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE` —
não é dono de nada, tem `USAGE` no esquema e DML nas tabelas, e **não** tem `CREATE` no esquema: é
isso que faz um `migrate` com a URL errada morrer no primeiro `CREATE TABLE` em vez de aplicar
metade. O `FORCE` mantém-se em todas as tabelas com `tenant_id`, agora pela sua razão verdadeira — já
não é pela app, que não é dona; é pelo `stockflow_owner`, que corre migrações de dados e sem ele
corria-as sem política. Quem dá o esquema ao dono é `ALTER DATABASE stockflow OWNER TO
stockflow_owner`, sem GRANT nenhum: desde o PG 15 o esquema `public` pertence a `pg_database_owner`,
e é a mesma mecânica que lhe dá `CREATE` na base de dados de teste que ele próprio cria. As tabelas
que as migrações futuras criarem ficam acessíveis à app por `ALTER DEFAULT PRIVILEGES FOR ROLE
stockflow_owner IN SCHEMA public` (`SELECT, INSERT, UPDATE, DELETE ON TABLES` e `USAGE, SELECT ON
SEQUENCES`), e serve — com dois avisos que têm de ficar escritos: os defaults são indexados pelo role
**que cria** e pelo esquema, logo uma migração corrida por outro role (o bootstrap, o admin do
fornecedor) produz tabelas sem GRANT nenhum, e o erro aparece na app e não na migração; e não são
retroativos nem viajam para uma base de dados nova, por isso o provisionamento faz também um
`GRANT ... ON ALL TABLES` de uma vez e repete os defaults no `template1`, de onde nasce a BD de
teste. `TRUNCATE` fica de fora da lista, e não é esquecimento. A imutabilidade do ledger é o mesmo
assunto: `REVOKE UPDATE, DELETE ON inventory_stockmovement FROM stockflow_app`, na migração que cria
a tabela, ao lado do bloco de RLS. Não é uma exceção espalhada por migrações — é **uma** tabela, a
única onde append-only é regra de negócio (pedido do `domain-expert`: toda a matemática da contagem
física depende de o append-only ser real), e o que a impede de se tornar folclore é um teste com a
lista das tabelas append-only explícita, que falha se outra tabela perder `UPDATE`/`DELETE` ou se
esta os recuperar; **consultar `domain-expert`** antes de acrescentar a segunda. O `DATABASES`
continua a ter **uma** alias, sempre a da app, e a URL do dono nunca entra lá: o role é propriedade
do *processo*, não de um comando. O `migrate` corre num processo cujo `DATABASE_URL` é o
`MIGRATION_DATABASE_URL` — serviço one-shot no compose, passo com `env:` próprio no CI, job antes do
rollout em produção — e `base.py`, `dev.py` e `prod.py` não mudam uma linha. O `pytest` precisa de
criar, migrar e apagar a BD de teste, e quem migra fica dono das tabelas: logo o setup é do dono e os
testes são da app. Um `django_db_setup` próprio troca `USER`/`PASSWORD` da alias `default` pelos do
`MIGRATION_DATABASE` (lido só em `config/settings/test.py`), corre o `setup_databases`, fecha a
ligação e devolve a alias ao role da app antes do primeiro teste, voltando ao dono no teardown que
apaga a BD. A suite passa a ter a forma de produção: tabelas do dono, queries da app, GRANTs reais
exercidos, RLS imposta em **todos** os testes e não só nos quatro que hoje pedem uma fixture. Uma
concessão, nomeada: o setup faz `GRANT TRUNCATE ON ALL TABLES` à app, porque o `flush` entre testes
`transaction=True` é um `TRUNCATE` (que nenhuma política filtra) — fica no harness e não no
`roles.sql`, e é por isso que o append-only que a suite prova é sobre `UPDATE` e `DELETE`. O
provisionamento é `docker/db/roles.sql`, idempotente e sem passwords dentro (vêm do ambiente por
`\getenv`), com duas entradas: montado em `/docker-entrypoint-initdb.d/`, para um volume novo o
receber de graça, e corrível a qualquer momento por um serviço one-shot do compose. A segunda não é
conveniência — o init dir só corre na **primeira** inicialização do volume, quem já tem o `pgdata`
nunca o vê, e em Postgres gerido não existe. Roles são objetos do cluster e não do esquema: não
entram numa migração, que corre com um role sem `CREATEROLE` e uma vez por base de dados.

**Alternativas.** App dona das tabelas com `FORCE` — respondido no contexto: o dono desliga a
política que o sujeita. Duas aliases em `DATABASES` com `migrate --database=migrator` — o Django
suporta-o de fábrica e é mais ergonómico em dev, mas a alias é lida do ambiente do processo, logo a
password do dono passa a existir em cada gunicorn e worker, e com `CONN_MAX_AGE = 60` cada um guarda
uma ligação privilegiada aberta e sem uso; a flag esquece-se, e esquecê-la é silencioso quando não há
nada para aplicar; e em teste deixa de ser explícito quem cria a base de dados — passa a depender da
ordem do dicionário e de uma assinatura de BD de teste onde o `USER` não entra. `SET ROLE
stockflow_app` por ligação, com uma credencial só — fecha a porta que a ADR 0005 abriu de propósito:
é estado de sessão, não sobrevive a um pooler em modo transação, e a alternativa (`SET LOCAL ROLE` em
cada transação) é uma segunda instrução por pedido num role que pode voltar atrás. GRANTs à mão em
cada migração — depende de disciplina e a falha aparece em runtime, na app, longe da causa. Defaults
só com `SELECT, INSERT` e `UPDATE`/`DELETE` explícitos por tabela — inverte o ónus: dezenas de
exceções por escrever para proteger uma tabela. Roles criados numa migração — exige `CREATEROLE` no
role de migração, que é precisamente o privilégio que se está a retirar.

**Consequências.** O `.env.example` deixa de ter uma credencial e passa a ter três papéis:
`DATABASE_URL` é do `stockflow_app`, entra `MIGRATION_DATABASE_URL` do `stockflow_owner`, e o bloco
`POSTGRES_*` fica identificado como o superuser de bootstrap — usado pelo `initdb`, pelo healthcheck
e pelo `roles.sql` —, com `STOCKFLOW_APP_PASSWORD` e `STOCKFLOW_OWNER_PASSWORD` para o script lhes
atribuir password. Quem já tem o volume `pgdata` corre o `roles.sql` à mão uma vez; ele arruma também
a posse do que já existe, num `DO` sobre `pg_tables` com `ALTER TABLE ... OWNER TO` — que é
igualmente o que endireita um `pg_dump` restaurado — e faz `DROP ROLE IF EXISTS
stockflow_rls_probe`. Apagar o volume nunca é necessário. A fixture `ligacao_sujeita_a_rls`
desaparece por inteiro, com o `CREATE ROLE` e os GRANTs ad-hoc que tinha lá dentro: os quatro testes
da política da outbox perdem o argumento e passam a valer. **Prova, em `tests/test_db_roles.py`:** na
ligação normal do Django, `current_user` é `stockflow_app`, `rolsuper` e `rolbypassrls` são falsos e
`session_user = current_user` — é esta última que distingue "ligou-se como" de "trocou para", e é a
asserção que a suite de hoje não consegue fazer; nenhuma tabela do `public` tem a app como
`relowner`; `has_schema_privilege('stockflow_app', 'public', 'CREATE')` é falso; e uma varredura do
`pg_class` afirma que toda a tabela é legível e escrita pela app exceto a lista append-only, e que
toda a tabela com coluna `tenant_id` tem `relrowsecurity`, `relforcerowsecurity` e política — o que
transforma a regra do CLAUDE.md num teste em vez de um item de revisão. O `check --deploy` não abre
ligação, pelo que o `security_check.sh` continua a correr com a credencial da app e mais nada; no CI
(passo 7) a ordem é `roles.sql` como bootstrap → `migrate` com a URL do dono → `pytest` com as duas →
gates. O risco residual muda de sítio e encolhe: o `stockflow_owner` continua a poder desligar a RLS
das suas tabelas, mas a sua password não existe em processo nenhum que sirva pedidos, e a app já não
pode `ALTER TABLE` nada. Uma migração de dados sobre uma tabela de tenant corre como dono e **com**
`FORCE`: vê zero linhas até definir `app.tenant_id`, e a saída é iterar tenants, não `NO FORCE` —
que, se um dia for preciso, é greppable e passa pelo `security-reviewer`. `DELETE` revogado no ledger
significa que nada que aponte para um movimento pode apagar em cascata: `on_delete=PROTECT` ou
remoção lógica em quem lhe está acima, senão o ORM emite um `DELETE` que a base de dados recusa —
**consultar `domain-expert`**, que é a mesma conversa do produto que não apaga um artigo com
histórico. E o pooler: credenciais separadas por role mantêm a porta do modo transação aberta —
o pgbouncer agrupa por (utilizador, base de dados) e nada disto é estado de sessão. Depois desta ADR
não há um único `SET ROLE` no repositório.
