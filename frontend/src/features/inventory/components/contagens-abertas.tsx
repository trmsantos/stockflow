import { Link } from "@tanstack/react-router";
import { ChevronRight, ClipboardCheck } from "lucide-react";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { mensagemDeErro } from "@/lib/api/errors";
import { formatTime } from "@/lib/format";

import { useLocalizacoes } from "../api";
import type { Contagem, Localizacao } from "../schemas";
import { textos } from "../textos";
import { diaDe, diferencaEmDiasCivis } from "../vocabulario";
import { ErroDaLista } from "./estados-da-lista";

/**
 * As contagens **a decorrer** — plural —, e o que começa outra.
 *
 * ## Porque é que isto existe, e o que substituiu
 *
 * Até à ADR 0033 havia **uma** contagem aberta por estabelecimento e o ecrã
 * Contar era o ecrã dela: ou havia contagem e contava-se, ou não havia e
 * começava-se uma. A exclusividade passou a ser **por localização** — duas
 * correcções dos mesmos factos é o que não pode acontecer duas vezes, e dois
 * instantâneos de localizações diferentes não têm uma linha de nível em comum
 * —, logo a arca e a despensa são duas contagens legítimas ao mesmo tempo e
 * "a contagem" deixou de existir como singular.
 *
 * A unidade passa a ser a **localização**: esta lista é "as minhas contagens
 * abertas", e cada linha leva à sua pelo `?contagem=` do URL (ADR 0008).
 *
 * ## O `started_at` não é cromado
 *
 * Com várias abertas ao mesmo tempo, "desde quando" é o que **distingue** uma
 * da outra — e é também o que diz a quem chega às 6h que há trabalho de ontem
 * por fechar. A contagem que não foi aberta hoje leva o trilho de 4px em âmbar
 * e a frase na mesma cor: não é um relógio a decidir nada (a ADR 0033 põe
 * expiração automática fora de âmbito, e nada aqui fecha nem apaga seja o que
 * for), é ênfase sobre um facto que já está escrito ao lado em palavras. A cor
 * nunca comunica sozinha — "aberta desde ontem às 22:14" diz o mesmo sem ela.
 *
 * E uma contagem aberta **hoje** não leva trilho nenhum: um trilho em todas as
 * linhas é uma coluna pintada que não distingue nada (DESIGN.md §3).
 */

function LinhaDeContagemAberta({ contagem }: { readonly contagem: Contagem }) {
  const deHoje = diferencaEmDiasCivis(contagem.started_at) === 0;

  return (
    <li className="relative">
      {/* Decoração (`aria-hidden`): o sentido está na frase ao lado. */}
      <span
        aria-hidden="true"
        className={`absolute inset-y-0 left-0 w-trilho ${deHoje ? "" : "bg-warning"}`}
      />
      <Link
        to="/contar"
        // O objecto e não um reducer: trocar de contagem **larga** a zona da
        // anterior, que é de outra localização e não filtra nada aqui.
        search={{ contagem: contagem.id }}
        className="flex min-h-linha items-center gap-3 border-b border-border px-celula-x py-2 transition-colors hover:bg-surface-2"
      >
        <span className="flex min-w-0 grow basis-24 flex-col">
          <span className="truncate text-sm font-medium" title={contagem.location.name}>
            {contagem.location.name}
          </span>
          <span className={`truncate text-xs ${deHoje ? "text-muted-foreground" : "text-warning"}`}>
            {textos.contagem.abertaDesde(
              diaDe(contagem.started_at),
              formatTime(contagem.started_at),
            )}
          </span>
        </span>

        {/* O número em cima e o microrótulo por baixo, como a régua de
            contadores: a 360px "3 de 9 contados" numa linha só rouba a largura
            do nome da localização, que é o que se lê primeiro. */}
        <span className="flex shrink-0 flex-col items-end">
          <span className="text-sm">
            <span data-numeric>{contagem.counted_lines}</span>{" "}
            <span className="text-muted-foreground">{textos.contagem.de}</span>{" "}
            <span data-numeric>{contagem.total_lines}</span>
          </span>
          <span className="text-xs text-muted-foreground">{textos.contagem.contados}</span>
        </span>

        <ChevronRight aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
      </Link>
    </li>
  );
}

export function ContagensAbertas({ contagens }: { readonly contagens: readonly Contagem[] }) {
  return (
    <section className="flex flex-col">
      <h2 className="px-celula-x pt-3 pb-2 text-sm font-semibold">{textos.contagem.aDecorrer}</h2>
      <ul className="flex flex-col">
        {contagens.map((contagem) => (
          <LinhaDeContagemAberta key={contagem.id} contagem={contagem} />
        ))}
      </ul>
    </section>
  );
}

/** O mesmo bloco enquanto não há dados, com a forma de duas linhas por item. */
export function EsqueletoDasContagensAbertas() {
  return (
    <div aria-busy="true" className="flex flex-col">
      <span className="sr-only">{textos.contagem.aCarregarAbertas}</span>
      <div className="px-celula-x pt-3 pb-2">
        <Skeleton className="h-4 w-40" />
      </div>
      {[0, 1].map((indice) => (
        <div
          key={indice}
          className="flex min-h-linha items-center justify-between gap-3 border-b border-border px-celula-x py-2"
        >
          <div className="flex flex-col gap-1.5">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-3 w-40" />
          </div>
          <Skeleton className="h-4 w-16" />
        </div>
      ))}
    </div>
  );
}

/**
 * Começar a contar uma localização — e desde a ADR 0033 **sem papel à porta**.
 *
 * A ADR 0030 punha o `POST /stock/counts` do lado de `owner|manager` e escrevia
 * a razão: não o risco da escrita, mas *"ocupar a única contagem aberta do
 * estabelecimento"*. Acabada a escassez, acabou a razão — e o que a restrição
 * custava era concreto: quem conta de madrugada não começava nada e ficava à
 * espera de alguém. Não há aqui aviso nenhum a explicar a mudança: quem conta
 * às 6h não precisa de saber que a regra mudou, precisa de conseguir abrir.
 *
 * As localizações vêm do `GET /locations` — a lista a sério, ordenada pelo
 * servidor (no seed ela já é o percurso: Armazém → Cozinha → Sala). **Não se
 * esconde a que já está a ser contada**: a exclusividade é do servidor (índice
 * único parcial, não um `exists()`, porque dois telemóveis vêem os dois zero
 * abertas no mesmo instante), e um seletor que a escondesse estaria a imitar
 * uma regra que não impõe. Quem escolher uma que já está aberta leva um 409
 * **navegável**, com o atalho para ela.
 */
export function AbrirContagem({
  titulo,
  aComecar,
  aoComecar,
}: {
  /** Ausente dentro de um estado vazio, que já tem título próprio. */
  readonly titulo?: string;
  readonly aComecar: boolean;
  readonly aoComecar: (localizacao: Localizacao) => void;
}) {
  const localizacoes = useLocalizacoes();
  const [escolhida, setEscolhida] = useState("");
  const campo = useId();

  const lista = localizacoes.data?.results ?? [];
  const local = lista.find((item) => item.id === escolhida) ?? lista[0];

  return (
    <>
      {titulo === undefined ? null : <h2 className="text-sm font-semibold">{titulo}</h2>}

      <div className="flex w-full max-w-xs flex-col gap-1.5">
        <Label htmlFor={campo}>{textos.contagem.ondeContar}</Label>
        <Select value={local?.id ?? ""} onValueChange={setEscolhida} disabled={lista.length === 0}>
          <SelectTrigger id={campo} className="w-full">
            <SelectValue placeholder={textos.contagem.escolhaALoja} />
          </SelectTrigger>
          <SelectContent>
            {lista.map((localizacao) => (
              <SelectItem key={localizacao.id} value={localizacao.id}>
                {localizacao.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Button
        disabled={local === undefined || aComecar}
        onClick={() => {
          if (local === undefined) return;
          aoComecar(local);
        }}
      >
        <ClipboardCheck aria-hidden="true" />
        {aComecar ? textos.contagem.aComecar : textos.contagem.comecar}
      </Button>

      {localizacoes.isError ? (
        <ErroDaLista
          titulo={textos.contagem.erroDasLocalizacoes}
          mensagem={mensagemDeErro(localizacoes.error)}
          aoTentarOutraVez={() => {
            void localizacoes.refetch();
          }}
        />
      ) : null}
    </>
  );
}
