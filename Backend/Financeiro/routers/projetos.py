from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

if __package__ == "routers":
    from autenticacao import Papel, exigir_autenticacao, exigir_papel
    from projetos import (
        Projeto,
        ProjetoDuplicado,
        ProjetoInvalido,
        StatusProjeto,
        alterar_status,
        listar_projetos,
        registrar_projeto,
    )
    from persistencia import obter_repositorio
else:
    from ..autenticacao import Papel, exigir_autenticacao, exigir_papel
    from ..projetos import (
        Projeto,
        ProjetoDuplicado,
        ProjetoInvalido,
        StatusProjeto,
        alterar_status,
        listar_projetos,
        registrar_projeto,
    )
    from ..persistencia import obter_repositorio

router = APIRouter(tags=["projetos"])


class ProjetoCreate(BaseModel):
    nome: str


class ProjetoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nome: str
    status: StatusProjeto


class StatusEdicao(BaseModel):
    status: StatusProjeto


@router.post("/projetos", response_model=ProjetoSaida, status_code=201)
def criar_projeto(
    payload: ProjetoCreate,
    _papel: Papel = Depends(exigir_papel(Papel.COORDENACAO)),
    repositorio=Depends(obter_repositorio),
) -> Projeto:
    try:
        projeto = registrar_projeto(payload.nome, repositorio)
    except ProjetoDuplicado as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro
    except ProjetoInvalido as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    repositorio.confirmar()
    return projeto


@router.get("/projetos", response_model=List[ProjetoSaida])
def listar(
    _auth: str = Depends(exigir_autenticacao), repositorio=Depends(obter_repositorio)
) -> List[Projeto]:
    # Com banco, inclui os programas cadastrados pela Gestão (mesma tabela projetos).
    return listar_projetos(repositorio)


@router.patch("/projetos/{projeto_id}/status", response_model=ProjetoSaida)
def editar_status(
    projeto_id: str,
    payload: StatusEdicao,
    _papel: Papel = Depends(exigir_papel(Papel.COORDENACAO, Papel.DIRECAO)),
    repositorio=Depends(obter_repositorio),
) -> Projeto:
    # T-29 · US-07: encerrar (ou reabrir) o projeto para o filtro do dashboard.
    projeto = alterar_status(projeto_id, payload.status, repositorio)
    if projeto is None:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    repositorio.confirmar()
    return projeto
