"""Fixtures dos testes do Módulo de Acesso (login único, T-35).

Mesmo esquema da Gestão: API integrada (``Backend/main.py``) e um PostgreSQL
descartável indicado por ``TEST_DATABASE_URL``, com o esquema das migrations.
"""

import os
from typing import Iterable, Optional

import pytest
import sqlalchemy as sa

from Gestao.tests.conftest import (  # noqa: F401  (fixtures reaproveitadas)
    TEST_DATABASE_URL,
    _garantir_banco_descartavel,
    app,
    cabecalhos,
    cliente,
    motor_de_teste,
)

TOKEN = "token-de-teste-gestao"


def _limpar(motor) -> None:
    # CASCADE leva sessões, códigos e vínculos junto com os usuários.
    with motor.begin() as conexao:
        conexao.execute(sa.text("TRUNCATE projetos, usuarios, log_auditoria CASCADE"))


@pytest.fixture
def banco(motor_de_teste, monkeypatch):
    """Banco de teste vazio, já apontado pela DATABASE_URL da API."""
    _garantir_banco_descartavel(TEST_DATABASE_URL)
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    _limpar(motor_de_teste)
    yield motor_de_teste
    _limpar(motor_de_teste)


def criar_usuario(
    motor,
    *,
    id: str,
    nome: str,
    email: Optional[str],
    papeis: Iterable[str] = (),
    senha: Optional[str] = None,
    ativo: bool = True,
) -> None:
    """Insere um usuário (com papéis e senha opcionais) já confirmado no banco."""
    from Acesso import senhas

    with motor.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO usuarios (id, nome, email, ativo, senha_hash) "
                "VALUES (:id, :nome, :email, :ativo, :senha_hash)"
            ),
            {
                "id": id,
                "nome": nome,
                "email": email,
                "ativo": ativo,
                "senha_hash": senhas.gerar_hash(senha) if senha else None,
            },
        )
        for papel in papeis:
            conexao.execute(
                sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES (:u, :p)"),
                {"u": id, "p": papel},
            )
