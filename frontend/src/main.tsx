import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/App";
import { esconderArranque } from "@/lib/arranque";
import { aplicarLingua } from "@/lib/i18n";
import { aplicarTemaDoEspelho } from "@/lib/tema";
import { syncThemeColor } from "@/lib/theme-color";

const container = document.getElementById("root");
if (container === null) {
  throw new Error("Falta o <div id=\"root\"> no index.html.");
}

// **Antes do `createRoot`, e a ordem é a decisão** (ADR 0016, decisão 4). A
// preferência de tema vive no servidor, e o servidor só responde depois da
// primeira pintura; o que torna a pré-pintura possível é a cópia local do nome
// do tema, que esta linha lê e aplica ao `<html>`. Sem ela, quem escolheu o
// claro via um relâmpago escuro em **cada** arranque.
//
// É uma leitura de `localStorage` e um `setAttribute`, sem rede e sem React. Um
// `<script>` inline no `index.html` seria um frame mais cedo e custava
// `unsafe-inline` na CSP ou um hash guardado no Caddyfile — uma segunda fonte de
// verdade entre duas imagens, que silenciosamente parava de aplicar o tema no
// dia em que o script mudasse. A ADR mede antes de escalar.
aplicarTemaDoEspelho();

// A língua, ao lado do tema e pela mesma razão de **ordem**: o `lang` do `<html>`
// é o que diz ao leitor de ecrã que voz usar, e um texto português lido com
// pronúncia inglesa é inintelegível — não é só feio.
//
// Custa menos do que o tema e é por isso que não tem espelho nenhum: a língua
// vem do `navigator.languages`, que já está na máquina antes do primeiro pixel
// (ADR 0019, decisão 2). O `index.html` tem `lang="pt-PT"` escrito à mão para a
// primeira pintura; esta linha corrige-o quando a língua resolvida é outra.
aplicarLingua();

// Depois do tema: o `theme-color` lê o `--color-background` **da paleta activa**,
// e lê-o uma vez à cabeça. Trocado de ordem, a barra do browser nascia com a cor
// do escuro em quem prefere o claro — e só corrigia na troca seguinte.
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
