import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { ArrowLeft, FilePlus2, QrCode, Truck } from "lucide-react";
import { useState } from "react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { EstadoVazio } from "@/components/estado-vazio";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAbrirDocumentoComFicheiro,
  useAbrirSlotDeCaptura,
  useAnexarFicheiro,
  useDescartarDocumento,
  useDocumento,
  useDocumentos,
  useFecharDocumento,
} from "../api-de-documentos";
import { PainelDeLeitura } from "../components/painel-de-leitura";
import { PainelDoDocumento } from "../components/painel-do-documento";
import {
  EsqueletoDaTabelaDeDocumentos,
  TabelaDeDocumentos,
} from "../components/tabela-de-documentos";
import { ZonaDeFicheiro } from "../components/zona-de-ficheiro";
// `fraseDaRecusa` e não o `mensagemDeErro` do `lib/api/errors` em **nenhum** dos
// quatro sítios, e foi medido: com o `mensagemDeErro`, um 500 sem corpo JSON
// punha "500 em /documents" dentro do banner de erro deste ecrã. O leitor desta
// feature é o que sabe que uma recusa sem `detail` tem de virar uma frase de
// produto.
import { desenhoDaRecusa, fraseDaRecusa, statusDaRecusaDeDocumento } from "../recusas-de-documento";
import { textos } from "../textos";

/**
 * `/receber/fotografar` — a entrada do documento de fornecedor.
 *
 * ## O que este ecrã era, e porque deixou de o ser
 *
 * Era um placeholder de 117 linhas a dizer que não havia câmara nem envio de
 * ficheiro, e a razão escrita nele era boa: *"tirar a fotografia e não acontecer
 * nada é a única coisa pior do que não ter o botão"*. A fatia 1 da ADR 0021
 * removeu essa razão — os endpoints existem, o documento entra, é guardado e é
 * lido — e um ecrã que continuasse a dizer que não há caminho passava a ser ele
 * a mentir.
 *
 * ## A zona de ficheiro resolve as duas pontas, e é por isso que é uma só
 *
 * Um `<input type="file" capture="environment">`: no computador abre o
 * explorador e aceita o PDF que o fornecedor mandou por email; num telemóvel
 * abre a câmara de trás. Uma rota, não duas (ADR 0020, decisão 7), e o que varia
 * com a largura é ordem e ênfase — layout, nunca routing (ADR 0008, decisão 1).
 *
 * ## Dois caminhos de entrada, e o segundo existe por uma razão do backend
 *
 * Um ficheiro **fecha-se a si mesmo**: um PDF de dez páginas é um documento
 * completo e o número de páginas sabe-se do ficheiro (ADR 0021, decisão 9), logo
 * `POST /documents` com ficheiro nasce fechado e não aceita um segundo. Isso
 * resolve o computador num gesto e **não** resolve uma fatura de duas folhas
 * fotografada folha a folha — que é precisamente o caso de campo deste ecrã.
 * Para esse existe o slot: `POST /documents` vazio nasce aberto, cada fotografia
 * é um `POST .../files`, e uma pessoa diz quando acabou.
 *
 * É também o que torna os oito estados **alcançáveis**: sem abrir um slot não há
 * `aguarda_captura`, não há `expirado`, e as recusas `documento_sem_paginas` e
 * `paginas_excedidas` não têm como acontecer. Um ramo que nada exercita é um ramo
 * que ninguém sabe se funciona.
 *
 * ## O que **não** está aqui, e a ausência é dita no ecrã
 *
 * O bloco do QR — a ponte computador→telemóvel da ADR 0020 — não é desta fatia:
 * precisa de uma biblioteca que desenhe o código e essa escolha está com o dono.
 * O ecrã não finge que ela existe e também não a esconde: fica **uma linha no
 * sítio onde ela vai ficar**, a dizer o que falta e sem prometer data. A
 * alternativa — não dizer nada — faria o próximo leitor procurar o bloco no
 * código e concluir que se esqueceram dele.
 *
 * ## E a terceira via continua escrita
 *
 * Os três caminhos por onde a mercadoria entra numa cozinha portuguesa ficam no
 * fundo, onde não pagam pixéis acima da dobra: *"um escritório sem ficheiro
 * nenhum usa a terceira via que o ecrã já descreve hoje: a receção à mão"* (ADR
 * 0020, decisão 7). É conteúdo de sessão 0 e é a lista que se quer que o dono
 * corrija.
 *
 * ## Dois erros em dois sítios, e porque não um só
 *
 * As escritas deste ecrã são cinco e dividem-se em duas famílias: as que levam
 * **um ficheiro** (abrir com ficheiro, anexar) e as que agem **sobre o
 * documento** (abrir slot, fechar, descartar). Uma recusa da primeira família
 * pertence ao campo; uma da segunda pertence ao painel. Um `erro` só no topo
 * mandava alguém procurar o problema do ficheiro no sítio errado — e é
 * exactamente a distinção que os quatro códigos do servidor pedem.
 */
export function EcraDeFotografar() {
  const busca = useSearch({ from: "/app/receber/fotografar" });
  // `from` é o **caminho** da rota e não o id dela: o `useSearch` acima lê por
  // id (`/app/...`) e o `useNavigate` tipa-se pelo caminho. Dois nomes para a
  // mesma rota, e o compilador diz qual é qual.
  const navegar = useNavigate({ from: "/receber/fotografar" });
  const escolhido = busca.documento ?? null;

  /**
   * O que repõe o `<input type="file">`.
   *
   * Um input de ficheiro guarda o que foi escolhido, e sem o remontar escolher
   * **o mesmo** ficheiro outra vez não dispara `change` — que é exactamente o
   * que alguém faz depois de uma falha de rede. Conta-se aqui, e não dentro da
   * zona, porque é o ecrã que sabe quando uma escrita acabou.
   */
  const [envios, setEnvios] = useState(0);

  const documentos = useDocumentos();
  const { consulta: consultaDoDocumento, desistiu } = useDocumento(escolhido);
  const documento = consultaDoDocumento.data;

  const abrirComFicheiro = useAbrirDocumentoComFicheiro();
  const abrirSlot = useAbrirSlotDeCaptura();
  const anexar = useAnexarFicheiro();
  const fechar = useFecharDocumento();
  const descartar = useDescartarDocumento();

  const aberto = documento?.state === "aguarda_captura";
  const noTeto = documento !== undefined && documento.page_count >= documento.page_limit;

  // A recusa de uma escrita **com ficheiro**: ou se está a abrir um documento, ou
  // se está a anexar a um que já está aberto, nunca as duas.
  const erroDoFicheiro: unknown = aberto ? anexar.error : abrirComFicheiro.error;
  const desenhoDoFicheiro = desenhoDaRecusa(erroDoFicheiro);

  // A recusa de uma escrita **sobre o documento**. O `reset` cruzado em cada
  // acção é o que garante que há no máximo uma a falar: sem ele, um erro de
  // ficheiro de há dois minutos continuava no ecrã debaixo de um fecho que
  // correu bem.
  const erroDoDocumento: unknown = fechar.error ?? descartar.error;
  const desenhoDoDocumento = desenhoDaRecusa(erroDoDocumento);

  const documentoPerdido =
    desenhoDoFicheiro === "documento_perdido" || desenhoDoDocumento === "documento_perdido";

  function escolher(id: string) {
    void navegar({ search: (anterior) => ({ ...anterior, documento: id }) });
  }

  /**
   * Limpa a escolha **omitindo** a chave em vez de a pôr a `undefined`: com
   * `exactOptionalPropertyTypes` as duas coisas não são a mesma, e o filtro do
   * `/receber` tem de sobreviver — é ele que o link de voltar leva.
   */
  function limparEscolha() {
    void navegar({
      search: (anterior) => (anterior.estado === undefined ? {} : { estado: anterior.estado }),
    });
  }

  function aoEscolherFicheiro(ficheiro: File) {
    fechar.reset();
    descartar.reset();
    const terminar = () => {
      setEnvios((anteriores) => anteriores + 1);
    };

    if (aberto && escolhido !== null) {
      anexar.mutate({ documento: escolhido, ficheiro }, { onSettled: terminar });
      return;
    }
    abrirComFicheiro.mutate(ficheiro, {
      onSuccess: (criado) => {
        escolher(criado.id);
      },
      onSettled: terminar,
    });
  }

  const linhas = documentos.data?.results;
  const total = documentos.data?.count ?? 0;
  const truncada = documentos.data !== undefined && total > documentos.data.results.length;

  return (
    // Sem `max-w`: as duas tabelas deste ecrã usam a largura toda da área de
    // conteúdo (DESIGN.md §4), e as regiões encostam às arestas e separam-se por
    // réguas de 1px. A prosa que existe leva `max-w-prose` por dentro.
    <section className="flex w-full min-w-0 flex-1 flex-col">
      <div className="flex flex-col gap-1 px-celula-x py-3">
        <Button asChild variant="ghost" className="-ml-2 self-start">
          <Link to="/receber" search={{ estado: busca.estado }}>
            <ArrowLeft aria-hidden="true" />
            {textos.comuns.receber}
          </Link>
        </Button>
        <h1 className="text-2xl font-semibold text-balance">{textos.comuns.novoDocumento}</h1>
        <p className="max-w-prose text-pretty text-sm text-muted-foreground">
          {textos.fotografar.pergunta}
        </p>
      </div>

      {/* A zona de ficheiro, a um ecrã de distância de nada: é a primeira coisa
          depois do nome, nas duas larguras.
          **Duas colunas a partir de `md`, e uma só a 360** — o que varia com a
          largura é ordem e ênfase, que é layout e nunca routing (ADR 0020,
          adenda 2, a corrigir o `hidden md:block` da decisão 7: um tablet de
          balcão em retrato é mais estreito que `md` e é precisamente onde mais se
          quer a ponte). A coluna da direita é o sítio do bloco do QR; medido a
          1280, com uma coluna só o conteúdo deste ecrã ocupava 510px de 1024 e o
          resto era preto. */}
      <div className="grid border-y border-border bg-surface md:grid-cols-[minmax(0,1fr)_19rem]">
        <div className="flex flex-col gap-3 px-celula-x py-4">
          <ZonaDeFicheiro
            paraDocumentoAberto={aberto}
            aEnviar={abrirComFicheiro.isPending || anexar.isPending}
            desativado={desenhoDoFicheiro === "limite" || (aberto && noTeto)}
            limiteAtingido={
              (desenhoDoFicheiro === "limite" || (aberto && noTeto)) && documento !== undefined
                ? documento.page_limit
                : null
            }
            erro={
              desenhoDoFicheiro === "campo" || desenhoDoFicheiro === "limite"
                ? fraseDaRecusa(erroDoFicheiro)
                : null
            }
            chave={envios}
            aoEscolher={aoEscolherFicheiro}
          />

          {/* `documento_fechado` e `documento_descartado`: o documento aberto
            deixou de aceitar escrita, logo o erro não é do campo e a única saída
            é abrir outro. */}
          {documentoPerdido ? (
            <Alert className="border-danger-border bg-danger-surface">
              <AlertTitle>{textos.documento.painel.abrirOutro}</AlertTitle>
              <AlertDescription className="flex flex-col items-start gap-2">
                <span className="text-pretty">
                  {fraseDaRecusa(
                    desenhoDoFicheiro === "documento_perdido" ? erroDoFicheiro : erroDoDocumento,
                  )}
                </span>
                <Button variant="outline" onClick={limparEscolha}>
                  {textos.documento.painel.abrirOutro}
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}

          {desenhoDoFicheiro === "generico" && erroDoFicheiro !== null ? (
            <Alert className="border-danger-border bg-danger-surface">
              <AlertTitle>{textos.documento.zona.erroTitulo}</AlertTitle>
              <AlertDescription className="text-pretty">
                {fraseDaRecusa(erroDoFicheiro)}
              </AlertDescription>
            </Alert>
          ) : null}

          {/* O segundo caminho de entrada. Só aparece quando não há documento
            aberto: com um aberto, o botão abriria um segundo e deixava o
            primeiro a expirar sozinho. */}
          {aberto ? null : (
            <div className="flex flex-col gap-1.5 border-t border-border pt-3">
              <Button
                variant="outline"
                className="self-start"
                disabled={abrirSlot.isPending}
                onClick={() => {
                  abrirSlot.mutate(undefined, {
                    onSuccess: (criado) => {
                      escolher(criado.id);
                    },
                  });
                }}
              >
                <FilePlus2 aria-hidden="true" />
                {abrirSlot.isPending ? textos.documento.slot.aAbrir : textos.documento.slot.abrir}
              </Button>
              <p className="max-w-prose text-pretty text-xs text-muted-foreground">
                {textos.documento.slot.explicacao}
              </p>
              {abrirSlot.isError ? (
                <p role="alert" className="text-sm text-danger">
                  {fraseDaRecusa(abrirSlot.error)}
                </p>
              ) : null}
            </div>
          )}
        </div>

        {/* O sítio do bloco do QR, sem o bloco. Diz o que falta e não promete
            data — e fica onde ele vai ficar, para a ausência ser visível em vez
            de ser uma omissão. A régua de 1px é horizontal a 360 e vertical a
            partir de `md`: é a mesma régua das colunas da tabela. */}
        <div className="flex flex-col gap-1.5 border-t border-border px-celula-x py-4 md:border-t-0 md:border-l">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <QrCode aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
            {textos.documento.ponte.titulo}
          </h2>
          <p className="text-pretty text-xs text-muted-foreground">
            {textos.documento.ponte.corpo}
          </p>
        </div>
      </div>

      {/* O documento escolhido: o estado, as páginas, os ficheiros, e o que o
          modelo leu. Só existe quando há um no URL. */}
      {escolhido === null ? null : (
        <div className="flex flex-col gap-ritmo px-celula-x py-4">
          {consultaDoDocumento.isPending ? (
            <div aria-busy="true" className="flex flex-col gap-2">
              <span className="sr-only">{textos.documento.painel.aCarregar}</span>
              {/* A forma do que vem: o cabeçalho do painel e a régua de campos. */}
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : null}

          {/* 404 tem uma saída própria — o endereço aponta para um documento que
              não existe neste estabelecimento — e tudo o resto é uma falha a
              tentar outra vez. Confundidos, davam um botão de retry sobre um
              documento que nunca vai responder. */}
          {consultaDoDocumento.isError ? (
            statusDaRecusaDeDocumento(consultaDoDocumento.error) === 404 ? (
              <EstadoVazio
                icone={FilePlus2}
                titulo={textos.documento.painel.naoExisteTitulo}
                descricao={textos.documento.painel.naoExisteCorpo}
              >
                <Button variant="outline" onClick={limparEscolha}>
                  {textos.documento.painel.abrirOutro}
                </Button>
              </EstadoVazio>
            ) : (
              <ErroAoCarregar
                titulo={textos.documento.painel.erroAoCarregar}
                mensagem={fraseDaRecusa(consultaDoDocumento.error)}
                aoTentarOutraVez={() => {
                  void consultaDoDocumento.refetch();
                }}
              />
            )
          ) : null}

          {documento === undefined ? null : (
            <>
              <PainelDoDocumento
                documento={documento}
                desistiu={desistiu}
                aFechar={fechar.isPending}
                aDescartar={descartar.isPending}
                recusaDoFecho={
                  erroDoDocumento === null || desenhoDoDocumento === "documento_perdido"
                    ? null
                    : fraseDaRecusa(erroDoDocumento)
                }
                aoFechar={() => {
                  abrirComFicheiro.reset();
                  anexar.reset();
                  fechar.mutate(documento.id);
                }}
                aoDescartar={() => {
                  abrirComFicheiro.reset();
                  anexar.reset();
                  descartar.mutate(documento.id, { onSuccess: limparEscolha });
                }}
              />

              {/* O painel existe sempre, com extração ou sem ela: é ele que
                  responde a "o que o modelo leu", incluindo quando a resposta é
                  "ainda nada". */}
              <PainelDeLeitura extracao={documento.extraction} />
            </>
          )}
        </div>
      )}

      {/* A lista do que entrou. Fica abaixo do painel porque a pergunta dela é a
          segunda: primeiro "o que é que acabei de enviar?", depois "o que é que
          já entrou?". */}
      <div className="flex min-w-0 flex-col border-t border-border">
        <h2 className="px-celula-x py-3 text-sm font-semibold">{textos.documento.lista.titulo}</h2>

        {documentos.isPending ? <EsqueletoDaTabelaDeDocumentos /> : null}

        {documentos.isError ? (
          <ErroAoCarregar
            titulo={textos.documento.lista.erroAoCarregar}
            mensagem={fraseDaRecusa(documentos.error)}
            aoTentarOutraVez={() => {
              void documentos.refetch();
            }}
          />
        ) : null}

        {linhas === undefined ? null : linhas.length === 0 ? (
          <EstadoVazio
            icone={Truck}
            titulo={textos.documento.lista.vazioTitulo}
            descricao={textos.documento.lista.vazioCorpo}
          >
            <Button asChild variant="outline">
              <Link to="/receber" search={() => ({})}>
                {textos.comuns.verAsRececoes}
              </Link>
            </Button>
          </EstadoVazio>
        ) : (
          <>
            <TabelaDeDocumentos documentos={linhas} escolhido={escolhido} aoEscolher={escolher} />
            <p className="px-celula-x py-3 text-xs text-muted-foreground">
              {textos.documento.lista.rodape(linhas.length, truncada ? total : null)}
            </p>
          </>
        )}
      </div>

      {/* Os três caminhos por onde a mercadoria entra. Fica no fim: é conteúdo de
          sessão 0 e não a acção do ecrã.
          Cada frase em duas partes nomeadas — o nome do documento vai no `<span>`
          com peso, e juntá-las numa string perdia essa ênfase. Pôr HTML numa
          string pedia um `dangerouslySetInnerHTML`, que o `eslint.config.js`
          proíbe. */}
      <div className="flex flex-col gap-2 border-t border-border px-celula-x py-4">
        <h2 className="text-sm font-semibold">{textos.fotografar.porOndeEntra}</h2>
        <ul className="flex max-w-prose flex-col gap-2 text-sm text-muted-foreground">
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
    </section>
  );
}
