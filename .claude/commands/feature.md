---
description: Implementa uma feature de ponta a ponta com o pipeline architect → domain-expert → backend → frontend → security-reviewer
argument-hint: <descrição da feature>
---
Implementa a feature: $ARGUMENTS

Segue exatamente esta sequência, delegando a cada subagent e esperando o resultado antes de avançar:

1. `architect`: módulo, contrato, ADR. Mostra-me o contrato e **pára para eu aprovar** antes de continuar.
2. Se a feature tocar em stock, compras, receitas, contagens ou faturas: `domain-expert` valida regras e casos limite.
3. `backend`: implementa, testa, regenera OpenAPI e tipos TS.
4. `frontend`: implementa a UI a partir dos tipos gerados.
5. Corre `pnpm typecheck && pnpm lint` e `uv run pytest`. Se falhar, volta ao agente responsável.
6. `security-reviewer`: relatório com PASS/FAIL. Se FAIL, volta ao agente responsável e repete.

No fim: resumo em 5 linhas, ficheiros tocados, comandos para eu testar localmente, o que ficou por decidir.
