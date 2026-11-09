from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Connection

# Token de serviço provisório, o mesmo das rotas do Financeiro, até existirem o
# login único (T-35) e o RBAC (T-33).
from Financeiro.autenticacao import exigir_autenticacao
from Gestao import programas
from Gestao.banco import obter_conexao
from Gestao.programas import ErroDeCadastro, Programa
from Gestao.routers.plano_de_acao import router as plano_de_acao_router

router = APIRouter(prefix="/gestao", tags=["gestao"])

# Os campos de entrada são opcionais de propósito: o que falta volta como 400 com a
# lista dos campos (critério da US-02), não como o 422 genérico da validação.


class ProgramaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nome: str
    # Vazios nos programas antigos, criados só com nome.
    identificador: Optional[str] = None
    vigencia_inicio: Optional[date] = None
    vigencia_fim: Optional[date] = None


class ProgramaEntrada(BaseModel):
    nome: Optional[str] = Field(default=None, max_length=200)
    # Código compartilhado com o Financeiro (ex.: "SCFV"); único, sem diferenciar maiúsculas.
    identificador: Optional[str] = Field(default=None, max_length=50)
    publico: Optional[str] = Field(default=None, max_length=500)
    responsavel: Optional[str] = Field(default=None, max_length=200)
    vigencia_inicio: Optional[date] = None
    vigencia_fim: Optional[date] = None
    descricao: Optional[str] = Field(default=None, max_length=2000)


class ProgramaDetalhadoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nome: str
    # Nulos só em programas antigos, criados antes do cadastro completo (T-45).
    identificador: Optional[str]
    publico: Optional[str]
    responsavel: Optional[str]
    vigencia_inicio: Optional[date]
    vigencia_fim: Optional[date]
    descricao: Optional[str]
    status: str


class ConvenioEntrada(BaseModel):
    nome: Optional[str] = Field(default=None, max_length=300)
    concedente: Optional[str] = Field(default=None, max_length=300)
    vigencia_inicio: Optional[date] = None
    vigencia_fim: Optional[date] = None


class ConvenioSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nome: str
    concedente: Optional[str]
    vigencia_inicio: Optional[date]
    vigencia_fim: Optional[date]


class VagasEntrada(BaseModel):
    descricao: Optional[str] = Field(default=None, max_length=300)
    quantidade: Optional[int] = None


class VagasSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    descricao: str
    quantidade: int


def _http(erro: ErroDeCadastro) -> HTTPException:
    return HTTPException(status_code=erro.status, detail=erro.mensagem)


# A autenticação vem antes da conexão: sem token, o banco nem é aberto.


@router.get("/programas", response_model=List[ProgramaSaida])
def listar(
    _auth: str = Depends(exigir_autenticacao),
    conexao: Connection = Depends(obter_conexao),
) -> List[Programa]:
    return programas.listar_programas(conexao)


@router.post("/programas", response_model=ProgramaDetalhadoSaida, status_code=201)
def cadastrar(
    dados: ProgramaEntrada,
    _auth: str = Depends(exigir_autenticacao),
    conexao: Connection = Depends(obter_conexao),
) -> programas.ProgramaDetalhado:
    try:
        programa = programas.cadastrar_programa(conexao, **dados.model_dump())
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    conexao.commit()
    return programa


@router.patch("/programas/{programa_id}", response_model=ProgramaDetalhadoSaida)
def editar(
    programa_id: str,
    dados: ProgramaEntrada,
    _auth: str = Depends(exigir_autenticacao),
    conexao: Connection = Depends(obter_conexao),
) -> programas.ProgramaDetalhado:
    """Altera só os campos enviados; o programa resultante segue as regras do cadastro."""
    try:
        programa = programas.editar_programa(conexao, programa_id, dados.model_dump(exclude_unset=True))
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    conexao.commit()
    return programa


@router.get("/programas/{programa_id}", response_model=ProgramaDetalhadoSaida)
def consultar(
    programa_id: str,
    _auth: str = Depends(exigir_autenticacao),
    conexao: Connection = Depends(obter_conexao),
) -> programas.ProgramaDetalhado:
    try:
        return programas.buscar_programa(conexao, programa_id)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro


@router.get("/programas/{programa_id}/convenios", response_model=List[ConvenioSaida])
def listar_convenios(
    programa_id: str,
    _auth: str = Depends(exigir_autenticacao),
    conexao: Connection = Depends(obter_conexao),
) -> List[programas.Convenio]:
    try:
        return programas.listar_convenios(conexao, programa_id)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro


@router.post("/programas/{programa_id}/convenios", response_model=ConvenioSaida, status_code=201)
def cadastrar_convenio(
    programa_id: str,
    dados: ConvenioEntrada,
    _auth: str = Depends(exigir_autenticacao),
    conexao: Connection = Depends(obter_conexao),
) -> programas.Convenio:
    try:
        convenio = programas.cadastrar_convenio(conexao, programa_id, **dados.model_dump())
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    conexao.commit()
    return convenio


@router.get("/programas/{programa_id}/vagas", response_model=List[VagasSaida])
def listar_vagas(
    programa_id: str,
    _auth: str = Depends(exigir_autenticacao),
    conexao: Connection = Depends(obter_conexao),
) -> List[programas.Vaga]:
    try:
        return programas.listar_vagas(conexao, programa_id)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro


@router.post("/programas/{programa_id}/vagas", response_model=VagasSaida, status_code=201)
def cadastrar_vagas(
    programa_id: str,
    dados: VagasEntrada,
    _auth: str = Depends(exigir_autenticacao),
    conexao: Connection = Depends(obter_conexao),
) -> programas.Vaga:
    try:
        vaga = programas.cadastrar_vagas(conexao, programa_id, **dados.model_dump())
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    conexao.commit()
    return vaga


# Objetivos, ações, metas, registros e painel: /gestao/programas/{programa_id}/...
router.include_router(plano_de_acao_router)
