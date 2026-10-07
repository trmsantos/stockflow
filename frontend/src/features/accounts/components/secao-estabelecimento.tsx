import { useState } from "react";
import { CircleAlert, FlaskConical, RotateCcw, Save } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { Skeleton } from "@/components/ui/skeleton";
import { mensagemDeErro } from "@/lib/api/errors";

import { useConfiguracaoDoEstabelecimento, useGuardarEstabelecimento } from "../api";
import type { ConfiguracaoDoEstabelecimento, RegimeDeIva } from "../schemas";

/**
 * A secção **Estabelecimento** das Definições: o nome por que esta casa aparece,
 * e as duas coisas que decidem contas.
 *
 * Era o ecrã `/configuracao`, com entrada própria no menu da sidebar, até
 * 2026-10-07. Passou a secção por decisão do dono do produto (ADR 0019, decisão
 * 6), que supersede a decisão 1 da ADR 0017 — dois ecrãs.
 *
 * ## O que cada campo decide, porque nenhum dos dois é uma preferência
 *
 * O **regime de IVA** decide se o IVA de uma compra é custo: em regime normal é
 * dedutível e o custo é a base tributável; no art. 53.º não é dedutível e o
 * custo é o total da fatura. O rótulo diz "Regime de IVA" e **nunca "Regime"**,
 * porque o que um dono chama "simplificado" é o regime de **IRS** e metade das
 * respostas seria sobre outro imposto (`domain-expert`, 2026-10-07).
 *
 * A **hora a que o dia de negócio começa** decide a que dia pertence um
 * movimento e onde começa o mês. O aviso de que mudá-la **recalcula** os dias
 * passados aparece antes de gravar e não depois: é retroactivo de propósito (a
 * alternativa, histórico da hora, parte o invariante `Σ(dias) == mês` da ADR
 * 0013), e o efeito real limita-se aos movimentos registados entre as duas
 * horas. E diz-se o que ela **não** decide, porque é o erro que alguém
 * escreveria: as validades são a data impressa na embalagem e não se deslocam
 * com este relógio.
 *
 * ## O que não está aqui
 *
 * **O horizonte de validade não entra**, e é decisão e não falta de tempo: é
 * literalmente o campo de que a proibição nº 7 do guião da sessão 0 fala —
 * mostrar um limiar remove o sinal que diz qual é o default certo — e um número
 * único por casa é estruturalmente errado (a 3 dias, o pastel de nata fica em
 * alerta permanente desde que entra e a farinha é avisada 3 dias antes de um DDM
 * a 9 meses). A forma certa é por família de produto, e a ADR 0017 já a pôs num
 * endpoint separado.
 *
 * **O NIF também não**: exige `nif_encrypted` + `nif_hmac` com pepper fora da
 * base de dados (`SECURITY.md` §3) e tem a questão do NIF duplicado em aberto
 * desde a ADR 0007.
 */
/** Os dois regimes por extenso, e **o que cada um faz ao custo**. */
const REGIMES: Record<RegimeDeIva, { readonly nome: string; readonly efeito: string }> = {
  normal: {
    nome: "Regime normal",
    efeito: "O IVA das compras é dedutível, logo o custo de um artigo é o valor sem IVA.",
  },
  isento_art_53: {
    nome: "Isento (art. 53.º)",
    efeito: "O IVA das compras não é dedutível, logo é custo: entra no valor do stock.",
  },
};

const REGIMES_POR_NOME = new Map(Object.entries(REGIMES));

export function SecaoEstabelecimento() {
  const configuracao = useConfiguracaoDoEstabelecimento(true);
  const guardar = useGuardarEstabelecimento();

  /**
   * O rascunho. `null` até haver resposta, pela razão do rascunho do menu: com um
   * objecto vazio por omissão, o botão de guardar ficava activo sobre campos que
   * ninguém viu.
   */
  const [rascunho, setRascunho] = useState<ConfiguracaoDoEstabelecimento | null>(null);

  if (configuracao.isPending) {
    return (
      <div aria-busy="true" className="flex max-w-xl flex-col gap-4">
        <span className="sr-only">A carregar a configuração do estabelecimento…</span>
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-40" />
      </div>
    );
  }

  if (configuracao.isError) {
    return (
      <Alert variant="destructive">
        <CircleAlert aria-hidden="true" />
        <AlertTitle>Não foi possível ler a configuração</AlertTitle>
        <AlertDescription>{mensagemDeErro(configuracao.error)}</AlertDescription>
      </Alert>
    );
  }

  const actual = configuracao.data;
  const valores = rascunho ?? actual;
  const mexido = rascunho !== null;
  const horaMudou = valores.business_day_starts_at !== actual.business_day_starts_at;

  function mudar(mudanca: Partial<ConfiguracaoDoEstabelecimento>) {
    setRascunho({ ...valores, ...mudanca });
  }

  return (
    <div className="flex max-w-xl flex-col gap-4">
      {actual.demonstracao ? (
        <Alert>
          <FlaskConical aria-hidden="true" />
          <AlertTitle>Este é o estabelecimento de demonstração</AlertTitle>
          <AlertDescription>
            Os dados foram semeados para experimentar e não são de um negócio real. O nome não se
            altera aqui; o resto da configuração muda como em qualquer casa.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="nome-do-estabelecimento">Nome</Label>
        <Input
          id="nome-do-estabelecimento"
          value={valores.nome}
          maxLength={200}
          disabled={guardar.isPending || actual.demonstracao}
          onChange={(evento) => {
            mudar({ nome: evento.target.value });
          }}
        />
        <p className="text-xs text-muted-foreground">
          Como aparece no seletor de estabelecimento e no topo dos ecrãs.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        {/* "Regime de IVA" e nunca "Regime": o que um dono chama "simplificado"
            é o regime de IRS, e metade das respostas seria sobre outro imposto. */}
        <Label htmlFor="regime-de-iva">Regime de IVA</Label>
        <Select
          value={valores.vat_regime}
          disabled={guardar.isPending}
          onValueChange={(escolhido) => {
            const regime = REGIMES_POR_NOME.has(escolhido)
              ? (escolhido as RegimeDeIva)
              : valores.vat_regime;
            mudar({ vat_regime: regime });
          }}
        >
          <SelectTrigger id="regime-de-iva" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(REGIMES).map(([valor, { nome }]) => (
              <SelectItem key={valor} value={valor}>
                {nome}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-pretty text-muted-foreground">
          {REGIMES_POR_NOME.get(valores.vat_regime)?.efeito}
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="dia-de-negocio">O dia de negócio começa às</Label>
        {/* `type="time"` com `step={60}`: o controlo nativo é o que dá o teclado
            certo no telemóvel e o formato local. O `step` tira os segundos do
            picker, que o contrato não transporta. */}
        <Input
          id="dia-de-negocio"
          type="time"
          step={60}
          className="w-32"
          value={valores.business_day_starts_at}
          disabled={guardar.isPending}
          onChange={(evento) => {
            mudar({ business_day_starts_at: evento.target.value });
          }}
        />
        <p className="text-xs text-pretty text-muted-foreground">
          É a hora que separa um dia do seguinte nos totais e nos alertas. Com{" "}
          {actual.business_day_starts_at}, o que acontece à 01:30 conta no dia anterior, e o mês vai
          do dia 1 às {actual.business_day_starts_at} ao dia 1 do mês seguinte à mesma hora — não é
          o mês fiscal. <strong>As validades não mudam com esta hora</strong>: são a data impressa
          na embalagem.
        </p>
        {horaMudou ? (
          // O aviso aparece **antes** de gravar e só quando a hora mudou. É
          // retroactivo de propósito (a alternativa parte o invariante do mês da
          // ADR 0013), e dizê-lo é o que separa uma decisão de uma surpresa.
          <Alert>
            <CircleAlert aria-hidden="true" />
            <AlertTitle>Mudar esta hora recalcula os dias e os meses já passados</AlertTitle>
            <AlertDescription>
              Só mudam de dia os movimentos registados entre as{" "}
              {actual.business_day_starts_at} e as {valores.business_day_starts_at}.
            </AlertDescription>
          </Alert>
        ) : null}
      </div>

      {guardar.isError ? (
        <Alert variant="destructive">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>A configuração não ficou guardada</AlertTitle>
          <AlertDescription>
            {mensagemDeErro(guardar.error)} O que está no ecrã é o que escreveu, e continua por
            guardar.
          </AlertDescription>
        </Alert>
      ) : null}

      <span className="flex gap-2">
        <Button
          type="button"
          disabled={!mexido || guardar.isPending}
          aria-busy={guardar.isPending}
          onClick={() => {
            guardar.mutate(
              {
                nome: valores.nome,
                vat_regime: valores.vat_regime,
                business_day_starts_at: valores.business_day_starts_at,
              },
              { onSuccess: () => { setRascunho(null); } },
            );
          }}
        >
          <Save aria-hidden="true" />
          {guardar.isPending ? "A guardar…" : "Guardar"}
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={!mexido || guardar.isPending}
          onClick={() => {
            setRascunho(null);
          }}
        >
          <RotateCcw aria-hidden="true" />
          Desfazer
        </Button>
      </span>
    </div>
  );
}
