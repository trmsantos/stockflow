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
 * **1. Prosa acentuada fora de um catálogo é erro.** Um literal com uma letra
 * acentuada num nó de texto de JSX, ou num `title`/`aria-label`/`placeholder`,
 * fora dos `textos.*.ts`. O critério é o acento e isso **diz-se em vez de se
 * prometer**: apanha "Não foi possível" e **não** apanha "Save" nem "Total". É um
 * gate de cobertura parcial com um critério legível, e a alternativa — tentar
 * distinguir prosa de identificador — era um gate que ninguém confia.
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
 */
const SEM_CATALOGO = new Set([
  // Entrada e activação: quem não os entende não chega a lado nenhum.
  "src/features/accounts/screens/entrar.tsx",
  "src/features/accounts/screens/ativar.tsx",
  // As Definições e as suas quatro secções.
  "src/features/accounts/screens/definicoes.tsx",
  "src/features/accounts/components/secao-aparencia.tsx",
  "src/features/accounts/components/secao-estabelecimento.tsx",
  "src/features/accounts/components/secao-navegacao.tsx",
  "src/features/accounts/components/secao-equipa.tsx",
  "src/features/accounts/components/formulario-de-convite.tsx",
  "src/features/accounts/components/segredo-do-convite.tsx",
  "src/features/accounts/components/tabela-de-convites.tsx",
  // Os ecrãs de operação, pela ordem de uso.
  "src/features/inventory/screens/stock.tsx",
  "src/features/inventory/screens/alertas.tsx",
  "src/features/inventory/screens/artigo.tsx",
  "src/features/inventory/screens/contar.tsx",
  "src/features/inventory/screens/fecho-de-contagem.tsx",
  "src/features/inventory/components/barra-de-filtros.tsx",
  "src/features/inventory/components/fecho-de-contagem.tsx",
  "src/features/inventory/components/formulario-de-desperdicio.tsx",
  "src/features/inventory/components/historico-de-movimentos.tsx",
  "src/features/inventory/components/linha-de-contagem.tsx",
  "src/features/purchasing/screens/receber.tsx",
  "src/features/purchasing/screens/rececao.tsx",
  "src/features/purchasing/screens/fotografar.tsx",
  "src/features/purchasing/components/cabecalho-da-rececao.tsx",
  "src/features/purchasing/components/esqueletos.tsx",
  "src/features/purchasing/components/tabela-de-linhas-de-fatura.tsx",
  "src/features/purchasing/components/tabela-de-rececoes.tsx",
  "src/features/purchasing/components/temperatura-a-entrega.tsx",
  "src/features/reporting/screens/inicio.tsx",
  "src/features/reporting/screens/painel.tsx",
  "src/features/reporting/components/abas-do-painel.tsx",
  "src/features/reporting/components/barra-do-painel.tsx",
  "src/features/reporting/components/fecho-do-mes.tsx",
  "src/features/reporting/components/perdas-do-periodo.tsx",
  "src/features/reporting/components/pessoal-do-mes.tsx",
  "src/features/reporting/components/resultado-do-mes.tsx",
  "src/features/reporting/components/variacao-no-periodo.tsx",
  // Componentes partilhados.
  "src/components/barras-ordenadas.tsx",
]);

/** O que não entra: o gerado, o do CLI do shadcn, e o que não vai para produção. */
const IGNORAR = [
  "src/dev/",
  "src/components/ui/",
  "src/lib/api/types.ts",
];

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
const TEXTO_JSX = />([^<>{}]*[À-ÿ][^<>{}]*)</g;
const ATRIBUTO = /(?:aria-label|title|placeholder|alt)="([^"]*[À-ÿ][^"]*)"/g;

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

  // 1. Prosa acentuada fora do catálogo.
  const achados = [];
  for (const m of fonte.matchAll(TEXTO_JSX)) {
    const t = m[1].trim();
    if (t) achados.push(t);
  }
  for (const m of fonte.matchAll(ATRIBUTO)) achados.push(m[1]);
  for (const t of achados) {
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
