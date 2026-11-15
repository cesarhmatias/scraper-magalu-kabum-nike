# Thread — Magalu, KaBuM e Nike, na ordem (com ScrapeLens e DeepSeek)

1/18
Fiz um scraper de catálogo para Magalu, KaBuM e Nike que roda na CLI e devolve XLSX — sem navegador headless.

Vou contar na ordem em que resolvi: Magalu, depois KaBuM e, por último, Nike (o mais difícil).

Thread:

---

2/18
Tudo começou com o ScrapeLens: ele abre um Chrome dedicado (perfil temporário, sem headless) e captura CDP + NetLog — requests, responses, corpos, cookies e headers na ordem original.

É a resposta para: "o navegador consegue; o que meu scraper faz diferente?"

---

3/18
Com as capturas em mão, usei o DeepSeek para analisar as requests de pesquisa e paginação dos 3 domínios: qual chamada trazia o catálogo, quais params paginavam e o que era só telemetria. A análise inteira custou US$ 0,21.

---

4/18
MAGALU (1/3)
O HTML de /busca/ fica atrás do Akamai Bot Manager: GET simples recebe challenge, não a listagem.

A captura mostrou que o catálogo não vinha no HTML, e sim numa chamada XHR do Next.js.

---

5/18
MAGALU (2/3)
Endpoint: /_next/data/<buildId>/busca/<termo>.json

O buildId atual sai da home mobile m.magazineluiza.com.br, que escapa do challenge. A paginação é ?page=N.

Sem JS, sem renderizar a página.

---

6/18
MAGALU (3/3)
Resultado: 705 anúncios únicos em 25 páginas, com preço, Pix, parcelamento, vendedor e avaliação.

Nesse alvo o curl_cffi ainda negociou HTTP/3 de verdade pelo relay UDP. Lição: o JSON é a porta dos fundos do HTML protegido.

---

7/18
KABUM (1/3)
O /busca/... é só um shell Next.js. Quando o SSR vem completo, dá para ler o __NEXT_DATA__; quando não, a listagem é carregada por XHR.

A captura entregou a API que o site usa.

---

8/18
KABUM (2/3)
GET servicespub.../catalog/v2/products?query=<termo>&page_number=N&page_size=60

Headers origin e referer do site, resposta JSON com attributes: title, price, price_with_discount, seller, images. Paginação de 60 em 60.

---

9/18
KABUM (3/3)
Resultado: "processador" deu 618 itens; 120 em 2 páginas no teste.

Cuidado: a busca é match literal. "tênis de corrida" retornou 0 — e zero é aviso, não erro do scraper.

---

10/18
NIKE (1/4) — o mais difícil
/busca é __N_SSP e o Akamai bloqueia o documento. GET em /busca?term=... devolve 403 "Access Denied" com ~540 bytes.

Nem curl_cffi com headers de Chrome passou. O problema não era TLS/fingerprint.

---

11/18
NIKE (2/4)
Pista da captura: o gSSP do /busca exige o param term, e o Akamai aplica regra no literal "term=".

/_next/data/<build>/busca.json?q=tenis devolve 404 notFound; ?term=tenis devolve 403. O caminho do HTML estava fechado.

---

12/18
NIKE (3/4)
Fui ao bundle JS: o _app expõe publicApi.bff = apigateway.nike.com.br/nike-bff. As únicas rotas de busca do cliente são /v2/search/topsuggestions e /v2/search/topterms.

Aí estava o caminho sem browser.

---

13/18
NIKE (4/4)
GET /nike-bff/v2/search/topsuggestions?term=<termo>&limit=<N>

JSON com id, nome, categoria, URL, preço, listPrice, desconto e Pix. page é ignorado; limite máximo de 500 itens. Sem sensor JS do Akamai.

---

14/18
O que os três exigiram em comum: ORDEM dos headers.

Anti-bots comparam sequência, não só valores. Copiei a ordem exata do Chrome nas capturas e forcei no curl_cffi com default_headers=False + Headers ordenado. Tem teste local conferindo a ordem no fio.

---

15/18
Proxy UDP: gate.decodo.com:10000 recusa UDP ASSOCIATE (reply=0x02). O gateway que aceita é socks5-gate.decodo.com:10000.

Com curl_cffi http_version="v3", o QUIC sai pelo relay UDP; quando o CDN não negocia h3, cai para h2 — e o protocolo real vai na planilha.

---

16/18
Pipeline final: curl_cffi → parser por domínio → dataclass Anuncio → openpyxl.

A planilha tem 23 colunas (preço, preço original, desconto, Pix, parcelamento, vendedor, categoria, avaliação, URL, imagem, transporte, fonte) e uma aba de resumo com erros.

---

17/18
Resultado: "tênis" nos 3 sites, 1.212 anúncios; "tênis de corrida" Magalu+Nike, 220 (Magalu em h3); "processador" KaBuM, 120.

Tudo por CLI e proxy SOCKS5, sem abrir Chrome na coleta.

---

18/18
Resumo do processo: Magalu = JSON do Next.js por buildId; KaBuM = API de catálogo com query/page_number; Nike = BFF topsuggestions com term/limit.

Capture com navegador real (ScrapeLens), analise com DeepSeek, colete com HTTP puro — e respeite a ordem dos headers.
