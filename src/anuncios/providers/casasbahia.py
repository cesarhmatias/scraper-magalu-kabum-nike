"""Casas Bahia: busca interna pela API v3 do parceiro (JSON) + API de precos.

O HTML de `/<termo>/b` e SSR e fica atras do Akamai Bot Manager: sem os cookies
`bm_*`/`_abck` validados por sensor JavaScript a resposta e o desafio
`sec-if-cpt` (ou a pagina de erro 403). A propria pagina SSR usa a
`SEARCH_API_V3` publicada no `runtimeConfig` do `__NEXT_DATA__`, que devolve o
mesmo JSON da busca sem executar JavaScript.

Os precos nao vem nesse JSON: o site os pede em lote para
`api.casasbahia.com.br` (`POST /Preco/Oferta/PrecoVenda/`, headers `xaplication`
e `apikey`). O corpo aceita `idProduto`/`skus` e devolve ofertas com preco de,
preco, Pix, parcelamento e disponibilidade.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Iterable, Iterator
from urllib.parse import urlencode

from ..config import headers_api_json, headers_preco_json
from ..http import ErroColeta, SemResultados
from ..log import evento
from ..models import Anuncio, ResultadoDominio
from ..utilitarios import numero, reais, slug
from .base import Provider

SITE = "https://www.casasbahia.com.br"
API = "https://api-partner-prd.casasbahia.com.br/api/v3/web/busca"
PRECO = (
    "https://api.casasbahia.com.br/merchandising/oferta/v1/Preco/Oferta/"
    "PrecoVenda/?IdRegiao=&composicao=DescontoFormaPagamento,"
    "MelhoresParcelamentos&canal=SITE&origem=vv-categoria-frontend"
)
API_KEY = "casasbahia"                 # `ApiKey` da busca (runtimeConfig)
PARTNER_KEY = "elastic"                # `PartnerKey` do motor de busca
PRICE_API_KEY = "d081fef8c2c44645bb082712ed32a047"  # `PRICE_API_KEY` do runtimeConfig
TAMANHO_PAGINA = 20                    # ResultsPerPage aceita 0..21; o site usa 20
LOTE_PRECO = 50                        # ids por POST de preco
MAX_PAGINAS = 50
MAX_PRODUTOS = 10_000                  # `maxSize` declarado pela API


def url_busca(termo: str, pagina: int) -> str:
    """URL da busca v3, com os mesmos nomes de parametro do Next.js (minúsculos)."""
    params = {
        "resultsperpage": TAMANHO_PAGINA,
        "apikey": API_KEY,
        "filter": "",
        "page": pagina,
        "banner": "true",
        "platformtype": 1,
        "variantconfiguration": "Q4",
        "multiselection": "true",
        "partnerkey": PARTNER_KEY,
        "enablepriceslider": "false",
        "terms": termo,
        "sessionid": "",
        "userid": "",
        "visitorid": "",
        "wps": "true",
    }
    return f"{API}?{urlencode(params)}"


def _lotes(itens: list[int], tamanho: int) -> Iterator[list[int]]:
    for inicio in range(0, len(itens), tamanho):
        yield itens[inicio:inicio + tamanho]


class CasasBahia(Provider):
    nome = "casasbahia"
    dominio = "casasbahia.com.br"
    aliases = ("casas bahia", "casasbahia", "casas-bahia", "casas bahia.com.br")
    descricao = "Casas Bahia (API de busca v3 + API de precos, JSON)"

    # -- coleta ------------------------------------------------------------
    def coletar(self, termo: str, paginas: int = 1) -> ResultadoDominio:
        inicio = time.perf_counter()
        termo = termo.strip()
        out = ResultadoDominio(dominio=self.dominio, termo=termo, paginas=paginas)
        limite = MAX_PAGINAS if paginas <= 0 else min(MAX_PAGINAS, paginas)
        headers = headers_api_json(origem=SITE, referer=f"{SITE}/{slug(termo)}/b")

        produtos: list[tuple[int, int, dict, str]] = []
        vistos: set[str] = set()
        total: int | None = None
        total_paginas: int | None = None
        paginas_feitas = 0
        pagina = 1
        while pagina <= limite:
            url = url_busca(termo, pagina)
            try:
                resp = self.http.get(
                    url, headers, esperado="json", rotulo=f"casasbahia-p{pagina}"
                )
            except ErroColeta as exc:
                if "404" in str(exc):
                    if pagina == 1:
                        raise SemResultados(
                            f"Casas Bahia nao encontrou anuncios para {termo!r}"
                        ) from None
                    break
                raise

            out.transporte = resp.http_version
            out.url_consulta = out.url_consulta or url
            dados = resp.json()
            total = dados.get("size") or total
            if total:
                total_paginas = math.ceil(int(total) / TAMANHO_PAGINA)
            itens = dados.get("products") or []
            if not itens:
                if pagina == 1:
                    raise SemResultados(f"Casas Bahia nao encontrou anuncios para {termo!r}")
                break

            for pos, produto in enumerate(itens, start=1):
                chave = str(produto.get("id") or "")
                if chave and chave in vistos:
                    continue
                vistos.add(chave)
                produtos.append((pagina, pos, produto, resp.url_final))

            paginas_feitas = pagina
            if total_paginas and pagina >= total_paginas:
                break
            if len(itens) < TAMANHO_PAGINA:
                break
            pagina += 1
            time.sleep(0.35)

        if not produtos:
            raise SemResultados(f"Casas Bahia nao encontrou anuncios para {termo!r}")

        ids = [int(p["id"]) for _, _, p, _ in produtos if str(p.get("id") or "").isdigit()]
        precos, falhas_preco = self._buscar_precos(ids)

        out.total_declarado = total
        out.paginas = paginas_feitas or 1
        out.build_id = f"{PARTNER_KEY}:{API_KEY}"
        for pagina_origem, pos, produto, fonte in produtos:
            oferta = precos.get(str(produto.get("id")))
            out.anuncios.append(
                self._mapear(produto, oferta, termo, pagina_origem, pos, fonte)
            )
        out.duracao_ms = int((time.perf_counter() - inicio) * 1000)
        out.avisos.append(f"api=v3 parceiro={PARTNER_KEY} chave={API_KEY}")
        aviso_preco = f"precos={len(precos)}/{len(produtos)} (lotes de {LOTE_PRECO})"
        if falhas_preco:
            aviso_preco += f"; {falhas_preco} lote(s) de preco com falha"
        out.avisos.append(aviso_preco)
        if paginas <= 0 and total and total >= MAX_PRODUTOS:
            out.avisos.append(f"total limitado a {MAX_PRODUTOS} pela API")
        elif paginas <= 0 and total and total > MAX_PAGINAS * TAMANHO_PAGINA:
            out.avisos.append(
                f"total {total} acima do limite de {MAX_PAGINAS} paginas "
                f"({MAX_PAGINAS * TAMANHO_PAGINA} itens)"
            )
        return out

    # -- precos ------------------------------------------------------------
    def _buscar_precos(self, ids: Iterable[int]) -> tuple[dict[str, dict], int]:
        """POST em lote; devolve ofertas por `IdProduto` e a contagem de falhas."""
        ofertas: dict[str, dict] = {}
        falhas = 0
        headers = headers_preco_json(origem=SITE, referer=f"{SITE}/", apikey=PRICE_API_KEY)
        validos = [i for i in ids if i]
        for lote in _lotes(validos, LOTE_PRECO):
            corpo = {"produtos": [{"idProduto": i} for i in lote], "skus": []}
            try:
                resp = self.http.post(
                    PRECO, headers, corpo, esperado="json", rotulo="casasbahia-preco"
                )
                dados = resp.json()
            except (ErroColeta, ValueError) as exc:
                falhas += 1
                evento("aviso", acao="casasbahia_preco_falhou",
                       ids=len(lote), erro=str(exc)[:300])
                continue
            for oferta in dados.get("Ofertas") or []:
                id_produto = (oferta.get("PrecoVenda") or {}).get("IdProduto")
                if id_produto is not None:
                    ofertas[str(id_produto)] = oferta
        return ofertas, falhas

    # -- mapeamento --------------------------------------------------------
    def _mapear(
        self,
        produto: dict,
        oferta: dict | None,
        termo: str,
        pagina: int,
        pos: int,
        fonte: str,
    ) -> Anuncio:
        oferta = oferta or {}
        preco_venda = oferta.get("PrecoVenda") or {}
        desconto_pagamento = oferta.get("DescontoFormaPagamento") or {}

        preco = numero(preco_venda.get("Preco"))
        original = numero(preco_venda.get("PrecoDe"))
        if original and preco and original <= preco:
            original = None
        desconto = None
        if original and preco and original > 0:
            desconto = round((1 - preco / original) * 100)
        if not desconto:
            percentual = numero(preco_venda.get("PercentualDesconto"))
            if percentual and percentual < 0:
                desconto = round(abs(percentual))

        preco_pix = None
        if desconto_pagamento.get("PossuiDesconto"):
            forma = f"{desconto_pagamento.get('FormaPagamento') or ''} " \
                    f"{desconto_pagamento.get('DescricaoDesconto') or ''}".lower()
            if "pix" in forma:
                preco_pix = numero(desconto_pagamento.get("PrecoVendaComDesconto"))
                if preco_pix and preco and preco_pix >= preco:
                    preco_pix = None

        disponivel = None
        status = produto.get("status")
        if status:
            disponivel = status == "AVAILABLE"
        disponibilidade = oferta.get("Disponibilidade") or {}
        if disponibilidade:
            partes = [
                disponibilidade.get("DisponibilidadeEstoque"),
                disponibilidade.get("DisponibilidadeVenda"),
            ]
            if all(p is not None for p in partes):
                disponivel = bool(all(partes))

        avaliacao = numero(produto.get("rating"))
        if avaliacao == 0.0:
            avaliacao = None
        avaliacoes = produto.get("ratingComments")
        try:
            avaliacoes = int(avaliacoes) if avaliacoes is not None else None
        except (TypeError, ValueError):
            avaliacoes = None

        categorias = produto.get("categories") or []
        categoria = (categorias[0] or {}).get("name") if categorias else None
        marca = (produto.get("brand") or {}).get("brand")
        id_produto = str(produto.get("id") or "") or None
        url = produto.get("url")
        patrocinado = None
        if produto.get("hasSponsorProducts") is not None:
            patrocinado = bool(produto.get("hasSponsorProducts"))

        return Anuncio(
            dominio=self.dominio,
            termo=termo,
            pagina=pagina,
            posicao=pos,
            id=id_produto,
            titulo=produto.get("name") or "",
            marca=marca,
            preco=preco,
            preco_original=original,
            desconto_pct=desconto,
            parcelamento=self._parcelamento(oferta),
            vendedor=self._vendedor(produto, preco_venda),
            categoria=categoria if isinstance(categoria, str) else None,
            preco_pix=preco_pix,
            disponivel=disponivel,
            avaliacao=avaliacao,
            avaliacoes=avaliacoes,
            patrocinado=patrocinado,
            url=url if isinstance(url, str) and url.startswith("http") else None,
            imagem=produto.get("image"),
            coletado_em=datetime.now(timezone.utc),
            transporte=self.http.ultimo_transporte,
            fonte=fonte,
        )

    @staticmethod
    def _parcelamento(oferta: dict) -> str | None:
        """Melhor parcela sem juros; senao, o texto de parcelamento da oferta."""
        opcoes = []
        for plano in oferta.get("MelhoresParcelamentos") or []:
            qtd = plano.get("QtdParcela")
            valor = numero(plano.get("ValorParcela"))
            if qtd and valor:
                opcoes.append((int(qtd), valor, str(plano.get("Descricao") or "")))
        sem_juros = [o for o in opcoes if "sem juros" in o[2].lower()]
        if sem_juros:
            qtd, valor, _ = max(sem_juros, key=lambda o: o[0])
            return f"{qtd}x de {reais(valor)}"
        return (oferta.get("PrecoVenda") or {}).get("Parcelamento") or None

    @staticmethod
    def _vendedor(produto: dict, preco_venda: dict) -> str | None:
        tipo = str(produto.get("sellerType") or "").strip()
        if tipo.lower() in {"nacional", "1p"}:
            return "Casas Bahia"
        if tipo:
            return tipo
        lojista = preco_venda.get("IdLojista")
        if lojista == 33013:
            return "Casas Bahia"
        if produto.get("productType") == "Nacional" or not lojista:
            return "Casas Bahia"
        return f"Lojista {lojista}"
