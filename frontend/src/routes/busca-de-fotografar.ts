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
 * ## Dois uuids, e cada um escrito por quem é
 *
 * São **dois** — `estabelecimento` e `documento` — porque os dois viajam no QR
 * que o telemóvel lê, e desde 2026-10-08 o QR existe: é o `urlDaPonte` do
 * `features/purchasing/ponte-de-captura.ts` que os escreve, numa função só, e é
 * o `scripts/check-ponte-de-captura.mjs` que afirma que são exactamente estes
 * dois, os dois uuid, sem fragmento (ADR 0020, adenda 2, gate 4). Até esse dia o
 * `estabelecimento` estava **fora** deste schema com a razão escrita — um campo
 * que nada produz é um ramo que nada exercita —, e entrou com quem lhe dá
 * sujeito.
 *
 * O `estabelecimento` não é uma credencial e não abre nada: é **argumento** (ADR
 * 0007), e o trabalho dele é fazer o telemóvel aterrar na casa certa. Se o
 * âmbito activo da sessão não é o do código, o ecrã **pede** a troca com um
 * toque, pelo `POST /auth/tenant-ativo` que já existe, e nunca a faz em
 * silêncio. Sem pertença, a política recusa genericamente.
 *
 * O `documento` tem sujeito desde a fatia 1: é escrito por este ecrã quando um ficheiro
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
  estabelecimento: z.uuid().optional().catch(undefined),
  documento: z.uuid().optional().catch(undefined),
});

export type BuscaDeFotografar = z.output<typeof buscaDeFotografarSchema>;
