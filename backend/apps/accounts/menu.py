"""O registo de rotas: a lista fechada do que o menu pode nomear (ADR 0009).

Este ficheiro é **código e não configuração**, e a distinção é a decisão central
da ADR 0011: a projecção por tenant (`accounts_tenantmenuitem`) só consegue
mexer em `grupo`, `ordem`, `visivel` e `rotulo` **de uma rota que esteja aqui**.
Três colunas mutáveis sobre uma lista fechada não são um armazém chave/valor —
é essa a fronteira que impede o motor genérico de nascer.

## Porque é que o `route_id` é um enum fechado do backend

Porque é o backend que valida o que a projecção guarda (ADR 0011), e porque é
isso que fecha o caminho completo que a ADR 0009 descreve:

    RotaDeMenu (Django)  →  RotaIdEnum (OpenAPI)  →  união no `types.ts`
                         →  Record<RotaId, EntradaDoRegisto> no shell

O `Record` sobre uma união **gerada** é exaustivo nos dois sentidos sob
`pnpm typecheck`: uma rota no registo do frontend que este enum não tem não
compila, e uma rota deste enum que o registo do frontend não tem também não. É
o que substitui a garantia dos "4 itens" que morreu com a tab bar — integridade
referencial, não cardinalidade. O número de itens de um menu que chega por HTTP
**fica sem mecanismo**, e está escrito assim na ADR em vez de disfarçado com um
teste que mede outra coisa.

Os seis ids são exactamente os do `frontend/src/shell/registo-de-rotas.ts`, que
os escreveu primeiro (a projecção em código que esta feature substitui). Não há
um sétimo: um id que o backend conhecesse e o registo do frontend não tivesse
fazia o `pnpm typecheck` do outro agente falhar — e a rota de configuração do
menu, que é a candidata óbvia, ainda não existe na árvore de rotas da SPA.

## `papeis_permitidos` e não `papel_minimo`, e a razão não é de gosto

A ADR 0011 pede que a resposta seja filtrada pelo papel de quem a pede, "contra
o papel mínimo que o registo declara". **Um mínimo exige uma ordem entre papéis,
e essa ordem não existe neste projeto**: o conjunto de papéis é a Q7 do
`SESSION-CONTEXT.md`, está marcada como "não inventes default sem falar com um
utilizador real", e o v1 resolve-a com "só o `owner` convida e só o `owner`
configura". A ADR 0010 já nomeou a mesma dívida pelo outro lado — "nenhum
convite concede papel acima do de quem convida" é verdadeiro hoje por
construção e não tem código a impô-lo, porque escrever a ordem na implementação
dos convites era responder à Q7 sem ninguém ter perguntado.

Logo o registo declara um **conjunto de papéis permitidos** por rota. Dá
exactamente o mesmo poder de filtragem sem afirmar que `manager` > `staff`, e no
dia em que a Q7 for respondida um conjunto derivado de uma ordem continua a ser
um conjunto. O caminho contrário — escrever a ordem agora e derivar o conjunto
dela — não se desfaz sem mudar o contrato.

**Hoje há três rotas restritas, e nenhuma foi restringida por esta ADR:**
`convites` é do `owner` porque a ADR 0010 o decidiu e porque é o que o
`ConviteViewSet` impõe (`TemPapel.exige(Papel.OWNER)`); `painel` porque a ADR
0013 o decidiu e porque é o que as permissões dos três endpoints do `reporting`
impõem; `configuracao` porque a ADR 0017 o decidiu e porque é o que o
`EstabelecimentoView` impõe. Esconder do `staff` um item que o leva a um 403 é o
caso literal da frase da ADR 0011 — autorização e não preferência — e é a razão
de o filtro não ser teórico.

As outras cinco estão abertas aos três papéis, e isso é uma afirmação e não um
descuido: dizer que um `staff` não pode ver o Stock ou os Alertas é uma decisão
de produto que ninguém tomou.

**O conjunto de papéis de cada rota segue a permissão real do endpoint que ela
serve, e nada mais.** É isso que mantém esta coluna fora da Q7: `convites` tem
um `permission_classes` a dizê-lo, e uma rota cujo ecrã não recuse ninguém não
tem razão para restringir o item de menu. O que **não** tem mecanismo é o
casamento entre as duas coisas — nada falha se amanhã o `ConviteViewSet` passar
a aceitar um `manager` e este registo não mudar. Está no relatório.

## `campo` está aqui e **também** no frontend, e isso é dívida nomeada

`campo` marca as rotas desenhadas para 360px (ADR 0009: Contar e Receber). A
cópia que a UI usa é a do `frontend/src/shell/registo-de-rotas.ts`, porque é ela
que gera a frase da gaveta de mobile, e a projecção que alimenta a sidebar
**não** transporta este campo — é isso que torna estruturalmente impossível a uma
configuração de tenant promover uma rota de escritório para o telemóvel
(ADR 0009, adenda 2). A cópia daqui serve o painel de configuração, que tem de
poder dizer "esta rota foi desenhada para telemóvel" ao lado do item.

São duas fontes para o mesmo facto de desenho e **não há mecanismo que as case**:
nada falha se divergirem. Está no relatório.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from apps.accounts.models import Papel, RotaDeMenu

__all__ = [
    "ItemDeMenu",
    "REGISTO_DE_ROTAS",
    "RotaDoRegisto",
    "TODOS_OS_PAPEIS",
    "papeis_ordenados",
    "rota_do_registo",
    "rotas_do_registo",
]

#: Os três papéis, como conjunto. É o valor de `papeis` de todas as rotas de
#: hoje — ver o docstring do módulo.
TODOS_OS_PAPEIS: Final[frozenset[str]] = frozenset(Papel.values)


@dataclass(frozen=True, kw_only=True, slots=True)
class RotaDoRegisto:
    """Uma rota que existe, com os seus defaults e com quem a pode ver.

    Congelado como os outros DTOs do módulo: isto é uma declaração de código, e
    um registo que se pudesse mutar a meio de um pedido era uma decisão de
    autorização a mudar debaixo dos pés de quem já a tomou.

    É **isto** que o `RotaDeMenuOutSerializer` serializa, sem camada de mapeamento
    pelo meio: por isso o `route_id` é um campo da entrada (e não só a chave do
    dicionário) e por isso existe a propriedade `papeis_permitidos`. O `__all__`
    não expõe uma função de conversão porque não há nenhuma para expor.

    `ordem_default` não sai no contrato de `GET /menu/rotas` e sai na projecção,
    que é onde serve: quem precisa da ordem por omissão recebe-a já aplicada no
    `menu` da sessão.

    ## E **não há** `rotulo_default` nem `grupo_default`, desde 2026-10-07

    Tinha os dois, e saíam no contrato "porque o painel precisa deles para
    mostrar o default ao lado de um valor que o tenant sobrepôs". Saíram, e a
    razão é a regra que a ADR 0019 fixou: **nenhum rótulo nosso viaja no arame.**
    O que atravessa a API é um id de união fechada ou texto que o **tenant**
    escreveu; o nome por omissão de uma rota é copy do produto, e copy traduz-se
    no catálogo do cliente — um rótulo servido pelo servidor seria uma segunda
    fonte para a mesma palavra, numa língua só.

    O `rotulo` já era assim (o contrato manda `null` e o cliente resolve contra o
    seu registo); o `grupo` **não era**, e o preço estava medido: o `grupo`
    viajava resolvido e obrigatório, e como o `PUT /menu` é substituição total, a
    primeira gravação congelava "Inventário" na linha do tenant e nenhuma
    tradução a voltava a alcançar. Agora os dois são `null` no contrato e os dois
    caem no registo do cliente.
    """

    route_id: str
    ordem_default: int
    #: Os papéis que podem ver este item. Conjunto e não mínimo — ver o módulo.
    papeis: frozenset[str]
    #: Desenhada para 360px (ADR 0009). Duplicado no frontend — ver o módulo.
    campo: bool

    @property
    def papeis_permitidos(self) -> list[str]:
        """Os `papeis` pela ordem de declaração do `Papel`, para o contrato.

        O conjunto é a forma certa para decidir ("o papel está lá dentro?") e a
        errada para responder: a iteração de um `frozenset` de strings depende do
        hash e varia entre processos, logo a mesma resposta sairia com os papéis
        em ordens diferentes em dois workers. Ordem de declaração e **não** de
        precedência — não existe nenhuma (ver o módulo).
        """
        return papeis_ordenados(self.papeis)


@dataclass(frozen=True, kw_only=True, slots=True)
class ItemDeMenu:
    """Uma linha da projecção **já resolvida**: defaults, configuração e filtro.

    É a forma que viaja no `menu` do `SessaoOut` e na resposta do `PUT /menu`, e
    é exactamente a tupla que a ADR 0009 fixa: uma lista com um nível de
    agrupamento, nunca uma árvore.

    **`rotulo` e `grupo` são `None` quando o tenant não sobrepôs nada**, e não o
    valor do registo já resolvido. Resolvê-los aqui fazia-os voltar no próximo
    `PUT` como sobreposição explícita, e um dia em que o default mudasse o tenant
    ficava preso ao antigo sem nunca ter escolhido nada — e, pior, nenhuma
    tradução alcançava o que estava congelado na linha.

    A assimetria fica com o `ordem`, que viaja **resolvido**, e a razão é a que
    separa as duas coisas: `ordem` é um número e não é copy. O registo do cliente
    tem um rótulo e um grupo por rota (foi o que a ADR 0019 lá pôs, decisão 5) e
    não tem ordem nenhuma, logo é o único dos três que não tem para onde cair do
    lado de lá.
    """

    route_id: str
    grupo: str | None
    ordem: int
    visivel: bool
    rotulo: str | None


#: As rotas, pela ordem em que o menu por omissão as mostra. A `ordem_default`
#: vai de dez em dez pela razão de sempre: inserir um item entre dois não obriga
#: a renumerar os outros, nem aqui nem na tabela.
#:
#: Os rótulos e os grupos são os que o `PROJECCAO_EM_CODIGO` do shell já usava —
#: esta feature substitui essa projecção pela fonte real, e mudar os nomes no
#: caminho fazia a troca parecer um redesenho.
_ROTAS: Final[tuple[RotaDoRegisto, ...]] = (
    RotaDoRegisto(
        route_id=RotaDeMenu.INICIO,
        ordem_default=10,
        papeis=TODOS_OS_PAPEIS,
        campo=False,
    ),
    RotaDoRegisto(
        route_id=RotaDeMenu.PAINEL,
        ordem_default=15,
        # **A segunda rota restrita, e pela mesma mecânica do `convites`.** O
        # painel de gestão mostra o resultado do mês, a folha salarial e o custo
        # por cargo; é do dono e de mais ninguém (decisão do dono do produto, e o
        # `reporting` impõe-no nas permissões dos três endpoints). Mostrar o item
        # a um encarregado era pôr no menu um caminho que acaba em 403 — o caso
        # literal do "esconder um item que um papel não pode usar é autorização e
        # não preferência" (ADR 0011).
        #
        # Não é uma ordem entre papéis: é o conjunto `{owner}`, que se alarga sem
        # se desfazer. A Q7 continua sem resposta e esta entrada não a inventa.
        papeis=frozenset({Papel.OWNER}),
        # Escritório. Um painel de gestão lê-se sentado, com o mês ao lado do
        # período; a 360px as tabelas deslizam e isso é declarado (DESIGN.md §4).
        campo=False,
    ),
    RotaDoRegisto(
        route_id=RotaDeMenu.ALERTAS,
        ordem_default=20,
        papeis=TODOS_OS_PAPEIS,
        campo=False,
    ),
    RotaDoRegisto(
        route_id=RotaDeMenu.ASSISTENTE,
        ordem_default=25,
        # **Nenhum papel**, de propósito: o dono decidiu (2026-10-15, segunda
        # adenda à ADR 0027 d10) que o assistente não tem entrada no menu — a
        # entrada é o lançador global (botão fixo em todos os ecrãs, painel
        # lateral), e a página `/assistente` abre-se de lá ou por URL. A rota
        # fica no registo porque ele cobre a união `RotaDeMenu` nos dois
        # sentidos e o registo do cliente exige uma rota por id; o conjunto
        # vazio é o que diz "existe, mas o menu não a mostra a ninguém".
        papeis=frozenset(),
        campo=False,
    ),
    RotaDoRegisto(
        route_id=RotaDeMenu.STOCK,
        ordem_default=30,
        papeis=TODOS_OS_PAPEIS,
        campo=False,
    ),
    RotaDoRegisto(
        route_id=RotaDeMenu.CONTAR,
        ordem_default=40,
        papeis=TODOS_OS_PAPEIS,
        campo=True,
    ),
    RotaDoRegisto(
        route_id=RotaDeMenu.RECEBER,
        ordem_default=50,
        papeis=TODOS_OS_PAPEIS,
        campo=True,
    ),
)

#: O registo, indexado pelo id. Construído a partir do `_ROTAS` acima e não
#: escrito à mão com a chave repetida dentro do valor: assim a chave e o
#: `route_id` da entrada não podem divergir.
#:
#: Um `dict` e não um `MappingProxyType`: o `tests/test_menu.py` substitui
#: **uma** entrada por `monkeypatch.setitem` para medir o filtro por papel antes
#: de existir a primeira rota restrita (ver o docstring do módulo), e o
#: `monkeypatch` repõe-a. Os valores são congelados, pelo que uma entrada não se
#: consegue alterar; quem lê usa o `rota_do_registo` abaixo, que devolve por uma
#: vista imutável.
REGISTO_DE_ROTAS: Final[dict[str, RotaDoRegisto]] = {rota.route_id: rota for rota in _ROTAS}


def rotas_do_registo() -> tuple[RotaDoRegisto, ...]:
    """O registo inteiro, pela ordem em que o menu por omissão o mostra.

    É o que o `GET /menu/rotas` serializa. Devolve uma tupla e lê do
    `REGISTO_DE_ROTAS` — e não do `_ROTAS` — para que o registo adulterado de um
    teste seja visto também por aqui: um filtro por papel medido na sessão e
    invisível no registo seria metade da prova.
    """
    return tuple(REGISTO_DE_ROTAS.values())


def rota_do_registo(route_id: str) -> RotaDoRegisto | None:
    """A entrada do registo deste id, ou `None` se o id não existir.

    `None` em vez de `KeyError` porque há um caminho onde o id pode não existir
    e não é um bug: uma linha de `accounts_tenantmenuitem` escrita por uma versão
    mais nova do backend e lida por uma mais velha, no intervalo de um rolling
    deploy. Ignorar a linha é o comportamento certo aí — é o mesmo que o
    `montarMenu` do shell faz, e pela mesma razão.

    O que devolve é congelado (`RotaDoRegisto`), logo quem lê não consegue
    alterar o registo a partir de uma leitura.
    """
    return REGISTO_DE_ROTAS.get(route_id)


def papeis_ordenados(papeis: frozenset[str]) -> list[str]:
    """Os papéis de um conjunto pela ordem em que o `Papel` os declara.

    Ordem de declaração e **não** alfabética: a lista sai no contrato e uma
    ordem estável é o que faz o diff do `schema.yml` e do `types.ts` ser sobre a
    API e não sobre a iteração de um `frozenset`, que é arbitrária por hash. Não
    é uma ordem de precedência — não existe nenhuma (ver o módulo); é a ordem em
    que se lê uma lista, do dono ao colaborador.
    """
    return [papel for papel in Papel.values if papel in papeis]
