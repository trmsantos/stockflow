# ADR 0002 — Portas de desenvolvimento fora dos defaults

**Contexto.** A máquina de desenvolvimento corre mais do que um projeto ao mesmo tempo (outras
sessões de Claude Code com Django em 8000 e Vite em 5173). Colisões de porta em `docker compose up`
são silenciosas ou dão erros opacos, e custam tempo a diagnosticar no meio de outra tarefa.

**Decisão.** Nenhum serviço do StockFlow publica uma porta default no host. O mapeamento é:
proxy `8090`, Django `8010`, Vite `5183`, Postgres `5442`, Redis `6389`. Dentro da rede do compose
os contentores continuam a ouvir nas portas canónicas (80, 8000, 5173, 5432, 6379) — só muda o lado
do host. Todas as portas do host vêm de variáveis em `.env` (`PROXY_PORT`, `BACKEND_PORT`,
`FRONTEND_PORT`, `POSTGRES_PORT`, `REDIS_PORT`) com estes valores como default no `compose.yml`,
e estão documentadas no `.env.example`.

**Alternativas.** Deixar os defaults e parar o outro projeto antes de trabalhar (frágil, e obriga a
serializar trabalho); `network_mode: host` (não funciona em Docker Desktop no macOS); portas
aleatórias atribuídas pelo Docker (impossível pôr URLs estáveis na documentação e no `gen:api`).

**Consequências.** As URLs de desenvolvimento são `http://localhost:8090` (app via proxy) e
`http://localhost:8010` (API direta). `CSRF_TRUSTED_ORIGINS` e a base de URL do cliente OpenAPI têm
de incluir a porta. Em produção nada disto se aplica: o proxy fica em 443 atrás do orquestrador.
