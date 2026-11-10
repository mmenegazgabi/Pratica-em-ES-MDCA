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

A lista de usuários da plataforma (T-40) é consultada pela administração e por quem
coordena algum programa (para escolher quem vincular à equipe).

Cadastros de pessoas atendidas (US-03) são dados de crianças e famílias: consulta só
quem tem vínculo ativo no programa da pessoa e a administração (a direção não vê
cadastros individuais); cadastram e alteram a coordenação e a assistência social
vinculadas ao programa, e a administração.

Atividades, chamadas e evidências (US-05): registram a coordenação e os educadores
vinculados ao programa, e a administração.
"""

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Set, Tuple

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
SEM_ACESSO_AOS_USUARIOS = "Seu perfil não tem acesso à lista de usuários."

PAPEIS_COM_TODAS_AS_PESSOAS = {"administracao"}
PAPEIS_QUE_CADASTRAM_PESSOAS = {"coordenacao", "assistente_social"}
PESSOA_NAO_ENCONTRADA = "Pessoa não encontrada."
SEM_ACESSO_A_PESSOAS = "Seu perfil não tem acesso aos cadastros de pessoas deste programa."
SEM_PERMISSAO_PARA_CADASTRAR = "Seu perfil não pode cadastrar nem alterar pessoas deste programa."

PAPEIS_QUE_REGISTRAM_ATIVIDADES = {"coordenacao", "educador"}
SEM_PERMISSAO_PARA_REGISTRAR = "Seu perfil não pode registrar atividades neste programa."


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


# Visão integrada (T-78): quem vê os valores financeiros do programa. Provisório até a
# matriz de permissões do Financeiro (T-37) e o RBAC (T-33).
PAPEIS_QUE_VEEM_FINANCEIRO_DE_TODOS = {"direcao", "administracao"}
PAPEIS_QUE_VEEM_FINANCEIRO_DO_PROGRAMA = {"coordenacao"}


def ve_valores_financeiros(
    conexao: Connection, usuario_id: str, programa_id: str, hoje: Optional[date] = None
) -> bool:
    papeis = papeis_do_usuario(conexao, usuario_id, programa_id, hoje or date.today())
    if papeis is None:
        return False
    globais, no_programa = papeis
    return bool(globais & PAPEIS_QUE_VEEM_FINANCEIRO_DE_TODOS) or bool(
        no_programa & PAPEIS_QUE_VEEM_FINANCEIRO_DO_PROGRAMA
    )


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
        operacao = "gerenciar" if gerenciar else "consultar"
        _registrar_negacao(
            conexao,
            usuario_id,
            alvo_tipo="programa",
            alvo_id=programa_id,
            operacao=operacao,
            descricao=f"Tentativa de {operacao} o programa sem permissão",
            requisicao=requisicao,
        )
        detalhe = SEM_PERMISSAO_PARA_GERENCIAR if gerenciar and consulta else SEM_ACESSO
        raise HTTPException(status_code=403, detail=detalhe)
    return Acesso(usuario_id=usuario_id, programa_id=programa_id, pode_gerenciar=gerencia)


def pode_consultar_usuarios(conexao: Connection, usuario_id: str, hoje: date) -> bool:
    """Administração da plataforma, ou coordenação ativa em algum programa."""
    return conexao.execute(
        sa.text(
            """
            SELECT 1 FROM usuarios u
            WHERE u.id = :id AND u.ativo AND (
                EXISTS (SELECT 1 FROM usuarios_papeis up
                        WHERE up.usuario_id = u.id AND up.papel_id IN :globais)
                OR EXISTS (SELECT 1 FROM vinculos_equipe v
                           WHERE v.usuario_id = u.id AND v.papel_id IN :no_programa
                             AND (v.data_saida IS NULL OR v.data_saida > :hoje))
            )
            """
        ).bindparams(
            sa.bindparam("globais", expanding=True),
            sa.bindparam("no_programa", expanding=True),
        ),
        {
            "id": usuario_id,
            "globais": sorted(PAPEIS_QUE_GERENCIAM_TODOS),
            "no_programa": sorted(PAPEIS_QUE_GERENCIAM_O_PROGRAMA),
            "hoje": hoje,
        },
    ).first() is not None


def verificar_acesso_aos_usuarios(
    conexao: Connection,
    usuario_id: str,
    *,
    requisicao: Optional[Request] = None,
    hoje: Optional[date] = None,
) -> str:
    if not pode_consultar_usuarios(conexao, usuario_id, hoje or date.today()):
        _registrar_negacao(
            conexao,
            usuario_id,
            alvo_tipo="usuarios",
            alvo_id=None,
            operacao="consultar",
            descricao="Tentativa de consultar a lista de usuários sem permissão",
            requisicao=requisicao,
        )
        raise HTTPException(status_code=403, detail=SEM_ACESSO_AOS_USUARIOS)
    return usuario_id


def _registrar_negacao(
    conexao: Connection,
    usuario_id: str,
    *,
    alvo_tipo: str,
    alvo_id: Optional[str],
    operacao: str,
    descricao: str,
    requisicao: Optional[Request],
) -> None:
    detalhes = {"operacao": operacao}
    if requisicao is not None:
        detalhes.update(metodo=requisicao.method, rota=requisicao.url.path)
    auditoria.registrar(
        conexao,
        usuario_id=usuario_id,
        acao=auditoria.ACESSO_NEGADO,
        alvo_tipo=alvo_tipo,
        alvo_id=alvo_id,
        descricao=descricao,
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


@dataclass(frozen=True)
class AcessoAPessoas:
    usuario_id: str
    programa_id: str
    pode_cadastrar: bool


def verificar_acesso_a_pessoas(
    conexao: Connection,
    usuario_id: str,
    programa_id: str,
    *,
    cadastrar: bool,
    alvo_tipo: str = "programa",
    alvo_id: Optional[str] = None,
    requisicao: Optional[Request] = None,
    hoje: Optional[date] = None,
) -> AcessoAPessoas:
    """Regra dos cadastros de pessoas (US-03) sobre o programa da pessoa."""
    if not programa_existe(conexao, programa_id):
        raise HTTPException(status_code=404, detail=PROGRAMA_NAO_ENCONTRADO)

    papeis = papeis_do_usuario(conexao, usuario_id, programa_id, hoje or date.today())
    if papeis is None:
        consulta = cadastro = False
    else:
        globais, no_programa = papeis
        todas = bool(globais & PAPEIS_COM_TODAS_AS_PESSOAS)
        cadastro = todas or bool(no_programa & PAPEIS_QUE_CADASTRAM_PESSOAS)
        consulta = cadastro or todas or bool(no_programa)

    if not (cadastro if cadastrar else consulta):
        operacao = "cadastrar" if cadastrar else "consultar"
        _registrar_negacao(
            conexao,
            usuario_id,
            alvo_tipo=alvo_tipo,
            alvo_id=alvo_id or programa_id,
            operacao=operacao,
            descricao=f"Tentativa de {operacao} cadastro de pessoa sem permissão",
            requisicao=requisicao,
        )
        detalhe = SEM_PERMISSAO_PARA_CADASTRAR if cadastrar and consulta else SEM_ACESSO_A_PESSOAS
        raise HTTPException(status_code=403, detail=detalhe)
    return AcessoAPessoas(usuario_id=usuario_id, programa_id=programa_id, pode_cadastrar=cadastro)


def programas_com_pessoas_visiveis(
    conexao: Connection, usuario_id: str, hoje: Optional[date] = None
) -> Optional[List[str]]:
    """Programas cujas pessoas o usuário pode listar; ``None`` quando são todos."""
    ativo = conexao.execute(
        sa.text("SELECT ativo FROM usuarios WHERE id = :id"), {"id": usuario_id}
    ).scalar_one_or_none()
    if not ativo:
        return []
    globais = set(
        conexao.execute(
            sa.text("SELECT papel_id FROM usuarios_papeis WHERE usuario_id = :id"), {"id": usuario_id}
        ).scalars()
    )
    if globais & PAPEIS_COM_TODAS_AS_PESSOAS:
        return None
    return list(
        conexao.execute(
            sa.text(
                """
                SELECT DISTINCT programa_id FROM vinculos_equipe
                WHERE usuario_id = :id AND (data_saida IS NULL OR data_saida > :hoje)
                ORDER BY programa_id
                """
            ),
            {"id": usuario_id, "hoje": hoje or date.today()},
        ).scalars()
    )


def _acesso_a_pessoa(conexao, usuario_id, pessoa_id, requisicao, *, cadastrar) -> AcessoAPessoas:
    programa_id = conexao.execute(
        sa.text("SELECT programa_id FROM pessoas WHERE id = :id"), {"id": pessoa_id}
    ).scalar_one_or_none()
    if programa_id is None:
        raise HTTPException(status_code=404, detail=PESSOA_NAO_ENCONTRADA)
    return verificar_acesso_a_pessoas(
        conexao,
        usuario_id,
        programa_id,
        cadastrar=cadastrar,
        alvo_tipo="pessoa",
        alvo_id=pessoa_id,
        requisicao=requisicao,
    )


def exigir_consulta_a_pessoa(
    pessoa_id: str,
    requisicao: Request,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> AcessoAPessoas:
    return _acesso_a_pessoa(conexao, usuario_id, pessoa_id, requisicao, cadastrar=False)


def exigir_cadastro_na_pessoa(
    pessoa_id: str,
    requisicao: Request,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> AcessoAPessoas:
    return _acesso_a_pessoa(conexao, usuario_id, pessoa_id, requisicao, cadastrar=True)


def verificar_registro_de_atividade(
    conexao: Connection,
    usuario_id: str,
    programa_id: str,
    *,
    requisicao: Optional[Request] = None,
    hoje: Optional[date] = None,
) -> Acesso:
    """Quem pode registrar encontros, chamadas e evidências no programa (US-05)."""
    if not programa_existe(conexao, programa_id):
        raise HTTPException(status_code=404, detail=PROGRAMA_NAO_ENCONTRADO)

    papeis = papeis_do_usuario(conexao, usuario_id, programa_id, hoje or date.today())
    if papeis is None:
        consulta = registra = False
    else:
        globais, no_programa = papeis
        registra = bool(globais & PAPEIS_QUE_GERENCIAM_TODOS) or bool(
            no_programa & PAPEIS_QUE_REGISTRAM_ATIVIDADES
        )
        consulta = registra or bool(globais & PAPEIS_QUE_CONSULTAM_TODOS) or bool(no_programa)

    if not registra:
        _registrar_negacao(
            conexao,
            usuario_id,
            alvo_tipo="programa",
            alvo_id=programa_id,
            operacao="registrar_atividade",
            descricao="Tentativa de registrar atividade sem permissão",
            requisicao=requisicao,
        )
        raise HTTPException(status_code=403, detail=SEM_PERMISSAO_PARA_REGISTRAR if consulta else SEM_ACESSO)
    gerencia = bool(globais & PAPEIS_QUE_GERENCIAM_TODOS) or bool(no_programa & PAPEIS_QUE_GERENCIAM_O_PROGRAMA)
    return Acesso(usuario_id=usuario_id, programa_id=programa_id, pode_gerenciar=gerencia)


def exigir_registro_de_atividade(
    programa_id: str,
    requisicao: Request,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> Acesso:
    return verificar_registro_de_atividade(conexao, usuario_id, programa_id, requisicao=requisicao)


def exigir_acesso_aos_usuarios(
    requisicao: Request,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> str:
    return verificar_acesso_aos_usuarios(conexao, usuario_id, requisicao=requisicao)
