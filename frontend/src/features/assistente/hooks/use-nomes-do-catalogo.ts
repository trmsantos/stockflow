import { useMemo } from "react";

// A **única** porta para outra feature (ADR 0008, decisão 2): o `api.ts` do
// `catalog`. É de lá que vêm os nomes dos artigos, lojas e fornecedores que o
// rodapé "Fontes" mostra no lugar dos uuids que o modelo escreveu.
import { useArtigos, useFornecedores, useLocalizacoes } from "@/features/catalog/api";

/** Resolve um id em nome, ou `null` quando o catálogo (ainda) não o conhece. */
export interface NomesDoCatalogo {
  readonly artigo: (id: string) => string | null;
  readonly loja: (id: string) => string | null;
  readonly fornecedor: (id: string) => string | null;
}

/**
 * Os nomes do catálogo, para o rodapé "Fontes" dizer «Farinha T65» em vez de
 * um uuid.
 *
 * O rasto de uma tool guarda os argumentos **como o modelo os escreveu** (ADR
 * 0027, decisão 1), e o modelo fala por id: `saldo_de_artigo(product_id)`. O
 * nome não está lá, e não se pede ao servidor que o ponha — seria uma segunda
 * forma de serializar o rasto só para o ecrã. Está no catálogo, que o ecrã de
 * Produtos já lê com as mesmas chaves de cache, logo é uma leitura partilhada e
 * não um pedido a mais por turno.
 *
 * Chamado **dentro** do rodapé e não no ecrã: o rodapé só existe num turno com
 * tools chamadas, e uma conversa que ainda não tem nenhum não paga as três
 * listas. O TanStack Query funde os pedidos dos vários rodapés numa consulta.
 *
 * Um erro em qualquer das três não é um erro do turno: o rodapé mostra a tool
 * sem o nome, que é o que mostraria se o artigo tivesse sido apagado.
 */
export function useNomesDoCatalogo(): NomesDoCatalogo {
  const artigos = useArtigos();
  const lojas = useLocalizacoes();
  const fornecedores = useFornecedores();

  return useMemo(() => {
    const porArtigo = new Map(
      (artigos.data?.results ?? []).map((artigo) => [artigo.id, artigo.short_name]),
    );
    const porLoja = new Map((lojas.data?.results ?? []).map((loja) => [loja.id, loja.name]));
    const porFornecedor = new Map(
      (fornecedores.data?.results ?? []).map((fornecedor) => [fornecedor.id, fornecedor.name]),
    );
    return {
      artigo: (id) => porArtigo.get(id) ?? null,
      loja: (id) => porLoja.get(id) ?? null,
      fornecedor: (id) => porFornecedor.get(id) ?? null,
    };
  }, [artigos.data, lojas.data, fornecedores.data]);
}
