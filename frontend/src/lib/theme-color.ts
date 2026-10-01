/**
 * Mantém o `<meta name="theme-color">` igual ao fundo da página.
 *
 * É escrito em runtime a partir do token `--color-background` em vez de estar
 * no `index.html`: o meta exige um valor literal, e uma cor literal no HTML
 * seria a única cor do projeto fora do `tokens.css` — exatamente o que o
 * DESIGN.md §6 proíbe. Assim o valor segue o token.
 *
 * Lê-se uma vez e não se subscreve nada: há **uma paleta**, escura, e ela não
 * muda em runtime (DESIGN.md §2). Havia aqui um listener de
 * `prefers-color-scheme` que voltava a escrever o meta quando o sistema
 * trocava de modo; com um modo só, era um listener a reagir a um evento que
 * não muda nada. O modo claro, quando entrar, traz o mecanismo que o
 * seleciona, e é aí que isto volta a ter o que ouvir.
 */
const META_NAME = "theme-color";

function currentBackground(): string {
  return getComputedStyle(document.documentElement).getPropertyValue("--color-background").trim();
}

export function syncThemeColor(): void {
  let meta = document.head.querySelector<HTMLMetaElement>(`meta[name="${META_NAME}"]`);
  if (meta === null) {
    meta = document.createElement("meta");
    meta.name = META_NAME;
    document.head.append(meta);
  }

  const background = currentBackground();
  if (background !== "") meta.content = background;
}
