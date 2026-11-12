"""Critérios da US-03: duplicidade, responsável legal e uso de imagem (T-50).

Cada seção é um critério do card:

1. o cadastro com mesmo nome, nascimento e responsável gera alerta;
2. o menor sem responsável legal é bloqueado;
3. o uso de imagem com autorização vencida ou revogada é bloqueado.

Os testes de cada rota ficam em ``test_gestao_pessoas.py``. Aqui tudo passa pela API, como
no uso real: a coordenação cadastra a pessoa e registra ou revoga a autorização, e a
educadora pede o uso externo da imagem. Contra o banco de teste (TEST_DATABASE_URL).
"""

from datetime import date, timedelta

import pytest
import sqlalchemy as sa

HOJE = date.today()
ONTEM = HOJE - timedelta(days=1)
DAQUI_A_UM_ANO = HOJE + timedelta(days=365)
# Quem faz 18 anos hoje já é maior (em 29/02, quem nasceu em 28/02); um dia depois, ainda é menor.
try:
    FEZ_18_HOJE = HOJE.replace(year=HOJE.year - 18)
except ValueError:
    FEZ_18_HOJE = date(HOJE.year - 18, 2, 28)
FAZ_18_AMANHA = FEZ_18_HOJE + timedelta(days=1)

PESSOAS = "/gestao/pessoas"
USO_DE_IMAGEM = "/gestao/pessoas/uso-de-imagem"


@pytest.fixture
def programa(banco):
    """Programa Semear (p-1).

    Equipe: Ana (coordenação) e Jéssica (educadora).
    Núcleo Oliveira: Lara (12/05/2013, responsável legal Marina Oliveira), Davi e Maria.
    """
    with banco.begin() as c:
        c.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear')"))
        c.execute(
            sa.text("INSERT INTO usuarios (id, nome) VALUES (:id, :nome)"),
            [{"id": "ana", "nome": "Ana Martins"}, {"id": "jessica", "nome": "Jéssica Almeida"}],
        )
        c.execute(sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('ana', 'coordenacao')"))
        c.execute(
            sa.text("INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) VALUES (:id, :u, 'p-1', :papel, '2025-01-01')"),
            [{"id": "v2", "u": "jessica", "papel": "educador"}],
        )
        c.execute(sa.text("INSERT INTO nucleos_familiares (id, nome) VALUES ('f-oliveira', 'Oliveira')"))
        c.execute(
            sa.text(
                "INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id) "
                "VALUES (:id, :nome, lower(:nome), :nascimento, 'f-oliveira', 'p-1')"
            ),
            [
                {"id": "pe-lara", "nome": "Lara Oliveira", "nascimento": "2013-05-12"},
                {"id": "pe-davi", "nome": "Davi Oliveira", "nascimento": "2016-02-01"},
                {"id": "pe-maria", "nome": "Maria Oliveira", "nascimento": "2018-07-20"},
            ],
        )
        c.execute(sa.text("INSERT INTO responsaveis (id, nome, nome_normalizado) VALUES ('r-marina', 'Marina Oliveira', 'marina oliveira')"))
        c.execute(
            sa.text(
                "INSERT INTO pessoas_responsaveis (pessoa_id, responsavel_id, parentesco, responsavel_legal) "
                "VALUES ('pe-lara', 'r-marina', 'Mãe', true)"
            )
        )
    return banco


def como(cabecalhos, usuario="ana"):
    return {**cabecalhos, "X-Usuario-Id": usuario}


def cadastrar(cliente, cabecalhos, **dados):
    """Cadastra uma criança nova no p-1 (Sofia Costa, com responsável legal), com as mudanças do caso."""
    corpo = {
        "programa_id": "p-1",
        "nome": "Sofia Costa",
        "data_nascimento": "2015-01-23",
        "nucleo_familiar_nome": "Costa",
        "responsaveis": [{"nome": "Daniela Costa", "parentesco": "Mãe", "responsavel_legal": True}],
        **dados,
    }
    return cliente.post(PESSOAS, json=corpo, headers=como(cabecalhos))


def total(banco, tabela):
    with banco.connect() as c:
        return c.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar_one()


def eventos_de_auditoria(banco, acao):
    with banco.connect() as c:
        linhas = c.execute(
            sa.text("SELECT usuario_id, alvo_tipo, alvo_id, detalhes FROM log_auditoria WHERE acao = :a ORDER BY id"), {"a": acao}
        )
        return [dict(l._mapping) for l in linhas]


# --- 1. Cadastro com mesmo nome, nascimento e responsável gera alerta ---------------------


def como_a_lara(**dados):
    """Os dados da Lara já cadastrada: mesmo nome, nascimento, núcleo e responsável legal."""
    return {
        "nome": "Lara Oliveira",
        "data_nascimento": "2013-05-12",
        "nucleo_familiar_id": "f-oliveira",
        "nucleo_familiar_nome": None,
        "responsaveis": [{"id": "r-marina", "parentesco": "Mãe", "responsavel_legal": True}],
        **dados,
    }


@pytest.mark.parametrize(
    "dados",
    [
        {},
        {"nome": "  LÁRA   oliveira "},
        {"responsaveis": [{"nome": "marina  OLIVEIRA", "parentesco": "Mãe", "responsavel_legal": True}]},
    ],
    ids=["mesmos-dados", "nome-escrito-diferente", "responsavel-digitado-de-novo"],
)
def test_mesmo_nome_nascimento_e_responsavel_gera_alerta_e_nada_e_gravado(cliente, cabecalhos, programa, dados):
    resposta = cadastrar(cliente, cabecalhos, **como_a_lara(**dados))

    assert resposta.status_code == 409
    alerta = resposta.json()["detail"]
    assert (alerta["codigo"], alerta["mensagem"]) == ("possivel_duplicidade", "Possível duplicidade: confira os cadastros semelhantes antes de concluir.")
    assert [(c["id"], c["nome"], c["data_nascimento"], c["responsaveis"], c["motivos"]) for c in alerta["candidatos"]] == [
        ("pe-lara", "Lara Oliveira", "2013-05-12", ["Marina Oliveira"], ["nascimento", "responsavel"])
    ]
    # Sem a confirmação de quem cadastra, nada é gravado (nem o responsável digitado de novo).
    assert (total(programa, "pessoas"), total(programa, "responsaveis"), total(programa, "pessoas_responsaveis")) == (3, 1, 1)


def test_depois_do_alerta_o_cadastro_confirmado_segue_e_fica_na_auditoria(cliente, cabecalhos, programa):
    resposta = cadastrar(cliente, cabecalhos, **como_a_lara(confirmar_duplicidade=True))

    assert resposta.status_code == 201
    assert total(programa, "pessoas") == 4
    assert eventos_de_auditoria(programa, "duplicidade_confirmada") == [
        {"usuario_id": "ana", "alvo_tipo": "pessoa", "alvo_id": resposta.json()["id"], "detalhes": {"semelhantes": ["pe-lara"]}}
    ]


def test_mesmo_nome_sem_nascimento_nem_responsavel_em_comum_nao_gera_alerta(cliente, cabecalhos, programa):
    resposta = cadastrar(
        cliente,
        cabecalhos,
        **como_a_lara(data_nascimento="2014-02-01", responsaveis=[{"nome": "Paulo Oliveira", "parentesco": "Pai", "responsavel_legal": True}]),
    )

    assert resposta.status_code == 201
    assert eventos_de_auditoria(programa, "duplicidade_confirmada") == []


# --- 2. Menor sem responsável legal é bloqueado -------------------------------------------


@pytest.mark.parametrize("nascimento", ["2015-01-23", FAZ_18_AMANHA.isoformat()], ids=["crianca", "faz-18-amanha"])
@pytest.mark.parametrize(
    "responsaveis",
    [
        [],
        [{"nome": "Pedro Costa", "parentesco": "Tio", "responsavel_legal": False}],
        [{"id": "r-marina", "parentesco": "Tia"}],
    ],
    ids=["sem-responsavel", "responsavel-nao-legal", "responsavel-ja-cadastrado-nao-legal"],
)
def test_menor_sem_responsavel_legal_e_bloqueado_e_nada_e_gravado(cliente, cabecalhos, programa, nascimento, responsaveis):
    resposta = cadastrar(cliente, cabecalhos, data_nascimento=nascimento, responsaveis=responsaveis)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Informe ao menos um responsável legal para uma pessoa menor de idade."
    # Nem a pessoa, nem o núcleo novo, nem o responsável ou o vínculo com ele.
    assert total(programa, "pessoas") == 3
    assert total(programa, "nucleos_familiares") == 1
    assert total(programa, "responsaveis") == 1
    assert total(programa, "pessoas_responsaveis") == 1


@pytest.mark.parametrize(
    "dados",
    [
        {},
        {"nucleo_familiar_id": "f-oliveira", "nucleo_familiar_nome": None, "responsaveis": [{"id": "r-marina", "parentesco": "Mãe", "responsavel_legal": True}]},
        {"responsaveis": [{"nome": "Pedro Costa", "parentesco": "Tio"}, {"nome": "Daniela Costa", "parentesco": "Mãe", "responsavel_legal": True}]},
    ],
    ids=["responsavel-legal-novo", "responsavel-legal-ja-cadastrado", "um-dos-responsaveis-e-legal"],
)
def test_menor_com_responsavel_legal_e_cadastrado(cliente, cabecalhos, programa, dados):
    resposta = cadastrar(cliente, cabecalhos, **dados)

    assert resposta.status_code == 201
    assert any(r["responsavel_legal"] for r in resposta.json()["responsaveis"])


def test_quem_ja_fez_18_anos_nao_precisa_de_responsavel_legal(cliente, cabecalhos, programa):
    resposta = cadastrar(cliente, cabecalhos, data_nascimento=FEZ_18_HOJE.isoformat(), responsaveis=[])

    assert resposta.status_code == 201


# --- 3. Uso de imagem com autorização vencida ou revogada é bloqueado ---------------------


def deixar_autorizacao(cliente, cabecalhos, pessoa_id, situacao, valida_ate=DAQUI_A_UM_ANO):
    """Registra a autorização de imagem da pessoa já na situação pedida."""
    corpo = {"tipo": "uso_de_imagem", "valida_ate": valida_ate.isoformat()}
    if situacao == "vencida":
        corpo = {**corpo, "valida_de": (HOJE - timedelta(days=365)).isoformat(), "valida_ate": ONTEM.isoformat()}
    resposta = cliente.post(f"{PESSOAS}/{pessoa_id}/autorizacoes", json=corpo, headers=como(cabecalhos))
    assert resposta.status_code == 201, resposta.text
    if situacao == "revogada":
        revogacao = cliente.post(f"{PESSOAS}/{pessoa_id}/autorizacoes/{resposta.json()['id']}/revogacao", headers=como(cabecalhos))
        assert revogacao.status_code == 200, revogacao.text


def usar_imagem(cliente, cabecalhos, pessoa_ids):
    return cliente.post(USO_DE_IMAGEM, json={"pessoa_ids": pessoa_ids, "uso": "externo"}, headers=como(cabecalhos, "jessica"))


@pytest.mark.parametrize("situacao", ["vencida", "revogada"])
def test_uso_de_imagem_com_autorizacao_vencida_ou_revogada_e_bloqueado(cliente, cabecalhos, programa, situacao):
    deixar_autorizacao(cliente, cabecalhos, "pe-lara", situacao)

    resposta = usar_imagem(cliente, cabecalhos, ["pe-lara"])

    assert resposta.status_code == 409
    bloqueio = resposta.json()["detail"]
    assert bloqueio["codigo"] == "uso_de_imagem_bloqueado"
    assert bloqueio["bloqueios"] == [{"pessoa_id": "pe-lara", "nome": "Lara Oliveira", "motivo": situacao}]
    # O cadastro mostra a mesma situação.
    assert cliente.get(f"{PESSOAS}/pe-lara", headers=como(cabecalhos)).json()["autorizacao_imagem"] == situacao


def test_no_grupo_o_uso_e_bloqueado_e_aponta_quem_tem_autorizacao_vencida_ou_revogada(cliente, cabecalhos, programa):
    deixar_autorizacao(cliente, cabecalhos, "pe-lara", "vigente")
    deixar_autorizacao(cliente, cabecalhos, "pe-davi", "vencida")
    deixar_autorizacao(cliente, cabecalhos, "pe-maria", "revogada")

    resposta = usar_imagem(cliente, cabecalhos, ["pe-lara", "pe-davi", "pe-maria"])

    assert resposta.status_code == 409
    assert [(b["pessoa_id"], b["motivo"]) for b in resposta.json()["detail"]["bloqueios"]] == [("pe-davi", "vencida"), ("pe-maria", "revogada")]


@pytest.mark.parametrize("valida_ate", [HOJE, DAQUI_A_UM_ANO], ids=["vence-hoje", "daqui-a-um-ano"])
def test_com_autorizacao_vigente_o_uso_de_imagem_e_liberado(cliente, cabecalhos, programa, valida_ate):
    deixar_autorizacao(cliente, cabecalhos, "pe-lara", "vigente", valida_ate=valida_ate)

    resposta = usar_imagem(cliente, cabecalhos, ["pe-lara"])

    assert resposta.status_code == 200
    assert resposta.json() == {"liberado": True, "bloqueios": []}
