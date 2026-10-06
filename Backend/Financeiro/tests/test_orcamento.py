from datetime import date

from fastapi.testclient import TestClient

from Financeiro.main import app
from Financeiro.orcamento import Lancamento, Orcamento, StatusLancamento
from Financeiro.routers.orcamentos import _orcamentos

client = TestClient(app)


def setup_function():
    _orcamentos.clear()


def payload(**overrides):
    base = {
        "projeto_id": "projeto-1",
        "valor_total": 1000.0,
        "data_inicio": "2026-01-01",
        "data_fim": "2026-12-31",
        "categorias_despesa": ["materiais", "transporte"],
    }
    base.update(overrides)
    return base


def orcamento_de_teste(**overrides):
    base = {
        "id": "orcamento-1",
        "projeto_id": "projeto-1",
        "valor_total": 1000,
        "data_inicio": date(2026, 1, 1),
        "data_fim": date(2026, 12, 31),
        "categorias_despesa": ["materiais"],
        "lancamentos": [],
    }
    base.update(overrides)
    return Orcamento(**base)


def test_valor_total_negativo_retorna_400_com_mensagem_clara():
    response = client.post("/orcamentos", json=payload(valor_total=-100.0))

    assert response.status_code == 400
    assert "negativo" in response.json()["detail"].lower()


def test_periodo_com_data_fim_anterior_a_data_inicio_retorna_400():
    response = client.post(
        "/orcamentos",
        json=payload(data_inicio="2026-06-01", data_fim="2026-01-01"),
    )

    assert response.status_code == 400


def test_payload_valido_cria_orcamento_e_retorna_201():
    response = client.post("/orcamentos", json=payload())

    assert response.status_code == 201
    body = response.json()
    assert body["projeto_id"] == "projeto-1"
    assert body["valor_total"] == 1000.0
    assert "id" in body


def test_saldo_com_lancamentos_aprovados():
    orcamento = orcamento_de_teste(
        lancamentos=[
            Lancamento(valor=200, status=StatusLancamento.APROVADO),
            Lancamento(valor=150, status=StatusLancamento.APROVADO),
        ],
    )

    assert orcamento.saldo == 650


def test_saldo_sem_lancamentos_e_igual_ao_valor_total():
    orcamento = orcamento_de_teste(valor_total=500)

    assert orcamento.saldo == 500


def test_lancamentos_pendentes_e_rejeitados_nao_afetam_saldo():
    orcamento = orcamento_de_teste(
        lancamentos=[
            Lancamento(valor=300, status=StatusLancamento.PENDENTE),
            Lancamento(valor=200, status=StatusLancamento.REJEITADO),
        ],
    )

    assert orcamento.saldo == 1000


def test_saldo_considera_apenas_aprovados_entre_status_mistos():
    orcamento = orcamento_de_teste(
        lancamentos=[
            Lancamento(valor=100, status=StatusLancamento.APROVADO),
            Lancamento(valor=300, status=StatusLancamento.PENDENTE),
            Lancamento(valor=200, status=StatusLancamento.REJEITADO),
        ],
    )

    assert orcamento.saldo == 900


def test_saldo_fica_negativo_quando_aprovados_ultrapassam_o_valor_total():
    orcamento = orcamento_de_teste(
        lancamentos=[
            Lancamento(valor=700, status=StatusLancamento.APROVADO),
            Lancamento(valor=500, status=StatusLancamento.APROVADO),
        ],
    )

    assert orcamento.saldo == -200


def test_get_orcamento_inexistente_retorna_404():
    response = client.get("/orcamentos/nao-existe")

    assert response.status_code == 404


def test_get_orcamento_sem_lancamentos_retorna_saldo_igual_ao_valor_total():
    _orcamentos.append(orcamento_de_teste(id="orcamento-1", valor_total=500))

    response = client.get("/orcamentos/orcamento-1")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "orcamento-1"
    assert body["saldo"] == 500


def test_get_orcamento_com_lancamentos_aprovados_reflete_saldo_calculado():
    _orcamentos.append(
        orcamento_de_teste(
            id="orcamento-1",
            valor_total=1000,
            lancamentos=[
                Lancamento(valor=200, status=StatusLancamento.APROVADO),
                Lancamento(valor=100, status=StatusLancamento.PENDENTE),
            ],
        )
    )

    response = client.get("/orcamentos/orcamento-1")

    assert response.status_code == 200
    assert response.json()["saldo"] == 800


def test_get_orcamentos_do_projeto_retorna_valor_vigencia_e_categorias():
    _orcamentos.append(
        orcamento_de_teste(
            id="orcamento-1",
            projeto_id="projeto-1",
            categorias_despesa=["materiais", "transporte"],
        )
    )
    _orcamentos.append(orcamento_de_teste(id="orcamento-2", projeto_id="projeto-2"))

    response = client.get("/orcamentos/projeto/projeto-1")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["itens"][0]
    assert item["id"] == "orcamento-1"
    assert item["valor_total"] == 1000
    assert item["data_inicio"] == "2026-01-01"
    assert item["data_fim"] == "2026-12-31"
    assert item["categorias_despesa"] == ["materiais", "transporte"]


def test_get_orcamentos_de_projeto_sem_orcamento_retorna_lista_vazia():
    response = client.get("/orcamentos/projeto/projeto-sem-orcamento")

    assert response.status_code == 200
    body = response.json()
    assert body["itens"] == []
    assert body["total"] == 0


def test_get_orcamentos_do_projeto_pagina_historico_mais_recente_primeiro():
    for ano in (2024, 2025, 2026):
        _orcamentos.append(
            orcamento_de_teste(
                id=f"orcamento-{ano}",
                data_inicio=date(ano, 1, 1),
                data_fim=date(ano, 12, 31),
            )
        )

    primeira = client.get("/orcamentos/projeto/projeto-1?pagina=1&tamanho=2").json()
    segunda = client.get("/orcamentos/projeto/projeto-1?pagina=2&tamanho=2").json()

    assert primeira["total"] == 3
    assert [o["id"] for o in primeira["itens"]] == ["orcamento-2026", "orcamento-2025"]
    assert [o["id"] for o in segunda["itens"]] == ["orcamento-2024"]
    assert segunda["pagina"] == 2
    assert segunda["tamanho"] == 2


def test_get_orcamentos_do_projeto_com_pagina_invalida_retorna_422():
    response = client.get("/orcamentos/projeto/projeto-1?pagina=0")

    assert response.status_code == 422
