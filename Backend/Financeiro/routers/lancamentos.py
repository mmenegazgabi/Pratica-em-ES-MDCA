"""Rotas de lançamentos.

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

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

if __package__ == "routers":
    from autenticacao import Papel, exigir_autenticacao, exigir_papel
    from comprovantes import (
        TAMANHO_MAXIMO_BYTES,
        ArmazenamentoComprovantes,
        ComprovanteInvalido,
        gerar_chave,
        limpar_nome_original,
        validar_comprovante,
    )
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
    from ..autenticacao import Papel, exigir_autenticacao, exigir_papel
    from ..comprovantes import (
        TAMANHO_MAXIMO_BYTES,
        ArmazenamentoComprovantes,
        ComprovanteInvalido,
        gerar_chave,
        limpar_nome_original,
        validar_comprovante,
    )
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

    return LancamentoAprovado(
        id=lancamento.id,
        orcamento_id=orcamento.id,
        valor=lancamento.valor,
        status=lancamento.status.value,
        status_descricao=DESCRICAO_STATUS[lancamento.status],
        saldo_orcamento=orcamento.saldo,
    )
