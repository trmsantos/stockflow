/**
 * Mantém o `<meta name="theme-color">` igual ao fundo da página.
 *
 * É escrito em runtime a partir do token `--color-background` em vez de estar
 * no `index.html`: o meta exige um valor literal, e uma cor literal no HTML
 * seria a única cor do projeto fora do `tokens.css` — exatamente o que o
 * DESIGN.md §6 proíbe. Assim o valor segue o token, incluindo quando o modo
 * muda.
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

  const apply = (element: HTMLMetaElement): void => {
    const background = currentBackground();
    if (background !== "") element.content = background;
  };

  apply(meta);
  const element = meta;
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    apply(element);
  });
}
