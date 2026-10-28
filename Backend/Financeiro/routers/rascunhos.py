"""Rascunhos de despesa: foto agora, dados depois.

POST /rascunhos                    -> guarda só o comprovante
GET  /rascunhos                    -> rascunhos de quem está logado
POST /rascunhos/{id}/completar     -> vira lançamento pendente e o rascunho some

Quem está logado vem do cabeçalho provisório ``X-Usuario-Id`` (até a US-08).
"""

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

if __package__ == "routers":
    from autenticacao import exigir_usuario
    from comprovantes import ArmazenamentoComprovantes
    from rascunhos import Rascunho, RascunhoNaoEncontrado, caixa_de_rascunhos
    from routers.comprovantes import obter_armazenamento
    from routers.lancamentos import (
        LancamentoCriado,
        _criar_lancamento,
        _receber_comprovante,
        _validar_dados_da_despesa,
    )
    from routers.orcamentos import _buscar_orcamento
else:
    from ..autenticacao import exigir_usuario
    from ..comprovantes import ArmazenamentoComprovantes
    from ..rascunhos import Rascunho, RascunhoNaoEncontrado, caixa_de_rascunhos
    from .comprovantes import obter_armazenamento
    from .lancamentos import (
        LancamentoCriado,
        _criar_lancamento,
        _receber_comprovante,
        _validar_dados_da_despesa,
    )
    from .orcamentos import _buscar_orcamento

router = APIRouter(prefix="/rascunhos", tags=["rascunhos"])


class RascunhoSaida(BaseModel):
    id: str
    criado_em: datetime
    comprovante_url: str
    nome_original: str
    content_type: str
    tamanho: int


def _saida(rascunho: Rascunho) -> RascunhoSaida:
    return RascunhoSaida(
        id=rascunho.id,
        criado_em=rascunho.criado_em,
        comprovante_url=f"/{rascunho.comprovante_chave}",
        nome_original=rascunho.nome_original,
        content_type=rascunho.content_type,
        tamanho=rascunho.tamanho,
    )


@router.post("", response_model=RascunhoSaida, status_code=201)
async def criar_rascunho(
    comprovante: Optional[UploadFile] = File(None),
    armazenamento: ArmazenamentoComprovantes = Depends(obter_armazenamento),
    autor_id: str = Depends(exigir_usuario),
) -> RascunhoSaida:
    chave, content_type, nome_original, tamanho = await _receber_comprovante(
        comprovante, armazenamento
    )
    rascunho = caixa_de_rascunhos.criar(
        Rascunho(
            autor_id=autor_id,
            comprovante_chave=chave,
            nome_original=nome_original,
            content_type=content_type,
            tamanho=tamanho,
        )
    )
    return _saida(rascunho)


@router.get("", response_model=List[RascunhoSaida])
def listar_rascunhos(autor_id: str = Depends(exigir_usuario)) -> List[RascunhoSaida]:
    return [_saida(r) for r in caixa_de_rascunhos.do_autor(autor_id)]


@router.post("/{rascunho_id}/completar", response_model=LancamentoCriado, status_code=201)
def completar_rascunho(
    rascunho_id: str,
    orcamento_id: str = Form(...),
    valor: float = Form(...),
    descricao: str = Form(..., min_length=1, max_length=200),
    categoria: str = Form(...),
    data_despesa: date = Form(...),
    autor_id: str = Depends(exigir_usuario),
) -> LancamentoCriado:
    rascunho = next(
        (r for r in caixa_de_rascunhos.do_autor(autor_id) if r.id == rascunho_id), None
    )
    if rascunho is None:
        raise HTTPException(status_code=404, detail="Rascunho não encontrado")

    # Valida antes de retirar: dado inválido não pode consumir o rascunho.
    orcamento = _buscar_orcamento(orcamento_id)
    descricao = _validar_dados_da_despesa(
        orcamento, valor, descricao, categoria, data_despesa
    )
    try:
        caixa_de_rascunhos.retirar(rascunho_id, autor_id)
    except RascunhoNaoEncontrado as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro

    return _criar_lancamento(
        orcamento, valor, descricao, categoria, data_despesa,
        rascunho.comprovante_chave, rascunho.content_type,
        rascunho.nome_original, rascunho.tamanho, autor_id,
    )
