# ADR 0011 — Configuração por tenant em três formas, e nenhuma é um motor de configuração

**Contexto.** A direcção nova pede que cada empresa personalize a app, e a primeira versão é **menu +
limiares e unidades**: esconder, reordenar e renomear itens de menu, limiar de aviso de validade,
mínimos por artigo, hora do dia de negócio, unidades preferidas. O risco não é escrever estas cinco
coisas — é a forma que se lhes dá. Uma tabela `chave`/`valor` ou um `JSONField` de settings é o sítio
onde todas as perguntas não decididas vão viver, não tem tipos, não aparece no `schema.yml` e portanto
é invisível ao gate de diff do `types.ts` (`ARCHITECTURE.md` §5). E há uma armadilha estrutural: um
`GET /configuracao` agregado teria de ser uma view a importar o `api.py` de três módulos, o que inverte
o grafo de dependências — todos importam `accounts.api`, nunca o contrário (`ARCHITECTURE.md` §6b).

**Decisão.** Três formas, e nada fora delas.

**1. Uma coluna na linha que descreve.** Tudo o que é por artigo, por localização ou por fornecedor é
coluna na tabela desse objecto: o mínimo do artigo e a unidade em que o staff o conta são colunas do
artigo. **Nunca uma linha de settings indexada por id de objecto** — isso é um armazém chave/valor com
passos a mais, e é por aqui que o motor genérico entra.

**2. Uma linha por tenant, no módulo que é dono do significado.** A hora do dia de negócio e o
horizonte de aviso de validade são do `inventory`: definem o que conta como "deitado fora hoje" e que
lotes são alerta. `tenant_id` único e política, como qualquer tabela de dados de um tenant. **Os
defaults vivem em código e a linha nasce na primeira escrita**; quem lê chama
`inventory.api.configuracao(tenant_id)` e recebe os defaults quando a linha não existe. O
`accounts.criar_tenant` **não** a pode criar — o `accounts` não importa nada —, e fazê-lo por evento
exigia o consumidor da outbox, que não existe.

**3. Uma projecção sobre um registo de rotas que é código** — o menu, e só o menu.
`accounts_tenantmenuitem`, com `tenant_id` e política: `route_id` de uma **lista fechada que é do
backend**, mais `grupo`, `ordem`, `visivel` e `rotulo`. Uma lista com um nível de agrupamento, nunca
uma árvore (ADR 0009). Três colunas mutáveis não são um armazém chave/valor. A lista fechada viaja no
enum do OpenAPI, o `types.ts` carrega a união e o registo do frontend é um `Record<RotaId, …>`, igual à
lista do backend nos dois sentidos sob `pnpm typecheck`.

**Como chega ao cliente.** O menu viaja **na resposta do `GET /api/v1/auth/sessao`**: é o mesmo módulo,
e o menu resolve-se com exactamente o que a sessão já resolveu — o tenant activo —, pelo que não custa
um round trip no caminho crítico do primeiro paint da sidebar. É filtrado pelo **papel** de quem pede,
contra o papel mínimo que o registo declara: a configuração é por tenant, a resposta é por
(tenant, papel), porque esconder um item que um `staff` não pode usar é autorização e não preferência.
A configuração do `inventory` é endpoint próprio, pedido pelos ecrãs que precisam dela e não no
arranque. Dois endpoints e não um agregado é o preço da fronteira de módulo, e é o preço certo — um
endpoint de bootstrap é como um monólito modular cria uma vista-deus. Se o arranque ficar lento, a
resposta é `staleTime` e multiplexing, não agregação: não há sinal nenhum da secção 7 do
`ARCHITECTURE.md` para cache.

**O que impede o motor genérico, com mecanismo e não com promessa.** Nenhum par `chave`/`valor` e
nenhum `JSONField` de settings. Todo o valor configurável é coluna tipada ou campo tipado, logo aparece
no `schema.yml` e no `types.ts` commitado, e o gate de diff do CI vê-o. **Um valor configurável que o
TypeScript gerado não consegue nomear não é configuração, é um bug** — um blob de settings geraria
`Record<string, unknown>` e o gate não veria nada. Editar: `owner`, nos dois casos, no v1 (Q7 aberta).

**Alternativas.** Um módulo `settings` para tudo — teria de validar códigos de unidade e ids de artigo,
logo teria de importar `catalog` e `inventory`, e a fronteira cai no primeiro campo. Tabela
`chave`/`valor` ou `JSONField` — invisível ao único gate de contrato que existe, e torna-se o depósito
das decisões adiadas. Endpoint `GET /configuracao` agregado — inverte o grafo de imports para poupar um
round trip. `django-constance` / dynamic-preferences — configuração global de instância, não por
tenant, e nenhuma delas passa pela RLS. Menu só em código com flags de operador — rejeitado na ADR
0009. Mínimos e unidades numa tabela de settings por tenant — é a forma 1 ao contrário, e dá um
chave/valor indexado por `product_id`.

**Consequências.** Duas tabelas novas, as duas com `tenant_id` e portanto as duas com política na
migração que as cria; as listas fechadas do `test_db_roles.py` não mudam, e isso é o sinal de que esta
ADR não abriu excepção nenhuma. **Um conflito que não resolvo em silêncio:** a proibição nº 7 do §4 do
`docs/sessao-0-guiao.md` diz "ecrã de configurações com limiares... não lhe dês um painel, que é o que
te faz perder o default", e o dono do produto acaba de pedir esse painel para o v1. As duas coisas são
verdade sobre coisas diferentes, e vale a pena separá-las: **ser configurável remove o risco de uma
resposta global errada; um painel visível remove o sinal que diz qual é o default certo** — e só a
primeira é comprada por esta ADR. A minha recomendação, que é sequência e não desempate: o painel
entra como produto, e na sessão 0 não se mostra; o limiar continua visível **dentro** do alerta, como o
guião desenhou. É decisão do dono do produto. Fica também adiado, com gatilho no primeiro pedido real:
colunas visíveis, vistas guardadas e layout por utilizador — é a coisa seguinte que um utilizador de
ERP pede e é um desenho maior (por utilizador ou por tenant? exportação? filtros guardados?).
**Consultar `domain-expert`:** o default da hora do dia de negócio e do horizonte de validade; se o
mínimo é por artigo ou por (artigo, localização) — a sonda da Q2 compara o **mesmo** mínimo contra o
consolidado e contra cada loja, o que se lê como um mínimo por artigo, e isso é afirmação de domínio e
não minha; e qual das três unidades é a "preferida" (de contagem, de compra, de consumo).
