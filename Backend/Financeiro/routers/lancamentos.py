"""Rotas de lançamentos.

GET   /lancamentos                 -> lista com filtros, mais antigos primeiro
POST  /lancamentos                 -> cria com comprovante (T-12 · US-03)
GET   /lancamentos/{id}            -> consulta, com o motivo de rejeição (T-16)
PATCH /lancamentos/{id}/aprovar    -> aprova (T-15 · US-04)
PATCH /lancamentos/{id}/rejeitar   -> rejeita com motivo obrigatório (T-16 · US-04)
PATCH /lancamentos/{id}/reenviar   -> corrige e reenvia despesa rejeitada
PATCH /lancamentos/{id}/conciliar  -> vincula a um item do extrato (T-21 · US-05)

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

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from pydantic import BaseModel

if __package__ == "routers":
    import auditoria
    from autenticacao import (
        Identidade,
        Papel,
        exigir_acesso_financeiro,
        exigir_papel,
        exigir_programa,
        exigir_usuario,
        obter_identidade,
        obter_usuario,
    )
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
        ConciliacaoInvalida,
        Lancamento,
        LancamentoInvalido,
        Orcamento,
        StatusLancamento,
    )
    from persistencia import obter_repositorio
    from routers.comprovantes import obter_armazenamento
    from projetos import buscar_projeto
    from routers.orcamentos import _buscar_orcamento
else:
    from .. import auditoria
    from ..autenticacao import (
        Identidade,
        Papel,
        exigir_acesso_financeiro,
        exigir_papel,
        exigir_programa,
        exigir_usuario,
        obter_identidade,
        obter_usuario,
    )
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
        ConciliacaoInvalida,
        Lancamento,
        LancamentoInvalido,
        Orcamento,
        StatusLancamento,
    )
    from ..persistencia import obter_repositorio
    from .comprovantes import obter_armazenamento
    from ..projetos import buscar_projeto
    from .orcamentos import _buscar_orcamento

router = APIRouter(
    prefix="/lancamentos",
    tags=["lancamentos"],
    dependencies=[Depends(exigir_acesso_financeiro)],
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


async def _ler_comprovante(comprovante: Optional[UploadFile]) -> bytes:
    conteudo = await comprovante.read(TAMANHO_MAXIMO_BYTES + 1) if comprovante else b""
    if not conteudo:
        raise HTTPException(status_code=400, detail="Comprovante obrigatório.")
    return conteudo


def _guardar_comprovante(
    conteudo: bytes, filename: Optional[str], armazenamento: ArmazenamentoComprovantes
) -> tuple[str, str, str, int]:
    """Valida tipo e tamanho e salva no armazenamento."""
    try:
        tipo = validar_comprovante(conteudo)
    except ComprovanteInvalido as erro:
        status = 413 if len(conteudo) > TAMANHO_MAXIMO_BYTES else 400
        raise HTTPException(status_code=status, detail=str(erro)) from erro

    chave = gerar_chave(tipo)
    nome_original = limpar_nome_original(filename)
    try:
        armazenamento.salvar(chave, conteudo, tipo.content_type, nome_original)
    except Exception as erro:
        raise HTTPException(
            status_code=503, detail="Falha ao salvar o comprovante."
        ) from erro
    return chave, tipo.content_type, nome_original, len(conteudo)


async def _receber_comprovante(
    comprovante: Optional[UploadFile], armazenamento: ArmazenamentoComprovantes
) -> tuple[str, str, str, int]:
    """Lê, valida e salva o comprovante -> (chave, content_type, nome_original, tamanho)."""
    conteudo = await _ler_comprovante(comprovante)
    return _guardar_comprovante(conteudo, comprovante.filename, armazenamento)


def _validar_dados_da_despesa(
    orcamento: Orcamento,
    valor: float,
    descricao: str,
    categoria: str,
    data_despesa: date,
) -> str:
    """Devolve a descrição sem espaços sobrando; 400 se algo for inválido."""
    descricao = descricao.strip()
    if not descricao:
        raise HTTPException(status_code=400, detail="Descrição obrigatória.")
    try:
        orcamento.validar_lancamento(valor, categoria, data_despesa)
    except LancamentoInvalido as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    return descricao


def _criar_lancamento(
    repositorio,
    orcamento: Orcamento,
    valor: float,
    descricao: str,
    categoria: str,
    data_despesa: date,
    comprovante_chave: str,
    content_type: str,
    nome_original: str,
    tamanho: int,
    autor_id: Optional[str],
) -> LancamentoCriado:
    """Registra o lançamento como pendente e monta a resposta."""
    lancamento = orcamento.registrar_lancamento(
        Lancamento(
            valor=valor,
            status=StatusLancamento.PENDENTE,
            descricao=descricao,
            categoria=categoria,
            data_despesa=data_despesa,
            comprovante_chave=comprovante_chave,
            autor_id=autor_id,
        )
    )
    repositorio.salvar_lancamento(orcamento, lancamento)
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
            chave=comprovante_chave,
            url=f"/{comprovante_chave}",
            nome_original=nome_original,
            content_type=content_type,
            tamanho=tamanho,
        ),
    )


def auditar_lancamento(
    repositorio,
    identidade: Optional[Identidade],
    acao: str,
    orcamento: Orcamento,
    lancamento: Lancamento,
    *extra: Optional[str],
    detalhes: Optional[dict] = None,
) -> None:
    """T-34: registra a ação no lançamento, na mesma transação (antes do confirmar)."""
    projeto = buscar_projeto(orcamento.projeto_id, repositorio)
    auditoria.registrar(
        repositorio,
        identidade,
        acao,
        alvo_tipo="lancamento",
        alvo_id=lancamento.id,
        descricao=auditoria.alvo_lancamento(lancamento, projeto.nome if projeto else None, *extra),
        detalhes={
            "orcamento_id": orcamento.id,
            "projeto_id": orcamento.projeto_id,
            "valor": lancamento.valor,
            "categoria": lancamento.categoria,
            "status": lancamento.status.value,
            **(detalhes or {}),
        },
    )


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
    repositorio=Depends(obter_repositorio),
    identidade: Identidade = Depends(exigir_acesso_financeiro),
) -> LancamentoCriado:
    # 1. Comprovante obrigatório
    conteudo = await _ler_comprovante(comprovante)

    # 2 e 3. Orçamento e dados da despesa (sem trava: o envio do arquivo para o R2
    # não deve segurar o orçamento)
    orcamento = _buscar_orcamento(repositorio, orcamento_id)
    exigir_programa(identidade, orcamento.projeto_id)
    descricao = _validar_dados_da_despesa(
        orcamento, valor, descricao, categoria, data_despesa
    )

    # 4. Tipo e tamanho do arquivo, e salva
    chave, content_type, nome_original, tamanho = _guardar_comprovante(
        conteudo, comprovante.filename, armazenamento
    )

    # 5. Relê com trava e confere de novo: a coordenação pode ter mudado as categorias
    # ou a vigência enquanto o arquivo subia. Aí registra como pendente.
    orcamento = _buscar_orcamento(repositorio, orcamento_id, para_alterar=True)
    _validar_dados_da_despesa(orcamento, valor, descricao, categoria, data_despesa)
    criado = _criar_lancamento(
        repositorio, orcamento, valor, descricao, categoria, data_despesa,
        chave, content_type, nome_original, tamanho, autor_id,
    )
    lancamento = next(l for l in orcamento.lancamentos if l.id == criado.id)
    auditar_lancamento(repositorio, identidade, "criar_lancamento", orcamento, lancamento)
    repositorio.confirmar()
    return criado


# --- PATCH /lancamentos/{id}/aprovar (T-15 · US-04) --------------------------


class LancamentoAprovado(BaseModel):
    id: str
    orcamento_id: str
    valor: float
    status: str
    status_descricao: str
    saldo_orcamento: float


def _buscar_orcamento_do_lancamento(
    repositorio, lancamento_id: str, para_alterar: bool = False
) -> Orcamento:
    orcamento = repositorio.buscar_orcamento_do_lancamento(
        lancamento_id, para_alterar=para_alterar
    )
    if orcamento is None:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    return orcamento


@router.patch("/{lancamento_id}/aprovar", response_model=LancamentoAprovado)
def aprovar_lancamento(
    lancamento_id: str,
    _papel: Papel = Depends(exigir_papel(Papel.COORDENACAO, Papel.DIRECAO)),
    repositorio=Depends(obter_repositorio),
    identidade: Identidade = Depends(obter_identidade),
) -> LancamentoAprovado:
    orcamento = _buscar_orcamento_do_lancamento(repositorio, lancamento_id, para_alterar=True)
    try:
        lancamento = orcamento.aprovar_lancamento(lancamento_id)
    except AprovacaoInvalida as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro

    repositorio.salvar_lancamento(orcamento, lancamento)
    repositorio.notificar_resultado(lancamento)
    auditar_lancamento(
        repositorio, identidade, "aprovar_lancamento", orcamento, lancamento,
        detalhes={"saldo_orcamento": orcamento.saldo},
    )
    repositorio.confirmar()

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
    motivos_rejeicao_anteriores: List[str]
    comprovante_url: Optional[str]
    conciliado: bool
    referencia_extrato: Optional[str]


@router.patch("/{lancamento_id}/rejeitar", response_model=LancamentoRejeitado)
def rejeitar_lancamento(
    lancamento_id: str,
    payload: Optional[RejeicaoPayload] = Body(None),
    _papel: Papel = Depends(exigir_papel(Papel.COORDENACAO, Papel.DIRECAO)),
    repositorio=Depends(obter_repositorio),
    identidade: Identidade = Depends(obter_identidade),
) -> LancamentoRejeitado:
    orcamento = _buscar_orcamento_do_lancamento(repositorio, lancamento_id, para_alterar=True)

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

    repositorio.salvar_lancamento(orcamento, lancamento)
    repositorio.notificar_resultado(lancamento)
    auditar_lancamento(
        repositorio, identidade, "rejeitar_lancamento", orcamento, lancamento,
        detalhes={"motivo": lancamento.motivo_rejeicao},
    )
    repositorio.confirmar()

    return LancamentoRejeitado(
        id=lancamento.id,
        orcamento_id=orcamento.id,
        valor=lancamento.valor,
        status=lancamento.status.value,
        status_descricao=DESCRICAO_STATUS[lancamento.status],
        motivo_rejeicao=lancamento.motivo_rejeicao,
        saldo_orcamento=orcamento.saldo,
    )


class LancamentoResumo(BaseModel):
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
    motivo_rejeicao: Optional[str]
    conciliado: bool
    referencia_extrato: Optional[str]
    comprovante_url: Optional[str]
    criado_em: datetime
    aprovado_em: Optional[datetime]


# GET /lancamentos precisa vir antes de GET /lancamentos/{id}.
@router.get("", response_model=List[LancamentoResumo])
def listar_lancamentos(
    status: Optional[StatusLancamento] = Query(
        None, description="Filtra pelo status, ex.: pendente."
    ),
    orcamento_id: Optional[str] = Query(None),
    conciliado: Optional[bool] = Query(None),
    meus: bool = Query(False, description="Só os lançamentos do usuário informado."),
    papel: Papel = Depends(
        exigir_papel(
            Papel.COORDENACAO,
            Papel.DIRECAO,
            Papel.VOLUNTARIO_FINANCEIRO,
            Papel.EDUCADOR,
        )
    ),
    usuario: Optional[str] = Depends(obter_usuario),
    repositorio=Depends(obter_repositorio),
    identidade: Identidade = Depends(exigir_acesso_financeiro),
) -> List[LancamentoResumo]:
    """Lançamentos de todos os orçamentos, dos mais antigos para os mais novos.

    Ordem da fila de aprovação: quem espera há mais tempo vem primeiro.

    Educador só enxerga os próprios; `meus=true` aplica o mesmo a qualquer papel.
    """
    so_do_usuario = meus or papel == Papel.EDUCADOR
    if so_do_usuario and usuario is None:
        raise HTTPException(
            status_code=400, detail="Identificação do usuário obrigatória."
        )

    itens = [
        (orcamento, lancamento)
        for orcamento in repositorio.listar_orcamentos()
        if (orcamento_id is None or orcamento.id == orcamento_id)
        and identidade.ve_programa(orcamento.projeto_id)
        for lancamento in orcamento.lancamentos
        if (status is None or lancamento.status == status)
        and (conciliado is None or lancamento.conciliado == conciliado)
        and (not so_do_usuario or lancamento.autor_id == usuario)
    ]
    itens.sort(key=lambda item: item[1].criado_em)
    return [
        LancamentoResumo(
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
            motivo_rejeicao=lancamento.motivo_rejeicao,
            conciliado=lancamento.conciliado,
            referencia_extrato=lancamento.referencia_extrato,
            comprovante_url=(
                f"/{lancamento.comprovante_chave}" if lancamento.comprovante_chave else None
            ),
            criado_em=lancamento.criado_em,
            aprovado_em=lancamento.aprovado_em,
        )
        for orcamento, lancamento in itens
    ]


@router.get("/{lancamento_id}", response_model=LancamentoDetalhe)
def obter_lancamento(
    lancamento_id: str,
    repositorio=Depends(obter_repositorio),
    identidade: Identidade = Depends(exigir_acesso_financeiro),
) -> LancamentoDetalhe:
    """Consulta do lançamento por quem lançou: status e motivo da rejeição.

    Qualquer papel do Financeiro, porque quem lança é o educador. Com o login, quem só
    é educador vê apenas os próprios lançamentos (o de outra pessoa responde como
    inexistente).
    """
    orcamento = _buscar_orcamento_do_lancamento(repositorio, lancamento_id)
    lancamento = next(l for l in orcamento.lancamentos if l.id == lancamento_id)
    if identidade.programas is not None and lancamento.autor_id != identidade.usuario_id:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    return _detalhe(orcamento, lancamento)


def _detalhe(orcamento: Orcamento, lancamento: Lancamento) -> LancamentoDetalhe:
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
        motivos_rejeicao_anteriores=list(lancamento.motivos_rejeicao_anteriores),
        comprovante_url=(
            f"/{lancamento.comprovante_chave}" if lancamento.comprovante_chave else None
        ),
        conciliado=lancamento.conciliado,
        referencia_extrato=lancamento.referencia_extrato,
    )


# --- PATCH /lancamentos/{id}/reenviar (redesign Financeiro) -----------------


@router.patch("/{lancamento_id}/reenviar", response_model=LancamentoDetalhe)
async def reenviar_lancamento(
    lancamento_id: str,
    valor: float = Form(...),
    descricao: str = Form(..., min_length=1, max_length=200),
    categoria: str = Form(...),
    data_despesa: date = Form(...),
    comprovante: Optional[UploadFile] = File(None),
    armazenamento: ArmazenamentoComprovantes = Depends(obter_armazenamento),
    autor_id: str = Depends(exigir_usuario),
    repositorio=Depends(obter_repositorio),
    identidade: Identidade = Depends(obter_identidade),
) -> LancamentoDetalhe:
    def conferir(orcamento: Orcamento) -> str:
        lancamento = next(l for l in orcamento.lancamentos if l.id == lancamento_id)
        if lancamento.autor_id != autor_id:
            raise HTTPException(status_code=404, detail="Lançamento não encontrado")
        if lancamento.status != StatusLancamento.REJEITADO:
            raise HTTPException(
                status_code=409, detail="Só despesas rejeitadas podem ser reenviadas"
            )
        return _validar_dados_da_despesa(
            orcamento, valor, descricao, categoria, data_despesa
        )

    # Valida tudo antes de salvar a foto nova, para não deixar arquivo órfão; sem
    # trava, para o envio ao R2 não segurar o orçamento.
    descricao = conferir(_buscar_orcamento_do_lancamento(repositorio, lancamento_id))
    chave = None
    if comprovante is not None:
        chave, *_ = await _receber_comprovante(comprovante, armazenamento)
    # Relê com trava e confere de novo antes de alterar (pode ter mudado no meio).
    orcamento = _buscar_orcamento_do_lancamento(repositorio, lancamento_id, para_alterar=True)
    descricao = conferir(orcamento)
    try:
        lancamento = orcamento.reenviar_lancamento(
            lancamento_id,
            valor=valor,
            descricao=descricao,
            categoria=categoria,
            data_despesa=data_despesa,
            comprovante_chave=chave,
        )
    except AprovacaoInvalida as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro
    except LancamentoInvalido as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    repositorio.salvar_lancamento(orcamento, lancamento)
    auditar_lancamento(
        repositorio, identidade, "reenviar_lancamento", orcamento, lancamento,
        detalhes={"comprovante_novo": chave is not None},
    )
    repositorio.confirmar()
    return _detalhe(orcamento, lancamento)


# --- PATCH /lancamentos/{id}/conciliar (T-21 · US-05) ------------------------

REFERENCIA_TAMANHO_MAXIMO = 200


class ConciliacaoPayload(BaseModel):
    referencia_extrato: Optional[str] = None


class LancamentoConciliado(BaseModel):
    id: str
    orcamento_id: str
    valor: float
    status: str
    status_descricao: str
    conciliado: bool
    referencia_extrato: str


@router.patch("/{lancamento_id}/conciliar", response_model=LancamentoConciliado)
def conciliar_lancamento(
    lancamento_id: str,
    payload: Optional[ConciliacaoPayload] = Body(None),
    _papel: Papel = Depends(exigir_papel(Papel.VOLUNTARIO_FINANCEIRO)),
    repositorio=Depends(obter_repositorio),
    identidade: Identidade = Depends(obter_identidade),
) -> LancamentoConciliado:
    """Marca o lançamento como conciliado com um item do extrato bancário.

    Repetir com a mesma referência é idempotente (200, nada muda); com outra
    referência retorna 409.
    """
    orcamento = _buscar_orcamento_do_lancamento(repositorio, lancamento_id, para_alterar=True)

    referencia = ((payload.referencia_extrato if payload else None) or "").strip()
    if not referencia:
        raise HTTPException(status_code=400, detail="Referência do extrato é obrigatória.")
    if len(referencia) > REFERENCIA_TAMANHO_MAXIMO:
        raise HTTPException(
            status_code=400,
            detail=f"Referência do extrato deve ter no máximo {REFERENCIA_TAMANHO_MAXIMO} caracteres.",
        )

    ja_conciliado = next(l for l in orcamento.lancamentos if l.id == lancamento_id).conciliado
    try:
        lancamento = orcamento.conciliar_lancamento(lancamento_id, referencia)
    except ConciliacaoInvalida as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro
    except LancamentoInvalido as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro

    repositorio.salvar_lancamento(orcamento, lancamento)
    if not ja_conciliado:  # repetir a mesma referência não muda nada nem gera registro
        auditar_lancamento(
            repositorio, identidade, "conciliar_lancamento", orcamento, lancamento,
            referencia, detalhes={"referencia_extrato": referencia},
        )
    repositorio.confirmar()

    return LancamentoConciliado(
        id=lancamento.id,
        orcamento_id=orcamento.id,
        valor=lancamento.valor,
        status=lancamento.status.value,
        status_descricao=DESCRICAO_STATUS[lancamento.status],
        conciliado=lancamento.conciliado,
        referencia_extrato=lancamento.referencia_extrato,
    )
