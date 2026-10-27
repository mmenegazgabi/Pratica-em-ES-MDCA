"""Rotas de lançamentos.

GET   /lancamentos?status=pendente -> fila de aprovação (T-18 · US-04)
POST  /lancamentos                 -> cria com comprovante (T-12 · US-03)
GET   /lancamentos/{id}            -> consulta, com o motivo de rejeição (T-16)
PATCH /lancamentos/{id}/aprovar    -> aprova (T-15 · US-04)
PATCH /lancamentos/{id}/rejeitar   -> rejeita com motivo obrigatório (T-16 · US-04)

Aprovar e rejeitar notificam o autor do lançamento in-app (T-17 · US-04).

POST /lancamentos com upload de comprovante (T-12 · US-03).

Recebe os dados da despesa e a foto/PDF do comprovante no mesmo envio
(multipart/form-data). O lançamento nasce sempre como "Pendente de aprovação".

Ordem das verificações, para não deixar arquivo órfão no bucket:
1. comprovante presente           -> senão 400 "Comprovante obrigatório."
2. orçamento existe               -> senão 404
3. valor, categoria e data válidos -> senão 400
4. arquivo de tipo e tamanho aceitos (regras da T-11) -> senão 400 / 413
5. só então o arquivo vai para o R2 e o lançamento é registrado.
"""

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

if __package__ == "routers":
    from autenticacao import Papel, exigir_autenticacao, exigir_papel, obter_usuario
    from comprovantes import (
        TAMANHO_MAXIMO_BYTES,
        ArmazenamentoComprovantes,
        ComprovanteInvalido,
        gerar_chave,
        limpar_nome_original,
        validar_comprovante,
    )
    from notificacoes import caixa_de_notificacoes
    from orcamento import (
        AprovacaoInvalida,
        Lancamento,
        LancamentoInvalido,
        Orcamento,
        StatusLancamento,
    )
    from routers.comprovantes import obter_armazenamento
    from routers.orcamentos import _buscar_orcamento, _orcamentos
else:
    from ..autenticacao import Papel, exigir_autenticacao, exigir_papel, obter_usuario
    from ..comprovantes import (
        TAMANHO_MAXIMO_BYTES,
        ArmazenamentoComprovantes,
        ComprovanteInvalido,
        gerar_chave,
        limpar_nome_original,
        validar_comprovante,
    )
    from ..notificacoes import caixa_de_notificacoes
    from ..orcamento import (
        AprovacaoInvalida,
        Lancamento,
        LancamentoInvalido,
        Orcamento,
        StatusLancamento,
    )
    from .comprovantes import obter_armazenamento
    from .orcamentos import _buscar_orcamento, _orcamentos

router = APIRouter(
    prefix="/lancamentos",
    tags=["lancamentos"],
    dependencies=[Depends(exigir_autenticacao)],
)

DESCRICAO_STATUS = {
    StatusLancamento.PENDENTE: "Pendente de aprovação",
    StatusLancamento.APROVADO: "Aprovado",
    StatusLancamento.REJEITADO: "Rejeitado",
}


class ComprovanteDoLancamento(BaseModel):
    chave: str
    url: str
    nome_original: str
    content_type: str
    tamanho: int


class LancamentoCriado(BaseModel):
    id: str
    orcamento_id: str
    valor: float
    descricao: str
    categoria: str
    data_despesa: date
    status: str
    status_descricao: str
    comprovante: ComprovanteDoLancamento


@router.post("", response_model=LancamentoCriado, status_code=201)
async def criar_lancamento(
    orcamento_id: str = Form(...),
    valor: float = Form(...),
    descricao: str = Form(..., min_length=1, max_length=200),
    categoria: str = Form(...),
    data_despesa: date = Form(...),
    comprovante: Optional[UploadFile] = File(None),
    armazenamento: ArmazenamentoComprovantes = Depends(obter_armazenamento),
    autor_id: Optional[str] = Depends(obter_usuario),
) -> LancamentoCriado:
    # 1. Comprovante obrigatório
    conteudo = await comprovante.read(TAMANHO_MAXIMO_BYTES + 1) if comprovante else b""
    if not conteudo:
        raise HTTPException(status_code=400, detail="Comprovante obrigatório.")

    # 2 e 3. Orçamento e dados da despesa
    orcamento = _buscar_orcamento(orcamento_id)
    descricao = descricao.strip()
    if not descricao:
        raise HTTPException(status_code=400, detail="Descrição obrigatória.")
    try:
        orcamento.validar_lancamento(valor, categoria, data_despesa)
    except LancamentoInvalido as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro

    # 4. Tipo (imagem/PDF) e tamanho máximo do arquivo
    try:
        tipo = validar_comprovante(conteudo)
    except ComprovanteInvalido as erro:
        status = 413 if len(conteudo) > TAMANHO_MAXIMO_BYTES else 400
        raise HTTPException(status_code=status, detail=str(erro)) from erro

    # 5. Salva o arquivo e registra o lançamento como pendente
    chave = gerar_chave(tipo)
    nome_original = limpar_nome_original(comprovante.filename)
    try:
        armazenamento.salvar(chave, conteudo, tipo.content_type, nome_original)
    except Exception as erro:
        raise HTTPException(
            status_code=503, detail="Falha ao salvar o comprovante."
        ) from erro

    lancamento = orcamento.registrar_lancamento(
        Lancamento(
            valor=valor,
            status=StatusLancamento.PENDENTE,
            descricao=descricao,
            categoria=categoria,
            data_despesa=data_despesa,
            comprovante_chave=chave,
            autor_id=autor_id,
        )
    )

    return LancamentoCriado(
        id=lancamento.id,
        orcamento_id=orcamento.id,
        valor=lancamento.valor,
        descricao=lancamento.descricao,
        categoria=lancamento.categoria,
        data_despesa=data_despesa,
        status=lancamento.status.value,
        status_descricao=DESCRICAO_STATUS[lancamento.status],
        comprovante=ComprovanteDoLancamento(
            chave=chave,
            url=f"/{chave}",
            nome_original=nome_original,
            content_type=tipo.content_type,
            tamanho=len(conteudo),
        ),
    )


# --- PATCH /lancamentos/{id}/aprovar (T-15 · US-04) --------------------------


class LancamentoAprovado(BaseModel):
    id: str
    orcamento_id: str
    valor: float
    status: str
    status_descricao: str
    saldo_orcamento: float


def _buscar_orcamento_do_lancamento(lancamento_id: str) -> Orcamento:
    for orcamento in _orcamentos:
        if any(l.id == lancamento_id for l in orcamento.lancamentos):
            return orcamento
    raise HTTPException(status_code=404, detail="Lançamento não encontrado")


@router.patch("/{lancamento_id}/aprovar", response_model=LancamentoAprovado)
def aprovar_lancamento(
    lancamento_id: str,
    _papel: Papel = Depends(exigir_papel(Papel.COORDENACAO, Papel.DIRECAO)),
) -> LancamentoAprovado:
    orcamento = _buscar_orcamento_do_lancamento(lancamento_id)
    try:
        lancamento = orcamento.aprovar_lancamento(lancamento_id)
    except AprovacaoInvalida as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro

    caixa_de_notificacoes.notificar_resultado(lancamento)

    return LancamentoAprovado(
        id=lancamento.id,
        orcamento_id=orcamento.id,
        valor=lancamento.valor,
        status=lancamento.status.value,
        status_descricao=DESCRICAO_STATUS[lancamento.status],
        saldo_orcamento=orcamento.saldo,
    )


# --- PATCH /lancamentos/{id}/rejeitar e GET /lancamentos/{id} (T-16 · US-04) --

MOTIVO_TAMANHO_MAXIMO = 500


class RejeicaoPayload(BaseModel):
    motivo: Optional[str] = None


class LancamentoRejeitado(BaseModel):
    id: str
    orcamento_id: str
    valor: float
    status: str
    status_descricao: str
    motivo_rejeicao: str
    saldo_orcamento: float


class LancamentoDetalhe(BaseModel):
    id: str
    orcamento_id: str
    valor: float
    descricao: str
    categoria: str
    data_despesa: Optional[date]
    status: str
    status_descricao: str
    motivo_rejeicao: Optional[str]
    comprovante_url: Optional[str]


@router.patch("/{lancamento_id}/rejeitar", response_model=LancamentoRejeitado)
def rejeitar_lancamento(
    lancamento_id: str,
    payload: Optional[RejeicaoPayload] = Body(None),
    _papel: Papel = Depends(exigir_papel(Papel.COORDENACAO, Papel.DIRECAO)),
) -> LancamentoRejeitado:
    orcamento = _buscar_orcamento_do_lancamento(lancamento_id)

    motivo = ((payload.motivo if payload else None) or "").strip()
    if not motivo:
        raise HTTPException(status_code=400, detail="Motivo da rejeição é obrigatório.")
    if len(motivo) > MOTIVO_TAMANHO_MAXIMO:
        raise HTTPException(
            status_code=400,
            detail=f"Motivo da rejeição deve ter no máximo {MOTIVO_TAMANHO_MAXIMO} caracteres.",
        )

    try:
        lancamento = orcamento.rejeitar_lancamento(lancamento_id, motivo)
    except AprovacaoInvalida as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro
    except LancamentoInvalido as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro

    caixa_de_notificacoes.notificar_resultado(lancamento)

    return LancamentoRejeitado(
        id=lancamento.id,
        orcamento_id=orcamento.id,
        valor=lancamento.valor,
        status=lancamento.status.value,
        status_descricao=DESCRICAO_STATUS[lancamento.status],
        motivo_rejeicao=lancamento.motivo_rejeicao,
        saldo_orcamento=orcamento.saldo,
    )


@router.get("/{lancamento_id}", response_model=LancamentoDetalhe)
def obter_lancamento(lancamento_id: str) -> LancamentoDetalhe:
    """Consulta do lançamento por quem lançou: status e motivo da rejeição.

    Exige só autenticação (qualquer papel), porque quem lança é o educador.
    """
    orcamento = _buscar_orcamento_do_lancamento(lancamento_id)
    lancamento = next(l for l in orcamento.lancamentos if l.id == lancamento_id)
    return LancamentoDetalhe(
        id=lancamento.id,
        orcamento_id=orcamento.id,
        valor=lancamento.valor,
        descricao=lancamento.descricao,
        categoria=lancamento.categoria,
        data_despesa=lancamento.data_despesa,
        status=lancamento.status.value,
        status_descricao=DESCRICAO_STATUS[lancamento.status],
        motivo_rejeicao=lancamento.motivo_rejeicao,
        comprovante_url=(
            f"/{lancamento.comprovante_chave}" if lancamento.comprovante_chave else None
        ),
    )


# --- GET /lancamentos (T-18 · US-04) -----------------------------------------


class LancamentoNaFila(BaseModel):
    id: str
    orcamento_id: str
    projeto_id: str
    valor: float
    descricao: str
    categoria: str
    data_despesa: Optional[date]
    status: str
    status_descricao: str
    autor_id: Optional[str]
    comprovante_url: Optional[str]
    criado_em: datetime


@router.get("", response_model=List[LancamentoNaFila])
def listar_lancamentos(
    status: Optional[StatusLancamento] = Query(
        None, description="Filtra pelo status, ex.: pendente."
    ),
    _papel: Papel = Depends(exigir_papel(Papel.COORDENACAO, Papel.DIRECAO)),
) -> List[LancamentoNaFila]:
    """Lançamentos de todos os orçamentos, dos mais antigos para os mais novos.

    É a fila do painel de aprovação: só Coordenação e Direção veem os
    lançamentos de todo mundo.
    """
    itens = [
        (orcamento, lancamento)
        for orcamento in _orcamentos
        for lancamento in orcamento.lancamentos
        if status is None or lancamento.status == status
    ]
    itens.sort(key=lambda item: item[1].criado_em)
    return [
        LancamentoNaFila(
            id=lancamento.id,
            orcamento_id=orcamento.id,
            projeto_id=orcamento.projeto_id,
            valor=lancamento.valor,
            descricao=lancamento.descricao,
            categoria=lancamento.categoria,
            data_despesa=lancamento.data_despesa,
            status=lancamento.status.value,
            status_descricao=DESCRICAO_STATUS[lancamento.status],
            autor_id=lancamento.autor_id,
            comprovante_url=(
                f"/{lancamento.comprovante_chave}" if lancamento.comprovante_chave else None
            ),
            criado_em=lancamento.criado_em,
        )
        for orcamento, lancamento in itens
    ]
