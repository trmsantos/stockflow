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
      "Fonte proibida como default (DESIGN.md §2). As fontes do projeto são IBM Plex Sans e IBM Plex Mono.",
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
    // Fora destas pastas as duas continuam activas, e todas as outras regras do
    // plugin são erro em qualquer sítio.
    files: ["src/dev/**/*.{ts,tsx}", "scripts/**/*.mjs"],
    rules: {
      "security/detect-object-injection": "off",
      "security/detect-non-literal-fs-filename": "off",
    },
  },
  pluginQuery.configs["flat/recommended"],
  {
    files: ["**/*.{ts,tsx}"],
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
      "no-restricted-syntax": ["error", ...REGRAS_DE_DESIGN],
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
      "no-restricted-syntax": ["error", ...REGRAS_DE_DESIGN.filter((r) => !r.selector.includes("-\\["))],
    },
  },
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
