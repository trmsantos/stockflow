---
description: Revisão completa do diff atual — arquitetura, código, UI e segurança
---
Revê o diff atual (`git diff main...HEAD`):

1. `architect`: as alterações respeitam ARCHITECTURE.md? Fronteiras, ledger, outbox. Lista violações.
2. `backend` (só leitura): services vs views, serializers, N+1, testes em falta.
3. `frontend` (só leitura): DESIGN.md — tokens, estados, a11y, anti-padrões.
4. `security-reviewer`: PASS/FAIL.

Consolida num único relatório: bloqueadores · deve-corrigir · sugestões. Sem repetir o mesmo problema em duas secções.
