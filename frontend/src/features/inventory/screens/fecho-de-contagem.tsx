import { Link, useSearch } from "@tanstack/react-router";
import { ArrowLeft, CircleCheck, ClipboardList } from "lucide-react";

import { EstadoVazio } from "@/components/estado-vazio";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CLASSE_CONTADOR, ReguaDeContadores } from "@/components/regua-de-contadores";
import { mensagemDeErro } from "@/lib/api/errors";

import { useContagemAberta, useFecharContagem, useFechoDeContagem } from "../api";
import { ErroDaLista } from "../components/estados-da-lista";
import { FormularioDeFecho, ResumoDoFecho } from "../components/fecho-de-contagem";

/**
 * O fecho da contagem — "as diferenças, em quantidade e em euros" (guião §1).
 *
 * É aqui que a contagem toca no ledger, e **uma vez só**: cada diferença gera
 * um `adjustment` com a justificação, e nada reescreve um nível. É também aqui
 * que a zona cega revela o esperado — contar às cegas é para não ancorar quem
 * conta, não para esconder o resultado a quem assina.
 *
 * Fechar com diferenças é possível e fechar sem contar tudo também: bloquear é
 * a Q1, e o shell não responde por ela (guião §4, proibição 3). O que o ecrã
 * faz é mostrar o que vai acontecer antes de acontecer.
 */

function Voltar() {
  return (
    <Button asChild variant="ghost" className="self-start">
      <Link to="/contar" search={() => ({})}>
        <ArrowLeft aria-hidden="true" />
        Contar
      </Link>
    </Button>
  );
}

export function EcraDeFechoDeContagem() {
  const busca = useSearch({ from: "/app/contar/fechar" });
  // Sem `?contagem=` no URL — alguém que escreveu `/contar/fechar` à mão —, a
  // contagem aberta é o palpite certo, e vem da mesma entrada de cache que o
  // ecrã de contar já tem.
  const aberta = useContagemAberta();
  const id = busca.contagem ?? aberta.data?.id;

  const fecho = useFechoDeContagem(id);
  const fechar = useFecharContagem();

  const dados = fecho.data;
  const fechada = dados?.status === "closed";

  return (
    <section className="flex w-full max-w-2xl flex-col gap-4 py-3">
      <Voltar />

      <h1 className="px-4 text-2xl font-semibold text-balance">
        {fechada ? "Contagem fechada" : "Fechar contagem"}
      </h1>

      {id === undefined && !aberta.isPending ? (
        <EstadoVazio
          icone={ClipboardList}
          titulo="Não há contagem para fechar"
          descricao="Este endereço aponta para uma contagem que já não existe, ou não há nenhuma a decorrer."
        >
          <Button asChild variant="outline">
            <Link to="/contar" search={() => ({})}>
              Ir para Contar
            </Link>
          </Button>
        </EstadoVazio>
      ) : null}

      {fecho.isPending && id !== undefined ? (
        <div aria-busy="true" className="flex flex-col gap-3">
          <span className="sr-only">A carregar as diferenças…</span>
          {/* O esqueleto tem a forma da régua e não de três mosaicos: senão o
              layout salta no momento em que os totais chegam. */}
          <ReguaDeContadores>
            {[0, 1, 2].map((indice) => (
              <div key={indice} className={CLASSE_CONTADOR}>
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-8 w-20" />
              </div>
            ))}
          </ReguaDeContadores>
          <div className="flex flex-col gap-3 px-celula-x">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-14 w-full" />
          </div>
        </div>
      ) : null}

      {fecho.isError ? (
        <ErroDaLista
          titulo="Não foi possível calcular as diferenças"
          mensagem={mensagemDeErro(fecho.error)}
          aoTentarOutraVez={() => {
            void fecho.refetch();
          }}
        />
      ) : null}

      {dados === undefined ? null : (
        <>
          {fechada ? (
            <div className="px-4">
              <Alert className="border-success-border bg-success-surface">
                <CircleCheck aria-hidden="true" className="text-success" />
                <AlertTitle>Fechada, e o ajuste está no ledger</AlertTitle>
                <AlertDescription>
                  Cada diferença gerou um movimento de ajuste com o autor e a justificação. Nada
                  foi reescrito: para corrigir, conta-se outra vez.
                  {dados.closing_reason === null ? "" : ` Justificação: «${dados.closing_reason}».`}
                </AlertDescription>
              </Alert>
            </div>
          ) : null}

          <ResumoDoFecho fecho={dados} />

          {fechada ? (
            <div className="flex flex-col items-start gap-2 px-4">
              <Button asChild variant="outline">
                <Link to="/contar" search={() => ({})}>
                  Voltar a Contar
                </Link>
              </Button>
            </div>
          ) : (
            <FormularioDeFecho
              fecho={dados}
              aFechar={fechar.isPending}
              erroDoServidor={fechar.isError ? fechar.error : null}
              aoFechar={(motivo) => {
                fechar.mutate(
                  motivo === undefined
                    ? { contagem: dados.count }
                    : { contagem: dados.count, reason: motivo },
                );
              }}
            />
          )}
        </>
      )}
    </section>
  );
}
