"""Magazine Luiza: busca interna pelo endpoint `_next/data` (JSON do Next.js).

O HTML de `/busca/...` fica atras do Akamai Bot Manager. O endpoint de dados do
Next.js (`/_next/data/<buildId>/busca/<termo>.json`) responde JSON sem executar
JavaScript, desde que o buildId atual seja descoberto. O buildId e obtido do
site mobile (m.magazineluiza.com.br), que nao aplica o mesmo challenge.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from ..config import RAIZ, headers_navegacao, headers_next_data
from ..http import ErroColeta, Http, SemResultados
from ..log import evento
from ..models import Anuncio, ResultadoDominio
from ..utilitarios import numero, reais, slug
from .base import Provider

_CACHE = RAIZ / "out" / ".cache"
_RE_BUILD = re.compile(r"/_next/static/([A-Za-z0-9_-]{12,32})/_buildManifest\.js")
_RE_BUILD_JSON = re.compile(r'"buildId"\s*:\s*"([^"]+)"')


class Magalu(Provider):
    nome = "magalu"
    dominio = "magazineluiza.com.br"
    aliases = ("magazineluiza", "magazine", "magazine luiza", "magalu.com.br")
    descricao = "Magazine Luiza (endpoint _next/data, JSON)"

    BASE = "https://www.magazineluiza.com.br"
    MOBILE = "https://m.magazineluiza.com.br/"

    def __init__(self, cfg):
        super().__init__(cfg)
        self._build_id: str | None = None
        _CACHE.mkdir(parents=True, exist_ok=True)
        self._cache = _CACHE / "magalu-buildid"

    # -- buildId -----------------------------------------------------------
    def _ler_cache(self) -> str | None:
        try:
            valor = self._cache.read_text().strip()
            return valor if re.fullmatch(r"[A-Za-z0-9_-]{12,32}", valor) else None
        except OSError:
            return None

    def _gravar_cache(self, valor: str) -> None:
        try:
            self._cache.write_text(valor)
        except OSError:
            pass

    def _descobrir_build_id(self, forcar: bool = False) -> str:
        if self._build_id and not forcar:
            return self._build_id
        if not forcar:
            cache = self._ler_cache()
            if cache:
                self._build_id = cache
                return cache
        # A home mobile em h3 as vezes recebe o challenge de ~2 KB do Akamai.
        # Tentamos h2 numa sessao descartavel para nao rebaixar a sessao principal
        # (o endpoint _next/data negocia h3 normalmente).
        m = None
        resp = self.http.aquecer(self.MOBILE, headers_navegacao())
        texto = resp.texto if resp else ""
        m = _RE_BUILD.search(texto) or _RE_BUILD_JSON.search(texto)
        if not m:
            evento("aviso", acao="magalu_build_fallback_h2",
                   bytes=len(resp.corpo) if resp else 0)
            alternativo = Http(self.cfg, self.dominio)
            try:
                alternativo.forcar_h2()
                resp2 = alternativo.aquecer(self.MOBILE, headers_navegacao())
                texto2 = resp2.texto if resp2 else ""
                m = _RE_BUILD.search(texto2) or _RE_BUILD_JSON.search(texto2)
            finally:
                alternativo.fechar()
        if not m:
            raise ErroColeta(
                "nao foi possivel descobrir o buildId do Magalu em "
                f"{self.MOBILE}; a home mobile pode ter mudado ou bloqueado a coleta"
            )
        self._build_id = m.group(1)
        self._gravar_cache(self._build_id)
        evento("info", acao="magalu_build_id", build_id=self._build_id)
        return self._build_id

    # -- coleta ------------------------------------------------------------
    def coletar(self, termo: str, paginas: int = 1) -> ResultadoDominio:
        inicio = time.perf_counter()
        termo = termo.strip()
        s = slug(termo)
        out = ResultadoDominio(dominio=self.dominio, termo=termo, paginas=paginas)
        build = self._descobrir_build_id()
        vistos: set[str] = set()
        build_refeito = False
        limite = 50 if paginas <= 0 else paginas
        total_paginas = None
        paginas_feitas = 0
        pagina = 1
        while pagina <= limite:
            url = f"{self.BASE}/_next/data/{build}/busca/{quote(s, safe='-')}.json"
            if pagina > 1:
                url += f"?page={pagina}"
            headers = headers_next_data(referer=f"{self.BASE}/busca/{s}/")
            try:
                resp = self.http.get(url, headers, esperado="json", rotulo=f"magalu-p{pagina}")
            except ErroColeta as exc:
                if "404" in str(exc) and not build_refeito:
                    build_refeito = True
                    build = self._descobrir_build_id(forcar=True)
                    url = f"{self.BASE}/_next/data/{build}/busca/{quote(s, safe='-')}.json"
                    if pagina > 1:
                        url += f"?page={pagina}"
                    resp = self.http.get(url, headers, esperado="json", rotulo=f"magalu-p{pagina}")
                else:
                    raise
            out.transporte = resp.http_version
            out.url_consulta = url
            out.build_id = build
            dados = resp.json()
            busca = (dados.get("pageProps") or {}).get("data", {}).get("search") or {}
            itens = busca.get("items") or []
            paginacao = busca.get("pagination") or {}
            out.total_declarado = out.total_declarado or paginacao.get("records")
            total_paginas = paginacao.get("pages") or total_paginas
            if not itens:
                if pagina == 1:
                    raise SemResultados(f"Magalu nao retornou anuncios para {termo!r}")
                break

            for pos, item in enumerate(itens, start=1):
                anuncio = self._mapear(item, termo, pagina, pos, resp.url_final)
                chave = anuncio.id or anuncio.url or f"{pagina}-{pos}"
                if chave in vistos:
                    continue
                vistos.add(chave)
                out.anuncios.append(anuncio)

            paginas_feitas = pagina
            if total_paginas and pagina >= int(total_paginas):
                break
            pagina += 1

        out.paginas = paginas_feitas or 1
        out.duracao_ms = int((time.perf_counter() - inicio) * 1000)
        out.avisos.append(f"buildId={build}")
        return out

    def _mapear(self, item: dict, termo: str, pagina: int, pos: int, fonte: str) -> Anuncio:
        ofertas = item.get("offers") or [{}]
        oferta = ofertas[0] or {}
        preco = numero(oferta.get("price"))
        original = numero(oferta.get("listPrice"))
        if original and preco and original <= preco:
            original = None
        best = oferta.get("bestPrice") or {}
        desconto = None
        if original and preco and original > 0:
            desconto = round((1 - preco / original) * 100)
        elif best.get("discount"):
            desconto = int(best["discount"])

        plano = oferta.get("bestInstallmentPlan") or {}
        texto_parcela = None
        if plano.get("installment"):
            texto_parcela = f"{plano['installment']}x de {reais(numero(plano.get('installmentAmount')))}"
            if plano.get("paymentMethodDescription"):
                texto_parcela += f" {plano['paymentMethodDescription']}"

        vendedor = ((oferta.get("seller") or {}).get("id"))
        marca = ((item.get("brand") or {}).get("label"))
        categoria = item.get("category")
        if isinstance(categoria, dict):
            categoria = categoria.get("label") or categoria.get("name")
        pix = best.get("totalAmount") if str(best.get("paymentMethodId", "")).lower() == "pix" else None
        if pix is None and "pix" in str(best.get("paymentMethodDescription", "")).lower():
            pix = best.get("totalAmount")
        url = self.BASE + item["path"] if item.get("path") else None
        imagem = item.get("image")
        if imagem:
            imagem = imagem.replace("{w}x{h}", "400x400")
        patrocinado = (item.get("ads") or {}).get("sponsored")
        return Anuncio(
            dominio=self.dominio,
            termo=termo,
            pagina=pagina,
            posicao=pos,
            id=str(item.get("id") or "") or None,
            titulo=item.get("title") or "",
            marca=marca,
            preco=preco,
            preco_original=original,
            desconto_pct=desconto,
            parcelamento=texto_parcela,
            vendedor=vendedor,
            categoria=categoria if isinstance(categoria, str) else None,
            preco_pix=numero(pix),
            disponivel=item.get("available"),
            avaliacao=numero(item.get("reviewRating")),
            avaliacoes=int(item["reviewCount"]) if item.get("reviewCount") is not None else None,
            patrocinado=bool(patrocinado) if patrocinado is not None else None,
            url=url,
            imagem=imagem,
            coletado_em=datetime.now(timezone.utc),
            transporte=self.http.ultimo_transporte,
            fonte=fonte,
        )
