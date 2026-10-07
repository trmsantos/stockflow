import { leituraDe, tituloDe } from "../leitura-da-validade";
import type { ValidadeProxima } from "../schemas";
import { textos } from "../textos";

/**
 * A validade mais próxima — o quarto dos quatro dados de uma linha de Stock.
 *
 * Duas regras, e a segunda é a que decide se o dono confia nos alertas:
 *
 *  1. **semáforo por texto, nunca só cor.** A palavra diz o mesmo que a tinta,
 *     para quem não distingue vermelho de verde e para quem lê por áudio. Fora
 *     do horizonte o texto fica em `muted-foreground`: um prazo folgado não é um
 *     aviso, e pintar quinze linhas de verde faria perder as três que importam.
 *
 *     **O ícone saiu a 2026-10-06**, e não por economia de pixéis. Dizia
 *     exactamente o mesmo que a palavra ao lado — um relógio antes de "expira
 *     amanhã" é a palavra outra vez, em desenho — e um ícone da Lucide por
 *     célula, em três ecrãs, é o acessório que faz uma app parecer gerada
 *     (DESIGN.md §5). A regra de não comunicar só por cor continua cumprida pela
 *     **palavra**, que é quem sempre a cumpriu: o ícone nunca foi o que a
 *     salvava, era redundância a fingir que era acessibilidade.
 *
 *  2. **`use_by` e `best_before` não se dizem com as mesmas palavras.**
 *     "Consumir até" é limite legal; "consumir de preferência antes de" é
 *     qualidade. A amêndoa laminada com a durabilidade a acabar não é para
 *     deitar fora, e se o ecrã a marcar como "expira" perde a confiança do dono
 *     na primeira vez (guião da sessão 0, §2). Por isso o `best_before` fala de
 *     **qualidade**, e o seu tecto de cor é o aviso: nunca chega a vermelho.
 *
 * O limiar de dias é o do servidor (`expiring_within_days`) e entra por
 * propriedade — não há aqui uma segunda noção de "a expirar".
 */

export function TextoDeValidade({
  validade,
  limiarEmDias,
}: {
  readonly validade: ValidadeProxima | null;
  readonly limiarEmDias: number;
}) {
  if (validade === null) {
    return <span className="text-muted-foreground">{textos.validade.semValidade}</span>;
  }

  const leitura = leituraDe(validade, limiarEmDias);

  return (
    <span className={`block min-w-0 truncate ${leitura.corDoTexto}`} title={tituloDe(validade)}>
      {leitura.texto}
    </span>
  );
}
