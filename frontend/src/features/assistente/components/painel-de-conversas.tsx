import type { UseQueryResult } from "@tanstack/react-query";
import { CircleAlert, MessagesSquare } from "lucide-react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { EstadoVazio } from "@/components/estado-vazio";
import { Button } from "@/components/ui/button";
import { mensagemDeErro } from "@/lib/api/errors";
import type { Paginated } from "@/lib/api/pagination";

import type { ConversaResumo } from "../schemas";
import { textos } from "../textos";
import { EsqueletoDaListaDeConversas } from "./esqueletos";
import { ListaDeConversas } from "./lista-de-conversas";

/**
 * A lista com os seus três estados (DESIGN.md §3) e o erro de apagar.
 *
 * Existe para a coluna de desktop e a gaveta de mobile mostrarem **a mesma
 * coisa**: os quatro ramos num sítio só, e nenhum dos dois invólucros a
 * decidir o que é um vazio.
 */
export function PainelDeConversas({
  conversas,
  ativa,
  aApagar,
  erroAoApagar,
  aoApagar,
  aoNavegar,
  aoNovaConversa,
}: {
  readonly conversas: UseQueryResult<Paginated<ConversaResumo>>;
  readonly ativa: string | null;
  readonly aApagar: string | null;
  /** A frase do servidor para um `DELETE` recusado, ou `null`. */
  readonly erroAoApagar: string | null;
  readonly aoApagar: (id: string) => void;
  readonly aoNavegar?: (() => void) | undefined;
  readonly aoNovaConversa: () => void;
}) {
  if (conversas.isPending) return <EsqueletoDaListaDeConversas />;

  if (conversas.isError) {
    return (
      <ErroAoCarregar
        titulo={textos.lista.erroAoCarregar}
        mensagem={mensagemDeErro(conversas.error)}
        aoTentarOutraVez={() => {
          void conversas.refetch();
        }}
      />
    );
  }

  if (conversas.data.results.length === 0) {
    return (
      <EstadoVazio
        icone={MessagesSquare}
        titulo={textos.lista.vazioTitulo}
        descricao={textos.lista.vazioCorpo}
      >
        <Button type="button" variant="outline" onClick={aoNovaConversa}>
          {textos.ecra.novaConversa}
        </Button>
      </EstadoVazio>
    );
  }

  return (
    <>
      {erroAoApagar === null ? null : (
        <p role="alert" className="flex items-start gap-1.5 px-celula-x py-2 text-sm text-danger">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span className="text-pretty">
            {textos.lista.erroAoApagar}
            {": "}
            {erroAoApagar}
          </span>
        </p>
      )}
      <ListaDeConversas
        conversas={conversas.data.results}
        ativa={ativa}
        aApagar={aApagar}
        aoApagar={aoApagar}
        aoNavegar={aoNavegar}
      />
    </>
  );
}
