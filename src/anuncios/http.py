"""Camada HTTP: curl_cffi com proxy SOCKS5, ordem de headers e deteccao de bloqueio.

O requisito do projeto e nao usar navegador headless. O transporte preferido e
QUIC/HTTP/3 sobre o relay UDP do SOCKS5; quando o alvo ou a build do libcurl nao
negocia h3, a camada cai para h2 no mesmo gateway (e registra o protocolo real).
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from typing import Iterable

from curl_cffi import requests as cffi

from .config import Config
from .log import evento

# CURLINFO_HTTP_VERSION: 2 = 1.1; 3 = 2; 30/31 = 3.
_VERSOES = {1: "h1.1", 2: "h1.1", 3: "h2", 30: "h3", 31: "h3"}

# Marcadores de bloqueio/challenge vistos nas capturas e no alvo.
_MARCADORES = (
    "access denied",
    "sec-if-cpt",
    "powered and protected by",
    "captcha-delivery",
    "datadome",
    "just a moment",
    "unusual traffic",
    "cf-chl",
    "attention required",
    "request unsuccessful",
)


class ErroColeta(RuntimeError):
    """Falha generica de coleta, com contexto seguro (sem credenciais)."""


class BloqueioError(ErroColeta):
    def __init__(self, url: str, status: int | None, evidencia: str):
        super().__init__(f"bloqueio em {url}: status={status} evidencia={evidencia!r}")
        self.url = url
        self.status = status
        self.evidencia = evidencia


class SemResultados(ErroColeta):
    pass


@dataclass
class Resposta:
    url: str
    url_final: str
    status: int
    corpo: bytes
    http_version: str
    duracao_ms: int
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def texto(self) -> str:
        for charset in ("utf-8", "latin-1"):
            try:
                return self.corpo.decode(charset)
            except UnicodeDecodeError:
                continue
        return self.corpo.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.texto)


class Http:
    """Sessao curl_cffi por dominio. Uma sessao por provider isola cookies."""

    def __init__(self, cfg: Config, dominio: str):
        self.cfg = cfg
        self.dominio = dominio
        self._versao = "v3" if cfg.transporte in {"auto", "h3"} else "v2"
        self._sessao = self._nova_sessao(self._versao)
        self._forcou_h2 = False
        self._falhas_h3 = 0
        self.ultimo_transporte = "-"

    # -- sessao ------------------------------------------------------------
    def _nova_sessao(self, versao: str):
        kwargs = dict(
            impersonate=self.cfg.impersonate,
            http_version=versao,
            timeout=self.cfg.timeout,
            allow_redirects=True,
            verify=True,
            # Nao deixe o fingerprint inserir headers antes dos nossos: a ordem
            # capturada do Chrome e o que o anti-bot compara.
            default_headers=False,
        )
        if self.cfg.proxy:
            kwargs["proxy"] = self.cfg.proxy
        return cffi.Session(**kwargs)

    def _recriar(self, versao: str) -> None:
        try:
            self._sessao.close()
        except Exception:
            pass
        self._versao = versao
        self._sessao = self._nova_sessao(versao)

    def forcar_h2(self) -> None:
        """Recria a sessao em HTTP/2 (ex.: challenge do Akamai em h3)."""
        if self._versao != "v2":
            self._forcou_h2 = True
            self._recriar("v2")

    def fechar(self) -> None:
        try:
            self._sessao.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.fechar()

    # -- requests ----------------------------------------------------------
    def get(
        self,
        url: str,
        headers: Iterable[tuple[str, str]],
        *,
        esperado: str = "html",
        permitir_403: bool = False,
        rotulo: str = "",
    ) -> Resposta:
        """GET com retry. `esperado` = html|json|qualquer."""
        tentativas = max(1, self.cfg.tentativas)
        ultimo_erro: Exception | None = None
        for tentativa in range(1, tentativas + 1):
            inicio = time.perf_counter()
            try:
                r = self._sessao.get(url, headers=cffi.Headers(list(headers)))
            except Exception as exc:  # rede, TLS, QUIC
                ultimo_erro = exc
                protocolo = "erro"
                evento(
                    "aviso", acao="request_erro", dominio=self.dominio, url=url,
                    tentativa=tentativa, transporte=self._versao,
                    erro=f"{type(exc).__name__}: {exc}"[:300], proxy=self.cfg.proxy_id,
                )
                if self._pode_cair_para_h2(exc):
                    # QUIC sobre relay UDP pode morrer por idle/timeout: mais uma
                    # tentativa em h3 antes de degradar para h2.
                    if self._versao == "v3" and self._falhas_h3 < 1 and self.cfg.transporte == "auto":
                        self._falhas_h3 += 1
                        time.sleep(0.6)
                        continue
                    self._forcou_h2 = True
                    self._recriar("v2")
                    continue
                if tentativa < tentativas:
                    time.sleep(self._backoff(tentativa))
                    continue
                raise ErroColeta(
                    f"falha de rede em {url} ({type(exc).__name__}); ultimo transporte={protocolo}"
                ) from None

            duracao = int((time.perf_counter() - inicio) * 1000)
            protocolo = _VERSOES.get(int(getattr(r, "http_version", 0) or 0), "desconhecido")
            self.ultimo_transporte = protocolo
            corpo = r.content or b""
            resp = Resposta(
                url=url,
                url_final=str(r.url),
                status=r.status_code,
                corpo=corpo,
                http_version=protocolo,
                duracao_ms=duracao,
                headers={k.lower(): v for k, v in (r.headers or {}).items()},
            )
            evento(
                "info", acao="request", dominio=self.dominio, rotulo=rotulo or None,
                status=resp.status, protocolo=protocolo, bytes=len(corpo),
                duracao_ms=duracao, tentativa=tentativa, url=url, sessao=self._versao,
                proxy=self.cfg.proxy_id,
            )

            if (self.cfg.transporte == "h3" or self.cfg.exigir_udp) and protocolo != "h3":
                raise ErroColeta(
                    f"h3 exigido mas o transporte negociou {protocolo} em {url}; "
                    "o libcurl nao faz QUIC sobre SOCKS5 em todas as builds"
                )

            if resp.status in {429, 500, 502, 503, 504} and tentativa < tentativas:
                time.sleep(self._backoff(tentativa))
                continue

            if resp.status == 403 and not permitir_403:
                raise BloqueioError(url, resp.status, _evidencia(resp))

            if esperado in {"html", "json"} and _parece_bloqueio(resp):
                raise BloqueioError(url, resp.status, _evidencia(resp))

            if esperado == "json" and "json" not in resp.headers.get("content-type", ""):
                if resp.status >= 400:
                    raise ErroColeta(f"HTTP {resp.status} em {url}: {resp.texto[:160]!r}")
                raise BloqueioError(
                    url, resp.status,
                    "esperava JSON e recebeu " + resp.headers.get("content-type", "?"),
                )

            if esperado == "html" and resp.status >= 400 and not permitir_403:
                raise ErroColeta(f"HTTP {resp.status} em {url}: {resp.texto[:160]!r}")

            return resp

        raise ErroColeta(f"falha apos {tentativas} tentativas em {url}: {ultimo_erro}")

    # -- utilidades --------------------------------------------------------
    def _pode_cair_para_h2(self, exc: Exception) -> bool:
        if self.cfg.transporte != "auto" or self._forcou_h2:
            return False
        texto = f"{type(exc).__name__}: {exc}".lower()
        return any(
            marca in texto
            for marca in ("http3", "quic", "udp", "socks5", "connection", "timeout", "curl")
        )

    @staticmethod
    def _backoff(tentativa: int) -> float:
        return min(8.0, 1.2 * (2 ** (tentativa - 1))) + random.uniform(0, 0.4)

    def aquecer(self, url: str, headers: Iterable[tuple[str, str]]) -> Resposta | None:
        """GET inicial para cookies/challenge; falhas sao registradas, nao fatais."""
        try:
            return self.get(url, headers, esperado="qualquer", permitir_403=True, rotulo="aquecimento")
        except Exception as exc:
            evento("aviso", acao="aquecimento_falhou", dominio=self.dominio,
                   url=url, erro=f"{type(exc).__name__}: {exc}"[:200])
            return None


def _evidencia(resp: Resposta) -> str:
    texto = resp.texto[:5000].lower()
    for marca in _MARCADORES:
        if marca in texto:
            return marca
    return resp.headers.get("content-type", "") + f" / {len(resp.corpo)} bytes"


def _parece_bloqueio(resp: Resposta) -> bool:
    if resp.status in {403, 429, 503}:
        return True
    if len(resp.corpo) > 200_000:
        return False
    texto = resp.texto[:8000].lower()
    return any(marca in texto for marca in _MARCADORES)
