"""Regra de alerta de consumo do orçamento (US-02).

O nível de alerta é calculado no backend para que todas as telas usem
os mesmos limiares:

- abaixo de 80% do valor total consumido  -> NORMAL
- a partir de 80% (inclusive)             -> ATENCAO   (amarelo)
- a partir de 100% (inclusive)            -> ESTOURADO (vermelho)

"Consumido" é o realizado: a soma dos lançamentos aprovados, ou seja,
``valor_total - saldo``. Os valores são arredondados para centavos antes
da comparação, para que somas em float (ex.: 0.1 + 0.7 = 0.7999...) não
deixem de disparar o alerta exatamente no limiar.
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Optional

LIMIAR_ATENCAO = Decimal("80")
LIMIAR_ESTOURADO = Decimal("100")

_CENTAVO = Decimal("0.01")


class NivelAlerta(str, Enum):
    NORMAL = "normal"
    ATENCAO = "atencao"
    ESTOURADO = "estourado"


def _em_centavos(valor: float) -> Decimal:
    return Decimal(str(valor)).quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def calcular_realizado(valor_total: float, saldo: float) -> float:
    """Valor já consumido do orçamento, em reais com 2 casas."""
    return float(_em_centavos(valor_total) - _em_centavos(saldo))


def calcular_percentual_consumido(
    valor_total: float, realizado: float
) -> Optional[float]:
    """Percentual do orçamento consumido (0–100+), com 2 casas.

    O percentual é truncado (não arredondado) para ficar coerente com o
    nível de alerta: 79,999% aparece como 79,99%, e não como 80%.
    Retorna ``None`` quando o valor total é zero, porque o percentual não
    é definido nesse caso.
    """
    total = _em_centavos(valor_total)
    if total == 0:
        return None
    percentual = _em_centavos(realizado) * 100 / total
    return float(percentual.quantize(_CENTAVO, rounding=ROUND_DOWN))


def classificar_nivel_alerta(valor_total: float, realizado: float) -> NivelAlerta:
    """Classifica o consumo do orçamento nos limiares de 80% e 100%."""
    total = _em_centavos(valor_total)
    gasto = _em_centavos(realizado)

    if total == 0:
        return NivelAlerta.ESTOURADO if gasto > 0 else NivelAlerta.NORMAL

    # Compara sem dividir: gasto / total >= limiar / 100
    if gasto * 100 >= total * LIMIAR_ESTOURADO:
        return NivelAlerta.ESTOURADO
    if gasto * 100 >= total * LIMIAR_ATENCAO:
        return NivelAlerta.ATENCAO
    return NivelAlerta.NORMAL
