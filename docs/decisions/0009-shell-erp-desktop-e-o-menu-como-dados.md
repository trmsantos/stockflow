# ADR 0009 — O shell de um ERP desktop-primeiro: a árvore de rotas é código, o menu é dados

**Contexto.** Direcção nova do dono do produto (2026-10-01): ERP desktop — menu lateral que cresce,
tabelas densas com muitas colunas, configuração por empresa — e o telemóvel a servir **só** os fluxos
de campo (contar, receber), com a tab bar de quatro itens a desaparecer. Isto contraria três coisas
escritas, e as três têm de ser reconciliadas e não contornadas. O `DESIGN.md` §4 fixa "tab bar
inferior (4 itens)" e mobile-first. O §1 do mesmo ficheiro diz que o público "usa em telemóvel, em pé,
com pressa", e é dessa frase que derivam os tokens **e** a estrutura dos ecrãs: o banner do ficheiro já
devia uma reescrita do §1 por o Linear ser a referência errada, e agora deve-a por uma **segunda razão
independente** — a afirmação de público deixou de ser verdadeira. A ADR 0008, decisão 2, pôs a
navegação num array único cujos itens de mobile são uma tupla de quatro **verificada pelo `pnpm
typecheck`**; com o menu por empresa, o número de itens chega por HTTP e nenhum compilador o conta. E o
§0 do `docs/sessao-0-guiao.md` fixa um orçamento de 3 números + 7 linhas a 360px, desenhado para quem
está de pé — bom trabalho de domínio, mas derivado de um público que mudou.

**Decisão.** **A árvore de rotas continua a ser código; o menu passa a ser dados, e é uma projecção por
tenant sobre o superconjunto de rotas que existem.** Três razões, e nenhuma é estética: um deep link
tem de funcionar para uma rota que o menu da empresa esconde, porque esconder é apresentação e não
autorização — quem autoriza é o `Membership` e as classes de permissão (ADR 0007), e um menu como fonte
de verdade transformaria "esconder" num controlo de acesso falso e um marcador guardado num 404; o
`validateSearch`, os params tipados e o `lazyRouteComponent` exigem a árvore em build time (ADR 0008,
decisão 1); e a lista fechada de rotas é **do backend**, porque é ele que valida o `route_id` que a
projecção guarda (ADR 0011).

**O que substitui a garantia dos "4 itens": a integridade referencial do menu contra as rotas, e não a
cardinalidade.** A lista fechada de ids viaja no enum do OpenAPI, logo o `types.ts` commitado carrega a
união e o registo do frontend é um `Record<RotaId, EntradaDoRegisto>` — um `Record` sobre uma união
gerada é exaustivo **nos dois sentidos** sob `pnpm typecheck`: uma rota no registo que o backend não
conhece não compila, e uma que o backend conhece e o registo não tem também não. Sobrevive também o
**predicado** do telemóvel: o registo marca `campo: boolean` em código, e o menu de mobile é
`registo.filter(campo) ∩ projecção do tenant`, pelo que a projecção não consegue promover uma rota de
escritório para o telemóvel. O que **não** tem substituto é o número: ninguém conta ao compilar uma
lista que chega por HTTP, e um tenant pode configurar 1 ou 9 itens de campo. **Fica sem mecanismo**, e
está escrito assim em vez de disfarçado com um teste que mede outra coisa.

**O resto do shell.** Largura de desenho 1440px, obrigatória a 1280 (o portátil real), e 360px continua
a ser referência **das rotas de campo** e não de todas. Nenhuma rota é bloqueada em mobile — deep links
têm de funcionar — mas só as de campo são desenhadas para 360; as outras a 360 têm scroll horizontal na
tabela, e isso é declarado e não um defeito. Navegação: sidebar persistente e colapsável em desktop,
**a mesma** sidebar como drawer a partir do header em mobile, e nenhuma terceira superfície de
navegação; a tab bar sai. A projecção é uma **lista com um nível de agrupamento**
(`route_id, grupo, ordem, visivel, rotulo`), nunca uma árvore: esconder e reordenar uma árvore é um
problema muito maior e "cresce" não precisa dele. O cap de `72rem` do `DESIGN.md` §4 passa a aplicar-se
a formulários e leitura; tabelas usam a largura toda da área de conteúdo. E duas coisas que se vão
querer juntar e são diferentes: o **seletor de tenant** é do shell (`accounts`, ADR 0007) e vive no pé
da sidebar; o **seletor de loja** é do ecrã (`inventory`, guião Q2) e fica na barra do ecrã.

**Alternativas.** Manter a tab bar e acrescentar sidebar (o estado da ADR 0008) — o dono rejeitou-a, e
um cap de quatro não carrega um menu de ERP. Menu só em código, personalizado por flags de operador —
flags são ferramenta de operador, e o pedido é "cada empresa personaliza a seu gosto". **Rotas como
dados**, com a árvore gerada da configuração — mata os search params tipados, mata o code-splitting em
build, põe o deep link a depender da configuração e transforma esconder em pseudo-autorização. Duas
apps (PWA de campo + ERP de escritório) — dois bundles, duas autenticações e o dobro da superfície de
frontend, sem sinal nenhum da secção 7 do `ARCHITECTURE.md`. Manter o §0 do guião como orçamento global
— era desenhado para um público que mudou, e um ERP não cabe em 7 linhas.

**Consequências.** A decisão 2 da ADR 0008 fica **superada nesta parte** (as decisões 1 e 3 ficam
intactas): `ITENS_DA_TAB_BAR`, `ItensDaTabBar` e o tipo `SoMobile` desaparecem, e com eles o único gate
que o `typecheck` tinha sobre navegação. O `DESIGN.md` §4 e §1 ficam **devidos e não editados aqui** —
não é o meu ficheiro e há um agente a escrever em `frontend/`; o §4 perde a tab bar e ganha duas
larguras de referência, o §1 reescreve-se com as duas razões juntas, para não se reescrever duas vezes.
**Dos quatro ecrãs construídos, sobrevive o conteúdo e refaz-se o invólucro.** Sobrevive tudo o que é
domínio: a anatomia das linhas, a ordem ("o pior primeiro" no Stock, por localização física no Contar),
a distinção entre "consumir até" e DDM, o fluxo de motivo de desperdício, a conversão à vista na linha
de fatura, a temperatura à entrega, o badge do NIF diferente, as fixtures, os `schemas.ts`, os `api.ts`
e as sondas da Q1, Q2, Q7 e Q10. Refaz-se o orçamento de ecrã como lei de layout, e com ele a
composição do **Stock** e dos **Alertas**, que passam a tabela densa; o **Contar** e o **Receber** ficam
como estão, porque são as rotas de campo e 360px é o desenho certo para elas. **O que recomendo não
fazer agora:** reestruturar o Stock e os Alertas antes da sessão 0. É a mesma obra que o redesenho
visual já devido, e fazê-la duas vezes é o erro que o banner do `DESIGN.md` nomeia; o mínimo que esta
direcção exige do shell existente é tirar a tab bar. Se a sessão 0 ainda corre com este shell, e em que
forma, é decisão do dono do produto e não minha.
