"""Testes da US-12 (T-80): identificador do programa, acesso por papel, trilha de auditoria
e o fluxo ponta a ponta da integração.

Ponta a ponta: o orçamento, o lançamento e a aprovação são feitos pelas rotas do próprio
Financeiro, na mesma API integrada e no mesmo banco. O programa cadastrado na Gestão já é
o projeto do Financeiro (tabela ``projetos``), e a Visão integrada de Gestão mostra os
valores novos do mesmo programa e período, sem recadastro e sem dado desatualizado.
"""

import pytest
import sqlalchemy as sa

from Financeiro.comprovantes import ArmazenamentoEmMemoria
from Financeiro.routers.comprovantes import obter_armazenamento

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
VISAO = "/gestao/programas/p-1/visao-integrada"


@pytest.fixture
def plataforma(app, banco, cabecalhos):
    """Programa p-1 (Semear) com uma meta, equipe e o Financeiro vazio, com armazenamento em memória.

    - ana: coordenação em p-1       - jessica: educadora em p-1
    - dora: direção da plataforma   - bruno: sem vínculo
    """
    app.dependency_overrides[obter_armazenamento] = ArmazenamentoEmMemoria
    with banco.begin() as conexao:
        conexao.execute(
            sa.text("INSERT INTO projetos (id, nome, identificador) VALUES ('p-1', 'Semear', 'SEMEAR')")
        )
        conexao.execute(
            sa.text("INSERT INTO usuarios (id, nome) VALUES ('ana', 'Ana'), ('jessica', 'Jéssica'), ('dora', 'Dora'), ('bruno', 'Bruno')")
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
                VALUES ('a-1', 'o-1', 'Encontros', '2026-03-01', '2026-11-30', 'Famílias participando', 'mensal')
                """
            )
        )
        conexao.execute(
            sa.text("INSERT INTO metas (id, acao_id, descricao, valor_planejado) VALUES ('m-1', 'a-1', 'Famílias', 40)")
        )
    yield banco
    app.dependency_overrides.pop(obter_armazenamento, None)


def financeiro(cabecalhos, papel, usuario):
    """Cabeçalhos do jeito que o frontend do Financeiro manda hoje (código, papel e usuário)."""
    return {**cabecalhos, "X-Papel-Usuario": papel, "X-Usuario-Id": usuario}


def gestao(cabecalhos, usuario):
    return {**cabecalhos, "X-Usuario-Id": usuario}


def visao(cliente, cabecalhos, usuario="ana", **periodo):
    resposta = cliente.get(VISAO, params=periodo, headers=gestao(cabecalhos, usuario))
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


# --- Ponta a ponta -----------------------------------------------------------


def test_orcamento_e_lancamento_aprovado_no_financeiro_aparecem_na_visao_integrada(cliente, cabecalhos, plataforma):
    coordenacao = financeiro(cabecalhos, "coordenacao", "coordenadora-ana")

    # 1. Financeiro: o programa da Gestão já aparece como projeto, sem recadastro; um
    # segundo cadastro com o mesmo nome é recusado. O orçamento vai para o próprio programa.
    projetos = cliente.get("/projetos", headers=coordenacao).json()
    assert [(p["id"], p["nome"]) for p in projetos] == [("p-1", "Semear")]
    assert cliente.post("/projetos", json={"nome": "Semear"}, headers=coordenacao).status_code == 409
    orcamento = cliente.post(
        "/orcamentos",
        json={
            "projeto_id": "p-1",
            "valor_total": 5000,
            "data_inicio": "2026-01-01",
            "data_fim": "2026-12-31",
            "categorias_despesa": ["materiais"],
        },
        headers=coordenacao,
    )
    assert orcamento.status_code == 201
    assert orcamento.json()["projeto_id"] == "p-1"
    antes = visao(cliente, cabecalhos)["financeira"]
    assert (antes["vinculo"], antes["orcado"], antes["realizado"], antes["saldo"]) == ("id", 5000.0, 0.0, 5000.0)

    # 2. Financeiro: lançamento com comprovante; pendente ainda não conta no realizado.
    lancamento = cliente.post(
        "/lancamentos",
        data={
            "orcamento_id": orcamento.json()["id"],
            "valor": "1250.50",
            "descricao": "Material das oficinas",
            "categoria": "materiais",
            "data_despesa": "2026-05-15",
        },
        files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")},
        headers=financeiro(cabecalhos, "educador", "educadora-jessica"),
    )
    assert lancamento.status_code == 201
    assert visao(cliente, cabecalhos)["financeira"]["realizado"] == 0.0

    # 3. Financeiro: aprovação pela coordenação.
    aprovado = cliente.patch(f"/lancamentos/{lancamento.json()['id']}/aprovar", headers=coordenacao)
    assert aprovado.status_code == 200

    # 4. Gestão: a Visão integrada do mesmo programa já mostra os valores novos.
    depois = visao(cliente, cabecalhos)
    assert depois["programa"]["id"] == "p-1"
    assert (depois["financeira"]["orcado"], depois["financeira"]["realizado"], depois["financeira"]["saldo"]) == (
        5000.0,
        1250.5,
        3749.5,
    )
    assert depois["financeira"]["percentual_executado"] == 25.0
    # E respeita o período: fora de maio, o lançamento não entra no realizado.
    assert visao(cliente, cabecalhos, inicio="2026-06-01", fim="2026-06-30")["financeira"]["realizado"] == 0.0


# --- Identificador canônico --------------------------------------------------


def test_gestao_e_visao_integrada_usam_o_mesmo_identificador_do_programa(cliente, cabecalhos, plataforma):
    programa = cliente.get("/gestao/programas/p-1", headers=cabecalhos).json()

    assert visao(cliente, cabecalhos)["programa"]["identificador"] == programa["identificador"] == "SEMEAR"


def test_quando_o_financeiro_usa_o_mesmo_registro_o_vinculo_e_pelo_id(cliente, cabecalhos, plataforma):
    # O Financeiro usa o cadastro canônico: o projeto dele é o próprio programa.
    assert visao(cliente, cabecalhos)["financeira"]["vinculo"] == "nenhum"
    cliente.post(
        "/orcamentos",
        json={
            "projeto_id": "p-1",
            "valor_total": 1000,
            "data_inicio": "2026-01-01",
            "data_fim": "2026-12-31",
            "categorias_despesa": ["materiais"],
        },
        headers=financeiro(cabecalhos, "coordenacao", "coordenadora-ana"),
    )

    financeira = visao(cliente, cabecalhos)["financeira"]

    assert (financeira["vinculo"], financeira["projeto_id"], financeira["projeto"]) == ("id", "p-1", "Semear")


def test_dados_do_financeiro_ficam_no_banco_e_nao_somem_com_reinicio(cliente, cabecalhos, plataforma):
    coordenacao = financeiro(cabecalhos, "coordenacao", "coordenadora-ana")
    criado = cliente.post(
        "/orcamentos",
        json={
            "projeto_id": "p-1",
            "valor_total": 800,
            "data_inicio": "2026-01-01",
            "data_fim": "2026-12-31",
            "categorias_despesa": ["materiais"],
        },
        headers=coordenacao,
    )
    assert criado.status_code == 201

    with plataforma.connect() as conexao:
        gravado = conexao.execute(
            sa.text("SELECT projeto_id, valor_total FROM orcamentos WHERE id = :id"), {"id": criado.json()["id"]}
        ).one()
    assert (gravado.projeto_id, float(gravado.valor_total)) == ("p-1", 800.0)


# --- Acesso por papel ----------------------------------------------------------


@pytest.mark.parametrize("usuario, ve_valores", [("ana", True), ("dora", True), ("jessica", False)])
def test_papel_sem_acesso_aos_valores_financeiros_recebe_so_a_parte_fisica(cliente, cabecalhos, plataforma, usuario, ve_valores):
    resposta = visao(cliente, cabecalhos, usuario)

    assert (resposta["financeira"] is not None) is ve_valores
    assert [m["descricao"] for m in resposta["fisica"]["metas"]] == ["Famílias"]


# --- Trilha de auditoria -------------------------------------------------------


def eventos(banco):
    with banco.connect() as conexao:
        return [
            linha._asdict()
            for linha in conexao.execute(sa.text("SELECT usuario_id, acao, alvo_id FROM log_auditoria ORDER BY id"))
        ]


def test_consulta_e_acesso_negado_ficam_na_trilha_de_auditoria(cliente, cabecalhos, plataforma):
    visao(cliente, cabecalhos, "dora")
    negado = cliente.get(VISAO, headers=gestao(cabecalhos, "bruno"))

    assert negado.status_code == 403
    assert eventos(plataforma) == [
        {"usuario_id": "dora", "acao": "consulta_visao_integrada", "alvo_id": "p-1"},
        {"usuario_id": "bruno", "acao": "acesso_negado", "alvo_id": "p-1"},
    ]
