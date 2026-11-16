# Akamai no Magazine Luiza — o que é o challenge e o que dá para fazer

Registro: 2026-11-14. Alvo: `https://www.magazineluiza.com.br/busca/<termo>/`.
Objetivo: descobrir o tipo de challenge do Akamai Bot Manager e avaliar se ele é
solucionável em Python puro, sem navegador.

## Resumo

O challenge **não é proof-of-work nem um captcha aritmético**. É o `sec-if-cpt` do
Akamai Bot Manager: uma página de ~2,5 KB com dois scripts ofuscados que executam
**SBSD** (`/.well-known/sbsd`) + **sensor_data** (telemetria v3) e, só depois,
liberam a navegação. Não existe nonce/dificuldade para calcular em Python; o corpo
enviado é cifrado/gerado por 1,1 MB de JavaScript por emissão.

O caminho 100% Python que funciona é o endpoint JSON `_next/data` já usado pelo
provedor Magalu. Para o HTML, o caminho viável é bootstrap de sessão em Chrome real
(Patchright headed) **no mesmo IP de saída** e, então, reutilizar os cookies no
`curl_cffi` — com a ressalva de que o Akamai aceita poucas requisições por bootstrap.

## Evidências coletadas

### Página de challenge (`sec-if-cpt`)

- HTTP 200, ~2.503 bytes, `server: AkamaiGHost`, sem o catálogo.
- Dois scripts:
  - `.../N4N94mG5GOE7/F2YmSikD/aFJsAlI/jDFQIAQ?v=<uuid>&t=<token>` (~475 KB);
  - `.../u7N94mXwGO4QXSzO1O/GiAcSikD/YwgMOl1/0ZAg` (~632 KB).
- Script 1 contém a referência `/.well-known/sbsd`; script 2 contém o
  `XMLHttpRequest` do sensor.
- Um wrapper inline observa o XHR cuja URL contém `t=<token>` e chama
  `location.reload(true)` quando ele termina.

### O que o Chrome real faz (Patchright headed, sem interação)

1. `POST <script-do-sensor>` com `{"sensor_data":"3;0;1;0;...;<payload cifrado>"}` →
   **201**.
2. `POST <script-SBSD>?t=<token>` com `{"body":"<payload cifrado>"}` → **200**.
3. A página recarrega e entrega o catálogo real: **~2,0 MB**, sem `sec-if-cpt`.

O `sensor_data` tem o prefixo v3 (`3;0;1;0;<hash>;...`) descrito no laboratório
(`docs/cases/sensor_data.md`) e o `body` é o fluxo SBSD em modo bloqueante
(`docs/cases/sbsd_challenge.md`).

## Tentativas em Python puro

| Tentativa | Resultado |
|---|---|
| `POST` de `sensor_data` falso no endpoint do sensor | **201** `{"success": true}`, mas a página continua no challenge |
| `POST` de `{"body":"x"}` no endpoint SBSD `?t=` | **200** vazio, sem cookie novo, página continua no challenge |
| Recarregar a página com os cookies do challenge | 200 com ~2,5 KB, ainda `sec-if-cpt` |
| Replay de cookies de um Chrome real, **mesmo IP direto** | 200 com ~2,15 MB, catálogo completo |
| Replay dos mesmos cookies por outro exit do proxy | 200 com ~2,5 KB, challenge |
| Chrome via proxy sticky + `curl_cffi` no mesmo exit | 200 com ~2,0 MB, sem challenge (1ª requisição) |
| Segunda requisição no mesmo replay | volta ao challenge (~2,5 KB) |

Conclusões parciais:

- O Akamai **vincula `_abck`/sessão ao IP, UA/JA4 e ao histórico de navegação**.
  Trocar o exit do proxy invalida o cookie; o laboratório modela isso em
  `docs/cases/abck_cookie.md`.
- O servidor aceita o POST do sensor com corpo trivial (201), mas isso **não** é
  suficiente para liberar a página: a decisão depende do SBSD/validação server-side.
- O cookie replay funciona por uma janela curta; uma sequência de navegações sem o
  JS do sensor volta a ser desafiada.

## O experimento do solver sem navegador (2026-11-14)

Construímos um solver completo em `out/solver/` (Node + jsdom, gitignored) que executa
os dois scripts do challenge **sem navegador** e com **rede real** pelo mesmo proxy sticky
da sessão:

- `scripts/magalu_solver_session.py` captura a página `sec-if-cpt` num exit novo e salva
  HTML, URLs dos scripts, cookies e o proxy usado.
- `out/solver/solve.js` baixa os dois scripts, executa em jsdom com shims de browser e
  encaminha **cada XHR/fetch/beacon que o script dispara para o servidor de verdade**,
  com cookie jar atualizado por `Set-Cookie` e o header set/ordem do Chrome por tipo de
  requisição (navegação, script, XHR).
- `scripts/magalu_solver_verificar.py` refaz a navegação com `curl_cffi` (TLS Chrome).

### O que o solver já conquistou

| Sinal | Resultado |
|---|---|
| Os dois scripts (1,1 MB ofuscados) avaliam sem erro em jsdom | sim, após shims |
| `POST` do sensor gerado pelo próprio script | **201 `{"success":true}`** (várias vezes) |
| `POST` do SBSD `?t=<token>` com body gerado pelo script | **200** |
| Cookie `bm_lso` (sucesso do SBSD, cf. `docs/cases/sbsd_challenge.md`) | **emitido** |
| Reload da página limpo | **não** — 403 (bloqueio duro) |

Shims adicionados por iteração, na ordem: `crypto.subtle`, `matchMedia`, `getBattery`,
`connection`, `getGamepads`, observers, `performance.now` fracionário (timing
monotônico), eventos de mouse/teclado sintéticos, `navigator.platform/hardwareConcurrency/
deviceMemory/languages/vendor`, `plugins` com 5 entradas PDF, `mimeTypes`,
`AudioContext`/`OfflineAudioContext` completos, `speechSynthesis`.

### O que ainda reprova

O `201` do sensor é só reconhecimento de recebimento. A **decisão** do Akamai usa o
conteúdo decodificado do sensor (bot score), e algo na telemetria do jsdom ainda parece
robótico — candidatos: hash de canvas (rasterizador do `@napi-rs/canvas` ≠ Chrome),
strings de WebGL, enumeração de fontes, distribuição de timing, e probes rotativos que
mudam a cada emissão. Após 5 iterações de shims o resultado se manteve: challenge
aceito, navegação bloqueada (403 duro). Fizemos a diferença entre **resolver o
challenge** (feito: o servidor aceita os POSTs e emite `bm_lso`) e **passar o bot
score** (não feito).

## Por que não dá para “resolver em Python puro”

O laboratório classifica os módulos relevantes assim:

| Módulo | `curl_cffi` | Chrome/Patchright |
|---|---|---|
| `tls_fingerprint`, `h2_fingerprint`, `header_order` | passa | passa |
| `abck_cookie` | falha (sem JS) | passa |
| `sensor_data` | falha (sem JS) | passa |
| `js_integrity` | falha | passa |
| `sbsd_challenge` | falha (op chain gerada por JS) | passa |

O próprio `docs/cases/sbsd_challenge.md` diz: “A pure-HTTP client must reimplement
the generated script, whose shape changes per issuance” e “A determined client can
port the generated JavaScript to Python or run a minimal JS engine”.

Para portar seria necessário reimplementar:

1. o op-chain do SBSD (operações de 32 bits sobre título, UA e DOM, geradas por
   emissão);
2. a coleta e a cifra do `sensor_data` (chave derivada de `bm_sz` + build do script);
3. a ordem/timing dos POSTs e o reload.

Não há um valor fixo (nonce + dificuldade) que um `hashlib` resolva. O experimento
com Node + jsdom chegou a **avaliar** os dois scripts e gerar um `sensor_data` de
~1,9 KB, mas o SBSD depende de APIs de browser (canvas, `currentScript`, telemetria)
e não produziu o `body` válido; é uma linha de pesquisa, não um solver confiável.

## Alternativas, em ordem de custo/benefício

### A. Usar o JSON `_next/data` (recomendado para listagens)

O HTML é desafiado, mas o endpoint de dados do Next.js responde o catálogo completo:

```
GET /_next/data/<buildId>/busca/<slug>.json?page=N
```

- Sem navegador, sem challenge, paginação estável (25 páginas no teste).
- É o que o provedor `Magalu` já faz; entrega título, preço, Pix, parcelamento,
  vendedor, avaliação, filtros e ordenações.
- O `buildId` é descoberto em `m.magazineluiza.com.br` e cacheado.

### B. Híbrido: Chrome só para o bootstrap, HTTP para o volume

1. Abrir Patchright/Chrome **headed**, via proxy HTTP sticky, em
   `gate.decodo.com:10000` com usuário `...-session-<id>`.
2. Navegar até a URL desejada e esperar o challenge sumir.
3. Exportar `storage_state` / cookies (`_abck`, `bm_sz`, `bm_s`, `bm_so`, `bm_sc`).
4. Fazer **uma** requisição `curl_cffi` no mesmo proxy sticky com os cookies e a
   ordem de headers capturada.

Foi validado: 200, ~2,0 MB, sem challenge. Para a página seguinte, repetir o
bootstrap (a sessão HTTP pura é desafiada depois da primeira navegação). É o
caminho se o HTML for obrigatório.

### C. Chrome dirigido (Patchright) para o HTML

Navegar e ler `page.content()`/`__NEXT_DATA__` direto. Mais lento, porém é o único
caminho que passa por `_abck`, `sensor_data`, `js_integrity` e SBSD de forma
consistente. O laboratório chama isso de “Patchright bypass attempt”: passa em 18
de 21 casos; os três restantes são `native_app` e os dois interstitials.

### D. Motor JS (Node + jsdom) + POST — validado até o bot score

O caminho D deixou de ser teoria: o solver de `out/solver/` executa os scripts, gera
payloads aceitos e ganha `bm_lso`. O que falta é o conteúdo do sensor ser
indistinguível do Chrome — engineering iterativo contra um alvo opaco, com custo de
manutenção alto porque o script muda a cada emissão.

Executar os scripts do challenge num DOM simulado, capturar os corpos e postar com
`requests`. Viável em teoria; na prática exige shims de canvas, `navigator`,
`chrome`, `userAgentData`, `currentScript`, timers e telemetria. O protótipo gerou
`sensor_data`, mas não o SBSD válido. Alto custo de manutenção porque o script muda
a cada emissão.

### E. Unblocker comercial

Bright Data Web Unlocker, Zyte, ScraperAPI etc. resolvem o challenge do lado deles.
Custo por requisição e dependência externa; útil se o volume justificar.

## Recomendação

- Para **anúncios/listagens**, ficar com o `_next/data`: é mais rápido, estável e
  não depende de browser. O “bypass” do Akamai já existe nesse caminho.
- Para **HTML/PLP canônica**, implementar o modo híbrido (B) com proxy sticky e
  re-bootstrap por página, ou usar (C) se a fidelidade de JS for necessária.
- Não investir em reimplementar o SBSD em Python puro: o custo é alto, o payload é
  por emissão e o laboratório só o classifica como LOW/vendor-sourced.
- Respeitar limites de taxa, termos de uso e legislação aplicável; a coleta é de
  catálogo público, mas o bypass continua sendo uma decisão operacional do site.

## Referências

- Lab local: `vendor/akamai-style-bot-lab/`
  - `docs/cases/sbsd_challenge.md`
  - `docs/cases/sensor_data.md`
  - `docs/cases/abck_cookie.md`
  - `docs/cases/js_integrity.md`
  - `docs/cases/header_order.md`
- Notas do projeto: `01_Projects/Google SERP UDP/02`, `06` e `17` (proxy, UDP e
  sessão quente).
