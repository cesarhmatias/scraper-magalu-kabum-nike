"""Captura uma sessao do challenge sec-if-cpt do Magalu para o solver Node.

Salva out/solver/session.json com HTML, URLs dos scripts, cookies e o proxy
sticky usado (o solver Node precisa sair pelo MESMO exit).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from curl_cffi import requests

from anuncios.config import headers_navegacao, normalizar_proxy

ALVO = "https://www.magazineluiza.com.br/busca/tenis/"
SAIDA = Path(__file__).resolve().parents[1] / "out" / "solver" / "session.json"
SAIDA.parent.mkdir(parents=True, exist_ok=True)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36")


def proxy_sticky(n: int) -> str | None:
    base = normalizar_proxy(os.environ.get("ANUNCIOS_PROXY"))
    if not base:
        return None
    scheme, resto = base.split("://", 1)
    userinfo, host = resto.split("@", 1)
    user, senha = userinfo.split(":", 1)
    if "-session-" in user:
        user = user.split("-session-")[0]
    return f"{scheme}://{user}-session-solve{n}:{senha}@{host}"


def tentar(proxy: str | None) -> requests.Session:
    s = requests.Session(impersonate="chrome146", http_version="v2", proxy=proxy,
                          timeout=35, default_headers=False)
    return s


for n in range(1, 16):
    proxy = proxy_sticky(n)
    s = tentar(proxy)
    try:
        r = s.get(ALVO, headers=requests.Headers(headers_navegacao()))
    except Exception as exc:
        print(json.dumps({"n": n, "erro": f"{type(exc).__name__}: {exc}"[:120]}), file=sys.stderr)
        s.close()
        continue
    html = r.text
    if "sec-if-cpt" not in html:
        print(json.dumps({"n": n, "status": r.status_code, "bytes": len(r.content),
                          "kind": "sem challenge"}), file=sys.stderr)
        s.close()
        time.sleep(1)
        continue

    srcs = [x if x.startswith("http") else "https://www.magazineluiza.com.br" + x
            for x in re.findall(r'<script[^>]+src="([^"]+)"', html)]
    cookies = [{"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
              for c in s.cookies.jar]
    sessao = {
        "alvo": ALVO,
        "html": html,
        "srcs": srcs,
        "cookies": cookies,
        "proxy": proxy,
        "user_agent": UA,
    }
    SAIDA.write_text(json.dumps(sessao, ensure_ascii=False))
    print(json.dumps({"n": n, "kind": "challenge", "srcs": [u[:110] for u in srcs],
                      "cookies": sorted({c["name"] for c in cookies}),
                      "proxy": bool(proxy), "salvo": str(SAIDA)}, ensure_ascii=False))
    s.close()
    break
else:
    print("nenhum challenge reproduzido", file=sys.stderr)
    raise SystemExit(1)
