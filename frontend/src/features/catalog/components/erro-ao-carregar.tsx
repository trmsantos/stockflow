import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { textos } from "../textos";

/**
 * Erro ao carregar a lista de produtos.
 */

export function ErroAoCarregar({
  mensagem,
  aoTentarOutraVez,
}: {
  readonly mensagem: string;
  readonly aoTentarOutraVez: () => void;
}) {
  return (
    <div className="rounded-lg border border-danger-border bg-danger-surface p-4">
      <div className="flex gap-3">
        <AlertCircle className="size-5 shrink-0 text-danger" aria-hidden="true" />
        <div className="flex-1">
          <h2 className="font-semibold text-danger">{textos.catalogo.erroAoCarregar}</h2>
          <p className="mt-1 text-sm text-foreground">{mensagem}</p>
          <Button
            onClick={aoTentarOutraVez}
            variant="outline"
            size="sm"
            className="mt-3"
          >
            {textos.catalogo.tentarOutraVez}
          </Button>
        </div>
      </div>
    </div>
  );
}
