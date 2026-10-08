import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  EsqueletoDeTabela,
  MolduraDeTabela,
  TrilhoDaLinha,
  type ColunaDeTabela,
} from "@/components/tabela";
import { formatDate, formatTime } from "@/lib/format";

import type { Documento } from "../schemas-de-documento";
import { textos } from "../textos";
import {
  rotuloDeEstadoDoDocumento,
  rotuloDeOrigem,
  tintaDoTextoDoDocumento,
  tintaDoTrilhoDoDocumento,
} from "../vocabulario-de-documento";

/**
 * Os documentos que já entraram, em tabela densa — o mesmo cromado da tabela de
 * receções, porque é a mesma pergunta num grão diferente.
 *
 * ## O que a lista **não** mostra, e é o servidor que o decide
 *
 * Um slot sem páginas e um documento descartado não vêm nesta resposta. Isso tem
 * uma consequência de desenho que vale a pena dizer: o painel do documento acima
 * desta tabela **não é um luxo** — é o único sítio onde esses dois estados se
 * vêem, porque o `GET` por `id` serve-os e a lista não.
 *
 * ## Cada linha é um botão, e não um `<Link>`
 *
 * Porque não há para onde ligar: a receção de um documento é da fatia 2 e o
 * campo `receipt` é sempre nulo hoje. O que a linha faz é **escolher** o
 * documento para o painel acima, e isso vai para o search param — logo o botão
 * navega e a navegação é reproduzível (ADR 0008: o URL carrega o que reproduz o
 * ecrã). Um `<tr onClick>` não é alcançável por teclado; um `<button>` dentro da
 * primeira célula é, e tem foco visível pelo `:focus-visible` do `base.css`.
 *
 * O trilho de 4px é o mesmo das outras tabelas, na mesma vertical: aceso só nos
 * três estados que pedem outra acção de uma pessoa. Uma linha saudável não tem
 * trilho nenhum.
 *
 * ## Quatro colunas, e a quinta caiu numa fotografia
 *
 * Havia uma coluna "Leitura" com o estado da extração ao lado do estado do
 * documento, e **medida** ela dizia a mesma palavra duas vezes em quatro das
 * cinco linhas: `lido`/`lido`, `não foi lido`/`não foi lido`,
 * `ilegível`/`ilegível`. Não era coincidência — o estado do documento é
 * **derivado** do da leitura (`models.estado_do_documento`), logo as duas colunas
 * são a mesma afirmação com dois graus. O estado da leitura continua a existir
 * onde acrescenta algo: dentro do painel, onde há uma tentativa concreta com hora
 * e razão.
 *
 * ## E o que identifica o documento não é a palavra "ficheiro"
 *
 * A primeira coluna mostrava a **origem** (`ficheiro`/`fotografia`), que responde
 * a uma pergunta de suporte e não à pergunta de quem está a olhar: *qual* é este
 * documento. Quando a leitura correu, o número impresso e o nome do fornecedor
 * estão lá — e são o que a pessoa procura no papel que tem na mão. A origem desce
 * para a segunda linha da célula, onde já estava o nome de quem o abriu.
 */

const COLUNAS: readonly ColunaDeTabela[] = [
  { chave: "documento", rotulo: textos.documento.lista.colunas.documento },
  // `w-48` e não `w-44`, e `whitespace-nowrap`: medido a 1280, "08/10/2026 09:14"
  // em mono partia em duas linhas dentro dos 176px e punha as linhas a 62px numa
  // tabela de 44 — o defeito que o DESIGN.md §4 nomeia por extenso.
  {
    chave: "chegou",
    rotulo: textos.documento.lista.colunas.chegou,
    classe: "w-48 whitespace-nowrap",
  },
  { chave: "paginas", rotulo: textos.documento.lista.colunas.paginas, classe: "w-28 text-right" },
  { chave: "estado", rotulo: textos.documento.lista.colunas.estado, classe: "w-40" },
];

/** Quatro colunas: cabem numa área de 1024px sem truncar nada (DESIGN.md §4). */
const LARGURA_MINIMA = "min-w-2xl";

const ROTULO = textos.documento.lista.tabela;

/**
 * O que **a leitura** diz que este documento é: o número impresso, ou o nome do
 * fornecedor. `null` quando não há leitura ou quando ela não deu nenhum dos dois.
 *
 * Devolve `null` em vez de cair para a origem, e isso foi uma correcção medida: a
 * versão anterior caía para a palavra da origem e a célula lia-se
 * **"ficheiro · ficheiro · Ana Silva"** — a mesma palavra duas vezes, porque o
 * sufixo também a diz. Com `null`, quem decide o que mostrar é a célula, que já
 * sabe o que vai escrever a seguir.
 *
 * Os dois valores vêm da **extração**, que é texto não confiável de um LLM, e
 * isso é aceitável aqui por uma razão estreita: é um rótulo de linha de lista e
 * não um valor de negócio. Nada nesta célula entra no stock, e o que entra tem de
 * passar pela revisão humana (CLAUDE.md). O React escapa-o como escapa qualquer
 * texto — não há `dangerouslySetInnerHTML` em sítio nenhum deste ecrã.
 */
function identificadorLido(documento: Documento): string | null {
  const leitura = documento.extraction;
  if (leitura === null) return null;
  if (leitura.doc_number !== "") return leitura.doc_number;
  if (leitura.supplier_name !== "") return leitura.supplier_name;
  return null;
}

export function TabelaDeDocumentos({
  documentos,
  escolhido,
  aoEscolher,
}: {
  readonly documentos: readonly Documento[];
  /** O documento que está no painel acima, para marcar a linha. */
  readonly escolhido: string | null;
  readonly aoEscolher: (documento: string) => void;
}) {
  return (
    <MolduraDeTabela colunas={COLUNAS} larguraMinima={LARGURA_MINIMA} comTrilho rotulo={ROTULO}>
      <tbody>
        {documentos.map((documento) => {
          const quando = textos.comuns.dataEHora(
            formatDate(documento.created_at),
            formatTime(documento.created_at),
          );
          const identificador = identificadorLido(documento);
          const origem = rotuloDeOrigem(documento.source);
          // A origem só entra no sufixo quando **não** é ela o identificador.
          const resto = [identificador === null ? null : origem, documento.created_by]
            .filter((parte) => parte !== null && parte !== "")
            .join(" · ");
          return (
            <tr
              key={documento.id}
              // O degrau de superfície marca a linha escolhida — luminosidade e
              // não matiz, como o campo activo da régua de contadores. O
              // `aria-current` é o que o diz a quem ouve.
              className={`${CLASSE_LINHA} ${documento.id === escolhido ? "bg-surface-2" : ""}`}
              aria-current={documento.id === escolhido ? "true" : undefined}
            >
              <TrilhoDaLinha tinta={tintaDoTrilhoDoDocumento(documento.state)} />

              <td className={CLASSE_CELULA}>
                <button
                  type="button"
                  onClick={() => {
                    aoEscolher(documento.id);
                  }}
                  // Três coisas, e a primeira é um alvo de toque medido:
                  //
                  // **O alvo é a linha, e a linha continua a ter 44px.** Medido
                  // a 360px: o botão tinha 22px no meio de uma linha de 44 — ela
                  // parecia tocável e só o texto é que era. Três formas foram
                  // medidas antes desta: `h-linha` e `min-h-linha` pedem 44px de
                  // **conteúdo** e a linha, que é `border-box` com 1px de borda,
                  // crescia para 45; e `h-full` não resolve contra uma célula de
                  // tabela (ficou nos 22). O par `py-celula-y` com
                  // `-my-celula-y` dá 46px de área tocável e **zero** de altura
                  // para o layout — medido, a linha fica nos 44 nas duas
                  // larguras, com e sem a regra de `pointer: coarse`.
                  //
                  // `text-left` porque é um botão com prosa dentro de uma
                  // célula, e `underline-offset` em vez de uma cor própria: o
                  // acento está gasto no trilho e no item de menu activo.
                  className="-my-celula-y flex w-full items-center py-celula-y text-left hover:underline hover:underline-offset-4"
                >
                  <span className="sr-only">{textos.documento.lista.ver(quando)}</span>
                  {/* **Uma** linha e não duas, e isto foi medido numa fotografia:
                      com o nome em cima e a origem numa sub-linha de 13px, a
                      célula crescia de 44px para 62 e o ritmo da tabela
                      desfazia-se — o defeito que o DESIGN.md §4 nomeia no seu
                      terceiro ponto sobre larguras medidas. O que o nome perde
                      em destaque ganha-se com a tinta: o identificador em
                      `foreground`, o resto em `muted-foreground`. */}
                  <span aria-hidden="true" className="line-clamp-1">
                    {identificador ?? origem}
                    {resto === "" ? null : (
                      <span className="text-muted-foreground">
                        {" · "}
                        {resto}
                      </span>
                    )}
                  </span>
                </button>
              </td>

              <td data-numeric className={`${CLASSE_CELULA} w-48 whitespace-nowrap`}>
                {formatDate(documento.created_at)}{" "}
                <span className="text-muted-foreground">{formatTime(documento.created_at)}</span>
              </td>

              <td data-numeric className={`${CLASSE_CELULA} w-28`}>
                {documento.page_count}
              </td>

              {/* O estado é a **palavra**, não um chip (DESIGN.md §3). A cor vem
                  do primeiro papel do §2 e a palavra é quem cumpre a regra de
                  não comunicar só por cor. */}
              <td className={`${CLASSE_CELULA} w-40 ${tintaDoTextoDoDocumento(documento.state)}`}>
                {rotuloDeEstadoDoDocumento(documento.state)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </MolduraDeTabela>
  );
}

/** Pendente: a moldura e o cabeçalho a sério, só as células são barras. */
export function EsqueletoDaTabelaDeDocumentos() {
  return (
    <EsqueletoDeTabela
      colunas={COLUNAS}
      larguraMinima={LARGURA_MINIMA}
      comTrilho
      rotulo={textos.documento.lista.aCarregar}
      linhas={4}
    />
  );
}
