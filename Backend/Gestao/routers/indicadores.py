"""Rota dos indicadores agregados (T-72 · US-10).

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
    try:
        recorte = indicadores.periodo(inicio, fim, date.today())
    except ErroDeCadastro as erro:
        raise HTTPException(status_code=erro.status, detail=erro.mensagem) from erro
    if programa_id:
        verificar_acesso(conexao, usuario_id, programa_id, gerenciar=False, requisicao=requisicao)
        programas = [programa_id]
    else:
        programas = programas_consultaveis(conexao, usuario_id)
    return indicadores.calcular(conexao, programas, recorte)
