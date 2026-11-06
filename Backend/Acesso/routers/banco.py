"""Erro do banco nas rotas de Acesso vira 503 (T-35).

Sem isto, um ``SQLAlchemyError`` (por exemplo, a migration do login ainda não
aplicada: as tabelas não existem) sobe como 500 e sai sem os cabeçalhos de CORS; o
navegador só mostra "falha de rede". Como ``HTTPException``, a resposta passa pelo
CORS e a tela mostra "Banco de dados indisponível", como nas rotas da Gestão.
"""

from typing import Callable

from fastapi import HTTPException, Request, Response
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError

from Gestao.banco import BANCO_INDISPONIVEL


class RotaComBanco(APIRoute):
    """Rota cujo erro de banco (nas dependências ou na função) responde 503."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def tratar(requisicao: Request) -> Response:
            try:
                return await original(requisicao)
            except SQLAlchemyError as erro:
                raise HTTPException(status_code=503, detail=BANCO_INDISPONIVEL) from erro

        return tratar
