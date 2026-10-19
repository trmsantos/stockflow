import { MessagesSquare, X } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

import { textos } from "../textos";

/**
 * A lista de conversas em mobile: **a mesma lista, numa gaveta** a partir da
 * barra do ecrã. É o padrão da gaveta de navegação (ADR 0009) — um `Dialog`,
 * porque dá de graça os quatro comportamentos que ninguém escreve todos:
 * Escape, clique fora, retenção de foco, e o foco de volta ao botão ao fechar.
 *
 * O telemóvel **não** é rota de campo para este ecrã (ADR 0027, decisão 10):
 * funciona por deep link, e é isto que o torna usável — não um segundo desenho.
 *
 * O conteúdo entra por `children` e o fecho sai por `render prop`: quem
 * desenha a lista é o ecrã, e a lista precisa de fechar a gaveta ao navegar.
 */
export function GavetaDeConversas({
  children,
}: {
  readonly children: (fechar: () => void) => ReactNode;
}) {
  const [aberta, setAberta] = useState(false);
  const fechar = () => {
    setAberta(false);
  };

  return (
    <Sheet open={aberta} onOpenChange={setAberta}>
      <SheetTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="shrink-0 md:hidden"
          title={textos.ecra.abrirConversas}
        >
          <MessagesSquare aria-hidden="true" />
          <span className="sr-only">{textos.ecra.abrirConversas}</span>
        </Button>
      </SheetTrigger>

      <SheetContent side="left" showCloseButton={false} className="gap-0 bg-surface p-0">
        <SheetHeader className="h-cabecalho shrink-0 flex-row items-center gap-2 border-b border-border px-celula-x py-0">
          <SheetTitle className="truncate text-xs font-bold tracking-microrotulo text-muted-foreground uppercase">
            {textos.lista.titulo}
          </SheetTitle>
          <SheetDescription className="sr-only">{textos.ecra.conversasDescricao}</SheetDescription>
          <SheetClose asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="ml-auto shrink-0"
              title={textos.ecra.fecharConversas}
            >
              <X aria-hidden="true" />
              <span className="sr-only">{textos.ecra.fecharConversas}</span>
            </Button>
          </SheetClose>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain">{children(fechar)}</div>
      </SheetContent>
    </Sheet>
  );
}
