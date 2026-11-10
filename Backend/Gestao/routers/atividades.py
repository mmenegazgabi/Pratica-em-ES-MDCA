"""Agenda, encontros com chamada e evidências de um programa (T-56 · US-05).

Acesso (``Gestao/acesso.py``):

- agenda (sem nomes de pessoas): quem consulta o programa;
- registrar encontro com chamada e enviar evidência: coordenação e educadores vinculados
  ao programa, e a administração;
- detalhe do encontro (com a chamada) e download de evidência: a regra dos cadastros de
  pessoas da US-03, então a direção recebe 403. Todo download vai para a auditoria.

Envios da fila offline: o mesmo ``registro_id`` recebido de novo responde 200 com o que
já estava gravado, sem duplicar; o primeiro envio responde 201.

O arquivo da evidência usa o armazenamento dos comprovantes do Financeiro (mesmo bucket
privado do R2, validação pelo conteúdo do arquivo, limite de 5 MB), numa pasta própria
da Gestão.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Connection

from Financeiro.comprovantes import (
    TAMANHO_MAXIMO_BYTES,
    ArmazenamentoComprovantes,
    ComprovanteInvalido,
    limpar_nome_original,
    validar_comprovante,
)
from Financeiro.routers.comprovantes import obter_armazenamento
from Gestao import alertas, atividades, auditoria
from Gestao.acesso import (
    Acesso,
    exigir_consulta_ao_programa,
    exigir_registro_de_atividade,
    verificar_acesso_a_pessoas,
)
from Gestao.banco import obter_conexao
from Gestao.erros import ErroDeCadastro

router = APIRouter(prefix="/gestao/programas/{programa_id}", tags=["gestao"])

DOWNLOAD_DE_EVIDENCIA = "download_evidencia"


# --- Entradas ------------------------------------------------------------------


class PresencaEntrada(BaseModel):
    pessoa_id: str = Field(min_length=1, max_length=100)
    presente: bool
    justificativa: Optional[str] = Field(default=None, max_length=1000)


class AtividadeEntrada(BaseModel):
    # Gerado no aparelho; reenviar o mesmo valor não duplica o encontro.
    registro_id: str = Field(min_length=1, max_length=100)
    data: date
    conteudo: str = Field(max_length=5000)
    # Vazio: quem envia é o educador do encontro.
    educador_id: Optional[str] = Field(default=None, max_length=100)
    observacao: Optional[str] = Field(default=None, max_length=5000)
    presencas: List[PresencaEntrada] = Field(max_length=500)


# --- Saídas --------------------------------------------------------------------


class _Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EncontroSaida(_Saida):
    data: date
    turma_id: str
    turma: str
    espaco: str
    responsavel_id: str
    responsavel: str
    hora_inicio: str
    hora_fim: str
    # Falso para um encontro registrado num dia fora da agenda da turma.
    previsto: bool
    # Encontros já registrados nesse dia; vazio enquanto a chamada não foi feita.
    atividades: List[str]


class PresencaSaida(_Saida):
    pessoa_id: str
    pessoa: str
    presente: bool
    justificativa: Optional[str]


class EvidenciaSaida(_Saida):
    id: str
    registro_id: str
    atividade_id: str
    programa_id: str
    autor_id: str
    autor: str
    data: date
    descricao: Optional[str]
    nome_arquivo: str
    content_type: str
    tamanho: int


class AtividadeSaida(_Saida):
    id: str
    registro_id: str
    programa_id: str
    turma_id: str
    turma: str
    data: date
    educador_id: str
    educador: str
    conteudo: str
    observacao: Optional[str]
    presentes: int
    ausentes: int
    chamada: List[PresencaSaida]
    evidencias: List[EvidenciaSaida]


# --- Apoio ---------------------------------------------------------------------


def _http(erro: ErroDeCadastro) -> HTTPException:
    if erro.codigo or erro.dados:
        detalhe = jsonable_encoder({"codigo": erro.codigo, "mensagem": erro.mensagem, **erro.dados})
    else:
        detalhe = erro.mensagem
    return HTTPException(status_code=erro.status, detail=detalhe)


def _encontro(encontro: atividades.Encontro) -> EncontroSaida:
    return EncontroSaida(
        **{
            **encontro.__dict__,
            "hora_inicio": encontro.hora_inicio.strftime("%H:%M"),
            "hora_fim": encontro.hora_fim.strftime("%H:%M"),
        }
    )


def _atividade_visivel(conexao, acesso: Acesso, atividade_id: str, requisicao: Request) -> atividades.Atividade:
    try:
        atividade = atividades.obter_atividade(conexao, acesso.programa_id, atividade_id)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    # A chamada traz nomes de crianças e adolescentes: vale a regra de pessoas da US-03.
    verificar_acesso_a_pessoas(
        conexao,
        acesso.usuario_id,
        acesso.programa_id,
        cadastrar=False,
        alvo_tipo="atividade",
        alvo_id=atividade_id,
        requisicao=requisicao,
    )
    return atividade


# --- Rotas ---------------------------------------------------------------------


@router.get("/agenda", response_model=List[EncontroSaida])
def consultar_agenda(
    inicio: Optional[date] = None,
    fim: Optional[date] = None,
    acesso: Acesso = Depends(exigir_consulta_ao_programa),
    conexao: Connection = Depends(obter_conexao),
) -> List[EncontroSaida]:
    """Encontros previstos e registrados das turmas no período (padrão: hoje)."""
    inicio = inicio or date.today()
    fim = fim or inicio
    try:
        encontros = atividades.agenda(conexao, acesso.programa_id, inicio, fim)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    return [_encontro(e) for e in encontros]


@router.post("/turmas/{turma_id}/atividades", response_model=AtividadeSaida, status_code=201)
def registrar_atividade(
    turma_id: str,
    dados: AtividadeEntrada,
    resposta: Response,
    acesso: Acesso = Depends(exigir_registro_de_atividade),
    conexao: Connection = Depends(obter_conexao),
) -> atividades.Atividade:
    """Encerra o encontro gravando a chamada. 201 no primeiro envio; 200 no reenvio."""
    nova = atividades.NovaAtividade(
        registro_id=dados.registro_id,
        data=dados.data,
        conteudo=dados.conteudo,
        educador_id=dados.educador_id,
        observacao=dados.observacao,
        presencas=[atividades.NovaPresenca(p.pessoa_id, p.presente, p.justificativa) for p in dados.presencas],
    )
    try:
        atividade, criada = atividades.registrar_atividade(
            conexao, acesso.programa_id, turma_id, nova, usuario_id=acesso.usuario_id
        )
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    if criada:
        # US-06: quem atingiu o limite de faltas do programa ganha um alerta para a equipe.
        for alerta_id in alertas.avaliar_chamada(conexao, atividade.id):
            auditoria.registrar(
                conexao,
                usuario_id=None,
                acao="alerta_infrequencia",
                alvo_tipo="alerta",
                alvo_id=alerta_id,
                descricao="Alerta automático de infrequência",
                detalhes={"programa_id": acesso.programa_id, "turma_id": turma_id, "atividade_id": atividade.id},
            )
    conexao.commit()
    if not criada:
        resposta.status_code = 200
    return atividade


@router.get("/atividades/{atividade_id}", response_model=AtividadeSaida)
def obter_atividade(
    atividade_id: str,
    requisicao: Request,
    acesso: Acesso = Depends(exigir_consulta_ao_programa),
    conexao: Connection = Depends(obter_conexao),
) -> atividades.Atividade:
    return _atividade_visivel(conexao, acesso, atividade_id, requisicao)


@router.post("/atividades/{atividade_id}/evidencias", response_model=EvidenciaSaida, status_code=201)
async def enviar_evidencia(
    atividade_id: str,
    resposta: Response,
    registro_id: str = Form(..., min_length=1, max_length=100),
    data: Optional[date] = Form(None),
    descricao: Optional[str] = Form(None, max_length=2000),
    arquivo: UploadFile = File(...),
    acesso: Acesso = Depends(exigir_registro_de_atividade),
    conexao: Connection = Depends(obter_conexao),
    armazenamento: ArmazenamentoComprovantes = Depends(obter_armazenamento),
) -> atividades.Evidencia:
    """Envia o arquivo para o R2 e liga a evidência ao encontro. 201 no primeiro envio;
    200 no reenvio do mesmo ``registro_id`` (o arquivo não é enviado de novo)."""
    registro_id = registro_id.strip()
    try:
        atividade = atividades.obter_atividade(conexao, acesso.programa_id, atividade_id)
        existente = atividades.evidencia_ja_recebida(conexao, acesso.programa_id, atividade_id, registro_id)
        if existente is not None:
            resposta.status_code = 200
            return existente
        data = data or atividade.data
        atividades.validar_data_da_evidencia(data)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro

    # Lê no máximo 1 byte além do limite, para recusar arquivos grandes sem carregar tudo.
    conteudo = await arquivo.read(TAMANHO_MAXIMO_BYTES + 1)
    try:
        tipo = validar_comprovante(conteudo)
    except ComprovanteInvalido as erro:
        status = 413 if len(conteudo) > TAMANHO_MAXIMO_BYTES else 400
        raise HTTPException(status_code=status, detail=str(erro)) from erro

    chave = atividades.gerar_chave_evidencia(tipo)
    nome_arquivo = limpar_nome_original(arquivo.filename)
    try:
        armazenamento.salvar(chave, conteudo, tipo.content_type, nome_arquivo)
    except Exception as erro:
        raise HTTPException(status_code=503, detail="Falha ao salvar a evidência.") from erro

    evidencia, criada = atividades.registrar_evidencia(
        conexao,
        atividade,
        registro_id=registro_id,
        autor_id=acesso.usuario_id,
        data=data,
        descricao=descricao,
        chave_arquivo=chave,
        nome_arquivo=nome_arquivo,
        content_type=tipo.content_type,
        tamanho=len(conteudo),
    )
    conexao.commit()
    if not criada:
        resposta.status_code = 200
    return evidencia


@router.get("/evidencias/{evidencia_id}/arquivo")
def baixar_evidencia(
    evidencia_id: str,
    requisicao: Request,
    acesso: Acesso = Depends(exigir_consulta_ao_programa),
    conexao: Connection = Depends(obter_conexao),
    armazenamento: ArmazenamentoComprovantes = Depends(obter_armazenamento),
) -> Response:
    try:
        evidencia = atividades.obter_evidencia(conexao, acesso.programa_id, evidencia_id)
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    verificar_acesso_a_pessoas(
        conexao,
        acesso.usuario_id,
        acesso.programa_id,
        cadastrar=False,
        alvo_tipo="evidencia",
        alvo_id=evidencia_id,
        requisicao=requisicao,
    )
    try:
        armazenado = armazenamento.ler(evidencia.chave_arquivo)
    except Exception as erro:
        raise HTTPException(status_code=503, detail="Falha ao ler a evidência.") from erro
    if armazenado is None:
        raise HTTPException(status_code=404, detail="Arquivo da evidência não encontrado.")

    auditoria.registrar(
        conexao,
        usuario_id=acesso.usuario_id,
        acao=DOWNLOAD_DE_EVIDENCIA,
        alvo_tipo="evidencia",
        alvo_id=evidencia_id,
        descricao="Download de evidência de atividade",
        detalhes={"programa_id": acesso.programa_id, "atividade_id": evidencia.atividade_id},
    )
    conexao.commit()
    return Response(
        content=armazenado.conteudo,
        media_type=evidencia.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{evidencia.nome_arquivo}"',
        },
    )
