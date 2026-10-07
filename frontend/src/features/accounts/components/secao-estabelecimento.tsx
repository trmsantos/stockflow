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
import { textos } from "../textos";

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
/**
 * Os dois regimes por extenso, e **o que cada um faz ao custo**.
 *
 * As palavras vêm do catálogo; o que fica aqui é o `Record<RegimeDeIva, …>`, que
 * é a parte que amarra a copy ao contrato: um terceiro regime no `schemas.ts` não
 * compila até alguém o nomear, e o catálogo sozinho não dava essa garantia.
 */
const REGIMES: Record<RegimeDeIva, { readonly nome: string; readonly efeito: string }> = {
  // As quatro folhas nomeadas uma a uma, e não `normal: textos.….regimes.normal`:
  // o `check-textos` conta uma chave como usada quando alguém a **nomeia**, e
  // entregar o objecto inteiro deixava as folhas sem uso visível. Medido: a
  // alternativa era ensinar o gate a aceitar o pai, e isso cobria estas quatro e
  // mais nada — ou seja, trocava-se poder de poda por conveniência.
  normal: {
    nome: textos.estabelecimento.regimes.normal.nome,
    efeito: textos.estabelecimento.regimes.normal.efeito,
  },
  isento_art_53: {
    nome: textos.estabelecimento.regimes.isento_art_53.nome,
    efeito: textos.estabelecimento.regimes.isento_art_53.efeito,
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
        <span className="sr-only">{textos.estabelecimento.aCarregar}</span>
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
        <AlertTitle>{textos.estabelecimento.erroDeLeitura}</AlertTitle>
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
          <AlertTitle>{textos.estabelecimento.demoTitulo}</AlertTitle>
          <AlertDescription>{textos.estabelecimento.demoCorpo}</AlertDescription>
        </Alert>
      ) : null}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="nome-do-estabelecimento">{textos.estabelecimento.nome}</Label>
        <Input
          id="nome-do-estabelecimento"
          value={valores.nome}
          maxLength={200}
          disabled={guardar.isPending || actual.demonstracao}
          onChange={(evento) => {
            mudar({ nome: evento.target.value });
          }}
        />
        <p className="text-xs text-muted-foreground">{textos.estabelecimento.nomeExplicacao}</p>
      </div>

      <div className="flex flex-col gap-1.5">
        {/* "Regime de IVA" e nunca "Regime": o que um dono chama "simplificado"
            é o regime de IRS, e metade das respostas seria sobre outro imposto. */}
        <Label htmlFor="regime-de-iva">{textos.estabelecimento.regimeDeIva}</Label>
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
        <Label htmlFor="dia-de-negocio">{textos.estabelecimento.diaDeNegocio}</Label>
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
        {/* A frase longa é uma função do catálogo (interpola a hora em vigor
            duas vezes) e a ênfase é uma parte nomeada: o `<strong>` do meio é o
            que o DESIGN.md §2 quer que quem lê em diagonal leve, e juntar tudo
            numa string perdia-o. */}
        <p className="text-xs text-pretty text-muted-foreground">
          {textos.estabelecimento.diaDeNegocioExplicacao(actual.business_day_starts_at)}{" "}
          <strong>{textos.estabelecimento.validadesEnfase}</strong>
          {textos.estabelecimento.validadesFim}
        </p>
        {horaMudou ? (
          // O aviso aparece **antes** de gravar e só quando a hora mudou. É
          // retroactivo de propósito (a alternativa parte o invariante do mês da
          // ADR 0013), e dizê-lo é o que separa uma decisão de uma surpresa.
          <Alert>
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{textos.estabelecimento.avisoRetroactivoTitulo}</AlertTitle>
            <AlertDescription>
              {textos.estabelecimento.avisoRetroactivoCorpo(
                actual.business_day_starts_at,
                valores.business_day_starts_at,
              )}
            </AlertDescription>
          </Alert>
        ) : null}
      </div>

      {guardar.isError ? (
        <Alert variant="destructive">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{textos.estabelecimento.erroAoGuardar}</AlertTitle>
          <AlertDescription>
            {mensagemDeErro(guardar.error)} {textos.accoes.naoGuardado}
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
          {guardar.isPending ? textos.accoes.aGuardar : textos.accoes.guardar}
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
          {textos.accoes.desfazer}
        </Button>
      </span>
    </div>
  );
}
