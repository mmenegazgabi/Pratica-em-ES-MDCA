"""Turmas, matrículas e lista de espera de um programa (T-52 · US-04).

Acesso (``Gestao/acesso.py``):

- lista de turmas (sem nomes de pessoas): quem consulta o programa;
- detalhe da turma (com os nomes): a regra dos cadastros de pessoas da US-03, então a
  direção, que não vê cadastros individuais, recebe 403;
- cadastrar e editar turma, inscrever, chamar a lista de espera e desligar: quem gerencia
  o programa.

Toda negação vai para ``log_auditoria``. Um conflito de horário na inscrição também vai,
como alerta para a coordenação (critério da US-04).
"""

from datetime import date, datetime, time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Connection

from Gestao import auditoria, turmas
from Gestao.acesso import Acesso, exigir_consulta_ao_programa, exigir_gestao_do_programa, verificar_acesso_a_pessoas
from Gestao.banco import obter_conexao
from Gestao.erros import ErroDeCadastro

router = APIRouter(prefix="/gestao/programas/{programa_id}", tags=["gestao"])

CONFLITO_DE_HORARIO = "conflito_de_horario"


# --- Entradas ------------------------------------------------------------------
# Campos opcionais de propósito: o que falta volta como 400 com a lista (como no cadastro
# de programas), não como o 422 genérico da validação.


class TurmaEntrada(BaseModel):
    nome: Optional[str] = Field(default=None, max_length=200)
    espaco_id: Optional[str] = Field(default=None, max_length=100)
    responsavel_id: Optional[str] = Field(default=None, max_length=100)
    capacidade: Optional[int] = None
    # 1 = segunda … 7 = domingo.
    dias_semana: Optional[List[int]] = Field(default=None, max_length=7)
    hora_inicio: Optional[time] = None
    hora_fim: Optional[time] = None


class InscricaoEntrada(BaseModel):
    pessoa_id: str = Field(min_length=1, max_length=100)


class DesligamentoEntrada(BaseModel):
    data_saida: Optional[date] = None
    motivo: Optional[str] = Field(default=None, max_length=1000)


# --- Saídas --------------------------------------------------------------------


class _Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TurmaSaida(_Saida):
    id: str
    programa_id: str
    nome: str
    espaco_id: str
    espaco: str
    responsavel_id: str
    responsavel: str
    capacidade: int
    dias_semana: List[int]
    hora_inicio: time
    hora_fim: time
    ativas: int
    em_espera: int
    vagas_livres: int


class ConflitoSaida(_Saida):
    turma_id: str
    turma: str
    dias_semana: List[int]
    hora_inicio: time
    hora_fim: time


class MatriculaSaida(_Saida):
    id: str
    pessoa_id: str
    pessoa: str
    # ativa, espera ou desligada.
    situacao: str
    inscrito_em: datetime
    data_entrada: Optional[date]
    data_saida: Optional[date]
    motivo_saida: Optional[str]
    posicao_espera: Optional[int]
    # Outras turmas em que a pessoa está ativa no mesmo horário.
    conflitos: List[ConflitoSaida]


class TurmaDetalhadaSaida(_Saida):
    turma: TurmaSaida
    matriculas: List[MatriculaSaida]
    # Em ordem de inscrição: o primeiro é o próximo a ser chamado.
    lista_de_espera: List[MatriculaSaida]
    desligadas: List[MatriculaSaida]


class InscricaoSaida(_Saida):
    matricula: MatriculaSaida
    conflitos: List[ConflitoSaida]


# --- Apoio ---------------------------------------------------------------------


def _http(erro: ErroDeCadastro) -> HTTPException:
    return HTTPException(status_code=erro.status, detail=erro.mensagem)


def _alertar_conflitos(conexao: Connection, acesso: Acesso, turma_id: str, inscricao: turmas.Inscricao) -> None:
    if not inscricao.conflitos:
        return
    auditoria.registrar(
        conexao,
        usuario_id=acesso.usuario_id,
        acao=CONFLITO_DE_HORARIO,
        alvo_tipo="matricula",
        alvo_id=inscricao.matricula.id,
        descricao="Matrícula salva com conflito de horário com outra matrícula ativa",
        detalhes={
            "programa_id": acesso.programa_id,
            "turma_id": turma_id,
            "pessoa_id": inscricao.matricula.pessoa_id,
            "turmas_em_conflito": [c.turma_id for c in inscricao.conflitos],
        },
    )


# --- Rotas ---------------------------------------------------------------------


@router.get("/turmas", response_model=List[TurmaSaida])
def listar_turmas(
    acesso: Acesso = Depends(exigir_consulta_ao_programa),
    conexao: Connection = Depends(obter_conexao),
) -> List[turmas.Turma]:
    """Turmas do programa com vagas, matrículas ativas e lista de espera (só contagens)."""
    return turmas.listar_turmas(conexao, acesso.programa_id)


@router.post("/turmas", response_model=TurmaSaida, status_code=201)
def cadastrar_turma(
    dados: TurmaEntrada,
    acesso: Acesso = Depends(exigir_gestao_do_programa),
    conexao: Connection = Depends(obter_conexao),
) -> turmas.Turma:
    try:
        turma = turmas.cadastrar_turma(conexao, acesso.programa_id, dados.model_dump(), usuario_id=acesso.usuario_id)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    conexao.commit()
    return turma


@router.get("/turmas/{turma_id}", response_model=TurmaDetalhadaSaida)
def obter_turma(
    turma_id: str,
    requisicao: Request,
    acesso: Acesso = Depends(exigir_consulta_ao_programa),
    conexao: Connection = Depends(obter_conexao),
) -> turmas.TurmaDetalhada:
    """Matrículas ativas, lista de espera em ordem e histórico de desligamentos."""
    # Nomes de pessoas atendidas: mesma regra dos cadastros da US-03.
    verificar_acesso_a_pessoas(
        conexao, acesso.usuario_id, acesso.programa_id, cadastrar=False, alvo_tipo="turma", alvo_id=turma_id, requisicao=requisicao
    )
    try:
        return turmas.obter_turma(conexao, acesso.programa_id, turma_id)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro


@router.patch("/turmas/{turma_id}", response_model=TurmaSaida)
def editar_turma(
    turma_id: str,
    dados: TurmaEntrada,
    acesso: Acesso = Depends(exigir_gestao_do_programa),
    conexao: Connection = Depends(obter_conexao),
) -> turmas.Turma:
    """Só os campos enviados mudam; a capacidade não fica abaixo das matrículas ativas."""
    try:
        turma = turmas.editar_turma(conexao, acesso.programa_id, turma_id, dados.model_dump(exclude_unset=True))
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    conexao.commit()
    return turma


@router.post("/turmas/{turma_id}/matriculas", response_model=InscricaoSaida, status_code=201)
def inscrever(
    turma_id: str,
    dados: InscricaoEntrada,
    acesso: Acesso = Depends(exigir_gestao_do_programa),
    conexao: Connection = Depends(obter_conexao),
) -> turmas.Inscricao:
    """Matricula se há vaga; com a turma lotada, coloca na lista de espera (situação ``espera``)."""
    try:
        inscricao = turmas.inscrever(
            conexao, acesso.programa_id, turma_id, dados.pessoa_id.strip(), usuario_id=acesso.usuario_id
        )
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    _alertar_conflitos(conexao, acesso, turma_id, inscricao)
    conexao.commit()
    return inscricao


@router.post("/turmas/{turma_id}/lista-de-espera/chamada", response_model=InscricaoSaida)
def chamar_lista_de_espera(
    turma_id: str,
    acesso: Acesso = Depends(exigir_gestao_do_programa),
    conexao: Connection = Depends(obter_conexao),
) -> turmas.Inscricao:
    """Passa o primeiro da lista de espera para a turma; 409 se lotada ou sem fila."""
    try:
        inscricao = turmas.chamar_proximo(conexao, acesso.programa_id, turma_id)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    _alertar_conflitos(conexao, acesso, turma_id, inscricao)
    conexao.commit()
    return inscricao


@router.patch("/turmas/{turma_id}/matriculas/{matricula_id}/desligamento", response_model=MatriculaSaida)
def desligar(
    turma_id: str,
    matricula_id: str,
    dados: DesligamentoEntrada,
    acesso: Acesso = Depends(exigir_gestao_do_programa),
    conexao: Connection = Depends(obter_conexao),
) -> turmas.Matricula:
    """Data e motivo obrigatórios (400 sem eles); a matrícula fica no histórico."""
    try:
        matricula = turmas.desligar(
            conexao, acesso.programa_id, turma_id, matricula_id, data_saida=dados.data_saida, motivo=dados.motivo
        )
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    conexao.commit()
    return matricula
