"""Consulta da trilha de auditoria: GET /auditoria, só coordenação e direção."""

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from Acesso import auditoria_consulta
from Acesso.routers.banco import RotaComBanco
from Financeiro.autenticacao import Papel, exigir_papel
from Gestao.banco import obter_conexao

router = APIRouter(prefix="/auditoria", tags=["auditoria"], route_class=RotaComBanco)

PERIODO_INVALIDO = "A data inicial não pode ser depois da final."


class EventoAuditoria(BaseModel):
    id: int
    ocorrido_em: datetime
    usuario_id: Optional[str]
    usuario_nome: Optional[str]
    modulo: str
    acao: str
    alvo_tipo: Optional[str]
    alvo_id: Optional[str]
    descricao: Optional[str]


@router.get("", response_model=List[EventoAuditoria])
def listar_auditoria(
    texto: Optional[str] = Query(None, max_length=200, description="Procura em ação, descrição, pessoa e alvo."),
    modulo: Optional[str] = Query(None, pattern="^(financeiro|gestao|plataforma)$"),
    desde: Optional[date] = None,
    ate: Optional[date] = None,
    limite: int = Query(auditoria_consulta.LIMITE_PADRAO, ge=1, le=auditoria_consulta.LIMITE_MAXIMO),
    _papel: Papel = Depends(exigir_papel(Papel.COORDENACAO, Papel.DIRECAO)),
    conexao: Connection = Depends(obter_conexao),
) -> List[EventoAuditoria]:
    if desde and ate and desde > ate:
        raise HTTPException(status_code=400, detail=PERIODO_INVALIDO)
    eventos = auditoria_consulta.consultar(
        conexao, texto=texto, modulo=modulo, desde=desde, ate=ate, limite=limite
    )
    return [EventoAuditoria(**e) for e in eventos]
