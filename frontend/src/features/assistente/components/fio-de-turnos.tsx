import { useEffect, useRef } from "react";

import type { Conversa } from "../schemas";
import { Turno } from "./turno";

/**
 * O fio da conversa: os turnos por posição, e o fim sempre à vista.
 *
 * O servidor manda os turnos ordenados por `position` (ADR 0027, decisão 4) e o
 * cliente **não** reordena. O que este componente acrescenta é o scroll: quando
 * entra um turno novo ou o último muda de estado, o fim do fio volta a ficar
 * visível — é o gesto que uma pessoa faria à mão a cada resposta, e a única
 * razão para haver um `ref` aqui.
 */
export function FioDeTurnos({
  conversa,
  desistiu,
  aoRetomar,
  aoNavegar,
}: {
  readonly conversa: Conversa;
  readonly desistiu: boolean;
  readonly aoRetomar: () => void;
  /**
   * Carregou-se num botão de acção de um turno. Só o painel lateral o passa —
   * para se fechar enquanto a navegação acontece por baixo dele —, e é por isso
   * que atravessa daqui em vez de viver num contexto: um contexto para um
   * consumidor é uma dependência escondida a mais.
   */
  readonly aoNavegar?: (() => void) | undefined;
}) {
  const fim = useRef<HTMLDivElement>(null);
  const ultimo = conversa.messages.at(-1);
  // A desistência entra na assinatura: o banner dela é mais alto do que a frase
  // de espera que substitui, e o botão de voltar a sondar ficava abaixo da dobra
  // — medido numa fotografia aos 96 s.
  const assinatura = `${conversa.id}:${String(conversa.messages.length)}:${ultimo?.status ?? ""}:${String(desistiu)}`;

  useEffect(() => {
    // `block: "end"` e sem `behavior`: o scroll é instantâneo, que é o que o
    // `prefers-reduced-motion` pede e o que não distrai quem está a ler.
    fim.current?.scrollIntoView({ block: "end" });
  }, [assinatura]);

  return (
    <div className="mx-auto w-full max-w-4xl">
      <ol className="flex flex-col">
        {conversa.messages.map((mensagem) => (
          <Turno
            key={mensagem.id}
            mensagem={mensagem}
            ultimo={mensagem.id === ultimo?.id}
            desistiu={desistiu && mensagem.id === ultimo?.id}
            aoRetomar={aoRetomar}
            aoNavegar={aoNavegar}
          />
        ))}
      </ol>
      <div ref={fim} aria-hidden="true" />
    </div>
  );
}
