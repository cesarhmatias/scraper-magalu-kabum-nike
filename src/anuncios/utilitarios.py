"""Utilitarios pequenos e sem dependencias."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone


def slug(termo: str, separador: str = "-") -> str:
    termo = termo.strip().lower()
    termo = unicodedata.normalize("NFKD", termo)
    termo = "".join(c for c in termo if not unicodedata.combining(c))
    termo = re.sub(r"[^a-z0-9]+", separador, termo)
    return termo.strip(separador)


def numero(valor) -> float | None:
    """Converte 2899.99, '3.588,22', 'R$ 89,90' em float."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).replace("R$", "").replace("\xa0", " ").strip()
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def reais(valor: float | None) -> str:
    if valor is None:
        return ""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def parcela(max_parcelas, valor_parcela) -> str | None:
    if not max_parcelas:
        return None
    try:
        n = int(max_parcelas)
    except (TypeError, ValueError):
        return None
    v = numero(valor_parcela)
    if v is None:
        return f"{n}x"
    return f"{n}x de {reais(v)}"


def agora() -> datetime:
    return datetime.now(timezone.utc)


def primeiro(valor):
    if isinstance(valor, list) and valor:
        return valor[0]
    return valor
