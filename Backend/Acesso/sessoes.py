"""Sessões do login único (T-35): token aleatório, guardado só como SHA-256.

Dura 30 dias com "lembrar de mim" e 12 horas sem. Datas (``agora``) são sempre
``datetime`` com fuso UTC.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

import sqlalchemy as sa
from sqlalchemy.engine import Connection

DURACAO_LEMBRAR = timedelta(days=30)
DURACAO_PADRAO = timedelta(hours=12)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def criar(conexao: Connection, usuario_id: str, lembrar: bool, agora: datetime) -> Tuple[str, datetime]:
    """Abre uma sessão e devolve o token (só aqui aparece em claro) e a validade."""
    token = secrets.token_urlsafe(32)
    expira_em = agora + (DURACAO_LEMBRAR if lembrar else DURACAO_PADRAO)
    conexao.execute(
        sa.text(
            "INSERT INTO sessoes (token_hash, usuario_id, criada_em, expira_em) "
            "VALUES (:h, :u, :agora, :expira)"
        ),
        {"h": _hash(token), "u": usuario_id, "agora": agora, "expira": expira_em},
    )
    return token, expira_em


def usuario_da_sessao(conexao: Connection, token: str, agora: datetime) -> Optional[str]:
    """Id do dono da sessão, ou ``None`` se não existe, venceu ou o usuário está inativo."""
    return conexao.execute(
        sa.text(
            "SELECT s.usuario_id FROM sessoes s JOIN usuarios u ON u.id = s.usuario_id "
            "WHERE s.token_hash = :h AND s.expira_em > :agora AND u.ativo"
        ),
        {"h": _hash(token), "agora": agora},
    ).scalar()


def encerrar(conexao: Connection, token: str) -> None:
    conexao.execute(sa.text("DELETE FROM sessoes WHERE token_hash = :h"), {"h": _hash(token)})


def encerrar_todas(conexao: Connection, usuario_id: str) -> None:
    conexao.execute(sa.text("DELETE FROM sessoes WHERE usuario_id = :u"), {"u": usuario_id})
