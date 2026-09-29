# ADR 0004 — A única exceção de lint: F403 na camada de settings

**Contexto.** O CLAUDE.md diz "nunca suprimir lint". O passo 2 do kickoff criou
`config/settings/{base,dev,prod,test}.py`, e a herança entre eles é `from config.settings.base
import *` — não é estilo, é o mecanismo de composição do Django: o `DJANGO_SETTINGS_MODULE` aponta
para *um* módulo e o Django lê os atributos que lá estiverem, pelo que tudo o que vem do `base` tem
de existir no módulo final. O ruff emite `F403` em qualquer `import *`, com ou sem `__all__` no
módulo de origem (verificado empiricamente, não deduzido). Ou seja: a regra e o mecanismo são
incompatíveis, e a escolha é onde pôr a exceção — não se pode não a ter.

**Decisão.** Fica em `[tool.ruff.lint.per-file-ignores]`, restrita a `F403` e aos três módulos de
ambiente (`config/settings/dev.py`, `prod.py`, `test.py`), com o comentário que explica porquê no
próprio `pyproject.toml`. O `base.py` não está na lista: não faz `import *`. Três coisas limitam o
alcance: cada módulo de ambiente **volta a importar explicitamente** os nomes que usa
(`from config.settings.base import CONTENT_SECURITY_POLICY, DATABASES, REST_FRAMEWORK, env`), pelo
que o `F405` continua ativo e apanha referências a nomes que não existem no `base`; não há um único
`# noqa` no repositório; e nenhuma regra dos grupos `S` (bandit), `DJ` ou `B` é dispensada em sítio
algum. A regra do CLAUDE.md passa a ler-se: **nunca `# noqa` no código; exceções só em
`per-file-ignores`, com comentário e com um ADR**.

**Alternativas.** Listar à mão os ~45 nomes em cada módulo de ambiente — cumpre a regra à letra, mas
uma setting nova no `base` deixa de chegar a `prod` em silêncio, e é em produção que isso custa
(seria uma setting de segurança a faltar sem ninguém dar por ela). `# noqa: F403` na linha do import
— é a mesma supressão, menos visível, e abre a porta ao `# noqa` no resto do repositório.
`globals().update(vars(base))` — engana o ruff em vez de responder-lhe, e nenhuma ferramenta
estática passa a ver as settings. Settings baseadas em classes (`django-configurations`) — uma
dependência nova, e um modelo mental diferente do resto do projeto, para resolver um aviso de lint.

**Consequências.** O `per-file-ignores` passa a ter duas entradas — `tests/** = ["S101"]` (o
`assert` do pytest) e esta. São o limite conhecido: uma terceira entrada é sinal de que algo está
errado, e passa pelo `security-reviewer` e por um ADR próprio. Em contrapartida, `uv run ruff
check .` volta a ter significado absoluto: qualquer output diferente de "All checks passed!" é um
erro a corrigir, nunca um aviso a tolerar. Se um dia o ruff resolver `__all__` para efeitos de
`F403`, esta exceção sai do `pyproject.toml` e este ADR fica superado.
