"""Registro de eventos de Gestão na trilha única da plataforma (``log_auditoria``, T-32).

A tabela só aceita inclusão (trigger no banco). Por enquanto Gestão registra as
tentativas de acesso negadas (US-01); o registro de consultas e alterações em dados
sensíveis chega com a US-13 (T-81).
"""

from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

MODULO = "gestao"
ACESSO_NEGADO = "acesso_negado"

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
