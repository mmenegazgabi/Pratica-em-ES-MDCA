"""Quem está chamando a API (T-35): o token de serviço ou uma pessoa logada.

``Financeiro/autenticacao.py`` monta a ``Identidade`` e as rotas do Financeiro e da
Gestão decidem a partir dela. Este módulo só usa a biblioteca padrão no topo: o job
do Financeiro no CI não instala o SQLAlchemy, e o modo serviço não toca no banco.
A consulta da sessão importa o que precisa só quando é chamada.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import FrozenSet, Optional


@dataclass(frozen=True)
class Identidade:
    # Token de serviço: papel e usuário seguem vindo dos cabeçalhos, como antes.
    servico: bool
    # Na sessão, o dono dela; no modo serviço, ``None``.
    usuario_id: Optional[str]
    # Papéis da plataforma da pessoa (``usuarios_papeis``); vazio no modo serviço.
    papeis: FrozenSet[str]


SERVICO = Identidade(servico=True, usuario_id=None, papeis=frozenset())


def sessoes_configuradas() -> bool:
    """Sem ``DATABASE_URL`` não existe sessão possível, só o token de serviço."""
    return bool(os.getenv("DATABASE_URL", ""))


def pela_sessao(token: str) -> Optional[Identidade]:
    """Identidade do dono da sessão, ou ``None`` se o token não é de uma sessão válida.

    Banco não configurado ou fora do ar: 503, como nas rotas da Gestão.
    """
    from fastapi import HTTPException
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError

    from Acesso import sessoes
    from Gestao.banco import BANCO_INDISPONIVEL, _motor

    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise HTTPException(status_code=503, detail=BANCO_INDISPONIVEL)
    try:
        with _motor(url).connect() as conexao:
            usuario_id = sessoes.usuario_da_sessao(conexao, token, datetime.now(timezone.utc))
            if usuario_id is None:
                return None
            papeis = conexao.execute(
                text("SELECT papel_id FROM usuarios_papeis WHERE usuario_id = :u"),
                {"u": usuario_id},
            ).scalars()
            return Identidade(servico=False, usuario_id=usuario_id, papeis=frozenset(papeis))
    except SQLAlchemyError as erro:
        raise HTTPException(status_code=503, detail=BANCO_INDISPONIVEL) from erro
