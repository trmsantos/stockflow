# ADR 0012 — Bloquear ou avisar sem stock não é configuração

**Contexto.** A pergunta 1 das onze é "bloquear ou avisar quando falta stock", e a direcção nova
torna-a tentadora: se a hora do dia de negócio e o limiar de validade passam a ser configuráveis, isto
parece-se com um vizinho — um interruptor por empresa, e a pergunta desaparece. As outras duas de facto
**desarmam-se**: deixam de ser "qual é a resposta?" e passam a ser "qual é o default?". Esta não. O
`docs/sessao-0-guiao.md` §4 proíbe bloqueio duro em qualquer sítio do shell precisamente porque
bloquear **é** a Q1 e o shell não responde pelo dono; o §5 lista "stock negativo permitido com aviso"
como **hipótese** e diz explicitamente que nenhuma hipótese entra numa migração antes da sessão 0.

**Decisão.** A Q1 **não entra no primeiro conjunto configurável, e também não entra numa linha de
settings mais tarde.** O que esta ADR decide é só isto: é um **invariante do ledger**, com um ponto de
imposição único em `inventory.services`, respondido uma vez para o produto pela sessão 0 — não é uma
preferência por tenant. O shell continua a mostrar a variante permissiva, que é a sonda e não a
resposta: a hipótese do §5 do guião fica hipótese, e nada migra por causa desta ADR.

**O preço da alternativa configurável, para a resposta poder ser orçamentada antes de ser dada.**
Suportar os dois comportamentos são dois caminhos pela função mais testada do sistema. "Bloquear"
significa uma pré-verificação sob `FOR UPDATE` nas linhas de `StockLevel` **antes** de escolher o lote —
a ADR 0005 já exige trancar antes de escolher para o FEFO, porque escolher e depois trancar é o bug;
significa recusa **por linha** e nunca por lote, porque uma contagem de 40 artigos sincronizada à saída
de uma câmara frigorífica não pode perder 39 por causa de uma (ADR 0005, restrições de domínio); e
significa decidir o que um bloqueio quer dizer para um movimento registado num telemóvel há duas horas
que só agora chega. **É esta última que resolve a questão: bloquear é um conceito sincrónico e os
fluxos de campo são assíncronos.** Uma recusa que chega depois do facto não é um bloqueio, é uma
rejeição para reconciliar, e não existe ecrã nem estado para isso. O append-only fecha a outra saída:
um movimento não se desescreve, logo "bloqueado" só pode querer dizer "recusado na escrita" e nunca
"reparado depois". Se um dia os dois forem precisos a sério, a forma não é um booleano numa linha de
settings — é uma política nomeada com um ponto de imposição só, decidida com o caso à frente.

**Alternativas.** Booleano por tenant agora — é o pedido, e é o que esta ADR recusa pelo parágrafo
acima. `CHECK (quantity >= 0)` na migração — não pode ser condicional a uma linha por tenant, e
transforma uma regra de negócio num `IntegrityError` no ponto onde a resposta por linha já é
impossível. Bloquear só em alguns fluxos (consumo sim, quebra não) — plausível, e é exactamente o tipo
de coisa que tem de vir da sessão 0 e não daqui. Bloquear por artigo (no bacalhau sim, nas saquetas de
açúcar não) — a variante mais defensável de todas, e a razão pela qual isto é pergunta de domínio e não
de arquitectura.

**Consequências.** Nada migra e nada muda no shell: a proibição nº 3 do §4 do guião (sem bloqueio duro
em sítio nenhum) continua em vigor, e esta ADR é a razão escrita. A pergunta fica **aberta**, e o
gatilho para reabrir esta ADR é a resposta da sessão 0; se for "bloquear", o custo acima é a estimativa
e aterra em `inventory.services`, na sessão do ledger, antes de qualquer migração. **Consultar
`domain-expert`** — e a sessão 0, que é onde esta se responde.
