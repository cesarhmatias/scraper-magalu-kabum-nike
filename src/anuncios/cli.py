"""CLI: `anuncios buscar --termo ... --dominio ...`."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .coletor import coletar
from .config import RAIZ, config_do_ambiente, headers_next_data
from .export import gerar_planilha
from .http import ErroColeta, Http
from .log import evento
from .providers import TODOS, resolver
from .utilitarios import slug


def _saida_padrao(termo: str) -> Path:
    carimbo = time.strftime("%Y%m%d-%H%M")
    return RAIZ / "out" / f"anuncios-{slug(termo) or 'busca'}-{carimbo}.xlsx"


def _tabela(coleta) -> str:
    linhas = []
    cabecalho = f"{'DOMINIO':28} {'ANUNCIOS':>9} {'PAGINAS':>8} {'TRANSP':>7} {'TEMPO':>8}  OBS"
    linhas.append(cabecalho)
    linhas.append("-" * len(cabecalho))
    for resultado in [*coleta.resultados, *coleta.falhas]:
        obs = "; ".join(resultado.erros or resultado.avisos)
        if len(obs) > 60:
            obs = obs[:57] + "..."
        linhas.append(
            f"{resultado.dominio:28} {len(resultado.anuncios):>9} {resultado.paginas:>8} "
            f"{resultado.transporte:>7} {resultado.duracao_ms:>7}ms  {obs}"
        )
    return "\n".join(linhas)


def cmd_buscar(args) -> int:
    cfg = config_do_ambiente(
        proxy=args.proxy,
        transporte=args.transporte,
        exigir_udp=args.exigir_udp,
        timeout=args.timeout,
        tentativas=args.tentativas,
    )
    dominios = args.dominio or [p.dominio for p in TODOS]
    # aliases/validacao antes de tocar a rede
    validados: list[str] = []
    for d in dominios:
        try:
            alvo = resolver(d).dominio
        except KeyError as exc:
            print(f"erro: {exc}", file=sys.stderr)
            return 2
        if alvo not in validados:
            validados.append(alvo)

    print(f"Termo: {args.termo!r} | domínios: {', '.join(validados)} | páginas: {args.paginas}")
    print(f"Proxy: {cfg.proxy_descricao} | transporte: {cfg.transporte}")
    coleta = coletar(args.termo, validados, args.paginas, cfg)
    print()
    print(_tabela(coleta))
    print()

    if not coleta.anuncios:
        print("Nenhum anúncio coletado.", file=sys.stderr)
        return 2

    saida = Path(args.saida).expanduser() if args.saida else _saida_padrao(args.termo)
    caminho = gerar_planilha(coleta, saida, cfg)
    total = len(coleta.anuncios)
    print(f"{total} anúncios -> {caminho}")
    if coleta.parcial:
        print("Coleta parcial: houve falha em ao menos um domínio (veja o Resumo da planilha).", file=sys.stderr)
        return 1
    return 0


def cmd_dominios(args) -> int:
    print(f"{'NOME':10} {'DOMINIO':28} {'ALIASES':40} DESCRICAO")
    for p in TODOS:
        print(f"{p.nome:10} {p.dominio:28} {', '.join(p.aliases)[:40]:40} {p.descricao}")
    return 0


def cmd_doctor(args) -> int:
    cfg = config_do_ambiente(proxy=args.proxy, transporte=args.transporte, exigir_udp=args.exigir_udp)
    print(json.dumps({
        "proxy": cfg.proxy_descricao,
        "proxy_id": cfg.proxy_id,
        "transporte_pedido": cfg.transporte,
        "exigir_udp": cfg.exigir_udp,
    }, ensure_ascii=False, indent=2))

    # Magalu: buildId + primeiro JSON
    try:
        from .providers.magalu import Magalu
        m = Magalu(cfg)
        try:
            bid = m._descobrir_build_id(forcar=True)
            resp = m.http.get(
                f"{m.BASE}/_next/data/{bid}/busca/tenis-de-corrida.json",
                headers_next_data(referer=f"{m.BASE}/busca/tenis-de-corrida/"),
                esperado="json",
                rotulo="doctor-magalu",
            )
            dados = resp.json()
            itens = (dados.get("pageProps", {}).get("data", {}).get("search", {}) or {}).get("items") or []
            print(f"magalu   ok  buildId={bid} status={resp.status} protocolo={resp.http_version} itens={len(itens)}")
        finally:
            m.fechar()
    except Exception as exc:
        print(f"magalu   falhou: {type(exc).__name__}: {exc}")

    # Kabum: API
    try:
        from .providers.kabum import API, SITE, Kabum
        from .config import headers_api_json
        k = Kabum(cfg)
        try:
            header = headers_api_json(origem=SITE, referer=f"{SITE}/busca/processador")
            resp = k.http.get(
                f"{API}?query=processador&page_number=1&page_size=5&sort=most_searched",
                header, esperado="json", rotulo="doctor-kabum",
            )
            dados = resp.json()
            print(
                f"kabum    ok  status={resp.status} protocolo={resp.http_version} "
                f"itens={len(dados.get('data') or [])} total={dados.get('meta', {}).get('total_items_count')}"
            )
        finally:
            k.fechar()
    except Exception as exc:
        print(f"kabum    falhou: {type(exc).__name__}: {exc}")

    # Nike: API do BFF usada pelo provedor (o documento /busca e bloqueado pelo Akamai)
    try:
        from .config import headers_api_json
        from .providers.nike import API as NIKE_API, SITE as NIKE_SITE
        h = Http(cfg, "nike.com.br")
        try:
            resp = h.get(
                f"{NIKE_API}?term=tenis&limit=5",
                headers_api_json(origem=NIKE_SITE, referer=f"{NIKE_SITE}/busca?term=tenis"),
                esperado="json", rotulo="doctor-nike",
            )
            dados = resp.json()
            print(
                f"nike     ok  status={resp.status} protocolo={resp.http_version} "
                f"produtos={len(dados.get('products') or [])} (/busca segue bloqueado pelo Akamai)"
            )
        finally:
            h.fechar()
    except ErroColeta as exc:
        print(f"nike     falhou: {exc}")

    # Casas Bahia: API de busca v3 + API de precos (o HTML /<termo>/b e barrado pelo Akamai)
    try:
        from .config import headers_api_json
        from .providers.casasbahia import SITE as CB_SITE, CasasBahia, url_busca
        cb = CasasBahia(cfg)
        try:
            resp = cb.http.get(
                url_busca("iphone", 1),
                headers_api_json(origem=CB_SITE, referer=f"{CB_SITE}/iphone/b"),
                esperado="json", rotulo="doctor-casasbahia",
            )
            dados = resp.json()
            produtos = dados.get("products") or []
            print(
                f"casasbahia ok status={resp.status} protocolo={resp.http_version} "
                f"produtos={len(produtos)} total={dados.get('size')}"
            )
            if produtos:
                ofertas, falhas = cb._buscar_precos([int(produtos[0]["id"])])
                print(f"           preco={'ok' if ofertas else 'vazio'} ofertas={len(ofertas)} falhas={falhas}")
        finally:
            cb.fechar()
    except ErroColeta as exc:
        print(f"casasbahia falhou: {exc}")

    return 0


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="anuncios", description="Coleta de anúncios/listagens por termo e domínio.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def comuns(p):
        p.add_argument("--proxy", default=None, help="SOCKS5 com UDP (default: ANUNCIOS_PROXY)")
        p.add_argument("--transporte", choices=["auto", "h3", "h2"], default=None,
                       help="auto (h3 com fallback), h3 (exige QUIC) ou h2")
        p.add_argument("--exigir-udp", action="store_true", help="falha se o HTTP/3 não for negociado")

    b = sub.add_parser("buscar", help="busca o termo e gera a planilha")
    b.add_argument("--termo", required=True, help="termo de busca")
    b.add_argument("--dominio", action="append", default=None,
                   help="domínio/alias (magalu, kabum, nike, casasbahia); repita para vários")
    b.add_argument("--paginas", type=int, default=0,
                   help="páginas por domínio; 0 = todas (limite de 50; itens/página varia por domínio)")
    b.add_argument("--saida", default=None, help="caminho do .xlsx")
    b.add_argument("--timeout", type=float, default=None)
    b.add_argument("--tentativas", type=int, default=None)
    comuns(b)
    b.set_defaults(func=cmd_buscar)

    d = sub.add_parser("dominios", help="lista domínios suportados")
    d.set_defaults(func=cmd_dominios)

    doc = sub.add_parser("doctor", help="diagnostica proxy, HTTP/3 e acesso a cada domínio")
    comuns(doc)
    doc.set_defaults(func=cmd_doctor)
    return ap


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        evento("aviso", acao="interrompido")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
