import { CircleAlert, CircleCheck } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import type { Rececao } from "../schemas";
import { textos } from "../textos";

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
  conservation,
  aGuardar,
  erroDoServidor,
  aoGuardar,
}: {
  readonly rececao: Rececao;
  readonly conservation: "chilled" | "frozen";
  readonly aGuardar: boolean;
  readonly erroDoServidor: string | null;
  readonly aoGuardar: (conservation: "chilled" | "frozen", celsius: string) => void;
}) {
  const idCampo = useId();
  const idErro = useId();
  const [erro, setErro] = useState<string | null>(null);

  // Procura a última temperatura registada para esta classe
  const temperaturaRegistada = rececao.temperatures
    .filter((t) => t.conservation === conservation)
    .at(-1);

  function aoSubmeter(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const campo = new FormData(evento.currentTarget).get("graus");
    const escrito = (typeof campo === "string" ? campo : "").trim();

    if (!GRAUS.test(escrito)) {
      setErro(textos.formularios.escrevaOsGraus);
      return;
    }

    setErro(null);
    // A vírgula decimal é como se escreve em português; o contrato quer ponto.
    aoGuardar(conservation, escrito.replace(",", "."));
  }

  return (
    <form onSubmit={aoSubmeter} className="flex flex-col gap-1.5 px-4">
      <Label htmlFor={idCampo} className="text-sm">
        {textos.temperatura.rotulo}
      </Label>
      <div className="flex items-start gap-2">
        <Input
          id={idCampo}
          name="graus"
          type="text"
          inputMode="decimal"
          autoComplete="off"
          key={temperaturaRegistada?.celsius ?? "sem-temperatura"}
          defaultValue={temperaturaRegistada?.celsius ?? ""}
          placeholder="—"
          data-numeric
          className="h-11 w-24 shrink-0 text-base"
          aria-invalid={erro === null ? undefined : true}
          aria-describedby={erro === null ? undefined : idErro}
        />
        <Button type="submit" variant="outline" disabled={aGuardar}>
          {aGuardar ? textos.comuns.aGuardar : textos.temperatura.guardar}
        </Button>
        {temperaturaRegistada === undefined || aGuardar ? null : (
          <span className="flex items-center gap-1 pt-3 text-xs text-muted-foreground">
            <CircleCheck aria-hidden="true" className="size-3.5 shrink-0 text-success" />
            {textos.temperatura.registada}
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
