#!/usr/bin/env node
/**
 * Guarda do sistema visual. Corre no `pnpm lint`, depois do ESLint.
 *
 * Porque existe, quando já há regras no ESLint: o ESLint não lê CSS, e é no
 * CSS que as cores vivem. Isto cobre os dois — e verifica invariantes que
 * nenhum linter conhece:
 *
 *  - **a paleta em vigor completa, e nenhuma paleta a meio**. Ver
 *    `verificarPaletas`: é aqui que este gate mudou de alvo, duas vezes, e
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
  return declaracoesDe(fonte, "color");
}

/**
 * Declarações `--<prefixo>-<nome>: <valor>` de um pedaço de CSS.
 *
 * Genérico desde 2026-10-07 porque **uma paleta não é só `--color-*`**: o
 * `--shadow-sm` codifica "num fundo preto a sombra não separa, o que separa é o
 * fio de luz na aresta de cima" (DESIGN.md §2), e num fundo claro isso
 * inverte-se — um fio de luz branco sobre papel não existe. Um tema claro com as
 * sombras do escuro é um tema a 16 de 18 que o gate antigo dava por completo
 * (ADR 0015, decisão 4).
 */
function declaracoesDe(fonte, prefixo) {
  const encontradas = new Map();
  // Um padrão **literal** com o prefixo em grupo, e não um `new RegExp` com o
  // prefixo interpolado: o `security/detect-non-literal-regexp` do
  // `eslint.config.js` acusa a construção dinâmica, e com `--max-warnings 0`
  // isso é fatal. A regra tem razão em geral (um padrão vindo de fora é um vector
  // de ReDoS) e aqui os dois chamadores passam literais — mas silenciá-la para
  // provar que este caso é seguro custa mais do que escrever o padrão fixo.
  const padrao = /--(color|shadow)-([a-z0-9-]+)\s*:\s*([^;]+);/g;
  let encontro = padrao.exec(fonte);
  while (encontro !== null) {
    if (encontro[1] === prefixo) encontradas.set(encontro[2], encontro[3].trim());
    encontro = padrao.exec(fonte);
  }
  return encontradas;
}

function literaisDe(declaracoes) {
  return new Map([...declaracoes].filter(([, valor]) => !valor.startsWith("var(")));
}

/**
 * Os blocos `:root[data-tema="<nome>"]` de um CSS, com o corpo delimitado por
 * contagem de chaves (um bloco pode conter regras com chaves, logo um
 * `indexOf("}")` não serve). Corre sobre o CSS já sem comentários, senão um
 * selector dentro de um comentário — como o que explica esta função — contava
 * como bloco.
 *
 * **Eram blocos `@media (prefers-color-scheme: …)` até 2026-10-07**, e a troca é
 * a decisão 1 da ADR 0015: a preferência de tema é **da pessoa** e vive no
 * servidor, não na configuração do sistema operativo de quem olha; e uma media
 * query tem dois estados para três paletas. O `prefers-color-scheme` passou a
 * ser proibido em `src/**` inteiro — deixou de selecionar o que quer que seja, e
 * uma segunda forma de escolher paleta é uma segunda fonte de verdade.
 */
function blocosDeTema(limpo) {
  const blocos = [];
  const padrao = /:root\[data-tema=["']?([a-z_]+)["']?\]\s*\{/g;
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
      nome: encontro[1],
      corpo: limpo.slice(abre + 1, fecha),
      inicio: encontro.index,
      fim: fecha + 1,
    });
    padrao.lastIndex = fecha + 1;
    encontro = padrao.exec(limpo);
  }
  return blocos;
}

/** O nome da paleta que vive sem atributo: é o default e a identidade aprovada. */
const PALETA_DEFAULT = "escuro";

/**
 * Separa uma fonte nas suas paletas: a **default** (tudo o que está fora de um
 * bloco de tema, isto é o `@theme static`) e uma por `:root[data-tema=…]`.
 *
 * Cada paleta traz as cores **e as sombras**, porque as duas definem o aspecto
 * de uma superfície e a completude é medida sobre as duas (ADR 0015, decisão 4).
 *
 * Os blocos de tema são removidos do texto da default antes de a ler, senão os
 * tokens de um tema entravam na paleta que ele sobrepõe — e a default passaria a
 * ter dois valores para o mesmo nome, com o último a ganhar por acidente de
 * ordem.
 */
function paletasDe(fonte) {
  const limpo = semComentarios(fonte);
  const blocos = blocosDeTema(limpo);
  let base = limpo;
  for (const bloco of [...blocos].reverse()) {
    base = base.slice(0, bloco.inicio) + base.slice(bloco.fim);
  }
  return {
    default: {
      nome: PALETA_DEFAULT,
      cores: declaracoesDeCor(base),
      sombras: declaracoesDe(base, "shadow"),
    },
    temas: blocos.map((bloco) => ({
      nome: bloco.nome,
      cores: declaracoesDeCor(bloco.corpo),
      sombras: declaracoesDe(bloco.corpo, "shadow"),
    })),
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

/* Aqui vivia a descrição do alvo **anterior** deste gate ("uma paleta só,
 * completa, e nenhum `prefers-color-scheme` parcial"), órfã em cima do
 * `SOMBRAS` depois da reescrita de 2026-10-07 e já falsa em dois pontos: o
 * `prefers-color-scheme` deixou de ser medido para passar a ser proibido, e as
 * paletas são N. A história das três versões do alvo — que é o que valia a pena
 * guardar — está inteira no comentário do `verificarPaletas`, abaixo. Duas
 * versões da mesma história no mesmo ficheiro é a forma de a errada ser a que
 * alguém lê. */

/** As duas sombras. Uma paleta não é só `--color-*` (ADR 0015, decisão 4). */
const SOMBRAS = ["sm", "lg"];

/**
 * As paletas: quantas há, se cada uma está completa, e se nenhuma segunda forma
 * de as escolher apareceu.
 *
 * ## Este gate mudou de alvo duas vezes, e as duas estão escritas
 *
 * Até 2026-10-01 exigia **paridade entre dois modos**: 18 tokens na paleta clara
 * e os mesmos 18 redefinidos num `@media (prefers-color-scheme: dark)`. Com a
 * identidade "Cabine" (escura) e a decisão "escuro primário, claro depois", essa
 * paridade passou a ser uma afirmação sobre um conjunto vazio — passava sempre.
 * Passou então a exigir **uma** paleta completa e nenhuma alternativa parcial.
 *
 * A 2026-10-07 o dono do produto pediu claro, escuro e um meio termo, e o alvo
 * mudou outra vez (ADR 0015): **N paletas, cada uma completa e cada uma medida**.
 * O que não mudou nas três versões é a propriedade: nunca se relaxou o que o
 * gate afirma — mudou-se o que ele afirma, porque a coisa mudou. A diferença
 * importa, e é a razão de isto estar escrito em vez de reescrito em silêncio.
 *
 * ## O que se exige, por paleta
 *
 *  1. os nove tokens de **estrutura** e os **três papéis** de cada cor de estado;
 *  2. as **duas sombras** — o `--shadow-sm` codifica "num fundo preto a sombra
 *     não separa, o que separa é o fio de luz na aresta de cima", e num fundo
 *     claro isso inverte-se. Um tema claro com as sombras do escuro é um tema a
 *     16 de 18 que a versão anterior deste gate dava por completo;
 *  3. todo o token literal legível como `oklch(L C h)`, senão entrava na paleta
 *     sem ser medido;
 *  4. **igualdade de conjuntos** contra a default, nos dois sentidos: um token a
 *     menos é um tema a meio, e um a mais é um token que a default não tem e que
 *     ninguém mede no caso em que o tema está inactivo.
 *
 * O gamut e o contraste são medidos à parte, em `verificarCorEMedidas`, porque é
 * lá que vive a matemática — e são medidos para **cada** paleta: o mesmo `oklch`
 * que dá 5,5:1 sobre quase-preto dá muito menos sobre papel. O gate não exige que
 * os valores difiram entre paletas; exige que cada uma passe a **sua** medição, e
 * um valor copiado falha na paleta onde não passa. Tornar impossível em vez de
 * proibir, que é a mecânica do resto deste sistema.
 */
function verificarPaletas() {
  const { default: base, temas } = paletasDe(readFileSync(TOKENS_CSS, "utf8"));

  const completude = (paleta) => {
    const literais = literaisDe(paleta.cores);

    for (const nome of ESTRUTURAIS) {
      if (!literais.has(nome)) {
        relatar(
          TOKENS_CSS,
          1,
          `paleta \`${paleta.nome}\`: não tem --color-${nome}, e sem ele não se mede`,
        );
      }
    }

    for (const sufixo of SOMBRAS) {
      if (!paleta.sombras.has(sufixo)) {
        relatar(
          TOKENS_CSS,
          1,
          `paleta \`${paleta.nome}\`: não tem --shadow-${sufixo}. Uma paleta não é só cor — ` +
            "o fio de luz na aresta de cima que separa num fundo preto não existe sobre papel",
        );
      }
    }

    for (const [nome, valor] of literais) {
      if (!/^oklch\(\s*[-\d.]+\s+[-\d.]+\s+[-\d.]+\s*\)$/.test(valor)) {
        relatar(
          TOKENS_CSS,
          1,
          `paleta \`${paleta.nome}\`: --color-${nome} é \`${valor}\` e não um oklch(L C h) — ` +
            "entrava na paleta sem ser medido",
        );
      }
    }

    // As famílias de estado vêm do **nome**: tudo o que não é estrutura é uma cor
    // de estado, e uma cor de estado tem três papéis. Um `--color-info` novo
    // passa a exigir `-surface` e `-border` nas **três** paletas sozinho, sem
    // ninguém o inscrever.
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
          `paleta \`${paleta.nome}\`: a cor de estado \`${familia}\` tem de ter os três papéis ` +
            `(DESIGN.md §2); falta ${faltam.map((nome) => `--color-${nome}`).join(", ")}`,
        );
      }
    }

    return literais;
  };

  const daDefault = completude(base);

  for (const tema of temas) {
    completude(tema);
    const suas = literaisDe(tema.cores);
    const faltam = [...daDefault.keys()].filter((nome) => !suas.has(nome));
    const aMais = [...suas.keys()].filter((nome) => !daDefault.has(nome));
    if (faltam.length > 0 || aMais.length > 0) {
      relatar(
        TOKENS_CSS,
        1,
        `paleta parcial em \`data-tema="${tema.nome}"\`: ` +
          `${faltam.length} token(s) por redefinir${faltam.length > 0 ? ` (${faltam.join(", ")})` : ""}` +
          `${aMais.length > 0 ? ` e ${aMais.length} que a paleta \`${PALETA_DEFAULT}\` não tem (${aMais.join(", ")})` : ""}.` +
          " Um tema entra completo e medido, ou não entra",
      );
    }
  }

  // `prefers-color-scheme` deixou de selecionar paleta nenhuma (ADR 0015,
  // decisão 1) e passa a ser proibido em `src/**` **inteiro**, incluindo este
  // ficheiro: uma segunda forma de escolher paleta é uma segunda fonte de
  // verdade, e esta já não escolhe nada — seria um mecanismo morto a parecer
  // vivo. A excepção é o `index.html`, que está fora de `src/` e onde a única
  // media query que resta é a de `prefers-reduced-motion`.
  for (const ficheiro of ficheirosDe(join(RAIZ, "src"), [".css"])) {
    const linhas = semComentarios(readFileSync(ficheiro, "utf8")).split("\n");
    linhas.forEach((linha, indice) => {
      if (linha.includes("prefers-color-scheme")) {
        relatar(
          ficheiro,
          indice + 1,
          "`prefers-color-scheme` não selecciona paleta nenhuma desde a ADR 0015: " +
            "o tema é um atributo `data-tema` no `<html>`, escolhido pela pessoa e guardado no servidor",
        );
      }
    });
  }

  const nomes = [PALETA_DEFAULT, ...temas.map((tema) => tema.nome)];
  console.log(
    `check-design: ${nomes.length} paleta(s) — ${nomes.join(", ")} — ` +
      `com ${daDefault.size} tokens de cor e ${SOMBRAS.length} sombras cada.`,
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

  const frente = tintas.get("foreground");
  if (!frente) {
    relatar(TOKENS_CSS, 1, `${etiqueta}: falta --color-foreground, sem ele não há o que medir`);
    return medicoes;
  }

  // **A pior superfície é calculada, não nomeada** (ADR 0015, decisão 4.2).
  //
  // Era `tintas.get("surface-2")`, com a razão escrita: "o mais claro dos três
  // pretos, logo o pior fundo para texto claro". Verdade numa paleta escura, e
  // falso numa clara — ali o pior fundo para texto escuro é o **mais escuro** dos
  // três. Nomear o `surface-2` numa paleta clara seria medir contra o melhor
  // fundo e chamar-lhe o pior, que é a forma de um gate passar a mentir sem
  // mudar uma linha.
  //
  // Calcula-se: das três superfícies, aquela contra a qual o `foreground` tem o
  // **menor** contraste. No escuro isso devolve o `surface-2`, que é o que o §2
  // já diz; no claro devolve a mais escura. E o gate imprime qual é, por paleta,
  // em cada corrida — se mudar, muda num diff.
  const candidatas = [...SUPERFICIES]
    .map((nome) => ({ nome, tinta: tintas.get(nome) }))
    .filter((candidata) => candidata.tinta !== undefined);
  if (candidatas.length === 0) {
    relatar(TOKENS_CSS, 1, `${etiqueta}: não há superfície nenhuma contra a qual medir`);
    return medicoes;
  }
  const piorSuperficie = candidatas.reduce((a, b) =>
    contraste(frente, a.tinta) <= contraste(frente, b.tinta) ? a : b,
  );
  const pior = piorSuperficie.tinta;

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
      medicao.piorSuperficie = piorSuperficie.nome;
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
    medicao.piorSuperficie = piorSuperficie.nome;
    if (razao < papel.minimo) {
      const descricao = {
        tinta: `--color-foreground sobre --color-${token}`,
        fronteira: `--color-${token} como fronteira de componente sobre ${piorSuperficie.nome}`,
        "texto-sobre-primary": `--color-${token} sobre --color-primary`,
        texto: `--color-${token} como texto sobre ${piorSuperficie.nome}`,
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

  const paletas = [doCss.default, ...doCss.temas].map((paleta) => ({
    etiqueta: `paleta \`${paleta.nome}\``,
    cores: paleta.cores,
  }));

  let tintasMedidas = 0;
  const piores = new Map();
  const medicoesPorPaleta = new Map();
  for (const paleta of paletas) {
    const tintas = tintasDasDeclaracoes(paleta.cores);
    tintasMedidas += tintas.size;
    const medicoes = medirPaleta(paleta.etiqueta, tintas);
    medicoesPorPaleta.set(paleta.etiqueta, medicoes);
    for (const medicao of medicoes) {
      if (!medicao.minimo || medicao.razao === undefined) continue;
      const atual = piores.get(medicao.papel);
      if (!atual || medicao.razao < atual.razao) piores.set(medicao.papel, medicao);
    }
    if (DETALHE) imprimirDetalhe(paleta.etiqueta, medicoes);
  }

  // A paridade com o §2 do DESIGN.md: token a token, nos dois sentidos, e
  // também nos **nomes das paletas** — um tema documentado que não existe no CSS
  // (ou o contrário) é a mesma divergência que um token com outro valor.
  //
  // Compara-se por **nome** e não por ordem, desde que as paletas passaram a
  // ter nome (ADR 0015): com blocos `@media` anónimos a única chave era a
  // posição, e trocar a ordem dos dois blocos no documento passava calado.
  const nomesCss = [doCss.default.nome, ...doCss.temas.map((t) => t.nome)];
  const nomesMd = [doMd.default.nome, ...doMd.temas.map((t) => t.nome)];
  const soNoCss = nomesCss.filter((nome) => !nomesMd.includes(nome));
  const soNoMd = nomesMd.filter((nome) => !nomesCss.includes(nome));
  if (soNoCss.length > 0 || soNoMd.length > 0) {
    relatar(
      DESIGN_MD,
      1,
      `as paletas do §2 e do tokens.css não são as mesmas: ` +
        `${soNoCss.length > 0 ? `só no tokens.css ${soNoCss.join(", ")}` : ""}` +
        `${soNoCss.length > 0 && soNoMd.length > 0 ? "; " : ""}` +
        `${soNoMd.length > 0 ? `só no §2 ${soNoMd.join(", ")}` : ""}`,
    );
  }

  const porNomeMd = new Map([doMd.default, ...doMd.temas].map((t) => [t.nome, t]));
  const pares = [doCss.default, ...doCss.temas]
    .filter((paleta) => porNomeMd.has(paleta.nome))
    .map((paleta) => [
      `paleta \`${paleta.nome}\``,
      paleta.cores,
      porNomeMd.get(paleta.nome).cores,
    ]);

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
  // A pior superfície de cada paleta é impressa **por nome**: é ela o fundo
  // contra o qual todo o texto e toda a fronteira foram medidos, e é calculada e
  // não nomeada em código. Se mudar, muda num diff — que é a única forma de
  // alguém reparar.
  const fundos = paletas
    .map((paleta) => {
      const medicoes = medicoesPorPaleta.get(paleta.etiqueta) ?? [];
      const qual = medicoes.find((medicao) => medicao.piorSuperficie !== undefined);
      return `${paleta.etiqueta} mede contra ${qual ? qual.piorSuperficie : "—"}`;
    })
    .join("; ");
  console.log(
    `check-design: ${tintasMedidas} tintas oklch no gamut sRGB, §2 em dia. Pior de cada papel: ${resumo}.`,
  );
  console.log(`check-design: ${fundos}.`);
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
verificarPaletas();
verificarCorEMedidas();
verificarFontes();

if (problemas.length > 0) {
  console.error(`\ncheck-design: ${problemas.length} problema(s).\n`);
  for (const problema of problemas) console.error(`  ${problema}`);
  process.exit(1);
}

console.log("check-design: sem problemas.");
