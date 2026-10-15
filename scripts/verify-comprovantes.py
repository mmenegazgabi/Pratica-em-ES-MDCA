"""Verifica os critérios da T-11 contra a API publicada e o R2 real.

Uso (só biblioteca padrão do Python, sem instalar nada):

    FINANCEIRO_API_TOKEN=... R2_ACCOUNT_ID=... R2_BUCKET_NAME=mdca-arquivos \
        python scripts/verify-comprovantes.py https://SUA-API.run.app

No PowerShell:

    $env:FINANCEIRO_API_TOKEN="..."; $env:R2_ACCOUNT_ID="..."; $env:R2_BUCKET_NAME="mdca-arquivos"
    python scripts/verify-comprovantes.py https://SUA-API.run.app

Não precisa das chaves secretas do R2: o teste de "acesso direto" é feito
justamente sem credenciais. O script envia um PNG de 1x1 pixel para
comprovantes/ (cerca de 70 bytes).
"""

import json
import os
import sys
import urllib.error
import urllib.request
import uuid

PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f"
    "15c4890000000b49444154789c6360000200000500017a5eab3f0000000049454e44ae426082"
)


def requisitar(metodo, url, corpo=None, cabecalhos=None):
    pedido = urllib.request.Request(url, data=corpo, method=metodo, headers=cabecalhos or {})
    try:
        with urllib.request.urlopen(pedido, timeout=20) as resposta:
            return resposta.status, resposta.read()
    except urllib.error.HTTPError as erro:
        return erro.code, erro.read()
    except urllib.error.URLError as erro:
        print(f"     erro de conexão com {url}: {erro.reason}")
        return 0, b""


def multipart(nome_arquivo, conteudo, content_type):
    fronteira = uuid.uuid4().hex
    corpo = (
        f"--{fronteira}\r\n"
        f'Content-Disposition: form-data; name="arquivo"; filename="{nome_arquivo}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + conteudo + f"\r\n--{fronteira}--\r\n".encode()
    return corpo, {"Content-Type": f"multipart/form-data; boundary={fronteira}"}


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python scripts/verify-comprovantes.py https://SUA-API.run.app")
    api = sys.argv[1].rstrip("/")
    try:
        token = os.environ["FINANCEIRO_API_TOKEN"]
        conta = os.environ["R2_ACCOUNT_ID"]
        bucket = os.environ["R2_BUCKET_NAME"]
    except KeyError as faltando:
        raise SystemExit(f"Variável de ambiente ausente: {faltando}")

    auth = {"Authorization": f"Bearer {token}"}
    resultados = []

    def checar(descricao, ok, detalhe=""):
        resultados.append(ok)
        print(f"[{'OK' if ok else 'FALHOU'}] {descricao}" + (f" ({detalhe})" if detalhe else ""))

    corpo, cabecalhos = multipart("verificacao.png", PNG_1X1, "image/png")

    status, _ = requisitar("POST", f"{api}/comprovantes", corpo, cabecalhos)
    checar("Upload sem autenticação é negado", status == 401, f"HTTP {status}")

    status, resposta = requisitar("POST", f"{api}/comprovantes", corpo, {**cabecalhos, **auth})
    checar("Upload autenticado é aceito", status == 201, f"HTTP {status}")
    if status != 201:
        print(resposta.decode(errors="replace"))
        raise SystemExit(1)

    chave = json.loads(resposta)["chave"]
    print(f"     chave: {chave}")

    status, _ = requisitar("GET", f"{api}/{chave}")
    checar("Leitura pela API sem autenticação é negada", status == 401, f"HTTP {status}")

    status, conteudo = requisitar("GET", f"{api}/{chave}", cabecalhos=auth)
    checar(
        "Leitura pela API autenticada devolve o mesmo arquivo",
        status == 200 and conteudo == PNG_1X1,
        f"HTTP {status}",
    )

    url_direta = f"https://{conta}.r2.cloudflarestorage.com/{bucket}/{chave}"
    status, _ = requisitar("GET", url_direta)
    checar(
        "Acesso direto à URL do arquivo no R2, sem assinatura, é negado",
        400 <= status < 500,
        f"HTTP {status}",
    )

    print()
    if all(resultados):
        print("Todos os critérios verificados.")
    else:
        print("Algum critério falhou.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
