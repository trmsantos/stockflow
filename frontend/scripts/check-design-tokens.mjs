#!/usr/bin/env node
/**
 * Guarda do sistema visual. Corre no `pnpm lint`, depois do ESLint.
 *
 * Porque existe, quando já há regras no ESLint: o ESLint não lê CSS, e é no
 * CSS que as cores vivem. Isto cobre os dois — e verifica invariantes que
 * nenhum linter conhece:
 *
 *  - **a paleta em vigor completa, e nenhuma paleta a meio**. Ver
 *    `verificarPaletaUnica`: é aqui que este gate mudou de alvo a 2026-10-01, e
 *    a razão está escrita lá porque daqui a três meses parece a mesma coisa;
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

/**
 * `--detalhe` imprime a tabela token a token (gamut e contraste medidos) em vez
 * do resumo. O default é o resumo porque isto corre a cada `pnpm lint`; a
 * tabela existe para quando alguém mexe na paleta e tem de **reportar números
 * medidos** em vez de os presumir.
 */
const DETALHE = process.argv.includes("--detalhe");

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
    mensagem: "fonte proibida — o projeto é Archivo / IBM Plex Mono (DESIGN.md §2)",
    aplicaAGerados: true,
  },
  {
    // O `dark:` dos primitivos do shadcn está neutralizado no `tokens.css`
    // (`@custom-variant dark (&:where(:not(*)))`), porque com uma paleta escura
    // única ele passaria a fazer o aspecto depender da configuração do sistema
    // de quem olha. Nos ficheiros gerados fica inerte e não se editam à mão;
    // escrever um `dark:` novo em código nosso seria escrever uma regra que não
    // corre — e o dia em que o modo claro entrar, entra com o seu próprio
    // mecanismo e este diff é o sítio onde isso se decide.
    nome: "variant dark inerte",
    padrao: /\bdark:[a-z[]/,
    mensagem:
      "`dark:` não seleciona nada: há uma paleta só (DESIGN.md §2). Usa o token, não o variant",
    aplicaAGerados: false,
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
    mensagem: "raio fora da escala (4 · 6 · 8 · 12px) — DESIGN.md §5 proíbe rounded-2xl em tudo",
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
 * Declarações `--color-<nome>: <valor>` de um pedaço de CSS, na ordem em que
 * aparecem. As pontes para o shadcn (valor `var(--...)`) seguem o token a que
 * apontam e por isso são separadas das literais mais abaixo.
 */
function declaracoesDeCor(fonte) {
  const encontradas = new Map();
  const padrao = /--color-([a-z0-9-]+)\s*:\s*([^;]+);/g;
  let encontro = padrao.exec(fonte);
  while (encontro !== null) {
    encontradas.set(encontro[1], encontro[2].trim());
    encontro = padrao.exec(fonte);
  }
  return encontradas;
}

function literaisDe(declaracoes) {
  return new Map([...declaracoes].filter(([, valor]) => !valor.startsWith("var(")));
}

/**
 * Os blocos `@media` de um CSS, com o corpo delimitado por contagem de chaves
 * (um `@media` pode conter regras com chaves, logo um `indexOf("}")` não
 * serve). Corre sobre o CSS já sem comentários, senão um `@media` dentro de um
 * comentário — como o que explica esta função — contava como bloco.
 */
function blocosDeMedia(limpo) {
  const blocos = [];
  const padrao = /@media([^{]*)\{/g;
  let encontro = padrao.exec(limpo);
  while (encontro !== null) {
    const abre = padrao.lastIndex - 1;
    let profundidade = 0;
    let fecha = limpo.length;
    for (let i = abre; i < limpo.length; i += 1) {
      if (limpo[i] === "{") profundidade += 1;
      else if (limpo[i] === "}") {
        profundidade -= 1;
        if (profundidade === 0) {
          fecha = i;
          break;
        }
      }
    }
    blocos.push({
      condicao: encontro[1].trim(),
      corpo: limpo.slice(abre + 1, fecha),
      inicio: encontro.index,
      fim: fecha + 1,
    });
    padrao.lastIndex = fecha + 1;
    encontro = padrao.exec(limpo);
  }
  return blocos;
}

/**
 * Separa uma fonte na **paleta em vigor** (tudo o que está fora de `@media`) e
 * nas paletas alternativas (um bloco `prefers-color-scheme` cada).
 */
function paletasDe(fonte) {
  const limpo = semComentarios(fonte);
  const medias = blocosDeMedia(limpo);
  let base = limpo;
  for (const bloco of [...medias].reverse()) {
    base = base.slice(0, bloco.inicio) + base.slice(bloco.fim);
  }
  return {
    base: declaracoesDeCor(base),
    alternativas: medias
      .filter((bloco) => bloco.condicao.includes("prefers-color-scheme"))
      .map((bloco) => ({ condicao: bloco.condicao, cores: declaracoesDeCor(bloco.corpo) })),
  };
}

/** Os nove tokens de estrutura. Sem um deles a paleta não se consegue medir. */
const ESTRUTURAIS = [
  "background",
  "surface",
  "surface-2",
  "border",
  "border-strong",
  "foreground",
  "muted-foreground",
  "primary",
  "primary-foreground",
];

/** Os três papéis de uma cor de estado (DESIGN.md §2). */
const PAPEIS = ["", "-surface", "-border"];

/**
 * A paleta — uma só, completa, e nenhuma paleta a meio. **É aqui que este gate
 * mudou de alvo, e a razão fica escrita porque daqui a três meses parece a
 * mesma coisa.**
 *
 * Até 2026-10-01 o que se exigia era **paridade entre dois modos**: 18 tokens
 * na paleta clara e os mesmos 18 redefinidos no `@media
 * (prefers-color-scheme: dark)`, a falhar nos dois sentidos. A identidade
 * escolhida ("Cabine") é escura e a decisão do dono do produto é "escuro
 * primário, claro depois": com um modo só, essa paridade passou a ser uma
 * afirmação sobre um conjunto vazio — passava sempre e deixava de proteger o
 * que protegia.
 *
 * **Relaxar um gate é afirmar menos sobre a mesma coisa; mudar o que ele
 * afirma, porque a coisa mudou, é outra.** O alvo novo é mais forte no caso que
 * de facto vai acontecer, que é alguém começar o modo claro e deixá-lo a meio:
 *
 *  1. a paleta em vigor tem de estar **completa** — os nove tokens de estrutura
 *     e os **três papéis** de cada cor de estado. A checklist do DESIGN.md §6
 *     prometia isto e nada o media;
 *  2. todo o token literal tem de ser um `oklch(L C h)` legível, senão entrava
 *     na paleta sem ser medido;
 *  3. qualquer bloco `prefers-color-scheme` que apareça tem de redefinir a
 *     paleta **inteira** — e é medido com a mesma matemática (gamut e
 *     contraste, em `verificarCorEMedidas`). Um modo claro a meio não passa;
 *  4. a paleta vive só no `tokens.css`: um `prefers-color-scheme` noutro `.css`
 *     de `src/` é uma segunda fonte de verdade.
 *
 * O que **não** mudou: a paridade token a token entre o DESIGN.md §2 e este
 * ficheiro, que continua a falhar nos dois sentidos.
 */
function verificarPaletaUnica() {
  const { base, alternativas } = paletasDe(readFileSync(TOKENS_CSS, "utf8"));
  const literais = literaisDe(base);

  for (const nome of ESTRUTURAIS) {
    if (!literais.has(nome)) {
      relatar(TOKENS_CSS, 1, `a paleta não tem --color-${nome}, e sem ele não se mede`);
    }
  }

  for (const [nome, valor] of literais) {
    if (!/^oklch\(\s*[-\d.]+\s+[-\d.]+\s+[-\d.]+\s*\)$/.test(valor)) {
      relatar(
        TOKENS_CSS,
        1,
        `--color-${nome} é \`${valor}\` e não um oklch(L C h) — entrava na paleta sem ser medido`,
      );
    }
  }

  // As famílias de estado vêm do **nome**: tudo o que não é estrutura é uma cor
  // de estado, e uma cor de estado tem três papéis. Um `--color-info` novo
  // passa a exigir `-surface` e `-border` sozinho, sem ninguém o inscrever.
  const familias = new Set(
    [...literais.keys()]
      .filter((nome) => !ESTRUTURAIS.includes(nome))
      .map((nome) => nome.replace(/-(?:surface|border)$/, "")),
  );
  for (const familia of familias) {
    const faltam = PAPEIS.map((papel) => `${familia}${papel}`).filter(
      (nome) => !literais.has(nome),
    );
    if (faltam.length > 0) {
      relatar(
        TOKENS_CSS,
        1,
        `a cor de estado \`${familia}\` tem de ter os três papéis (DESIGN.md §2); falta ${faltam
          .map((nome) => `--color-${nome}`)
          .join(", ")}`,
      );
    }
  }

  for (const alternativa of alternativas) {
    const suas = literaisDe(alternativa.cores);
    const faltam = [...literais.keys()].filter((nome) => !suas.has(nome));
    const aMais = [...suas.keys()].filter((nome) => !literais.has(nome));
    if (faltam.length > 0 || aMais.length > 0) {
      relatar(
        TOKENS_CSS,
        1,
        `paleta parcial em \`@media ${alternativa.condicao}\`: ` +
          `${faltam.length} token(s) por redefinir${faltam.length > 0 ? ` (${faltam.join(", ")})` : ""}` +
          `${aMais.length > 0 ? ` e ${aMais.length} que não existem na paleta em vigor (${aMais.join(", ")})` : ""}.` +
          " Um segundo modo entra completo e medido, ou não entra",
      );
    }
  }

  for (const ficheiro of ficheirosDe(join(RAIZ, "src"), [".css"])) {
    if (ficheiro === TOKENS_CSS) continue;
    const linhas = semComentarios(readFileSync(ficheiro, "utf8")).split("\n");
    linhas.forEach((linha, indice) => {
      if (linha.includes("prefers-color-scheme")) {
        relatar(
          ficheiro,
          indice + 1,
          "paleta fora do tokens.css — `prefers-color-scheme` só lá, onde é medido",
        );
      }
    });
  }

  console.log(
    `check-design: paleta em vigor com ${literais.size} tokens de cor` +
      `${alternativas.length === 0 ? ", e nenhuma paleta alternativa" : `, mais ${alternativas.length} em \`@media prefers-color-scheme\``}.`,
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

/* As tintas saem das declarações (`tintasDasDeclaracoes`) e não de uma varredura
 * da fonte: é a mesma travessia que vê as paletas, logo um token num `@media`
 * não se confunde com um da paleta em vigor. */

/** Fundos, que não são tinta. E a borda decorativa, isenta dos 3:1 por decisão. */
const SUPERFICIES = new Set(["background", "surface", "surface-2"]);
const BORDA_DECORATIVA = "border";

/** As tintas `oklch(L C h)` de um mapa de declarações (as pontes ficam fora). */
function tintasDasDeclaracoes(declaracoes) {
  const tintas = new Map();
  for (const [nome, valor] of literaisDe(declaracoes)) {
    const encontro = /^oklch\(\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\)$/.exec(valor);
    if (encontro !== null) {
      tintas.set(nome, [Number(encontro[1]), Number(encontro[2]), Number(encontro[3])]);
    }
  }
  return tintas;
}

/**
 * O papel de um token, derivado do **nome** e não de uma lista fixa — é isso
 * que faz disto um gate em vez de um retrato: um `--color-info` novo entra
 * sozinho como texto, o `--color-info-surface` como preenchimento e o
 * `--color-info-border` como fronteira, sem ninguém se lembrar de os inscrever.
 *
 * `border-strong` **e** `<estado>-border` são o mesmo papel. Tinha escrito só o
 * sufixo e o `border-strong` caiu na regra de texto a 4.5 — o gate acusou-se a
 * si mesmo na primeira corrida, que é a razão de se correr antes de se publicar.
 */
function papelDe(nome) {
  // O parâmetro chama-se `nome` e não `token` de propósito: o
  // `security/detect-possible-timing-attacks` do ESLint acusa qualquer
  // `if (token === ...)` por heurística de nome, e o `--max-warnings 0` torna
  // isso fatal. Renomear é mais honesto do que desligar uma regra de segurança
  // numa pasta inteira para um falso positivo de vocabulário.
  if (SUPERFICIES.has(nome)) return { tipo: "superficie", minimo: 0 };
  if (nome === BORDA_DECORATIVA) return { tipo: "separador", minimo: 0 };
  if (nome.endsWith("-surface")) return { tipo: "tinta", minimo: 4.5 };
  if (nome.startsWith("border") || nome.endsWith("-border")) {
    return { tipo: "fronteira", minimo: 3 };
  }
  if (nome === "primary-foreground") return { tipo: "texto-sobre-primary", minimo: 4.5 };
  return { tipo: "texto", minimo: 4.5 };
}

/**
 * Gamut e contraste de uma paleta. Devolve as medições, para o resumo poder
 * imprimir os piores números e o `--detalhe` a tabela inteira: um gate que mede
 * e não diz o que mediu obriga quem reporta a presumir.
 */
function medirPaleta(etiqueta, tintas) {
  const medicoes = [];

  for (const [token, tinta] of tintas) {
    const canais = paraSrgbLinear(...tinta);
    const dentro = canais.every((v) => v >= -1e-6 && v <= 1 + 1e-6);
    if (!dentro) {
      const fora = canais.map((v) => v.toFixed(6)).join(", ");
      relatar(TOKENS_CSS, 1, `${etiqueta}: --color-${token} fora do gamut sRGB (${fora})`);
    }
    medicoes.push({ token, canais, dentro });
  }

  // A pior das três superfícies é o `surface-2` — o mais claro dos três pretos,
  // logo o pior fundo para texto claro — e é contra ela que o DESIGN.md §2
  // exige a medição, não contra o `background`.
  const pior = tintas.get("surface-2");
  if (!pior) {
    relatar(TOKENS_CSS, 1, `${etiqueta}: falta --color-surface-2, sem ele não há contra o que medir`);
    return medicoes;
  }
  const frente = tintas.get("foreground");

  for (const medicao of medicoes) {
    const { token } = medicao;
    const tinta = tintas.get(token);
    const papel = papelDe(token);

    if (papel.tipo === "superficie" || papel.tipo === "separador") {
      // Um separador decorativo entre superfícies está fora da regra dos 3:1,
      // que se aplica a fronteiras que identificam componentes. Mede-se para o
      // número aparecer, e não se julga.
      medicao.papel = papel.tipo;
      medicao.razao = contraste(tinta, pior);
      medicao.minimo = 0;
      continue;
    }

    // Preenchimento suave: a tinta não é para ler, o que se lê é o foreground
    // por cima dela.
    const frenteDaVez = papel.tipo === "tinta" ? frente : tinta;
    const fundoDaVez =
      papel.tipo === "tinta"
        ? tinta
        : papel.tipo === "texto-sobre-primary"
          ? tintas.get("primary")
          : pior;
    if (!frenteDaVez || !fundoDaVez) continue;

    const razao = contraste(frenteDaVez, fundoDaVez);
    medicao.papel = papel.tipo;
    medicao.razao = razao;
    medicao.minimo = papel.minimo;
    if (razao < papel.minimo) {
      const descricao = {
        tinta: `--color-foreground sobre --color-${token}`,
        fronteira: `--color-${token} como fronteira de componente sobre surface-2`,
        "texto-sobre-primary": `--color-${token} sobre --color-primary`,
        texto: `--color-${token} como texto sobre surface-2`,
      }[papel.tipo];
      relatar(
        TOKENS_CSS,
        1,
        `${etiqueta}: ${descricao} dá ${razao.toFixed(3)}:1, mínimo ${papel.minimo}`,
      );
    }
  }

  return medicoes;
}

function imprimirDetalhe(etiqueta, medicoes) {
  console.log(`\ncheck-design --detalhe · ${etiqueta}`);
  console.log(
    `  ${"token".padEnd(28)}${"papel".padEnd(22)}${"medido".padStart(9)}${"mínimo".padStart(9)}  gamut`,
  );
  for (const medicao of medicoes) {
    const razao = medicao.razao === undefined ? "—" : `${medicao.razao.toFixed(3)}:1`;
    const minimo = medicao.minimo ? `${medicao.minimo.toFixed(1)}:1` : "isento";
    console.log(
      `  --color-${medicao.token.padEnd(20)}${(medicao.papel ?? "—").padEnd(22)}` +
        `${razao.padStart(9)}${minimo.padStart(9)}  ${medicao.dentro ? "sRGB ok" : "FORA"}`,
    );
  }
}

/** Gamut, contraste e o §2 do DESIGN.md contra o `tokens.css`. */
function verificarCorEMedidas() {
  const doCss = paletasDe(readFileSync(TOKENS_CSS, "utf8"));
  const doMd = paletasDe(readFileSync(DESIGN_MD, "utf8"));

  const paletas = [
    { etiqueta: "paleta em vigor", cores: doCss.base },
    ...doCss.alternativas.map((alternativa) => ({
      etiqueta: `@media ${alternativa.condicao}`,
      cores: alternativa.cores,
    })),
  ];

  let tintasMedidas = 0;
  const piores = new Map();
  for (const paleta of paletas) {
    const tintas = tintasDasDeclaracoes(paleta.cores);
    tintasMedidas += tintas.size;
    const medicoes = medirPaleta(paleta.etiqueta, tintas);
    for (const medicao of medicoes) {
      if (!medicao.minimo || medicao.razao === undefined) continue;
      const atual = piores.get(medicao.papel);
      if (!atual || medicao.razao < atual.razao) piores.set(medicao.papel, medicao);
    }
    if (DETALHE) imprimirDetalhe(paleta.etiqueta, medicoes);
  }

  // A paridade com o §2 do DESIGN.md: token a token, nos dois sentidos, e
  // também no **número de paletas** — um modo documentado que não existe no CSS
  // (ou o contrário) é a mesma divergência que um token com outro valor.
  if (doCss.alternativas.length !== doMd.alternativas.length) {
    relatar(
      DESIGN_MD,
      1,
      `o §2 documenta ${doMd.alternativas.length} paleta(s) alternativa(s) e o tokens.css tem ${doCss.alternativas.length}`,
    );
  }

  const pares = [["paleta em vigor", doCss.base, doMd.base]];
  const alternativas = Math.min(doCss.alternativas.length, doMd.alternativas.length);
  for (let i = 0; i < alternativas; i += 1) {
    pares.push([
      `@media ${doCss.alternativas[i].condicao}`,
      doCss.alternativas[i].cores,
      doMd.alternativas[i].cores,
    ]);
  }

  for (const [etiqueta, css, md] of pares) {
    const tintasCss = tintasDasDeclaracoes(css);
    const tintasMd = tintasDasDeclaracoes(md);
    for (const [token, tinta] of tintasCss) {
      const documentado = tintasMd.get(token);
      if (!documentado) {
        relatar(DESIGN_MD, 1, `${etiqueta}: --color-${token} está no tokens.css e não no §2`);
      } else if (documentado.join() !== tinta.join()) {
        relatar(
          DESIGN_MD,
          1,
          `${etiqueta}: --color-${token} é oklch(${documentado.join(" ")}) no §2 e oklch(${tinta.join(" ")}) no tokens.css`,
        );
      }
    }
    for (const token of tintasMd.keys()) {
      if (!tintasCss.has(token)) {
        relatar(DESIGN_MD, 1, `${etiqueta}: --color-${token} está no §2 e não no tokens.css`);
      }
    }
  }

  const resumo = [...piores.entries()]
    .map(([papel, medicao]) => `${papel} ${medicao.razao.toFixed(3)}:1 (--color-${medicao.token})`)
    .join(", ");
  console.log(
    `check-design: ${tintasMedidas} tintas oklch no gamut sRGB, §2 em dia. Pior de cada papel: ${resumo}.`,
  );
  if (!DETALHE) console.log("check-design: `--detalhe` imprime a tabela token a token.");
}

/**
 * Cada @font-face tem de ter `font-display: swap` e vir do bundle. E cada
 * família que os tokens declaram tem de ter ficheiros: trocar a família no
 * `tokens.css` e esquecer o `@font-face` compila, passa em dev com a fonte
 * antiga ainda em cache e serve `system-ui` a quem chega de novo — uma troca de
 * identidade que falha em silêncio é exactamente o que esta passagem fez.
 */
function verificarFontes() {
  const css = readFileSync(FONTS_CSS, "utf8");
  const blocos = css.split("@font-face").slice(1);
  blocos.forEach((bloco, indice) => {
    if (!bloco.includes("font-display: swap")) {
      relatar(FONTS_CSS, 1, `@font-face #${indice + 1} sem font-display: swap`);
    }
  });

  const limpo = semComentarios(css);
  const servidas = new Set();
  const padraoServida = /font-family:\s*"([^"]+)"/g;
  let encontro = padraoServida.exec(limpo);
  while (encontro !== null) {
    servidas.add(encontro[1]);
    encontro = padraoServida.exec(limpo);
  }

  const tokens = semComentarios(readFileSync(TOKENS_CSS, "utf8"));
  const padraoDeclarada = /--font-(?:sans|mono|heading):\s*"([^"]+)"/g;
  let declarada = padraoDeclarada.exec(tokens);
  while (declarada !== null) {
    if (!servidas.has(declarada[1])) {
      relatar(
        TOKENS_CSS,
        1,
        `a família "${declarada[1]}" não tem @font-face no fonts.css — cairia para o fallback`,
      );
    }
    declarada = padraoDeclarada.exec(tokens);
  }

  console.log(
    `check-design: ${blocos.length} @font-face locais (${[...servidas].join(", ")}), e os tokens de fonte apontam para elas.`,
  );
}

verificarFicheiros();
verificarPaletaUnica();
verificarCorEMedidas();
verificarFontes();

if (problemas.length > 0) {
  console.error(`\ncheck-design: ${problemas.length} problema(s).\n`);
  for (const problema of problemas) console.error(`  ${problema}`);
  process.exit(1);
}

console.log("check-design: sem problemas.");
