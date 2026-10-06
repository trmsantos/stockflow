# ADR 0017 — Dois ecrãs de configurações, porque há duas famílias e confundi-las é um bug de autorização

**Contexto.** O dono do produto diz que "settings personalizáveis era bastante importante", e a ADR 0011
já respondeu à parte difícil: a configuração por tenant existe em **três formas** — coluna na linha que
descreve, uma linha por tenant no módulo dono do significado, e uma projecção sobre um registo de rotas
que é código — e **recusou explicitamente um motor de configuração genérico**, com mecanismo: nenhum par
`chave`/`valor`, nenhum `JSONField`, todo o valor configurável tipado e portanto visível no `schema.yml`
e no `types.ts` que o CI compara. Esta ADR não reabre nada disso. Decide o **ecrã**: o que lá vai, quem
pode mudar o quê, e como é que a fronteira entre as duas famílias de definições se lê sem se ler o
código. As duas famílias são: **da pessoa** (o tema da ADR 0016, e pouco mais hoje) e **da empresa** (o
menu, os limiares, as unidades, a hora a que o dia de negócio começa, o regime de IVA). Um `staff` muda
o seu tema; não muda o limiar de validade da empresa. A ADR 0011 já disse que esconder é apresentação e
não autorização, logo a imposição é do endpoint.

**Decisão 1 — Dois ecrãs, não um ecrã com duas secções.** `/preferencias` (a pessoa) e `/configuracao`
(a empresa). Três razões, e a terceira é a que decide: um ecrã único seria um ecrã cujo **conteúdo
inteiro** depende do papel, que é a forma de UI do "200 parcial" que a ADR 0013 rejeitou; os dados vêm de
módulos diferentes e a ADR 0011 proibiu o endpoint agregado, logo um ecrã único seria o sítio onde
alguém o pediria outra vez; e **a distinção fica legível no próprio menu** — `configuracao` entra no
registo de rotas com `papeis = {owner}`, como o `convites`, pelo que a um `staff` o item simplesmente não
existe, em vez de existir e levar a um 403. Esse é o único "como se lê no ecrã" que não é um ícone a
explicar uma regra.

O `/preferencias` **não** entra no registo do menu, e o seu ponto de entrada é o **pé da sidebar**, ao
lado do email e da saída da conta — que é onde "a tua conta" vive, e é o shell, que é o lado certo
porque o tema é da pessoa e não do estabelecimento. Um sétimo item de menu para uma coisa que se toca
duas vezes por ano é ruído num menu que a ADR 0009 desenhou para crescer com o domínio; e uma rota
pessoal dentro de uma projecção **por tenant** deixava uma empresa esconder um ecrã pessoal aos seus
colaboradores, que é exactamente a mistura que esta ADR existe para evitar. Gatilho para reverter: se na
sessão 0 alguém a procurar no menu — é uma entrada no registo dos dois lados.

**Decisão 2 — O contrato: nenhum agregado, e metade dele já existe.** Caminhos e vocabulário dos
vizinhos do `accounts` (português, como `/convites` e `/menu`).

```python
# PATCH /api/v1/auth/preferencias      autenticado, qualquer papel  -> SessaoOut   (ADR 0016)
# GET   /api/v1/menu/rotas             owner  (existe)              -> lista de RotaDeMenuOut
# PUT   /api/v1/menu                   owner  (existe)              -> lista de ItemDeMenuOut
# GET   /api/v1/estabelecimento        owner                        -> EstabelecimentoOut
# PATCH /api/v1/estabelecimento        owner                        -> EstabelecimentoOut
# GET   /api/v1/inventory/configuracao owner  (ADR 0011, forma 2)   -> ConfiguracaoDeInventarioOut
# PUT   /api/v1/inventory/configuracao owner                        -> ConfiguracaoDeInventarioOut

@dataclass(frozen=True, kw_only=True, slots=True)
class EstabelecimentoOut:              # accounts — descreve a **entidade** (ADR 0013)
    id: UUID
    nome: str
    vat_regime: str                    # normal | isento_art_53
    business_day_starts_at: str        # "04:00"
    demonstracao: bool                 # só de leitura (ADR 0018)

class EstabelecimentoIn:               # serializer de escrita: `fields` listados, sem `__all__`
    nome: str
    vat_regime: str
    business_day_starts_at: str
```

**Não há `GET /menu`, e isso é decisão de quem o implementou e não um esquecimento**: o menu efectivo
viaja no `GET /auth/sessao` e o registo no `GET /menu/rotas`, logo um terceiro endpoint seria uma
terceira fonte para a mesma lista. O ecrã da empresa compõe-se desses dois, e a resposta do `PUT` é a
configuração como ficou, **sem filtro de papel** — é por isso que ela não é filtrada. A consequência
fica nomeada aqui porque é deste ecrã: o `menu` da sessão **é** filtrado pelo papel, pelo que um `owner`
só configura as rotas que o papel dele vê. Hoje coincide (a única rota restrita é a dos `convites`, e é
restrita **ao** `owner`, e a `configuracao` segue-a), e no dia em que uma rota for visível a um papel que
quem configura não tem, este ecrã passa a precisar de um `GET /menu` sem filtro. É um gatilho, não uma
dívida a pagar agora.

A forma do `ConfiguracaoDeInventarioOut` é do `inventory` e não se escreve aqui — a tabela ainda não
existe e o seu conteúdo é afirmação de domínio. O que esta ADR fixa é que ela é **um endpoint próprio,
pedido pelo ecrã e não no arranque**, e que os seus defaults vivem em código com a linha a nascer na
primeira escrita (ADR 0011). **Eventos: nenhum.** Não há consumidor da outbox, e um evento sem subscritor
é um contrato público escrito ao contrário. **Tarefas Celery: nenhuma. Cache: nenhuma** — sem sinal da
secção 7 do `ARCHITECTURE.md`, e a ADR 0011 já fixou que a resposta a lentidão é `staleTime`.

**Decisão 3 — Quem pode o quê, e o que acontece a quem não pode: 403, seguindo a ADR 0013.** O tema é de
quem o pede e a escrita é sempre sobre o `request.user`, sem `user_id` no corpo: não há objecto para
autorizar nem caminho para a preferência de outra pessoa (ADR 0016). A empresa é `owner` em **leitura e
escrita** no v1 — é o que a ADR 0011 escolheu para editar, estendido à leitura pelo argumento da ADR 0013
(*o default é o mais fechado, e um conjunto de um elemento alarga-se sem se desfazer*) e porque nada fora
deste ecrã precisa destas leituras por HTTP: o `vat_regime` é consumido pelo `reporting` do lado do
servidor, através do `accounts.api`. **403 e não 200 com blocos ausentes**, com a forma exacta do DRF
(`detail`, **sem `code` novo**), e o argumento da ADR 0013 vale aqui com uma nota a mais: num ecrã de
configurações, um 200 parcial torna "não podes ver isto" indistinguível de "esta empresa ainda não
configurou nada", e os dois precisam de ecrãs opostos — o vazio ensina a configurar, o restrito não pode.
O cliente já sabe o papel antes de pedir (vem na sessão), logo não monta o ecrã e não dispara o pedido; o
403 é a rede do deep link e da pertença revogada a meio da sessão, que é o caso que a ADR 0007 fez ser
verificado por pedido.

**Decisão 4 — O que **não** entra na v1, porque "settings personalizáveis" é um convite ao motor
genérico.** Nada de `chave`/`valor` e nada de `JSONField`: um valor configurável que o TypeScript gerado
não consiga nomear não é configuração, é um bug (ADR 0011). Em concreto, ficam fora:

- **As unidades e os mínimos não vivem neste ecrã**, e isto é a correcção mais importante ao pedido tal
  como chegou: são **colunas do artigo** (ADR 0011, forma 1), editadas na linha do artigo. Pô-los num
  ecrã de configurações é o armazém chave/valor indexado por `product_id` que a 0011 recusou, com passos
  a mais.
- **O NIF não entra**, apesar de descrever a entidade: exige `nif_encrypted` + `nif_hmac` com pepper fora
  da base de dados (`SECURITY.md` §3) e tem a questão do NIF duplicado em aberto desde a ADR 0007. É
  sessão própria e está nomeado como tal.
- **Colunas visíveis, vistas guardadas e layout por utilizador** — já adiado pela ADR 0011 com gatilho no
  primeiro pedido real, e continua adiado; é a coisa seguinte que um utilizador de ERP pede e é um
  desenho maior do que este ecrã.
- **Cor de acento, densidade e tamanho de letra configuráveis** — a paleta e a densidade **são** a
  identidade, e o gate de cor mede ficheiros e não linhas de base de dados: um acento escolhido num
  formulário é uma paleta que ninguém mediu (ADR 0015).
- **Um tema imposto pelo estabelecimento** — a preferência é da pessoa (ADR 0016), e um default por
  empresa é um pedido plausível com uma ADR pequena, não uma linha deste ecrã.
- **Idioma, fuso horário e preferências de notificação** — nenhum módulo as consome hoje e o
  `notifications` não tem consumidor da outbox; três campos sem leitor são três campos a decidir por
  omissão.

**Alternativas.** *Um ecrã com duas secções e as da empresa escondidas a quem não é `owner`* — é a forma
que o pedido assumia; rejeitada porque esconder é apresentação e o ecrã ficaria a ser dois ecrãs com uma
rota, e porque convida ao endpoint agregado que a ADR 0011 recusou. *Um ecrã com abas e um 403 por aba* —
põe a autorização no desenho da navegação e dá a um `staff` uma aba que lhe responde erro. *Um módulo
`settings` que junte tudo* — a ADR 0011 já o rejeitou com a razão estrutural: teria de validar códigos de
unidade e ids de artigo, logo teria de importar `catalog` e `inventory`, e a fronteira cai no primeiro
campo. *`GET /configuracao` agregado* — inverte o grafo de imports para poupar um round trip (ADR 0011).
*Pôr o `/preferencias` no registo do menu* — ver a decisão 1: uma rota pessoal numa projecção por tenant.

**Consequências.** Zero tabelas novas no `accounts`: o ecrã da empresa escreve colunas que a ADR 0013 já
decidiu (`vat_regime`, `business_day_starts_at`) e a projecção de menu que a ADR 0011 já criou. As listas
fechadas do `tests/test_db_roles.py` não mexem. O `RotaDeMenu` ganha `configuracao` **e** o
`REGISTO_DE_ROTAS` do shell ganha a entrada no mesmo commit — não há escolha nisto: o
`Record<RotaId, EntradaDoRegisto>` é exaustivo nos dois sentidos e um id só num dos lados não compila (a
sonda que o `registo-de-rotas.ts` documenta usa, por coincidência útil, este mesmo id). No frontend o ecrã
da empresa vive em `features/accounts/screens/` e lê a configuração do `inventory` pela porta
pré-aprovada da ADR 0008 (`@/features/inventory/api`), que é a única aresta entre features que o
`eslint.config.js` permite. O `/preferencias` não está no `REGISTO_DE_ROTAS`, logo a barra de topo não o
nomeia e o ecrã carrega o seu próprio `<h1>` visível, como qualquer ecrã de detalhe. **Consultar
`domain-expert`**: a ADR 0011 já o deixou em dívida para o default da hora do dia de negócio e do
horizonte de validade, e este ecrã é o primeiro sítio onde esses defaults aparecem escritos a alguém —
mostrar um limiar é remover o sinal que diz qual é o default certo, que é a tensão com a proibição nº 7
do §4 do `docs/sessao-0-guiao.md` que a ADR 0011 nomeou e não resolveu em silêncio.

**O que fica por decidir.** Se o tema se troca também no pé da sidebar, sem abrir ecrã: hoje há **um**
controlo, no `/preferencias`, e o pé tem o atalho para lá — um segundo controlo é uma segunda fonte para
o mesmo gesto, e o gatilho para o acrescentar é alguém à procura dele. E se um `manager` configura a
empresa: é a Q7, está marcada como "não inventes default sem falar com um utilizador real", e o conjunto
`{owner}` alarga-se sem se desfazer.
