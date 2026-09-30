#!/usr/bin/env node
/**
 * Guarda do sistema visual. Corre no `pnpm lint`, depois do ESLint.
 *
 * Porque existe, quando já há regras no ESLint: o ESLint não lê CSS, e é no
 * CSS que as cores vivem. Isto cobre os dois — e verifica invariantes que
 * nenhum linter conhece:
 *
 *  - **todos os tokens de cor redefinidos no modo escuro**. Um token esquecido
 *    no `@media (prefers-color-scheme: dark)` não dá erro nenhum em runtime; dá
 *    texto cinzento-claro sobre fundo branco a quem usa o telemóvel no modo
 *    escuro, e ninguém repara até um cliente reparar;
 *  - **contraste WCAG AA medido** contra a pior superfície, e **gamut sRGB**,
 *    que eram as duas afirmações do DESIGN.md §2 sem mecanismo nenhum a
 *    sustentá-las. Não é hipótese: dois tokens de `warning` estiveram fora do
 *    gamut a `-0.0011` e `-0.0015` no canal azul, escondidos por uma tolerância
 *    de `0.002` escrita por quem media. Foram apanhados por um agente a ler o
 *    ficheiro, o que não é um gate — se ninguém olhar, ninguém vê;
 *  - **o §2 do DESIGN.md igual ao `tokens.css`**. O documento diz que a fonte
 *    da verdade é o CSS e escreve a paleta inteira por baixo; se divergirem, o
 *    agente de UI lê a paleta errada antes de trabalhar.
 *
 * Um `oklch()` fora do gamut é distorcido pelo browser em silêncio, e a partir
 * daí o contraste que se mede não é o contraste que se vê. É por isso que o
 * gamut é verificado antes do contraste, e com tolerância de 1e-6.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const TOKENS_CSS = join(RAIZ, "src/styles/tokens.css");
const FONTS_CSS = join(RAIZ, "src/styles/fonts.css");
const DESIGN_MD = resolve(RAIZ, "../DESIGN.md");

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

/**
 * oklch() para sRGB linear. OKLab -> LMS -> linear sRGB (Björn Ottosson).
 *
 * Fica aqui e não numa dependência de propósito: são doze coeficientes, e uma
 * biblioteca de cor a mais no `package.json` é uma superfície de supply chain
 * para o que cabe em quinze linhas.
 */
function paraSrgbLinear(L, C, h) {
  const rad = (h * Math.PI) / 180;
  const a = C * Math.cos(rad);
  const b = C * Math.sin(rad);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

/** Luminância relativa da WCAG. O sRGB linear já é o que a fórmula pede. */
function luminancia(tinta) {
  const [r, g, b] = paraSrgbLinear(...tinta).map((v) => Math.min(1, Math.max(0, v)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contraste(tinta, fundo) {
  const [claro, escuro] = [luminancia(tinta), luminancia(fundo)].sort((x, y) => y - x);
  return (claro + 0.05) / (escuro + 0.05);
}

function tintasDe(fonte) {
  const encontradas = new Map();
  const padrao = /--color-([a-z0-9-]+)\s*:\s*oklch\(\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\)/g;
  let encontro = padrao.exec(fonte);
  while (encontro !== null) {
    encontradas.set(encontro[1], [Number(encontro[2]), Number(encontro[3]), Number(encontro[4])]);
    encontro = padrao.exec(fonte);
  }
  return encontradas;
}

/** Fundos, que não são tinta. E a borda decorativa, isenta dos 3:1 por decisão. */
const SUPERFICIES = new Set(["background", "surface", "surface-2"]);
const BORDA_DECORATIVA = "border";

/**
 * Gamut e contraste de um modo (claro ou escuro).
 *
 * Os papéis vêm do **nome** do token e não de uma lista fixa, e isso é o que
 * faz disto um gate em vez de um retrato: um `--color-info` novo entra sozinho
 * como texto, o `--color-info-surface` como preenchimento e o
 * `--color-info-border` como fronteira, sem ninguém se lembrar de os inscrever.
 */
function verificarModoDeCor(modo, tintas) {
  for (const [token, tinta] of tintas) {
    const canais = paraSrgbLinear(...tinta);
    if (canais.some((v) => v < -1e-6 || v > 1 + 1e-6)) {
      const fora = canais.map((v) => v.toFixed(6)).join(", ");
      relatar(TOKENS_CSS, 1, `${modo}: --color-${token} fora do gamut sRGB (${fora})`);
    }
  }

  // A pior das três superfícies é o `surface-2` nos dois modos, e é contra ela
  // que o DESIGN.md §2 exige a medição — não contra o `background`.
  const pior = tintas.get("surface-2");
  if (!pior) {
    relatar(TOKENS_CSS, 1, `${modo}: falta --color-surface-2, sem ele não há contra o que medir`);
    return;
  }

  for (const [token, tinta] of tintas) {
    if (SUPERFICIES.has(token) || token === BORDA_DECORATIVA) continue;

    // Preenchimento suave: a tinta não é para ler, o que se lê é o foreground
    // por cima dela.
    if (token.endsWith("-surface")) {
      const frente = tintas.get("foreground");
      if (!frente) continue;
      const razao = contraste(frente, tinta);
      if (razao < 4.5) {
        relatar(
          TOKENS_CSS,
          1,
          `${modo}: --color-foreground sobre --color-${token} dá ${razao.toFixed(3)}:1, mínimo 4.5`,
        );
      }
      continue;
    }

    // `border-strong` **e** `<estado>-border` são o mesmo papel. Tinha escrito
    // só o sufixo e o `border-strong` caiu na regra de texto a 4.5 — o gate
    // acusou-se a si mesmo na primeira corrida, que é a razão de se correr
    // antes de se publicar.
    const ehFronteira = token.startsWith("border") || token.endsWith("-border");
    const alvo = token === "primary-foreground" ? tintas.get("primary") : pior;
    if (!alvo) continue;
    const minimo = ehFronteira ? 3 : 4.5;
    const papel = ehFronteira
      ? "fronteira de componente sobre surface-2"
      : token === "primary-foreground"
        ? "sobre --color-primary"
        : "texto sobre surface-2";
    const razao = contraste(tinta, alvo);
    if (razao < minimo) {
      relatar(TOKENS_CSS, 1, `${modo}: --color-${token} dá ${razao.toFixed(3)}:1 como ${papel}, mínimo ${minimo}`);
    }
  }
}

/** Gamut, contraste e o §2 do DESIGN.md contra o `tokens.css`. */
function verificarCorEMedidas() {
  const css = readFileSync(TOKENS_CSS, "utf8");
  const corte = css.indexOf("@media (prefers-color-scheme: dark)");
  const claro = tintasDe(corte === -1 ? css : css.slice(0, corte));
  const escuro = corte === -1 ? new Map() : tintasDe(css.slice(corte));
  verificarModoDeCor("claro", claro);
  if (escuro.size > 0) verificarModoDeCor("escuro", escuro);

  const md = readFileSync(DESIGN_MD, "utf8");
  const corteMd = md.indexOf("@media (prefers-color-scheme: dark)");
  const pares = [
    ["claro", claro, tintasDe(corteMd === -1 ? md : md.slice(0, corteMd))],
    ["escuro", escuro, corteMd === -1 ? new Map() : tintasDe(md.slice(corteMd))],
  ];
  for (const [modo, doCss, doMd] of pares) {
    for (const [token, tinta] of doCss) {
      const documentado = doMd.get(token);
      if (!documentado) {
        relatar(DESIGN_MD, 1, `${modo}: --color-${token} está no tokens.css e não no §2`);
      } else if (documentado.join() !== tinta.join()) {
        relatar(
          DESIGN_MD,
          1,
          `${modo}: --color-${token} é oklch(${documentado.join(" ")}) no §2 e oklch(${tinta.join(" ")}) no tokens.css`,
        );
      }
    }
    for (const token of doMd.keys()) {
      if (!doCss.has(token)) {
        relatar(DESIGN_MD, 1, `${modo}: --color-${token} está no §2 e não no tokens.css`);
      }
    }
  }

  console.log(
    `check-design: ${claro.size + escuro.size} tintas oklch no gamut sRGB, contraste medido, §2 em dia.`,
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
verificarCorEMedidas();
verificarFontes();

if (problemas.length > 0) {
  console.error(`\ncheck-design: ${problemas.length} problema(s).\n`);
  for (const problema of problemas) console.error(`  ${problema}`);
  process.exit(1);
}

console.log("check-design: sem problemas.");
