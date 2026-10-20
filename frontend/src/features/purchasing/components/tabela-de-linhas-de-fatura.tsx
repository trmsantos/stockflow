import { Link } from "@tanstack/react-router";
import { useId, useState, type FormEvent } from "react";

import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  EsqueletoDeTabela,
  MolduraDeTabela,
  TrilhoDaLinha,
  type ColunaDeTabela,
} from "@/components/tabela";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  formatDate,
  formatMoney,
  formatPercentChange,
  formatPercentPoints,
  formatRate,
  formatTime,
} from "@/lib/format";

import type { LinhaDeRececao } from "../schemas";
import { textos } from "../textos";
import { tintaDoTextoDoEstado, tintaDoTrilhoDoEstado } from "../tinta-do-estado";
import {
  rotuloCurtoDeValidade,
  rotuloDeConservacao,
  rotuloDeEspecie,
  rotuloDeEstadoDeLinha,
  rotuloDeValidade,
  temConversao,
  textoDaUnidadeDeCompra,
  textoDeQuantidadeDaFatura,
  textoNaUnidadeBase,
} from "../vocabulario";

/**
 * As linhas de um documento, como tabela densa — e é a tabela mais difícil do
 * repositório, porque metade dela é **leitura** e a outra metade é um
 * **formulário**.
 *
 * ## O que isto substitui, e o que não mudou
 *
 * Era `linha-de-fatura.tsx`: um `<li>` por linha com até sete filas de texto
 * empilhadas, dentro de uma coluna de `max-w-2xl`. Cada fila juntava factos
 * diferentes com pontos médios — "1 caixa 12×1 L → 12 000 ml · 44,50 €/saco ·
 * IVA 23 % · Cozinha" — e três filas eram badges da Lucide: `Snowflake`
 * congelado, `Scale` peso variável, `Recycle` vasilhame. Para comparar o preço
 * de duas linhas era preciso ler as duas frases inteiras e encontrar o número no
 * meio.
 *
 * O que **não** mudou é o que o ecrã afirma: a extração não gera movimentos, a
 * confirmação humana gera. Continua a não haver percentagens de confiança nem
 * menção a extração; uma linha ou precisa de revisão ou está revista, e quem a
 * reviu assina com nome e hora.
 *
 * ## A parte que é formulário continua a ser um formulário
 *
 * Escrever o lote e a validade é a única coisa que esta feature **escreve**, e é
 * um `<form>` com label acima e erro abaixo em texto (DESIGN.md §3). Um
 * formulário não se achata numa célula de 44px: campos de texto dentro de uma
 * grelha densa dão uma folha de cálculo, e o CLAUDE.md é explícito — stock é um
 * ledger, nada se edita no lugar. Por isso o formulário vive numa **linha
 * expansível** (um `<tr>` com `colSpan`), aberta por um botão na coluna de
 * acção, uma de cada vez. É a mesma mecânica do painel de motivos do ecrã
 * Alertas, e a mesma razão: o segundo toque é que escreve.
 *
 * ## Porque é que **todas** as linhas têm botão, ao contrário dos Alertas
 *
 * Nos Alertas o botão só existe nas linhas em que faz efeito — não se deita fora
 * o que não há, logo uma falta não tem botão. Aqui a conta dá outro resultado: o
 * painel de uma linha não é só o formulário, é o **dossier** dela (o que a
 * fatura cobra, a taxa de IVA da linha, o que foi faturado contra o que entrou, a
 * conversão por extenso, a conservação, quem reviu e a que horas). Uma linha já
 * revista continua a ter dossier, e esconder-lho obrigava a tirar o total da
 * linha e a taxa de IVA de uma tabela que já não tem largura para eles. Por isso
 * o botão diz "Rever" onde há o que escrever e "Ver" onde já não há — o que não
 * existe em nenhuma linha é um botão `disabled`, que numa tabela densa é uma
 * pergunta por linha.
 *
 * ## O que ficou de fora das colunas, e porquê
 *
 * **O total da linha e a taxa de IVA** estão numa coluna só ("Valor") e no
 * dossier: a taxa é um de três valores legais e não é número que se compare de
 * linha em linha — o que se compara são os preços —, e o rodapé do documento
 * continua a dar a base e o IVA **por taxa**, como está impresso.
 *
 * **A localização da linha** não tem coluna: num documento de cinco linhas ela
 * costuma ser a mesma em todas, e uma coluna constante é ruído. Onde a divisão
 * importa é no resumo do que entra no stock, logo abaixo da tabela, que já diz
 * "12 000 ml de Nata em Cozinha" linha a linha.
 *
 * **A `position`** não tem coluna porque **é** a ordem das linhas: o servidor
 * devolve-as na ordem em que estão impressas no documento, e numerá-las outra vez
 * ao lado era repetir a mesma informação em algarismos.
 */

/**
 * Um código de lote como vem impresso numa embalagem: letras, dígitos, hífenes,
 * pontos, barras e espaços, até 40 caracteres. Não se normaliza nem se força
 * maiúsculas — o que está na embalagem é o que tem de ficar registado, porque é
 * por ele que se responde a uma recolha.
 */
const LOTE_VALIDO = /^[\w\-./ ]{1,40}$/;

/**
 * As colunas. Todas menos o artigo levam largura escrita, que é a distribuição
 * que o ecrã de Alertas chegou a medir num screenshot: sem larguras declaradas
 * o layout automático dá espaço a quem tem o conteúdo mais largo, e numa coluna
 * numérica o conteúdo mais largo é o **cabeçalho** em caixa alta.
 *
 * A conta com euros (soma do que está declarado abaixo): o trilho e as sete
 * fixas somam 836px, logo a 1280px, onde a área de conteúdo tem ~1024px, o
 * artigo fica com ~190px e trunca nomes longos; a 1440px fica com ~350px.
 * Truncar o nome é o preço de ter o lote, a validade e o dinheiro à vista ao
 * mesmo tempo; o nome completo está no `title` do link, a descrição da fatura
 * por extenso está no dossier, e a sidebar do shell colapsa quando o documento
 * é grande.
 *
 * As duas alternativas foram rejeitadas: esconder colunas a 1280 (a coluna que
 * se esconde é sempre a que faltava) e deixar a tabela deslizar na horizontal no
 * portátil obrigatório do §4.
 *
 * ## **Oito colunas com euros, sete sem eles**, e a que falta é a coluna inteira
 *
 * Quem não vê dinheiro não recebe a coluna "Valor": uma coluna cheia de "—", ou
 * de "0,00 €", lê-se como uma fatura **sem preços**, que é uma mentira sobre o
 * documento que ele tem na mão. A ausência não tem essa leitura — é o mesmo
 * reflexo com que o servidor tira a chave do JSON em vez de a pôr a zero.
 *
 * E não fica buraco nenhum, pela conta acima: o artigo é a única coluna
 * flexível, logo os 144px do `w-36` passam **para ela** — que é exactamente a
 * que truncava nomes a 1280px. A tabela sem euros é mais larga onde precisava
 * de ser, não mais estreita.
 */
function colunasDasLinhas(comEuros: boolean): readonly ColunaDeTabela[] {
  return [
    // Medido a 1280px: com o `Recebido` a `w-32` e a validade a forçar 152px, esta
    // coluna ficava com 159px (126 úteis) e truncava "Nata para bater 35% UHT 1L",
    // que precisa de 192. O `Recebido` desceu a `w-28` (o cabeçalho "RECEBIDO" em
    // caixa alta precisa de 110 e tem 112) e a validade encurtou o seu rótulo.
    { chave: "artigo", rotulo: textos.linhas.colunas.artigo },
    { chave: "recebido", rotulo: textos.linhas.colunas.recebido, classe: "w-28 text-right" },
    { chave: "stock", rotulo: textos.linhas.colunas.stock, classe: "w-28 text-right" },
    ...(comEuros
      ? [{ chave: "valor", rotulo: textos.linhas.colunas.valor, classe: "w-36 text-right" }]
      : []),
    { chave: "lote", rotulo: textos.linhas.colunas.lote, classe: "w-28" },
    { chave: "validade", rotulo: textos.linhas.colunas.validade, classe: "w-32" },
    { chave: "estado", rotulo: textos.linhas.colunas.estado, classe: "w-28" },
    { chave: "accao", rotulo: textos.linhas.colunas.accao, classe: "w-24" },
  ];
}

const LARGURA_MINIMA = "min-w-5xl";
const ROTULO = textos.linhas.tabela;

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
      ...(LOTE_VALIDO.test(lote) ? {} : { lote: textos.formularios.escrevaOLote }),
      ...(validade === "" ? { validade: textos.formularios.escrevaAValidade } : {}),
    };
    setErros(problemas);
    if (problemas.lote !== undefined || problemas.validade !== undefined) return;

    aoConfirmar(lote, validade);
  }

  return (
    <form onSubmit={aoSubmeter} className="flex flex-col gap-2">
      {linha.requires_lot ? (
        <div className="flex flex-wrap items-start gap-2">
          <div className="flex w-full max-w-48 flex-col gap-1">
            {/* O rótulo do campo é o da coluna: é o mesmo campo, e duas chaves
                para a mesma palavra divergiam na primeira tradução. */}
            <Label htmlFor={idLote} className="text-xs">
              {textos.linhas.colunas.lote}
            </Label>
            <Input
              id={idLote}
              name="lote"
              type="text"
              autoComplete="off"
              spellCheck={false}
              maxLength={40}
              defaultValue={linha.lot_code ?? ""}
              placeholder={textos.linhas.lotePlaceholder}
              className="font-mono"
              aria-invalid={erros.lote === undefined ? undefined : true}
              aria-describedby={erros.lote === undefined ? undefined : idErroDeLote}
            />
          </div>
          <div className="flex w-full max-w-48 flex-col gap-1">
            <Label htmlFor={idValidade} className="text-xs">
              {linha.expiry_kind === null
                ? textos.linhas.colunas.validade
                : textos.linhas.validadeCom(rotuloCurtoDeValidade(linha.expiry_kind))}
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
        {aRevisar ? textos.comuns.aGuardar : textos.linhas.confirmarLinha}
      </Button>
    </form>
  );
}

/**
 * O dossier da linha: as frases que não caberiam numa célula de 44px, e que é
 * por existirem aqui que a tabela pode ter oito colunas em vez de treze.
 *
 * Em frases e não em etiquetas, de propósito. Eram seis badges com ícones da
 * Lucide — floco de neve, balança, reciclagem — e cada um dizia em desenho o que
 * a palavra ao lado dizia em texto. O DESIGN.md §5 nomeia isso ("três colunas de
 * features com ícones da Lucide todos da mesma cor") e a regra de "nunca só a
 * cor" é cumprida pela palavra, nunca foi pelo ícone.
 */
function DossierDaLinha({ linha }: { readonly linha: LinhaDeRececao }) {
  // `?? null` junta as duas ausências **neste** sítio de propósito: quem não vê
  // euros não vê a variação contra as últimas compras, e quem vê mas não tem
  // histórico também não. A frase que falta é a mesma, e não há uma terceira a
  // escrever — a razão de não haver preços está dita no rodapé do documento.
  const historico = linha.price_history ?? null;
  const parcial = Number(linha.quantity_invoiced) !== Number(linha.quantity_received);

  return (
    <div className="flex flex-col gap-1 text-sm">
      {/* A descrição **como vem na fatura**, por extenso e sem truncar: é o que
          ele compara com o papel. Mono com `font-mono` e não com `data-numeric`,
          porque o atributo também alinha à direita. */}
      <p className="font-mono text-xs leading-snug text-muted-foreground">{linha.description}</p>

      {linha.stock_quantity !== null && temConversao(linha) ? (
        <p className="text-muted-foreground">
          <span data-numeric>{textoDaUnidadeDeCompra(linha)}</span>{" "}
          {textos.linhas.conversaoMeio}{" "}
          <span data-numeric>{textoNaUnidadeBase(linha.stock_quantity)}</span>{" "}
          {textos.linhas.conversaoFim}
        </p>
      ) : null}

      {linha.unit_price === null ? (
        // A guia de remessa não traz preços, e isso não é um campo em falta: a
        // fatura vem a fim de mês.
        <p className="text-muted-foreground">{textos.linhas.guiaSemPrecos}</p>
      ) : (
        // **A mesma frase, com menos factos** quando os euros não vêm: "A
        // fatura cobra 50 un, com IVA de 23 %". A quantidade faturada, a
        // unidade impressa e a taxa continuam a ser dela — a taxa é 6, 13 ou 23
        // e está em qualquer talão. O que sai é o preço e o total da linha, e
        // sai sem deixar um buraco no meio da frase.
        <p className="text-muted-foreground">
          {textos.linhas.aFaturaCobra}{" "}
          <span data-numeric>
            {textoDeQuantidadeDaFatura(linha.quantity_invoiced, linha.invoice_unit)}
          </span>
          {linha.unit_price === undefined ? null : (
            <>
              {" "}
              {textos.linhas.aoPreco} <span data-numeric>{formatMoney(linha.unit_price)}</span>/
              {linha.invoice_unit}
            </>
          )}
          {linha.vat_rate === null ? null : (
            <>
              {textos.linhas.comIvaDe}{" "}
              <span data-numeric>{formatRate(linha.vat_rate)}</span>
              {textos.linhas.taxaDaLinha}
            </>
          )}
          {linha.line_total === null || linha.line_total === undefined ? null : (
            <>
              {textos.linhas.totalDaLinha}{" "}
              <span data-numeric>{formatMoney(linha.line_total)}</span>
            </>
          )}
          .
        </p>
      )}

      {parcial ? (
        // A receção parcial, representada sem encomenda nenhuma: a divergência é
        // entre o documento e a prateleira. Não há nada a corrigir no ecrã; há
        // uma conversa a ter com o fornecedor, e o ecrã dá-lhe o número.
        <p className="text-warning">
          {textos.linhas.faturadosInicio}{" "}
          <span data-numeric>
            {textoDeQuantidadeDaFatura(linha.quantity_invoiced, linha.invoice_unit)}
          </span>
          {textos.linhas.faturadosMeio}{" "}
          <span data-numeric>
            {textoDeQuantidadeDaFatura(linha.quantity_received, linha.invoice_unit)}
          </span>
          {textos.linhas.faturadosFim}
        </p>
      ) : null}

      {historico === null ? null : (
        <p className={historico.change_pct > 0 ? "text-warning" : "text-success"}>
          <span data-numeric>{formatPercentChange(historico.change_pct)}</span>{" "}
          {historico.change_pct > 0 ? textos.linhas.acima : textos.linhas.abaixo}{" "}
          {textos.linhas.dasUltimasCompras} (
          <span data-numeric>{formatMoney(historico.last_price)}</span>/{historico.unit_label}{" "}
          {textos.linhas.historicoEm} {historico.reference}).{" "}
          {textos.linhas.oAvisoApareceAcimaDe}{" "}
          {/* O limiar entra na frase, que é onde ele se contesta em voz alta: um
              painel de limiares está proibido (guião §4, nº 7). */}
          <span data-numeric>{formatPercentPoints(historico.threshold_pct)}</span>.
        </p>
      )}

      {/* As frases do catálogo acabam em espaço de propósito: só aparecem quando
          a linha as tem, e a que vem depois encosta-se-lhe. */}
      <p className="text-muted-foreground">
        {linha.kind === "deposit" ? textos.linhas.vasilhame : ""}
        {linha.kind === "charge" ? textos.linhas.encargo : ""}
        {linha.conservation === "ambient"
          ? null
          : textos.linhas.conservaSe(rotuloDeConservacao(linha.conservation))}
        {linha.variable_weight ? textos.linhas.pesoVariavel : ""}
        {linha.expires_at === null || linha.expiry_kind === null
          ? null
          : textos.linhas.aValidadeDestaLinha(rotuloDeValidade(linha.expiry_kind))}
        {textos.linhas.entraEm(linha.location.name)}
      </p>

      {linha.reviewed_by === null ? null : (
        <p className="text-muted-foreground">
          {textos.linhas.revistaPor(linha.reviewed_by)}
          {linha.reviewed_at === null ? null : (
            <>
              {" "}
              {textos.comuns.as} <span data-numeric>{formatTime(linha.reviewed_at)}</span>
            </>
          )}
          {linha.movement === null
            ? textos.linhas.semMovimentoAinda
            : textos.linhas.jaEstaNoStock}
        </p>
      )}
    </div>
  );
}

function LinhaDeFatura({
  linha,
  colunas,
  comEuros,
  aberto,
  aoAlternar,
  aRevisar,
  erro,
  idDoPainel,
  aoConfirmar,
  aoDeixarFora,
  aoVoltarARever,
}: {
  readonly linha: LinhaDeRececao;
  /** As colunas desta tabela — sete ou oito. O painel abre com o `colSpan` delas. */
  readonly colunas: readonly ColunaDeTabela[];
  /** Este documento trouxe euros. Decide a coluna "Valor", não o conteúdo dela. */
  readonly comEuros: boolean;
  readonly aberto: boolean;
  readonly aoAlternar: () => void;
  /** Esta linha tem um pedido a sair. */
  readonly aRevisar: boolean;
  readonly erro: string | null;
  readonly idDoPainel: string;
  readonly aoConfirmar: (lote: string | undefined, validade: string | undefined) => void;
  readonly aoDeixarFora: () => void;
  readonly aoVoltarARever: () => void;
}) {
  const semArtigo = linha.product === null && linha.kind === "goods";
  const porRever = linha.status === "needs_review";
  const foraDaEntrada = linha.status === "skipped";
  const parcial = Number(linha.quantity_invoiced) !== Number(linha.quantity_received);
  const historico = linha.price_history ?? null;

  return (
    <>
      <tr className={`group ${CLASSE_LINHA} transition-colors hover:bg-surface-2`}>
        <TrilhoDaLinha tinta={tintaDoTrilhoDoEstado(linha.status)} />

        <th scope="row" className={`${CLASSE_CELULA} max-w-0 text-left font-medium`}>
          {linha.product === null || linha.product_name === null ? (
            <span className={`block truncate ${semArtigo ? "text-warning" : "text-muted-foreground"}`}>
              {semArtigo ? textos.linhas.semArtigo : rotuloDeEspecie(linha.kind)}
            </span>
          ) : (
            <Link
              to="/stock/$artigo"
              params={{ artigo: linha.product }}
              search={{}}
              className="block truncate hover:underline group-hover:underline"
              title={linha.product_name}
            >
              {linha.product_name}
            </Link>
          )}
          {/* A descrição da fatura debaixo do artigo: é a **tradução** que se
              está a confirmar, e as duas têm de estar à vista ao mesmo tempo.
              Por extenso fica no dossier; aqui trunca. */}
          <span
            className="block truncate font-mono text-xs font-normal text-muted-foreground"
            title={linha.description}
          >
            {linha.description}
          </span>
        </th>

        {/* O que entrou de facto, na unidade da fatura. O **faturado** só aparece
            quando divergem, debaixo do número que ele contradiz: uma coluna
            "FATURADO" seria igual à do recebido em todas as linhas menos uma. */}
        <td
          data-numeric
          className={`${CLASSE_CELULA} w-32 text-right ${parcial ? "text-warning" : ""}`}
          {...(parcial
            ? {
                title: textos.linhas.faturados(
                  textoDeQuantidadeDaFatura(linha.quantity_invoiced, linha.invoice_unit),
                  textoDeQuantidadeDaFatura(linha.quantity_received, linha.invoice_unit),
                ),
              }
            : {})}
        >
          {textoDeQuantidadeDaFatura(linha.quantity_received, linha.invoice_unit)}
          {parcial ? (
            <span className="block text-xs">
              {textos.linhas.faturadoCurto}{" "}
              {textoDeQuantidadeDaFatura(linha.quantity_invoiced, linha.invoice_unit)}
            </span>
          ) : linha.variable_weight ? (
            <span className="block text-xs text-muted-foreground">
              {textos.linhas.pesoVariavelNota}
            </span>
          ) : null}
        </td>

        {/* A quantidade na unidade **base**, que é a do ledger: é o número que
            vai entrar, e é por isso que não se mostra em kg nem em L. */}
        <td data-numeric className={`${CLASSE_CELULA} w-28 text-right`}>
          {linha.stock_quantity === null ? (
            // Duas ausências diferentes, e dizem-se com palavras diferentes: uma
            // linha de tara **não é** stock, e uma linha sem artigo no catálogo
            // não tem por onde converter — o ecrã não inventa nenhum dos dois.
            <span className="font-sans text-xs text-muted-foreground">
              {semArtigo ? textos.linhas.semConversao : textos.linhas.naoEStock}
            </span>
          ) : (
            <>
              {textoNaUnidadeBase(linha.stock_quantity)}
              {linha.movement === null ? (
                linha.packaging === null ? null : (
                  <span
                    className="block truncate text-xs text-muted-foreground"
                    title={linha.packaging.label}
                  >
                    {linha.packaging.label}
                  </span>
                )
              ) : (
                // O que separa este produto de um que inventa stock a partir de
                // um OCR: até o documento ser confirmado, esta quantidade é uma
                // promessa; depois, é uma linha do ledger.
                <span className="block font-sans text-xs text-muted-foreground">
                  {textos.linhas.jaNoStock}
                </span>
              )}
            </>
          )}
        </td>

        {/* Uma coluna para o dinheiro da linha: o total em cima, e debaixo dele o
            preço por unidade com a variação contra as últimas compras — que é o
            número que o dono reconhece de imediato. A **taxa de IVA** não tem
            coluna (é um de três valores legais, e não é número que se compare de
            linha em linha): vive no `title` desta célula, no dossier, e no rodapé
            do documento, que dá a base e o IVA por taxa como está impresso. */}
        {comEuros ? (
          <td
            data-numeric
            className={`${CLASSE_CELULA} w-36 text-right`}
            {...(linha.vat_rate === null
              ? {}
              : { title: textos.linhas.ivaDaLinha(formatRate(linha.vat_rate)) })}
          >
            {/* `null` **tem** célula e diz "sem preço": é uma afirmação sobre o
                documento (uma guia não os traz). A ausência não chega aqui —
                nesse caso não há coluna. */}
            {linha.line_total === null || linha.line_total === undefined ? (
              <span className="font-sans text-xs text-muted-foreground">
                {textos.linhas.semPreco}
              </span>
            ) : (
              formatMoney(linha.line_total)
            )}
            {linha.unit_price === null || linha.unit_price === undefined ? null : (
              <span className="block text-xs text-muted-foreground">
                {formatMoney(linha.unit_price)}/{linha.invoice_unit}
                {historico === null ? null : (
                  <span className={historico.change_pct > 0 ? "text-warning" : "text-success"}>
                    {" "}
                    {formatPercentChange(historico.change_pct)}
                  </span>
                )}
              </span>
            )}
          </td>
        ) : null}

        <td data-numeric className={`${CLASSE_CELULA} w-28 text-left text-muted-foreground`}>
          {linha.lot_code ?? ""}
        </td>

        <td className={`${CLASSE_CELULA} w-32`}>
          {linha.expires_at === null ? null : (
            <>
              <span data-numeric className="block text-left">
                {formatDate(linha.expires_at)}
              </span>
              {linha.expiry_kind === null ? null : (
                // A distinção que a lei faz, em palavra e não em cor: tratar
                // «consumir até» e a durabilidade mínima como a mesma coisa
                // perde a credibilidade dos alertas de imediato.
                <span
                  className="block truncate text-xs text-muted-foreground"
                  title={rotuloDeValidade(linha.expiry_kind)}
                >
                  {rotuloCurtoDeValidade(linha.expiry_kind)}
                </span>
              )}
            </>
          )}
        </td>

        {/* O estado é a palavra (DESIGN.md §3), e só o que precisa de atenção
            leva tinta: "por rever" em âmbar, "revista" e "de fora" em cinzento.
            Nenhuma linha desta tabela está num estado saudável que se possa
            calar — todas as três são passos de um trabalho em curso. */}
        <td className={`${CLASSE_CELULA} w-28`}>
          <span
            className={`block truncate ${porRever ? tintaDoTextoDoEstado(linha.status) : "text-muted-foreground"}`}
            {...(foraDaEntrada ? { title: textos.linhas.ficaDeFora } : {})}
          >
            {rotuloDeEstadoDeLinha(linha.status)}
          </span>
          {linha.reviewed_by === null ? null : (
            <span
              className="block truncate text-xs text-muted-foreground"
              title={textos.linhas.revistaPor(linha.reviewed_by)}
            >
              {linha.reviewed_by}
            </span>
          )}
        </td>

        {/* O botão abre o painel da linha. "Rever" onde há o que escrever ou o
            que decidir, "Ver" onde só há dossier — e nunca um `disabled`. */}
        <td className={`${CLASSE_CELULA} w-24`}>
          <Button
            variant="outline"
            size="sm"
            onClick={aoAlternar}
            aria-expanded={aberto}
            aria-controls={idDoPainel}
            // Uma função por verbo e não o verbo interpolado numa frase: numa
            // frase inglesa ele não fica onde está na portuguesa.
            aria-label={
              porRever || foraDaEntrada
                ? textos.linhas.reverALinha(linha.description)
                : textos.linhas.verALinha(linha.description)
            }
          >
            {porRever || foraDaEntrada ? textos.linhas.rever : textos.linhas.ver}
          </Button>
        </td>
      </tr>

      {aberto ? (
        // `scroll-mt-cabecalho`: a barra do ecrã é sticky à altura do cabeçalho,
        // e sem isto o campo de lote que recebe o foco podia parar debaixo dela.
        <tr className="scroll-mt-cabecalho border-b border-border">
          <td aria-hidden="true" className="w-trilho bg-surface-2 p-0" />
          <td
            id={idDoPainel}
            colSpan={colunas.length}
            className="bg-surface-2 px-celula-x py-3"
          >
            <div className="flex max-w-6xl flex-col gap-3">
              <DossierDaLinha linha={linha} />

              {foraDaEntrada ? (
                <div className="flex flex-col items-start gap-2">
                  <p className="text-sm text-muted-foreground">{textos.linhas.ficaDeFora}</p>
                  <Button variant="outline" disabled={aRevisar} onClick={aoVoltarARever}>
                    {aRevisar ? textos.comuns.aGuardar : textos.linhas.voltarARever}
                  </Button>
                </div>
              ) : porRever && semArtigo ? (
                <div className="flex flex-col items-start gap-2">
                  <p className="text-pretty text-sm text-muted-foreground">
                    {textos.linhas.semArtigoCorpo}
                  </p>
                  <Button variant="outline" disabled={aRevisar} onClick={aoDeixarFora}>
                    {aRevisar ? textos.comuns.aGuardar : textos.linhas.deixarFora}
                  </Button>
                </div>
              ) : porRever ? (
                <FormularioDeLinha
                  linha={linha}
                  aRevisar={aRevisar}
                  aoConfirmar={aoConfirmar}
                />
              ) : null}

              {erro === null ? null : (
                <p role="alert" className="text-sm text-danger">
                  {erro}
                </p>
              )}
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

export function TabelaDeLinhasDeFatura({
  linhas,
  comEuros,
  abertaEm,
  aoAlternar,
  linhaARevisar,
  erro,
  aoConfirmar,
  aoDeixarFora,
  aoVoltarARever,
}: {
  readonly linhas: readonly LinhaDeRececao[];
  /**
   * Este documento trouxe euros. Vem do **cabeçalho** da receção e não das
   * linhas, para o esqueleto poder ter as mesmas colunas que a tabela: o
   * cabeçalho chega primeiro, e um esqueleto com outra contagem de colunas é um
   * salto de layout no momento em que os dados chegam (DESIGN.md §3).
   */
  readonly comEuros: boolean;
  /** O `id` da linha com o painel aberto, ou `null`. */
  readonly abertaEm: string | null;
  readonly aoAlternar: (id: string) => void;
  /** O `id` da linha cujo pedido está a sair, ou `null`. */
  readonly linhaARevisar: string | null;
  readonly erro: string | null;
  readonly aoConfirmar: (
    linha: LinhaDeRececao,
    lote: string | undefined,
    validade: string | undefined,
  ) => void;
  readonly aoDeixarFora: (linha: LinhaDeRececao) => void;
  readonly aoVoltarARever: (linha: LinhaDeRececao) => void;
}) {
  const colunas = colunasDasLinhas(comEuros);

  return (
    <MolduraDeTabela
      colunas={colunas}
      larguraMinima={LARGURA_MINIMA}
      comTrilho
      rotulo={ROTULO}
    >
      <tbody>
        {linhas.map((linha) => (
          <LinhaDeFatura
            key={linha.id}
            linha={linha}
            colunas={colunas}
            comEuros={comEuros}
            idDoPainel={`linha-${linha.id}`}
            aberto={abertaEm === linha.id}
            aoAlternar={() => {
              aoAlternar(linha.id);
            }}
            aRevisar={linhaARevisar === linha.id}
            erro={abertaEm === linha.id ? erro : null}
            aoConfirmar={(lote, validade) => {
              aoConfirmar(linha, lote, validade);
            }}
            aoDeixarFora={() => {
              aoDeixarFora(linha);
            }}
            aoVoltarARever={() => {
              aoVoltarARever(linha);
            }}
          />
        ))}
      </tbody>
    </MolduraDeTabela>
  );
}

/**
 * O pendente da tabela, com as **mesmas** colunas e a mesma largura mínima: um
 * esqueleto com outra contagem de colunas é um salto de layout no momento em que
 * os dados chegam. Três linhas, que é a ordem de grandeza de um documento real
 * deste seed.
 */
export function EsqueletoDaTabelaDeLinhas({ comEuros }: { readonly comEuros: boolean }) {
  return (
    <EsqueletoDeTabela
      colunas={colunasDasLinhas(comEuros)}
      larguraMinima={LARGURA_MINIMA}
      comTrilho
      rotulo={textos.linhas.aCarregar}
      linhas={3}
    />
  );
}
