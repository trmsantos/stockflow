/**
 * Esconde o ecrã de arranque do `index.html` quando a aplicação monta.
 *
 * ## Porquê um módulo para três linhas
 *
 * Porque o **quando** é a decisão, e ela merece estar escrita. O ecrã existe para
 * tapar a janela entre o primeiro byte e a montagem do React; escondê-lo cedo
 * demais devolve o preto que ele existe para evitar, e tarde demais tapa a
 * aplicação já pronta.
 *
 * Esconde-se num `requestAnimationFrame` depois do primeiro render, e não
 * imediatamente a seguir ao `createRoot().render()`: esse retorna antes de o
 * browser ter pintado, logo remover ali deixava um frame de nada entre os dois.
 *
 * ## `hidden` e não `remove()`
 *
 * O elemento fica no DOM com o atributo `hidden`. Removê-lo poupa um nó e custa a
 * possibilidade de o voltar a mostrar — e há um caso em que isso importa: uma
 * recarga provocada pelo router, ou um arranque que falhe depois de montar, podem
 * querer o ecrã de volta sem reconstruir a sua marcação a partir de JavaScript,
 * que é onde ela deixaria de poder usar os tokens por CSS.
 */
export function esconderArranque(): void {
  const arranque = document.getElementById("arranque");
  if (arranque === null) return;
  requestAnimationFrame(() => {
    arranque.setAttribute("hidden", "");
  });
}
