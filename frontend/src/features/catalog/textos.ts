import { escolher } from "@/lib/i18n";

import { EN } from "./textos.en";
import { PT } from "./textos.pt";

/** A copy do `catalog`, na língua desta visita. Ver `src/lib/i18n.ts`. */
export const textos = escolher({ "pt-PT": PT, en: EN });
