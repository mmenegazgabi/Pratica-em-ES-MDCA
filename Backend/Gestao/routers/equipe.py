from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Connection

from Gestao import equipe
from Gestao.acesso import Acesso, exigir_consulta_ao_programa, exigir_gestao_do_programa
from Gestao.banco import obter_conexao

router = APIRouter(prefix="/gestao/programas/{programa_id}", tags=["gestao"])


class VinculoEntrada(BaseModel):
    usuario_id: str = Field(min_length=1, max_length=100)
    papel_id: str = Field(min_length=1, max_length=100)
    data_entrada: date


class DesligamentoEntrada(BaseModel):
    data_saida: date


class VinculoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    usuario_id: str
    nome: str
    papel_id: str
    papel: str
    data_entrada: date
    data_saida: Optional[date]
    # Falso a partir da data de saída: a pessoa perde o acesso ao programa.
    ativo: bool


class EspacoEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    capacidade: Optional[int] = Field(default=None, gt=0)


class EspacoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nome: str
    capacidade: Optional[int]


def _http(erro: equipe.ErroDeEquipe) -> HTTPException:
    return HTTPException(status_code=erro.status, detail=erro.mensagem)


# O acesso vem antes da conexão da rota: a dependência de acesso já abre a conexão
# (a mesma, reaproveitada pelo FastAPI) e responde 404/403 antes de qualquer consulta.


@router.get("/equipe", response_model=List[VinculoSaida])
def listar_equipe(
    incluir_desligados: bool = False,
    acesso: Acesso = Depends(exigir_consulta_ao_programa),
    conexao: Connection = Depends(obter_conexao),
) -> List[equipe.Vinculo]:
    """Vínculos ativos do programa; com ``incluir_desligados``, também o histórico."""
    return equipe.listar_equipe(conexao, acesso.programa_id, incluir_desligados=incluir_desligados)


@router.post("/equipe", response_model=VinculoSaida, status_code=201)
def vincular(
    dados: VinculoEntrada,
    acesso: Acesso = Depends(exigir_gestao_do_programa),
    conexao: Connection = Depends(obter_conexao),
) -> equipe.Vinculo:
    try:
        vinculo = equipe.vincular(
            conexao,
            acesso.programa_id,
            usuario_id=dados.usuario_id.strip(),
            papel_id=dados.papel_id.strip(),
            data_entrada=dados.data_entrada,
        )
    except equipe.ErroDeEquipe as erro:
        raise _http(erro) from erro
    conexao.commit()
    return vinculo


@router.patch("/equipe/{vinculo_id}/desligamento", response_model=VinculoSaida)
def registrar_desligamento(
    vinculo_id: str,
    dados: DesligamentoEntrada,
    acesso: Acesso = Depends(exigir_gestao_do_programa),
    conexao: Connection = Depends(obter_conexao),
) -> equipe.Vinculo:
    try:
        vinculo = equipe.registrar_desligamento(
            conexao, acesso.programa_id, vinculo_id, data_saida=dados.data_saida
        )
    except equipe.ErroDeEquipe as erro:
        raise _http(erro) from erro
    conexao.commit()
    return vinculo


@router.get("/espacos", response_model=List[EspacoSaida])
def listar_espacos(
    acesso: Acesso = Depends(exigir_consulta_ao_programa),
    conexao: Connection = Depends(obter_conexao),
) -> List[equipe.Espaco]:
    return equipe.listar_espacos(conexao, acesso.programa_id)


@router.post("/espacos", response_model=EspacoSaida, status_code=201)
def criar_espaco(
    dados: EspacoEntrada,
    acesso: Acesso = Depends(exigir_gestao_do_programa),
    conexao: Connection = Depends(obter_conexao),
) -> equipe.Espaco:
    try:
        espaco = equipe.criar_espaco(
            conexao, acesso.programa_id, nome=dados.nome, capacidade=dados.capacidade
        )
    except equipe.ErroDeEquipe as erro:
        raise _http(erro) from erro
    conexao.commit()
    return espaco
