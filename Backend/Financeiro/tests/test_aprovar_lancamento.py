"""T-15 · US-04 — PATCH /lancamentos/{id}/aprovar."""

from concurrent.futures import ThreadPoolExecutor
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
        categorias_despesa=["materiais"],
        lancamentos=list(lancamentos),
    )
    _orcamentos.append(orcamento)
    return orcamento


def pendente(valor=200):
    return Lancamento(valor=valor, status=StatusLancamento.PENDENTE)


def aprovar(lancamento_id, **kwargs):
    return client.patch(
        f"/lancamentos/{lancamento_id}/aprovar", headers=cabecalhos(**kwargs)
    )


# --- Critério 1: pendente -> aprovado, debita do saldo -----------------------


def test_aprovar_pendente_muda_status_e_debita_saldo():
    lancamento = pendente(200)
    orcamento = criar_orcamento(lancamento)

    resposta = aprovar(lancamento.id)

    assert resposta.status_code == 200
    assert resposta.json() == {
        "id": lancamento.id,
        "orcamento_id": "orcamento-1",
        "valor": 200,
        "status": "aprovado",
        "status_descricao": "Aprovado",
        "saldo_orcamento": 800,
    }
    assert lancamento.status == StatusLancamento.APROVADO
    assert orcamento.saldo == 800


def test_aprovacao_reflete_no_saldo_do_get_orcamento():
    lancamento = pendente(250)
    criar_orcamento(lancamento)

    aprovar(lancamento.id)

    detalhe = client.get("/orcamentos/orcamento-1").json()
    assert detalhe["saldo"] == 750
    assert detalhe["realizado"] == 250


def test_aprovar_um_lancamento_nao_mexe_nos_outros():
    alvo, outro = pendente(100), pendente(300)
    orcamento = criar_orcamento(alvo, outro)

    aprovar(alvo.id)

    assert outro.status == StatusLancamento.PENDENTE
    assert orcamento.saldo == 900


def test_lancamento_inexistente_retorna_404():
    criar_orcamento(pendente())

    resposta = aprovar("nao-existe")

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Lançamento não encontrado"


# --- Critério 2: transição de estado inválida --------------------------------


def test_aprovar_lancamento_ja_aprovado_retorna_409_sem_debitar_de_novo():
    lancamento = pendente(200)
    orcamento = criar_orcamento(lancamento)
    aprovar(lancamento.id)

    resposta = aprovar(lancamento.id)

    assert resposta.status_code == 409
    assert resposta.json()["detail"] == "Lançamento já está aprovado"
    assert orcamento.saldo == 800


def test_aprovar_lancamento_rejeitado_retorna_409_sem_alterar_saldo():
    lancamento = Lancamento(valor=200, status=StatusLancamento.REJEITADO)
    orcamento = criar_orcamento(lancamento)

    resposta = aprovar(lancamento.id)

    assert resposta.status_code == 409
    assert lancamento.status == StatusLancamento.REJEITADO
    assert orcamento.saldo == 1000


def test_aprovacoes_simultaneas_do_mesmo_lancamento_debitam_uma_unica_vez():
    lancamento = pendente(200)
    orcamento = criar_orcamento(lancamento)

    with ThreadPoolExecutor(max_workers=10) as executor:
        respostas = list(executor.map(lambda _: aprovar(lancamento.id), range(10)))

    assert sorted(r.status_code for r in respostas) == [200] + [409] * 9
    assert orcamento.saldo == 800


# --- Critério 3: apenas Coordenação ou Direção -------------------------------


@pytest.mark.parametrize("papel", ["coordenacao", "direcao", " Direcao "])
def test_coordenacao_e_direcao_podem_aprovar(papel):
    lancamento = pendente()
    criar_orcamento(lancamento)

    assert aprovar(lancamento.id, papel=papel).status_code == 200


@pytest.mark.parametrize(
    "papel", ["educador", "voluntario_financeiro", "admin", "", None]
)
def test_outros_papeis_recebem_403_e_nada_muda(papel):
    lancamento = pendente()
    orcamento = criar_orcamento(lancamento)

    resposta = aprovar(lancamento.id, papel=papel)

    assert resposta.status_code == 403
    assert lancamento.status == StatusLancamento.PENDENTE
    assert orcamento.saldo == 1000


def test_sem_token_retorna_401_mesmo_com_papel_valido():
    lancamento = pendente()
    criar_orcamento(lancamento)

    resposta = aprovar(lancamento.id, token=None)

    assert resposta.status_code == 401
    assert lancamento.status == StatusLancamento.PENDENTE


def test_token_errado_retorna_401():
    lancamento = pendente()
    criar_orcamento(lancamento)

    assert aprovar(lancamento.id, token="errado").status_code == 401


def test_papel_sem_permissao_nao_descobre_se_lancamento_existe():
    criar_orcamento(pendente())

    assert aprovar("nao-existe", papel="educador").status_code == 403
