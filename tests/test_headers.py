"""Ordem dos headers na requisicao (o requisito do projeto)."""
from __future__ import annotations

import http.server
import socketserver
import threading

from anuncios.config import Config, headers_navegacao
from anuncios.http import Http

RECEBIDOS: list[str] = []


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        RECEBIDOS.clear()
        RECEBIDOS.extend(ln.split(":", 1)[0].strip().lower() for ln in str(self.headers).splitlines() if ":" in ln)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def test_ordem_de_headers_preservada():
    srv = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    porta = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cfg = Config(proxy=None, transporte="h2", timeout=10)
        http = Http(cfg, "local")
        try:
            resposta = http.get(
                f"http://127.0.0.1:{porta}/x",
                headers_navegacao(),
                esperado="qualquer",
                rotulo="teste-ordem",
            )
            assert resposta.status == 200
        finally:
            http.fechar()
    finally:
        srv.shutdown()

    esperado = [
        "pragma",
        "cache-control",
        "upgrade-insecure-requests",
        "user-agent",
        "accept",
        "sec-fetch-site",
        "sec-fetch-mode",
        "sec-fetch-user",
        "sec-fetch-dest",
        "sec-ch-ua",
        "sec-ch-ua-mobile",
        "sec-ch-ua-platform",
        "accept-encoding",
        "accept-language",
    ]
    # Host/connection sao gerados pelo libcurl; priority e consumido pela camada HTTP/2.
    filtrados = [h for h in RECEBIDOS if h in set(esperado)]
    assert filtrados == esperado, filtrados
