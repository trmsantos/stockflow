"""`manage.py criar_estabelecimento` — o tenant e o seu primeiro `owner`.

Sem este comando não há como entrar na aplicação, e isso é por desenho: a ADR
0010 decide que **o tenant nasce por operador e não por registo self-service no
v1**, por três razões que nenhuma é de conveniência — o que fazer com um NIF que
já existe está em aberto (e recusar diz ao candidato que aquele NIF é cliente),
o NIF do tenant é PII de pessoa singular numas vezes e exige encriptação de
campo com pepper (`SECURITY.md` §3), e o `billing` é fase 3, pelo que um
formulário aberto cria tenants sem limite.

## A password

É pedida ao terminal e **nunca** vem num argumento: um `--password` fica no
histórico da shell e aparece no `ps` de qualquer utilizador da máquina. Os dois
caminhos são os do `createsuperuser`, de propósito — é o comando que a pessoa
que corre este já conhece:

    uv run manage.py criar_estabelecimento --nome "Pastelaria Aurora" \
        --email ana@aurora.pt --responsavel "Ana Silva"

    STOCKFLOW_PASSWORD=... uv run manage.py criar_estabelecimento --noinput \
        --nome "Pastelaria Aurora" --email ana@aurora.pt --responsavel "Ana Silva"

A password passa pelos `AUTH_PASSWORD_VALIDATORS` (mínimo 12 caracteres, não
comum, não numérica) dentro do service: a primeira conta do sistema é a que abre
tudo, e um comando que saltasse as regras seria a porta mais fraca da casa.

**Se o email já existir, a password não é tocada.** É a mesma regra que a ADR
0010 dá à aceitação de convites, e a razão é a mesma: a password é global e a
pertença é por tenant, pelo que "criar um estabelecimento e definir a password do
dono" dava a quem corre o comando a tomada de uma conta existente, com os outros
estabelecimentos dela lá dentro. O comando diz que não a tocou.

## O que este comando não faz

**Não** verifica se já existe um estabelecimento com o mesmo nome: o nome não é
único e o que identifica um cliente é o NIF, que ainda não existe no modelo
(sessão própria, `SECURITY.md` §3). Correr isto duas vezes cria dois
estabelecimentos, e o uuid de cada um sai impresso — é a forma de os distinguir.

**Não** imprime um link de activação. Isso é o convite da ADR 0010, que é a
tarefa seguinte: enquanto não existir, a única forma de entrar é com uma password
definida aqui.
"""

from __future__ import annotations

import os
from getpass import getpass
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.services import criar_tenant_com_dono

#: Nome da variável de ambiente onde o `--noinput` vai buscar a password. Segue
#: o `DJANGO_SUPERUSER_PASSWORD` do `createsuperuser` na forma e na intenção: é
#: o caminho para um script de provisionamento, não para o uso interactivo.
#:
#: A constante chama-se pelo que **é** — um nome de variável de ambiente — e não
#: `..._PASSWORD`: o `S105` do ruff trata um literal atribuído a um nome com
#: "password" dentro como credencial em código, e aqui o literal é o nome da
#: variável e não o seu valor. Nomear com precisão vale mais do que uma supressão
#: de lint, que nesta casa não existe em ficheiro nenhum (CLAUDE.md).
VARIAVEL_DE_AMBIENTE = "STOCKFLOW_PASSWORD"


class Command(BaseCommand):
    help = "Cria um estabelecimento e o seu primeiro utilizador com papel owner."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--nome",
            required=True,
            help="Nome do estabelecimento, como aparece no seletor.",
        )
        parser.add_argument(
            "--email",
            required=True,
            help="Email do dono. É o campo de entrada (USERNAME_FIELD).",
        )
        parser.add_argument(
            "--responsavel",
            required=True,
            help=(
                "Nome do dono **neste** estabelecimento (display_name do "
                "Membership). A mesma pessoa pode ter outro noutro."
            ),
        )
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_true",
            dest="noinput",
            help=f"Lê a password de {VARIAVEL_DE_AMBIENTE} em vez de a pedir.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        password = self._password(noinput=options["noinput"])
        try:
            resultado = criar_tenant_com_dono(
                nome=options["nome"],
                email=options["email"],
                display_name=options["responsavel"],
                password=password,
            )
        except ValidationError as erro:
            # As regras de password do `AUTH_PASSWORD_VALIDATORS`, vindas do
            # service. `CommandError` e não traceback: isto é entrada do
            # operador a ser recusada, não um defeito.
            raise CommandError("; ".join(erro.messages)) from erro

        self.stdout.write(
            self.style.SUCCESS(f"Estabelecimento criado: {resultado.tenant.name}")
        )
        self.stdout.write(f"  tenant_id: {resultado.tenant.id}")
        self.stdout.write(f"  owner:     {resultado.user.email}")
        if resultado.utilizador_criado:
            self.stdout.write("  conta:     criada, com a password que indicou")
            return
        self.stdout.write(
            self.style.WARNING(
                "  conta:     já existia — a password NÃO foi alterada. "
                "A pertença a este estabelecimento foi concedida."
            )
        )

    def _password(self, *, noinput: bool) -> str:
        """A password, do ambiente ou do terminal. Nunca de um argumento.

        No caminho interactivo é pedida **duas** vezes e o `getpass` não a
        mostra. A confirmação não é cerimónia: a password que sai daqui é a única
        forma de entrar na aplicação, e um erro de dactilografia sem confirmação
        só se descobre no ecrã de login, sem forma de a corrigir — não há
        reposição de password ainda (ADR 0010, tarefa seguinte).
        """
        if noinput:
            password = os.environ.get(VARIAVEL_DE_AMBIENTE, "")
            if not password:
                raise CommandError(
                    f"--noinput exige a password em {VARIAVEL_DE_AMBIENTE}. "
                    "Nunca a passes num argumento: fica no histórico da shell e "
                    "no ps de qualquer utilizador da máquina."
                )
            return password

        password = getpass("Password do dono: ")
        if password != getpass("Confirme a password: "):
            raise CommandError("As duas passwords não coincidem.")
        if not password:
            raise CommandError("A password não pode ser vazia.")
        return password
