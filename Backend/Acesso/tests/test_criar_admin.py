"""Comando da primeira administradora (T-35)."""

from datetime import datetime, timezone

import sqlalchemy as sa

from Acesso.criar_admin import criar_admin
from Acesso.tests.conftest import criar_usuario


def _criar(banco, nome, email):
    with banco.connect() as c:
        return criar_admin(c, nome, email, datetime.now(timezone.utc))


def test_cria_nova_e_segunda_com_mesmo_nome(banco):
    assert _criar(banco, "Maria Silva", "m1@mdca.org.br")[0] == "maria-silva"
    assert _criar(banco, "Maria Silva", "m2@mdca.org.br")[0] == "maria-silva-2"
    with banco.connect() as c:
        papeis = c.execute(
            sa.text("SELECT papel_id FROM usuarios_papeis WHERE usuario_id = 'maria-silva'")
        ).scalars().all()
    assert papeis == ["administracao"]


def test_slug_sem_acentos(banco):
    assert _criar(banco, "  Zélia  Ávila ", "z@mdca.org.br")[0] == "zelia-avila"


def test_email_existente_reaproveita_a_pessoa(banco):
    criar_usuario(banco, id="ana", nome="Ana", email="ana@mdca.org.br", papeis=["coordenacao"])
    usuario_id, _, _ = _criar(banco, "Outro Nome", "ANA@mdca.org.br")
    assert usuario_id == "ana"
    with banco.connect() as c:
        papeis = c.execute(
            sa.text("SELECT papel_id FROM usuarios_papeis WHERE usuario_id = 'ana' ORDER BY 1")
        ).scalars().all()
    assert papeis == ["administracao", "coordenacao"]


def test_codigo_serve_no_primeiro_acesso(banco, cliente):
    _, codigo, _ = _criar(banco, "Maria Silva", "m1@mdca.org.br")
    r = cliente.post(
        "/auth/primeiro-acesso",
        json={"email": "m1@mdca.org.br", "codigo": codigo, "senha": "senha-boa-1"},
    )
    assert r.status_code == 200
    assert [p["id"] for p in r.json()["usuario"]["papeis"]] == ["administracao"]


def test_nome_em_branco_e_recusado(banco):
    import pytest

    with pytest.raises(ValueError):
        _criar(banco, "   ", "x@mdca.org.br")
