"""Páginas com QR, fabricadas no teste. **Nada aqui toca na rede.**

O leitor de QR precisa de pixéis, e um teste que os fosse buscar a um ficheiro
binário commitado deixava o que se está a medir fora do diff. Aqui o QR é
gerado pela **própria `zxing-cpp`** no momento (ela escreve e lê, e a escrita é
um caminho de código diferente do da leitura), composto numa página de
cinzentos, e opcionalmente embrulhado num PNG para os testes que exercitam a
libvips a sério.

Duas funções e um DTO, e as três servem três leitores:

* `luminancia_com_qr` — a página em cinzentos, que é **exactamente** o formato
  que a `descodificacao.payload_da_at` recebe (um byte por pixel, linha a linha,
  sem padding). É o que permite testar o leitor sem libvips nenhuma, numa
  máquina de desenvolvimento onde ela não existe;
* `png_cinzento` — a mesma página como PNG, para o teste que corre a cadeia
  nativa inteira (libvips a abrir o ficheiro, a encolher, a dar os cinzentos, e
  a `zxing-cpp` a ler). Escrito à mão com `zlib` e `struct` porque este
  repositório não tem — e não quer — uma biblioteca de imagem em Python;
* `PaginaDeEnsaio` — o par (bytes, geometria), que nunca se separa.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

__all__ = ["PaginaDeEnsaio", "luminancia_com_qr", "png_cinzento"]

#: O branco do papel. A página nasce toda branca e os QR são colados por cima.
BRANCO = 0xFF


@dataclass(frozen=True, kw_only=True, slots=True)
class PaginaDeEnsaio:
    """Uma página em cinzentos: um byte por pixel, linha a linha, sem padding."""

    luminancia: bytes
    largura: int
    altura: int


def luminancia_com_qr(
    *textos: str, escala: int = 4, margem: int = 20, intervalo: int = 24
) -> PaginaDeEnsaio:
    """Uma página branca com um QR por cada texto, lado a lado.

    Sem textos nenhuns sai uma página branca — que é o caso "imagem sem QR" e
    não um caso degenerado. Com dois, sai o caso que uma fatura mesmo tem: o QR
    da AT e o do fornecedor (ou um de publicidade) na mesma folha.

    `escala` é o lado de cada módulo do QR em pixéis; 4 dá um código com ~180 px
    de lado, que é a ordem de grandeza do que uma fatura impressa dá depois de a
    página ser encolhida para os 2000 px do rasterizador.
    """
    codigos = [_qr(texto, escala=escala) for texto in textos]
    largura = margem * 2 + sum(c.largura for c in codigos)
    largura += intervalo * max(len(codigos) - 1, 0)
    altura = margem * 2 + max((c.altura for c in codigos), default=escala)

    pagina = bytearray(bytes([BRANCO]) * (largura * altura))
    esquerda = margem
    for codigo in codigos:
        _colar(pagina, largura_da_pagina=largura, codigo=codigo, x=esquerda, y=margem)
        esquerda += codigo.largura + intervalo
    return PaginaDeEnsaio(luminancia=bytes(pagina), largura=largura, altura=altura)


def png_cinzento(pagina: PaginaDeEnsaio) -> bytes:
    """A página como PNG de 8 bits em escala de cinzentos, sem dependências.

    Um PNG é a assinatura, três blocos e o CRC de cada um; os dados são as
    linhas com um byte de filtro (`0`, sem filtro) à frente, comprimidos com
    `zlib`. São dez linhas de código e poupam uma biblioteca de imagem a uma
    suite que só precisa disto para escrever um ficheiro que a libvips abra.
    """
    cru = b"".join(
        b"\x00" + pagina.luminancia[y * pagina.largura : (y + 1) * pagina.largura]
        for y in range(pagina.altura)
    )
    cabecalho = struct.pack(">IIBBBBB", pagina.largura, pagina.altura, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + b"".join(
        _bloco(nome, dados)
        for nome, dados in (
            (b"IHDR", cabecalho),
            (b"IDAT", zlib.compress(cru, 9)),
            (b"IEND", b""),
        )
    )


@dataclass(frozen=True, kw_only=True, slots=True)
class _Codigo:
    pixeis: bytes
    largura: int
    altura: int


def _qr(texto: str, *, escala: int) -> _Codigo:
    """Um QR como matriz de cinzentos, gerado pela `zxing-cpp`."""
    import zxingcpp

    imagem = zxingcpp.create_barcode(texto, zxingcpp.BarcodeFormat.QRCode).to_image(
        scale=escala
    )
    altura, largura = imagem.shape
    return _Codigo(pixeis=bytes(memoryview(imagem)), largura=largura, altura=altura)


def _colar(
    pagina: bytearray, *, largura_da_pagina: int, codigo: _Codigo, x: int, y: int
) -> None:
    """Copia o código para a página, linha a linha."""
    for linha in range(codigo.altura):
        inicio = (y + linha) * largura_da_pagina + x
        pagina[inicio : inicio + codigo.largura] = codigo.pixeis[
            linha * codigo.largura : (linha + 1) * codigo.largura
        ]


def _bloco(nome: bytes, dados: bytes) -> bytes:
    """Um bloco de PNG: tamanho, nome, dados e o CRC-32 dos dois últimos."""
    return (
        struct.pack(">I", len(dados))
        + nome
        + dados
        + struct.pack(">I", zlib.crc32(nome + dados) & 0xFFFFFFFF)
    )
