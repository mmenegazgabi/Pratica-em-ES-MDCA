"""T-38 · US-01: espacos and vinculos_equipe migration, run against a real Postgres.

Like test_migrations.py, these tests downgrade the target database to an empty
schema, so they only run when TEST_DATABASE_URL points at a disposable database.
The helpers are repeated here so this file does not depend on the others.
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
UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"

# Revision right before this migration (T-32); a relative "-1" would break once
# newer migrations are added.
REV_USUARIOS_PAPEIS = "9409373416eb"
TABELAS = {"espacos", "vinculos_equipe"}

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


def _garantir_banco_descartavel(url: str) -> None:
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


def _preparar_programa_e_usuario(conn) -> None:
    conn.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear')"))
    conn.execute(sa.text("INSERT INTO usuarios (id, nome) VALUES ('jessica', 'Jéssica Almeida')"))


def _vincular(conn, vinculo_id="v-1", papel_id="educador", entrada="2026-03-01", saida=None):
    conn.execute(
        sa.text(
            """
            INSERT INTO vinculos_equipe
                (id, usuario_id, programa_id, papel_id, data_entrada, data_saida)
            VALUES (:id, 'jessica', 'p-1', :papel, :entrada, :saida)
            """
        ),
        {"id": vinculo_id, "papel": papel_id, "entrada": entrada, "saida": saida},
    )


def _inserir_espaco(conn, espaco_id="e-1", nome="Sala de convivência", capacidade=25):
    conn.execute(
        sa.text(
            "INSERT INTO espacos (id, programa_id, nome, capacidade) "
            "VALUES (:id, 'p-1', :nome, :capacidade)"
        ),
        {"id": espaco_id, "nome": nome, "capacidade": capacidade},
    )


def test_migration_cria_tabelas_com_colunas_esperadas(migrated_db):
    engine, _ = migrated_db
    inspetor = sa.inspect(engine)

    assert {c["name"] for c in inspetor.get_columns("espacos")} == {
        "id",
        "programa_id",
        "nome",
        "capacidade",
    }
    assert {c["name"] for c in inspetor.get_columns("vinculos_equipe")} == {
        "id",
        "usuario_id",
        "programa_id",
        "papel_id",
        "data_entrada",
        "data_saida",
        "criado_em",
    }


def test_vinculo_registra_usuario_programa_papel_e_datas(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _preparar_programa_e_usuario(conn)
        _vincular(conn)
        vinculo = conn.execute(
            sa.text(
                "SELECT usuario_id, programa_id, papel_id, data_entrada::text, data_saida "
                "FROM vinculos_equipe"
            )
        ).one()
        conn.rollback()

    # data_saida is optional: an open link has none.
    assert tuple(vinculo) == ("jessica", "p-1", "educador", "2026-03-01", None)


def test_registrar_saida_mantem_o_vinculo(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _preparar_programa_e_usuario(conn)
        _vincular(conn)
        conn.execute(sa.text("UPDATE vinculos_equipe SET data_saida = '2026-09-30' WHERE id = 'v-1'"))
        vinculos = conn.execute(
            sa.text("SELECT id, data_saida::text FROM vinculos_equipe")
        ).all()
        conn.rollback()

    assert [tuple(v) for v in vinculos] == [("v-1", "2026-09-30")]


def test_check_impede_saida_antes_da_entrada(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _preparar_programa_e_usuario(conn)
        with pytest.raises(IntegrityError) as erro:
            _vincular(conn, entrada="2026-03-01", saida="2026-02-28")
        conn.rollback()

    assert erro.value.orig.sqlstate == CHECK_VIOLATION


def test_so_um_vinculo_ativo_por_pessoa_programa_e_papel(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _preparar_programa_e_usuario(conn)
        _vincular(conn, "v-1")
        # Another role in the same program is a different link.
        _vincular(conn, "v-2", papel_id="assistente_social")
        with pytest.raises(IntegrityError) as erro:
            _vincular(conn, "v-3")
        conn.rollback()

    assert erro.value.orig.sqlstate == UNIQUE_VIOLATION


def test_quem_saiu_pode_voltar_com_novo_vinculo(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _preparar_programa_e_usuario(conn)
        _vincular(conn, "v-1", entrada="2025-03-01", saida="2025-12-15")
        _vincular(conn, "v-2", entrada="2026-03-01")
        vinculos = conn.execute(sa.text("SELECT count(*) FROM vinculos_equipe")).scalar_one()
        conn.rollback()

    assert vinculos == 2


@pytest.mark.parametrize(
    "campo, valor",
    [("usuario_id", "ninguem"), ("programa_id", "p-inexistente"), ("papel_id", "estagiario")],
)
def test_fk_impede_vinculo_com_referencia_inexistente(migrated_db, campo, valor):
    engine, _ = migrated_db
    valores = {"usuario_id": "jessica", "programa_id": "p-1", "papel_id": "educador"}
    valores[campo] = valor

    with engine.connect() as conn:
        _preparar_programa_e_usuario(conn)
        with pytest.raises(IntegrityError) as erro:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO vinculos_equipe
                        (id, usuario_id, programa_id, papel_id, data_entrada)
                    VALUES ('v-1', :usuario_id, :programa_id, :papel_id, '2026-03-01')
                    """
                ),
                valores,
            )
        conn.rollback()

    assert erro.value.orig.sqlstate == FOREIGN_KEY_VIOLATION


@pytest.mark.parametrize(
    "apagar",
    [
        "DELETE FROM usuarios WHERE id = 'jessica'",
        "DELETE FROM projetos WHERE id = 'p-1'",
        "DELETE FROM papeis WHERE id = 'educador'",
    ],
)
def test_historico_impede_apagar_usuario_programa_ou_papel_com_vinculo(migrated_db, apagar):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _preparar_programa_e_usuario(conn)
        _vincular(conn, saida="2026-09-30")
        with pytest.raises(IntegrityError) as erro:
            conn.execute(sa.text(apagar))
        conn.rollback()

    assert erro.value.orig.sqlstate == FOREIGN_KEY_VIOLATION


def test_espaco_pertence_a_um_programa(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _preparar_programa_e_usuario(conn)
        _inserir_espaco(conn)
        _inserir_espaco(conn, "e-2", "Ateliê", None)
        espacos = conn.execute(
            sa.text("SELECT nome, capacidade FROM espacos WHERE programa_id = 'p-1' ORDER BY id")
        ).all()
        conn.rollback()

    assert [tuple(e) for e in espacos] == [("Sala de convivência", 25), ("Ateliê", None)]


def test_nome_de_espaco_repetido_no_programa_e_barrado(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _preparar_programa_e_usuario(conn)
        _inserir_espaco(conn, "e-1", "Ateliê")
        with pytest.raises(IntegrityError) as erro:
            _inserir_espaco(conn, "e-2", "ateliê")
        conn.rollback()

    assert erro.value.orig.sqlstate == UNIQUE_VIOLATION


@pytest.mark.parametrize("campos", [{"nome": "  "}, {"capacidade": 0}])
def test_check_impede_espaco_sem_nome_ou_com_capacidade_invalida(migrated_db, campos):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _preparar_programa_e_usuario(conn)
        with pytest.raises(IntegrityError) as erro:
            _inserir_espaco(conn, **campos)
        conn.rollback()

    assert erro.value.orig.sqlstate == CHECK_VIOLATION


def test_fk_impede_espaco_de_programa_inexistente(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as erro:
            _inserir_espaco(conn)
        conn.rollback()

    assert erro.value.orig.sqlstate == FOREIGN_KEY_VIOLATION


def test_downgrade_remove_so_as_tabelas_novas_e_upgrade_recria(migrated_db):
    engine, config = migrated_db

    command.downgrade(config, REV_USUARIOS_PAPEIS)
    tabelas = set(sa.inspect(engine).get_table_names())
    assert not TABELAS & tabelas
    assert {"projetos", "usuarios", "papeis"} <= tabelas

    command.upgrade(config, "head")
    assert TABELAS <= set(sa.inspect(engine).get_table_names())
