"""Rotas de administração de pessoas e papéis (T-35): só a administração, em sessão."""

from datetime import datetime, timezone
from typing import List, Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from Acesso import admin, auditoria, codigos, sessoes, usuarios
from Acesso.identidade import Identidade
from Acesso.routers.banco import RotaComBanco
from Financeiro.autenticacao import exigir_autenticacao
from Gestao.banco import obter_conexao

router = APIRouter(prefix="/admin/usuarios", tags=["admin"], route_class=RotaComBanco)

PAPEL_ADMINISTRACAO = "administracao"

SEM_ACESSO = "Seu perfil não tem acesso à administração de pessoas."
NAO_ENCONTRADA = "Pessoa não encontrada."
EMAIL_REPETIDO = "Já existe uma pessoa com este e-mail."
SEM_PAPEL = "Escolha ao menos um papel."
NOME_VAZIO = "Informe o nome."
EMAIL_INVALIDO = "Informe um e-mail válido."
NAO_DESATIVAR_A_SI = "Você não pode desativar a própria conta."
NAO_TIRAR_ADMINISTRACAO = "Você não pode tirar o próprio papel de administração."
REATIVAR_ANTES = "Reative a pessoa antes de gerar um código."


class NovaPessoa(BaseModel):
    nome: str = Field(max_length=200)
    email: str = Field(max_length=320)
    papeis: List[str]


class EdicaoPessoa(BaseModel):
    nome: Optional[str] = Field(default=None, max_length=200)
    # Quem já existia antes do login pode não ter e-mail; sem ele, não entra.
    email: Optional[str] = Field(default=None, max_length=320)
    papeis: Optional[List[str]] = None
    ativo: Optional[bool] = None


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def exigir_administracao(
    requisicao: Request,
    identidade: Identidade = Depends(exigir_autenticacao),
    conexao: Connection = Depends(obter_conexao),
) -> str:
    """Id de quem administra; modo serviço e sessões sem o papel levam 403 auditado."""
    if not identidade.servico and PAPEL_ADMINISTRACAO in identidade.papeis:
        return identidade.usuario_id
    auditoria.registrar(
        conexao,
        usuario_id=identidade.usuario_id,
        acao="acesso_negado",
        alvo_tipo="usuarios",
        descricao="Tentativa de administrar pessoas sem permissão",
        detalhes={"metodo": requisicao.method, "rota": requisicao.url.path},
    )
    # O 403 desfaria a transação; o registro da tentativa precisa ficar.
    conexao.commit()
    raise HTTPException(status_code=403, detail=SEM_ACESSO)


def _validar_email(email: str) -> str:
    email = usuarios.normalizar_email(email)
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=400, detail=EMAIL_INVALIDO)
    return email


def _validar_papeis(conexao: Connection, papeis: List[str]) -> List[str]:
    papeis = sorted(set(papeis))
    if not papeis:
        raise HTTPException(status_code=400, detail=SEM_PAPEL)
    desconhecidos = admin.papeis_desconhecidos(conexao, papeis)
    if desconhecidos:
        raise HTTPException(status_code=400, detail=f"Papel desconhecido: {', '.join(desconhecidos)}.")
    return papeis


@router.get("")
def listar(_: str = Depends(exigir_administracao), conexao: Connection = Depends(obter_conexao)) -> list:
    return admin.listar(conexao)


@router.post("", status_code=201)
def criar(
    corpo: NovaPessoa,
    quem: str = Depends(exigir_administracao),
    conexao: Connection = Depends(obter_conexao),
) -> dict:
    nome = corpo.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail=NOME_VAZIO)
    email = _validar_email(corpo.email)
    papeis = _validar_papeis(conexao, corpo.papeis)
    if usuarios.por_email(conexao, email) is not None:
        raise HTTPException(status_code=409, detail=EMAIL_REPETIDO)

    agora = _agora()
    usuario_id = usuarios.novo_id(conexao, nome)
    conexao.execute(
        sa.text("INSERT INTO usuarios (id, nome, email, ativo) VALUES (:id, :nome, :email, true)"),
        {"id": usuario_id, "nome": nome, "email": email},
    )
    admin.definir_papeis(conexao, usuario_id, papeis)
    codigo, expira_em = codigos.emitir(conexao, usuario_id, quem, agora)
    auditoria.registrar(
        conexao,
        usuario_id=quem,
        acao="usuario_criado",
        alvo_tipo="usuarios",
        alvo_id=usuario_id,
        detalhes={"email": email, "papeis": papeis},
    )
    resposta = {
        "usuario": admin.obter(conexao, usuario_id),
        "codigo": codigo,
        "codigo_expira_em": expira_em.isoformat(),
    }
    conexao.commit()
    return resposta


@router.patch("/{usuario_id}")
def editar(
    usuario_id: str,
    corpo: EdicaoPessoa,
    quem: str = Depends(exigir_administracao),
    conexao: Connection = Depends(obter_conexao),
) -> dict:
    atual = admin.obter(conexao, usuario_id)
    if atual is None:
        raise HTTPException(status_code=404, detail=NAO_ENCONTRADA)

    if corpo.ativo is False and usuario_id == quem:
        raise HTTPException(status_code=400, detail=NAO_DESATIVAR_A_SI)
    papeis = None
    if corpo.papeis is not None:
        papeis = _validar_papeis(conexao, corpo.papeis)
        if usuario_id == quem and PAPEL_ADMINISTRACAO not in papeis:
            raise HTTPException(status_code=400, detail=NAO_TIRAR_ADMINISTRACAO)
    nome = None
    if corpo.nome is not None:
        nome = corpo.nome.strip()
        if not nome:
            raise HTTPException(status_code=400, detail=NOME_VAZIO)
    email = None
    if corpo.email is not None:
        email = _validar_email(corpo.email)
        if email == (atual["email"] or "").lower():
            email = None
        else:
            outra = usuarios.por_email(conexao, email)
            if outra is not None and outra.id != usuario_id:
                raise HTTPException(status_code=409, detail=EMAIL_REPETIDO)

    alteracoes = {}
    if nome is not None and nome != atual["nome"]:
        conexao.execute(sa.text("UPDATE usuarios SET nome = :n WHERE id = :id"), {"n": nome, "id": usuario_id})
        alteracoes["nome"] = nome
    if email is not None:
        conexao.execute(sa.text("UPDATE usuarios SET email = :e WHERE id = :id"), {"e": email, "id": usuario_id})
        alteracoes["email"] = email
    ids_atuais = sorted(p["id"] for p in atual["papeis"])
    if papeis is not None and papeis != ids_atuais:
        admin.definir_papeis(conexao, usuario_id, papeis)
        alteracoes["papeis"] = papeis
    if alteracoes:
        auditoria.registrar(
            conexao,
            usuario_id=quem,
            acao="usuario_editado",
            alvo_tipo="usuarios",
            alvo_id=usuario_id,
            detalhes=alteracoes,
        )
    if corpo.ativo is not None and corpo.ativo != atual["ativo"]:
        conexao.execute(
            sa.text("UPDATE usuarios SET ativo = :a WHERE id = :id"), {"a": corpo.ativo, "id": usuario_id}
        )
        if not corpo.ativo:
            sessoes.encerrar_todas(conexao, usuario_id)
        auditoria.registrar(
            conexao,
            usuario_id=quem,
            acao="usuario_reativado" if corpo.ativo else "usuario_desativado",
            alvo_tipo="usuarios",
            alvo_id=usuario_id,
        )
    resposta = admin.obter(conexao, usuario_id)
    conexao.commit()
    return resposta


@router.post("/{usuario_id}/codigo")
def gerar_codigo(
    usuario_id: str,
    quem: str = Depends(exigir_administracao),
    conexao: Connection = Depends(obter_conexao),
) -> dict:
    alvo = admin.obter(conexao, usuario_id)
    if alvo is None:
        raise HTTPException(status_code=404, detail=NAO_ENCONTRADA)
    if not alvo["ativo"]:
        raise HTTPException(status_code=400, detail=REATIVAR_ANTES)
    codigo, expira_em = codigos.emitir(conexao, usuario_id, quem, _agora())
    # O código nunca vai para a auditoria.
    auditoria.registrar(
        conexao, usuario_id=quem, acao="codigo_gerado", alvo_tipo="usuarios", alvo_id=usuario_id
    )
    conexao.commit()
    return {"codigo": codigo, "codigo_expira_em": expira_em.isoformat()}
