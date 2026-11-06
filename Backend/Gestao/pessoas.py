"""Pessoas atendidas, núcleos familiares e responsáveis (US-03, tabelas da T-47).

Regras da US-03 aplicadas aqui:

- **Possível duplicidade:** mesmo nome (sem diferenciar maiúsculas, espaços e acentos)
  e, além disso, mesmo nascimento **ou** mesmo responsável. É um alerta: o cadastro só
  segue com a confirmação explícita de quem cadastra.
- **Responsável legal:** pessoa com menos de 18 anos precisa de ao menos um.

As funções não fazem commit: a rota decide quando a operação termina.
"""

import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from Gestao.autorizacoes import Autorizacao, autorizacoes_por_pessoa, listar_autorizacoes, situacao_de_imagem
from Gestao.erros import Conflito, DadosInvalidos, ErroDeCadastro, NaoEncontrado  # noqa: F401

MAIORIDADE = 18


# --- Normalização e idade ------------------------------------------------------


def normalizar_nome(nome: str) -> str:
    """'  Lára  OLIVEIRA ' → 'lara oliveira' (base da busca de duplicidade)."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", nome or "") if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.casefold().split())


def idade(nascimento: date, hoje: date) -> int:
    anos = hoje.year - nascimento.year
    return anos - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))


# --- Modelos -------------------------------------------------------------------


@dataclass(frozen=True)
class Responsavel:
    id: str
    nome: str
    telefone: Optional[str]
    parentesco: Optional[str]
    responsavel_legal: bool


@dataclass(frozen=True)
class NucleoFamiliar:
    id: str
    nome: str


@dataclass(frozen=True)
class Documento:
    id: str
    tipo: str
    nome_arquivo: str
    tamanho: Optional[int]
    criado_em: object


@dataclass(frozen=True)
class PessoaResumo:
    id: str
    nome: str
    data_nascimento: date
    programa_id: str
    programa: str
    nucleo_familiar: NucleoFamiliar
    responsaveis: List[str]
    situacao: str
    # Situação da autorização de uso de imagem: vigente, vencida, revogada ou sem_autorizacao.
    autorizacao_imagem: str


@dataclass(frozen=True)
class Pessoa:
    id: str
    nome: str
    data_nascimento: date
    idade: int
    programa_id: str
    programa: str
    nucleo_familiar: NucleoFamiliar
    telefone: Optional[str]
    observacao: Optional[str]
    situacao: str
    responsaveis: List[Responsavel] = field(default_factory=list)
    documentos: List[Documento] = field(default_factory=list)
    autorizacoes: List[Autorizacao] = field(default_factory=list)
    autorizacao_imagem: str = "sem_autorizacao"


@dataclass(frozen=True)
class PossivelDuplicado:
    id: str
    nome: str
    data_nascimento: date
    programa_id: str
    programa: str
    responsaveis: List[str]
    # Por que foi apontado: mesmo nascimento, mesmo responsável ou os dois.
    motivos: List[str]


@dataclass(frozen=True)
class NovoResponsavel:
    """Responsável existente (``id``) ou novo (``nome``), com o vínculo com a pessoa."""

    id: Optional[str] = None
    nome: Optional[str] = None
    telefone: Optional[str] = None
    parentesco: Optional[str] = None
    responsavel_legal: bool = False


@dataclass(frozen=True)
class NovaPessoa:
    nome: str
    data_nascimento: date
    programa_id: str
    nucleo_familiar_id: Optional[str] = None
    nucleo_familiar_nome: Optional[str] = None
    responsaveis: Sequence[NovoResponsavel] = ()
    telefone: Optional[str] = None
    observacao: Optional[str] = None


# --- Duplicidade ---------------------------------------------------------------


def _nomes_de_responsaveis(conexao: Connection, responsaveis: Iterable[NovoResponsavel]) -> List[str]:
    """Nomes normalizados dos responsáveis informados, novos ou já cadastrados."""
    nomes = {normalizar_nome(r.nome) for r in responsaveis if r.nome and not r.id}
    ids = [r.id for r in responsaveis if r.id]
    if ids:
        nomes |= set(
            conexao.execute(
                sa.text("SELECT nome_normalizado FROM responsaveis WHERE id IN :ids").bindparams(
                    sa.bindparam("ids", expanding=True)
                ),
                {"ids": ids},
            ).scalars()
        )
    return sorted(n for n in nomes if n)


def _responsaveis_por_pessoa(conexao: Connection, pessoa_ids: Sequence[str]) -> Dict[str, List[str]]:
    if not pessoa_ids:
        return {}
    resultado: Dict[str, List[str]] = {}
    for linha in conexao.execute(
        sa.text(
            """
            SELECT pr.pessoa_id, r.nome FROM pessoas_responsaveis pr
            JOIN responsaveis r ON r.id = pr.responsavel_id
            WHERE pr.pessoa_id IN :ids
            ORDER BY pr.responsavel_legal DESC, lower(r.nome)
            """
        ).bindparams(sa.bindparam("ids", expanding=True)),
        {"ids": list(pessoa_ids)},
    ):
        resultado.setdefault(linha.pessoa_id, []).append(linha.nome)
    return resultado


def buscar_duplicidades(
    conexao: Connection,
    *,
    nome: str,
    data_nascimento: date,
    responsaveis: Sequence[NovoResponsavel] = (),
    ignorar_id: Optional[str] = None,
) -> List[PossivelDuplicado]:
    nome_normalizado = normalizar_nome(nome)
    if not nome_normalizado:
        return []
    nomes_responsaveis = _nomes_de_responsaveis(conexao, responsaveis)
    # Lista vazia no IN não é SQL válido; um valor impossível mantém a consulta única.
    filtro_responsavel = nomes_responsaveis or [""]
    linhas = conexao.execute(
        sa.text(
            """
            SELECT p.id, p.nome, p.data_nascimento, p.programa_id, pr.nome AS programa,
                   p.data_nascimento = :nascimento AS mesmo_nascimento,
                   EXISTS (
                       SELECT 1 FROM pessoas_responsaveis pres
                       JOIN responsaveis r ON r.id = pres.responsavel_id
                       WHERE pres.pessoa_id = p.id AND r.nome_normalizado IN :responsaveis
                   ) AS mesmo_responsavel
            FROM pessoas p
            JOIN projetos pr ON pr.id = p.programa_id
            WHERE p.nome_normalizado = :nome
              AND (CAST(:ignorar AS text) IS NULL OR p.id <> CAST(:ignorar AS text))
            ORDER BY p.data_nascimento, p.id
            """
        ).bindparams(sa.bindparam("responsaveis", expanding=True)),
        {
            "nome": nome_normalizado,
            "nascimento": data_nascimento,
            "responsaveis": filtro_responsavel,
            "ignorar": ignorar_id,
        },
    ).all()
    candidatos = [l for l in linhas if l.mesmo_nascimento or l.mesmo_responsavel]
    responsaveis_de = _responsaveis_por_pessoa(conexao, [c.id for c in candidatos])
    return [
        PossivelDuplicado(
            id=c.id,
            nome=c.nome,
            data_nascimento=c.data_nascimento,
            programa_id=c.programa_id,
            programa=c.programa,
            responsaveis=responsaveis_de.get(c.id, []),
            motivos=[m for m, sim in (("nascimento", c.mesmo_nascimento), ("responsavel", c.mesmo_responsavel)) if sim],
        )
        for c in candidatos
    ]


# --- Cadastro ------------------------------------------------------------------


def _texto(valor: Optional[str]) -> Optional[str]:
    valor = (valor or "").strip()
    return valor or None


def _validar(conexao: Connection, dados: NovaPessoa, hoje: date) -> None:
    if not normalizar_nome(dados.nome):
        raise DadosInvalidos("Informe o nome da pessoa.")
    if dados.data_nascimento > hoje:
        raise DadosInvalidos("A data de nascimento não pode estar no futuro.")
    if not dados.nucleo_familiar_id and not _texto(dados.nucleo_familiar_nome):
        raise DadosInvalidos("Informe o núcleo familiar.")
    if dados.nucleo_familiar_id and conexao.execute(
        sa.text("SELECT 1 FROM nucleos_familiares WHERE id = :id"), {"id": dados.nucleo_familiar_id}
    ).first() is None:
        raise DadosInvalidos("Núcleo familiar não encontrado.")
    _validar_responsaveis(conexao, dados.responsaveis)
    if idade(dados.data_nascimento, hoje) < MAIORIDADE and not any(r.responsavel_legal for r in dados.responsaveis):
        raise DadosInvalidos(
            "Informe ao menos um responsável legal para uma pessoa menor de idade.",
            codigo="responsavel_legal_obrigatorio",
        )


def _validar_responsaveis(conexao: Connection, responsaveis: Sequence[NovoResponsavel]) -> None:
    ids = [r.id for r in responsaveis if r.id]
    if len(ids) != len(set(ids)):
        raise DadosInvalidos("O mesmo responsável foi informado mais de uma vez.")
    for r in responsaveis:
        if not r.id and not normalizar_nome(r.nome or ""):
            raise DadosInvalidos("Informe o nome de cada responsável.")
    if ids:
        existentes = set(
            conexao.execute(
                sa.text("SELECT id FROM responsaveis WHERE id IN :ids").bindparams(
                    sa.bindparam("ids", expanding=True)
                ),
                {"ids": ids},
            ).scalars()
        )
        if set(ids) - existentes:
            raise DadosInvalidos("Responsável não encontrado.")


def _vincular_responsaveis(conexao: Connection, pessoa_id: str, responsaveis: Sequence[NovoResponsavel]) -> None:
    for r in responsaveis:
        responsavel_id = r.id
        if not responsavel_id:
            responsavel_id = str(uuid.uuid4())
            conexao.execute(
                sa.text(
                    "INSERT INTO responsaveis (id, nome, nome_normalizado, telefone) "
                    "VALUES (:id, :nome, :normalizado, :telefone)"
                ),
                {
                    "id": responsavel_id,
                    "nome": r.nome.strip(),
                    "normalizado": normalizar_nome(r.nome),
                    "telefone": _texto(r.telefone),
                },
            )
        conexao.execute(
            sa.text(
                "INSERT INTO pessoas_responsaveis (pessoa_id, responsavel_id, parentesco, responsavel_legal) "
                "VALUES (:pessoa, :responsavel, :parentesco, :legal)"
            ),
            {
                "pessoa": pessoa_id,
                "responsavel": responsavel_id,
                "parentesco": _texto(r.parentesco),
                "legal": r.responsavel_legal,
            },
        )


def cadastrar(
    conexao: Connection,
    dados: NovaPessoa,
    *,
    usuario_id: str,
    confirmar_duplicidade: bool = False,
    hoje: Optional[date] = None,
) -> tuple:
    """Cadastra a pessoa; devolve ``(pessoa, duplicados_confirmados)``.

    Com possíveis duplicados e sem ``confirmar_duplicidade``, nada é gravado e a
    resposta é 409 com a lista, para quem cadastra conferir antes de concluir.
    """
    hoje = hoje or date.today()
    _validar(conexao, dados, hoje)
    duplicados = buscar_duplicidades(
        conexao, nome=dados.nome, data_nascimento=dados.data_nascimento, responsaveis=dados.responsaveis
    )
    if duplicados and not confirmar_duplicidade:
        raise Conflito(
            "Possível duplicidade: confira os cadastros semelhantes antes de concluir.",
            codigo="possivel_duplicidade",
            dados={"candidatos": duplicados},
        )

    nucleo_id = dados.nucleo_familiar_id
    if not nucleo_id:
        nucleo_id = str(uuid.uuid4())
        conexao.execute(
            sa.text("INSERT INTO nucleos_familiares (id, nome) VALUES (:id, :nome)"),
            {"id": nucleo_id, "nome": dados.nucleo_familiar_nome.strip()},
        )
    pessoa_id = str(uuid.uuid4())
    conexao.execute(
        sa.text(
            """
            INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id,
                                 programa_id, telefone, observacao, criado_por)
            VALUES (:id, :nome, :normalizado, :nascimento, :nucleo, :programa, :telefone, :observacao, :usuario)
            """
        ),
        {
            "id": pessoa_id,
            "nome": " ".join(dados.nome.split()),
            "normalizado": normalizar_nome(dados.nome),
            "nascimento": dados.data_nascimento,
            "nucleo": nucleo_id,
            "programa": dados.programa_id,
            "telefone": _texto(dados.telefone),
            "observacao": _texto(dados.observacao),
            "usuario": usuario_id,
        },
    )
    _vincular_responsaveis(conexao, pessoa_id, dados.responsaveis)
    return obter(conexao, pessoa_id, hoje=hoje), duplicados


def incluir_responsavel(
    conexao: Connection, pessoa_id: str, responsavel: NovoResponsavel, *, hoje: Optional[date] = None
) -> Pessoa:
    _validar_responsaveis(conexao, [responsavel])
    if responsavel.id and conexao.execute(
        sa.text("SELECT 1 FROM pessoas_responsaveis WHERE pessoa_id = :p AND responsavel_id = :r"),
        {"p": pessoa_id, "r": responsavel.id},
    ).first():
        raise Conflito("Esse responsável já está vinculado a esta pessoa.")
    _vincular_responsaveis(conexao, pessoa_id, [responsavel])
    return obter(conexao, pessoa_id, hoje=hoje)


def registrar_documento(
    conexao: Connection,
    pessoa_id: str,
    *,
    tipo: str,
    nome_arquivo: str,
    tamanho: Optional[int],
    usuario_id: str,
) -> Documento:
    if not _texto(tipo) or not _texto(nome_arquivo):
        raise DadosInvalidos("Informe o tipo e o nome do arquivo.")
    documento_id = str(uuid.uuid4())
    linha = conexao.execute(
        sa.text(
            """
            INSERT INTO documentos_pessoa (id, pessoa_id, tipo, nome_arquivo, tamanho, criado_por)
            VALUES (:id, :pessoa, :tipo, :nome, :tamanho, :usuario)
            RETURNING id, tipo, nome_arquivo, tamanho, criado_em
            """
        ),
        {
            "id": documento_id,
            "pessoa": pessoa_id,
            "tipo": tipo.strip(),
            "nome": nome_arquivo.strip(),
            "tamanho": tamanho,
            "usuario": usuario_id,
        },
    ).one()
    return Documento(**linha._mapping)


# --- Consulta ------------------------------------------------------------------


def obter(conexao: Connection, pessoa_id: str, *, hoje: Optional[date] = None) -> Pessoa:
    hoje = hoje or date.today()
    linha = conexao.execute(
        sa.text(
            """
            SELECT p.id, p.nome, p.data_nascimento, p.programa_id, pr.nome AS programa,
                   p.telefone, p.observacao, p.situacao, n.id AS nucleo_id, n.nome AS nucleo_nome
            FROM pessoas p
            JOIN projetos pr ON pr.id = p.programa_id
            JOIN nucleos_familiares n ON n.id = p.nucleo_familiar_id
            WHERE p.id = :id
            """
        ),
        {"id": pessoa_id},
    ).first()
    if linha is None:
        raise NaoEncontrado("Pessoa não encontrada.")
    responsaveis = [
        Responsavel(**r._mapping)
        for r in conexao.execute(
            sa.text(
                """
                SELECT r.id, r.nome, r.telefone, pr.parentesco, pr.responsavel_legal
                FROM pessoas_responsaveis pr JOIN responsaveis r ON r.id = pr.responsavel_id
                WHERE pr.pessoa_id = :id
                ORDER BY pr.responsavel_legal DESC, lower(r.nome), r.id
                """
            ),
            {"id": pessoa_id},
        )
    ]
    documentos = [
        Documento(**d._mapping)
        for d in conexao.execute(
            sa.text(
                "SELECT id, tipo, nome_arquivo, tamanho, criado_em FROM documentos_pessoa "
                "WHERE pessoa_id = :id ORDER BY criado_em, id"
            ),
            {"id": pessoa_id},
        )
    ]
    autorizacoes = listar_autorizacoes(conexao, pessoa_id, hoje=hoje)
    return Pessoa(
        id=linha.id,
        nome=linha.nome,
        data_nascimento=linha.data_nascimento,
        idade=idade(linha.data_nascimento, hoje),
        programa_id=linha.programa_id,
        programa=linha.programa,
        nucleo_familiar=NucleoFamiliar(id=linha.nucleo_id, nome=linha.nucleo_nome),
        telefone=linha.telefone,
        observacao=linha.observacao,
        situacao=linha.situacao,
        responsaveis=responsaveis,
        documentos=documentos,
        autorizacoes=autorizacoes,
        autorizacao_imagem=situacao_de_imagem(autorizacoes),
    )


def programa_da_pessoa(conexao: Connection, pessoa_id: str) -> Optional[str]:
    return conexao.execute(
        sa.text("SELECT programa_id FROM pessoas WHERE id = :id"), {"id": pessoa_id}
    ).scalar_one_or_none()


def listar(
    conexao: Connection,
    *,
    programas: Optional[Sequence[str]],
    busca: str = "",
    hoje: Optional[date] = None,
) -> List[PessoaResumo]:
    """Pessoas dos ``programas`` informados (``None`` = todos), com busca por nome,
    núcleo ou responsável."""
    hoje = hoje or date.today()
    if programas is not None and not programas:
        return []
    filtros = []
    params: dict = {}
    if programas is not None:
        filtros.append("p.programa_id IN :programas")
        params["programas"] = list(programas)
    termo = normalizar_nome(busca)
    if termo:
        filtros.append(
            """(p.nome_normalizado LIKE :termo OR lower(n.nome) LIKE :termo_bruto OR EXISTS (
                   SELECT 1 FROM pessoas_responsaveis pres JOIN responsaveis r ON r.id = pres.responsavel_id
                   WHERE pres.pessoa_id = p.id AND r.nome_normalizado LIKE :termo))"""
        )
        params["termo"] = f"%{termo}%"
        params["termo_bruto"] = f"%{busca.strip().lower()}%"
    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    consulta = sa.text(
        f"""
        SELECT p.id, p.nome, p.data_nascimento, p.programa_id, pr.nome AS programa,
               p.situacao, n.id AS nucleo_id, n.nome AS nucleo_nome
        FROM pessoas p
        JOIN projetos pr ON pr.id = p.programa_id
        JOIN nucleos_familiares n ON n.id = p.nucleo_familiar_id
        {where}
        ORDER BY p.nome_normalizado, p.id
        """
    )
    if programas is not None:
        consulta = consulta.bindparams(sa.bindparam("programas", expanding=True))
    linhas = conexao.execute(consulta, params).all()
    ids = [l.id for l in linhas]
    responsaveis_de = _responsaveis_por_pessoa(conexao, ids)
    autorizacoes_de = autorizacoes_por_pessoa(conexao, ids, hoje=hoje)
    imagem_de = {i: situacao_de_imagem(autorizacoes_de.get(i, [])) for i in ids}
    return [
        PessoaResumo(
            id=l.id,
            nome=l.nome,
            data_nascimento=l.data_nascimento,
            programa_id=l.programa_id,
            programa=l.programa,
            nucleo_familiar=NucleoFamiliar(id=l.nucleo_id, nome=l.nucleo_nome),
            responsaveis=responsaveis_de.get(l.id, []),
            situacao=l.situacao,
            autorizacao_imagem=imagem_de[l.id],
        )
        for l in linhas
    ]


def buscar_nucleos(
    conexao: Connection, *, programas: Optional[Sequence[str]], busca: str = ""
) -> List[NucleoFamiliar]:
    """Núcleos com alguém nos ``programas`` informados (``None`` = todos)."""
    if programas is not None and not programas:
        return []
    filtros = ["lower(n.nome) LIKE :busca"]
    params: dict = {"busca": f"%{busca.strip().lower()}%"}
    if programas is not None:
        filtros.append(
            "EXISTS (SELECT 1 FROM pessoas p WHERE p.nucleo_familiar_id = n.id AND p.programa_id IN :programas)"
        )
        params["programas"] = list(programas)
    consulta = sa.text(
        f"SELECT n.id, n.nome FROM nucleos_familiares n WHERE {' AND '.join(filtros)} "
        "ORDER BY lower(n.nome), n.id LIMIT 50"
    )
    if programas is not None:
        consulta = consulta.bindparams(sa.bindparam("programas", expanding=True))
    return [NucleoFamiliar(**l._mapping) for l in conexao.execute(consulta, params)]
