import { Link } from "@tanstack/react-router";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Os três estados que uma rota tem sempre, e que o DESIGN.md §3 exige em tudo o
 * que carrega: pendente, erro e não encontrado. Vivem no shell e não nos
 * ficheiros de rota porque o JSX é o mesmo para todas as rotas — o ficheiro de
 * rota nomeia-os, não os desenha (ADR 0008, decisão 2).
 */

/**
 * Pendente: o chunk da rota está a chegar. É um **skeleton**, não um spinner
 * (DESIGN.md §3), e a altura das barras aproxima o que vem a seguir para o
 * layout não saltar quando chegar.
 */
export function EsqueletoDeEcra() {
  return (
    <div className="flex w-full max-w-6xl flex-col gap-3 px-4 py-6" aria-busy="true">
      <span className="sr-only">A carregar…</span>
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-4 w-full max-w-md" />
      <Skeleton className="h-32 w-full" />
    </div>
  );
}

/**
 * O `error` que o router entrega é `unknown` — e bem: pode vir de qualquer
 * sítio. O `message` do `ApiError` já traz o `detail` do servidor, pronto para
 * mostrar, por isso não há aqui uma segunda redação da mensagem de erro.
 */
function mensagemDe(erro: unknown): string {
  if (erro instanceof Error && erro.message !== "") return erro.message;
  return "Erro inesperado. Verifique a ligação e tente outra vez.";
}

/**
 * Erro: a rota não carregou. Tem **retry** e não só um texto, porque numa
 * cozinha com Wi-Fi mau a causa mais provável é a rede e a ação certa é tentar
 * outra vez. O `reset` é o do router; não recarrega a página inteira.
 */
export function ErroDeEcra({ error, reset }: { error: unknown; reset: () => void }) {
  return (
    <div
      role="alert"
      className="m-4 flex w-full max-w-md flex-col items-start gap-3 rounded-xl border border-danger-border bg-danger-surface p-4"
    >
      <p className="font-medium">Não foi possível abrir este ecrã.</p>
      <p className="text-sm text-muted-foreground">{mensagemDe(error)}</p>
      <Button type="button" variant="outline" onClick={reset}>
        Tentar outra vez
      </Button>
    </div>
  );
}

/** Não encontrado: um URL que não existe. Dentro do shell, com saída. */
export function NaoEncontrado() {
  return (
    <div className="flex w-full max-w-md flex-col items-start gap-3 px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Este ecrã não existe</h1>
      <p className="text-pretty text-muted-foreground">
        O endereço que abriu não corresponde a nenhum ecrã do StockFlow.
      </p>
      <Button asChild variant="outline">
        <Link to="/">Voltar ao início</Link>
      </Button>
    </div>
  );
}
