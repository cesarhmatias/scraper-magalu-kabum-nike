# anuncios — busca por termo → planilha de anúncios por domínio

CLI em Python que recebe **um termo** e **um ou mais domínios** (Magazine Luiza, KaBuM!,
Nike Brasil, Casas Bahia), coleta **todas as listagens/anúncios** daquela busca interna e devolve
uma **planilha XLSX** pronta para análise. Nenhum navegador headless: só HTTP com fingerprint
de Chrome (`curl_cffi`) por um **proxy SOCKS5 com relay UDP** (gateway que aceita
`UDP ASSOCIATE`, necessário para QUIC/HTTP/3).

```bash
.venv/bin/anuncios buscar --termo "tênis de corrida" \
  --dominio magalu --dominio nike --dominio casasbahia --paginas 2 \
  --saida out/tenis-de-corrida.xlsx
```

```text
Termo: 'tênis de corrida' | domínios: magazineluiza.com.br, nike.com.br, casasbahia.com.br | páginas: 2
Proxy: socks5h://socks5-gate.decodo.com:10000 | transporte: auto

DOMINIO                       ANUNCIOS  PAGINAS  TRANSP    TEMPO  OBS
---------------------------------------------------------------------
magazineluiza.com.br               100        2      h3   39715ms  buildId=7r3tcIYiLcgcsZ0noAtuQ
nike.com.br                        120        2      h2    2449ms  limite=120 (API sem paginação)
casasbahia.com.br                   40        2      h2    5900ms  api=v3 parceiro=elastic chave=casasbahia; precos=40/40
  
260 anúncios -> out/tenis-de-corrida.xlsx
```

## Instalação

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env      # preencha ANUNCIOS_PROXY
.venv/bin/anuncios dominios
```

O `.env` fica fora do git. O proxy padrão esperado é SOCKS5 autenticado
(`socks5h://usuario:senha@host:porta`). O CLI também aceita `--proxy`.

## Comandos

| Comando | Para que serve |
|---|---|
| `anuncios buscar --termo ... --dominio ...` | coleta e grava a planilha |
| `anuncios dominios` | lista domínios/aliases suportados |
| `anuncios doctor` | testa proxy, protocolo negociado e acesso a cada fonte |

Opções de `buscar`:

| Opção | Padrão | Descrição |
|---|---|---|
| `--termo` | — | termo livre da busca |
| `--dominio` | todos | `magalu`, `kabum`, `nike`, `casasbahia`, host completo ou alias; repita para vários |
| `--paginas` | `0` | `0` = todas (limite de 50 páginas); N domínio → `60 × N` na Nike e `20 × N` na Casas Bahia |
| `--saida` | `out/anuncios-<termo>-<data>.xlsx` | caminho da planilha |
| `--proxy` | `ANUNCIOS_PROXY` | SOCKS5 com UDP |
| `--transporte` | `auto` | `auto` (tenta h3 e cai para h2), `h3` (exige h3) ou `h2` |
| `--exigir-udp` | desligado | falha se o h3 não for realmente negociado |
| `--timeout` / `--tentativas` | `35` / `3` | rede e retry |

Códigos de saída: `0` coleta completa, `1` parcial (algum domínio falhou, planilha ainda é
gravada), `2` nenhum anúncio.

## O que vai na planilha

Aba **Anúncios** (uma linha por anúncio, com filtro e cabeçalho congelado):

`Domínio, Termo, Página, Posição, ID, Título, Marca, Preço, Preço original, Desconto %,
Parcelamento, Vendedor, Categoria, Preço Pix, Disponível, Avaliação, Avaliações,
Patrocinado, URL, Imagem, Transporte, Coletado em, Fonte`.

Aba **Resumo**: totais, domínios com resultado/falha, transporte, build/ID, duração,
erros e avisos de cada domínio. Preços em `R$`, datas em UTC (o Excel não aceita
`tzinfo`).

## Como cada domínio é coletado (sem browser)

| Domínio | Fonte usada | Paginação | Protocolo observado |
|---|---|---|---|
| **Magazine Luiza** | JSON do Next.js: `/_next/data/<buildId>/busca/<slug>.json` | `?page=N` | **h3** via relay UDP, com fallback h2 |
| **KaBuM!** | API de catálogo: `servicespub.../catalog/v2/products?query=<termo>&page_number=N` | `page_number` (60/página) | h2 |
| **Nike Brasil** | API do BFF: `apigateway.nike.com.br/nike-bff/v2/search/topsuggestions?term=<termo>&limit=<N>` | `limit` (máx. 500; `page` é ignorado) | h2 |
| **Casas Bahia** | API de busca v3: `api-partner-prd.casasbahia.com.br/api/v3/web/busca?terms=<termo>&page=N` + API de preços em lote | `page` (20/página) | h2 |

- **Magalu:** o HTML de `/busca/...` está atrás do Akamai Bot Manager. O endpoint
  `_next/data` responde o JSON completo da busca sem executar JavaScript. O `buildId`
  atual é descoberto em `m.magazineluiza.com.br` (site mobile, que não aplica o mesmo
  challenge) e fica em cache em `out/.cache/magalu-buildid`; se o build mudar, o cache é
  renovado automaticamente. É essa rota que negocia **HTTP/3** de verdade pelo proxy.
- **KaBuM!:** o HTML de `/busca` é só o shell do Next.js; a listagem completa e paginada
  vem da API JSON que o próprio site consome. A API faz **match literal**: termos
  compostos que não existem no catálogo retornam `CATALOG_NOT_MATCH` (o provedor trata
  como “sem resultados”, não como falha).
- **Nike:** `/busca` é `__N_SSP` e o Akamai bloqueia a rota de documento com regra no
  literal `term=` (403 `Access Denied`). A rota pública usada pelo próprio cliente para
  autocomplete/resultados é a `topsuggestions`, que devolve produtos com preço, Pix,
  desconto e URL. Ela não substitui a PLP canônica (ordenação/facetas da página), mas é
  o caminho estável sem browser. Detalhes e evidências em
  [`docs/nike-endpoints.md`](docs/nike-endpoints.md).
- **Casas Bahia:** o HTML de `/<termo>/b` é SSR e fica atrás do Akamai Bot Manager
  (403, ou o desafio `sec-if-cpt` de 6,7 KB mesmo com os cookies `bm_*` da captura). O
  `__NEXT_DATA__` da página publica a `SEARCH_API_V3` usada pelo servidor Next; chamada
  direta, ela devolve o mesmo JSON da busca, sem sensor JavaScript. O preço não vem nesse
  JSON: o site pede em lote para `api.casasbahia.com.br` (`POST PrecoVenda`), com os
  headers `xaplication`/`apikey`. O provedor faz 1 busca por página (20 itens) + 1 POST
  de preço a cada 50 produtos. Detalhes e evidências em
  [`docs/casasbahia-endpoints.md`](docs/casasbahia-endpoints.md).

## Ordem dos headers (requisito explícito)

Os anti-bots comparam a **ordem** dos headers, não só os valores. Por isso:

1. As ordens foram extraídas das capturas do Chrome 157 em
   `/Users/cesar/Downloads/capture-{magalu,kabum,nike,casas-bahia}-full/session.json`
   (campo `requestHeaders`, `orderState: sourceOrder`). Estão em
   [`src/anuncios/config.py`](src/anuncios/config.py):
   `headers_navegacao`, `headers_next_data`, `headers_api_json` e `headers_preco_json`.
2. A sessão `curl_cffi` usa `default_headers=False` e `curl_cffi.requests.Headers`
   (lista ordenada). Sem isso o fingerprint do Chrome injeta os headers padrão antes dos
   nossos e a ordem capturada se perde.
3. [`tests/test_headers.py`](tests/test_headers.py) sobe um servidor local e compara a
   ordem que chega no fio com a lista esperada.
4. `priority` é consumido pela camada HTTP/2 do libcurl (não sai como header comum);
   `host`, `connection` e `upgrade` são gerados pelo cliente. O teste cobre a sequência
   útil de fingerprint.

O mesmo conjunto de headers é usado nos quatro domínios, com as variantes de documento
(`Sec-Fetch-Dest: document`), XHR JSON (`cors/empty`), `_next/data` (`x-nextjs-data: 1`) e
o POST de preço da Casas Bahia (`xaplication` + `apikey` + `content-type`).

## Proxy UDP, QUIC e HTTP/3

- `UDP ASSOCIATE` foi confirmado no gateway **`socks5-gate.decodo.com:10000`**. O
  `gate.decodo.com:10000` recusa o comando (`reply=0x02`), então o CLI normaliza
  automaticamente o host quando detecta Decodo — mantendo usuário/senha e porta.
- Com `curl_cffi` (`http_version="v3"`) o QUIC sai pelo relay UDP do SOCKS5. O protocolo
  **real** negociado aparece no log (`protocolo`), na aba Resumo e na coluna
  `Transporte` de cada linha: `h3` quando o alvo negocia QUIC, `h2` quando não.
- O relay UDP do provedor pode encerrar conexões QUIC grandes por idle/timeout. A camada
  tenta h3 mais uma vez e, se falhar, cai para h2 **explicitamente** (nunca silencioso).
  Use `--exigir-udp` quando a coleta precisar falhar em vez de degradar.
- As lições de transportes vêm do projeto de notas
  [`Google SERP UDP`](/Users/cesar/Notas/01_Projects/Google%20SERP%20UDP/00%20-%20%C3%8Dndice%20do%20projeto.md):
  SOCKS5 ≠ UDP, `UDP ASSOCIATE` tem relay próprio, e MASQUE não é necessário aqui
  (notas 02 e 06). O runtime anterior em `/Users/cesar/Projects/serp google` foi a
  referência de proxy/retry, mas o parser de SERP do Google não é reutilizado.

## Entregas de exemplo

| Arquivo | Conteúdo | Transporte |
|---|---|---|
| `out/anuncios-tenis-todos.xlsx` | anúncios de `tênis` em todas as páginas disponíveis (Magalu + KaBuM + Nike) | h2 pelo gateway UDP; até 50 páginas por domínio |
| `out/anuncios-tenis-de-corrida-magalu-nike.xlsx` | 220 anúncios de `tênis de corrida` (Magalu 100 + Nike 120) | **h3** na Magalu, h2 na Nike |
| `out/anuncios-processador-kabum.xlsx` | 120 processadores (2 páginas de 618) | h2 |
| `out/anuncios-tenis-3-dominios.xlsx` | 117 anúncios de `tênis` (1 página por domínio) | h2 |
| `out/anuncios-iphone-casasbahia.xlsx` | 20 iPhones da Casas Bahia (1 página de 74) com preço, Pix e parcelamento | h2 |
| `out/anuncios-iphone-4-dominios.xlsx` | 134 anúncios de `iphone` (Magalu 52, KaBuM 60, Nike 2, Casas Bahia 20) | h2 |

O `todos` usa `--transporte h2` para evitar a instabilidade do relay QUIC em volume;
o arquivo `tênis de corrida` foi coletado em `auto` e registra `h3` nas linhas da Magalu.

## Limitações conhecidas

- **Nike:** `topsuggestions` devolve no máximo 500 itens e não tem a ordenação/facetas da
  PLP. Para a PLP canônica seria necessário um HAR de navegação humana e os cookies
  `bm_*`/`_abck`; não é o escopo deste CLI.
- **KaBuM!:** busca literal. “tênis de corrida” retorna zero (o catálogo não tem a frase);
  “processador” retorna 618 itens. O zero é registrado como aviso, não como erro.
- **Magalu:** o `buildId` muda a cada deploy; o cache é validado pela resposta (`404`
  dispara redescoberta). O endpoint de dados pode receber challenge do Akamai em
  momentos de instabilidade; nesse caso o domínio falha e os demais continuam.
- **Casas Bahia:** a busca v3 devolve no máximo 21 itens por página (o site usa 20), então
  50 páginas = 1.000 produtos; a API declara `maxSize: 10000`. O preço vem de um segundo
  POST em lote: se ele falhar, os anúncios saem com preço vazio e um aviso no Resumo, sem
  derrubar o domínio. O nome do lojista não vem na API de preço — `IdLojista 33013` é
  rotulado “Casas Bahia” e os demais como `Lojista <id>`.
- Preço, estoque e disponibilidade são **fotografias** do momento da coleta; a planilha
  registra `Coletado em` em UTC.
- A coleta respeita limites de taxa (pausa entre domínios, backoff e retry), mas o uso
  continua sujeito aos termos de cada site e à legislação aplicável.

## Testes

```bash
.venv/bin/pytest -q
.venv/bin/anuncios doctor
```

`pytest` cobre: ordem dos headers no fio (inclusive o POST de preço), normalização do
gateway Decodo, parsers dos quatro domínios e geração/leitura da planilha. Não há teste de rede na suíte; a rede é
validada pelo `doctor` e pelos smoke tests registrados em `out/`.

## Estrutura

```text
src/anuncios/
├── cli.py            # buscar | dominios | doctor
├── coletor.py        # orquestra domínios, isola falhas
├── config.py         # .env, proxy, perfis de header ordenados
├── http.py           # curl_cffi, retry, h3→h2, detecção de bloqueio
├── models.py         # Anuncio / ResultadoDominio
├── export.py         # XLSX (Anúncios + Resumo)
├── utilitarios.py    # slug, preço, parcela
└── providers/        # magalu.py, kabum.py, nike.py, casasbahia.py, base.py
tests/                # headers, proxy, parsers, export
docs/nike-endpoints.md
docs/casasbahia-endpoints.md
```

## Segurança

- Credenciais só em `.env` (ignorado pelo git) ou em `--proxy`; logs e planilha mostram
  apenas `socks5h://host:porta` e um `proxy_id` com hash.
- Nenhum cookie, token ou corpo de resposta autenticado é gravado no repositório.
