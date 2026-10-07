# ADR 0015 — Três paletas, e o alvo do gate passa de uma para N

**Contexto.** O dono do produto pediu "definições de light e dark mode, e um meio termo". O §2 do
`DESIGN.md` afirma hoje **"uma paleta só, e é escura"**, com o modo claro como dívida nomeada, e o
`frontend/scripts/check-design-tokens.mjs` **impõe-no**: falha se aparecer um bloco
`prefers-color-scheme` com uma paleta parcial, e a razão escrita é boa — "um modo claro a meio é pior
do que não ter modo claro: dá uma app com metade das cores erradas a quem tem o sistema em claro".
Este gate já mudou de alvo uma vez, a 2026-10-01, quando a paridade entre dois modos passou a ser uma
afirmação sobre um conjunto vazio, e a frase que ele escreveu então é a que decide esta ADR:
**relaxar um gate é afirmar menos sobre a mesma coisa; mudar o que ele afirma, porque a coisa mudou, é
outra.** O que torna isto barato é uma propriedade já paga: não há um `#hex` nem um `bg-[…]` em código
nosso e a paleta default do Tailwind está removida, logo nenhum componente sabe de que paleta é a cor
que usa. Três paletas são três blocos de CSS e **zero** alterações a componentes.

**Decisão 1 — Três paletas completas, e a selecção é um atributo no `<html>`, não uma media query.**
`data-tema`, com `claro | meio_termo | escuro`; o `escuro` fica na `:root` sem atributo, porque é o
default e é a identidade aprovada, e as outras duas em `:root[data-tema=…]` dentro do `tokens.css`.
Não é `prefers-color-scheme` por duas razões independentes: a preferência é **da pessoa** e vive no
servidor (ADR 0016), não na configuração do sistema operativo de quem olha; e uma media query tem dois
estados para três paletas. Em consequência, `prefers-color-scheme` passa a ser proibido em `src/**`
**inteiro**, incluindo o `tokens.css` — deixou de selecionar o que quer que seja, e uma segunda forma
de escolher paleta é uma segunda fonte de verdade.

**Decisão 2 — O meio termo é um terceiro conjunto de superfícies, não um `opacity` por cima do
escuro.** São superfícies de grafite com texto claro: a mesma **direcção** do escuro, logo herda a
identidade e a leitura de dois metros do §1 (o trilho de 4px, a excepção que se vê sem se ler), e sobe
as superfícies o suficiente para matar a halation do texto claro sobre quase-preto num monitor barato e
numa sala com a persiana aberta. A alternativa de leitura — um claro esbatido — é uma paleta clara com
menos contraste, isto é, pior do que o claro precisamente naquilo para que o claro serve. E um
`opacity` sobre o escuro **não é uma paleta**: multiplica tudo pelo mesmo factor, não redefine token
nenhum, e um token que caia a 4,4:1 não aparece em medição alguma porque não existe como valor.

**Decisão 3 — Acentos e cores de estado são redefinidos em cada paleta, e isto não é uma proibição de
partilhar: é o que a medição obriga.** O mesmo `oklch` que dá 5,5:1 sobre quase-preto dá muito menos
sobre papel. O gate **não** exige que os valores difiram; exige que **cada paleta passe a sua própria
medição**, e um valor copiado que não passe falha na paleta onde não passa. É a mecânica do resto deste
sistema: tornar impossível em vez de proibir.

**Decisão 4 — O gate muda de "uma paleta completa e nenhuma alternativa" para "N paletas, cada uma
completa e cada uma medida".** Quatro pontos:

1. **Completa são os 18 tokens de cor** — os nove de estrutura e os três papéis de cada uma das três
   cores de estado — **mais os dois de sombra**. Um tema que entre com 17 dos 18 falha, por igualdade
   de conjuntos contra a paleta default, que é o que o gate já faz hoje a um bloco
   `prefers-color-scheme`. As sombras entram porque **a paleta não é só `--color-*`**: o `--shadow-sm`
   codifica "num fundo preto a sombra não separa, o que separa é o fio de luz na aresta de cima", e num
   fundo claro isso inverte-se — um fio de luz branco sobre papel não existe e a sombra volta a ser o
   que separa. Um tema claro com as sombras do escuro é um tema a 16 de 18 que o gate de hoje daria por
   completo.
2. **A pior superfície é calculada, não nomeada.** Por paleta: o contraste do `foreground` contra cada
   uma das três superfícies, e a **menor** é o fundo contra o qual se mede todo o texto e toda a
   fronteira. No escuro isso devolve o `surface-2`, que é o que o §2 já diz; no claro devolve a **mais
   escura** das três. Nomear o `surface-2` numa paleta clara seria medir contra o melhor fundo e
   chamar-lhe o pior. O gate imprime qual é, por paleta, em cada corrida: se mudar, muda num diff.
3. **Gamut sRGB a 1e-6 e os mínimos de sempre, por paleta**: 4,5:1 para texto (incluindo o `foreground`
   sobre cada tinta `-surface` e o `primary-foreground` sobre o `primary`), 3:1 para fronteira de
   componente, e o `--color-border` isento por ser separador decorativo. Os papéis continuam a derivar
   do **nome** do token, logo um `--color-info` novo passa a exigir os seus três papéis nas **três**
   paletas sem ninguém o inscrever.
4. **A paridade com o §2 do `DESIGN.md` mantém-se token a token e passa a ser por paleta**, incluindo o
   número de paletas. O custo é o §2 passar a ter três blocos de cor; é o preço de a fonte da verdade
   ser o CSS e o documento afirmá-la, e é mecânico.

**O que esta ADR não faz, e é deliberado: não escreve as duas paletas novas.** Trinta e seis valores só
existem **medidos**, e medir é correr o gate. O §2 fica emendado com a decisão e com o alvo novo, a
dizer que a `claro` e a `meio_termo` **ainda não existem**; elas entram, com os seus blocos no
`tokens.css` e no §2, na mesma alteração que muda o gate — e até aí a paridade continua verdadeira com
uma paleta de cada lado. Um §2 com três paletas e um `tokens.css` com uma põe o `pnpm lint` vermelho no
mesmo minuto, que é o gate a trabalhar e não um obstáculo.

**Alternativas.** *`prefers-color-scheme` para o claro e o escuro, e o meio termo por atributo* — dois
mecanismos de selecção para três paletas, e o aspecto de duas delas a depender da configuração do
sistema de quem olha, que é o bug que o `tokens.css` já nomeia por escrito. *Reanimar o variant `dark:`*
— selecciona dois estados e há três, e com a paleta nos tokens nenhum componente precisa de saber qual
está activa; fica inerte, e a regra de lint que o recusa fica, agora com uma segunda razão. *Um claro
parcial agora e o resto depois* — é exactamente o que a razão escrita no gate recusa, e continua a valer
palavra por palavra. *Deixar o utilizador escolher a cor de acento* — o gate mede **ficheiros**, não
linhas de base de dados: um acento escolhido num formulário é uma paleta que ninguém mediu, e põe a
acessibilidade atrás de um selector de cor. Não entra, nem como dívida.

**Consequências.** Zero backend e zero contrato. No frontend: o `tokens.css` ganha dois blocos e o
`color-scheme` da `:root` deixa de ser `dark` fixo — é `light` na paleta clara e `dark` nas outras duas,
porque é ele que alinha as barras de scroll, o caret, o autofill e os controlos nativos, e é essa a razão
pela qual a linha existe. O `src/lib/theme-color.ts` volta a ter o que ouvir: hoje lê o
`--color-background` uma vez, com o comentário "há uma paleta só e ela não muda em runtime", e passa a
reagir à troca de **tema** — não ao `prefers-color-scheme`, que foi o listener que de lá saiu.
`check-design-tokens.mjs` é reescrito em `paletasDe`, `verificarPaletaUnica` e `medirPaleta`, e quem o
reescrever confirma-o com uma sonda em **cada** direcção: um tema com 17 tokens tem de dar exit 1, e um
token fora do gamut numa paleta que não é a default também. O `DESIGN.md` §2 e a checklist do §6 ficam
emendados nesta sessão (os itens "não comecei um segundo modo de cor" e "nenhum `dark:`" mudam de razão,
não de resposta).

**O que fica por decidir.** Se o meio termo passa a ser o **default** das contas novas: há argumento (é
o mais tolerante a um monitor barato), e o default de hoje é a identidade que o dono aprovou e viu
a correr. Gatilho: a sessão 0, com as três paletas na mão. E se existe uma quarta paleta de contraste
reforçado para a copa com sol directo — ninguém a pediu, e seriam mais 18 tokens a manter medidos.
