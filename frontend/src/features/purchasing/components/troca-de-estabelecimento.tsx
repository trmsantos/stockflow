import { Building2, CircleAlert } from "lucide-react";
import { useId } from "react";

import { Button } from "@/components/ui/button";

import { textos } from "../textos";

/**
 * O código é de outro estabelecimento: **pede-se a troca, nunca se faz em
 * silêncio.**
 *
 * ## Porque é que este bloco existe
 *
 * O `?estabelecimento=` do código é **argumento e não credencial** (ADR 0007), e
 * tem um trabalho concreto: quem tem duas casas tem a sessão do telemóvel numa
 * delas, e o código pode ser da outra. Sem este bloco, o telemóvel lia o código,
 * pedia o documento no âmbito errado, levava um 404 genérico — que é a resposta
 * certa do servidor — e o ecrã dizia *"este documento já não está aqui"* a
 * alguém que está a olhar para o código que o abriu. A resposta verdadeira não é
 * "não existe": é "estás na casa errada".
 *
 * ## E a troca é um toque, não um efeito secundário
 *
 * *"O ecrã **pede** a troca com um toque, e nunca a faz em silêncio — a sessão
 * escolhe o âmbito (ADR 0007), e uma troca de âmbito disparada por um parâmetro
 * de URL era um efeito secundário de uma navegação"* (ADR 0020, decisão 2b). Um
 * link partilhado num grupo de WhatsApp não pode mudar em que casa alguém está a
 * trabalhar sem ela carregar.
 *
 * Quem o faz é o `POST /auth/tenant-ativo` que já existe, pela API pública do
 * `accounts` — não há aqui um pedido novo nem uma segunda forma de trocar de
 * âmbito.
 *
 * ## Sem pertença não há botão, e isso não é um erro do ecrã
 *
 * Se o uuid do código não está na lista de estabelecimentos da sessão, esta
 * conta não tem acesso àquela casa. Não há nada a oferecer — carregar num botão
 * daria a recusa genérica da política, que é a mesma que um uuid forjado recebe.
 * O bloco diz o que se passa e quais são as duas saídas: outra conta, ou quem
 * abriu o código abre-o aqui.
 */
export function TrocaDeEstabelecimento({
  nomeDoCodigo,
  nomeAtual,
  aTrocar,
  erro,
  aoTrocar,
}: {
  /**
   * O nome do estabelecimento do código, ou `null` quando esta conta não o tem
   * na lista — isto é, quando não pertence a ele.
   */
  readonly nomeDoCodigo: string | null;
  readonly nomeAtual: string;
  readonly aTrocar: boolean;
  /** A frase do servidor para uma recusa da troca, não reescrita. */
  readonly erro: string | null;
  readonly aoTrocar: () => void;
}) {
  const idTitulo = useId();
  const semAcesso = nomeDoCodigo === null;

  return (
    <section
      aria-labelledby={idTitulo}
      className="flex min-w-0 flex-col border border-border bg-surface"
    >
      <header className="flex items-center gap-3 border-b border-border px-celula-x py-3">
        {/* O trilho de sinal: isto pede uma acção de uma pessoa, logo acende.
            `aria-hidden` porque o título ao lado já diz o que é — a cor nunca
            comunica sozinha (DESIGN.md §3). */}
        <span aria-hidden="true" className="-ml-celula-x h-8 w-trilho shrink-0 bg-warning" />
        <Building2 aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        <h2 id={idTitulo} className="text-sm font-semibold">
          {semAcesso
            ? textos.documento.ponte.semAcessoTitulo
            : textos.documento.ponte.trocaTitulo}
        </h2>
      </header>

      <div className="flex flex-col gap-3 px-celula-x py-3">
        <p className="max-w-prose text-pretty text-sm text-muted-foreground">
          {semAcesso
            ? textos.documento.ponte.semAcessoCorpo
            : textos.documento.ponte.trocaCorpo(nomeDoCodigo, nomeAtual)}
        </p>

        {semAcesso ? null : (
          <Button className="self-start" disabled={aTrocar} onClick={aoTrocar}>
            {aTrocar
              ? textos.documento.ponte.aTrocar
              : textos.documento.ponte.trocar(nomeDoCodigo)}
          </Button>
        )}

        {erro === null ? null : (
          <p role="alert" className="flex items-start gap-1.5 text-sm text-danger">
            <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <span className="text-pretty">{erro}</span>
          </p>
        )}
      </div>
    </section>
  );
}
