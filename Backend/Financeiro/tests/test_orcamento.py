from datetime import date

import pytest
from fastapi.testclient import TestClient

from main import app
from orcamento import Lancamento, Orcamento, StatusLancamento
from routers.orcamentos import _orcamentos

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


def orcamento_de_teste(**overrides):
    base = {
        "id": "orcamento-1",
        "projeto_id": "projeto-1",
        "valor_total": 1000,
        "data_inicio": date(2026, 1, 1),
        "data_fim": date(2026, 12, 31),
        "categorias_despesa": ["materiais"],
        "lancamentos": [],
    }
    base.update(overrides)
    return Orcamento(**base)


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


def test_saldo_com_lancamentos_aprovados():
    orcamento = orcamento_de_teste(
        lancamentos=[
            Lancamento(valor=200, status=StatusLancamento.APROVADO),
            Lancamento(valor=150, status=StatusLancamento.APROVADO),
        ],
    )

    assert orcamento.saldo == 650


def test_saldo_sem_lancamentos_e_igual_ao_valor_total():
    orcamento = orcamento_de_teste(valor_total=500)

    assert orcamento.saldo == 500


def test_lancamentos_pendentes_e_rejeitados_nao_afetam_saldo():
    orcamento = orcamento_de_teste(
        lancamentos=[
            Lancamento(valor=300, status=StatusLancamento.PENDENTE),
            Lancamento(valor=200, status=StatusLancamento.REJEITADO),
        ],
    )

    assert orcamento.saldo == 1000


def test_saldo_considera_apenas_aprovados_entre_status_mistos():
    orcamento = orcamento_de_teste(
        lancamentos=[
            Lancamento(valor=100, status=StatusLancamento.APROVADO),
            Lancamento(valor=300, status=StatusLancamento.PENDENTE),
            Lancamento(valor=200, status=StatusLancamento.REJEITADO),
        ],
    )

    assert orcamento.saldo == 900


def test_saldo_fica_negativo_quando_aprovados_ultrapassam_o_valor_total():
    orcamento = orcamento_de_teste(
        lancamentos=[
            Lancamento(valor=700, status=StatusLancamento.APROVADO),
            Lancamento(valor=500, status=StatusLancamento.APROVADO),
        ],
    )

    assert orcamento.saldo == -200


def test_aprovar_lancamento_debita_saldo_no_mesmo_instante():
    lancamento = Lancamento(valor=200, status=StatusLancamento.PENDENTE)
    orcamento = orcamento_de_teste(valor_total=1000, lancamentos=[lancamento])

    orcamento.aprovar_lancamento(lancamento.id)

    assert lancamento.status == StatusLancamento.APROVADO
    assert orcamento.saldo == 800


def test_aprovar_lancamento_ja_aprovado_nao_debita_novamente():
    lancamento = Lancamento(valor=200, status=StatusLancamento.APROVADO)
    orcamento = orcamento_de_teste(valor_total=1000, lancamentos=[lancamento])

    orcamento.aprovar_lancamento(lancamento.id)

    assert orcamento.saldo == 800


def test_aprovar_lancamento_inexistente_levanta_erro():
    orcamento = orcamento_de_teste(valor_total=1000, lancamentos=[])

    with pytest.raises(ValueError):
        orcamento.aprovar_lancamento("nao-existe")


def test_reverter_aprovacao_recredita_saldo_e_volta_para_pendente():
    lancamento = Lancamento(valor=200, status=StatusLancamento.APROVADO)
    orcamento = orcamento_de_teste(valor_total=1000, lancamentos=[lancamento])

    orcamento.reverter_aprovacao(lancamento.id)

    assert lancamento.status == StatusLancamento.PENDENTE
    assert orcamento.saldo == 1000


def test_reverter_aprovacao_de_lancamento_nao_aprovado_levanta_erro():
    lancamento = Lancamento(valor=200, status=StatusLancamento.PENDENTE)
    orcamento = orcamento_de_teste(valor_total=1000, lancamentos=[lancamento])

    with pytest.raises(ValueError):
        orcamento.reverter_aprovacao(lancamento.id)

    assert orcamento.saldo == 1000


def test_reverter_aprovacao_de_lancamento_inexistente_levanta_erro():
    orcamento = orcamento_de_teste(valor_total=1000, lancamentos=[])

    with pytest.raises(ValueError):
        orcamento.reverter_aprovacao("nao-existe")


def test_aprovacoes_concorrentes_serializam_acesso_ao_saldo():
    import threading
    import time

    lancamentos = [
        Lancamento(valor=10, status=StatusLancamento.PENDENTE) for _ in range(5)
    ]
    orcamento = orcamento_de_teste(valor_total=1000, lancamentos=lancamentos)

    buscar_original = orcamento._buscar_lancamento
    contador_lock = threading.Lock()
    ativos = 0
    maximo_simultaneo = 0

    def buscar_com_atraso(lancamento_id):
        nonlocal ativos, maximo_simultaneo
        with contador_lock:
            ativos += 1
            maximo_simultaneo = max(maximo_simultaneo, ativos)
        time.sleep(0.02)
        resultado = buscar_original(lancamento_id)
        with contador_lock:
            ativos -= 1
        return resultado

    orcamento._buscar_lancamento = buscar_com_atraso

    threads = [
        threading.Thread(target=orcamento.aprovar_lancamento, args=(l.id,))
        for l in lancamentos
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert maximo_simultaneo == 1
    assert orcamento.saldo == 1000 - 5 * 10
    assert all(l.status == StatusLancamento.APROVADO for l in lancamentos)


def test_get_orcamento_inexistente_retorna_404():
    response = client.get("/orcamentos/nao-existe")

    assert response.status_code == 404


def test_get_orcamento_sem_lancamentos_retorna_saldo_igual_ao_valor_total():
    _orcamentos.append(orcamento_de_teste(id="orcamento-1", valor_total=500))

    response = client.get("/orcamentos/orcamento-1")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "orcamento-1"
    assert body["saldo"] == 500


def test_get_orcamento_com_lancamentos_aprovados_reflete_saldo_calculado():
    _orcamentos.append(
        orcamento_de_teste(
            id="orcamento-1",
            valor_total=1000,
            lancamentos=[
                Lancamento(valor=200, status=StatusLancamento.APROVADO),
                Lancamento(valor=100, status=StatusLancamento.PENDENTE),
            ],
        )
    )

    response = client.get("/orcamentos/orcamento-1")

    assert response.status_code == 200
    assert response.json()["saldo"] == 800


def url_aprovar(orcamento_id, lancamento_id):
    return f"/orcamentos/{orcamento_id}/lancamentos/{lancamento_id}/aprovar"


def url_reverter(orcamento_id, lancamento_id):
    return (
        f"/orcamentos/{orcamento_id}/lancamentos/{lancamento_id}"
        "/reverter-aprovacao"
    )


def test_post_aprovar_debita_saldo_e_retorna_orcamento_atualizado():
    lancamento = Lancamento(valor=200, status=StatusLancamento.PENDENTE)
    _orcamentos.append(orcamento_de_teste(lancamentos=[lancamento]))

    response = client.post(url_aprovar("orcamento-1", lancamento.id))

    assert response.status_code == 200
    assert response.json()["saldo"] == 800
    assert lancamento.status == StatusLancamento.APROVADO


def test_post_aprovar_duas_vezes_debita_saldo_uma_unica_vez():
    lancamento = Lancamento(valor=200, status=StatusLancamento.PENDENTE)
    _orcamentos.append(orcamento_de_teste(lancamentos=[lancamento]))

    client.post(url_aprovar("orcamento-1", lancamento.id))
    response = client.post(url_aprovar("orcamento-1", lancamento.id))

    assert response.status_code == 200
    assert response.json()["saldo"] == 800


def test_post_reverter_aprovacao_recredita_saldo_e_volta_para_pendente():
    lancamento = Lancamento(valor=200, status=StatusLancamento.APROVADO)
    _orcamentos.append(orcamento_de_teste(lancamentos=[lancamento]))

    response = client.post(url_reverter("orcamento-1", lancamento.id))

    assert response.status_code == 200
    assert response.json()["saldo"] == 1000
    assert lancamento.status == StatusLancamento.PENDENTE


def test_post_reverter_lancamento_nao_aprovado_retorna_409_sem_alterar_saldo():
    lancamento = Lancamento(valor=200, status=StatusLancamento.PENDENTE)
    _orcamentos.append(orcamento_de_teste(lancamentos=[lancamento]))

    response = client.post(url_reverter("orcamento-1", lancamento.id))

    assert response.status_code == 409
    assert client.get("/orcamentos/orcamento-1").json()["saldo"] == 1000


@pytest.mark.parametrize("montar_url", [url_aprovar, url_reverter])
def test_post_em_orcamento_inexistente_retorna_404(montar_url):
    response = client.post(montar_url("nao-existe", "qualquer"))

    assert response.status_code == 404


@pytest.mark.parametrize("montar_url", [url_aprovar, url_reverter])
def test_post_em_lancamento_inexistente_retorna_404(montar_url):
    _orcamentos.append(orcamento_de_teste())

    response = client.post(montar_url("orcamento-1", "nao-existe"))

    assert response.status_code == 404


def test_aprovacoes_simultaneas_via_api_mantem_saldo_consistente():
    from concurrent.futures import ThreadPoolExecutor

    lancamentos = [
        Lancamento(valor=10, status=StatusLancamento.PENDENTE) for _ in range(20)
    ]
    _orcamentos.append(orcamento_de_teste(lancamentos=lancamentos))

    with ThreadPoolExecutor(max_workers=10) as executor:
        respostas = list(
            executor.map(
                lambda l: client.post(url_aprovar("orcamento-1", l.id)),
                lancamentos,
            )
        )

    assert all(r.status_code == 200 for r in respostas)
    assert client.get("/orcamentos/orcamento-1").json()["saldo"] == 1000 - 20 * 10


def test_aprovacoes_simultaneas_do_mesmo_lancamento_debitam_uma_unica_vez():
    from concurrent.futures import ThreadPoolExecutor

    lancamento = Lancamento(valor=200, status=StatusLancamento.PENDENTE)
    _orcamentos.append(orcamento_de_teste(lancamentos=[lancamento]))

    with ThreadPoolExecutor(max_workers=10) as executor:
        respostas = list(
            executor.map(
                lambda _: client.post(url_aprovar("orcamento-1", lancamento.id)),
                range(10),
            )
        )

    assert all(r.status_code == 200 for r in respostas)
    assert client.get("/orcamentos/orcamento-1").json()["saldo"] == 800


def test_post_aprovar_lancamento_rejeitado_retorna_409_sem_alterar_saldo():
    lancamento = Lancamento(valor=200, status=StatusLancamento.REJEITADO)
    _orcamentos.append(orcamento_de_teste(lancamentos=[lancamento]))

    response = client.post(url_aprovar("orcamento-1", lancamento.id))

    assert response.status_code == 409
    assert lancamento.status == StatusLancamento.REJEITADO
    assert client.get("/orcamentos/orcamento-1").json()["saldo"] == 1000
