"""Vagas ofertadas e convênios saem dos programas (migration f2b4d6e8a1c3).

Como os outros testes de migration, desce o banco de teste até o esquema vazio; por isso
só roda com ``TEST_DATABASE_URL`` apontando para um banco descartável.
"""

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

SHARED_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

REV_ANTERIOR = "e4b8c1d7f2a9"
REV_REMOCAO = "f2b4d6e8a1c3"
TABELAS = {"vagas", "convenios"}

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL não definido; os testes de migration precisam de um PostgreSQL descartável",
)


def _sqlalchemy_url(url: str) -> str:
    parsed = make_url(url)
    if parsed.drivername in ("postgresql", "postgres"):
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed.render_as_string(hide_password=False)


def _alembic_config() -> Config:
    config = Config(str(SHARED_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SHARED_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    return config


def _garantir_banco_descartavel(url: str) -> None:
    nome = make_url(url).database or ""
    if "test" not in nome:
        pytest.fail(f"TEST_DATABASE_URL deve apontar para um banco de teste, veio {nome!r}")
    if url == os.environ.get("DATABASE_URL"):
        pytest.fail("TEST_DATABASE_URL deve ser diferente de DATABASE_URL")


@pytest.fixture
def banco_antes():
    """Banco na revisão anterior, com um programa que tem convênio e vagas."""
    _garantir_banco_descartavel(TEST_DATABASE_URL)
    config = _alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, REV_ANTERIOR)

    engine = sa.create_engine(_sqlalchemy_url(TEST_DATABASE_URL))
    with engine.begin() as c:
        c.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear')"))
        c.execute(sa.text("INSERT INTO convenios (id, programa_id, nome) VALUES ('c-1', 'p-1', 'teste')"))
        c.execute(sa.text(
            "INSERT INTO vagas (id, programa_id, descricao, quantidade) VALUES ('v-1', 'p-1', 'Manhã', 30)"
        ))
    try:
        yield engine, config
    finally:
        engine.dispose()
        command.downgrade(config, "base")


def test_as_duas_tabelas_saem_e_o_programa_fica(banco_antes):
    engine, config = banco_antes

    command.upgrade(config, REV_REMOCAO)

    tabelas = set(sa.inspect(engine).get_table_names())
    assert not TABELAS & tabelas
    with engine.connect() as c:
        assert c.execute(sa.text("SELECT nome FROM projetos WHERE id = 'p-1'")).scalar_one() == "Semear"


def test_downgrade_recria_as_tabelas_vazias_com_as_mesmas_regras(banco_antes):
    engine, config = banco_antes
    command.upgrade(config, REV_REMOCAO)

    command.downgrade(config, REV_ANTERIOR)

    assert TABELAS <= set(sa.inspect(engine).get_table_names())
    with engine.begin() as c:
        assert c.execute(sa.text("SELECT count(*) FROM vagas")).scalar_one() == 0
        c.execute(sa.text("INSERT INTO vagas (id, programa_id, descricao, quantidade) VALUES ('v-2', 'p-1', 'Tarde', 10)"))
        c.execute(sa.text("INSERT INTO convenios (id, programa_id, nome) VALUES ('c-2', 'p-1', 'Municipal')"))
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as c:
            c.execute(sa.text("INSERT INTO vagas (id, programa_id, descricao, quantidade) VALUES ('v-3', 'p-1', 'Noite', 0)"))
