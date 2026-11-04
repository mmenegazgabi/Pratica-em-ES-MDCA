"""Acesso aos programas de Gestão (US-01), provisório até o RBAC da T-33.

Quem chama é identificado pelo cabeçalho ``X-Usuario-Id``, sempre junto com o token
de serviço (o mesmo esquema do Financeiro, até o login da T-35). Os papéis vêm do
banco, não de cabeçalho:

- papéis da plataforma (``usuarios_papeis``): direção consulta todos os programas e
  administração consulta e gerencia todos;
- papéis no programa (``vinculos_equipe`` ativos): qualquer vínculo ativo consulta o
  programa, e a coordenação vinculada também gerencia a equipe e os espaços.

Vínculo ativo é o que não tem data de saída ou tem a saída ainda no futuro: a partir
da data de saída o acesso é bloqueado, e o vínculo continua no histórico. Usuário
desativado não acessa nada. Toda negação vai para ``log_auditoria`` antes do 403.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional, Set, Tuple

import sqlalchemy as sa
from fastapi import Depends, HTTPException, Request
from sqlalchemy.engine import Connection

from Financeiro.autenticacao import exigir_usuario
from Gestao import auditoria
from Gestao.banco import obter_conexao

PAPEIS_QUE_CONSULTAM_TODOS = {"direcao", "administracao"}
PAPEIS_QUE_GERENCIAM_TODOS = {"administracao"}
PAPEIS_QUE_GERENCIAM_O_PROGRAMA = {"coordenacao"}

PROGRAMA_NAO_ENCONTRADO = "Programa não encontrado."
SEM_ACESSO = "Seu perfil não tem acesso a este programa."
SEM_PERMISSAO_PARA_GERENCIAR = "Seu perfil não pode alterar a equipe nem os espaços deste programa."


@dataclass(frozen=True)
class Acesso:
    usuario_id: str
    programa_id: str
    pode_gerenciar: bool


def programa_existe(conexao: Connection, programa_id: str) -> bool:
    return conexao.execute(
        sa.text("SELECT 1 FROM projetos WHERE id = :id"), {"id": programa_id}
    ).first() is not None


def papeis_do_usuario(
    conexao: Connection, usuario_id: str, programa_id: str, hoje: date
) -> Optional[Tuple[Set[str], Set[str]]]:
    """Papéis da plataforma e papéis ativos no programa; ``None`` se o usuário não pode entrar."""
    ativo = conexao.execute(
        sa.text("SELECT ativo FROM usuarios WHERE id = :id"), {"id": usuario_id}
    ).scalar_one_or_none()
    if not ativo:
        return None
    globais = set(
        conexao.execute(
            sa.text("SELECT papel_id FROM usuarios_papeis WHERE usuario_id = :id"),
            {"id": usuario_id},
        ).scalars()
    )
    no_programa = set(
        conexao.execute(
            sa.text(
                """
                SELECT papel_id FROM vinculos_equipe
                WHERE usuario_id = :usuario AND programa_id = :programa
                  AND (data_saida IS NULL OR data_saida > :hoje)
                """
            ),
            {"usuario": usuario_id, "programa": programa_id, "hoje": hoje},
        ).scalars()
    )
    return globais, no_programa


def verificar_acesso(
    conexao: Connection,
    usuario_id: str,
    programa_id: str,
    *,
    gerenciar: bool,
    requisicao: Optional[Request] = None,
    hoje: Optional[date] = None,
) -> Acesso:
    if not programa_existe(conexao, programa_id):
        raise HTTPException(status_code=404, detail=PROGRAMA_NAO_ENCONTRADO)

    papeis = papeis_do_usuario(conexao, usuario_id, programa_id, hoje or date.today())
    if papeis is None:
        consulta = gerencia = False
    else:
        globais, no_programa = papeis
        gerencia = bool(globais & PAPEIS_QUE_GERENCIAM_TODOS) or bool(
            no_programa & PAPEIS_QUE_GERENCIAM_O_PROGRAMA
        )
        consulta = gerencia or bool(globais & PAPEIS_QUE_CONSULTAM_TODOS) or bool(no_programa)

    if not (gerencia if gerenciar else consulta):
        _registrar_negacao(conexao, usuario_id, programa_id, gerenciar, requisicao)
        detalhe = SEM_PERMISSAO_PARA_GERENCIAR if gerenciar and consulta else SEM_ACESSO
        raise HTTPException(status_code=403, detail=detalhe)
    return Acesso(usuario_id=usuario_id, programa_id=programa_id, pode_gerenciar=gerencia)


def _registrar_negacao(
    conexao: Connection,
    usuario_id: str,
    programa_id: str,
    gerenciar: bool,
    requisicao: Optional[Request],
) -> None:
    operacao = "gerenciar" if gerenciar else "consultar"
    detalhes = {"operacao": operacao}
    if requisicao is not None:
        detalhes.update(metodo=requisicao.method, rota=requisicao.url.path)
    auditoria.registrar(
        conexao,
        usuario_id=usuario_id,
        acao=auditoria.ACESSO_NEGADO,
        alvo_tipo="programa",
        alvo_id=programa_id,
        descricao=f"Tentativa de {operacao} o programa sem permissão",
        detalhes=detalhes,
    )
    # O 403 desfaria a transação; o registro da tentativa precisa ficar.
    conexao.commit()


def exigir_consulta_ao_programa(
    programa_id: str,
    requisicao: Request,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> Acesso:
    return verificar_acesso(conexao, usuario_id, programa_id, gerenciar=False, requisicao=requisicao)


def exigir_gestao_do_programa(
    programa_id: str,
    requisicao: Request,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> Acesso:
    return verificar_acesso(conexao, usuario_id, programa_id, gerenciar=True, requisicao=requisicao)
