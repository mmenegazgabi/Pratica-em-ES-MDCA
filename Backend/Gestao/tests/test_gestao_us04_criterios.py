"""Critérios da US-04: lista de espera, desligamento e conflito de horário (T-54).

Cada seção é um critério do card:

1. a inscrição em turma lotada vai para a lista de espera;
2. o desligamento sem motivo ou data falha;
3. o conflito de horário gera alerta.

Os testes de cada rota ficam em ``test_gestao_turmas.py``. Aqui tudo passa pela API, como
no uso real: a coordenação cadastra a turma, inscreve e registra o desligamento. O alerta
de conflito é o que a coordenação recebe: os ``conflitos`` na resposta da inscrição, o
registro em ``log_auditoria`` (ação ``conflito_de_horario``) e o conflito no detalhe da
turma. Contra o banco de teste (TEST_DATABASE_URL).
"""

from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

HOJE = date.today()
PROGRAMA = "/gestao/programas/p-1"
ARTE = {
    "nome": "Oficina de arte",
    "espaco_id": "e-1",
    "responsavel_id": "jessica",
    "capacidade": 2,
    "dias_semana": [1, 3],
    "hora_inicio": "14:00",
    "hora_fim": "16:00",
}
PESSOAS = ["pe-lara", "pe-davi", "pe-maria", "pe-joana"]


@pytest.fixture
def programa(banco):
    """Programa Semear (p-1) com o espaço Ateliê (e-1).

    Equipe: Ana (coordenação) e Jéssica (educadora, responsável pelas turmas).
    Pessoas atendidas: Lara, Davi, Maria e Joana.
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
        c.execute(sa.text("INSERT INTO espacos (id, programa_id, nome) VALUES ('e-1', 'p-1', 'Ateliê')"))
        c.execute(sa.text("INSERT INTO nucleos_familiares (id, nome) VALUES ('f-1', 'Oliveira')"))
        c.execute(
            sa.text(
                "INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id) "
                "VALUES (:id, :nome, lower(:nome), '2014-01-01', 'f-1', 'p-1')"
            ),
            [
                {"id": "pe-lara", "nome": "Lara"},
                {"id": "pe-davi", "nome": "Davi"},
                {"id": "pe-maria", "nome": "Maria"},
                {"id": "pe-joana", "nome": "Joana"},
            ],
        )
    return banco


def como(cabecalhos, usuario="ana"):
    return {**cabecalhos, "X-Usuario-Id": usuario}


def criar_turma(cliente, cabecalhos, **campos):
    resposta = cliente.post(f"{PROGRAMA}/turmas", json={**ARTE, **campos}, headers=como(cabecalhos))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def inscrever(cliente, cabecalhos, turma_id, pessoa_id):
    resposta = cliente.post(f"{PROGRAMA}/turmas/{turma_id}/matriculas", json={"pessoa_id": pessoa_id}, headers=como(cabecalhos))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def detalhe(cliente, cabecalhos, turma_id):
    resposta = cliente.get(f"{PROGRAMA}/turmas/{turma_id}", headers=como(cabecalhos))
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def trajetoria(cliente, cabecalhos, pessoa_id):
    resposta = cliente.get(f"/gestao/pessoas/{pessoa_id}/trajetoria", headers=como(cabecalhos))
    assert resposta.status_code == 200, resposta.text
    return {e["titulo"]: e["descricao"] for e in resposta.json()}


def alertas_de_conflito(banco):
    with banco.connect() as c:
        linhas = c.execute(
            sa.text("SELECT usuario_id, alvo_tipo, alvo_id, detalhes FROM log_auditoria WHERE acao = 'conflito_de_horario' ORDER BY id")
        )
        return [dict(l._mapping) for l in linhas]


# --- 1. Inscrição em turma lotada vai para a lista de espera ------------------------------


@pytest.mark.parametrize("capacidade", [1, 2, 3])
def test_turma_lotada_a_inscricao_vai_para_a_lista_de_espera(cliente, cabecalhos, programa, capacidade):
    turma = criar_turma(cliente, cabecalhos, capacidade=capacidade)
    for pessoa in PESSOAS[:capacidade]:
        assert inscrever(cliente, cabecalhos, turma["id"], pessoa)["matricula"]["situacao"] == "ativa"

    excedente = PESSOAS[capacidade]
    resposta = inscrever(cliente, cabecalhos, turma["id"], excedente)

    # A inscrição é salva, mas não ocupa vaga: entra na fila, sem data de entrada.
    matricula = resposta["matricula"]
    assert (matricula["pessoa_id"], matricula["situacao"], matricula["posicao_espera"], matricula["data_entrada"]) == (excedente, "espera", 1, None)
    visto = detalhe(cliente, cabecalhos, turma["id"])
    assert (visto["turma"]["ativas"], visto["turma"]["em_espera"], visto["turma"]["vagas_livres"]) == (capacidade, 1, 0)
    assert sorted(m["pessoa_id"] for m in visto["matriculas"]) == sorted(PESSOAS[:capacidade])
    assert [m["pessoa_id"] for m in visto["lista_de_espera"]] == [excedente]
    # Na trajetória, a pessoa aparece aguardando vaga, ainda sem matrícula.
    eventos = trajetoria(cliente, cabecalhos, excedente)
    assert eventos["Lista de espera da turma Oficina de arte"] == "Inscrição aguardando vaga."
    assert "Matrícula na turma Oficina de arte" not in eventos


def test_cada_inscricao_em_turma_lotada_entra_no_fim_da_lista_de_espera(cliente, cabecalhos, programa):
    turma = criar_turma(cliente, cabecalhos, capacidade=1)
    inscrever(cliente, cabecalhos, turma["id"], "pe-lara")

    na_espera = [inscrever(cliente, cabecalhos, turma["id"], p)["matricula"] for p in ("pe-davi", "pe-maria", "pe-joana")]

    assert [(m["situacao"], m["posicao_espera"]) for m in na_espera] == [("espera", 1), ("espera", 2), ("espera", 3)]
    visto = detalhe(cliente, cabecalhos, turma["id"])
    assert [m["pessoa"] for m in visto["matriculas"]] == ["Lara"]
    assert [(m["pessoa"], m["posicao_espera"]) for m in visto["lista_de_espera"]] == [("Davi", 1), ("Maria", 2), ("Joana", 3)]


# --- 2. Desligamento sem motivo ou data falha --------------------------------------------


@pytest.fixture
def matricula(cliente, cabecalhos, programa):
    """Lara matriculada na Oficina de arte, turma de uma vaga: (turma_id, matricula_id)."""
    turma = criar_turma(cliente, cabecalhos, capacidade=1)
    return turma["id"], inscrever(cliente, cabecalhos, turma["id"], "pe-lara")["matricula"]["id"]


def desligar(cliente, cabecalhos, matricula, corpo):
    turma_id, matricula_id = matricula
    return cliente.patch(f"{PROGRAMA}/turmas/{turma_id}/matriculas/{matricula_id}/desligamento", json=corpo, headers=como(cabecalhos))


@pytest.mark.parametrize(
    "corpo, mensagem",
    [
        ({}, "Informe data e motivo do desligamento."),
        ({"motivo": "Mudou de cidade"}, "Informe data do desligamento."),
        ({"data_saida": None, "motivo": "Mudou de cidade"}, "Informe data do desligamento."),
        ({"data_saida": HOJE.isoformat()}, "Informe motivo do desligamento."),
        ({"data_saida": HOJE.isoformat(), "motivo": ""}, "Informe motivo do desligamento."),
        ({"data_saida": HOJE.isoformat(), "motivo": "  \n "}, "Informe motivo do desligamento."),
    ],
    ids=["sem-data-e-motivo", "sem-data", "data-nula", "sem-motivo", "motivo-vazio", "motivo-em-branco"],
)
def test_desligamento_sem_motivo_ou_data_falha_e_a_matricula_segue_ativa(cliente, cabecalhos, programa, matricula, corpo, mensagem):
    resposta = desligar(cliente, cabecalhos, matricula, corpo)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == mensagem
    visto = detalhe(cliente, cabecalhos, matricula[0])
    assert [(m["id"], m["situacao"], m["data_saida"], m["motivo_saida"]) for m in visto["matriculas"]] == [(matricula[1], "ativa", None, None)]
    assert visto["desligadas"] == []
    # A vaga não é liberada e o desligamento não entra na trajetória.
    assert visto["turma"]["vagas_livres"] == 0
    assert "Desligamento da turma Oficina de arte" not in trajetoria(cliente, cabecalhos, "pe-lara")


@pytest.mark.parametrize("data_saida, motivo", [(None, "Mudou de cidade"), (HOJE, None), (HOJE, "   ")], ids=["sem-data", "sem-motivo", "motivo-em-branco"])
def test_o_banco_tambem_recusa_desligar_sem_motivo_ou_data(programa, matricula, data_saida, motivo):
    with pytest.raises(IntegrityError, match="ck_matriculas_desligamento_com_data_e_motivo"):
        with programa.begin() as c:
            c.execute(
                sa.text("UPDATE matriculas SET situacao = 'desligada', data_saida = :saida, motivo_saida = :motivo WHERE id = :id"),
                {"saida": data_saida, "motivo": motivo, "id": matricula[1]},
            )


def test_com_data_e_motivo_o_desligamento_e_registrado_uma_vez(cliente, cabecalhos, programa, matricula):
    resposta = desligar(cliente, cabecalhos, matricula, {"data_saida": HOJE.isoformat(), "motivo": "  Mudou de cidade  "})

    assert resposta.status_code == 200
    saida = resposta.json()
    assert (saida["situacao"], saida["data_saida"], saida["motivo_saida"]) == ("desligada", HOJE.isoformat(), "Mudou de cidade")
    # A matrícula fica no histórico da turma e na trajetória, e a vaga é liberada.
    visto = detalhe(cliente, cabecalhos, matricula[0])
    assert [(m["pessoa"], m["motivo_saida"]) for m in visto["desligadas"]] == [("Lara", "Mudou de cidade")]
    assert visto["turma"]["vagas_livres"] == 1
    assert trajetoria(cliente, cabecalhos, "pe-lara")["Desligamento da turma Oficina de arte"] == "Mudou de cidade"
    # Não desliga de novo.
    assert desligar(cliente, cabecalhos, matricula, {"data_saida": HOJE.isoformat(), "motivo": "Outro."}).status_code == 409


# --- 3. Conflito de horário gera alerta --------------------------------------------------


@pytest.mark.parametrize(
    "dias, inicio, fim",
    [
        ([1, 3], "14:00", "16:00"),
        ([3, 5], "15:00", "17:00"),
        ([1], "13:00", "15:00"),
        ([3], "14:30", "15:30"),
        ([2, 3, 4], "15:59", "18:00"),
    ],
    ids=["mesmo-horario", "comeca-no-meio", "termina-no-meio", "dentro", "um-dia-e-um-minuto"],
)
def test_conflito_de_horario_salva_a_matricula_e_gera_alerta(cliente, cabecalhos, programa, dias, inicio, fim):
    arte = criar_turma(cliente, cabecalhos)  # seg e qua, 14h às 16h
    musica = criar_turma(cliente, cabecalhos, nome="Música", dias_semana=dias, hora_inicio=inicio, hora_fim=fim)
    inscrever(cliente, cabecalhos, arte["id"], "pe-lara")

    resposta = inscrever(cliente, cabecalhos, musica["id"], "pe-lara")

    # A inscrição não é barrada: a matrícula é salva e o conflito volta para a coordenação.
    matricula = resposta["matricula"]
    assert matricula["situacao"] == "ativa"
    assert resposta["conflitos"] == [
        {"turma_id": arte["id"], "turma": "Oficina de arte", "dias_semana": [1, 3], "hora_inicio": "14:00:00", "hora_fim": "16:00:00"}
    ]
    # O alerta fica na trilha de auditoria, com quem inscreveu e a turma em conflito.
    assert alertas_de_conflito(programa) == [
        {
            "usuario_id": "ana",
            "alvo_tipo": "matricula",
            "alvo_id": matricula["id"],
            "detalhes": {"programa_id": "p-1", "turma_id": musica["id"], "pessoa_id": "pe-lara", "turmas_em_conflito": [arte["id"]]},
        }
    ]
    # E aparece no detalhe da turma, na matrícula em conflito.
    [na_musica] = detalhe(cliente, cabecalhos, musica["id"])["matriculas"]
    assert [c["turma"] for c in na_musica["conflitos"]] == ["Oficina de arte"]


@pytest.mark.parametrize(
    "dias, inicio, fim",
    [([1, 3], "16:00", "18:00"), ([1, 3], "12:00", "14:00"), ([2, 4, 5], "14:00", "16:00")],
    ids=["comeca-quando-a-outra-acaba", "acaba-quando-a-outra-comeca", "outros-dias"],
)
def test_sem_conflito_de_horario_nao_ha_alerta(cliente, cabecalhos, programa, dias, inicio, fim):
    arte = criar_turma(cliente, cabecalhos)
    outra = criar_turma(cliente, cabecalhos, nome="Outra", dias_semana=dias, hora_inicio=inicio, hora_fim=fim)
    inscrever(cliente, cabecalhos, arte["id"], "pe-lara")

    resposta = inscrever(cliente, cabecalhos, outra["id"], "pe-lara")

    assert resposta["conflitos"] == []
    assert alertas_de_conflito(programa) == []
