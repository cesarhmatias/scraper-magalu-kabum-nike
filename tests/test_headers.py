"""Ordem dos headers na requisicao (o requisito do projeto)."""
from __future__ import annotations

import http.server
import socketserver
import threading

from anuncios.config import Config, headers_navegacao, headers_preco_json
from anuncios.http import Http

RECEBIDOS: list[str] = []


class _Handler(http.server.BaseHTTPRequestHandler):
    def _capturar(self):
        RECEBIDOS.clear()
        RECEBIDOS.extend(ln.split(":", 1)[0].strip().lower() for ln in str(self.headers).splitlines() if ":" in ln)

    def do_GET(self):  # noqa: N802
        self._capturar()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):  # noqa: N802
        self._capturar()
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho:
            self.rfile.read(tamanho)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


def _servidor():
    srv = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def test_ordem_de_headers_preservada():
    srv, porta = _servidor()
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


def test_ordem_headers_preco_casasbahia():
    srv, porta = _servidor()
    try:
        cfg = Config(proxy=None, transporte="h2", timeout=10)
        http = Http(cfg, "local")
        try:
            resposta = http.post(
                f"http://127.0.0.1:{porta}/preco",
                headers_preco_json(
                    origem="https://www.casasbahia.com.br",
                    referer="https://www.casasbahia.com.br/",
                    apikey="chave",
                ),
                {"produtos": [{"idProduto": 1}], "skus": []},
                esperado="json",
                rotulo="teste-preco",
            )
            assert resposta.status == 200
        finally:
            http.fechar()
    finally:
        srv.shutdown()

    esperado = [
        "pragma",
        "cache-control",
        "sec-ch-ua-platform",
        "xaplication",
        "user-agent",
        "sec-ch-ua",
        "content-type",
        "apikey",
        "sec-ch-ua-mobile",
        "accept",
        "origin",
        "sec-fetch-site",
        "sec-fetch-mode",
        "sec-fetch-dest",
        "referer",
        "accept-encoding",
        "accept-language",
    ]
    filtrados = [h for h in RECEBIDOS if h in set(esperado)]
    assert filtrados == esperado, filtrados
