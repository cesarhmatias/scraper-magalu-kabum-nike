"""Provedores de busca interna."""
from __future__ import annotations

from .base import Provider
from .casasbahia import CasasBahia
from .kabum import Kabum
from .magalu import Magalu
from .nike import Nike

TODOS: tuple[type[Provider], ...] = (Magalu, Kabum, Nike, CasasBahia)

_ALIASES: dict[str, type[Provider]] = {}
for _p in TODOS:
    _ALIASES[_p.dominio] = _p
    _ALIASES[_p.nome] = _p
    for _a in _p.aliases:
        _ALIASES[_a] = _p


def resolver(dominio: str) -> type[Provider]:
    chave = dominio.strip().lower().removeprefix("www.").rstrip("/")
    if chave in _ALIASES:
        return _ALIASES[chave]
    for nome, prov in _ALIASES.items():
        if chave.startswith(nome) or nome in chave:
            return prov
    disponiveis = ", ".join(sorted({p.nome for p in TODOS}))
    raise KeyError(f"dominio nao suportado: {dominio!r}. Disponiveis: {disponiveis}")


__all__ = ["Provider", "Magalu", "Kabum", "Nike", "CasasBahia", "TODOS", "resolver"]
