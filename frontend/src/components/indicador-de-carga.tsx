/**
 * O indicador de carga do produto: três traços que acendem em sequência.
 *
 * ## Porque existe, e porque não é um anel a rodar
 *
 * O dono do produto pediu "um spinner ao carregar dados". Um anel a rodar é o
 * elemento mais genérico que existe numa interface — e esta identidade tem um
 * vocabulário próprio para dizer "aqui há sinal": o trilho de 4px que marca uma
 * linha nas tabelas. Três traços a piscar são esse mesmo trilho a dizer que o
 * produto está a trabalhar, e são **os mesmos** que o ecrã de arranque do
 * `index.html` desenha antes de o React montar. Um produto com dois indicadores
 * de carga diferentes tem dois produtos lá dentro.
 *
 * ## O que ele **não** substitui, e porquê
 *
 * Os esqueletos ficam. O DESIGN.md §3 pedia "skeleton, não spinner" e a razão
 * continua verdadeira: um esqueleto com a forma do conteúdo impede o layout de
 * saltar quando os dados chegam, e um indicador não reserva espaço nenhum. O que
 * mudou é que a regra era **exclusiva** e passou a ser uma divisão de trabalho:
 *
 *  - o **esqueleto** diz *que forma vem* — tabela de sete colunas, régua de três
 *    campos — e é por isso que vive onde o conteúdo vai aparecer;
 *  - o **indicador** diz *que alguma coisa está a acontecer*, e vive onde não há
 *    forma a reservar: a barra de topo, um botão à espera da resposta, o ecrã de
 *    arranque. É a parte que faltava — uma revalidação em segundo plano não tem
 *    esqueleto nenhum e, até aqui, não tinha sinal nenhum.
 */
export function IndicadorDeCarga({
  rotulo = "A carregar",
  className = "",
}: {
  /** O que se está a carregar, para quem ouve o ecrã. */
  readonly rotulo?: string;
  readonly className?: string;
}) {
  return (
    <span role="status" aria-live="polite" className={`inline-flex items-center gap-1 ${className}`}>
      <span className="sr-only">{rotulo}</span>
      {/* `aria-hidden` nos traços: o estado é dito pelo `sr-only` acima, e três
          elementos a animar não acrescentam nada a quem ouve. */}
      {[0, 1, 2].map((indice) => (
        <span
          key={indice}
          aria-hidden="true"
          className="traco-de-carga block h-3.5 w-1 rounded-xs"
        />
      ))}
    </span>
  );
}
