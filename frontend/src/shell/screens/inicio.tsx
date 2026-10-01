/**
 * A raiz da app, dentro do shell.
 *
 * Continua a dizer o que está de pé em vez de fingir um dashboard — e agora os
 * quatro ecrãs estão todos de pé, com dados falsos por cima e a API de domínio
 * ainda por existir do outro lado. Vive em `src/shell/screens/` e não numa
 * feature porque não tem domínio nenhum: é o ecrã que fala da própria
 * aplicação, e desaparece no dia em que a raiz passar a ser um ecrã de produto.
 */
export function EcraInicial() {
  return (
    <section className="flex w-full max-w-2xl flex-col gap-4 px-4 py-6">
      <h1 className="text-3xl font-semibold tracking-tight text-balance">StockFlow</h1>
      <p className="text-pretty text-muted-foreground">
        O shell está de pé: navegação, tokens, tipografia, cliente da API e os estados de
        carregamento, vazio e erro. Os quatro ecrãs — Stock, Receber, Contar e Alertas — já
        respondem às perguntas da manhã sobre dados de demonstração. A API de domínio ainda não
        existe do outro lado: quem responde em desenvolvimento é o servidor de dados falsos.
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
