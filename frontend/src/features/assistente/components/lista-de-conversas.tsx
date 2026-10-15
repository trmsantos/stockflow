import { Link } from "@tanstack/react-router";
import { Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatDate, formatDayMonth, formatDaysAway, formatTime } from "@/lib/format";

import type { ConversaResumo } from "../schemas";
import { textos } from "../textos";

/**
 * A lista de conversas: linhas de 44px, a activa com o trilho de 4px.
 *
 * É a coluna esquerda do ecrã em desktop e o conteúdo da gaveta em mobile — o
 * **mesmo** componente, como a sidebar e a gaveta de navegação (ADR 0009). Cada
 * linha é um `<Link>` com o id da conversa no search param, logo funciona com o
 * clique do meio, com o Tab, e sobrevive a um recarregamento.
 *
 * ## Apagar pede confirmação na própria linha
 *
 * É o idioma da tabela de convites: dois passos inline, sem diálogo. Apagar é
 * final (ADR 0027, decisão 2) e numa lista densa um clique no sítio errado é um
 * acidente; mas um modal tira o contexto a quem precisa de confirmar **qual**
 * das linhas está a apagar. Em dois passos o título continua à vista e o
 * segundo clique é deliberado. Só uma linha pergunta de cada vez, porque o
 * estado é dela.
 */
export function ListaDeConversas({
  conversas,
  ativa,
  aApagar,
  aoApagar,
  aoNavegar,
}: {
  readonly conversas: readonly ConversaResumo[];
  /** O id da conversa aberta, ou `null`. */
  readonly ativa: string | null;
  /** O id da conversa cujo `DELETE` está em voo, ou `null`. */
  readonly aApagar: string | null;
  readonly aoApagar: (id: string) => void;
  /** Depois de navegar: a gaveta de mobile fecha-se com isto. */
  readonly aoNavegar?: (() => void) | undefined;
}) {
  return (
    <ul className="flex flex-col">
      {conversas.map((conversa) => (
        <LinhaDeConversa
          key={conversa.id}
          conversa={conversa}
          ativa={conversa.id === ativa}
          aApagar={aApagar === conversa.id}
          inerte={aApagar !== null}
          aoApagar={aoApagar}
          aoNavegar={aoNavegar}
        />
      ))}
    </ul>
  );
}

/**
 * Quando foi a última mensagem, no grão que importa: a hora se foi hoje, a
 * palavra se foi esta semana ("ontem", "há 3 dias"), o dia e o mês depois. A
 * data por extenso fica no `title` da linha.
 */
function quando(iso: string): string {
  const data = new Date(iso);
  const hoje = new Date();
  const inicio = (valor: Date) =>
    new Date(valor.getFullYear(), valor.getMonth(), valor.getDate()).getTime();
  const dias = Math.round((inicio(data) - inicio(hoje)) / 86_400_000);
  if (dias === 0) return formatTime(data);
  if (dias > -7) return formatDaysAway(dias);
  return formatDayMonth(data);
}

function LinhaDeConversa({
  conversa,
  ativa,
  aApagar,
  inerte,
  aoApagar,
  aoNavegar,
}: {
  readonly conversa: ConversaResumo;
  readonly ativa: boolean;
  readonly aApagar: boolean;
  /** Há **algum** apagamento em voo: as outras linhas também ficam quietas. */
  readonly inerte: boolean;
  readonly aoApagar: (id: string) => void;
  readonly aoNavegar?: (() => void) | undefined;
}) {
  const [aConfirmar, setAConfirmar] = useState(false);

  return (
    <li
      className={`relative flex h-linha items-center gap-1 border-b border-border pr-2 pl-celula-x ${
        ativa ? "bg-surface-2" : "hover:bg-surface-2/60"
      }`}
    >
      {/* O trilho de sinal na linha activa: a mesma vertical do item de menu
          activo, e só nela. A palavra que o acompanha é o `aria-current`. */}
      {ativa ? (
        <span aria-hidden="true" className="absolute inset-y-0 left-0 w-trilho bg-primary" />
      ) : null}

      {aConfirmar ? (
        <span className="flex min-w-0 flex-1 items-center justify-end gap-1">
          <span className="mr-1 truncate text-xs text-muted-foreground">
            {textos.lista.apagarEFinal}
          </span>
          <Button
            type="button"
            variant="destructive"
            size="sm"
            disabled={inerte}
            aria-busy={aApagar}
            onClick={() => {
              setAConfirmar(false);
              aoApagar(conversa.id);
            }}
          >
            <Trash2 aria-hidden="true" />
            {aApagar ? textos.lista.aApagar : textos.lista.apagar}
            <span className="sr-only">{textos.lista.aConversa(conversa.title)}</span>
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={inerte}
            onClick={() => {
              setAConfirmar(false);
            }}
          >
            {textos.lista.cancelar}
          </Button>
        </span>
      ) : (
        <>
          <Link
            to="/assistente"
            search={{ conversa: conversa.id }}
            aria-current={ativa ? "page" : undefined}
            title={textos.lista.ultimaMensagem(formatDate(conversa.last_message_at))}
            className="flex min-w-0 flex-1 items-center gap-3 self-stretch rounded-sm"
            onClick={aoNavegar}
          >
            <span className="min-w-0 flex-1 truncate text-sm">{conversa.title}</span>
            <span data-numeric className="shrink-0 text-xs text-muted-foreground">
              {quando(conversa.last_message_at)}
            </span>
          </Link>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            disabled={inerte}
            aria-busy={aApagar}
            title={textos.lista.apagarPista}
            className="shrink-0 text-muted-foreground"
            onClick={() => {
              setAConfirmar(true);
            }}
          >
            <Trash2 aria-hidden="true" />
            <span className="sr-only">
              {aApagar ? textos.lista.aApagar : textos.lista.apagar}
              {textos.lista.aConversa(conversa.title)}
            </span>
          </Button>
        </>
      )}
    </li>
  );
}
