"""Resposta 422 para corpo inválido, usada pelos dois apps (Financeiro e o de deploy).

O handler padrão do FastAPI ecoa o valor recebido ("input"); NaN/Infinity não
serializam em JSON e a resposta virava 500.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def erro_de_validacao(_request: Request, erro: RequestValidationError) -> JSONResponse:
    detalhes = [{k: v for k, v in e.items() if k not in ("input", "ctx")} for e in erro.errors()]
    return JSONResponse(status_code=422, content={"detail": detalhes})


def registrar_erro_de_validacao(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, erro_de_validacao)
