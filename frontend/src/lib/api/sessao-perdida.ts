/**
 * A sessão deixou de servir a meio — o caminho que a tarefa do login deixou
 * devido, de propósito (`routes/app.tsx`: "um 403 `sem_sessao` num pedido de
 * dados tem de trazer a pessoa de volta a `/entrar`, e isso é do shell").
 *
 * ## Porque é que isto é um registo e não um import
 *
 * Quem **deteta** é o `http.ts`, que está em `lib/` e não conhece nem o router
 * nem a cache — e não pode conhecer: `lib/` é o `apps/shared` do frontend e não
 * importa nada de cima (ADR 0008, decisão 2). Quem **reage** precisa dos dois: a
 * cache, para esquecer a sessão e os dados do estabelecimento, e o router, para
 * levar a pessoa a `/entrar` com o `destino` preenchido. A ligação é feita no
 * sítio onde os dois existem (`routes/router.tsx`, chamado do `App.tsx`), e
 * chega aqui por registo.
 *
 * É a mesma forma — e pela mesma razão — que o `tenant.ts` já tem para o
 * estabelecimento ativo: um valor de módulo, em memória, com uma porta de
 * entrada e uma de saída. **Nada disto vai para `localStorage`** (SECURITY.md
 * §7).
 *
 * ## Um tratador só, e substituível
 *
 * Há uma aplicação e um router por processo. Um conjunto de subscritores daria
 * a ilusão de que dois sítios podem reagir, e o segundo seria o que ninguém se
 * lembra que existe. O registo devolve a função de remoção para o efeito do
 * `App.tsx` poder limpar o que registou — sem isso, um remount em
 * desenvolvimento deixava o tratador a apontar para o router anterior.
 */

/**
 * `sem_sessao` — 403 do `TenantMiddleware` (`apps/accounts/middleware.py`).
 *
 * Quer dizer **duas** coisas e é por isso que o cliente não ramifica aqui: "não
 * há utilizador autenticado" **ou** "a sessão não nomeia estabelecimento
 * nenhum". As duas se resolvem no mesmo sítio — o `/entrar` distingue os quatro
 * estados da sessão e mostra o formulário, o seletor ou a frase própria —, e é
 * essa a razão pela qual este caminho leva a uma rota e não a um ecrã.
 */
export const CODIGO_SEM_SESSAO = "sem_sessao";

type TratadorDePerda = () => void;

let tratador: TratadorDePerda | null = null;

/** Registar quem reage. Devolve a função que desfaz o registo. */
export function registarPerdaDeSessao(novo: TratadorDePerda): () => void {
  tratador = novo;
  return () => {
    if (tratador === novo) tratador = null;
  };
}

/**
 * Anunciar que um pedido de dados foi recusado por falta de âmbito.
 *
 * Não faz dedupe, e isso é uma decisão: uma rajada de 403s do mesmo instante
 * (três ecrãs montados, três queries) chama isto três vezes, e as três chegam ao
 * mesmo tratador, que é idempotente — o segundo `navigate` para a mesma
 * localização é colapsado pelo próprio router (`isSameLocation`), e esquecer uma
 * cache já esquecida não faz nada. Um guarda de tempo aqui seria estado a mais
 * para poupar trabalho que não custa.
 */
export function anunciarPerdaDeSessao(): void {
  tratador?.();
}
