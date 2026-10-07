import { Link } from "@tanstack/react-router";

import type { AbaDoPainel } from "../abas";
import { ABAS, rotuloDaAba } from "../abas";
import { textos } from "../textos";

/**
 * As **três abas do painel** — e são `<Link>`s, não botões.
 *
 * ## Porque é que o painel tem abas
 *
 * Porque tinha 3630px de altura e nove tabelas, e o dono do produto leu isso
 * como confusão e não como completude. A razão estrutural é que o painel
 * respondia a três perguntas diferentes com **as mesmas formas** e números
 * diferentes: "quanto entrou e saiu", "o que se perdeu" e "quanto custa a
 * equipa". Empilhadas no mesmo scroll, obrigavam a ler uma tabela de rubricas e
 * valores três vezes e a perceber a meio qual delas se estava a ler.
 *
 * As abas não escondem informação: mudam **quando** ela aparece. E o que fica
 * fora delas é o que vale para as três — a barra com a janela e o bloco de
 * qualidade de dados, que diz em que números se pode confiar.
 *
 * ## `<Link>` e não `<button>`, e a diferença é de produto
 *
 * Uma aba tem de ser partilhável, sobreviver a um recarregamento e abrir noutro
 * separador com Cmd+clique. Um `<button>` com `useState` não faz nenhuma das
 * três, e é o estado que **define** o ecrã (ADR 0008, decisão 1). O
 * `aria-current="page"` é o que diz qual está activa a quem ouve o ecrã — a
 * tinta e o trilho não comunicam sozinhos (DESIGN.md §2).
 *
 * O trilho de 4px fica na **aresta de baixo** da aba activa e não na esquerda: é
 * o mesmo idioma do item de menu e da linha da tabela, virado para onde a aba
 * aponta — o painel que está logo por baixo.
 */
export function AbasDoPainel({ ativa }: { readonly ativa: AbaDoPainel }) {
  return (
    <nav aria-label={textos.abas.regua} className="flex items-stretch self-stretch">
      {ABAS.map((chave) => {
        const ativo = chave === ativa;
        return (
          <Link
            key={chave}
            to="/painel"
            // O reducer recebe a busca actual já validada pela rota: mudar de
            // aba **preserva** o período, o mês e a camada de explicação. São
            // grãos independentes (ADR 0013, decisão 5), e perder um ao mexer
            // noutro seria tratá-los como um.
            search={(anteriores) => ({ ...anteriores, aba: chave })}
            aria-current={ativo ? "page" : undefined}
            // O anel de foco é o do `base.css` (`:focus-visible`, 2px no
            // `--color-ring`) e não um à parte: um foco com outra cor neste
            // ecrã era uma segunda convenção para a mesma coisa. O
            // `focus-visible:z-10` existe porque as abas são `relative` e em
            // ordem de documento — sem ele, a aba seguinte pintava por cima do
            // anel da anterior.
            className={`relative flex items-center px-celula-x text-sm font-semibold transition-colors focus-visible:z-10 ${
              ativo ? "bg-surface-2 text-foreground" : "text-muted-foreground hover:bg-surface-2"
            }`}
          >
            {rotuloDaAba(chave)}
            {ativo ? (
              <span
                aria-hidden="true"
                className="absolute inset-x-0 bottom-0 h-trilho bg-primary"
              />
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
}
