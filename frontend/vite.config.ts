import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

// Portas do ADR 0002 — nenhuma default, para não colidir com outros projetos na
// mesma máquina. Dentro do compose o contentor ouve na porta canónica (5173) e é
// publicado em 5183 no host, por isso a porta é sobreponível por ambiente. A
// variável não tem prefixo `VITE_` de propósito: só é lida aqui, no Node, e não
// entra no bundle (SECURITY.md §7).
const DEV_PORT = Number(process.env.FRONTEND_DEV_PORT ?? 5183);
const API_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8090";

/*
 * **O servidor de dados falsos saiu daqui a 2026-10-27 (ADR 0034, decisão 7),
 * e saiu por apagamento e não por desligar.**
 *
 * Era um plugin com `apply: "serve"` em `fixtures/`, fora de `src/`, que
 * respondia aos `/api/v1/…` que o Django ainda não tinha. Com os sete recursos
 * do Stock e dos Alertas servidos pelo Django, o `ROTAS` ficou vazio e a pasta
 * inteira foi-se — a decisão 3 da ADR 0008 **termina por apagamento**, e o
 * `scripts/check-fixtures.mjs` fica no `pnpm lint` precisamente para o provar:
 * ele falha nos dois sentidos, e sem a pasta exige que este ficheiro já não
 * fale dela.
 *
 * **A perda, nomeada:** os modos `FIXTURES_ERRO`, `FIXTURES_VAZIO`,
 * `FIXTURES_SEM_SESSAO` e `FIXTURES_ATRASO_MS` — e o `?_fixture=…` por pedido —
 * ficam **sem gatilho**. Eram a forma de ver os estados do DESIGN.md §3 sem
 * dados, com erro, ou com a sessão a expirar a meio. O vazio passa a ser um
 * estabelecimento semeado sem stock (ADR 0018); os outros dois não têm hoje
 * substituto, e isso é perda e não esquecimento.
 */

export default defineConfig({
  plugins: [react(), tailwindcss()],
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
