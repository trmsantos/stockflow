import {
  CLASSE_CONTADOR,
  CorpoDoContador,
  ReguaDeContadores,
} from "@/components/regua-de-contadores";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMoney, formatUnitMoney } from "@/lib/format";

import { fichaMostraEuros } from "../euros-da-ficha";
import type { ReceitaResumo } from "../schemas";
import { textos } from "../textos";
import { tintaDoTextoDoCusto } from "../tinta-do-custo";
import { fraseDaCobertura, palavraDoCusto, textoDeQuantidade, textoNaUnidadeBase } from "../vocabulario";

/**
 * Os números da ficha, numa **régua de campos** e não numa grelha de cartões
 * (DESIGN.md §3): sem radius, sem borda individual, sem sombra, sem `gap` — o
 * que separa é a régua vertical de 1px, a mesma das colunas da tabela que vem
 * logo abaixo. É essa rima que faz o topo e a tabela lerem-se como um
 * instrumento só.
 *
 * ## Dois campos para toda a gente, quatro para quem vê euros
 *
 * A fornada e a contagem de ingredientes são **o produto** e chegam aos três
 * papéis; os dois custos têm a chave ausente para o `staff` e o campo
 * desaparece com ela. A régua empacota à esquerda e não estica (é o que o
 * `regua-de-contadores.tsx` existe para garantir), logo dois campos numa casa e
 * quatro noutra não precisam de duas grelhas — é a mesma faixa com menos
 * células.
 *
 * ## A certeza não é um campo da régua
 *
 * A figura de um campo é **mono e numérica** por desenho, e "Estimado" não é um
 * número. A palavra vive na frase por baixo (`FraseDoCusto`), onde cabe a
 * cobertura ao lado — e é lá que ela chega aos três papéis, porque o
 * `cost_status` e o `ingredients_without_cost` não são euros.
 */
export function NumerosDaFicha({ receita }: { readonly receita: ReceitaResumo }) {
  const comEuros = fichaMostraEuros(receita);
  // A forma do ledger ao lado da de apresentação, e só quando diferem: "2,4 kg"
  // com "= 2 400 g" por baixo é o que impede o cozinheiro de ler 2400 onde
  // escreveu 2,4 — e com `un` as duas são a mesma frase duas vezes.
  const mostraBase = receita.batch_size.display_unit !== receita.batch_size.base_unit;

  return (
    <ReguaDeContadores>
      <div className={CLASSE_CONTADOR}>
        <CorpoDoContador
          campo={textos.ficha.campoFornada}
          figura={textoDeQuantidade(receita.batch_size)}
          {...(mostraBase
            ? { nota: textos.ficha.notaDaBase(textoNaUnidadeBase(receita.batch_size)) }
            : {})}
        />
      </div>

      <div className={CLASSE_CONTADOR}>
        <CorpoDoContador
          campo={textos.ficha.campoIngredientes}
          figura={String(receita.line_count)}
        />
      </div>

      {comEuros ? (
        <>
          <div className={CLASSE_CONTADOR}>
            <CorpoDoContador
              campo={textos.ficha.campoCustoDaFornada}
              figura={
                receita.batch_cost === null || receita.batch_cost === undefined
                  ? textos.custo.semValor
                  : formatMoney(receita.batch_cost)
              }
            />
          </div>
          {/* A pergunta do dono, por extenso: "quanto me custa **um pastel**".
              Um pastel é uma unidade de **apresentação**, e o `display_cost` vem
              pronto do servidor — multiplicar o `unit_cost` pelo
              `display_factor` aqui era a conversão no cliente que a casa
              proíbe. */}
          <div className={CLASSE_CONTADOR}>
            <CorpoDoContador
              campo={textos.ficha.campoCustoUnitario(receita.display_unit)}
              figura={
                receita.display_cost === null || receita.display_cost === undefined
                  ? textos.custo.semValor
                  : formatUnitMoney(receita.display_cost)
              }
            />
          </div>
        </>
      ) : null}
    </ReguaDeContadores>
  );
}

/**
 * A frase do custo: **as três palavras da casa** e a cobertura.
 *
 * Aqui a palavra aparece sempre — incluindo o `conhecido` —, e isso é o
 * contrário do que a coluna da tabela faz de propósito. Numa coluna de quinze
 * linhas o estado saudável é silêncio visual, para o que está mal saltar; nesta
 * frase a palavra **é** a frase, e deixá-la em branco daria "Custo de
 * ingredientes: todos os ingredientes têm custo" sem dizer com que certeza. São
 * dois papéis diferentes para a mesma informação, e é por isso que estão
 * escritos nos dois sítios em vez de partilharem um componente que teria de
 * escolher um dos dois.
 *
 * Chega aos **três papéis**: o `cost_status` e o `ingredients_without_cost` são
 * qualidade de dados e contagem, não euros. É o que o `staff` lê em vez do
 * número — e é informação a sério, não um consolo: diz-lhe que a ficha está
 * incompleta e quantos ingredientes faltam preencher.
 */
export function FraseDoCusto({ receita }: { readonly receita: ReceitaResumo }) {
  return (
    <p className="border-b border-border px-celula-x py-2 text-sm">
      <span className="text-muted-foreground">{textos.custo.rotulo}</span>{" "}
      <span className={tintaDoTextoDoCusto(receita.cost_status)}>
        {palavraDoCusto(receita.cost_status)}
      </span>{" "}
      <span aria-hidden="true" className="text-muted-foreground">·</span>{" "}
      <span className="text-muted-foreground">
        {fraseDaCobertura(
          receita.cost_status,
          receita.ingredients_without_cost,
          receita.line_count,
        )}
      </span>
    </p>
  );
}

/**
 * O pendente da régua: as mesmas duas células e a mesma altura, para a faixa não
 * saltar quando os dados chegarem. **Sem** as de euros, pela mesma razão do
 * esqueleto da tabela — antes da resposta o cliente não sabe quem vê dinheiro, e
 * dois campos que desaparecessem eram um salto maior do que dois que aparecem.
 */
export function EsqueletoDosNumerosDaFicha() {
  return (
    <ReguaDeContadores aria-busy="true" rotulo={textos.ficha.numeros}>
      {[0, 1].map((indice) => (
        <div key={indice} className={CLASSE_CONTADOR}>
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-8 w-28" />
        </div>
      ))}
    </ReguaDeContadores>
  );
}
