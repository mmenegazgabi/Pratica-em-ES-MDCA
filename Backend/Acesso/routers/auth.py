"""Rotas de login único (T-35): entrar, primeiro acesso, quem sou eu e sair."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from Acesso import auditoria, codigos, senhas, sessoes, usuarios
from Gestao.banco import obter_conexao

router = APIRouter(prefix="/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)

FALHAS_PERMITIDAS = 5
JANELA_DE_FALHAS = timedelta(minutes=15)

CREDENCIAIS_INVALIDAS = "E-mail ou senha incorretos."
CODIGO_INVALIDO = "Código inválido ou vencido."
MUITAS_TENTATIVAS = "Muitas tentativas. Tente de novo em alguns minutos."
SESSAO_INVALIDA = "Sessão inválida ou vencida."


class EntrarEntrada(BaseModel):
    email: str = Field(max_length=320)
    senha: str = Field(max_length=1000)
    lembrar: bool = False


class PrimeiroAcessoEntrada(BaseModel):
    email: str = Field(max_length=320)
    codigo: str = Field(max_length=64)
    senha: str = Field(max_length=1000)
    lembrar: bool = False


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _resposta(conexao: Connection, usuario_id: str, token: str, expira_em: datetime) -> dict:
    return {
        "token": token,
        "expira_em": expira_em.isoformat(),
        "usuario": usuarios.dados_publicos(conexao, usuario_id),
    }


def _falhas_recentes(conexao: Connection, email: str, agora: datetime) -> int:
    return conexao.execute(
        sa.text(
            "SELECT count(*) FROM log_auditoria WHERE modulo = :modulo AND acao = 'login_falhou' "
            "AND alvo_id = :email AND ocorrido_em > :desde"
        ),
        {"modulo": auditoria.MODULO, "email": email, "desde": agora - JANELA_DE_FALHAS},
    ).scalar()


@router.post("/entrar")
def entrar(corpo: EntrarEntrada, conexao: Connection = Depends(obter_conexao)) -> dict:
    agora = _agora()
    email = usuarios.normalizar_email(corpo.email)
    if _falhas_recentes(conexao, email, agora) >= FALHAS_PERMITIDAS:
        raise HTTPException(status_code=429, detail=MUITAS_TENTATIVAS)

    usuario = usuarios.por_email(conexao, email)
    # Confere sempre, mesmo sem usuário, para a resposta demorar parecido.
    confere = senhas.conferir(corpo.senha, usuario.senha_hash if usuario else None)
    if usuario is None or not usuario.ativo or not confere:
        auditoria.registrar(
            conexao, usuario_id=None, acao="login_falhou", alvo_tipo="usuario", alvo_id=email
        )
        conexao.commit()
        raise HTTPException(status_code=401, detail=CREDENCIAIS_INVALIDAS)

    token, expira_em = sessoes.criar(conexao, usuario.id, corpo.lembrar, agora)
    auditoria.registrar(conexao, usuario_id=usuario.id, acao="login")
    resposta = _resposta(conexao, usuario.id, token, expira_em)
    conexao.commit()
    return resposta


@router.post("/primeiro-acesso")
def primeiro_acesso(corpo: PrimeiroAcessoEntrada, conexao: Connection = Depends(obter_conexao)) -> dict:
    agora = _agora()
    erro = senhas.validar(corpo.senha)
    if erro:
        raise HTTPException(status_code=400, detail=erro)

    usuario = usuarios.por_email(conexao, corpo.email)
    if usuario is None or not usuario.ativo or not codigos.consumir(conexao, usuario.id, corpo.codigo, agora):
        raise HTTPException(status_code=400, detail=CODIGO_INVALIDO)

    conexao.execute(
        sa.text("UPDATE usuarios SET senha_hash = :h WHERE id = :id"),
        {"h": senhas.gerar_hash(corpo.senha), "id": usuario.id},
    )
    sessoes.encerrar_todas(conexao, usuario.id)
    token, expira_em = sessoes.criar(conexao, usuario.id, corpo.lembrar, agora)
    auditoria.registrar(conexao, usuario_id=usuario.id, acao="primeiro_acesso")
    resposta = _resposta(conexao, usuario.id, token, expira_em)
    conexao.commit()
    return resposta


def _token(credenciais: Optional[HTTPAuthorizationCredentials]) -> str:
    return credenciais.credentials if credenciais else ""


@router.get("/eu")
def eu(
    credenciais: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    conexao: Connection = Depends(obter_conexao),
) -> dict:
    token = _token(credenciais)
    usuario_id = sessoes.usuario_da_sessao(conexao, token, _agora()) if token else None
    if usuario_id is None:
        raise HTTPException(
            status_code=401, detail=SESSAO_INVALIDA, headers={"WWW-Authenticate": "Bearer"}
        )
    return usuarios.dados_publicos(conexao, usuario_id)


@router.post("/sair", status_code=204)
def sair(
    credenciais: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    conexao: Connection = Depends(obter_conexao),
) -> Response:
    token = _token(credenciais)
    usuario_id = sessoes.usuario_da_sessao(conexao, token, _agora()) if token else None
    if usuario_id is not None:
        sessoes.encerrar(conexao, token)
        auditoria.registrar(conexao, usuario_id=usuario_id, acao="logout")
        conexao.commit()
    return Response(status_code=204)
