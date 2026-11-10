from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

if __package__ == "routers":
    from autenticacao import Papel, exigir_papel
    from dashboard import ResumoProjeto, resumo_por_projeto
    from persistencia import obter_repositorio
    from projetos import StatusProjeto, listar_projetos
else:
    from ..autenticacao import Papel, exigir_papel
    from ..dashboard import ResumoProjeto, resumo_por_projeto
    from ..persistencia import obter_repositorio
    from ..projetos import StatusProjeto, listar_projetos

router = APIRouter(tags=["dashboard"])


class ResumoProjetoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    projeto_id: str
    nome: str
    status: StatusProjeto
    orcado: float
    realizado: float
    saldo: float


@router.get("/dashboard/projetos", response_model=List[ResumoProjetoSaida])
def resumo_dos_projetos(
    data_inicio: Optional[date] = Query(None, description="Início do período (AAAA-MM-DD)."),
    data_fim: Optional[date] = Query(None, description="Fim do período (AAAA-MM-DD)."),
    status: Optional[StatusProjeto] = Query(None, description="ativo ou encerrado."),
    _papel: Papel = Depends(exigir_papel(Papel.DIRECAO)),
    repositorio=Depends(obter_repositorio),
) -> List[ResumoProjeto]:
    # T-29 · US-07: orçado, realizado e saldo de todos os projetos numa
    # única resposta, para o dashboard executivo da Diretoria.
    if data_inicio and data_fim and data_fim < data_inicio:
        raise HTTPException(
            status_code=422,
            detail="data_fim não pode ser anterior a data_inicio",
        )
    return resumo_por_projeto(
        listar_projetos(repositorio),
        repositorio.listar_orcamentos(),
        data_inicio,
        data_fim,
        status,
    )
