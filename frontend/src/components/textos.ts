import { escolher } from "@/lib/i18n";

import { EN } from "./textos.en";
import { PT } from "./textos.pt";

/** A copy dos componentes partilhados, na língua desta visita. */
export const textos = escolher({ "pt-PT": PT, en: EN });
