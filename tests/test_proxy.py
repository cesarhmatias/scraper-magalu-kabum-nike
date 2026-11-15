from __future__ import annotations

from anuncios.config import Config, normalizar_proxy


def test_gateway_decodo_udp():
    url = "socks5h://usuario:senha@gate.decodo.com:10000"
    assert normalizar_proxy(url) == "socks5h://usuario:senha@socks5-gate.decodo.com:10000"


def test_outros_proxies_intactos():
    url = "socks5h://u:p@127.0.0.1:1080"
    assert normalizar_proxy(url) == url
    assert normalizar_proxy(None) is None


def test_descricao_nao_expoe_credenciais():
    cfg = Config(proxy="socks5h://usuario:segredo@gate.decodo.com:10000")
    assert "segredo" not in cfg.proxy_descricao
    assert cfg.proxy_descricao == "socks5h://socks5-gate.decodo.com:10000"
    assert cfg.proxy_id.startswith("proxy-")
