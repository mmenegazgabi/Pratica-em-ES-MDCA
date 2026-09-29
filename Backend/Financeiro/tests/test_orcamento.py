from orcamento import Lancamento, Orcamento, StatusLancamento


def test_saldo_com_lancamentos_aprovados():
    orcamento = Orcamento(
        valor_total=1000,
        lancamentos=[
            Lancamento(valor=200, status=StatusLancamento.APROVADO),
            Lancamento(valor=150, status=StatusLancamento.APROVADO),
        ],
    )

    assert orcamento.saldo == 650


def test_saldo_sem_lancamentos_e_igual_ao_valor_total():
    orcamento = Orcamento(valor_total=500)

    assert orcamento.saldo == 500


def test_lancamentos_pendentes_e_rejeitados_nao_afetam_saldo():
    orcamento = Orcamento(
        valor_total=1000,
        lancamentos=[
            Lancamento(valor=300, status=StatusLancamento.PENDENTE),
            Lancamento(valor=200, status=StatusLancamento.REJEITADO),
        ],
    )

    assert orcamento.saldo == 1000


def test_saldo_considera_apenas_aprovados_entre_status_mistos():
    orcamento = Orcamento(
        valor_total=1000,
        lancamentos=[
            Lancamento(valor=100, status=StatusLancamento.APROVADO),
            Lancamento(valor=300, status=StatusLancamento.PENDENTE),
            Lancamento(valor=200, status=StatusLancamento.REJEITADO),
        ],
    )

    assert orcamento.saldo == 900


def test_saldo_fica_negativo_quando_aprovados_ultrapassam_o_valor_total():
    orcamento = Orcamento(
        valor_total=1000,
        lancamentos=[
            Lancamento(valor=700, status=StatusLancamento.APROVADO),
            Lancamento(valor=500, status=StatusLancamento.APROVADO),
        ],
    )

    assert orcamento.saldo == -200
