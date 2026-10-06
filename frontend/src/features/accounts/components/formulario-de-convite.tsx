import { UserPlus } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";

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

import { errosDeValidacao, errosPorCampo, mensagemDaRecusa, statusDaRecusa } from "../erros";
import {
  conviteParaCriarSchema,
  nomeDoPapel,
  papelSchema,
  type ConviteParaCriar,
  type Papel,
} from "../schemas";
import { Aviso } from "./aviso";

/**
 * O formulário de convite — **uma linha de ERP**, não um cartão centrado.
 *
 * ## Porque é que os três campos vivem numa linha
 *
 * Este é um ecrã de escritório (DESIGN.md §1: "donos e encarregados ao
 * computador") e a pergunta dele é "quem tem acesso?", que é a **tabela**. Um
 * formulário empilhado em três linhas de 64px empurrava a resposta abaixo da
 * dobra para pagar um campo de email. A 1280px os três campos e o botão cabem
 * numa linha de controlo (40px) com os rótulos acima, que é a densidade que o §2
 * pede; abaixo de `md` empilham, e aí é a tabela que desce.
 *
 * O email e o nome crescem (`flex-1`), o papel tem largura fixa porque os seus
 * três valores são conhecidos, e o botão tem o tamanho do seu texto. Com quatro
 * colunas iguais, o email — que é o campo longo — ficava do tamanho do seletor
 * de papel.
 *
 * ## Os erros, nos dois sítios onde eles são de facto
 *
 * As recusas de criação são **erros de validação por campo** (400 por campo) e
 * não códigos estáveis: "já existe um convite para este email" e "esta pessoa já
 * é membro" são afirmações sobre o email submetido (ADR 0010, ponto 4). Medido
 * contra o backend a correr: as duas chegam em `{"email": [...]}`, e há mais duas
 * em `{"nome": [...]}` e `{"papel": [...]}`, nenhuma com `code`. Logo aparecem
 * **debaixo do input**, e o banner do topo fica para o que não tem campo — uma
 * recusa de papel (403 sem `code`), um 409 de tenant, uma falha de rede.
 *
 * Os erros locais e os do servidor leem-se com o mesmo `.get(campo)` porque o
 * `erros.ts` devolve os dois na mesma forma, e um campo pode ter os dois em
 * momentos diferentes: o local quando está vazio, o do servidor quando o email
 * já tem convite.
 *
 * ## O `papel` por omissão é `staff`, e é a escolha menos perigosa
 *
 * Não há ordem entre papéis — é a Q7, e a ADR 0010 diz explicitamente para não a
 * inventar —, logo "o mais baixo" não é uma afirmação que este código possa
 * fazer. O que se pode dizer é outra coisa, e é essa que decide: um convite
 * entregue por distracção com o papel errado é um acesso a mais, e `staff` é o
 * único dos três que o backend não deixa convidar ninguém. Um seletor vazio
 * obrigaria a uma escolha a cada convite, o que é defensável — e foi rejeitado
 * porque transforma o caso comum (alguém novo para a copa) em três cliques.
 */

/**
 * Os campos deste formulário, numa lista fechada.
 *
 * É ela que diz ao `errosPorCampo` quais as chaves do 400 do DRF que têm um
 * input onde aparecer — sem ela, um `Object.keys(payload)` punha no ecrã o nome
 * de qualquer chave que o servidor inventasse, incluindo `detail`, debaixo de um
 * input que não existe.
 */
const CAMPOS = ["email", "nome", "papel"] as const;

type Campo = (typeof CAMPOS)[number];

/**
 * Os três papéis, **pela ordem do enum gerado** e não por uma ordem nossa.
 *
 * `papelSchema.options` e não um array escrito à mão: no dia em que o `PapelEnum`
 * do backend ganhar um quarto valor, ele aparece neste seletor sem ninguém se
 * lembrar dele — e a lista nunca pode divergir da união que o `types.ts`
 * declara. Que a ordem do enum não é uma ordem de poder está dito na ADR 0010 e
 * no `schemas.ts`.
 */
const PAPEIS: readonly Papel[] = papelSchema.options;

/** O papel por omissão. A razão está no bloco de abertura. */
const PAPEL_POR_OMISSAO: Papel = "staff";

export function FormularioDeConvite({
  prefixoDeId,
  aSubmeter,
  erroDoServidor,
  aoSubmeter,
}: {
  /**
   * Um prefixo de id **estável**, quando quem monta precisa de nomear um destes
   * campos de fora.
   *
   * Existe por um caso concreto: o estado vazio do ecrã tem de ter uma acção (é o
   * contrato do `EstadoVazio`) e a acção é pôr o foco no campo de email daqui —
   * logo o id tem de ser conhecido dos dois lados. Ausente, usa-se o `useId`, que
   * é o que mantém este componente seguro de ser renderizado duas vezes.
   */
  readonly prefixoDeId?: string | undefined;
  readonly aSubmeter: boolean;
  /** O erro da mutação, ou `null`. Lido aqui para o pôr no campo certo. */
  readonly erroDoServidor: unknown;
  /**
   * Submeter, e o que fazer **se correr bem**.
   *
   * O segundo argumento existe para o formulário se limpar sozinho sem saber o
   * que é uma mutação: o ecrã chama-o no `onSuccess`. As alternativas eram um
   * `ref` ao `<form>` no ecrã (imperativo, e o ecrã passava a conhecer o DOM
   * deste componente) ou um `key` que o remontasse (perdia o foco de quem ia
   * escrever o convite seguinte).
   */
  readonly aoSubmeter: (convite: ConviteParaCriar, aoConseguir: () => void) => void;
}) {
  // `useId` por omissão e não ids literais: este formulário é único hoje, e um
  // id literal é a forma de ele deixar de o ser em silêncio no dia em que alguém
  // o renderizar duas vezes — dois `htmlFor` iguais quebram a ligação
  // rótulo/campo sem nenhum sintoma visível. O hook é chamado sempre (um hook
  // não se chama condicionalmente) e só se ignora quando quem monta dá o seu.
  const gerado = useId();
  const prefixo = prefixoDeId ?? gerado;

  const [email, setEmail] = useState("");
  const [nome, setNome] = useState("");
  const [papel, setPapel] = useState<Papel>(PAPEL_POR_OMISSAO);
  const [errosLocais, setErrosLocais] = useState(() => new Map<Campo, string>());

  const idDoEmail = `${prefixo}-email`;
  const idDoNome = `${prefixo}-nome`;
  const idDoPapel = `${prefixo}-papel`;

  const errosDoServidor = errosPorCampo(erroDoServidor, CAMPOS);
  const temErroDeCampo = errosDoServidor.size > 0;

  // Neste endpoint um 400 é **sempre** por campo (medido nas quatro recusas): se
  // a recusa é 400 e nenhum dos três campos a reclamou, um banner diria uma
  // frase de diagnóstico em vez de uma de produto. Fora dos 400 — 403 de papel,
  // 409 de tenant, rede, CSRF — o banner é o único sítio onde a frase cabe.
  const mostrarBanner =
    erroDoServidor !== null && !temErroDeCampo && statusDaRecusa(erroDoServidor) !== 400;

  function limpar() {
    setEmail("");
    setNome("");
    setPapel(PAPEL_POR_OMISSAO);
    setErrosLocais(new Map());
  }

  function submeter(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();

    // A validação local é o **mesmo** schema que valida o corpo antes de ele
    // sair, com as mensagens dentro dele. Só presença e comprimento: o formato
    // do email tem uma definição e é a do Django, que responde 400 por campo com
    // a frase pronta. O `.trim()` é do schema, logo o que vai no pedido é o mesmo
    // valor que o servidor ia usar.
    const analise = conviteParaCriarSchema.safeParse({ email, nome, papel });
    if (!analise.success) {
      const problemas = errosDeValidacao(analise.error, CAMPOS);
      setErrosLocais(problemas);

      // **Foco no primeiro campo com erro.** É o oposto do `autoFocus` que o
      // `CampoDeTexto` recusa, e a diferença é quem pediu: um foco no primeiro
      // paint faz um leitor de ecrã começar a ler a meio da página sem ninguém
      // ter pedido nada; este acontece **em resposta a um submit**, é o sítio
      // onde a pessoa tem de agir, e sem ele quem navega por teclado fica com o
      // foco no botão e tem de voltar atrás a contar Tabs às cegas.
      //
      // Pela ordem de `CAMPOS`, que é a ordem visual: o primeiro erro de cima.
      const primeiro = CAMPOS.find((campo) => problemas.has(campo));
      if (primeiro !== undefined) document.getElementById(`${prefixo}-${primeiro}`)?.focus();
      return;
    }
    setErrosLocais(new Map());
    aoSubmeter(analise.data, limpar);
  }

  const erroDoEmail = errosLocais.get("email") ?? errosDoServidor.get("email");
  const erroDoNome = errosLocais.get("nome") ?? errosDoServidor.get("nome");
  const erroDoPapel = errosLocais.get("papel") ?? errosDoServidor.get("papel");

  return (
    <section
      aria-labelledby={`${prefixo}-titulo`}
      // `scroll-mt-cabecalho`: a barra do ecrã é sticky a `top-cabecalho`, e sem
      // esta margem de scroll um campo focado por teclado (ou pelo botão do
      // estado vazio) acabava **debaixo** dela — que é a regra "sticky headers
      // must not cover the focused element".
      className="flex scroll-mt-cabecalho flex-col gap-3 rounded-xl border border-border bg-surface p-celula-x"
    >
      <h2 id={`${prefixo}-titulo`} className="text-sm font-semibold">
        Convidar alguém
      </h2>

      {mostrarBanner ? (
        <Aviso
          tom="danger"
          titulo="Não foi possível criar o convite"
          mensagem={mensagemDaRecusa(erroDoServidor)}
        />
      ) : null}

      {/* `noValidate`: a validação é nossa, para a mensagem aparecer **abaixo do
          campo, em texto**, e não numa bolha nativa que o DESIGN.md não desenha
          e que desaparece ao primeiro clique. */}
      <form
        noValidate
        onSubmit={submeter}
        className="flex flex-col gap-3 md:flex-row md:items-start md:gap-2"
      >
        <CampoDoConvite
          id={idDoEmail}
          rotulo="Email"
          erro={erroDoEmail}
          className="md:flex-1"
        >
          <Input
            id={idDoEmail}
            name="email"
            type="email"
            value={email}
            onChange={(evento) => {
              setEmail(evento.target.value);
            }}
            disabled={aSubmeter}
            // Um teclado de telemóvel capitaliza a primeira letra e corrige
            // palavras: num email as duas coisas são sabotagem.
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            // `off` e não `email`: este campo é o email **de outra pessoa**, e um
            // autocomplete de credencial oferecia aqui o de quem está a convidar.
            autoComplete="off"
            maxLength={254}
            placeholder="pessoa@exemplo.pt"
            // Um email é um identificador, não prosa: a tradução automática do
            // browser não tem nada que lhe tocar, e quando toca garante um
            // convite entregue a um endereço que não existe.
            translate="no"
            aria-invalid={erroDoEmail === undefined ? undefined : true}
            aria-describedby={erroDoEmail === undefined ? undefined : `${idDoEmail}-erro`}
            className="h-controlo font-mono"
          />
        </CampoDoConvite>

        <CampoDoConvite
          id={idDoNome}
          rotulo="Nome"
          erro={erroDoNome}
          pista="Como aparece na lista de membros deste estabelecimento."
          className="md:flex-1"
        >
          <Input
            id={idDoNome}
            name="nome"
            type="text"
            value={nome}
            onChange={(evento) => {
              setNome(evento.target.value);
            }}
            disabled={aSubmeter}
            autoComplete="off"
            // Um nome próprio não se corrige nem se capitaliza por regra: o
            // corrector sublinha "Aurora" a vermelho e um teclado de telemóvel
            // "corrige" apelidos.
            autoCorrect="off"
            spellCheck={false}
            maxLength={150}
            placeholder="Ana Silva"
            aria-invalid={erroDoNome === undefined ? undefined : true}
            aria-describedby={
              erroDoNome === undefined
                ? `${idDoNome}-pista`
                : `${idDoNome}-pista ${idDoNome}-erro`
            }
            className="h-controlo"
          />
        </CampoDoConvite>

        <CampoDoConvite
          id={idDoPapel}
          rotulo="Papel"
          erro={erroDoPapel}
          className="md:w-40 md:shrink-0"
        >
          <Select
            value={papel}
            onValueChange={(valor) => {
              // O valor do Radix é `string`; quem decide se é um papel é o
              // schema. Um `as Papel` aqui era uma afirmação sobre dados que
              // vêm de um componente, e o `typescript-eslint/strict` recusa-a
              // com razão.
              const analise = papelSchema.safeParse(valor);
              if (analise.success) setPapel(analise.data);
            }}
            disabled={aSubmeter}
          >
            <SelectTrigger id={idDoPapel} className="h-controlo w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PAPEIS.map((opcao) => (
                <SelectItem key={opcao} value={opcao}>
                  {nomeDoPapel(opcao)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CampoDoConvite>

        {/* O botão alinha com os **inputs** e não com os rótulos: em `md` o
            `pt-6` é a altura do microrótulo acima dele. Em mobile não há rótulo
            a compensar, porque o botão está na sua própria linha. */}
        <div className="md:shrink-0 md:pt-6">
          <Button
            type="submit"
            className="h-controlo w-full md:w-auto"
            disabled={aSubmeter}
            aria-busy={aSubmeter}
          >
            <UserPlus aria-hidden="true" />
            {aSubmeter ? "A criar…" : "Criar convite"}
          </Button>
        </div>
      </form>
    </section>
  );
}

/**
 * Rótulo acima, controlo, pista e erro abaixo **em texto** (DESIGN.md §3).
 *
 * Não reutiliza o `CampoDeTexto` desta mesma pasta, e a razão é que o
 * `CampoDeTexto` **é** o input: recebe `valor`/`aoMudar` e renderiza um
 * `<Input>`. Aqui um dos três campos é um `<Select>` do Radix, que não tem
 * `value`/`onChange` de input nem aceita os atributos de teclado que o outro
 * passa. Generalizar o `CampoDeTexto` para servir os dois dava um componente com
 * dois modos e um `children` opcional — exactamente a forma que ele evita. Este
 * faz a outra metade: a **moldura** (ligação `htmlFor`/`id`, ordem visual, ids
 * derivados) com o controlo por `children`.
 *
 * O `role="alert"` não está no parágrafo de erro, de propósito e pela mesma razão
 * do `CampoDeTexto`: um `alert` por campo fazia um leitor de ecrã anunciar três
 * erros ao mesmo tempo no submit. Quem anuncia é o banner; o `aria-describedby`
 * faz o campo dizer o seu erro quando recebe foco, que é quando interessa.
 */
function CampoDoConvite({
  id,
  rotulo,
  erro,
  pista,
  className,
  children,
}: {
  readonly id: string;
  readonly rotulo: string;
  readonly erro?: string | undefined;
  readonly pista?: string | undefined;
  readonly className?: string | undefined;
  readonly children: ReactNode;
}) {
  return (
    <div className={`flex min-w-0 flex-col gap-1.5 ${className ?? ""}`}>
      <Label htmlFor={id} className="text-xs font-bold tracking-microrotulo uppercase">
        {rotulo}
      </Label>
      {children}
      {pista === undefined ? null : (
        <p id={`${id}-pista`} className="text-xs text-muted-foreground">
          {pista}
        </p>
      )}
      {erro === undefined ? null : (
        <p id={`${id}-erro`} className="text-sm text-danger">
          {erro}
        </p>
      )}
    </div>
  );
}
