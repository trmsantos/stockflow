/**
 * O placeholder honesto de um ecrã que ainda não existe.
 *
 * Diz **o que chega a seguir**, e não desenha um esqueleto que finge ter dados:
 * um ecrã com números inventados por cima de uma grelha vazia ensina o produto
 * errado a quem o vê e dá por feito o que não está. O que está a sério neste
 * shell é o layout, a navegação, os tokens e os estados; os ecrãs de produto
 * chegam um a um, e cada um substitui uma destas páginas.
 *
 * Vive em `src/components/` e não numa feature porque não tem domínio nenhum —
 * e não em `src/components/ui/`, que é do CLI do shadcn e não se edita à mão.
 */
export interface PorConstruirProps {
  /** O nome do ecrã, como aparece na navegação. */
  readonly titulo: string;
  /** A pergunta que o dono faz de manhã e que este ecrã vai responder. */
  readonly pergunta: string;
  /** O que o ecrã vai mostrar, em uma frase. */
  readonly conteudo: string;
}

export function PorConstruir({ titulo, pergunta, conteudo }: PorConstruirProps) {
  return (
    <section className="flex w-full max-w-2xl flex-col gap-4 px-4 py-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{titulo}</h1>
        <p className="text-pretty text-muted-foreground">{pergunta}</p>
      </div>
      <div className="rounded-xl border border-border bg-surface p-4">
        <p className="text-sm font-medium">Este ecrã chega a seguir.</p>
        <p className="mt-1 text-pretty text-sm text-muted-foreground">{conteudo}</p>
      </div>
    </section>
  );
}
