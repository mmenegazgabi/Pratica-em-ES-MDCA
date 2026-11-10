"""Erro do banco nas rotas de Acesso vira 503 com CORS, não 500 (T-35)."""

import sqlalchemy as sa

from Acesso import admin, usuarios
from Acesso.tests.conftest import criar_usuario

ORIGEM = {"Origin": "http://localhost:8080"}


def _tabela_faltando(*_args, **_kwargs):
    raise sa.exc.ProgrammingError("SELECT ...", {}, Exception('relation "usuarios" does not exist'))


def _banco_fora(*_args, **_kwargs):
    raise sa.exc.OperationalError("SELECT ...", {}, Exception("server closed the connection"))


def test_auth_com_tabela_faltando_responde_503_com_cors(banco, cliente, monkeypatch):
    monkeypatch.setattr(usuarios, "por_email", _tabela_faltando)
    r = cliente.post(
        "/auth/entrar", json={"email": "ana@mdca.org.br", "senha": "senha-boa-1"}, headers=ORIGEM
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "Banco de dados indisponível"
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8080"


def test_admin_com_banco_fora_responde_503(banco, cliente, monkeypatch):
    criar_usuario(
        banco, id="adm", nome="Adm", email="adm@mdca.org.br", papeis=["administracao"], senha="senha-boa-1"
    )
    token = cliente.post(
        "/auth/entrar", json={"email": "adm@mdca.org.br", "senha": "senha-boa-1"}
    ).json()["token"]
    monkeypatch.setattr(admin, "listar", _banco_fora)
    r = cliente.get("/admin/usuarios", headers={"Authorization": f"Bearer {token}", **ORIGEM})
    assert r.status_code == 503
    assert r.json()["detail"] == "Banco de dados indisponível"
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8080"
