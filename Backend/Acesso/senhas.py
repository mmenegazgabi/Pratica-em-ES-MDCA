"""Senhas do login único (T-35): hash com scrypt da biblioteca padrão.

Formato guardado: ``scrypt$n$r$p$<sal b64>$<hash b64>``. Os parâmetros ficam no próprio
texto, então dá para endurecê-los depois sem invalidar senhas já gravadas.
"""

import base64
import binascii
import hashlib
import hmac
import secrets
from typing import Optional

N = 2**14
R = 8
P = 1
TAMANHO_SAL = 16
TAMANHO_HASH = 32
MINIMO = 8
MAXIMO = 128


def _scrypt(senha: str, sal: bytes, n: int, r: int, p: int) -> bytes:
    # maxmem acima do padrão (32 MiB) para aceitar parâmetros maiores no futuro.
    return hashlib.scrypt(
        senha.encode("utf-8"), salt=sal, n=n, r=r, p=p, dklen=TAMANHO_HASH, maxmem=128 * 1024 * 1024
    )


def gerar_hash(senha: str) -> str:
    sal = secrets.token_bytes(TAMANHO_SAL)
    derivado = _scrypt(senha, sal, N, R, P)
    return "scrypt${}${}${}${}${}".format(
        N, R, P, base64.b64encode(sal).decode("ascii"), base64.b64encode(derivado).decode("ascii")
    )


def conferir(senha: str, hash_: Optional[str]) -> bool:
    """Confere a senha; ``None`` ou formato inválido nunca conferem."""
    if not hash_:
        return False
    partes = hash_.split("$")
    if len(partes) != 6 or partes[0] != "scrypt":
        return False
    try:
        n, r, p = int(partes[1]), int(partes[2]), int(partes[3])
        sal = base64.b64decode(partes[4], validate=True)
        esperado = base64.b64decode(partes[5], validate=True)
        derivado = _scrypt(senha, sal, n, r, p)
    except (ValueError, binascii.Error, MemoryError):
        return False
    return hmac.compare_digest(derivado, esperado)


def validar(senha: str) -> Optional[str]:
    """Mensagem de erro para uma senha fora das regras, ou ``None`` se estiver ok."""
    if len(senha) < MINIMO:
        return "A senha precisa ter pelo menos 8 caracteres."
    if len(senha) > MAXIMO:
        return "A senha pode ter no máximo 128 caracteres."
    return None
