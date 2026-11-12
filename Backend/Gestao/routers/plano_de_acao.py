"""Rotas do plano de ação de um programa (US-02): objetivos, ações, metas, registros do
realizado e o painel de acompanhamento.

Este router é incluído pelo de programas (``routers/programas.py``), então não precisa
de linha própria no ``Backend/main.py``.
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Connection

# Acesso por programa (T-87): quem chama vem da sessão do login único (ou do token de
# serviço com X-Usuario-Id, em testes) e os papéis vêm do banco.
from Gestao.acesso import Acesso, exigir_consulta_ao_programa, exigir_gestao_do_programa
from Gestao import plano_de_acao as plano
from Gestao.banco import obter_conexao
from Gestao.programas import ErroDeCadastro

router = APIRouter(prefix="/programas/{programa_id}")

# Os campos de entrada são opcionais de propósito: o que falta volta como 400 com a
# lista dos campos (critério da US-02), não como o 422 genérico da validação.


class ObjetivoEntrada(BaseModel):
    descricao: Optional[str] = Field(default=None, max_length=2000)


class ObjetivoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    descricao: str


class AcaoEntrada(BaseModel):
    objetivo_id: Optional[str] = Field(default=None, max_length=100)
    descricao: Optional[str] = Field(default=None, max_length=2000)
    periodo_inicio: Optional[date] = None
    periodo_fim: Optional[date] = None
    resultado_esperado: Optional[str] = Field(default=None, max_length=2000)
    periodicidade: Optional[str] = Field(default=None, max_length=30)


class AcaoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    objetivo_id: str
    descricao: str
    periodo_inicio: date
    periodo_fim: date
    resultado_esperado: str
    periodicidade: str


class MetaEntrada(BaseModel):
    acao_id: Optional[str] = Field(default=None, max_length=100)
    descricao: Optional[str] = Field(default=None, max_length=2000)
    valor_planejado: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    unidade: Optional[str] = Field(default=None, max_length=100)


class MetaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    acao_id: str
    descricao: str
    valor_planejado: float
    unidade: Optional[str]


class RegistroEntrada(BaseModel):
    data: Optional[date] = None
    valor_realizado: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    observacao: Optional[str] = Field(default=None, max_length=2000)


class RegistroSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    meta_id: str
    data: date
    valor_realizado: float
    observacao: Optional[str]


class MetaNoPainel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    meta_id: str
    descricao: str
    unidade: Optional[str]
    acao_id: str
    acao: str
    objetivo_id: str
    objetivo: str
    planejado: float
    realizado: float
    # Realizado sobre planejado, em %, com uma casa; passa de 100 se a meta for superada.
    percentual: float


class PainelSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    programa_id: str
    metas: List[MetaNoPainel]


def _http(erro: ErroDeCadastro) -> HTTPException:
    return HTTPException(status_code=erro.status, detail=erro.mensagem)


# O acesso vem antes de qualquer consulta: sem token, o banco nem é aberto.


@router.get("/objetivos", response_model=List[ObjetivoSaida])
def listar_objetivos(
    programa_id: str,
    _acesso: Acesso = Depends(exigir_consulta_ao_programa),
    conexao: Connection = Depends(obter_conexao),
) -> List[plano.Objetivo]:
    try:
        return plano.listar_objetivos(conexao, programa_id)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro


@router.post("/objetivos", response_model=ObjetivoSaida, status_code=201)
def cadastrar_objetivo(
    programa_id: str,
    dados: ObjetivoEntrada,
    _acesso: Acesso = Depends(exigir_gestao_do_programa),
    conexao: Connection = Depends(obter_conexao),
) -> plano.Objetivo:
    try:
        objetivo = plano.cadastrar_objetivo(conexao, programa_id, descricao=dados.descricao)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    conexao.commit()
    return objetivo


@router.get("/acoes", response_model=List[AcaoSaida])
def listar_acoes(
    programa_id: str,
    _acesso: Acesso = Depends(exigir_consulta_ao_programa),
    conexao: Connection = Depends(obter_conexao),
) -> List[plano.Acao]:
    try:
        return plano.listar_acoes(conexao, programa_id)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro


@router.post("/acoes", response_model=AcaoSaida, status_code=201)
def cadastrar_acao(
    programa_id: str,
    dados: AcaoEntrada,
    _acesso: Acesso = Depends(exigir_gestao_do_programa),
    conexao: Connection = Depends(obter_conexao),
) -> plano.Acao:
    try:
        acao = plano.cadastrar_acao(conexao, programa_id, **dados.model_dump())
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    conexao.commit()
    return acao


@router.get("/metas", response_model=List[MetaSaida])
def listar_metas(
    programa_id: str,
    _acesso: Acesso = Depends(exigir_consulta_ao_programa),
    conexao: Connection = Depends(obter_conexao),
) -> List[plano.Meta]:
    try:
        return plano.listar_metas(conexao, programa_id)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro


@router.post("/metas", response_model=MetaSaida, status_code=201)
def cadastrar_meta(
    programa_id: str,
    dados: MetaEntrada,
    _acesso: Acesso = Depends(exigir_gestao_do_programa),
    conexao: Connection = Depends(obter_conexao),
) -> plano.Meta:
    try:
        meta = plano.cadastrar_meta(conexao, programa_id, **dados.model_dump())
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    conexao.commit()
    return meta


@router.get("/metas/{meta_id}/registros", response_model=List[RegistroSaida])
def listar_registros(
    programa_id: str,
    meta_id: str,
    _acesso: Acesso = Depends(exigir_consulta_ao_programa),
    conexao: Connection = Depends(obter_conexao),
) -> List[plano.RegistroMeta]:
    try:
        return plano.listar_registros(conexao, programa_id, meta_id)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro


@router.post("/metas/{meta_id}/registros", response_model=RegistroSaida, status_code=201)
def registrar_realizado(
    programa_id: str,
    meta_id: str,
    dados: RegistroEntrada,
    _acesso: Acesso = Depends(exigir_gestao_do_programa),
    conexao: Connection = Depends(obter_conexao),
) -> plano.RegistroMeta:
    try:
        registro = plano.registrar_realizado(conexao, programa_id, meta_id, **dados.model_dump())
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    conexao.commit()
    return registro


@router.get("/painel", response_model=PainelSaida)
def consultar_painel(
    programa_id: str,
    _acesso: Acesso = Depends(exigir_consulta_ao_programa),
    conexao: Connection = Depends(obter_conexao),
) -> plano.Painel:
    """Planejado, realizado (soma dos registros) e percentual de cada meta."""
    try:
        return plano.painel(conexao, programa_id)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
