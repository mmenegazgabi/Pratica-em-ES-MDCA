"""T-01 orcamentos and T-10 lancamentos migrations, run against a real Postgres.

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
    assert "lancamentos" not in tabelas
    assert "orcamentos" not in tabelas
    assert "projetos" not in tabelas

    command.upgrade(config, "head")
    tabelas = set(sa.inspect(engine).get_table_names())
    assert "orcamentos" in tabelas
    assert "lancamentos" in tabelas


# T-10 · US-03: lancamentos migration.

CHECK_VIOLATION = "23514"
# Revision right before lancamentos; a relative "-1" would break once newer
# migrations are added.
REV_ORCAMENTOS = "f59a65664c33"


def _inserir_projeto_e_orcamento(conn) -> None:
    conn.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Projeto 1')"))
    _inserir_orcamento(conn, "p-1")


def _inserir_lancamento(
    conn,
    projeto_id: str = "p-1",
    status: str = "pendente",
    valor: float = 100,
    descricao: str = "compra",
    orcamento_id: str = "orc-1",
    motivo_rejeicao: str | None = None,
) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO lancamentos
                (id, projeto_id, orcamento_id, categoria, valor, data, descricao,
                 status, motivo_rejeicao)
            VALUES
                (:id, :projeto_id, :orcamento_id, 'materiais', :valor, '2026-05-01',
                 :descricao, :status, :motivo_rejeicao)
            """
        ),
        {
            "id": "lan-1",
            "projeto_id": projeto_id,
            "orcamento_id": orcamento_id,
            "status": status,
            "valor": valor,
            "descricao": descricao,
            "motivo_rejeicao": motivo_rejeicao,
        },
    )


def test_migration_cria_tabela_lancamentos_com_colunas_esperadas(migrated_db):
    engine, _ = migrated_db
    inspector = sa.inspect(engine)

    assert "lancamentos" in inspector.get_table_names()
    colunas = {c["name"] for c in inspector.get_columns("lancamentos")}
    assert colunas == {
        "id",
        "projeto_id",
        "orcamento_id",
        "categoria",
        "valor",
        "data",
        "descricao",
        "status",
        "comprovante_url",
        "motivo_rejeicao",
        "autor_id",
    }

    fks = {
        (tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]))
        for fk in inspector.get_foreign_keys("lancamentos")
    }
    assert fks == {
        (("projeto_id",), "projetos", ("id",)),
        (("orcamento_id",), "orcamentos", ("id",)),
    }


@pytest.mark.parametrize(
    "status, motivo",
    [("pendente", None), ("aprovado", None), ("rejeitado", "nota fiscal ilegível")],
)
def test_lancamento_com_status_valido_e_gravado(migrated_db, status, motivo):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_projeto_e_orcamento(conn)
        _inserir_lancamento(conn, status=status, motivo_rejeicao=motivo)
        gravado = conn.execute(sa.text("SELECT status FROM lancamentos")).scalar_one()
        conn.rollback()

    assert gravado == status


def test_status_do_lancamento_tem_default_pendente(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_projeto_e_orcamento(conn)
        conn.execute(
            sa.text(
                """
                INSERT INTO lancamentos
                    (id, projeto_id, orcamento_id, categoria, valor, data, descricao)
                VALUES
                    ('lan-1', 'p-1', 'orc-1', 'materiais', 100, '2026-05-01', 'compra')
                """
            )
        )
        status = conn.execute(sa.text("SELECT status FROM lancamentos")).scalar_one()
        conn.rollback()

    assert status == "pendente"


def test_check_impede_lancamento_com_status_invalido(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_projeto_e_orcamento(conn)
        with pytest.raises(IntegrityError) as erro:
            _inserir_lancamento(conn, status="cancelado")
        conn.rollback()

    assert erro.value.orig.sqlstate == CHECK_VIOLATION


@pytest.mark.parametrize(
    "campos",
    [
        {"valor": 0},
        {"valor": -100},
        {"descricao": ""},
        {"descricao": "   "},
        {"status": "rejeitado"},
        {"status": "rejeitado", "motivo_rejeicao": "   "},
    ],
)
def test_check_impede_lancamento_com_campos_invalidos(migrated_db, campos):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_projeto_e_orcamento(conn)
        with pytest.raises(IntegrityError) as erro:
            _inserir_lancamento(conn, **campos)
        conn.rollback()

    assert erro.value.orig.sqlstate == CHECK_VIOLATION


@pytest.mark.parametrize(
    "campos",
    [{"projeto_id": "projeto-fantasma"}, {"orcamento_id": "orcamento-fantasma"}],
)
def test_fk_impede_insercao_de_lancamento_com_referencia_inexistente(migrated_db, campos):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_projeto_e_orcamento(conn)
        with pytest.raises(IntegrityError) as erro:
            _inserir_lancamento(conn, **campos)
        conn.rollback()

    assert erro.value.orig.sqlstate == FOREIGN_KEY_VIOLATION


def test_downgrade_de_lancamentos_nao_deixa_orfaos(migrated_db):
    engine, config = migrated_db

    command.downgrade(config, REV_ORCAMENTOS)

    inspector = sa.inspect(engine)
    tabelas = set(inspector.get_table_names())
    assert "lancamentos" not in tabelas
    assert "projetos" in tabelas
    assert "orcamentos" in tabelas
    with engine.connect() as conn:
        restantes = conn.execute(
            sa.text(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conname LIKE '%lancamentos%'"
            )
        ).scalar_one()
    assert restantes == 0

    command.upgrade(config, "head")
    assert "lancamentos" in sa.inspect(engine).get_table_names()
