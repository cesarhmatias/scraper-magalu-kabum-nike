from __future__ import annotations

import json
from pathlib import Path

from anuncios.config import Config
from anuncios.providers.casasbahia import CasasBahia, url_busca
from anuncios.providers.kabum import Kabum
from anuncios.providers.magalu import Magalu
from anuncios.providers.nike import Nike

FIXTURES = Path(__file__).parent / "fixtures"


def _cfg():
    return Config(proxy=None, transporte="h2", timeout=10)


def test_magalu_mapeia_item():
    item = json.loads((FIXTURES / "magalu_busca.json").read_text())["pageProps"]["data"]["search"]["items"][0]
    p = Magalu(_cfg())
    try:
        a = p._mapear(item, "tênis de corrida", 1, 1, "fonte")
    finally:
        p.fechar()
    assert a.id
    assert "Tênis" in a.titulo
    assert a.preco and a.preco > 0
    assert a.marca
    assert a.parcelamento and "x de" in a.parcelamento
    assert a.url.startswith("https://www.magazineluiza.com.br/")
    assert a.preco_pix is None or a.preco_pix > 0


def test_kabum_mapeia_item():
    item = json.loads((FIXTURES / "kabum_api.json").read_text())["data"][0]
    p = Kabum(_cfg())
    try:
        a = p._mapear(item, "processador", 1, 1, "fonte")
    finally:
        p.fechar()
    assert a.id == str(item["id"])
    assert a.titulo
    assert a.preco and a.preco > 0
    assert a.categoria
    assert a.url and a.url.startswith("https://www.kabum.com.br/produto/")


def test_nike_mapeia_produto():
    produto = json.loads((FIXTURES / "nike_topsuggestions.json").read_text())["products"][0]
    a = Nike._mapear(produto, "tenis", 1, "fonte")
    assert a.id == produto["id"]
    assert a.titulo == produto["name"]
    assert a.preco == float(produto["priceInfo"]["price"])
    assert a.url.startswith("https://www.nike.com.br/")
    assert a.imagem.endswith(f"{produto['id']}.jpg")
    assert a.vendedor == "Nike"


def _cb_fixtures():
    busca = json.loads((FIXTURES / "casasbahia_busca.json").read_text())
    preco = json.loads((FIXTURES / "casasbahia_preco.json").read_text())
    produtos = busca["products"]
    ofertas = preco["Ofertas"]
    return busca, preco, produtos, ofertas


def test_casasbahia_url_busca():
    url = url_busca("tênis de corrida", 2)
    assert url.startswith("https://api-partner-prd.casasbahia.com.br/api/v3/web/busca?")
    assert "resultsperpage=20" in url
    assert "apikey=casasbahia" in url
    assert "partnerkey=elastic" in url
    assert "page=2" in url
    assert "terms=t%C3%AAnis+de+corrida" in url


def test_casasbahia_mapeia_produto_com_preco():
    _, _, produtos, ofertas = _cb_fixtures()
    produto = produtos[0]
    oferta = next(o for o in ofertas if o["PrecoVenda"]["IdProduto"] == int(produto["id"]))
    p = CasasBahia(_cfg())
    try:
        a = p._mapear(produto, oferta, "iphone", 1, 1, "fonte")
    finally:
        p.fechar()
    pv = oferta["PrecoVenda"]
    assert a.id == produto["id"]
    assert a.titulo == produto["name"]
    assert a.marca == produto["brand"]["brand"]
    assert a.categoria == produto["categories"][0]["name"]
    assert a.preco == float(pv["Preco"])
    assert a.preco_original == float(pv["PrecoDe"])
    assert a.desconto_pct and a.desconto_pct > 0
    assert a.parcelamento and "x de" in a.parcelamento
    assert a.vendedor == "Casas Bahia"
    assert a.disponivel is True
    assert a.url.startswith("https://www.casasbahia.com.br/")
    assert a.imagem == produto["image"]


def test_casasbahia_mapeia_produto_sem_oferta():
    _, _, produtos, _ = _cb_fixtures()
    produto = produtos[0]
    p = CasasBahia(_cfg())
    try:
        a = p._mapear(produto, None, "iphone", 1, 1, "fonte")
    finally:
        p.fechar()
    assert a.id == produto["id"]
    assert a.preco is None
    assert a.preco_pix is None
    assert a.parcelamento is None
    # sem preco, a disponibilidade cai no status da busca
    assert a.disponivel is (produto["status"] == "AVAILABLE")
