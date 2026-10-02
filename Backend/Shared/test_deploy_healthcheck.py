import json
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


@contextmanager
def health_server(responses):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            code, body = responses[min(len(calls), len(responses) - 1)]
            calls.append(self.path)
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def check_health(url, attempts=1):
    script = Path(__file__).parents[2] / "scripts" / "verify-backend.py"
    return subprocess.run(
        [sys.executable, str(script), url, "--attempts", str(attempts), "--delay", "0"],
        text=True, capture_output=True, timeout=10,
    )


def test_healthcheck_accepts_healthy_api():
    with health_server([(200, {"status": "ok"})]) as (url, calls):
        result = check_health(url + "/")
    assert result.returncode == 0, result.stderr
    assert calls == ["/health"]


def test_healthcheck_retries_transient_http_failure():
    with health_server([(503, {"status": "starting"}), (200, {"status": "ok"})]) as (url, calls):
        result = check_health(url, attempts=2)
    assert result.returncode == 0, result.stderr
    assert calls == ["/health", "/health"]


def test_healthcheck_rejects_http_200_without_healthy_payload():
    with health_server([(200, {"status": "error"})]) as (url, calls):
        result = check_health(url)
    assert result.returncode == 1
    assert calls == ["/health"]


def test_healthcheck_fails_after_retry_limit():
    with health_server([(503, {"status": "starting"})]) as (url, calls):
        result = check_health(url, attempts=2)
    assert result.returncode == 1
    assert calls == ["/health", "/health"]
