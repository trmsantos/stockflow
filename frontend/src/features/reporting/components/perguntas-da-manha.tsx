import { Link } from "@tanstack/react-router";

/**
 * As perguntas de operação, uma por linha, cada uma a levar ao ecrã que a
 * responde.
 *
 * ## Porque é que isto sobreviveu ao painel
 *
 * Era o ecrã Início inteiro (`shell/screens/inicio.tsx`) e passou a ser um
 * componente, por duas razões que a ADR 0013 escreve:
 *
 *  - **é o ecrã completo de um `staff`.** O painel é restrito por papel e o
 *    `staff` não o vê — aterra no Início e vê isto, que é o que ele já via. Não
 *    é um placeholder: é o ecrã certo para quem está ao balcão, e o que mudou
 *    foi passar a ser *uma* das três projecções em vez da única;
 *  - **é o último bloco do painel**, para os outros dois papéis. Num dia em que
 *    os dados não carreguem — Wi-Fi da copa, backend em baixo —, é esta lista
 *    que continua a servir. Um painel que falha inteiro não tem saída; um
 *    painel que falha com as portas para os quatro ecrãs em baixo, tem.
 *
 * Não é um menu a dobrar. O menu está na sidebar e diz os **nomes** dos ecrãs
 * ("Stock", "Alertas"); isto diz as **perguntas**, que é a outra metade e a que
 * o DESIGN.md §1 fixa como princípio de UX. Quem abre o produto às sete da
 * manhã tem a pergunta na cabeça, não o nome do ecrã.
 *
 * Linhas e não cartões, pela mesma razão que no resto da app: réguas de 1px,
 * 44px de altura (`h-linha`), trilho de 4px que acende no hover. É a mesma
 * linguagem da tabela de Stock.
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

export function PerguntasDaManha() {
  return (
    <nav aria-label="Perguntas de operação" className="flex flex-col">
      {PERGUNTAS.map((entrada) => (
        <Link
          key={entrada.para}
          to={entrada.para}
          // `group` para o trilho e o nome do ecrã responderem ao hover da
          // linha inteira, que é o que se toca.
          className="group relative flex h-linha items-center gap-celula-x border-b border-border px-celula-x transition-colors last:border-b-0 hover:bg-surface-2"
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
  );
}
