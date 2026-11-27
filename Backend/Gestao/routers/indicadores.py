"""Rotas dos indicadores agregados (T-72 · US-10) e das pendências do período (T-91).

Cada perfil vê só os programas que pode consultar: a equipe, os programas em que tem
vínculo ativo; a direção e a administração, todos. Com ``programa_id``, o acesso a esse
programa é conferido como nas outras rotas (404 se não existe, 403 registrado na trilha).
A resposta não tem dados pessoais, só números agregados.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.engine import Connection

from Financeiro.autenticacao import exigir_usuario
from Gestao import indicadores
from Gestao.acesso import programas_consultaveis, verificar_acesso
from Gestao.banco import obter_conexao
from Gestao.erros import ErroDeCadastro

router = APIRouter(prefix="/gestao", tags=["gestao"])


class PeriodoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    inicio: date
    fim: date
    # Falso enquanto o período inclui hoje ou o futuro: os números ainda podem mudar.
    fechado: bool


class NumerosSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pessoas_acompanhadas: int
    encontros_realizados: int
    presencas: int
    ausencias: int
    frequencia: Optional[float]
    horas_de_atividades: float
    metas: int
    percentual_medio_das_metas: Optional[float]


class ProgramaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    programa_id: str
    nome: str
    identificador: Optional[str]
    numeros: NumerosSaida


class IndicadoresSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    periodo: PeriodoSaida
    totais: NumerosSaida
    programas: List[ProgramaSaida]


class NumerosDePendenciaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chamadas_sem_registro: int
    encontros_sem_evidencia: int
    autorizacoes_de_imagem_vencidas: int
    total: int


class PendenciasDoProgramaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    programa_id: str
    nome: str
    identificador: Optional[str]
    numeros: NumerosDePendenciaSaida


class PendenciasSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    periodo: PeriodoSaida
    totais: NumerosDePendenciaSaida
    programas: List[PendenciasDoProgramaSaida]


def _recorte(conexao, usuario_id, programa_id, inicio, fim, requisicao):
    """Período e programas da consulta, com o acesso conferido como nas outras rotas."""
    try:
        recorte = indicadores.periodo(inicio, fim, date.today())
    except ErroDeCadastro as erro:
        raise HTTPException(status_code=erro.status, detail=erro.mensagem) from erro
    if programa_id:
        verificar_acesso(conexao, usuario_id, programa_id, gerenciar=False, requisicao=requisicao)
        return recorte, [programa_id]
    return recorte, programas_consultaveis(conexao, usuario_id)


@router.get("/indicadores", response_model=IndicadoresSaida)
def consultar(
    requisicao: Request,
    programa_id: Optional[str] = None,
    inicio: Optional[date] = None,
    fim: Optional[date] = None,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> indicadores.Indicadores:
    """Indicadores do período (padrão: o mês atual) nos programas visíveis a quem consulta."""
    recorte, programas = _recorte(conexao, usuario_id, programa_id, inicio, fim, requisicao)
    return indicadores.calcular(conexao, programas, recorte)


@router.get("/pendencias", response_model=PendenciasSaida)
def consultar_pendencias(
    requisicao: Request,
    programa_id: Optional[str] = None,
    inicio: Optional[date] = None,
    fim: Optional[date] = None,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> indicadores.Pendencias:
    """O que falta registrar antes de fechar o período (Visão geral, T-91): só números."""
    recorte, programas = _recorte(conexao, usuario_id, programa_id, inicio, fim, requisicao)
    return indicadores.pendencias(conexao, programas, recorte, date.today())
