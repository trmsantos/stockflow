import { Link } from "@tanstack/react-router";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import {
  CLASSE_CONTADOR,
  CLASSE_CONTADOR_ATIVO,
  CLASSE_CONTADOR_TOCAVEL,
  CorpoDoContador,
  ReguaDeContadores,
} from "@/components/regua-de-contadores";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMoneyRounded, formatTime } from "@/lib/format";

import type { ResumoDeAlertas } from "../schemas";
import { textos } from "../textos";

/**
 * Os três contadores do topo dos Alertas — e a razão de este ecrã não ser três
 * ecrãs.
 *
 * "Três perguntas numa tab é o maior risco do DESIGN.md", e resolve-se com
 * **três contadores e uma só lista**: cada contador é um filtro da mesma lista,
 * no URL, logo o dono nunca tem de escolher um separador para ver o que lhe
 * interessa — toca no número e a lista por baixo passa a ser aquela.
 *
 * O terceiro contador é a sonda da Q6. A nota diz **a hora a que o dia de
 * negócio começa** — "desde as 04:00" — e a hora vem do servidor, não daqui: na
 * pastelaria a fronteira é o início da produção (~4h) e num restaurante é o fim
 * do serviço (~2h), e é essa diferença que se quer ouvir.
 *
 * Os euros aparecem **arredondados ao euro**: vêm de custos médios, e o cêntimo
 * convidaria a discutir o cêntimo em vez do desperdício (guião §4, nº 9).
 *
 * ## Eram mosaicos, e passaram a régua a 2026-10-06
 *
 * Três cartões `rounded-xl` numa `grid grid-cols-3` eram o cartão de estatística
 * que o DESIGN.md §5 proíbe quase pela letra, e eram o primeiro bloco deste
 * ecrã. A forma nova está documentada no `components/regua-de-contadores.tsx`,
 * com a razão inteira. O que mudou aqui foi só a forma: os três números, os três
 * filtros e as três sondas da sessão 0 são os mesmos.
 *
 * O limiar de dias saiu do rótulo para a nota pela mesma razão que no Stock: um
 * microrótulo em caixa alta com 24 caracteres parte em duas linhas e desalinha a
 * régua. Continua no ecrã e continua a vir do servidor.
 *
 * ## Três contadores para os três papéis, e o terceiro muda de unidade
 *
 * O `wasted_today_eur` chega **ausente** ao `staff`, como todo o dinheiro desta
 * casa (ADR 0032, decisão 1). Esconder o campo — que é o que o ecrã de Stock faz
 * com o valor de stock — aqui **não** serve: este contador e o rodapé do ecrã
 * são as **duas únicas portas** para a lista de desperdício, e a decisão 4 da
 * ADR 0034 diz expressamente que essa lista tem de chegar a quem a cria. Sem
 * ele, o `staff` ficava com dois contadores e sem caminho nenhum para a rota.
 *
 * Por isso o terceiro campo troca de unidade em vez de desaparecer: euros para
 * quem os vê, **linhas** (`wasted_today_count`) para quem não. Uma contagem não
 * reconstrói o custo unitário — um `COUNT(id)` não tem numerador nem
 * denominador — e o rótulo muda com ela, porque "deitado fora hoje: 7" seria
 * sete euros para quem leu o campo do lado.
 *
 * A **cobertura** entra na nota quando há linhas sem preço conhecido, e entra
 * para os três papéis: "7 quebras hoje" e "7 quebras hoje, 4 sem preço
 * conhecido" não são a mesma frase, e do lado dos euros é a diferença entre um
 * total e um total subestimado.
 */
export type VistaDeAlertas = "expira" | "falta" | "desperdicio" | undefined;

function ContadorDeVista({
  figura,
  campo,
  nota,
  titulo,
  ativo,
  vista,
}: {
  readonly figura: string;
  readonly campo: string;
  readonly nota?: string;
  readonly titulo: string;
  readonly ativo: boolean;
  readonly vista: "expira" | "falta" | "desperdicio";
}) {
  return (
    <Link
      to="/alertas"
      // Tocar segunda vez no mesmo contador limpa o filtro, como no ecrã de
      // Stock: o reducer recebe os filtros actuais já validados pela rota.
      search={(anteriores) => ({ ...anteriores, ver: ativo ? undefined : vista })}
      title={titulo}
      className={`${CLASSE_CONTADOR} ${CLASSE_CONTADOR_TOCAVEL} ${ativo ? CLASSE_CONTADOR_ATIVO : ""}`}
    >
      <CorpoDoContador
        campo={campo}
        figura={figura}
        ativo={ativo}
        {...(nota === undefined ? {} : { nota })}
      />
    </Link>
  );
}

export function NumerosDosAlertas({
  resumo,
  vistaAtiva,
}: {
  readonly resumo: ResumoDeAlertas;
  readonly vistaAtiva: VistaDeAlertas;
}) {
  const dias = resumo.expiring_within_days;
  const desde = resumo.business_day_starts_at;

  // A cobertura qualifica os dois casos: para quem vê euros diz que o total
  // está subestimado, para quem vê linhas diz que nem todas têm preço.
  const semPreco = resumo.wasted_today_lines_without_cost;
  const nota =
    semPreco === 0
      ? textos.numeros.desdeAs(desde)
      : textos.numeros.desdeAsSemPreco(desde, String(semPreco));

  return (
    <ReguaDeContadores>
      <ContadorDeVista
        figura={String(resumo.expiring_count)}
        campo={textos.numeros.lotesAExpirar}
        nota={textos.numeros.dentroDeDias(String(dias))}
        titulo={textos.numeros.lotesComValidade(String(dias))}
        ativo={vistaAtiva === "expira"}
        vista="expira"
      />
      <ContadorDeVista
        figura={String(resumo.missing_count)}
        campo={textos.numeros.emFalta}
        nota={textos.numeros.abaixoDoMinimo}
        titulo={textos.numeros.artigosAbaixoDoMinimoNosAlertas}
        ativo={vistaAtiva === "falta"}
        vista="falta"
      />
      <ContadorDeVista
        figura={
          resumo.wasted_today_eur === undefined
            ? String(resumo.wasted_today_count)
            : formatMoneyRounded(resumo.wasted_today_eur)
        }
        campo={
          resumo.wasted_today_eur === undefined
            ? textos.numeros.quebrasHoje
            : textos.numeros.deitadoForaHoje
        }
        nota={nota}
        titulo={textos.numeros.diaDeNegocio(desde, formatTime(resumo.wasted_since))}
        ativo={vistaAtiva === "desperdicio"}
        vista="desperdicio"
      />
    </ReguaDeContadores>
  );
}

/** Pendente: um aviso só, no contentor, para quem ouve o ecrã (medido no Stock). */
export function EsqueletoDosNumerosDeAlertas() {
  return (
    <ReguaDeContadores aria-busy="true" rotulo={textos.numeros.aCarregar}>
      {[0, 1, 2].map((indice) => (
        <div key={indice} className={CLASSE_CONTADOR}>
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-8 w-16" />
        </div>
      ))}
    </ReguaDeContadores>
  );
}

export function ErroDosNumerosDeAlertas({
  aoTentarOutraVez,
}: {
  readonly aoTentarOutraVez: () => void;
}) {
  return (
    <div className="border-b border-border px-celula-x py-3">
      <ErroAoCarregar
        titulo={textos.numeros.erroDeAlertasTitulo}
        mensagem={textos.numeros.erroDeAlertasCorpo}
        aoTentarOutraVez={aoTentarOutraVez}
      />
    </div>
  );
}
