"""T-32 · US-08: usuarios, papeis, usuarios_papeis and log_auditoria migration,
run against a real Postgres.

Like test_migrations.py, these tests downgrade the target database to an empty
schema, so they only run when TEST_DATABASE_URL points at a disposable database.
The helpers are repeated here so this file does not depend on that one.
"""

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

SHARED_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"
RAISE_EXCEPTION = "P0001"

# Revision right before this migration; a relative "-1" would break once newer
# migrations are added.
REV_STATUS_PROJETOS = "a3c5e7f9b1d2"
TABELAS = {"usuarios", "papeis", "usuarios_papeis", "log_auditoria"}

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


def _inserir_usuario(conn, usuario_id="ana-martins", nome="Ana Martins", email=None):
    conn.execute(
        sa.text("INSERT INTO usuarios (id, nome, email) VALUES (:id, :nome, :email)"),
        {"id": usuario_id, "nome": nome, "email": email},
    )


def _inserir_log(conn, **campos):
    valores = {"usuario_id": "ana-martins", "modulo": "gestao", "acao": "consultou_pessoa"}
    valores.update(campos)
    conn.execute(
        sa.text(
            "INSERT INTO log_auditoria (usuario_id, modulo, acao) "
            "VALUES (:usuario_id, :modulo, :acao)"
        ),
        valores,
    )


def test_migration_cria_as_quatro_tabelas_com_colunas_esperadas(migrated_db):
    engine, _ = migrated_db
    inspetor = sa.inspect(engine)

    assert TABELAS <= set(inspetor.get_table_names())
    colunas = {
        tabela: {c["name"] for c in inspetor.get_columns(tabela)} for tabela in TABELAS
    }
    assert colunas["usuarios"] == {"id", "nome", "email", "ativo", "criado_em", "senha_hash"}
    assert colunas["papeis"] == {"id", "nome"}
    assert colunas["usuarios_papeis"] == {"usuario_id", "papel_id", "atribuido_em"}
    assert colunas["log_auditoria"] == {
        "id",
        "ocorrido_em",
        "usuario_id",
        "modulo",
        "acao",
        "alvo_tipo",
        "alvo_id",
        "descricao",
        "detalhes",
    }


def test_papeis_dos_dois_modulos_ja_vem_cadastrados(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        papeis = set(conn.execute(sa.text("SELECT id FROM papeis")).scalars())

    # The first four are the roles the Financeiro API already accepts.
    assert papeis == {
        "coordenacao",
        "direcao",
        "educador",
        "voluntario_financeiro",
        "assistente_social",
        "psicologo",
        "administracao",
    }


def test_usuario_novo_comeca_ativo(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_usuario(conn)
        ativo, criado_em = conn.execute(
            sa.text("SELECT ativo, criado_em FROM usuarios WHERE id = 'ana-martins'")
        ).one()
        conn.rollback()

    assert ativo is True
    assert criado_em is not None


@pytest.mark.parametrize("nome", ["", "   "])
def test_check_impede_usuario_sem_nome(migrated_db, nome):
    engine, _ = migrated_db

    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as erro:
            _inserir_usuario(conn, nome=nome)
        conn.rollback()

    assert erro.value.orig.sqlstate == CHECK_VIOLATION


def test_email_repetido_e_barrado_sem_diferenciar_maiusculas(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_usuario(conn, "ana-martins", "Ana Martins", "ana@exemplo.test")
        _inserir_usuario(conn, "rafael-nunes", "Rafael Nunes", None)
        _inserir_usuario(conn, "jessica-almeida", "Jéssica Almeida", None)
        with pytest.raises(IntegrityError) as erro:
            _inserir_usuario(conn, "ana-2", "Ana M.", "ANA@exemplo.test")
        conn.rollback()

    assert erro.value.orig.sqlstate == UNIQUE_VIOLATION


def test_usuario_pode_ter_mais_de_um_papel(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_usuario(conn)
        conn.execute(
            sa.text(
                "INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES "
                "('ana-martins', 'coordenacao'), ('ana-martins', 'voluntario_financeiro')"
            )
        )
        papeis = set(
            conn.execute(
                sa.text("SELECT papel_id FROM usuarios_papeis WHERE usuario_id = 'ana-martins'")
            ).scalars()
        )
        conn.rollback()

    assert papeis == {"coordenacao", "voluntario_financeiro"}


def test_mesmo_papel_repetido_para_o_usuario_e_barrado(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_usuario(conn)
        inserir = sa.text(
            "INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('ana-martins', 'coordenacao')"
        )
        conn.execute(inserir)
        with pytest.raises(IntegrityError) as erro:
            conn.execute(inserir)
        conn.rollback()

    assert erro.value.orig.sqlstate == UNIQUE_VIOLATION


@pytest.mark.parametrize(
    "usuario_id, papel_id",
    [("ana-martins", "papel-inexistente"), ("usuario-inexistente", "coordenacao")],
)
def test_fk_impede_papel_ou_usuario_inexistente(migrated_db, usuario_id, papel_id):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_usuario(conn)
        with pytest.raises(IntegrityError) as erro:
            conn.execute(
                sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES (:u, :p)"),
                {"u": usuario_id, "p": papel_id},
            )
        conn.rollback()

    assert erro.value.orig.sqlstate == FOREIGN_KEY_VIOLATION


@pytest.mark.parametrize(
    "apagar",
    ["DELETE FROM papeis WHERE id = 'coordenacao'", "DELETE FROM usuarios WHERE id = 'ana-martins'"],
)
def test_papel_ou_usuario_em_uso_nao_pode_ser_apagado(migrated_db, apagar):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_usuario(conn)
        conn.execute(
            sa.text(
                "INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('ana-martins', 'coordenacao')"
            )
        )
        with pytest.raises(IntegrityError) as erro:
            conn.execute(sa.text(apagar))
        conn.rollback()

    assert erro.value.orig.sqlstate == FOREIGN_KEY_VIOLATION


def test_log_registra_evento_com_data_e_id_automaticos(migrated_db):
    engine, _ = migrated_db

    with engine.connect() as conn:
        _inserir_log(conn)
        # usuario_id may be unknown or missing: denied attempts are logged too.
        _inserir_log(conn, usuario_id=None, acao="acesso_negado")
        linhas = conn.execute(
            sa.text("SELECT id, ocorrido_em, usuario_id, acao FROM log_auditoria ORDER BY id")
        ).all()
        conn.rollback()

    assert [(linha.usuario_id, linha.acao) for linha in linhas] == [
        ("ana-martins", "consultou_pessoa"),
        (None, "acesso_negado"),
    ]
    assert all(linha.id is not None and linha.ocorrido_em is not None for linha in linhas)


@pytest.mark.parametrize("campos", [{"modulo": "rh"}, {"acao": " "}])
def test_check_impede_log_com_modulo_invalido_ou_sem_acao(migrated_db, campos):
    engine, _ = migrated_db

    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as erro:
            _inserir_log(conn, **campos)
        conn.rollback()

    assert erro.value.orig.sqlstate == CHECK_VIOLATION


@pytest.mark.parametrize(
    "comando",
    ["UPDATE log_auditoria SET acao = 'outra'", "DELETE FROM log_auditoria"],
)
def test_log_nao_aceita_alteracao_nem_exclusao(migrated_db, comando):
    engine, _ = migrated_db

    with engine.begin() as conn:
        _inserir_log(conn)

    with engine.connect() as conn:
        with pytest.raises(DBAPIError) as erro:
            conn.execute(sa.text(comando))
        conn.rollback()
        restantes = conn.execute(sa.text("SELECT acao FROM log_auditoria")).scalars().all()

    assert erro.value.orig.sqlstate == RAISE_EXCEPTION
    assert "apenas inclusões" in str(erro.value.orig)
    assert restantes == ["consultou_pessoa"]


def test_downgrade_remove_so_as_tabelas_novas_e_upgrade_recria(migrated_db):
    engine, config = migrated_db

    command.downgrade(config, REV_STATUS_PROJETOS)
    tabelas = set(sa.inspect(engine).get_table_names())
    assert not TABELAS & tabelas
    assert {"projetos", "orcamentos", "lancamentos"} <= tabelas
    # The previous migration (status on projetos, #82) stays applied.
    assert "status" in {c["name"] for c in sa.inspect(engine).get_columns("projetos")}
    with engine.connect() as conn:
        funcao = conn.execute(
            sa.text("SELECT 1 FROM pg_proc WHERE proname = 'log_auditoria_somente_inclusao'")
        ).first()
    assert funcao is None

    command.upgrade(config, "head")
    assert TABELAS <= set(sa.inspect(engine).get_table_names())
