import { Link, useSearch } from "@tanstack/react-router";
import { ArrowLeft, ArrowRight, Camera } from "lucide-react";

import { EstadoVazio } from "@/components/estado-vazio";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { useRececoes } from "../api";

/**
 * O destino do botão da câmara, num shell que não tem câmara.
 *
 * O guião pede "fotografar a fatura, câmara a um toque". Num telemóvel esse
 * toque abre a câmara; aqui não há câmara, não há envio de ficheiro e não há
 * leitura de documento — e o que este ecrã faz é **dizer isso** e levar ao sítio
 * onde o fluxo continua de verdade: a receção que está à espera de revisão.
 *
 * Porque não um `<input type="file" capture>`, que abriria a câmara a sério: no
 * fim dela não há nada. Tirar a fotografia e não acontecer nada é a única coisa
 * pior do que não ter o botão — promete-se o produto todo e entrega-se um ecrã
 * em branco, e a sessão passa a ser sobre o que falhou.
 *
 * O texto do meio não é desculpa: são **os três caminhos por onde a mercadoria
 * entra** numa cozinha portuguesa (guião §2), e é a lista que se quer que ele
 * corrija ou complete. Se ele disser "falta aqui o telefone do fornecedor a
 * ditar-me a encomenda", isso é o achado.
 */
export function EcraDeFotografar() {
  const busca = useSearch({ from: "/app/receber/fotografar" });
  const porRever = useRececoes("revisao");
  const primeira = porRever.data?.results[0];

  return (
    <section className="flex w-full max-w-2xl flex-col gap-4 py-3">
      <Button asChild variant="ghost" className="self-start">
        <Link to="/receber" search={busca}>
          <ArrowLeft aria-hidden="true" />
          Receber
        </Link>
      </Button>

      <h1 className="px-4 text-2xl font-semibold text-balance">Fotografar fatura</h1>

      <div className="px-4">
        <Alert className="border-border-strong bg-surface-2">
          <Camera aria-hidden="true" />
          <AlertTitle>Neste ecrã ainda não há câmara</AlertTitle>
          <AlertDescription className="text-pretty">
            No telemóvel este botão abre a câmara e a fotografia fica anexada ao documento. Aqui não
            há câmara nem leitura do documento: a receção que está à espera de revisão foi preenchida
            à mão, para se poder percorrer a revisão de ponta a ponta — que é a parte que decide se o
            stock muda.
          </AlertDescription>
        </Alert>
      </div>

      <div className="flex flex-col gap-2 px-4">
        <h2 className="text-sm font-semibold">Por onde é que a mercadoria entra</h2>
        <ul className="flex flex-col gap-2 text-sm text-muted-foreground">
          {/* A regra, não a hipótese: a receção existe sem encomenda e sem
              fatura (guião §5). Se o modelo exigir uma encomenda para receber,
              está errado para o mercado português. */}
          <li className="text-pretty">
            <span className="font-medium text-foreground">Fatura ou fatura simplificada</span>, de
            uma ida ao cash & carry: sem encomenda, sem guia, a mercadoria vem na carrinha e o
            documento vem na mão.
          </li>
          <li className="text-pretty">
            <span className="font-medium text-foreground">Guia de remessa</span>, do distribuidor: a
            mercadoria entra primeiro e a fatura vem a fim de mês, a reconciliar várias entregas.
          </li>
          <li className="text-pretty">
            <span className="font-medium text-foreground">Sem documento nenhum</span>, ou com um
            escrito à mão no mercado: também tem de dar entrada, e o documento aparece depois.
          </li>
        </ul>
      </div>

      {porRever.isPending ? (
        <div aria-busy="true" className="px-4">
          <span className="sr-only">A procurar receções por revisar…</span>
          <Skeleton className="h-10 w-56" />
        </div>
      ) : primeira === undefined ? (
        <EstadoVazio
          icone={Camera}
          titulo="Não há nada à espera de revisão"
          descricao="Quando um documento novo entrar, aparece na lista a precisar de revisão — e o stock só muda depois de alguém confirmar as linhas."
        >
          <Button asChild variant="outline">
            <Link to="/receber" search={() => ({})}>
              Ver as receções
            </Link>
          </Button>
        </EstadoVazio>
      ) : (
        <div className="flex flex-col items-start gap-1.5 px-4">
          <Button asChild>
            <Link to="/receber/$rececao" params={{ rececao: primeira.id }} search={busca}>
              Rever {primeira.supplier.name}
              <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
          <p className="text-xs text-muted-foreground">
            {primeira.doc_number ?? "sem número"} ·{" "}
            {primeira.lines_to_review === 1
              ? "1 linha por rever"
              : `${String(primeira.lines_to_review)} linhas por rever`}
          </p>
        </div>
      )}
    </section>
  );
}
