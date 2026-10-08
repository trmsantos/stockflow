#!/usr/bin/env node
/**
 * check-ponte-de-captura — **o gate 4 da ADR 0020**: nada de segredo no QR.
 *
 * ## O que a ADR pede, em palavras dela
 *
 * A adenda 2, gate 4: *"o URL é composto por **uma** função, e o teste afirma
 * que ele dá `/receber/fotografar` com **exactamente dois** search params, os
 * dois uuid, **sem fragmento** e sem terceiro campo. Nenhuma string opaca de 43
 * caracteres aparece no payload, e é isso que se assere."*
 *
 * Os 43 caracteres não são um número arbitrário: é o comprimento de um
 * `secrets.token_urlsafe(32)`, que é o segredo que a **adenda 1** punha no
 * fragmento e que a adenda 2 revogou. O gate existe para que a revogação seja
 * verificável e não uma frase num documento — se alguém voltar a pôr um token no
 * link, isto fica vermelho antes de o código sair da máquina.
 *
 * ## Porque é que isto é um gate do `pnpm lint` e não um ficheiro de testes
 *
 * Porque este frontend **não tem corredor de testes**, e acrescentar um por uma
 * função pura custava uma dependência e um segundo lugar onde se verifica
 * código. A ordem desta casa é a contrária: *um gate que corre no CI vale mais
 * do que uma linha num documento que ninguém relê* (`eslint.config.js`), e os
 * seis gates do `pnpm lint` são exactamente isso. Este é o sétimo, e é o
 * primeiro que **importa** código de produção em vez de o ler como texto — o que
 * é possível por uma razão concreta: o `ponte-de-captura.ts` não tem um único
 * `import`, logo o Node carrega-o sem bundler e sem resolver o alias `@/`.
 *
 * **Uma reimplementação do URL aqui não valeria nada.** O que este ficheiro
 * afirma é sobre a função que o ecrã usa, não sobre uma cópia dela.
 *
 * ## As três metades
 *
 * **1. A forma do URL**, sobre a função a sério: caminho, dois params com nome,
 * dois uuid, zero fragmento, nada a mais. Com um terceiro campo pedido à força,
 * para o teste falhar nos dois sentidos.
 *
 * **2. Nenhum segredo no payload**: cada valor do URL é um uuid pela forma
 * canónica, e nenhuma parte dele é uma string opaca com o comprimento de um
 * token ao portador. É a asserção da ADR escrita como medida e não como
 * intenção.
 *
 * **3. Uma função e um chamador**: o `urlDaPonte` é definido **uma** vez em todo
 * o `src/` e chamado de **um** sítio. Duas definições do mesmo endereço é a
 * forma como uma delas deixa de bater, e é exactamente o que a ADR quer impedir
 * ao dizer "uma função".
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const MODULO = join(RAIZ, "src/features/purchasing/ponte-de-captura.ts");

const { CAMINHO_DA_PONTE, urlDaPonte } = await import(MODULO);

const problemas = [];
const relatar = (mensagem) => problemas.push(mensagem);

/** A forma canónica de um uuid, que é a que o `z.uuid()` do schema aceita. */
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** O comprimento de um `secrets.token_urlsafe(32)` — o segredo que não existe. */
const COMPRIMENTO_DE_TOKEN = 43;

const ESTABELECIMENTO = "a17a5e0c-5d08-4a5a-b395-d8db6eda771f";
const DOCUMENTO = "9365df98-f869-4c5d-80fe-8e4bae903ebc";

// --- 1. A forma do URL.
const bruto = urlDaPonte({
  origem: "https://stockflow.example.pt",
  estabelecimento: ESTABELECIMENTO,
  documento: DOCUMENTO,
  // Um terceiro campo, pedido à força: a função não o declara, e se um dia
  // alguém lhe acrescentar um caminho para campos extra isto apanha-o. Sem esta
  // linha o gate media só o que a assinatura já promete.
  token: "este-valor-nunca-pode-aparecer-no-payload",
});

const url = new URL(bruto);

if (url.pathname !== CAMINHO_DA_PONTE) {
  relatar(`o caminho é \`${url.pathname}\` e tinha de ser \`${CAMINHO_DA_PONTE}\``);
}

if (url.hash !== "") {
  relatar(
    `o URL tem fragmento (\`${url.hash}\`). A adenda 2 da ADR 0020 é explícita: ` +
      "o fragmento existe para um segredo não chegar ao servidor, e aqui não há segredo.",
  );
}

const params = [...url.searchParams.entries()];
if (params.length !== 2) {
  relatar(
    `o URL tem ${String(params.length)} search param(s) e tinha de ter exactamente 2: ` +
      params.map(([nome]) => nome).join(", "),
  );
}

const nomes = params.map(([nome]) => nome).sort();
if (nomes.join(",") !== "documento,estabelecimento") {
  relatar(`os search params são \`${nomes.join(", ")}\` e tinham de ser \`documento, estabelecimento\``);
}

if (url.searchParams.get("estabelecimento") !== ESTABELECIMENTO) {
  relatar("o `estabelecimento` do URL não é o que foi pedido");
}
if (url.searchParams.get("documento") !== DOCUMENTO) {
  relatar("o `documento` do URL não é o que foi pedido");
}

// --- 2. Nenhum segredo no payload.
for (const [nome, valor] of params) {
  if (!UUID.test(valor)) {
    relatar(`o search param \`${nome}\` não é um uuid: \`${valor}\`. No QR só viajam uuids.`);
  }
  if (valor.length === COMPRIMENTO_DE_TOKEN) {
    relatar(
      `o search param \`${nome}\` tem ${String(COMPRIMENTO_DE_TOKEN)} caracteres, que é o ` +
        "comprimento de um `token_urlsafe(32)`. A adenda 1 da ADR 0020 está revogada.",
    );
  }
}

if (bruto.includes("token")) {
  relatar("a palavra `token` aparece no URL composto — o payload levou alguma coisa que não devia");
}
if (bruto.includes("#")) {
  relatar("o URL composto contém `#`: não há fragmento nesta ponte");
}

// --- 3. Uma função, e um chamador.
function ficheiros(diretorio) {
  const saida = [];
  for (const nome of readdirSync(diretorio)) {
    const caminho = join(diretorio, nome);
    if (statSync(caminho).isDirectory()) saida.push(...ficheiros(caminho));
    else if (/\.tsx?$/.test(nome)) saida.push(caminho);
  }
  return saida;
}

/** Sem comentários: neste repositório o nome da função aparece em prosa a toda a hora. */
function semComentarios(fonte) {
  return fonte.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

const definem = [];
const chamam = [];
for (const caminho of ficheiros(join(RAIZ, "src"))) {
  const fonte = semComentarios(readFileSync(caminho, "utf8"));
  if (/\bfunction urlDaPonte\b/.test(fonte)) definem.push(relative(RAIZ, caminho));
  if (/\burlDaPonte\(/.test(fonte)) chamam.push(relative(RAIZ, caminho));
}

if (definem.length !== 1) {
  relatar(
    `o \`urlDaPonte\` está definido em ${String(definem.length)} ficheiro(s) — ` +
      `${definem.join(", ")}. A ADR 0020 pede **uma** função: duas definições do mesmo ` +
      "endereço é a forma como uma delas deixa de bater.",
  );
}

// O ficheiro que define também chama (dentro de si não chama, mas um dia pode):
// o que se mede é quantos **outros** compõem o endereço.
const outros = chamam.filter((caminho) => !definem.includes(caminho));
if (outros.length > 1) {
  relatar(
    `o \`urlDaPonte\` é chamado de ${String(outros.length)} sítios — ${outros.join(", ")}. ` +
      "Há um ecrã que compõe este endereço, e é o `/receber/fotografar`.",
  );
}

if (problemas.length > 0) {
  console.error(`check-ponte: ${problemas.length} problema(s).\n`);
  for (const problema of problemas) console.error(`  ${problema}`);
  console.error(
    "\nO gate 4 da ADR 0020 (adenda 2): o URL do código QR é composto por uma função, " +
      "dá `/receber/fotografar` com exactamente dois search params, os dois uuid, e sem " +
      "fragmento. Nenhum segredo viaja no código.",
  );
  process.exit(1);
}

console.log(
  `check-ponte: ${CAMINHO_DA_PONTE} com 2 search params (${nomes.join(", ")}), ` +
    `os dois uuid, sem fragmento. Uma função em ${definem.join("")}, ` +
    `chamada de ${outros.join("") || "nenhum ecrã"}.`,
);
