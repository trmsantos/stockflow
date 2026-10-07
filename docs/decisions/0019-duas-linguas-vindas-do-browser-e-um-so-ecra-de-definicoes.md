# ADR 0019 — Duas línguas vindas do browser, e um só ecrã de Definições

**Contexto.** Dois pedidos do dono do produto (2026-10-07), e o segundo **supersede a decisão central da
ADR 0017**: (a) o ecrã não se chama "Configuração", a app tem de ter **pt-PT e inglês**, e o português
tem de ser o de Portugal; (b) as definições são **um** ecrã com secções, alcançado pelo pé da sidebar
onde está a pessoa, e o item do menu sai da sidebar. Duas respostas dele são restrições e não
hipóteses: **o i18n alcança o backend** (as recusas e as validações do DRF são lidas por quem olha — e
é verdade que o cliente as mostra tal e qual: o `erros.ts` diz "o `detail` do servidor **não é
reescrito**"), e **o idioma vem da configuração do browser**, sem selector e sem ser preferência da
pessoa no servidor. A leitura do pedido confirma-se em dois pontos e **corrige-se num**: "Definições" é
o termo pt-PT e "Configurações" é pt-BR — o próprio dono troca na segunda frase; os dois ecrãs passam a
um; e **os rótulos do menu não vêm do servidor**, ao contrário do que o pedido assume — ver a decisão 5.

**Decisão 1 — "Definições", e o vocabulário muda na copy e não no código.** O ecrã é `/definicoes`, o
`<h1>` é "Definições", o botão do pé da sidebar deixa de dizer "Preferências". O que **não** muda é
código: `GET /inventory/configuracao` (ADR 0011, forma 2), `ConfiguracaoDeInventarioOut` e o
`configuracao.tsx` são identificadores, e renomeá-los é churn sem leitor. O caminho da rota **é** copy
(ADR 0008: "os URLs são em português porque são copy de produto") e portanto muda. Mesma régua para
"aba": é a palavra do dono e é a do código do painel (`features/reporting/abas.ts`, `?aba=`), e nunca
chega ao olho — o que o painel mostra a quem ouve é `<nav aria-label="Secções do painel">`. Fica assim.

**Decisão 2 — O idioma é o `Accept-Language`, e o argumento mais forte é que não há nada a ligar os
dois lados.** O header que o browser já manda em cada pedido e o `navigator.language` que o React lê
são **o mesmo sinal da mesma configuração**: os dois lados concordam sem contrato, sem campo, sem
coluna e sem espelho. É o oposto do tema (ADR 0016), que vive no servidor e por isso **precisou** de uma
cópia em `localStorage` para sobreviver à primeira pintura, de uma excepção estreitada no
`eslint.config.js` e de três parágrafos de CSP. Aqui o `<html lang>` escreve-se no módulo de entrada ao
lado do `aplicarTemaDoEspelho()`, sem pedido novo e sem uma linha de CSP, porque o sinal já está na
máquina antes do primeiro pixel. **E a ausência de selector é o que mantém `t` uma função e não um
hook:** com o idioma fixo por documento, o catálogo resolve-se **ao nível do módulo** — é o que permite
que os `z.string().min(1, "Escreva o email…")` dos `schemas.ts` e os `Intl.*Format` do `lib/format.ts`
continuem constantes de módulo. Com selector, cada string passava a reactiva e cada constante a função.

**Divergem, e em quatro casos — os quatro nomeados, três com mecanismo.** (1) **Não há pedido nenhum**:
Celery, outbox, emails do `notifications`, comandos `manage.py`. Não há `Accept-Language` e não há
língua; é o buraco estrutural e está no "fica por decidir". (2) **A precedência do `LocaleMiddleware`**:
ele olha primeiro para o prefixo de URL e para o cookie `django_language`, e só depois para o
`Accept-Language`. Um cookie velho ganhava ao browser do lado da API sem ganhar do lado do React —
logo `django.conf.urls.i18n` **não é encaminhado** (o `set_language` é um POST anónimo que escreve um
cookie, exactamente a família que o `SECURITY.md` §5 obriga a proteger) e nada nosso chama
`translation.activate`. (3) **Cache sem `Vary`**: uma resposta com texto traduzido guardada sem
`Vary: Accept-Language` sai na língua errada. O `LocaleMiddleware` acrescenta o header a todas as
respostas que passam por ele, e é isso que o põe no `MIDDLEWARE` em vez de um `activate` numa view.
(4) **Mudar a língua do browser com a app aberta**: o documento montado continua com o
`navigator.language` antigo e os pedidos novos já vão com o header novo. Dura até ao recarregamento,
não tem mecanismo e não vale um: é um gesto raro com um remédio óbvio.

**Decisão 3 — No frontend, catálogo escrito à mão, e o contrato é um `typeof`.** Nenhuma biblioteca. O
mecanismo é um objecto por língua, com o português como fonte, e o inglês anotado com o tipo do
português:

```ts
// features/inventory/textos.pt.ts   (sem `as const`: os valores querem-se `string`, não literais)
export const PT = { titulo: "Stock", artigos: (n: number) => (n === 1 ? "1 artigo" : `${n} artigos`) };
// features/inventory/textos.en.ts
export const EN: typeof PT = { … };     // falta uma chave → TS2741; uma a mais → TS2353
// lib/i18n.ts escolhe uma vez; quem lê faz `textos.titulo`, não `t("titulo")`
```

Isto é mais forte do que a forma que o pedido propõe (uma união declarada mais dois
`Record<Chave, string>`) por duas razões: a união declarada é uma **terceira** lista escrita à mão, ao
contrário do `Record<RotaId, …>` e do `Record<Tema, …>`, onde a união é **gerada** pelo backend; e um
`Record<Chave, string>` não consegue guardar uma função, logo não tipa a **interpolação**. Com `typeof`,
uma chave com dados é uma função cujos parâmetros fazem parte do contrato: mudar `(n: number)` para
`(n: number, loja: string)` numa língua e não na outra não compila. Acesso por propriedade em vez de
`t(chave)` elimina também a união de chaves, o `detect-object-injection` e o ramo de fallback.
**Pluralização não paga biblioteca nestas duas línguas:** pt e en têm as mesmas duas categorias CLDR e
o plural é `n === 1`. O gatilho para reabrir está escrito: a primeira língua com mais de duas categorias
(polaco, russo, árabe) troca isto por `Intl.PluralRules` ou por uma biblioteca, e aí a conta muda.
**Onde vivem:** `textos.pt.ts`/`textos.en.ts` **por feature e no shell**, ao lado do `vocabulario.ts`
que já é onde a copy vive (ADR 0013, decisão 5), e não num ficheiro central de 800 linhas que todos os
agentes tocam. O mecanismo (resolver a língua, `<html lang>`, a lista de línguas disponíveis) é um
ficheiro em `lib/`, que é o `apps/shared` do frontend e se importa de cima para baixo.

**O `lib/format.ts` passa a ter dois locales, e a divisão é "forma de dado" contra "palavra".** Os 14
formatadores de hoje têm `const LOCALE = "pt-PT"`. A **forma** do número e da data fica em pt-PT
sempre — vírgula decimal, euro em sufixo, dia primeiro — porque é a forma dos dados do negócio
(a factura que a pessoa tem na mão), porque as larguras de coluna do `DESIGN.md` §3 foram medidas nela,
e porque o `<input>` do Contar tem **um** parser: duas formas de escrever `12,5` são duas leituras de
uma quantidade de stock. As **palavras** que o `Intl` produz seguem a língua, e são três
(`mesEAno`, `diaEMesCurto`, `relativo`): um ecrã inglês com "setembro de 2026" e "ontem" está meio
traduzido no sítio mais visível. **Consultar `domain-expert`** — ver as consequências.

**Decisão 4 — No backend, `LocaleMiddleware` com um catálogo de projecto que ganha ao do DRF.** Entra o
`LocaleMiddleware` logo depois do `SessionMiddleware` e sempre **acima** do `TenantMiddleware` (a língua
tem de estar activa quando um service levanta uma recusa), mais `LANGUAGES`, `LOCALE_PATHS` e
`gettext_lazy`/`ngettext_lazy` nas ~15 strings nossas que chegam ao olho (o `detalhe` das
`RecusaDeSessao`/`RecusaDeConvite` e as mensagens escritas à mão nos serializers). **Os msgid ficam em
inglês**, contra o hábito do repositório, e por duas razões mecânicas: é a língua dos catálogos com que
o nosso se funde (Django e DRF), logo o `makemessages` produz um ficheiro coerente e o inglês sai de
graça sem catálogo nenhum; e uma tradução pt-PT em falta mede-se comparando conjuntos de msgid, ao
contrário do caminho inverso, onde a falta cai no msgid português e **mostra português a um leitor
inglês sem erro nenhum** — a forma de falha que este pedido existe para evitar.

**"pt é pt de Portugal" torna-se verdade porque as traduções do projecto ganham às das apps.** O
`LOCALE_PATHS` é fundido **depois** dos catálogos das apps instaladas, e a fusão sobrepõe, logo um
`locale/pt_PT/LC_MESSAGES/django.po` nosso ganha ao `pt_PT` do DRF — que, medido pelo dono do
repositório, é quase uma cópia do `pt_BR` ("Use um dos formatos a seguir"). Mudar o código de língua
não é a correcção: `pt` e `pt-pt` dão a mesma frase. **E torna-se medível porque a lista de strings a
sobrepor é derivada de uma medição e não adivinhada**, que é o método do gate de cor ("calcula a pior
superfície em vez de a nomear"): o teste itera os msgid do catálogo `pt_PT` do DRF, traduz cada um sob
`activate("pt-pt")` e falha se o resultado contiver um de uma lista **fechada** de marcadores pt-BR
(`você`, `arquivo`, `registro`, `deletar`, `a seguir`, `planilha`). O que ele apanha são marcadores e
não prosa, e isso diz-se: prova que estas seis formas não chegam ao utilizador, não que a frase é de
Portugal. O que a medição já aponta, e é o âmbito do `.po`: os `default_error_messages` dos campos que
esta API usa (`required`, `blank`, `max_length`, `invalid` de `EmailField`/`UUIDField`/`TimeField`/
`DateTimeField`/`IntegerField`, `invalid_choice`, `not_a_list`) e as `APIException` que ela emite
(`NotAuthenticated`, `PermissionDenied`, `NotFound`, `MethodNotAllowed`, `Throttled` — esta com plural,
logo `ngettext`, `ParseError`, `UnsupportedMediaType`). ~30 msgid, não o catálogo inteiro.
**Os `.po` são commitados e os `.mo` não**: `compilemessages` corre no stage `builder` do
`backend.Dockerfile` (que ganha o `gettext`) e no CI antes do `pytest`, e quem apanha um compile
esquecido é o teste que afirma a tradução — um msgid que se traduz para si mesmo é vermelho, não é uma
UI inglesa em silêncio. Um `.mo` commitado era um artefacto binário cujo diff ninguém lê.

**Decisão 5 — Nenhum rótulo nosso viaja no arame, e o menu é o único sítio onde isso não era verdade.**
A regra que o pedido pede para fixar é a certa: **o default é nosso e traduz-se; o que o tenant escreveu
é texto dele e nunca se traduz.** O que o pedido assume e é falso é que o default venha do servidor.
Medido no contrato: o `ItemDeMenuOut.rotulo` é `null` quando o tenant não sobrepôs nada, e quem resolve
é o cliente contra o seu próprio registo (`entrada.rotulo ?? registo.rotulo`). Logo **o rótulo do menu
não precisa de i18n no backend** — é copy do frontend e traduz-se no catálogo. O `rotulo_default` do
`GET /menu/rotas` é consumido por um sítio só (a secção que mostra "o default é este") e é uma **segunda
fonte** para a mesma palavra: **sai do contrato e sai do `RotaDoRegisto`**, e a secção usa o registo do
cliente. O `grupo` é o inverso e é o achado: ele viaja **resolvido** e obrigatório, logo o cabeçalho de
grupo da sidebar vem do servidor — e pior, o `PUT /menu` é uma substituição total, logo **a primeira
gravação congela "Inventário" e "Equipa" na linha do tenant** e nenhuma tradução os volta a alcançar.
Não é uma falha do i18n: é o `grupo` do lado errado da regra desde a ADR 0009, que o torna texto livre.
A correcção é a assimetria que o `rotulo` já tem — `""` na coluna quer dizer "usa o default", `null` no
contrato, e o cliente resolve contra o registo. Com isto, **o `grupo_default` também sai do contrato** e
a ADR 0013 decisão 5 ("nenhum rótulo viaja no arame") passa a ser verdadeira de toda a API: o que
atravessa é um id de união fechada ou texto que o tenant escreveu — mais a prosa de uma recusa, que é
uma frase sobre um pedido concreto e é traduzida no servidor. A fronteira entre as duas coisas lê-se no
`schema.yml`, e **não tem mecanismo automático**: é regra de revisão e fica escrita como tal.

**Decisão 6 — Um ecrã, quatro secções, e a objecção da ADR 0017 resolve-se com o search param e não com
403.** Isto **supersede a decisão 1 da ADR 0017** (dois ecrãs) e a rejeição que ela escreveu de "um ecrã
com abas e um 403 por aba". **O que sobrevive intacto:** a decisão 2 (nenhum agregado — as secções
compõem os mesmos seis endpoints, logo a proibição da ADR 0011 não é tocada e continua a não haver
`GET /configuracao`), a decisão 3 (403 e não 200 parcial; `owner` em leitura e escrita; a escrita
pessoal é sempre sobre o `request.user`), a decisão 4 (o que não entra no v1 — e **o idioma continua
fora**, porque não passa a ser campo de nada: a 0017 recusou-o por ser "um campo sem leitor" e esta ADR
satisfaz a recusa por outro caminho), e a parte da decisão 1 que mantém o ecrã **fora** do
`REGISTO_DE_ROTAS`, agora pelas duas razões juntas: uma rota pessoal dentro de uma projecção por tenant
deixava uma empresa esconder um ecrã pessoal, e a entrada é o pé da sidebar.

A objecção da 0017 não desaparece por o dono mudar de ideias — um ecrã cujo **conteúdo** depende do
papel —, e a resposta tem três peças. **Primeira: a secção é um search param com queda para o
default**, validado em Zod como o `?aba=` do painel (ADR 0008, decisão 1: "um URL malformado degrada
para o default em vez de explodir dentro de um ecrã"). Um papel que não pode ver uma secção é, para
este efeito, o mesmo que um URL malformado: o `validateSearch` valida a **forma** e o ecrã resolve
`secção ∈ visíveis ? secção : primeira(visíveis)`. Não há 403 por secção porque não há pedido: o papel
vem na sessão antes de o ecrã montar, as secções da empresa não são renderizadas e o pedido não é
disparado. O 403 do servidor fica onde a própria 0017 o punha — a rede do deep link e da pertença
revogada a meio da sessão (ADR 0007, verificação por pedido) —, e nesse caso é alcançável e o ecrã
mostra a recusa. **Segunda: o buraco que a hipótese do pedido tem, e é real.** O papel é **por tenant**,
e o seletor de tenant vive no mesmo pé da sidebar: quem é `owner` de A e `staff` de B, parado em
`/definicoes?aba=estabelecimento`, troca de estabelecimento e fica com uma secção que o papel novo não
tem — sem o URL mudar, logo um `beforeLoad` ou uma verificação no `validateSearch` não a apanham. A
queda tem de viver no **render**, derivada da sessão viva, e não à entrada da rota. É a única peça desta
decisão que não é cópia de um padrão existente. **Terceira: a fronteira entre as duas famílias tem de
continuar legível, e a 0017 punha-a no menu** — resposta que morre aqui. Substitui-se por duas coisas
que não são um ícone a explicar uma regra: a régua de secções tem a pessoal primeiro e **uma separação
visível** antes das da empresa (a mesma régua de 1px e o mesmo trilho de 4px do selector de paleta,
`DESIGN.md` §4), e cada secção da empresa nomeia o **estabelecimento** no seu `<h2>` — que é também a
resposta a "qual destas casas é que eu estou a configurar?" para quem tem duas.

**As quatro secções, e os nomes.** `aparencia` — **Aparência** (a paleta, ADR 0016; a única que os três
papéis vêem); `estabelecimento` — **Estabelecimento** (nome, regime de IVA, hora a que o dia de negócio
começa); `navegacao` — **Navegação** (a projecção do menu; **e não "Menu"**, que numa app de restauração
se lê como a ementa); `equipa` — **Equipa** (os convites de hoje, os membros quando existirem). Em
inglês: Appearance · Establishment · Navigation · Team. As três últimas são `{owner}`, como já eram.
**Com uma secção só não há régua de secções**: um `staff` vê o ecrã "Definições" com a paleta e mais
nada, porque uma régua de um segmento é um controlo que não escolhe. A forma copia-se do painel ponta a
ponta — `z.enum` das secções com os rótulos e a ordem num sítio só, uma `<nav>` de `<Link>`s com
`aria-current`, sem primitivo novo do shadcn (o painel não usa `role="tablist"`).

**Decisão 7 — O `configuracao` sai do enum, e o `convites` com ele; e não há migração de dados.**
Manter o id no enum e tirá-lo só do registo **não é viável**, e quem o decide é o mecanismo: o
`RotaIdEnum` do `types.ts` vem do `RotaDeMenu` (quatro `ChoiceField` o emitem), e o
`Record<RotaId, EntradaDoRegisto>` do shell exige uma entrada para cada valor — com um `caminho` que
tem de existir na árvore de rotas, porque o tipo vem dela. Um id sem rota no `REGISTO_DE_ROTAS` não
compila de nenhum dos dois lados. Logo os dois lados saem no mesmo commit, verificado pelo compilador
nos dois sentidos, simétrico à entrada que a ADR 0017 fez ontem. **E o `convites` sai pela mesma regra,
que é a correcção que faço à leitura do pedido:** o dono apontou "as definições da equipa [que estão] na
side bar", e o que está na sidebar no grupo "Equipa" é Convites e Configuração. O invariante que isto
fixa, e que evita litigar item a item no futuro: **uma rota do registo responde a uma pergunta de
operação** — o campo `pergunta` do registo existe para isso (`DESIGN.md` §1) — **e definições não
respondem a nenhuma**. "Quem tem acesso?" e "como é que esta casa está configurada?" são as únicas duas
entradas de hoje cuja `pergunta` não é uma pergunta da manhã. Fica também o grupo "Equipa" sem um
cabeçalho sobre um item só, e a projecção por tenant passa a querer dizer uma coisa limpa: uma empresa
configura **que ecrãs de operação as suas pessoas vêem**, nunca se alguém alcança as suas definições.

**Nenhuma migração de dados, e por três razões que se somam.** A migração é um `AlterField` de
`choices`, que é validação em Python: no-op na base de dados, como a 0005 e a 0007, a confirmar com
`sqlmigrate` **antes** de ser escrita. Uma linha órfã com `route_id="configuracao"` já é tratada por
desenho — o `rota_do_registo` devolve `None` e a projecção ignora a linha, que é o caminho do rolling
deploy —, e cura-se sozinha no `PUT` seguinte, que é uma substituição total construída a partir de um
`GET /menu/rotas` que já não lista o id. E **uma migração de dados sobre esta tabela não funcionaria sem
trabalho a mais**: o `accounts_tenantmenuitem` tem `FORCE ROW LEVEL SECURITY`, que sujeita o
`stockflow_owner` (`SECURITY.md` §3), logo um `delete()` numa migração, sem `app.tenant_id`, apaga
**zero linhas em silêncio**. Fica escrito aqui para ninguém a escrever a achar que apagou.

**Decisão 8 — O que os gates passam a medir, e onde.** **Uma tradução em falta falha no
`pnpm typecheck`**, por catálogo, pelo `typeof` da decisão 3 — é compilação e não arranque. **Uma string
nova fora do catálogo falha no `pnpm lint`**, num `scripts/check-textos.mjs` ao lado dos outros três, em
duas metades que falham nos dois sentidos: (a) um literal com letra acentuada num nó de texto de JSX ou
num `title`/`aria-label`/`placeholder` fora dos `textos.*.ts` é erro — apanha prosa acentuada e **não**
apanha "Save" nem "Total", e isso diz-se em vez de se prometer; (b) um ficheiro de `screens/` ou de
`shell/` que não importe o seu módulo de textos é erro, salvo lista fechada — que é o grão certo, porque
um ecrã está traduzido ou não está, e é a lista que a decisão 9 usa. Uma chave de catálogo que nenhum
ficheiro usa também é erro, que é a direcção que o compilador não cobre. No backend,
`tests/test_i18n.py`: cada msgid do nosso `.po` resolve para o seu msgstr sob `activate("pt-pt")` (o
gate do `.mo`); zero entradas por traduzir ou `fuzzy`; a varredura de marcadores pt-BR da decisão 4; o
mesmo corpo inválido com `Accept-Language: pt-PT` e com `en` a dar duas respostas **afirmadas** (é a
única prova de que o middleware, o catálogo e a ordem estão os três ligados); e `Vary: Accept-Language`
presente. **O `DESIGN.md` não ganha um gate, ganha uma obrigação de instrumento, e isso diz-se por
inteiro:** as larguras de coluna "medem-se, não se somam" (§4) e a mais apertada foi medida em pt-PT —
mas o cabeçalho em caixa alta com `tracking` de 0.08em não é mais curto em inglês de forma fiável
("Onde"→"Where", "Validade"→"Best before"). Logo as constantes de largura passam a ser o **máximo das
duas línguas**, com a medição de cada uma no comentário, e o `scripts/ver-ecra.py` ganha um argumento de
língua — que tem de mover os **dois** sinais (`Emulation.setLocaleOverride` para o `navigator.language`
e o `Intl`, mais o `Accept-Language` nos headers), senão mede uma divergência que nenhum utilizador
tem. Mede-se a 1280 e a 360 nas duas línguas. **O repositório não tem gate de layout e esta ADR não
inventa um**: é um procedimento com um instrumento, e fica nomeado como tal.

**Decisão 9 — Fases: a primeira é uma correcção de pt-PT, não uma língua nova.** "Um modo a meio é pior
do que não ter modo" aplica-se com força: uma app meio traduzida dá ao leitor inglês uma parede de
português exactamente onde a tarefa fica difícil — uma recusa, uma confirmação. E com o idioma a vir do
browser **não se pode "não enviar" inglês**: um browser inglês recebe o que houver. Logo a língua
disponível é uma **lista fechada de um elemento**, dos dois lados — `LANGUAGES` com `pt-pt` só, e a
mesma lista no `lib/i18n.ts` —, e enquanto for de um, `Accept-Language: en` cai no default e a app é
inteiramente portuguesa, como hoje. **Primeira alteração (coerente por construção):** o mecanismo
inteiro (decisões 3 e 4), o ecrã novo e a saída dos dois ids (decisões 6 e 7), a limpeza dos rótulos do
arame (decisão 5), os gates (decisão 8), e os catálogos do **shell**, dos **estados genéricos**
(vazio/erro/indicador/esqueleto), do `/entrar` e do `/ativar` e do `/definicoes` — o shell porque
emoldura todos os ecrãs, os estados porque aparecem em todos, e os dois primeiros porque quem não os
entende não chega a lado nenhum. Nada disto é visível a um leitor inglês, e **é visível a um
português**: deixa de ler "Use um dos formatos a seguir". **Depois, um ecrã por commit**, pela ordem de
uso (Stock, Alertas, Receber e a recepção, Contar e o fecho, Artigo, Painel), cada um a remover a sua
linha da lista fechada do gate — o mesmo gesto do `DECLARADAS` do `security_check.sh`, onde o meio
caminho é declarado e encurta num diff em vez de viver escondido. **O inglês liga-se numa entrada em
cada uma das duas listas**, no commit em que a última linha do gate sai, e nunca antes: é a única
alteração em que a app muda de estado, e é de duas linhas.

**Alternativas.** *react-i18next* — a opção óbvia; rejeitada porque a sua garantia de chaves é
tipagem **opt-in** por augmentação de módulo e a falta de uma tradução é um fallback em runtime com um
aviso na consola, não um erro de compilação: para ter o que a decisão 3 tem escrevia-se a mesma
restrição à mão **mais** a dependência, o provider e o hook que o "sem selector" torna desnecessários.
*lingui* — macro, `extract`/`compile` e `.po` no frontend: um passo de build e uma família de
artefactos para duas línguas cujo plural é `n === 1`, e os `.po` justificam-se por tradutores humanos,
que não existem. *FormatJS/react-intl* — ICU e extracção; compra categorias de plural que estas línguas
não têm e formatação de números que o `lib/format.ts` já faz com `Intl`. *Rótulos traduzidos no
servidor* — a ADR 0013 já o rejeitou ("nenhum rótulo viaja no arame") e punha cada ecrã à espera de um
pedido para saber como se chama. *Uma coluna `idioma` no `accounts_user`, ao lado do `tema`* — é a opção
que o dono excluiu, e tem o custo medido da ADR 0016 de volta (espelho local, relâmpago, uma excepção no
`eslint.config.js`) mais um: faz de cada string um valor reactivo. *Um `?lang=` ou um header nosso* —
um segundo sinal que pode discordar do browser, que é exactamente a propriedade que a decisão 2 compra.
*`i18n_patterns` com prefixo de língua* — duplica todos os caminhos e parte o tipo `CaminhoDeRota`, que
vem da árvore real. *Mudar `LANGUAGE_CODE` para `pt`* — medido: dá a mesma frase pt-BR. *Traduzir o
catálogo `pt_PT` do DRF por inteiro, ou forká-lo* — centenas de msgid para os ~30 que esta API serve, e
um fork que deriva a cada actualização do DRF sem nada que o diga; a sobreposição de uma lista fechada
**derivada de uma medição** tem gate. *`django-modeltranslation` ou colunas traduzidas* — nada no
domínio é multilingue: o texto do tenant está na língua do tenant. *Manter dois ecrãs e só renomear* —
é o que o dono recusou, e a 0017 fica superada na decisão 1 e não na 2 nem na 3.

**Consequências.** **Zero tabelas novas, zero colunas, zero RLS**: as duas listas fechadas do
`tests/test_db_roles.py` não mexem e o `APPEND_ONLY` continua vazio — é o sinal de que esta ADR não abre
excepção. **Nenhum evento, nenhuma tarefa Celery, nenhuma chave de Redis**: não há sinal nenhum da
secção 7 do `ARCHITECTURE.md`. Duas migrações, as duas no-op na base de dados e as duas a confirmar com
`sqlmigrate` antes de serem escritas: o `choices` do `route_id` sem os dois ids, e o `grupo` a aceitar
vazio. **No contrato:** `ItemDeMenuOut.grupo` passa a anulável, o `grupo` do corpo do `PUT /menu` passa
a opcional, o `RotaDeMenuOut` perde `rotulo_default` e `grupo_default`, o `RotaIdEnum` perde dois
valores — `pnpm gen:api` e o gate de diff do `types.ts` (`ARCHITECTURE.md` §5), com os dois lados no
mesmo commit porque de outra forma não compila. **No frontend:** `lib/i18n.ts`, um par de `textos.*.ts`
por feature e no shell, o `lib/format.ts` com dois locales, o `lang` do `<html>` escrito no módulo de
entrada, a rota `/definicoes` e o apagamento de `/preferencias` e `/configuracao` — **sem redirects**,
porque a app é pré-lançamento e ninguém tem marcadores, e porque um `<Link>` esquecido para uma rota que
não existe **não compila** (o `to` é tipado pela árvore, o que torna a remoção verificada em vez de
procurada). Mais o `check-textos.mjs` no `pnpm lint` e o argumento de língua no `ver-ecra.py`.
**No backend:** o `LocaleMiddleware`, `LANGUAGES`, `LOCALE_PATHS`, o `.po` de projecto, o `gettext` no
stage `builder` do `backend.Dockerfile` e no CI, e o `tests/test_i18n.py`. **Ficam devidos e não editados
aqui** (não são os meus ficheiros, como a ADR 0009 fez): o `DESIGN.md` §4 perde a linha "são dois ecrãs e
não dois separadores do mesmo (ADR 0017)" e ganha a entrada única no pé da sidebar, o §3 ganha "medido
nas duas línguas" na linha das larguras de coluna, e a checklist do §6 ganha a linha das duas línguas a
1280 e a 360; o `SECURITY.md` §5 ganha uma linha a dizer que `django.conf.urls.i18n` não é encaminhado,
com a razão. **Consultar `domain-expert`, e não é formalidade**: o vocabulário inglês deste domínio tem
pelo menos uma tradução que é uma afirmação de segurança alimentar e não uma escolha de palavra —
"consumir até" e "melhor antes de" são *use by* e *best before*, são coisas legalmente diferentes nas
duas línguas e trocá-las é um bug de validade; mais a separação `waste`/`shrinkage`/`consumption` do
painel (ADR 0013, decisões 4 e 7), o rótulo inglês de `isento_art_53` (um regime fiscal português não
tem nome inglês oficial), e a decisão de manter a vírgula decimal e o euro em sufixo nas duas línguas,
que toca em quantidades de stock e no `<input>` do Contar.

**O que fica por decidir.** **A língua de tudo o que não tem pedido**: o digest diário do
`notifications`, o email de convite e qualquer tarefa Celery não têm `Accept-Language` nenhum, e a
resposta honesta hoje é "português". No dia em que o primeiro email sair, a decisão reabre com três
saídas — uma coluna por pessoa (que contraria a restrição do dono), a língua do estabelecimento, ou
português sempre — e é melhor decidi-la com o email à frente do que inventar agora um campo sem leitor
(ADR 0016 recusou um valor de enum "que nada produz"). **Se o inglês é `en` ou `en-GB`**: as três
palavras que o `Intl` produz são iguais nos dois, e a forma das datas ficou em pt-PT, logo `en` basta;
reabre com o primeiro leitor americano a ler 09/10 como 9 de outubro. **Um terceiro idioma**: o
mecanismo escala (um ficheiro por língua), e a conta muda se a língua tiver mais de duas categorias de
plural. **Um `manager` a configurar o estabelecimento** continua a ser a Q7, como a 0017 a deixou.
**Um menu bilingue** não existe: um grupo renomeado pelo tenant é texto dele, numa língua só, e é custo
aceite. E **o cabeçalho de tabela `sticky`** continua por decidir, como o `DESIGN.md` §3 o deixou.

---

**Nota ao dono do produto — o que vale contestar antes de implementar.**

1. **"Inglês" responde a quem?** Se o leitor é o próprio dono, um investidor ou um encarregado que
   prefere inglês, está certo. Se o leitor real é **pessoal de cozinha que não fala português** — o caso
   comum numa pastelaria em Portugal —, então o inglês pode ser a segunda língua errada, e as duas rotas
   onde a barreira custa dinheiro (Contar e Receber: uma quantidade mal contada, uma recepção mal
   confirmada) são **duas**, não doze. Traduzir dois ecrãs na língua que essas pessoas lêem vale mais do
   que traduzir doze em inglês. A escolha do mecanismo não bloqueia nenhuma das duas respostas — um
   ficheiro por língua —, mas a **ordem do trabalho** muda por inteiro. É a pergunta a fazer primeiro.
2. **Sem selector, uma máquina partilhada tem uma língua.** O tablet da copa é um browser para várias
   pessoas, e o tema é da pessoa (ADR 0016) enquanto a língua passa a ser da máquina. É uma
   inconsistência que vai ser notada exactamente no aparelho onde importa. Recomendo manter a decisão —
   o custo do selector está escrito na decisão 2 e é alto —, mas sabendo que **reverter não é grátis**:
   com selector, `t` deixa de ser uma função de módulo e passa a hook, e as constantes de módulo
   (schemas Zod, formatadores) passam a funções. Não deixei nenhuma hipoteca preparada para isso, de
   propósito.
3. **O `convites` a sair do menu é minha leitura das tuas palavras**, não uma coisa que pediste em
   separado. Se o que querias mover era só a "Configuração", o grupo "Equipa" sobrevive com um item só e
   a alteração é menor: o `convites` fica no enum e nos dois registos, e a secção "Equipa" do ecrã novo
   não existe. Diz qual das duas.
4. **"pt de Portugal" e "não pt-BR" não são a mesma afirmação.** Esta ADR faz a primeira (medida, com
   gate). A segunda — excluir o pt-BR como língua — não está decidida, e um cozinheiro brasileiro é
   servido aqui por pt-PT. Se um dia quiseres pt-BR a sério, é uma terceira língua e não um ajuste.

---

## Adenda — 2026-10-07: o gate media menos do que prometia, e a lista era metade

Esta ADR fez a lista fechada do `check-textos.mjs` o **gate** de quando o inglês liga: "no commit em
que a última linha sair". Ao traduzir as Definições descobriu-se que a lista não media o que prometia.

**A medição.** Com a regra 1 a olhar só para nós de texto de JSX e três atributos, a lista dizia **32
ficheiros por traduzir**. Uma varredura por strings acentuadas em todo o `src/` deu **60**. Os 28 que
faltavam não eram ecrãs esquecidos: eram ficheiros onde a copy **nunca passa por JSX** — um
`vocabulario.ts` inteiro, os rótulos e as perguntas do `secoes.ts`, as mensagens de Zod dos
`schemas.ts`, os nomes das paletas no `lib/tema.ts`, as frases de erro da camada de rede. Esvaziar a
lista de 32 não teria ligado o inglês: teria ligado **metade** dele, que é precisamente o estado que a
decisão 9 existe para proibir.

**O que mudou no gate** (três alterações, cada uma medida antes de ser adoptada):

1. **a regra 1 passou a ver strings de código**, e não só JSX. O varredor consome cada literal até ao
   seu próprio delimitador — um `matchAll` de templates emparelhava o fecho de um com a abertura do
   seguinte e acusava quatro strings que não existiam;
2. **o critério do nó de JSX passou de "tem acento" a "tem uma palavra"**. Num ficheiro já traduzido um
   nó de texto não tem palavra nenhuma: o que lá está é `{textos.x}`, um `·` ou um número. Apanhou seis
   strings reais que o acento não via, entre elas um "Tentar outra vez" em dois ecrãs de erro;
3. **numa string de código, o acento ganhou um segundo sinal** — começar por maiúscula e ter uma
   segunda palavra. Apanhou mais três, entre elas o `Estabelecimento: ${nome}` do pé da sidebar.

Fica **declarado** o que continua a escapar: uma palavra só sem acento num atributo (um
`rotulo="Email"`). Distinguir "Email" de "icon-sm" sem um dicionário era um gate em que ninguém
confia, e os dois rótulos que existem foram traduzidos porque alguém os leu — está dito no catálogo, ao
lado deles.

**O que não é copy passou a ser uma lista fechada por string** (`NAO_E_COPY`), e não uma excepção por
ficheiro: um `schemas.ts` tem as duas coisas lado a lado — a mensagem do formulário, que se lê, e a da
resposta do servidor, que vive no `cause` de um `ErroDeContrato` e ninguém lê. Uma excepção por
ficheiro deixava passar a primeira. A primeira versão da lista tinha um erro que a revisão apanhou: a
frase do `ResponseShapeError` estava lá como diagnóstico, e é falso — o `mensagemDeErro` cai para o
`message` de qualquer `Error`, logo ela aparece debaixo de um `<Alert>` como qualquer outra.

**Quatro catálogos novos**, pela mesma regra da decisão 3 (a copy vive ao lado de quem a usa):
`src/components/` para o que aparece em todos os ecrãs, `src/lib/` para as frases da camada de rede e
as paletas, e um por feature de domínio.

**A forma do catálogo cresceu em três sentidos**, e os três estão no `accounts` para quem copiar:

- **função** quando a frase interpola um valor (`diaDeNegocioExplicacao(hora)`). A assinatura faz parte
  do `typeof PT`, logo mudá-la numa língua e não na outra não compila;
- **partes nomeadas** quando a frase tem ênfase no meio (`<strong>As validades não mudam…</strong>`).
  Juntá-las perdia o negrito que o DESIGN.md §2 escolheu; pô-las numa string com HTML pedia um
  `dangerouslySetInnerHTML` que o `eslint.config.js` proíbe;
- **`accoes`**, uma secção com os verbos que aparecem em mais do que um sítio (Guardar · A guardar… ·
  Desfazer · A sair…). É a regra de escrita do DESIGN.md — uma acção mantém o mesmo nome em todo o
  produto — e três secções com três chaves `guardar` eram três sítios onde ela se podia perder.

**E o `Record` fica no código, não no catálogo.** Onde a copy é indexada por uma união do contrato (os
papéis, os estados de um convite, os regimes de IVA, os motivos de desperdício), o
`Record<Uniao, string>` continua no `schemas.ts`/`vocabulario.ts` e só as palavras vêm do catálogo,
**nomeadas uma a uma**. São duas garantias diferentes e as duas fazem falta: o `Record` é o que deixa
de compilar quando o contrato ganha um valor; o catálogo é o que exige a entrada inglesa.

### O inglês ligou no mesmo dia, e o que a segunda língua mostrou

A lista esvaziou e as duas linhas entraram. Três coisas que só se viram com o
inglês a correr:

**1. O gate das duas pontas passou a existir.** A decisão 9 era uma frase numa
ADR, e as duas metades vivem em repositórios de linguagens diferentes — a forma
de divergência que ninguém vê. O `test_o_ingles_so_liga_com_a_lista_vazia` lê o
`SEM_CATALOGO` do frontend e afirma `("en" in LANGUAGES) == (lista vazia)`,
falhando nos dois sentidos. O segundo sentido é o que valia escrever: *lista
vazia sem inglês servido* é trabalho feito que ninguém recebe, e não tem sintoma.

**2. Um grupo de menu renomeado pelo tenant parte-se em duas línguas**, e é mais
do que "fica numa língua só" (que é o que esta ADR tinha aceitado). O grupo é
texto livre e a pertença a um grupo é **igualdade de texto**: um tenant com
`grupo='Painel'` gravado numa rota e as irmãs a cair no default vê, em inglês,
"PAINEL" com um item e "OVERVIEW" com os outros dois — uma sidebar com cinco
cabeçalhos onde havia três, metade em cada língua. Em português é invisível,
porque o texto gravado é igual ao default.

Foi visto no estabelecimento de demonstração, e a causa ali é **resíduo
pré-0010**: um `PUT /menu` feito quando o `grupo` ainda viajava resolvido
congelou `"Painel"` e `"Inventário"` na linha do tenant, que é exactamente o que
a migração 0010 descreve e deliberadamente não migrou. Cura-se gravando as
Definições → Navegação com os campos de grupo vazios. Não se mudou código por
isto: o contrato já diz que em branco significa "usa o default", e o resíduo é de
desenvolvimento. **Mas a consequência estrutural fica escrita**: enquanto o grupo
for texto livre, uma empresa que renomeie *alguns* grupos tem a sidebar partida
na segunda língua. Se isso passar a importar, o caminho é o grupo deixar de ser
texto e passar a ser um id com nome por língua — o que é a ADR 0011 a mudar de
forma, não um ajuste.

**3. A forma dos números ficou em pt-PT e lê-se estranho ao lado de palavras
inglesas** ("5919,94 €" debaixo de "Sales, excluding VAT"). É a decisão que já
estava tomada — o negócio é português, a vírgula decimal e o símbolo depois do
número são o que um dono reconhece — e continua a ser a certa por uma razão a
mais: o painel compara-se com faturas e com o extracto do TPA, que estão em
pt-PT. Reabre no dia em que o leitor inglês for quem **introduz** números.
