# ADR 0021 — Receção de mercadoria: as tabelas, as três fronteiras, e a ordem das fatias

**Contexto.** As seis apps de domínio são conchas — `__init__.py` + `apps.py`, zero models, zero
migrações — e os ecrãs de operação existem todos, escritos na forma final (ADR 0008, decisão 3) sobre
o `frontend/fixtures/`. O passo autorizado é dar-lhes tabelas e endpoints, a começar pelo que
desbloqueia a entrada de mercadoria por documento do fornecedor. A ADR 0020 decidiu o **upload** e a
ponte para o telemóvel e disse, duas vezes, que não desenha as colunas: *"esta ADR não desenha as
colunas do `InvoiceDocument` — isso é da ADR da receção por fatura, que também lhe deve o
`PurchaseReceiptDraft`"*. Esta é essa ADR.

E tem uma vantagem que nenhuma das anteriores teve: **o contrato já existe.** O
`frontend/src/features/{purchasing,inventory}/schemas.ts` e o `frontend/fixtures/rececoes.ts` fixam
caminhos, envelope de paginação, nomes de campos, nulabilidade e enums, estão validados pelo
`domain-expert` e são o rascunho que esta sessão recebe (ADR 0008, decisão 3). Logo o trabalho não é
inventar um contrato: é **satisfazê-lo, ou nomear o desvio e justificar o preço**. Cada desvio custa
uma alteração no frontend, e isso é um preço a justificar e não a assumir.

**Decisão 1 — A fronteira dos três módulos, numa frase-teste.** `catalog` é **o que um artigo é**
(nome, unidade base, embalagens, se exige lote, quem o vende); `purchasing` é **o que o documento
diz** (o ficheiro, o que o modelo leu, o que a pessoa confirmou); `inventory` é **o que há e como
mudou** (localizações, lotes, movimentos, projeções). A frase que decide um campo em dúvida: *se o
valor muda quando chega outra fatura, é do `purchasing`; se é verdade sobre o artigo
independentemente de quem o vendeu, é do `catalog`; se só existe porque alguma coisa se moveu, é do
`inventory`.* Três consequências imediatas, as três contra o instinto: a **taxa de IVA** é da linha
do documento e nunca do artigo (o contrato afirma-o e a razão é as Regiões Autónomas); o **custo
unitário** é do movimento e nunca do artigo (ADR 0014 — reavaliar o passado é falsificar um número já
impresso); e a **validade** é do lote, que é do `inventory`, enquanto o *rótulo* da validade
(`use_by`/`best_before`) é do artigo, que é do `catalog`.

**Decisão 2 — O contrato existente manda. Os desvios são oito, e sete não custam uma linha de
frontend.** Vale listá-los um a um, porque a alternativa é descobri-los na sessão do backend.

1. **`document_total` deixa de ser fabricado.** A fixture serve `totalImpresso ?? soma_das_linhas`; o
   endpoint serve `null` quando o documento não imprimiu total. O tipo não muda
   (`decimal.nullable()`), e a razão é que um total impresso que é cópia da soma **nunca pode
   divergir dela** — o que desarma exactamente a verificação para que o campo existe, e que o
   rascunho da fixture demonstra (204,40 € contra 201,90 €).
2. **A página das linhas é 200 e não 50.** Medido: não há um único uso de `next` em `src/`, logo o
   ecrã de revisão mostra `results` e mais nada. Um rolo de cash & carry passa das 50 linhas, e uma
   linha que não aparece é uma entrada de stock que não acontece — é o único ecrã onde truncar em
   silêncio tem esse efeito. A lista de receções fica nos 50, como o `api.ts` já diz. O dia em que um
   documento passar das 200, a correcção honesta é o cliente seguir o `next` e não subir o número.
3. **`company_nif` sai como string vazia** até existir a sessão do NIF do tenant (`nif_encrypted` +
   `nif_hmac` com pepper, SECURITY.md §3 — dívida nomeada). O contrato permite-o de propósito:
   `z.string()` sem `min(1)`. O badge da Q10 ("esta fatura foi emitida ao NIF pessoal do sócio") só
   acende quando o NIF do estabelecimento existir, e isso é uma **dependência** desta feature a outra
   sessão, não um desvio.
4. **Não é criado `GET /receipts/<id>`.** O cliente selecciona da entrada de cache da lista, de
   propósito e com a razão escrita no `api.ts`. O alvo do polling da decisão 3 da ADR 0020 é o `GET`
   do **documento**, que é recurso novo.
5. **A confirmação devolve 201 na primeira vez e 200 na repetição**, como a fixture. Não é
   cosmética: é a idempotência observável de um duplo toque num telemóvel, e trocá-la por 409 fazia
   uma rede fraca parecer um erro.
6. **O parâmetro `estado=revisao|hoje` fica em português** num payload inteiramente em inglês. É
   herdado, muda-lo custa uma alteração no frontend e não compra nada. Quem escrever a view não deve
   escrever `status=`.
7. **Uma nota de crédito gera `return` e não `receipt`** (skill `inventory-domain` §7), e o documento
   que ela anula **não tem campo no contrato**. No v1 a NC gera `return` sobre as linhas que a pessoa
   reviu, sem referência ao original; a ligação é uma coluna aditiva da fatia da reconciliação. O
   payload não muda.
8. **O único desvio que custa frontend:** o `revisaoDeLinhaSchema` ganha campos na fatia 2
   (`product`, `packaging`, `base_per_invoice_unit`, `location`, `kind`, `quantity_received`). Não é
   uma surpresa — o próprio ficheiro o prevê por extenso: *"Não há `product`, e a ausência é uma
   decisão por tomar e não um esquecimento… o campo entra quando houver resposta sobre o catálogo"*.
   É a alteração que a resposta do dono autoriza, e não uma que esta ADR imponha.

**Decisão 3 — A linha tem duas zonas, e a revisão só escreve numa.** É a resposta estrutural a *como
é que o que o modelo devolveu se distingue do que a pessoa confirmou*, e vive na forma da tabela e
não numa convenção de serviço. A **zona do documento** é escrita uma vez (pela extração, ou pela
pessoa numa receção à mão) e a revisão nunca lhe toca: `description` como vem impressa,
`invoice_unit`, `quantity_invoiced`, `unit_price`, `vat_rate`, `extraction_confidence`. A **zona da
pessoa** é tudo o que a revisão escreve: `product_id`, `packaging_id`, `base_per_invoice_unit`,
`quantity_received`, `location_id`, `kind`, `lot_code`, `expires_at`, `status`, `reviewed_by`,
`movement_id`. O contrato já separa o par que mais importa — `quantity_invoiced` contra
`quantity_received` —, e é por isso que a receção parcial (cinco rolos faturados, três entregues) se
representa sem encomenda nenhuma. É afirmável por teste: *o serviço de revisão não escreve nenhuma
coluna da zona do documento*.

**Decisão 4 — `agents_extraction` guarda o que o modelo devolveu, verbatim, em JSON, e nunca é lido
para ramificar.** Uma linha por **chamada** ao modelo, com `payload` (JSONField) a conter a resposta
tal como veio. O `JSONField` que a ADR 0011 proíbe é o de **configuração** — valores em que o produto
ramifica, invisíveis ao `schema.yml` e ao gate de diff do `types.ts`. Aqui é o oposto: é **prova**,
texto não confiável guardado para se poder voltar a ele, nunca comparado num `if`, nunca interpolado
em SQL, nunca renderizado sem escape (CLAUDE.md, SECURITY.md §6). O que o produto lê são as colunas
tipadas da linha de receção, que são a verdade da pessoa. A tarefa valida o payload contra o schema
Pydantic **à escrita** e marca `status=ilegivel` quando falha; o serializer de saída volta a
validá-lo à leitura, porque é a única coluna do sistema em que nada se confia. E a tabela não é
append-only: `started_at`/`finished_at`/`cost_eur` são `UPDATE`s da mesma chamada.

**Decisão 5 — Chave estrangeira entre módulos só para entidades de referência; para acontecimentos,
um `UUIDField`.** Uma FK declarada por string não gera import (é o que o `TenantModel` já faz com
`accounts.Tenant`) e compra integridade referencial de graça, e a direcção `purchasing → catalog`,
`inventory → catalog` é a que o import-linter já permite. Logo `product_id`, `packaging_id`,
`supplier_id` e `location_id` são FK por string, `related_name="+"`, e **`on_delete=RESTRICT` e não
`PROTECT`** — o `RESTRICT` recusa apagar um artigo com histórico e **permite** que o apagamento do
tenant o leve na mesma cascata, que é o que o `PROTECT` rebentaria. Duas referências não são FK:

- **`purchasing_receiptline.movement_id`** — a tabela do movimento tem `UPDATE`/`DELETE` revogados
  (ADR 0006) e a relação ORM convidaria a escrever `line.movement.quantity`, que é `purchasing` a ler
  os models do `inventory` — a coisa exacta que o `api.py` existe para impedir. O contrato já o trata
  como um uuid opaco (`movement: z.uuid().nullable()`);
- **`agents_extraction.document_id`** — a secção 7 do `ARCHITECTURE.md` nomeia o `agents` como o
  candidato óbvio a sair para serviço próprio e promete que *"a extração é mecânica"*. Uma FK para a
  tabela do `purchasing` quebra essa promessa ao nível do esquema, e uma promessa que só se descobre
  falsa no dia da extração não vale nada.

O que a FK compra é a integridade e o id; **o nome vem pelo `api.py`** — a lista de receções lê os
nomes curtos por uma chamada em lote a `catalog.api`, e não por `select_related`. É também o que torna
a travessia desnecessária: se o nome já vem no DTO, ninguém escreve `line.product.short_name`.

**Decisão 6 — O tipo do movimento vem do tipo do documento, nunca da linha.** `NC` → `return`, tudo o
resto → `receipt`. Um tipo por linha deixaria a mesma fatura a produzir entradas e devoluções, e o
sinal do dinheiro no painel passava a depender de uma escolha de ecrã (ADR 0014, tabela de nove
linhas: `return` reduz compras e **não** é consumo). Linhas de `deposit` (vasilhame) e `charge`
(portes, descontos) **não geram movimento nenhum** e não impedem a confirmação do documento — é o que
a nota de crédito das duas grades vazias, que está no seed por esta razão, demonstra.

**Decisão 7 — As tabelas.** Todas herdam `TenantModel` (`id` uuid, `tenant_id`, `created_at`,
`updated_at`), logo **todas** levam `ENABLE` + `FORCE` + política com
`NULLIF(current_setting('app.tenant_id', true), '')::uuid` na migração que as cria. Quantidades
`Decimal(12,3)`, custos `Decimal(12,4)`, dinheiro `Decimal(12,2)`, taxas `Decimal(6,3)`.

*Fatia 1 — `purchasing` e `agents`:*

| Tabela | Colunas que não são óbvias |
|---|---|
| `purchasing_invoicedocument` | `source` (`upload\|capture`) · `closed_at` null · `discarded_at` null · `created_by` (FK User, SET_NULL) + `created_by_name` char(150) · **sem ficheiro e sem cabeçalho**, e **sem colunas de captura**: o slot é `created_at` + 15 min + zero páginas, derivado (ADR 0020, decisão 2) |
| `purchasing_documentfile` | `document` FK CASCADE · `position` · `path` char(255) (nome gerado, nunca o do cliente) · `original_filename` (rótulo, nunca caminho) · `content_type` (o **real**, do `python-magic`; o do cliente é ignorado) · `byte_size` · `sha256` char(64) · `pages_detected` · **unique (document, sha256)** |
| `purchasing_documentpage` | `document` FK · `file` FK · `file_page_number` · `position` · `image_path` null · `width`/`height` null · `normalized_at` null · unique (document, position) e (file, file_page_number) |
| `agents_extraction` | `document_id` **UUIDField** · `attempt` smallint · `model` · `prompt_version` · `idempotency_key` unique · `started_at`/`finished_at` · tokens e `cost_eur` · `status` (`pendente\|lido\|ilegivel\|erro`) · `confidence` · `payload` JSON · unique (tenant, document_id, attempt) |

Três tabelas para o documento e não uma, por uma razão medível: **um PDF de dez páginas é um ficheiro
e dez páginas, duas fotografias são dois ficheiros e duas páginas**, e a contagem não é a mesma. O
`sha256` com unicidade por documento é o que faz uma retentativa em rede má não criar uma página
duplicada — e uma página duplicada é uma linha duplicada é uma entrada de stock duplicada.

*Fatia 2 — `catalog`, `inventory_location`, e a receção:*

| Tabela | Colunas que não são óbvias |
|---|---|
| `catalog_product` | `short_name` · `base_unit` (`g\|ml\|un`) · `display_unit` + `display_factor` · `count_unit` null · `min_quantity` (**na unidade base**) · `track_lots` · `expiry_kind` null (`use_by\|best_before`) · `conservation` · `is_active` (um artigo com histórico não se apaga) · unique (tenant, LOWER(short_name)) |
| `catalog_productpackaging` | `product` FK · `label` ("caixa 12×1 L") · `base_quantity` (quantas unidades base vale **uma** embalagem) · `ean` null · unique (tenant, product, LOWER(label)) e parcial (tenant, ean) |
| `catalog_supplier` | `name` · `nif` char(9) null · `is_active` · unique parcial (tenant, nif) e unique (tenant, LOWER(name)) |
| `catalog_supplierproductcode` | `supplier` · `product` · `packaging` null · `code` · `description_raw` · unique (tenant, supplier, code) — é o que faz o match ser exacto à segunda fatura |
| `inventory_location` | `name` · `position` · `is_active` · unique (tenant, LOWER(name)). Sem `slug`: o contrato manda `{id, name}` e o `?loja=` é o id |
| `purchasing_receipt` | `document` FK SET_NULL null (uma receção à mão não tem ficheiro) · `supplier` FK null + `supplier_name`/`supplier_nif` **como vêm impressos** · `doc_type` · `doc_number` null · `reference` (a que o ledger copia, normalizada e imutável) · `received_at` · `customer_name`/`customer_nif` null · `document_total_eur` null · `temperature_c` null · `location` (destino por omissão) · `confirmed_at`/`confirmed_by`/`confirmed_by_name` · unique parcial (tenant, supplier_nif, doc_type, doc_number) where `doc_number` not null |
| `purchasing_receiptline` | as duas zonas da decisão 3 · `position` unique por receção · `base_per_invoice_unit` (**snapshot** do factor usado) · `variable_weight` · `movement_id` UUIDField null |

O `base_per_invoice_unit` em snapshot é o mesmo argumento do `unit_cost` da ADR 0014: a embalagem é
editável, e uma conversão histórica que mude quando alguém corrige o rótulo de uma caixa reescreve
quantidades que já foram ao ledger. O `location` **não é anulável** porque o contrato o exige por
linha; é semeado com o destino do documento e alterável linha a linha — o que é exactamente o caso da
ida ao Makro com mercadoria a ficar em duas lojas. A unicidade parcial do documento é a rede contra o
**duplo lançamento da mesma fatura**, e a fatura manuscrita sem número fica sem essa rede, dito aqui
em vez de descoberto.

*Fatia 3 — o ledger:*

| Tabela | Colunas que não são óbvias |
|---|---|
| `inventory_lot` | `product` · `code` · `expires_at` null · `received_at` · unique (tenant, product, code). **Sem `expiry_kind`** — o rótulo é do artigo. Um artigo com `track_lots=False` dá movimentos com `lot_id` NULL e não um lote sintético |
| `inventory_stockmovement` | `movement_type` (os **nove** da ADR 0014) · `quantity` **com sinal** · `unit_cost` · `cost_is_estimate` · `reason` null · `reference` null · `production_id` UUIDField null · `occurred_at` · `created_by` + `created_by_name` char(150). **Append-only na base de dados**: `REVOKE UPDATE, DELETE ON inventory_stockmovement FROM stockflow_app` na migração que a cria |
| `inventory_stocklevel` | `(product, location, lot)` com `quantity`, unique com **`nulls_distinct=False`** — sem isso o Postgres trata cada `lot_id` NULL como distinto e a projeção ganha linhas duplicadas para os artigos sem lote |
| `inventory_productcost` | `product` unique por tenant · `unit_cost`. **Sem quantidade**: a média ponderada usa a soma dos níveis lida na mesma transação, e uma segunda quantidade era um número a divergir |

A quantidade é guardada **com sinal** e não em valor absoluto: uma soma passa a ser `SUM(quantity)` em
vez de um `CASE` por tipo, e o `adjustment` é o único movimento cujo sinal o tipo não determina. O
serializer de escrita continua a receber o valor absoluto, como o contrato manda
(`quebraParaRegistarSchema`), e o sinal é posto no serviço. O `updated_at` que a tabela herda do
`TenantModel` nunca difere do `created_at` — não vale uma base abstracta nova, fica nomeado.

**O que não entra, e é uma tabela a menos do que a `ARCHITECTURE.md` §2 prevê:
`purchasing_supplierprice`.** O `price_history` de uma linha (a manteiga a 9,40 € contra 7,80 €) lê-se
das **linhas confirmadas** por um índice, que é o que a fixture já faz, e uma segunda cópia do preço é
uma segunda fonte de verdade sobre dinheiro quando a primeira já é imutável de facto — uma receção
confirmada não se edita. Gatilho para a criar: preços **acordados**, que existem antes de haver
compra. Pelo mesmo teste sai a `PurchaseOrder`, que o contrato recusa por extenso (*"se o modelo de
dados exigir uma `PurchaseOrder`, está errado para o mercado português"*), e o nome
`PurchaseReceiptDraft` da §2 fica corrigido para `Receipt`: a mesma linha é o rascunho e o documento
confirmado, porque o contrato tem dois estados e um `id` que não muda.

**Decisão 8 — A ordem das fatias, e a primeira é o documento sem revisão de linhas.** Confirmo a
direcção proposta — documento primeiro, efeito no stock no fim — e corrijo a fronteira: **a revisão
humana não cabe na fatia 1**, porque todos os campos que ela escreve precisam do catálogo, e porque o
`location` de uma linha não é anulável no contrato. Querer revisão na fatia 1 é querer o catálogo na
fatia 1.

1. **O documento** — as quatro tabelas acima, o recurso `/documents`, a rasterização e a extração.
   Entrega-se ao dono exactamente o que ele pediu: arrastar um PDF no desktop, ver as páginas, e ver
   **o que o modelo leu**, num painel só de leitura. Nenhuma das onze perguntas de domínio entra numa
   migração desta fatia, e é essa a propriedade que a torna a primeira.
2. **O catálogo e a revisão** — `catalog_*`, `inventory_location`, `purchasing_receipt` e
   `purchasing_receiptline`; `/receipts` em GET, a revisão por linha e a temperatura. A extração passa
   a escrever linhas pelo `purchasing.api`.
3. **O ledger** — `inventory_lot`, `inventory_stockmovement`, `inventory_stocklevel`,
   `inventory_productcost`, o `POST /receipts/<id>/confirmation`, e os níveis e movimentos do ecrã de
   Stock. Uma transação: lotes, movimentos, projeção, CMP.

**A razão de o documento vir antes do catálogo é melhor do que "foi o que o dono pediu": a fatia 1
produz a prova de que a fatia 2 precisa.** O plano de sessões do README punha catálogo (2) e ledger
(3) antes da receção (6–7); isso congela a forma do catálogo antes de alguma vez se ter lido uma
fatura real, e as faturas reais são a melhor evidência disponível sobre o que o catálogo precisa de
ter — que unidades vêm impressas, que embalagens existem, quantos artigos chegam pesados peça a peça,
quantos fornecedores são ENI. Ler trinta faturas do dono antes de escrever `catalog_product` é mais
barato do que escrever `catalog_product` e descobri-lo com migrações aplicadas, que o `CLAUDE.md`
proíbe editar.

**Decisão 9 — O contrato novo, que é o único que esta ADR inventa.** Caminhos e campos em inglês,
como os vizinhos. Permissão: `IsAuthenticated` + `PertenceAoTenant`, **qualquer membro activo** — pela
razão da decisão 1b da ADR 0020, receber mercadoria é trabalho de quem está lá —, mais
`has_object_permission` a comparar `obj.tenant_id == request.tenant.id` em todas as que recebem um
`pk` (SECURITY.md §5). `ScopedRateThrottle` nas escritas.

```
POST   /api/v1/documents                      201 DocumentoOut   (slot, com ou sem ficheiro)
POST   /api/v1/documents/<id>/files           201 DocumentoOut   (multipart, um ficheiro)
POST   /api/v1/documents/<id>/closing         200 DocumentoOut   (repetível)
GET    /api/v1/documents                      lista paginada
GET    /api/v1/documents/<id>                 200 DocumentoOut   (o alvo do polling, ADR 0020 d.3)
GET    /api/v1/documents/<id>/pages/<n>/image 200 image/webp     (inline, nosniff, com âmbito)
DELETE /api/v1/documents/<id>                 204                (descarta; só apaga bytes se não houver páginas)

DocumentoOut  { id, source, state, created_at, created_by, closed_at, expires_at,
                page_count, page_limit, files: [FicheiroOut], pages: [PaginaOut],
                extraction: ExtracaoOut | None, receipt: UUID | None }
PaginaOut     { position, image_url, width, height, normalized }
FicheiroOut   { position, original_filename, content_type, byte_size, pages_detected, received_at }
ExtracaoOut   { state, confidence, read_at, supplier_name, supplier_nif, doc_type, doc_number,
                issued_at, customer_nif, total, lines: [LinhaLidaOut] }
LinhaLidaOut  { position, description, quantity, unit, unit_price, vat_rate, line_total, confidence }
```

O `state` é **derivado e nunca guardado**, como o estado do convite (ADR 0010) e o do slot (ADR 0020):
`aguarda_captura | a_normalizar | a_extrair | lido | ilegivel | descartado`, com o `a_extrair` a
precisar de um relógio — uma tarefa morta deixaria o estado preso para sempre, logo é
`a_extrair` enquanto a última extração tiver `finished_at` nulo e menos de dez minutos, e `erro`
depois. **Um ficheiro fecha-se a si mesmo** (um PDF de dez páginas é um documento completo e o número
de páginas sabe-se do ficheiro); **uma captura é fechada por uma pessoa**, e também pelo desktop
(ADR 0020, decisão 1g sobrevive à revogação). Reabrir é possível enquanto não houver receção
confirmada, e cada abertura acrescenta uma linha de extração em vez de sobrepor a anterior.

**E quem serve os bytes da imagem, que a ADR 0020 deixou em aberto.** Ela decidiu que o proxy nunca
encaminha `/media/` e que o `MEDIA_URL` fica sem valor, mas alguém tem de servir a imagem que o ecrã
de revisão mostra: é **uma view com âmbito**, `inline`, `nosniff`, `Cache-Control: private` e imutável
(o caminho contém o uuid da página). O original sai só pela acção explícita da decisão 5 da ADR 0020,
com `attachment` e `octet-stream`. Gatilho para trocar por URL assinada: o object storage, que é
setting e não código.

**Decisão 10 — `accounts.api` ganha o primeiro consumidor real, e é uma função e não o DTO.** O
`/receipts/summary` precisa da hora a que o dia de negócio começa, que já é coluna do
`accounts_tenant` (migração 0008/0009). O `services.py` do `accounts` prevê este dia por extenso:
*"um DTO público sem consumidor é um contrato público escrito ao contrário, e o dia em que houver um
consumidor real a subida para o `api.py` é uma linha"*. Sobe **`inicio_do_dia_de_negocio(tenant_id) ->
time`** e não o `EstabelecimentoOut`, porque o DTO carrega o `vat_regime` e o mesmo docstring diz
porque é que ninguém o pode ler para valorizar o passado. Uma função expõe a fronteira do dia e não a
regra fiscal.

**Alternativas.** *Catálogo primeiro, como o plano do README* — congela o catálogo sem evidência, e a
evidência é o que a fatia 1 produz (decisão 8). *Uma tabela só para o ficheiro e a receção* — uma
receção à mão não tem ficheiro, e um ficheiro pode não ser uma fatura (ADR 0020, decisão 8): o
documento é físico, a receção é uma interpretação dele, e uma fotografia de um gato tem páginas e
nunca tem receção. *`PurchaseReceiptDraft` e `PurchaseReceipt` como duas tabelas, com cópia na
confirmação* — o contrato tem dois estados e um `id` que não muda, e copiar linhas duplicaria a
verdade e obrigaria o `movement_id` a viver na cópia. *Guardar o output do modelo em colunas tipadas,
num espelho da linha de receção* — duplica o esquema para guardar uma afirmação não confiável e obriga
a migrar as duas tabelas em sincronia; o que se quer do modelo é **verbatim**, e verbatim é JSON.
*Confiança por linha num `JSONField`* — recusada pela ADR 0011 na letra: é um número que a UI realça,
logo é contrato, logo é coluna. *FK do `receiptline` para o movimento* — decisão 5. *Uma FK só na base
de dados, por `RunSQL`, sem relação ORM* — fecharia a afordância da travessia por construção, e é
tentador; recusada porque é um padrão novo a repetir em cada migração para fechar uma porta que o DTO
em lote já torna desnecessária, e porque uma relação que o `makemigrations` não gere é uma relação que
a próxima migração esquece. *Uma receção por localização, partindo a fatura do Makro em três* —
perde a correspondência com o papel que o contabilista tem na mão; a localização é da linha, e o
contrato já manda `locations: []` no documento. *`StockLevel` ao grão (artigo, localização), sem
lote* — o FEFO e os alertas são por lote, e agregar depois é barato enquanto desagregar nunca é
possível. *Extração síncrona no pedido do upload* — o `CLAUDE.md` proíbe efeitos secundários
síncronos, e a ADR 0005 mostra o que uma chamada a LLM dentro do pedido faz aos locks do FEFO.
*`agents` a escrever em `purchasing_receiptline`* — entra pelo `purchasing.api` (ADR 0020, decisão 6),
e a razão de esquema é a secção 7.

**Consequências.** **Quinze tabelas novas** — quatro na fatia 1, sete na fatia 2, quatro na fatia 3 —,
todas com `tenant_id` e portanto todas com o bloco de RLS na migração que as cria. As três listas
fechadas: o `SEM_POLITICA` do `test_db_roles.py` **não mexe** (nenhuma destas tabelas é lida fora de
âmbito, e é a adenda 2 da ADR 0020 que o garante, ao revogar o caminho anónimo); o `fora_do_admin` do
`test_rls_isolation.py` **não cresce** (pela mesma adenda); e o `APPEND_ONLY` ganha **uma** entrada,
`inventory_stockmovement`, na fatia 3 — a primeira da sua história, com o `REVOKE UPDATE, DELETE` ao
lado do bloco de RLS, e o `CLAUDE.md` exige o `domain-expert` antes dela. **Zero contratos novos no
import-linter**: as arestas que esta ADR usa — `purchasing → inventory.api, catalog.api`,
`inventory → catalog.api`, `agents → purchasing.api, catalog.api` — são exactamente as que já estão
declaradas, e não ter um contrato novo a escrever é o sinal de que o desenho não inverteu o grafo.
Nenhum destes modelos é registado no admin (ADR 0007).

**Três tarefas Celery e nenhum evento.** `purchasing.tasks.normalizar_pagina`,
`purchasing.tasks.limpar_slots_expirados` e `agents.tasks.extrair_documento`, todas com `tenant_id`
obrigatório pelo `TenantTask`, e o `tenant_id` vem **da linha do documento** e nunca de
`request.tenant` (ADR 0020). Zero eventos emitidos ou consumidos: não há consumidor da outbox, e um
evento sem subscritor é um contrato público escrito ao contrário (ADR 0010, ADR 0013) — logo a cadeia
do §6b do `ARCHITECTURE.md` é, até lá, tarefa a enfileirar tarefa, e o evento só liga no dia em que o
consumidor existir. **E não há beat**, logo a limpeza dos slots não corre: dívida já nomeada no
`SESSION-CONTEXT.md`, e esta feature é a primeira a precisar dela. **O ticket D5 deixa de ser
teórico** — ele diz "não há tarefas de domínio", e a partir da fatia 1 há três; o que o limita é o
`tenant_id` sair sempre de uma linha lida dentro do âmbito.

**O seed do `apps/demo` é o destino do trabalho que está nas fixtures, e é isso que torna o
apagamento indolor.** Os 22 artigos, as 3 localizações, os 7 documentos e os ~45 movimentos do
`fixtures/aurora.ts`, `ledger.ts` e `rececoes.ts` são afirmações de domínio validadas, e cada uma está
lá por uma razão nomeada no guião. Quando morrerem, não se perdem: traduzem-se para o
`semear_demonstracao` (ADR 0018), que hoje só semeia `accounts` e passa a entrar pelos `api.py` do
`catalog`, do `inventory` e do `purchasing` — arestas de saída, como a ADR 0018 exige.

**O caminho do apagamento, fatia a fatia** (ADR 0008, decisão 3: *"termina por apagamento"*).
**Fatia 1: nada se apaga** — `/documents` é recurso novo, e o shell nunca mentiu sobre o upload (a
rota `fotografar` diz em texto que não há câmara). O que muda no frontend é o `fotografar.tsx`, que
perde o aviso e ganha a zona de ficheiro e o bloco do QR, e o `validateSearch` com os dois uuids
(ADR 0020, decisão 7 corrigida: sem `hidden md:block`). **Fatia 2: nada se apaga** — a remoção é por
recurso, e o recurso `/receipts` não está completo enquanto a confirmação não existir; os endpoints
novos vivem no `schema.yml` e são exercitados por `pytest` e `curl` e não pelo browser, que é como
este repositório já trabalha. **Fatia 3: morrem `rececoes.ts` e `stock.ts`, juntos e no mesmo dia**, e
a razão está no próprio `rececoes.ts`: ele é a única escrita do `ledger.ts`, logo apagá-lo sozinho
deixava o ecrã de Stock a mostrar um ledger que já não cresce quando se confirma uma receção real — a
contradição exacta contra a qual o `resolverMovimentos()` rebenta no arranque. O `ledger.ts`,
`aurora.ts` e `decimal.ts` saem com o último consumidor, nas fatias dos alertas e da contagem, que
precisam de `inventory_stockcount` e da linha de configuração do `inventory` (ADR 0011, forma 2) e não
são desta ADR.

**O que tem de ser decidido por um humano antes de existir migração.** O `CLAUDE.md` proíbe editar uma
migração aplicada, logo estas escolhas ficam caras depois.

*Bloqueia a fatia 1 — três, e é pouco de propósito:*

1. **"Qual é o documento com mais páginas que lhe entra por mês — e dez chega?"** O teto de dez
   páginas por documento é simétrico ao de PDF (ADR 0020, decisão 4) e é também o teto de custo por
   captura. Um rolo de cash & carry pode passá-lo.
2. **"Depois de lançar a fatura, o que faz com o papel? E o contabilista precisa do ficheiro?"**
   Decide se existe a acção de descarregar o original, quanto tempo o original fica, e se a purga é
   uma tarefa ou nunca acontece. Uma fatura traz NIF e morada (SECURITY.md §3).
3. **"Quem envia faturas, e quem pode apagar um documento que entrou errado?"** O envio está decidido
   (qualquer membro activo); o apagamento decide se `discarded_at` é de qualquer membro ou só de quem
   manda, e é a única permissão desta fatia que não é óbvia.

*Bloqueia o ledger (fatias 2 e 3):*

4. **"O mínimo de um artigo é um número só, ou um por loja?"** Decide se `min_quantity` é coluna do
   artigo ou uma tabela `(artigo, localização)`. A sonda da Q2 compara o **mesmo** mínimo contra o
   consolidado e contra cada loja, e isso lê-se como um mínimo por artigo — mas é afirmação de domínio
   e não nossa (ADR 0011).
5. **"Quando conta manteiga, conta em quilos ou em blocos? E quando a compra?"** Decide se o artigo
   tem duas unidades (base e apresentação) ou três (a de contagem é um campo do contrato da contagem).
6. **"A validade está sempre na embalagem, e é sempre quem recebe que a escreve?"** Decide se
   `inventory_lot.expires_at` é anulável e se um artigo sem lote pode ter validade.
7. **"'Consumir até' e 'consumir de preferência antes de' são uma propriedade do artigo ou daquela
   caixa?"** Decide se `expiry_kind` vive no artigo (a decisão desta ADR) ou no lote. A fixture
   põe-no no lote e o comentário do contrato di-lo do artigo; um dos dois está errado.
8. **A mais cara de todas: "a guia de remessa entra sem preço. Quanto vale essa mercadoria no dia em
   que entra?"** O `unit_cost` de um movimento é append-only: não se pode deixar nulo e preencher
   quando a fatura chegar, porque isso é um `UPDATE` numa tabela onde ele está revogado. As saídas são
   duas — entrar ao último preço conhecido com `cost_is_estimate=True` (ADR 0013, decisão 8), ou
   entrar a zero e corrigir com um movimento novo — e as duas são visíveis no painel de maneiras
   diferentes. Sem resposta, a fatia 3 não tem migração.
9. **"Uma nota de crédito devolve mercadoria, ou corrige o preço de uma que ficou?"** Decide se o
   `return` sai sempre do stock ou se há notas de crédito que não tocam no ledger, e decide a
   reconciliação da coluna que o desvio 7 adiou.
10. **"Três lojas são uma empresa com três lojas, ou três empresas?"** A ADR 0005 já afirma um tenant
    com N localizações; inverter isto depois é re-tenantizar dados, e é a mais cara de reverter.
11. **"A Ana, do balcão, pode lançar uma fatura e dar entrada a stock?"** Não bloqueia migração
    nenhuma — é uma classe de permissão num sítio só —, mas bloqueia o contrato: o default desta ADR é
    qualquer membro activo, porque restringir inventaria a ordem entre papéis que a Q7 não respondeu
    (ADR 0010, ADR 0011). O autor fica em cada movimento, e é isso que a sonda da Q7 mede.

**A Q1 não bloqueia esta feature, e vale dizê-lo porque parece que bloqueia.** "Bloquear ou avisar
quando falta stock" (ADR 0012) é sobre saídas; um `receipt` só soma. O que ela toca é o `POST
/stock/movements` da quebra, que entra na fatia 3 pelo ecrã de Stock: aí implementa-se a variante
permissiva que o shell já mostra, num ponto de imposição só em `inventory.services`, e a resposta da
sessão 0 muda uma função. A hora do dia de negócio (Q6) já está respondida e migrada.

**Dívida que esta ADR cria e nomeia em vez de esconder.** O **NIF do fornecedor tem a mesma natureza
do NIF do tenant** — a frutaria do mercado é um ENI, e o seed já traz um NIF com prefixo 2 a prová-lo.
Fica coluna em claro, e o argumento não é conveniência: a **imagem da fatura** contém o mesmo NIF, a
morada e a assinatura do documento, e encriptar a coluna enquanto se guarda o JPEG em claro no
`MEDIA_ROOT` protege o índice e não a pessoa. O gatilho é a sessão da encriptação de campo, que passa
a ter de cobrir o `MEDIA_ROOT` e não só colunas. Fica também o que já estava em aberto e agora tem
mais linhas lá dentro: **apagar um tenant com um ledger append-only** (SECURITY.md §3) deixa de ser
teórico a partir da fatia 3, e o apagamento passa a ser uma operação privilegiada — o role da app não
tem `DELETE` no movimento. E o ticket D3 (o guarda de âmbito do `conftest.py` a filtrar por
`sql.lstrip()[:6]`) deixa de ser inofensivo se a projeção for recalculada com um `WITH`.

**Consultar `domain-expert`**, e não é formalidade: esta feature toca em stock, validades, unidades,
receitas e faturas, que é a lista inteira do `CLAUDE.md`. As perguntas que lhe pertencem, além das
onze de cima: se o `unit_cost` de um `receipt` é o preço da linha ou o preço com portes rateados; se o
CMP é por artigo ou por (artigo, localização); se o IVA por taxa se calcula sobre a base agregada (como
a fixture faz, e como uma fatura portuguesa imprime) ou somando as linhas; se o ATCUD e o QR são fonte
fiável para o cabeçalho antes de qualquer extração; se uma fatura de duas folhas é um documento ou
dois e se um rolo de cash & carry é um ou cinco (herdadas da ADR 0020, e agora com o dedo de quem
fecha o documento a traçar a fronteira); e se um documento pode ser reaberto depois de a revisão ter
começado.

---

## Adenda — a consulta ao `domain-expert`, feita no mesmo dia

Esta ADR acabou com uma lista de perguntas para o `domain-expert`. Elas foram feitas **em paralelo**
com a escrita dela, e as respostas fecham cinco e corrigem três decisões. Fica aqui em vez de na
cabeça de quem leu as duas.

### O que fecha

**O ATCUD e o QR são fonte fiável para o cabeçalho, e isso muda a divisão do trabalho.** Desde
1/1/2023 toda a fatura portuguesa imprime um **código QR** que traz, legível por máquina e sem erro de
OCR: os dois NIF, o tipo de documento, o **estado** (normal ou anulado), a data, a identificação do
documento, o ATCUD, o **espaço fiscal** (`PT` · `PT-AC` · `PT-MA`) e as **bases e o IVA por taxa**,
mais o total. Não traz as linhas.

Logo: **o QR é a verdade do cabeçalho e o LLM só serve para as linhas.** Três consequências que
entram no desenho:

1. **`purchasing_documentpage` ganha `qr_payload` (texto, null)** — é uma coluna da fatia 1, e é
   barata hoje. A leitura é determinística (não é extração) e acontece antes de qualquer chamada ao
   modelo. **A biblioteca que a faz é uma dependência nova e não está escolhida**: a coluna entra
   agora porque é grátis, a descodificação entra quando a dependência for decidida. Até lá o campo
   fica nulo e o cabeçalho vem da extração, como esta ADR já previa;
2. um documento cujo QR diga **anulado** é motivo para recusar na revisão, e não um aviso;
3. a validação das taxas de IVA **não é contra um conjunto fixo**: Continente 6/13/23, Madeira
   5/12/22, Açores 4/9/16, e o campo do espaço fiscal do QR é o que decide qual. O papel ganha sempre
   — incluindo 0 %, que é o que uma aquisição intracomunitária com autoliquidação imprime.

**O IVA por taxa calcula-se sobre a base agregada**, como a fixture faz e como uma fatura portuguesa
imprime. Confirmado. Com tolerância de ±0,02 € por taxa ao comparar com o impresso, e algo que escale
no total, senão um rolo de trinta linhas do Makro falha sempre por um cêntimo.

**O `unit_cost` de um `receipt` é o preço da linha e não o preço com portes rateados** — em v1, e por
três razões que não são de engenharia: o CMP tem de ser explicável apontando para uma linha de um
papel; qualquer chave de rateio é arbitrária; e uma chave arbitrária gravada num campo append-only não
se revisita. Fica com gatilho: um cliente com transporte acima de ~5 % do valor da mercadoria.

**O desconto de linha é a excepção e entra sempre no custo**, e é o bug clássico desta família: o
`unit_cost` deriva do **total líquido da linha** e nunca do preço unitário impresso. O
`purchasing_receiptline` ganha o desconto, o `line_total` é líquido, e o histórico de preços compara
líquidos — comparar o impresso mente na presença de um desconto.

**A tara não é custo, e é lei e não convenção**: uma embalagem retornável cuja devolução foi
convencionada e consta da fatura como tal está fora da base tributável (é a razão por que a linha de
tara vem sem IVA, exactamente como o seed a tem). A decisão 6 desta ADR já diz que `deposit` não gera
movimento; falta a outra metade, que é **excluí-la também do `purchases_eur`** da ADR 0013. Um bar que
roda quarenta grades por semana mostra custos fantasma se a tara for compra.

### O que corrige

**1. A temperatura não é um valor por documento — é um por classe de conservação.** A tabela da fatia
2 tem `temperature_c` null no `purchasing_receipt`, que é o que o contrato actual já serve, e **está
errado por construção**: a fatura simplificada do Makro que está no seed traz congelados (rissóis,
bacalhau) e refrigerados (queijo, fiambre, com 7,0 °C registado). 7 °C é aceitável num refrigerado e é
uma catástrofe num congelado. Um registo HACCP com um número só é um registo errado.

A forma: uma linha por classe presente no documento (no máximo duas que interessam — `chilled` e
`frozen`), com **quem mediu e quando**, porque um registo HACCP é assinado. Os limites exactos **não
se codificam**: vivem no plano HACCP do estabelecimento e variam por produto (congelados na ordem dos
−18 °C, refrigerados tipicamente ≤ 4–6 °C, carne picada e peixe mais exigentes).

Custa uma alteração no frontend, e é a altura de a fazer: hoje são duas linhas de contrato.

**2. `Decimal(12,4)` não chega para o custo unitário.** Com a unidade base ao grama, um saco de 25 kg a
17,33 € dá 0,00069320 €/g, que a quatro casas é 0,0007 — e 0,0007 × 25 000 = **17,50 €**. Dezassete
cêntimos a mais, ~1 % da linha, em silêncio.

A correcção: **o número autoritário de um movimento é o valor total em euros**, e o custo unitário
deriva-se para mostrar ou guarda-se a seis casas. E o CMP calcula-se `Σ valor / Σ quantidade`, **nunca**
como média ponderada de custos unitários arredondados. Entra na fatia 3, que é onde o movimento nasce.

**3. O `base` dos totais mistura base tributável com caução, e isso já está no código.** Medido no
`frontend/fixtures/rececoes.ts`: o `base += centimos` acontece **antes** do `continue` que salta as
linhas sem IVA, logo a tara soma ao `base` e não soma a nenhuma taxa. O total acerta por acidente (a
tara *é* parte do total do documento), e o campo chamado `base` fica errado — `Σ vat_breakdown.base ≠
base`. Num seed é inofensivo; num serializer é o cêntimo que manda alguém à caça. A identidade que o
serializer tem de respeitar é:

    total_impresso == Σ(base por taxa) + Σ(IVA por taxa) + Σ(linhas não tributáveis)

### O que o `domain-expert` acrescenta às tabelas, e que esta ADR não tinha

Todos baratos hoje e caros depois, por serem colunas de tabelas que ainda não existem:

- **no documento/receção:** `doc_date` (a data impressa — é a chave de deduplicação, a validação de
  plausibilidade e o que o contabilista pede; o `received_at` é outra coisa e os dois coexistem) ·
  `atcud` · `fiscal_space` · `doc_number_normalized` (a chave de unicidade; o impresso guarda-se como
  está) · a ligação **N guias ↔ 1 fatura** · `cost_is_provisional`;
- **na linha:** `supplier_code` e `ean` (sem eles a memória do match não existe e cada fatura é a
  primeira) · o desconto · `reverses_movement` nas linhas de nota de crédito que devolvem mercadoria,
  porque **uma devolução sai ao custo a que entrou** e não ao CMP de hoje;
- **nos enums:** `doc_type` ganha **`ND`** (uma correcção de preço *para cima* não vem em nota de
  crédito, vem em nota de débito: valor sobe, mercadoria não mexe) e a espécie de linha ganha
  **`document_ref`**, porque muitas faturas de fim de mês não repetem as linhas — a linha é
  `"GUIA 4471 DE 06/10/2026"`, quantidade 1, com um valor, e isso não é uma linha de produto.

E a restrição de unicidade da decisão 7 fica **completa com duas e não uma**: a parcial
`(tenant, supplier_nif, doc_type, doc_number)` que a ADR já tem, mais `(tenant, atcud)`. As duas são
necessárias porque o `sha256` por ficheiro não as substitui: uma fotografia e um PDF da **mesma**
fatura têm bytes diferentes e passam os dois. O documento duplicado duplica o stock e duplica as
compras, e descobre-se semanas depois numa contagem com um mês de custo errado atrás — **se só uma
restrição desta feature for escrita, é esta.**

### O erro mais caro do fluxo, que nenhuma coluna resolve

A fatura de fim de mês lançada como entrada **depois** das guias que ela liquida. A detecção é
possível (linhas que referenciam guias, o fornecedor tem guias abertas, as quantidades casam), mas a
defesa a sério é de ecrã e vive **antes** do botão: *"esta fatura liquida 14 guias — não dá entrada de
mercadoria"*. Entra com a reconciliação, e a pergunta 2 do dono (quantos fornecedores faturam a fim de
mês) decide se isso é fatia 2 ou fatia 3.

### O que o `domain-expert` diz que não sabe

O artigo exacto do CIVA que exclui as embalagens retornáveis da base tributável (indica o 16.º), o
fundamento legal preciso da facturação global mensal contra guias, o limiar do art. 53.º para 2026, e
os limites de temperatura por produto — que existem, variam e vivem no plano HACCP. **As quatro são
para o contabilista de um cliente, não para o dono**, e nenhuma bloqueia uma migração.
