"""Contrato dos provedores de busca interna."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import Config
from ..http import Http
from ..models import ResultadoDominio


class Provider(ABC):
    nome: str
    dominio: str
    aliases: tuple[str, ...] = ()
    descricao: str = ""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.http = Http(cfg, self.dominio)

    @abstractmethod
    def coletar(self, termo: str, paginas: int = 1) -> ResultadoDominio:
        raise NotImplementedError

    def fechar(self) -> None:
        self.http.fechar()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.fechar()
