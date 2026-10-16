"""O mapa fechado tool → ecrã: as acções de interface de um turno (ADR 0028, d3).

**O modelo não pede rotas nem escreve URLs.** As acções derivam-se, à leitura,
das tools que o turno chamou e dos argumentos **já revalidados** (`rasto.py`),
por este mapa em código. Não há URL injectável porque não há URL vinda do
modelo; não há coluna nova porque isto é derivado como o `estado_derivado` de um
documento.

## O que é uma acção

`{rota, parametros, rotulo_id}`. `rota` é um id de uma lista fechada e
`rotulo_id` resolve-se no catálogo do cliente — **nenhum rótulo nosso viaja no
arame** (ADR 0019). `parametros` leva tudo o que o cliente precisa para montar a
ligação: os parâmetros de caminho (o `artigo` de `/stock/<artigo>`) e os de
procura (`?ver=falta`), e os de procura são **exactamente** os que os schemas
Zod das rotas aceitam hoje. Um teste nas duas pontas falha quando divergem.

## O filtro por papel

Um botão para um ecrã que o papel não vê não sai. Para as rotas do menu quem
decide é o registo de rotas do `accounts/menu.py` — a mesma lista que filtra a
sidebar —, lido pela porta (`accounts.api.papeis_da_rota`), e para as que não
estão no menu (o detalhe de um artigo, o detalhe de uma receção, as Definições)
a entrada declara o conjunto, herdado do ecrã que a serve. O `assistente` tem
conjunto vazio no registo (não tem entrada de menu, ADR 0027 d10, segunda
adenda), logo nunca sai botão para ele — e é a resposta certa: já se está lá.

## A ajuda

`ajuda_sobre(tema)` é a única tool que não lê dados: lê um manual curado por nós
em `ajuda/<lingua>/<tema>.md`. O índice de temas vive aqui, ao lado da rota de
cada um, porque é a mesma afirmação: **o tema é o sítio onde a coisa se faz**.
Um tema sem rota é um tema cujo ecrã ainda não existe, e isso diz-se.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from apps.accounts.api import Papel, papeis_da_rota

__all__ = [
    "LINGUAS_DA_AJUDA",
    "PARAMETROS_POR_ROTA",
    "ROTAS",
    "ROTULOS",
    "TEMAS",
    "Acao",
    "Destino",
    "acoes_do_turno",
    "indice_de_temas",
    "texto_de_ajuda",
]

TODOS_OS_PAPEIS: frozenset[str] = frozenset(Papel.values)
SO_O_DONO: frozenset[str] = frozenset({Papel.OWNER})

#: As rotas que uma acção pode nomear. As sete primeiras são o `RotaDeMenu` do
#: `accounts/models.py`; as três últimas são rotas que existem na árvore do
#: cliente e **não** no menu: o detalhe de um artigo, o detalhe de uma receção e
#: as Definições. Um id fora desta lista não sai no contrato.
ROTAS: tuple[str, ...] = (
    "inicio",
    "painel",
    "alertas",
    "assistente",
    "stock",
    "artigo",
    "contar",
    "receber",
    "rececao",
    "definicoes",
)

#: Os parâmetros que cada rota aceita — os mesmos dos schemas Zod do cliente
#: (`frontend/src/routes/busca-de-*.ts`) mais o parâmetro de caminho das rotas
#: de detalhe. O teste das duas pontas compara esta tabela com os `z.enum`.
PARAMETROS_POR_ROTA: Mapping[str, frozenset[str]] = {
    "inicio": frozenset(),
    "painel": frozenset({"period", "month", "aba", "explicar"}),
    "alertas": frozenset({"ver", "periodo"}),
    "assistente": frozenset({"conversa"}),
    "stock": frozenset({"loja", "filtro", "q"}),
    "artigo": frozenset({"artigo"}),
    "contar": frozenset({"zona"}),
    "receber": frozenset({"estado"}),
    "rececao": frozenset({"rececao"}),
    "definicoes": frozenset({"secao"}),
}

#: Os valores fechados de cada parâmetro de enum, pela mesma fonte. Um parâmetro
#: que não esteja aqui é livre (um `q`, um uuid) e o mapa abaixo nunca o produz
#: a partir de texto do modelo — só de um id que uma tool já validou.
VALORES_POR_PARAMETRO: Mapping[str, frozenset[str]] = {
    "ver": frozenset({"expira", "falta", "desperdicio"}),
    "periodo": frozenset({"hoje", "semana"}),
    "filtro": frozenset({"falta", "validade"}),
    "estado": frozenset({"revisao", "hoje"}),
    "secao": frozenset({"aparencia", "estabelecimento", "navegacao", "equipa"}),
    "period": frozenset({"today", "7d", "30d", "month", "prev_month"}),
    "aba": frozenset({"dinheiro", "perdas", "pessoal"}),
    "explicar": frozenset({"1"}),
}

#: Os ids de rótulo que o cliente resolve no seu catálogo. Lista fechada: um
#: `rotulo_id` que o cliente não conheça é um botão sem palavra.
ROTULOS: tuple[str, ...] = (
    "ver_artigo",
    "ver_falta",
    "ver_validade",
    "ver_desperdicio",
    "ver_alertas",
    "rever_rececoes",
    "ver_rececoes_de_hoje",
    "ver_rececoes",
    "ver_rececao",
    "ver_contagens",
    "ver_painel",
    "ver_stock",
    "ver_equipa",
    "ver_estabelecimento",
    "ver_inicio",
)


@dataclass(frozen=True, kw_only=True, slots=True)
class Destino:
    """Um ecrã, os seus parâmetros e quem o pode ver."""

    rota: str
    parametros: Mapping[str, str] = field(default_factory=dict)
    rotulo_id: str
    #: Vazio significa "herda do `menu.py`" — é o caso das sete do menu.
    papeis: frozenset[str] = frozenset()

    def papeis_efectivos(self) -> frozenset[str]:
        """Quem vê este botão: o conjunto declarado, ou o do registo do menu."""
        if self.papeis:
            return self.papeis
        return papeis_da_rota(self.rota)


@dataclass(frozen=True, kw_only=True, slots=True)
class Acao:
    """Uma acção de interface, já resolvida: é isto que o `MensagemOut` serve."""

    rota: str
    parametros: Mapping[str, str]
    rotulo_id: str


# ---------------------------------------------------------------------------
# A ajuda: os doze temas, a rota de cada um, e o texto
# ---------------------------------------------------------------------------
#: As duas línguas do manual (decisão do dono, 2026-10-16).
LINGUAS_DA_AJUDA: tuple[str, ...] = ("pt-pt", "en")

#: Os doze temas e o ecrã onde cada coisa se faz. `None` é "ainda não tem ecrã"
#: — hoje só as receitas, cuja produção não tem rota na árvore do cliente.
TEMAS: Mapping[str, Destino | None] = {
    "receber": Destino(rota="receber", rotulo_id="ver_rececoes"),
    "rever-linhas": Destino(
        rota="receber", parametros={"estado": "revisao"}, rotulo_id="rever_rececoes"
    ),
    "perdas-ajustes-transferencias": Destino(rota="stock", rotulo_id="ver_stock"),
    "contar": Destino(rota="contar", rotulo_id="ver_contagens"),
    "alertas-e-minimos": Destino(rota="alertas", rotulo_id="ver_alertas"),
    "painel": Destino(rota="painel", rotulo_id="ver_painel"),
    "artigos-sku-embalagens": Destino(rota="stock", rotulo_id="ver_stock"),
    "fornecedores": Destino(rota="receber", rotulo_id="ver_rececoes"),
    "receitas-e-producao": None,
    "equipa-e-convites": Destino(
        rota="definicoes",
        parametros={"secao": "equipa"},
        rotulo_id="ver_equipa",
        papeis=SO_O_DONO,
    ),
    "definicoes": Destino(
        rota="definicoes",
        parametros={"secao": "estabelecimento"},
        rotulo_id="ver_estabelecimento",
        papeis=SO_O_DONO,
    ),
    "assistente": Destino(rota="assistente", rotulo_id="ver_inicio"),
}

_RAIZ_DA_AJUDA = Path(__file__).resolve().parent / "ajuda"


def indice_de_temas() -> tuple[str, ...]:
    """Os temas pela ordem de declaração. Vai no prompt, para o modelo escolher."""
    return tuple(TEMAS)


@lru_cache(maxsize=64)
def texto_de_ajuda(*, tema: str, lingua: str) -> str | None:
    """O texto de um tema numa língua, ou `None` se o tema não existir.

    Lê de `ajuda/<lingua>/<tema>.md`, e o `tema` **nunca** chega aqui como
    caminho: o schema da tool é um `Literal` dos doze, e esta função volta a
    confirmar contra o `TEMAS` antes de tocar no disco. Uma língua fora das duas
    cai no português, que é a fonte.
    """
    if tema not in TEMAS:
        return None
    if lingua not in LINGUAS_DA_AJUDA:
        lingua = LINGUAS_DA_AJUDA[0]
    caminho = _RAIZ_DA_AJUDA / lingua / f"{tema}.md"
    if not caminho.is_file():
        return None
    return caminho.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# O mapa: tool + argumentos → destino
# ---------------------------------------------------------------------------
def _destino_de_artigo(args: Mapping[str, Any]) -> Destino | None:
    """O detalhe de um artigo, se os argumentos trouxerem um id que seja um UUID."""
    bruto = args.get("product_id") or args.get("id")
    if not isinstance(bruto, str):
        return None
    try:
        artigo = UUID(bruto)
    except ValueError:
        return None
    return Destino(
        rota="artigo",
        parametros={"artigo": str(artigo)},
        rotulo_id="ver_artigo",
        papeis=papeis_da_rota("stock"),
    )


def _destino_de_rececao(args: Mapping[str, Any]) -> Destino | None:
    """O detalhe de uma receção, pelo `id` dos argumentos."""
    bruto = args.get("id")
    if not isinstance(bruto, str):
        return None
    try:
        rececao = UUID(bruto)
    except ValueError:
        return None
    return Destino(
        rota="rececao",
        parametros={"rececao": str(rececao)},
        rotulo_id="ver_rececao",
        papeis=papeis_da_rota("receber"),
    )


_VER_DO_TIPO_DE_ALERTA: Mapping[str, tuple[str, str]] = {
    "falta": ("falta", "ver_falta"),
    "validade": ("expira", "ver_validade"),
    "desperdicio": ("desperdicio", "ver_desperdicio"),
}


def _destino_de_alertas(args: Mapping[str, Any]) -> Destino | None:
    """A vista dos Alertas que corresponde ao tipo pedido; `todos` não filtra."""
    tipo = args.get("tipo", "todos")
    if tipo == "todos" or not isinstance(tipo, str):
        return Destino(rota="alertas", rotulo_id="ver_alertas")
    par = _VER_DO_TIPO_DE_ALERTA.get(tipo)
    if par is None:
        return None
    ver, rotulo = par
    return Destino(rota="alertas", parametros={"ver": ver}, rotulo_id=rotulo)


_ESTADO_DE_RECECOES: Mapping[str, tuple[Mapping[str, str], str]] = {
    "por_rever": ({"estado": "revisao"}, "rever_rececoes"),
    "hoje": ({"estado": "hoje"}, "ver_rececoes_de_hoje"),
    "confirmadas": ({}, "ver_rececoes"),
}


def _destino_de_rececoes(args: Mapping[str, Any]) -> Destino | None:
    """A lista de receções no filtro pedido."""
    estado = args.get("estado", "por_rever")
    par = _ESTADO_DE_RECECOES.get(estado if isinstance(estado, str) else "")
    if par is None:
        return None
    parametros, rotulo = par
    return Destino(rota="receber", parametros=parametros, rotulo_id=rotulo)


def _destino_de_ajuda(args: Mapping[str, Any]) -> Destino | None:
    """O ecrã do tema pedido, quando o tema tem ecrã."""
    tema = args.get("tema")
    if not isinstance(tema, str):
        return None
    return TEMAS.get(tema)


def _fixo(destino: Destino):
    """Um destino que não depende dos argumentos."""
    return lambda _args: destino


#: O mapa **fechado**. Uma tool que não esteja aqui não produz botão nenhum, e
#: isso é a resposta certa para as procuras (`procurar_artigos`) e para o que
#: ainda não tem ecrã (receitas, produções).
_MAPA = {
    "saldo_de_artigo": _destino_de_artigo,
    "movimentos_de_artigo": _destino_de_artigo,
    "artigo": _destino_de_artigo,
    "artigos_abaixo_do_minimo": _fixo(
        Destino(rota="alertas", parametros={"ver": "falta"}, rotulo_id="ver_falta")
    ),
    "lotes_a_vencer": _fixo(
        Destino(rota="alertas", parametros={"ver": "expira"}, rotulo_id="ver_validade")
    ),
    "alertas": _destino_de_alertas,
    "rececoes": _destino_de_rececoes,
    "rececao": _destino_de_rececao,
    "contagens": _fixo(Destino(rota="contar", rotulo_id="ver_contagens")),
    "contagem": _fixo(Destino(rota="contar", rotulo_id="ver_contagens")),
    "compras_por_periodo": _fixo(Destino(rota="receber", rotulo_id="ver_rececoes")),
    "historico_de_precos": _fixo(Destino(rota="receber", rotulo_id="ver_rececoes")),
    "equipa": _fixo(
        Destino(
            rota="definicoes",
            parametros={"secao": "equipa"},
            rotulo_id="ver_equipa",
            papeis=SO_O_DONO,
        )
    ),
    "estabelecimento": _fixo(
        Destino(
            rota="definicoes",
            parametros={"secao": "estabelecimento"},
            rotulo_id="ver_estabelecimento",
            papeis=SO_O_DONO,
        )
    ),
    "ajuda_sobre": _destino_de_ajuda,
}


def acoes_do_turno(
    *, chamadas: Sequence[Mapping[str, Any]], papel: str
) -> tuple[Acao, ...]:
    """As acções de um turno, do rasto revalidado e filtradas pelo papel.

    A ordem é a das chamadas, e repetições do mesmo destino contam uma vez: um
    turno que consultou o saldo de farinha três vezes dá **um** botão.

    Chamadas que falharam (`ok: false`) não dão botão: levar alguém a um ecrã a
    partir de uma consulta que não correu é prometer o que não se viu.
    """
    vistas: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    acoes: list[Acao] = []
    for chamada in chamadas:
        if not chamada.get("ok", False):
            continue
        resolver = _MAPA.get(chamada.get("name", ""))
        if resolver is None:
            continue
        destino = resolver(chamada.get("args") or {})
        if destino is None or papel not in destino.papeis_efectivos():
            continue
        chave = (destino.rota, tuple(sorted(destino.parametros.items())))
        if chave in vistas:
            continue
        vistas.add(chave)
        acoes.append(
            Acao(
                rota=destino.rota,
                parametros=dict(destino.parametros),
                rotulo_id=destino.rotulo_id,
            )
        )
    return tuple(acoes)
