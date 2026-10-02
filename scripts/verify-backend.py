"""Verifica a API após o deploy, sem dependências ou credenciais privadas."""
import argparse
import json
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description="Verifica /health após o deploy.")
    parser.add_argument("url", help="URL base do serviço Cloud Run")
    parser.add_argument("--attempts", type=int, default=6)
    parser.add_argument("--delay", type=float, default=5)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    if args.attempts < 1 or args.delay < 0 or args.timeout <= 0:
        parser.error("attempts e timeout devem ser positivos; delay não pode ser negativo")

    endpoint = args.url.rstrip("/") + "/health"
    for attempt in range(1, args.attempts + 1):
        try:
            with urlopen(endpoint, timeout=args.timeout) as response:
                body = json.load(response)
                if response.status == 200 and isinstance(body, dict) and body.get("status") == "ok":
                    print("Health check do backend: ok")
                    return 0
        except (URLError, OSError, ValueError):
            pass
        print(f"Health check sem sucesso: tentativa {attempt}/{args.attempts}", file=sys.stderr)
        if attempt < args.attempts:
            time.sleep(args.delay)
    return 1


if __name__ == "__main__":
    sys.exit(main())
