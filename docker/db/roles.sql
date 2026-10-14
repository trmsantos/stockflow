-- docker/db/roles.sql — provisionamento dos roles de base de dados (ADR 0006).
--
-- Três roles, nenhum com duas funções:
--   * superuser de bootstrap (POSTGRES_USER) — só corre este ficheiro; não
--     aparece em DATABASE_URL nenhum;
--   * stockflow_owner — dono da base de dados e das tabelas, credencial do
--     `migrate` e mais nada;
--   * stockflow_app — não é dono de nada, sem CREATE no esquema, sujeito à RLS.
--     É a única ligação que serve pedidos.
--
-- O dono é um role separado porque o dono de uma tabela pode
-- `ALTER TABLE ... DISABLE ROW LEVEL SECURITY`, e um role que desliga o seu
-- próprio isolamento não tem isolamento.
--
-- **É idempotente e pode correr a qualquer momento.** Tem duas entradas:
-- montado em /docker-entrypoint-initdb.d/ (um volume novo recebe-o de graça) e
-- pelo serviço `db-roles` do compose (`--profile setup`). A segunda não é
-- conveniência: o init dir só corre na PRIMEIRA inicialização do volume, quem já
-- tem o pgdata nunca o vê, e em Postgres gerido não existe.
--
-- As passwords vêm do ambiente, nunca do ficheiro.
\set ON_ERROR_STOP on
\getenv app_pw STOCKFLOW_APP_PASSWORD
\getenv owner_pw STOCKFLOW_OWNER_PASSWORD

-- Criação idempotente por \gexec e não por `DO $$ ... $$`: o psql não interpola
-- variáveis dentro de dollar-quoting, logo um `DO` com :'app_pw' lá dentro
-- passaria a password literalmente como texto "..:'app_pw'..".
SELECT 'CREATE ROLE stockflow_owner LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE CREATEDB'
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'stockflow_owner')\gexec
SELECT 'CREATE ROLE stockflow_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE'
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'stockflow_app')\gexec

-- ALTER explícito: o script também corrige um role que já existisse com
-- atributos errados (é o caso de quem provisionou antes desta ADR).
ALTER ROLE stockflow_owner LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE CREATEDB PASSWORD :'owner_pw';
ALTER ROLE stockflow_app   LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :'app_pw';

-- Timeouts no role da aplicação, porque o timeout do servidor de aplicação não
-- alcança o Postgres: o `--timeout=30` do gunicorn mata o worker, mas o backend
-- do lado do servidor continua com a transação aberta e os locks presos — só
-- nota que o cliente desapareceu na próxima escrita. Com uma transação por
-- pedido (ADR 0005) e o FEFO a trancar linhas de `StockLevel` com `FOR UPDATE`,
-- uma transação órfã bloqueia os outros pedidos sobre os mesmos produtos.
--
-- Os três, e o que cada um trava:
--   statement_timeout                  uma query que demora demasiado
--   lock_timeout                       uma espera por um lock que não chega
--   idle_in_transaction_session_timeout  uma transação aberta e parada, que é
--                                      o caso do worker morto
--
-- Ficam no role e não nas settings do Django de propósito: assim valem para
-- **qualquer** ligação com esta credencial, incluindo um `psql` de alguém a
-- depurar em produção. O `stockflow_owner` não os leva — uma migração de dados
-- pode legitimamente demorar minutos, e um `statement_timeout` a matá-la a meio
-- é pior do que a espera.
ALTER ROLE stockflow_app SET statement_timeout = '15s';
ALTER ROLE stockflow_app SET lock_timeout = '5s';
ALTER ROLE stockflow_app SET idle_in_transaction_session_timeout = '30s';

-- Desde o PG 15 o esquema `public` pertence a `pg_database_owner`: passar a
-- posse da BD dá o esquema ao dono sem um único GRANT, e é a mesma mecânica que
-- lhe dá CREATE na base de dados de teste que ele próprio cria.
SELECT format('ALTER DATABASE %I OWNER TO stockflow_owner', current_database())\gexec
SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', current_database())\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO stockflow_app, stockflow_owner', current_database())\gexec
ALTER SCHEMA public OWNER TO stockflow_owner;

GRANT USAGE, CREATE ON SCHEMA public TO stockflow_app;

-- Posse do que já existe (tabelas criadas antes desta ADR pelo superuser).
-- `%I` é a citação segura de identificador; mudar o dono da tabela arrasta as
-- sequências que ela possui.
DO $$
DECLARE t text;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('ALTER TABLE public.%I OWNER TO stockflow_owner', t);
    END LOOP;
END $$;

-- Retroativo, uma vez. Sem TRUNCATE, e não é esquecimento: um TRUNCATE não é
-- filtrado por política nenhuma, logo é um apagar-tudo que atravessa tenants.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO stockflow_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO stockflow_app;

-- Reexecuta após a posse da BD ter passado para stockflow_owner: garante que
-- as tabelas criadas pela primeira metade das migrações também têm GRANT.
-- Sem isto, a migração parcial deixa tabelas com permissões erradas.
DO $$
DECLARE t text;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO stockflow_app', t);
    END LOOP;
END $$;
DO $$
DECLARE s text;
BEGIN
    FOR s IN SELECT sequencename FROM pg_sequences WHERE schemaname = 'public' LOOP
        EXECUTE format('GRANT USAGE, SELECT ON public.%I TO stockflow_app', s);
    END LOOP;
END $$;

-- Para as tabelas que as migrações futuras criarem. Indexado pelo role que
-- CRIA: uma migração corrida por outro role produz tabelas sem GRANT nenhum, e
-- o erro aparece na app, não na migração.
ALTER DEFAULT PRIVILEGES FOR ROLE stockflow_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO stockflow_app;
ALTER DEFAULT PRIVILEGES FOR ROLE stockflow_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO stockflow_app;

-- A fixture que trocava de role no passo 3 deixa de ter razão de existir: a
-- ligação da suite passa a ser a da app e a RLS aplica-se em todos os testes.
-- `DROP OWNED BY` primeiro, senão o DROP ROLE falha por dependências.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'stockflow_rls_probe') THEN
        EXECUTE 'DROP OWNED BY stockflow_rls_probe';
        EXECUTE 'DROP ROLE stockflow_rls_probe';
    END IF;
END $$;

-- O pg_default_acl é por base de dados e a BD de teste nasce clonada do
-- template1: sem isto, as tabelas que o pytest migra ficam sem GRANT para a
-- app. Só os defaults — não se mexe na posse do public do template1.
\c template1
ALTER DEFAULT PRIVILEGES FOR ROLE stockflow_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO stockflow_app;
ALTER DEFAULT PRIVILEGES FOR ROLE stockflow_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO stockflow_app;
