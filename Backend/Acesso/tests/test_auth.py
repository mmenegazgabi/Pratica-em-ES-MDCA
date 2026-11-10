"""Rotas /auth do login único (T-35)."""

from datetime import datetime, timezone

import sqlalchemy as sa

from Acesso import codigos
from Acesso.tests.conftest import criar_usuario

MENSAGEM_LOGIN = "E-mail ou senha incorretos."
MENSAGEM_CODIGO = "Código inválido ou vencido."


def _ana(banco, **extra):
    criar_usuario(banco, id="ana", nome="Ana", email="ana@mdca.org.br", senha="senha-boa-1", **extra)


def _entrar(cliente, email="ana@mdca.org.br", senha="senha-boa-1", **extra):
    return cliente.post("/auth/entrar", json={"email": email, "senha": senha, **extra})


def _emitir(banco, usuario_id):
    with banco.begin() as c:
        return codigos.emitir(c, usuario_id, None, datetime.now(timezone.utc))[0]


def test_entrar_devolve_token_e_papeis(banco, cliente):
    _ana(banco, papeis=["voluntario_financeiro", "coordenacao"])
    r = _entrar(cliente, email=" Ana@MDCA.org.br ")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["token"]
    assert [p["id"] for p in corpo["usuario"]["papeis"]] == ["coordenacao", "voluntario_financeiro"]


def test_entrar_falhas_tem_a_mesma_resposta(banco, cliente):
    _ana(banco)
    criar_usuario(banco, id="sem", nome="Sem", email="sem@mdca.org.br")
    criar_usuario(banco, id="off", nome="Off", email="off@mdca.org.br", senha="senha-boa-1", ativo=False)
    tentativas = [
        ("nao@mdca.org.br", "senha-boa-1"),
        ("ana@mdca.org.br", "errada-errada"),
        ("sem@mdca.org.br", "senha-boa-1"),
        ("off@mdca.org.br", "senha-boa-1"),
    ]
    for email, senha in tentativas:
        r = _entrar(cliente, email=email, senha=senha)
        assert r.status_code == 401
        assert r.json()["detail"] == MENSAGEM_LOGIN


def test_bloqueia_depois_de_5_falhas(banco, cliente):
    _ana(banco)
    for _ in range(5):
        assert _entrar(cliente, senha="errada-errada").status_code == 401
    r = _entrar(cliente)
    assert r.status_code == 429
    assert r.json()["detail"] == "Muitas tentativas. Tente de novo em alguns minutos."


def test_primeiro_acesso_define_senha(banco, cliente):
    criar_usuario(banco, id="bia", nome="Bia", email="bia@mdca.org.br")
    codigo = _emitir(banco, "bia")
    corpo = {"email": "bia@mdca.org.br", "codigo": codigo, "senha": "nova-senha-1"}
    r = cliente.post("/auth/primeiro-acesso", json=corpo)
    assert r.status_code == 200
    assert r.json()["token"]
    assert _entrar(cliente, email="bia@mdca.org.br", senha="nova-senha-1").status_code == 200
    r = cliente.post("/auth/primeiro-acesso", json=corpo)
    assert r.status_code == 400
    assert r.json()["detail"] == MENSAGEM_CODIGO


def test_primeiro_acesso_senha_curta(banco, cliente):
    criar_usuario(banco, id="bia", nome="Bia", email="bia@mdca.org.br")
    codigo = _emitir(banco, "bia")
    r = cliente.post(
        "/auth/primeiro-acesso", json={"email": "bia@mdca.org.br", "codigo": codigo, "senha": "curta"}
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "A senha precisa ter pelo menos 8 caracteres."
    r = cliente.post(
        "/auth/primeiro-acesso", json={"email": "bia@mdca.org.br", "codigo": codigo, "senha": "senha-longa-1"}
    )
    assert r.status_code == 200


def test_primeiro_acesso_encerra_outras_sessoes(banco, cliente):
    _ana(banco)
    antigo = _entrar(cliente).json()["token"]
    codigo = _emitir(banco, "ana")
    r = cliente.post(
        "/auth/primeiro-acesso",
        json={"email": "ana@mdca.org.br", "codigo": codigo, "senha": "outra-senha-1"},
    )
    assert r.status_code == 200
    assert cliente.get("/auth/eu", headers={"Authorization": f"Bearer {antigo}"}).status_code == 401
    novo = r.json()["token"]
    assert cliente.get("/auth/eu", headers={"Authorization": f"Bearer {novo}"}).status_code == 200


def test_eu_e_sair(banco, cliente):
    _ana(banco, papeis=["coordenacao"])
    entrada = _entrar(cliente).json()
    cab = {"Authorization": f"Bearer {entrada['token']}"}
    r = cliente.get("/auth/eu", headers=cab)
    assert r.status_code == 200
    assert r.json() == entrada["usuario"]
    assert cliente.post("/auth/sair", headers=cab).status_code == 204
    r = cliente.get("/auth/eu", headers=cab)
    assert r.status_code == 401
    assert r.json()["detail"] == "Sessão inválida ou vencida."
    assert cliente.post("/auth/sair").status_code == 204


def test_auditoria_de_login(banco, cliente):
    _ana(banco)
    _entrar(cliente)
    _entrar(cliente, senha="errada-errada")
    with banco.connect() as c:
        linhas = c.execute(
            sa.text("SELECT acao, modulo, alvo_id FROM log_auditoria ORDER BY id")
        ).all()
    assert [(l.acao, l.modulo) for l in linhas] == [("login", "plataforma"), ("login_falhou", "plataforma")]
    assert linhas[1].alvo_id == "ana@mdca.org.br"


def test_email_desconhecido_tambem_roda_o_scrypt(banco, cliente, monkeypatch):
    from Acesso import senhas

    chamadas = []
    original = senhas._scrypt
    monkeypatch.setattr(senhas, "_scrypt", lambda *a, **k: chamadas.append(1) or original(*a, **k))
    assert _entrar(cliente, email="nao@mdca.org.br").status_code == 401
    assert len(chamadas) == 1
