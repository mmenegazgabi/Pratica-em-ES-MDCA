"""Programas/Projetos do cadastro canônico (tabela ``projetos``, ARQ-02), com convênios
e vagas (US-02, tabelas da T-45).

O programa é o mesmo registro que o Financeiro referencia em orçamentos e lançamentos;
o ``identificador`` é o código compartilhado entre os dois módulos. Programas antigos,
criados só com nome, continuam válidos na leitura; os campos obrigatórios valem para
os programas cadastrados por aqui.

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


class ErroDeCadastro(Exception):
    """Erro de regra; ``status`` é a resposta HTTP correspondente."""

    status = 400

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


class DadosInvalidos(ErroDeCadastro):
    status = 400


class NaoEncontrado(ErroDeCadastro):
    status = 404


class Conflito(ErroDeCadastro):
    status = 409


# Padrão do protótipo: alerta a partir de 3 faltas consecutivas.
LIMITE_FALTAS_PADRAO = 3


@dataclass(frozen=True)
class Programa:
    id: str
    nome: str
    # Opcionais: programas antigos (e os criados pelo Financeiro) só têm nome.
    identificador: Optional[str] = None
    vigencia_inicio: Optional[date] = None
    vigencia_fim: Optional[date] = None


@dataclass(frozen=True)
class ProgramaDetalhado:
    id: str
    nome: str
    identificador: Optional[str]
    publico: Optional[str]
    responsavel: Optional[str]
    vigencia_inicio: Optional[date]
    vigencia_fim: Optional[date]
    descricao: Optional[str]
    status: str
    # Faltas consecutivas que geram alerta de infrequência (US-06).
    limite_faltas: int = LIMITE_FALTAS_PADRAO


@dataclass(frozen=True)
class Convenio:
    id: str
    nome: str
    concedente: Optional[str]
    vigencia_inicio: Optional[date]
    vigencia_fim: Optional[date]


@dataclass(frozen=True)
class Vaga:
    id: str
    descricao: str
    quantidade: int


def texto(valor: Optional[str]) -> Optional[str]:
    """Texto sem espaços nas pontas; vazio vira ``None`` (campo não informado)."""
    if valor is None:
        return None
    return valor.strip() or None


def faltando(campos: List[str], o_que: str) -> DadosInvalidos:
    """400 que lista, de uma vez, tudo o que falta (ex.: "Programa sem público e responsável.")."""
    lista = campos[0] if len(campos) == 1 else ", ".join(campos[:-1]) + " e " + campos[-1]
    return DadosInvalidos(f"{o_que} sem {lista}.")


def formatar_data(dia: date) -> str:
    return dia.strftime("%d/%m/%Y")


def _eh_duplicidade(erro: IntegrityError) -> bool:
    return getattr(erro.orig, "sqlstate", None) == UNIQUE_VIOLATION


def listar_programas(conexao: Connection) -> List[Programa]:
    linhas = conexao.execute(
        sa.text(
            """
            SELECT id, nome, identificador, vigencia_inicio, vigencia_fim
            FROM projetos ORDER BY lower(nome), id
            """
        )
    )
    return [Programa(**linha._mapping) for linha in linhas]


def buscar_programa(conexao: Connection, programa_id: str) -> ProgramaDetalhado:
    linha = conexao.execute(
        sa.text(
            """
            SELECT id, nome, identificador, publico, responsavel,
                   vigencia_inicio, vigencia_fim, descricao, status, limite_faltas
            FROM projetos WHERE id = :id
            """
        ),
        {"id": programa_id},
    ).first()
    if linha is None:
        raise NaoEncontrado("Programa não encontrado.")
    return ProgramaDetalhado(**linha._mapping)


def cadastrar_programa(
    conexao: Connection,
    *,
    nome: Optional[str],
    identificador: Optional[str],
    publico: Optional[str],
    responsavel: Optional[str],
    vigencia_inicio: Optional[date],
    vigencia_fim: Optional[date],
    descricao: Optional[str] = None,
    limite_faltas: Optional[int] = None,
) -> ProgramaDetalhado:
    nome, identificador = texto(nome), texto(identificador)
    publico, responsavel = texto(publico), texto(responsavel)
    _validar_programa(nome, identificador, publico, responsavel, vigencia_inicio, vigencia_fim)
    limite_faltas = LIMITE_FALTAS_PADRAO if limite_faltas is None else limite_faltas
    _validar_limite(limite_faltas)

    programa_id = str(uuid.uuid4())
    try:
        # Savepoint: se o identificador já existir, só esta inclusão é desfeita.
        with conexao.begin_nested():
            conexao.execute(
                sa.text(
                    """
                    INSERT INTO projetos (id, nome, identificador, publico, responsavel,
                                          vigencia_inicio, vigencia_fim, descricao, limite_faltas)
                    VALUES (:id, :nome, :identificador, :publico, :responsavel,
                            :inicio, :fim, :descricao, :limite_faltas)
                    """
                ),
                {
                    "id": programa_id,
                    "nome": nome,
                    "identificador": identificador,
                    "publico": publico,
                    "responsavel": responsavel,
                    "inicio": vigencia_inicio,
                    "fim": vigencia_fim,
                    "descricao": texto(descricao),
                    "limite_faltas": limite_faltas,
                },
            )
    except IntegrityError as erro:
        if _eh_duplicidade(erro):
            raise Conflito("Já existe um programa com esse identificador.") from erro
        raise
    return buscar_programa(conexao, programa_id)


def _validar_programa(nome, identificador, publico, responsavel, vigencia_inicio, vigencia_fim) -> None:
    """Regras do cadastro e da edição: tudo o que falta de uma vez, e vigência coerente."""
    ausentes = [
        rotulo
        for rotulo, valor in (
            ("nome", nome),
            ("identificador", identificador),
            ("vigência (início e fim)", vigencia_inicio and vigencia_fim),
            ("público", publico),
            ("responsável", responsavel),
        )
        if not valor
    ]
    if ausentes:
        raise faltando(ausentes, "Programa")
    if vigencia_fim < vigencia_inicio:
        raise DadosInvalidos("O fim da vigência não pode ser anterior ao início.")


def _validar_limite(limite_faltas: Optional[int]) -> None:
    if limite_faltas is None or limite_faltas < 1:
        raise DadosInvalidos("O limite de faltas precisa ser de pelo menos 1.")


CAMPOS_EDITAVEIS = (
    "limite_faltas",
    "nome",
    "identificador",
    "publico",
    "responsavel",
    "vigencia_inicio",
    "vigencia_fim",
    "descricao",
)


def editar_programa(conexao: Connection, programa_id: str, alteracoes: dict) -> ProgramaDetalhado:
    """Altera só os campos enviados; o resultado precisa valer as mesmas regras do cadastro.

    Um programa antigo, só com nome, precisa ganhar os campos obrigatórios na edição.
    """
    atual = buscar_programa(conexao, programa_id)
    dados = {campo: getattr(atual, campo) for campo in CAMPOS_EDITAVEIS}
    dados.update({campo: valor for campo, valor in alteracoes.items() if campo in CAMPOS_EDITAVEIS})
    for campo in ("nome", "identificador", "publico", "responsavel", "descricao"):
        dados[campo] = texto(dados[campo])
    _validar_programa(
        dados["nome"],
        dados["identificador"],
        dados["publico"],
        dados["responsavel"],
        dados["vigencia_inicio"],
        dados["vigencia_fim"],
    )
    _validar_limite(dados["limite_faltas"])
    try:
        with conexao.begin_nested():
            conexao.execute(
                sa.text(
                    """
                    UPDATE projetos SET nome = :nome, identificador = :identificador,
                        publico = :publico, responsavel = :responsavel,
                        vigencia_inicio = :vigencia_inicio, vigencia_fim = :vigencia_fim,
                        descricao = :descricao, limite_faltas = :limite_faltas
                    WHERE id = :id
                    """
                ),
                {**dados, "id": programa_id},
            )
    except IntegrityError as erro:
        if _eh_duplicidade(erro):
            raise Conflito("Já existe um programa com esse identificador.") from erro
        raise
    return buscar_programa(conexao, programa_id)


def listar_convenios(conexao: Connection, programa_id: str) -> List[Convenio]:
    buscar_programa(conexao, programa_id)
    linhas = conexao.execute(
        sa.text(
            """
            SELECT id, nome, concedente, vigencia_inicio, vigencia_fim
            FROM convenios WHERE programa_id = :programa
            ORDER BY lower(nome), id
            """
        ),
        {"programa": programa_id},
    )
    return [Convenio(**linha._mapping) for linha in linhas]


def cadastrar_convenio(
    conexao: Connection,
    programa_id: str,
    *,
    nome: Optional[str],
    concedente: Optional[str] = None,
    vigencia_inicio: Optional[date] = None,
    vigencia_fim: Optional[date] = None,
) -> Convenio:
    buscar_programa(conexao, programa_id)
    convenio = Convenio(
        id=str(uuid.uuid4()),
        nome=texto(nome),
        concedente=texto(concedente),
        vigencia_inicio=vigencia_inicio,
        vigencia_fim=vigencia_fim,
    )
    if not convenio.nome:
        raise faltando(["nome"], "Convênio")
    if vigencia_inicio and vigencia_fim and vigencia_fim < vigencia_inicio:
        raise DadosInvalidos("O fim da vigência do convênio não pode ser anterior ao início.")
    conexao.execute(
        sa.text(
            """
            INSERT INTO convenios (id, programa_id, nome, concedente, vigencia_inicio, vigencia_fim)
            VALUES (:id, :programa, :nome, :concedente, :inicio, :fim)
            """
        ),
        {
            "id": convenio.id,
            "programa": programa_id,
            "nome": convenio.nome,
            "concedente": convenio.concedente,
            "inicio": vigencia_inicio,
            "fim": vigencia_fim,
        },
    )
    return convenio


def listar_vagas(conexao: Connection, programa_id: str) -> List[Vaga]:
    buscar_programa(conexao, programa_id)
    linhas = conexao.execute(
        sa.text(
            "SELECT id, descricao, quantidade FROM vagas WHERE programa_id = :programa "
            "ORDER BY lower(descricao), id"
        ),
        {"programa": programa_id},
    )
    return [Vaga(**linha._mapping) for linha in linhas]


def cadastrar_vagas(
    conexao: Connection, programa_id: str, *, descricao: Optional[str], quantidade: Optional[int]
) -> Vaga:
    buscar_programa(conexao, programa_id)
    descricao = texto(descricao)
    ausentes = [r for r, v in (("descrição", descricao), ("quantidade", quantidade)) if v is None]
    if ausentes:
        raise faltando(ausentes, "Vagas")
    if quantidade <= 0:
        raise DadosInvalidos("A quantidade de vagas deve ser maior que zero.")
    vaga = Vaga(id=str(uuid.uuid4()), descricao=descricao, quantidade=quantidade)
    try:
        with conexao.begin_nested():
            conexao.execute(
                sa.text(
                    "INSERT INTO vagas (id, programa_id, descricao, quantidade) "
                    "VALUES (:id, :programa, :descricao, :quantidade)"
                ),
                {
                    "id": vaga.id,
                    "programa": programa_id,
                    "descricao": vaga.descricao,
                    "quantidade": vaga.quantidade,
                },
            )
    except IntegrityError as erro:
        if _eh_duplicidade(erro):
            raise Conflito("Já existem vagas com essa descrição neste programa.") from erro
        raise
    return vaga
