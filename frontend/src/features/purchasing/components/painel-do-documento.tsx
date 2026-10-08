import { CircleAlert, FileText, ImageOff, Trash2 } from "lucide-react";
import { useId, type ReactNode } from "react";

import { IndicadorDeCarga } from "@/components/indicador-de-carga";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { CLASSE_MICROROTULO } from "@/components/tabela";
import { formatFileSize, formatTime } from "@/lib/format";

import type { Documento } from "../schemas-de-documento";
import { textos } from "../textos";
import {
  estaAAcontecer,
  fraseDeEstadoDoDocumento,
  rotuloDeEstadoDoDocumento,
  rotuloDeOrigem,
  tintaDoTextoDoDocumento,
  tintaDoTrilhoDoDocumento,
} from "../vocabulario-de-documento";

/**
 * O documento que está em cima da mesa: o estado, as páginas, os ficheiros e as
 * duas acções que ele admite.
 *
 * ## O estado é uma frase e um desenho, nos oito casos
 *
 * O painel não tem um ramo `default`. A palavra vem do `vocabulario-de-documento`
 * (exaustivo sobre o enum gerado), a frase também, e o que **muda com o estado**
 * é o desenho:
 *
 *  - o **trilho de 4px** na aresta esquerda, aceso só nos três que pedem outra
 *    acção de uma pessoa. É o mesmo trilho das tabelas, na mesma vertical, e é
 *    por isso que ele se lê de dois metros (DESIGN.md §1);
 *  - o **indicador de carga** nos três estados em que há trabalho a decorrer. Os
 *    três traços do DESIGN.md §3 dizem "está a acontecer" onde não há forma a
 *    reservar — e um esqueleto aqui era pior, porque prometia uma forma que não
 *    vem;
 *  - a **hora da expiração** ao lado do contador de páginas, e só no
 *    `aguarda_captura`: o `expires_at` é servido sempre (também num documento
 *    que já tem páginas, onde não quer dizer nada), e mostrá-lo fora desse
 *    estado era mostrar um relógio que não conta nada;
 *  - as **acções**, que existem enquanto o documento aceita páginas e
 *    desaparecem quando fecha. Um botão desactivado no lugar diria que ainda há
 *    ali algo a fazer. Quem decide é o `aceitaPaginas`, que vem de fora e é
 *    `closed_at === null` — **não** o estado, que passa a `a_normalizar` com a
 *    primeira folha e levava o botão de terminar com ele.
 *
 * ## A régua de campos, e não uma grelha de cartões
 *
 * Quatro números e um estado no topo, sem radius, sem borda individual, sem
 * sombra, sem `gap`: o que separa é a régua vertical de 1px, e o microrótulo usa
 * o mesmo tratamento do `<th>` das tabelas (DESIGN.md §4). É essa rima que faz o
 * painel e a lista lerem-se como um instrumento só. Os campos empacotam à
 * esquerda e não esticam.
 */
export function PainelDoDocumento({
  documento,
  aceitaPaginas,
  desistiu,
  aFechar,
  aDescartar,
  recusaDoFecho,
  aoFechar,
  aoDescartar,
}: {
  readonly documento: Documento;
  /**
   * O documento **aceita mais páginas**, o que é `closed_at === null` e não um
   * estado.
   *
   * Vem de fora e não se deriva aqui, porque a derivação é a mesma do ecrã e
   * duas cópias dela divergiriam — e porque a cópia que este painel tinha
   * **estava errada**: era `state === "aguarda_captura"`, que o servidor deriva
   * de *zero páginas*, logo o botão de terminar desaparecia no instante em que a
   * primeira folha chegava. A razão inteira está no `aceitaPaginas` do
   * `screens/fotografar.tsx`, com a sonda que o apanhou.
   */
  readonly aceitaPaginas: boolean;
  /** O polling desistiu aos 3 minutos (ADR 0020, decisão 3). */
  readonly desistiu: boolean;
  readonly aFechar: boolean;
  readonly aDescartar: boolean;
  /** A frase do servidor para uma recusa do `closing`, **não reescrita**. */
  readonly recusaDoFecho: string | null;
  readonly aoFechar: () => void;
  readonly aoDescartar: () => void;
}) {
  const idTitulo = useId();
  /** O slot ainda vazio: é o único estado em que o `expires_at` conta algo. */
  const aVazio = documento.state === "aguarda_captura";
  const aTrabalhar = estaAAcontecer(documento.state);
  const palavra = rotuloDeEstadoDoDocumento(documento.state);

  return (
    <section
      aria-labelledby={idTitulo}
      className="flex min-w-0 flex-col border border-border bg-surface"
    >
      <header className="flex items-center gap-3 border-b border-border px-celula-x py-3">
        {/* O trilho de sinal: 4px na aresta, aceso só quando algo pede uma
            acção. `aria-hidden` porque a palavra está ao lado — a cor nunca
            comunica sozinha. */}
        <span
          aria-hidden="true"
          className={`-ml-celula-x h-8 w-trilho shrink-0 ${tintaDoTrilhoDoDocumento(documento.state)}`}
        />
        <FileText aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        <h2 id={idTitulo} className="text-sm font-semibold">
          {textos.documento.painel.titulo}
        </h2>
        {/* **O indicador apaga-se com a desistência**, e isto foi apanhado numa
            fotografia tirada aos 195 segundos: o banner dizia "deixei de
            perguntar" e os três traços continuavam acesos a dois centímetros
            dele. Um indicador aceso afirma que alguém está a olhar; depois do
            teto ninguém está, e as duas coisas no mesmo ecrã são o produto a
            contradizer-se. */}
        {aTrabalhar && !desistiu ? (
          <IndicadorDeCarga rotulo={palavra} className="ml-auto" />
        ) : null}
      </header>

      {/* A régua de campos: `divide-x` é a régua vertical de 1px e não um `gap`,
          e os campos **não esticam**. `overflow-x-auto` e não `flex-wrap`, pela
          mesma razão que a régua de contadores do repositório: com wrap, o
          primeiro campo da segunda linha ganha uma régua à esquerda que não
          separa nada, e a 360px a régua deslizava-se melhor do que se partia. */}
      <dl className="flex min-w-0 divide-x divide-border overflow-x-auto overscroll-x-contain border-b border-border">
        <Campo rotulo={textos.documento.painel.campoEstado}>
          <span className={`text-sm font-semibold ${tintaDoTextoDoDocumento(documento.state)}`}>
            {palavra}
          </span>
        </Campo>

        <Campo
          rotulo={textos.documento.painel.campoPaginas}
          nota={
            aVazio
              ? textos.documento.painel.expiraAs(formatTime(documento.expires_at))
              : textos.documento.painel.limiteDePaginas(documento.page_limit)
          }
        >
          {/* `text-left` explícito: o `[data-numeric]` do `base.css` alinha à
              direita, que é o certo numa célula de tabela e o errado debaixo do
              seu próprio microrótulo. É a mesma correcção medida no
              `CorpoDoContador`. */}
          <span data-numeric className="block text-left text-sm font-semibold">
            {documento.page_count}
          </span>
        </Campo>

        <Campo rotulo={textos.documento.painel.campoOrigem}>
          <span className="text-sm">{rotuloDeOrigem(documento.source)}</span>
        </Campo>

        <Campo rotulo={textos.documento.painel.campoQuando}>
          <span data-numeric className="block text-left text-sm">
            {formatTime(documento.created_at)}
          </span>
        </Campo>

        {documento.created_by === "" ? null : (
          <Campo rotulo={textos.documento.painel.campoQuem}>
            <span className="text-sm">{documento.created_by}</span>
          </Campo>
        )}
      </dl>

      {/* **A frase do estado, com uma correcção que o cliente pode fazer e o
          servidor não.** O `a_normalizar` do contrato cobre duas situações — a
          imagem a ser preparada e *"o documento ainda aberto à espera da segunda
          folha"*, nas palavras do `models.estado_do_documento` — e a frase do
          vocabulário só serve a primeira ("pode sair deste ecrã"). A quem está a
          fotografar folha a folha isso é o conselho errado: falta-lhe dizer que
          acabou. Quem sabe distinguir as duas é este lado, porque tem o
          `closed_at`; o enum do servidor não o distingue. */}
      <p className="max-w-prose text-pretty px-celula-x py-3 text-sm text-muted-foreground">
        {aceitaPaginas && documento.page_count > 0
          ? textos.documento.painel.aindaAceitaPaginas
          : fraseDeEstadoDoDocumento(documento.state)}
      </p>

      {/* A desistência do polling. Fica **acima** das páginas porque é a resposta
          à pergunta que quem está a olhar tem na cabeça ("isto está parado?"). */}
      {desistiu ? (
        <div className="px-celula-x pb-3">
          <Alert className="border-warning-border bg-warning-surface">
            <CircleAlert aria-hidden="true" className="text-warning" />
            <AlertTitle>{textos.documento.painel.desistiuTitulo}</AlertTitle>
            {/* Duas frases, porque o teto quer dizer duas coisas diferentes. Um
                documento a ser preparado **aparece na lista** quando ficar
                pronto; um slot à espera de páginas não aparece lá nunca
                enquanto estiver vazio, logo a mesma frase seria falsa. A
                segunda entrou com o bloco do código QR, que é o que pôs o
                `aguarda_captura` a ser sondado. */}
            <AlertDescription className="text-pretty">
              {aceitaPaginas
                ? textos.documento.painel.desistiuCorpoDaCaptura
                : textos.documento.painel.desistiuCorpo}
            </AlertDescription>
          </Alert>
        </div>
      ) : null}

      <Paginas documento={documento} />

      {documento.files.length === 0 ? null : (
        <div className="flex flex-col gap-2 border-t border-border px-celula-x py-3">
          <h3 className={CLASSE_MICROROTULO}>{textos.documento.ficheiros.titulo}</h3>
          <ul className="flex flex-col gap-1">
            {documento.files.map((ficheiro) => (
              <li key={ficheiro.position} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                <span className="min-w-0 break-all">
                  {ficheiro.original_filename === ""
                    ? textos.documento.ficheiros.semNome
                    : ficheiro.original_filename}
                </span>
                <span data-numeric className="text-xs text-muted-foreground">
                  {formatFileSize(ficheiro.byte_size)}
                </span>
                <span className="text-xs text-muted-foreground">
                  {ficheiro.content_type} ·{" "}
                  {textos.documento.ficheiros.paginas(ficheiro.pages_detected)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {aceitaPaginas ? (
        <div className="flex flex-col gap-2 border-t border-border px-celula-x py-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={aoFechar} disabled={aFechar || aDescartar}>
              {aFechar ? textos.documento.painel.aFechar : textos.documento.painel.terminei}
            </Button>
            <Button variant="destructive" onClick={aoDescartar} disabled={aFechar || aDescartar}>
              <Trash2 aria-hidden="true" />
              {aDescartar ? textos.documento.painel.aDescartar : textos.documento.painel.descartar}
            </Button>
          </div>
          {/* `documento_sem_paginas`: a recusa do fecho vive **ao lado do botão
              que a provoca**, e não num banner no topo. É o único dos quatro
              códigos que nasce aqui. */}
          {recusaDoFecho === null ? null : (
            <p role="alert" className="flex items-start gap-1.5 text-sm text-danger">
              <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
              <span className="text-pretty">{recusaDoFecho}</span>
            </p>
          )}
        </div>
      ) : null}
    </section>
  );
}

/** Um campo da régua: microrótulo acima, valor abaixo, nota opcional. */
function Campo({
  rotulo,
  nota,
  children,
}: {
  readonly rotulo: string;
  readonly nota?: string;
  readonly children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5 px-celula-x py-2">
      <dt className={CLASSE_MICROROTULO}>{rotulo}</dt>
      <dd className="flex flex-col">
        {children}
        {nota === undefined ? null : <span className="text-xs text-muted-foreground">{nota}</span>}
      </dd>
    </div>
  );
}

/**
 * As páginas recebidas.
 *
 * **Nunca uma imagem partida, e nunca um esqueleto eterno.** O `image_url` vem
 * sempre servido e quem decide se vale a pena pedi-lo é o `normalized`; hoje ele
 * é `false` em todo o projecto, porque falta o rasterizador. Logo o default
 * desta grelha é um mosaico com o número da página e a frase "recebida, imagem a
 * preparar" — e a razão por que não há imagem é dita **uma vez**, abaixo da
 * grelha, em vez de dez vezes dentro dela.
 *
 * Um `<img>` sem `onError` apontado a um 404 dá o ícone de imagem partida do
 * browser, que é o pior dos dois mundos: parece um defeito e não diz nada. Um
 * `Skeleton` a pulsar para sempre é o outro extremo — promete que está a chegar.
 * Esta grelha não promete nada: diz o que há.
 */
function Paginas({ documento }: { readonly documento: Documento }) {
  if (documento.pages.length === 0) {
    return (
      <p className="border-t border-border px-celula-x py-3 text-sm text-muted-foreground">
        {textos.documento.paginas.semPaginas}
      </p>
    );
  }

  const algumaPreparada = documento.pages.some((pagina) => pagina.normalized);

  return (
    <div className="flex flex-col gap-2 border-t border-border px-celula-x py-3">
      <h3 className={CLASSE_MICROROTULO}>{textos.documento.paginas.titulo}</h3>
      <ul className="flex flex-wrap gap-2">
        {documento.pages.map((pagina) => (
          <li
            key={pagina.position}
            // `w-44` e não `w-32`: medido a 1280, a 128px a frase "Página 1
            // recebida, imagem a preparar" partia em **quatro** linhas dentro de
            // um mosaico de 2rem de altura útil, e o que se lia era um bloco de
            // texto esmagado. A 176px são duas linhas.
            className="flex w-44 flex-col gap-1 border border-border-strong bg-surface-2 p-2"
          >
            <span data-numeric className="text-left text-sm font-semibold">
              {pagina.position}
            </span>
            {pagina.normalized ? (
              <img
                src={pagina.image_url}
                alt={textos.documento.paginas.alternativa(pagina.position)}
                width={pagina.width ?? undefined}
                height={pagina.height ?? undefined}
                className="h-auto w-full"
              />
            ) : (
              <span className="flex items-start gap-1 text-xs text-muted-foreground">
                <ImageOff aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
                <span className="text-pretty">
                  {textos.documento.paginas.etiqueta(pagina.position)}{" "}
                  {textos.documento.paginas.aPreparar}
                </span>
              </span>
            )}
          </li>
        ))}
      </ul>
      {algumaPreparada ? null : (
        <p className="max-w-prose text-pretty text-xs text-muted-foreground">
          {textos.documento.paginas.porqueNaoHaImagem}
        </p>
      )}
    </div>
  );
}
