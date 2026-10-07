#!/usr/bin/env node
/**
 * check-marca — o ícone do separador **abre**, e as cores dele são os tokens.
 *
 * ## O defeito que o trouxe
 *
 * O `public/favicon.svg` nasceu a 2026-10-06 com um comentário a explicar de que
 * tokens é feito, e os nomes dos tokens CSS começam por dois hífenes. **Um
 * comentário de XML não pode conter dois hífenes seguidos**, logo o ficheiro não
 * era XML bem formado, logo o browser recusava-o inteiro e mostrava o globo
 * cinzento por omissão. Esteve assim desde que nasceu e foi o dono do produto a
 * dá-lo por isso no dia seguinte.
 *
 * O modo de falha é o pior que há: o `pnpm build` copia o ficheiro sem o olhar, o
 * servidor responde `200 image/svg+xml`, nenhum gate falha, e o único sintoma é
 * um ícone que não aparece num sítio onde ninguém procura defeitos.
 *
 * ## O que isto mede, e o que não consegue medir
 *
 * **1. O comentário é legal em XML**: nenhum `--` dentro dele, e cada `<!--`
 * fecha. É a regra que apanha o defeito de ontem, e é a que um humano volta a
 * quebrar — porque escrever o nome de um token num comentário é a coisa natural a
 * fazer.
 *
 * **2. O documento tem a forma de um ícone**: raiz `<svg>`, `viewBox`, e nenhuma
 * referência externa (`href`, `url(`, `<image>`, `<use>`). Um favicon é
 * rasterizado num contexto sem rede e sem CSS da aplicação: uma referência
 * externa não falha — desenha menos, em silêncio.
 *
 * **3. As quatro cores são os tokens.** Cada `rect` declara `data-token` e o
 * valor do `fill` é comparado com esse token na **paleta escura** do
 * `tokens.css`, que é a do azulejo (a razão está no comentário do SVG). É a
 * promessa que o próprio ficheiro já fazia e que não existia: ele dizia "o
 * `scripts/check-marca.mjs` compara-as token a token a cada `pnpm lint`" e o
 * script não existia. Uma promessa num comentário não é um gate.
 *
 * **O que não mede: que o ícone desenhe.** Isso precisa de um rasterizador, e o
 * Node não traz nenhum. Entre "parece XML" e "um browser abriu-o", o que este
 * gate afirma é o primeiro — e a prova do segundo fez-se uma vez, à mão, com o
 * ficheiro carregado como `<img>` numa página de ensaio ao lado do PNG do iOS.
 * Está dito em vez de prometido.
 */
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const FAVICON = join(RAIZ, "public/favicon.svg");
const TOKENS_CSS = join(RAIZ, "src/styles/tokens.css");

const problemas = [];
const svg = readFileSync(FAVICON, "utf8");

// --- 1. Os comentários são legais em XML.
let posicao = 0;
let comentarios = 0;
while (posicao < svg.length) {
  const abre = svg.indexOf("<!--", posicao);
  if (abre === -1) break;
  const fecha = svg.indexOf("-->", abre + 4);
  if (fecha === -1) {
    problemas.push("há um `<!--` que nunca fecha: o documento não é XML bem formado.");
    break;
  }
  const corpo = svg.slice(abre + 4, fecha);
  if (corpo.includes("--")) {
    const onde = corpo.split("--")[0]?.split("\n").length ?? 0;
    problemas.push(
      "um comentário de XML não pode conter dois hífenes seguidos, e este contém " +
        `(a ~${String(onde)} linhas do início do comentário). O browser recusa o ` +
        "ficheiro inteiro e mostra o ícone por omissão. Escreve `color-primary` em " +
        "vez do nome completo do token.",
    );
  }
  comentarios += 1;
  posicao = fecha + 3;
}

// --- 2. Tem a forma de um ícone, e não puxa nada de fora.
if (!/^<svg\b[^>]*\bviewBox="0 0 \d+ \d+"/m.test(svg)) {
  problemas.push("a raiz tem de ser um `<svg>` com `viewBox`: sem ela não escala.");
}
for (const fora of ["<image", "<use", "href=", "url(", "@import", "<script"]) {
  if (svg.includes(fora)) {
    problemas.push(
      `o ícone referencia algo de fora (\`${fora}\`). Um favicon é rasterizado sem ` +
        "rede e sem o CSS da aplicação: isso não falha, desenha menos em silêncio.",
    );
  }
}

// --- 3. As cores são os tokens da paleta escura.
//
// A paleta escura é a que o `@theme static` declara — é o default do produto
// (ADR 0015), e é a do azulejo do ícone. As outras duas vivem em blocos
// `:root[data-tema=…]` e não interessam aqui: um favicon não tem tema.
const css = readFileSync(TOKENS_CSS, "utf8");
const inicio = css.indexOf("@theme static {");
const fim = css.indexOf(':root[data-tema="claro"]');
if (inicio === -1 || fim === -1 || fim < inicio) {
  problemas.push(
    `não encontrei a paleta escura no ${TOKENS_CSS}. Se a forma do ficheiro mudou, ` +
      "este gate deixou de medir o que diz medir — arranja-o em vez de o apagar.",
  );
} else {
  const escura = css.slice(inicio, fim);
  const valorDoToken = new Map(
    [...escura.matchAll(/--([\w-]+):\s*([^;]+);/g)].map(([, nome, valor]) => [
      nome,
      valor.trim(),
    ]),
  );

  const declarados = [...svg.matchAll(/data-token="([\w-]+)"[^>]*?fill="([^"]+)"/g)];
  if (declarados.length === 0) {
    problemas.push(
      "nenhum elemento declara `data-token`. Cada forma do ícone diz de que token " +
        "copiou a cor, e é isso que este gate compara — sem o atributo, teria de " +
        "adivinhar pela ordem dos elementos.",
    );
  }
  for (const [, token, usada] of declarados) {
    const esperada = valorDoToken.get(token);
    if (esperada === undefined) {
      problemas.push(`\`${token}\` não existe na paleta escura do \`tokens.css\`.`);
    } else if (esperada !== usada) {
      problemas.push(
        `o ícone usa \`${usada}\` onde o token \`${token}\` vale \`${esperada}\`. ` +
          "A cópia divergiu: um ícone com a cor antiga do produto é a coisa que " +
          "ninguém nota e todos vêem.",
      );
    }
  }
}

if (problemas.length > 0) {
  console.error(`check-marca: ${problemas.length} problema(s).\n`);
  for (const p of problemas) console.error(`  ${p}`);
  console.error(
    "\nO ícone do separador é a única peça da identidade que vive fora do `src/` e " +
      "fora do alcance do compilador. Ver o comentário do `public/favicon.svg`.",
  );
  process.exit(1);
}

console.log(
  `check-marca: o favicon abre, tem ${String(comentarios)} comentário(s) legal(is), ` +
    "e as cores são os tokens da paleta escura.",
);
