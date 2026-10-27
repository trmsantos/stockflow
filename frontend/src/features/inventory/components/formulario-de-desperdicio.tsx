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
import {
  motivoQuebraSchema,
  type MotivoQuebra,
  type Movimento,
  type NivelDeStock,
} from "../schemas";
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
 * ## A unidade é um campo, e isso fechou o buraco mais caro deste ecrã
 *
 * O corpo da quebra leva `quantity` **e** `unit` desde a ADR 0034 (decisão 11),
 * e o campo nasce com a **unidade de apresentação** escolhida — é a unidade em
 * que a pessoa fala. Antes, o contrato dizia "unidade BASE" e o ecrã mostrava a
 * unidade de apresentação ao lado do campo: às 6 da manhã, em pé, quem deita
 * fora dois pães escreve `2` e ficavam **2 g** registados num ledger
 * append-only, sem botão de desfazer.
 *
 * A conversão é do **servidor**, sempre: converter unidades no cliente é a
 * fonte nº 1 de bugs de stock (`inventory-domain` §2), e o que o 201 devolve já
 * vem convertido, para a frase de confirmação dizer "2 kg" a quem escreveu 2.
 *
 * Com uma unidade só (quando a base e a de apresentação coincidem — `un`, por
 * exemplo) não há selector nenhum: um controlo que não escolhe é cromado, e a
 * unidade fica escrita ao lado do campo na mesma.
 *
 * ## O lote não se escolhe, e o 201 traz os que foram
 *
 * Aqui a acção parte do artigo e não de um lote, logo o corpo vai sem `lot` e o
 * servidor escolhe por FEFO na localização pedida — repartindo por quantos
 * forem precisos. É por isso que a confirmação nomeia **os lotes**, no plural:
 * uma quebra de 2 kg com o lote mais velho a 0,4 kg são três linhas no ledger,
 * e dizer "registado no lote X" escondia as outras duas.
 */

/** A mesma forma que o `decimal` do `schemas.ts`, sem sinal: é um valor absoluto. */
const DECIMAL_POSITIVO = /^\d+$|^\d+\.\d+$/;

interface Erros {
  readonly quantidade?: string;
  readonly motivo?: string;
}

/**
 * A frase de confirmação, construída sobre a **lista** de movimentos do 201.
 *
 * A quantidade é a soma? Não: é a de cada linha, e o que se nomeia são os
 * lotes. Uma quebra reparte-se por ordem de validade quando o lote mais velho
 * não chega, e quem acabou de carregar no botão tem de saber de onde saiu — é
 * essa a diferença entre um registo e um número que apareceu.
 *
 * Três casos, e nenhum deles é "registado no lote X" quando há mais do que um:
 *  - um movimento, com código de lote: nomeia-o;
 *  - um movimento sem código (lote sintético) ou nenhum: diz só que ficou
 *    registado, porque não há nome a dar;
 *  - vários: nomeia-os todos, separados por vírgula. São dois ou três na
 *    prática, e a lista cabe na linha.
 */
function fraseDoRegisto(movimentos: readonly Movimento[]): string {
  const codigos = movimentos
    .map((movimento) => movimento.lot_code)
    .filter((codigo): codigo is string => codigo !== null);

  if (codigos.length === 0) return textos.desperdicio.registado;
  if (codigos.length === 1) return textos.desperdicio.registadoNoLote(codigos[0] ?? "");
  return textos.desperdicio.registadoNosLotes(codigos.join(", "));
}

export function FormularioDeDesperdicio({ nivel }: { readonly nivel: NivelDeStock }) {
  const idQuantidade = useId();
  const idErroDeQuantidade = useId();
  const idMotivo = useId();
  const idErroDeMotivo = useId();
  const idUnidade = useId();
  const idSeletorDeUnidade = useId();
  const idLocalizacao = useId();

  const primeiraLocalizacao = nivel.by_location[0]?.location;
  const unidadeBase = nivel.quantity.base_unit;
  const unidadeMostrada = nivel.quantity.display_unit;
  // As unidades que o servidor aceita para **este** artigo, e só essas: a base
  // e a de apresentação. Qualquer outra é 400, porque não há motor genérico de
  // conversão (ADR 0011). Uma só quando coincidem — e aí não há escolha.
  const unidades =
    unidadeBase === unidadeMostrada ? [unidadeBase] : [unidadeMostrada, unidadeBase];

  const [localizacao, setLocalizacao] = useState(primeiraLocalizacao?.id ?? "");
  // Pré-seleccionada a de apresentação: é a unidade em que a pessoa fala.
  const [unidade, setUnidade] = useState(unidadeMostrada);
  const [quantidade, setQuantidade] = useState("");
  const [motivo, setMotivo] = useState<MotivoQuebra | "">("");
  const [erros, setErros] = useState<Erros>({});

  const registar = useRegistarDesperdicio();

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
        : { quantidade: textos.desperdicio.escrevaAQuantidade(unidade) }),
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
      {
        product: nivel.product,
        location: localizacao,
        quantity: valor,
        // A unidade viaja **explícita**. Sem ela era uma convenção, e uma
        // convenção não sobrevive a dois ecrãs — entre `g` e `kg` há um factor
        // de 1000 e o destino não tem desfazer.
        unit: unidade,
        reason: motivo,
      },
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
          <Label htmlFor={idQuantidade}>{textos.desperdicio.quantidade}</Label>
          {/* O número e a unidade lado a lado, porque são **uma** resposta:
              "dois quilos" lê-se de uma vez e não em duas perguntas. O campo
              estica, o selector tem a largura do que lá cabe (`kg`, `un`), e os
              dois têm a altura de controlo do DESIGN.md §2 — 40px em desktop,
              44px num ecrã de toque pelo `pointer: coarse` do `base.css`. */}
          {/* Com tecto, pela mesma razão que o campo de procurar do Stock o
              tem: sem ele o campo esticava até aos ~890px da área de conteúdo
              em desktop e punha a unidade a quase um metro do número que ela
              qualifica — que é o oposto do que este par existe para fazer.
              Medido na fotografia a 1280px. */}
          <div className="flex max-w-sm items-stretch gap-2">
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
              placeholder={textos.desperdicio.exemploDeQuantidade(unidade)}
              className="min-w-0 flex-1"
              aria-invalid={erros.quantidade === undefined ? undefined : true}
              aria-describedby={
                erros.quantidade === undefined ? idUnidade : `${idUnidade} ${idErroDeQuantidade}`
              }
            />
            {unidades.length === 1 ? (
              // Uma unidade só: não há nada a escolher, e um selector de uma
              // opção é um controlo que não escolhe. A unidade continua à
              // vista, que é o que importa.
              // `items-stretch` na linha e nenhuma altura escrita aqui: a
              // unidade acompanha o campo, que é 32px em desktop e 44px num
              // ecrã de toque (o `pointer: coarse` do `base.css`). Um número no
              // JSX desalinhava-se de um dos dois.
              <span className="flex shrink-0 items-center text-sm text-muted-foreground">
                {unidade}
              </span>
            ) : (
              <>
                <Label htmlFor={idSeletorDeUnidade} className="sr-only">
                  {textos.desperdicio.unidade}
                </Label>
                <Select value={unidade} onValueChange={setUnidade}>
                  <SelectTrigger id={idSeletorDeUnidade} className="w-24 shrink-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {unidades.map((opcao) => (
                      <SelectItem key={opcao} value={opcao}>
                        {opcao}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </>
            )}
          </div>
          <p id={idUnidade} className="text-xs text-muted-foreground">
            {unidades.length === 1
              ? textos.desperdicio.unidadeUnica(unidade)
              : textos.desperdicio.unidadeAEscolher(unidadeMostrada, unidadeBase)}
          </p>
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
            <span>{fraseDoRegisto(registar.data.movements)}</span>
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
