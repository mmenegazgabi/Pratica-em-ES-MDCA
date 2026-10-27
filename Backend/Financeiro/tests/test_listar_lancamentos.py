"""T-18 · US-04 — GET /lancamentos (fila de aprovação da Coordenação)."""

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from Financeiro.comprovantes import ArmazenamentoEmMemoria
from Financeiro.main import app
from Financeiro.orcamento import Lancamento, Orcamento, StatusLancamento
from Financeiro.routers.comprovantes import obter_armazenamento
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
AGORA = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)

client = TestClient(app)


def cabecalhos(papel="coordenacao", token=TOKEN, usuario=None):
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if papel is not None:
        headers["X-Papel-Usuario"] = papel
    if usuario is not None:
        headers["X-Usuario-Id"] = usuario
    return headers


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    _orcamentos.clear()
    app.dependency_overrides[obter_armazenamento] = lambda: ArmazenamentoEmMemoria()
    yield
    app.dependency_overrides.clear()
    _orcamentos.clear()


def criar_orcamento(*lancamentos, id="orcamento-1", projeto_id="projeto-1"):
    orcamento = Orcamento(
        id=id,
        projeto_id=projeto_id,
        valor_total=10000,
        data_inicio=date(2026, 1, 1),
        data_fim=date(2026, 12, 31),
        categorias_despesa=["materiais"],
        lancamentos=list(lancamentos),
    )
    _orcamentos.append(orcamento)
    return orcamento


def lancamento(horas_atras, status=StatusLancamento.PENDENTE, **campos):
    return Lancamento(
        valor=campos.pop("valor", 100),
        status=status,
        criado_em=AGORA - timedelta(hours=horas_atras),
        **campos,
    )


def listar(params=None, **kwargs):
    return client.get("/lancamentos", params=params, headers=cabecalhos(**kwargs))


def ids(resposta):
    return [item["id"] for item in resposta.json()]


# --- Fila de pendentes, mais antigos primeiro --------------------------------


def test_lista_pendentes_do_mais_antigo_para_o_mais_novo():
    novo, antigo, meio = lancamento(1), lancamento(48), lancamento(5)
    criar_orcamento(novo, antigo, meio)

    resposta = listar({"status": "pendente"})

    assert resposta.status_code == 200
    assert ids(resposta) == [antigo.id, meio.id, novo.id]


def test_ordena_por_quando_foi_lancado_e_nao_pela_data_da_despesa():
    # Despesa de janeiro lançada hoje fica depois de despesa de outubro
    # lançada ontem: a fila é por tempo de espera.
    retroativo = lancamento(1, data_despesa=date(2026, 1, 5))
    de_ontem = lancamento(24, data_despesa=date(2026, 10, 20))
    criar_orcamento(retroativo, de_ontem)

    assert ids(listar({"status": "pendente"})) == [de_ontem.id, retroativo.id]


def test_junta_pendentes_de_todos_os_orcamentos():
    do_a = lancamento(10)
    do_b = lancamento(20)
    criar_orcamento(do_a, id="orcamento-a", projeto_id="projeto-a")
    criar_orcamento(do_b, id="orcamento-b", projeto_id="projeto-b")

    corpo = listar({"status": "pendente"}).json()

    assert [(i["id"], i["orcamento_id"], i["projeto_id"]) for i in corpo] == [
        (do_b.id, "orcamento-b", "projeto-b"),
        (do_a.id, "orcamento-a", "projeto-a"),
    ]


def test_filtro_pendente_deixa_de_fora_aprovados_e_rejeitados():
    pendente = lancamento(3)
    criar_orcamento(
        pendente,
        lancamento(5, StatusLancamento.APROVADO),
        lancamento(4, StatusLancamento.REJEITADO, motivo_rejeicao="x"),
    )

    assert ids(listar({"status": "pendente"})) == [pendente.id]


def test_sem_filtro_lista_todos_os_status():
    criar_orcamento(
        lancamento(3),
        lancamento(2, StatusLancamento.APROVADO),
        lancamento(1, StatusLancamento.REJEITADO, motivo_rejeicao="x"),
    )

    corpo = listar().json()

    assert [i["status"] for i in corpo] == ["pendente", "aprovado", "rejeitado"]


@pytest.mark.parametrize("status", ["aprovado", "rejeitado"])
def test_filtra_por_outros_status(status):
    alvo = lancamento(1, StatusLancamento(status), motivo_rejeicao="x")
    criar_orcamento(alvo, lancamento(2))

    assert ids(listar({"status": status})) == [alvo.id]


def test_status_invalido_retorna_422():
    criar_orcamento()
    assert listar({"status": "qualquer"}).status_code == 422


def test_sem_pendentes_retorna_lista_vazia():
    criar_orcamento(lancamento(1, StatusLancamento.APROVADO))
    assert listar({"status": "pendente"}).json() == []


def test_lancamento_aprovado_sai_da_fila():
    primeiro, segundo = lancamento(2), lancamento(1)
    criar_orcamento(primeiro, segundo)

    client.patch(f"/lancamentos/{primeiro.id}/aprovar", headers=cabecalhos())

    assert ids(listar({"status": "pendente"})) == [segundo.id]


# --- Dados que o painel precisa ---------------------------------------------


def test_item_traz_os_dados_para_o_painel():
    criar_orcamento()
    criado = client.post(
        "/lancamentos",
        data={
            "orcamento_id": "orcamento-1",
            "valor": "80.5",
            "descricao": "Lanche da oficina",
            "categoria": "materiais",
            "data_despesa": "2026-10-10",
        },
        files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")},
        headers=cabecalhos(papel="educador", usuario="educadora-ana"),
    ).json()

    [item] = listar({"status": "pendente"}).json()

    assert item.pop("criado_em")
    assert item == {
        "id": criado["id"],
        "orcamento_id": "orcamento-1",
        "projeto_id": "projeto-1",
        "valor": 80.5,
        "descricao": "Lanche da oficina",
        "categoria": "materiais",
        "data_despesa": "2026-10-10",
        "status": "pendente",
        "status_descricao": "Pendente de aprovação",
        "autor_id": "educadora-ana",
        "comprovante_url": criado["comprovante"]["url"],
    }


def test_lancamento_novo_ganha_criado_em_automaticamente():
    antes = datetime.now(timezone.utc)
    novo = Lancamento(valor=10, status=StatusLancamento.PENDENTE)
    assert antes <= novo.criado_em <= datetime.now(timezone.utc)


# --- Papéis e autenticação ---------------------------------------------------


@pytest.mark.parametrize("papel", ["coordenacao", "direcao"])
def test_coordenacao_e_direcao_veem_a_fila(papel):
    criar_orcamento(lancamento(1))
    assert listar({"status": "pendente"}, papel=papel).status_code == 200


@pytest.mark.parametrize("papel", ["educador", "voluntario_financeiro", "", None])
def test_outros_papeis_recebem_403(papel):
    criar_orcamento(lancamento(1))
    assert listar({"status": "pendente"}, papel=papel).status_code == 403


def test_sem_token_retorna_401():
    criar_orcamento(lancamento(1))
    assert listar({"status": "pendente"}, token=None).status_code == 401
