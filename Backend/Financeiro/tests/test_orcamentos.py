from fastapi.testclient import TestClient

from main import app, _orcamentos

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
