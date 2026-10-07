import { CircleAlert, CircleCheck } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import type { Rececao } from "../schemas";

/**
 * A temperatura à entrega.
 *
 * Aparece quando a receção traz frio — refrigerado ou congelado — e é o servidor
 * que o diz (`cold_chain`). Um campo, um botão, nenhuma explicação: quem já faz
 * este registo em papel reconhece-o sem lhe dizerem nada, e é a reação dele que
 * interessa.
 *
 * Aceita negativos (um ultracongelado chega a −18 °C) e aceita vírgula, que é
 * como se escreve em português. Não valida o valor contra limiar nenhum: um
 * congelado a −4 °C é precisamente o que vale a pena ter registado, e um ecrã
 * que o recusasse apagava o único caso que importa.
 */

/** Um número com sinal e até uma casa decimal: "-18", "-18,5", "4". */
const GRAUS = /^-?\d{1,2}$|^-?\d{1,2}[.,]\d$/;

export function TemperaturaAEntrega({
  rececao,
  aGuardar,
  erroDoServidor,
  aoGuardar,
}: {
  readonly rececao: Rececao;
  readonly aGuardar: boolean;
  readonly erroDoServidor: string | null;
  readonly aoGuardar: (celsius: string) => void;
}) {
  const idCampo = useId();
  const idErro = useId();
  const [erro, setErro] = useState<string | null>(null);

  function aoSubmeter(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const campo = new FormData(evento.currentTarget).get("graus");
    const escrito = (typeof campo === "string" ? campo : "").trim();

    if (!GRAUS.test(escrito)) {
      setErro("Escreva os graus, por exemplo -18 ou 4,5.");
      return;
    }

    setErro(null);
    // A vírgula decimal é como se escreve em português; o contrato quer ponto.
    aoGuardar(escrito.replace(",", "."));
  }

  return (
    <form onSubmit={aoSubmeter} className="flex flex-col gap-1.5 px-4">
      <Label htmlFor={idCampo} className="text-sm">
        Temperatura à entrega (°C)
      </Label>
      <div className="flex items-start gap-2">
        <Input
          id={idCampo}
          name="graus"
          type="text"
          inputMode="decimal"
          autoComplete="off"
          // O `key` remonta o campo quando o servidor confirma outro valor: o
          // campo é não controlado, logo não há nada a reconciliar com a cache.
          key={rececao.temperature_c ?? "sem-temperatura"}
          defaultValue={rececao.temperature_c ?? ""}
          placeholder="—"
          data-numeric
          className="h-11 w-24 shrink-0 text-base"
          aria-invalid={erro === null ? undefined : true}
          aria-describedby={erro === null ? undefined : idErro}
        />
        <Button type="submit" variant="outline" disabled={aGuardar}>
          {aGuardar ? "A guardar…" : "Guardar"}
        </Button>
        {rececao.temperature_c === null || aGuardar ? null : (
          <span className="flex items-center gap-1 pt-3 text-xs text-muted-foreground">
            <CircleCheck aria-hidden="true" className="size-3.5 shrink-0 text-success" />
            registada
          </span>
        )}
      </div>

      {erro === null ? null : (
        <p id={idErro} className="text-sm text-danger">
          {erro}
        </p>
      )}

      {erroDoServidor === null ? null : (
        <p role="alert" className="flex items-start gap-1.5 text-sm text-danger">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span>{erroDoServidor}</span>
        </p>
      )}
    </form>
  );
}
