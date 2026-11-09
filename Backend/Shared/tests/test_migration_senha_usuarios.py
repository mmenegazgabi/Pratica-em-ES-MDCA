"""T-35 · US-08: usuarios.senha_hash migration, run against a real Postgres.

Like test_migrations.py, these tests downgrade the target database to an empty
schema, so they only run when TEST_DATABASE_URL points at a disposable database.
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

# Revision right before this migration; a relative "-1" would break once newer
# migrations are added.
REV_PESSOAS = "b7d4e19a2c60"

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; migration tests need a disposable Postgres",
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


@pytest.fixture
def migrated_db():
    nome = make_url(TEST_DATABASE_URL).database or ""
    if "test" not in nome or TEST_DATABASE_URL == os.environ.get("DATABASE_URL"):
        pytest.fail("TEST_DATABASE_URL must point at a disposable test database")

    config = _alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = sa.create_engine(_sqlalchemy_url(TEST_DATABASE_URL))
    try:
        yield engine, config
    finally:
        engine.dispose()
        command.downgrade(config, "base")


def _colunas(engine):
    return {c["name"]: c for c in sa.inspect(engine).get_columns("usuarios")}


def test_senha_e_opcional_e_contas_antigas_continuam_validas(migrated_db):
    engine, config = migrated_db

    command.downgrade(config, REV_PESSOAS)
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO usuarios (id, nome) VALUES ('ana', 'Ana Martins')"))
    command.upgrade(config, "head")

    assert _colunas(engine)["senha_hash"]["nullable"] is True
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT senha_hash FROM usuarios")).scalar_one() is None


def test_downgrade_remove_so_a_coluna_da_senha(migrated_db):
    engine, config = migrated_db

    command.downgrade(config, REV_PESSOAS)

    assert "senha_hash" not in _colunas(engine)
    assert {"id", "nome", "email", "ativo"} <= set(_colunas(engine))
