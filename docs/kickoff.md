# StockFlow — o guião do arranque

> **Este documento é histórico e está em português, de propósito.** Era o
> `README.md` do repositório quando ele era um andaime: descrevia como copiar a
> pasta para um repo novo, que skills instalar e que sessão fazer o quê. Passou
> para cá a 2026-10-07, quando o dono do produto apanhou a página do GitHub a
> descrever um procedimento de cópia em vez do produto — e tinha razão duas
> vezes, porque também estava na língua errada para quem chega de fora.
>
> O plano de sessões abaixo está **parcialmente cumprido e parcialmente
> desactualizado**: a sessão 1 está feita, os ecrãs das sessões 4 e 5 existem
> sobre o servidor de dados falsos, e a ordem mudou por decisões do dono que
> estão nas ADRs. Fica como registo de por onde se começou, não como plano a
> seguir. O estado real está no `README.md` e as decisões em `docs/decisions/`.


Copia **todo** o conteúdo desta pasta para a raiz do teu repositório (incluindo a pasta oculta `.claude/`).

```
stockflow/
├── CLAUDE.md                 regras + quem faz o quê
├── DESIGN.md                 sistema visual (já preenchido para o StockFlow)
├── ARCHITECTURE.md           módulos, fluxos, fronteiras
├── SECURITY.md               ameaças, settings, encriptação, CI
├── docs/decisions/           ADRs (a primeira já está)
└── .claude/
    ├── agents/               architect · backend · frontend · domain-expert · security-reviewer
    ├── commands/             /feature · /review · /kickoff
    └── skills/               security-check · inventory-domain · invoice-extraction
                              django-expert · django-safe-migration · django-celery-expert · django-reviewer (vintasoftware, já incluídas)
```

## 1. Instalar as skills externas (uma vez, na raiz do repo)

```bash
npx skills add anthropics/skills --skill frontend-design
npx skills add vercel-labs/agent-skills --skill web-design-guidelines
npx skills add vercel-labs/agent-skills --skill react-best-practices
npx skills add mattpocock/skills --skill grill-me
npx skills add shadcn-ui/ui --skill shadcn
```

As skills de Django da vintasoftware (`django-expert`, `django-safe-migration`, `django-celery-expert`,
`django-reviewer`) **já estão na pasta** — não precisas de as instalar. Para atualizar mais tarde:
`npx skills add vintasoftware/django-ai-plugins --skill django-expert` (e as outras três).

A `django-drf` da prowler-cloud ficou de fora de propósito: está escrita para o repo deles
(JSON:API, `BaseRLSViewSet`, caminhos `api/v1/…`) e ia puxar o agente para convenções que não são as nossas.
As regras boas dela (serializers separados por operação, UUID, N+1, `swagger_fake_view`) já estão no agente `backend`.

Antes de instalar qualquer skill, abre a pasta `scripts/` dela (se existir) e vê o que faz.
Confirma os caminhos no skills.sh — os repositórios mudam.

## 2. Como começar (faseado, não "abrir e dar prompts")

| Sessão | O que fazes | Resultado |
|---|---|---|
| 0 | Fala com 3–5 donos de restaurante. Duas perguntas: como dão entrada de mercadoria; quanto deitam fora por mês. | Validação (ou pivot) antes de escrever código |
| 1 | `git init`, copia esta pasta, instala as skills, abre Claude Code, corre `/kickoff`. Confirma passo a passo. | Repo com auth multi-tenant, RLS, Docker, CI — e zero features |
| 2 | `/feature catálogo de produtos com unidades, embalagens e fornecedores` | `catalog` |
| 3 | `/feature localizações e movimentos de stock (entrada e saída manual) com lotes e validade` | `inventory` — o ledger |
| 4 | `/feature listagem de stock com alertas de mínimo e de validade` | Primeiro ecrã útil |
| 5 | `/feature contagem física em telemóvel` | Fecha o MVP fase 1 |
| 6–7 | `/feature receção por fatura: upload, extração, revisão e confirmação` | O diferenciador |
| 8 | `/feature receitas que consomem stock` · `/feature relatório de desperdício em €` | Fase 2 |

Regra: uma feature por sessão. No fim de cada uma, `/review`, commit, e para. Amanhã continua-se com
contexto limpo — é para isso que os ficheiros `.md` existem.

## 3. Como interagir com os agentes

- `/feature …` — usa sempre isto para trabalho novo; o pipeline chama os agentes pela ordem certa.
- "usa o `domain-expert` para …" — quando tens uma dúvida de regras antes de decidir.
- "usa o `security-reviewer` em `apps/purchasing`" — auditoria pontual.
- Os agentes leem `CLAUDE.md` e os `.md` que este lhes manda ler; **não** leem a conversa atual.
  Se decidires algo importante no chat, pede para o registar numa ADR ou no ficheiro certo.
