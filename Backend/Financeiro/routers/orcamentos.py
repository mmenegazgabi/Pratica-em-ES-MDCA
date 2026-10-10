import uuid
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

if __package__ == "routers":
    from orcamento import AprovacaoInvalida, LancamentoNaoEncontrado, Orcamento
else:
    from ..orcamento import AprovacaoInvalida, LancamentoNaoEncontrado, Orcamento

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


class OrcamentosPaginados(BaseModel):
    itens: List[OrcamentoDetalhe]
    total: int
    pagina: int
    tamanho: int


def autorizar_leitura_projeto(projeto_id: str) -> str:
    # Ponto de integração com o RBAC da US-08: quando implementado,
    # deve levantar 403 se o usuário não puder ver o projeto.
    return projeto_id


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


@router.get("/orcamentos/projeto/{projeto_id}", response_model=OrcamentosPaginados)
def listar_orcamentos_do_projeto(
    projeto_id: str = Depends(autorizar_leitura_projeto),
    pagina: int = Query(1, ge=1),
    tamanho: int = Query(10, ge=1, le=100),
) -> OrcamentosPaginados:
    do_projeto = sorted(
        (o for o in _orcamentos if o.projeto_id == projeto_id),
        key=lambda o: o.data_inicio,
        reverse=True,
    )
    inicio = (pagina - 1) * tamanho
    return OrcamentosPaginados(
        itens=[
            OrcamentoDetalhe.model_validate(o)
            for o in do_projeto[inicio : inicio + tamanho]
        ],
        total=len(do_projeto),
        pagina=pagina,
        tamanho=tamanho,
    )


@router.get("/orcamentos/{orcamento_id}", response_model=OrcamentoDetalhe)
def obter_orcamento(orcamento_id: str) -> Orcamento:
    return _buscar_orcamento(orcamento_id)


@router.post(
    "/orcamentos/{orcamento_id}/lancamentos/{lancamento_id}/aprovar",
    response_model=OrcamentoDetalhe,
)
def aprovar_lancamento(orcamento_id: str, lancamento_id: str) -> Orcamento:
    orcamento = _buscar_orcamento(orcamento_id)
    try:
        orcamento.aprovar_lancamento(lancamento_id)
    except LancamentoNaoEncontrado as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    except AprovacaoInvalida as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro
    return orcamento


@router.post(
    "/orcamentos/{orcamento_id}/lancamentos/{lancamento_id}/reverter-aprovacao",
    response_model=OrcamentoDetalhe,
)
def reverter_aprovacao(orcamento_id: str, lancamento_id: str) -> Orcamento:
    orcamento = _buscar_orcamento(orcamento_id)
    try:
        orcamento.reverter_aprovacao(lancamento_id)
    except LancamentoNaoEncontrado as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    except AprovacaoInvalida as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro
    return orcamento
