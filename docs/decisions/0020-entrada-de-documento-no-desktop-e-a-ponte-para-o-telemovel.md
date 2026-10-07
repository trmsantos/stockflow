# ADR 0020 — Entrada de documento no desktop, e uma ponte para o telemóvel sem segredo novo

**Contexto.** O dono do produto pede duas coisas (2026-10-07): *"no 'Receber' dá para fotografar
fatura e tudo bem, mas no desktop deveria dar para dar upload a um pdf/fatura para fazer extração dos
documentos. Em app desktop se for para tirar foto tem de ser gerado um QR Code para poder abrir no
telefone a camera e tirar por sua vez a foto da fatura e depois fazer essa conexão entre
desktop/telemovel"*. A primeira é um validador; a segunda é a decisão. O que existe hoje: a rota
`/receber/fotografar` diz em texto que não há câmara, as receções vêm do servidor de fixtures (ADR
0008) e o `purchasing`, o `agents` e o `catalog` são conchas com **zero models**. O `base.py` tem um
comentário correcto a dizer que as suas settings de upload não são um teto de tamanho e a nomear as
duas coisas que o seriam; **uma das duas já existe** — `request_body { max_size 12MB }` no
`docker/caddy/proxy.Caddyfile:101`, e o comentário do `base.py` ainda a trata como futura. Falta a
outra: o validador no serializer. E há um precedente directo para a ponte, a ADR 0010:
`/ativar#<uuid-do-tenant>.<token>`, onde o uuid é **argumento** e o token é o segredo verificado
dentro do âmbito que o uuid abre. A pergunta desta ADR é se a ponte é essa forma com outro nome.

**Decisão 1 — Não é, e a diferença é que a ponte não precisa de segredo nenhum. O QR transporta dois
identificadores e o que concede é a sessão do próprio telemóvel.** O token do convite existe porque
do outro lado **não há ninguém ainda**: ele compra *identidade*. Aqui a identidade já existe — quem
fotografa a fatura é um membro do estabelecimento — e o que falta é só um **ponto de encontro**, que é
um id e não um segredo. Logo o QR leva `<uuid-do-tenant>.<uuid-do-documento>`, os dois argumentos, e o
telemóvel chama um endpoint **normal**: com sessão, com âmbito, com CSRF pelo caminho de sempre. O
`uuid-do-documento` é lido dentro do âmbito que a sessão do telemóvel escolheu e que a política
concede (ADR 0007); um documento de outro tenant dá zero linhas e a recusa genérica. **A superfície
dispensada de âmbito não cresce em uma entrada**, e isso é o gate.

Isto responde às três objecções, e vale responder uma a uma porque cada uma leva a um desenho
diferente. *"Um QR é fotografável por quem está na sala"* — a resposta é **tirar-lhe o segredo**, não
encurtar-lhe o TTL: quem o fotografa sem pertença recebe o ecrã de entrada e mais nada, e quem o
fotografa **com** pertença podia já fazer upload de um documento por si. *"O telemóvel pode não ter
sessão nenhuma"* — precisa de uma, **uma vez**, e o produto já lha exige: `contar` é `campo: true` e
não se conta sem sessão. O que mata a feature é um login **por captura**; um login por telemóvel e
por 14 dias (`SECURITY.md` §5) é o que já se paga. *"O sentido do fluxo é inverso"* — é, e é essa a
razão pela qual não há segredo: o convite concede **acesso** a quem não o tem; isto escreve um
ficheiro dentro de um âmbito que já existe, para alguém que já o tem.

E compra uma propriedade que um token ao portador não deixaria ter: **o slot aceita várias páginas.**
Uma fatura em duas folhas são duas fotografias, e com um portador reutilizável N escritas seriam N
usos do mesmo segredo. Sem segredo, N páginas são N escritas de um membro autenticado — nada de novo.

**Decisão 2 — O slot é um estado do documento, não uma tabela nova.** O desktop cria um
`InvoiceDocument` **sem ficheiro**; o QR nomeia-o; o telemóvel anexa-lhe páginas; o desktop lê-o. O
estado é **derivado e nunca guardado**, como o `EstadoDoConvite` da ADR 0010 e pela mesma razão: um
timeout não escreve linha nenhuma, logo um estado em coluna estaria errado quinze minutos depois.
`aguarda_captura` enquanto `created_at` tiver menos de **15 minutos** e não houver páginas; `expirado`
depois. Um documento com zero páginas nunca aparece na lista do Receber. **Esta ADR não desenha as
colunas do `InvoiceDocument`** — isso é da ADR da receção por fatura, que também lhe deve o
`PurchaseReceiptDraft`; o que fica fixado é que a ponte **não acrescenta tabela** e que o documento
tem de poder existir antes do ficheiro.

**Decisão 3 — O desktop sabe por polling de um endpoint que já tinha de existir. Nem SSE, nem
WebSocket.** A conta: entre o QR aparecer e a fotografia chegar há desbloqueio, câmara,
enquadramento e envio — 15 a 40 s no caso normal, 90 s no mau. Polling a **2 s enquanto o bloco está
aberto, com desistência aos 3 minutos** custa no máximo **90 pedidos por captura**, 30/min de um
desktop contra os 600/min por IP da zona `geral` do proxy: 5 % do orçamento. O endpoint é o `GET` do
documento, que o ecrã de revisão precisa de qualquer maneira — **nenhum endpoint existe só para
polling** — e é uma linha por PK dentro do âmbito. Aos 3 minutos o bloco diz que o documento aparece
na lista quando chegar, e isso é a decisão inteira: **o polling é conveniência, o caminho é a lista.**
O que **não** entra: SSE e WebSocket, porque não há sinal nenhum da secção 7 do `ARCHITECTURE.md` e
porque um socket de vida longa parte o invariante da ADR 0005 — o âmbito é a transação e a transação é
o **pedido**, e o `TenantMiddleware` é por pedido; um socket não tem pedido, e daria um segundo
caminho de autorização a derivar o âmbito por fora do único que existe. A ADR 0011 escreveu que a
resposta a lentidão é `staleTime`; aqui o `staleTime` é 0 de propósito, e não há contradição: aquilo é
a resposta a uma **leitura lenta**, isto é a espera por um **acontecimento externo**, limitada a um
bloco aberto.

**Decisão 4 — Os dois tetos do upload, e decoders nativos nunca no processo que serve pedidos.** O
teto do proxy já existe (12 MiB); o do serializer entra a **10 MiB por ficheiro**, e tem de ser
**estritamente abaixo** do do proxy — acima, a recusa vem do Caddy sem corpo JSON e o formulário não
tem mensagem para mostrar. O `DATA_UPLOAD_MAX_MEMORY_SIZE` fica nos 5 MiB porque conta os campos e
não os ficheiros. O serializer recusa, por campo: extensão fora da allowlist (`.jpg .jpeg .png .webp
.pdf`), tipo real do `python-magic` fora da allowlist, tipo real **em desacordo com a extensão**, PDF
com mais de 10 páginas (contadas com `pypdf`, sem render), zero bytes. O `Content-Type` do cliente é
**ignorado**, não validado. E a linha que separa as duas metades: **nenhum decoder nativo de imagem ou
de PDF corre no processo que serve pedidos** — o pedido faz sniff de bytes e contagem de páginas em
Python puro; Pillow, poppler e pdfium só existem no worker. O ficheiro vai para `MEDIA_ROOT` num
volume, com nome gerado (UUID), nunca o do cliente — que fica guardado como rótulo e nunca como
caminho. `MEDIA_URL` fica **sem valor**, para que um `.url()` acidental levante em vez de emitir um
caminho que ninguém serve, e o proxy nunca encaminha `/media/`.

**Decisão 5 — O PDF nunca é renderizado no browser.** Pode ter JavaScript, ficheiros embutidos e
várias páginas, e o visualizador do browser é superfície que não precisamos de ter. O worker
**rasteriza** cada página para uma imagem normalizada, e é só isso que o ecrã de revisão mostra e que
a extração vê — o que dá também um pipeline uniforme, porque a jusante tudo é imagem. O original fica
para o rasto e sai **só** por uma acção explícita, com `Content-Disposition: attachment`,
`application/octet-stream` e `nosniff`, nunca inline. **Um ficheiro é um documento, com N páginas, e
nunca é partido automaticamente**: se a extração encontrar dois números de documento, baixa a
confiança e diz-o na revisão. Partir é acção humana e não existe no v1.

**Decisão 6 — `purchasing` possui o documento e a normalização; `agents` recebe páginas já imagem.** A
imagem normalizada tem **dois** consumidores — a extração e o ecrã de revisão, que precisa dela mesmo
quando a extração falha — logo é propriedade do documento e não da extração, e a rasterização é uma
tarefa Celery do `purchasing`. O `agents` nunca vê um PDF, nunca corre poppler e entra pelo
`purchasing.api`, que lhe dá páginas como DTO congelado e escreve o draft pela mesma porta — nunca
`purchasing.models`, que os contratos do import-linter já proíbem. A cadeia do §6b do
`ARCHITECTURE.md` corrige-se num ponto: o evento sai **depois** da normalização e não do upload,
porque antes dela não há nada que o `agents` possa ler. E fica nomeado o pré-requisito: **não há
consumidor da outbox** (ADR 0010), logo a cadeia por evento só liga quando ele existir; até lá o
encadeamento é tarefa a enfileirar tarefa, que é o que o passo da extração vai escrever.

**Decisão 7 — Uma rota, e não duas nem três.** `/receber/fotografar` continua a ser **uma** rota e
ganha a câmara a sério (`capture="environment"`), a zona de ficheiro e o bloco do QR, com o bloco
escondido por breakpoint (`hidden md:block`) — um QR no telemóvel que se tem na mão não serve de nada,
e esconder por breakpoint em vez de ramificar por dispositivo é a decisão 1 da ADR 0008 (*"o
mobile/desktop não é um problema de routing"*). O slot **não** vai no URL do desktop e **vai** no URL
do telemóvel, e a regra que resolve a assimetria é a da ADR 0008: o URL carrega o que **reproduz o
ecrã** — no telemóvel o slot *é* o ecrã, no desktop é um estado que expira em 15 minutos e um link
partilhável para ele seria uma promessa falsa. Vai em **search params validados por Zod**, e não no
fragmento: o fragmento do convite existe para o segredo não chegar ao servidor, e pôr nele uma coisa
que não é segredo sugeria ao próximo leitor que era. O botão do fundo da lista passa a dizer
*Novo documento*. **Um desktop sem telemóvel à mão usa a zona de ficheiro**, e um escritório sem
ficheiro nenhum usa a terceira via que o ecrã já descreve hoje: a receção à mão. O QR é um atalho e
nunca o único caminho.

**Decisão 8 — "Não é uma fatura" não se recusa à entrada, e isso é desenho e não omissão.** O limite
recusa *formatos*; uma fotografia de um gato num JPEG válido é indistinguível de uma fatura mal
iluminada sem um classificador no caminho do pedido, e um classificador que recuse uma fatura
verdadeira é pior do que um que aceite um gato. Quem recusa é a extração — draft sem linhas, confiança
baixa — e a revisão humana, que é obrigatória (`CLAUDE.md`). O que o gate tem de afirmar não é "o gato
foi recusado" e sim que **um documento sem linhas revistas nunca chega a poder ser confirmado**, logo
nunca produz `StockMovement`.

**Os gates, e os dois que falham nos dois sentidos.** (1) **Ficheiro recusado**, em `pytest` com
`SimpleUploadedFile` e bytes escritos no teste, sem browser: PNG com extensão `.pdf` e PDF com
extensão `.png` são os dois recusados (prova que o sniff é a autoridade), um ficheiro com extensão e
magic correctos e `Content-Type` mentiroso é **aceite** (prova que o header do cliente é ignorado e
não validado), mais `.svg`, `.zip`, 0 bytes, 11 MiB e 20 páginas. (2) **Travessia de tenant**, sem
telemóvel: o desktop de A cria o slot, uma sessão de um membro de B anexa-lhe uma página, e a
asserção é 404 genérico **e** o slot ainda vazio — no padrão do `tests/test_rls_isolation.py`, com o
guarda de âmbito do `conftest.py` calado porque a leitura é dentro do âmbito. (3) **A lista fechada de
`tenant_scope_exempt` não cresce**, que é a prova em uma linha de que a ponte não abriu superfície
anónima. (4) **Nada de segredo no QR**: o payload é composto por uma função só e um teste afirma que
ele parseia como `<uuid>.<uuid>` e mais nada. (5) `curl -I` a `/media/<caminho>` dá 404 pelo proxy, no
job `stack`, ao lado do que já existe para `/static/`.

**Alternativas.** *A forma do convite — um token ao portador no QR* (32 bytes, SHA-256, uso único,
TTL curto): é a resposta reflexa e é a que esta ADR recusa, porque paga um segredo novo, um caminho
anónimo de escrita com `csrf_protect` à mão e uma tabela de tokens para comprar uma coisa que a sessão
do telemóvel já dá — e porque o uso único tornaria a fatura de duas folhas impossível. Fica como
**plano B com gatilho nomeado**: um cliente real cujos telemóveis não podem ter sessão (aparelho
partilhado na copa, dispositivo bloqueado); nesse dia entra com TTL de 2 minutos, uma página e a mesma
tabela. *Sessão no QR* — é a credencial ao portador na sua pior forma, e um QR num ecrã de escritório
é uma sessão afixada na parede. *Login no telemóvel a cada captura* — mata a feature, e é a objecção
do dono. *WebSocket ou SSE para o aviso* — secção 7 sem sinal, e um socket sem pedido não tem âmbito.
*Upload directo do browser para object storage com URL assinado* — tira a validação do sítio onde ela
é verificável e exige o object storage que a stack ainda não tem. *Renderizar o PDF no browser* —
decisão 5. *Rasterizar no `agents`* — deixava o ecrã de revisão sem imagem quando a extração falha, que
é precisamente quando ela é mais necessária. *Uma tabela de slots à parte* — um segundo ciclo de vida
a sincronizar com o do documento, para guardar um uuid que o documento já tem. *Duas rotas,
desktop e telemóvel* — ramificação por dispositivo, que a ADR 0008 recusou.

**Consequências.** Nenhuma tabela nova **desta** ADR; uma tabela da ADR da receção (`InvoiceDocument`)
que passa a ter de aceitar existir sem ficheiro, com `tenant_id` e política na migração que a cria,
como qualquer tabela de dados de um tenant. `APPEND_ONLY` não muda e as duas listas fechadas do
`test_db_roles.py` não mexem — é o sinal de que esta ADR não abriu excepção nenhuma. Entram
`python-magic`, `pypdf` e um rasterizador no `uv`, e o rasterizador é a única dependência nativa, só
alcançável pelo worker. Entra `MEDIA_ROOT` num volume partilhado por `backend` e `worker` no compose,
com o gatilho para trocar por S3/MinIO escrito: mais de uma réplica web, ou backups que tenham de
incluir os blobs — é setting (`STORAGES`) e não código. Duas tarefas Celery no `purchasing`
(normalizar, e a limpeza dos slots expirados), ambas com `tenant_id` obrigatório pelo `TenantTask`. Um
`ScopedRateThrottle` nos dois endpoints de escrita, porque cada página aceite custa uma rasterização e
uma chamada a LLM a jusante — é o primeiro sítio onde o limite de custo do `SECURITY.md` §6 aterra. No
frontend: uma biblioteca de QR (desenhado no cliente, porque o backend não conhece a origem da SPA —
decisão 1 do contrato de convites da ADR 0010), o `validateSearch` do `/receber/fotografar` ganha dois
uuids opcionais, e o `fotografar.tsx` perde o aviso de que não há câmara. O comentário de uploads do
`base.py` é corrigido: metade do que ele nomeia como futuro já existe no proxy.

**Consultar `domain-expert`**, e não é formalidade: isto é a entrada de faturas. Uma fatura em duas
folhas é um documento ou dois, e um rolo de cash & carry é um ou cinco; quanto tempo se guarda o
ficheiro original (obrigação fiscal, e o `SECURITY.md` §3 já diz que uma fatura traz NIF e morada); se
o QR/ATCUD do documento é fonte fiável para o cabeçalho antes de qualquer extração; e o que fazer com
um ficheiro cujo NIF de adquirente não é o do estabelecimento.

**O que o dono do produto tem de responder antes de se implementar.** (1) **Os telemóveis da equipa
têm a app e ficam com sessão?** É a única suposição desta ADR que vem de nós e não dele, e é a que
troca a decisão 1 pelo plano B. (2) **Quem diz que o documento está completo** — o telemóvel ("tirei
as duas"), o desktop ("já vi as duas") ou o relógio. (3) **Vale o QR o que custa?** O upload no
desktop é um validador; a ponte é um slot, um bloco novo, polling e um ecrã de telemóvel. Se o upload
resolver quase tudo, o QR é a fatia seguinte e não a primeira. (4) **Há um multifunções no
escritório?** Se há, *enviar a fatura por email para um endereço do estabelecimento* é uma terceira
entrada que pode valer mais do que a ponte e que não precisa dela — mas precisa de recepção de email,
que hoje não existe em sítio nenhum.

---

**Adenda de 2026-10-07 — a decisão 1 cai: o telemóvel não tem sessão, e a ponte passa a ter um
segredo.** As quatro respostas do dono chegaram no mesmo dia em que esta ADR foi escrita e respondem
às perguntas 1, 2 e 3; a 4 não propõe alternativa nenhuma (*"a parte do email também é preciso
configurar um SMTP"* — o `prod.py` não tem SMTP, e isso é outra sessão). A decisão 1 fica no texto
acima, porque o argumento dela continua a ser o certo **se** o pressuposto for verdadeiro; o que esta
adenda diz é que ele não é, e o que entra no lugar.

**Primeiro, a leitura da frase, porque me foi pedido que a contestasse se estivesse esticada — e está,
em parte.** *"Os telemóveis apenas servem de middle man"* é uma afirmação sobre o **fluxo da
fotografia**, não sobre autenticação: ele descreveu quem faz o quê com a imagem e não respondeu à
pergunta 1. E a resposta 2 dá ao telemóvel **mais** do que relé — um botão que declara um documento
completo é uma afirmação de negócio e não uma passagem de bytes. Lida à letra, a frase não diz "sem
sessão".

**A decisão 1 cai à mesma, e por duas razões que não dependem de o ler.** A primeira é que a
justificação dela era uma analogia que não se sustenta: *"o produto já lha exige: `contar` é
`campo: true`"*. Contar é uma tarefa marcada, feita por uma pessoa nomeada, no telemóvel dela, durante
minutos; receber é um recado de vinte segundos feito por quem está a segurar a caixa à porta das
traseiras. O predicado `campo` da ADR 0009 descreve **ecrãs desenhados para o telemóvel**, não
**aparelhos inscritos no produto**, e a decisão 1 leu-o como a segunda coisa. A segunda razão é
medível e está no repositório: `/receber/fotografar` é filha de `rotaDaApp`
(`frontend/src/routes/receber.tsx`), que carrega o `beforeLoad` que exige sessão (ADR 0008 e 0010). O
QR da decisão 1 aponta um telemóvel sem sessão para dentro do shell — ele aterra em `/entrar`, e os
dois uuids do slot têm de sobreviver ao login para voltarem, o que é um *login com retorno* que
ninguém escreveu e que o ramo público da ADR 0010 deliberadamente não tem. "Precisa de uma sessão, uma
vez" nunca foi *uma vez*: era *uma vez, mais um fluxo que não existe*, e a decisão 1 cotou os dois a
zero. A resposta 3 — *"tem de ter as duas opções disponíveis independentemente de qualquer coisa"* —
torna esse beco permanente e sempre visível no ecrã.

**Decisão 1a — a ponte passa a ser a forma do convite, com outro nome: `<uuid-do-tenant>.<token>` no
fragmento.** O uuid é **argumento** e escolhe o âmbito; o token é o segredo, verificado **dentro** do
âmbito que o uuid abriu, contra uma coluna com política normal. É a ADR 0010 à letra, com o QR no
lugar do email: *o link escolhe o âmbito, a política concede-o*. O uuid do documento **sai** do
payload — com um token, o id da linha é redundante, e um segundo identificador é mais uma coisa para
validar e mais uma para vazar; a linha encontra-se pelo `capture_token_hash` e por mais nada, o que
tira ao portador o id que ele poderia trocar. O token é **32 bytes de `secrets.token_urlsafe`**
(43 caracteres), guardado **só** como **SHA-256** e nunca em claro, com `UniqueConstraint` no hash —
as três coisas pelas razões já escritas no `Invitation`: 256 bits não se adivinham por dicionário,
logo o factor de trabalho de um KDF não compra nada; o que o hash compra é que um `pg_dump`, um backup
ou o `stockflow_owner` não conseguem usar um slot vivo; e a unicidade global é a rede contra o mesmo
token em dois estabelecimentos. O payload tem **80 caracteres**, o mesmo `LIMITE_DO_FRAGMENTO` do
convite e a mesma função de partir, e o QR leva `${origin}/capturar#<fragmento>` composto **no
cliente**, porque o backend não conhece a origem da SPA. **No fragmento e não em search params**, o que
inverte essa parte da decisão 7 pela sua própria razão: ela punha o slot na query *por não ser
segredo*; agora é, e um segredo em search params entra no log de acesso do proxy e no `Referer`. O
corpo do pedido leva o **fragmento inteiro e opaco**, nunca `tenant_id` + `token` separados — o formato
do segredo tem uma definição e ela fica no servidor (ADR 0010).

**Decisão 1b — o que o portador consegue, e sobretudo o que não consegue.** Consegue duas coisas:
**anexar uma página a um documento**, N vezes enquanto o token viver, e **fechá-lo**. Não consegue
**ler coisa nenhuma** — a ponte não tem `GET`, e isso é estrutural e não uma omissão: as respostas dos
dois POST dizem `{paginas, limite}` e `{fechado, paginas}`, sem nome de estabelecimento, sem
fornecedor, sem linhas, sem o nome do ficheiro do outro lado. Não consegue listar documentos (não
existe colecção para ele). Não consegue alcançar **outro documento do mesmo tenant**, porque não há id
em lado nenhum para trocar. Não consegue alcançar **outro tenant**: forjar o uuid escolhe um âmbito
onde nenhum `capture_token_hash` existe, e a leitura devolve zero linhas. E não consegue **confirmar
linhas**: a confirmação é `purchasing.confirm_receipt`, endpoint normal com sessão, âmbito e revisão
humana obrigatória — **nenhum caminho do portador chega ao ledger**. O contrato:

```
POST /api/v1/captura/paginas   anónimo · dispensado de âmbito · abre o do QR · csrf_protect · multipart
  CapturaDePaginaIn  { fragmento: str(<=80), ficheiro: imagem }
  CapturaDePaginaOut { paginas: int, limite: int }
POST /api/v1/captura/fechar    anónimo · dispensado de âmbito · abre o do QR · csrf_protect · JSON
  FecharCapturaIn    { fragmento: str(<=80) }
  FecharCapturaOut   { fechado: true, paginas: int }
```

Do lado do desktop, um POST autenticado e com âmbito abre o slot e devolve o `fragmento` **uma vez**,
como o `ConviteCriadoOut`; repeti-lo **roda o token** e mata o QR anterior, que é o `reenviar_convite`
e é exactamente o caminho de recuperação da resposta 2 ("falta uma página, o desktop reabre"). O path
desse endpoint é da ADR da receção, que é quem desenha o `InvoiceDocument`. **Quem pode abri-lo: qualquer
membro activo** (`IsAuthenticated, PertenceAoTenant`, sem `TemPapel`) — receber mercadoria é trabalho
de quem está lá, e o que torna isto aceitável é o raio de explosão da decisão 1d, não o papel. A Q7
continua por responder e não é aqui que se responde.

**Decisão 1c — o relógio é um só, o uso não é único, e o que mata o token são três coisas.** Uso único
está errado por duas respostas ao mesmo tempo: a 2 pede várias páginas no mesmo slot e a 3 põe o QR
sempre à vista. Logo o token é **multi-escrita dentro de um documento** e o que morre é outra coisa:
**(i) o "Terminei"**, que é a operação de uso único desta ponte — depois dele o `WHERE` da escrita de
páginas deixa de casar; **(ii) o relógio**, `capture_expires_at`, a **15 minutos**, que é o **mesmo**
relógio do `aguarda_captura`/`expirado` da decisão 2 e não um segundo — dois relógios divergem, e um
slot `expirado` no ecrã do desktop que ainda aceitasse páginas seria a pior divergência possível;
**(iii) a reabertura**, que roda o hash. Há ainda um teto que não mata o token mas limita o estrago:
**10 páginas por slot**, simétrico ao teto de páginas de PDF da decisão 4. As condições vivem no
`WHERE` da escrita e nunca num `if` em Python, como o `_marcar_aceite` — duas capturas em corrida
resolvem-se na base de dados. **Uma segunda leitura do mesmo QR** enquanto ele vive dá a **mesma**
página de captura e pode anexar páginas: é a consequência deliberada de não ser uso único, e é útil —
dois telemóveis a fotografar um rolo de cinco folhas caem no mesmo documento. Depois do "Terminei" ou
dos 15 minutos, dá **uma** recusa: `400 captura_invalida`, um código e um corpo para as cinco
situações (payload mal formado, uuid forjado, token inexistente, expirado, fechado), construída por
**uma** função, como o `_convite_invalido()` — e com o código no log, que é onde a distinção serve a
quem opera. O bloco do desktop deixa de mostrar um QR morto aos 15 minutos e oferece abrir outro.

**Decisão 1d — o custo de ser fotografável na sala, sem o encolher.** A decisão 1 respondia a esta
objecção tirando o segredo; já não há segredo para tirar, logo a resposta tem de ser o raio de
explosão. **Quem pode abusar:** qualquer pessoa com linha de vista para o ecrã enquanto o bloco está
aberto — um cliente ao balcão, o motorista do fornecedor, alguém numa chamada com o ecrã partilhado,
uma câmara de videovigilância do escritório, um ex-empregado. Nenhuma pertença é precisa. **O que
ganha:** até 10 imagens à escolha dele dentro de **um** documento de **um** estabelecimento, durante
no máximo 15 minutos, mais o poder de o fechar. **O pior caso concreto:** fotografa o QR do outro lado
do balcão e, antes de a pessoa acabar, envia 10 imagens suas e carrega em "Terminei" — e as três
consequências são de naturezas diferentes. A barata é o dinheiro: 10 rasterizações e 10 chamadas a
LLM debitadas a este tenant. A desagradável é humana: quem revê vê conteúdo que não fotografou, e no
caso de uma imagem chocante isso é dano a uma pessoa e não um problema de dados. A perigosa é a
plausível: 10 fotografias de uma fatura **verdadeira mas de outra compra** entram na fila de revisão
parecendo legítimas — e só produzem `StockMovement` **se um humano as aprovar**, que é a razão pela
qual a revisão obrigatória da decisão 8 passa a ser a afirmação principal desta ADR e não um rodapé.
**O que não está no pior caso, e vale dizê-lo:** nada é lido. Um token de convite roubado **é** uma
pertença; um token de captura roubado é uma escrita num bloco de rascunho. **Risco residual nomeado:
um QR fotografado na sala é uma escrita naquele documento**, e o que o limita é o relógio, o teto de
páginas, o "Terminei", a rotação na reabertura e a revisão humana — mais nada. Ninguém deve ler esta
ADR e ficar a pensar que o QR é secreto.

**Decisão 1e — CSRF nos dois, e aqui o decorador é o único cinto e não o segundo.** Os dois endpoints
novos são exactamente a forma que o `SECURITY.md` §5 descreve: **anónimos e de escrita**. O `as_view()`
do DRF embrulha-os em `csrf_exempt` e o `SessionAuthentication` só verifica o token quando **encontra**
utilizador na sessão, o que neste caminho nunca acontece — logo nascem sem protecção nenhuma. Levam
`@method_decorator(csrf_protect, name="dispatch")`, como o `LoginView` e a `AtivacaoView`, e o ataque
não é teórico: é um `<form>` noutra origem a fazer o browser de quem tem o ecrã de captura aberto
enviar uma página escolhida pelo atacante, ou carregar no "Terminei" antes de as páginas verdadeiras
chegarem — uma negação que se parece com um defeito. **E há uma diferença em relação ao `/auth/`:** a
página não pode levar `parser_classes = [JSONParser]`, porque o corpo **é** um ficheiro. A segunda
camada que protege o login — um `<form>` de outra origem faz `multipart` sem preflight e JSON não — não
existe aqui, portanto o `csrf_protect` é a única coisa entre este endpoint e um formulário remoto. O
`fechar`, que não leva ficheiro, fica com `JSONParser` e com os dois cintos. O token de CSRF chega ao
telemóvel pelo `GET /auth/sessao`, que já leva `ensure_csrf_cookie` (ADR 0010) e que a rota de captura
chama ao montar **para isso e para mais nada** — a resposta é descartada, diz `estado: anonimo` e não
revela tenant nenhum; inventar um segundo mecanismo de CSRF era ter duas fontes para a mesma coisa. O
preço fica nomeado: um telemóvel com cookies bloqueados não envia páginas, tal como já não faz login.
Do outro lado, o POST do desktop que **cria o segredo** leva `csrf_protect` apesar de ser autenticado,
pelo argumento do `EstabelecimentoView`: é a escrita que cunha uma credencial ao portador, e no dia em
que alguém acrescentar uma autenticação por token a diferença entre as duas views é esta linha.

**Decisão 1f — a lista fechada cresce em duas entradas, e a propriedade que fica no lugar do gate
perdido.** A resposta à pergunta "pode a ponte ser a forma do `ativar` e não crescer?" é: a forma do
`ativar` é a certa, mas ela **não** evita crescer — o próprio `api/v1/auth/ativar` está na lista. O que
a forma do `ativar` evita é a coisa que importa, e a decisão 1 estava a confundir as duas. O
`fora_do_admin` do `tests/test_rls_isolation.py` ganha **exactamente duas** entradas,
`api/v1/captura/fechar` e `api/v1/captura/paginas`, e o prefixo é deliberado: o docstring do
`accounts/views.py` diz que a fronteira entre as duas famílias é o `/auth/`, e essa frase fica
**devida de correcção** — passam a ser dois prefixos, `/auth/` e `/captura/`, e o segundo lê-se como o
que é. No lugar do gate perdido ficam duas propriedades, as duas verificáveis: **(1) o `SEM_POLITICA`
do `test_db_roles.py` não mexe** — nenhuma tabela passa a ser legível sem âmbito, porque a ponte abre
o âmbito a partir do uuid do QR e lê o slot lá dentro, que é a razão inteira de a decisão da ADR 0010
existir; e **(2) estas são as duas únicas dispensas do repositório que não leem nada** — sem `GET`,
sem colecção, sem id no corpo —, o que é uma superfície mais estreita do que qualquer uma das seis de
`/auth/`, e afirma-se percorrendo as duas classes e exigindo que só exponham `post`.

**Decisão 1g — o "Terminei" é endpoint próprio, com o mesmo token, e o relógio é a rede de quando ele
nunca chega.** Endpoint próprio e não uma flag na última página: fechar é uma intenção distinta e tem
de ser possível **sem** enviar página nenhuma (a pessoa já tirou as duas e só depois decide). A
assimetria das duas escritas é de propósito — a página exige
`capture_closed_at IS NULL AND capture_expires_at > now()`; o fechar exige só o relógio, o que o torna
**repetível dentro do TTL** e faz com que uma retentativa numa rede má devolva 200 em vez de uma
recusa sobre uma operação que afinal correu bem. Fechar duas vezes não compra nada a ninguém. **Se o
"Terminei" nunca chegar** — bateria, a pessoa afasta-se —, as páginas já enviadas **ficam**, porque são
páginas verdadeiras de um documento verdadeiro, e aos 15 minutos o slot é `expirado` por derivação,
sem escrita nenhuma. Quem fecha então é o **desktop**, no ecrã de revisão, com sessão e âmbito: a
resposta 2 deu ao telemóvel o botão, não a exclusividade, e sem isto uma bateria descarregada deixava
um documento encravado para sempre. Zero páginas e nunca fechado continua a ser o slot invisível da
decisão 2, varrido pela tarefa de limpeza.

**Decisão 7, corrigida pela resposta 3 — as duas opções sempre, e uma rota pública nova que não é uma
segunda versão da primeira.** `/receber/fotografar` continua a ser **uma** rota, com a zona de ficheiro
**e** o bloco do QR, sem ramificar por dispositivo (ADR 0008). O que cai é o `hidden md:block`:
*"independentemente de qualquer coisa"* não convive com um breakpoint, e o dono tem razão por um motivo
que a decisão 7 não viu — um tablet de balcão em retrato é mais estreito que `md` e é precisamente o
sítio onde se quer o QR para um segundo telemóvel. O que varia com a largura passa a ser **ordem e
ênfase**, que é layout e não routing. **Um desktop sem telemóvel à mão** vê a zona de ficheiro
primeiro, o bloco do QR a seguir e a terceira via que o ecrã já descreve (a receção à mão). **Um
telemóvel com sessão que abra a rota directamente** vê as duas, usa a câmara pela zona de ficheiro
(`capture="environment"`) e ignora um QR que aponta para si mesmo — inútil, inofensivo, e o preço de
"sempre as duas". **Um telemóvel sem sessão não abre essa rota de todo**: abre `/capturar#<fragmento>`,
**terceiro filho do `rotaPublica`**, ao lado de `/entrar` e `/ativar`, fora do `AppShell` e sem
`beforeLoad` — um botão, nenhuma navegação, nenhum seletor de estabelecimento. É a consequência que a
decisão 7 não podia ter, porque assumia o telemóvel dentro do shell. E o `validateSearch` do
`/receber/fotografar` **não** ganha uuid nenhum, ao contrário do que as consequências acima dizem.

**O que mais muda, e o que não.** **Permissões:** passam a existir duas classes de endpoint, e a da
ponte não tem classe de permissão nenhuma a exprimi-la — `AllowAny` mais o token verificado no service,
como a `AtivacaoView`; inventar um `TemTokenDeCaptura` punha autorização na camada das permissões
quando a verificação precisa de uma leitura dentro de um âmbito que o middleware não abriu.
**`has_object_permission`:** desaparece do caminho do portador, e na direcção certa — a decisão 1
recebia um uuid de documento, logo era uma view "que recebe um `pk`" e o `SECURITY.md` §5 exigia a
comparação; sem id no path e sem id no corpo não há objecto endereçável, como no `PreferenciasView` e
no `EstabelecimentoView`, e além disso não há `request.tenant` com que comparar. O `GET` do documento
no desktop **recebe** pk e mantém o `PertenceAoTenant`. **O throttle de 20/min:** sobrevive como
segundo cinto e **deixa de ser o teto de custo**, que é a correcção importante — o `ScopedRateThrottle`
sem utilizador passa a contar por IP, e um atacante não partilha IP com a vítima, enquanto os
telemóveis do restaurante partilham um só. O teto de custo real é **o teto de páginas por slot**.
Fica nomeado o que falta: o `SECURITY.md` §6 pede limite por utilizador/dia e aqui não há utilizador;
a forma que encaixa é um teto **por tenant/dia**, devido e não construído nesta ADR. Nenhuma zona nova
no Caddy — ela limitaria o que o teto de páginas já limita; o gatilho para a abrir é subir esse teto.
**O evento depois da normalização (decisão 6):** não muda, e ganha uma armadilha a nomear — a tarefa
leva `tenant_id` **da linha do documento** e nunca de `request.tenant`, que neste caminho não existe;
e a rasterização continua a ser **por página à chegada** e não no fecho, senão o polling da decisão 3
não tem nada para mostrar. **As decisões 2, 3, 5 e 8 ficam intactas**; a 4 fica intacta e mais
importante, porque agora o upload anónimo é o pior sítio do sistema para correr um parser nativo — e
por isso a ponte aceita **só imagens** (`.jpg .jpeg .png .webp`), sem PDF, o que tira o `pypdf` do
caminho anónimo por inteiro; PDF entra pela zona de ficheiro, que é autenticada. O `InvoiceDocument`
ganha três colunas (`capture_token_hash` único e nulável, `capture_expires_at`, `capture_closed_at`) e
continua sem tabela nova; o `APPEND_ONLY` continua a não mexer.

**Os gates, sem browser e sem telemóvel.** Os cinco de cima continuam, com o (3) e o (4) reescritos, e
entram quatro. **(a) Não escreve noutro tenant:** o slot é de A e o POST leva o uuid de B com o token
de A — `400 captura_invalida` **e** o slot de A ainda vazio; e o simétrico, para o teste não passar por
vacuidade. **(b) Não serve depois de expirar:** com `capture_expires_at` posto no passado, a mesma
recusa e a contagem de páginas intacta. **(c) Não serve depois do "Terminei":** fechar, tentar anexar,
mesma recusa, mesma contagem — e o fechar repetido dentro do TTL devolve 200. **(d) Não serve para ler
nada:** duas metades — as duas classes só expõem `post`, percorridas no teste, e os **cinco** corpos de
recusa são byte a byte iguais, pelo precedente do `_convite_invalido()`. Mais o CSRF nas duas metades
com `enforce_csrf_checks=True` nos dois endpoints, confirmado por mutação como em
`tests/test_convites.py`; mais as duas listas fechadas a mexerem em sentidos declarados — o
`fora_do_admin` ganha duas entradas nomeadas, o `SEM_POLITICA` e o `APPEND_ONLY` não mexem. O gate (4)
de cima inverte-se de conteúdo e mantém-se de forma: o payload parseia como `<uuid>.<token>` e mais
nada, composto por uma função só.

**Continua a ser preciso o `domain-expert`**, e a resposta 2 acrescenta-lhe uma pergunta: se o
documento pode ser **reaberto depois de fechado** para mais páginas — que é o caminho de recuperação
que o dono propõe — então "fechado" não é terminal para o documento, só para aquele token, e isso toca
no que um documento *é* quando a revisão já começou. Continua em aberto, e agora com dentes, se uma
fatura de duas folhas é um documento ou dois e se um rolo de cash & carry é um ou cinco: com a resposta
2, quem traça essa fronteira é o dedo de quem carrega no "Terminei".

---

**Adenda 2, de 2026-10-07 — a adenda 1 é revogada e a decisão 1 do corpo volta a valer: o *login com
retorno* existe, está no repositório desde 2026-10-06, e o dono escolheu pagar o login.** O registo
desta ADR tem três camadas e fica com as três à vista: o **corpo** desenhou a ponte sem segredo; a
**adenda 1** trocou-a por um token ao portador num caminho anónimo; esta **adenda 2** revoga a adenda 1
e restaura o corpo. A camada do meio caiu por uma razão de facto e não de gosto — a premissa que ela
própria chamou *"a razão medível no repositório"* é falsa, e mediu-se.

**O que estava errado, ficheiro a ficheiro.** A adenda 1 escreveu que o QR da decisão 1 aponta um
telemóvel sem sessão para dentro do shell, que ele aterra em `/entrar`, e que os dois uuids "têm de
sobreviver ao login para voltarem, o que é um *login com retorno* que ninguém escreveu". Está escrito,
e foi construído exactamente para este caso:

- `frontend/src/routes/destino.ts` — `destinoDoRegresso(href)` tem ficheiro próprio desde 2026-10-06 e
  o docstring abre com "Para onde voltar depois de entrar"; carrega **caminho e search params**
  (`/stock?loja=…`), com a razão escrita (*"voltar a `/stock` sem o filtro era voltar a outro ecrã"*) e
  `replace: true` para o botão de voltar não cair num ciclo;
- `frontend/src/routes/app.tsx:116` — o `beforeLoad` da `rotaDaApp` redirecciona com
  `search: destinoDoRegresso(location.href)`. É o portão que a adenda 1 citou, a fazer o oposto do que
  ela lhe atribuiu;
- `frontend/src/routes/entrar.tsx:54` — `redirect({ href: alvoDoRegresso(search.destino,
  location.hash), replace: true, throw: true })`, que carrega **também o fragmento**, e o docstring
  di-lo por extenso: *"o `/ativar` manda-o a `/entrar?destino=/ativar#<fragmento>`"*;
- `frontend/src/routes/busca-de-entrada.ts` — o `destino` é validado contra redirecção aberta (começa
  por `/`, não começa por `//`, não é `/entrar`) com `max(512)`, logo um caminho de ~90 caracteres com
  dois uuids passa com folga e sem alterar o schema.

O fluxo existe, preserva o fragmento, e **o link de convite já o usa**. A ponte precisa da mesma forma
com o QR no lugar do email. *"Era uma vez, mais um fluxo que não existe"* media a zero um fluxo que
está escrito, testado e em uso — e era essa a frase que fechava a porta. A resposta 3 do dono (*"as
duas opções disponíveis independentemente de qualquer coisa"*) também não exige que a segunda opção
seja anónima: exige que esteja no ecrã, e isso é a decisão 7 corrigida, que sobrevive.

**Decisão 2a — a revogação, ponto por ponto, e os três detalhes que sobrevivem.**

- **1a** (token no fragmento, `capture_token_hash`, payload de 80 caracteres) — **revogada**. Nenhum
  segredo novo, nenhuma coluna de hash, nenhum `LIMITE_DO_FRAGMENTO`.
- **1b** (`POST /api/v1/captura/paginas` e `/captura/fechar`, anónimos) — **revogada**: os dois
  endpoints **não existem**. As escritas da ponte são endpoints do documento, com sessão, âmbito e
  CSRF pelo caminho de sempre, e o path continua a ser da ADR da receção, como a 1b já dizia do lado
  do desktop.
- **1c** (relógio do token, `400 captura_invalida`, rotação na reabertura) — **revogada**. O relógio
  volta a ser **um só e derivado** (decisão 2: 15 minutos desde `created_at`); não há token para rodar
  nem recusa nova para construir.
- **1d** (o raio de explosão de um QR fotografável) — **revogada como decisão, mantida como leitura**:
  é a descrição correcta do custo do plano B, e é por ela que o plano B é plano B. Com a decisão 1 de
  pé, quem fotografa o QR sem pertença recebe o ecrã de entrada e para aí; quem o fotografa **com**
  pertença já podia fazer upload por si.
- **1e** (`csrf_protect` como único cinto, `/auth/sessao` só para o cookie) — **revogada por não ter
  sujeito**: sem endpoint anónimo de escrita não há o caso que ela resolvia. A regra geral que ela
  invoca continua verdadeira no repositório; deixa de se aplicar aqui.
- **1f** (o `fora_do_admin` cresce em duas entradas) — **revogada**, e é a inversão que mais importa:
  a lista fechada do `tests/test_rls_isolation.py` fica **sem crescer em nenhuma entrada**. O
  `fora_do_admin` continua a ser as **oito** de hoje — as seis de `/auth/` mais `healthz` e `readyz`.
  O `com_ambito` da mesma asserção ganhará o que a ADR da receção lhe trouxer, e isso não é uma
  dispensa: é o default.
- **1g** (o "Terminei" como endpoint do portador) — **revogada na forma, intacta na substância**:
  fechar continua a ser intenção própria, possível sem enviar página, repetível, e o desktop também o
  pode fazer. É a resposta 2 do dono e não dependia do token. As colunas de captura saem; se existe um
  marcador de "completo" é da ADR da receção e da Q7, não desta.
- **A correcção à decisão 7 — sobrevive inteira**, e é o melhor achado da adenda 1: cai o
  `hidden md:block`, porque um tablet de balcão em retrato é mais estreito que `md` e é precisamente
  onde mais se quer o QR. O que varia com a largura é **ordem e ênfase** — layout, não routing (ADR
  0008). O resto desse parágrafo cai com o `/capturar`.
- **A crítica à analogia do `campo: true` — sobrevive como nota sobre o custo**: o predicado `campo`
  da ADR 0009 descreve **ecrãs desenhados para telemóvel**, não **aparelhos inscritos no produto**, e
  a decisão 1 leu-o como a segunda coisa. Não é uma impossibilidade — é o preço, e o preço foi
  escolhido com conhecimento (decisão 2c).
- **Um terceiro, e marcado como fraco:** o **teto de 10 páginas por documento**. Deixa de ser teto de
  custo (com utilizador, o `ScopedRateThrottle` volta a contar por utilizador, que é o que o
  `SECURITY.md` §6 pede) e fica como **limite de produto**, simétrico ao teto de 10 páginas de PDF da
  decisão 4: um ficheiro e um slot têm o mesmo teto, e um rolo mais comprido é uma pergunta para o
  `domain-expert`, não um limite a subir aqui.

As duas afirmações do corpo que a adenda 1 revogou **voltam a valer sem emenda**: *"a superfície
dispensada de âmbito não cresce em uma entrada, e isso é o gate"*, e *"o `validateSearch` do
`/receber/fotografar` ganha dois uuids opcionais"*.

**Decisão 2b — o QR leva um caminho da app com os dois uuids em search params; a rota `/capturar`
deixa de existir.** O argumento da decisão 7 volta intacto — o fragmento existe para um segredo não
chegar ao servidor, e aqui não há segredo — e **ganha uma confirmação medida**: o `alvoDoRegresso`
(`frontend/src/routes/entrar.tsx:93`) e o `alvoDepoisDeEntrar`
(`frontend/src/features/accounts/screens/entrar.tsx:121`) arrastam o fragmento **só para o `/ativar`**,
com a razão escrita nos dois sítios (*"o fragmento é um segredo, e levá-lo para qualquer outro destino
deixava um token na barra de endereço"*). Pôr o slot no fragmento obrigava a alargar essa lista nos
**dois** ficheiros para um payload que não é segredo — o sinal errado ao próximo leitor, e duas linhas
que ninguém precisa de escrever. Em search params o retorno funciona **sem uma linha nova**.

Uma correcção ao corpo, por coerência interna: a decisão 1 escreve o payload como
`<uuid-do-tenant>.<uuid-do-documento>`, que é a forma do convite herdada por hábito. **Sem segredo não
há razão para concatenar** — são dois campos com nome, validados por Zod, e o ponto desaparece. O QR
leva `${origin}/receber/fotografar?estabelecimento=<uuid>&documento=<uuid>`, composto no cliente
(o backend não conhece a origem da SPA — ADR 0010). `estabelecimento` e não `tenant` porque é a palavra
do produto, e porque o **nome** de um search param é partilhado por toda a árvore de rotas (medido no
`busca-de-rececoes.ts`). Os dois uuids entram num schema **próprio** do `/receber/fotografar` que
estende o `buscaDeRececoesSchema` em vez de o alterar: as três rotas de `/receber` partilham-no hoje, e
alargá-lo punha dois uuids no tipo da lista e do detalhe.

O uuid do estabelecimento continua a ser **argumento e não credencial**, e agora tem trabalho: se o
âmbito activo da sessão do telemóvel não é o do QR, o ecrã **pede a troca** com um toque, pelo
`POST /auth/tenant-ativo` que já existe, e nunca a faz em silêncio — a sessão escolhe o âmbito (ADR
0007), e uma troca de âmbito disparada por um parâmetro de URL era um efeito secundário de uma
navegação. Sem pertença, a troca recusa genericamente. Quem tem um estabelecimento só nunca vê o caso.

**Decisão 2c — o custo que fica, quem o paga, e o gatilho que reabre isto.** A escolha foi posta ao
dono com os dois custos à frente — **um login por telemóvel** contra **um segredo de 15 minutos num
ecrã fotografável** — e ele escolheu *"Login uma vez no telemóvel"*. A frase anterior (*"os telemóveis
apenas servem de middle man"*) era sobre o fluxo da fotografia e não sobre autenticação: nessa parte a
contestação da adenda 1 estava certa e fica de pé. O custo é real e tem um caso concreto: **um
telemóvel partilhado na copa onde ninguém tem conta.** Quem o usa lê o QR, aterra em `/entrar` e
**para aí** — não há ecrã para lhe mostrar, e é deliberado. As saídas desse dia são três, por ordem de
custo: o upload no desktop (decisão 4, que não precisa de ponte), a receção à mão (a terceira via que o
ecrã já descreve) ou dar conta à pessoa, que custa um convite. **O plano B fica revogado mas
disponível**, e o desenho dele está escrito por inteiro na adenda 1 — é o valor que ela mantém, e não é
pequeno: no dia do gatilho não há nada para desenhar. **O gatilho, nomeado:** um cliente real em que o
aparelho que fotografa **não pode** ter sessão (telemóvel partilhado sem conta por pessoa, dispositivo
bloqueado por política de MDM) **e** em que as três saídas acima já foram tentadas. Nesse dia entra a
adenda 1 como está — relógio de 15 minutos, teto de páginas, revisão humana a fazer o trabalho que a
decisão 1d descreve. Até lá, nenhuma linha dela é construída.

**Decisão 2d — a correcção devida ao `apps/accounts/views.py` é retirada.** A adenda 1 deixou devida a
emenda do docstring que diz *"Duas famílias, e a fronteira entre elas é o `/auth/`"*, porque
`/captura/` ia ser um segundo prefixo dispensado. Com `/captura/` a não existir, a frase está **certa
como está** e a correcção não fica devida a ninguém.

**Os gates, reduzidos ao que faz sentido sem token.** Os cinco do corpo voltam todos; os quatro da
adenda 1 (a, b, c, d) **saem**, porque mediam endpoints que não existem, e o CSRF volta a ser o que
cobre qualquer escrita autenticada em vez de um gate próprio.

1. **Ficheiro recusado** — intacto, e agora cobre o caminho inteiro: sem caminho anónimo não há uma
   allowlist mais estreita a manter em dois sítios, e o `pypdf` não tem um segundo lugar onde não deva
   correr.
2. **Travessia de tenant** — é a resposta ao uuid de outro tenant no QR, e é o gate de cima sem
   emenda: o desktop de A abre o slot, uma sessão de um membro de B faz o POST da página com o uuid do
   documento de A, e a asserção é **404 genérico e o slot de A ainda vazio**, no padrão do
   `tests/test_rls_isolation.py`, com o guarda de âmbito do `conftest.py` calado porque a leitura é
   dentro do âmbito. Mais o simétrico (a sessão de A anexa, a contagem sobe), para não passar por
   vacuidade. **Sem browser e sem telemóvel:** dois clientes de teste, duas sessões, dois POST. E um
   uuid **inexistente** dá a **mesma** resposta que um de outro tenant — corpo igual, byte a byte, pelo
   precedente do `_convite_invalido()`; é asserção e não acaso, porque é a diferença entre as duas
   respostas que diria a um estranho que o documento existe.
3. **O `fora_do_admin` não cresce** — volta a ser o gate principal e é mais forte do que era:
   afirma-se comparando a lista contra as oito entradas de hoje, num teste que já falha nos dois
   sentidos. É a feature que mais se pareceria com uma dispensa nova, e não abre nenhuma.
4. **Nada de segredo no QR** — invertido de volta, com a forma adaptada: o URL é composto por **uma**
   função, e o teste afirma que ele dá `/receber/fotografar` com **exactamente dois** search params, os
   dois uuid, **sem fragmento** e sem terceiro campo. Nenhuma string opaca de 43 caracteres aparece no
   payload, e é isso que se assere.
5. `curl -I` a `/media/<caminho>` dá 404 pelo proxy — intacto.

E as **três** listas fechadas ficam quietas: o `fora_do_admin` do `test_rls_isolation.py`, o
`SEM_POLITICA` e o `APPEND_ONLY` do `test_db_roles.py`. Nenhuma cresce, e é o resumo desta adenda em
uma linha.

**Continua a ser preciso o `domain-expert`**, e nada disto lhe tira perguntas: a fatura de duas folhas,
o rolo de cash & carry, a retenção do original, o ATCUD como fonte do cabeçalho e o NIF de adquirente
errado. A pergunta que a adenda 1 lhe acrescentou — se um documento pode ser **reaberto depois de
fechado** — **fica**, porque sobrevive à revogação: quem fecha passa a ser uma pessoa autenticada em
vez de um portador, e a fronteira continua a ser o dedo dela.
