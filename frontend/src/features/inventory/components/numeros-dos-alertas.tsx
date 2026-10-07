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
        figura={formatMoneyRounded(resumo.wasted_today_eur)}
        campo={textos.numeros.deitadoForaHoje}
        nota={textos.numeros.desdeAs(desde)}
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
