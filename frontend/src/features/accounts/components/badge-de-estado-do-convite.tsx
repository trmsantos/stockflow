import { Ban, CircleCheck, Clock, MailQuestionMark, type LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";

import { nomeDoEstadoDoConvite, type EstadoDoConvite } from "../schemas";

/**
 * O estado de um convite, como badge — **a coluna que decide que botões a linha
 * tem**.
 *
 * Três propriedades, e nenhuma é decoração:
 *
 *  - **o estado vem do servidor**, derivado lá dos três timestamps (ADR 0010).
 *    Não há aqui uma comparação de `expira_em` com o relógio do browser: um
 *    separador aberto desde ontem veria "pendente" onde o servidor já diz
 *    "expirado", e o botão que mostrasse levaria um 409;
 *  - **a cor nunca comunica sozinha**: cada estado tem ícone *e* palavra. É a
 *    diferença entre uma etiqueta que se lê com daltonismo e uma que não;
 *  - a tinta é o `-surface` do estado com o texto em `foreground`, que é o
 *    segundo dos três papéis do DESIGN.md §2 — a cor de estado sobre a própria
 *    tinta não teria contraste. O `aceite` é deliberadamente **cinzento** e não
 *    verde: num ecrã de convites a maioria das linhas acaba aceite, e quinze
 *    vistos verdes são ruído que esconde o `expirado` que precisa de acção.
 *
 * O par `Map`/`Record` está no `schemas.ts` (texto) e aqui (aparência) porque
 * são duas coisas: o texto é vocabulário de produto e é lido também por quem
 * nunca vê um badge; a aparência é desta camada. A exaustividade sobre a união
 * gerada é verificada lá.
 */
interface Aparencia {
  readonly tinta: string;
  readonly icone: LucideIcon;
  readonly corDoIcone: string;
}

const APARENCIA = new Map<EstadoDoConvite, Aparencia>([
  [
    // `surface-2` e **não** uma tinta de acento a 15%: as três tintas de estado
    // da paleta são `success`, `warning` e `danger`, e "pendente" não é nenhum
    // dos três — é o estado normal e vivo de um convite. Um `bg-primary/15`
    // inventava uma cor que o gate do `pnpm lint` não mede (ele mede os 18
    // tokens, não composições de opacidade), e o DESIGN.md §2 diz que uma cor
    // de estado tem três papéis e não um quarto. O que distingue este do
    // `aceite`, que usa a mesma tinta, é o que tem de distinguir sempre: o
    // ícone, a palavra, e o texto em `foreground` em vez de `muted-foreground`.
    "pendente",
    {
      tinta: "bg-surface-2 text-foreground",
      icone: MailQuestionMark,
      corDoIcone: "text-primary",
    },
  ],
  [
    "expirado",
    {
      tinta: "bg-warning-surface text-foreground",
      icone: Clock,
      corDoIcone: "text-warning",
    },
  ],
  [
    "aceite",
    {
      tinta: "bg-surface-2 text-muted-foreground",
      icone: CircleCheck,
      corDoIcone: "text-success",
    },
  ],
  [
    "revogado",
    {
      tinta: "bg-danger-surface text-foreground",
      icone: Ban,
      corDoIcone: "text-danger",
    },
  ],
]);

/**
 * Um estado que esta versão do bundle não conhece.
 *
 * Inalcançável hoje — a união vem do enum gerado e o `Record` do `schemas.ts` é
 * exaustivo nos dois sentidos — e deixa de o ser no dia em que o servidor for
 * mais novo que este bundle. Nesse dia um badge cinzento com o texto do
 * `schemas.ts` é o comportamento certo: a linha continua a existir e a lista
 * continua a montar.
 */
const APARENCIA_DESCONHECIDA: Aparencia = {
  tinta: "bg-surface-2 text-muted-foreground",
  icone: MailQuestionMark,
  corDoIcone: "text-muted-foreground",
};

export function BadgeDeEstadoDoConvite({ estado }: { readonly estado: EstadoDoConvite }) {
  const aparencia = APARENCIA.get(estado) ?? APARENCIA_DESCONHECIDA;
  const Icone = aparencia.icone;
  const { rotulo, explicacao } = nomeDoEstadoDoConvite(estado);

  return (
    <Badge className={`h-chip ${aparencia.tinta}`} title={explicacao}>
      <Icone aria-hidden="true" className={aparencia.corDoIcone} />
      {rotulo}
    </Badge>
  );
}
