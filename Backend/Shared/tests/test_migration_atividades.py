"""T-55 · US-05: atividades (encontros), chamadas e evidências.

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
NOT_NULL_VIOLATION = "23502"

# Revision right before this migration (T-51); a relative "-1" would break later.
REV_TURMAS = "193453ca12ea"
TABELAS = {"atividades", "chamadas", "evidencias"}

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
    """Programas p-1 e p-2, cada um com uma turma; a educadora ana e duas pessoas em p-1."""
    _executar(conn, "INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear'), ('p-2', 'Oficina')")
    _executar(conn, "INSERT INTO usuarios (id, nome) VALUES ('ana', 'Ana Martins'), ('jessica', 'Jéssica Almeida')")
    _executar(conn, "INSERT INTO espacos (id, programa_id, nome) VALUES ('e-1', 'p-1', 'Ateliê'), ('e-2', 'p-2', 'Sala')")
    _executar(conn, "INSERT INTO nucleos_familiares (id, nome) VALUES ('f-1', 'Oliveira')")
    _executar(
        conn,
        """
        INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id) VALUES
            ('pe-1', 'Lara Oliveira', 'lara oliveira', '2013-05-12', 'f-1', 'p-1'),
            ('pe-2', 'Davi Oliveira', 'davi oliveira', '2015-02-01', 'f-1', 'p-1')
        """,
    )
    _executar(
        conn,
        """
        INSERT INTO turmas (id, programa_id, nome, espaco_id, responsavel_id, capacidade, dias_semana, hora_inicio, hora_fim) VALUES
            ('t-1', 'p-1', 'Oficina de arte', 'e-1', 'ana', 20, '{1,3}', '14:00', '16:00'),
            ('t-2', 'p-2', 'Reforço', 'e-2', 'ana', 10, '{2}', '08:00', '10:00')
        """,
    )
    _executar(conn, ATIVIDADE, id="a-1", registro="dispositivo-1/a-1", programa="p-1", turma="t-1", conteudo="Pintura com guache")


ATIVIDADE = """
    INSERT INTO atividades (id, registro_id, programa_id, turma_id, data, educador_id, conteudo)
    VALUES (:id, :registro, :programa, :turma, '2026-11-09', 'ana', :conteudo)
"""

CHAMADA = """
    INSERT INTO chamadas (id, atividade_id, pessoa_id, presente, justificativa)
    VALUES (:id, 'a-1', :pessoa, :presente, :justificativa)
"""

EVIDENCIA = """
    INSERT INTO evidencias (id, registro_id, atividade_id, programa_id, autor_id, data,
                            chave_arquivo, nome_arquivo, content_type, tamanho)
    VALUES (:id, :registro, 'a-1', :programa, :autor, '2026-11-09',
            :chave, 'foto.jpg', 'image/jpeg', :tamanho)
"""


def _evidencia(**extra):
    dados = {
        "id": "ev-x",
        "registro": "dispositivo-1/ev-x",
        "programa": "p-1",
        "autor": "jessica",
        "chave": "gestao/evidencias/2026/11/ev-x.jpg",
        "tamanho": 1024,
    }
    return {**dados, **extra}


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


def test_migration_cria_as_tres_tabelas_com_os_campos_dos_criterios(migrated_db):
    engine, _ = migrated_db
    inspetor = sa.inspect(engine)

    assert TABELAS <= set(inspetor.get_table_names())
    # Chamada: data, turma, educador e conteúdo no encontro; presentes e ausentes nas linhas.
    assert {"registro_id", "programa_id", "turma_id", "data", "educador_id", "conteudo"} <= {
        c["name"] for c in inspetor.get_columns("atividades")
    }
    assert {"atividade_id", "pessoa_id", "presente", "justificativa"} <= {
        c["name"] for c in inspetor.get_columns("chamadas")
    }
    # Evidência: atividade, programa, autor e data; o arquivo fica no R2 (só a chave aqui).
    colunas = {c["name"] for c in inspetor.get_columns("evidencias")}
    assert {"registro_id", "atividade_id", "programa_id", "autor_id", "data"} <= colunas
    assert {"chave_arquivo", "nome_arquivo", "content_type", "tamanho"} <= colunas
    assert not {"arquivo", "conteudo", "dados"} & colunas


# --- Atividade (encontro) ------------------------------------------------------


@pytest.mark.parametrize(
    "campo, valor",
    [("programa", "nao-existe"), ("turma", "nao-existe")],
)
def test_atividade_referencia_programa_e_turma(com_base, campo, valor):
    dados = {"id": "a-x", "registro": "r-x", "programa": "p-1", "turma": "t-1", "conteudo": "X", campo: valor}

    assert _violacao(com_base, ATIVIDADE, **dados) == FOREIGN_KEY_VIOLATION


def test_atividade_nao_aceita_turma_de_outro_programa(com_base):
    estado = _violacao(com_base, ATIVIDADE, id="a-x", registro="r-x", programa="p-1", turma="t-2", conteudo="X")

    assert estado == FOREIGN_KEY_VIOLATION


def test_atividade_exige_educador_existente(com_base):
    sql = ATIVIDADE.replace("'ana'", "'ninguem'")

    assert _violacao(com_base, sql, id="a-x", registro="r-x", programa="p-1", turma="t-1", conteudo="X") == FOREIGN_KEY_VIOLATION


@pytest.mark.parametrize("conteudo", ["", "   "])
def test_atividade_exige_conteudo(com_base, conteudo):
    estado = _violacao(com_base, ATIVIDADE, id="a-x", registro="r-x", programa="p-1", turma="t-1", conteudo=conteudo)

    assert estado == CHECK_VIOLATION


def test_mesmo_registro_sincronizado_de_novo_nao_duplica_a_atividade(com_base):
    estado = _violacao(
        com_base, ATIVIDADE, id="a-outra", registro="dispositivo-1/a-1", programa="p-1", turma="t-1", conteudo="Pintura com guache"
    )

    assert estado == UNIQUE_VIOLATION


def test_dois_encontros_da_mesma_turma_no_mesmo_dia_sao_permitidos(com_base):
    with com_base.begin() as conn:
        _executar(conn, ATIVIDADE, id="a-2", registro="dispositivo-1/a-2", programa="p-1", turma="t-1", conteudo="Segundo turno")

    with com_base.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM atividades WHERE turma_id = 't-1'")).scalar_one() == 2


# --- Chamada -------------------------------------------------------------------


def test_chamada_registra_presentes_e_ausentes(com_base):
    with com_base.begin() as conn:
        _executar(conn, CHAMADA, id="c-1", pessoa="pe-1", presente=True, justificativa=None)
        _executar(conn, CHAMADA, id="c-2", pessoa="pe-2", presente=False, justificativa="Consulta médica")

    with com_base.connect() as conn:
        linhas = conn.execute(
            sa.text(
                """
                SELECT a.data, a.turma_id, a.educador_id, a.conteudo, c.pessoa_id, c.presente
                FROM chamadas c JOIN atividades a ON a.id = c.atividade_id ORDER BY c.pessoa_id
                """
            )
        ).all()
    assert [(str(l.data), l.turma_id, l.educador_id, l.conteudo, l.pessoa_id, l.presente) for l in linhas] == [
        ("2026-11-09", "t-1", "ana", "Pintura com guache", "pe-1", True),
        ("2026-11-09", "t-1", "ana", "Pintura com guache", "pe-2", False),
    ]


def test_pessoa_aparece_uma_vez_por_chamada(com_base):
    with com_base.begin() as conn:
        _executar(conn, CHAMADA, id="c-1", pessoa="pe-1", presente=True, justificativa=None)

    estado = _violacao(com_base, CHAMADA, id="c-2", pessoa="pe-1", presente=False, justificativa=None)
    assert estado == UNIQUE_VIOLATION


def test_chamada_exige_pessoa_existente_e_presenca_informada(com_base):
    assert _violacao(com_base, CHAMADA, id="c-x", pessoa="nao-existe", presente=True, justificativa=None) == FOREIGN_KEY_VIOLATION
    assert _violacao(com_base, CHAMADA, id="c-x", pessoa="pe-1", presente=None, justificativa=None) == NOT_NULL_VIOLATION


def test_justificativa_so_para_ausencia(com_base):
    estado = _violacao(com_base, CHAMADA, id="c-x", pessoa="pe-1", presente=True, justificativa="Chegou atrasada")

    assert estado == CHECK_VIOLATION


def test_linhas_da_chamada_saem_junto_com_o_encontro(com_base):
    with com_base.begin() as conn:
        _executar(conn, CHAMADA, id="c-1", pessoa="pe-1", presente=True, justificativa=None)
        _executar(conn, "DELETE FROM atividades WHERE id = 'a-1'")

    with com_base.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM chamadas")).scalar_one() == 0
        assert conn.execute(sa.text("SELECT count(*) FROM pessoas")).scalar_one() == 2


# --- Evidência -----------------------------------------------------------------


def test_evidencia_guarda_atividade_programa_autor_data_e_so_os_metadados(com_base):
    with com_base.begin() as conn:
        _executar(conn, EVIDENCIA, **_evidencia())

    with com_base.connect() as conn:
        linha = conn.execute(
            sa.text(
                "SELECT atividade_id, programa_id, autor_id, data, chave_arquivo, content_type, tamanho, criado_em "
                "FROM evidencias"
            )
        ).one()
    assert (linha.atividade_id, linha.programa_id, linha.autor_id, str(linha.data)) == ("a-1", "p-1", "jessica", "2026-11-09")
    assert (linha.chave_arquivo, linha.content_type, linha.tamanho) == ("gestao/evidencias/2026/11/ev-x.jpg", "image/jpeg", 1024)
    assert linha.criado_em is not None


@pytest.mark.parametrize(
    "extra",
    [{"programa": "p-2"}, {"autor": "ninguem"}],
    ids=["programa-diferente-do-da-atividade", "autor-inexistente"],
)
def test_evidencia_referencia_atividade_do_mesmo_programa_e_autor_existente(com_base, extra):
    assert _violacao(com_base, EVIDENCIA, **_evidencia(**extra)) == FOREIGN_KEY_VIOLATION


def test_evidencia_nao_apaga_junto_com_o_encontro(com_base):
    with com_base.begin() as conn:
        _executar(conn, EVIDENCIA, **_evidencia())

    with com_base.connect() as conn:
        with pytest.raises(IntegrityError) as erro:
            _executar(conn, "DELETE FROM atividades WHERE id = 'a-1'")
        conn.rollback()
    assert erro.value.orig.sqlstate == FOREIGN_KEY_VIOLATION


@pytest.mark.parametrize(
    "extra",
    [
        {"chave": "comprovantes/2026/11/x.jpg"},
        {"chave": "gestao/documentos/x.pdf"},
        {"tamanho": 0},
    ],
    ids=["pasta-do-financeiro", "pasta-de-documentos", "tamanho-zero"],
)
def test_evidencia_fica_na_pasta_da_gestao_e_tem_tamanho(com_base, extra):
    assert _violacao(com_base, EVIDENCIA, **_evidencia(**extra)) == CHECK_VIOLATION


def test_mesmo_registro_ou_mesmo_arquivo_nao_duplica_a_evidencia(com_base):
    with com_base.begin() as conn:
        _executar(conn, EVIDENCIA, **_evidencia())

    reenvio = _evidencia(id="ev-y", chave="gestao/evidencias/2026/11/ev-y.jpg")
    assert _violacao(com_base, EVIDENCIA, **reenvio) == UNIQUE_VIOLATION
    mesmo_arquivo = _evidencia(id="ev-y", registro="dispositivo-1/ev-y")
    assert _violacao(com_base, EVIDENCIA, **mesmo_arquivo) == UNIQUE_VIOLATION


# --- Reversibilidade -----------------------------------------------------------


def test_downgrade_remove_so_o_que_a_migration_criou_e_upgrade_recria(migrated_db):
    engine, config = migrated_db

    command.downgrade(config, REV_TURMAS)
    inspetor = sa.inspect(engine)
    tabelas = set(inspetor.get_table_names())
    assert not TABELAS & tabelas
    assert {"turmas", "matriculas", "pessoas", "projetos"} <= tabelas
    assert "uq_turmas_id_programa_id" not in {u["name"] for u in inspetor.get_unique_constraints("turmas")}

    command.upgrade(config, "head")
    assert TABELAS <= set(sa.inspect(engine).get_table_names())


def test_downgrade_com_dados_nas_turmas_preserva_as_turmas(com_base):
    config = _alembic_config()

    command.downgrade(config, REV_TURMAS)

    with com_base.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM turmas")).scalar_one() == 2
