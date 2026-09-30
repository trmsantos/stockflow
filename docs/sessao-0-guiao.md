# Guião da sessão 0 — o shell como instrumento

Este ficheiro tem dois leitores. O **agente `frontend`** encontra aqui o que os quatro ecrãs
mostram, com que dados e o que está proibido. Quem **conduz a conversa** encontra aqui, pergunta a
pergunta, o que o ecrã responde sozinho e o que tem de ser perguntado.

Fonte: consulta ao `domain-expert` (2026-09-30). As onze perguntas abertas estão no
`SESSION-CONTEXT.md`, parágrafo "Sessão 0". Nada aqui é decisão de domínio — é o desenho da
**pergunta**. Onde a resposta é desconhecida, o shell mostra as duas variantes; não escolhe.

---

## 0. O orçamento de ecrã, que é o que trava a tentação

360×640, header 48px, tab bar 56px → **~530px úteis**. São **3 números de topo + 7 linhas de 56px**,
ou 9 linhas sem header. Acrescentar um campo obriga a tirar outro. O público usa isto em telemóvel,
em pé, com pressa.

---

## 1. Os quatro ecrãs

### Stock — "o que é que eu tenho, e quanto?"
- **Topo, 3 números tocáveis:** artigos em falta · a expirar ≤3 dias · valor de stock em €.
- **Linha, 4 dados e nunca mais:** nome curto (como o staff lhe chama, não a descrição da fatura) ·
  quantidade + unidade (`data-numeric`, mono, à direita) · badge de estado (ok / baixo / esgotado) ·
  validade mais próxima ("V. 02/10" ou "2 dias").
- **Ordem:** o que está pior primeiro. **Nunca alfabética.**
- **Acção principal:** campo *sticky* de procurar/scan no topo. É a acção menos certa das quatro — o
  Stock pode ser legitimamente um ecrã de leitura. O sinal que interessa é **o que ele tenta tocar**:
  se toca no número da quantidade, aprendeste que espera editá-lo, e é a conversa mais importante do
  dia.

### Receber — "o que chegou, e está certo?"
- **Topo:** 1 receção a precisar de revisão · 3 confirmadas hoje.
- **Linha:** fornecedor · nº do documento + data · tipo (FT / FR / FS / NC / guia) · total € ·
  badge "precisa de revisão (2 linhas)".
- **Dentro de uma receção** (o ecrã que interessa), por linha de fatura: descrição da fatura →
  artigo do catálogo · quantidade na unidade de compra → quantidade na unidade de stock **com a
  conversão à vista** ("1 caixa 12×1 L → 12 000 ml") · lote + validade, por preencher · preço
  unitário e taxa de IVA **como vêm na linha**.
- **Acção principal:** fotografar a fatura, câmara a um toque. Segunda: confirmar linha.

### Contar — "o que está na prateleira é o que o sistema diz?"
- **Topo:** progresso ("12 de 34") + zona actual ("Arca 1").
- **Linha:** nome · campo numérico grande com teclado já aberto · unidade em que ele conta · e o
  esperado do sistema **visível numa zona e escondido noutra** (ver §3, contagem cega).
- **Ordem: por localização física** (Balcão → Frigorífico → Arca → Armazém). É regra, não
  preferência.
- **Acção principal:** escrever o número e avançar; scan salta para o artigo. Ao fechar: diferenças
  em quantidade **e em €**, com motivo obrigatório acima de um limiar.

### Alertas — "o que expira? o que falta? quanto deitei fora?"
Três perguntas numa tab é o maior risco do `DESIGN.md`. Resolve-se com três contadores e **uma** lista.
- **Topo:** expira ≤3 dias · em falta · deitado fora esta semana (€).
- **Linha:** nome · lote e validade ("L. 240928 · amanhã") · quantidade em risco · valor € ·
  **distinção entre "consumir até" e "consumir de preferência antes de"**. Sem isto o dono perde a
  confiança nos alertas na primeira amêndoa laminada marcada a vermelho.
- **Acção principal, um toque na linha: "Deitei fora"** → segundo toque escolhe o motivo (expirado /
  estragado / quebra / perda de preparação). É esta acção que alimenta o número que o dono mais quer.

---

## 2. Os dados — Pastelaria Aurora (fictícia)

**Nome fictício, obrigatoriamente.** Com o nome da pastelaria dele, o dono trata os dados como sendo
seus e passa a caçar erros em vez de reagir ao fluxo.

Duas lojas + produção: **Loja Centro**, **Loja Mercado**, **Cozinha** (esta só para participantes com
produção separada). Volume implícito ~300 pastéis/dia. **Validades relativas a hoje, nunca datas
congeladas** — um "expirou há 3 meses" mata a credibilidade no primeiro ecrã.

Artigos que têm de existir, cada um por uma razão:

| Artigo | Compra → base | Consumo | Porque está aqui |
|---|---|---|---|
| Farinha T65 | saco 25 kg → 25 000 g | g | compra ao saco, consumo ao g; DDM não é "deitar fora" |
| Açúcar branco | saco 25 kg **e** pacote 1 kg | g | duas embalagens para o mesmo artigo |
| Ovo líquido pasteurizado | emb. 1 kg, caixa de 6 | g | **3 dias após abertura** |
| Ovos frescos classe M | plateau de 30 un | un e g | caixa de N + o mesmo ingrediente em duas formas |
| Manteiga sem sal 82% | bloco 2,5 kg → 2 500 g | g | bloco → g |
| **Nata 35% 1 L** | caixa 12×1 L | ml | **0 L com quebra de 2 L registada — a sonda da Q1** |
| Leite UHT 1 L | caixa 12×1 L | ml (galão 250 ml) | dose pequena de embalagem grande |
| Café em grão | lote 1 kg | 7 g/café | dose; máquina em comodato |
| Massa folhada em rolo | caixa 5 rolos 2 kg | g | congelado + **lote filho após descongelação** |
| Chocolate cobertura 54% | saco 5 kg | g | IVA 23% ao lado de artigos a 6% |
| Amêndoa laminada | saco 1 kg | g | **DDM próximo: alerta amarelo que NÃO é para deitar fora** |
| Morango | caixa 2 kg (8×250 g) | g limpo | validade 2 dias + **yield 80%** + fatura manuscrita |
| Fermento fresco | bloco 500 g | g | bloco meio usado: "0,5 un" ou "250 g"? |
| **Queijo flamengo em bola** | **ao kg**, bola ~3,5 kg | ~25 g/tosta | **peso variável na fatura** + casca + 7 d aberto |
| Fiambre da perna | **ao kg**, peça ~4 kg | g | **3 d depois de fatiado** + rastreabilidade |
| Rissóis congelados | caixa 100 un | un | caixa de N + congelado |
| Óleo de fritar | garrafão 5 L | ml | consumo que ninguém mede: gere-se por reposição |
| **Água 0,33 L vidro** | grade 24 un, **tara retornável** | un | **vasilhame: linha de fatura que não é stock** |
| Caixa de cartão p/ bolo | pacote 50 un | un | **não alimentar, e é o que mais falta** |
| **Saqueta de açúcar 8 g** | caixa 1 000 un | un | **o artigo que ninguém vai contar** |
| Bacalhau ultracongelado | caixa 5 kg | g | origem animal → lote obrigatório por lei |
| **Pastel de nata** (próprio) | — | un | 46 un ao fecho, validade **mesmo dia** → sonda da Q6 |

Eventos que têm de estar nos dados — é neles que vive o §3:
- **receção parcial** (5 rolos encomendados, vieram 3);
- **guia de remessa sem fatura** (lácteos, guia 4471, fatura a fim de mês);
- **nota de crédito** por 2 grades vazias devolvidas;
- **fatura simplificada do Makro emitida ao NIF pessoal do sócio** (Q10);
- **transferência em trânsito** Cozinha → Loja Centro, 40 pastéis, ainda "em trânsito" (Q4);
- **preço 21% acima do histórico** (manteiga a €9,40/kg contra €7,80);
- **artigo novo na fatura** que não existe no catálogo.

### Onde a prática portuguesa muda a resposta
1. **Cash & carry sem encomenda.** O dono vai ao Makro de manhã e traz na carrinha, com **fatura
   simplificada**: sem guia, sem encomenda. O fluxo Receber **não pode assentar numa encomenda
   obrigatória** — a receção sem documento prévio é o caso normal.
2. **Guia de remessa + fatura a fim de mês.** A mercadoria entra **antes de existir fatura**, e a
   fatura depois reconcilia N entregas. Estrutural, não cosmético.
3. **IVA por linha, lido da linha.** Nunca inferir a taxa a partir do artigo: muda entre Continente e
   Regiões Autónomas. A taxa é dado da fatura; o artigo não a "tem".
4. **ATCUD + QR** em toda a fatura desde 2023. Se o QR é legível, é melhor fonte do que OCR do corpo.
5. **Tara/vasilhame retornável** aparece como linha com valor e não é consumível.
6. **HACCP.** Origem animal exige registo de lote; a ASAE pede registos de receção, incluindo
   **temperatura à entrega**. Um campo "temperatura (°C)" na receção de congelados é o probe mais
   barato do shell — e pode revelar que o verdadeiro gancho é substituir as folhas de papel.
7. **"Consumir até" (limite legal) vs "consumir de preferência antes de" (qualidade).** Tratar as
   duas igual perde a credibilidade dos alertas de imediato.
8. **O contabilista já tem as compras** pelo e-Fatura. O valor da extração é **stock e custo**, não
   contabilidade — dizer isto na abertura evita ser comparado com algo que ele já tem de graça.

---

## 3. As onze perguntas: o que o ecrã responde e o que tem de ser conversa

**SHELL** (6): desenha-se a ambiguidade para dentro e observa-se · **MISTO** (2) · **CONVERSA** (3).

| # | Pergunta | | Como |
|---|---|---|---|
| 1 | Bloquear ou avisar sem stock | **SHELL** | Nata a 0 L. O shell **deixa** registar a quebra de 2 L e mostra `−2,0 L` em vermelho com aviso suave. Não perguntes nada: ou ele passa ao lado (→ avisar), ou pára (→ bloquear). Só então: *"e se fosse a Ana às 8h, com o cliente à frente?"* |
| 2 | Várias lojas: um NIF ou vários | MISTO | O ecrã responde à parte operacional: seletor de loja no header e stock repartido ("3,4 kg — Centro 2,0 · Mercado 1,4"). A parte jurídica é conversa. |
| 3 | Consumo por talão ou em lote | **SHELL** | Duas variantes lado a lado: pastel com 14 linhas "Venda 11:02 — 6 un"; café com uma linha "Vendas de 29/09 — 312 un (fecho de caixa)". Pergunta: *"em qual destes notavas que faltava alguma coisa?"* Atalho técnico a perguntar: **"se eu pedisse o SAF-T do mês, isso chegava?"** — dispensa integração de POS no v1. |
| 4 | Cozinha central e trânsito | **SHELL** (condicional) | Uma linha: "08:40 · Cozinha → Loja Centro · 40 un · **em trânsito**", e no Stock da loja esses 40 ainda não aparecem. Só mostrar a quem tem produção separada. |
| 5 | `yield_factor` | **SHELL** | Ninguém responde a "qual é o teu fator de rendimento". Cartão de ficha técnica **só de leitura**: "morango: 1,20 kg limpo ← 1,50 kg comprado (80%)". Pergunta: *"como fazes esta conta hoje?"* Se a resposta é "não faço", é resposta: default 1.0 com override, nunca obrigatório. |
| 6 | Hora a que começa o dia | **SHELL** | Rótulo "Deitado fora — hoje (desde as 04:00)" e na lista "05:10 — Pastéis de ontem, 12 un, € 14,40". Na pastelaria a fronteira é o **início da produção** (~4h), não o fim do serviço (~2h) do restaurante — e isso pode significar que a resposta é diferente por tipo de negócio. |
| 7 | Conjunto de papéis | MISTO | **Autor em toda a linha de movimento**: "Ajuste −2,0 kg · Ana (balcão) · quebra", e uma acção visivelmente restrita ("Fechar contagem — só o responsável"). Depois: *"a Ana podia ter feito isto? e apagar?"* |
| 8 | ENI → Lda e histórico | CONVERSA | Probe incidental grátis: uma fatura antiga ao nome antigo ao lado de uma recente ao nome novo. Não contar com isso. |
| 9 | Contabilista | CONVERSA | Probe: acção discreta "Enviar para a contabilidade". A pergunta a fazer é factual: *"como é que as faturas chegam hoje à tua contabilista?"* **Não** desenhar um seletor de tenant para ela. |
| 10 | Faturas ao NIF pessoal | **SHELL** | Badge discreto: "Makro · FS 2026/114 570 · **NIF diferente do da empresa**". Ninguém oferece isto em abstracto; um badge extrai-o em dois segundos. |
| 11 | Grupos com N sociedades | CONVERSA | Segmentação de mercado, não uso de produto. |

**Três perguntas que o shell responde de graça, e vale a pena ir buscar:**
- **Até onde ele quer controlar.** As saquetas de açúcar e o leite ao ml: se ele vê e diz "isto não
  vale a pena", definiste o âmbito do catálogo v1 sem o discutir.
- **Contagem cega ou não.** Uma zona com o esperado visível, outra sem. A boa prática é cega (evita
  ancoragem); a intuição do dono costuma ser o contrário. Hipótese marcada como tal: **esperado
  visível**, porque a desconfiança de "o sistema está errado" pesa mais do que o risco de ancoragem.
- **O que ele procura e não encontra.** As quatro tabs não têm Receitas, Encomendas, Fornecedores nem
  Relatórios. Anota o que ele tenta encontrar e em que ecrã o procurou: é o sinal mais barato da
  sessão inteira.

---

## 4. Proibido no shell

**Porque ensina o modelo errado e mata o ledger:**
1. **Campo de quantidade editável no Stock.** Um stepper ao lado do "3,4 kg" e perdeste a conversa:
   ele passa a sessão a editar números e pede esse lápis para sempre.
2. **Botão de editar ou apagar movimento.** Append-only; corrige-se com movimento inverso.
3. **Bloqueio duro em qualquer sítio** — nem stock negativo, nem fechar contagem com diferenças, nem
   confirmar fatura com totais a não bater. Bloquear **é** a Q1; o shell não responde por ele.

**Porque pré-decide uma das onze:**
4. Ecrã completo de receitas/fichas técnicas (pré-decide a Q5). Só o cartão de leitura.
5. Integração de POS "ligada", com logótipos reais (pré-decide a Q3 e promete o que não existe).
6. Seletor de tenant ou vista de contabilista (pré-decide a Q9 e a Q11).
7. Ecrã de configurações com limiares. Mostra o limiar **dentro** do alerta ("expira em 2 dias —
   aviso a 3") para ele o contestar; não lhe dês um painel, que é o que te faz perder o default.
8. Importação de catálogo por Excel. Come a sessão inteira antes de ele ver o produto.

**Porque desvia a conversa:**
9. Números em € com precisão falsa (CMP, margem, valor ao cêntimo). Usa € onde é o ponto —
   desperdício e valor em risco — arredonda, e diz na abertura que são dados de demonstração.
10. Qualquer vocabulário de IA na UI. "Precisa de revisão", nunca "87% de confiança": ele vai
    discutir a percentagem em vez do fluxo.
11. Preços de venda e margem. Abre menu engineering.
12. O nome real da pastelaria dele nos dados.
13. Datas absolutas congeladas.
14. Toggle de dark mode, gráficos decorativos, avatares, multi-idioma.

---

## 5. Hipóteses assumidas — nenhuma para migrar

Marcadas como hipótese e não como decisão. Nenhuma entra numa migração antes da sessão 0.

- stock negativo é permitido **com aviso**, não bloqueado;
- o dia de negócio começa às **05:00** na pastelaria (início da produção), configurável por tenant;
- `yield_factor` default 1.0, override por linha de receita, nunca obrigatório;
- contagem com quantidade esperada **visível**;
- um bloco de fermento meio usado conta-se em **g** (unidade base = g), não em "0,5 un";
- tara/vasilhame é linha de fatura reconhecida e **excluída** do stock consumível.

**Não é hipótese, é regra:** a receção existe **sem encomenda e sem fatura**. Se o modelo de dados
exigir uma `PurchaseOrder`, está errado para o mercado português.
