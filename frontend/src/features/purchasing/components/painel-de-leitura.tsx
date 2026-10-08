import { CircleAlert, ScanText } from "lucide-react";
import { useId } from "react";

import { IndicadorDeCarga } from "@/components/indicador-de-carga";
import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  CLASSE_MICROROTULO,
  MolduraDeTabela,
  type ColunaDeTabela,
} from "@/components/tabela";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { formatDate, formatMoney, formatRate } from "@/lib/format";

import type { Extracao } from "../schemas-de-documento";
import { textos } from "../textos";
import { textoDeNif } from "../vocabulario";
import { rotuloDeEstadoDaLeitura } from "../vocabulario-de-documento";

/**
 * O que o modelo leu — **só de leitura**, e sem um único controlo.
 *
 * É a entrega da fatia 1 ao dono do produto: *"arrastar um PDF no desktop, ver
 * as páginas, e ver o que o modelo leu, num painel só de leitura"* (ADR 0021,
 * decisão 8). O que **não** está aqui é a revisão: nenhum campo editável,
 * nenhum botão de confirmar, nenhuma forma de isto virar stock. A revisão é a
 * fatia 2 e exige o catálogo.
 *
 * ## O `erro` é o caminho normal, não a excepção
 *
 * Hoje não há modelo configurado, logo a extração falha **sempre**, com uma
 * razão legível no campo `reason`. É por isso que este painel não trata o erro
 * como um caso de canto: o ramo do erro é o primeiro que se desenhou, mostra a
 * frase do servidor sem a reescrever, e não oferece "tentar outra vez" — repetir
 * não muda nada enquanto a dependência não existir, e um botão que não resolve
 * nada é pior do que a frase sozinha.
 *
 * ## A confiança é um número e não um semáforo
 *
 * O contrato dá `confidence` por linha e no documento, como `Decimal`. O que
 * este painel **não** faz é pintá-la de verde, âmbar e vermelho: um semáforo
 * precisa de limiares, e um limiar de confiança é uma afirmação de domínio ("a
 * partir de 80 % aceita-se") que ninguém tomou. Inventá-lo num ficheiro de UI
 * seria fixá-lo onde nenhum revisor o procuraria. Fica o número, mono, alinhado
 * à direita, com a unidade visível — e a frase do rodapé a dizer que nada disto
 * entra no stock sem uma pessoa.
 */

const COLUNAS: readonly ColunaDeTabela[] = [
  { chave: "posicao", rotulo: textos.documento.leitura.colunas.posicao, classe: "w-10 text-right" },
  { chave: "descricao", rotulo: textos.documento.leitura.colunas.descricao },
  {
    chave: "quantidade",
    rotulo: textos.documento.leitura.colunas.quantidade,
    classe: "w-40 text-right",
  },
  { chave: "preco", rotulo: textos.documento.leitura.colunas.preco, classe: "w-28 text-right" },
  { chave: "iva", rotulo: textos.documento.leitura.colunas.iva, classe: "w-20 text-right" },
  { chave: "total", rotulo: textos.documento.leitura.colunas.total, classe: "w-28 text-right" },
  {
    chave: "confianca",
    rotulo: textos.documento.leitura.colunas.confianca,
    classe: "w-28 text-right",
  },
];

/** `—` para um valor que o modelo não leu. Um zero inventado era pior. */
const VAZIO = "—";

/**
 * Sete colunas, e a soma das larguras fixas pede uma escala larga. `min-w-4xl`
 * (56rem) e não um valor arbitrário: é o mesmo idioma das outras seis tabelas do
 * repositório, e a 360px a tabela desliza por dentro da moldura — que é o que o
 * DESIGN.md §4 declara.
 */
const LARGURA_MINIMA = "min-w-4xl";

export function PainelDeLeitura({ extracao }: { readonly extracao: Extracao | null }) {
  const idTitulo = useId();
  // A extração **lida**, e não um booleano: é ela que o `Cabecalho` recebe, e um
  // `lido && extracao !== null` era uma condição que o compilador já sabia ser
  // verdadeira pela primeira metade (o `no-unnecessary-condition` apanhou-o).
  const lida = extracao?.state === "lido" ? extracao : null;

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
      {extracao === null ? (
        <p className="max-w-prose text-pretty px-celula-x py-3 text-sm text-muted-foreground">
          {textos.documento.leitura.semLeitura}
        </p>
      ) : null}

      {/* A razão, como o servidor a deu. Nem reescrita, nem resumida: é a única
          pista que impede alguém de ir ler os logs do worker.
          Só fora do `lido`: um documento lido com sucesso não tem razão nenhuma
          a dar, e um banner com um título a dizer que a leitura não acabou em
          cima de uma leitura que acabou é o ecrã a desmentir-se. */}
      {extracao === null || extracao.reason === "" || lida !== null ? null : (
        <div className="px-celula-x py-3">
          <Alert className="border-warning-border bg-warning-surface">
            <CircleAlert aria-hidden="true" className="text-warning" />
            <AlertTitle>{textos.documento.leitura.razaoTitulo}</AlertTitle>
            <AlertDescription className="text-pretty">{extracao.reason}</AlertDescription>
          </Alert>
        </div>
      )}

      {lida === null ? null : <Cabecalho extracao={lida} />}

      {extracao === null ? null : extracao.lines.length === 0 ? (
        <p className="max-w-prose text-pretty border-t border-border px-celula-x py-3 text-sm text-muted-foreground">
          {textos.documento.leitura.semLinhas}
        </p>
      ) : (
        <MolduraDeTabela
          colunas={COLUNAS}
          larguraMinima={LARGURA_MINIMA}
          rotulo={textos.documento.leitura.tabela}
        >
          <tbody>
            {extracao.lines.map((linha) => (
              <tr key={linha.position} className={CLASSE_LINHA}>
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
                <td data-numeric className={`${CLASSE_CELULA} w-28`}>
                  {linha.unit_price === null ? VAZIO : formatMoney(linha.unit_price)}
                </td>
                {/* `formatRate` porque neste módulo a taxa viaja como
                    **fracção** (`"0.230"` → `23 %`), que é o que o
                    `schemas.ts` fixa e o que a tabela de linhas da receção já
                    mostra. Fica nomeado o pressuposto: o serializer do `agents`
                    aceita `Decimal(6,3)` sem limite de 0 a 1, logo um modelo que
                    devolva `23` dá `2 300 %` aqui. Duas convenções para a mesma
                    coluna em dois ecrãs seria pior; o que falta é o limite no
                    contrato, e é lá que tem de ser escrito. */}
                <td data-numeric className={`${CLASSE_CELULA} w-20`}>
                  {linha.vat_rate === null ? VAZIO : formatRate(linha.vat_rate)}
                </td>
                <td data-numeric className={`${CLASSE_CELULA} w-28`}>
                  {linha.line_total === null ? VAZIO : formatMoney(linha.line_total)}
                </td>
                <td data-numeric className={`${CLASSE_CELULA} w-28`}>
                  {linha.confidence === null ? VAZIO : formatRate(linha.confidence)}
                </td>
              </tr>
            ))}
          </tbody>
        </MolduraDeTabela>
      )}

      <p className="max-w-prose text-pretty border-t border-border px-celula-x py-3 text-xs text-muted-foreground">
        {textos.documento.leitura.soLeitura}
      </p>
    </section>
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
      <CampoLido
        rotulo={textos.documento.leitura.campos.total}
        valor={extracao.total === null ? "" : formatMoney(extracao.total)}
        numerico
      />
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
