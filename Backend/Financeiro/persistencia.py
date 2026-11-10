"""Onde o Financeiro guarda os dados: PostgreSQL ou memória.

**Com ``DATABASE_URL``** (Cloud Run, ou local com ``Backend/.env``), tudo vai para o
PostgreSQL compartilhado com a Gestão, nas tabelas das migrations do Alembic
(``Backend/Shared/migrations``):

- ``projetos`` — o cadastro canônico de programas, o mesmo da Gestão;
- ``orcamentos`` + ``orcamento_categorias`` — orçamento, vigência e valor por categoria;
- ``lancamentos`` — despesas, aprovação, rejeição, reenvio e conciliação;
- ``notificacoes`` e ``rascunhos_despesa``.

O saldo não é gravado: é recalculado dos lançamentos aprovados toda vez que o orçamento
é lido, como já acontecia em memória.

**Sem ``DATABASE_URL``** (ou com ``FINANCEIRO_ARMAZENAMENTO=memoria``), os dados ficam
em memória e somem quando a API reinicia. Serve aos testes e a quem roda local sem banco.

Como as rotas usam: recebem o repositório por ``Depends(obter_repositorio)``, alteram
os objetos de domínio (``Orcamento``, ``Lancamento``...) com as mesmas regras de antes,
mandam salvar e chamam ``repositorio.confirmar()`` antes de responder. Assim o commit
acontece antes da resposta sair; se algo der errado no meio, nada é gravado. Para
alterar um orçamento, ele é lido com ``para_alterar=True`` (``SELECT ... FOR UPDATE``):
duas aprovações ao mesmo tempo no mesmo orçamento esperam uma pela outra, mesmo com
mais de uma instância da API no Cloud Run.
"""

import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, List, Optional

from Shared import sessao

if __package__:
    from .alerta_saldo import _em_centavos
    from .notificacoes import (
        CaixaDeNotificacoes,
        Notificacao,
        NotificacaoNaoEncontrada,
        TipoNotificacao,
        caixa_de_notificacoes,
        criar_notificacao,
    )
    from .orcamento import Lancamento, Orcamento, StatusLancamento
    from .projetos import Projeto, StatusProjeto, _projetos, _trava, ordenar
    from .rascunhos import CaixaDeRascunhos, Rascunho, RascunhoNaoEncontrado, caixa_de_rascunhos
else:
    from alerta_saldo import _em_centavos
    from notificacoes import (
        CaixaDeNotificacoes,
        Notificacao,
        NotificacaoNaoEncontrada,
        TipoNotificacao,
        caixa_de_notificacoes,
        criar_notificacao,
    )
    from orcamento import Lancamento, Orcamento, StatusLancamento
    from projetos import Projeto, StatusProjeto, _projetos, _trava, ordenar
    from rascunhos import CaixaDeRascunhos, Rascunho, RascunhoNaoEncontrado, caixa_de_rascunhos

logger = logging.getLogger(__name__)

VARIAVEL_ARMAZENAMENTO = "FINANCEIRO_ARMAZENAMENTO"


def usa_banco() -> bool:
    """Banco quando há ``DATABASE_URL``, a não ser que a memória seja pedida."""
    if os.getenv(VARIAVEL_ARMAZENAMENTO, "").strip().lower() == "memoria":
        return False
    return bool(os.getenv("DATABASE_URL", "").strip())


# --- Memória ------------------------------------------------------------------

# Orçamentos em memória. ``routers/orcamentos.py`` reexporta esta lista como
# ``_orcamentos``, que os testes preenchem e esvaziam diretamente.
ORCAMENTOS_EM_MEMORIA: List[Orcamento] = []


class RepositorioMemoria:
    """Os mesmos objetos de sempre, em listas do processo. Salvar não faz nada:
    as rotas alteram os próprios objetos guardados."""

    def __init__(
        self,
        projetos: List[Projeto],
        orcamentos: List[Orcamento],
        notificacoes: CaixaDeNotificacoes,
        rascunhos: CaixaDeRascunhos,
    ) -> None:
        self._projetos = projetos
        self._orcamentos = orcamentos
        self._notificacoes = notificacoes
        self._rascunhos = rascunhos

    def confirmar(self) -> None:
        pass

    # Projetos
    @contextmanager
    def cadastro_de_projetos(self) -> Iterator[None]:
        with _trava:
            yield

    def listar_projetos(self) -> List[Projeto]:
        with _trava:
            return ordenar(list(self._projetos))

    def buscar_projeto(self, projeto_id: str) -> Optional[Projeto]:
        with _trava:
            return next((p for p in self._projetos if p.id == projeto_id), None)

    def inserir_projeto(self, projeto: Projeto) -> None:
        with _trava:
            self._projetos.append(projeto)

    def salvar_status_projeto(self, projeto: Projeto) -> None:
        pass

    # Orçamentos e lançamentos
    def listar_orcamentos(self) -> List[Orcamento]:
        return list(self._orcamentos)

    def buscar_orcamento(self, orcamento_id: str, para_alterar: bool = False) -> Optional[Orcamento]:
        return next((o for o in self._orcamentos if o.id == orcamento_id), None)

    def buscar_orcamento_do_lancamento(
        self, lancamento_id: str, para_alterar: bool = False
    ) -> Optional[Orcamento]:
        return next(
            (o for o in self._orcamentos if any(l.id == lancamento_id for l in o.lancamentos)),
            None,
        )

    def inserir_orcamento(self, orcamento: Orcamento) -> None:
        self._orcamentos.append(orcamento)

    def salvar_orcamento(self, orcamento: Orcamento) -> None:
        pass

    def salvar_lancamento(self, orcamento: Orcamento, lancamento: Lancamento) -> None:
        pass

    # Notificações
    def notificar_resultado(self, lancamento: Lancamento) -> Optional[Notificacao]:
        return self._notificacoes.notificar_resultado(lancamento)

    def listar_notificacoes(self, destinatario_id: str, apenas_nao_lidas: bool = False) -> List[Notificacao]:
        return self._notificacoes.listar(destinatario_id, apenas_nao_lidas)

    def marcar_notificacao_como_lida(self, notificacao_id: str, destinatario_id: str) -> Notificacao:
        return self._notificacoes.marcar_como_lida(notificacao_id, destinatario_id)

    # Rascunhos
    def guardar_rascunho(self, rascunho: Rascunho) -> Rascunho:
        return self._rascunhos.criar(rascunho)

    def rascunhos_do_autor(self, autor_id: str) -> List[Rascunho]:
        return self._rascunhos.do_autor(autor_id)

    def retirar_rascunho(self, rascunho_id: str, autor_id: str) -> Rascunho:
        return self._rascunhos.retirar(rascunho_id, autor_id)


MEMORIA = RepositorioMemoria(
    _projetos, ORCAMENTOS_EM_MEMORIA, caixa_de_notificacoes, caixa_de_rascunhos
)


# --- PostgreSQL ---------------------------------------------------------------


def _valor(numero) -> Optional[float]:
    return None if numero is None else float(numero)


def _utc(momento: Optional[datetime]) -> Optional[datetime]:
    if momento is None or momento.tzinfo is not None:
        return momento
    return momento.replace(tzinfo=timezone.utc)


def _chave_do_comprovante(comprovante_url: Optional[str]) -> Optional[str]:
    # A coluna guarda o caminho que a API mostra ("/comprovantes/AAAA/MM/arquivo");
    # a chave no R2 é o mesmo texto sem a barra inicial.
    if not comprovante_url:
        return None
    return comprovante_url[1:] if comprovante_url.startswith("/") else comprovante_url


class RepositorioBanco:
    """Lê e grava nas tabelas do PostgreSQL usando a conexão da requisição.

    Nada é confirmado até ``confirmar()``; ao fechar a conexão sem confirmar, tudo
    o que a requisição fez é desfeito.
    """

    def __init__(self, conexao) -> None:
        import sqlalchemy as sa

        self._sa = sa
        self._conexao = conexao

    def _executar(self, sql: str, parametros: Optional[dict] = None):
        return self._conexao.execute(self._sa.text(sql), parametros or {})

    def confirmar(self) -> None:
        self._conexao.commit()

    # Projetos ------------------------------------------------------------------

    @contextmanager
    def cadastro_de_projetos(self) -> Iterator[None]:
        # Trava só até o fim da transação: impede dois cadastros com o mesmo nome
        # em requisições simultâneas, sem bloquear o resto do banco.
        self._executar("SELECT pg_advisory_xact_lock(hashtext('financeiro.cadastro_de_projetos'))")
        yield

    @staticmethod
    def _projeto(linha) -> Projeto:
        return Projeto(nome=linha.nome, id=linha.id, status=StatusProjeto(linha.status))

    def listar_projetos(self) -> List[Projeto]:
        linhas = self._executar("SELECT id, nome, status FROM projetos")
        return ordenar([self._projeto(linha) for linha in linhas])

    def buscar_projeto(self, projeto_id: str) -> Optional[Projeto]:
        linha = self._executar(
            "SELECT id, nome, status FROM projetos WHERE id = :id", {"id": projeto_id}
        ).first()
        return None if linha is None else self._projeto(linha)

    def inserir_projeto(self, projeto: Projeto) -> None:
        # Só nome e status: os demais campos do programa (identificador, vigência,
        # público...) são cadastrados pela Gestão.
        self._executar(
            "INSERT INTO projetos (id, nome, status) VALUES (:id, :nome, :status)",
            {"id": projeto.id, "nome": projeto.nome, "status": projeto.status.value},
        )

    def salvar_status_projeto(self, projeto: Projeto) -> None:
        self._executar(
            "UPDATE projetos SET status = :status WHERE id = :id",
            {"id": projeto.id, "status": projeto.status.value},
        )

    # Orçamentos e lançamentos ------------------------------------------------

    _COLUNAS_LANCAMENTO = """
        id, orcamento_id, categoria, valor, data, descricao, status, comprovante_url,
        motivo_rejeicao, motivos_rejeicao_anteriores, autor_id, conciliado,
        item_extrato_ref, criado_em, aprovado_em
    """

    def _carregar_orcamentos(
        self, filtro: str = "", parametros: Optional[dict] = None, para_alterar: bool = False
    ) -> List[Orcamento]:
        linhas = self._executar(
            "SELECT id, projeto_id, valor_total, periodo_inicio, periodo_fim, categorias "
            f"FROM orcamentos {filtro} ORDER BY periodo_inicio, id"
            + (" FOR UPDATE" if para_alterar else ""),
            parametros,
        ).all()
        if not linhas:
            return []
        ids = [linha.id for linha in linhas]

        valores: dict = {orcamento_id: {} for orcamento_id in ids}
        for linha in self._executar(
            "SELECT orcamento_id, nome, valor_orcado FROM orcamento_categorias "
            "WHERE orcamento_id = ANY(:ids)",
            {"ids": ids},
        ):
            valores[linha.orcamento_id][linha.nome] = float(linha.valor_orcado)

        lancamentos: dict = {orcamento_id: [] for orcamento_id in ids}
        for linha in self._executar(
            f"SELECT {self._COLUNAS_LANCAMENTO} FROM lancamentos "
            "WHERE orcamento_id = ANY(:ids) ORDER BY criado_em, id",
            {"ids": ids},
        ):
            lancamentos[linha.orcamento_id].append(
                Lancamento(
                    id=linha.id,
                    valor=float(linha.valor),
                    status=StatusLancamento(linha.status),
                    descricao=linha.descricao,
                    categoria=linha.categoria,
                    data_despesa=linha.data,
                    comprovante_chave=_chave_do_comprovante(linha.comprovante_url),
                    motivo_rejeicao=linha.motivo_rejeicao,
                    motivos_rejeicao_anteriores=list(linha.motivos_rejeicao_anteriores or []),
                    autor_id=linha.autor_id,
                    criado_em=_utc(linha.criado_em),
                    aprovado_em=_utc(linha.aprovado_em),
                    conciliado=linha.conciliado,
                    referencia_extrato=linha.item_extrato_ref,
                )
            )

        # O saldo é calculado pelo próprio Orcamento a partir dos aprovados.
        return [
            Orcamento(
                id=linha.id,
                projeto_id=linha.projeto_id,
                valor_total=float(linha.valor_total),
                data_inicio=linha.periodo_inicio,
                data_fim=linha.periodo_fim,
                categorias_despesa=list(linha.categorias),
                lancamentos=lancamentos[linha.id],
                valores_categorias=valores[linha.id],
            )
            for linha in linhas
        ]

    def listar_orcamentos(self) -> List[Orcamento]:
        return self._carregar_orcamentos()

    def buscar_orcamento(self, orcamento_id: str, para_alterar: bool = False) -> Optional[Orcamento]:
        encontrados = self._carregar_orcamentos(
            "WHERE id = :id", {"id": orcamento_id}, para_alterar
        )
        return encontrados[0] if encontrados else None

    def buscar_orcamento_do_lancamento(
        self, lancamento_id: str, para_alterar: bool = False
    ) -> Optional[Orcamento]:
        orcamento_id = self._executar(
            "SELECT orcamento_id FROM lancamentos WHERE id = :id", {"id": lancamento_id}
        ).scalar_one_or_none()
        if orcamento_id is None:
            return None
        return self.buscar_orcamento(orcamento_id, para_alterar)

    def _gravar_categorias(self, orcamento: Orcamento) -> None:
        self._executar(
            "DELETE FROM orcamento_categorias WHERE orcamento_id = :id", {"id": orcamento.id}
        )
        for nome, valor in orcamento.valores_categorias.items():
            self._executar(
                "INSERT INTO orcamento_categorias (orcamento_id, nome, valor_orcado) "
                "VALUES (:id, :nome, :valor)",
                {"id": orcamento.id, "nome": nome, "valor": _em_centavos(valor)},
            )

    def inserir_orcamento(self, orcamento: Orcamento) -> None:
        self._executar(
            """
            INSERT INTO orcamentos (id, projeto_id, valor_total, periodo_inicio, periodo_fim, categorias)
            VALUES (:id, :projeto_id, :valor_total, :inicio, :fim, :categorias)
            """,
            {
                "id": orcamento.id,
                "projeto_id": orcamento.projeto_id,
                "valor_total": _em_centavos(orcamento.valor_total),
                "inicio": orcamento.data_inicio,
                "fim": orcamento.data_fim,
                "categorias": list(orcamento.categorias_despesa),
            },
        )
        self._gravar_categorias(orcamento)
        for lancamento in orcamento.lancamentos:
            self.salvar_lancamento(orcamento, lancamento)

    def salvar_orcamento(self, orcamento: Orcamento) -> None:
        """Grava valor, vigência e categorias depois de uma edição."""
        self._executar(
            """
            UPDATE orcamentos SET valor_total = :valor_total, periodo_inicio = :inicio,
                periodo_fim = :fim, categorias = :categorias
            WHERE id = :id
            """,
            {
                "id": orcamento.id,
                "valor_total": _em_centavos(orcamento.valor_total),
                "inicio": orcamento.data_inicio,
                "fim": orcamento.data_fim,
                "categorias": list(orcamento.categorias_despesa),
            },
        )
        self._gravar_categorias(orcamento)

    def salvar_lancamento(self, orcamento: Orcamento, lancamento: Lancamento) -> None:
        """Insere o lançamento novo ou grava o estado atual de um existente."""
        self._executar(
            """
            INSERT INTO lancamentos (
                id, projeto_id, orcamento_id, categoria, valor, data, descricao, status,
                comprovante_url, motivo_rejeicao, motivos_rejeicao_anteriores, autor_id,
                conciliado, item_extrato_ref, criado_em, aprovado_em
            ) VALUES (
                :id, :projeto_id, :orcamento_id, :categoria, :valor, :data, :descricao, :status,
                :comprovante_url, :motivo_rejeicao, :motivos_anteriores, :autor_id,
                :conciliado, :item_extrato_ref, :criado_em, :aprovado_em
            )
            ON CONFLICT (id) DO UPDATE SET
                categoria = EXCLUDED.categoria,
                valor = EXCLUDED.valor,
                data = EXCLUDED.data,
                descricao = EXCLUDED.descricao,
                status = EXCLUDED.status,
                comprovante_url = EXCLUDED.comprovante_url,
                motivo_rejeicao = EXCLUDED.motivo_rejeicao,
                motivos_rejeicao_anteriores = EXCLUDED.motivos_rejeicao_anteriores,
                conciliado = EXCLUDED.conciliado,
                item_extrato_ref = EXCLUDED.item_extrato_ref,
                criado_em = EXCLUDED.criado_em,
                aprovado_em = EXCLUDED.aprovado_em
            """,
            {
                "id": lancamento.id,
                "projeto_id": orcamento.projeto_id,
                "orcamento_id": orcamento.id,
                "categoria": lancamento.categoria,
                "valor": _em_centavos(lancamento.valor),
                "data": lancamento.data_despesa,
                "descricao": lancamento.descricao,
                "status": lancamento.status.value,
                "comprovante_url": (
                    f"/{lancamento.comprovante_chave}" if lancamento.comprovante_chave else None
                ),
                "motivo_rejeicao": lancamento.motivo_rejeicao,
                "motivos_anteriores": list(lancamento.motivos_rejeicao_anteriores),
                "autor_id": lancamento.autor_id,
                "conciliado": lancamento.conciliado,
                "item_extrato_ref": lancamento.referencia_extrato,
                "criado_em": lancamento.criado_em,
                "aprovado_em": lancamento.aprovado_em,
            },
        )

    # Notificações -------------------------------------------------------------

    @staticmethod
    def _notificacao(linha) -> Notificacao:
        return Notificacao(
            id=linha.id,
            destinatario_id=linha.destinatario_id,
            lancamento_id=linha.lancamento_id,
            tipo=TipoNotificacao(linha.tipo),
            mensagem=linha.mensagem,
            motivo=linha.motivo,
            lida=linha.lida,
            criada_em=_utc(linha.criada_em),
        )

    def notificar_resultado(self, lancamento: Lancamento) -> Optional[Notificacao]:
        notificacao = criar_notificacao(lancamento)
        if notificacao is None:
            return None
        self._executar(
            """
            INSERT INTO notificacoes (id, destinatario_id, lancamento_id, tipo, mensagem,
                                      motivo, lida, criada_em)
            VALUES (:id, :destinatario, :lancamento, :tipo, :mensagem, :motivo, :lida, :criada_em)
            """,
            {
                "id": notificacao.id,
                "destinatario": notificacao.destinatario_id,
                "lancamento": notificacao.lancamento_id,
                "tipo": notificacao.tipo.value,
                "mensagem": notificacao.mensagem,
                "motivo": notificacao.motivo,
                "lida": notificacao.lida,
                "criada_em": notificacao.criada_em,
            },
        )
        return notificacao

    def listar_notificacoes(self, destinatario_id: str, apenas_nao_lidas: bool = False) -> List[Notificacao]:
        filtro = " AND NOT lida" if apenas_nao_lidas else ""
        linhas = self._executar(
            "SELECT * FROM notificacoes WHERE destinatario_id = :destinatario"
            f"{filtro} ORDER BY criada_em DESC, id DESC",
            {"destinatario": destinatario_id},
        )
        return [self._notificacao(linha) for linha in linhas]

    def marcar_notificacao_como_lida(self, notificacao_id: str, destinatario_id: str) -> Notificacao:
        # Notificação de outro usuário responde como inexistente.
        linha = self._executar(
            "UPDATE notificacoes SET lida = true "
            "WHERE id = :id AND destinatario_id = :destinatario RETURNING *",
            {"id": notificacao_id, "destinatario": destinatario_id},
        ).first()
        if linha is None:
            raise NotificacaoNaoEncontrada("Notificação não encontrada")
        return self._notificacao(linha)

    # Rascunhos ----------------------------------------------------------------

    @staticmethod
    def _rascunho(linha) -> Rascunho:
        return Rascunho(
            id=linha.id,
            autor_id=linha.autor_id,
            comprovante_chave=linha.comprovante_chave,
            nome_original=linha.nome_original,
            content_type=linha.content_type,
            tamanho=linha.tamanho,
            criado_em=_utc(linha.criado_em),
        )

    def guardar_rascunho(self, rascunho: Rascunho) -> Rascunho:
        self._executar(
            """
            INSERT INTO rascunhos_despesa (id, autor_id, comprovante_chave, nome_original,
                                           content_type, tamanho, criado_em)
            VALUES (:id, :autor, :chave, :nome, :tipo, :tamanho, :criado_em)
            """,
            {
                "id": rascunho.id,
                "autor": rascunho.autor_id,
                "chave": rascunho.comprovante_chave,
                "nome": rascunho.nome_original,
                "tipo": rascunho.content_type,
                "tamanho": rascunho.tamanho,
                "criado_em": rascunho.criado_em,
            },
        )
        return rascunho

    def rascunhos_do_autor(self, autor_id: str) -> List[Rascunho]:
        linhas = self._executar(
            "SELECT * FROM rascunhos_despesa WHERE autor_id = :autor "
            "ORDER BY criado_em DESC, id DESC",
            {"autor": autor_id},
        )
        return [self._rascunho(linha) for linha in linhas]

    def retirar_rascunho(self, rascunho_id: str, autor_id: str) -> Rascunho:
        linha = self._executar(
            "DELETE FROM rascunhos_despesa WHERE id = :id AND autor_id = :autor RETURNING *",
            {"id": rascunho_id, "autor": autor_id},
        ).first()
        if linha is None:
            raise RascunhoNaoEncontrado("Rascunho não encontrado")
        return self._rascunho(linha)


# --- Dependência das rotas ------------------------------------------------------

_avisou_memoria = False


def obter_repositorio():
    """Repositório da requisição: banco com ``DATABASE_URL``, memória sem ela.

    Sem banco acessível, as rotas respondem 503 (como ``/db/health`` e a Gestão).
    """
    global _avisou_memoria
    if not usa_banco():
        if not _avisou_memoria:
            logger.warning(
                "Financeiro guardando dados EM MEMÓRIA (sem DATABASE_URL): "
                "eles somem quando a API reinicia."
            )
            _avisou_memoria = True
        yield MEMORIA
        return
    conexao = sessao.conectar()
    # Ao sair, a conexão volta ao pool e o que não foi confirmado é desfeito.
    with conexao:
        yield RepositorioBanco(conexao)
