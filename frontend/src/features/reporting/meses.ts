/**
 * Os dois meses de que o painel precisa quando o URL não os traz.
 *
 * ## Porque é que o fecho abre no **mês anterior** e não neste
 *
 * É uma decisão de produto e está aqui com a razão, porque a ADR 0013 fixa o
 * parâmetro `month` e deixa o default ao ecrã. Medido no fixture: um mês a
 * correr ao dia 6 tem o pessoal e os custos fixos do mês **inteiro** contra as
 * vendas de seis dias, logo o rácio de pessoal dá 117% e o resultado dá −4 200 €.
 * Nenhum dos dois está errado, e nenhum dos dois é a pergunta "como fechou o
 * mês". Abrir o painel num falso prejuízo é a mesma bomba de confiança que a
 * decisão 7 nomeia, com o sinal ao contrário — e o painel seria lido assim
 * todos os meses, do dia 1 ao dia 20.
 *
 * O mês corrente continua a um toque na navegação do bloco, e **o que está a
 * acontecer agora é o bloco de período**, que é o grão que serve para isso.
 *
 * ## A fronteira das 04:00 e o que isto não resolve
 *
 * O mês de negócio vai de `[dia 1 às 04:00, dia 1 do mês seguinte às 04:00)`
 * (ADR 0013, decisão 8), e este cálculo é sobre o dia **civil**: entre a
 * meia-noite e as 04:00 do dia 1 de um mês, o servidor ainda está no mês
 * anterior e este default já avançou. O efeito é de quatro horas por mês e é
 * visível, não silencioso: o bloco mostra o mês que o servidor resolveu, com
 * `closed: false` e `days_elapsed` igual ao número de dias dele — está lá
 * escrito que o mês não fechou. Resolvê-lo exigia a hora de início do dia de
 * negócio **antes** do primeiro pedido, e ela vem dentro das respostas.
 */

function paraIso(data: Date): string {
  return `${String(data.getFullYear())}-${String(data.getMonth() + 1).padStart(2, "0")}`;
}

/** `"2026-10"` — o mês em que hoje está. É o limite da navegação. */
export function mesCorrente(): string {
  return paraIso(new Date());
}

/** `"2026-09"` — o último mês que já fechou. É onde o bloco de fecho abre. */
export function mesDeFechoPorOmissao(): string {
  const agora = new Date();
  return paraIso(new Date(agora.getFullYear(), agora.getMonth() - 1, 1, 12));
}
