"""Camada de settings: `base` + um módulo por ambiente (`dev`, `prod`, `test`).

`DJANGO_SETTINGS_MODULE` aponta sempre para um dos três, nunca para `base`.

O `.env` é lido **aqui**, à entrada da camada, e não dentro do `base.py`. A razão
é a ordem, e ela morde: o Python importa este pacote antes de qualquer um dos
quatro módulos, enquanto o `base.py` só é lido depois de o módulo de ambiente
já ter decidido os seus defaults. O `config/settings/test.py` põe um
`DATABASE_URL` de fallback com `setdefault`, para a suite correr numa máquina
limpa; se o `.env` só fosse lido a seguir, esse fallback — que não tem password —
ganhava ao `DATABASE_URL` real e `uv run pytest` não chegava ao Postgres do
compose, onde o role do ADR 0002 exige password.

Em produção este ficheiro não existe (as variáveis vêm do orquestrador ou de
Docker secrets), e o `is_file()` trata disso. O `read_env` do django-environ
**não** sobrepõe variáveis que já existam no ambiente, pelo que o ambiente real
continua a mandar sobre o ficheiro.
"""

from pathlib import Path

import environ

#: Raiz do projeto backend — onde vivem `manage.py`, `pyproject.toml` e `.env`.
#: O `base.py` recalcula-o como `BASE_DIR`, a partir do seu próprio ficheiro.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

if _ENV_FILE.is_file():
    environ.Env.read_env(_ENV_FILE)
