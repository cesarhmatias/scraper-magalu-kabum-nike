"""Configuracao, perfis de header ordenados e normalizacao do proxy."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependencia declarada
    load_dotenv = None

RAIZ = Path(__file__).resolve().parents[2]

# Valores observados no Chrome 157 das capturas do ScrapeLens (2026-11-14).
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
)
SEC_CH_UA = '"Not-A.Brand";v="99", "Google Chrome";v="157", "Chromium";v="157"'
ACCEPT_LANGUAGE = "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
ACCEPT_ENCODING = "gzip, deflate, br, zstd"
ACCEPT_HTML = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/jxl,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
)
ACCEPT_JSON = "application/json, text/plain, */*"
ACCEPT_ALL = "*/*"


@dataclass(frozen=True)
class Config:
    proxy: str | None
    transporte: str = "auto"      # auto | h3 | h2
    exigir_udp: bool = False
    timeout: float = 35.0
    tentativas: int = 3
    pausa_s: float = 0.8
    impersonate: str = "chrome146"

    def __post_init__(self):
        if self.proxy:
            object.__setattr__(self, "proxy", normalizar_proxy(self.proxy))

    @property
    def proxy_id(self) -> str:
        if not self.proxy:
            return "direto"
        return "proxy-" + hashlib.sha1(self.proxy.encode()).hexdigest()[:8]

    @property
    def proxy_descricao(self) -> str:
        """Descricao sem credenciais, para log e planilha."""
        if not self.proxy:
            return "sem proxy (direto)"
        p = urlsplit(self.proxy)
        host = p.hostname or "?"
        porta = p.port or "?"
        return f"{p.scheme}://{host}:{porta}"


def carregar_env() -> None:
    if load_dotenv is None:
        return
    for caminho in (Path.cwd() / ".env", RAIZ / ".env"):
        if caminho.exists():
            load_dotenv(caminho, override=False)


def normalizar_proxy(url: str | None) -> str | None:
    """Aponta o gateway Decodo para a entrada com UDP ASSOCIATE.

    `gate.decodo.com:10000` recusa UDP ASSOCIATE (reply=0x02); o gateway
    documentado para HTTP/3 e `socks5-gate.decodo.com:10000`. O mesmo login e
    mantido; apenas o host muda. Qualquer outro provedor passa intacto.
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if "://" not in url:
        url = "socks5h://" + url
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    if host == "gate.decodo.com" and p.scheme in {"socks5", "socks5h"}:
        host = "socks5-gate.decodo.com"
    netloc = host
    if p.port:
        netloc += f":{p.port}"
    if p.username is not None:
        userinfo = p.username
        if p.password is not None:
            userinfo += ":" + p.password
        netloc = userinfo + "@" + netloc
    return urlunsplit((p.scheme, netloc, p.path, p.query, p.fragment))


def config_do_ambiente(proxy: str | None = None, transporte: str | None = None,
                       exigir_udp: bool = False, timeout: float | None = None,
                       tentativas: int | None = None) -> Config:
    carregar_env()
    bruto = proxy or os.environ.get("ANUNCIOS_PROXY") or None
    cfg = Config(
        proxy=normalizar_proxy(bruto),
        transporte=(transporte or os.environ.get("ANUNCIOS_TRANSPORTE") or "auto").lower(),
        exigir_udp=exigir_udp,
        timeout=float(timeout or os.environ.get("ANUNCIOS_TIMEOUT") or 35),
        tentativas=int(tentativas or os.environ.get("ANUNCIOS_TENTATIVAS") or 3),
    )
    if cfg.transporte not in {"auto", "h3", "h2"}:
        raise ValueError("transporte deve ser auto, h3 ou h2")
    return cfg


# ---------------------------------------------------------------------------
# Perfis de header na ordem exata em que o Chrome os enviou nas capturas.
# A ordem e o que bibliotecas como o DataDome/Akamai comparam; por isso usamos
# curl_cffi.requests.Headers (ordenado) em vez de dict comum.
# ---------------------------------------------------------------------------

def headers_navegacao(*, referer: str | None = None, h3: bool = False) -> list[tuple[str, str]]:
    """Documento HTML (Sec-Fetch-Dest: document), ordem do Kabum/Nike."""
    h = [
        ("pragma", "no-cache"),
        ("cache-control", "no-cache"),
        ("upgrade-insecure-requests", "1"),
        ("user-agent", USER_AGENT),
        ("accept", ACCEPT_HTML),
        ("sec-fetch-site", "same-origin" if referer else "none"),
        ("sec-fetch-mode", "navigate"),
        ("sec-fetch-user", "?1"),
        ("sec-fetch-dest", "document"),
        ("sec-ch-ua", SEC_CH_UA),
        ("sec-ch-ua-mobile", "?0"),
        ("sec-ch-ua-platform", '"macOS"'),
    ]
    if referer:
        h.append(("referer", referer))
    h += [
        ("accept-encoding", ACCEPT_ENCODING),
        ("accept-language", ACCEPT_LANGUAGE),
        ("priority", "u=0, i"),
    ]
    return h


def headers_next_data(*, referer: str) -> list[tuple[str, str]]:
    """XHR do Next.js `/_next/data/...` (Magalu), ordem da captura."""
    return [
        ("pragma", "no-cache"),
        ("cache-control", "no-cache"),
        ("x-nextjs-data", "1"),
        ("sec-ch-ua-platform", '"macOS"'),
        ("user-agent", USER_AGENT),
        ("sec-ch-ua", SEC_CH_UA),
        ("sec-ch-ua-mobile", "?0"),
        ("accept", ACCEPT_ALL),
        ("sec-fetch-site", "same-origin"),
        ("sec-fetch-mode", "cors"),
        ("sec-fetch-dest", "empty"),
        ("referer", referer),
        ("accept-encoding", ACCEPT_ENCODING),
        ("accept-language", ACCEPT_LANGUAGE),
        ("priority", "u=1, i"),
    ]


def headers_api_json(*, origem: str, referer: str) -> list[tuple[str, str]]:
    """Chamada XHR JSON cross-site (Kabum servicespub), ordem da captura."""
    return [
        ("pragma", "no-cache"),
        ("cache-control", "no-cache"),
        ("sec-ch-ua-platform", '"macOS"'),
        ("user-agent", USER_AGENT),
        ("accept", ACCEPT_JSON),
        ("sec-ch-ua", SEC_CH_UA),
        ("sec-ch-ua-mobile", "?0"),
        ("origin", origem),
        ("sec-fetch-site", "cross-site"),
        ("sec-fetch-mode", "cors"),
        ("sec-fetch-dest", "empty"),
        ("referer", referer),
        ("accept-encoding", ACCEPT_ENCODING),
        ("accept-language", ACCEPT_LANGUAGE),
        ("priority", "u=1, i"),
    ]


def headers_preco_json(*, origem: str, referer: str, apikey: str) -> list[tuple[str, str]]:
    """POST JSON da API de precos da Casas Bahia, ordem exata da captura.

    Os headers `xaplication` e `apikey` sao exigidos pelo gateway Kong; a ordem
    abaixo e a que o Chrome 157 enviou em `api.casasbahia.com.br`.
    """
    return [
        ("pragma", "no-cache"),
        ("cache-control", "no-cache"),
        ("sec-ch-ua-platform", '"macOS"'),
        ("xaplication", "vv-categoria-frontend"),
        ("user-agent", USER_AGENT),
        ("sec-ch-ua", SEC_CH_UA),
        ("content-type", "application/json"),
        ("apikey", apikey),
        ("sec-ch-ua-mobile", "?0"),
        ("accept", ACCEPT_ALL),
        ("origin", origem),
        ("sec-fetch-site", "same-site"),
        ("sec-fetch-mode", "cors"),
        ("sec-fetch-dest", "empty"),
        ("referer", referer),
        ("accept-encoding", ACCEPT_ENCODING),
        ("accept-language", ACCEPT_LANGUAGE),
        ("priority", "u=1, i"),
    ]
