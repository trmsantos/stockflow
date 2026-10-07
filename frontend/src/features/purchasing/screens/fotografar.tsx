import { Link, useSearch } from "@tanstack/react-router";
import { ArrowLeft, ArrowRight, Camera } from "lucide-react";

import { EstadoVazio } from "@/components/estado-vazio";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { useRececoes } from "../api";
import { textos } from "../textos";

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
          {textos.comuns.receber}
        </Link>
      </Button>

      {/* O mesmo texto do botão que traz para cá: é o nome deste ecrã. */}
      <h1 className="px-4 text-2xl font-semibold text-balance">
        {textos.comuns.fotografarFatura}
      </h1>

      <div className="px-4">
        <Alert className="border-border-strong bg-surface-2">
          <Camera aria-hidden="true" />
          <AlertTitle>{textos.fotografar.semCamaraTitulo}</AlertTitle>
          <AlertDescription className="text-pretty">
            {textos.fotografar.semCamaraCorpo}
          </AlertDescription>
        </Alert>
      </div>

      <div className="flex flex-col gap-2 px-4">
        <h2 className="text-sm font-semibold">{textos.fotografar.porOndeEntra}</h2>
        {/* Cada frase em duas partes nomeadas: o nome do documento vai no
            `<span>` com peso, e juntá-las numa string perdia essa ênfase. */}
        <ul className="flex flex-col gap-2 text-sm text-muted-foreground">
          {/* A regra, não a hipótese: a receção existe sem encomenda e sem
              fatura (guião §5). Se o modelo exigir uma encomenda para receber,
              está errado para o mercado português. */}
          <li className="text-pretty">
            <span className="font-medium text-foreground">{textos.fotografar.faturaEnfase}</span>
            {textos.fotografar.faturaFim}
          </li>
          <li className="text-pretty">
            <span className="font-medium text-foreground">{textos.fotografar.guiaEnfase}</span>
            {textos.fotografar.guiaFim}
          </li>
          <li className="text-pretty">
            <span className="font-medium text-foreground">
              {textos.fotografar.semDocumentoEnfase}
            </span>
            {textos.fotografar.semDocumentoFim}
          </li>
        </ul>
      </div>

      {porRever.isPending ? (
        <div aria-busy="true" className="px-4">
          <span className="sr-only">{textos.fotografar.aProcurar}</span>
          <Skeleton className="h-10 w-56" />
        </div>
      ) : primeira === undefined ? (
        <EstadoVazio
          icone={Camera}
          titulo={textos.fotografar.semRevisaoTitulo}
          descricao={textos.fotografar.semRevisaoCorpo}
        >
          <Button asChild variant="outline">
            <Link to="/receber" search={() => ({})}>
              {textos.comuns.verAsRececoes}
            </Link>
          </Button>
        </EstadoVazio>
      ) : (
        <div className="flex flex-col items-start gap-1.5 px-4">
          <Button asChild>
            <Link to="/receber/$rececao" params={{ rececao: primeira.id }} search={busca}>
              {textos.fotografar.rever(primeira.supplier.name)}
              <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
          <p className="text-xs text-muted-foreground">
            {primeira.doc_number ?? textos.comuns.semNumero} ·{" "}
            {textos.comuns.linhasPorRever(primeira.lines_to_review)}
          </p>
        </div>
      )}
    </section>
  );
}
