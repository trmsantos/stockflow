/**
 * A raiz da app, dentro do shell.
 *
 * Continua a dizer o que está de pé em vez de fingir um dashboard: o shell
 * navega, os tokens e os estados são a sério, e os quatro ecrãs chegam um por
 * sessão. Vive em `src/shell/screens/` e não numa feature porque não tem
 * domínio nenhum — é o ecrã que fala da própria aplicação, e desaparece no dia
 * em que a raiz passar a ser um ecrã de produto.
 */
export function EcraInicial() {
  return (
    <section className="flex w-full max-w-2xl flex-col gap-4 px-4 py-6">
      <h1 className="text-3xl font-semibold tracking-tight text-balance">StockFlow</h1>
      <p className="text-pretty text-muted-foreground">
        O shell está de pé: navegação, tokens, tipografia, cliente da API e os estados de
        carregamento, vazio e erro. Os quatro ecrãs — Stock, Receber, Contar e Alertas — chegam um
        por sessão, e a API de domínio ainda não existe do outro lado.
      </p>
      {import.meta.env.DEV ? (
        <p className="text-sm">
          <a
            href="/dev/tokens"
            className="text-primary underline underline-offset-4 hover:no-underline"
          >
            Ver o sistema visual em /dev/tokens
          </a>
        </p>
      ) : null}
    </section>
  );
}
