"""Tela única de Auditoria: GET /auditoria com a trilha dos três módulos.

``modulo`` = ``financeiro`` (padrão), ``gestao``, ``plataforma`` ou ``todos``. Coordenação,
Direção e Administração leem tudo; a Psicologia lê só os próprios registros; os demais
papéis recebem 403, e a tentativa fica na trilha. Os papéis vêm da sessão (plataforma e
vínculos ativos), como nas outras rotas com login.

Precisa do PostgreSQL descartável (``TEST_DATABASE_URL``), como os demais testes de banco.
"""

from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from Acesso import sessoes
from Financeiro.main import app

client = TestClient(app)
_motor = None


@pytest.fixture
def trilha(banco_financeiro):
    """Pessoas, papéis e um evento de cada módulo, do mais antigo ao mais novo."""
    global _motor
    _motor = banco_financeiro
    agora = datetime.now(timezone.utc)
    with banco_financeiro.begin() as c:
        c.execute(
            sa.text("INSERT INTO usuarios (id, nome, email) VALUES (:id, :nome, :email)"),
            [
                {"id": u, "nome": nome, "email": f"{u}@mdca.org.br"}
                for u, nome in [
                    ("luana", "Luana Ferraz"), ("jane", "Jane Almeida"), ("adm", "Administração"),
                    ("paula", "Paula Psicóloga"), ("rafael", "Rafael Psicólogo"), ("marcos", "Marcos Vieira"),
                    ("ana", "Ana Social"),
                ]
            ],
        )
        c.execute(
            sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES (:u, :p)"),
            [{"u": "luana", "p": "coordenacao"}, {"u": "jane", "p": "direcao"}, {"u": "adm", "p": "administracao"}],
        )
        # Psicologia e educador entram pelo vínculo com o programa, como na Gestão.
        c.execute(
            sa.text(
                "INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) "
                "VALUES (:id, :u, 'p-1', :papel, '2025-01-01')"
            ),
            [
                {"id": "v-1", "u": "paula", "papel": "psicologo"},
                {"id": "v-2", "u": "rafael", "papel": "psicologo"},
                {"id": "v-3", "u": "marcos", "papel": "educador"},
                {"id": "v-4", "u": "ana", "papel": "assistente_social"},
            ],
        )
        eventos = [
            ("luana", "financeiro", "aprovar_lancamento", None, None, "Materiais · R$ 180,00 · Semear"),
            ("paula", "gestao", "download_documento", "documento_pessoa", "d-1", "Download de documento da pessoa atendida"),
            ("rafael", "gestao", "download_documento", "documento_pessoa", "d-2", "Download de documento da pessoa atendida"),
            ("adm", "plataforma", "usuario_criado", "usuarios", "marcos", None),
            (None, "plataforma", "login_falhou", "usuario", "alguem@mdca.org.br", None),
            ("paula", "plataforma", "login", None, None, None),
        ]
        for posicao, (usuario, modulo, acao, alvo_tipo, alvo_id, descricao) in enumerate(eventos):
            c.execute(
                sa.text(
                    "INSERT INTO log_auditoria (usuario_id, modulo, acao, alvo_tipo, alvo_id, descricao, ocorrido_em) "
                    "VALUES (:u, :m, :a, :t, :i, :d, :quando)"
                ),
                {"u": usuario, "m": modulo, "a": acao, "t": alvo_tipo, "i": alvo_id, "d": descricao,
                 "quando": agora - timedelta(minutes=len(eventos) - posicao)},
            )
    return banco_financeiro


def sessao_de(usuario):
    with _motor.begin() as conexao:
        token, _ = sessoes.criar(conexao, usuario, False, datetime.now(timezone.utc))
    return {"Authorization": f"Bearer {token}"}


def ler(usuario, **params):
    return client.get("/auditoria", params=params, headers=sessao_de(usuario))


def test_todos_traz_os_tres_modulos_com_modulo_rotulo_e_detalhe(trilha):
    corpo = ler("luana", modulo="todos").json()

    assert corpo["escopo"] == "todos"
    assert [(i["modulo"], i["acao"]) for i in corpo["itens"]] == [
        ("plataforma", "Entrou no sistema"),
        ("plataforma", "Tentativa de entrar sem sucesso"),
        ("plataforma", "Cadastrou conta"),
        ("gestao", "Baixou documento de pessoa atendida"),
        ("gestao", "Baixou documento de pessoa atendida"),
        ("financeiro", "Aprovou despesa"),
    ]
    detalhes = {i["codigo"]: i["alvo"] for i in corpo["itens"]}
    # Conta criada: o nome da conta; login sem sucesso: o e-mail digitado.
    assert detalhes["usuario_criado"] == "Marcos Vieira"
    assert detalhes["login_falhou"] == "alguem@mdca.org.br"
    assert corpo["itens"][0]["quem"] == "Paula Psicóloga"


@pytest.mark.parametrize("modulo, codigos", [
    ("financeiro", ["aprovar_lancamento"]),
    ("gestao", ["download_documento", "download_documento"]),
    ("plataforma", ["login", "login_falhou", "usuario_criado"]),
])
def test_filtro_por_modulo(trilha, modulo, codigos):
    itens = ler("luana", modulo=modulo).json()["itens"]
    assert [i["codigo"] for i in itens] == codigos
    assert {i["modulo"] for i in itens} == {modulo}


@pytest.mark.parametrize("quem", ["luana", "jane", "adm"])
def test_coordenacao_direcao_e_administracao_leem_tudo(trilha, quem):
    corpo = ler(quem, modulo="todos").json()
    assert (corpo["total"], corpo["escopo"]) == (6, "todos")


def test_psicologia_le_so_os_proprios_registros(trilha):
    corpo = ler("paula", modulo="todos").json()

    assert corpo["escopo"] == "proprios"
    assert [i["codigo"] for i in corpo["itens"]] == ["login", "download_documento"]
    assert {i["quem"] for i in corpo["itens"]} == {"Paula Psicóloga"}
    # Pedir os registros de outra pessoa não abre nada a mais.
    outro = ler("paula", modulo="todos", usuario_id="rafael").json()
    assert {i["quem"] for i in outro["itens"]} == {"Paula Psicóloga"}


@pytest.mark.parametrize("quem", ["marcos", "ana"])
def test_outros_papeis_nao_leem_e_a_tentativa_fica_na_trilha(trilha, quem):
    resposta = ler(quem, modulo="todos")

    assert resposta.status_code == 403
    with trilha.connect() as c:
        negado = c.execute(
            sa.text("SELECT modulo, alvo_id FROM log_auditoria WHERE acao = 'acesso_negado' AND usuario_id = :u"),
            {"u": quem},
        ).one()
    assert negado == ("financeiro", "GET /auditoria")


def test_sem_login_responde_401(trilha):
    assert client.get("/auditoria", params={"modulo": "todos"}).status_code == 401
