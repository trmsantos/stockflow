import { Link } from "@tanstack/react-router";
import { ChevronLeft, ChevronRight, ShieldAlert } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDayMonthShort, formatTime } from "@/lib/format";

import type { FechoDoMes } from "../schemas";

/**
 * O **segundo grão** do painel: o fecho do mês, com salários.
 *
 * São dois grãos e não um, e a ADR 0013 (decisão 5) diz porquê numa linha: um
 * salário é um facto mensal, e ratear 30 dias por uma janela de 7 inventa
 * precisão que ninguém tem. É por isso que `period` e `month` são parâmetros
 * diferentes e que este bloco tem navegação própria.
 *
 * ## A moldura do mês a correr, e porque é que ela é obrigatória
 *
 * Medido no fixture: ao dia 6 de um mês, o custo de pessoal e os custos fixos
 * são os do **mês inteiro** e as vendas são as de seis dias — o rácio de
 * pessoal dá 117% e o resultado dá −4 200 €. Nenhum dos dois é falso e nenhum
 * dos dois é comparável, e é exactamente para isto que o contrato manda
 * `days_elapsed`/`days_in_month`: "um mês a correr ao dia 9 não se compara com
 * um fechado, e o `closed: bool` sozinho não evita a leitura errada" (decisão
 * 7). A frase está acima dos números e não abaixo.
 *
 * ## Os botões de mês, e o `disabled` que não é decoração
 *
 * Não há mês seguinte depois do mês corrente: o futuro não tem vendas e um mês
 * de zeros lido como fecho é a pior espécie de ecrã vazio. O controlo fica
 * **desactivado e visível** em vez de desaparecer — um botão que desaparece faz
 * a barra mudar de largura e deixa quem navega por teclado sem saber onde está
 * o fim da série.
 */

/** O mês anterior e o seguinte, em `YYYY-MM`. Aritmética de calendário. */
function mesVizinho(mes: string, passo: number): string {
  const [ano, numero] = mes.split("-").map(Number);
  const data = new Date(ano ?? 0, (numero ?? 1) - 1 + passo, 1, 12);
  return `${String(data.getFullYear())}-${String(data.getMonth() + 1).padStart(2, "0")}`;
}

export function NavegacaoDeMes({
  mes,
  limite,
}: {
  readonly mes: string;
  /** O último mês navegável: o corrente. Não se avança para o futuro. */
  readonly limite: string;
}) {
  const anterior = mesVizinho(mes, -1);
  const seguinte = mesVizinho(mes, 1);
  const podeAvancar = seguinte <= limite;

  return (
    <>
      <Button asChild variant="outline" size="sm">
        <Link to="/" search={(anteriores) => ({ ...anteriores, month: anterior })}>
          <ChevronLeft aria-hidden="true" />
          Mês anterior
        </Link>
      </Button>
      {podeAvancar ? (
        <Button asChild variant="outline" size="sm">
          <Link to="/" search={(anteriores) => ({ ...anteriores, month: seguinte })}>
            Mês seguinte
            <ChevronRight aria-hidden="true" />
          </Link>
        </Button>
      ) : (
        <Button
          variant="outline"
          size="sm"
          disabled
          // O `disabled` de um botão já é anunciado; o `title` diz **porquê**,
          // que é a parte que falta a quem o encontra inerte.
          title="O mês corrente é o último com dados: o seguinte ainda não aconteceu."
        >
          Mês seguinte
          <ChevronRight aria-hidden="true" />
        </Button>
      )}
    </>
  );
}

/** A fronteira do mês de negócio, ecoada: `1 set 04:00 → 1 out 04:00`. */
export function FronteiraDoMes({ mes }: { readonly mes: FechoDoMes }) {
  return (
    <>
      <span className="sr-only">Mês de negócio: </span>
      <span data-numeric className="text-xs">
        {formatDayMonthShort(mes.since)} {formatTime(mes.since)}
      </span>
      {" → "}
      <span data-numeric className="text-xs">
        {formatDayMonthShort(mes.until)} {formatTime(mes.until)}
      </span>
      <span>
        {mes.closed
          ? " · mês fechado"
          : ` · a correr: ${String(mes.days_elapsed)} de ${String(mes.days_in_month)} dias`}
      </span>
    </>
  );
}

/**
 * O aviso do mês a correr. Um `warning` e não um `danger`: não está nada mal —
 * está **incompleto**, e o passo seguinte é esperar pelo fim do mês ou olhar
 * para o bloco de período, que é o que mede o que está a acontecer.
 */
export function AvisoDoMesACorrer({ mes }: { readonly mes: FechoDoMes }) {
  if (mes.closed) return null;

  return (
    <div className="px-celula-x pb-3">
      <Alert className="border-warning-border bg-warning-surface">
        <ShieldAlert aria-hidden="true" className="text-warning" />
        <AlertTitle>
          Mês a correr: {mes.days_elapsed} de {mes.days_in_month} dias
        </AlertTitle>
        <AlertDescription className="text-foreground">
          <span className="text-pretty">
            O pessoal e os custos fixos são do mês inteiro — um salário é um facto mensal e não se
            divide por dias. As vendas e a mercadoria são as dos dias que já passaram, logo o
            resultado e os rácios deste bloco só ficam comparáveis quando o mês fechar.
          </span>
        </AlertDescription>
      </Alert>
    </div>
  );
}

/**
 * O 403 do `/month` — quem não é dono não vê este bloco, e **não é este ecrã
 * que o decide**.
 *
 * O cliente não dispara o pedido (a projecção do papel decide-o no `api.ts`),
 * logo isto só aparece no caso que a ADR 0007 fez ser verificado por pedido: a
 * pertença revogada com a página aberta, ou um deep link de alguém que não é
 * dono. Nesse caso o que se mostra é **o que se passa**, e não um
 * redireccionamento em silêncio: quem clica num link e aterra noutro ecrã não
 * aprende nada e vai tentar outra vez.
 */
export function SemPermissaoParaOMes() {
  return (
    <div className="px-celula-x pb-3">
      <Alert className="border-warning-border bg-warning-surface">
        <ShieldAlert aria-hidden="true" className="text-warning" />
        <AlertTitle>O fecho do mês é do dono do estabelecimento</AlertTitle>
        <AlertDescription className="flex flex-col items-start gap-2 text-foreground">
          <span className="text-pretty">
            Este bloco inclui salários e custo por cargo, e um custo por cargo com uma pessoa é o
            salário dessa pessoa com outro nome. O resto do painel — vendas, compras, mercadoria,
            perdas — continua acima.
          </span>
          <span className="text-xs text-muted-foreground">
            Quem decide isto é o servidor, não este ecrã.
          </span>
        </AlertDescription>
      </Alert>
    </div>
  );
}

export function EsqueletoDoMes() {
  return (
    <div aria-busy="true" className="flex flex-col gap-3 px-celula-x pb-3">
      <span className="sr-only">A carregar o fecho do mês…</span>
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-4 w-full max-w-md" />
      <Skeleton className="h-linha w-full" />
      <Skeleton className="h-linha w-full" />
      <Skeleton className="h-linha w-full" />
    </div>
  );
}
