"""A fronteira da rasterização: uma função, e por trás dela a libvips.

A ADR 0020 (decisão 5) decidiu que **o PDF nunca é renderizado no browser** e que
o worker rasteriza cada página para uma imagem normalizada, que é o que o ecrã de
revisão mostra e o que a extração vê.

## Porque é a libvips do sistema e não uma wheel com o binário dentro

As duas opções foram medidas antes de a escolha ser feita, e o dono escolheu com
os números à frente. Uma wheel (`pypdfium2` + `pillow`) custava ~10 MiB, zero
pacotes de sistema e zero apt; a libvips do Debian custa **149 MiB** e ~90
pacotes. O que a libvips compra por esses 139 MiB é **visibilidade**: cada um dos
90 pacotes é um nome e uma versão que o `trivy` do CI lê e reporta, e um binário
vendorizado dentro de uma wheel não é rastreado por ferramenta nenhuma deste
repositório. É a mesma razão por que a camada de apt do `backend.Dockerfile`
existe com dois pacotes pinados à mão — "o pino envelhece de propósito".

**A reversão é barata e fica escrita**: duas linhas no Dockerfile, uma no
`pyproject.toml` e o corpo desta função. O gatilho para a querer: o tamanho da
imagem passar a doer no deploy.

## Porque é uma biblioteca e não o `pdftoppm`

O caminho óbvio — `poppler-utils` e um `subprocess.run(["pdftoppm", ...])` — **não
passa os gates deste repositório**, e isso foi medido e não presumido: o `bandit`
do CI corre sem limiar de severidade (`.github/workflows/ci.yml`), um
`subprocess.run` levanta B404 e B603 em LOW, e o `# nosec` é supressão — que o
`CLAUDE.md` proíbe e que o próprio `security_check.sh` procura em ficheiros de
configuração. Ligar à **biblioteca** pelo `pyvips` dá a mesma capacidade sem
lançar processo nenhum.

E dá-a com um só loader: a libvips do Debian traz `VipsForeignLoadPdf` (poppler)
**e** `webpsave` — verificado dentro da imagem antes de isto ser escrito —, logo
renderizar, encolher e gravar são uma chamada e não três ferramentas.

## O import é dentro da função, e isso não é estilo

Este módulo é importado pelo processo que **serve pedidos**, porque a tarefa vive
no mesmo pacote. Um import de topo obrigava a libvips a existir em qualquer
ambiente que sirva HTTP — incluindo um portátil sem ela — e trocava um 404 numa
imagem por um erro de arranque em toda a aplicação.

Quando a biblioteca falta, a função levanta `RasterizadorIndisponivel`: a tarefa
apanha-a, deixa a página sem imagem e regista a razão; o documento fica em
`a_normalizar` e o endpoint da imagem responde 404. Nada mente — não há uma coluna
`normalized_at` escrita sem imagem por baixo.

É também o ponto onde a imagem normalizada entra pela única porta: a tarefa chama
isto, recebe bytes e geometria, e entrega-os a `services.registar_normalizacao`,
que é quem escreve. Em teste, é esta função que se substitui para exercitar o
caminho completo sem dependência nenhuma.

## O QR lê-se aqui, e por uma razão de custo

Desde 2026-10-19 esta função devolve também o `qr_payload` da página
(`descodificacao.py`, a outra fronteira nativa). Lê-se **aqui** porque é aqui
que a imagem está aberta e **já encolhida**: descodificar noutro sítio obrigava
a abrir o ficheiro uma segunda vez e a renderizar outra vez um PDF, que é a
parte cara disto. O que a `zxing-cpp` vê é a mesma imagem que o ecrã mostra, em
cinzentos.

A leitura **nunca** faz uma página ser ilegível: `PaginaIlegivel` continua a
querer dizer "a libvips recusou este ficheiro" e mais nada. Sem QR a coluna fica
vazia, a página normaliza na mesma e o cabeçalho vem da extração, como vinha.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from apps.purchasing.descodificacao import payload_da_at
from apps.purchasing.ficheiros import caminho_dentro_do_media

__all__ = [
    "ImagemNormalizada",
    "PaginaIlegivel",
    "RasterizadorIndisponivel",
    "ha_rasterizador",
    "rasterizar",
]

logger = logging.getLogger(__name__)

#: O lado maior de uma página normalizada, em pixéis.
#:
#: 2000 é a ordem de grandeza que o `domain-expert` deu para uma página legível a
#: ler ao lado das linhas (300–600 KB em WebP). **Só encolhe**: uma fotografia
#: pequena fica como está, porque ampliar não acrescenta informação e multiplica
#: os bytes.
LADO_MAXIMO = 2000

#: A qualidade do WebP. 80 é o joelho da curva — acima disso o ficheiro cresce
#: mais do que a legibilidade.
QUALIDADE = 80


class RasterizadorIndisponivel(RuntimeError):
    """Não há rasterizador neste ambiente. Não é recuperável por retentativa."""


class PaginaIlegivel(RuntimeError):
    """A biblioteca existe e não conseguiu ler esta página.

    Distinta da de cima de propósito: esta **não** é um problema do ambiente, é
    um problema daquele ficheiro — um PDF truncado a meio do upload, uma página
    que o poppler recusa, uma fotografia corrompida. Repetir não ajuda, e a
    diferença entre as duas é a diferença entre "falta instalar" e "este
    documento não serve".
    """


def _biblioteca() -> Any:
    """A libvips, ou `RasterizadorIndisponivel` com a frase do que falta.

    O `pyvips` carrega a biblioteca nativa **no import** e levanta `OSError`
    quando ela não está no sistema, que é o caso de qualquer máquina de
    desenvolvimento sem o `libvips42`. As duas falhas — o pacote Python ausente e
    a biblioteca nativa ausente — dizem-se com a mesma frase porque a acção é a
    mesma.
    """
    try:
        import pyvips
    except (ImportError, OSError) as erro:
        raise RasterizadorIndisponivel(
            "sem rasterizador: este ambiente não tem a libvips. Na imagem do "
            "worker ela vem do `libvips42` da camada de apt do "
            "`docker/backend.Dockerfile`; numa máquina de desenvolvimento, "
            "instalá-la é opcional — sem ela as páginas ficam sem imagem e o "
            f"endpoint da imagem responde 404. ({erro})"
        ) from erro
    return pyvips


@dataclass(frozen=True, kw_only=True, slots=True)
class ImagemNormalizada:
    """O resultado de rasterizar uma página: os bytes e a geometria.

    Congelado e com `slots` como todos os DTO deste repositório. `webp` porque é
    o único formato que o endpoint da imagem serve, e tê-lo no nome do campo é o
    que impede alguém de lhe passar um JPEG e o servir com o tipo errado.

    `qr_payload` é o texto do QR da AT que esta página traz, vazio quando não
    traz nenhum. **Tem omissão** porque a página é o que ela é com ou sem QR, e
    porque o campo entrou depois dos outros três: um teste que encene a
    fronteira continua a dizer apenas o que lhe interessa.
    """

    webp: bytes
    width: int
    height: int
    qr_payload: str = ""


def rasterizar(*, caminho: str, numero_da_pagina: int) -> ImagemNormalizada:
    """A imagem normalizada de uma página de um ficheiro.

    `caminho` é relativo ao `MEDIA_ROOT` e vem da coluna `path` do
    `purchasing_documentfile` — um valor **gerado** pelo `ficheiros.py` e nunca
    um nome que tenha vindo do cliente. Passa pelo `caminho_dentro_do_media`
    ainda assim, que é a regra deste repositório para a última linha antes de
    abrir um ficheiro.

    `numero_da_pagina` é **1-based**, como a coluna `file_page_number`; o `page`
    da libvips é 0-based, e a conversão acontece aqui numa linha em vez de ficar
    espalhada por quem chama.

    Uma chamada só faz as três coisas: o `thumbnail` da libvips renderiza o PDF
    **já na escala pedida** em vez de renderizar grande e encolher — é o que
    limita a memória de uma página A0 — e o `size="down"` é o que garante que
    nada é ampliado.

    O QR sai da mesma imagem, depois de o WebP estar feito e **fora** do `try`
    que traduz um erro da libvips em `PaginaIlegivel`: uma página que se
    rasteriza não passa a não servir por causa de um QR.
    """
    pyvips = _biblioteca()
    origem = caminho_dentro_do_media(caminho)

    descritor = str(origem)
    if origem.suffix.lower() == ".pdf":
        descritor = f"{origem}[page={numero_da_pagina - 1}]"

    try:
        imagem = pyvips.Image.thumbnail(
            descritor, LADO_MAXIMO, height=LADO_MAXIMO, size="down"
        )
        # Uma página de PDF vem com canal alfa e um documento não é transparente:
        # sem isto, o branco do papel fica a preto em qualquer visualizador que
        # componha sobre escuro — que é esta aplicação inteira.
        if imagem.hasalpha():
            imagem = imagem.flatten(background=[255, 255, 255])
        # `strip=True` apaga os metadados, e **isto é privacidade e não higiene**:
        # a fotografia de uma fatura tirada num telemóvel traz EXIF com GPS, e a
        # imagem é servida a qualquer membro do estabelecimento. O que se guarda
        # é a página, não o sítio onde ela foi fotografada.
        #
        # **A imagem materializa-se aqui, e isto não é optimização.** O que o
        # `thumbnail` devolve é um pipeline de acesso **sequencial**, que só se
        # consome uma vez: com dois consumidores — o WebP e os cinzentos do QR —
        # o segundo morria com `unable to write to memory: out of order read`, e
        # morria *dentro* deste `try`, logo uma página perfeitamente legível
        # passava a `PaginaIlegivel`. Medido dentro da imagem de runtime, que é
        # onde há libvips. O preço é a página descodificada em RAM, limitada
        # pelo `LADO_MAXIMO` (≤ 12 MB a 2000×2000 RGB) e libertada a seguir.
        imagem = imagem.copy_memory()
        bytes_webp = imagem.write_to_buffer(".webp", Q=QUALIDADE, strip=True)
    except pyvips.Error as erro:
        raise PaginaIlegivel(
            f"a libvips não conseguiu ler a página {numero_da_pagina} de "
            f"{caminho!r}: {erro}"
        ) from erro

    return ImagemNormalizada(
        webp=bytes(bytes_webp),
        width=imagem.width,
        height=imagem.height,
        qr_payload=_qr_da_imagem(pyvips, imagem),
    )


def _qr_da_imagem(pyvips: Any, imagem: Any) -> str:
    """O QR da AT desta página, lido na imagem já encolhida, ou `""`.

    `colourspace("b-w")` é luminância a sério e não a primeira banda: um QR
    impresso a cor sobre fundo claro perde contraste quando se deita fora o
    verde e o azul. O `cast("uchar")` é a rede contra uma origem de 16 bits por
    banda, que daria dois bytes por pixel e uma vista desalinhada.

    O `write_to_memory()` custa um byte por pixel — 4 MB no tecto de 2000×2000,
    libertados a seguir — e é o preço de não voltar a abrir o ficheiro. Só
    funciona porque quem chama já materializou a imagem (`copy_memory`): o
    pipeline do `thumbnail` lê-se uma vez, e o WebP foi o primeiro a lê-lo.

    O `bytes(...)` não é cosmética: o que a libvips devolve é um buffer dela, e a
    vista que a `zxing-cpp` constrói **não é dona** da memória que lê. O que
    atravessa a fronteira é um objecto Python normal, com um nome vivo do outro
    lado durante toda a leitura.

    Um erro da libvips aqui é **só** falta de QR: o WebP já está feito e a
    página serve. Por isso este ramo regista e devolve vazio em vez de levantar
    `PaginaIlegivel`.
    """
    try:
        cinzentos = imagem.colourspace("b-w").cast("uchar")
        luminancia = bytes(cinzentos.write_to_memory())
    except pyvips.Error as erro:
        logger.warning(
            "página normalizada sem leitura de QR: a libvips não deu os cinzentos (%s)",
            erro,
            extra={"event": "documento.qr", "outcome": "sem_cinzentos"},
        )
        return ""
    return payload_da_at(
        luminancia=luminancia,
        largura=cinzentos.width,
        altura=cinzentos.height,
    )


def ha_rasterizador() -> bool:
    """Há libvips neste ambiente?

    Existe porque a pergunta tem dois leitores e nenhum deve adivinhar: um teste
    que renderiza uma página **salta** onde ela não está (e o `importorskip` do
    pytest não serve — o `pyvips` está instalado e o que falha é a biblioteca
    nativa, com um erro que não é sobre o módulo pedido), e um dia um diagnóstico
    de arranque vai querer dizer "o worker não rasteriza" em vez de o descobrir
    por páginas sem imagem.

    Não é a mesma coisa que apanhar a excepção no sítio da chamada: aqui a
    resposta é um booleano e não um ramo de erro.
    """
    try:
        _biblioteca()
    except RasterizadorIndisponivel:
        return False
    return True
