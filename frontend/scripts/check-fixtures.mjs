#!/usr/bin/env node
/**
 * Guarda da fronteira dos dados falsos. Corre no `pnpm lint`, ao lado do
 * `check-design-tokens.mjs`.
 *
 * A decisão 3 do ADR 0008 tem três peças, e **a primeira não é um gate — é uma
 * impossibilidade**: o `apply: "serve"` é do Vite e não nosso, o plugin não
 * participa em `vite build`, e porque nada em `src/` importa `fixtures/` os
 * dados falsos não estão no grafo de módulos da app. Este ficheiro é a segunda
 * peça: verifica que as condições dessa impossibilidade continuam a valer.
 *
 * As três coisas que mede, e o que cada uma impede:
 *  1. **nenhum ficheiro de `src/` importa de `fixtures/`** — é esta aresta que,
 *     se existisse, punha a mentira dentro do bundle e trocava uma
 *     impossibilidade por uma deteção;
 *  2. **o plugin está registado no `vite.config.ts` e tem `apply: "serve"`** —
 *     sem o `apply`, o mesmo middleware passaria a correr no `vite build`;
 *  3. **todo o ficheiro de `fixtures/` carrega a sentinela `dados-falsos-…`** —
 *     e o job `frontend` do CI exige que essa sentinela dê zero ocorrências em
 *     `dist/`. As duas falham em sentidos opostos: uma garante que toda a
 *     mentira é reconhecível, a outra que nenhuma chega ao artefacto. Se alguém
 *     ligar um fixture à app, a sentinela viaja com ele e o CI fica vermelho.
 *
 * A quarta é de outra natureza e está aqui por economia: `fixtures` tem de
 * estar no `include` do `tsconfig.json`, senão o ESLint com `projectService`
 * **crasha** nesses ficheiros (exit 2) e eles deixam de ser tipados, que é o
 * que os torna úteis como rascunho do contrato (ADR 0008, consequências).
 *
 * E falha nos dois sentidos: no dia em que `fixtures/` não existir, exige que o
 * `vite.config.ts` já não fale dela. A decisão 3 termina por apagamento.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const FIXTURES = join(RAIZ, "fixtures");
const SRC = join(RAIZ, "src");
const VITE_CONFIG = join(RAIZ, "vite.config.ts");
const TSCONFIG = join(RAIZ, "tsconfig.json");

/** A marca que torna a mentira reconhecível em qualquer varredura. */
const SENTINELA = "dados-falsos-stockflow";

const problemas = [];

function relatar(ficheiro, linha, mensagem) {
  problemas.push(`${relative(RAIZ, ficheiro)}:${linha} - ${mensagem}`);
}

/** Apaga comentários mantendo o número de linhas (igual ao check-design). */
function semComentarios(fonte) {
  return fonte
    .replace(/\/\*[\s\S]*?\*\//g, (bloco) => bloco.replace(/[^\n]/g, " "))
    .replace(
      /(^|[\s{;(])\/\/[^\n]*/g,
      (linha, prefixo) => prefixo + " ".repeat(linha.length - prefixo.length),
    );
}

function ficheirosDe(diretorio, extensoes) {
  if (!existsSync(diretorio)) return [];
  const encontrados = [];
  for (const entrada of readdirSync(diretorio)) {
    if (entrada === "node_modules" || entrada === "dist") continue;
    const caminho = join(diretorio, entrada);
    if (statSync(caminho).isDirectory()) {
      encontrados.push(...ficheirosDe(caminho, extensoes));
    } else if (extensoes.includes(extname(caminho))) {
      encontrados.push(caminho);
    }
  }
  return encontrados;
}

/**
 * Os especificadores de import de uma linha. Cobre `from "..."`, `import("...")`,
 * `import "..."` e `require("...")` — as quatro formas com que uma aresta de
 * módulo se escreve.
 */
function especificadoresDe(linha) {
  const padroes = [
    /\bfrom\s*["']([^"']+)["']/g,
    /\bimport\s*\(\s*["']([^"']+)["']/g,
    /\bimport\s+["']([^"']+)["']/g,
    /\brequire\s*\(\s*["']([^"']+)["']/g,
  ];
  const encontrados = [];
  for (const padrao of padroes) {
    let encontro = padrao.exec(linha);
    while (encontro !== null) {
      encontrados.push(encontro[1]);
      encontro = padrao.exec(linha);
    }
  }
  return encontrados;
}

/** (1) Nada em `src/` toca em `fixtures/`. */
function verificarQueSrcNaoImportaFixtures() {
  const antes = problemas.length;
  let arestas = 0;
  for (const ficheiro of ficheirosDe(SRC, [".ts", ".tsx", ".css"])) {
    const linhas = semComentarios(readFileSync(ficheiro, "utf8")).split("\n");
    linhas.forEach((linha, indice) => {
      for (const especificador of especificadoresDe(linha)) {
        arestas += 1;
        if (/(^|[/\\])fixtures([/\\]|$)/.test(especificador)) {
          relatar(
            ficheiro,
            indice + 1,
            `importa "${especificador}" — nada em src/ pode importar de fixtures/ (ADR 0008, decisão 3): ` +
              "é essa aresta que põe os dados falsos no grafo de módulos e no bundle",
          );
          continue;
        }
        // O mesmo, generalizado: um import relativo que saia de `src/` é a
        // mesma aresta com outro nome, e sobrevive a renomear a pasta.
        if (especificador.startsWith(".")) {
          const alvo = resolve(dirname(ficheiro), especificador);
          if (!alvo.startsWith(SRC)) {
            relatar(
              ficheiro,
              indice + 1,
              `importa "${especificador}", que sai de src/ — o grafo de módulos da app começa e acaba em src/`,
            );
          }
        }
      }
      // Um `@import` de CSS é uma aresta como as outras.
      if (/@import\s+["'][^"']*fixtures/.test(linha)) {
        relatar(ficheiro, indice + 1, "@import de fixtures/ em CSS (ADR 0008, decisão 3)");
      }
    });
  }
  // A linha tranquilizadora só se imprime se for verdade: um "nenhum para
  // fixtures/" seguido de um problema é como um gate perde a credibilidade.
  if (problemas.length === antes) {
    console.log(`check-fixtures: ${arestas} imports em src/, nenhum para fixtures/.`);
  }
}

/**
 * O conteúdo do array `plugins` do `vite.config.ts`, com os parênteses rectos
 * equilibrados. Um `RegExp` construído em runtime seria mais curto e o
 * `security/detect-non-literal-regexp` recusa-o — e a casa não suprime lint.
 */
function arrayDePlugins(configuracao) {
  const chave = configuracao.indexOf("plugins");
  if (chave === -1) return "";
  const abre = configuracao.indexOf("[", chave);
  if (abre === -1) return "";
  let profundidade = 0;
  for (let i = abre; i < configuracao.length; i += 1) {
    const caracter = configuracao[i];
    if (caracter === "[") profundidade += 1;
    if (caracter === "]") {
      profundidade -= 1;
      if (profundidade === 0) return configuracao.slice(abre + 1, i);
    }
  }
  return "";
}

/** (2) O plugin está registado e tem `apply: "serve"`. */
function verificarOPlugin({ comFixtures }) {
  const antes = problemas.length;
  const configuracao = semComentarios(readFileSync(VITE_CONFIG, "utf8"));
  const importacao =
    /import\s*\{\s*([A-Za-z0-9_$]+)[^}]*\}\s*from\s*["'](\.\/fixtures\/[^"']+)["']/.exec(
      configuracao,
    );

  if (!comFixtures) {
    if (importacao !== null) {
      relatar(
        VITE_CONFIG,
        1,
        `importa "${importacao[2]}" e a pasta fixtures/ já não existe — ` +
          "quando o último fixture sai, sai também esta linha (ADR 0008)",
      );
    } else {
      console.log("check-fixtures: sem fixtures/ e sem plugin — a decisão 3 terminou por apagamento.");
    }
    return;
  }

  if (importacao === null) {
    relatar(
      VITE_CONFIG,
      1,
      "não importa o plugin de fixtures de ./fixtures/* — sem ele os caminhos que o Django " +
        "ainda não tem não são servidos por ninguém",
    );
    return;
  }

  const [, identificador, especificador] = importacao;

  if (!arrayDePlugins(configuracao).includes(`${identificador}(`)) {
    relatar(
      VITE_CONFIG,
      1,
      `importa ${identificador} e não o registou no array \`plugins\` — um plugin importado e não usado não serve nada`,
    );
  }

  const modulo = ["", ".ts", ".mts", "/index.ts"]
    .map((sufixo) => join(RAIZ, `${especificador}${sufixo}`))
    .find((caminho) => existsSync(caminho) && statSync(caminho).isFile());

  if (modulo === undefined) {
    relatar(VITE_CONFIG, 1, `o plugin importado de "${especificador}" não existe no disco`);
    return;
  }

  if (!/\bapply\s*:\s*["']serve["']/.test(semComentarios(readFileSync(modulo, "utf8")))) {
    relatar(
      modulo,
      1,
      'não declara `apply: "serve"` — sem isso o middleware de dados falsos passa a participar ' +
        "em `vite build`, e a impossibilidade da decisão 3 do ADR 0008 vira uma promessa",
    );
    return;
  }

  if (problemas.length === antes) {
    console.log(`check-fixtures: ${identificador} registado no vite.config.ts com apply: "serve".`);
  }
}

/** (3) Toda a mentira carrega a sentinela. */
function verificarASentinela() {
  const antes = problemas.length;
  const ficheiros = ficheirosDe(FIXTURES, [".ts", ".tsx", ".mts", ".json"]);
  if (ficheiros.length === 0) return;
  for (const ficheiro of ficheiros) {
    if (!readFileSync(ficheiro, "utf8").includes(SENTINELA)) {
      relatar(
        ficheiro,
        1,
        `não contém a sentinela "${SENTINELA}" — é ela que torna a mentira reconhecível ` +
          "na varredura do dist/ que o CI faz (ADR 0008, decisão 3)",
      );
    }
  }
  if (problemas.length === antes) {
    console.log(
      `check-fixtures: ${ficheiros.length} ficheiro(s) de fixtures, todos com a sentinela.`,
    );
  }
}

/** (4) `fixtures` no `include` do tsconfig, senão o ESLint crasha (exit 2). */
function verificarOTsconfig({ comFixtures }) {
  const bruto = readFileSync(TSCONFIG, "utf8");
  const include = /"include"\s*:\s*\[([^\]]*)\]/.exec(semComentarios(bruto));
  if (include === null) {
    relatar(TSCONFIG, 1, 'sem campo "include" — não há como saber o que é tipado');
    return;
  }
  const temFixtures = /["']fixtures["']/.test(include[1]);
  if (comFixtures && !temFixtures) {
    relatar(
      TSCONFIG,
      1,
      '"fixtures" não está no include — o ESLint com projectService crasha (exit 2) nesses ' +
        "ficheiros e eles deixam de ser tipados (ADR 0008, consequências)",
    );
  }
  if (!comFixtures && temFixtures) {
    relatar(TSCONFIG, 1, '"fixtures" está no include e a pasta já não existe');
  }
}

const comFixtures = existsSync(FIXTURES);

verificarQueSrcNaoImportaFixtures();
verificarOPlugin({ comFixtures });
verificarASentinela();
verificarOTsconfig({ comFixtures });

if (problemas.length > 0) {
  console.error(`\ncheck-fixtures: ${problemas.length} problema(s).\n`);
  for (const problema of problemas) console.error(`  ${problema}`);
  process.exit(1);
}

console.log("check-fixtures: sem problemas.");
