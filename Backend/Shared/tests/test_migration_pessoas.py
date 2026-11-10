"""T-47 · US-03: people served, guardians, family units, documents and authorizations.

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

# Revision right before this migration (T-45); a relative "-1" would break once
# newer migrations are added.
REV_PLANO_DE_ACAO = "5c2e8d41a7b3"
TABELAS = {
    "nucleos_familiares",
    "pessoas",
    "responsaveis",
    "pessoas_responsaveis",
    "documentos_pessoa",
    "autorizacoes",
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


def _executar(conn, sql, **params):
    return conn.execute(sa.text(sql), params)


def _base(conn) -> None:
    """Programa, usuário, núcleo e uma pessoa com dois responsáveis (um legal)."""
    _executar(conn, "INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear')")
    _executar(conn, "INSERT INTO usuarios (id, nome) VALUES ('ana', 'Ana Martins')")
    _executar(conn, "INSERT INTO nucleos_familiares (id, nome) VALUES ('f-1', 'Oliveira')")
    _executar(
        conn,
        """
        INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id, criado_por)
        VALUES ('pe-1', 'Lara Oliveira', 'lara oliveira', '2013-05-12', 'f-1', 'p-1', 'ana')
        """,
    )
    _executar(
        conn,
        """
        INSERT INTO responsaveis (id, nome, nome_normalizado) VALUES
            ('r-1', 'Marina Oliveira', 'marina oliveira'),
            ('r-2', 'Antônio Oliveira', 'antonio oliveira')
        """,
    )
    _executar(
        conn,
        """
        INSERT INTO pessoas_responsaveis (pessoa_id, responsavel_id, parentesco, responsavel_legal) VALUES
            ('pe-1', 'r-1', 'Mãe', true),
            ('pe-1', 'r-2', 'Avô', false)
        """,
    )


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


# --- Estrutura -----------------------------------------------------------------


def test_migration_cria_tabelas_com_colunas_esperadas(migrated_db):
    engine, _ = migrated_db
    inspetor = sa.inspect(engine)
    colunas = lambda tabela: {c["name"] for c in inspetor.get_columns(tabela)}  # noqa: E731

    assert TABELAS <= set(inspetor.get_table_names())
    assert colunas("pessoas") == {
        "id", "nome", "nome_normalizado", "data_nascimento", "nucleo_familiar_id",
        "programa_id", "telefone", "observacao", "situacao", "criado_por", "criado_em",
    }
    assert colunas("pessoas_responsaveis") == {
        "pessoa_id", "responsavel_id", "parentesco", "responsavel_legal", "criado_em",
    }
    assert colunas("autorizacoes") == {
        "id", "pessoa_id", "tipo", "valida_de", "valida_ate", "documento_id",
        "revogada_em", "revogada_por", "criado_por", "criado_em",
    }
    assert colunas("documentos_pessoa") == {
        "id", "pessoa_id", "tipo", "nome_arquivo", "tamanho", "chave_arquivo", "criado_por", "criado_em",
    }


def test_indices_para_busca_de_duplicidade(migrated_db):
    engine, _ = migrated_db
    inspetor = sa.inspect(engine)
    indices = lambda tabela: {i["name"]: i["column_names"] for i in inspetor.get_indexes(tabela)}  # noqa: E731

    assert indices("pessoas")["ix_pessoas_nome_nascimento"] == ["nome_normalizado", "data_nascimento"]
    assert indices("responsaveis")["ix_responsaveis_nome"] == ["nome_normalizado"]
    assert indices("pessoas_responsaveis")["ix_pessoas_responsaveis_responsavel_id"] == ["responsavel_id"]


# --- Pessoa, família e responsáveis --------------------------------------------


def test_pessoa_ligada_a_nucleo_familiar_e_a_varios_responsaveis(com_base):
    with com_base.connect() as conn:
        familia = _executar(conn, "SELECT nucleo_familiar_id, situacao FROM pessoas WHERE id = 'pe-1'").one()
        responsaveis = _executar(
            conn,
            "SELECT responsavel_id, responsavel_legal FROM pessoas_responsaveis "
            "WHERE pessoa_id = 'pe-1' ORDER BY responsavel_id",
        ).all()

    assert tuple(familia) == ("f-1", "ativo")
    assert [tuple(r) for r in responsaveis] == [("r-1", True), ("r-2", False)]


def test_responsavel_pode_responder_por_irmaos(com_base):
    with com_base.begin() as conn:
        _executar(
            conn,
            "INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id) "
            "VALUES ('pe-2', 'Davi Oliveira', 'davi oliveira', '2016-02-01', 'f-1', 'p-1')",
        )
        _executar(
            conn,
            "INSERT INTO pessoas_responsaveis (pessoa_id, responsavel_id, responsavel_legal) VALUES ('pe-2', 'r-1', true)",
        )
        total = _executar(conn, "SELECT count(*) FROM pessoas_responsaveis WHERE responsavel_id = 'r-1'").scalar()

    assert total == 2


def test_mesmo_responsavel_nao_se_repete_para_a_mesma_pessoa(com_base):
    sql = "INSERT INTO pessoas_responsaveis (pessoa_id, responsavel_id) VALUES ('pe-1', 'r-1')"
    assert _violacao(com_base, sql) == UNIQUE_VIOLATION


@pytest.mark.parametrize(
    "campo, valor",
    [("nucleo_familiar_id", "f-x"), ("programa_id", "p-x"), ("criado_por", "ninguem")],
)
def test_fk_impede_pessoa_com_referencia_inexistente(com_base, campo, valor):
    valores = {"nucleo_familiar_id": "f-1", "programa_id": "p-1", "criado_por": "ana", campo: valor}
    sql = (
        "INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id, criado_por) "
        "VALUES ('pe-9', 'X', 'x', '2010-01-01', :nucleo_familiar_id, :programa_id, :criado_por)"
    )
    assert _violacao(com_base, sql, **valores) == FOREIGN_KEY_VIOLATION


def test_pessoa_exige_nucleo_familiar(com_base):
    sql = (
        "INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, programa_id) "
        "VALUES ('pe-9', 'X', 'x', '2010-01-01', 'p-1')"
    )
    with com_base.connect() as conn:
        with pytest.raises(IntegrityError) as erro:
            _executar(conn, sql)
        conn.rollback()
    assert erro.value.orig.sqlstate == "23502"  # not_null_violation


@pytest.mark.parametrize(
    "nome, situacao",
    [("   ", "ativo"), ("Ana", "arquivado")],
    ids=["nome-em-branco", "situacao-invalida"],
)
def test_check_da_pessoa(com_base, nome, situacao):
    sql = (
        "INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id, situacao) "
        "VALUES ('pe-9', :nome, 'x', '2010-01-01', 'f-1', 'p-1', :situacao)"
    )
    assert _violacao(com_base, sql, nome=nome, situacao=situacao) == CHECK_VIOLATION


# --- Documentos e autorizações -------------------------------------------------


def test_autorizacao_guarda_tipo_validade_e_revogacao(com_base):
    with com_base.begin() as conn:
        _executar(
            conn,
            "INSERT INTO documentos_pessoa (id, pessoa_id, tipo, nome_arquivo, tamanho) "
            "VALUES ('d-1', 'pe-1', 'autorizacao_imagem', 'termo.pdf', 1024)",
        )
        _executar(
            conn,
            "INSERT INTO autorizacoes (id, pessoa_id, tipo, valida_de, valida_ate, documento_id) "
            "VALUES ('a-1', 'pe-1', 'uso_de_imagem', '2026-01-01', '2026-12-31', 'd-1')",
        )
        _executar(conn, "UPDATE autorizacoes SET revogada_em = now(), revogada_por = 'ana' WHERE id = 'a-1'")
        linha = _executar(conn, "SELECT tipo, valida_ate, revogada_por, documento_id FROM autorizacoes").one()

    assert (linha.tipo, str(linha.valida_ate), linha.revogada_por, linha.documento_id) == (
        "uso_de_imagem", "2026-12-31", "ana", "d-1",
    )


@pytest.mark.parametrize(
    "tipo, de, ate, revogada_em, revogada_por",
    [
        ("outro", "2026-01-01", "2026-12-31", None, None),
        ("uso_de_imagem", "2026-12-31", "2026-01-01", None, None),
        ("uso_de_imagem", "2026-01-01", "2026-12-31", None, "ana"),
    ],
    ids=["tipo-invalido", "validade-invertida", "revogada-por-sem-data"],
)
def test_check_da_autorizacao(com_base, tipo, de, ate, revogada_em, revogada_por):
    sql = (
        "INSERT INTO autorizacoes (id, pessoa_id, tipo, valida_de, valida_ate, revogada_em, revogada_por) "
        "VALUES ('a-9', 'pe-1', :tipo, :de, :ate, :revogada_em, :revogada_por)"
    )
    assert _violacao(
        com_base, sql, tipo=tipo, de=de, ate=ate, revogada_em=revogada_em, revogada_por=revogada_por
    ) == CHECK_VIOLATION


def test_apagar_pessoa_leva_documentos_autorizacoes_e_vinculos_com_responsaveis(com_base):
    with com_base.begin() as conn:
        _executar(
            conn,
            "INSERT INTO documentos_pessoa (id, pessoa_id, tipo, nome_arquivo) VALUES ('d-1', 'pe-1', 'rg', 'rg.pdf')",
        )
        _executar(
            conn,
            "INSERT INTO autorizacoes (id, pessoa_id, tipo, valida_de, valida_ate, documento_id) "
            "VALUES ('a-1', 'pe-1', 'uso_de_imagem', '2026-01-01', '2026-12-31', 'd-1')",
        )
        _executar(conn, "DELETE FROM pessoas WHERE id = 'pe-1'")
        restantes = {
            t: _executar(conn, f"SELECT count(*) FROM {t}").scalar()
            for t in ("documentos_pessoa", "autorizacoes", "pessoas_responsaveis", "responsaveis")
        }

    # Os responsáveis continuam: podem responder por outras pessoas.
    assert restantes == {"documentos_pessoa": 0, "autorizacoes": 0, "pessoas_responsaveis": 0, "responsaveis": 2}


# --- Reversibilidade -----------------------------------------------------------


def test_downgrade_remove_so_as_tabelas_novas_e_upgrade_recria(migrated_db):
    engine, config = migrated_db

    command.downgrade(config, REV_PLANO_DE_ACAO)
    tabelas = set(sa.inspect(engine).get_table_names())
    assert not TABELAS & tabelas
    assert {"projetos", "usuarios", "vinculos_equipe"} <= tabelas

    command.upgrade(config, "head")
    assert TABELAS <= set(sa.inspect(engine).get_table_names())
