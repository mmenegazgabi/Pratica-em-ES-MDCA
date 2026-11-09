"""T-51 · US-04: classes, enrollments and the waiting list.

Like the other migration tests, these downgrade the target database to an empty schema,
so they only run when TEST_DATABASE_URL points at a disposable database. The helpers are
repeated here so this file does not depend on the others.
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

# Revision right before this migration (T-35); a relative "-1" would break later.
REV_SENHA = "62959ecab341"
TABELAS = {"turmas", "matriculas"}

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


def _executar(conn, sql, **params):
    return conn.execute(sa.text(sql), params)


TURMA = """
    INSERT INTO turmas (id, programa_id, nome, espaco_id, responsavel_id, capacidade, dias_semana, hora_inicio, hora_fim)
    VALUES (:id, 'p-1', :nome, 'e-1', 'ana', :capacidade, CAST(:dias AS smallint[]), :inicio, :fim)
"""


def _base(conn) -> None:
    """Programa com espaço, uma educadora, duas pessoas e a turma t-1 (seg e qua, 14h às 16h)."""
    _executar(conn, "INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear')")
    _executar(conn, "INSERT INTO usuarios (id, nome) VALUES ('ana', 'Ana Martins')")
    _executar(conn, "INSERT INTO espacos (id, programa_id, nome) VALUES ('e-1', 'p-1', 'Ateliê')")
    _executar(conn, "INSERT INTO nucleos_familiares (id, nome) VALUES ('f-1', 'Oliveira')")
    _executar(
        conn,
        """
        INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id) VALUES
            ('pe-1', 'Lara Oliveira', 'lara oliveira', '2013-05-12', 'f-1', 'p-1'),
            ('pe-2', 'Davi Oliveira', 'davi oliveira', '2015-02-01', 'f-1', 'p-1')
        """,
    )
    _executar(conn, TURMA, id="t-1", nome="Oficina de arte", capacidade=20, dias="{1,3}", inicio="14:00", fim="16:00")


def _violacao(engine, sql, **params) -> str:
    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as erro:
            _executar(conn, sql, **params)
        conn.rollback()
    return erro.value.orig.sqlstate


@pytest.fixture
def com_base(migrated_db):
    engine, _ = migrated_db
    with engine.begin() as conn:
        _base(conn)
    return engine


MATRICULA = """
    INSERT INTO matriculas (id, turma_id, pessoa_id, situacao, data_entrada, data_saida, motivo_saida)
    VALUES (:id, 't-1', :pessoa, :situacao, :entrada, :saida, :motivo)
"""


# --- Estrutura -----------------------------------------------------------------


def test_migration_cria_turmas_e_matriculas(migrated_db):
    engine, _ = migrated_db
    inspetor = sa.inspect(engine)

    assert TABELAS <= set(inspetor.get_table_names())
    colunas = {c["name"] for c in inspetor.get_columns("turmas")}
    assert {"programa_id", "espaco_id", "responsavel_id", "capacidade", "dias_semana", "hora_inicio", "hora_fim"} <= colunas
    colunas = {c["name"] for c in inspetor.get_columns("matriculas")}
    assert {"turma_id", "pessoa_id", "situacao", "inscrito_em", "data_entrada", "data_saida", "motivo_saida"} <= colunas


# --- Turma ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "campo, valor",
    [("programa_id", "nao-existe"), ("espaco_id", "nao-existe"), ("responsavel_id", "nao-existe")],
)
def test_turma_referencia_programa_local_e_responsavel(com_base, campo, valor):
    dados = {"programa_id": "p-1", "espaco_id": "e-1", "responsavel_id": "ana", campo: valor}
    sql = (
        "INSERT INTO turmas (id, programa_id, nome, espaco_id, responsavel_id, capacidade, dias_semana, hora_inicio, hora_fim) "
        "VALUES ('t-x', :programa_id, 'X', :espaco_id, :responsavel_id, 10, '{2}', '08:00', '09:00')"
    )
    assert _violacao(com_base, sql, **dados) == FOREIGN_KEY_VIOLATION


@pytest.mark.parametrize(
    "capacidade, dias, inicio, fim",
    [
        (0, "{1}", "08:00", "09:00"),
        (10, "{}", "08:00", "09:00"),
        (10, "{8}", "08:00", "09:00"),
        (10, "{1}", "09:00", "09:00"),
    ],
)
def test_check_da_turma(com_base, capacidade, dias, inicio, fim):
    estado = _violacao(com_base, TURMA, id="t-x", nome="X", capacidade=capacidade, dias=dias, inicio=inicio, fim=fim)

    assert estado == CHECK_VIOLATION


def test_nome_da_turma_unico_no_programa(com_base):
    estado = _violacao(com_base, TURMA, id="t-x", nome="OFICINA DE ARTE", capacidade=5, dias="{2}", inicio="08:00", fim="09:00")

    assert estado == UNIQUE_VIOLATION


# --- Matrícula -----------------------------------------------------------------


def test_desligamento_exige_data_e_motivo(com_base):
    base = {"id": "m-x", "pessoa": "pe-1", "situacao": "desligada", "entrada": "2026-03-01"}

    assert _violacao(com_base, MATRICULA, **base, saida=None, motivo="Mudou de cidade") == CHECK_VIOLATION
    assert _violacao(com_base, MATRICULA, **base, saida="2026-06-01", motivo=None) == CHECK_VIOLATION
    assert _violacao(com_base, MATRICULA, **base, saida="2026-06-01", motivo="   ") == CHECK_VIOLATION


def test_matricula_ativa_tem_entrada_e_saida_nao_antecede_entrada(com_base):
    assert _violacao(com_base, MATRICULA, id="m-x", pessoa="pe-1", situacao="ativa", entrada=None, saida=None, motivo=None) == CHECK_VIOLATION
    estado = _violacao(
        com_base, MATRICULA, id="m-x", pessoa="pe-1", situacao="desligada", entrada="2026-03-01", saida="2026-02-01", motivo="Erro"
    )
    assert estado == CHECK_VIOLATION


def test_uma_matricula_em_aberto_por_pessoa_e_turma_e_o_historico_pode_repetir(com_base):
    with com_base.begin() as conn:
        _executar(conn, MATRICULA, id="m-1", pessoa="pe-1", situacao="desligada", entrada="2026-03-01", saida="2026-04-01", motivo="Mudou de turno")
        _executar(conn, MATRICULA, id="m-2", pessoa="pe-1", situacao="ativa", entrada="2026-05-01", saida=None, motivo=None)

    estado = _violacao(com_base, MATRICULA, id="m-3", pessoa="pe-1", situacao="espera", entrada=None, saida=None, motivo=None)
    assert estado == UNIQUE_VIOLATION


def test_lista_de_espera_mantem_a_ordem_de_inscricao(com_base):
    with com_base.begin() as conn:
        _executar(conn, MATRICULA, id="m-1", pessoa="pe-2", situacao="espera", entrada=None, saida=None, motivo=None)
    with com_base.begin() as conn:
        _executar(conn, MATRICULA, id="m-2", pessoa="pe-1", situacao="espera", entrada=None, saida=None, motivo=None)

    with com_base.connect() as conn:
        ordem = conn.execute(
            sa.text("SELECT pessoa_id FROM matriculas WHERE situacao = 'espera' ORDER BY inscrito_em, id")
        ).scalars().all()
    assert ordem == ["pe-2", "pe-1"]


# --- Reversibilidade -----------------------------------------------------------


def test_downgrade_remove_so_as_tabelas_novas_e_upgrade_recria(migrated_db):
    engine, config = migrated_db

    command.downgrade(config, REV_SENHA)
    tabelas = set(sa.inspect(engine).get_table_names())
    assert not TABELAS & tabelas
    assert {"projetos", "espacos", "pessoas"} <= tabelas

    command.upgrade(config, "head")
    assert TABELAS <= set(sa.inspect(engine).get_table_names())
