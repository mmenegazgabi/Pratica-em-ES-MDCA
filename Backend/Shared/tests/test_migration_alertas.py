"""T-59 · US-06: alertas de infrequência, ações de busca ativa e limite de faltas do programa.

Like the other migration tests, these downgrade the target database to an empty schema,
so they only run when TEST_DATABASE_URL points at a disposable database.
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

# Revision right before this migration (T-55).
REV_ATIVIDADES = "4e3a59521428"
TABELAS = {"alertas", "acoes_busca_ativa"}

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


ALERTA = """
    INSERT INTO alertas (id, tipo, programa_id, pessoa_id, turma_id, responsavel_id, situacao,
                         faltas_consecutivas, limite, primeira_falta, ultima_falta,
                         encerrado_em, encerrado_por, justificativa_encerramento)
    VALUES (:id, :tipo, 'p-1', 'pe-1', 't-1', 'ana', :situacao, :faltas, :limite,
            '2026-10-01', '2026-10-08', :encerrado_em, :encerrado_por, :justificativa)
"""
ACAO = """
    INSERT INTO acoes_busca_ativa (id, alerta_id, tipo, data, resultado, responsavel_id)
    VALUES (:id, 'al-1', :tipo, '2026-10-09', :resultado, 'ana')
"""


def _alerta(**extra):
    dados = {"id": "al-x", "tipo": "infrequencia", "situacao": "aberto", "faltas": 3, "limite": 3,
             "encerrado_em": None, "encerrado_por": None, "justificativa": None}
    return {**dados, **extra}


@pytest.fixture
def com_base(migrated_db):
    engine, _ = migrated_db
    with engine.begin() as conn:
        _executar(conn, "INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear')")
        _executar(conn, "INSERT INTO usuarios (id, nome) VALUES ('ana', 'Ana Martins')")
        _executar(conn, "INSERT INTO espacos (id, programa_id, nome) VALUES ('e-1', 'p-1', 'Ateliê')")
        _executar(conn, "INSERT INTO nucleos_familiares (id, nome) VALUES ('f-1', 'Oliveira')")
        _executar(
            conn,
            "INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id) "
            "VALUES ('pe-1', 'Lara Oliveira', 'lara oliveira', '2013-05-12', 'f-1', 'p-1')",
        )
        _executar(
            conn,
            "INSERT INTO turmas (id, programa_id, nome, espaco_id, responsavel_id, capacidade, dias_semana, hora_inicio, hora_fim) "
            "VALUES ('t-1', 'p-1', 'Oficina', 'e-1', 'ana', 10, '{1}', '14:00', '16:00')",
        )
        _executar(conn, ALERTA, **_alerta(id="al-1"))
    return engine


def _violacao(engine, sql, **params) -> str:
    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as erro:
            _executar(conn, sql, **params)
        conn.rollback()
    return erro.value.orig.sqlstate


# --- Estrutura e limite do programa ------------------------------------------------


def test_programa_ganha_limite_de_faltas_com_padrao_3(com_base):
    with com_base.begin() as conn:
        _executar(conn, "INSERT INTO projetos (id, nome) VALUES ('p-2', 'Oficina')")
        limite = _executar(conn, "SELECT limite_faltas FROM projetos WHERE id = 'p-2'").scalar_one()

    assert limite == 3
    assert _violacao(com_base, "UPDATE projetos SET limite_faltas = 0 WHERE id = 'p-1'") == CHECK_VIOLATION


def test_tabelas_criadas_com_os_campos_da_us06(migrated_db):
    engine, _ = migrated_db
    inspetor = sa.inspect(engine)

    assert TABELAS <= set(inspetor.get_table_names())
    assert {"pessoa_id", "turma_id", "responsavel_id", "situacao", "faltas_consecutivas", "limite", "justificativa_encerramento"} <= {
        c["name"] for c in inspetor.get_columns("alertas")
    }
    assert {"alerta_id", "tipo", "data", "resultado", "responsavel_id"} <= {c["name"] for c in inspetor.get_columns("acoes_busca_ativa")}


# --- Alerta --------------------------------------------------------------------------


def test_um_alerta_aberto_por_pessoa_e_turma(com_base):
    assert _violacao(com_base, ALERTA, **_alerta(id="al-2")) == UNIQUE_VIOLATION


def test_encerrado_pode_ter_outro_aberto_depois(com_base):
    with com_base.begin() as conn:
        _executar(
            conn,
            "UPDATE alertas SET situacao = 'encerrado', encerrado_em = now(), encerrado_por = 'ana', "
            "justificativa_encerramento = 'Voltou a frequentar' WHERE id = 'al-1'",
        )
        _executar(conn, ALERTA, **_alerta(id="al-2"))

    with com_base.connect() as conn:
        assert _executar(conn, "SELECT count(*) FROM alertas").scalar_one() == 2


@pytest.mark.parametrize(
    "justificativa, encerrado_por",
    [(None, "ana"), ("   ", "ana"), ("Voltou a frequentar", None)],
    ids=["sem-justificativa", "justificativa-em-branco", "sem-quem-encerrou"],
)
def test_encerramento_exige_justificativa_e_quem_encerrou(com_base, justificativa, encerrado_por):
    sql = (
        "UPDATE alertas SET situacao = 'encerrado', encerrado_em = now(), encerrado_por = :por, "
        "justificativa_encerramento = :justificativa WHERE id = 'al-1'"
    )

    assert _violacao(com_base, sql, por=encerrado_por, justificativa=justificativa) == CHECK_VIOLATION


@pytest.mark.parametrize(
    "extra",
    [{"tipo": "outro"}, {"situacao": "pendente"}, {"faltas": 2, "limite": 3}, {"limite": 0, "faltas": 0}],
    ids=["tipo-invalido", "situacao-invalida", "abaixo-do-limite", "limite-zero"],
)
def test_check_do_alerta(com_base, extra):
    with com_base.begin() as conn:
        _executar(conn, "UPDATE alertas SET situacao = 'encerrado', encerrado_em = now(), encerrado_por = 'ana', justificativa_encerramento = 'x'")

    assert _violacao(com_base, ALERTA, **_alerta(**extra)) == CHECK_VIOLATION


# --- Ações de busca ativa ------------------------------------------------------------


def test_acao_exige_tipo_valido_resultado_e_alerta_existente(com_base):
    assert _violacao(com_base, ACAO, id="ac-1", tipo="visita", resultado="Família localizada") == CHECK_VIOLATION
    assert _violacao(com_base, ACAO, id="ac-1", tipo="busca_ativa", resultado="  ") == CHECK_VIOLATION
    sql = ACAO.replace("'al-1'", "'nao-existe'")
    assert _violacao(com_base, sql, id="ac-1", tipo="busca_ativa", resultado="ok") == FOREIGN_KEY_VIOLATION


def test_alerta_com_acoes_nao_pode_ser_apagado(com_base):
    with com_base.begin() as conn:
        _executar(conn, ACAO, id="ac-1", tipo="contato_familia", resultado="Mãe atendeu e explicou a falta")

    assert _violacao(com_base, "DELETE FROM alertas WHERE id = 'al-1'") == FOREIGN_KEY_VIOLATION


# --- Reversibilidade -----------------------------------------------------------------


def test_downgrade_remove_so_o_que_a_migration_criou_e_upgrade_recria(migrated_db):
    engine, config = migrated_db

    command.downgrade(config, REV_ATIVIDADES)
    inspetor = sa.inspect(engine)
    assert not TABELAS & set(inspetor.get_table_names())
    assert "limite_faltas" not in {c["name"] for c in inspetor.get_columns("projetos")}
    assert {"atividades", "chamadas", "evidencias", "projetos"} <= set(inspetor.get_table_names())

    command.upgrade(config, "head")
    assert TABELAS <= set(sa.inspect(engine).get_table_names())
