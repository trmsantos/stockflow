import { Link } from "@tanstack/react-router";
import { ChevronLeft, ChevronRight, ShieldAlert } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDayMonthShort, formatTime } from "@/lib/format";

import type { FechoDoMes } from "../schemas";
import { textos } from "../textos";

/**
 * O **segundo grão** do painel: o fecho do mês, com salários. Vive na aba
 * **Pessoal**, e é a única que o usa.
 *
 * São dois grãos e não um, e a ADR 0013 (decisão 5) diz porquê numa linha: um
 * salário é um facto mensal, e ratear 30 dias por uma janela de 7 inventa
 * precisão que ninguém tem. É por isso que `period` e `month` são parâmetros
 * diferentes e que esta aba tem navegação própria — a barra do ecrã troca o
 * seletor de período por estes dois botões quando a aba muda.
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
    <nav aria-label={textos.fecho.navegacao} className="flex items-center gap-1">
      <Button asChild variant="outline" size="sm">
        <Link to="/painel" search={(anteriores) => ({ ...anteriores, month: anterior })}>
          <ChevronLeft aria-hidden="true" />
          {textos.fecho.mesAnterior}
        </Link>
      </Button>
      {podeAvancar ? (
        <Button asChild variant="outline" size="sm">
          <Link to="/painel" search={(anteriores) => ({ ...anteriores, month: seguinte })}>
            {textos.fecho.mesSeguinte}
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
          title={textos.fecho.semMesSeguinte}
        >
          {textos.fecho.mesSeguinte}
          <ChevronRight aria-hidden="true" />
        </Button>
      )}
    </nav>
  );
}

/**
 * A fronteira do mês de negócio, ecoada: `1 set 04:00 → 1 out 04:00`.
 *
 * Mesma forma e mesmo lugar da fronteira do período (`FronteiraDoPeriodo`), na
 * ponta direita da barra: é a mesma afirmação sobre um grão diferente, e duas
 * formas para a mesma afirmação fariam parecer que se está a falar de outra
 * coisa.
 */
export function FronteiraDoMes({ mes }: { readonly mes: FechoDoMes }) {
  return (
    <p className="ml-auto min-w-0 truncate text-xs text-muted-foreground">
      <span className="sr-only">{textos.barra.mesDeNegocio}</span>
      <span data-numeric className="text-xs">
        {formatDayMonthShort(mes.since)} {formatTime(mes.since)}
      </span>
      {" → "}
      <span data-numeric className="text-xs">
        {formatDayMonthShort(mes.until)} {formatTime(mes.until)}
      </span>
      <span>
        {mes.closed
          ? textos.fecho.mesFechado
          : textos.fecho.aCorrer(mes.days_elapsed, mes.days_in_month)}
      </span>
    </p>
  );
}

/**
 * O aviso do mês a correr. Um `warning` e não um `danger`: não está nada mal —
 * está **incompleto**, e o passo seguinte é esperar pelo fim do mês ou olhar
 * para a aba do dinheiro, que é a que mede o que está a acontecer.
 */
export function AvisoDoMesACorrer({ mes }: { readonly mes: FechoDoMes }) {
  if (mes.closed) return null;

  return (
    <div className="px-celula-x py-3">
      <Alert className="border-warning-border bg-warning-surface">
        <ShieldAlert aria-hidden="true" className="text-warning" />
        <AlertTitle>{textos.fecho.avisoTitulo(mes.days_elapsed, mes.days_in_month)}</AlertTitle>
        <AlertDescription className="text-foreground">
          <span className="text-pretty">{textos.fecho.avisoCorpo}</span>
        </AlertDescription>
      </Alert>
    </div>
  );
}

/**
 * O 403 do painel — **quem não é dono não o vê, e não é este ecrã que o
 * decide**.
 *
 * Era só do `/reporting/month` e passou a ser do painel inteiro a 2026-10-06,
 * quando o dono do produto o tirou do Início: *"esta aba de dashboard é apenas
 * para owner do estabelecimento"*. Os três caminhos de `reporting` são de
 * `{owner}`, e o cliente não dispara nenhum deles sem o papel (a projecção
 * decide-o no `api.ts`).
 *
 * Isto só aparece em dois casos, e os dois são reais: um deep link de quem não é
 * dono, e a pertença revogada com a página aberta — que é o caso que a ADR 0007
 * fez ser verificado por pedido. Nos dois mostra-se **o que se passa**, e não um
 * redireccionamento em silêncio: quem clica num link e aterra noutro ecrã não
 * aprende nada e vai tentar outra vez.
 */
export function SemPermissaoParaOPainel() {
  return (
    <div className="px-celula-x py-3">
      <Alert className="border-warning-border bg-warning-surface">
        <ShieldAlert aria-hidden="true" className="text-warning" />
        <AlertTitle>{textos.fecho.semPermissaoTitulo}</AlertTitle>
        <AlertDescription className="flex flex-col items-start gap-2 text-foreground">
          <span className="text-pretty">{textos.fecho.semPermissaoCorpo}</span>
          <Button asChild variant="outline" size="sm">
            <Link to="/">{textos.fecho.irParaOInicio}</Link>
          </Button>
          <span className="text-xs text-muted-foreground">{textos.fecho.decideOServidor}</span>
        </AlertDescription>
      </Alert>
    </div>
  );
}

export function EsqueletoDoMes() {
  return (
    <div aria-busy="true" className="flex flex-col gap-3 px-celula-x pb-3">
      <span className="sr-only">{textos.fecho.aCarregar}</span>
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-4 w-full max-w-md" />
      <Skeleton className="h-linha w-full" />
      <Skeleton className="h-linha w-full" />
      <Skeleton className="h-linha w-full" />
    </div>
  );
}
