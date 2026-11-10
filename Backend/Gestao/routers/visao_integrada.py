from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.engine import Connection

from Gestao import auditoria, visao_integrada
from Gestao.acesso import Acesso, exigir_consulta_ao_programa, ve_valores_financeiros
from Gestao.banco import obter_conexao
from Gestao.programas import ErroDeCadastro

router = APIRouter(prefix="/gestao/programas/{programa_id}", tags=["gestao"])


class ProgramaResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nome: str
    # O código compartilhado com o Financeiro (ARQ-02).
    identificador: Optional[str]


class MetaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    meta_id: str
    descricao: str
    unidade: Optional[str]
    acao_id: str
    acao: str
    objetivo_id: str
    objetivo: str
    planejado: float
    realizado: float
    percentual: float


class FisicaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metas: List[MetaSaida]
    # Média dos percentuais das metas; vazio quando o programa ainda não tem metas.
    percentual_medio: Optional[float]


class FinanceiraSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # Como o projeto do Financeiro foi achado: "id", "nome" (provisório, enquanto o
    # Financeiro tem cadastro próprio em memória) ou "nenhum".
    vinculo: str
    projeto_id: Optional[str]
    projeto: Optional[str]
    orcado: float
    realizado: float
    saldo: float
    percentual_executado: Optional[float]


class VisaoIntegradaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    programa: ProgramaResumo
    inicio: Optional[date]
    fim: Optional[date]
    fisica: FisicaSaida
    # Vazio quando o papel de quem consulta não vê valores financeiros.
    financeira: Optional[FinanceiraSaida]


@router.get("/visao-integrada", response_model=VisaoIntegradaSaida)
def consultar(
    inicio: Optional[date] = None,
    fim: Optional[date] = None,
    acesso: Acesso = Depends(exigir_consulta_ao_programa),
    conexao: Connection = Depends(obter_conexao),
) -> visao_integrada.VisaoIntegrada:
    """Execução física (Gestão) e financeira (Financeiro) do programa, no mesmo período."""
    com_financeiro = ve_valores_financeiros(conexao, acesso.usuario_id, acesso.programa_id)
    try:
        visao = visao_integrada.visao_integrada(
            conexao, acesso.programa_id, inicio=inicio, fim=fim, com_financeiro=com_financeiro
        )
    except ErroDeCadastro as erro:
        raise HTTPException(status_code=erro.status, detail=erro.mensagem) from erro
    # A visão junta dados de dois módulos: cada consulta fica na trilha de auditoria.
    auditoria.registrar(
        conexao,
        usuario_id=acesso.usuario_id,
        acao="consulta_visao_integrada",
        alvo_tipo="programa",
        alvo_id=acesso.programa_id,
        descricao="Consulta à visão integrada do programa",
        detalhes={
            "inicio": inicio.isoformat() if inicio else None,
            "fim": fim.isoformat() if fim else None,
            "financeiro": com_financeiro,
            "vinculo": visao.financeira.vinculo if visao.financeira else None,
        },
    )
    conexao.commit()
    return visao
