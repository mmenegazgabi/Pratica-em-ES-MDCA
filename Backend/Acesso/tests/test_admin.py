"""Rotas /admin/usuarios do login único (T-35)."""

import sqlalchemy as sa

from Acesso.tests.conftest import criar_usuario

SENHA = "senha-boa-1"


def _sessao(banco, cliente, id="adm", papeis=("administracao",)):
    criar_usuario(banco, id=id, nome=id.title(), email=f"{id}@mdca.org.br", papeis=papeis, senha=SENHA)
    r = cliente.post("/auth/entrar", json={"email": f"{id}@mdca.org.br", "senha": SENHA})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _nova(cliente, h, **extra):
    corpo = {"nome": "Joao Silva", "email": " Joao@MDCA.org.br ", "papeis": ["coordenacao"], **extra}
    return cliente.post("/admin/usuarios", json=corpo, headers=h)


def _auditoria(banco, acao):
    with banco.connect() as c:
        return c.execute(
            sa.text("SELECT usuario_id, alvo_tipo, alvo_id, descricao, detalhes FROM log_auditoria WHERE acao = :a"),
            {"a": acao},
        ).all()


def test_sem_sessao_401(banco, cliente):
    assert cliente.get("/admin/usuarios").status_code == 401


def test_sem_papel_403_e_audita(banco, cliente):
    h = _sessao(banco, cliente, id="vol", papeis=("voluntario_financeiro",))
    assert cliente.get("/admin/usuarios", headers=h).status_code == 403
    linhas = _auditoria(banco, "acesso_negado")
    assert len(linhas) == 1 and linhas[0].alvo_tipo == "usuarios" and linhas[0].usuario_id == "vol"


def test_modo_servico_403(banco, cliente, cabecalhos):
    assert cliente.get("/admin/usuarios", headers=cabecalhos).status_code == 403
    assert len(_auditoria(banco, "acesso_negado")) == 1


def test_criar_e_primeiro_acesso(banco, cliente):
    h = _sessao(banco, cliente)
    r = _nova(cliente, h)
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["usuario"]["email"] == "joao@mdca.org.br"
    assert corpo["usuario"]["situacao"] == "aguardando_primeiro_acesso"
    assert corpo["codigo"] and corpo["codigo_expira_em"]
    lista = cliente.get("/admin/usuarios", headers=h).json()
    assert [u["id"] for u in lista] == ["adm", "joao-silva"]
    pa = cliente.post(
        "/auth/primeiro-acesso",
        json={"email": "joao@mdca.org.br", "codigo": corpo["codigo"], "senha": "outra-senha-9"},
    )
    assert pa.status_code == 200
    situacoes = {u["id"]: u["situacao"] for u in cliente.get("/admin/usuarios", headers=h).json()}
    assert situacoes["joao-silva"] == "ativo"


def test_validacoes_da_criacao(banco, cliente):
    h = _sessao(banco, cliente)
    assert _nova(cliente, h).status_code == 201
    assert _nova(cliente, h, nome="Outro", email="JOAO@mdca.org.br").status_code == 409
    assert _nova(cliente, h, email="x@y.com", papeis=["inexistente"]).status_code == 400
    r = _nova(cliente, h, email="x@y.com", papeis=[])
    assert r.status_code == 400 and r.json()["detail"] == "Escolha ao menos um papel."
    assert _nova(cliente, h, email="x@y.com", nome="  ").status_code == 400
    assert _nova(cliente, h, email="sem-arroba").status_code == 400


def test_desativar_encerra_sessao(banco, cliente):
    h = _sessao(banco, cliente)
    h2 = _sessao(banco, cliente, id="bia", papeis=("coordenacao",))
    assert cliente.get("/auth/eu", headers=h2).status_code == 200
    r = cliente.patch("/admin/usuarios/bia", json={"ativo": False}, headers=h)
    assert r.status_code == 200 and r.json()["situacao"] == "desativado"
    assert cliente.get("/auth/eu", headers=h2).status_code == 401
    assert len(_auditoria(banco, "usuario_desativado")) == 1
    r = cliente.patch("/admin/usuarios/bia", json={"ativo": True}, headers=h)
    assert r.json()["situacao"] == "ativo"
    assert len(_auditoria(banco, "usuario_reativado")) == 1


def test_editar_nome_e_papeis(banco, cliente):
    h = _sessao(banco, cliente)
    r = cliente.patch(
        "/admin/usuarios/adm", json={"nome": "Adm Novo", "papeis": ["administracao", "direcao"]}, headers=h
    )
    assert r.status_code == 200
    assert r.json()["nome"] == "Adm Novo"
    assert [p["id"] for p in r.json()["papeis"]] == ["administracao", "direcao"]
    assert len(_auditoria(banco, "usuario_editado")) == 1


def test_nao_mexe_na_propria_conta(banco, cliente):
    h = _sessao(banco, cliente)
    r = cliente.patch("/admin/usuarios/adm", json={"ativo": False}, headers=h)
    assert r.status_code == 400 and r.json()["detail"] == "Você não pode desativar a própria conta."
    r = cliente.patch("/admin/usuarios/adm", json={"papeis": ["direcao"]}, headers=h)
    assert r.status_code == 400 and r.json()["detail"] == "Você não pode tirar o próprio papel de administração."


def test_patch_e_codigo_de_pessoa_inexistente_404(banco, cliente):
    h = _sessao(banco, cliente)
    assert cliente.patch("/admin/usuarios/nada", json={"nome": "X"}, headers=h).status_code == 404
    assert cliente.post("/admin/usuarios/nada/codigo", headers=h).status_code == 404


def test_novo_codigo_invalida_o_anterior_e_nao_vai_para_auditoria(banco, cliente):
    h = _sessao(banco, cliente)
    antigo = _nova(cliente, h).json()["codigo"]
    r = cliente.post("/admin/usuarios/joao-silva/codigo", headers=h)
    assert r.status_code == 200
    novo = r.json()["codigo"]
    corpo = {"email": "joao@mdca.org.br", "senha": "outra-senha-9"}
    assert cliente.post("/auth/primeiro-acesso", json={**corpo, "codigo": antigo}).status_code == 400
    with banco.connect() as c:
        tudo = str(c.execute(sa.text("SELECT detalhes, descricao FROM log_auditoria")).all())
    assert antigo not in tudo and novo not in tudo
    assert len(_auditoria(banco, "codigo_gerado")) == 1
    assert cliente.post("/auth/primeiro-acesso", json={**corpo, "codigo": novo}).status_code == 200


def test_codigo_de_pessoa_desativada_400(banco, cliente):
    h = _sessao(banco, cliente)
    _nova(cliente, h)
    cliente.patch("/admin/usuarios/joao-silva", json={"ativo": False}, headers=h)
    r = cliente.post("/admin/usuarios/joao-silva/codigo", headers=h)
    assert r.status_code == 400 and r.json()["detail"] == "Reative a pessoa antes de gerar um código."


def test_editar_email_de_pessoa_sem_email(banco, cliente):
    h = _sessao(banco, cliente)
    criar_usuario(banco, id="leo", nome="Leo", email=None, papeis=["educador"])
    r = cliente.patch("/admin/usuarios/leo", json={"email": "  Leo@MDCA.org.br "}, headers=h)
    assert r.status_code == 200 and r.json()["email"] == "leo@mdca.org.br"
    linhas = _auditoria(banco, "usuario_editado")
    assert len(linhas) == 1 and linhas[0].detalhes == {"email": "leo@mdca.org.br"}
    # Com o e-mail, o código de primeiro acesso já serve.
    codigo = cliente.post("/admin/usuarios/leo/codigo", headers=h).json()["codigo"]
    pa = cliente.post(
        "/auth/primeiro-acesso",
        json={"email": "leo@mdca.org.br", "codigo": codigo, "senha": "outra-senha-9"},
    )
    assert pa.status_code == 200


def test_editar_email_valida_e_recusa_repetido(banco, cliente):
    h = _sessao(banco, cliente)
    criar_usuario(banco, id="leo", nome="Leo", email="leo@mdca.org.br", papeis=["educador"])
    r = cliente.patch("/admin/usuarios/leo", json={"email": "ADM@mdca.org.br"}, headers=h)
    assert r.status_code == 409 and r.json()["detail"] == "Já existe uma pessoa com este e-mail."
    assert cliente.patch("/admin/usuarios/leo", json={"email": "sem-arroba"}, headers=h).status_code == 400
    # O próprio e-mail, só com outra caixa, não é repetido nem alteração.
    r = cliente.patch("/admin/usuarios/leo", json={"email": "LEO@mdca.org.br"}, headers=h)
    assert r.status_code == 200 and r.json()["email"] == "leo@mdca.org.br"
    assert _auditoria(banco, "usuario_editado") == []
