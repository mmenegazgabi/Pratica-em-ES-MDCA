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

Login único (T-35 · US-08): o ``Authorization: Bearer`` também aceita o token de
sessão devolvido por ``POST /auth/entrar`` (``Shared/sessao.py``). Com ele, quem
chama vem do token, e não do cabeçalho ``X-Usuario-Id``. O código de acesso continua
valendo enquanto os frontends migram para o login.
"""

import hmac
import os
from enum import Enum
from typing import Optional

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from Shared import sessao

VARIAVEL_TOKEN = "FINANCEIRO_API_TOKEN"

_esquema_bearer = HTTPBearer(
    auto_error=False,
    description="Token de sessão (POST /auth/entrar) ou código de acesso do Financeiro.",
)


def _token_recebido(credenciais: Optional[HTTPAuthorizationCredentials]) -> str:
    return credenciais.credentials if credenciais else ""


def exigir_autenticacao(
    credenciais: Optional[HTTPAuthorizationCredentials] = Depends(_esquema_bearer),
) -> str:
    token_esperado = os.getenv(VARIAVEL_TOKEN, "")
    if not token_esperado and not sessao.chave_configurada():
        raise HTTPException(
            status_code=503,
            detail="Autenticação da API não configurada no servidor.",
        )

    token_recebido = _token_recebido(credenciais)
    if token_recebido and token_esperado and hmac.compare_digest(
        token_recebido.encode(), token_esperado.encode()
    ):
        return "servico-financeiro"
    # Token de sessão: válido, não expirado e com a conta ainda ativa no banco.
    if token_recebido and sessao.usuario_da_sessao(token_recebido):
        return "sessao"

    raise HTTPException(
        status_code=401,
        detail="Autenticação obrigatória.",
        headers={"WWW-Authenticate": "Bearer"},
    )


# --- Papel do usuário (T-15 · US-04) ----------------------------------------
#
# Com token de sessão (T-35), o papel vem do banco: ``usuarios_papeis`` e os
# vínculos ativos em ``vinculos_equipe``. O cabeçalho ``X-Papel-Usuario`` só
# escolhe entre os papéis que a pessoa tem; sem ele, vale o primeiro permitido
# que ela tiver. Assim não dá para se declarar coordenação pelo cabeçalho.
# Limitação até a T-33: o papel de um vínculo vale para o Financeiro inteiro,
# porque os projetos do Financeiro ainda não estão ligados aos programas.
#
# Com o código de acesso compartilhado, o papel ainda vem só do cabeçalho, até
# os frontends migrarem para o login (T-35). As rotas continuam usando
# ``exigir_papel`` do mesmo jeito.

CABECALHO_PAPEL = "X-Papel-Usuario"


class Papel(str, Enum):
    COORDENACAO = "coordenacao"
    DIRECAO = "direcao"
    EDUCADOR = "educador"
    VOLUNTARIO_FINANCEIRO = "voluntario_financeiro"


def exigir_papel(*permitidos: Papel):
    def negado() -> HTTPException:
        return HTTPException(
            status_code=403,
            detail="Ação permitida apenas para: " + ", ".join(p.value for p in permitidos) + ".",
        )

    def verificar(
        autenticacao: str = Depends(exigir_autenticacao),
        papel: Optional[str] = Header(None, alias=CABECALHO_PAPEL),
        credenciais: Optional[HTTPAuthorizationCredentials] = Depends(_esquema_bearer),
    ) -> Papel:
        papel_normalizado = (papel or "").strip().lower()
        if autenticacao == "sessao":
            usuario_id = sessao.ler_token(_token_recebido(credenciais))
            if usuario_id is None:
                # Expirou entre a autenticação e aqui: pede login de novo, não é falta de papel.
                raise HTTPException(
                    status_code=401,
                    detail="Autenticação obrigatória.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            do_usuario = set(sessao.papeis_da_sessao(usuario_id))
            candidatos = [
                p
                for p in permitidos
                if p.value in do_usuario and papel_normalizado in ("", p.value)
            ]
            if not candidatos:
                raise negado()
            return candidatos[0]
        if papel_normalizado not in {p.value for p in permitidos}:
            raise negado()
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
    credenciais: Optional[HTTPAuthorizationCredentials] = Depends(_esquema_bearer),
) -> Optional[str]:
    """Usuário do token de sessão; sem ele, o do cabeçalho; ``None`` quando ausente.

    Com token de sessão o cabeçalho é ignorado: não dá para se passar por outra pessoa.
    A conta ativa já foi conferida por ``exigir_autenticacao``.
    """
    da_sessao = sessao.ler_token(_token_recebido(credenciais))
    if da_sessao is not None:
        return da_sessao
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
