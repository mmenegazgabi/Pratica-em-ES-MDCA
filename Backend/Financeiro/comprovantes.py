"""Armazenamento de comprovantes no bucket privado do R2 (T-11 · US-03).

Regras:
- Só entram fotos e PDFs (JPEG, PNG, WEBP, HEIC ou PDF), identificados pelo
  conteúdo do arquivo, não pela extensão nem pelo Content-Type enviado.
- Tamanho máximo por arquivo: ``TAMANHO_MAXIMO_BYTES`` (5 MB), para manter o
  uso dentro da camada gratuita do R2.
- Os objetos ficam em ``comprovantes/AAAA/MM/<uuid>.<ext>``, separados dos
  arquivos da Gestão, e o nome original vai só nos metadados.
- O bucket é privado: a leitura acontece apenas pela API (rota autenticada),
  nunca por URL pública.
"""

import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePath
from typing import Optional, Protocol

PREFIXO = "comprovantes"
TAMANHO_MAXIMO_BYTES = 5 * 1024 * 1024

_MARCAS_HEIC = {b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"}

_PADRAO_CHAVE = re.compile(
    rf"^{PREFIXO}/\d{{4}}/\d{{2}}/[0-9a-f]{{32}}\.(jpg|png|webp|heic|pdf)$"
)


@dataclass(frozen=True)
class TipoArquivo:
    extensao: str
    content_type: str


TIPOS_ACEITOS = {
    "jpg": TipoArquivo("jpg", "image/jpeg"),
    "png": TipoArquivo("png", "image/png"),
    "webp": TipoArquivo("webp", "image/webp"),
    "heic": TipoArquivo("heic", "image/heic"),
    "pdf": TipoArquivo("pdf", "application/pdf"),
}


class ComprovanteInvalido(ValueError):
    """Arquivo recusado pelas regras de comprovante."""


@dataclass(frozen=True)
class ArquivoArmazenado:
    conteudo: bytes
    content_type: str
    nome_original: str


class ArmazenamentoComprovantes(Protocol):
    def salvar(
        self, chave: str, conteudo: bytes, content_type: str, nome_original: str
    ) -> None: ...

    def ler(self, chave: str) -> Optional[ArquivoArmazenado]: ...


def detectar_tipo(conteudo: bytes) -> Optional[TipoArquivo]:
    """Identifica o tipo pelo início do arquivo (magic bytes)."""
    if conteudo.startswith(b"\xff\xd8\xff"):
        return TIPOS_ACEITOS["jpg"]
    if conteudo.startswith(b"\x89PNG\r\n\x1a\n"):
        return TIPOS_ACEITOS["png"]
    if conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP":
        return TIPOS_ACEITOS["webp"]
    if conteudo[4:8] == b"ftyp" and conteudo[8:12] in _MARCAS_HEIC:
        return TIPOS_ACEITOS["heic"]
    if conteudo.startswith(b"%PDF-"):
        return TIPOS_ACEITOS["pdf"]
    return None


def validar_comprovante(conteudo: bytes) -> TipoArquivo:
    if not conteudo:
        raise ComprovanteInvalido("Arquivo vazio.")
    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        raise ComprovanteInvalido("Arquivo maior que o limite de 5 MB.")
    tipo = detectar_tipo(conteudo)
    if tipo is None:
        raise ComprovanteInvalido(
            "Tipo de arquivo não aceito. Envie foto (JPG, PNG, WEBP, HEIC) ou PDF."
        )
    return tipo


def gerar_chave(tipo: TipoArquivo, agora: Optional[datetime] = None) -> str:
    agora = agora or datetime.now(timezone.utc)
    return f"{PREFIXO}/{agora:%Y/%m}/{uuid.uuid4().hex}.{tipo.extensao}"


def chave_valida(chave: str) -> bool:
    """Só aceita chaves geradas por ``gerar_chave`` (impede ler outras pastas)."""
    return bool(_PADRAO_CHAVE.fullmatch(chave))


def limpar_nome_original(nome: Optional[str]) -> str:
    """Nome seguro para metadados do S3 (somente ASCII) e Content-Disposition."""
    base = PurePath(nome or "").name or "comprovante"
    limpo = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return limpo[:120]


class ArmazenamentoR2:
    """Implementação real, usando a API S3 do Cloudflare R2."""

    def __init__(self) -> None:
        import boto3
        from botocore.client import Config

        self._bucket = os.environ["R2_BUCKET_NAME"]
        self._client = boto3.client(
            "s3",
            endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            config=Config(
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=15,
                retries={"max_attempts": 2},
            ),
            region_name="auto",
        )

    def salvar(
        self, chave: str, conteudo: bytes, content_type: str, nome_original: str
    ) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=chave,
            Body=conteudo,
            ContentType=content_type,
            Metadata={"nome-original": nome_original},
        )

    def ler(self, chave: str) -> Optional[ArquivoArmazenado]:
        from botocore.exceptions import ClientError

        try:
            resposta = self._client.get_object(Bucket=self._bucket, Key=chave)
        except ClientError as erro:
            if erro.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                return None
            raise
        return ArquivoArmazenado(
            conteudo=resposta["Body"].read(),
            content_type=resposta.get("ContentType", "application/octet-stream"),
            nome_original=resposta.get("Metadata", {}).get("nome-original", "comprovante"),
        )


class ArmazenamentoEmMemoria:
    """Implementação para testes, sem rede."""

    def __init__(self) -> None:
        self.objetos: dict[str, ArquivoArmazenado] = {}

    def salvar(
        self, chave: str, conteudo: bytes, content_type: str, nome_original: str
    ) -> None:
        self.objetos[chave] = ArquivoArmazenado(conteudo, content_type, nome_original)

    def ler(self, chave: str) -> Optional[ArquivoArmazenado]:
        return self.objetos.get(chave)
