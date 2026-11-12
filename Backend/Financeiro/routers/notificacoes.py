"""Notificações in-app do usuário (T-17 · US-04).

GET   /notificacoes               -> notificações de quem está logado
PATCH /notificacoes/{id}/lida     -> marca como lida

Quem está logado vem da sessão do login único (ou de ``X-Usuario-Id`` no modo serviço).
Cada usuário só vê e altera as próprias notificações.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

if __package__ == "routers":
    from autenticacao import exigir_acesso_financeiro, exigir_usuario
    from notificacoes import (
        Notificacao,
        NotificacaoNaoEncontrada,
        TipoNotificacao,
    )
    from persistencia import obter_repositorio
else:
    from ..autenticacao import exigir_acesso_financeiro, exigir_usuario
    from ..notificacoes import (
        Notificacao,
        NotificacaoNaoEncontrada,
        TipoNotificacao,
    )
    from ..persistencia import obter_repositorio

router = APIRouter(
    prefix="/notificacoes",
    tags=["notificacoes"],
    dependencies=[Depends(exigir_acesso_financeiro)],
)


class NotificacaoSaida(BaseModel):
    id: str
    lancamento_id: str
    tipo: TipoNotificacao
    mensagem: str
    motivo: Optional[str]
    lida: bool
    criada_em: datetime


def _saida(notificacao: Notificacao) -> NotificacaoSaida:
    return NotificacaoSaida(
        id=notificacao.id,
        lancamento_id=notificacao.lancamento_id,
        tipo=notificacao.tipo,
        mensagem=notificacao.mensagem,
        motivo=notificacao.motivo,
        lida=notificacao.lida,
        criada_em=notificacao.criada_em,
    )


@router.get("", response_model=List[NotificacaoSaida])
def listar_notificacoes(
    nao_lidas: bool = Query(False, description="Só as que ainda não foram lidas."),
    usuario: str = Depends(exigir_usuario),
    repositorio=Depends(obter_repositorio),
) -> List[NotificacaoSaida]:
    return [_saida(n) for n in repositorio.listar_notificacoes(usuario, nao_lidas)]


@router.patch("/{notificacao_id}/lida", response_model=NotificacaoSaida)
def marcar_notificacao_como_lida(
    notificacao_id: str,
    usuario: str = Depends(exigir_usuario),
    repositorio=Depends(obter_repositorio),
) -> NotificacaoSaida:
    try:
        notificacao = repositorio.marcar_notificacao_como_lida(notificacao_id, usuario)
    except NotificacaoNaoEncontrada as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    repositorio.confirmar()
    return _saida(notificacao)
