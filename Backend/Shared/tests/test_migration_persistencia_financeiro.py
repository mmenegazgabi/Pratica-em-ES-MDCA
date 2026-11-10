"""Persistência do Financeiro (c2d8e4f6a1b3): campos novos em lancamentos, tabelas
notificacoes e rascunhos_lancamento, e a ordem das migrations.

Os testes de ordem (um único head, histórico em linha) não precisam de banco e rodam em
qualquer job: duas migrations partindo da mesma anterior quebram o deploy, como já
aconteceu na T-32. Os demais, como os outros testes de migration, descem o banco de teste
até o esquema vazio, então só rodam com TEST_DATABASE_URL apontando para um banco
descartável.
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

REVISAO = "c2d8e4f6a1b3"
# Revisão logo antes desta (T-59, alertas da Gestão).
ANTERIOR = "6bd565cae094"
FOREIGN_KEY_VIOLATION = "23503"
CHECK_VIOLATION = "23514"
NOT_NULL_VIOLATION = "23502"

COLUNAS_NOVAS = {
    "criado_em",
    "aprovado_em",
    "rejeitado_em",
    "conciliado_em",
    "motivos_rejeicao_anteriores",
    "comprovante_chave",
}

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


# --- Ordem das migrations (sem banco) -------------------------------------------------


def test_migrations_tem_um_unico_head():
    heads = ScriptDirectory.from_config(_alembic_config()).get_heads()

    assert len(heads) == 1, f"mais de um head: {heads} — combine a ordem das migrations antes do merge"


def test_historico_das_migrations_e_uma_linha_so():
    script = ScriptDirectory.from_config(_alembic_config())
    revisoes = list(script.walk_revisions())

    # Nenhuma migration é base de duas outras (sem ramificação) e nenhuma junta ramos.
    assert all(not isinstance(r.down_revision, tuple) for r in revisoes)
    filhos = [r.down_revision for r in revisoes if r.down_revision]
    assert len(filhos) == len(set(filhos))
    assert [r.revision for r in revisoes if r.down_revision is None] == ["4113860459ea"]


def test_persistencia_do_financeiro_vem_depois_dos_alertas():
    revisao = ScriptDirectory.from_config(_alembic_config()).get_revision(REVISAO)

    assert revisao.down_revision == ANTERIOR


# --- Esquema (com banco) ---------------------------------------------------------------


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
    """Banco na revisão anterior, com um orçamento e um lançamento já gravados."""
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
                INSERT INTO lancamentos (id, projeto_id, orcamento_id, categoria, valor, data, descricao,
                                         status, comprovante_url, autor_id)
                VALUES ('l-1', 'p-1', 'o-1', 'materiais', 50, '2026-05-01', 'Tinta', 'aprovado',
                        '/comprovantes/2026/05/abc.jpg', 'marcos'),
                       ('l-2', 'p-1', 'o-1', 'materiais', 20, '2026-05-02', 'Papel', 'pendente',
                        NULL, 'ana')
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


def _violacao(engine, sql, **params) -> str:
    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as erro:
            conn.execute(sa.text(sql), params)
        conn.rollback()
    return erro.value.orig.sqlstate


@precisa_de_banco
def test_lancamentos_ganham_os_campos_novos(migrado):
    colunas = {c["name"]: c for c in sa.inspect(migrado).get_columns("lancamentos")}

    assert COLUNAS_NOVAS <= set(colunas)
    assert colunas["criado_em"]["nullable"] is False
    assert colunas["motivos_rejeicao_anteriores"]["nullable"] is False
    for coluna in ("aprovado_em", "rejeitado_em", "conciliado_em", "comprovante_chave"):
        assert colunas[coluna]["nullable"] is True


@precisa_de_banco
def test_lancamentos_existentes_sao_preenchidos_sem_perder_dados(migrado):
    with migrado.connect() as conn:
        linhas = {
            l.id: l
            for l in conn.execute(
                sa.text(
                    "SELECT id, valor, status, criado_em, motivos_rejeicao_anteriores, comprovante_url, "
                    "comprovante_chave, aprovado_em FROM lancamentos"
                )
            )
        }

    assert set(linhas) == {"l-1", "l-2"}
    assert (float(linhas["l-1"].valor), linhas["l-1"].status) == (50.0, "aprovado")
    assert all(l.criado_em is not None and l.motivos_rejeicao_anteriores == [] for l in linhas.values())
    # A chave do R2 vem do caminho que já estava gravado; sem comprovante, fica nula.
    assert linhas["l-1"].comprovante_chave == "comprovantes/2026/05/abc.jpg"
    assert linhas["l-1"].comprovante_url == "/comprovantes/2026/05/abc.jpg"
    assert linhas["l-2"].comprovante_chave is None
    assert linhas["l-1"].aprovado_em is None


@precisa_de_banco
def test_tabela_de_notificacoes_e_suas_regras(migrado):
    with migrado.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO notificacoes (id, destinatario_id, lancamento_id, tipo, mensagem) "
                "VALUES ('n-1', 'marcos', 'l-1', 'lancamento_aprovado', 'Aprovado.')"
            )
        )
        lida, criada = conn.execute(sa.text("SELECT lida, criada_em FROM notificacoes")).one()
    assert lida is False and criada is not None

    tipo_invalido = (
        "INSERT INTO notificacoes (id, destinatario_id, lancamento_id, tipo, mensagem) "
        "VALUES ('n-2', 'marcos', 'l-1', 'outro', 'x')"
    )
    assert _violacao(migrado, tipo_invalido) == CHECK_VIOLATION
    sem_lancamento = (
        "INSERT INTO notificacoes (id, destinatario_id, lancamento_id, tipo, mensagem) "
        "VALUES ('n-3', 'marcos', 'nao-existe', 'lancamento_aprovado', 'x')"
    )
    assert _violacao(migrado, sem_lancamento) == FOREIGN_KEY_VIOLATION

    # Apagar o lançamento leva as notificações dele junto.
    with migrado.begin() as conn:
        conn.execute(sa.text("DELETE FROM lancamentos WHERE id = 'l-1'"))
        assert conn.execute(sa.text("SELECT count(*) FROM notificacoes")).scalar_one() == 0


@precisa_de_banco
def test_tabela_de_rascunhos_e_suas_regras(migrado):
    with migrado.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO rascunhos_lancamento (id, autor_id, comprovante_chave, nome_original, content_type, tamanho) "
                "VALUES ('r-1', 'marcos', 'comprovantes/2026/11/x.jpg', 'foto.jpg', 'image/jpeg', 10)"
            )
        )
    tamanho_zero = (
        "INSERT INTO rascunhos_lancamento (id, autor_id, comprovante_chave, nome_original, content_type, tamanho) "
        "VALUES ('r-2', 'marcos', 'k', 'f', 'image/jpeg', 0)"
    )
    assert _violacao(migrado, tamanho_zero) == CHECK_VIOLATION
    sem_autor = (
        "INSERT INTO rascunhos_lancamento (id, comprovante_chave, nome_original, content_type, tamanho) "
        "VALUES ('r-3', 'k', 'f', 'image/jpeg', 1)"
    )
    assert _violacao(migrado, sem_autor) == NOT_NULL_VIOLATION


@precisa_de_banco
def test_indices_de_busca_por_autor_e_destinatario(migrado):
    inspetor = sa.inspect(migrado)

    assert "ix_lancamentos_autor_id" in {i["name"] for i in inspetor.get_indexes("lancamentos")}
    assert "ix_notificacoes_destinatario_id" in {i["name"] for i in inspetor.get_indexes("notificacoes")}
    assert "ix_rascunhos_lancamento_autor_id" in {i["name"] for i in inspetor.get_indexes("rascunhos_lancamento")}


@precisa_de_banco
def test_downgrade_desfaz_so_o_que_esta_migration_criou(migrado, banco_antes):
    _, config = banco_antes
    command.downgrade(config, ANTERIOR)
    inspetor = sa.inspect(migrado)

    assert not {"notificacoes", "rascunhos_lancamento"} & set(inspetor.get_table_names())
    assert not COLUNAS_NOVAS & {c["name"] for c in inspetor.get_columns("lancamentos")}
    # Os lançamentos e as tabelas da Gestão continuam lá.
    assert {"alertas", "acoes_busca_ativa", "lancamentos"} <= set(inspetor.get_table_names())
    with migrado.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM lancamentos")).scalar_one() == 2


@precisa_de_banco
def test_upgrade_downgrade_upgrade_e_idempotente(migrado, banco_antes):
    _, config = banco_antes
    command.downgrade(config, ANTERIOR)
    command.upgrade(config, REVISAO)

    colunas = {c["name"] for c in sa.inspect(migrado).get_columns("lancamentos")}
    assert COLUNAS_NOVAS <= colunas
