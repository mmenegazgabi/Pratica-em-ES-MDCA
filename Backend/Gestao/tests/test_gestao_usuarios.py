"""Usuários e papéis da plataforma para as telas de Gestão (T-40 · US-01)."""

from datetime import date, timedelta

import pytest
import sqlalchemy as sa

HOJE = date.today()
ONTEM = HOJE - timedelta(days=1)
AMANHA = HOJE + timedelta(days=1)

USUARIOS = "/gestao/usuarios"
PAPEIS = "/gestao/papeis"


@pytest.fixture
def plataforma(banco):
    """Dois programas e pessoas com papéis variados.

    - admin: administração da plataforma   - dora: direção da plataforma
    - ana: coordenação (na conta)           - jessica: educadora em p-1 e p-2
    - rafael: educador em p-2, saiu ontem   - bruno: educador em p-2 até amanhã
    - inativo: conta desativada com coordenação na conta
    """
    with banco.begin() as conexao:
        conexao.execute(
            sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear'), ('p-2', 'Oficina')")
        )
        conexao.execute(
            sa.text("INSERT INTO usuarios (id, nome, email, ativo) VALUES (:id, :nome, :email, :ativo)"),
            [
                {"id": "admin", "nome": "Administração", "email": "admin@mdca.org", "ativo": True},
                {"id": "dora", "nome": "Dora Prates", "email": None, "ativo": True},
                {"id": "ana", "nome": "Ana Martins", "email": "ana@mdca.org", "ativo": True},
                {"id": "jessica", "nome": "Jéssica Almeida", "email": None, "ativo": True},
                {"id": "rafael", "nome": "Rafael Nunes", "email": None, "ativo": True},
                {"id": "bruno", "nome": "Bruno Lima", "email": None, "ativo": True},
                {"id": "inativo", "nome": "Conta Antiga", "email": None, "ativo": False},
            ],
        )
        conexao.execute(
            sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES (:u, :p)"),
            [
                {"u": "admin", "p": "administracao"},
                {"u": "dora", "p": "direcao"},
                {"u": "ana", "p": "coordenacao"},
                {"u": "inativo", "p": "coordenacao"},
            ],
        )
        conexao.execute(
            sa.text(
                """
                INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada, data_saida)
                VALUES (:id, :u, :prog, :papel, '2025-01-10', :saida)
                """
            ),
            [
                {"id": "v2", "u": "jessica", "prog": "p-1", "papel": "educador", "saida": None},
                {"id": "v3", "u": "jessica", "prog": "p-2", "papel": "educador", "saida": None},
                {"id": "v4", "u": "rafael", "prog": "p-2", "papel": "educador", "saida": ONTEM},
                {"id": "v5", "u": "bruno", "prog": "p-2", "papel": "educador", "saida": AMANHA},
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


def por_id(resposta):
    return {u["id"]: u for u in resposta.json()}


# --- Quem consulta a lista de usuários ---------------------------------------


@pytest.mark.parametrize(
    "usuario",
    ["admin", "ana"],
    ids=["administracao", "coordenacao"],
)
def test_administracao_e_coordenacao_consultam_os_usuarios(cliente, cabecalhos, plataforma, usuario):
    resposta = cliente.get(USUARIOS, headers=como(cabecalhos, usuario))

    assert resposta.status_code == 200
    assert negacoes(plataforma) == []


@pytest.mark.parametrize(
    "usuario",
    ["jessica", "dora", "rafael", "inativo", "desconhecido"],
    ids=["educadora", "direcao", "vinculo-encerrado", "usuario-desativado", "usuario-inexistente"],
)
def test_sem_permissao_recebe_403_e_a_tentativa_e_registrada(cliente, cabecalhos, plataforma, usuario):
    resposta = cliente.get(USUARIOS, headers=como(cabecalhos, usuario))

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Seu perfil não tem acesso à lista de usuários."
    assert negacoes(plataforma) == [
        {
            "usuario_id": usuario,
            "modulo": "gestao",
            "acao": "acesso_negado",
            "alvo_tipo": "usuarios",
            "alvo_id": None,
            "detalhes": {"operacao": "consultar", "metodo": "GET", "rota": USUARIOS},
        }
    ]


def test_usuarios_sem_identificacao_400(cliente, cabecalhos, plataforma):
    assert cliente.get(USUARIOS, headers=cabecalhos).status_code == 400


def test_usuarios_sem_autenticacao_401(cliente, plataforma):
    assert cliente.get(USUARIOS, headers={"X-Usuario-Id": "admin"}).status_code == 401


# --- Conteúdo da lista -------------------------------------------------------


def test_lista_todos_os_usuarios_em_ordem_de_nome(cliente, cabecalhos, plataforma):
    resposta = cliente.get(USUARIOS, headers=como(cabecalhos, "admin"))

    assert [u["nome"] for u in resposta.json()] == [
        "Administração",
        "Ana Martins",
        "Bruno Lima",
        "Conta Antiga",
        "Dora Prates",
        "Jéssica Almeida",
        "Rafael Nunes",
    ]


def test_usuario_traz_papeis_da_plataforma_e_vinculos_ativos(cliente, cabecalhos, plataforma):
    usuarios = por_id(cliente.get(USUARIOS, headers=como(cabecalhos, "admin")))

    assert usuarios["admin"] == {
        "id": "admin",
        "nome": "Administração",
        "email": "admin@mdca.org",
        "ativo": True,
        "papeis": [{"id": "administracao", "nome": "Administração do sistema"}],
        "vinculos": [],
    }
    assert usuarios["jessica"]["papeis"] == []
    assert usuarios["jessica"]["vinculos"] == [
        {"programa_id": "p-2", "programa": "Oficina", "papel_id": "educador", "papel": "Educador(a) social"},
        {"programa_id": "p-1", "programa": "Semear", "papel_id": "educador", "papel": "Educador(a) social"},
    ]


def test_vinculo_encerrado_nao_aparece_e_saida_futura_ainda_aparece(cliente, cabecalhos, plataforma):
    usuarios = por_id(cliente.get(USUARIOS, headers=como(cabecalhos, "admin")))

    assert usuarios["rafael"]["vinculos"] == []
    assert [v["programa_id"] for v in usuarios["bruno"]["vinculos"]] == ["p-2"]


def test_usuario_desativado_aparece_marcado_como_inativo(cliente, cabecalhos, plataforma):
    usuarios = por_id(cliente.get(USUARIOS, headers=como(cabecalhos, "ana")))

    assert usuarios["inativo"]["ativo"] is False


# --- Catálogo de papéis ------------------------------------------------------


@pytest.mark.parametrize("usuario", ["admin", "jessica", "desconhecido"])
def test_papeis_vem_do_catalogo_para_qualquer_usuario_identificado(cliente, cabecalhos, plataforma, usuario):
    resposta = cliente.get(PAPEIS, headers=como(cabecalhos, usuario))

    assert resposta.status_code == 200
    papeis = {p["id"]: p["nome"] for p in resposta.json()}
    assert papeis["coordenacao"] == "Coordenação"
    assert papeis["educador"] == "Educador(a) social"
    assert {"administracao", "direcao", "assistente_social", "psicologo"} <= papeis.keys()
    assert negacoes(plataforma) == []


def test_papeis_sem_identificacao_400(cliente, cabecalhos, plataforma):
    assert cliente.get(PAPEIS, headers=cabecalhos).status_code == 400
