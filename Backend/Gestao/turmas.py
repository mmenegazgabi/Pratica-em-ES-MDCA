"""Turmas, matrículas e lista de espera (US-04, tabelas da T-51).

Regras aplicadas aqui:

- **Turma:** local é um espaço do próprio programa, e o responsável precisa ter vínculo
  ativo no programa (critério da US-01: só quem está na equipe pode ser escolhido).
- **Turma lotada:** a inscrição entra na lista de espera, na ordem de chegada
  (``inscrito_em``). Quando abre vaga, a coordenação chama o próximo da fila.
- **Desligamento:** data e motivo obrigatórios; a matrícula nunca é apagada.
- **Conflito de horário:** outra matrícula ativa da mesma pessoa em turma com dia em
  comum e horário sobreposto. A inscrição é salva, e o conflito volta na resposta (para
  a coordenação ver) e fica na trilha de auditoria.

As funções não fazem commit: a rota decide quando a operação termina.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Dict, List, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from Gestao.erros import Conflito, DadosInvalidos, NaoEncontrado

UNIQUE_VIOLATION = "23505"
ATIVA, ESPERA, DESLIGADA = "ativa", "espera", "desligada"
DIAS = {1: "seg", 2: "ter", 3: "qua", 4: "qui", 5: "sex", 6: "sáb", 7: "dom"}


# --- Modelos -------------------------------------------------------------------


@dataclass(frozen=True)
class ConflitoDeHorario:
    turma_id: str
    turma: str
    dias_semana: List[int]
    hora_inicio: time
    hora_fim: time


@dataclass(frozen=True)
class Matricula:
    id: str
    pessoa_id: str
    pessoa: str
    situacao: str
    inscrito_em: datetime
    data_entrada: Optional[date]
    data_saida: Optional[date]
    motivo_saida: Optional[str]
    # 1, 2, 3… para quem está na lista de espera; vazio para os demais.
    posicao_espera: Optional[int] = None
    conflitos: List[ConflitoDeHorario] = field(default_factory=list)


@dataclass(frozen=True)
class Turma:
    id: str
    programa_id: str
    nome: str
    espaco_id: str
    espaco: str
    responsavel_id: str
    responsavel: str
    capacidade: int
    dias_semana: List[int]
    hora_inicio: time
    hora_fim: time
    ativas: int
    em_espera: int

    @property
    def vagas_livres(self) -> int:
        return max(0, self.capacidade - self.ativas)


@dataclass(frozen=True)
class TurmaDetalhada:
    turma: Turma
    matriculas: List[Matricula]
    lista_de_espera: List[Matricula]
    desligadas: List[Matricula]


@dataclass(frozen=True)
class Inscricao:
    matricula: Matricula
    conflitos: List[ConflitoDeHorario]


# --- Consultas -----------------------------------------------------------------

_TURMAS = """
    SELECT t.id, t.programa_id, t.nome, t.espaco_id, e.nome AS espaco,
           t.responsavel_id, u.nome AS responsavel, t.capacidade, t.dias_semana,
           t.hora_inicio, t.hora_fim,
           count(m.id) FILTER (WHERE m.situacao = 'ativa') AS ativas,
           count(m.id) FILTER (WHERE m.situacao = 'espera') AS em_espera
    FROM turmas t
    JOIN espacos e ON e.id = t.espaco_id
    JOIN usuarios u ON u.id = t.responsavel_id
    LEFT JOIN matriculas m ON m.turma_id = t.id
    WHERE t.programa_id = :programa {filtro}
    GROUP BY t.id, e.nome, u.nome
    ORDER BY lower(t.nome), t.id
"""


def _turma(linha) -> Turma:
    dados = dict(linha._mapping)
    dados["dias_semana"] = sorted(dados["dias_semana"])
    return Turma(**dados)


def listar_turmas(conexao: Connection, programa_id: str) -> List[Turma]:
    linhas = conexao.execute(sa.text(_TURMAS.format(filtro="")), {"programa": programa_id})
    return [_turma(l) for l in linhas]


def buscar_turma(conexao: Connection, programa_id: str, turma_id: str) -> Turma:
    linha = conexao.execute(
        sa.text(_TURMAS.format(filtro="AND t.id = :turma")), {"programa": programa_id, "turma": turma_id}
    ).first()
    if linha is None:
        raise NaoEncontrado("Turma não encontrada.")
    return _turma(linha)


def conflitos_de_horario(
    conexao: Connection, pessoa_id: str, turma_id: str, *, ignorar_matricula: Optional[str] = None
) -> List[ConflitoDeHorario]:
    """Outras turmas em que a pessoa está ativa, com dia em comum e horário sobreposto."""
    linhas = conexao.execute(
        sa.text(
            """
            SELECT outra.id AS turma_id, outra.nome AS turma, outra.dias_semana,
                   outra.hora_inicio, outra.hora_fim
            FROM turmas esta
            JOIN matriculas m ON m.pessoa_id = :pessoa AND m.situacao = 'ativa'
                             AND m.turma_id <> esta.id
                             AND (CAST(:ignorar AS text) IS NULL OR m.id <> CAST(:ignorar AS text))
            JOIN turmas outra ON outra.id = m.turma_id
            WHERE esta.id = :turma
              AND outra.dias_semana && esta.dias_semana
              AND outra.hora_inicio < esta.hora_fim AND esta.hora_inicio < outra.hora_fim
            ORDER BY lower(outra.nome), outra.id
            """
        ),
        {"pessoa": pessoa_id, "turma": turma_id, "ignorar": ignorar_matricula},
    )
    return [
        ConflitoDeHorario(
            turma_id=l.turma_id,
            turma=l.turma,
            dias_semana=sorted(l.dias_semana),
            hora_inicio=l.hora_inicio,
            hora_fim=l.hora_fim,
        )
        for l in linhas
    ]


_MATRICULAS = """
    SELECT m.id, m.pessoa_id, p.nome AS pessoa, m.situacao, m.inscrito_em,
           m.data_entrada, m.data_saida, m.motivo_saida
    FROM matriculas m JOIN pessoas p ON p.id = m.pessoa_id
    WHERE m.turma_id = :turma {filtro}
"""


def _matricula(conexao: Connection, linha, turma_id: str, posicao: Optional[int] = None) -> Matricula:
    conflitos = conflitos_de_horario(conexao, linha.pessoa_id, turma_id) if linha.situacao == ATIVA else []
    return Matricula(**dict(linha._mapping), posicao_espera=posicao, conflitos=conflitos)


def obter_turma(conexao: Connection, programa_id: str, turma_id: str) -> TurmaDetalhada:
    """Turma com as matrículas ativas, a lista de espera em ordem e o histórico."""
    turma = buscar_turma(conexao, programa_id, turma_id)
    linhas = conexao.execute(
        sa.text(_MATRICULAS.format(filtro="") + " ORDER BY m.inscrito_em, m.id"), {"turma": turma_id}
    ).all()
    ativas = [_matricula(conexao, l, turma_id) for l in linhas if l.situacao == ATIVA]
    ativas.sort(key=lambda m: (m.pessoa.casefold(), m.id))
    espera = [_matricula(conexao, l, turma_id, i) for i, l in enumerate((l for l in linhas if l.situacao == ESPERA), 1)]
    desligadas = [_matricula(conexao, l, turma_id) for l in linhas if l.situacao == DESLIGADA]
    desligadas.sort(key=lambda m: (m.data_saida, m.id), reverse=True)
    return TurmaDetalhada(turma=turma, matriculas=ativas, lista_de_espera=espera, desligadas=desligadas)


def _buscar_matricula(conexao: Connection, turma_id: str, matricula_id: str) -> Matricula:
    linha = conexao.execute(
        sa.text(_MATRICULAS.format(filtro="AND m.id = :id")), {"turma": turma_id, "id": matricula_id}
    ).first()
    if linha is None:
        raise NaoEncontrado("Matrícula não encontrada.")
    posicao = None
    if linha.situacao == ESPERA:
        posicao = conexao.execute(
            sa.text(
                """
                SELECT count(*) FROM matriculas
                WHERE turma_id = :turma AND situacao = 'espera'
                  AND (inscrito_em, id) <= (:inscrito, :id)
                """
            ),
            {"turma": turma_id, "inscrito": linha.inscrito_em, "id": linha.id},
        ).scalar_one()
    return _matricula(conexao, linha, turma_id, posicao)


# --- Cadastro da turma -----------------------------------------------------------


def _texto(valor: Optional[str]) -> Optional[str]:
    valor = (valor or "").strip()
    return valor or None


def _validar_turma(conexao: Connection, programa_id: str, dados: Dict) -> None:
    faltando = [
        rotulo
        for chave, rotulo in [
            ("nome", "nome"),
            ("espaco_id", "local"),
            ("responsavel_id", "responsável"),
            ("capacidade", "vagas"),
            ("dias_semana", "dias da semana"),
            ("hora_inicio", "horário de início"),
            ("hora_fim", "horário de término"),
        ]
        if dados.get(chave) in (None, "", [])
    ]
    if faltando:
        raise DadosInvalidos("Turma sem " + _lista(faltando) + ".")
    if dados["capacidade"] <= 0:
        raise DadosInvalidos("A turma precisa de ao menos uma vaga.")
    dias = dados["dias_semana"]
    if any(d not in DIAS for d in dias):
        raise DadosInvalidos("Dias da semana válidos: 1 (segunda) a 7 (domingo).")
    if dados["hora_fim"] <= dados["hora_inicio"]:
        raise DadosInvalidos("O horário de término precisa ser depois do início.")
    if conexao.execute(
        sa.text("SELECT 1 FROM espacos WHERE id = :id AND programa_id = :programa"),
        {"id": dados["espaco_id"], "programa": programa_id},
    ).first() is None:
        raise DadosInvalidos("Escolha um local cadastrado neste programa.")
    if conexao.execute(
        sa.text(
            """
            SELECT 1 FROM vinculos_equipe v JOIN usuarios u ON u.id = v.usuario_id
            WHERE v.usuario_id = :usuario AND v.programa_id = :programa AND u.ativo
              AND (v.data_saida IS NULL OR v.data_saida > :hoje)
            """
        ),
        {"usuario": dados["responsavel_id"], "programa": programa_id, "hoje": date.today()},
    ).first() is None:
        raise DadosInvalidos("O responsável precisa ter vínculo ativo na equipe do programa.")


def _lista(itens: Sequence[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def _gravar(conexao: Connection, sql: str, parametros: Dict) -> None:
    # Savepoint: com nome repetido, só esta gravação é desfeita.
    try:
        with conexao.begin_nested():
            conexao.execute(sa.text(sql), parametros)
    except IntegrityError as erro:
        if getattr(erro.orig, "sqlstate", None) == UNIQUE_VIOLATION:
            raise Conflito("Já existe uma turma com esse nome neste programa.") from erro
        raise


def cadastrar_turma(conexao: Connection, programa_id: str, dados: Dict, *, usuario_id: str) -> Turma:
    dados = {**dados, "nome": _texto(dados.get("nome")), "dias_semana": sorted(set(dados.get("dias_semana") or []))}
    _validar_turma(conexao, programa_id, dados)
    turma_id = str(uuid.uuid4())
    _gravar(
        conexao,
        """
        INSERT INTO turmas (id, programa_id, nome, espaco_id, responsavel_id, capacidade,
                            dias_semana, hora_inicio, hora_fim, criado_por)
        VALUES (:id, :programa, :nome, :espaco_id, :responsavel_id, :capacidade,
                CAST(:dias_semana AS smallint[]), :hora_inicio, :hora_fim, :usuario)
        """,
        {**dados, "id": turma_id, "programa": programa_id, "usuario": usuario_id},
    )
    return buscar_turma(conexao, programa_id, turma_id)


CAMPOS_DA_TURMA = ("nome", "espaco_id", "responsavel_id", "capacidade", "dias_semana", "hora_inicio", "hora_fim")


def editar_turma(conexao: Connection, programa_id: str, turma_id: str, alteracoes: Dict) -> Turma:
    """Só os campos enviados mudam; a turma resultante segue as regras do cadastro."""
    atual = buscar_turma(conexao, programa_id, turma_id)
    dados = {campo: getattr(atual, campo) for campo in CAMPOS_DA_TURMA}
    dados.update({k: v for k, v in alteracoes.items() if k in CAMPOS_DA_TURMA})
    dados["nome"] = _texto(dados.get("nome"))
    dados["dias_semana"] = sorted(set(dados.get("dias_semana") or []))
    _validar_turma(conexao, programa_id, dados)
    if dados["capacidade"] < atual.ativas:
        raise Conflito(
            f"A turma tem {atual.ativas} matrículas ativas; a capacidade não pode ficar abaixo disso."
        )
    _gravar(
        conexao,
        """
        UPDATE turmas SET nome = :nome, espaco_id = :espaco_id, responsavel_id = :responsavel_id,
               capacidade = :capacidade, dias_semana = CAST(:dias_semana AS smallint[]),
               hora_inicio = :hora_inicio, hora_fim = :hora_fim
        WHERE id = :id
        """,
        {**dados, "id": turma_id},
    )
    return buscar_turma(conexao, programa_id, turma_id)


# --- Matrículas ----------------------------------------------------------------


def _travar_turma(conexao: Connection, programa_id: str, turma_id: str) -> Turma:
    """Bloqueia a turma até o fim da transação: duas inscrições ao mesmo tempo não
    conseguem ocupar a mesma última vaga."""
    if conexao.execute(
        sa.text("SELECT 1 FROM turmas WHERE id = :id AND programa_id = :programa FOR UPDATE"),
        {"id": turma_id, "programa": programa_id},
    ).first() is None:
        raise NaoEncontrado("Turma não encontrada.")
    return buscar_turma(conexao, programa_id, turma_id)


def inscrever(
    conexao: Connection, programa_id: str, turma_id: str, pessoa_id: str, *, usuario_id: str, hoje: Optional[date] = None
) -> Inscricao:
    """Matricula se há vaga; senão, coloca na lista de espera."""
    hoje = hoje or date.today()
    turma = _travar_turma(conexao, programa_id, turma_id)
    programa_da_pessoa = conexao.execute(
        sa.text("SELECT programa_id FROM pessoas WHERE id = :id"), {"id": pessoa_id}
    ).scalar_one_or_none()
    if programa_da_pessoa is None:
        raise NaoEncontrado("Pessoa não encontrada.")
    if programa_da_pessoa != programa_id:
        raise DadosInvalidos("A pessoa precisa estar cadastrada no mesmo programa da turma.")
    if conexao.execute(
        sa.text("SELECT 1 FROM matriculas WHERE turma_id = :turma AND pessoa_id = :pessoa AND situacao <> 'desligada'"),
        {"turma": turma_id, "pessoa": pessoa_id},
    ).first():
        raise Conflito("Essa pessoa já está matriculada ou na lista de espera desta turma.")

    situacao = ATIVA if turma.vagas_livres > 0 else ESPERA
    matricula_id = str(uuid.uuid4())
    conexao.execute(
        sa.text(
            """
            INSERT INTO matriculas (id, turma_id, pessoa_id, situacao, data_entrada, criado_por, inscrito_em)
            VALUES (:id, :turma, :pessoa, :situacao, :entrada, :usuario, clock_timestamp())
            """
        ),
        {
            "id": matricula_id,
            "turma": turma_id,
            "pessoa": pessoa_id,
            "situacao": situacao,
            "entrada": hoje if situacao == ATIVA else None,
            "usuario": usuario_id,
        },
    )
    conflitos = conflitos_de_horario(conexao, pessoa_id, turma_id, ignorar_matricula=matricula_id)
    return Inscricao(matricula=_buscar_matricula(conexao, turma_id, matricula_id), conflitos=conflitos)


def chamar_proximo(conexao: Connection, programa_id: str, turma_id: str, *, hoje: Optional[date] = None) -> Inscricao:
    """Passa o primeiro da lista de espera para a turma, se houver vaga."""
    hoje = hoje or date.today()
    turma = _travar_turma(conexao, programa_id, turma_id)
    if turma.vagas_livres <= 0:
        raise Conflito("A turma continua lotada. Registre um desligamento antes de chamar a lista de espera.")
    proxima = conexao.execute(
        sa.text(
            "SELECT id, pessoa_id FROM matriculas WHERE turma_id = :turma AND situacao = 'espera' "
            "ORDER BY inscrito_em, id LIMIT 1"
        ),
        {"turma": turma_id},
    ).first()
    if proxima is None:
        raise Conflito("A lista de espera está vazia.")
    conexao.execute(
        sa.text("UPDATE matriculas SET situacao = 'ativa', data_entrada = :hoje WHERE id = :id"),
        {"hoje": hoje, "id": proxima.id},
    )
    conflitos = conflitos_de_horario(conexao, proxima.pessoa_id, turma_id, ignorar_matricula=proxima.id)
    return Inscricao(matricula=_buscar_matricula(conexao, turma_id, proxima.id), conflitos=conflitos)


def desligar(
    conexao: Connection,
    programa_id: str,
    turma_id: str,
    matricula_id: str,
    *,
    data_saida: Optional[date],
    motivo: Optional[str],
) -> Matricula:
    """Encerra a matrícula (ou tira da lista de espera) com data e motivo obrigatórios."""
    buscar_turma(conexao, programa_id, turma_id)
    matricula = _buscar_matricula(conexao, turma_id, matricula_id)
    motivo = _texto(motivo)
    faltando = [rotulo for valor, rotulo in [(data_saida, "data"), (motivo, "motivo")] if not valor]
    if faltando:
        raise DadosInvalidos("Informe " + _lista(faltando) + " do desligamento.")
    if matricula.situacao == DESLIGADA:
        raise Conflito("Essa matrícula já foi encerrada.")
    inicio = matricula.data_entrada or matricula.inscrito_em.date()
    if data_saida < inicio:
        raise DadosInvalidos("A data do desligamento não pode ser anterior à entrada na turma.")
    conexao.execute(
        sa.text(
            "UPDATE matriculas SET situacao = 'desligada', data_saida = :saida, motivo_saida = :motivo WHERE id = :id"
        ),
        {"saida": data_saida, "motivo": motivo, "id": matricula_id},
    )
    return _buscar_matricula(conexao, turma_id, matricula_id)
