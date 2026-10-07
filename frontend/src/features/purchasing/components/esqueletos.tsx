import { Skeleton } from "@/components/ui/skeleton";

import { textos } from "../textos";

/**
 * Pendente: **skeleton, não spinner** (DESIGN.md §3), com a altura do que vem a
 * seguir para o ecrã não saltar quando os dados chegarem.
 *
 * ## Sobrou um, e isso é o resumo da conversão de 2026-10-06
 *
 * Este ficheiro tinha três. Dois eram esqueletos de **lista** — seis cartões de
 * 56px para as receções, três de quatro filas para as linhas da fatura — e
 * foram-se embora com as listas que imitavam: um esqueleto tem de ter a forma do
 * que vem a seguir, logo o pendente de uma tabela desenha a moldura e o
 * cabeçalho a sério e só as células são barras. Esse vive no módulo de tabela
 * (`src/components/tabela.tsx`) e as colunas vêm do ficheiro da tabela que ele
 * está a pendurar, para não haver duas listas de colunas a divergir.
 *
 * O que fica é o do **cabeçalho do documento**, que não é tabela nenhuma: é um
 * nome, um total e uma tira de badges.
 */

/** Pendente: o cabeçalho do documento. */
export function EsqueletoDoCabecalho() {
  return (
    <div aria-busy="true" className="flex flex-col gap-2 px-celula-x">
      <span className="sr-only">{textos.rececao.aCarregar}</span>
      <div className="flex items-baseline justify-between gap-3">
        <Skeleton className="h-7 w-44" />
        <Skeleton className="h-6 w-20" />
      </div>
      <Skeleton className="h-4 w-56" />
      <Skeleton className="h-5 w-40" />
    </div>
  );
}
