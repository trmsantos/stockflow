import { CircleAlert, FileQuestion, ScanText } from "lucide-react";
import { useId } from "react";

import { EstadoVazio } from "@/components/estado-vazio";
import { IndicadorDeCarga } from "@/components/indicador-de-carga";
import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  CLASSE_MICROROTULO,
  MolduraDeTabela,
  TrilhoDaLinha,
  type ColunaDeTabela,
} from "@/components/tabela";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { formatDate, formatMoney, formatPercentPoints, formatRate } from "@/lib/format";

import { extracaoMostraEuros } from "../euros-do-papel";
import { confiancaEBaixa } from "../qualidade-da-leitura";
import type { Extracao, LinhaLida } from "../schemas-de-documento";
import { textos } from "../textos";
import { textoDeNif } from "../vocabulario";
import { rotuloDeEstadoDaLeitura } from "../vocabulario-de-documento";

import { PainelDoQr } from "./painel-do-qr";
import { SaidaDaLeitura, type PropsDaSaidaDaLeitura } from "./saida-da-leitura";

/**
 * O que o modelo leu — **só de leitura**, e sem um único controlo sobre as
 * linhas.
 *
 * É a entrega da fatia 1 ao dono do produto: *"arrastar um PDF no desktop, ver
 * as páginas, e ver o que o modelo leu, num painel só de leitura"* (ADR 0021,
 * decisão 8). O que **não** está aqui é a revisão: nenhum campo editável,
 * nenhum botão de confirmar, nenhuma forma de isto virar stock. Os dois botões
 * que existem não tocam no que foi lido — pedem outra leitura, ou saem deste
 * caminho.
 *
 * ## O `erro` deixou de ser o caminho normal, e três coisas mudaram com isso
 *
 * Este ficheiro dizia *"hoje não há modelo configurado, logo a extração falha
 * **sempre**"* e desenhava-se a partir daí. Com a ADR 0031 a extração corre a
 * sério, e o que era verdade deixou de o ser:
 *
 *  1. o ramo do erro **oferece duas saídas** — *tentar outra vez* e *rever à
 *     mão* — onde antes não oferecia nenhuma. A razão de não oferecer era boa e
 *     caducou com ela: repetir não mudava nada enquanto a dependência não
 *     existisse. Agora muda, e custa dinheiro, e por isso o botão tem um tecto;
 *  2. a confiança **marca linhas**. Este ficheiro recusava-se a pintá-la porque
 *     um limiar era *"uma afirmação de domínio que ninguém tomou"*. Foi tomada:
 *     0,80, na decisão 4 da ADR 0031, e vive numa constante nomeada
 *     (`qualidade-da-leitura.ts`) e não num `<` enterrado neste JSX. O que
 *     **não** mudou é o que importa — a confiança não bloqueia nada, não
 *     reordena nada e não é um semáforo de três cores: é um aviso, numa cor só,
 *     sempre com a palavra ao lado;
 *  3. existe um **painel do QR**, que é a única coisa neste ecrã que não é
 *     opinião de um modelo.
 *
 * ## A ordem das linhas é a do papel, e isso é a feature
 *
 * Nada aqui reordena por confiança, por valor ou por o que quer que seja. *"A
 * correspondência com o papel é a única coisa que a revisão tem a seu favor"*
 * (ADR 0031, decisão 4): quem está a conferir tem a fatura ao lado e corre as
 * duas com o dedo. Uma tabela ordenada por confiança seria uma segunda ordem a
 * memorizar, e a primeira coisa que se perdia era o erro de uma linha em falta.
 */

/**
 * **Sete colunas com euros, cinco sem eles**, e as duas que faltam são as
 * colunas inteiras.
 *
 * Quem não vê dinheiro não recebe o "Preço" nem o "Total": duas colunas cheias
 * de "—" de alto a baixo leem-se como uma fatura **sem preços**, que é uma
 * mentira sobre o documento que está na fotografia ao lado. A ausência não tem
 * essa leitura — é o mesmo reflexo com que o servidor tira a chave do JSON em
 * vez de a pôr a zero (`euros-do-papel.ts`).
 *
 * É a mesma decisão que a tabela das receções e a das linhas de fatura já
 * tomaram, e está escrita três vezes porque as colunas são outras; a **regra**
 * de quem vê euros está escrita uma vez só, no `euros-do-papel.ts`.
 *
 * Os 224px que as duas largam vão para a descrição, que é a única coluna
 * flexível desta tabela — e é a que trunca nomes de artigo copiados do papel.
 */
function colunasDaLeitura(comEuros: boolean): readonly ColunaDeTabela[] {
  return [
    {
      chave: "posicao",
      rotulo: textos.documento.leitura.colunas.posicao,
      classe: "w-10 text-right",
    },
    { chave: "descricao", rotulo: textos.documento.leitura.colunas.descricao },
    {
      chave: "quantidade",
      rotulo: textos.documento.leitura.colunas.quantidade,
      classe: "w-40 text-right",
    },
    ...(comEuros
      ? [
          {
            chave: "preco",
            rotulo: textos.documento.leitura.colunas.preco,
            classe: "w-28 text-right",
          },
        ]
      : []),
    { chave: "iva", rotulo: textos.documento.leitura.colunas.iva, classe: "w-20 text-right" },
    ...(comEuros
      ? [
          {
            chave: "total",
            rotulo: textos.documento.leitura.colunas.total,
            classe: "w-28 text-right",
          },
        ]
      : []),
    {
      chave: "confianca",
      rotulo: textos.documento.leitura.colunas.confianca,
      // `w-44` e não `w-28`: a célula passou a levar a **palavra** ao lado do
      // número, e a largura é a soma dos dois ("CONFIRMAR" em caixa alta com
      // tracking de 0.08em, mais "72 %" em mono, mais o `gap` e os dois `px`).
      // A 28 a palavra partia para uma segunda linha e crescia a linha de 44px,
      // que é o defeito que o DESIGN.md §4 mede no terceiro ponto.
      classe: "w-44 text-right",
    },
  ];
}

/** `—` para um valor que o modelo não leu. Um zero inventado era pior. */
const VAZIO = "—";

/**
 * Sete colunas, e a soma das larguras fixas pede uma escala larga. `min-w-4xl`
 * (56rem) e não um valor arbitrário: é o mesmo idioma das outras seis tabelas do
 * repositório, e a 360px a tabela desliza por dentro da moldura — que é o que o
 * DESIGN.md §4 declara.
 *
 * **A mesma largura mínima com e sem euros**, de propósito: sem as duas colunas
 * de dinheiro a descrição fica com os 224px delas em vez de a tabela encolher,
 * e a 1280px é ela que truncava.
 */
const LARGURA_MINIMA = "min-w-4xl";

export function PainelDeLeitura({
  extracao,
  ramoDeErro,
  saida,
}: {
  readonly extracao: Extracao | null;
  /**
   * O **documento** está em `erro` ou `ilegivel`.
   *
   * Vem de fora e não se deriva do `extracao.state`, e a diferença é real: o
   * `erro` do documento inclui o relógio de 10 minutos a passar sobre uma
   * extração que ficou `pendente` — aí o estado da leitura não diz `erro`
   * nenhum, e o documento diz. Quem sabe os dois é o ecrã.
   */
  readonly ramoDeErro: boolean;
  /** As duas saídas, para o ramo de erro e para o vazio de um documento lido. */
  readonly saida: PropsDaSaidaDaLeitura;
}) {
  const idTitulo = useId();
  // A extração **lida**, e não um booleano: é ela que o `Cabecalho` recebe, e um
  // `lido && extracao !== null` era uma condição que o compilador já sabia ser
  // verdadeira pela primeira metade (o `no-unnecessary-condition` apanhou-o).
  const lida = extracao?.state === "lido" ? extracao : null;
  const marcadas = extracao?.lines.filter((linha) => confiancaEBaixa(linha.confidence)).length ?? 0;
  // Lido da **resposta** e não do papel da sessão: quem decide quem vê euros é o
  // servidor, e a forma do payload não pode divergir de si própria
  // (`euros-do-papel.ts`). Sem extração não há payload nenhum, e aí a pergunta
  // não se faz — nenhuma das duas tabelas é desenhada.
  const comEuros = extracao !== null && extracaoMostraEuros(extracao);

  return (
    <section
      aria-labelledby={idTitulo}
      className="flex min-w-0 flex-col border border-border bg-surface"
    >
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border px-celula-x py-3">
        <ScanText aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        <h2 id={idTitulo} className="text-sm font-semibold">
          {textos.documento.leitura.titulo}
        </h2>
        {extracao === null ? null : (
          <span className="text-sm text-muted-foreground">
            {rotuloDeEstadoDaLeitura(extracao.state)}
          </span>
        )}
        {extracao?.state === "pendente" ? (
          <IndicadorDeCarga rotulo={textos.documento.leitura.pendente} />
        ) : null}
        {extracao?.confidence === null || extracao === null ? null : (
          <span className="ml-auto flex items-baseline gap-1.5">
            <span className={CLASSE_MICROROTULO}>{textos.documento.leitura.confianca}</span>
            <span data-numeric className="text-sm">
              {formatRate(extracao.confidence)}
            </span>
          </span>
        )}
      </header>

      {/* **O vazio vive aqui e não no ecrã**, e isso foi uma correcção medida: a
          frase estava num `<p>` solto por cima da tela, fora de qualquer moldura,
          e lia-se como um resto de texto esquecido entre dois painéis. Um painel
          que responde a "o que o modelo leu" tem de responder também quando a
          resposta é "ainda nada" — é a mesma regra que faz o estado vazio de uma
          lista pertencer à lista. */}
      {extracao === null && !ramoDeErro ? (
        <p className="max-w-prose text-pretty px-celula-x py-3 text-sm text-muted-foreground">
          {textos.documento.leitura.semLeitura}
        </p>
      ) : null}

      {/* **O ramo de erro: a razão do servidor, e as duas saídas por baixo.**

          A razão vai como o servidor a deu — nem reescrita, nem resumida: é a
          única pista que impede alguém de ir ler os logs do worker, e desde a
          ADR 0031 ela distingue casos a sério (orçamento diário gasto, páginas a
          mais, tentativas esgotadas).

          Âmbar e não vermelho, pela doutrina do `vocabulario-de-documento`: uma
          leitura que não serviu não é uma perda — a mercadoria entra à mão e o
          documento continua guardado. O vermelho deste ecrã está reservado para
          o que **não pode** dar entrada, que é o documento anulado no painel do
          QR. */}
      {ramoDeErro ? (
        <div className="flex flex-col gap-3 px-celula-x py-3">
          <Alert className="border-warning-border bg-warning-surface">
            <CircleAlert aria-hidden="true" className="text-warning" />
            <AlertTitle>{textos.documento.leitura.razaoTitulo}</AlertTitle>
            <AlertDescription className="text-pretty">
              {extracao === null || extracao.reason === ""
                ? textos.documento.leitura.semRazao
                : extracao.reason}
            </AlertDescription>
          </Alert>
          {/* **As acções ficam fora do banner**, e por duas razões que a
              primeira fotografia mostrou de uma vez. O `AlertDescription` do
              shadcn sublinha todos os `<a>` que tem dentro, e o *rever à mão* é
              um `<Link>` dentro de um `<Button asChild>`: ao lado do irmão, um
              aparecia sublinhado e o outro não. E o `Alert` é `role="alert"` —
              uma região viva —, logo os rótulos dos dois botões eram lidos como
              parte do anúncio. O banner é a frase do servidor; o que se faz com
              ela é nosso e fica a seguir. */}
          <SaidaDaLeitura {...saida} />
        </div>
      ) : null}

      {/* A razão fora do ramo de erro: um documento lido **com** um aviso do
          servidor (uma página que não entrou, por exemplo). Sem botões: não há
          nada a reparar, e o resultado está logo abaixo. */}
      {extracao === null || extracao.reason === "" || lida !== null || ramoDeErro ? null : (
        <div className="px-celula-x py-3">
          <Alert className="border-warning-border bg-warning-surface">
            <CircleAlert aria-hidden="true" className="text-warning" />
            <AlertTitle>{textos.documento.leitura.razaoTitulo}</AlertTitle>
            <AlertDescription className="text-pretty">{extracao.reason}</AlertDescription>
          </Alert>
        </div>
      )}

      {lida === null ? null : (
        <>
          <Cabecalho extracao={lida} />
          <PainelDoQr extracao={lida} />
        </>
      )}

      {/* **Um documento lido sem linhas é um estado vazio e não um erro.**

          É a fotografia de um gato: o modelo validou, devolveu `{"lines": []}`, e
          o estado é `lido` (ADR 0031, decisão 3). Mas é também a nota de crédito
          que legitimamente não tem linhas de mercadoria — a das duas grades
          vazias está no seed —, e é por isso que o vazio tem de dizer as duas
          coisas sem acusar nenhuma. A acção existe porque o primeiro caso tem
          saída e o segundo não precisa dela. */}
      {lida !== null && lida.lines.length === 0 ? (
        <div className="border-t border-border">
          <EstadoVazio
            icone={FileQuestion}
            titulo={textos.documento.leitura.semLinhasTitulo}
            descricao={textos.documento.leitura.semLinhasCorpo}
          >
            <SaidaDaLeitura {...saida} />
          </EstadoVazio>
        </div>
      ) : null}

      {extracao === null || extracao.lines.length === 0 ? null : (
        <>
          <MolduraDeTabela
            colunas={colunasDaLeitura(comEuros)}
            larguraMinima={LARGURA_MINIMA}
            rotulo={textos.documento.leitura.tabela}
            comTrilho
          >
            <tbody>
              {extracao.lines.map((linha) => (
                <LinhaDaLeitura key={linha.position} linha={linha} comEuros={comEuros} />
              ))}
            </tbody>
          </MolduraDeTabela>

          {/* A legenda do marcador, **abaixo da tabela e uma vez só**. Diz as
              duas coisas que uma marca de cor não consegue dizer sozinha: o que
              ela significa, e o que ela **não** faz. "Não impede nada" é a
              metade que impede alguém de a ler como um bloqueio. */}
          {marcadas === 0 ? null : (
            <p className="max-w-prose text-pretty border-t border-border px-celula-x py-3 text-xs text-muted-foreground">
              {textos.documento.leitura.legendaDoMarcador(marcadas)}
            </p>
          )}
        </>
      )}

      {/* **A única frase deste painel sobre a ausência de euros, e uma só por
          documento.** Repetida em cada célula seria um ecrã a justificar-se; e
          é aqui, no rodapé, porque as três ausências — a coluna do preço, a do
          total, e o campo do cabeçalho — são a mesma decisão e têm uma razão
          só. Sem tom de castigo: diz de quem são os valores e o que fica para
          conferir, que é o trabalho de quem recebe (ADR 0021, decisão 9). */}
      {extracao !== null && !comEuros ? (
        <p className="max-w-prose text-pretty border-t border-border px-celula-x py-3 text-xs text-muted-foreground">
          {textos.documento.leitura.eurosDeQuemGere}
        </p>
      ) : null}

      <p className="max-w-prose text-pretty border-t border-border px-celula-x py-3 text-xs text-muted-foreground">
        {textos.documento.leitura.soLeitura}
      </p>
    </section>
  );
}

/**
 * Uma linha lida, com o marcador de confiança baixa quando é o caso.
 *
 * ## O marcador são **três** coisas, e nenhuma delas sozinha chega
 *
 *  1. o **trilho de 4px** na aresta esquerda, que é como esta identidade diz
 *     "olha para aqui" e como a leitura de dois metros do DESIGN.md §1 funciona
 *     — todos os trilhos na mesma vertical, o olho corre uma coluna em vez de
 *     trinta linhas;
 *  2. a **palavra**, na célula da confiança, porque a cor nunca comunica sozinha
 *     (DESIGN.md §3) e porque o trilho é `aria-hidden` — quem ouve o ecrã ouve a
 *     palavra;
 *  3. a **tinta do número**, que é a cor de estado no seu primeiro papel (cor de
 *     texto). Não é um chip: um badge de 28px dentro de uma célula de 44px é um
 *     cartão pequeno a competir com a régua que já delimita a célula.
 *
 * Âmbar e não vermelho: isto é um **aviso** e não um erro. A linha pode estar
 * perfeitamente certa — a confiança é o que o modelo diz de si próprio — e quem
 * revê é que decide. O vermelho deste ecrã é do painel do QR, onde há aritmética
 * a discordar de um número certificado.
 *
 * E a `description` é **texto de uma fatura**, ou seja entrada não confiável:
 * entra como nó de texto do React, que escapa, e nunca como HTML. O `title` leva
 * o texto inteiro para o que a coluna trunca.
 */
function LinhaDaLeitura({
  linha,
  comEuros,
}: {
  readonly linha: LinhaLida;
  /** Este payload trouxe euros. Decide as **duas colunas**, não o conteúdo delas. */
  readonly comEuros: boolean;
}) {
  const baixa = confiancaEBaixa(linha.confidence);

  return (
    <tr className={CLASSE_LINHA}>
      <TrilhoDaLinha tinta={baixa ? "bg-warning" : ""} />
      <td data-numeric className={`${CLASSE_CELULA} w-10`}>
        {linha.position}
      </td>
      <td className={CLASSE_CELULA}>
        <span className="line-clamp-1" title={linha.description}>
          {linha.description === "" ? VAZIO : linha.description}
        </span>
      </td>
      <td data-numeric className={`${CLASSE_CELULA} w-40`}>
        {linha.quantity === null
          ? VAZIO
          : `${linha.quantity}${linha.unit === "" ? "" : ` ${linha.unit}`}`}
      </td>
      {/* A célula só existe se a coluna existir — e a coluna só existe se os
          euros vierem. Dentro dela, o `null` continua a ser o traço: aí é o
          **modelo** que não leu o preço, que é um facto sobre o documento. */}
      {comEuros ? (
        <td data-numeric className={`${CLASSE_CELULA} w-28`}>
          {linha.unit_price === null || linha.unit_price === undefined
            ? VAZIO
            : formatMoney(linha.unit_price)}
        </td>
      ) : null}
      {/* **`formatPercentPoints` e não `formatRate`, e isto é uma correcção.**
          A versão anterior usava o `formatRate` (fracção → percentagem) com o
          pressuposto escrito ao lado: *"um modelo que devolva `23` dá
          `2 300 %` aqui ... o que falta é o limite no contrato"*. A ADR 0031
          escreveu-o: o prompt da extração pede a **percentagem impressa**
          (`6.000`, nunca `0.06`), e o QR compara as bases contra taxas de 6, 13 e
          23. Nesta tabela a taxa viaja em pontos, logo é assim que se lê. O
          `vat_rate` da **receção** continua a ser outro contrato e outro ecrã. */}
      <td data-numeric className={`${CLASSE_CELULA} w-20`}>
        {linha.vat_rate === null ? VAZIO : formatPercentPoints(Number(linha.vat_rate))}
      </td>
      {comEuros ? (
        <td data-numeric className={`${CLASSE_CELULA} w-28`}>
          {linha.line_total === null || linha.line_total === undefined
            ? VAZIO
            : formatMoney(linha.line_total)}
        </td>
      ) : null}
      {/* Sem `data-numeric` na célula: ela leva uma palavra **e** um número, e o
          `[data-numeric]` do `base.css` põe a célula inteira em mono. A marca
          fica no `<span>` do número, que é o único dado numérico aqui. */}
      <td className={`${CLASSE_CELULA} w-44`}>
        <span className="flex items-baseline justify-end gap-2">
          {baixa ? (
            <span className={`${CLASSE_MICROROTULO} text-warning`}>
              {textos.documento.leitura.confirmar}
            </span>
          ) : null}
          <span data-numeric className={`text-sm ${baixa ? "text-warning" : ""}`}>
            {linha.confidence === null ? VAZIO : formatRate(linha.confidence)}
          </span>
        </span>
      </td>
    </tr>
  );
}

/**
 * O cabeçalho que o modelo leu, em régua de campos.
 *
 * **A quantidade é mostrada verbatim e não normalizada.** O `quantity` da linha
 * vai como string, sem passar pelo `formatQuantity`: um `Decimal` a três casas
 * dava "1,000 cx" onde o papel diz "1", e isto é um painel que existe para se
 * comparar com o papel. Nos campos de dinheiro o `formatMoney` entra, porque
 * `"78.40"` não é como um total de fatura se lê em português.
 *
 * **E quando há QR, estes valores são os dele.** O servidor já resolveu o
 * conflito antes de servir — o QR é gerado por software certificado e o papel é
 * a leitura de uma fotografia —, e o que o papel dizia aparece abaixo, no painel
 * do QR, como prova e não como alternativa.
 */
function Cabecalho({ extracao }: { readonly extracao: Extracao }) {
  return (
    <dl className="flex min-w-0 divide-x divide-border overflow-x-auto overscroll-x-contain border-t border-border">
      <CampoLido
        rotulo={textos.documento.leitura.campos.fornecedor}
        valor={extracao.supplier_name}
      />
      <CampoLido
        rotulo={textos.documento.leitura.campos.nif}
        valor={extracao.supplier_nif === "" ? "" : textoDeNif(extracao.supplier_nif)}
        numerico
      />
      <CampoLido rotulo={textos.documento.leitura.campos.tipo} valor={extracao.doc_type} />
      <CampoLido
        rotulo={textos.documento.leitura.campos.numero}
        valor={extracao.doc_number}
        numerico
      />
      <CampoLido
        rotulo={textos.documento.leitura.campos.emitidaA}
        valor={extracao.issued_at === null ? "" : formatDate(extracao.issued_at)}
        numerico
      />
      <CampoLido
        rotulo={textos.documento.leitura.campos.adquirente}
        valor={extracao.customer_nif === "" ? "" : textoDeNif(extracao.customer_nif)}
        numerico
      />
      {/* **O campo inteiro sai da régua**, e não fica um "—" no lugar dele: um
          microrótulo "TOTAL" sobre um traço diz que este documento não tem
          total, e tem — é a mesma mentira que uma coluna de traços seria na
          tabela. A régua empacota à esquerda e fecha o buraco sozinha. O `null`
          continua a ser o traço: aí o total existe e o modelo é que não o leu. */}
      {extracao.total === undefined ? null : (
        <CampoLido
          rotulo={textos.documento.leitura.campos.total}
          valor={extracao.total === null ? "" : formatMoney(extracao.total)}
          numerico
        />
      )}
      {extracao.read_at === null ? null : (
        <div className="flex shrink-0 flex-col justify-center px-celula-x py-2">
          <span className="text-xs text-muted-foreground">
            {textos.documento.leitura.lidoA(formatDate(extracao.read_at))}
          </span>
        </div>
      )}
    </dl>
  );
}

function CampoLido({
  rotulo,
  valor,
  numerico = false,
}: {
  readonly rotulo: string;
  readonly valor: string;
  /** Dinheiro, datas, NIF e números de documento. Mono e alinhados à esquerda. */
  readonly numerico?: boolean;
}) {
  return (
    <div className="flex shrink-0 flex-col gap-0.5 px-celula-x py-2">
      <dt className={CLASSE_MICROROTULO}>{rotulo}</dt>
      {/* O `[data-numeric]` do `base.css` alinha à direita, e debaixo do seu
          próprio microrótulo isso lê-se como dois blocos diferentes: o
          `text-left` é a mesma correcção medida no `CorpoDoContador`.
          `undefined` e não `false` no atributo: o selector do CSS é
          `[data-numeric]`, logo o que conta é a presença, e `false` escreveria o
          atributo com o valor "false" — presente, e portanto a casar. */}
      <dd
        data-numeric={numerico ? true : undefined}
        className={`text-sm ${numerico ? "text-left" : ""}`}
      >
        {valor === "" ? VAZIO : valor}
      </dd>
    </div>
  );
}
