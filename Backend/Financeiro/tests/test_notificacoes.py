"""T-17 · US-04 — Notificação ao autor do lançamento (aprovado/rejeitado)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient

from Financeiro.comprovantes import ArmazenamentoEmMemoria
from Financeiro.main import app
from Financeiro.notificacoes import (
    TipoNotificacao,
    caixa_de_notificacoes,
    formatar_reais,
)
from Financeiro.orcamento import Lancamento, Orcamento, StatusLancamento
from Financeiro.routers.comprovantes import obter_armazenamento
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64

client = TestClient(app)


def cabecalhos(papel="coordenacao", usuario=None, token=TOKEN):
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
    caixa_de_notificacoes.limpar()
    app.dependency_overrides[obter_armazenamento] = lambda: ArmazenamentoEmMemoria()
    yield
    app.dependency_overrides.clear()
    _orcamentos.clear()
    caixa_de_notificacoes.limpar()


def criar_orcamento(*lancamentos):
    orcamento = Orcamento(
        id="orcamento-1",
        projeto_id="projeto-1",
        valor_total=1000,
        data_inicio=date(2026, 1, 1),
        data_fim=date(2026, 12, 31),
        categorias_despesa=["materiais"],
        lancamentos=list(lancamentos),
    )
    _orcamentos.append(orcamento)
    return orcamento


def pendente(valor=200, autor_id="educadora-ana", descricao="Tintas para a oficina"):
    return Lancamento(
        valor=valor,
        status=StatusLancamento.PENDENTE,
        descricao=descricao,
        autor_id=autor_id,
    )


def aprovar(lancamento_id, papel="coordenacao"):
    return client.patch(
        f"/lancamentos/{lancamento_id}/aprovar", headers=cabecalhos(papel=papel)
    )


def rejeitar(lancamento_id, motivo, papel="coordenacao"):
    return client.patch(
        f"/lancamentos/{lancamento_id}/rejeitar",
        json={"motivo": motivo},
        headers=cabecalhos(papel=papel),
    )


def notificacoes_de(usuario, **params):
    return client.get(
        "/notificacoes", params=params, headers=cabecalhos(papel="educador", usuario=usuario)
    )


# --- Critério 1: aprovado → autor recebe notificação no sistema -------------


def test_aprovar_notifica_o_autor():
    lancamento = pendente(150)
    criar_orcamento(lancamento)

    assert aprovar(lancamento.id).status_code == 200

    resposta = notificacoes_de("educadora-ana")
    assert resposta.status_code == 200
    [notificacao] = resposta.json()
    assert notificacao["lancamento_id"] == lancamento.id
    assert notificacao["tipo"] == "lancamento_aprovado"
    assert notificacao["mensagem"] == (
        'Seu lançamento "Tintas para a oficina" de R$ 150,00 foi aprovado.'
    )
    assert notificacao["motivo"] is None
    assert notificacao["lida"] is False
    assert notificacao["criada_em"]


# --- Critério 2: rejeitado → autor recebe notificação com o motivo ----------


def test_rejeitar_notifica_o_autor_com_o_motivo():
    lancamento = pendente(1234.5)
    criar_orcamento(lancamento)

    assert rejeitar(lancamento.id, "  Nota fiscal ilegível.  ").status_code == 200

    [notificacao] = notificacoes_de("educadora-ana").json()
    assert notificacao["tipo"] == "lancamento_rejeitado"
    assert notificacao["motivo"] == "Nota fiscal ilegível."
    assert notificacao["mensagem"] == (
        'Seu lançamento "Tintas para a oficina" de R$ 1.234,50 foi rejeitado. '
        "Motivo: Nota fiscal ilegível."
    )


def test_fluxo_completo_autor_do_post_recebe_a_notificacao():
    # O educador lança pela T-12 identificado no cabeçalho; a coordenação
    # rejeita; o educador vê a notificação com o motivo.
    criar_orcamento()
    criado = client.post(
        "/lancamentos",
        data={
            "orcamento_id": "orcamento-1",
            "valor": "80",
            "descricao": "Lanche",
            "categoria": "materiais",
            "data_despesa": "2026-10-10",
        },
        files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")},
        headers=cabecalhos(papel="educador", usuario="educador-joao"),
    ).json()

    rejeitar(criado["id"], "Valor acima do limite.")

    [notificacao] = notificacoes_de("educador-joao").json()
    assert notificacao["lancamento_id"] == criado["id"]
    assert notificacao["motivo"] == "Valor acima do limite."


# --- Só ações confirmadas notificam -----------------------------------------


def test_acao_que_falha_nao_gera_notificacao():
    lancamento = pendente()
    criar_orcamento(lancamento)

    assert rejeitar(lancamento.id, "   ").status_code == 400
    assert aprovar(lancamento.id, papel="educador").status_code == 403
    assert notificacoes_de("educadora-ana").json() == []


def test_acao_repetida_nao_duplica_notificacao():
    lancamento = pendente()
    criar_orcamento(lancamento)

    aprovar(lancamento.id)
    assert aprovar(lancamento.id).status_code == 409
    assert rejeitar(lancamento.id, "Tarde demais.").status_code == 409

    assert len(notificacoes_de("educadora-ana").json()) == 1


def test_aprovacoes_simultaneas_geram_uma_notificacao():
    lancamento = pendente()
    criar_orcamento(lancamento)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: aprovar(lancamento.id), range(8)))

    assert len(notificacoes_de("educadora-ana").json()) == 1


def test_lancamento_sem_autor_nao_gera_notificacao_nem_erro():
    lancamento = pendente(autor_id=None)
    criar_orcamento(lancamento)

    assert aprovar(lancamento.id).status_code == 200
    assert caixa_de_notificacoes.listar("educadora-ana") == []


# --- Cada usuário vê só as suas ---------------------------------------------


def test_usuario_nao_ve_notificacao_de_outro():
    da_ana, do_joao = pendente(autor_id="educadora-ana"), pendente(autor_id="educador-joao")
    criar_orcamento(da_ana, do_joao)

    aprovar(da_ana.id)
    rejeitar(do_joao.id, "Duplicado.")

    [da_ana_notif] = notificacoes_de("educadora-ana").json()
    [do_joao_notif] = notificacoes_de("educador-joao").json()
    assert da_ana_notif["lancamento_id"] == da_ana.id
    assert do_joao_notif["lancamento_id"] == do_joao.id


def test_lista_mais_recente_primeiro_e_filtra_nao_lidas():
    primeiro, segundo = pendente(), pendente()
    criar_orcamento(primeiro, segundo)
    aprovar(primeiro.id)
    rejeitar(segundo.id, "Sem comprovante.")

    lista = notificacoes_de("educadora-ana").json()
    assert [n["lancamento_id"] for n in lista] == [segundo.id, primeiro.id]

    resposta = client.patch(
        f"/notificacoes/{lista[0]['id']}/lida",
        headers=cabecalhos(papel="educador", usuario="educadora-ana"),
    )
    assert resposta.status_code == 200
    assert resposta.json()["lida"] is True

    nao_lidas = notificacoes_de("educadora-ana", nao_lidas="true").json()
    assert [n["lancamento_id"] for n in nao_lidas] == [primeiro.id]
    assert len(notificacoes_de("educadora-ana").json()) == 2


def test_nao_marca_como_lida_notificacao_de_outro_usuario():
    lancamento = pendente()
    criar_orcamento(lancamento)
    aprovar(lancamento.id)
    [notificacao] = notificacoes_de("educadora-ana").json()

    resposta = client.patch(
        f"/notificacoes/{notificacao['id']}/lida",
        headers=cabecalhos(papel="educador", usuario="educador-joao"),
    )

    assert resposta.status_code == 404
    assert notificacoes_de("educadora-ana").json()[0]["lida"] is False


def test_marcar_inexistente_retorna_404():
    resposta = client.patch(
        "/notificacoes/nao-existe/lida",
        headers=cabecalhos(papel="educador", usuario="educadora-ana"),
    )
    assert resposta.status_code == 404


# --- Autenticação e identificação -------------------------------------------


def test_listar_sem_token_retorna_401():
    resposta = client.get("/notificacoes", headers=cabecalhos(usuario="educadora-ana", token=None))
    assert resposta.status_code == 401


@pytest.mark.parametrize("usuario", [None, "", "   "])
def test_listar_sem_usuario_retorna_400(usuario):
    resposta = client.get("/notificacoes", headers=cabecalhos(usuario=usuario))
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Identificação do usuário obrigatória."


def test_usuario_muito_longo_retorna_400():
    assert notificacoes_de("x" * 101).status_code == 400


def test_post_sem_usuario_continua_funcionando_sem_autor():
    criar_orcamento()
    resposta = client.post(
        "/lancamentos",
        data={
            "orcamento_id": "orcamento-1",
            "valor": "80",
            "descricao": "Lanche",
            "categoria": "materiais",
            "data_despesa": "2026-10-10",
        },
        files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")},
        headers=cabecalhos(papel="educador"),
    )

    assert resposta.status_code == 201
    assert _orcamentos[0].lancamentos[0].autor_id is None


# --- Domínio ----------------------------------------------------------------


def test_dominio_nao_notifica_lancamento_pendente():
    assert caixa_de_notificacoes.notificar_resultado(pendente()) is None


def test_dominio_mensagem_sem_descricao():
    lancamento = pendente(descricao="")
    lancamento.status = StatusLancamento.APROVADO

    notificacao = caixa_de_notificacoes.notificar_resultado(lancamento)

    assert notificacao.tipo == TipoNotificacao.LANCAMENTO_APROVADO
    assert notificacao.mensagem == "Seu lançamento de R$ 200,00 foi aprovado."


@pytest.mark.parametrize(
    "valor, esperado",
    [(0.5, "R$ 0,50"), (80, "R$ 80,00"), (1234.5, "R$ 1.234,50"), (1000000, "R$ 1.000.000,00")],
)
def test_formatar_reais(valor, esperado):
    assert formatar_reais(valor) == esperado
