import type { z } from "zod";

import { readCookie } from "./cookies";
import { ApiError, ResponseShapeError, TenantConflictError } from "./errors";
import { anunciarPerdaDeSessao, CODIGO_SEM_SESSAO } from "./sessao-perdida";
import { getActiveTenantId } from "./tenant";
import { textos } from "../textos";

/**
 * Cliente HTTP da API.
 *
 * Três decisões que não são negociáveis (SECURITY.md §7):
 *  - `credentials: "include"` — a autenticação é o cookie de sessão httpOnly;
 *    não há token nenhum guardado em JS.
 *  - `X-CSRFToken` lido do cookie `csrftoken` em todos os métodos que escrevem.
 *  - a URL é relativa (`/api/v1/...`): mesma origem que a app, em dev pelo
 *    proxy do Vite e em produção pelo Caddy. Não há `VITE_API_URL` — uma base
 *    de URL configurável seria também uma forma de apontar a app a outro host,
 *    e a CSP de produção (`connect-src 'self'`) proíbe-o de qualquer maneira.
 */
const API_BASE = "/api/v1";
const CSRF_COOKIE = "csrftoken";
const CSRF_HEADER = "X-CSRFToken";
const TENANT_HEADER = "X-Tenant-ID";

const METHODS_WITHOUT_CSRF = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export type QueryValue = string | number | boolean | null | undefined;

export interface ApiRequestInit {
  method?: HttpMethod;
  /** Serializado como JSON. Para upload de ficheiros, passa um `FormData`. */
  body?: unknown;
  query?: Readonly<Record<string, QueryValue>>;
  signal?: AbortSignal;
}

function buildUrl(path: string, query: ApiRequestInit["query"]): string {
  const url = `${API_BASE}${path}`;
  if (!query) return url;
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null) continue;
    search.set(key, String(value));
  }
  const serialized = search.toString();
  return serialized ? `${url}?${serialized}` : url;
}

function buildBody(body: unknown): { body?: BodyInit; contentType?: string } {
  if (body === undefined) return {};
  if (body instanceof FormData) return { body };
  return { body: JSON.stringify(body), contentType: "application/json" };
}

async function readPayload(response: Response): Promise<unknown> {
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("json")) return null;
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

function errorFields(payload: unknown): { code: string | null; detail: string | null } {
  if (typeof payload !== "object" || payload === null) {
    return { code: null, detail: null };
  }
  const record = payload as Record<string, unknown>;
  return {
    code: typeof record.code === "string" ? record.code : null,
    detail: typeof record.detail === "string" ? record.detail : null,
  };
}

async function send(path: string, init: ApiRequestInit): Promise<Response> {
  const method = init.method ?? "GET";
  const headers = new Headers({ Accept: "application/json" });

  if (!METHODS_WITHOUT_CSRF.has(method)) {
    const csrfToken = readCookie(CSRF_COOKIE);
    if (csrfToken === null) {
      // Falhar aqui, com uma instrução, em vez de deixar sair um pedido que o
      // Django recusa com um 403 de CSRF que ninguém sabe ler.
      throw new ApiError({
        status: 0,
        code: "csrf_ausente",
        detail: textos.erros.csrfAusente,
        payload: null,
        message: "Cookie csrftoken ausente.",
      });
    }
    headers.set(CSRF_HEADER, csrfToken);
  }

  // O tenant que o cliente acha que está ativo. Só pode causar 409; nunca
  // seleciona âmbito nenhum.
  const tenantId = getActiveTenantId();
  if (tenantId !== null) headers.set(TENANT_HEADER, tenantId);

  const { body, contentType } = buildBody(init.body);
  if (contentType !== undefined) headers.set("Content-Type", contentType);

  return fetch(buildUrl(path, init.query), {
    method,
    headers,
    credentials: "include",
    ...(body === undefined ? {} : { body }),
    ...(init.signal === undefined ? {} : { signal: init.signal }),
  });
}

function throwForStatus(path: string, response: Response, payload: unknown): never {
  const { code, detail } = errorFields(payload);
  if (response.status === 409 && code === "tenant_divergente") {
    throw new TenantConflictError({ detail, payload });
  }

  // A sessão deixou de servir a meio: anuncia-se **e continua a lançar**.
  //
  // As duas metades são precisas e fazem coisas diferentes. O anúncio leva a
  // pessoa de volta a `/entrar` com o `destino` preenchido (ver
  // `sessao-perdida.ts`); o `throw` faz a query falhar, o que impede o ecrã de
  // renderizar como se tivesse dados e deixa o estado de erro no sítio durante
  // o instante em que a navegação acontece. Engolir o erro aqui dava uma
  // promise pendente para sempre e um skeleton eterno se a navegação falhasse.
  //
  // Fica no `throwForStatus` e não em cada `api.ts` porque é a **única** forma
  // de recusa que vale para todos os endpoints com âmbito, e porque uma
  // verificação por feature é a que falta na quinta.
  if (response.status === 403 && code === CODIGO_SEM_SESSAO) {
    anunciarPerdaDeSessao();
  }
  throw new ApiError({
    status: response.status,
    code,
    detail,
    payload,
    message: detail ?? `${String(response.status)} em ${path}`,
  });
}

/**
 * Faz o pedido e valida a resposta com Zod.
 *
 * O schema é obrigatório por construção: o SECURITY.md §4 pede Zod em todas as
 * respostas, e um parâmetro opcional seria esquecido no primeiro endpoint com
 * pressa. O que sai daqui tem o tipo do schema, não `any` do JSON.
 */
export async function apiRequest<Schema extends z.ZodType>(
  path: string,
  schema: Schema,
  init: ApiRequestInit = {},
): Promise<z.output<Schema>> {
  const response = await send(path, init);
  const payload = await readPayload(response);
  if (!response.ok) throwForStatus(path, response, payload);

  const parsed = schema.safeParse(payload);
  if (!parsed.success) throw new ResponseShapeError(path, parsed.error);
  return parsed.data;
}

/** Para respostas sem corpo (204). */
export async function apiRequestVoid(path: string, init: ApiRequestInit = {}): Promise<void> {
  const response = await send(path, init);
  if (!response.ok) throwForStatus(path, response, await readPayload(response));
}
