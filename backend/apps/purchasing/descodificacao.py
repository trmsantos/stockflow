"""A fronteira do leitor de QR: uma função, e por trás dela a `zxing-cpp`.

Desde 1/1/2023 toda a fatura portuguesa imprime um QR gerado pelo **software
certificado** que a emitiu, e é por isso que ele é a verdade do cabeçalho
(ADR 0021, adenda; ADR 0031, C). O `qr.py` já sabia interpretar esse texto — o
que faltava, e é o que este ficheiro faz, era **tirá-lo da imagem**.

## A dependência, e porque é esta

O dono decidiu a **2026-10-19**: `zxing-cpp`. Três razões, pela ordem em que
pesaram. Instala-se como qualquer pacote Python (wheel `manylinux_2_28` com o
C++ lá dentro, fixada por hash no `uv.lock`); **não acrescenta uma linha ao
`docker/backend.Dockerfile`** — verificado a correr a wheel dentro da imagem de
runtime, que já traz o `libstdc++6` de que ela precisa; e lê QR fotografados de
lado ou com reflexo, que é o caso normal de uma fatura fotografada em cima do
balcão.

É a escolha oposta à do rasterizador do lado (`rasterizacao.py`, a libvips do
apt), e não é incoerência: ali os 149 MiB compraram **visibilidade** sobre quem
dá parse a um PDF que chegou de fora. Aqui o que entra na biblioteca é uma
matriz de cinzentos que já passou pela libvips, e a wheel é uma linha que o
`uv.lock` fixa e o `pip-audit` lê.

## Nunca rebenta a normalização

Um QR ilegível, ausente, uma página que não é uma fatura, ou uma excepção da
biblioteca dão **string vazia** e mais nada. O QR é um bónus: sem ele o
cabeçalho vem da extração, exactamente como vinha. É por isso que a única função
pública daqui não levanta — e é por isso que o que ela apanha é uma **lista
fechada** de excepções e nunca um `Exception` nu, que esconderia um defeito
nosso com o aspecto de uma fotografia má.

## O payload nunca vai para um log

Traz os dois NIF (ARCHITECTURE.md §8: logs sem PII). O que se regista é quantos
códigos se viram e qual foi a razão de não haver leitura — nunca o conteúdo.

Puro: não toca na base de dados e não importa `models.py`. Quem escreve a coluna
`purchasing_documentpage.qr_payload` com o que isto devolve é o
`services.registar_normalizacao`, na mesma transação que a largura.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.purchasing.qr import ler_qr

__all__ = ["COMPRIMENTO_MAXIMO", "LeitorIndisponivel", "payload_da_at"]

logger = logging.getLogger(__name__)

#: O maior payload que se aceita como cabeçalho, em caracteres.
#:
#: Um QR da AT com todos os campos preenchidos não passa dos ~250; 1024 é folga
#: de quatro vezes. O que isto recusa é um QR que **valida a forma** e traz um
#: quilobyte de texto atrás — não é um cabeçalho, é um sítio para esconder
#: conteúdo numa coluna que o ecrã mostra. É o mesmo reflexo do `_DINHEIRO_MAXIMO`
#: do `qr.py`: cortar na fronteira, e não três ficheiros à frente.
COMPRIMENTO_MAXIMO = 1024

#: As excepções que a biblioteca levanta e que **não** são defeito nosso: um
#: buffer que ela recusa, um argumento que a ligação C++ não converte, memória
#: que não chega numa página enorme. Lista fechada e não `Exception`: um
#: `AttributeError` daqui é um erro de código e tem de subir.
_ERROS_DO_LEITOR = (ValueError, TypeError, RuntimeError, MemoryError, OverflowError)


class LeitorIndisponivel(ImportError):
    """Não há `zxing-cpp` neste ambiente.

    `ImportError` e não `RuntimeError` (que é o que o `RasterizadorIndisponivel`
    usa) por duas razões: é literalmente o que aconteceu, e mantém esta classe
    **fora** do `_ERROS_DO_LEITOR` — as duas razões de não haver leitura são
    distintas e os dois ramos registam frases diferentes.

    Ao contrário da libvips, esta ausência não é esperada em lado nenhum: a wheel
    não precisa de biblioteca de sistema, logo um ambiente com as dependências
    instaladas tem-na sempre. O ramo existe porque uma página normalizar-se é
    mais importante do que ler o QR.
    """


def payload_da_at(*, luminancia: bytes, largura: int, altura: int) -> str:
    """O QR da AT desta página, ou `""`. **Nunca levanta.**

    `luminancia` é um byte por pixel, linha a linha e sem padding — é o que a
    `write_to_memory()` de uma imagem `b-w`/`uchar` da libvips dá. É o único
    formato que entra aqui de propósito: converter cor é trabalho de quem tem a
    imagem aberta (`rasterizacao.py`), e este módulo não conhece a libvips.

    `""` em cinco casos que de fora são o mesmo — *não há cabeçalho
    certificado*: a página não tem QR nenhum, tem QR que não são da AT
    (publicidade, o logótipo do fornecedor), a biblioteca não está instalada, a
    biblioteca recusou a imagem, ou a geometria não bate com os bytes.
    """
    if largura <= 0 or altura <= 0 or len(luminancia) < largura * altura:
        # A biblioteca levantaria `ValueError` e o resultado seria o mesmo, mas a
        # razão não é: aqui quem se enganou fomos nós a montar a vista, e a
        # frase do log tem de o dizer para alguém poder corrigi-lo.
        logger.warning(
            "página normalizada sem leitura de QR: a geometria não bate com os bytes",
            extra={"event": "documento.qr", "outcome": "geometria_invalida"},
        )
        return ""
    try:
        textos = _textos_dos_codigos(
            luminancia=luminancia, largura=largura, altura=altura
        )
    except LeitorIndisponivel as erro:
        logger.warning(
            "página normalizada sem leitura de QR: %s",
            erro,
            extra={"event": "documento.qr", "outcome": "sem_leitor"},
        )
        return ""
    except _ERROS_DO_LEITOR as erro:
        logger.warning(
            "página normalizada sem leitura de QR: a zxing-cpp recusou a imagem (%s)",
            erro,
            extra={"event": "documento.qr", "outcome": "imagem_recusada"},
        )
        return ""
    return _candidato_da_at(textos)


def _biblioteca() -> Any:
    """A `zxing-cpp`, ou `LeitorIndisponivel` com a frase do que falta.

    O import é **dentro da função**, pela mesma razão do rasterizador: este
    módulo é alcançado pelo processo que serve pedidos (o `services.py` importa
    a `rasterizacao.py`, que importa esta), e um import de topo carregava o C++
    em todo o lado para o usar só no worker.
    """
    try:
        import zxingcpp
    except ImportError as erro:
        raise LeitorIndisponivel(
            "sem leitor de QR: este ambiente não tem a `zxing-cpp`. Ela está no "
            "`pyproject.toml` e no `uv.lock` desde 2026-10-19, a wheel não "
            f"precisa de nada do sistema, e um `uv sync` repõe-na. ({erro})"
        ) from erro
    return zxingcpp


def _textos_dos_codigos(*, luminancia: bytes, largura: int, altura: int) -> list[str]:
    """O texto de cada QR encontrado na imagem, por ordem de descoberta.

    `formats=QRCode` fecha a leitura ao que interessa: o EAN de um artigo
    impresso na linha não é um cabeçalho, e procurar só uma simbologia é também
    o caminho mais barato. `try_rotate` e `try_invert` ficam nos defaults — são
    eles que lêem o QR de uma fatura fotografada de lado ou impressa a branco
    sobre fundo escuro, e são metade da razão da escolha da biblioteca.

    **A `ImageView` é uma vista e não é dona dos bytes.** `luminancia` é um
    parâmetro, logo tem um nome vivo durante toda a função e a memória não
    desaparece debaixo da leitura. Passar aqui uma expressão temporária — um
    `bytes(...)` construído dentro da chamada — dá uma leitura sem código
    nenhum, sem erro nenhum e sem aviso nenhum: foi assim que isto se descobriu,
    a correr a cadeia inteira dentro da imagem de runtime.
    """
    zxingcpp = _biblioteca()
    vista = zxingcpp.ImageView(luminancia, largura, altura, zxingcpp.ImageFormat.Lum)
    codigos = zxingcpp.read_barcodes(vista, formats=zxingcpp.BarcodeFormat.QRCode)
    return [codigo.text for codigo in codigos]


def _candidato_da_at(textos: list[str]) -> str:
    """O primeiro texto que é um QR da AT, ou `""` — e **nunca** a junção de dois.

    Quem decide se um texto é da AT é o `ler_qr` do `qr.py`, e não uma segunda
    validação escrita aqui: é lá que vive a forma `chave:valor*…` e a exigência
    de trazer o NIF do emitente ou o ATCUD — os dois campos que nenhum outro
    texto traz por acaso. Um URL de publicidade não passa, e é esse o caso que
    uma página de fatura tem mesmo.

    Com mais do que um candidato fica **o primeiro** e regista-se que havia
    mais. Concatenar era fabricar um cabeçalho que nenhum software assinou; e
    escolher "o melhor" era inferência nossa sobre um documento que uma pessoa
    tem à frente.
    """
    candidatos = [
        texto
        for texto in textos
        if len(texto) <= COMPRIMENTO_MAXIMO and ler_qr(texto) is not None
    ]
    if not candidatos:
        if textos:
            logger.info(
                "página com QR que não são da AT: o cabeçalho vem da extração",
                extra={
                    "event": "documento.qr",
                    "outcome": "sem_candidato",
                    "codigos": len(textos),
                },
            )
        return ""
    if len(candidatos) > 1:
        logger.warning(
            "página com mais do que um QR de fatura: fica o primeiro",
            extra={
                "event": "documento.qr",
                "outcome": "varios_candidatos",
                "candidatos": len(candidatos),
            },
        )
    return candidatos[0]
