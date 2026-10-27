"""T-13 · US-03 — GET /orcamentos, usado pelo formulário de lançamento."""

from datetime import date

from fastapi.testclient import TestClient

from Financeiro.main import app
from Financeiro.orcamento import Orcamento
from Financeiro.routers.orcamentos import _orcamentos

client = TestClient(app)


def setup_function():
    _orcamentos.clear()


def teardown_function():
    _orcamentos.clear()


def orcamento(id, projeto_id, inicio, fim, categorias=("materiais",)):
    o = Orcamento(
        id=id,
        projeto_id=projeto_id,
        valor_total=1000,
        data_inicio=inicio,
        data_fim=fim,
        categorias_despesa=list(categorias),
    )
    _orcamentos.append(o)
    return o


def test_lista_vazia_quando_nao_ha_orcamentos():
    resposta = client.get("/orcamentos")

    assert resposta.status_code == 200
    assert resposta.json() == []


def test_lista_todos_com_categorias_e_vigencia_ordenados_por_projeto():
    orcamento("o2", "semear", date(2026, 1, 1), date(2026, 12, 31), ["alimentacao", "transporte"])
    orcamento("o1", "casa-convivencia", date(2026, 1, 1), date(2026, 6, 30))

    corpo = client.get("/orcamentos").json()

    assert [o["id"] for o in corpo] == ["o1", "o2"]
    assert corpo[1]["categorias_despesa"] == ["alimentacao", "transporte"]
    assert corpo[1]["data_inicio"] == "2026-01-01"
    assert corpo[1]["data_fim"] == "2026-12-31"
    assert corpo[1]["saldo"] == 1000


def test_filtra_so_os_vigentes_na_data_informada():
    orcamento("encerrado", "a", date(2025, 1, 1), date(2025, 12, 31))
    orcamento("vigente", "b", date(2026, 1, 1), date(2026, 12, 31))
    orcamento("futuro", "c", date(2027, 1, 1), date(2027, 12, 31))

    corpo = client.get("/orcamentos?vigentes_em=2026-10-26").json()

    assert [o["id"] for o in corpo] == ["vigente"]


def test_vigencia_inclui_o_primeiro_e_o_ultimo_dia():
    orcamento("o", "a", date(2026, 1, 1), date(2026, 12, 31))

    assert len(client.get("/orcamentos?vigentes_em=2026-01-01").json()) == 1
    assert len(client.get("/orcamentos?vigentes_em=2026-12-31").json()) == 1
    assert client.get("/orcamentos?vigentes_em=2027-01-01").json() == []


def test_data_invalida_retorna_422():
    assert client.get("/orcamentos?vigentes_em=26/10/2026").status_code == 422


def test_rota_de_detalhe_e_de_projeto_continuam_funcionando():
    orcamento("o1", "semear", date(2026, 1, 1), date(2026, 12, 31))

    assert client.get("/orcamentos/o1").status_code == 200
    assert client.get("/orcamentos/projeto/semear").json()["total"] == 1
