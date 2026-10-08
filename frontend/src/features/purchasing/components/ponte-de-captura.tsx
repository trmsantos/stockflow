import { CircleAlert, Copy, QrCode, Smartphone } from "lucide-react";
import { useId, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { textos } from "../textos";
import { CodigoDeCaptura } from "./codigo-de-captura";

/**
 * O bloco da ponte: **o código, o endereço e o relógio.**
 *
 * ## Quatro estados, e nenhum deles é um ecrã em branco
 *
 *  1. **a carregar** — há um documento no URL e a resposta ainda não chegou. Um
 *     esqueleto com a *forma da placa*, porque aqui há forma a reservar: sem
 *     ele, o código aparece e empurra o resto do bloco 240px para baixo;
 *  2. **sem documento aberto** — a explicação e o botão. É o estado inicial do
 *     computador, e o que ele tem de dizer não é "carrega aqui": é que o
 *     telemóvel vai pedir a conta de quem o usa, porque quem descobre isso com o
 *     telemóvel na mão e a mercadoria à porta desiste;
 *  3. **documento aberto** — o código, o endereço copiável, a hora a que
 *     expira e quantas páginas já chegaram;
 *  4. **expirado** — o código morreu e o bloco diz que morreu, em vez de mostrar
 *     um código que o telemóvel vai recusar. A saída é abrir outro (ADR 0020,
 *     decisão 1c, que sobreviveu à revogação da adenda 1 por não depender de
 *     token nenhum: *"o bloco do desktop deixa de mostrar um QR morto aos 15
 *     minutos e oferece abrir outro"*).
 *
 * ## O código não é o único caminho, e o bloco não finge que é
 *
 * Quem não pode apontar uma câmara — e quem está a ver isto num leitor de ecrã —
 * tem o endereço em texto, selecionável e com um botão que o copia. A
 * alternativa textual do `<svg>` diz **o que o código é**; é este endereço que
 * diz o que ele *contém*. Ler 140 caracteres em voz alta não serve a ninguém, e
 * um `aria-label` com o URL lá dentro era exactamente isso.
 *
 * ## O relógio vem do servidor
 *
 * O `expires_at` está no contrato do documento desde a fatia 1. Calcular aqui
 * "quinze minutos a contar do `created_at`" era uma segunda definição do mesmo
 * prazo, a que deixa de bater no dia em que o servidor mudar — e os dois
 * relógios divergentes são precisamente o que a decisão 1c da ADR 0020 nomeia
 * como a pior divergência possível.
 */
export function PonteDeCaptura({
  url,
  expiraAs,
  paginas,
  expirado,
  aCarregar,
  aAbrir,
  erroAoAbrir,
  aoAbrir,
}: {
  /** O endereço do documento aberto, ou `null` se não houver nenhum. */
  readonly url: string | null;
  /** A hora a que o slot expira, já formatada. `null` fora do `aguarda_captura`. */
  readonly expiraAs: string | null;
  readonly paginas: number;
  readonly expirado: boolean;
  readonly aCarregar: boolean;
  readonly aAbrir: boolean;
  /** A frase do servidor para uma recusa do `POST /documents`, não reescrita. */
  readonly erroAoAbrir: string | null;
  readonly aoAbrir: () => void;
}) {
  const idTitulo = useId();

  return (
    <section
      aria-labelledby={idTitulo}
      className="flex flex-col gap-2 border-t border-border px-celula-x py-4"
    >
      <h2 id={idTitulo} className="flex items-center gap-2 text-sm font-semibold">
        <QrCode aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        {textos.documento.ponte.titulo}
      </h2>

      {aCarregar ? (
        <div aria-busy="true" className="flex flex-col gap-3 md:flex-row md:items-start md:gap-6">
          <span className="sr-only">{textos.documento.ponte.aCarregar}</span>
          {/* A forma do que vem, e é por isso que é um esqueleto e não o
              indicador: a placa tem 240px e o bloco de texto ao lado tem três
              linhas. Sem reservar a forma, o código aparece e empurra a banda
              inteira para baixo (DESIGN.md §3).
              **O custo, dito por inteiro:** se o documento que estava a carregar
              já estiver fechado, não vem código nenhum e a banda encolhe os
              mesmos ~155px que o esqueleto reservou. Reserva-se a forma do
              código porque **é esta a forma que esta banda existe para mostrar**
              — quem abre um documento para o telemóvel está a olhar para aqui —,
              e a alternativa (reservar a forma pequena) trocava um encolhimento
              por um crescimento do mesmo tamanho no caminho que importa. */}
          <Skeleton className="size-60 max-w-full shrink-0" />
          <Skeleton className="h-20 w-full max-w-prose" />
        </div>
      ) : url !== null ? (
        // `key={url}`: o "Copiado" é sobre **aquele** endereço, e sem a chave um
        // documento novo herdava a confirmação do anterior — alguém a ler
        // "Copiado" ao lado de um código que nunca copiou. Remontar é a resposta
        // idiomática a "este estado pertence a este valor".
        <CodigoEEndereco key={url} url={url} expiraAs={expiraAs} paginas={paginas} />
      ) : (
        <ParaAbrir
          expirado={expirado}
          aAbrir={aAbrir}
          erroAoAbrir={erroAoAbrir}
          aoAbrir={aoAbrir}
        />
      )}
    </section>
  );
}

/** O estado 3: o código, o endereço, o relógio e o que já chegou. */
function CodigoEEndereco({
  url,
  expiraAs,
  paginas,
}: {
  readonly url: string;
  readonly expiraAs: string | null;
  readonly paginas: number;
}) {
  const idEndereco = useId();

  /**
   * O que aconteceu ao último pedido de cópia.
   *
   * Três estados e não um booleano: `navigator.clipboard` falha de verdade — um
   * contexto não seguro, uma permissão negada, um browser antigo — e nesse caso
   * a resposta útil não é silêncio nem um "copiado" falso, é dizer que não deu e
   * que o endereço está ali para selecionar à mão.
   */
  const [copia, setCopia] = useState<"nada" | "sim" | "nao">("nada");

  async function copiar() {
    try {
      await navigator.clipboard.writeText(url);
      setCopia("sim");
    } catch {
      setCopia("nao");
    }
  }

  return (
    // O código **ao lado** do texto a partir de `md`, empilhados a 360. É o que
    // faz esta banda usar a largura que tem em vez de ser uma coluna estreita de
    // 570px de altura, e é o que lhe dá a altura de uma banda e não de um painel.
    <div className="flex flex-col gap-3 md:flex-row md:items-start md:gap-6">
      {/*
        A moldura da placa. **`border-border-strong` e não `border`**: isto
        delimita um componente e não separa superfícies (DESIGN.md §2), e na
        paleta clara é a única coisa que distingue a placa branca do cinzento
        quase branco do painel. `w-fit` para a moldura não esticar e deixar
        branco a mais em volta de um código que já tem a sua zona de silêncio
        desenhada lá dentro; `shrink-0` para o código **não** encolher quando o
        endereço ao lado for comprido — um módulo abaixo de 3px deixa de se ler.
      */}
      <div className="w-fit shrink-0 border border-border-strong">
        <CodigoDeCaptura
          url={url}
          rotulo={textos.documento.ponte.alternativaDoCodigo}
          className="size-60 max-w-full"
        />
      </div>

      <div className="flex min-w-0 max-w-prose flex-col gap-2">
        <p className="text-pretty text-xs text-muted-foreground">
          {textos.documento.ponte.comoLer}
        </p>

        {/* O endereço em texto, que é a outra metade da acessibilidade deste
            bloco: nem toda a gente consegue apontar uma câmara. */}
        <div className="flex flex-col gap-1">
          <span id={idEndereco} className="text-xs font-semibold">
            {textos.documento.ponte.endereco}
          </span>
          {/* `break-all` e mono: é um endereço e não prosa, e parte-se dentro de
              si mesmo em vez de esticar a banda. */}
          <code className="max-w-full break-all font-mono text-xs text-muted-foreground">
            {url}
          </code>
          <div className="flex flex-wrap items-center gap-2">
            {/* Sem `size="sm"`, e por duas razões medidas: aquele variante dá
                **28px** de altura — abaixo do `--spacing-controlo` de 40px e à
                altura de um chip — e traz um `text-[0.8rem]` que está fora da
                escala tipográfica do DESIGN.md §2. O tamanho `default` (32px, e
                44px sob `pointer: coarse` pelo `base.css`) é o que os outros
                botões deste ecrã usam. */}
            <Button
              variant="outline"
              aria-describedby={idEndereco}
              onClick={() => {
                void copiar();
              }}
            >
              <Copy aria-hidden="true" />
              {textos.documento.ponte.copiar}
            </Button>
            {/*
              **O rótulo do botão não muda para "Copiado"**, e a confirmação vive
              aqui. Duas razões: o nome de um botão diz o que ele *faz* e não o
              que já aconteceu — trocá-lo deixa quem volta a precisar de copiar
              sem o verbo —, e um nome de controlo que muda não é anunciado de
              forma fiável por um leitor de ecrã, enquanto uma região `status` é.
              A confirmação e a falha partilham a região de propósito: duas
              regiões `status` encavalitadas dizem a mesma coisa duas vezes.
              A cor nunca comunica sozinha — a palavra está sempre lá (§3).
            */}
            <span
              role="status"
              className={`text-xs ${copia === "nao" ? "text-danger" : "text-success"}`}
            >
              {copia === "sim"
                ? textos.documento.ponte.copiado
                : copia === "nao"
                  ? textos.documento.ponte.semCopiar
                  : ""}
            </span>
          </div>
        </div>

        {/* **Sem `data-numeric`**, e a razão é do DESIGN.md §2: o mono é para
            dados, e isto é prosa com uma hora dentro. Com ele, a frase inteira
            vinha em IBM Plex Mono — apanhado numa fotografia. A hora sozinha,
            em mono, está no campo do painel abaixo, que é onde ela é dado. */}
        {expiraAs === null ? null : (
          <p className="text-xs text-muted-foreground">
            {textos.documento.ponte.expiraAs(expiraAs)}
          </p>
        )}

        {/* O que o polling de 2 s existe para mostrar (ADR 0020, decisão 3).
            `aria-live="polite"`: quem está a olhar vê o número subir, e quem não
            está ouve-o — é o único sinal de que o telemóvel do outro lado está a
            funcionar. */}
        <p aria-live="polite" className="text-pretty text-xs font-medium">
          {paginas === 0
            ? textos.documento.ponte.semPaginas
            : textos.documento.ponte.paginasChegadas(paginas)}
        </p>
      </div>
    </div>
  );
}

/** Os estados 2 e 4: a explicação e o botão, com o aviso do código morto. */
function ParaAbrir({
  expirado,
  aAbrir,
  erroAoAbrir,
  aoAbrir,
}: {
  readonly expirado: boolean;
  readonly aAbrir: boolean;
  readonly erroAoAbrir: string | null;
  readonly aoAbrir: () => void;
}) {
  return (
    // `max-w-prose`: esta metade é texto corrido e o DESIGN.md §4 dá-lhe 42rem.
    // Sem o cap, numa banda de largura inteira a 1280 o aviso e a explicação
    // esticavam-se por 990px — medido, e lê-se mal pela razão de sempre.
    <div className="flex max-w-prose flex-col gap-2">
      {expirado ? (
        <Alert className="border-warning-border bg-warning-surface">
          <CircleAlert aria-hidden="true" className="text-warning" />
          <AlertTitle>{textos.documento.ponte.expiradoTitulo}</AlertTitle>
          <AlertDescription className="text-pretty">
            {textos.documento.ponte.expiradoCorpo}
          </AlertDescription>
        </Alert>
      ) : null}

      <p className="text-pretty text-xs text-muted-foreground">
        {textos.documento.ponte.comoFunciona}
      </p>

      <Button variant="outline" className="self-start" disabled={aAbrir} onClick={aoAbrir}>
        <Smartphone aria-hidden="true" />
        {aAbrir ? textos.documento.ponte.aAbrir : textos.documento.ponte.abrir}
      </Button>

      {erroAoAbrir === null ? null : (
        <p role="alert" className="flex items-start gap-1.5 text-sm text-danger">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span className="text-pretty">{erroAoAbrir}</span>
        </p>
      )}
    </div>
  );
}
