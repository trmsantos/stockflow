import { z } from "zod";

/**
 * Os filtros do ecrã Alertas, no URL e validados.
 *
 * O `ver` é o que resolve o maior risco do DESIGN.md: **três perguntas numa
 * tab**. Não há três separadores nem três ecrãs — há três contadores no topo, e
 * cada um põe aqui o seu valor, logo a lista de baixo é sempre a mesma lista
 * vista de três maneiras. Ausente é o default e mostra o risco todo (validades
 * **e** faltas juntas), porque de manhã a pergunta é "o que é que me vai doer
 * hoje?" e não "quero ver a categoria X".
 *
 * **Não há `horizonte` nem `limiar`.** O limiar de dias é do servidor e aparece
 * dentro de cada alerta ("expira em 2 dias — aviso a 3"); um campo no URL para
 * o mudar era o painel de configurações que o guião §4 nº 7 proíbe, e com ele
 * perdia-se a informação de qual devia ser o valor por omissão.
 *
 * O `periodo` só diz respeito à vista do desperdício, e existe porque as duas
 * fronteiras são a pergunta da Q6: "hoje" começa à hora a que o **dia de
 * negócio** começa (04:00 numa pastelaria, não à meia-noite) e "semana" são os
 * últimos sete. Qual delas ele escolhe primeiro é, também, resposta.
 */
export const buscaDeAlertasSchema = z.object({
  ver: z.enum(["expira", "falta", "desperdicio"]).optional().catch(undefined),
  periodo: z.enum(["hoje", "semana"]).optional().catch(undefined),
});

export type BuscaDeAlertas = z.output<typeof buscaDeAlertasSchema>;
