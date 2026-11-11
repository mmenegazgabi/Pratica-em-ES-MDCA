"""Cadastro de projetos e orçamento só para projeto existente."""

import pytest
from fastapi.testclient import TestClient

from Financeiro.main import app
from Financeiro.projetos import _projetos
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"

client = TestClient(app)

# As rotas de orçamento passaram a exigir login (T-33): a tela manda o código de
# acesso e o papel em toda chamada.
LEITURA_ORCAMENTO = {"Authorization": f"Bearer {TOKEN}", "X-Papel-Usuario": "coordenacao"}

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
    detalhe = client.get(f"/orcamentos/{orcamento_id}", headers=LEITURA_ORCAMENTO).json()
    assert detalhe["projeto_nome"] == "Oficina de Arte"
    assert client.get("/orcamentos", headers=LEITURA_ORCAMENTO).json()[0]["projeto_nome"] == "Oficina de Arte"


def test_projeto_nome_e_nulo_quando_o_projeto_nao_existe_mais():
    projeto = criar_projeto("Temporário").json()
    orcamento_id = client.post(
        "/orcamentos", json={**ORCAMENTO, "projeto_id": projeto["id"]}, headers=LEITURA_ORCAMENTO).json()["id"]
    _projetos.clear()

    assert client.get(f"/orcamentos/{orcamento_id}", headers=LEITURA_ORCAMENTO).json()["projeto_nome"] is None


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
    assert set(resposta.json()[0]) == {"id", "nome", "status"}
    assert resposta.json()[0]["status"] == "ativo"


def test_listar_projetos_sem_autenticacao_401():
    assert client.get("/projetos").status_code == 401


def alterar_status(projeto_id, status, papel="direcao"):
    return client.patch(
        f"/projetos/{projeto_id}/status", json={"status": status}, headers=cabecalhos(papel)
    )


@pytest.mark.parametrize("papel", ["coordenacao", "direcao"])
def test_encerrar_e_reabrir_projeto(papel):
    projeto = criar_projeto("Leitura").json()

    encerrado = alterar_status(projeto["id"], "encerrado", papel)
    assert encerrado.status_code == 200
    assert encerrado.json()["status"] == "encerrado"
    assert client.get("/projetos", headers=cabecalhos()).json()[0]["status"] == "encerrado"

    assert alterar_status(projeto["id"], "ativo", papel).json()["status"] == "ativo"


@pytest.mark.parametrize("papel", ["educador", "voluntario_financeiro"])
def test_alterar_status_outros_papeis_403(papel):
    projeto = criar_projeto("Leitura").json()

    assert alterar_status(projeto["id"], "encerrado", papel).status_code == 403
    assert _projetos[0].status == "ativo"


def test_alterar_status_de_projeto_inexistente_404():
    assert alterar_status("nao-existe", "encerrado").status_code == 404


def test_alterar_status_invalido_422():
    projeto = criar_projeto("Leitura").json()

    assert alterar_status(projeto["id"], "pausado").status_code == 422
