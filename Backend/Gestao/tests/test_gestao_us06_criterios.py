"""Critérios da US-06: limite de faltas e encerramento justificado (T-61).

Cada seção é um critério do card:

1. faltas abaixo do limite não geram alerta; no limite, geram;
2. a busca ativa concluída fica registrada na linha do tempo do alerta;
3. o encerramento sem justificativa falha.

Tudo passa pela API, como no uso real: a educadora registra as chamadas (T-56), o alerta
nasce delas (T-59) e a assistente social acompanha. O limite é o configurado na edição do
programa. Contra o banco de teste (TEST_DATABASE_URL).
"""

from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

HOJE = date.today()
INICIO = HOJE - timedelta(days=60)
PROGRAMA = "/gestao/programas/p-1"
ALERTAS = "/gestao/alertas"


@pytest.fixture
def programa(banco):
    """Programa Semear (p-1) com a turma Oficina de arte (t-1), todos os dias.

    Equipe: Jéssica (educadora), Ana (coordenação) e Patrícia (assistente social).
    Matriculadas: Lara e Davi.
    """
    with banco.begin() as c:
        # Programa completo, como cadastrado pela tela: a edição do limite exige os campos obrigatórios.
        c.execute(
            sa.text(
                "INSERT INTO projetos (id, nome, identificador, publico, responsavel, vigencia_inicio, vigencia_fim) "
                "VALUES ('p-1', 'Semear', 'SEMEAR', 'Crianças de 6 a 12 anos', 'Ana Martins', :inicio, :fim)"
            ),
            {"inicio": INICIO, "fim": HOJE + timedelta(days=300)},
        )
        c.execute(
            sa.text("INSERT INTO usuarios (id, nome) VALUES (:id, :nome)"),
            [{"id": "jessica", "nome": "Jéssica Almeida"}, {"id": "ana", "nome": "Ana Martins"}, {"id": "patricia", "nome": "Patrícia Souza"}],
        )
        c.execute(
            sa.text("INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) VALUES (:id, :u, 'p-1', :papel, :inicio)"),
            [
                {"id": "v1", "u": "jessica", "papel": "educador", "inicio": INICIO},
                {"id": "v2", "u": "ana", "papel": "coordenacao", "inicio": INICIO},
                {"id": "v3", "u": "patricia", "papel": "assistente_social", "inicio": INICIO},
            ],
        )
        c.execute(sa.text("INSERT INTO espacos (id, programa_id, nome) VALUES ('e-1', 'p-1', 'Ateliê')"))
        c.execute(
            sa.text(
                "INSERT INTO turmas (id, programa_id, nome, espaco_id, responsavel_id, capacidade, dias_semana, hora_inicio, hora_fim) "
                "VALUES ('t-1', 'p-1', 'Oficina de arte', 'e-1', 'jessica', 20, '{1,2,3,4,5,6,7}', '14:00', '16:00')"
            )
        )
        c.execute(sa.text("INSERT INTO nucleos_familiares (id, nome) VALUES ('f-1', 'Oliveira')"))
        c.execute(
            sa.text(
                "INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id) "
                "VALUES (:id, :nome, lower(:nome), '2014-01-01', 'f-1', 'p-1')"
            ),
            [{"id": "pe-lara", "nome": "Lara Oliveira"}, {"id": "pe-davi", "nome": "Davi Oliveira"}],
        )
        c.execute(
            sa.text("INSERT INTO matriculas (id, turma_id, pessoa_id, situacao, data_entrada) VALUES (:id, 't-1', :p, 'ativa', :inicio)"),
            [{"id": "m1", "p": "pe-lara", "inicio": INICIO}, {"id": "m2", "p": "pe-davi", "inicio": INICIO}],
        )
    return banco


def como(cabecalhos, usuario):
    return {**cabecalhos, "X-Usuario-Id": usuario}


class Turma:
    """Chamadas da turma t-1, um encontro por dia, do mais antigo para o mais recente."""

    def __init__(self, cliente, cabecalhos):
        self.cliente, self.cabecalhos, self.dia = cliente, cabecalhos, HOJE - timedelta(days=30)

    def encontro(self, faltou=()):
        self.dia += timedelta(days=1)
        presencas = [{"pessoa_id": p, "presente": p not in faltou} for p in ("pe-lara", "pe-davi")]
        resposta = self.cliente.post(
            f"{PROGRAMA}/turmas/t-1/atividades",
            json={"registro_id": f"r-{self.dia.isoformat()}", "data": self.dia.isoformat(), "conteudo": "Encontro", "presencas": presencas},
            headers=como(self.cabecalhos, "jessica"),
        )
        assert resposta.status_code == 201, resposta.text

    def faltas(self, vezes, pessoa="pe-lara"):
        for _ in range(vezes):
            self.encontro(faltou=[pessoa])


@pytest.fixture
def turma(cliente, cabecalhos, programa):
    return Turma(cliente, cabecalhos)


def definir_limite(cliente, cabecalhos, valor):
    resposta = cliente.patch(PROGRAMA, json={"limite_faltas": valor}, headers=cabecalhos)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["limite_faltas"] == valor


def alertas(cliente, cabecalhos, usuario="patricia"):
    resposta = cliente.get(ALERTAS, headers=como(cabecalhos, usuario))
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def registros_de_auditoria(banco, acao):
    with banco.connect() as c:
        return c.execute(sa.text("SELECT count(*) FROM log_auditoria WHERE acao = :a"), {"a": acao}).scalar_one()


# --- 1. Faltas abaixo do limite (sem alerta) e no limite (com alerta) -----------------


@pytest.mark.parametrize("limite", [1, 2, 3, 5])
def test_abaixo_do_limite_nao_ha_alerta_e_no_limite_o_alerta_nasce(cliente, cabecalhos, programa, turma, limite):
    definir_limite(cliente, cabecalhos, limite)

    turma.faltas(limite - 1)
    assert alertas(cliente, cabecalhos) == []

    turma.faltas(1)
    [alerta] = alertas(cliente, cabecalhos)
    assert {k: alerta[k] for k in ("pessoa", "programa_id", "turma", "faltas_consecutivas", "limite", "situacao", "responsavel")} == {
        "pessoa": "Lara Oliveira",
        "programa_id": "p-1",
        "turma": "Oficina de arte",
        "faltas_consecutivas": limite,
        "limite": limite,
        "situacao": "aberto",
        # A equipe responsável: a assistente social do programa.
        "responsavel": "Patrícia Souza",
    }
    # A coordenação também acompanha; a geração fica na auditoria.
    assert [a["id"] for a in alertas(cliente, cabecalhos, "ana")] == [alerta["id"]]
    assert registros_de_auditoria(programa, "alerta_infrequencia") == 1


def test_presenca_antes_do_limite_recomeca_a_contagem(cliente, cabecalhos, programa, turma):
    turma.faltas(2)
    turma.encontro()
    turma.faltas(2)

    assert alertas(cliente, cabecalhos) == []

    turma.faltas(1)
    [alerta] = alertas(cliente, cabecalhos)
    assert alerta["faltas_consecutivas"] == 3


def test_so_quem_atingiu_o_limite_ganha_alerta(cliente, cabecalhos, programa, turma):
    turma.encontro(faltou=["pe-lara", "pe-davi"])
    turma.encontro(faltou=["pe-lara", "pe-davi"])
    turma.encontro(faltou=["pe-lara"])

    assert [a["pessoa"] for a in alertas(cliente, cabecalhos)] == ["Lara Oliveira"]


# --- 2. Busca ativa concluída registrada na linha do tempo ------------------------------


@pytest.fixture
def alerta_id(cliente, cabecalhos, turma):
    turma.faltas(3)
    return alertas(cliente, cabecalhos)[0]["id"]


def registrar_acao(cliente, cabecalhos, alerta_id, usuario="patricia", **dados):
    return cliente.post(f"{ALERTAS}/{alerta_id}/acoes", json=dados, headers=como(cabecalhos, usuario))


def test_busca_ativa_concluida_fica_na_linha_do_tempo_com_resultado_responsavel_e_data(cliente, cabecalhos, programa, alerta_id):
    anteontem, ontem = HOJE - timedelta(days=2), HOJE - timedelta(days=1)
    registrar_acao(cliente, cabecalhos, alerta_id, tipo="contato_familia", data=anteontem.isoformat(), resultado="Telefone sem resposta.")

    resposta = registrar_acao(
        cliente, cabecalhos, alerta_id, usuario="ana", tipo="busca_ativa", data=ontem.isoformat(), resultado="Visita: família localizada, retorno combinado."
    )

    assert resposta.status_code == 201
    linha_do_tempo = [(a["tipo_nome"], a["data"], a["resultado"], a["responsavel"]) for a in resposta.json()["acoes"]]
    assert linha_do_tempo == [
        ("Busca ativa", ontem.isoformat(), "Visita: família localizada, retorno combinado.", "Ana Martins"),
        ("Contato com a família", anteontem.isoformat(), "Telefone sem resposta.", "Patrícia Souza"),
    ]
    # Quem consulta depois vê a mesma linha do tempo, e cada ação foi auditada.
    detalhe = cliente.get(f"{ALERTAS}/{alerta_id}", headers=como(cabecalhos, "patricia")).json()
    assert [(a["tipo_nome"], a["responsavel"]) for a in detalhe["acoes"]] == [("Busca ativa", "Ana Martins"), ("Contato com a família", "Patrícia Souza")]
    assert registros_de_auditoria(programa, "acao_busca_ativa") == 2


def test_busca_ativa_sem_resultado_nao_entra_na_linha_do_tempo(cliente, cabecalhos, programa, alerta_id):
    resposta = registrar_acao(cliente, cabecalhos, alerta_id, tipo="busca_ativa", data=HOJE.isoformat(), resultado="  ")

    assert resposta.status_code == 400
    assert cliente.get(f"{ALERTAS}/{alerta_id}", headers=como(cabecalhos, "patricia")).json()["acoes"] == []


# --- 3. Encerramento sem justificativa falha --------------------------------------------


def encerrar(cliente, cabecalhos, alerta_id, corpo, usuario="patricia"):
    return cliente.post(f"{ALERTAS}/{alerta_id}/encerramento", json=corpo, headers=como(cabecalhos, usuario))


@pytest.mark.parametrize("corpo", [{}, {"justificativa": None}, {"justificativa": ""}, {"justificativa": "  \n "}], ids=["sem-campo", "nula", "vazia", "em-branco"])
def test_encerramento_sem_justificativa_falha_e_o_alerta_continua_aberto(cliente, cabecalhos, programa, alerta_id, corpo):
    resposta = encerrar(cliente, cabecalhos, alerta_id, corpo)

    assert resposta.status_code == 400
    assert resposta.json()["detail"]["codigo"] == "justificativa_obrigatoria"
    detalhe = cliente.get(f"{ALERTAS}/{alerta_id}", headers=como(cabecalhos, "patricia")).json()
    assert (detalhe["situacao"], detalhe["encerrado_em"], detalhe["justificativa_encerramento"]) == ("aberto", None, None)
    # O acompanhamento segue: ainda dá para registrar ações.
    assert registrar_acao(cliente, cabecalhos, alerta_id, tipo="busca_ativa", data=HOJE.isoformat(), resultado="Nova visita.").status_code == 201
    assert registros_de_auditoria(programa, "alerta_encerrado") == 0


def test_o_banco_tambem_recusa_encerrar_sem_justificativa(programa, alerta_id):
    with pytest.raises(IntegrityError, match="ck_alertas_encerramento_com_justificativa"):
        with programa.begin() as c:
            c.execute(
                sa.text("UPDATE alertas SET situacao = 'encerrado', encerrado_em = now(), encerrado_por = 'patricia', justificativa_encerramento = ' ' WHERE id = :id"),
                {"id": alerta_id},
            )


def test_com_justificativa_o_alerta_e_encerrado_uma_vez(cliente, cabecalhos, programa, alerta_id):
    resposta = encerrar(cliente, cabecalhos, alerta_id, {"justificativa": "  Voltou a frequentar nos últimos encontros.  "})

    assert resposta.status_code == 200
    encerrado = resposta.json()
    assert (encerrado["situacao"], encerrado["encerrado_por"], encerrado["justificativa_encerramento"]) == (
        "encerrado",
        "patricia",
        "Voltou a frequentar nos últimos encontros.",
    )
    assert encerrado["encerrado_em"] is not None
    assert registros_de_auditoria(programa, "alerta_encerrado") == 1
    # Não encerra de novo nem recebe ações depois.
    assert encerrar(cliente, cabecalhos, alerta_id, {"justificativa": "Outra."}).status_code == 409
    assert registrar_acao(cliente, cabecalhos, alerta_id, tipo="busca_ativa", data=HOJE.isoformat(), resultado="Visita.").status_code == 409
