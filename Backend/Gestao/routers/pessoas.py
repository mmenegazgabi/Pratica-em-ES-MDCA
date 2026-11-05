"""Cadastro de pessoas atendidas, famílias, responsáveis e autorizações (T-48 · US-03)."""

from datetime import date, datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Connection

from Financeiro.autenticacao import exigir_usuario
from Gestao import auditoria, autorizacoes, pessoas
from Gestao.acesso import (
    AcessoAPessoas,
    exigir_cadastro_na_pessoa,
    exigir_consulta_a_pessoa,
    programas_com_pessoas_visiveis,
    verificar_acesso_a_pessoas,
)
from Gestao.banco import obter_conexao
from Gestao.erros import ErroDeCadastro

router = APIRouter(prefix="/gestao", tags=["gestao"])

NOME = Field(min_length=1, max_length=200)
TEXTO_CURTO = Field(default=None, max_length=200)


# --- Entradas --------------------------------------------------------------------


class ResponsavelEntrada(BaseModel):
    """Responsável já cadastrado (``id``) ou novo (``nome``)."""

    id: Optional[str] = Field(default=None, max_length=100)
    nome: Optional[str] = TEXTO_CURTO
    telefone: Optional[str] = Field(default=None, max_length=40)
    parentesco: Optional[str] = Field(default=None, max_length=60)
    responsavel_legal: bool = False

    def para_dominio(self) -> pessoas.NovoResponsavel:
        return pessoas.NovoResponsavel(**self.model_dump())


class DuplicidadeEntrada(BaseModel):
    programa_id: str = Field(min_length=1, max_length=100)
    nome: str = NOME
    data_nascimento: date
    responsaveis: List[ResponsavelEntrada] = Field(default_factory=list, max_length=10)


class PessoaEntrada(DuplicidadeEntrada):
    nucleo_familiar_id: Optional[str] = Field(default=None, max_length=100)
    nucleo_familiar_nome: Optional[str] = TEXTO_CURTO
    telefone: Optional[str] = Field(default=None, max_length=40)
    observacao: Optional[str] = Field(default=None, max_length=2000)
    # Depois do alerta de possível duplicidade, quem cadastra confirma que é outra pessoa.
    confirmar_duplicidade: bool = False


class DocumentoEntrada(BaseModel):
    tipo: str = Field(min_length=1, max_length=60)
    nome_arquivo: str = Field(min_length=1, max_length=255)
    tamanho: Optional[int] = Field(default=None, ge=0)


class AutorizacaoEntrada(BaseModel):
    tipo: Literal["uso_de_imagem"]
    valida_ate: date
    valida_de: Optional[date] = None
    documento_id: Optional[str] = Field(default=None, max_length=100)


class UsoDeImagemEntrada(BaseModel):
    pessoa_ids: List[str] = Field(min_length=1, max_length=200)
    # Externo: divulgação, redes, relatórios públicos. Interno não depende de autorização.
    uso: Literal["externo", "interno"] = "externo"


# --- Saídas ------------------------------------------------------------------------


class _Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class NucleoSaida(_Saida):
    id: str
    nome: str


class ResponsavelSaida(_Saida):
    id: str
    nome: str
    telefone: Optional[str]
    parentesco: Optional[str]
    responsavel_legal: bool


class DocumentoSaida(_Saida):
    id: str
    tipo: str
    nome_arquivo: str
    tamanho: Optional[int]
    criado_em: datetime


class AutorizacaoSaida(_Saida):
    id: str
    tipo: str
    valida_de: date
    valida_ate: date
    documento_id: Optional[str]
    revogada_em: Optional[datetime]
    # vigente, vencida ou revogada (calculada na consulta).
    situacao: str


class PessoaResumoSaida(_Saida):
    id: str
    nome: str
    data_nascimento: date
    programa_id: str
    programa: str
    nucleo_familiar: NucleoSaida
    responsaveis: List[str]
    situacao: str
    autorizacao_imagem: str


class PessoaSaida(_Saida):
    id: str
    nome: str
    data_nascimento: date
    idade: int
    programa_id: str
    programa: str
    nucleo_familiar: NucleoSaida
    telefone: Optional[str]
    observacao: Optional[str]
    situacao: str
    responsaveis: List[ResponsavelSaida]
    documentos: List[DocumentoSaida]
    autorizacoes: List[AutorizacaoSaida]
    # vigente, vencida, revogada ou sem_autorizacao.
    autorizacao_imagem: str


class DuplicadoSaida(_Saida):
    id: str
    nome: str
    data_nascimento: date
    programa_id: str
    programa: str
    responsaveis: List[str]
    motivos: List[str]


class BloqueioSaida(_Saida):
    pessoa_id: str
    nome: str
    motivo: str


class UsoDeImagemSaida(BaseModel):
    liberado: bool
    bloqueios: List[BloqueioSaida]


# --- Apoio -------------------------------------------------------------------------


def _http(erro: ErroDeCadastro) -> HTTPException:
    if not erro.dados:
        return HTTPException(status_code=erro.status, detail=erro.mensagem)
    detalhe = {"codigo": erro.codigo, "mensagem": erro.mensagem, **erro.dados}
    return HTTPException(status_code=erro.status, detail=jsonable_encoder(detalhe))


def _cadastro_no_programa(conexao, usuario_id, programa_id, requisicao) -> AcessoAPessoas:
    return verificar_acesso_a_pessoas(
        conexao, usuario_id, programa_id, cadastrar=True, requisicao=requisicao
    )


# --- Rotas -------------------------------------------------------------------------
# Como nas demais rotas de Gestão, o acesso vem antes de qualquer consulta de dados.


@router.get("/pessoas", response_model=List[PessoaResumoSaida])
def listar_pessoas(
    requisicao: Request,
    programa_id: Optional[str] = None,
    busca: str = "",
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
):
    """Pessoas dos programas em que a pessoa usuária atua (administração: todas)."""
    if programa_id:
        verificar_acesso_a_pessoas(conexao, usuario_id, programa_id, cadastrar=False, requisicao=requisicao)
        programas = [programa_id]
    else:
        programas = programas_com_pessoas_visiveis(conexao, usuario_id)
    return pessoas.listar(conexao, programas=programas, busca=busca)


@router.post("/pessoas/duplicidades", response_model=List[DuplicadoSaida])
def verificar_duplicidade(
    dados: DuplicidadeEntrada,
    requisicao: Request,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
):
    """Possíveis duplicados de um cadastro ainda não concluído (etapa de revisão)."""
    _cadastro_no_programa(conexao, usuario_id, dados.programa_id, requisicao)
    return pessoas.buscar_duplicidades(
        conexao,
        nome=dados.nome,
        data_nascimento=dados.data_nascimento,
        responsaveis=[r.para_dominio() for r in dados.responsaveis],
    )


@router.post("/pessoas", response_model=PessoaSaida, status_code=201)
def cadastrar_pessoa(
    dados: PessoaEntrada,
    requisicao: Request,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
):
    _cadastro_no_programa(conexao, usuario_id, dados.programa_id, requisicao)
    nova = pessoas.NovaPessoa(
        nome=dados.nome,
        data_nascimento=dados.data_nascimento,
        programa_id=dados.programa_id,
        nucleo_familiar_id=dados.nucleo_familiar_id,
        nucleo_familiar_nome=dados.nucleo_familiar_nome,
        responsaveis=[r.para_dominio() for r in dados.responsaveis],
        telefone=dados.telefone,
        observacao=dados.observacao,
    )
    try:
        pessoa, duplicados = pessoas.cadastrar(
            conexao, nova, usuario_id=usuario_id, confirmar_duplicidade=dados.confirmar_duplicidade
        )
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    if duplicados:
        auditoria.registrar(
            conexao,
            usuario_id=usuario_id,
            acao="duplicidade_confirmada",
            alvo_tipo="pessoa",
            alvo_id=pessoa.id,
            descricao="Cadastro concluído após alerta de possível duplicidade",
            detalhes={"semelhantes": [d.id for d in duplicados]},
        )
    conexao.commit()
    return pessoa


@router.get("/pessoas/{pessoa_id}", response_model=PessoaSaida)
def obter_pessoa(
    pessoa_id: str,
    _acesso: AcessoAPessoas = Depends(exigir_consulta_a_pessoa),
    conexao: Connection = Depends(obter_conexao),
):
    return pessoas.obter(conexao, pessoa_id)


@router.post("/pessoas/{pessoa_id}/responsaveis", response_model=PessoaSaida, status_code=201)
def incluir_responsavel(
    pessoa_id: str,
    dados: ResponsavelEntrada,
    _acesso: AcessoAPessoas = Depends(exigir_cadastro_na_pessoa),
    conexao: Connection = Depends(obter_conexao),
):
    try:
        pessoa = pessoas.incluir_responsavel(conexao, pessoa_id, dados.para_dominio())
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    conexao.commit()
    return pessoa


@router.post("/pessoas/{pessoa_id}/documentos", response_model=DocumentoSaida, status_code=201)
def registrar_documento(
    pessoa_id: str,
    dados: DocumentoEntrada,
    acesso: AcessoAPessoas = Depends(exigir_cadastro_na_pessoa),
    conexao: Connection = Depends(obter_conexao),
):
    """Registra os dados do documento; o envio do arquivo chega com as telas (T-49)."""
    try:
        documento = pessoas.registrar_documento(
            conexao, pessoa_id, usuario_id=acesso.usuario_id, **dados.model_dump()
        )
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    conexao.commit()
    return documento


@router.post("/pessoas/{pessoa_id}/autorizacoes", response_model=AutorizacaoSaida, status_code=201)
def registrar_autorizacao(
    pessoa_id: str,
    dados: AutorizacaoEntrada,
    acesso: AcessoAPessoas = Depends(exigir_cadastro_na_pessoa),
    conexao: Connection = Depends(obter_conexao),
):
    try:
        autorizacao = autorizacoes.registrar(
            conexao, pessoa_id, usuario_id=acesso.usuario_id, **dados.model_dump()
        )
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    conexao.commit()
    return autorizacao


@router.post(
    "/pessoas/{pessoa_id}/autorizacoes/{autorizacao_id}/revogacao", response_model=AutorizacaoSaida
)
def revogar_autorizacao(
    pessoa_id: str,
    autorizacao_id: str,
    acesso: AcessoAPessoas = Depends(exigir_cadastro_na_pessoa),
    conexao: Connection = Depends(obter_conexao),
):
    try:
        autorizacao = autorizacoes.revogar(
            conexao, pessoa_id, autorizacao_id, usuario_id=acesso.usuario_id
        )
    except ErroDeCadastro as erro:
        raise _http(erro) from erro
    auditoria.registrar(
        conexao,
        usuario_id=acesso.usuario_id,
        acao="autorizacao_revogada",
        alvo_tipo="pessoa",
        alvo_id=pessoa_id,
        descricao=f"Autorização de {autorizacao.tipo} revogada",
        detalhes={"autorizacao_id": autorizacao_id},
    )
    conexao.commit()
    return autorizacao


@router.post("/pessoas/uso-de-imagem", response_model=UsoDeImagemSaida)
def verificar_uso_de_imagem(
    dados: UsoDeImagemEntrada,
    requisicao: Request,
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
):
    """Uso externo só com autorização de imagem vigente de cada pessoa (409 senão)."""
    ids = list(dict.fromkeys(dados.pessoa_ids))
    programas = {pid: pessoas.programa_da_pessoa(conexao, pid) for pid in ids}
    inexistentes = [pid for pid, programa in programas.items() if programa is None]
    if inexistentes:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada.")
    for pessoa_id, programa_id in programas.items():
        verificar_acesso_a_pessoas(
            conexao,
            usuario_id,
            programa_id,
            cadastrar=False,
            alvo_tipo="pessoa",
            alvo_id=pessoa_id,
            requisicao=requisicao,
        )
    if dados.uso == "interno":
        return UsoDeImagemSaida(liberado=True, bloqueios=[])
    bloqueios = autorizacoes.verificar_uso_de_imagem(conexao, ids)
    if bloqueios:
        raise HTTPException(
            status_code=409,
            detail=jsonable_encoder(
                {
                    "codigo": "uso_de_imagem_bloqueado",
                    "mensagem": "Uso externo bloqueado: há pessoas sem autorização de imagem vigente. "
                    "Atualize a autorização ou mantenha o material só para uso interno.",
                    "bloqueios": bloqueios,
                }
            ),
        )
    return UsoDeImagemSaida(liberado=True, bloqueios=[])


@router.get("/nucleos-familiares", response_model=List[NucleoSaida])
def buscar_nucleos(
    busca: str = "",
    usuario_id: str = Depends(exigir_usuario),
    conexao: Connection = Depends(obter_conexao),
):
    """Núcleos com alguém nos programas em que a pessoa usuária atua."""
    programas = programas_com_pessoas_visiveis(conexao, usuario_id)
    return pessoas.buscar_nucleos(conexao, programas=programas, busca=busca)
