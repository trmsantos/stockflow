import type { ServerResponse } from "node:http";
import type { Connect, Plugin } from "vite";
import type { z } from "zod";

import { ROTAS_DE_ALERTAS } from "./alertas.ts";
import { ROTAS_DE_CONTAGEM } from "./contagem.ts";
import { ROTAS_DE_RECECOES } from "./rececoes.ts";
import { ROTAS_DE_STOCK } from "./stock.ts";

/**
 * dados-falsos-stockflow — o backend de fixtures do servidor de desenvolvimento.
 *
 * Isto **não** é um módulo da app (ADR 0008, decisão 3): é um plugin do Vite com
 * `apply: "serve"` que responde aos caminhos `/api/v1/…` que o Django ainda não
 * tem e faz `next()` em tudo o resto, caindo no proxy para o backend. A
 * consequência é que o `api.ts` de cada feature se escreve na forma final no
 * primeiro dia — mesmo `fetch`, mesmo cookie, mesmo `X-Tenant-ID`, mesmo
 * envelope de paginação, mesmo Zod, mesmos `retry` e `staleTime`. Não existe
 * `if (fake)` em sítio nenhum e não existe hook para ligar depois: já está
 * ligado.
 *
 * O `apply: "serve"` é do Vite e não nosso: o plugin não participa em
 * `vite build`, e porque nada em `src/` importa `fixtures/` os dados falsos não
 * estão no grafo de módulos da app. Não há artefacto de produção que os
 * contenha — não porque alguém se lembre de os apagar, mas porque nunca entram.
 * O preço, dito com clareza: **não existe build do shell com dados falsos**.
 * Mostra-se ao dono com `pnpm dev --host` num telemóvel na mesma rede.
 *
 * O middleware é instalado na forma **pré** do `configureServer` (corpo do
 * hook, sem devolver uma função), logo corre antes do proxy interno do Vite.
 * Isso foi medido com `curl` e não deduzido — ver o relatório da sessão.
 */

/** Só este prefixo é nosso. Tudo o que não casa segue para o Django. */
const PREFIXO = "/api/v1/";

/**
 * O atraso existe porque os estados loading/empty/error do DESIGN.md §3 são
 * metade do que se vai mostrar na sessão 0: sem latência nenhuma, o skeleton
 * nunca aparece em dev e ninguém o vê antes do dono o ver.
 */
const ATRASO_DEFAULT_MS = 250;

/**
 * O estabelecimento falso. O `X-Tenant-ID` do cliente nunca escolhe âmbito —
 * só pode ser recusado (ADR 0007) —, e é esse 409 que este servidor sabe dar,
 * para o caminho de erro do `http.ts` existir em dev e não só em teoria.
 */
const TENANT_FALSO = "a000a000-0000-4000-8000-000000000001";

const METODOS_QUE_ESCREVEM = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export interface Contexto {
  /** O caminho pedido, sem query string. */
  readonly caminho: string;
  readonly parametros: URLSearchParams;
  /**
   * Os segmentos nomeados do caminho (`:contagem` em
   * `/stock/counts/:contagem/lines`). Vazio nas rotas sem parâmetros.
   */
  readonly variaveis: ReadonlyMap<string, string>;
  /** O corpo JSON do pedido, já parseado. `null` nos GET. */
  readonly corpo: unknown;
}

export interface Resposta {
  readonly estado: number;
  readonly corpo: unknown;
  /**
   * O schema que valida este corpo **à saída**, no servidor de dev, e que é o
   * mesmo que o cliente usa à chegada. Um fixture que não poderia sair do
   * endpoint real falha aqui, alto, em vez de passar por bom. As respostas de
   * erro não têm schema: a sua forma é do `errors.ts`, não do domínio.
   */
  readonly schema?: z.ZodType;
}

export function resposta(estado: number, corpo: unknown, schema?: z.ZodType): Resposta {
  // `exactOptionalPropertyTypes`: a propriedade ou existe com schema, ou não
  // existe. `schema: undefined` não é a mesma coisa.
  return schema === undefined ? { estado, corpo } : { estado, corpo, schema };
}

export interface Rota {
  readonly metodo: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /**
   * Caminho com o prefixo `/api/v1`. Um segmento que comece por `:` é um
   * parâmetro e chega ao `ctx.variaveis` — existe para os caminhos se
   * escreverem na forma que o DRF lhes vai dar
   * (`/stock/counts/<uuid>/lines`), e não numa forma de conveniência do
   * servidor de fixtures que depois obrigasse a reescrever o `api.ts`.
   */
  readonly caminho: string;
  /** Sobrepõe o atraso default deste caminho. */
  readonly atrasoMs?: number;
  readonly responder: (ctx: Contexto) => Resposta;
  /** A variante vazia, para "o que aparece quando não há nada?". */
  readonly vazio?: (ctx: Contexto) => Resposta;
}

export interface OpcoesDeFixtures {
  /** Atraso default, em ms. */
  readonly atrasoMs?: number;
  /** Caminhos que respondem a variante vazia (`results: []`). */
  readonly vazios?: readonly string[];
  /** Caminhos que respondem 500. */
  readonly erros?: readonly string[];
}

/**
 * As rotas servidas. Uma linha por recurso, e a remoção é por recurso: no dia
 * em que o endpoint real existir, apaga-se o ficheiro e esta linha.
 */
const ROTAS: readonly Rota[] = [
  ...ROTAS_DE_STOCK,
  ...ROTAS_DE_CONTAGEM,
  ...ROTAS_DE_ALERTAS,
  ...ROTAS_DE_RECECOES,
];

function esperar(ms: number): Promise<void> {
  return new Promise((resolver) => {
    setTimeout(resolver, ms);
  });
}

interface Correspondencia {
  readonly rota: Rota;
  readonly variaveis: Map<string, string>;
}

function casarCaminho(rota: Rota, caminho: string): Map<string, string> | null {
  const padrao = rota.caminho.split("/");
  const pedido = caminho.split("/");
  if (padrao.length !== pedido.length) return null;

  const variaveis = new Map<string, string>();
  for (const [indice, segmento] of padrao.entries()) {
    const valor = pedido.at(indice) ?? "";
    if (segmento.startsWith(":")) {
      if (valor === "") return null;
      variaveis.set(segmento.slice(1), decodeURIComponent(valor));
      continue;
    }
    if (segmento !== valor) return null;
  }
  return variaveis;
}

/**
 * A rota que responde a este pedido. Os caminhos **literais** são tentados
 * primeiro: sem isso, uma rota futura `/stock/counts/open` ficaria à mercê da
 * ordem de declaração contra `/stock/counts/:contagem`, e a ambiguidade só
 * apareceria no dia em que alguém reordenasse a lista.
 */
function casar(metodo: string, caminho: string): Correspondencia | null {
  const candidatas = ROTAS.filter((rota) => rota.metodo === metodo);
  const literais = candidatas.filter((rota) => !rota.caminho.includes("/:"));
  for (const rota of [...literais, ...candidatas.filter((rota) => rota.caminho.includes("/:"))]) {
    const variaveis = casarCaminho(rota, caminho);
    if (variaveis !== null) return { rota, variaveis };
  }
  return null;
}

/** Um header pode vir repetido; o que interessa é o primeiro. */
function primeiro(valor: string | string[] | undefined): string | null {
  if (typeof valor === "string") return valor;
  if (Array.isArray(valor)) return valor[0] ?? null;
  return null;
}

function lerCorpo(req: Connect.IncomingMessage): Promise<unknown> {
  return new Promise((resolver, rejeitar) => {
    const pedacos: Buffer[] = [];
    req.on("data", (pedaco: Buffer) => {
      pedacos.push(pedaco);
    });
    req.on("error", rejeitar);
    req.on("end", () => {
      const texto = Buffer.concat(pedacos).toString("utf8");
      if (texto.trim() === "") {
        resolver(null);
        return;
      }
      try {
        resolver(JSON.parse(texto) as unknown);
      } catch (erro) {
        rejeitar(erro instanceof Error ? erro : new Error("JSON inválido."));
      }
    });
  });
}

function enviar(res: ServerResponse, estado: number, corpo: unknown): void {
  res.statusCode = estado;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  // Respostas de API não se cacheiam; e sem isto um GET repetido em dev podia
  // nem chegar ao middleware.
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(corpo));
}

/**
 * O cookie de CSRF que o Django daria. Sem ele o `http.ts` recusa-se — e bem —
 * a enviar qualquer mutação, e o fluxo "Deitei fora" nunca sairia do browser em
 * dev. O valor é fixo e é público: não é uma credencial, é o par do header.
 */
function garantirCookieDeCsrf(req: Connect.IncomingMessage, res: ServerResponse): void {
  const cookies = req.headers.cookie ?? "";
  if (cookies.includes("csrftoken=")) return;
  res.setHeader(
    "Set-Cookie",
    "csrftoken=fixtures-dados-falsos-stockflow; Path=/; SameSite=Lax",
  );
}

function registar(metodo: string, caminho: string, estado: number, ms: number): void {
  console.log(`  [fixtures] ${metodo} ${caminho} → ${String(estado)} (${String(ms)} ms)`);
}

export function servidorDeFixtures(opcoes: OpcoesDeFixtures = {}): Plugin {
  const atrasoDefault = opcoes.atrasoMs ?? ATRASO_DEFAULT_MS;
  const vazios = new Set(opcoes.vazios ?? []);
  const erros = new Set(opcoes.erros ?? []);

  const middleware: Connect.NextHandleFunction = (req, res, next) => {
    const metodo = req.method ?? "GET";
    const url = new URL(req.url ?? "/", "http://fixtures.invalid");
    const caminho = url.pathname;

    // Tudo o que não é nosso segue para o proxy, e daí para o Django. É esta
    // linha que faz a remoção por recurso funcionar sem tocar em mais nada.
    if (!caminho.startsWith(PREFIXO)) {
      next();
      return;
    }

    const correspondencia = casar(metodo, caminho);
    if (!correspondencia) {
      next();
      return;
    }
    const { rota, variaveis } = correspondencia;

    garantirCookieDeCsrf(req, res);

    const inicio = Date.now();
    const atraso = rota.atrasoMs ?? atrasoDefault;

    const servir = async (): Promise<void> => {
      // O header nunca seleciona âmbito; só pode divergir do da sessão.
      const tenant = primeiro(req.headers["x-tenant-id"]);
      if (tenant !== null && tenant !== TENANT_FALSO) {
        await esperar(atraso);
        enviar(res, 409, {
          code: "tenant_divergente",
          detail: "O estabelecimento do pedido não é o da sessão. Recarregue a página.",
        });
        registar(metodo, caminho, 409, Date.now() - inicio);
        return;
      }

      if (METODOS_QUE_ESCREVEM.has(metodo) && primeiro(req.headers["x-csrftoken"]) === null) {
        await esperar(atraso);
        enviar(res, 403, {
          code: "csrf_ausente",
          detail: "Pedido sem token CSRF. Recarregue a página e tente outra vez.",
        });
        registar(metodo, caminho, 403, Date.now() - inicio);
        return;
      }

      let corpo: unknown = null;
      if (METODOS_QUE_ESCREVEM.has(metodo)) {
        try {
          corpo = await lerCorpo(req);
        } catch {
          enviar(res, 400, { code: "json_invalido", detail: "O corpo do pedido não é JSON." });
          registar(metodo, caminho, 400, Date.now() - inicio);
          return;
        }
      }

      /**
       * Os estados do DESIGN.md §3 pedem-se de duas formas, e nenhuma delas é
       * um `if` dentro da app: por caminho, ao arrancar o `pnpm dev`
       * (`FIXTURES_ERRO=/api/v1/stock/levels pnpm dev`), ou por pedido, com
       * `?_fixture=erro`. O segundo existe para sondar com `curl` sem
       * reiniciar; nada em `src/` o envia, e no dia em que o Django servir o
       * caminho o parâmetro deixa de ter quem o leia.
       */
      // Casa pelo caminho pedido **e** pelo padrão da rota: com um `:contagem`
      // no meio, o caminho pedido traz um uuid que ninguém ia escrever à mão
      // numa variável de ambiente.
      const pedido = url.searchParams.get("_fixture");
      const comErro = pedido === "erro" || erros.has(caminho) || erros.has(rota.caminho);
      const comVazio = pedido === "vazio" || vazios.has(caminho) || vazios.has(rota.caminho);

      await esperar(atraso);

      if (comErro) {
        enviar(res, 500, {
          code: "erro_simulado",
          detail: "Não foi possível obter os dados. Tente outra vez.",
        });
        registar(metodo, caminho, 500, Date.now() - inicio);
        return;
      }

      const ctx: Contexto = { caminho, parametros: url.searchParams, variaveis, corpo };
      const resultado = comVazio && rota.vazio ? rota.vazio(ctx) : rota.responder(ctx);

      if (resultado.schema) {
        const validado = resultado.schema.safeParse(resultado.corpo);
        if (!validado.success) {
          // Falha alto: um fixture que não passa o schema do cliente não
          // poderia sair do endpoint real, e um ecrã construído sobre ele
          // estaria a ser construído sobre um contrato que não existe.
          console.error(`  [fixtures] ${metodo} ${caminho} não passa o próprio schema Zod:`);
          for (const problema of validado.error.issues) {
            console.error(`    ${problema.path.join(".")}: ${problema.message}`);
          }
          enviar(res, 500, {
            code: "fixture_invalido",
            detail: `O fixture de ${caminho} não passa o schema Zod do cliente. Ver a consola do Vite.`,
          });
          registar(metodo, caminho, 500, Date.now() - inicio);
          return;
        }
      }

      enviar(res, resultado.estado, resultado.corpo);
      registar(metodo, caminho, resultado.estado, Date.now() - inicio);
    };

    void servir().catch((erro: unknown) => {
      console.error("  [fixtures] erro no servidor de fixtures:", erro);
      if (!res.headersSent) {
        enviar(res, 500, { code: "erro_de_fixture", detail: "Erro no servidor de fixtures." });
      }
    });
  };

  return {
    name: "stockflow:fixtures",
    // Do Vite e não nosso: é isto que garante que nada disto participa em
    // `vite build`. Não tirar sem ler a decisão 3 do ADR 0008 — o
    // `scripts/check-fixtures.mjs` falha se desaparecer.
    apply: "serve",
    configureServer(server) {
      // Forma **pré**: o middleware entra no corpo do hook, e não dentro de uma
      // função devolvida (que seria a forma pós, depois do proxy interno). A
      // ordem foi medida com `curl`: um GET a um caminho servido aqui responde
      // 200 com o Django em baixo, e um caminho desconhecido dá o erro do proxy.
      server.middlewares.use(middleware);

      const caminhos = [...new Set(ROTAS.map((rota) => `${rota.metodo} ${rota.caminho}`))];
      server.config.logger.info(
        `  dados falsos  ${String(caminhos.length)} rota(s) de fixtures, ${String(atrasoDefault)} ms de atraso`,
      );
      for (const caminho of caminhos) {
        server.config.logger.info(`                ${caminho}`);
      }
    },
  };
}
