"""Login único da plataforma (T-35 · US-08): senhas e tokens de sessão.

- **Senha:** guardada em ``usuarios.senha_hash`` como hash scrypt com sal aleatório
  (biblioteca padrão do Python), nunca a senha em si.
- **Token de sessão:** emitido por ``POST /auth/entrar`` depois de conferir e-mail e
  senha. É assinado com HMAC-SHA256 usando a chave da variável ``SESSAO_CHAVE`` e
  vale por ``DURACAO_SESSAO``. Alterar qualquer parte do token invalida a assinatura.
- **Usuário desativado** perde o acesso na hora: a cada requisição com token,
  ``usuario_da_sessao`` confere ``usuarios.ativo`` no banco.

Sem ``SESSAO_CHAVE`` no servidor, nenhum token é emitido nem aceito e a API volta a
funcionar só com o código de acesso (``FINANCEIRO_API_TOKEN``): é o jeito de desligar o
login sem deploy.

O banco é aberto só quando chega um token de sessão. Assim os testes e o app do
Financeiro, que não têm SQLAlchemy instalado, continuam funcionando com o código.
"""

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional, Tuple

from fastapi import HTTPException

VARIAVEL_CHAVE = "SESSAO_CHAVE"
DURACAO_SESSAO = 8 * 60 * 60  # segundos
# Prefixo que diferencia um token de sessão do código de acesso.
PREFIXO_TOKEN = "mdca1"
BANCO_INDISPONIVEL = "Banco de dados indisponível"

# scrypt: custo recomendado para senhas interativas (n=2^14, r=8, p=1).
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _SCRYPT_TAMANHO = 2**14, 8, 1, 32


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode("ascii")


def _de_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


# --- Senhas ------------------------------------------------------------------


def gerar_hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    derivada = hashlib.scrypt(
        senha.encode("utf-8"), salt=sal, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_TAMANHO
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(sal)}${_b64(derivada)}"


def conferir_senha(senha: str, hash_salvo: Optional[str]) -> bool:
    try:
        algoritmo, n, r, p, sal, esperado = (hash_salvo or "").split("$")
        if algoritmo != "scrypt":
            return False
        derivada = hashlib.scrypt(
            senha.encode("utf-8"),
            salt=_de_b64(sal),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(_de_b64(esperado)),
        )
    except (ValueError, binascii.Error):
        return False
    return hmac.compare_digest(derivada, _de_b64(esperado))


# Conferido quando o e-mail não existe, para a resposta levar o mesmo tempo e não
# revelar quais e-mails estão cadastrados.
HASH_FICTICIO = gerar_hash_senha(secrets.token_urlsafe(16))


# --- Tokens de sessão --------------------------------------------------------


def _chave() -> bytes:
    return os.getenv(VARIAVEL_CHAVE, "").encode("utf-8")


def chave_configurada() -> bool:
    return bool(_chave())


def parece_token_de_sessao(token: str) -> bool:
    return token.startswith(PREFIXO_TOKEN + ".")


def _assinar(conteudo: str) -> str:
    return _b64(hmac.new(_chave(), conteudo.encode("ascii"), hashlib.sha256).digest())


def criar_token(usuario_id: str, agora: Optional[float] = None) -> Tuple[str, datetime]:
    if not chave_configurada():
        raise RuntimeError(f"{VARIAVEL_CHAVE} não configurada")
    agora = time.time() if agora is None else agora
    expira = int(agora) + DURACAO_SESSAO
    carga = _b64(json.dumps({"sub": usuario_id, "exp": expira}, separators=(",", ":")).encode())
    conteudo = f"{PREFIXO_TOKEN}.{carga}"
    return f"{conteudo}.{_assinar(conteudo)}", datetime.fromtimestamp(expira, tz=timezone.utc)


def ler_token(token: str, agora: Optional[float] = None) -> Optional[str]:
    """Id do usuário de um token válido e não expirado; ``None`` em qualquer outro caso."""
    if not chave_configurada() or not parece_token_de_sessao(token):
        return None
    try:
        prefixo, carga, assinatura = token.split(".")
        if not hmac.compare_digest(assinatura, _assinar(f"{prefixo}.{carga}")):
            return None
        dados = json.loads(_de_b64(carga))
        usuario_id, expira = dados["sub"], int(dados["exp"])
    except (ValueError, KeyError, TypeError, binascii.Error):
        return None
    if not isinstance(usuario_id, str) or not usuario_id:
        return None
    if (time.time() if agora is None else agora) >= expira:
        return None
    return usuario_id


# --- Banco -------------------------------------------------------------------


@lru_cache(maxsize=1)
def _motor(url: str):
    # Mesma regra de Gestao/banco.py: URLs postgres puras usam o psycopg 3. Importado
    # aqui dentro para quem não usa token (testes do Financeiro) não precisar do SQLAlchemy.
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    if parsed.drivername in ("postgresql", "postgres"):
        parsed = parsed.set(drivername="postgresql+psycopg")
    return create_engine(
        parsed.render_as_string(hide_password=False),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )


def conectar():
    """Conexão SQLAlchemy com o banco da ``DATABASE_URL``; 503 se não houver banco."""
    from sqlalchemy.exc import SQLAlchemyError

    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise HTTPException(status_code=503, detail=BANCO_INDISPONIVEL)
    try:
        return _motor(url).connect()
    except SQLAlchemyError as erro:
        raise HTTPException(status_code=503, detail=BANCO_INDISPONIVEL) from erro


def usuario_da_sessao(token: str) -> Optional[str]:
    """Id do usuário de um token válido cuja conta continua ativa; ``None`` se não vale."""
    usuario_id = ler_token(token)
    if usuario_id is None:
        return None
    import sqlalchemy as sa
    from sqlalchemy.exc import SQLAlchemyError

    try:
        with conectar() as conexao:
            ativo = conexao.execute(
                sa.text("SELECT ativo FROM usuarios WHERE id = :id"), {"id": usuario_id}
            ).scalar_one_or_none()
    except SQLAlchemyError as erro:
        raise HTTPException(status_code=503, detail=BANCO_INDISPONIVEL) from erro
    return usuario_id if ativo else None
