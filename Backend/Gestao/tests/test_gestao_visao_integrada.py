"""Visão integrada da execução física e financeira (T-78 · US-12).

A parte física vem das tabelas de Gestão; a financeira, dos dados em memória do
Financeiro, que estes testes preparam diretamente nos módulos dele (só leitura no código
de Gestão).
"""

from datetime import date

import pytest
import sqlalchemy as sa

from Financeiro import projetos as fin_projetos
from Financeiro.orcamento import Lancamento, Orcamento, StatusLancamento
from Financeiro.routers import orcamentos as fin_orcamentos

VISAO = "/gestao/programas/p-1/visao-integrada"


@pytest.fixture
def memoria_do_financeiro():
    """Esvazia os cadastros em memória do Financeiro antes e depois de cada teste."""
    fin_projetos._projetos.clear()
    fin_orcamentos._orcamentos.clear()
    yield
    fin_projetos._projetos.clear()
    fin_orcamentos._orcamentos.clear()


@pytest.fixture
def programa(banco, memoria_do_financeiro):
    """Programa p-1 (Semear) com plano de ação, equipe e papéis.

    - ana: coordenação em p-1       - jessica: educadora em p-1
    - dora: direção da plataforma   - bruno: sem vínculo em p-1
    Metas: "Famílias" (40, realizado 30 em maio e 5 em agosto) e "Encontros" (10, nada).
    """
    with banco.begin() as conexao:
        conexao.execute(
            sa.text("INSERT INTO projetos (id, nome, identificador) VALUES ('p-1', 'Semear', 'SEMEAR')")
        )
        conexao.execute(
            sa.text("INSERT INTO usuarios (id, nome) VALUES (:id, :nome)"),
            [
                {"id": "ana", "nome": "Ana Martins"},
                {"id": "jessica", "nome": "Jéssica Almeida"},
                {"id": "dora", "nome": "Dora Prates"},
                {"id": "bruno", "nome": "Bruno Lima"},
            ],
        )
        conexao.execute(sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('dora', 'direcao')"))
        conexao.execute(
            sa.text(
                """
                INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) VALUES
                    ('v-ana', 'ana', 'p-1', 'coordenacao', '2025-01-10'),
                    ('v-jessica', 'jessica', 'p-1', 'educador', '2025-03-01')
                """
            )
        )
        conexao.execute(sa.text("INSERT INTO objetivos (id, programa_id, descricao) VALUES ('o-1', 'p-1', 'Vínculos')"))
        conexao.execute(
            sa.text(
                """
                INSERT INTO acoes (id, objetivo_id, descricao, periodo_inicio, periodo_fim,
                                   resultado_esperado, periodicidade)
                VALUES ('a-1', 'o-1', 'Encontros com famílias', '2026-03-01', '2026-11-30',
                        'Famílias participando', 'mensal')
                """
            )
        )
        conexao.execute(
            sa.text(
                """
                INSERT INTO metas (id, acao_id, descricao, valor_planejado, unidade) VALUES
                    ('m-1', 'a-1', 'Famílias', 40, 'famílias'),
                    ('m-2', 'a-1', 'Encontros', 10, 'encontros')
                """
            )
        )
        conexao.execute(
            sa.text(
                """
                INSERT INTO registros_meta (id, meta_id, data, valor_realizado) VALUES
                    ('r-1', 'm-1', '2026-05-10', 30),
                    ('r-2', 'm-1', '2026-08-10', 5)
                """
            )
        )
    return banco


def projeto_financeiro(nome="Semear", projeto_id=None, orcado=10000, aprovados=(2500,), pendentes=(400,)):
    """Projeto e orçamento no Financeiro (em memória), com lançamentos em 2026."""
    projeto = fin_projetos.registrar_projeto(nome)
    if projeto_id:
        projeto.id = projeto_id
    lancamentos = [
        Lancamento(valor=v, status=StatusLancamento.APROVADO, data_despesa=date(2026, 5, 15)) for v in aprovados
    ] + [Lancamento(valor=v, status=StatusLancamento.PENDENTE, data_despesa=date(2026, 5, 20)) for v in pendentes]
    fin_orcamentos._orcamentos.append(
        Orcamento(
            id=f"orc-{projeto.id}",
            projeto_id=projeto.id,
            valor_total=orcado,
            data_inicio=date(2026, 1, 1),
            data_fim=date(2026, 12, 31),
            categorias_despesa=["materiais"],
            lancamentos=lancamentos,
        )
    )
    return projeto


def como(cabecalhos, usuario):
    return {**cabecalhos, "X-Usuario-Id": usuario}


def test_junta_execucao_fisica_e_financeira_do_programa(cliente, cabecalhos, programa):
    projeto_financeiro()

    resposta = cliente.get(VISAO, headers=como(cabecalhos, "ana"))

    assert resposta.status_code == 200
    visao = resposta.json()
    assert visao["programa"] == {"id": "p-1", "nome": "Semear", "identificador": "SEMEAR"}
    assert [(m["descricao"], m["planejado"], m["realizado"], m["percentual"]) for m in visao["fisica"]["metas"]] == [
        ("Encontros", 10.0, 0.0, 0.0),
        ("Famílias", 40.0, 35.0, 87.5),
    ]
    assert visao["fisica"]["percentual_medio"] == 43.8
    financeira = visao["financeira"]
    # Só o lançamento aprovado entra no realizado (o pendente fica de fora).
    assert {k: financeira[k] for k in ("vinculo", "projeto", "orcado", "realizado", "saldo", "percentual_executado")} == {
        "vinculo": "nome",
        "projeto": "Semear",
        "orcado": 10000.0,
        "realizado": 2500.0,
        "saldo": 7500.0,
        "percentual_executado": 25.0,
    }


def test_periodo_filtra_o_realizado_fisico_e_o_financeiro(cliente, cabecalhos, programa):
    projeto_financeiro()

    resposta = cliente.get(VISAO, params={"inicio": "2026-08-01", "fim": "2026-08-31"}, headers=como(cabecalhos, "ana"))

    visao = resposta.json()
    assert (visao["inicio"], visao["fim"]) == ("2026-08-01", "2026-08-31")
    familias = next(m for m in visao["fisica"]["metas"] if m["descricao"] == "Famílias")
    assert familias["realizado"] == 5.0
    assert visao["financeira"]["realizado"] == 0.0


def test_projeto_do_financeiro_com_o_mesmo_id_casa_pelo_id(cliente, cabecalhos, programa):
    projeto_financeiro(nome="Nome diferente no Financeiro", projeto_id="p-1")

    financeira = cliente.get(VISAO, headers=como(cabecalhos, "ana")).json()["financeira"]

    assert financeira["vinculo"] == "id"
    assert financeira["projeto_id"] == "p-1"


def test_nome_casa_sem_diferenciar_maiusculas_e_acentos(cliente, cabecalhos, programa):
    with programa.begin() as conexao:
        conexao.execute(sa.text("UPDATE projetos SET nome = 'Ação Semear' WHERE id = 'p-1'"))
    projeto_financeiro(nome="acao semear")

    assert cliente.get(VISAO, headers=como(cabecalhos, "ana")).json()["financeira"]["vinculo"] == "nome"


def test_programa_sem_projeto_no_financeiro_mostra_so_a_execucao_fisica(cliente, cabecalhos, programa):
    resposta = cliente.get(VISAO, headers=como(cabecalhos, "ana"))

    assert resposta.status_code == 200
    assert resposta.json()["financeira"] == {
        "vinculo": "nenhum",
        "projeto_id": None,
        "projeto": None,
        "orcado": 0.0,
        "realizado": 0.0,
        "saldo": 0.0,
        "percentual_executado": None,
    }
    assert len(resposta.json()["fisica"]["metas"]) == 2


@pytest.mark.parametrize("usuario, ve_financeiro", [("ana", True), ("dora", True), ("jessica", False)])
def test_valores_financeiros_so_para_coordenacao_direcao_e_administracao(cliente, cabecalhos, programa, usuario, ve_financeiro):
    projeto_financeiro()

    visao = cliente.get(VISAO, headers=como(cabecalhos, usuario)).json()

    assert (visao["financeira"] is not None) is ve_financeiro
    assert len(visao["fisica"]["metas"]) == 2


def test_sem_acesso_ao_programa_403(cliente, cabecalhos, programa):
    assert cliente.get(VISAO, headers=como(cabecalhos, "bruno")).status_code == 403


def test_consulta_fica_na_trilha_de_auditoria(cliente, cabecalhos, programa):
    projeto_financeiro()
    cliente.get(VISAO, params={"inicio": "2026-01-01"}, headers=como(cabecalhos, "jessica"))

    with programa.connect() as conexao:
        evento = conexao.execute(
            sa.text("SELECT usuario_id, acao, alvo_id, detalhes FROM log_auditoria WHERE acao = 'consulta_visao_integrada'")
        ).one()

    assert evento.usuario_id == "jessica"
    assert evento.alvo_id == "p-1"
    assert evento.detalhes == {"inicio": "2026-01-01", "fim": None, "financeiro": False, "vinculo": None}


def test_periodo_invertido_400(cliente, cabecalhos, programa):
    resposta = cliente.get(VISAO, params={"inicio": "2026-08-01", "fim": "2026-07-01"}, headers=como(cabecalhos, "ana"))

    assert resposta.status_code == 400


def test_programa_inexistente_404(cliente, cabecalhos, programa):
    resposta = cliente.get("/gestao/programas/nao-existe/visao-integrada", headers=como(cabecalhos, "dora"))

    assert resposta.status_code == 404
