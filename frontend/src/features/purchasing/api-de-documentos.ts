import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { apiRequest, apiRequestVoid } from "@/lib/api/http";
import { paginated, type Paginated } from "@/lib/api/pagination";
import { queryKeys } from "@/lib/api/query-keys";
import { tenantDaCache } from "@/lib/api/tenant";

import { documentoSchema, type Documento } from "./schemas-de-documento";

/**
 * A camada de dados do **documento de fornecedor** — a fatia 1 da ADR 0021.
 *
 * Ao lado do `api.ts` e não dentro dele, pela mesma razão que separa os dois
 * ficheiros de schemas: o `api.ts` fala com endpoints que **ainda não existem**
 * (as receções, servidas por fixtures) e este fala com endpoints que existem. Um
 * ficheiro com as duas metades esconderia qual é qual, e é precisamente essa a
 * pergunta de quem vem corrigir um erro de rede.
 *
 * ## As cinco escritas e o que cada uma invalida
 *
 * Nenhuma toca no ledger, e isso é a propriedade que esta fatia tem de
 * encarnar: **um documento não é stock.** Criar, anexar, fechar e descartar
 * mexem na lista de documentos e em mais nada — não há `useInvalidarLedger`
 * neste ficheiro, e não é por esquecimento. O `receipt` de um documento é
 * sempre nulo nesta fatia, logo não há sequer uma receção a invalidar.
 *
 * ## Sem update optimista, em nenhuma das quatro
 *
 * Quem decide o estado é o servidor, e o estado é **derivado**: se um upload
 * nasce fechado, se um slot já expirou, se as páginas detectadas num PDF são
 * três ou dez, se os mesmos bytes já estavam lá (a resposta é 200 em vez de 201
 * e não há página nova). Adivinhar isso aqui era refazer no cliente as regras do
 * `services.py` — e mostrar por um instante um documento que podia voltar atrás.
 *
 * O caso que mais tenta é o descarte: parece reversível porque é suave
 * (`discarded_at`, a linha fica). Não é reversível **pelo ecrã** — não há
 * endpoint que o desfaça —, e um update optimista numa acção que o utilizador
 * não pode anular é uma promessa que o cliente faz sozinho.
 */

const CAMINHO_DOCUMENTOS = "/documents";

/**
 * Um recurso na cache, e não dois. As páginas, os ficheiros e a extração vêm
 * **dentro** do documento (é a decisão 9 da ADR 0021: as cinco operações
 * devolvem o `DocumentoOut` completo), logo não há uma segunda lista com o seu
 * próprio ritmo de invalidação.
 */
const RECURSO_DOCUMENTOS = "documents";

/** O intervalo do polling: 2 s (ADR 0020, decisão 3). */
const INTERVALO_DE_SONDAGEM_MS = 2_000;

/**
 * A desistência: 3 minutos (ADR 0020, decisão 3).
 *
 * A conta dela: 90 pedidos no máximo por documento, 30/min de um desktop contra
 * os 600/min por IP da zona `geral` do proxy — 5 % do orçamento. E a razão de
 * haver um teto é melhor do que o orçamento: **o polling é conveniência, o
 * caminho é a lista.** Aos três minutos o ecrã diz que o documento aparece na
 * lista quando ficar pronto, em vez de sondar para sempre um worker que pode
 * nunca responder.
 */
const TETO_DE_SONDAGEM_MS = 3 * 60 * 1_000;

/**
 * Os dois estados em que há trabalho a decorrer do lado do servidor, e portanto
 * os dois únicos em que vale a pena sondar.
 *
 * Os outros seis são terminais ou relógios: `aguarda_captura` e `expirado`
 * esperam por uma **pessoa** (ou pelos quinze minutos), e `lido`, `ilegivel`,
 * `erro` e `descartado` não voltam a mudar sozinhos. Sondar um `aguarda_captura`
 * seria a única excepção defensável — é o que o bloco do QR faria enquanto está
 * aberto —, e ela fica para o dia em que esse bloco existir: sem QR não há nada
 * a chegar de outro aparelho, e a página que falta vem deste mesmo ecrã, pelo
 * input de ficheiro, que já invalida a cache por si.
 */
function aTrabalhar(documento: Documento | undefined): boolean {
  if (documento === undefined) return false;
  return documento.state === "a_normalizar" || documento.state === "a_extrair";
}

function invalidarDocumentos(
  queryClient: ReturnType<typeof useQueryClient>,
  tenant: string,
): Promise<unknown> {
  return queryClient.invalidateQueries({
    queryKey: queryKeys.resource(tenant, RECURSO_DOCUMENTOS),
  });
}

/**
 * A lista de documentos do estabelecimento, mais recentes primeiro.
 *
 * O servidor esconde duas famílias: os slots **sem páginas** (um documento vazio
 * não é um documento) e os **descartados**. É por isso que esta lista não é o
 * alvo do polling e o `GET` por `id` é — o estado que o ecrã está a sondar é
 * precisamente um dos que não aparecem aqui.
 */
export function useDocumentos(): UseQueryResult<Paginated<Documento>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_DOCUMENTOS),
    queryFn: ({ signal }) => apiRequest(CAMINHO_DOCUMENTOS, paginated(documentoSchema), { signal }),
  });
}

/** O que o ecrã precisa de saber sobre a espera, e não só sobre os dados. */
export interface DocumentoSondado {
  readonly consulta: UseQueryResult<Documento>;
  /**
   * `true` quando passaram os 3 minutos e o documento continua a normalizar ou
   * a extrair. É o estado que o ecrã **tem de dizer**: a alternativa é um
   * indicador que roda para sempre, que é a forma mais barata de mentir.
   */
  readonly desistiu: boolean;
}

/**
 * Um documento, com sondagem enquanto houver trabalho a decorrer.
 *
 * `staleTime` fica a **0 de propósito**, e não contradiz a ADR 0011 (*"a
 * resposta a lentidão é `staleTime`"*): aquilo é a resposta a uma leitura lenta,
 * isto é a espera por um **acontecimento externo** — uma tarefa Celery a
 * rasterizar uma página e um modelo a ler uma fatura.
 *
 * A desistência é um `setTimeout` e não uma conta feita no `refetchInterval`, e
 * a diferença é observável: um predicado avaliado dentro do `refetchInterval`
 * para de sondar na primeira avaliação depois do teto, mas **não produz um
 * render** — o ecrã ficava com o último estado conhecido e com o indicador
 * aceso, para sempre, sem nada a dizer que já ninguém está a perguntar. O
 * temporizador força o render que escreve a frase.
 */
export function useDocumento(documento: string | null): DocumentoSondado {
  const tenant = tenantDaCache();

  /**
   * **Qual** documento é que esgotou o relógio, e não um booleano.
   *
   * Um booleano obrigava a reposição — `setDesistiu(false)` no corpo do efeito
   * quando o trabalho acaba ou quando se escolhe outro documento —, e uma
   * reposição síncrona num efeito é uma cascata de renders que o
   * `react-hooks/set-state-in-effect` recusa, e com razão. Guardando o **id**, a
   * desistência deriva-se por comparação e não há nada a repor: trocar de
   * documento deixa o id antigo a não casar, e acabar o trabalho desliga o
   * `emTrabalho`. O único setState que resta é o do temporizador, que é o
   * callback de um sistema externo — exactamente o caso para que o efeito serve.
   */
  const [desistidoEm, setDesistidoEm] = useState<string | null>(null);

  const consulta = useQuery({
    queryKey: queryKeys.detail(tenant, RECURSO_DOCUMENTOS, documento ?? ""),
    queryFn: ({ signal }) =>
      apiRequest(`${CAMINHO_DOCUMENTOS}/${documento ?? ""}`, documentoSchema, { signal }),
    enabled: documento !== null,
    staleTime: 0,
    refetchInterval: ({ state }) =>
      desistidoEm !== documento && aTrabalhar(state.data) ? INTERVALO_DE_SONDAGEM_MS : false,
  });

  const emTrabalho = aTrabalhar(consulta.data);

  // O relógio arranca quando o trabalho começa e é limpo quando ele acaba. As
  // duas dependências são as duas que o definem: o documento que se está a
  // sondar, e se ainda há o que sondar.
  useEffect(() => {
    if (documento === null || !emTrabalho) return;
    const relogio = setTimeout(() => {
      setDesistidoEm(documento);
    }, TETO_DE_SONDAGEM_MS);
    return () => {
      clearTimeout(relogio);
    };
  }, [documento, emTrabalho]);

  return { consulta, desistiu: emTrabalho && desistidoEm === documento };
}

/**
 * Abrir um documento **com** um ficheiro: o upload de um só gesto.
 *
 * `FormData` e não JSON — é `multipart/form-data`, e o `http.ts` reconhece-o e
 * não lhe põe `Content-Type` (o browser tem de escrever o `boundary`). O campo
 * chama-se `ficheiro` porque é o nome que o serializer valida, e é por esse nome
 * que a recusa de 400 volta.
 *
 * O documento nasce **fechado** e com o trabalho agendado: um ficheiro é um
 * documento completo, e o número de páginas de um PDF sabe-se do ficheiro (ADR
 * 0021, decisão 9). Quem quiser juntar folha a folha abre um slot.
 */
export function useAbrirDocumentoComFicheiro(): UseMutationResult<Documento, Error, File> {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (ficheiro: File) => {
      const corpo = new FormData();
      corpo.append("ficheiro", ficheiro);
      return apiRequest(CAMINHO_DOCUMENTOS, documentoSchema, { method: "POST", body: corpo });
    },
    onSuccess: async () => {
      await invalidarDocumentos(queryClient, tenant);
    },
  });
}

/**
 * Abrir um documento **sem** ficheiro: o slot que espera páginas.
 *
 * Nasce aberto, espera 15 minutos pela primeira página e é fechado por uma
 * pessoa. É o que torna possível fotografar uma fatura de duas folhas — e é
 * também o único caminho pelo qual os estados `aguarda_captura` e `expirado`
 * existem para este ecrã.
 *
 * Sem corpo nenhum: a origem é derivada de vir ou não ficheiro, e um campo
 * `source` que o cliente declarasse era mais uma coisa que ele pode pôr errada
 * (`services.criar_documento`).
 */
export function useAbrirSlotDeCaptura(): UseMutationResult<Documento, Error, void> {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: () => apiRequest(CAMINHO_DOCUMENTOS, documentoSchema, { method: "POST" }),
    onSuccess: async () => {
      await invalidarDocumentos(queryClient, tenant);
    },
  });
}

export interface FicheiroParaDocumento {
  readonly documento: string;
  readonly ficheiro: File;
}

/**
 * Anexar um ficheiro a um documento aberto. Um ficheiro por pedido.
 *
 * **201 na primeira vez e 200 na repetição**: os mesmos bytes no mesmo documento
 * não criam uma segunda página. O `apiRequest` não distingue os dois códigos — e
 * não precisa, porque a resposta é o documento completo nos dois casos: se o
 * `page_count` não subiu, a retentativa já estava lá. Uma rede má não deve
 * parecer um erro.
 */
export function useAnexarFicheiro(): UseMutationResult<Documento, Error, FicheiroParaDocumento> {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: ({ documento, ficheiro }: FicheiroParaDocumento) => {
      const corpo = new FormData();
      corpo.append("ficheiro", ficheiro);
      return apiRequest(`${CAMINHO_DOCUMENTOS}/${documento}/files`, documentoSchema, {
        method: "POST",
        body: corpo,
      });
    },
    onSuccess: async () => {
      await invalidarDocumentos(queryClient, tenant);
    },
  });
}

/**
 * Fechar o documento: não vêm mais páginas.
 *
 * Repetível dentro do mesmo estado — fechar duas vezes devolve 200 e não agenda
 * trabalho duas vezes. Um documento **sem páginas** não se fecha (recusa
 * `documento_sem_paginas`): fechar é dizer "não vêm mais páginas", e dizê-lo de
 * um documento vazio pedia uma extração de nada. Esse morre pelo relógio.
 */
export function useFecharDocumento(): UseMutationResult<Documento, Error, string> {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (documento: string) =>
      apiRequest(`${CAMINHO_DOCUMENTOS}/${documento}/closing`, documentoSchema, {
        method: "POST",
      }),
    onSuccess: async () => {
      await invalidarDocumentos(queryClient, tenant);
    },
  });
}

/**
 * Descartar: descarte **suave**, com `204` e sem corpo.
 *
 * A linha fica com `discarded_at` e sai da lista; os bytes só são apagados se o
 * documento não tiver páginas — o original de um documento fiscal não se apaga
 * enquanto não houver política de retenção. É por isso que `apiRequestVoid` e
 * não `apiRequest`: não há documento para validar à saída.
 */
export function useDescartarDocumento(): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (documento: string) =>
      apiRequestVoid(`${CAMINHO_DOCUMENTOS}/${documento}`, { method: "DELETE" }),
    onSuccess: async () => {
      await invalidarDocumentos(queryClient, tenant);
    },
  });
}

/* ---------------------------------------------------------------------------
 * O endereço dos bytes de uma página **não** vive aqui, e a ausência é uma
 * decisão: o `image_url` vem no `PaginaOut`, é um caminho relativo construído
 * pelo `reverse` do Django, e montá-lo no cliente era uma segunda definição do
 * mesmo endereço — a que deixa de bater no dia em que o `urls.py` mudar. Quem
 * decide se vale a pena pedi-lo é o `normalized`, e hoje é sempre `false`.
 * ------------------------------------------------------------------------- */
