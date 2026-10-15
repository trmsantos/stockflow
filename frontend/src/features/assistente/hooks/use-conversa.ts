import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { queryKeys } from "@/lib/api/query-keys";
import { tenantDaCache } from "@/lib/api/tenant";

import { lerConversa, RECURSO_CONVERSAS } from "../api";
import { temTurnoEmCurso, type Conversa } from "../schemas";

/** O intervalo do polling: 2 s (ADR 0027, decisão 3, a forma da ADR 0020 d3). */
const INTERVALO_DE_SONDAGEM_MS = 2_000;

/**
 * A desistência: 90 s (ADR 0027, decisão 3).
 *
 * A conta: 45 pedidos no máximo por turno, contra os 10/min do throttle das
 * escritas — que este `GET` nem sequer gasta. E a razão de haver um teto é a de
 * sempre: **o polling é conveniência, o caminho é a conversa.** Aos 90 s o ecrã
 * diz que a resposta aparece na conversa quando ficar pronta, em vez de sondar
 * para sempre um worker que pode nunca responder. O servidor, por seu lado, lê
 * um turno parado há mais de 2 min como `erro/tempo_esgotado` — logo quem
 * voltar a sondar depois disso recebe uma resposta terminal, não um limbo.
 */
const TETO_DE_SONDAGEM_MS = 90_000;

/** O que o ecrã precisa de saber sobre a espera, e não só sobre os dados. */
export interface ConversaSondada {
  readonly consulta: UseQueryResult<Conversa>;
  /** Há um turno `pendente` ou `a_responder`: o compositor fica à espera. */
  readonly emCurso: boolean;
  /**
   * `true` quando passaram os 90 s e o turno continua em curso. É o estado que
   * o ecrã **tem de dizer**: a alternativa é um indicador aceso para sempre.
   */
  readonly desistiu: boolean;
  /** Volta a sondar — o "tentar outra vez" do banner de desistência. */
  readonly retomar: () => void;
}

/**
 * Uma conversa, com sondagem a 2 s enquanto houver um turno em curso.
 *
 * É o `useDocumento` do `purchasing/api-de-documentos.ts` com outro relógio, e
 * as duas decisões de forma vêm de lá, medidas:
 *
 *  - `staleTime: 0` de propósito — isto não é uma leitura lenta, é a espera por
 *    um acontecimento externo (uma tarefa Celery a falar com um modelo);
 *  - a desistência é um `setTimeout` e **não** uma conta no `refetchInterval`:
 *    um predicado avaliado lá dentro pára de sondar sem produzir um render, e o
 *    ecrã ficava com o indicador aceso sem ninguém a perguntar. O temporizador
 *    força o render que escreve a frase.
 *
 * Guarda-se **qual** conversa esgotou o relógio e não um booleano: trocar de
 * conversa deixa o id antigo a não casar, e acabar o turno desliga o `emCurso` —
 * nada a repor dentro de um efeito. O `retomar` é o único caminho de volta, e é
 * um gesto da pessoa.
 */
export function useConversa(id: string | null): ConversaSondada {
  const tenant = tenantDaCache();
  const [desistidoEm, setDesistidoEm] = useState<string | null>(null);

  const consulta = useQuery({
    queryKey: queryKeys.detail(tenant, RECURSO_CONVERSAS, id ?? ""),
    queryFn: ({ signal }) => lerConversa(id ?? "", signal),
    enabled: id !== null,
    staleTime: 0,
    refetchInterval: ({ state }) =>
      desistidoEm !== id && temTurnoEmCurso(state.data) ? INTERVALO_DE_SONDAGEM_MS : false,
  });

  const emCurso = temTurnoEmCurso(consulta.data);
  const desistiu = emCurso && desistidoEm === id;

  // O relógio arranca quando o turno começa, é limpo quando ele acaba, e
  // volta a arrancar quando o `retomar` apaga a desistência.
  useEffect(() => {
    if (id === null || !emCurso || desistidoEm === id) return;
    const relogio = setTimeout(() => {
      setDesistidoEm(id);
    }, TETO_DE_SONDAGEM_MS);
    return () => {
      clearTimeout(relogio);
    };
  }, [id, emCurso, desistidoEm]);

  // Sem `useCallback`: o React Compiler memoiza-o sozinho, e recusa — com
  // razão — uma lista de dependências escrita à mão que não bate com a dele.
  const retomar = () => {
    setDesistidoEm(null);
    void consulta.refetch();
  };

  return { consulta, emCurso, desistiu, retomar };
}
