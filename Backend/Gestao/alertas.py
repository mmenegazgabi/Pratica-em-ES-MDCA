"""Alertas de infrequência e busca ativa (US-06, tabelas da T-59).

Regras, as mesmas do protótipo da E2:

- **Quando nasce:** a cada chamada recebida, conta as faltas consecutivas de cada pessoa
  que faltou, nos encontros daquela turma em ordem de data. Ao atingir o limite do
  programa (``projetos.limite_faltas``, padrão 3), cria o alerta. Falta justificada não
  conta e interrompe a sequência, como presença; encontro em que a pessoa não estava na
  chamada também interrompe.
- **Para quem:** a equipe do programa que faz o acompanhamento. O responsável é a
  assistente social com vínculo ativo; sem ela, a coordenação.
- **Sem repetir:** com um alerta aberto da pessoa na turma, a sequência só atualiza esse
  alerta. Depois de encerrado, só nasce outro com uma falta nova (posterior à última
  falta já alertada) — uma chamada antiga sincronizada depois não reabre nada.
- **Acompanhamento:** cada ação (tipo, data, resultado) entra na linha do tempo do alerta
  com quem a registrou.
- **Encerramento:** só com justificativa, uma vez; o alerta e as ações nunca são apagados.

As funções não fazem commit: a rota decide quando a operação termina.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from Gestao.erros import Conflito, DadosInvalidos, NaoEncontrado

INFREQUENCIA = "infrequencia"
ABERTO, ENCERRADO = "aberto", "encerrado"

TIPOS_DE_ACAO = {
    "contato_familia": "Contato com a família",
    "busca_ativa": "Busca ativa",
    "articulacao_rede": "Articulação com a rede",
    "revisao_contrato": "Revisão de contrato",
}

ALERTA_NAO_ENCONTRADO = "Alerta não encontrado."


# --- Modelos -------------------------------------------------------------------


@dataclass(frozen=True)
class Acao:
    id: str
    tipo: str
    tipo_nome: str
    data: date
    resultado: str
    responsavel_id: str
    responsavel: str
    criado_em: datetime


@dataclass(frozen=True)
class FaltaDoAlerta:
    """Encontro da sequência que gerou o alerta (falta sem justificativa)."""

    atividade_id: str
    data: date


@dataclass(frozen=True)
class Alerta:
    id: str
    tipo: str
    programa_id: str
    pessoa_id: str
    pessoa: str
    turma_id: str
    turma: str
    responsavel_id: Optional[str]
    responsavel: Optional[str]
    situacao: str
    faltas_consecutivas: int
    limite: int
    primeira_falta: date
    ultima_falta: date
    criado_em: datetime
    encerrado_em: Optional[datetime]
    encerrado_por: Optional[str]
    justificativa_encerramento: Optional[str]
    acoes: List[Acao] = field(default_factory=list)
    # Só no detalhe: os encontros da sequência, do mais antigo para o mais recente (T-89).
    faltas: List[FaltaDoAlerta] = field(default_factory=list)

    @property
    def titulo(self) -> str:
        return f"{self.pessoa.split()[0]} precisa de um contato"

    @property
    def descricao(self) -> str:
        faltas = "1 ausência" if self.faltas_consecutivas == 1 else f"{self.faltas_consecutivas} ausências consecutivas"
        return f"{faltas} na turma {self.turma}. Limite configurado no programa: {self.limite}."


@dataclass(frozen=True)
class Sequencia:
    pessoa_id: str
    faltas: int
    primeira: date
    ultima: date


# --- Geração a partir da chamada -------------------------------------------------


def sequencias_de_faltas(conexao: Connection, turma_id: str, pessoas: Sequence[str]) -> Dict[str, Sequencia]:
    """Faltas sem justificativa seguidas, dos encontros mais recentes da turma para trás."""
    if not pessoas:
        return {}
    linhas = conexao.execute(
        sa.text(
            """
            SELECT p.pessoa_id, a.data, c.presente, c.justificativa
            FROM atividades a
            CROSS JOIN unnest(CAST(:pessoas AS text[])) AS p(pessoa_id)
            LEFT JOIN chamadas c ON c.atividade_id = a.id AND c.pessoa_id = p.pessoa_id
            WHERE a.turma_id = :turma
            ORDER BY p.pessoa_id, a.data DESC, a.criado_em DESC, a.id DESC
            """
        ),
        {"turma": turma_id, "pessoas": list(pessoas)},
    )
    sequencias: Dict[str, Sequencia] = {}
    terminou = set()
    for pessoa_id, dia, presente, justificativa in linhas:
        if pessoa_id in terminou:
            continue
        # Presença, falta justificada ou fora da chamada: a sequência acaba aqui.
        if presente is None or presente or justificativa:
            terminou.add(pessoa_id)
            continue
        atual = sequencias.get(pessoa_id)
        sequencias[pessoa_id] = Sequencia(pessoa_id, (atual.faltas if atual else 0) + 1, dia, atual.ultima if atual else dia)
    return sequencias


def _responsavel_do_programa(conexao: Connection, programa_id: str, hoje: date) -> Optional[str]:
    """Assistente social ativa no programa; sem ela, a coordenação (T-87: papel da conta,
    vale para todos os programas), começando por quem tem o papel há mais tempo."""
    assistente = conexao.execute(
        sa.text(
            """
            SELECT v.usuario_id FROM vinculos_equipe v JOIN usuarios u ON u.id = v.usuario_id
            WHERE v.programa_id = :programa AND u.ativo AND v.papel_id = 'assistente_social'
              AND v.data_entrada <= :hoje AND (v.data_saida IS NULL OR v.data_saida > :hoje)
            ORDER BY v.data_entrada, v.id
            LIMIT 1
            """
        ),
        {"programa": programa_id, "hoje": hoje},
    ).scalar_one_or_none()
    if assistente is not None:
        return assistente
    return conexao.execute(
        sa.text(
            """
            SELECT up.usuario_id FROM usuarios_papeis up JOIN usuarios u ON u.id = up.usuario_id
            WHERE up.papel_id = 'coordenacao' AND u.ativo
            ORDER BY up.atribuido_em, up.usuario_id
            LIMIT 1
            """
        )
    ).scalar_one_or_none()


def avaliar_chamada(conexao: Connection, atividade_id: str, *, hoje: Optional[date] = None) -> List[str]:
    """Cria ou atualiza os alertas de quem faltou no encontro. Devolve os ids dos alertas
    criados agora (para a auditoria)."""
    encontro = conexao.execute(
        sa.text(
            """
            SELECT a.programa_id, a.turma_id, p.limite_faltas
            FROM atividades a JOIN projetos p ON p.id = a.programa_id WHERE a.id = :id
            """
        ),
        {"id": atividade_id},
    ).one()
    faltaram = list(
        conexao.execute(
            sa.text("SELECT pessoa_id FROM chamadas WHERE atividade_id = :id AND NOT presente AND justificativa IS NULL"),
            {"id": atividade_id},
        ).scalars()
    )
    criados = []
    for sequencia in sequencias_de_faltas(conexao, encontro.turma_id, faltaram).values():
        if sequencia.faltas < encontro.limite_faltas:
            continue
        aberto = conexao.execute(
            sa.text(
                "SELECT id FROM alertas WHERE pessoa_id = :pessoa AND turma_id = :turma AND tipo = :tipo AND situacao = 'aberto'"
            ),
            {"pessoa": sequencia.pessoa_id, "turma": encontro.turma_id, "tipo": INFREQUENCIA},
        ).scalar_one_or_none()
        if aberto:
            conexao.execute(
                sa.text(
                    """
                    UPDATE alertas SET faltas_consecutivas = GREATEST(faltas_consecutivas, :faltas),
                           ultima_falta = GREATEST(ultima_falta, :ultima)
                    WHERE id = :id
                    """
                ),
                {"id": aberto, "faltas": sequencia.faltas, "ultima": sequencia.ultima},
            )
            continue
        ja_alertada = conexao.execute(
            sa.text(
                "SELECT 1 FROM alertas WHERE pessoa_id = :pessoa AND turma_id = :turma AND tipo = :tipo AND ultima_falta >= :ultima"
            ),
            {"pessoa": sequencia.pessoa_id, "turma": encontro.turma_id, "tipo": INFREQUENCIA, "ultima": sequencia.ultima},
        ).first()
        if ja_alertada:
            continue
        alerta_id = str(uuid.uuid4())
        conexao.execute(
            sa.text(
                """
                INSERT INTO alertas (id, tipo, programa_id, pessoa_id, turma_id, responsavel_id, situacao,
                                     faltas_consecutivas, limite, primeira_falta, ultima_falta)
                VALUES (:id, :tipo, :programa, :pessoa, :turma, :responsavel, 'aberto',
                        :faltas, :limite, :primeira, :ultima)
                """
            ),
            {
                "id": alerta_id,
                "tipo": INFREQUENCIA,
                "programa": encontro.programa_id,
                "pessoa": sequencia.pessoa_id,
                "turma": encontro.turma_id,
                "responsavel": _responsavel_do_programa(conexao, encontro.programa_id, hoje or date.today()),
                "faltas": sequencia.faltas,
                "limite": encontro.limite_faltas,
                "primeira": sequencia.primeira,
                "ultima": sequencia.ultima,
            },
        )
        criados.append(alerta_id)
    return criados


# --- Consulta --------------------------------------------------------------------

_SELECIONAR_ALERTA = """
    SELECT al.id, al.tipo, al.programa_id, al.pessoa_id, pe.nome AS pessoa, al.turma_id, t.nome AS turma,
           al.responsavel_id, u.nome AS responsavel, al.situacao, al.faltas_consecutivas, al.limite,
           al.primeira_falta, al.ultima_falta, al.criado_em, al.encerrado_em, al.encerrado_por,
           al.justificativa_encerramento
    FROM alertas al
    JOIN pessoas pe ON pe.id = al.pessoa_id
    JOIN turmas t ON t.id = al.turma_id
    LEFT JOIN usuarios u ON u.id = al.responsavel_id
"""


def _acoes(conexao: Connection, alerta_id: str) -> List[Acao]:
    linhas = conexao.execute(
        sa.text(
            """
            SELECT ac.id, ac.tipo, ac.data, ac.resultado, ac.responsavel_id, u.nome AS responsavel, ac.criado_em
            FROM acoes_busca_ativa ac JOIN usuarios u ON u.id = ac.responsavel_id
            WHERE ac.alerta_id = :id
            ORDER BY ac.data DESC, ac.criado_em DESC, ac.id
            """
        ),
        {"id": alerta_id},
    )
    return [Acao(tipo_nome=TIPOS_DE_ACAO[l.tipo], **l._mapping) for l in linhas]


def listar(conexao: Connection, *, programas: Optional[Sequence[str]], situacao: Optional[str] = None) -> List[Alerta]:
    """Alertas dos programas indicados (``None``: todos), os abertos e mais recentes primeiro."""
    if programas is not None and not programas:
        return []
    filtros, parametros = [], {}
    if programas is not None:
        filtros.append("al.programa_id IN :programas")
        parametros["programas"] = list(programas)
    if situacao:
        filtros.append("al.situacao = :situacao")
        parametros["situacao"] = situacao
    consulta = sa.text(
        f"{_SELECIONAR_ALERTA} {'WHERE ' + ' AND '.join(filtros) if filtros else ''} "
        "ORDER BY (al.situacao = 'aberto') DESC, al.criado_em DESC, al.id"
    )
    if programas is not None:
        consulta = consulta.bindparams(sa.bindparam("programas", expanding=True))
    return [Alerta(**l._mapping) for l in conexao.execute(consulta, parametros)]


def obter(conexao: Connection, alerta_id: str) -> Alerta:
    linha = conexao.execute(sa.text(f"{_SELECIONAR_ALERTA} WHERE al.id = :id"), {"id": alerta_id}).first()
    if linha is None:
        raise NaoEncontrado(ALERTA_NAO_ENCONTRADO)
    return Alerta(**linha._mapping, acoes=_acoes(conexao, alerta_id), faltas=_faltas(conexao, linha))


def _faltas(conexao: Connection, alerta) -> List[FaltaDoAlerta]:
    """Encontros da turma, no período do alerta, em que a pessoa faltou sem justificativa."""
    linhas = conexao.execute(
        sa.text(
            """
            SELECT a.id AS atividade_id, a.data
            FROM atividades a JOIN chamadas c ON c.atividade_id = a.id
            WHERE a.turma_id = :turma AND c.pessoa_id = :pessoa AND NOT c.presente AND c.justificativa IS NULL
              AND a.data BETWEEN :primeira AND :ultima
            ORDER BY a.data, a.id
            """
        ),
        {"turma": alerta.turma_id, "pessoa": alerta.pessoa_id, "primeira": alerta.primeira_falta, "ultima": alerta.ultima_falta},
    )
    return [FaltaDoAlerta(**l._mapping) for l in linhas]


def programa_do_alerta(conexao: Connection, alerta_id: str) -> Optional[str]:
    return conexao.execute(sa.text("SELECT programa_id FROM alertas WHERE id = :id"), {"id": alerta_id}).scalar_one_or_none()


# --- Acompanhamento ----------------------------------------------------------------


def registrar_acao(
    conexao: Connection,
    alerta_id: str,
    *,
    tipo: str,
    data: date,
    resultado: Optional[str],
    responsavel_id: str,
    hoje: Optional[date] = None,
) -> Alerta:
    alerta = obter(conexao, alerta_id)
    if alerta.situacao == ENCERRADO:
        raise Conflito("O acompanhamento deste alerta já foi encerrado.", codigo="alerta_encerrado")
    if tipo not in TIPOS_DE_ACAO:
        raise DadosInvalidos("Tipo de ação inválido.", codigo="tipo_invalido")
    resultado = (resultado or "").strip()
    if not resultado:
        raise DadosInvalidos("Informe o resultado da ação.", codigo="resultado_obrigatorio")
    if data > (hoje or date.today()):
        raise DadosInvalidos("A data da ação não pode estar no futuro.", codigo="data_no_futuro")
    conexao.execute(
        sa.text(
            """
            INSERT INTO acoes_busca_ativa (id, alerta_id, tipo, data, resultado, responsavel_id)
            VALUES (:id, :alerta, :tipo, :data, :resultado, :responsavel)
            """
        ),
        {"id": str(uuid.uuid4()), "alerta": alerta_id, "tipo": tipo, "data": data, "resultado": resultado, "responsavel": responsavel_id},
    )
    return obter(conexao, alerta_id)


def encerrar(conexao: Connection, alerta_id: str, *, justificativa: Optional[str], usuario_id: str) -> Alerta:
    alerta = obter(conexao, alerta_id)
    if alerta.situacao == ENCERRADO:
        raise Conflito("Este alerta já foi encerrado.", codigo="alerta_encerrado")
    justificativa = (justificativa or "").strip()
    if not justificativa:
        raise DadosInvalidos(
            "Informe a justificativa do encerramento (por exemplo, o retorno à frequência regular).",
            codigo="justificativa_obrigatoria",
        )
    conexao.execute(
        sa.text(
            """
            UPDATE alertas SET situacao = 'encerrado', encerrado_em = now(), encerrado_por = :usuario,
                   justificativa_encerramento = :justificativa
            WHERE id = :id
            """
        ),
        {"id": alerta_id, "usuario": usuario_id, "justificativa": justificativa},
    )
    return obter(conexao, alerta_id)
