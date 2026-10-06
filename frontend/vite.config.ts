import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

import { servidorDeFixtures } from "./fixtures/servidor.ts";

// Portas do ADR 0002 — nenhuma default, para não colidir com outros projetos na
// mesma máquina. Dentro do compose o contentor ouve na porta canónica (5173) e é
// publicado em 5183 no host, por isso a porta é sobreponível por ambiente. A
// variável não tem prefixo `VITE_` de propósito: só é lida aqui, no Node, e não
// entra no bundle (SECURITY.md §7).
const DEV_PORT = Number(process.env.FRONTEND_DEV_PORT ?? 5183);
const API_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8010";

/**
 * Os dados falsos do shell (ADR 0008, decisão 3). O plugin vive em
 * `fixtures/`, fora de `src/`, e tem `apply: "serve"` — não participa em
 * `vite build` e não há artefacto de produção que o contenha. No dia em que o
 * último fixture sair, sai a pasta e sai esta linha.
 *
 * Os três controlos são lidos aqui, no Node, porque é neste ficheiro que o
 * `process.env` é permitido (SECURITY.md §7): nenhum deles tem prefixo `VITE_`
 * e nenhum entra no bundle. Os estados do DESIGN.md §3 pedem-se por caminho:
 *   FIXTURES_ERRO=/api/v1/stock/levels pnpm dev   → 500 naquele caminho
 *   FIXTURES_VAZIO=/api/v1/stock/levels pnpm dev  → results: []
 *   FIXTURES_ATRASO_MS=1500 pnpm dev              → para ver os skeletons
 *
 * E um quarto, que não é um estado de dados: `FIXTURES_SEM_SESSAO=<caminho>`
 * responde **403 `sem_sessao`** naquele caminho, que é a sessão a expirar a
 * meio. Não é fingir uma sessão — é o contrário, e a razão está no
 * `fixtures/servidor.ts`.
 *
 * E um quinto, da mesma família: `FIXTURES_RESTRITO=/api/v1/reporting/month`
 * responde o **403 de papel** daquele caminho — o painel do dono visto por quem
 * não é dono (ADR 0013, decisão 6). Só as rotas que declaram a variante
 * `restrito` o conhecem, e hoje é uma.
 */
const ATRASO_DE_FIXTURES = Number(process.env.FIXTURES_ATRASO_MS ?? 250);

function caminhos(valor: string | undefined): string[] {
  return (valor ?? "")
    .split(",")
    .map((caminho) => caminho.trim())
    .filter((caminho) => caminho !== "");
}

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    servidorDeFixtures({
      atrasoMs: ATRASO_DE_FIXTURES,
      vazios: caminhos(process.env.FIXTURES_VAZIO),
      erros: caminhos(process.env.FIXTURES_ERRO),
      semSessao: caminhos(process.env.FIXTURES_SEM_SESSAO),
      restritos: caminhos(process.env.FIXTURES_RESTRITO),
    }),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: DEV_PORT,
    // Sem fallback silencioso para outra porta: uma porta que muda sozinha é
    // exatamente o diagnóstico opaco que o ADR 0002 evita.
    strictPort: true,
    proxy: {
      // A API é servida na mesma origem que a app — em dev pelo proxy do Vite,
      // em produção pelo Caddy. É o que torna o cookie de sessão e o
      // `connect-src 'self'` da CSP possíveis sem CORS.
      "/api": {
        target: API_ORIGIN,
        // `changeOrigin: false` é deliberado: o Django valida o header `Origin`
        // contra CSRF_TRUSTED_ORIGINS, e `http://localhost:5183` está lá
        // (config/settings/dev.py). Reescrever o Origin esconderia erros de CSRF
        // em dev que apareceriam em produção.
        changeOrigin: false,
      },
    },
  },
  preview: {
    port: DEV_PORT,
    strictPort: true,
  },
});
