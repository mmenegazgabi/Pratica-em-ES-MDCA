"""Cadastro de projetos e orçamento só para projeto existente."""

import pytest
from fastapi.testclient import TestClient

from Financeiro.main import app
from Financeiro.projetos import _projetos
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"

client = TestClient(app)

ORCAMENTO = {
    "projeto_id": "projeto-1",
    "valor_total": 1000.0,
    "data_inicio": "2026-01-01",
    "data_fim": "2026-12-31",
    "categorias_despesa": ["materiais"],
}


def cabecalhos(papel="coordenacao"):
    return {"Authorization": f"Bearer {TOKEN}", "X-Papel-Usuario": papel}


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    _orcamentos.clear()
    _projetos.clear()
    yield
    _orcamentos.clear()
    _projetos.clear()


def criar_projeto(nome, papel="coordenacao"):
    return client.post("/projetos", json={"nome": nome}, headers=cabecalhos(papel))


def test_criar_orcamento_para_projeto_inexistente_retorna_400_e_nao_cria():
    resposta = client.post("/orcamentos", json={**ORCAMENTO, "projeto_id": "nao-existe"}, headers=cabecalhos())

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Projeto não encontrado. Cadastre o projeto antes de criar o orçamento."
    assert _orcamentos == []


def test_criar_orcamento_para_projeto_existente_retorna_201_com_nome():
    projeto = criar_projeto("Oficina de Arte").json()

    resposta = client.post("/orcamentos", json={**ORCAMENTO, "projeto_id": projeto["id"]}, headers=cabecalhos())

    assert resposta.status_code == 201
    assert resposta.json()["projeto_id"] == projeto["id"]
    orcamento_id = resposta.json()["id"]
    detalhe = client.get(f"/orcamentos/{orcamento_id}").json()
    assert detalhe["projeto_nome"] == "Oficina de Arte"
    assert client.get("/orcamentos").json()[0]["projeto_nome"] == "Oficina de Arte"


def test_projeto_nome_e_nulo_quando_o_projeto_nao_existe_mais():
    projeto = criar_projeto("Temporário").json()
    orcamento_id = client.post(
        "/orcamentos", json={**ORCAMENTO, "projeto_id": projeto["id"]}
    ).json()["id"]
    _projetos.clear()

    assert client.get(f"/orcamentos/{orcamento_id}").json()["projeto_nome"] is None


def test_criar_projeto_coordenacao_201():
    resposta = criar_projeto("  Leitura  ")

    assert resposta.status_code == 201
    assert resposta.json()["nome"] == "Leitura"
    assert resposta.json()["id"]


@pytest.mark.parametrize("papel", ["educador", "financeiro"])
def test_criar_projeto_outros_papeis_403(papel):
    assert criar_projeto("Leitura", papel).status_code == 403
    assert _projetos == []


@pytest.mark.parametrize("nome", ["", "   "])
def test_criar_projeto_nome_vazio_400(nome):
    resposta = criar_projeto(nome)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Informe o nome do projeto."


def test_criar_projeto_nome_com_mais_de_120_caracteres_400():
    assert criar_projeto("a" * 121).status_code == 400


def test_criar_projeto_nome_repetido_409():
    assert criar_projeto("Leitura").status_code == 201

    for repetido in (" leitura ", "LEITURA"):
        resposta = criar_projeto(repetido)
        assert resposta.status_code == 409
        assert resposta.json()["detail"] == "Já existe um projeto com esse nome."


def test_criar_projeto_nome_repetido_sem_diferenciar_acentos_409():
    assert criar_projeto("Educação").status_code == 201
    assert criar_projeto("educacao").status_code == 409


def test_listar_projetos_em_ordem_alfabetica():
    for nome in ("Semear", "Casa de Convivência", "Oficina"):
        criar_projeto(nome)

    resposta = client.get("/projetos", headers=cabecalhos("educador"))

    assert resposta.status_code == 200
    assert [p["nome"] for p in resposta.json()] == ["Casa de Convivência", "Oficina", "Semear"]
    assert set(resposta.json()[0]) == {"id", "nome"}


def test_listar_projetos_sem_autenticacao_401():
    assert client.get("/projetos").status_code == 401
