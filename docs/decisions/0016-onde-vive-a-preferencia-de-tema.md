# ADR 0016 — Onde vive a preferência de tema, e o relâmpago da primeira pintura

**Contexto.** O tema é preferência **da pessoa** e não da empresa: dois encarregados do mesmo
estabelecimento podem querer temas diferentes, e o dono que usa o portátil na copa com a persiana
fechada quer o escuro mesmo que a contabilista queira o claro. Há três sítios possíveis — coluna no
`accounts_user`, tabela de preferências, armazenamento local — e um problema que **os três** têm: numa
SPA a folha de estilos é bloqueante e o módulo de entrada é diferido, logo o fundo da página é pintado
**antes** de a sessão chegar. Com a preferência no servidor, quem escolheu o claro vê um relâmpago
escuro em cada arranque, que é o mesmo defeito e na mesma superfície que o `color-scheme` do §2 do
`DESIGN.md` existe para evitar. O `CLAUDE.md` diz "sem tokens em localStorage", e a primeira pergunta é
se essa regra alcança o **nome** de um tema.

**Decisão 1 — Uma coluna `tema` no `accounts_user`, e o precedente é desta casa.** `escuro` por
omissão, não nula, com os três valores da ADR 0015. A ADR 0007 manda **encolher** o `accounts_user`,
porque é a tabela que o role da app lê sem âmbito nenhum, e essa regra é sobre o que um atacante
aprende sobre **identidade e o grafo de pertenças** — "esta conta prefere o claro" não acrescenta nada a
nenhum dos dois. O que decide é a forma: a ADR 0007 já escolheu uma coluna em vez de uma tabela para o
`tenant_ids` com o argumento exacto que serve aqui — *uma tabela de índice teria `tenant_id` sem
política, que é a forma que o gate nunca pode deixar passar; uma coluna numa tabela que já não tem
política não introduz forma nova*. Uma tabela de preferências global entrava na lista `SEM_POLITICA` do
`tests/test_db_roles.py`; uma por tenant era pior do que inútil, porque dava à contabilista três temas
para três estabelecimentos e deixava o `/entrar` e o estado `escolha_pendente` sem tema nenhum, que é
precisamente onde a primeira pintura acontece. **As duas listas fechadas do `test_db_roles.py` não
mexem**, e é esse o sinal de que esta ADR não abriu excepção.

**Decisão 2 — Viaja no `SessaoOut` e escreve-se num quinto endpoint com a mesma forma.** O `utilizador`
do `SessaoOut` é hoje `{id, email}` e ganha `tema`, pela razão com que a ADR 0011 pôs lá o menu:
resolve-se com exactamente o que a sessão já resolveu e não custa um round trip no caminho crítico.

```
PATCH /api/v1/auth/preferencias    autenticado, qualquer papel, tenant_scope_exempt
      PreferenciasIn  { tema }                      -> 200 SessaoOut
```

Devolve `SessaoOut` e não um objecto próprio, pelo argumento que a ADR 0010 já escreveu para os outros
quatro: *o cliente guarda uma entrada de cache e qualquer destas respostas a substitui*, em vez de uma
quinta forma e um quinto ramo de Zod. Dispensado de âmbito porque escreve numa tabela sem política e tem
de funcionar em `escolha_pendente` e em `sem_estabelecimento` — um tema que só se possa trocar depois de
escolher o estabelecimento é um tema que não se troca no ecrã onde o relâmpago se vê. **Dispensa-se do
âmbito e não do CSRF** (`SECURITY.md` §5): aqui não faz falta decorador nenhum, porque o pedido é
autenticado e o `SessionAuthentication` verifica o token quando encontra utilizador na sessão — o furo da
ADR 0010 era dos endpoints **anónimos** de escrita. Fica escrito para ninguém o "corrigir" nos dois
sentidos. E a escrita é sempre sobre o `request.user`: **não há `user_id` no corpo**, logo não existe
objecto para autorizar nem caminho para a preferência de outra pessoa. O endpoint entra na lista fechada
de dispensas do `tests/test_rls_isolation.py`, que é onde ela vale.

**Decisão 3 — Um espelho local, e é ele que torna a primeira pintura possível.** O servidor é a fonte da
verdade — a preferência sobrevive à máquina e é a mesma em casa e no balcão —, e o cliente guarda uma
**cópia** do nome do tema em `localStorage` sempre que lê a sessão. É essa cópia que o arranque lê, antes
de haver rede. Sem ela nenhum mecanismo de pré-pintura é possível: o cookie de sessão é `httpOnly` e um
pedido à API é, por definição, depois da primeira pintura.

**A regra "sem tokens em localStorage" não alcança isto, e o teste que a impede de ser esticada é:**
*vai para o armazenamento local o que um atacante não ganha nada em ler e nada em escrever.* Um nome de
tema não é credencial, não é dado pessoal e não concede âmbito; escrever-lhe lixo dá um tema errado, e o
valor é fechado a três com queda para o default. O `SECURITY.md` §7 continua literalmente verdadeiro e
não se emenda. O que fica **nomeado**: a cópia sobrevive ao logout de propósito (limpá-la trazia o
relâmpago de volta ao ecrã de entrada), logo um portátil partilhado diz que a última pessoa que lá
entrou preferia o claro. É o que é, e é menos do que o email que o pé da sidebar mostra.

**Decisão 4 — Nada de script inline, e o custo de cada caminho em CSP é o que decide.** O `index.html`
desta SPA é **estático e servido pelo Caddy**, não renderizado pelo Django: não há nonce para injectar
(o nonce do `django-csp` vive nas respostas JSON, onde um browser não executa nada) e a CSP do documento
vem do `docker/caddy/proxy.Caddyfile` com `script-src 'self'`. Logo um `<script>` inline exigiria
`unsafe-inline` — que o job `stack` do CI recusa por `grep`, e bem — ou um `'sha256-…'` guardado no
Caddyfile, isto é, uma segunda fonte de verdade entre duas imagens sem nada que as case: o dia em que o
script mudasse, o tema parava de ser aplicado e nenhum gate dizia porquê. **Um atributo no HTML servido
está fora de questão por impossibilidade e não por gosto** — o Caddy serve um ficheiro e não sabe
descodificar um cookie de sessão do Django. **Um cookie legível por JS não compra nada** sobre o
`localStorage`: continua a precisar de JS para o aplicar, e passa a viajar em cada pedido para cada
caminho.

O que entra é o mais barato dos que funcionam: **o módulo de entrada aplica o `data-tema` antes de
montar o React**, sem ficheiro novo, sem pedido novo e sem uma linha de CSP. O que fica pintado antes
dele é o fundo de uma página vazia, no intervalo entre a folha de estilos e um módulo que já vem em
`modulepreload` pela mesma ligação. Se esse intervalo se vir num arranque frio na máquina do dono —
**medido, não presumido** —, a escalada já está escolhida e também não toca na CSP: um script **clássico
e separado**, servido do próprio domínio, bloqueante no `<head>` antes da folha de estilos. Paga-se um
pedido no caminho crítico de **todos** os arranques, incluindo os de quem usa o default, e é por isso que
se mede primeiro. Em qualquer dos dois casos, numa máquina nova o primeiro arranque pinta o default e
troca quando a sessão chega: é um relâmpago por máquina e não um por arranque, e não há forma de o evitar
sem um servidor a renderizar o documento.

**Alternativas.** *Só local, sem servidor* — não precisa de pedido e é a mais simples, e perde a
propriedade que o dono vai notar primeiro: o tema não o segue do balcão para casa, e cada browser é uma
app com outro aspecto. *Só no servidor, sem espelho* — é o relâmpago em cada arranque, aceite como "não
é nada" até alguém com o tema claro abrir a app ao escuro vinte vezes por dia. *Tabela de preferências*
— ou entra na lista `SEM_POLITICA`, ou é por tenant e responde à pergunta errada; e abre a forma que a
ADR 0011 recusou, porque uma tabela de preferências com uma coluna é uma tabela de preferências com
sete. *No `Membership`* — o tema passaria a ser da pessoa **naquele** estabelecimento, e os dois ecrãs
onde ainda não há estabelecimento ficavam sem tema. *Na sessão do Django* — morre com a sessão e com
`SESSION_SAVE_EVERY_REQUEST` escreve na tabela de sessões a cada clique; a sessão escolhe âmbito, não
guarda perfil. *Um valor `sistema` como quarto estado* — a preferência do sistema é binária e as paletas
são três, logo `sistema` só alcançaria duas e tornaria a terceira inalcançável por esse caminho; e o
default é a identidade aprovada, não a configuração do portátil. Fica de fora como o `mfa_pendente` da
ADR 0010 ficou: um valor de enum que nada produz é uma promessa no `types.ts` que ninguém cumpre.

**Consequências.** Uma coluna nova no `accounts_user` (sem política, como a tabela), um campo novo no
`UtilizadorOutSerializer`, um endpoint, `pnpm gen:api` e o gate de diff do `types.ts`. Nenhum evento,
nenhuma tarefa Celery, nenhuma chave de Redis — não há sinal nenhum da secção 7 do `ARCHITECTURE.md` e
um evento sem subscritor é um contrato público escrito ao contrário (`accounts/services.py`). O
`APPEND_ONLY` não muda: trocar de tema é um `UPDATE` e é isso que se quer. No frontend, o `features/
accounts` ganha a mutação e o espelho, e o shell ganha **um** sítio onde o tema se troca sem abrir ecrã
(ADR 0017). Prova a pedir à implementação: o `PATCH` de uma conta não altera o tema de outra; um valor
fora dos três dá 400 por campo e não um tema inválido guardado; e o espelho adulterado à mão no browser
dá o default e não uma página sem estilos.

**O que fica por decidir.** Um **default por estabelecimento** ("esta empresa abre no claro"), que é o
pedido seguinte plausível e muda a coluna de não-nula para "nunca escolheu" — hoje não existe e
inventá-lo era um quarto estado sem consumidor. E se a troca de tema deve ser registada: não é
autorização e não é dinheiro, logo não; reabre no dia em que alguém perguntar porque é que a app lhe
mudou de cor.
