"""T-16 · US-04 — PATCH /lancamentos/{id}/rejeitar (motivo obrigatório)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient

from Financeiro.comprovantes import ArmazenamentoEmMemoria
from Financeiro.main import app
from Financeiro.orcamento import (
    AprovacaoInvalida,
    Lancamento,
    LancamentoInvalido,
    Orcamento,
    StatusLancamento,
)
from Financeiro.routers.comprovantes import obter_armazenamento
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64

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
    app.dependency_overrides[obter_armazenamento] = lambda: ArmazenamentoEmMemoria()
    yield
    app.dependency_overrides.clear()
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


def rejeitar(lancamento_id, corpo=..., **kwargs):
    url = f"/lancamentos/{lancamento_id}/rejeitar"
    if corpo is ...:
        return client.patch(url, headers=cabecalhos(**kwargs))
    return client.patch(url, json=corpo, headers=cabecalhos(**kwargs))


def consultar(lancamento_id, papel="educador"):
    return client.get(f"/lancamentos/{lancamento_id}", headers=cabecalhos(papel=papel))


# --- Critério 1: pendente rejeitado sem motivo → 400 ------------------------


@pytest.mark.parametrize(
    "corpo",
    [..., {}, {"motivo": None}, {"motivo": ""}, {"motivo": "   "}],
    ids=["sem-corpo", "corpo-vazio", "motivo-null", "motivo-vazio", "motivo-so-espacos"],
)
def test_rejeitar_pendente_sem_motivo_retorna_400_e_nada_muda(corpo):
    lancamento = pendente(200)
    orcamento = criar_orcamento(lancamento)

    resposta = rejeitar(lancamento.id, corpo)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Motivo da rejeição é obrigatório."
    assert lancamento.status == StatusLancamento.PENDENTE
    assert lancamento.motivo_rejeicao is None
    assert orcamento.saldo == 1000


def test_motivo_maior_que_500_caracteres_retorna_400():
    lancamento = pendente()
    criar_orcamento(lancamento)

    resposta = rejeitar(lancamento.id, {"motivo": "x" * 501})

    assert resposta.status_code == 400
    assert lancamento.status == StatusLancamento.PENDENTE


# --- Critério 2: com motivo → "Rejeitado" e motivo visível -----------------


def test_rejeitar_pendente_com_motivo_muda_status_e_guarda_motivo():
    lancamento = pendente(200)
    criar_orcamento(lancamento)

    resposta = rejeitar(lancamento.id, {"motivo": "  Nota fiscal ilegível na foto.  "})

    assert resposta.status_code == 200
    assert resposta.json() == {
        "id": lancamento.id,
        "orcamento_id": "orcamento-1",
        "valor": 200,
        "status": "rejeitado",
        "status_descricao": "Rejeitado",
        "motivo_rejeicao": "Nota fiscal ilegível na foto.",
        "saldo_orcamento": 1000,
    }
    assert lancamento.status == StatusLancamento.REJEITADO
    assert lancamento.motivo_rejeicao == "Nota fiscal ilegível na foto."


def test_quem_lancou_ve_o_motivo_ao_consultar_o_lancamento():
    # Fluxo real: o educador lança pela T-12, a coordenação rejeita,
    # o educador consulta e vê o motivo.
    criar_orcamento()
    criado = client.post(
        "/lancamentos",
        data={
            "orcamento_id": "orcamento-1",
            "valor": "150",
            "descricao": "Lanche da oficina",
            "categoria": "materiais",
            "data_despesa": "2026-10-10",
        },
        files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")},
        headers=cabecalhos(papel="educador"),
    ).json()
    rejeitar(criado["id"], {"motivo": "Valor acima do limite da categoria."})

    resposta = consultar(criado["id"], papel="educador")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "rejeitado"
    assert corpo["status_descricao"] == "Rejeitado"
    assert corpo["motivo_rejeicao"] == "Valor acima do limite da categoria."
    assert corpo["descricao"] == "Lanche da oficina"
    assert corpo["comprovante_url"] == criado["comprovante"]["url"]


def test_consulta_de_pendente_nao_tem_motivo():
    lancamento = pendente()
    criar_orcamento(lancamento)

    corpo = consultar(lancamento.id).json()

    assert corpo["status_descricao"] == "Pendente de aprovação"
    assert corpo["motivo_rejeicao"] is None


@pytest.mark.parametrize("papel", ["coordenacao", "direcao", "educador", "voluntario_financeiro", None])
def test_qualquer_usuario_autenticado_consulta_o_lancamento(papel):
    lancamento = pendente()
    criar_orcamento(lancamento)

    assert consultar(lancamento.id, papel=papel).status_code == 200


def test_consultar_sem_token_retorna_401():
    lancamento = pendente()
    criar_orcamento(lancamento)

    assert client.get(f"/lancamentos/{lancamento.id}").status_code == 401


# --- Critério 3: rejeitado não afeta o saldo --------------------------------


def test_rejeitar_nao_altera_saldo_e_get_orcamento_confirma():
    lancamento = pendente(300)
    criar_orcamento(lancamento)

    rejeitar(lancamento.id, {"motivo": "Comprovante não confere."})

    assert client.get("/orcamentos/orcamento-1").json()["saldo"] == 1000


def test_saldo_considera_so_o_aprovado_quando_outro_e_rejeitado():
    aprovado, rejeitado = pendente(200), pendente(500)
    orcamento = criar_orcamento(aprovado, rejeitado)

    client.patch(f"/lancamentos/{aprovado.id}/aprovar", headers=cabecalhos())
    resposta = rejeitar(rejeitado.id, {"motivo": "Fora do escopo do projeto."})

    assert resposta.json()["saldo_orcamento"] == 800
    assert orcamento.saldo == 800


def test_lancamento_rejeitado_nao_pode_ser_aprovado_depois():
    lancamento = pendente(300)
    orcamento = criar_orcamento(lancamento)
    rejeitar(lancamento.id, {"motivo": "Duplicado."})

    resposta = client.patch(f"/lancamentos/{lancamento.id}/aprovar", headers=cabecalhos())

    assert resposta.status_code == 409
    assert lancamento.status == StatusLancamento.REJEITADO
    assert orcamento.saldo == 1000


# --- Só pendente pode ser rejeitado -----------------------------------------


def test_rejeitar_lancamento_aprovado_retorna_409_e_saldo_continua_debitado():
    lancamento = Lancamento(valor=300, status=StatusLancamento.APROVADO)
    orcamento = criar_orcamento(lancamento)

    resposta = rejeitar(lancamento.id, {"motivo": "Mudei de ideia."})

    assert resposta.status_code == 409
    assert lancamento.status == StatusLancamento.APROVADO
    assert orcamento.saldo == 700


def test_rejeitar_de_novo_retorna_409_e_mantem_o_motivo_original():
    lancamento = pendente()
    criar_orcamento(lancamento)
    rejeitar(lancamento.id, {"motivo": "Primeiro motivo."})

    resposta = rejeitar(lancamento.id, {"motivo": "Segundo motivo."})

    assert resposta.status_code == 409
    assert lancamento.motivo_rejeicao == "Primeiro motivo."


def test_rejeicoes_simultaneas_do_mesmo_lancamento_so_uma_vence():
    lancamento = pendente()
    criar_orcamento(lancamento)

    with ThreadPoolExecutor(max_workers=8) as executor:
        respostas = list(
            executor.map(
                lambda i: rejeitar(lancamento.id, {"motivo": f"Motivo {i}"}), range(8)
            )
        )

    codigos = sorted(r.status_code for r in respostas)
    assert codigos.count(200) == 1
    assert codigos.count(409) == 7


def test_lancamento_inexistente_retorna_404():
    criar_orcamento()

    assert rejeitar("nao-existe", {"motivo": "Qualquer."}).status_code == 404
    assert consultar("nao-existe").status_code == 404


# --- Papéis e autenticação (mesmo padrão da T-15) ---------------------------


@pytest.mark.parametrize("papel", ["coordenacao", "direcao", "COORDENACAO", " direcao "])
def test_coordenacao_e_direcao_podem_rejeitar(papel):
    lancamento = pendente()
    criar_orcamento(lancamento)

    assert rejeitar(lancamento.id, {"motivo": "Ok."}, papel=papel).status_code == 200


@pytest.mark.parametrize("papel", ["educador", "voluntario_financeiro", "admin", "", None])
def test_outros_papeis_recebem_403_e_nada_muda(papel):
    lancamento = pendente()
    criar_orcamento(lancamento)

    resposta = rejeitar(lancamento.id, {"motivo": "Tentativa."}, papel=papel)

    assert resposta.status_code == 403
    assert lancamento.status == StatusLancamento.PENDENTE
    assert lancamento.motivo_rejeicao is None


def test_sem_token_retorna_401_mesmo_com_papel_valido():
    lancamento = pendente()
    criar_orcamento(lancamento)

    resposta = rejeitar(lancamento.id, {"motivo": "Sem token."}, token=None)

    assert resposta.status_code == 401
    assert lancamento.status == StatusLancamento.PENDENTE


def test_papel_sem_permissao_nao_descobre_se_lancamento_existe():
    criar_orcamento()

    resposta = rejeitar("nao-existe", {"motivo": "x"}, papel="educador")

    assert resposta.status_code == 403


# --- Regra de domínio -------------------------------------------------------


def test_dominio_rejeitar_guarda_motivo_e_nao_altera_saldo():
    lancamento = pendente(300)
    orcamento = criar_orcamento(lancamento)

    devolvido = orcamento.rejeitar_lancamento(lancamento.id, "Comprovante ilegível.")

    assert devolvido is lancamento
    assert lancamento.status == StatusLancamento.REJEITADO
    assert lancamento.motivo_rejeicao == "Comprovante ilegível."
    assert orcamento.saldo == 1000


def test_dominio_exige_motivo():
    lancamento = pendente()
    orcamento = criar_orcamento(lancamento)

    with pytest.raises(LancamentoInvalido):
        orcamento.rejeitar_lancamento(lancamento.id, "   ")
    assert lancamento.status == StatusLancamento.PENDENTE


def test_dominio_nao_rejeita_aprovado():
    lancamento = Lancamento(valor=300, status=StatusLancamento.APROVADO)
    orcamento = criar_orcamento(lancamento)

    with pytest.raises(AprovacaoInvalida):
        orcamento.rejeitar_lancamento(lancamento.id, "Motivo.")
    assert orcamento.saldo == 700
