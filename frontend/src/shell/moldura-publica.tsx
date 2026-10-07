import { Outlet } from "@tanstack/react-router";
import { RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { textos } from "./textos";

/**
 * O invólucro do ramo público: `/entrar` e `/ativar`, **fora** do `AppShell`
 * (ADR 0010).
 *
 * Vive em `src/shell/` por eliminação e não por arrumação: não tem domínio
 * nenhum — não conhece sessão, nem convites, nem estabelecimentos — logo não é
 * uma feature; e não é `src/components/`, cuja subpasta `ui/` é do CLI do
 * shadcn. É o segundo invólucro da aplicação, e o `AppShell` é o primeiro.
 *
 * Como o `src/shell/**` não pode importar `@/features/*` (ADR 0008, decisão 2),
 * esta moldura **não sabe** o que lhe entra no `<Outlet/>` — o que é exactamente
 * o que se quer: é a rota que liga o ecrã da feature ao invólucro.
 *
 * ## A identidade, na primeira tela real do produto
 *
 * A comparação que o dono do produto aprovou a 2026-10-01 foi numa rota de dev,
 * e é aqui que a "Cabine" passa a valer: preto de monitor como tela, um painel
 * um degrau acima (`surface`), cromado contado (uma borda de 1px e o fio de luz
 * do `shadow-sm`), e o trilho de 4px em ciano ao lado do wordmark — a lâmpada
 * do painel. Nenhum gradiente, nenhum texto centrado, nenhum ícone em círculo
 * (DESIGN.md §5).
 *
 * ## `m-auto` e não `justify-center`
 *
 * Centrar com `justify-center` num contentor de `min-h-dvh` **corta o topo**
 * quando o conteúdo é mais alto que o ecrã — e é: o ecrã de activação tem duas
 * passwords e três parágrafos, e num telemóvel com o teclado aberto o viewport
 * fica com 300px de altura. Com `m-auto` no filho, a margem automática centra
 * enquanto couber e deixa de centrar quando não couber, em vez de esconder o
 * título.
 */
export function MolduraPublica() {
  return (
    <div className="flex min-h-dvh flex-col bg-background px-4 py-8 text-foreground">
      <div className="m-auto flex w-full max-w-md flex-col gap-ritmo">
        <div className="flex items-center gap-3">
          {/* O trilho de 4px da identidade. Decoração: o nome está ao lado. */}
          <span aria-hidden="true" className="h-chip w-trilho shrink-0 bg-primary" />
          <span className="text-sm font-bold tracking-microrotulo uppercase">{textos.marca}</span>
        </div>

        <main className="rounded-xl border border-border bg-surface p-6 shadow-sm">
          <Outlet />
        </main>

        <p className="text-xs text-muted-foreground">
          {textos.publico.tagline}
        </p>
      </div>
    </div>
  );
}

/**
 * Erro, dentro do painel, **com retry**.
 *
 * O ramo público tem o seu, e não usa o `ErroDeEcra` do shell, por uma razão
 * concreta: o do shell é um banner numa página com sidebar e header, e aqui não
 * há nem uma nem outro — renderizado dentro deste painel, ficava uma caixa
 * dentro de uma caixa. O `reset` é o do router e não recarrega a página.
 *
 * O `message` do `ApiError` já traz o `detail` do servidor, por isso não há aqui
 * uma segunda redação da mensagem.
 */
export function ErroPublico({ error, reset }: { error: unknown; reset: () => void }) {
  const mensagem =
    error instanceof Error && error.message !== ""
      ? error.message
      : textos.publico.erroCorpo;

  return (
    <div role="alert" className="flex flex-col items-start gap-3">
      <h1 className="text-xl font-semibold tracking-tight">{textos.publico.erroTitulo}</h1>
      <p className="text-pretty text-sm text-muted-foreground">{mensagem}</p>
      <Button type="button" variant="outline" className="h-controlo" onClick={reset}>
        <RotateCcw aria-hidden="true" />
        {textos.estados.tentarOutraVez}
      </Button>
    </div>
  );
}
