"""T-21 · US-05 — PATCH /lancamentos/{id}/conciliar."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient

from Financeiro.main import app
from Financeiro.orcamento import Lancamento, Orcamento, StatusLancamento
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"

client = TestClient(app)


def cabecalhos(papel="voluntario_financeiro", token=TOKEN):
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


def aprovado(valor=200):
    return Lancamento(valor=valor, status=StatusLancamento.APROVADO)


def conciliar(lancamento_id, corpo=None, **kwargs):
    if corpo is None:
        corpo = {"referencia_extrato": "EXT-2026-10-001"}
    return client.patch(
        f"/lancamentos/{lancamento_id}/conciliar",
        json=corpo,
        headers=cabecalhos(**kwargs),
    )


# --- Critério 1: aprovado e não conciliado -> conciliado = true --------------


def test_conciliar_aprovado_marca_conciliado_e_guarda_referencia():
    lancamento = aprovado(200)
    orcamento = criar_orcamento(lancamento)

    resposta = conciliar(lancamento.id, {"referencia_extrato": "  EXT-2026-10-001  "})

    assert resposta.status_code == 200
    assert resposta.json() == {
        "id": lancamento.id,
        "orcamento_id": "orcamento-1",
        "valor": 200,
        "status": "aprovado",
        "status_descricao": "Aprovado",
        "conciliado": True,
        "referencia_extrato": "EXT-2026-10-001",
    }
    assert lancamento.conciliado is True
    assert lancamento.referencia_extrato == "EXT-2026-10-001"
    assert orcamento.saldo == 800  # conciliar não mexe no saldo


def test_lancamento_novo_nasce_nao_conciliado():
    lancamento = aprovado()
    criar_orcamento(lancamento)

    corpo = client.get(f"/lancamentos/{lancamento.id}", headers=cabecalhos()).json()

    assert corpo["conciliado"] is False
    assert corpo["referencia_extrato"] is None


def test_conciliacao_aparece_ao_consultar_o_lancamento():
    lancamento = aprovado()
    criar_orcamento(lancamento)

    conciliar(lancamento.id)
    corpo = client.get(f"/lancamentos/{lancamento.id}", headers=cabecalhos()).json()

    assert corpo["conciliado"] is True
    assert corpo["referencia_extrato"] == "EXT-2026-10-001"


@pytest.mark.parametrize(
    "corpo", [{}, {"referencia_extrato": None}, {"referencia_extrato": "   "}]
)
def test_sem_referencia_retorna_400(corpo):
    lancamento = aprovado()
    criar_orcamento(lancamento)

    resposta = conciliar(lancamento.id, corpo)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Referência do extrato é obrigatória."
    assert lancamento.conciliado is False


def test_sem_corpo_retorna_400():
    lancamento = aprovado()
    criar_orcamento(lancamento)

    resposta = client.patch(
        f"/lancamentos/{lancamento.id}/conciliar", headers=cabecalhos()
    )

    assert resposta.status_code == 400
    assert lancamento.conciliado is False


def test_referencia_longa_demais_retorna_400():
    lancamento = aprovado()
    criar_orcamento(lancamento)

    resposta = conciliar(lancamento.id, {"referencia_extrato": "x" * 201})

    assert resposta.status_code == 400
    assert lancamento.conciliado is False


def test_lancamento_inexistente_retorna_404():
    criar_orcamento(aprovado())

    resposta = conciliar("nao-existe")

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Lançamento não encontrado"


# --- Critério 2: repetir a ação não duplica ----------------------------------


def test_repetir_com_mesma_referencia_e_idempotente():
    lancamento = aprovado()
    criar_orcamento(lancamento)
    primeira = conciliar(lancamento.id)

    segunda = conciliar(lancamento.id)

    assert segunda.status_code == 200
    assert segunda.json() == primeira.json()
    assert lancamento.referencia_extrato == "EXT-2026-10-001"


def test_repetir_com_outra_referencia_retorna_409_e_mantem_a_original():
    lancamento = aprovado()
    criar_orcamento(lancamento)
    conciliar(lancamento.id)

    resposta = conciliar(lancamento.id, {"referencia_extrato": "EXT-OUTRA"})

    assert resposta.status_code == 409
    assert (
        resposta.json()["detail"]
        == "Lançamento já está conciliado com outra referência do extrato"
    )
    assert lancamento.referencia_extrato == "EXT-2026-10-001"


def test_conciliacoes_simultaneas_com_referencias_diferentes_so_uma_vence():
    lancamento = aprovado()
    criar_orcamento(lancamento)

    with ThreadPoolExecutor(max_workers=10) as executor:
        respostas = list(
            executor.map(
                lambda i: conciliar(lancamento.id, {"referencia_extrato": f"EXT-{i}"}),
                range(10),
            )
        )

    assert sorted(r.status_code for r in respostas) == [200] + [409] * 9
    vencedora = next(r for r in respostas if r.status_code == 200)
    assert lancamento.referencia_extrato == vencedora.json()["referencia_extrato"]


# --- Critério 3: apenas lançamentos aprovados --------------------------------


@pytest.mark.parametrize(
    "status", [StatusLancamento.PENDENTE, StatusLancamento.REJEITADO]
)
def test_lancamento_nao_aprovado_retorna_409(status):
    lancamento = Lancamento(valor=200, status=status)
    criar_orcamento(lancamento)

    resposta = conciliar(lancamento.id)

    assert resposta.status_code == 409
    assert (
        resposta.json()["detail"]
        == "Apenas lançamentos aprovados podem ser conciliados"
    )
    assert lancamento.conciliado is False
    assert lancamento.referencia_extrato is None


def test_fluxo_aprovar_e_depois_conciliar():
    lancamento = Lancamento(valor=200, status=StatusLancamento.PENDENTE)
    criar_orcamento(lancamento)
    assert conciliar(lancamento.id).status_code == 409

    client.patch(
        f"/lancamentos/{lancamento.id}/aprovar",
        headers=cabecalhos(papel="coordenacao"),
    )

    assert conciliar(lancamento.id).status_code == 200
    assert lancamento.conciliado is True


# --- Permissões: ação do Voluntário Financeiro -------------------------------


@pytest.mark.parametrize("papel", ["voluntario_financeiro", " Voluntario_Financeiro "])
def test_voluntario_financeiro_pode_conciliar(papel):
    lancamento = aprovado()
    criar_orcamento(lancamento)

    assert conciliar(lancamento.id, papel=papel).status_code == 200


@pytest.mark.parametrize(
    "papel", ["coordenacao", "direcao", "educador", "admin", "", None]
)
def test_outros_papeis_recebem_403_e_nada_muda(papel):
    lancamento = aprovado()
    criar_orcamento(lancamento)

    resposta = conciliar(lancamento.id, papel=papel)

    assert resposta.status_code == 403
    assert lancamento.conciliado is False


def test_sem_token_retorna_401():
    lancamento = aprovado()
    criar_orcamento(lancamento)

    assert conciliar(lancamento.id, token=None).status_code == 401
    assert lancamento.conciliado is False


def test_papel_sem_permissao_nao_descobre_se_lancamento_existe():
    criar_orcamento(aprovado())

    assert conciliar("nao-existe", papel="educador").status_code == 403
