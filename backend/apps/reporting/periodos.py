"""A janela do painel, num sítio só (ADR 0013, decisão 8; ADR 0029, decisão 4).

Uma função resolve o `period`, outra o `month`, e as três respostas ecoam o par
`[desde, ate)` que elas devolvem. Está num módulo próprio e não dentro do
`selectors.py` por uma razão que é um invariante e não arrumação: **Σ(dias de
negócio) == mês por construção**. Com a fronteira do dia às 04:00 e a do mês à
meia-noite, o dia de negócio de 30 de abril parte-se em dois meses e as barras
diárias deixam de somar o total mensal — e um gráfico cujas barras não somam o
número ao lado perde credibilidade mais depressa do que um sinal trocado.

Três regras que vivem aqui e em mais lado nenhum:

* **o dia de negócio começa à hora do estabelecimento** (o
  `business_day_starts_at` do `accounts`, 04:00 por omissão), logo um
  movimento das 02:00 do dia 1 é do mês anterior;
* **`ate = min(fim da janela, agora)`.** Um período a correr não promete o
  futuro: o `7d` inclui o dia a correr como último balde **parcial**, e quem o
  lê sabe-o pelo `until` que viaja na resposta. O `/month` diz a mesma coisa
  por outras palavras, com `closed` e `days_elapsed`;
* **a aritmética é de calendário local e não de horas.** "Menos seis dias" é
  seis voltas ao calendário, não 144 horas: no domingo em que o relógio muda,
  as duas respostas diferem em uma hora e uma delas põe um dia inteiro no balde
  errado.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.utils import timezone
from rest_framework.exceptions import ValidationError

__all__ = [
    "Balde",
    "Janela",
    "JanelaDoMes",
    "PERIODOS",
    "baldes",
    "dia_de_negocio",
    "granularidade_de",
    "inicio_do_dia_de_negocio",
    "janela_do_mes",
    "janela_do_periodo",
    "mes_de_negocio",
]

#: Os cinco períodos do contrato (ADR 0013, decisão 5). União fechada: o
#: serializer recusa o resto com 400 antes de isto ser chamado.
PERIODOS: tuple[str, ...] = ("today", "7d", "30d", "month", "prev_month")

#: Quantos dias de calendário cada janela móvel cobre, **incluindo** o dia a
#: correr: `7d` é hoje e os seis anteriores, e não "há 168 horas".
DIAS_DA_JANELA: dict[str, int] = {"today": 1, "7d": 7, "30d": 30}

#: `YYYY-MM`, a mesma forma que o `mesSchema` do cliente valida.
FORMA_DO_MES = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


@dataclass(frozen=True, kw_only=True, slots=True)
class Janela:
    """O período resolvido: o que o `PeriodOut` ecoa, mais a hora do negócio."""

    key: str
    desde: datetime
    ate: datetime
    inicio_do_dia: time


@dataclass(frozen=True, kw_only=True, slots=True)
class JanelaDoMes:
    """O mês de negócio resolvido, com o que distingue um mês a correr de um fechado."""

    month: str
    desde: datetime
    ate: datetime
    inicio_do_dia: time
    closed: bool
    days_elapsed: int
    days_in_month: int

    @property
    def janela(self) -> Janela:
        """A mesma janela na forma do período, para o agregado ser o mesmo código."""
        return Janela(
            key="month",
            desde=self.desde,
            ate=self.ate,
            inicio_do_dia=self.inicio_do_dia,
        )


@dataclass(frozen=True, kw_only=True, slots=True)
class Balde:
    """Um intervalo do gráfico e os dias de negócio que caem dentro dele."""

    dias: tuple[date, ...]
    desde: datetime
    ate: datetime


def inicio_do_dia_de_negocio(*, dia: date, inicio_do_dia: time) -> datetime:
    """O instante em que o dia de negócio `dia` começa, no fuso do servidor."""
    return timezone.make_aware(datetime.combine(dia, inicio_do_dia))


def dia_de_negocio(*, instante: datetime, inicio_do_dia: time) -> date:
    """A que dia de negócio pertence um instante. Às 02:00 ainda é ontem."""
    local = timezone.localtime(instante)
    if local.time() >= inicio_do_dia:
        return local.date()
    return local.date() - timedelta(days=1)


def mes_de_negocio(*, instante: datetime, inicio_do_dia: time) -> str:
    """O mês `YYYY-MM` a que um instante pertence, pela fronteira do dia de negócio."""
    dia = dia_de_negocio(instante=instante, inicio_do_dia=inicio_do_dia)
    return f"{dia.year:04d}-{dia.month:02d}"


def _mes_anterior(*, ano: int, mes: int) -> tuple[int, int]:
    """O par (ano, mês) do mês anterior."""
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


def janela_do_periodo(*, key: str, inicio_do_dia: time, agora: datetime) -> Janela:
    """Resolve `today|7d|30d|month|prev_month` em `[desde, ate)`.

    `ate` nunca passa de `agora`: o último balde de um período a correr é
    parcial e é o `until` da resposta que o diz. Um `key` fora da união é um
    erro de programação — quem valida a entrada é o serializer, com 400.
    """
    hoje = dia_de_negocio(instante=agora, inicio_do_dia=inicio_do_dia)
    if key in DIAS_DA_JANELA:
        primeiro = hoje - timedelta(days=DIAS_DA_JANELA[key] - 1)
        desde = inicio_do_dia_de_negocio(dia=primeiro, inicio_do_dia=inicio_do_dia)
        return Janela(key=key, desde=desde, ate=agora, inicio_do_dia=inicio_do_dia)

    if key == "month":
        ano, mes = hoje.year, hoje.month
    elif key == "prev_month":
        ano, mes = _mes_anterior(ano=hoje.year, mes=hoje.month)
    else:
        raise ValueError(f"período desconhecido: {key!r}")

    janela = janela_do_mes(mes=f"{ano:04d}-{mes:02d}", inicio_do_dia=inicio_do_dia, agora=agora)
    return Janela(
        key=key,
        desde=janela.desde,
        ate=janela.ate,
        inicio_do_dia=inicio_do_dia,
    )


def janela_do_mes(*, mes: str, inicio_do_dia: time, agora: datetime) -> JanelaDoMes:
    """O mês de negócio `YYYY-MM`: `[dia 1 às <hora>, dia 1 do mês seguinte às <hora>)`.

    `days_elapsed` conta o dia a correr **como um dia inteiro**: ao dia 9 às
    06:00 vão nove dias decorridos e não 8,08. A fração seria precisão
    inventada, e o passo seguinte — extrapolar o mês a partir dela — é o que
    transforma um painel numa previsão que ninguém pediu (ADR 0029, fora de
    âmbito).
    """
    encontrado = FORMA_DO_MES.match(mes)
    if encontrado is None:
        raise ValueError(f"mês desconhecido: {mes!r}")
    ano, numero = int(encontrado.group(1)), int(encontrado.group(2))

    desde = inicio_do_dia_de_negocio(dia=date(ano, numero, 1), inicio_do_dia=inicio_do_dia)
    seguinte = (ano + 1, 1) if numero == 12 else (ano, numero + 1)
    fim = inicio_do_dia_de_negocio(
        dia=date(seguinte[0], seguinte[1], 1), inicio_do_dia=inicio_do_dia
    )
    # `max(desde, …)` e não só `min(…)`: num mês futuro o `agora` fica *antes*
    # do início e a janela invertia-se, o que no SQL é zero linhas por acidente
    # em vez de uma janela vazia por desenho.
    ate = max(desde, min(fim, agora))

    dias_do_mes = calendar.monthrange(ano, numero)[1]
    if fim <= agora:
        decorridos = dias_do_mes
    elif agora < desde:
        decorridos = 0
    else:
        hoje = dia_de_negocio(instante=agora, inicio_do_dia=inicio_do_dia)
        decorridos = min(hoje.day, dias_do_mes)

    return JanelaDoMes(
        month=f"{ano:04d}-{numero:02d}",
        desde=desde,
        ate=ate,
        inicio_do_dia=inicio_do_dia,
        closed=fim <= agora,
        days_elapsed=decorridos,
        days_in_month=dias_do_mes,
    )


def granularidade_de(key: str) -> str:
    """`day` para janelas curtas, `week` para as longas. **Derivada pelo servidor.**

    O cliente não a escolhe (ADR 0013, decisão 5): trinta barras num cartão de
    telemóvel não são legíveis, e quem sabe quantas cabem é quem conhece o
    contrato, não quem desenha. A fronteira está onde o ecrã já a desenhou
    sobre as fixtures: `today` e `7d` ao dia, o resto à semana.
    """
    return "day" if key in ("today", "7d") else "week"


def baldes(*, janela: Janela, granularidade: str) -> tuple[Balde, ...]:
    """Os intervalos do gráfico, do `desde` ao `ate`, sem buracos nem sobreposição.

    Os baldes **particionam** a janela: o primeiro começa no `desde` e o último
    acaba no `ate`, pelo que a soma dos pontos é o total da janela e não uma
    aproximação dele. Um balde de semana são sete dias de negócio, e o último
    pode ser mais curto — é o que acontece a um mês que não tem 28 dias.
    """
    if janela.ate <= janela.desde:
        return ()

    primeiro = dia_de_negocio(instante=janela.desde, inicio_do_dia=janela.inicio_do_dia)
    dias: list[date] = []
    dia = primeiro
    while inicio_do_dia_de_negocio(dia=dia, inicio_do_dia=janela.inicio_do_dia) < janela.ate:
        dias.append(dia)
        dia += timedelta(days=1)

    passo = 7 if granularidade == "week" else 1
    grupos = [dias[indice : indice + passo] for indice in range(0, len(dias), passo)]
    return tuple(
        Balde(
            dias=tuple(grupo),
            desde=inicio_do_dia_de_negocio(dia=grupo[0], inicio_do_dia=janela.inicio_do_dia),
            ate=min(
                inicio_do_dia_de_negocio(
                    dia=grupo[-1] + timedelta(days=1), inicio_do_dia=janela.inicio_do_dia
                ),
                janela.ate,
            ),
        )
        for grupo in grupos
    )


def exigir_forma_do_mes(mes: str) -> None:
    """Recusa um `month` mal formado **antes** de qualquer ida à base de dados.

    A mensagem nomeia a forma esperada e não ecoa o que veio: devolver ao
    pedinte a string que ele escreveu não acrescenta nada a quem lê.
    """
    if not FORMA_DO_MES.match(mes):
        raise ValidationError({"detail": "Mês inválido. Esperado o formato AAAA-MM."})
