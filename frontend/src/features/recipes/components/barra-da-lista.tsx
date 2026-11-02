import { Link } from "@tanstack/react-router";
import { Plus, Search } from "lucide-react";
import { useEffect, useState } from "react";

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

import { estadoDaListaSchema, type EstadoDaLista } from "../schemas";
import { textos } from "../textos";

/**
 * A barra *sticky* do topo das Receitas: procurar, escolher o estado, e — para
 * quem escreve fichas — a acção principal.
 *
 * É a irmã da `inventory/components/barra-de-filtros.tsx` e segue-a na forma e
 * nas razões: **não tem título** (o nome do ecrã está no header do shell, com o
 * grupo, e um segundo título aqui era a mesma palavra duas vezes a 40px de
 * distância), o campo de procura tem tecto de 320px (sem ele esticava até à
 * largura do monitor para escrever "pastel"), e é `top-cabecalho` e não um
 * número, para acompanhar a barra do shell em vez de desaparecer por trás dela.
 *
 * ## A procura espera 300ms, e isso é consequência de o filtro ser do servidor
 *
 * `?q=` é um `WHERE` que casa no nome **ou no SKU** do acabado. Escrever
 * "pastel" sem travão são seis pedidos em voo, e numa ligação má é a resposta
 * que interessa a chegar em último. O campo responde à tecla (o rascunho é
 * local) e o **URL**, que é o estado do ecrã, só muda quando a pessoa pára.
 *
 * ## O estado é um seletor de dois e não um interruptor
 *
 * `activas` e `todas` são os dois valores que o contrato serve, e um terceiro é
 * 400 no servidor — o conjunto é fechado dos dois lados. As arquivadas entram
 * **marcadas** e nunca escondidas, porque esconder uma ficha arquivada fazia
 * «não tenho essa receita» mentir; o que o filtro faz é tirá-las do caminho por
 * omissão.
 */

/** O travão da procura: o mesmo intervalo do Stock, pela mesma razão. */
const ATRASO_DA_PROCURA_MS = 300;

export function BarraDaLista({
  termo,
  aoProcurar,
  estado,
  aoEscolherEstado,
  podeEscrever,
}: {
  readonly termo: string;
  readonly aoProcurar: (valor: string) => void;
  readonly estado: EstadoDaLista;
  readonly aoEscolherEstado: (valor: EstadoDaLista) => void;
  readonly podeEscrever: boolean;
}) {
  // O rascunho do campo, local, para a tecla aparecer no instante em que é
  // premida. O `termo` continua a ser a verdade (vem do URL): quando ele muda
  // por fora — "Limpar os filtros", o botão de voltar, um link partilhado — o
  // rascunho acompanha-o. É o ajuste-durante-o-render que o React documenta
  // para derivar estado de propriedades, e não um `useEffect` de sincronização.
  const [rascunho, setRascunho] = useState(termo);
  const [termoVisto, setTermoVisto] = useState(termo);
  if (termo !== termoVisto) {
    setTermoVisto(termo);
    setRascunho(termo);
  }

  useEffect(() => {
    if (rascunho === termo) return undefined;
    const relogio = setTimeout(() => {
      aoProcurar(rascunho);
    }, ATRASO_DA_PROCURA_MS);
    return () => {
      clearTimeout(relogio);
    };
  }, [rascunho, termo, aoProcurar]);

  return (
    <div className="sticky top-cabecalho z-10 flex items-center gap-2 border-b border-border bg-background px-celula-x py-2">
      {/* `role="search"` e não um `<form>`: não há submissão — o filtro aplica-se
          a cada tecla e o estado vive no URL, logo não há nada para enviar. */}
      <div role="search" className="relative min-w-0 flex-1 sm:max-w-xs">
        <Label htmlFor="procurar-ficha" className="sr-only">
          {textos.lista.procurar}
        </Label>
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          id="procurar-ficha"
          name="q"
          type="search"
          value={rascunho}
          onChange={(evento) => {
            setRascunho(evento.target.value);
          }}
          placeholder={textos.lista.procurarPista}
          autoComplete="off"
          spellCheck={false}
          enterKeyHint="search"
          className="pl-8"
        />
      </div>

      <Select
        value={estado}
        onValueChange={(valor) => {
          // O valor vem do próprio `SelectItem`, e passa pelo schema do contrato
          // em vez de por uma asserção de tipo: é o mesmo conjunto fechado que o
          // servidor valida, e uma asserção aqui seria a única linha do ecrã em
          // que o tipo é uma promessa.
          const analisado = estadoDaListaSchema.safeParse(valor);
          if (analisado.success) aoEscolherEstado(analisado.data);
        }}
      >
        <SelectTrigger aria-label={textos.lista.estado} className="w-40 shrink-0 sm:w-52">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="activas">{textos.lista.activas}</SelectItem>
          <SelectItem value="todas">{textos.lista.todas}</SelectItem>
        </SelectContent>
      </Select>

      {/* A acção principal vive aqui e não no fim da lista: é onde o polegar e o
          olho a procuram, e é a única escrita deste ecrã. Escondida para o
          `staff` **por apresentação** — quem autoriza é o servidor, com 403 (ADR
          0009: "esconder é apresentação, não autorização"). */}
      {podeEscrever ? (
        <Button asChild className="ml-auto shrink-0">
          <Link to="/receitas/nova" search={true}>
            <Plus aria-hidden="true" />
            {/* Abaixo de `sm` fica só o `+`, e a palavra fica **para áudio** e
                não apagada: medido a 360px, esta barra tem três controlos (o
                Stock tem dois) e com a palavra inteira o campo de procurar
                encolhia para a largura da lupa. `sr-only` e não `hidden`: um
                botão sem nome acessível é um botão que ninguém ouve. */}
            <span className="sr-only sm:not-sr-only">{textos.accoes.novaFicha}</span>
          </Link>
        </Button>
      ) : null}
    </div>
  );
}
