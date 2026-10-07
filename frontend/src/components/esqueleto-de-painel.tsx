import { Skeleton } from "@/components/ui/skeleton";
import { textos } from "./textos";

/**
 * O estado pendente de um painel com um formulário: **skeleton e não spinner**
 * (DESIGN.md §3).
 *
 * Vive em `src/components/` e não no `shell/` nem numa feature porque tem dois
 * consumidores em **camadas diferentes** e nenhum domínio: o `pendingComponent`
 * das rotas do ramo público (enquanto o chunk da rota chega) e o ecrã de entrada
 * (enquanto o `GET /auth/sessao` responde). São dois momentos diferentes da
 * mesma espera, e duas cópias de cinco barras divergiam na primeira correção.
 *
 * As barras aproximam o que vem a seguir — título, uma linha de texto, dois
 * controlos e um botão — para o painel não saltar de altura quando os dados
 * chegarem. A altura dos controlos é o token `h-controlo` (40px), a mesma dos
 * inputs que vão ocupar o lugar.
 *
 * O pulsar é opacidade, logo sobrevive ao `prefers-reduced-motion` com a
 * excepção que o `base.css` declara: é o único sinal de que há algo a carregar.
 */
export function EsqueletoDePainel() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true">
      <span className="sr-only">{textos.aCarregar}</span>
      <Skeleton className="h-7 w-32" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-controlo w-full" />
      <Skeleton className="h-controlo w-full" />
      <Skeleton className="h-controlo w-28" />
    </div>
  );
}
