import os
import re
from dataclasses import dataclass
from pathlib import PurePath


@dataclass(frozen=True)
class R2Config:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket_name: str
    public_url: str


def get_r2_config() -> R2Config:
    return R2Config(
        account_id=os.environ["R2_ACCOUNT_ID"],
        access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        bucket_name=os.environ["R2_BUCKET_NAME"],
        public_url=os.environ["R2_PUBLIC_URL"].rstrip("/"),
    )


def build_public_file_url(public_url: str, file_key: str) -> str:
    return f"{public_url.rstrip('/')}/{file_key.lstrip('/')}"


def sanitize_file_name(file_name: str) -> str:
    name = PurePath(file_name).name or "arquivo"
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)
