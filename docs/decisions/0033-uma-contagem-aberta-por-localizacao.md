# ADR 0033 — Uma contagem aberta por localização: a ADR 0030 d2 revogada, e o fecho que não cede

**Contexto.** A ADR 0030 tem duas regras que o dono aprovou **isoladamente** e que são defensáveis
isoladamente: **uma só contagem aberta por estabelecimento** (d2 — índice único parcial
`inventory_stockcount_uma_aberta_por_tenant`, 409 `contagem_ja_aberta` com o `id` da aberta) e **abrir
e fechar são de `owner|manager`** (d1), porque fechar escreve `adjustment` irreversíveis num ledger
append-only. O **efeito combinado nunca foi aprovado**, e é este: numa padaria que conta de madrugada,
quem chega às 6h não abre contagem nenhuma, e a contagem de ontem — já contada, à espera do dono —
ocupa a **única** vaga do estabelecimento até alguém com papel a fechar. Às 7h não se conta a despensa
porque a câmara fria ainda está aberta. A aplicação diz "não" a quem está a trabalhar. O dono
confirmou a 2026-10-21 e mandou tratá-lo em fatia própria. **Toca em stock e em contagens: consultar
`domain-expert`** — as perguntas estão no fim e uma delas é maior do que esta fatia.

**Decisão 1 — A exclusividade passa a ser por localização, e a ADR 0030, decisão 2, fica revogada.** A
pergunta certa não é "quantas contagens podem estar abertas" mas **o que é que não pode acontecer duas
vezes ao mesmo tempo**, e a resposta é: **duas correcções dos mesmos factos**. O `StockLevel` tem
chave `(artigo, localização, lote)`; uma contagem materializa as linhas a partir dos níveis **de uma
localização** (0030 d4) e o fecho escreve movimentos **nessa** localização e em mais nenhuma. Dois
instantâneos de localizações diferentes não se cruzam porque não têm uma única linha de nível em
comum — o argumento da 0030 d2 é verdadeiro, mas só **dentro** da mesma localização, e foi aplicado a
um âmbito mais largo do que aquele em que é verdade. Passa a `UniqueConstraint(fields=["tenant",
"location"], condition=Q(status="open"))`, continua a ser **índice e não `filter().exists()`** pela
razão da 0030 (dois telemóveis no mesmo instante veem os dois zero abertas). O código do 409
**mantém-se** `contagem_ja_aberta` porque o cliente ramifica nele; o que muda é o significado — "já há
uma contagem aberta **nesta localização**" — e a frase passa a nomear a localização. A migração
**relaxa** o índice, e é por isso que é segura: uma aberta por estabelecimento implica no máximo uma
por localização, logo nenhuma linha existente pode violar o índice novo e não há reconciliação a
fazer. (A frase original dizia *"estreita o índice, e estreitar é sempre seguro"* — está trocada nos
dois sentidos, e a regra que ensinava é falsa: **estreitar é precisamente o que falha**, como a
migração `0008` teve de aprender ao fechar contagens antes de criar o seu índice, e como esta mesma
migração assume na reversão.)

**Decisão 2 — Abrir passa a ser de toda a gente, e é a própria ADR 0030 que o manda.** A 0030 d1
escreve a razão de abrir ser restrito e ela não é o risco da escrita: *"abrir entra do lado restrito
não por escrever muito, mas por **ocupar a única contagem aberta do estabelecimento** (d2)"*. Com a
decisão 1 a escassez acaba, e a razão acaba com ela — manter a permissão seria conservar a consequência
de uma premissa revogada. Abrir não escreve movimento nenhum (insere a contagem e as linhas), não
revela euro nenhum (o 201 já passa pelo `ve_euros`, ADR 0032) e passa a estar limitado pelo número de
localizações. **O custo está nomeado**: alguém abre a contagem errada e limpá-la custa um fecho de
`owner|manager`, porque cancelar não existe (0030, fora de âmbito) — mas uma contagem **sem nada
contado gera zero movimentos** no fecho, logo a limpeza é inerte no ledger e custa uma frase de
justificação. `GET /counts` e `POST /counts/{id}/lines` ficam como estão: de toda a gente.

**Decisão 3 — Fechar continua a ser de `owner|manager`, e a razão não é o papel: é a
pré-visualização.** O `GET /closing` **é** a decisão (diferença por linha, `loss_eur`, `gain_eur`,
`net_eur`); o `POST` é só a assinatura. Dar a assinatura a quem não pode ver a decisão não é delegar
responsabilidade, é retirá-la — e um carimbo é pior do que a espera. Somam-se duas razões concretas:
(a) fechar com linhas por contar **é permitido** (0030 d5), logo um toque escreve `adjustment`
irreversíveis (ADR 0006: `UPDATE`/`DELETE` revogados ao `stockflow_app`) **e** marca a localização como
contada no painel, sem segundo par de olhos; (b) o `reason_required_above_eur` é um oráculo de euros no
dia em que deixar de ser zero — "esta diferença vale mais de X €", repetido artigo a artigo, é uma
busca binária sobre o preço (`count_services.py`, nota do `MOTIVO_OBRIGATORIO_ACIMA_DE_EUR`). O teste
`SO_OWNER_OU_MANAGER.papeis == PAPEIS_QUE_VEEM_EUROS` (ADR 0032) é o alarme disso, e esta ADR **não
lhe toca**: a constante deixa de ser usada no `create` e fica só no `closing`, que é a rota que ela
descreve, e continua igual aos `PAPEIS_QUE_VEEM_EUROS`. O `closing_role` que a `Contagem` publica
continua a ser o rótulo certo.

**Decisão 4 — O cliente deixa de adivinhar qual é "a" contagem aberta.** A 0030 d2 usou o
`results.find(status === "open")` do cliente como argumento para a regra do servidor; era o rabo a
abanar o cão — uma suposição de ecrã a decidir uma invariante de domínio. `GET stock/counts` ganha
**um** parâmetro opcional, `?status=open|closed`, e mais nada: cada `Contagem` já traz `location: {id,
name}`, `started_at` e o progresso, que é tudo o que uma lista de "contagens a decorrer" precisa. No
ecrã, a contagem em curso passa a viver no URL — `/contar?contagem=<uuid>&zona=<slug>` —, que é o
padrão que o `/contar/fechar?contagem=` já usa e que a ADR 0008 impõe (search params validados por
Zod). O `id` que o 409 devolve passa finalmente a ter leitor: o `recusas-de-contagem.ts` já tinha
previsto o dia (*"se um dia houver mais do que uma aberta, o campo volta a ser preciso"*).

**O que fica igual, para não haver dúvida.** O `expected` continua congelado na abertura; a linha
continua a ser por artigo; a repartição da diferença por lotes (falta por FEFO, sobra no lote mais
recente) não muda; a justificação continua sempre obrigatória; fechar com linhas por contar continua a
ser possível; os euros continuam a ser de quem os vê, com a chave **ausente** para os outros (ADR 0032
d5); e não se reabre, não se cancela e não se apaga nada.

**Alternativas.** *Fechar passa a ser de quem conta, com ou sem euros* — é o outro lado da mesma
escolha e cai na decisão 3: sem a pré-visualização é um carimbo, com ela é a fuga do limiar, e nos dois
casos uma pessoa sozinha escreve no ledger o que ninguém mais vê. *Fechar só quando não há diferenças*
— tem o incentivo perverso exacto que a 0030 d5 foi combater (escreve-se o esperado para o botão
acender), e uma contagem com **zero** linhas contadas também não tem diferenças, logo deixava fechar
uma contagem que nunca se fez e dá-la por feita no painel. *Um terceiro estado, "à espera de
aprovação"* — não desbloqueia, **renomeia**: a contagem por aprovar tem de continuar exclusiva na sua
localização (senão o ajuste dela e o da contagem seguinte aplicam duas vezes a mesma correcção), logo
a mesma localização fica bloqueada no dia seguinte tal como hoje — e custa um estado, uma rota, um
ecrã e mais um sítio onde a verdade diverge. *Expirar a contagem aberta ao fim de N horas* — ou o
relógio escreve no ledger um ajuste que ninguém decidiu, ou deita fora em silêncio os 40 minutos que
alguém passou a contar de madrugada; e o relógio não distingue "esquecida" de "à espera das 10h". *Uma
aberta por estabelecimento mas aberta por toda a gente* — piora: a escassez fica e agora qualquer
pessoa a ocupa. *Uma aberta por localização e por dia, fechando a de ontem ao abrir a de hoje* — é
escrever no ledger como efeito secundário de carregar em "começar". *Nenhuma exclusividade* — é
exactamente o que não pode acontecer duas vezes. *Resolver no cliente* — o bloqueio é um 409 do
servidor; nenhum ecrã o contorna.

**Impacto.** **Zero tabelas novas, zero colunas, zero políticas RLS novas** — o `inventory_stockcount`
e o `inventory_stockcountline` já têm `tenant_id` e política, e trocar um índice não mexe no predicado.
Uma migração com duas operações: largar `inventory_stockcount_uma_aberta_por_tenant` e criar
`inventory_stockcount_uma_aberta_por_local` sobre `(tenant_id, location_id) WHERE status = 'open'`
(composto a começar no `tenant`, como os outros). **Zero tarefas Celery, zero eventos, zero outbox.**
No backend: `selectors.contagem_aberta` ganha `location_id` e nasce ao lado dela a lista das abertas do
estabelecimento; o `abrir_contagem` passa o `location_id` ao apanhar o `IntegrityError`;
`get_permissions` tira o `SO_OWNER_OU_MANAGER` do `create`; o `list` ganha o `?status=`; os docstrings
do `StockCount` e do selector deixam de dizer "por estabelecimento". No frontend: `useContagemAberta`
(singular) dá lugar às contagens abertas e à escolhida pelo `?contagem=`, o seletor de localização do
estado vazio deixa de estar atrás do `usePodeGerirContagens` (o hook fica, para o fecho), e a lista das
abertas mostra o `started_at` — "aberta desde ontem" é a frase que faz alguém ir fechá-la, e é de graça.
`uv run manage.py spectacular` e `pnpm gen:api`.

**Consequências.** A pessoa que conta às 6h abre e conta a localização que quiser, sem esperar por
ninguém; o que continua a precisar do dono é **fechar**, e a espera deixa de travar o trabalho dos
outros. Um estabelecimento passa a poder ter tantas contagens abertas quantas as localizações; o painel
não muda, porque o `last_count_at` lê contagens **fechadas**. Testes: os dois 409 da 0030 passam a ser
sobre a mesma localização, mais um que abre duas localizações ao mesmo tempo, mais um que prova que o
`staff` abre e **não** fecha. **Dívida nomeada, maior do que esta fatia**: o ajuste do fecho é
`contado − esperado_congelado` aplicado como delta contra o nível **de agora**, logo tudo o que se
mexeu entre a abertura e o fecho é contado duas vezes — já era verdade com uma contagem só, e com duas
passa a ser alcançável nas **duas pernas da mesma transferência** (sai 10 do Armazém, entra 10 na
Cozinha, e as duas contagens corrigem o mesmo movimento). A correcção é mudar o que o fecho escreve, é
território das ADR 0029/0030, e não se decide aqui.

**Fora de âmbito, por extenso.** Reabrir, cancelar ou apagar uma contagem (continua da 0030 — limpar
uma contagem aberta por engano faz-se fechando-a, e sem nada contado isso não escreve movimento
nenhum); duas contagens abertas da **mesma** localização; uma contagem sobre várias localizações;
qualquer mudança ao que o fecho escreve, incluindo a dívida do parágrafo anterior; um estado de
aprovação; expiração automática e qualquer relógio sobre contagens; avisar o dono por
`notifications` de que há uma contagem à espera de fecho (é fatia própria e é a continuação natural
desta); um quarto papel ou configurar por tenant quem fecha (a ADR 0011 proíbe o motor genérico);
zonas como entidade, contagem cega, contar por lote e offline (tudo 0030).

**Consultar `domain-expert`, antes do `backend`.** (a) Duas contagens abertas e uma **transferência**
entre as duas localizações no meio: confirmar a dupla contagem descrita nas consequências e dizer se a
correcção certa é o fecho escrever `contado − nível_no_fecho` em vez de `contado − esperado_congelado`.
(b) Contar a mesma localização duas vezes seguidas, com a primeira ainda aberta, é alguma vez legítimo
em operação real — ou é sempre a mesma observação em duplicado? (c) Uma contagem aberta há três dias
ainda é uma observação válida para gerar ajustes, ou há um prazo a partir do qual o número contado
deixa de dizer o que lá está?

---

## Adenda (2026-10-21) — o cut-off: congela-se no instante em que se **conta**, não na abertura

Esta adenda **corrige a própria ADR**. A consulta (a) do texto acima nomeou bem a dívida da dupla
contagem mas propôs a correcção errada — *"contado − nível no fecho"* —, e o `domain-expert`
respondeu **"nenhuma das três"**.

**A regra correcta é a do cut-off.** Uma contagem é uma **observação datada**: *"às 06:12, nesta
localização, havia 3,4 kg de farinha"*. O `adjustment` existe para absorver o que mexeu no stock
**sem ter sido registado** até esse instante — quebra não lançada, roubo, sobre-porcionamento, erro
de receção. Logo a base de comparação é o que os livros diziam **no momento em que se contou**: nem
na abertura, nem agora.

```
ajuste = contado − Σ(movimentos da localização com occurred_at ≤ counted_at)
nível_final = nível_agora + ajuste = contado + tudo o que se moveu depois de counted_at
```

Movimentos registados **depois** da observação são factos documentados — uma transferência tem duas
pernas, uma receção tem fatura. Uma contagem descobre o que não foi registado; **não tem autoridade
para des-registar o que foi**. É esse o critério que separa as alternativas.

**A base recalcula-se no fecho, a partir do ledger e por `occurred_at`** — não se lê de um número
gravado na abertura nem no `POST`. É o caso [E] abaixo que o exige.

### O modo de falhar que ninguém vê, e que é a razão desta adenda

O defeito conhecido produz um **número errado** (esperado 100, transferência de −10 às 7h, conta-se
90 às 8h → escreve-se −10 sobre 90 → 80, quando o ajuste certo era 0). Alguém pode estranhar.

O inverso é pior: esperado 100, transferência de −10 registada às 7h, conta-se às 8h e vê-se **100**
— ou seja, há uma **sobra real de +10** face aos livros. O cálculo de hoje dá `100 − 100 = 0`. A
contagem fecha *"tudo certo"*, não escreve movimento nenhum, e **ninguém investiga — porque uma
variância zero nunca é investigada**. Um movimento registado mascara uma discrepância real do mesmo
tamanho. **Isto produz silêncio, e silêncio não se audita.**

E esta ADR, ao permitir duas localizações em simultâneo, não cria um erro novo: cria a **versão
silenciosa do antigo**. Na transferência da arca para a despensa, hoje escreve-se −10 de um lado e
+10 do outro — o total do estabelecimento continua certo, **nenhum relatório agregado o apanha**, e
só quem olhar localização a localização o vê. Com uma contagem só, o mesmo erro aparecia como
variação do total. Com o cut-off, as duas dão ajuste **zero** e a decisão 1 aguenta-se de pé.

### Porque é que as outras três caem

- **Congelar na abertura** (hoje) só acerta quando nada mexeu entre abrir e contar, ou seja **por
  acidente**; e o erro cresce com o atraso.
- **Recalcular contra o nível actual no fecho** é pior, não melhor: afirma *"agora há C"*, que
  **ninguém observou**, e aniquila nos níveis a mercadoria recebida às 7h e o pão produzido às 9h —
  os movimentos ficam no ledger e os níveis deixam de os reflectir, que é a divergência entre as duas
  verdades que este domínio existe para evitar. É a única opção cujo resultado **depende do relógio
  no instante em que alguém carrega no botão**: fechar às 10h00 e às 10h05 escreve ajustes diferentes
  a partir da mesma contagem, o que quebra a promessa da ADR 0030 d5 de que o `GET /closing` **é** a
  decisão e o `POST` é só a assinatura. E com dois fechos em momentos diferentes chega a **fazer
  desaparecer unidades** do estabelecimento.
- **Recusar fechar se houve movimento** é insatisfazível numa cozinha, proíbe o que é legítimo
  (movimento *depois* da contagem é compatível com um ajuste correcto) e cria o incentivo de **deixar
  de registar movimentos para o botão acender** — estraga o ledger muito mais do que qualquer
  variância. É a mesma família do `can_close` que a ADR 0030 d5 já tinha matado.

### O que isto muda, em concreto

- **`quantity_expected` deixa de ser congelado na abertura.** Passa a ser escrito junto com
  `quantity_counted` e `counted_at`, como **tripla atómica** — os três movem-se juntos ou não se
  movem. O valor materializado na abertura continua a existir como **adorno de ecrã** (o esperado que
  o contador vê), nunca como base de cálculo. Numa **recontagem** (upsert), reescrever o `counted_at`
  obriga a reescrever o esperado com ele: o comentário do `registar_linha_contagem` que hoje diz
  *"congelado uma vez"* é precisamente o que cai. O código já faz o certo no caminho da linha que não
  existia e o errado no caminho da linha materializada na abertura — a correcção é **uniformizar os
  dois**, não inventar mecanismo novo.
- **`counted_at` passa a ser carga aritmética e não rasto de auditoria.** Logo **nunca se aceita do
  cliente** — seria uma alavanca para mover a base do ajuste, e um oráculo no dia em que o
  `reason_required_above_eur` saia do zero. É `timezone.now()` do servidor, e é invariante que
  `quantity_counted IS NOT NULL ⇒ counted_at IS NOT NULL`.
- **O cut-off é por `occurred_at`**, nunca por `created_at` nem por ordem de inserção.
- **A atribuição por lote continua a correr contra a composição de hoje.** A quantidade é *as-of*, a
  atribuição não: o delta tem de aterrar em linhas de nível que existam. Se o lote FEFO foi todo
  consumido entre contar e fechar, a falta cai num lote que a pessoa nunca viu — aceitável, porque a
  repartição já é heurística assumida (ADR 0030), mas **não se finge que é exacta** e não se constrói
  um segundo motor *as-of* para lotes nesta fatia.
- **Contagem parcial fica mais coerente, não menos:** sem `counted_at` não há cut-off, logo não há
  base, logo não há afirmação. O *"ausência de observação não é zero"* da ADR 0030 passa a ser
  **consequência da aritmética** e não só política.

### Decisões do dono (2026-10-21)

1. **O `occurred_at` do ajuste é a hora do fecho.** O ajuste é uma decisão, e o instante da
   observação já vive no `counted_at` de cada linha — não se perde nada. É também o que o código já
   faz.
2. **Uma contagem sem nenhuma linha contada não carimba `last_count_at`.** Sem isto o painel
   **mente**: esta ADR tornou o fecho a forma de limpar uma contagem aberta por engano, logo passaria
   a dizer que a arca foi contada hoje sem ninguém lá ter ido — e é exactamente o número que serve
   para saber o que falta contar. Corrige a contradição entre esta ADR e a ADR 0030.
3. **O resíduo da fatura atrasada documenta-se agora; o detector é fatia própria.**

### O resíduo que fica, por extenso

A mercadoria chega às 7h e vai para a prateleira; a fatura é fotografada e revista por uma pessoa às
11h, com `occurred_at` = data de entrega. Quem contou às 8h **viu a mercadoria** e contou-a. Se a
fatura já estiver lançada no momento do fecho, o cut-off acerta. Se entrar **depois do fecho** com
`occurred_at` anterior ao `counted_at`, produz uma **dupla contagem permanente e silenciosa**, e não
há solução dentro desta fatia. Mitigação operacional: **receber antes de contar**. O detector —
assinalar um documento que entra com data anterior a uma contagem já fechada naquela localização — é
barato de construir e o erro é caro de corrigir à mão, e fica como fatia própria.
