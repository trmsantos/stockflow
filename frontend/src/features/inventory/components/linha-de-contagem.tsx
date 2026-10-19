import { Check, Info } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Label } from "@/components/ui/label";
import { formatDecimalField, formatMoney, formatTime } from "@/lib/format";

import type { LinhaDeContagem } from "../schemas";
import { textos } from "../textos";
import { textoDeQuantidade } from "../vocabulario";

/**
 * Uma linha de contagem: nome · **campo numérico grande** · a unidade em que
 * ele conta · o esperado · a diferença · e **quem contou e quando**.
 *
 * **Isto não é "quantidade editável".** A proibição nº 1 do guião §4 é um lápis
 * ao lado do número no ecrã de **Stock**, e continua a valer: lá o número é
 * leitura. Aqui o campo é o ponto do ecrã — uma contagem é uma observação da
 * prateleira, e ao fechar entra no ledger como `adjustment` com justificação.
 * Nada aqui reescreve um nível, e é por isso que as duas coisas cabem no mesmo
 * produto.
 *
 * O campo tem `inputMode="decimal"`: no telemóvel abre o **teclado numérico**
 * ao primeiro toque, sem passar por um stepper nem por um seletor. O
 * `enterKeyHint="next"` põe "seguinte" na tecla de ação e o submit salta para o
 * campo por contar que vem depois — é assim que o teclado fica aberto do
 * princípio ao fim da zona, que é o que "teclado já aberto" quer dizer em pé,
 * com uma mão. Não há `autoFocus`: num ecrã de nove campos, o que a página faz
 * ao abrir é fazer *scroll* para o campo que roubou o foco, e perde-se o topo
 * com o progresso.
 *
 * O `<label>` fica **ao lado** e não acima, contra o default do DESIGN.md §3:
 * nove rótulos empilhados sobre nove campos são dezoito linhas, e o orçamento
 * do guião §0 são sete. O rótulo continua a ser um `<label htmlFor>` a sério —
 * clicável, lido por áudio, com a unidade em `aria-describedby`.
 *
 * ## O que se escreve no campo é o que o rótulo ao lado diz
 *
 * A unidade do campo é o `count_unit` da linha — kg na balança, un à mão —, e é
 * **nessa** unidade que o `POST` viaja. A conversão para a unidade base do
 * ledger é do servidor (`inventory-domain` §2). Isto esteve ao contrário no
 * contrato até 2026-10-19: o corpo era lido em unidade base, logo "24" ao lado
 * de um rótulo `kg` entrava como 24 g e o fecho gravava um ajuste de −24,976 kg
 * num ledger onde uma linha errada não se corrige.
 *
 * ## Quem contou não é cromado
 *
 * Há **uma** contagem aberta por estabelecimento, logo duas pessoas contam ao
 * mesmo tempo em dois telemóveis e a última a escrever ganha (o `POST` é um
 * upsert por artigo). Quem chega a uma linha tem de ver que já ali esteve
 * alguém — "o João já contou isto às 10:42" é a diferença entre recontar e
 * contar a mesma prateleira duas vezes. Nunca se somam duas observações.
 */

/** A mesma forma que o `decimal` do contrato, sem sinal: não se conta negativo. */
const DECIMAL_POSITIVO = /^\d+$|^\d+\.\d+$/;

/**
 * A grelha da linha, **e a do cabeçalho de colunas**, numa constante só.
 *
 * Duas definições divergiam na primeira coluna que mudasse de largura, e aí o
 * cabeçalho deixava de estar em cima da coluna que nomeia — um defeito que se vê
 * e que nenhum gate apanha.
 *
 * ## Porque é uma grelha e não uma `<table>`
 *
 * Este ecrã ficou de fora da conversão a tabelas densas e o dono do produto
 * apanhou-o: continuava a `max-w-2xl` com o cromado antigo, parecia de outro
 * produto. A minha razão para o deixar fora era que isto é um **formulário** e
 * não uma lista — o que é verdade —, mas tinha um pressuposto escondido: assumi
 * que uma tabela obriga a uma largura mínima grande e que isso partia os 360px.
 * Com poucas colunas não obriga.
 *
 * O que **de facto** não cabe é a informação toda a 360px: cinco colunas pedem
 * 640px, e a contagem faz-se de pé no armazém, com uma mão. Uma `<table>` com
 * `overflow-x-auto` punha fora do ecrã o campo que se está a escrever, que é o
 * oposto do que este ecrã existe para fazer.
 *
 * Daí uma grelha responsiva com **um só** `<input>` no DOM: cinco colunas em
 * desktop (a leitura de tabela que o resto da app tem) e duas linhas a 360, com
 * os mesmos elementos. O `md:contents` faz o `<p>` da segunda linha desaparecer
 * da grelha em desktop e promove os filhos dele a células — é o que evita
 * duplicar o campo em dois layouts, que seria duplicar o foco, o `key` de
 * remontagem e o `onBlur`.
 *
 * A ordem do DOM serve as duas larguras sem um único `order-*`: nome, campo,
 * esperado, diferença, quem. E pôr o campo **logo depois do nome** não é só
 * conveniência de layout — encurta o percurso do olho entre o que se lê na
 * prateleira e onde se escreve.
 */
const GRELHA_DA_LINHA =
  "grid-cols-[minmax(0,1fr)_auto] items-center gap-x-celula-x gap-y-1 px-celula-x md:grid-cols-[minmax(0,1fr)_11rem_7rem_9rem_9rem] md:gap-y-0";

/**
 * A segunda linha a 360px: **uma linha de texto e sempre a mesma altura**.
 *
 * É o que impede a lista de saltar enquanto se escreve. Antes de contar ela diz
 * o esperado; depois de contar ganha a diferença à esquerda e "quem · quando" à
 * direita, e os dois lados truncam em vez de passarem a uma segunda linha —
 * uma sub-linha que cresce desfaz o ritmo da lista debaixo do dedo que está a
 * escrever, que é exactamente o momento em que isso custa mais caro.
 *
 * `h-5` e não `min-h-5`: com `min-h` a altura voltava a ser a do conteúdo no dia
 * em que um nome longo não truncasse.
 */
const META_A_360 = "col-span-2 flex h-5 items-center gap-2 text-xs md:contents";

/**
 * O cabeçalho de colunas, **só onde há colunas**.
 *
 * A 360px a linha são duas linhas empilhadas, e um cabeçalho sobre elas nomearia
 * uma grelha que não está lá — daí `hidden md:grid`. Usa a **mesma** constante da
 * linha: duas definições divergiam na primeira coluna que mudasse de largura, e
 * aí o rótulo deixava de estar em cima da coluna que nomeia.
 *
 * `aria-hidden`: cada campo da linha já tem o seu nome acessível — o `<label>` no
 * nome do artigo, o `aria-describedby` da unidade, as palavras "esperado" e "a
 * menos"/"a mais". Um cabeçalho de grelha sem `role="columnheader"` não liga a
 * nada para quem ouve o ecrã, e fingir que liga era pior do que não o anunciar.
 */
export function CabecalhoDaContagem() {
  return (
    <div
      aria-hidden="true"
      className={`hidden h-8 border-b border-border bg-surface-2 text-xs font-bold tracking-microrotulo text-muted-foreground uppercase md:grid ${GRELHA_DA_LINHA}`}
    >
      <span>{textos.colunas.artigo}</span>
      <span>{textos.colunas.contado}</span>
      <span className="text-right">{textos.colunas.esperado}</span>
      <span className="text-right">{textos.colunas.diferenca}</span>
      <span>{textos.colunas.quem}</span>
    </div>
  );
}

/**
 * O que o servidor recusou **desta** linha, e com que registo o dizer.
 *
 * `orientacao` separa "faz primeiro a receção" — um passo seguinte, que quem
 * conta não fez de errado — de uma falha a sério. A cor do §2 muda com ele e a
 * palavra muda com a frase: nunca é só a cor a comunicar.
 */
export interface RecusaDaLinha {
  readonly frase: string;
  readonly orientacao: boolean;
}

export function LinhaDeContagem({
  linha,
  aRegistar,
  aoRegistar,
  idDoCampo,
  idDoCampoSeguinte,
  recusa,
}: {
  readonly linha: LinhaDeContagem;
  /** Esta linha tem um pedido a sair. */
  readonly aRegistar: boolean;
  readonly aoRegistar: (quantidade: string) => void;
  readonly idDoCampo: string;
  /** O campo por contar que vem a seguir, para onde o Enter salta. */
  readonly idDoCampoSeguinte: string | undefined;
  /** A recusa do servidor **para esta linha**, se a última tentativa falhou. */
  readonly recusa: RecusaDaLinha | null;
}) {
  const idDaUnidade = useId();
  const idDoErro = useId();
  const [erro, setErro] = useState<string | null>(null);

  // O que o campo mostra, **e** a referência contra a qual o `onBlur` decide se
  // houve mudança. Uma segunda forma do mesmo número aqui fazia cada saída do
  // campo valer como uma escrita nova: o campo dizia "24" e a comparação era
  // contra "24.000".
  const contado = linha.counted === null ? "" : formatDecimalField(linha.counted.display);
  const diferenca = linha.difference;
  const diferencaEmEuros = linha.difference_eur;

  // O sinal da diferença decide a tinta, e o sinal está no próprio número ("−")
  // mais a palavra em `sr-only`, logo a cor nunca comunica sozinha.
  const base = diferenca?.base;
  const emFalta = base?.startsWith("-") ?? false;
  const semDiferenca = base !== undefined && Number(base) === 0;
  const corDaDiferenca = semDiferenca
    ? "text-muted-foreground"
    : emFalta
      ? "text-danger"
      : "text-success";

  const aviso = recusa ?? (erro === null ? null : { frase: erro, orientacao: false });
  const temAviso = aviso !== null;

  function aoSubmeter(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const formulario = evento.currentTarget;
    const escrito = new FormData(formulario).get("quantidade");
    // A vírgula decimal é como se escreve em português; o contrato quer ponto.
    // É normalização de locale, não conversão de unidades — essa é do servidor.
    const valor = (typeof escrito === "string" ? escrito : "").trim().replace(",", ".");

    if (valor === "") {
      // Apagar o campo não "descontar" a linha: o contrato não tem como voltar
      // atrás numa observação, e um campo vazio com um número guardado no
      // servidor era o ecrã a contradizer-se. O `reset()` devolve o valor
      // confirmado, que é o que a linha ao lado continua a dizer.
      setErro(null);
      formulario.reset();
      return;
    }
    if (!DECIMAL_POSITIVO.test(valor)) {
      setErro(textos.contagem.escrevaQuantos(linha.count_unit));
      return;
    }

    setErro(null);
    aoRegistar(valor);
  }

  return (
    // O `scroll-mt-16` (64px) desconta a barra de topo do shell — 56px desde
    // que ela passou a ter os `--spacing-cabecalho` que o DESIGN.md §2 lhe dá —
    // mais uma folga. Sem ele, o campo que recebe o foco ao saltar de linha em
    // linha pode parar debaixo dela.
    <li className="scroll-mt-16 border-b border-border last:border-b-0 transition-colors hover:bg-surface-2">
      <form onSubmit={aoSubmeter} className={`grid ${GRELHA_DA_LINHA} py-2 md:h-linha md:py-0`}>
        <Label htmlFor={idDoCampo} className="min-w-0 truncate font-medium">
          {linha.short_name}
        </Label>

        <div className="flex shrink-0 items-center gap-2">
          <Input
            id={idDoCampo}
            key={linha.counted_at ?? "por-contar"}
            name="quantidade"
            type="text"
            inputMode="decimal"
            autoComplete="off"
            spellCheck={false}
            enterKeyHint={idDoCampoSeguinte === undefined ? "done" : "next"}
            // Sem `value`: o campo é **não controlado** e o `key` acima remonta-o
            // quando o servidor confirma outro número. Um input controlado
            // obrigava a reconciliar o que ele está a escrever com o que a cache
            // acabou de revalidar, e é assim que um dígito desaparece a meio.
            defaultValue={contado}
            placeholder="—"
            aria-describedby={temAviso ? `${idDaUnidade} ${idDoErro}` : idDaUnidade}
            aria-invalid={aviso?.orientacao === false ? true : undefined}
            data-numeric
            // `h-12` e não `h-11`: a 360px escreve-se de pé e com uma mão, e o
            // alvo cresce para o tamanho do dedo em vez do mínimo. Em desktop
            // volta ao controlo de 40px que o DESIGN.md §2 fixa.
            className="h-12 w-24 shrink-0 scroll-mt-16 text-base md:h-controlo md:w-20"
            onBlur={(evento) => {
              // Sair do campo vale como escrever: quem conta com o telemóvel
              // numa mão toca no campo seguinte em vez de carregar em "seguinte".
              if (evento.target.value.trim() === contado) return;
              evento.target.form?.requestSubmit();
            }}
          />
          <span id={idDaUnidade} className="w-8 shrink-0 text-sm text-muted-foreground">
            {linha.count_unit}
          </span>
        </div>

        {/* `md:contents`: em desktop este `<p>` desaparece da grelha e os filhos
            passam a células próprias. A 360px é uma segunda linha a atravessar as
            duas colunas, com altura fixa para a lista não saltar. */}
        <p className={META_A_360}>
          {/* O esperado **sai da linha a 360px assim que há contagem**, e em
              desktop fica sempre — lá é uma coluna. A razão é de espaço e é
              medida: a 328px úteis não cabem esperado, diferença, euros e quem,
              e a primeira a sair é a que o número ao lado já responde (contado
              menos diferença **é** o esperado). Antes de contar é o contrário:
              o esperado é a única coisa que a linha tem para dizer. */}
          <span
            className={`min-w-0 flex-1 truncate text-muted-foreground md:flex-none md:text-right ${
              linha.counted === null ? "" : "hidden md:block"
            }`}
          >
            <span className="md:hidden">{textos.contagem.esperadoPrefixo} </span>
            <span data-numeric>
              {linha.expected === null ? "—" : textoDeQuantidade(linha.expected)}
            </span>
          </span>

          {diferenca === null ? (
            // Uma célula vazia em desktop mantém o campo "Quem" na sua coluna:
            // sem ela a grelha fechava o buraco e a linha por contar desalinhava
            // da linha contada acima.
            <span aria-hidden="true" className="hidden md:block" />
          ) : (
            <span
              className={`flex shrink-0 items-center gap-1 md:justify-end ${corDaDiferenca}`}
            >
              {semDiferenca ? (
                <>
                  <Check aria-hidden="true" className="size-3.5 shrink-0" />
                  {textos.contagem.confere}
                </>
              ) : (
                <>
                  {/* O sinal é um **carácter**, não uma cor: "−0,600 kg" lê-se
                      igual a preto e branco. A palavra vai em `sr-only` para
                      quem ouve a linha não ter de interpretar o sinal. */}
                  <span data-numeric>{textoDeQuantidade(diferenca)}</span>
                  <span className="sr-only">
                    {emFalta ? textos.accoes.aMenos : textos.accoes.aMais}
                  </span>
                  {/* Os euros só para quem os vê. `difference_eur` chega a `null`
                      ao colaborador, e um traço no lugar deles seria dizer-lhe
                      que falta um número — quando o que falta é a permissão. */}
                  {diferencaEmEuros === null ? null : (
                    <>
                      <span aria-hidden="true">·</span>
                      <span data-numeric>{formatMoney(diferencaEmEuros)}</span>
                    </>
                  )}
                </>
              )}
            </span>
          )}

          {/* Quem contou e quando, nas **duas** larguras. Esteve escondido a
              360px, e a razão de então ("quem está a contar ao telemóvel é quem
              conta") caiu com a contagem única por estabelecimento: duas pessoas
              contam ao mesmo tempo em dois telemóveis, e é no telemóvel que a
              pergunta "isto já foi contado?" se faz. */}
          <span className="ml-auto max-w-36 shrink-0 truncate text-right text-muted-foreground md:ml-0 md:max-w-none md:text-left">
            {aRegistar ? (
              textos.contagem.aGuardar
            ) : linha.counted_by === null ? (
              ""
            ) : (
              <>
                {linha.counted_by}
                {linha.counted_at === null ? null : (
                  <>
                    <span aria-hidden="true"> · </span>
                    <span className="sr-only">{textos.contagem.as} </span>
                    <span data-numeric>{formatTime(linha.counted_at)}</span>
                  </>
                )}
              </>
            )}
          </span>
        </p>

        {aviso === null ? null : (
          <p
            id={idDoErro}
            // Orientação é âmbar e falha é vermelha, e nos dois casos a frase é
            // que comunica: a cor nunca vai sozinha (DESIGN.md §3).
            className={`col-span-2 flex items-start gap-1.5 py-1 text-sm md:col-span-5 ${
              aviso.orientacao ? "text-warning" : "text-danger"
            }`}
          >
            <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <span>{aviso.frase}</span>
          </p>
        )}
      </form>
    </li>
  );
}

/**
 * O pendente da lista de contagem: a **mesma** grelha, com barras nas células.
 *
 * Usava o `EsqueletoDaLista` dos outros ecrãs, que desenha cartões de 56px — e
 * com a linha a passar a grelha de 44px isso era um salto de layout no momento
 * em que as linhas chegam. O cabeçalho entra a sério, porque o cromado não
 * precisa de carregar.
 */
export function EsqueletoDaContagem({ linhas = 5 }: { readonly linhas?: number }) {
  return (
    <div aria-busy="true">
      <span className="sr-only">{textos.contagem.aCarregarLinhas}</span>
      <CabecalhoDaContagem />
      {Array.from({ length: linhas }, (_, indice) => indice).map((indice) => (
        <div
          key={indice}
          className={`grid ${GRELHA_DA_LINHA} border-b border-border py-2 md:h-linha md:py-0`}
        >
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-10 w-24 md:h-9 md:w-20" />
          <Skeleton className="col-span-2 h-3 w-24 md:col-span-1 md:ml-auto" />
          <Skeleton className="hidden h-3 w-20 md:block md:ml-auto" />
          <Skeleton className="hidden h-3 w-16 md:block" />
        </div>
      ))}
    </div>
  );
}
