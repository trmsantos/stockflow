import js from "@eslint/js";
import pluginQuery from "@tanstack/eslint-plugin-query";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import security from "eslint-plugin-security";
import globals from "globals";
import tseslint from "typescript-eslint";

/**
 * As regras do DESIGN.md §5/§6 e do SECURITY.md §7 que se conseguem impor com
 * o linter estão em `no-restricted-syntax` mais abaixo. Uma regra que o CI
 * verifica vale mais do que uma linha num documento que ninguém relê — e o
 * CLAUDE.md proíbe suprimir lint, por isso um `eslint-disable` para contornar
 * qualquer destas é uma alteração que se vê em revisão.
 */
const REGRAS_DE_DESIGN = [
  {
    // #fff, #ffffff, #ffffffff. A lookahead evita apanhar âncoras como
    // `#dados` ou `#cor`, que não são cores.
    selector:
      "Literal[value=/#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-zA-Z])/]",
    message:
      "Cor literal. Só tokens do DESIGN.md §2 (bg-surface, text-muted-foreground, ...). Ver src/styles/tokens.css.",
  },
  {
    selector:
      "Literal[value=/\\b(?:bg|text|border|ring|outline|fill|stroke|shadow|divide|decoration|accent|caret|from|via|to)-\\[/]",
    message:
      "Valor arbitrário de cor (bg-[...]). Proibido pelo DESIGN.md §6 — usa um token ou acrescenta um ao tokens.css.",
  },
  {
    selector: "Literal[value=/\\b(?:Inter|Roboto|Poppins|Open Sans|Geist|Figtree)\\b/]",
    message:
      "Fonte proibida como default (DESIGN.md §2). As fontes do projeto são Archivo e IBM Plex Mono.",
  },
  {
    selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
    message: "Proibido sem sanitização e revisão (SECURITY.md §7).",
  },
  {
    selector:
      ":matches(MemberExpression, OptionalMemberExpression)[object.name=/^(localStorage|sessionStorage)$/]",
    message:
      "Sem tokens nem estado de sessão em localStorage/sessionStorage (SECURITY.md §7). A autenticação é o cookie de sessão.",
  },
];

/**
 * O segundo caminho de dados do TanStack Router — `loader`, `loaderDeps`,
 * `useLoaderData` — não se usa nesta casa: a única camada de dados é o TanStack
 * Query (ADR 0008, decisão 1). Sem este selector, a API do router tem tudo o
 * que é preciso para uma segunda cache aparecer numa rota com pressa, e a
 * partir daí haveria dois sítios onde um ecrã pode ir buscar a mesma lista.
 *
 * No dia em que uma rota precisar de `ensureQueryData` no `beforeLoad`, tirar
 * estas duas linhas é um diff visível, com uma razão escrita — que é
 * exactamente a diferença entre uma decisão e um acidente.
 */
const REGRAS_DE_ROTEAMENTO = [
  {
    selector: "Property[key.name=/^(?:loader|loaderDeps)$/]",
    message:
      "Sem `loader`/`loaderDeps` (ADR 0008, decisão 1): os dados são do TanStack Query, não do router.",
  },
  {
    selector: "Identifier[name='useLoaderData']",
    message:
      "Sem `useLoaderData` (ADR 0008, decisão 1): um ecrã lê dados por um hook de `api.ts`, não da rota.",
  },
];

/**
 * As fronteiras do frontend (ADR 0008, decisão 2), em quatro blocos.
 *
 * No backend o import-linter protege a integridade transacional e a extração
 * futura; aqui o que se protege é a **apagabilidade**: os dados falsos só são
 * removíveis por apagamento se o conjunto de sítios que toca em cada camada for
 * finito e conhecido. Não se instala ferramenta nova — quem impõe é o
 * `no-restricted-imports` do ESLint core, que já corre.
 *
 * Os padrões seguem a semântica do `.gitignore` (é o pacote `ignore` que o
 * ESLint usa por baixo): dois asteriscos atravessam barras, um asterisco não, e
 * a última linha que casa é a que decide — por isso as negações vêm no fim. Em
 * cada bloco há também um padrão que apanha o segmento `features` em qualquer
 * posição do caminho, para o mesmo import escrito em relativo
 * (`../features/...`) não escapar pela porta do lado.
 *
 * Os quatro blocos foram medidos com uma sonda por bloco — um import proibido
 * posto de propósito, exit 1 confirmado, e removido a seguir. Quatro blocos de
 * configuração que ninguém mediu não são um gate.
 */
const FRONTEIRAS = [
  {
    files: ["src/routes/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@/features/**", "**/features/**", "!@/features/*/screens/*"],
              message:
                "Uma rota é o caminho e renderiza **um** ecrã: só `@/features/<módulo>/screens/<ecrã>`. " +
                "Se precisas de um componente, de um hook ou do `api.ts` de uma feature numa rota, a " +
                "lógica está no sítio errado (ADR 0008, decisão 2).",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/features/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              // **`regex` e não `group`, e a razão foi medida.** A forma
              // natural — `group: ["@/features/**", "!@/features/*/api"]` —
              // bloqueia *também* a porta que a ADR 0008 deixou aberta: os
              // padrões de `group` seguem a semântica do `.gitignore`, onde
              // "não é possível re-incluir um ficheiro se um directório pai
              // está excluído". Como `@/features/**` casa o próprio
              // `@/features/inventory`, a negação `!@/features/*/api` nunca
              // chega a valer, e o primeiro import legítimo entre features
              // (`purchasing` a invalidar o ledger de `inventory`) dava exit 1
              // com a mensagem a dizer que esse era precisamente o import
              // permitido. Medido com uma sonda de seis imports e quatro
              // formulações de `group`: nenhuma consegue abrir a excepção.
              //
              // O `regex` não tem a regra do directório pai, logo diz
              // exactamente o que a ADR diz: tudo o que atravesse um segmento
              // `features/` é proibido **excepto** um especificador que termine
              // em `<módulo>/api`. Fica mais apertado do que a versão anterior,
              // não menos: `@/features/inventory` (um index implícito) e
              // `@/features/inventory/api/interno` continuam bloqueados, e a
              // forma relativa (`../../inventory/api`) é bloqueada pelo padrão
              // `../../**` mais abaixo — o alias é a única porta.
              regex: "(?:^|/)features/(?![^/]+/api$)",
              message:
                "De outra feature só se importa `@/features/<módulo>/api` — o `api.py` do frontend. " +
                "Dentro da própria feature os imports são relativos (`./components/...`), logo um " +
                "`@/features/…` aqui é cross-feature por construção (ADR 0008, decisão 2).",
            },
            {
              group: ["@/routes/**", "**/routes/**", "@/shell/**", "**/shell/**"],
              message:
                "Uma feature é produto: não conhece o encaminhamento (`routes/`) nem o invólucro " +
                "(`shell/`). O que for para partilhar entre features desce para `src/components/`.",
            },
            {
              // O padrão do alias não apanha o mesmo import escrito em
              // relativo: de `features/inventory/screens/` o caminho
              // `../../purchasing/screens/receber` nunca diz "features", e foi
              // assim que a sonda deste bloco passou à primeira tentativa.
              // Dois níveis acima é sempre fora da feature; um nível acima
              // (`../components/...`) continua a ser dentro dela.
              group: ["../../**", "../../*"],
              message:
                "Dois níveis acima saem da feature. De outra feature importa-se `@/features/<módulo>/api`, " +
                "e o que for partilhado desce para `src/components/` (ADR 0008, decisão 2).",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/shell/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@/features/**", "**/features/**", "@/routes/**", "**/routes/**"],
              message:
                "O shell conhece caminhos de rota, nunca domínios: sem `@/features/*` e sem " +
                "`@/routes/*` (ADR 0008, decisão 2). Os links são tipados pela augmentação global do " +
                "router, que não precisa de import.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/lib/**/*.{ts,tsx}", "src/components/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: [
                "@/features/**",
                "**/features/**",
                "@/routes/**",
                "**/routes/**",
                "@/shell/**",
                "**/shell/**",
                "@/dev/**",
                "**/dev/**",
              ],
              message:
                "`lib/` e `components/` são o `apps/shared` do frontend: não importam nada de cima. " +
                "Uma dependência nesse sentido é um ciclo à espera de acontecer (ADR 0008, decisão 2).",
            },
          ],
        },
      ],
    },
  },
];

export default tseslint.config(
  {
    ignores: [
      "dist",
      // Gerado pelo `pnpm gen:api`. Editá-lo à mão é o erro que o CI apanha.
      "src/lib/api/types.ts",
    ],
  },
  js.configs.recommended,
  tseslint.configs.strictTypeChecked,
  tseslint.configs.stylisticTypeChecked,
  jsxA11y.flatConfigs.recommended,
  // `eslint-plugin-security` — o SECURITY.md §9 e a SKILL.md listam-no como
  // gate obrigatório e ele não estava instalado: uma linha de tabela que não
  // corria. Apanha `eval`/`new Function` com input, regex vulnerável a ReDoS,
  // `child_process`, e caminhos de ficheiro construídos por concatenação.
  security.configs.recommended,
  {
    // Duas regras do plugin desligadas **com âmbito**, nas pastas de
    // ferramentas, e não com `eslint-disable` inline (que o CLAUDE.md proíbe e
    // que desapareceria numa revisão).
    //
    // `detect-object-injection` acusa qualquer `obj[variavel]`, e a
    // `/dev/tokens` indexa mapas de tokens por chaves que ela própria define —
    // é o falso positivo mais conhecido desta regra. `detect-non-literal-fs-filename`
    // acusa o `readFileSync` do nosso script de lint de CSS, que lê ficheiros
    // que ele próprio encontrou: não há input não confiável em nenhum dos dois.
    //
    // Fora destas pastas as duas continuam activas. As outras regras do plugin
    // ficam a **warn** (é o default do `security.configs.recommended`, medido:
    // uma sonda com `eval` dá `warning security/detect-eval-with-expression`),
    // e o que as torna fatais é o `--max-warnings 0` do script `lint`. O
    // comportamento é o que se quer; o que estava errado era esta frase dizer
    // "erro" e esconder que a barra vem toda do flag.
    files: ["src/dev/**/*.{ts,tsx}", "scripts/**/*.mjs"],
    rules: {
      "security/detect-object-injection": "off",
      "security/detect-non-literal-fs-filename": "off",
    },
  },
  pluginQuery.configs["flat/recommended"],
  {
    // `mts`/`cts` incluídos: os configs partilhados do typescript-eslint
    // apanham-nos, mas era este bloco que fornecia o `projectService`, e sem
    // ele um `.mts` fazia o eslint **crashar** (exit 2) em vez de o lintar.
    // Falhava fechada, logo não era bypass — era uma falha confusa.
    files: ["**/*.{ts,tsx,mts,cts}"],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["error", { allowConstantExport: true }],
      "no-restricted-syntax": ["error", ...REGRAS_DE_DESIGN, ...REGRAS_DE_ROTEAMENTO],
      "no-restricted-globals": [
        "error",
        { name: "localStorage", message: "SECURITY.md §7: nada de estado de sessão em storage." },
        { name: "sessionStorage", message: "SECURITY.md §7: nada de estado de sessão em storage." },
      ],
      // O `process.env` não existe no browser: configuração de build é lida no
      // vite.config.ts, e o que começa por VITE_ vai para o bundle público.
      "no-restricted-properties": [
        "error",
        {
          object: "process",
          property: "env",
          message:
            "Não há process.env no browser. Configuração de build fica no vite.config.ts (SECURITY.md §7).",
        },
      ],
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { prefer: "type-imports", fixStyle: "inline-type-imports" },
      ],
    },
  },
  {
    // Primitivos gerados pelo CLI do shadcn. Não se editam à mão (DESIGN.md
    // §3), por isso o que o linter aqui apontar não tem como ser corrigido sem
    // quebrar a próxima atualização: `buttonVariants` ao lado do componente e
    // um `color-mix` em valor arbitrário vêm do registry, não de nós.
    files: ["src/components/ui/**/*.tsx"],
    rules: {
      "react-refresh/only-export-components": "off",
      "no-restricted-syntax": [
        "error",
        ...REGRAS_DE_DESIGN.filter((r) => !r.selector.includes("-\\[")),
        ...REGRAS_DE_ROTEAMENTO,
      ],
    },
  },
  // As quatro fronteiras. Ficam depois dos blocos de linguagem para nenhum
  // `rules` posterior as apagar por omissão.
  ...FRONTEIRAS,
  {
    files: ["vite.config.ts"],
    languageOptions: { globals: globals.node },
    rules: { "no-restricted-properties": "off" },
  },
  {
    files: ["**/*.{js,mjs}"],
    extends: [tseslint.configs.disableTypeChecked],
    languageOptions: { globals: globals.node },
  },
);
