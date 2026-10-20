import { CircleAlert } from "lucide-react";
import { useId, type ChangeEvent, type FormEvent } from "react";

import { IndicadorDeCarga } from "@/components/indicador-de-carga";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { textos } from "../textos";

/**
 * A zona de ficheiro — **um** `<input type="file">`, e é ela que resolve as duas
 * pontas.
 *
 * Num computador abre o explorador e aceita o PDF que o fornecedor mandou por
 * email; num telemóvel o `capture="environment"` abre a câmara de trás. É a
 * decisão 7 da ADR 0020 — *uma* rota, não duas — e a razão de ser um campo só e
 * não dois caminhos: um `<input>` com `capture` é ignorado por um browser sem
 * câmara, logo o mesmo elemento faz as duas coisas sem o cliente ter de
 * adivinhar em que aparelho está. Ramificar por dispositivo era o que a decisão
 * 1 da ADR 0008 proíbe (*"o mobile/desktop não é um problema de routing"*).
 *
 * ## O `accept` é mais estreito do que a allowlist do servidor, e é de propósito
 *
 * O servidor aceita `.jpg .jpeg .png .webp .pdf` e decide pelos **bytes
 * mágicos** — o `Content-Type` que o cliente declara é ignorado e não validado
 * (ADR 0020, decisão 4). O `accept` daqui é um filtro de conveniência do
 * explorador de ficheiros e não uma validação: um `.webp` escolhido à força
 * passa no servidor, e um `.png` renomeado para `.pdf` é recusado lá, não aqui.
 * Validar o tipo neste ficheiro era escrever uma segunda allowlist que só sabe
 * ficar desalinhada da primeira.
 *
 * ## O envio começa ao escolher, e não num segundo botão
 *
 * É um gesto e não dois. Quem está num armazém com uma fatura numa mão não vai
 * carregar em "enviar" depois de tirar a fotografia — a câmara do telemóvel já
 * tem o seu próprio passo de confirmação, e no computador escolher o ficheiro
 * **é** a decisão. O `onChange` pede o `requestSubmit()` do próprio formulário,
 * de modo a que haja **um** caminho de submissão: o `onSubmit`. Sem isso
 * passariam a existir dois (o `onChange` directo e a tecla Enter), e dois
 * caminhos para a mesma escrita divergem na primeira correção.
 *
 * O `<form>` fica, apesar de não haver botão de submeter: é o elemento que diz o
 * que isto é, é ele que o teclado submete, e um `<div>` com um `onChange` não é
 * um formulário só porque não tem botões.
 *
 * ## O `key` que repõe o campo
 *
 * Um `<input type="file">` guarda o ficheiro escolhido. Sem o remontar, escolher
 * **o mesmo** ficheiro outra vez não dispara `change` — que é exactamente o que
 * alguém faz depois de uma falha de rede. O `key` vem de fora porque é o ecrã
 * que sabe quantos envios acabaram.
 */
export function ZonaDeFicheiro({
  paraDocumentoAberto,
  aEnviar,
  desativado,
  limiteAtingido,
  erro,
  idDoAviso,
  chave,
  aoEscolher,
}: {
  /**
   * `true` quando já existe um documento aberto a receber páginas: o rótulo
   * passa de "o ficheiro do documento" para "a página seguinte", porque é outra
   * coisa que se está a pedir.
   */
  readonly paraDocumentoAberto: boolean;
  readonly aEnviar: boolean;
  /** Teto de páginas atingido, ou um documento que já não aceita escrita. */
  readonly desativado: boolean;
  /**
   * O `page_limit` do documento, quando é **ele** a razão de o campo estar
   * desactivado. `null` quando o campo está activo ou quando a razão é outra.
   *
   * Vem em separado do `desativado` porque um controlo desactivado tem de dizer
   * **porquê**: sem a frase, quem olha não sabe se é um defeito ou um limite, e
   * não sabe o que fazer a seguir.
   */
  readonly limiteAtingido: number | null;
  /** A frase do servidor para o campo `ficheiro`, **não reescrita**. */
  readonly erro: string | null;
  /**
   * O `id` do **aviso de privacidade**, que o ecrã desenha por cima deste campo.
   *
   * Entra no `aria-describedby` **à frente** da ajuda, e a ordem é o requisito:
   * quem ouve o ecrã tem de saber para onde vai a imagem **antes** de escolher o
   * ficheiro, não depois (ADR 0031, resposta do dono). Visualmente a ordem já é
   * essa porque o aviso está acima no DOM; isto é a mesma garantia para quem não
   * vê o ecrã.
   *
   * Vem de fora porque o aviso vive fora deste componente — ele é do ecrã e
   * cobre também o botão que abre um documento de várias folhas.
   */
  readonly idDoAviso: string;
  readonly chave: number;
  readonly aoEscolher: (ficheiro: File) => void;
}) {
  const idCampo = useId();
  const idAjuda = useId();
  const idErro = useId();

  function aoSubmeter(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const escolhido = new FormData(evento.currentTarget).get("ficheiro");
    // `instanceof File` e não um `as`: o `FormData.get` devolve
    // `File | string | null`, e um `<input type="file">` vazio devolve um `File`
    // de zero bytes em alguns browsers — que o servidor recusa com a frase dele.
    if (!(escolhido instanceof File) || escolhido.size === 0) return;
    aoEscolher(escolhido);
  }

  function aoMudar(evento: ChangeEvent<HTMLInputElement>) {
    evento.currentTarget.form?.requestSubmit();
  }

  return (
    <form onSubmit={aoSubmeter} className="flex flex-col gap-1.5">
      <Label htmlFor={idCampo} className="text-sm">
        {paraDocumentoAberto ? textos.documento.zona.rotuloParaSlot : textos.documento.zona.rotulo}
      </Label>

      <div className="flex flex-wrap items-center gap-3">
        <Input
          key={chave}
          id={idCampo}
          name="ficheiro"
          type="file"
          accept="application/pdf,image/jpeg,image/png"
          capture="environment"
          disabled={aEnviar || desativado}
          aria-describedby={
            erro === null ? `${idDoAviso} ${idAjuda}` : `${idDoAviso} ${idAjuda} ${idErro}`
          }
          aria-invalid={erro === null ? undefined : true}
          onChange={aoMudar}
          // Duas coisas, e as duas foram medidas numa fotografia:
          //
          // **44px em qualquer largura**, e não só com `pointer: coarse`: este é
          // o alvo principal do ecrã, e a altura do `h-controlo` (40px) é para
          // os campos de um formulário denso. `max-w-md` para o nome de um
          // ficheiro longo não esticar a linha até ao outro lado de um monitor
          // de 1440.
          //
          // **O `file:` tem de parecer um botão.** O primitivo do shadcn deixa o
          // selector nativo em `bg-transparent` sem borda, e o resultado medido é
          // a acção principal do ecrã a ler-se como texto dentro de uma caixa —
          // "Escolher ficheiro Nenhum ficheiro selecionado", indistinguível de um
          // placeholder. Com a tinta do `surface-2` e a fronteira de componente
          // ele ganha a mesma forma que um `<Button variant="outline">`, sem que
          // haja um segundo primitivo: é o controlo nativo, que é o que mantém o
          // teclado e o `capture` a funcionar.
          className="h-11 max-w-md text-sm file:mr-3 file:h-8 file:rounded-md file:border file:border-border-strong file:bg-surface-2 file:px-2.5"
        />
        {/* **Nada ao lado do campo quando não está a enviar**, e a ausência foi
            medida: havia aqui um ícone decorativo de envio, e a 360px o
            `flex-wrap` descia-o para uma linha só dele, debaixo do campo, onde
            se lia como um botão perdido. Um ícone que não é alvo e não diz nada
            que o botão nativo já não diga não paga a linha que ocupa.
            O indicador já tem `role="status"` e o seu próprio texto `sr-only`; a
            frase visível fica `aria-hidden` para a espera ser **anunciada uma
            vez** em vez de duas. Duas regiões `status` encavalitadas são a forma
            de um leitor de ecrã dizer a mesma coisa duas vezes. */}
        {aEnviar ? (
          <span className="flex items-center gap-2 text-sm text-muted-foreground">
            <IndicadorDeCarga rotulo={textos.documento.zona.aEnviar} />
            <span aria-hidden="true">{textos.documento.zona.aEnviar}</span>
          </span>
        ) : null}
      </div>

      <p id={idAjuda} className="max-w-prose text-pretty text-xs text-muted-foreground">
        {limiteAtingido !== null
          ? textos.documento.zona.noTeto(limiteAtingido)
          : paraDocumentoAberto
            ? textos.documento.zona.ajudaDoSlot
            : textos.documento.zona.ajuda}
      </p>

      {/* O erro **abaixo do campo, em texto** (DESIGN.md §3): a cor nunca
          comunica sozinha, e o `role="alert"` é o que o anuncia a quem não está
          a olhar para esta parte do ecrã. */}
      {erro === null ? null : (
        <p id={idErro} role="alert" className="flex items-start gap-1.5 text-sm text-danger">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span className="text-pretty">
            <span className="font-semibold">{textos.documento.zona.erroTitulo}</span>
            {" — "}
            {erro}
          </span>
        </p>
      )}
    </form>
  );
}
