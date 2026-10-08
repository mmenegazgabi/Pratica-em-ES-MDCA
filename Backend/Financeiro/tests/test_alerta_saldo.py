"""T-09 · US-02 — Testes dos limiares de alerta (80% e 100%)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from Financeiro.alerta_saldo import (
    NivelAlerta,
    calcular_percentual_consumido,
    calcular_realizado,
    classificar_nivel_alerta,
)
from Financeiro.main import app
from Financeiro.orcamento import Lancamento, Orcamento, StatusLancamento
from Financeiro.routers.orcamentos import _orcamentos

client = TestClient(app)


def setup_function():
    _orcamentos.clear()


def orcamento_com_aprovados(*valores, valor_total=1000, **overrides):
    base = {
        "id": "orcamento-1",
        "projeto_id": "projeto-1",
        "valor_total": valor_total,
        "data_inicio": date(2026, 1, 1),
        "data_fim": date(2026, 12, 31),
        "categorias_despesa": ["materiais"],
        "lancamentos": [
            Lancamento(valor=v, status=StatusLancamento.APROVADO) for v in valores
        ],
    }
    base.update(overrides)
    return Orcamento(**base)


# --- Regra pura: limiares --------------------------------------------------


@pytest.mark.parametrize(
    "realizado, esperado",
    [
        (0, NivelAlerta.NORMAL),
        (500, NivelAlerta.NORMAL),
        (799.99, NivelAlerta.NORMAL),  # um centavo antes de 80%
        (800, NivelAlerta.ATENCAO),  # exatamente 80%
        (800.01, NivelAlerta.ATENCAO),
        (999.99, NivelAlerta.ATENCAO),  # um centavo antes de 100%
        (1000, NivelAlerta.ESTOURADO),  # exatamente 100%
        (1000.01, NivelAlerta.ESTOURADO),
        (1500, NivelAlerta.ESTOURADO),
    ],
)
def test_classificacao_nos_limiares_de_80_e_100_por_cento(realizado, esperado):
    assert classificar_nivel_alerta(1000, realizado) == esperado


def test_soma_em_float_que_cai_abaixo_de_80_ainda_dispara_atencao():
    # 0.1 + 0.7 == 0.7999999999999999 em float; em centavos é 0.80 (80%)
    realizado = 0.1 + 0.7

    assert classificar_nivel_alerta(1.0, realizado) == NivelAlerta.ATENCAO


def test_valor_total_zero_sem_gasto_e_normal():
    assert classificar_nivel_alerta(0, 0) == NivelAlerta.NORMAL
    assert calcular_percentual_consumido(0, 0) is None


def test_valor_total_zero_com_gasto_e_estourado():
    assert classificar_nivel_alerta(0, 10) == NivelAlerta.ESTOURADO
    assert calcular_percentual_consumido(0, 10) is None


@pytest.mark.parametrize(
    "valor_total, realizado, percentual",
    [
        (1000, 0, 0.0),
        (1000, 800, 80.0),
        (1000, 1000, 100.0),
        (1000, 1250, 125.0),
        (3, 1, 33.33),
        (3, 2, 66.66),  # truncado, não arredondado
        (1000, 799.99, 79.99),
    ],
)
def test_percentual_consumido(valor_total, realizado, percentual):
    assert calcular_percentual_consumido(valor_total, realizado) == percentual


def test_realizado_e_valor_total_menos_saldo():
    assert calcular_realizado(1000, 150) == 850
    assert calcular_realizado(1000, -200) == 1200


# --- Integração com o domínio: só aprovados contam ---------------------------


def test_lancamentos_pendentes_e_rejeitados_nao_disparam_alerta():
    orcamento = orcamento_com_aprovados(
        lancamentos=[
            Lancamento(valor=100, status=StatusLancamento.APROVADO),
            Lancamento(valor=900, status=StatusLancamento.PENDENTE),
            Lancamento(valor=900, status=StatusLancamento.REJEITADO),
        ],
    )
    realizado = calcular_realizado(orcamento.valor_total, orcamento.saldo)

    assert classificar_nivel_alerta(orcamento.valor_total, realizado) == NivelAlerta.NORMAL


# --- API: os campos chegam prontos para a tela --------------------------------


@pytest.mark.parametrize(
    "aprovados, nivel, percentual, saldo",
    [
        ((300, 200), "normal", 50.0, 500),
        ((799.99,), "normal", 79.99, 200.01),  # truncado: não mostra 80% sem alerta
        ((500, 300), "atencao", 80.0, 200),
        ((950,), "atencao", 95.0, 50),
        ((600, 400), "estourado", 100.0, 0),
        ((700, 500), "estourado", 120.0, -200),
    ],
)
def test_get_orcamento_retorna_nivel_de_alerta(aprovados, nivel, percentual, saldo):
    _orcamentos.append(orcamento_com_aprovados(*aprovados))

    response = client.get("/orcamentos/orcamento-1")

    assert response.status_code == 200
    body = response.json()
    assert body["nivel_alerta"] == nivel
    assert body["percentual_consumido"] == percentual
    assert body["saldo"] == pytest.approx(saldo)
    assert body["realizado"] == pytest.approx(1000 - saldo)


def test_listagem_por_projeto_retorna_nivel_de_alerta_de_cada_orcamento():
    _orcamentos.append(
        orcamento_com_aprovados(100, id="o-normal", data_inicio=date(2024, 1, 1))
    )
    _orcamentos.append(
        orcamento_com_aprovados(850, id="o-atencao", data_inicio=date(2025, 1, 1))
    )
    _orcamentos.append(
        orcamento_com_aprovados(1100, id="o-estourado", data_inicio=date(2026, 1, 1))
    )

    body = client.get("/orcamentos/projeto/projeto-1").json()

    niveis = {item["id"]: item["nivel_alerta"] for item in body["itens"]}
    assert niveis == {
        "o-normal": "normal",
        "o-atencao": "atencao",
        "o-estourado": "estourado",
    }
