"""Trajetória da pessoa atendida: linha do tempo do cadastro (T-49 · US-03).

Por enquanto a linha do tempo junta o que o cadastro já guarda:

- entrada no programa (cadastro da pessoa);
- responsáveis vinculados depois do cadastro;
- documentos registrados;
- autorizações registradas, revogadas e vencidas (o vencimento entra na data em que a
  autorização deixou de valer, sem nada gravado para isso).

Frequência (US-05), atendimentos (US-07), rede de proteção (US-08) e matrículas (US-04)
entram aqui quando cada uma existir, com o sigilo de cada registro.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy.engine import Connection

CADASTRO = "cadastro"
RESPONSAVEL = "responsavel"
DOCUMENTO = "documento"
AUTORIZACAO = "autorizacao"

NOMES_DE_AUTORIZACAO = {"uso_de_imagem": "uso de imagem"}


@dataclass(frozen=True)
class Evento:
    # Data do evento; registros com hora usam a data e hora em que aconteceram.
    data: datetime
    tipo: str
    titulo: str
    descricao: str


def _data_br(dia: date) -> str:
    return dia.strftime("%d/%m/%Y")


def _meia_noite(dia: date, fuso) -> datetime:
    return datetime(dia.year, dia.month, dia.day, tzinfo=fuso)


def trajetoria(conexao: Connection, pessoa_id: str, *, hoje: Optional[date] = None) -> List[Evento]:
    """Eventos da pessoa, do mais recente para o mais antigo. A rota já conferiu o acesso."""
    hoje = hoje or date.today()
    eventos: List[Evento] = []

    cadastro = conexao.execute(
        sa.text(
            """
            SELECT p.criado_em, pr.nome AS programa, n.nome AS nucleo
            FROM pessoas p
            JOIN projetos pr ON pr.id = p.programa_id
            JOIN nucleos_familiares n ON n.id = p.nucleo_familiar_id
            WHERE p.id = :id
            """
        ),
        {"id": pessoa_id},
    ).one()
    eventos.append(
        Evento(
            data=cadastro.criado_em,
            tipo=CADASTRO,
            titulo=f"Cadastro no programa {cadastro.programa}",
            descricao=f"Núcleo familiar {cadastro.nucleo}.",
        )
    )
    fuso = cadastro.criado_em.tzinfo

    # Responsáveis do próprio cadastro já aparecem nele; aqui só os incluídos depois. O
    # cadastro grava tudo numa transação só, e o now() do Postgres é o mesmo nela toda.
    for r in conexao.execute(
        sa.text(
            """
            SELECT pr.criado_em, r.nome, pr.parentesco, pr.responsavel_legal
            FROM pessoas_responsaveis pr
            JOIN responsaveis r ON r.id = pr.responsavel_id
            WHERE pr.pessoa_id = :id AND pr.criado_em > :cadastro
            """
        ),
        {"id": pessoa_id, "cadastro": cadastro.criado_em},
    ):
        papel = "Responsável legal" if r.responsavel_legal else "Responsável"
        eventos.append(
            Evento(
                data=r.criado_em,
                tipo=RESPONSAVEL,
                titulo=f"{papel} incluído",
                descricao=r.nome + (f" ({r.parentesco})" if r.parentesco else ""),
            )
        )

    for d in conexao.execute(
        sa.text("SELECT criado_em, tipo, nome_arquivo FROM documentos_pessoa WHERE pessoa_id = :id"),
        {"id": pessoa_id},
    ):
        eventos.append(
            Evento(data=d.criado_em, tipo=DOCUMENTO, titulo=f"Documento registrado: {d.tipo}", descricao=d.nome_arquivo)
        )

    for a in conexao.execute(
        sa.text(
            "SELECT criado_em, tipo, valida_de, valida_ate, revogada_em FROM autorizacoes WHERE pessoa_id = :id"
        ),
        {"id": pessoa_id},
    ):
        nome = NOMES_DE_AUTORIZACAO.get(a.tipo, a.tipo)
        eventos.append(
            Evento(
                data=a.criado_em,
                tipo=AUTORIZACAO,
                titulo=f"Autorização de {nome} registrada",
                descricao=f"Válida de {_data_br(a.valida_de)} a {_data_br(a.valida_ate)}.",
            )
        )
        if a.revogada_em is not None:
            eventos.append(
                Evento(
                    data=a.revogada_em,
                    tipo=AUTORIZACAO,
                    titulo=f"Autorização de {nome} revogada",
                    descricao="O uso externo deixa de ser permitido por esta autorização.",
                )
            )
        elif a.valida_ate < hoje:
            eventos.append(
                Evento(
                    data=_meia_noite(a.valida_ate + timedelta(days=1), fuso),
                    tipo=AUTORIZACAO,
                    titulo=f"Autorização de {nome} vencida",
                    descricao=f"Valeu até {_data_br(a.valida_ate)}. Renove para voltar a permitir o uso externo.",
                )
            )

    return sorted(eventos, key=lambda e: e.data, reverse=True)
