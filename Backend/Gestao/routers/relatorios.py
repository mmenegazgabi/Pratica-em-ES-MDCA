"""Rotas do relatório técnico (T-75 · US-11).

- ``POST /gestao/relatorios-tecnicos/previa``: o conteúdo do relatório (as mesmas seções
  e linhas do arquivo) e as pendências, para a tela mostrar antes da versão final.
- ``POST /gestao/relatorios-tecnicos/exportacao?formato=pdf|xlsx``: o arquivo. Cada
  exportação fica na trilha de auditoria (``relatorio_tecnico_emitido``).
- ``GET /gestao/relatorios-tecnicos/emissoes``: o histórico, lido da trilha.

Quem emite: ``acesso.verificar_emissao_de_relatorio`` (coordenação e administração nas
duas finalidades; direção só para circulação externa).
"""

from datetime import date, datetime
from typing import List, Literal, Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Connection

from Financeiro.autenticacao import exigir_usuario
from Gestao import auditoria, indicadores, relatorio_tecnico
from Gestao.acesso import finalidades_do_relatorio, programas_consultaveis, ve_valores_financeiros, verificar_emissao_de_relatorio
from Gestao.banco import obter_conexao
from Gestao.erros import ErroDeCadastro
from Shared import relatorios

router = APIRouter(prefix="/gestao/relatorios-tecnicos", tags=["gestao"])

EMITIDO = "relatorio_tecnico_emitido"
TIPOS = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class PedidoDeRelatorio(BaseModel):
    programa_id: str = Field(min_length=1, max_length=100)
    inicio: Optional[date] = None
    fim: Optional[date] = None
    finalidade: Literal["interna", "externa"]
    secoes: List[str] = Field(max_length=10)
    # Ids das evidências escolhidas; vazio (null) = todas as do período.
    evidencias: Optional[List[str]] = Field(default=None, max_length=500)


class SecaoSaida(BaseModel):
    titulo: str
    colunas: List[str]
    linhas: List[List[str]]
    nota: Optional[str]
    vazio: str


class PendenciaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tipo: str
    descricao: str
    quantidade: int


class EvidenciaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    data: date
    turma: str
    liberada_externa: bool


class PeriodoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    inicio: date
    fim: date
    fechado: bool


class PreviaSaida(BaseModel):
    programa_id: str
    programa: str
    periodo: PeriodoSaida
    finalidade: str
    secoes: List[str]
    titulo: str
    cabecalho: List[List[str]]
    conteudo: List[SecaoSaida]
    rodape: str
    pendencias: List[PendenciaSaida]
    evidencias_disponiveis: List[EvidenciaSaida]
    # Finalidades que quem consulta pode emitir, para a tela oferecer só essas.
    finalidades_permitidas: List[str]


class EmissaoSaida(BaseModel):
    momento: datetime
    usuario: Optional[str]
    programa_id: Optional[str]
    programa: Optional[str]
    inicio: Optional[date]
    fim: Optional[date]
    finalidade: Optional[str]
    secoes: List[str]
    formato: Optional[str]


def _nome(conexao: Connection, usuario_id: str) -> str:
    return conexao.execute(sa.text("SELECT nome FROM usuarios WHERE id = :id"), {"id": usuario_id}).scalar_one_or_none() or ""


def _montar(pedido: PedidoDeRelatorio, usuario_id: str, conexao: Connection, requisicao: Request) -> relatorio_tecnico.Relatorio:
    verificar_emissao_de_relatorio(conexao, usuario_id, pedido.programa_id, pedido.finalidade, requisicao=requisicao)
    try:
        recorte = indicadores.periodo(pedido.inicio, pedido.fim, date.today())
        return relatorio_tecnico.montar(
            conexao,
            pedido.programa_id,
            recorte,
            finalidade=pedido.finalidade,
            secoes=pedido.secoes,
            evidencias_escolhidas=pedido.evidencias,
            com_financeiro=ve_valores_financeiros(conexao, usuario_id, pedido.programa_id),
            emitido_por=_nome(conexao, usuario_id),
        )
    except ErroDeCadastro as erro:
        raise HTTPException(status_code=erro.status, detail=erro.mensagem) from erro


@router.post("/previa", response_model=PreviaSaida)
def previa(
    pedido: PedidoDeRelatorio,
    requisicao: Request,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> PreviaSaida:
    """O mesmo conteúdo do arquivo, já minimizado pela finalidade, com as pendências."""
    relatorio = _montar(pedido, usuario_id, conexao, requisicao)
    doc = relatorio.documento
    return PreviaSaida(
        programa_id=relatorio.programa_id,
        programa=relatorio.programa,
        periodo=PeriodoSaida.model_validate(relatorio.periodo),
        finalidade=relatorio.finalidade,
        secoes=relatorio.secoes,
        titulo=doc.titulo,
        cabecalho=[[r, v] for r, v in doc.cabecalho],
        conteudo=[
            SecaoSaida(titulo=s.titulo, colunas=list(s.colunas), linhas=[list(l) for l in s.linhas], nota=s.nota, vazio=s.vazio)
            for s in doc.secoes
        ],
        rodape=doc.rodape,
        pendencias=[PendenciaSaida.model_validate(p) for p in relatorio.pendencias],
        evidencias_disponiveis=[EvidenciaSaida.model_validate(e) for e in relatorio.evidencias_disponiveis],
        finalidades_permitidas=sorted(finalidades_do_relatorio(conexao, usuario_id)),
    )


@router.post("/exportacao")
def exportar(
    pedido: PedidoDeRelatorio,
    requisicao: Request,
    formato: Literal["pdf", "xlsx"] = "pdf",
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> Response:
    """O arquivo do relatório. A emissão fica na trilha, com a configuração usada."""
    relatorio = _montar(pedido, usuario_id, conexao, requisicao)
    gerar = relatorios.gerar_pdf if formato == "pdf" else relatorios.gerar_xlsx
    arquivo = gerar(relatorio.documento)
    auditoria.registrar(
        conexao,
        usuario_id=usuario_id,
        acao=EMITIDO,
        alvo_tipo="programa",
        alvo_id=relatorio.programa_id,
        descricao=f"Emissão do relatório técnico ({relatorio_tecnico.FINALIDADES[relatorio.finalidade]}, {formato.upper()})",
        detalhes={
            "inicio": relatorio.periodo.inicio.isoformat(),
            "fim": relatorio.periodo.fim.isoformat(),
            "finalidade": relatorio.finalidade,
            "secoes": relatorio.secoes,
            "formato": formato,
            "evidencias": pedido.evidencias,
            "pendencias": {p.tipo: p.quantidade for p in relatorio.pendencias},
        },
    )
    conexao.commit()
    nome = relatorios.nome_do_arquivo(relatorio.documento, formato)
    return Response(
        content=arquivo,
        media_type=TIPOS[formato],
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.get("/emissoes", response_model=List[EmissaoSaida])
def emissoes(
    programa_id: Optional[str] = None,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
) -> List[EmissaoSaida]:
    """Relatórios emitidos nos programas que a pessoa consulta (mais recentes primeiro)."""
    if not finalidades_do_relatorio(conexao, usuario_id):
        raise HTTPException(status_code=403, detail="Seu perfil não emite relatórios técnicos.")
    visiveis = programas_consultaveis(conexao, usuario_id)
    filtros, parametros = ["l.acao = :acao"], {"acao": EMITIDO}
    if visiveis is not None:
        filtros.append("l.alvo_id = ANY(:visiveis)")
        parametros["visiveis"] = visiveis
    if programa_id:
        filtros.append("l.alvo_id = :programa")
        parametros["programa"] = programa_id
    linhas = conexao.execute(
        sa.text(
            f"""
            SELECT l.ocorrido_em AS momento, u.nome AS usuario, l.alvo_id AS programa_id, p.nome AS programa, l.detalhes
            FROM log_auditoria l
            LEFT JOIN usuarios u ON u.id = l.usuario_id
            LEFT JOIN projetos p ON p.id = l.alvo_id
            WHERE {' AND '.join(filtros)}
            ORDER BY l.ocorrido_em DESC, l.id DESC
            LIMIT 100
            """
        ),
        parametros,
    )
    resultado = []
    for l in linhas:
        d = l.detalhes or {}
        resultado.append(
            EmissaoSaida(
                momento=l.momento,
                usuario=l.usuario,
                programa_id=l.programa_id,
                programa=l.programa,
                inicio=d.get("inicio"),
                fim=d.get("fim"),
                finalidade=d.get("finalidade"),
                secoes=d.get("secoes") or [],
                formato=d.get("formato"),
            )
        )
    return resultado
