import { Link } from "@tanstack/react-router";
import { CircleAlert, PenLine, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";

import { MAXIMO_DE_TENTATIVAS } from "../qualidade-da-leitura";
import { textos } from "../textos";

/**
 * **As duas saídas de uma leitura que não serviu.** Nenhuma delas é um beco.
 *
 * Aparece em dois sítios do painel de leitura, e são dois casos diferentes com a
 * mesma resposta:
 *
 *  - no **ramo de erro** (`erro` e `ilegivel`), debaixo da razão que o servidor
 *    deu;
 *  - debaixo do **vazio de um documento lido sem linhas** — que não é um erro, e
 *    por isso o bloco não muda de cor por estar ali.
 *
 * ## *Tentar outra vez* é um endpoint próprio, e tinha de ser
 *
 * `POST /documents/<id>/extraction`, e **não** um segundo `POST .../closing`. O
 * fecho é repetível de propósito, para um duplo toque num telemóvel não pagar
 * duas leituras; reutilizá-lo aqui obrigava a destruir essa propriedade. Este
 * pedido **quer** pagar outra leitura, porque uma pessoa a pediu (ADR 0031,
 * decisão 7).
 *
 * ## O botão desaparece quando as tentativas acabam, e isso não é esconder
 *
 * O servidor recusa com 409 quando `attempt >= 3`, e o `attempt` vem no DTO —
 * logo o ecrã **sabe**, antes de alguém carregar, que o botão vai ser recusado.
 * Oferecê-lo na mesma era mentir a quem o carrega: o gesto custa um toque, uma
 * espera e uma frase de erro, e não tinha hipótese nenhuma de resultar.
 *
 * E não é um botão desactivado: um controlo desactivado sem frase é um beco (é o
 * argumento que a zona de ficheiro já faz para o teto de páginas). No lugar dele
 * fica a **frase** que diz que as três leituras foram gastas — e a outra saída
 * continua lá, que é o ponto todo deste bloco.
 *
 * ## *Rever à mão* e o que ela é hoje
 *
 * É a receção à mão: ninguém fica preso a uma leitura que não serviu, porque o
 * caminho de dar entrada a mercadoria nunca dependeu do modelo. O botão leva ao
 * ecrã Receber, que é onde as receções vivem.
 *
 * **O que ele ainda não faz, dito em vez de prometido:** não abre já um rascunho
 * a partir deste documento. O `POST /receipts` aceita um `document` e o
 * `useCriarRececao` do `api.ts` existe, mas o corpo exige uma `location` e **não
 * há neste ecrã nenhum sítio onde uma pessoa escolha o destino** — adivinhá-la
 * aqui era escrever uma entrada de mercadoria no armazém errado para poupar um
 * clique. O ecrã de criação à mão é a fatia que falta, e quando existir é este
 * botão que muda de destino.
 */
export interface PropsDaSaidaDaLeitura {
  readonly aPedir: boolean;
  /**
   * Ainda há tentativas por gastar **e** o servidor ainda não recusou esta.
   * Quando é `false` o botão não existe e a frase explica porquê.
   */
  readonly podeTentar: boolean;
  /** A frase do servidor para um 409, **não reescrita**. `null` se não houve. */
  readonly recusa: string | null;
  readonly aoTentarOutraVez: () => void;
}

export function SaidaDaLeitura({
  aPedir,
  podeTentar,
  recusa,
  aoTentarOutraVez,
}: PropsDaSaidaDaLeitura) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {podeTentar ? (
          <Button variant="outline" disabled={aPedir} onClick={aoTentarOutraVez}>
            <RefreshCw aria-hidden="true" />
            {aPedir ? textos.documento.saida.aPedir : textos.documento.saida.tentarOutraVez}
          </Button>
        ) : null}

        <Button asChild variant="outline">
          {/* `search={() => ({})}`: a receção à mão não herda o filtro deste
              ecrã, que é do documento e não da lista de receções. */}
          <Link to="/receber" search={() => ({})}>
            <PenLine aria-hidden="true" />
            {textos.documento.saida.reverAMao}
          </Link>
        </Button>
      </div>

      {/* A frase que substitui o botão quando ele não existe. Um controlo que
          desaparece sem explicação é tão beco como um desactivado sem razão. */}
      {podeTentar ? null : (
        <p className="max-w-prose text-pretty text-xs text-muted-foreground">
          {textos.documento.saida.semTentativas(MAXIMO_DE_TENTATIVAS)}
        </p>
      )}

      {/* O 409 do servidor, **ao lado do botão que o provocou** e não num banner
          no topo — a mesma regra que a recusa do fecho já segue. */}
      {recusa === null ? null : (
        <p role="alert" className="flex items-start gap-1.5 text-sm text-danger">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span className="text-pretty">{recusa}</span>
        </p>
      )}
    </div>
  );
}
