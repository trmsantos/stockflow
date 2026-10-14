import { Link } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";

import { EstadoVazio } from "@/components/estado-vazio";
import { Button } from "@/components/ui/button";
import { mensagemDeErro } from "@/lib/api/errors";

import { useArtigos, useCriarArtigo } from "../api";
import { TabelaDeProdutos } from "../components/tabela-de-produtos";
import { SkeletonTabelaDeProdutos } from "../components/skeleton-tabela-de-produtos";
import { ErroAoCarregar } from "../components/erro-ao-carregar";
import { textos } from "../textos";

/**
 * O ecrã Produtos — o catálogo de artigos do estabelecimento.
 *
 * Uma tabela densa com: nome, SKU, unidade, rastreio de lotes, quantidade mínima, ativo.
 * As ações principais são: criar produto, editar, ativar/desativar.
 *
 * Stock é um ledger e não se edita aqui: só o domínio do catálogo (nome, unidades,
 * rastreio). Quem quer mexer no stock vai ao detalhe do artigo em Stock ou Alertas.
 *
 * RLS: cada tenant vê só seus produtos.
 */

export function EcraDeProdutos() {
  const [termo, setTermo] = useState("");

  const produtos = useArtigos(termo);
  const criarArtigo = useCriarArtigo();

  const linhas = produtos.data?.results;
  const estaVazio = linhas?.length === 0;
  const temErro = produtos.isError;
  const estaCarregando = produtos.isPending;

  return (
    <section className="flex w-full flex-col gap-ritmo">
      <header className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">
          {textos.catalogo.titulo} ({linhas?.length ?? 0})
        </h1>
        <Button asChild className="gap-1.5">
          <Link to="/produtos/novo">
            <Plus className="size-4" />
            {textos.accoes.novoArtigo}
          </Link>
        </Button>
      </header>

      {/* Campo de procura — opcional, mas útil em catálogos maiores */}
      <div className="flex gap-2">
        <input
          type="text"
          placeholder={textos.catalogo.procurar}
          value={termo}
          onChange={(e) => {
            setTermo(e.target.value);
          }}
          className="flex-1 rounded border border-border-strong bg-surface px-3 py-2 text-sm"
          aria-label={textos.catalogo.procurarAriaLabel}
        />
      </div>

      {/* Estados: loading, empty, error */}
      {estaCarregando ? <SkeletonTabelaDeProdutos /> : null}

      {temErro ? (
        <ErroAoCarregar
          mensagem={mensagemDeErro(produtos.error)}
          aoTentarOutraVez={() => {
            void produtos.refetch();
          }}
        />
      ) : null}

      {estaVazio ? (
        <EstadoVazio
          icone={Plus}
          titulo={textos.catalogo.nenhum}
          descricao={textos.catalogo.nenhumDescricao}
        >
          <Button asChild variant="outline">
            <Link to="/produtos/novo">
              {textos.accoes.criarPrimeiroArtigo}
            </Link>
          </Button>
        </EstadoVazio>
      ) : null}

      {linhas !== undefined && linhas.length > 0 ? (
        <TabelaDeProdutos produtos={linhas} />
      ) : null}

      {/* Aviso se há mutação em progresso */}
      {criarArtigo.isPending ? (
        <p className="px-celula-x py-2 text-sm text-muted-foreground">
          {textos.accoes.aCriarArtigo}
        </p>
      ) : null}

      {criarArtigo.isError ? (
        <p className="px-celula-x py-2 text-sm text-danger">
          Erro ao criar: {mensagemDeErro(criarArtigo.error)}
        </p>
      ) : null}
    </section>
  );
}
