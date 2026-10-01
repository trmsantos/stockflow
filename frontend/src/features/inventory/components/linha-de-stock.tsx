import { Link } from "@tanstack/react-router";

import type { NivelDeStock } from "../schemas";
import { textoDeQuantidade } from "../vocabulario";
import { BadgeDeEstado } from "./badge-de-estado";
import { TextoDeValidade } from "./validade";

/**
 * Uma linha do ecrã Stock: **quatro dados e nunca mais** (guião da sessão 0,
 * §1) — nome curto, quantidade com unidade, badge de estado, validade mais
 * próxima. 56px de altura mínima, que é um alvo de toque confortável e o que faz
 * caberem sete linhas nos ~530px úteis de um 360×640.
 *
 * **Não há aqui campo de quantidade editável, e isso é a decisão mais
 * importante do ecrã.** Nem stepper, nem input, nem toque-para-editar no
 * "3,4 kg": stock é um ledger, corrige-se com um movimento e não com um lápis. A
 * linha inteira é um `<Link>` para o detalhe — tocar no número leva ao histórico
 * e à ação de registar desperdício, que é o sítio certo. Ser um link e não um
 * `div` com `onClick` dá de graça o Cmd+clique, o clique do meio e o teclado.
 *
 * `search={true}` mantém os filtros no URL ao abrir o detalhe: é assim que o
 * link de voltar devolve a lista exactamente como estava, sem depender do
 * histórico do browser.
 */
export function LinhaDeStock({
  nivel,
  limiarEmDias,
}: {
  readonly nivel: NivelDeStock;
  readonly limiarEmDias: number;
}) {
  // A única cor que a quantidade recebe, e vem do veredicto do servidor: um
  // negativo lê-se a vermelho (a sonda da Q1). O texto do badge ao lado diz
  // "Negativo", logo a cor não está sozinha.
  const corDaQuantidade = nivel.status === "negativo" ? "text-danger" : "";

  // O stock repartido por localização — a parte operacional da Q2. Não é um
  // quinto dado: é o **mesmo** dado (a quantidade) decomposto, e só aparece
  // quando há mais de uma localização, ou seja numa ou duas linhas da lista.
  const repartido = nivel.by_location.length > 1;

  return (
    <Link
      to="/stock/$artigo"
      params={{ artigo: nivel.product }}
      search={true}
      // O `scroll-mt-24` existe por causa da barra *sticky* do topo: sem ele, a
      // linha que recebe o foco por teclado pode ficar debaixo dela.
      className="flex min-h-14 scroll-mt-24 flex-col justify-center gap-1 border-b border-border px-4 py-2 transition-colors hover:bg-surface-2"
    >
      <span className="flex items-baseline gap-3">
        <span className="min-w-0 flex-1 truncate font-medium">{nivel.short_name}</span>
        <span data-numeric className={`shrink-0 text-sm ${corDaQuantidade}`}>
          {textoDeQuantidade(nivel.quantity)}
        </span>
      </span>

      <span className="flex items-center gap-2 text-xs">
        <BadgeDeEstado estado={nivel.status} />
        <TextoDeValidade validade={nivel.nearest_expiry} limiarEmDias={limiarEmDias} />
      </span>

      {repartido ? (
        <span className="truncate text-xs text-muted-foreground">
          {nivel.by_location.map((parcela, indice) => (
            <span key={parcela.location.id}>
              {indice === 0 ? "" : " · "}
              {parcela.location.name} <span data-numeric>{textoDeQuantidade(parcela.quantity)}</span>
            </span>
          ))}
        </span>
      ) : null}
    </Link>
  );
}
