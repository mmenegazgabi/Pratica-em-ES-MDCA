import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, computed_field

if __package__ == "routers":

    from autenticacao import Papel, exigir_papel
    from alerta_saldo import (
        NivelAlerta,
        calcular_percentual_consumido,
        calcular_realizado,
        classificar_nivel_alerta,
    )
    from orcamento import (
        AprovacaoInvalida,
        LancamentoInvalido,
        LancamentoNaoEncontrado,
        Orcamento,
    )
else:
    from ..autenticacao import Papel, exigir_papel
    from ..alerta_saldo import (
        NivelAlerta,
        calcular_percentual_consumido,
        calcular_realizado,
        classificar_nivel_alerta,
    )
    from ..orcamento import (
        AprovacaoInvalida,
        LancamentoInvalido,
        LancamentoNaoEncontrado,
        Orcamento,
    )

router = APIRouter(tags=["orcamentos"])

_orcamentos: List[Orcamento] = []


class OrcamentoCreate(BaseModel):
    projeto_id: str
    valor_total: float
    data_inicio: date
    data_fim: date
    categorias_despesa: List[str] = Field(min_length=1)


class OrcamentoEdicao(BaseModel):
    valor_total: float
    data_inicio: date
    data_fim: date
    categorias_despesa: List[str]


class OrcamentoDetalhe(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    projeto_id: str
    valor_total: float
    data_inicio: date
    data_fim: date
    categorias_despesa: List[str]
    saldo: float

    # T-08 · US-02: indicador de consumo com alerta em 80% e 100%.
    # Calculados a partir de valor_total e saldo para que as telas não
    # precisem repetir a regra dos limiares.
    @computed_field
    @property
    def realizado(self) -> float:
        return calcular_realizado(self.valor_total, self.saldo)

    @computed_field
    @property
    def percentual_consumido(self) -> Optional[float]:
        return calcular_percentual_consumido(self.valor_total, self.realizado)

    @computed_field
    @property
    def nivel_alerta(self) -> NivelAlerta:
        return classificar_nivel_alerta(self.valor_total, self.realizado)


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


@router.get("/orcamentos", response_model=List[OrcamentoDetalhe])
def listar_orcamentos(
    vigentes_em: Optional[date] = Query(
        None,
        description="Se informado, devolve só os orçamentos vigentes nessa data (AAAA-MM-DD).",
    ),
) -> List[OrcamentoDetalhe]:
    # T-13 · US-03: o formulário de lançamento precisa listar projetos e
    # categorias para o educador escolher.
    orcamentos = [
        o
        for o in _orcamentos
        if vigentes_em is None or o.data_inicio <= vigentes_em <= o.data_fim
    ]
    orcamentos.sort(key=lambda o: (o.projeto_id, o.data_inicio))
    return [OrcamentoDetalhe.model_validate(o) for o in orcamentos]


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


@router.patch("/orcamentos/{orcamento_id}", response_model=OrcamentoDetalhe)
def editar_orcamento(
    orcamento_id: str,
    payload: OrcamentoEdicao,
    _papel: Papel = Depends(exigir_papel(Papel.COORDENACAO)),
) -> Orcamento:
    orcamento = _buscar_orcamento(orcamento_id)
    try:
        orcamento.editar(**payload.model_dump())
    except LancamentoInvalido as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    return orcamento


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
