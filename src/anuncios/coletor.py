"""Orquestracao da coleta por dominio, com isolamento de falhas."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .config import Config
from .http import BloqueioError, ErroColeta, SemResultados
from .log import evento
from .models import ResultadoDominio
from .providers import resolver


@dataclass
class Coleta:
    termo: str
    resultados: list[ResultadoDominio] = field(default_factory=list)
    falhas: list[ResultadoDominio] = field(default_factory=list)
    duracao_ms: int = 0

    @property
    def anuncios(self):
        return [a for r in self.resultados for a in r.anuncios]

    @property
    def ok(self) -> bool:
        return bool(self.anuncios)

    @property
    def parcial(self) -> bool:
        return bool(self.falhas) and bool(self.anuncios)


def coletar(termo: str, dominios: list[str], paginas: int, cfg: Config,
            pausa_entre_dominios: float = 1.0) -> Coleta:
    inicio = time.perf_counter()
    coleta = Coleta(termo=termo)
    for i, dominio in enumerate(dominios):
        try:
            classe = resolver(dominio)
        except KeyError as exc:
            res = ResultadoDominio(dominio=dominio, termo=termo, erros=[str(exc)])
            coleta.falhas.append(res)
            evento("erro", acao="dominio_desconhecido", dominio=dominio, erro=str(exc))
            continue

        evento("info", acao="inicio_dominio", dominio=classe.dominio, termo=termo, paginas=paginas)
        provider = classe(cfg)
        t0 = time.perf_counter()
        try:
            resultado = provider.coletar(termo, paginas)
            coleta.resultados.append(resultado)
            evento(
                "info", acao="fim_dominio", dominio=classe.dominio, anuncios=len(resultado.anuncios),
                transporte=resultado.transporte, duracao_ms=resultado.duracao_ms,
                total_declarado=resultado.total_declarado,
            )
        except SemResultados as exc:
            res = ResultadoDominio(dominio=classe.dominio, termo=termo)
            res.avisos.append(str(exc))
            res.duracao_ms = int((time.perf_counter() - t0) * 1000)
            coleta.resultados.append(res)
            evento("aviso", acao="sem_resultados", dominio=classe.dominio, detalhe=str(exc))
        except BloqueioError as exc:
            res = ResultadoDominio(dominio=classe.dominio, termo=termo)
            res.erros.append(f"bloqueio: {exc.evidencia} (status {exc.status})")
            res.duracao_ms = int((time.perf_counter() - t0) * 1000)
            coleta.falhas.append(res)
            evento("erro", acao="bloqueio", dominio=classe.dominio, status=exc.status,
                   evidencia=exc.evidencia, url=exc.url)
        except ErroColeta as exc:
            res = ResultadoDominio(dominio=classe.dominio, termo=termo)
            res.erros.append(str(exc))
            res.duracao_ms = int((time.perf_counter() - t0) * 1000)
            coleta.falhas.append(res)
            evento("erro", acao="falha_dominio", dominio=classe.dominio, erro=str(exc)[:400])
        except Exception as exc:  # nunca derruba os outros dominios
            res = ResultadoDominio(dominio=classe.dominio, termo=termo)
            res.erros.append(f"{type(exc).__name__}: {exc}")
            res.duracao_ms = int((time.perf_counter() - t0) * 1000)
            coleta.falhas.append(res)
            evento("erro", acao="excecao", dominio=classe.dominio,
                   erro=f"{type(exc).__name__}: {exc}"[:400])
        finally:
            provider.fechar()

        if i < len(dominios) - 1:
            time.sleep(pausa_entre_dominios)

    coleta.duracao_ms = int((time.perf_counter() - inicio) * 1000)
    return coleta
