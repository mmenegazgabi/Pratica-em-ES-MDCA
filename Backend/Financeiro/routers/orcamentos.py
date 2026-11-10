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
    import auditoria
    from autenticacao import Identidade, Papel, exigir_acesso_financeiro, exigir_papel, exigir_programa, obter_identidade
    from moeda import formatar_reais
    from orcamento import (
        Orcamento,
        OrcamentoInvalido,
        validar_categorias,
    )
    from persistencia import ORCAMENTOS_EM_MEMORIA, obter_repositorio
    from projetos import buscar_projeto, listar_projetos
else:
    from ..alerta_saldo import (
        NivelAlerta,
        calcular_percentual_consumido,
        calcular_realizado,
        classificar_nivel_alerta,
    )
    from .. import auditoria
    from ..autenticacao import Identidade, Papel, exigir_acesso_financeiro, exigir_papel, exigir_programa, obter_identidade
    from ..moeda import formatar_reais
    from ..orcamento import (
        Orcamento,
        OrcamentoInvalido,
        validar_categorias,
    )
    from ..persistencia import ORCAMENTOS_EM_MEMORIA, obter_repositorio
    from ..projetos import buscar_projeto, listar_projetos

router = APIRouter(tags=["orcamentos"])

# Orçamentos guardados em memória (sem DATABASE_URL). Com banco, eles vêm das
# tabelas orcamentos, orcamento_categorias e lancamentos (persistencia.py).
_orcamentos: List[Orcamento] = ORCAMENTOS_EM_MEMORIA


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
    projeto_nome: Optional[str] = None

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


def autorizar_leitura_projeto(
    projeto_id: str, identidade: Identidade = Depends(exigir_acesso_financeiro)
) -> str:
    # T-33 · US-08: quem só é educador lê apenas os programas em que tem vínculo.
    exigir_programa(identidade, projeto_id)
    return projeto_id


def _buscar_orcamento(repositorio, orcamento_id: str, para_alterar: bool = False) -> Orcamento:
    orcamento = repositorio.buscar_orcamento(orcamento_id, para_alterar=para_alterar)
    if orcamento is None:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")
    return orcamento


def detalhar(orcamento: Orcamento, nomes_dos_projetos: dict) -> OrcamentoDetalhe:
    detalhe = OrcamentoDetalhe.model_validate(orcamento)
    detalhe.projeto_nome = nomes_dos_projetos.get(orcamento.projeto_id)
    return detalhe


def detalhar_um(orcamento: Orcamento, repositorio) -> OrcamentoDetalhe:
    projeto = buscar_projeto(orcamento.projeto_id, repositorio)
    return detalhar(orcamento, {projeto.id: projeto.nome} if projeto else {})


def _resumo_do_orcamento(orcamento: Orcamento) -> dict:
    """O que a auditoria guarda de um orçamento (para comparar antes e depois)."""
    return {
        "projeto_id": orcamento.projeto_id,
        "valor_total": orcamento.valor_total,
        "data_inicio": orcamento.data_inicio.isoformat(),
        "data_fim": orcamento.data_fim.isoformat(),
        "categorias": [
            {"nome": nome, "valor_orcado": orcamento.valores_categorias.get(nome)}
            for nome in orcamento.categorias_despesa
        ],
    }


def _nomes_dos_projetos(repositorio) -> dict:
    return {p.id: p.nome for p in listar_projetos(repositorio)}


@router.get("/orcamentos", response_model=List[OrcamentoDetalhe])
def listar_orcamentos(
    vigentes_em: Optional[date] = Query(
        None,
        description="Se informado, devolve só os orçamentos vigentes nessa data (AAAA-MM-DD).",
    ),
    repositorio=Depends(obter_repositorio),
    identidade: Identidade = Depends(exigir_acesso_financeiro),
) -> List[OrcamentoDetalhe]:
    # T-13 · US-03: o formulário de lançamento precisa listar projetos e
    # categorias para o educador escolher (só os dos programas dele, T-33).
    orcamentos = [
        o
        for o in repositorio.listar_orcamentos()
        if (vigentes_em is None or o.data_inicio <= vigentes_em <= o.data_fim)
        and identidade.ve_programa(o.projeto_id)
    ]
    orcamentos.sort(key=lambda o: (o.projeto_id, o.data_inicio))
    nomes = _nomes_dos_projetos(repositorio)
    return [detalhar(o, nomes) for o in orcamentos]


@router.post("/orcamentos", response_model=Orcamento, status_code=201)
def criar_orcamento(
    payload: OrcamentoCreate,
    repositorio=Depends(obter_repositorio),
    _papel: Papel = Depends(exigir_papel(Papel.COORDENACAO)),
    identidade: Identidade = Depends(obter_identidade),
) -> Orcamento:
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

    if buscar_projeto(payload.projeto_id, repositorio) is None:
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
    repositorio.inserir_orcamento(orcamento)
    projeto = buscar_projeto(orcamento.projeto_id, repositorio)
    auditoria.registrar(
        repositorio, identidade, "criar_orcamento",
        alvo_tipo="orcamento", alvo_id=orcamento.id,
        descricao=auditoria.alvo(projeto.nome if projeto else None, f"valor total {formatar_reais(orcamento.valor_total)}"),
        detalhes=_resumo_do_orcamento(orcamento),
    )
    repositorio.confirmar()
    return orcamento


@router.get("/orcamentos/projeto/{projeto_id}", response_model=OrcamentosPaginados)
def listar_orcamentos_do_projeto(
    projeto_id: str = Depends(autorizar_leitura_projeto),
    pagina: int = Query(1, ge=1),
    tamanho: int = Query(10, ge=1, le=100),
    repositorio=Depends(obter_repositorio),
) -> OrcamentosPaginados:
    do_projeto = sorted(
        (o for o in repositorio.listar_orcamentos() if o.projeto_id == projeto_id),
        key=lambda o: o.data_inicio,
        reverse=True,
    )
    inicio = (pagina - 1) * tamanho
    nomes = _nomes_dos_projetos(repositorio)
    return OrcamentosPaginados(
        itens=[detalhar(o, nomes) for o in do_projeto[inicio : inicio + tamanho]],
        total=len(do_projeto),
        pagina=pagina,
        tamanho=tamanho,
    )


@router.get("/orcamentos/{orcamento_id}", response_model=OrcamentoDetalhe)
def obter_orcamento(
    orcamento_id: str,
    repositorio=Depends(obter_repositorio),
    identidade: Identidade = Depends(exigir_acesso_financeiro),
) -> OrcamentoDetalhe:
    orcamento = _buscar_orcamento(repositorio, orcamento_id)
    exigir_programa(identidade, orcamento.projeto_id)
    return detalhar_um(orcamento, repositorio)


@router.patch("/orcamentos/{orcamento_id}", response_model=OrcamentoDetalhe)
def editar_orcamento(
    orcamento_id: str,
    payload: OrcamentoEdicao,
    _papel: Papel = Depends(exigir_papel(Papel.COORDENACAO)),
    repositorio=Depends(obter_repositorio),
    identidade: Identidade = Depends(obter_identidade),
) -> OrcamentoDetalhe:
    """Coordenação edita valor, vigência e categorias (redesign + US-01)."""
    orcamento = _buscar_orcamento(repositorio, orcamento_id, para_alterar=True)
    antes = _resumo_do_orcamento(orcamento)
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
    repositorio.salvar_orcamento(orcamento)
    projeto = buscar_projeto(orcamento.projeto_id, repositorio)
    auditoria.registrar(
        repositorio, identidade, "editar_orcamento",
        alvo_tipo="orcamento", alvo_id=orcamento.id,
        descricao=auditoria.alvo(projeto.nome if projeto else None, f"valor total {formatar_reais(orcamento.valor_total)}"),
        detalhes={"antes": antes, "depois": _resumo_do_orcamento(orcamento)},
    )
    repositorio.confirmar()
    return detalhar_um(orcamento, repositorio)


# As rotas antigas POST /orcamentos/{id}/lancamentos/{id}/aprovar e
# .../reverter-aprovacao (T-07) foram removidas: não pediam login. A aprovação é
# PATCH /lancamentos/{id}/aprovar, que exige o papel de Coordenação ou Direção.
