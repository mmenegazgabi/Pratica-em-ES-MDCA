"""Acesso ao PostgreSQL do Módulo de Gestão.

As tabelas são criadas pelas migrations do Alembic em ``Backend/Shared/migrations``;
este módulo só abre conexões. A URL vem de ``DATABASE_URL`` (no Cloud Run, variável
do serviço; localmente, ``Backend/.env``).

As rotas recebem a conexão por ``Depends(obter_conexao)``. Sem banco configurado ou
acessível, respondem 503, como o ``/db/health``.
"""

import os
from functools import lru_cache
from typing import Iterator

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

BANCO_INDISPONIVEL = "Banco de dados indisponível"


def url_sqlalchemy(url: str) -> str:
    # Mesma regra de Shared/migrations/env.py: URLs postgres puras usam o psycopg 3.
    parsed = make_url(url)
    if parsed.drivername in ("postgresql", "postgres"):
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed.render_as_string(hide_password=False)


@lru_cache(maxsize=1)
def _motor(url: str) -> Engine:
    # Um pool por processo; pre_ping descarta conexões que o Neon fechou por inatividade.
    return create_engine(
        url_sqlalchemy(url),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )


def obter_conexao() -> Iterator[Connection]:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise HTTPException(status_code=503, detail=BANCO_INDISPONIVEL)
    try:
        conexao = _motor(url).connect()
    except SQLAlchemyError as erro:
        raise HTTPException(status_code=503, detail=BANCO_INDISPONIVEL) from erro
    # Ao sair, a conexão volta ao pool e o que não foi commitado é desfeito.
    with conexao:
        yield conexao
