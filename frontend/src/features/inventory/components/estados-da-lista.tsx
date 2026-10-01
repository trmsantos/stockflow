import { Link } from "@tanstack/react-router";
import { CircleAlert, PackageOpen, RotateCcw, Search } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Os três estados que a lista tem sempre (DESIGN.md §3) — e não são um extra:
 * "o que aparece quando não há nada?" é uma das perguntas da sessão 0, logo o
 * estado vazio é tanto produto como a lista cheia.
 *
 * O servidor de fixtures sabe devolver `results: []` e 500 por caminho
 * (`FIXTURES_VAZIO=…`, `FIXTURES_ERRO=…`, ou `?_fixture=vazio|erro` num `curl`),
 * por isso estes três ecrãs foram vistos e medidos, não deduzidos.
 */

/**
 * Pendente: **skeleton, não spinner**. Sete linhas porque sete é o que cabe nos
 * ~530px úteis de um 360×640 (guião §0), e com a altura certa para a lista não
 * saltar quando os dados chegarem.
 */
export function EsqueletoDaLista() {
  return (
    <div aria-busy="true" className="flex flex-col">
      <span className="sr-only">A carregar o stock…</span>
      {[0, 1, 2, 3, 4, 5, 6].map((indice) => (
        <div
          key={indice}
          className="flex min-h-14 flex-col justify-center gap-1.5 border-b border-border px-4 py-2"
        >
          <div className="flex items-center justify-between gap-3">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-20" />
          </div>
          <div className="flex items-center gap-2">
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-3 w-24" />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Erro: com retry, porque numa cozinha a causa mais provável é o Wi-Fi. */
export function ErroDaLista({
  mensagem,
  aoTentarOutraVez,
}: {
  readonly mensagem: string;
  readonly aoTentarOutraVez: () => void;
}) {
  return (
    <div className="px-4 py-3">
      <Alert className="border-danger-border bg-danger-surface">
        <CircleAlert aria-hidden="true" className="text-danger" />
        <AlertTitle>Não foi possível carregar o stock</AlertTitle>
        <AlertDescription className="flex flex-col items-start gap-2">
          <span>{mensagem}</span>
          <Button variant="outline" onClick={aoTentarOutraVez}>
            <RotateCcw aria-hidden="true" />
            Tentar outra vez
          </Button>
        </AlertDescription>
      </Alert>
    </div>
  );
}

/**
 * Vazio, em duas variantes, porque são duas situações diferentes e a ação
 * seguinte não é a mesma: não há stock nenhum (o caminho é receber mercadoria)
 * ou os filtros não deixaram passar nada (o caminho é limpá-los).
 */
export function ListaVazia({ comFiltros }: { readonly comFiltros: boolean }) {
  if (comFiltros) {
    return (
      <div className="flex flex-col items-start gap-3 px-4 py-8">
        <Search aria-hidden="true" className="size-6 text-muted-foreground" />
        <div className="flex flex-col gap-1">
          <p className="font-medium">Nenhum artigo corresponde</p>
          <p className="text-pretty text-sm text-muted-foreground">
            A procura e os filtros do topo não deixaram passar nada. O stock continua lá.
          </p>
        </div>
        <Button asChild variant="outline">
          {/* Um reducer que devolve o objeto vazio limpa os três filtros do URL
              de uma vez — e é um link, logo funciona com o clique do meio. */}
          <Link to="/stock" search={() => ({})}>
            Limpar filtros
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-start gap-3 px-4 py-8">
      <PackageOpen aria-hidden="true" className="size-6 text-muted-foreground" />
      <div className="flex flex-col gap-1">
        <p className="font-medium">Ainda não há stock registado</p>
        <p className="text-pretty text-sm text-muted-foreground">
          O stock aparece aqui à medida que a mercadoria entra. Comece por uma entrada de
          fornecedor.
        </p>
      </div>
      <Button asChild>
        <Link to="/receber">Receber mercadoria</Link>
      </Button>
    </div>
  );
}
