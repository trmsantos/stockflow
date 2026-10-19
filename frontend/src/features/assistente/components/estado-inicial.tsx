import { BotMessageSquare } from "lucide-react";

import { EstadoVazio } from "@/components/estado-vazio";
import { Button } from "@/components/ui/button";

import { textos } from "../textos";

/**
 * O vazio da primeira visita: três perguntas-exemplo que **preenchem** o
 * compositor em vez de o enviarem. A pessoa vê o que se pode perguntar, lê a
 * pergunta no campo, e é dela o gesto de perguntar — uma chamada paga nunca sai
 * de um clique num exemplo.
 *
 * Três botões em linha e não três cartões em grelha (DESIGN.md §5): são atalhos
 * para um campo, não três funcionalidades.
 */
export function EstadoInicial({
  aoEscolher,
}: {
  readonly aoEscolher: (pergunta: string) => void;
}) {
  const exemplos = [textos.inicio.exemplo1, textos.inicio.exemplo2, textos.inicio.exemplo3];

  return (
    <div className="mx-auto w-full max-w-4xl">
      <EstadoVazio
        icone={BotMessageSquare}
        titulo={textos.inicio.titulo}
        descricao={textos.inicio.corpo}
      >
        <ul className="flex flex-wrap gap-2">
          {exemplos.map((exemplo) => (
            <li key={exemplo}>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  aoEscolher(exemplo);
                }}
              >
                {exemplo}
              </Button>
            </li>
          ))}
        </ul>
      </EstadoVazio>
    </div>
  );
}
