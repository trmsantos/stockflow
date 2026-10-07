# ADR 0018 — O estabelecimento de demonstração é um tenant, e não um modo

**Contexto.** O dono do produto aprovou ("Sim concordo com a parte da demo") a proposta de um
**estabelecimento de demonstração semeado**, que aparece no seletor que já existe no pé da sidebar, em
vez de um "modo" que troca a fonte de dados. O argumento que ele aceitou é o que esta ADR registra: um
modo é uma segunda fonte de verdade com um ramo em cada endpoint e os bugs todos na costura; um tenant de
demonstração **não traz conceito novo** — a RLS já o isola, o seletor já funciona, o `TenantMiddleware` já
exige um `Membership` por pedido, e tudo lá dentro comporta-se exactamente como em produção, incluindo o
ledger ser append-only. O que falta decidir é mecânico: como é semeado, como se distingue, de que são
feitos os dados, quem o vê, e o que impede alguém de registar uma quebra no sítio errado.

**Decisão 1 — É um tenant como qualquer outro, e nenhum endpoint sabe que ele existe.** Zero ramos, zero
parâmetros, zero cabeçalhos. A única coisa que o distingue é uma coluna de leitura, e ela não altera o
comportamento de nenhum service. É esta propriedade — **o demo não acrescenta caminho de código** — que
faz dele a opção mais segura das duas, e não apenas a mais simples: um modo seria um ramo, por endpoint,
que escolhe a fonte de dados a partir de um argumento, e um ramo desses é a ameaça "acesso a dados de
outro tenant" do `SECURITY.md` §1 a nascer dentro da nossa própria app.

**Decisão 2 — Uma coluna `is_demo` no `accounts_tenant`, que viaja no contrato como `demonstracao`.** A
tabela é o tenant e já tem política sobre `id` (ADR 0007), logo não há nada a acrescentar à RLS. Passa o
teste que a ADR 0013 escreveu para esta tabela — *uma coluna vai para o `accounts_tenant` se descreve a
**entidade***: que tipo de estabelecimento isto é está no papel de carta, ao lado do nome e do regime de
IVA. A segunda metade do teste ("lida por dois ou mais módulos") **ainda não se verifica** e fica
nomeada: hoje só o `accounts` a lê, e o leitor futuro com nome é o `billing` (fase 3), que não pode contar
estabelecimentos de mentira num plano por nº de utilizadores e localizações. O nome é duplo de propósito e
não por descuido: a coluna segue a convenção de booleano da sua própria tabela e dos vizinhos
(`is_active`, `is_staff`), e o campo segue o vocabulário português dos endpoints do `accounts` (`papel`,
`rotulo`, `visivel`). Viaja no `TenantOut`, logo chega ao `tenant_ativo` e a cada entrada da lista do
`SessaoOut` — que é exactamente o que o seletor e o cromado precisam, sem pedido novo.

**Decisão 3 — Semeado por um comando `manage.py` em `apps/demo/`, um módulo-sumidouro de escrita: sem
models, sem migrações, sem `api.py`, sem endpoints.** Só um `management/commands/semear_demonstracao.py`
que chama os `api.py` dos outros módulos, dentro de `tenant_scope(uuid)` aberto explicitamente, com a
credencial da app — que é o padrão que a ADR 0007 já fixou para acesso operacional. É o espelho de escrita
do `reporting` da ADR 0013: as **únicas** arestas são de saída, e um contrato `forbidden` novo
(o 15.º) proíbe que alguém o importe. A razão de não o pôr num módulo existente é a que torna isto um
mecanismo e não uma intenção: `purchasing` podia hospedá-lo sem nenhuma aresta nova, mas um semeador
**dentro** de um módulo de domínio está dentro da casa e pode escrever directamente nos `models.py` dele;
de fora, o import-linter **não o deixa** fazer outra coisa que não seja entrar pela porta da frente de
cada módulo. E é isso que compra a propriedade que justifica a decisão 1: os dados do demo são produzidos
pelos **mesmos services** que os dados reais, logo o ledger, o FEFO, o CMP e os lotes comportam-se lá
exactamente como aqui. Um semeador que escreva `StockLevel` à mão produz um estabelecimento que ensina um
produto que não existe — a mesma razão com que a ADR 0008 escreveu "stock é um ledger, também na mentira".

**Decisão 4 — Os dados são sintéticos por construção, e nunca uma cópia de dados de um cliente, nem
anonimizada.** Um gerador determinístico com semente fixa — os mesmos artigos, fornecedores, validades e
movimentos em cada corrida, para um screenshot de hoje valer amanhã. Uma cópia anonimizada **continua a
ser uma cópia**: nomes de fornecedores, preços de compra e volumes são informação comercialmente sensível,
e um restaurante reidentifica-se a partir do padrão de compras com uma facilidade desconfortável (o
fornecedor, o volume, a localidade). E não há base legal para replicar os dados de um cliente para dentro
de outro tenant. A regra é absoluta porque a excepção é indefensável uma a uma.

**Decisão 5 — Reinicializar é criar outro e revogar a pertença ao antigo; apagar é tarefa de operador.** O
caminho normal **nunca apaga nada**, e isso não é zelo: o `inventory_stockmovement` nasce com
`REVOKE UPDATE, DELETE ... FROM stockflow_app` (`SECURITY.md` §3), logo o role da app não consegue limpar
um ledger, e é bom que não consiga. Reinicializar é correr o comando outra vez: tenant novo com uuid novo,
pertença nova, e a pertença ao demo anterior revogada — a partir desse momento ele é inalcançável por
quem quer que seja, porque a query do `TenantMiddleware` devolve zero linhas e a resposta é 403 (ADR
0007). Limpar os órfãos é tarefa de operador com o `stockflow_owner`, e a guarda é a coluna da decisão 2:
**recusa qualquer tenant sem `is_demo`**. A coluna ganha o seu lugar duas vezes — uma no cromado, outra
aqui, a impedir que um comando destrutivo seja apontado a um cliente.

**Decisão 6 — Quem o vê: quem tiver um `Membership` nele, e mais ninguém.** É concedido pelo mesmo caminho
de sempre (o comando de operador, ou um convite), e aparece no seletor porque o seletor lista pertenças —
nenhum código novo. Logo **não há demonstração para quem não tem conta**: o registo self-service não
existe no v1 (ADR 0010) e esta ADR não o reabre. **Um demo por conta que o pede**, e não um partilhado: um
demo partilhado é mutável por todos os que o vêem, e a primeira pessoa que lá registar uma quebra muda o
que a próxima encontra; reinicializá-lo apanharia alguém a meio. O custo fica nomeado: tenants de
demonstração acumulam-se como linhas mortas até alguém os limpar, e o `billing` da fase 3 tem de os
filtrar — está escrito aqui para o agente dessa sessão o encontrar.

**Decisão 7 — O cromado passa a ser de tenant, e a faixa não se fecha.** Hoje o badge "dados de
demonstração" do `shell/app-header.tsx` é **de ambiente** (`import.meta.env.DEV`, porque quem responde é o
servidor de fixtures) e o `features/reporting/screens/painel.tsx` tem o parágrafo equivalente. Passa a
haver um sinal **de tenant**, ligado ao `tenant_ativo.demonstracao`, na barra de topo — que é `sticky`,
logo está sempre à vista em todos os ecrãs — e o item do seletor marcado na lista e no botão em repouso,
para o pé da sidebar responder "onde estou" sem abrir a lista. Usa os papéis de banner que já existem
(`--color-warning-surface` e `-border`, texto em `--color-foreground`), porque não se inventam cores
(`DESIGN.md` §2) e porque o amarelo é o registo certo: é um aviso, não um erro.

**As duas afirmações não se juntam num badge só, e isto é a parte fácil de "simplificar" para o lado
errado.** "O servidor de fixtures respondeu" e "estás no estabelecimento de demonstração" são afirmações
diferentes: a primeira é sobre o ambiente de desenvolvimento e a segunda é a que tem de funcionar **em
produção**. Colapsá-las dava um sinal de produção que só é testável num ambiente onde está sempre ligado —
o modo de falha é ele nunca aparecer onde interessa e ninguém notar. O badge de DEV fica, a dizer o que é
(o servidor de fixtures), e o de tenant entra ao lado.

**Decisão 8 — O demo é escrevível, e o que o protege é a sinalização e não um `read_only`.** "Tudo lá se
comporta exactamente como em produção" é a decisão inteira: não se aprende o Contar sem contar, nem o
Receber sem confirmar uma receção. E **nada passa do demo para o estabelecimento a sério** — não há
importação, não há promoção, nunca. Essa seria a única feature capaz de transformar o demo numa segunda
fonte de verdade, que é precisamente o que esta ADR recusou na decisão 1. O risco simétrico — alguém
registar no demo uma quebra que era a sério — é real e o que o limita é a faixa permanente, o seletor
marcado e o facto de o demo ter um nome que não é o do estabelecimento da pessoa.

**O risco de a demonstração viver na mesma base de dados de produção, nomeado.** **Não** é fuga entre
tenants: o isolamento é o mesmo de qualquer outro cliente, pela mesma política, na mesma ligação sem
`BYPASSRLS` (ADR 0006). São três outras coisas. **Contamina agregados**: qualquer contagem de
estabelecimentos, métrica operacional ou plano de `billing` passa a incluir estabelecimentos falsos — a
coluna existe antes do `billing` precisamente para ele poder filtrar. **Contamina o que itera tenants**:
o cron da ADR 0005 que enfileira uma tarefa por tenant e o digest diário do `notifications` **saltam os
`is_demo`**, porque um alerta de validade sobre stock inventado ensina a ignorar alertas, que é o pior
estrago possível neste produto. E **custa espaço, backups e tempo de restore**, o que é pequeno e aceite.
O que torna o conjunto aceitável é a decisão 1: zero caminhos de código novos. A alternativa — uma
instância ou base de dados separada — trocaria estes três custos por um ambiente que divergiria do real na
primeira migração e por uma segunda superfície a manter, sem sinal nenhum da secção 7 do
`ARCHITECTURE.md`.

**Alternativas.** *Um "modo de demonstração" que troca a fonte de dados* — é a forma que o pedido assumia
e é a que o dono recusou com o argumento acima: um ramo por endpoint, e o ramo decide de onde vêm os
dados. *Uma base de dados ou instância separada* — divergência garantida e o dobro da operação.
*Um tenant de demonstração partilhado* — mutável por todos, e reinicializá-lo apanha alguém a meio.
*Uma cópia anonimizada de um cliente real* — decisão 4. *Um demo só de leitura* — ensina metade do
produto, e a metade que ensina é a que ninguém precisa de aprender. *Dados falsos pelo servidor de
fixtures em produção* — a ADR 0008 fechou essa porta por impossibilidade (`apply: "serve"`, nada em
`src/` importa `fixtures/`, e o CI varre a sentinela do `dist/`), e reabri-la para isto seria desfazer o
único gate de mentira que existe. *Importar o demo para o estabelecimento a sério, depois* — decisão 8.

**Consequências.** Uma coluna no `accounts_tenant` (sem migração de política nova — já existe sobre `id`),
um campo no `TenantOutSerializer`, `pnpm gen:api` e o gate de diff do `types.ts`. Um módulo novo sem
tabelas (`apps/demo/`) e os contratos de import-linter passam de 14 para 15, com `apps.demo` a entrar
também nas listas `forbidden_modules` dos outros, como a ADR 0013 fez para o `reporting`. As duas listas
fechadas do `tests/test_db_roles.py` **não mexem**, e o `APPEND_ONLY` também não. No frontend: o
`TenantOut` do Zod ganha o campo, o `SessaoDoShell` ganha-o no `EstabelecimentoDoShell` (é informação de
shell, como o `papel` já é, e chega como dado e não como tipo de domínio), e o `app-header.tsx` ganha o
sinal de tenant ao lado do de ambiente. **Consultar `domain-expert`**: os valores do semeador são
afirmações de domínio — artigos, unidades, validades, lotes, preços de fornecedor, uma contagem com
divergência, um desperdício com motivo — e um demo que mostre números que um pasteleiro não reconhece é
pior do que não ter demo. O gerador é também o instrumento mais barato para a sessão 0 depois do servidor
de fixtures, porque é o mesmo ecrã com o backend verdadeiro atrás.

**O que fica por decidir.** Se o demo expira sozinho (um TTL na pertença, para não acumular), o que exige
um conceito de pertença com data de fim que hoje não existe. Se há demonstração para quem ainda não é
cliente, que é o registo self-service da ADR 0010 e três perguntas em aberto. E o nome do
estabelecimento, que é copy e é do dono — "Pastelaria de Demonstração" é um exemplo e não uma decisão.
