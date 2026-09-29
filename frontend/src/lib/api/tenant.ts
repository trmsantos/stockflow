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
