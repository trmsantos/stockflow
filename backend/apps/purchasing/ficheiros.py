"""O que os bytes dizem, e o nome que o ficheiro leva no disco.

Módulo **puro**: não toca na base de dados, não importa models, e não corre
decoder nativo nenhum. É por isso que pode ser chamado de dentro do pedido — a
linha que separa as duas metades da decisão 4 da ADR 0020 é exactamente esta:
*nenhum decoder nativo de imagem ou de PDF corre no processo que serve pedidos*.
Aqui compara-se prefixos de bytes e conta-se ocorrências de um token; Pillow e um
rasterizador só existem no worker (e hoje não existem em sítio nenhum — ver
`rasterizacao.py`).

## Porque é que não há `python-magic`

A ADR 0021 herdou-o da ADR 0020. Trá-lo significa trazer o `libmagic` para a
imagem — uma dependência nativa, num Dockerfile multi-stage, para distinguir três
famílias de ficheiro cujos bytes mágicos cabem em três linhas. Não se paga por
isto. O que se perde está nomeado: o `libmagic` reconhece centenas de formatos e
isto reconhece **três**, logo a lista é fechada por construção e um formato novo
é um diff aqui.

## O `Content-Type` do cliente é ignorado, não validado

É a decisão 4 da ADR 0020 à letra, e a diferença importa: um ficheiro com bytes
de PDF e `Content-Type: text/plain` é **aceite** (o header do cliente não é
prova de nada), e um `.exe` renomeado para `.pdf` é **recusado** (os bytes são a
autoridade). As duas direcções são testes.
"""

from __future__ import annotations

import re
from uuid import UUID, uuid4

__all__ = [
    "BYTES_PARA_DECIDIR",
    "EXTENSAO_POR_TIPO",
    "TAMANHO_MAXIMO_DO_FICHEIRO",
    "TIPOS_ACEITES",
    "caminho_da_imagem",
    "caminho_do_ficheiro",
    "paginas_num_pdf",
    "tipo_real",
]

#: Os bytes mágicos de cada família aceite. **Lista fechada**, e a ordem não
#: importa porque os três prefixos são mutuamente exclusivos.
#:
#: Falta o WEBP, que a allowlist da decisão 4 da ADR 0020 incluía
#: (`.jpg .jpeg .png .webp .pdf`). Sai por decisão desta sessão, não por
#: esquecimento: um WEBP é `RIFF....WEBP` (o quarto ao sétimo byte são o tamanho,
#: logo o prefixo não é contíguo) e nenhuma câmara de telemóvel o produz por
#: omissão. Entra no dia em que um cliente real o enviar — é uma entrada nesta
#: tabela e uma linha no teste.
BYTES_MAGICOS: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)

#: Os tipos aceites, derivados da tabela acima: uma segunda lista escrita à mão
#: divergiria dela no primeiro acrescento.
TIPOS_ACEITES: tuple[str, ...] = tuple(tipo for _, tipo in BYTES_MAGICOS)

#: A extensão que cada tipo leva **no nome gerado**. Nunca a extensão que o
#: cliente enviou: o nome no disco deriva do que os bytes dizem (SECURITY.md §4).
EXTENSAO_POR_TIPO: dict[str, str] = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
}

#: Quantos bytes se leem para decidir o tipo. O prefixo mais longo tem 8 bytes;
#: 16 dá folga sem ler o ficheiro inteiro.
BYTES_PARA_DECIDIR = 16

#: O teto de tamanho de **um** ficheiro, em bytes: **11 MiB, estritamente abaixo
#: dos 12 MB do proxy**, e é a ordem entre os dois que importa.
#:
#: O `docker/caddy/proxy.Caddyfile` impõe `request_body { max_size 12MB }`, e a
#: duplicação aqui é de propósito por duas razões. Em desenvolvimento não há
#: proxy à frente do Django — o `runserver` e o `pytest` falam directamente com a
#: app —, logo sem este número não haveria teto nenhum no sítio onde a feature se
#: constrói. E em produção **a frase que uma pessoa lê tem de ser a desta
#: aplicação**: o Caddy recusa com um corpo que não é JSON, e um formulário não
#: tem o que mostrar a um 413 sem mensagem.
#:
#: **Por isso o número é mais baixo e não igual, e isso foi medido.** A primeira
#: versão punha 12 MiB "para ser o mesmo número do proxy" — e não é: o `12MB` do
#: Caddy são 12 000 000 bytes (base 10, como o go-humanize o lê) e 12 MiB são
#: 12 582 912. Um ficheiro entre os dois valores era recusado pelo **proxy**, sem
#: corpo, exactamente no caso que esta constante existe para cobrir. 11 MiB
#: (11 534 336) fica 465 664 bytes abaixo do proxy, continua a aceitar qualquer
#: fotografia de telemóvel, e garante a ordem: **quem recusa primeiro é quem tem
#: uma frase**.
#:
#: Subir um dos dois sem o outro é o erro a evitar, e é para isso que esta nota
#: existe. Se o do proxy subir, este sobe atrás e continua abaixo.
TAMANHO_MAXIMO_DO_FICHEIRO = 11 * 1024 * 1024

#: O token que conta páginas num PDF. `/Type /Page` seguido de qualquer coisa que
#: não seja `s` — o `/Type /Pages` é o **nó** da árvore e não uma página.
_PAGINA_NUM_PDF = re.compile(rb"/Type\s*/Page(?![s])")


def tipo_real(cabecalho: bytes) -> str | None:
    """O tipo dos bytes, ou `None` se não estiver na lista fechada.

    Recebe só o início do ficheiro (ver `BYTES_PARA_DECIDIR`) e devolve um dos
    `TIPOS_ACEITES`. `None` é a resposta para tudo o mais — um `.svg` (que é XML
    e portanto script), um `.zip`, um executável renomeado, um ficheiro vazio.
    """
    for prefixo, tipo in BYTES_MAGICOS:
        if cabecalho.startswith(prefixo):
            return tipo
    return None


def paginas_num_pdf(dados: bytes) -> int:
    """Quantas páginas este PDF declara, contadas **sem** abrir o PDF.

    Conta as ocorrências de `/Type /Page` nos bytes em claro. Nunca devolve menos
    de 1: um ficheiro que é reconhecidamente um PDF tem ao menos uma página a
    processar, e devolver 0 fazia o documento nascer sem páginas e aparecer como
    `expirado` quinze minutos depois.

    **Os limites deste contador, ditos aqui em vez de descobertos:** um PDF
    moderno guarda os objectos das páginas dentro de `/ObjStm` comprimidos com
    Flate, onde o token não aparece em claro — nesses, isto devolve 1 e
    **subconta**. A ADR 0020 pedia o `pypdf` para esta conta, e o `pypdf` é uma
    dependência que esta sessão não acrescenta. A consequência é conhecida e falha
    para o lado brando: um PDF de doze páginas comprimidas passa o teto de dez à
    entrada, e a autoridade sobre o número real de páginas passa a ser a
    rasterização — que é quem abre o ficheiro, e que ainda não existe. O gatilho
    para trocar isto por uma biblioteca é um documento real que entre com menos
    páginas do que tem.
    """
    return max(1, len(_PAGINA_NUM_PDF.findall(dados)))


def caminho_do_ficheiro(*, tenant_id: UUID, documento_id: UUID, tipo: str) -> str:
    """O caminho relativo (ao `MEDIA_ROOT`) de um ficheiro novo. **Gerado.**

    Três segmentos e um nome: `documentos/<tenant>/<documento>/<uuid>.<ext>`.
    Nada aqui vem do pedido — nem o nome, nem a extensão, que sai do tipo real. É
    o que torna impossível uma travessia de caminho a partir de um
    `original_filename` como `../../etc/passwd`: esse valor é um rótulo e nunca
    chega a esta função.

    O tenant vai no caminho porque é ele que torna um apagamento de tenant uma
    operação de uma árvore só, e porque dois estabelecimentos nunca partilham
    uma pasta.
    """
    extensao = EXTENSAO_POR_TIPO[tipo]
    return f"documentos/{tenant_id}/{documento_id}/{uuid4()}.{extensao}"


def caminho_da_imagem(*, tenant_id: UUID, documento_id: UUID, pagina_id: UUID) -> str:
    """O caminho relativo da imagem normalizada de uma página. **Gerado.**

    Determinístico no uuid da página, ao contrário do caminho do ficheiro: uma
    re-normalização substitui a imagem no mesmo sítio em vez de deixar a anterior
    órfã, e é também o que torna o `Cache-Control` da view da imagem defensável.
    """
    return f"documentos/{tenant_id}/{documento_id}/paginas/{pagina_id}.webp"
