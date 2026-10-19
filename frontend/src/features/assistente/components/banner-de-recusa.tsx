import { CircleAlert, RotateCcw } from "lucide-react";

import { textos as textosPartilhados } from "@/components/textos";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

import type { Recusa } from "../recusas";
import { textos } from "../textos";

/**
 * A recusa de uma pergunta, **no fio e não num toast**: o estado vive onde a
 * pessoa está a olhar, por cima do compositor, e a pergunta fica escrita no
 * campo para ela decidir o que lhe fazer.
 *
 * As tintas são os papéis de banner do DESIGN.md §2 — `-surface` por baixo,
 * `-border` à volta, `foreground` por cima, e a cor de estado só no ícone. As
 * duas acções possíveis vêm da recusa: repetir (só na rede) e abrir outra
 * conversa (só quando esta encheu).
 */
export function BannerDeRecusa({
  recusa,
  aoRepetir,
  aoNovaConversa,
}: {
  readonly recusa: Recusa;
  readonly aoRepetir: () => void;
  readonly aoNovaConversa: () => void;
}) {
  const aviso = recusa.tinta === "aviso";

  return (
    <Alert
      className={
        aviso ? "border-warning-border bg-warning-surface" : "border-danger-border bg-danger-surface"
      }
    >
      <CircleAlert aria-hidden="true" className={aviso ? "text-warning" : "text-danger"} />
      <AlertTitle>{recusa.titulo}</AlertTitle>
      <AlertDescription className="flex flex-col items-start gap-2">
        <span className="text-pretty">{recusa.corpo}</span>
        {recusa.repetivel ? (
          <Button type="button" variant="outline" onClick={aoRepetir}>
            <RotateCcw aria-hidden="true" />
            {textosPartilhados.tentarOutraVez}
          </Button>
        ) : null}
        {recusa.codigo === "conversa_cheia" ? (
          <Button type="button" variant="outline" onClick={aoNovaConversa}>
            {textos.ecra.novaConversa}
          </Button>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}
