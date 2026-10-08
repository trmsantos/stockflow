import { z } from "zod";

import { buscaDeRececoesSchema } from "./busca-de-rececoes";

/**
 * O search param do `/receber/fotografar`: o filtro das três rotas de `/receber`
 * **mais** o documento que está em cima da mesa.
 *
 * ## Um schema próprio que estende, e não uma alteração ao outro
 *
 * É a forma que a decisão 2b da ADR 0020 manda: *"os dois uuids entram num
 * schema próprio do `/receber/fotografar` que estende o `buscaDeRececoesSchema`
 * em vez de o alterar: as três rotas de `/receber` partilham-no hoje, e
 * alargá-lo punha dois uuids no tipo da lista e do detalhe"*. O `estende` paga o
 * link de voltar: `/receber` continua a receber o `estado` e nada mais.
 *
 * ## Um uuid e não dois, e a diferença é quem o constrói
 *
 * A ADR prevê **dois** — `estabelecimento` e `documento` — porque os dois viajam
 * no QR que o telemóvel lê. O `estabelecimento` só existe para o caso em que o
 * âmbito activo da sessão do telemóvel não é o do QR, e aí o ecrã pede a troca
 * com um toque; sem o bloco do QR construído, **ninguém escreve esse parâmetro**,
 * e um campo que nada produz é um ramo que nada exercita. Entra com o QR, que é
 * quem lhe dá sujeito.
 *
 * O `documento` tem sujeito hoje: é escrito por este ecrã quando um ficheiro
 * entra, e lido por ele para saber o que mostrar no painel. É a regra da ADR 0008
 * — o URL carrega o que **reproduz o ecrã** — e vale aqui por uma razão que não
 * valia para o slot: um documento com páginas **não expira**. A decisão 7 da ADR
 * 0020 recusou pôr o slot no URL do desktop porque *"é um estado que expira em
 * 15 minutos e um link partilhável para ele seria uma promessa falsa"*; um
 * documento já enviado está na lista e continua lá amanhã, logo o link cumpre o
 * que promete. Um slot ainda vazio **também** passa por aqui, e o custo é
 * conhecido e pequeno: um link para ele, aberto meia hora depois, mostra o
 * painel a dizer `expirado`, que é a verdade.
 *
 * O `.catch(undefined)` é a mesma rede que o `buscaDeRececoesSchema` tem, pela
 * mesma razão medida no Stock: é ele que garante que a chave chega ao ecrã
 * sempre presente, e que um valor cru do URL — alguém a escrever `?documento=1`
 * à mão — nunca sobrevive à fusão que o router faz. A ADR 0008 manda cair para o
 * default **em silêncio**, e é o que acontece.
 */
export const buscaDeFotografarSchema = buscaDeRececoesSchema.extend({
  documento: z.uuid().optional().catch(undefined),
});

export type BuscaDeFotografar = z.output<typeof buscaDeFotografarSchema>;
