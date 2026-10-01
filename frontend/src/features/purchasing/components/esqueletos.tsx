import { Skeleton } from "@/components/ui/skeleton";

/**
 * Pendente: **skeleton, não spinner** (DESIGN.md §3), com a altura do que vem a
 * seguir para a lista não saltar quando os dados chegarem.
 *
 * Seis linhas por omissão, que é o que cabe nos ~530px úteis de um 360×640
 * depois dos dois números do topo (guião §0) — uma linha de receção tem três
 * filas de texto e é mais alta do que uma linha de stock, logo são seis e não
 * sete.
 */
export function EsqueletoDasRececoes({
  rotulo = "A carregar as receções…",
  linhas = 6,
}: {
  readonly rotulo?: string;
  readonly linhas?: number;
} = {}) {
  return (
    <div aria-busy="true" className="flex flex-col">
      <span className="sr-only">{rotulo}</span>
      {Array.from({ length: linhas }, (_, indice) => indice).map((indice) => (
        <div
          key={indice}
          className="flex min-h-14 flex-col justify-center gap-1.5 border-b border-border px-4 py-2"
        >
          <div className="flex items-center justify-between gap-3">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-16" />
          </div>
          <div className="flex items-center gap-2">
            <Skeleton className="h-4 w-10" />
            <Skeleton className="h-3 w-28" />
          </div>
          <Skeleton className="h-4 w-32" />
        </div>
      ))}
    </div>
  );
}

/** Pendente: as linhas de um documento. Mais altas, e com menos por ecrã. */
export function EsqueletoDasLinhas() {
  return (
    <div aria-busy="true" className="flex flex-col">
      <span className="sr-only">A carregar as linhas da fatura…</span>
      {[0, 1, 2].map((indice) => (
        <div key={indice} className="flex flex-col gap-1.5 border-b border-border px-4 py-3">
          <Skeleton className="h-3 w-48" />
          <div className="flex items-center justify-between gap-3">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-14" />
          </div>
          <Skeleton className="h-3 w-40" />
          <Skeleton className="h-3 w-28" />
        </div>
      ))}
    </div>
  );
}

/** Pendente: o cabeçalho do documento. */
export function EsqueletoDoCabecalho() {
  return (
    <div aria-busy="true" className="flex flex-col gap-2 px-4">
      <span className="sr-only">A carregar a receção…</span>
      <div className="flex items-baseline justify-between gap-3">
        <Skeleton className="h-7 w-44" />
        <Skeleton className="h-6 w-20" />
      </div>
      <Skeleton className="h-4 w-56" />
      <Skeleton className="h-5 w-40" />
    </div>
  );
}
