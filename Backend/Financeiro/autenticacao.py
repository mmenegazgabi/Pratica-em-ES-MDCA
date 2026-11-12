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
requisição é aceita. ``Acesso`` e SQLAlchemy só são importados dentro das funções,
para o Financeiro continuar subindo sozinho (``Financeiro/main.py``) no modo serviço.
"""

import hmac
import logging
import os
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, FrozenSet, Optional

from fastapi import Depends, Header, HTTPException, Request
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
# Na sessão, precisa ser um dos papéis da pessoa (da plataforma ou de um vínculo ativo
# com programa, T-33); sem cabeçalho, vale o único papel permitido na rota que ela
# tiver. As rotas usam ``exigir_papel`` do mesmo jeito.

CABECALHO_PAPEL = "X-Papel-Usuario"


class Papel(str, Enum):
    COORDENACAO = "coordenacao"
    DIRECAO = "direcao"
    EDUCADOR = "educador"
    VOLUNTARIO_FINANCEIRO = "voluntario_financeiro"


# ``exigir_papel`` fica no fim do arquivo: decide a partir do ``AcessoFinanceiro``.


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


# --- Acesso no Financeiro (T-33 · US-08; T-34 para o acesso negado) ----------
#
# Plano de integração, Trabalho 3. A partir da ``Identidade`` do login (T-35), cada
# requisição do Financeiro vira um ``AcessoFinanceiro``:
#
# - **Sessão do login único:** papéis do Financeiro da pessoa nos papéis da plataforma
#   (``usuarios_papeis``) **e** nos vínculos ativos com programas (``vinculos_equipe``).
#   Quem só é educador enxerga apenas os programas em que tem vínculo ativo;
#   Coordenação, Direção e voluntário financeiro enxergam todos. Sem nenhum papel do
#   Financeiro, a pessoa é bloqueada (403).
# - **Token de serviço** (``FINANCEIRO_API_TOKEN``): papel e usuário dos cabeçalhos,
#   sem restrição de programa, como antes do login (testes e scripts).

PAPEIS_DO_FINANCEIRO = frozenset(p.value for p in Papel)
# Quem tem algum destes papéis vê todos os programas; quem não tem, só os do vínculo.
PAPEIS_QUE_VEEM_TODOS_OS_PROGRAMAS = frozenset(
    {Papel.COORDENACAO.value, Papel.DIRECAO.value, Papel.VOLUNTARIO_FINANCEIRO.value}
)
SEM_VINCULO = "Você não tem vínculo com este programa."

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AcessoFinanceiro:
    usuario_id: Optional[str]
    papeis: FrozenSet[str]
    via_sessao: bool
    # None: todos os programas. Conjunto: só esses (quem só é educador).
    programas: Optional[FrozenSet[str]] = None
    # "PATCH /lancamentos/x/aprovar": vai para a auditoria quando o acesso é negado.
    rota: str = ""

    def ve_programa(self, programa_id: str) -> bool:
        return self.programas is None or programa_id in self.programas


def _vinculos_ativos(usuario_id: str, hoje: date):
    """(papel, programa) dos vínculos ativos: sem data de saída ou saída depois de hoje."""
    import sqlalchemy as sa
    from sqlalchemy.exc import SQLAlchemyError

    from Shared.banco import BANCO_INDISPONIVEL, conectar

    try:
        with conectar() as conexao:
            return conexao.execute(
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


def obter_acesso(
    request: Request,
    identidade=Depends(exigir_autenticacao),
    usuario: Optional[str] = Depends(obter_usuario),
    papel: Optional[str] = Header(None, alias=CABECALHO_PAPEL),
) -> AcessoFinanceiro:
    rota = f"{request.method} {request.url.path}"
    if identidade.servico:
        papel = (papel or "").strip().lower()
        papeis = frozenset({papel}) if papel in PAPEIS_DO_FINANCEIRO else frozenset()
        return AcessoFinanceiro(usuario, papeis, via_sessao=False, rota=rota)
    vinculos = _vinculos_ativos(identidade.usuario_id, date.today())
    papeis = frozenset((set(identidade.papeis) | {v.papel_id for v in vinculos}) & PAPEIS_DO_FINANCEIRO)
    programas = None
    if not papeis & PAPEIS_QUE_VEEM_TODOS_OS_PROGRAMAS:
        programas = frozenset(v.programa_id for v in vinculos)
    return AcessoFinanceiro(identidade.usuario_id, papeis, via_sessao=True, programas=programas, rota=rota)


def registrar_acesso_negado(acesso: AcessoFinanceiro, motivo: str) -> None:
    """T-34: a tentativa negada vai para a trilha, em transação própria (a ação não acontece).

    Uma falha ao gravar não muda a resposta: o acesso continua negado.
    """
    if __package__:
        from .auditoria import ACESSO_NEGADO, MODULO
        from .persistencia import MEMORIA, usa_banco
    else:
        from auditoria import ACESSO_NEGADO, MODULO
        from persistencia import MEMORIA, usa_banco
    evento = dict(
        usuario_id=acesso.usuario_id,
        acao=ACESSO_NEGADO,
        alvo_tipo="rota",
        alvo_id=acesso.rota or None,
        descricao=acesso.rota or None,
        detalhes={"motivo": motivo, "papeis": sorted(acesso.papeis), "login": acesso.via_sessao},
    )
    try:
        if not usa_banco():
            MEMORIA.auditar(**evento)
            return
        from Shared.auditoria import registrar
        from Shared.banco import conectar

        with conectar() as conexao:
            registrar(conexao, modulo=MODULO, **evento)
            conexao.commit()
    except Exception:  # noqa: BLE001 — a auditoria não pode transformar um 403 em 500
        _log.warning("Não foi possível registrar o acesso negado na auditoria", exc_info=True)


def _negar(acesso: AcessoFinanceiro, permitidos) -> HTTPException:
    detalhe = "Ação permitida apenas para: " + ", ".join(p.value for p in permitidos) + "."
    registrar_acesso_negado(acesso, detalhe)
    return HTTPException(status_code=403, detail=detalhe)


def exigir_papel(*permitidos: Papel):
    """Exige um dos papéis; devolve o papel com que a pessoa age nesta rota.

    Regra do login (T-35): na sessão, o ``X-Papel-Usuario`` escolhe entre os papéis da
    pessoa (agora também os dos vínculos); sem ele, vale o único papel permitido que
    ela tiver. No modo serviço, o cabeçalho vale como veio.
    """
    valores_permitidos = {p.value for p in permitidos}

    def verificar(
        acesso: AcessoFinanceiro = Depends(obter_acesso),
        papel: Optional[str] = Header(None, alias=CABECALHO_PAPEL),
    ) -> Papel:
        papel_normalizado = (papel or "").strip().lower()
        if not acesso.via_sessao:
            if papel_normalizado not in valores_permitidos:
                raise _negar(acesso, permitidos)
            return Papel(papel_normalizado)

        possiveis = acesso.papeis & valores_permitidos
        if papel_normalizado:
            if papel_normalizado not in possiveis:
                raise _negar(acesso, permitidos)
            return Papel(papel_normalizado)
        if len(possiveis) != 1:
            raise _negar(acesso, permitidos)
        return Papel(next(iter(possiveis)))

    return verificar


def exigir_acesso_financeiro(acesso: AcessoFinanceiro = Depends(obter_acesso)) -> AcessoFinanceiro:
    """Rotas de qualquer papel do Financeiro.

    Com o login, quem não tem papel do Financeiro (nem da plataforma, nem de vínculo
    ativo) é bloqueado. No modo serviço vale só o token, como antes.
    """
    if acesso.via_sessao and not acesso.papeis:
        raise _negar(acesso, tuple(Papel))
    return acesso


def exigir_programa(acesso: AcessoFinanceiro, programa_id: str) -> None:
    """403 quando a pessoa não tem vínculo com o programa (educador em outro programa)."""
    if not acesso.ve_programa(programa_id):
        registrar_acesso_negado(acesso, SEM_VINCULO)
        raise HTTPException(status_code=403, detail=SEM_VINCULO)
