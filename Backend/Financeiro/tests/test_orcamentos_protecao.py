"""Rotas de orçamento fechadas sem login e por papel (T-11, T-15), no modo serviço.

O client daqui não tem cabeçalhos fixos: cada chamada diz com que token e papel vai.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from Financeiro.main import app
from Financeiro.orcamento import Lancamento, Orcamento, StatusLancamento
from Financeiro.projetos import _projetos, registrar_projeto
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"

client = TestClient(app)


def como(papel):
    return {"Authorization": f"Bearer {TOKEN}", "X-Papel-Usuario": papel}


@pytest.fixture(autouse=True)
def token_configurado(monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)


@pytest.fixture(autouse=True)
def orcamento_com_lancamentos():
    _orcamentos.clear()
    _projetos.clear()
    registrar_projeto("Projeto 1").id = "projeto-1"
    _orcamentos.append(
        Orcamento(
            id="orcamento-1",
            projeto_id="projeto-1",
            valor_total=1000,
            data_inicio=date(2026, 1, 1),
            data_fim=date(2026, 12, 31),
            categorias_despesa=["materiais"],
            lancamentos=[
                Lancamento(
                    id="pendente",
                    valor=100,
                    categoria="materiais",
                    status=StatusLancamento.PENDENTE,
                ),
                Lancamento(
                    id="aprovado",
                    valor=50,
                    categoria="materiais",
                    status=StatusLancamento.APROVADO,
                ),
            ],
        )
    )
    yield
    _orcamentos.clear()
    _projetos.clear()


LEITURAS = ["/orcamentos", "/orcamentos/orcamento-1", "/orcamentos/projeto/projeto-1"]


@pytest.mark.parametrize("rota", LEITURAS)
def test_leitura_sem_token_da_401(rota):
    assert client.get(rota).status_code == 401


@pytest.mark.parametrize("rota", LEITURAS)
def test_leitura_com_token_errado_da_401(rota):
    assert client.get(rota, headers={"Authorization": "Bearer errado"}).status_code == 401


@pytest.mark.parametrize("rota", LEITURAS)
def test_leitura_com_token_vale_para_educador(rota):
    assert client.get(rota, headers=como("educador")).status_code == 200


def test_criar_orcamento_sem_token_da_401():
    resposta = client.post("/orcamentos", json={"projeto_id": "projeto-1"})

    assert resposta.status_code == 401


@pytest.mark.parametrize("papel", ["educador", "direcao", "voluntario_financeiro"])
def test_criar_orcamento_fora_da_coordenacao_da_403(papel):
    resposta = client.post(
        "/orcamentos",
        json={
            "projeto_id": "projeto-1",
            "valor_total": 500.0,
            "data_inicio": "2026-01-01",
            "data_fim": "2026-12-31",
            "categorias_despesa": ["materiais"],
        },
        headers=como(papel),
    )

    assert resposta.status_code == 403
    assert len(_orcamentos) == 1


# A aprovação é PATCH /lancamentos/{id}/aprovar (a das telas). As rotas antigas
# POST /orcamentos/{id}/lancamentos/{id}/aprovar e /reverter-aprovacao saíram na E3
# (docs/persistencia-financeiro.md, "Rotas removidas").
APROVAR = "/lancamentos/pendente/aprovar"


@pytest.mark.parametrize("papel", ["educador", "voluntario_financeiro"])
def test_aprovar_fora_da_coordenacao_e_direcao_da_403(papel):
    resposta = client.patch(APROVAR, headers=como(papel))

    assert resposta.status_code == 403
    assert _orcamentos[0].lancamentos[0].status == StatusLancamento.PENDENTE


def test_aprovar_sem_token_da_401():
    assert client.patch(APROVAR).status_code == 401
    assert _orcamentos[0].lancamentos[0].status == StatusLancamento.PENDENTE


@pytest.mark.parametrize("papel", ["coordenacao", "direcao"])
def test_direcao_e_coordenacao_aprovam(papel):
    resposta = client.patch(APROVAR, headers=como(papel))

    assert resposta.status_code == 200
    assert _orcamentos[0].lancamentos[0].status == StatusLancamento.APROVADO


@pytest.mark.parametrize(
    "rota",
    [
        "/orcamentos/orcamento-1/lancamentos/pendente/aprovar",
        "/orcamentos/orcamento-1/lancamentos/aprovado/reverter-aprovacao",
    ],
)
def test_rotas_antigas_de_aprovar_e_reverter_nao_existem(rota):
    assert client.post(rota, headers=como("coordenacao")).status_code in (404, 405)
    assert [l.status for l in _orcamentos[0].lancamentos] == [
        StatusLancamento.PENDENTE,
        StatusLancamento.APROVADO,
    ]
