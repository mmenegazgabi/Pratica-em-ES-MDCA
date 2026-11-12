"""Critérios de aceitação da US-01 (T-41): vínculo, desligamento e acesso negado por programa.

Os testes de cada rota ficam em ``test_gestao_equipe.py`` e ``test_gestao_usuarios.py``.
Aqui cada critério da US-01 é verificado como um percurso completo pela API:

1. A escolha do responsável de uma turma é feita entre os profissionais vinculados ao
   programa (a lista de equipe ativa, que a T-51 vai usar).
2. Um profissional desligado que tenta acessar o programa é bloqueado em todas as
   rotas, e o histórico continua preservado.
3. Todo acesso negado gera um registro na trilha de auditoria (``log_auditoria``).
"""

from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

HOJE = date.today()
ONTEM = HOJE - timedelta(days=1)
AMANHA = HOJE + timedelta(days=1)

P1 = "/gestao/programas/p-1"
EQUIPE = f"{P1}/equipe"
ESPACOS = f"{P1}/espacos"
USUARIOS = "/gestao/usuarios"
PESSOAS = "/gestao/pessoas"

SEM_ACESSO = "Seu perfil não tem acesso a este programa."


@pytest.fixture
def programa(banco):
    """Programa p-1 (Semear) e p-2 (Oficina).

    - ana: coordenação (na conta)           - jessica: educadora em p-1
    - carla: educadora em p-1 e em p-2
    - rafael: psicólogo, saiu de p-1 ontem  - bruno: educador só em p-2
    - patricia: sem vínculo                 - admin: administração da plataforma
    - dora: direção da plataforma           - lara (pe-lara): pessoa atendida em p-1
    """
    with banco.begin() as conexao:
        conexao.execute(
            sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear'), ('p-2', 'Oficina')")
        )
        conexao.execute(
            sa.text("INSERT INTO usuarios (id, nome, ativo) VALUES (:id, :nome, true)"),
            [
                {"id": u, "nome": n}
                for u, n in [
                    ("ana", "Ana Martins"),
                    ("jessica", "Jéssica Almeida"),
                    ("carla", "Carla Dias"),
                    ("rafael", "Rafael Nunes"),
                    ("bruno", "Bruno Lima"),
                    ("patricia", "Patrícia Souza"),
                    ("admin", "Administração"),
                    ("dora", "Dora Prates"),
                ]
            ],
        )
        conexao.execute(
            sa.text(
                "INSERT INTO usuarios_papeis (usuario_id, papel_id) "
                "VALUES ('admin', 'administracao'), ('dora', 'direcao'), ('ana', 'coordenacao')"
            )
        )
        conexao.execute(
            sa.text(
                """
                INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada, data_saida)
                VALUES (:id, :u, :prog, :papel, :entrada, :saida)
                """
            ),
            [
                {"id": "v-jessica", "u": "jessica", "prog": "p-1", "papel": "educador", "entrada": "2025-03-01", "saida": None},
                {"id": "v-carla", "u": "carla", "prog": "p-1", "papel": "educador", "entrada": "2025-02-01", "saida": None},
                {"id": "v-carla-p2", "u": "carla", "prog": "p-2", "papel": "educador", "entrada": "2025-02-01", "saida": None},
                {"id": "v-rafael", "u": "rafael", "prog": "p-1", "papel": "psicologo", "entrada": "2025-02-01", "saida": ONTEM},
                {"id": "v-bruno", "u": "bruno", "prog": "p-2", "papel": "educador", "entrada": "2025-04-01", "saida": None},
            ],
        )
        conexao.execute(
            sa.text("INSERT INTO nucleos_familiares (id, nome) VALUES ('f-oliveira', 'Oliveira')")
        )
        conexao.execute(
            sa.text(
                "INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id) "
                "VALUES ('pe-lara', 'Lara Oliveira', 'lara oliveira', '2013-05-12', 'f-oliveira', 'p-1')"
            )
        )
    return banco


def como(cabecalhos, usuario_id):
    return {**cabecalhos, "X-Usuario-Id": usuario_id}


def registros(banco):
    with banco.connect() as conexao:
        linhas = conexao.execute(
            sa.text(
                "SELECT usuario_id, modulo, acao, alvo_tipo, alvo_id, detalhes, ocorrido_em "
                "FROM log_auditoria ORDER BY id"
            )
        ).all()
    return [linha._asdict() for linha in linhas]


def responsaveis_disponiveis(cliente, cabecalhos, quem="ana"):
    """Quem pode ser escolhido como responsável de turma: a equipe ativa do programa."""
    resposta = cliente.get(EQUIPE, headers=como(cabecalhos, quem))
    assert resposta.status_code == 200
    return sorted(v["usuario_id"] for v in resposta.json())


def desligar(cliente, cabecalhos, vinculo_id, data_saida=HOJE, quem="ana"):
    resposta = cliente.patch(
        f"{EQUIPE}/{vinculo_id}/desligamento",
        json={"data_saida": data_saida.isoformat()},
        headers=como(cabecalhos, quem),
    )
    assert resposta.status_code == 200
    return resposta.json()


# --- Critério 1: responsável de turma escolhido entre os vinculados -------------------


def test_responsaveis_disponiveis_sao_so_os_vinculados_ativos_ao_programa(cliente, cabecalhos, programa):
    # Fora da lista: rafael (desligado), bruno (só em p-2), patricia (sem vínculo) e
    # admin/dora (papéis da plataforma, sem vínculo no programa).
    assert responsaveis_disponiveis(cliente, cabecalhos) == ["carla", "jessica"]


def test_profissional_recem_vinculado_passa_a_poder_ser_responsavel(cliente, cabecalhos, programa):
    resposta = cliente.post(
        EQUIPE,
        json={"usuario_id": "patricia", "papel_id": "educador", "data_entrada": HOJE.isoformat()},
        headers=como(cabecalhos, "ana"),
    )

    assert resposta.status_code == 201
    assert "patricia" in responsaveis_disponiveis(cliente, cabecalhos)


def test_vinculo_em_outro_programa_nao_torna_responsavel_neste(cliente, cabecalhos, programa):
    # bruno está ativo em p-2; para p-1 ele não é opção até ser vinculado aqui.
    assert "bruno" not in responsaveis_disponiveis(cliente, cabecalhos)
    resposta = cliente.get("/gestao/programas/p-2/equipe", headers=como(cabecalhos, "admin"))
    assert sorted(v["usuario_id"] for v in resposta.json()) == ["bruno", "carla"]


def test_desligado_hoje_deixa_de_ser_opcao_de_responsavel(cliente, cabecalhos, programa):
    desligar(cliente, cabecalhos, "v-jessica")

    assert "jessica" not in responsaveis_disponiveis(cliente, cabecalhos)


def test_desligamento_agendado_mantem_o_profissional_como_opcao_ate_a_data(cliente, cabecalhos, programa):
    desligar(cliente, cabecalhos, "v-jessica", data_saida=AMANHA)

    assert "jessica" in responsaveis_disponiveis(cliente, cabecalhos)


def test_profissional_revinculado_volta_a_ser_opcao(cliente, cabecalhos, programa):
    resposta = cliente.post(
        EQUIPE,
        json={"usuario_id": "rafael", "papel_id": "psicologo", "data_entrada": HOJE.isoformat()},
        headers=como(cabecalhos, "ana"),
    )

    assert resposta.status_code == 201
    assert "rafael" in responsaveis_disponiveis(cliente, cabecalhos)


def test_conta_desativada_nao_aparece_como_responsavel_e_fica_no_historico(cliente, cabecalhos, programa):
    with programa.begin() as conexao:
        conexao.execute(sa.text("UPDATE usuarios SET ativo = false WHERE id = 'jessica'"))

    assert cliente.get(EQUIPE, headers=como(cabecalhos, "jessica")).status_code == 403
    assert "jessica" not in responsaveis_disponiveis(cliente, cabecalhos)
    historico = cliente.get(
        EQUIPE, params={"incluir_desligados": True}, headers=como(cabecalhos, "ana")
    ).json()
    jessica = next(v for v in historico if v["id"] == "v-jessica")
    assert (jessica["data_saida"], jessica["ativo"]) == (None, False)


def test_conta_desativada_ainda_pode_ter_a_saida_registrada(cliente, cabecalhos, programa):
    with programa.begin() as conexao:
        conexao.execute(sa.text("UPDATE usuarios SET ativo = false WHERE id = 'jessica'"))

    desligado = desligar(cliente, cabecalhos, "v-jessica")

    assert (desligado["data_saida"], desligado["ativo"]) == (HOJE.isoformat(), False)


def test_conta_reativada_volta_a_ser_opcao_de_responsavel(cliente, cabecalhos, programa):
    with programa.begin() as conexao:
        conexao.execute(sa.text("UPDATE usuarios SET ativo = false WHERE id = 'jessica'"))
        conexao.execute(sa.text("UPDATE usuarios SET ativo = true WHERE id = 'jessica'"))

    assert "jessica" in responsaveis_disponiveis(cliente, cabecalhos)


# --- Critério 2: desligado tentando acessar o programa --------------------------------

ROTAS_DE_CONSULTA = [
    ("GET", EQUIPE, None),
    ("GET", f"{EQUIPE}?incluir_desligados=true", None),
    ("GET", ESPACOS, None),
    ("GET", f"{PESSOAS}?programa_id=p-1", None),
    ("GET", f"{PESSOAS}/pe-lara", None),
]
ROTAS_DE_GESTAO = [
    ("POST", EQUIPE, {"usuario_id": "patricia", "papel_id": "educador", "data_entrada": "2026-03-01"}),
    ("PATCH", f"{EQUIPE}/v-jessica/desligamento", {"data_saida": HOJE.isoformat()}),
    ("POST", ESPACOS, {"nome": "Ateliê"}),
]


def _ids(rotas):
    return [f"{metodo} {rota}" for metodo, rota, _ in rotas]


@pytest.mark.parametrize("metodo, rota, corpo", ROTAS_DE_CONSULTA + ROTAS_DE_GESTAO, ids=_ids(ROTAS_DE_CONSULTA + ROTAS_DE_GESTAO))
def test_desligado_e_bloqueado_em_todas_as_rotas_do_programa(cliente, cabecalhos, programa, metodo, rota, corpo):
    resposta = cliente.request(metodo, rota, json=corpo, headers=como(cabecalhos, "rafael"))

    assert resposta.status_code == 403


def test_profissional_desligado_perde_consulta_e_gestao_do_programa(cliente, cabecalhos, programa):
    desligar(cliente, cabecalhos, "v-carla")

    for metodo, rota, corpo in ROTAS_DE_CONSULTA + ROTAS_DE_GESTAO:
        resposta = cliente.request(metodo, rota, json=corpo, headers=como(cabecalhos, "carla"))
        assert resposta.status_code == 403, f"{metodo} {rota}"
        assert resposta.json()["detail"] in {SEM_ACESSO, "Seu perfil não tem acesso aos cadastros de pessoas deste programa."}
    # Nada foi alterado pelas tentativas.
    with programa.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM espacos")).scalar_one() == 0
        assert conexao.execute(
            sa.text("SELECT data_saida FROM vinculos_equipe WHERE id = 'v-jessica'")
        ).scalar_one() is None


def test_bloqueio_vale_so_para_o_programa_de_que_saiu(cliente, cabecalhos, programa):
    desligar(cliente, cabecalhos, "v-carla")

    assert cliente.get(EQUIPE, headers=como(cabecalhos, "carla")).status_code == 403
    assert cliente.get("/gestao/programas/p-2/equipe", headers=como(cabecalhos, "carla")).status_code == 200


def test_desligado_nao_ve_pessoas_do_programa_na_lista_geral(cliente, cabecalhos, programa):
    antes = cliente.get(PESSOAS, headers=como(cabecalhos, "jessica")).json()
    desligar(cliente, cabecalhos, "v-jessica")
    depois = cliente.get(PESSOAS, headers=como(cabecalhos, "jessica"))

    assert [p["id"] for p in antes] == ["pe-lara"]
    assert depois.status_code == 200
    assert depois.json() == []


def test_sem_a_coordenacao_na_conta_perde_a_lista_de_usuarios(cliente, cabecalhos, programa):
    assert cliente.get(USUARIOS, headers=como(cabecalhos, "ana")).status_code == 200
    with programa.begin() as conexao:
        conexao.execute(sa.text("DELETE FROM usuarios_papeis WHERE usuario_id = 'ana'"))

    assert cliente.get(USUARIOS, headers=como(cabecalhos, "ana")).status_code == 403


def test_desligamento_preserva_o_historico_do_vinculo(cliente, cabecalhos, programa):
    desligado = desligar(cliente, cabecalhos, "v-jessica")

    assert desligado == {
        "id": "v-jessica",
        "usuario_id": "jessica",
        "nome": "Jéssica Almeida",
        "papel_id": "educador",
        "papel": "Educador(a) social",
        "data_entrada": "2025-03-01",
        "data_saida": HOJE.isoformat(),
        "ativo": False,
    }
    historico = cliente.get(
        EQUIPE, params={"incluir_desligados": True}, headers=como(cabecalhos, "ana")
    ).json()
    assert desligado in historico
    assert {v["id"] for v in historico} >= {"v-jessica", "v-rafael"}
    with programa.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM vinculos_equipe")).scalar_one() == 5
        assert conexao.execute(sa.text("SELECT ativo FROM usuarios WHERE id = 'jessica'")).scalar_one() is True


def test_revinculo_cria_novo_vinculo_e_mantem_o_antigo_no_historico(cliente, cabecalhos, programa):
    novo = cliente.post(
        EQUIPE,
        json={"usuario_id": "rafael", "papel_id": "psicologo", "data_entrada": HOJE.isoformat()},
        headers=como(cabecalhos, "ana"),
    ).json()

    historico = cliente.get(
        EQUIPE, params={"incluir_desligados": True}, headers=como(cabecalhos, "ana")
    ).json()
    vinculos_do_rafael = {v["id"]: v for v in historico if v["usuario_id"] == "rafael"}
    assert set(vinculos_do_rafael) == {"v-rafael", novo["id"]}
    assert vinculos_do_rafael["v-rafael"]["data_saida"] == ONTEM.isoformat()
    assert vinculos_do_rafael[novo["id"]]["ativo"] is True


def test_negacoes_do_desligado_continuam_na_trilha_depois_do_revinculo(cliente, cabecalhos, programa):
    cliente.get(EQUIPE, headers=como(cabecalhos, "rafael"))
    cliente.post(
        EQUIPE,
        json={"usuario_id": "rafael", "papel_id": "psicologo", "data_entrada": HOJE.isoformat()},
        headers=como(cabecalhos, "ana"),
    )

    assert cliente.get(EQUIPE, headers=como(cabecalhos, "rafael")).status_code == 200
    assert [r["usuario_id"] for r in registros(programa)] == ["rafael"]


# --- Critério 3: acesso negado gera registro na trilha de auditoria -------------------


@pytest.mark.parametrize("metodo, rota, corpo", ROTAS_DE_CONSULTA + ROTAS_DE_GESTAO, ids=_ids(ROTAS_DE_CONSULTA + ROTAS_DE_GESTAO))
def test_cada_tentativa_do_desligado_gera_um_registro(cliente, cabecalhos, programa, metodo, rota, corpo):
    cliente.request(metodo, rota, json=corpo, headers=como(cabecalhos, "rafael"))

    [registro] = registros(programa)
    assert registro["usuario_id"] == "rafael"
    assert (registro["modulo"], registro["acao"]) == ("gestao", "acesso_negado")
    assert registro["detalhes"]["metodo"] == metodo
    assert registro["detalhes"]["rota"] == rota.split("?")[0]
    assert registro["detalhes"]["operacao"] in {"consultar", "gerenciar"}
    assert registro["ocorrido_em"] is not None


def test_registro_identifica_o_alvo_da_tentativa(cliente, cabecalhos, programa):
    cliente.get(EQUIPE, headers=como(cabecalhos, "rafael"))
    cliente.get(f"{PESSOAS}/pe-lara", headers=como(cabecalhos, "rafael"))
    cliente.get(USUARIOS, headers=como(cabecalhos, "rafael"))

    assert [(r["alvo_tipo"], r["alvo_id"]) for r in registros(programa)] == [
        ("programa", "p-1"),
        ("pessoa", "pe-lara"),
        ("usuarios", None),
    ]


def test_registro_diferencia_consulta_de_alteracao(cliente, cabecalhos, programa):
    cliente.get(ESPACOS, headers=como(cabecalhos, "bruno"))
    cliente.post(ESPACOS, json={"nome": "Ateliê"}, headers=como(cabecalhos, "jessica"))

    assert [(r["usuario_id"], r["detalhes"]["operacao"]) for r in registros(programa)] == [
        ("bruno", "consultar"),
        ("jessica", "gerenciar"),
    ]


def test_tentativas_repetidas_geram_um_registro_cada(cliente, cabecalhos, programa):
    for _ in range(3):
        assert cliente.get(EQUIPE, headers=como(cabecalhos, "rafael")).status_code == 403

    assert len(registros(programa)) == 3


def test_registro_permanece_mesmo_com_a_resposta_403(cliente, cabecalhos, programa):
    # A requisição negada é encerrada com erro; o registro tem de sobreviver a ela e
    # ficar visível para uma conexão nova.
    cliente.post(ESPACOS, json={"nome": "Ateliê"}, headers=como(cabecalhos, "rafael"))

    with programa.connect() as conexao:
        assert conexao.execute(
            sa.text("SELECT count(*) FROM log_auditoria WHERE acao = 'acesso_negado'")
        ).scalar_one() == 1
        assert conexao.execute(sa.text("SELECT count(*) FROM espacos")).scalar_one() == 0


def test_registro_de_acesso_negado_nao_pode_ser_alterado_nem_apagado(cliente, cabecalhos, programa):
    cliente.get(EQUIPE, headers=como(cabecalhos, "rafael"))

    for comando in ("UPDATE log_auditoria SET usuario_id = 'outra-pessoa'", "DELETE FROM log_auditoria"):
        with pytest.raises(DBAPIError, match="apenas inclus"):
            with programa.begin() as conexao:
                conexao.execute(sa.text(comando))
    assert [r["usuario_id"] for r in registros(programa)] == ["rafael"]


@pytest.mark.parametrize(
    "usuario, metodo, rota, corpo",
    [
        ("ana", "GET", EQUIPE, None),
        ("jessica", "GET", ESPACOS, None),
        ("dora", "GET", EQUIPE, None),
        ("admin", "POST", ESPACOS, {"nome": "Ateliê"}),
        ("ana", "PATCH", f"{EQUIPE}/v-jessica/desligamento", {"data_saida": AMANHA.isoformat()}),
        ("ana", "GET", USUARIOS, None),
    ],
    ids=["coordenacao-consulta", "educadora-consulta", "direcao-consulta", "admin-gerencia", "coordenacao-desliga", "coordenacao-usuarios"],
)
def test_acesso_permitido_nao_gera_registro_de_negacao(cliente, cabecalhos, programa, usuario, metodo, rota, corpo):
    resposta = cliente.request(metodo, rota, json=corpo, headers=como(cabecalhos, usuario))

    assert resposta.status_code < 300
    assert registros(programa) == []


@pytest.mark.parametrize(
    "caso, rota, status",
    [
        ("sem-autenticacao", EQUIPE, 401),
        ("sem-usuario", EQUIPE, 400),
        ("programa-inexistente", "/gestao/programas/p-9/equipe", 404),
    ],
    ids=lambda valor: valor if isinstance(valor, str) and not valor.startswith("/") else None,
)
def test_falhas_que_nao_sao_negacao_de_acesso_nao_geram_registro(cliente, cabecalhos, programa, caso, rota, status):
    enviados = {
        "sem-autenticacao": {"X-Usuario-Id": "rafael"},
        "sem-usuario": cabecalhos,
        "programa-inexistente": como(cabecalhos, "rafael"),
    }[caso]

    assert cliente.get(rota, headers=enviados).status_code == status
    assert registros(programa) == []
