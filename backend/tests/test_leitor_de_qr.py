"""A fronteira que tira o QR da imagem (`purchasing/descodificacao.py`).

O `qr.py` interpreta o texto de um QR e está medido no
`tests/test_extracao_de_faturas.py` (secção 3). Este ficheiro mede o passo que
faltava e que a ADR 0031 (decisão 8) tinha deixado de fora por falta de
dependência: **tirar esse texto de uma página**. A dependência foi decidida a
2026-10-19 (`zxing-cpp`).

## O que se afirma, e porquê cada um

1. **o payload sai exacto.** Um QR lido "quase bem" é pior do que nenhum: o
   cabeçalho dele ganha ao do modelo, logo um carácter trocado passa a ser a
   verdade servida;
2. **as quatro maneiras de não haver QR dão todas `""`** — página sem QR, QR que
   não é da AT, biblioteca a levantar, biblioteca ausente — e **nenhuma levanta**.
   É isto que faz do QR um bónus: sem ele a página normaliza na mesma e o
   cabeçalho vem da extração, como vinha antes de haver leitor;
3. **nunca se concatenam dois QR.** Uma fatura traz publicidade e logótipos na
   mesma folha; com dois candidatos fica o primeiro e fica dito no log.

Nenhum teste fala com a rede e nenhum lê um binário commitado: os QR são
gerados no momento pela própria biblioteca (`tests/qr_de_ensaio.py`).
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from apps.purchasing.descodificacao import (
    COMPRIMENTO_MAXIMO,
    LeitorIndisponivel,
    payload_da_at,
)
from tests.qr_de_ensaio import luminancia_com_qr, png_cinzento

#: O QR de uma fatura do Continente, no formato da AT.
QR_DA_AT = (
    "A:500000001*B:999999990*C:PT*D:FT*E:N*F:20261006*G:FT A/1174*"
    "H:JFBD7CJ9-1174*I1:PT*I3:72.26*I4:4.34*I7:100.00*I8:23.00*N:27.34*O:199.60"
)

#: Um segundo QR da AT, de outro documento. Serve para o caso dos dois
#: candidatos, que é o único em que a escolha "o primeiro" é observável.
QR_DE_OUTRO_DOCUMENTO = (
    "A:500000002*B:999999990*C:PT*D:FT*E:N*F:20261007*G:FT B/22*"
    "H:JFBD7CJ9-22*I1:PT*I7:50.00*I8:11.50*N:11.50*O:61.50"
)

#: O QR que uma fatura mesmo traz ao lado do da AT: o do fornecedor, a apontar
#: para o site dele. Não começa por `A:` e não tem campo nenhum da AT.
QR_DE_PUBLICIDADE = "https://exemplo.invalido/promocoes-de-outubro"


def _lido(*textos: str) -> str:
    """O que a fronteira lê numa página com estes QR."""
    pagina = luminancia_com_qr(*textos)
    return payload_da_at(
        luminancia=pagina.luminancia, largura=pagina.largura, altura=pagina.altura
    )


@pytest.fixture
def avisos(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> pytest.LogCaptureFixture:
    """O `caplog` a ver os registos do `apps.*`.

    O `LOGGING` do `config/settings/base.py` dá ao logger `apps` um handler
    próprio e `propagate: False` — o que é certo em produção (uma linha JSON e
    não duas) e invisível para o `caplog`, que vive na raiz. Ligar a propagação
    só neste teste é a forma honesta de ver o que a aplicação regista sem mudar
    a configuração de produção.
    """
    monkeypatch.setattr(logging.getLogger("apps"), "propagate", True)
    caplog.set_level(logging.INFO, logger="apps.purchasing.descodificacao")
    return caplog


# ---------------------------------------------------------------------------
# 1. O caminho feliz
# ---------------------------------------------------------------------------
def test_o_qr_da_at_de_uma_pagina_le_se_exactamente() -> None:
    """Carácter a carácter, porque é o cabeçalho servido que depende disto.

    `==` e não "contém": o payload vai inteiro para a coluna e é dele que saem
    os dois NIF, o ATCUD e as bases por taxa. Um carácter a mais ou a menos é um
    NIF que não casa com fornecedor nenhum, ou uma base que não confere.
    """
    assert _lido(QR_DA_AT) == QR_DA_AT


def test_a_leitura_sobrevive_a_um_qr_pequeno_numa_pagina_grande() -> None:
    """Um QR de 180 px numa página de folha inteira continua a ler-se.

    É a geometria real depois do rasterizador: a página encolhe para 2000 px de
    lado e o QR fica com a fracção dela que tinha no papel.
    """
    pagina = luminancia_com_qr(QR_DA_AT, margem=400)

    assert payload_da_at(
        luminancia=pagina.luminancia, largura=pagina.largura, altura=pagina.altura
    ) == QR_DA_AT


# ---------------------------------------------------------------------------
# 2. As maneiras de não haver QR — todas `""`, nenhuma levanta
# ---------------------------------------------------------------------------
def test_uma_pagina_sem_qr_nenhum_nao_da_leitura_e_nao_levanta() -> None:
    """O caso mais comum de todos: uma fatura anterior a 2023, ou um talão."""
    assert _lido() == ""


def test_um_qr_que_nao_e_da_at_nao_e_cabecalho(avisos: pytest.LogCaptureFixture) -> None:
    """Um URL é um QR válido e não é um cabeçalho certificado.

    Quem decide isto é o `ler_qr` do `qr.py` — a mesma função que a leitura usa
    —, e é por isso que não há aqui uma segunda validação da forma a divergir da
    primeira.
    """
    assert _lido(QR_DE_PUBLICIDADE) == ""
    assert "não são da AT" in avisos.text


def test_a_biblioteca_a_levantar_deixa_a_pagina_sem_qr_e_avisa(
    monkeypatch: pytest.MonkeyPatch, avisos: pytest.LogCaptureFixture
) -> None:
    """Uma excepção da `zxing-cpp` é falta de QR e nunca uma página perdida.

    Substitui-se a função da biblioteca e não a nossa: o que se mede é o ramo
    que apanha o que ela levanta, e esse ramo tem uma lista fechada de tipos
    para um `AttributeError` nosso continuar a subir.
    """
    import zxingcpp

    def recusa(*_: Any, **__: Any) -> list[Any]:
        raise ValueError("encenado por este teste")

    monkeypatch.setattr(zxingcpp, "read_barcodes", recusa)

    assert _lido(QR_DA_AT) == ""
    assert "a zxing-cpp recusou a imagem" in avisos.text


def test_sem_biblioteca_nao_ha_leitura_e_a_frase_diz_o_que_falta(
    monkeypatch: pytest.MonkeyPatch, avisos: pytest.LogCaptureFixture
) -> None:
    """A ausência da wheel é um ramo próprio, com outra frase e outro `outcome`.

    Não é um caso esperado — ao contrário da libvips, esta dependência não
    precisa de nada do sistema — mas uma página normalizar-se é mais importante
    do que ler o QR, e é isso que este ramo garante.
    """
    import apps.purchasing.descodificacao as fronteira

    def sem_wheel() -> Any:
        raise LeitorIndisponivel("encenado por este teste")

    monkeypatch.setattr(fronteira, "_biblioteca", sem_wheel)

    assert _lido(QR_DA_AT) == ""
    assert "encenado por este teste" in avisos.text


def test_uma_geometria_que_nao_bate_com_os_bytes_nao_chega_a_biblioteca(
    avisos: pytest.LogCaptureFixture,
) -> None:
    """Bytes a menos para a geometria declarada é defeito nosso, e diz-se isso.

    O resultado seria o mesmo por dentro da biblioteca (um `ValueError`), mas a
    razão registada não: quem se enganou a montar a vista fomos nós, e a frase
    do log é o que permite distingui-lo de uma fotografia má.
    """
    assert payload_da_at(luminancia=b"\xff" * 10, largura=100, altura=100) == ""
    assert payload_da_at(luminancia=b"", largura=0, altura=0) == ""
    assert "a geometria não bate com os bytes" in avisos.text


def test_um_payload_longo_de_mais_nao_entra_na_coluna() -> None:
    """Um QR com a forma certa e um quilobyte de texto atrás não é cabeçalho.

    O corte é na fronteira (`COMPRIMENTO_MAXIMO`), como o do dinheiro no
    `qr.py`: um campo que cresceu é um diff, e um texto arbitrário guardado numa
    coluna que o ecrã mostra é uma superfície que não se quer ganhar por acaso.
    """
    enchimento = "*Z:" + "x" * COMPRIMENTO_MAXIMO

    assert _lido(QR_DA_AT + enchimento) == ""


# ---------------------------------------------------------------------------
# 3. Dois QR na mesma folha
# ---------------------------------------------------------------------------
def test_com_um_qr_da_at_e_um_de_publicidade_fica_o_da_at() -> None:
    """A folha real: o QR fiscal e o do fornecedor lado a lado.

    E nas duas ordens, porque "fica o primeiro" não pode querer dizer "fica o
    primeiro que a biblioteca encontrou, seja ele qual for".
    """
    assert _lido(QR_DE_PUBLICIDADE, QR_DA_AT) == QR_DA_AT
    assert _lido(QR_DA_AT, QR_DE_PUBLICIDADE) == QR_DA_AT


def test_com_dois_qr_da_at_fica_o_primeiro_e_o_log_diz_que_havia_mais(
    avisos: pytest.LogCaptureFixture,
) -> None:
    """Nunca concatenar: um cabeçalho fabricado não foi assinado por ninguém.

    Dois QR fiscais na mesma folha querem dizer que a fotografia apanhou dois
    papéis — e isso é exactamente o que a divergência do `qr.py` serve para
    mostrar a quem revê, com um dos documentos à vista.
    """
    lido = _lido(QR_DA_AT, QR_DE_OUTRO_DOCUMENTO)

    assert lido == QR_DA_AT
    assert QR_DE_OUTRO_DOCUMENTO not in lido
    assert "mais do que um QR de fatura" in avisos.text


# ---------------------------------------------------------------------------
# 4. As duas peças nativas, juntas
# ---------------------------------------------------------------------------
def test_a_libvips_e_o_leitor_juntos_lem_o_qr_de_uma_pagina() -> None:
    """A cadeia nativa inteira, sem nada substituído.

    **Salta onde a libvips não existe** e corre no CI, que a instala de propósito
    — a mesma regra do `test_rasterizar_um_pdf_da_um_webp_que_nao_amplia`. É o
    único teste que exercita a cola entre as duas bibliotecas: a imagem aberta e
    encolhida pela libvips, convertida para cinzentos e entregue à `zxing-cpp`
    sem o ficheiro ser aberto uma segunda vez.
    """
    from apps.purchasing.ficheiros import caminho_dentro_do_media
    from apps.purchasing.rasterizacao import ha_rasterizador, rasterizar

    if not ha_rasterizador():
        pytest.skip("sem libvips neste ambiente: o CI instala-a de propósito")

    relativo = "documentos/ensaio/qr/pagina.png"
    destino = caminho_dentro_do_media(relativo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(png_cinzento(luminancia_com_qr(QR_DA_AT, escala=6)))

    imagem = rasterizar(caminho=relativo, numero_da_pagina=1)

    assert imagem.qr_payload == QR_DA_AT
    assert imagem.webp[:4] == b"RIFF"


def test_uma_pagina_sem_qr_rasteriza_na_mesma() -> None:
    """Sem QR não há leitura, e a página serve à mesma. O QR é um bónus."""
    from apps.purchasing.ficheiros import caminho_dentro_do_media
    from apps.purchasing.rasterizacao import ha_rasterizador, rasterizar

    if not ha_rasterizador():
        pytest.skip("sem libvips neste ambiente: o CI instala-a de propósito")

    relativo = "documentos/ensaio/qr/sem-qr.png"
    destino = caminho_dentro_do_media(relativo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(png_cinzento(luminancia_com_qr(margem=120)))

    imagem = rasterizar(caminho=relativo, numero_da_pagina=1)

    assert imagem.qr_payload == ""
    assert imagem.width > 0
