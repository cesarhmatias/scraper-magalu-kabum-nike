"""Modelos de dados da coleta."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class Anuncio:
    dominio: str
    termo: str
    pagina: int
    posicao: int
    id: str | None
    titulo: str
    marca: str | None = None
    preco: float | None = None
    preco_original: float | None = None
    desconto_pct: float | None = None
    parcelamento: str | None = None
    vendedor: str | None = None
    categoria: str | None = None
    preco_pix: float | None = None
    disponivel: bool | None = None
    avaliacao: float | None = None
    avaliacoes: int | None = None
    patrocinado: bool | None = None
    url: str | None = None
    imagem: str | None = None
    coletado_em: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    transporte: str = "h2"
    fonte: str | None = None

    def linha(self) -> dict:
        d = asdict(self)
        d["coletado_em"] = self.coletado_em
        return d


@dataclass(slots=True)
class ResultadoDominio:
    dominio: str
    termo: str
    anuncios: list[Anuncio] = field(default_factory=list)
    paginas: int = 1
    total_declarado: int | None = None
    transporte: str = "h2"
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    duracao_ms: int = 0
    url_consulta: str | None = None
    build_id: str | None = None
