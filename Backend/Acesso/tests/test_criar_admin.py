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


def test_promove_pessoa_existente_pelo_id(banco, cliente):
    criar_usuario(banco, id="ana", nome="Ana", email=None, papeis=["coordenacao"], ativo=False)
    with banco.connect() as c:
        usuario_id, codigo, _ = criar_admin(
            c, "Ignorado", " Ana@MDCA.org.br ", datetime.now(timezone.utc), usuario_id="ana"
        )
    assert usuario_id == "ana"
    with banco.connect() as c:
        linha = c.execute(sa.text("SELECT nome, email, ativo FROM usuarios WHERE id = 'ana'")).one()
        papeis = c.execute(
            sa.text("SELECT papel_id FROM usuarios_papeis WHERE usuario_id = 'ana' ORDER BY 1")
        ).scalars().all()
        total = c.execute(sa.text("SELECT count(*) FROM usuarios")).scalar()
    assert (linha.nome, linha.email, linha.ativo) == ("Ana", "ana@mdca.org.br", True)
    assert papeis == ["administracao", "coordenacao"] and total == 1
    r = cliente.post(
        "/auth/primeiro-acesso",
        json={"email": "ana@mdca.org.br", "codigo": codigo, "senha": "senha-boa-1"},
    )
    assert r.status_code == 200


def test_id_inexistente_ou_email_de_outra_pessoa_e_recusado(banco):
    import pytest

    criar_usuario(banco, id="ana", nome="Ana", email="ana@mdca.org.br")
    criar_usuario(banco, id="bia", nome="Bia", email=None)
    with banco.connect() as c:
        with pytest.raises(ValueError):
            criar_admin(c, "", "x@mdca.org.br", datetime.now(timezone.utc), usuario_id="nada")
        with pytest.raises(ValueError):
            criar_admin(c, "", "ANA@mdca.org.br", datetime.now(timezone.utc), usuario_id="bia")


def test_main_com_id_dispensa_o_nome(banco, capsys):
    from Acesso.criar_admin import main

    criar_usuario(banco, id="bia", nome="Bia", email=None)
    assert main(["--id", "bia", "--email", "bia@mdca.org.br"]) == 0
    assert "Código de primeiro acesso" in capsys.readouterr().out
    with banco.connect() as c:
        assert c.execute(sa.text("SELECT email FROM usuarios WHERE id = 'bia'")).scalar() == "bia@mdca.org.br"
