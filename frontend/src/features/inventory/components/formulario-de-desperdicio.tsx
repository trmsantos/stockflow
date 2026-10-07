import { CircleAlert, CircleCheck } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { mensagemDeErro } from "@/lib/api/errors";

import { useRegistarDesperdicio } from "../api";
import { motivoQuebraSchema, type MotivoQuebra, type NivelDeStock } from "../schemas";
import { textos } from "../textos";
import { MOTIVOS_DE_DESPERDICIO, rotuloDeMotivo } from "../vocabulario";

/**
 * Registar desperdício — a única escrita deste ecrã, e a sonda da Q1.
 *
 * **Não bloqueia nada.** A nata está a 0 L e o formulário deixa registar 2 L: o
 * guião da sessão 0 é explícito em que o shell não responde por ele à pergunta
 * "bloquear ou avisar", porque um bloqueio aqui destrói a sonda — observa-se se
 * o dono passa ao lado ou se pára, e só depois se pergunta. O resultado aparece
 * como aviso **suave** no ecrã (`−2,0 L` a vermelho, "ficou negativo"), nunca
 * como modal de erro, e o botão nunca fica desativado por o stock ser
 * insuficiente. O que desativa o botão é o pedido estar a sair, e mais nada.
 *
 * Não há confirmação em modal, e é deliberado: o motivo é obrigatório, logo a
 * ação já tem dois passos — escrever a quantidade e escolher o porquê —, e um
 * terceiro diálogo seria a fricção que faz o dono parar por causa da UI e não
 * por causa do stock, que é precisamente o sinal que a Q1 quer medir.
 *
 * A quantidade escreve-se na **unidade base** do artigo. Converter unidades no
 * cliente é a fonte nº 1 de bugs de stock (`inventory-domain` §2) e o contrato
 * de escrita só aceita a unidade base; por isso o ecrã diz qual é, em vez de
 * fingir que aceita litros e multiplicar por mil às escondidas.
 */

/** A mesma forma que o `decimal` do `schemas.ts`, sem sinal: é um valor absoluto. */
const DECIMAL_POSITIVO = /^\d+$|^\d+\.\d+$/;

interface Erros {
  readonly quantidade?: string;
  readonly motivo?: string;
}

export function FormularioDeDesperdicio({ nivel }: { readonly nivel: NivelDeStock }) {
  const idQuantidade = useId();
  const idErroDeQuantidade = useId();
  const idMotivo = useId();
  const idErroDeMotivo = useId();
  const idUnidade = useId();
  const idLocalizacao = useId();

  const primeiraLocalizacao = nivel.by_location[0]?.location;
  const [localizacao, setLocalizacao] = useState(primeiraLocalizacao?.id ?? "");
  const [quantidade, setQuantidade] = useState("");
  const [motivo, setMotivo] = useState<MotivoQuebra | "">("");
  const [erros, setErros] = useState<Erros>({});

  const registar = useRegistarDesperdicio();

  const unidadeBase = nivel.quantity.base_unit;
  const unidadeMostrada = nivel.quantity.display_unit;

  if (primeiraLocalizacao === undefined) {
    return (
      <p className="px-4 text-sm text-muted-foreground">{textos.desperdicio.semLocalizacao}</p>
    );
  }

  function aoSubmeter(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();

    // A vírgula decimal é como se escreve em português; o contrato quer ponto.
    // É normalização de locale, não conversão de unidades.
    const valor = quantidade.trim().replace(",", ".");

    const problemas: Erros = {
      ...(DECIMAL_POSITIVO.test(valor) && Number(valor) > 0
        ? {}
        : { quantidade: textos.desperdicio.escrevaAQuantidade(unidadeBase) }),
      ...(motivo === "" ? { motivo: textos.desperdicio.escolhaOMotivo } : {}),
    };

    setErros(problemas);

    if (problemas.quantidade !== undefined) {
      // Foco no primeiro campo errado, por `id` e não por `ref`: os primitivos
      // do shadcn são funções que espalham props e nesta versão do React um
      // `ref` passado a uma função não chega ao DOM — ficaria um foco que
      // ninguém mede e que não acontece.
      const campo = document.getElementById(idQuantidade);
      if (campo instanceof HTMLInputElement) campo.focus();
      return;
    }
    if (problemas.motivo !== undefined || motivo === "") return;

    registar.mutate(
      { product: nivel.product, location: localizacao, quantity: valor, reason: motivo },
      {
        onSuccess: () => {
          setQuantidade("");
          setMotivo("");
        },
      },
    );
  }

  return (
    <section className="flex flex-col gap-3 px-4">
      <h2 className="text-sm font-semibold">{textos.desperdicio.registar}</h2>

      <form onSubmit={aoSubmeter} className="flex flex-col gap-3">
        {nivel.by_location.length === 1 ? (
          <p className="text-sm text-muted-foreground">
            {textos.desperdicio.localizacaoPrefixo}{" "}
            <span className="text-foreground">{primeiraLocalizacao.name}</span>
          </p>
        ) : (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={idLocalizacao}>{textos.desperdicio.localizacao}</Label>
            <Select value={localizacao} onValueChange={setLocalizacao}>
              <SelectTrigger id={idLocalizacao} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {nivel.by_location.map((parcela) => (
                  <SelectItem key={parcela.location.id} value={parcela.location.id}>
                    {parcela.location.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <Label htmlFor={idQuantidade}>{textos.desperdicio.quantidadeEm(unidadeBase)}</Label>
          <Input
            id={idQuantidade}
            name="quantidade"
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={quantidade}
            onChange={(evento) => {
              setQuantidade(evento.target.value);
            }}
            placeholder={textos.desperdicio.exemploDeQuantidade(unidadeBase)}
            aria-invalid={erros.quantidade === undefined ? undefined : true}
            aria-describedby={
              erros.quantidade === undefined ? idUnidade : `${idUnidade} ${idErroDeQuantidade}`
            }
          />
          {unidadeBase === unidadeMostrada ? null : (
            <p id={idUnidade} className="text-xs text-muted-foreground">
              {textos.desperdicio.unidadeDeRegisto(unidadeMostrada, unidadeBase)}
            </p>
          )}
          {erros.quantidade === undefined ? null : (
            <p id={idErroDeQuantidade} className="text-sm text-danger">
              {erros.quantidade}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor={idMotivo}>{textos.desperdicio.motivo}</Label>
          <Select
            value={motivo}
            onValueChange={(valor) => {
              // O valor vem do próprio `SelectItem`, mas passa pelo schema do
              // contrato em vez de por uma asserção de tipo: é o mesmo enum que
              // o servidor valida, e uma asserção aqui seria a única linha do
              // ecrã em que o tipo é uma promessa.
              const analisado = motivoQuebraSchema.safeParse(valor);
              if (analisado.success) setMotivo(analisado.data);
            }}
          >
            <SelectTrigger
              id={idMotivo}
              className="w-full"
              aria-invalid={erros.motivo === undefined ? undefined : true}
              aria-describedby={erros.motivo === undefined ? undefined : idErroDeMotivo}
            >
              <SelectValue placeholder={textos.desperdicio.escolhaOMotivoPista} />
            </SelectTrigger>
            <SelectContent>
              {MOTIVOS_DE_DESPERDICIO.map((opcao) => (
                <SelectItem key={opcao} value={opcao}>
                  {rotuloDeMotivo(opcao)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {erros.motivo === undefined ? null : (
            <p id={idErroDeMotivo} className="text-sm text-danger">
              {erros.motivo}
            </p>
          )}
        </div>

        <Button type="submit" disabled={registar.isPending} className="self-start">
          {registar.isPending ? textos.accoes.aRegistar : textos.desperdicio.registar}
        </Button>
      </form>

      {/* O resultado, em `role="status"`: quem não está a olhar para o ecrã tem
          de o ouvir. O movimento novo aparece no histórico abaixo por
          invalidação da cache, não por o escrevermos aqui à mão. */}
      <p role="status" className="flex items-start gap-1.5 text-sm">
        {registar.isSuccess ? (
          <>
            <CircleCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-success" />
            <span>
              {registar.data.lot_code === null
                ? textos.desperdicio.registado
                : textos.desperdicio.registadoNoLote(registar.data.lot_code)}
            </span>
          </>
        ) : null}
      </p>

      {registar.isError ? (
        <p role="alert" className="flex items-start gap-1.5 text-sm text-danger">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span>{mensagemDeErro(registar.error)}</span>
        </p>
      ) : null}
    </section>
  );
}
