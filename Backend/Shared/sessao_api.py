"""Rotas do login único (T-35 · US-08): ``POST /auth/entrar`` e ``GET /auth/eu``.

O token devolvido por ``/auth/entrar`` vai no cabeçalho ``Authorization: Bearer`` de
qualquer rota da plataforma, da Gestão e do Financeiro: ``Financeiro/autenticacao.py``
aceita o token no lugar do código de acesso e tira dele quem está chamando.

Cada tentativa de entrada vai para ``log_auditoria`` (módulo ``plataforma``): ``login``
quando dá certo e ``login_recusado`` quando não, com o motivo nos detalhes. A resposta
de recusa é sempre a mesma, para não revelar se o e-mail existe.
"""

from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from . import sessao

router = APIRouter(prefix="/auth", tags=["autenticacao"])

LOGIN_INDISPONIVEL = "Login indisponível no servidor."
CREDENCIAIS_INVALIDAS = "E-mail ou senha inválidos."
SESSAO_INVALIDA = "Sessão inválida ou expirada. Entre de novo."

_bearer = HTTPBearer(auto_error=False, description="Token de sessão devolvido por /auth/entrar.")

_REGISTRAR = sa.text(
    """
    INSERT INTO log_auditoria (usuario_id, modulo, acao, alvo_tipo, descricao, detalhes)
    VALUES (:usuario_id, 'plataforma', :acao, 'sessao', :descricao, :detalhes)
    """
).bindparams(sa.bindparam("detalhes", type_=JSONB))


class Entrada(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    senha: str = Field(min_length=1, max_length=200)


class UsuarioDaSessao(BaseModel):
    id: str
    nome: str
    email: Optional[str]
    # Papéis da plataforma e papéis com vínculo ativo em algum programa, sem repetição.
    papeis: List[str]


class Sessao(BaseModel):
    token: str
    expira_em: datetime
    usuario: UsuarioDaSessao


def _usuario(conexao: Connection, usuario_id: str) -> UsuarioDaSessao:
    linha = conexao.execute(
        sa.text("SELECT id, nome, email FROM usuarios WHERE id = :id"), {"id": usuario_id}
    ).one()
    papeis = conexao.execute(
        sa.text(
            """
            SELECT papel_id FROM usuarios_papeis WHERE usuario_id = :id
            UNION
            SELECT papel_id FROM vinculos_equipe
            WHERE usuario_id = :id AND (data_saida IS NULL OR data_saida > CURRENT_DATE)
            ORDER BY 1
            """
        ),
        {"id": usuario_id},
    ).scalars()
    return UsuarioDaSessao(id=linha.id, nome=linha.nome, email=linha.email, papeis=list(papeis))


@router.post("/entrar", response_model=Sessao)
def entrar(dados: Entrada) -> Sessao:
    if not sessao.chave_configurada():
        raise HTTPException(status_code=503, detail=LOGIN_INDISPONIVEL)
    email = dados.email.strip().lower()
    try:
        with sessao.conectar() as conexao:
            conta = conexao.execute(
                sa.text(
                    "SELECT id, ativo, senha_hash FROM usuarios WHERE lower(email) = :email"
                ),
                {"email": email},
            ).first()
            # Confere uma senha mesmo sem conta, para a resposta levar o mesmo tempo.
            senha_confere = sessao.conferir_senha(
                dados.senha, conta.senha_hash if conta and conta.senha_hash else sessao.HASH_FICTICIO
            )
            if conta is None:
                motivo = "email_nao_cadastrado"
            elif not conta.senha_hash:
                motivo = "sem_senha"
            elif not conta.ativo:
                motivo = "usuario_desativado"
            elif not senha_confere:
                motivo = "senha_incorreta"
            else:
                motivo = None

            conexao.execute(
                _REGISTRAR,
                {
                    "usuario_id": conta.id if conta else None,
                    "acao": "login_recusado" if motivo else "login",
                    "descricao": "Entrada recusada" if motivo else "Entrada na plataforma",
                    "detalhes": {"email": email, "motivo": motivo} if motivo else None,
                },
            )
            conexao.commit()
            if motivo:
                raise HTTPException(status_code=401, detail=CREDENCIAIS_INVALIDAS)

            token, expira_em = sessao.criar_token(conta.id)
            return Sessao(token=token, expira_em=expira_em, usuario=_usuario(conexao, conta.id))
    except SQLAlchemyError as erro:
        raise HTTPException(status_code=503, detail=sessao.BANCO_INDISPONIVEL) from erro


@router.get("/eu", response_model=UsuarioDaSessao)
def eu(credenciais: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> UsuarioDaSessao:
    """Quem está logado, para as telas mostrarem o nome e os papéis."""
    token = credenciais.credentials if credenciais else ""
    usuario_id = sessao.usuario_da_sessao(token)
    if usuario_id is None:
        raise HTTPException(
            status_code=401, detail=SESSAO_INVALIDA, headers={"WWW-Authenticate": "Bearer"}
        )
    try:
        with sessao.conectar() as conexao:
            return _usuario(conexao, usuario_id)
    except SQLAlchemyError as erro:
        raise HTTPException(status_code=503, detail=sessao.BANCO_INDISPONIVEL) from erro
