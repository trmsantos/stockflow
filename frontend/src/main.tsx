import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/App";
import { esconderArranque } from "@/lib/arranque";
import { syncThemeColor } from "@/lib/theme-color";

const container = document.getElementById("root");
if (container === null) {
  throw new Error("Falta o <div id=\"root\"> no index.html.");
}

syncThemeColor();

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// Depois do render, e num frame à frente: o `render()` devolve antes de o
// browser pintar, logo esconder aqui mesmo deixava um frame de nada entre o ecrã
// de arranque e a aplicação. A razão inteira está no `lib/arranque.ts`.
esconderArranque();
