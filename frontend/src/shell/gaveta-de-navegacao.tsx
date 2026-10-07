import { Menu, X } from "lucide-react";
import { useState } from "react";

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

import { MenuDeNavegacao } from "./menu-de-navegacao";
import { rotulosDeCampo, type GrupoDeMenu } from "./menu";
import { RodapeDaSidebar } from "./rodape-da-sidebar";
import type { SessaoDoShell } from "./sessao-do-shell";

/**
 * A navegação de mobile: **a mesma sidebar, numa gaveta a partir do header**
 * (ADR 0009). Não é uma terceira superfície de navegação, e não é uma segunda
 * lista — o conteúdo é o `MenuDeNavegacao`, exactamente o mesmo componente com
 * exactamente o mesmo menu, mais o mesmo pé.
 *
 * ## Porquê um `Dialog` e não um painel à mão
 *
 * Uma gaveta feita com um `div` posicionado precisa de quatro comportamentos que
 * ninguém se lembra de escrever todos: fechar com Escape, fechar no clique fora,
 * **retenção de foco** enquanto está aberta e devolver o foco ao botão ao
 * fechar. Sem o terceiro, quem navega por teclado sai da gaveta para o conteúdo
 * que está tapado por ela — um defeito de acessibilidade que não se vê a olhar
 * para o ecrã. O primitivo do shadcn (`sheet`, instalado pelo CLI como o
 * DESIGN.md §3 exige) dá os quatro.
 *
 * O `showCloseButton={false}` e um `SheetClose` nosso: o botão do primitivo traz
 * o texto "Close" em inglês dentro de um `sr-only`, e a UI deste produto é em
 * português. O resto do primitivo não se edita à mão.
 *
 * ## A frase de campo, gerada e não escrita
 *
 * O rodapé do menu diz **quais** daqueles ecrãs foram desenhados para o
 * telemóvel, e a lista vem do predicado `campo` do registo de rotas
 * (`rotulosDeCampo`). É aqui que o predicado da ADR 0009 se paga: a projecção
 * por tenant não tem o campo, logo nenhuma configuração de empresa pode
 * prometer um ecrã de escritório ao telemóvel — e o DESIGN.md §4 pede que o
 * scroll horizontal dos outros seja **declarado** em vez de tratado como
 * defeito. É isto a declaração, no sítio onde ela é útil.
 */
export function GavetaDeNavegacao({
  menu,
  sessao,
}: {
  readonly menu: readonly GrupoDeMenu[];
  readonly sessao: SessaoDoShell;
}) {
  const [aberta, setAberta] = useState(false);
  const deCampo = rotulosDeCampo(menu);

  return (
    <Sheet open={aberta} onOpenChange={setAberta}>
      <SheetTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="shrink-0 md:hidden"
          title="Abrir o menu"
        >
          <Menu aria-hidden="true" />
          <span className="sr-only">Abrir o menu</span>
        </Button>
      </SheetTrigger>

      <SheetContent
        side="left"
        showCloseButton={false}
        className="gap-0 bg-surface p-0"
        // A gaveta é full-bleed e o pé dela leva o seletor e o botão de sair: num
        // telemóvel com barra de gestos, os dois ficavam por baixo dela. O valor
        // só o dispositivo o conhece, logo é `env()` e não um token; em desktop é
        // zero e não muda nada.
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <SheetHeader className="h-cabecalho shrink-0 flex-row items-center gap-2 border-b border-border px-2 py-0">
          <span aria-hidden="true" className="h-chip w-trilho shrink-0 bg-primary" />
          <SheetTitle className="truncate text-sm font-bold tracking-microrotulo uppercase">
            StockFlow
          </SheetTitle>
          {/* O `Dialog` do Radix quer uma descrição; esta serve quem ouve e não
              rouba uma linha a quem vê. */}
          <SheetDescription className="sr-only">
            Escolha um ecrã do StockFlow.
          </SheetDescription>
          <SheetClose asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="ml-auto shrink-0"
              title="Fechar o menu"
            >
              <X aria-hidden="true" />
              <span className="sr-only">Fechar o menu</span>
            </Button>
          </SheetClose>
        </SheetHeader>

        <MenuDeNavegacao
          menu={menu}
          id="gaveta"
          aoNavegar={() => {
            setAberta(false);
          }}
        />

        {deCampo.length === 0 ? null : (
          <p className="shrink-0 px-celula-x pb-3 text-xs text-pretty text-muted-foreground">
            {deCampo.join(" e ")} {deCampo.length === 1 ? "foi desenhado" : "foram desenhados"} para
            o telemóvel. Os outros ecrãs são tabelas largas: aqui deslizam na horizontal.
          </p>
        )}

        <RodapeDaSidebar sessao={sessao} id="gaveta" />
      </SheetContent>
    </Sheet>
  );
}
