"""T-44 · US-02: cadastro e consulta de programas, convênios e vagas."""

import pytest
import sqlalchemy as sa

PROGRAMA = {
    "nome": "Convivência e fortalecimento de vínculos",
    "identificador": "SCFV",
    "publico": "Crianças e adolescentes de 6 a 15 anos",
    "responsavel": "Ana Martins",
    "vigencia_inicio": "2026-02-02",
    "vigencia_fim": "2026-12-18",
    "descricao": "Espaços de convivência, cultura e participação.",
}


def cadastrar(cliente, cabecalhos, **campos):
    return cliente.post("/gestao/programas", json={**PROGRAMA, **campos}, headers=cabecalhos)


def test_cadastra_programa_completo_e_consulta_pelo_id(cliente, cabecalhos, banco):
    resposta = cadastrar(cliente, cabecalhos)

    assert resposta.status_code == 201
    programa = resposta.json()
    assert programa == {
        "id": programa["id"],
        **PROGRAMA,
        "status": "ativo",
    }
    consulta = cliente.get(f"/gestao/programas/{programa['id']}", headers=cabecalhos)
    assert consulta.status_code == 200
    assert consulta.json() == programa


def test_programa_cadastrado_entra_no_cadastro_canonico_do_financeiro(cliente, cabecalhos, banco):
    # É a mesma tabela projetos que orçamentos e lançamentos referenciam (ARQ-02).
    programa_id = cadastrar(cliente, cabecalhos).json()["id"]

    lista = cliente.get("/gestao/programas", headers=cabecalhos).json()
    with banco.connect() as conexao:
        nome = conexao.execute(
            sa.text("SELECT nome FROM projetos WHERE id = :id"), {"id": programa_id}
        ).scalar_one()

    assert lista == [{"id": programa_id, "nome": PROGRAMA["nome"]}]
    assert nome == PROGRAMA["nome"]


@pytest.mark.parametrize(
    "ausentes, mensagem",
    [
        ({"vigencia_inicio": None, "vigencia_fim": None}, "Programa sem vigência (início e fim)."),
        ({"vigencia_fim": None}, "Programa sem vigência (início e fim)."),
        ({"publico": None}, "Programa sem público."),
        ({"responsavel": "   "}, "Programa sem responsável."),
        ({"identificador": ""}, "Programa sem identificador."),
        (
            {"identificador": None, "vigencia_inicio": None, "publico": None, "responsavel": None},
            "Programa sem identificador, vigência (início e fim), público e responsável.",
        ),
    ],
)
def test_programa_sem_vigencia_publico_responsavel_ou_identificador_400(
    cliente, cabecalhos, banco, ausentes, mensagem
):
    resposta = cadastrar(cliente, cabecalhos, **ausentes)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == mensagem


def test_campo_omitido_no_corpo_tambem_e_400(cliente, cabecalhos, banco):
    corpo = {k: v for k, v in PROGRAMA.items() if k != "publico"}

    resposta = cliente.post("/gestao/programas", json=corpo, headers=cabecalhos)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Programa sem público."


def test_programa_invalido_nao_e_gravado(cliente, cabecalhos, banco):
    cadastrar(cliente, cabecalhos, responsavel=None)

    assert cliente.get("/gestao/programas", headers=cabecalhos).json() == []


def test_vigencia_terminando_antes_de_comecar_400(cliente, cabecalhos, banco):
    resposta = cadastrar(cliente, cabecalhos, vigencia_inicio="2026-12-18", vigencia_fim="2026-02-02")

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "O fim da vigência não pode ser anterior ao início."


def test_identificador_repetido_409(cliente, cabecalhos, banco):
    cadastrar(cliente, cabecalhos)

    resposta = cadastrar(cliente, cabecalhos, nome="Outro programa", identificador="scfv")

    assert resposta.status_code == 409
    assert resposta.json()["detail"] == "Já existe um programa com esse identificador."


def test_data_mal_formatada_continua_422(cliente, cabecalhos, banco):
    resposta = cadastrar(cliente, cabecalhos, vigencia_inicio="02/02/2026")

    assert resposta.status_code == 422


def test_programa_inexistente_404(cliente, cabecalhos, banco):
    for rota in ("", "/convenios", "/vagas"):
        resposta = cliente.get(f"/gestao/programas/nao-existe{rota}", headers=cabecalhos)
        assert resposta.status_code == 404, rota
        assert resposta.json()["detail"] == "Programa não encontrado."


def test_programa_antigo_so_com_nome_aparece_na_consulta(cliente, cabecalhos, banco):
    with banco.begin() as conexao:
        conexao.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear')"))

    resposta = cliente.get("/gestao/programas/p-1", headers=cabecalhos)

    assert resposta.status_code == 200
    assert resposta.json()["identificador"] is None
    assert resposta.json()["nome"] == "Semear"


def test_cadastra_e_lista_convenios_do_programa(cliente, cabecalhos, banco):
    programa_id = cadastrar(cliente, cabecalhos).json()["id"]
    url = f"/gestao/programas/{programa_id}/convenios"

    criado = cliente.post(
        url,
        json={
            "nome": "Convênio municipal 2026",
            "concedente": "Prefeitura de Porto Alegre",
            "vigencia_inicio": "2026-01-01",
            "vigencia_fim": "2026-12-31",
        },
        headers=cabecalhos,
    )
    so_nome = cliente.post(url, json={"nome": "Apoio Instituto Semear"}, headers=cabecalhos)

    assert criado.status_code == 201
    assert so_nome.status_code == 201
    assert [c["nome"] for c in cliente.get(url, headers=cabecalhos).json()] == [
        "Apoio Instituto Semear",
        "Convênio municipal 2026",
    ]


@pytest.mark.parametrize(
    "corpo, mensagem",
    [
        ({}, "Convênio sem nome."),
        (
            {"nome": "Convênio", "vigencia_inicio": "2026-12-31", "vigencia_fim": "2026-01-01"},
            "O fim da vigência do convênio não pode ser anterior ao início.",
        ),
    ],
)
def test_convenio_invalido_400(cliente, cabecalhos, banco, corpo, mensagem):
    programa_id = cadastrar(cliente, cabecalhos).json()["id"]

    resposta = cliente.post(f"/gestao/programas/{programa_id}/convenios", json=corpo, headers=cabecalhos)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == mensagem


def test_cadastra_e_lista_vagas_do_programa(cliente, cabecalhos, banco):
    programa_id = cadastrar(cliente, cabecalhos).json()["id"]
    url = f"/gestao/programas/{programa_id}/vagas"

    cliente.post(url, json={"descricao": "Tarde · 11 a 15 anos", "quantidade": 40}, headers=cabecalhos)
    cliente.post(url, json={"descricao": "Manhã · 6 a 10 anos", "quantidade": 40}, headers=cabecalhos)

    assert [(v["descricao"], v["quantidade"]) for v in cliente.get(url, headers=cabecalhos).json()] == [
        ("Manhã · 6 a 10 anos", 40),
        ("Tarde · 11 a 15 anos", 40),
    ]


@pytest.mark.parametrize(
    "corpo, status, mensagem",
    [
        ({}, 400, "Vagas sem descrição e quantidade."),
        ({"descricao": "Manhã", "quantidade": 0}, 400, "A quantidade de vagas deve ser maior que zero."),
        ({"descricao": "manhã", "quantidade": 10}, 409, "Já existem vagas com essa descrição neste programa."),
    ],
)
def test_vagas_invalidas_ou_repetidas(cliente, cabecalhos, banco, corpo, status, mensagem):
    programa_id = cadastrar(cliente, cabecalhos).json()["id"]
    url = f"/gestao/programas/{programa_id}/vagas"
    cliente.post(url, json={"descricao": "Manhã", "quantidade": 20}, headers=cabecalhos)

    resposta = cliente.post(url, json=corpo, headers=cabecalhos)

    assert resposta.status_code == status
    assert resposta.json()["detail"] == mensagem


def test_cadastro_sem_autenticacao_401(cliente):
    assert cliente.post("/gestao/programas", json=PROGRAMA).status_code == 401
