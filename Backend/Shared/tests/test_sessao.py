"""T-35 · US-08: password hashes and session tokens (no database needed)."""

import pytest

from Shared import sessao


@pytest.fixture(autouse=True)
def chave(monkeypatch):
    monkeypatch.setenv(sessao.VARIAVEL_CHAVE, "chave-de-teste")


def test_hash_confere_a_senha_certa_e_recusa_a_errada():
    guardado = sessao.gerar_hash_senha("senha-forte-1")

    assert guardado.startswith("scrypt$")
    assert "senha-forte-1" not in guardado
    assert sessao.conferir_senha("senha-forte-1", guardado)
    assert not sessao.conferir_senha("senha-forte-2", guardado)


def test_mesma_senha_gera_hashes_diferentes():
    assert sessao.gerar_hash_senha("igual") != sessao.gerar_hash_senha("igual")


@pytest.mark.parametrize("guardado", [None, "", "texto-puro", "bcrypt$1$2$3$4$5", "scrypt$x$8$1$a$b"])
def test_hash_ausente_ou_invalido_nunca_confere(guardado):
    assert not sessao.conferir_senha("qualquer", guardado)


def test_token_identifica_o_usuario_ate_expirar():
    token, expira_em = sessao.criar_token("ana", agora=1_000_000)

    assert sessao.parece_token_de_sessao(token)
    assert sessao.ler_token(token, agora=1_000_000) == "ana"
    assert sessao.ler_token(token, agora=1_000_000 + sessao.DURACAO_SESSAO - 1) == "ana"
    assert sessao.ler_token(token, agora=1_000_000 + sessao.DURACAO_SESSAO) is None
    assert expira_em.timestamp() == 1_000_000 + sessao.DURACAO_SESSAO


def test_token_alterado_e_recusado():
    token, _ = sessao.criar_token("jessica")
    prefixo, carga, assinatura = token.split(".")
    outro, _ = sessao.criar_token("admin")
    carga_de_outro = outro.split(".")[1]

    # Trocar o usuário dentro do token sem a chave não passa na assinatura.
    assert sessao.ler_token(f"{prefixo}.{carga_de_outro}.{assinatura}") is None
    assert sessao.ler_token(f"{prefixo}.{carga}.{assinatura[:-2]}xx") is None


def test_token_assinado_com_outra_chave_e_recusado(monkeypatch):
    token, _ = sessao.criar_token("ana")
    monkeypatch.setenv(sessao.VARIAVEL_CHAVE, "outra-chave")

    assert sessao.ler_token(token) is None


@pytest.mark.parametrize("token", ["", "codigo-de-acesso", "mdca1.", "mdca1.a.b.c", "mdca1.!!!.???"])
def test_texto_que_nao_e_token_valido_e_recusado(token):
    assert sessao.ler_token(token) is None


def test_sem_chave_no_servidor_nao_ha_login(monkeypatch):
    token, _ = sessao.criar_token("ana")
    monkeypatch.delenv(sessao.VARIAVEL_CHAVE)

    assert not sessao.chave_configurada()
    assert sessao.ler_token(token) is None
    with pytest.raises(RuntimeError):
        sessao.criar_token("ana")
