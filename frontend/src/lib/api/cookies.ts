/**
 * Leitura de cookies não-httpOnly. Só serve para o `csrftoken`.
 *
 * O cookie de sessão é httpOnly e não é legível daqui — de propósito
 * (SECURITY.md §2). Não há, e não pode haver, tokens em `localStorage` ou
 * `sessionStorage` (SECURITY.md §7): a autenticação é o cookie de sessão que o
 * browser envia sozinho.
 */
export function readCookie(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  for (const part of document.cookie.split("; ")) {
    if (part.startsWith(prefix)) {
      return decodeURIComponent(part.slice(prefix.length));
    }
  }
  return null;
}
