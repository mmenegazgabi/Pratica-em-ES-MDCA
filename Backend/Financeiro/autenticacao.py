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
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import FrozenSet, Optional

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


# --- Papel do usuário (T-15 · US-04; T-33 · US-08) ---------------------------
#
# Com o token de sessão do login único, o papel vem do banco (``usuarios_papeis`` e
# ``vinculos_equipe``) e o cabeçalho ``X-Papel-Usuario`` é ignorado. Com o código de
# acesso (transição até a tela Entrar do Financeiro), o papel ainda chega nesse
# cabeçalho, como antes. ``exigir_papel`` fica no fim do arquivo.

CABECALHO_PAPEL = "X-Papel-Usuario"


class Papel(str, Enum):
    COORDENACAO = "coordenacao"
    DIRECAO = "direcao"
    EDUCADOR = "educador"
    VOLUNTARIO_FINANCEIRO = "voluntario_financeiro"


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


# --- Identidade e autorização (T-33 · US-08) ---------------------------------
#
# Plano de integração, Trabalho 3. Quem chama a API é uma ``Identidade``:
#
# - **Token de sessão** (login único): usuário do token; papéis do Financeiro que a
#   pessoa tem no banco, nos papéis da plataforma (``usuarios_papeis``) e nos vínculos
#   ativos com programas (``vinculos_equipe``). Quem só é educador enxerga apenas os
#   programas em que tem vínculo ativo; Coordenação, Direção e voluntário financeiro
#   enxergam todos. Sem nenhum papel do Financeiro, a pessoa é bloqueada (403).
# - **Código de acesso** (``FINANCEIRO_API_TOKEN``, só durante a transição): papel e
#   usuário dos cabeçalhos, sem restrição de programa, exatamente como antes. Para
#   desligar, basta tirar a variável do Cloud Run quando a tela Entrar estiver pronta.

PAPEIS_DO_FINANCEIRO = frozenset(p.value for p in Papel)
# Ordem usada quando a pessoa tem mais de um papel permitido na rota.
PRIORIDADE = (Papel.COORDENACAO, Papel.DIRECAO, Papel.VOLUNTARIO_FINANCEIRO, Papel.EDUCADOR)
# Quem tem algum destes papéis vê todos os programas; quem não tem, só os do vínculo.
PAPEIS_QUE_VEEM_TODOS_OS_PROGRAMAS = frozenset(
    {Papel.COORDENACAO.value, Papel.DIRECAO.value, Papel.VOLUNTARIO_FINANCEIRO.value}
)
SEM_VINCULO = "Você não tem vínculo com este programa."


@dataclass(frozen=True)
class Identidade:
    usuario_id: Optional[str]
    papeis: FrozenSet[str]
    via_sessao: bool
    # None: todos os programas. Conjunto: só esses (quem só é educador).
    programas: Optional[FrozenSet[str]] = None

    def ve_programa(self, programa_id: str) -> bool:
        return self.programas is None or programa_id in self.programas


def papeis_no_banco(usuario_id: str, hoje: Optional[date] = None) -> Identidade:
    """Papéis do Financeiro da pessoa e os programas que ela pode ver."""
    import sqlalchemy as sa
    from sqlalchemy.exc import SQLAlchemyError

    from Shared.banco import BANCO_INDISPONIVEL, conectar

    hoje = hoje or date.today()
    try:
        with conectar() as conexao:
            globais = set(
                conexao.execute(
                    sa.text("SELECT papel_id FROM usuarios_papeis WHERE usuario_id = :u"),
                    {"u": usuario_id},
                ).scalars()
            )
            vinculos = conexao.execute(
                sa.text(
                    """
                    SELECT papel_id, programa_id FROM vinculos_equipe
                    WHERE usuario_id = :u AND (data_saida IS NULL OR data_saida > :hoje)
                    """
                ),
                {"u": usuario_id, "hoje": hoje},
            ).all()
    except SQLAlchemyError as erro:
        raise HTTPException(status_code=503, detail=BANCO_INDISPONIVEL) from erro
    papeis = frozenset((globais | {v.papel_id for v in vinculos}) & PAPEIS_DO_FINANCEIRO)
    programas = None
    if not papeis & PAPEIS_QUE_VEEM_TODOS_OS_PROGRAMAS:
        programas = frozenset(v.programa_id for v in vinculos)
    return Identidade(usuario_id, papeis, via_sessao=True, programas=programas)


def obter_identidade(
    modo: str = Depends(exigir_autenticacao),
    usuario: Optional[str] = Depends(obter_usuario),
    papel: Optional[str] = Header(None, alias=CABECALHO_PAPEL),
) -> Identidade:
    if modo == "sessao":
        # O cabeçalho de papel é ignorado: o papel vem do banco, não da tela.
        return papeis_no_banco(usuario)
    papel = (papel or "").strip().lower()
    papeis = frozenset({papel}) if papel in PAPEIS_DO_FINANCEIRO else frozenset()
    return Identidade(usuario, papeis, via_sessao=False)


def _negar(permitidos) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail="Ação permitida apenas para: " + ", ".join(p.value for p in permitidos) + ".",
    )


def exigir_papel(*permitidos: Papel):
    """Exige um dos papéis; devolve o papel com que a pessoa age nesta rota."""

    def verificar(identidade: Identidade = Depends(obter_identidade)) -> Papel:
        for papel in PRIORIDADE:
            if papel in permitidos and papel.value in identidade.papeis:
                return papel
        raise _negar(permitidos)

    return verificar


def exigir_acesso_financeiro(identidade: Identidade = Depends(obter_identidade)) -> Identidade:
    """Rotas de qualquer papel do Financeiro.

    Com o login, quem não tem papel do Financeiro é bloqueado. Com o código de acesso,
    vale só o código, como antes (a tela manda o papel, mas as rotas de leitura não o
    exigiam).
    """
    if identidade.via_sessao and not identidade.papeis:
        raise _negar(PRIORIDADE)
    return identidade


def exigir_programa(identidade: Identidade, programa_id: str) -> None:
    """403 quando a pessoa não tem vínculo com o programa (educador em outro programa)."""
    if not identidade.ve_programa(programa_id):
        raise HTTPException(status_code=403, detail=SEM_VINCULO)
