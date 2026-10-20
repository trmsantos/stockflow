import { ApiError, mensagemDeErro } from "@/lib/api/errors";
import { erroDoCampo } from "@/lib/api/erros-por-campo";

import { textos } from "./textos";

/**
 * Ler uma recusa do recurso `/documents` — e **só** ler: nada aqui reescreve uma
 * frase do servidor.
 *
 * ## As recusas têm duas formas, e é por isso que este ficheiro existe
 *
 * O `views.py` do `purchasing` devolve `{code, detail}` para as quatro recusas
 * de **estado** do documento, e a forma normal do DRF — `{"ficheiro": ["..."]}`,
 * **por campo** — para o que o serializer recusa no ficheiro. O mesmo status
 * (400) com duas formas: o `code` é para o ecrã **ramificar**, o erro por campo
 * é para aparecer debaixo do input.
 *
 * O `errors.ts` já lê o `code` defensivamente (`string | null`), porque nenhuma
 * das duas formas é garantida por um status; o que falta é a outra metade, e é
 * ela que está aqui.
 *
 * ## A cópia morreu, e foi o gatilho que esta secção declarava
 *
 * Esta secção explicava porque é que isto era uma cópia e não o `errosPorCampo`
 * do `accounts`: a fronteira do frontend só deixa importar
 * `@/features/<módulo>/api` de outra feature (ADR 0008, decisão 2), e pôr um
 * leitor de erros na porta pública do `accounts` era alargar uma interface
 * pública por arrumação. E nomeava a saída: *"a alternativa honesta é a descida
 * para `src/lib/api/`, e ela tem um gatilho: o **terceiro** módulo a precisar
 * disto. Hoje são dois"*.
 *
 * O terceiro chegou a 2026-10-19 — as contagens, onde o `POST` de uma linha
 * recusa um artigo com controlo por lotes e sem lote em `{"product": ["…"]}`.
 * A leitura está em `@/lib/api/erros-por-campo` e o que fica aqui é o que é
 * deste módulo: **qual** o campo, e o que se faz com a frase.
 *
 * ## Os códigos são por endpoint, de propósito
 *
 * O `RecusaDeDocumentoOut` declara `code` como string e não como enum fechado
 * porque o conjunto é **por endpoint**: `paginas_excedidas` só no anexar,
 * `documento_sem_paginas` só no fechar. Um enum com a união de todos sugeria ao
 * ecrã ramos que aquele endpoint nunca devolve. Os cinco estão aqui porque os
 * cinco mudam o **desenho** deste ecrã; qualquer outro cai no ramo genérico,
 * que mostra o `detail` e mais nada.
 */

/**
 * `documento_fechado` — 409. Anexar a um documento já fechado.
 *
 * É também o que recusa um **segundo** ficheiro num documento criado com
 * ficheiro: um ficheiro fecha-se a si mesmo (ADR 0021, decisão 9).
 */
export const CODIGO_DOCUMENTO_FECHADO = "documento_fechado";

/** `documento_descartado` — 409. Escrever num documento que alguém descartou. */
export const CODIGO_DOCUMENTO_DESCARTADO = "documento_descartado";

/**
 * `documento_sem_paginas` — 409. Fechar um documento vazio.
 *
 * Só aparece no `closing`, e só ao abrir um slot e carregar em "terminei" antes
 * de enviar a primeira página. O slot vazio morre pelo relógio e não por uma
 * pessoa (ADR 0020, decisão 2).
 */
export const CODIGO_DOCUMENTO_SEM_PAGINAS = "documento_sem_paginas";

/** `paginas_excedidas` — 400. Mais páginas do que o `page_limit` do documento. */
export const CODIGO_PAGINAS_EXCEDIDAS = "paginas_excedidas";

/**
 * `releitura_recusada` — 409. O `POST /documents/<id>/extraction` não aceita.
 *
 * **Três situações num código só**, e é o servidor que assim o decide: já há
 * receção confirmada, o documento está a ser lido neste momento, ou as três
 * tentativas acabaram (ADR 0031, decisão 7). O `detail` cobre as três numa frase
 * e o ecrã mostra-a sem a reescrever — distinguir as três aqui era inventar
 * ramos que o contrato não dá.
 */
export const CODIGO_RELEITURA_RECUSADA = "releitura_recusada";

/**
 * O `code` de uma recusa, ou `null`.
 *
 * Nunca se assume presente por o status ser 400: as duas formas partilham o
 * status. Quem lê isto ramifica por igualdade e tem sempre um ramo para `null`.
 */
export function codigoDaRecusaDeDocumento(erro: unknown): string | null {
  return erro instanceof ApiError ? erro.code : null;
}

/**
 * A mensagem que o serializer devolveu para o campo `ficheiro`, ou `null`.
 *
 * As seis recusas por campo da ADR 0020 (decisão 4) saem todas por aqui:
 * extensão fora da allowlist, tipo real em desacordo com a extensão, PDF com
 * mais de dez páginas, zero bytes, e os 11 MiB. Cada uma com a sua frase, já
 * pronta para mostrar, e **nenhuma reescrita aqui** — o ecrã mostra-a debaixo do
 * input, que é onde um erro de campo pertence.
 *
 * Defensivo em cada passo: o payload pode ser `null` (uma resposta sem JSON — é
 * o que o proxy devolve se os bytes passarem o teto *dele*, 12 MiB, antes de
 * chegarem ao Django), pode não ser um objecto, a chave pode não existir, e o
 * valor pode ser uma string em vez de uma lista. Nenhum desses casos é um erro
 * desta função: é a ausência de erro naquele campo, e o ecrã cai então na frase
 * genérica do `mensagemDeErro`.
 *
 * Lê **uma** chave, escrita por extenso. Um `Object.entries` punha no ecrã o
 * nome de qualquer chave que o servidor inventasse (incluindo `detail`) debaixo
 * de um input que não existe, e um acesso por variável acordava o
 * `security/detect-object-injection`, que esta casa não suprime (CLAUDE.md).
 */
export function erroDoCampoFicheiro(erro: unknown): string | null {
  return erroDoCampo(erro, "ficheiro");
}

/**
 * **Onde é que a recusa é desenhada.** É a parte que não se adivinha a partir do
 * `code`, e por isso está nomeada.
 *
 * A frase do servidor nunca se reescreve — o que ramifica é o **sítio** e o
 * **desenho**, porque uma recusa sobre o ficheiro que se acabou de escolher não
 * pertence ao mesmo lugar que uma recusa sobre o documento que já não existe:
 *
 *  - `campo` — o serializer recusou o ficheiro (tipo, tamanho, zero bytes, PDF
 *    com páginas a mais). Vive **debaixo do input**, que é onde um erro de campo
 *    pertence, e quem o lê pode escolher outro ficheiro no mesmo gesto;
 *  - `limite` — `paginas_excedidas`. Também é sobre o ficheiro, mas o desenho
 *    muda: o campo fica **desactivado**, porque não há ficheiro nenhum que
 *    caiba, e o contador de páginas do painel já mostra o teto;
 *  - `documento_perdido` — `documento_fechado` ou `documento_descartado`. O
 *    documento aberto deixou de aceitar escrita, logo não há nada a corrigir
 *    neste campo: o desenho é um banner com **uma saída**, que é abrir outro;
 *  - `fecho` — `documento_sem_paginas`. Nasce no botão de fechar e fica **ao
 *    lado dele**, e não num banner no topo que faria alguém procurar o problema
 *    no sítio errado;
 *  - `releitura` — `releitura_recusada`. Nasce no botão de *tentar outra vez* e
 *    fica ao lado dele, pela mesma razão do `fecho`. O desenho tem uma segunda
 *    metade: a frase aparece **e o botão desaparece**, porque as três situações
 *    que o servidor cobre com este código não mudam por se voltar a carregar;
 *  - `generico` — tudo o resto, incluindo o que não tem corpo JSX nenhum (uma
 *    falha de rede, ou o teto de 12 MiB do proxy, que responde antes do Django).
 *    Banner com a frase e com retry.
 *
 * Os dois primeiros são o mesmo `code`-menos-um e desenhos diferentes; juntá-los
 * dava um campo activo a dizer "escolhe outro" sobre um documento que não aceita
 * mais nenhum.
 */
export type DesenhoDaRecusa =
  | "campo"
  | "limite"
  | "documento_perdido"
  | "fecho"
  | "releitura"
  | "generico";

export function desenhoDaRecusa(erro: unknown): DesenhoDaRecusa {
  if (erro === null || erro === undefined) return "generico";
  if (erroDoCampoFicheiro(erro) !== null) return "campo";

  switch (codigoDaRecusaDeDocumento(erro)) {
    case CODIGO_PAGINAS_EXCEDIDAS:
      return "limite";
    case CODIGO_DOCUMENTO_FECHADO:
    case CODIGO_DOCUMENTO_DESCARTADO:
      return "documento_perdido";
    case CODIGO_DOCUMENTO_SEM_PAGINAS:
      return "fecho";
    case CODIGO_RELEITURA_RECUSADA:
      return "releitura";
    default:
      return "generico";
  }
}

/**
 * A frase a mostrar, venha ela por campo ou por `detail`.
 *
 * O `mensagemDeErro` já devolve o `detail` quando ele existe e já garante que há
 * **sempre** uma frase (um erro de rede não tem `detail` nenhum, e é o caso mais
 * provável num telemóvel numa cave de armazém). Faltam-lhe duas coisas, e as
 * duas estão aqui:
 *
 *  1. **preferir o erro por campo**, que é mais específico do que qualquer
 *     `detail`;
 *  2. **não deixar sair texto de diagnóstico.** Quando um `ApiError` não tem
 *     `detail`, o `message` dele é `"500 em /documents"` — útil num log e
 *     indefensável num ecrã. O caso é real e não hipotético: foi **medido** neste
 *     ecrã, com um backend cuja base de dados ainda não tinha as tabelas do
 *     documento, e o que aparecia no banner de erro era exactamente essa string.
 *     Acontece em qualquer resposta sem corpo JSON — um 500 com a página de erro
 *     do Django, ou o teto de 12 MiB do proxy, que recusa antes de o Django ver o
 *     pedido.
 *
 * É a mesma correcção que o `mensagemDaRecusa` do `accounts` faz para o login, e
 * pela mesma razão. Não está em `src/lib/api/errors.ts` porque a frase é copy e a
 * copy vive no catálogo da feature (ADR 0019, decisão 3).
 */
export function fraseDaRecusa(erro: unknown): string {
  const doCampo = erroDoCampoFicheiro(erro);
  if (doCampo !== null) return doCampo;
  if (erro instanceof ApiError && erro.detail === null) return textos.documento.recusas.semCorpo;
  return mensagemDeErro(erro);
}

/**
 * O status HTTP, ou `null` se o erro não vier da API (rede, Zod).
 *
 * Existe por **um** ramo que o `code` não resolve: o `GET /documents/<id>` de um
 * documento que não existe neste estabelecimento responde **404 genérico e sem
 * `code`** — é a mesma recusa que a travessia de tenant produz, e é genérica de
 * propósito (um 403 diria a um estranho que o uuid existe noutra casa). Um 404
 * tem uma saída diferente de uma falha de rede: "abrir outro" em vez de "tentar
 * outra vez", e um botão de retry sobre um documento que nunca vai responder é a
 * pior das duas opções.
 */
export function statusDaRecusaDeDocumento(erro: unknown): number | null {
  return erro instanceof ApiError ? erro.status : null;
}
