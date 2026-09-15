import os
import uuid
from pathlib import Path

if Path(".env").exists():
    from dotenv import load_dotenv

    load_dotenv()

import boto3
import psycopg
from botocore.client import Config
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from storage import build_public_file_url, get_r2_config, sanitize_file_name

DATABASE_URL = os.environ["DATABASE_URL"]
APP_NAME = os.getenv("APP_NAME", "Pratica-em-ES-MDCA")

app = FastAPI(title=f"API - {APP_NAME}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    return psycopg.connect(DATABASE_URL)


def get_r2_client():
    config = get_r2_config()
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{config.account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )
    return client, config


@app.on_event("startup")
def preparar_banco():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app_metadata (
                    chave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL,
                    criado_em TIMESTAMP NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                INSERT INTO app_metadata (chave, valor)
                VALUES ('app_name', %s)
                ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor
                """,
                (APP_NAME,),
            )
        conn.commit()


@app.get("/")
def raiz():
    return {"status": "ok", "app": APP_NAME}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/db/health")
def db_health():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                resultado = cur.fetchone()
    except Exception as erro:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível") from erro

    return {"status": "ok", "database": "connected", "result": resultado[0]}


@app.get("/storage/health")
def storage_health():
    try:
        client, config = get_r2_client()
        client.head_bucket(Bucket=config.bucket_name)
    except Exception as erro:
        raise HTTPException(status_code=503, detail="R2 indisponível") from erro

    return {"status": "ok", "storage": "connected", "bucket": config.bucket_name}


@app.post("/files")
async def upload_file(
    arquivo: UploadFile = File(...),
    pasta: str = Form("uploads"),
):
    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    nome_original = sanitize_file_name(arquivo.filename or "arquivo")
    pasta_limpa = sanitize_file_name(pasta.strip().strip("/") or "uploads")
    chave = f"{pasta_limpa}/{uuid.uuid4()}-{nome_original}"

    try:
        client, config = get_r2_client()
        client.put_object(
            Bucket=config.bucket_name,
            Key=chave,
            Body=conteudo,
            ContentType=arquivo.content_type or "application/octet-stream",
        )
    except Exception as erro:
        raise HTTPException(status_code=503, detail="Falha ao enviar arquivo para o R2") from erro

    return {
        "filename": nome_original,
        "key": chave,
        "url": build_public_file_url(config.public_url, chave),
        "content_type": arquivo.content_type,
        "size": len(conteudo),
    }
