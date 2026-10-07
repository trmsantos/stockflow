import { Link } from "@tanstack/react-router";

import { formatDate, formatDaysAway, formatMoney } from "@/lib/format";

import { eZero, type QualidadeDosDados } from "../schemas";
import { textos } from "../textos";
import { rotuloDaOrigemDaReceita } from "../vocabulario";

/**
 * **O painel declara o que não sabe**, e a declaração é parte do contrato (ADR
 * 0013, decisão 7). Este bloco não é opcional e **não se esconde quando está
 * tudo bem**: é a leitura do `DataQualityOut`, que viaja nas três respostas.
 *
 * A razão é a mais forte de toda a ADR: como o `sales` v1 não escreve no
 * ledger, pode não existir consumo registado nenhum — e aí o painel mostraria
 * 85% de margem. **Um painel optimista por omissão destrói a confiança mais
 * depressa do que um prejuízo falso**, porque o prejuízo falso faz perguntar e
 * o lucro falso faz acreditar.
 *
 * ## Quatro declarações, **uma linha cada** — e isso é o que mudou
 *
 * Eram quatro parágrafos: rótulo em caixa alta numa coluna de 224px, valor, e
 * uma frase de duas linhas com a consequência. 212px de altura para quatro
 * factos, num painel que o dono do produto recusou por ter demasiado texto. O
 * peso era maior do que a informação merecia.
 *
 * Passou a **uma linha por declaração**: o nome, o valor logo a seguir e o link
 * para onde a coisa se resolve. A consequência — "sem consumo no ledger não há
 * rácio de mercadoria" — não desapareceu: está no `title` da linha e aparece por
 * baixo dela com o `?explicar=1`, como as notas das tabelas. O que se perdeu foi
 * a obrigação de ler trinta linhas para descobrir que estava tudo bem.
 *
 * E quando **está** tudo bem, é uma linha só: "O painel sabe tudo o que
 * precisa". Quatro declarações a dizer que não há nada a declarar é a definição
 * de ruído; esconder que não há nada a declarar seria pior, porque é a resposta
 * a uma das perguntas da sessão 0 ("o que aparece quando não há nada?"). As
 * quatro continuam a um clique, no mesmo interruptor.
 *
 * ## Não é um banner de alerta, e isso é deliberado
 *
 * Estas linhas usam a cor de estado como **cor de texto** (o primeiro dos três
 * papéis do DESIGN.md §2) e a palavra diz sempre o mesmo que a cor. Um banner
 * com tinta e borda por cada aviso dava quatro cartões coloridos no meio de um
 * painel escuro — o §5 quase pela letra — e, pior, dava ao "está tudo
 * registado" o mesmo peso visual que ao "ninguém contou há três meses".
 */

/** Para onde se vai resolver o que falta. Dois ecrãs, e os dois já existem. */
interface Porta {
  readonly rotulo: string;
  readonly para: "/contar" | "/receber";
}

interface Declaracao {
  readonly campo: string;
  readonly valor: string;
  /** Cor do valor. Sempre com a consequência a dizer o mesmo em palavras. */
  readonly tinta: string;
  /** A consequência, em texto: vai para o `title` e para a camada. */
  readonly consequencia: string;
  /** Só quando há o que fazer. Um aviso sem saída é um beco. */
  readonly porta?: Porta;
}

/** Quantos dias faz hoje que isto aconteceu. Dias, não dinheiro. */
function diasDesde(instante: string): number {
  const umDia = 24 * 60 * 60 * 1000;
  return Math.round((new Date(instante).getTime() - Date.now()) / umDia);
}

function declaracoesDe(qualidade: QualidadeDosDados): readonly Declaracao[] {
  const semFatura = !eZero(qualidade.purchases_awaiting_invoice_eur);
  const semVendas = qualidade.revenue_source === "none";
  // A última contagem é a única das quatro que pode **não existir**, e o `null`
  // é informação e não ausência de valor: "nunca se contou" é a declaração.
  const ultimaContagem = qualidade.last_count_at;
  const semContagem = ultimaContagem === null;

  return [
    {
      campo: textos.qualidade.campoConsumo,
      valor: qualidade.consumption_registered ? textos.qualidade.sim : textos.qualidade.nao,
      tinta: qualidade.consumption_registered ? "" : "text-warning",
      consequencia: qualidade.consumption_registered
        ? textos.qualidade.consumoSim
        : textos.qualidade.consumoNao,
      ...(qualidade.consumption_registered
        ? {}
        : { porta: { rotulo: textos.qualidade.portaRegistar, para: "/contar" } }),
    },
    {
      campo: textos.qualidade.campoSemFatura,
      valor: formatMoney(qualidade.purchases_awaiting_invoice_eur),
      tinta: semFatura ? "text-warning" : "",
      consequencia: semFatura
        ? textos.qualidade.semFaturaHa
        : textos.qualidade.semFaturaNenhuma,
      ...(semFatura
        ? { porta: { rotulo: textos.qualidade.portaRececoes, para: "/receber" } }
        : {}),
    },
    {
      campo: textos.qualidade.campoUltimaContagem,
      valor: ultimaContagem === null ? textos.qualidade.nunca : formatDate(ultimaContagem),
      tinta: semContagem ? "text-warning" : "",
      consequencia:
        ultimaContagem === null
          ? textos.qualidade.semContagem
          : textos.qualidade.contouSe(formatDaysAway(diasDesde(ultimaContagem))),
      ...(semContagem
        ? { porta: { rotulo: textos.qualidade.portaContar, para: "/contar" } }
        : {}),
    },
    {
      campo: textos.qualidade.campoOrigemDasVendas,
      valor: semVendas
        ? textos.qualidade.nenhuma
        : qualidade.revenue_source === "pos"
          ? textos.qualidade.pos
          : textos.qualidade.aMao,
      tinta: semVendas ? "text-warning" : "",
      consequencia: textos.qualidade.origemDasVendas(
        rotuloDaOrigemDaReceita(qualidade.revenue_source),
      ),
    },
  ];
}

/** Há algo a declarar? É a pergunta que decide entre uma linha e quatro. */
function temDeclaracoes(qualidade: QualidadeDosDados): boolean {
  return (
    !qualidade.consumption_registered ||
    !eZero(qualidade.purchases_awaiting_invoice_eur) ||
    qualidade.last_count_at === null ||
    qualidade.revenue_source === "none"
  );
}

function Linha({
  declaracao,
  explicar,
}: {
  readonly declaracao: Declaracao;
  readonly explicar: boolean;
}) {
  return (
    <div
      title={declaracao.consequencia}
      className="flex flex-wrap items-baseline gap-x-2 gap-y-1 border-t border-border px-celula-x py-2 first:border-t-0"
    >
      <span className="shrink-0 text-xs font-bold tracking-microrotulo text-muted-foreground uppercase">
        {declaracao.campo}
      </span>
      {/* `text-left` explícito: o `[data-numeric]` do `base.css` alinha à
          direita, que é o certo numa célula de tabela e o errado numa linha de
          leitura — aqui o valor vem logo depois do rótulo. */}
      <span data-numeric className={`shrink-0 text-left text-sm ${declaracao.tinta}`}>
        {declaracao.valor}
      </span>
      {declaracao.porta === undefined ? null : (
        <Link
          to={declaracao.porta.para}
          className="shrink-0 text-sm text-primary underline underline-offset-4 hover:no-underline"
        >
          {declaracao.porta.rotulo}
        </Link>
      )}
      {explicar ? (
        <p className="w-full text-xs leading-snug text-muted-foreground">
          {declaracao.consequencia}
        </p>
      ) : null}
    </div>
  );
}

export function QualidadeDosDadosDoPainel({
  qualidade,
  explicar,
}: {
  readonly qualidade: QualidadeDosDados;
  readonly explicar: boolean;
}) {
  const declaracoes = declaracoesDe(qualidade);

  // Tudo bem e o interruptor desligado: **uma linha**. O `title` leva os quatro
  // valores mesmo assim — "nada mais" é sobre o peso no ecrã, não sobre esconder
  // o que o painel sabe.
  //
  // A data da última contagem é a **única** que fica à vista nesta linha, e não
  // é um extra que escapou à redução: "a quebra desconhecida nunca aparece sem a
  // data da última contagem" é regra da ADR 0013 (decisão 7), e esta linha é o
  // que o painel diz sobre contagens quando as quatro declarações estão em
  // ordem. Sem ela, um mês inteiro sem contar lia-se como "o painel sabe tudo o
  // que precisa" — que é exactamente a afirmação optimista por omissão que a
  // decisão 7 existe para proibir. Existir uma contagem e estar em dia são
  // coisas diferentes, e o contrato não manda limiar nenhum para a segunda: o
  // que se pode fazer sem inventar uma regra é mostrar a data e deixar quem olha
  // decidir.
  if (!temDeclaracoes(qualidade) && !explicar) {
    return (
      <p
        className="px-celula-x pb-3 text-sm text-muted-foreground"
        title={declaracoes.map((uma) => `${uma.campo}: ${uma.valor}`).join("; ")}
      >
        {textos.qualidade.sabeTudo}
        <span data-numeric className="text-left text-sm">
          {qualidade.last_count_at === null
            ? textos.qualidade.nunca
            : formatDate(qualidade.last_count_at)}
        </span>
        .
      </p>
    );
  }

  return (
    <div className="flex flex-col">
      {declaracoes.map((declaracao) => (
        <Linha key={declaracao.campo} declaracao={declaracao} explicar={explicar} />
      ))}
    </div>
  );
}
