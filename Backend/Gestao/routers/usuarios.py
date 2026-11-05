from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.engine import Connection

from Financeiro.autenticacao import exigir_usuario
from Gestao import usuarios
from Gestao.acesso import exigir_acesso_aos_usuarios
from Gestao.banco import obter_conexao

router = APIRouter(prefix="/gestao", tags=["gestao"])


class PapelSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nome: str


class VinculoAtivoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    programa_id: str
    programa: str
    papel_id: str
    papel: str


class UsuarioSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nome: str
    email: Optional[str]
    ativo: bool
    # Papéis da plataforma (direção, administração…), fora de qualquer programa.
    papeis: List[PapelSaida]
    # Só os vínculos ativos; o histórico de cada programa fica em …/equipe.
    vinculos: List[VinculoAtivoSaida]


# Como nas rotas de programa, o acesso vem antes da conexão da rota: a dependência
# já abre a conexão (a mesma, reaproveitada) e responde 403 antes de qualquer consulta.


@router.get("/usuarios", response_model=List[UsuarioSaida])
def listar_usuarios(
    _usuario: str = Depends(exigir_acesso_aos_usuarios),
    conexao: Connection = Depends(obter_conexao),
) -> List[usuarios.Usuario]:
    """Usuários da plataforma com papéis e vínculos ativos (administração e coordenação)."""
    return usuarios.listar_usuarios(conexao)


@router.get("/papeis", response_model=List[PapelSaida])
def listar_papeis(
    _usuario: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> List[usuarios.Papel]:
    """Catálogo de papéis (sem dado pessoal): qualquer usuário identificado consulta."""
    return usuarios.listar_papeis(conexao)
