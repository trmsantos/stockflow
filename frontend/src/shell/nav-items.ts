import { Boxes, ClipboardCheck, House, TriangleAlert, Truck, type LucideIcon } from "lucide-react";

/**
 * Os itens de navegação — **um** array, e só um.
 *
 * A sidebar renderiza-o todo; a tab bar renderiza os marcados para mobile. Se
 * fossem duas listas, a primeira pergunta do dono fazia-as divergir e a
 * navegação de telemóvel passava a mostrar outra coisa que a de desktop (ADR
 * 0008, decisão 2).
 *
 * O shell conhece **caminhos de rota, nunca domínios**: não há aqui um import
 * de `@/features/*` nem de `@/routes/*`, e o `eslint.config.js` impõe-o.
 *
 * Os URLs são em português porque são copy de produto; as pastas das features
 * têm os nomes dos módulos do backend porque são código.
 */

/** Os caminhos que o shell conhece. */
export type CaminhoDeNavegacao = "/" | "/stock" | "/receber" | "/contar" | "/alertas";

export interface ItemDeNavegacao {
  readonly to: CaminhoDeNavegacao;
  readonly rotulo: string;
  readonly icone: LucideIcon;
  /** A pergunta que o ecrã responde (DESIGN.md §1). Vai no `title` do link. */
  readonly pergunta: string;
  /** Entra na tab bar de mobile. */
  readonly mobile: boolean;
}

export const ITENS_DE_NAVEGACAO = [
  {
    to: "/stock",
    rotulo: "Stock",
    icone: Boxes,
    pergunta: "O que é que eu tenho, e quanto?",
    mobile: true,
  },
  {
    to: "/receber",
    rotulo: "Receber",
    icone: Truck,
    pergunta: "O que chegou, e está certo?",
    mobile: true,
  },
  {
    to: "/contar",
    rotulo: "Contar",
    icone: ClipboardCheck,
    pergunta: "O que está na prateleira é o que o sistema diz?",
    mobile: true,
  },
  {
    to: "/alertas",
    rotulo: "Alertas",
    icone: TriangleAlert,
    pergunta: "O que expira? O que falta? Quanto deitei fora?",
    mobile: true,
  },
  {
    // A raiz fica fora da tab bar: em mobile os 530px úteis são 3 números e 7
    // linhas (guião §0), e um quinto alvo come a largura dos outros quatro.
    to: "/",
    rotulo: "Início",
    icone: House,
    pergunta: "Em que estado está a aplicação?",
    mobile: false,
  },
] as const satisfies readonly ItemDeNavegacao[];

/**
 * Filtro **ao nível do tipo**: percorre a tupla e mantém os que têm
 * `mobile: true`. É isto que transforma os "4 itens" do DESIGN.md §4 numa
 * afirmação que o `pnpm typecheck` verifica — marcar um quinto item como
 * mobile, ou desmarcar um dos quatro, deixa de compilar na atribuição abaixo.
 * Um comentário a dizer "são quatro" não teria apanhado nenhum dos dois casos.
 */
type SoMobile<T extends readonly ItemDeNavegacao[]> = T extends readonly [
  infer Cabeca,
  ...infer Resto,
]
  ? Cabeca extends ItemDeNavegacao
    ? Resto extends readonly ItemDeNavegacao[]
      ? Cabeca["mobile"] extends true
        ? readonly [Cabeca, ...SoMobile<Resto>]
        : SoMobile<Resto>
      : never
    : never
  : readonly [];

/** Quatro, nem três nem cinco — DESIGN.md §4. */
export type ItensDaTabBar = readonly [
  ItemDeNavegacao,
  ItemDeNavegacao,
  ItemDeNavegacao,
  ItemDeNavegacao,
];

function soMobile<T extends readonly ItemDeNavegacao[]>(itens: T): SoMobile<T> {
  // A asserção é inevitável — um `filter` em runtime não prova o comprimento ao
  // compilador. O que importa é que o tipo devolvido vem do `SoMobile<T>`
  // calculado sobre o array literal, e é esse tipo que a anotação abaixo
  // confronta com a tupla de quatro.
  return itens.filter((item) => item.mobile) as unknown as SoMobile<T>;
}

export const ITENS_DA_TAB_BAR: ItensDaTabBar = soMobile(ITENS_DE_NAVEGACAO);

/** O rótulo do caminho actual, para o header orientar em mobile. */
export function rotuloDoCaminho(caminho: string): string | null {
  const item = ITENS_DE_NAVEGACAO.find((candidato) => candidato.to === caminho);
  return item?.rotulo ?? null;
}
