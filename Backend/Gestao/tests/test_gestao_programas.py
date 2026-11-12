"""GET /gestao/programas: leitura do cadastro canônico no PostgreSQL (T-00f)."""

import pytest
import sqlalchemy as sa


@pytest.fixture
def cabecalhos(cabecalhos_admin):
    """Estes testes cobrem o cadastro; quem chama é a administração (o acesso por papel fica em test_gestao_acesso_programas.py)."""
    return cabecalhos_admin


def inserir_projetos(banco, *projetos):
    with banco.begin() as conexao:
        conexao.execute(
            sa.text("INSERT INTO projetos (id, nome) VALUES (:id, :nome)"),
            [{"id": id_, "nome": nome} for id_, nome in projetos],
        )


def test_lista_programas_gravados_no_banco_em_ordem_alfabetica(cliente, cabecalhos, banco):
    inserir_projetos(banco, ("p-1", "Semear"), ("p-2", "casa de convivência"), ("p-3", "Oficina"))

    resposta = cliente.get("/gestao/programas", headers=cabecalhos)

    assert resposta.status_code == 200
    # Programas antigos, criados só com nome, vêm sem identificador nem vigência.
    vazio = {"identificador": None, "vigencia_inicio": None, "vigencia_fim": None}
    assert resposta.json() == [
        {"id": "p-2", "nome": "casa de convivência", **vazio},
        {"id": "p-3", "nome": "Oficina", **vazio},
        {"id": "p-1", "nome": "Semear", **vazio},
    ]


def test_lista_traz_identificador_e_vigencia_do_programa(cliente, cabecalhos, banco):
    with banco.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO projetos (id, nome, identificador, vigencia_inicio, vigencia_fim) "
                "VALUES ('p-1', 'Semear', 'SEMEAR', '2026-02-02', '2026-12-18')"
            )
        )

    resposta = cliente.get("/gestao/programas", headers=cabecalhos)

    assert resposta.json() == [
        {
            "id": "p-1",
            "nome": "Semear",
            "identificador": "SEMEAR",
            "vigencia_inicio": "2026-02-02",
            "vigencia_fim": "2026-12-18",
        }
    ]


def test_lista_vazia_quando_nao_ha_programas(cliente, cabecalhos, banco):
    resposta = cliente.get("/gestao/programas", headers=cabecalhos)

    assert resposta.status_code == 200
    assert resposta.json() == []


def test_sem_autenticacao_401(cliente):
    assert cliente.get("/gestao/programas").status_code == 401


def test_sem_database_url_503(cliente, cabecalhos, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    resposta = cliente.get("/gestao/programas", headers=cabecalhos)

    assert resposta.status_code == 503
    assert resposta.json()["detail"] == "Banco de dados indisponível"


def test_banco_inacessivel_503(cliente, cabecalhos, monkeypatch):
    # Porta 1 recusa a conexão na hora, sem esperar o timeout.
    monkeypatch.setenv("DATABASE_URL", "postgresql://mdca:senha@127.0.0.1:1/gestao_test")

    resposta = cliente.get("/gestao/programas", headers=cabecalhos)

    assert resposta.status_code == 503
    assert resposta.json()["detail"] == "Banco de dados indisponível"
