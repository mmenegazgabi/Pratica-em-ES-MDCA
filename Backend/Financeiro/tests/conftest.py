"""Fixtures comuns dos testes do Financeiro.

Os testes de rotas usam o armazenamento em memória, mesmo que a máquina tenha uma
``DATABASE_URL`` configurada: nada deles chega a um banco real.

Os testes que pedem a fixture ``banco_financeiro`` rodam contra um PostgreSQL descartável
indicado por ``TEST_DATABASE_URL``, com o esquema das migrations do Alembic. Sem essa
variável eles são pulados localmente; no CI, a falta do banco é erro.
"""

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url

from Financeiro.comprovantes import ArmazenamentoEmMemoria
from Financeiro.main import app
from Financeiro.notificacoes import caixa_de_notificacoes
from Financeiro.persistencia import VARIAVEL_ARMAZENAMENTO
from Financeiro.projetos import _projetos
from Financeiro.rascunhos import caixa_de_rascunhos
from Financeiro.routers.comprovantes import obter_armazenamento
from Financeiro.routers.orcamentos import _orcamentos
from Shared.banco import url_sqlalchemy

SHARED_DIR = Path(__file__).resolve().parents[2] / "Shared"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TOKEN = "token-de-teste-banco"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64

FIXTURES_DE_BANCO = {"banco_financeiro", "motor_financeiro"}


@pytest.fixture(autouse=True)
def _financeiro_em_memoria(request, monkeypatch):
    if FIXTURES_DE_BANCO & set(request.fixturenames):
        return
    monkeypatch.setenv(VARIAVEL_ARMAZENAMENTO, "memoria")


def _garantir_banco_descartavel(url: str) -> None:
    # As fixtures apagam dados: recusam qualquer coisa que pareça um banco real.
    nome = make_url(url).database or ""
    if "test" not in nome:
        pytest.fail(f"TEST_DATABASE_URL deve apontar para um banco de teste, veio {nome!r}")
    if url == os.environ.get("DATABASE_URL"):
        pytest.fail("TEST_DATABASE_URL deve ser diferente de DATABASE_URL")


@pytest.fixture(scope="session")
def motor_financeiro():
    if not TEST_DATABASE_URL:
        if os.environ.get("CI"):
            pytest.fail("TEST_DATABASE_URL não definido: no CI os testes de banco do Financeiro precisam rodar")
        pytest.skip("TEST_DATABASE_URL não definido; os testes de banco precisam de um PostgreSQL descartável")
    # Importado aqui: só os testes de banco precisam do Alembic.
    from alembic import command
    from alembic.config import Config

    _garantir_banco_descartavel(TEST_DATABASE_URL)
    config = Config(str(SHARED_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SHARED_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "head")
    motor = sa.create_engine(url_sqlalchemy(TEST_DATABASE_URL))
    yield motor
    motor.dispose()


def limpar_banco(motor) -> None:
    # CASCADE leva orçamentos, categorias, lançamentos, notificações, papéis, vínculos e o
    # que a Gestão pendura nos programas (a mesma lista do conftest da Gestão). A lista de
    # papéis, preenchida pela migration, fica. TRUNCATE passa pelo trigger do log, que só
    # barra UPDATE e DELETE.
    with motor.begin() as conexao:
        conexao.execute(
            sa.text(
                "TRUNCATE projetos, usuarios, log_auditoria, nucleos_familiares, responsaveis, "
                "rascunhos_lancamento CASCADE"
            )
        )


def esvaziar_memoria() -> None:
    """O equivalente a reiniciar a API: some tudo o que estava só no processo."""
    _projetos.clear()
    _orcamentos.clear()
    caixa_de_notificacoes.limpar()
    caixa_de_rascunhos.limpar()


@pytest.fixture
def banco_financeiro(motor_financeiro, monkeypatch):
    """Banco vazio, apontado pela DATABASE_URL da API, com o programa p-1 da Gestão."""
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.delenv(VARIAVEL_ARMAZENAMENTO, raising=False)
    app.dependency_overrides[obter_armazenamento] = lambda: ArmazenamentoEmMemoria()
    limpar_banco(motor_financeiro)
    esvaziar_memoria()
    with motor_financeiro.begin() as conexao:
        conexao.execute(
            sa.text("INSERT INTO projetos (id, nome, identificador) VALUES ('p-1', 'Semear', 'SEMEAR')")
        )
    yield motor_financeiro
    app.dependency_overrides.clear()
    limpar_banco(motor_financeiro)
    esvaziar_memoria()
