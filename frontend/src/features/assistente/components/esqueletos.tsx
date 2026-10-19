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

/**
 * Dois turnos com a forma do `Turno`: o bloco da pergunta à direita (rótulo e
 * um bloco de 36px com o canto de 6px) e a resposta à esquerda, com a assinatura
 * do assistente (ícone e microrótulo) e três linhas, na coluna do trilho.
 */
export function EsqueletoDoFio() {
  return (
    <div aria-busy="true" className="mx-auto flex w-full max-w-4xl flex-col">
      <span className="sr-only">{textos.fio.aCarregar}</span>
      {[0, 1].map((indice) => (
        <div key={indice} className="flex flex-col gap-3 border-b border-border px-celula-x py-4">
          <div className="flex max-w-2/3 flex-col items-end gap-1 self-end">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-9 w-56 rounded-md" />
          </div>
          <div className="flex flex-col gap-2 pl-4">
            <div className="flex items-center gap-2">
              <Skeleton className="size-4" />
              <Skeleton className="h-3 w-20" />
            </div>
            <Skeleton className="h-4 w-full max-w-2xl" />
            <Skeleton className="h-4 w-4/5 max-w-2xl" />
            <Skeleton className="h-4 w-2/3 max-w-2xl" />
          </div>
        </div>
      ))}
    </div>
  );
}
