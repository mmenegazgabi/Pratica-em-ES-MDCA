import uuid
from datetime import date
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from orcamento import Orcamento

router = APIRouter(tags=["orcamentos"])

_orcamentos: List[Orcamento] = []


class OrcamentoCreate(BaseModel):
    projeto_id: str
    valor_total: float
    data_inicio: date
    data_fim: date
    categorias_despesa: List[str] = Field(min_length=1)


class OrcamentoDetalhe(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    projeto_id: str
    valor_total: float
    data_inicio: date
    data_fim: date
    categorias_despesa: List[str]
    saldo: float


def _buscar_orcamento(orcamento_id: str) -> Orcamento:
    for orcamento in _orcamentos:
        if orcamento.id == orcamento_id:
            return orcamento
    raise HTTPException(status_code=404, detail="Orçamento não encontrado")


@router.post("/orcamentos", response_model=Orcamento, status_code=201)
def criar_orcamento(payload: OrcamentoCreate) -> Orcamento:
    if payload.valor_total < 0:
        raise HTTPException(
            status_code=400,
            detail="valor_total não pode ser negativo",
        )
    if payload.data_fim < payload.data_inicio:
        raise HTTPException(
            status_code=400,
            detail="data_fim não pode ser anterior a data_inicio",
        )

    orcamento = Orcamento(id=str(uuid.uuid4()), **payload.model_dump())
    _orcamentos.append(orcamento)
    return orcamento


@router.get("/orcamentos/{orcamento_id}", response_model=OrcamentoDetalhe)
def obter_orcamento(orcamento_id: str) -> Orcamento:
    return _buscar_orcamento(orcamento_id)
