import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/App";
import { syncThemeColor } from "@/lib/theme-color";
import "@/index.css";

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
