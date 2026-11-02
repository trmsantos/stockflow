import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, CircleAlert, Lock } from "lucide-react";

import { EstadoVazio } from "@/components/estado-vazio";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { mensagemDeErro } from "@/lib/api/errors";

import { useCriarReceita, usePodeEscreverFicha } from "../api";
import { FormularioDeReceita, type FichaGravavel } from "../components/formulario-de-receita";
import {
  CODIGO_RECEITA_JA_EXISTE,
  codigoDaRecusa,
  erroDaFornada,
  erroDasLinhas,
  erroDoRendimento,
  fichaDoConflito,
} from "../recusas-de-receita";
import { textos } from "../textos";

/**
 * Escrever a primeira versão de uma ficha técnica.
 *
 * ## Criar é outra página, editar é um `?editar=1`
 *
 * Aqui ainda não há documento nenhum: não há cabeçalho para mostrar, não há
 * custo para calcular — ele é derivado do stock **na leitura** (ADR 0035,
 * decisão 2) — e o acabado ainda se escolhe, que num `PATCH` nem sequer é
 * aceite, porque é a identidade da ficha.
 *
 * ## O 409 não é um erro: é um atalho
 *
 * `Recipe.product` é `OneToOneField`, logo a segunda ficha do mesmo artigo é um
 * `IntegrityError` e não um `exists()` em Python — duas pessoas a gravar no
 * mesmo instante veem ambas zero fichas. O servidor devolve o **`id` da que
 * existe**, e a reacção certa é levar lá quem tentou em vez de lhe dizer "erro"
 * (precedente: o 409 da contagem já aberta, ADR 0030, decisão 2).
 *
 * ## Sem update optimista, e a razão é o que o servidor devolve
 *
 * A regra da casa é "optimista só em acções reversíveis", e esta é reversível —
 * uma ficha corrige-se, ao contrário de um movimento do ledger. O que o impede é
 * outra coisa: **o que volta não é o que foi enviado.** A fornada volta
 * convertida para a unidade base, as quantidades voltam nas duas formas, e os
 * cinco euros e as três palavras do `cost_status` são calculados a partir do
 * stock de hoje. Uma ficha optimista teria de os inventar — isto é, inventar
 * precisamente o número que o ecrã existe para mostrar.
 */
export function EcraDeNovaReceita() {
  const navegar = useNavigate({ from: "/receitas/nova" });
  const podeEscrever = usePodeEscreverFicha();
  const criar = useCriarReceita();

  const conflito =
    codigoDaRecusa(criar.error) === CODIGO_RECEITA_JA_EXISTE
      ? fichaDoConflito(criar.error)
      : null;

  return (
    <section className="flex w-full flex-col gap-ritmo py-3">
      <div className="px-celula-x">
        <Button asChild variant="ghost" className="-ml-3">
          <Link to="/receitas" search={true}>
            <ArrowLeft aria-hidden="true" />
            {textos.accoes.voltar}
          </Link>
        </Button>
      </div>

      <h1 className="px-celula-x text-2xl font-semibold text-balance">
        {textos.formulario.tituloNova}
      </h1>

      {/* Escrever a ficha é de `owner|manager` (ADR 0035, decisão 5). Esconder o
          botão que leva aqui é apresentação; a rota **existe** para todos porque
          um deep link tem de funcionar, e quem recusa é o servidor com 403. O
          que este ramo evita é um formulário que só falha depois de preenchido.
          Não é autorização: é não prometer o que o servidor desmente. */}
      {podeEscrever ? (
        <>
          {conflito === null ? null : (
            <div className="px-celula-x">
              <Alert className="border-warning-border bg-warning-surface">
                <CircleAlert aria-hidden="true" className="text-warning" />
                <AlertTitle>{textos.formulario.jaExisteTitulo}</AlertTitle>
                <AlertDescription className="flex flex-col items-start gap-2">
                  <span>{textos.formulario.jaExisteCorpo}</span>
                  <Button asChild variant="outline">
                    <Link
                      to="/receitas/$receita"
                      params={{ receita: conflito }}
                      search={() => ({})}
                    >
                      {textos.accoes.verFichaExistente}
                    </Link>
                  </Button>
                </AlertDescription>
              </Alert>
            </div>
          )}

          {/* As outras recusas: o ciclo de receitas, a unidade que o artigo não
              aceita, a quantidade a zero, o ingrediente repetido. A frase é a do
              servidor e o campo é o que ele nomeou — nada aqui a reescreve. */}
          {criar.isError && conflito === null ? (
            <div className="px-celula-x">
              <Alert className="border-danger-border bg-danger-surface">
                <CircleAlert aria-hidden="true" className="text-danger" />
                <AlertTitle>{textos.formulario.erroAoGravar}</AlertTitle>
                <AlertDescription>
                  {erroDasLinhas(criar.error) ??
                    erroDaFornada(criar.error) ??
                    erroDoRendimento(criar.error) ??
                    mensagemDeErro(criar.error)}
                </AlertDescription>
              </Alert>
            </div>
          ) : null}

          <FormularioDeReceita
            pendente={criar.isPending}
            aoGravar={(valores: FichaGravavel) => {
              criar.mutate(
                {
                  product: valores.product,
                  batch_size: valores.batch_size,
                  batch_unit: valores.batch_unit,
                  yield_factor: valores.yield_factor,
                  lines: [...valores.lines],
                },
                {
                  onSuccess: (ficha) => {
                    // `replace`: o passo seguinte do botão de voltar é a lista,
                    // e não um formulário vazio sobre uma ficha que já existe.
                    void navegar({
                      to: "/receitas/$receita",
                      params: { receita: ficha.id },
                      search: () => ({}),
                      replace: true,
                    });
                  },
                },
              );
            }}
            aoCancelar={() => {
              void navegar({ to: "/receitas", search: true });
            }}
          />
        </>
      ) : (
        <EstadoVazio
          icone={Lock}
          titulo={textos.formulario.semPermissaoTitulo}
          descricao={textos.formulario.semPermissaoCorpo}
        >
          <Button asChild variant="outline">
            <Link to="/receitas" search={() => ({})}>
              {textos.accoes.voltar}
            </Link>
          </Button>
        </EstadoVazio>
      )}
    </section>
  );
}
