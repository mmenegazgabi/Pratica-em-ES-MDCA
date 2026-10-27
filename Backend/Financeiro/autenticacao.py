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
from enum import Enum
from typing import Optional

from fastapi import Depends, Header, HTTPException
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


# --- Papel do usuário (T-15 · US-04) ----------------------------------------
#
# Provisório até a US-08: o papel chega no cabeçalho ``X-Papel-Usuario`` e só
# é aceito junto com o token de serviço (quem tem o token é o frontend, que já
# sabe quem está logado). Na US-08 o papel passa a vir do usuário autenticado;
# as rotas continuam usando ``exigir_papel`` do mesmo jeito.

CABECALHO_PAPEL = "X-Papel-Usuario"


class Papel(str, Enum):
    COORDENACAO = "coordenacao"
    DIRECAO = "direcao"
    EDUCADOR = "educador"
    VOLUNTARIO_FINANCEIRO = "voluntario_financeiro"


def exigir_papel(*permitidos: Papel):
    def verificar(
        _servico: str = Depends(exigir_autenticacao),
        papel: Optional[str] = Header(None, alias=CABECALHO_PAPEL),
    ) -> Papel:
        papel_normalizado = (papel or "").strip().lower()
        if papel_normalizado not in {p.value for p in permitidos}:
            raise HTTPException(
                status_code=403,
                detail="Ação permitida apenas para: "
                + ", ".join(p.value for p in permitidos)
                + ".",
            )
        return Papel(papel_normalizado)

    return verificar


# --- Identificação do usuário (T-17 · US-04) --------------------------------
#
# Provisório até a US-08, no mesmo esquema do papel: quem está logado chega no
# cabeçalho ``X-Usuario-Id``, sempre junto com o token de serviço. Serve para
# saber quem é o autor de um lançamento e de quem são as notificações.

CABECALHO_USUARIO = "X-Usuario-Id"
USUARIO_TAMANHO_MAXIMO = 100


def obter_usuario(
    usuario: Optional[str] = Header(None, alias=CABECALHO_USUARIO),
) -> Optional[str]:
    """Usuário informado no cabeçalho, ou ``None`` quando ausente."""
    usuario = (usuario or "").strip()
    if not usuario:
        return None
    if len(usuario) > USUARIO_TAMANHO_MAXIMO:
        raise HTTPException(
            status_code=400,
            detail=f"{CABECALHO_USUARIO} deve ter no máximo {USUARIO_TAMANHO_MAXIMO} caracteres.",
        )
    return usuario


def exigir_usuario(
    _servico: str = Depends(exigir_autenticacao),
    usuario: Optional[str] = Depends(obter_usuario),
) -> str:
    if usuario is None:
        raise HTTPException(
            status_code=400,
            detail="Identificação do usuário obrigatória.",
        )
    return usuario
