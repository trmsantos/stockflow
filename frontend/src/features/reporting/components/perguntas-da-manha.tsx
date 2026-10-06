import { Link } from "@tanstack/react-router";

/**
 * As perguntas de operação, uma por linha, cada uma a levar ao ecrã que a
 * responde.
 *
 * ## Porque é que isto sobreviveu a duas mudanças de direcção
 *
 * Era o ecrã Início inteiro (`shell/screens/inicio.tsx`). Com a ADR 0013 passou
 * a ser um componente — o ecrã de um `staff` e o último bloco do painel. A
 * 2026-10-06 o painel saiu do Início e o Início passou a ser a **fila de
 * trabalho do dia**, com números em vez de portas; e isto continua a existir,
 * **abaixo da fila**, por uma razão que não é inércia:
 *
 *  - **a fila responde com números e esgota-se.** Quando não há nada a expirar,
 *    nada abaixo do mínimo, nada por dar entrada e nenhuma contagem aberta, a
 *    fila está vazia — e aí a pergunta "o que tenho, e quanto?" continua a
 *    valer. Um ecrã que fica em branco quando tudo está bem ensina a não voltar
 *    a ele;
 *  - **é a única parte do Início que não depende de pedido nenhum.** Num dia em
 *    que o Wi-Fi da copa caia, ou o backend esteja em baixo, a fila não enche e
 *    estas quatro linhas continuam a abrir os quatro ecrãs. Um ecrã que falha
 *    inteiro não tem saída.
 *
 * Não é um menu a dobrar. O menu está na sidebar e diz os **nomes** dos ecrãs
 * ("Stock", "Alertas"); isto diz as **perguntas**, que é a outra metade e a que
 * o DESIGN.md §1 fixa como princípio de UX. Quem abre o produto às sete da
 * manhã tem a pergunta na cabeça, não o nome do ecrã.
 *
 * Linhas e não cartões, pela mesma razão que no resto da app: réguas de 1px,
 * 44px de altura (`h-linha`), trilho de 4px que acende no hover. É a mesma
 * linguagem da fila que vem acima e da tabela de Stock.
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
