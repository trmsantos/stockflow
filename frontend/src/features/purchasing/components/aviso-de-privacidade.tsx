import { ShieldAlert } from "lucide-react";
import { useId } from "react";

import { textos } from "../textos";

/**
 * **Para onde vai a imagem, dito antes de alguém escolher o ficheiro.**
 *
 * ## Porque é que este bloco existe, e porque é que não pode ser menor
 *
 * O dono escolheu o escalão **gratuito** de um fornecedor de IA para ligar a
 * extração (ADR 0031, resposta do dono de 2026-10-19), e um escalão gratuito
 * costuma treinar com o que lhe entra. Uma fatura traz o NIF do fornecedor, o
 * NIF do estabelecimento e uma morada. A ADR escreve-o sem margem:
 *
 * > *"O ecrã onde se envia um documento tem de dizer, **antes do envio e em
 * > português simples**, para onde vai a imagem e o que o fornecedor pode fazer
 * > com ela — uma pessoa não pode descobrir isso depois. O dia em que entrar uma
 * > fatura real sem esse aviso é o dia em que o produto mente a quem confia
 * > nele."*
 *
 * Daí as três propriedades que este componente tem de ter, e que são o que se
 * perde se alguém o "arrumar":
 *
 *  1. **está visível antes do input**, no DOM e no ecrã. Não é um tooltip, não
 *     está atrás de um "saber mais", não aparece depois de enviar. Um aviso que
 *     se descobre a seguir não é um aviso, é uma justificação;
 *  2. **é lido por um leitor de ecrã antes do campo**, porque o `id` dele entra
 *     no `aria-describedby` do `<input type="file">` **à frente** da ajuda. Quem
 *     ouve o ecrã chega ao campo e ouve isto primeiro;
 *  3. **diz as três coisas**: que a imagem sai do nosso servidor para um serviço
 *     de outra empresa, que o escalão é gratuito e que num gratuito a imagem pode
 *     servir para treinar, e que por isso só se enviam documentos de
 *     demonstração por agora.
 *
 * ## Não nomeia o fornecedor nem cita política nenhuma
 *
 * Dizer *"a OpenAI"* ou *"a Google"* seria uma afirmação sobre a configuração do
 * servidor que este lado não consegue verificar — o modelo e a base URL são
 * settings, e a fábrica `cliente()` é a única linha do repositório que sabe quem
 * é o fornecedor. E citar uma política de retenção que ninguém leu era inventar
 * uma garantia. O que fica é o que é verdade: um serviço de IA de terceiros, no
 * escalão gratuito.
 *
 * ## O dia em que o escalão passar a pago, esta frase fica **errada**
 *
 * E ficará errada em silêncio, que é o pior modo de falha de um aviso. Não se lê
 * do servidor porque **não há hoje campo nenhum no contrato que o diga**: o
 * `ExtracaoOut` serve o estado, o cabeçalho e o QR, e não traz o escalão, o
 * fornecedor nem a política. Inventar um `VITE_` com o nome do escalão era pior
 * do que a constante — punha no bundle uma afirmação sobre privacidade que
 * ninguém verifica e que qualquer build pode pôr errada.
 *
 * Logo a frase é **estática**, e a sua manutenção é esta linha: quem mudar a
 * `AGENTS_EXTRACTION_API_KEY` para uma conta paga muda a copy no mesmo commit.
 * O gatilho honesto para automatizar isto é o contrato ganhar um campo — e
 * pedi-lo é trabalho de backend, não deste ficheiro.
 *
 * ## Não é um `Alert` do shadcn, e a razão é de a11y
 *
 * O `Alert` traz `role="alert"`, que é uma região viva: serve para dizer o que
 * acabou de acontecer, não para descrever o que um campo faz. Um aviso
 * permanente com `role="alert"` é anunciado como interrupção ao montar e depois
 * cala-se — exactamente ao contrário do que se quer. Isto é uma `<section>` com
 * título, na mesma forma da `TrocaDeEstabelecimento`, e os papéis de banner do
 * DESIGN.md §2 (`warning-surface` + `warning-border`, texto em `foreground`):
 * é um aviso e não um erro, que é o mesmo registo da faixa do estabelecimento de
 * demonstração.
 */
export function AvisoDePrivacidade({ id }: { readonly id: string }) {
  const idTitulo = useId();

  return (
    <section
      aria-labelledby={idTitulo}
      className="flex min-w-0 flex-col border border-warning-border bg-warning-surface"
    >
      <header className="flex items-center gap-3 px-celula-x pt-3">
        <ShieldAlert aria-hidden="true" className="size-4 shrink-0 text-warning" />
        <h2 id={idTitulo} className="text-sm font-semibold">
          {textos.documento.privacidade.titulo}
        </h2>
      </header>
      {/* O `id` vem de fora e não de um `useId` daqui: quem o usa é o
          `aria-describedby` do campo de ficheiro, que vive noutro componente. */}
      <p id={id} className="max-w-prose text-pretty px-celula-x pt-1.5 pb-3 text-sm">
        {textos.documento.privacidade.corpo}
      </p>
    </section>
  );
}
