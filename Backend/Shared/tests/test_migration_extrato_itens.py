"""Extrato bancário (e4b8c1d7f2a9): tabela extrato_itens e suas regras.

O teste de ordem não precisa de banco. Os demais descem o banco de teste até o esquema
vazio, como os outros testes de migration, então só rodam com TEST_DATABASE_URL
apontando para um banco descartável.
"""

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

SHARED_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

REVISAO = "e4b8c1d7f2a9"
# Junção do login com a persistência do Financeiro (a produção estava nela em 11/11).
ANTERIOR = "d9f1a7c3b5e2"
FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"
NOT_NULL_VIOLATION = "23502"

precisa_de_banco = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; migration tests need a disposable Postgres",
)


def _alembic_config() -> Config:
    config = Config(str(SHARED_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SHARED_DIR / "migrations"))
    if TEST_DATABASE_URL:
        config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    return config


def test_extrato_vem_depois_da_juncao():
    revisao = ScriptDirectory.from_config(_alembic_config()).get_revision(REVISAO)

    assert revisao.down_revision == ANTERIOR


def _url_sqlalchemy(url: str) -> str:
    parsed = make_url(url)
    if parsed.drivername in ("postgresql", "postgres"):
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed.render_as_string(hide_password=False)


def _garantir_banco_descartavel(url: str) -> None:
    nome = make_url(url).database or ""
    if "test" not in nome:
        pytest.fail(f"TEST_DATABASE_URL must point at a test database, got {nome!r}")
    if url == os.environ.get("DATABASE_URL"):
        pytest.fail("TEST_DATABASE_URL must differ from DATABASE_URL")


@pytest.fixture
def banco_antes():
    """Banco na revisão anterior, com dois lançamentos já gravados."""
    _garantir_banco_descartavel(TEST_DATABASE_URL)
    config = _alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, ANTERIOR)
    engine = sa.create_engine(_url_sqlalchemy(TEST_DATABASE_URL))
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear')"))
        conn.execute(
            sa.text(
                "INSERT INTO orcamentos (id, projeto_id, valor_total, periodo_inicio, periodo_fim, categorias) "
                "VALUES ('o-1', 'p-1', 1000, '2026-01-01', '2026-12-31', '{materiais}')"
            )
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO lancamentos (id, projeto_id, orcamento_id, categoria, valor, data, descricao, status)
                VALUES ('l-1', 'p-1', 'o-1', 'materiais', 50, '2026-05-01', 'Tinta', 'aprovado'),
                       ('l-2', 'p-1', 'o-1', 'materiais', 20, '2026-05-02', 'Papel', 'aprovado')
                """
            )
        )
    try:
        yield engine, config
    finally:
        engine.dispose()
        command.downgrade(config, "base")


@pytest.fixture
def migrado(banco_antes):
    engine, config = banco_antes
    command.upgrade(config, REVISAO)
    return engine


def _inserir(conn, item_id, conciliado_com=None, valor="10.00"):
    conn.execute(
        sa.text(
            "INSERT INTO extrato_itens (id, data, descricao, valor, conciliado_com) "
            "VALUES (:id, '2026-05-01', 'PIX', :valor, :lancamento)"
        ),
        {"id": item_id, "valor": valor, "lancamento": conciliado_com},
    )


def _violacao(engine, sql, **params) -> str:
    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as erro:
            conn.execute(sa.text(sql), params)
        conn.rollback()
    return erro.value.orig.sqlstate


@precisa_de_banco
def test_colunas_e_valores_padrao(migrado):
    colunas = {c["name"]: c for c in sa.inspect(migrado).get_columns("extrato_itens")}

    assert {"id", "data", "descricao", "valor", "importado_em", "conciliado_com", "ordem"} == set(colunas)
    assert colunas["conciliado_com"]["nullable"] is True
    for coluna in ("data", "descricao", "valor", "importado_em"):
        assert colunas[coluna]["nullable"] is False
    assert (colunas["valor"]["type"].precision, colunas["valor"]["type"].scale) == (14, 2)

    with migrado.begin() as conn:
        _inserir(conn, "i-1", valor="-250.505")
        _inserir(conn, "i-2")
        linhas = conn.execute(
            sa.text("SELECT id, valor, importado_em, ordem FROM extrato_itens ORDER BY ordem")
        ).all()
    assert [l.id for l in linhas] == ["i-1", "i-2"]
    assert str(linhas[0].valor) == "-250.51"
    assert all(l.importado_em is not None for l in linhas)
    assert linhas[0].ordem < linhas[1].ordem


@precisa_de_banco
def test_conciliado_com_precisa_ser_um_lancamento(migrado):
    sem_lancamento = (
        "INSERT INTO extrato_itens (id, data, descricao, valor, conciliado_com) "
        "VALUES ('i-1', '2026-05-01', 'PIX', 1, 'nao-existe')"
    )
    assert _violacao(migrado, sem_lancamento) == FOREIGN_KEY_VIOLATION
    sem_valor = "INSERT INTO extrato_itens (id, data, descricao) VALUES ('i-2', '2026-05-01', 'PIX')"
    assert _violacao(migrado, sem_valor) == NOT_NULL_VIOLATION


@precisa_de_banco
def test_um_lancamento_liga_no_maximo_um_item(migrado):
    with migrado.begin() as conn:
        _inserir(conn, "i-1", "l-1")
        # Vários itens em aberto (sem lançamento) podem existir.
        _inserir(conn, "i-2")
        _inserir(conn, "i-3")
        _inserir(conn, "i-4", "l-2")

    repetido = (
        "INSERT INTO extrato_itens (id, data, descricao, valor, conciliado_com) "
        "VALUES ('i-5', '2026-05-01', 'PIX', 1, 'l-1')"
    )
    assert _violacao(migrado, repetido) == UNIQUE_VIOLATION


@precisa_de_banco
def test_apagar_o_lancamento_solta_o_item(migrado):
    with migrado.begin() as conn:
        _inserir(conn, "i-1", "l-1")
        conn.execute(sa.text("DELETE FROM lancamentos WHERE id = 'l-1'"))
        assert conn.execute(sa.text("SELECT conciliado_com FROM extrato_itens")).scalar_one() is None


@precisa_de_banco
def test_indices(migrado):
    indices = {i["name"]: i for i in sa.inspect(migrado).get_indexes("extrato_itens")}

    assert indices["ix_extrato_itens_data"]["column_names"] == ["data"]
    assert indices["uq_extrato_itens_conciliado_com"]["unique"]


@precisa_de_banco
def test_downgrade_desfaz_so_a_tabela_do_extrato(migrado, banco_antes):
    _, config = banco_antes
    command.downgrade(config, ANTERIOR)
    inspetor = sa.inspect(migrado)

    assert "extrato_itens" not in inspetor.get_table_names()
    assert {"lancamentos", "notificacoes", "log_auditoria"} <= set(inspetor.get_table_names())
    with migrado.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM lancamentos")).scalar_one() == 2


@precisa_de_banco
def test_upgrade_downgrade_upgrade(migrado, banco_antes):
    _, config = banco_antes
    command.downgrade(config, ANTERIOR)
    command.upgrade(config, REVISAO)

    assert "extrato_itens" in sa.inspect(migrado).get_table_names()
