"""Rotas do Financeiro e da Gestão com a sessão do login único (T-35)."""

from datetime import date, datetime, timezone

import pytest
import sqlalchemy as sa

from Acesso import sessoes
from Acesso.tests.conftest import TOKEN, criar_usuario
from Financeiro.comprovantes import ArmazenamentoEmMemoria
from Financeiro.orcamento import Orcamento
from Financeiro.projetos import _projetos
from Financeiro.rascunhos import caixa_de_rascunhos
from Financeiro.routers.comprovantes import obter_armazenamento
from Financeiro.routers.orcamentos import _orcamentos

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
ORCAMENTO = {
    "valor_total": 1000.0,
    "data_inicio": "2026-01-01",
    "data_fim": "2026-12-31",
    "categorias_despesa": ["materiais"],
}


@pytest.fixture(autouse=True)
def financeiro_limpo(app, monkeypatch):
    """As listas do Financeiro são do módulo: cada teste começa e termina vazio.

    O login usa o banco, mas o Financeiro fica em memória aqui para os testes
    conferirem as listas acima. O Financeiro no banco com sessão está em
    Financeiro/tests/test_acesso_por_papel.py.
    """
    monkeypatch.setenv("FINANCEIRO_ARMAZENAMENTO", "memoria")

    def limpar():
        _orcamentos.clear()
        _projetos.clear()
        caixa_de_rascunhos.limpar()

    limpar()
    app.dependency_overrides[obter_armazenamento] = ArmazenamentoEmMemoria
    yield
    app.dependency_overrides.pop(obter_armazenamento, None)
    limpar()


def _sessao(banco, usuario_id, papeis=(), ativo=True):
    criar_usuario(
        banco, id=usuario_id, nome=usuario_id.title(), email=f"{usuario_id}@mdca.org.br",
        papeis=papeis, ativo=ativo,
    )
    with banco.begin() as conexao:
        token, _ = sessoes.criar(conexao, usuario_id, False, datetime.now(timezone.utc))
    return token


def _vinculo_no_projeto_1(banco, usuario_id):
    """Educador só vê e lança no programa em que tem vínculo ativo (T-36)."""
    with banco.begin() as conexao:
        conexao.execute(sa.text(
            "INSERT INTO projetos (id, nome, identificador) VALUES ('projeto-1', 'Semear', 'SEMEAR') "
            "ON CONFLICT (id) DO NOTHING"
        ))
        conexao.execute(
            sa.text(
                "INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) "
                "VALUES (:id, :u, 'projeto-1', 'educador', '2025-01-01')"
            ),
            {"id": f"v-{usuario_id}", "u": usuario_id},
        )


def _bearer(token, **extra):
    return {"Authorization": f"Bearer {token}", **extra}


def _orcamento_existente():
    _orcamentos.append(
        Orcamento(
            id="orcamento-1",
            projeto_id="projeto-1",
            valor_total=1000,
            data_inicio=date(2026, 1, 1),
            data_fim=date(2026, 12, 31),
            categorias_despesa=["materiais"],
        )
    )


def test_coordenacao_por_sessao_cria_orcamento_e_projeto(banco, cliente):
    token = _sessao(banco, "ana", papeis=["coordenacao", "voluntario_financeiro"])
    cab = _bearer(token, **{"X-Papel-Usuario": "coordenacao"})

    projeto = cliente.post("/projetos", json={"nome": "Oficina"}, headers=cab)
    assert projeto.status_code == 201
    orcamento = cliente.post(
        "/orcamentos", json={**ORCAMENTO, "projeto_id": projeto.json()["id"]}, headers=cab
    )
    assert orcamento.status_code == 201


def test_papel_que_a_pessoa_nao_tem_da_403(banco, cliente):
    token = _sessao(banco, "bia", papeis=["voluntario_financeiro"])
    r = cliente.post(
        "/projetos", json={"nome": "Oficina"},
        headers=_bearer(token, **{"X-Papel-Usuario": "coordenacao"}),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "Ação permitida apenas para: coordenacao."
    assert _projetos == []


def test_sem_cabeçalho_usa_o_unico_papel_permitido(banco, cliente):
    # Rota de coordenação ou direção; a pessoa só tem coordenação entre as duas.
    token = _sessao(banco, "ana", papeis=["coordenacao", "educador"])
    cab = _bearer(token)
    projeto = cliente.post("/projetos", json={"nome": "Oficina"}, headers=cab).json()

    r = cliente.patch(
        f"/projetos/{projeto['id']}/status", json={"status": "encerrado"}, headers=cab
    )
    assert r.status_code == 200


def test_sem_cabecalho_com_dois_papeis_permitidos_da_403(banco, cliente):
    token = _sessao(banco, "ana", papeis=["coordenacao", "direcao"])
    cab = _bearer(token, **{"X-Papel-Usuario": "coordenacao"})
    projeto = cliente.post("/projetos", json={"nome": "Oficina"}, headers=cab).json()

    r = cliente.patch(
        f"/projetos/{projeto['id']}/status", json={"status": "encerrado"}, headers=_bearer(token)
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "Ação permitida apenas para: coordenacao, direcao."


def test_educador_por_sessao_le_orcamentos_mas_nao_cria_nem_aprova(banco, cliente):
    _orcamento_existente()
    token = _sessao(banco, "edu", papeis=["educador"])
    _vinculo_no_projeto_1(banco, "edu")

    assert cliente.get("/orcamentos/orcamento-1", headers=_bearer(token)).status_code == 200
    for cab in (_bearer(token), _bearer(token, **{"X-Papel-Usuario": "coordenacao"})):
        criar = cliente.post("/orcamentos", json={**ORCAMENTO, "projeto_id": "projeto-1"}, headers=cab)
        assert criar.status_code == 403
        aprovar = cliente.patch("/lancamentos/qualquer/aprovar", headers=cab)
        assert aprovar.status_code == 403
    assert len(_orcamentos) == 1


def test_autor_vem_da_sessao(banco, cliente):
    _orcamento_existente()
    token = _sessao(banco, "marcos", papeis=["educador"])
    _vinculo_no_projeto_1(banco, "marcos")
    cab = _bearer(token, **{"X-Usuario-Id": "outra-pessoa"})

    rascunho = cliente.post(
        "/rascunhos", files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")}, headers=cab
    )
    assert rascunho.status_code == 201
    assert caixa_de_rascunhos.do_autor("marcos")
    assert caixa_de_rascunhos.do_autor("outra-pessoa") == []

    lancamento = cliente.post(
        "/lancamentos",
        data={
            "orcamento_id": "orcamento-1",
            "valor": "42.50",
            "descricao": "Lanche",
            "categoria": "materiais",
            "data_despesa": "2026-03-10",
        },
        files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")},
        headers=cab,
    )
    assert lancamento.status_code == 201
    assert [l.autor_id for l in _orcamentos[0].lancamentos] == ["marcos"]


def test_token_desconhecido_da_401(banco, cliente):
    r = cliente.get("/projetos", headers=_bearer("token-que-nao-existe"))
    assert r.status_code == 401
    assert r.json()["detail"] == "Autenticação obrigatória."
    assert r.headers["WWW-Authenticate"] == "Bearer"


def test_usuario_desativado_perde_acesso_na_hora(banco, cliente):
    token = _sessao(banco, "ana", papeis=["coordenacao"])
    assert cliente.get("/projetos", headers=_bearer(token)).status_code == 200

    with banco.begin() as conexao:
        conexao.execute(sa.text("UPDATE usuarios SET ativo = false WHERE id = 'ana'"))

    assert cliente.get("/projetos", headers=_bearer(token)).status_code == 401


def test_sessao_vale_sem_token_de_servico_configurado(banco, cliente, monkeypatch):
    token = _sessao(banco, "ana", papeis=["coordenacao"])
    monkeypatch.delenv("FINANCEIRO_API_TOKEN")

    assert cliente.get("/projetos", headers=_bearer(token)).status_code == 200
    assert cliente.get("/projetos").status_code == 503


def test_banco_fora_do_ar_da_503(banco, cliente, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://ninguem@127.0.0.1:1/mdca_test")
    r = cliente.get("/projetos", headers=_bearer("um-token-qualquer"))
    assert r.status_code == 503
    assert r.json()["detail"] == "Banco de dados indisponível"


def test_gestao_aceita_sessao(banco, cliente):
    token = _sessao(banco, "ana")
    r = cliente.get("/gestao/papeis", headers=_bearer(token))
    assert r.status_code == 200
    assert "coordenacao" in {p["id"] for p in r.json()}


@pytest.mark.parametrize("papel", ["coordenacao", "direcao", "educador", "voluntario_financeiro"])
def test_modo_servico_continua_igual(banco, cliente, papel):
    # Token de serviço: papel e usuário dos cabeçalhos, sem precisar existir no banco.
    cab = _bearer(TOKEN, **{"X-Papel-Usuario": papel, "X-Usuario-Id": "fulana"})

    r = cliente.get("/lancamentos", headers=cab)
    assert r.status_code == 200

    r = cliente.post("/projetos", json={"nome": f"Oficina {papel}"}, headers=cab)
    assert r.status_code == (201 if papel == "coordenacao" else 403)

    r = cliente.post(
        "/rascunhos", files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")}, headers=cab
    )
    assert r.status_code == 201
    assert caixa_de_rascunhos.do_autor("fulana")
