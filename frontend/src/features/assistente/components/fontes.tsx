import { CLASSE_MICROROTULO } from "@/components/tabela";
import { formatSeconds } from "@/lib/format";

import { useNomesDoCatalogo } from "../hooks/use-nomes-do-catalogo";
import type { ToolCall } from "../schemas";
import { textos } from "../textos";
import { argumentosLegiveis, rotuloDaTool } from "../vocabulario";

/**
 * O rodapé "Fontes" de uma resposta: as tools chamadas, com os argumentos
 * principais e o nº de linhas que cada uma devolveu (ADR 0027, decisão 10).
 *
 * É o que torna um número explicável: «Saldo de artigo · Farinha T65 · 3
 * linhas» diz de onde veio o "12,5 kg" da resposta, e uma resposta **sem**
 * consultas diz-o também — é a que mais vale a pena ler com desconfiança.
 *
 * Os nomes vêm do catálogo (`useNomesDoCatalogo`), e é por isso que isto é um
 * componente com hooks e não uma função: só paga as três listas o turno que
 * tem tools chamadas.
 */
export function Fontes({
  toolCalls,
  duracaoMs,
}: {
  readonly toolCalls: readonly ToolCall[];
  /** Quanto demorou o turno, ou `null` enquanto não tiver acabado. */
  readonly duracaoMs: number | null;
}) {
  return (
    <footer className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs text-muted-foreground">
      <span className={CLASSE_MICROROTULO}>{textos.fio.fontes}</span>
      {toolCalls.length === 0 ? (
        <span>{textos.fio.semFontes}</span>
      ) : (
        <ListaDeFontes toolCalls={toolCalls} />
      )}
      {duracaoMs === null ? null : (
        <span data-numeric className="ml-auto">
          {formatSeconds(duracaoMs)}
        </span>
      )}
    </footer>
  );
}

function ListaDeFontes({ toolCalls }: { readonly toolCalls: readonly ToolCall[] }) {
  const nomes = useNomesDoCatalogo();

  return (
    <ul className="flex min-w-0 flex-wrap gap-x-3 gap-y-1">
      {toolCalls.map((tool, indice) => (
        // O índice como chave: o rasto é uma lista ordenada sem id, e a mesma
        // tool pode ser chamada duas vezes com os mesmos argumentos.
        <li key={indice} className="flex flex-wrap items-baseline gap-x-1">
          <span title={tool.name}>{rotuloDaTool(tool.name)}</span>
          {argumentosLegiveis(tool, nomes).map((argumento) => (
            <span key={argumento}>
              {" · "}
              {argumento}
            </span>
          ))}
          <span>
            {" · "}
            <span data-numeric>{textos.fio.linhas(tool.rows)}</span>
          </span>
          {tool.truncated ? <span>{` · ${textos.fio.truncado}`}</span> : null}
          {tool.ok ? null : <span className="text-danger">{` · ${textos.fio.falhou}`}</span>}
        </li>
      ))}
    </ul>
  );
}
