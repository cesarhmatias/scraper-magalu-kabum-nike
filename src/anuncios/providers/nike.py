"""Nike Brasil: busca interna pela API de sugestoes do BFF.

O documento `/busca` e `__N_SSP` e fica atras do Akamai Bot Manager (regra no
literal `term=`). A rota usada pelo proprio cliente para autocomplete/resultados
(`GET /nike-bff/v2/search/topsuggestions?term=...&limit=...`) responde JSON com
os produtos completos, sem JavaScript. O `limit` e o unico controle de volume
(a API ignora `page` e devolve no maximo 500 itens).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

from ..config import headers_api_json
from ..http import ErroColeta, SemResultados
from ..models import Anuncio, ResultadoDominio
from ..utilitarios import numero
from .base import Provider

SITE = "https://www.nike.com.br"
API = "https://apigateway.nike.com.br/nike-bff/v2/search/topsuggestions"
IMAGEM = "https://imgnike-a.akamaihd.net/360x360/{id}.jpg"
LIMITE_MAX = 500


class Nike(Provider):
    nome = "nike"
    dominio = "nike.com.br"
    aliases = ("nike", "nike br", "nike.com")
    descricao = "Nike Brasil (API topsuggestions do BFF, JSON)"

    def coletar(self, termo: str, paginas: int = 1) -> ResultadoDominio:
        inicio = time.perf_counter()
        termo = termo.strip()
        limite = LIMITE_MAX if paginas <= 0 else min(LIMITE_MAX, max(60, paginas * 60))
        out = ResultadoDominio(dominio=self.dominio, termo=termo, paginas=paginas)
        url = f"{API}?term={quote_plus(termo)}&limit={limite}"
        headers = headers_api_json(origem=SITE, referer=f"{SITE}/busca?term={quote_plus(termo)}")
        try:
            resp = self.http.get(url, headers, esperado="json", rotulo="nike-topsuggestions")
        except ErroColeta as exc:
            if "404" in str(exc):
                raise SemResultados(f"Nike nao encontrou anuncios para {termo!r}") from None
            raise

        out.transporte = resp.http_version
        out.url_consulta = url
        dados = resp.json()
        produtos = dados.get("products") or []
        if not produtos:
            raise SemResultados(f"Nike nao encontrou anuncios para {termo!r}")
        out.total_declarado = len(produtos)
        out.paginas = 1
        for pos, produto in enumerate(produtos, start=1):
            anuncio = self._mapear(produto, termo, pos, resp.url_final)
            anuncio.transporte = resp.http_version
            out.anuncios.append(anuncio)
        out.duracao_ms = int((time.perf_counter() - inicio) * 1000)
        out.avisos.append(f"limite={limite} (API sem paginação)")
        if len(produtos) >= limite:
            out.avisos.append("limite atingido; aumente --paginas para buscar mais")
        return out

    @staticmethod
    def _mapear(p: dict, termo: str, pos: int, fonte: str) -> Anuncio:
        info = p.get("priceInfo") or {}
        preco = numero(info.get("price"))
        original = numero(info.get("listPrice"))
        if original and preco and original <= preco:
            original = None
        pix = info.get("pixDiscount") or {}
        preco_pix = numero(pix.get("price"))
        desconto = info.get("discount")
        try:
            desconto = int(desconto) if desconto not in (None, "", 0) else None
        except (TypeError, ValueError):
            desconto = None
        if not desconto and original and preco and original > 0:
            desconto = round((1 - preco / original) * 100)
        ident = str(p.get("id") or "") or None
        caminho = p.get("url") or ""
        url = caminho if caminho.startswith("http") else (SITE + caminho if caminho else None)
        imagem = p.get("imageUrl") or (IMAGEM.format(id=ident) if ident else None)
        return Anuncio(
            dominio=Nike.dominio,
            termo=termo,
            pagina=1,
            posicao=pos,
            id=ident,
            titulo=p.get("name") or "",
            marca="Nike",
            preco=preco,
            preco_original=original,
            desconto_pct=desconto,
            parcelamento=None,
            vendedor="Nike",
            categoria=p.get("category"),
            preco_pix=preco_pix,
            disponivel=None,
            avaliacao=None,
            avaliacoes=None,
            patrocinado=None,
            url=url,
            imagem=imagem,
            coletado_em=datetime.now(timezone.utc),
            transporte="h2",
            fonte=fonte,
        )
