"""Consultas de usuários do login único (T-35)."""

import re
import unicodedata
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Row


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def por_email(conexao: Connection, email: str) -> Optional[Row]:
    """Usuário pelo e-mail (sem diferenciar maiúsculas); inclui os inativos."""
    return conexao.execute(
        sa.text(
            "SELECT id, nome, email, ativo, senha_hash FROM usuarios WHERE lower(email) = :email"
        ),
        {"email": normalizar_email(email)},
    ).first()


def dados_publicos(conexao: Connection, usuario_id: str) -> dict:
    """O que a tela pode saber da pessoa logada: id, nome, e-mail e papéis."""
    usuario = conexao.execute(
        sa.text("SELECT id, nome, email FROM usuarios WHERE id = :id"), {"id": usuario_id}
    ).one()
    papeis = conexao.execute(
        sa.text(
            "SELECT p.id, p.nome FROM usuarios_papeis up JOIN papeis p ON p.id = up.papel_id "
            "WHERE up.usuario_id = :id ORDER BY p.nome"
        ),
        {"id": usuario_id},
    ).all()
    return {
        "id": usuario.id,
        "nome": usuario.nome,
        "email": usuario.email,
        "papeis": [{"id": p.id, "nome": p.nome} for p in papeis],
    }


def _slug(nome: str) -> str:
    """Mesma regra de ``usuarioId`` em Frontend/Financeiro/base/sessao.js."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", nome) if not "̀" <= c <= "ͯ"
    )
    return re.sub(r"\s+", "-", sem_acento.strip().lower())


def novo_id(conexao: Connection, nome: str) -> str:
    """Id da pessoa: o slug do nome, com ``-2``, ``-3``… se já estiver em uso."""
    base = _slug(nome)
    candidato, n = base, 1
    while conexao.execute(
        sa.text("SELECT 1 FROM usuarios WHERE id = :id"), {"id": candidato}
    ).first():
        n += 1
        candidato = f"{base}-{n}"
    return candidato
