"""T-35: núcleo de senhas, códigos de acesso e sessões, mais a migration das tabelas."""

import re
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from alembic import command

from Acesso import codigos, sessoes
from Acesso.senhas import conferir, gerar_hash, validar
from Acesso.tests.conftest import TEST_DATABASE_URL, criar_usuario

AGORA = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
REV_ANTERIOR = "5c2e8d41a7b3"


def test_hash_confere_e_nao_guarda_texto():
    h = gerar_hash("segredo123")
    assert h.startswith("scrypt$16384$8$1$")
    assert "segredo123" not in h
    assert conferir("segredo123", h)
    assert not conferir("outra", h)
    assert not conferir("x", None)
    assert not conferir("x", "lixo")


def test_validar_senha():
    assert validar("1234567") == "A senha precisa ter pelo menos 8 caracteres."
    assert validar("x" * 129) == "A senha pode ter no máximo 128 caracteres."
    assert validar("12345678") is None


def test_codigo_formato_e_normalizacao():
    assert re.fullmatch(r"[A-HJ-NP-Z2-9]{3}-[A-HJ-NP-Z2-9]{3}-[A-HJ-NP-Z2-9]{3}", codigos.gerar())
    assert codigos.normalizar(" k7q-4mz 9p2 ") == "K7Q4MZ9P2"


@pytest.fixture
def ana(banco):
    criar_usuario(banco, id="ana", nome="Ana", email="ana@exemplo.test", papeis=["coordenacao"])
    return banco


def test_codigo_vale_uma_vez(ana):
    with ana.begin() as c:
        codigo, _ = codigos.emitir(c, "ana", "admin", AGORA)
    with ana.begin() as c:
        assert codigos.consumir(c, "ana", codigo.lower(), AGORA)
    with ana.begin() as c:
        assert not codigos.consumir(c, "ana", codigo, AGORA)


def test_codigo_novo_invalida_anterior(ana):
    with ana.begin() as c:
        a, _ = codigos.emitir(c, "ana", "admin", AGORA)
        b, _ = codigos.emitir(c, "ana", "admin", AGORA)
    with ana.begin() as c:
        assert not codigos.consumir(c, "ana", a, AGORA)
        assert codigos.consumir(c, "ana", b, AGORA)


def test_codigo_vence_em_7_dias(ana):
    with ana.begin() as c:
        codigo, validade = codigos.emitir(c, "ana", None, AGORA)
        assert validade == AGORA + timedelta(days=7)
        assert not codigos.consumir(c, "ana", codigo, AGORA + timedelta(days=7, seconds=1))
        assert codigos.consumir(c, "ana", codigo, AGORA + timedelta(days=6))


def test_codigo_nao_serve_para_outro_usuario(ana):
    criar_usuario(ana, id="rafa", nome="Rafa", email=None)
    with ana.begin() as c:
        codigo, _ = codigos.emitir(c, "ana", None, AGORA)
        assert not codigos.consumir(c, "rafa", codigo, AGORA)


def test_sessao_validade(ana):
    with ana.begin() as c:
        token, expira = sessoes.criar(c, "ana", True, AGORA)
        assert expira == AGORA + timedelta(days=30)
        curto, expira_curto = sessoes.criar(c, "ana", False, AGORA)
        assert expira_curto == AGORA + timedelta(hours=12)
        hashes = c.execute(sa.text("SELECT token_hash FROM sessoes")).scalars().all()
        assert token not in hashes and curto not in hashes
        assert sessoes.usuario_da_sessao(c, token, AGORA) == "ana"
        assert sessoes.usuario_da_sessao(c, curto, AGORA + timedelta(hours=13)) is None
        sessoes.encerrar(c, token)
        assert sessoes.usuario_da_sessao(c, token, AGORA) is None
        sessoes.encerrar_todas(c, "ana")
        assert sessoes.usuario_da_sessao(c, curto, AGORA) is None


def test_sessao_de_usuario_desativado_nao_vale(ana):
    with ana.begin() as c:
        token, _ = sessoes.criar(c, "ana", True, AGORA)
    with ana.begin() as c:
        c.execute(sa.text("UPDATE usuarios SET ativo = false WHERE id = 'ana'"))
    with ana.begin() as c:
        assert sessoes.usuario_da_sessao(c, token, AGORA) is None


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL não definido")
def test_migration_cria_e_remove(motor_de_teste):
    from Gestao.tests.conftest import _alembic_config

    config = _alembic_config()
    try:
        command.downgrade(config, REV_ANTERIOR)
        inspetor = sa.inspect(motor_de_teste)
        assert not {"sessoes", "codigos_acesso"} & set(inspetor.get_table_names())
        assert "senha_hash" not in {c["name"] for c in inspetor.get_columns("usuarios")}

        command.upgrade(config, "head")
        inspetor = sa.inspect(motor_de_teste)
        assert {c["name"] for c in inspetor.get_columns("sessoes")} == {
            "token_hash", "usuario_id", "criada_em", "expira_em"
        }
        assert {c["name"] for c in inspetor.get_columns("codigos_acesso")} == {
            "id", "usuario_id", "codigo_hash", "criado_em", "expira_em", "usado_em", "criado_por"
        }
        assert "senha_hash" in {c["name"] for c in inspetor.get_columns("usuarios")}
        assert any(i["column_names"] == ["usuario_id"] for i in inspetor.get_indexes("sessoes"))
        assert any(i["column_names"] == ["usuario_id"] for i in inspetor.get_indexes("codigos_acesso"))
    finally:
        command.upgrade(config, "head")
