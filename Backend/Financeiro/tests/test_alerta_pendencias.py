"""T-23 · US-05 — highlight for entries not reconciled for more than 7 days."""

from datetime import datetime, timedelta, timezone

from Financeiro.orcamento import (
    DIAS_PARA_DESTAQUE,
    Lancamento,
    StatusLancamento,
    pendencias_conciliacao,
)

# Fixed "now" so the tests don't depend on the clock.
AGORA = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def lancamento(dias_atras, status=StatusLancamento.APROVADO, conciliado=False):
    return Lancamento(
        valor=100,
        status=status,
        criado_em=AGORA - timedelta(days=dias_atras),
        conciliado=conciliado,
        referencia_extrato="EXT-2026-10-001" if conciliado else None,
    )


def pendencia_de(item, lancamentos):
    encontradas = [
        p for p in pendencias_conciliacao(lancamentos, agora=AGORA)
        if p.lancamento is item
    ]
    assert len(encontradas) == 1
    return encontradas[0]


def ids_pendentes(lancamentos):
    return [p.lancamento.id for p in pendencias_conciliacao(lancamentos, agora=AGORA)]


def test_limite_de_destaque_e_sete_dias():
    assert DIAS_PARA_DESTAQUE == 7


# --- Criterion 1: 6 days without reconciliation -> no highlight --------------


def test_seis_dias_sem_conciliacao_nao_tem_destaque():
    item = lancamento(dias_atras=6)

    pendencia = pendencia_de(item, [item])

    assert pendencia.dias_sem_conciliar == 6
    assert pendencia.destaque is False


# --- Criterion 2: 8 days without reconciliation -> highlighted ---------------


def test_oito_dias_sem_conciliacao_tem_destaque():
    item = lancamento(dias_atras=8)

    pendencia = pendencia_de(item, [item])

    assert pendencia.dias_sem_conciliar == 8
    assert pendencia.destaque is True


# --- Criterion 3: already reconciled -> not listed, whatever its age ---------


def test_conciliado_nao_aparece_na_lista_independente_da_idade():
    conciliados = [lancamento(dias_atras=d, conciliado=True) for d in (0, 6, 8, 30)]

    assert pendencias_conciliacao(conciliados, agora=AGORA) == []


def test_conciliado_fica_fora_e_pendencias_continuam_na_lista():
    conciliado = lancamento(dias_atras=30, conciliado=True)
    recente = lancamento(dias_atras=6)
    antigo = lancamento(dias_atras=8)

    assert ids_pendentes([conciliado, recente, antigo]) == [antigo.id, recente.id]


# --- Boundary and robustness ------------------------------------------------


def test_exatamente_sete_dias_ainda_nao_tem_destaque():
    # The rule is "more than 7 days", so day 7 itself is not highlighted.
    item = lancamento(dias_atras=7)

    pendencia = pendencia_de(item, [item])

    assert pendencia.dias_sem_conciliar == 7
    assert pendencia.destaque is False


def test_pendente_e_rejeitado_nao_entram_na_lista():
    # Only approved entries can be reconciled (T-21), so only they are pending here.
    lancamentos = [
        lancamento(dias_atras=10, status=StatusLancamento.PENDENTE),
        lancamento(dias_atras=10, status=StatusLancamento.REJEITADO),
    ]

    assert pendencias_conciliacao(lancamentos, agora=AGORA) == []


def test_lista_vem_da_pendencia_mais_antiga_para_a_mais_nova():
    novo = lancamento(dias_atras=1)
    antigo = lancamento(dias_atras=12)
    meio = lancamento(dias_atras=5)

    assert ids_pendentes([novo, antigo, meio]) == [antigo.id, meio.id, novo.id]


def test_agora_sem_fuso_e_tratado_como_utc():
    item = lancamento(dias_atras=8)

    pendencias = pendencias_conciliacao([item], agora=AGORA.replace(tzinfo=None))

    assert pendencias[0].dias_sem_conciliar == 8
    assert pendencias[0].destaque is True


def test_criado_em_no_futuro_nao_gera_dias_negativos():
    item = lancamento(dias_atras=0)
    item.criado_em = AGORA + timedelta(minutes=5)

    pendencia = pendencia_de(item, [item])

    assert pendencia.dias_sem_conciliar == 0
    assert pendencia.destaque is False
