def formatar_reais(valor: float) -> str:
    """1234.5 -> "R$ 1.234,50"."""
    texto = f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"
