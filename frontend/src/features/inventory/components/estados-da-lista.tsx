import { Link } from "@tanstack/react-router";
import { PackageOpen, Search } from "lucide-react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { EstadoVazio } from "@/components/estado-vazio";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { textos } from "../textos";

/**
 * Os três estados que a lista tem sempre (DESIGN.md §3) — e não são um extra:
 * "o que aparece quando não há nada?" é uma das perguntas da sessão 0, logo o
 * estado vazio é tanto produto como a lista cheia.
 *
 * Até 2026-10-27 os três viam-se por encomenda: o servidor de fixtures devolvia
 * `results: []` ou 500 a pedido (`?_fixture=vazio|erro`). Com a pasta apagada
 * (ADR 0034, decisão 7) **esse gatilho deixou de existir**. O vazio continua a
 * ver-se com uma procura sem correspondência ou um estabelecimento sem stock;
 * o erro e a sessão expirada **não têm hoje forma de se provocar**, e isso é
 * uma perda nomeada da fatia, não um esquecimento.
 */

/**
 * Pendente: **skeleton, não spinner**. Sete linhas porque sete é o que cabe nos
 * ~530px úteis de um 360×640 (guião §0), e com a altura certa para a lista não
 * saltar quando os dados chegarem.
 *
 * O rótulo entra por propriedade porque os três ecrãs de inventário usam o
 * mesmo esqueleto e quem ouve o ecrã tem de saber o que está a carregar — "a
 * carregar o stock" num ecrã de alertas é pior do que não dizer nada.
 */
export function EsqueletoDaLista({
  rotulo = textos.accoes.aCarregarStock,
  linhas = 7,
}: {
  readonly rotulo?: string;
  readonly linhas?: number;
} = {}) {
  return (
    <div aria-busy="true" className="flex flex-col">
      <span className="sr-only">{rotulo}</span>
      {Array.from({ length: linhas }, (_, indice) => indice).map((indice) => (
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

/**
 * Erro: com retry, porque numa cozinha a causa mais provável é o Wi-Fi.
 *
 * O bloco desceu para `@/components/erro-ao-carregar` quando o ecrã Receber
 * passou a precisar do mesmo (ADR 0008, decisão 2). O que fica aqui é só o
 * **default do título** deste módulo: lá o título é obrigatório, de propósito,
 * para um ecrã de faturas não poder dizer "não foi possível carregar o stock".
 */
export function ErroDaLista({
  titulo = textos.lista.erroDeStock,
  mensagem,
  aoTentarOutraVez,
}: {
  readonly titulo?: string;
  readonly mensagem: string;
  readonly aoTentarOutraVez: () => void;
}) {
  return (
    <ErroAoCarregar titulo={titulo} mensagem={mensagem} aoTentarOutraVez={aoTentarOutraVez} />
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
      <EstadoVazio
        icone={Search}
        titulo={textos.lista.semCorrespondenciaTitulo}
        descricao={textos.lista.semCorrespondenciaCorpo}
      >
        <Button asChild variant="outline">
          {/* Um reducer que devolve o objeto vazio limpa os três filtros do URL
              de uma vez — e é um link, logo funciona com o clique do meio. */}
          <Link to="/stock" search={() => ({})}>
            {textos.lista.limparFiltros}
          </Link>
        </Button>
      </EstadoVazio>
    );
  }

  return (
    <EstadoVazio
      icone={PackageOpen}
      titulo={textos.lista.vazioTitulo}
      descricao={textos.lista.vazioCorpo}
    >
      <Button asChild>
        <Link to="/receber">{textos.lista.receberMercadoria}</Link>
      </Button>
    </EstadoVazio>
  );
}
