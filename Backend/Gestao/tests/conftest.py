"""Fixtures dos testes do Módulo de Gestão.

Os testes rodam contra a API integrada (``Backend/main.py``), a mesma publicada no
Cloud Run. Os que leem do banco usam um PostgreSQL descartável indicado por
``TEST_DATABASE_URL``, com o esquema das migrations do Alembic. Sem essa variável
eles são pulados localmente; no CI, a falta do banco é erro.
"""

import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from Gestao.banco import url_sqlalchemy

BACKEND_DIR = Path(__file__).resolve().parents[2]
SHARED_DIR = BACKEND_DIR / "Shared"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TOKEN = "token-de-teste-gestao"


def carregar_app():
    # Carrega pelo caminho: "main" sozinho poderia ser o Financeiro/main.py.
    spec = importlib.util.spec_from_file_location("mdca_api_gestao", BACKEND_DIR / "main.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.app


@pytest.fixture(scope="session")
def app():
    return carregar_app()


@pytest.fixture
def cliente(app, monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    return TestClient(app)


@pytest.fixture
def cabecalhos():
    return {"Authorization": f"Bearer {TOKEN}"}


def _garantir_banco_descartavel(url: str) -> None:
    # As fixtures apagam dados, então recusam qualquer coisa que pareça um banco real.
    nome = make_url(url).database or ""
    if "test" not in nome:
        pytest.fail(f"TEST_DATABASE_URL deve apontar para um banco de teste, veio {nome!r}")
    if url == os.environ.get("DATABASE_URL"):
        pytest.fail("TEST_DATABASE_URL deve ser diferente de DATABASE_URL")


def _alembic_config() -> Config:
    config = Config(str(SHARED_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SHARED_DIR / "migrations"))
    # O ConfigParser interpola "%", então senhas com URL-encoding precisam de escape.
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def motor_de_teste():
    if not TEST_DATABASE_URL:
        if os.environ.get("CI"):
            pytest.fail("TEST_DATABASE_URL não definido: no CI os testes de banco da Gestão precisam rodar")
        pytest.skip("TEST_DATABASE_URL não definido; os testes de banco precisam de um PostgreSQL descartável")
    _garantir_banco_descartavel(TEST_DATABASE_URL)
    command.upgrade(_alembic_config(), "head")
    motor = sa.create_engine(url_sqlalchemy(TEST_DATABASE_URL))
    yield motor
    motor.dispose()


def _limpar(motor) -> None:
    # CASCADE leva junto vínculos, espaços e papéis de usuários; a lista de papéis
    # (preenchida pela migration) fica. TRUNCATE passa pelo trigger do log, que só
    # barra UPDATE e DELETE.
    with motor.begin() as conexao:
        conexao.execute(sa.text("TRUNCATE projetos, usuarios, log_auditoria CASCADE"))


@pytest.fixture
def banco(motor_de_teste, monkeypatch):
    """Banco de teste vazio, já apontado pela DATABASE_URL da API."""
    _garantir_banco_descartavel(TEST_DATABASE_URL)
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    _limpar(motor_de_teste)
    yield motor_de_teste
    _limpar(motor_de_teste)
