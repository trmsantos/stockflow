"""Entrypoint ASGI. **Hoje não é servido por nada** — ver `config/wsgi.py`.

Fica porque é o entrypoint padrão do Django e porque o `ASGI_APPLICATION` do
`base.py` o nomeia, não porque haja um uvicorn à espera dele: o servidor de
produção é o gunicorn sobre o `config/wsgi.py` (ver o comentário da dependência
no `pyproject.toml`).

Se um dia houver razão para o servir — uma view `async` de streaming, websockets
— três coisas têm de ser resolvidas **antes**, e nenhuma é configuração:

1. `CONN_MAX_AGE = 60` (ADR 0005). Sob ASGI, cada pedido síncrono corre no seu
   próprio executor de uma thread; uma ligação é thread-local e com
   `CONN_MAX_AGE > 0` não é fechada no fim do pedido, pelo que fica aberta
   depois de a thread que a abriu desaparecer. Ou `CONN_MAX_AGE = 0`, ou um
   pooler (pgbouncer em modo transação, que a ADR 0005 já diz ser possível
   porque o GUC do tenant está preso à transação), ou o `pool` do psycopg3;
2. o teto de concorrência. Com WSGI + `--threads`, `workers × threads` é o
   número máximo de transações abertas ao mesmo tempo e escolhe-se contra o
   `max_connections` do Postgres. O ASGI aceita pedidos enquanto o event loop
   os aceitar, e sem teto próprio isso é um número de transações simultâneas
   decidido pelo tráfego;
3. a fronteira da RLS. O `tenant_scope` guarda o tenant num `ContextVar` e a
   transação numa ligação thread-local: uma view `async` que salte de thread a
   meio do pedido sai do âmbito sem que nada se queixe. Uma view `async` neste
   projeto exige reler a ADR 0005 primeiro, não um `async def`.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_asgi_application()
