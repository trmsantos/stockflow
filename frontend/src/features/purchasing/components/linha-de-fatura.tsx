import {
  ArrowRight,
  CircleAlert,
  CircleCheck,
  CircleSlash,
  Recycle,
  Scale,
  Snowflake,
  Thermometer,
  TrendingUp,
} from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  formatDate,
  formatMoney,
  formatPercentChange,
  formatPercentPoints,
  formatRate,
} from "@/lib/format";

import type { LinhaDeRececao } from "../schemas";
import {
  rotuloCurtoDeValidade,
  rotuloDeValidade,
  temConversao,
  textoDaUnidadeDeCompra,
  textoDeQuantidadeDaFatura,
  textoNaUnidadeBase,
} from "../vocabulario";

/**
 * Uma linha de fatura — o objeto que este ecrã existe para rever, e por isso o
 * componente mais denso do shell.
 *
 * Mostra, por esta ordem, o que o guião §1 manda ter à vista:
 *
 *  1. **a descrição da fatura → o artigo do catálogo.** As duas, lado a lado,
 *     porque é essa tradução que se está a confirmar. A descrição fica em mono e
 *     em maiúsculas como os sistemas a imprimem — é o que ele vai comparar com o
 *     papel;
 *  2. **a quantidade na unidade de compra → a quantidade na unidade de stock,
 *     com a conversão à vista**: "1 caixa 12×1 L → 12 000 ml". O lado direito
 *     está na unidade **base**, que é a do ledger, e não em kg nem em L: o que a
 *     linha afirma é exactamente o número que vai entrar;
 *  3. **o preço unitário e a taxa de IVA como vêm na linha.** A taxa é dado do
 *     documento e nunca é deduzida do artigo — muda entre o Continente e as
 *     Regiões Autónomas, e é por isso que vive na linha;
 *  4. **o lote e a validade**, que são a única parte que não se extrai de
 *     documento nenhum: estão na embalagem. É aqui que a revisão humana
 *     acontece, e é por isso que esta é a única parte editável do ecrã.
 *
 * O que **não** está aqui: nenhuma percentagem de confiança, nenhum "lido
 * automaticamente", nenhuma menção a extração. Uma linha ou precisa de revisão
 * ou está revista, e quem a reviu assina com nome e hora. Dar um número de
 * confiança punha a conversa na percentagem em vez de no fluxo (guião §4, nº 10).
 */

/**
 * Um código de lote como vem impresso numa embalagem: letras, dígitos, hífenes,
 * pontos, barras e espaços, até 40 caracteres. Não se normaliza nem se força
 * maiúsculas — o que está na embalagem é o que tem de ficar registado, porque é
 * por ele que se responde a uma recolha.
 */
const LOTE_VALIDO = /^[\w\-./ ]{1,40}$/;

function Etiquetas({ linha }: { readonly linha: LinhaDeRececao }) {
  const etiquetas = [];

  if (linha.kind === "deposit") {
    etiquetas.push(
      <Badge key="tara" className="bg-surface-2 text-foreground">
        <Recycle aria-hidden="true" />
        vasilhame — não é stock
      </Badge>,
    );
  }
  if (linha.kind === "charge") {
    etiquetas.push(
      <Badge key="encargo" className="bg-surface-2 text-foreground">
        encargo — não é stock
      </Badge>,
    );
  }
  if (linha.conservation === "frozen") {
    etiquetas.push(
      <Badge key="frio" className="bg-surface-2 text-muted-foreground">
        <Snowflake aria-hidden="true" />
        congelado
      </Badge>,
    );
  }
  if (linha.conservation === "chilled") {
    etiquetas.push(
      <Badge key="refrigerado" className="bg-surface-2 text-muted-foreground">
        <Thermometer aria-hidden="true" />
        refrigerado
      </Badge>,
    );
  }
  if (linha.variable_weight) {
    etiquetas.push(
      <Badge key="peso" className="bg-surface-2 text-muted-foreground">
        <Scale aria-hidden="true" />
        peso variável
      </Badge>,
    );
  }

  if (etiquetas.length === 0) return null;
  return <span className="flex flex-wrap items-center gap-1.5">{etiquetas}</span>;
}

/**
 * A divergência entre o que a fatura cobra e o que entrou — a **receção
 * parcial**, representada sem encomenda nenhuma.
 *
 * Aviso suave e no fluxo: cinco rolos faturados, três entregues, e a fatura
 * cobra cinco. Não há nada a corrigir no ecrã; há uma conversa a ter com o
 * fornecedor, e o que o ecrã faz é dar-lhe o número.
 */
function Parcial({ linha }: { readonly linha: LinhaDeRececao }) {
  if (Number(linha.quantity_invoiced) === Number(linha.quantity_received)) return null;

  return (
    <span className="flex flex-wrap items-center gap-x-1.5 text-xs text-warning">
      <CircleAlert aria-hidden="true" className="size-3.5 shrink-0" />
      <span>
        faturados{" "}
        <span data-numeric>
          {textoDeQuantidadeDaFatura(linha.quantity_invoiced, linha.invoice_unit)}
        </span>
        , entraram{" "}
        <span data-numeric>
          {textoDeQuantidadeDaFatura(linha.quantity_received, linha.invoice_unit)}
        </span>
        {" — a fatura cobra os que faturou"}
      </span>
    </span>
  );
}

/** O preço contra o das últimas compras. Aviso suave, com o limiar à vista. */
function Preco({ linha }: { readonly linha: LinhaDeRececao }) {
  const historico = linha.price_history;
  if (historico === null) return null;

  const subiu = historico.change_pct > 0;

  return (
    <span className={`flex flex-wrap items-center gap-x-1.5 text-xs ${subiu ? "text-warning" : "text-success"}`}>
      <TrendingUp aria-hidden="true" className="size-3.5 shrink-0" />
      <span>
        <span data-numeric>{formatPercentChange(historico.change_pct)}</span>{" "}
        {subiu ? "acima" : "abaixo"} das últimas compras (
        <span data-numeric>{formatMoney(historico.last_price)}</span>/{historico.unit_label} em{" "}
        {historico.reference}) · aviso acima de{" "}
        <span data-numeric>{formatPercentPoints(historico.threshold_pct)}</span>
      </span>
    </span>
  );
}

/** O lote e a validade já escritos. Com a distinção que a lei faz, em texto. */
function LoteEValidade({ linha }: { readonly linha: LinhaDeRececao }) {
  if (linha.lot_code === null && linha.expires_at === null) return null;

  return (
    <span className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
      {linha.lot_code === null ? null : (
        <span>
          lote <span data-numeric>{linha.lot_code}</span>
        </span>
      )}
      {linha.expires_at === null ? null : (
        <span title={linha.expiry_kind === null ? undefined : rotuloDeValidade(linha.expiry_kind)}>
          {"· "}
          {linha.expiry_kind === null ? "validade" : rotuloCurtoDeValidade(linha.expiry_kind)}{" "}
          <span data-numeric>{formatDate(linha.expires_at)}</span>
        </span>
      )}
    </span>
  );
}

interface Erros {
  readonly lote?: string;
  readonly validade?: string;
}

/**
 * O formulário de revisão de uma linha: lote e validade, label acima e erro
 * abaixo em texto (DESIGN.md §3).
 *
 * Os dois campos aparecem **só** quando o artigo os exige, e é o servidor que o
 * diz (`requires_lot`): pedir um lote de um saco de açúcar seria fricção sem
 * razão, e não pedir um de bacalhau seria perder a rastreabilidade que a lei
 * obriga em produto de origem animal.
 */
function FormularioDeLinha({
  linha,
  aRevisar,
  aoConfirmar,
}: {
  readonly linha: LinhaDeRececao;
  readonly aRevisar: boolean;
  readonly aoConfirmar: (lote: string | undefined, validade: string | undefined) => void;
}) {
  const idLote = useId();
  const idValidade = useId();
  const idErroDeLote = useId();
  const idErroDeValidade = useId();
  const [erros, setErros] = useState<Erros>({});

  function aoSubmeter(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const dados = new FormData(evento.currentTarget);
    // `FormData.get` devolve `string | File | null`; o `typeof` é o que
    // distingue, e é o mesmo padrão dos formulários do módulo `inventory`.
    const escritoNoLote = dados.get("lote");
    const escritoNaValidade = dados.get("validade");
    const lote = (typeof escritoNoLote === "string" ? escritoNoLote : "").trim();
    const validade = (typeof escritoNaValidade === "string" ? escritoNaValidade : "").trim();

    if (!linha.requires_lot) {
      setErros({});
      aoConfirmar(undefined, undefined);
      return;
    }

    const problemas: Erros = {
      ...(LOTE_VALIDO.test(lote)
        ? {}
        : { lote: "Escreva o lote que está na embalagem, como está impresso." }),
      ...(validade === "" ? { validade: "Escreva a validade da embalagem." } : {}),
    };
    setErros(problemas);
    if (problemas.lote !== undefined || problemas.validade !== undefined) return;

    aoConfirmar(lote, validade);
  }

  return (
    <form onSubmit={aoSubmeter} className="flex flex-col gap-2 pt-1">
      {linha.requires_lot ? (
        <div className="flex flex-wrap items-start gap-2">
          <div className="flex min-w-32 flex-1 flex-col gap-1">
            <Label htmlFor={idLote} className="text-xs">
              Lote
            </Label>
            <Input
              id={idLote}
              name="lote"
              type="text"
              autoComplete="off"
              spellCheck={false}
              maxLength={40}
              defaultValue={linha.lot_code ?? ""}
              placeholder="como está na embalagem"
              className="font-mono"
              aria-invalid={erros.lote === undefined ? undefined : true}
              aria-describedby={erros.lote === undefined ? undefined : idErroDeLote}
            />
          </div>
          <div className="flex min-w-36 flex-1 flex-col gap-1">
            <Label htmlFor={idValidade} className="text-xs">
              {linha.expiry_kind === null
                ? "Validade"
                : `Validade (${rotuloCurtoDeValidade(linha.expiry_kind)})`}
            </Label>
            <Input
              id={idValidade}
              name="validade"
              // `type="date"` abre o seletor nativo do telemóvel e devolve
              // sempre `AAAA-MM-DD`, que é a forma do contrato. Escrever a data
              // à mão num campo de texto, em pé, é como entra um ano errado.
              type="date"
              defaultValue={linha.expires_at ?? ""}
              aria-invalid={erros.validade === undefined ? undefined : true}
              aria-describedby={erros.validade === undefined ? undefined : idErroDeValidade}
            />
          </div>
        </div>
      ) : null}

      {erros.lote === undefined ? null : (
        <p id={idErroDeLote} className="text-sm text-danger">
          {erros.lote}
        </p>
      )}
      {erros.validade === undefined ? null : (
        <p id={idErroDeValidade} className="text-sm text-danger">
          {erros.validade}
        </p>
      )}

      <Button type="submit" variant="outline" disabled={aRevisar} className="self-start">
        <CircleCheck aria-hidden="true" />
        {aRevisar ? "A guardar…" : "Confirmar linha"}
      </Button>
    </form>
  );
}

export function LinhaDeFatura({
  linha,
  aRevisar,
  erro,
  aoConfirmar,
  aoDeixarFora,
  aoVoltarARever,
}: {
  readonly linha: LinhaDeRececao;
  /** Esta linha tem um pedido a sair. */
  readonly aRevisar: boolean;
  readonly erro: string | null;
  readonly aoConfirmar: (lote: string | undefined, validade: string | undefined) => void;
  readonly aoDeixarFora: () => void;
  readonly aoVoltarARever: () => void;
}) {
  const semArtigo = linha.product === null && linha.kind === "goods";
  const porRever = linha.status === "needs_review";
  const foraDaEntrada = linha.status === "skipped";

  return (
    // O `scroll-mt-16` é o header *sticky* de 48px do shell: sem ele, o campo
    // de lote que recebe o foco pode parar debaixo dele.
    <li className="flex scroll-mt-16 flex-col gap-1 border-b border-border px-4 py-3 last:border-b-0">
      {/* A descrição **como vem na fatura**: é o que ele compara com o papel.
          Mono com `font-mono` e não com `data-numeric`, porque o atributo também
          alinha à direita — o que se quer numa coluna de números e não num
          texto. */}
      <p className="font-mono text-xs leading-snug text-muted-foreground">
        {linha.description}
      </p>

      <div className="flex items-baseline gap-3">
        <p className="flex min-w-0 flex-1 items-baseline gap-1.5">
          <ArrowRight aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
          {linha.product_name === null ? (
            <span className="min-w-0 truncate text-warning">sem artigo no catálogo</span>
          ) : (
            <span className="min-w-0 truncate font-medium">{linha.product_name}</span>
          )}
        </p>
        {linha.line_total === null ? null : (
          <span data-numeric className="shrink-0 text-sm">
            {formatMoney(linha.line_total)}
          </span>
        )}
      </div>

      {/* A conversão à vista: a língua do fornecedor à esquerda, a do ledger à
          direita. Sem conversão nenhuma (un → un) mostra-se só a quantidade. */}
      <p className="flex flex-wrap items-baseline gap-x-1.5 text-xs">
        <span data-numeric>{textoDaUnidadeDeCompra(linha)}</span>
        {linha.stock_quantity !== null && temConversao(linha) ? (
          <>
            <ArrowRight aria-hidden="true" className="size-3 shrink-0 text-muted-foreground" />
            <span data-numeric className="font-medium">
              {textoNaUnidadeBase(linha.stock_quantity)}
            </span>
          </>
        ) : null}
        {linha.unit_price === null ? (
          // A guia de remessa não traz preços, e isso não é um campo em falta: a
          // fatura vem a fim de mês.
          <span className="text-muted-foreground">· sem preço nesta guia</span>
        ) : (
          <span className="text-muted-foreground">
            {"· "}
            <span data-numeric>{formatMoney(linha.unit_price)}</span>/{linha.invoice_unit}
            {linha.vat_rate === null ? null : (
              <span title="A taxa é a que vem na linha da fatura, não é deduzida do artigo">
                {" · IVA "}
                <span data-numeric>{formatRate(linha.vat_rate)}</span>
              </span>
            )}
          </span>
        )}
        <span className="text-muted-foreground">· {linha.location.name}</span>
      </p>

      <Parcial linha={linha} />
      <Preco linha={linha} />
      <Etiquetas linha={linha} />
      <LoteEValidade linha={linha} />

      {foraDaEntrada ? (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <CircleSlash aria-hidden="true" className="size-3.5 shrink-0" />
            fica fora desta entrada — não gera movimento
          </span>
          <Button variant="ghost" disabled={aRevisar} onClick={aoVoltarARever}>
            Voltar a rever
          </Button>
        </div>
      ) : porRever && semArtigo ? (
        <div className="flex flex-col items-start gap-2 pt-1">
          <p className="text-pretty text-xs text-muted-foreground">
            A fatura traz isto e o catálogo não tem. Sem artigo não há conversão para a unidade de
            stock, por isso a linha não entra — fica fora desta entrada, ou cria-se o artigo no
            catálogo primeiro.
          </p>
          <Button variant="outline" disabled={aRevisar} onClick={aoDeixarFora}>
            <CircleSlash aria-hidden="true" />
            {aRevisar ? "A guardar…" : "Deixar fora desta entrada"}
          </Button>
        </div>
      ) : porRever ? (
        <FormularioDeLinha linha={linha} aRevisar={aRevisar} aoConfirmar={aoConfirmar} />
      ) : (
        <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <CircleCheck aria-hidden="true" className="size-3.5 shrink-0 text-success" />
          revista
          {linha.reviewed_by === null ? null : <> por {linha.reviewed_by}</>}
          {linha.movement === null ? null : <> · já no stock</>}
        </p>
      )}

      {erro === null ? null : (
        <p role="alert" className="flex items-start gap-1.5 text-sm text-danger">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span>{erro}</span>
        </p>
      )}
    </li>
  );
}
