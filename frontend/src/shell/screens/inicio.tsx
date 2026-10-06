import { Link } from "@tanstack/react-router";

/**
 * A raiz da app, dentro do shell — e a primeira coisa que se vê depois de entrar.
 *
 * ## O que isto era, e porque não podia ficar
 *
 * Era um parágrafo de prosa a dizer que "o shell está de pé: navegação, tokens,
 * tipografia, cliente da API e os estados de carregamento, vazio e erro", num
 * cap de 42rem com o nome do produto a 32px por cima. Descrevia o repositório a
 * quem abriu o produto. Era verdade e era útil — para mim, durante uma semana —
 * e era a primeira página de um ERP a falar do seu próprio andaime.
 *
 * Um ecrã assim decide a opinião de quem entra antes de chegar ao trabalho, e foi
 * exactamente isso que aconteceu quando o dono do produto olhou para a app.
 *
 * ## O que é agora
 *
 * As **perguntas de operação**, uma por linha, cada uma a levar ao ecrã que a
 * responde. Não é um menu a dobrar — o menu está na sidebar e diz os nomes dos
 * ecrãs ("Stock", "Alertas"). Isto diz as perguntas, que é a outra metade e a
 * que o DESIGN.md §1 fixa como princípio de UX: "cada ecrã responde a uma
 * pergunta de operação". Quem abre o produto às sete da manhã tem a pergunta na
 * cabeça, não o nome do ecrã.
 *
 * Linhas e não cartões, pela mesma razão que no resto da app: réguas de 1px, 44px
 * de altura, trilho de 4px que acende no hover. É a mesma linguagem da tabela de
 * Stock, e é isso que faz os dois ecrãs parecerem do mesmo produto.
 *
 * ## O que isto **não** é
 *
 * Não é um painel da manhã com números. Um painel desses é a coisa certa para
 * esta rota e está por desenhar: o que lá vai — que números, de que âmbito, com
 * que fronteira de dia — são decisões de produto que a sessão 0 responde, e
 * inventá-las aqui era pôr no primeiro ecrã do produto uma resposta que ninguém
 * deu. Os números que existem vivem nos ecrãs que os produzem, com a régua de
 * contadores, e aqui estão as portas para eles.
 *
 * Vive em `src/shell/screens/` e não numa feature porque não tem domínio nenhum:
 * não sabe o que é stock nem o que é uma receção, só sabe que rotas existem.
 */

/**
 * As perguntas, na ordem da manhã e não na do menu: primeiro o que está mal,
 * depois o que há, depois o que entrou, por fim o que foi conferido. É a mesma
 * ordem de "o que está pior primeiro" que as listas usam.
 */
const PERGUNTAS = [
  { pergunta: "O que está a faltar ou a expirar?", para: "/alertas", ecra: "Alertas" },
  { pergunta: "O que tenho, e quanto?", para: "/stock", ecra: "Stock" },
  { pergunta: "O que chegou, e falta dar entrada?", para: "/receber", ecra: "Receber" },
  { pergunta: "O que é que a contagem diz?", para: "/contar", ecra: "Contar" },
] as const;

export function EcraInicial() {
  return (
    <section className="flex w-full flex-col">
      <h1 className="sr-only">StockFlow — as perguntas da manhã</h1>

      <nav aria-label="Perguntas de operação" className="flex flex-col">
        {PERGUNTAS.map((entrada) => (
          <Link
            key={entrada.para}
            to={entrada.para}
            // `group` para o trilho e o nome do ecrã responderem ao hover da
            // linha inteira, que é o que se toca.
            className="group relative flex h-linha items-center gap-celula-x border-b border-border px-celula-x transition-colors hover:bg-surface-2"
          >
            {/* O trilho de 4px, transparente em repouso — o mesmo idioma do item
                de menu e da linha da tabela. Decoração: o destino é o texto. */}
            <span
              aria-hidden="true"
              className="absolute inset-y-0 left-0 w-trilho bg-transparent transition-colors group-hover:bg-primary"
            />
            <span className="min-w-0 flex-1 truncate font-medium">{entrada.pergunta}</span>
            <span className="shrink-0 text-xs font-bold tracking-microrotulo text-muted-foreground uppercase">
              {entrada.ecra}
            </span>
          </Link>
        ))}
      </nav>

      {import.meta.env.DEV ? (
        // Em desenvolvimento os dados de domínio vêm do servidor de fixtures
        // (ADR 0008, decisão 3) — a autenticação, não: essa é o backend a sério.
        // Em produção este ramo não existe no bundle.
        <p className="px-celula-x py-3 text-xs text-muted-foreground">
          Os dados de stock, receções e contagens são de demonstração. O sistema visual está em{" "}
          <a href="/dev/tokens" className="text-primary underline underline-offset-4 hover:no-underline">
            /dev/tokens
          </a>
          .
        </p>
      ) : null}
    </section>
  );
}
