from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

if __package__ == "routers":
    from autenticacao import Papel, exigir_autenticacao, exigir_papel
    from projetos import (
        Projeto,
        ProjetoDuplicado,
        ProjetoInvalido,
        listar_projetos,
        registrar_projeto,
    )
else:
    from ..autenticacao import Papel, exigir_autenticacao, exigir_papel
    from ..projetos import (
        Projeto,
        ProjetoDuplicado,
        ProjetoInvalido,
        listar_projetos,
        registrar_projeto,
    )

router = APIRouter(tags=["projetos"])


class ProjetoCreate(BaseModel):
    nome: str


class ProjetoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nome: str


@router.post("/projetos", response_model=ProjetoSaida, status_code=201)
def criar_projeto(
    payload: ProjetoCreate,
    _papel: Papel = Depends(exigir_papel(Papel.COORDENACAO)),
) -> Projeto:
    try:
        return registrar_projeto(payload.nome)
    except ProjetoDuplicado as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro
    except ProjetoInvalido as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


@router.get("/projetos", response_model=List[ProjetoSaida])
def listar(_auth: str = Depends(exigir_autenticacao)) -> List[Projeto]:
    return listar_projetos()
