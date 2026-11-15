"""Log JSON Lines em stderr, sem credenciais."""
from __future__ import annotations

import json
import sys
import time
from typing import Any


def evento(nivel: str = "info", **campos: Any) -> None:
    registro = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "nivel": nivel}
    registro.update(campos)
    print(json.dumps(registro, ensure_ascii=False, default=str), file=sys.stderr, flush=True)
