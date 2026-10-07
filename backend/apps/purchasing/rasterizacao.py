"""A fronteira da rasterização: uma função, e hoje levanta sempre.

A ADR 0020 (decisão 5) decidiu que **o PDF nunca é renderizado no browser** e que
o worker rasteriza cada página para uma imagem normalizada, que é o que o ecrã de
revisão mostra e o que a extração vê. Isso precisa de um rasterizador nativo
(poppler, pdfium) e de um codec de imagem (Pillow) — **duas dependências que esta
sessão não acrescenta**.

Em vez de fingir, a fronteira tem nome próprio e levanta uma excepção que diz o
que falta. A tarefa `normalizar_pagina` apanha-a, deixa a página sem imagem e
regista a razão no log; o documento fica em `a_normalizar` e o endpoint da imagem
responde 404. Nada mente: não há uma coluna `normalized_at` escrita sem imagem por
baixo.

**A condição exacta para isto deixar de levantar:** um rasterizador na imagem do
worker (e só no worker — este módulo é importado pelo processo que serve pedidos
porque a tarefa vive no mesmo pacote, e é por isso que o import do rasterizador
tem de ficar **dentro** da função que o usa, no dia em que existir).

É também o ponto onde a imagem normalizada entra pela única porta: a tarefa chama
isto, recebe bytes e geometria, e entrega-os a `services.registar_normalizacao`,
que é quem escreve. Em teste, é esta função que se substitui para exercitar o
caminho completo sem dependência nenhuma.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ImagemNormalizada", "RasterizadorIndisponivel", "rasterizar"]


class RasterizadorIndisponivel(RuntimeError):
    """Não há rasterizador neste ambiente. Não é recuperável por retentativa."""


@dataclass(frozen=True, kw_only=True, slots=True)
class ImagemNormalizada:
    """O resultado de rasterizar uma página: os bytes e a geometria.

    Congelado e com `slots` como todos os DTO deste repositório. `webp` porque é
    o único formato que o endpoint da imagem serve, e tê-lo no nome do campo é o
    que impede alguém de lhe passar um JPEG e o servir com o tipo errado.
    """

    webp: bytes
    width: int
    height: int


def rasterizar(*, caminho: str, numero_da_pagina: int) -> ImagemNormalizada:
    """A imagem normalizada de uma página de um ficheiro. **Levanta sempre, hoje.**

    `caminho` é relativo ao `MEDIA_ROOT` e vem da coluna `path` do
    `purchasing_documentfile` — um valor **gerado** pelo `ficheiros.py` e nunca
    um nome que tenha vindo do cliente.
    """
    raise RasterizadorIndisponivel(
        "sem rasterizador: converter a página "
        f"{numero_da_pagina} de {caminho!r} numa imagem normalizada precisa de "
        "um rasterizador de PDF (poppler ou pdfium) e de um codec de imagem "
        "(Pillow) na imagem do worker, e nenhum dos dois está nas dependências "
        "deste projecto. A página fica sem imagem e o documento fica em "
        "'a_normalizar' — ver o docstring de apps/purchasing/rasterizacao.py."
    )
