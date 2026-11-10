"""Registro de eventos de login na trilha única da plataforma (``log_auditoria``, T-32).

Mesma forma de ``Gestao/auditoria.py``, com o módulo ``plataforma`` (login e códigos de acesso
não pertencem a Financeiro nem a Gestão). A tabela só aceita inclusão.
"""

from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

MODULO = "plataforma"

_INSERIR = sa.text(
    """
    INSERT INTO log_auditoria (usuario_id, modulo, acao, alvo_tipo, alvo_id, descricao, detalhes)
    VALUES (:usuario_id, :modulo, :acao, :alvo_tipo, :alvo_id, :descricao, :detalhes)
    """
).bindparams(sa.bindparam("detalhes", type_=JSONB))


def registrar(
    conexao: Connection,
    *,
    usuario_id: Optional[str],
    acao: str,
    alvo_tipo: Optional[str] = None,
    alvo_id: Optional[str] = None,
    descricao: Optional[str] = None,
    detalhes: Optional[Dict[str, Any]] = None,
) -> None:
    """Inclui um evento. Quem chama decide quando fazer o commit."""
    conexao.execute(
        _INSERIR,
        {
            "usuario_id": usuario_id,
            "modulo": MODULO,
            "acao": acao,
            "alvo_tipo": alvo_tipo,
            "alvo_id": alvo_id,
            "descricao": descricao,
            "detalhes": detalhes,
        },
    )
