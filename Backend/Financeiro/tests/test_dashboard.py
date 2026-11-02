"""T-29 · US-07 — GET /dashboard/projetos, orçado x realizado da Diretoria."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from Financeiro.main import app
from Financeiro.orcamento import Lancamento, Orcamento, StatusLancamento
from Financeiro.projetos import StatusProjeto, _projetos, registrar_projeto
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"

client = TestClient(app)


def cabecalhos(papel="direcao"):
    return {"Authorization": f"Bearer {TOKEN}", "X-Papel-Usuario": papel}


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    _orcamentos.clear()
    _projetos.clear()
    yield
    _orcamentos.clear()
    _projetos.clear()


def aprovado(valor, dia):
    return Lancamento(valor=valor, status=StatusLancamento.APROVADO, data_despesa=dia)


def orcamento(projeto, valor_total, inicio, fim, lancamentos=()):
    o = Orcamento(
        id=f"orc-{len(_orcamentos) + 1}",
        projeto_id=projeto.id,
        valor_total=valor_total,
        data_inicio=inicio,
        data_fim=fim,
        categorias_despesa=["materiais"],
        lancamentos=list(lancamentos),
    )
    _orcamentos.append(o)
    return o


def consultar(**filtros):
    resposta = client.get("/dashboard/projetos", params=filtros, headers=cabecalhos())
    assert resposta.status_code == 200
    return {p["nome"]: p for p in resposta.json()}


def test_varios_projetos_numa_unica_resposta_com_orcado_realizado_e_saldo():
    semear = registrar_projeto("Semear")
    oficina = registrar_projeto("Oficina")
    orcamento(semear, 1000, date(2026, 1, 1), date(2026, 12, 31), [aprovado(250.10, date(2026, 3, 1))])
    orcamento(semear, 500, date(2026, 1, 1), date(2026, 6, 30), [aprovado(0.1, date(2026, 2, 1)), aprovado(0.2, date(2026, 2, 2))])
    orcamento(oficina, 2000, date(2026, 1, 1), date(2026, 12, 31))

    corpo = consultar()

    assert corpo["Semear"] == {
        "projeto_id": semear.id,
        "nome": "Semear",
        "status": "ativo",
        "orcado": 1500.0,
        "realizado": 250.4,
        "saldo": 1249.6,
    }
    assert corpo["Oficina"]["orcado"] == 2000.0
    assert corpo["Oficina"]["realizado"] == 0.0
    assert corpo["Oficina"]["saldo"] == 2000.0


def test_projeto_sem_orcamento_aparece_zerado():
    novo = registrar_projeto("Novo")

    assert consultar()["Novo"] == {
        "projeto_id": novo.id,
        "nome": "Novo",
        "status": "ativo",
        "orcado": 0.0,
        "realizado": 0.0,
        "saldo": 0.0,
    }


def test_so_lancamentos_aprovados_entram_no_realizado():
    projeto = registrar_projeto("Semear")
    orcamento(
        projeto,
        1000,
        date(2026, 1, 1),
        date(2026, 12, 31),
        [
            aprovado(100, date(2026, 3, 1)),
            Lancamento(valor=200, status=StatusLancamento.PENDENTE, data_despesa=date(2026, 3, 1)),
            Lancamento(valor=300, status=StatusLancamento.REJEITADO, data_despesa=date(2026, 3, 1), motivo_rejeicao="x"),
        ],
    )

    assert consultar()["Semear"]["realizado"] == 100.0


def test_filtro_de_periodo_considera_so_lancamentos_e_orcamentos_do_periodo():
    projeto = registrar_projeto("Semear")
    orcamento(
        projeto,
        1000,
        date(2026, 1, 1),
        date(2026, 6, 30),
        [
            aprovado(100, date(2026, 1, 31)),
            aprovado(200, date(2026, 2, 1)),
            aprovado(300, date(2026, 3, 31)),
            aprovado(400, date(2026, 4, 1)),
            Lancamento(valor=500, status=StatusLancamento.APROVADO),
        ],
    )
    orcamento(projeto, 800, date(2026, 7, 1), date(2026, 12, 31))

    semear = consultar(data_inicio="2026-02-01", data_fim="2026-03-31")["Semear"]

    assert semear["orcado"] == 1000.0
    assert semear["realizado"] == 500.0
    assert semear["saldo"] == 500.0


def test_filtro_de_periodo_com_so_uma_das_pontas():
    projeto = registrar_projeto("Semear")
    orcamento(projeto, 1000, date(2025, 1, 1), date(2025, 12, 31), [aprovado(100, date(2025, 5, 1))])
    orcamento(projeto, 800, date(2026, 1, 1), date(2026, 12, 31), [aprovado(50, date(2026, 5, 1))])

    assert consultar(data_inicio="2026-01-01")["Semear"]["orcado"] == 800.0
    assert consultar(data_inicio="2026-01-01")["Semear"]["realizado"] == 50.0
    assert consultar(data_fim="2025-12-31")["Semear"]["orcado"] == 1000.0
    assert consultar(data_fim="2025-12-31")["Semear"]["realizado"] == 100.0


def test_periodo_invertido_422():
    resposta = client.get(
        "/dashboard/projetos",
        params={"data_inicio": "2026-12-31", "data_fim": "2026-01-01"},
        headers=cabecalhos(),
    )

    assert resposta.status_code == 422


@pytest.mark.parametrize("status, esperados", [("ativo", {"Semear"}), ("encerrado", {"Antigo"})])
def test_filtro_de_status_mostra_so_os_projetos_correspondentes(status, esperados):
    registrar_projeto("Semear")
    antigo = registrar_projeto("Antigo")
    antigo.status = StatusProjeto.ENCERRADO

    assert set(consultar(status=status)) == esperados
    assert set(consultar()) == {"Semear", "Antigo"}


def test_status_invalido_422():
    resposta = client.get("/dashboard/projetos", params={"status": "pausado"}, headers=cabecalhos())

    assert resposta.status_code == 422


@pytest.mark.parametrize("papel", ["coordenacao", "educador", "voluntario_financeiro"])
def test_outros_papeis_403(papel):
    assert client.get("/dashboard/projetos", headers=cabecalhos(papel)).status_code == 403


def test_sem_autenticacao_401():
    assert client.get("/dashboard/projetos").status_code == 401
