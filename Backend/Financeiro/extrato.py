"""Extrato bancário (US-05): leitura do CSV e itens para conciliar.

O item do extrato é o lado do banco da conciliação; ``conciliado_com`` guarda o id do
lançamento a que ele foi ligado. Os itens são guardados pelo repositório
(``persistencia.py``): na tabela ``extrato_itens`` com ``DATABASE_URL`` ou em
``caixa_do_extrato`` (memória do processo) sem ela. As regras de importação (CSV,
limite de 1 MB, erros com o número da linha, repetidos por multiconjunto) ficam aqui
e valem para os dois.
"""

import csv
from collections import Counter
import io
import re
import threading
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

TAMANHO_MAXIMO_BYTES = 1024 * 1024
DESCRICAO_TAMANHO_MAXIMO = 500
LIMITE_VALOR = Decimal("1e12")
_QUEBRA_DE_LINHA = re.compile(r"\r\n|\r|\n")
_CONTROLE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class ExtratoInvalido(ValueError):
    pass


class ItemJaConciliado(ValueError):
    MENSAGEM = "Item do extrato já conciliado com outro lançamento."

    def __init__(self, mensagem: str = MENSAGEM) -> None:
        super().__init__(mensagem)


@dataclass
class ItemExtrato:
    data: date
    descricao: str
    valor: float
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    importado_em: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    conciliado_com: Optional[str] = None


# --- Leitura do CSV ----------------------------------------------------------


def _normalizar_cabecalho(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.strip().lower()


def _decodificar(conteudo: bytes) -> str:
    try:
        return conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Extratos de banco costumam sair em Windows-1252.
        return conteudo.decode("cp1252", errors="replace")


def _converter_data(texto: str) -> date:
    texto = texto.strip()
    for padrao, formato in (
        (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
        (r"\d{1,2}/\d{1,2}/\d{4}", "%d/%m/%Y"),
    ):
        if re.fullmatch(padrao, texto):
            return datetime.strptime(texto, formato).date()
    raise ValueError(texto)


def _converter_valor(texto: str) -> float:
    """Aceita "R$ 1.234,56", "1234.56", "-50,00". Negativo é saída."""
    limpo = re.sub(r"R\$|\s", "", texto, flags=re.IGNORECASE)
    if not re.fullmatch(r"[+-]?[\d.,]*\d[\d.,]*", limpo):
        raise ValueError(texto)
    ultima_virgula, ultimo_ponto = limpo.rfind(","), limpo.rfind(".")
    if ultima_virgula >= 0 and ultimo_ponto >= 0:
        # Os dois aparecem: o último deles é o decimal, o outro é milhar.
        decimal = "," if ultima_virgula > ultimo_ponto else "."
        milhar = "." if decimal == "," else ","
        limpo = limpo.replace(milhar, "").replace(decimal, ".")
    elif ultima_virgula >= 0:
        if limpo.count(",") > 1:
            raise ValueError(texto)
        limpo = limpo.replace(",", ".")
    elif "." in limpo:
        # Só pontos: milhar quando a parte inteira é "1.234" ou "1.234.567";
        # um ponto só, com outra forma ("0.500", "12.5"), é decimal.
        if re.fullmatch(r"[+-]?[1-9]\d{0,2}(\.\d{3})+", limpo):
            limpo = limpo.replace(".", "")
        elif limpo.count(".") > 1:
            raise ValueError(texto)
    try:
        valor = Decimal(limpo)
        if not valor.is_finite() or abs(valor) >= LIMITE_VALOR:
            raise ValueError(texto)
        return float(round(valor, 2))
    except InvalidOperation as erro:
        raise ValueError(texto) from erro


def _achar_coluna(cabecalho: List[str], nomes: Tuple[str, ...]) -> Optional[int]:
    for indice, coluna in enumerate(cabecalho):
        if coluna in nomes:
            return indice
    return None


def ler_csv(conteudo: bytes) -> List[ItemExtrato]:
    """Converte o CSV em itens (linhas iguais no mesmo arquivo são transações distintas).

    Falha inteira, com o número da linha, se qualquer linha for inválida.
    """
    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        raise ExtratoInvalido("Arquivo acima de 1 MB.")
    linhas = _QUEBRA_DE_LINHA.split(_decodificar(conteudo))
    primeira = next((i for i, linha in enumerate(linhas) if linha.strip()), None)
    if primeira is None:
        raise ExtratoInvalido("Arquivo vazio.")
    separador = ";" if linhas[primeira].count(";") > linhas[primeira].count(",") else ","

    leitor = csv.reader(io.StringIO("\n".join(linhas[primeira:])), delimiter=separador)
    try:
        cabecalho = [_normalizar_cabecalho(c) for c in next(leitor)]
    except csv.Error:
        raise ExtratoInvalido(f"Linha {primeira + 1}: linha mal formada.") from None
    col_data = _achar_coluna(cabecalho, ("data",))
    col_descricao = _achar_coluna(cabecalho, ("descricao", "historico"))
    col_valor = _achar_coluna(cabecalho, ("valor",))
    if col_data is None or col_descricao is None or col_valor is None:
        raise ExtratoInvalido(
            "Cabeçalho inválido: o arquivo precisa das colunas data, descricao e valor."
        )

    itens: List[ItemExtrato] = []
    while True:
        try:
            celulas = next(leitor)
        except StopIteration:
            break
        except csv.Error:
            raise ExtratoInvalido(f"Linha {primeira + leitor.line_num}: linha mal formada.") from None
        if not any(c.strip() for c in celulas):
            continue
        # Linha do arquivo original (o cabeçalho pode não ser a primeira).
        numero = primeira + leitor.line_num
        if len(celulas) <= max(col_data, col_descricao, col_valor):
            raise ExtratoInvalido(f"Linha {numero}: colunas faltando.")
        try:
            data = _converter_data(celulas[col_data])
        except ValueError:
            raise ExtratoInvalido(f"Linha {numero}: data inválida.") from None
        descricao = " ".join(_CONTROLE.sub(" ", celulas[col_descricao]).split())
        if not descricao:
            raise ExtratoInvalido(f"Linha {numero}: descrição obrigatória.")
        if len(descricao) > DESCRICAO_TAMANHO_MAXIMO:
            raise ExtratoInvalido(
                f"Linha {numero}: descrição acima de {DESCRICAO_TAMANHO_MAXIMO} caracteres."
            )
        try:
            valor = _converter_valor(celulas[col_valor])
        except ValueError:
            raise ExtratoInvalido(f"Linha {numero}: valor inválido.") from None
        itens.append(ItemExtrato(data=data, descricao=descricao, valor=valor))
    if not itens:
        raise ExtratoInvalido("O arquivo não tem linhas de dados.")
    return itens


# --- Repetidos --------------------------------------------------------------


def chave(item: ItemExtrato) -> Tuple[date, str, float]:
    return (item.data, item.descricao, item.valor)


def separar_repetidos(
    novos: List[ItemExtrato], ja_guardados: Counter
) -> List[ItemExtrato]:
    """Os itens que entram, pela regra de multiconjunto.

    Para cada (data, descrição, valor), entram ``max(0, quantas_no_arquivo -
    quantas_já_guardadas)``. Importar o mesmo arquivo de novo não muda nada; dois PIX
    iguais no mesmo dia entram os dois. ``ja_guardados`` é consumido.
    """
    entram = []
    for item in novos:
        if ja_guardados[chave(item)] > 0:
            ja_guardados[chave(item)] -= 1
            continue
        entram.append(item)
    return entram


# --- Memória (sem DATABASE_URL) ----------------------------------------------


class CaixaDoExtrato:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._itens: List[ItemExtrato] = []

    def importar(self, novos: List[ItemExtrato]) -> Tuple[List[ItemExtrato], int]:
        """Guarda os itens novos; devolve (guardados, repetidos)."""
        with self._lock:
            guardados = separar_repetidos(novos, Counter(chave(i) for i in self._itens))
            self._itens.extend(guardados)
        return guardados, len(novos) - len(guardados)

    def listar(self, em_aberto: Optional[bool] = None) -> List[ItemExtrato]:
        """Do mais antigo para o mais recente (na mesma data, pela ordem de importação)."""
        with self._lock:
            itens = list(self._itens)
        if em_aberto is not None:
            itens = [i for i in itens if (i.conciliado_com is None) == em_aberto]
        return sorted(itens, key=lambda i: i.data)

    def buscar(self, item_id: str) -> Optional[ItemExtrato]:
        with self._lock:
            return next((i for i in self._itens if i.id == item_id), None)

    def vincular(self, item_id: str, lancamento_id: str) -> None:
        """Liga o item (ainda livre) ao lançamento."""
        with self._lock:
            item = next(i for i in self._itens if i.id == item_id)
            if item.conciliado_com not in (None, lancamento_id):
                raise ItemJaConciliado()
            item.conciliado_com = lancamento_id

    def limpar(self) -> None:
        with self._lock:
            self._itens.clear()


caixa_do_extrato = CaixaDoExtrato()
