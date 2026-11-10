"""Códigos de acesso de uso único (T-35): primeiro acesso e redefinição de senha.

O código tem 9 caracteres sem os ambíguos (I, L, O, U, 0, 1), é mostrado como
``XXX-XXX-XXX``, vale 7 dias e só é gravado como SHA-256. Datas (``agora``) são
sempre ``datetime`` com fuso UTC.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

import sqlalchemy as sa
from sqlalchemy.engine import Connection

ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
TAMANHO = 9
VALIDADE = timedelta(days=7)


def gerar() -> str:
    letras = "".join(secrets.choice(ALFABETO) for _ in range(TAMANHO))
    return "-".join(letras[i : i + 3] for i in range(0, TAMANHO, 3))


def normalizar(codigo: str) -> str:
    """Tira espaços e hífens e põe em maiúsculas, para comparar com o que foi emitido."""
    return "".join(c for c in codigo if c not in " -\t\r\n").upper()


def _hash(codigo: str) -> str:
    return hashlib.sha256(normalizar(codigo).encode("utf-8")).hexdigest()


def emitir(
    conexao: Connection, usuario_id: str, criado_por: Optional[str], agora: datetime
) -> Tuple[str, datetime]:
    """Invalida os códigos pendentes do usuário e grava um novo. Quem chama faz o commit."""
    conexao.execute(
        sa.text("UPDATE codigos_acesso SET usado_em = :agora WHERE usuario_id = :u AND usado_em IS NULL"),
        {"agora": agora, "u": usuario_id},
    )
    codigo = gerar()
    validade = agora + VALIDADE
    conexao.execute(
        sa.text(
            "INSERT INTO codigos_acesso (usuario_id, codigo_hash, criado_em, expira_em, criado_por) "
            "VALUES (:u, :h, :agora, :validade, :por)"
        ),
        {"u": usuario_id, "h": _hash(codigo), "agora": agora, "validade": validade, "por": criado_por},
    )
    return codigo, validade


def consumir(conexao: Connection, usuario_id: str, codigo: str, agora: datetime) -> bool:
    """Marca o código como usado se for válido; o UPDATE condicional evita uso em duplicidade."""
    resultado = conexao.execute(
        sa.text(
            "UPDATE codigos_acesso SET usado_em = :agora "
            "WHERE usuario_id = :u AND codigo_hash = :h AND usado_em IS NULL AND expira_em >= :agora"
        ),
        {"agora": agora, "u": usuario_id, "h": _hash(codigo)},
    )
    return resultado.rowcount > 0
