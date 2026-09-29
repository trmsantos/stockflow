/**
 * A raiz da app. Ainda não há ecrãs de produto: a API não tem endpoints (o
 * `paths` do schema OpenAPI está vazio) e os módulos chegam um por sessão.
 * Esta página diz isso em vez de finge um dashboard.
 */
export function HomeRoute() {
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <main className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-4 py-12">
        <h1 className="text-3xl font-semibold text-balance">StockFlow</h1>
        <p className="text-pretty text-muted-foreground">
          A base do frontend está de pé: tokens, tipografia, cliente da API e ferramentas. Os
          ecrãs chegam com o primeiro módulo do catálogo.
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
      </main>
    </div>
  );
}
