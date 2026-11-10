"""Alertas de infrequência e busca ativa (T-59 · US-06).

Os alertas nascem sozinhos, quando uma chamada é registrada (``routers/atividades.py``).
Aqui ficam a consulta, as ações de acompanhamento e o encerramento.

Acesso (``Gestao/acesso.py``): a coordenação e a assistência social vinculadas ao
programa do alerta, e a administração. Toda negação vai para ``log_auditoria``; as ações
e o encerramento também.
"""

from datetime import date, datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Connection

from Financeiro.autenticacao import exigir_usuario
from Gestao import alertas, auditoria
from Gestao.acesso import Acesso, programas_com_alertas_visiveis, verificar_acompanhamento_de_alertas
from Gestao.banco import obter_conexao
from Gestao.erros import ErroDeCadastro

router = APIRouter(prefix="/gestao", tags=["gestao"])

ACAO_DE_BUSCA_ATIVA = "acao_busca_ativa"
ALERTA_ENCERRADO = "alerta_encerrado"


# --- Entradas e saídas ---------------------------------------------------------


class AcaoEntrada(BaseModel):
    tipo: Literal["contato_familia", "busca_ativa", "articulacao_rede", "revisao_contrato"]
    data: date
    resultado: Optional[str] = Field(default=None, max_length=5000)


class EncerramentoEntrada(BaseModel):
    justificativa: Optional[str] = Field(default=None, max_length=5000)


class _Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AcaoSaida(_Saida):
    id: str
    tipo: str
    tipo_nome: str
    data: date
    resultado: str
    responsavel_id: str
    responsavel: str
    criado_em: datetime


class AlertaResumoSaida(_Saida):
    id: str
    tipo: str
    titulo: str
    descricao: str
    programa_id: str
    pessoa_id: str
    pessoa: str
    turma_id: str
    turma: str
    responsavel_id: Optional[str]
    responsavel: Optional[str]
    # aberto ou encerrado.
    situacao: str
    faltas_consecutivas: int
    limite: int
    primeira_falta: date
    ultima_falta: date
    criado_em: datetime


class FaltaSaida(_Saida):
    atividade_id: str
    data: date


class AlertaSaida(AlertaResumoSaida):
    encerrado_em: Optional[datetime]
    encerrado_por: Optional[str]
    justificativa_encerramento: Optional[str]
    # Linha do tempo do acompanhamento, da ação mais recente para a mais antiga.
    acoes: List[AcaoSaida]
    # Encontros da sequência de faltas, do mais antigo para o mais recente (T-89).
    faltas: List[FaltaSaida]


# --- Apoio ---------------------------------------------------------------------


def _http(erro: ErroDeCadastro) -> HTTPException:
    if erro.codigo or erro.dados:
        return HTTPException(status_code=erro.status, detail=jsonable_encoder({"codigo": erro.codigo, "mensagem": erro.mensagem, **erro.dados}))
    return HTTPException(status_code=erro.status, detail=erro.mensagem)


def _acesso_ao_alerta(conexao: Connection, usuario_id: str, alerta_id: str, requisicao: Request) -> Acesso:
    programa_id = alertas.programa_do_alerta(conexao, alerta_id)
    if programa_id is None:
        raise HTTPException(status_code=404, detail=alertas.ALERTA_NAO_ENCONTRADO)
    return verificar_acompanhamento_de_alertas(conexao, usuario_id, programa_id, alvo_id=alerta_id, requisicao=requisicao)


# --- Rotas ---------------------------------------------------------------------


@router.get("/alertas", response_model=List[AlertaResumoSaida])
def listar_alertas(
    requisicao: Request,
    programa_id: Optional[str] = None,
    situacao: Optional[Literal["aberto", "encerrado"]] = None,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> List[alertas.Alerta]:
    """Alertas dos programas que a pessoa acompanha (administração: todos); abertos primeiro."""
    if programa_id:
        verificar_acompanhamento_de_alertas(conexao, usuario_id, programa_id, requisicao=requisicao)
        programas = [programa_id]
    else:
        programas = programas_com_alertas_visiveis(conexao, usuario_id)
    return alertas.listar(conexao, programas=programas, situacao=situacao)


@router.get("/alertas/{alerta_id}", response_model=AlertaSaida)
def obter_alerta(
    alerta_id: str,
    requisicao: Request,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> alertas.Alerta:
    _acesso_ao_alerta(conexao, usuario_id, alerta_id, requisicao)
    return alertas.obter(conexao, alerta_id)


@router.post("/alertas/{alerta_id}/acoes", response_model=AlertaSaida, status_code=201)
def registrar_acao(
    alerta_id: str,
    dados: AcaoEntrada,
    requisicao: Request,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> alertas.Alerta:
    """Ação de busca ativa ou acompanhamento: entra na linha do tempo do alerta."""
    acesso = _acesso_ao_alerta(conexao, usuario_id, alerta_id, requisicao)
    try:
        alerta = alertas.registrar_acao(
            conexao, alerta_id, tipo=dados.tipo, data=dados.data, resultado=dados.resultado, responsavel_id=acesso.usuario_id
        )
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    auditoria.registrar(
        conexao,
        usuario_id=acesso.usuario_id,
        acao=ACAO_DE_BUSCA_ATIVA,
        alvo_tipo="alerta",
        alvo_id=alerta_id,
        descricao=f"{alertas.TIPOS_DE_ACAO[dados.tipo]} registrada no acompanhamento",
        detalhes={"programa_id": acesso.programa_id, "pessoa_id": alerta.pessoa_id, "tipo": dados.tipo, "data": dados.data.isoformat()},
    )
    conexao.commit()
    return alerta


@router.post("/alertas/{alerta_id}/encerramento", response_model=AlertaSaida)
def encerrar_alerta(
    alerta_id: str,
    dados: EncerramentoEntrada,
    requisicao: Request,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> alertas.Alerta:
    """Encerra o acompanhamento; a justificativa é obrigatória (400 sem ela)."""
    acesso = _acesso_ao_alerta(conexao, usuario_id, alerta_id, requisicao)
    try:
        alerta = alertas.encerrar(conexao, alerta_id, justificativa=dados.justificativa, usuario_id=acesso.usuario_id)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    auditoria.registrar(
        conexao,
        usuario_id=acesso.usuario_id,
        acao=ALERTA_ENCERRADO,
        alvo_tipo="alerta",
        alvo_id=alerta_id,
        descricao="Alerta de infrequência encerrado com justificativa",
        detalhes={"programa_id": acesso.programa_id, "pessoa_id": alerta.pessoa_id},
    )
    conexao.commit()
    return alerta
