import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  EsqueletoDeTabela,
  MolduraDeTabela,
  type ColunaDeTabela,
} from "@/components/tabela";
import { formatMoney, formatTime } from "@/lib/format";

import type { Desperdicio } from "../schemas";
import { rotuloDeMotivo, textoDeQuantidade } from "../vocabulario";

/**
 * O que foi deitado fora, como tabela.
 *
 * ## Sem trilho, e é uma decisão
 *
 * Esta é a primeira tabela do repositório **sem** a coluna de sinal, e a razão é
 * semântica: o trilho quer dizer "isto precisa de atenção". Uma linha do registo
 * de desperdício é um facto consumado — já foi deitado fora, já está no ledger.
 * Pintar-lhe um trilho vermelho era pedir uma acção que não existe, e uma coluna
 * de 4px acesa em todas as linhas não distingue nada de nada.
 *
 * **Não há acção nenhuma nesta tabela, e é de propósito.** Um movimento é
 * append-only (ADR 0006: `REVOKE UPDATE, DELETE`): corrige-se com um movimento
 * inverso, nunca com um botão de apagar — que é a proibição nº 2 do guião §4.
 *
 * ## A hora é a primeira coluna, e é a sonda da Q6
 *
 * "05:10 — Pastéis de ontem, 12 un, 4,20 €" é uma linha que o dono reconhece, e é
 * a partir dela que ele diz "isso é de ontem" — que é a resposta à pergunta sobre
 * a hora a que o dia de negócio começa, sem ela ter sido feita. Numa coluna
 * própria, alinhada e em mono, as horas comparam-se na vertical: se três quebras
 * estão todas antes das 05:00, isso vê-se em vez de se somar de cabeça.
 *
 * Os oito factos que o rodapé juntava com pontos médios ("estragado · Ana
 * (balcão) · Copa · lote L-NAT-1002") passaram a quatro colunas. **Quem** tem
 * coluna porque é a sonda da Q7: toda a linha do ledger tem autor, e numa coluna
 * vê-se se é sempre a mesma pessoa a registar.
 */

const COLUNAS: readonly ColunaDeTabela[] = [
  { chave: "hora", rotulo: "Hora", classe: "w-24 text-right" },
  { chave: "artigo", rotulo: "Artigo" },
  { chave: "quantidade", rotulo: "Quantidade", classe: "w-32 text-right" },
  { chave: "valor", rotulo: "Valor", classe: "w-28 text-right" },
  { chave: "motivo", rotulo: "Motivo", classe: "w-36" },
  { chave: "quem", rotulo: "Quem" },
  { chave: "onde", rotulo: "Onde" },
  { chave: "lote", rotulo: "Lote", classe: "w-36" },
];

const LARGURA_MINIMA = "min-w-5xl";
const ROTULO = "Movimentos de desperdício, do mais recente para o mais antigo";

export function TabelaDeDesperdicio({ linhas }: { readonly linhas: readonly Desperdicio[] }) {
  return (
    <MolduraDeTabela colunas={COLUNAS} larguraMinima={LARGURA_MINIMA} rotulo={ROTULO}>
      <tbody>
        {linhas.map((linha) => (
          <tr key={linha.id} className={`${CLASSE_LINHA} transition-colors hover:bg-surface-2`}>
            <td data-numeric className={`${CLASSE_CELULA} w-24 text-right text-muted-foreground`}>
              {formatTime(linha.occurred_at)}
            </td>
            <td className={`${CLASSE_CELULA} max-w-0 font-medium`}>
              <span className="block truncate">{linha.short_name}</span>
            </td>
            <td data-numeric className={`${CLASSE_CELULA} w-32 text-right`}>
              {textoDeQuantidade(linha.quantity)}
            </td>
            <td data-numeric className={`${CLASSE_CELULA} w-28 text-right`}>
              {formatMoney(linha.value_eur)}
            </td>
            <td className={`${CLASSE_CELULA} w-36`}>{rotuloDeMotivo(linha.reason)}</td>
            <td className={`${CLASSE_CELULA} max-w-0 text-muted-foreground`}>
              <span className="block truncate">{linha.created_by}</span>
            </td>
            <td className={`${CLASSE_CELULA} max-w-0 text-muted-foreground`}>
              <span className="block truncate">{linha.location.name}</span>
            </td>
            <td data-numeric className={`${CLASSE_CELULA} w-36 text-left text-muted-foreground`}>
              {linha.lot_code ?? ""}
            </td>
          </tr>
        ))}
      </tbody>
    </MolduraDeTabela>
  );
}

export function EsqueletoDaTabelaDeDesperdicio({ linhas = 4 }: { readonly linhas?: number }) {
  return (
    <EsqueletoDeTabela
      colunas={COLUNAS}
      larguraMinima={LARGURA_MINIMA}
      rotulo="A carregar o desperdício…"
      linhas={linhas}
    />
  );
}
