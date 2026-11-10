"""GET /auditoria: leitura da trilha única (log_auditoria)."""

import json

import sqlalchemy as sa

from Acesso.tests.conftest import criar_usuario


def _evento(banco, *, acao="criar_orcamento", modulo="financeiro", usuario_id=None, alvo_id=None,
            descricao=None, ocorrido_em="2026-10-05T12:00:00+00:00", detalhes=None, alvo_tipo=None):
    with banco.begin() as c:
        c.execute(
            sa.text(
                "INSERT INTO log_auditoria (ocorrido_em, usuario_id, modulo, acao, alvo_tipo, alvo_id, descricao, detalhes) "
                "VALUES (:o, :u, :m, :a, :t, :i, :d, CAST(:det AS jsonb))"
            ),
            {"o": ocorrido_em, "u": usuario_id, "m": modulo, "a": acao, "t": alvo_tipo, "i": alvo_id,
             "d": descricao, "det": json.dumps(detalhes) if detalhes is not None else None},
        )


def _servico(cabecalhos, papel="coordenacao"):
    return {**cabecalhos, "X-Papel-Usuario": papel}


def _ler(cliente, cabecalhos, papel="coordenacao", **params):
    return cliente.get("/auditoria", params=params, headers=_servico(cabecalhos, papel))


def test_sem_autenticacao_401(banco, cliente):
    assert cliente.get("/auditoria").status_code == 401


def test_papeis_negados_403(banco, cliente, cabecalhos):
    for papel in ("voluntario_financeiro", "educador"):
        assert _ler(cliente, cabecalhos, papel).status_code == 403


def test_coordenacao_e_direcao_leem(banco, cliente, cabecalhos):
    _evento(banco)
    for papel in ("coordenacao", "direcao"):
        r = _ler(cliente, cabecalhos, papel)
        assert r.status_code == 200 and len(r.json()) == 1


def test_sessao_com_papel_direcao(banco, cliente):
    criar_usuario(banco, id="dir", nome="Diretora", email="dir@mdca.org.br", papeis=("direcao",), senha="senha-boa-1")
    token = cliente.post("/auth/entrar", json={"email": "dir@mdca.org.br", "senha": "senha-boa-1"}).json()["token"]
    _evento(banco)
    r = cliente.get("/auditoria", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and len(r.json()) >= 1


def test_forma_da_resposta_sem_detalhes_e_com_nome(banco, cliente, cabecalhos):
    criar_usuario(banco, id="u1", nome="Ana Souza", email="ana@mdca.org.br")
    _evento(banco, usuario_id="u1", alvo_tipo="orcamento", alvo_id="o-1", descricao="Criou orçamento",
            detalhes={"segredo": "x"})

    (evento,) = _ler(cliente, cabecalhos).json()

    assert set(evento) == {"id", "ocorrido_em", "usuario_id", "usuario_nome", "modulo", "acao",
                           "alvo_tipo", "alvo_id", "descricao"}
    assert evento["usuario_nome"] == "Ana Souza"
    assert evento["modulo"] == "financeiro" and evento["alvo_id"] == "o-1"
    assert "segredo" not in json.dumps(evento)


def test_usuario_sem_cadastro_vem_sem_nome(banco, cliente, cabecalhos):
    _evento(banco, usuario_id="texto-livre")

    (evento,) = _ler(cliente, cabecalhos).json()

    assert evento["usuario_id"] == "texto-livre" and evento["usuario_nome"] is None


def test_ordem_mais_recente_primeiro(banco, cliente, cabecalhos):
    _evento(banco, acao="a1", ocorrido_em="2026-10-01T10:00:00+00:00")
    _evento(banco, acao="a3", ocorrido_em="2026-10-03T10:00:00+00:00")
    _evento(banco, acao="a2", ocorrido_em="2026-10-02T10:00:00+00:00")

    assert [e["acao"] for e in _ler(cliente, cabecalhos).json()] == ["a3", "a2", "a1"]


def test_filtro_de_modulo(banco, cliente, cabecalhos):
    _evento(banco, modulo="financeiro", acao="f")
    _evento(banco, modulo="gestao", acao="g")
    _evento(banco, modulo="plataforma", acao="p")

    assert [e["acao"] for e in _ler(cliente, cabecalhos, modulo="gestao").json()] == ["g"]
    assert _ler(cliente, cabecalhos, modulo="outro").status_code == 422


def test_busca_em_acao_descricao_usuario_e_alvo_sem_caixa(banco, cliente, cabecalhos):
    _evento(banco, acao="aprovar_lancamento")
    _evento(banco, acao="x1", descricao="Rejeitou a Despesa de materiais")
    _evento(banco, acao="x2", usuario_id="Maria-123")
    _evento(banco, acao="x3", alvo_id="ALVO-999")
    _evento(banco, acao="x4", descricao="nada a ver")

    def achar(t):
        return sorted(e["acao"] for e in _ler(cliente, cabecalhos, texto=t).json())

    assert achar("APROVAR") == ["aprovar_lancamento"]
    assert achar("despesa") == ["x1"]
    assert achar("maria") == ["x2"]
    assert achar("alvo-9") == ["x3"]


def test_busca_trata_coringas_como_texto(banco, cliente, cabecalhos):
    _evento(banco, acao="x1", descricao="100% pago")
    _evento(banco, acao="x2", descricao="outra coisa")

    assert [e["acao"] for e in _ler(cliente, cabecalhos, texto="%").json()] == ["x1"]
    assert _ler(cliente, cabecalhos, texto="_").json() == []


def test_filtro_de_periodo_inclui_os_dois_dias(banco, cliente, cabecalhos):
    _evento(banco, acao="antes", ocorrido_em="2026-10-01T15:00:00+00:00")
    _evento(banco, acao="primeiro", ocorrido_em="2026-10-02T15:00:00+00:00")
    _evento(banco, acao="ultimo", ocorrido_em="2026-10-04T23:00:00+00:00")  # 20h em Brasília
    _evento(banco, acao="depois", ocorrido_em="2026-10-05T15:00:00+00:00")

    r = _ler(cliente, cabecalhos, desde="2026-10-02", ate="2026-10-04")

    assert sorted(e["acao"] for e in r.json()) == ["primeiro", "ultimo"]
    assert [e["acao"] for e in _ler(cliente, cabecalhos, desde="2026-10-05").json()] == ["depois"]


def test_periodo_invertido_400_e_data_invalida_422(banco, cliente, cabecalhos):
    r = _ler(cliente, cabecalhos, desde="2026-10-05", ate="2026-10-01")
    assert r.status_code == 400
    assert _ler(cliente, cabecalhos, desde="ontem").status_code == 422


def test_limite_padrao_maximo_e_validacao(banco, cliente, cabecalhos):
    with banco.begin() as c:
        c.execute(sa.text(
            "INSERT INTO log_auditoria (modulo, acao) SELECT 'gestao', 'a' || g FROM generate_series(1, 520) g"
        ))

    assert len(_ler(cliente, cabecalhos).json()) == 200
    assert len(_ler(cliente, cabecalhos, limite=500).json()) == 500
    assert len(_ler(cliente, cabecalhos, limite=3).json()) == 3
    assert _ler(cliente, cabecalhos, limite=501).status_code == 422
    assert _ler(cliente, cabecalhos, limite=0).status_code == 422


def test_filtros_combinam(banco, cliente, cabecalhos):
    _evento(banco, modulo="financeiro", acao="aprovar", ocorrido_em="2026-10-02T15:00:00+00:00")
    _evento(banco, modulo="gestao", acao="aprovar", ocorrido_em="2026-10-02T15:00:00+00:00")
    _evento(banco, modulo="financeiro", acao="aprovar", ocorrido_em="2026-09-02T15:00:00+00:00")

    r = _ler(cliente, cabecalhos, texto="aprov", modulo="financeiro", desde="2026-10-01")

    assert len(r.json()) == 1


def test_erro_de_banco_vira_503(cliente, cabecalhos, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert _ler(cliente, cabecalhos).status_code == 503
