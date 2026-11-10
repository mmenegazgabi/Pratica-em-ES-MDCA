"""Registro de eventos de Gestão na trilha única da plataforma (``log_auditoria``, T-32).

A gravação é a mesma do Financeiro (``Shared/auditoria.py``); aqui só fica o módulo
``gestao``. A tabela só aceita inclusão (trigger no banco). Gestão registra as
tentativas de acesso negadas (US-01) e as consultas e alterações em dados sensíveis.
"""

from typing import Any, Dict, Optional

from sqlalchemy.engine import Connection

from Shared import auditoria as _trilha
from Shared.auditoria import ACESSO_NEGADO

__all__ = ["ACESSO_NEGADO", "MODULO", "registrar"]

MODULO = "gestao"


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
    """Inclui um evento de Gestão. Quem chama decide quando fazer o commit."""
    _trilha.registrar(
        conexao,
        modulo=MODULO,
        usuario_id=usuario_id,
        acao=acao,
        alvo_tipo=alvo_tipo,
        alvo_id=alvo_id,
        descricao=descricao,
        detalhes=detalhes,
    )
