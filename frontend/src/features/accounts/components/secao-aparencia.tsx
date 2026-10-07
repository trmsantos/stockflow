import { CircleAlert, Palette } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { mensagemDeErro } from "@/lib/api/errors";
import { rotuloDoTema, TEMAS, temaDe, type Tema } from "@/lib/tema";

import { useGuardarTema, useSessao } from "../api";
import { textos } from "../textos";

/**
 * `/preferencias` — as definições **desta pessoa** (ADR 0016 e ADR 0017).
 *
 * Hoje tem uma: a paleta. E é um ecrã e não uma linha no pé da sidebar porque a
 * ADR 0017 separou as duas famílias de definições — da pessoa e da empresa — e
 * decidiu que a da pessoa não entra no registo do menu: o ponto de entrada é o
 * pé da sidebar, ao lado do email e da saída da conta, que é onde "a tua conta"
 * vive. Um sétimo item de menu para uma coisa que se toca duas vezes por ano era
 * ruído num menu desenhado para crescer com o domínio.
 *
 * Por não estar no registo, a barra de topo **não** o nomeia (o `rotuloDoCaminho`
 * devolve `null` e o `AppHeader` não escreve nada) — logo o `<h1>` deste ecrã é
 * visível, como em qualquer ecrã de detalhe, e não `sr-only` como nos ecrãs de
 * lista.
 *
 * ## Uma régua de três segmentos, e **não** três cartões — foi corrigido aqui
 *
 * A primeira versão deste ecrã eram três `rounded-lg` com borda própria, um
 * ícone e uma descrição, empilhados com `gap-2`. Funcionava, e era exactamente
 * o tell que o `components/regua-de-contadores.tsx` documenta ter saído deste
 * repositório: *"uma grelha de três cartões iguais ... é o cartão de estatística
 * que aparece em todos os painéis gerados"*, e o DESIGN.md §5 proíbe-o quase
 * pela letra. Foi visto num screenshot, não deduzido — e a lição é que o tell
 * volta pela porta do ecrã novo, porque é a forma que vem primeiro à mão.
 *
 * A forma que ficou é a da casa: **uma moldura com três segmentos encostados**,
 * separados pela régua de 1px que separa as colunas da tabela, e o escolhido
 * marcado pelo **trilho de 4px** — o mesmo idioma do item de menu activo, da
 * linha com excepção e do campo da régua que está a filtrar. Sem radius, sem
 * borda individual, sem sombra, sem `gap`. É o gesto onde a identidade gasta a
 * sua única peça de ousadia, e aqui ele cai no sítio certo: o trilho quer dizer
 * "é este", que é precisamente o que um selector tem para dizer.
 *
 * Em coluna abaixo de `md` e em linha acima: três segmentos de 1/3 num
 * telemóvel davam 110px para uma frase de dez palavras. A régua roda com eles
 * (`divide-y md:divide-x md:divide-y-0`), e o trilho passa de vertical à
 * esquerda a horizontal no topo, que é como a mesma peça se lê nas duas
 * direcções.
 *
 * ## `<input type="radio">` nativo, e não um primitivo
 *
 * O `src/components/ui/` não tem um `radio-group` e acrescentá-lo pelo CLI do
 * shadcn traz o Radix inteiro para um ecrã com três opções. O nativo dá de graça
 * o que aqui importa — grupo navegável com as setas, anúncio de "1 de 3",
 * `:checked` e `:focus-visible` — e o segmento é o `<label>`, que é a área de
 * clique inteira. O input fica `sr-only` e **não** `hidden`: escondido de
 * verdade, deixava de ser focável.
 *
 * Não há bolinha de rádio desenhada: o estado é o trilho, a superfície um degrau
 * acima, e a palavra "em uso" ao lado do nome. Nunca só a cor (DESIGN.md §2) —
 * e, como o trilho é `bg-primary`, nunca **só** o trilho.
 *
 * ## Sem botão de guardar
 *
 * Escolher **é** guardar, e isso não é pressa: o efeito da escolha é a
 * aplicação inteira a mudar de cor, logo não há nada que um botão de confirmação
 * possa acrescentar que o ecrã não mostre melhor. A mutação é optimista (a razão
 * está no `useGuardarTema`) e um erro repinta a paleta anterior — o que a pessoa
 * vê é a cor voltar atrás e a frase a dizer porquê, que é o contrário de um
 * formulário que diz "guardado" por cima de um valor que não foi.
 */

function Esqueleto() {
  // A forma que vem: uma moldura com três segmentos. O esqueleto reserva a
  // moldura e não três blocos soltos, senão o layout salta quando os dados
  // chegam — que é o defeito que um esqueleto existe para evitar.
  return (
    <div
      aria-busy="true"
      className="flex flex-col divide-y divide-border border border-border md:flex-row md:divide-x md:divide-y-0"
    >
      <span className="sr-only">{textos.aparencia.aCarregar}</span>
      {[0, 1, 2].map((indice) => (
        <div key={indice} className="flex flex-1 flex-col gap-2 px-celula-x py-3">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-3 w-full" />
        </div>
      ))}
    </div>
  );
}

function SegmentoDeTema({
  tema,
  activo,
  aGuardar,
  aoEscolher,
}: {
  readonly tema: Tema;
  readonly activo: boolean;
  readonly aGuardar: boolean;
  readonly aoEscolher: (tema: Tema) => void;
}) {
  const { nome, descricao } = rotuloDoTema(tema);

  return (
    // `relative` para dar âncora ao trilho, como no `CLASSE_CONTADOR`.
    // `cursor-pointer` no `<label>` porque a área de clique é ele e não o input.
    <label
      className={
        "relative flex flex-1 cursor-pointer flex-col gap-1 px-celula-x py-3 transition-colors " +
        "has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50 has-[:focus-visible]:ring-inset " +
        (activo ? "bg-surface-2" : "hover:bg-surface-2")
      }
    >
      <input
        type="radio"
        name="tema"
        value={tema}
        checked={activo}
        disabled={aGuardar}
        className="sr-only"
        onChange={() => {
          aoEscolher(tema);
        }}
      />

      {/* O trilho de 4px: à esquerda em coluna, no topo em linha. Decoração —
          quem ouve a página recebe o estado do input, e quem lê recebe o "em
          uso" abaixo. */}
      {activo ? (
        <span
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-trilho bg-primary md:inset-y-0 md:right-auto md:left-0 md:h-auto md:w-trilho"
        />
      ) : null}

      <span className="flex items-baseline gap-2">
        <span className="text-sm font-semibold">{nome}</span>
        {activo ? (
          <span className="text-xs font-bold tracking-microrotulo text-primary uppercase">
            {textos.aparencia.emUso}
          </span>
        ) : null}
      </span>

      <span className="text-xs text-pretty text-muted-foreground">{descricao}</span>
    </label>
  );
}

export function SecaoAparencia() {
  const sessao = useSessao();
  const guardar = useGuardarTema();

  // O tema vem da **sessão** e não do `<html>`, e a diferença importa: o
  // atributo do documento é o que está pintado, que durante uma mutação
  // optimista é o valor novo e durante uma visita à `/dev/tokens` é um valor que
  // ninguém guardou. O que este ecrã mostra é o que a conta prefere.
  const tema = temaDe(sessao.data?.utilizador?.tema);

  return (
    <section aria-labelledby="titulo-da-paleta" className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <h2
            id="titulo-da-paleta"
            className="flex items-center gap-2 text-xs font-bold tracking-microrotulo text-muted-foreground uppercase"
          >
            <Palette aria-hidden="true" className="size-3.5" />
            {textos.aparencia.rotulo}
          </h2>
          <p className="text-sm text-muted-foreground">{textos.aparencia.explicacao}</p>
        </div>

        {guardar.isError ? (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{textos.aparencia.erroTitulo}</AlertTitle>
            <AlertDescription>
              {mensagemDeErro(guardar.error)} {textos.aparencia.erroCorpo}
            </AlertDescription>
          </Alert>
        ) : null}

        {sessao.isPending ? (
          <Esqueleto />
        ) : (
          // `role="radiogroup"` não é preciso: os três inputs partilham o `name`,
          // logo o browser já os expõe como um grupo e anuncia "1 de 3". O que
          // falta é o nome do grupo, e isso vem do `aria-labelledby` da secção.
          <div
            aria-busy={guardar.isPending ? "true" : undefined}
            className="flex flex-col divide-y divide-border border border-border md:flex-row md:divide-x md:divide-y-0"
          >
            {TEMAS.map((nome) => (
              <SegmentoDeTema
                key={nome}
                tema={nome}
                activo={nome === tema}
                aGuardar={guardar.isPending}
                aoEscolher={(escolhido) => {
                  // Escolher o que já está escolhido é um PATCH que muda nada.
                  if (escolhido !== tema) guardar.mutate({ tema: escolhido });
                }}
              />
            ))}
          </div>
        )}
    </section>
  );
}
