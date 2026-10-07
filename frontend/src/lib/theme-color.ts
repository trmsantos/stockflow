/**
 * Mantém o `<meta name="theme-color">` igual ao fundo da página.
 *
 * É escrito em runtime a partir do token `--color-background` em vez de estar
 * no `index.html`: o meta exige um valor literal, e uma cor literal no HTML
 * seria a única cor do projeto fora do `tokens.css` — exatamente o que o
 * DESIGN.md §6 proíbe. Assim o valor segue o token.
 *
 * **E desde 2026-10-07 volta a ter o que ouvir.** Até aqui lia-se uma vez, e a
 * razão escrita era verdadeira: havia uma paleta só, escura, e ela não mudava
 * em runtime. Com três paletas (ADR 0015) o fundo muda quando muda o
 * `data-tema` do `<html>`, e um meta desactualizado pinta a barra do browser no
 * telemóvel com a cor da paleta anterior — o mesmo tipo de detalhe que o
 * `color-scheme` resolve dentro da página, e que trai uma app feita a meio.
 *
 * O que se observa é o **atributo**, e não o `prefers-color-scheme`: foi esse o
 * listener que daqui saiu, porque a paleta deixou de depender da configuração
 * do sistema operativo de quem olha (ADR 0015, decisão 1). O observador é um
 * só, guardado no módulo: o `syncThemeColor()` é chamado do `main.tsx` e
 * chamá-lo duas vezes não pode deixar dois observadores a escrever o mesmo
 * meta.
 */
const META_NAME = "theme-color";
const ATRIBUTO_DE_TEMA = "data-tema";

let observador: MutationObserver | null = null;

function fundoActual(): string {
  return getComputedStyle(document.documentElement).getPropertyValue("--color-background").trim();
}

function metaDeTema(): HTMLMetaElement {
  const existente = document.head.querySelector<HTMLMetaElement>(`meta[name="${META_NAME}"]`);
  if (existente !== null) return existente;

  const criado = document.createElement("meta");
  criado.name = META_NAME;
  document.head.append(criado);
  return criado;
}

function escrever(): void {
  // `getComputedStyle` depois da mutação do atributo força o recálculo de
  // estilo, logo o valor que sai já é o da paleta nova. Se vier vazio — o CSS
  // ainda não chegou — não se escreve: um meta vazio é pior do que o anterior.
  const fundo = fundoActual();
  if (fundo !== "") metaDeTema().content = fundo;
}

export function syncThemeColor(): void {
  escrever();

  if (observador !== null) return;
  observador = new MutationObserver(escrever);
  observador.observe(document.documentElement, { attributeFilter: [ATRIBUTO_DE_TEMA] });
}
