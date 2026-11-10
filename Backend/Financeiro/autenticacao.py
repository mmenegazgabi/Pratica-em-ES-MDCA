"""Autenticação das rotas do Financeiro (T-11 · US-03, login único T-35).

As rotas protegidas exigem ``Authorization: Bearer <token>``. Há dois modos:

- **serviço**: o token é o ``FINANCEIRO_API_TOKEN`` (variável de ambiente do Cloud
  Run, nunca versionada). Papel e usuário chegam nos cabeçalhos ``X-Papel-Usuario``
  e ``X-Usuario-Id``, como antes do login. Fica para testes, scripts e o front da
  Gestão enquanto ele não migra.
- **sessão**: qualquer outro token é procurado nas sessões do login único
  (``DATABASE_URL``). Quem chama é o dono da sessão; o papel precisa ser um dos dele.

``exigir_autenticacao`` devolve a ``Identidade`` (``Acesso/identidade.py``); as rotas
que já dependem dela, de ``exigir_papel`` ou de ``exigir_usuario`` continuam iguais.

A verificação falha fechada: sem token de serviço nem banco configurados, nenhuma
requisição é aceita. ``Acesso`` e SQLAlchemy só são importados dentro das funções:
o job do Financeiro no CI não instala o SQLAlchemy e roda só no modo serviço.
"""

import hmac
import os
from enum import Enum
from typing import TYPE_CHECKING, Optional

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

if TYPE_CHECKING:
    from Acesso.identidade import Identidade

VARIAVEL_TOKEN = "FINANCEIRO_API_TOKEN"

_esquema_bearer = HTTPBearer(
    auto_error=False,
    description="Token da sessão do login único ou token de serviço do Financeiro.",
)


def _nao_autenticado() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Autenticação obrigatória.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def exigir_autenticacao(
    credenciais: Optional[HTTPAuthorizationCredentials] = Depends(_esquema_bearer),
) -> "Identidade":
    from Acesso import identidade

    token_esperado = os.getenv(VARIAVEL_TOKEN, "")
    token_recebido = credenciais.credentials if credenciais else ""

    if token_esperado and token_recebido and hmac.compare_digest(
        token_recebido.encode(), token_esperado.encode()
    ):
        return identidade.SERVICO

    if token_recebido and identidade.sessoes_configuradas():
        quem = identidade.pela_sessao(token_recebido)
        if quem is None:
            raise _nao_autenticado()
        return quem

    # Sem sessão possível, vale a regra de antes do login: sem token de serviço
    # configurado no servidor, nada é aceito.
    if not token_esperado:
        raise HTTPException(
            status_code=503,
            detail="Autenticação da API não configurada no servidor.",
        )
    raise _nao_autenticado()


# --- Papel do usuário (T-15 · US-04) ----------------------------------------
#
# O papel com que a pessoa age chega no cabeçalho ``X-Papel-Usuario``.
# No modo serviço ele é aceito como veio (quem tem o token sabe quem está logado).
# Na sessão, precisa ser um dos papéis da pessoa; sem cabeçalho, vale o único papel
# permitido na rota que ela tiver. As rotas usam ``exigir_papel`` do mesmo jeito.

CABECALHO_PAPEL = "X-Papel-Usuario"


class Papel(str, Enum):
    COORDENACAO = "coordenacao"
    DIRECAO = "direcao"
    EDUCADOR = "educador"
    VOLUNTARIO_FINANCEIRO = "voluntario_financeiro"


def exigir_papel(*permitidos: Papel):
    valores_permitidos = {p.value for p in permitidos}

    def negar() -> HTTPException:
        return HTTPException(
            status_code=403,
            detail="Ação permitida apenas para: "
            + ", ".join(p.value for p in permitidos)
            + ".",
        )

    # Sem anotação de tipo: ``Identidade`` só é importada dentro das funções.
    def verificar(
        identidade=Depends(exigir_autenticacao),
        papel: Optional[str] = Header(None, alias=CABECALHO_PAPEL),
    ) -> Papel:
        papel_normalizado = (papel or "").strip().lower()
        if identidade.servico:
            if papel_normalizado not in valores_permitidos:
                raise negar()
            return Papel(papel_normalizado)

        possiveis = identidade.papeis & valores_permitidos
        if papel_normalizado:
            if papel_normalizado not in possiveis:
                raise negar()
            return Papel(papel_normalizado)
        if len(possiveis) != 1:
            raise negar()
        return Papel(next(iter(possiveis)))

    return verificar


# --- Identificação do usuário (T-17 · US-04) --------------------------------
#
# Serve para saber quem é o autor de um lançamento e de quem são as notificações.
# Na sessão, é o dono dela e o ``X-Usuario-Id`` é ignorado; no modo serviço, quem
# está logado chega nesse cabeçalho, como antes do login.

CABECALHO_USUARIO = "X-Usuario-Id"
USUARIO_TAMANHO_MAXIMO = 100


def obter_usuario(
    usuario: Optional[str] = Header(None, alias=CABECALHO_USUARIO),
    identidade=Depends(exigir_autenticacao),
) -> Optional[str]:
    """Usuário da sessão; no modo serviço, o do cabeçalho (``None`` quando ausente).

    Todas as rotas que usam esta dependência já exigem autenticação (o router de
    lançamentos declara ``exigir_autenticacao``); o FastAPI reaproveita o resultado
    na mesma requisição, então a sessão é consultada uma vez só.
    """
    if not identidade.servico:
        return identidade.usuario_id
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
    usuario: Optional[str] = Depends(obter_usuario),
) -> str:
    if usuario is None:
        raise HTTPException(
            status_code=400,
            detail="Identificação do usuário obrigatória.",
        )
    return usuario
