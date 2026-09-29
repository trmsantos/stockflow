/**
 * Erros da API, com a forma que o backend garante.
 *
 * As recusas de âmbito de tenant respondem `{code, detail}` com um `code`
 * estável (`apps/accounts/middleware.py`): `sem_sessao` (403),
 * `tenant_desconhecido` (403) e `tenant_divergente` (409). O `detail` vem
 * pronto para mostrar e já diz o passo seguinte; a UI não o reescreve.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly detail: string | null;
  readonly payload: unknown;

  constructor(args: {
    status: number;
    code: string | null;
    detail: string | null;
    payload: unknown;
    message: string;
  }) {
    super(args.message);
    this.name = "ApiError";
    this.status = args.status;
    this.code = args.code;
    this.detail = args.detail;
    this.payload = args.payload;
  }
}

/**
 * 409: o `X-Tenant-ID` que o cliente declarou não é o estabelecimento da
 * sessão. O header nunca escolhe âmbito — só pode recusar (ADR 0007) —, por
 * isso a única reação correta é recarregar e voltar a ler o âmbito da sessão,
 * nunca tentar outro tenant.
 */
export class TenantConflictError extends ApiError {
  constructor(args: { detail: string | null; payload: unknown }) {
    super({
      status: 409,
      code: "tenant_divergente",
      detail: args.detail,
      payload: args.payload,
      message: "O estabelecimento do pedido não é o da sessão.",
    });
    this.name = "TenantConflictError";
  }
}

/** A resposta não passou o schema Zod: o servidor devolveu algo inesperado. */
export class ResponseShapeError extends Error {
  constructor(path: string, cause: unknown) {
    // O erro do Zod vai em `cause`: o `message` é para mostrar, o `cause` é
    // para o log.
    super(`A resposta de ${path} não tem a forma esperada.`, { cause });
    this.name = "ResponseShapeError";
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}
