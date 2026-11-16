# Casas Bahia — coleta sem navegador (termo livre → listagem com preço)

Captura de referência: `/Users/cesar/Downloads/capture-casas-bahia-full` (Chrome 157, 2026-11-16,
954 requisições, página `https://www.casasbahia.com.br/iphone/b`).
Validação: HTTP puro com `curl_cffi` (`impersonate=chrome146`, h2, proxy SOCKS5 BR) e `__NEXT_DATA__`
da captura.

## Resultado

Duas chamadas JSON, nenhuma delas protegida por sensor JavaScript:

```
GET  https://api-partner-prd.casasbahia.com.br/api/v3/web/busca?<params>
POST https://api.casasbahia.com.br/merchandising/oferta/v1/Preco/Oferta/PrecoVenda/?<params>
```

A busca devolve os produtos (sem preço). O preço vem da API de merchandising em lote
(`{"produtos":[{"idProduto":N},...],"skus":[]}` → `Ofertas`).

## 1. Descoberta da API de busca

O HTML de `/<termo>/b` é SSR (`pageType: "search"`) e o `__NEXT_DATA__` traz o estado completo.
No `runtimeConfig` do mesmo JSON está a URL usada **pelo servidor Next**:

```json
{
  "SEARCH_API_V3": "https://api-partner-prd.casasbahia.com.br/api/v3/web",
  "PARTNER_KEY": "elastic",
  "RESULTS_PER_PAGE": "20",
  "NPRICE_ENDPOINT": "https://api.casasbahia.com.br/merchandising/oferta/v1/Preco",
  "NPRICE_OFERTA_PATH": "/Oferta/PrecoVenda/",
  "PRICE_API_KEY": "d081fef8c2c44645bb082712ed32a047"
}
```

O construtor da chamada está no chunk do cliente
`catalogo-ssr/_next/static/chunks/…` (módulo `4410`/`E`), não no HTML:

```js
let Z = new URL(`${n.RY}/${e.strbusca ? "busca" : "categoria"}`);
Object.entries(T).forEach(([t, r]) => {
  (Array.isArray(r) ? r : [r]).forEach(v => Z.searchParams.append(t.toLowerCase(), v ?? ""));
});
```

Ou seja: a rota é `/busca` e **todos os nomes de parâmetro são minúsculos**
(`ResultsPerPage` → `resultsperpage`, `PartnerKey` → `partnerkey`, etc.).

### Chamada usada pelo provedor

```text
GET /api/v3/web/busca
    ?resultsperpage=20
    &apikey=casasbahia
    &filter=
    &page=1
    &banner=true
    &platformtype=1
    &variantconfiguration=Q4
    &multiselection=true
    &partnerkey=elastic
    &enablepriceslider=false
    &terms=iphone
    &sessionid=
    &userid=
    &visitorid=
    &wps=true
```

`size`/`sizeLabel` no retorno são o total declarado (`1.473 produtos encontrados`). `terms` aceita
texto livre com acento e espaço (a API normaliza, ex.: `tênis de corrida` → `tenis-de-corrida`).

### Limites verificados

| teste | resultado |
|---|---|
| `resultsperpage=20` | 200, 20 produtos (valor que o site usa) |
| `resultsperpage=21` | 200, 21 produtos (teto da validação) |
| `resultsperpage=24…100` | **400** `The field ResultsPerPage must be between 0 and 21.` |
| `resultsperpage=0` | **204** sem corpo (não serve para listar) |
| `page=2,3,10` | 200, 20 produtos cada, sem repetição |
| `page=74` (última de 1.473) | 200, 13 produtos |
| `page>74` | 200, `products: []` |
| termo sem correspondência | devolve resultados aproximados nos testes (não houve zero para medir o fallback) |

Por isso `TAMANHO_PAGINA = 20` e o provedor para em `len(products) < 20`, na última página
calculada (`ceil(size/20)`) ou em 50 páginas (limite do CLI).

### Schema do produto (API, sem preço)

```json
{
  "id": "93574465",
  "name": "Iphone 17 Pro Max 256Gb Laranja-Cósmico",
  "sku": 1582380324,
  "url": "https://www.casasbahia.com.br/iphone-17-pro-max-256gb-laranja-cosmico/p/1582380324",
  "image": "https://imgs.casasbahia.com.br/1582380324/1xg.jpg",
  "brand": { "idBrand": "19", "brand": "Apple" },
  "categories": [{ "id": "38", "name": "Telefones e Celulares", "subCategory": [...] }],
  "rating": 5.0,
  "ratingComments": 4,
  "status": "AVAILABLE",
  "sellerType": null,
  "productType": "Nacional",
  "hasSponsorProducts": false
}
```

## 2. Descoberta da API de preço

Preço não vem no JSON da busca. O cliente pede preço por produto/lote em
`api.casasbahia.com.br`. A captura registrou o POST em lote (índice 426 de `session.json`):

```http
POST /merchandising/oferta/v1/Preco/Oferta/PrecoVenda/?IdRegiao=&composicao=DescontoFormaPagamento,MelhoresParcelamentos&canal=SITE&origem=vv-categoria-frontend
content-type: application/json
xaplication: vv-categoria-frontend
apikey: d081fef8c2c44645bb082712ed32a047

{"produtos":[{"idProduto":93574465},{"idProduto":93574538}],"skus":[]}
```

Ordem dos headers (captura, `orderState: sourceOrder`):
`pragma, cache-control, sec-ch-ua-platform, xaplication, user-agent, sec-ch-ua, content-type,
apikey, sec-ch-ua-mobile, accept, origin, sec-fetch-site, sec-fetch-mode, sec-fetch-dest, referer,
accept-encoding, accept-language, priority`.

Resposta (`Ofertas`, uma por produto que tem oferta):

```json
{"PrecoVenda": {
   "IdSku": 1582380324, "IdProduto": 93574465, "IdLojista": 33013,
   "PrecoDe": 13999.0, "Preco": 9599.0, "PercentualDesconto": -31,
   "Parcelamento": "12x de R$799,91", "NumeroParcelas": 12, "ValorParcela": 799.91,
   "DisponibilidadeVenda": true, "DisponibilidadeEstoque": true
 },
 "DescontoFormaPagamento": {
   "PossuiDesconto": true, "FormaPagamento": "Pix", "DescricaoDesconto": "No Pix",
   "PercentualDesconto": 10.0, "PrecoVendaComDesconto": 8639.1
 },
 "MelhoresParcelamentos": [{"Tipo": "Outros", "QtdParcela": 12, "ValorParcela": 799.91, "Descricao": "sem juros"}],
 "Disponibilidade": {"Nacional": true, "DisponibilidadeOferta": true, "IdSku": 1582380324, "IdLojista": 33013}
}
```

- `Preco` é o preço cheio; `PrecoDe` é o "de" (só vira `preco_original` quando maior).
- `PercentualDesconto` vem negativo (`-31` = 31% off); o provedor usa o valor absoluto quando o
  desconto calculado não existe.
- `DescontoFormaPagamento.PrecoVendaComDesconto` só vira `preco_pix` quando `PossuiDesconto` e a
  forma/descrição menciona Pix.
- `parcelamento` usa a maior parcela "sem juros" de `MelhoresParcelamentos`; na ausência, o texto
  `PrecoVenda.Parcelamento`.
- `IdLojista 33013` é tratado como Casas Bahia; demais viram `Lojista <id>` (a API não devolve o
  nome do lojista nesse endpoint).
- Lotes de 40 e 60 ids foram aceitos (200); o provedor usa 50. Produtos sem oferta são omitidos
  da resposta e ficam com preço vazio na planilha, sem derrubar a coleta.

### Alternativa GET (usada pelo cliente no card)

O bundle mostra também `GET {NPRICE_ENDPOINT}/Produto/PrecoVenda/?…&idsProduto=1,2,3`
(header `apiKey`). Verificado: 200 e mesma estrutura, em `PrecoProdutos`. O provedor usa o POST
porque é o que está na captura e não depende do tamanho da URL.

## 3. Por que não usar o HTML

O documento `/iphone/b` está atrás do Akamai Bot Manager:

| tentativa | resposta |
|---|---|
| `GET /iphone/b` sem cookies | **403** página "Ops! Algo deu errado" (~3,3 KB) |
| home `/` primeiro, depois `/iphone/b` | home 200; busca continua 403 |
| replay dos cookies da captura (`bm_so`, `_abck`, …) | **200**, mas corpo de 6.714 B com `sec-if-cpt` / "Powered and protected by Akamai" |

Na própria captura a segunda navegação para `/iphone/b` (índice 743) recebeu exatamente esse
desafio de 6,7 KB; a primeira (índice 314, 594 KB) passou porque o Chrome já tinha executado o
sensor do Akamai na home (`_abck` com `~0~`). Reproduzir isso exigiria navegador — o que o projeto
não usa. As APIs acima respondem 200 sem cookies e sem `_abck`.

## 4. Como reproduzir

```bash
# busca
curl -sS 'https://api-partner-prd.casasbahia.com.br/api/v3/web/busca?resultsperpage=20&apikey=casasbahia&filter=&page=1&banner=true&platformtype=1&variantconfiguration=Q4&multiselection=true&partnerkey=elastic&enablepriceslider=false&terms=iphone&sessionid=&userid=&visitorid=&wps=true' \
  -H 'accept: application/json' -H 'origin: https://www.casasbahia.com.br' \
  -H 'referer: https://www.casasbahia.com.br/iphone/b'

# preços (lote)
curl -sS -X POST 'https://api.casasbahia.com.br/merchandising/oferta/v1/Preco/Oferta/PrecoVenda/?IdRegiao=&composicao=DescontoFormaPagamento,MelhoresParcelamentos&canal=SITE&origem=vv-categoria-frontend' \
  -H 'content-type: application/json' -H 'xaplication: vv-categoria-frontend' \
  -H 'apikey: d081fef8c2c44645bb082712ed32a047' \
  -H 'origin: https://www.casasbahia.com.br' -H 'referer: https://www.casasbahia.com.br/' \
  --data '{"produtos":[{"idProduto":93574465}],"skus":[]}'
```

Pelo CLI:

```bash
.venv/bin/anuncios doctor
.venv/bin/anuncios buscar --termo "iphone" --dominio casasbahia --paginas 1
```

> As chaves `apikey` da busca e do preço são públicas no bundle do site (não são credenciais
> de usuário). O proxy SOCKS5 é usado apenas em teste; não versionar credenciais.
