"""Atividades (encontros), chamadas e evidências (US-05, tabelas da T-55).

Regras aplicadas aqui:

- **Agenda:** os encontros previstos das turmas do programa num período (pelos dias da
  semana de cada turma), com os encontros já registrados.
- **Chamada:** é registrada junto com o encontro, quando ele é encerrado: data, turma,
  educador, conteúdo e quem esteve presente ou ausente. Só entra quem estava matriculado
  na turma naquela data. O encontro não pode estar no futuro.
- **Sincronização sem duplicar:** cada registro traz o ``registro_id`` gerado no aparelho.
  Recebido de novo (a fila offline reenviou), devolve o que já foi gravado, sem gravar
  outra vez. Vale a primeira versão recebida.
- **Evidência:** o arquivo vai para o bucket privado (R2) em ``gestao/evidencias/``; o
  banco guarda só os metadados, ligados à atividade, ao programa, ao autor e à data.

As funções não fazem commit: a rota decide quando a operação termina.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from Financeiro.comprovantes import TipoArquivo
from Gestao import turmas
from Gestao.erros import Conflito, DadosInvalidos, NaoEncontrado

UNIQUE_VIOLATION = "23505"
PREFIXO_EVIDENCIAS = "gestao/evidencias"
MAXIMO_DIAS_NA_AGENDA = 62

ATIVIDADE_NAO_ENCONTRADA = "Atividade não encontrada."
EVIDENCIA_NAO_ENCONTRADA = "Evidência não encontrada."
REGISTRO_DE_OUTRO_ENCONTRO = "Este identificador de registro já foi usado em outro encontro."
REGISTRO_DE_OUTRA_ATIVIDADE = "Este identificador de registro já foi usado em outra evidência."


# --- Modelos -------------------------------------------------------------------


@dataclass(frozen=True)
class Presenca:
    pessoa_id: str
    pessoa: str
    presente: bool
    justificativa: Optional[str]


@dataclass(frozen=True)
class Evidencia:
    id: str
    registro_id: str
    atividade_id: str
    programa_id: str
    autor_id: str
    autor: str
    data: date
    descricao: Optional[str]
    chave_arquivo: str
    nome_arquivo: str
    content_type: str
    tamanho: int
    criado_em: datetime


@dataclass(frozen=True)
class Atividade:
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
    criado_em: datetime
    chamada: List[Presenca] = field(default_factory=list)
    evidencias: List[Evidencia] = field(default_factory=list)

    @property
    def presentes(self) -> int:
        return sum(1 for p in self.chamada if p.presente)

    @property
    def ausentes(self) -> int:
        return sum(1 for p in self.chamada if not p.presente)


@dataclass(frozen=True)
class Encontro:
    """Um encontro na agenda: previsto pela turma, registrado, ou os dois."""

    data: date
    turma_id: str
    turma: str
    espaco: str
    responsavel_id: str
    responsavel: str
    hora_inicio: time
    hora_fim: time
    previsto: bool
    atividades: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class NovaPresenca:
    pessoa_id: str
    presente: bool
    justificativa: Optional[str] = None


@dataclass(frozen=True)
class NovaAtividade:
    registro_id: str
    data: date
    conteudo: str
    presencas: Sequence[NovaPresenca]
    educador_id: Optional[str] = None
    observacao: Optional[str] = None


# --- Apoio ---------------------------------------------------------------------


def _texto(valor: Optional[str]) -> Optional[str]:
    valor = (valor or "").strip()
    return valor or None


def _eh_duplicidade(erro: IntegrityError) -> bool:
    return getattr(erro.orig, "sqlstate", None) == UNIQUE_VIOLATION


def gerar_chave_evidencia(tipo: TipoArquivo, agora: Optional[datetime] = None) -> str:
    agora = agora or datetime.now(timezone.utc)
    return f"{PREFIXO_EVIDENCIAS}/{agora:%Y/%m}/{uuid.uuid4().hex}.{tipo.extensao}"


# --- Agenda --------------------------------------------------------------------


def agenda(conexao: Connection, programa_id: str, inicio: date, fim: date) -> List[Encontro]:
    if fim < inicio:
        raise DadosInvalidos("O fim do período não pode ser anterior ao início.")
    if (fim - inicio).days + 1 > MAXIMO_DIAS_NA_AGENDA:
        raise DadosInvalidos(f"Consulte no máximo {MAXIMO_DIAS_NA_AGENDA} dias de agenda por vez.")

    registradas: Dict[Tuple[str, date], List[str]] = {}
    for linha in conexao.execute(
        sa.text(
            """
            SELECT id, turma_id, data FROM atividades
            WHERE programa_id = :programa AND data BETWEEN :inicio AND :fim
            ORDER BY data, criado_em, id
            """
        ),
        {"programa": programa_id, "inicio": inicio, "fim": fim},
    ):
        registradas.setdefault((linha.turma_id, linha.data), []).append(linha.id)

    encontros = []
    for turma in turmas.listar_turmas(conexao, programa_id):
        dia = inicio
        while dia <= fim:
            previsto = dia.isoweekday() in turma.dias_semana
            ids = registradas.pop((turma.id, dia), [])
            if previsto or ids:
                encontros.append(
                    Encontro(
                        data=dia,
                        turma_id=turma.id,
                        turma=turma.nome,
                        espaco=turma.espaco,
                        responsavel_id=turma.responsavel_id,
                        responsavel=turma.responsavel,
                        hora_inicio=turma.hora_inicio,
                        hora_fim=turma.hora_fim,
                        previsto=previsto,
                        atividades=ids,
                    )
                )
            dia += timedelta(days=1)
    return sorted(encontros, key=lambda e: (e.data, e.hora_inicio, e.turma.lower(), e.turma_id))


# --- Atividade e chamada -------------------------------------------------------

_SELECIONAR_ATIVIDADE = """
    SELECT a.id, a.registro_id, a.programa_id, a.turma_id, t.nome AS turma, a.data,
           a.educador_id, u.nome AS educador, a.conteudo, a.observacao, a.criado_em
    FROM atividades a
    JOIN turmas t ON t.id = a.turma_id
    JOIN usuarios u ON u.id = a.educador_id
"""


def _chamada(conexao: Connection, atividade_id: str) -> List[Presenca]:
    linhas = conexao.execute(
        sa.text(
            """
            SELECT c.pessoa_id, p.nome AS pessoa, c.presente, c.justificativa
            FROM chamadas c JOIN pessoas p ON p.id = c.pessoa_id
            WHERE c.atividade_id = :id
            ORDER BY lower(p.nome), c.pessoa_id
            """
        ),
        {"id": atividade_id},
    )
    return [Presenca(**linha._mapping) for linha in linhas]


def obter_atividade(conexao: Connection, programa_id: str, atividade_id: str) -> Atividade:
    linha = conexao.execute(
        sa.text(f"{_SELECIONAR_ATIVIDADE} WHERE a.id = :id AND a.programa_id = :programa"),
        {"id": atividade_id, "programa": programa_id},
    ).first()
    if linha is None:
        raise NaoEncontrado(ATIVIDADE_NAO_ENCONTRADA)
    return Atividade(
        **linha._mapping,
        chamada=_chamada(conexao, atividade_id),
        evidencias=listar_evidencias(conexao, atividade_id),
    )


def _ja_recebida(
    conexao: Connection, programa_id: str, turma_id: str, registro_id: str
) -> Optional[Atividade]:
    linha = conexao.execute(
        sa.text("SELECT id, programa_id, turma_id FROM atividades WHERE registro_id = :registro"),
        {"registro": registro_id},
    ).first()
    if linha is None:
        return None
    if (linha.programa_id, linha.turma_id) != (programa_id, turma_id):
        raise Conflito(REGISTRO_DE_OUTRO_ENCONTRO, codigo="registro_id_em_uso")
    return obter_atividade(conexao, programa_id, linha.id)


def _validar_educador(conexao: Connection, programa_id: str, educador_id: str, data: date) -> None:
    vinculado = conexao.execute(
        sa.text(
            """
            SELECT 1 FROM vinculos_equipe v JOIN usuarios u ON u.id = v.usuario_id
            WHERE v.usuario_id = :usuario AND v.programa_id = :programa AND u.ativo
              AND v.data_entrada <= :data AND (v.data_saida IS NULL OR v.data_saida > :data)
            """
        ),
        {"usuario": educador_id, "programa": programa_id, "data": data},
    ).first()
    if vinculado is None:
        raise DadosInvalidos(
            "O educador precisa ter vínculo ativo com o programa na data do encontro.",
            codigo="educador_sem_vinculo",
        )


def _validar_presencas(
    conexao: Connection, turma_id: str, data: date, presencas: Sequence[NovaPresenca]
) -> List[NovaPresenca]:
    if not presencas:
        raise DadosInvalidos("Informe a chamada: quem esteve presente e quem faltou.", codigo="chamada_vazia")
    ids = [p.pessoa_id for p in presencas]
    repetidas = sorted({i for i in ids if ids.count(i) > 1})
    if repetidas:
        raise DadosInvalidos(
            "Cada pessoa aparece uma vez na chamada.", codigo="pessoa_repetida", dados={"pessoas": repetidas}
        )
    matriculadas = set(
        conexao.execute(
            sa.text(
                """
                SELECT pessoa_id FROM matriculas
                WHERE turma_id = :turma AND pessoa_id IN :pessoas
                  AND data_entrada IS NOT NULL AND data_entrada <= :data
                  AND (data_saida IS NULL OR data_saida > :data)
                """
            ).bindparams(sa.bindparam("pessoas", expanding=True)),
            {"turma": turma_id, "pessoas": ids, "data": data},
        ).scalars()
    )
    fora = [i for i in ids if i not in matriculadas]
    if fora:
        raise DadosInvalidos(
            "Há pessoas na chamada sem matrícula na turma nessa data.",
            codigo="fora_da_turma",
            dados={"pessoas": fora},
        )
    normalizadas = []
    for p in presencas:
        justificativa = _texto(p.justificativa)
        if p.presente and justificativa:
            raise DadosInvalidos(
                "Justificativa só vale para quem faltou.", codigo="justificativa_em_presenca"
            )
        normalizadas.append(NovaPresenca(p.pessoa_id, p.presente, justificativa))
    return normalizadas


def registrar_atividade(
    conexao: Connection,
    programa_id: str,
    turma_id: str,
    dados: NovaAtividade,
    *,
    usuario_id: str,
    hoje: Optional[date] = None,
) -> Tuple[Atividade, bool]:
    """Grava o encontro com a chamada. Devolve ``(atividade, criada)``; ``criada`` é falso
    quando o mesmo ``registro_id`` já tinha sido recebido."""
    registro_id = _texto(dados.registro_id)
    if not registro_id:
        raise DadosInvalidos("Informe o identificador do registro.", codigo="registro_id_obrigatorio")
    existente = _ja_recebida(conexao, programa_id, turma_id, registro_id)
    if existente is not None:
        return existente, False

    turmas.buscar_turma(conexao, programa_id, turma_id)
    conteudo = _texto(dados.conteudo)
    if not conteudo:
        raise DadosInvalidos("Informe o conteúdo trabalhado no encontro.", codigo="conteudo_obrigatorio")
    if dados.data > (hoje or date.today()):
        raise DadosInvalidos("A data do encontro não pode estar no futuro.", codigo="data_no_futuro")
    educador_id = _texto(dados.educador_id) or usuario_id
    _validar_educador(conexao, programa_id, educador_id, dados.data)
    presencas = _validar_presencas(conexao, turma_id, dados.data, dados.presencas)

    atividade_id = str(uuid.uuid4())
    try:
        # Savepoint: se outro envio do mesmo registro chegou primeiro, só esta gravação
        # é desfeita e devolvemos a que ficou.
        with conexao.begin_nested():
            conexao.execute(
                sa.text(
                    """
                    INSERT INTO atividades (id, registro_id, programa_id, turma_id, data,
                                            educador_id, conteudo, observacao, criado_por)
                    VALUES (:id, :registro, :programa, :turma, :data, :educador, :conteudo,
                            :observacao, :usuario)
                    """
                ),
                {
                    "id": atividade_id,
                    "registro": registro_id,
                    "programa": programa_id,
                    "turma": turma_id,
                    "data": dados.data,
                    "educador": educador_id,
                    "conteudo": conteudo,
                    "observacao": _texto(dados.observacao),
                    "usuario": usuario_id,
                },
            )
    except IntegrityError as erro:
        if not _eh_duplicidade(erro):
            raise
        return _ja_recebida(conexao, programa_id, turma_id, registro_id), False

    conexao.execute(
        sa.text(
            """
            INSERT INTO chamadas (id, atividade_id, pessoa_id, presente, justificativa)
            VALUES (:id, :atividade, :pessoa, :presente, :justificativa)
            """
        ),
        [
            {
                "id": str(uuid.uuid4()),
                "atividade": atividade_id,
                "pessoa": p.pessoa_id,
                "presente": p.presente,
                "justificativa": p.justificativa,
            }
            for p in presencas
        ],
    )
    return obter_atividade(conexao, programa_id, atividade_id), True


# --- Evidências ----------------------------------------------------------------

_SELECIONAR_EVIDENCIA = """
    SELECT e.id, e.registro_id, e.atividade_id, e.programa_id, e.autor_id, u.nome AS autor,
           e.data, e.descricao, e.chave_arquivo, e.nome_arquivo, e.content_type, e.tamanho,
           e.criado_em
    FROM evidencias e JOIN usuarios u ON u.id = e.autor_id
"""


def listar_evidencias(conexao: Connection, atividade_id: str) -> List[Evidencia]:
    linhas = conexao.execute(
        sa.text(f"{_SELECIONAR_EVIDENCIA} WHERE e.atividade_id = :id ORDER BY e.criado_em, e.id"),
        {"id": atividade_id},
    )
    return [Evidencia(**linha._mapping) for linha in linhas]


def obter_evidencia(conexao: Connection, programa_id: str, evidencia_id: str) -> Evidencia:
    linha = conexao.execute(
        sa.text(f"{_SELECIONAR_EVIDENCIA} WHERE e.id = :id AND e.programa_id = :programa"),
        {"id": evidencia_id, "programa": programa_id},
    ).first()
    if linha is None:
        raise NaoEncontrado(EVIDENCIA_NAO_ENCONTRADA)
    return Evidencia(**linha._mapping)


def evidencia_ja_recebida(
    conexao: Connection, programa_id: str, atividade_id: str, registro_id: str
) -> Optional[Evidencia]:
    """A evidência com esse ``registro_id``, se já chegou; consultada antes do envio do
    arquivo, para o reenvio não subir o mesmo arquivo outra vez."""
    linha = conexao.execute(
        sa.text("SELECT id, programa_id, atividade_id FROM evidencias WHERE registro_id = :registro"),
        {"registro": registro_id},
    ).first()
    if linha is None:
        return None
    if (linha.programa_id, linha.atividade_id) != (programa_id, atividade_id):
        raise Conflito(REGISTRO_DE_OUTRA_ATIVIDADE, codigo="registro_id_em_uso")
    return obter_evidencia(conexao, programa_id, linha.id)


def validar_data_da_evidencia(data: date, hoje: Optional[date] = None) -> None:
    if data > (hoje or date.today()):
        raise DadosInvalidos("A data da evidência não pode estar no futuro.", codigo="data_no_futuro")


def registrar_evidencia(
    conexao: Connection,
    atividade: Atividade,
    *,
    registro_id: str,
    autor_id: str,
    data: date,
    descricao: Optional[str],
    chave_arquivo: str,
    nome_arquivo: str,
    content_type: str,
    tamanho: int,
) -> Tuple[Evidencia, bool]:
    """Grava os metadados do arquivo já enviado. Devolve ``(evidencia, criada)``."""
    evidencia_id = str(uuid.uuid4())
    try:
        with conexao.begin_nested():
            conexao.execute(
                sa.text(
                    """
                    INSERT INTO evidencias (id, registro_id, atividade_id, programa_id, autor_id, data,
                                            descricao, chave_arquivo, nome_arquivo, content_type, tamanho)
                    VALUES (:id, :registro, :atividade, :programa, :autor, :data,
                            :descricao, :chave, :nome, :content_type, :tamanho)
                    """
                ),
                {
                    "id": evidencia_id,
                    "registro": registro_id,
                    "atividade": atividade.id,
                    "programa": atividade.programa_id,
                    "autor": autor_id,
                    "data": data,
                    "descricao": _texto(descricao),
                    "chave": chave_arquivo,
                    "nome": nome_arquivo,
                    "content_type": content_type,
                    "tamanho": tamanho,
                },
            )
    except IntegrityError as erro:
        if not _eh_duplicidade(erro):
            raise
        # Outro envio do mesmo registro gravou primeiro; o arquivo deste fica sem uso.
        existente = evidencia_ja_recebida(conexao, atividade.programa_id, atividade.id, registro_id)
        if existente is None:
            raise
        return existente, False
    return obter_evidencia(conexao, atividade.programa_id, evidencia_id), True
