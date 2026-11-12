"""Equipe e espaços de um programa (US-01, tabelas da T-38).

Desligar é registrar a data de saída: o vínculo nunca é apagado, e o histórico ligado
a ele continua válido. A lista de quem está ativo é a mesma usada para escolher o
responsável de uma turma (T-51).

As funções não fazem commit: a rota decide quando a operação termina.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

UNIQUE_VIOLATION = "23505"

# A coordenação é dada na conta e vale para todos os programas (T-87); não é vínculo.
PAPEIS_FORA_DE_VINCULO = {"coordenacao"}
COORDENACAO_NAO_E_VINCULO = (
    "A coordenação vale para todos os programas e é dada na conta, na Administração. "
    "Escolha outro papel para o vínculo."
)


class ErroDeEquipe(Exception):
    """Erro de regra; ``status`` é a resposta HTTP correspondente."""

    status = 400

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


class DadosInvalidos(ErroDeEquipe):
    status = 400


class NaoEncontrado(ErroDeEquipe):
    status = 404


class Conflito(ErroDeEquipe):
    status = 409


@dataclass(frozen=True)
class Vinculo:
    id: str
    usuario_id: str
    nome: str
    papel_id: str
    papel: str
    data_entrada: date
    data_saida: Optional[date]
    ativo: bool


@dataclass(frozen=True)
class Espaco:
    id: str
    nome: str
    capacidade: Optional[int]


_SELECIONAR_VINCULOS = """
    SELECT v.id, v.usuario_id, u.nome, v.papel_id, p.nome AS papel,
           v.data_entrada, v.data_saida,
           (u.ativo AND (v.data_saida IS NULL OR v.data_saida > :hoje)) AS ativo
    FROM vinculos_equipe v
    JOIN usuarios u ON u.id = v.usuario_id
    JOIN papeis p ON p.id = v.papel_id
"""


def _vinculo(linha) -> Vinculo:
    return Vinculo(**linha._mapping)


def _eh_duplicidade(erro: IntegrityError) -> bool:
    return getattr(erro.orig, "sqlstate", None) == UNIQUE_VIOLATION


def listar_equipe(
    conexao: Connection,
    programa_id: str,
    *,
    incluir_desligados: bool = False,
    hoje: Optional[date] = None,
) -> List[Vinculo]:
    # Conta desativada não acessa o programa (acesso.py), então também não é opção de
    # responsável; o vínculo continua no histórico, com ``ativo`` falso.
    filtro = "" if incluir_desligados else "AND u.ativo AND (v.data_saida IS NULL OR v.data_saida > :hoje)"
    linhas = conexao.execute(
        sa.text(
            f"""
            {_SELECIONAR_VINCULOS}
            WHERE v.programa_id = :programa {filtro}
            ORDER BY lower(u.nome), v.data_entrada, v.id
            """
        ),
        {"programa": programa_id, "hoje": hoje or date.today()},
    )
    return [_vinculo(linha) for linha in linhas]


def vincular(
    conexao: Connection,
    programa_id: str,
    *,
    usuario_id: str,
    papel_id: str,
    data_entrada: date,
    hoje: Optional[date] = None,
) -> Vinculo:
    ativo = conexao.execute(
        sa.text("SELECT ativo FROM usuarios WHERE id = :id"), {"id": usuario_id}
    ).scalar_one_or_none()
    if ativo is None:
        raise DadosInvalidos("Usuário não encontrado.")
    if not ativo:
        raise Conflito("Usuário desativado não pode ser vinculado.")
    papel_existe = conexao.execute(
        sa.text("SELECT 1 FROM papeis WHERE id = :id"), {"id": papel_id}
    ).first()
    if papel_existe is None:
        raise DadosInvalidos("Papel inválido.")
    if papel_id in PAPEIS_FORA_DE_VINCULO:
        raise DadosInvalidos(COORDENACAO_NAO_E_VINCULO)

    vinculo_id = str(uuid.uuid4())
    try:
        # Savepoint: se o vínculo já existir, só esta inclusão é desfeita.
        with conexao.begin_nested():
            conexao.execute(
                sa.text(
                    """
                    INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada)
                    VALUES (:id, :usuario, :programa, :papel, :entrada)
                    """
                ),
                {
                    "id": vinculo_id,
                    "usuario": usuario_id,
                    "programa": programa_id,
                    "papel": papel_id,
                    "entrada": data_entrada,
                },
            )
    except IntegrityError as erro:
        if _eh_duplicidade(erro):
            raise Conflito("Essa pessoa já tem um vínculo ativo com esse papel no programa.") from erro
        raise
    return _buscar_vinculo(conexao, programa_id, vinculo_id, hoje)


def registrar_desligamento(
    conexao: Connection,
    programa_id: str,
    vinculo_id: str,
    *,
    data_saida: date,
    hoje: Optional[date] = None,
) -> Vinculo:
    vinculo = _buscar_vinculo(conexao, programa_id, vinculo_id, hoje)
    if vinculo.data_saida is not None:
        raise Conflito("O desligamento deste vínculo já foi registrado.")
    if data_saida < vinculo.data_entrada:
        raise DadosInvalidos("A data de saída não pode ser anterior à data de entrada.")
    conexao.execute(
        sa.text("UPDATE vinculos_equipe SET data_saida = :saida WHERE id = :id"),
        {"saida": data_saida, "id": vinculo_id},
    )
    return _buscar_vinculo(conexao, programa_id, vinculo_id, hoje)


def _buscar_vinculo(
    conexao: Connection, programa_id: str, vinculo_id: str, hoje: Optional[date]
) -> Vinculo:
    linha = conexao.execute(
        sa.text(f"{_SELECIONAR_VINCULOS} WHERE v.id = :id AND v.programa_id = :programa"),
        {"id": vinculo_id, "programa": programa_id, "hoje": hoje or date.today()},
    ).first()
    if linha is None:
        raise NaoEncontrado("Vínculo não encontrado neste programa.")
    return _vinculo(linha)


def listar_espacos(conexao: Connection, programa_id: str) -> List[Espaco]:
    linhas = conexao.execute(
        sa.text(
            "SELECT id, nome, capacidade FROM espacos WHERE programa_id = :programa "
            "ORDER BY lower(nome), id"
        ),
        {"programa": programa_id},
    )
    return [Espaco(**linha._mapping) for linha in linhas]


def criar_espaco(
    conexao: Connection, programa_id: str, *, nome: str, capacidade: Optional[int]
) -> Espaco:
    espaco = Espaco(id=str(uuid.uuid4()), nome=nome.strip(), capacidade=capacidade)
    if not espaco.nome:
        raise DadosInvalidos("Informe o nome do espaço.")
    try:
        with conexao.begin_nested():
            conexao.execute(
                sa.text(
                    "INSERT INTO espacos (id, programa_id, nome, capacidade) "
                    "VALUES (:id, :programa, :nome, :capacidade)"
                ),
                {
                    "id": espaco.id,
                    "programa": programa_id,
                    "nome": espaco.nome,
                    "capacidade": espaco.capacidade,
                },
            )
    except IntegrityError as erro:
        if _eh_duplicidade(erro):
            raise Conflito("Já existe um espaço com esse nome neste programa.") from erro
        raise
    return espaco
