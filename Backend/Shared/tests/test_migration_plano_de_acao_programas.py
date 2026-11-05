"""T-44 · US-02: program fields, convenios, objetivos, acoes, metas, registros_meta and
vagas migration, run against a real Postgres.

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

# Revision right before this migration (T-38); a relative "-1" would break once
# newer migrations are added.
REV_VINCULOS_EQUIPE = "3fb5b9b4c7fa"
TABELAS = {"convenios", "objetivos", "acoes", "metas", "registros_meta", "vagas"}
COLUNAS_NOVAS_PROGRAMA = {
    "identificador",
    "publico",
    "responsavel",
    "vigencia_inicio",
    "vigencia_fim",
    "descricao",
}

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


def _inserir_programa(conn, programa_id="p-1", identificador="SCFV", inicio="2026-02-01", fim="2026-12-18"):
    conn.execute(
        sa.text(
            """
            INSERT INTO projetos
                (id, nome, identificador, publico, responsavel, vigencia_inicio, vigencia_fim)
            VALUES (:id, 'Convivência', :identificador, 'Crianças de 6 a 15 anos',
                    'Ana Martins', :inicio, :fim)
            """
        ),
        {"id": programa_id, "identificador": identificador, "inicio": inicio, "fim": fim},
    )


def _inserir_objetivo(conn, objetivo_id="o-1", descricao="Ampliar a participação"):
    conn.execute(
        sa.text("INSERT INTO objetivos (id, programa_id, descricao) VALUES (:id, 'p-1', :d)"),
        {"id": objetivo_id, "d": descricao},
    )


def _inserir_acao(conn, acao_id="a-1", **campos):
    valores = {
        "descricao": "Oficinas semanais",
        "inicio": "2026-03-01",
        "fim": "2026-11-30",
        "resultado": "120 oficinas no ano",
        "periodicidade": "mensal",
    }
    valores.update(campos)
    conn.execute(
        sa.text(
            """
            INSERT INTO acoes (id, objetivo_id, descricao, periodo_inicio, periodo_fim,
                               resultado_esperado, periodicidade)
            VALUES (:id, 'o-1', :descricao, :inicio, :fim, :resultado, :periodicidade)
            """
        ),
        {"id": acao_id, **valores},
    )


def _inserir_meta(conn, meta_id="m-1", planejado=120):
    conn.execute(
        sa.text(
            "INSERT INTO metas (id, acao_id, descricao, valor_planejado, unidade) "
            "VALUES (:id, 'a-1', 'Oficinas realizadas', :planejado, 'oficinas')"
        ),
        {"id": meta_id, "planejado": planejado},
    )


def _registrar(conn, registro_id="r-1", valor=10):
    conn.execute(
        sa.text(
            "INSERT INTO registros_meta (id, meta_id, data, valor_realizado) "
            "VALUES (:id, 'm-1', '2026-04-30', :valor)"
        ),
        {"id": registro_id, "valor": valor},
    )


def _plano_completo(conn) -> None:
    _inserir_programa(conn)
    _inserir_objetivo(conn)
    _inserir_acao(conn)
    _inserir_meta(conn)


def test_migration_cria_tabelas_e_completa_o_programa(migrated_db):
    engine, _ = migrated_db
    inspetor = sa.inspect(engine)

    assert TABELAS <= set(inspetor.get_table_names())
    assert COLUNAS_NOVAS_PROGRAMA <= {c["name"] for c in inspetor.get_columns("projetos")}
    assert {c["name"] for c in inspetor.get_columns("acoes")} == {
        "id",
        "objetivo_id",
        "descricao",
        "periodo_inicio",
        "periodo_fim",
        "resultado_esperado",
        "periodicidade",
    }
    assert {c["name"] for c in inspetor.get_columns("metas")} == {
        "id",
        "acao_id",
        "descricao",
        "valor_planejado",
        "unidade",
    }


def test_programa_antigo_so_com_nome_continua_valido(migrated_db):
    # The Financeiro and the T-00f rows only have id and nome.
    engine, _ = migrated_db

    with engine.connect() as conn:
        conn.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear')"))
        programa = conn.execute(
            sa.text("SELECT nome, status, identificador, vigencia_inicio FROM projetos")
        ).one()
        conn.rollback()

    assert tuple(programa) == ("Semear", "ativo", None, None)


def test_identificador_repetido_e_barrado_sem_diferenciar_maiusculas(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_programa(conn, "p-1", "SCFV")
        with pytest.raises(IntegrityError) as erro:
            _inserir_programa(conn, "p-2", "scfv")
        conn.rollback()

    assert erro.value.orig.sqlstate == UNIQUE_VIOLATION


@pytest.mark.parametrize(
    "campos", [{"identificador": "  "}, {"inicio": "2026-12-18", "fim": "2026-02-01"}]
)
def test_check_impede_identificador_vazio_ou_vigencia_invertida(migrated_db, campos):
    engine, _ = migrated_db

    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as erro:
            _inserir_programa(conn, **campos)
        conn.rollback()

    assert erro.value.orig.sqlstate == CHECK_VIOLATION


def test_plano_de_acao_liga_objetivo_acao_meta_e_registros(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _plano_completo(conn)
        _registrar(conn, "r-1", 10)
        _registrar(conn, "r-2", 32)
        linha = conn.execute(
            sa.text(
                """
                SELECT o.programa_id, a.periodicidade, m.valor_planejado,
                       sum(r.valor_realizado) AS realizado
                FROM metas m
                JOIN acoes a ON a.id = m.acao_id
                JOIN objetivos o ON o.id = a.objetivo_id
                JOIN registros_meta r ON r.meta_id = m.id
                GROUP BY o.programa_id, a.periodicidade, m.valor_planejado
                """
            )
        ).one()
        conn.rollback()

    assert (linha.programa_id, linha.periodicidade) == ("p-1", "mensal")
    assert (float(linha.valor_planejado), float(linha.realizado)) == (120.0, 42.0)


@pytest.mark.parametrize(
    "campos",
    [
        {"resultado": " "},
        {"descricao": ""},
        {"periodicidade": "diaria"},
        {"inicio": "2026-11-30", "fim": "2026-03-01"},
    ],
)
def test_check_impede_acao_incompleta_ou_invalida(migrated_db, campos):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_programa(conn)
        _inserir_objetivo(conn)
        with pytest.raises(IntegrityError) as erro:
            _inserir_acao(conn, **campos)
        conn.rollback()

    assert erro.value.orig.sqlstate == CHECK_VIOLATION


@pytest.mark.parametrize("coluna", ["periodo_inicio", "periodo_fim", "resultado_esperado", "periodicidade"])
def test_acao_exige_periodo_resultado_e_periodicidade(migrated_db, coluna):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_programa(conn)
        _inserir_objetivo(conn)
        _inserir_acao(conn)
        with pytest.raises(IntegrityError) as erro:
            conn.execute(sa.text(f"UPDATE acoes SET {coluna} = NULL WHERE id = 'a-1'"))
        conn.rollback()

    assert erro.value.orig.sqlstate == "23502"  # not_null_violation


def test_check_impede_meta_sem_valor_planejado_positivo(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_programa(conn)
        _inserir_objetivo(conn)
        _inserir_acao(conn)
        with pytest.raises(IntegrityError) as erro:
            _inserir_meta(conn, planejado=0)
        conn.rollback()

    assert erro.value.orig.sqlstate == CHECK_VIOLATION


def test_check_impede_registro_sem_valor_realizado_positivo(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _plano_completo(conn)
        with pytest.raises(IntegrityError) as erro:
            _registrar(conn, valor=0)
        conn.rollback()

    assert erro.value.orig.sqlstate == CHECK_VIOLATION


@pytest.mark.parametrize(
    "inserir",
    [
        "INSERT INTO convenios (id, programa_id, nome) VALUES ('c-1', 'p-x', 'Convênio')",
        "INSERT INTO objetivos (id, programa_id, descricao) VALUES ('o-1', 'p-x', 'Objetivo')",
        "INSERT INTO vagas (id, programa_id, descricao, quantidade) VALUES ('v-1', 'p-x', 'Manhã', 20)",
    ],
)
def test_fk_impede_registro_de_programa_inexistente(migrated_db, inserir):
    engine, _ = migrated_db

    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as erro:
            conn.execute(sa.text(inserir))
        conn.rollback()

    assert erro.value.orig.sqlstate == FOREIGN_KEY_VIOLATION


def test_programa_com_plano_nao_pode_ser_apagado(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _plano_completo(conn)
        with pytest.raises(IntegrityError) as erro:
            conn.execute(sa.text("DELETE FROM projetos WHERE id = 'p-1'"))
        conn.rollback()

    assert erro.value.orig.sqlstate == FOREIGN_KEY_VIOLATION


def test_convenio_com_vigencia_invertida_e_barrado(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_programa(conn)
        with pytest.raises(IntegrityError) as erro:
            conn.execute(
                sa.text(
                    "INSERT INTO convenios (id, programa_id, nome, vigencia_inicio, vigencia_fim) "
                    "VALUES ('c-1', 'p-1', 'Convênio municipal', '2026-12-31', '2026-01-01')"
                )
            )
        conn.rollback()

    assert erro.value.orig.sqlstate == CHECK_VIOLATION


def test_vagas_repetidas_no_programa_sao_barradas_e_quantidade_e_positiva(migrated_db):
    engine, _ = migrated_db
    inserir = sa.text(
        "INSERT INTO vagas (id, programa_id, descricao, quantidade) VALUES (:id, 'p-1', :d, :q)"
    )

    with engine.connect() as conn:
        _inserir_programa(conn)
        conn.execute(inserir, {"id": "v-1", "d": "Manhã", "q": 20})
        with pytest.raises(IntegrityError) as repetida:
            conn.execute(inserir, {"id": "v-2", "d": "manhã", "q": 10})
        conn.rollback()

        _inserir_programa(conn)
        with pytest.raises(IntegrityError) as zerada:
            conn.execute(inserir, {"id": "v-3", "d": "Tarde", "q": 0})
        conn.rollback()

    assert repetida.value.orig.sqlstate == UNIQUE_VIOLATION
    assert zerada.value.orig.sqlstate == CHECK_VIOLATION


def test_downgrade_remove_so_o_que_a_migration_criou_e_upgrade_recria(migrated_db):
    engine, config = migrated_db

    command.downgrade(config, REV_VINCULOS_EQUIPE)
    inspetor = sa.inspect(engine)
    assert not TABELAS & set(inspetor.get_table_names())
    assert not COLUNAS_NOVAS_PROGRAMA & {c["name"] for c in inspetor.get_columns("projetos")}
    assert {"projetos", "espacos", "vinculos_equipe"} <= set(inspetor.get_table_names())

    command.upgrade(config, "head")
    assert TABELAS <= set(sa.inspect(engine).get_table_names())
