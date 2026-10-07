#!/usr/bin/env node
/**
 * check-textos — a copy visível vive num catálogo, e o que falta é **declarado**.
 *
 * ## O que este gate mede, e o que não consegue medir
 *
 * O `pnpm typecheck` garante que um catálogo que exista está **completo** nas
 * duas línguas (o `typeof PT` do `textos.en.ts`). O que ele não vê é uma string
 * escrita à mão num ecrã, que não está em catálogo nenhum e por isso nunca se
 * traduz. É isso que este ficheiro mede, em três metades que falham nos dois
 * sentidos.
 *
 * **1. Copy fora de um catálogo é erro**, em duas formas com dois critérios
 * diferentes — e a diferença é o que os torna honestos.
 *
 * **1a. Num nó de texto de JSX, qualquer palavra.** Num ficheiro já traduzido um
 * nó de texto não tem palavra nenhuma: o que lá está é `{textos.x}`, um `·` ou um
 * número. Logo o critério não precisa de adivinhar o que é prosa — basta uma
 * palavra. Foi medido antes de ser adoptado: nos ficheiros traduzidos deu seis
 * strings reais ("Tentar outra vez", "A carregar…", "A filtrar por", …), todas
 * copy que o critério do acento não via, mais o nome do produto.
 *
 * **1b. Numa string de código, prosa acentuada ou uma frase com maiúscula.**
 * Aqui a regra de 1a não serve — o código é feito de strings — e o que separa uma
 * frase de um identificador são dois sinais: o acento, e **começar por maiúscula
 * e ter uma segunda palavra**. O segundo entrou a 2026-10-07 porque o primeiro
 * deixava passar copy sem acentos: o `Estabelecimento: ${nome}` do pé da sidebar,
 * o "A carregar" do indicador e o "A sair…" do botão de sair. Medido: dá cinco
 * achados em todo o `src/`, os cinco reais, e zero falsos.
 *
 * Fica de fora uma **palavra só** sem acento — um `rotulo="Email"` — e isso
 * **diz-se em vez de se prometer**: distinguir "Email" de "icon-sm" sem um
 * dicionário era um gate em que ninguém confia. Os atributos não têm regra
 * própria porque um `title="…"` **é** uma string de código.
 *
 * A segunda forma entrou a 2026-10-07 e **a medição que a trouxe importa**: com a
 * regra só em JSX, a lista fechada dizia 32 ficheiros por traduzir e havia 60 com
 * prosa. Um `vocabulario.ts`, um `secoes.ts` e as mensagens de Zod dos
 * `schemas.ts` são copy que nunca passa por um nó de JSX — logo a lista media uma
 * coisa mais pequena do que a que prometia, e esvaziá-la não teria ligado o
 * inglês: teria ligado metade dele.
 *
 * O que **não** é copy declara-se no `NAO_E_COPY`, por string exacta e com a
 * razão ao lado.
 *
 * **2. Um ficheiro de `screens/` ou de `shell/` sem catálogo é erro**, salvo
 * lista fechada. É o grão certo: um ecrã está traduzido ou não está, e um ecrã a
 * meio é o que a ADR 0019 proíbe. A lista é o meio caminho **declarado**, como o
 * `DECLARADAS` do `security_check.sh`: encurta num diff em vez de viver
 * escondida, e quando ficar vazia o inglês liga-se.
 *
 * **3. Uma chave de catálogo que nenhum ficheiro usa é erro.** É a direcção que
 * o compilador não cobre: ele exige que o inglês tenha o que o português tem, e
 * nenhum dos dois sabe se alguém lê a chave. Um catálogo cresce por acrescento e
 * ninguém o poda.
 *
 * ## Porque é que a lista fechada não é uma supressão
 *
 * Um ficheiro na lista está a dizer "esta copy ainda não foi traduzida", que é
 * verdade e é visível. Tirá-lo de lá é o commit que traduz o ecrã. O que a lista
 * **não** faz é esconder: ela aparece no fim de cada corrida com a contagem, e o
 * teste do backend (`test_i18n.py`) afirma que a app serve uma língua só
 * enquanto ela não estiver vazia.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const RAIZ = "src";

/**
 * Os ficheiros cuja copy **ainda não** está em catálogo. Lista fechada.
 *
 * Cada linha que sai daqui é um ecrã traduzido. Quando ficar vazia, o inglês
 * liga-se com duas linhas — uma no `LINGUAS` do `src/lib/i18n.ts` e outra no
 * `LANGUAGES` do `backend/config/settings/base.py` — e a partir daí o
 * `escolher` passa a exigir a entrada inglesa em **todos** os catálogos, porque
 * é um `Record` sobre a união das línguas.
 *
 * A ordem é a de uso dos ecrãs, que é a ordem por que a ADR 0019 manda traduzi-los.
 *
 * A lista subiu de 32 para 60 a 2026-10-07, e **não foi uma regressão**: foi o
 * gate a passar a ver as strings de código (ver a regra 1 acima). Os 28 que
 * entraram tinham a copy toda fora de JSX, e já estavam por traduzir antes de
 * alguém os contar.
 */
const SEM_CATALOGO = new Set([
  // ## accounts — o que falta das Definições e dos convites
  "src/features/accounts/components/secao-equipa.tsx",
  "src/features/accounts/components/formulario-de-convite.tsx",
  "src/features/accounts/components/segredo-do-convite.tsx",
  "src/features/accounts/components/tabela-de-convites.tsx",
  "src/features/accounts/components/validade-do-convite.tsx",
  "src/features/accounts/erros.ts",
  "src/features/accounts/schemas.ts",
  "src/features/accounts/secoes.ts",
  // ## O que é de toda a aplicação, e por isso se traduz primeiro
  "src/features/accounts/screens/entrar.tsx",
  // ## inventory — os ecrãs de operação, pela ordem de uso
  "src/features/inventory/screens/stock.tsx",
  "src/features/inventory/screens/alertas.tsx",
  "src/features/inventory/screens/artigo.tsx",
  "src/features/inventory/screens/contar.tsx",
  "src/features/inventory/screens/fecho-de-contagem.tsx",
  "src/features/inventory/components/barra-de-filtros.tsx",
  "src/features/inventory/components/estados-da-lista.tsx",
  "src/features/inventory/components/fecho-de-contagem.tsx",
  "src/features/inventory/components/formulario-de-desperdicio.tsx",
  "src/features/inventory/components/historico-de-movimentos.tsx",
  "src/features/inventory/components/linha-de-contagem.tsx",
  "src/features/inventory/components/numeros-do-topo.tsx",
  "src/features/inventory/components/numeros-dos-alertas.tsx",
  "src/features/inventory/components/progresso-da-contagem.tsx",
  "src/features/inventory/components/tabela-de-alertas.tsx",
  "src/features/inventory/components/tabela-de-desperdicio.tsx",
  "src/features/inventory/components/tabela-de-stock.tsx",
  "src/features/inventory/components/validade.tsx",
  "src/features/inventory/leitura-da-validade.ts",
  "src/features/inventory/vocabulario.ts",
  // ## purchasing
  "src/features/purchasing/screens/receber.tsx",
  "src/features/purchasing/screens/rececao.tsx",
  "src/features/purchasing/screens/fotografar.tsx",
  "src/features/purchasing/components/badges-de-rececao.tsx",
  "src/features/purchasing/components/cabecalho-da-rececao.tsx",
  "src/features/purchasing/components/esqueletos.tsx",
  "src/features/purchasing/components/numeros-de-rececoes.tsx",
  "src/features/purchasing/components/tabela-de-linhas-de-fatura.tsx",
  "src/features/purchasing/components/tabela-de-rececoes.tsx",
  "src/features/purchasing/components/temperatura-a-entrega.tsx",
  "src/features/purchasing/vocabulario.ts",
  // ## reporting
  "src/features/reporting/screens/inicio.tsx",
  "src/features/reporting/screens/painel.tsx",
  "src/features/reporting/abas.ts",
  "src/features/reporting/components/abas-do-painel.tsx",
  "src/features/reporting/components/barra-do-painel.tsx",
  "src/features/reporting/components/cartoes-do-inicio.tsx",
  "src/features/reporting/components/dinheiro-do-periodo.tsx",
  "src/features/reporting/components/fecho-do-mes.tsx",
  "src/features/reporting/components/numeros-do-periodo.tsx",
  "src/features/reporting/components/perdas-do-periodo.tsx",
  "src/features/reporting/components/pessoal-do-mes.tsx",
  "src/features/reporting/components/qualidade-dos-dados.tsx",
  "src/features/reporting/components/resultado-do-mes.tsx",
  "src/features/reporting/components/variacao-no-periodo.tsx",
  "src/features/reporting/contagem.ts",
  "src/features/reporting/vocabulario.ts",
  // ## Componentes partilhados. O `barras-ordenadas` tem **uma** palavra visível
  // ("Proporção") e um catálogo próprio para ela era desproporcionado: sai desta
  // lista com os ecrãs do `reporting`, que são os que o usam.
  "src/components/barras-ordenadas.tsx",
]);

/** O que não entra: o gerado, o do CLI do shadcn, e o que não vai para produção. */
const IGNORAR = [
  "src/dev/",
  "src/components/ui/",
  "src/lib/api/types.ts",
];

/**
 * As strings acentuadas que **não são copy** e por isso vivem fora de um
 * catálogo. Lista fechada, por string exacta.
 *
 * O critério é um só: **ninguém as lê**. Uma mensagem de Zod sobre a forma da
 * *resposta* do servidor não chega a um ecrã — um contrato partido vira
 * `ErroDeContrato` e o ecrã mostra a frase do `erros.ts` —, e uma recusa de
 * search param também não, porque a ADR 0008 manda cair para o default sem dizer
 * nada. Traduzi-las era prometer que alguém as lê.
 *
 * Por string e não por ficheiro de propósito: um `schemas.ts` tem as duas coisas
 * lado a lado — a mensagem do formulário, que se lê, e a da resposta, que não — e
 * uma excepção por ficheiro deixava passar a primeira.
 */
const NAO_E_COPY = new Set([
  // Zod sobre a forma da resposta: o consumidor é o `ErroDeContrato`.
  "decimal inválido",
  "hora inválida",
  "NIF inválido",
  "mês inválido (YYYY-MM)",
  "A sessão diz-se ativa sem estabelecimento, ou o contrário: o invariante da ADR 0010 não se verifica nesta resposta.",
  // Recusas de search param: a ADR 0008 cai para o default em silêncio.
  "o destino tem de ser um caminho desta aplicação",
  "o destino não pode ser a entrada",
  // O nome do produto. Entra por causa da regra 1a, que conta palavras: é a
  // única palavra que aparece num nó de texto de JSX e **não** se traduz.
  "StockFlow",
  // Diagnóstico que não chega a um ecrã: o `message` de um `ApiError` que tem
  // `detail` (o `mensagemDeErro` prefere o `detail`), e o `throw` do arranque,
  // que só dispara se o `index.html` não tiver o `<div id="root">`.
  "Cookie csrftoken ausente.",
  'Falta o <div id=\\"root\\"> no index.html.',
]);

function ficheiros(dir) {
  const saida = [];
  for (const nome of readdirSync(dir)) {
    const caminho = join(dir, nome);
    if (statSync(caminho).isDirectory()) {
      saida.push(...ficheiros(caminho));
    } else if (/\.tsx?$/.test(nome)) {
      saida.push(caminho);
    }
  }
  return saida;
}

/** Sem comentários: este repositório tem mais comentário do que código. */
function semComentarios(fonte) {
  return fonte.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

const ACENTUADA = /[À-ÿ]/;
const PALAVRA = /[A-Za-zÀ-ÿ]{2,}/;
/**
 * Uma frase: começa por maiúscula e tem uma segunda palavra (ou uma
 * interpolação). É o segundo sinal da regra 1b, para a copy que não tem acentos.
 */
const FRASE = /^[A-ZÀ-Þ][a-zà-ÿ]*[ :,]\s*[A-Za-zÀ-ÿ$]/;

/**
 * Um nó de texto de JSX: o que fica entre um `>` que fecha uma tag e o `<` que
 * abre a seguinte.
 *
 * O `(?<![=!<>-])` é o que separa uma tag de código: sem ele, o `>` de um `=>`
 * emparelha com o `<` de um genérico e o gate acusa o "new Map" de um
 * `useState(() => new Map<Campo, string>())` — medido, era o único falso positivo
 * da regra 1a. O `CODIGO` abaixo apanha o resto: o que tem `=` ou `;` no meio é
 * código, não uma frase.
 */
const TEXTO_JSX = /(?<![=!<>-])>([^<>{}]+)</g;
const CODIGO = /[=;]|\breturn\b|\bconst\b/;

/**
 * As strings do ficheiro, **consumidas pela ordem em que aparecem**.
 *
 * Um `matchAll` com `` /`[^`]*`/ `` não serve, e a primeira versão disto
 * provou-o: um template sem acento é saltado, e então o delimitador de fecho dele
 * emparelha com o de abertura do seguinte — o que fica no meio é código, e se
 * esse código tiver JSX acentuado o gate acusa uma string que não existe. Deu
 * quatro falsos positivos em quatro ficheiros, um deles no `http.ts`.
 *
 * Consumir resolve-o: cada literal fecha o seu próprio delimitador antes de a
 * varredura continuar. Uma `'` solta em prosa de JSX (um `d'água`) não parte
 * nada — não havendo fecho na linha, a varredura avança um carácter e segue.
 */
function literais(fonte) {
  const saida = [];
  let i = 0;
  while (i < fonte.length) {
    const abre = fonte[i];
    if (abre === '"' || abre === "'" || abre === "`") {
      let j = i + 1;
      while (j < fonte.length && fonte[j] !== abre) {
        if (fonte[j] === "\\") j += 1;
        else if (abre !== "`" && fonte[j] === "\n") break;
        j += 1;
      }
      if (fonte[j] === abre) {
        saida.push(fonte.slice(i + 1, j));
        i = j + 1;
        continue;
      }
    }
    i += 1;
  }
  return saida;
}

const problemas = [];
const todos = ficheiros(RAIZ)
  .map((c) => relative(".", c))
  .filter((c) => !IGNORAR.some((i) => c.startsWith(i) || c === i));

const catalogos = todos.filter((c) => /textos\.(pt|en)\.ts$/.test(c));
const chavesUsadas = new Set();

for (const caminho of todos) {
  if (/textos\.(pt|en)\.ts$/.test(caminho)) continue;
  const bruto = readFileSync(caminho, "utf8");
  const fonte = semComentarios(bruto);

  // Quem usa o catálogo, e que chaves lê.
  for (const m of fonte.matchAll(/\btextos\.([\w.]+)/g)) {
    chavesUsadas.add(m[1]);
  }

  if (SEM_CATALOGO.has(caminho)) continue;

  // 1. Prosa acentuada fora do catálogo, nas duas formas.
  const achados = new Set();
  // A regra 1a só se aplica a `.tsx`: num `.ts` não há JSX, e o `>` de um
  // genérico emparelha com o `<` do seguinte (o `escolher<T>(catalogos: Record<…`
  // do `i18n.ts` era um falso positivo exactamente assim).
  for (const m of (caminho.endsWith(".tsx") ? fonte.matchAll(TEXTO_JSX) : [])) {
    const bruta = m[1];
    const t = bruta.trim();
    if (!t || CODIGO.test(t)) continue;
    // Numa linha só, basta uma palavra. Em várias linhas há duas coisas com a
    // mesma forma — um parágrafo embrulhado pelo Prettier, que é prosa a sério, e
    // o código de JSX de um ternário (`) : x.isError ? (`) — e o que as separa é
    // o parêntese: a prosa deste produto não o usa a meio de um nó de texto, e o
    // ternário não vive sem ele. Com parêntese o critério recua para o acento,
    // que o ternário não tem; sem parêntese basta a palavra.
    const ambiguo = bruta.includes("\n") && /[()]/.test(t);
    const criterio = ambiguo ? ACENTUADA : PALAVRA;
    if (criterio.test(t)) achados.add(t);
  }
  for (const bruta of literais(fonte)) {
    const t = bruta.trim();
    if (ACENTUADA.test(t) || FRASE.test(t)) achados.add(t);
  }
  for (const t of achados) {
    if (NAO_E_COPY.has(t)) continue;
    problemas.push(`${caminho}: prosa fora do catálogo — ${JSON.stringify(t.slice(0, 60))}`);
  }

  // 2. Um ecrã ou um ficheiro do shell tem de ler de um catálogo.
  const eEcraOuShell = /^src\/(shell|features\/[^/]+\/screens)\//.test(caminho);
  const leCatalogo = /\btextos\b/.test(fonte);
  const temProsa = ACENTUADA.test(fonte);
  if (eEcraOuShell && !leCatalogo && temProsa) {
    problemas.push(
      `${caminho}: tem prosa e não lê de um catálogo. Traduz, ou declara-o no SEM_CATALOGO.`,
    );
  }
}

// 3. Chaves de catálogo que ninguém usa.
for (const caminho of catalogos) {
  if (!caminho.endsWith(".pt.ts")) continue;
  const fonte = semComentarios(readFileSync(caminho, "utf8"));
  // As chaves folha do objecto, pelo caminho: `rodape.definicoes`.
  const pilha = [];
  for (const linha of fonte.split("\n")) {
    const abre = /^\s*(\w+):\s*\{\s*$/.exec(linha);
    const folha = /^\s*(\w+):\s*(?:"|\(|`)/.exec(linha);
    if (abre) pilha.push(abre[1]);
    else if (folha) {
      const chave = [...pilha, folha[1]].join(".");
      if (![...chavesUsadas].some((u) => u === chave || u.startsWith(`${chave}.`))) {
        problemas.push(`${caminho}: a chave \`${chave}\` não é usada em sítio nenhum.`);
      }
    } else if (/^\s*\},?\s*$/.test(linha)) pilha.pop();
  }
}

if (problemas.length > 0) {
  console.error(`check-textos: ${problemas.length} problema(s).\n`);
  for (const p of problemas) console.error(`  ${p}`);
  console.error(
    "\nA copy visível vive num `textos.pt.ts`/`textos.en.ts` ao lado do ficheiro " +
      "que a usa (ADR 0019, decisão 3). Um ecrã ainda não traduzido declara-se no " +
      "`SEM_CATALOGO` deste ficheiro — e é essa lista que, ao ficar vazia, liga o inglês.",
  );
  process.exit(1);
}

const traduzidos = todos.filter(
  (c) => /^src\/(shell|features\/[^/]+\/(screens|components))\//.test(c) && !SEM_CATALOGO.has(c),
).length;
console.log(
  `check-textos: ${catalogos.length} catálogo(s), ${chavesUsadas.size} chave(s) em uso, ` +
    `${SEM_CATALOGO.size} ficheiro(s) por traduzir.`,
);
console.log(
  SEM_CATALOGO.size === 0
    ? "check-textos: a lista está vazia — o inglês pode ser ligado (duas linhas, ver o cabeçalho)."
    : `check-textos: ${traduzidos} ficheiro(s) de ecrã/shell já com catálogo. Sem problemas.`,
);
