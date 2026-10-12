import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";

import { apiRequest } from "@/lib/api/http";
import { paginated, type Paginated } from "@/lib/api/pagination";
import { queryKeys } from "@/lib/api/query-keys";
import { tenantDaCache } from "@/lib/api/tenant";

import {
  embalagemParaCriarSchema,
  embalagemSchema,
  fornecedorParaCriarSchema,
  fornecedorSchema,
  localizacaoParaCriarSchema,
  localizacaoSchema,
  produtoParaCriarSchema,
  produtoSchema,
  type Embalagem,
  type EmbalagemParaCriar,
  type Fornecedor,
  type FornecedorParaCriar,
  type Localizacao,
  type LocalizacaoParaCriar,
  type Produto,
  type ProdutoParaCriar,
} from "./schemas";

const CAMINHO_PRODUTOS = "/products";
const CAMINHO_FORNECEDORES = "/suppliers";
const CAMINHO_LOCALIZACOES = "/locations";

const RECURSO_PRODUTOS = "catalog-products";
const RECURSO_EMBALAGENS = "catalog-packagings";
const RECURSO_FORNECEDORES = "catalog-suppliers";
const RECURSO_LOCALIZACOES = "inventory-locations";

/**
 * Lista de produtos do catálogo com paginação e busca.
 */
export function useArtigos(q = ""): UseQueryResult<Paginated<Produto>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_PRODUTOS, { q }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_PRODUTOS, paginated(produtoSchema), {
        query: { q, active: "" },
        signal,
      }),
  });
}

/**
 * Criar um novo produto com embalagem opcional.
 */
export function useCriarArtigo() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (pedido: ProdutoParaCriar) =>
      apiRequest(CAMINHO_PRODUTOS, produtoSchema, {
        method: "POST",
        body: produtoParaCriarSchema.parse(pedido),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.resource(tenant, RECURSO_PRODUTOS),
      });
    },
  });
}

/**
 * Embalagens de um produto específico.
 */
export function useEmbalagens(produto: string): UseQueryResult<Paginated<Embalagem>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_EMBALAGENS, { produto }),
    queryFn: ({ signal }) =>
      apiRequest(`${CAMINHO_PRODUTOS}/${produto}/packagings`, paginated(embalagemSchema), {
        signal,
      }),
    enabled: !!produto,
  });
}

/**
 * Criar uma embalagem para um produto.
 */
export function useCriarEmbalagem() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: ({ produto, ...embalagem }: EmbalagemParaCriar & { produto: string }) =>
      apiRequest(`${CAMINHO_PRODUTOS}/${produto}/packagings`, embalagemSchema, {
        method: "POST",
        body: embalagemParaCriarSchema.parse(embalagem),
      }),
    onSuccess: async (_dados, variaveis) => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.list(tenant, RECURSO_EMBALAGENS, { produto: variaveis.produto }),
      });
    },
  });
}

/**
 * Lista de fornecedores com paginação e busca.
 */
export function useFornecedores(q = ""): UseQueryResult<Paginated<Fornecedor>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_FORNECEDORES, { q }),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_FORNECEDORES, paginated(fornecedorSchema), {
        query: { q },
        signal,
      }),
  });
}

/**
 * Criar um novo fornecedor.
 */
export function useCriarFornecedor() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (pedido: FornecedorParaCriar) =>
      apiRequest(CAMINHO_FORNECEDORES, fornecedorSchema, {
        method: "POST",
        body: fornecedorParaCriarSchema.parse(pedido),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.resource(tenant, RECURSO_FORNECEDORES),
      });
    },
  });
}

/**
 * Lista de localizações com paginação.
 */
export function useLocalizacoes(): UseQueryResult<Paginated<Localizacao>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_LOCALIZACOES, {}),
    queryFn: ({ signal }) =>
      apiRequest(CAMINHO_LOCALIZACOES, paginated(localizacaoSchema), { signal }),
  });
}

/**
 * Criar uma nova localização.
 */
export function useCriarLocalizacao() {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (pedido: LocalizacaoParaCriar) =>
      apiRequest(CAMINHO_LOCALIZACOES, localizacaoSchema, {
        method: "POST",
        body: localizacaoParaCriarSchema.parse(pedido),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.resource(tenant, RECURSO_LOCALIZACOES),
      });
    },
  });
}
