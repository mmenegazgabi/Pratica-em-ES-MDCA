"""T-01: orcamentos migration, run against a real Postgres.

These tests downgrade the target database to an empty schema, so they only
run when TEST_DATABASE_URL points at a disposable database.
"""

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

SHARED_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

FOREIGN_KEY_VIOLATION = "23503"

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; migration tests need a disposable Postgres",
)


def _sqlalchemy_url(url: str) -> str:
    # Same rule as migrations/env.py: plain postgres URLs use psycopg v3.
    parsed = make_url(url)
    if parsed.drivername in ("postgresql", "postgres"):
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed.render_as_string(hide_password=False)


def _alembic_config() -> Config:
    config = Config(str(SHARED_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SHARED_DIR / "migrations"))
    # ConfigParser interpolates "%", so URL-encoded passwords must be escaped.
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    return config


def _garantir_banco_descartavel(url: str) -> None:
    # The fixture drops every table, so refuse anything that looks like a real DB.
    nome = make_url(url).database or ""
    if "test" not in nome:
        pytest.fail(f"TEST_DATABASE_URL must point at a test database, got {nome!r}")
    if url == os.environ.get("DATABASE_URL"):
        pytest.fail("TEST_DATABASE_URL must differ from DATABASE_URL")


@pytest.fixture
def migrated_db():
    _garantir_banco_descartavel(TEST_DATABASE_URL)

    config = _alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = sa.create_engine(_sqlalchemy_url(TEST_DATABASE_URL))
    try:
        yield engine, config
    finally:
        engine.dispose()
        command.downgrade(config, "base")


def _inserir_orcamento(conn, projeto_id: str) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO orcamentos
                (id, projeto_id, valor_total, periodo_inicio, periodo_fim, categorias)
            VALUES
                (:id, :projeto_id, :valor_total, :inicio, :fim, :categorias)
            """
        ),
        {
            "id": "orc-1",
            "projeto_id": projeto_id,
            "valor_total": 1000,
            "inicio": "2026-01-01",
            "fim": "2026-12-31",
            "categorias": ["materiais"],
        },
    )


def test_migration_cria_tabela_orcamentos_com_colunas_esperadas(migrated_db):
    engine, _ = migrated_db
    inspector = sa.inspect(engine)

    assert "orcamentos" in inspector.get_table_names()
    colunas = {c["name"] for c in inspector.get_columns("orcamentos")}
    assert colunas == {
        "id",
        "projeto_id",
        "valor_total",
        "periodo_inicio",
        "periodo_fim",
        "categorias",
    }

    [fk] = inspector.get_foreign_keys("orcamentos")
    assert fk["constrained_columns"] == ["projeto_id"]
    assert fk["referred_table"] == "projetos"
    assert fk["referred_columns"] == ["id"]


def test_fk_impede_insercao_de_orcamento_com_projeto_id_inexistente(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as erro:
            _inserir_orcamento(conn, "projeto-fantasma")
        conn.rollback()

    assert erro.value.orig.sqlstate == FOREIGN_KEY_VIOLATION


def test_orcamento_com_projeto_existente_e_gravado(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        conn.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Projeto 1')"))
        _inserir_orcamento(conn, "p-1")
        total = conn.execute(sa.text("SELECT count(*) FROM orcamentos")).scalar_one()
        conn.rollback()

    assert total == 1


def test_migration_e_reversivel(migrated_db):
    engine, config = migrated_db

    command.downgrade(config, "base")
    tabelas = set(sa.inspect(engine).get_table_names())
    assert "orcamentos" not in tabelas
    assert "projetos" not in tabelas

    command.upgrade(config, "head")
    assert "orcamentos" in sa.inspect(engine).get_table_names()
