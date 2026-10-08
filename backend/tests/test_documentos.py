"""`/api/v1/documents`, ponta a ponta (ADR 0021, fatia 1).

Este ficheiro existe para medir sete coisas que não se vêem por revisão. As
outras asserções são acessórias a elas.

**1. Os bytes são a autoridade e o `Content-Type` do cliente é ignorado.** Um
`.exe` renomeado para `.pdf` é recusado e um PDF com `Content-Type` mentiroso é
**aceite** — as duas direcções, porque só as duas juntas provam que o header não
é validado em vez de ser ignorado. Os testes são
`test_um_executavel_renomeado_para_pdf_e_recusado` e
`test_um_pdf_com_content_type_mentiroso_e_aceite`.

**2. A travessia de tenant dá 404 e não 403.** O `id` de um documento de outro
estabelecimento não é legível (a política devolve zero linhas), logo não há
objecto sobre o qual negar — e um 403 confirmaria que aquele documento existe. A
lista também não o traz. É o
`test_um_documento_de_outro_estabelecimento_da_404_e_nao_403`.

**3. A mesma página enviada duas vezes não cria uma segunda.** É a retentativa de
uma rede má, que é o caso normal de um telemóvel a enviar uma fotografia, e a
rede é a unicidade `(document, sha256)` — o primeiro envio devolve 201 e o
segundo 200, com a contagem de páginas intacta.

**4. Os dois tetos recusam.** O 11.º ficheiro e o ficheiro de 13 MiB.

**5. O estado é derivado do relógio e não de uma coluna.** Um slot sem páginas
com quinze minutos lê-se `expirado` **sem nenhuma escrita entretanto** — o teste
recua o `created_at` por `update()` e lê o estado duas vezes, antes e depois.

**6. Qualquer membro activo envia.** Um `staff` cria, anexa, fecha e descarta: é a
decisão 9 da ADR 0021, e o `test_um_staff_faz_o_ciclo_todo` é o que falha se
alguém lhe puser um `TemPapel`.

**7. O nome do ficheiro no disco é gerado.** Um `original_filename` com `../` no
meio não aparece em caminho nenhum — o `test_o_nome_do_cliente_nunca_chega_ao_
disco` compara o `path` contra o nome enviado.

## Porque é que todos levam `transactional_db`

O mesmo motivo do `tests/test_convites.py`: com a transação do pytest-django por
fora, o `set_config('app.tenant_id', ..., true)` que o `tenant_scope` corre só
reverte no fim **dela** e não no fim do bloco `with`. E há uma segunda razão nesta
feature: o `transaction.on_commit` com que os handlers da outbox enfileiram as
tarefas só corre num commit a sério, logo sem `transactional_db` nada era
enfileirado e metade do estado derivado não se mediria.

Desde 2026-10-08 o fecho de um documento publica um evento em vez de enfileirar
(`apps/shared/consumidor.py`), pelo que os dois testes deste ficheiro que
dependiam do trabalho ter sido feito chamam `consumir_outbox()` — que é o que o
`beat` faz a cada 5 segundos. Os outros não chamam, e isso é informação: o POST
passou a registar o trabalho em vez de o fazer.

## O guarda de âmbito do `conftest.py` está a trabalhar aqui

Nenhum teste deste ficheiro tem a marca `sem_ambito_de_rls`, logo o guarda está
montado e levanta se alguma query tocar nas tabelas do documento fora de um
âmbito que as alcance. Isso torna cada pedido deste ficheiro uma afirmação de que
a leitura acontece dentro do âmbito que a sessão escolheu.
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from apps.accounts.middleware import SESSION_TENANT_KEY
from apps.accounts.models import Papel, Tenant, User
from apps.accounts.services import BACKEND_DE_SESSAO, conceder_pertenca, criar_tenant
from apps.purchasing.ficheiros import TAMANHO_MAXIMO_DO_FICHEIRO, TIPOS_ACEITES
from apps.purchasing.models import (
    JANELA_DO_SLOT,
    PAGINAS_POR_DOCUMENTO,
    DocumentFile,
    DocumentPage,
    EstadoDoDocumento,
    InvoiceDocument,
    OrigemDoDocumento,
)
from apps.purchasing.rasterizacao import ImagemNormalizada, RasterizadorIndisponivel
from apps.purchasing.services import CODIGOS_DE_RECUSA_DE_DOCUMENTO
from apps.purchasing.views import STATUS_DA_RECUSA_DE_DOCUMENTO
from apps.shared.db import tenant_scope

URL = "/api/v1/documents"

CREDENCIAL_VALIDA = "trigo-fresco-ao-amanhecer-7"

#: Um PDF mínimo com **uma** página: o `/Type /Catalog` é o nó do catálogo e o
#: `/Type /Page` é a página. Escrito à mão porque o contador do `ficheiros.py` é
#: um varredor de tokens em Python puro — não há `pypdf` neste projecto — e o que
#: interessa medir é exactamente o que ele vê.
PDF_DE_UMA_PAGINA = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type /Catalog /Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type /Pages /Kids [3 0 R] /Count 1>>endobj\n"
    b"3 0 obj<</Type /Page /Parent 2 0 R>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)

#: JPEG e PNG: os bytes mágicos mais enchimento. Nenhum decoder os abre no caminho
#: do pedido, logo não precisam de ser imagens válidas — e é precisamente isso que
#: o teste prova a par do sniffer.
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 128
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128

#: Um executável de Windows: `MZ` e mais nada. Serve o teste do `.exe` renomeado.
EXECUTAVEL = b"MZ\x90\x00\x03" + b"\x00" * 128

#: Um SVG, que é XML e portanto script. Um dos formatos que a ADR 0020 nomeia
#: explicitamente como recusado.
SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"></svg>'


def pdf_com(paginas: int) -> bytes:
    """Um PDF com `paginas` ocorrências do token que o contador conta."""
    corpo = b"".join(
        f"{numero} 0 obj<</Type /Page>>endobj\n".encode() for numero in range(paginas)
    )
    return b"%PDF-1.4\n" + corpo + b"%%EOF\n"


@dataclass(frozen=True, kw_only=True, slots=True)
class Cenario:
    """Dois estabelecimentos e três contas, uma por situação que interessa."""

    alfa: Tenant
    beta: Tenant
    #: `owner` em Alfa.
    ana: User
    #: `staff` em Alfa: é a prova de que qualquer membro activo envia.
    carla: User
    #: `owner` em Beta: serve a travessia de estabelecimento.
    dinis: User


@pytest.fixture(autouse=True)
def _cache_limpa() -> Iterator[None]:
    """O `ScopedRateThrottle` das escritas conta em cache, local ao processo.

    Sem isto, os 20/min do balde `documentos` acumulam entre testes do mesmo
    processo — e este ficheiro faz muitas escritas — e um teste começa a falhar
    por causa dos que correram antes.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def cenario(transactional_db: None) -> Cenario:
    """O cenário, construído **só** pelas funções de `services.py`."""
    ana = User.objects.create_user("ana@alfa.pt", CREDENCIAL_VALIDA)
    carla = User.objects.create_user("carla@alfa.pt", CREDENCIAL_VALIDA)
    dinis = User.objects.create_user("dinis@beta.pt", CREDENCIAL_VALIDA)

    alfa = criar_tenant(name="Pastelaria Alfa")
    beta = criar_tenant(name="Café Beta")

    with tenant_scope(alfa.id):
        conceder_pertenca(
            user=ana, tenant_id=alfa.id, role=Papel.OWNER, display_name="Ana Silva"
        )
        conceder_pertenca(
            user=carla, tenant_id=alfa.id, role=Papel.STAFF, display_name="Carla Reis"
        )
    with tenant_scope(beta.id):
        conceder_pertenca(
            user=dinis, tenant_id=beta.id, role=Papel.OWNER, display_name="Dinis Lima"
        )

    return Cenario(alfa=alfa, beta=beta, ana=ana, carla=carla, dinis=dinis)


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
def _cliente(user: User, tenant_id: UUID) -> Client:
    """Um cliente com sessão e estabelecimento activo."""
    cliente = Client()
    cliente.force_login(user, backend=BACKEND_DE_SESSAO)
    sessao = cliente.session
    sessao[SESSION_TENANT_KEY] = str(tenant_id)
    sessao.save()
    return cliente


def _ficheiro(
    conteudo: bytes, nome: str = "fatura.pdf", content_type: str = "application/pdf"
) -> SimpleUploadedFile:
    """Um upload com bytes escritos no teste, sem tocar no disco do repositório."""
    return SimpleUploadedFile(nome, conteudo, content_type=content_type)


def _criar(cliente: Client, conteudo: bytes | None = None, **kwargs: Any) -> Any:
    if conteudo is None:
        return cliente.post(URL, data={})
    return cliente.post(URL, data={"ficheiro": _ficheiro(conteudo, **kwargs)})


def _anexar(cliente: Client, documento_id: str, conteudo: bytes, **kwargs: Any) -> Any:
    return cliente.post(
        f"{URL}/{documento_id}/files", data={"ficheiro": _ficheiro(conteudo, **kwargs)}
    )


def _fechar(cliente: Client, documento_id: str) -> Any:
    return cliente.post(f"{URL}/{documento_id}/closing", data={})


def _recuar_criacao(tenant_id: UUID, documento_id: str, quanto: Any) -> None:
    """Põe o `created_at` no passado.

    Escreve por `update()` e fora de `services.py` de propósito, como o `_expirar`
    do `tests/test_convites.py`: não há caso de uso que envelheça um documento —
    ele envelhece pela passagem do tempo —, e a alternativa era um `freezegun` só
    para isto. É também o que torna o teste do estado derivado honesto: **nenhuma
    coluna de estado é escrita**, só o `created_at` recua.
    """
    with tenant_scope(tenant_id):
        InvoiceDocument.objects.filter(pk=documento_id).update(
            created_at=timezone.now() - quanto
        )


# ---------------------------------------------------------------------------
# 1. O caminho feliz, nos dois sentidos de entrada
# ---------------------------------------------------------------------------
def test_um_pdf_arrastado_no_desktop_fecha_se_a_si_mesmo(cenario: Cenario) -> None:
    """Um ficheiro na criação dá um documento `upload`, fechado, com uma página."""
    resposta = _criar(_cliente(cenario.ana, cenario.alfa.id), PDF_DE_UMA_PAGINA)

    assert resposta.status_code == 201, resposta.content
    corpo = resposta.json()
    assert corpo["source"] == OrigemDoDocumento.UPLOAD
    assert corpo["closed_at"] is not None
    assert corpo["page_count"] == 1
    assert corpo["page_limit"] == PAGINAS_POR_DOCUMENTO
    assert corpo["created_by"] == "Ana Silva"
    assert corpo["receipt"] is None
    assert len(corpo["files"]) == 1
    ficheiro = corpo["files"][0]
    assert ficheiro["content_type"] == "application/pdf"
    assert ficheiro["pages_detected"] == 1
    assert ficheiro["original_filename"] == "fatura.pdf"
    assert ficheiro["byte_size"] == len(PDF_DE_UMA_PAGINA)
    pagina = corpo["pages"][0]
    assert pagina["position"] == 1
    assert pagina["normalized"] is False
    assert pagina["width"] is None
    assert pagina["image_url"].endswith("/pages/1/image")


def test_o_slot_do_qr_nasce_vazio_aberto_e_invisivel_na_lista(cenario: Cenario) -> None:
    """Sem ficheiro é `capture`: aberto, zero páginas, e fora da lista.

    *"Um documento com zero páginas nunca aparece na lista do Receber"* (ADR
    0020, decisão 2) — mas o `GET` por `id` serve-o, porque é precisamente esse o
    estado que o desktop está a sondar enquanto espera pela fotografia.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    resposta = _criar(cliente)

    assert resposta.status_code == 201, resposta.content
    corpo = resposta.json()
    assert corpo["source"] == OrigemDoDocumento.CAPTURE
    assert corpo["closed_at"] is None
    assert corpo["page_count"] == 0
    assert corpo["state"] == EstadoDoDocumento.AGUARDA_CAPTURA

    assert cliente.get(URL).json()["results"] == []
    assert cliente.get(f"{URL}/{corpo['id']}").status_code == 200


def test_o_telemovel_anexa_duas_paginas_e_uma_pessoa_fecha(cenario: Cenario) -> None:
    """O fluxo da ponte: slot, duas páginas, fecho. E a ordem das páginas mantém-se."""
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente).json()["id"]

    primeira = _anexar(cliente, documento_id, JPEG, nome="folha1.jpg")
    assert primeira.status_code == 201, primeira.content
    assert primeira.json()["page_count"] == 1
    assert primeira.json()["state"] == EstadoDoDocumento.A_NORMALIZAR

    segunda = _anexar(cliente, documento_id, PNG, nome="folha2.png")
    assert segunda.status_code == 201, segunda.content
    corpo = segunda.json()
    assert corpo["page_count"] == 2
    assert [pagina["position"] for pagina in corpo["pages"]] == [1, 2]
    assert [f["content_type"] for f in corpo["files"]] == ["image/jpeg", "image/png"]

    fechado = _fechar(cliente, documento_id)
    assert fechado.status_code == 200, fechado.content
    assert fechado.json()["closed_at"] is not None

    # Agora aparece na lista: tem páginas.
    assert [d["id"] for d in cliente.get(URL).json()["results"]] == [documento_id]


def test_fechar_e_repetivel_e_nao_agenda_trabalho_duas_vezes(cenario: Cenario) -> None:
    """Dois toques no mesmo botão: 200 nas duas vezes, uma extração só.

    A idempotência observável de um duplo toque num telemóvel (ADR 0020, decisão
    1g). A contagem de extrações é o que prova que o segundo fecho não agendou
    nada — e é também a razão de `fechar_documento` sair cedo quando já está
    fechado.

    Desde 2026-10-08 o fecho publica um evento em vez de enfileirar (ver o
    `apps/shared/consumidor.py`), logo a passagem do consumidor está aqui: é ela
    que transforma os eventos em trabalho, e corrê-la **depois dos dois fechos**
    é o que torna o teste honesto — se o segundo fecho tivesse publicado uma
    segunda linha, haveria duas extrações.
    """
    from apps.agents.models import Extraction
    from apps.shared.consumidor import consumir_outbox

    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente).json()["id"]
    _anexar(cliente, documento_id, JPEG)

    primeiro = _fechar(cliente, documento_id)
    segundo = _fechar(cliente, documento_id)
    consumir_outbox()

    assert primeiro.status_code == 200
    assert segundo.status_code == 200
    assert primeiro.json()["closed_at"] == segundo.json()["closed_at"]
    with tenant_scope(cenario.alfa.id):
        assert Extraction.objects.filter(document_id=documento_id).count() == 1


# ---------------------------------------------------------------------------
# 2. Isolamento por estabelecimento
# ---------------------------------------------------------------------------
def test_um_documento_de_outro_estabelecimento_da_404_e_nao_403(cenario: Cenario) -> None:
    """O `id` de Alfa, com a sessão de Beta: 404 em **todas** as operações.

    404 e não 403 porque a linha não é legível: a política devolve zero linhas,
    logo não há objecto sobre o qual negar, e um 403 confirmaria a existência do
    documento a quem não o pode ver.

    E a mesma resposta para um `id` **inexistente**, porque é a diferença entre as
    duas respostas que diria a um estranho que aquele documento existe.
    """
    de_alfa = _criar(_cliente(cenario.ana, cenario.alfa.id), PDF_DE_UMA_PAGINA).json()
    beta = _cliente(cenario.dinis, cenario.beta.id)
    inexistente = str(uuid4())

    assert beta.get(f"{URL}/{de_alfa['id']}").status_code == 404
    assert beta.get(f"{URL}/{inexistente}").status_code == 404
    assert _anexar(beta, de_alfa["id"], JPEG).status_code == 404
    assert _fechar(beta, de_alfa["id"]).status_code == 404
    assert beta.delete(f"{URL}/{de_alfa['id']}").status_code == 404
    assert beta.get(f"{URL}/{de_alfa['id']}/pages/1/image").status_code == 404

    # A lista de Beta não o traz, e a de Alfa continua a trazê-lo: sem o
    # simétrico, o teste passava por vacuidade.
    assert beta.get(URL).json()["results"] == []
    alfa = _cliente(cenario.ana, cenario.alfa.id)
    assert [d["id"] for d in alfa.get(URL).json()["results"]] == [de_alfa["id"]]


def test_a_travessia_nao_escreve_nada_do_lado_de_alfa(cenario: Cenario) -> None:
    """Depois da tentativa de Beta, o documento de Alfa está intacto.

    O 404 podia vir **depois** de uma escrita, e um teste que só olhasse para o
    status não notava. A asserção é a contagem de ficheiros e de páginas do lado
    de Alfa.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente).json()["id"]

    assert _anexar(_cliente(cenario.dinis, cenario.beta.id), documento_id, JPEG).status_code == 404

    with tenant_scope(cenario.alfa.id):
        assert DocumentFile.objects.filter(document_id=documento_id).count() == 0
        assert DocumentPage.objects.filter(document_id=documento_id).count() == 0


# ---------------------------------------------------------------------------
# 3. A unicidade `(document, sha256)`
# ---------------------------------------------------------------------------
def test_a_mesma_pagina_enviada_duas_vezes_nao_cria_uma_segunda(cenario: Cenario) -> None:
    """A retentativa de uma rede má: 201, depois 200, e uma página só.

    E o nome do ficheiro **não** entra na identidade: a segunda tentativa chega
    com outro nome e com outro `Content-Type`, porque um telemóvel a repetir um
    upload não garante nenhum dos dois. O que identifica os bytes é o digest.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente).json()["id"]

    primeira = _anexar(cliente, documento_id, JPEG, nome="IMG_1.jpg")
    segunda = _anexar(
        cliente, documento_id, JPEG, nome="outro.jpeg", content_type="image/png"
    )

    assert primeira.status_code == 201, primeira.content
    assert segunda.status_code == 200, segunda.content
    assert segunda.json()["page_count"] == 1
    with tenant_scope(cenario.alfa.id):
        assert DocumentFile.objects.filter(document_id=documento_id).count() == 1
        assert DocumentPage.objects.filter(document_id=documento_id).count() == 1


def test_os_mesmos_bytes_em_dois_documentos_sao_dois_ficheiros(cenario: Cenario) -> None:
    """A unicidade é **por documento** e não global.

    A mesma fatura pode legitimamente chegar a dois documentos — alguém que se
    corrige, ou dois estabelecimentos do mesmo grupo —, e uma unicidade global
    transformava isso numa recusa inexplicável.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    primeiro = _criar(cliente).json()["id"]
    segundo = _criar(cliente).json()["id"]

    assert _anexar(cliente, primeiro, JPEG).status_code == 201
    assert _anexar(cliente, segundo, JPEG).status_code == 201


# ---------------------------------------------------------------------------
# 4. O verificador de bytes
# ---------------------------------------------------------------------------
def test_um_executavel_renomeado_para_pdf_e_recusado(cenario: Cenario) -> None:
    """`MZ` com extensão `.pdf` e `Content-Type` de PDF: 400, e nada escrito.

    É a metade mais importante do par: o nome e o header dizem PDF, os bytes
    dizem executável, e quem decide são os bytes.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    resposta = _criar(cliente, EXECUTAVEL, nome="fatura.pdf")

    assert resposta.status_code == 400, resposta.content
    assert "ficheiro" in resposta.json()
    with tenant_scope(cenario.alfa.id):
        assert InvoiceDocument.objects.count() == 0


def test_um_pdf_com_content_type_mentiroso_e_aceite(cenario: Cenario) -> None:
    """Bytes de PDF e `Content-Type: text/plain`: **aceite**, e gravado como PDF.

    Prova que o header do cliente é **ignorado** e não validado — que é a decisão
    4 da ADR 0020 e a diferença entre esta implementação e uma que comparasse os
    dois.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    resposta = _criar(
        cliente, PDF_DE_UMA_PAGINA, nome="qualquer.coisa", content_type="text/plain"
    )

    assert resposta.status_code == 201, resposta.content
    assert resposta.json()["files"][0]["content_type"] == "application/pdf"


def test_os_formatos_fora_da_lista_fechada_sao_recusados(cenario: Cenario) -> None:
    """SVG (que é script), ZIP e zero bytes: 400 nos três.

    A lista aceite tem três entradas e está fechada no `ficheiros.py`; o que esta
    asserção mede é que ela **é** fechada, e não uma sugestão.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    assert _criar(cliente, SVG, nome="fatura.svg").status_code == 400
    assert _criar(cliente, b"PK\x03\x04" + b"\x00" * 64, nome="f.zip").status_code == 400
    assert _criar(cliente, b"", nome="vazio.pdf").status_code == 400
    assert tuple(TIPOS_ACEITES) == ("application/pdf", "image/jpeg", "image/png")


# ---------------------------------------------------------------------------
# 5. Os dois tetos
# ---------------------------------------------------------------------------
def test_o_decimo_primeiro_ficheiro_e_recusado(cenario: Cenario) -> None:
    """Dez páginas entram, a décima primeira não. Com o código de recusa."""
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente).json()["id"]

    for numero in range(PAGINAS_POR_DOCUMENTO):
        bytes_unicos = JPEG + bytes([numero])
        resposta = _anexar(cliente, documento_id, bytes_unicos, nome=f"{numero}.jpg")
        assert resposta.status_code == 201, resposta.content

    excedente = _anexar(cliente, documento_id, JPEG + b"excedente", nome="x.jpg")

    assert excedente.status_code == 400, excedente.content
    assert excedente.json()["code"] == "paginas_excedidas"
    assert excedente.json()["detail"] == "Um documento aceita no máximo 10 páginas."
    assert cliente.get(f"{URL}/{documento_id}").json()["page_count"] == 10


def test_um_pdf_com_mais_paginas_do_que_o_teto_e_recusado(cenario: Cenario) -> None:
    """Um PDF de vinte páginas é recusado **à entrada**, por campo.

    É o gate da ADR 0020 ("20 páginas") e passa pelo contador em Python puro, que
    é o que este projecto tem no lugar do `pypdf`.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    resposta = _criar(cliente, pdf_com(20), nome="rolo.pdf")

    assert resposta.status_code == 400, resposta.content
    assert "ficheiro" in resposta.json()


def test_um_ficheiro_grande_e_recusado_com_uma_frase_da_aplicacao(cenario: Cenario) -> None:
    """Acima do teto: 400 com uma frase da aplicação, e nada escrito.

    O teto está repetido no `docker/caddy/proxy.Caddyfile` **de propósito**: em
    desenvolvimento não há proxy, e a frase que uma pessoa lê é a da aplicação. É
    por isso que o que se mede aqui é o corpo da resposta e não só o status.

    A frase traz o número e o número vem da constante, logo este teste não o
    repete — repeti-lo era escrever o teto em dois sítios, que é precisamente o
    defeito que o teste seguinte mede.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    grande = PDF_DE_UMA_PAGINA + b"\x00" * (TAMANHO_MAXIMO_DO_FICHEIRO + 1)
    assert len(grande) > TAMANHO_MAXIMO_DO_FICHEIRO

    resposta = _criar(cliente, grande, nome="enorme.pdf")

    assert resposta.status_code == 400, resposta.content
    assert resposta.json()["ficheiro"] == [
        f"Este ficheiro é maior do que {TAMANHO_MAXIMO_DO_FICHEIRO // (1024 * 1024)} MiB."
    ]
    with tenant_scope(cenario.alfa.id):
        assert InvoiceDocument.objects.count() == 0


#: As unidades que o Caddy lê, e **o que cada uma vale**. O `go-humanize` segue
#: o SI: `MB` é 10⁶ e `MiB` é 2²⁰. É exactamente nesta diferença que a primeira
#: versão desta feature tropeçou.
_UNIDADES_DO_CADDY = {
    "B": 1,
    "KB": 1_000,
    "MB": 1_000_000,
    "GB": 1_000_000_000,
    "KIB": 1024,
    "MIB": 1024**2,
    "GIB": 1024**3,
}


def test_o_teto_da_app_fica_estritamente_abaixo_do_teto_do_proxy() -> None:
    """A ordem entre os dois tetos, lida dos dois sítios — e falha nos dois sentidos.

    **Este teste existe por causa de um erro que aconteceu.** A primeira versão
    pôs o teto da aplicação em 12 MiB "para ser o mesmo número do proxy", e não
    era: o `12MB` do Caddy são 12 000 000 bytes e 12 MiB são 12 582 912. Um
    ficheiro entre os dois era recusado pelo **proxy**, com um 413 sem corpo
    JSON — exactamente o caso que a constante da aplicação existe para cobrir.

    O que se afirma é a **ordem** e não a igualdade: quem recusa primeiro tem de
    ser quem tem uma frase para mostrar. Subir o do proxy sem subir este, ou
    subir este acima daquele, falha aqui.

    Lê o Caddyfile por regex e não por um parser: é uma linha de configuração, e
    uma dependência nova para ler `max_size 12MB` seria pior do que o problema.
    """
    caddyfile = (
        pathlib.Path(__file__).resolve().parents[2] / "docker/caddy/proxy.Caddyfile"
    ).read_text(encoding="utf-8")

    achado = re.search(r"max_size\s+(\d+)\s*([KMG]i?B|B)\b", caddyfile, re.IGNORECASE)
    assert achado is not None, (
        "não encontrei o `max_size` no proxy.Caddyfile. Se ele mudou de nome ou "
        "desapareceu, este teste deixou de medir o que diz medir — arranja-o em vez "
        "de o apagar, porque sem ele o teto da aplicação volta a poder passar o do proxy."
    )
    escrito = f"{achado.group(1)}{achado.group(2)}"
    do_proxy = int(achado.group(1)) * _UNIDADES_DO_CADDY[achado.group(2).upper()]

    assert TAMANHO_MAXIMO_DO_FICHEIRO < do_proxy, (
        f"o teto da aplicação ({TAMANHO_MAXIMO_DO_FICHEIRO} bytes) não está abaixo do "
        f"teto do proxy ({do_proxy} bytes, de `max_size {escrito}`). Entre os dois "
        "valores a recusa vem do Caddy, com um 413 sem corpo JSON, e o ecrã não tem "
        "frase nenhuma para mostrar a quem acabou de fotografar uma fatura."
    )


# ---------------------------------------------------------------------------
# 6. O estado derivado
# ---------------------------------------------------------------------------
def test_um_slot_sem_paginas_com_quinze_minutos_le_se_expirado(cenario: Cenario) -> None:
    """O mesmo documento, sem nenhuma escrita entretanto: `aguarda_captura`, depois
    `expirado`.

    **É o teste do estado derivado.** O que muda entre as duas leituras é o
    `created_at` — recuado por um `update()` que não toca em nenhuma coluna de
    estado, porque não existe nenhuma. Se um dia alguém acrescentar uma coluna
    `state`, este teste continua verde e passa a estar a medir a coluna; é por
    isso que ele afirma também que a resposta **não** tem campo nenhum guardado a
    dizer o contrário do relógio.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente).json()["id"]

    assert cliente.get(f"{URL}/{documento_id}").json()["state"] == (
        EstadoDoDocumento.AGUARDA_CAPTURA
    )

    _recuar_criacao(cenario.alfa.id, documento_id, JANELA_DO_SLOT)

    corpo = cliente.get(f"{URL}/{documento_id}").json()
    assert corpo["state"] == EstadoDoDocumento.EXPIRADO
    assert corpo["page_count"] == 0
    # O `expires_at` é derivado do `created_at` e acompanhou-o: um valor guardado
    # teria ficado no futuro. Comparado como instante e não como string — as duas
    # pontas podem estar em fusos diferentes e `"19:44+01:00" < "18:44+00:00"` é
    # falso sobre dois instantes iguais.
    assert datetime.fromisoformat(corpo["expires_at"]) <= timezone.now()


def test_um_documento_descartado_le_se_descartado_e_sai_da_lista(cenario: Cenario) -> None:
    """O `DELETE` é um descarte suave: 204, estado `descartado`, fora da lista."""
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente, PDF_DE_UMA_PAGINA).json()["id"]

    assert cliente.delete(f"{URL}/{documento_id}").status_code == 204

    assert cliente.get(f"{URL}/{documento_id}").json()["state"] == (
        EstadoDoDocumento.DESCARTADO
    )
    assert cliente.get(URL).json()["results"] == []
    with tenant_scope(cenario.alfa.id):
        assert InvoiceDocument.objects.filter(pk=documento_id).exists()


def test_descartar_duas_vezes_nao_levanta(cenario: Cenario) -> None:
    """Repetível, como o fecho: um duplo toque não é um erro."""
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente, PDF_DE_UMA_PAGINA).json()["id"]

    assert cliente.delete(f"{URL}/{documento_id}").status_code == 204
    assert cliente.delete(f"{URL}/{documento_id}").status_code == 204


def test_descartar_um_documento_com_paginas_nao_apaga_os_bytes(cenario: Cenario) -> None:
    """*"Só apaga bytes se não houver páginas"* (ADR 0021, decisão 9).

    A razão não é simetria: apagar a imagem de uma fatura é apagar o original de
    um documento fiscal, e quanto tempo ele se guarda é a segunda pergunta que o
    dono ainda não respondeu.
    """
    from pathlib import Path

    from django.conf import settings

    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente, PDF_DE_UMA_PAGINA).json()["id"]
    with tenant_scope(cenario.alfa.id):
        caminho = DocumentFile.objects.get(document_id=documento_id).path
    assert (Path(settings.MEDIA_ROOT) / caminho).is_file()

    cliente.delete(f"{URL}/{documento_id}")

    assert (Path(settings.MEDIA_ROOT) / caminho).is_file()


# ---------------------------------------------------------------------------
# 7. As recusas de escrita num documento que já não aceita
# ---------------------------------------------------------------------------
def test_anexar_a_um_documento_fechado_da_409(cenario: Cenario) -> None:
    """Um ficheiro fecha-se a si mesmo, logo o segundo ficheiro é uma recusa.

    É a consequência de *"um ficheiro é um documento, com N páginas"* (ADR 0020,
    decisão 5): quem quer duas folhas abre um slot e anexa duas vezes.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente, PDF_DE_UMA_PAGINA).json()["id"]

    resposta = _anexar(cliente, documento_id, JPEG)

    assert resposta.status_code == 409, resposta.content
    assert resposta.json()["code"] == "documento_fechado"


def test_escrever_num_documento_descartado_da_409(cenario: Cenario) -> None:
    """Descartar é dizer "isto não interessa"; voltar a escrever-lhe é um engano."""
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente).json()["id"]
    cliente.delete(f"{URL}/{documento_id}")

    assert _anexar(cliente, documento_id, JPEG).json()["code"] == "documento_descartado"
    assert _fechar(cliente, documento_id).json()["code"] == "documento_descartado"


def test_fechar_um_documento_vazio_da_409(cenario: Cenario) -> None:
    """Fechar é "não vêm mais páginas", e de um documento vazio é uma extração de
    nada."""
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente).json()["id"]

    resposta = _fechar(cliente, documento_id)

    assert resposta.status_code == 409, resposta.content
    assert resposta.json()["code"] == "documento_sem_paginas"


def test_o_mapa_de_status_cobre_a_lista_fechada_de_recusas() -> None:
    """Um código sem entrada no mapa apareceria como 500.

    A lista vive no `services.py` (que é quem levanta) e o mapa no `views.py` (que
    é quem sabe HTTP). Fechar os dois conjuntos um contra o outro é o que impede
    um código novo de se tornar um erro de servidor.
    """
    assert set(STATUS_DA_RECUSA_DE_DOCUMENTO) == set(CODIGOS_DE_RECUSA_DE_DOCUMENTO)


# ---------------------------------------------------------------------------
# 8. Permissões
# ---------------------------------------------------------------------------
def test_um_staff_faz_o_ciclo_todo(cenario: Cenario) -> None:
    """Qualquer membro activo envia, fecha e descarta (ADR 0021, decisão 9).

    *"Receber mercadoria é trabalho de quem está lá"* (ADR 0020, decisão 1b). Este
    teste é o que falha se alguém puser um `TemPapel` nesta view — e o descarte
    está aqui de propósito, porque é a única permissão desta fatia que a ADR deixou
    por decidir: o default é este, e é este que se mede.
    """
    cliente = _cliente(cenario.carla, cenario.alfa.id)

    documento_id = _criar(cliente).json()["id"]
    assert _anexar(cliente, documento_id, JPEG).status_code == 201
    assert _fechar(cliente, documento_id).status_code == 200
    assert cliente.delete(f"{URL}/{documento_id}").status_code == 204
    with tenant_scope(cenario.alfa.id):
        assert InvoiceDocument.objects.get(pk=documento_id).created_by_name == "Carla Reis"


def test_sem_sessao_nao_se_chega_ao_recurso(cenario: Cenario) -> None:
    """Anónimo: 403 do `TenantMiddleware`, antes de qualquer view.

    403 e não 404 porque não há `pk` nenhum em jogo — a recusa é sobre não haver
    estabelecimento na sessão, e é a mesma de todos os endpoints com âmbito.
    """
    anonimo = Client()

    assert anonimo.get(URL).status_code == 403
    assert anonimo.post(URL, data={}).status_code == 403


def test_uma_sessao_sem_estabelecimento_activo_e_recusada(cenario: Cenario) -> None:
    """Com conta e sem estabelecimento na sessão: 403 `sem_sessao`."""
    cliente = Client()
    cliente.force_login(cenario.ana, backend=BACKEND_DE_SESSAO)

    resposta = cliente.get(URL)

    assert resposta.status_code == 403
    assert resposta.json()["code"] == "sem_sessao"


# ---------------------------------------------------------------------------
# 9. Os bytes da imagem
# ---------------------------------------------------------------------------
def test_a_imagem_de_uma_pagina_sem_normalizacao_da_404(
    cenario: Cenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uma página sem normalização dá 404, e a ausência é **encenada**.

    O `monkeypatch` é a correcção de um defeito deste teste, não um adorno: ele
    media a ausência de rasterizador **do ambiente** — passava num portátil sem a
    libvips e falhava no CI, que a instala de propósito. Um teste cujo veredicto
    depende do que está instalado na máquina não afirma nada sobre o código.

    O que se afirma é o que o nome diz: **sem `image_path`, 404**. Vale também
    para uma posição que não existe, e os dois casos têm de ser indistinguíveis
    de fora.
    """
    import apps.purchasing.tasks as tarefas
    from apps.shared.consumidor import consumir_outbox

    def sem_rasterizador(**_: object) -> ImagemNormalizada:
        raise RasterizadorIndisponivel("encenado por este teste")

    monkeypatch.setattr(tarefas, "rasterizar", sem_rasterizador)

    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente, PDF_DE_UMA_PAGINA).json()["id"]
    # A passagem do consumidor é o que faz a rasterização ser **tentada** — sem
    # ela a página ficava sem imagem por ninguém ter pedido, e o teste passava
    # por uma razão que não é a que ele mede. Com ela, a ausência de imagem é do
    # rasterizador encenado, que é o que o nome do teste afirma.
    consumir_outbox()

    assert cliente.get(f"{URL}/{documento_id}/pages/1/image").status_code == 404
    assert cliente.get(f"{URL}/{documento_id}/pages/9/image").status_code == 404


def test_a_imagem_normalizada_sai_inline_com_nosniff(
    cenario: Cenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com a fronteira da rasterização substituída, o caminho completo corre.

    Substitui-se a **fronteira** e não um decoder: é para isso que ela tem nome
    próprio. O que o teste mede depois disso é tudo o que a ADR 0021 pede desta
    view — `image/webp`, `inline`, `nosniff`, `private` — mais a geometria a
    chegar à resposta do documento.
    """
    import apps.purchasing.tasks as tarefas
    from apps.purchasing.tasks import normalizar_pagina

    monkeypatch.setattr(
        tarefas,
        "rasterizar",
        lambda **_: ImagemNormalizada(webp=b"RIFF-nao-e-um-webp-a-serio", width=1240, height=1754),
    )

    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente, PDF_DE_UMA_PAGINA).json()["id"]
    with tenant_scope(cenario.alfa.id):
        pagina_id = DocumentPage.objects.get(document_id=documento_id).id
    assert normalizar_pagina(tenant_id=str(cenario.alfa.id), pagina_id=str(pagina_id)) == (
        "normalizada"
    )

    corpo = cliente.get(f"{URL}/{documento_id}").json()
    assert corpo["pages"][0]["normalized"] is True
    assert corpo["pages"][0]["width"] == 1240
    assert corpo["pages"][0]["height"] == 1754

    imagem = cliente.get(f"{URL}/{documento_id}/pages/1/image")
    assert imagem.status_code == 200
    assert imagem["Content-Type"] == "image/webp"
    assert imagem["Content-Disposition"] == "inline"
    assert imagem["X-Content-Type-Options"] == "nosniff"
    assert "private" in imagem["Cache-Control"]
    assert b"".join(imagem.streaming_content) == b"RIFF-nao-e-um-webp-a-serio"


def test_a_tarefa_de_normalizacao_nao_rebenta_sem_rasterizador(
    cenario: Cenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem rasterizador a tarefa devolve um estado e não uma excepção.

    E a página fica **sem** `normalized_at`: nada mente, não há uma coluna de
    "normalizada" escrita sem imagem por baixo.

    A ausência é **encenada** e não ambiental, pela razão escrita no teste do 404:
    este media o que estava instalado na máquina, e por isso passava sem a libvips
    e falhava com ela. O ramo que interessa — a tarefa a traduzir uma dependência
    em falta num estado — existe nos dois mundos e tem de ser testado nos dois.
    """
    import apps.purchasing.tasks as tarefas
    from apps.purchasing.tasks import normalizar_pagina

    def sem_rasterizador(**_: object) -> ImagemNormalizada:
        raise RasterizadorIndisponivel("encenado por este teste")

    monkeypatch.setattr(tarefas, "rasterizar", sem_rasterizador)

    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente, PDF_DE_UMA_PAGINA).json()["id"]
    with tenant_scope(cenario.alfa.id):
        pagina = DocumentPage.objects.get(document_id=documento_id)

    resultado = normalizar_pagina(
        tenant_id=str(cenario.alfa.id), pagina_id=str(pagina.id)
    )

    assert resultado == "sem_rasterizador"
    with tenant_scope(cenario.alfa.id):
        assert DocumentPage.objects.get(pk=pagina.id).normalized_at is None


# ---------------------------------------------------------------------------
# 10. O nome do ficheiro no disco, e o QR
# ---------------------------------------------------------------------------
def test_o_nome_do_cliente_nunca_chega_ao_disco(cenario: Cenario) -> None:
    """Um `original_filename` com travessia de caminho fica rótulo e mais nada.

    O `path` é gerado a partir de uuid e da extensão do **tipo real**, logo não
    contém nada que tenha vindo do pedido (SECURITY.md §4). O nome do cliente
    guarda-se para a pessoa reconhecer o que enviou.
    """
    from pathlib import Path

    from django.conf import settings

    nome_mau = "../../../../etc/passwd.pdf"
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    corpo = _criar(cliente, PDF_DE_UMA_PAGINA, nome=nome_mau).json()

    with tenant_scope(cenario.alfa.id):
        ficheiro = DocumentFile.objects.get(document_id=corpo["id"])
    assert ".." not in ficheiro.path
    assert "passwd" not in ficheiro.path
    assert ficheiro.path.endswith(".pdf")
    assert ficheiro.path.startswith(f"documentos/{cenario.alfa.id}/{corpo['id']}/")
    # O nome do cliente sobrevive como rótulo — e o Django já lhe tira os
    # directórios no `SimpleUploadedFile`, o que é a segunda rede e não a
    # primeira.
    assert "passwd" in corpo["files"][0]["original_filename"]
    assert (Path(settings.MEDIA_ROOT) / ficheiro.path).is_file()


def test_o_qr_de_uma_pagina_nasce_vazio_e_ninguem_o_escreve(cenario: Cenario) -> None:
    """A coluna existe, está vazia, e não há código que lhe escreva.

    A coluna é grátis hoje; a descodificação é uma dependência que ainda não foi
    decidida (ADR 0021, adenda). A segunda metade da asserção é uma varredura do
    código: o dia em que alguém escrever no `qr_payload` é um diff que faz este
    teste falhar, e é onde a decisão da dependência tem de ser tomada.
    """
    import pathlib

    from django.conf import settings

    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = _criar(cliente, PDF_DE_UMA_PAGINA).json()["id"]
    with tenant_scope(cenario.alfa.id):
        assert DocumentPage.objects.get(document_id=documento_id).qr_payload == ""

    mencionam = sorted(
        str(caminho.relative_to(settings.BASE_DIR))
        for caminho in pathlib.Path(settings.BASE_DIR, "apps").rglob("*.py")
        if "migrations" not in caminho.parts
        and "qr_payload" in caminho.read_text(encoding="utf-8")
    )
    assert mencionam == [
        # o campo do DTO que atravessa a fronteira para o `agents`
        "apps/purchasing/extracao.py",
        # a declaração da coluna, com a razão de ela entrar hoje
        "apps/purchasing/models.py",
        # a **leitura** que preenche esse campo
        "apps/purchasing/selectors.py",
    ], (
        f"a lista de ficheiros que tocam no qr_payload mudou ({mencionam}). As "
        "três entradas de cima são declarações e leituras; uma escrita quer "
        "dizer que alguém descodificou um QR, e a biblioteca que o faz é uma "
        "dependência que ainda não foi decidida — ver a adenda da ADR 0021."
    )


# ---------------------------------------------------------------------------
# 11. A limpeza dos slots (a tarefa que não corre)
# ---------------------------------------------------------------------------
def test_a_limpeza_apaga_slots_vazios_e_expirados_e_mais_nada(cenario: Cenario) -> None:
    """Três documentos, um apagado: o slot vazio e expirado.

    A tarefa existe e tem teste; **não corre**, porque não há `beat` neste
    projecto (dívida nomeada no `SESSION-CONTEXT.md` e na ADR 0021). O que este
    teste garante é que, no dia em que correr, não apaga um documento com páginas
    nem um slot ainda dentro do relógio.
    """
    from apps.purchasing.tasks import limpar_slots_expirados_do_tenant

    cliente = _cliente(cenario.ana, cenario.alfa.id)
    vazio_e_velho = _criar(cliente).json()["id"]
    vazio_e_novo = _criar(cliente).json()["id"]
    com_paginas = _criar(cliente, PDF_DE_UMA_PAGINA).json()["id"]
    _recuar_criacao(cenario.alfa.id, vazio_e_velho, JANELA_DO_SLOT * 2)
    _recuar_criacao(cenario.alfa.id, com_paginas, JANELA_DO_SLOT * 2)

    apagados = limpar_slots_expirados_do_tenant(tenant_id=str(cenario.alfa.id))

    assert apagados == 1
    with tenant_scope(cenario.alfa.id):
        restantes = set(InvoiceDocument.objects.values_list("id", flat=True))
    assert restantes == {UUID(vazio_e_novo), UUID(com_paginas)}


# ---------------------------------------------------------------------------
# 12. O custo da listagem, em queries
# ---------------------------------------------------------------------------
def test_a_listagem_custa_o_mesmo_com_um_ou_com_quatro_documentos(
    cenario: Cenario,
) -> None:
    """O número de queries da lista **não cresce** com o número de documentos.

    É a asserção que protege a decisão de compor a página em lote (ver o `list`
    do `views.py`): sem ela, cada documento atravessava a fronteira do `agents`
    por sua conta e uma página de cinquenta custava cinquenta queries a mais. Com
    ela, acrescentar um `select_related` esquecido ou um acesso a uma relação
    dentro do serializer passa a ser um teste vermelho.

    O que se compara são **dois cenários** e não um número absoluto: o valor
    exacto depende da sessão, do `Membership` e do `COUNT` da paginação, e fixá-lo
    tornava este teste um alarme em cada alteração ao middleware.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    cliente = _cliente(cenario.ana, cenario.alfa.id)
    _criar(cliente, PDF_DE_UMA_PAGINA, nome="um.pdf")
    with CaptureQueriesContext(connection) as com_um:
        assert len(cliente.get(URL).json()["results"]) == 1

    for numero in range(3):
        _criar(cliente, PDF_DE_UMA_PAGINA + bytes([numero]), nome=f"{numero}.pdf")
    with CaptureQueriesContext(connection) as com_quatro:
        assert len(cliente.get(URL).json()["results"]) == 4

    assert len(com_quatro) == len(com_um), (
        f"a listagem passou de {len(com_um)} para {len(com_quatro)} queries ao "
        "crescer de 1 para 4 documentos: há um N+1 novo. As páginas e os "
        "ficheiros vêm por `Prefetch` e as extrações por **uma** chamada ao "
        "porto — ver o `list` do views.py e o `compor_muitos` do selectors.py."
    )


# ---------------------------------------------------------------------------
# 9. O throttle, que é o teto de custo nomeado
# ---------------------------------------------------------------------------
def test_o_throttle_vive_nas_escritas_e_nao_nas_leituras() -> None:
    """As duas metades da decisão, e sem elas não havia gate nenhum.

    O `ScopedRateThrottle` é o controlo que a ADR 0021 (decisão 9) e as
    consequências da ADR 0020 nomeiam como teto de custo — e **a única menção
    dele nos testes era a fixture que limpa a cache entre eles**, o que significa
    que tirar o `get_throttles` não punha nada vermelho. Isto fecha-o.

    Afirma duas coisas e as duas são decisão:

    1. **as escritas são travadas.** O balde é por âmbito e o limite está no
       `DEFAULT_THROTTLE_RATES`, logo o que se mede aqui é que o throttle está
       montado e que o âmbito existe na configuração — um âmbito sem taxa é um
       throttle que não trava nada e o DRF não se queixa;
    2. **as leituras não entram no mesmo balde.** O `GET` é o alvo do polling de
       2 s da ADR 0020: se ele contasse, vinte segundos de espera por uma
       rasterização gastavam o orçamento de uploads do minuto.

    Não gasta 21 pedidos a provocar um 429: o que se mede é a montagem, porque é
    ela que alguém apaga sem querer. O comportamento do `ScopedRateThrottle` é do
    DRF e tem os testes dele.
    """
    from rest_framework.settings import api_settings
    from rest_framework.throttling import ScopedRateThrottle

    from apps.purchasing.views import AMBITO_DO_THROTTLE, DocumentoViewSet

    assert AMBITO_DO_THROTTLE in api_settings.DEFAULT_THROTTLE_RATES, (
        f"o âmbito {AMBITO_DO_THROTTLE!r} não tem taxa no `DEFAULT_THROTTLE_RATES`: "
        "o `ScopedRateThrottle` deixa passar tudo e o DRF não se queixa."
    )
    assert DocumentoViewSet.throttle_scope == AMBITO_DO_THROTTLE

    def montados(metodo: str) -> list[type]:
        vista = DocumentoViewSet()
        vista.request = type("Pedido", (), {"method": metodo})()  # type: ignore[assignment]
        return [type(t) for t in vista.get_throttles()]

    assert ScopedRateThrottle in montados("POST"), (
        "as escritas de `/documents` deixaram de ter o `ScopedRateThrottle`: um "
        "membro autenticado passa a poder escrever sem teto, a 11 MiB por ficheiro."
    )
    assert ScopedRateThrottle not in montados("GET"), (
        "o `GET` passou a contar no balde das escritas, e ele é o alvo do polling "
        "de 2 s da ADR 0020: a espera por uma rasterização passa a gastar o "
        "orçamento de uploads."
    )


# ---------------------------------------------------------------------------
# 10. O rasterizador, de verdade
# ---------------------------------------------------------------------------
def test_rasterizar_um_pdf_da_um_webp_que_nao_amplia() -> None:
    """A única dependência nativa deste projecto, exercitada a sério.

    **Salta onde a libvips não existe** (uma máquina de desenvolvimento sem o
    `libvips42`) e corre no CI, que a instala de propósito — o passo "libvips" do
    `.github/workflows/ci.yml` existe por causa deste teste. Sem ele, um `skip`
    verde era indistinguível de um teste que passa, e a única peça nativa ficava
    sem gate nenhum.

    Afirma três coisas, e as três são decisão e não mecanismo:

    1. **sai WebP**, que é o único formato que o endpoint da imagem serve — um
       JPEG servido como `image/webp` era um ficheiro que o browser recusa;
    2. **não amplia.** O PDF de ensaio é minúsculo; com `size="down"` a saída fica
       pelo tamanho natural da página e não esticada até 2000px. Ampliar não
       acrescenta informação e multiplica os bytes;
    3. **a geometria devolvida é a da imagem**, porque é ela que vai para as
       colunas `width`/`height` e daí para o `<img>` do ecrã de revisão — se
       mentir, o ecrã salta quando a imagem carrega.
    """
    from apps.purchasing.ficheiros import caminho_dentro_do_media
    from apps.purchasing.rasterizacao import LADO_MAXIMO, ha_rasterizador, rasterizar

    if not ha_rasterizador():
        pytest.skip("sem libvips neste ambiente: o CI instala-a de propósito")

    relativo = "documentos/ensaio/rasterizar/pagina.pdf"
    destino = caminho_dentro_do_media(relativo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(PDF_DE_UMA_PAGINA)

    imagem = rasterizar(caminho=relativo, numero_da_pagina=1)

    # O cabeçalho de um WebP: "RIFF" + 4 bytes de tamanho + "WEBP".
    assert imagem.webp[:4] == b"RIFF", imagem.webp[:16]
    assert imagem.webp[8:12] == b"WEBP", imagem.webp[:16]
    assert 0 < imagem.width <= LADO_MAXIMO
    assert 0 < imagem.height <= LADO_MAXIMO
    assert len(imagem.webp) > 0


def test_rasterizar_um_ficheiro_que_nao_e_imagem_diz_que_a_pagina_e_ilegivel() -> None:
    """Lixo no disco é `PaginaIlegivel` e **não** uma tarefa em falha.

    A diferença entre esta excepção e a `RasterizadorIndisponivel` é a diferença
    entre "falta instalar" e "este documento não serve", e é ela que impede um PDF
    truncado a meio de um upload de aparecer como avaria da infraestrutura.
    """
    from apps.purchasing.ficheiros import caminho_dentro_do_media
    from apps.purchasing.rasterizacao import PaginaIlegivel, ha_rasterizador, rasterizar

    if not ha_rasterizador():
        pytest.skip("sem libvips neste ambiente: o CI instala-a de propósito")

    relativo = "documentos/ensaio/rasterizar/lixo.pdf"
    destino = caminho_dentro_do_media(relativo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(b"%PDF-1.4\nisto nao e um PDF\n")

    with pytest.raises(PaginaIlegivel):
        rasterizar(caminho=relativo, numero_da_pagina=1)
