/**
 * O estabelecimento (tenant) ativo, em memória e só em memória.
 *
 * Quem escolhe o âmbito é a sessão do servidor, e a política de RLS é que o
 * concede (ADR 0007). Este valor é apenas o que o cliente *acha* que está
 * ativo, e serve para uma coisa: ir no header `X-Tenant-ID` para que o
 * servidor responda 409 se divergir, em vez de servir dados do
 * estabelecimento errado a um ecrã que ficou aberto.
 *
 * Não vai para `localStorage` nem `sessionStorage`. Além da regra do
 * SECURITY.md §7, guardá-lo criava uma segunda fonte de verdade que só sabe
 * ficar desatualizada — e cujo único efeito possível é gerar 409s.
 */
let activeTenantId: string | null = null;

export function getActiveTenantId(): string | null {
  return activeTenantId;
}

export function setActiveTenantId(tenantId: string | null): void {
  activeTenantId = tenantId;
}

/**
 * O estabelecimento à cabeça das chaves de query (`query-keys.ts`).
 *
 * Enquanto não há autenticação, o cliente não sabe qual é o estabelecimento da
 * sessão — e não tem de saber: quem escolhe o âmbito é a sessão do servidor e
 * quem o concede é a política de RLS (ADR 0007). O que a cache precisa é de um
 * nome estável para "o estabelecimento desta sessão, qualquer que ele seja",
 * para que no dia em que o login existir as chaves passem a levar o id real e
 * as entradas antigas deixem de casar — que é exactamente o efeito desejado.
 *
 * Não é uma credencial nem viaja em pedido nenhum: o header `X-Tenant-ID` sai
 * do `getActiveTenantId()`, e quando é `null` não é enviado.
 */
const TENANT_DA_SESSAO = "sessao";

export function tenantDaCache(): string {
  return activeTenantId ?? TENANT_DA_SESSAO;
}
