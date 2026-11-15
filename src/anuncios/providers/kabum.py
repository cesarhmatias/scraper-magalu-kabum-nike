"""KaBuM!: busca interna pela API de catalogo (JSON, sem JavaScript).

O HTML de `/busca/<termo>` e um shell Next.js; o SSR pode trazer o catalogo, mas
a paginacao so existe na API que o proprio site consome:
`servicespub.../catalog/v2/products?query=<termo>&page_number=<n>`.
Os headers seguem a ordem exata da chamada XHR capturada no Chrome.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

from ..config import headers_api_json, headers_navegacao
from ..http import ErroColeta, SemResultados
from ..models import Anuncio, ResultadoDominio
from ..utilitarios import numero, slug
from .base import Provider

API = "https://servicespub.prod.api.aws.grupokabum.com.br/catalog/v2/products"
SITE = "https://www.kabum.com.br"
TAMANHO_PAGINA = 60


class Kabum(Provider):
    nome = "kabum"
    dominio = "kabum.com.br"
    aliases = ("kabum", "ka bu m", "kabum!", "grupokabum")
    descricao = "KaBuM! (API de catalogo, JSON)"

    def coletar(self, termo: str, paginas: int = 1) -> ResultadoDominio:
        inicio = time.perf_counter()
        termo = termo.strip()
        out = ResultadoDominio(dominio=self.dominio, termo=termo, paginas=paginas)
        url_busca = f"{SITE}/busca/{slug(termo)}"
        # aquecimento: cookies do site e, se houver, challenge do DataDome/Akamai
        self.http.aquecer(SITE + "/", headers_navegacao())
        headers = headers_api_json(origem=SITE, referer=url_busca)
        vistos: set[str] = set()
        total = None
        limite = 50 if paginas <= 0 else paginas
        paginas_feitas = 0
        pagina = 1
        while pagina <= limite:
            url = (
                f"{API}?query={quote_plus(termo)}&page_number={pagina}"
                f"&page_size={TAMANHO_PAGINA}&sort=most_searched&facet_filters="
                f"&is_prime=false&payload_data=products_all_filters&include=gift"
            )
            try:
                resp = self.http.get(url, headers, esperado="json", rotulo=f"kabum-p{pagina}")
            except ErroColeta as exc:
                if "404" in str(exc):
                    if pagina == 1:
                        raise SemResultados(f"Kabum nao encontrou anuncios para {termo!r}") from None
                    break
                raise
            out.transporte = resp.http_version
            out.url_consulta = url_busca
            dados = resp.json()
            meta = dados.get("meta") or {}
            total = meta.get("total_items_count") or total
            out.total_declarado = total
            itens = dados.get("data") or []
            if not itens:
                if pagina == 1:
                    raise SemResultados(f"Kabum nao encontrou anuncios para {termo!r}")
                break

            for pos, item in enumerate(itens, start=1):
                anuncio = self._mapear(item, termo, pagina, pos, resp.url_final)
                chave = anuncio.id or anuncio.url or f"{pagina}-{pos}"
                if chave in vistos:
                    continue
                vistos.add(chave)
                out.anuncios.append(anuncio)

            if total is not None and pagina * TAMANHO_PAGINA >= int(total):
                break
            paginas_feitas = pagina
            if len(itens) < TAMANHO_PAGINA:
                break
            pagina += 1
            time.sleep(0.35)

        out.paginas = paginas_feitas or 1
        out.duracao_ms = int((time.perf_counter() - inicio) * 1000)
        if total is not None:
            out.avisos.append(f"total_declarado={total}")
        return out

    def _mapear(self, item: dict, termo: str, pagina: int, pos: int, fonte: str) -> Anuncio:
        a = item.get("attributes") or {}
        preco = numero(a.get("price_with_discount")) or numero(a.get("price"))
        bruto = numero(a.get("price"))
        antigo = numero(a.get("old_price"))
        original = None
        for candidato in (antigo, bruto):
            if candidato and preco and candidato > preco:
                original = candidato
                break
        desconto = a.get("discount_percentage")
        try:
            desconto = int(desconto) if desconto not in (None, "", 0) else None
        except (TypeError, ValueError):
            desconto = None
        if not desconto and original and preco and original > 0:
            desconto = round((1 - preco / original) * 100)

        imagens = a.get("images") or []
        if not imagens:
            fotos = a.get("photos") or {}
            for chave in ("g", "m", "p"):
                if fotos.get(chave):
                    imagens = fotos[chave]
                    break
        imagem = imagens[0] if imagens else None

        link = a.get("product_link") or ""
        url = None
        if link:
            base = link if link.startswith("http") else f"{SITE}/produto/{item.get('id')}/{link}"
            url = base
        elif a.get("external_url"):
            url = a["external_url"]

        vendedor = ((a.get("marketplace") or {}).get("seller_name")) or "KaBuM!"
        marca = ((a.get("manufacturer") or {}).get("name"))
        avaliacao = numero(a.get("average_of_ratings"))
        if avaliacao == 0.0:
            avaliacao = None
        avaliacoes = a.get("number_of_ratings")
        try:
            avaliacoes = int(avaliacoes) if avaliacoes is not None else None
        except (TypeError, ValueError):
            avaliacoes = None

        return Anuncio(
            dominio=self.dominio,
            termo=termo,
            pagina=pagina,
            posicao=pos,
            id=str(item.get("id") or "") or None,
            titulo=a.get("title") or "",
            marca=marca,
            preco=preco,
            preco_original=original,
            desconto_pct=desconto,
            parcelamento=a.get("max_installment") or None,
            vendedor=vendedor,
            categoria=a.get("menu") or a.get("category"),
            preco_pix=None,
            disponivel=a.get("available"),
            avaliacao=avaliacao,
            avaliacoes=avaliacoes,
            patrocinado=None,
            url=url,
            imagem=imagem,
            coletado_em=datetime.now(timezone.utc),
            transporte=self.http.ultimo_transporte,
            fonte=fonte,
        )
