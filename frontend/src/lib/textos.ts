import { escolher } from "./i18n";

import { EN } from "./textos.en";
import { PT } from "./textos.pt";

/**
 * A copy do `src/lib/`, na língua desta visita.
 *
 * Importa o `escolher` por caminho relativo e não por `@/lib/i18n`: é o mesmo
 * módulo, e um alias para dentro da própria pasta é ruído.
 */
export const textos = escolher({ "pt-PT": PT, en: EN });
