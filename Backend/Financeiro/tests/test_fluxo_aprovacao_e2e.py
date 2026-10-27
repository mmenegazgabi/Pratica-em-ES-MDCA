"""T-19 · US-04 — Fluxo completo: lançamento → aprovação/rejeição →
notificação → saldo.

Diferente dos testes de cada rota, aqui tudo passa só pela API, do jeito
que o frontend faz: a coordenação cria o orçamento, o educador lança com
comprovante, a coordenação vê a fila e decide, e o educador recebe a
notificação. O saldo é conferido pelo GET /orcamentos/{id}.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from Financeiro.comprovantes import ArmazenamentoEmMemoria
from Financeiro.main import app
from Financeiro.notificacoes import caixa_de_notificacoes
from Financeiro.routers.comprovantes import obter_armazenamento
from Financeiro.projetos import _projetos, registrar_projeto
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64

client = TestClient(app)


def como(papel, usuario=None):
    headers = {"Authorization": f"Bearer {TOKEN}", "X-Papel-Usuario": papel}
    if usuario:
        headers["X-Usuario-Id"] = usuario
    return headers


COORDENACAO = como("coordenacao", "coordenadora-luana")


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    _orcamentos.clear()
    _projetos.clear()
    caixa_de_notificacoes.limpar()
    app.dependency_overrides[obter_armazenamento] = lambda: ArmazenamentoEmMemoria()
    yield
    app.dependency_overrides.clear()
    _orcamentos.clear()
    _projetos.clear()
    caixa_de_notificacoes.limpar()


# --- Passos do fluxo, como o frontend chama a API ---------------------------


def criar_orcamento(valor_total=1000):
    projeto = registrar_projeto(f"Oficina de Arte {len(_projetos)}")
    resposta = client.post(
        "/orcamentos",
        json={
            "projeto_id": projeto.id,
            "valor_total": valor_total,
            "data_inicio": "2026-01-01",
            "data_fim": "2026-12-31",
            "categorias_despesa": ["materiais", "alimentacao"],
        },
    )
    assert resposta.status_code == 201
    return resposta.json()["id"]


def lancar(orcamento_id, valor, autor="educadora-ana", descricao="Tintas"):
    resposta = client.post(
        "/lancamentos",
        data={
            "orcamento_id": orcamento_id,
            "valor": str(valor),
            "descricao": descricao,
            "categoria": "materiais",
            "data_despesa": "2026-10-10",
        },
        files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")},
        headers=como("educador", autor),
    )
    assert resposta.status_code == 201
    assert resposta.json()["status"] == "pendente"
    return resposta.json()["id"]


def fila_de_pendentes():
    resposta = client.get("/lancamentos", params={"status": "pendente"}, headers=COORDENACAO)
    assert resposta.status_code == 200
    return [item["id"] for item in resposta.json()]


def aprovar(lancamento_id):
    return client.patch(f"/lancamentos/{lancamento_id}/aprovar", headers=COORDENACAO)


def rejeitar(lancamento_id, corpo):
    return client.patch(
        f"/lancamentos/{lancamento_id}/rejeitar", json=corpo, headers=COORDENACAO
    )


def saldo(orcamento_id):
    return client.get(f"/orcamentos/{orcamento_id}").json()["saldo"]


def notificacoes(usuario="educadora-ana"):
    resposta = client.get("/notificacoes", headers=como("educador", usuario))
    assert resposta.status_code == 200
    return resposta.json()


def lancamento(lancamento_id):
    return client.get(f"/lancamentos/{lancamento_id}", headers=como("educador")).json()


# --- Critério 1: aprovação completa (saldo debitado, notificação enviada) ---


def test_fluxo_de_aprovacao_completo():
    orcamento_id = criar_orcamento(1000)
    lancamento_id = lancar(orcamento_id, 300, descricao="Tintas para a oficina")

    # Pendente não mexe no saldo e aparece na fila da coordenação
    assert saldo(orcamento_id) == 1000
    assert fila_de_pendentes() == [lancamento_id]
    assert notificacoes() == []

    resposta = aprovar(lancamento_id)

    assert resposta.status_code == 200
    assert resposta.json()["status_descricao"] == "Aprovado"
    assert resposta.json()["saldo_orcamento"] == 700

    # Saldo debitado e indicador de consumo atualizado
    orcamento = client.get(f"/orcamentos/{orcamento_id}").json()
    assert orcamento["saldo"] == 700
    assert orcamento["realizado"] == 300
    assert orcamento["percentual_consumido"] == 30

    # Notificação enviada ao autor
    [notificacao] = notificacoes()
    assert notificacao["lancamento_id"] == lancamento_id
    assert notificacao["tipo"] == "lancamento_aprovado"
    assert notificacao["mensagem"] == (
        'Seu lançamento "Tintas para a oficina" de R$ 300,00 foi aprovado.'
    )
    assert notificacao["lida"] is False

    # Saiu da fila e o autor vê o novo status
    assert fila_de_pendentes() == []
    assert lancamento(lancamento_id)["status_descricao"] == "Aprovado"


# --- Critério 2: rejeição completa (motivo, notificação, saldo intacto) ----


def test_fluxo_de_rejeicao_completo():
    orcamento_id = criar_orcamento(1000)
    lancamento_id = lancar(orcamento_id, 250, descricao="Lanche")

    # Sem motivo é bloqueado e nada acontece
    for corpo in [{}, {"motivo": ""}, {"motivo": "   "}]:
        resposta = rejeitar(lancamento_id, corpo)
        assert resposta.status_code == 400
        assert resposta.json()["detail"] == "Motivo da rejeição é obrigatório."
    assert fila_de_pendentes() == [lancamento_id]
    assert notificacoes() == []

    resposta = rejeitar(lancamento_id, {"motivo": "Nota fiscal ilegível."})

    assert resposta.status_code == 200
    assert resposta.json()["status_descricao"] == "Rejeitado"
    assert resposta.json()["saldo_orcamento"] == 1000

    # Saldo intacto
    assert saldo(orcamento_id) == 1000

    # Notificação enviada com o motivo
    [notificacao] = notificacoes()
    assert notificacao["tipo"] == "lancamento_rejeitado"
    assert notificacao["motivo"] == "Nota fiscal ilegível."
    assert notificacao["mensagem"].endswith("Motivo: Nota fiscal ilegível.")

    # Saiu da fila e o autor vê o motivo no lançamento
    assert fila_de_pendentes() == []
    detalhe = lancamento(lancamento_id)
    assert detalhe["status_descricao"] == "Rejeitado"
    assert detalhe["motivo_rejeicao"] == "Nota fiscal ilegível."


def test_rejeitado_nao_pode_ser_aprovado_depois():
    orcamento_id = criar_orcamento(1000)
    lancamento_id = lancar(orcamento_id, 250)
    rejeitar(lancamento_id, {"motivo": "Duplicado."})

    assert aprovar(lancamento_id).status_code == 409
    assert saldo(orcamento_id) == 1000
    assert len(notificacoes()) == 1


# --- Critério 3: dupla aprovação bloqueada -----------------------------------


def test_dupla_aprovacao_e_bloqueada():
    orcamento_id = criar_orcamento(1000)
    lancamento_id = lancar(orcamento_id, 300)
    assert aprovar(lancamento_id).status_code == 200

    segunda = aprovar(lancamento_id)

    assert segunda.status_code == 409
    assert segunda.json()["detail"] == "Lançamento já está aprovado"
    assert saldo(orcamento_id) == 700  # debitado uma vez só
    assert len(notificacoes()) == 1  # notificado uma vez só


def test_aprovacoes_simultaneas_so_uma_vale():
    # Duas pessoas da coordenação clicam em "Aprovar" ao mesmo tempo.
    orcamento_id = criar_orcamento(1000)
    lancamento_id = lancar(orcamento_id, 300)

    with ThreadPoolExecutor(max_workers=8) as executor:
        codigos = list(executor.map(lambda _: aprovar(lancamento_id).status_code, range(8)))

    assert codigos.count(200) == 1
    assert codigos.count(409) == 7
    assert saldo(orcamento_id) == 700
    assert len(notificacoes()) == 1


def test_aprovado_nao_pode_ser_rejeitado_depois():
    orcamento_id = criar_orcamento(1000)
    lancamento_id = lancar(orcamento_id, 300)
    aprovar(lancamento_id)

    assert rejeitar(lancamento_id, {"motivo": "Mudei de ideia."}).status_code == 409
    assert saldo(orcamento_id) == 700
    assert [n["tipo"] for n in notificacoes()] == ["lancamento_aprovado"]


def test_rota_antiga_de_aprovacao_tambem_bloqueia_dupla_aprovacao():
    # POST /orcamentos/{id}/lancamentos/{id}/aprovar (T-07) ainda existe;
    # aprovar por ela depois do PATCH não pode debitar de novo.
    orcamento_id = criar_orcamento(1000)
    lancamento_id = lancar(orcamento_id, 300)
    aprovar(lancamento_id)

    resposta = client.post(
        f"/orcamentos/{orcamento_id}/lancamentos/{lancamento_id}/aprovar"
    )

    assert resposta.status_code == 409
    assert saldo(orcamento_id) == 700


# --- Vários lançamentos ao mesmo tempo --------------------------------------


def test_fila_com_varios_autores_e_decisoes():
    orcamento_id = criar_orcamento(1000)
    da_ana = lancar(orcamento_id, 400, autor="educadora-ana", descricao="Tintas")
    do_joao = lancar(orcamento_id, 200, autor="educador-joao", descricao="Lanche")
    da_ana_2 = lancar(orcamento_id, 450, autor="educadora-ana", descricao="Pincéis")

    # Mais antigos primeiro
    assert fila_de_pendentes() == [da_ana, do_joao, da_ana_2]

    aprovar(da_ana)
    rejeitar(do_joao, {"motivo": "Fora da categoria."})
    aprovar(da_ana_2)

    # Só os aprovados contam: 1000 - 400 - 450
    orcamento = client.get(f"/orcamentos/{orcamento_id}").json()
    assert orcamento["saldo"] == 150
    assert orcamento["nivel_alerta"] == "atencao"  # 85% consumido
    assert fila_de_pendentes() == []

    # Cada autor recebe só as próprias notificações
    assert [(n["lancamento_id"], n["tipo"]) for n in notificacoes("educadora-ana")] == [
        (da_ana_2, "lancamento_aprovado"),
        (da_ana, "lancamento_aprovado"),
    ]
    [do_joao_notif] = notificacoes("educador-joao")
    assert do_joao_notif["lancamento_id"] == do_joao
    assert do_joao_notif["motivo"] == "Fora da categoria."
