"""Redesign Financeiro · GET /lancamentos com filtros (substitui a fila da T-18)."""

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


# --- Ordem e filtros ----------------------------------------------------------


def test_lista_todos_mais_antigos_primeiro():
    velho, novo, meio = lancamento(48), lancamento(1), lancamento(5)
    criar_orcamento(velho, novo, meio)

    resposta = listar()

    assert resposta.status_code == 200
    assert ids(resposta) == [velho.id, meio.id, novo.id]


def test_junta_lancamentos_de_todos_os_orcamentos():
    do_a, do_b = lancamento(10), lancamento(20)
    criar_orcamento(do_a, id="orcamento-a", projeto_id="projeto-a")
    criar_orcamento(do_b, id="orcamento-b", projeto_id="projeto-b")

    corpo = listar().json()

    assert [(i["id"], i["orcamento_id"], i["projeto_id"]) for i in corpo] == [
        (do_b.id, "orcamento-b", "projeto-b"),
        (do_a.id, "orcamento-a", "projeto-a"),
    ]


def test_filtra_por_status():
    pendente = lancamento(3)
    aprovado = lancamento(2, StatusLancamento.APROVADO)
    rejeitado = lancamento(1, StatusLancamento.REJEITADO, motivo_rejeicao="x")
    criar_orcamento(pendente, aprovado, rejeitado)

    assert ids(listar({"status": "pendente"})) == [pendente.id]
    assert ids(listar({"status": "aprovado"})) == [aprovado.id]
    assert ids(listar({"status": "rejeitado"})) == [rejeitado.id]


def test_filtra_por_orcamento_e_conciliado():
    a_conciliado = lancamento(1, StatusLancamento.APROVADO, conciliado=True)
    a_aberto = lancamento(2, StatusLancamento.APROVADO)
    b_aberto = lancamento(3, StatusLancamento.APROVADO)
    criar_orcamento(a_conciliado, a_aberto, id="o1")
    criar_orcamento(b_aberto, id="o2")

    assert ids(listar({"orcamento_id": "o1", "conciliado": "false"})) == [a_aberto.id]
    assert ids(listar({"orcamento_id": "o1", "conciliado": "true"})) == [a_conciliado.id]
    assert ids(listar({"orcamento_id": "o3"})) == []


def test_status_invalido_retorna_422():
    criar_orcamento()
    assert listar({"status": "qualquer"}).status_code == 422


# --- Acesso por papel ---------------------------------------------------------


def test_educador_ve_so_os_proprios():
    do_marcos = lancamento(1, autor_id="marcos")
    criar_orcamento(do_marcos, lancamento(2, autor_id="ana"), lancamento(3))

    resposta = listar(papel="educador", usuario="marcos")

    assert ids(resposta) == [do_marcos.id]


def test_educador_sem_usuario_recebe_400():
    criar_orcamento(lancamento(1, autor_id="marcos"))

    resposta = listar(papel="educador")

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Identificação do usuário obrigatória."


def test_educador_nao_escapa_do_filtro_com_meus_false():
    criar_orcamento(lancamento(1, autor_id="ana"))
    assert listar({"meus": "false"}, papel="educador", usuario="marcos").json() == []


def test_meus_true_filtra_pelo_usuario_em_qualquer_papel():
    meu = lancamento(1, autor_id="ana")
    criar_orcamento(meu, lancamento(2, autor_id="marcos"))

    assert ids(listar({"meus": "true"}, papel="coordenacao", usuario="ana")) == [meu.id]
    sem_usuario = listar({"meus": "true"}, papel="coordenacao")
    assert sem_usuario.status_code == 400


@pytest.mark.parametrize("papel", ["coordenacao", "direcao", "voluntario_financeiro"])
def test_outros_papeis_veem_todos(papel):
    criar_orcamento(lancamento(1, autor_id="ana"), lancamento(2, autor_id="marcos"))
    assert len(listar(papel=papel).json()) == 2


@pytest.mark.parametrize("papel", [None, "", "admin"])
def test_papel_ausente_ou_desconhecido_recebe_403(papel):
    criar_orcamento(lancamento(1))
    assert listar(papel=papel).status_code == 403


def test_reverter_aprovacao_limpa_aprovado_em():
    pendente = lancamento(1)
    orcamento = criar_orcamento(pendente)
    orcamento.aprovar_lancamento(pendente.id)
    assert pendente.aprovado_em is not None

    orcamento.reverter_aprovacao(pendente.id)

    assert pendente.aprovado_em is None


def test_sem_token_retorna_401():
    criar_orcamento(lancamento(1))
    assert listar(token=None).status_code == 401


# --- Dados do resumo ----------------------------------------------------------


def test_aprovar_preenche_aprovado_em():
    pendente = lancamento(1)
    criar_orcamento(pendente)
    assert listar().json()[0]["aprovado_em"] is None

    client.patch(f"/lancamentos/{pendente.id}/aprovar", headers=cabecalhos())

    [item] = listar().json()
    assert item["status"] == "aprovado"
    assert item["aprovado_em"] is not None


def test_resumo_traz_projeto_e_comprovante_url():
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

    [item] = listar().json()

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
        "motivo_rejeicao": None,
        "conciliado": False,
        "referencia_extrato": None,
        "comprovante_url": criado["comprovante"]["url"],
        "aprovado_em": None,
    }


def test_lancamento_novo_ganha_criado_em_automaticamente():
    antes = datetime.now(timezone.utc)
    novo = Lancamento(valor=10, status=StatusLancamento.PENDENTE)
    assert antes <= novo.criado_em <= datetime.now(timezone.utc)
