import {
  Building2,
  ChevronsUpDown,
  CircleAlert,
  CircleCheck,
  CircleMinus,
  Clock,
  PackageOpen,
  RotateCcw,
  Search,
  Store,
  TriangleAlert,
  Truck,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate, formatDayMonth, formatDaysAway, formatMoneyRounded } from "@/lib/format";

import {
  EMPRESA,
  LIMIAR_EM_DIAS,
  LINHAS,
  LOJA,
  MENU,
  type EstadoDeLinha,
  type LinhaDeMaqueta,
  type ValidadeDeMaqueta,
} from "./dados";

/**
 * Uma fatia do ERP: barra lateral com menu agrupado, cabeçalho, barra de ecrã e
 * uma **tabela densa** de dez linhas de stock. É aqui que a densidade se vê —
 * uma paleta mostra-se num quadrado de cor, uma densidade não.
 *
 * **É uma maqueta estática.** Nada navega e nada submete: os itens de menu são
 * `<span>` dentro de uma lista e não links, os seletores de empresa e de loja
 * são texto, e o campo de procura não filtra. A alternativa — botões que não
 * fazem nada — mentia sobre o que é interactivo. O que é real é o `:hover` das
 * linhas (que não precisa de interactividade nenhuma) e o formulário da tela de
 * entrar, que recebe foco e aceita texto.
 *
 * O que vem do domínio e não da identidade, porque sobrevive a uma mudança
 * visual (ADR 0009): a ordem é a do servidor, **o pior primeiro**; o estado é um
 * veredicto e não uma comparação feita aqui; "consumir até" e "consumir de
 * preferência antes de" não se dizem com as mesmas palavras; a unidade está
 * sempre visível; as quantidades e o dinheiro são `tabular-nums` alinhados à
 * direita.
 *
 * O que vem da identidade, e é por isso que o JSX é igual nas duas rotas: a
 * altura da linha, o ar da célula, a largura e a tinta da barra lateral, o
 * fundo e a caixa do cabeçalho de coluna, as réguas verticais, o trilho da
 * linha selecionada, o raio, a sombra e a família dos algarismos. Tudo isso
 * chega por variável do invólucro (`identidades.css`).
 */

/* Três decimais, como o ledger guarda. A unidade vai na coluna ao lado, para a
 * coluna dos números ficar com largura de dígito constante — `12,500` e
 * `142,000` têm de alinhar na vírgula, e `kg` ao lado de `L` estragava isso. */
const numero = new Intl.NumberFormat("pt-PT", {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});

interface Aparencia {
  readonly rotulo: string;
  readonly tinta: string;
  readonly icone: LucideIcon;
  readonly corDoIcone: string;
}

/**
 * A cor nunca comunica sozinha: cada estado tem ícone **e** palavra. O `ok` é
 * deliberadamente cinzento — um visto verde em sete linhas é ruído, e o que o
 * dono procura de manhã são as outras três.
 */
const APARENCIA: Readonly<Record<EstadoDeLinha, Aparencia>> = {
  negativo: {
    rotulo: "Negativo",
    tinta: "bg-danger-surface text-foreground",
    icone: CircleAlert,
    corDoIcone: "text-danger",
  },
  esgotado: {
    rotulo: "Esgotado",
    tinta: "bg-danger-surface text-foreground",
    icone: CircleMinus,
    corDoIcone: "text-danger",
  },
  baixo: {
    rotulo: "Baixo",
    tinta: "bg-warning-surface text-foreground",
    icone: TriangleAlert,
    corDoIcone: "text-warning",
  },
  ok: {
    rotulo: "Suficiente",
    tinta: "bg-surface-2 text-muted-foreground",
    icone: CircleCheck,
    corDoIcone: "text-success",
  },
};

interface Leitura {
  readonly texto: string;
  readonly corDoTexto: string;
  readonly icone: LucideIcon;
  readonly corDoIcone: string;
}

function leituraDeValidade(validade: ValidadeDeMaqueta): Leitura {
  const relativo = formatDaysAway(validade.dias);

  if (validade.natureza === "consumir_ate") {
    if (validade.dias < 0) {
      return {
        texto: `expirou ${relativo}`,
        corDoTexto: "text-danger",
        icone: CircleAlert,
        corDoIcone: "text-danger",
      };
    }
    if (validade.dias === 0) {
      return {
        texto: "expira hoje",
        corDoTexto: "text-danger",
        icone: CircleAlert,
        corDoIcone: "text-danger",
      };
    }
    if (validade.dias <= LIMIAR_EM_DIAS) {
      return {
        texto: `expira ${relativo}`,
        corDoTexto: "text-warning",
        icone: Clock,
        corDoIcone: "text-warning",
      };
    }
    return {
      texto: `consumir até ${formatDayMonth(validade.data)}`,
      corDoTexto: "text-muted-foreground",
      icone: CircleCheck,
      corDoIcone: "text-success",
    };
  }

  // Durabilidade mínima: o tecto de cor é o aviso e nunca chega a vermelho.
  if (validade.dias <= LIMIAR_EM_DIAS) {
    return {
      texto: validade.dias < 0 ? `perdeu qualidade ${relativo}` : `perde qualidade ${relativo}`,
      corDoTexto: "text-warning",
      icone: Clock,
      corDoIcone: "text-warning",
    };
  }
  return {
    texto: `melhor antes de ${formatDayMonth(validade.data)}`,
    corDoTexto: "text-muted-foreground",
    icone: CircleCheck,
    corDoIcone: "text-success",
  };
}

function tituloDeValidade(validade: ValidadeDeMaqueta): string {
  const natureza =
    validade.natureza === "consumir_ate"
      ? "consumir até (limite legal)"
      : "consumir de preferência antes de (qualidade)";
  return `Lote ${validade.lote} · ${natureza} ${formatDate(validade.data)}`;
}

function CelulaDeValidade({ validade }: { readonly validade: ValidadeDeMaqueta | null }) {
  if (validade === null) {
    return <span className="text-muted-foreground">sem validade</span>;
  }
  const leitura = leituraDeValidade(validade);
  const Icone = leitura.icone;
  return (
    <span
      className={`flex min-w-0 items-center gap-1.5 ${leitura.corDoTexto}`}
      title={tituloDeValidade(validade)}
    >
      <Icone aria-hidden="true" className={`size-4 shrink-0 ${leitura.corDoIcone}`} />
      <span className="truncate">{leitura.texto}</span>
    </span>
  );
}

function BarraLateral() {
  return (
    <div
      data-barra-lateral
      className="hidden shrink-0 flex-col border-r border-border md:flex"
    >
      <div
        data-cabecalho
        translate="no"
        className="flex shrink-0 items-center border-b border-border px-4 font-heading text-lg font-semibold"
      >
        StockFlow
      </div>

      <div className="flex-1 overflow-hidden px-2 py-3">
        {MENU.map((grupo) => (
          <div key={grupo.grupo} className="mb-3">
            <p
              data-microrotulo
              className="px-2 pb-1 text-xs font-medium text-muted-foreground"
            >
              {grupo.grupo}
            </p>
            <ul className="flex flex-col">
              {grupo.itens.map((item) => (
                <li key={item.rotulo}>
                  <span
                    data-nav-activo={item.activo === true ? "" : undefined}
                    className="relative flex items-center gap-2 overflow-hidden rounded-lg px-2 py-1.5 text-sm text-muted-foreground"
                  >
                    {item.activo === true ? (
                      <span data-trilho aria-hidden="true" className="absolute inset-y-0 left-0" />
                    ) : null}
                    {item.rotulo}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {/* O seletor de **empresa** vive no pé da barra lateral e é do shell; o de
          loja vive na barra do ecrã e é do ecrã. São coisas diferentes e a ADR
          0009 separa-as de propósito. */}
      <div className="flex shrink-0 items-center gap-2 border-t border-border px-3 py-3 text-sm">
        <Building2 aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate font-medium">{EMPRESA}</span>
        <ChevronsUpDown aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
      </div>
    </div>
  );
}

function LinhaDaTabela({ linha }: { readonly linha: LinhaDeMaqueta }) {
  const aparencia = APARENCIA[linha.estado];
  const Icone = aparencia.icone;
  const negativa = linha.quantidade.startsWith("-");
  // A linha selecionada é a primeira porque a ordem é "o pior primeiro": é
  // onde o dono está quando abre o ecrã.
  const selecionada = linha === LINHAS[0];

  return (
    <tr
      data-linha
      data-selecionada={selecionada ? "" : undefined}
      className="border-b border-border transition-colors last:border-b-0 hover:bg-surface-2"
    >
      <td data-celula className="relative max-w-0 truncate font-medium">
        {selecionada ? (
          <span data-trilho aria-hidden="true" className="absolute inset-y-0 left-0" />
        ) : null}
        {linha.artigo}
      </td>
      <td data-celula className="whitespace-nowrap text-muted-foreground">
        {linha.localizacao}
      </td>
      <td
        data-celula
        data-numeric
        className={`whitespace-nowrap ${negativa ? "text-danger" : ""}`}
      >
        {numero.format(Number(linha.quantidade))}
      </td>
      <td data-celula className="whitespace-nowrap text-muted-foreground">
        {linha.unidade}
      </td>
      <td data-celula>
        <Badge data-chip className={`${aparencia.tinta} w-fit`}>
          <Icone aria-hidden="true" className={aparencia.corDoIcone} />
          {aparencia.rotulo}
        </Badge>
      </td>
      <td data-celula className="max-w-0">
        <CelulaDeValidade validade={linha.validade} />
      </td>
      <td data-celula data-numeric className="whitespace-nowrap">
        {formatMoneyRounded(linha.valor)}
      </td>
    </tr>
  );
}

const COLUNAS = [
  { rotulo: "Artigo", numerica: false },
  { rotulo: "Localização", numerica: false },
  { rotulo: "Quantidade", numerica: true },
  { rotulo: "Un.", numerica: false },
  { rotulo: "Estado", numerica: false },
  { rotulo: "Validade mais próxima", numerica: false },
  { rotulo: "Valor em stock", numerica: true },
] as const;

function TabelaDeStock() {
  return (
    <div data-painel className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">
          Níveis de stock por artigo, ordenados pelo que está pior primeiro.
        </caption>
        <thead>
          <tr className="border-b border-border">
            {COLUNAS.map((coluna) => (
              <th
                key={coluna.rotulo}
                scope="col"
                data-celula
                data-th
                data-numeric={coluna.numerica ? "" : undefined}
                // Sem `sticky` aqui, e é uma omissão e não um esquecimento: o
                // cabeçalho sticky do DESIGN.md §3 precisa do contentor de
                // scroll do produto, e esta maqueta mostra as dez linhas de uma
                // vez para a densidade se comparar de relance. O que a
                // identidade decide — a banda de cor, o peso e a caixa do
                // rótulo — está no `--id-th-*`, e o fundo é opaco nas duas
                // justamente para o sticky do produto funcionar.
                className="whitespace-nowrap text-left text-xs text-muted-foreground"
              >
                {coluna.rotulo}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {LINHAS.map((linha) => (
            <LinhaDaTabela key={linha.id} linha={linha} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Os três estados que o DESIGN.md §3 exige de tudo o que carrega dados. */
function EstadosDaTabela() {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      <div data-painel className="flex flex-col gap-2 p-4" aria-busy="true">
        <p data-microrotulo className="text-xs font-medium text-muted-foreground">
          A carregar
        </p>
        <span className="sr-only">A carregar níveis de stock…</span>
        {[0, 1, 2, 3].map((indice) => (
          <div key={indice} data-linha className="flex items-center gap-3">
            <Skeleton className="h-3 flex-1" />
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-3 w-20" />
          </div>
        ))}
      </div>

      <div data-painel className="flex flex-col items-start gap-2 p-4">
        <p data-microrotulo className="text-xs font-medium text-muted-foreground">
          Sem resultados
        </p>
        <PackageOpen aria-hidden="true" className="size-6 text-muted-foreground" />
        <p className="text-sm">Nenhum artigo corresponde a estes filtros.</p>
        <Button data-controlo type="button" variant="outline">
          <RotateCcw aria-hidden="true" />
          Limpar filtros
        </Button>
      </div>

      <div data-painel className="flex flex-col items-start gap-2 p-4" role="alert">
        <p data-microrotulo className="text-xs font-medium text-muted-foreground">
          Erro
        </p>
        <p className="flex items-start gap-1.5 text-sm text-danger">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span>Não foi possível carregar o stock. Verifique a ligação.</span>
        </p>
        <Button data-controlo type="button" variant="outline">
          <RotateCcw aria-hidden="true" />
          Tentar outra vez
        </Button>
      </div>
    </div>
  );
}

export function FatiaDeErp() {
  return (
    <div
      data-flutuante
      className="flex overflow-hidden rounded-xl border border-border bg-background"
    >
      <BarraLateral />

      <div className="flex min-w-0 flex-1 flex-col">
        {/* O cabeçalho da aplicação: onde estou, em que loja, e a ação da
            manhã. Nenhum número — os números estão na tabela. */}
        <header
          data-cabecalho
          className="flex shrink-0 items-center gap-3 border-b border-border bg-surface px-4"
        >
          <h3 className="font-heading text-lg font-semibold">Stock</h3>
          <span className="flex min-w-0 items-center gap-1.5 text-sm text-muted-foreground">
            <Store aria-hidden="true" className="size-4 shrink-0" />
            <span className="truncate">{LOJA}</span>
            <ChevronsUpDown aria-hidden="true" className="size-4 shrink-0" />
          </span>
          <Button data-controlo type="button" className="ml-auto shrink-0">
            <Truck aria-hidden="true" />
            Receber mercadoria
          </Button>
        </header>

        {/* A barra do ecrã: procura e filtros. O estado destes controlos vive no
            URL no produto; aqui é uma fotografia. */}
        <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border bg-surface px-4 py-2">
          <span className="relative flex min-w-48 flex-1 items-center">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute left-2.5 size-4 text-muted-foreground"
            />
            <Input
              data-controlo
              type="search"
              name="q"
              // Não é um campo de autenticação: sem isto o gestor de passwords
              // oferece-se para preencher uma caixa de procura.
              autoComplete="off"
              spellCheck={false}
              className="pl-8"
              placeholder="Procurar artigo…"
              aria-label="Procurar artigo"
            />
          </span>
          <Badge data-chip className="bg-danger-surface text-foreground">
            <CircleMinus aria-hidden="true" className="text-danger" />
            Em falta 2
          </Badge>
          <Badge data-chip className="bg-warning-surface text-foreground">
            <Clock aria-hidden="true" className="text-warning" />
            A expirar 4
          </Badge>
        </div>

        <div data-ritmo className="flex flex-1 flex-col bg-background p-4">
          <TabelaDeStock />

          {/* Espaço inquebrável entre o número e o que ele conta: "10 artigos"
              não se parte no fim da linha, pela mesma razão que o `lib/format`
              usa NBSP antes da unidade. */}
          <p className="text-xs text-muted-foreground">
            <span data-numeric>{LINHAS.length}</span>&nbsp;artigos de{" "}
            <span data-numeric>148</span> · ordenados pelo que está pior primeiro
          </p>

          <EstadosDaTabela />
        </div>
      </div>
    </div>
  );
}
