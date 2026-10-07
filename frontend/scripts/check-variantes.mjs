/**
 * Gate: toda a variante `data-<palavra>:` usada em `src/` está declarada em
 * `src/styles/variantes.css`, e toda a declarada é usada.
 *
 * ## Porque existe
 *
 * As variantes dos primitivos shadcn vinham de `@import "shadcn/tailwind.css"`,
 * o que fazia do `shadcn` dependência de build por causa de vinte linhas de CSS
 * — e arrastava um aviso `high` do `braces` **sem correcção a montante**. As três
 * variantes que o código usa passaram a ser nossas (ver o ficheiro), e isso cria
 * um risco novo: se um primitivo instalado por `pnpm dlx shadcn@latest add …`
 * usar uma variante que não está declarada, **o Tailwind não a gera e não se
 * queixa**. A classe fica no HTML, não faz nada, e nada fica vermelho.
 *
 * ## A primeira versão deste gate estava errada, e foi ele que o mostrou
 *
 * Escrevi-o a exigir declaração para **toda** a variante `data-<palavra>:`, e ele
 * apanhou logo `data-placeholder:` no `select.tsx` — que o pacote shadcn também
 * nunca declarou. Medi no CSS compilado antes de concluir: o Tailwind v4 gera
 * `data-<palavra>:` nativamente como `[data-<palavra>]`, logo aquela funcionava e
 * funciona.
 *
 * O risco real é mais estreito e mais perigoso: o Radix não escreve
 * `data-open` nos primitivos antigos — escreve **`data-state="open"`**. Uma
 * variante `data-open:` sem a nossa declaração cai no nativo `[data-open]`, que
 * **nunca casa** com esse atributo. A classe existe, o CSS existe, e o estilo não
 * aparece. É a pior forma de falha: nada vermelho em sítio nenhum.
 *
 * Daí a lista fechada `DO_RADIX`: só os nomes que o Radix expressa por
 * `data-state` exigem declaração. As outras variantes `data-*` passam porque o
 * nativo as serve — e a forma arbitrária (`data-[state=active]:`) fica de fora
 * pela própria forma do padrão, que exige uma palavra e não um `[`.
 *
 * Falha também no sentido inverso: uma variante declarada e sem utilizações é
 * código morto que um dia alguém "corrige" a copiar as nove outra vez.
 */

/**
 * Os nomes em que a variante nativa do Tailwind **não basta**. Lista fechada, a
 * estender quando um primitivo novo trouxer outro — e a estender **aqui**, que é
 * onde se vê.
 *
 * Duas razões diferentes entram na mesma lista:
 *
 *  - a maioria porque o Radix os expressa por **`data-state`** (`data-state="open"`),
 *    e o nativo `[data-open]` nunca casa com isso;
 *  - o `data-disabled` porque o Radix o escreve como atributo próprio mas pode
 *    trazer o valor `"false"`, e o nativo `[data-disabled]` casa com a presença do
 *    atributo — logo aplicava o estilo de desactivado a um controlo activo.
 *
 * As duas dão a mesma falha silenciosa, por caminhos opostos: uma nunca aplica o
 * estilo, a outra aplica-o quando não devia.
 */
const DO_RADIX = new Set([
  "data-open",
  "data-closed",
  "data-checked",
  "data-unchecked",
  "data-indeterminate",
  "data-active",
  "data-inactive",
  "data-on",
  "data-off",
  "data-visible",
  "data-hidden",
  "data-delayed-open",
  "data-instant-open",
]);
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const FICHEIRO = "src/styles/variantes.css";

/** Os nomes declarados, na ordem em que aparecem. */
function declaradas() {
  const css = readFileSync(FICHEIRO, "utf8");
  return new Set([...css.matchAll(/@custom-variant\s+([a-z][a-z0-9-]*)\s*\{/g)].map((m) => m[1]));
}

function ficheiros(raiz) {
  const saida = [];
  for (const nome of readdirSync(raiz)) {
    const caminho = join(raiz, nome);
    if (statSync(caminho).isDirectory()) saida.push(...ficheiros(caminho));
    else if (/\.(tsx?|css)$/.test(nome) && caminho !== FICHEIRO) saida.push(caminho);
  }
  return saida;
}

/**
 * As utilizações, com o ficheiro onde estão. O prefixo opcional cobre
 * `group-data-open:` e `peer-data-closed:`, que usam a mesma declaração.
 */
function usadas() {
  const porNome = new Map();
  for (const caminho of ficheiros("src")) {
    const texto = readFileSync(caminho, "utf8");
    for (const m of texto.matchAll(/(?:^|[\s"'`:[])(?:group-|peer-)?(data-[a-z][a-z0-9-]*):/g)) {
      const nome = m[1];
      if (!porNome.has(nome)) porNome.set(nome, new Set());
      porNome.get(nome).add(caminho);
    }
  }
  return porNome;
}

const temos = declaradas();
const usa = usadas();
const problemas = [];

for (const [nome, ondes] of usa) {
  if (DO_RADIX.has(nome) && !temos.has(nome)) {
    problemas.push(
      `  ${nome}: usada em ${[...ondes].join(", ")} e **não declarada** em ${FICHEIRO}.\n` +
        `    É um dos valores que o Radix escreve em \`data-state\`. Sem a declaração, esta\n` +
        `    variante cai no nativo do Tailwind (\`[${nome}]\`), que nunca casa com\n` +
        `    \`data-state="${nome.slice(5)}"\` — a classe existe e o estilo não aparece, sem erro.\n` +
        `    Copia a declaração do CLI (\`pnpm dlx shadcn@latest\` tem-na em dist/tailwind.css).`,
    );
  }
}
for (const nome of temos) {
  if (!usa.has(nome)) {
    problemas.push(
      `  ${nome}: declarada em ${FICHEIRO} e sem utilizações. Apaga-a — uma variante morta\n` +
        `    convida a copiar as nove outra vez "por segurança".`,
    );
  }
}

if (problemas.length > 0) {
  console.error(`check-variantes: ${String(problemas.length)} problema(s).\n`);
  console.error(problemas.join("\n\n"));
  process.exit(1);
}

const nativas = [...usa.keys()].filter((n) => !temos.has(n)).length;
console.log(
  `check-variantes: ${String(temos.size)} declarada(s) e todas usadas (${[...temos].join(", ")}); ` +
    `${String(nativas)} servida(s) pelo nativo do Tailwind.`,
);
console.log("check-variantes: sem problemas.");
