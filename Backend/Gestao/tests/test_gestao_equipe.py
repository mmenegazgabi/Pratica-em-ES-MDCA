"""Equipe e espaços do programa: vínculo, desligamento e bloqueio de acesso (T-39 · US-01)."""

from datetime import date, timedelta

import pytest
import sqlalchemy as sa

HOJE = date.today()
ONTEM = HOJE - timedelta(days=1)
AMANHA = HOJE + timedelta(days=1)

EQUIPE = "/gestao/programas/p-1/equipe"
ESPACOS = "/gestao/programas/p-1/espacos"


@pytest.fixture
def programa(banco):
    """Programa p-1 (Semear) com equipe, e p-2 (Oficina) com outra pessoa.

    - ana: coordenação em p-1         - jessica: educadora em p-1
    - rafael: psicólogo, saiu de p-1 ontem
    - bruno: educador só em p-2       - dora: direção da plataforma
    - admin: administração            - inativo: usuário desativado
    """
    with banco.begin() as conexao:
        conexao.execute(
            sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear'), ('p-2', 'Oficina')")
        )
        conexao.execute(
            sa.text("INSERT INTO usuarios (id, nome, ativo) VALUES (:id, :nome, :ativo)"),
            [
                {"id": "ana", "nome": "Ana Martins", "ativo": True},
                {"id": "jessica", "nome": "Jéssica Almeida", "ativo": True},
                {"id": "rafael", "nome": "Rafael Nunes", "ativo": True},
                {"id": "bruno", "nome": "Bruno Lima", "ativo": True},
                {"id": "dora", "nome": "Dora Prates", "ativo": True},
                {"id": "admin", "nome": "Administração", "ativo": True},
                {"id": "inativo", "nome": "Conta Antiga", "ativo": False},
                {"id": "patricia", "nome": "Patrícia Souza", "ativo": True},
            ],
        )
        conexao.execute(
            sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES (:u, :p)"),
            [{"u": "dora", "p": "direcao"}, {"u": "admin", "p": "administracao"}],
        )
        conexao.execute(
            sa.text(
                """
                INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada, data_saida)
                VALUES (:id, :u, :prog, :papel, :entrada, :saida)
                """
            ),
            [
                {"id": "v-ana", "u": "ana", "prog": "p-1", "papel": "coordenacao", "entrada": "2025-01-10", "saida": None},
                {"id": "v-jessica", "u": "jessica", "prog": "p-1", "papel": "educador", "entrada": "2025-03-01", "saida": None},
                {"id": "v-rafael", "u": "rafael", "prog": "p-1", "papel": "psicologo", "entrada": "2025-02-01", "saida": ONTEM},
                {"id": "v-bruno", "u": "bruno", "prog": "p-2", "papel": "educador", "entrada": "2025-04-01", "saida": None},
            ],
        )
    return banco


def como(cabecalhos, usuario_id):
    return {**cabecalhos, "X-Usuario-Id": usuario_id}


def negacoes(banco):
    with banco.connect() as conexao:
        linhas = conexao.execute(
            sa.text(
                "SELECT usuario_id, modulo, acao, alvo_tipo, alvo_id, detalhes "
                "FROM log_auditoria ORDER BY id"
            )
        ).all()
    return [linha._asdict() for linha in linhas]


# --- Consulta da equipe ------------------------------------------------------


def test_profissional_vinculado_aparece_entre_os_responsaveis_disponiveis(cliente, cabecalhos, programa):
    resposta = cliente.get(EQUIPE, headers=como(cabecalhos, "ana"))

    assert resposta.status_code == 200
    equipe = resposta.json()
    # Quem saiu (rafael) não pode mais ser escolhido como responsável de turma.
    assert [(v["usuario_id"], v["papel_id"], v["ativo"]) for v in equipe] == [
        ("ana", "coordenacao", True),
        ("jessica", "educador", True),
    ]
    assert equipe[1] == {
        "id": "v-jessica",
        "usuario_id": "jessica",
        "nome": "Jéssica Almeida",
        "papel_id": "educador",
        "papel": "Educador(a) social",
        "data_entrada": "2025-03-01",
        "data_saida": None,
        "ativo": True,
    }


def test_historico_inclui_quem_ja_saiu(cliente, cabecalhos, programa):
    resposta = cliente.get(EQUIPE, params={"incluir_desligados": True}, headers=como(cabecalhos, "ana"))

    assert resposta.status_code == 200
    rafael = next(v for v in resposta.json() if v["usuario_id"] == "rafael")
    assert rafael["data_saida"] == ONTEM.isoformat()
    assert rafael["ativo"] is False


@pytest.mark.parametrize("usuario", ["jessica", "dora", "admin"])
def test_equipe_direcao_e_administracao_consultam_o_programa(cliente, cabecalhos, programa, usuario):
    assert cliente.get(EQUIPE, headers=como(cabecalhos, usuario)).status_code == 200


# --- Acesso negado e bloqueio por desligamento -------------------------------


def test_desligado_tem_acesso_bloqueado_e_o_historico_continua(cliente, cabecalhos, programa):
    resposta = cliente.get(EQUIPE, headers=como(cabecalhos, "rafael"))

    assert resposta.status_code == 403
    historico = cliente.get(
        EQUIPE, params={"incluir_desligados": True}, headers=como(cabecalhos, "ana")
    ).json()
    assert "v-rafael" in [v["id"] for v in historico]


@pytest.mark.parametrize(
    "usuario",
    ["bruno", "patricia", "inativo", "desconhecido"],
    ids=["outro-programa", "sem-vinculo", "usuario-desativado", "usuario-inexistente"],
)
def test_perfil_sem_permissao_recebe_403_e_a_tentativa_e_registrada(cliente, cabecalhos, programa, usuario):
    resposta = cliente.get(ESPACOS, headers=como(cabecalhos, usuario))

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Seu perfil não tem acesso a este programa."
    assert negacoes(programa) == [
        {
            "usuario_id": usuario,
            "modulo": "gestao",
            "acao": "acesso_negado",
            "alvo_tipo": "programa",
            "alvo_id": "p-1",
            "detalhes": {"operacao": "consultar", "metodo": "GET", "rota": ESPACOS},
        }
    ]


@pytest.mark.parametrize("usuario", ["jessica", "dora"])
def test_quem_so_consulta_nao_altera_a_equipe_e_a_tentativa_e_registrada(cliente, cabecalhos, programa, usuario):
    resposta = cliente.post(
        EQUIPE,
        json={"usuario_id": "patricia", "papel_id": "assistente_social", "data_entrada": "2026-03-01"},
        headers=como(cabecalhos, usuario),
    )

    assert resposta.status_code == 403
    assert "não pode alterar" in resposta.json()["detail"]
    [negacao] = negacoes(programa)
    assert negacao["usuario_id"] == usuario
    assert negacao["detalhes"]["operacao"] == "gerenciar"


def test_coordenacao_de_outro_programa_nao_gerencia_este(cliente, cabecalhos, programa):
    with programa.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) "
                "VALUES ('v-bruno-coord', 'bruno', 'p-2', 'coordenacao', '2025-04-01')"
            )
        )

    resposta = cliente.post(ESPACOS, json={"nome": "Ateliê"}, headers=como(cabecalhos, "bruno"))

    assert resposta.status_code == 403


def test_programa_inexistente_404_sem_registro(cliente, cabecalhos, programa):
    resposta = cliente.get("/gestao/programas/p-9/equipe", headers=como(cabecalhos, "admin"))

    assert resposta.status_code == 404
    assert negacoes(programa) == []


def test_sem_identificacao_do_usuario_400(cliente, cabecalhos, programa):
    assert cliente.get(EQUIPE, headers=cabecalhos).status_code == 400


def test_sem_autenticacao_401(cliente, programa):
    assert cliente.get(EQUIPE, headers={"X-Usuario-Id": "ana"}).status_code == 401


# --- Vincular ----------------------------------------------------------------


def test_coordenacao_vincula_profissional_ao_programa(cliente, cabecalhos, programa):
    resposta = cliente.post(
        EQUIPE,
        json={"usuario_id": "patricia", "papel_id": "assistente_social", "data_entrada": "2026-03-01"},
        headers=como(cabecalhos, "ana"),
    )

    assert resposta.status_code == 201
    vinculo = resposta.json()
    assert {k: vinculo[k] for k in ("usuario_id", "nome", "papel_id", "data_saida", "ativo")} == {
        "usuario_id": "patricia",
        "nome": "Patrícia Souza",
        "papel_id": "assistente_social",
        "data_saida": None,
        "ativo": True,
    }
    # Vinculada, ela passa a consultar o programa.
    assert cliente.get(EQUIPE, headers=como(cabecalhos, "patricia")).status_code == 200


def test_administracao_vincula_sem_estar_no_programa(cliente, cabecalhos, programa):
    resposta = cliente.post(
        EQUIPE,
        json={"usuario_id": "bruno", "papel_id": "educador", "data_entrada": "2026-03-01"},
        headers=como(cabecalhos, "admin"),
    )

    assert resposta.status_code == 201


def test_vinculo_ativo_repetido_409(cliente, cabecalhos, programa):
    resposta = cliente.post(
        EQUIPE,
        json={"usuario_id": "jessica", "papel_id": "educador", "data_entrada": "2026-03-01"},
        headers=como(cabecalhos, "ana"),
    )

    assert resposta.status_code == 409


def test_quem_saiu_pode_ser_vinculado_de_novo(cliente, cabecalhos, programa):
    resposta = cliente.post(
        EQUIPE,
        json={"usuario_id": "rafael", "papel_id": "psicologo", "data_entrada": HOJE.isoformat()},
        headers=como(cabecalhos, "ana"),
    )

    assert resposta.status_code == 201
    assert cliente.get(EQUIPE, headers=como(cabecalhos, "rafael")).status_code == 200


@pytest.mark.parametrize(
    "dados, status",
    [
        ({"usuario_id": "ninguem", "papel_id": "educador"}, 400),
        ({"usuario_id": "patricia", "papel_id": "estagiario"}, 400),
        ({"usuario_id": "inativo", "papel_id": "educador"}, 409),
    ],
    ids=["usuario-inexistente", "papel-invalido", "usuario-desativado"],
)
def test_vinculo_com_dados_invalidos(cliente, cabecalhos, programa, dados, status):
    resposta = cliente.post(
        EQUIPE, json={**dados, "data_entrada": "2026-03-01"}, headers=como(cabecalhos, "ana")
    )

    assert resposta.status_code == status
    with programa.connect() as conexao:
        total = conexao.execute(sa.text("SELECT count(*) FROM vinculos_equipe")).scalar_one()
    assert total == 4


def test_vinculo_sem_data_de_entrada_422(cliente, cabecalhos, programa):
    resposta = cliente.post(
        EQUIPE, json={"usuario_id": "patricia", "papel_id": "educador"}, headers=como(cabecalhos, "ana")
    )

    assert resposta.status_code == 422


# --- Desligamento ------------------------------------------------------------


def test_desligamento_bloqueia_o_acesso_sem_apagar_o_vinculo(cliente, cabecalhos, programa):
    resposta = cliente.patch(
        f"{EQUIPE}/v-jessica/desligamento",
        json={"data_saida": HOJE.isoformat()},
        headers=como(cabecalhos, "ana"),
    )

    assert resposta.status_code == 200
    assert resposta.json()["data_saida"] == HOJE.isoformat()
    assert resposta.json()["ativo"] is False
    assert cliente.get(EQUIPE, headers=como(cabecalhos, "jessica")).status_code == 403
    historico = cliente.get(
        EQUIPE, params={"incluir_desligados": True}, headers=como(cabecalhos, "ana")
    ).json()
    assert "v-jessica" in [v["id"] for v in historico]


def test_desligamento_com_data_futura_mantem_acesso_ate_la(cliente, cabecalhos, programa):
    resposta = cliente.patch(
        f"{EQUIPE}/v-jessica/desligamento",
        json={"data_saida": AMANHA.isoformat()},
        headers=como(cabecalhos, "ana"),
    )

    assert resposta.json()["ativo"] is True
    assert cliente.get(EQUIPE, headers=como(cabecalhos, "jessica")).status_code == 200


def test_desligamento_repetido_409(cliente, cabecalhos, programa):
    resposta = cliente.patch(
        f"{EQUIPE}/v-rafael/desligamento",
        json={"data_saida": HOJE.isoformat()},
        headers=como(cabecalhos, "ana"),
    )

    assert resposta.status_code == 409


def test_saida_antes_da_entrada_400(cliente, cabecalhos, programa):
    resposta = cliente.patch(
        f"{EQUIPE}/v-jessica/desligamento",
        json={"data_saida": "2025-02-28"},
        headers=como(cabecalhos, "ana"),
    )

    assert resposta.status_code == 400


def test_vinculo_de_outro_programa_404(cliente, cabecalhos, programa):
    resposta = cliente.patch(
        f"{EQUIPE}/v-bruno/desligamento",
        json={"data_saida": HOJE.isoformat()},
        headers=como(cabecalhos, "ana"),
    )

    assert resposta.status_code == 404


# --- Espaços -----------------------------------------------------------------


def test_coordenacao_cadastra_espaco_e_equipe_consulta(cliente, cabecalhos, programa):
    criado = cliente.post(
        ESPACOS, json={"nome": " Sala de convivência ", "capacidade": 25}, headers=como(cabecalhos, "ana")
    )
    cliente.post(ESPACOS, json={"nome": "Ateliê"}, headers=como(cabecalhos, "ana"))

    assert criado.status_code == 201
    assert criado.json()["nome"] == "Sala de convivência"
    resposta = cliente.get(ESPACOS, headers=como(cabecalhos, "jessica"))
    assert resposta.status_code == 200
    assert [(e["nome"], e["capacidade"]) for e in resposta.json()] == [
        ("Ateliê", None),
        ("Sala de convivência", 25),
    ]


def test_espaco_com_nome_repetido_409(cliente, cabecalhos, programa):
    cliente.post(ESPACOS, json={"nome": "Ateliê"}, headers=como(cabecalhos, "ana"))

    resposta = cliente.post(ESPACOS, json={"nome": "ateliê"}, headers=como(cabecalhos, "ana"))

    assert resposta.status_code == 409


@pytest.mark.parametrize(
    "dados, status",
    [({"nome": "   "}, 400), ({"nome": "Sala", "capacidade": 0}, 422), ({}, 422)],
    ids=["nome-em-branco", "capacidade-zero", "sem-nome"],
)
def test_espaco_com_dados_invalidos(cliente, cabecalhos, programa, dados, status):
    resposta = cliente.post(ESPACOS, json=dados, headers=como(cabecalhos, "ana"))

    assert resposta.status_code == status


def test_educadora_nao_cadastra_espaco(cliente, cabecalhos, programa):
    resposta = cliente.post(ESPACOS, json={"nome": "Ateliê"}, headers=como(cabecalhos, "jessica"))

    assert resposta.status_code == 403
