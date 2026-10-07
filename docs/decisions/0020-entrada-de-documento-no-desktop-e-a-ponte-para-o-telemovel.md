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
