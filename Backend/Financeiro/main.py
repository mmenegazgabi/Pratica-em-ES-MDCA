import uuid
from datetime import date
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="MDCA — Financeiro")

_orcamentos: List[dict] = []


class OrcamentoCreate(BaseModel):
    projeto_id: str
    valor_total: float
    data_inicio: date
    data_fim: date
    categorias_despesa: List[str] = Field(min_length=1)


class Orcamento(OrcamentoCreate):
    id: str


@app.post("/orcamentos", response_model=Orcamento, status_code=201)
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
    _orcamentos.append(orcamento.model_dump())
    return orcamento


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
