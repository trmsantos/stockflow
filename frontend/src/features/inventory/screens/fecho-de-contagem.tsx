import { Link, useSearch } from "@tanstack/react-router";
import { ArrowLeft, CircleCheck, ClipboardList, Lock } from "lucide-react";

import { EstadoVazio } from "@/components/estado-vazio";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CLASSE_CONTADOR, ReguaDeContadores } from "@/components/regua-de-contadores";
import { mensagemDeErro } from "@/lib/api/errors";

import {
  useContagemAberta,
  useFecharContagem,
  useFechoDeContagem,
  usePodeGerirContagens,
} from "../api";
import { ErroDaLista } from "../components/estados-da-lista";
import { FormularioDeFecho, ResumoDoFecho } from "../components/fecho-de-contagem";
import { textos } from "../textos";

/**
 * O fecho da contagem — "as diferenças, em quantidade e em euros" (guião §1).
 *
 * É aqui que a contagem toca no ledger, e **uma vez só**: cada diferença gera
 * um `adjustment` com a justificação, e nada reescreve um nível. O `GET` desta
 * pré-visualização não escreve nada e corre pelo **mesmo** algoritmo do `POST`
 * — o que se vê é o que vai acontecer, e não uma estimativa dele.
 *
 * **O ecrã é de `owner|manager`, e o servidor responde 403 a quem conta.** Por
 * isso quem não tem o papel não dispara o pedido: vê uma frase que diz de quem
 * é a ação e volta a contar. Não é controlo de acesso — é não bater numa porta
 * fechada, e é o que impede um 403 de aparecer como "erro ao calcular as
 * diferenças" num ecrã onde não há nada a corrigir.
 *
 * Fechar com diferenças é possível e fechar sem contar tudo também (guião §4,
 * proibição 3). O que o ecrã faz é mostrar o que vai acontecer — incluindo
 * **quais** linhas ficam de fora do ajuste — antes de acontecer.
 */

function Voltar() {
  return (
    <Button asChild variant="ghost" className="self-start">
      <Link to="/contar" search={() => ({})}>
        <ArrowLeft aria-hidden="true" />
        {textos.fecho.voltar}
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
  const podeGerir = usePodeGerirContagens();

  const fecho = useFechoDeContagem(id, podeGerir);
  const fechar = useFecharContagem();

  const dados = fecho.data;
  const fechada = dados?.status === "closed";

  return (
    // Largura toda da área de conteúdo, como o ecrã de Contar de onde se vem.
    // Tinha um cap de `42rem` e isso partia o par: a régua de contadores e a
    // lista de diferenças acabavam a meio do ecrã ao lado de uma lista de
    // contagem que ocupa tudo, e as duas são **o mesmo gesto**. O que continua a
    // ter cap é o que é formulário — o campo da justificação e o banner do que
    // fica por contar —, pela razão de leitura do DESIGN.md §4 e não de grelha.
    <section className="flex w-full flex-col gap-4 py-3">
      <Voltar />

      <h1 className="max-w-3xl px-celula-x text-2xl font-semibold text-balance">
        {fechada ? textos.fecho.fechada : textos.fecho.fechar}
      </h1>

      {!podeGerir ? (
        <EstadoVazio
          icone={Lock}
          titulo={textos.fecho.semPapelTitulo}
          descricao={textos.fecho.semPapelCorpo}
        >
          <Button asChild variant="outline">
            <Link to="/contar" search={() => ({})}>
              {textos.fecho.irParaContar}
            </Link>
          </Button>
        </EstadoVazio>
      ) : null}

      {podeGerir && id === undefined && !aberta.isPending ? (
        <EstadoVazio
          icone={ClipboardList}
          titulo={textos.fecho.semContagemTitulo}
          descricao={textos.fecho.semContagemCorpo}
        >
          <Button asChild variant="outline">
            <Link to="/contar" search={() => ({})}>
              {textos.fecho.irParaContar}
            </Link>
          </Button>
        </EstadoVazio>
      ) : null}

      {fecho.isPending && podeGerir && id !== undefined ? (
        <div aria-busy="true" className="flex flex-col gap-3">
          <span className="sr-only">{textos.fecho.aCarregar}</span>
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
          titulo={textos.fecho.erroAoCalcular}
          mensagem={mensagemDeErro(fecho.error)}
          aoTentarOutraVez={() => {
            void fecho.refetch();
          }}
        />
      ) : null}

      {dados === undefined ? null : (
        <>
          {fechada ? (
            <div className="max-w-3xl px-celula-x">
              <Alert className="border-success-border bg-success-surface">
                <CircleCheck aria-hidden="true" className="text-success" />
                <AlertTitle>{textos.fecho.fechadaTitulo}</AlertTitle>
                <AlertDescription>
                  {textos.fecho.fechadaCorpo}
                  {dados.closing_reason === null
                    ? ""
                    : textos.fecho.justificacao(dados.closing_reason)}
                </AlertDescription>
              </Alert>
            </div>
          ) : null}

          <ResumoDoFecho fecho={dados} />

          {fechada ? (
            <div className="flex flex-col items-start gap-2 px-celula-x">
              <Button asChild variant="outline">
                <Link to="/contar" search={() => ({})}>
                  {textos.fecho.voltarAContar}
                </Link>
              </Button>
            </div>
          ) : (
            <FormularioDeFecho
              fecho={dados}
              aFechar={fechar.isPending}
              erroDoServidor={fechar.isError ? fechar.error : null}
              aoFechar={(motivo) => {
                fechar.mutate({ contagem: dados.count, reason: motivo });
              }}
            />
          )}
        </>
      )}
    </section>
  );
}
