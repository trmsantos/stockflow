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
const API_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8010";

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
