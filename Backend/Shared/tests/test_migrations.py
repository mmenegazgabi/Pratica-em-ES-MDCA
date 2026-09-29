import os

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
ALEMBIC_INI = os.path.join(BASE_DIR, "alembic.ini")
MIGRATIONS_DIR = os.path.join(BASE_DIR, "migrations")

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg2://localhost/mdca_test"
)


def _alembic_config() -> Config:
    config = Config(ALEMBIC_INI)
    config.set_main_option("script_location", MIGRATIONS_DIR)
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


@pytest.fixture
def migrated_db():
    config = _alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = sa.create_engine(TEST_DATABASE_URL)
    try:
        yield engine, config
    finally:
        engine.dispose()
        command.downgrade(config, "base")


def test_migration_cria_tabela_orcamentos_com_colunas_esperadas(migrated_db):
    engine, _ = migrated_db
    inspector = sa.inspect(engine)

    assert "orcamentos" in inspector.get_table_names()
    colunas = {c["name"] for c in inspector.get_columns("orcamentos")}
    assert colunas == {
        "id",
        "projeto_id",
        "valor_total",
        "data_inicio",
        "data_fim",
        "categorias_despesa",
    }


def test_fk_impede_insercao_de_orcamento_com_projeto_id_inexistente(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            with pytest.raises(IntegrityError):
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO orcamentos
                            (id, projeto_id, valor_total, data_inicio, data_fim, categorias_despesa)
                        VALUES
                            (:id, :projeto_id, :valor_total, :inicio, :fim, :categorias)
                        """
                    ),
                    {
                        "id": "orc-1",
                        "projeto_id": "projeto-fantasma",
                        "valor_total": 1000,
                        "inicio": "2026-01-01",
                        "fim": "2026-12-31",
                        "categorias": ["materiais"],
                    },
                )
        finally:
            trans.rollback()


def test_migration_e_reversivel(migrated_db):
    engine, config = migrated_db

    command.downgrade(config, "base")

    tabelas = set(sa.inspect(engine).get_table_names())
    assert "orcamentos" not in tabelas
    assert "projetos" not in tabelas
