import { CircleAlert, CircleCheck, CircleMinus, TriangleAlert, type LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";

import type { EstadoNivel } from "../schemas";
import { rotuloDeEstado } from "../vocabulario";

/**
 * O badge de estado — o terceiro dos quatro dados de uma linha de Stock.
 *
 * Três propriedades que não são decoração:
 *
 *  - **o estado vem do servidor** (`status`), não de uma comparação feita aqui.
 *    Se o limiar de "baixo" mudar, muda num sítio e esta lista não passa a
 *    discordar dos alertas;
 *  - **a cor nunca comunica sozinha**: cada estado tem ícone *e* palavra. É a
 *    diferença entre uma etiqueta que se lê com daltonismo e uma que não;
 *  - a tinta é o `-surface` do estado com o texto em `foreground`, que é o
 *    segundo dos três papéis do DESIGN.md §2 — a cor de estado sobre a própria
 *    tinta não teria contraste. O `ok` é deliberadamente **cinzento**: um visto
 *    verde em quinze linhas é ruído, e o que o dono procura de manhã são as
 *    outras três.
 */
interface Aparencia {
  readonly tinta: string;
  readonly icone: LucideIcon;
  readonly corDoIcone: string;
}

const APARENCIA = new Map<EstadoNivel, Aparencia>([
  [
    "negativo",
    { tinta: "bg-danger-surface text-foreground", icone: CircleAlert, corDoIcone: "text-danger" },
  ],
  [
    "esgotado",
    { tinta: "bg-danger-surface text-foreground", icone: CircleMinus, corDoIcone: "text-danger" },
  ],
  [
    "baixo",
    {
      tinta: "bg-warning-surface text-foreground",
      icone: TriangleAlert,
      corDoIcone: "text-warning",
    },
  ],
  [
    "ok",
    {
      tinta: "bg-surface-2 text-muted-foreground",
      icone: CircleCheck,
      corDoIcone: "text-success",
    },
  ],
]);

const APARENCIA_DESCONHECIDA: Aparencia = {
  tinta: "bg-surface-2 text-muted-foreground",
  icone: CircleMinus,
  corDoIcone: "text-muted-foreground",
};

export function BadgeDeEstado({ estado }: { estado: EstadoNivel }) {
  const aparencia = APARENCIA.get(estado) ?? APARENCIA_DESCONHECIDA;
  const Icone = aparencia.icone;

  return (
    <Badge className={aparencia.tinta}>
      <Icone aria-hidden="true" className={aparencia.corDoIcone} />
      {rotuloDeEstado(estado)}
    </Badge>
  );
}
