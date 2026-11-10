"""Login único (T-35 · US-08): POST /auth/entrar, GET /auth/eu e o token de sessão nas
rotas da Gestão e do Financeiro, ao lado do código de acesso, que continua valendo."""

import pytest
import sqlalchemy as sa

from Shared import sessao

SENHA = "senha-de-teste-123"
EQUIPE = "/gestao/programas/p-1/equipe"
ESPACOS = "/gestao/programas/p-1/espacos"


@pytest.fixture
def contas(banco, monkeypatch):
    """Programa p-1 e contas com senha.

    - ana: coordenação em p-1           - jessica: educadora em p-1
    - dora: direção da plataforma       - inativo: conta desativada
    - semsenha: conta sem senha definida
    """
    monkeypatch.setenv(sessao.VARIAVEL_CHAVE, "chave-de-teste")
    hash_senha = sessao.gerar_hash_senha(SENHA)
    with banco.begin() as conexao:
        conexao.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear')"))
        conexao.execute(
            sa.text(
                "INSERT INTO usuarios (id, nome, email, ativo, senha_hash) "
                "VALUES (:id, :nome, :email, :ativo, :hash)"
            ),
            [
                {"id": "ana", "nome": "Ana Martins", "email": "ana@mdca.org", "ativo": True, "hash": hash_senha},
                {"id": "jessica", "nome": "Jéssica Almeida", "email": "jessica@mdca.org", "ativo": True, "hash": hash_senha},
                {"id": "dora", "nome": "Dora Prates", "email": "dora@mdca.org", "ativo": True, "hash": hash_senha},
                {"id": "inativo", "nome": "Conta Antiga", "email": "antiga@mdca.org", "ativo": False, "hash": hash_senha},
                {"id": "semsenha", "nome": "Sem Senha", "email": "semsenha@mdca.org", "ativo": True, "hash": None},
            ],
        )
        conexao.execute(
            sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('dora', 'direcao')")
        )
        conexao.execute(
            sa.text(
                """
                INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) VALUES
                    ('v-ana', 'ana', 'p-1', 'coordenacao', '2025-01-10'),
                    ('v-jessica', 'jessica', 'p-1', 'educador', '2025-03-01')
                """
            )
        )
    return banco


def entrar(cliente, email, senha=SENHA):
    return cliente.post("/auth/entrar", json={"email": email, "senha": senha})


def token_de(cliente, email):
    resposta = entrar(cliente, email)
    assert resposta.status_code == 200, resposta.text
    return {"Authorization": f"Bearer {resposta.json()['token']}"}


def eventos(banco):
    with banco.connect() as conexao:
        return [
            linha._asdict()
            for linha in conexao.execute(
                sa.text("SELECT usuario_id, modulo, acao, detalhes FROM log_auditoria ORDER BY id")
            )
        ]


# --- POST /auth/entrar -------------------------------------------------------


def test_entrar_devolve_token_e_quem_entrou(cliente, contas):
    resposta = entrar(cliente, "ana@mdca.org")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert sessao.ler_token(corpo["token"]) == "ana"
    assert corpo["expira_em"]
    assert corpo["usuario"] == {
        "id": "ana",
        "nome": "Ana Martins",
        "email": "ana@mdca.org",
        "papeis": ["coordenacao"],
    }


def test_papeis_juntam_os_da_plataforma_e_os_dos_programas(cliente, contas):
    with contas.begin() as conexao:
        conexao.execute(
            sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('ana', 'voluntario_financeiro')")
        )

    assert entrar(cliente, "ana@mdca.org").json()["usuario"]["papeis"] == ["coordenacao", "voluntario_financeiro"]
    assert entrar(cliente, "dora@mdca.org").json()["usuario"]["papeis"] == ["direcao"]


def test_email_vale_sem_diferenciar_maiusculas_e_espacos(cliente, contas):
    assert entrar(cliente, "  ANA@Mdca.org ").status_code == 200


def test_entrada_certa_fica_no_log(cliente, contas):
    entrar(cliente, "ana@mdca.org")

    assert eventos(contas) == [
        {"usuario_id": "ana", "modulo": "plataforma", "acao": "login", "detalhes": None}
    ]


@pytest.mark.parametrize(
    "email, senha, usuario_id, motivo",
    [
        ("ana@mdca.org", "senha-errada", "ana", "senha_incorreta"),
        ("ninguem@mdca.org", SENHA, None, "email_nao_cadastrado"),
        ("antiga@mdca.org", SENHA, "inativo", "usuario_desativado"),
        ("semsenha@mdca.org", SENHA, "semsenha", "sem_senha"),
    ],
)
def test_entrada_recusada_responde_igual_e_fica_no_log(cliente, contas, email, senha, usuario_id, motivo):
    resposta = entrar(cliente, email, senha)

    # A mesma resposta em todos os casos: não revela se o e-mail existe.
    assert resposta.status_code == 401
    assert resposta.json()["detail"] == "E-mail ou senha inválidos."
    assert eventos(contas) == [
        {
            "usuario_id": usuario_id,
            "modulo": "plataforma",
            "acao": "login_recusado",
            "detalhes": {"email": email, "motivo": motivo},
        }
    ]


def test_sem_chave_no_servidor_o_login_fica_desligado(cliente, contas, monkeypatch):
    monkeypatch.delenv(sessao.VARIAVEL_CHAVE)

    resposta = entrar(cliente, "ana@mdca.org")

    assert resposta.status_code == 503
    assert resposta.json()["detail"] == "Login indisponível no servidor."


# --- GET /auth/eu ------------------------------------------------------------


def test_eu_mostra_quem_esta_logado(cliente, contas):
    resposta = cliente.get("/auth/eu", headers=token_de(cliente, "jessica@mdca.org"))

    assert resposta.status_code == 200
    assert resposta.json()["id"] == "jessica"
    assert resposta.json()["papeis"] == ["educador"]


@pytest.mark.parametrize("cabecalhos", [{}, {"Authorization": "Bearer mdca1.invalido.x"}])
def test_eu_sem_sessao_valida_401(cliente, contas, cabecalhos):
    assert cliente.get("/auth/eu", headers=cabecalhos).status_code == 401


# --- O token nas rotas da Gestão e do Financeiro -----------------------------


def test_token_vale_na_gestao_sem_x_usuario_id(cliente, contas):
    resposta = cliente.get(EQUIPE, headers=token_de(cliente, "jessica@mdca.org"))

    assert resposta.status_code == 200
    assert {v["usuario_id"] for v in resposta.json()} == {"ana", "jessica"}


def test_com_token_nao_da_para_se_passar_por_outra_pessoa(cliente, contas):
    # Jéssica (educadora) tenta cadastrar espaço dizendo ser a Ana (coordenação).
    cabecalhos = {**token_de(cliente, "jessica@mdca.org"), "X-Usuario-Id": "ana"}

    resposta = cliente.post(ESPACOS, json={"nome": "Ateliê"}, headers=cabecalhos)

    assert resposta.status_code == 403
    negacao = [e for e in eventos(contas) if e["acao"] == "acesso_negado"]
    assert negacao[0]["usuario_id"] == "jessica"


def test_token_vale_no_financeiro_e_identifica_quem_chama(cliente, contas):
    # /notificacoes exige saber quem chama: sem token nem X-Usuario-Id daria 400.
    resposta = cliente.get("/notificacoes", headers=token_de(cliente, "ana@mdca.org"))

    assert resposta.status_code == 200


# --- Papel no Financeiro vem do banco, não do cabeçalho ------------------------


@pytest.fixture
def sem_projetos_em_memoria():
    from Financeiro.projetos import _projetos

    _projetos.clear()
    yield
    _projetos.clear()


def test_com_token_o_papel_vem_do_banco(cliente, contas, sem_projetos_em_memoria):
    resposta = cliente.post(
        "/projetos", json={"nome": "Horta"}, headers=token_de(cliente, "ana@mdca.org")
    )

    assert resposta.status_code == 201


def test_com_token_nao_da_para_se_declarar_coordenacao(cliente, contas, sem_projetos_em_memoria):
    cabecalhos = {**token_de(cliente, "jessica@mdca.org"), "X-Papel-Usuario": "coordenacao"}

    assert cliente.post("/projetos", json={"nome": "Horta"}, headers=cabecalhos).status_code == 403
    assert cliente.patch("/orcamentos/qualquer", json={"valor_total": 1}, headers=cabecalhos).status_code == 403


def test_vinculo_que_ainda_nao_comecou_nao_da_o_papel(cliente, contas, sem_projetos_em_memoria):
    with contas.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) "
                "VALUES ('v-futuro', 'jessica', 'p-1', 'coordenacao', CURRENT_DATE + 30)"
            )
        )
    cabecalhos = token_de(cliente, "jessica@mdca.org")

    assert cliente.post("/projetos", json={"nome": "Horta"}, headers=cabecalhos).status_code == 403


def test_com_token_direcao_ve_o_dashboard_e_educadora_nao(cliente, contas):
    assert cliente.get("/dashboard/projetos", headers=token_de(cliente, "dora@mdca.org")).status_code == 200
    assert cliente.get("/dashboard/projetos", headers=token_de(cliente, "jessica@mdca.org")).status_code == 403


def test_com_token_o_cabecalho_escolhe_entre_os_papeis_da_pessoa(cliente, contas):
    with contas.begin() as conexao:
        conexao.execute(
            sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('ana', 'direcao')")
        )
    cabecalhos = token_de(cliente, "ana@mdca.org")

    assert cliente.get("/dashboard/projetos", headers=cabecalhos).status_code == 200
    assert (
        cliente.get("/dashboard/projetos", headers={**cabecalhos, "X-Papel-Usuario": "coordenacao"}).status_code
        == 403
    )


def test_conta_desativada_perde_o_acesso_na_hora(cliente, contas):
    cabecalhos = token_de(cliente, "jessica@mdca.org")
    with contas.begin() as conexao:
        conexao.execute(sa.text("UPDATE usuarios SET ativo = false WHERE id = 'jessica'"))

    assert cliente.get(EQUIPE, headers=cabecalhos).status_code == 401
    assert cliente.get("/notificacoes", headers=cabecalhos).status_code == 401


def test_token_alterado_ou_de_outra_chave_401(cliente, contas, monkeypatch):
    cabecalhos = token_de(cliente, "ana@mdca.org")
    alterado = {"Authorization": cabecalhos["Authorization"][:-3] + "xyz"}
    assert cliente.get(EQUIPE, headers=alterado).status_code == 401

    monkeypatch.setenv(sessao.VARIAVEL_CHAVE, "chave-trocada")
    assert cliente.get(EQUIPE, headers=cabecalhos).status_code == 401


def test_codigo_de_acesso_continua_valendo(cliente, cabecalhos, contas):
    resposta = cliente.get(EQUIPE, headers={**cabecalhos, "X-Usuario-Id": "ana"})

    assert resposta.status_code == 200


def test_token_vale_mesmo_sem_codigo_de_acesso_no_servidor(cliente, contas, monkeypatch):
    cabecalhos = token_de(cliente, "ana@mdca.org")
    monkeypatch.delenv("FINANCEIRO_API_TOKEN")

    assert cliente.get(EQUIPE, headers=cabecalhos).status_code == 200


def test_sem_codigo_e_sem_chave_no_servidor_503(cliente, contas, monkeypatch):
    monkeypatch.delenv("FINANCEIRO_API_TOKEN")
    monkeypatch.delenv(sessao.VARIAVEL_CHAVE)

    assert cliente.get(EQUIPE, headers={"Authorization": "Bearer qualquer"}).status_code == 503
