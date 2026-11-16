"""Verificacao final do solver: navega com curl_cffi (TLS Chrome) + cookies ganhos."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from curl_cffi import requests

from anuncios.config import headers_navegacao

JAR = Path(__file__).resolve().parents[1] / "out" / "solver" / "jar.json"
dados = json.loads(JAR.read_text())
cookie = "; ".join(f"{k}={v}" for k, v in dados["cookies"])

headers = []
for nome, valor in headers_navegacao(referer=dados["alvo"]):
    if nome == "priority":
        headers.append(("cookie", cookie))
    headers.append((nome, valor))

sessao = requests.Session(impersonate="chrome146", http_version="v2",
                          proxy=dados["proxy"], timeout=45, default_headers=False)
r = sessao.get(dados["alvo"], headers=requests.Headers(headers))
resultado = {
    "status": r.status_code,
    "bytes": len(r.content),
    "challenge": "sec-if-cpt" in r.text[:6000],
    "bloqueio": "Não é possível acessar" in r.text,
    "titulo": (r.text.split("<title>")[1].split("</title>")[0][:90] if "<title>" in r.text else None),
    "proxy": bool(dados["proxy"]),
}
print(json.dumps(resultado, ensure_ascii=False))
sys.exit(0 if resultado["status"] == 200 and not resultado["challenge"] and resultado["bytes"] > 100000 else 2)
