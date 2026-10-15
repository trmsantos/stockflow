import { Skeleton } from "@/components/ui/skeleton";

import { textos } from "../textos";

/**
 * Os esqueletos do assistente: **a forma que vem**, não um anel a rodar
 * (DESIGN.md §3). O indicador de três traços fica para o turno em curso, que é
 * o sítio onde não há forma a reservar.
 */

/** Seis linhas de 44px, como as que a lista vai ocupar. */
export function EsqueletoDaListaDeConversas() {
  return (
    <div aria-busy="true" className="flex flex-col">
      <span className="sr-only">{textos.lista.aCarregar}</span>
      {[0, 1, 2, 3, 4, 5].map((indice) => (
        <div
          key={indice}
          className="flex h-linha items-center justify-between gap-3 border-b border-border px-celula-x"
        >
          <Skeleton className="h-4 w-36" />
          <Skeleton className="h-3 w-10" />
        </div>
      ))}
    </div>
  );
}

/** Dois turnos: uma pergunta curta à direita, uma resposta de três linhas à esquerda. */
export function EsqueletoDoFio() {
  return (
    <div aria-busy="true" className="mx-auto flex w-full max-w-4xl flex-col">
      <span className="sr-only">{textos.fio.aCarregar}</span>
      {[0, 1].map((indice) => (
        <div key={indice} className="flex flex-col gap-3 border-b border-border px-celula-x py-4">
          <div className="flex flex-col items-end gap-1.5">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-4 w-56" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Skeleton className="h-4 w-full max-w-2xl" />
            <Skeleton className="h-4 w-4/5 max-w-2xl" />
            <Skeleton className="h-4 w-2/3 max-w-2xl" />
          </div>
        </div>
      ))}
    </div>
  );
}
