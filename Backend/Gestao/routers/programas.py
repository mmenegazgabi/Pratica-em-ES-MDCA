from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.engine import Connection

# Mesma autenticação das rotas do Financeiro: sessão do login único (T-35) ou
# token de serviço, até existir o RBAC (T-33).
from Acesso.identidade import Identidade
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
    _auth: Identidade = Depends(exigir_autenticacao),
    conexao: Connection = Depends(obter_conexao),
) -> List[Programa]:
    return listar_programas(conexao)
