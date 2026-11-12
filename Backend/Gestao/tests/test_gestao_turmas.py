"""T-52 · US-04: API de turmas, matrículas, lista de espera, desligamento e conflito de horário."""

from datetime import date, timedelta

import pytest
import sqlalchemy as sa

HOJE = date.today()
P1 = "/gestao/programas/p-1"
TURMA = {
    "nome": "Oficina de arte",
    "espaco_id": "e-1",
    "responsavel_id": "jessica",
    "capacidade": 2,
    "dias_semana": [1, 3],
    "hora_inicio": "14:00",
    "hora_fim": "16:00",
}


@pytest.fixture
def programa(banco):
    """p-1 (Semear, espaço e-1) e p-2 (Oficina, espaço e-2).

    - ana: coordenação (na conta)    - jessica: educadora em p-1
    - rafael: saiu de p-1 ontem      - dora: direção   - admin: administração
    - Pessoas de p-1: Lara, Davi, Maria, Joana; de p-2: Pedro
    """
    with banco.begin() as c:
        c.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear'), ('p-2', 'Oficina')"))
        c.execute(
            sa.text("INSERT INTO usuarios (id, nome) VALUES (:id, :nome)"),
            [{"id": u, "nome": n} for u, n in [("ana", "Ana Martins"), ("jessica", "Jéssica Almeida"), ("rafael", "Rafael Nunes"), ("dora", "Dora"), ("admin", "Administração")]],
        )
        c.execute(sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('ana', 'coordenacao'), ('dora', 'direcao'), ('admin', 'administracao')"))
        c.execute(
            sa.text(
                "INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada, data_saida) VALUES "
                "('v2', 'jessica', 'p-1', 'educador', '2025-01-01', NULL), "
                "('v3', 'rafael', 'p-1', 'psicologo', '2025-01-01', :ontem)"
            ),
            {"ontem": HOJE - timedelta(days=1)},
        )
        c.execute(sa.text("INSERT INTO espacos (id, programa_id, nome) VALUES ('e-1', 'p-1', 'Ateliê'), ('e-2', 'p-2', 'Sala')"))
        c.execute(sa.text("INSERT INTO nucleos_familiares (id, nome) VALUES ('f-1', 'Família')"))
        c.execute(
            sa.text(
                "INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id) "
                "VALUES (:id, :nome, lower(:nome), '1990-01-01', 'f-1', :programa)"
            ),
            [
                {"id": "pe-lara", "nome": "Lara", "programa": "p-1"},
                {"id": "pe-davi", "nome": "Davi", "programa": "p-1"},
                {"id": "pe-maria", "nome": "Maria", "programa": "p-1"},
                {"id": "pe-joana", "nome": "Joana", "programa": "p-1"},
                {"id": "pe-pedro", "nome": "Pedro", "programa": "p-2"},
            ],
        )
    return banco


def como(cabecalhos, usuario="ana"):
    return {**cabecalhos, "X-Usuario-Id": usuario}


def criar_turma(cliente, cabecalhos, **campos):
    resposta = cliente.post(f"{P1}/turmas", json={**TURMA, **campos}, headers=como(cabecalhos))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def inscrever(cliente, cabecalhos, turma_id, pessoa_id, status=201):
    resposta = cliente.post(f"{P1}/turmas/{turma_id}/matriculas", json={"pessoa_id": pessoa_id}, headers=como(cabecalhos))
    assert resposta.status_code == status, resposta.text
    return resposta.json()


def detalhe(cliente, cabecalhos, turma_id, usuario="ana"):
    resposta = cliente.get(f"{P1}/turmas/{turma_id}", headers=como(cabecalhos, usuario))
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def eventos(banco, acao):
    with banco.connect() as c:
        return [tuple(r) for r in c.execute(sa.text("SELECT usuario_id, alvo_tipo, detalhes FROM log_auditoria WHERE acao = :a ORDER BY id"), {"a": acao})]


# --- Turma ---------------------------------------------------------------------


def test_cadastra_turma_e_lista_com_vagas(cliente, cabecalhos, programa):
    turma = criar_turma(cliente, cabecalhos)

    assert turma["espaco"] == "Ateliê"
    assert turma["responsavel"] == "Jéssica Almeida"
    assert (turma["dias_semana"], turma["hora_inicio"], turma["hora_fim"]) == ([1, 3], "14:00:00", "16:00:00")
    lista = cliente.get(f"{P1}/turmas", headers=como(cabecalhos, "dora")).json()
    assert [(t["nome"], t["capacidade"], t["ativas"], t["em_espera"], t["vagas_livres"]) for t in lista] == [("Oficina de arte", 2, 0, 0, 2)]


def test_turma_sem_campos_obrigatorios_400_com_a_lista(cliente, cabecalhos, programa):
    resposta = cliente.post(f"{P1}/turmas", json={"nome": "X", "capacidade": 5}, headers=como(cabecalhos))

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Turma sem local, responsável, dias da semana, horário de início e horário de término."


@pytest.mark.parametrize(
    "campos, mensagem",
    [
        ({"espaco_id": "e-2"}, "Escolha um local cadastrado neste programa."),
        ({"responsavel_id": "dora"}, "O responsável precisa ter vínculo ativo na equipe do programa."),
        ({"responsavel_id": "rafael"}, "O responsável precisa ter vínculo ativo na equipe do programa."),
        ({"capacidade": 0}, "A turma precisa de ao menos uma vaga."),
        ({"dias_semana": [0, 8]}, "Dias da semana válidos: 1 (segunda) a 7 (domingo)."),
        ({"hora_fim": "13:00"}, "O horário de término precisa ser depois do início."),
    ],
)
def test_regras_do_cadastro_da_turma(cliente, cabecalhos, programa, campos, mensagem):
    resposta = cliente.post(f"{P1}/turmas", json={**TURMA, **campos}, headers=como(cabecalhos))

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == mensagem


def test_nome_repetido_no_programa_409(cliente, cabecalhos, programa):
    criar_turma(cliente, cabecalhos)

    resposta = cliente.post(f"{P1}/turmas", json={**TURMA, "nome": "OFICINA DE ARTE"}, headers=como(cabecalhos))

    assert resposta.status_code == 409


def test_edita_turma_mas_capacidade_nao_fica_abaixo_das_ativas(cliente, cabecalhos, programa):
    turma = criar_turma(cliente, cabecalhos)
    inscrever(cliente, cabecalhos, turma["id"], "pe-lara")
    inscrever(cliente, cabecalhos, turma["id"], "pe-davi")

    editada = cliente.patch(f"{P1}/turmas/{turma['id']}", json={"nome": "Arte e cor", "capacidade": 3}, headers=como(cabecalhos))
    menor = cliente.patch(f"{P1}/turmas/{turma['id']}", json={"capacidade": 1}, headers=como(cabecalhos))

    assert editada.status_code == 200
    assert (editada.json()["nome"], editada.json()["vagas_livres"]) == ("Arte e cor", 1)
    assert menor.status_code == 409


# --- Matrícula e lista de espera -------------------------------------------------


def test_com_vaga_matricula_e_lotada_vai_para_a_lista_de_espera_em_ordem(cliente, cabecalhos, programa):
    turma = criar_turma(cliente, cabecalhos)

    lara = inscrever(cliente, cabecalhos, turma["id"], "pe-lara")["matricula"]
    davi = inscrever(cliente, cabecalhos, turma["id"], "pe-davi")["matricula"]
    maria = inscrever(cliente, cabecalhos, turma["id"], "pe-maria")["matricula"]
    joana = inscrever(cliente, cabecalhos, turma["id"], "pe-joana")["matricula"]

    assert (lara["situacao"], lara["data_entrada"]) == ("ativa", HOJE.isoformat())
    assert davi["situacao"] == "ativa"
    assert (maria["situacao"], maria["posicao_espera"], maria["data_entrada"]) == ("espera", 1, None)
    assert (joana["situacao"], joana["posicao_espera"]) == ("espera", 2)
    visto = detalhe(cliente, cabecalhos, turma["id"], "jessica")
    assert [m["pessoa"] for m in visto["matriculas"]] == ["Davi", "Lara"]
    assert [(m["pessoa"], m["posicao_espera"]) for m in visto["lista_de_espera"]] == [("Maria", 1), ("Joana", 2)]
    assert (visto["turma"]["ativas"], visto["turma"]["em_espera"], visto["turma"]["vagas_livres"]) == (2, 2, 0)


def test_pessoa_de_outro_programa_400_e_inscricao_repetida_409(cliente, cabecalhos, programa):
    turma = criar_turma(cliente, cabecalhos)
    inscrever(cliente, cabecalhos, turma["id"], "pe-lara")

    outro = inscrever(cliente, cabecalhos, turma["id"], "pe-pedro", status=400)
    repetida = inscrever(cliente, cabecalhos, turma["id"], "pe-lara", status=409)

    assert outro["detail"] == "A pessoa precisa estar cadastrada no mesmo programa da turma."
    assert repetida["detail"] == "Essa pessoa já está matriculada ou na lista de espera desta turma."
    assert inscrever(cliente, cabecalhos, turma["id"], "nao-existe", status=404)


# --- Desligamento --------------------------------------------------------------


@pytest.mark.parametrize(
    "corpo, mensagem",
    [
        ({}, "Informe data e motivo do desligamento."),
        ({"data_saida": HOJE.isoformat()}, "Informe motivo do desligamento."),
        ({"motivo": "Mudou de cidade"}, "Informe data do desligamento."),
        ({"data_saida": HOJE.isoformat(), "motivo": "   "}, "Informe motivo do desligamento."),
    ],
)
def test_desligamento_sem_motivo_ou_data_400(cliente, cabecalhos, programa, corpo, mensagem):
    turma = criar_turma(cliente, cabecalhos)
    matricula = inscrever(cliente, cabecalhos, turma["id"], "pe-lara")["matricula"]

    resposta = cliente.patch(
        f"{P1}/turmas/{turma['id']}/matriculas/{matricula['id']}/desligamento", json=corpo, headers=como(cabecalhos)
    )

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == mensagem


def test_desligamento_fica_no_historico_e_libera_a_vaga_para_o_proximo_da_fila(cliente, cabecalhos, programa):
    turma = criar_turma(cliente, cabecalhos)
    lara = inscrever(cliente, cabecalhos, turma["id"], "pe-lara")["matricula"]
    inscrever(cliente, cabecalhos, turma["id"], "pe-davi")
    inscrever(cliente, cabecalhos, turma["id"], "pe-maria")
    inscrever(cliente, cabecalhos, turma["id"], "pe-joana")
    chamar = f"{P1}/turmas/{turma['id']}/lista-de-espera/chamada"

    assert cliente.post(chamar, headers=como(cabecalhos)).status_code == 409  # ainda lotada
    saida = cliente.patch(
        f"{P1}/turmas/{turma['id']}/matriculas/{lara['id']}/desligamento",
        json={"data_saida": HOJE.isoformat(), "motivo": "Mudou de cidade"},
        headers=como(cabecalhos),
    )
    chamada = cliente.post(chamar, headers=como(cabecalhos))

    assert (saida.json()["situacao"], saida.json()["motivo_saida"]) == ("desligada", "Mudou de cidade")
    assert chamada.status_code == 200
    assert (chamada.json()["matricula"]["pessoa"], chamada.json()["matricula"]["situacao"]) == ("Maria", "ativa")
    visto = detalhe(cliente, cabecalhos, turma["id"])
    assert [m["pessoa"] for m in visto["desligadas"]] == ["Lara"]
    assert [(m["pessoa"], m["posicao_espera"]) for m in visto["lista_de_espera"]] == [("Joana", 1)]
    de_novo = cliente.patch(
        f"{P1}/turmas/{turma['id']}/matriculas/{lara['id']}/desligamento",
        json={"data_saida": HOJE.isoformat(), "motivo": "De novo"},
        headers=como(cabecalhos),
    )
    assert de_novo.status_code == 409


def test_quem_esta_na_espera_tambem_pode_sair_da_fila(cliente, cabecalhos, programa):
    turma = criar_turma(cliente, cabecalhos, capacidade=1)
    inscrever(cliente, cabecalhos, turma["id"], "pe-lara")
    davi = inscrever(cliente, cabecalhos, turma["id"], "pe-davi")["matricula"]

    resposta = cliente.patch(
        f"{P1}/turmas/{turma['id']}/matriculas/{davi['id']}/desligamento",
        json={"data_saida": HOJE.isoformat(), "motivo": "Desistiu da vaga"},
        headers=como(cabecalhos),
    )

    assert resposta.status_code == 200
    assert detalhe(cliente, cabecalhos, turma["id"])["lista_de_espera"] == []


def test_lista_de_espera_vazia_409(cliente, cabecalhos, programa):
    turma = criar_turma(cliente, cabecalhos)

    resposta = cliente.post(f"{P1}/turmas/{turma['id']}/lista-de-espera/chamada", headers=como(cabecalhos))

    assert resposta.status_code == 409
    assert resposta.json()["detail"] == "A lista de espera está vazia."


# --- Conflito de horário ---------------------------------------------------------


def test_conflito_de_horario_salva_a_inscricao_e_alerta_a_coordenacao(cliente, cabecalhos, programa):
    arte = criar_turma(cliente, cabecalhos)  # seg e qua, 14h às 16h
    musica = criar_turma(cliente, cabecalhos, nome="Música", dias_semana=[3, 5], hora_inicio="15:00", hora_fim="17:00")
    inscrever(cliente, cabecalhos, arte["id"], "pe-lara")

    resposta = inscrever(cliente, cabecalhos, musica["id"], "pe-lara")

    assert resposta["matricula"]["situacao"] == "ativa"
    assert [c["turma"] for c in resposta["conflitos"]] == ["Oficina de arte"]
    [alerta] = eventos(programa, "conflito_de_horario")
    assert alerta[0:2] == ("ana", "matricula")
    assert alerta[2]["turmas_em_conflito"] == [arte["id"]]
    visto = detalhe(cliente, cabecalhos, musica["id"])
    assert [c["turma"] for c in visto["matriculas"][0]["conflitos"]] == ["Oficina de arte"]


@pytest.mark.parametrize(
    "dias, inicio, fim",
    [([2, 4], "14:00", "16:00"), ([1], "16:00", "18:00"), ([3], "10:00", "14:00")],
)
def test_sem_dia_em_comum_ou_horario_encostado_nao_e_conflito(cliente, cabecalhos, programa, dias, inicio, fim):
    arte = criar_turma(cliente, cabecalhos)
    outra = criar_turma(cliente, cabecalhos, nome="Outra", dias_semana=dias, hora_inicio=inicio, hora_fim=fim)
    inscrever(cliente, cabecalhos, arte["id"], "pe-lara")

    assert inscrever(cliente, cabecalhos, outra["id"], "pe-lara")["conflitos"] == []
    assert eventos(programa, "conflito_de_horario") == []


def test_matricula_desligada_nao_conta_como_conflito(cliente, cabecalhos, programa):
    arte = criar_turma(cliente, cabecalhos)
    musica = criar_turma(cliente, cabecalhos, nome="Música", dias_semana=[1], hora_inicio="15:00", hora_fim="17:00")
    lara = inscrever(cliente, cabecalhos, arte["id"], "pe-lara")["matricula"]
    cliente.patch(
        f"{P1}/turmas/{arte['id']}/matriculas/{lara['id']}/desligamento",
        json={"data_saida": HOJE.isoformat(), "motivo": "Trocou de turma"},
        headers=como(cabecalhos),
    )

    assert inscrever(cliente, cabecalhos, musica["id"], "pe-lara")["conflitos"] == []


# --- Acesso --------------------------------------------------------------------


def test_equipe_so_consulta_e_direcao_nao_ve_os_nomes(cliente, cabecalhos, programa):
    turma = criar_turma(cliente, cabecalhos)

    educadora = cliente.post(f"{P1}/turmas", json={**TURMA, "nome": "Outra"}, headers=como(cabecalhos, "jessica"))
    direcao = cliente.get(f"{P1}/turmas/{turma['id']}", headers=como(cabecalhos, "dora"))

    assert educadora.status_code == 403
    assert direcao.status_code == 403
    assert cliente.get(f"{P1}/turmas", headers=como(cabecalhos, "dora")).status_code == 200
    with programa.connect() as c:
        negados = c.execute(sa.text("SELECT usuario_id FROM log_auditoria WHERE acao = 'acesso_negado' ORDER BY id")).scalars().all()
    assert negados == ["jessica", "dora"]


def test_turma_de_outro_programa_404(cliente, cabecalhos, programa):
    turma = criar_turma(cliente, cabecalhos)

    resposta = cliente.get(f"/gestao/programas/p-2/turmas/{turma['id']}", headers=como(cabecalhos, "admin"))

    assert resposta.status_code == 404


# --- Trajetória da pessoa --------------------------------------------------------


def test_matricula_espera_e_desligamento_entram_na_trajetoria(cliente, cabecalhos, programa):
    turma = criar_turma(cliente, cabecalhos, capacidade=1)
    lara = inscrever(cliente, cabecalhos, turma["id"], "pe-lara")["matricula"]
    inscrever(cliente, cabecalhos, turma["id"], "pe-davi")
    cliente.patch(
        f"{P1}/turmas/{turma['id']}/matriculas/{lara['id']}/desligamento",
        json={"data_saida": HOJE.isoformat(), "motivo": "Mudou de cidade"},
        headers=como(cabecalhos),
    )

    da_lara = cliente.get("/gestao/pessoas/pe-lara/trajetoria", headers=como(cabecalhos)).json()
    do_davi = cliente.get("/gestao/pessoas/pe-davi/trajetoria", headers=como(cabecalhos)).json()

    titulos = {e["titulo"]: e["descricao"] for e in da_lara}
    assert titulos["Matrícula na turma Oficina de arte"] == "Entrada na turma."
    assert titulos["Desligamento da turma Oficina de arte"] == "Mudou de cidade"
    assert "Lista de espera da turma Oficina de arte" in {e["titulo"] for e in do_davi}
