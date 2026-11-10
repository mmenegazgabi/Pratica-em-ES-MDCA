"""Trajetória da pessoa atendida: linha do tempo do cadastro (T-49 · US-03).

Por enquanto a linha do tempo junta o que o cadastro já guarda:

- entrada no programa (cadastro da pessoa);
- responsáveis vinculados depois do cadastro;
- documentos registrados;
- autorizações registradas, revogadas e vencidas (o vencimento entra na data em que a
  autorização deixou de valer, sem nada gravado para isso);
- turmas (US-04): inscrição na lista de espera, matrícula e desligamento com o motivo;
- alertas de infrequência (US-06): o alerta, cada ação de busca ativa e o encerramento.
  O resultado das ações e a justificativa do encerramento só aparecem para quem
  acompanha os alertas do programa (coordenação, assistência social e administração);
  para o resto da equipe fica só o registro de que houve o contato, como no protótipo.

Frequência (US-05), atendimentos (US-07) e rede de proteção (US-08) entram aqui quando
cada uma existir, com o sigilo de cada registro.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from Gestao.alertas import TIPOS_DE_ACAO

CADASTRO = "cadastro"
RESPONSAVEL = "responsavel"
DOCUMENTO = "documento"
AUTORIZACAO = "autorizacao"
MATRICULA = "matricula"
ALERTA = "alerta"
BUSCA_ATIVA = "busca_ativa"

NOMES_DE_AUTORIZACAO = {"uso_de_imagem": "uso de imagem"}
CONTATO_SEM_DETALHES = "Contato de acompanhamento registrado pela equipe técnica."
ENCERRAMENTO_SEM_DETALHES = "Acompanhamento encerrado pela equipe técnica."


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


def trajetoria(
    conexao: Connection, pessoa_id: str, *, hoje: Optional[date] = None, ve_acompanhamento: bool = False
) -> List[Evento]:
    """Eventos da pessoa, do mais recente para o mais antigo. A rota já conferiu o acesso.

    ``ve_acompanhamento``: quem pede acompanha os alertas do programa e vê o resultado das
    ações de busca ativa e a justificativa do encerramento.
    """
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

    for m in conexao.execute(
        sa.text(
            """
            SELECT t.nome AS turma, m.inscrito_em, m.data_entrada, m.data_saida, m.motivo_saida
            FROM matriculas m JOIN turmas t ON t.id = m.turma_id
            WHERE m.pessoa_id = :id
            """
        ),
        {"id": pessoa_id},
    ):
        # Quem não entrou no dia da inscrição esperou vaga.
        esperou = m.data_entrada is None or m.data_entrada > m.inscrito_em.astimezone(fuso).date()
        if esperou:
            eventos.append(
                Evento(data=m.inscrito_em, tipo=MATRICULA, titulo=f"Lista de espera da turma {m.turma}", descricao="Inscrição aguardando vaga.")
            )
        if m.data_entrada is not None:
            eventos.append(
                Evento(
                    data=m.inscrito_em if not esperou else _meia_noite(m.data_entrada, fuso),
                    tipo=MATRICULA,
                    titulo=f"Matrícula na turma {m.turma}",
                    descricao="Chamada da lista de espera." if esperou else "Entrada na turma.",
                )
            )
        if m.data_saida is not None:
            eventos.append(
                Evento(
                    data=_meia_noite(m.data_saida, fuso),
                    tipo=MATRICULA,
                    titulo=f"Desligamento da turma {m.turma}",
                    descricao=m.motivo_saida,
                )
            )

    eventos.extend(_eventos_de_alertas(conexao, pessoa_id, fuso, ve_acompanhamento))
    return sorted(eventos, key=lambda e: e.data, reverse=True)


def _eventos_de_alertas(conexao: Connection, pessoa_id: str, fuso, ve_acompanhamento: bool) -> List[Evento]:
    eventos: List[Evento] = []
    alertas = conexao.execute(
        sa.text(
            """
            SELECT al.id, t.nome AS turma, al.faltas_consecutivas, al.limite, al.primeira_falta, al.ultima_falta,
                   al.criado_em, al.encerrado_em, al.justificativa_encerramento
            FROM alertas al JOIN turmas t ON t.id = al.turma_id
            WHERE al.pessoa_id = :id
            """
        ),
        {"id": pessoa_id},
    ).all()
    for al in alertas:
        eventos.append(
            Evento(
                data=al.criado_em,
                tipo=ALERTA,
                titulo=f"Alerta de infrequência na turma {al.turma}",
                descricao=(
                    f"{al.faltas_consecutivas} faltas seguidas (limite do programa: {al.limite}), "
                    f"de {_data_br(al.primeira_falta)} a {_data_br(al.ultima_falta)}."
                ),
            )
        )
        if al.encerrado_em is not None:
            eventos.append(
                Evento(
                    data=al.encerrado_em,
                    tipo=ALERTA,
                    titulo=f"Alerta de infrequência encerrado (turma {al.turma})",
                    descricao=al.justificativa_encerramento if ve_acompanhamento else ENCERRAMENTO_SEM_DETALHES,
                )
            )

    if not alertas:
        return eventos
    for ac in conexao.execute(
        sa.text(
            """
            SELECT ac.tipo, ac.data, ac.resultado, ac.criado_em, u.nome AS responsavel
            FROM acoes_busca_ativa ac
            JOIN alertas al ON al.id = ac.alerta_id
            JOIN usuarios u ON u.id = ac.responsavel_id
            WHERE al.pessoa_id = :id
            """
        ),
        {"id": pessoa_id},
    ):
        # A ação vale pela data informada; registrada no próprio dia, entra na hora do registro.
        no_dia = ac.criado_em.astimezone(fuso).date() == ac.data
        eventos.append(
            Evento(
                data=ac.criado_em if no_dia else _meia_noite(ac.data, fuso),
                tipo=BUSCA_ATIVA,
                titulo=f"Busca ativa: {TIPOS_DE_ACAO.get(ac.tipo, ac.tipo).lower()}",
                descricao=f"{ac.resultado} (por {ac.responsavel})" if ve_acompanhamento else CONTATO_SEM_DETALHES,
            )
        )
    return eventos
