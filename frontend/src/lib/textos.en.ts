import type { PT } from "./textos.pt";

/** A copy do `src/lib/`, em inglês. Ver o `textos.en.ts` do shell. */
export const EN: typeof PT = {
  erros: {
    tenantDivergente: "The establishment in the request is not the one in the session.",
    respostaInesperada: (caminho: string) =>
      `The response from ${caminho} does not have the expected shape.`,
    semLigacao: "Check the connection and try again.",
    csrfAusente: "This session has no CSRF token. Reload the page and try again.",
  },

  temas: {
    escuroNome: "Dark",
    escuroDescricao:
      "Almost-black surfaces. It is the default, and it is the palette designed for the back of house.",
    meioTermoNome: "Mid tone",
    meioTermoDescricao:
      "Graphite with light text. Lifts the surfaces for a monitor with sunlight beside it.",
    claroNome: "Light",
    claroDescricao: "Cool grey with canvas on top. For the office, and for printing a screen.",
    desconhecidoNome: "Unknown theme",
    desconhecidoDescricao:
      "This palette is newer than this version of the application. Reload the page.",
  },
};
