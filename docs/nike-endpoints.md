# Nike.com.br — coleta sem navegador (termo livre → listagem)

Build Next: `v12-88-0` · Testes via HTTP puro (curl_cffi `impersonate=chrome146`, HTTP/2, proxy SOCKS5 BR)
Data: 2026-11-14 · ~57 requisições

## Resultado

**Caminho encontrado — API pública do BFF (JSON, sem HTML, sem sensor JS):**

```
GET https://apigateway.nike.com.br/nike-bff/v2/search/topsuggestions?term=<termo>&limit=<N>
```

Status **200**, `application/json`. É a busca real do autocomplete e devolve **produtos completos**, não só
sugestões. `limit` escala sem teto prático até o tamanho do catálogo do termo:

| chamada | status | bytes | produtos |
|---|---|---|---|
| `term=tenis&limit=10` | 200 | 2.768 | 10 |
| `term=tenis&limit=50` | 200 | 13.616 | 50 |
| `term=tenis&limit=100` | 200 | 27.141 | 100 |
| `term=tenis&limit=500` | 200 | 136.355 | 500 |

`page` é ignorado (`page=2&limit=10` devolveu body idêntico, 2.768 B) — paginação é só por `limit`.

### Schema (verificado)

```json
{
  "topSuggestions": ["tenis masculino", "tenis", "tenis feminino"],
  "products": [{
    "id": "107005IE",
    "name": "Tênis Nike Hybrid RN Masculino",
    "category": "Tênis",
    "url": "/tenis-nike-hybrid-rn-masculino-107005.html?cor=IE",
    "imageUrl": "",
    "priceInfo": {
      "price": "899.99",
      "listPrice": "899.99",
      "discount": 0,
      "pixDiscount": { "price": "854.99", "discount": 5 }
    }
  }]
}
```

`url` é relativa (prefixar `https://www.nike.com.br`). `imageUrl` veio vazio nesse tenant — montar imagem
pelo PDP ou usar `/marvin/enriched-pdp`. Preços são **string decimal** ("899.99"); `discount` é percentual.

### Base do BFF (extraída do bundle, não chutada)

`https://static.nike.com.br/v12-88-0/_next/static/chunks/pages/_app-254176096a507bb9.js` (2.47 MB) contém:

```js
publicApi:{ checkout:".../checkout", base:"https://apigateway.nike.com.br",
            bff:"https://apigateway.nike.com.br/nike-bff", core:"https://api.gruposbf.com.br", ... }
```

Rotas de busca usadas pelo cliente (as únicas no bundle): `/v2/search/topsuggestions`,
`/v2/search/topterms`. Outras confirmadas: `/v2/search/topterms` → 200/196 B;
`/marvin/quick-filters?term=` → 200/180 B (só filtros/links, não produtos).

## O que NÃO funciona (bloqueio Akamai)

`GET https://www.nike.com.br/busca?term=tenis` → **403, 540 B, `server: AkamaiGHost`**, corpo
`<HTML><HEAD><TITLE>Access Denied</TITLE>`. Headers que provam Bot Manager:

```
server: AkamaiGHost
x-akamai-transformed: 0 - 0 -
nikeakamaiconfigresponse: True
set-cookie: bm_s=...; bm_so=...; bm_sz=...   (sensor Akamai Bot Manager)
```

`/_next/data` também é filtrado — e a regra é cirúrgica, no literal `term=`:

| URL | status | corpo |
|---|---|---|
| `/_next/data/v12-88-0/index.json` | 200 | 52.092 B, `__N_SSG` (home, dados reais) |
| `/_next/data/v12-88-0/busca.json?q=tenis` | 404 | `{"notFound":true}` (`istio-envoy`) |
| `/_next/data/v12-88-0/busca.json?term=tenis` | 403 | Akamai Access Denied |
| `/_next/data/v12-88-0/busca.json?te%72m=tenis` | 403 | Akamai normaliza e bloqueia |
| `/_next/data/v12-88-0/busca.json?term%3Dtenis` | 404 | `{"notFound":true}` (param não é `term`) |
| `/v12-88-0/_next/data/v12-88-0/busca.json?term=tenis` | 404 | HTML Next 194 KB (rewrite só serve `static`) |

Diagnóstico: `/busca` é `__N_SSP` (gSSP server-side). Sem `term` o gSSP devolve `notFound`; com `term` o
Akamai corta antes. O rewrite `/v12-88-0/_next/:path+` → `/_next/:path+` existe só para assets estáticos.

Gateway tem **outra** propriedade Akamai, com regra por path — não é 404 do Express:
`/nike-bff/products` → 403 Akamai, mas `/nike-bff/products/` (trailing slash) → 404 Express
`{"code":404,"message":"Cannot GET /products/?term=tenis",...}`. Ou seja `/products` **existe** e está
bloqueado na borda, não ausente.

### Rotas testadas e inexistentes (404 JSON do Express)

`/docs`, `/swagger`, `/swagger-ui.html`, `/openapi.json`, `/v2/api-json`, `/api`,
`/marvin/search`, `/marvin/products`, `/marvin/plp`, `/marvin/vitrine`, `/marvin/filters`,
`/marvin/filters-and-products`, `/marvin/search-results`, `/v2/search/products`, `/v2/search/plp`,
`/v2/products`, `/v2/products/search`. Não há Swagger exposto. `OPTIONS /marvin/quick-filters` → 400
`Invalid Preflight Request`.

Infra: gateway `apigateway.nike.com.br/` → `{"nomeAplicacao":"Scooby.WebApi"}` (IIS/.NET);
`/nike-bff/` e `/nike-bff/health` → `{"status":"I'm fine"}` (Express); app em `istio-envoy`.

## Próximo passo recomendado

1. **Usar `topsuggestions` com `limit` alto** como fonte primária de "termo livre → produtos". Custo 1 req/termo,
   JSON limpo, com preço. Já resolve o caso de uso.
2. Se for necessária a **PLP canônica** (ordenação, facetas, estoque por tamanho): a rota server-side do gSSP
   não está nos bundles do cliente — ela só aparece no tráfego do servidor Next. Alternativa barata: capturar
   **1 HAR de uma navegação humana real** em `/busca?term=...` e ler a chamada que o servidor Next faz ao BFF
   (procure por `/products` ou `/marvin/`), depois replicar via `apigateway` com os cookies `bm_*`/`_abck`
   daquela sessão.
3. Não vale insistir em `/busca` ou `/_next/data/.../busca.json` por HTTP: exige executar o sensor JS do Akamai
   Bot Manager (fora do escopo "sem navegador"). Também evitar `/nike-bff/products`, bloqueado por path.

> Proxy SOCKS5 usado apenas em teste; não versionar credenciais.
