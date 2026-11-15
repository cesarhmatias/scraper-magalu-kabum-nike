from __future__ import annotations

import json
from pathlib import Path

from anuncios.config import Config
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
