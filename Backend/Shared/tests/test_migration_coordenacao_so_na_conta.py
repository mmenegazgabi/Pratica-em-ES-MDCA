"""T-87: a coordenação passa a ser só papel da conta (migration e4a6c8b0d2f1).

Como os outros testes de migration, desce o banco de teste até o esquema vazio; por isso
só roda com ``TEST_DATABASE_URL`` apontando para um banco descartável. Os auxiliares são
repetidos aqui para este arquivo não depender dos outros.
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

CHECK_VIOLATION = "23514"
REV_ANTERIOR = "d9f1a7c3b5e2"
REV_COORDENACAO = "e4a6c8b0d2f1"

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL não definido; os testes de migration precisam de um PostgreSQL descartável",
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
        pytest.fail(f"TEST_DATABASE_URL deve apontar para um banco de teste, veio {nome!r}")
    if url == os.environ.get("DATABASE_URL"):
        pytest.fail("TEST_DATABASE_URL deve ser diferente de DATABASE_URL")


@pytest.fixture
def banco_antes():
    """Banco na revisão anterior, com o caso da produção: Ana coordena o Semear por vínculo."""
    _garantir_banco_descartavel(TEST_DATABASE_URL)
    config = _alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, REV_ANTERIOR)

    engine = sa.create_engine(_sqlalchemy_url(TEST_DATABASE_URL))
    with engine.begin() as c:
        c.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear'), ('p-2', 'Oficina')"))
        c.execute(
            sa.text(
                "INSERT INTO usuarios (id, nome) VALUES "
                "('ana', 'Ana Martins'), ('jessica', 'Jéssica Almeida'), ('admin', 'Administração')"
            )
        )
        # admin já tem coordenação na conta e também um vínculo antigo de coordenação.
        c.execute(sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('admin', 'coordenacao')"))
        c.execute(
            sa.text(
                "INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada, data_saida) VALUES "
                "('v-ana', 'ana', 'p-1', 'coordenacao', '2026-11-09', NULL), "
                "('v-jessica', 'jessica', 'p-1', 'educador', '2026-01-01', NULL), "
                "('v-admin', 'admin', 'p-2', 'coordenacao', '2025-01-01', '2025-12-31')"
            )
        )
    try:
        yield engine, config
    finally:
        engine.dispose()
        command.downgrade(config, "base")


def test_vinculo_de_coordenacao_vira_papel_da_conta(banco_antes):
    engine, config = banco_antes

    command.upgrade(config, REV_COORDENACAO)

    with engine.connect() as c:
        papeis = set(c.execute(sa.text("SELECT usuario_id, papel_id FROM usuarios_papeis")).all())
        vinculos = c.execute(sa.text("SELECT id FROM vinculos_equipe ORDER BY id")).scalars().all()
    assert papeis == {("ana", "coordenacao"), ("admin", "coordenacao")}
    # Os outros vínculos ficam como estavam.
    assert vinculos == ["v-jessica"]


def test_cada_vinculo_convertido_fica_na_auditoria(banco_antes):
    engine, config = banco_antes

    command.upgrade(config, REV_COORDENACAO)

    with engine.connect() as c:
        linhas = c.execute(
            sa.text(
                "SELECT usuario_id, modulo, acao, alvo_tipo, alvo_id, detalhes FROM log_auditoria "
                "WHERE acao = 'converter_coordenacao' ORDER BY alvo_id"
            )
        ).all()
    assert [tuple(linha[:5]) for linha in linhas] == [
        ("admin", "gestao", "converter_coordenacao", "vinculo", "v-admin"),
        ("ana", "gestao", "converter_coordenacao", "vinculo", "v-ana"),
    ]
    assert linhas[1].detalhes == {"programa_id": "p-1", "data_entrada": "2026-11-09", "data_saida": None}


def test_depois_da_migration_o_banco_recusa_vinculo_de_coordenacao(banco_antes):
    engine, config = banco_antes
    command.upgrade(config, REV_COORDENACAO)

    with pytest.raises(IntegrityError) as erro:
        with engine.begin() as c:
            c.execute(
                sa.text(
                    "INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) "
                    "VALUES ('v-nova', 'jessica', 'p-2', 'coordenacao', '2026-11-11')"
                )
            )
    assert erro.value.orig.sqlstate == CHECK_VIOLATION


def test_downgrade_tira_so_o_check(banco_antes):
    engine, config = banco_antes
    command.upgrade(config, REV_COORDENACAO)

    command.downgrade(config, REV_ANTERIOR)

    with engine.begin() as c:
        c.execute(
            sa.text(
                "INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) "
                "VALUES ('v-nova', 'jessica', 'p-2', 'coordenacao', '2026-11-11')"
            )
        )
        # O papel dado na conta continua.
        assert c.execute(
            sa.text("SELECT count(*) FROM usuarios_papeis WHERE usuario_id = 'ana' AND papel_id = 'coordenacao'")
        ).scalar_one() == 1
