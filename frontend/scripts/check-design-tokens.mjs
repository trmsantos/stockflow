#!/usr/bin/env node
/**
 * Guarda do sistema visual. Corre no `pnpm lint`, depois do ESLint.
 *
 * Porque existe, quando já há regras no ESLint: o ESLint não lê CSS, e é no
 * CSS que as cores vivem. Isto cobre os dois — e verifica um invariante que
 * nenhum linter conhece: **todos os tokens de cor redefinidos no modo
 * escuro**. Um token esquecido no `@media (prefers-color-scheme: dark)` não dá
 * erro nenhum em runtime; dá texto cinzento-claro sobre fundo branco a quem
 * usa o telemóvel no modo escuro, e ninguém repara até um cliente reparar.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const TOKENS_CSS = join(RAIZ, "src/styles/tokens.css");
const FONTS_CSS = join(RAIZ, "src/styles/fonts.css");

/** Ficheiros gerados pelo CLI do shadcn: não se editam à mão (DESIGN.md §3). */
const GERADOS = ["src/components/ui/", "src/lib/api/types.ts"];

const problemas = [];

/**
 * Apaga comentários, mantendo o número de linhas.
 *
 * Sem isto o próprio comentário que explica uma proibição ("Inter e Roboto são
 * proibidos") é apanhado como violação, e a saída do linter deixa de merecer
 * atenção. Comentários não vão para o ecrã; o que interessa é o código.
 */
function semComentarios(fonte) {
  return fonte
    .replace(/\/\*[\s\S]*?\*\//g, (bloco) => bloco.replace(/[^\n]/g, " "))
    .replace(/(^|[\s{;(])\/\/[^\n]*/g, (linha, prefixo) => prefixo + " ".repeat(linha.length - prefixo.length));
}

function relatar(ficheiro, linha, mensagem) {
  problemas.push(`${relative(RAIZ, ficheiro)}:${linha} - ${mensagem}`);
}

function ficheirosDe(diretorio, extensoes) {
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

const REGRAS = [
  {
    nome: "cor literal",
    padrao: /#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-zA-Z])/,
    mensagem: "cor literal em hex — só tokens do DESIGN.md §2",
    aplicaAGerados: true,
  },
  {
    nome: "cor rgb/hsl",
    padrao: /\b(?:rgba?|hsla?)\(/,
    mensagem: "cor em rgb()/hsl() — a paleta é oklch() em src/styles/tokens.css",
    aplicaAGerados: false,
  },
  {
    nome: "valor arbitrário de cor",
    padrao:
      /\b(?:bg|text|border|ring|outline|fill|stroke|shadow|divide|decoration|accent|caret|from|via|to)-\[/,
    mensagem: "valor arbitrário (bg-[...]) — proibido pelo DESIGN.md §6",
    aplicaAGerados: false,
  },
  {
    nome: "fonte proibida",
    padrao: /\b(?:Inter|Roboto|Poppins|Open Sans|Geist|Figtree)\b/,
    mensagem: "fonte proibida — o projeto é IBM Plex Sans / IBM Plex Mono (DESIGN.md §2)",
    aplicaAGerados: true,
  },
  {
    nome: "glassmorphism",
    padrao: /backdrop-(?:blur|filter)|backdrop-filter/,
    mensagem: "blur de fundo / glassmorphism — anti-padrão (DESIGN.md §5)",
    aplicaAGerados: false,
  },
  {
    nome: "raio fora da escala",
    padrao: /\brounded-(?:2xl|3xl|4xl)\b/,
    mensagem: "raio fora da escala (4 · 6 · 10px) — DESIGN.md §5 proíbe rounded-2xl em tudo",
    aplicaAGerados: false,
  },
  {
    nome: "emoji como ícone",
    padrao: /\p{Extended_Pictographic}/u,
    mensagem: "emoji — os ícones são da Lucide (DESIGN.md §5)",
    aplicaAGerados: false,
  },
  {
    nome: "recurso externo",
    padrao: /url\(\s*["']?https?:/,
    mensagem:
      "recurso externo em CSS — a CSP de produção é 'self' (SECURITY.md §2); as fontes vêm do bundle",
    aplicaAGerados: true,
  },
];

function verificarFicheiros() {
  const ficheiros = [
    ...ficheirosDe(join(RAIZ, "src"), [".ts", ".tsx", ".css"]),
    join(RAIZ, "index.html"),
  ];

  for (const ficheiro of ficheiros) {
    const relativo = relative(RAIZ, ficheiro);
    const gerado = GERADOS.some((prefixo) => relativo.startsWith(prefixo));
    const linhas = semComentarios(readFileSync(ficheiro, "utf8")).split("\n");

    linhas.forEach((linha, indice) => {
      for (const regra of REGRAS) {
        if (gerado && !regra.aplicaAGerados) continue;
        if (regra.padrao.test(linha)) {
          relatar(ficheiro, indice + 1, `${regra.mensagem} (${regra.nome})`);
        }
      }
    });
  }
}

/**
 * Todos os tokens de cor com valor literal têm de estar redefinidos no bloco
 * de modo escuro. As pontes para o shadcn (valor `var(--...)`) seguem o token
 * a que apontam e não se repetem.
 */
function verificarModoEscuro() {
  const css = readFileSync(TOKENS_CSS, "utf8");

  const inicioEscuro = css.indexOf("@media (prefers-color-scheme: dark)");
  if (inicioEscuro === -1) {
    problemas.push(
      `${relative(RAIZ, TOKENS_CSS)}:1 - falta o bloco @media (prefers-color-scheme: dark)`,
    );
    return;
  }

  const claro = css.slice(0, inicioEscuro);
  const escuro = css.slice(inicioEscuro);

  const declaracoes = (fonte) => {
    const encontradas = new Map();
    const padrao = /--color-([a-z0-9-]+)\s*:\s*([^;]+);/g;
    let encontro = padrao.exec(fonte);
    while (encontro !== null) {
      encontradas.set(encontro[1], encontro[2].trim());
      encontro = padrao.exec(fonte);
    }
    return encontradas;
  };

  const tokensClaros = declaracoes(claro);
  const tokensEscuros = declaracoes(escuro);

  const literais = [...tokensClaros.entries()]
    .filter(([nome, valor]) => !valor.startsWith("var(") && nome !== "*")
    .map(([nome]) => nome);

  const faltam = literais.filter((nome) => !tokensEscuros.has(nome));
  if (faltam.length > 0) {
    problemas.push(
      `${relative(RAIZ, TOKENS_CSS)}:1 - modo escuro incompleto, faltam ${faltam.length} token(s): ${faltam.join(", ")}`,
    );
  }

  const aMais = [...tokensEscuros.keys()].filter((nome) => !tokensClaros.has(nome));
  if (aMais.length > 0) {
    problemas.push(
      `${relative(RAIZ, TOKENS_CSS)}:1 - token(s) só no modo escuro: ${aMais.join(", ")}`,
    );
  }

  console.log(
    `check-design: ${literais.length} tokens de cor, ${tokensEscuros.size} redefinidos no modo escuro.`,
  );
}

/** Cada @font-face tem de ter `font-display: swap` e vir do bundle. */
function verificarFontes() {
  const css = readFileSync(FONTS_CSS, "utf8");
  const blocos = css.split("@font-face").slice(1);
  blocos.forEach((bloco, indice) => {
    if (!bloco.includes("font-display: swap")) {
      relatar(FONTS_CSS, 1, `@font-face #${indice + 1} sem font-display: swap`);
    }
  });
  console.log(`check-design: ${blocos.length} @font-face locais.`);
}

verificarFicheiros();
verificarModoEscuro();
verificarFontes();

if (problemas.length > 0) {
  console.error(`\ncheck-design: ${problemas.length} problema(s).\n`);
  for (const problema of problemas) console.error(`  ${problema}`);
  process.exit(1);
}

console.log("check-design: sem problemas.");
