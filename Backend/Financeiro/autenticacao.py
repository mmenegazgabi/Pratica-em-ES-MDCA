"""Autenticação das rotas do Financeiro (T-11 · US-03).

Enquanto o login de usuários (US-08) não existe, as rotas protegidas exigem
um token de serviço no cabeçalho ``Authorization: Bearer <token>``. O valor
esperado vem da variável de ambiente ``FINANCEIRO_API_TOKEN``, configurada no
Cloud Run e nunca versionada.

Quando a US-08 for implementada, basta trocar o corpo de
``exigir_autenticacao`` pela validação do usuário logado; as rotas que já
dependem dela continuam iguais.

A verificação falha fechada: sem token configurado no servidor, nenhuma
requisição é aceita.
"""

import hmac
import os
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

VARIAVEL_TOKEN = "FINANCEIRO_API_TOKEN"

_esquema_bearer = HTTPBearer(
    auto_error=False,
    description="Token de serviço do Financeiro (provisório até a US-08).",
)


def exigir_autenticacao(
    credenciais: Optional[HTTPAuthorizationCredentials] = Depends(_esquema_bearer),
) -> str:
    token_esperado = os.getenv(VARIAVEL_TOKEN, "")
    if not token_esperado:
        raise HTTPException(
            status_code=503,
            detail="Autenticação da API não configurada no servidor.",
        )

    token_recebido = credenciais.credentials if credenciais else ""
    if not token_recebido or not hmac.compare_digest(
        token_recebido.encode(), token_esperado.encode()
    ):
        raise HTTPException(
            status_code=401,
            detail="Autenticação obrigatória.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return "servico-financeiro"
