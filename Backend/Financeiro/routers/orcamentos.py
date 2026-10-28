import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

if __package__ == "routers":
    from alerta_saldo import (
        NivelAlerta,
        calcular_percentual_consumido,
        calcular_realizado,
        classificar_nivel_alerta,
    )
    from autenticacao import Papel, exigir_papel
    from orcamento import (
        AprovacaoInvalida,
        LancamentoNaoEncontrado,
        Orcamento,
        OrcamentoInvalido,
        validar_categorias,
    )
    from projetos import buscar_projeto
else:
    from ..alerta_saldo import (
        NivelAlerta,
        calcular_percentual_consumido,
        calcular_realizado,
        classificar_nivel_alerta,
    )
    from ..autenticacao import Papel, exigir_papel
    from ..orcamento import (
        AprovacaoInvalida,
        LancamentoNaoEncontrado,
        Orcamento,
        OrcamentoInvalido,
        validar_categorias,
    )
    from ..projetos import buscar_projeto

router = APIRouter(tags=["orcamentos"])

_orcamentos: List[Orcamento] = []


class CategoriaEntrada(BaseModel):
    nome: str
    valor_orcado: float = Field(allow_inf_nan=False)


class OrcamentoCreate(BaseModel):
    """Categorias chegam de um dos dois jeitos:

    - ``categorias``: nome e valor orçado de cada uma (US-01);
    - ``categorias_despesa``: só os nomes, sem limite por categoria (formato
      original, mantido para quem já usa).
    """

    projeto_id: str
    valor_total: float = Field(allow_inf_nan=False)
    data_inicio: date
    data_fim: date
    categorias_despesa: Optional[List[str]] = Field(None, min_length=1)
    categorias: Optional[List[CategoriaEntrada]] = Field(None, min_length=1)

    @model_validator(mode="after")
    def _uma_forma_de_categorias(self):
        if (self.categorias is None) == (self.categorias_despesa is None):
            raise ValueError("Informe categorias ou categorias_despesa (só um dos dois).")
        return self


class OrcamentoEdicao(BaseModel):
    """Edição parcial: o que não vier fica como está.

    O formulário do redesign manda tudo, com ``categorias_despesa`` (só
    nomes). ``categorias`` (US-01) traz também o valor orçado de cada uma.
    As duas formas substituem a lista inteira; só uma delas por vez.
    """

    valor_total: Optional[float] = Field(None, gt=0, allow_inf_nan=False)
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None
    categorias_despesa: Optional[List[str]] = None
    categorias: Optional[List[CategoriaEntrada]] = None

    @model_validator(mode="after")
    def _algo_para_editar(self):
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para editar.")
        if self.categorias is not None and self.categorias_despesa is not None:
            raise ValueError("Informe categorias ou categorias_despesa (só um dos dois).")
        return self


class CategoriaDetalhe(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nome: str
    valor_orcado: Optional[float]
    realizado: float

    # Mesmos limiares de 80% e 100% do orçamento inteiro (T-08). Categoria
    # sem valor orçado não tem percentual nem alerta.
    @computed_field
    @property
    def percentual_consumido(self) -> Optional[float]:
        if self.valor_orcado is None:
            return None
        return calcular_percentual_consumido(self.valor_orcado, self.realizado)

    @computed_field
    @property
    def nivel_alerta(self) -> Optional[NivelAlerta]:
        if self.valor_orcado is None:
            return None
        return classificar_nivel_alerta(self.valor_orcado, self.realizado)


class OrcamentoDetalhe(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    projeto_id: str
    valor_total: float = Field(allow_inf_nan=False)
    data_inicio: date
    data_fim: date
    categorias_despesa: List[str]
    saldo: float
    # US-01: limite e gasto de cada categoria, na ordem de categorias_despesa.
    categorias: List[CategoriaDetalhe]

    # Nome vem do cadastro de projetos; None se o projeto não existir mais.
    @computed_field
    @property
    def projeto_nome(self) -> Optional[str]:
        projeto = buscar_projeto(self.projeto_id)
        return projeto.nome if projeto else None

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

    if buscar_projeto(payload.projeto_id) is None:
        raise HTTPException(
            status_code=400,
            detail="Projeto não encontrado. Cadastre o projeto antes de criar o orçamento.",
        )

    if payload.categorias is not None:
        nomes = [c.nome.strip() for c in payload.categorias]
        # Nome repetido é barrado em validar_categorias, que olha a lista.
        valores = {c.nome.strip(): c.valor_orcado for c in payload.categorias}
    else:
        nomes = payload.categorias_despesa
        valores = {}
    try:
        validar_categorias(payload.valor_total, nomes, valores)
    except OrcamentoInvalido as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro

    orcamento = Orcamento(
        id=str(uuid.uuid4()),
        projeto_id=payload.projeto_id,
        valor_total=payload.valor_total,
        data_inicio=payload.data_inicio,
        data_fim=payload.data_fim,
        categorias_despesa=nomes,
        valores_categorias=valores,
    )
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
    """Coordenação edita valor, vigência e categorias (redesign + US-01)."""
    orcamento = _buscar_orcamento(orcamento_id)
    categorias = (
        None
        if payload.categorias is None
        else [(c.nome.strip(), c.valor_orcado) for c in payload.categorias]
    )
    try:
        orcamento.editar(
            valor_total=payload.valor_total,
            data_inicio=payload.data_inicio,
            data_fim=payload.data_fim,
            categorias_despesa=payload.categorias_despesa,
            categorias=categorias,
        )
    except OrcamentoInvalido as erro:
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
