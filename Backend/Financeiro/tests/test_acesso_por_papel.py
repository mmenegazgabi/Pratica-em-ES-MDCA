"""T-36 · US-08: restrição de acesso por papel no Financeiro, com o login único.

Plano de integração, Trabalho 3 ("pronto quando"): o educador é bloqueado no projeto de
outra pessoa, a Coordenação vê tudo e o voluntário financeiro não consegue aprovar
despesa. Aqui a pessoa entra pelo token de sessão e o papel vem do banco
(``usuarios_papeis`` e ``vinculos_equipe``), não da tela.

Programas: p-1 (Semear) e p-2 (Oficina). Pessoas:

- luana: Coordenação (papel da plataforma)       - jane: Direção
- vera: voluntária financeira                    - paula: psicóloga (sem papel do Financeiro)
- marcos: educador com vínculo ativo em p-1      - ana: educadora com vínculo ativo em p-2
- bruno: educador cujo vínculo com p-1 terminou  - rita: coordenação só pelo vínculo em p-2
- tiago: educador em p-1, conta desativada

Precisa do PostgreSQL descartável (``TEST_DATABASE_URL``), como os demais testes de banco.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from Acesso import senhas, sessoes
from Financeiro.main import app

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
CODIGO = "token-de-teste-banco"  # o mesmo da fixture banco_financeiro (código de acesso)
SENHA = "senha-de-teste-123"

client = TestClient(app)


_motor = None  # o banco da fixture, para abrir sessões do login (T-35)


@pytest.fixture
def pessoas(banco_financeiro):
    global _motor
    _motor = banco_financeiro
    ontem = date.today() - timedelta(days=1)
    hash_senha = senhas.gerar_hash(SENHA)
    with banco_financeiro.begin() as c:
        c.execute(sa.text("INSERT INTO projetos (id, nome, identificador) VALUES ('p-2', 'Oficina', 'OFICINA')"))
        c.execute(
            sa.text("INSERT INTO usuarios (id, nome, email, senha_hash, ativo) VALUES (:id, :nome, :email, :h, :ativo)"),
            [
                {"id": u, "nome": u.title(), "email": f"{u}@mdca.org.br", "h": hash_senha, "ativo": u != "tiago"}
                for u in ("luana", "jane", "vera", "paula", "marcos", "ana", "bruno", "rita", "tiago")
            ],
        )
        c.execute(
            sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES (:u, :p)"),
            [
                {"u": "luana", "p": "coordenacao"},
                {"u": "jane", "p": "direcao"},
                {"u": "vera", "p": "voluntario_financeiro"},
                {"u": "paula", "p": "psicologo"},
            ],
        )
        c.execute(
            sa.text(
                "INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada, data_saida) "
                "VALUES (:id, :u, :prog, :papel, '2025-01-01', :saida)"
            ),
            [
                {"id": "v-1", "u": "marcos", "prog": "p-1", "papel": "educador", "saida": None},
                {"id": "v-2", "u": "ana", "prog": "p-2", "papel": "educador", "saida": None},
                {"id": "v-3", "u": "bruno", "prog": "p-1", "papel": "educador", "saida": ontem},
                {"id": "v-4", "u": "rita", "prog": "p-2", "papel": "coordenacao", "saida": None},
                {"id": "v-5", "u": "tiago", "prog": "p-1", "papel": "educador", "saida": None},
            ],
        )
    return banco_financeiro


def sessao_de(usuario, **extra):
    """Sessão do login único (T-35), como a que POST /auth/entrar devolve."""
    with _motor.begin() as conexao:
        token, _ = sessoes.criar(conexao, usuario, False, datetime.now(timezone.utc))
    return {"Authorization": f"Bearer {token}", **extra}


@pytest.fixture
def orcamentos(pessoas):
    """Um orçamento em cada programa, criados pela Coordenação com o login."""
    ids = {}
    for programa in ("p-1", "p-2"):
        r = client.post(
            "/orcamentos",
            headers=sessao_de("luana"),
            json={"projeto_id": programa, "valor_total": 1000, "data_inicio": "2026-01-01",
                  "data_fim": "2026-12-31", "categorias_despesa": ["materiais"]},
        )
        assert r.status_code == 201, r.text
        ids[programa] = r.json()["id"]
    return ids


def lancar(orcamento_id, quem, valor="100.00"):
    return client.post(
        "/lancamentos",
        headers=sessao_de(quem),
        data={"orcamento_id": orcamento_id, "valor": valor, "descricao": "Tinta",
              "categoria": "materiais", "data_despesa": "2026-05-15"},
        files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")},
    )


def contar(motor, tabela):
    with motor.connect() as c:
        return c.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar_one()


# --- Educador: só os programas em que tem vínculo ---------------------------------


def test_educador_ve_so_os_programas_e_orcamentos_do_seu_vinculo(orcamentos):
    projetos = client.get("/projetos", headers=sessao_de("marcos")).json()
    lista = client.get("/orcamentos", headers=sessao_de("marcos")).json()

    assert [p["id"] for p in projetos] == ["p-1"]
    assert [o["id"] for o in lista] == [orcamentos["p-1"]]


@pytest.mark.parametrize(
    "rota",
    ["/orcamentos/{orc}", "/orcamentos/projeto/p-2"],
)
def test_educador_recebe_403_no_programa_de_outra_pessoa(orcamentos, rota):
    resposta = client.get(rota.format(orc=orcamentos["p-2"]), headers=sessao_de("marcos"))

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Você não tem vínculo com este programa."


def test_educador_nao_lanca_despesa_no_programa_de_outra_pessoa(orcamentos, pessoas):
    resposta = lancar(orcamentos["p-2"], "marcos")

    assert resposta.status_code == 403
    assert contar(pessoas, "lancamentos") == 0


def test_educador_lanca_no_proprio_programa_e_ve_so_os_proprios_lancamentos(orcamentos):
    do_marcos = lancar(orcamentos["p-1"], "marcos")
    da_ana = lancar(orcamentos["p-2"], "ana")
    assert (do_marcos.status_code, da_ana.status_code) == (201, 201)

    lista = client.get("/lancamentos", headers=sessao_de("marcos")).json()
    assert [l["id"] for l in lista] == [do_marcos.json()["id"]]
    # O lançamento de outra pessoa responde como inexistente.
    assert client.get(f"/lancamentos/{da_ana.json()['id']}", headers=sessao_de("marcos")).status_code == 404
    assert client.get(f"/lancamentos/{do_marcos.json()['id']}", headers=sessao_de("marcos")).status_code == 200


def test_educador_nao_completa_rascunho_em_programa_de_outra_pessoa(orcamentos, pessoas):
    rascunho = client.post(
        "/rascunhos", headers=sessao_de("marcos"), files={"comprovante": ("foto.jpg", JPEG, "image/jpeg")}
    ).json()

    resposta = client.post(
        f"/rascunhos/{rascunho['id']}/completar",
        headers=sessao_de("marcos"),
        data={"orcamento_id": orcamentos["p-2"], "valor": "10", "descricao": "x",
              "categoria": "materiais", "data_despesa": "2026-05-15"},
    )

    assert resposta.status_code == 403
    assert contar(pessoas, "rascunhos_lancamento") == 1  # o rascunho continua lá


def test_vinculo_encerrado_nao_da_acesso(orcamentos):
    assert client.get("/projetos", headers=sessao_de("bruno")).status_code == 403
    assert lancar(orcamentos["p-1"], "bruno").status_code == 403


# --- Coordenação vê tudo ------------------------------------------------------------


@pytest.mark.parametrize("quem", ["luana", "rita"])
def test_coordenacao_ve_todos_os_programas(orcamentos, quem):
    projetos = client.get("/projetos", headers=sessao_de(quem)).json()

    assert {p["id"] for p in projetos} == {"p-1", "p-2"}
    for orcamento_id in orcamentos.values():
        assert client.get(f"/orcamentos/{orcamento_id}", headers=sessao_de(quem)).status_code == 200


def test_coordenacao_e_direcao_aprovam(orcamentos):
    primeiro = lancar(orcamentos["p-1"], "marcos").json()["id"]
    segundo = lancar(orcamentos["p-2"], "ana").json()["id"]

    assert client.patch(f"/lancamentos/{primeiro}/aprovar", headers=sessao_de("luana")).status_code == 200
    assert client.patch(f"/lancamentos/{segundo}/aprovar", headers=sessao_de("jane")).status_code == 200


# --- Voluntário financeiro não aprova ------------------------------------------------


def test_voluntario_financeiro_nao_aprova_mas_concilia(orcamentos):
    lancamento = lancar(orcamentos["p-1"], "marcos").json()["id"]

    assert client.patch(f"/lancamentos/{lancamento}/aprovar", headers=sessao_de("vera")).status_code == 403
    assert client.patch(f"/lancamentos/{lancamento}/aprovar", headers=sessao_de("luana")).status_code == 200
    conciliado = client.patch(
        f"/lancamentos/{lancamento}/conciliar", json={"referencia_extrato": "ext-1"}, headers=sessao_de("vera")
    )
    assert conciliado.status_code == 200


# --- O papel vem do banco, não da tela ------------------------------------------------


def test_cabecalho_de_papel_e_ignorado_com_o_login(orcamentos):
    """O educador escreve "coordenacao" no cabeçalho e mesmo assim não aprova nem edita."""
    lancamento = lancar(orcamentos["p-1"], "marcos").json()["id"]
    finge = sessao_de("marcos", **{"X-Papel-Usuario": "coordenacao", "X-Usuario-Id": "luana"})

    assert client.patch(f"/lancamentos/{lancamento}/aprovar", headers=finge).status_code == 403
    assert client.patch(f"/orcamentos/{orcamentos['p-1']}", json={"valor_total": 9999}, headers=finge).status_code == 403
    assert client.post("/orcamentos", headers=finge, json={
        "projeto_id": "p-1", "valor_total": 1, "data_inicio": "2026-01-01", "data_fim": "2026-12-31",
        "categorias_despesa": ["x"]}).status_code == 403
    assert client.get("/dashboard/projetos", headers=finge).status_code == 403


@pytest.mark.parametrize(
    "metodo, rota",
    [("get", "/projetos"), ("get", "/orcamentos"), ("get", "/lancamentos"),
     ("get", "/notificacoes"), ("get", "/rascunhos")],
)
def test_sem_papel_do_financeiro_e_bloqueado(pessoas, metodo, rota):
    assert getattr(client, metodo)(rota, headers=sessao_de("paula")).status_code == 403


def test_conta_desativada_perde_o_acesso(pessoas):
    assert client.get("/projetos", headers=sessao_de("tiago")).status_code == 401


# --- Todas as rotas exigem login ------------------------------------------------------


@pytest.mark.parametrize(
    "metodo, rota",
    [("get", "/orcamentos"), ("get", "/orcamentos/x"), ("get", "/orcamentos/projeto/p-1"),
     ("post", "/orcamentos"), ("get", "/projetos"), ("get", "/lancamentos"), ("get", "/notificacoes"),
     ("get", "/rascunhos"), ("get", "/dashboard/projetos")],
)
def test_rotas_sem_login_respondem_401(pessoas, metodo, rota):
    assert getattr(client, metodo)(rota).status_code == 401


# --- Um login só para os dois módulos -----------------------------------------------------


def _api_integrada():
    """A API publicada no Cloud Run (Backend/main.py): Financeiro, Gestão e login juntos."""
    import importlib.util
    from pathlib import Path

    caminho = Path(__file__).resolve().parents[2] / "main.py"
    spec = importlib.util.spec_from_file_location("mdca_api_integrada_acesso", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return TestClient(modulo.app)


def test_entrar_uma_vez_e_usar_gestao_e_financeiro(orcamentos):
    api = _api_integrada()
    entrada = api.post("/auth/entrar", json={"email": "marcos@mdca.org.br", "senha": SENHA})
    assert entrada.status_code == 200
    token = {"Authorization": f"Bearer {entrada.json()['token']}"}

    assert [p["id"] for p in api.get("/projetos", headers=token).json()] == ["p-1"]
    assert api.get("/orcamentos/projeto/p-2", headers=token).status_code == 403
    assert api.get("/gestao/programas", headers=token).status_code == 200


# --- Transição: o código de acesso continua valendo, como antes ---------------------------


def test_codigo_de_acesso_continua_funcionando_como_antes(orcamentos):
    tela = {"Authorization": f"Bearer {CODIGO}", "X-Papel-Usuario": "educador", "X-Usuario-Id": "marcos"}

    # Sem restrição de programa: é o comportamento atual das telas do Financeiro.
    assert len(client.get("/orcamentos", headers=tela).json()) == 2


def test_sem_o_codigo_configurado_so_o_login_entra(orcamentos, monkeypatch):
    """Quando a tela Entrar estiver pronta, tirar FINANCEIRO_API_TOKEN do Cloud Run desliga o código."""
    monkeypatch.delenv("FINANCEIRO_API_TOKEN")

    assert client.get("/orcamentos", headers={"Authorization": f"Bearer {CODIGO}"}).status_code == 401
    assert client.get("/orcamentos", headers=sessao_de("luana")).status_code == 200
