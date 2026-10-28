"""PATCH /orcamentos/{id} — coordenação edita valor, vigência e categorias."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from Financeiro.main import app
from Financeiro.orcamento import Lancamento, Orcamento, StatusLancamento
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"

client = TestClient(app)


def cabecalhos(papel="coordenacao", token=TOKEN):
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if papel is not None:
        headers["X-Papel-Usuario"] = papel
    return headers


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    _orcamentos.clear()
    yield
    _orcamentos.clear()


def criar_orcamento(*lancamentos, valor_total=1000):
    orcamento = Orcamento(
        id="orcamento-1",
        projeto_id="projeto-1",
        valor_total=valor_total,
        data_inicio=date(2026, 1, 1),
        data_fim=date(2026, 12, 31),
        categorias_despesa=["materiais", "transporte"],
        lancamentos=list(lancamentos),
    )
    _orcamentos.append(orcamento)
    return orcamento


def lancamento(valor, status, categoria="materiais"):
    return Lancamento(valor=valor, status=status, categoria=categoria)


def corpo(**extra):
    base = {
        "valor_total": 1000,
        "data_inicio": "2026-01-01",
        "data_fim": "2026-12-31",
        "categorias_despesa": ["materiais", "transporte"],
    }
    base.update(extra)
    return base


def editar(corpo_, orcamento_id="orcamento-1", **kwargs):
    return client.patch(
        f"/orcamentos/{orcamento_id}", json=corpo_, headers=cabecalhos(**kwargs)
    )


def test_editar_atualiza_valor_e_saldo():
    criar_orcamento(lancamento(300, StatusLancamento.APROVADO))
    resposta = editar(corpo(valor_total=2000, categorias_despesa=["materiais", "obras"]))
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["valor_total"] == 2000
    assert dados["saldo"] == 1700
    assert dados["realizado"] == 300
    assert dados["categorias_despesa"] == ["materiais", "obras"]
    assert dados["projeto_id"] == "projeto-1"


def test_valor_menor_que_o_gasto_e_rejeitado():
    criar_orcamento(lancamento(300, StatusLancamento.APROVADO))
    resposta = editar(corpo(valor_total=250))
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == (
        "O valor total não pode ser menor que o já gasto (R$ 300,00)."
    )


def test_data_fim_anterior_a_data_inicio_e_rejeitada():
    criar_orcamento()
    resposta = editar(corpo(data_inicio="2026-06-01", data_fim="2026-05-01"))
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "data_fim não pode ser anterior a data_inicio"


@pytest.mark.parametrize(
    "status", [StatusLancamento.PENDENTE, StatusLancamento.APROVADO]
)
def test_categoria_com_lancamento_nao_rejeitado_nao_pode_ser_removida(status):
    criar_orcamento(lancamento(100, status, categoria="transporte"))
    resposta = editar(corpo(categorias_despesa=["materiais"]))
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == (
        'A categoria "transporte" tem lançamentos e não pode ser removida.'
    )


def test_categoria_so_com_lancamento_rejeitado_pode_ser_removida():
    criar_orcamento(lancamento(100, StatusLancamento.REJEITADO, categoria="transporte"))
    resposta = editar(corpo(categorias_despesa=["materiais"]))
    assert resposta.status_code == 200
    assert resposta.json()["categorias_despesa"] == ["materiais"]


def test_lista_vazia_de_categorias_e_rejeitada():
    criar_orcamento()
    resposta = editar(corpo(categorias_despesa=[]))
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Informe ao menos uma categoria."


def test_direcao_recebe_403():
    criar_orcamento()
    assert editar(corpo(), papel="direcao").status_code == 403


def test_sem_token_recebe_401():
    criar_orcamento()
    assert editar(corpo(), token=None).status_code == 401


def test_orcamento_inexistente_404():
    resposta = editar(corpo(), orcamento_id="nao-existe")
    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Orçamento não encontrado"


def test_valor_igual_ao_gasto_com_centavos_e_aceito():
    criar_orcamento(
        lancamento(420.50, StatusLancamento.APROVADO),
        lancamento(180.10, StatusLancamento.APROVADO),
        lancamento(0.70, StatusLancamento.APROVADO),
        valor_total=2000,
    )
    resposta = editar(corpo(valor_total=601.30))
    assert resposta.status_code == 200
    assert resposta.json()["saldo"] == 0
    assert resposta.json()["realizado"] == 601.30


def test_edicao_recusada_nao_altera_o_orcamento():
    orcamento = criar_orcamento(lancamento(300, StatusLancamento.APROVADO))
    resposta = editar(corpo(valor_total=250, categorias_despesa=["obras"]))
    assert resposta.status_code == 400
    assert orcamento.valor_total == 1000
    assert orcamento.saldo_atual == 700
    assert orcamento.categorias_despesa == ["materiais", "transporte"]


@pytest.mark.parametrize("valor", ["NaN", "Infinity", "-Infinity", "0", "-5"])
def test_valor_total_invalido_e_rejeitado_e_nada_muda(valor):
    orcamento = criar_orcamento(lancamento(300, StatusLancamento.APROVADO))
    corpo_bruto = (
        '{"valor_total": %s, "data_inicio": "2026-01-01", "data_fim": "2026-12-31",'
        ' "categorias_despesa": ["materiais"]}' % valor
    )
    resposta = client.patch(
        "/orcamentos/orcamento-1",
        content=corpo_bruto,
        headers={**cabecalhos(), "Content-Type": "application/json"},
    )
    assert resposta.status_code in (400, 422)
    assert orcamento.valor_total == 1000
    assert orcamento.saldo_atual == 700
