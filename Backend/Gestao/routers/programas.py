from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.engine import Connection

# Token de serviço provisório, o mesmo das rotas do Financeiro, até existirem o
# login único (T-35) e o RBAC (T-33).
from Financeiro.autenticacao import exigir_autenticacao
from Gestao.banco import obter_conexao
from Gestao.programas import Programa, listar_programas

router = APIRouter(prefix="/gestao", tags=["gestao"])


class ProgramaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nome: str


@router.get("/programas", response_model=List[ProgramaSaida])
def listar(
    # A autenticação vem antes da conexão: sem token, o banco nem é aberto.
    _auth: str = Depends(exigir_autenticacao),
    conexao: Connection = Depends(obter_conexao),
) -> List[Programa]:
    return listar_programas(conexao)
