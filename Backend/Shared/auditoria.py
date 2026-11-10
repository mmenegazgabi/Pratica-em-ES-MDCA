"""Trilha única de auditoria da plataforma (``log_auditoria``, T-32).

Gestão, Financeiro e o login gravam na mesma tabela, cada um com o seu ``modulo``
(``gestao``, ``financeiro`` ou ``plataforma``). A tabela só aceita inclusão (trigger no
banco): nenhuma rota edita ou apaga um registro.

``registrar`` não faz commit: quem chama grava o evento na mesma transação da ação, e
se a ação falhar o registro também não fica.
"""

from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

MODULOS = ("gestao", "financeiro", "plataforma")
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
    modulo: str,
    usuario_id: Optional[str],
    acao: str,
    alvo_tipo: Optional[str] = None,
    alvo_id: Optional[str] = None,
    descricao: Optional[str] = None,
    detalhes: Optional[Dict[str, Any]] = None,
) -> None:
    """Inclui um evento. Quem chama decide quando fazer o commit."""
    if modulo not in MODULOS:
        raise ValueError(f"Módulo de auditoria desconhecido: {modulo}")
    conexao.execute(
        _INSERIR,
        {
            "usuario_id": usuario_id,
            "modulo": modulo,
            "acao": acao,
            "alvo_tipo": alvo_tipo,
            "alvo_id": alvo_id,
            "descricao": descricao,
            "detalhes": detalhes,
        },
    )
