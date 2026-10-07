import { CircleAlert, RotateCcw } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { textos } from "./textos";

/**
 * O estado de erro de um bloco que carrega dados, **com retry**.
 *
 * Numa cozinha a causa mais provável é o Wi-Fi, logo a ação certa é tentar
 * outra vez e não um texto a pedir desculpa. O erro fica **no fluxo** — um
 * banner no sítio onde os dados deviam estar — e não num modal: o resto do ecrã
 * continua a funcionar, e quem está em pé não tem de despachar um diálogo para
 * voltar ao que estava a fazer.
 *
 * Vive em `src/components/` porque o desenham duas features e não tem domínio:
 * o título vem por propriedade e é **obrigatório**, de propósito. Um default do
 * género "não foi possível carregar o stock" era o que fazia este bloco dizer
 * "stock" dentro de um ecrã de faturas quando descesse de camada.
 *
 * A tinta é o `-surface` do estado com o texto em `foreground`, que é o segundo
 * dos três papéis do DESIGN.md §2; a cor de estado fica para o ícone.
 */
export function ErroAoCarregar({
  titulo,
  mensagem,
  aoTentarOutraVez,
}: {
  readonly titulo: string;
  /** A frase do servidor, já pronta para mostrar (`mensagemDeErro`). */
  readonly mensagem: string;
  readonly aoTentarOutraVez: () => void;
}) {
  return (
    <div className="px-4 py-3">
      <Alert className="border-danger-border bg-danger-surface">
        <CircleAlert aria-hidden="true" className="text-danger" />
        <AlertTitle>{titulo}</AlertTitle>
        <AlertDescription className="flex flex-col items-start gap-2">
          <span>{mensagem}</span>
          <Button variant="outline" onClick={aoTentarOutraVez}>
            <RotateCcw aria-hidden="true" />
            {textos.tentarOutraVez}
          </Button>
        </AlertDescription>
      </Alert>
    </div>
  );
}
