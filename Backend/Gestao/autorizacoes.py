"""Autorizações das pessoas atendidas, como o uso de imagem (US-03, tabela da T-47).

A situação não é gravada: sai de ``revogada_em`` e ``valida_ate`` no momento da
consulta, para não ficar errada no dia em que a autorização vence.

- **revogada:** tem ``revogada_em``;
- **vencida:** ``valida_ate`` já passou;
- **vigente:** nenhum dos dois.

Uso **externo** de imagem (divulgação, redes, relatórios públicos) exige autorização de
imagem vigente de cada pessoa que aparece; uso interno não depende dela. A mesma
verificação servirá às evidências de atividade (US-05, T-56).

As funções não fazem commit: a rota decide quando a operação termina.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from Gestao.erros import Conflito, DadosInvalidos, NaoEncontrado

USO_DE_IMAGEM = "uso_de_imagem"
TIPOS = {USO_DE_IMAGEM}

VIGENTE = "vigente"
VENCIDA = "vencida"
REVOGADA = "revogada"
SEM_AUTORIZACAO = "sem_autorizacao"


@dataclass(frozen=True)
class Autorizacao:
    id: str
    tipo: str
    valida_de: date
    valida_ate: date
    documento_id: Optional[str]
    revogada_em: Optional[datetime]
    situacao: str


@dataclass(frozen=True)
class Bloqueio:
    pessoa_id: str
    nome: str
    motivo: str


def situacao(*, revogada_em: Optional[datetime], valida_ate: date, hoje: date) -> str:
    if revogada_em is not None:
        return REVOGADA
    if valida_ate < hoje:
        return VENCIDA
    return VIGENTE


def situacao_de_imagem(autorizacoes: Sequence[Autorizacao]) -> str:
    """Situação do uso de imagem: vigente se alguma estiver vigente; senão, a da mais
    recente (revogada ou vencida); sem nenhuma, ``sem_autorizacao``."""
    de_imagem = [a for a in autorizacoes if a.tipo == USO_DE_IMAGEM]
    if not de_imagem:
        return SEM_AUTORIZACAO
    if any(a.situacao == VIGENTE for a in de_imagem):
        return VIGENTE
    return de_imagem[0].situacao


_SELECIONAR = """
    SELECT id, pessoa_id, tipo, valida_de, valida_ate, documento_id, revogada_em
    FROM autorizacoes
"""
# A mais recente primeiro: é ela que explica o bloqueio quando nenhuma está vigente.
_ORDEM = " ORDER BY valida_ate DESC, criado_em DESC, id"


def _autorizacao(linha, hoje: date) -> Autorizacao:
    return Autorizacao(
        id=linha.id,
        tipo=linha.tipo,
        valida_de=linha.valida_de,
        valida_ate=linha.valida_ate,
        documento_id=linha.documento_id,
        revogada_em=linha.revogada_em,
        situacao=situacao(revogada_em=linha.revogada_em, valida_ate=linha.valida_ate, hoje=hoje),
    )


def listar_autorizacoes(conexao: Connection, pessoa_id: str, *, hoje: Optional[date] = None) -> List[Autorizacao]:
    hoje = hoje or date.today()
    linhas = conexao.execute(sa.text(_SELECIONAR + " WHERE pessoa_id = :id" + _ORDEM), {"id": pessoa_id})
    return [_autorizacao(l, hoje) for l in linhas]


def autorizacoes_por_pessoa(
    conexao: Connection, pessoa_ids: Sequence[str], *, hoje: Optional[date] = None
) -> Dict[str, List[Autorizacao]]:
    if not pessoa_ids:
        return {}
    hoje = hoje or date.today()
    resultado: Dict[str, List[Autorizacao]] = {}
    linhas = conexao.execute(
        sa.text(_SELECIONAR + " WHERE pessoa_id IN :ids" + _ORDEM).bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": list(pessoa_ids)},
    )
    for linha in linhas:
        resultado.setdefault(linha.pessoa_id, []).append(_autorizacao(linha, hoje))
    return resultado


def registrar(
    conexao: Connection,
    pessoa_id: str,
    *,
    tipo: str,
    valida_ate: date,
    valida_de: Optional[date] = None,
    documento_id: Optional[str] = None,
    usuario_id: str,
    hoje: Optional[date] = None,
) -> Autorizacao:
    hoje = hoje or date.today()
    valida_de = valida_de or hoje
    if tipo not in TIPOS:
        raise DadosInvalidos("Tipo de autorização inválido.")
    if valida_de > hoje:
        # Uma autorização que ainda não começou não pode ser chamada de vigente nem de
        # vencida; ela é registrada quando passa a valer.
        raise DadosInvalidos("O início da validade não pode estar no futuro.")
    if valida_ate < valida_de:
        raise DadosInvalidos("O fim da validade não pode ser anterior ao início.")
    if documento_id and conexao.execute(
        sa.text("SELECT 1 FROM documentos_pessoa WHERE id = :id AND pessoa_id = :pessoa"),
        {"id": documento_id, "pessoa": pessoa_id},
    ).first() is None:
        raise DadosInvalidos("Documento não encontrado para esta pessoa.")
    autorizacao_id = str(uuid.uuid4())
    conexao.execute(
        sa.text(
            """
            INSERT INTO autorizacoes (id, pessoa_id, tipo, valida_de, valida_ate, documento_id, criado_por)
            VALUES (:id, :pessoa, :tipo, :de, :ate, :documento, :usuario)
            """
        ),
        {
            "id": autorizacao_id,
            "pessoa": pessoa_id,
            "tipo": tipo,
            "de": valida_de,
            "ate": valida_ate,
            "documento": documento_id,
            "usuario": usuario_id,
        },
    )
    return _buscar(conexao, pessoa_id, autorizacao_id, hoje)


def revogar(
    conexao: Connection, pessoa_id: str, autorizacao_id: str, *, usuario_id: str, hoje: Optional[date] = None
) -> Autorizacao:
    hoje = hoje or date.today()
    atual = _buscar(conexao, pessoa_id, autorizacao_id, hoje)
    if atual.revogada_em is not None:
        raise Conflito("Esta autorização já foi revogada.")
    conexao.execute(
        sa.text("UPDATE autorizacoes SET revogada_em = now(), revogada_por = :usuario WHERE id = :id"),
        {"usuario": usuario_id, "id": autorizacao_id},
    )
    return _buscar(conexao, pessoa_id, autorizacao_id, hoje)


def _buscar(conexao: Connection, pessoa_id: str, autorizacao_id: str, hoje: date) -> Autorizacao:
    linha = conexao.execute(
        sa.text(_SELECIONAR + " WHERE id = :id AND pessoa_id = :pessoa"),
        {"id": autorizacao_id, "pessoa": pessoa_id},
    ).first()
    if linha is None:
        raise NaoEncontrado("Autorização não encontrada para esta pessoa.")
    return _autorizacao(linha, hoje)


def verificar_uso_de_imagem(
    conexao: Connection, pessoa_ids: Sequence[str], *, hoje: Optional[date] = None
) -> List[Bloqueio]:
    """Quem impede o uso externo da imagem: lista vazia quando todos têm autorização
    de imagem vigente. Ids inexistentes devem ser recusados antes (404)."""
    hoje = hoje or date.today()
    ids = list(dict.fromkeys(pessoa_ids))
    if not ids:
        return []
    nomes = dict(
        conexao.execute(
            sa.text("SELECT id, nome FROM pessoas WHERE id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": ids},
        ).all()
    )
    autorizacoes = autorizacoes_por_pessoa(conexao, ids, hoje=hoje)
    bloqueios = []
    for pessoa_id in ids:
        motivo = situacao_de_imagem(autorizacoes.get(pessoa_id, []))
        if motivo != VIGENTE:
            bloqueios.append(Bloqueio(pessoa_id=pessoa_id, nome=nomes.get(pessoa_id, ""), motivo=motivo))
    return bloqueios
